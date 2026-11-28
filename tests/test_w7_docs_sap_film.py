"""W7 (the founder, 24 November 2026): the SAP film of /sap is also on the docs' "SAP on Fabric" page, where he looked
for it. The same <video> as /sap (n242: controls, playsinline, preload="none", the poster, English captions on, an MP4
link as the fallback), the disclosure, and a link to /sap. /docs.md keeps a plain link to the film."""
import re

import pytest
from starlette.testclient import TestClient

from fabric_backend import pages, server

SAP_DOCS = "/docs/concepts/sap-on-fabric"            # DS1: in "How it works"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    with TestClient(server.build_app()) as c:
        yield c


def _video(html: str) -> str:
    return re.sub(r"\s+", " ", re.search(r"<video\b.*?</video>", html, re.S).group(0))


def _film(html: str) -> str:
    return re.search(r'<div class="sap-film-docs" id="sap-film">.*?</div>', html, re.S).group(0)


def test_the_sap_docs_page_is_where_the_menu_says():
    assert SAP_DOCS in [x["path"] for x in pages.docs_pages()]
    assert "sap-on-fabric" in pages.docs_anchors() and pages.docs_anchors()["sap-on-fabric"] == SAP_DOCS


def test_the_film_is_on_the_docs_sap_page_under_its_heading(client):
    html = client.get(SAP_DOCS).text
    assert html.count("<video") == 1
    assert html.index('<h1 id="sap-on-fabric">') < html.index('id="sap-film"') < html.index("SAP tables do not follow general naming rules")
    film = _film(html)
    assert '<a href="/sap">the SAP page</a>' in film
    for said in ("shown on our SAP-shaped example, not data from an SAP system", "Voice: AI-generated.",
                 "Krusgraph is independent and is not affiliated with SAP or Microsoft"):
        assert said in film, said
    assert "{{" not in film


def test_the_video_is_the_same_element_as_on_sap(client):
    docs, sap = _video(client.get(SAP_DOCS).text), _video(client.get("/sap").text)
    assert docs == sap
    for attr in ("controls", "playsinline", 'preload="none"', f'poster="{pages.SAP_FILM_POSTER}"'):
        assert attr in docs, attr
    assert f'<source src="{pages.SAP_FILM_MP4}" type="video/mp4">' in docs
    assert f'<track kind="captions" srclang="en" label="English" src="{pages.SAP_FILM_VTT}" default>' in docs
    assert f'<a href="{pages.SAP_FILM_MP4}">Download it as MP4</a>' in docs
    assert "autoplay" not in docs and "<iframe" not in client.get(SAP_DOCS).text


def test_the_files_behind_it_are_served(client):
    for path, kind in ((pages.SAP_FILM_MP4, "video/mp4"), (pages.SAP_FILM_POSTER, "image/webp"), (pages.SAP_FILM_VTT, "text/vtt")):
        r = client.get(path, headers={"Range": "bytes=0-1023"})
        assert r.status_code in (200, 206) and r.headers["content-type"].startswith(kind), path


def test_the_film_is_only_on_sap_and_its_docs_page(client):
    for x in pages.docs_pages():
        n = client.get(x["path"]).text.count("krusgraph-sap-to-report.mp4")
        assert (n > 0) == (x["path"] == SAP_DOCS), x["path"]


def test_the_page_description_is_its_first_paragraph_not_the_films_fallback(client):
    html = client.get(SAP_DOCS).text
    desc = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
    assert "cannot play this film" not in desc and "MP4" not in desc


def test_docs_md_links_the_film(client):
    md = client.get("/docs.md").text
    sec = md[md.index("### SAP on Fabric"):md.index("## Check")]                # DS1: SAP on Fabric closes "How it works"
    assert "[the SAP joining problem](/sap#sap-film)" in sec and "[the SAP page](/sap)" in sec


def test_the_frame_keeps_16_9_at_every_width():
    css = (pages.STATIC_DIR / "site.css").read_text(encoding="utf-8")
    rule = css[css.index(".sap-film-docs .sap-film-frame video{"):]
    assert "aspect-ratio:16/9" in rule.split("}", 1)[0]
    assert ".sap-film-docs .sap-film-frame{" in css and "max-width:100%" in css[css.index(".sap-film-docs .sap-film-frame{"):].split("}", 1)[0]
