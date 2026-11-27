"""ON3 (26 November 2026): the docs page "Shared ontology" explains one shared Fabric IQ ontology over SAP and Dynamics
365 (rounds ON1 and ON2), with the approved film at the top. It is a "###" page of DOCS.md under "Build from a plan",
so the docs index links it; the film is a native <video> with the poster and an English captions track (the film's
own captions are burned in), and the line under it says the example is synthetic and the voice and music AI-generated. The numbers on the page are the ones the ON1 and
ON2 tests assert on the synthetic pair, and the status section says what was tested and what was not."""
import html as _html
import re

import pytest
from fixtures import sap_dynamics as sd
from starlette.testclient import TestClient

from fabric_backend import pages, server

PAGE = "/docs/build-from-a-plan/shared-ontology"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    with TestClient(server.build_app()) as c:
        yield c


def _article(html: str) -> str:
    return html[html.index('<article class="prose docs">'):html.index("</article>")]


def _text(html: str) -> str:
    html = re.sub(r"<video\b.*?</video>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).replace("&amp;", "&")


def test_the_page_renders_under_build_from_a_plan(client):
    assert PAGE in [x["path"] for x in pages.docs_pages()]
    r = client.get(PAGE)
    assert r.status_code == 200
    assert '<h1 id="shared-ontology">Shared ontology</h1>' in r.text
    assert "<title>Shared ontology — Krusgraph docs</title>" in r.text
    desc = re.search(r'<meta name="description" content="([^"]*)"', r.text).group(1)
    assert desc.startswith("One shared Fabric IQ ontology over SAP and Dynamics 365")


def test_the_docs_index_links_it(client):
    index = client.get("/docs").text
    kids = re.search(r'<nav class="docs-children" aria-label="All docs pages">(.*?)</nav>', index, re.S).group(1)
    assert f'<a href="{PAGE}">Shared ontology</a>' in kids
    group = client.get("/docs/build-from-a-plan").text
    assert f'<a href="{PAGE}">Shared ontology</a>' in group
    assert pages.docs_anchors()["shared-ontology"] == PAGE


def test_the_film_is_at_the_top_with_its_poster_track_and_note(client):
    html = client.get(PAGE).text
    art = _article(html)
    assert art.count("<video") == 1
    assert art.index('<h1 id="shared-ontology">') < art.index("<video") < art.index("<p>One shared Fabric IQ ontology")
    video = re.search(r"<video\b[^>]*>", art).group(0)
    for attr in ("controls", 'preload="metadata"', "playsinline", f'poster="{pages.SHARED_FILM_POSTER}"'):
        assert attr in video, attr
    assert "autoplay" not in video and "muted" not in video
    assert f'<source src="{pages.SHARED_FILM_MP4}" type="video/mp4">' in art
    # the film has its captions burned in; the track is offered, not on by default (on, Chromium drew each line twice)
    assert f'<track kind="captions" srclang="en" label="English" src="{pages.SHARED_FILM_VTT}">' in art
    assert '<figcaption class="muted tiny so-film-note">Synthetic example. Voice and music are AI-generated.</figcaption>' in art
    assert "<iframe" not in html


def test_the_film_files_are_served_from_static_media(client):
    for path, kind in ((pages.SHARED_FILM_MP4, "video/mp4"), (pages.SHARED_FILM_POSTER, "image/webp"),
                       (pages.SHARED_FILM_VTT, "text/vtt")):
        r = client.get(path, headers={"Range": "bytes=0-1023"})
        assert r.status_code in (200, 206) and r.headers["content-type"].startswith(kind), path
    vtt = client.get(pages.SHARED_FILM_VTT).text
    assert vtt.startswith("WEBVTT\n") and vtt.count(" --> ") == 6 and "," not in "".join(re.findall(r"[\d:.,]+ --> [\d:.,]+", vtt))
    assert "Nothing is created without your yes." in vtt


def test_same_origin_media_is_allowed_by_the_pages_policy(client):
    csp = client.get(PAGE).headers["content-security-policy"]
    assert "default-src 'self'" in csp and "media-src" not in csp            # media falls back to 'self'


def test_the_film_is_only_on_this_page(client):
    for x in pages.docs_pages():
        n = client.get(x["path"]).text.count("krusgraph-shared-ontology.mp4")
        assert (n > 0) == (x["path"] == PAGE), x["path"]


def test_the_diagram_shows_the_gold_and_the_ontology(client):
    art = _article(client.get(PAGE).text)
    fig = re.search(r'<figure class="so-fig" id="shared-gold-figure">.*?</figure>', art, re.S).group(0)
    for said in ("dim_customer</code> (9 rows)", "dim_product</code> (5 rows)", "xref_customer", "xref_product",
                 "fact_sap_sales_order", "fact_d365_opportunity", "9 entity types, 7 relationship types",
                 "fails the run"):
        assert said in fig, said
    css = (pages.STATIC_DIR / "site.css").read_text(encoding="utf-8")
    for rule in (".so-fig{", ".so-srcs{", "@media (max-width:560px){.so-srcs{grid-template-columns:1fr}"):
        assert rule in css, rule
    assert "aspect-ratio:16/9" in css[css.index(".so-film-frame video{"):].split("}", 1)[0]


def test_the_numbers_are_the_ones_the_tests_assert():
    c, p = sd.EXPECTED["customer"]["counts"], sd.EXPECTED["product"]["counts"]
    assert (c["matched"], c["ambiguous"], c["only_b"], c["only_a"]) == (3, 2, 2, 1)     # only_b: only in SAP
    assert (p["matched"], p["ambiguous"], p["only_b"], p["only_a"]) == (2, 0, 2, 1)
    assert (c["found_raw"], c["found"]) == (2, 5)
    md = pages.docs_md()
    sec = md[md.index("### Shared ontology"):md.index("### Two steps stay manual")]
    assert "| Customer: `account.accountnumber` → `KNA1.KUNNR` | M2 | 3 | 2 | 2 | 1 |" in sec
    assert "| Product: `product.productnumber` → `MARA.MATNR` | M2 | 2 | 0 | 2 | 1 |" in sec
    for said in ("`dim_customer` 9 rows and `dim_product` 5 rows", "9 entity types and 7\nrelationship types",
                 "at least\n95 % of the filled values", "Two account numbers match as written, five\nafter normalising"):
        assert said in sec, said


def test_the_status_section_says_what_was_tested_and_what_was_not(client):
    art = _article(client.get(PAGE).text)
    assert '<h2 id="status">Status</h2>' in art
    status = _text(art[art.index('<h2 id="status">'):art.index('<h2 id="the-calls-in-order">')])
    for said in ("Unit-tested on synthetic data only", "Not yet run against a live Fabric tenant (26 November 2026)",
                 "Fabric IQ's ontology is a preview feature in Fabric",
                 "A person builds the ontology's graph in Fabric",
                 "Not built yet: the combined semantic model", "Order and Invoice across sources",
                 "filtered lookups as relationships", "Business Central counted on rows"):
        assert said in status, said
    assert 'href="/docs/reference/test-status#test-status"' in art


def test_the_calls_are_the_real_tools_and_arguments(client):
    import inspect
    art = _article(client.get(PAGE).text)
    code = re.search(r'<h2 id="the-calls-in-order">.*?<pre tabindex="0"><code>(.*?)</code></pre>', art, re.S).group(1)
    code = _html.unescape(code)
    calls = re.findall(r"^(\w+)\((.*?)\)$", code.replace("\n      ", " ").replace("\n        ", " "), re.M)
    assert [t for t, _ in calls] == ["start", "start", "create_pipeline", "create_pipeline", "create_ontology",
                                     "create_ontology", "verify_build"]
    for tool, args in calls:
        params = set(inspect.signature(getattr(server, tool)).parameters)
        for name in re.findall(r"(?:^|, )(\w+)=", args):
            assert name in params, (tool, name)
    assert sd.CUSTOMER in code and sd.PRODUCT in code and 'schema="sap+d365"' in code


def test_the_footer_line_and_no_sales_words(client):
    text = _text(_article(client.get(PAGE).text))
    assert ("Krusgraph is independent and not affiliated with SAP or Microsoft. Dynamics 365, Microsoft Fabric and "
            "Fabric IQ are trademarks of Microsoft.") in text
    from test_site import SALES
    low = client.get(PAGE).text.lower()
    assert not [w for w in SALES if w in low]
    for w in ("partner", "certified", "endorsed", "unique", "guarantee"):
        assert w not in text.lower(), w
