"""create_backend with the workspace given by its display name (found in round n13): the name has to be looked up to
the workspace id before anything else uses it. Before the fix the plan was made against the id, but the source lookup,
the API definition, the create call and the connection card got the name, and Fabric answered 404.

Fabric REST and the SQL endpoint are the doubles of tests/golden_support.py; each call gets a fresh workspace, so a
call by name and a call by id start from the same state."""
import json
import sys

import pytest

import golden_support as gs
from fabric_backend import server

_REAL_EXISTING_API = server._existing_api          # tests/conftest.py stubs the guard out; here it runs, as in production


@pytest.fixture
def fresh(monkeypatch):
    import requests

    def make():
        fake = gs.FakeFabric()
        for verb in ("get", "post", "patch"):
            monkeypatch.setattr(requests, verb, getattr(fake, verb))
        monkeypatch.setitem(sys.modules, "pyodbc", gs.fake_pyodbc())
        return fake
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "limiter", None)
    monkeypatch.setattr(server, "_existing_api", _REAL_EXISTING_API)
    return make


def _call(make, **kw):
    fake = make()
    out = json.loads(server.create_backend(source="demo_lh", schema="shop", **kw))
    return out, fake


@pytest.mark.parametrize("name, extra", [("shop_api_v2", {}), ("shop_api", {}), ("shop_api", {"confirmed": [gs.SHIP_TO]})])
def test_a_workspace_name_gives_the_same_result_as_its_id(fresh, name, extra):
    by_id, fake_id = _call(fresh, workspace=gs.WS, name=name, **extra)
    by_name, fake_name = _call(fresh, workspace="demo", name=name, **extra)
    assert "error" not in by_id or by_id["kind"] == "would_remove", by_id
    assert by_name == by_id
    assert fake_name.created == fake_id.created
    # no request ever carries the name where Fabric expects the id
    assert not [c for c in fake_name.calls if "/workspaces/demo" in c[1]], fake_name.calls
    # the name costs one lookup (GET /v1/workspaces) and nothing else changes
    assert fake_name.calls.count(("GET", "/v1/workspaces")) == 1
    assert [c for c in fake_name.calls if c != ("GET", "/v1/workspaces")] == [c for c in fake_id.calls if c != ("GET", "/v1/workspaces")]


def test_the_definition_and_the_card_carry_the_workspace_id(fresh):
    out, fake = _call(fresh, workspace="DEMO", name="shop_api_v2")                 # case does not matter, as elsewhere
    assert out["result"]["status"] == "Succeeded" and gs.WS in out["card"] and "/workspaces/DEMO" not in out["card"]
    created = json.dumps(fake.created)
    assert "DEMO" not in created and '"demo"' not in created


def test_an_unknown_or_ambiguous_workspace_name_answers_before_anything_is_written(fresh, monkeypatch):
    out, fake = _call(fresh, workspace="nowhere", name="shop_api_v2")
    assert out["kind"] == "not_found" and "nowhere" in out["error"] and not fake.created
    assert all(m == "GET" for m, _ in fake.calls)
    monkeypatch.setattr(server, "_workspaces", lambda headers: [{"id": gs.WS, "name": "demo"},
                                                                {"id": "99999999-2222-3333-4444-555555555555", "name": "Demo"}])
    out, fake = _call(fresh, workspace="demo", name="shop_api_v2")
    assert out["kind"] == "bad_input" and gs.WS in out["error"] and not fake.created
