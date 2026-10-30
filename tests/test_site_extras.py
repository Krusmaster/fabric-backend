"""404 page, sitemap, robots and the text rendering of the plan."""
import pytest

from starlette.testclient import TestClient

from fabric_backend import server


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    with TestClient(server.build_app()) as c:
        yield c


def test_browser_404_is_styled_and_noindex(client):
    r = client.get("/no-such-page", headers={"Accept": "text/html,application/xhtml+xml"})
    assert r.status_code == 404 and r.headers["x-robots-tag"] == "noindex"
    assert "Nothing connects here." in r.text and "/no-such-page" in r.text and 'href="/explore"' in r.text
    assert 'content="noindex,nofollow"' in r.text and "{{" not in r.text
    assert "&lt;" in client.get("/<script>alert(1)</script>", headers={"Accept": "text/html"}).text        # path is escaped


def test_pages_carry_a_strict_csp_but_mcp_does_not(client):
    for path in ("/", "/demo", "/explore", "/docs", "/privacy", "/mascots"):
        h = client.get(path).headers
        assert h["content-security-policy"].startswith("default-src 'self'; script-src 'self' 'sha256-"), path
        assert h["x-content-type-options"] == "nosniff" and h["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "content-security-policy" in client.get("/nope", headers={"Accept": "text/html"}).headers
    assert "content-security-policy" not in client.post("/mcp", json={}).headers
    assert "content-security-policy" not in client.get("/demo/plan.json").headers


def test_every_response_carries_hsts_and_nosniff(client):
    """Site, static files, JSON, health and the MCP endpoint alike; the page CSP stays page-only."""
    for path, method in (("/", "GET"), ("/static/site.css", "GET"), ("/demo/plan.json", "GET"), ("/healthz", "GET"),
                         ("/nope", "GET"), ("/mcp", "POST"), ("/sitemap.xml", "GET")):
        h = (client.post(path, json={}) if method == "POST" else client.get(path)).headers
        assert h["strict-transport-security"] == "max-age=31536000", path
        assert h["x-content-type-options"] == "nosniff", path


def test_site_responses_gzip_when_asked_and_mcp_never_does(client):
    import gzip
    for path, ctype in (("/", "text/html"), ("/static/site.css", "text/css"), ("/demo/plan.json", "application/json")):
        r = client.get(path, headers={"Accept-Encoding": "gzip"})
        assert r.status_code == 200 and r.headers.get("content-encoding") == "gzip" and r.headers["vary"] == "Accept-Encoding", path
        assert r.headers["content-type"].startswith(ctype)
        assert r.text.startswith(("<!doctype html>", "/*", "{"))                        # the test client transparently inflates
        plain = client.get(path, headers={"Accept-Encoding": "identity"})
        assert "content-encoding" not in plain.headers and plain.text == r.text
    assert "content-encoding" not in client.get("/static/fonts/fredoka-var.woff2", headers={"Accept-Encoding": "gzip"}).headers
    assert "content-encoding" not in client.post("/mcp", json={}, headers={"Accept-Encoding": "gzip"}).headers
    raw = client.get("/static/site.css", headers={"Accept-Encoding": "gzip"})
    assert gzip.decompress(raw.content).startswith(b"/*") if raw.headers.get("content-encoding") == "gzip" and raw.content[:2] == b"\x1f\x8b" else True


def test_non_browser_404_stays_plain(client):
    r = client.get("/no-such-page", headers={"Accept": "application/json"})
    assert r.status_code == 404 and r.text == "not found"
    assert client.post("/no-such-page", headers={"Accept": "text/html"}).status_code in (404, 405)


def test_sitemap_and_robots(client):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    for p in ("/", "/demo", "/explore", "/start", "/support", "/partners", "/partners/workspace", "/docs", "/privacy"):
        assert f"<loc>https://krusgraph.test{p}</loc>" in r.text
    assert "/mascots" not in r.text
    robots = client.get("/robots.txt").text
    assert "Sitemap: https://krusgraph.test/sitemap.xml" in robots and "Disallow: /mascots" in robots


def test_explore_has_the_plan_as_text(client):
    html = client.get("/explore").text
    assert "The plan as text" in html and 'id="plan-text"' in html
    assert "7 tables, 6 with keys, 6 relationships" in html
    assert "<strong>audit_log</strong>: no key, <code>K3</code>" in html
    assert "<code>orders.customer_id</code> → <code>customers.customer_id</code>, <code>R1</code>" in html
    text = html.split('id="plan-text"', 1)[1].split("</details>", 1)[0]
    from fabric_backend.infer import RULES
    for code in ("K1", "K2", "K3", "R1"):                                 # each rule explained once, then only its code
        assert text.count(RULES[code].replace("`", "")[:40]) <= 1 and f"<dt><code>{code}</code></dt>" in text
    assert "<code>orders.ship_to_id</code>: no rule matched" in html
    assert 'aria-label="Tables and legend"' in html and 'aria-label="Why these tables are linked"' in html


def test_heading_order_starts_at_h2_after_the_h1(client):
    import re
    for path in ("/start", "/partners", "/", "/demo"):
        html = client.get(path).text
        levels = [int(m) for m in re.findall(r"<h([1-3])[ >]", html.split("<main", 1)[1].split("</main>")[0])]
        for a, b in zip(levels, levels[1:]):
            assert b <= a + 1, (path, levels)


def test_oversized_bodies_are_refused_before_they_are_read():
    """The wrapper looks at Content-Length only; a client announcing a huge body gets 413 and nothing is read."""
    import asyncio
    from fabric_backend import server
    app = server.build_app()
    sent = []

    async def receive():
        pytest.fail("the body must not be read")

    async def send(message):
        sent.append(message)
    scope = {"type": "http", "method": "POST", "path": "/mcp", "headers": [(b"content-length", str(server.MAX_BODY_BYTES + 1).encode()),
                                                                           (b"content-type", b"application/json")],
             "query_string": b"", "scheme": "http", "server": ("testserver", 80), "client": ("127.0.0.1", 1), "http_version": "1.1"}
    asyncio.run(app(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    assert start["status"] == 413
    headers = {k.decode(): v.decode() for k, v in start["headers"]}
    assert headers["strict-transport-security"] == "max-age=31536000"


def test_the_theme_script_is_the_one_inline_script_and_the_csp_allows_it_by_hash(client):
    import base64, hashlib, re
    from fabric_backend.pages import THEME_JS
    digest = "'sha256-" + base64.b64encode(hashlib.sha256(THEME_JS.encode()).digest()).decode() + "'"
    for path in ("/", "/check", "/use-cases"):
        r = client.get(path)
        inline = re.findall(r"<script>(.*?)</script>", r.text, re.S)
        assert inline == [THEME_JS], path
        assert r.text.index("<script>") < r.text.index('rel="stylesheet"'), path        # before the CSS: no flash
        csp = r.headers["content-security-policy"]
        assert digest in csp and "unsafe-inline" not in csp.split("script-src")[1].split(";")[0], path
        assert 'data-theme-toggle aria-pressed="false" aria-label="Dark theme"' in r.text, path
