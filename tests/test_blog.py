"""n145: /blog and its first post. The post is the Markdown file Gustav reviewed, served unchanged at <path>.md and
rendered the way /docs is; its title, meta description and JSON-LD (Article, FAQPage) are read from that file."""
import hashlib
import html as _html
import json
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import pages, server

SLUG = "fabric-totals-double-after-join"
POST = "/blog/" + SLUG
FILE = Path(pages.__file__).parent / "page_templates" / f"BLOG-{SLUG}.md"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    with TestClient(server.build_app()) as c:
        yield c


def _json_ld(text: str) -> list[dict]:
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S)]


def _plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def test_the_post_file_is_the_reviewed_article():
    assert hashlib.sha256(FILE.read_bytes()).hexdigest().startswith("1f6a337a6168fb3b")


def test_both_pages_answer_and_the_markdown_is_the_file(client):
    for path in ("/blog", POST):
        r = client.get(path)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html"), path
    r = client.get(POST + ".md")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    assert r.content == FILE.read_bytes()
    assert client.get("/blog/no-such-post").status_code == 404


def test_the_article_body_is_the_file_rendered(client):
    """Every heading, paragraph, list item, table cell and code line of the file is on the page, in the file's order."""
    page = client.get(POST).text
    body = page[page.index("<article"):page.index("</article>")]
    expected = _plain(pages._md_to_html(FILE.read_text(encoding="utf-8")))
    shown = _plain(body)
    byline = "7 November 2026 · Gustav Kruse, Kruse Consulting AB"
    assert byline in shown
    assert expected in shown.replace(byline + " ", "")
    for line in FILE.read_text(encoding="utf-8").splitlines():                    # the SQL as written, line by line
        if line.startswith(("SELECT", "FROM", "JOIN", "  ", "WITH", "GROUP", "HAVING", ")", "WHERE")):
            assert _html.escape(line, quote=False) in body or _html.escape(line) in body, line


def test_json_ld_is_the_article_and_its_faq(client):
    page = client.get(POST).text
    blocks = _json_ld(page)
    art = next(b for b in blocks if b["@type"] == "Article")
    faq = next(b for b in blocks if b["@type"] == "FAQPage")
    md = FILE.read_text(encoding="utf-8")
    assert art["headline"] == md.splitlines()[0][2:] == "Why Your Fabric Totals Double When You Join Orders to Order Lines"
    assert art["datePublished"] == "2026-11-07" and art["author"]["name"] == "Gustav Kruse"
    assert art["publisher"] == {"@type": "Organization", "name": "Kruse Consulting AB", "url": "https://krusgraph.test/"}
    assert art["url"] == "https://krusgraph.test" + POST and "image" not in art
    qs = [(q["name"], q["acceptedAnswer"]["text"]) for q in faq["mainEntity"]]
    assert [q for q, _ in qs] == ["Why does my revenue double when I join two Fabric tables?",
                                  "Does SELECT DISTINCT fix duplicate rows after a many-to-many join?"]
    faq_html = page[page.index('id="faq"'):page.index("</article>")]
    for q, a in qs:                                                              # the answers word for word as shown
        assert a in _plain(faq_html), q
    assert qs[0][1].startswith("One table is at a finer grain") and qs[1][1].endswith("to find the keys that are not unique.")
    for banned in ("aggregaterating", "ratingvalue", "review\"", "offers"):
        assert banned not in json.dumps(blocks).lower()
    assert _json_ld(client.get("/blog").text) == []


def test_head_has_description_canonical_and_open_graph(client):
    page = client.get(POST).text
    desc = re.search(r'<meta name="description" content="([^"]+)">', page).group(1)
    quick = re.search(r"\*\*Quick answer:\*\* (.+)", FILE.read_text(encoding="utf-8")).group(1).replace("`", "")
    assert len(desc) < 160 and desc.endswith("…") and quick[1:].startswith(desc[1:-1]) and desc[0] == "A"
    assert f'<link rel="canonical" href="https://krusgraph.test{POST}">' in page
    assert f'<meta property="og:description" content="{desc}">' in page and '<meta property="og:type" content="article">' in page
    assert '<meta property="og:title" content="Why Your Fabric Totals Double When You Join Orders to Order Lines — Krusgraph blog">' in page
    assert '<meta property="og:image" content="https://krusgraph.test/static/og.png">' in page and (Path(pages.STATIC_DIR) / "og.png").exists()
    assert f'<link rel="alternate" type="text/markdown" href="{POST}.md"' in page
    assert '<link rel="canonical" href="https://krusgraph.test/blog">' in client.get("/blog").text


def test_external_links_open_safely_and_own_links_stay_plain(client):
    page = client.get(POST).text
    body = page[page.index("<article"):page.index("</article>")]
    ms = re.findall(r'<a href="(https://learn\.microsoft\.com/[^"]+)"([^>]*)>', body)
    assert len(ms) == 2 and all(rel == ' rel="noopener"' for _u, rel in ms)
    assert '<a href="https://krusgraph.com/check">' in body


def test_index_lists_the_post_with_date_and_author(client):
    page = client.get("/blog").text
    main = page[page.index("<main"):page.index("</main>")]
    assert f'<a href="{POST}">Why Your Fabric Totals Double When You Join Orders to Order Lines</a>' in main
    assert '<time datetime="2026-11-07">7 November 2026</time> · Gustav Kruse, Kruse Consulting AB' in main


def test_footer_sitemap_and_llms_list_the_blog(client):
    for path in ("/", "/docs", POST):
        footer = client.get(path).text.split('<footer class="site-footer">')[1]
        assert '<a href="/blog">Blog</a>' in footer, path
    sm = client.get("/sitemap.xml").text
    for p in ("/blog", POST):
        assert f"<url><loc>https://krusgraph.test{p}</loc><lastmod>2026-11-07</lastmod></url>" in sm
    llms = [ln for ln in client.get("/llms.txt").text.splitlines() if "/blog" in ln]
    assert len(llms) == 1 and "](https://krusgraph.test/blog)" in llms[0] and f"https://krusgraph.test{POST}" in llms[0]


def test_the_blog_keeps_the_sales_word_rule(client):
    from test_site import SALES
    for path in ("/blog", POST, POST + ".md"):
        low = client.get(path).text.lower()
        assert not [w for w in SALES if w in low], path
