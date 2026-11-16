# Snowflake or Azure Databricks to Microsoft Fabric with Krusgraph (MG1)

Round MG1, 16 November 2026, written by a scheduled Claude session with no live user, from the founder's question of
the same day: "När ska vi implementera databricks och snowflake migreringen? Vi kan implementera det också." It builds
the first slice of the design in [MIGRATION-PLATFORMS-DESIGN.md](MIGRATION-PLATFORMS-DESIGN.md) (W10): the inventory
from the source's own metadata, a plan per object, and the before-and-after counts. Qlik is out of scope here; it has
its own track ([QLIK-MIGRATION-PRODUCT.md](QLIK-MIGRATION-PRODUCT.md)).

The idea: a customer who moves from Snowflake or Azure Databricks to Fabric should get a checked model and a plan, not
only copied tables. The source already ships much of the model as metadata (layer 2 of the integration strategy):
declared PRIMARY KEY, UNIQUE and FOREIGN KEY constraints that neither platform enforces, table and column comments,
view definitions. Krusgraph reads them, treats them as candidates, and counts them in the rows on both sides.

Code: `fabric_backend/migrate/` (`metadata.py`, `plan.py`, `sqlrules.py`, `compare.py`, `demo.py`). CLI:
`fabric-backend migrate`. Local MCP tool: `plan_migration`. Tests: `tests/test_mg1_migrate.py` on synthetic exports
(`tests/fixtures/mg1/`).

Rules for this text and the code: no AI inside Krusgraph (every step is a rule, a lookup or a count); nothing about
speed or cost of either platform; Snowflake, Databricks and Fabric are product names only, and Krusgraph is not
affiliated with any of them.

---

## 1. The flow

| Step | Who | What |
|---|---|---|
| 1. Export the metadata | The customer, in Snowflake or Databricks | Runs the queries in section 2 and saves each result as a CSV file in one folder. No credentials reach Krusgraph |
| 2. Plan | Krusgraph, locally | `fabric-backend migrate <folder> --source snowflake\|databricks` or the `plan_migration` tool: per object the Fabric target, how it lands, the column types that do not carry, each view's SQL against Fabric T-SQL; the declared keys and links as candidates in a Krusgraph plan |
| 3. Land | The customer, in Fabric | Mirroring, a Copy job or a rebuild, as the plan says. Krusgraph creates nothing |
| 4. Count before | The customer, in the source | Runs `before_<source>.sql` (written by `--counting-sql DIR`) and saves the result, two columns `metric,value` |
| 5. Count after and compare | Krusgraph | Runs `after_fabric.sql` on the Fabric side (the local server over `FABRIC_ODBC`, read-only) or reads its saved result; validate_plan's checks prove keys, links and amounts there; the report puts both sides next to each other |

## 2. The export queries the customer runs

Each result goes into one folder as `<name>.csv` with a header row (or all of them into one JSON file
`{"tables": [...], "columns": [...], ...}`). Column names are read without case and without quotes. Replace `SHOP`
/ `shop` with the database or catalog and `SALES` / `sales` with the schema.

### 2.1 Snowflake

Snowflake's documentation could not be opened from this session (`docs.snowflake.com` is outside its network), so the
view and column names below are **Unverified**: they are the ones we know, and the reader accepts the usual
variations. Read them against Snowflake's pages before the first customer run.

```sql
-- tables.csv
SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE, IS_TRANSIENT, IS_ICEBERG, IS_DYNAMIC, ROW_COUNT, COMMENT
FROM SHOP.INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'SALES';

-- columns.csv
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, ORDINAL_POSITION, DATA_TYPE, IS_NULLABLE, COMMENT
FROM SHOP.INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'SALES';

-- views.csv
SELECT TABLE_SCHEMA, TABLE_NAME, VIEW_DEFINITION
FROM SHOP.INFORMATION_SCHEMA.VIEWS WHERE TABLE_SCHEMA = 'SALES';

-- functions.csv (user-defined functions: a view that calls one is "manual")
SELECT FUNCTION_SCHEMA, FUNCTION_NAME FROM SHOP.INFORMATION_SCHEMA.FUNCTIONS WHERE FUNCTION_SCHEMA = 'SALES';

-- primary_keys.csv, unique_keys.csv, imported_keys.csv: INFORMATION_SCHEMA has no KEY_COLUMN_USAGE,
-- so the column lists come from SHOW ... KEYS, each saved with RESULT_SCAN
SHOW PRIMARY KEYS IN SCHEMA SHOP.SALES;   SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
SHOW UNIQUE KEYS IN SCHEMA SHOP.SALES;    SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
SHOW IMPORTED KEYS IN SCHEMA SHOP.SALES;  SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
```

### 2.2 Azure Databricks (Unity Catalog)

The information schema and its views (TABLES, COLUMNS, VIEWS, TABLE_CONSTRAINTS, KEY_COLUMN_USAGE,
REFERENTIAL_CONSTRAINTS, ROUTINES, ROW_FILTERS, COLUMN_MASKS) are listed on
https://learn.microsoft.com/en-us/azure/databricks/sql/language-manual/sql-ref-information-schema (ms.date 11
September 2026, read 16 November 2026), which also says it shows only what the reader has privileges on and needs no
explicit `SELECT` grant. The column names of each view were not opened one by one.

```sql
-- tables.csv
SELECT table_schema, table_name, table_type, data_source_format, comment
FROM shop.information_schema.tables WHERE table_schema = 'sales';

-- columns.csv
SELECT table_schema, table_name, column_name, ordinal_position, data_type, full_data_type, is_nullable, comment
FROM shop.information_schema.columns WHERE table_schema = 'sales';

-- views.csv
SELECT table_schema, table_name, view_definition FROM shop.information_schema.views WHERE table_schema = 'sales';

-- routines.csv
SELECT routine_schema, routine_name FROM shop.information_schema.routines WHERE routine_schema = 'sales';

-- constraints.csv: one row per key column; a foreign key with the column it references
SELECT tc.table_schema, tc.table_name, tc.constraint_name, tc.constraint_type, kcu.column_name, kcu.ordinal_position,
       rk.table_schema AS ref_schema, rk.table_name AS ref_table, rk.column_name AS ref_column
FROM shop.information_schema.table_constraints tc
JOIN shop.information_schema.key_column_usage kcu
  ON kcu.constraint_catalog = tc.constraint_catalog AND kcu.constraint_schema = tc.constraint_schema
 AND kcu.constraint_name = tc.constraint_name
LEFT JOIN shop.information_schema.referential_constraints rc
  ON rc.constraint_catalog = tc.constraint_catalog AND rc.constraint_schema = tc.constraint_schema
 AND rc.constraint_name = tc.constraint_name
LEFT JOIN shop.information_schema.key_column_usage rk
  ON rk.constraint_catalog = rc.unique_constraint_catalog AND rk.constraint_schema = rc.unique_constraint_schema
 AND rk.constraint_name = rc.unique_constraint_name AND rk.ordinal_position = kcu.position_in_unique_constraint
WHERE tc.table_schema = 'sales';

-- row_filters.csv and column_masks.csv (tables mirroring does not take)
SELECT table_schema, table_name FROM shop.information_schema.row_filters WHERE table_schema = 'sales';
SELECT table_schema, table_name, column_name FROM shop.information_schema.column_masks WHERE table_schema = 'sales';
```

## 3. What Krusgraph does with them

**The model.** A declared PRIMARY KEY (or, without one, the first UNIQUE) becomes the table's key, and a FOREIGN KEY a
link, with the rule `Snowflake metadata` or `Databricks metadata` and the provenance `declared by metadata (Snowflake)`
or `declared by metadata (Databricks)`, the same pattern as the SAP CSN reader ([SAP-CSN.md](SAP-CSN.md)). They are
candidates: Azure Databricks says primary key, foreign key and unique constraints "are informational only and aren't
enforced" (https://learn.microsoft.com/en-us/azure/databricks/tables/constraints, ms.date 6 November 2026, read 16
November 2026); that Snowflake does not enforce them on standard tables is Unverified here. A foreign key whose
referenced columns are not the target's declared key is not applied and is listed with why; keys the caller passes
win. Tables without declarations get Krusgraph's name rules as before. Comments are carried into the report.

**The plan per object.** Every rule is a lookup on the pages below, each opened on 16 November 2026:

| Page | Its date | What it says that the plan uses |
|---|---|---|
| [Mirroring Snowflake](https://learn.microsoft.com/en-us/fabric/mirroring/snowflake) | 2025-09-16, updated 2026-10-23 | Managed and Iceberg tables: yes; views and materialized views: yes, "Supported with syncs every 12 hours"; external, transient, temporary and dynamic tables: no. The Snowflake user needs `CREATE STREAM`, `SELECT`, `SHOW` and `DESCRIBE` on tables |
| [Snowflake mirroring limitations](https://learn.microsoft.com/en-us/fabric/mirroring/snowflake-limitations) | 2026-02-26, updated 2026-10-23 | At most 1,000 tables; "Mirror all data" takes the first 1,000 by schema and table name; a DDL change triggers a reseed; Snowflake RLS and CLS policies are not replicated |
| [Mirroring Azure Databricks](https://learn.microsoft.com/en-us/fabric/mirroring/azure-databricks) | 2026-10-24, updated 2026-10-28 | "there is no data movement or data replication": the catalog structure is mirrored and data read through shortcuts; "Views and metric views don't appear"; external tables that are not Delta are not displayed |
| [Azure Databricks mirroring limitations](https://learn.microsoft.com/en-us/fabric/mirroring/azure-databricks-limitations) | 2025-12-19, updated 2026-10-28 | Not supported: tables with RLS/CLM policies, Lakehouse federated tables, Delta sharing tables, views |
| [Copy job connectors](https://learn.microsoft.com/en-us/fabric/data-factory/copy-job-connectors) | 2026-11-09 | Snowflake: source and destination, full load, watermark incremental, and a CDC source. Azure Databricks: source and destination, full load, watermark incremental; not in the CDC table |
| [Lakehouse or Warehouse](https://learn.microsoft.com/en-us/fabric/fundamentals/decision-guide-lakehouse-warehouse) | 2026-09-14 | Spark: Lakehouse; T-SQL: Warehouse; multi-table transactions: Warehouse; structured and unstructured data, or not sure: Lakehouse |
| [Data types](https://learn.microsoft.com/en-us/fabric/data-warehouse/data-types) | 2026-06-11 | Warehouse tables: json as varchar, no datetimeoffset ("Use datetime2"), geography as a pair, varbinary or text; on the SQL analytics endpoint a Delta type not in the mapping table is not represented as a column |
| [T-SQL surface area](https://learn.microsoft.com/en-us/fabric/data-warehouse/tsql-surface-area) | 2026-09-16 | QUALIFY, GROUP BY ALL and MERGE (Warehouse) are supported; recursive queries are not |

So, per object:

- **Snowflake managed table**: Mirroring, Copy job as the alternative. **Transient, temporary, dynamic or external**:
  Copy job. **Iceberg**: mirroring through a storage connection. **Beyond the first 1,000 mirrorable tables**: flagged.
- **Databricks Delta table, materialized view, streaming table**: mirroring for the parallel run (the data stays in
  Databricks storage), then a Copy job to own it in Fabric. **Non-Delta external**, **row filter or column mask**: Copy
  job, and the security is a manual design task. **Federated (FOREIGN)**: manual, from the system it federates.
- **Views of both**: rebuilt as Fabric views from the translated SQL; a Snowflake view's rows can be mirrored meanwhile.
- **Target**: a table with a semi-structured column (VARIANT, OBJECT, ARRAY, MAP, STRUCT) goes to a Lakehouse (rule
  T1); otherwise the caller's choice, Lakehouse by default (T2; `--target warehouse` for T-SQL development or
  multi-table transactions).
- **Columns that do not land plainly**: semi-structured types, time zone timestamps (TIMESTAMP_TZ, TIMESTAMP_LTZ),
  Databricks TIMESTAMP_NTZ (not in the endpoint's mapping table), GEOGRAPHY and GEOMETRY, INTERVAL.

**View SQL.** `sqlrules.py` finds the constructs in each view and gives one of three statuses, with the line:

| Status | What |
|---|---|
| translated by rule | `IFF` and Databricks `if` to `IIF`; `NVL`, `IFNULL` to `COALESCE`; `ZEROIFNULL(x)`; `x::type` and `f(x)::type` to `CAST`; `col:a.b` to `JSON_VALUE(col, '$.a.b')` (with a cast when one follows); `LISTAGG` to `STRING_AGG`; one-argument `TO_DATE`; `CURRENT_TIMESTAMP()`; Databricks `date_add(d, n)`; backticks to brackets; a final `LIMIT n` to `TOP n`; `CREATE [OR REPLACE] VIEW` to `CREATE OR ALTER VIEW` |
| supported in Fabric | `QUALIFY`, `GROUP BY ALL`, `MERGE` (Warehouse), from the T-SQL surface area page |
| manual | `FLATTEN`, `LATERAL VIEW` / `explode`, semi-structured construction and parsing, array aggregation, time travel (`AT`, `BEFORE`, `VERSION AS OF`, `TIMESTAMP AS OF`), recursive queries, sequences, `MATCH_RECOGNIZE`, `PIVOT`, `ILIKE` / `RLIKE` / regular expressions, `NVL2` / `DECODE`, sampling, stages, lambdas, a call to a user-defined function from the export, a path with an index, and any source function or `::` a rule could not rewrite (its argument too complex) |

A view gets a T-SQL draft only when nothing in it is manual; anything a rule did not rewrite makes it manual rather
than passing through. String literals and comments are never rewritten. A draft is still a draft: run it and compare.

**After landing.** One counting query per side, built from the plan: per table the rows, the key's distinct values and
NULLs, the totals of number columns that are neither key nor link; per link the orphans. On the Fabric side
validate_plan's existing checks run on the same plan (keys unique, links without orphans, header amounts repeated by
a join). Then the two sides next to each other.

## 4. Measured on the synthetic sample

`python -m fabric_backend.migrate.demo` runs it all on the synthetic Snowflake export in `tests/fixtures/mg1/snowflake/`
with made-up rows in two SQLite databases standing in for Snowflake and the Fabric SQL analytics endpoint (planted: a
duplicate customer under a declared key, an order for a customer that does not exist, a line of an order that does not
exist, one line lost in landing, and the transient EVENTS table not landed). Measured 16 November 2026:

- 4 declared keys and 3 declared links became candidates with the rule `Snowflake metadata`.
- Landing: CUSTOMERS, ORDERS, ORDER_LINES and PRODUCTS by mirroring; EVENTS by a Copy job (transient: mirroring does
  not take it); the four views rebuilt. Views: V_LATEST_ORDER and V_TOP_CUSTOMERS translated by rule; V_ORDER_MARGIN
  manual (user-defined function MARGIN_PCT); V_PRODUCT_ATTRIBUTES manual (FLATTEN).
- Checks on the Fabric side: 3 of 4 keys unique, 1 of 3 relationships hold without orphans (CUSTOMERS' declared key
  has a duplicate on both sides; one orphan order and one orphan line, on both sides: the migration kept them, and the
  checks show they were there before).
- The comparison found 4 differences:
  - events: no count after (the table is not on that side, or the query was not run)
  - order_lines: rows 6 before, 5 after (-1)
  - order_lines.quantity: total 12 before, 11 after (-1)
  - order_lines.line_amount: total 2100 before, 1800 after (-300)

The Databricks fixture (`tests/fixtures/mg1/databricks/`) is planned and its views translated in the tests; no rows
are made up for it.

## 5. What Krusgraph does not do

- It connects to nothing on the source: no Snowflake or Databricks connection, no credentials. The files are the
  customer's exports.
- It creates nothing in Fabric: no mirrored database, Copy job, shortcut, table or view. `plan_migration` refuses
  `dry_run=false`.
- It moves no rows. Mirroring or a Copy job does, set up by a person.
- It translates views only, by the fixed rules above. Stored procedures, tasks, streams, notebooks, jobs, dbt models,
  dashboards and metric views are not translated.
- It applies no security. Snowflake row access and masking policies, Unity Catalog grants, row filters and column
  masks are listed for a person to design in Fabric.
- It does not prove equal values. Equal row counts, key counts, orphan counts and totals are evidence, not a
  row-by-row comparison.
- It has not run against a real Snowflake account, Databricks workspace or Fabric workspace: unit tests on synthetic
  exports and SQLite only, 16 November 2026.

## 6. Open

- Read Snowflake's pages for the export queries and the constraint semantics (network access to `docs.snowflake.com`).
- A first run on a trial account of each source with synthetic data, written up in [LIVE-TEST.md](LIVE-TEST.md).
- The hosted server and the Fabric workload do not offer this yet; it is the local server and the CLI only.
