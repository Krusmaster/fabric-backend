"""MCP server: let an app-building agent provision its own Fabric backend.

Microsoft's own GraphQL MCP server queries an API that already exists. This one makes the API.
Same functions as the library, over the one SQL connection in FABRIC_ODBC:

  list_tables(schema)                       what is in the lakehouse / warehouse
  plan_backend(schema, ...)                 inferred keys + relationships, Mermaid, nothing deployed
  validate_plan / sample_rows               the plan checked against the rows; a few rows of one table
  create_backend(workspace, source, name)   create/update the GraphQLApi item, return endpoint + checklist
  rayfin_connector(connector, ...)          Rayfin (Fabric Apps) connector entity files from the same plan
  ontology_draft, semantic_model_draft      Fabric IQ ontology draft; Power BI model in TMDL (Direct Lake)
  join_path, data_dictionary, dbt_schema    how two tables connect (with T-SQL); hand-over Markdown; dbt sources
  analyze_schema, suggest_relationships     the plan as a graph; missing links checked against the data
  create_views(dry_run=True)                CREATE OR ALTER VIEW in a schema of its own (SQL, no Fabric REST)

The tools that need Fabric item ids (describe_backend, plan_drift, app_starter, create_semantic_model,
create_data_agent) live in the remote server only. Set FABRIC_SOURCE_KIND (Lakehouse, Warehouse, SQLDatabase) and
FABRIC_SCHEMAS_ENABLED=1 for a lakehouse created with schemas when semantic_model_draft should write schemaName.

Run:  fabric-backend-mcp            (stdio; `pip install fabric-backend[mcp]`)
Auth: a Fabric token via `az login` (FABRIC_TOKEN env var overrides). The SQL side needs an ODBC
connection string in FABRIC_ODBC, e.g.
  Driver={ODBC Driver 18 for SQL Server};Server=<sql endpoint>.datawarehouse.fabric.microsoft.com;
  Database=<lakehouse>;Authentication=ActiveDirectoryInteractive   (or ...ServicePrincipal)
Add it to Lovable as a custom MCP connector, or to Claude Code / Cursor as an MCP server.
"""
from __future__ import annotations

import json
import os

from . import create, plan_from
from .errors import safe
from .infer import check_tables
from .rayfin import rayfin_files
from .ontology import bindings as ontology_bindings, ontology_ttl, summary as ontology_summary
from .deploy import token_from_az
from . import evidence as _evidence, semantic_model as _semantic_model, paths as _paths, dictionary as _dictionary
from . import dbt as _dbt, graphs as _graphs, views as _views

try:
    from mcp.server.mcpserver import MCPServer as _Server          # mcp >= 2
except ImportError:  # pragma: no cover
    try:
        from mcp.server.fastmcp import FastMCP as _Server          # mcp 1.x
    except ImportError as e:
        raise SystemExit("pip install 'fabric-backend[mcp]'") from e

mcp = _Server("fabric-backend")


def _token() -> str:
    return os.environ.get("FABRIC_TOKEN") or token_from_az()


def _execute_factory(schema: str):
    import pyodbc
    conn = pyodbc.connect(os.environ["FABRIC_ODBC"])

    def execute(sql: str):
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def statement(sql: str) -> None:                       # DDL for create_views: no rows, committed
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
    execute.statement = statement
    execute.close = conn.close
    return execute


def _odbc_part(key: str) -> str:
    for part in os.environ.get("FABRIC_ODBC", "").split(";"):
        k, _, v = part.partition("=")
        if k.strip().lower() == key.lower():
            return v.strip()
    return ""


def _source_info(schema: str) -> dict:
    """What the drafts know about the source locally: host and database from the ODBC string, kind and the
    schemas flag from the environment; item ids are unknown here (the remote server has them)."""
    kind = os.environ.get("FABRIC_SOURCE_KIND", "Lakehouse")
    flag = os.environ.get("FABRIC_SCHEMAS_ENABLED", "").lower()
    schemas_enabled = True if kind != "Lakehouse" else (flag in ("1", "true", "yes") if flag else None)
    db = _odbc_part("Database") or "source"
    return dict(workspace_id="", item_id="", item_name=db, item_kind=kind, schema=schema,
                sql_endpoint=_odbc_part("Server"), sql_db=db, schemas_enabled=schemas_enabled)


@mcp.tool()
@safe
def list_tables(schema: str = "dbo") -> str:
    """Tables and columns in the source behind FABRIC_ODBC."""
    p = plan_from(execute=_execute_factory(schema), schema=schema)
    return json.dumps({t.name: t.column_names for t in p.schema}, indent=2)


@mcp.tool()
@safe
def plan_backend(schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                 confirmed: list[dict] | None = None) -> str:
    """Infer keys and relationships without deploying. Returns summary, relationships with the rule
    that produced each, ambiguous columns to confirm, and a Mermaid ER diagram."""
    p = plan_from(execute=_execute_factory(schema), schema=schema, keys=keys, confirmed=confirmed)
    return json.dumps({
        "summary": p.summary(),
        "keys": {t: {"columns": k, "rule": r} for t, (k, r) in p.keys.items()},
        "relationships": [r.__dict__ for r in p.relationships],
        "ambiguous": p.ambiguous, "keyless": p.keyless, "mermaid": p.mermaid(),
    }, indent=2)


@mcp.tool()
@safe
def create_backend(workspace: str, source: str, name: str, schema: str = "dbo", writable: bool = False,
                   keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                   tables: list[str] | None = None, dry_run: bool = False) -> str:
    """Create (or update in place) a Fabric API for GraphQL item over the source's tables with the
    inferred relationships. Returns the endpoint URL and the portal steps that remain."""
    out = create(workspace, source, name, execute=_execute_factory(schema), schema=schema, keys=keys,
                 confirmed=confirmed, tables=tables, writable=writable, token_provider=_token, dry_run=dry_run)
    return json.dumps({"summary": out["plan"].summary(), "source": out["source"],
                       "result": out.get("result"), "card": out.get("card"),
                       "skipped_relationships": out["definition"].get("skipped_relationships", [])}, indent=2)


@mcp.tool()
@safe
def rayfin_connector(connector: str = "data", source_type: str = "SqlAnalyticsEndpoint", schema: str = "dbo",
                     keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                     tables: list[str] | None = None, relationships: bool = True) -> str:
    """Generate Rayfin (Fabric Apps) connector entity classes + schema.ts for the source's tables, with
    inferred keys and @one/@many relationships. Returns {path: content}; write them under your app."""
    p = plan_from(execute=_execute_factory(schema), schema=schema, keys=keys, confirmed=confirmed)
    check_tables(p.schema, tables)
    return json.dumps(rayfin_files(p, connector, source_type, tables=tables, relationships=relationships), indent=2)


@mcp.tool()
@safe
def ontology_draft(name: str = "ontology", schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                   confirmed: list[dict] | None = None, tables: list[str] | None = None) -> str:
    """The inferred entity types, keys and relationships as a Fabric IQ ontology (preview) draft: summary, binding
    checklist and a Turtle file for the portal's Import ontology. The full item definition needs the Fabric item ids;
    use the remote server or `fabric_backend.ontology_files` for that."""
    p = plan_from(execute=_execute_factory(schema), schema=schema, keys=keys, confirmed=confirmed)
    check_tables(p.schema, tables)
    return json.dumps({"summary": ontology_summary(p, tables), "bindings": ontology_bindings(p, os.environ.get("FABRIC_ODBC", "").split(";")[0] or "source", schema, tables),
                       "ttl": ontology_ttl(p, name, schema, tables)}, indent=2)


@mcp.tool()
@safe
def validate_plan(schema: str = "dbo", keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                  max_items: int = 60) -> str:
    """Check the plan's keys and relationships against the rows: is each key unique and free of NULLs, does every
    reference find its target (orphan count). One counting query per key and relationship, read-only."""
    execute = _execute_factory(schema)
    try:
        p = plan_from(execute=execute, schema=schema, keys=keys, confirmed=confirmed)
        return json.dumps(_evidence.validate(p, execute, max_items=max(1, min(int(max_items), 200))), indent=2, default=str)
    finally:
        getattr(execute, "close", lambda: None)()


@mcp.tool()
@safe
def sample_rows(table: str, schema: str = "dbo", n: int = 10) -> str:
    """The first n rows (at most 20) of one table, to check what a column means."""
    execute = _execute_factory(schema)
    try:
        p = plan_from(execute=execute, schema=schema)
        check_tables(p.schema, [table])
        t = next(x for x in p.schema if x.name.lower() == table.lower())
        rows = execute(_evidence.sample_sql(schema, t.name, t.column_names, max(1, min(int(n), 20))))
        return json.dumps({"table": t.name, "rows": rows}, indent=2, default=str)
    finally:
        getattr(execute, "close", lambda: None)()


@mcp.tool()
@safe
def semantic_model_draft(name: str = "semantic_model", schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                         confirmed: list[dict] | None = None, tables: list[str] | None = None) -> str:
    """The plan as a Power BI semantic model in TMDL: Direct Lake tables on the SQL endpoint in FABRIC_ODBC, one active
    relationship path per table pair (the rest inactive with the reason), README.generated.md with the decisions.
    Returns {path: content}; creates nothing."""
    p = plan_from(execute=_execute_factory(schema), schema=schema, keys=keys, confirmed=confirmed)
    check_tables(p.schema, tables)
    out = _semantic_model.draft(p, _source_info(schema), name, tables)
    out["note"] = ("Drafted locally: the SQL endpoint host and database come from FABRIC_ODBC, the item kind from FABRIC_SOURCE_KIND. "
                   "Unit-tested against Microsoft's sample definitions; not yet created in a live workspace.")
    return json.dumps(out, indent=2)


@mcp.tool()
@safe
def join_path(start: str, end: str, schema: str = "dbo", keys: dict[str, list[str]] | None = None,
              confirmed: list[dict] | None = None) -> str:
    """How two tables connect through the plan: the shortest chain of relationships with the rule per hop and a ready
    T-SQL SELECT … JOIN …, the safest chain by certainty, or which relationship is missing."""
    p = plan_from(execute=_execute_factory(schema), schema=schema, keys=keys, confirmed=confirmed)
    return json.dumps(_paths.join_path(p, start, end), indent=2)


@mcp.tool()
@safe
def data_dictionary(schema: str = "dbo", keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                    validate: bool = False, max_items: int = 60) -> str:
    """Hand-over documentation in Markdown: tables, columns and types, keys and relationships with rules, roles and
    subject areas, an empty Description column; validate=true adds the counts from validate_plan."""
    execute = _execute_factory(schema)
    try:
        p = plan_from(execute=execute, schema=schema, keys=keys, confirmed=confirmed)
        checked = _evidence.validate(p, execute, max_items=max(1, min(int(max_items), 200))) if validate else None
    finally:
        getattr(execute, "close", lambda: None)()
    md = _dictionary.data_dictionary(p, _source_info(schema)["item_name"], schema, checked)
    return json.dumps({"path": f"docs/{schema}-data-dictionary.md", "markdown": md, "summary": p.summary()}, indent=2)


@mcp.tool()
@safe
def dbt_schema(schema: str = "dbo", source_name: str | None = None, keys: dict[str, list[str]] | None = None,
               confirmed: list[dict] | None = None, tables: list[str] | None = None, arguments_block: bool = True) -> str:
    """A dbt sources file: unique and not_null on key columns, relationships on single-column relationships, in the
    syntax of the dbt documentation (arguments_block=false for dbt before 1.10.5)."""
    p = plan_from(execute=_execute_factory(schema), schema=schema, keys=keys, confirmed=confirmed)
    check_tables(p.schema, tables)
    src = source_name or schema
    yml = _dbt.schema_yml(p, src, schema, database=_source_info(schema)["sql_db"], tables=tables, arguments_block=arguments_block)
    return json.dumps({"path": f"models/sources/{src}.yml", "yaml": yml, "summary": p.summary()}, indent=2)


@mcp.tool()
@safe
def analyze_schema(schema: str = "dbo", keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None) -> str:
    """The plan as a graph, metadata only: table roles with the numbers behind them, the most central tables,
    subject areas, cycles and multi-path pairs, and which relationships can be active at once."""
    p = plan_from(execute=_execute_factory(schema), schema=schema, keys=keys, confirmed=confirmed)
    out = _graphs.analyze(p)
    out["summary"] = p.summary().splitlines()[0] + "; " + out["summary"]
    return json.dumps(out, indent=2)


@mcp.tool()
@safe
def suggest_relationships(schema: str = "dbo", keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                          check: int = 15) -> str:
    """Columns that could point at another table's key but are in no relationship, ranked by name, type and
    triangular closure, the best `check` counted against the data (inclusion share). Suggestions only."""
    execute = _execute_factory(schema)
    try:
        p = plan_from(execute=execute, schema=schema, keys=keys, confirmed=confirmed)
        out = _graphs.suggest(p, execute, check=max(0, min(int(check), 100)))
    finally:
        getattr(execute, "close", lambda: None)()
    out["summary"] = p.summary().splitlines()[0] + f"; {len(out['candidates'])} candidate(s), {out['checked_against_data']} checked against the data"
    return json.dumps(out, indent=2, default=str)


@mcp.tool()
@safe
def create_views(schema: str = "dbo", views_schema: str = "krusgraph", keys: dict[str, list[str]] | None = None,
                 confirmed: list[dict] | None = None, dry_run: bool = True) -> str:
    """CREATE OR ALTER VIEW in a schema of its own (created if missing) over the connection in FABRIC_ODBC: a wide
    view per fact table with its dimensions, one per hard-to-read relationship. Never DROP, nothing outside that
    schema. dry_run=true (default) returns the SQL."""
    execute = _execute_factory(schema)
    try:
        p = plan_from(execute=execute, schema=schema, keys=keys, confirmed=confirmed)
        stmts = _views.statements(p, views_schema)
        out = {"summary": p.summary(), "schema": views_schema, "dry_run": dry_run, "schema_sql": stmts["schema_sql"], "views": stmts["views"]}
        if dry_run or not stmts["views"]:
            if not stmts["views"]:
                out["note"] = "No fact table and no hard-to-read relationship in the plan: nothing to create."
            return json.dumps(out, indent=2)
        out["applied"] = _views.apply(stmts, getattr(execute, "statement", None) or execute)
        out["result"] = {"status": "Succeeded", "views": len(stmts["views"]), "schema": views_schema}
        return json.dumps(out, indent=2, default=str)
    finally:
        getattr(execute, "close", lambda: None)()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
