"""The Fabric adapter: the first platform behind the engine, and the only one the hosted server (server.py) uses.

1. Read: Fabric REST finds the workspace and the source item (lakehouse, warehouse, SQL database, mirrored and
   Snowflake items) and its SQL analytics endpoint; the schema comes from the endpoint's INFORMATION_SCHEMA
   (schema.py), declared keys included where the item has them (warehouse, SQL database).
2. Run SQL: ODBC Driver 18 against the SQL analytics endpoint with an Entra access token for database.windows.net,
   a login timeout and a per-statement timeout; T-SQL.
3. Build: the objects in BUILDERS, each a pure generator in its own module plus the REST call in deploy.py (or the
   SQL connection, for views) that creates it.

Moved here from server.py in round n13 without a change to any answer (tests/test_golden.py). server.py keeps thin
wrappers under the old names, so that it passes its own, patchable readers in (the pattern lineage.py uses).
"""
from __future__ import annotations

import re
import struct

from ..deploy import ENDPOINT_ITEM_ROUTES, FABRIC, find_item_by_name
from ..dialects import TSQL
from .base import Builder, Platform, connection

GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
LOGIN_TIMEOUT = 30      # seconds to log in to the SQL analytics endpoint
QUERY_TIMEOUT = 120     # seconds per metadata query
SOURCE_ROUTES = {"Lakehouse": "lakehouses", "Warehouse": "warehouses", "SQLDatabase": "sqlDatabases", **ENDPOINT_ITEM_ROUTES}


# ------------------------------------------------------------------ 1. read --------------------------------------

def workspaces(headers: dict) -> list[dict]:
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


def workspace_id(workspace: str, headers: dict, list_workspaces=workspaces) -> str:
    """Tools take a workspace id or its display name; a name is looked up (case does not matter)."""
    from ..infer import PlanInputError
    w = (workspace or "").strip()
    if GUID.match(w):
        return w
    if not w:
        raise PlanInputError("workspace: give the workspace id or its name; list_workspaces shows both")
    hits = [x for x in list_workspaces(headers) if (x["name"] or "").lower() == w.lower()]
    if len(hits) == 1:
        return hits[0]["id"]
    if not hits:
        raise LookupError(f"no workspace named {w!r} is visible to the signed-in account; list_workspaces shows what is")
    raise PlanInputError(f"{len(hits)} workspaces are named {w!r}; use the id instead: " + ", ".join(h["id"] for h in hits))


def resolve_source(workspace: str, source: str, headers: dict, find=find_item_by_name) -> dict:
    """Lakehouse / warehouse / SQL database by name or id → item dict with sql endpoint host."""
    import requests
    item = find(workspace, source, headers)
    if item is None:
        for t, route in (("Lakehouse", "lakehouses"), ("Warehouse", "warehouses"), ("SQLDatabase", "sqlDatabases"), *ENDPOINT_ITEM_ROUTES.items()):
            r = requests.get(f"{FABRIC}/v1/workspaces/{workspace}/{route}/{source}", headers=headers, timeout=30)
            if r.status_code == 200:
                item = {"type": t, **r.json()}
                break
    if item is None:
        raise LookupError(f"no lakehouse/warehouse/SQL database named or with id {source!r} in workspace {workspace}")
    route = SOURCE_ROUTES[item["type"]]
    r = requests.get(f"{FABRIC}/v1/workspaces/{workspace}/{route}/{item['id']}", headers=headers, timeout=30)
    r.raise_for_status()
    body = r.json()
    props = body.get("properties", {})
    if body.get("sensitivityLabel") or item.get("sensitivityLabel"):   # Item.sensitivityLabel {id}, read-only (common/definitions.json)
        item["sensitivityLabel"] = body.get("sensitivityLabel") or item.get("sensitivityLabel")
    ep = props.get("sqlEndpointProperties") or {}
    item["sql_host"] = ep.get("connectionString") or props.get("connectionString") or props.get("connectionInfo")
    if ep.get("id"):                                   # what a GraphQL API over this source names as its sourceItemId (lineage)
        item["sql_endpoint_id"] = ep["id"]
    # a Fabric SQL database's actual database name carries a suffix (properties.databaseName); the others use the display name
    item["sql_db"] = props.get("databaseName") or item.get("displayName")
    # a lakehouse created with schemas carries properties.defaultSchema (lakehouse/definitions.json: "returned only for
    # schema enabled lakehouse"); the TMDL partitions need schemaName in that case, and must not have it otherwise
    item["schemas_enabled"] = item["type"] != "Lakehouse" or "defaultSchema" in props
    return item


# ------------------------------------------------------------------ 2. run SQL -----------------------------------

def connect(item: dict, sql_token: str, login_timeout: int = LOGIN_TIMEOUT, query_timeout: int = QUERY_TIMEOUT):
    """DB-API over the SQL analytics endpoint with an Entra access token (ODBC Driver 18)."""
    import pyodbc
    if not item.get("sql_host"):
        raise RuntimeError("source has no SQL endpoint connection string yet")
    tok = sql_token.encode("utf-16-le")
    attrs = {1256: struct.pack("<i", len(tok)) + tok}      # SQL_COPT_SS_ACCESS_TOKEN
    conn = pyodbc.connect(f"Driver={{ODBC Driver 18 for SQL Server}};Server={item['sql_host']};Database={item['sql_db']};Encrypt=yes",
                          attrs_before=attrs, timeout=login_timeout)     # a cold or paused endpoint fails as `timeout`, not a hang
    conn.timeout = query_timeout                                           # per statement; the driver raises HYT00, explained as `timeout`

    def execute(sql: str):
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def statement(sql: str) -> None:                                       # DDL (CREATE OR ALTER VIEW): no rows, committed
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
    return connection(execute, dialect=TSQL, statement=statement, close=conn.close)


# ------------------------------------------------------------------ 3. build -------------------------------------

BUILDERS = (
    Builder("API for GraphQL item", None, "create_backend", "graphql.py, deploy.deploy", "GraphQLApi.ReadWrite.All"),
    Builder("Rayfin connector entities", "rayfin_connector", None, "rayfin.py"),
    Builder("Power BI semantic model (TMDL, Direct Lake)", "semantic_model_draft", "create_semantic_model",
            "semantic_model.py, deploy.create_semantic_model", "SemanticModel.ReadWrite.All or Item.ReadWrite.All"),
    Builder("Fabric IQ ontology", "ontology_draft", "create_ontology", "ontology.py, deploy.create_ontology", "Item.ReadWrite.All"),
    Builder("T-SQL views in a schema of their own", "create_views", "create_views", "views.py", "the SQL right to create objects"),
    Builder("Fabric data agent", "create_data_agent", "create_data_agent", "data_agent.py", "Item.ReadWrite.All"),
    Builder("silver-tables notebook (PySpark)", "silver_notebook_draft", "create_silver_notebook", "silver.py, notebook.py",
            "Notebook.ReadWrite.All or Item.ReadWrite.All"),
    Builder("gold views (materialized lake views)", "gold_views_draft", "create_gold_views", "gold.py, notebook.py",
            "Notebook.ReadWrite.All or Item.ReadWrite.All"),
    Builder("nightly drift monitor (notebook, pipeline, schedule)", "drift_monitor_draft", "create_drift_monitor", "monitor.py",
            "DataPipeline.ReadWrite.All and DataPipeline.Execute.All"),
    Builder("item definitions in Fabric's Git format", "export_item_definitions", None, "git_export.py"),
)


class FabricPlatform(Platform):
    name = "fabric"
    title = "Microsoft Fabric"
    dialect = TSQL
    builders = BUILDERS

    def connect(self, item: dict, sql_token: str, login_timeout: int = LOGIN_TIMEOUT, query_timeout: int = QUERY_TIMEOUT):
        return connect(item, sql_token, login_timeout, query_timeout)


PLATFORM = FabricPlatform()
