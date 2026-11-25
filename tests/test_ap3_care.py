"""Round AP3: the caretaker in /app (fabric_backend/guided_care.py, the CARE route of guided_app.py). The read side and
the build are AP1's and AP2's doubles (tests/ap1_support.py, tests/ap2_support.py: Entra, the synthetic SAP demo, the
in-memory workspaces `demo` and `build`); tests/ap3_support.py adds Fabric's job list, Power BI's refresh history, the
health table and a Krusgraph Model item.

Checked: the data products are found from a Krusgraph Model's outputs.json and from this session's own Create; the
report says each source's result with the source named (the last pipeline run, the health check, verify_build, the source
against the plan) and a source that cannot be read says so without hiding the others; a failing pipeline, a red health
check, drift and an unrefreshed model each lead to the right proposal, at most three, and a healthy product to none; a
writing fix needs a preview's token and the confirm of its item's name, refuses a missing, wrong, used or stale token and
writes nothing then, and once confirmed writes once; "Update the build in place" is AP2's dry run on the product's basis
(its names, its items updated in place); every lock of AP1 holds on the new address, and no token or tenant id reaches an
answer or a log line.
"""
from __future__ import annotations

import copy
import json
import time

import pytest

pytest.importorskip("jwt")
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import ap1_support as s  # noqa: E402
import ap2_support as s2  # noqa: E402
import ap3_support as s3  # noqa: E402
from fabric_backend import access, flow_state, guided_app, guided_build, guided_care  # noqa: E402

CH = {"workspace": "demo", "source": "demo_lh", "schema": "dbo"}
ITEM = "rel:sap_vbap.MANDT+VBELN>sap_vbak"
BUILD = {"workspace": s2.BUILD_WS, "lakehouse": "build_lh"}


@pytest.fixture(scope="module")
def keys():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


@pytest.fixture
def app(monkeypatch, keys):
    flow_state.clear()
    guided_build.BUILDS.clear()
    guided_care.CARES.clear()
    monkeypatch.delenv(access.PIPELINE_EXECUTE_ENV, raising=False)
    a, auth, fake = s.entra_app(monkeypatch, keys)
    fabric = s3.data(monkeypatch)
    token = s.tok(keys[0])
    c = TestClient(a, base_url=s.ORIGIN, follow_redirects=False)
    c.__enter__()
    assert s.sign_in(c, fake, token).status_code == 302
    yield c, fabric, token
    c.__exit__(None, None, None)


def care(c, body: dict, **headers):
    h = {"Origin": s.ORIGIN, "Content-Type": "application/json", **headers}
    return c.post(guided_app.CARE, content=json.dumps(body), headers=h)


def build(c, body: dict):
    return c.post(guided_app.BUILD, content=json.dumps(body), headers={"Origin": s.ORIGIN, "Content-Type": "application/json"})


def wait(c, route, op_id: str, **extra) -> dict:
    for _ in range(200):
        st = route(c, {"action": "state", "operation_id": op_id, **extra}).json()
        if st.get("status") in ("done", "lost"):
            return st
        time.sleep(0.05)
    raise AssertionError("the operation did not finish")


def built_here(c) -> None:
    """AP2's whole path: the one decision, a dry run into the build workspace, Create of every item."""
    s.step(c, {**CH, "step": "decide", "decide": {"item": ITEM, "review": "accepted"}})
    v = build(c, {"action": "dry_run", **CH, "target": BUILD}).json()
    got = build(c, {"action": "confirm", "token": v["token"], "names": [x["name"] for x in v["creates"]]}).json()
    for it in got["items"]:
        op = build(c, {"action": "create", "run": got["run"], "kind": it["kind"]}).json()
        assert wait(c, build, op["operation_id"])["status"] == "done"


def sid(c) -> str:
    return guided_app._digest(c.cookies.get(guided_app.SESSION_COOKIE))


def plan_id(c) -> str:
    return guided_build.BUILDS.get(sid(c))["run"]["rv"]["plan_id"]


def healthy(c, fabric, monkeypatch) -> None:
    """A good last run of the pipeline and its notebooks, a green health check and a refreshed model."""
    for name in ("demo_lh_pipeline", "demo_lh_silver", "demo_lh_gold", "demo_lh_pipeline_check"):
        fabric.jobs[fabric.item(name)["id"]] = [s3.run("Completed")]
    s3.health_rows(monkeypatch, [s3.health_row(plan_id(c), "key", "silver.sap_vbak", "pass"),
                                 s3.health_row(plan_id(c), "drift", "dbo", "pass")])


def report_of(c, n: int = 0) -> dict:
    ps = care(c, {"action": "products"}).json()["products"]
    r = care(c, {"action": "report", "product": ps[n]["id"]}).json()
    assert "error" not in r, r
    return r


def section(r: dict, key: str) -> dict:
    return next(x for x in r["sections"] if x["key"] == key)


# ------------------------------------------------------------------ finding the data products --------------------------

def test_nothing_built_means_no_products_and_the_usual_journey(app):
    c, fabric, _ = app
    assert care(c, {"action": "products"}).json() == {"products": []}
    assert fabric.writes == []
    page = c.get(guided_app.PATH).text
    assert "Since last time" in page                                              # the greeting is data for app.js


def test_what_this_session_built_is_a_data_product(app):
    c, fabric, _ = app
    built_here(c)
    ps = care(c, {"action": "products"}).json()["products"]
    assert len(ps) == 1 and ps[0]["origin"] == "session" and ps[0]["source"] == "demo_lh · dbo"
    assert {"demo_lh_model", "demo_lh_pipeline", "demo_lh_report"} <= set(ps[0]["built"])
    assert ps[0]["id"].startswith("p-") and s2.BUILD_WS not in json.dumps(ps)


def test_a_krusgraph_models_outputs_json_is_a_data_product(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    run = guided_build.BUILDS.get(sid(c))
    created = [dict(x, workspace=x.get("workspace") or s2.BUILD_WS) for x in run["created"]]
    fabric.add_model(s2.BUILD_WS, "sales_model", {"created": created, "product": {"name": "Sales orders"},
                                                  "outputs": [{"type": "semantic_model", "name": "demo_lh_model", "enabled": True}]},
                     {"version": 1, "platform": "fabric", "workspaceId": s2.SOURCE_WS, "itemId": "lh-1", "itemType": "Lakehouse",
                      "displayName": "demo_lh", "schema": "dbo", "target": {"itemId": s2.BUILD_LH, "displayName": "build_lh",
                                                                            "workspaceId": s2.BUILD_WS}},
                     run["run"]["rv"])
    fabric.add_model(s2.BUILD_WS, "empty_model", {"created": []}, {"displayName": "demo_lh", "schema": "dbo"}, run["run"]["rv"])
    ps = care(c, {"action": "products"}).json()["products"]
    assert [p["name"] for p in ps] == ["Sales orders"]                            # the session's build is the Model's: listed once
    assert ps[0]["origin"] == "model" and "the Krusgraph Model sales_model in build" == ps[0]["from"]
    s3.health_rows(monkeypatch, [])                                               # no health table yet
    r = care(c, {"action": "report", "product": ps[0]["id"]}).json()
    assert {x["key"] for x in r["sections"]} == {"pipeline", "health", "verify", "drift"}
    assert section(r, "verify")["lines"][0].startswith("6 items read back")


# ------------------------------------------------------------------ the report, source by source ----------------------

def test_a_healthy_product_reports_each_source_and_proposes_nothing(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    before = list(fabric.writes)
    r = report_of(c)
    assert r["actions"] == [] and "all is well" in r["say"]
    pipe = section(r, "pipeline")
    assert pipe["source"] == "from the last pipeline run" and pipe["state"] == "ok"
    assert pipe["lines"][0] == "Latest run of demo_lh_pipeline: succeeded, started 2026-11-24 06:00 UTC, took 4m12s."
    assert "Failures: 0 of the last 1 run in Fabric's run history." in pipe["lines"]
    assert pipe["link"].startswith(f"https://app.fabric.microsoft.com/workloads/data-pipeline/monitoring/workspaces/{s2.BUILD_WS}/")
    health = section(r, "health")
    assert health["source"] == "from the health check's latest run" and health["state"] == "ok"
    assert health["lines"][0].startswith("Latest health check: green, every check passed in the latest run (run of 2026-11-24 06:04 UTC)")
    ver = section(r, "verify")
    assert ver["source"] == "from verify_build" and ver["title_note"] == "Checked by rules, not by AI"
    assert ver["facts"]["model_refresh"] == "verified"
    drift = section(r, "drift")
    assert drift["source"] == "from the source now, compared with the plan" and drift["state"] == "ok"
    assert drift["lines"] == ["The source still matches the plan: the same tables, columns, types, keys and links."]
    assert r["note"] == "Nothing was changed in Fabric: the report only reads."
    assert fabric.writes == before                                                # the report only reads


def test_a_failed_pipeline_run_says_why_and_proposes_running_it_once(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    pipe = fabric.item("demo_lh_pipeline")
    fabric.jobs[pipe["id"]] = [s3.run("Failed", "2026-11-25T06:00:00", "2026-11-25T06:01:05", "Activity failed"),
                               s3.run("Completed")]
    fabric.jobs[fabric.item("demo_lh_silver")["id"]] = [
        s3.run("Failed", "2026-11-25T06:00:10", "2026-11-25T06:01:00", "Capacity level limit exceeded for the workspace")]
    r = report_of(c)
    sec = section(r, "pipeline")
    assert sec["state"] == "bad"
    assert sec["lines"][0] == "Latest run of demo_lh_pipeline: failed, started 2026-11-25 06:00 UTC, took 1m05s."
    assert any(x.startswith("Failed step: ") and "Capacity level limit exceeded" in x for x in sec["lines"])
    assert any(x.startswith("What usually helps (a heuristic") for x in sec["lines"])
    assert "Failures: 1 of the last 2 runs in Fabric's run history." in sec["lines"]
    # the opt-in switch is off: the proposal is the manual step, with the pipeline's link, and nothing that writes
    a = r["actions"][0]
    assert a["act"] == "run_manual" and a["writes"] is False and "DataPipeline.Execute.All" in a["why"]
    assert a["steps"][0].startswith("Run it once: open the pipeline in Fabric") and a["link"].endswith(pipe["id"])
    assert care(c, {"action": "preview", "product": r["product"]["id"], "act": "run_pipeline"}).json()["kind"] == "bad_request"
    # with the operator's switch on (and the sign-in's permission unknown, so Fabric decides), it is a button
    monkeypatch.setenv(access.PIPELINE_EXECUTE_ENV, "true")
    r = report_of(c)
    assert r["actions"][0]["act"] == "run_pipeline" and r["actions"][0]["label"] == "Run the pipeline once"
    assert r["actions"][0]["why"].startswith("The latest run failed (from the last pipeline run).")


def test_a_red_health_check_with_broken_links_proposes_re_checking_them(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    s3.health_rows(monkeypatch, [s3.health_row(plan_id(c), "orphans", "silver.sap_vbap", "fail", 3),
                                 s3.health_row(plan_id(c), "freshness", "dbo.sap_vbak", "warn", 1)])
    r = report_of(c)
    sec = section(r, "health")
    assert sec["state"] == "bad" and sec["lines"][0].startswith("Latest health check: red, 1 failed, 1 warning(s) in the latest run")
    assert sec["lines"][1] == "1 key or link check failed: silver.sap_vbap."
    assert "1 key or link check no longer holds against the rows (from the health check's latest run)." in section(r, "drift")["lines"]
    a = [x for x in r["actions"] if x["act"] == "recheck_links"]
    assert a and a[0]["writes"] is False and "(from the health check's latest run)" in a[0]["why"]
    before = list(fabric.writes)
    got = care(c, {"action": "recheck", "product": r["product"]["id"]}).json()
    assert got["title"] == "Checked by rules, not by AI" and got["counts"]["checked"] > 0
    assert got["lines"][0].endswith("hold now (counted against the rows now).")
    assert any("sap_vbap.MANDT+VBELN → sap_vbak: does not hold (1 row). You accepted it so" in x for x in got["lines"])
    assert fabric.writes == before                                                # re-checking only counts


def test_drift_since_the_plan_is_named_and_proposes_an_update_in_place(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    rv = guided_build.BUILDS.get(sid(c))["run"]["rv"]
    old = copy.deepcopy(rv)
    gone = sorted(old["snapshot"]["tables"])[0]
    del old["snapshot"]["tables"][gone]                                          # a table the plan did not have
    old["snapshot"]["tables"]["sap_vbak"]["columns"]["LEGACY_FLAG"] = "varchar"   # a column the source no longer has
    guided_build.BUILDS.get(sid(c))["run"]["rv"] = old
    r = report_of(c)
    sec = section(r, "drift")
    assert sec["state"] == "bad" and sec["facts"]["changed"] is True
    assert f"New table in the source: {gone}." in sec["lines"]
    assert "Column gone: sap_vbak.LEGACY_FLAG." in sec["lines"]
    a = next(x for x in r["actions"] if x["act"] == "update_build")
    assert a["why"].startswith("The source changed since the plan (from the source now, compared with the plan).")
    assert a["build"]["product"] == r["product"]["id"] and a["build"]["target"] == BUILD
    assert a["build"]["update"] == ["silver_notebook", "gold_views", "pipeline", "semantic_model", "data_agent"]


def test_an_unrefreshed_model_proposes_one_refresh(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    fabric.refreshes = []
    r = report_of(c)
    assert section(r, "verify")["facts"]["model_refresh"] == "differs"
    assert [x["act"] for x in r["actions"]] == ["refresh_model"]
    assert r["actions"][0]["why"] == "The model has no completed refresh (from verify_build)."


def test_a_source_that_cannot_be_read_says_so_and_the_others_stand(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    from fabric_backend import workload_api

    def broken(req):
        raise RuntimeError("the endpoint is asleep")
    monkeypatch.setattr(workload_api, "run_health", broken)
    r = report_of(c)
    assert section(r, "health")["state"] == "unknown" and section(r, "health")["lines"][0].startswith("Not read: ")
    assert section(r, "pipeline")["state"] == "ok" and section(r, "verify")["lines"]


def test_never_more_than_three_proposals_in_the_rules_order():
    sig = {"pipeline": {"id": "p", "name": "x_pipeline", "workspace": "w"}, "pipeline_state": "failed", "drift": True,
           "links_failing": 2, "needs_refresh": True, "verify_differs": 1}
    acts = guided_care.propose(sig, (True, ""))
    assert [a["act"] for a in acts] == ["run_pipeline", "update_build", "recheck_links"]
    assert [a["act"] for a in guided_care.propose({**sig, "pipeline_state": "ok"}, (True, ""))] == \
        ["update_build", "recheck_links", "refresh_model"]
    assert guided_care.propose({"pipeline": sig["pipeline"], "pipeline_state": "ok"}, (True, "")) == []
    assert guided_care.propose({**sig, "pipeline_state": "never"}, (False, "Off here."))[0]["act"] == "run_manual"


# ------------------------------------------------------------------ the writing fixes: preview, confirm, once ----------

def test_a_refresh_needs_the_previews_token_and_the_items_name_and_runs_once(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    fabric.refreshes = []
    pid = report_of(c)["product"]["id"]
    assert care(c, {"action": "preview", "product": pid, "act": "run_pipeline"}).json()["kind"] == "bad_request"  # not proposed
    before = len(fabric.refresh_requests)
    pv = care(c, {"action": "preview", "product": pid, "act": "refresh_model"}).json()
    assert pv["token"].startswith("care-") and pv["item"] == "demo_lh_model" and "nothing is done until you confirm" in pv["note"]
    assert len(fabric.refresh_requests) == before                                 # the preview writes nothing
    assert care(c, {"action": "confirm", "token": "care-" + "0" * 32, "names": ["demo_lh_model"]}).json()["kind"] == "stale"
    assert care(c, {"action": "confirm", "token": pv["token"], "names": ["demo_lh_report"]}).json()["kind"] == "bad_request"
    assert care(c, {"action": "confirm", "token": pv["token"], "names": ["demo_lh_model"]}).json()["kind"] == "stale"   # used
    assert len(fabric.refresh_requests) == before
    pv = care(c, {"action": "preview", "product": pid, "act": "refresh_model"}).json()
    got = care(c, {"action": "confirm", "token": pv["token"], "names": ["demo_lh_model"]}).json()
    assert got["act"] == "refresh_model" and got["operation_id"]
    st = wait(c, care, got["operation_id"])
    assert st["refresh"] == "refreshed" and st["words"].startswith("Refreshed once")
    assert len(fabric.refresh_requests) == before + 1
    model = fabric.item("demo_lh_model")
    assert fabric.refresh_requests[-1].endswith(f"/datasets/{model['id']}/refreshes")
    assert not any(m == "DELETE" for m, _ in fabric.calls)


def test_an_item_renamed_after_the_preview_makes_its_token_stale(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    fabric.refreshes = []
    pid = report_of(c)["product"]["id"]
    pv = care(c, {"action": "preview", "product": pid, "act": "refresh_model"}).json()
    fabric.item("demo_lh_model")["displayName"] = "renamed_model"
    before = len(fabric.refresh_requests)
    got = care(c, {"action": "confirm", "token": pv["token"], "names": ["demo_lh_model"]}).json()
    assert got["kind"] == "stale" and "renamed" in got["hint"]
    assert len(fabric.refresh_requests) == before


def test_an_old_preview_is_stale(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    fabric.refreshes = []
    pid = report_of(c)["product"]["id"]
    pv = care(c, {"action": "preview", "product": pid, "act": "refresh_model"}).json()
    monkeypatch.setattr(guided_care, "CARE_TTL", -1)
    assert care(c, {"action": "confirm", "token": pv["token"], "names": ["demo_lh_model"]}).json()["kind"] == "stale"


def test_running_the_pipeline_once_needs_the_switch_a_preview_and_the_confirm(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    monkeypatch.setenv(access.PIPELINE_EXECUTE_ENV, "1")
    pipe = fabric.item("demo_lh_pipeline")
    fabric.jobs[pipe["id"]] = [s3.run("Failed", message="Activity failed")]
    pid = report_of(c)["product"]["id"]
    pv = care(c, {"action": "preview", "product": pid, "act": "run_pipeline"}).json()
    assert pv["item"] == "demo_lh_pipeline" and "No schedule is added" in pv["say"] and fabric.started_runs == []
    monkeypatch.delenv(access.PIPELINE_EXECUTE_ENV)                              # the operator turned it off meanwhile
    got = care(c, {"action": "confirm", "token": pv["token"], "names": ["demo_lh_pipeline"]}).json()
    assert got["kind"] == "needs_permission" and fabric.started_runs == []
    monkeypatch.setenv(access.PIPELINE_EXECUTE_ENV, "1")
    pv = care(c, {"action": "preview", "product": pid, "act": "run_pipeline"}).json()
    got = care(c, {"action": "confirm", "token": pv["token"], "names": ["demo_lh_pipeline"]}).json()
    assert got["state"] == "queued" and got["words"] == "demo_lh_pipeline: queued in Fabric."
    assert fabric.started_runs == [pipe["id"]]                                    # one run, of that pipeline
    assert got["link"].startswith("https://app.fabric.microsoft.com/")
    assert care(c, {"action": "confirm", "token": pv["token"], "names": ["demo_lh_pipeline"]}).json()["kind"] == "stale"
    assert fabric.started_runs == [pipe["id"]]


def test_update_in_place_is_ap2s_dry_run_on_the_products_basis(app, monkeypatch):
    c, fabric, _ = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    rv = guided_build.BUILDS.get(sid(c))["run"]["rv"]
    old = copy.deepcopy(rv)
    old["snapshot"]["tables"]["sap_vbak"]["columns"]["LEGACY_FLAG"] = "varchar"
    guided_build.BUILDS.get(sid(c))["run"]["rv"] = old
    r = report_of(c)
    args = next(x for x in r["actions"] if x["act"] == "update_build")["build"]
    assert build(c, {"action": "dry_run", **{k: v for k, v in args.items() if k != "product"}, "product": "p-unknown"}).status_code == 400
    count, writes = len(fabric.created()), list(fabric.writes)
    v = build(c, {"action": "dry_run", **args}).json()
    assert v["stage"] == "dry_run" and v["target"]["line"] == "build › build_lh"
    assert [x["name"] for x in v["items"]] == ["demo_lh_silver", "demo_lh_gold", "demo_lh_pipeline", "demo_lh_model",
                                               "demo_lh_report", "demo_lh_agent"]
    assert [(x["name"], x["badge"]) for x in v["items"]] == [
        ("demo_lh_silver", "Update in place"), ("demo_lh_gold", "Update in place"), ("demo_lh_pipeline", "Update in place"),
        ("demo_lh_model", "Update in place"), ("demo_lh_report", "Already built"), ("demo_lh_agent", "Update in place")]
    assert len(fabric.created()) == count and fabric.writes == writes              # the dry run writes nothing
    got = build(c, {"action": "confirm", "token": v["token"], "names": [x["name"] for x in v["creates"]]}).json()
    for it in got["items"]:
        op = build(c, {"action": "create", "run": got["run"], "kind": it["kind"]}).json()
        assert wait(c, build, op["operation_id"])["item"]["action"] == "update"
    assert len(fabric.created()) == count                                         # updated in place: no new item
    ours = {fabric.item(n)["id"] for n in ("demo_lh_silver", "demo_lh_gold", "demo_lh_pipeline", "demo_lh_model", "demo_lh_agent")}
    updated = {p.split("/")[-2] for m, p in fabric.writes[len(writes):] if p.endswith("/updateDefinition")}
    assert updated and updated <= ours | {fabric.item("demo_lh_pipeline_check")["id"]}
    ver = build(c, {"action": "verify"}).json()
    assert ver["title"] == "Checked by rules, not by AI"
    assert not any(m == "DELETE" for m, _ in fabric.calls)


# ------------------------------------------------------------------ AP1's locks on the new address ---------------------

def test_the_care_address_is_the_sites_404_while_the_list_is_empty(monkeypatch, keys):
    a, _, fake = s.entra_app(monkeypatch, keys, None)
    with TestClient(a, base_url=s.ORIGIN, follow_redirects=False) as c:
        assert care(c, {"action": "products"}).status_code == 404
        assert care(c, {"action": "products"}).text == "not found"
        assert c.get(guided_app.CARE, headers={"Accept": "text/html"}).status_code == 404


def test_a_foreign_tenant_gets_the_sites_404_and_the_care_address_reads_nothing(monkeypatch, keys):
    a, _, fake = s.entra_app(monkeypatch, keys)
    fabric = s3.data(monkeypatch)
    with TestClient(a, base_url=s.ORIGIN, follow_redirects=False) as c:
        r = s.sign_in(c, fake, s.tok(keys[0], tid=s.OTHER))
        assert r.status_code == 404
        assert not any(x.startswith(guided_app.SESSION_COOKIE + "=") for x in r.headers.get_list("set-cookie"))
        fabric.calls.clear()
        assert care(c, {"action": "products"}).status_code == 401                 # no session: nothing is read
        assert fabric.calls == []
        s.sign_in(c, fake, s.tok(keys[0]), code="code-2")
        assert care(c, {"action": "products"}).status_code == 200
        monkeypatch.setenv(guided_app.ENV, s.OTHER)                               # the list changed: the session ends
        assert care(c, {"action": "products"}).status_code == 401
        monkeypatch.setenv(guided_app.ENV, "")
        assert care(c, {"action": "products"}).status_code == 404


def test_the_care_address_takes_json_from_this_sites_page_only(app):
    c = app[0]
    assert care(c, {"action": "products"}, Origin="https://evil.example").status_code == 403
    r = c.post(guided_app.CARE, content=json.dumps({"action": "products"}), headers={"Origin": s.ORIGIN, "Content-Type": "text/plain"})
    assert r.status_code == 403
    assert care(c, {"action": "delete"}).status_code == 400
    assert care(c, {"action": "products", "pad": "x" * 5000}).status_code == 400
    assert c.get(guided_app.CARE).status_code == 404
    assert care(c, {"action": "report", "product": "p-nothing"}).json()["kind"] == "not_found"


def test_no_token_or_tenant_id_in_answers_or_logs(app, monkeypatch, capsys):
    c, fabric, token = app
    built_here(c)
    healthy(c, fabric, monkeypatch)
    fabric.refreshes = []
    r = report_of(c)
    pv = care(c, {"action": "preview", "product": r["product"]["id"], "act": "refresh_model"}).json()
    got = care(c, {"action": "confirm", "token": pv["token"], "names": [pv["item"]]}).json()
    st = wait(c, care, got["operation_id"])
    text = json.dumps([r, pv, got, st]) + capsys.readouterr().out
    assert token not in text and s.TID not in text and "obo|" not in text
