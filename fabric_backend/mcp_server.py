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
  answer_query_draft                        a question (Swedish or English) as T-SQL over the safest join path
  silver_notebook_draft                     a PySpark notebook that builds silver tables (lakehouse; nothing created)

The tools that need Fabric item ids (describe_backend, plan_drift, app_starter, create_semantic_model,
create_data_agent, the drift monitor, the creating notebook tools, GraphQL answers) live in the remote server only. Set FABRIC_SOURCE_KIND (Lakehouse, Warehouse, SQLDatabase, or
SQLServer for an on-prem or Azure SQL Server reached with Windows or SQL sign-in) and FABRIC_SCHEMAS_ENABLED=1 for a
lakehouse created with schemas when semantic_model_draft should write schemaName. With SQLServer the Fabric-only drafts
(semantic model in Direct Lake, Fabric IQ ontology) answer with an explanation; everything else works. docs/LOCAL.md.

Databricks (round n13, Draft only): KRUSGRAPH_PLATFORM=databricks with DATABRICKS_HOST (or a profile),
DATABRICKS_WAREHOUSE_ID and DATABRICKS_CATALOG reads a Unity Catalog schema through platforms/databricks.py; the
databricks_* tools draft constraints, a Lakeflow pipeline, metric views and a bundle. docs/DATABRICKS.md.

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
from .platforms import local as _local, databricks as _databricks
from .dialects import TSQL as _TSQL, of as _dialect_of
from . import evidence as _evidence, semantic_model as _semantic_model, paths as _paths, dictionary as _dictionary
from . import dbt as _dbt, graphs as _graphs, views as _views, compact as _compact

try:
    from mcp.server.mcpserver import MCPServer as _Server          # mcp >= 2
except ImportError:  # pragma: no cover
    try:
        from mcp.server.fastmcp import FastMCP as _Server          # mcp 1.x
    except ImportError as e:
        raise SystemExit("pip install 'fabric-backend[mcp]'") from e

INSTRUCTIONS = (
    "Tables in one source behind this local server: a Fabric SQL analytics endpoint, warehouse or SQL database, or a SQL "
    "Server (FABRIC_ODBC), or Databricks Unity Catalog (KRUSGRAPH_PLATFORM=databricks, Draft only). plan_backend gives the "
    "keys and relationships with the rule behind each (K0-K5, R0-R4); validate_plan checks them against the rows; "
    "review_plan keeps the plan, the decisions and the checks as a file to read back later. The "
    "databricks_* tools draft informational constraints, a Lakeflow pipeline, metric views and a bundle from the same "
    "plan; create_databricks_constraints and create_databricks_pipeline are dry runs by default. A tool that does not "
    "apply to the source answers kind unsupported with the tool that does. Failures answer error, kind and hint.")
try:
    mcp = _Server("fabric-backend", instructions=INSTRUCTIONS)
except TypeError:  # pragma: no cover — an SDK without instructions
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
    if _is_databricks():
        return _platform().connect()
    dsn = os.environ.get("FABRIC_ODBC")
    if not dsn:
        raise RuntimeError("FABRIC_ODBC is not set: the stdio server needs an ODBC connection string for the SQL analytics endpoint")
    return _local.odbc_connection(dsn)


@contextmanager
def _connection(schema: str):
    """One connection per tool call, closed when the call ends (also on failure)."""
    execute = _execute_factory(schema)
    try:
        yield execute
    finally:
        getattr(execute, "close", lambda: None)()


def _plan_on(execute, schema: str, keys=None, confirmed=None):
    """The plan of one schema over an open connection: INFORMATION_SCHEMA through plan_from, or the Databricks adapter's
    reader (Unity Catalog: declared constraints, column tags) when KRUSGRAPH_PLATFORM=databricks."""
    if _is_databricks():
        from .infer import plan as _make_plan
        return _make_plan(_platform().read_schema(execute, schema), keys, confirmed)
    return plan_from(execute=execute, schema=schema, keys=keys, confirmed=confirmed)


def _plan(schema: str, keys=None, confirmed=None):
    with _connection(schema) as execute:
        return _plan_on(execute, schema, keys, confirmed)


def _odbc_parts(dsn: str) -> dict[str, str]:
    """key -> value of an ODBC connection string (platforms/local.py)."""
    return _local.odbc_parts(dsn)


def _odbc_part(key: str) -> str:
    return _local.odbc_part(os.environ.get("FABRIC_ODBC", ""), key)


_KINDS = _local.KINDS
FABRIC_ONLY = _local.FABRIC_ONLY


def _is_databricks() -> bool:
    return os.environ.get("KRUSGRAPH_PLATFORM", "").strip().lower() == "databricks"


def _platform():
    """The local adapter: Databricks when KRUSGRAPH_PLATFORM=databricks (platforms/databricks.py), else the source behind
    FABRIC_ODBC with the kind FABRIC_SOURCE_KIND names (platforms/local.py)."""
    if _is_databricks():
        return _databricks.DatabricksPlatform.from_env()
    return _local.OdbcPlatform(_local.source_kind(os.environ.get("FABRIC_SOURCE_KIND", "Lakehouse")))


def _dialect():
    """The SQL the drafts are written in: Databricks SQL with the catalog bound, else T-SQL."""
    return _platform().dialect.with_catalog(_platform().catalog) if _is_databricks() else _TSQL


def _databricks_only(tool: str) -> str | None:
    if _is_databricks():
        return None
    return json.dumps({"error": f"{tool} is a Databricks tool, and this server reads the source behind FABRIC_ODBC.", "kind": "unsupported",
                       "hint": "Set KRUSGRAPH_PLATFORM=databricks with DATABRICKS_HOST, DATABRICKS_WAREHOUSE_ID and DATABRICKS_CATALOG "
                               "(docs/DATABRICKS.md); the Fabric drafts (semantic_model_draft, silver_notebook_draft, create_views) "
                               "serve the same purpose on Fabric."}, indent=2)


def _fabric_only(tool: str, schema: str) -> str | None:
    """A tool the source cannot serve answers with an explanation (OdbcPlatform.unsupported): with SQLServer the drafts
    that only make sense for a Fabric item, and the silver notebook on anything but a lakehouse."""
    refused = _platform().unsupported(tool)
    return json.dumps(refused.answer(), indent=2) if refused else None


def _source_info(schema: str) -> dict:
    """What the drafts know about the source locally: host and database from the ODBC string, kind and the
    schemas flag from the environment; item ids are unknown here (the remote server has them)."""
    if _is_databricks():
        plat = _platform()
        return dict(workspace_id="", item_id="", item_name=plat.catalog or "", item_kind="Databricks", schema=schema,
                    sql_endpoint=plat.host or "", sql_db=plat.catalog or "", schemas_enabled=True)
    kind = _platform().kind
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
    refused = _fabric_only("create_backend", schema)
    if refused:
        return refused
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
    refused = _fabric_only("rayfin_connector", schema)
    if refused:
        return refused
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
        p = _plan_on(execute, schema, keys, confirmed)
        return json.dumps(_evidence.validate(p, execute, max_items=max(1, min(int(max_items), 200))), indent=2, default=str)


@_tool("Keep the reviewed plan as a file", RO)
@safe
def review_plan(schema: str = "dbo", keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                decisions: list[dict] | None = None, previous: dict | str | None = None, validate: bool = False,
                tables: list[str] | None = None, max_items: int = 60) -> str:
    """The plan with the decisions made about it and its checks, as one JSON file to keep in your own repository,
    plus a short Markdown report and what needs attention first. Each key and relationship has a review status
    (proposed, accepted, rejected or open, with a reason, set through `decisions`: [{"item": "key:orders", "review":
    "accepted", "reason": "..."}]) and, separately, a check status (not_checked, passed, failed, stale). validate=true
    runs validate_plan's counting queries. `previous` takes an earlier file from this tool: its corrections are applied
    again, schema changes are listed, and a check on a table that changed becomes stale. Holds names, types, rules,
    decisions and counts, never row values or the connection string. Creates nothing."""
    from datetime import datetime, timezone
    from . import compact as _compact, review as _review
    prev = _review.read(previous) if previous else None
    k, c = _review.merge_arguments(_review.carried_arguments(prev), keys, confirmed) if prev else (keys, confirmed)
    with _connection(schema) as execute:
        p, base = _plan_on(execute, schema, k, c), _plan_on(execute, schema)
        keep = _compact.match_tables(p.schema, tables)
        checks = _evidence.validate(p, execute, max_items=max(1, min(int(max_items), 200))) if validate else None
    rv = _review.build(p, base, {"platform": _platform().name, "schema": schema}, decisions=decisions, checks=checks,
                       previous=prev, tables=sorted(keep) if keep is not None else None,
                       checked_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"))
    return _review.answer(rv, MAX_RESULT_CHARS)


@_tool("Sample rows of one table", RO)
@safe
def sample_rows(table: str, schema: str = "dbo", n: int = 10, show_personal_data: bool = False) -> str:
    """The first n rows (at most 20) of one table, to check what a column means. Binary columns come back as their
    size in bytes; SQL Server's hierarchyid, geography, geometry and sql_variant as text. Columns whose name looks like
    personal data come back masked with the rule; show_personal_data=true returns them as they are."""
    from . import privacy as _privacy
    with _connection(schema) as execute:
        p = _plan_on(execute, schema)
        check_tables(p.schema, [table])
        t = next(x for x in p.schema if x.name.lower() == table.lower())
        types = {c.name: c.data_type for c in t.columns}
        rows = execute(_evidence.sample_sql(schema, t.name, t.column_names, max(1, min(int(n), 20)), types, _dialect_of(execute)))
        flagged = _privacy.personal_columns(p.schema, [t.name])
        if not show_personal_data:
            rows, _ = _privacy.mask_rows(t.name, [dict(r) for r in rows], flagged)
        out = {"table": t.name, "rows": rows}
        found = _privacy.findings(flagged)
        if found:
            out["personal_data"] = {"columns": found, "masked": not show_personal_data, "notice": _privacy.notice(found, show_personal_data)}
        return json.dumps(out, indent=2, default=str)


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
    return json.dumps(_paths.join_path(p, start, end, dialect=_dialect()), indent=2)


@_tool("Data dictionary (Markdown)", RO)
@safe
def data_dictionary(schema: str = "dbo", keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                    validate: bool = False, max_items: int = 60) -> str:
    """Hand-over documentation in Markdown: tables, columns and types, keys and relationships with rules, roles and
    subject areas, an empty Description column; validate=true adds the counts from validate_plan."""
    with _connection(schema) as execute:
        p = _plan_on(execute, schema, keys, confirmed)
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
        p = _plan_on(execute, schema, keys, confirmed)
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
        p = _plan_on(execute, schema, keys, confirmed)
        if _is_databricks():
            from .infer import PlanInputError
            if views_schema.lower() == schema.lower():
                raise PlanInputError(f"views_schema {views_schema!r} is the source schema; the views need a schema of their own")
        stmts = _views.statements(p, views_schema, _dialect())
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
            if _is_databricks():
                out["hint"] = (out.get("hint", "") + " Creating views needs USE CATALOG, USE SCHEMA and CREATE TABLE on the views' schema "
                               "(and CREATE SCHEMA on the catalog when it is new).").strip()
            else:
                out["hint"] = (out.get("hint", "") + " If this endpoint refuses CREATE VIEW (a mirrored or SQL database endpoint, or missing "
                               "rights), create the views in a warehouse in the same workspace instead: the SQL is unchanged.").strip()
        return json.dumps(out, indent=2, default=str)


@_tool("Suggest a T-SQL query for a question (runs nothing)", RO)
@safe
def answer_query_draft(question: str, tables: list[str], schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                       confirmed: list[dict] | None = None, show_personal_data: bool = False) -> str:
    """A question in Swedish or English about the given tables as T-SQL over the safest join path of the plan, each
    step with the rule behind its relationship, plus what was read from the question and what was assumed. Columns that
    look like personal data by name are left out (the key stands in) unless show_personal_data=true. Runs nothing; the
    GraphQL form needs an API in Fabric and is in the remote server."""
    from . import answers as _answers
    refused = _fabric_only("answer_query_draft", schema)
    if refused:
        return refused
    p = _plan(schema, keys=keys, confirmed=confirmed)
    out = _answers.draft(p, question, tables, show_personal_data=show_personal_data)
    out["runs"] = "nothing: the T-SQL runs on the connection in FABRIC_ODBC (SQL analytics endpoint, warehouse or SQL Server)"
    return _compact.bounded(out, MAX_RESULT_CHARS)


@_tool("Draft a PySpark notebook that builds silver tables (nothing created)", RO)
@safe
def silver_notebook_draft(schema: str = "dbo", silver_schema: str = "silver", order_by: dict[str, str] | None = None,
                          keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                          tables: list[str] | None = None) -> str:
    """The Fabric notebook (PySpark) that builds silver tables from a lakehouse's tables: de-duplicated on each key (the
    latest row by `order_by` {table: column} wins), every relationship checked with the rows whose reference is
    missing in krusgraph_quarantine, Delta tables written only in `silver_schema`, each step commented with its rule.
    Returns the steps and the notebook source (notebook-content.py); creates nothing. FABRIC_SOURCE_KIND must be
    Lakehouse."""
    from . import silver as _silver
    info = _source_info(schema)
    refused = _fabric_only("silver_notebook_draft", schema)
    if refused:
        return refused
    if info["schemas_enabled"] is None:                       # not set: a schema other than dbo only exists on a lakehouse with schemas
        info["schemas_enabled"] = schema.lower() != "dbo"
    p = _plan(schema, keys=keys, confirmed=confirmed)
    spec = _silver.spec(p, info, silver_schema, order_by, tables)
    text = _silver.notebook_source(spec)
    out = {"summary": p.summary().splitlines()[0] + f"; the notebook writes {len(spec['tables'])} silver table(s) and {_silver.QUARANTINE}",
           "steps": _silver.steps(spec), "not_checked": spec["not_checked"],
           "notebook": {"path": "notebook-content.py", "format": "fabricGitSource", "content": text},
           "run": ["In Fabric: import the notebook (or paste the cells), attach it to the lakehouse, and Run all; the item ids are not "
                   "known here, so the notebook carries no default lakehouse.",
                   f"Lakehouse with schemas: {spec['source']['schemas_enabled']} (FABRIC_SCHEMAS_ENABLED; a schema other than dbo implies yes)."],
           "note": "Unit-tested; the generated notebook ran on a local PySpark 4.0.1 against the shop seed; not yet run in Fabric."}
    return _compact.bounded(out, MAX_RESULT_CHARS)


# ------------------------------------------------------------------ Databricks (KRUSGRAPH_PLATFORM=databricks) ------
# Draft only: unit-tested with Databricks mocked at its REST API, not yet run against a workspace (docs/DATABRICKS.md).

def _validated(execute, p, max_items: int = 200) -> dict:
    return _evidence.validate(p, execute, max_items=max(1, min(int(max_items), 200)))


@_tool("Databricks: draft informational PRIMARY KEY / FOREIGN KEY constraints (nothing changed)", RO)
@safe
def databricks_constraints_draft(schema: str = "default", keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                                 validate: bool = False, set_not_null: bool = False, max_items: int = 60) -> str:
    """The plan's keys and relationships as Unity Catalog informational constraints: ALTER TABLE ... ADD CONSTRAINT ...
    PRIMARY KEY / FOREIGN KEY for those not declared yet, each with its rule. validate=true runs validate_plan's counts
    first: RELY only where they hold, and a key the data contradicts is left out. A PRIMARY KEY needs NOT NULL columns;
    set_not_null=true adds ALTER COLUMN ... SET NOT NULL where the counts show no NULL. Returns the SQL; changes nothing."""
    refused = _databricks_only("databricks_constraints_draft")
    if refused:
        return refused
    from . import databricks_drafts as _dd
    with _connection(schema) as execute:
        p = _plan_on(execute, schema, keys, confirmed)
        checked = _validated(execute, p, max_items) if validate else None
    out = _dd.constraints(p, _platform().catalog, checked, set_not_null=bool(set_not_null))
    out["summary"] = (f"{len([x for x in out['statements'] if x['kind'] != 'not_null'])} constraint(s) to add, {len(out['skipped'])} left out, "
                      f"{len(out['declared'])} already declared")
    out["note"] = "Draft only: unit-tested with Databricks mocked; not yet run against a workspace."
    return _compact.bounded(out, MAX_RESULT_CHARS)


@_tool("Databricks: add informational constraints (dry run by default)", WRITE)
@safe
def create_databricks_constraints(schema: str = "default", keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                                  set_not_null: bool = False, dry_run: bool = True) -> str:
    """Add the informational PRIMARY KEY / FOREIGN KEY constraints of databricks_constraints_draft to the source tables
    through the SQL warehouse, after validate_plan's counts: RELY only where they hold, a key the data contradicts left
    out, SET NOT NULL only with set_not_null=true and only where there is no NULL. Only ADD; never DROP. dry_run=true
    (default) returns the statements. Needs ownership of each table."""
    refused = _databricks_only("create_databricks_constraints")
    if refused:
        return refused
    from . import databricks_drafts as _dd
    with _connection(schema) as execute:
        p = _plan_on(execute, schema, keys, confirmed)
        out = _dd.constraints(p, _platform().catalog, _validated(execute, p), set_not_null=bool(set_not_null))
        out.pop("sql", None)
        out["dry_run"] = dry_run
        if dry_run or not out["statements"]:
            if not out["statements"]:
                out["note"] = "Nothing to add: every key and relationship is declared already, or left out with the reason."
            return _compact.bounded(out, MAX_RESULT_CHARS)
        applied: list = []
        out["applied"] = applied
        try:
            for st in out["statements"]:
                entry = {"statement": st["kind"], "table": st["table"], "name": st.get("name")}
                applied.append(entry)
                execute.statement(st["sql"])
                entry["status"] = "ok"
            out["result"] = {"status": "Succeeded", "statements": len(applied)}
        except Exception as e:  # noqa: BLE001 — explained, with what was applied before the failure
            from .errors import explain
            out.update(explain(e, "adding the constraints"))
        return _compact.bounded(out, MAX_RESULT_CHARS)


def _pipeline_draft(schema, silver_schema, gold_schema, order_by, keys, confirmed, tables, show_personal_data, name):
    from . import databricks_drafts as _dd
    p = _plan(schema, keys=keys, confirmed=confirmed)
    return _dd.pipeline(p, _platform().catalog, silver_schema, gold_schema, order_by, tables, bool(show_personal_data), name)


@_tool("Databricks: draft a Lakeflow pipeline for silver and gold (nothing created)", RO)
@safe
def databricks_pipeline_draft(schema: str = "default", silver_schema: str = "silver", gold_schema: str = "gold",
                              order_by: dict[str, str] | None = None, keys: dict[str, list[str]] | None = None,
                              confirmed: list[dict] | None = None, tables: list[str] | None = None, show_personal_data: bool = False,
                              name: str = "krusgraph") -> str:
    """The silver and gold rules of the Fabric notebooks as a Lakeflow pipeline in SQL (two notebooks in Databricks'
    source format): per table the latest row per key (by `order_by` {table: column}), the key and every reference as
    expectations that drop the row, clean tables in `silver_schema`, krusgraph_quarantine with each dropped row and its
    rule; one gold materialized view per fact table in `gold_schema` with the plan's keys and relationships as
    expectations. Never over a source table. Returns the notebooks and the pipeline settings; creates nothing."""
    refused = _databricks_only("databricks_pipeline_draft")
    if refused:
        return refused
    out = _pipeline_draft(schema, silver_schema, gold_schema, order_by, keys, confirmed, tables, show_personal_data, name)
    out["note"] = "Draft only: unit-tested, the SELECT logic run on SQLite; not yet run in Databricks."
    return _compact.bounded(out, MAX_RESULT_CHARS)


@_tool("Databricks: create or update the Lakeflow pipeline (dry run by default)", WRITE)
@safe
def create_databricks_pipeline(name: str, schema: str = "default", silver_schema: str = "silver", gold_schema: str = "gold",
                               order_by: dict[str, str] | None = None, keys: dict[str, list[str]] | None = None,
                               confirmed: list[dict] | None = None, tables: list[str] | None = None, show_personal_data: bool = False,
                               dry_run: bool = True) -> str:
    """Write databricks_pipeline_draft's two notebooks to /Workspace/Users/<you>/krusgraph/<name> and create the pipeline
    `name` (serverless), or update the one of that name in place when all its code is in that folder. Starts no run and
    deletes nothing. dry_run=true (default) returns the notebooks and the REST calls it would make."""
    refused = _databricks_only("create_databricks_pipeline")
    if refused:
        return refused
    from .infer import PlanInputError
    if not re.match(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,99}$", name or ""):
        raise PlanInputError("name: letters, digits, _ and -, up to 100 characters")
    out = _pipeline_draft(schema, silver_schema, gold_schema, order_by, keys, confirmed, tables, show_personal_data, name)
    out["dry_run"] = dry_run
    out["rest"] = ["GET /api/2.0/preview/scim/v2/Me (the folder under your user)", f"GET /api/2.0/pipelines?filter=name LIKE '{name}'",
                   "POST /api/2.0/workspace/mkdirs", "POST /api/2.0/workspace/import (silver, gold: SQL notebooks)",
                   "POST /api/2.0/pipelines, or PUT /api/2.0/pipelines/{id} for the pipeline of that name"]
    if dry_run:
        return _compact.bounded(out, MAX_RESULT_CHARS)
    plat = _platform()
    plat.check()
    out["result"] = _databricks.apply_pipeline(plat.rest(), name, out["settings"], out["files"])
    out["next"] = "Open the pipeline in Jobs & Pipelines and start an update; the first run builds silver, the quarantine and gold."
    return _compact.bounded(out, MAX_RESULT_CHARS)


@_tool("Databricks: draft metric views (nothing created)", RO)
@safe
def databricks_metric_view_draft(schema: str = "default", metrics_schema: str = "krusgraph", keys: dict[str, list[str]] | None = None,
                                 confirmed: list[dict] | None = None, show_personal_data: bool = False) -> str:
    """One Unity Catalog metric view per fact table (CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML): the row
    count and the sums semantic_model_draft would suggest as measures, the fact's columns and those of the tables one
    many-to-one step away as dimensions, those tables as joins. Personal columns left out unless show_personal_data.
    Returns the YAML and the SQL; creates nothing."""
    refused = _databricks_only("databricks_metric_view_draft")
    if refused:
        return refused
    from . import databricks_drafts as _dd
    p = _plan(schema, keys=keys, confirmed=confirmed)
    out = _dd.metric_views(p, _platform().catalog, metrics_schema, bool(show_personal_data))
    out["note"] = "Draft only: unit-tested; not yet created in Databricks. Query with MEASURE(`<measure>`)."
    return _compact.bounded(out, MAX_RESULT_CHARS)


@_tool("Databricks: export a bundle (nothing created)", RO)
@safe
def export_databricks_bundle(schema: str = "default", name: str = "krusgraph", silver_schema: str = "silver", gold_schema: str = "gold",
                             views_schema: str = "krusgraph", metrics_schema: str = "krusgraph", keys: dict[str, list[str]] | None = None,
                             confirmed: list[dict] | None = None, validate: bool = False, show_personal_data: bool = False) -> str:
    """What the Databricks drafts would create, as a Declarative Automation Bundle (formerly Databricks Asset Bundle)
    folder for your own repository: databricks.yml, the pipeline and two jobs as resources, the pipeline notebooks, and
    the constraints, views and metric views as SQL files. validate=true runs the counts first, for RELY in the
    constraints. Returns {path: content}; deploy it yourself with `databricks bundle deploy`."""
    refused = _databricks_only("export_databricks_bundle")
    if refused:
        return refused
    from . import databricks_drafts as _dd
    plat = _platform()
    with _connection(schema) as execute:
        p = _plan_on(execute, schema, keys, confirmed)
        checked = _validated(execute, p) if validate else None
    pipe = _dd.pipeline(p, plat.catalog, silver_schema, gold_schema, None, None, bool(show_personal_data), name)
    cons = _dd.constraints(p, plat.catalog, checked)
    if views_schema.lower() == schema.lower():
        from .infer import PlanInputError
        raise PlanInputError(f"views_schema {views_schema!r} is the source schema; the views need a schema of their own")
    v = _views.statements(p, views_schema, _dialect())
    views_sql = "\n\n".join([v["schema_sql"] + ";"] + [f"-- {x['why']}\n{x['sql']};" for x in v["views"]]) + "\n"
    files = _dd.bundle(name, plat.catalog, pipe, cons, views_sql, _dd.metric_views(p, plat.catalog, metrics_schema, bool(show_personal_data)),
                       plat.host or "")
    return _compact.bounded({"files": files, "summary": p.summary().splitlines()[0] + f"; {len(files)} files",
                             "note": "Draft only: unit-tested; not yet deployed. `databricks bundle validate` checks it against your workspace."},
                            MAX_RESULT_CHARS)


@_tool("Databricks: lineage of a schema's tables from the system tables", RO)
@safe
def databricks_lineage(schema: str = "default", table: str | None = None, days: int = 90) -> str:
    """What read from or wrote to the schema's tables in the last `days` days, from system.access.table_lineage:
    source and target tables, and the notebook, job, pipeline, dashboard or query (entity_type, entity_id) behind each
    event. Needs access to the system catalog (an account admin enables and grants it). Read-only."""
    refused = _databricks_only("databricks_lineage")
    if refused:
        return refused
    plat = _platform()
    with _connection(schema) as execute:
        rows = _databricks.lineage(execute, plat.catalog, schema, max(1, min(int(days), 365)))
    full = f"{plat.catalog}.{schema}".lower()
    if table:
        t = f"{full}.{table}".lower()
        rows = [r for r in rows if str(r.get("source_table_full_name") or "").lower() == t or str(r.get("target_table_full_name") or "").lower() == t]
    downstream = sorted({str(r.get("target_table_full_name")) for r in rows
                         if str(r.get("source_table_full_name") or "").lower().startswith(full + ".") and r.get("target_table_full_name")})
    entities = sorted({f"{r.get('entity_type')} {r.get('entity_id')}" for r in rows if r.get("entity_type")})
    return _compact.bounded({"schema": full, "table": table, "days": days, "events": rows, "downstream_tables": downstream,
                             "entities": entities,
                             "note": "system.access.table_lineage holds a subset of read and write events (Databricks captures lineage "
                                     "where it can). Draft only: unit-tested; not yet run against a workspace."}, MAX_RESULT_CHARS)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
