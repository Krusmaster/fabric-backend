"""W8 (the founder, 24 November 2026): "Why Krusgraph" in eight points, on the home page and at /docs/why-krusgraph.

One source (fabric_backend/why.py) for both; every point links its evidence, and every link answers here (a page of
this site, with its anchor) or is the Microsoft Learn page the repository already cites. No price, no ruled-out word."""
import html as _html
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import pages, server, why

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


def _plain(s: str) -> str:
    t = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()
    return re.sub(r"\(\s+", "(", re.sub(r"\s+([,.;:)])", r"\1", t))


def _section(home: str) -> str:
    i = home.index('id="why"')
    return home[i:home.index("</section>", i)]


def test_eight_points_in_the_founders_order():
    """Each point has a short line for the home page (one sentence or two, under 140 characters) and a line for the docs."""
    ps = why.points()
    assert [p["id"] for p in ps] == ["no-guessing", "a-person-decides", "fabric-building-blocks", "light-on-resources",
                                     "run-it-yourself", "free-and-workload", "who-makes-it", "not-one-platform"]
    for p in ps:
        assert p["links"] and len(re.split(r"(?<=[.;])\s", p["line"])) <= 6, p["id"]      # one line, not a paragraph
        assert len(p["short"]) <= 140, p["id"]


def test_the_docs_page_renders_second_in_the_menu(client):
    r = client.get(why.PAGE)
    assert r.status_code == 200
    art = r.text[r.text.index('<article class="prose docs">'):]
    assert '<h1 id="why-choose-krusgraph">Why choose Krusgraph</h1>' in art
    text = _plain(art[:art.index("</article>")])
    for p in why.points():
        assert _plain(p["title"]) in text and _plain(p["line"].replace("{{PRODUCT}}", "Krusgraph").replace("`", "")) in text, p["id"]
    menu = re.search(r'<nav class="docs-menu"[^>]*>(.*?)</nav>', client.get("/docs").text, re.S).group(1)
    hrefs = re.findall(r'href="([^"#]+)"', menu)
    assert hrefs.index(why.PAGE) == hrefs.index("/docs") + 1 < hrefs.index("/docs/get-started")
    assert pages.DOCS_GROUPS[1] == "Why Krusgraph"
    assert 'href="/docs/why-krusgraph"' in client.get("/docs").text          # the overview's "Why" links it


def test_the_home_page_has_the_compact_section_and_links_the_page(client):
    home = client.get("/").text
    main = home[home.index("<main"):home.index("</main>")]
    assert main.index('id="how"') < main.index('id="why"') < main.index('id="developer"')
    sec = _section(main)
    assert f'href="{why.PAGE}"' in sec and sec.count("<li ") == 8
    for p in why.points():
        assert _plain(p["short"]) in _plain(sec)
        assert f'id="why-{p["id"]}"' in sec and _plain(p["title"]).replace("'", "’") in _plain(sec).replace("'", "’")
    assert "{{" not in sec and 'class="btn' not in sec                     # the page keeps its four buttons


def _links(text: str) -> list[str]:
    return re.findall(r'href="([^"]+)"', text)


@pytest.mark.parametrize("where", ["/", why.PAGE])
def test_every_evidence_link_resolves(client, where):
    text = client.get(where).text
    part = _section(text) if where == "/" else text[text.index('<article class="prose docs">'):text.index("</article>")]
    if where != "/":
        part = part[part.index('id="why-choose-krusgraph"'):part.index('class="docs-pager"')]
    hrefs = set(_links(part))
    wanted = {h for p in why.points() for h, _t in p["links"]}
    if where == "/":
        wanted = {p["links"][0][0] for p in why.points()}
    assert wanted <= {_html.unescape(h) for h in hrefs}
    for h in hrefs:
        h = _html.unescape(h)
        if h.startswith("http"):
            # outside links: the repository itself, or the one Microsoft Learn page the repository already cites
            assert h.startswith(why.GITHUB + "/blob/main/") or h == why.DIRECT_LAKE, h
            if h.startswith(why.GITHUB):
                assert (ROOT / h.split("/blob/main/", 1)[1]).is_file(), h
            continue
        path, _, frag = h.partition("#")
        r = client.get(path)
        assert r.status_code == 200, h
        if frag:
            assert f'id="{frag}"' in r.text, h
    assert "fundamentals/direct-lake-overview" in (ROOT / "fabric_backend" / "semantic_model.py").read_text(encoding="utf-8")


def test_the_rule_names_follow_the_engine():
    from fabric_backend.infer import RULES
    ks = sorted(int(k[1:]) for k in RULES if re.fullmatch(r"K\d+", k))
    rs = sorted(int(k[1:]) for k in RULES if re.fullmatch(r"R\d+", k))
    assert f"K0–K{ks[-1]} for keys, R0–R{rs[-1]} for relationships" in why.points()[0]["line"]


def test_no_price_no_sales_word_and_true_status(client):
    from tests.test_site import SALES
    home = _section(client.get("/").text)
    page = client.get(why.PAGE).text
    page = page[page.index('<article class="prose docs">'):page.index("</article>")]
    for text in (home, page, why.markdown()):
        low = _plain(text).lower()
        assert not re.search(r"[€$£]|\b(?:eur|usd|sek|chf|kr)\b|per month|per user|/month", low), low[:200]
        for w in SALES + ("fast", "faster", "certified", "partner", "endorsed", "guarantee", "hallucinat", "best"):
            assert w not in low, w
        # the workload and Marketplace as the status pages say: a pilot (preview); listing and Marketplace planned
        assert "pilot (preview)" in low and "marketplace" in low and "planned" in low and "available today" not in low
        assert "based in uppsala, sweden, and bern, switzerland" in low and "swiss company" not in low
        assert "databricks: draft only" in low
    assert "planned, not available yet" in _plain(page).lower() and "mirrored databases (experimental)" in _plain(page).lower()
    from fabric_backend import offering
    assert "pilot (preview)" in offering._status_fabric().lower() and "planned, not available" in offering._status_fabric()


def test_the_page_is_in_the_sitemap_and_llms_txt(client):
    assert f"https://krusgraph.test{why.PAGE}</loc>" in client.get("/sitemap.xml").text
    assert f"[Why choose Krusgraph](https://krusgraph.test{why.PAGE})" in client.get("/llms.txt").text
