"""W7 (the founder, 24 November 2026): the docs menu keeps its place. A page opened from the menu showed the menu from
the top again, so a link far down meant scrolling the long menu on every page; and the menu, meant to be sticky with its
own scroll from 960 px, scrolled away with the page, because body's overflow-x:hidden made body a scroll container that
never scrolls (n148 had changed it to clip under 760 px only).

Now body clips at every width, so the menu and "On this page" stay put, and site.js scrolls the menu, and only the menu,
so that the current page's link is in view. Nothing is stored; the window's scroll and #hash links are untouched. Under
960 px the menu is the closed "Docs menu" above the text, as before. The browser half runs tests/w7_docs_browser.js
(W7_SHOTS=<dir> keeps its screenshots)."""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "fabric_backend/static/site.css").read_text(encoding="utf-8")
JS = (ROOT / "fabric_backend/static/site.js").read_text(encoding="utf-8")


def _block() -> str:
    return JS[JS.index("W7: the docs menu keeps its place"):JS.index("window.KrusGraph =")]


def test_body_clips_instead_of_becoming_a_scroll_container():
    body = re.search(r"^body\{[^}]*\}", CSS, re.M).group(0)
    assert "overflow-x:hidden;overflow-x:clip" in body             # clip wins where supported; hidden is the fallback


def test_the_menu_is_sticky_with_its_own_scroll_from_960px():
    wide = CSS[CSS.index("@media (min-width:960px){\n  .docs-layout"):]
    rule = re.search(r"\.docs-menu\{[^}]*\}", wide).group(0)
    for part in ("position:sticky", "top:16px", "max-height:calc(100vh - 32px)", "overflow-y:auto"):
        assert part in rule, part


def test_the_script_scrolls_the_menu_only_and_stores_nothing():
    block = _block()
    assert "docsMenu.scrollTop" in block and "aria-current=page" in block
    for never in ("scrollIntoView", "window.scrollTo", "window.scroll(", "scrollBy", "sessionStorage", "localStorage", "location"):
        assert never not in block, never


# ------------------------------------------------------------------ the browser ------------------------------------

def _playwright() -> bool:
    return bool(shutil.which("node")) and subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


@pytest.fixture(scope="module")
def browser():
    if not _playwright():
        pytest.skip("node + playwright not available")
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    env = os.environ | {"PRODUCT_NAME": "Krusgraph", "MCP_PUBLIC_URL": "https://krusgraph.test/mcp", "CONTACT_EMAIL": "hello@krusgraph.test",
                        "ENTRA_CLIENT_ID": "00000000-0000-0000-0000-000000000000", "ENTRA_CLIENT_SECRET": "test-only"}
    proc = subprocess.Popen([sys.executable, "-m", "fabric_backend.server", "--host", "127.0.0.1", "--port", str(port)], env=env,
                            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(base + "/healthz", timeout=1); break
            except Exception:
                time.sleep(0.25)
        else:
            pytest.fail("server did not start")
        run = subprocess.run(["node", str(ROOT / "tests" / "w7_docs_browser.js"), base], capture_output=True, text=True, timeout=600)
        assert run.returncode == 0, run.stderr[-3000:]
        yield json.loads(run.stdout.strip().splitlines()[-1])
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_browser_no_script_errors(browser):
    assert browser["errors"] == []


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_browser_a_link_low_in_the_menu_is_in_view_after_the_click(browser, scheme):
    w = browser["wide"][scheme]
    first, target, after = w["first"], w["target"], w["after"]
    assert first["sticky"] == "sticky" and first["overflowY"] == "auto" and first["menuScrolls"]
    assert target["index"] >= target["of"] - 3 and target["scrolledTo"] > 0           # a link near the menu's bottom
    assert after["href"] == target["href"]                                            # the page that was clicked
    assert after["inMenu"], after                                                      # its link is in the menu's visible part
    assert after["menuScroll"] > 0 and 0 <= after["linkTop"] and after["linkBottom"] <= 800
    assert after["windowY"] == 0 and not after["overflow"]                             # the window did not move
    assert after["bodyBg"] == ("rgb(31, 27, 25)" if scheme == "dark" else "rgb(251, 248, 245)")


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_browser_a_hash_still_lands_and_the_menu_stays_on_screen(browser, scheme):
    h = browser["hash"][scheme]
    assert 0 <= h["headingTop"] < 100, h                                                # the anchor is at the top
    assert h["windowY"] > 0 and h["menuTop"] == 16 and h["sticky"] == "sticky"          # sticky: the menu is still there
    assert h["inMenu"] and h["href"] == h["url"].split("#")[0]


def test_browser_a_phone_keeps_the_closed_docs_menu(browser):
    d = browser["phone"]["docs"]
    assert d["details"] and not d["open"] and not d["wideMenuShown"]
    assert d["windowY"] == 0 and not d["overflow"]


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_browser_the_sap_film_on_the_docs_page(browser, scheme):
    s = browser["sap"][scheme]
    assert s["preload"] == "none" and s["controls"] and not s["autoplay"]
    assert s["src"].endswith("krusgraph-sap-to-report.mp4") and s["poster"].endswith("krusgraph-sap-to-report-poster.webp")
    assert s["track"] == {"kind": "captions", "srclang": "en", "def": True, "src": "/static/media/krusgraph-sap-to-report.en.vtt"}
    assert abs(s["ratio"] - 16 / 9) < 0.01 and s["width"] > 600 and s["link"] and not s["overflow"]
    assert s["active"] == "/docs/concepts/sap-on-fabric"


def test_browser_the_sap_film_fits_a_phone(browser):
    p = browser["phone"]["sap"]
    assert p["left"] >= 0 and p["right"] <= p["vw"] and abs(p["ratio"] - 16 / 9) < 0.01 and not p["overflow"]
