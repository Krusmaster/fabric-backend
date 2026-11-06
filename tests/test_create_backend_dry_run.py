"""Round n111: create_backend has a dry run, with the name and default of the other creating tools (dry_run=True). The
dry run says whether the item exists and would be updated or created, the definition and what changes in it, and the
checks that passed; it reads, and writes nothing. Fabric REST and the SQL endpoint are the doubles of
tests/golden_support.py: shop_api exists in the workspace, shop_api_v2 does not."""
import base64
import inspect
import json
import re
import sys
from pathlib import Path

import pytest

import golden_support as gs
from fabric_backend import mcp_server, server

_REAL_EXISTING_API = server._existing_api          # tests/conftest.py stubs the guard out; here it runs, as in production
ROOT = Path(__file__).resolve().parents[1]


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


SRC = {"workspace": gs.WS, "source": "demo_lh", "schema": "shop"}


def _writes(fake) -> list[tuple[str, str]]:
    """Every call that could change Fabric: anything but a GET and the read-only getDefinition."""
    return [c for c in fake.calls if c[0] != "GET" and not c[1].endswith("/getDefinition")]


def _sent(fake) -> dict:
    """graphql-definition.json of the one create or updateDefinition the real call sent."""
    assert len(fake.created) == 1, fake.created
    part = next(p for p in fake.created[0]["body"]["definition"]["parts"] if p["path"] == "graphql-definition.json")
    return json.loads(base64.b64decode(part["payload"]))


def test_the_default_is_a_dry_run_in_both_servers_like_the_other_creating_tools():
    for module in (server, mcp_server):
        for tool in ("create_backend", "create_views"):
            fn = getattr(module, tool)
            fn = getattr(fn, "__wrapped__", fn)
            assert inspect.signature(fn).parameters["dry_run"].default is True, (module.__name__, tool)


@pytest.mark.parametrize("name, extra", [("shop_api_v2", {}), ("shop_api", {"confirmed": [gs.SHIP_TO]}), ("shop_api", {})])
def test_the_dry_run_writes_nothing(fresh, name, extra):
    fake = fresh()
    out = json.loads(server.create_backend(**SRC, name=name, **extra))
    assert out["dry_run"] is True and "error" not in out, out
    assert _writes(fake) == [] and fake.created == []
    assert "result" not in out and "card" not in out


def test_a_new_name_is_reported_as_a_create(fresh):
    fresh()
    out = json.loads(server.create_backend(**SRC, name="shop_api_v2"))
    assert out["name"] == "shop_api_v2" and out["exists"] is False and out["would"] == "create" and "id" not in out
    assert out["rest"]["url"].endswith(f"/workspaces/{gs.WS}/graphQLApis") and out["parts"] == ["graphql-definition.json", ".platform"]
    assert len(out["changes"]["new_tables"]) == 7 and out["changes"]["tables_gone"] == []
    assert any("letters, digits and underscores" in c for c in out["checks_passed"])
    assert "validate_plan" in out["not_checked"]


def test_an_existing_name_is_reported_as_an_update_with_what_changes(fresh):
    fresh()
    out = json.loads(server.create_backend(**SRC, name="shop_api", confirmed=[gs.SHIP_TO]))
    assert out["exists"] is True and out["would"] == "update" and out["id"] == gs.API
    assert out["rest"]["url"].endswith(f"/items/{gs.API}/updateDefinition")
    assert set(out["changes"]) == {"new_tables", "tables_gone", "new_columns", "removed_columns", "relationships_unsupported",
                                   "new_relationships", "actions_changed", "source_changed"}
    drift = json.loads(server.plan_drift(**SRC, api="shop_api", confirmed=[gs.SHIP_TO]))
    assert out["would_change"] == drift["would_change"]
    assert {k: out["changes"][k] for k in ("new_tables", "tables_gone", "new_columns", "removed_columns")} == \
           {k: drift[k] for k in ("new_tables", "tables_gone", "new_columns", "removed_columns")}
    assert "the existing API's definition was read" in out["checks_passed"]
    assert "no relationship the API has today would be removed" in out["checks_passed"]


@pytest.mark.parametrize("name, extra", [("shop_api_v2", {}), ("shop_api", {"confirmed": [gs.SHIP_TO]}), ("shop_api", {}),
                                         ("shop_api_v2", {"tables": ["orders", "customers"], "writable": True})])
def test_the_dry_run_shows_exactly_what_a_real_create_sends(fresh, name, extra):
    fresh()
    preview = json.loads(server.create_backend(**SRC, name=name, **extra))
    fake = fresh()
    real = json.loads(server.create_backend(**SRC, name=name, dry_run=False, **extra))
    assert real["dry_run"] is False and real["result"]["status"] == "Succeeded", real
    assert preview["definition"] == _sent(fake)
    assert (preview["would"], real["result"]["mode"]) in {("create", "created"), ("update", "updated")}
    assert preview["rest"]["url"].endswith(fake.created[0]["route"])


def test_a_dry_run_that_would_remove_a_relationship_answers_as_the_real_call_does(fresh):
    renamed = [{**gs.SHIP_TO, "field_name": "address", "reverse_name": "shipments"}]
    fake = fresh()
    preview = json.loads(server.create_backend(**SRC, name="shop_api", confirmed=renamed))
    assert preview["kind"] == "would_remove" and fake.created == []
    fresh()
    real = json.loads(server.create_backend(**SRC, name="shop_api", confirmed=renamed, dry_run=False))
    assert preview == real


def test_the_local_dry_run_writes_nothing_and_matches_the_real_create(monkeypatch):
    import requests
    fake = gs.FakeFabric()
    for verb in ("get", "post", "patch"):
        monkeypatch.setattr(requests, verb, getattr(fake, verb))
    monkeypatch.setitem(sys.modules, "pyodbc", gs.fake_pyodbc())
    monkeypatch.setenv("FABRIC_ODBC", f"Driver={{ODBC Driver 18 for SQL Server}};Server={gs.SQL_HOST};Database=demo_lh")
    monkeypatch.setenv("FABRIC_TOKEN", "fabric-token")
    for var in ("FABRIC_SOURCE_KIND", "FABRIC_SCHEMAS_ENABLED", "KRUSGRAPH_PLATFORM"):
        monkeypatch.delenv(var, raising=False)
    args = {"workspace": gs.WS, "source": "demo_lh", "name": "shop_api", "schema": "shop"}
    preview = json.loads(mcp_server.create_backend(**args))
    assert preview["dry_run"] is True and preview["would"] == "update" and preview["exists"] is True
    assert _writes(fake) == [] and fake.created == []
    real = json.loads(mcp_server.create_backend(**args, dry_run=False))
    assert real["result"]["mode"] == "updated" and preview["definition"] == _sent(fake)


NO_DRY_RUN = re.compile(r"no dry run|without a dry run|has no dry run|for every tool but create_backend|"
                        r"all but create_backend show", re.I)


def test_no_text_says_create_backend_has_no_dry_run():
    from fabric_backend import tool_status
    files = [ROOT / "README.md", ROOT / "fabric_backend" / "page_templates" / "DOCS.md", ROOT / "fabric_backend" / "discovery.py",
             ROOT / "fabric_backend" / "server.py", ROOT / "fabric_backend" / "pages.py",
             *sorted((ROOT / "docs").glob("*.md")), *sorted((ROOT / "plugin").rglob("*.md"))]
    found = [f"{f.relative_to(ROOT)}: {m.group(0)!r}" for f in files if f.exists()
             for m in NO_DRY_RUN.finditer(f.read_text(encoding="utf-8"))]
    assert not found, found
    assert tool_status.NO_DRY_RUN == ()
    import asyncio
    for mcp in (server.mcp, mcp_server.mcp):
        text = json.dumps([t.model_dump(mode="json") for t in asyncio.run(mcp.list_tools())])
        assert not NO_DRY_RUN.search(text)
