"""n161: the overview film adapts to the device. Phones (max-width 640 px) get the 4:5 web version through the first
<source>, larger screens the 16:9 one; on the home page and on /docs. One shared captions track (the two formats carry
the same narration with the same timing) and one poster (16:9; a poster cannot be swapped without script). n160's
aria-label and the rest of n157 stay: preload="none", controls, playsinline, no autoplay, nothing from another host."""
import json
import re
import subprocess

import pytest

from fabric_backend import pages
from tests.test_site import client  # noqa: F401  (the site's test client)
from test_browser import CHROMIUM, ROOT, _playwright_available, site  # noqa: F401

MEDIA = ROOT / "fabric_backend" / "static" / "media"
CSS = (ROOT / "fabric_backend" / "static" / "site.css").read_text(encoding="utf-8")
PHONE = '<source media="(max-width: 640px)" src="/static/media/krusgraph-overview-web-4x5.mp4" type="video/mp4">'
WIDE = '<source src="/static/media/krusgraph-overview-web.mp4" type="video/mp4">'


@pytest.mark.parametrize("path", ["/docs"])                  # n190: the film left the home page
def test_both_sources_with_the_phone_query_first(client, path):
    html = client.get(path).text
    video = re.search(r"<video[^>]*>.*?</video>", html, re.S).group(0)
    assert video.count("<source") == 2 and PHONE in video and WIDE in video
    assert video.index(PHONE) < video.index(WIDE)                         # the browser takes the first source that matches
    head = re.search(r"<video([^>]*)>", video).group(1)
    for attr in ('preload="none"', "controls", "playsinline", 'poster="/static/media/krusgraph-overview-poster.webp"',
                 f'aria-label="{pages.FILM_LABEL}"'):
        assert attr in head, attr
    assert "autoplay" not in head and "muted" not in head
    assert video.count("<track") == 1 and 'src="/static/media/krusgraph-overview.en.vtt"' in video   # one shared track
    assert all(u.startswith("/static/media/") for u in re.findall(r'(?:src|poster|href)="([^"]+)"', video))


def test_the_css_breakpoint_matches_the_source_query():
    assert pages.FILM_PHONE == "(max-width: 640px)"
    assert "@media (max-width:640px){.film-frame video{aspect-ratio:4/5;object-fit:cover}}" in CSS


def test_the_files_exist_and_are_small_enough():
    for name in ("krusgraph-overview-web.mp4", "krusgraph-overview-web-4x5.mp4"):
        f = MEDIA / name
        assert f.is_file() and f.stat().st_size < 8 * 1024 * 1024, name
        head = f.read_bytes()[:64 * 1024]
        assert 0 <= head.find(b"moov") < head.find(b"mdat") or (head.find(b"moov") >= 0 and head.find(b"mdat") < 0), name
    assert (MEDIA / "krusgraph-overview-web-4x5.mp4").stat().st_size < 4 * 1024 * 1024    # the target for the phone file


def test_the_phone_file_is_served(client):
    r = client.get("/static/media/krusgraph-overview-web-4x5.mp4")
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"
    r = client.get("/static/media/krusgraph-overview-web-4x5.mp4", headers={"Range": "bytes=0-1023"})
    assert r.status_code == 206 and len(r.content) == 1024


@pytest.mark.skipif(not _playwright_available(), reason="node + playwright not available")
def test_in_a_browser_phones_pick_4x5_and_larger_screens_16x9(site):
    out = subprocess.run(["node", str(ROOT / "tests" / "n161_film_browser.js"), site] + ([CHROMIUM] if CHROMIUM else []),
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    r = json.loads(out.stdout.strip().splitlines()[-1])
    assert r["errors"] == []
    four_five, sixteen_nine = "/static/media/krusgraph-overview-web-4x5.mp4", "/static/media/krusgraph-overview-web.mp4"
    for path in ("/docs",):
        phone, wide = r[f"375 {path}"], r[f"1280 {path}"]
        assert phone["queryMatches"] and not wide["queryMatches"] and phone["ratio"] == 0.8 and wide["ratio"] == 1.78
        # n163: where the browser honours media on <source> (current Chromium, Firefox, Safari) a phone gets the 4:5
        # file; where it does not (the older Chromium of CI's Playwright), the page still plays the 16:9 one
        assert phone["src"] == (four_five if phone["mediaHonoured"] else sixteen_nine), phone
        assert wide["src"] == sixteen_nine, wide
        assert not phone["overflow"] and not wide["overflow"] and phone["external"] == 0 and wide["external"] == 0
