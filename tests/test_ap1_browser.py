"""Round AP1: the guided chat at /app clicked through in Chromium (tests/ap1_app_browser.js), at a desktop width and at
390 px, light and dark. The hosted app (server.build_app in Entra mode) runs on localhost with a test Entra app and the
synthetic SAP demo behind the doubles of tests/wb15_fake.py; the browser's request to Microsoft Entra is answered with
Entra's redirect back to /app/callback, so the sign-in takes its real path (state, flow cookie, PKCE, session cookie).

Checked: the browser ends on /app with only the session cookie (HttpOnly, Secure, SameSite=Lax), the log is aria-live,
a workspace is chosen by a tap or by its typed name, Next: Check works from the keyboard (the focus is on it after the
choice), the check's counts are drawn as the site's check tiles, the last bubble is the Builder's "coming next", nothing
scrolls sideways at 390 px, every button is at least 44 px high, and no token or tenant id is in the page.

Screenshots: set AP1_SHOTS to a folder to keep them (desktop and 390 px, light and dark)."""
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
            pytest.fail("AP1: Chromium did not start in CI")
        pytest.skip("Chromium (playwright) is not available here; CI runs this test")
    import uvicorn
    mp = pytest.MonkeyPatch()
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    app, auth, fake = s.entra_app(mp, (priv, priv.public_key()))
    s.data(mp)
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


RUNS = [("desktop", 1280, 900, "light", "0"), ("390", 390, 844, "light", "1"), ("390", 390, 844, "dark", "0")]


@pytest.fixture(scope="module", params=RUNS, ids=[f"{r[0]}-{r[3]}" for r in RUNS])
def run(request, served):
    name, w, h, scheme, typed = request.param
    shots = os.environ.get("AP1_SHOTS", "")
    shot = ""
    if shots:
        Path(shots).mkdir(parents=True, exist_ok=True)
        shot = str(Path(shots) / f"app-{name}-{scheme}.png")
    r = subprocess.run(["node", str(TESTS / "ap1_app_browser.js"), served["origin"], str(w), str(h), scheme, typed, shot],
                       capture_output=True, text=True, timeout=180, cwd=TESTS.parent)
    assert r.returncode == 0, r.stderr[-3000:]
    out = json.loads(r.stdout)
    out["width"], out["token"] = w, served["token"]
    return out


def test_the_browser_signs_in_and_holds_only_the_session_cookie(run):
    assert run["errors"] == []
    assert run["url"] == "/app"
    names = {c["name"]: c for c in run["cookies"]}
    assert set(names) == {guided_app.SESSION_COOKIE}
    c = names[guided_app.SESSION_COOKIE]
    assert c["httpOnly"] and c["secure"] and c["sameSite"] == "Lax"
    assert run["token"] not in run["html"] and s.TID not in run["html"]


def test_the_journey_reads_and_stops_before_deciding(run):
    assert run["live"] == "polite"
    assert run["focusOnNext"].startswith("Next: Check")                    # the keyboard lands on the next step
    said = run["said"]
    assert said.count("Hi!") == 1 and "Hi! Which workspace" in said         # AP2b: one greeting, the start tool's own
    assert "demo › demo_lh › dbo ✓" in said
    assert "17 tables, 24 links, 1 needs you." in said
    assert any("40 of 41" in k for k in run["kpis"])
    assert guided_app.NEXT_LINE in run["next"]
    whos = [b.split(":")[0] for b in run["bubbles"]]
    assert whos[-1].startswith("app-msg builder") and any(w.startswith("app-msg thinker") for w in whos)
    assert any(w == "app-you" for w in whos)                               # the person's own choice is a bubble


def test_it_fits_a_phone_and_every_button_is_big_enough(run):
    assert run["overflow"] <= 0, run["width"]
    assert run["chipMin"] >= 44
