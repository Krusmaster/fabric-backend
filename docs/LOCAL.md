# Run Krusgraph locally on Windows against SQL Server

The local MCP server `fabric-backend-mcp` runs the same engine as the hosted connector over one ODBC connection: an
on-prem SQL Server reached with Windows sign-in, an Azure SQL database, or a Fabric SQL analytics endpoint. Nothing
leaves the machine except the queries to that database; there is no account with us and no Microsoft sign-in to
krusgraph.com. The web page version of this guide is https://krusgraph.com/local.

Status (28 October 2026): run against SQL Server 2022 in a container (`mcr.microsoft.com/mssql/server:2022-latest`, on
Linux) with Microsoft ODBC Driver 18 and a SQL login that has `db_datareader` only, on the synthetic shop data
(`fabric_backend.seed`) plus the two tables of the amount example (`seed.AMOUNT_DEMO`, schema `demo`): the Python API
below (plan, validate, data dictionary, dbt schema, the check for the total that doubles), the local server's
`plan_backend`, `validate_plan`, `data_dictionary`, `dbt_schema` and `answer_query_draft` (its SQL run on the server gave
1 000, not 2 000), and `fabric-backend demo` with `--odbc` (all four steps and every export). The login was refused a
`CREATE TABLE`, as it should be. Not yet run: a SQL Server on Windows with Windows sign-in (`Trusted_Connection=yes`),
`dbt test` itself on the generated `schema.yml` (the file is generated, dbt was not run), and Claude Desktop starting
the local server. Unit-tested as before against recorded SQL Server metadata (`tests/test_sqlserver.py`). The first
user on a real server is asked to report what differed.

## 1. What you need

| | |
| --- | --- |
| Python | 3.10 or later (`python --version` in PowerShell) |
| ODBC | Microsoft ODBC Driver 18 for SQL Server (the Microsoft download; the driver name in the connection string is `{ODBC Driver 18 for SQL Server}`) |
| A database sign-in | Windows sign-in (`Trusted_Connection=yes`) or a SQL login. Give it `db_datareader` only: every tool reads; `create_views` is the one writer and it is a dry run until you say otherwise, and when you do it needs `CREATE VIEW` and `CREATE SCHEMA` or `ALTER` on the views schema |
| Claude Desktop | or any MCP client that starts a local command (Claude Code: `claude mcp add`) |

## 2. Install

```powershell
pip install "fabric-backend[mcp] @ git+https://github.com/Krusmaster/fabric-backend"
fabric-backend-mcp --help
```

The second line proves the executable is on the PATH; if PowerShell cannot find it, it is in the `Scripts` folder of
your Python installation (`python -c "import sysconfig; print(sysconfig.get_path('scripts'))"`), and you can use that
full path in the configuration below.

## 3. Claude Desktop configuration

Settings → Developer → Edit config opens `claude_desktop_config.json`. Add the server with your own server name and
database:

```json
{
  "mcpServers": {
    "krusgraph-local": {
      "command": "fabric-backend-mcp",
      "env": {
        "FABRIC_ODBC": "Driver={ODBC Driver 18 for SQL Server};Server=sql01;Database=shopdb;Trusted_Connection=yes;TrustServerCertificate=yes",
        "FABRIC_SOURCE_KIND": "SQLServer"
      }
    }
  }
}
```

- `Trusted_Connection=yes` uses your Windows account; no password in the file. For a SQL login use
  `Uid=...;Pwd=...` instead and keep the file private.
- `TrustServerCertificate=yes` accepts the server's own certificate; remove it when the server has a certificate
  your machine trusts (Driver 18 encrypts by default).
- A named instance is `Server=sql01\SQLEXPRESS`; a port is `Server=sql01,1433`. The connection string is parsed with
  braces and quotes as ODBC does, and `Addr`, `Address`, `Network Address` and `Initial Catalog` are accepted synonyms.
- `FABRIC_SOURCE_KIND=SQLServer` tells the drafts what they are drawing from. For a Fabric endpoint instead:
  `Server=<sql analytics endpoint host>;Database=<lakehouse>;Authentication=ActiveDirectoryInteractive` and
  `FABRIC_SOURCE_KIND=Lakehouse` (or `Warehouse`, `SQLDatabase`), plus `FABRIC_SCHEMAS_ENABLED=1` for a lakehouse
  created with schemas.

Restart Claude Desktop. The tools appear under the server's name; ask, for example, *"Plan the tables in schema
dbo"*, *"Check the plan against the data"*, *"How do orders connect to products?"*, *"Write the data dictionary"*.

## 4. What works locally, and what answers with an explanation

Works: `list_tables`, `plan_backend`, `validate_plan`, `sample_rows`, `join_path`, `data_dictionary`, `dbt_schema`,
`analyze_schema`, `suggest_relationships`, `rayfin_connector`, `create_views` (dry run by default; `CREATE OR ALTER
VIEW` in a schema of its own, never DROP; `CREATE OR ALTER` needs SQL Server 2016 SP1 or later), `answer_query_draft` (a
question in Swedish or English as T-SQL over the safest join path; runs nothing) and, with `FABRIC_SOURCE_KIND=Lakehouse`,
`silver_notebook_draft` (the PySpark notebook that builds silver tables, without a default lakehouse since the item ids are
not known locally; attach it in Fabric).

On SQL Server the declared primary and foreign keys are read from `INFORMATION_SCHEMA` and become rules K0 and R0, so
the plan starts from what the database says; name inference fills in the rest. Constraints are matched by schema and
name (two schemas may both have `PK_orders`); a foreign key into another schema is left out rather than guessed.
Views are read like tables (`INFORMATION_SCHEMA.COLUMNS` lists them), computed columns like any column, and
`nvarchar(max)`, `datetimeoffset` and `uniqueidentifier` map to string, dateTime and string in the drafts. Tables with
spaces or other odd characters in their names are bracket-quoted in every query the tools send.

Two drafts are Fabric-specific and, with `FABRIC_SOURCE_KIND=SQLServer`, answer `kind: unsupported` with the reason
and the alternative: `semantic_model_draft` (Direct Lake needs a Fabric SQL analytics endpoint; open the tables in Power
BI Desktop in Import or DirectQuery mode and use the plan's keys and relationships, or mirror the database into Fabric)
and `ontology_draft` (Fabric IQ binds to a Fabric item). The tools that need Fabric item ids (`create_backend`,
`describe_backend`, `plan_drift`, `app_starter`, `app_readiness`, `create_semantic_model`, `create_data_agent`,
`lineage`, `create_silver_notebook`, the drift monitor, and the GraphQL form of `answer_query_draft`) exist in the hosted
connector only.

## 5. The 20-minute demo

`fabric-backend demo --odbc "<the same connection string>" --schema dbo` (or `--folder C:\data\export` for CSV / Excel
files, or no flag to choose on the page) opens one local page on 127.0.0.1 with the map, the health check with Accept
and Skip, five questions run on the data and the exports. The script for running it with a customer is
[DEMO-20-MIN.md](DEMO-20-MIN.md).

## 5b. From your own Python

The same engine without Claude and without the demo page, for a team that writes Python:

```python
from fabric_backend import plan_sql_server

dsn = ("Driver={ODBC Driver 18 for SQL Server};Server=sql01;Database=shopdb;"
       "Trusted_Connection=yes;TrustServerCertificate=yes")

with plan_sql_server(dsn, schema="shop") as local:          # reads INFORMATION_SCHEMA; declared keys are K0/R0
    print(local.plan.summary())
    for r in local.plan.relationships:
        print(f"{r.source}.{'+'.join(r.source_cols)} -> {r.target} ({r.rule})")
    checks = local.validate()                               # counting queries only: keys, orphans, amount_levels
    print(checks["summary"])
    for f in checks["amount_levels"]["findings"]:           # the total that doubles
        print(f["explanation"])
    open("dictionary.md", "w", encoding="utf-8").write(local.data_dictionary(checks))
    open("schema.yml", "w", encoding="utf-8").write(local.dbt_schema())   # dbt sources with unique/not_null/relationships
```

`keys={"order_items": ["order_id", "line_no"]}` and `confirmed=[{"source": ..., "source_cols": [...], "target": ...,
"target_cols": [...]}]` work as in the tools. `local.amount_levels()` runs only the amount check. `local.execute(sql)`
runs your own read-only query over the same connection. Nothing is written and nothing leaves the machine but the
queries to the database.

To try it without a server of your own, a SQL Server in Docker with the synthetic data is what we ran:

```powershell
docker run -d --name mssql -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD=<a strong password> -p 1433:1433 mcr.microsoft.com/mssql/server:2022-latest
```

then create a database, load `fabric_backend.seed.rows()` into a schema `shop` and `seed.AMOUNT_DEMO` into a schema
`demo`, and give a login `db_datareader`. `KRUSGRAPH_SQLSERVER_DSN=<its connection string> pytest
tests/test_sqlserver_api.py` then runs the live test as well.

## 6. The CSV path: no connection at all

Export the columns of one schema once:

```sql
SELECT TABLE_SCHEMA AS table_schema, TABLE_NAME AS table_name, COLUMN_NAME AS column_name,
       DATA_TYPE AS data_type, ORDINAL_POSITION AS ordinal_position
FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' ORDER BY TABLE_NAME, ORDINAL_POSITION
```

Save the result as `columns.csv` (SQL Server Management Studio: right-click the result → Save Results As) and run:

```powershell
fabric-backend plan columns.csv --schema dbo --mermaid er.mmd
fabric-backend dictionary columns.csv --schema dbo --out dictionary.md
fabric-backend dbt columns.csv --schema dbo --database shopdb --out schema.yml
fabric-backend analyze columns.csv --schema dbo
fabric-backend views columns.csv --schema dbo --views-schema krusgraph
```

Keys from names only (no declared keys in a CSV; add a `keys.csv` with `table_name,column_name` rows for composite
keys), the ER diagram, the data dictionary, the dbt sources file and the view script with `GO` between batches. The
counting checks (`validate_plan`, `suggest_relationships`) need the connection.

## 7. When something fails

- `kind: server_config` with "FABRIC_ODBC is not set": the `env` block did not reach the server; check the JSON.
- `kind: sql_sign_in`: the Windows account or SQL login was refused; the message never repeats the connection string.
- `kind: server_config` with "SQL driver is not installed": `pyodbc` or Driver 18 is missing (`pip install pyodbc`
  after the driver).
- `kind: schema_not_found`: the schema has no tables for this sign-in; `db_datareader` must cover it.
- A certificate error at connect: add `TrustServerCertificate=yes` for a test, then fix the certificate.
