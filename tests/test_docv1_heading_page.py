"""DOCV1 (Gustav, 21 November 2026: "översätt och lägg in i docs på hemsidan"): the docs page "Where Krusgraph is
heading", with its hand-drawn sketch as a static inline SVG (fabric_backend/heading_sketch.py draws it once).

The page renders, is in the docs menu and linked from the docs start page and the get-started page, says the honest
status line near the top, uses none of the forbidden words, loads nothing from another host, and at 390 px the page
does not scroll sideways (only the sketch's own box does)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import heading_sketch, server

PATH = "/docs/why/vision"                       # DS1: "Where Krusgraph is heading" is a part of Vision, in the group "Why"
OLD = "/docs/concepts/where-krusgraph-is-heading"        # its old address answers 301 to that part
TITLE = "Where Krusgraph is heading"
STATUS = ("This is a sketch of where we are heading, not what ships today. Today every step is rules; whether Ask, Run "
          "and Use get an optional model is being decided. Data stays in your Fabric either way.")
# the words this page never uses (in the brief's order); checked on the article and the sketch, not on the site's menus
FORBIDDEN = ("lovable", "strawberry", "works with claude", "replaces data engineers", "replace data engineers",
             "certified", "certification", "partner", "endorse", "compliant", "compliance", "faster", "seconds",
             "minutes", "2026", "2027", "q1", "q2", "q3", "q4", "coming soon", "next month", "next year")
TESTS = Path(__file__).parent


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()
    mp.setenv("PRODUCT_NAME", "Krusgraph")
    mp.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    with TestClient(server.build_app()) as c:
        yield c
    mp.undo()


def _text(h: str) -> str:
    h = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", h, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).strip()


def _article(h: str) -> str:
    a = re.search(r'<article class="prose docs">(.*?)</article>', h, re.S).group(1)
    return re.sub(r"<nav\b.*?</nav>", " ", a, flags=re.S)          # the breadcrumb, menus and pager are the site's


def test_the_checked_in_sketch_is_what_the_module_draws():
    assert heading_sketch.SVG_PATH.read_text(encoding="utf-8") == heading_sketch.build_svg(), \
        "run: python -m fabric_backend.heading_sketch"
    assert heading_sketch.SVG_PATH.parent.name == "static"            # package data (static/*), so the image has it


def test_the_page_renders_with_its_title_and_the_status_near_the_top(client):
    r = client.get(PATH)
    assert r.status_code == 200
    assert f'<h2 id="where-krusgraph-is-heading">{TITLE}</h2>' in r.text                 # DS1: a part of Vision
    assert "<title>Vision — Krusgraph docs</title>" in r.text
    assert f'<a href="#where-krusgraph-is-heading">{TITLE}</a>' in r.text                # in "On this page"
    body = _text(_article(r.text))
    assert STATUS in body
    assert body.index(TITLE) < body.index(STATUS) < body.index("Your Fabric tenant") < body.index("Three kinds of helper")   # before the sketch
    old = client.get(OLD, follow_redirects=False)
    assert old.status_code == 301 and old.headers["location"] == f"{PATH}#where-krusgraph-is-heading"


def test_the_page_says_what_the_brief_asks(client):
    body = _text(_article(client.get(PATH).text))
    for s in ("Your estate", "The mascots suggest", "Plan", "Answer: reads and replies. It writes nothing.",
              "A rule or a person decides", "A person promotes it", "The compiler, which turns a plan into Fabric items, "
              "and the approver are not agents. So the same plan gives the same result every time.", "use it in Claude",
              "Data rows are read only inside Fabric"):
        assert s in body, s


def test_the_sketch_is_inline_and_described(client):
    h = client.get(PATH).text
    svg = re.search(r'<svg class="hs-svg".*?</svg>', h, re.S).group(0)
    assert 'role="img"' in svg and 'aria-labelledby="hs-title hs-desc"' in svg
    assert "<desc id=\"hs-desc\">A hand-drawn sketch." in svg
    t = _text(svg)
    for s in ("Your Fabric tenant · your data stays here", "Sign in with Entra", "Krusgraph", "Your estate", "keys 6/6",
              "missing", "desired vs actual", "The mascots suggest", "You have no gold", "for orders.",
              "Build gold + model", "Add a key check", "Show why", "one tap = a dry run", "+ 4 gold views",
              "+ model on gold", "+ 12 tests", "the rest: defaults", "Approve", "PR in Fabric Git",
              "One sign-in + one approval.", "Everything else is a default.", "Behind the scenes", "Find", "Ask", "Build",
              "Run", "Use", "Improve", "gray = rules", "purple = a model proposes", "amber = you approve",
              "data rows are read only inside Fabric"):
        assert s in t, s
    assert "The sketch in words" in h                                  # the same content as a list, for anyone


@pytest.mark.parametrize("where", ["/docs", PATH])
def test_the_page_is_in_the_docs_menu(client, where):
    menu = re.search(r'<nav class="docs-menu" aria-label="Docs">(.*?)</nav>', client.get(where).text, re.S).group(1)
    assert f'<a href="{PATH}"' in menu and "Vision" in menu


@pytest.mark.parametrize("where", ["/docs", "/docs/get-started", PATH])
def test_the_docs_start_and_the_start_path_link_it(client, where):
    href = "#where-krusgraph-is-heading" if where == PATH else f"{PATH}#where-krusgraph-is-heading"   # on Vision: its own part
    assert f'href="{href}"' in _article(client.get(where).text), where


def test_the_markdown_twin_has_it(client):
    md = client.get("/docs.md").text
    assert f"#### {TITLE}" in md and STATUS in md


@pytest.mark.parametrize("where", [PATH, "/docs.md"])
def test_no_forbidden_words(client, where):
    h = client.get(where).text
    if where == PATH:
        h = _article(h)
    else:
        h = h[h.index(f"#### {TITLE}"):]
        h = h[:h.index("\n## ")]
    low = _text(h).lower()
    for s in FORBIDDEN:
        assert not re.search(r"(?<![a-z])" + re.escape(s) + r"(?![a-z])", low), s
    assert "Use it in Claude".lower() in low


def test_nothing_loads_from_another_host(client):
    h = client.get(PATH).text
    assert not re.search(r'<script[^>]+src="(?:https?:)?//', h)
    for tag in re.findall(r'<link[^>]+href="(?:https?:)?//[^"]*"[^>]*>', h):     # only the page's own address
        assert re.search(r'rel="(?:canonical|alternate)"', tag), tag
    assert "fonts.googleapis" not in h and "fonts.gstatic" not in h
    svg = heading_sketch.svg().replace(f'xmlns="{heading_sketch.XMLNS}"', "")
    assert "http" not in svg and "<image" not in svg and "@import" not in svg
    css = client.get("/static/site.css").text
    assert not re.search(r"url\((?:['\"])?(?:https?:)?//", css) and "@import" not in css


def _browser_ready() -> bool:
    if not shutil.which("node"):
        return False
    r = subprocess.run(["node", "-e", "require('playwright').chromium.launch().then(b => b.close())"],
                       capture_output=True, cwd=TESTS.parent, timeout=60)
    return r.returncode == 0


def test_390_px_has_no_page_level_sideways_scroll(client, tmp_path):
    if not _browser_ready():
        pytest.skip("node with playwright and Chromium is not available here")
    h = client.get(PATH).text
    files = {"__page__": PATH, PATH: ["text/html", h]}
    for ref in re.findall(r'(?:href|src)="(/static/[^"?]+\.(?:css|js))(?:\?[^"]*)?"', h):
        r = client.get(ref)
        files[ref] = [r.headers["content-type"], r.text]
    (tmp_path / "files.json").write_text(json.dumps(files), encoding="utf-8")
    p = subprocess.run(["node", str(TESTS / "test_docv1_overflow.js"), str(tmp_path / "files.json")],
                       capture_output=True, text=True, cwd=TESTS.parent, timeout=120)
    assert p.returncode == 0, p.stderr
    runs = json.loads(p.stdout.strip().splitlines()[-1])
    for x in runs:
        assert x["page"] <= x["inner"], x                              # the page itself never scrolls sideways
        assert x["box"] <= x["inner"], x                               # the sketch's box fits; the sketch scrolls in it
        assert x["font"] >= 12, x                                      # the sketch's body text stays legible
        assert not x["external"], x
    dark = next(x for x in runs if x["scheme"] == "dark")
    light = next(x for x in runs if x["scheme"] == "light")
    assert dark["ink"] != light["ink"]                                 # the sketch follows the theme
