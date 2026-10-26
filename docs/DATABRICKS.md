# Krusgraph on Databricks (Draft only)

Round n13 added a Databricks adapter behind the same engine as Fabric (`fabric_backend/platforms/databricks.py`, the
drafts in `fabric_backend/databricks_drafts.py`; the boundary is in [ARCHITECTURE.md](ARCHITECTURE.md)). **Everything
here is Draft only: unit-tested with Databricks mocked at its REST API, never run against a Databricks workspace.** It
runs in the local stdio server only; the hosted server at krusgraph.com and its Microsoft sign-in are unchanged and read
Fabric. Krusgraph is independent and not affiliated with Databricks.

## What it does

The same plan as on Fabric (keys K0–K5, relationships R0–R4, every result with its rule), read from Unity Catalog, and
from that plan the Databricks objects:

1. **Read.** `information_schema` of one catalog: `columns` (with `full_data_type` and `is_nullable`), the informational
   PRIMARY KEY and FOREIGN KEY constraints (`table_constraints`, `key_column_usage`, `referential_constraints`), which
   become K0 and R0 exactly as a Fabric warehouse's declared keys do, and `column_tags`, which feed the personal-data
   rules P1–P6 (a tag such as `class.email_address` or `pii: phone` flags the column under that rule; a tag that only
   says personal data, such as `pii` or `gdpr`, flags it as `tag`). `information_schema` returns only what the
   signed-in principal may see. Lineage comes from `system.access.table_lineage`.
2. **Run SQL.** The SQL Statement Execution API (`POST /api/2.0/sql/statements`, polled with `GET .../{statement_id}`,
   results `INLINE` as `JSON_ARRAY`, further chunks followed) on a SQL warehouse, in Databricks SQL: backticks, `COUNT`,
   `LIMIT`, three-part names. Chosen over `databricks-sql-connector` because it is plain HTTPS like the Fabric side, needs
   no Thrift or Arrow, and every call can be tested with the REST layer mocked. A statement that runs longer than 120
   seconds is cancelled.
3. **Build, as drafts.** Informational constraints, views, a Lakeflow pipeline, metric views and a bundle (below). Two
   creating tools apply the constraints and create the pipeline; both are dry runs by default and never delete.

## Set-up (local stdio server)

```
pip install "fabric-backend[mcp,databricks]"
databricks auth login --host https://<your-workspace>.cloud.databricks.com      # or a profile in ~/.databrickscfg
```

Then add the server to your MCP client with these environment variables:

| Variable | Value |
| --- | --- |
| `KRUSGRAPH_PLATFORM` | `databricks` |
| `DATABRICKS_HOST` | the workspace URL (or leave it to the profile) |
| `DATABRICKS_CONFIG_PROFILE` | a profile name from `~/.databrickscfg`, when not `DEFAULT` |
| `DATABRICKS_WAREHOUSE_ID` | the SQL warehouse's id (SQL Warehouses → the warehouse → Connection details) |
| `DATABRICKS_CATALOG` | the catalog to read, for example `workspace` |

Sign-in is Databricks' own unified client authentication through `databricks-sdk`'s `Config`: a profile made by
`databricks auth login` (OAuth, user to machine), a profile with a token, or OAuth machine to machine
(`DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`). `Config.authenticate()` gives the request headers and refreshes an
OAuth token; nothing is stored by Krusgraph. Tools take the schema without the catalog (`schema="shop"`).

## Every local tool on Databricks

| Tool | Status | On Databricks |
| --- | --- | --- |
| `list_tables` | Draft only | Unity Catalog `information_schema.columns` |
| `plan_backend` | Draft only | inference on names; informational PRIMARY KEY / FOREIGN KEY constraints are K0 / R0 |
| `validate_plan` | Draft only | the counting queries in Databricks SQL on the SQL warehouse |
| `sample_rows` | Draft only | `LIMIT n`; columns flagged by name or by a Unity Catalog column tag are masked |
| `join_path` | Draft only | the chain with Databricks SQL (three-part names, `LIMIT`) |
| `data_dictionary` | Draft only | as on Fabric |
| `dbt_schema` | Draft only | `database` is the catalog, as dbt-databricks reads it |
| `analyze_schema` | Draft only | as on Fabric |
| `suggest_relationships` | Draft only | inclusion counts in Databricks SQL |
| `create_views` | Draft only | `CREATE OR REPLACE VIEW` with the reason as `COMMENT`, in a schema of its own (`CREATE SCHEMA IF NOT EXISTS`); dry run by default |
| `databricks_constraints_draft` | Draft only | `ALTER TABLE … ADD CONSTRAINT … PRIMARY KEY / FOREIGN KEY`, `RELY` only where `validate_plan`'s counts hold |
| `create_databricks_constraints` | Draft only | applies the draft after the counts; dry run by default; only `ADD`, never `DROP` |
| `databricks_pipeline_draft` | Draft only | a Lakeflow pipeline in SQL: silver and gold with expectations, and the quarantine |
| `create_databricks_pipeline` | Draft only | writes the two notebooks and creates or updates the pipeline; dry run by default; starts no run |
| `databricks_metric_view_draft` | Draft only | one metric view per fact table |
| `export_databricks_bundle` | Draft only | a bundle folder: `databricks.yml`, the pipeline, two jobs, the SQL files |
| `databricks_lineage` | Draft only | `system.access.table_lineage` for the schema's tables |
| `create_backend` | Not on Databricks | the API for GraphQL is a Fabric item; mirror the catalog into Fabric (Mirrored Azure Databricks catalog) and use the hosted server |
| `semantic_model_draft` | Not on Databricks | Direct Lake is Fabric's; `databricks_metric_view_draft` is the Databricks semantic layer |
| `silver_notebook_draft` | Not on Databricks | a Fabric notebook; `databricks_pipeline_draft` carries the same rules |
| `ontology_draft`, `rayfin_connector` | Not on Databricks | Fabric IQ and Rayfin read Fabric items |
| `answer_query_draft` | Planned | the drafted query is T-SQL; `join_path` gives the joins in Databricks SQL |

The last six answer `kind: unsupported` with the hint above; of them only `answer_query_draft` is planned for
Databricks, the others build Fabric items. The seven `databricks_*` tools answer
`unsupported` on a Fabric source. Every tool has a title and annotations; the two new creating tools have
`readOnlyHint: false`, `destructiveHint: true` like the Fabric creating tools.

## The drafts and what they rest on

The documentation was read on 26 October 2026. docs.databricks.com could not be opened from the environment this was
written in, so its pages were read through search summaries (close paraphrases, not quotes); databricks-sdk-py,
databricks/cli (the bundle JSON schema), databricks/bundle-examples and dbt-databricks were read as source. Each source
is cited again in `fabric_backend/databricks_drafts.py`.

- **Constraints** ([ALTER TABLE ADD CONSTRAINT](https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-ddl-alter-table-add-constraint),
  [constraints](https://docs.databricks.com/aws/en/tables/constraints), [query optimization with constraints](https://docs.databricks.com/aws/en/sql/user/queries/query-optimization-constraints); GA).
  Databricks does not enforce PRIMARY KEY or FOREIGN KEY. `RELY` lets the optimizer remove a `DISTINCT`, an aggregate or
  a join on the strength of the constraint, and the user answers for it being true, so `RELY` is written only where the
  counts held: a key unique and without NULLs, a reference without orphans to a unique key. A primary key needs NOT NULL
  columns; `ALTER COLUMN … SET NOT NULL` is enforced on existing and future rows, so it is written only with
  `set_not_null=true` and only for columns the counts show without NULLs. There is no `ADD CONSTRAINT IF NOT EXISTS`:
  declared constraints are read first and left out. Rights: ownership of the table (MODIFY for `SET NOT NULL`, SELECT on
  the parent for a foreign key).
- **Lakeflow pipeline** (Lakeflow pipelines, also called Lakeflow Spark Declarative Pipelines, formerly Delta Live
  Tables; [CREATE MATERIALIZED VIEW in pipelines](https://docs.databricks.com/aws/en/ldp/developer/ldp-sql-ref-create-materialized-view),
  [expectations](https://docs.databricks.com/aws/en/ldp/expectations), [expectation patterns](https://docs.databricks.com/aws/en/ldp/expectation-patterns)).
  The same rules and comments as the Fabric silver notebook and gold views: per table, rows numbered within their key
  (the latest by `order_by`, else by a content hash), the key and each reference as an expectation `ON VIOLATION DROP
  ROW`, the clean rows published in the silver schema, and `krusgraph_quarantine` holding each dropped row with its rule
  (personal columns masked); gold, one materialized view per fact table over the safest many-to-one paths with the
  plan's keys and relationships as expectations. An expectation sees one row and cannot contain a subquery, so each
  reference is looked up in a private materialized view first. Two notebooks in Databricks' SQL source format. Never
  over a source table. The SQL ran on SQLite in the tests with the same quarantine, per table and rule, as the Fabric
  notebook on the same dirty seed.
- **Views** ([CREATE VIEW](https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-ddl-create-view)): the
  same wide views as on Fabric, `CREATE OR REPLACE VIEW … COMMENT '…'`. Rights: `CREATE TABLE` on the views' schema.
- **Metric views** ([metric views](https://docs.databricks.com/aws/en/metric-views/create/sql),
  [YAML reference](https://docs.databricks.com/aws/en/business-semantics/metric-views/yaml-reference); generally available
  as part of Unity Catalog Business Semantics per Databricks' announcement of October 2026, some sub-features still in
  preview): `CREATE OR REPLACE VIEW … WITH METRICS LANGUAGE YAML AS $$ … $$`, YAML version 1.1 (Databricks Runtime 17.2,
  current SQL warehouses): the fact table as source, the tables one many-to-one step away as joins, the row count and the
  sums `semantic_model_draft` would suggest as measures. Queried with `MEASURE()`.
- **Bundle** (Declarative Automation Bundles, the name of Databricks Asset Bundles since March 2026;
  [bundles](https://docs.databricks.com/aws/en/dev-tools/bundles/), the bundle schema in
  [databricks/cli](https://github.com/databricks/cli)): `databricks.yml` with `dev` (`mode: development`) and `prod`
  targets, the pipeline (serverless) and two jobs: `<name>_build` (views, a pipeline refresh, metric views) and
  `<name>_constraints`, on its own because it changes the source tables' metadata.
- **Lineage** ([lineage system tables](https://docs.databricks.com/aws/en/admin/system-tables/lineage)): events that read
  or wrote the schema's tables in the last 90 days, with the notebook, job, pipeline, dashboard or query behind each.
  The system catalog's `access` schema must be readable by you (granted by an account or metastore admin).

## Beside Databricks' own MCP servers

Databricks runs [managed MCP servers](https://docs.databricks.com/aws/en/generative-ai/mcp/managed-mcp) in the
workspace (Public Preview): Unity Catalog functions (`/api/2.0/mcp/functions/{catalog}/{schema}`), Genie spaces
(`/api/2.0/mcp/genie/{space_id}`), Vector Search (`/api/2.0/mcp/vector-search/{catalog}/{schema}`) and Databricks SQL
(`/api/2.0/mcp/sql`); custom MCP servers run on Databricks Apps. They answer questions, run SQL and call functions.
Krusgraph does a different part: it works out how the tables relate, with the rule behind every key and relationship,
checks that against the rows, and drafts the constraints, pipeline, views, metric views and bundle from that plan. A
typical pairing: Krusgraph plans a schema and drafts its metric views; once they are created, a Genie space or the
Databricks SQL MCP server answers questions on them. Both can be added to the same MCP client.

## A hosted Databricks sign-in (proposal, not built)

The hosted server signs users in with Microsoft Entra. For Databricks it would need its own OAuth app: an app
connection registered in the Databricks account console (account-level OAuth, user to machine) with the hosted
server's redirect URL, the scopes the tools need (`sql`, `all-apis`; to be confirmed against the app connection page), and the user's workspace host asked for at sign-in, because a
token is issued per workspace. Every call would then run with the user's own Unity Catalog privileges, as the Fabric
side does with on-behalf-of tokens. Nothing of this exists in code; it needs an account admin to register the app.

## Uncertainties

- Not run against a workspace: every request and answer shape comes from Databricks' published API (the SDK's
  generated docstrings) and is mocked in `tests/databricks_support.py`.
- Whether reading `information_schema` needs an explicit SELECT grant: the sources differ. Whether data classification's
  `class.*` tags appear in `information_schema.column_tags`: likely, not confirmed.
- The full column list of `system.access.table_lineage`: `source_table_full_name`, `entity_type` and `entity_id` are
  confirmed; `target_table_full_name`, `event_time` and `event_date` come from secondary sources (the live test runs
  `DESCRIBE` first).
- Free Edition (one serverless SQL warehouse; the catalog `workspace`, per community posts): whether system tables and
  lineage are available there is not confirmed.
- `create_databricks_pipeline` imports the notebooks with `format: SOURCE, language: SQL`, which creates notebooks; the
  folder comes from `GET /api/2.0/preview/scim/v2/Me`. That a bundle deploys `.sql` files that start with
  `-- Databricks notebook source` as notebooks is from the bundle examples, not tested.

The live test for a trial workspace is in [LIVE-TEST.md](LIVE-TEST.md#databricks).
