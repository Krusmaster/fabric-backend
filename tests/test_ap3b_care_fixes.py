"""Round AP3b (25 November 2026): the caretaker report's fixes after the founder's live run of /app. Fakes only: AP3's
doubles (tests/ap3_support.py on AP2's and AP1's: the synthetic SAP demo, an in-memory Fabric, Power BI's refresh
history, the health table); no Fabric, no tenant, invented names and ids.

Checked, one test or more per problem of the live run:
1. (the layout is tests/test_ap3b_browser.py)
2. Ids treated as names: a Krusgraph Model hands verify its created items' ids; the report names every item by its name,
   an item deleted since Create is said by its recorded name, an App is "not checked" by name, and the MCP tool
   verify_build looks an id up and names the item.
3. (the notebook format is tests/test_ap3b_notebook_format.py)
4. One rule for the update: the items verify_build finds different are the ones "Update the build in place" names and
   the ones its dry run updates; an item read back as the dry run is "Unchanged".
5. Time: the four sections are read at once under one budget; a section not done is "Not read in time" with Read again;
   the page's progress call; the page waits a little longer than the budget.
6. Health "Nothing yet" says why: the match by plan id is right, the reason is the pipeline's age.
And the coordinator's item: the verify card's "Refresh the model once" only refreshes, after a preview and a confirm.
"""
from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path

import pytest

pytest.importorskip("jwt")

import ap2_support as s2  # noqa: E402
import ap3_support as s3  # noqa: E402
from test_ap3_care import BUILD, app, build, built_here, care, healthy, keys, plan_id, section, sid, wait  # noqa: E402,F401
from fabric_backend import guided_build, guided_care  # noqa: E402

GUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
APP_ID = "0f0f0f0f-1111-4222-8333-444444444444"           # an invented App item, recorded at Create, never listed


def model_product(c, fabric, extra: list | None = None) -> str:
    """The session's build recorded by a Krusgraph Model (outputs.json with the ids Fabric gave), as the workload does."""
    run = guided_build.BUILDS.get(sid(c))
    created = [dict(x, workspace=x.get("workspace") or s2.BUILD_WS) for x in run["created"]] + list(extra or [])
    fabric.add_model(s2.BUILD_WS, "sales_model", {"created": created, "product": {"name": "Sales orders"}},
                     {"version": 1, "platform": "fabric", "workspaceId": s2.SOURCE_WS, "itemId": "lh-1", "itemType": "Lakehouse",
                      "displayName": "demo_lh", "schema": "dbo",
                      "target": {"itemId": s2.BUILD_LH, "displayName": "build_lh", "workspaceId": s2.BUILD_WS}},
                     run["run"]["rv"])
    guided_build.BUILDS.clear()
    ps = care(c, {"action": "products"}).json()["products"]
    assert [p["origin"] for p in ps] == ["model"]
    return ps[0]["id"]


def report(c, pid: str) -> dict:
    r = care(c, {"action": "report", "product": pid}).json()
    assert "error" not in r, r
    return r


def notebook_text(fabric, name: str) -> str:
    it = fabric.item(name)
    part = next(p for p in fabric.definitions[it["id"]]["parts"] if p["path"] == "notebook-content.py")
    return base64.b64decode(part["payload"]).decode()


def set_notebook(fabric, name: str, text: str) -> None:
    it = fabric.item(name)
    for p in fabric.definitions[it["id"]]["parts"]:
        if p["path"] == "notebook-content.py":
            p["payload"] = base64.b64encode(text.encode()).decode()


# ------------------------------------------------------------------ 2. ids are looked up, names are shown --------------

def test_the_report_names_items_by_name_never_by_the_ids_a_model_recorded(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    fabric.refreshes = []
    app_item = {"type": "AppBackend", "id": APP_ID, "name": "demo_lh_app", "workspace": s2.BUILD_WS, "output": "rayfin_app"}
    pid = model_product(c, fabric, [app_item])
    ids = {x["id"] for ws in fabric.items.values() for x in ws} | {APP_ID}
    r = report(c, pid)
    ver = section(r, "verify")
    text = json.dumps(r["sections"])
    assert not any(i in text for i in ids), [i for i in ids if i in text]
    assert ver["lines"][0].startswith("7 items read back")
    app_line = next(x for x in ver["lines"] if x.startswith("demo_lh_app (App)"))
    assert app_line.startswith("demo_lh_app (App): not checked.") and "no documented call reads what an App holds" in app_line
    assert "named" not in app_line and "time" not in app_line


def test_an_item_deleted_since_create_is_said_by_its_recorded_name(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    pid = model_product(c, fabric)
    pipe = fabric.item("demo_lh_pipeline")
    fabric.items[s2.BUILD_WS].remove(pipe)                                        # deleted in the portal
    r = report(c, pid)
    assert section(r, "pipeline")["lines"] == ["Not read: demo_lh_pipeline, the pipeline recorded at Create, is not in its "
                                               "workspace's item list any more (deleted, or moved to another workspace)."]
    line = next(x for x in section(r, "verify")["lines"] if x.startswith("demo_lh_pipeline (pipeline)"))
    assert "recorded at Create is not in the workspace's item list any more" in line
    assert pipe["id"] not in json.dumps(r) and s2.BUILD_WS not in json.dumps(r["sections"])


def test_verify_build_given_an_id_names_the_item(monkeypatch):
    """verify_build, the MCP tool, had the same gap: an id given in items found the item, but a line not read and one
    not found were said by the id. Now the id is looked up and every line is named by the item's display name."""
    import test_n229_verify_build as t
    src = t.local.sample_source()
    try:
        w = t.Workspace()
        _wire(monkeypatch, t, w, src.execute)
        out = t.verify({"semantic_model": t.MODEL_ID, "pipeline": "p-1"})
        names = [x["item"] for x in out["lines"]]
        assert "shop_model" in names and t.MODEL_ID not in json.dumps(out["lines"])
        out = t.verify({"api": "99999999-9999-4999-8999-999999999999"})
        assert out["lines"][0]["said"].startswith("99999999-9999-4999-8999-999999999999 (API for GraphQL): not checked. "
                                                  "Definition not checked: no item with the id")
    finally:
        src.close()


def _wire(monkeypatch, t, w, rows):
    from fabric_backend import server
    monkeypatch.setattr(server, "_source_inputs", lambda workspace, source, schema, keys, confirmed, ctx: (w.plan, dict(t.INFO)))
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_items", lambda ws, headers: list(w.items))
    monkeypatch.setattr(server, "_item_definition_parts", w.parts)
    monkeypatch.setattr(server, "_graphql_definition", lambda ws, api_id, headers: w.api)
    monkeypatch.setattr(server, "source_for", lambda ws, item, headers: ("ep-1", "SqlAnalyticsEndpoint"))
    monkeypatch.setattr(server, "_connected", lambda workspace, source, schema, ctx: (w.plan.schema, rows))
    monkeypatch.setattr(server, "_job_instances", lambda ws, item_id, headers: list(w.runs))
    monkeypatch.setattr(server, "_powerbi_refreshes", lambda ws, model_id, ctx: list(w.refreshes))
    monkeypatch.setattr(server, "_powerbi_dax", lambda ws, model_id, query, ctx: (_ for _ in ()).throw(RuntimeError("no DAX here")))


# ------------------------------------------------------------------ 4. one rule for the proposal and the dry run -------

def test_what_verify_finds_different_is_what_the_update_names_and_its_dry_run_updates(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    text = notebook_text(fabric, "demo_lh_silver")
    set_notebook(fabric, "demo_lh_silver", text.replace("TABLE_FORMAT = \"delta\"", "TABLE_FORMAT = \"parquet\"", 1))
    pid = model_product(c, fabric)
    r = report(c, pid)
    a = next(x for x in r["actions"] if x["act"] == "update_build")
    assert a["items"] == ["demo_lh_silver"]
    assert a["why"].startswith("demo_lh_silver differs from the dry run (from verify_build); the update writes them through "
                               "demo_lh_pipeline, whose Create writes its notebooks.")
    assert a["build"]["update"] == ["pipeline"]
    v = build(c, {"action": "dry_run", **{k: a["build"][k] for k in ("workspace", "source", "schema")},
                  "target": a["build"]["target"], "update": ["semantic_model", "data_agent"], "product": pid}).json()
    by = {x["kind"]: x for x in v["items"]}
    assert by["pipeline"]["action"] == "update" and "verify_build found demo_lh_silver different" in by["pipeline"]["words"]
    assert by["silver_notebook"]["action"] == "skip" and by["silver_notebook"]["badge"] == "With the pipeline"
    assert by["gold_views"]["badge"] == "With the pipeline"
    assert by["semantic_model"]["action"] == "skip" and by["semantic_model"]["badge"] == "Unchanged"   # the page's list ignored
    assert by["semantic_model"]["words"] == guided_build.UNCHANGED
    assert [x["name"] for x in v["creates"]] == ["demo_lh_pipeline"]


def test_a_product_verify_reads_back_as_the_dry_run_proposes_no_update(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    pid = model_product(c, fabric)
    r = report(c, pid)
    assert not any(x["act"] == "update_build" for x in r["actions"])
    assert guided_care.update_args(guided_care.product(sid(c), pid))["update"] == []


# ------------------------------------------------------------------ 5. one time budget, the four parts at once ---------

def test_the_four_parts_are_read_at_once_and_a_late_one_says_so(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    pid = model_product(c, fabric)
    monkeypatch.setattr(guided_care, "CARE_SECONDS", 1.5)
    monkeypatch.setattr(guided_care, "GRACE", 0.5)
    started = []
    slow = dict(guided_care.SECTIONS)

    def sleepy(p):
        started.append(time.monotonic())
        time.sleep(6)
        return slow["pipeline"](p)

    def quick(key):
        def f(p):
            started.append(time.monotonic())
            return guided_care._section(key, "ok", [f"{key} read"]), {}
        return f
    monkeypatch.setattr(guided_care, "SECTIONS", (("pipeline", sleepy), ("health", quick("health")), ("verify", quick("verify")),
                                                  ("drift", quick("drift"))))
    t0 = time.monotonic()
    r = report(c, pid)
    took = time.monotonic() - t0
    assert took < 5, took                                                         # not 6 s + the others one after another
    assert max(started) - min(started) < 1                                        # all four started together
    pipe = section(r, "pipeline")
    assert pipe["state"] == "unknown" and pipe["again"] is True
    assert pipe["lines"][0].startswith("Not read in time: the report's time budget of 1.5 s ran out before pipeline runs were read.")
    assert [section(r, k)["lines"] for k in ("health", "verify", "drift")] == [["health read"], ["verify read"], ["drift read"]]
    got = care(c, {"action": "progress", "product": pid}).json()
    assert [x["part"] for x in got["parts"]] == ["pipeline runs", "the health check", "verify_build", "the source"]
    assert [x["done"] for x in got["parts"]][1:] == [True, True, True]


def test_progress_is_not_rate_limited_and_names_only_this_sessions_products(app):
    c, fabric, _ = app
    for _ in range(80):                                                           # above the 60 a minute of the other calls
        got = care(c, {"action": "progress", "product": "p-none"})
        assert got.status_code == 200 and got.json()["kind"] == "not_found"


def test_the_page_waits_a_little_longer_than_the_servers_budget():
    js = (Path(__file__).parent.parent / "fabric_backend" / "static" / "app.js").read_text()
    wait_ms = int(re.search(r"var REPORT_WAIT_MS = (\d+);", js).group(1))
    assert guided_care.CARE_SECONDS * 1000 < wait_ms <= guided_care.CARE_SECONDS * 1000 + 15000
    assert "AbortController" in js and "did not answer within" in js
    assert "var CARE_PARALLEL = 2;" in js


# ------------------------------------------------------------------ 6. no health row: why ------------------------------

def test_no_health_table_after_a_good_run_says_the_pipeline_predates_the_health_step(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    s3.health_rows(monkeypatch, [])                                               # the check never wrote the table
    pid = model_product(c, fabric)
    h = section(report(c, pid), "health")
    assert h["state"] == "none"
    assert h["lines"] == ["The last run (2026-11-24) wrote no health table (krusgraph.health): its check notebook was built "
                          "before the check wrote health rows (Krusgraph's checks write them since 11 November 2026). Update "
                          "the build in place adds the health step."]


def test_a_check_built_by_an_earlier_krusgraph_is_named_as_the_reason(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    s3.health_rows(monkeypatch, [])
    name = "demo_lh_pipeline_check"
    old = "\n".join(ln for ln in notebook_text(fabric, name).splitlines()
                    if not ln.startswith(("RUN_ID =", "ALERT_KEY_VAULT =", "ALERT_SECRET_NAME =", "ALERT_ON =")))
    set_notebook(fabric, name, old.replace("Generated by Krusgraph from the checked plan", "Generated by Krusgraph from the plan"))
    pid = model_product(c, fabric)
    r = report(c, pid)
    assert section(r, "health")["lines"] == [
        "The last run (2026-11-24) was of a pipeline built by an earlier version of Krusgraph, before its check wrote health "
        "rows; Update the build in place adds the health step."]
    line = next(x for x in section(r, "verify")["lines"] if x.startswith(name))
    assert "built by an earlier version of Krusgraph; Update the build in place brings it to the current dry run" in line
    a = next(x for x in r["actions"] if x["act"] == "update_build")
    assert "built by an earlier version of Krusgraph" in a["why"] and a["build"]["update"] == ["pipeline"]


# ------------------------------------------------------------------ the verify card's refresh, refresh only ------------

def test_the_verify_cards_refresh_only_refreshes_after_a_preview_and_a_confirm(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    fabric.refreshes = []                                                         # verify_build: the model was never refreshed
    v = build(c, {"action": "verify"}).json()
    assert v["refresh"]["act"] == "refresh_model" and v["refresh"]["item"] == "demo_lh_model"
    pid = v["refresh"]["product"]
    fabric.calls.clear()
    before = len(fabric.refresh_requests)                                         # Create's own refresh of the new model
    pv = care(c, {"action": "preview", "product": pid, "act": "refresh_model"}).json()
    assert pv["item"] == "demo_lh_model" and len(fabric.refresh_requests) == before and fabric.writes == []   # writes nothing
    got = care(c, {"action": "confirm", "token": pv["token"], "names": ["demo_lh_model"]}).json()
    assert wait(c, care, got["operation_id"])["refresh"] == "refreshed"
    model = fabric.item("demo_lh_model")
    assert len(fabric.refresh_requests) == before + 1 and fabric.refresh_requests[-1].endswith(f"/datasets/{model['id']}/refreshes")
    assert [w for w in fabric.writes if not w[1].endswith("/refreshes")] == []   # one refresh call, no definition written
    assert not any(p.endswith(("/updateDefinition", "/semanticModels")) for _, p in fabric.calls)
    # the token was used: the same yes again does nothing
    again = care(c, {"action": "confirm", "token": pv["token"], "names": ["demo_lh_model"]}).json()
    assert again["kind"] == "stale" and len(fabric.refresh_requests) == before + 1


def test_the_verify_cards_refresh_with_an_expired_token_does_nothing(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    fabric.refreshes = []
    pid = build(c, {"action": "verify"}).json()["refresh"]["product"]
    before = len(fabric.refresh_requests)
    pv = care(c, {"action": "preview", "product": pid, "act": "refresh_model"}).json()
    monkeypatch.setattr(guided_care, "CARE_TTL", -1)
    got = care(c, {"action": "confirm", "token": pv["token"], "names": ["demo_lh_model"]}).json()
    assert got["kind"] == "stale" and len(fabric.refresh_requests) == before


# ------------------------------------------------------------------ create_semantic_model(refresh=true) on an existing one

def test_refresh_on_an_existing_model_says_one_thing_and_only_refreshes(monkeypatch):
    """The orchestrator's live dry run (25 November 2026) said both "the whole definition is replaced, 3 relationships
    would disappear" and "refreshed once and its definition is left as it is". The second is what the code does; the
    answer now says only that, and dry_run=false sends no definition."""
    import test_n229_verify_build as t
    from fabric_backend import server
    src = t.local.sample_source()
    try:
        w = t.Workspace()
        _wire(monkeypatch, t, w, src.execute)
        existing = {"existing": True, "id": t.MODEL_ID, "said": "A semantic model named 'shop_model' exists in the workspace; "
                    "with dry_run=false its whole definition is replaced: 0 table(s), 3 relationship(s) and 0 measure(s) listed below.",
                    "relationships_gone": ["order_items.orders_customer_id -> customers.customer_id"]}
        monkeypatch.setattr(server, "_model_replacement", lambda *a, **k: dict(existing))
        dry = json.loads(server.create_semantic_model("demo", "demo_lh", "shop_model", schema="shop", refresh=True))
        assert dry["mode"] == "refresh_only" and dry["replaces"]["applies"] is False
        assert dry["replaces"]["said"].startswith("shop_model exists, and refresh=true only refreshes it: its definition is not "
                                                  "sent and nothing in it is replaced or removed.")
        assert "left as it is" in dry["refresh"]["said"]
        plain = json.loads(server.create_semantic_model("demo", "demo_lh", "shop_model", schema="shop"))
        assert "mode" not in plain and plain["replaces"]["said"] == existing["said"]          # an update: as before
        asked = []
        monkeypatch.setattr(server, "_refresh_once", lambda ws, model_id, ctx: asked.append(model_id) or {"status": "refreshed"})
        monkeypatch.setattr(server, "_create_semantic_model", lambda *a, **k: pytest.fail("no definition is sent"))
        out = json.loads(server.create_semantic_model("demo", "demo_lh", "shop_model", schema="shop", refresh=True, dry_run=False))
        assert asked == [t.MODEL_ID] and out["result"]["mode"] == "refreshed_only" and out["mode"] == "refresh_only"
    finally:
        src.close()
