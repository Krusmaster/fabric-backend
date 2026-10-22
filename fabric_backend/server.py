"""Remote MCP server (Streamable HTTP): your Fabric tables, with keys, relationships and rules,
for Claude, Cursor and Lovable.

    fabric-backend-server                      # http://0.0.0.0:8000/mcp
    FABRIC_TENANT_ID / FABRIC_CLIENT_ID / FABRIC_CLIENT_SECRET   a service principal with access to the workspaces

Authentication, in order:
  1. `Authorization: Bearer <token>` on the request — a Fabric API token (audience api.fabric.microsoft.com);
     `X-Fabric-SQL-Token` carries the SQL analytics endpoint token (audience database.windows.net) when the
     caller has one. This is what an OAuth front (Entra on-behalf-of) will supply.
  2. Otherwise the server's own service principal mints both tokens (client credentials). This is the
     "custom connection" model Lovable's Fabric connector uses: one principal, no per-user identity.
The server stores nothing: no tokens beyond their lifetime, no data, no query results.

Tools (all annotated for the Claude directory): list_sources, list_tables, plan_backend,
create_backend, rayfin_connector, query_graphql.
"""
from __future__ import annotations

import json
import os
import struct
import time

from .infer import plan as make_plan
from .schema import Schema
from .graphql import definition
from .deploy import FABRIC, deploy, connection_card, find_item_by_name, source_for, SOURCE_ITEM_TYPES
from .rayfin import rayfin_files

try:
    from mcp.server.mcpserver import MCPServer, Context
    from mcp.types import ToolAnnotations
except ImportError as e:  # pragma: no cover
    raise SystemExit("pip install 'fabric-backend[server]'") from e

FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
SQL_SCOPE = "https://database.windows.net/.default"

mcp = MCPServer("fabric-backend", instructions=(
    "Tables in a Microsoft Fabric lakehouse/warehouse → a GraphQL API with inferred keys and relationships, "
    "plus Rayfin connector entities. Start with list_sources, then plan_backend (nothing is deployed), then "
    "create_backend. Every inferred key/relationship carries the rule that produced it (K0–K3, R0–R3); "
    "ambiguous columns are reported, never guessed."))


# ------------------------------------------------------------------ auth ---------------------

class Auth:
    """Tokens for the two audiences the server talks to. Request headers win; else client credentials."""

    def __init__(self) -> None:
        self.tenant = os.environ.get("FABRIC_TENANT_ID")
        self.client = os.environ.get("FABRIC_CLIENT_ID")
        self.secret = os.environ.get("FABRIC_CLIENT_SECRET")
        self._cache: dict[str, tuple[str, float]] = {}

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
        h = (ctx.headers if ctx is not None else {}) or {}
        auth = h.get("authorization") or h.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return self._client_credentials(FABRIC_SCOPE)

    def sql(self, ctx: Context | None) -> str:
        h = (ctx.headers if ctx is not None else {}) or {}
        t = h.get("x-fabric-sql-token") or h.get("X-Fabric-SQL-Token")
        return t.strip() if t else self._client_credentials(SQL_SCOPE)


auth = Auth()


def _headers(ctx) -> dict:
    return {"Authorization": f"Bearer {auth.fabric(ctx)}", "Content-Type": "application/json"}


# ------------------------------------------------------------------ fabric helpers -----------

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
                          attrs_before=attrs)

    def execute(sql: str):
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    return execute


def _plan(workspace: str, source: str, schema: str, keys, confirmed, ctx):
    headers = _headers(ctx)
    item = _resolve_source(workspace, source, headers)
    s = Schema.from_sql(_execute_factory(item, auth.sql(ctx)), schema)
    return make_plan(s, keys, confirmed), item, headers


# ------------------------------------------------------------------ tools --------------------

RO = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)


@mcp.tool(title="List data sources in a workspace", annotations=RO)
def list_sources(workspace: str, ctx: Context = None) -> str:
    """Lakehouses, warehouses, SQL databases and mirrored databases in a Fabric workspace (id), plus existing
    API for GraphQL items. Use the display name or id as `source` in the other tools."""
    import requests
    headers = _headers(ctx)
    out = {"sources": [], "graphql_apis": []}
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
def list_tables(workspace: str, source: str, schema: str = "dbo", ctx: Context = None) -> str:
    """Tables and columns (with types) in one schema of a source. Read-only."""
    p, _, _ = _plan(workspace, source, schema, None, None, ctx)
    return json.dumps({t.name: [[c.name, c.data_type] for c in t.columns] for t in p.schema}, indent=2)


@mcp.tool(title="Plan keys and relationships (nothing deployed)", annotations=RO)
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
def create_backend(workspace: str, source: str, name: str, schema: str = "dbo", writable: bool = False,
                   keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                   tables: list[str] | None = None, ctx: Context = None) -> str:
    """Create a Fabric API for GraphQL item over the source's tables with the inferred relationships — or update
    the item of that name in place. Creates one item; never deletes anything. Returns the endpoint URL and the
    portal steps that remain (introspection, service principal permission)."""
    p, item, headers = _plan(workspace, source, schema, keys, confirmed, ctx)
    source_id, source_type = source_for(workspace, item, headers)
    env = definition(p, name, workspace, source_id, source_type, writable=writable, tables=tables)
    result = deploy(env, workspace, token_provider=lambda: auth.fabric(ctx))
    out = {"summary": p.summary(), "source": {"id": source_id, "type": source_type}, "result": result,
           "skipped_relationships": env.get("skipped_relationships", [])}
    if result.get("status") == "Succeeded":
        out["card"] = connection_card(workspace, result["id"], name)
    return json.dumps(out, indent=2)


@mcp.tool(title="Generate Rayfin connector entities", annotations=RO)
def rayfin_connector(workspace: str, source: str, connector: str = "data", schema: str = "dbo",
                     keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None,
                     tables: list[str] | None = None, relationships: bool = True, ctx: Context = None) -> str:
    """Rayfin (Fabric Apps) connector entity classes + schema.ts for the source's tables, with inferred keys and
    @one/@many relationships (sourceFields/targetFields spelled out). Returns {path: content}; nothing is deployed."""
    p, item, _ = _plan(workspace, source, schema, keys, confirmed, ctx)
    st = {"Lakehouse": "SqlAnalyticsEndpoint", "MirroredDatabase": "SqlAnalyticsEndpoint", "Warehouse": "Warehouse",
          "SQLDatabase": "SqlDbNative"}.get(item["type"], "SqlAnalyticsEndpoint")
    return json.dumps(rayfin_files(p, connector, st, tables=tables, relationships=relationships), indent=2)


@mcp.tool(title="Run a GraphQL query", annotations=RO)
def query_graphql(workspace: str, api: str, query: str, variables: dict | None = None, ctx: Context = None) -> str:
    """Run a read-only GraphQL query against an API for GraphQL item (name or id) in the workspace. Query fields
    are named <type>s, e.g. `{ customers(first: 5) { items { customer_id name } } }`; relationships nest.
    Mutations are refused."""
    import requests
    if query.lstrip().lower().startswith("mutation"):
        return json.dumps({"error": "mutations are not allowed through this tool"})
    headers = _headers(ctx)
    api_id = api if len(api) == 36 and api.count("-") == 4 else find_item_by_name(workspace, api, headers, "GraphQLApi")
    if not api_id:
        return json.dumps({"error": f"no API for GraphQL named {api!r} in workspace {workspace}"})
    r = requests.post(f"{FABRIC}/v1/workspaces/{workspace}/graphqlapis/{api_id}/graphql", headers=headers,
                      json={"query": query, "variables": variables or {}}, timeout=100)
    try:
        body = r.json()
    except ValueError:
        body = {"http": r.status_code, "text": r.text[:2000]}
    return json.dumps(body, indent=2, default=str)[:60000]


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
        mcp.run(transport="streamable-http", host=a.host, port=a.port, stateless_http=True)


if __name__ == "__main__":
    main()
