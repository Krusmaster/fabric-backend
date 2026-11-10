"""n206: the home page tidied for launch-day traffic. One diagram (the four products; the hub left), its sources as the
status record says (tool_status.SOURCES), a short Try in Claude, the button pair only in the hero and the final call to
action, the three steps without the replay's questions, and the sections in the founder's order. The browser half runs
tests/n206_browser.js at 375, 768, 1280 and 1440 px, light and dark."""
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
from starlette.testclient import TestClient

from fabric_backend import offering, pages, server
from fabric_backend import tool_status as ts

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    with TestClient(server.build_app()) as c:
        yield c


def _main(html: str) -> str:
    return html[html.index('<div data-page="home"'):html.index('<footer class="site-footer">')]


def _plain(h: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h)).strip()


# ------------------------------------------------------------------ 1. one diagram -----------------------------------

def test_one_diagram_on_the_home_page_the_four_products(client):
    main = _main(client.get("/").text)
    assert main.count('<figure class="off-fig"') == 1 and "One engine, four products" in main
    assert '<div class="hub">' not in main and 'class="wrap connects"' not in main
    assert "Where you build" not in main and "What Krusgraph builds in Fabric" not in main
    assert "{{HOME_HUB}}" not in pages._read("home.html")


# ------------------------------------------------------------------ 2. sources from the status record ----------------

def _sources(box: str) -> list[tuple[str, str]]:
    src = box[box.index('class="off-src"'):box.index('class="off-engine"')]
    return re.findall(r'<li>([^<]+?) <span class="off-src-st">([^<]+)</span></li>', src)


@pytest.mark.parametrize("path", ["/", "/choose"])
def test_the_diagrams_sources_equal_the_status_record(client, path):
    html = client.get(path).text
    box = html[html.index('<section class="wrap offering"'):]
    box = box[:box.index("</section>")]
    assert _sources(box) == [(n, "tested end to end" if t else "experimental") for n, t in ts.SOURCES]
    assert _sources(box) == [("Lakehouse", "tested end to end"), ("Warehouse", "experimental"), ("SQL database", "experimental")]
    assert "irrored" not in box                                          # not supported yet (planned, n201)
    words = re.search(r'<div id="offering-words">(.*?)</div>', box, re.S).group(1)
    assert "lakehouse (tested end to end), warehouse (experimental), SQL database (experimental)" in words


def test_the_status_word_is_muted_in_both_themes():
    css = (ROOT / "fabric_backend" / "static" / "site.css").read_text(encoding="utf-8")
    assert ".off-src-st{display:block;font-size:12.5px;color:var(--muted)}" in css


# ------------------------------------------------------------------ 3. Try in Claude, short --------------------------

def test_try_in_claude_on_the_home_page_is_two_buttons_and_one_line(client):
    main = _main(client.get("/").text)
    box = re.search(r'<div class="try-claude">(.*?)</div>', main, re.S).group(1)
    assert 'data-try-claude' in box and "data-desktop-link" in box and box.count('class="btn ') == 2
    note = re.search(r'<p class="muted tiny try-claude-note"[^>]*>(.*?)</p>', box, re.S).group(1)
    assert note == pages.TRY_SHORT_NOTE == "The button copies the first question and opens Claude."
    assert "no documented way" not in main
    # /start keeps the long note
    assert "no documented way" in client.get("/start").text


# ------------------------------------------------------------------ 4. the button pair, and the order ---------------

def test_the_button_pair_appears_at_most_twice_hero_and_final(client):
    main = _main(client.get("/").text)
    ctas = re.findall(r'<(?:div|p) class="ctas[^"]*"[^>]*>(.*?)</(?:div|p)>', main, re.S)
    pairs = [c for c in ctas if re.search(r'class="btn [^"]*" href="/check"', c) and re.search(r'class="btn [^"]*" href="/start"', c)]
    assert len(pairs) == 2
    assert main.index(pairs[0]) < main.index('id="film"') and main.index(pairs[1]) > main.index('id="faq"')
    # every button to /check or /start on the page is one of those four
    assert len(re.findall(r'class="btn [^"]*" href="/(?:check|start)"', main)) == 4
    # "Try it yourself" links once in its text instead
    tp = main[main.index('id="paths"'):main.index('id="how"')]
    assert '<a href="/check">the check page</a>' in tp and '<a href="/start">connect Krusgraph to your AI client</a>' in tp


def test_the_sections_keep_the_founders_order(client):
    main = _main(client.get("/").text)
    marks = ['class="hero"', 'id="film"', '<figure class="session"', 'class="wrap before-after"', 'id="offering"', 'id="paths"',
             'id="how"', 'id="developer"', 'id="faq"', "Try it on a schema you know."]
    at = [main.index(m) for m in marks]
    assert at == sorted(at)


def test_the_three_steps_no_longer_repeat_the_replays_questions(client):
    main = _main(client.get("/").text)
    how = main[main.index('id="how"'):main.index('id="developer"')]
    assert '<span class="ex">' not in how and how.count('<span class="step-n') == 3
    assert "Check the plan against the data." not in how


def test_no_testimonial_or_customer_on_the_home_page(client):
    text = _plain(_main(client.get("/").text))
    assert "<blockquote" not in _main(client.get("/").text) and "anonymous by request" not in text


# ------------------------------------------------------------------ 5. the browser ------------------------------------

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
        run = subprocess.run(["node", str(ROOT / "tests" / "n206_browser.js"), base], capture_output=True, text=True, timeout=600)
        assert run.returncode == 0, run.stderr[-3000:]
        yield json.loads(run.stdout.strip().splitlines()[-1])
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_browser_no_horizontal_scroll_at_four_widths_in_both_themes(browser):
    assert browser["errors"] == []
    assert sorted(browser["sizes"]) == sorted(f"{w}-{s}" for w in (375, 768, 1280, 1440) for s in ("light", "dark"))
    for key, s in browser["sizes"].items():
        assert s["overflow"] == 0, key
        assert s["wide"] == [], key                                       # no element wider than the page
        assert s["themed"], key                                           # the dark theme is dark, the light light


def test_browser_one_diagram_and_the_sources_as_rendered(browser):
    for key, s in browser["sizes"].items():
        assert s["figures"] == 1 and s["hubs"] == 0, key
        assert s["sources"] == [f"{n}\n{ts.source_word(t)}" for n, t in ts.SOURCES], key


def test_browser_no_orphaned_headings_and_even_spacing(browser):
    for key, s in browser["sizes"].items():
        assert s["orphans"] == [], key                                    # a heading is never the last thing in its section
        assert s["gaps"], key
        assert max(s["gaps"]) - min(s["gaps"]) <= 24, (key, s["gaps"])   # the room between sections stays even


def test_browser_buttons_wrap_cleanly_on_a_phone(browser):
    s = browser["sizes"]["375-light"]
    assert s["buttonsClipped"] == [], s["buttonsClipped"]                 # every button inside the page, on one line or wrapped whole
    assert s["buttonsOverlap"] == []
