"""MF1 (27 November 2026): "Why Krusgraph", the founder's short manifesto, at /docs/why. It is the first part of the docs
after the overview (a "##" section of page_templates/DOCS.md, its address in pages.DOCS_PATHS), so the docs index, the
menu, llms.txt and the sitemap list it the usual way. The text is the founder's, as written; under it a calm "See it"
row with three links. The place for its film is at the top and renders nothing until static/media has the film."""
import html as _html
import re

import pytest
from starlette.testclient import TestClient

from fabric_backend import pages, server

PAGE = "/docs/why"
BELIEF = "We believe data work should start with what's true, not with what someone guessed."


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    with TestClient(server.build_app()) as c:
        yield c


def _article(html: str) -> str:
    return html[html.index('<article class="prose docs">'):html.index("</article>")]


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def test_the_page_renders_first_after_the_overview(client):
    ps = pages.docs_pages()
    assert [x["path"] for x in ps[:3]] == ["/docs", PAGE, "/docs/why-krusgraph"]
    assert pages.DOCS_GROUPS[1] == "Why"                            # DS1: the menu group "Why"; the page keeps its title
    r = client.get(PAGE)
    assert r.status_code == 200
    assert '<h1 id="why-krusgraph">Why Krusgraph</h1>' in r.text
    assert "<title>Why Krusgraph — Krusgraph docs</title>" in r.text
    desc = re.search(r'<meta name="description" content="([^"]*)"', r.text).group(1)
    assert _html.unescape(desc) == BELIEF


def test_the_belief_line_count_first_and_the_text_as_written(client):
    art = _article(client.get(PAGE).text)
    # DS1: the belief is the first section, a plain <p> that site.css sizes (and the page's description)
    assert f'<section class="mf-sec mf-hero">\n<p><strong>{_html.escape(BELIEF, quote=False)}</strong></p>' in art
    assert '<p class="mf-sign"><strong>Krusgraph. Count first.</strong></p>' in art
    t = _text(art)
    for s in ("We think that is the wrong order.", "So we do it the other way around.",
              "We count before we build. Every key and every link is checked against your rows.",
              "We show our work. Every rule, every number, every reason.",
              "We say so when we don't know. What the rows can't prove, we hand to you instead of guessing.",
              "You decide. Nothing is created or changed without your yes, and nothing is deleted.",
              "We check what we built. Read back from Fabric, compared with the plan, counted again.",
              "We believe people should spend their time deciding, not double-checking.",
              "We believe trust is earned with numbers, not promises.",
              "We just happen to make it for Microsoft Fabric."):
        assert s in t, s
    assert art.count('class="logo-mark"') == 1                      # one small mark at the end, no mascots
    assert "mascot" not in art


def test_the_see_it_row_links_three_pages_that_answer(client):
    art = _article(client.get(PAGE).text)
    row = re.search(r'<nav class="mf-see" aria-label="See it">(.*?)</nav>', art, re.S).group(1)
    hrefs = [_html.unescape(h) for h in re.findall(r'href="([^"]+)"', row)]
    assert hrefs == ["/check?example=sample&guide=1", "/docs/build-from-a-plan/shared-ontology", "/start"]
    for h in hrefs:
        assert client.get(h).status_code == 200, h
    assert 'class="btn' not in row


def test_linked_from_the_docs_index_and_the_menu(client):
    index = client.get("/docs").text
    kids = re.search(r'<nav class="docs-children" aria-label="All docs pages">(.*?)</nav>', index, re.S).group(1)
    assert f'<a class="docs-group" href="{PAGE}">Why</a>' in kids              # DS1: the group "Why" opens on it
    assert f'<a href="{PAGE}">Why Krusgraph</a>' in _article(index)        # the overview's own "Why" links it
    menu = re.search(r'<nav class="docs-menu"[^>]*>(.*?)</nav>', index, re.S).group(1)
    hrefs = re.findall(r'href="([^"#]+)"', menu)
    assert hrefs.index(PAGE) == hrefs.index("/docs") + 1
    page = client.get(PAGE).text
    assert f'href="{PAGE}" aria-current="page"' in page


def test_the_overviews_own_why_anchor_stays_on_the_overview():
    assert "why-krusgraph" not in pages.docs_anchors()            # /docs#why-krusgraph is the overview's "Why"


def test_no_film_until_the_file_exists(client, monkeypatch, tmp_path):
    assert "<video" not in _article(client.get(PAGE).text)
    assert pages.why_film_html() == ""
    media = tmp_path / "static" / "media"
    media.mkdir(parents=True)
    (media / "krusgraph-why.mp4").write_bytes(b"\0")
    monkeypatch.setattr(pages, "HERE", tmp_path)
    film = pages.why_film_html()
    assert f'<source src="{pages.WHY_FILM_MP4}" type="video/mp4">' in film
    assert 'preload="metadata"' in film and "playsinline" in film and "autoplay" not in film and "poster=" not in film
    (media / "krusgraph-why-poster.webp").write_bytes(b"\0")
    assert f'poster="{pages.WHY_FILM_POSTER}"' in pages.why_film_html()


def test_in_the_sitemap_and_llms_txt(client):
    assert f"https://krusgraph.test{PAGE}</loc>" in client.get("/sitemap.xml").text
    assert f"(https://krusgraph.test{PAGE})" in client.get("/llms.txt").text


def test_no_sales_word_no_price_no_claim_word(client):
    from tests.test_site import SALES
    art = _article(client.get(PAGE).text)
    low = _text(art).lower()
    for w in SALES + ("certified", "partner", "endorsed", "guarantee", "best", "unique", "fastest", "world-class",
                      "cutting-edge", "next-generation", "powerful", "ai-"):
        assert w not in low, w
    assert not re.search(r"[€$£]|\b(?:eur|usd|sek|chf|kr)\b|per month|per user|/month", low)
    assert not re.search(r"\bonly\b", low)
