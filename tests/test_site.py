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
    for href in ("/docs", "/support", "/partners", "/demo", "/explore", "/start", "/privacy", "https://github.com/Krusmaster/fabric-backend"):
        assert f'href="{href}"' in html, href
    assert "Microsoft Fabric, connected." in html
    assert 'href="/mascots"' not in html                                                 # review page is unlinked


def test_home_says_what_it_helps_with_before_how_it_connects(client):
    """The website brief of 26 October 2026: the hero says what a reader can understand about their Fabric tables
    without needing to know MCP or GraphQL; the API step carries its experimental status where the expectation is made."""
    html = client.get("/").text
    assert "Good things happen when data connects." not in html
    h1 = re.search(r"<h1>(.*?)</h1>", html).group(1)
    assert "Fabric tables" in h1 and "MCP" not in h1 and "GraphQL" not in h1
    first = re.search(r'<p class="lede">(.*?)</p>', html).group(1)
    assert "relationships" in first and "MCP" not in first and "GraphQL" not in first and len(first.split()) <= 30
    assert 'href="/demo">Try the guided demo<' in html and 'href="/start">Connect to Claude<' in html
    assert "No account needed" in html and "through MCP" in html                        # MCP explained further down
    step3 = re.search(r'<span class="step-n lav">3</span>(.*?)</li>', html, re.S).group(1)
    assert "API" in step3 and "experimental" in step3 and 'href="/docs#test-status"' in step3
    assert "“Plan a backend over the shop lakehouse.”" in html and "“Create it as shop_api.”" in html


def test_home_introduces_the_developer_without_a_story(client):
    html = client.get("/").text
    assert "A note from Gustav" in html and "I’m Gustav, the developer behind Krusgraph" in html
    assert 'href="mailto:hello@krusgraph.test?subject=Krusgraph"' in html and ">Email Gustav</a>" in html
    assert "Sweden" not in html and "Swedish" not in html                                # no country of origin on the start page


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
    assert "The first goal is a plan you have read and checked" in html and "check the plan against the data" in html
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
    assert '<h3 id="first-time-errors">' in docs
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
    assert "<code>error</code>, <code>kind</code> and <code>hint</code>" in html and "with no guaranteed response time" in html
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
    assert "Bring one schema and one question." in html and 'href="/partners/workspace"' in html and "Discuss your schema" in html
    assert "No customer data is needed" in html and "SLA" not in html                    # no price, duration or guarantee promised
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
    footer = client.get("/").text.split('<footer class="site-footer">')[1]
    assert "Kruse Consulting AB · Org. no. 123456-7890 · Open source under the MIT licence" in footer and "Sweden" not in footer


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
    # the one suggestion is the engine's: suggest_relationships on the synthetic rows, with its data check (home page round 1)
    [sug] = d["suggestions"]
    assert (sug["table"], sug["column"], sug["target"], sug["target_cols"]) == ("orders", "ship_to_id", "addresses", ["address_id"])
    assert sug["source"] == "suggest_relationships" and sug["score"] == 3.94
    assert "ship-to" in sug["why"] and "orders -> customers <- addresses" in sug["why"]
    assert sug["evidence"]["inclusion"] == 1.0 and sug["evidence"]["rows_with_value"] == 60 and sug["evidence"]["distinct_values"] == 15
    assert sug["check"] == "All 60 orders in this sample have a ship_to_id that exists in addresses (15 different addresses)."
    assert sug["runner_up"] == {"target": "customers", "matched": 35, "rows_with_value": 60}
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
    assert 'class="hero-figure"' not in html and 'id="home-graph"' not in html           # the graph and its mascots are on /demo
    assert 'class="trust"' in html and "What Krusgraph reads" in html and 'href="/privacy"' in html
    assert "Your data never leaves Fabric" not in html
    demo = client.get("/demo").text
    assert "Demo · synthetic data" in demo and 'id="home-graph"' in demo


# ------------------------------------------------------------------ SEO and agent discovery ---------------------

PUBLIC = ["/", "/demo", "/explore", "/start", "/docs", "/lovable", "/local", "/use-cases", "/privacy", "/support", "/partners", "/partners/workspace"]


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
    for md in ("/docs.md", "/start.md", "/privacy.md", "/lovable.md", "/local.md", "/demo", "/demo/plan.json", "/mcp/server-card"):
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
    assert '<h3 id="fabric-iq-the-same-graph-as-an-ontology">' in docs and "ontology_draft" in docs and "Item.ReadWrite.All" in docs
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
             "silver_notebook_draft", "create_silver_notebook", "drift_monitor_draft", "create_drift_monitor", "answer_query_draft",
             "compare_semantic_model", "gold_views_draft", "create_gold_views", "export_item_definitions"}
    assert tools <= defined
    docs = client.get("/docs").text
    for t in tools:
        assert f"<code>{t}</code>" in docs, t
    assert "Cold start" in docs and "min_replicas" in docs and "26 October 2026" in docs
    assert "never a cold start" not in docs and "well under a second" not in docs
    home = client.get("/").text
    from fabric_backend import tool_status as ts
    assert "Check the plan against the data" in home and f"Tested end to end on {ts.LIVE_RUN_DATE}" in home and "no new item was created" in home
    llms = client.get("/llms.txt").text
    assert "`validate_plan`" in llms and "`describe_backend`" in llms and "/demo/validation.json" in llms
    assert "Thirty-six tools" in llms and "K0–K5 for keys, R0–R4 for relationships" in llms and "Eleven" not in llms
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
    assert len(tools) == 36, sorted(tools)
    for tool, status in tools.items():
        assert status.startswith(STATUS_WORDS), (tool, status)
    for tool in ("create_semantic_model", "create_data_agent", "create_ontology", "create_silver_notebook", "create_drift_monitor"):
        assert tools[tool].startswith("Available when enabled by the operator"), tool
    assert "## Test status" in md and "27 October 2026, through the hosted server's build src-df29c45febaec4b0" in md
    assert "one creating call that updated an existing API in place" in md
    assert "The first such run was on 26 October 2026 (14 steps)" in md
    assert "22 tools" not in md and "for real" not in md
    assert tools["create_backend"] == "Tested end to end (27 October 2026: update in place of shop_api with confirmed)"
    assert tools["create_views"] == "Tested end to end as a dry run; creating them: Experimental"
    for tool in ("create_semantic_model", "create_data_agent"):
        assert tools[tool] == "Available when enabled by the operator; tested end to end as a dry run", tool
    for tool in ("ontology_draft", "semantic_model_draft", "data_dictionary", "dbt_schema", "app_starter", "answer_query_draft",
                 "rayfin_connector", "export_item_definitions"):
        assert tools[tool] == "Tested end to end (a draft; creates nothing)", tool
    tested = {t for t, s in tools.items() if s.startswith("Tested end to end")}
    assert tested == {"list_workspaces", "list_sources", "list_tables", "sample_rows", "plan_backend", "validate_plan",
                      "suggest_relationships", "analyze_schema", "join_path", "describe_backend", "query_graphql",
                      "answer_query_draft", "app_readiness", "app_starter", "plan_drift", "lineage", "review_plan", "dbt_schema",
                      "data_dictionary", "semantic_model_draft", "ontology_draft", "rayfin_connector", "silver_notebook_draft",
                      "gold_views_draft", "drift_monitor_draft", "export_item_definitions", "create_views",
                      "create_backend"}   # the run of 27 October, create_backend as an update in place
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
    assert "(planned)" not in html and "What do you need to understand about your data?" in html
    assert "time it takes to read and accept a plan" not in html and "defensible to auditors" not in html
    first = html.split('id="industries"')[0]                                            # the illustrative note comes first
    assert "The schemas are illustrative examples, not customer projects." in first


@pytest.mark.parametrize("registration", ["", "1"])
def test_no_page_claims_every_tool_nothing_stored_or_cursor_as_a_working_client(client, monkeypatch, registration):
    """The text review of 26 October: no "every tool" (most tools are not live-tested), no "Nothing stored" (tokens,
    usage records and logs exist). Cursor is named as working only where the hosted service signs it in: with client
    registration off, only as a client that cannot sign in; with it on (live test of 27 October 2026), in a sentence
    that sends it to /mcp/connect, gives the date it was tested, says what Krusgraph does not accept, or in the hub."""
    from fabric_backend.discovery import PUBLIC_PAGES
    monkeypatch.setenv("KRUSGRAPH_CLIENT_REGISTRATION", registration)
    paths = PUBLIC_PAGES + ["/docs.md", "/start.md", "/privacy.md", "/lovable.md", "/local.md", "/use-cases.md",
                            "/llms.txt", "/llms-full.txt", "/mcp/server-card"]
    for path in paths:
        text = client.get(path).text
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
        low = plain.lower()
        for banned in ("every tool", "nothing stored", "stores nothing", "never data"):
            assert banned not in low, (path, banned)
        for sentence in re.split(r"(?<=[.;!?])\s+", plain):
            if "cursor" not in sentence.lower():
                continue
            if not registration:
                assert re.search(r"can(?:no|’|')t|not registered|not supported", sentence), (path, sentence)
            else:
                assert re.search(r"can(?:no|’|')t|not registered|not supported|mcp/connect|27 October 2026|does not accept|"
                                 r"Where you build|Claude, VS Code and Cursor|Anysphere|/oauth|not yet confirmed", sentence), (path, sentence)



def test_docs_and_llms_place_krusgraph_beside_microsofts_fabric_mcp_servers_without_claiming_ties(client):
    """Round n12: one section in /docs and one line in llms.txt and the server instructions on working with Microsoft's
    official Fabric MCP servers, with Microsoft's own pages linked; no partnership, endorsement or certification."""
    from fabric_backend import server
    docs = client.get("/docs").text
    assert "With Microsoft’s Fabric MCP servers" in docs or "With Microsoft's Fabric MCP servers" in docs
    for link in ("https://github.com/microsoft/mcp/blob/main/servers/Fabric.Mcp.Server/README.md",
                 "https://learn.microsoft.com/fabric/iq/connectors/fabric-iq-mcp", "https://github.com/microsoft/powerbi-modeling-mcp"):
        assert link in docs, link
    llms = client.get("/llms.txt").text
    assert "Microsoft's own Fabric MCP servers" in llms and "not affiliated with Microsoft" in llms
    assert "Microsoft's own Fabric MCP servers" in server.mcp.instructions
    for text in (docs, llms, server.mcp.instructions):
        low = text.lower()
        for banned in ("partner of microsoft", "microsoft partner", "in partnership with microsoft", "approved by microsoft",
                       "recommended by microsoft"):          # the footer's "not affiliated with, endorsed by or certified by" stays
            assert banned not in low, banned


def test_privacy_and_docs_say_exactly_what_is_read_about_personal_data_and_labels(client):
    html = client.get("/privacy").text
    assert "show_personal_data=true" in html and "judged by the column" in html and "label’s id only" in html or "label's id only" in html
    assert "no call goes to GitHub, Azure" in html and "compare_semantic_model" in html
    docs = client.get("/docs").text
    assert "Personal data and sensitivity labels." in docs and "never from the values" in docs


# ------------------------------------------------------------------ creating is not tested end to end (n12 follow-up) ----

_CREATE_CLAIMS = [
    # "tested end to end" said of the GraphQL API or the SQL views as things created, without "dry run" or "querying"
    re.compile(r"\b(?:GraphQL API|SQL views)\b(?:(?!dry run|querying|existing|in place|\n\n|\|)[\s\S]){0,200}?\btested end to end\b(?!\s*(?:\(dry run\)|as a dry run))", re.I),
    # create_backend or create_views with the status word and no dry run
    re.compile(r"\bcreate_(?:backend|views)`?\s*\|\s*Tested end to end(?!\s*(?:\(dry run\)|as a dry run|\(27 October 2026: update in place))"),
    # create_backend said to have created something, or to have run live
    re.compile(r"\bcreate_backend`?\s+(?:created|ran live|was run live)\b|\bLive on 25 October; `create_backend", re.I),
    # create_views said to have created its schema or a view for real
    re.compile(r"create_views`?[^\n]{0,120}\b(?:created (?:a |its |the )?schema|for real)\b", re.I),
]


def _create_claims(text: str) -> list[str]:
    return [m.group(0)[:160] for rx in _CREATE_CLAIMS for m in rx.finditer(text)]


def test_creating_the_api_or_the_views_is_never_called_tested_end_to_end(client):
    """Decisions 1 and 11 of 26 October 2026: create_backend had not been run live, and create_views ran as a dry run
    only. Since 27 October create_backend's update in place of shop_api is tested end to end; creating a new API is not,
    and is never called so."""
    import pathlib
    from fabric_backend import server, use_cases
    from fabric_backend.discovery import PUBLIC_PAGES
    # the detector catches the sentences that used to be there
    for old in ("- **GraphQL API**: an API for GraphQL item in your workspace, for an app or for questions in Claude (tested end to end)",
                "- **SQL views**: wide T-SQL views over the plan's joins on the SQL analytics endpoint (tested end to end)",
                "| `create_backend` | Tested end to end | creates/updates one item",
                "`create_backend` created `shop_api` and a second run answered `mode: updated`",
                "| Live on 25 October; `create_backend` now refuses to drop relationships",
                "| `create_views` | Tested end to end (a schema and one wide view created for real); the header views are unit-tested |"):
        assert _create_claims(old), old
    for ok in ("| `create_views` | Tested end to end (dry run); creating and the header views are unit-tested |",
               "| `create_views` | Tested end to end as a dry run; creating them: Experimental |",
               "- **GraphQL API**: an API for GraphQL item (creating it: experimental; querying an existing one: tested end to end)",
               "- **SQL views**: wide T-SQL views (tested end to end as a dry run; creating them: experimental)"):
        assert not _create_claims(ok), ok
    texts = {p: client.get(p).text for p in list(PUBLIC_PAGES) + ["/docs.md", "/start.md", "/privacy.md", "/lovable.md", "/local.md",
                                                                  "/use-cases.md", "/llms.txt", "/llms-full.txt"]}
    root = pathlib.Path(__file__).resolve().parents[1]
    for f in [root / "README.md", *sorted((root / "docs").glob("*.md"))]:
        texts[str(f.relative_to(root))] = f.read_text(encoding="utf-8")
    texts["server instructions"] = server.mcp.instructions
    found = {p: _create_claims(t) for p, t in texts.items() if _create_claims(t)}
    assert not found, found
    status = {name: tag for name, _what, tag in use_cases.OUTPUTS}
    assert status["GraphQL API"].startswith("creating a new API is experimental") and "querying an existing one: tested end to end" in status["GraphQL API"]
    assert status["SQL views"].startswith("tested end to end as a dry run")


def test_docs_are_grouped_and_every_old_section_anchor_still_resolves(client):
    """The website brief of 26 October 2026 groups /docs into five parts; links into the old sections (from the home
    page, /start, the README and other sites) must keep landing on the same section."""
    docs = client.get("/docs").text
    groups = re.findall(r'<h2 id="([^"]+)">', docs)
    assert groups == ["get-started", "explore-and-check", "build-from-a-plan", "tool-reference", "hosting-and-permissions"]
    for anchor in ("connect", "what-it-accesses", "what-you-can-ask", "review-check-then-create", "test-status", "tools",
                   "how-relationships-are-inferred", "cold-start-and-min-replicas-if-you-run-it-yourself", "one-plan-five-fabric-pieces",
                   "with-microsoft-s-fabric-mcp-servers", "fabric-iq-the-same-graph-as-an-ontology", "sources",
                   "databricks-draft-only", "first-time-errors", "two-steps-stay-manual", "use-with-lovable", "for-agents", "keep-your-review",
                   "support"):
        assert f'id="{anchor}"' in docs, anchor
    # every in-site link to a /docs anchor lands on an id that exists
    ids = set(re.findall(r'\sid="([^"]+)"', docs))
    for page in ("/", "/start", "/explore", "/use-cases", "/lovable", "/local", "/partners", "/support", "/docs"):
        for frag in re.findall(r'href="/docs#([^"]+)"', client.get(page).text):
            assert frag in ids, (page, frag)
    # the 'on this page' list nests each section under its group
    toc = re.search(r'<nav class="toc"[^>]*>(.*?)</nav>', docs, re.S).group(1)
    assert toc.index('href="#get-started"') < toc.index('href="#connect"') < toc.index('href="#explore-and-check"')


def test_home_data_check_is_computed_from_the_demo_validation(monkeypatch):
    """The home panel's 'Data check' comes from the same counting checks /demo/validation.json serves, not from copy:
    change the counts and the sentence follows; drop a relationship's check and the panel says it was not checked."""
    import copy
    import re as _re
    from fabric_backend import demo
    real = demo.demo_validation()
    rel = next(r for r in real["relationships"] if r["source"] == "orders" and r["target"] == "customers")
    assert rel["orphans"] == 0 and rel["rows_with_value"] > 0

    def data_check(details: dict, key: str) -> str:
        m = _re.search(r"<dt>Data check</dt><dd>(.*?)</dd>", details[key])
        return _re.sub(r"<[^>]+>", "", m.group(1))

    assert str(rel["rows_with_value"]) in data_check(demo.home_details(), demo.HOME_DEFAULT)
    broken = copy.deepcopy(real)
    for r in broken["relationships"]:
        if r["source"] == "orders" and r["target"] == "customers":
            r["orphans"], r["rows_with_value"] = 3, 41
    monkeypatch.setattr(demo, "demo_validation", lambda: broken)
    text = data_check(demo.home_details(), demo.HOME_DEFAULT)
    assert "3" in text and "41" in text and str(rel["rows_with_value"]) not in text
    unchecked = copy.deepcopy(real)
    unchecked["relationships"] = [r for r in unchecked["relationships"] if not (r["source"] == "orders" and r["target"] == "customers")]
    monkeypatch.setattr(demo, "demo_validation", lambda: unchecked)
    assert "not checked" in data_check(demo.home_details(), demo.HOME_DEFAULT).lower()
    # the suggestion's data check is the engine's count; accepting its meaning never changes what the check says
    monkeypatch.setattr(demo, "demo_validation", lambda: real)
    d = demo.home_details()
    sid = "orders.ship_to_id>addresses"
    assert data_check(d, sid) == data_check(d, sid + "|accepted") == "All 60 orders in this sample have a ship_to_id that exists in addresses (15 different addresses)."
    assert "Accepted in this demo" in d[sid + "|accepted"] and "separate" in d[sid + "|accepted"]
    sug = demo.demo_suggestions()
    monkeypatch.setattr(demo, "demo_suggestions", lambda: [dict(sug[0], evidence=None, check="")])
    assert "not checked" in data_check(demo.home_details(), sid).lower()


def test_sweden_stays_a_privacy_fact_not_a_selling_point(client):
    """The brief of 26 October 2026: the operator, IMY and Sweden Central stay in /privacy; the product pages do not
    sell the product on where it is made. Swedish as a language the tools read (kund, a question in Swedish) is a
    feature, not a location claim."""
    privacy = client.get("/privacy").text
    assert "Kruse Consulting AB, Sweden" in privacy and "IMY" in privacy and "Sweden Central" in privacy
    for path in ("/", "/use-cases", "/start", "/partners", "/support", "/explore", "/lovable", "/local", "/docs", "/llms.txt"):
        text = re.sub(r"<[^>]+>", " ", client.get(path).text)
        assert not re.search(r"\b(?:Sweden|Swedish (?:company|team|developer|consultan\w*)|Stockholm|svensk\w*)\b", text), path


def test_experimental_status_sits_next_to_the_creating_step(client):
    """Wherever a page offers creating the API as a step, the step itself says it is experimental and links the test
    status, so the claim and its status cannot drift apart on different parts of the page."""
    home = client.get("/").text
    step = re.search(r'<section[^>]*id="how".*?</section>', home, re.S).group(0)
    items = re.findall(r"<li.*?</li>", step, re.S)
    creating = [i for i in items if "create" in i.lower() or "build" in i.lower()]
    assert creating and all("xperimental" in i and 'href="/docs#test-status"' in i for i in creating[-1:])
    start = client.get("/start").text
    assert re.search(r"create_backend[^<]{0,200}", start) and "xperimental" in start
    lovable = client.get("/lovable").text
    assert "xperimental" in lovable


def test_one_status_source_covers_exactly_the_hosted_tools(client):
    """tool_status is the shared source the brief of 26 October asks for: every hosted tool has one entry with its four
    fields, the docs render from it, and a tool that creates is never called tested end to end beyond a dry run."""
    import asyncio
    from fabric_backend import server, tool_status as ts
    hosted = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert set(ts.STATUS) == hosted, sorted(set(ts.STATUS) ^ hosted)
    md = client.get("/docs.md").text
    for name, s in ts.STATUS.items():
        assert s.available in (ts.HOSTED, ts.OPERATOR) and s.kind in (ts.READS, ts.DRAFT, ts.CREATES) and s.changes and s.tested
        assert f"| `{name}` | {ts.label(name)} | {s.changes} | " in md, name
        if s.kind == ts.CREATES and s.live:                                       # a dry run, or what the one live call did
            assert (s.dry_run_only and "tested end to end as a dry run" in ts.label(name).lower()
                    or name in ts.LIVE_RUN_PARTLY and "update in place" in ts.label(name)), name
        if s.kind != ts.CREATES:
            assert s.changes.startswith("nothing"), name
    assert set(ts.LIVE_RUN) <= hosted and len(set(ts.LIVE_RUN)) == len(ts.LIVE_RUN)
    llms = client.get("/llms.txt").text
    assert all(f"`{t}`" in llms for t in ts.LIVE_RUN) and f"{len(ts.LIVE_RUN)} tools were run" in llms


def test_the_notes_in_the_tools_answers_follow_tool_status(monkeypatch):
    """The live test of 27 October 2026: lineage, app_readiness and others still answered "not yet run against a live
    workspace" after they had run live. Each tool's note about how far it has run now comes from
    tool_status.answer_note, so it changes with the status. Every hosted tool is called as the golden tests call it."""
    import sys
    import requests
    import golden_support as gs
    from test_golden import HOSTED_CALLS
    from fabric_backend import server, tool_status as ts
    fake = gs.FakeFabric()
    for verb in ("get", "post", "patch"):
        monkeypatch.setattr(requests, verb, getattr(fake, verb))
    monkeypatch.setitem(sys.modules, "pyodbc", gs.fake_pyodbc())
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "limiter", None)
    carried = set()
    for name, kwargs in HOSTED_CALLS:
        try:
            out = json.loads(getattr(server, name)(**kwargs))
        except ValueError:
            continue
        note = out.get("note") if isinstance(out, dict) else None
        if not isinstance(note, str):
            continue
        if ts.STATUS[name].live:
            assert "not yet run against a live" not in note.lower() and "26 october 2026, not yet" not in note.lower(), (name, note)
        if ts.answer_note(name) in note:
            carried.add(name)
    assert {"lineage", "app_readiness", "app_starter", "semantic_model_draft", "compare_semantic_model", "create_semantic_model",
            "create_views", "create_data_agent", "create_ontology", "silver_notebook_draft", "gold_views_draft",
            "drift_monitor_draft", "export_item_definitions"} <= carried, sorted(carried)



# ------------------------------------------------------------------ home page round 1: the guided ship-to example ------

def test_the_guided_example_follows_one_order_to_its_delivery_address(client):
    """The home page brief of 27 October 2026, round 1: one example all the way (customer, order, delivery address), the
    engine's suggestion with its data check, the visitor's review apart from the check, and a result card. Every pane
    is in the HTML, so the page reads without JavaScript; the script shows one step at a time."""
    from fabric_backend import demo
    html = client.get("/demo").text
    guide = re.search(r'<div class="guide" id="guide".*?<!-- /guide -->', html, re.S).group(0)
    assert "Where should each order be delivered?" in html
    steps = re.findall(r'<button type="button" class="guide-step"[^>]*data-step="(\d)"[^>]*>(.*?)</button>', guide, re.S)
    assert [n for n, _ in steps] == ["1", "2", "3", "4"]
    panes = re.findall(r'<section class="guide-pane" data-pane="(\d)"[^>]*>', guide)
    assert panes == ["1", "2", "3", "4"] and not re.search(r'class="guide-pane"[^>]*\shidden', guide)
    order = demo.demo_preview()[0]
    p1 = re.search(r'data-pane="1".*?</section>', guide, re.S).group(0)
    assert "Illustrative preview" in p1 and "synthetic" in p1 and "Delivery address not confirmed" in p1
    assert f">{order['order_id']}<" in p1 and f">{order['customer_id']}<" in p1 and f">{order['ship_to_id']}<" in p1
    p2 = re.search(r'data-pane="2".*?</section>', guide, re.S).group(0)
    assert "suggest_relationships" in p2 and "All 60 orders in this sample have a ship_to_id that exists in addresses" in p2
    assert "35 of 60" in p2                                                            # the next candidate, customers, does not hold
    assert "does not say what the column means" in p2
    why = re.search(r"<dt>Why</dt><dd>(.*?)</dd>", p2, re.S).group(1)
    assert why[:1].isupper() and why.endswith(".")                                  # a sentence of its own
    p3 = re.search(r'data-pane="3".*?</section>', guide, re.S).group(0)
    assert 'data-guide-decide="accept"' in p3 and 'data-guide-decide="open"' in p3 and "Nothing changes in Fabric" in p3
    p4 = re.search(r'data-pane="4".*?</section>', guide, re.S).group(0)
    for variant in ("accepted", "open"):
        card = re.search(rf'<div class="result-card" data-variant="{variant}".*?</div><!-- /card -->', p4, re.S).group(0)
        for head in ("You reviewed", "The data shows", "Still open", "Next"):
            assert head in card, (variant, head)
        assert "Demo with synthetic data" in card and 'data-copy="#guide-summary-' + variant + '"' in card
        rows = len(re.findall(r"<dt>", card))
        words = {3: "three", 4: "four", 5: "five", 6: "six"}
        assert not re.search(r"in (three|four|five|six) lines", card) or f"in {words[rows]} lines" in card, (variant, rows)
    opened = re.search(r'data-variant="open".*?<!-- /card -->', p4, re.S).group(0)
    assert "Delivery address not confirmed" in opened
    assert 'href="/docs#test-status"' in p4 and "create_backend" in p4                  # the app path carries its status
    assert '<button type="button" class="btn ghost small" data-guide="reset"' in guide


def test_accepting_in_the_guide_is_never_shown_as_a_check():
    """Proposal, review and check stay three things: the accepted card names the check as what the data shows and the
    meaning as the visitor's decision; neither card calls the meaning checked."""
    from fabric_backend import pages
    html = pages.render("/demo")
    accepted = re.search(r'data-variant="accepted".*?<!-- /card -->', html, re.S).group(0)
    assert "You accepted, in this demo" in accepted and "checked the meaning" not in accepted
    assert "The check counts values" in accepted


# ------------------------------------------------------------------ round n17: the guided demo on a page of its own ----

def test_the_guided_demo_has_a_page_of_its_own_and_home_a_short_way_in(client):
    """Round n17: the guided demo took 38 % of the start page at 1280 px. It is on /demo now, whole (the steps, the graph
    with its mascots, the details, the relationship list, the status pill), with its own title, description, canonical
    link and sitemap row, and links on to /explore and /start. The start page keeps a heading, one sentence and the
    button; the hero's button goes to /demo too."""
    home = client.get("/").text
    entry = re.search(r'<section class="wrap demo-entry" id="demo".*?</section>', home, re.S).group(0)
    assert '<h2 id="guide">Where should each order be delivered?</h2>' in entry
    sentences = re.findall(r"<p>(.*?)</p>", entry, re.S)
    assert len(sentences) == 1 and len(re.findall(r"[.!?](?=\s|$)", sentences[0])) == 1
    assert re.findall(r'<a [^>]*href="([^"]+)"[^>]*>([^<]+)</a>', entry) == [("/demo", "Try the guided demo")]
    for gone in ('class="guide"', 'id="home-graph"', 'class="rel-list"', 'id="home-details"', 'class="result-card"'):
        assert gone not in home, gone
    hero = re.search(r'<section class="hero">.*?</section>', home, re.S).group(0)
    assert re.findall(r'<a class="btn [^"]*" href="([^"]+)"', hero) == ["/demo", "/start"]

    demo = client.get("/demo").text
    assert "<title>Guided demo: where should each order be delivered? — Krusgraph</title>" in demo
    assert re.search(r'<meta name="description" content="Follow one order to its delivery address[^"]{60,}"', demo)
    assert '<link rel="canonical" href="https://krusgraph.test/demo">' in demo
    assert "<loc>https://krusgraph.test/demo</loc>" in client.get("/sitemap.xml").text
    assert '<a href="/" aria-current=page>Product</a>' in demo                          # under Product, like /explore
    assert demo.count("<h1") == 1 and '<h1 id="demo-h">Where should each order be delivered?</h1>' in demo
    assert '<span class="pill demo">Demo · synthetic data</span>' in demo and 'data-page="demo"' in demo
    for part in ('<div class="guide" id="guide"', 'id="home-graph"', 'id="home-why"', 'class="rel-list"', 'id="home-details"',
                 'data-variant="open"', 'data-variant="accepted"'):
        assert part in demo, part
    main = demo.split("<main", 1)[1].split("</main>", 1)[0]
    assert 'href="/explore"' in main and 'href="/start"' in main
    js = client.get("/static/site.js").text
    assert "document.querySelector('[data-page=demo]')" in js and "{ kind: 'onto'" in js      # the graph's mascots came along
    assert "[guided demo](/demo)" in client.get("/docs.md").text
    assert "](https://krusgraph.test/demo)" in client.get("/llms.txt").text


def test_old_links_into_the_demo_on_the_start_page_go_on_to_demo(client):
    """The old button pointed at /#guide, and people may have kept that address or another of the demo's ids. On the
    start page site.js sends each of them to the same anchor on /demo, where every one still exists; without
    JavaScript #demo and #guide land on the start page's way in, which links to /demo."""
    js = client.get("/static/site.js").text
    m = re.search(r"\[data-page=home\]'\) && /\^#\((.*?)\)\$/\.test\(location\.hash\)", js)
    ids = m.group(1).replace("guide-h[1-4]", "guide-h1|guide-h2|guide-h3|guide-h4").split("|")
    assert {"demo", "guide", "guide-h1", "home-graph"} <= set(ids)
    assert "location.replace('/demo' + location.hash)" in js
    demo = client.get("/demo").text
    for i in ids:
        assert f'id="{i}"' in demo, i
    home = client.get("/").text
    assert 'id="demo"' in home and 'id="guide"' in home


def _hub(client):
    html = client.get("/").text
    after_hero = html.split('<section class="hero">', 1)[1].split("</section>", 1)[1].lstrip()
    assert after_hero.startswith('<section class="wrap connects" aria-label="What Krusgraph connects">')
    row = after_hero.split("</section>", 1)[0]
    visual = re.search(r'<div class="hub" aria-hidden="true">(.*)</div>\s*<p class="muted tiny connects-note">', row, re.S).group(1)
    groups = {re.search(r'<p class="hub-h">(.*?)</p>', g).group(1): re.findall(r"<li><b>(.*?)</b>(.*?)</li>", g)
              for g in re.findall(r'<div class="hub-group[^"]*">(.*?)</ul></div>', visual, re.S)}
    said = re.search(r'<p class="visually-hidden">(.*?)</p>', row, re.S).group(1)
    return row, visual, groups, said


def _tag(rest):
    m = re.search(r'<span class="hub-tag[^"]*">(.*?)</span>', rest)
    return m.group(1) if m else None


def test_home_hub_shows_the_data_what_is_built_and_where_you_build_with_statuses_from_tool_status(client):
    """Gustav's brief of 27 October 2026: under the hero a hub, "Your data in Fabric" and "What Krusgraph builds in
    Fabric" on the left, Krusgraph in the middle ("one plan, the rule behind every relationship"), "Where you build" on
    the right, joined by lines as in the graph; text names only, no third-party logos; the disclaimer word for word. A
    built part says "creates" only when tool_status records it created live on the hosted service (the GraphQL API),
    "draft" otherwise; the warehouse and the SQL database, not yet read live, are marked experimental. With client
    registration off, the only MCP client named is Claude."""
    from fabric_backend import tool_status as ts
    row, visual, groups, said = _hub(client)
    assert list(groups) == ["Your data in Fabric", "What Krusgraph builds in Fabric", "Where you build"]
    assert [n for n, _ in groups["Your data in Fabric"]] == ["Lakehouse", "Warehouse", "SQL database"]
    assert {n: _tag(r) for n, r in groups["Your data in Fabric"]} == {"Lakehouse": None, "Warehouse": "experimental",
                                                                       "SQL database": "experimental"}
    built = {n: _tag(r) for n, r in groups["What Krusgraph builds in Fabric"]}
    assert built == {n: ts.build_word(t) for n, t in ts.BUILDS}                         # rendered from tool_status
    assert built == {"GraphQL API": "creates", "Power BI semantic model": "draft", "Fabric IQ ontology": "draft", "views": "draft",
                     "data agent": "draft", "silver notebooks": "draft"}                  # the live test of 27 October 2026
    assert groups["Where you build"] == [("Claude", '<span class="hub-via">via MCP</span>'),
                                         ("Lovable", '<span class="hub-via">via the GraphQL API</span>')]
    assert '<span class="c-hub">krusgraph</span>' in visual and "one plan, the rule behind every relationship" in visual
    assert visual.count('class="hub-link ') == 2                                        # the lines on the left; the right one is the hub's
    assert not re.search(r"<(img|svg|picture|object|image)\b", row) and "logo" not in row.lower() and "data-mascot" not in row
    plain = re.sub(r"<[^>]+>", " ", row)
    for other in ("VS Code", "Visual Studio", "Cursor", "Copilot", "ChatGPT", "Windsurf", "Claude Code", "Glama"):
        assert other not in plain, other
    for part in ("Lakehouse (tested end to end)", "Warehouse (experimental)", "SQL database (experimental)",
                 "one plan, with the rule behind every relationship", "it creates the GraphQL API",
                 "Power BI semantic model, Fabric IQ ontology, views, data agent and silver notebooks are drafts so far",
                 "Claude connects to Krusgraph through MCP",
                 "Lovable uses the GraphQL API Krusgraph creates in Fabric rather than Krusgraph itself"):
        assert part in said, part
    assert ('<p class="muted tiny connects-note">Independent product. Not affiliated with or endorsed by Microsoft, '
            'Anthropic or Lovable.</p>') in row


def test_home_hub_names_vs_code_and_cursor_once_the_hosted_service_signs_them_in(client, monkeypatch):
    """Cursor (and VS Code) only once a full sign-in through client registration is confirmed: tool_status.CLIENTS says
    Experimental for them (the brief of 28 October 2026: they reached the approval page, a full sign-in is not yet
    confirmed), so the hub names Claude only; recorded as tested, they join it, and Anysphere joins the disclaimer."""
    from fabric_backend import tool_status as ts
    monkeypatch.setenv("KRUSGRAPH_CLIENT_REGISTRATION", "1")
    row, visual, groups, said = _hub(client)
    assert [n for n, _ in groups["Where you build"]] == ["Claude", "Lovable"] and "Cursor" not in row
    monkeypatch.setitem(ts.CLIENTS_TESTED, "VS Code", ("/mcp/connect", "29 October 2026"))
    monkeypatch.setitem(ts.CLIENTS_TESTED, "Cursor", ("/mcp/connect", "29 October 2026"))
    row, visual, groups, said = _hub(client)
    assert [n for n, _ in groups["Where you build"]] == ["Claude", "VS Code", "Cursor", "Lovable"]
    assert "Claude, VS Code and Cursor connect to Krusgraph through MCP" in said
    assert "Not affiliated with or endorsed by Microsoft, Anthropic, Anysphere or Lovable.</p>" in row


def test_home_hub_follows_tool_status_when_another_part_is_tested(client, monkeypatch):
    from fabric_backend import tool_status as ts
    live = ts.ToolStatus(*ts._RAW["create_views"][:4], dry_run_only=False, name="create_views")
    monkeypatch.setitem(ts.STATUS, "create_views", live)
    monkeypatch.setattr(ts, "SOURCES", (("Lakehouse", True), ("Warehouse", True), ("SQL database", False)))
    row, visual, groups, said = _hub(client)
    assert {n: _tag(r) for n, r in groups["What Krusgraph builds in Fabric"]}["views"] == "creates"
    assert {n: _tag(r) for n, r in groups["Your data in Fabric"]}["Warehouse"] is None
    assert "it creates the GraphQL API and views" in said and "Warehouse (tested end to end)" in said


def test_start_docs_and_llms_send_other_clients_to_mcp_connect_only_when_registration_is_on(client, monkeypatch):
    start, docs, llms = client.get("/start").text, client.get("/docs").text, client.get("/llms.txt").text
    for text in (start, docs, llms):
        assert "/mcp/connect" not in text
    assert "that is the client it has been tested with" in start
    monkeypatch.setenv("KRUSGRAPH_CLIENT_REGISTRATION", "1")
    start, docs, llms = client.get("/start").text, client.get("/docs").text, client.get("/llms.txt").text
    assert "<code>https://krusgraph.test/mcp/connect</code>" in start and 'href="/docs#other-mcp-clients"' in start
    assert "a full sign-in is not yet confirmed (VS Code, Claude Code and Cursor)" in start      # the brief of 28 October 2026
    assert 'id="other-mcp-clients"' in docs and "https://krusgraph.test/mcp/connect" in docs
    for client_ in ("VS Code", "Cursor", "Glama", "Claude Code"):
        assert client_ in docs, client_
    assert "(not tried yet)" in docs and "unsupported protocol" in docs
    assert "streamable HTTP at `https://krusgraph.test/mcp/connect`" in llms and "docs.md#other-mcp-clients" in llms
    assert "that is the client it has been tested with" not in start and "cannot sign in to" not in llms
    home = client.get("/").text
    assert "Krusgraph connects Claude to Microsoft Fabric through MCP" in home              # VS Code and Cursor: Experimental (tool_status.CLIENTS)
