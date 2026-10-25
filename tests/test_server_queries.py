import json

import pytest

from fabric_backend import server


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
