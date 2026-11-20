# Migrations as a product on Krusgraph's engine: Qlik Sense to Power BI first (Q1)

Round Q1, 15 November 2026, written by a scheduled Claude session with no live user, from the founder's question of
the same day: "Are there other workloads we can build that use Krusgraph's engine? For example Qlik migration to
Power BI." This text says which shape such a product should take, what a first version does, and what this round
built. The market, competitors, prices and the ranking of other products by market are business material and are
kept outside this repository.

It builds on, and does not repeat: `MIGRATION-DESIGN.md` (W7: the journey, the reader for a `.qvs`),
`MIGRATION-PLATFORMS-DESIGN.md` (W10: the truths file, the difference rules D1 to D10, part B on Qlik),
`SCOPE-REVIEW.md` (S1: count before claiming) and `PUBLISHING-READINESS.md` (W11: the workload name).

Rules for this text, as in W7 and W10:

- **No AI in Krusgraph for Fabric.** Every step is a rule, a count or a table lookup. The chat's own model, in the
  customer's client, reads Krusgraph's answers; it is not part of Krusgraph.
- **No claim** that a migration gets faster, cheaper or compliant, and no share of anything "converted".
- **Independent.** Krusgraph is not affiliated with Microsoft or Qlik. Qlik, QlikView and Qlik Sense are trademarks
  of QlikTech International AB; Power BI and Microsoft Fabric are trademarks of Microsoft. They are named here only
  to say what is read and what is built.
- **Verified** means a page on `learn.microsoft.com` was opened on 15 November 2026 and says it. This session's
  network reached that host only. **Every Qlik fact is Unverified**: written from public knowledge of Qlik's
  documentation or from a search summary, to be read on the page before anything public rests on it.
- Nothing here is legal advice. The lines about what may be read are a design position for a lawyer to confirm.

---

## 0. Update, round Q2 (16 November 2026)

Written by a scheduled Claude session with no live user. The text from section 1 on is Q1's and is kept as it was
written, with a note where Q2 changed something. Three things changed.

**The founder decided the shape**, on 16 November 2026, differently from Q1's recommendation in section 1:

| Decision | Where it is carried |
|---|---|
| Migrate becomes its own Fabric workload. Registered name proposal `Krusgraph.Migrate`; "Qlik" is not in the registered name (a trademark); the display text may say "Krusgraph Migrate - from Qlik to Power BI" | `MIGRATE-WORKLOAD-DESIGN.md`: a design, nothing built, and the name is in no build |
| The chat (MCP) tools and a guided page are built first, because workload name registration is still blocked | Section 3b below; `MIGRATE-GUIDED-PAGE-DRAFT.md` |
| Customers are meant to use both Migrate and `Krusgraph.Modeler` | `MIGRATE-WORKLOAD-DESIGN.md` section 4 |
| Load scripts may go through the hosted server by default, with a local-only path for sensitive customers | The three tools are on the hosted server and on the local server (`LOCAL.md` section 4) |

So section 1's "not (b)" and section 6's questions 1 and 2 are answered: (b), and hosted by default.

**The reader was run on public load scripts**: 58 files from four public repositories under the MIT licence
(`tests/fixtures/qlik/SOURCES.md` has each source, commit, licence and change). Of 1 856 statements the reader now
reads 1 092, lists 722 as control flow and 29 as includes of files it was not given, and leaves 13 not read. Before
this round's fixes it left 813 under "not read". That corpus has no data model: no file in it has two tables that
share a field, so associations and synthetic keys are still tested on the synthetic script only.

**Three tools exist** (section 3b): `qlik_plan`, `qlik_measures_draft` and `qlik_reconcile_draft`. Steps 5, 6 and 7
of section 2.2 are built as tools. Nothing here has read a script from a customer's Qlik installation, and
every Qlik fact is still Unverified: `help.qlik.com` and `qlik.dev` could not be reached in this round either.

---

## 1. Which shape

Three candidates.

| | (a) A second item type, "Migration", in the `Krusgraph.Modeler` workload | (b) A separate Fabric workload | (c) MCP tools and a guided page |
|---|---|---|---|
| Registration with Microsoft | None new. An item type lives under its workload's name (`<workload>.<item>`, as `Krusgraph.Modeler.Model` does), so it follows the one registration that is already being worked on | A second `[Publisher].[Workload]` name, reserved for good at first upload, with its own Entra audience, its own attestation and its own Workload Hub request. The first name is not registered yet (`PUBLISHING-READINESS.md`, blocker 1) | None. The local server needs no Microsoft review; the hosted connector is live already |
| Marketplace | The same offer and the same plans (Team and Business are the plan names; no price is decided). Which paid feature an organisation has is decided per feature in `entitlements.py` (dormant today), so a Migration item is one more feature of a plan, not a new listing | A second offer, or one offer whose plans span two workloads: the listing requirement ties a workload to an offer, and this was not read for two workloads | Not listed through the Hub. Sold directly, or as part of the same subscription |
| What must be built before a customer can use it | A new editor (the kit's item scaffolding, the six-step frame of `WORKLOAD-UX-DESIGN.md` reused), the manifest entry, a route in `workload_api.py` | Everything in (a), plus a second package, a second build in CI and a second sign-in configuration (the server holds one workload app today, `WORKLOAD-PUBLISH.md`) | One tool on the module built in this round, in the local server first; a page that walks the steps |
| What blocks it today | The name registration, as for the Model item | The same, twice | Nothing |
| Where the customer's Qlik script goes | Through the hosted editor to krusgraph.com for the call | The same | With the local server it stays on the customer's machine (W10's default for the source side) |
| No AI in the Fabric item | Holds: the item calls the same rules | Holds | Holds for the tools; the chat's model belongs to the customer's client |

**Recommended: (c) now, then (a), and not (b).** In three steps, each usable on its own:

1. **Now: the engine module, a local MCP tool and a guided page.** A migration starts as an assessment of what the
   customer has, and the source side should not leave the customer's machine. Nothing here waits for Microsoft.
2. **Next: "Start from a Qlik load script" inside the existing Model item.** The module's output is a Krusgraph plan
   with its keys and confirmed links, which is exactly what the Model item's Review step takes. No new item type, no
   manifest change: one more way into step one of the editor.
3. **Later: a Migration item type in the same workload**, when there is state of its own to keep that a Model item
   has no place for: the truths file, the reconciliation runs over time, who accepted which difference, the cutover
   sheet. That is the point where a second item earns its place in **+ New item**.

Why not (b): a second workload name costs a second registration, attestation and listing before the first exists, and
it would split one engine across two sign-in configurations. It becomes worth it only if migrations are sold under
their own name to a buyer who would never install a modelling workload. That is a business decision, and nothing
technical is lost by taking it later: the module does not know which shape calls it.

One thing was not read on a Microsoft page and must be before step 3: that a workload may hold several item types.
The kit's manifest has an `items/` folder and `WORKLOAD-FEASIBILITY.md` writes "its own item types"; neither is the
publishing requirement.

---

## 2. The first version: Qlik Sense to Power BI on Fabric

### 2.1 What can be read, and what should not be

| Input | Realistic | May it be read | First version |
|---|---|---|---|
| **The load script as text**: copied from the data load editor, or exported as a `.qvs` file | Yes. Every Qlik developer can do it, per app | It is the customer's own script, taken out with the product's own editor: ordinary use | **Yes. This is the input.** |
| **The app unbuilt by Qlik's own command line** (`qlik app unbuild`: script, master measures, dimensions, variables as JSON and YAML files, from an app in a running engine) | Yes, for someone with access to the engine. It is how the master measures are reached | Qlik's own published tool, run by the customer | Next (section 5, Q5). Unverified: the file layout must be read on qlik.dev |
| **The Engine JSON API or the QRS API** (the script, the tables and keys, the list of apps) | Yes, for an inventory of many apps | A documented API, with the customer's own credentials | Later, and only from the local server: Krusgraph's hosted service should not hold a Qlik credential |
| **A `.qvf` file opened directly** | Tempting: it is one file | **No.** It is a binary format with no public specification that this session could find, and Qlik's customer agreement is reported to forbid reverse engineering (a search summary; Unverified). The customer opens the app in Qlik and exports from there | Never read |
| **`.qvd` data files** | They hold the rows | Not needed: the rows are landed from the original sources, or stored out of Qlik by the customer in an open format | Not read |
| **Qlik's numbers for the validation**: a table exported from the app, one measure per grain, no selections | Yes | The customer's own data, exported by the customer | Next (Q3) |

Krusgraph connects to nothing on the Qlik side in the first version and evaluates no Qlik expression.

### 2.2 The steps

| # | Step | What Krusgraph does, by rule | State |
|---|---|---|---|
| 1 | Read the script | Tables, fields, loads, joins, concatenations, mapping tables, QUALIFY, synthetic keys, circular references; every statement not read listed with its line | **Built**: W7's reader, and this round's `read_script` |
| 2 | Tables for the lakehouse | Per table: a column name per field that a Delta table accepts, the source of each field, and whether the table is a copy of its source or shaped in the script (the list of steps to rebuild in silver) | **Built** (this round) |
| 3 | Associations to a star schema | A one side per association from counts in the rows; each synthetic key in one of five cases; roles (fact, dimension); a second path between two tables named | **Built** (this round) |
| 4 | A Krusgraph plan | Keys and confirmed links as `infer.Plan`; the engine's own check (`validate_plan`) and the semantic model draft read it | **Built** (this round), as a library call |
| 5 | Measures | Master measures and chart expressions under W10's three labels (section 2.4) | **Built in Q2** as `qlik_measures_draft`; fewer rules than section 2.4 lists (section 3b) |
| 6 | Validate truths | The exported Qlik table against the new model's SQL per grain; equal, or a reason that reproduces the number, or open (section 2.5) | **Built in Q2** as `qlik_reconcile_draft`: the statement and the comparison; it names no reason (section 3b) |
| 7 | A tool and a page | `qlik_plan` in the local server; the guided page | **Built in Q2**: three tools, hosted and local; the page is a draft in `docs/` |

### 2.3 Associations: the trap, and how it is decided

Qlik associates two tables on every field name they share. With two or more shared fields it builds a synthetic key
over them together, so two rows associate only where all of them are equal. A Power BI relationship has one column
per side and needs a one side where the value is unique. One relationship per shared field gives two paths between
the same tables, or a link on a field that is unique nowhere; choosing one field silently changes which rows
relate. So each synthetic key is put in exactly one case, and the counts that decided it are in the answer.

| Case | The counts show | What goes into the plan |
|---|---|---|
| One field links | Exactly one shared field is unique in one of the two tables | A relationship on that field. For every other shared field, the number of rows that matched on the link but differed there: in Qlik those rows did not associate, in the new model they do |
| A composite key | No single field is unique; the fields together are unique in one table | One relationship on all the fields, carried as one combined key column (`combined_keys.py`) |
| Two facts sharing dimensions | The fields together are unique in neither table | No relationship between the two. Each field is a dimension both relate to: an existing table, or a proposed new one. A real many-to-many is a person's decision |
| A person decides | More than one field could carry the link, or both tables are unique on the fields | Nothing; the candidates are listed |
| Not decided | Nothing was counted and the names do not say | Nothing; what to count is listed |

A shared field that is unique in no table is not a relationship either. It is an attribute two tables name alike,
which is also how many circular references arise: the loop disappears from the plan when that link does, and the
answer says so. Where a loop remains among real relationships, the second path is named and the semantic model
draft makes it inactive, as it does for any plan.

Without rows, the one side comes from Krusgraph's name rules and every such line says "by name, not counted". "Unique
nowhere" is never said without counting.

This differs from W10's B.3 in one way, as W10 asks to be told: B.3 has four cases, and this has five, because "not
decided" is a result of its own when the tables are not landed yet.

### 2.4 Measures: what a rule may translate (not built; W10 B.4 stands)

| Translated by rule | Suggested, with what may differ | Not translated: a person decides |
|---|---|---|
| `Sum`, `Min`, `Max`, `Avg`, `Count` of one field with no set expression | The same set modifier when the field is a chart dimension | Alternate states and bookmarks as set identifiers |
| `Count(DISTINCT f)` as `DISTINCTCOUNTNOBLANK` | Clearing a field, `{<Year=>}`; the identifier `1` | Set operators between sets |
| A master measure that only refers to other master measures | `TOTAL` and `TOTAL <fields>` | `Aggr` with `NODISTINCT`; nested `Aggr` |
| A set modifier that sets one field to literal values, `{<Year={2025}>}`, when that field is not a dimension where the measure is used | `P()` and `E()`; a search inside a set; `Aggr()` | Dollar-sign expansion computed at run time |
| | | Calculated dimensions; anything the reader could not parse; one measure name with two expressions in two apps |

The share of an app's expressions under each label is counted per app. None is promised in advance and none is
known today.

### 2.5 Validating truths (not built; W10 section 4 and B.5 stand)

The customer exports each KPI per grain from the Qlik app. Krusgraph computes the same KPI on the new model, per
grain, and writes one line per KPI: equal; or different, with the reason that reproduces the number exactly; or
open. It never says "probably". What this round adds to that design: step 3's counts are the first candidate
reasons, already with their row counts before any KPI is compared (rows without a match that land on the blank row;
rows a synthetic key kept apart; a link that had no unique side).

---

## 3. What this round built

`fabric_backend/qlik/`, with `tests/test_q1_qlik.py` (21 tests) and `tests/fixtures/q1/sales.qvs`.

| Call | What it gives |
|---|---|
| `qlik.read_script(text)` | W7's reading (`migration_read.read_qvs`, not changed), and per table: the lakehouse name, per field the column name and its source (a source column through renames and preceding loads, an expression, a join, a resident table that was dropped later, a mapping table through `ApplyMap` with its default and how to rebuild it as a join), the fields `QUALIFY` took out of the associations, and the steps the script performs on the table |
| `qlik.map_associations(read, execute=None, schema=...)` | Relationships with their one side and counts, the synthetic keys by case, shared fields with no key side, circular references and what became of them, second paths, what is undecided, how many queries ran and which failed |
| `qlik.to_plan(mapping, schema)` | `(infer.Plan, also_found)`: the keys as the caller's keys and the links as confirmed, so the plan holds what the mapping decided and nothing else; `also_found` lists what Krusgraph's name rules would add that was not an association in Qlik |

On the synthetic script (nine tables, eight linking fields, three synthetic keys, one circular reference) with
synthetic rows in a local database, counted:

- nine relationships, each with its one side counted; one order row and one shipment row without a match, named as
  rows that land on the blank row;
- the three synthetic keys in three different cases: one field links (three shipment rows matched their order on the
  key but differed on a second field that only shares a name); a composite key, carried as a combined key column in
  the semantic model draft; two facts sharing dimensions, with one existing dimension and one proposed;
- one shared field unique nowhere, and the circular reference gone with it; one second path named;
- the plan passes through `evidence.validate` and `semantic_model.draft` unchanged from how any plan does.

What it is not. (Q1 wrote: "It is **not a tool**: nothing in `server.py`, `mcp_server.py` or `workload_api.py` calls
it, and a test keeps it so." Since Q2 three tools call it, section 3b; the workload still does not.) It has not read
a script from a Qlik installation. Its rules about Qlik are Unverified. It runs no
Qlik expression, translates no measure and compares no number. It imports private helpers of `migration_read.py`
rather than keeping a second parser; a test fails if they change.

Limits a real script will meet first: control statements (`IF`, `FOR`, `SUB`) are listed and their loads read as if
each ran once; dollar-sign expansion that builds table or field names is counted, not expanded; `GENERIC`,
`INTERVALMATCH` and `HIERARCHY` are listed as not read (`CROSSTABLE` is applied since Q2); a `LOAD *` from a file gives a table whose
columns are not in the script; types are not in a script at all, so the plan's columns are strings until the landed
tables' own schema is passed in.

---

## 3b. What round Q2 built

**The reader, after the public corpus** (`fabric_backend/migration_read.py`, the Qlik part; `tests/test_q2_qlik_corpus.py`):

| What the corpus showed | What the reader does now |
|---|---|
| 722 control statements (`IF`, `FOR`, `SUB`, `CALL`) filled "not read" | Listed on their own (`control_statements`); the loads inside them are read as if each ran once, as before |
| `$(Include=...)` and `$(Must_Include=...)` | Listed as `includes`: a file the reader was not given. A `lib://` path inside one is no longer cut off as a comment |
| `SET` and `LET` with a name built by dollar-sign expansion, `SET v;` without a value, `name = expression` without `LET` | Read as variables |
| `REPLACE LOAD`, `ADD LOAD`, `BUFFER`, `FIRST n`, `SAMPLE p` | The load is read; the prefix is noted on it as not applied (it changes which rows, not which fields) |
| A label built by dollar-sign expansion, `NoConcatenate Label: LOAD` | Read; the plan flags a table whose name is built when the script runs |
| `CROSSTABLE (attribute, data, n)` | Applied: the first n fields stay, then the attribute field and the data field |
| `EXECUTE` | No effect on the tables |
| Every statement | Counted by type and outcome (`statements`): read, control flow, include, not read |

**Three tools** (`fabric_backend/qlik_tools.py`; `tests/test_q2_qlik_tools.py`), on the hosted server and on the local
server, read-only, with fixed rules and no AI model. Each answer carries `kg_card` (one result line, at most five
more, and notes), as the other tools' cards do.

| Tool | In | Out |
|---|---|---|
| `qlik_plan` | The load script as text. Optionally a workspace and a source (hosted) or `count=true` (local) to count in the landed tables | Tables with their lakehouse columns; relationships with their one side; each synthetic key in its case; circular references; `plan.keys` and `plan.confirmed`, the arguments `plan_backend`, `validate_plan`, `semantic_model_draft` and the creating tools take; a proposed star schema (facts, dimensions, tables in between, dimensions to build, what a person decides); statements by type; what was not read |
| `qlik_measures_draft` | Measures as name and expression; optionally the script, which says which table holds each field | Per expression a label (translated, suggested, not translated), its DAX or the reason, when a suggestion may differ from Qlik, the counts, and TMDL lines on request |
| `qlik_reconcile_draft` | The script, and KPIs with their exported values per grain; optionally the rows the statements returned | One T-SQL statement per KPI (the exported values, the KPI on the migrated tables, the comparison); the comparison table: equal, different, only in Qlik, only on the migrated tables, or to compute |

`qlik_measures_draft` carries fewer rules than section 2.4 lists. Built: the first column, and from the second
column the fixed-value set modifier, a cleared field, the identifier `1`, `TOTAL` and `TOTAL <fields>`, all as
"suggested" because the tool cannot know in which visual a measure is used. Not built, and answered as "not
translated" with the reason: `P()` and `E()`, a search inside a set, `Aggr()`. A field that is in several tables is
not translated either: Qlik treats it as one field, and which table's column a measure reads is a decision.

`qlik_reconcile_draft` writes the statement and compares; it does not yet test candidate reasons. Section 2.5's
"a reason that reproduces the number" is therefore not built: a difference is listed as open, with the checks that
may explain it. The export must be made with no selections.

On the synthetic script and rows of section 3, by the tests:

- `qlik_plan`, counted: nine relationships; the three synthetic keys in three cases; a star schema of four facts,
  three dimensions, two tables in between and one dimension to build.
- `qlik_measures_draft`, 24 expressions written to cover the rules: 9 translated, 7 suggested, 8 not translated.
  That share says nothing about a real app.
- `qlik_reconcile_draft`, nine KPIs with three planted differences: six get a statement and three a reason; run on
  SQLite, the statements find the three planted differences (one different value, one group only in the export, one
  only in the rows) and call the other nine rows equal.

What is not tested: the DAX was never run; the statements ran on SQLite and not on a Fabric SQL analytics endpoint;
the hosted tools were not called through the deployed connector; no script, measure or number came from Qlik.

---

## 4. Other products on the same engine: what each would reuse, and the effort

Rounds are build rounds of the usual size. The ranking by market is kept with the business material.

| Product | What the engine already has | What is new | Rounds, about |
|---|---|---|---|
| **Qlik to Power BI** | The reader, this round's plan, validate, the semantic model draft, combined keys | Measures by rule, the reconciliation, a tool and a page | 5 to 6 more |
| **Tableau to Power BI** | W7's `read_twb`, the same plan and model steps | Joins and relationships to a plan, level-of-detail expressions under three labels, the reconciliation (shared with Qlik) | 5 |
| **A data-quality and drift monitor item** | `evidence.py`, `drift.py`, `health.py`, `monitor.py`, the checks of a plan | Runs over time in Fabric, a history, an item or a view to show it | 2 to 3 |
| **Databricks and Snowflake to Fabric** | The Databricks adapter (mocked), `schema.py` on Snowflake, mirrored sources | W10's B1 to B5: the two-sided check, a Snowflake adapter, the truths file | 6 |
| **ECC to S/4HANA reconciliation** | The SAP pack, `amounts.py`, the two-sided check once built | A mapping file per object, counts and totals before and after; every mapping "proposed, not tested on a customer" | 3, after the two-sided check |
| **SAP BW to Fabric** | The SAP pack for the tables underneath | A reader for BW objects (InfoProviders, queries, transformations), which Krusgraph has nothing for, and no public test data | 8 or more |
| **A data product catalogue** | `catalog.py`, `product_life.py`, `domains.py` | A catalogue of its own beside Fabric's OneLake catalog, which is where Microsoft points governance | Not recommended as a product; keep it as the Model item's data product page |

The three that share the most with what exists are the two BI migrations (one reconciliation serves both) and the
monitor (it is the plan's own checks, run again).

---

## 5. Next builds, in order

| # | Build | Tested on | Rounds |
|---|---|---|---|
| Q2 | Measures "translated by rule" only (the first column of 2.4), each with its expected DAX, and the count per label | A synthetic set of expressions. Qlik's set analysis pages read first | **Done in round Q2**, without the Qlik pages (not reachable) |
| Q3 | The reconciliation per KPI: an exported table against the model's SQL per grain, with this round's counts and W10's D2 to D9 as candidate reasons; a reason is named only when it reproduces the number | The synthetic rows of this round with planted differences, and one case that must come out open | **Half done in round Q2**: the statement and the comparison. Testing candidate reasons is left: 1 |
| Q4 | `qlik_plan` as a tool in the local server, and the guided page (section 1, step 1) | The tool's answer under the listing caps; the page on the synthetic script | **Done in round Q2** (hosted and local); the page is a draft |
| Q4b | One real load script, its measures and a KPI export from a trial Qlik Sense app with synthetic data, run through the three tools | Whatever it breaks | 1, after the founder has a trial app |
| Q4c | `P()`, `E()`, a search in a set and `Aggr()` as suggestions with what may differ | Synthetic expressions, then Q4b's | 1 to 2 |
| Q5 | A reader for the files `qlik app unbuild` writes (master measures, dimensions, variables) | Files made by hand to the documented layout, then one real unbuild of a synthetic app | 1 |
| Q6 | "Start from a Qlik load script" in the Model item (section 1, step 2) | The workload's own tests | Replaced by the founder's decision: a Migration item in a workload of its own (`MIGRATE-WORKLOAD-DESIGN.md` section 9) |

## 6. Decisions for the founder

1. **The shape**: (c) now, then the entry in the Model item, then a Migration item type; no second workload. Agreed?
2. **May a load script be pasted into the hosted server**, or does the Qlik side stay local-only (W7's question 3,
   W10's decision 4)? Q4 builds for local-only unless told otherwise.
3. **Network for Q2 and Q5**: `help.qlik.com` and `qlik.dev`. Without them no Qlik fact moves from Unverified.
4. **One real script, synthetic data**: a load script exported from a trial Qlik Sense app, and its `unbuild`
   output. The reader's assumptions stand or fall on it.
5. **A lawyer's reading** of what may be read (2.1), before any text says so in public.
6. **Qlik or the monitor first?** They do not compete for the same code; they compete for rounds.

## 7. Not to be said on the site until built and tested

That Krusgraph migrates, converts or translates Qlik apps, or any share of them. That measures are translated. That
numbers are reconciled. That the Qlik reader exists as a feature. Anything about speed, cost or compliance.

Since Q2 the three tools are in the tool lists that render from `tool_status.py` (the docs' tool table, `llms.txt`,
the README), each with the status "draft only" and the "(experimental)" label, and each saying that it was not
tested on a customer's Qlik installation. That is what may be said. The rest of this section stands: no page says
that Krusgraph migrates an app, no share is stated, and "compared" is the word, not "reconciled".

## Sources

Verified, opened on learn.microsoft.com on 15 November 2026:

- Power BI migration overview and its stage pages (`/power-bi/guidance/powerbi-migration-overview` and following;
  updated between January and September 2026): written for "a third-party BI tool"; Qlik is not named; "It isn't
  possible to completely automate a Power BI conversion process end-to-end"; the validation stage asks that a
  difference can be explained.
- Microsoft Fabric migration overview (`/fabric/fundamentals/migration`, updated 29 September 2026): no entry for
  Qlik.
- The pages W10 and W11 cite for relationships, Direct Lake and the publishing flow, in their own source lists.

Unverified (not opened; from public knowledge or a search summary): every statement about Qlik's products, its
command line, its APIs, the `.qvf` format and its customer agreement.

Added in Q2 (16 November 2026): the four public repositories of the test corpus, each `LICENSE` file read at the
commit in `tests/fixtures/qlik/SOURCES.md`; and the Microsoft Learn pages listed in `MIGRATE-WORKLOAD-DESIGN.md`.
`help.qlik.com` and `qlik.dev` answered 403 through this session's network policy.
