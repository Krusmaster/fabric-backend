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

from fabric_backend import pages

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


def test_mascot_toggle_and_builder(report):
    f = report["facts"]
    assert f["mascotsAfterReload"] == "off" and f["mascotsAfterToggleBack"] == "on"
    assert f["builderPoses"][:2] == ["working", "failure"] and "celebrate" not in f["builderPoses"]
    assert f["builderErrorShown"] is True
    assert f["motionClassUnderReducedMotion"] is False


def test_the_theme_button_switches_and_the_choice_survives_a_reload(report):
    f = report["facts"]
    assert f["themeFirst"]["theme"] is None and f["themeFirst"]["pressed"] == "false"          # the system's choice (light)
    assert f["themeAfterClick"]["theme"] == "dark" and f["themeAfterClick"]["pressed"] == "true"
    assert f["themeAfterClick"]["bg"] != f["themeFirst"]["bg"] and f["themeAfterClick"]["meta"] == "#1F1B19"
    assert f["themeAfterReload"] == f["themeAfterClick"]
    assert f["themeAfterEnter"]["theme"] == "light" and f["themeAfterEnter"]["bg"] == f["themeFirst"]["bg"]


def test_the_home_buttons_and_a_visible_focus_ring(report):
    f = report["facts"]
    for v in ("1440-light", "1440-dark", "768-light", "375-light"):
        assert f[f"homeCtas@{v}"][:2] == ["/check", "/start"], v
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



def test_home_entry_old_anchors_and_the_hub_under_the_hero(report):
    """Round n17: the start page's way in to the guided demo takes at most half the screen of a small phone (375 x 667)
    and of a laptop (1280 x 800); /#guide, /#demo and a step's anchor open the guided demo on /check (n55). The hub (brief of
    27 October 2026) keeps its three cards and the product on the screen, none on top of another and no name cut off,
    with its text version for screen readers: side by side with the lines at 1280 and 1440 px, stacked with the product
    in the middle at 768 and 375 px. (This server runs without client registration: Claude and Lovable on the right.)"""
    f = report["facts"]
    assert f["homeEntry@375x667"] <= 0.5 and f["homeEntry@1280x800"] <= 0.5
    for h in ("#guide", "#demo", "#guide-h3"):
        assert f[f"oldAnchor{h}"] == "/check?example=sample&guide=1", h          # n55: the guided demo is on /check
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
        assert b["steps"] == len(pages.build_path()) and b["stepsOutside"] == 0, (v, b)     # the row of steps (n34)
    assert f["build@1280-light"]["stepsInRow"] == 1 and f["build@375-light"]["stepsInRow"] == len(pages.build_path())
    assert f["buildMotion"] == 0


def test_a_tap_in_the_played_session_shows_two_links_and_keeps_it_playing(report):
    """n48: touch at 375 and mouse at 1280; Tab reaches the links, Escape hides them."""
    for w in (375, 1280):
        s = report["facts"][f"session@{w}"]
        assert s["state"] == "running" and s["pause"] == "Pause", (w, s)
        assert s["links"] == ["/check", "/start"] and s["wide"] <= w and s["hidden"], (w, s)
        assert s["tabbed"] == "/check" and s["tabShown"] and s["escFocus"] == "session-pause", (w, s)


# ------------------------------------------------------------------ round n52: first-time visitors' ways in ----------
@pytest.fixture(scope="module")
def first_visit(site):
    cmd = ["node", str(ROOT / "tests" / "first_visit_browser.js"), site] + ([CHROMIUM] if CHROMIUM else [])
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_the_start_page_hero_buttons_are_above_the_fold(first_visit):
    """n52: on 29 October 2026 the start page's first button sat at y 1069 (1280 x 800) and 1411 (375 x 812). Now
    "Check your files – no account" and "Connect to Claude" come right after the lede, before the replayed session,
    and both are wholly on the first screen at both sizes, light and dark, with and without reduced motion."""
    for v, ctas in ((k.split("@")[1], c) for k, c in first_visit.items() if k.startswith("hero@")):
        height = int(v.split("-")[0].split("x")[1])
        assert [(c["href"], c["text"]) for c in ctas] == [("/check", "Check your files – no account"), ("/start", "Connect to Claude")], v
        assert all(c["bottom"] <= height for c in ctas), (v, ctas)


def test_the_hero_buttons_come_early_on_the_keyboard(first_visit):
    for w in (1280, 375):
        seen = first_visit[f"tab@{w}"]
        assert "/check" in seen and seen.index("/check") < seen.index("/start"), (w, seen)


def test_the_check_examples_are_above_the_fold_on_a_phone(first_visit):
    """n52: at 375 x 812 the examples sat at y 1078, below the drop box and the privacy note. Now the heading and all
    three examples are on the first screen, and the privacy sentence is still next to the drop box."""
    for v, e in ((k.split("@")[1], c) for k, c in first_visit.items() if k.startswith("examples@")):
        height = int(v.split("-")[0].split("x")[1])
        assert e["heading"]["bottom"] <= height and len(e["buttons"]) == 3, v
        assert all(b["bottom"] <= height for b in e["buttons"]), (v, e["buttons"])
        assert 0 <= e["privacy"]["top"] - e["drop"]["bottom"] <= 40, v
