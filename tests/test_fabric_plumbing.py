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
    out = json.loads(server.list_sources("ws-1"))
    assert [s["name"] for s in out["sources"]] == ["shop_lh", "dw"]                 # endpoint and notebook are not sources
    assert out["graphql_apis"] == [{"name": "shop_api", "id": "api-1"}]


@pytest.mark.parametrize("item,expect", [
    ({"type": "SQLEndpoint", "id": "ep-1"}, ("ep-1", "SqlAnalyticsEndpoint")),
    ({"type": "Lakehouse", "id": "lh-1"}, ("ep-lh", "SqlAnalyticsEndpoint")),
    ({"type": "Warehouse", "id": "wh-1"}, ("wh-1", "Warehouse")),
    ({"type": "SQLDatabase", "id": "db-1"}, ("db-1", "SqlDbNative")),
    ({"type": "MirroredDatabase", "id": "md-1"}, ("ep-md", "SqlAnalyticsEndpoint")),
])
def test_source_for_picks_the_id_and_type_the_definition_needs(monkeypatch, item, expect):
    pages(monkeypatch, {"/lakehouses/lh-1": Resp(200, {"properties": {"sqlEndpointProperties": {"id": "ep-lh", "provisioningStatus": "Success"}}}),
                        "/mirroredDatabases/md-1": Resp(200, {"properties": {"sqlEndpointProperties": {"id": "ep-md"}}})})
    assert dep.source_for("ws-1", item, HEADERS) == expect


def test_source_for_explains_a_provisioning_lakehouse_and_refuses_other_items(monkeypatch):
    pages(monkeypatch, {"/lakehouses/lh-2": Resp(200, {"properties": {"sqlEndpointProperties": {"provisioningStatus": "InProgress"}}}),
                        "/mirroredDatabases/md-2": Resp(200, {"properties": {}})})
    with pytest.raises(RuntimeError, match="no SQL analytics endpoint yet"):
        dep.source_for("ws-1", {"type": "Lakehouse", "id": "lh-2"}, HEADERS)
    with pytest.raises(RuntimeError, match="no SQL endpoint id"):
        dep.source_for("ws-1", {"type": "MirroredDatabase", "id": "md-2"}, HEADERS)
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
