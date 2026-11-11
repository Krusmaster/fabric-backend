"""Round n173: the Krusgraph Model editor checks the review against the rows (POST /workload/v1/check).

The founder's ask, 8 November 2026: after the review, "Check against the rows" inside the editor, which runs validate_plan's
counting queries, shows each key and relationship as passed, failed (orphans, duplicates) or not checked, and lets the dry
run say what passed instead of "Not checked: validate_plan". The route has the same audience and on-behalf-of path as
/review and /build (tests/test_workload_api.py); here: its shape, that it runs as the user and writes nothing, the counts
of a failing check on a copy of seed.py's synthetic shop with one orphan and one duplicate key, the map the editor draws,
the inline answers to Thinker's questions (keys, confirmed), and that the editor's copy of the cards' map code is current
(workload/scripts/build_card_map.py)."""
import json
import runpy
import sys
from pathlib import Path

import pytest

pytest.importorskip("jwt")

import golden_support as gs  # noqa: E402
from fabric_backend import entra, workload_api  # noqa: E402
from test_workload_api import FABRIC_ORIGIN, MCP, SRC, TID, WL, FakeJWKS, FakeOBO, _post, _writes, api, keys, tok  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[1]


def _review(client, priv, **extra):
    return _post(client, "/review", {**SRC, **extra}, tok(priv)).json()


# ------------------------------------------------------------------ shape, audience, on-behalf-of --------------------

def test_check_answers_with_the_review_checked_the_totals_the_map_and_the_questions(api):
    client, fake, obo, priv = api
    rv = _review(client, priv)["review"]
    fake.calls.clear()
    obo.calls.clear()
    r = _post(client, "/check", {**SRC, "review": rv}, tok(priv))
    assert r.status_code == 200, r.text
    out = r.json()
    assert set(out) == {"review", "summary", "attention", "counts", "map", "note", "check", "questions", "suggested_products"}   # n222
    c = out["check"]
    assert c["keys"] == {"passed": 6, "failed": 0, "stale": 0, "not_checked": 0}
    assert c["relationships"] == {"passed": 7, "failed": 0, "stale": 0, "not_checked": 0}
    assert c["checked"] == 13 and c["failed"] == [] and c["checked_at"].endswith("Z")
    assert all(it["check"]["status"] == "passed" for it in out["review"]["items"])
    assert {r["state"] for r in out["map"]["relationships"]} == {"passed"}
    assert {t.get("key_check") for t in out["map"]["tables"]} == {"passed", None}        # audit_log has no key
    assert [q["about"] for q in out["questions"]] == ["key:audit_log"]
    assert {s for _, s in obo.calls} == {entra.FABRIC_SCOPE, entra.SQL_SCOPE} and {t for t, _ in obo.calls} == {TID}
    assert _writes(fake) == [] and "Nothing was created" in out["note"]
    text = json.dumps(out)
    assert "Harbour Bikes" not in text and "obo:" not in text and "wl-secret" not in text


def test_check_keeps_the_decisions_of_the_review(api):
    client, _, _, priv = api
    first = _review(client, priv)["review"]
    rel = next(it["id"] for it in first["items"] if it["type"] == "relationship")
    decided = _review(client, priv, decisions=[{"item": rel, "review": "rejected", "reason": "not a reference"},
                                               {"item": "key:orders", "review": "accepted"}])["review"]
    out = _post(client, "/check", {**SRC, "review": decided}, tok(priv)).json()
    by = {it["id"]: it for it in out["review"]["items"]}
    assert by[rel]["review"] == "rejected" and by[rel]["reason"] == "not a reference"
    assert by["key:orders"]["review"] == "accepted"
    assert next(r for r in out["map"]["relationships"] if "rel:" + r["id"] == rel)["review"] == "rejected"


def test_check_takes_only_the_workload_audience(api):
    client, fake, obo, priv = api
    for t in (tok(priv, aud=MCP.public_url), tok(priv, aud="api://someone-else"), None):
        r = _post(client, "/check", {**SRC, "review": {"format": "krusgraph-review"}}, t)
        assert r.status_code == 401 and r.json()["kind"] == "sign_in"
    assert fake.calls == [] and obo.calls == []


def test_check_answers_fabric_origins_only(api):
    client, fake, _, priv = api
    r = _post(client, "/check", {**SRC, "review": {}}, tok(priv), origin="https://evil.example.com")
    assert r.status_code == 403 and fake.calls == []
    r = client.options(workload_api.PREFIX + "/check", headers={"Origin": FABRIC_ORIGIN, "Access-Control-Request-Method": "POST"})
    assert r.status_code == 204 and r.headers["access-control-allow-origin"] == FABRIC_ORIGIN
    assert "frame-ancestors" in r.headers["content-security-policy"]


@pytest.mark.parametrize("body, word", [({**SRC}, "review"), ({**SRC, "review": "x"}, "review"),
                                        ({**SRC, "review": {}, "max_items": 0}, "max_items"),
                                        ({**SRC, "review": {}, "max_items": True}, "max_items"),
                                        ({"review": {}}, "workspace")])
def test_check_refuses_bad_bodies(api, body, word):
    client, fake, obo, priv = api
    r = _post(client, "/check", body, tok(priv))
    assert r.status_code == 400 and word in r.json()["error"] and fake.calls == [] and obo.calls == []


def test_check_with_a_review_from_elsewhere_is_explained(api):
    client, fake, _, priv = api
    r = _post(client, "/check", {**SRC, "review": {"format": "something else"}}, tok(priv))
    assert r.status_code >= 400 and r.json()["error"] and _writes(fake) == []


# ------------------------------------------------------------------ a check that fails ------------------------------

@pytest.fixture
def broken_api(keys, monkeypatch):
    """The shop with one order whose customer does not exist (an orphan) and a customer id given twice (a duplicate)."""
    db = gs.shop_database()
    db.execute("INSERT INTO shop.[orders] VALUES (90001, 987654, '2026-01-02', 1)")
    first = db.execute("SELECT customer_id, name, country FROM shop.[customers] LIMIT 1").fetchone()
    db.execute("INSERT INTO shop.[customers] VALUES (?, ?, ?)", first)
    import requests
    from starlette.applications import Starlette
    from starlette.testclient import TestClient
    from fabric_backend import server
    from fabric_backend.entra import Validator
    priv, pub = keys
    fake = gs.FakeFabric()
    for verb in ("get", "post", "patch"):
        monkeypatch.setattr(requests, verb, getattr(fake, verb))
    monkeypatch.setitem(sys.modules, "pyodbc", gs.fake_pyodbc(db))
    monkeypatch.setattr(server, "limiter", None)
    app = Starlette(routes=workload_api.routes(WL, Validator(WL, FakeJWKS(pub)), FakeOBO()))
    return TestClient(app), fake, priv


def test_a_failed_check_says_how_many_orphans_and_duplicates(broken_api):
    client, fake, priv = broken_api
    rv = _review(client, priv)["review"]
    out = _post(client, "/check", {**SRC, "review": rv}, tok(priv)).json()
    failed = {f["id"]: f for f in out["check"]["failed"]}
    assert failed["key:customers"]["duplicates"] == 1 and failed["key:customers"]["nulls"] == 0
    orphan = failed["rel:orders.customer_id>customers"]
    assert orphan["orphans"] == 1 and orphan["rows_with_value"] > 1
    assert out["check"]["keys"]["failed"] == 1 and out["check"]["relationships"]["failed"] >= 1
    m = {r["id"]: r for r in out["map"]["relationships"]}
    assert m["orders.customer_id>customers"]["state"] == "failed" and m["orders.customer_id>customers"]["orphans"] == 1
    assert next(t for t in out["map"]["tables"] if t["name"] == "customers")["key_check"] == "failed"
    assert any(a.startswith("Check failed") for a in out["attention"])
    assert _writes(fake) == []
    assert "987654" not in json.dumps(out["check"])                     # counts, never a value


# ------------------------------------------------------------------ the dry run after a check -----------------------

def test_the_dry_run_after_a_check_says_what_passed(api):
    client, _, _, priv = api
    rv = _review(client, priv)["review"]
    before = _post(client, "/build", {**SRC, "name": "shop_model_api", "review": rv}, tok(priv)).json()
    assert "validate_plan" in before["not_checked"] and before["row_check"]["checked"] == 0
    checked = _post(client, "/check", {**SRC, "review": rv}, tok(priv)).json()["review"]
    after = _post(client, "/build", {**SRC, "name": "shop_model_api", "review": checked}, tok(priv)).json()
    assert "not_checked" not in after
    assert after["row_check"]["keys"]["passed"] == 6 and after["row_check"]["relationships"]["passed"] == 7


# ------------------------------------------------------------------ Thinker's questions answered inline -------------

def test_a_key_given_for_the_keyless_table_becomes_an_accepted_key(api):
    client, _, _, priv = api
    first = _review(client, priv)
    assert [q["about"] for q in first["review"]["open_questions"]] == ["key:audit_log"]
    out = _review(client, priv, previous=first["review"], keys={"audit_log": ["event", "happened_at"]})
    key = next(it for it in out["review"]["items"] if it["id"] == "key:audit_log")
    assert key["rule"] == "K1" and key["review"] == "accepted" and key["columns"] == ["event", "happened_at"]
    assert out["review"]["open_questions"] == []
    again = _review(client, priv, previous=out["review"])                       # carried by the saved review
    assert any(it["id"] == "key:audit_log" for it in again["review"]["items"])


@pytest.mark.parametrize("extra, word", [({"keys": {"audit_log": []}}, "keys"), ({"keys": ["x"]}, "keys"),
                                         ({"confirmed": [{"source": "a"}]}, "confirmed")])
def test_review_refuses_bad_answers(api, extra, word):
    client, fake, _, priv = api
    r = _post(client, "/review", {**SRC, **extra}, tok(priv))
    assert r.status_code == 400 and word in r.json()["error"] and fake.calls == []


# ------------------------------------------------------------------ the editor's copy of the cards' map --------------

def test_the_editors_map_code_is_the_cards_own_and_current():
    """The editor draws the map with the MCP Apps cards' code (n170/n172), copied by workload/scripts/build_card_map.py;
    a change to the cards without running the script fails here, so the two never diverge."""
    mod = runpy.run_path(str(ROOT / "workload" / "scripts" / "build_card_map.py"))
    want = mod["render"]()
    got = (ROOT / mod["OUT"]).read_text(encoding="utf-8")
    assert got == want, "run: python workload/scripts/build_card_map.py"
    from fabric_backend import mcp_apps_pictures as P
    assert P.DRAW_JS.strip()[:40] in got and "function drawMap(box, m)" in got and "export { drawMap" in got
