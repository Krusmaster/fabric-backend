"""Turn a Plan into a Fabric *API for GraphQL* item definition.

The GraphQLApi item is GA and its definition is documented:
https://learn.microsoft.com/rest/api/fabric/articles/item-management/definitions/graphql-api-definition

- A lakehouse is exposed through its SQL analytics endpoint: sourceType "SqlAnalyticsEndpoint" and
  sourceItemId = the endpoint's item id, not the lakehouse id (`sql_endpoint_id_for_lakehouse`).
- A warehouse / Fabric SQL database is its own item id, sourceType "Warehouse" / "SqlDbNative".
- Lakehouse and mirrored sources are read-only through GraphQL; `writable` only has an effect on
  Warehouse / SqlDbNative / AzureSql.
- Each relationship becomes ManyToOne on the source and OneToMany on the target.

Verified against a live item (sandbox, 2026-10-21), which corrected four things the docs do not say:
- no "format" key in the definition (InvalidDefinitionFormat)
- relationships[].targetObject is the target's *sourceObject* ("dbo.orders"), not its graphqlType
- fieldMappings must list every column the SQL endpoint has, technical columns included; a leading
  "__" is stripped from the GraphQL name because GraphQL reserves that prefix
- a relationship field named "items" collides with the connection's own `items` list (500) — see infer
- actions left out of the definition are stored as Enabled, so all five are always spelled out;
  on a SQL analytics endpoint the schema has no Mutation type regardless
"""
from __future__ import annotations

import base64
import json
import re
import uuid

from .infer import Plan

SCHEMA_URL = "https://developer.microsoft.com/json-schemas/fabric/item/graphqlApi/definition/1.0.0/schema.json"
SOURCE_TYPES = ("SqlAnalyticsEndpoint", "Warehouse", "SqlDbNative", "AzureSql")
_GQL_NAME = re.compile(r"[^A-Za-z0-9_]")
_ITEM_NAME = re.compile(r"^[A-Za-z0-9_]+$")


def graphql_name(name: str) -> str:
    n = _GQL_NAME.sub("_", name)
    return n if not n[:1].isdigit() else f"_{n}"


def valid_item_name(name: str) -> bool:
    """Fabric item names for GraphQL/Ontology: letters, digits, underscores. No spaces."""
    return bool(_ITEM_NAME.match(name))


def definition(plan: Plan, display_name: str, workspace_id: str, source_item_id: str,
               source_type: str = "SqlAnalyticsEndpoint", writable: bool = False,
               tables: list[str] | None = None) -> dict:
    """The envelope for POST /v1/workspaces/{ws}/graphQLApis (and updateDefinition).

    tables: restrict to these (default: every table in the plan). Keyless tables are exposed with
    Query only — no Query_by_pk, and relationships that touch them are dropped and listed under
    "skipped_relationships".
    """
    if not valid_item_name(display_name):
        raise ValueError(f"item name {display_name!r}: letters, digits and underscores only")
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"source_type must be one of {SOURCE_TYPES}")
    wanted = {t.lower() for t in tables} if tables else None

    objects: dict[str, dict] = {}
    for t in plan.schema:
        if wanted and t.name.lower() not in wanted:
            continue
        keyed = t.name in plan.keys
        # Fabric stores any action you leave out as Enabled (issue #1, note C) — so every action is spelled out
        can_write = writable and keyed and source_type in ("Warehouse", "SqlDbNative", "AzureSql")
        actions = {"Query": "Enabled", "Query_by_pk": "Enabled" if keyed else "Disabled",
                   "Create": "Enabled" if can_write else "Disabled",
                   "Update": "Enabled" if can_write else "Disabled",
                   "Delete": "Disabled"}
        objects[t.name] = {
            "graphqlType": graphql_name(t.name),
            "sourceObject": f"{t.schema}.{t.name}",
            "sourceObjectType": "Table",
            "actions": actions,
            "fieldMappings": {c.name: graphql_name(c.name.lstrip("_")) for c in t.columns},
            "relationships": [],
        }

    skipped: list[str] = []
    for r in plan.relationships:
        if r.source not in objects or r.target not in objects or r.target not in plan.keys:
            skipped.append(f"{r.source}.{'+'.join(r.source_cols)} -> {r.target} ({r.rule})")
            continue
        objects[r.source]["relationships"].append({
            "field": r.field_name, "cardinality": "ManyToOne",
            "targetObject": objects[r.target]["sourceObject"],
            "sourceFields": r.source_cols, "targetFields": r.target_cols,
        })
        objects[r.target]["relationships"].append({
            "field": r.reverse_name, "cardinality": "OneToMany",
            "targetObject": objects[r.source]["sourceObject"],
            "sourceFields": r.target_cols, "targetFields": r.source_cols,
        })

    body = {"$schema": SCHEMA_URL, "datasources": [{
        "sourceItemId": source_item_id, "sourceWorkspaceId": workspace_id,
        "sourceType": source_type, "objects": list(objects.values()),
    }]}
    platform = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "GraphQLApi", "displayName": display_name},
        "config": {"version": "2.0", "logicalId": str(uuid.uuid5(uuid.NAMESPACE_URL, "graphql|" + display_name))},
    }

    def b64(o: dict) -> str:
        return base64.b64encode(json.dumps(o, separators=(",", ":")).encode()).decode()

    env = {
        "displayName": display_name,
        "type": "GraphQLApi",
        "definition": {"parts": [
            {"path": "graphql-definition.json", "payload": b64(body), "payloadType": "InlineBase64"},
            {"path": ".platform", "payload": b64(platform), "payloadType": "InlineBase64"},
        ]},
    }
    if skipped:
        env["skipped_relationships"] = skipped
    return env


def decode(env: dict) -> dict:
    """The graphql-definition.json back out of an envelope (for tests and for reading what you deployed)."""
    for p in env["definition"]["parts"]:
        if p["path"] == "graphql-definition.json":
            return json.loads(base64.b64decode(p["payload"]))
    raise KeyError("graphql-definition.json")
