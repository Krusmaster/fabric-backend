"""n196: the film directly under the home page's headline and buttons (muted, looping, a Pause/Play button, the poster under
reduced motion); three blocks leave the home page for /docs and the footer; a customer quote on /docs only.
The browser half runs tests/n196_browser.js."""
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

from fabric_backend import discovery, offering, pages, server

ROOT = Path(__file__).resolve().parents[1]

QUOTE_SV = ("Krusgraph har förändrat hur mitt team jobbar med data engineering. Det som tidigare tog lång tid kan vi nu bygga "
            "på en eftermiddag: hela flöden och ett ekosystem för vår data. Jag rekommenderar deras MCP-server till alla som "
            "jobbar med data engineering.")
QUOTE_EN = ("Krusgraph has changed how my team works with data engineering. What used to take a long time we can now build in "
            "an afternoon: whole flows and an ecosystem for our data. I recommend their MCP server to anyone who works with "
            "data engineering.")
QUOTE_BY = "Data engineer at a Swedish company (anonymous by request)"

USP_LEAD = ("See how your business tables really connect – with the proof behind every link – so your reports, apps and agents "
            "get the numbers right.")
USP = ("Checked against your rows.", "Errors before anyone sees them.", "One checked plan, every starting point.")
DATA_P = "Planning uses schema metadata. If you ask for data checks, samples or queries"
DATA_STAYS = "stores no table contents. Names, counts and the sample rows you ask for pass through the service in memory"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    with TestClient(server.build_app()) as c:
        yield c


def _plain(h: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h)).strip()


def _main(html: str) -> str:
    return html[html.index('<div data-page="home"'):html.index('<footer class="site-footer">')]


# ------------------------------------------------------------------ 1. the film under the headline --------------------

def test_the_film_is_directly_under_the_headline_and_buttons(client):
    html = client.get("/").text
    hero = re.search(r'<section class="hero">.*?</section>', html, re.S).group(0)
    h1, ctas, film = hero.index("<h1>"), hero.index('class="ctas hero-ctas"'), hero.index('<div class="film film-hero" id="film">')
    assert h1 < ctas < film
    between = hero[ctas:film]
    assert re.sub(r"\s+", "", re.sub(r"<a [^>]*>.*?</a>", "", between)) == 'class="ctashero-ctas"id="connect"></div>'   # only the buttons
    assert hero.index('id="film"') < hero.index('<figure class="session"')                                            # the replay follows
    # the headline, the sentence and the buttons from n188/n194, unchanged
    assert "<h1>Why is your total twice what finance says?</h1>" in hero
    assert "Krusgraph checks keys and joins in your Fabric tables, and shows the rule and the row counts behind every link." in hero
    assert '<a class="btn primary" href="/check">Check my tables</a>' in hero and '<a class="btn secondary" href="/start">Connect to my Fabric</a>' in hero


def test_the_film_is_once_on_the_page_and_still_on_docs(client):
    html = client.get("/").text
    assert html.count("<video") == 1 and html.count('id="film"') == 1
    assert '<section class="wrap film"' not in html and "See how it works" not in html      # the old section below the hero is gone
    docs = client.get("/docs").text
    assert docs.count("<video") == 1 and '<div class="film film-docs" id="film">' in docs


def test_the_hero_film_is_muted_looping_and_has_a_named_button(client):
    hero = re.search(r'<div class="film film-hero" id="film">.*?</div>', client.get("/").text, re.S).group(0)
    video = re.search(r"<video([^>]*)>", hero).group(1)
    for attr in (" muted", " loop", " playsinline", ' preload="metadata"', " controls", ' poster="/static/media/krusgraph-overview-poster.webp"',
                 ' aria-label="Krusgraph overview film, synthetic demo data, AI-generated voice"', ' id="film-video"', " data-film-hero"):
        assert attr in video, attr
    assert "autoplay" not in video and 'loading="lazy"' not in video        # site.js starts it, so reduced motion can keep the poster
    # n161: the per-device versions stay
    assert '<source media="(max-width: 640px)" src="/static/media/krusgraph-overview-web-4x5.mp4"' in hero
    assert '<source src="/static/media/krusgraph-overview-web.mp4"' in hero
    assert '<track kind="captions" srclang="en" label="English" src="/static/media/krusgraph-overview.en.vtt" default>' in hero
    button = re.search(r'<button type="button" class="film-toggle"[^>]*>.*?</button>', hero).group(0)
    assert 'aria-controls="film-video"' in button and _plain(button) == "Play the film"


def test_site_js_starts_the_film_unless_reduced_motion():
    js = (ROOT / "fabric_backend/static/site.js").read_text()
    part = js[js.index("n196: the film under the home page's headline"):]
    part = part[:part.index("});\n", part.index("if (!still)")) + 4]
    assert "prefers-reduced-motion: reduce" in part and "if (!still)" in part and "v.muted = true" in part
    assert "'Play the film'" in part and "'Pause the film'" in part


# ------------------------------------------------------------------ 3. the three blocks leave the home page -----------

def test_the_three_blocks_are_no_longer_on_the_home_page(client):
    main = _main(client.get("/").text)
    # a) the chip, the sentence, the three points and the SAP line
    assert 'class="ba-mini"' not in main and "One order, 2 lines, sample data" not in main
    assert "See how your business tables really connect" not in main and 'class="usp"' not in main
    assert not any(u in main for u in USP) and "usp-sap" not in main and "MANDT" not in main
    # b) Which Krusgraph should I use? with its rows and the paragraph, and the status line
    assert '<h2 id="choose-short-home"' not in main and 'class="wrap choose-short"' not in main
    assert not any(q in main for q, _k in offering.DECIDE)
    assert offering.NO_AI not in main
    assert 'id="status"' not in main and "home-status" not in main
    # c) What Krusgraph reads
    assert "What Krusgraph reads" not in main and 'id="data"' not in main and "trust-wrap" not in main
    assert DATA_P not in main and DATA_STAYS not in main


def test_the_home_page_still_leads_to_check_choose_and_docs(client):
    html = client.get("/").text
    main = _main(html)
    assert 'href="/check"' in main and 'href="/choose"' in main                          # the buttons; the products' diagram
    assert '<a href="/docs"' in html                                                   # the navigation


def test_the_home_page_keeps_its_other_sections_in_order(client):
    main = _main(client.get("/").text)
    order = ['<section class="hero">', 'id="example"', 'id="demo"', 'class="wrap offering"', 'id="paths"', 'id="how"',
             'class="hub', 'id="developer"', 'id="faq"', 'class="card ready"']
    at = [main.index(x) for x in order]
    assert at == sorted(at), dict(zip(order, at))


def test_docs_starts_with_what_krusgraph_does_then_which_krusgraph(client):
    html = client.get("/docs").text
    art = html[html.index('<article class="prose docs">'):]
    after_h1 = art[art.index("</h1>"):]
    first = re.search(r"<p>(.*?)</p>", after_h1, re.S).group(1)
    assert _plain(first) == "What Krusgraph does"
    assert after_h1.index("What Krusgraph does") < after_h1.index(USP_LEAD) < after_h1.index("Which Krusgraph should I use?") < after_h1.index('id="film"')
    ul = re.search(r"<ul>(.*?)</ul>", after_h1[after_h1.index(USP_LEAD):], re.S).group(1)
    items = [_plain(x) for x in re.findall(r"<li>(.*?)</li>", ul, re.S)]
    assert items == list(discovery.USP_POINTS)                # the docs' wording of the three points, as in llms.txt
    assert '<a href="/sap">SAP tables: keys with MANDT and the order-to-cash links, each with its public source</a>' in after_h1
    assert html.count("See how your business tables really connect") == 1                # once, not twice
    md = client.get("/docs.md").text
    assert md.index("What Krusgraph does") < md.index(USP_LEAD) < md.index("Which Krusgraph should I use?")


def test_docs_has_data_and_access_with_the_home_page_text(client):
    html = client.get("/docs").text
    art = html[html.index('<article class="prose docs">'):]
    sec = art[art.index("<strong>Data and access</strong>"):art.index('id="why-krusgraph"')]
    assert DATA_P in sec and 'href="/privacy">Read how data and access are handled</a>' in sec
    quote = re.search(r"<blockquote>(.*?)</blockquote>", sec, re.S).group(1)
    assert ("Krusgraph " + DATA_STAYS) in quote and 'href="/it#data-goes">Where your data goes</a>' in quote
    assert html.count(DATA_P) == 1
    points = [_plain(x) for x in re.findall(r"<li><strong>(.*?)</strong>", sec, re.S)]
    assert points == ["How it connects.", "Nothing is created until you ask.", "Open source."]   # the section's three points too


def test_the_footer_has_the_preview_line_and_the_data_link(client):
    for path in ("/", "/docs", "/choose", "/check"):
        html = client.get(path).text
        foot = html[html.index('<footer class="site-footer">'):]
        line = re.search(r'<p class="muted tiny footer-status">(.*?)</p>', foot, re.S).group(1)
        assert _plain(line) == "Krusgraph is a preview service. Test status per tool · How data and access are handled · Security and data.", path
        assert '<a href="/docs#test-status">Test status per tool</a>' in line and '<a href="/privacy">How data and access are handled</a>' in line


def test_which_krusgraph_is_once_on_docs_and_choose(client):
    docs = client.get("/docs").text
    art = docs[docs.index('<article class="prose docs">'):docs.index('<nav class="docs-children"')]
    assert art.count("Which Krusgraph should I use?") == 1
    choose = client.get("/choose").text
    assert choose.count("<h1>Which Krusgraph should I use?</h1>") == 1


# ------------------------------------------------------------------ 3b. the customer quote, on /docs only -----------

def test_the_customer_quote_is_on_the_docs_get_started_page(client):
    html = client.get("/docs/get-started").text
    q = re.search(r"<blockquote>(.*?)</blockquote>", html, re.S).group(1)
    ps = [_plain(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", q, re.S)]
    assert ps == [f"“{QUOTE_SV}”", f"“{QUOTE_EN}” (English translation)", f"— {QUOTE_BY}"]
    assert ps[0].startswith("“Krusgraph har")                                            # Swedish first
    for no in ("★", "&#9733;", "<img", "<svg", "stars", "logo"):
        assert no not in q
    md = client.get("/docs.md").text
    assert md.count(QUOTE_SV) == 1 and md.count(QUOTE_EN) == 1 and md.count(QUOTE_BY) == 1
    assert md.index("## Get started") < md.index(QUOTE_SV) < md.index("### Connect")


def test_the_customer_quote_is_nowhere_else(client):
    words = ("förändrat hur mitt team", "changed how my team works", "Data engineer at a Swedish company")
    paths = [p for p in pages.PAGES] + ["/docs", "/docs/concepts", "/choose", "/blog", "/llms.txt"]
    for path in paths:
        r = client.get(path)
        if r.status_code != 200 or path in ("/docs/get-started",):
            continue
        assert not any(w in r.text for w in words), path
    sources = [p for p in (ROOT / "fabric_backend").rglob("*") if p.is_file() and p.suffix in (".py", ".html", ".md", ".js", ".json")]
    hits = [p.relative_to(ROOT).as_posix() for p in sources if "förändrat hur mitt team" in p.read_text(encoding="utf-8", errors="ignore")]
    assert hits == ["fabric_backend/page_templates/DOCS.md"]


# ------------------------------------------------------------------ 4. the browser ------------------------------------

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
        run = subprocess.run(["node", str(ROOT / "tests" / "n196_browser.js"), base], capture_output=True, text=True, timeout=600)
        assert run.returncode == 0, run.stderr[-3000:]
        yield json.loads(run.stdout.strip().splitlines()[-1])
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_browser_film_in_the_first_viewport_under_the_buttons(browser):
    assert browser["errors"] == []
    assert len(browser["sizes"]) == 8
    for key, s in browser["sizes"].items():
        assert s["h1InView"] and s["ctasInView"], key
        assert s["filmAfterButtons"] and s["gapAfterButtons"] < 48, key                  # directly under the buttons
        assert s["filmTop"] < s["vh"] - 100 and s["visibleFraction"] > 0.2, key       # the film starts in the first screen
        assert s["filmCentre"] < 2, key
        assert not s["overflow"], key
        assert s["films"] == 1, key
        assert s["muted"] and s["loop"] and s["playsinline"] and s["preload"] == "metadata" and not s["autoplayAttr"], key
        assert not s["paused"] and s["button"] == "Pause the film" and s["buttonVisible"], key
    for scheme in ("light", "dark"):
        for w in ("1280", "1440"):                                                       # at least the top half without scrolling
            assert browser["sizes"][f"{scheme} {w}"]["visibleFraction"] >= 0.5, (scheme, w)
        assert browser["sizes"][f"{scheme} 1440"]["filmWidth"] > 1000                    # n203: wider than n196's 960 px
        assert browser["sizes"][f"{scheme} 375"]["filmWidth"] >= 330                     # the content width on a phone
    assert browser["sizes"]["light 1440"]["theme"] != browser["sizes"]["dark 1440"]["theme"]


def test_browser_the_film_is_as_wide_as_the_replay_card(browser):
    # n203: the film's frame and the replay card under it share one width and the same left and right edges, at every size
    for key, s in browser["sizes"].items():
        assert abs(s["frameWidth"] - s["cardWidth"]) <= 2, (key, s["frameWidth"], s["cardWidth"])
        assert abs(s["frameLeft"] - s["cardLeft"]) <= 2 and abs(s["frameRight"] - s["cardRight"]) <= 2, key
        assert s["cardAfterFilm"], key                                                    # the order: film, then the replay
    for scheme in ("light", "dark"):
        assert browser["sizes"][f"{scheme} 1440"]["cardWidth"] > 1000, scheme             # the card grows with the film
        assert browser["sizes"][f"{scheme} 375"]["cardWidth"] >= 330, scheme


def test_browser_the_replay_card_has_no_blank_band_and_does_not_jump(browser):
    # n203: no fixed floor under the thread; the card keeps the longest turn's height through all four turns; and while a
    # question is typed the previous question and answer stay above the field, so the room the card reserves is not an
    # empty band (before n203 it was empty for the whole typing: 317 px on a phone, 187 px on a desktop)
    for key, s in browser["sizes"].items():
        r = s["replay"]
        assert r["minHeight"] == "0px", key
        assert max(r["heights"]) - min(r["heights"]) <= 1, (key, r["heights"])
        for gap, room in zip(r["typingGaps"], r["typingRoom"]):
            assert room <= r["longest"] + 16 + 12 + 2, (key, room, r["longest"])        # the turn's 16 px gap, the heading's 12 px
            assert gap < 100 and gap <= 0.35 * room, (key, gap, room)


def test_the_previous_answer_stays_while_the_next_question_is_typed():
    css = (ROOT / "fabric_backend/static/site.css").read_text()
    assert "@media (prefers-reduced-motion:no-preference){.hero .session-turn{animation-name:session-turn-held}}" in css
    held = re.search(r"@keyframes session-turn-held\{(.*?\})\}", css).group(1)
    # shown from 1.5 %, on top during its own turn, kept under the next turn until that question is sent (5.25 % of the
    # next turn = 30.25 %), then gone; the 24 s cycle and the 6 s delays are n165's
    assert held == "0%{opacity:0;z-index:2}1.5%,24.9%{opacity:1;z-index:2}25%,30.25%{opacity:1;z-index:1}30.5%,100%{opacity:0;z-index:1}"
    sent = re.search(r"@keyframes session-sent\{0%,([\d.]+)%\{opacity:0", css).group(1)
    assert 25 + float(sent) == 30.25


def test_browser_reduced_motion_keeps_the_poster_and_the_button_works_by_keyboard(browser):
    r = browser["reduced"]
    assert r["still"] == {"paused": True, "time": 0, "poster": "/static/media/krusgraph-overview-poster.webp", "button": "Play the film"}
    assert r["afterEnter"] == {"paused": False, "button": "Pause the film", "focused": True}
    assert r["afterSpace"] == {"paused": True, "button": "Play the film"}
    assert r["name"]["tag"] == "BUTTON" and r["name"]["type"] == "button"
    assert r["name"]["video"] == "Krusgraph overview film, synthetic demo data, AI-generated voice"
