"""n157: the overview film on the home page, directly after the hero.
A native <video> (controls, preload="none", playsinline, a poster, an English captions track), served from /static/media/
with the right types; nothing from another host; the masters stay out of the repository."""
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import pages, server

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "fabric_backend" / "static" / "media"
FILES = {"krusgraph-overview-web.mp4": "video/mp4", "krusgraph-overview-web-4x5.mp4": "video/mp4",   # n161: the 4:5 web version
         "krusgraph-overview-poster.webp": "image/webp",
         "krusgraph-overview.en.vtt": "text/vtt; charset=utf-8"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    with TestClient(server.build_app()) as c:
        yield c


def _film(html):
    return re.search(r'<section class="wrap film" id="film".*?</section>', html, re.S).group(0)


def test_the_film_section_follows_the_hero(client):
    html = client.get("/").text
    hero = re.search(r'<section class="hero">.*?</section>', html, re.S)
    film = html.index('<section class="wrap film" id="film"')
    assert hero.end() <= film < html.index('id="example"')
    assert html[hero.end():film].strip() == ""                       # nothing between the hero and the film
    assert "<video" not in hero.group(0)                             # the replay in the hero is untouched
    sec = _film(html)
    assert '<h2 id="film-h">See how it works</h2>' in sec
    assert "About 45 seconds" not in sec and "film-note" not in sec    # n160: the visible note is gone
    assert 'aria-label="Krusgraph overview film, synthetic demo data, AI-generated voice"' in sec


def test_the_video_element(client):
    sec = _film(client.get("/").text)
    video = re.search(r"<video([^>]*)>", sec).group(1)
    for attr in ("controls", 'preload="none"', "playsinline", 'poster="/static/media/krusgraph-overview-poster.webp"'):
        assert attr in video, attr
    assert "autoplay" not in video and "muted" not in video and "loop" not in video
    assert '<source src="/static/media/krusgraph-overview-web.mp4" type="video/mp4">' in sec
    track = re.search(r"<track([^>]*)>", sec).group(1)
    assert 'kind="captions"' in track and 'srclang="en"' in track and " default" in track
    assert 'src="/static/media/krusgraph-overview.en.vtt"' in track
    assert sec.count("<video") == 1 and client.get("/").text.count("<video") == 1


def test_no_external_url_in_the_film_section(client):
    sec = _film(client.get("/").text)
    urls = re.findall(r'(?:src|href|poster)="([^"]+)"', sec)
    assert urls and all(u.startswith("/static/media/") for u in urls), urls
    assert "http://" not in sec and "https://" not in sec and "//" not in sec.replace("://", "")
    assert not re.search(r"youtube|vimeo|iframe", sec, re.I)


def test_the_files_exist_and_are_small_enough():
    for name in FILES:
        assert (MEDIA / name).is_file(), name
    assert (MEDIA / "krusgraph-overview-web.mp4").stat().st_size < 8 * 1024 * 1024
    assert (MEDIA / "krusgraph-overview-poster.webp").stat().st_size < 150 * 1024
    vtt = (MEDIA / "krusgraph-overview.en.vtt").read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT") and vtt.count(" --> ") >= 10 and "Krusgraph, for Microsoft Fabric." in vtt
    head = (MEDIA / "krusgraph-overview-web.mp4").read_bytes()[:64 * 1024]
    assert 0 <= head.find(b"moov") < head.find(b"mdat") or (head.find(b"moov") >= 0 and head.find(b"mdat") < 0)  # faststart
    assert sorted(p.name for p in MEDIA.iterdir()) == sorted(FILES)   # only the web version; the masters stay out


def test_the_files_are_served_with_their_types(client):
    for name, ctype in FILES.items():
        r = client.get(f"/static/media/{name}")
        assert r.status_code == 200 and r.headers["content-type"] == ctype, name
        assert r.headers["x-content-type-options"] == "nosniff"
    r = client.get("/static/media/krusgraph-overview-web.mp4", headers={"Range": "bytes=0-1023"})
    assert r.status_code == 206 and len(r.content) == 1024           # range requests, which Safari needs for video


def test_the_policy_lets_the_film_load_from_the_site_only(client):
    csp = client.get("/").headers["content-security-policy"]
    assert csp.startswith("default-src 'self'") and "media-src" not in csp   # same-origin video and captions only
    assert "img-src 'self' data:" in csp                                     # the poster


def test_the_media_folder_is_packaged():
    assert '"static/media/*"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for ext in (".mp4", ".webp", ".vtt"):
        assert ext in pages.STATIC_TYPES


def _video_urls(html):
    return sorted(re.findall(r'(?:src|poster)="(/static/media/[^"]+)"', html))


def test_docs_landing_page_has_the_same_film_at_the_top(client):
    docs = client.get("/docs").text
    assert docs.count("<video") == 1
    film = re.search(r'<div class="film film-docs" id="film">.*?</figure>', docs, re.S).group(0)
    video = re.search(r"<video([^>]*)>", film).group(1)
    assert 'preload="none"' in video and "controls" in video and "playsinline" in video and 'poster="/static/media/' in video
    assert "autoplay" not in video and "muted" not in video
    track = re.search(r"<track([^>]*)>", film).group(1)
    assert 'kind="captions"' in track and 'srclang="en"' in track and " default" in track
    assert "About 45 seconds" not in film and "film-note" not in film  # n160: the visible note is gone
    assert 'aria-label="Krusgraph overview film, synthetic demo data, AI-generated voice"' in video
    article = docs[docs.index('<article class="prose docs">'):]
    assert article.index("<h1") < article.index('id="film"') < article.index("<h2")      # at the top, before the first section
    assert _video_urls(film) == _video_urls(_film(client.get("/").text))                  # the same files as the home page
    assert "<!--" not in film and "&lt;video" not in docs                                  # rendered by the directive, not escaped HTML


def test_docs_source_has_no_raw_html_for_the_film():
    md = (ROOT / "fabric_backend" / "page_templates" / "DOCS.md").read_text(encoding="utf-8")
    assert "<!-- figure:overview-film -->" in md and "<video" not in md


def test_the_film_is_not_on_the_blog_or_the_docs_sub_pages(client):
    assert "<video" not in client.get("/blog").text
    for post in pages.BLOG_POSTS:
        assert "<video" not in client.get(f"/blog/{post['slug']}").text
    sub = [p["path"] for p in pages.docs_pages() if p["path"] != "/docs"]
    assert sub and all("<video" not in client.get(p).text for p in sub[:6])
