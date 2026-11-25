"""Round AP2b: the founder's live test of /app (25 November 2026) clicked through in Chromium at 390 px, dark and light
(tests/ap2b_app_browser.js, the invented tenant of tests/ap2b_support.py behind the doubles of tests/ap1_support.py).

Checked: one greeting; the header says nothing is written until a Create is confirmed; the build target's schema list
puts dbo first (suggested) and labels gold, krusgraph and silver as Krusgraph's own, with no combined chip; "Shop" typed
there says it is a schema in demo › demo_lh and its chip goes there; the check's tiles, its sentence and the map count
the same 18 tables, and the first line names the one without a key; the closing line says nothing was written in this
session; nothing scrolls sideways and every button is at least 44 px high.

Screenshots: set AP2B_SHOTS to a folder to keep them."""
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
import ap2b_support as b  # noqa: E402
from fabric_backend import guided_app  # noqa: E402

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
            pytest.fail("AP2b: Chromium did not start in CI")
        pytest.skip("Chromium (playwright) is not available here; CI runs this test")
    import uvicorn
    mp = pytest.MonkeyPatch()
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    app, auth, fake = s.entra_app(mp, (priv, priv.public_key()))
    s.data(mp)
    b.install(mp)
    token = s.tok(priv)

    def redeem(url, data):                           # every sign-in of the browser runs gets the same test token
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
    try:
        yield {"origin": f"http://localhost:{port}", "token": token}
    finally:
        srv.should_exit = True
        t.join(timeout=10)
        mp.undo()
        guided_app.SESSIONS.clear()


RUNS = [(390, 844, "dark"), (390, 844, "light")]


@pytest.fixture(scope="module", params=RUNS, ids=[f"{r[0]}-{r[2]}" for r in RUNS])
def run(request, served):
    w, h, scheme = request.param
    shots = os.environ.get("AP2B_SHOTS", "")
    if shots:
        Path(shots).mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["node", str(TESTS / "ap2b_app_browser.js"), served["origin"], str(w), str(h), scheme, shots],
                       capture_output=True, text=True, timeout=180, cwd=TESTS.parent)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout)


def test_one_greeting_and_a_true_header(run):
    assert run["errors"] == []
    assert run["greetings"] == 1
    assert guided_app.HEADER in run["header"] and "only reads" not in run["header"]


def test_the_build_targets_schemas_put_the_source_first(run):
    assert run["schemaChips"] == ["dbo 17 tables, suggested [suggested]", "gold 7 tables, looks like Krusgraph output",
                                  "krusgraph 3 tables, written by Krusgraph", "silver 17 tables, looks like Krusgraph output"]
    assert "gold, krusgraph, silver" in run["ownLine"]


def test_a_name_from_another_workspace_is_found_with_a_way_there(run):
    assert "“shop” is a schema in demo › demo_lh" in run["match"]
    assert run["goChip"] == "Go to demo › demo_lh › shop"


def test_the_check_counts_the_same_tables_everywhere(run):
    assert run["kpis"][0].split() == ["18", "tables", "read"]
    assert run["mapSummary"] == "The map: 18 tables, 24 links"
    assert run["firstLine"].startswith("17 of the 18 tables have a key") and "sap_notes" in run["firstLine"]
    assert guided_app.NOTHING_WRITTEN in run["closing"]


def test_it_fits_a_phone(run):
    assert run["overflow"] <= 0
    assert run["chipMin"] >= 44
