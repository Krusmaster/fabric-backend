import json

import pytest

from fabric_backend import server


@pytest.fixture(autouse=True)
def _workspace_ids_pass_through(monkeypatch):
    """These tests mock Fabric per route; a workspace given as a plain string is used as the id."""
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: workspace)



@pytest.mark.parametrize("query", [
    "# comment\nmutation { deleteCustomers { id } }",
    "\ufeff, mutation Write { createCustomers { id } }",
    "fragment F on Customer { id } mutation Write { deleteCustomers { ...F } }",
    "query Read { customers { id } } mutation Write { deleteCustomers { id } }",
    "subscription { customers { id } }",
    "query One { customers { id } } query Two { customers { id } }",
    "type Customer { id: ID }",
    "{ broken",
])
def test_non_query_documents_never_contact_fabric(monkeypatch, query):
    def unexpected(*args, **kwargs):
        pytest.fail("A rejected query must not acquire tokens or contact Fabric")
    monkeypatch.setattr(server, "_headers", unexpected)
    result = json.loads(server.query_graphql("workspace", "api", query))
    assert "error" in result


def test_named_api_is_resolved_to_its_id(monkeypatch):
    import requests
    calls = []
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "find_item_by_name", lambda *args: {"id": "resolved-id", "displayName": "shop"})

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return type("Response", (), {"json": lambda self: {"data": {"customers": []}}})()

    monkeypatch.setattr(requests, "post", post)
    query = "# read\nquery Read { customers { ...Fields } } fragment Fields on Customer { id }"
    assert "data" in json.loads(server.query_graphql("workspace", "shop", query))
    assert calls[0][0].endswith("/graphqlapis/resolved-id/graphql")
    assert calls[0][1]["json"]["query"] == query


def test_large_results_are_cut_to_valid_json_that_says_so(monkeypatch):
    import requests
    rows = [{"order_id": i, "customer": {"name": f"Customer {i}", "orders": [{"id": j} for j in range(20)]}} for i in range(3000)]
    body = {"data": {"orders": {"items": rows}}, "extensions": {"note": "kept"}}
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(requests, "post", lambda url, **kw: type("Response", (), {"json": lambda self: body, "status_code": 200})())
    text = server.query_graphql("workspace", "11111111-2222-3333-4444-555555555555", "{ orders { items { order_id } } }")
    assert len(text) <= server.MAX_RESULT_CHARS
    answer = json.loads(text)                                                              # valid JSON, not chopped mid-document
    items = answer["data"]["orders"]["items"]
    assert 1 <= len(items) < 3000 and items[0]["order_id"] == 0 and answer["extensions"] == {"note": "kept"}
    assert "truncated" in answer and str(len(items)) in answer["truncated"] and "first:" in answer["truncated"]
    # a small result is returned untouched
    monkeypatch.setattr(requests, "post", lambda url, **kw: type("Response", (), {"json": lambda self: {"data": {"orders": {"items": rows[:2]}}}, "status_code": 200})())
    small = json.loads(server.query_graphql("workspace", "11111111-2222-3333-4444-555555555555", "{ orders { items { order_id } } }"))
    assert "truncated" not in small and len(small["data"]["orders"]["items"]) == 2
    # one enormous scalar: still valid JSON, with a preview
    assert "preview" in json.loads(server._bounded({"data": {"blob": "x" * 200000}}, 1000))


def test_sql_connection_has_timeouts_and_is_closed_after_the_plan(monkeypatch):
    """pyodbc is not installed in the test environment; a stand-in records what the server asks of it."""
    import sys
    import types
    seen = {}

    class Cursor:
        description = [("TABLE_NAME",), ("COLUMN_NAME",)]
        def execute(self, sql): seen["sql"] = sql
        def fetchall(self): return [("orders", "order_id")]

    class Conn:
        timeout = None
        closed = False
        def cursor(self): return Cursor()
        def close(self): self.closed = True

    conn = Conn()

    def connect(conn_str, **kwargs):
        seen["conn_str"] = conn_str; seen.update(kwargs); return conn

    monkeypatch.setitem(sys.modules, "pyodbc", types.SimpleNamespace(connect=connect))
    execute = server._execute_factory({"sql_host": "x.datawarehouse.fabric.microsoft.com", "sql_db": "shop_lh"}, "sql-token")
    assert seen["timeout"] == server.LOGIN_TIMEOUT and conn.timeout == server.QUERY_TIMEOUT
    assert "Encrypt=yes" in seen["conn_str"] and "sql-token" not in seen["conn_str"]      # the token travels as an attribute, not in the string
    assert 1256 in seen["attrs_before"]
    assert execute("select 1") == [{"TABLE_NAME": "orders", "COLUMN_NAME": "order_id"}]
    execute.close()
    assert conn.closed

    # _plan closes the connection even when the schema is empty and SchemaEmpty is raised
    conn.closed = False
    monkeypatch.setattr(server, "_headers", lambda ctx: {})
    monkeypatch.setattr(server, "_resolve_source", lambda *a: {"sql_host": "h", "sql_db": "d"})
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server.Schema, "from_sql", staticmethod(lambda execute, schema: []))
    with pytest.raises(server.SchemaEmpty):
        server._plan("ws", "src", "dbo", None, None, None)
    assert conn.closed


def test_query_resolves_the_api_by_exact_item_type(monkeypatch):
    """The by-name lookup takes a tuple of item types; a bare string would be a substring test on the type name."""
    import requests
    items = {"value": [{"displayName": "shop_api", "type": "Lakehouse", "id": "lh-1"},
                       {"displayName": "shop_api", "type": "GraphQLApi", "id": "api-1"}]}
    posted = []
    monkeypatch.setattr(server, "_headers", lambda ctx: {})
    monkeypatch.setattr(requests, "get", lambda url, **k: type("R", (), {"json": lambda self: items, "raise_for_status": lambda self: None})())
    monkeypatch.setattr(requests, "post", lambda url, **k: posted.append(url) or type("R", (), {"status_code": 200, "json": lambda self: {"data": {}}})())
    server.query_graphql("ws-1", "shop_api", "{ customers { items { name } } }")
    assert posted and posted[0].endswith("/graphqlapis/api-1/graphql")
