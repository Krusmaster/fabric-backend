"""The Fabric REST plumbing under the tools: item lookup with paging, the source id/type the GraphQL definition
needs, the service-principal token cache, and the SQL schema reader. Fabric is mocked throughout."""
import importlib
import json
import time

import pytest
import requests

from fabric_backend import server
from fabric_backend.schema import Schema

dep = importlib.import_module("fabric_backend.deploy")
HEADERS = {"Authorization": "Bearer test-only"}


class Resp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


def pages(monkeypatch, routes):
    """requests.get answering from a {url_suffix: Resp} table; unknown URLs fail the test."""
    seen = []

    def get(url, **kwargs):
        seen.append(url)
        for suffix, resp in routes.items():
            if url.endswith(suffix):
                return resp
        pytest.fail(f"unexpected GET {url}")
    monkeypatch.setattr(requests, "get", get)
    return seen


def test_item_lookups_follow_the_continuation_uri_and_skip_the_sql_endpoint_twin(monkeypatch):
    first = {"value": [{"displayName": "shop_lh", "type": "SQLEndpoint", "id": "ep-1"}], "continuationUri": "https://x/page2"}
    second = {"value": [{"displayName": "shop_lh", "type": "Lakehouse", "id": "lh-1"},
                        {"displayName": "shop_api", "type": "GraphQLApi", "id": "api-1"}]}
    seen = pages(monkeypatch, {"/items": Resp(200, first), "/page2": Resp(200, second), "items?type=GraphQLApi": Resp(200, first)})
    item = dep.find_item_by_name("ws-1", "shop_lh", HEADERS)
    assert item["type"] == "Lakehouse" and item["id"] == "lh-1"                      # not the endpoint listed first
    assert seen[:2] == ["https://api.fabric.microsoft.com/v1/workspaces/ws-1/items", "https://x/page2"]
    assert dep.find_item_by_name("ws-1", "nope", HEADERS) is None
    monkeypatch.setattr(requests, "get", lambda url, **k: Resp(200, second) if url.endswith("page2") else Resp(200, dict(first, value=[])))
    assert dep.find_item("ws-1", "shop_api", HEADERS) == "api-1" and dep.find_item("ws-1", "other", HEADERS) is None


def test_list_sources_pages_through_the_workspace(monkeypatch):
    first = {"value": [{"displayName": "shop_lh", "type": "Lakehouse", "id": "lh-1"},
                       {"displayName": "shop_lh", "type": "SQLEndpoint", "id": "ep-1"},
                       {"displayName": "notes", "type": "Notebook", "id": "nb-1"}], "continuationUri": "https://x/next"}
    second = {"value": [{"displayName": "dw", "type": "Warehouse", "id": "wh-1"},
                        {"displayName": "shop_api", "type": "GraphQLApi", "id": "api-1"}]}
    pages(monkeypatch, {"/items": Resp(200, first), "/next": Resp(200, second)})
    monkeypatch.setattr(server, "_headers", lambda ctx: HEADERS)
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: workspace)
    out = json.loads(server.list_sources("ws-1"))
    assert [s["name"] for s in out["sources"]] == ["shop_lh", "dw"]                 # endpoint and notebook are not sources
    assert out["graphql_apis"] == [{"name": "shop_api", "id": "api-1"}]


@pytest.mark.parametrize("item,expect", [
    ({"type": "SQLEndpoint", "id": "ep-1"}, ("ep-1", "SqlAnalyticsEndpoint")),
    ({"type": "Lakehouse", "id": "lh-1"}, ("ep-lh", "SqlAnalyticsEndpoint")),
    ({"type": "Warehouse", "id": "wh-1"}, ("wh-1", "Warehouse")),
    ({"type": "SQLDatabase", "id": "db-1"}, ("db-1", "SqlDbNative")),
    ({"type": "MirroredDatabase", "id": "md-1"}, ("ep-md", "SqlAnalyticsEndpoint")),
    ({"type": "MirroredAzureDatabricksCatalog", "id": "dbx-1"}, ("ep-dbx", "SqlAnalyticsEndpoint")),
])
def test_source_for_picks_the_id_and_type_the_definition_needs(monkeypatch, item, expect):
    pages(monkeypatch, {"/lakehouses/lh-1": Resp(200, {"properties": {"sqlEndpointProperties": {"id": "ep-lh", "provisioningStatus": "Success"}}}),
                        "/mirroredDatabases/md-1": Resp(200, {"properties": {"sqlEndpointProperties": {"id": "ep-md"}}}),
                        "/mirroredAzureDatabricksCatalogs/dbx-1": Resp(200, {"properties": {"catalogName": "main", "sqlEndpointProperties": {"id": "ep-dbx"}}})})
    assert dep.source_for("ws-1", item, HEADERS) == expect


def explain_kind(exc):
    from fabric_backend.errors import explain
    return explain(exc)["kind"]


def test_source_for_explains_a_provisioning_lakehouse_and_refuses_other_items(monkeypatch):
    pages(monkeypatch, {"/lakehouses/lh-2": Resp(200, {"properties": {"sqlEndpointProperties": {"provisioningStatus": "InProgress"}}}),
                        "/mirroredDatabases/md-2": Resp(200, {"properties": {}})})
    with pytest.raises(RuntimeError, match="no SQL analytics endpoint yet"):
        dep.source_for("ws-1", {"type": "Lakehouse", "id": "lh-2"}, HEADERS)
    with pytest.raises(RuntimeError, match="mirrored database has no SQL analytics endpoint yet"):
        dep.source_for("ws-1", {"type": "MirroredDatabase", "id": "md-2"}, HEADERS)
    assert explain_kind(RuntimeError("mirrored Databricks catalog has no SQL analytics endpoint yet; pass its SQL analytics endpoint item")) == "source_not_ready"
    with pytest.raises(ValueError, match="cannot expose item type Notebook"):
        dep.source_for("ws-1", {"type": "Notebook", "id": "nb-1"}, HEADERS)
    # through the tool wrapper these become the kinds a user can act on
    from fabric_backend.errors import explain
    assert explain(RuntimeError("lakehouse has no SQL analytics endpoint yet (provisioningStatus=InProgress)"))["kind"] == "source_not_ready"
    assert explain(ValueError("cannot expose item type Notebook through GraphQL"))["kind"] == "unsupported"


def test_service_principal_tokens_are_cached_per_scope_until_shortly_before_expiry(monkeypatch):
    a = server.Auth()
    a.entra = None
    a.tenant, a.client, a.secret = "tenant-1", "client-1", "secret-1"
    posts = []

    def post(url, **kwargs):
        posts.append((url, kwargs["data"]))
        return type("R", (), {"raise_for_status": lambda self: None,
                              "json": lambda self: {"access_token": f"tok-{len(posts)}", "expires_in": 3600}})()
    monkeypatch.setattr(requests, "post", post)
    assert a.fabric(None) == "tok-1" and a.fabric(None) == "tok-1"                    # second call: cache hit
    assert a.sql(None) == "tok-2"                                                     # another scope: another token
    assert posts[0][0] == "https://login.microsoftonline.com/tenant-1/oauth2/v2.0/token"
    assert posts[0][1]["scope"] == server.FABRIC_SCOPE and posts[1][1]["scope"] == server.SQL_SCOPE
    a._cache[server.FABRIC_SCOPE] = ("stale", time.time() + 30)                       # inside the 60 s margin: refreshed
    assert a.fabric(None) == "tok-3"
    # a request carrying its own bearer wins over the service principal
    ctx = type("Ctx", (), {"headers": {"Authorization": "Bearer from-the-request"}})()
    assert a.fabric(ctx) == "from-the-request"
    ctx = type("Ctx", (), {"headers": {"x-fabric-sql-token": " sql-from-the-request "}})()
    assert a.sql(ctx) == "sql-from-the-request"
    a.secret = None
    with pytest.raises(RuntimeError, match="no bearer token"):
        a._client_credentials("x")


def test_schema_reader_tolerates_an_endpoint_without_constraints_and_mixed_row_shapes():
    class Row(dict):                                                                   # dict-like with keys(), upper-case names
        pass
    calls = []

    def execute(sql):
        calls.append(sql)
        if "CONSTRAINT" in sql.upper() or "KEY" in sql.upper():
            raise RuntimeError("Invalid object name 'INFORMATION_SCHEMA.TABLE_CONSTRAINTS'")
        return [Row(TABLE_SCHEMA="dbo", TABLE_NAME="orders", COLUMN_NAME="order_id", DATA_TYPE="INT", ORDINAL_POSITION=1),
                ("dbo", "orders", "customer_id", "int", 2),
                ("sales", "other", "x", "int", 1)]                                   # another schema: ignored
    s = Schema.from_sql(execute, "dbo")
    assert [c.name for c in s.tables["orders"].columns] == ["order_id", "customer_id"] and "other" not in s.tables
    assert s.tables["orders"].columns[0].data_type == "int" and len(calls) == 2


def test_resolve_source_by_name_or_id_and_reads_the_sql_endpoint_host(monkeypatch):
    lakehouse = {"id": "lh-1", "type": "Lakehouse", "displayName": "shop_lh",
                 "properties": {"sqlEndpointProperties": {"connectionString": "x.datawarehouse.fabric.microsoft.com", "id": "ep-1"}}}
    warehouse = {"id": "wh-1", "type": "Warehouse", "displayName": "dw", "properties": {"connectionString": "y.datawarehouse.fabric.microsoft.com"}}
    routes = {"/items": Resp(200, {"value": [{"displayName": "shop_lh", "type": "Lakehouse", "id": "lh-1"}]}),
              "/lakehouses/lh-1": Resp(200, lakehouse), "/warehouses/wh-1": Resp(200, warehouse),
              "/lakehouses/wh-1": Resp(404, {}), "/lakehouses/ghost": Resp(404, {}), "/warehouses/ghost": Resp(404, {}), "/sqlDatabases/ghost": Resp(404, {}),
              "/mirroredDatabases/ghost": Resp(404, {}), "/mirroredAzureDatabricksCatalogs/ghost": Resp(404, {})}
    pages(monkeypatch, routes)
    by_name = server._resolve_source("ws-1", "shop_lh", HEADERS)
    assert by_name["type"] == "Lakehouse" and by_name["sql_host"] == "x.datawarehouse.fabric.microsoft.com" and by_name["sql_db"] == "shop_lh"
    by_id = server._resolve_source("ws-1", "wh-1", HEADERS)                            # not in the name list: tried as an id
    assert by_id["type"] == "Warehouse" and by_id["sql_host"] == "y.datawarehouse.fabric.microsoft.com" and by_id["sql_db"] == "dw"
    with pytest.raises(LookupError, match="'ghost'"):
        server._resolve_source("ws-1", "ghost", HEADERS)
    # a Fabric SQL database connects by its properties.databaseName (display name plus a suffix), per the REST spec
    sqldb = {"id": "db-1", "type": "SQLDatabase", "displayName": "sales", "properties": {"connectionString": "z.database.fabric.microsoft.com", "databaseName": "sales-2f3e4d5c-aaaa", "serverFqdn": "z.database.fabric.microsoft.com"}}
    pages(monkeypatch, {"/items": Resp(200, {"value": [{"displayName": "sales", "type": "SQLDatabase", "id": "db-1"}]}), "/sqlDatabases/db-1": Resp(200, sqldb)})
    got = server._resolve_source("ws-1", "sales", HEADERS)
    assert got["sql_host"] == "z.database.fabric.microsoft.com" and got["sql_db"] == "sales-2f3e4d5c-aaaa"


def test_on_behalf_of_failure_is_a_token_error_without_the_assertion(monkeypatch):
    from fabric_backend.entra import EntraConfig, OnBehalfOf, TokenError
    cfg = EntraConfig("https://x/mcp", "client-1", "secret-1")
    obo = OnBehalfOf(cfg)
    body = {"error": "invalid_grant", "error_description": "AADSTS65001: The user or administrator has not consented.\nTrace ID: abc"}
    monkeypatch.setattr(requests, "post", lambda url, **k: type("R", (), {"status_code": 400, "headers": {"content-type": "application/json; charset=utf-8"},
                                                                         "json": lambda self: body})())
    with pytest.raises(TokenError) as info:
        obo.token("user-assertion-token", "tenant-1", "https://api.fabric.microsoft.com/.default")
    msg = str(info.value)
    assert "AADSTS65001" in msg and "Trace ID" not in msg and "user-assertion-token" not in msg
    from fabric_backend.errors import explain
    assert explain(info.value)["kind"] == "consent"


def test_schema_name_stays_inside_its_sql_literal():
    """The schema name comes from the tool call; a quote in it must not end the literal."""
    seen = []

    def execute(sql):
        seen.append(sql)
        return []
    Schema.from_sql(execute, "o'brien'; DROP TABLE x; --")
    assert all("TABLE_SCHEMA) = UPPER('o''brien''; DROP TABLE x; --')" in q for q in seen) and len(seen) == 2
    seen.clear()
    Schema.from_sql(execute, "dbo")
    assert "UPPER(TABLE_SCHEMA) = UPPER('dbo')" in seen[0]


WS1, WS2, WS3 = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222", "33333333-3333-3333-3333-333333333333"


def test_list_workspaces_pages_and_tools_accept_a_workspace_name(monkeypatch):
    first = {"value": [{"displayName": "Sales", "type": "Workspace", "id": WS1, "capacityId": "cap-1"}], "continuationUri": "https://x/ws2"}
    second = {"value": [{"displayName": "Finance", "type": "Workspace", "id": WS2, "capacityId": "cap-1"},
                        {"displayName": "Finance", "type": "Workspace", "id": WS3}]}
    pages(monkeypatch, {"/v1/workspaces": Resp(200, first), "/ws2": Resp(200, second),
                        f"/workspaces/{WS1}/items": Resp(200, {"value": [{"displayName": "sales_lh", "type": "Lakehouse", "id": "lh-1"}]})})
    monkeypatch.setattr(server, "_headers", lambda ctx: HEADERS)
    out = json.loads(server.list_workspaces())
    assert [w["name"] for w in out["workspaces"]] == ["Sales", "Finance", "Finance"] and out["workspaces"][0]["capacity_id"] == "cap-1"
    assert server._workspace_id(WS1, HEADERS) == WS1                                   # an id needs no lookup
    assert server._workspace_id(" sales ", HEADERS) == WS1                              # a name does, case-insensitively
    out = json.loads(server.list_sources("Sales"))
    assert out["workspace"] == WS1 and out["sources"][0]["name"] == "sales_lh"
    out = json.loads(server.list_sources("Marketing"))
    assert out["kind"] == "not_found" and "list_workspaces" in out["error"]
    out = json.loads(server.list_sources("finance"))
    assert out["kind"] == "bad_input" and WS2 in out["error"] and WS3 in out["error"]
    out = json.loads(server.list_sources(""))
    assert out["kind"] == "bad_input"


def test_snowflake_information_schema_plans_without_key_views():
    """Snowflake upper-cases unquoted names, answers INFORMATION_SCHEMA with upper-case column names and has no
    KEY_COLUMN_USAGE view: keys come from names (K2) and links from names (R1), as on a lakehouse."""
    from fabric_backend.infer import plan

    def execute(sql):
        if "KEY_COLUMN_USAGE" in sql:
            raise RuntimeError("002003 (42S02): SQL compilation error: Object 'INFORMATION_SCHEMA.KEY_COLUMN_USAGE' does not exist")
        assert "UPPER(TABLE_SCHEMA) = UPPER('public')" in sql
        rows = [("PUBLIC", "CUSTOMERS", "CUSTOMER_ID", "NUMBER", 1), ("PUBLIC", "CUSTOMERS", "NAME", "TEXT", 2),
                ("PUBLIC", "ORDERS", "ORDER_ID", "NUMBER", 1), ("PUBLIC", "ORDERS", "CUSTOMER_ID", "NUMBER", 2),
                ("PUBLIC", "ORDERS", "ORDERED_AT", "TIMESTAMP_NTZ", 3)]
        return [{"TABLE_SCHEMA": a, "TABLE_NAME": b, "COLUMN_NAME": c, "DATA_TYPE": d, "ORDINAL_POSITION": e} for a, b, c, d, e in rows]
    s = Schema.from_sql(execute, "public")
    p = plan(s, None, None)
    assert p.keys["CUSTOMERS"] == (["CUSTOMER_ID"], "K2") and p.keys["ORDERS"] == (["ORDER_ID"], "K2")
    assert [(r.source, r.target, r.rule) for r in p.relationships] == [("ORDERS", "CUSTOMERS", "R1")]


def test_databricks_information_schema_brings_declared_keys():
    """Unity Catalog exposes information_schema with lower-case names and informational PK/FK constraints: K0 and R0."""
    from fabric_backend.infer import plan
    cols = [("sales", "customers", "customer_id", "INT", 1), ("sales", "customers", "name", "STRING", 2),
            ("sales", "orders", "order_id", "BIGINT", 1), ("sales", "orders", "customer_id", "INT", 2), ("sales", "orders", "total", "DECIMAL(10,2)", 3)]
    keys = [("customers", "PRIMARY KEY", "customer_id", 1, "customers_pk", None, None),
            ("orders", "PRIMARY KEY", "order_id", 1, "orders_pk", None, None),
            ("orders", "FOREIGN KEY", "customer_id", 1, "orders_customer_fk", "customers", "customer_id")]

    def execute(sql):
        return keys if "KEY_COLUMN_USAGE" in sql else cols
    p = plan(Schema.from_sql(execute, "sales"), None, None)
    assert p.keys["orders"] == (["order_id"], "K0") and p.keys["customers"] == (["customer_id"], "K0")
    assert [(r.source, r.source_cols, r.target, r.rule) for r in p.relationships] == [("orders", ["customer_id"], "customers", "R0")]
    assert p.schema.tables["orders"].columns[2].data_type == "decimal(10,2)"
