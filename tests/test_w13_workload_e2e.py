"""W13: the end-to-end engine for the Model editor (workload/scripts/e2e/engine.py) answers as the editor expects.

engine.py serves the real /workload/v1 routes on tests/golden_support.py's Fabric and SQL doubles, so run.js can drive
the real editor in Chromium. These tests keep its scenarios honest without a browser: the shop review and check, the
empty schema, no access (403) and the big schema. Everything engine.app patches is put back after each test.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("starlette")
pytest.importorskip("jwt")
pytest.importorskip("cryptography")

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client():
    import requests
    from starlette.testclient import TestClient

    import golden_support as gs
    from fabric_backend import server, workload_host
    saved = {v: getattr(requests, v) for v in ("get", "post", "patch")}
    saved_mod, saved_exec = sys.modules.get("pyodbc"), gs._Cursor.execute
    saved_origin, saved_limiter = workload_host.same_host_origin, server.limiter
    spec = importlib.util.spec_from_file_location("w13_e2e_engine", ROOT / "workload/scripts/e2e/engine.py")
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    try:
        tc = TestClient(engine.app(None))
        token = tc.get("/e2e/token").json()["token"]

        def post(path, body):
            return tc.post("/workload/v1" + path, json=body, headers={"Authorization": f"Bearer {token}", "Origin": "http://127.0.0.1:8765"})
        yield tc, post, gs
    finally:
        for v, f in saved.items():
            setattr(requests, v, f)
        if saved_mod is None:
            sys.modules.pop("pyodbc", None)
        else:
            sys.modules["pyodbc"] = saved_mod
        gs._Cursor.execute = saved_exec
        workload_host.same_host_origin, server.limiter = saved_origin, saved_limiter


def src(gs, schema="shop"):
    return {"workspace": gs.WS, "source": gs.LH, "source_name": "demo_lh", "schema": schema}


def test_review_and_check_on_the_shop_schema(client):
    tc, post, gs = client
    r = post("/review", src(gs))
    assert r.status_code == 200
    assert r.json()["counts"]["keys"] == 6 and r.json()["counts"]["relationships"] == 7
    c = post("/check", {**src(gs), "review": r.json()["review"]}).json()
    assert c["check"]["keys"]["passed"] == 6 and c["check"]["relationships"]["passed"] == 7
    rows = {i["id"]: i["check"]["result"] for i in c["review"]["items"]}
    assert rows["key:order_items"]["rows"] == 134 and rows["key:orders"]["rows"] == 60   # the 2.2x the editor shows
    assert rows["rel:order_items.order_id>orders"]["orphans"] == 0


def test_the_empty_schema_and_no_access(client):
    tc, post, gs = client
    e = post("/review", src(gs, "dbo"))
    assert e.status_code == 404 and e.json()["kind"] == "schema_not_found"
    tc.post("/e2e/scenario", json={"name": "forbidden"})
    f = post("/schemas", {"workspace": gs.WS, "source": gs.LH})
    assert f.status_code == 403 and f.json()["kind"] == "no_access"   # the editor's schemaProblem words this


def test_the_big_schema(client):
    tc, post, gs = client
    tc.post("/e2e/scenario", json={"name": "big"})
    r = post("/review", src(gs)).json()
    assert r["counts"]["keys"] == 246 and r["counts"]["relationships"] == 247
