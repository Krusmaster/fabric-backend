# Benchmark: relationships and their traps on the same synthetic data (rounds n61, n62, n72 and n78)

First run on **30 October 2026** (round n61); run again the same day after round n62 added rule R5, Python 3.13.17,
SQLite in memory, from the repository's commit at the time. Round n72 (1 November 2026, Python 3.13.18) added the fifth
set, **younium**; the four rows from before are unchanged by it. Round n78 (2 November 2026, Python 3.13.18) ran it
again after the engine began to read the `younium_salesforce` pack: the Krusgraph row of younium changed, every other
row is the same as before (`tests/test_younium_pack.py` also compares the plans of shop, sap, crm and traps with the
plans the SAP-only engine made). No network, no
Fabric, no Azure: every number below is what `benchmark.py` measured, and `tests/test_benchmark.py` checks that a new
run gives the same table.

```bash
python examples/benchmark/benchmark.py
```

## What is compared

| Method | What it is here |
| --- | --- |
| Krusgraph | `plan()` with the rows (the rules behind plan_backend, with the knowledge packs (SAP; Younium + Salesforce since round n78), plus R5, which counts code and role columns in the rows; since round n71 the hosted plan_backend runs R5 too, bounded to the first 200 distinct values of a column and 20 counting queries per call, while `/check` still calls `plan()` without rows), `evidence.validate` (validate_plan: keys, orphans, amount levels) and `graphs.suggest` (suggest_relationships, 15 candidates checked against the rows). Only the plan counts as predicted; suggestions and R5 proposals (`plan.proposed`) count separately, as decisions for a person. |
| Approximation of documented autodetect rules | Not Power BI. A small implementation of what Microsoft Learn documents for *Autodetect during load* in [Create and manage relationships in Power BI Desktop](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-create-and-manage-relationships): candidate relationships from matching column names, cardinality from the data (many-to-one toward the unique side, one-to-one when both are unique), single-column relationships. Implemented: same column name (case-insensitive), same type family, one side unique in the rows. Nothing else. |
| dbt-style tests | A person declares the right relationships (the facit), then `unique` + `not_null` on each target key and dbt's built-in `relationships` test (one column) for orphans. Precision and recall are 1 by construction; the point is what the tests catch afterwards and how much the person had to declare. |

Datasets (all synthetic): **shop** (`fabric_backend/seed.py`, 7 tables), **sap** (`fabric_backend/sap_demo.py`, 17
SAP-shaped tables), **crm** (Salesforce-shaped objects + an ERP, `fabric_backend/browser_check.py`), **traps**
(`benchmark.py`, 8 invoice tables built for known traps: `code` in two unrelated tables, `name` everywhere, two
roles to `users` whose names do not say users, a total that both lines and payments repeat, two orphans), **younium**
(`fabric_backend/younium_demo.py`, round n72: 10 Younium-shaped and 4 Salesforce-shaped tables with the system prefixes
`younium_` and `sf_`, 58 rows; the facit is the `younium_salesforce` pack's 15 applied relationships plus the three
links by number the invoice lines carry in these rows; planted: a Younium account whose Salesforce id has 15
characters against 18-character `sf_account.Id`, an invoice total over three lines, and the opportunity amount over
its line items).

`facit.json` lists the right relationships and the planted traps. A prediction is right when source table, column set
and target table match. "Ambiguous columns fallen for" counts facit columns that appear in a wrong predicted
relationship. "Doubled totals" are header amounts that a join with more than one line row per header repeats.

## Result

After round n62 (rule R5). The Krusgraph rows before it, as measured in round n61, are under the table; the two
baselines did not change.

| Dataset | Method | Precision | Recall | Recall incl. suggestions | Orphans found | Doubled totals found | Ambiguous columns fallen for | Left to the person |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| shop | Krusgraph (plan + validate_plan + suggest_relationships) | 1.0 (7/7) | 1.0 (7/7) | 1.0 | 0/0 | 0/0 | 0/1 | 0 suggestion(s) to accept or reject |
| shop | Approximation of documented autodetect rules | 0.62 (5/8) | 0.71 (5/7) | 0.71 | 0/0 | 0/0 | 1/1 | every created relationship to review (no rule or evidence given) |
| shop | dbt-style tests, relationships declared by a person | 1.0 (7/7) | 1.0 (7/7) | 1.0 | 0/0 | 0/0 | 0/1 | 7 relationships declared by hand |
| sap | Krusgraph (plan + validate_plan + suggest_relationships) | 1.0 (34/34) | 1.0 (34/34) | 1.0 | 1/1 | 4/4 | 0/4 | 0 suggestion(s) to accept or reject |
| sap | Approximation of documented autodetect rules | 0.0 (0/123) | 0.0 (0/34) | 0.0 | 0/1 | 0/4 | 4/4 | every created relationship to review (no rule or evidence given) |
| sap | dbt-style tests, relationships declared by a person | 1.0 (34/34) | 1.0 (34/34) | 1.0 | 0/1 | 0/4 | 0/4 | 34 relationships declared by hand; 34 composite need a package or custom test |
| crm | Krusgraph (plan + validate_plan + suggest_relationships) | 1.0 (5/5) | 1.0 (5/5) | 1.0 | 2/2 | 1/1 | 0/2 | 0 suggestion(s) to accept or reject |
| crm | Approximation of documented autodetect rules | 0.25 (2/8) | 0.4 (2/5) | 0.4 | 0/2 | 0/1 | 2/2 | every created relationship to review (no rule or evidence given) |
| crm | dbt-style tests, relationships declared by a person | 1.0 (5/5) | 1.0 (5/5) | 1.0 | 2/2 | 0/1 | 0/2 | 5 relationships declared by hand |
| traps | Krusgraph (plan + validate_plan + suggest_relationships) | 1.0 (8/8) | 1.0 (8/8) | 1.0 | 2/2 | 2/2 | 0/2 | 0 suggestion(s) to accept or reject |
| traps | Approximation of documented autodetect rules | 0.27 (4/15) | 0.5 (4/8) | 0.5 | 0/2 | 0/2 | 2/2 | every created relationship to review (no rule or evidence given) |
| traps | dbt-style tests, relationships declared by a person | 1.0 (8/8) | 1.0 (8/8) | 1.0 | 2/2 | 0/2 | 0/2 | 8 relationships declared by hand |
| younium | Krusgraph (plan + validate_plan + suggest_relationships) | 1.0 (15/15) | 0.83 (15/18) | 1.0 | 1/1 | 2/2 | 0/3 | 50 suggestion(s) to accept or reject |
| younium | Approximation of documented autodetect rules | 0.02 (3/121) | 0.17 (3/18) | 0.17 | 0/1 | 0/2 | 3/3 | every created relationship to review (no rule or evidence given) |
| younium | dbt-style tests, relationships declared by a person | 1.0 (18/18) | 1.0 (18/18) | 1.0 | 1/1 | 0/2 | 0/3 | 18 relationships declared by hand |

Krusgraph before R5 (round n61, plan by names only):

| Dataset | Method | Precision | Recall | Recall incl. suggestions | Orphans found | Doubled totals found | Ambiguous columns fallen for | Left to the person |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| shop | Krusgraph (plan + validate_plan + suggest_relationships) | 1.0 (6/6) | 0.86 (6/7) | 1.0 | 0/0 | 0/0 | 0/1 | 4 suggestion(s) to accept or reject |
| sap | Krusgraph (plan + validate_plan + suggest_relationships) | 1.0 (34/34) | 1.0 (34/34) | 1.0 | 1/1 | 4/4 | 0/4 | 0 suggestion(s) to accept or reject |
| crm | Krusgraph (plan + validate_plan + suggest_relationships) | 1.0 (4/4) | 0.8 (4/5) | 1.0 | 2/2 | 1/1 | 0/2 | 1 suggestion(s) to accept or reject |
| traps | Krusgraph (plan + validate_plan + suggest_relationships) | 1.0 (4/4) | 0.5 (4/8) | 0.75 | 2/2 | 2/2 | 0/2 | 2 suggestion(s) to accept or reject |

**The younium row (rounds n72 and n78).** Since round n78 the engine reads the `younium_salesforce` pack: `infer._pack`
calls `sap_pack.match_any`, which takes the pack that recognises most of a schema's tables. On this set that is the
Younium + Salesforce pack (14 of 14 tables), so the plan has the pack's keys and its 15 applied relationships, with the
rule `SAP pack` (one rule for every pack) and the pack's name and source on each note: precision 1.0 (15/15), recall
0.83 (15/18; the three links by number the invoice lines carry are listed in the pack as unverified and not applied),
1.0 with suggestions, the same as the n72 measurement through `sap_pack.plan_with`. With the relationships in the plan,
`validate_plan` shows the three planted traps: the 15-character Salesforce id is the one orphan of
`younium_accounts.external_crm_id -> sf_account` (1 of 4 rows point at nothing; the reason, 15 against 18 characters,
is the pack's trap in `plan.pack`, not something the count says), and *the total that doubles* finds the invoice total
over its three lines (`younium_invoices` with `younium_invoice_lines`) and the opportunity amount over its line items
(`sf_opportunity` with `sf_opportunitylineitem`). It also reports `younium_charges.list_price` repeated over
`younium_subscription_charges`, which the facit does not count: a list price is a price, and summing it over that join
is wrong too. The 50 suggestions from the rows are counted the same way as before. Before round n78, when the engine
read the SAP pack alone, the row was the name rules: no relationship planned, recall 0.0 (0/18), 0.94 with
suggestions, orphans 0/1, doubled totals 0/2, 50 suggestions. The pack itself was written from sources the writing
session could not open and the demo rows from the pack (`docs/YOUNIUM-SALESFORCE.md`), so the row shows what a pack
adds on such a schema, not that the pack is right about Younium.

## Where Krusgraph is better, equal, and worse

- **Better:** doubled totals are found only by Krusgraph (7 of 7 over the four sets, and 2 of 2 on younium since the engine
  reads its pack in round n78; neither baseline reports them, and
  dbt has no built-in test for it). Same-name columns (`name`, `code`, `Id`, `MANDT`, `VBELN`) produced no wrong
  relationship in Krusgraph's plan, while the autodetect approximation created relationships on every one of them. On
  the SAP set the pack gives the composite keys with MANDT; the approximation found none of the 34.
- **Equal:** orphan rows are found by Krusgraph and by dbt's `relationships` test alike wherever the relationship is
  known and single-column (crm, traps). The data check is ordinary counting; dbt does it as well.
- **Equal, since R5:** with the rows, Krusgraph's plan reaches the recall of a person who declares the relationships
  (1.0 on all four sets) at precision 1.0. Before R5 it reached 0.5 to 0.86 outside SAP and missed `orders.ship_to_id`,
  `Account.ERP_Customer_No__c`, `invoices.created_by`/`approved_by` and `currency_code → currencies.code` and
  `country_code → countries.code`; R5 now plans all six because their values are all in the target's key.
- **Worse, or not shown here:** R5 was written after round n61 named exactly these six misses, by the same project,
  on these same sets: the 1.0 says the rule fixes what it was written for, not how it does on other data. R5 needs
  the rows; `/check` plans by names alone and still misses the six, and plan_backend's bounded R5 (round n71) sees only the first 200 distinct values of a column. On real data with small integer keys a role name can
  fit two tables, and then R5 proposes instead of planning (`tests/test_infer_r5.py`).

## Conditions and limitations

- **Tiny synthetic tables.** Several SAP tables have one or two rows, so every column in them is "unique" and the
  autodetect approximation links them on almost any shared name (123 relationships, none right). On real tables that
  number would be lower; the SAP row for the approximation says more about tiny tables than about the rule.
- **The approximation is not Power BI.** Power BI Desktop's actual heuristics are not all documented (the page says it
  creates a relationship only when it can determine a match with high confidence). Microsoft Learn could not be fetched
  from the session that built this (network policy); the rules were implemented from the page as published and should
  be re-read against it before this is quoted. Inactive relationships and filter direction are not modelled.
- **The SAP facit is the pack's own knowledge.** It follows the public SAP table relationships, which is what the SAP
  pack encodes, and `sap_demo.py` rows were written from the pack. The SAP row shows the pack applied, not that the pack
  is right about SAP.
- **The other facits were written by the same project.** shop, crm and traps were written from the table meanings by
  the author of this benchmark, who also knows Krusgraph's rules. The traps set was built to contain traps, not to be
  typical.
- **dbt is approximated, not run.** The tests are the SQL that dbt's generic tests compile to; composite relationships
  (all 34 in SAP) would need dbt_utils or a custom test, so they count as not tested. Packages such as dbt_utils or
  dbt-expectations could add more checks than counted here.
- **Not measured:** time, cost, how long a person takes to declare or review, large or messy schemas.
