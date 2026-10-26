# Run Krusgraph locally on Windows against SQL Server

The local MCP server `fabric-backend-mcp` runs the same engine as the hosted connector over one ODBC connection: an
on-prem SQL Server reached with Windows sign-in, an Azure SQL database, or a Fabric SQL analytics endpoint. Nothing
leaves the machine except the queries to that database; there is no account with us and no Microsoft sign-in to
krusgraph.com. The web page version of this guide is https://krusgraph.com/local.

Status (26 October 2026): unit-tested against recorded SQL Server metadata (`tests/test_sqlserver.py`: declared
primary and foreign keys in two schemas with shared constraint names, a table with a space in its name and a composite
key, `nvarchar(max)`, `datetimeoffset`, `uniqueidentifier`, `decimal`, a computed column, a view) and against the shop
schema in SQLite; not yet run against a live SQL Server by us. The first user who does is asked to report what
differed.

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
VIEW` in a schema of its own, never DROP; `CREATE OR ALTER` needs SQL Server 2016 SP1 or later).

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
`lineage`) exist in the hosted connector only.

## 5. The CSV path: no connection at all

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

## 6. When something fails

- `kind: server_config` with "FABRIC_ODBC is not set": the `env` block did not reach the server; check the JSON.
- `kind: sql_sign_in`: the Windows account or SQL login was refused; the message never repeats the connection string.
- `kind: server_config` with "SQL driver is not installed": `pyodbc` or Driver 18 is missing (`pip install pyodbc`
  after the driver).
- `kind: schema_not_found`: the schema has no tables for this sign-in; `db_datareader` must cover it.
- A certificate error at connect: add `TrustServerCertificate=yes` for a test, then fix the certificate.
