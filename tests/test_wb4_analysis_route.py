"""WB4 (20 Nov 2026): the analysis pack in the Krusgraph Model item. POST /workload/v1/analysis runs analysis_plan
(round AP2) on the item's reviewed plan, read-only, and only after the check has passed for a key or link. On the
24-month synthetic SAP sample (sap_sd, the e2e engine's `sap` scenario) it ranks A7 and A3 ready with their notebooks,
A8 partial without one, and says what the not-ready analyses need. On the shop schema it says there is nothing SAP to
rank. Synthetic data and the Fabric and SQL doubles only."""
from __future__ import annotations

import json

import pytest

from test_w13_workload_e2e import client, src  # noqa: F401  (the e2e engine's fixture)

from fabric_backend import workload_api as W


def _checked(post, gs, schema):
    r = post("/review", src(gs, schema))
    assert r.status_code == 200, r.text
    c = post("/check", {**src(gs, schema), "review": r.json()["review"]})
    assert c.status_code == 200, c.text
    return r.json()["review"], c.json()["review"]


@pytest.fixture()
def sap(client):  # noqa: F811
    tc, post, gs = client
    tc.post("/e2e/scenario", json={"name": "sap"})
    reviewed, checked = _checked(post, gs, "sap_sd")
    return tc, post, gs, reviewed, checked


def test_nothing_is_ranked_before_the_check(sap):
    tc, post, gs, reviewed, _ = sap
    before = len(tc.get("/e2e/log").json()["fabric_calls"])
    out = post("/analysis", {**src(gs, "sap_sd"), "review": reviewed}).json()
    assert out["recommendations"] == [] and out["waiting"].startswith("Check against the rows first")
    assert len(tc.get("/e2e/log").json()["fabric_calls"]) == before          # not even a read of Fabric


def test_the_sap_sample_ranks_a7_and_a3_ready_with_their_notebooks(sap):
    tc, post, gs, _, checked = sap
    r = post("/analysis", {**src(gs, "sap_sd"), "review": checked})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["applies"] is True and out["rule_version"] == "ap-o2c-1"
    by = {e["analysis"]: e for e in out["recommendations"]}
    assert [e["analysis"] for e in out["recommendations"]][:4] == ["A7", "A8", "A3", "A4"]   # AP2's worked example
    assert by["A7"]["readiness"] == "ready" and by["A3"]["readiness"] == "ready" and by["A8"]["readiness"] == "partial"
    assert by["A7"]["because"].startswith("Recommended because: ")
    for a in ("A7", "A3"):
        nb = by[a]["notebook"]
        assert nb["filename"].endswith(".ipynb") and nb["name"].startswith("krusgraph_a")
        doc = json.loads(nb["ipynb"])
        assert doc["nbformat"] == 4 and len(doc["cells"]) == nb["cells"] == 8
        assert "sap_sd" in nb["code"] and "krusgraph.analysis" in nb["code"]
    assert "notebook" not in by["A8"]                                        # partial: no notebook offered
    assert all("notebook" not in e for e in out["recommendations"] if e["analysis"] not in ("A7", "A3"))
    missing = [e for e in out["recommendations"] if e["readiness"] == "missing"]
    assert missing and all(e["missing"] and e["because"].startswith("Not recommended yet because: ") for e in missing)
    assert out["land_next"] and out["note"].startswith(W.NOTHING_CHANGED) and "no AI" in out["note"]
    assert tc.get("/e2e/log").json()["created"] == []                        # nothing created


def test_the_answer_reads_only(sap):
    tc, post, gs, _, checked = sap
    import sys
    mod = sys.modules["pyodbc"]
    mod.ddl.clear()
    before = len(tc.get("/e2e/log").json()["fabric_calls"])
    post("/analysis", {**src(gs, "sap_sd"), "review": checked})
    assert mod.ddl == [] and tc.get("/e2e/log").json()["created"] == []
    calls = tc.get("/e2e/log").json()["fabric_calls"][before:]
    assert calls and all(c.startswith("get ") for c in calls)               # Fabric only read


def test_a_rejected_link_is_left_out_of_the_plan(sap):
    tc, post, gs, _, checked = sap
    rid = "rel:VBRP.MANDT+MATNR>MARA"                                         # the billing item's material link
    rejected = {**checked, "items": [{**i, "review": "rejected"} if i["id"] == rid else i for i in checked["items"]]}
    by = {e["analysis"]: e for e in post("/analysis", {**src(gs, "sap_sd"), "review": rejected}).json()["recommendations"]}
    assert by["A3"]["readiness"] == "missing" and "notebook" not in by["A3"]  # ABC/XYZ needs the material link
    assert by["A7"]["readiness"] == "ready" and "notebook" in by["A7"]


def test_the_shop_schema_has_nothing_sap_to_rank(client):  # noqa: F811
    tc, post, gs = client
    _, checked = _checked(post, gs, "shop")
    out = post("/analysis", {**src(gs, "shop"), "review": checked}).json()
    assert out["applies"] is False and out["recommendations"] == [] and "No SAP order-to-cash tables" in out["words"]


def test_bad_input_is_refused(client):  # noqa: F811
    tc, post, gs = client
    assert post("/analysis", src(gs)).status_code == 400                     # no review
    assert post("/analysis", {**src(gs), "review": []}).status_code == 400


def test_the_route_is_never_a_write_for_billing():
    from fabric_backend import billing
    assert billing.route_writes("analysis", {"dry_run": False}) is False


def test_proven_follows_the_editors_rule():
    passed = {"type": "key", "review": "open", "check": {"status": "passed"}}
    assert W.analysis_proven({"items": [passed]})
    assert not W.analysis_proven({"items": [{**passed, "review": "rejected"}]})
    assert not W.analysis_proven({"items": [{**passed, "check": {"status": "failed"}}]})
    assert not W.analysis_proven({"items": []})
