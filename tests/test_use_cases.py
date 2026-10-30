"""/use-cases: the page, its Markdown twin, discovery entries, the three maps (engine output, drawn by /check's
renderer) and the word cap (n59)."""
import re

import pytest
from starlette.testclient import TestClient

from fabric_backend import pages, server, use_cases
import html as htmllib
import json

from fabric_backend.browser_check import analyze


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


def _main(html: str) -> str:
    return html.split('<main id="main"', 1)[1].split("</main>", 1)[0]


def _words(html: str) -> int:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", _main(html), flags=re.S)
    return len(htmllib.unescape(re.sub(r"<[^>]+>", " ", text)).split())


def test_page_renders_indexable_with_the_examples_the_industries_and_the_footnote(client):
    r = client.get("/use-cases")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    html = r.text
    assert "{{" not in html
    assert 'name="robots" content="noindex' not in html and 'content="index,follow' in html
    assert '<link rel="canonical" href="https://krusgraph.test/use-cases">' in html
    assert '<link rel="alternate" type="text/markdown" href="/use-cases.md"' in html
    for slug, name, _line in use_cases.INDUSTRIES:
        assert f'id="{slug}"' in html and htmllib.escape(name, quote=False) in html, slug
    assert use_cases.FOOTNOTE in html
    assert "For Fabric consultancies" in html and 'href="/start"' in html and 'href="/docs"' in html
    assert "mailto:hello@krusgraph.test" in html
    assert 'id="problem-total-doubles"' in html                            # linked from /check
    assert html.count('data-mascot="') == 1                                 # one mascot moment
    scripts = re.findall(r"<script\b[^>]*>", _main(html))
    assert all('type="application/json"' in t or re.search(r'src="/static/(map|use-cases)\.js\?v=', t) for t in scripts), scripts
    assert "<style" not in html and ' style="' not in _main(html)
    for m in re.finditer(r'<(?:script|link|img)[^>]+(?:src|href)="([^"]+)"', html):
        if not m.group(0).startswith('<link rel="canonical"'):
            assert not m.group(1).startswith(("http://", "https://", "//")), m.group(0)


def test_the_page_stays_under_the_word_cap(client):
    """n59: the page was 5 800 words with ten industry sketches; the cap keeps it short."""
    assert _words(client.get("/use-cases").text) <= use_cases.WORD_CAP


def test_each_map_is_the_engines_run_drawn_by_the_check_renderer(client):
    """The embedded data is what /check draws for the same example: the same tables, relationships and suggestion;
    the finding buttons are the engine's own findings; the page loads map.js, the file /check loads."""
    html = client.get("/use-cases").text
    assert '<script src="/static/map.js?v=' in client.get("/check").text and '<script src="/static/map.js?v=' in html
    for kind, anchor, _title, _text, _button in use_cases.EXAMPLES:
        card = html.split(f'id="{anchor}"', 1)[1]
        card = card.split('data-try="', 1)[0]
        data = json.loads(card.split('class="uc-map-data">', 1)[1].split("</script>", 1)[0])
        events = []
        r = analyze(kind, emit=events.append)
        by = {e["step"]: e for e in events}
        steps = {s["step"]: s for s in data["steps"]}
        assert [t["name"] for t in steps["keys"]["tables"]] == [t["name"] for t in by["keys"]["tables"]]
        assert steps["relationships"]["relationships"] == by["relationships"]["relationships"]
        assert steps["suggest"]["suggested"] == by["suggest"].get("suggested", [])
        titles = {f["title"] for f in r["findings"] + r["suggestions"]}
        assert 1 <= len(data["findings"]) <= 3 and all(f["title"] in titles for f in data["findings"])
        assert card.count("data-finding=") == len(data["findings"])
        assert f'{len(r["tables"])} tables, {len(r["relationships"])} relationships' in card


def test_three_synthetic_examples_open_check_with_their_example(client):
    """n55: retail and e-commerce, manufacturing and sales with SAP, sales and CRM; marked synthetic; no logistics,
    warehouse or supply-chain theme anywhere on the page."""
    html = client.get("/use-cases").text
    sec = html.split('id="try"', 1)[1].split("</section>", 1)[0]
    assert re.findall(r'href="(/check\?example=\w+)"', sec) == ["/check?example=sample", "/check?example=sap", "/check?example=crm"]
    for h in ("Retail and e-commerce", "Manufacturing and sales with SAP", "Sales and CRM"):
        assert f"<h3>{h}</h3>" in sec, h
    assert sec.count("Synthetic data</span>") == 3
    low = (_main(html) + client.get("/use-cases.md").text).lower()
    assert not any(w in low for w in ("logistic", "warehouse", "supply chain", "inventory", "lager"))
    assert html.index('id="try"') < html.index('id="tasks"')


def test_tasks_link_to_anchors_on_the_page(client):
    html = client.get("/use-cases").text
    for href in re.findall(r'<li class="uc-task".*?href="#([\w-]+)"', html):
        assert f'id="{href}"' in html, href


def test_the_build_cards_have_their_own_page(client):
    r = client.get("/use-cases/build")
    assert r.status_code == 200 and 'id="build"' in r.text and 'href="/use-cases/build"' in client.get("/use-cases").text
    assert '<a href="/use-cases" aria-current=page>' in r.text


def test_page_keeps_out_what_it_must_not_claim(client):
    page = client.get("/use-cases").text
    text = page + client.get("/use-cases.md").text
    low = text.lower().replace("based in uppsala, sweden, and bern, switzerland", "")    # n53: the footer's agreed fact
    for banned in ("switzerland", "swiss", "logistics", "warehousing", "distribution", "pharmacy", "wholesale", " ewm",
                   "trusted by", "customer story", "case study", "testimonial", "chf", "price:", "€", "$"):
        assert banned not in low, banned
    assert not re.search(r"\d+\s?%", text.split("<main")[1] if "<main" in text else text)      # no invented percentages


def test_nav_and_footer_link_the_page(client):
    for path in ("/", "/docs", "/use-cases"):
        html = client.get(path).text
        nav = html.split('id="site-nav"')[1].split("</nav>")[0]
        footer = html.split('class="footer-links"')[1].split("</nav>")[0]
        assert '<a href="/use-cases"' in nav and ">Use cases</a>" in nav, path
        assert '<a href="/use-cases">Use cases</a>' in footer, path
    assert '<a href="/use-cases" aria-current=page>' in client.get("/use-cases").text


def test_nav_and_footer_link_the_page(client):
    for path in ("/", "/docs", "/use-cases"):
        html = client.get(path).text
        nav = html.split('id="site-nav"')[1].split("</nav>")[0]
        footer = html.split('class="footer-links"')[1].split("</nav>")[0]
        assert '<a href="/use-cases"' in nav and ">Use cases</a>" in nav, path
        assert '<a href="/use-cases">Use cases</a>' in footer, path
    assert '<a href="/use-cases" aria-current=page>' in client.get("/use-cases").text


def test_markdown_twin_sitemap_and_llms(client):
    r = client.get("/use-cases.md")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    md = r.text
    assert md.startswith("# Use cases") and "{{" not in md and "<div" not in md and "<svg" not in md
    for _slug, name, _line in use_cases.INDUSTRIES:
        assert f"**{name}.**" in md
    assert use_cases.FOOTNOTE in md and "https://krusgraph.test/start" in md and "hello@krusgraph.test" in md
    assert "<loc>https://krusgraph.test/use-cases</loc>" in client.get("/sitemap.xml").text
    assert "(https://krusgraph.test/use-cases.md)" in client.get("/llms.txt").text
    assert "<!-- https://krusgraph.test/use-cases.md -->" in client.get("/llms-full.txt").text


