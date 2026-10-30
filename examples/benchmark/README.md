# Benchmark: relationships and their traps on the same synthetic data (round n61)

Run on **30 October 2026**, Python 3.13.17, SQLite in memory, from the repository's commit at the time. No network, no
Fabric, no Azure: every number below is what `benchmark.py` measured, and `tests/test_benchmark.py` checks that a new
run gives the same table.

```bash
python examples/benchmark/benchmark.py
```

## What is compared

| Method | What it is here |
| --- | --- |
| Krusgraph | `plan()` (the rules behind plan_backend, with the SAP pack), `evidence.validate` (validate_plan: keys, orphans, amount levels) and `graphs.suggest` (suggest_relationships, 15 candidates checked against the rows). Only the plan counts as predicted; suggestions count separately, as decisions for a person. |
| Approximation of documented autodetect rules | Not Power BI. A small implementation of what Microsoft Learn documents for *Autodetect during load* in [Create and manage relationships in Power BI Desktop](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-create-and-manage-relationships): candidate relationships from matching column names, cardinality from the data (many-to-one toward the unique side, one-to-one when both are unique), single-column relationships. Implemented: same column name (case-insensitive), same type family, one side unique in the rows. Nothing else. |
| dbt-style tests | A person declares the right relationships (the facit), then `unique` + `not_null` on each target key and dbt's built-in `relationships` test (one column) for orphans. Precision and recall are 1 by construction; the point is what the tests catch afterwards and how much the person had to declare. |

Datasets (all synthetic): **shop** (`fabric_backend/seed.py`, 7 tables), **sap** (`fabric_backend/sap_demo.py`, 17
SAP-shaped tables), **crm** (Salesforce-shaped objects + an ERP, `fabric_backend/browser_check.py`), **traps**
(`benchmark.py`, 8 invoice tables built for known traps: `code` in two unrelated tables, `name` everywhere, two
roles to `users` whose names do not say users, a total that both lines and payments repeat, two orphans).

`facit.json` lists the right relationships and the planted traps. A prediction is right when source table, column set
and target table match. "Ambiguous columns fallen for" counts facit columns that appear in a wrong predicted
relationship. "Doubled totals" are header amounts that a join with more than one line row per header repeats.

## Result

| Dataset | Method | Precision | Recall | Recall incl. suggestions | Orphans found | Doubled totals found | Ambiguous columns fallen for | Left to the person |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| shop | Krusgraph (plan + validate_plan + suggest_relationships) | 1.0 (6/6) | 0.86 (6/7) | 1.0 | 0/0 | 0/0 | 0/1 | 4 suggestion(s) to accept or reject |
| shop | Approximation of documented autodetect rules | 0.62 (5/8) | 0.71 (5/7) | 0.71 | 0/0 | 0/0 | 1/1 | every created relationship to review (no rule or evidence given) |
| shop | dbt-style tests, relationships declared by a person | 1.0 (7/7) | 1.0 (7/7) | 1.0 | 0/0 | 0/0 | 0/1 | 7 relationships declared by hand |
| sap | Krusgraph (plan + validate_plan + suggest_relationships) | 1.0 (34/34) | 1.0 (34/34) | 1.0 | 1/1 | 4/4 | 0/4 | 0 suggestion(s) to accept or reject |
| sap | Approximation of documented autodetect rules | 0.0 (0/123) | 0.0 (0/34) | 0.0 | 0/1 | 0/4 | 4/4 | every created relationship to review (no rule or evidence given) |
| sap | dbt-style tests, relationships declared by a person | 1.0 (34/34) | 1.0 (34/34) | 1.0 | 0/1 | 0/4 | 0/4 | 34 relationships declared by hand; 34 composite need a package or custom test |
| crm | Krusgraph (plan + validate_plan + suggest_relationships) | 1.0 (4/4) | 0.8 (4/5) | 1.0 | 2/2 | 1/1 | 0/2 | 1 suggestion(s) to accept or reject |
| crm | Approximation of documented autodetect rules | 0.25 (2/8) | 0.4 (2/5) | 0.4 | 0/2 | 0/1 | 2/2 | every created relationship to review (no rule or evidence given) |
| crm | dbt-style tests, relationships declared by a person | 1.0 (5/5) | 1.0 (5/5) | 1.0 | 2/2 | 0/1 | 0/2 | 5 relationships declared by hand |
| traps | Krusgraph (plan + validate_plan + suggest_relationships) | 1.0 (4/4) | 0.5 (4/8) | 0.75 | 2/2 | 2/2 | 0/2 | 2 suggestion(s) to accept or reject |
| traps | Approximation of documented autodetect rules | 0.27 (4/15) | 0.5 (4/8) | 0.5 | 0/2 | 0/2 | 2/2 | every created relationship to review (no rule or evidence given) |
| traps | dbt-style tests, relationships declared by a person | 1.0 (8/8) | 1.0 (8/8) | 1.0 | 2/2 | 0/2 | 0/2 | 8 relationships declared by hand |

## Where Krusgraph is better, equal, and worse

- **Better:** doubled totals are found only by Krusgraph (7 of 7 over the four sets; neither baseline reports them, and
  dbt has no built-in test for it). Same-name columns (`name`, `code`, `Id`, `MANDT`, `VBELN`) produced no wrong
  relationship in Krusgraph's plan, while the autodetect approximation created relationships on every one of them. On
  the SAP set the pack gives the composite keys with MANDT; the approximation found none of the 34.
- **Equal:** orphan rows are found by Krusgraph and by dbt's `relationships` test alike wherever the relationship is
  known and single-column (crm, traps). The data check is ordinary counting; dbt does it as well.
- **Worse:** a person who declares the relationships has recall 1.0; Krusgraph's plan reached 0.5 to 0.86 outside SAP.
  It missed `orders.ship_to_id`, `Account.ERP_Customer_No__c`, `invoices.created_by`/`approved_by` (these four come
  back as suggestions, among wrong ones a person must reject) and `currency_code → currencies.code` and
  `country_code → countries.code`, which it neither planned nor suggested.

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
