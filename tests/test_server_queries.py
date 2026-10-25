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
