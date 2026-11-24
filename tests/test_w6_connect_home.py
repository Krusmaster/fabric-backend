"""W6: the connector address on the home page, and the short address /connect.

The founder's request of 24 November 2026: the MCP connect address should be easy to find on the site. The home page's
hero shows it under the two buttons with a Copy button (the same copy row and data-copy as step 3 of /start) and one
line of how; the address follows /start exactly: /mcp/connect while client registration is on, /mcp while it is off, so
the page never shows an address that cannot sign in. /connect redirects to step 3 of /start; /mcp/connect, the OAuth
paths and the .well-known metadata are unchanged."""
import re

import pytest
from starlette.testclient import TestClient

from fabric_backend import server
from fabric_backend.pages import PAGES, REDIRECTS


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


def _hero_address(html: str) -> str:
    hero = re.search(r'<section class="hero">.*?</section>', html, re.S).group(0)
    return re.search(r'<div class="hero-connect" id="connect-address">(.*?)\n    </div>', hero, re.S).group(1)


def _start_address(html: str) -> str:
    return re.search(r'<div class="copy-row"><pre><code id="mcp-url">([^<]+)</code></pre>', html).group(1)


@pytest.mark.parametrize("registration", ["", "1"])
def test_the_home_hero_shows_the_same_address_as_start_with_a_copy_button(client, monkeypatch, registration):
    monkeypatch.setenv("KRUSGRAPH_CLIENT_REGISTRATION", registration)
    home, start = client.get("/").text, client.get("/start").text
    row = _hero_address(home)
    shown = re.search(r'<div class="copy-row"><pre><code id="connect-url">([^<]+)</code></pre>'
                      r'<button type="button" class="btn ghost small" data-copy="#connect-url">Copy</button></div>', row)
    assert shown, row
    expected = "https://krusgraph.test/mcp/connect" if registration else "https://krusgraph.test/mcp"
    assert shown.group(1) == expected == _start_address(start)                      # never an address /start does not give
    how = re.sub(r"<[^>]+>", "", re.search(r'<p class="muted tiny">(.*?)</p>', row, re.S).group(1))
    assert how.startswith("In Claude: Customize → Connectors → Add custom connector")
    assert ("Register automatically" in how) == bool(registration)                 # as step 3 of /start says it
    assert how.endswith("Other clients: set-up guide.") and '<a href="/start#step-3">set-up guide</a>' in row
    assert home.count('id="connect-url"') == 1 and home.count('id="connect-address"') == 1


def test_the_buttons_stay_and_the_address_follows_them(client):
    html = client.get("/").text
    hero = re.search(r'<section class="hero">.*?</section>', html, re.S).group(0)
    ctas = re.search(r'<div class="ctas hero-ctas" id="connect">(.*?)</div>', hero, re.S).group(1)
    assert re.findall(r'href="([^"]+)"', ctas) == ["/check", "/start"]
    assert hero.index("hero-ctas") < hero.index('id="connect-address"') < hero.index('id="film"')


def test_the_copy_script_and_style_are_the_shared_ones():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "fabric_backend" / "static"
    assert "querySelectorAll('[data-copy],[data-copy-text]')" in (root / "site.js").read_text(encoding="utf-8")
    css = (root / "site.css").read_text(encoding="utf-8")
    assert ".copy-row{" in css and ".hero-connect .copy-row{" in css


def test_connect_redirects_to_step_3_of_start(client):
    r = client.get("/connect", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/start#step-3"
    assert 'data-pane="3" id="step-3"' in client.get("/start").text                # the anchor site.js opens


def test_connect_does_not_touch_mcp_connect_or_the_metadata(client):
    assert "/connect" not in PAGES and REDIRECTS["/connect"] == "/start#step-3"
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "fabric_backend" / "server.py").read_text(encoding="utf-8")
    assert not re.search(r'Route\("/connect\b', src) and not re.search(r'Mount\("/connect\b', src)   # only the redirect
    assert client.get("/mcp/connect", follow_redirects=False).status_code != 301    # the MCP endpoint, not the redirect
    assert client.get("/connect/x", follow_redirects=False).status_code == 404       # the exact path only
