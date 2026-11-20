# MG1 fixtures: synthetic metadata exports

Everything here is **synthetic**, written by hand for `tests/test_mg1_migrate.py` on 16 November 2026 (round MG1). No
file was exported from a Snowflake account or a Databricks workspace; no name, row or figure comes from a customer.

- `snowflake/`: what the queries in `docs/MIGRATE-DATABRICKS-SNOWFLAKE.md` section 2.1 return for a made-up database
  `SHOP`, schema `SALES` (plus one table in `STAGING`, left out by the reader): `tables.csv`, `columns.csv`,
  `views.csv`, `functions.csv`, and `primary_keys.csv` / `imported_keys.csv` in the column layout of `SHOW PRIMARY KEYS`
  and `SHOW IMPORTED KEYS` as we understand it (Snowflake's pages could not be opened from the session: Unverified).
- `databricks/`: what the queries in section 2.2 return for a made-up Unity Catalog catalog `shop`, schema `sales`:
  `tables.csv`, `columns.csv`, `views.csv`, `constraints.csv` (the documented join of TABLE_CONSTRAINTS,
  KEY_COLUMN_USAGE and REFERENTIAL_CONSTRAINTS), `row_filters.csv`, `routines.csv`.

The rows behind them, for the before/after comparison, are made up in `fabric_backend/migrate/demo.py`.
