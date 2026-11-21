# Spike: joins mined from customer SQL as relationship evidence

Status: spike, 21 November 2026. A report and a throwaway runner (`tools/spikes/sql_lineage/`); no product code, no
new dependency of the server or the workload, nothing run against Fabric or Azure. Synthetic tables only.

## Purpose

A customer's warehouse usually comes with SQL that already joins its tables: views, notebooks, stored procedures,
dbt models. Each equality join in that SQL (`VBAP.MANDT = VBAK.MANDT AND VBAP.VBELN = VBAK.VBELN`) is a statement
by someone who knew the data that those columns match. The question: can a parser pull those pairs out reliably
enough (aliases, CTEs, subqueries, APPLY, MERGE, two dialects resolved to base tables) to use them as one more kind
of evidence for a relationship? Two parsers were compared:

- **sqlglot** 30.33.0 (Python, https://github.com/tobymao/sqlglot), already a test extra of this repository.
- **sqllens** 1.11.0 (TypeScript, https://github.com/NiclasOlofsson/sqllens), a separate open-source project,
  installed only inside the spike folder. Its API was learned from its README and `docs/` at commit
  `ae24f646c0abf2b8ff1bcfac92432bd761c5afc0` and from the type declarations (`dist/*.d.ts`) in the npm package; no
  sqllens code was copied.

## Corpus

19 statements written for this spike (`tools/spikes/sql_lineage/corpus/`), 12 T-SQL (Fabric Warehouse) and 7 Spark
SQL, over the synthetic SAP-shaped tables of `fabric_backend/sap_demo.py` (VBAK, VBAP, VBEP, KNA1, MARA, MAKT, LIKP,
LIPS, VBRK, VBRP, VBPA, TVKO) and the Salesforce-shaped tables of `fabric_backend/salesforce_demo.py` (Account,
Opportunity, OpportunityLineItem, Pricebook2, PricebookEntry, Product2, Contact, Order, OrderItem, Quote). Each
file's header holds the expected answer: the equality join pairs as unordered `{TABLE.COL, TABLE.COL}` between base
tables, and the base-table columns behind each output column. 61 expected pairs, 66 expected output columns.

| # | Covers |
|---|---|
| 01 | CREATE VIEW, three-part names `lakehouse.dbo.VBAK`, composite ON (MANDT + VBELN) |
| 02 | bracket quoting `[lh].[dbo].[VBAP]`, chained LEFT JOINs, a literal filter inside ON |
| 03 | chained CTEs, a join on CTE columns that must resolve to VBAP/VBAK |
| 04 | join inside a derived table, then a join on its renamed column (`order_no` = LIPS.VGBEL) |
| 05 | old-style comma joins, join conditions in WHERE |
| 06, 07 | OUTER APPLY (TOP 1, three-column correlation), CROSS APPLY over a derived table with its own JOIN |
| 08 | MERGE with a joined USING source; the target table is not in the schema |
| 09 | INSERT ... SELECT over four Salesforce joins |
| 10 | UNION ALL, a join in each branch, a literal output column |
| 11 | window functions |
| 12 | date-range predicates (BETWEEN, >=) next to equalities: the ranges must not be reported as key pairs |
| 13, 14 | Spark backticks `` `sales_lh`.`dbo`.`Order` ``, `lakehouse.schema.table`, a CTE joined on |
| 15 | a compiled dbt model: import CTEs with `select *`, a `final` CTE, `select * from final` |
| 16 | an uncompiled dbt model with `{{ config() }}` and `{{ ref() }}` |
| 17 | Spark INSERT OVERWRITE, item-level keys through AUBEL/AUPOS |
| 18 | correlated EXISTS (a semi-join written in WHERE) and an IN subquery (not an equality, not expected) |
| 19 | JOIN ... USING (MANDT, VBELN, POSNR): no ON predicate at all |

Lineage is scored as exact set equality per output column (every column the output expression reads, window
PARTITION/ORDER BY included; a literal has none). Join pairs are scored per statement as precision and recall.

## What each tool needed (glue)

Both runners share one extraction rule, written for the spike: an equality between two plain columns that is a
conjunct (through AND only) of a JOIN ON, WHERE or HAVING, with both sides resolved to base-table columns of two
different tables. Neither library has a "list the join keys" call; this is about 35 lines on the sqlglot side
(`resolve`, `is_join_predicate`, the loop) and about 20 on the sqllens side (`conjuncts`, the loop, name
normalisation), since sqllens's `originsOfExpr` already follows a column through CTEs, subqueries and correlated
scopes to its base table.

Out of the box, then the workaround glue (switched off with `--raw`):

- **sqlglot**: `parse_one`, `qualify` (aliases, `*` expansion, USING rewritten to ON), `traverse_scope`, `lineage`
  handle everything except: MERGE (no scope for its ON: about 3 lines rewrite it into `SELECT 1 FROM target JOIN
  source ON ...`), uncompiled jinja (a parse error: 5 lines of regex render `ref`/`source`/`config`), and lakehouse
  and schema prefixes (5 lines drop them; with a flat schema this changed no score here).
- **sqllens**: parse, scopes, `originsOfExpr`, `lineage` and native dbt templating (`minijinja()` with the shipped
  `DbtTemplateProvider`, an option rather than glue) handle everything except: T-SQL `CREATE VIEW`, `INSERT ... SELECT`
  and `MERGE`, which 1.11.0 parses without errors but lowers as `unparsed` (about 17 lines find the inner
  `Select_statementContext` in the CST, the documented escape hatch, and analyse that text again; MERGE gets the same
  SELECT rewrite as on the sqlglot side); `JOIN ... USING` (the IR keeps the column list, about 10 lines pair it with
  the earlier source that has the column); quoting (origins keep `` `ID` `` and `[ID]` as written, by design per its
  `docs/identifier-delimiter-contract.md`, so names are stripped before comparing); and a `CallbackSchema` (2 lines)
  so that any prefix finds the flat demo table (on the statements that needed no other glue the scores were the same
  with a plain `Schema`; it removes unknown-table diagnostics). Grammar context names are internals, not an API, so the CST glue can break on any release.

## Results

Per statement, with the glue (joins precision / recall / lineage exact):

| Statement | Dialect | sqlglot | sqllens |
|---|---|---|---|
| 01_view_order_items | tsql | 2/2 / 2/2 / 5/5 | 2/2 / 2/2 / 5/5 |
| 02_bracket_quoting | tsql | 4/4 / 4/4 / 4/4 | 4/4 / 4/4 / 4/4 |
| 03_chained_ctes | tsql | 4/4 / 4/4 / 4/4 | 4/4 / 4/4 / 4/4 |
| 04_subquery_in_from | tsql | 4/4 / 4/4 / 3/3 | 4/4 / 4/4 / 3/3 |
| 05_old_style_where | tsql | 4/4 / 4/4 / 4/4 | 4/4 / 4/4 / 4/4 |
| 06_outer_apply | tsql | 3/3 / 3/3 / **2/3** | 3/3 / 3/3 / 3/3 |
| 07_cross_apply | tsql | 4/4 / 4/4 / **1/3** | 4/4 / 4/4 / 3/3 |
| 08_merge | tsql | 4/4 / 4/4 / - | 2/2 / **2/4** / - |
| 09_insert_select | tsql | 4/4 / 4/4 / 5/5 | 4/4 / 4/4 / 5/5 |
| 10_union | tsql | 4/4 / 4/4 / 3/3 | 4/4 / 4/4 / **1/3** |
| 11_window | tsql | 1/1 / 1/1 / 5/5 | 1/1 / 1/1 / 5/5 |
| 12_date_range_not_a_key | tsql | 4/4 / 4/4 / 3/3 | 4/4 / 4/4 / 3/3 |
| 13_spark_backticks | spark | 3/3 / 3/3 / 4/4 | 3/3 / 3/3 / 4/4 |
| 14_spark_cte_lakehouse | spark | 2/2 / 2/2 / 3/3 | 2/2 / 2/2 / 3/3 |
| 15_dbt_rendered | spark | 1/1 / 1/1 / 4/4 | 1/1 / 1/1 / 4/4 |
| 16_dbt_ref_jinja | spark | 1/1 / 1/1 / 3/3 | 1/1 / 1/1 / 3/3 |
| 17_spark_insert_overwrite | spark | 7/7 / 7/7 / 5/5 | 7/7 / 7/7 / 5/5 |
| 18_spark_exists | spark | 2/2 / 2/2 / 2/2 | 2/2 / 2/2 / 2/2 |
| 19_spark_using | spark | 3/3 / 3/3 / 3/3 | 3/3 / 3/3 / 3/3 |

Totals (`python score.py`, `results/score.md`):

| Run | Join precision | Join recall | Lineage exact | Parse failures |
|---|---|---|---|---|
| sqlglot 30.33.0, with glue | 61/61 (100%) | 61/61 (100%) | 63/66 (95%) | 0/19 |
| sqllens 1.11.0, with glue | 59/59 (100%) | 59/61 (97%) | 64/66 (97%) | 0/19 |
| sqlglot, out of the box (`--raw`) | 58/58 (100%) | 58/61 (95%) | 60/66 (91%) | 1/19 (the jinja model) |
| sqllens, out of the box (`--raw`) | 47/47 (100%) | 47/61 (77%) | 51/66 (77%) | 1/19 (the jinja model, no templating declared) |

In the sqllens `--raw` run three more T-SQL statements (01, 08, 09) parse without a syntax error but come back as
`unparsed`, so they yield nothing; with USING (19) that explains the gap to the glued run.

What went wrong, and why:

- **No wrong join pair from either tool.** The date ranges in 12 (BETWEEN, >=), the literal filters, the MERGE
  `UPDATE SET t.x = s.x` and the IN subquery in 18 were not reported as key pairs. That is mostly the extraction
  rule (plain column = plain column, conjuncts only), which is the same on both sides.
- **sqllens, MERGE target (08)**: `t.MANDT = s.MANDT` is not resolved because `order_summary` is not in the schema
  and sqllens answers "unknown" rather than guess; sqlglot resolves a qualified column without the schema. With
  `order_summary` added to the schema, sqllens resolves both sides (checked separately, not in the scored run).
- **sqllens, UNION lineage (10)**: when the second branch starts with an unnamed literal (`SELECT 'invoice', r.VBELN,
  c.NAME1`), its columns are matched to the wrong outputs: `doc_type` gets VBRK.VBELN, `doc_no` gets KNA1.NAME1.
  Reproduced in isolation; with aliases in the second branch, or the literal last, the answer is right. A wrong
  answer rather than an unknown one, worth reporting upstream with the two-line repro.
- **sqlglot, APPLY lineage (06, 07)**: sqlglot turns APPLY into `LATERAL`; `lineage` ends the inner columns in
  placeholder nodes and returns the correlated outer key columns (VBAP.MANDT, VBELN, POSNR) instead of VBEP.EDATU.
  The join pairs from the same statements were all right, since they come from the scopes, not from `lineage`.

Caveats: 19 statements written by the same person who wrote the expected answers and the extraction; a customer's
SQL will have temp tables, dynamic SQL, procedures, macros and dialect corners not covered here. The numbers show
that both tools can do the job on common shapes, not how often they will on a real estate.

## Licences (verified)

- **sqlglot 30.33.0**: MIT. Read in the installed package, `sqlglot-30.33.0.dist-info/licenses/LICENSE` ("MIT
  License, Copyright (c) 2026 Toby Mao"), and its metadata `License-Expression: MIT`, on 21 November 2026.
- **sqllens 1.11.0**: MIT. `LICENSE` read at commit `ae24f646c0abf2b8ff1bcfac92432bd761c5afc0` (the `gitHead` npm
  records for 1.11.0; commit dated 14 September 2026) on 21 November 2026; the copy in the npm tarball is the same
  file. Its `THIRD-PARTY-NOTICES.md` says the forked grammars keep their upstream licences: Apache-2.0 for the
  Databricks grammar (from Apache Spark, with its NOTICE reproduced), MIT for T-SQL and Snowflake, BSD-3 for BigQuery
  and Redshift. Its one runtime dependency, `antlr4ng` 3.0.16, is BSD-3-Clause (its `LICENSE` in the package).

Using either as a dependency later means a pin in `deploy/constraints.txt` (sqlglot is today only an unpinned test
extra) or in `workload/Workload/package-lock.json`, and `python tools/third_party_notices.py` per CONTRIBUTING.md.
No code was copied from either, so the vendored-code rules do not apply to this spike.

## Maintenance risk (facts checked 21 November 2026)

- **sqlglot**: on PyPI since 0.1.0 (18 March 2021); 795 releases, 47 of them in 2026, the latest 30.33.0 on
  17 November 2026 (PyPI JSON API). Its git history (a blob-less clone of `tobymao/sqlglot`) has 9 011 commits on
  the default branch by 516 distinct author names, 265 of them in the last twelve months. Risk: frequent releases
  change behaviour (major version 30), so a pin and our own tests on the extraction are needed.
- **sqllens**: first published to npm on 9 July 2026 (0.1.0; `npm view sqllens time`), 18 versions, the latest
  1.11.0 on 14 September 2026, no release since. One npm maintainer. The repository's first commit is from 6 June
  2026; of 935 commits, 913 are by one human author and the rest by bots, and its HEAD on 21 November 2026 was
  still the 1.11.0 commit. The npm package unpacks to 46.9 MB (`dist.unpackedSize`), relevant for a browser bundle.
  Risk: a young single-maintainer project; good design documents and an explicit "never guess" rule, but a bus
  factor of one and a short history.

## Recommendation

Use sqlglot in the Python server for join mining: it found every expected pair and no wrong one, with less glue
(it models CREATE VIEW and INSERT out of the box; only MERGE's ON needed a 3-line rewrite), runs in the server's
language, is already in the test extras, and has a large contributor base. Keep its `lineage` out of the APPLY case, or resolve those columns from the
scopes as the join extraction does. sqllens is a reasonable candidate later for the TypeScript workload frontend
(the Model editor), where an error-tolerant parser with spans, completion and native dbt templating fits an editor;
before that, its T-SQL DDL/DML lowering and the UNION finding should be rechecked on a newer release, and the bundle
size measured.

## How mined joins would enter Krusgraph (evidence only)

A mined pair is a hint with a source, the same standing as the SAP pack's relationships, never a decision:

1. The customer hands over files (views, notebooks, dbt `target/compiled` output); Krusgraph would parse them
   with sqlglot in the server. No SQL is executed and the SQL text is not kept beyond the run.
2. Each pair group (all conjuncts of one ON between the same two tables, e.g. VBAP.(MANDT, VBELN) -> VBAK.(MANDT,
   VBELN)) becomes a relationship candidate with the rule `seen in customer SQL: <file>` (with the line), the
   direction taken from the side whose columns are the target's key in the plan (K0/K1/R5); without a known key it
   stays a candidate with no direction and is not applied. Several files saying the same thing are listed, not
   weighted.
3. It goes through the existing order: declared keys, the caller's keys and confirmed relationships win; a candidate
   that contradicts them is reported, not applied. A pair on a non-key column set goes to `plan.extended`
   (`ExtendedRelationship`, kind "unique"), as pack joins do.
4. `validate_plan` counts it like any other relationship: the target key unique and free of NULLs, the orphan count
   of the reference. The rule stays visible, so a reviewer sees "seen in customer SQL" next to the counts.

Deterministic rules only: the parser, the extraction rule above and the counts. No AI or LLM reads the SQL or
decides on a candidate. Non-equality predicates (date ranges) are not key evidence; a later round could map them to
`valid_on` only with an explicit rule.

## Proposal: row counts after each join in dry runs

Idea from the CTE-by-CTE row-count profiler and step debugger described in the README of dbt-anvil-vscode
(https://github.com/NiclasOlofsson/dbt-anvil-vscode, a separate open-source VS Code extension, MIT; `LICENSE` and
README read at HEAD, commit `ecf9ed730672f8bcc4d2c46a1d5d5866d39c861d` of 15 September 2026, on 21 November 2026): run each step separately and show the rows it produced, so the step that
multiplied the row count is visible. Proposal only, no code.

When Krusgraph drafts a mart (`fabric_backend/dbt.py`, `_mart`) and answers with a dry run, it would add one
counting query per join step of the draft, in the order the joins are written, read-only, within the existing time
budget: the row count after the step and, for each header amount the plan already knows (`amounts.header_amounts`),
its sum. A step whose count grows on a many-to-one join, or whose amount sum changes, is marked. Worked example on
the synthetic SAP demo (counted in SQLite with `sap_demo.sqlite()`; all three orders, both clients):

| Step | Rows | SUM(VBAK.NETWR) | Reading |
|---|---|---|---|
| VBAK | 3 | 750 | one row per order |
| + VBAP on MANDT, VBELN | 5 | 1 950 | fan-out: order 0000000001 has three items, its 600 counts three times; the orphan item 0000000009 drops out (VBAP has 6 rows) |
| + MARA on MANDT, MATNR | 5 | 1 950 | many-to-one, unchanged |
| + KNA1 on MANDT, KUNNR | 5 | 1 950 | many-to-one, unchanged |

Two mistakes the same view makes visible: VBAP joined on VBELN without MANDT gives 9 rows and 2 700 (client 200's
order 0000000001 meets client 100's items), and MAKT added without `SPRAS = 'E'` takes the 5 rows to 9 (one text per
language). The draft states the grain it means (one row per VBAP item here); a step that ends above that grain, or
an amount that is not at the grain's level, is the finding. It complements `validate_plan`, which counts single
relationships, by counting the chain as the mart writes it.
