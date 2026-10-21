"""fabric-backend: tables in Fabric -> a GraphQL backend for Lovable, Cursor and Claude Code. One call."""
from __future__ import annotations

from .schema import Schema, Table, Column
from .infer import plan, Plan, Relationship
from .graphql import definition, decode, valid_item_name
from .deploy import deploy, connection_card, endpoint_url, source_for, find_item_by_name, _headers

__all__ = ["Schema", "Table", "Column", "plan", "Plan", "Relationship", "definition", "decode",
           "valid_item_name", "deploy", "connection_card", "endpoint_url", "create", "plan_from"]
__version__ = "0.1.0"


def plan_from(spark=None, execute=None, schema: str = "dbo", database: str | None = None,
              keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None) -> Plan:
    """Read the tables (Spark catalog, or any execute(sql) callable) and infer keys + relationships."""
    if spark is None and execute is None:
        raise ValueError("give spark= (lakehouse notebook) or execute= (SQL endpoint / warehouse / SQL database)")
    s = Schema.from_spark(spark, schema, database) if spark is not None else Schema.from_sql(execute, schema)
    return plan(s, keys, confirmed)


def create(workspace: str, source: str, name: str, *, spark=None, execute=None, schema: str = "dbo",
           database: str | None = None, keys: dict[str, list[str]] | None = None,
           confirmed: list[dict] | None = None, tables: list[str] | None = None, writable: bool = False,
           token_provider=None, dry_run: bool = False) -> dict:
    """The one call.

    workspace: workspace id.  source: display name or id of the lakehouse / warehouse / SQL database /
    mirrored database.  name: GraphQL item name (letters, digits, underscores).
    Reads the schema, infers keys and relationships, builds the GraphQLApi definition, creates the
    item (or updates it in place if the name exists), and returns {"plan", "definition", "result",
    "card"}. dry_run=True stops before deploying.
    """
    p = plan_from(spark, execute, schema, database, keys, confirmed)
    headers = _headers(token_provider)
    item = find_item_by_name(workspace, source, headers)
    if item is None:
        for t, route in (("Lakehouse", "lakehouses"), ("Warehouse", "warehouses"), ("SQLDatabase", "sqlDatabases"),
                         ("MirroredDatabase", "mirroredDatabases")):
            import requests
            r = requests.get(f"https://api.fabric.microsoft.com/v1/workspaces/{workspace}/{route}/{source}",
                             headers=headers, timeout=30)
            if r.status_code == 200:
                item = {"id": source, "type": t, **r.json()}
                break
    if item is None:
        raise LookupError(f"no lakehouse/warehouse/SQL database named or with id {source!r} in workspace {workspace}")
    source_id, source_type = source_for(workspace, item, headers)
    env = definition(p, name, workspace, source_id, source_type, writable=writable, tables=tables)
    out = {"plan": p, "definition": env, "source": {"id": source_id, "type": source_type}}
    if dry_run:
        return out
    out["result"] = deploy(env, workspace, token_provider)
    if out["result"].get("status") == "Succeeded":
        out["card"] = connection_card(workspace, out["result"]["id"], name)
    return out
