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


def test_demo_graph_and_the_mobile_list(report):
    """The demo graph from the website brief of 26 October 2026, on /demo since round n17: orders.customer_id preselected
    with its explanation, ship_to_id as the decision by mouse and keyboard, the list as the graph's alternative at 375,
    768 and 1440."""
    f = report["facts"]
    for v in ("1440-light", "1440-dark", "768-light", "375-light"):
        assert f[f"demoList@{v}"] == f["edgeCount"], v                 # every relationship is in the list at every width
        assert f[f"homeCtas@{v}"][:2] == ["/demo", "/start"], v
    assert f["homeDefault"] == "orders.customer_id>customers"
    for part in ("Suggestion", "Why", "Data check", "Your review", "Technical details"):
        assert part in f["homePanelDefault"], part
    assert f["homeDetailsClosed"] is True
    assert "All 60 orders in this sample" in f["homeDecisionPanel"] and f["homeUrlAfterListClick"] == "/demo"
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



def test_the_guided_example_steps_decides_resets_and_agrees_with_the_graph(report):
    """Home page round 1, on /demo since round n17: one step at a time with the script, Next and Back by keyboard, the decision in step 3 drawn on
    the graph's line too, the result card for that decision, and Start over returning to step 1 with nothing accepted;
    at 375 px the guide fits the screen."""
    f = report["facts"]
    assert f["guideVisiblePanes"] == ["1"] and f["guideStatus"].startswith("Step 1 of 4")
    assert f["guideAfterNext"] == ["2"] and f["guideAfterKeyboardNext"] == ["3"] and f["guideAfterBack"] == ["2"]
    assert f["guideAcceptPressed"] == "true" and "accepted" in f["guideEdgeClass"]
    assert f["guideCardShown"] == "accepted" and "You accepted, in this demo" in f["guideCardText"]
    assert f["guideAfterReset"] == ["1"] and "accepted" not in f["guideEdgeAfterReset"] and f["guideCardAfterReset"] == "open"
    assert f["guideFromGraph"] == "accepted"                                  # accepting on the graph's panel shows the same card
    assert f["guideOverflow375"] == [] and f["guideStepTargets375"] >= 44
    assert f["guidePreviewFits375"] == [True]                               # the delivery-address column is visible without scrolling


def test_home_entry_old_anchors_and_the_hub_under_the_hero(report):
    """Round n17: the start page's way in to the guided demo takes at most half the screen of a small phone (375 x 667)
    and of a laptop (1280 x 800); /#guide, /#demo and a step's anchor open the same anchor on /demo. The hub (brief of
    27 October 2026) keeps its three cards and the product on the screen, none on top of another and no name cut off,
    with its text version for screen readers: side by side with the lines at 1280 and 1440 px, stacked with the product
    in the middle at 768 and 375 px. (This server runs without client registration: Claude and Lovable on the right.)"""
    f = report["facts"]
    assert f["homeEntry@375x667"] <= 0.5 and f["homeEntry@1280x800"] <= 0.5
    for h in ("#guide", "#demo", "#guide-h3"):
        assert f[f"oldAnchor{h}"] == "/demo" + h, h
    for v in ("1440-light", "1440-dark", "1280-light", "768-light", "375-light"):
        c = f[f"hub@{v}"]
        assert c["cards"] == 4 and c["items"] == 11 and c["outside"] == 0 and c["overlaps"] == 0 and c["cut"] == 0, (v, c)
        assert c["srText"] > 300, v
        wide = v.startswith(("1440", "1280"))
        assert c["sideBySide"] is wide and c["stacked"] is not wide and c["lines"] == (2 if wide else 0), (v, c)


def test_explore_build_cards_fit_at_375_and_1280_and_hold_still_with_reduced_motion(report):
    f = report["facts"]
    for v in ("375-light", "1280-light"):
        b = f[f"build@{v}"]
        assert b["cards"] == 4 and b["outside"] == 0 and b["scrollWidth"] <= int(v.split("-")[0]), (v, b)
    assert f["buildMotion"] == 0
