"""Round AP3: the caretaker at /app clicked through in Chromium (tests/ap3_app_browser.js), at a desktop width and at
390 px, light and dark. The hosted app (server.build_app in Entra mode) runs on localhost with a test Entra app, the
synthetic SAP demo behind the doubles of tests/wb15_fake.py and an in-memory Fabric (tests/ap3_support.py).

Before the browser opens /app, the in-memory Fabric holds a data product: AP2's path is run once through the API (the one
decision, a dry run into the build workspace, Create), and a Krusgraph Model item records what was built in its
outputs.json, as the Fabric workload does. Its last pipeline run failed, the health check is red on a link, and the
source has a column the plan did not have.

Clicked: the "Since last time" report (four sections, each naming its source; three proposals), Re-check the links
(reads only), Run the pipeline once (its preview, the modal confirm naming the pipeline, Yes: one run started), and
Update the build in place (AP2's dry run on the product, each item "Update in place"). Checked too: nothing scrolls
sideways at 390 px, every button is at least 44 px high, no token or tenant id in the page, one run started and nothing
else written or deleted.

Screenshots: set AP3_SHOTS to a folder to keep them (five per run: report, re-check, confirm, run, update dry run)."""
from __future__ import annotations

import copy
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("jwt")
pytest.importorskip("uvicorn")
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import ap1_support as s  # noqa: E402
import ap2_support as s2  # noqa: E402
import ap3_support as s3  # noqa: E402
from fabric_backend import access, flow_state, guided_app, guided_build, guided_care, operations  # noqa: E402

TESTS = Path(__file__).parent
CH = {"workspace": "demo", "source": "demo_lh", "schema": "dbo"}
ITEM = "rel:sap_vbap.MANDT+VBELN>sap_vbak"


def _browser_ready() -> bool:
    if not shutil.which("node"):
        return False
    r = subprocess.run(["node", "-e", "require('playwright').chromium.launch().then(b => b.close())"],
                       capture_output=True, cwd=TESTS.parent, timeout=60)
    return r.returncode == 0


def _post(c, route: str, body: dict) -> dict:
    return c.post(route, content=json.dumps(body), headers={"Origin": s.ORIGIN, "Content-Type": "application/json"}).json()


def built_product(app, fake, token, fabric, mp) -> dict:
    """AP2's path once through the API, then a Krusgraph Model item that records it; a failed run, a red link, drift."""
    def redeemed(url, data):
        fake.codes[data.get("code")] = token
        return s.FakeEntra.post(fake, url, data)
    c = TestClient(app, base_url=s.ORIGIN, follow_redirects=False)                # no lifespan: uvicorn runs this app
    mp.setattr(guided_app.App, "_entra_post", lambda self, data: redeemed(None, data))
    s.sign_in(c, fake, token, code="setup")
    c.post(guided_app.STEP, content=json.dumps({**CH, "step": "decide", "decide": {"item": ITEM, "review": "accepted"}}),
           headers={"Origin": s.ORIGIN, "Content-Type": "application/json"})
    v = _post(c, guided_app.BUILD, {"action": "dry_run", **CH, "target": {"workspace": s2.BUILD_WS, "lakehouse": "build_lh"}})
    got = _post(c, guided_app.BUILD, {"action": "confirm", "token": v["token"], "names": [x["name"] for x in v["creates"]]})
    for it in got["items"]:
        op = _post(c, guided_app.BUILD, {"action": "create", "run": got["run"], "kind": it["kind"]})
        for _ in range(200):
            if _post(c, guided_app.BUILD, {"action": "state", "operation_id": op["operation_id"]}).get("status") == "done":
                break
            time.sleep(0.05)
    st = guided_build.BUILDS.get(guided_app._digest(c.cookies.get(guided_app.SESSION_COOKIE)))
    created = [dict(x, workspace=x.get("workspace") or s2.BUILD_WS) for x in st["created"]]
    rv = copy.deepcopy(st["run"]["rv"])
    rv["snapshot"]["tables"]["sap_vbak"]["columns"]["LEGACY_FLAG"] = "varchar"     # the plan had a column the source lost
    fabric.add_model(s2.BUILD_WS, "sales_model", {"created": created, "product": {"name": "Sales orders"}},
                     {"version": 1, "platform": "fabric", "workspaceId": s2.SOURCE_WS, "itemId": "lh-1", "itemType": "Lakehouse",
                      "displayName": "demo_lh", "schema": "dbo",
                      "target": {"itemId": s2.BUILD_LH, "displayName": "build_lh", "workspaceId": s2.BUILD_WS}}, rv)
    pipe = fabric.item("demo_lh_pipeline")
    fabric.jobs[pipe["id"]] = [s3.run("Failed", "2026-11-25T06:00:00", "2026-11-25T06:01:05", "Activity failed")]
    fabric.jobs[fabric.item("demo_lh_silver")["id"]] = [
        s3.run("Failed", "2026-11-25T06:00:10", "2026-11-25T06:01:00", "Capacity level limit exceeded for the workspace")]
    s3.health_rows(mp, [s3.health_row(rv["plan_id"], "orphans", "silver.sap_vbap", "fail", 1)])
    guided_build.BUILDS.clear()
    fabric.calls.clear()
    return {"pipeline": pipe["id"], "made": len(fabric.created())}


@pytest.fixture(scope="module")
def served():
    if not _browser_ready():
        if os.environ.get("CI"):
            pytest.fail("AP3: Chromium did not start in CI")
        pytest.skip("Chromium (playwright) is not available here; CI runs this test")
    import uvicorn
    mp = pytest.MonkeyPatch()
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    app, auth, fake = s.entra_app(mp, (priv, priv.public_key()))
    mp.setenv(access.PIPELINE_EXECUTE_ENV, "1")                                     # the operator's opt-in switch, on
    box = {"fabric": s3.data(mp)}
    token = s.tok(priv)

    def redeem(url, data):
        fake.codes[data.get("code")] = token
        return s.FakeEntra.post(fake, url, data)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(200):
        if srv.started:
            break
        time.sleep(0.05)

    def fresh():
        """Each run starts from a build workspace that holds the data product, and no session's own build."""
        import requests
        import wb15_fake
        box["fabric"] = s3.Fabric(wb15_fake._get)
        for verb in ("get", "post", "patch", "put", "delete"):
            mp.setattr(requests, verb, getattr(box["fabric"], verb))
        flow_state.clear()
        guided_build.BUILDS.clear()
        guided_care.CARES.clear()
        got = built_product(app, fake, token, box["fabric"], mp)
        mp.setattr(guided_app.App, "_entra_post", lambda self, data: redeem(None, data))
        return box["fabric"], got
    try:
        yield {"origin": f"http://localhost:{port}", "token": token, "fresh": fresh}
    finally:
        srv.should_exit = True
        t.join(timeout=10)
        mp.undo()
        guided_app.SESSIONS.clear()
        operations.use_store(None)


RUNS = [("desktop", 1280, 900, "light"), ("390", 390, 844, "light"), ("390", 390, 844, "dark")]


@pytest.fixture(scope="module", params=RUNS, ids=[f"{r[0]}-{r[3]}" for r in RUNS])
def run(request, served):
    name, w, h, scheme = request.param
    fabric, got = served["fresh"]()
    shots = os.environ.get("AP3_SHOTS", "")
    prefix = ""
    if shots:
        Path(shots).mkdir(parents=True, exist_ok=True)
        prefix = str(Path(shots) / f"app3-{name}-{scheme}")
    r = subprocess.run(["node", str(TESTS / "ap3_app_browser.js"), served["origin"], str(w), str(h), scheme, prefix],
                       capture_output=True, text=True, timeout=300, cwd=TESTS.parent)
    assert r.returncode == 0, r.stderr[-4000:]
    out = json.loads(r.stdout)
    out.update(width=w, token=served["token"], fabric=fabric, **got)
    return out


def test_onto_greets_with_since_last_time_and_each_source_is_named(run):
    assert run["errors"] == []
    assert run["greeting"].startswith("Onto") and "Since last time" in run["greeting"]
    assert "Sales orders" in run["report"] and "the Krusgraph Model sales_model in build" in run["report"]
    assert [x.split(" ")[0] for x in run["sections"]] == ["Pipeline", "Health", "What", "The"]
    assert run["sources"] == ["from the last pipeline run.", "from the health check's latest run.",
                              "Checked by rules, not by AI, from verify_build.", "from the source now, compared with the plan."]
    assert "Latest run of demo_lh_pipeline: failed" in run["report"] and "Capacity level limit exceeded" in run["report"]
    assert "Latest health check: red" in run["report"] and "Column gone: sap_vbak.LEGACY_FLAG." in run["report"]


def test_three_proposals_as_buttons_and_the_journey_still_there(run):
    assert run["buttons"] == ["Run the pipeline once", "Update the build in place", "Re-check the links",
                              "Read the report again", "Start something new"]


def test_re_checking_the_links_only_counts(run):
    assert "Checked by rules, not by AI" in run["recheck"] and "hold now (counted against the rows now)" in run["recheck"]


def test_a_run_comes_after_a_preview_and_a_modal_confirm_that_names_the_pipeline(run):
    assert "Starts one run of the pipeline demo_lh_pipeline" in run["preview"] and "nothing is done until you confirm" in run["preview"]
    assert run["dialogModal"] is True and run["dialogFocus"] == "app-confirm-h"
    assert "demo_lh_pipeline" in run["dialog"] and "nothing is deleted" in run["dialog"]
    assert "demo_lh_pipeline: queued in Fabric." in run["ran"]
    assert run["fabric"].started_runs == [run["pipeline"]]                          # one run, of that pipeline


def test_update_in_place_opens_ap2s_dry_run_on_the_product(run):
    assert run["target"] == "build › build_lh"
    assert [i.split(" ")[0] for i in run["items"]] == ["demo_lh_silver", "demo_lh_gold", "demo_lh_pipeline", "demo_lh_model",
                                                       "demo_lh_report", "demo_lh_agent"]
    assert sum(i.endswith("Update in place") for i in run["items"]) == 5 and run["items"][4].endswith("Already built")
    assert run["createButton"].startswith("Create these 5 items")
    assert len(run["fabric"].created()) == run["made"]                              # nothing new was created
    assert run["fabric"].writes == [("POST", f"/v1/workspaces/{s2.BUILD_WS}/items/{run['pipeline']}/jobs/instances")]
    assert not any(m == "DELETE" for m, _ in run["fabric"].calls)


def test_it_fits_a_phone_every_button_is_big_enough_and_nothing_secret_is_in_the_page(run):
    assert all(o <= 0 for _, o in run["overflow"]), run["overflow"]
    assert run["chipMin"] >= 44
    assert run["live"] == "polite"
    assert run["token"] not in run["html"] and s.TID not in run["html"]
