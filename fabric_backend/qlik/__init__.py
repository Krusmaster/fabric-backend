"""Qlik Sense to Power BI on Fabric, the first part (round Q1, docs/QLIK-MIGRATION-PRODUCT.md).

Two steps, both by fixed rules, with no AI model and no connection to Qlik:

- `read_script(text)` (script.py): a load script as tables for a lakehouse. It takes the tables, fields, associations,
  synthetic keys and circular references from W7's reader (`migration_read.read_qvs`, not changed) and adds what a
  plan needs: a column name per field that a Delta table accepts, where each field comes from (the source column, a
  renamed one, an expression, a join, a mapping table through ApplyMap), which fields QUALIFY took out of the
  associations, and per table whether it is a copy of its source or shaped in the script.
- `map_associations(read, execute=None)` (model.py): Qlik's associations as keys and relationships. Qlik links two
  tables on every field name they share; a relationship in a Power BI model has one column per side and a unique
  one side. So each association gets a one side (from counts in the rows, or from Krusgraph's name rules when
  nothing is counted), and each synthetic key is put in one of the cases of docs/MIGRATION-PLATFORMS-DESIGN.md B.3
  with the counts that decided it. `to_plan` gives the result as Krusgraph's `infer.Plan`, which the engine's own
  steps read (validate, the semantic model draft, the gold views).

Tested on a synthetic load script and synthetic rows only (tests/test_q1_qlik.py, tests/fixtures/q1/). It has not read
a script from a Qlik installation. help.qlik.com and qlik.dev could not be opened from the session that wrote this
(15 November 2026), so every rule about Qlik is **Unverified**: written from public knowledge of Qlik's documentation
and to be read on the page before anything public rests on it. Qlik is a trademark of its owner; Krusgraph is not
affiliated with it.

Q2 (16 November 2026) added the chart expressions (expr.py), the measure drafts (measures.py), the reconciliation
SQL (reconcile.py), the star schema proposal and the statement count (star.py), and three tools that call them
(fabric_backend/qlik_tools.py). The reader was run on public load scripts (tests/fixtures/qlik/SOURCES.md); it has still
not read a script from a customer's Qlik installation, and the workload does not call it.
"""
from .model import map_associations, to_plan
from .script import column_name, listing, read_script
from .star import star_schema, statement_coverage

__all__ = ["read_script", "map_associations", "to_plan", "listing", "column_name", "star_schema", "statement_coverage"]
