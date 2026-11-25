"""Round AP2: the whole guided path at /app clicked through in Chromium (tests/ap2_app_browser.js), at a desktop width
and at 390 px, light and dark. The hosted app (server.build_app in Entra mode) runs on localhost with a test Entra app,
the synthetic SAP demo behind the doubles of tests/wb15_fake.py and an in-memory Fabric (tests/ap2_support.py) that
takes the writes of Create. The sign-in takes its real path, as in tests/test_ap1_browser.py.

Clicked: the workspace, Next: Check, Next: Decide, Accept with quarantine on the one open decision (shown as "Decided by
you"), Next: Dry run, Change where to build -> the build workspace -> build_lh, Show definition, Create ... -> the confirm
dialog (modal, focus on its heading, every item by name), Yes -> each item created with its Fabric link, then
verify_build's card, "Checked by rules, not by AI". Checked too: nothing scrolls sideways at 390 px, every button is at
least 44 px high, no token or tenant id in the page, and only the dry run's items were written, nothing deleted.

Screenshots: set AP2_SHOTS to a folder to keep them (four per run: decide, dry run, confirm, created and verified)."""
from __future__ import annotations

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

import ap1_support as s  # noqa: E402
import ap2_support as s2  # noqa: E402
from fabric_backend import flow_state, guided_app, guided_build, operations  # noqa: E402

TESTS = Path(__file__).parent


def _browser_ready() -> bool:
    if not shutil.which("node"):
        return False
    r = subprocess.run(["node", "-e", "require('playwright').chromium.launch().then(b => b.close())"],
                       capture_output=True, cwd=TESTS.parent, timeout=60)
    return r.returncode == 0


@pytest.fixture(scope="module")
def served():
    if not _browser_ready():
        if os.environ.get("CI"):
            pytest.fail("AP2: Chromium did not start in CI")
        pytest.skip("Chromium (playwright) is not available here; CI runs this test")
    import uvicorn
    mp = pytest.MonkeyPatch()
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    app, auth, fake = s.entra_app(mp, (priv, priv.public_key()))
    box = {"fabric": s2.data(mp)}
    token = s.tok(priv)

    def redeem(url, data):
        fake.codes[data.get("code")] = token
        return s.FakeEntra.post(fake, url, data)
    mp.setattr(guided_app.App, "_entra_post", lambda self, data: redeem(None, data))
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
        """Each run starts from an empty build workspace and an undecided path."""
        import requests
        box["fabric"] = s2.Workspaces(box["fabric"].lakehouse_get)
        for verb in ("get", "post", "patch", "put", "delete"):
            mp.setattr(requests, verb, getattr(box["fabric"], verb))
        flow_state.clear()
        guided_build.BUILDS.clear()
        return box["fabric"]
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
    fabric = served["fresh"]()
    shots = os.environ.get("AP2_SHOTS", "")
    prefix = ""
    if shots:
        Path(shots).mkdir(parents=True, exist_ok=True)
        prefix = str(Path(shots) / f"app2-{name}-{scheme}")
    r = subprocess.run(["node", str(TESTS / "ap2_app_browser.js"), served["origin"], str(w), str(h), scheme, prefix],
                       capture_output=True, text=True, timeout=300, cwd=TESTS.parent)
    assert r.returncode == 0, r.stderr[-4000:]
    out = json.loads(r.stdout)
    out["width"], out["token"], out["fabric"] = w, served["token"], fabric
    return out


NAMES = ["demo_lh_silver", "demo_lh_gold", "demo_lh_pipeline", "demo_lh_model", "demo_lh_report", "demo_lh_agent"]


def test_decide_shows_the_rule_the_counts_and_records_the_choice(run):
    assert run["errors"] == []
    assert run["focusAfterCheck"].startswith("Next: Decide")
    d = run["decision"]
    assert "sap_vbap.MANDT+VBELN → sap_vbak" in d and "SAP pack" in d
    assert "5 of 6 rows join; 1 goes to quarantine" in d and "Leaves the link out" in d
    assert run["focusOnOption"].startswith("Accept with quarantine")              # the keyboard lands on the choice
    assert run["decided"] == "Decided by you: Accepted"


def test_the_dry_run_names_the_target_marks_each_item_and_shows_its_definition(run):
    assert run["firstTarget"] == "demo › demo_lh"                                  # the source's workspace by default
    assert run["target"] == "build › build_lh"                                     # the build workspace, as chosen
    assert [i.split(" ")[0] for i in run["items"]] == NAMES
    assert all(i.endswith("New") for i in run["items"])
    assert "sap_vbap.MANDT+VBELN → sap_vbak: accepted" in run["decidedInDry"]
    assert "definition/" in run["definition"]                                    # the semantic model's TMDL parts


def test_create_comes_after_a_modal_confirm_that_names_each_item(run):
    assert run["dialogModal"] is True and run["dialogFocus"] == "app-confirm-h"
    assert all(n in run["dialog"] for n in NAMES) and "build › build_lh" in run["dialog"] and "deletes nothing" in run["dialog"]
    assert [c.split(" ")[0] for c in run["created"]] == NAMES and all(c.endswith("New") for c in run["created"])
    assert run["links"] and all(x.startswith(f"https://app.fabric.microsoft.com/groups/{s2.BUILD_WS}/") for x in run["links"])
    made = sorted({it["displayName"] for it in run["fabric"].created()})
    assert made == sorted(NAMES + ["demo_lh_pipeline_check"])                    # the pipeline's own check notebook
    assert all(it["workspace"] == s2.BUILD_WS for it in run["fabric"].created())
    assert not any(m == "DELETE" for m, _ in run["fabric"].calls)


def test_verify_says_it_was_checked_by_rules(run):
    v = run["verify"]
    assert "Checked by rules, not by AI" in v and "Next steps" in v and "Run the pipeline once" in v


def test_it_fits_a_phone_every_button_is_big_enough_and_nothing_secret_is_in_the_page(run):
    assert all(o <= 0 for _, o in run["overflow"]), run["overflow"]
    assert run["chipMin"] >= 44
    assert run["live"] == "polite"
    assert run["token"] not in run["html"] and s.TID not in run["html"]
