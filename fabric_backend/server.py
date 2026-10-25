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

Tools (all annotated for the Claude directory): list_workspaces, list_sources, list_tables, plan_backend,
create_backend, rayfin_connector, query_graphql.
"""
from __future__ import annotations

import json
import os
import struct
import time

from .infer import check_tables, plan as make_plan
from .schema import Schema
from .graphql import definition
from .deploy import FABRIC, deploy, connection_card, find_item_by_name, source_for, SOURCE_ITEM_TYPES
from .rayfin import rayfin_files
from .errors import SchemaEmpty, classify_http, safe

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
    "plus Rayfin connector entities. Start with list_workspaces (or list_sources if you know the workspace), then plan_backend (nothing is deployed), then "
    "create_backend. Every inferred key/relationship carries the rule that produced it (K0–K3, R0–R3); "
    "ambiguous columns are reported, never guessed. A call that cannot be completed answers with error (plain words), "
    "kind (a stable code such as not_found, no_access, capacity, sign_in, consent, schema_not_found, timeout) and "
    "hint (what to do next); relay the hint to the user rather than retrying blindly."))


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
        for t, route in (("Lakehouse", "lakehouses"), ("Warehouse", "warehouses"), ("SQLDatabase", "sqlDatabases")):
            r = requests.get(f"{FABRIC}/v1/workspaces/{workspace}/{route}/{source}", headers=headers, timeout=30)
            if r.status_code == 200:
                item = {"type": t, **r.json()}
                break
    if item is None:
        raise LookupError(f"no lakehouse/warehouse/SQL database named or with id {source!r} in workspace {workspace}")
    route = {"Lakehouse": "lakehouses", "Warehouse": "warehouses", "SQLDatabase": "sqlDatabases", "MirroredDatabase": "mirroredDatabases"}[item["type"]]
    r = requests.get(f"{FABRIC}/v1/workspaces/{workspace}/{route}/{item['id']}", headers=headers, timeout=30)
    r.raise_for_status()
    props = r.json().get("properties", {})
    ep = props.get("sqlEndpointProperties") or {}
    item["sql_host"] = ep.get("connectionString") or props.get("connectionString") or props.get("connectionInfo")
    item["sql_db"] = item.get("displayName")
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
    execute.close = conn.close
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


@mcp.tool(title="List workspaces", annotations=RO)
@safe
def list_workspaces(ctx: Context = None) -> str:
    """The Fabric workspaces the signed-in account can see, with id, name and capacity. Start here if you do not
    know the workspace id; the other tools take the id or the name."""
    return json.dumps({"workspaces": _workspaces(_headers(ctx))}, indent=2)


@mcp.tool(title="List data sources in a workspace", annotations=RO)
@safe
def list_sources(workspace: str, ctx: Context = None) -> str:
    """Lakehouses, warehouses, SQL databases and mirrored databases in a Fabric workspace (id or name), plus existing
    API for GraphQL items. Use the display name or id as `source` in the other tools."""
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
def list_tables(workspace: str, source: str, schema: str = "dbo", ctx: Context = None) -> str:
    """Tables and columns (with types) in one schema of a source. Read-only."""
    p, _, _ = _plan(workspace, source, schema, None, None, ctx)
    return json.dumps({t.name: [[c.name, c.data_type] for c in t.columns] for t in p.schema}, indent=2)


@mcp.tool(title="Plan keys and relationships (nothing deployed)", annotations=RO)
@safe
def plan_backend(workspace: str, source: str, schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                 confirmed: list[dict] | None = None, ctx: Context = None) -> str:
    """Infer keys and relationships for the source's tables. Returns the summary, each relationship with the rule
    that produced it (K0–K3 / R0–R3), ambiguous columns to confirm, keyless tables, and a Mermaid ER diagram.
    Pass `keys` for composite keys ({"order_items": ["order_id","line_no"]}) and `confirmed` for relationships
    the rules missed. Deploys nothing."""
    p, _, _ = _plan(workspace, source, schema, keys, confirmed, ctx)
    return json.dumps({
        "summary": p.summary(),
        "keys": {t: {"columns": k, "rule": r} for t, (k, r) in p.keys.items()},
        "relationships": [r.__dict__ for r in p.relationships],
        "ambiguous": p.ambiguous, "keyless": p.keyless, "mermaid": p.mermaid(),
    }, indent=2)


@mcp.tool(title="Create or update the GraphQL API", annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False,
                                                                               idempotent_hint=True, open_world_hint=True))
@safe
def create_backend(workspace: str, source: str, name: str, schema: str = "dbo", writable: bool = False,
                   keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                   tables: list[str] | None = None, ctx: Context = None) -> str:
    """Create a Fabric API for GraphQL item over the source's tables with the inferred relationships — or update
    the item of that name in place. Creates one item; never deletes anything. Returns the endpoint URL and the
    portal steps that remain (introspection, service principal permission)."""
    p, item, headers = _plan(workspace, source, schema, keys, confirmed, ctx)
    check_tables(p.schema, tables)
    source_id, source_type = source_for(workspace, item, headers)
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


@mcp.tool(title="Generate Rayfin connector entities", annotations=RO)
@safe
def rayfin_connector(workspace: str, source: str, connector: str = "data", schema: str = "dbo",
                     keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                     tables: list[str] | None = None, relationships: bool = True, ctx: Context = None) -> str:
    """Rayfin (Fabric Apps) connector entity classes + schema.ts for the source's tables, with inferred keys and
    @one/@many relationships (sourceFields/targetFields spelled out). Returns {path: content}; nothing is deployed."""
    p, item, _ = _plan(workspace, source, schema, keys, confirmed, ctx)
    check_tables(p.schema, tables)
    st = {"Lakehouse": "SqlAnalyticsEndpoint", "MirroredDatabase": "SqlAnalyticsEndpoint", "Warehouse": "Warehouse",
          "SQLDatabase": "SqlDbNative"}.get(item["type"], "SqlAnalyticsEndpoint")
    return json.dumps(rayfin_files(p, connector, st, tables=tables, relationships=relationships), indent=2)


@mcp.tool(title="Run a GraphQL query", annotations=RO)
@safe
def query_graphql(workspace: str, api: str, query: str, variables: dict | None = None, ctx: Context = None) -> str:
    """Run a read-only GraphQL query against an API for GraphQL item (name or id) in the workspace. Query fields
    are named <type>s, e.g. `{ customers(first: 5) { items { customer_id name } } }`; relationships nest.
    Mutations are refused."""
    import requests
    from graphql import GraphQLError, OperationType, parse
    from graphql.language import FragmentDefinitionNode, OperationDefinitionNode
    try:
        document = parse(query, max_tokens=10000)
    except GraphQLError:
        return json.dumps({"error": "invalid GraphQL query"})
    operations = [node for node in document.definitions if isinstance(node, OperationDefinitionNode)]
    if any(node.operation != OperationType.QUERY for node in operations):
        return json.dumps({"error": "mutations and subscriptions are not allowed through this tool"})
    if len(operations) != 1 or any(not isinstance(node, (OperationDefinitionNode, FragmentDefinitionNode))
                                   for node in document.definitions):
        return json.dumps({"error": "provide exactly one GraphQL query operation"})
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


def _bounded(body, limit: int) -> str:
    """The query result as JSON of at most `limit` characters, always valid JSON. A result that is too large has
    its lists cut to the same number of leading items each and says so under `truncated`, instead of being
    chopped mid-document."""
    text = json.dumps(body, indent=2, default=str)
    if len(text) <= limit:
        return text

    def longest(node) -> int:
        if isinstance(node, list):
            return max([len(node)] + [longest(x) for x in node])
        if isinstance(node, dict):
            return max([0] + [longest(v) for v in node.values()])
        return 0

    def cut(node, keep):
        if isinstance(node, list):
            return [cut(x, keep) for x in node[:keep]]
        if isinstance(node, dict):
            return {k: cut(v, keep) for k, v in node.items()}
        return node

    keep = longest(body)
    while keep > 1:
        keep //= 2
        slim = cut(body, keep) if isinstance(body, dict) else body
        slim = dict(slim, truncated=f"The full result was too large for one answer; every list was cut to its first {keep} items. "
                                    "Ask for fewer fields or page with first:/after.")
        text = json.dumps(slim, indent=2, default=str)
        if len(text) <= limit:
            return text
    preview = json.dumps(body, default=str)[:limit - 400]
    return json.dumps({"truncated": "The result was too large for one answer even with one item per list; this is the start of it. "
                                    "Ask for fewer fields.", "preview": preview}, indent=2)


MAX_BODY_BYTES = 4 * 1024 * 1024      # an MCP message is a few kilobytes; nothing here needs more than this


def _with_security_headers(app):
    """Every HTTP response, /mcp included: HSTS (the server is only ever reached over HTTPS; Container Apps
    redirects plain HTTP) and nosniff. A request that announces a body over MAX_BODY_BYTES is refused with 413
    before anything reads it. Pure ASGI so streamed MCP responses are untouched apart from the headers."""
    from starlette.datastructures import Headers, MutableHeaders
    from starlette.responses import JSONResponse

    async def wrapped(scope, receive, send):
        if scope["type"] != "http":
            return await app(scope, receive, send)
        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            app_ = JSONResponse({"error": f"request body over {MAX_BODY_BYTES} bytes"}, status_code=413)
        else:
            app_ = app

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("Strict-Transport-Security", "max-age=31536000")
                headers.setdefault("X-Content-Type-Options", "nosniff")
            await send(message)
        return await app_(scope, receive, send_with_headers)
    return wrapped


def build_app(host: str = "0.0.0.0"):
    """The ASGI app: the MCP endpoint at /mcp, plus — in Entra mode — the protected resource metadata and a
    401 challenge in front of /mcp for any request without a valid token (Claude starts sign-in on the 401)."""
    import json as _json
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route

    app = mcp.streamable_http_app(stateless_http=True, host=host)
    cfg = auth.entra

    async def health(_request):
        body = {"ok": True, "auth": "entra" if cfg else "bearer-or-service-principal"}
        if os.environ.get("KRUSGRAPH_BUILD"):      # the source tag the deploy script built; lets it tell revisions apart
            body["build"] = os.environ["KRUSGRAPH_BUILD"]
        return JSONResponse(body)
    app.router.routes.append(Route("/healthz", health))

    from starlette.responses import FileResponse, HTMLResponse, PlainTextResponse
    from .pages import (PAGES, STATIC_TYPES, docs_html, docs_md, lovable_html, lovable_md, not_found_html, privacy_html,
                        privacy_md, render, start_md, static_file)
    from . import discovery
    from .demo import demo_plan_json

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

    # The same content as Markdown, for /llms.txt and agents.
    def md_route(path: str, fn):
        async def handler(request):
            return compressed(request, fn().encode("utf-8"), "text/markdown; charset=utf-8", {"Cache-Control": PAGE_CACHE})
        app.router.routes.append(Route(path, handler))
    for path, fn in (("/docs.md", docs_md), ("/privacy.md", privacy_md), ("/start.md", start_md), ("/lovable.md", lovable_md)):
        md_route(path, fn)

    async def llms(request):
        return compressed(request, discovery.llms_txt().encode("utf-8"), "text/plain; charset=utf-8", {"Cache-Control": PAGE_CACHE})
    app.router.routes.append(Route("/llms.txt", llms))

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

    inner = app

    async def guarded(scope, receive, send):
        if scope["type"] == "http" and scope["path"].rstrip("/") == "/mcp":
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            a = headers.get("authorization", "")
            err = "invalid_request"
            if a.lower().startswith("bearer "):
                try:
                    auth.validator.validate(a[7:].strip())
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
        uvicorn.run(build_app(a.host), host=a.host, port=a.port, proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
