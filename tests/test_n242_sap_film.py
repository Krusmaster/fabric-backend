"""n242: the approved SAP film on /sap, under the page's heading. Self-hosted like the home page's film: a native
<video> with controls, playsinline and preload="none" (nothing downloads before play), a poster, an English captions
track on by default, 16:9 with no layout shift, and nothing from another host."""
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import server

MEDIA = Path(__file__).resolve().parents[1] / "fabric_backend" / "static" / "media"
MP4 = "/static/media/krusgraph-sap-to-report.mp4"
POSTER = "/static/media/krusgraph-sap-to-report-poster.webp"
VTT = "/static/media/krusgraph-sap-to-report.en.vtt"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    with TestClient(server.build_app()) as c:
        yield c


def _section(html):
    return re.search(r'<section class="wrap sap-film" id="sap-film".*?</section>', html, re.S).group(0)


def test_sap_page_renders_with_the_film_under_the_heading(client):
    r = client.get("/sap")
    assert r.status_code == 200
    html = r.text
    assert html.index("<h1>") < html.index('id="sap-film"') < html.index('id="sap-keys-h"')
    sec = _section(html)
    assert "The SAP joining problem. Krusgraph does the trick!" in sec
    assert "Shown on our SAP-shaped example, not data from an SAP system. Voice: AI-generated." in sec
    assert "Krusgraph is independent and is not affiliated with SAP or Microsoft" in sec


def test_video_element_preload_none_and_no_autoplay(client):
    sec = _section(client.get("/sap").text)
    video = re.search(r"<video\b[^>]*>", sec).group(0)
    for attr in ("controls", "playsinline", 'preload="none"', f'poster="{POSTER}"'):
        assert attr in video, attr
    assert "autoplay" not in sec and "<iframe" not in sec and "youtube" not in sec.lower()
    assert f'<source src="{MP4}" type="video/mp4">' in sec
    assert "aspect-ratio:16/9" in client.get("/sap").text and "max-width:880px" in client.get("/sap").text


def test_captions_track_is_english_and_default(client):
    sec = _section(client.get("/sap").text)
    track = re.search(r"<track\b[^>]*>", sec).group(0)
    for attr in ('kind="captions"', 'srclang="en"', f'src="{VTT}"', "default"):
        assert attr in track, attr
    r = client.get(VTT)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/vtt")
    cues = re.findall(r"^\d\d:\d\d:\d\d\.\d{3} --> \d\d:\d\d:\d\d\.\d{3}$", r.text, re.M)
    assert r.text.startswith("WEBVTT") and len(cues) >= 10
    assert "32 of 34 links hold" in r.text


def test_media_files_are_served_and_sane(client):
    for path, kind in ((MP4, "video/mp4"), (POSTER, "image/webp")):
        r = client.get(path, headers={"Range": "bytes=0-1023"})
        assert r.status_code in (200, 206) and r.headers["content-type"].startswith(kind), path
    assert (MEDIA / "krusgraph-sap-to-report.mp4").stat().st_size < 4 * 1024 * 1024
    assert (MEDIA / "krusgraph-sap-to-report-poster.webp").stat().st_size < 150 * 1024


def test_no_forbidden_wording_on_the_sap_page(client):
    text = client.get("/sap").text.lower()
    for s in ("sap-certified", "sap-compatible", "works with claude", "certified", "partnership", "endorsed"):
        assert s not in text, s
