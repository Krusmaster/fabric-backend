"""n154: the founder's feedback of 8 November 2026 on n149. The replay is back in the home page's hero, under the two
buttons and above the small before and after, and its first round starts with question 1 already sent and answered;
the chat's button ("Try a demo") is on every page the site renders, the home page and /check included; on /check, whose
policy lets the page fetch nothing, the chat reads the same plan from the page. Its "Fix data issues" and "Write dbt
tests" link the docs of what exists today. n149's headline, labels, Blog link, /check card and /start line stay."""
import json
import re
import subprocess

import pytest

from fabric_backend import pages
from fabric_backend.demo import demo_plan_json
from tests.test_site import client  # noqa: F401  (the site's test client)
from test_browser import CHROMIUM, ROOT, _playwright_available, site  # noqa: F401

CSS = (ROOT / "fabric_backend" / "static" / "site.css").read_text(encoding="utf-8")


def _rendered_pages(client):
    """Every HTML page the site serves: the sitemap's pages and the ones it leaves out (privacy, local, the consent
    return page, the 404 pages)."""
    urls = re.findall(r"<loc>https?://[^/<]+(/[^<]*)</loc>", client.get("/sitemap.xml").text)
    urls += ["/privacy", "/local", "/lovable", "/pricing", "/it", "/start", "/use-cases", "/blog", pages.CONSENT_PATH,
             "/no-such-page", "/docs/no-such-page"]
    out = {}
    for u in sorted(set(urls)):
        r = client.get(u, headers={"accept": "text/html"})
        if r.headers.get("content-type", "").startswith("text/html"):
            out[u] = r
    return out


def test_the_button_is_on_every_rendered_page(client):
    seen = _rendered_pages(client)
    for must in ("/", "/check", "/docs", "/docs/reference/tools", "/blog", pages.BLOG_TOTALS, "/lovable", "/pricing", "/it",
                 "/privacy", "/start", "/use-cases", "/use-cases/build", "/partners", "/support", "/local"):
        assert must in seen, must
    assert len(seen) > 40
    for path, r in seen.items():
        assert r.text.count('id="kgcLaunch"') == 1, path
        assert r.text.index("</footer>") < r.text.index('id="kgcLaunch"'), path
    assert pages.CHAT_OFF == ("/demo",) and not hasattr(pages, "PILL_OFF")


def test_check_carries_the_plan_and_keeps_fetching_nothing(client):
    r = client.get("/check")
    assert "connect-src 'none'" in r.headers["content-security-policy"]
    block = re.search(r'<script type="application/json" id="kgcPlan">(.*?)</script>', r.text, re.S).group(1)
    assert "</" not in block and json.loads(block) == json.loads(demo_plan_json())
    assert r.text.count('id="kgcPlan"') == 1 and r.text.index('id="kgcPlan"') < r.text.index('<script src="/static/site.js')
    assert 'id="kgcPlan"' not in client.get("/").text            # elsewhere the chat fetches /demo/plan.json
    js = (ROOT / "fabric_backend" / "static" / "chat-demo.js").read_text(encoding="utf-8")
    assert "document.getElementById('kgcPlan')" in js and "JSON.parse(inline.textContent)" in js


def test_the_hero_has_the_replay_under_the_buttons_and_keeps_n149(client):
    html = client.get("/").text
    hero = re.search(r'<section class="hero">.*?</section>', html, re.S).group(0)
    order = [hero.index(x) for x in ("<h1>Why is your total twice what finance says?</h1>", 'class="lede"', "hero-ctas",
                                     '<figure class="session"', '<p class="ba-mini">', 'class="usp"')]
    assert order == sorted(order)
    assert ">Check my tables</a>" in hero and ">Connect to my Fabric</a>" in hero
    fig = hero[hero.index('<figure class="session"'):hero.index("</figure>")]
    assert "A replay of a session in Claude" in fig and "Create an ontology from my shop data." in fig
    assert "Answers shortened from real runs in Claude against synthetic shop data" in fig
    assert re.findall(r'class="session-tool">(\w+)<', fig) == ["plan_backend", "validate_plan", "create_ontology", "create_semantic_model"]
    assert html.count('<figure class="session"') == 1 and ".replay{" not in CSS
    # what n149 kept: Blog in the navigation, /check's card after a result, /start's line for people from /check
    assert re.search(r'<a href="/blog">Blog</a>', re.search(r'<nav id="site-nav".*?</nav>', html, re.S).group(0))
    assert 'id="check-live"' in client.get("/check").text and "Coming from /check?" in client.get("/start").text


def test_the_replay_starts_with_its_first_message_shown():
    """The first turn's first round shows the question and answer from the start (no empty thread above the field);
    from 24 s on it plays as the other turns do; with reduced motion all four show as before."""
    first = CSS[CSS.index("/* n154: the replay is back in the hero"):]
    assert ".session-turn:first-child{animation:session-turn-first 24s,session-turn 24s 24s infinite}" in first
    assert "@keyframes session-turn-first{0%,23.25%{opacity:1}25%,100%{opacity:0}}" in first
    assert "@keyframes session-first-on{0%,100%{opacity:1;transform:none}}" in first
    assert ".session-turn:first-child .session-text{animation:session-first-off 24s,session-type 24s 24s infinite steps(28,end)}" in first
    assert "animation-name:session-first-off,session-show" in first           # the narrow screen's variant
    assert "@media (prefers-reduced-motion:reduce)" in first and "{animation:none}" in first
    assert ".session-turn{justify-content:flex-start}" in first and ".session-ask{margin-top:auto}" in first


@pytest.mark.skipif(not _playwright_available(), reason="node + playwright not available")
def test_in_a_browser_the_hero_and_the_button_everywhere(site):
    out = subprocess.run(["node", str(ROOT / "tests" / "n154_browser.js"), site] + ([CHROMIUM] if CHROMIUM else []),
                         capture_output=True, text=True, timeout=400)
    assert out.returncode == 0, out.stderr[-2000:]
    r = json.loads(out.stdout.strip().splitlines()[-1])
    assert r["errors"] == []
    for w in (375, 1280):
        h = r[f"hero{w}"]
        assert h["inHero"] and h["ctas"]["bottom"] <= h["session"]["top"] <= h["ctas"]["bottom"] + 40, h
        assert h["session"]["bottom"] <= h["mini"]["top"] <= h["usp"]["top"], h
        # the first message is there at once, close under the panel's heading: no empty thread before the first line
        assert h["sentOpacity"] == 1 and h["answerOpacity"] == 1 and h["turnsShown"] == 1, h
        assert h["sent"]["top"] - h["head"]["bottom"] < 40, h
        assert r[f"later{w}"][1] == 1 and r[f"later{w}"][0] == 0, r[f"later{w}"]
        for path in ("/", "/check", "/start", "/pricing", "/docs/reference/tools", "/blog/fabric-totals-double-after-join", "/lovable", "/it"):
            f = r[f"{path}@{w}"]
            # shown in its corner, except that it steps aside while it would cover /check's drop area (a phone's width)
            assert f["exists"] and f["shownAtEnd"] and not f["coversHeader"] and not f["coversDrop"], (path, w, f)
            assert f["shown"] or (path == "/check" and w == 375), (path, w, f)
            assert f["pill"]["right"] <= w and f["pill"]["bottom"] <= 800, (path, w, f)
        chat = r[f"checkChat{w}"]
        assert "/demo/plan.json" not in chat["requests"], chat                  # the plan came from the page
        assert [(x["label"], x["tag"], x["href"], x["planned"]) for x in chat["links"]] == [
            ("Fix data issues", "A", "/docs/explore-and-check/fix-data-issues", False),
            ("Write dbt tests", "A", "/docs/reference/tools", False)], chat
        assert r[f"deepLink{w}"]["path"] == "/docs/explore-and-check/fix-data-issues", r[f"deepLink{w}"]
