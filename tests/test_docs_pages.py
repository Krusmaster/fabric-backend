"""n86a: /docs in sub-pages cut out of DOCS.md. Every heading and paragraph is on exactly one page, the menu's links answer,
old /docs#anchors have a page to go to, the pages keep /docs's policy, and the Markdown versions are the same text."""
import re

import pytest
from starlette.testclient import TestClient

from fabric_backend import pages, server


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


def _blocks(md: str) -> list[str]:
    return [b.strip() for b in re.split(r"\n\s*\n", md) if b.strip()]


@pytest.mark.parametrize("registration", ["", "1"])
def test_every_heading_and_paragraph_is_on_exactly_one_page(client, monkeypatch, registration):
    monkeypatch.setenv("KRUSGRAPH_CLIENT_REGISTRATION", registration)
    ps = pages.docs_pages()
    whole = pages.docs_md()
    assert "".join(x["md"] for x in ps) == whole                   # nothing left out, nothing twice, the same order
    per_page = [_blocks(x["md"]) for x in ps]
    for b in set(_blocks(whole)):
        on = [i for i, bl in enumerate(per_page) if b in bl]
        assert sum(bl.count(b) for bl in per_page) == _blocks(whole).count(b), b[:80]
        if _blocks(whole).count(b) == 1:
            assert len(on) == 1, b[:80]
    for x in ps:                                                    # no empty page: each has text under its heading
        assert len(_blocks(x["md"])) >= 2, x["path"]
        body = client.get(x["path"]).text
        for h in re.findall(r"^#{2,3} (.*)$", x["md"], flags=re.M):
            assert f'id="{pages._slug(h)}"' in body, (x["path"], h)
    groups = [x["group"] for x in ps if x["depth"] <= 1]
    assert groups == pages.DOCS_GROUPS


def test_menu_links_answer_and_mark_the_current_page(client):
    html = client.get("/docs").text
    menu = re.search(r'<nav class="docs-menu"[^>]*>(.*?)</nav>', html, re.S).group(1)
    hrefs = re.findall(r'href="([^"#]+)"', menu)
    assert set(x["path"] for x in pages.docs_pages()) | {"/start", "/it", "/lovable"} == set(hrefs)
    for h in hrefs:
        assert client.get(h).status_code == 200, h
    for x in pages.docs_pages():
        t = client.get(x["path"]).text
        assert t.count(f'href="{x["path"]}" aria-current="page"') + t.count(f'href="{x["path"]}" class') >= 2  # both menus
        assert '<details class="docs-menu-m">' in t and 'aria-label="Breadcrumb"' in t and 'class="docs-pager"' in t
    assert client.get("/docs/no-such-page").status_code == 404


def test_old_anchors_have_a_page(client):
    html = client.get("/docs").text
    assert '<script src="/static/docs.js?v=' in html
    data = re.search(r'<script type="application/json" id="docs-anchors">(.*?)</script>', html).group(1)
    import json
    where = json.loads(data)
    assert where == pages.docs_anchors() and len(where) > 25
    for anchor, path in where.items():
        assert path.startswith("/docs/") and f'id="{anchor}"' in client.get(path).text, anchor
    for anchor in ("test-status", "first-time-errors", "databricks-draft-only", "fabric-iq-the-same-graph-as-an-ontology", "tool-reference"):
        assert anchor in where
    # every in-site link to /docs#… names a heading that has a page (or is on /docs itself)
    own = set(re.findall(r'\sid="([^"]+)"', html))
    for page in ("/", "/start", "/it", "/check", "/lovable", "/local", "/support", "/use-cases"):
        for frag in re.findall(r'href="/docs#([^"]+)"', client.get(page).text):
            assert frag in where or frag in own, (page, frag)
    assert client.get("/static/docs.js").status_code == 200


def test_links_inside_the_text_go_to_the_page_with_the_heading(client):
    t = client.get("/docs/build-from-a-plan").text
    assert 'href="/docs/reference/test-status#test-status"' in t        # "Each tool's status is in the tool reference"


def test_sub_pages_keep_the_docs_policy_and_chat_rules(client):
    ref = client.get("/docs").headers
    for x in pages.docs_pages():
        r = client.get(x["path"])
        assert r.headers["content-security-policy"] == ref["content-security-policy"] == client.get("/privacy").headers["content-security-policy"]
        assert "connect-src 'self'" in r.headers["content-security-policy"]
        assert ("kgc-launch" in r.text) and ("data-mascot-toggle" in r.text), x["path"]


def test_markdown_versions_and_discovery(client):
    md = client.get("/docs.md").text
    assert md == pages.docs_md()
    assert "<!-- https://krusgraph.test/docs.md -->\n\n" + pages.docs_md().strip() in client.get("/llms-full.txt").text
    llms, sitemap = client.get("/llms.txt").text, client.get("/sitemap.xml").text
    for x in pages.docs_pages():
        assert f"(https://krusgraph.test{x['path']})" in llms and f"<loc>https://krusgraph.test{x['path']}</loc>" in sitemap
