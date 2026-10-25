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
    for path in ("/", "/explore", "/docs", "/privacy", "/mascots"):
        h = client.get(path).headers
        assert h["content-security-policy"].startswith("default-src 'self'; script-src 'self';"), path
        assert h["x-content-type-options"] == "nosniff" and h["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "content-security-policy" in client.get("/nope", headers={"Accept": "text/html"}).headers
    assert "content-security-policy" not in client.post("/mcp", json={}).headers
    assert "content-security-policy" not in client.get("/demo/plan.json").headers


def test_non_browser_404_stays_plain(client):
    r = client.get("/no-such-page", headers={"Accept": "application/json"})
    assert r.status_code == 404 and r.text == "not found"
    assert client.post("/no-such-page", headers={"Accept": "text/html"}).status_code in (404, 405)


def test_sitemap_and_robots(client):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    for p in ("/", "/explore", "/start", "/support", "/partners", "/partners/workspace", "/docs", "/privacy"):
        assert f"<loc>https://krusgraph.test{p}</loc>" in r.text
    assert "/mascots" not in r.text
    robots = client.get("/robots.txt").text
    assert "Sitemap: https://krusgraph.test/sitemap.xml" in robots and "Disallow: /mascots" in robots


def test_explore_has_the_plan_as_text(client):
    html = client.get("/explore").text
    assert "The plan as text" in html and 'id="plan-text"' in html
    assert "7 tables, 6 with keys, 6 relationships" in html
    assert "<strong>audit_log</strong>: no key, rule <code>K3</code>" in html
    assert "<code>orders.customer_id</code> → <code>customers.customer_id</code> by rule <code>R1</code>" in html
    assert "<code>orders.ship_to_id</code>: no rule matched" in html
    assert 'aria-label="Tables and legend"' in html and 'aria-label="Why this connection"' in html


def test_heading_order_starts_at_h2_after_the_h1(client):
    import re
    for path in ("/start", "/partners"):
        html = client.get(path).text
        levels = [int(m) for m in re.findall(r"<h([1-3])[ >]", html.split("<main", 1)[1].split("</main>")[0])]
        for a, b in zip(levels, levels[1:]):
            assert b <= a + 1, (path, levels)
