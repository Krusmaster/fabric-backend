"""DS1 (27 November 2026): the docs menu in six groups (Why, Get started, How it works, Check, Build, Run and reference),
and /docs/why, the manifesto, laid out in sections with the same words. Every docs address and /docs#anchor that existed
before DS1 still answers: a page that kept its address answers 200, a page that moved answers 301 to its new address."""
import html as _html
import re

import pytest
from starlette.testclient import TestClient

from fabric_backend import pages, server

# every docs address before DS1 (main at 95eee63), with its page title then
OLD = {
    "/docs": "Overview",
    "/docs/why": "Why Krusgraph",
    "/docs/why-krusgraph": "Why choose Krusgraph",
    "/docs/get-started": "Get started",
    "/docs/get-started/connect": "Connect",
    "/docs/get-started/what-you-can-ask": "What you can ask",
    "/docs/get-started/first-time-errors": "First-time errors",
    "/docs/concepts": None,                                   # the group page: "Concepts" then, "How it works" now
    "/docs/concepts/how-it-works": "How it works",
    "/docs/concepts/ontologies": "Ontologies",
    "/docs/concepts/data-products": "Data products",
    "/docs/concepts/how-they-connect": "How they connect",
    "/docs/concepts/where-it-runs": "Where it runs",
    "/docs/concepts/vision": "Vision",
    "/docs/concepts/where-krusgraph-is-heading": "Where Krusgraph is heading",
    "/docs/explore-and-check": None,                          # "Explore and check" then, "Check" now
    "/docs/explore-and-check/review-check-then-create": "Review, check, then create",
    "/docs/explore-and-check/keep-your-review": "Keep your review",
    "/docs/explore-and-check/fix-data-issues": "Fix data issues",
    "/docs/explore-and-check/how-relationships-are-inferred": "How relationships are inferred",
    "/docs/explore-and-check/sources": "Sources",
    "/docs/explore-and-check/how-krusgraph-uses-graph-theory": "How Krusgraph uses graph theory",
    "/docs/explore-and-check/sap-on-fabric": "SAP on Fabric",
    "/docs/build-from-a-plan": None,                          # "Build from a plan" then, "Build" now
    "/docs/build-from-a-plan/one-plan-five-fabric-pieces": "One plan, five Fabric pieces",
    "/docs/build-from-a-plan/create-a-dbt-flow": "Create a dbt flow",
    "/docs/build-from-a-plan/fabric-iq-the-same-graph-as-an-ontology": "Fabric IQ: the same graph as an ontology",
    "/docs/build-from-a-plan/shared-ontology": "Shared ontology",       # sent to an external reader: must stay
    "/docs/build-from-a-plan/two-steps-stay-manual": "Two steps stay manual",
    "/docs/build-from-a-plan/app-access": "App access",
    "/docs/build-from-a-plan/use-with-lovable": "Use with Lovable",
    "/docs/build-from-a-plan/databricks-draft-only": "Databricks (Draft only)",
    "/docs/krusgraph-for-fabric": "Krusgraph for Fabric",
    "/docs/krusgraph-for-fabric/what-the-krusgraph-model-item-does": "What the Krusgraph Model item does",
    "/docs/krusgraph-for-fabric/next-steps-with-other-workloads": "Next steps with other workloads",
    "/docs/krusgraph-for-fabric/add-it-to-your-fabric": "Add it to your Fabric",
    "/docs/krusgraph-for-fabric/permissions-in-plain-words": "Permissions in plain words",
    "/docs/krusgraph-for-fabric/network-hosts": "Network hosts",
    "/docs/krusgraph-for-fabric/troubleshooting": "Troubleshooting",
    "/docs/reference": "Tool reference",
    "/docs/reference/test-status": "Test status",
    "/docs/reference/overview-tools-functions-and-clients": "Overview: tools, functions and clients",
    "/docs/reference/tools": "Tools",
    "/docs/reference/for-agents": "For agents",
    "/docs/reference/with-microsoft-s-fabric-mcp-servers": "With Microsoft's Fabric MCP servers",
    "/docs/hosting-and-permissions": "Hosting and permissions",
    "/docs/hosting-and-permissions/what-it-accesses": "What it accesses",
    "/docs/hosting-and-permissions/cold-start-and-min-replicas-if-you-run-it-yourself": "Cold start, and min_replicas if you run it yourself",
    "/docs/hosting-and-permissions/support": "Support",
}
MOVED = {
    "/docs/concepts/vision": "/docs/why/vision",
    "/docs/concepts/where-krusgraph-is-heading": "/docs/why/vision#where-krusgraph-is-heading",
    "/docs/explore-and-check/how-relationships-are-inferred": "/docs/concepts/how-relationships-are-inferred",
    "/docs/explore-and-check/sources": "/docs/concepts/sources",
    "/docs/explore-and-check/how-krusgraph-uses-graph-theory": "/docs/concepts/how-krusgraph-uses-graph-theory",
    "/docs/explore-and-check/sap-on-fabric": "/docs/concepts/sap-on-fabric",
    "/docs/krusgraph-for-fabric/troubleshooting": "/docs/troubleshooting",
    "/docs/hosting-and-permissions/support": "/docs/support",
}
GROUPS = ["Why", "Get started", "How it works", "Check", "Build", "Run and reference"]


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()
    mp.setenv("PRODUCT_NAME", "Krusgraph")
    mp.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    with TestClient(server.build_app()) as c:
        yield c
    mp.undo()


def _title(h: str) -> str:
    return _html.unescape(re.search(r"<title>(.*?)</title>", h).group(1))


def _text(h: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


@pytest.mark.parametrize("old", list(OLD))
def test_every_old_docs_address_still_answers(client, old):
    r = client.get(old, follow_redirects=False)
    if old in MOVED:
        assert r.status_code == 301, old
        assert r.headers["location"] == MOVED[old]
        to, _, frag = MOVED[old].partition("#")
        page = client.get(to)
        assert page.status_code == 200, to
        if frag:                                              # merged: a part of the page it moved into
            assert re.search(rf'<h2 id="{frag}">{re.escape(OLD[old])}</h2>', page.text), old
        else:
            assert _title(page.text) == f"{OLD[old]} — Krusgraph docs", old
    else:
        assert r.status_code == 200, old
        if OLD[old] and old != "/docs":
            assert _title(r.text) == f"{OLD[old]} — Krusgraph docs", old


def test_the_shared_ontology_address_sent_out_is_the_page_itself(client):
    r = client.get("/docs/build-from-a-plan/shared-ontology", follow_redirects=False)
    assert r.status_code == 200 and '<h1 id="shared-ontology">Shared ontology</h1>' in r.text


def test_the_redirects_are_the_ones_the_server_answers():
    assert pages.docs_redirects() == MOVED
    now = {x["path"] for x in pages.docs_pages()}
    for old, new in MOVED.items():
        assert old not in now and new.split("#")[0] in now


def test_every_old_anchor_lands_on_a_page_with_that_heading(client):
    where = pages.docs_anchors()
    for old in OLD:
        if old == "/docs":
            continue
        ids = [re.sub(r"[^a-z0-9]+", "-", old.rsplit("/", 1)[1])]
        if OLD[old] is None:                                  # renamed groups: the old heading's id
            ids = [old.rsplit("/", 1)[1]]
        for i in ids:
            if i == "why":                                    # /docs/why had no anchor of its own
                continue
            i = {"why-krusgraph": "why-choose-krusgraph", "reference": "tool-reference"}.get(i, i)
            assert i in where, i
            page = client.get(where[i]).text
            assert f'id="{i}"' in page or i in pages.DOCS_ANCHOR_ALIASES, i


def test_the_menu_has_six_groups_in_order(client):
    menu = re.search(r'<nav class="docs-menu"[^>]*>(.*?)</nav>', client.get("/docs").text, re.S).group(1)
    tops = re.findall(r'<a class="docs-group" href="[^"]+"[^>]*>([^<]+)</a>|<span class="docs-part-h">([^<]+)</span>', menu)
    labels = [a or b for a, b in tops]
    assert labels[0] == "Overview"
    assert [x for x in labels if x in GROUPS] == GROUPS
    run = menu[menu.index('<li class="docs-part">'):]
    order = [run.index(f'href="{p}"') for p in ("/docs/krusgraph-for-fabric", "/docs/hosting-and-permissions", "/docs/reference",
                                                 "/docs/support", "/docs/troubleshooting")]
    assert order == sorted(order)
    # "Which Krusgraph should I use?" is the first entry of Get started
    gs = menu[menu.index('href="/docs/get-started"'):menu.index('href="/docs/concepts"')]
    assert gs.index('href="/choose"') < gs.index('href="/docs/get-started/connect"')
    # Why: the manifesto, the eight points, Vision
    why = menu[menu.index('href="/docs/why"'):menu.index('href="/docs/get-started"')]
    assert why.index('href="/docs/why-krusgraph"') < why.index('href="/docs/why/vision"')


def test_the_groups_hold_the_pages_asked_for():
    ps = pages.docs_pages()
    by = lambda g: [x["title"] for x in ps if x["group"] == g and x["depth"] == 2]
    assert by("Why") == ["Why choose Krusgraph", "Vision"]
    assert by("How it works")[:3] == ["How it works", "How relationships are inferred", "How Krusgraph uses graph theory"]
    assert by("How it works")[3:] == ["Ontologies", "Data products", "How they connect", "Where it runs", "Sources", "SAP on Fabric"]
    assert by("Check") == ["Review, check, then create", "Keep your review", "Fix data issues"]
    assert by("Build") == ["One plan, five Fabric pieces", "Fabric IQ: the same graph as an ontology", "Shared ontology",
                           "Create a dbt flow", "Use with Lovable", "App access", "Databricks (Draft only)", "Two steps stay manual"]


# ------------------------------------------------------------------------------------------------ /docs/why, laid out

def _article(h: str) -> str:
    return h[h.index('<article class="prose docs">'):h.index("</article>")]


def test_the_manifesto_sections_in_order(client):
    art = _article(client.get("/docs/why").text)
    order = [art.index(f'class="mf-sec {c}"') for c in ("mf-hero", "mf-problem", "mf-do", "mf-quotes", "mf-eng", "mf-close")]
    assert order == sorted(order) and art.index('<h1 id="why-krusgraph">') < order[0] < art.index('class="mf-see"')
    assert '<p class="mf-turn">So we do it the other way around.</p>' in art
    cards = re.findall(r'<li class="mf-card"><span class="mf-num" aria-hidden="true">(\d)</span>'
                       r'<p class="mf-card-h"><strong>(.*?)</strong></p><p>(.*?)</p></li>', art)
    assert [n for n, _h, _t in cards] == ["1", "2", "3", "4", "5"] and '<ol class="mf-cards">' in art
    assert art.count('<p class="mf-quote">We believe ') == 2
    pairs = re.findall(r'<strong class="mf-left">(.*?)</strong> <span class="mf-right">(.*?)</span>', art)
    assert [_html.unescape(l) for l, _r in pairs] == ["Counting", "Evidence", '"I don\'t know"', "People decide,", "A dry run",
                                                       "Checking what was built", "Open rules"]
    assert art.count('class="mf-because"') == 7
    assert '<p class="mf-close-big"><strong>Know what&#x27;s true. Build what you need.</strong></p>' in art or \
        "<p class=\"mf-close-big\"><strong>Know what's true. Build what you need.</strong></p>" in art


def test_the_manifesto_keeps_its_words(client):
    """The page says exactly the words of DOCS.md, in the same order: the layout adds none and drops none."""
    md = pages.docs_md()
    md = md[md.index("<!-- figure:why-hero -->"):md.index("<!-- figure:why-see -->")]
    md = re.sub(r"<!--.*?-->", " ", md).replace("**", "")
    md = re.sub(r"^- ", "", md, flags=re.M)
    art = _article(client.get("/docs/why").text)
    art = art[art.index('<section class="mf-sec mf-hero">'):art.index('<nav class="mf-see"')]
    art = re.sub(r'<span class="mf-num" aria-hidden="true">\d</span>', " ", art)
    art = re.sub(r"<svg\b.*?</svg>", " ", art, flags=re.S)
    assert _text(art) == re.sub(r"\s+", " ", md).strip()
    assert "What we believe about data engineering" in _text(art)


def test_the_manifesto_css_uses_the_tokens_and_both_widths():
    css = (pages.STATIC_DIR / "site.css").read_text()
    block = css[css.index(".mf-sec{"):css.index(".mf-see{")]
    assert "var(--radius)" in block and "var(--card)" in block and "var(--coral" in block and "var(--font-head)" in block
    assert "grid-template-columns:1fr 1fr" in block                     # two columns of cards on a wide screen
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", block)                 # colours from the theme's tokens only (light and dark)
