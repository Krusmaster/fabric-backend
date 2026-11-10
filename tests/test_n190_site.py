"""Round n190: the home page redesign after the outside UX review of 9 November 2026. One promise, a working demo entry,
four intent tiles to working /check flows, the map, a before and after computed from the engine's run, and one status
per output on every page (fabric_backend/claims.py). The browser half runs tests/n190_browser.js; set N190_SHOTS to a
directory to keep its screenshots (375, 768 and 1440 px, light and dark)."""
from __future__ import annotations

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

from fabric_backend import claims, offering, pages, server, tool_status as ts

ROOT = Path(__file__).resolve().parents[1]
CLAIM_PAGES = ("/", "/start", "/choose", "/pricing")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _main(html: str) -> str:
    return html[html.index('<main id="main"'):html.index("</main>")]


# ------------------------------------------------------------------ the hero, the CTAs and the intent tiles ----------

def test_hero_has_one_promise_and_two_ctas(client):
    html = client.get("/").text
    hero = html[html.index('<section class="hero home-hero"'):html.index("</section>", html.index('<section class="hero home-hero"'))]
    assert hero.count("<h1") == 1 and f">{claims.HEADLINE}</h1>" in hero
    assert claims.SUPPORT in hero
    ctas = re.findall(r'<div class="ctas hero-ctas" id="connect">(.*?)</div>', hero, re.S)[0]
    assert re.findall(r'<a class="btn (\w+)" href="([^"]+)"[^>]*>([^<]+)</a>', ctas) == [
        ("primary", "/check?example=sample&amp;guide=1", "Try the free demo"), ("secondary", "/start", "Connect Microsoft Fabric")]
    assert pages.CONNECT_LABEL == "Connect Microsoft Fabric"
    assert "ba-mini" in hero and "2 000" in hero and "1 000" in hero and 'href="#example">why</a>' in hero  # kept
    assert "<textarea" not in hero and "<input" not in hero                       # no free-text box


def test_intent_tiles_route_to_check_with_the_sample(client):
    html = client.get("/").text
    tiles = re.findall(r'<a class="intent-tile \w+" href="([^"]+)" data-intent="(\w+)"><strong>([^<]+)</strong>', html)
    assert [t[2] for t in tiles] == ["Find broken relationships", "Understand how my tables connect", "Build a Power BI model",
                                     "Prepare my data for an AI agent"]
    js = (ROOT / "fabric_backend/static/check.js").read_text()
    for href, key, _ in tiles:
        assert href == f"/check?example=sample&amp;intent={key}"
        assert f"    {key}: () =>" in js, key                                   # check.js acts on each intent
        assert client.get(href.replace("&amp;", "&")).status_code == 200


def test_every_home_link_answers(client):
    html = client.get("/").text
    for href in sorted(set(re.findall(r'href="(/[^"#]*)', _main(html)))):
        href = href.replace("&amp;", "&")
        if href.startswith("/static/"):
            continue
        assert client.get(href).status_code == 200, href


def test_home_order_follows_the_brief(client):
    body = _main(client.get("/").text)
    marks = ['class="hero home-hero"', 'id="intents-h"', 'id="see-h"', 'id="example-h"', 'id="build-h"', 'id="ways"',
             'id="how-h"', 'id="data-h"', 'id="final-h"']
    pos = [body.index(m) for m in marks]
    assert pos == sorted(pos)
    final = body[body.index('id="final-h"'):]
    assert "See what your data can become." in final
    assert [a for a in re.findall(r'data-cta="(\w+)"', final)] == ["demo", "connect", "pilot"]
    # what left the home page: the session replay (chat-like), the hub, the film, the FAQ
    for gone in ('class="session"', 'class="wrap connects"', 'class="film', 'id="faq"', "In Fabric, Krusgraph creates"):
        assert gone not in body, gone


def test_navigation_has_five_entries_and_one_cta(client):
    html = client.get("/pricing").text
    nav = re.search(r'<nav id="site-nav" class="site-nav" aria-label="Main">(.*?)</nav>', html, re.S).group(1)
    assert [x for x in re.findall(r">([^<]+)</a>", nav)] == ["Product", "Examples", "How it works", "Pricing", "Docs", "Try free demo"]
    assert 'aria-current=page>Pricing<' in nav
    for href in re.findall(r'href="([^"]+)"', nav):
        assert client.get(href.replace("&amp;", "&")).status_code == 200, href
    foot = html[html.index('<nav class="footer-links"'):]
    for moved in ('href="/check"', 'href="/blog"', 'href="/support"', 'href="/partners"', "github.com", 'href="/privacy"', 'href="/terms"'):
        assert moved in foot, moved


def test_old_routes_and_seo_are_kept(client):
    html = client.get("/").text
    assert "<title>Krusgraph | Find how your Microsoft Fabric data connects</title>" in html
    assert '<link rel="canonical"' in html and 'property="og:title"' in html and "application/ld+json" in html
    for path in list(pages.PAGES) + ["/docs", "/check", "/lovable", "/local", "/privacy", "/blog", "/llms.txt", "/sitemap.xml"]:
        assert client.get(path).status_code == 200, path
    for old, new in pages.REDIRECTS.items():
        r = client.get(old, follow_redirects=False)
        assert r.status_code in (301, 302, 307, 308) and r.headers["location"].endswith(new)


# ------------------------------------------------------------------ before and after -------------------------------

def test_before_and_after_comes_from_the_engines_run(client):
    from fabric_backend.browser_check import analyze
    r = analyze("sample")
    body = client.get("/").text
    ba = body[body.index('id="example"'):body.index("</section>", body.index('id="example"'))]
    before = ba[ba.index('data-ba="before"'):ba.index('data-ba="after"')]
    after = ba[ba.index('data-ba="after"'):]
    amount = next(f["amount"] for f in r["findings"] if f.get("amount") and not f["amount"]["on_map"])
    assert f"{len(r['tables'])} tables" in before and "2 000" in before and amount["wrong"] == 2000
    assert f"{len(r['relationships'])} links explained" in after and r["health"] in after and "1 000" in after
    issues = re.findall(r'<details class="ba-issue"><summary>([^<]+)</summary><p class="ba-tech"><code>([^<]+)</code>', after)
    assert len(issues) == len(r["findings"]) + len(r["suggestions"])
    assert ("We could not find what identifies a row in audit_log", "audit_log has no key (K3)") in issues
    assert all(plain != tech for plain, tech in issues)                       # plain words first, the technical detail on expand


def test_plain_words_for_an_orphan_check():
    f = {"check": "orphans", "link": {"source": "orders", "target": "customers", "source_cols": ["customer_id"]}, "title": "x"}
    assert pages.plain_issue(f) == "Some orders rows reference customers we could not find"


# ------------------------------------------------------------------ one status per output, everywhere ---------------

def test_claims_are_derived_from_tool_status():
    assert claims.status("semantic_model") == "Tested live" and "create_semantic_model" in ts.LATER_LIVE
    assert claims.status("pipeline") == "Tested live" and "create_pipeline" in ts.RAN_LIVE
    assert claims.status("data_agent") == "Experimental" and "create_data_agent" in ts.CREATE_RECORD
    assert claims.status("graphql") == "Experimental" and ts.create_api_word() == "Experimental"
    assert claims.status("app") == "Preview"
    assert {r["status"] for r in claims.table()} <= set(claims.CHIPS)


@pytest.mark.parametrize("path", CLAIM_PAGES)
def test_every_page_shows_every_output_with_the_same_chip(client, path):
    html = client.get(path).text
    found = re.findall(r'data-claim="(\w+)" data-status="([^"]+)"[^>]*>([^<]+)</a>', html)
    want = {k: claims.status(k) for k, *_ in claims.OUTPUTS}
    assert {k for k, _, _ in found} == set(want), path
    for key, status, text in found:
        assert status == want[key] == text, (path, key)


def test_docs_and_markdown_twins_carry_the_same_table(client):
    rows = [f"| {r['name']} | {r['status']} |" for r in claims.table()]
    for path in ("/docs.md", "/choose.md"):
        text = client.get(path).text
        assert all(x in text for x in rows), path
        assert claims.RUNS in text, path
    page = client.get(pages.docs_anchors()["test-status"]).text
    for r in claims.table():
        assert f"<td>{r['name']}</td><td>{r['status']}</td>" in page, r["name"]
    start_md = client.get("/start.md").text
    assert all(r["name"] in start_md and r["status"] in start_md for r in claims.table())


def test_the_contradiction_is_gone(client):
    """The review: the home page said Krusgraph creates models and ontologies, the set-up page that some create tools lack
    permissions on the hosted service. One sentence about running (claims.RUNS) is shown with the chips everywhere, and no
    page says an item needs a permission the hosted service does not ask for while no tool is OPERATOR."""
    operator = any(s.available == ts.OPERATOR for s in ts.STATUS.values())
    for path in CLAIM_PAGES + ("/docs.md", "/it", "/use-cases"):
        text = _plain(client.get(path).text)
        if not operator:
            assert "does not ask for today" not in text, path
        assert "Does not run or schedule the notebooks" not in text, path
    for path in CLAIM_PAGES:
        assert _plain(claims.RUNS) in _plain(client.get(path).text), path
    fabric = offering.way("fabric")
    assert any("Run once or Schedule" in x and "DataPipeline.Execute.All" in x for x in fabric["lacks"])


def test_no_unbacked_claims_on_the_home_page(client):
    text = _plain(_main(client.get("/").text)).lower()
    for word in ("certified", "endorsed", "testimonial", "trusted by", "soc 2 compliant", "gdpr compliant", "10x", "faster than",
                 "in seconds", "in minutes"):
        assert word not in text, word
    assert "<img" not in _main(client.get("/").text) or "logo" not in _main(client.get("/").text).lower()


# ------------------------------------------------------------------ the browser half ----------------------------------

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
        args = ["node", str(ROOT / "tests" / "n190_browser.js"), base] + ([os.environ["N190_SHOTS"]] if os.environ.get("N190_SHOTS") else [])
        run = subprocess.run(args, capture_output=True, text=True, timeout=900)
        assert run.returncode == 0, run.stderr[-3000:]
        yield json.loads(run.stdout.strip().splitlines()[-1])
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_browser_home_fits_and_works_at_three_widths(browser):
    assert browser["errors"] == []
    assert sorted(browser["home"]) == ["dark-1440", "dark-375", "light-1440", "light-375", "light-768"]
    for k, r in browser["home"].items():
        assert r["overflow"] is False, k
        assert r["h1"] == claims.HEADLINE and r["map"] and r["chips"] == len(claims.OUTPUTS), k
        assert [c["href"] for c in r["ctas"]] == ["/check?example=sample&guide=1", "/start"], k
        assert len(r["tiles"]) == 4 and all(t["href"].startswith("/check?example=sample&intent=") for t in r["tiles"]), k
        assert r["nav"][-1] == "Try free demo", k
        assert all(f["active"] and f["outline"] for f in r["focus"].values()), (k, r["focus"])
        for part, ratios in r["contrast"].items():
            assert ratios and min(ratios) >= 4.5, (k, part, ratios)
        assert r["tileTransition"] in ("0s", "0s, 0s"), k                     # prefers-reduced-motion


def test_browser_each_intent_lands_on_its_part_of_the_result(browser):
    i = browser["intents"]
    assert all("error" not in v for v in i.values()), i
    assert i["issues"]["allOpen"] and i["issues"]["findings"] >= 1
    assert i["map"]["map"]
    assert i["model"]["modelOpen"] and i["model"]["modelShown"]
    assert i["agent"]["evidence"] and i["agent"]["ontologyTile"]


def test_browser_axe_finds_no_violations(browser):
    if browser["axe"] is None:
        pytest.skip("axe-core is not installed (it is not a dependency of this repository)")
    assert {k: v for k, v in browser["axe"].items() if v} == {}
