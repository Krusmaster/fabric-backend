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
create_data_agent) live in the remote server only. Set FABRIC_SOURCE_KIND (Lakehouse, Warehouse, SQLDatabase, or
SQLServer for an on-prem or Azure SQL Server reached with Windows or SQL sign-in) and FABRIC_SCHEMAS_ENABLED=1 for a
lakehouse created with schemas when semantic_model_draft should write schemaName. With SQLServer the Fabric-only drafts
(semantic model in Direct Lake, Fabric IQ ontology) answer with an explanation; everything else works. docs/LOCAL.md.

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
import re
from contextlib import contextmanager

from . import create, plan_from
from .errors import safe
from .infer import check_tables
from .rayfin import rayfin_files
from .ontology import bindings as ontology_bindings, ontology_ttl, summary as ontology_summary
from .deploy import token_from_az
from . import evidence as _evidence, semantic_model as _semantic_model, paths as _paths, dictionary as _dictionary
from . import dbt as _dbt, graphs as _graphs, views as _views, compact as _compact

try:
    from mcp.server.mcpserver import MCPServer as _Server          # mcp >= 2
except ImportError:  # pragma: no cover
    try:
        from mcp.server.fastmcp import FastMCP as _Server          # mcp 1.x
    except ImportError as e:
        raise SystemExit("pip install 'fabric-backend[mcp]'") from e

mcp = _Server("fabric-backend")
MAX_RESULT_CHARS = 60000                                  # the same bound as the remote server

try:
    from mcp.types import ToolAnnotations
    RO = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)
    WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=True)
except ImportError:  # pragma: no cover — an SDK without annotations: tools register without them
    RO = WRITE = None


def _tool(title: str, annotations):
    """Register with a title and hints when the SDK takes them (clients show read-only tools without a confirmation)."""
    def wrap(fn):
        try:
            return mcp.tool(title=title, annotations=annotations)(fn) if annotations is not None else mcp.tool(title=title)(fn)
        except TypeError:
            return mcp.tool()(fn)
    return wrap


def _token() -> str:
    return os.environ.get("FABRIC_TOKEN") or token_from_az()


def _execute_factory(schema: str):
    dsn = os.environ.get("FABRIC_ODBC")
    if not dsn:
        raise RuntimeError("FABRIC_ODBC is not set: the stdio server needs an ODBC connection string for the SQL analytics endpoint")
    import pyodbc
    conn = pyodbc.connect(dsn)

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


@contextmanager
def _connection(schema: str):
    """One connection per tool call, closed when the call ends (also on failure)."""
    execute = _execute_factory(schema)
    try:
        yield execute
    finally:
        getattr(execute, "close", lambda: None)()


def _plan(schema: str, keys=None, confirmed=None):
    with _connection(schema) as execute:
        return plan_from(execute=execute, schema=schema, keys=keys, confirmed=confirmed)


_ODBC_SYNONYMS = {"server": ("server", "addr", "address", "network address"), "database": ("database", "initial catalog")}


def _odbc_parts(dsn: str) -> dict[str, str]:
    """key -> value of an ODBC connection string: `;` inside `{...}` does not split, one layer of braces or quotes
    around a value is removed, keys are compared without case."""
    out: dict[str, str] = {}
    for m in re.finditer(r"\s*([^=;]+?)\s*=\s*(\{[^}]*\}|\"[^\"]*\"|'[^']*'|[^;]*)\s*(?:;|$)", dsn):
        k, v = m.group(1).lower(), m.group(2).strip()
        if len(v) >= 2 and v[0] + v[-1] in ("{}", '""', "''"):
            v = v[1:-1]
        out[k] = v
    return out


def _odbc_part(key: str) -> str:
    parts = _odbc_parts(os.environ.get("FABRIC_ODBC", ""))
    for name in _ODBC_SYNONYMS.get(key.lower(), (key.lower(),)):
        if parts.get(name):
            return parts[name]
    return ""


_KINDS = {"lakehouse": "Lakehouse", "warehouse": "Warehouse", "sqldatabase": "SQLDatabase", "sqlserver": "SQLServer"}
FABRIC_ONLY = {"semantic_model_draft": "a Power BI semantic model in Direct Lake mode reads Delta tables through a Fabric SQL analytics endpoint",
               "ontology_draft": "a Fabric IQ ontology binds to tables of a Fabric item"}


def _fabric_only(tool: str, schema: str) -> str | None:
    """FABRIC_SOURCE_KIND=SQLServer: the drafts that only make sense for a Fabric item answer with an explanation."""
    if _source_info(schema)["item_kind"] != "SQLServer":
        return None
    return json.dumps({"error": f"{tool} is Fabric-specific: {FABRIC_ONLY[tool]}; FABRIC_SOURCE_KIND is SQLServer, so there is no such endpoint or item.",
                       "kind": "unsupported",
                       "hint": ("For SQL Server, open the tables in Power BI Desktop (Import or DirectQuery) and use the plan's keys and relationships "
                                "from plan_backend, join_path or data_dictionary; dbt_schema, create_views and the rest work on SQL Server. "
                                "Mirror the database into Fabric (Mirrored database for SQL Server) to get the Fabric drafts." if tool == "semantic_model_draft"
                                else "Mirror the database into Fabric (Mirrored database for SQL Server) or use the plan directly; plan_backend, "
                                     "join_path, data_dictionary, dbt_schema and create_views work on SQL Server.")}, indent=2)


def _source_info(schema: str) -> dict:
    """What the drafts know about the source locally: host and database from the ODBC string, kind and the
    schemas flag from the environment; item ids are unknown here (the remote server has them)."""
    raw = os.environ.get("FABRIC_SOURCE_KIND", "Lakehouse").strip()
    kind = _KINDS.get(raw.lower(), raw or "Lakehouse")
    flag = os.environ.get("FABRIC_SCHEMAS_ENABLED", "").strip().lower()
    schemas_enabled = True if kind != "Lakehouse" else (flag in ("1", "true", "yes") if flag else None)
    db = _odbc_part("Database")                               # empty when the string names none: the drafts keep their placeholder
    return dict(workspace_id="", item_id="", item_name=db, item_kind=kind, schema=schema,
                sql_endpoint=_odbc_part("Server"), sql_db=db, schemas_enabled=schemas_enabled)


@_tool("List tables", RO)
@safe
def list_tables(schema: str = "dbo", tables: list[str] | None = None, detail: str = "auto") -> str:
    """Tables and columns (with types) in the source behind FABRIC_ODBC. `tables` narrows the answer to names or
    patterns (["sales_*"]); `detail` is "auto" (full up to 60 tables, then the column count per table), "full" or "summary"."""
    p = _plan(schema)
    keep = _compact.match_tables(p.schema, tables)
    if _compact.pick_detail(detail, len(keep) if keep is not None else len(p.schema)) == "summary":
        return _compact.bounded(_compact.tables_summary(p.schema, keep), MAX_RESULT_CHARS, _compact.NARROW_HINT)
    return _compact.bounded(_compact.tables_full(p.schema, keep), MAX_RESULT_CHARS, _compact.NARROW_HINT)


@_tool("Plan keys and relationships", RO)
@safe
def plan_backend(schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                 confirmed: list[dict] | None = None, tables: list[str] | None = None, detail: str = "auto") -> str:
    """Infer keys and relationships without deploying. Returns summary, keys and relationships with the rule that
    produced each, ambiguous columns to confirm, names read through the synonym table, suggested composite keys and a
    Mermaid ER diagram. `tables` narrows the answer to names or patterns; `detail` is "auto" (full up to 60 tables,
    then one line per key and relationship), "full" or "summary"."""
    p = _plan(schema, keys=keys, confirmed=confirmed)
    keep = _compact.match_tables(p.schema, tables)
    shown = _compact.sub_plan(p, keep)
    suggested = [s for s in _evidence.suggest_composite_keys(p) if keep is None or s["table"] in keep]
    if _compact.pick_detail(detail, len(shown.schema)) == "summary":
        return _compact.bounded(_compact.plan_summary(shown, suggested, f"{len(shown.schema)} of {len(p.schema)} tables shown" if keep else ""), MAX_RESULT_CHARS, _compact.NARROW_HINT)
    return _compact.bounded(_compact.plan_full(shown, suggested), MAX_RESULT_CHARS, _compact.NARROW_HINT, drop=("mermaid",))


@_tool("Create or update the GraphQL API", WRITE)
@safe
def create_backend(workspace: str, source: str, name: str, schema: str = "dbo", writable: bool = False,
                   keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                   tables: list[str] | None = None, dry_run: bool = False) -> str:
    """Create (or update in place) a Fabric API for GraphQL item over the source's tables with the
    inferred relationships. Returns the endpoint URL and the portal steps that remain."""
    with _connection(schema) as execute:
        out = create(workspace, source, name, execute=execute, schema=schema, keys=keys,
                     confirmed=confirmed, tables=tables, writable=writable, token_provider=_token, dry_run=dry_run)
    return json.dumps({"summary": out["plan"].summary(), "source": out["source"],
                       "result": out.get("result"), "card": out.get("card"),
                       "skipped_relationships": out["definition"].get("skipped_relationships", [])}, indent=2)


@_tool("Rayfin connector entities", RO)
@safe
def rayfin_connector(connector: str = "data", source_type: str = "SqlAnalyticsEndpoint", schema: str = "dbo",
                     keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                     tables: list[str] | None = None, relationships: bool = True) -> str:
    """Generate Rayfin (Fabric Apps) connector entity classes + schema.ts for the source's tables, with
    inferred keys and @one/@many relationships. Returns {path: content}; write them under your app."""
    p = _plan(schema, keys=keys, confirmed=confirmed)
    check_tables(p.schema, tables)
    return json.dumps(rayfin_files(p, connector, source_type, tables=tables, relationships=relationships), indent=2)


@_tool("Draft a Fabric IQ ontology (nothing created)", RO)
@safe
def ontology_draft(name: str = "ontology", schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                   confirmed: list[dict] | None = None, tables: list[str] | None = None) -> str:
    """The inferred entity types, keys and relationships as a Fabric IQ ontology (preview) draft: summary, binding
    checklist and a Turtle file for the portal's Import ontology. The full item definition needs the Fabric item ids;
    use the remote server or `fabric_backend.ontology_files` for that."""
    refused = _fabric_only("ontology_draft", schema)
    if refused:
        return refused
    p = _plan(schema, keys=keys, confirmed=confirmed)
    check_tables(p.schema, tables)
    return json.dumps({"summary": ontology_summary(p, tables), "bindings": ontology_bindings(p, _source_info(schema)["item_name"] or "source", schema, tables),
                       "ttl": ontology_ttl(p, name, schema, tables)}, indent=2)


@_tool("Check the plan against the rows", RO)
@safe
def validate_plan(schema: str = "dbo", keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                  max_items: int = 60) -> str:
    """Check the plan's keys and relationships against the rows: is each key unique and free of NULLs, does every
    reference find its target (orphan count). One counting query per key and relationship, read-only."""
    with _connection(schema) as execute:
        p = plan_from(execute=execute, schema=schema, keys=keys, confirmed=confirmed)
        return json.dumps(_evidence.validate(p, execute, max_items=max(1, min(int(max_items), 200))), indent=2, default=str)


@_tool("Sample rows of one table", RO)
@safe
def sample_rows(table: str, schema: str = "dbo", n: int = 10) -> str:
    """The first n rows (at most 20) of one table, to check what a column means."""
    with _connection(schema) as execute:
        p = plan_from(execute=execute, schema=schema)
        check_tables(p.schema, [table])
        t = next(x for x in p.schema if x.name.lower() == table.lower())
        rows = execute(_evidence.sample_sql(schema, t.name, t.column_names, max(1, min(int(n), 20))))
        return json.dumps({"table": t.name, "rows": rows}, indent=2, default=str)


@_tool("Draft a Power BI semantic model (TMDL, nothing created)", RO)
@safe
def semantic_model_draft(name: str = "semantic_model", schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                         confirmed: list[dict] | None = None, tables: list[str] | None = None) -> str:
    """The plan as a Power BI semantic model in TMDL: Direct Lake tables on the SQL endpoint in FABRIC_ODBC, one active
    relationship path per table pair (the rest inactive with the reason), README.generated.md with the decisions.
    Returns {path: content}; creates nothing."""
    refused = _fabric_only("semantic_model_draft", schema)
    if refused:
        return refused
    p = _plan(schema, keys=keys, confirmed=confirmed)
    check_tables(p.schema, tables)
    out = _semantic_model.draft(p, _source_info(schema), name, tables)
    out["note"] = ("Drafted locally: the SQL endpoint host and database come from FABRIC_ODBC, the item kind from FABRIC_SOURCE_KIND. "
                   "Unit-tested against Microsoft's sample definitions; not yet created in a live workspace.")
    return json.dumps(out, indent=2)


@_tool("How two tables connect", RO)
@safe
def join_path(start: str, end: str, schema: str = "dbo", keys: dict[str, list[str]] | None = None,
              confirmed: list[dict] | None = None) -> str:
    """How two tables connect through the plan: the shortest chain of relationships with the rule per hop and a ready
    T-SQL SELECT … JOIN …, the safest chain by certainty, or which relationship is missing."""
    p = _plan(schema, keys=keys, confirmed=confirmed)
    return json.dumps(_paths.join_path(p, start, end), indent=2)


@_tool("Data dictionary (Markdown)", RO)
@safe
def data_dictionary(schema: str = "dbo", keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                    validate: bool = False, max_items: int = 60) -> str:
    """Hand-over documentation in Markdown: tables, columns and types, keys and relationships with rules, roles and
    subject areas, an empty Description column; validate=true adds the counts from validate_plan."""
    with _connection(schema) as execute:
        p = plan_from(execute=execute, schema=schema, keys=keys, confirmed=confirmed)
        checked = _evidence.validate(p, execute, max_items=max(1, min(int(max_items), 200))) if validate else None
    md = _dictionary.data_dictionary(p, _source_info(schema)["item_name"] or "source", schema, checked)
    return json.dumps({"path": f"docs/{schema}-data-dictionary.md", "markdown": md, "summary": p.summary()}, indent=2)


@_tool("dbt sources file", RO)
@safe
def dbt_schema(schema: str = "dbo", source_name: str | None = None, keys: dict[str, list[str]] | None = None,
               confirmed: list[dict] | None = None, tables: list[str] | None = None, arguments_block: bool = True) -> str:
    """A dbt sources file: unique and not_null on key columns, relationships on single-column relationships, in the
    syntax of the dbt documentation (arguments_block=false for dbt before 1.10.5)."""
    p = _plan(schema, keys=keys, confirmed=confirmed)
    check_tables(p.schema, tables)
    src = source_name or schema
    yml = _dbt.schema_yml(p, src, schema, database=_source_info(schema)["sql_db"], tables=tables, arguments_block=arguments_block)
    return json.dumps({"path": f"models/sources/{src}.yml", "yaml": yml, "summary": p.summary()}, indent=2)


@_tool("Analyze the schema as a graph", RO)
@safe
def analyze_schema(schema: str = "dbo", keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                   tables: list[str] | None = None, detail: str = "auto") -> str:
    """The plan as a graph, metadata only: table roles with the numbers behind them, the most central tables,
    subject areas, cycles and multi-path pairs, and which relationships can be active at once. `tables` narrows
    the answer to names or patterns; `detail` is "auto" (full up to 60 tables, then a summary), "full" or "summary"."""
    p = _plan(schema, keys=keys, confirmed=confirmed)
    keep = _compact.match_tables(p.schema, tables)
    out = _graphs.analyze(p)
    out["summary"] = p.summary().splitlines()[0] + "; " + out["summary"]
    if _compact.pick_detail(detail, len(keep) if keep is not None else len(p.schema)) == "summary":
        return _compact.bounded(_compact.analysis_summary(out, keep), MAX_RESULT_CHARS, _compact.NARROW_HINT)
    return _compact.bounded(_compact.analysis_filtered(out, keep), MAX_RESULT_CHARS, _compact.NARROW_HINT)


@_tool("Suggest missing relationships", RO)
@safe
def suggest_relationships(schema: str = "dbo", keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                          check: int = 15) -> str:
    """Columns that could point at another table's key but are in no relationship, ranked by name, type and
    triangular closure, the best `check` counted against the data (inclusion share). Suggestions only."""
    with _connection(schema) as execute:
        p = plan_from(execute=execute, schema=schema, keys=keys, confirmed=confirmed)
        out = _graphs.suggest(p, execute, check=max(0, min(int(check), 100)))
    out["summary"] = p.summary().splitlines()[0] + f"; {len(out['candidates'])} candidate(s), {out['checked_against_data']} checked against the data"
    return json.dumps(out, indent=2, default=str)


@_tool("Create wide views (dry run by default)", WRITE)
@safe
def create_views(schema: str = "dbo", views_schema: str = "krusgraph", keys: dict[str, list[str]] | None = None,
                 confirmed: list[dict] | None = None, dry_run: bool = True) -> str:
    """CREATE OR ALTER VIEW in a schema of its own (created if missing) over the connection in FABRIC_ODBC: a wide
    view per fact table with its dimensions, one per header table (orders, whose lines a fact table holds) with its
    dimensions, one per hard-to-read relationship. Never DROP, nothing outside that schema. dry_run=true (default)
    returns the SQL."""
    with _connection(schema) as execute:
        p = plan_from(execute=execute, schema=schema, keys=keys, confirmed=confirmed)
        stmts = _views.statements(p, views_schema)
        out = {"summary": p.summary(), "schema": views_schema, "dry_run": dry_run, "schema_sql": stmts["schema_sql"], "views": stmts["views"]}
        if dry_run or not stmts["views"]:
            if not stmts["views"]:
                out["note"] = "No fact table and no hard-to-read relationship in the plan: nothing to create."
            return json.dumps(out, indent=2)
        applied: list = []
        out["applied"] = applied
        try:
            _views.apply(stmts, getattr(execute, "statement", None) or execute, applied)
            out["result"] = {"status": "Succeeded", "views": len(stmts["views"]), "schema": views_schema}
        except Exception as e:  # noqa: BLE001 — explained, with the fallback the docs leave
            from .errors import explain
            out.update(explain(e, f"creating views in schema {views_schema!r}"))
            out["hint"] = (out.get("hint", "") + " If this endpoint refuses CREATE VIEW (a mirrored or SQL database endpoint, or missing "
                           "rights), create the views in a warehouse in the same workspace instead: the SQL is unchanged.").strip()
        return json.dumps(out, indent=2, default=str)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
