# Run {{PRODUCT}} locally

The hosted connector at `{{MCP_URL}}` reads Fabric through your Microsoft sign-in. The same engine also runs on your own
machine as a small MCP server over one ODBC connection: against a SQL Server you reach with Windows sign-in, an Azure
SQL database, or a Fabric SQL analytics endpoint. Nothing leaves your machine except the queries to that database;
there is no account with us and no sign-in with Microsoft. Keys and relationships are inferred the same way, with the
same rules (K0–K5, R0–R4), and the drafts are written to your disk.

Status: the local server is unit-tested against recorded SQL Server metadata (declared keys, several schemas, names
with spaces, `nvarchar(max)`, `datetimeoffset`, `uniqueidentifier`, computed columns, views) and against a Fabric
SQL analytics endpoint in the test suite; it has not yet been run against a live SQL Server by us.

## What you need

- Python 3.10 or later.
- Microsoft ODBC Driver 18 for SQL Server (the local server speaks ODBC).
- A database sign-in that can read metadata and run counting queries. Give it `db_datareader` and nothing more;
  `create_views` is the only tool that writes, and it is a dry run until you say otherwise.

## Install

```
pip install "fabric-backend[mcp] @ git+https://github.com/Krusmaster/fabric-backend"
```

This installs `fabric-backend-mcp` (the local MCP server) and `fabric-backend` (the command line).

## Claude Desktop

Add the server to Claude Desktop's configuration (Settings → Developer → Edit config), with your own server and
database. Windows sign-in needs no password in the string:

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

If Windows cannot find `fabric-backend-mcp`, use the full path of the executable in your Python `Scripts` folder.
`TrustServerCertificate=yes` accepts the server's own certificate; drop it when the server has one your machine trusts.
For a Fabric endpoint instead, use `Server=<sql analytics endpoint host>;Database=<lakehouse>;Authentication=ActiveDirectoryInteractive`
and `FABRIC_SOURCE_KIND=Lakehouse` (or `Warehouse`, `SQLDatabase`).

Restart Claude Desktop and ask, for example, *"Plan the tables in schema dbo"* or *"Check the plan against the data"*.

## What works locally

`list_tables`, `plan_backend`, `validate_plan`, `sample_rows`, `join_path`, `data_dictionary`, `dbt_schema`,
`analyze_schema`, `suggest_relationships`, `rayfin_connector` and `create_views` (dry run by default; `CREATE OR ALTER
VIEW` in a schema of its own, never DROP). On SQL Server, declared primary and foreign keys are read and become K0 and
R0; relationships into another schema are left out rather than guessed.

Two drafts are Fabric-specific and answer with an explanation when `FABRIC_SOURCE_KIND` is `SQLServer`: the Power BI
semantic model in Direct Lake mode (it needs a Fabric SQL analytics endpoint; open the tables in Power BI Desktop
instead, or mirror the database into Fabric) and the Fabric IQ ontology. The tools that need Fabric item ids
(`create_backend`, `describe_backend`, `plan_drift`, `app_starter`, `app_readiness`, `create_semantic_model`,
`create_data_agent`, `lineage`) live in the hosted connector only.

## Without any connection: the CSV path

Export the columns once (`INFORMATION_SCHEMA.COLUMNS` of one schema as CSV, with the columns `table_schema`,
`table_name`, `column_name`, `data_type`, `ordinal_position`) and run the command line on the file:

```
fabric-backend plan columns.csv --schema dbo --mermaid er.mmd
fabric-backend dictionary columns.csv --schema dbo --out dictionary.md
fabric-backend dbt columns.csv --schema dbo --out schema.yml
fabric-backend analyze columns.csv --schema dbo
fabric-backend views columns.csv --schema dbo
```

The plan, the diagram, the data dictionary, the dbt sources file and the view SQL come from the names alone, with the
rule per key and relationship; the counting checks need a connection.

## Source

Open source under the MIT licence: https://github.com/Krusmaster/fabric-backend. The hosted connector and its
docs: [/docs](/docs).
