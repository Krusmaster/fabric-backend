"""n240: /check on a phone in a real browser (tests/browser_n240_mobile.js) at 375 x 812 and 390 x 844, and the
campaign counts the visit leaves on the server (/admin/campaigns). Skipped where Node and Playwright are missing, as
tests/test_browser.py is."""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from tests.test_browser import CHROMIUM, _playwright_available

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "n240-browser-token-" + "y" * 24
pytestmark = pytest.mark.skipif(not _playwright_available(), reason="node + playwright not available")


@pytest.fixture(scope="module")
def site():
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    env = os.environ | {"PRODUCT_NAME": "Krusgraph", "MCP_PUBLIC_URL": "https://krusgraph.test/mcp", "CONTACT_EMAIL": "hello@krusgraph.test",
                        "ENTRA_CLIENT_ID": "00000000-0000-0000-0000-000000000000", "ENTRA_CLIENT_SECRET": "test-only", "COMPANY_ORGNR": "123456-7890",
                        "KRUSGRAPH_PREVIEW": "1", "KRUSGRAPH_METRICS_TOKEN": TOKEN}
    proc = subprocess.Popen([sys.executable, "-m", "fabric_backend.server", "--host", "127.0.0.1", "--port", str(port)], env=env,
                            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/healthz", timeout=1); break
            except Exception:
                time.sleep(0.25)
        else:
            pytest.fail("server did not start")
        yield base
    finally:
        proc.terminate(); proc.wait(timeout=10)


@pytest.fixture(scope="module")
def phone(site):
    cmd = ["node", str(ROOT / "tests" / "browser_n240_mobile.js"), site] + ([CHROMIUM] if CHROMIUM else [])
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


SIZES = ("375x812", "390x844")


def test_no_errors_and_no_sideways_scroll(phone):
    assert phone["errors"] == []
    for v in SIZES:
        s = phone["sizes"][v]
        assert s["scrollWidth"] <= s["width"] and s["scrollWidthAfter"] <= s["width"], v


def test_the_sample_button_is_on_the_first_screen_and_easy_to_tap(phone):
    for v in SIZES:
        s = phone["sizes"][v]
        b = s["tryBtn"]
        assert s["tryText"] == "Try it on SAP-shaped sample data", v
        assert 0 <= b["top"] and b["bottom"] <= s["height"] and b["height"] >= 44 and b["width"] >= 280, (v, b)
        assert s["dropTop"] < s["height"], v                       # n149: the drop area still starts on the first screen
        assert s["small"] == [], (v, s["small"])                    # every stand-alone tap target is 44 px or more
        assert s["textarea"] >= 16, v                               # no zoom when the text box gets focus


def test_one_tap_shows_the_engines_figures_on_the_sap_shaped_sample(phone):
    for v in SIZES:
        s = phone["sizes"][v]
        t = [" ".join(x.split()) for x in s["tiles"]]
        assert t[0].startswith("17 of 17") and "keys unique" in t[0], (v, t)
        assert t[1].startswith("1 of 6 rows (16.7%)") and "point at nothing" in t[1], (v, t)
        assert t[2].startswith("1 950 vs 750") and "2.6x" in t[2], (v, t)
        assert 0 <= s["headlineTop"] < s["height"], v               # the figures are what the run scrolls to
        assert s["cls"] < 0.1, (v, s["cls"])


def test_the_events_carry_the_campaign_and_the_server_counts_it(phone, site):
    for v in SIZES:
        ev = phone["sizes"][v]["events"]
        tags = "utm_source=tiktok&utm_medium=paid&utm_campaign=fabric_see_this_test1"
        assert "/check/event?e=loaded&" + tags in ev and "/check/event?e=done&k=sample&n=1&" + tags in ev, (v, ev)
    req = urllib.request.Request(site + "/admin/campaigns", headers={"Authorization": "Bearer " + TOKEN})
    rep = json.loads(urllib.request.urlopen(req, timeout=5).read())
    row = next(r for r in rep["days"][0]["campaigns"] if r["utm_source"] == "tiktok")
    assert (row["utm_medium"], row["utm_campaign"]) == ("paid", "fabric_see_this_test1")
    assert row["visits"] >= 2 and row["checks_sample"] >= 2 and row["visits_with_check"] >= 2 and row["checks_real"] == 0
