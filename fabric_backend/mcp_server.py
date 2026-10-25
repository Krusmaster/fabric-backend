"""MCP server: let an app-building agent provision its own Fabric backend.

Microsoft's own GraphQL MCP server queries an API that already exists. This one makes the API.
Three tools, same functions as the library:

  list_tables(workspace, source)            what is in the lakehouse / warehouse
  plan_backend(workspace, source, ...)      inferred keys + relationships, Mermaid, nothing deployed
  create_backend(workspace, source, name)   create/update the GraphQLApi item, return endpoint + checklist
  rayfin_connector(connector, ...)          Rayfin (Fabric Apps) connector entity files from the same plan

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
from .deploy import token_from_az

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
    return execute


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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
