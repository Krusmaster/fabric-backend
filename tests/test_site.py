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


ALL_PAGES = sorted(set(PAGES) | {"/docs", "/privacy", "/lovable"})


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
        if m.group(0).startswith('<link rel="canonical"'):                               # a URL, not something loaded
            continue
        assert not m.group(1).startswith(("http://", "https://", "//")), m.group(0)
    assert 'data-mascot-toggle' in html                                                  # the visible off switch
    # only descriptive use of Microsoft; no approval / listing / partner claims
    for banned in ("approved by Microsoft", "Microsoft partner", "listed in the Claude directory", "trusted by", "Microsoft Partner"):
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
    assert "not registered on the Entra app yet" in html                                   # no claim that Claude Code sign-in works today
    assert "Tested with" not in html and "tested with" not in html                          # the Claude end-to-end test is still on the to-do list
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
    for code, text in infer.RULES.items():                                                 # the rules table comes from the engine
        if code != "confirmed":
            assert f"<td>{code}</td>" in html, code
    assert "<code>keys</code> override from the caller" in html


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


@pytest.mark.parametrize("path", ["/static/../pyproject.toml", "/static/fonts/../../server.py", "/static/", "/static/nope.css", "/static/site.css/",
                                  "/static/%00", "/static/a%00b.css", "/static/" + "x" * 300 + ".css", "/static/" + "y" * 100 + "/" + "z" * 150 + ".css"])
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
    assert d["suggestions"] == [{"table": "orders", "column": "ship_to_id", "target": "addresses", "target_cols": ["address_id"],
                                 "source": "demo hint, not inferred", "why": "the synthetic seed stores address ids in this column"}]
    # no real-looking data: the synthetic seed only
    text = json.dumps(d)
    assert "shop" in text and "@" not in text


def test_rule_wording_matches_the_engine_docstring():
    doc = infer.__doc__
    for code, text in infer.RULES.items():
        if code == "confirmed":
            continue
        assert text.split(" (")[0].split(" — ")[0] in doc, code


def test_operator_values_are_escaped_in_templates(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "A&B <x>")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", 'me"@krusgraph.test')
    with TestClient(server.build_app()) as c:
        for path in ("/", "/support", "/docs", "/privacy"):
            html = c.get(path).text
            assert "<x>" not in html and "A&amp;B &lt;x&gt;" in html, path
        for path in ("/", "/support"):                                                   # templates: attribute-safe too
            html = c.get(path).text
            assert 'me"@' not in html and "me&quot;@" in html, path
        assert "subject=Supporting%20A%26B%20%3Cx%3E" in c.get("/support").text


def test_mcp_and_oauth_routes_are_untouched(client, monkeypatch):
    assert client.get("/healthz").json()["ok"] is True
    assert "build" not in client.get("/healthz").json()
    monkeypatch.setenv("KRUSGRAPH_BUILD", "src-0123456789abcdef")
    assert client.get("/healthz").json()["build"] == "src-0123456789abcdef"
    r = client.post("/mcp", json={})
    assert r.status_code in (400, 401, 406)                                              # the MCP endpoint still answers (bearer mode: no 401 gate)


def test_explore_table_list_names_keys_in_words_with_the_rule_as_tooltip(client):
    html = client.get("/explore").text
    assert 'data-table="order_items"' in html and ">composite key</span>" in html and ">no key</span>" in html
    assert '<span class="rule">K' not in html                                            # no bare K1/K2/K3 codes
    assert 'title="Rule K1: ' in html and 'title="Rule K3: ' in html
    assert 'class="t-ico c-coral"' in html and 'class="t-ico c-mustard"' in html          # coloured table icons
    assert "kicker" not in html


def test_home_hero_and_trust_row(client):
    html = client.get("/").text
    assert 'class="kicker"' not in html                                                  # no all-caps eyebrows
    assert 'class="hero-figure"' not in html and 'id="home-graph"' in html               # mascots live on the graph's wires
    assert 'class="trust"' in html and "Your permissions, not ours" in html and "Nothing stored" in html
    assert "Illustrative demo" in html


# ------------------------------------------------------------------ SEO and agent discovery ---------------------

PUBLIC = ["/", "/explore", "/start", "/docs", "/lovable", "/privacy", "/support", "/partners", "/partners/workspace"]


def test_every_public_page_has_canonical_open_graph_and_twitter_tags(client):
    titles = set()
    for path in PUBLIC:
        html = client.get(path).text
        assert '<html lang="en">' in html
        canonical = "https://krusgraph.test" + path
        assert f'<link rel="canonical" href="{canonical}">' in html, path
        assert f'<meta property="og:url" content="{canonical}">' in html, path
        assert '<meta property="og:image" content="https://krusgraph.test/static/og.png">' in html
        assert '<meta name="twitter:card" content="summary_large_image">' in html
        assert '<meta name="twitter:image" content="https://krusgraph.test/static/og.png">' in html
        assert re.search(r'<meta name="twitter:title" content="[^"]{5,}">', html)
        assert 'content="noindex' not in html, path
        titles.add(re.search(r"<title>([^<]+)</title>", html).group(1))
    assert len(titles) == len(PUBLIC)                                                     # every title is unique


def test_json_ld_on_home_only_and_only_facts(client):
    html = client.get("/").text
    blocks = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
    app = next(b for b in blocks if b["@type"] == "SoftwareApplication")
    org = next(b for b in blocks if b["@type"] == "Organization")
    assert app["name"] == "Krusgraph" and app["applicationCategory"] == "DeveloperApplication" and app["operatingSystem"] == "Web"
    assert app["offers"]["price"] == "0" and "MIT" in app["offers"]["description"]
    assert app["url"] == "https://krusgraph.test/" and "https://github.com/Krusmaster/fabric-backend" in app["sameAs"]
    assert org["name"] == "Kruse Consulting AB" and org["email"] == "hello@krusgraph.test"
    text = json.dumps(blocks).lower()
    for banned in ("aggregaterating", "ratingvalue", "review", "downloads", "interactioncount"):
        assert banned not in text, banned
    assert "application/ld+json" not in client.get("/docs").text


def test_sitemap_lists_public_pages_only(client):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    locs = re.findall(r"<loc>([^<]+)</loc>", r.text)
    assert locs == ["https://krusgraph.test" + p for p in PUBLIC]
    assert r.text.count("<lastmod>") == len(PUBLIC) and "mascots" not in r.text
    for loc in locs:
        assert client.get(loc.replace("https://krusgraph.test", "")).status_code == 200


def test_robots_points_at_sitemap_and_keeps_mascots_out(client):
    t = client.get("/robots.txt").text
    assert "Disallow: /mascots" in t and "Sitemap: https://krusgraph.test/sitemap.xml" in t
    assert "Allow: /mcp/server-card" in t


def test_llms_txt_follows_the_format_and_links_markdown(client):
    r = client.get("/llms.txt")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    t = r.text
    assert t.startswith("# Krusgraph\n\n> ")
    for tool in ("list_sources", "list_tables", "plan_backend", "create_backend", "rayfin_connector", "query_graphql"):
        assert f"`{tool}`" in t
    assert "https://krusgraph.test/mcp" in t and "Microsoft Entra work account" in t and "introspection" in t
    links = re.findall(r"\]\((https://krusgraph\.test/[^)]+)\)", t)
    for md in ("/docs.md", "/start.md", "/privacy.md", "/lovable.md", "/demo/plan.json", "/mcp/server-card"):
        assert "https://krusgraph.test" + md in links, md


@pytest.mark.parametrize("path,needle", [("/docs.md", "## Tools"), ("/privacy.md", "Kruse Consulting AB"),
                                         ("/start.md", "# Small steps. Useful connections."), ("/lovable.md", "# Use Krusgraph with Lovable")])
def test_markdown_versions(client, path, needle):
    r = client.get(path)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    assert needle in r.text and "{{" not in r.text and "<svg" not in r.text and "<div" not in r.text


def test_start_md_keeps_the_permissions_table(client):
    t = client.get("/start.md").text
    assert "| Permission | Used for |\n| --- | --- |\n| `User.Read` (Microsoft Graph) | sign-in only |" in t
    assert "```\nhttps://krusgraph.test/mcp\n```" in t and "](https://krusgraph.test/docs)" in t


def test_lovable_page_is_linked_and_makes_no_connector_claim(client):
    assert 'href="/lovable"' in client.get("/").text                                      # footer
    assert 'href="/lovable"' in client.get("/docs").text
    html = client.get("/lovable").text
    assert "https://docs.lovable.dev/integrations/microsoft-fabric" in html
    for step in ("Create the API with Krusgraph", "Turn on introspection in Fabric", "Add it in Lovable"):
        assert step in html
    assert "untested" in html and "dynamic client registration" in html


def test_server_card_is_public_and_follows_the_discovery_doc(client):
    r = client.get("/mcp/server-card", headers={"Accept": "application/mcp-server-card+json"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/mcp-server-card+json"
    assert r.headers["access-control-allow-origin"] == "*" and r.headers["access-control-allow-methods"] == "GET"
    assert r.headers["access-control-expose-headers"] == "ETag" and "If-None-Match" in r.headers["access-control-allow-headers"]
    assert r.headers["cache-control"] == "public, max-age=3600" and r.headers["etag"]
    card = r.json()
    assert card["$schema"] == "https://static.modelcontextprotocol.io/schemas/v1/server-card.schema.json"
    assert card["name"] == "test.krusgraph/krusgraph" and card["title"] == "Krusgraph"
    assert 0 < len(card["description"]) <= 100 and card["websiteUrl"] == "https://krusgraph.test/"
    assert card["repository"] == {"url": "https://github.com/Krusmaster/fabric-backend", "source": "github"}
    remote = card["remotes"][0]
    assert remote["type"] == "streamable-http" and remote["url"] == "https://krusgraph.test/mcp"
    assert remote["supportedProtocolVersions"] and all(re.match(r"^\d{4}-\d{2}-\d{2}$", v) for v in remote["supportedProtocolVersions"])
    assert "tools" not in card                                                             # primitives are listed at runtime
    import tomllib
    from pathlib import Path
    assert card["version"] == tomllib.loads((Path(__file__).resolve().parent.parent / "pyproject.toml").read_text())["project"]["version"]
    again = client.get("/mcp/server-card", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304 and again.headers["etag"] == r.headers["etag"]
    pre = client.options("/mcp/server-card")
    assert pre.status_code == 204 and pre.headers["access-control-allow-origin"] == "*"


def test_ai_catalog_points_at_the_server_card(client):
    r = client.get("/.well-known/ai-catalog.json")
    assert r.status_code == 200 and r.headers["content-type"] == "application/ai-catalog+json"
    assert r.headers["access-control-allow-origin"] == "*" and r.headers["cache-control"] == "public, max-age=3600"
    entry = r.json()["entries"][0]
    assert r.json()["specVersion"] == "1.0"
    assert entry == {"identifier": "urn:air:krusgraph.test:mcp:krusgraph", "type": "application/mcp-server-card+json",
                     "url": "https://krusgraph.test/mcp/server-card"}


def test_server_json_matches_the_package_and_the_card():
    import tomllib
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    sj = json.loads((root / "server.json").read_text())
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    assert sj["$schema"] == "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
    assert sj["name"] == "com.krusgraph/krusgraph" and sj["version"] == version and len(sj["description"]) <= 100
    import fabric_backend
    assert fabric_backend.__version__ == version                                          # the card and serverInfo read this
    assert sj["remotes"] == [{"type": "streamable-http", "url": "https://krusgraph.com/mcp"}]
    from fabric_backend.discovery import DESCRIPTION
    assert sj["description"] == DESCRIPTION


def test_ai_crawlers_are_named_in_robots_and_the_full_text_is_one_fetch(client):
    t = client.get("/robots.txt").text
    for bot in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"):
        assert f"User-agent: {bot}\nAllow: /\n" in t, bot
    assert t.count("Disallow: /mcp\n") >= 5 and t.strip().endswith("sitemap.xml")
    full = client.get("/llms-full.txt")
    assert full.status_code == 200 and full.headers["content-type"].startswith("text/plain")
    for marker in ("/docs.md -->", "/start.md -->", "/lovable.md -->", "/privacy.md -->", "## How relationships are inferred", "Snowflake"):
        assert marker in full.text, marker
    llms = client.get("/llms.txt").text
    assert "## Connect" in llms and "/llms-full.txt" in llms and "claude mcp add --transport http" in llms and "list_workspaces" in llms


def test_pages_point_agents_at_their_markdown_twin_and_home_declares_the_website(client):
    for path in ("/docs", "/start", "/privacy", "/lovable"):
        html = client.get(path).text
        assert f'<link rel="alternate" type="text/markdown" href="{path}.md"' in html, path
        assert 'content="index,follow,max-snippet:-1,max-image-preview:large"' in html, path
        assert client.get(path + ".md").status_code == 200
    home = client.get("/").text
    assert 'type="text/markdown"' not in home and '"@type": "WebSite"' in home
    assert 'name="robots" content="noindex' not in home
    assert 'content="index,follow' not in client.get("/mascots").text                     # noindex pages get no index directive
