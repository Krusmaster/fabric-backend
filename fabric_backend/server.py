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

Tools (all annotated for the Claude directory): list_workspaces, list_sources, list_tables, plan_backend, ontology_draft,
create_backend, rayfin_connector, query_graphql.
"""
from __future__ import annotations

import json

import requests
import os
import struct
import time

from .infer import check_tables, plan as make_plan
from .schema import Schema
from .graphql import definition
from .deploy import FABRIC, deploy, connection_card, find_item_by_name, source_for, SOURCE_ITEM_TYPES, ENDPOINT_ITEM_ROUTES
from .rayfin import rayfin_files
from . import ontology as _ontology
from .deploy import create_ontology as _create_ontology
from .errors import SchemaEmpty, classify_http, safe
from . import evidence as _evidence
from . import semantic_model as _semantic_model, paths as _paths, dictionary as _dictionary, dbt as _dbt, drift as _drift
from . import views as _views, data_agent as _data_agent, app_starter as _app_starter, graphs as _graphs, readiness as _readiness
from . import lineage as _lineage, compact as _compact
from . import limits as _limits, usage as _usage, entitlements as _entitlements
from .deploy import create_semantic_model as _create_semantic_model

try:
    from mcp.server.mcpserver import MCPServer, Context
    from mcp.types import ToolAnnotations
except ImportError as e:  # pragma: no cover
    raise SystemExit("pip install 'fabric-backend[server]'") from e

FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
SQL_SCOPE = "https://database.windows.net/.default"

from .discovery import package_version as _package_version  # noqa: E402

mcp = MCPServer("fabric-backend", version=_package_version(), instructions=(
    "Tables in a Microsoft Fabric lakehouse/warehouse → a GraphQL API with inferred keys and relationships, "
    "plus Rayfin connector entities. Start with list_workspaces (or list_sources if you know the workspace), then plan_backend (nothing is deployed; "
    "it also suggests composite keys), sample_rows when a column's meaning is unclear, validate_plan to check keys and "
    "relationships against the rows, then create_backend. Before query_graphql, describe_backend gives the exact field "
    "names. Every inferred key/relationship carries the rule that produced it (K0–K5, R0–R4); "
    "ambiguous columns are reported, never guessed. From the same plan, without creating anything: semantic_model_draft "
    "(a Power BI model in TMDL, Direct Lake) when a report is the goal; join_path when the user asks how two tables "
    "connect or wants the SQL for it; data_dictionary for hand-over documentation; dbt_schema when the team tests with dbt; "
    "plan_drift before re-running create_backend on an existing API, to see what would change. One plan, five Fabric pieces: "
    "create_backend (the API for GraphQL), create_semantic_model (a Power BI semantic model item from the TMDL draft), "
    "create_ontology (a Fabric IQ ontology item: entity types with keys, relationship types, bindings), create_views (wide T-SQL views in a schema of "
    "their own on the SQL endpoint), create_data_agent (a Fabric data agent with the plan as instructions and examples) — each "
    "answers with what it would create until dry_run=false; app_starter gives a Lovable prompt, connection details, queries and "
    "the Supabase edge function for an app on a created API; app_readiness lists what that API still needs before an app can use "
    "it (introspection, permissions, keys, relationships) with the next step per item. lineage shows which GraphQL APIs, "
    "semantic models, views and data agents in the workspace build on a source's tables and what a change to one table "
    "reaches; plan_drift names those objects for the tables and columns a re-run would drop. analyze_schema reads an unknown lakehouse as a graph (table roles, central tables, "
    "subject areas, cycles, which relationships can be active); suggest_relationships when the plan lacks links: it ranks "
    "candidate columns and checks the best against the data, suggesting only. "
    "A call that cannot be completed answers with error (plain words), "
    "kind (a stable code such as not_found, no_access, capacity, sign_in, consent, schema_not_found, timeout) and "
    "hint (the next step that fixes it). Five first questions that pay off on a lakehouse nobody has documented: "
    "(1) analyze_schema — which tables are facts, which are dimensions, what are the subject areas; (2) plan_backend — the keys "
    "and relationships with the rule behind each; (3) validate_plan — are the keys unique and do the references hold; "
    "(4) suggest_relationships — which columns look like references but are in no relationship; (5) data_dictionary — the "
    "hand-over document with everything above."))


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

_GUID = __import__("re").compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _workspaces(headers: dict) -> list[dict]:
    """Every workspace the signed-in account can see: id, name, type, capacity."""
    import requests
    out, url = [], f"{FABRIC}/v1/workspaces"
    while url:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        body = r.json()
        out += [{"name": w.get("displayName"), "id": w.get("id"), "type": w.get("type"), "capacity_id": w.get("capacityId")}
                for w in body.get("value", [])]
        url = body.get("continuationUri")
    return out


def _workspace_id(workspace: str, headers: dict) -> str:
    """Tools take a workspace id or its display name; a name is looked up (case does not matter)."""
    from .infer import PlanInputError
    w = (workspace or "").strip()
    if _GUID.match(w):
        return w
    if not w:
        raise PlanInputError("workspace: give the workspace id or its name; list_workspaces shows both")
    hits = [x for x in _workspaces(headers) if (x["name"] or "").lower() == w.lower()]
    if len(hits) == 1:
        return hits[0]["id"]
    if not hits:
        raise LookupError(f"no workspace named {w!r} is visible to the signed-in account; list_workspaces shows what is")
    raise PlanInputError(f"{len(hits)} workspaces are named {w!r}; use the id instead: " + ", ".join(h["id"] for h in hits))

def _resolve_source(workspace: str, source: str, headers: dict) -> dict:
    """Lakehouse / warehouse / SQL database by name or id → item dict with sql endpoint host."""
    import requests
    item = find_item_by_name(workspace, source, headers)
    if item is None:
        for t, route in (("Lakehouse", "lakehouses"), ("Warehouse", "warehouses"), ("SQLDatabase", "sqlDatabases"), *ENDPOINT_ITEM_ROUTES.items()):
            r = requests.get(f"{FABRIC}/v1/workspaces/{workspace}/{route}/{source}", headers=headers, timeout=30)
            if r.status_code == 200:
                item = {"type": t, **r.json()}
                break
    if item is None:
        raise LookupError(f"no lakehouse/warehouse/SQL database named or with id {source!r} in workspace {workspace}")
    route = {"Lakehouse": "lakehouses", "Warehouse": "warehouses", "SQLDatabase": "sqlDatabases", **ENDPOINT_ITEM_ROUTES}[item["type"]]
    r = requests.get(f"{FABRIC}/v1/workspaces/{workspace}/{route}/{item['id']}", headers=headers, timeout=30)
    r.raise_for_status()
    props = r.json().get("properties", {})
    ep = props.get("sqlEndpointProperties") or {}
    item["sql_host"] = ep.get("connectionString") or props.get("connectionString") or props.get("connectionInfo")
    # a Fabric SQL database's actual database name carries a suffix (properties.databaseName); the others use the display name
    item["sql_db"] = props.get("databaseName") or item.get("displayName")
    # a lakehouse created with schemas carries properties.defaultSchema (lakehouse/definitions.json: "returned only for
    # schema enabled lakehouse"); the TMDL partitions need schemaName in that case, and must not have it otherwise
    item["schemas_enabled"] = item["type"] != "Lakehouse" or "defaultSchema" in props
    return item


def _execute_factory(item: dict, sql_token: str):
    """DB-API over the SQL analytics endpoint with an Entra access token (ODBC Driver 18)."""
    import pyodbc
    if not item.get("sql_host"):
        raise RuntimeError("source has no SQL endpoint connection string yet")
    tok = sql_token.encode("utf-16-le")
    attrs = {1256: struct.pack("<i", len(tok)) + tok}      # SQL_COPT_SS_ACCESS_TOKEN
    conn = pyodbc.connect(f"Driver={{ODBC Driver 18 for SQL Server}};Server={item['sql_host']};Database={item['sql_db']};Encrypt=yes",
                          attrs_before=attrs, timeout=LOGIN_TIMEOUT)     # a cold or paused endpoint fails as `timeout`, not a hang
    conn.timeout = QUERY_TIMEOUT                                           # per statement; the driver raises HYT00, explained as `timeout`

    def execute(sql: str):
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def statement(sql: str) -> None:                                       # DDL (CREATE OR ALTER VIEW): no rows, committed
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
    execute.close = conn.close
    execute.statement = statement
    return execute


LOGIN_TIMEOUT = 30      # seconds to log in to the SQL analytics endpoint
QUERY_TIMEOUT = 120     # seconds per metadata query


def _plan(workspace: str, source: str, schema: str, keys, confirmed, ctx):
    headers = _headers(ctx)
    workspace = _workspace_id(workspace, headers)
    item = _resolve_source(workspace, source, headers)
    execute = _execute_factory(item, auth.sql(ctx))
    try:
        s = Schema.from_sql(execute, schema)
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
    """The Fabric workspaces the signed-in account can see, with id, name and capacity. The id or the name
    identifies the workspace in every tool."""
    return json.dumps({"workspaces": _workspaces(_headers(ctx))}, indent=2)


@mcp.tool(title="List data sources in a workspace", annotations=RO)
@safe
def list_sources(workspace: str, ctx: Context = None) -> str:
    """Lakehouses, warehouses, SQL databases, Snowflake databases, mirrored databases (Snowflake, Azure SQL, Cosmos DB,
    SAP, ...), mirrored Databricks catalogs and mirrored catalogs in a Fabric workspace (id or name), plus existing API
    for GraphQL items. The display name or id identifies the `source`."""
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
def list_tables(workspace: str, source: str, schema: str = "dbo", tables: list[str] | None = None, detail: str = "auto",
                ctx: Context = None) -> str:
    """Tables and columns (with types) in one schema of a source. Read-only. `tables` narrows the answer to names or
    patterns (["sales_*"]); `detail` is "auto" (full up to 60 tables, then a summary with the column count per table),
    "full" or "summary"."""
    p, _, _ = _plan(workspace, source, schema, None, None, ctx)
    keep = _compact.match_tables(p.schema, tables)
    if _compact.pick_detail(detail, len(keep) if keep is not None else len(p.schema)) == "summary":
        return _bounded(_compact.tables_summary(p.schema, keep), MAX_RESULT_CHARS, _compact.NARROW_HINT)
    return _bounded(_compact.tables_full(p.schema, keep), MAX_RESULT_CHARS, _compact.NARROW_HINT)


@mcp.tool(title="Plan keys and relationships (nothing deployed)", annotations=RO)
@safe
def plan_backend(workspace: str, source: str, schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                 confirmed: list[dict] | None = None, tables: list[str] | None = None, detail: str = "auto",
                 mermaid: bool = True, ctx: Context = None) -> str:
    """Infer keys and relationships for the source's tables. Returns the summary, each relationship with the rule
    that produced it (K0–K5 / R0–R4), ambiguous columns to confirm, keyless tables, names read through the synonym
    table, and a Mermaid ER diagram. Pass `keys` for composite keys ({"order_items": ["order_id","line_no"]}) and
    `confirmed` for relationships the rules missed. `tables` narrows the answer to names or patterns (["sales_*"]);
    the plan is still made from the whole schema. `detail` is "auto" (full up to 60 tables, then one line per key
    and relationship without field names or diagram), "full" or "summary"; mermaid=false leaves the diagram out of a
    full answer. Deploys nothing."""
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
        s = Schema.from_sql(execute, schema)
    except Exception:
        getattr(execute, "close", lambda: None)()
        raise
    if len(s) == 0:
        getattr(execute, "close", lambda: None)()
        raise SchemaEmpty(f"Schema {schema!r} has no tables in {source!r} (workspace {workspace}); it may not exist in this source.")
    return s, execute


@mcp.tool(title="Check the plan against the data", annotations=RO)
@safe
def validate_plan(workspace: str, source: str, schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                  confirmed: list[dict] | None = None, max_items: int = 60, ctx: Context = None) -> str:
    """Check the plan's keys and relationships against the rows, read-only: is each key unique and free of NULLs,
    and does every reference find its target (orphan count)? Returns counts and a verdict per key and relationship.
    It turns name-based suggestions into evidence. Takes the same keys/confirmed as
    plan_backend; runs one small counting query per key and per relationship (max_items caps the total)."""
    s, execute = _connected(workspace, source, schema, ctx)
    try:
        p = make_plan(s, keys, confirmed)
        out = _evidence.validate(p, execute, max_items=max(1, min(int(max_items), 200)))
    finally:
        getattr(execute, "close", lambda: None)()
    return json.dumps(out, indent=2, default=str)


@mcp.tool(title="Show a few rows of a table", annotations=RO)
@safe
def sample_rows(workspace: str, source: str, table: str, schema: str = "dbo", n: int = 10, ctx: Context = None) -> str:
    """The first n rows (at most 20) of one table, read-only, so the meaning of columns can be checked before
    deciding on keys or relationships. Long text values are shortened."""
    s, execute = _connected(workspace, source, schema, ctx)
    try:
        t = next((x for x in s if x.name.lower() == table.lower()), None)
        if t is None:
            return json.dumps({"error": f"no table {table!r} in schema {schema!r} of {source!r}",
                               "kind": "table_not_found", "hint": "list_tables shows the tables in a schema."}, indent=2)
        n = max(1, min(int(n), 20))
        rows = execute(_evidence.sample_sql(schema, t.name, t.column_names, n))
    finally:
        getattr(execute, "close", lambda: None)()

    def short(v):
        v = v if isinstance(v, (int, float, bool)) or v is None else str(v)
        return v[:200] + "…" if isinstance(v, str) and len(v) > 200 else v
    return json.dumps({"table": t.name, "columns": t.column_names,
                       "rows": [{k: short(v) for k, v in r.items()} for r in rows]}, indent=2, default=str)


@mcp.tool(title="Create or update the GraphQL API", annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True,
                                                                               idempotent_hint=True, open_world_hint=True))
@safe
def create_backend(workspace: str, source: str, name: str, schema: str = "dbo", writable: bool = False,
                   keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                   tables: list[str] | None = None, allow_removals: bool = False, ctx: Context = None) -> str:
    """Create a Fabric API for GraphQL item over the source's tables with the inferred relationships — or update
    the item of that name in place. Creates one item; never deletes an item. When an API of that name exists and
    the update would drop relationships it has (often ones confirmed earlier), nothing is written: the answer lists
    them with ready `confirmed` entries; pass those to keep them, or allow_removals=true to drop them on purpose.
    Returns the endpoint URL and the portal steps that remain (introspection, service principal permission)."""
    p, item, headers = _plan(workspace, source, schema, keys, confirmed, ctx)
    check_tables(p.schema, tables)
    source_id, source_type = source_for(workspace, item, headers)
    if not allow_removals:
        lost = _relationships_lost(workspace, name, p, source_id, source_type, writable, tables, headers)
        if lost:
            keep = [u["confirmed"] for u in lost if "confirmed" in u]
            return json.dumps({
                "error": f"updating {name!r} would remove {len(lost)} relationship(s) the API has today; nothing was written.",
                "kind": "would_remove", "relationships_lost": lost, "keep_with_confirmed": keep,
                "hint": "To keep them, call create_backend again with confirmed=keep_with_confirmed (added to any confirmed "
                        "you already pass). To drop them on purpose, call it with allow_removals=true."}, indent=2)
    env = definition(p, name, workspace, source_id, source_type, writable=writable, tables=tables)
    result = deploy(env, workspace, token_provider=lambda: auth.fabric(ctx))
    out = {"summary": p.summary(), "source": {"id": source_id, "type": source_type}, "result": result,
           "skipped_relationships": env.get("skipped_relationships", [])}
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


def _relationships_lost(workspace, name, p, source_id, source_type, writable, tables, headers) -> list[dict]:
    """Relationships an existing API of this name has that the update would drop. A new name, or an API whose
    definition cannot be read, gives [] so that creating still works as before."""
    found = _existing_api(workspace, name, headers)
    if not found:
        return []
    workspace_id, existing = found
    d = _drift.compare(p, existing, name, workspace_id, source_id, source_type, writable=writable, tables=tables)
    return d.get("relationships_unsupported", [])


@mcp.tool(title="Generate Rayfin connector entities", annotations=RO)
@safe
def rayfin_connector(workspace: str, source: str, connector: str = "data", schema: str = "dbo",
                     keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                     tables: list[str] | None = None, relationships: bool = True, ctx: Context = None) -> str:
    """Rayfin (Fabric Apps) connector entity classes + schema.ts for the source's tables, with inferred keys and
    @one/@many relationships (sourceFields/targetFields spelled out). Returns {path: content}; nothing is deployed."""
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
def ontology_draft(workspace: str, source: str, name: str = "ontology", schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                   confirmed: list[dict] | None = None, tables: list[str] | None = None, ctx: Context = None) -> str:
    """The inferred entity types, keys and relationships as a Fabric IQ ontology (preview) draft: a summary with the
    rule behind every key and link, the binding checklist, a Turtle file the portal's Import ontology accepts, and the
    generation-2 item definition (TMDL parts) ready for POST /ontologies or Git. Deploys nothing. `tables` keeps
    it small; the definition is the same information as plan_backend, in Fabric IQ's shape."""
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
def create_ontology(workspace: str, source: str, name: str, schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                    confirmed: list[dict] | None = None, tables: list[str] | None = None, dry_run: bool = True,
                    ctx: Context = None) -> str:
    """Create the Fabric IQ ontology (preview) item from the plan, or update the item of that name in place; never
    deletes. dry_run=true (the default) returns the definition parts and the REST call without creating anything.
    POST /workspaces/{id}/ontologies and .../updateDefinition need the delegated permission Item.ReadWrite.All and
    Contributor on the workspace, and the workspace must be on a Fabric capacity (fabric-rest-api-specs,
    ontology/swagger.json). Entity types with keys and properties, relationship types and the bindings come from the
    same plan as the GraphQL API, the semantic model, the views and the data agent."""
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
                    "entities, tables, relationships), checked against recorded definitions. The dry run and the create have not yet run against a live workspace.")}
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
def semantic_model_draft(workspace: str, source: str, name: str = "semantic_model", schema: str = "dbo",
                         keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                         tables: list[str] | None = None, ctx: Context = None) -> str:
    """The plan as a Power BI semantic model in TMDL: one table per source table in Direct Lake mode on the source's
    SQL analytics endpoint, relationships with cardinality and filter direction (one active path per table pair, the
    rest inactive with the reason), keyless tables without relationships into them. Returns {path: content} for the
    definition/ folder plus README.generated.md listing every decision to check. `tables` takes names or patterns
    (["sales_*"]); on a large schema the table files are left out of the answer and `tables` gets them a few at a
    time. Creates nothing in Fabric."""
    p, info = _source_inputs(workspace, source, schema, keys, confirmed, ctx)
    keep = _compact.match_tables(p.schema, tables)
    tables = sorted(keep, key=str.lower) if keep is not None else None
    out = _semantic_model.draft(p, info, name, tables)
    out["note"] = ("Unit-tested against Microsoft's published TMDL samples; drafted from a live lakehouse on 26 October 2026, "
                   "not yet created as an item. Open the "
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


@mcp.tool(title="Shortest join path between two tables", annotations=RO)
@safe
def join_path(workspace: str, source: str, start: str, end: str, schema: str = "dbo",
              keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None, ctx: Context = None) -> str:
    """How two tables connect through the plan's relationships: the shortest chain of hops with the rule per step and
    a ready T-SQL SELECT … JOIN … with quoted identifiers (equally short paths are all listed). When no path exists it
    says so and suggests which relationship is missing, as a `confirmed` entry. Reads metadata only."""
    p, _, _ = _plan(workspace, source, schema, keys, confirmed, ctx)
    return json.dumps(_paths.join_path(p, start, end), indent=2)


@mcp.tool(title="Analyse the schema as a graph (roles, centrality, areas, ambiguity)", annotations=RO)
@safe
def analyze_schema(workspace: str, source: str, schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                   confirmed: list[dict] | None = None, tables: list[str] | None = None, detail: str = "auto",
                   ctx: Context = None) -> str:
    """The plan as a graph, from metadata only (no data queries): each table's role (fact, dimension, bridge,
    isolated) with the numbers behind it, the ten most central tables (in/out degree, betweenness, PageRank),
    subject areas, cycles and table pairs with more than one path (where a Power BI model gets ambiguous filter
    paths), and the relationships that can be active at once in a semantic model with the rest explained as inactive.
    Useful on a lakehouse nobody has documented. `tables` narrows the answer to names or patterns; `detail` is
    "auto" (full up to 60 tables, then tables grouped by role, the central tables, areas by size and counts), "full"
    or "summary"."""
    p, _, _ = _plan(workspace, source, schema, keys, confirmed, ctx)
    keep = _compact.match_tables(p.schema, tables)
    out = _graphs.analyze(p)
    out["summary"] = p.summary().splitlines()[0] + "; " + out["summary"]
    if _compact.pick_detail(detail, len(keep) if keep is not None else len(p.schema)) == "summary":
        return _bounded(_compact.analysis_summary(out, keep), MAX_RESULT_CHARS, _compact.NARROW_HINT)
    return _bounded(_compact.analysis_filtered(out, keep), MAX_RESULT_CHARS, _compact.NARROW_HINT)


@mcp.tool(title="Suggest missing relationships, checked against the data", annotations=RO)
@safe
def suggest_relationships(workspace: str, source: str, schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                          confirmed: list[dict] | None = None, check: int = 15, ctx: Context = None) -> str:
    """Columns that could point at another table's key but are in no relationship, ranked by name similarity, type
    and triangular closure, then the best `check` (default 15) counted against the data: the share of the column's
    values that exist in the target key and how many distinct values it has. Suggestions only — nothing is applied;
    each one carries a ready `confirmed` entry for plan_backend or create_backend. Read-only counting queries."""
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
def data_dictionary(workspace: str, source: str, schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                    confirmed: list[dict] | None = None, validate: bool = False, max_items: int = 60,
                    tables: list[str] | None = None, ctx: Context = None) -> str:
    """Hand-over documentation for the source: every table with columns and types, keys and relationships with their
    rules, keyless tables, ambiguous columns and the ER diagram, with an empty Description column to fill in. With
    validate=true the counts from validate_plan (key uniqueness, orphans) are included. `tables` takes names or
    patterns (["sales_*"]) for one part of a large schema at a time; an answer over 60 000 characters is cut on a line
    and says so. Returns Markdown."""
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
    shown = _compact.sub_plan(p, keep)
    md = _dictionary.data_dictionary(shown, source, schema, checked, product=os.environ.get("PRODUCT_NAME", "Krusgraph"))
    return _compact.bounded_text({"path": f"docs/{source}-{schema}-data-dictionary.md", "markdown": md, "summary": p.summary()}, "markdown", MAX_RESULT_CHARS)


@mcp.tool(title="dbt schema.yml with source tests", annotations=RO)
@safe
def dbt_schema(workspace: str, source: str, schema: str = "dbo", source_name: str | None = None,
               keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
               tables: list[str] | None = None, arguments_block: bool = True, ctx: Context = None) -> str:
    """A dbt sources file for the schema: `unique` and `not_null` on every inferred key column and `relationships`
    on every single-column relationship, in the syntax the dbt documentation gives (test arguments under
    `arguments:`; arguments_block=false writes them top-level for dbt before 1.10.5). Composite keys and
    composite-column relationships are noted as comments. `tables` takes names or patterns (["sales_*"]); an
    answer over 60 000 characters is cut on a line and says so. Returns the YAML text."""
    p, item, _ = _plan(workspace, source, schema, keys, confirmed, ctx)
    keep = _compact.match_tables(p.schema, tables)
    tables = sorted(keep, key=str.lower) if keep is not None else None
    src = source_name or schema
    yml = _dbt.schema_yml(p, src, schema, database=item.get("sql_db") or item.get("displayName") or source,
                         tables=tables, arguments_block=arguments_block)
    return _compact.bounded_text({"path": f"models/sources/{src}.yml", "yaml": yml, "summary": p.summary()}, "yaml", MAX_RESULT_CHARS)


@mcp.tool(title="Compare today's plan with an existing GraphQL API", annotations=RO)
@safe
def plan_drift(workspace: str, source: str, api: str, schema: str = "dbo", keys: dict[str, list[str]] | None = None,
               confirmed: list[dict] | None = None, tables: list[str] | None = None, writable: bool = False,
               ctx: Context = None) -> str:
    """Today's plan against the definition of an existing API for GraphQL item (name or id): new tables and
    columns, columns the API still maps that the source no longer has, relationships the plan no longer supports,
    and whether a create_backend with the same name would change anything. Changes nothing."""
    p, item, headers = _plan(workspace, source, schema, keys, confirmed, ctx)
    check_tables(p.schema, tables)
    workspace_id = _workspace_id(workspace, headers)
    api_id = _api_id(workspace_id, api, headers)
    if not api_id:
        return json.dumps({"error": f"no API for GraphQL named {api!r} in workspace {workspace}", "kind": "not_found",
                           "hint": "list_sources lists the GraphQL APIs in a workspace."}, indent=2)
    existing = _graphql_definition(workspace_id, api_id, headers)
    source_id, source_type = source_for(workspace_id, item, headers)
    out = _drift.compare(p, existing, api, workspace_id, source_id, source_type, writable=writable, tables=tables)
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


def _consent(result: dict, scope: str, where: str) -> dict | None:
    """A 401/403 from a create call is almost always a missing delegated permission: say exactly which one."""
    http = result.get("http")
    if http in (401, 403):
        return {"error": f"Fabric refused {where} (HTTP {http}): the token does not carry the delegated permission this needs.",
                "kind": "consent",
                "hint": f"The Entra app needs the delegated permission {scope} and an administrator's consent, then sign in again. "
                        "docs/SCOPES.md in the repository lists the exact az commands."}
    return None


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
def create_semantic_model(workspace: str, source: str, name: str, schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                          confirmed: list[dict] | None = None, tables: list[str] | None = None, dry_run: bool = True,
                          ctx: Context = None) -> str:
    """Create a Fabric SemanticModel item from the TMDL draft (Direct Lake on the source's SQL analytics endpoint), or
    update the item of that name in place; never deletes. dry_run=true (the default) returns exactly what would be
    sent — the parts and the REST call — without creating anything. Needs the delegated permission
    SemanticModel.ReadWrite.All or Item.ReadWrite.All and Contributor on the workspace. After creation the model may
    need a first refresh (framing) and, in the portal, a connection/credential for the endpoint."""
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
           "note": "Unit-tested against Microsoft's sample definitions; the dry run has answered from a live workspace (26 October 2026); "
                   "the create itself answered kind=consent there (HTTP 403) because the app lacks the permission, see docs/SCOPES.md."}
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
def create_views(workspace: str, source: str, schema: str = "dbo", views_schema: str = "krusgraph",
                 keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None, dry_run: bool = True,
                 ctx: Context = None) -> str:
    """Wide views over the plan in the source's SQL analytics endpoint or warehouse, only inside `views_schema`
    (created if missing): one per fact table with its dimensions joined in, plus one per relationship that is hard
    to read from the names. CREATE OR ALTER VIEW only — never DROP, never anything outside that schema; identifiers
    come from the source's metadata. dry_run=true returns the SQL. Needs rights to create objects on the endpoint
    (Contributor on the workspace is enough for a warehouse or a lakehouse's endpoint)."""
    s, execute = _connected(workspace, source, schema, ctx)
    try:
        p = make_plan(s, keys, confirmed)
        stmts = _views.statements(p, views_schema)
        out = {"summary": p.summary(), "schema": views_schema, "dry_run": dry_run, "schema_sql": stmts["schema_sql"], "views": stmts["views"],
               "note": "Views are allowed on a lakehouse SQL analytics endpoint, a warehouse and the endpoints of mirrored and SQL "
                       "database items (read-only data, writable T-SQL objects). Unit-tested on SQLite and against the shop schema; "
                       "ran for real on a live lakehouse SQL analytics endpoint on 26 October 2026 (schema and one wide view created, read back with list_tables and sample_rows)."}
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
def create_data_agent(workspace: str, source: str, name: str, schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                      confirmed: list[dict] | None = None, publish: bool = True, dry_run: bool = True, ctx: Context = None) -> str:
    """A Fabric data agent over the source: the plan (tables, keys, relationships with rules, join paths) as its
    instructions, the source as its data source with the plan's tables selected, and 5–10 example question/T-SQL
    pairs, then published. Created through the public staging REST API; re-running updates the same agent, data
    source and examples in place and deletes nothing. dry_run=true returns the instructions, examples and REST calls
    to review. Needs the delegated permission Item.ReadWrite.All (or DataAgent.ReadWrite.All for the staging calls)."""
    p, info = _source_inputs(workspace, source, schema, keys, confirmed, ctx)
    spec = _data_agent.draft(p, info, name, schema)
    out = {"summary": p.summary(), "dry_run": dry_run, "agent": {k: spec[k] for k in ("name", "instructions", "datasource", "datasource_instructions", "tables_to_select", "fewshots")},
           "rest": spec["rest"], "delegated_scope": spec["delegated_scope"],
           "note": "Unit-tested with the REST calls mocked; the dry run has answered from a live workspace (26 October 2026); the create "
                   "itself answered kind=consent there (HTTP 403) because the app lacks the permission, see docs/SCOPES.md. The portal shows the agent's data source, "
                   "selected tables and example queries under its staging configuration; publish makes them live."}
    if dry_run:
        return json.dumps(out, indent=2)
    headers = _headers(ctx)
    try:
        result = _data_agent.apply(spec, info["workspace_id"], headers, publish=publish)
    except _data_agent.RestError as e:
        result = {"status": "Failed", "http": e.status, "body": e.body, "step": e.what}
    return _finish_create(out, result, "Item.ReadWrite.All (or DataAgent.ReadWrite.All)", f"creating the data agent {name!r}")


@mcp.tool(title="Starter pack for an app on a GraphQL API", annotations=RO)
@safe
def app_starter(workspace: str, api: str, ctx: Context = None) -> str:
    """Everything needed to start an app on a created API for GraphQL item, read from its definition: a Lovable
    prompt describing the data model and the main views, a connection description, five GraphQL queries that walk
    the relationships, and the manual portal steps (introspection, permissions). Generates text only."""
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
def app_readiness(workspace: str, api: str, ctx: Context = None) -> str:
    """For an existing API for GraphQL item (name or id): what is in place and what is missing before an app can use it.
    Reads the item's definition (types without a key, types in no relationship, write access) and sends one
    introspection query to the endpoint to see whether introspection is on; permissions and the tenant setting for
    service principals cannot be read through the Fabric API and are reported as unknown with the portal path.
    Each item carries its next step."""
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
    """Every item in the workspace (id, displayName, type), all pages."""
    out, url = [], f"{FABRIC}/v1/workspaces/{workspace}/items"
    while url:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        body = r.json()
        out += body.get("value", [])
        url = body.get("continuationUri")
    return out


def _item_definition_parts(workspace: str, route: str, item_id: str, headers: dict, fmt: str | None = None) -> dict[str, str]:
    """{path: text} of an item's definition (POST /workspaces/{ws}/{route}/{id}/getDefinition, long-running when Fabric says so)."""
    from .deploy import wait_operation
    url = f"{FABRIC}/v1/workspaces/{workspace}/{route}/{item_id}/getDefinition" + (f"?format={fmt}" if fmt else "")
    r = requests.post(url, headers=headers, timeout=60)
    status = getattr(r, "status_code", 200)
    if status == 202:
        op = r.headers.get("x-ms-operation-id") or r.headers.get("Location", "").rstrip("/").split("/")[-1]
        result = wait_operation(op, headers, poll_seconds=2, max_polls=30)
        if result.get("status") != "Succeeded":
            raise RuntimeError(f"reading the definition did not finish: {result.get('status')}")
        r = requests.get(f"{FABRIC}/v1/operations/{op}/result", headers=headers, timeout=60)
        status = getattr(r, "status_code", 200)
    if status >= 400:
        r.raise_for_status()
    return _lineage.decode_parts((r.json().get("definition") or {}).get("parts", []))


def _lineage_edges(workspace_id: str, item: dict, schema: str, tables: set[str], headers: dict, execute=None) -> tuple[list[dict], list[dict]]:
    """Edges table -> object over every item in the workspace that can be read, plus the items that could not."""
    from .errors import explain
    source_id = item.get("id")
    databases = {item.get("sql_db") or "", item.get("displayName") or ""}
    edges: list[dict] = []
    skipped: list[dict] = []
    for it in _workspace_items(workspace_id, headers):
        kind, meta = it.get("type"), {"id": it.get("id"), "displayName": it.get("displayName")}
        try:
            if kind == "GraphQLApi":
                edges += _lineage.from_graphql_definition(_graphql_definition(workspace_id, it["id"], headers), meta, source_id, schema, tables)
            elif kind == "SemanticModel":
                edges += _lineage.from_tmdl_parts(_item_definition_parts(workspace_id, "semanticModels", it["id"], headers, fmt="TMDL"), meta, databases, schema, tables)
            elif kind == "DataAgent":
                edges += _lineage.from_data_agent_parts(_item_definition_parts(workspace_id, "dataAgents", it["id"], headers), meta, source_id, schema, tables)
        except Exception as e:  # noqa: BLE001 — one unreadable item must not hide the rest
            skipped.append({"item": it.get("displayName"), "kind": kind, "reason": explain(e, f"reading {it.get('displayName')!r}").get("kind", "unexpected")})
    if execute is not None:
        try:
            rows = list(execute(_lineage.VIEW_USAGE_SQL))
        except Exception:  # noqa: BLE001 — an endpoint without INFORMATION_SCHEMA.VIEW_TABLE_USAGE: try the sys view
            try:
                rows = list(execute(_lineage.VIEW_USAGE_SQL_SYS))
            except Exception as e:  # noqa: BLE001
                rows = []
                skipped.append({"item": "views on the SQL endpoint", "kind": "View", "reason": explain(e, "reading view dependencies").get("kind", "unexpected")})
        edges += _lineage.from_view_rows(rows, item, schema, tables)
    return edges, skipped


@mcp.tool(title="Lineage: what builds on a source's tables", annotations=RO)
@safe
def lineage(workspace: str, source: str, schema: str = "dbo", table: str | None = None, ctx: Context = None) -> str:
    """Which Fabric objects in the workspace build on the source's tables: GraphQL APIs (from their definition),
    semantic models (from their TMDL definition), views on the SQL analytics endpoint (INFORMATION_SCHEMA.VIEW_TABLE_USAGE)
    and data agents (named in their definition). Returns a graph (nodes: tables and objects; edges: used by), the
    objects per table, the tables used by nothing, the items that could not be read, and with `table` the answer to
    what a change to that table reaches. Read-only."""
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
    """graphql-definition.json of an API for GraphQL item (getDefinition, long-running when Fabric says so)."""
    import base64
    import requests
    from .deploy import wait_operation
    r = requests.post(f"{FABRIC}/v1/workspaces/{workspace}/items/{api_id}/getDefinition", headers=headers, timeout=60)
    status = getattr(r, "status_code", 200)
    if status == 202:
        op = r.headers.get("x-ms-operation-id") or r.headers.get("Location", "").rstrip("/").split("/")[-1]
        result = wait_operation(op, headers, poll_seconds=2, max_polls=30)
        if result.get("status") != "Succeeded":
            raise RuntimeError(f"reading the API definition did not finish: {result.get('status')}")
        r = requests.get(f"{FABRIC}/v1/operations/{op}/result", headers=headers, timeout=60)
        status = getattr(r, "status_code", 200)
    if status >= 400:
        r.raise_for_status()
    parts = (r.json().get("definition") or {}).get("parts", [])
    part = next((x for x in parts if x.get("path") == "graphql-definition.json"), None)
    if not part:
        raise RuntimeError("the API has no graphql-definition.json part")
    return json.loads(base64.b64decode(part["payload"]))


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
def describe_backend(workspace: str, api: str, ctx: Context = None) -> str:
    """Types, fields and relationships of an existing API for GraphQL item (name or id), in the names a query
    uses — read from the item's definition, so it works without introspection; these are the names a GraphQL query uses."""
    headers = _headers(ctx)
    workspace = _workspace_id(workspace, headers)
    api_id = _api_id(workspace, api, headers)
    if not api_id:
        return json.dumps({"error": f"no API for GraphQL named {api!r} in workspace {workspace}", "kind": "not_found",
                           "hint": "list_sources lists the GraphQL APIs in a workspace."}, indent=2)
    return json.dumps(describe_definition(_graphql_definition(workspace, api_id, headers)), indent=2)


@mcp.tool(title="Run a GraphQL query", annotations=RO)
@safe
def query_graphql(workspace: str, api: str, query: str, variables: dict | None = None, ctx: Context = None) -> str:
    """Run a read-only GraphQL query against a Microsoft Fabric API for GraphQL item (name or id) in the workspace,
    see https://learn.microsoft.com/fabric/data-engineering/api-graphql-overview. Query fields are named <type>s,
    e.g. `{ customers(first: 5) { items { customer_id name } } }`; relationships nest; describe_backend lists the
    exact names. Mutations and subscriptions are refused."""
    import requests
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

    def page_route(path: str, fn):
        async def handler(request):
            headers = {"Cache-Control": PAGE_CACHE, **PAGE_HEADERS}
            if path == "/mascots":
                headers["X-Robots-Tag"] = "noindex, nofollow"
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

    async def plan_json(request):
        return compressed(request, demo_plan_json().encode("utf-8"), "application/json", {"Cache-Control": "public, max-age=3600"})
    app.router.routes.append(Route("/demo/plan.json", plan_json))

    async def validation_json(request):
        return compressed(request, demo_validation_json().encode("utf-8"), "application/json", {"Cache-Control": "public, max-age=3600"})
    app.router.routes.append(Route("/demo/validation.json", validation_json))

    TEXT_STATIC = {".css", ".js", ".svg", ".txt", ".json"}       # woff2 and png are already compressed

    async def static(request):
        p = static_file(request.path_params.get("path", ""))
        if p is None:
            return PlainTextResponse("not found", status_code=404)
        cache = "public, max-age=31536000, immutable" if request.query_params.get("v") else "public, max-age=86400"
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
    from . import dcr as _dcr

    async def prm(_request):
        meta = protected_resource_metadata(cfg)
        if _dcr.enabled():                                        # agents that register themselves find the facade first
            meta["authorization_servers"] = [_dcr.origin(cfg)] + meta["authorization_servers"]
        return JSONResponse(meta)
    app.router.routes.append(Route("/.well-known/oauth-protected-resource", prm))
    app.router.routes.append(Route("/.well-known/oauth-protected-resource/mcp", prm))

    if _dcr.enabled():                                            # KRUSGRAPH_DCR=1: see fabric_backend/dcr.py and docs/AUTH-DCR.md
        async def asm(_request):
            return JSONResponse(_dcr.authorization_server_metadata(cfg))

        async def register(request):
            raw = await request.body()
            if len(raw) > _dcr.MAX_BODY:
                return JSONResponse({"error": "invalid_client_metadata", "error_description": "request too large"}, status_code=413)
            try:
                body = _json.loads(raw) if raw else {}
            except ValueError:
                body = None
            status, out = _dcr.register(cfg, body)
            return JSONResponse(out, status_code=status, headers={"Cache-Control": "no-store"})
        app.router.routes.append(Route("/.well-known/oauth-authorization-server", asm))
        app.router.routes.append(Route("/oauth/register", register, methods=["POST"]))

    inner = app

    async def guarded(scope, receive, send):
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
