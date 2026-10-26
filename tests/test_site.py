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


ALL_PAGES = sorted(set(PAGES) | {"/docs", "/privacy", "/lovable", "/local"})


@pytest.mark.parametrize("path", ALL_PAGES)
def test_every_page_renders_with_title_description_and_footer(client, path):
    r = client.get(path)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert r.headers["cache-control"] == "public, max-age=300"
    html = r.text
    assert "{{" not in html and "{{/IF}}" not in html
    assert re.search(r"<title>[^<]{5,}</title>", html)
    assert re.search(r'<meta name="description" content="[^"]{20,}"', html)
    assert "Microsoft Fabric and Fabric IQ are trademarks of Microsoft Corporation" in html
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
    first = re.search(r'<p class="lede">(.*?)</p>', html).group(1)                         # Claude and Fabric tables in the first paragraph
    assert "Claude" in first and "Fabric tables" in first and "GraphQL API" in first
    assert 'href="/explore"' in html and "Try the demo" in html and "Connect Claude" in html
    assert "From tables to a GraphQL API" in html
    for step in ("Choose your tables", "Review the plan", "Create the API"):
        assert f"<h3>{step}</h3>" in html
    assert "“Plan a backend over the shop lakehouse.”" in html and "“Create it as shop_api.”" in html
    assert 'href="/docs#sources"' in html and 'href="/docs#test-status"' in html


def test_home_introduces_the_developer_without_a_story(client):
    html = client.get("/").text
    assert "A note from the developer" in html and "I’m Gustav, the developer behind Krusgraph" in html
    assert "through Kruse Consulting AB in Sweden" in html and 'href="mailto:hello@krusgraph.test?subject=Krusgraph"' in html
    assert ">Email Gustav</a>" in html


def test_start_page_has_real_instructions_and_no_fake_sign_in(client):
    html = client.get("/start").text
    assert "<h1>Connect Krusgraph to Claude</h1>" in html
    assert "https://krusgraph.test/mcp" in html
    assert "adminconsent?client_id=cid-123" in html
    assert "What will Krusgraph access?" in html and "GraphQLApi.ReadWrite.All" in html and "user_impersonation" in html
    assert "Continue with Microsoft" not in html
    assert "not registered on the Entra app yet" in html                                   # no claim that Claude Code sign-in works today
    assert "can’t sign in to krusgraph.test today" in html                                 # nor Cursor
    for step in ("Get admin approval", "Choose a Fabric workspace", "Add the connector in Claude"):
        assert step in html
    assert "Ask for a plan before creating anything" in html and "check the plan against the data" in html
    assert html.count('class="start-step"') == 3 and 'data-pane="3"' in html and "Explore a sample first" in html
    assert "Why each one:" in html and "create_backend</code> alone" in html and "Item.ReadWrite.All" in html   # every scope with its reason
    assert "notebooks and pipelines" in html and "available when enabled by the operator" in html
    assert "<code>sample_rows</code> returns up to 20 example rows" in html and "not kept after the request" in html
    assert "Design preview" not in html and 'type="password"' not in html                                       # no fake sign-in


def test_docs_have_the_first_questions_and_the_first_time_errors(client):
    docs = client.get("/docs").text
    assert "Five first questions on a lakehouse nobody has documented" in docs
    for tool in ("analyze_schema", "plan_backend", "validate_plan", "suggest_relationships", "data_dictionary"):
        assert f"({'<code>' + tool + '</code>'}" in docs or f"<code>{tool}</code>" in docs
    assert '<h2 id="first-time-errors">' in docs
    for kind in ("sign_in", "consent", "no_access", "capacity", "schema_not_found"):
        assert f"<code>{kind}</code>" in docs
    assert "Workspace settings → License info" in docs and "Disconnect" in docs
    from fabric_backend import errors
    assert errors.docs_url("first-time-errors").endswith("/docs#first-time-errors")
    for kind in errors.FIRST_TIME:
        assert errors._answer(kind, "x")["hint"].endswith("/docs#first-time-errors")
    assert "first-time-errors" not in errors._answer("timeout", "x")["hint"]


def test_support_page_is_a_help_page_without_contributions(client):
    html = client.get("/support").text
    assert "<h1>Get help with Krusgraph</h1>" in html and "<title>Get help with Krusgraph</title>" in html
    assert "mailto:hello@krusgraph.test?subject=Help%20with%20Krusgraph" in html
    assert "<code>error</code>, <code>kind</code> and <code>hint</code>" in html and "no promised response time" in html
    assert 'href="https://github.com/Krusmaster/fabric-backend/issues"' in html and 'href="/docs#first-time-errors"' in html
    for kind in ("sign_in", "consent", "no_access", "capacity", "schema_not_found"):
        assert f"<code>{kind}</code>" in html, kind
    main = html.split('<main id="main"')[1].split("</main>")[0].lower()
    for gone in (r"contribution", r"contribute\b", r"donat", r"\bsek\b", r"\bfund", r"payment", r"help keep"):   # "Contributor" is a Fabric role
        assert not re.search(gone, main), gone
    assert "<form" not in html and "card number" not in html.lower()
    docs = client.get("/docs.md").text
    assert "Support the work" not in docs and "Help keep" not in docs and "[Get help](/support)" in docs
    for t in (client.get("/llms.txt").text, client.get("/llms-full.txt").text, client.get("/").text):
        assert "Support the work" not in t and "contribution" not in t.lower() and "help keep" not in t.lower()


def test_partner_sign_in_button_only_with_flag(client, monkeypatch):
    html = client.get("/partners").text
    assert "Try Krusgraph on a Fabric project" in html and 'href="/partners/workspace"' in html and "Discuss a pilot" in html
    assert "never data" not in html and "not a partner programme or a certification, and it is not affiliated with Microsoft" in html
    assert "Continue with Microsoft" not in html
    monkeypatch.setenv("PARTNER_SIGNIN", "1")
    html = client.get("/partners").text
    assert "Continue with Microsoft" in html and 'aria-disabled="true"' in html and "redirect URI" in html


def test_workspace_preview_is_labelled_illustrative(client):
    html = client.get("/partners/workspace").text
    assert "Sample pilot · synthetic data. No customer workspace is connected." in html
    assert "A sample Krusgraph pilot" in html and "your workspace" not in html.lower() and "partner account" not in html
    for step in ("Connect", "Explore", "Review", "Build"):
        assert f'>{step}</span>' in html
    assert "Next step" in html and 'href="/docs"' in html and "seed.py" in html


def test_mascot_review_page_is_noindex(client):
    r = client.get("/mascots")
    assert r.headers["x-robots-tag"] == "noindex, nofollow"
    assert '<meta name="robots" content="noindex,nofollow">' in r.text
    assert "Simulate success" in r.text and "Simulate failure" in r.text and "Accept in this demo" in r.text and "Leave unlinked" in r.text
    assert "Both are valid" not in r.text
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
        assert "subject=Help%20with%20A%26B%20%3Cx%3E" in c.get("/support").text


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
    assert 'class="trust"' in html and "Your Microsoft sign-in" in html and "What passes through Krusgraph" in html
    assert "Demo · synthetic data" in html


# ------------------------------------------------------------------ SEO and agent discovery ---------------------

PUBLIC = ["/", "/explore", "/start", "/docs", "/lovable", "/local", "/use-cases", "/privacy", "/support", "/partners", "/partners/workspace"]


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
    assert "offers" not in app                                                           # no price line (decided 26 October 2026)
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
    for md in ("/docs.md", "/start.md", "/privacy.md", "/lovable.md", "/local.md", "/demo/plan.json", "/mcp/server-card"):
        assert "https://krusgraph.test" + md in links, md


@pytest.mark.parametrize("path,needle", [("/docs.md", "## Tools"), ("/privacy.md", "Kruse Consulting AB"),
                                         ("/start.md", "# Connect Krusgraph to Claude"), ("/lovable.md", "# Build a Lovable app on your Fabric tables"),
                                         ("/local.md", "# Run Krusgraph locally")])
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


def test_fabric_iq_is_described_on_home_docs_and_llms(client):
    home = client.get("/").text
    assert 'id="fabric-iq"' in home and 'href="/docs#fabric-iq-the-same-graph-as-an-ontology"' in home and "preview" in home
    docs = client.get("/docs").text
    assert '<h2 id="fabric-iq-the-same-graph-as-an-ontology">' in docs and "ontology_draft" in docs and "Item.ReadWrite.All" in docs
    assert "ontology_draft" in client.get("/docs.md").text and "`ontology_draft`" in client.get("/llms.txt").text
    assert "Fabric IQ" in client.get("/llms-full.txt").text


def test_demo_validation_is_computed_from_the_seed_rows_and_shown_on_explore(client):
    from fabric_backend import demo
    v = demo.demo_validation()
    assert v["summary"] == "6 of 6 keys unique, 6 of 6 relationships hold without orphans"
    assert {k["table"]: k["rows"] for k in v["keys"]}["order_items"] == 134 and all(k["nulls"] == 0 for k in v["keys"])
    assert all(r["orphans"] == 0 for r in v["relationships"]) and v["suggested_keys"] == []       # K5 infers order_id + line_no
    assert "synthetic demo data" in v["computed"]
    r = client.get("/demo/validation.json")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json") and json.loads(r.text)["summary"] == v["summary"]
    html = client.get("/explore").text
    assert 'id="plan-check"' in html and "computed on the synthetic demo data" in html and "validate_plan" in html
    assert html.count("unique in all") == 6 and html.count("holds for all") == 6 and 'href="/demo/validation.json"' in html


def test_docs_list_every_tool_the_server_defines_and_home_states_the_verification(client):
    import re
    from fabric_backend import server
    defined = {m.group(1) for m in re.finditer(r"^def (\w+)\(", open(server.__file__).read(), re.M)}
    tools = {"list_workspaces", "list_sources", "list_tables", "plan_backend", "sample_rows", "validate_plan", "create_backend",
             "describe_backend", "query_graphql", "rayfin_connector", "ontology_draft", "semantic_model_draft", "join_path",
             "data_dictionary", "dbt_schema", "plan_drift", "create_semantic_model", "create_views", "create_data_agent",
             "app_starter", "app_readiness", "lineage", "analyze_schema", "suggest_relationships", "create_ontology",
             "silver_notebook_draft", "create_silver_notebook", "drift_monitor_draft", "create_drift_monitor", "answer_query_draft"}
    assert tools <= defined
    docs = client.get("/docs").text
    for t in tools:
        assert f"<code>{t}</code>" in docs, t
    assert "Cold start" in docs and "min_replicas" in docs and "26 October 2026" in docs
    assert "never a cold start" not in docs and "well under a second" not in docs
    home = client.get("/").text
    assert "Check the plan against the data" in home and "Tested end to end on 26 October 2026" in home
    llms = client.get("/llms.txt").text
    assert "`validate_plan`" in llms and "`describe_backend`" in llms and "/demo/validation.json" in llms
    assert "Thirty tools" in llms and "K0–K5 for keys, R0–R4 for relationships" in llms and "Eleven" not in llms
    assert not re.search(r"\b[KR]0–[KR]\d", home) and "K0–K3" not in docs              # no rule ranges in the marketing text


def test_the_site_icon_is_served_at_the_root_where_directories_look():
    from starlette.testclient import TestClient
    from fabric_backend import server
    c = TestClient(server.build_app())
    ico = c.get("/favicon.ico")
    assert ico.status_code == 200 and ico.headers["content-type"] == "image/x-icon" and ico.content[:4] == b"\x00\x00\x01\x00"
    touch = c.get("/apple-touch-icon.png")
    assert touch.status_code == 200 and touch.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert c.get("/static/icon-512.png").status_code == 200


def test_local_page_registry_line_and_plugin_coming_soon(client):
    html = client.get("/local").text
    assert "Trusted_Connection=yes;TrustServerCertificate=yes" in html and "db_datareader" in html and "FABRIC_SOURCE_KIND" in html
    assert "not yet been run against a live SQL Server" in html and 'href="/docs"' in html
    assert 'href="/local"' in client.get("/docs").text and "/local" in client.get("/sitemap.xml").text
    assert "https://krusgraph.test/local.md" in client.get("/llms.txt").text and "/local.md -->" in client.get("/llms-full.txt").text
    for page in ("/", "/docs"):
        t = client.get(page).text
        assert "registry.modelcontextprotocol.io" in t and "com.krusgraph/krusgraph" in t
    docs = client.get("/docs").text
    assert "coming soon" in docs and "plugin/krusgraph" in docs and "not published yet" in docs
    for t in (docs, client.get("/").text, client.get("/llms.txt").text):
        assert "Claude directory" not in t and "connector directory" not in t and "Verified connector" not in t


# ------------------------------------------------------------------ status words and the data path (round n11) ----

STATUS_WORDS = ("Tested end to end", "Experimental", "Draft only", "Available when enabled by the operator", "Planned")


def test_docs_give_every_tool_a_status_in_the_shared_words(client):
    md = client.get("/docs.md").text
    rows = [r for r in md.splitlines() if r.startswith("| `") and r.count("|") >= 6]
    assert "| Tool | Status | What it changes | Does | Arguments |" in md                      # status visible without scrolling
    tools = {r.split("|")[1].strip().strip("`"): r.split("|")[2].strip() for r in rows}
    assert len(tools) == 30, sorted(tools)
    for tool, status in tools.items():
        assert status.startswith(STATUS_WORDS), (tool, status)
    for tool in ("create_semantic_model", "create_data_agent", "create_ontology", "create_silver_notebook", "create_drift_monitor"):
        assert tools[tool].startswith("Available when enabled by the operator"), tool
    for tool in ("lineage", "app_readiness"):
        assert tools[tool].startswith("Experimental"), tool
    assert "## Test status" in md and "26 October 2026" in md and "in 14 steps without any creating call" in md
    assert "22 tools" not in md and "for real" not in md
    for tool in ("create_backend", "list_tables"):
        assert tools[tool].startswith("Experimental"), tool                              # not among the 14 steps of 26 October
    assert tools["create_views"].startswith("Tested end to end (dry run)") and tools["ontology_draft"] == "Draft only"
    tested = {t for t, s in tools.items() if s.startswith("Tested end to end")}
    assert tested == {"list_workspaces", "list_sources", "sample_rows", "plan_backend", "validate_plan", "suggest_relationships",
                      "analyze_schema", "join_path", "describe_backend", "query_graphql", "data_dictionary", "dbt_schema",
                      "create_views", "plan_drift", "app_starter"} | ({"semantic_model_draft"} & tested)
    assert "`create_backend` does not run it for you" in md                               # validation is a step you ask for


def test_privacy_names_samples_and_checks_separately(client):
    html = client.get("/privacy").text
    assert "Everything the service handles passes through its memory and nowhere else" not in html
    assert "only when you run a query" not in html
    assert "<code>sample_rows</code> returns up to 20 rows" in html and "Only the counts come back" in html
    for heading in ("Your Microsoft account", "Metadata, samples and query results", "Access tokens", "Technical logs",
                    "Third parties: Microsoft and your MCP client", "Contact and requests"):
        assert f">{heading}</h2>" in html, heading


def test_explore_texts_say_the_demo_choice_stays_in_the_demo(client):
    html = client.get("/explore").text
    assert "Select a table or relationship to see its explanation here." in html and "Copy diagram (Mermaid)" in html
    assert "accepted in this demo" in html and "needs review" in html and "Checks on the demo data" in html
    assert 'href="#edge=orders.customer_id%3Ecustomers"' in html                            # Onto points at the first thing to do
    js = client.get("/static/site.js").text
    assert "Both are valid" not in js and "It does not update Fabric." in js and "Leave unlinked" in js
    assert "Accept in this demo" in js and "Accepted here" not in js


def test_use_cases_mark_outputs_with_the_docs_status(client):
    html = client.get("/use-cases").text
    assert "(planned)" not in html and "What could you build from your Fabric tables?" in html
    assert "time it takes to read and accept a plan" not in html and "defensible to auditors" not in html
    first = html.split('id="industries"')[0]                                            # the illustrative note comes first
    assert "The schemas are illustrative examples, not customer projects." in first


def test_no_page_claims_every_tool_nothing_stored_or_cursor_as_a_working_client(client):
    """The text review of 26 October: no "every tool" (most tools are not live-tested), no "Nothing stored" (tokens,
    usage records and logs exist), and Cursor only ever named as a client that cannot sign in to the hosted service."""
    from fabric_backend.discovery import PUBLIC_PAGES
    paths = PUBLIC_PAGES + ["/docs.md", "/start.md", "/privacy.md", "/lovable.md", "/local.md", "/use-cases.md",
                            "/llms.txt", "/llms-full.txt", "/mcp/server-card"]
    for path in paths:
        text = client.get(path).text
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
        low = plain.lower()
        for banned in ("every tool", "nothing stored", "stores nothing", "never data"):
            assert banned not in low, (path, banned)
        for sentence in re.split(r"(?<=[.;!?])\s+", plain):
            if "cursor" in sentence.lower():
                assert re.search(r"can(?:no|’|')t|not registered|not supported", sentence), (path, sentence)
