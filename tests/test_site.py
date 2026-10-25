"""The public site: every page, the static files, the demo plan and the honesty rules the pages must keep."""
import json
import re

import pytest

from starlette.testclient import TestClient

from fabric_backend import infer, server
from fabric_backend.pages import PAGES


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    monkeypatch.delenv("COMPANY_ORGNR", raising=False)
    monkeypatch.delenv("PARTNER_SIGNIN", raising=False)
    with TestClient(server.build_app()) as c:
        yield c


ALL_PAGES = sorted(set(PAGES) | {"/docs", "/privacy"})


@pytest.mark.parametrize("path", ALL_PAGES)
def test_every_page_renders_with_title_description_and_footer(client, path):
    r = client.get(path)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert r.headers["cache-control"] == "public, max-age=300"
    html = r.text
    assert "{{" not in html and "{{/IF}}" not in html
    assert re.search(r"<title>[^<]{5,}</title>", html)
    assert re.search(r'<meta name="description" content="[^"]{20,}"', html)
    assert "Microsoft Fabric is a trademark of Microsoft Corporation" in html
    assert 'href="/static/site.css?v=' in html and "fonts/fredoka-var.woff2" in html
    assert "fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html
    for m in re.finditer(r'<(?:script|link|img)[^>]+(?:src|href)="([^"]+)"', html):     # no external resources at runtime
        assert not m.group(1).startswith(("http://", "https://", "//")), m.group(0)
    assert 'data-mascot-toggle' in html                                                  # the visible off switch
    # only descriptive use of Microsoft; no approval / listing / partner claims
    for banned in ("approved by Microsoft", "certified by Microsoft.</p>".replace("certified by Microsoft.</p>", "Microsoft partner"),
                   "listed in the Claude directory", "trusted by", "Microsoft Partner"):
        assert banned.lower() not in html.lower().replace("not affiliated with, endorsed by or certified by microsoft", ""), banned


def test_nav_and_pages_are_linked(client):
    html = client.get("/").text
    for href in ("/docs", "/support", "/partners", "/explore", "/start", "/privacy", "https://github.com/Krusmaster/fabric-backend"):
        assert f'href="{href}"' in html, href
    assert "Microsoft Fabric, connected." in html
    assert 'href="/mascots"' not in html                                                 # review page is unlinked


def test_home_carries_the_one_sentence_and_the_three_steps(client):
    html = client.get("/").text
    assert "Good things happen when data connects." in html
    assert "Turn your Microsoft Fabric tables into an explainable graph and a GraphQL API." in html
    assert 'href="/explore"' in html and "Explore the demo" in html and "How it works" in html
    for step in ("Discover", "Understand", "Create"):
        assert f"<h3>{step}</h3>" in html


def test_start_page_has_real_instructions_and_no_fake_sign_in(client):
    html = client.get("/start").text
    assert "Small steps. Useful connections." in html
    assert "https://krusgraph.test/mcp" in html
    assert "adminconsent?client_id=cid-123" in html
    assert "What will Krusgraph access?" in html and "GraphQLApi.ReadWrite.All" in html and "user_impersonation" in html
    assert "Continue with Microsoft" not in html
    for step in ("Connect your account", "Choose a workspace", "Open in Claude"):
        assert step in html


def test_support_page_shows_amounts_but_takes_no_payment(client):
    html = client.get("/support").text
    assert "Help good things keep happening." in html
    for amount in ("50 SEK", "150 SEK", "500 SEK"):
        assert amount in html
    assert "Contributions open soon." in html and "Get in touch" in html and "mailto:hello@krusgraph.test" in html
    assert "<form" not in html and "card number" not in html.lower()
    for card in ("Better examples", "Clearer docs", "Ongoing maintenance"):
        assert card in html


def test_partner_sign_in_button_only_with_flag(client, monkeypatch):
    html = client.get("/partners").text
    assert "Better connections. Built together." in html and 'href="/partners/workspace"' in html
    assert "Continue with Microsoft" not in html
    monkeypatch.setenv("PARTNER_SIGNIN", "1")
    html = client.get("/partners").text
    assert "Continue with Microsoft" in html and 'aria-disabled="true"' in html and "redirect URI" in html


def test_workspace_preview_is_labelled_illustrative(client):
    html = client.get("/partners/workspace").text
    assert "Illustrative workspace. No partner data connected." in html
    assert "Let’s build something useful." in html
    for step in ("Connect", "Explore", "Review", "Build"):
        assert f'>{step}</span>' in html
    assert "Next step" in html and 'href="/docs"' in html and "seed.py" in html


def test_mascot_review_page_is_noindex(client):
    r = client.get("/mascots")
    assert r.headers["x-robots-tag"] == "noindex, nofollow"
    assert '<meta name="robots" content="noindex,nofollow">' in r.text
    assert "Simulate success" in r.text and "Simulate failure" in r.text and "Accept" in r.text and "Skip" in r.text
    assert "no Fabric call is made" in r.text
    assert "Disallow: /mascots" in client.get("/robots.txt").text


def test_privacy_shows_org_nr_only_when_configured(client, monkeypatch):
    html = client.get("/privacy").text
    assert "org. nr" not in html and "Kruse Consulting AB, Sweden." in html
    assert "without a" in html and "log destination" in html and "zero logs" in html     # the honest logging text
    assert "no database" in html and "in memory" in html
    monkeypatch.setenv("COMPANY_ORGNR", "123456-7890")
    html = client.get("/privacy").text
    assert "Kruse Consulting AB, Sweden (org. nr 123456-7890)" in html
    assert "org. nr 123456-7890" in client.get("/").text                                # footer too


def test_docs_describe_the_data_path(client):
    html = client.get("/docs").text
    assert 'id="what-it-accesses"' in html and "held in memory only" in html and "no database" in html
    assert "https://krusgraph.test/mcp" in html and "client_id=cid-123" in html
    assert "<td><code>create_backend</code></td>" in html


@pytest.mark.parametrize("path,ctype", [("/static/site.css", "text/css"), ("/static/site.js", "text/javascript"),
                                        ("/static/mascots.js", "text/javascript"), ("/static/fonts/fredoka-var.woff2", "font/woff2"),
                                        ("/static/fonts/nunito-var.woff2", "font/woff2"), ("/static/favicon.svg", "image/svg+xml"),
                                        ("/static/favicon.png", "image/png"), ("/static/og.svg", "image/svg+xml"), ("/static/og.png", "image/png"),
                                        ("/static/fonts/OFL-Fredoka.txt", "text/plain")])
def test_static_files_are_served_with_cache_headers(client, path, ctype):
    r = client.get(path)
    assert r.status_code == 200 and r.headers["content-type"].startswith(ctype)
    assert r.headers["cache-control"] == "public, max-age=86400"
    assert client.get(path + "?v=abc").headers["cache-control"] == "public, max-age=31536000, immutable"


@pytest.mark.parametrize("path", ["/static/../pyproject.toml", "/static/fonts/../../server.py", "/static/", "/static/nope.css", "/static/site.css/"])
def test_static_refuses_traversal_and_unknown_files(client, path):
    assert client.get(path).status_code == 404


def test_demo_plan_is_the_real_engine_output(client):
    r = client.get("/demo/plan.json")
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=3600"
    d = r.json()
    assert d["engine"] == "fabric_backend.infer.plan" and d["label"] == "Illustrative demo"
    assert [t["name"] for t in d["tables"]] == ["customers", "categories", "products", "addresses", "orders", "order_items", "audit_log"]
    assert len(d["relationships"]) == 6 and d["keyless"] == ["audit_log"] and d["ambiguous"] == []
    assert {(r["source"], r["target"], r["rule"]) for r in d["relationships"]} == {
        ("products", "categories", "R1"), ("addresses", "customers", "R1"), ("orders", "customers", "R1"),
        ("order_items", "orders", "R1"), ("order_items", "products", "R1"), ("audit_log", "customers", "R1")}
    assert d["unlinked"] == [{"table": "orders", "column": "ship_to_id",
                              "note": "no rule matched: not named after another table, and not another table's key name"}]
    keys = {t["name"]: (t["key"], t["key_rule"]) for t in d["tables"]}
    assert keys["order_items"] == (["order_id", "line_no"], "K1") and keys["audit_log"] == ([], "K3")
    assert d["rules"] == infer.RULES
    # no real-looking data: the synthetic seed only
    text = json.dumps(d)
    assert "shop" in text and "@" not in text


def test_rule_wording_matches_the_engine_docstring():
    doc = infer.__doc__
    for code, text in infer.RULES.items():
        if code == "confirmed":
            continue
        assert text.split(" (")[0].split(" — ")[0] in doc, code


def test_mcp_and_oauth_routes_are_untouched(client):
    assert client.get("/healthz").json()["ok"] is True
    r = client.post("/mcp", json={})
    assert r.status_code in (400, 401, 406)                                              # the MCP endpoint still answers (bearer mode: no 401 gate)
