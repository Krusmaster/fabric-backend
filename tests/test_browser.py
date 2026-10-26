"""Browser-level checks of the site (console errors, external requests, overflow, fonts, the explorer's
interactions, the mascot toggle, the builder sequence). Runs only where Node, Playwright and a Chromium are
available — on a developer machine with `npm i -g playwright` + `npx playwright install chromium`, or where
PLAYWRIGHT_CHROMIUM points at a browser. Skipped otherwise, so CI stays green without a browser."""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHROMIUM = os.environ.get("PLAYWRIGHT_CHROMIUM") or ("/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else "")


def _playwright_available() -> bool:
    if not shutil.which("node"):
        return False
    probe = subprocess.run(["node", "-e", "require('playwright')"], capture_output=True, text=True)
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(not _playwright_available(), reason="node + playwright not available")


@pytest.fixture(scope="module")
def site():
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    env = os.environ | {"PRODUCT_NAME": "Krusgraph", "MCP_PUBLIC_URL": "https://krusgraph.test/mcp", "CONTACT_EMAIL": "hello@krusgraph.test",
                        "ENTRA_CLIENT_ID": "00000000-0000-0000-0000-000000000000", "ENTRA_CLIENT_SECRET": "test-only", "COMPANY_ORGNR": "123456-7890",
                        "KRUSGRAPH_PREVIEW": "1"}
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
def report(site):
    cmd = ["node", str(ROOT / "tests" / "browser_check.js"), site] + ([CHROMIUM] if CHROMIUM else [])
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_no_console_errors_external_requests_or_overflow(report):
    assert report["errors"] == []


def test_explorer_interactions(report):
    f = report["facts"]
    assert f["nodeCount"] == 7 and f["edgeCount"] == 7                      # 6 relationships + 1 column to review
    assert f["deepLinkSelected"] == "orders"
    assert "R1" in f["whyText"] and "column named" in f["whyText"]
    assert f["hashAfterEdge"] == "#edge=orders.customer_id%3Ecustomers"
    assert "accepted" in f["acceptedClass"] and "accepted" not in f["afterResetClass"]
    assert f["fieldsShown"] == "block"
    assert f["firstGraphFocus"] != "svg"                                      # tables come before wires in tab order


def test_mascot_toggle_and_builder(report):
    f = report["facts"]
    assert f["mascotsAfterReload"] == "off" and f["mascotsAfterToggleBack"] == "on"
    assert f["builderPoses"][:2] == ["working", "failure"] and "celebrate" not in f["builderPoses"]
    assert f["builderErrorShown"] is True
    assert f["motionClassUnderReducedMotion"] is False


def test_home_demo_and_the_mobile_list(report):
    """The home demo from the website brief of 26 October 2026: orders.customer_id preselected with its explanation,
    ship_to_id as the decision by mouse and keyboard, the list as the graph's alternative at 375, 768 and 1440."""
    f = report["facts"]
    for v in ("1440-light", "1440-dark", "768-light", "375-light"):
        assert f[f"homeList@{v}"] == f["edgeCount"], v                 # every relationship is in the list at every width
        assert f[f"homeCtas@{v}"][:2] == ["/explore", "/start"], v
    assert f["homeDefault"] == "orders.customer_id>customers"
    for part in ("Suggestion", "Why", "Data check", "Your review", "Technical details"):
        assert part in f["homePanelDefault"], part
    assert f["homeDetailsClosed"] is True
    assert "Not checked" in f["homeDecisionPanel"] and f["homeUrlAfterListClick"] == "/"
    assert "Accepted in this demo" in f["homeAfterAccept"] and f["homeFocusAfterAccept"] == "accept"
    assert "accepted" in f["homeEdgeAccepted"]
    assert "Accepted in this demo" in f["homeAfterKeyboard"]
    assert f["homeKeyboardSelected"] == "order_items.order_id>orders"
    assert f["homeMotionClass"] is False                                      # reduced motion: no animation class
    assert f["ctaFocusOutline"] not in ("none", "")


def test_use_cases_tasks_first_and_details_by_keyboard(report):
    f = report["facts"]
    assert f["useCaseTasks"] == 3
    assert f["useCaseDetailsClosed"] is True and f["useCaseDetailsOpened"] is True


def test_sales_example_journey_at_phone_width(report):
    """The first customer demonstration (brief of 26 October 2026): the steps open in order, another question gets an
    honest answer, the decision changes the numbers exactly as the server computes them, the chart reads by keyboard,
    nothing but a table scrolls sideways, and a saved link reopens the same result."""
    f = report["facts"]
    assert f["salesScopeHiddenFirst"] is True and f["salesScopeHiddenAfterOther"] is True and f["salesScopeShown"] is True
    assert "answers one question" in f["salesOtherQuestion"] and "pilot" in f["salesOtherQuestion"]
    assert f["salesFocusAfterDefinition"] == "link-h"
    assert f["salesOpenTotal"] == f["salesApiOpenTotal"] and f["salesLinkedTotal"] == f["salesApiLinkedTotal"]
    assert f["salesLinkedTotal"] > f["salesOpenTotal"] and "d=B-7003%3AA-103" in f["salesUrlAfterLink"]
    assert f["salesFilteredTotal"] == f["salesApiFilteredTotal"]
    assert "forecast for week 51, 2026" in f["salesKeyboardEnd"] and "sold in week" in f["salesKeyboardHome"]
    assert f["salesWideOutsideScroll"] == []
    assert "Reopened" in f["salesReopened"] and f["salesReopenedTotal"] == f["salesFilteredTotal"]
    assert "linked to Commuter Light Set" in f["salesSavedList"] and f["salesChoiceKept"] is True
