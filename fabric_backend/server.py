"""Remote MCP server (Streamable HTTP): your Fabric tables, with keys, relationships and rules,
for Claude, Cursor and Lovable.

    fabric-backend-server                      # http://0.0.0.0:8000/mcp
    FABRIC_TENANT_ID / FABRIC_CLIENT_ID / FABRIC_CLIENT_SECRET   a service principal with access to the workspaces

Authentication, in order:
  0. Entra sign-in (when MCP_PUBLIC_URL / ENTRA_CLIENT_ID / ENTRA_CLIENT_SECRET are set) — the directory path:
     each user signs in with their own work account, the server validates the token and exchanges it
     on-behalf-of for Fabric and SQL tokens. Unauthenticated calls get the 401 Claude needs. See entra.py.
  1. `Authorization: Bearer <token>` on the request — a Fabric API token (audience api.fabric.microsoft.com);
     `X-Fabric-SQL-Token` carries the SQL analytics endpoint token (audience database.windows.net) when the
     caller has one. This is what an OAuth front (Entra on-behalf-of) will supply.
  2. Otherwise the server's own service principal mints both tokens (client credentials). This is the
     "custom connection" model Lovable's Fabric connector uses: one principal, no per-user identity.
The server stores nothing: no tokens beyond their lifetime, no data, no query results.

Tools (all annotated for the Claude directory): thirty-six, from list_workspaces to sap_pack_draft; docs page
/docs lists them. Around every tool: fair-use limits (limits.py), anonymous usage counts (usage.py) and the dormant paid-plan
check (entitlements.py).
"""
from __future__ import annotations

import json
import re

import requests
import os
import time

from .infer import check_tables, plan as make_plan
from .schema import Schema
from .graphql import definition
from .deploy import FABRIC, deploy, connection_card, find_item_by_name, source_for, SOURCE_ITEM_TYPES, ENDPOINT_ITEM_ROUTES
from .rayfin import rayfin_files
from . import ontology as _ontology
from .deploy import create_ontology as _create_ontology
from .errors import HINTS, SchemaEmpty, _fabric_body, classify_http, safe
from . import evidence as _evidence
from . import semantic_model as _semantic_model, paths as _paths, dictionary as _dictionary, dbt as _dbt, drift as _drift
from . import views as _views, data_agent as _data_agent, app_starter as _app_starter, graphs as _graphs, readiness as _readiness
from . import lineage as _lineage, compact as _compact, sap_pack as _sap_pack
from . import limits as _limits, usage as _usage, entitlements as _entitlements
from .deploy import create_semantic_model as _create_semantic_model
from .platforms import fabric as _fabric

try:
    from mcp.server.mcpserver import MCPServer, Context
    from mcp.types import ToolAnnotations
except ImportError as e:  # pragma: no cover
    raise SystemExit("pip install 'fabric-backend[server]'") from e

FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
SQL_SCOPE = "https://database.windows.net/.default"

from .discovery import package_version as _package_version  # noqa: E402
from . import tool_status as _tool_status  # noqa: E402
from . import tool_params as _p  # noqa: E402

mcp = MCPServer("fabric-backend", version=_package_version(), instructions=(
    "Tables in a Microsoft Fabric lakehouse/warehouse → a GraphQL API with inferred keys and relationships, "
    "plus Rayfin connector entities. Start with list_workspaces (or list_sources if you know the workspace), then plan_backend (nothing is deployed; "
    "it also suggests composite keys), sample_rows when a column's meaning is unclear, validate_plan to check keys and "
    "relationships against the rows (create_backend does not run it, and has no dry run), then create_backend. Before query_graphql, describe_backend gives the exact field "
    "names. Every inferred key/relationship carries the rule that produced it (K0–K5, R0–R4, or \"SAP pack\" for SAP tables such as "
    "VBAK/VBAP, whose keys with MANDT and order-to-cash relationships come from public sources; sap_pack_draft shows what the pack "
    "recognises and what is missing); "
    "ambiguous columns are reported, never guessed. From the same plan, without creating anything: semantic_model_draft "
    "(a Power BI model in TMDL, Direct Lake) when a report is the goal; join_path when the user asks how two tables "
    "connect or wants the SQL for it; data_dictionary for hand-over documentation; dbt_schema when the team tests with dbt; "
    "plan_drift before re-running create_backend on an existing API, to see what would change. One plan, five Fabric pieces: "
    "create_backend (the API for GraphQL), create_semantic_model (a Power BI semantic model item from the TMDL draft), "
    "create_ontology (a Fabric IQ ontology item: entity types with keys, relationship types, bindings), create_views (wide T-SQL views in a schema of "
    "their own on the SQL endpoint), create_data_agent (a Fabric data agent with the plan as instructions and examples) — all but "
    "create_backend answer with what they would create until dry_run=false. Creating a semantic model, ontology, data agent, notebook "
    "or pipeline needs a permission the operator may not have granted the app; without it the tool answers kind consent naming "
    "the scope, and the dry run still works. app_starter gives a Lovable prompt, connection details, queries and "
    "the Supabase edge function for an app on a created API; app_readiness lists what that API still needs before an app can use "
    "it (introspection, permissions, keys, relationships) with the next step per item. lineage shows which GraphQL APIs, "
    "semantic models, views and data agents in the workspace build on a source's tables and what a change to one table "
    "reaches; plan_drift names those objects for the tables and columns a re-run would drop. analyze_schema reads an unknown lakehouse as a graph (table roles, central tables, "
    "subject areas, cycles, which relationships can be active); suggest_relationships when the plan lacks links: it ranks "
    "candidate columns and checks the best against the data, suggesting only. From understanding to building: "
    "silver_notebook_draft and create_silver_notebook give a Fabric PySpark notebook that writes de-duplicated silver "
    "tables with every reference checked and a quarantine table, never over the source; drift_monitor_draft and "
    "create_drift_monitor a nightly notebook and pipeline that compare the plan with the last one and message a "
    "webhook; answer_query_draft turns a question (Swedish or English) into T-SQL over the safest join path, or "
    "GraphQL for an existing API, and query_graphql with question= runs it. gold_views_draft and create_gold_views give "
    "materialized lake views over the silver tables, one wide view per fact table with the plan's keys and relationships as data "
    "quality rules; compare_semantic_model checks an existing Power BI semantic model against the plan (missing, contradicted, "
    "cardinality, direction, active); export_item_definitions gives what the creating tools would create as files in Fabric's Git "
    "format, for the user's own repository. Columns that look like personal data by name are masked in sample_rows and left out "
    "of drafted queries and gold views unless show_personal_data=true. Alongside Microsoft's own Fabric MCP servers (Fabric Core "
    "and the local Fabric MCP Server for workspaces, items and files; Fabric IQ MCP for questions to semantic models; Power BI "
    "Modeling MCP for editing a model), this server is the part that works out how the tables relate and builds from that plan. "
    "This server reads Microsoft Fabric only; a Databricks adapter (Draft only: Unity Catalog, informational constraints, a "
    "Lakeflow pipeline, metric views) runs in the local stdio server, see /docs#databricks-draft-only. "
    "A call that cannot be completed answers with error (plain words), "
    "kind (a stable code such as not_found, no_access, capacity, sign_in, consent, schema_not_found, timeout, "
    "rate_limited with retry_after) and "
    "hint (the next step that fixes it). Five first questions that pay off on a lakehouse nobody has documented: "
    "(1) analyze_schema — which tables are facts, which are dimensions, what are the subject areas; (2) plan_backend — the keys "
    "and relationships with the rule behind each; (3) validate_plan — are the keys unique and do the references hold; "
    "(4) suggest_relationships — which columns look like references but are in no relationship; (5) data_dictionary — the "
    "hand-over document with everything above. review_plan keeps the plan, the decisions about it and the checks as a file "
    "for the user's own repository; passed back as previous it applies the decisions again and marks checks on changed "
    "tables stale. Shared parameters: workspace (list_workspaces), source (list_sources; lakehouse, warehouse or SQL "
    "database) and api take a name or an id; confirmed lists relationships the user confirmed and is not an approval flag; "
    "an entry has source, source_cols, target, target_cols (default source_cols) and optional field_name and reverse_name; "
    "tables narrows what is shown or included while the plan is still made from the whole schema. "
    + _tool_status.instructions_sentence()))


# ------------------------------------------------------------------ auth ---------------------

class Auth:
    """Tokens for the two audiences the server talks to. Request headers win; else client credentials."""

    def __init__(self) -> None:
        self.tenant = os.environ.get("FABRIC_TENANT_ID")
        self.client = os.environ.get("FABRIC_CLIENT_ID")
        self.secret = os.environ.get("FABRIC_CLIENT_SECRET")
        self._cache: dict[str, tuple[str, float]] = {}
        from .entra import EntraConfig
        self.entra = EntraConfig.from_env()
        self._validator = self._obo = None

    @property
    def validator(self):
        if self._validator is None:
            from .entra import Validator
            self._validator = Validator(self.entra)
        return self._validator

    @property
    def obo(self):
        if self._obo is None:
            from .entra import OnBehalfOf
            self._obo = OnBehalfOf(self.entra)
        return self._obo

    @staticmethod
    def _bearer(ctx) -> str | None:
        h = (ctx.headers if ctx is not None else {}) or {}
        a = h.get("authorization") or h.get("Authorization") or ""
        return a[7:].strip() if a.lower().startswith("bearer ") else None

    def _user_token(self, ctx, scope: str) -> str:
        """Entra mode: the request's token is for *this app*; exchange it for the downstream audience."""
        tok = self._bearer(ctx)
        if not tok:
            raise PermissionError("sign-in required")
        claims = self.validator.validate(tok)
        return self.obo.token(tok, claims["tid"], scope)

    def _client_credentials(self, scope: str) -> str:
        if not (self.tenant and self.client and self.secret):
            raise RuntimeError("no bearer token on the request and no FABRIC_TENANT_ID/CLIENT_ID/CLIENT_SECRET on the server")
        tok, exp = self._cache.get(scope, (None, 0.0))
        if tok and exp - 60 > time.time():
            return tok
        import requests
        r = requests.post(f"https://login.microsoftonline.com/{self.tenant}/oauth2/v2.0/token", timeout=30, data={
            "grant_type": "client_credentials", "client_id": self.client, "client_secret": self.secret, "scope": scope})
        r.raise_for_status()
        body = r.json()
        self._cache[scope] = (body["access_token"], time.time() + int(body.get("expires_in", 3600)))
        return body["access_token"]

    def fabric(self, ctx: Context | None) -> str:
        if self.entra:
            return self._user_token(ctx, FABRIC_SCOPE)
        tok = self._bearer(ctx)
        return tok if tok else self._client_credentials(FABRIC_SCOPE)

    def sql(self, ctx: Context | None) -> str:
        if self.entra:
            return self._user_token(ctx, SQL_SCOPE)
        h = (ctx.headers if ctx is not None else {}) or {}
        t = h.get("x-fabric-sql-token") or h.get("X-Fabric-SQL-Token")
        return t.strip() if t else self._client_credentials(SQL_SCOPE)


auth = Auth()


def _headers(ctx) -> dict:
    return {"Authorization": f"Bearer {auth.fabric(ctx)}", "Content-Type": "application/json"}


# ------------------------------------------------------------------ fabric helpers -----------
# Reading Fabric and opening the SQL endpoint is the Fabric adapter's (platforms/fabric.py). These wrappers keep the
# names the tools (and the tests) use, and pass the server's own patchable readers in.

_GUID = _fabric.GUID
LOGIN_TIMEOUT = _fabric.LOGIN_TIMEOUT      # seconds to log in to the SQL analytics endpoint
QUERY_TIMEOUT = _fabric.QUERY_TIMEOUT      # seconds per metadata query


def _workspaces(headers: dict) -> list[dict]:
    """Every workspace the signed-in account can see: id, name, type, capacity."""
    return _fabric.workspaces(headers)


def _workspace_id(workspace: str, headers: dict) -> str:
    """Tools take a workspace id or its display name; a name is looked up (case does not matter)."""
    return _fabric.workspace_id(workspace, headers, _workspaces)


def _resolve_source(workspace: str, source: str, headers: dict) -> dict:
    """Lakehouse / warehouse / SQL database by name or id → item dict with sql endpoint host."""
    return _fabric.resolve_source(workspace, source, headers, find_item_by_name)


def _execute_factory(item: dict, sql_token: str):
    """DB-API over the SQL analytics endpoint with an Entra access token (ODBC Driver 18)."""
    return _fabric.connect(item, sql_token, LOGIN_TIMEOUT, QUERY_TIMEOUT)


def _plan(workspace: str, source: str, schema: str, keys, confirmed, ctx):
    headers = _headers(ctx)
    workspace = _workspace_id(workspace, headers)
    item = _resolve_source(workspace, source, headers)
    execute = _execute_factory(item, auth.sql(ctx))
    try:
        s = _fabric.PLATFORM.read_schema(execute, schema)
    finally:
        getattr(execute, "close", lambda: None)()                          # the connection does not outlive the call
    if len(s) == 0:
        raise SchemaEmpty(f"Schema {schema!r} has no tables in {source!r} (workspace {workspace}); it may not exist in this source.")
    return make_plan(s, keys, confirmed), item, headers


# ------------------------------------------------------------------ tools --------------------

RO = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=True)   # the creating tools: dry run by default, never delete


limiter = _limits.Limiter.from_env()          # None when KRUSGRAPH_RATE_LIMITS=0; applies only to signed-in (Entra) calls


def _identity(ctx) -> dict | None:
    """oid and tid of the signed-in user on this call, from the token the 401 guard accepted; None outside Entra mode
    or without a valid token (the tool itself then answers sign_in, as before)."""
    if not auth.entra:
        return None
    tok = Auth._bearer(ctx)
    if not tok:
        return None
    try:
        claims = auth.validator.validate(tok)
    except Exception:  # noqa: BLE001 — not ours to answer here; the tool's own sign-in check does
        return None
    return {"oid": claims.get("oid") or claims.get("sub"), "tid": claims.get("tid")}


def _instrumented(fn, name: str):
    """Around every tool: the fair-use limit per user and organisation (limits.py), the paid-feature check when
    KRUSGRAPH_ENTITLEMENTS=1 (entitlements.py), and one anonymous usage record (usage.py: tool, outcome kind,
    duration, dry run). A refused call answers in the tool's own error format and runs nothing. The signature is
    the tool's own (functools.wraps), so the MCP schema and the ctx injection are unchanged."""
    import functools
    import inspect
    sig = inspect.signature(fn)
    dry_default = sig.parameters["dry_run"].default if "dry_run" in sig.parameters else None

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        start = time.monotonic()
        who = _identity(kwargs.get("ctx"))
        dry_run = None
        if dry_default is not None:
            try:
                dry_run = bool(sig.bind_partial(*args, **kwargs).arguments.get("dry_run", dry_default))
            except TypeError:
                dry_run = bool(dry_default)
        refusal = None
        if who and limiter is not None:
            hit = limiter.check(who.get("oid"), who.get("tid"))
            refusal = _limits.answer(hit) if hit else None
        if refusal is None and _entitlements.enabled():
            refusal = _entitlements.check(name, dry_run, (who or {}).get("tid"))
        text = json.dumps(refusal, indent=2) if refusal is not None else fn(*args, **kwargs)
        try:
            _usage.usage.record(name, _usage.outcome_of(text), time.monotonic() - start, dry_run, (who or {}).get("tid"))
        except Exception:  # noqa: BLE001 — counting must never break a call
            pass
        return text
    return wrapper


def _titled_tool(register):
    """The Claude directory reads a tool's name from annotations.title, not only from the tool's title: copy the
    title into the annotations of every tool, so each listing shows a human-readable name. Every tool is registered
    through _instrumented (limits, entitlements, usage)."""
    def tool(*args, title: str | None = None, annotations: ToolAnnotations | None = None, **kwargs):
        if title:
            annotations = (annotations or ToolAnnotations()).model_copy(update={"title": title})
        decorator = register(*args, title=title, annotations=annotations, **kwargs)

        def wrap(fn):
            return decorator(_instrumented(fn, kwargs.get("name") or fn.__name__))
        return wrap
    return tool


mcp.tool = _titled_tool(mcp.tool)


@mcp.tool(title="List workspaces", annotations=RO)
@safe
def list_workspaces(ctx: Context = None) -> str:
    """Lists the Fabric workspaces the signed-in account can see. Takes no arguments. Returns JSON {workspaces: [{id, name,
    capacity}]}; the name or id is the `workspace` of the other tools. Read-only. Errors: {error, kind, hint}."""
    return json.dumps({"workspaces": _workspaces(_headers(ctx))}, indent=2)


@mcp.tool(title="List data sources in a workspace", annotations=RO)
@safe
def list_sources(workspace: _p.Workspace, ctx: Context = None) -> str:
    """Lists the data sources in one workspace (lakehouses, warehouses, SQL databases, mirrored databases and catalogs) and
    its API for GraphQL items. Requires a workspace. Returns JSON {workspace, sources: [{name, id, type}],
    graphql_apis: [{name, id}]}; a source's name is the `source`, an API's name the `api` of the other tools.
    Read-only. Errors: {error, kind, hint}."""
    import requests
    headers = _headers(ctx)
    workspace = _workspace_id(workspace, headers)
    out = {"workspace": workspace, "sources": [], "graphql_apis": []}
    url = f"{FABRIC}/v1/workspaces/{workspace}/items"
    while url:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        body = r.json()
        for it in body.get("value", []):
            if it.get("type") in SOURCE_ITEM_TYPES:
                out["sources"].append({"name": it["displayName"], "id": it["id"], "type": it["type"]})
            elif it.get("type") == "GraphQLApi":
                out["graphql_apis"].append({"name": it["displayName"], "id": it["id"]})
        url = body.get("continuationUri")
    return json.dumps(out, indent=2)


@mcp.tool(title="List tables and columns", annotations=RO)
@safe
def list_tables(workspace: _p.Workspace, source: _p.Source, schema: _p.Schema = "dbo", tables: _p.TablesShown = None, detail: _p.Detail = "auto",
                ctx: Context = None) -> str:
    """Lists the tables and their columns with types in one schema of a source. Requires workspace and source. Returns JSON
    with columns and types per table, or a column count per table when the answer is a summary. Read-only. Errors:
    {error, kind, hint}."""
    p, _, _ = _plan(workspace, source, schema, None, None, ctx)
    keep = _compact.match_tables(p.schema, tables)
    if _compact.pick_detail(detail, len(keep) if keep is not None else len(p.schema)) == "summary":
        return _bounded(_compact.tables_summary(p.schema, keep), MAX_RESULT_CHARS, _compact.NARROW_HINT)
    return _bounded(_compact.tables_full(p.schema, keep), MAX_RESULT_CHARS, _compact.NARROW_HINT)


@mcp.tool(title="Plan keys and relationships (nothing deployed)", annotations=RO)
@safe
def plan_backend(workspace: _p.Workspace, source: _p.Source, schema: _p.Schema = "dbo", keys: _p.Keys = None,
                 confirmed: _p.Confirmed = None, tables: _p.TablesShown = None, detail: _p.Detail = "auto",
                 mermaid: _p.Mermaid = True, ctx: Context = None) -> str:
    """Infers primary keys and relationships for the tables in a schema and proposes them as a plan. Requires workspace and
    source. Returns JSON: summary, keys and relationships each with the rule behind it (K0–K5, R0–R4), ambiguous
    columns, keyless tables, suggested composite keys and a Mermaid ER diagram. Changes nothing in Fabric.
    validate_plan checks it against the rows; create_backend builds the API. Errors: {error, kind, hint}."""
    p, _, _ = _plan(workspace, source, schema, keys, confirmed, ctx)
    keep = _compact.match_tables(p.schema, tables)
    shown = _compact.sub_plan(p, keep)
    suggested = [s for s in _evidence.suggest_composite_keys(p) if keep is None or s["table"] in keep]
    if _compact.pick_detail(detail, len(shown.schema)) == "summary":
        return _bounded(_compact.plan_summary(shown, suggested, f"{len(shown.schema)} of {len(p.schema)} tables shown" if keep else ""), MAX_RESULT_CHARS, _compact.NARROW_HINT)
    return _bounded(_compact.plan_full(shown, suggested, mermaid=bool(mermaid)), MAX_RESULT_CHARS, _compact.NARROW_HINT, drop=("mermaid",))


def _connected(workspace: str, source: str, schema: str, ctx):
    """(plan inputs) the source's schema plus an open SQL connection; the caller closes it."""
    headers = _headers(ctx)
    workspace = _workspace_id(workspace, headers)
    item = _resolve_source(workspace, source, headers)
    execute = _execute_factory(item, auth.sql(ctx))
    try:
        execute.source_item = item                                         # the sensitivity label, for the answers that show values
    except AttributeError:
        pass
    try:
        s = _fabric.PLATFORM.read_schema(execute, schema)
    except Exception:
        getattr(execute, "close", lambda: None)()
        raise
    if len(s) == 0:
        getattr(execute, "close", lambda: None)()
        raise SchemaEmpty(f"Schema {schema!r} has no tables in {source!r} (workspace {workspace}); it may not exist in this source.")
    return s, execute


@mcp.tool(title="Check the plan against the data", annotations=RO)
@safe
def validate_plan(workspace: _p.Workspace, source: _p.Source, schema: _p.Schema = "dbo", keys: _p.Keys = None,
                  confirmed: _p.Confirmed = None, max_items: _p.MaxItems = 60, ctx: Context = None) -> str:
    """Checks the plan against the rows: is each key unique and non-null, and how many references find no target (orphans).
    Requires workspace and source; takes the same keys and confirmed as plan_backend. Returns JSON with counts and a
    verdict per key and relationship (no row values). Read-only counting queries. create_backend does not run this
    check. Errors: {error, kind, hint}."""
    from . import privacy as _privacy
    s, execute = _connected(workspace, source, schema, ctx)
    try:
        p = make_plan(s, keys, confirmed)
        out = _evidence.validate(p, execute, max_items=max(1, min(int(max_items), 200)))
        label = _privacy.label_of(getattr(execute, "source_item", None))
    finally:
        getattr(execute, "close", lambda: None)()
    checked = {(k["table"], c.lower()) for k in out["keys"] for c in k["columns"]} | \
              {(r[t], c.lower()) for r in out["relationships"] for t, cs in (("source", r["columns"]), ("target", r["target_columns"])) for c in cs}
    flagged = [f for f in _privacy.findings(_privacy.personal_columns(p.schema)) if (f["table"], f["column"].lower()) in checked]
    if flagged or label:
        out["personal_data"] = {"columns": flagged, "sensitivity_label": label,
                                "note": "validate_plan returns counts and verdicts only, never a value, so nothing here is masked."}
    return json.dumps(out, indent=2, default=str)


@mcp.tool(title="Keep the reviewed plan as a file (nothing in Fabric changes)", annotations=RO)
@safe
def review_plan(workspace: _p.Workspace, source: _p.Source, schema: _p.Schema = "dbo", keys: _p.Keys = None,
                confirmed: _p.Confirmed = None, decisions: _p.Decisions = None, previous: _p.Previous = None,
                validate: _p.Validate = False, tables: _p.TablesShown = None, max_items: _p.MaxItems = 60, ctx: Context = None) -> str:
    """Builds a review file of the plan: each key and relationship with a review status and a check status, plus a
    Markdown report. Requires workspace and source. Returns JSON with the file, the report and what needs attention
    first, no row values. Changes nothing. Errors: {error, kind, hint}."""
    from datetime import datetime, timezone
    from . import review as _review
    prev = _review.read(previous) if previous else None
    k, c = _review.merge_arguments(_review.carried_arguments(prev), keys, confirmed) if prev else (keys, confirmed)
    s, execute = _connected(workspace, source, schema, ctx)
    try:
        p, base = make_plan(s, k, c), make_plan(s)
        keep = _compact.match_tables(p.schema, tables)
        checks = _evidence.validate(p, execute, max_items=max(1, min(int(max_items), 200))) if validate else None
    finally:
        getattr(execute, "close", lambda: None)()
    rv = _review.build(p, base, {"platform": "fabric", "workspace": workspace, "source": source, "schema": schema},
                       decisions=decisions, checks=checks, previous=prev, tables=sorted(keep) if keep is not None else None,
                       checked_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"))
    return _review.answer(rv, MAX_RESULT_CHARS)


@mcp.tool(title="Show a few rows of a table", annotations=RO)
@safe
def sample_rows(workspace: _p.Workspace, source: _p.Source, table: _p.SampleTable, schema: _p.Schema = "dbo", n: _p.SampleN = 10, show_personal_data: _p.ShowPersonalData = False,
                ctx: Context = None) -> str:
    """Returns the first rows of one table so that a column's meaning can be checked. Requires workspace, source and table.
    Returns JSON {table, columns, rows, personal_data}; long text is shortened, and columns that look like personal
    data are masked unless show_personal_data=true. Read-only. Errors: {error, kind, hint}."""
    from . import privacy as _privacy
    s, execute = _connected(workspace, source, schema, ctx)
    try:
        t = next((x for x in s if x.name.lower() == table.lower()), None)
        if t is None:
            return json.dumps({"error": f"no table {table!r} in schema {schema!r} of {source!r}",
                               "kind": "table_not_found", "hint": "list_tables shows the tables in a schema."}, indent=2)
        n = max(1, min(int(n), 20))
        types = {c.name: c.data_type for c in t.columns}           # binary as its size, CLR types as text (as the local server does)
        rows = execute(_evidence.sample_sql(schema, t.name, t.column_names, n, types))
    finally:
        getattr(execute, "close", lambda: None)()

    def short(v):
        v = v if isinstance(v, (int, float, bool)) or v is None else str(v)
        return v[:200] + "…" if isinstance(v, str) and len(v) > 200 else v
    return json.dumps(_privacy_rows(t.name, t.column_names, [{k: short(v) for k, v in r.items()} for r in rows], s, show_personal_data,
                                    getattr(execute, "source_item", None)), indent=2, default=str)


def _privacy_rows(table: str, columns: list[str], rows: list[dict], schema, show: bool, item: dict | None = None) -> dict:
    """sample_rows' answer: rows with the columns the privacy rules flag masked unless `show`, the findings, the notice
    and the item's sensitivity label (fabric_backend/privacy.py)."""
    from . import privacy as _privacy
    flagged = _privacy.personal_columns(schema, [table])
    if not show:
        rows, _ = _privacy.mask_rows(table, rows, flagged)
    out = {"table": table, "columns": columns, "rows": rows}
    found = _privacy.findings(flagged)
    label = _privacy.label_of(item)
    if found or label:
        out["personal_data"] = {"columns": found, "masked": bool(found) and not show, "notice": _privacy.notice(found, show),
                                "sensitivity_label": label}
    return out


@mcp.tool(title="Create or update the GraphQL API", annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True,
                                                                               idempotent_hint=True, open_world_hint=True))
@safe
def create_backend(workspace: _p.Workspace, source: _p.Source, name: _p.BackendName, schema: _p.Schema = "dbo", writable: _p.Writable = False,
                   keys: _p.Keys = None, confirmed: _p.Confirmed = None,
                   tables: _p.CreateBackendTables = None, allow_removals: _p.AllowRemovals = False, ctx: Context = None) -> str:
    """Creates a Fabric API for GraphQL item over the source's tables with the plan's keys and relationships, or updates
    the API of that name in place. Requires workspace, source and name. Returns JSON {summary, result, card
    (endpoint, portal steps left), skipped_relationships}. Changes Fabric: an update replaces the API's definition;
    tables outside `tables` or gone from the source leave it, field names of unchanged relationships are kept, and
    no item is deleted. When an update would drop relationships the API has, nothing is written and the answer (kind
    would_remove) lists them as confirmed entries. No dry run, and it does not run validate_plan; plan_backend
    proposes, validate_plan checks, plan_drift previews an update. Errors: {error, kind, hint}."""
    workspace = _workspace_id(workspace, _headers(ctx))      # a display name becomes the id every call below needs
    p, item, headers = _plan(workspace, source, schema, keys, confirmed, ctx)
    check_tables(p.schema, tables)
    source_id, source_type = source_for(workspace, item, headers)
    found = _existing_api(workspace, name, headers)
    kept: list[dict] = []
    if found:                                    # the API's field names for the same relationships stay (finding 7, 27 October)
        p, kept = _drift.keep_api_names(p, found[1], confirmed)
    if not allow_removals:
        lost = _relationships_lost(found, name, p, source_id, source_type, writable, tables, confirmed)
        if lost:
            keep = _drift.keep_entries(lost)
            return json.dumps({
                "error": f"updating {name!r} would remove {len(lost)} relationship(s) the API has today; nothing was written.",
                "kind": "would_remove", "relationships_lost": lost, "keep_with_confirmed": keep,
                "hint": "To keep them, call create_backend again with confirmed=keep_with_confirmed (added to any confirmed "
                        "you already pass). To drop them on purpose, call it with allow_removals=true."}, indent=2)
    env = definition(p, name, workspace, source_id, source_type, writable=writable, tables=tables)
    result = deploy(env, workspace, token_provider=lambda: auth.fabric(ctx))
    out = {"summary": p.summary(), "source": {"id": source_id, "type": source_type}, "result": result,
           "skipped_relationships": env.get("skipped_relationships", [])}
    if kept:
        out["names_kept_from_api"] = kept
    if result.get("status") == "Succeeded":
        out["card"] = connection_card(workspace, result["id"], name)
    elif result.get("status") == "Failed" and result.get("http"):          # Fabric refused the create/update: say why
        out.update(classify_http(int(result["http"]), result.get("body", ""), f"creating {name!r} in workspace {workspace}"))
        result.pop("body", None)
    elif result.get("status") == "Failed":                                  # the long-running operation failed
        err = result.get("error") if isinstance(result.get("error"), dict) else {}
        out.update(classify_http(400, json.dumps(err) if err else "", f"creating {name!r} in workspace {workspace}"))
    elif result.get("status") == "Timeout":
        out.update({"error": f"Fabric is still working on {name!r}; the operation did not finish in time.", "kind": "timeout",
                    "hint": "Check the item in the Fabric portal in a minute; re-running create_backend updates it in place."})
    return json.dumps(out, indent=2)


def _existing_api(workspace: str, name: str, headers: dict) -> tuple[str, dict] | None:
    """(workspace id, graphql-definition.json) of the API for GraphQL item with this name, or None."""
    try:
        workspace_id = _workspace_id(workspace, headers)
        api_id = _api_id(workspace_id, name, headers)
        return (workspace_id, _graphql_definition(workspace_id, api_id, headers)) if api_id else None
    except Exception:                                                      # noqa: BLE001 — the guard must never block a create
        return None


def _relationships_lost(found, name, p, source_id, source_type, writable, tables, confirmed) -> list[dict]:
    """Relationships the existing API of this name (`found`, from _existing_api) has that the update would drop. A new
    name, or an API whose definition cannot be read, gives [] so that creating still works as before."""
    if not found:
        return []
    workspace_id, existing = found
    d = _drift.compare(p, existing, name, workspace_id, source_id, source_type, writable=writable, tables=tables, confirmed=confirmed)
    return d.get("relationships_unsupported", [])


@mcp.tool(title="Generate Rayfin connector entities", annotations=RO)
@safe
def rayfin_connector(workspace: _p.Workspace, source: _p.Source, connector: _p.Connector = "data", schema: _p.Schema = "dbo",
                     keys: _p.Keys = None, confirmed: _p.Confirmed = None,
                     tables: _p.TablesOnly = None, relationships: _p.RayfinRelationships = True, ctx: Context = None) -> str:
    """Generates Rayfin (Fabric Apps) connector entity files and schema.ts from the plan, with keys and @one/@many
    relationships. Requires workspace and source. Returns JSON {path: file content}. Changes nothing in Fabric.
    Errors: {error, kind, hint}."""
    p, item, _ = _plan(workspace, source, schema, keys, confirmed, ctx)
    check_tables(p.schema, tables)
    st = {"Lakehouse": "SqlAnalyticsEndpoint", **{k: "SqlAnalyticsEndpoint" for k in ENDPOINT_ITEM_ROUTES}, "Warehouse": "Warehouse",
          "SQLDatabase": "SqlDbNative"}.get(item["type"], "SqlAnalyticsEndpoint")
    return json.dumps(rayfin_files(p, connector, st, tables=tables, relationships=relationships), indent=2)


def _source_inputs(workspace, source, schema, keys, confirmed, ctx):
    """Plan the source and collect what a definition needs from the item: ids, name, kind, SQL endpoint host, the
    database name the endpoint opens, and whether the lakehouse was created with schemas."""
    p, item, headers = _plan(workspace, source, schema, keys, confirmed, ctx)
    workspace_id = _workspace_id(workspace, headers)
    return p, dict(workspace_id=workspace_id, item_id=item.get("id", ""), item_name=item.get("displayName") or source,
                   item_kind=item.get("type", "Lakehouse"), schema=schema, sql_endpoint=item.get("sql_host") or "",
                   sql_db=item.get("sql_db") or item.get("displayName") or source,
                   schemas_enabled=item.get("schemas_enabled", item.get("type", "Lakehouse") != "Lakehouse"))


def _ontology_inputs(workspace, source, schema, keys, confirmed, ctx):
    """The subset ontology.envelope takes as keyword arguments."""
    p, info = _source_inputs(workspace, source, schema, keys, confirmed, ctx)
    return p, {k: info[k] for k in ("workspace_id", "item_id", "item_name", "item_kind", "schema", "sql_endpoint")}


@mcp.tool(title="Draft a Fabric IQ ontology from the plan (nothing deployed)", annotations=RO)
@safe
def ontology_draft(workspace: _p.Workspace, source: _p.Source, name: _p.OntologyDraftName = "ontology", schema: _p.Schema = "dbo", keys: _p.Keys = None,
                   confirmed: _p.Confirmed = None, tables: _p.TablesOnly = None, ctx: Context = None) -> str:
    """Drafts a Fabric IQ ontology (preview) from the plan: entity types with keys, relationship types and bindings.
    Requires workspace and source. Returns JSON with a summary (the rule behind each key and link), the binding
    checklist, a Turtle file for Import ontology and the item definition parts. Changes nothing; create_ontology
    creates the item. Errors: {error, kind, hint}."""
    p, args = _ontology_inputs(workspace, source, schema, keys, confirmed, ctx)
    check_tables(p.schema, tables)
    parts = _ontology.ontology_parts(p, name, tables=tables, **args)
    out = {
        "summary": _ontology.summary(p, tables),
        "bindings": _ontology.bindings(p, args["item_name"], schema, tables),
        "ttl": _ontology.ontology_ttl(p, name, schema, tables),
        "definition_parts": parts,
        "rest": {"method": "POST", "url": f"{FABRIC}/v1/workspaces/{args['workspace_id']}/ontologies",
                 "delegated_scope": "Item.ReadWrite.All", "body": _ontology.envelope(name, parts)},
        "note": "Ontology (preview): format follows the item's own definition as of 2026. Creating the item needs the "
                "Item.ReadWrite.All scope, which this connector asks for only when its operator enables create_ontology; the "
                "portal route (Import ontology with the TTL, then bind per `bindings`) needs no extra permission.",
    }
    text = json.dumps(out, indent=2)
    if len(text) <= MAX_RESULT_CHARS:
        return text
    # A big schema: keep what a person reads first. Drop the two copies of the definition, then the TTL if it still does
    # not fit; bindings are cut per list by _bounded. Narrowing with tables= or the CLI gives the whole thing.
    out.pop("definition_parts"); out["rest"].pop("body")
    dropped = [f"the definition ({len(parts)} parts)"]
    if len(json.dumps(out, indent=2)) > MAX_RESULT_CHARS:
        out.pop("ttl"); dropped.append("the TTL")
    out["omitted"] = (", ".join(dropped) + " did not fit in one answer and were left out; the summary is complete. "
                      "Narrow with tables=, or run `fabric-backend ontology` (CLI) for the files.")
    return _bounded(out, MAX_RESULT_CHARS)                 # may still cut the binding lists, and says so under `truncated`


@mcp.tool(title="Create or update a Fabric IQ ontology from the plan (dry run by default)", annotations=WRITE)
@safe
def create_ontology(workspace: _p.Workspace, source: _p.Source, name: _p.OntologyName, schema: _p.Schema = "dbo", keys: _p.Keys = None,
                    confirmed: _p.Confirmed = None, tables: _p.TablesOnly = None, dry_run: _p.DryRun = True,
                    ctx: Context = None) -> str:
    """Creates a Fabric IQ ontology (preview) item from the plan, or updates the item of that name in place. Requires
    workspace, source and name; the delegated permission Item.ReadWrite.All, Contributor on the workspace and a
    Fabric capacity. Returns JSON with the definition parts and the REST call; with dry_run=false also the result,
    or kind consent when the permission is missing. Changes Fabric only with dry_run=false: an update replaces the
    item's definition, so entity types not in the plan leave it; no item is deleted. Errors: {error, kind, hint}."""
    p, args = _ontology_inputs(workspace, source, schema, keys, confirmed, ctx)
    check_tables(p.schema, tables)
    parts = _ontology.ontology_parts(p, name, tables=tables, **args)
    body = _ontology.envelope(name, parts, description=f"Created by Krusgraph from {source} ({schema})")
    out = {"summary": _ontology.summary(p, tables), "dry_run": dry_run,
           "rest": {"method": "POST", "url": f"{FABRIC}/v1/workspaces/{args['workspace_id']}/ontologies",
                    "update": f"{FABRIC}/v1/workspaces/{args['workspace_id']}/ontologies/{{id}}/updateDefinition",
                    "delegated_scope": "Item.ReadWrite.All", "workspace_role": "Contributor", "parts": list(parts),
                    "spec": ("microsoft/fabric-rest-api-specs ontology/swagger.json: Items_CreateOntology and Items_UpdateOntologyDefinition, "
                             "long-running operations, item in preview; read 26 October 2026 (commit a96c37a)")},
           "after_creation": ["Open the ontology item in Fabric and review the entity types, keys and relationship types; keyless tables and composite keys are under summary.notes.",
                              "Check the data bindings per entity (the definition binds Direct Lake-style to the source item).",
                              "Fabric IQ's ontology agent and data agents can then use the ontology as context."],
           "note": ("Ontology (preview): the definition follows the generation-2 layout of the specification's example (model, database, namespaces, "
                    "entities, tables, relationships), checked against recorded definitions. " + _tool_status.answer_note("create_ontology"))}
    if dry_run:
        out["parts"] = parts
        text = json.dumps(out, indent=2)
        if len(text) > MAX_RESULT_CHARS:
            out["omitted"] = sorted(k for k in parts if k.startswith(("entities/", "tables/")))
            out["parts"] = {k: v for k, v in parts.items() if not k.startswith(("entities/", "tables/"))}
            text = json.dumps(out, indent=2)
        return text
    result = _create_ontology(body, args["workspace_id"], token_provider=lambda: auth.fabric(ctx))
    return _finish_create(out, result, "Item.ReadWrite.All", f"creating the ontology {name!r}")


# ------------------------------------------------------------------ consultant tools -------
# Thin wrappers: the work is in semantic_model.py, paths.py, dictionary.py, dbt.py and drift.py. All read-only.


def _api_id(workspace: str, api: str, headers: dict) -> str | None:
    if len(api) == 36 and api.count("-") == 4:
        return api
    item = find_item_by_name(workspace, api, headers, ("GraphQLApi",))
    return item["id"] if item else None


@mcp.tool(title="Draft a Power BI semantic model (TMDL, nothing created)", annotations=RO)
@safe
def semantic_model_draft(workspace: _p.Workspace, source: _p.Source, name: _p.ModelDraftName = "semantic_model", schema: _p.Schema = "dbo",
                         keys: _p.Keys = None, confirmed: _p.Confirmed = None,
                         tables: _p.TablesShown = None, ctx: Context = None) -> str:
    """Drafts the plan as a Power BI semantic model in TMDL (Direct Lake on the source's SQL analytics endpoint):
    relationships with cardinality and filter direction, one active path per table pair. Requires workspace and
    source. Returns JSON {path: content} for the definition folder plus README.generated.md listing the decisions to
    check. Changes nothing; create_semantic_model creates the item, compare_semantic_model checks an existing model.
    Errors: {error, kind, hint}."""
    p, info = _source_inputs(workspace, source, schema, keys, confirmed, ctx)
    keep = _compact.match_tables(p.schema, tables)
    tables = sorted(keep, key=str.lower) if keep is not None else None
    out = _semantic_model.draft(p, info, name, tables)
    out["note"] = ("Unit-tested against Microsoft's published TMDL samples. " + _tool_status.answer_note("semantic_model_draft")
                   + " An item from it is not yet created live (create_semantic_model). Open the "
                   "folder in Power BI Desktop (TMDL view) or create the item with the Fabric REST API; README.generated.md "
                   "lists what to check first.")
    text = json.dumps(out, indent=2)
    if len(text) > MAX_RESULT_CHARS:
        parts = out["parts"]
        out["omitted"] = sorted(k for k in parts if k.startswith("definition/tables/"))
        out["parts"] = {k: v for k, v in parts.items() if not k.startswith("definition/tables/")}
        out["note"] += " The table files were left out of this answer because of its size; pass `tables` to get a few at a time."
        text = json.dumps(out, indent=2)
        while len(text) > MAX_RESULT_CHARS and len(out["parts"]) > 1:            # then the largest remaining part, until it fits
            biggest = max(out["parts"], key=lambda k: len(out["parts"][k]))
            out["omitted"].append(biggest)
            del out["parts"][biggest]
            text = json.dumps(out, indent=2)
    return text if len(text) <= MAX_RESULT_CHARS else _bounded(out, MAX_RESULT_CHARS, "Pass tables=[\"pattern*\"] to get a few tables at a time.")


MODEL_READ_SCOPE = "SemanticModel.ReadWrite.All (or Item.ReadWrite.All)"
MODEL_READ_SPEC = ("fabric-rest-api-specs a96c37a semanticModel/swagger.json, Items_GetSemanticModelDefinition (format TMDL): delegated "
                   "scope SemanticModel.ReadWrite.All or Item.ReadWrite.All, read and write permission on the model. The read-only "
                   "alternative, the Power BI REST executeQueries (Dataset.Read.All, Read and Build), is documented as \"Only DAX queries are "
                   "supported at this time. MDX, INFO functions and DMV queries are not supported\" (Power BI REST reference, "
                   "microsoft/PowerBI-CSharp swagger 5.1.0), so no read-only REST path returns a model's relationships today; "
                   "docs/SCOPES.md has the comparison.")


@mcp.tool(title="Compare an existing Power BI semantic model with the plan", annotations=RO)
@safe
def compare_semantic_model(workspace: _p.Workspace, source: _p.Source, model: _p.CompareModel = "", schema: _p.Schema = "dbo", keys: _p.Keys = None,
                           confirmed: _p.Confirmed = None, check_data: _p.CheckData = False, max_items: _p.MaxItems = 60,
                           tmdl: _p.Tmdl = None, ctx: Context = None) -> str:
    """Compares an existing Power BI semantic model with the plan: missing, contradicted and extra relationships,
    cardinality, direction, active, stale columns, suggested measures. Requires workspace, source and model
    (SemanticModel.ReadWrite.All or Item.ReadWrite.All) or tmdl (no permission). Returns JSON with the differences and
    confirmed entries for extra links. Changes nothing. Errors: {error, kind, hint}."""
    from . import model_compare as _mc
    if not model and not tmdl:
        return json.dumps({"error": "Name the semantic model (`model`, its name or id), or pass its definition files as `tmdl`.",
                           "kind": "bad_input", "hint": "list_sources does not list models; the Fabric portal (or Microsoft's own Fabric "
                                                        "MCP servers) shows the semantic models in a workspace."}, indent=2)
    execute = None
    if check_data:
        s, execute = _connected(workspace, source, schema, ctx)
        p = make_plan(s, keys, confirmed)
        headers = _headers(ctx)
    else:
        p, _, headers = _plan(workspace, source, schema, keys, confirmed, ctx)
    try:
        workspace_id = _workspace_id(workspace, headers)
        meta = {"name": model or "(from tmdl)", "read_with": "TMDL files given in `tmdl`; no call to the model"}
        if tmdl:
            m = _mc.from_tmdl(dict(tmdl))
        else:
            item = {"id": model} if _GUID.match(model.strip()) else find_item_by_name(workspace_id, model, headers, ("SemanticModel",))
            if not item:
                return json.dumps({"error": f"no semantic model named {model!r} in workspace {workspace}", "kind": "not_found",
                                   "hint": "Check the name in the Fabric portal (the model's own name, not its report's), or pass its id."}, indent=2)
            meta = {"name": model, "id": item["id"], "read_with": "Fabric getDefinition (TMDL)", "delegated_scope": MODEL_READ_SCOPE,
                    "spec": MODEL_READ_SPEC}
            try:
                m = _mc.from_tmdl(_item_definition_parts(workspace_id, "semanticModels", item["id"], headers, fmt="TMDL"))
            except requests.HTTPError as e:
                status = int(getattr(e.response, "status_code", 0) or 0)
                if status in (401, 403):
                    return json.dumps({"error": f"Fabric refused reading the definition of {model!r} (HTTP {status}): reading a semantic "
                                                f"model's relationships needs the delegated permission {MODEL_READ_SCOPE} and write "
                                                "permission on the model.",
                                       "kind": "consent", "scope": MODEL_READ_SCOPE,
                                       "hint": "The operator adds the permission to the Entra app and an administrator consents (docs/SCOPES.md); "
                                               "it is the same one create_semantic_model needs. Meanwhile pass the model's TMDL files as `tmdl` "
                                               "(from a PBIP folder or the workspace's Git repository): that needs no permission."}, indent=2)
                raise
        validation = data = None
        if execute is not None:
            budget = max(1, min(int(max_items), 200))
            validation = _evidence.validate(p, execute, max_items=budget)
            used = len(validation["keys"]) + len(validation["relationships"])
            data = {}
            for mt, mc_, ot, oc in _mc.to_check(_mc.compare(p, m)):
                if used + 2 > budget:
                    break
                one = execute(_evidence.key_sql(p.schema.schema, ot, [oc]))[0]
                n, nulls, distinct = (int(one.get(k) or 0) for k in ("n", "nulls", "distinct_keys"))
                rel = execute(_evidence.relationship_sql(p.schema.schema, mt, [mc_], ot, [oc]))[0]
                wv, orph = int(rel.get("with_value") or 0), int(rel.get("orphans") or 0)
                data[f"{mt}.{mc_} -> {ot}.{oc}"] = {"one_side": {"verdict": _evidence.key_verdict(n, nulls, distinct)},
                                                   "orphans": {"orphans": orph, "verdict": _evidence.relationship_verdict(wv, orph)}}
                used += 2
    finally:
        if execute is not None:
            getattr(execute, "close", lambda: None)()
    out = _mc.compare(p, m, validation, data)
    out = {"summary": out.pop("summary"), "model": meta, **out}
    if validation is not None:
        out["validate_plan"] = validation["summary"]
    out["note"] = ("Unit-tested against a model fixture over the shop schema and Microsoft's sample PBIP model. "
                   + _tool_status.answer_note("compare_semantic_model") + " The comparison reads names and metadata only, no rows from the model.")
    return _bounded(out, MAX_RESULT_CHARS)


@mcp.tool(title="Shortest join path between two tables", annotations=RO)
@safe
def join_path(workspace: _p.Workspace, source: _p.Source, start: _p.Start, end: _p.End, schema: _p.Schema = "dbo",
              keys: _p.Keys = None, confirmed: _p.Confirmed = None, ctx: Context = None) -> str:
    """Finds the shortest chain of relationships between two tables. Requires workspace, source, start and end. Returns
    JSON with each hop and its rule, every equally short path and a T-SQL SELECT … JOIN; without a path, the missing
    relationship as a confirmed entry. Metadata only; changes nothing. answer_query_draft drafts a query for a whole
    question. Errors: {error, kind, hint}."""
    p, _, _ = _plan(workspace, source, schema, keys, confirmed, ctx)
    return json.dumps(_paths.join_path(p, start, end), indent=2)


@mcp.tool(title="Analyse the schema as a graph (roles, centrality, areas, ambiguity)", annotations=RO)
@safe
def analyze_schema(workspace: _p.Workspace, source: _p.Source, schema: _p.Schema = "dbo", keys: _p.Keys = None,
                   confirmed: _p.Confirmed = None, tables: _p.TablesShown = None, detail: _p.Detail = "auto",
                   ctx: Context = None) -> str:
    """Reads the plan as a graph: each table's role (fact, dimension, bridge, isolated), the most central tables, subject
    areas, cycles, table pairs with more than one path, and which relationships can be active together. Requires
    workspace and source. Returns JSON. Metadata only, no data queries; changes nothing. Errors: {error, kind,
    hint}."""
    p, _, _ = _plan(workspace, source, schema, keys, confirmed, ctx)
    keep = _compact.match_tables(p.schema, tables)
    out = _graphs.analyze(p)
    out["summary"] = p.summary().splitlines()[0] + "; " + out["summary"]
    if _compact.pick_detail(detail, len(keep) if keep is not None else len(p.schema)) == "summary":
        return _bounded(_compact.analysis_summary(out, keep), MAX_RESULT_CHARS, _compact.NARROW_HINT)
    return _bounded(_compact.analysis_filtered(out, keep), MAX_RESULT_CHARS, _compact.NARROW_HINT)


@mcp.tool(title="Suggest missing relationships, checked against the data", annotations=RO)
@safe
def suggest_relationships(workspace: _p.Workspace, source: _p.Source, schema: _p.Schema = "dbo", keys: _p.Keys = None,
                          confirmed: _p.Confirmed = None, check: _p.Check = 15, ctx: Context = None) -> str:
    """Finds columns that look like references to another table's key but are in no relationship, ranks them and counts the
    best against the data (share of values found, distinct values). Requires workspace and source. Returns JSON
    candidates, each with a confirmed entry for plan_backend or create_backend. Read-only counting queries; applies
    nothing. Errors: {error, kind, hint}."""
    s, execute = _connected(workspace, source, schema, ctx)
    try:
        p = make_plan(s, keys, confirmed)
        out = _graphs.suggest(p, execute, check=max(0, min(int(check), 100)))
    finally:
        getattr(execute, "close", lambda: None)()
    out["summary"] = p.summary().splitlines()[0] + f"; {len(out['candidates'])} candidate(s), {out['checked_against_data']} checked against the data"
    return json.dumps(out, indent=2, default=str)


@mcp.tool(title="Data dictionary in Markdown", annotations=RO)
@safe
def data_dictionary(workspace: _p.Workspace, source: _p.Source, schema: _p.Schema = "dbo", keys: _p.Keys = None,
                    confirmed: _p.Confirmed = None, validate: _p.Validate = False, max_items: _p.MaxItems = 60,
                    tables: _p.TablesShown = None, ctx: Context = None) -> str:
    """Writes hand-over documentation: tables, columns and types, keys and relationships with their rules, keyless tables,
    ambiguous columns, the ER diagram and an empty Description column. Requires workspace and source. Returns
    Markdown text, cut on a line above 60 000 characters. Changes nothing. Errors: {error, kind, hint}."""
    if validate:
        s, execute = _connected(workspace, source, schema, ctx)
        try:
            p = make_plan(s, keys, confirmed)
            checked = _evidence.validate(p, execute, max_items=max(1, min(int(max_items), 200)))
        finally:
            getattr(execute, "close", lambda: None)()
    else:
        p, _, _ = _plan(workspace, source, schema, keys, confirmed, ctx)
        checked = None
    keep = _compact.match_tables(p.schema, tables)
    md = _dictionary.data_dictionary(p, source, schema, checked, product=os.environ.get("PRODUCT_NAME", "Krusgraph"), tables=keep)
    return _compact.bounded_text({"path": f"docs/{source}-{schema}-data-dictionary.md", "markdown": md, "summary": p.summary()}, "markdown", MAX_RESULT_CHARS)


@mcp.tool(title="dbt schema.yml with source tests", annotations=RO)
@safe
def dbt_schema(workspace: _p.Workspace, source: _p.Source, schema: _p.Schema = "dbo", source_name: _p.SourceName = None,
               keys: _p.Keys = None, confirmed: _p.Confirmed = None,
               tables: _p.TablesShown = None, arguments_block: _p.ArgumentsBlock = True, ctx: Context = None) -> str:
    """Writes a dbt sources file: unique and not_null on key columns, relationships tests on single-column relationships,
    composite ones as comments. Requires workspace and source. Returns YAML text, cut above 60 000 characters.
    Changes nothing. Errors: {error, kind, hint}."""
    p, item, _ = _plan(workspace, source, schema, keys, confirmed, ctx)
    keep = _compact.match_tables(p.schema, tables)
    tables = sorted(keep, key=str.lower) if keep is not None else None
    src = source_name or schema
    yml = _dbt.schema_yml(p, src, schema, database=item.get("sql_db") or item.get("displayName") or source,
                         tables=tables, arguments_block=arguments_block)
    return _compact.bounded_text({"path": f"models/sources/{src}.yml", "yaml": yml, "summary": p.summary()}, "yaml", MAX_RESULT_CHARS)


@mcp.tool(title="Show which SAP tables and relationships the SAP pack recognises (nothing created)", annotations=RO)
@safe
def sap_pack_draft(workspace: _p.Workspace, source: _p.Source, schema: _p.SapSchema = "dbo", keys: _p.SapKeys = None,
                   confirmed: _p.SapConfirmed = None, variant: _p.SapVariant = None, export: _p.SapExport = "none",
                   ctx: Context = None) -> str:
    """Shows which tables of the source the SAP pack recognises (VBAK, VBAP, LIKP, VBRK, KNA1…, with or without a
    prefix such as sap_), their keys with MANDT, the order-to-cash relationships it applies with the public source of
    each, the ones it lists but does not apply (VBFA), missing pack tables and columns, and the traps (client, header
    vs item amounts, currency, leading zeros, partner functions). Requires workspace and source. Returns JSON, with
    the chosen export when export is not "none". Read-only; changes nothing. Errors: {error, kind, hint}."""
    p, _, _ = _plan(workspace, source, schema, keys, confirmed, ctx)
    return _bounded(_sap_pack.draft(p, source_name=schema, export=export, variant=variant), MAX_RESULT_CHARS, _compact.NARROW_HINT)


@mcp.tool(title="Compare today's plan with an existing GraphQL API", annotations=RO)
@safe
def plan_drift(workspace: _p.Workspace, source: _p.Source, api: _p.DriftApi, schema: _p.Schema = "dbo", keys: _p.Keys = None,
               confirmed: _p.Confirmed = None, tables: _p.TablesOnly = None, writable: _p.DriftWritable = False,
               ctx: Context = None) -> str:
    """Compares today's plan with an existing API for GraphQL item: new tables and columns, mapped columns the source no
    longer has, relationships the plan no longer supports, and whether create_backend with that name would change
    anything. Requires workspace, source and api. Returns JSON. Changes nothing; lineage shows what else builds on
    the tables. Errors: {error, kind, hint}."""
    p, item, headers = _plan(workspace, source, schema, keys, confirmed, ctx)
    check_tables(p.schema, tables)
    workspace_id = _workspace_id(workspace, headers)
    api_id = _api_id(workspace_id, api, headers)
    if not api_id:
        return json.dumps({"error": f"no API for GraphQL named {api!r} in workspace {workspace}", "kind": "not_found",
                           "hint": "list_sources lists the GraphQL APIs in a workspace."}, indent=2)
    existing = _graphql_definition(workspace_id, api_id, headers)
    source_id, source_type = source_for(workspace_id, item, headers)
    out = _drift.compare(p, existing, api, workspace_id, source_id, source_type, writable=writable, tables=tables, confirmed=confirmed)
    touched = sorted({str(x["table"]).split(".")[-1] for x in out.get("tables_gone", []) + out.get("removed_columns", [])})
    if touched:
        edges, skipped = _lineage_edges(workspace_id, item, schema, set(touched) | {t.name for t in p.schema}, headers, execute=None)
        out["impact"] = _lineage.impact_of_changes(edges, touched)
        out["impact_note"] = ("objects in the workspace that use the tables a re-run would drop columns from or lose; read from the "
                              "objects' definitions (views not included here, see lineage)" + (f"; {len(skipped)} item(s) could not be read" if skipped else ""))
    return json.dumps(out, indent=2)


# ------------------------------------------------------------------ creating tools ---------
# Same pattern as create_backend: create or update in place under a name, never delete, dry_run first.

# Write tools can replace an existing definition (a model, a view, an agent) in place, so Claude asks before each call.


# Fabric's own errorCode decides what a 401/403 from a create call means. Codes from Microsoft's Fabric REST
# documentation: InsufficientScopes (the token lacks a delegated scope; learn.microsoft.com/rest/api/fabric/articles/scopes),
# InsufficientPrivileges (the account's workspace role is too low; the error responses of the item APIs in
# learn.microsoft.com/rest/api/fabric/core/items), WorkspaceNotOnCapacity / CapacityNotActive (capacity, as errors.py
# already reads them). A feature turned off in the tenant's settings (an item type in preview, such as the ontology):
# FeatureNotAvailable, the code Fabric answered create_ontology with on 28 October 2026; other codes for it are
# recognised by their words. Anything else is reported as unknown, with the code.
_SCOPE_CODES = {"InsufficientScopes"}
_FEATURE_CODES = {"FeatureNotAvailable"}
_ROLE_CODES = {"InsufficientPrivileges"}
_FEATURE_WORDS = re.compile(r"(?i)tenant|feature|not enabled|disabled|turned off|preview|admin(?:istrator)? setting")
_CAPACITY_WORDS = re.compile(r"(?i)capacity")


def _consent(result: dict, scope: str, where: str) -> dict | None:
    """A 401/403 from a create call, told apart by Fabric's errorCode and message: a scope missing from the token
    (kind consent, the only case that says consent), a workspace role (no_access), a feature off in the tenant or no
    capacity (feature_disabled / capacity), an expired sign-in (sign_in), or a code this server does not know
    (fabric_refused, with the code). Fabric's own errorCode and message are always in the answer."""
    http = result.get("http")
    if http not in (401, 403):
        return None
    code, msg = _fabric_body(str(result.get("body", "")))
    said = {"fabric_error_code": code or None, "fabric_message": msg or None}
    quoted = f" Fabric said: {code or '(no errorCode)'}{(': ' + msg) if msg else ''}."
    if code in _SCOPE_CODES:
        return {**said, "error": f"Fabric refused {where} (HTTP {http}, {code}): the token does not carry the delegated permission this needs.",
                "kind": "consent", "scope": scope,
                "hint": f"The Entra app needs the delegated permission {scope} and an administrator's consent, then sign in again. "
                        "docs/SCOPES.md in the repository lists the exact az commands."}
    if code in _ROLE_CODES:
        return {**said, "error": f"Fabric refused {where} (HTTP {http}, {code}): the signed-in account's role in the workspace is not enough.",
                "kind": "no_access",
                "hint": "Ask a workspace admin for Contributor (or Member/Admin) on the workspace, then try again. The token's permissions are not the problem."}
    if code in ("WorkspaceNotOnCapacity", "CapacityNotActive") or _CAPACITY_WORDS.search(f"{code} {msg}"):
        return {**said, "error": f"Fabric refused {where} (HTTP {http}): the workspace has no active capacity for it.{quoted}",
                "kind": "capacity", "hint": HINTS["capacity"]}
    if code in _FEATURE_CODES or _FEATURE_WORDS.search(f"{code} {msg}"):
        return {**said, "error": f"Fabric refused {where} (HTTP {http}): the feature looks turned off in the tenant's settings.{quoted}",
                "kind": "feature_disabled",
                "hint": "A Fabric administrator enables the item type in the admin portal's tenant settings (items in preview are "
                        "often off by default), for the whole organisation or a security group the user is in. The token's permissions are not the problem."}
    if http == 401 and code in ("", "Unauthorized", "TokenExpired"):
        return {**said, **classify_http(401, str(result.get("body", "")), where)}
    return {**said, "error": f"Fabric refused {where} (HTTP {http}) with an error code this server does not know: {code or '(none)'}.{quoted}",
            "kind": "fabric_refused",
            "hint": "The cause is unknown here: it may be a missing permission in the token, the workspace role, or a tenant setting. "
                    f"Check that the token has {scope}, that the account is Contributor on the workspace, and the tenant settings for this item type."}


def _finish_create(out: dict, result: dict, scope: str, where: str) -> str:
    out["result"] = {k: v for k, v in result.items() if k != "body"}
    if result.get("status") != "Succeeded":
        consent = _consent(result, scope, where)
        if consent:
            out.update(consent)
        elif result.get("http"):
            out.update(classify_http(int(result["http"]), result.get("body", ""), where))
        elif result.get("status") == "Timeout":
            out.update({"error": f"Fabric is still working on {where}; the operation did not finish in time.", "kind": "timeout",
                        "hint": "Check the item in the Fabric portal in a minute; running the tool again updates it in place."})
        else:
            err = result.get("error") if isinstance(result.get("error"), dict) else {}
            out.update(classify_http(400, json.dumps(err) if err else "", where))
    return json.dumps(out, indent=2, default=str)


@mcp.tool(title="Create or update a Power BI semantic model (dry run by default)", annotations=WRITE)
@safe
def create_semantic_model(workspace: _p.Workspace, source: _p.Source, name: _p.ModelName, schema: _p.Schema = "dbo", keys: _p.Keys = None,
                          confirmed: _p.Confirmed = None, tables: _p.TablesOnly = None, dry_run: _p.DryRun = True,
                          ctx: Context = None) -> str:
    """Creates a Fabric semantic model item from semantic_model_draft's TMDL (Direct Lake), or updates the item of that
    name in place. Requires workspace, source and name; SemanticModel.ReadWrite.All or Item.ReadWrite.All and
    Contributor on the workspace. Returns JSON with the parts and the REST call; with dry_run=false also the result,
    or kind consent. Changes Fabric only with dry_run=false: an update replaces the model's definition, so tables,
    relationships and measures added outside the plan leave it; no item is deleted. Errors: {error, kind, hint}."""
    p, info = _source_inputs(workspace, source, schema, keys, confirmed, ctx)
    check_tables(p.schema, tables)
    draft = _semantic_model.draft(p, info, name, tables)
    body = _semantic_model.envelope(draft["parts"], name, description=f"Created by Krusgraph from {source} ({schema})")
    out = {"summary": draft["summary"], "dry_run": dry_run,
           "rest": {"method": "POST", "url": f"{FABRIC}/v1/workspaces/{info['workspace_id']}/semanticModels",
                    "update": f"{FABRIC}/v1/workspaces/{info['workspace_id']}/semanticModels/{{id}}/updateDefinition",
                    "delegated_scope": "SemanticModel.ReadWrite.All or Item.ReadWrite.All", "parts": [x["path"] for x in body["definition"]["parts"]]},
           "after_creation": ["Refresh the model once (framing) so its Direct Lake tables are processed; until then queries fall back or fail.",
                              "If the portal asks for credentials on the SQL analytics endpoint connection, set them under the model's settings (OAuth2 with your account).",
                              "Open the model in the portal or Power BI Desktop and check the relationships README.generated.md lists as inactive."],
           "note": "Unit-tested against Microsoft's sample definitions. " + _tool_status.answer_note("create_semantic_model")
                   + " Without the permission the create answers kind=consent naming it, see docs/SCOPES.md."}
    if dry_run:
        out["parts"] = draft["parts"]
        out["rest"]["body_preview"] = {"displayName": body["displayName"], "definition": {"format": "TMDL", "parts": "<base64 parts, see parts>"}}
        text = json.dumps(out, indent=2)
        if len(text) > MAX_RESULT_CHARS:
            out["omitted"] = sorted(k for k in draft["parts"] if k.startswith("definition/tables/"))
            out["parts"] = {k: v for k, v in draft["parts"].items() if not k.startswith("definition/tables/")}
            text = json.dumps(out, indent=2)
        return text
    result = _create_semantic_model(body, info["workspace_id"], token_provider=lambda: auth.fabric(ctx))
    return _finish_create(out, result, "SemanticModel.ReadWrite.All (or Item.ReadWrite.All)", f"creating the semantic model {name!r}")


@mcp.tool(title="Create or alter T-SQL views in a schema of their own (dry run by default)", annotations=WRITE)
@safe
def create_views(workspace: _p.Workspace, source: _p.Source, schema: _p.Schema = "dbo", views_schema: _p.ViewsSchema = "krusgraph",
                 keys: _p.Keys = None, confirmed: _p.Confirmed = None, dry_run: _p.DryRun = True,
                 ctx: Context = None) -> str:
    """Creates or alters wide T-SQL views over the plan on the source's SQL analytics endpoint or warehouse: one per fact
    table with its dimensions, one per header table. Requires workspace and source; rights to create objects
    (Contributor is enough). Returns JSON with the SQL; with dry_run=false also what ran. Changes Fabric only with
    dry_run=false and only in views_schema: CREATE OR ALTER replaces views of the same name; nothing is dropped.
    Errors: {error, kind, hint}."""
    s, execute = _connected(workspace, source, schema, ctx)
    try:
        p = make_plan(s, keys, confirmed)
        stmts = _views.statements(p, views_schema)
        out = {"summary": p.summary(), "schema": views_schema, "dry_run": dry_run, "schema_sql": stmts["schema_sql"], "views": stmts["views"],
               "note": "Views are allowed on a lakehouse SQL analytics endpoint, a warehouse and the endpoints of mirrored and SQL "
                       "database items (read-only data, writable T-SQL objects). Unit-tested on SQLite and against the shop schema. "
                       + _tool_status.answer_note("create_views")}
        if dry_run or not stmts["views"]:
            if not stmts["views"]:
                out["note"] = "No fact table (two or more references out, none in) and no hard-to-read relationship in the plan: nothing to create. " + out["note"]
            return json.dumps(out, indent=2)
        run = getattr(execute, "statement", None) or execute
        out["applied"] = []
        try:
            _views.apply(stmts, run, out["applied"])
            out["result"] = {"status": "Succeeded", "views": len(stmts["views"]), "schema": views_schema}
        except Exception as e:  # noqa: BLE001 — explained, with the fallback the docs leave
            from .errors import explain
            out.update(explain(e, f"creating views in schema {views_schema!r} on {source!r}"))
            out["hint"] = (out.get("hint", "") + " If this endpoint refuses CREATE VIEW (a mirrored or SQL database endpoint, or missing rights), "
                           "create the views in a warehouse in the same workspace instead: the SQL is unchanged.").strip()
        return json.dumps(out, indent=2, default=str)
    finally:
        getattr(execute, "close", lambda: None)()


@mcp.tool(title="Create or update a Fabric data agent from the plan (dry run by default)", annotations=WRITE)
@safe
def create_data_agent(workspace: _p.Workspace, source: _p.Source, name: _p.AgentName, schema: _p.Schema = "dbo", keys: _p.Keys = None,
                      confirmed: _p.Confirmed = None, publish: _p.Publish = True, show_personal_data: _p.ShowPersonalData = False,
                      dry_run: _p.DryRun = True, ctx: Context = None) -> str:
    """Creates a Fabric data agent over the source, with the plan as its instructions, the plan's tables selected and 5–10
    example question/T-SQL pairs, or updates the agent of that name in place. Requires workspace, source and name;
    Item.ReadWrite.All or DataAgent.ReadWrite.All. Returns JSON with the instructions, examples and REST calls; with
    dry_run=false also the result, or kind consent. Changes Fabric only with dry_run=false: instructions, data
    source and examples are replaced; nothing is deleted. Errors: {error, kind, hint}."""
    from . import privacy as _privacy
    p, info = _source_inputs(workspace, source, schema, keys, confirmed, ctx)
    spec = _data_agent.draft(p, info, name, schema, show_personal_data)
    out = {"summary": p.summary(), "dry_run": dry_run, "agent": {k: spec[k] for k in ("name", "instructions", "datasource", "datasource_instructions", "tables_to_select", "fewshots")},
           "rest": spec["rest"], "delegated_scope": spec["delegated_scope"],
           "note": "Unit-tested with the REST calls mocked. " + _tool_status.answer_note("create_data_agent") + " Without the permission the create "
                   "answers kind=consent naming it, see docs/SCOPES.md. The portal shows the agent's data source, "
                   "selected tables and example queries under its staging configuration; publish makes them live."}
    flagged = spec["personal_left_out"] or ([] if not show_personal_data else _privacy.findings(_privacy.personal_columns(p.schema)))
    if spec["personal_left_out"]:
        out["personal_data"] = {"left_out": [f"{x['table']}.{x['column']} ({x['rule']}: {x['what']})" for x in flagged],
                                "notice": "left out of the instructions and the examples by name (privacy rules); the key stands in. "
                                          f"{_privacy.PARAMETER}=true includes them."}
    elif flagged:
        out["personal_data"] = {"included": [f"{x['table']}.{x['column']} ({x['rule']}: {x['what']})" for x in flagged],
                                "notice": _privacy.notice(flagged, shown=True)}
    if dry_run:
        return json.dumps(out, indent=2)
    headers = _headers(ctx)
    try:
        result = _data_agent.apply(spec, info["workspace_id"], headers, publish=publish)
    except _data_agent.RestError as e:
        result = {"status": "Failed", "http": e.status, "body": e.body, "step": e.what}
    return _finish_create(out, result, "Item.ReadWrite.All (or DataAgent.ReadWrite.All)", f"creating the data agent {name!r}")


# ------------------------------------------------------------------ notebooks ----------------
# From understanding to building: notebooks generated from the plan (silver.py, monitor.py; format in notebook.py).

NOTEBOOK_SCOPE = "Notebook.ReadWrite.All (or Item.ReadWrite.All)"
NOTEBOOK_SPEC = ("microsoft/fabric-rest-api-specs notebook/swagger.json: Items_CreateNotebook and Items_UpdateNotebookDefinition, "
                 "long-running, delegated scope Notebook.ReadWrite.All or Item.ReadWrite.All, Contributor on the workspace; "
                 "definition format fabricGitSource (notebook/definitions.json); read 26 October 2026 (commit a96c37a)")


def _lakehouse_only(info: dict, tool: str) -> str | None:
    if info.get("item_kind") == "Lakehouse":
        return None
    return json.dumps({"error": f"{tool} writes Delta tables with Spark, which needs a lakehouse; {info.get('item_name')!r} is a "
                                f"{info.get('item_kind')}.", "kind": "unsupported",
                       "hint": "Add the tables to a lakehouse as OneLake shortcuts (Get data -> New shortcut) and plan that lakehouse; "
                               "the notebook then reads them through the shortcuts and writes the silver tables beside them."}, indent=2)


def _silver(workspace, source, schema, silver_schema, order_by, keys, confirmed, tables, ctx, show_personal_data=False):
    from . import silver as _silver_mod
    p, info = _source_inputs(workspace, source, schema, keys, confirmed, ctx)
    refusal = _lakehouse_only(info, "The silver notebook")
    if refusal:
        return None, None, None, refusal
    spec = _silver_mod.spec(p, info, silver_schema, order_by, tables, show_personal_data)
    return p, info, spec, None


def _silver_answer(p, info, spec, name: str, tool: str = "silver_notebook_draft") -> dict:
    from . import silver as _silver_mod
    text = _silver_mod.notebook_source(spec)
    target = f"schema {spec['silver_schema']}" if spec["source"]["schemas_enabled"] else f"tables prefixed {spec['silver_schema']}_"
    out = {"summary": p.summary().splitlines()[0] + f"; the notebook writes {len(spec['tables'])} silver table(s) to {target} "
                      f"in {info['item_name']}, and {_silver_mod.QUARANTINE}; the source tables are only read",
           "steps": _silver_mod.steps(spec), "not_checked": spec["not_checked"],
           **({"personal_data": {"columns": spec["personal"], "quarantine_masked": spec["mask_personal_data"],
                                 "note": "The silver tables keep every column; rows put in quarantine keep these columns as *** while the "
                                         "notebook's MASK_PERSONAL_DATA is True (show_personal_data=true sets it to False)."}} if spec["personal"] else {}),
           "notebook": {"name": name, "path": "notebook-content.py", "format": "fabricGitSource", "content": text},
           "run": ["Open the notebook in Fabric (it is attached to the lakehouse) and Run all, or add it to a pipeline or a schedule.",
                   f"Afterwards: {_silver_mod.QUARANTINE} lists every row left out with its table, rule and reason.",
                   "Run it again whenever the source changes: every silver table is rewritten from the source."],
           "note": ("Unit-tested: the steps run in Python on the shop seed with duplicates and broken references added, and the generated "
                    "notebook ran on a local PySpark 4.0.1 session against the same rows with the same result (26 October 2026); the notebook "
                    "has not run in a Fabric workspace. " + _tool_status.answer_note(tool))}
    if len(json.dumps(out)) > MAX_RESULT_CHARS:
        out["notebook"].pop("content")
        out["notebook"]["omitted"] = (f"the notebook ({len(text)} characters) did not fit in one answer; pass tables=[...] for a few at a "
                                      "time, or create it with create_silver_notebook, which sends the whole notebook to Fabric")
    return out


@mcp.tool(title="Draft a PySpark notebook that builds silver tables (nothing created)", annotations=RO)
@safe
def silver_notebook_draft(workspace: _p.Workspace, source: _p.Source, schema: _p.Schema = "dbo", silver_schema: _p.SilverSchema = "silver",
                          order_by: _p.OrderBy = None, keys: _p.Keys = None,
                          confirmed: _p.Confirmed = None, tables: _p.TablesOnly = None, show_personal_data: _p.ShowPersonalData = False,
                          ctx: Context = None) -> str:
    """Drafts a PySpark notebook writing de-duplicated silver Delta tables: one row per key, references checked, broken
    rows to krusgraph_quarantine. Requires workspace and a lakehouse source. Returns JSON with the steps and the
    notebook source. Changes nothing. Errors: {error, kind, hint}."""
    p, info, spec, refusal = _silver(workspace, source, schema, silver_schema, order_by, keys, confirmed, tables, ctx, show_personal_data)
    if refusal:
        return refusal
    return json.dumps(_silver_answer(p, info, spec, f"silver_{schema}"), indent=2)


@mcp.tool(title="Create or update the silver-tables notebook in Fabric (dry run by default)", annotations=WRITE)
@safe
def create_silver_notebook(workspace: _p.Workspace, source: _p.Source, name: _p.SilverName, schema: _p.Schema = "dbo", silver_schema: _p.SilverSchema = "silver",
                           order_by: _p.OrderBy = None, keys: _p.Keys = None,
                           confirmed: _p.Confirmed = None, tables: _p.TablesOnly = None, show_personal_data: _p.ShowPersonalData = False,
                           dry_run: _p.DryRun = True, ctx: Context = None) -> str:
    """Creates a Fabric notebook item with silver_notebook_draft's notebook, attached to the lakehouse, or updates the
    notebook of that name in place. Requires workspace, a lakehouse source and name; Notebook.ReadWrite.All or
    Item.ReadWrite.All and Contributor. Returns JSON with the notebook and the REST call; with dry_run=false also
    the result, or kind consent. Changes Fabric only with dry_run=false: the notebook's content is replaced, no item
    is deleted, and nothing runs; when run, it writes only in silver_schema. Errors: {error, kind, hint}."""
    from . import notebook as _notebook
    from .deploy import create_item_with_definition
    p, info, spec, refusal = _silver(workspace, source, schema, silver_schema, order_by, keys, confirmed, tables, ctx, show_personal_data)
    if refusal:
        return refusal
    out = _silver_answer(p, info, spec, name, "create_silver_notebook")
    out["dry_run"] = dry_run
    out["rest"] = {"method": "POST", "url": f"{FABRIC}/v1/workspaces/{info['workspace_id']}/notebooks",
                   "update": f"{FABRIC}/v1/workspaces/{info['workspace_id']}/notebooks/{{id}}/updateDefinition",
                   "delegated_scope": NOTEBOOK_SCOPE, "workspace_role": "Contributor", "parts": ["notebook-content.py", ".platform"],
                   "spec": NOTEBOOK_SPEC}
    if dry_run:
        return json.dumps(out, indent=2)
    from . import silver as _silver_mod
    body = _notebook.envelope(name, _silver_mod.notebook_source(spec), f"Silver tables for {info['item_name']}.{schema}, generated by Krusgraph from the plan")
    out.get("notebook", {}).pop("content", None)                                  # sent to Fabric; the answer keeps the steps
    result = create_item_with_definition("notebooks", "Notebook", body, info["workspace_id"], token_provider=lambda: auth.fabric(ctx))
    return _finish_create(out, result, NOTEBOOK_SCOPE, f"creating the notebook {name!r}")


MLV_REFRESH = {"run_now": "POST /v1/workspaces/{workspaceId}/lakehouses/{lakehouseId}/jobs/refreshMaterializedLakeViews/instances",
               "run_now_scope": "Lakehouse.Execute.All or Item.Execute.All",
               "schedule": "POST /v1/workspaces/{workspaceId}/lakehouses/{lakehouseId}/jobs/refreshMaterializedLakeViews/schedules",
               "schedule_scope": "(Lakehouse.Execute.All or Item.Execute.All) and (Lakehouse.ReadWrite.All or Item.ReadWrite.All)",
               "portal": "Lakehouse -> Materialized lake views -> Manage -> Manage schedules -> New schedule",
               "spec": "fabric-rest-api-specs a96c37a lakehouse/swagger.json (one active refresh schedule per lineage, at most 20 per lakehouse); "
                       "MicrosoftDocs/fabric-docs a2de7f9 data-engineering/materialized-lake-views/schedule-lineage-run.md"}


def _gold(workspace, source, schema, silver_schema, gold_schema, keys, confirmed, tables, show_personal_data, ctx):
    from . import gold as _gold_mod
    p, info = _source_inputs(workspace, source, schema, keys, confirmed, ctx)
    refusal = _lakehouse_only(info, "The gold views")
    if refusal:
        return None, None, None, refusal
    if not info.get("schemas_enabled"):
        return None, None, None, json.dumps({
            "error": f"materialized lake views need a lakehouse created with schemas; {info.get('item_name')!r} has none.",
            "kind": "unsupported",
            "hint": "Create a lakehouse with Lakehouse schemas, add the tables to it as shortcuts and plan that lakehouse; or use create_views "
                    "for T-SQL views on the SQL analytics endpoint, which needs no schemas."}, indent=2)
    spec = _gold_mod.spec(p, info, silver_schema, gold_schema, tables, show_personal_data)
    return p, info, spec, None


def _gold_answer(p, info, spec, name: str, tool: str = "gold_views_draft") -> dict:
    from . import gold as _gold_mod, privacy as _privacy
    text = _gold_mod.notebook_source(spec)
    statements = _gold_mod.statements(spec)
    out = {"summary": p.summary().splitlines()[0] + f"; {len(spec['views'])} materialized lake view(s) in {spec['gold_schema']} over the "
                      f"silver tables in {spec['silver_schema']} of {info['item_name']}; source and silver tables are only read",
           "views": statements, "notebook": {"name": name, "path": "notebook-content.py", "format": "fabricGitSource", "content": text},
           "run": ["Run create_silver_notebook's notebook first: the gold views read its silver tables.",
                   "Open this notebook in Fabric (it is attached to the lakehouse, Fabric Runtime 1.3) and Run all; each cell creates or replaces "
                   "one view, after a guard that stops before any table it did not create.",
                   "Schedule the refresh in the lakehouse (Manage materialized lake views -> Manage schedules); the lineage view shows the "
                   "rows each rule dropped."],
           "refresh": MLV_REFRESH,
           "status": ("Materialized lake views are generally available (September 2026, fabric-docs whats-new.md); the data quality "
                      "constraints, optimal refresh and time-based schedules used here carry no preview label. REFRESH_HINT, event-triggered "
                      "schedules and the PySpark authoring API are preview and not used."),
           "note": ("Unit-tested: the SQL of every view runs as a SELECT with its rules on SQLite and on a local PySpark 4.0.1 over the silver "
                    "tables of the shop seed (open-source Spark has no CREATE MATERIALIZED LAKE VIEW, so the CREATE itself is checked against "
                    "the documented syntax); the views have not been created in a Fabric workspace. " + _tool_status.answer_note(tool))}
    pd = spec["personal_data"]
    if pd["omitted"] or pd["kept_for_joins"] or pd["shown"] and pd["flagged"]:
        notice = _privacy.notice(pd["flagged"], pd["shown"]) if pd["shown"] else (
            ("Left out of the views because the column name looks like personal data: "
             + ", ".join(sorted({f"{o['table']}.{o['column']} ({o['rule']})" for o in pd["omitted"]}))
             + f". Ask again with {_privacy.PARAMETER}=true to include them." if pd["omitted"] else "")
            + (" Kept although the name looks like personal data, because a view joins on it or it is a key: "
               + ", ".join(sorted({f"{k['table']}.{k['column']} ({k['rule']})" for k in pd["kept_for_joins"]})) + "." if pd["kept_for_joins"] else ""))
        out["personal_data"] = {"omitted": pd["omitted"], "kept_for_joins": pd["kept_for_joins"], "notice": notice.strip()}
    if len(json.dumps(out)) > MAX_RESULT_CHARS:
        out["notebook"].pop("content")
        out["notebook"]["omitted"] = (f"the notebook ({len(text)} characters) did not fit in one answer; the views' SQL is above, and "
                                      "create_gold_views sends the whole notebook to Fabric")
    return out


@mcp.tool(title="Draft gold views as materialized lake views (nothing created)", annotations=RO)
@safe
def gold_views_draft(workspace: _p.Workspace, source: _p.Source, schema: _p.Schema = "dbo", silver_schema: _p.SilverSchema = "silver", gold_schema: _p.GoldSchema = "gold",
                     keys: _p.Keys = None, confirmed: _p.Confirmed = None, tables: _p.TablesOnly = None,
                     show_personal_data: _p.ShowPersonalData = False, ctx: Context = None) -> str:
    """Drafts materialized lake views (Spark SQL) over the silver tables: one wide view per fact table in gold_schema,
    dimensions joined over many-to-one paths, the plan's keys and relationships as CHECK rules. Requires workspace
    and a lakehouse with schemas. Returns JSON with the SQL per view and the notebook that creates them. Changes
    nothing; create_gold_views creates the notebook. Errors: {error, kind, hint}."""
    p, info, spec, refusal = _gold(workspace, source, schema, silver_schema, gold_schema, keys, confirmed, tables, show_personal_data, ctx)
    if refusal:
        return refusal
    return _bounded(_gold_answer(p, info, spec, f"gold_{schema}"), MAX_RESULT_CHARS)


@mcp.tool(title="Create or update the gold-views notebook in Fabric (dry run by default)", annotations=WRITE)
@safe
def create_gold_views(workspace: _p.Workspace, source: _p.Source, name: _p.GoldName, schema: _p.Schema = "dbo", silver_schema: _p.SilverSchema = "silver", gold_schema: _p.GoldSchema = "gold",
                      keys: _p.Keys = None, confirmed: _p.Confirmed = None, tables: _p.TablesOnly = None,
                      show_personal_data: _p.ShowPersonalData = False, dry_run: _p.DryRun = True, ctx: Context = None) -> str:
    """Creates a Fabric notebook item with gold_views_draft's notebook, or updates the notebook of that name in place.
    Requires workspace, a lakehouse source with schemas and name; Notebook.ReadWrite.All or Item.ReadWrite.All and
    Contributor. Returns JSON with the views, the notebook and the REST call; with dry_run=false also the result.
    Changes Fabric only with dry_run=false: the notebook's content is replaced, no item is deleted, and nothing
    runs; when run, it stops before writing over a table it did not create. Errors: {error, kind, hint}."""
    from . import notebook as _notebook, gold as _gold_mod
    from .deploy import create_item_with_definition
    p, info, spec, refusal = _gold(workspace, source, schema, silver_schema, gold_schema, keys, confirmed, tables, show_personal_data, ctx)
    if refusal:
        return refusal
    out = _gold_answer(p, info, spec, name, "create_gold_views")
    out["dry_run"] = dry_run
    out["rest"] = {"method": "POST", "url": f"{FABRIC}/v1/workspaces/{info['workspace_id']}/notebooks",
                   "update": f"{FABRIC}/v1/workspaces/{info['workspace_id']}/notebooks/{{id}}/updateDefinition",
                   "delegated_scope": NOTEBOOK_SCOPE, "workspace_role": "Contributor", "parts": ["notebook-content.py", ".platform"],
                   "spec": NOTEBOOK_SPEC}
    if dry_run:
        return _bounded(out, MAX_RESULT_CHARS)
    body = _notebook.envelope(name, _gold_mod.notebook_source(spec), f"Gold views for {info['item_name']}.{schema}, generated by Krusgraph from the plan")
    out.get("notebook", {}).pop("content", None)
    result = create_item_with_definition("notebooks", "Notebook", body, info["workspace_id"], token_provider=lambda: auth.fabric(ctx))
    return _finish_create(out, result, NOTEBOOK_SCOPE, f"creating the notebook {name!r}")


PIPELINE_SCOPE = "DataPipeline.ReadWrite.All (or Item.ReadWrite.All)"
SCHEDULE_SCOPE = "DataPipeline.Execute.All (or Item.Execute.All) together with DataPipeline.ReadWrite.All (or Item.ReadWrite.All)"


def _monitor_inputs(workspace, source, schema, ctx):
    p, info = _source_inputs(workspace, source, schema, None, None, ctx)
    refusal = _lakehouse_only(info, "The drift monitor")
    if refusal:
        return None, None, refusal
    source_id, source_type = source_for(info["workspace_id"], {"type": info["item_kind"], "id": info["item_id"]}, _headers(ctx))
    src = {k: info[k] for k in ("workspace_id", "item_id", "item_name", "schema", "schemas_enabled", "sql_db")}
    src.update(source_id=source_id, source_type=source_type)
    return p, src, None


def _check_at(at: str) -> None:
    import re as _re
    if not _re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", at or ""):
        from .infer import PlanInputError
        raise PlanInputError("at: the time of day as hh:mm, for example 02:00")


def _step_failed(out: dict, step: str, result: dict, scope: str, where: str) -> str:
    """One step of a several-item create failed: the steps before it stay in `result`, the error says which scope or
    what Fabric answered (the same mapping as _finish_create)."""
    answer = json.loads(_finish_create({}, result, scope, where))
    answer.pop("result", None)
    out.update(answer)
    out["result"][step] = {k: v for k, v in result.items() if k != "body"}
    return json.dumps(out, indent=2, default=str)


def _monitor_answer(p, src: dict, name: str, at: str, time_zone: str, library_ref: str | None, tool: str = "drift_monitor_draft") -> dict:
    from . import monitor as _monitor, notebook as _notebook
    label = f"{src['item_name']}.{src['schema']}"
    text = _notebook.fabric_source(_monitor.notebook_cells(src, library_ref),
                                   _notebook.notebook_metadata(src["workspace_id"], src["item_id"], src["item_name"]))
    first = _monitor.summary_text(label, _monitor.diff(None, _monitor.snapshot(p)))
    return {"summary": p.summary().splitlines()[0] + f"; every night at {at} ({time_zone}) the monitor compares {label}'s plan with "
                       "the last saved one and sends the changes to the webhook set on the pipeline",
            "notebook": {"name": name, "path": "notebook-content.py", "format": "fabricGitSource", "content": text},
            "pipeline": {"name": f"{name}_nightly", "path": "pipeline-content.json",
                         "content": _monitor.pipeline_content("<the notebook's id, filled in when it is created>", src["workspace_id"], label)},
            "schedule": _monitor.schedule_body(at, time_zone),
            "plans_table": _monitor.plans_table(bool(src["schemas_enabled"])).replace("`", ""),
            "message_example": _monitor.teams_message(*first),
            "set_up_in_fabric": ["Open the pipeline, Parameters: set webhook_url's default value to a Teams workflow webhook "
                                 "(\"When a Teams webhook request is received\") or a Power Automate HTTP trigger that sends an e-mail.",
                                 "Open the Notebook activity once and check its Connection: if Fabric asks for one, choose your account or the "
                                 "workspace identity; the run reads the workspace's items with that identity.",
                                 "Run the pipeline once by hand: the first run saves the baseline plan and reports 'first run'."],
            "note": ("Unit-tested: the comparison, the message and the generated notebook and pipeline on the shop schema; the notebook "
                     "has not run in a Fabric workspace. " + _tool_status.answer_note(tool) + " " + _monitor.library_note(library_ref))}


@mcp.tool(title="Draft a nightly drift monitor: notebook, pipeline and schedule (nothing created)", annotations=RO)
@safe
def drift_monitor_draft(workspace: _p.Workspace, source: _p.Source, schema: _p.Schema = "dbo", name: _p.MonitorDraftName = "", at: _p.At = "02:00",
                        time_zone: _p.TimeZone = "W. Europe Standard Time", library_ref: _p.LibraryRef = None, ctx: Context = None) -> str:
    """Drafts a nightly Fabric notebook and pipeline that read the lakehouse schema, compare the plan with the last one
    saved in krusgraph.plans and post a summary to a webhook set as a pipeline parameter. Requires workspace and a
    lakehouse source. Returns JSON with the notebook, the pipeline definition and the schedule. Changes nothing;
    create_drift_monitor creates the items. Errors: {error, kind, hint}."""
    _check_at(at)
    p, src, refusal = _monitor_inputs(workspace, source, schema, ctx)
    if refusal:
        return refusal
    out = _monitor_answer(p, src, name or f"drift_monitor_{schema}", at, time_zone, library_ref)
    return _bounded(out, MAX_RESULT_CHARS)


@mcp.tool(title="Create or update the nightly drift monitor in Fabric (dry run by default)", annotations=WRITE)
@safe
def create_drift_monitor(workspace: _p.Workspace, source: _p.Source, name: _p.MonitorName, schema: _p.Schema = "dbo", at: _p.At = "02:00",
                         time_zone: _p.TimeZone = "W. Europe Standard Time", library_ref: _p.LibraryRef = None, schedule: _p.Schedule = True,
                         dry_run: _p.DryRun = True, ctx: Context = None) -> str:
    """Creates drift_monitor_draft's notebook and pipeline, or updates the items of those names in place, and adds a daily
    schedule unless one at that time exists. Requires workspace, a lakehouse source and name; Notebook.ReadWrite.All
    and DataPipeline.ReadWrite.All (or Item.ReadWrite.All), DataPipeline.Execute.All for the schedule, and
    Contributor. Returns JSON with the items and REST calls; with dry_run=false also each step's result. Changes
    Fabric only with dry_run=false: the two items' definitions are replaced, existing schedules are kept, nothing is
    deleted and no secret is written. Errors: {error, kind, hint}."""
    import requests as _requests
    from . import monitor as _monitor, notebook as _notebook
    from .deploy import create_item_with_definition
    _check_at(at)
    p, src, refusal = _monitor_inputs(workspace, source, schema, ctx)
    if refusal:
        return refusal
    out = _monitor_answer(p, src, name, at, time_zone, library_ref, "create_drift_monitor")
    ws = src["workspace_id"]
    out["dry_run"] = dry_run
    out["rest"] = [{"step": "notebook", "method": "POST", "url": f"{FABRIC}/v1/workspaces/{ws}/notebooks", "or_update": ".../notebooks/{id}/updateDefinition",
                    "delegated_scope": NOTEBOOK_SCOPE},
                   {"step": "pipeline", "method": "POST", "url": f"{FABRIC}/v1/workspaces/{ws}/dataPipelines", "or_update": ".../dataPipelines/{id}/updateDefinition",
                    "delegated_scope": PIPELINE_SCOPE},
                   {"step": "schedule", "method": "POST", "url": f"{FABRIC}/v1/workspaces/{ws}/dataPipelines/{{id}}/jobs/execute/schedules",
                    "delegated_scope": SCHEDULE_SCOPE, "skipped_when": "schedule=false, or a daily schedule at the same time exists"}]
    out["spec"] = ("microsoft/fabric-rest-api-specs a96c37a: notebook/swagger.json Items_CreateNotebook; dataPipeline/swagger.json "
                   "Items_CreateDataPipeline, Items_UpdateDataPipelineDefinition, BackgroundJobs_ScheduleExecute (at most 20 schedules per "
                   "pipeline); common/job_scheduling.json DailyScheduleConfig; read 26 October 2026")
    if dry_run:
        return _bounded(out, MAX_RESULT_CHARS)
    label = f"{src['item_name']}.{schema}"
    token = lambda: auth.fabric(ctx)  # noqa: E731
    out["notebook"].pop("content", None)
    out["result"] = {}
    nb = create_item_with_definition("notebooks", "Notebook", _notebook.envelope(name, _notebook.fabric_source(
        _monitor.notebook_cells(src, library_ref), _notebook.notebook_metadata(ws, src["item_id"], src["item_name"])),
        f"Krusgraph drift monitor for {label}"), ws, token_provider=token)
    out["result"]["notebook"] = {k: v for k, v in nb.items() if k != "body"}
    if nb.get("status") != "Succeeded":
        return _step_failed(out, "notebook", nb, NOTEBOOK_SCOPE, f"creating the notebook {name!r}")
    content = _monitor.pipeline_content(nb["id"], ws, label)
    out["pipeline"]["content"] = content
    pl = create_item_with_definition("dataPipelines", "DataPipeline", _notebook.pipeline_envelope(f"{name}_nightly", content,
                                     f"Krusgraph drift monitor for {label}"), ws, token_provider=token)
    out["result"]["pipeline"] = {k: v for k, v in pl.items() if k != "body"}
    if pl.get("status") != "Succeeded":
        return _step_failed(out, "pipeline", pl, PIPELINE_SCOPE, f"creating the pipeline {name + '_nightly'!r}")
    if not schedule:
        out["result"]["schedule"] = {"status": "Skipped", "why": "schedule=false"}
    else:
        headers = _headers(ctx)
        url = f"{FABRIC}/v1/workspaces/{ws}/dataPipelines/{pl['id']}/jobs/execute/schedules"
        r = _requests.get(url, headers=headers, timeout=30)
        existing = r.json().get("value", []) if getattr(r, "status_code", 0) == 200 else []
        same = [x for x in existing if (x.get("configuration") or {}).get("type") == "Daily" and at in ((x.get("configuration") or {}).get("times") or [])]
        if same:
            out["result"]["schedule"] = {"status": "Succeeded", "mode": "kept", "id": same[0].get("id"),
                                         "why": f"a daily schedule at {at} exists; {len(existing)} schedule(s) left as they are"}
        else:
            r = _requests.post(url, headers=headers, json=out["schedule"], timeout=30)
            status = getattr(r, "status_code", 0)
            if status not in (200, 201):
                return _step_failed(out, "schedule", {"status": "Failed", "http": status, "body": getattr(r, "text", "")}, SCHEDULE_SCOPE,
                                    f"scheduling the pipeline {name + '_nightly'!r}")
            body = r.json() if getattr(r, "text", "") else {}
            out["result"]["schedule"] = {"status": "Succeeded", "mode": "created", "id": (body or {}).get("id")}
    out["result"]["status"] = "Succeeded"
    return json.dumps(out, indent=2, default=str)


EXPORTABLE = ("create_backend", "create_semantic_model", "create_views", "create_silver_notebook", "create_drift_monitor", "create_gold_views")


@mcp.tool(title="Export what the creating tools would create, in Fabric's Git format", annotations=RO)
@safe
def export_item_definitions(workspace: _p.Workspace, source: _p.Source, schema: _p.Schema = "dbo", items: _p.ExportItems = None,
                            names: _p.ExportNames = None, keys: _p.Keys = None,
                            confirmed: _p.Confirmed = None, tables: _p.TablesOnly = None, silver_schema: _p.SilverSchema = "silver",
                            gold_schema: _p.GoldSchema = "gold", views_schema: _p.ViewsSchema = "krusgraph", writable: _p.Writable = False,
                            show_personal_data: _p.ShowPersonalData = False, ctx: Context = None) -> str:
    """Exports what the creating tools would create as files in Fabric's Git format: a <name>.<type> folder per item,
    views as .sql, a README. Requires workspace and source. Returns JSON with the files, the items and what was
    skipped and why. Changes nothing. Errors: {error, kind, hint}."""
    from . import git_export as _gx, notebook as _notebook, silver as _silver_mod, gold as _gold_mod, monitor as _monitor
    from .infer import PlanInputError
    wanted = list(dict.fromkeys(items or EXPORTABLE))
    unknown = [i for i in wanted if i not in EXPORTABLE]
    if unknown:
        raise PlanInputError("items: one or more of " + ", ".join(EXPORTABLE) + "; not known: " + ", ".join(unknown))
    p, info = _source_inputs(workspace, source, schema, keys, confirmed, ctx)
    check_tables(p.schema, tables)
    names = {**{"create_backend": f"{info['item_name']}_api", "create_semantic_model": f"{info['item_name']}_model",
                "create_silver_notebook": f"silver_{schema}", "create_drift_monitor": f"drift_monitor_{schema}",
                "create_gold_views": f"gold_{schema}"}, **(names or {})}
    lakehouse = info["item_kind"] == "Lakehouse"
    files: dict[str, str] = {}
    entries, notes, skipped = [], [], []

    def add(tool: str, item_type: str, body: dict, what: str) -> None:
        folder = _gx.folder(body["displayName"], item_type)
        if any(e["folder"] == folder for e in entries):
            raise PlanInputError(f"names: two items would share the folder {folder}; give {tool} another name")
        files.update(_gx.files_of(body, item_type))
        entries.append({"tool": tool, "type": item_type, "folder": _gx.folder(body["displayName"], item_type), "what": what})
    for tool in wanted:
        if tool in ("create_silver_notebook", "create_drift_monitor", "create_gold_views") and not lakehouse:
            skipped.append({"tool": tool, "why": f"needs a lakehouse; {info['item_name']!r} is a {info['item_kind']}"})
            continue
        if tool == "create_gold_views" and not info.get("schemas_enabled"):
            skipped.append({"tool": tool, "why": "materialized lake views need a lakehouse created with schemas"})
            continue
        if tool == "create_backend":
            source_id, source_type = source_for(info["workspace_id"], {"type": info["item_kind"], "id": info["item_id"]}, _headers(ctx))
            env = definition(p, names[tool], info["workspace_id"], source_id, source_type, writable=writable, tables=tables)
            add(tool, "GraphQLApi", env, f"the API for GraphQL over {info['item_name']}.{schema} with the plan's relationships")
        elif tool == "create_semantic_model":
            draft = _semantic_model.draft(p, info, names[tool], tables)
            add(tool, "SemanticModel", _semantic_model.envelope(draft["parts"], names[tool], f"Created by Krusgraph from {source} ({schema})"),
                "the Direct Lake semantic model with the plan's relationships, the suggested measures and the calendar")
            notes.append(f"The semantic model's README.generated.md is not part of its definition and is left out; semantic_model_draft returns it.")
        elif tool == "create_views":
            stmts = _views.statements(p, views_schema)
            sql = ["-- T-SQL views from the plan, as create_views runs them. Fabric's Git integration does not carry views on a SQL",
                   "-- analytics endpoint (fabric-docs data-warehouse/git-integration.md), so this file is outside every item folder: run it",
                   f"-- with create_views or in the SQL editor of {info['item_name']}. CREATE OR ALTER only; nothing is dropped. GO separates",
                   "-- the batches for SSMS and sqlcmd; in an editor that does not take GO, run one view at a time.", "",
                   stmts["schema_sql"] + ";", ""] + [f"-- {v['why']}\n{v['sql']};\nGO\n" for v in stmts["views"]]
            files[f"krusgraph-sql/{views_schema}-views.sql"] = "\n".join(sql)
            entries.append({"tool": tool, "type": "T-SQL", "folder": "krusgraph-sql", "what": f"{len(stmts['views'])} view(s) in schema {views_schema}, "
                            "as a script (not a Fabric item)"})
        elif tool == "create_silver_notebook":
            spec = _silver_mod.spec(p, info, silver_schema, None, tables, show_personal_data)
            add(tool, "Notebook", _notebook.envelope(names[tool], _silver_mod.notebook_source(spec),
                                                     f"Silver tables for {info['item_name']}.{schema}, generated by Krusgraph from the plan"),
                f"the notebook that writes the silver tables in {silver_schema}")
        elif tool == "create_drift_monitor":
            source_id, source_type = source_for(info["workspace_id"], {"type": info["item_kind"], "id": info["item_id"]}, _headers(ctx))
            src = {k: info[k] for k in ("workspace_id", "item_id", "item_name", "schema", "schemas_enabled", "sql_db")}
            src.update(source_id=source_id, source_type=source_type)
            label = f"{info['item_name']}.{schema}"
            nb = names[tool]
            add(tool, "Notebook", _notebook.envelope(nb, _notebook.fabric_source(_monitor.notebook_cells(src), _notebook.notebook_metadata(
                info["workspace_id"], info["item_id"], info["item_name"])), f"Krusgraph drift monitor for {label}"), "the drift monitor's notebook")
            add(tool, "DataPipeline", _notebook.pipeline_envelope(f"{nb}_nightly", _monitor.pipeline_content(
                "<the notebook's id after the Git update>", info["workspace_id"], label), f"Krusgraph drift monitor for {label}"),
                "the nightly pipeline that runs it")
            notes.append(f"{nb}_nightly: its Notebook activity names the notebook by id, which Fabric assigns when the Git update creates it; "
                         "open the activity once and pick the notebook. The daily schedule is not part of an item definition: add it in "
                         "the pipeline's Schedule pane, or let create_drift_monitor add it.")
        elif tool == "create_gold_views":
            spec = _gold_mod.spec(p, info, silver_schema, gold_schema, None, show_personal_data, within=tables)
            add(tool, "Notebook", _notebook.envelope(names[tool], _gold_mod.notebook_source(spec),
                                                     f"Gold views for {info['item_name']}.{schema}, generated by Krusgraph from the plan"),
                f"the notebook that creates {len(spec['views'])} materialized lake view(s) in {gold_schema}")
            notes.append("Materialized lake views are created when the gold notebook runs, not by the Git update; Fabric's Git integration "
                         "carries the notebook. Run the silver notebook first.")
    files["KRUSGRAPH-EXPORT.md"] = _gx.readme(entries, notes)
    out = {"summary": p.summary().splitlines()[0] + f"; {len(entries)} item(s) as files in Fabric's Git format, nothing created",
           "items": entries, "skipped": skipped, "how": _gx.HOW, "notes": notes, "files": files, "sources": _gx.SOURCES,
           "note": "Unit-tested: the files are the parts the creating tools send to the REST APIs, in the Git layout; not yet synced into a "
                   "workspace through Fabric's Git integration. " + _tool_status.answer_note("export_item_definitions")}
    text = json.dumps(out, indent=2)
    if len(text) > MAX_RESULT_CHARS:
        out["omitted"] = []
        while len(json.dumps(out, indent=2)) > MAX_RESULT_CHARS and len(out["files"]) > 1:
            biggest = max((k for k in out["files"] if k != "KRUSGRAPH-EXPORT.md"), key=lambda k: len(out["files"][k]))
            out["omitted"].append(biggest)
            out["files"] = {k: v for k, v in out["files"].items() if k != biggest}
        out["note"] += " Files left out of this answer because of its size are under `omitted`; pass `items` (one tool) or `tables` for them."
        text = json.dumps(out, indent=2)
    return text


@mcp.tool(title="Starter pack for an app on a GraphQL API", annotations=RO)
@safe
def app_starter(workspace: _p.Workspace, api: _p.StarterApi, ctx: Context = None) -> str:
    """Generates a starter pack for an app on an API for GraphQL item: a Lovable prompt, connection details, five GraphQL
    queries that follow the relationships, a Supabase edge function and the portal steps left. Requires workspace
    and an API that create_backend has created. Returns JSON {lovable_prompt, connection, queries, checklist,
    backend, note}. Changes nothing; app_readiness lists what the API lacks. Errors: {error, kind, hint}."""
    headers = _headers(ctx)
    workspace_id = _workspace_id(workspace, headers)
    api_id = _api_id(workspace_id, api, headers)
    if not api_id:
        return json.dumps({"error": f"no API for GraphQL named {api!r} in workspace {workspace}", "kind": "not_found",
                           "hint": "list_sources lists the GraphQL APIs in a workspace; create_backend creates one."}, indent=2)
    description = describe_definition(_graphql_definition(workspace_id, api_id, headers))
    from .deploy import endpoint_url
    return json.dumps(_app_starter.starter(description, endpoint_url(workspace_id, api_id), api, workspace_id), indent=2)


@mcp.tool(title="What an app still needs on a GraphQL API", annotations=RO)
@safe
def app_readiness(workspace: _p.Workspace, api: _p.StarterApi, ctx: Context = None) -> str:
    """Checks what an API for GraphQL item still needs before an app can use it: types without a key or relationship, write
    access, introspection (one probe query), and permissions, reported as unknown with the portal path. Requires
    workspace and an API that create_backend has created. Returns JSON {api, endpoint, checks, missing, unknown,
    verdict}, each item with its next step. Changes nothing. Errors: {error, kind, hint}."""
    headers = _headers(ctx)
    workspace_id = _workspace_id(workspace, headers)
    api_id = _api_id(workspace_id, api, headers)
    if not api_id:
        return json.dumps({"error": f"no API for GraphQL named {api!r} in workspace {workspace}", "kind": "not_found",
                           "hint": "list_sources lists the GraphQL APIs in a workspace; create_backend creates one."}, indent=2)
    description = describe_definition(_graphql_definition(workspace_id, api_id, headers))
    from .deploy import endpoint_url
    endpoint = endpoint_url(workspace_id, api_id)
    r = requests.post(endpoint, headers=headers, json={"query": _readiness.INTROSPECTION_QUERY, "variables": {}}, timeout=60)
    status = getattr(r, "status_code", 200)
    try:
        body = r.json() if status < 400 else {}
    except ValueError:
        body = {}
    return json.dumps(_readiness.assess(description, _readiness.classify_probe(status, body), endpoint, api), indent=2)


def _workspace_items(workspace: str, headers: dict) -> list[dict]:
    """Every item in the workspace (id, displayName, type), all pages (lineage.rest_items)."""
    return _lineage.rest_items(workspace, headers)


def _item_definition_parts(workspace: str, route: str, item_id: str, headers: dict, fmt: str | None = None) -> dict[str, str]:
    """{path: text} of an item's definition (lineage.rest_definition_parts)."""
    return _lineage.rest_definition_parts(workspace, route, item_id, headers, fmt)


def _lineage_edges(workspace_id: str, item: dict, schema: str, tables: set[str], headers: dict, execute=None) -> tuple[list[dict], list[dict]]:
    """Edges table -> object over every item in the workspace that can be read, plus the items that could not
    (lineage.workspace_edges, with this module's readers so the tests can stand in for Fabric)."""
    rows, view_skip = None, []
    if execute is not None:
        try:
            rows = list(execute(_lineage.VIEW_USAGE_SQL))
        except Exception:  # noqa: BLE001 — an endpoint without INFORMATION_SCHEMA.VIEW_TABLE_USAGE: try the sys view
            try:
                rows = list(execute(_lineage.VIEW_USAGE_SQL_SYS))
            except Exception as e:  # noqa: BLE001
                rows = []
                view_skip.append(_lineage.skipped_item("views on the SQL endpoint", "View", e, "reading view dependencies"))
    edges, skipped = _lineage.workspace_edges(workspace_id, item, schema, tables, headers, rows, items=_workspace_items,
                                              graphql_definition=_graphql_definition, definition_parts=_item_definition_parts)
    return edges, skipped + view_skip


@mcp.tool(title="Lineage: what builds on a source's tables", annotations=RO)
@safe
def lineage(workspace: _p.Workspace, source: _p.Source, schema: _p.Schema = "dbo", table: _p.LineageTable = None, ctx: Context = None) -> str:
    """Shows which Fabric objects in the workspace build on a source's tables: GraphQL APIs, semantic models, views on the
    SQL endpoint and data agents. Requires workspace and source. Returns JSON: a graph (nodes, edges), objects per
    table, tables nothing uses, items that could not be read, and with table, what a change to it reaches.
    Read-only. Errors: {error, kind, hint}."""
    s, execute = _connected(workspace, source, schema, ctx)
    try:
        headers = _headers(ctx)
        workspace_id = _workspace_id(workspace, headers)
        item = _resolve_source(workspace_id, source, headers)
        tables = [t.name for t in s]
        edges, skipped = _lineage_edges(workspace_id, item, schema, set(tables), headers, execute=execute)
    finally:
        getattr(execute, "close", lambda: None)()
    out = _lineage.graph(item, schema, tables, edges, skipped)
    if table:
        out["impact"] = _lineage.impact(out, table)
    return json.dumps(out, indent=2, default=str)


def _graphql_definition(workspace: str, api_id: str, headers: dict) -> dict:
    """graphql-definition.json of an API for GraphQL item (lineage.rest_graphql_definition)."""
    return _lineage.rest_graphql_definition(workspace, api_id, headers)


def describe_definition(body: dict) -> dict:
    """Types, their fields and relationships, in the names a query uses."""
    types = []
    for ds in body.get("datasources", []):
        for o in ds.get("objects", []):
            actions = o.get("actions", {})
            types.append({
                "type": o.get("graphqlType"),
                # Fabric names the list query after the type in the plural: audit_log -> audit_logs, orders -> orders
                "query_field": o.get("graphqlType") if str(o.get("graphqlType", "")).endswith("s") else f"{o.get('graphqlType')}s",
                "source": o.get("sourceObject"),
                "fields": list((o.get("fieldMappings") or {}).values()),
                "relationships": [{"field": r.get("field"), "to": r.get("targetObject"), "cardinality": r.get("cardinality")}
                                  for r in o.get("relationships", [])],
                "by_key": actions.get("Query_by_pk") == "Enabled",
                "writable": any(actions.get(a) == "Enabled" for a in ("Create", "Update", "Delete")),
            })
    return {"types": types,
            "how_to_query": "{ <query_field>(first: 10, filter: {...}, orderBy: {...}) { items { <fields> <relationship> { ... } } } }"}


@mcp.tool(title="Describe a GraphQL API", annotations=RO)
@safe
def describe_backend(workspace: _p.Workspace, api: _p.StarterApi, ctx: Context = None) -> str:
    """Describes an API for GraphQL item in the names a query uses: types, list query fields, fields and relationships.
    Requires workspace and an API that create_backend has created (list_sources lists them). Returns JSON {types:
    [{type, query_field, source, fields, relationships, by_key, writable}], how_to_query}. Read from the item's
    definition, so introspection can be off; changes nothing. query_graphql runs a query. Errors: {error, kind,
    hint}."""
    headers = _headers(ctx)
    workspace = _workspace_id(workspace, headers)
    api_id = _api_id(workspace, api, headers)
    if not api_id:
        return json.dumps({"error": f"no API for GraphQL named {api!r} in workspace {workspace}", "kind": "not_found",
                           "hint": "list_sources lists the GraphQL APIs in a workspace."}, indent=2)
    return json.dumps(describe_definition(_graphql_definition(workspace, api_id, headers)), indent=2)


@mcp.tool(title="Suggest a GraphQL or T-SQL query for a question (runs nothing)", annotations=RO)
@safe
def answer_query_draft(workspace: _p.Workspace, source: _p.Source, question: _p.Question, tables: _p.QuestionTables, schema: _p.Schema = "dbo", api: _p.QuestionApi = None,
                       keys: _p.Keys = None, confirmed: _p.Confirmed = None, show_personal_data: _p.ShowPersonalData = False,
                       ctx: Context = None) -> str:
    """Turns a question in Swedish or English about given tables into T-SQL over the plan's safest join path, and with api
    into GraphQL in that API's field names, or says why GraphQL cannot answer it. Requires workspace, source,
    question and tables. Returns JSON with the query, each join step with its rule, and what it assumed. Runs
    nothing; query_graphql runs the GraphQL version. Errors: {error, kind, hint}."""
    from . import answers as _answers
    p, _, headers = _plan(workspace, source, schema, keys, confirmed, ctx)
    description = None
    if api:
        workspace_id = _workspace_id(workspace, headers)
        api_id = _api_id(workspace_id, api, headers)
        if not api_id:
            return json.dumps({"error": f"no API for GraphQL named {api!r} in workspace {workspace}", "kind": "not_found",
                               "hint": "list_sources lists the GraphQL APIs in a workspace; leave api out for the T-SQL alone."}, indent=2)
        description = describe_definition(_graphql_definition(workspace_id, api_id, headers))
    return _bounded(_answers.draft(p, question, tables, description, api, show_personal_data), MAX_RESULT_CHARS)


def _check_query(query: str) -> str | None:
    """The read-only guard: one GraphQL query operation (fragments allowed), else the refusal as JSON."""
    from graphql import GraphQLError, OperationType, parse
    from graphql.language import FragmentDefinitionNode, OperationDefinitionNode
    try:
        document = parse(query, max_tokens=10000)
    except GraphQLError as e:
        return json.dumps({"error": f"The query is not valid GraphQL: {e.message}", "kind": "invalid_query",
                           "hint": "Fix the syntax; describe_backend lists the types, fields and relationships to use."})
    operations = [node for node in document.definitions if isinstance(node, OperationDefinitionNode)]
    if any(node.operation != OperationType.QUERY for node in operations):
        return json.dumps({"error": "Mutations and subscriptions are not allowed through this tool; it only reads.",
                           "kind": "read_only",
                           "hint": "Ask a question instead (a query). Changes to data belong in Fabric itself or in an app "
                                   "that uses the API with its own permissions."})
    if len(operations) != 1 or any(not isinstance(node, (OperationDefinitionNode, FragmentDefinitionNode))
                                   for node in document.definitions):
        return json.dumps({"error": "Send exactly one GraphQL query operation (fragments are allowed).", "kind": "invalid_query",
                           "hint": "Split several operations into separate calls."})
    return None


@mcp.tool(title="Run a GraphQL query", annotations=RO)
@safe
def query_graphql(workspace: _p.Workspace, api: _p.Api, query: _p.Query = "", variables: _p.Variables = None, question: _p.GraphqlQuestion = None,
                  tables: _p.GraphqlTables = None, source: _p.GraphqlSource = None, schema: _p.Schema = "dbo", ctx: Context = None) -> str:
    """Runs a read-only GraphQL query against an API for GraphQL item; given question instead of query, it builds the query
    as answer_query_draft does and runs it. Requires workspace and api, plus query, or question with tables and
    source. Returns JSON with the data, size-bounded, and for a question the query used. Mutations and subscriptions
    are refused; changes nothing. describe_backend gives the field names. Errors: {error, kind, hint}."""
    import requests
    if not query and not question:
        return json.dumps({"error": "Give a GraphQL query, or a question with the tables it is about.", "kind": "bad_input",
                           "hint": "answer_query_draft shows the query a question becomes before anything runs."})
    suggestion = None
    if not query:
        if not tables or not source:
            return json.dumps({"error": "A question needs `tables` (the tables it is about) and `source` (the lakehouse or warehouse the API reads).",
                               "kind": "bad_input", "hint": "list_sources shows the sources; answer_query_draft previews the query."})
        from . import answers as _answers
        p, _, headers = _plan(workspace, source, schema, None, None, ctx)
        workspace_id = _workspace_id(workspace, headers)
        api_id = _api_id(workspace_id, api, headers)
        if not api_id:
            return json.dumps({"error": f"no API for GraphQL named {api!r} in workspace {workspace}", "kind": "not_found",
                               "hint": "list_sources lists the GraphQL APIs in a workspace."}, indent=2)
        draft = _answers.draft(p, question, tables, describe_definition(_graphql_definition(workspace_id, api_id, headers)), api)
        if not draft["graphql"].get("query"):
            return json.dumps({"error": f"This question has no GraphQL form on {api!r}: {draft['graphql'].get('not_possible')}",
                               "kind": "unsupported", "hint": "Run the T-SQL below on the SQL analytics endpoint instead.", "tsql": draft["tsql"]}, indent=2)
        query = draft["graphql"]["query"]
        suggestion = {"question": question, "query": query, "understood": draft["understood"], "path": draft["path"],
                      "assumptions": draft["assumptions"], "notes": draft["graphql"].get("notes", [])}
    refused = _check_query(query)
    if refused:
        return refused
    headers = _headers(ctx)
    workspace = _workspace_id(workspace, headers)
    if len(api) == 36 and api.count("-") == 4:
        api_id = api
    else:
        item = find_item_by_name(workspace, api, headers, ("GraphQLApi",))
        api_id = item["id"] if item else None
    if not api_id:
        return json.dumps({"error": f"no API for GraphQL named {api!r} in workspace {workspace}"})
    r = requests.post(f"{FABRIC}/v1/workspaces/{workspace}/graphqlapis/{api_id}/graphql", headers=headers,
                      json={"query": query, "variables": variables or {}}, timeout=100)
    status = getattr(r, "status_code", 200)
    if status in (401, 403, 404, 429) or status >= 500:
        return json.dumps(classify_http(status, getattr(r, "text", ""), f"querying {api!r} in workspace {workspace}"), indent=2)
    try:
        body = r.json()
    except ValueError:
        body = {"http": r.status_code, "text": r.text[:2000]}
    if suggestion is not None:
        body = {"suggested": suggestion, "result": body}
    return _bounded(body, MAX_RESULT_CHARS)


MAX_RESULT_CHARS = 60000


def _bounded(body, limit: int, hint: str = "Ask for fewer fields or page with first:/after.", drop: tuple[str, ...] = ()) -> str:
    """JSON of at most `limit` characters, always valid (fabric_backend.compact.bounded)."""
    return _compact.bounded(body, limit, hint, drop)


MAX_BODY_BYTES = 4 * 1024 * 1024      # an MCP message is a few kilobytes; nothing here needs more than this


class _BodyTooLarge(Exception):
    pass


def _with_security_headers(app):
    """Every HTTP response, /mcp included: HSTS (the server is only ever reached over HTTPS; Container Apps
    redirects plain HTTP) and nosniff. A request that announces a body over MAX_BODY_BYTES is refused with 413
    before anything reads it, and a body that grows past the limit without announcing it (chunked transfer) is
    cut off with 413 at the first chunk over the limit, so no request can make the server buffer more than that.
    Pure ASGI so streamed MCP responses are untouched apart from the headers."""
    from starlette.datastructures import Headers, MutableHeaders
    from starlette.responses import JSONResponse

    too_large = JSONResponse({"error": f"request body over {MAX_BODY_BYTES} bytes"}, status_code=413)

    async def wrapped(scope, receive, send):
        if scope["type"] != "http":
            return await app(scope, receive, send)
        declared = Headers(scope=scope).get("content-length", "")
        app_ = too_large if declared.isdigit() and int(declared) > MAX_BODY_BYTES else app
        received, state = 0, {"started": False, "done": False}

        async def send_with_headers(message):
            if state["done"]:                                   # the 413 is out; whatever the app sends afterwards is dropped
                return
            if message["type"] == "http.response.start":
                state["started"] = True
                headers = MutableHeaders(scope=message)
                headers.setdefault("Strict-Transport-Security", "max-age=31536000")
                headers.setdefault("X-Content-Type-Options", "nosniff")
            await send(message)

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body") or b"")
                if received > MAX_BODY_BYTES:
                    if not state["started"]:
                        await too_large(scope, receive, send_with_headers)
                    state["done"] = True
                    raise _BodyTooLarge()
            return message

        try:
            await app_(scope, limited_receive, send_with_headers)
        except _BodyTooLarge:
            pass
        except Exception:
            if state["done"]:                                   # the app failed on the request we cut off: already answered
                return
            raise
    return wrapped


def build_app(host: str = "0.0.0.0"):
    """The ASGI app: the MCP endpoint at /mcp, plus — in Entra mode — the protected resource metadata and a
    401 challenge in front of /mcp for any request without a valid token (Claude starts sign-in on the 401)."""
    import json as _json
    from starlette.exceptions import HTTPException
    from starlette.responses import JSONResponse, PlainTextResponse, Response
    from starlette.routing import Route

    app = mcp.streamable_http_app(stateless_http=True, host=host)
    cfg = auth.entra

    async def health(_request):
        body = {"ok": True, "auth": "entra" if cfg else "bearer-or-service-principal"}
        if os.environ.get("KRUSGRAPH_BUILD"):      # the source tag the deploy script built; lets it tell revisions apart
            body["build"] = os.environ["KRUSGRAPH_BUILD"]
        return JSONResponse(body)
    app.router.routes.append(Route("/healthz", health))   # the container probes and the deploy script's build check

    async def health_public(_request):
        """For uptime monitors and the Azure Monitor availability test: no sign-in, nothing about the server."""
        return JSONResponse({"status": "ok"}, headers={"Cache-Control": "no-store"})
    app.router.routes.append(Route("/health", health_public, methods=["GET", "HEAD"]))

    async def metrics(request):
        """Usage totals (usage.py) in the Prometheus text format. Off unless KRUSGRAPH_METRICS_TOKEN is set (32
        characters or more); then only for a request carrying it as a bearer token. Otherwise this path is a 404."""
        import hmac
        expected = os.environ.get("KRUSGRAPH_METRICS_TOKEN", "").strip()
        if len(expected) < 32:
            return PlainTextResponse("not found", status_code=404)
        a = request.headers.get("authorization", "")
        given = a[7:].strip() if a.lower().startswith("bearer ") else ""
        if not given or not hmac.compare_digest(given.encode(), expected.encode()):
            return PlainTextResponse("unauthorized", status_code=401, headers={"Cache-Control": "no-store"})
        return PlainTextResponse(_usage.usage.prometheus(), media_type="text/plain; version=0.0.4", headers={"Cache-Control": "no-store"})
    app.router.routes.append(Route("/metrics", metrics))

    from starlette.responses import FileResponse, HTMLResponse
    from .pages import (PAGES, STATIC_TYPES, docs_html, docs_md, lovable_html, lovable_md, local_html, local_md, not_found_html, privacy_html,
                        privacy_md, render, start_md, static_file, use_cases_md)
    from . import discovery
    from .demo import demo_plan_json, demo_validation_json

    PAGE_CACHE = "public, max-age=300"
    # The pages load nothing from anywhere else, so the policy can say so. Inline style attributes are used in the
    # templates; scripts are only the two files under /static. Applies to HTML responses only, never to /mcp.
    PAGE_HEADERS = {
        "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                                   "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        "X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin",
    }

    import gzip as _gzip

    def compressed(request, body: bytes, media_type: str, headers: dict, status: int = 200) -> Response:
        """gzip for the site's text responses when the client accepts it. Only these routes; never /mcp."""
        if len(body) > 1024 and "gzip" in request.headers.get("accept-encoding", ""):
            body = _gzip.compress(body, compresslevel=6)
            headers = {**headers, "Content-Encoding": "gzip"}
        return Response(body, status_code=status, media_type=media_type, headers={**headers, "Vary": "Accept-Encoding"})

    # /check runs the engine in a Web Worker on files that never leave the browser. Apart from its two events (an image
    # from /check/event, step name only) the page itself fetches nothing
    # (connect-src 'none'); the worker may load exactly Pyodide's files and the engine zip from this host, and compile
    # WebAssembly. A request carrying a file therefore has nowhere to go (tests/browser_check.js checks it on screen).
    def check_headers(request, worker: bool = False) -> dict:
        host = request.headers.get("host", "").strip()
        own = f"{host}/static/pyodide/ {host}/check/engine.zip" if host and all(c.isalnum() or c in ".-:[]" for c in host) else "'none'"
        csp = ("default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; connect-src " + own + "; base-uri 'none'" if worker else
               "default-src 'self'; script-src 'self'; worker-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
               "font-src 'self'; connect-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'none'")
        return {**PAGE_HEADERS, "Content-Security-Policy": csp}

    def page_route(path: str, fn):
        async def handler(request):
            headers = {"Cache-Control": PAGE_CACHE, **(check_headers(request) if path == "/check" else PAGE_HEADERS)}
            if path == "/mascots":
                headers["X-Robots-Tag"] = "noindex, nofollow"
            _usage.page_view(path)                    # one line for /, /check, /explore, /start, /partners; nothing else
            return compressed(request, fn().encode("utf-8"), "text/html; charset=utf-8", headers)
        app.router.routes.append(Route(path, handler))

    for path in PAGES:
        page_route(path, (lambda p: lambda: render(p))(path))
    page_route("/privacy", privacy_html)
    page_route("/docs", docs_html)
    page_route("/lovable", lovable_html)
    page_route("/local", local_html)

    # The same content as Markdown, for /llms.txt and agents.
    def md_route(path: str, fn):
        async def handler(request):
            return compressed(request, fn().encode("utf-8"), "text/markdown; charset=utf-8", {"Cache-Control": PAGE_CACHE})
        app.router.routes.append(Route(path, handler))
    for path, fn in (("/docs.md", docs_md), ("/privacy.md", privacy_md), ("/start.md", start_md), ("/lovable.md", lovable_md),
                     ("/local.md", local_md), ("/use-cases.md", use_cases_md)):
        md_route(path, fn)

    async def llms(request):
        return compressed(request, discovery.llms_txt().encode("utf-8"), "text/plain; charset=utf-8", {"Cache-Control": PAGE_CACHE})
    app.router.routes.append(Route("/llms.txt", llms))

    async def llms_full(request):
        parts = [("/docs.md", docs_md()), ("/start.md", start_md()), ("/lovable.md", lovable_md()), ("/local.md", local_md()),
                 ("/use-cases.md", use_cases_md()), ("/privacy.md", privacy_md())]
        return compressed(request, discovery.llms_full_txt(parts).encode("utf-8"), "text/plain; charset=utf-8", {"Cache-Control": PAGE_CACHE})
    app.router.routes.append(Route("/llms-full.txt", llms_full))

    async def sitemap(request):
        return compressed(request, discovery.sitemap_xml().encode("utf-8"), "application/xml", {"Cache-Control": "public, max-age=86400"})
    app.router.routes.append(Route("/sitemap.xml", sitemap))

    # MCP Server Card (SEP-2127) at <streamable-http-url>/server-card and the AI Catalog that points at it. Public by
    # design: the auth guard below covers exactly /mcp, nothing under it. CORS, caching and ETag as docs/discovery.md says.
    CARD_HEADERS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET",
                    "Access-Control-Allow-Headers": "Content-Type, If-None-Match", "Access-Control-Expose-Headers": "ETag",
                    "Cache-Control": "public, max-age=3600"}

    def card_route(path: str, doc, media_type: str):
        async def handler(request):
            if request.method == "OPTIONS":
                return Response(status_code=204, headers=CARD_HEADERS)
            body = discovery.card_json(doc())
            tag = discovery.etag(body)
            headers = dict(CARD_HEADERS, ETag=tag)
            if tag in [t.strip() for t in request.headers.get("if-none-match", "").split(",")]:
                return Response(status_code=304, headers=headers)
            return Response(body, media_type=media_type, headers=headers)
        app.router.routes.append(Route(path, handler, methods=["GET", "HEAD", "OPTIONS"]))
    card_route("/mcp/server-card", discovery.server_card, discovery.SERVER_CARD_TYPE)
    card_route("/.well-known/ai-catalog.json", discovery.ai_catalog, discovery.AI_CATALOG_TYPE)

    async def glama(_request):
        """Glama's ownership file: public, outside the sign-in in front of /mcp, and only on krusgraph.com (discovery.py)."""
        body = discovery.glama_json()
        if body is None:
            raise HTTPException(status_code=404)
        return Response(body, media_type="application/json")
    app.router.routes.append(Route("/.well-known/glama.json", glama, methods=["GET", "HEAD"]))

    async def plan_json(request):
        return compressed(request, demo_plan_json().encode("utf-8"), "application/json", {"Cache-Control": "public, max-age=3600"})
    app.router.routes.append(Route("/demo/plan.json", plan_json))

    # The first customer demonstration (two companies, one sales view): a preview, served only with KRUSGRAPH_PREVIEW=1,
    # noindex and out of the sitemap, so a deploy does not publish it.
    from . import sales_demo
    if sales_demo.enabled():
        async def sales_page(request):
            headers = {"Cache-Control": "no-store", **PAGE_HEADERS, "X-Robots-Tag": "noindex, nofollow"}
            return compressed(request, sales_demo.page_html(request.query_params).encode("utf-8"), "text/html; charset=utf-8", headers)
        app.router.routes.append(Route(sales_demo.PATH, sales_page))

        async def sales_json(request):
            from .planning import PlanningInputError
            headers = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"}
            try:
                body = sales_demo.result_json(*sales_demo.parse(request.query_params))
            except PlanningInputError as e:
                return Response(json.dumps({"error": str(e), "kind": "bad_input",
                                            "hint": "Use d=B-7003:A-103 (or :none, :open), company=all|A|B and weeks=13|26|52|104."}),
                                status_code=400, media_type="application/json", headers=headers)
            return compressed(request, body.encode("utf-8"), "application/json", headers)
        app.router.routes.append(Route(sales_demo.PATH + "/result.json", sales_json))

    async def validation_json(request):
        return compressed(request, demo_validation_json().encode("utf-8"), "application/json", {"Cache-Control": "public, max-age=3600"})
    app.router.routes.append(Route("/demo/validation.json", validation_json))

    TEXT_STATIC = {".css", ".js", ".svg", ".txt", ".json", ".mjs"}       # woff2 and png are already compressed
    _gz: dict[str, bytes] = {}                                      # Pyodide's large files, compressed once per process

    def pyodide_file(request, p, cache: str) -> Response:
        if "gzip" not in request.headers.get("accept-encoding", "") or p.suffix in (".whl",):
            return FileResponse(str(p), media_type=STATIC_TYPES[p.suffix], headers={"Cache-Control": cache})
        body = _gz.get(p.name)
        if body is None:
            body = _gz[p.name] = _gzip.compress(p.read_bytes(), compresslevel=9)
        return Response(body, media_type=STATIC_TYPES[p.suffix], headers={"Cache-Control": cache, "Content-Encoding": "gzip", "Vary": "Accept-Encoding"})

    async def check_worker(request):
        p = static_file("check-worker.js")
        headers = {"Cache-Control": "public, max-age=31536000, immutable" if request.query_params.get("v") else PAGE_CACHE, **check_headers(request, worker=True)}
        return compressed(request, p.read_bytes(), STATIC_TYPES[".js"], headers)
    app.router.routes.append(Route("/check/worker.js", check_worker))

    # /check's two events, loaded as an image (the page itself may fetch nothing): the step is the whole request
    async def check_event(request):
        _usage.check_event(request.query_params.get("e", ""))
        return Response(status_code=204, headers={"Cache-Control": "no-store"})
    app.router.routes.append(Route("/check/event", check_event))

    async def check_engine(request):
        from .browser_check import engine_zip
        cache = "public, max-age=31536000, immutable" if request.query_params.get("v") else PAGE_CACHE
        return Response(engine_zip(), media_type="application/zip", headers={"Cache-Control": cache, "X-Content-Type-Options": "nosniff"})
    app.router.routes.append(Route("/check/engine.zip", check_engine))

    async def static(request):
        p = static_file(request.path_params.get("path", ""))
        if p is None:
            return PlainTextResponse("not found", status_code=404)
        cache = "public, max-age=31536000, immutable" if request.query_params.get("v") else "public, max-age=86400"
        if p.parent.name == "pyodide":                              # a pinned release (0.27.7): its files never change under a name
            return pyodide_file(request, p, "public, max-age=31536000, immutable")
        if p.suffix in TEXT_STATIC:
            return compressed(request, p.read_bytes(), STATIC_TYPES[p.suffix], {"Cache-Control": cache})
        return FileResponse(str(p), media_type=STATIC_TYPES[p.suffix], headers={"Cache-Control": cache})
    app.router.routes.append(Route("/static/{path:path}", static))

    def root_icon(name: str, media_type: str):
        """Directories and browsers look for the icon at the site root (Claude's directory shows the server's favicon)."""
        async def handler(_request):
            return FileResponse(str(static_file(name)), media_type=media_type, headers={"Cache-Control": "public, max-age=86400"})
        return handler
    app.router.routes.append(Route("/favicon.ico", root_icon("favicon.ico", "image/x-icon"), methods=["GET", "HEAD"]))
    app.router.routes.append(Route("/apple-touch-icon.png", root_icon("apple-touch-icon.png", "image/png"), methods=["GET", "HEAD"]))

    async def robots(_request):
        return PlainTextResponse(discovery.robots_txt(), headers={"Cache-Control": "public, max-age=86400"})
    app.router.routes.append(Route("/robots.txt", robots))

    async def not_found(request, exc):
        """A styled 404 for browsers; plain text for everything else (the MCP endpoint itself is never a 404)."""
        if request.method in ("GET", "HEAD") and "text/html" in request.headers.get("accept", ""):
            return HTMLResponse(not_found_html(request.url.path), status_code=404, headers={"X-Robots-Tag": "noindex", **PAGE_HEADERS})
        return PlainTextResponse("not found", status_code=404)
    app.add_exception_handler(404, not_found)

    if not cfg:
        return _with_security_headers(app)

    from .entra import protected_resource_metadata, challenge, TokenError

    async def prm(_request):
        return JSONResponse(protected_resource_metadata(cfg))
    app.router.routes.append(Route("/.well-known/oauth-protected-resource", prm))
    app.router.routes.append(Route("/.well-known/oauth-protected-resource/mcp", prm))

    # KRUSGRAPH_CLIENT_REGISTRATION=1: VS Code, Cursor and other MCP clients sign in at /mcp/connect through this
    # server's /oauth (fabric_backend/registration.py). Off, nothing below changes; on, /mcp and its metadata stay as they are.
    from . import registration as _reg, registration_flow as _registration
    layer = _registration.install(cfg, auth.validator)
    if layer is not None:
        app.router.routes.extend(layer.routes())

    inner = app

    async def guarded(scope, receive, send):
        if layer is not None and scope["type"] == "http" and scope["path"].rstrip("/") == _reg.CONNECT_PATH:
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            a = headers.get("authorization", "")
            token = a[7:].strip() if a.lower().startswith("bearer ") else ""
            err = "invalid_request"
            if token:
                try:
                    auth.validator.validate(token)                       # the same check as /mcp: audience, issuer, scope
                    return await inner({**scope, "path": "/mcp", "raw_path": b"/mcp"}, receive, send)
                except TokenError:
                    err = "invalid_token"
            resp = Response(_json.dumps({"error": err}), status_code=401, media_type="application/json",
                            headers={"WWW-Authenticate": _reg.challenge(cfg, err if err == "invalid_token" else None)})
            return await resp(scope, receive, send)
        if scope["type"] == "http" and scope["path"].rstrip("/") == "/mcp":
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            a = headers.get("authorization", "")
            token = a[7:].strip() if a.lower().startswith("bearer ") else ""
            err = "invalid_request"                                      # no or malformed credentials (RFC 6750 §3.1)
            if token:
                try:
                    auth.validator.validate(token)
                    return await inner(scope, receive, send)
                except TokenError:
                    err = "invalid_token"
            resp = Response(_json.dumps({"error": err}), status_code=401, media_type="application/json",
                            headers={"WWW-Authenticate": challenge(cfg, err if err == "invalid_token" else None)})
            return await resp(scope, receive, send)
        return await inner(scope, receive, send)

    return _with_security_headers(guarded)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(prog="fabric-backend-server")
    ap.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--stdio", action="store_true", help="local use instead of HTTP")
    a = ap.parse_args()
    if a.stdio:
        mcp.run(transport="stdio")
    else:
        import uvicorn
        # KRUSGRAPH_ACCESS_LOG=0 drops uvicorn's per-request access line (it carries the client's IP address); the deploy
        # script sets it when console logs go to Log Analytics, so no IP address is kept there (docs/OPERATIONS.md).
        access_log = os.environ.get("KRUSGRAPH_ACCESS_LOG", "1").strip().lower() not in {"0", "off", "false", "no"}
        uvicorn.run(build_app(a.host), host=a.host, port=a.port, proxy_headers=True, forwarded_allow_ips="*", access_log=access_log)


if __name__ == "__main__":
    main()
