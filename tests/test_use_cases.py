"""/use-cases: the page, its Markdown twin, discovery entries, and every engine claim the scenarios make."""
import re

import pytest
from starlette.testclient import TestClient

from fabric_backend import server, use_cases
from fabric_backend.evidence import suggest_composite_keys
from fabric_backend.infer import plan


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


def test_page_renders_indexable_with_every_industry_and_the_footnote(client):
    r = client.get("/use-cases")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    html = r.text
    assert "{{" not in html
    assert 'name="robots" content="noindex' not in html and 'content="index,follow' in html
    assert '<link rel="canonical" href="https://krusgraph.test/use-cases">' in html
    assert '<link rel="alternate" type="text/markdown" href="/use-cases.md"' in html
    for ind in use_cases.INDUSTRIES:
        assert f'id="{ind["slug"]}"' in html and f'href="#{ind["slug"]}"' in html, ind["slug"]
        assert re.escape(ind["name"]) and ind["name"].replace("&", "&amp;") in html
    assert use_cases.FOOTNOTE in html
    assert "For Fabric consultancies" in html and 'href="/start"' in html and 'href="/docs"' in html
    assert "mailto:hello@krusgraph.test" in html
    assert html.count('data-mascot="') == 1                                 # one mascot moment
    assert "<script>" not in html and "<style" not in html                  # no inline script or style blocks
    assert ' style="' not in html.split('<main id="main"')[1].split("</main>")[0]
    for m in re.finditer(r'<(?:script|link|img)[^>]+(?:src|href)="([^"]+)"', html):
        if not m.group(0).startswith('<link rel="canonical"'):
            assert not m.group(1).startswith(("http://", "https://", "//")), m.group(0)


def test_page_keeps_out_what_it_must_not_claim(client):
    text = client.get("/use-cases").text + client.get("/use-cases.md").text
    low = text.lower().replace("based in uppsala, sweden, and bern, switzerland", "")    # n53: the footer's agreed fact
    for banned in ("switzerland", "swiss", "logistics", "warehousing", "distribution", "pharmacy", "wholesale", " ewm",
                   "trusted by", "customer story", "case study", "testimonial", "chf", "price:", "€", "$"):
        assert banned not in low, banned
    assert not re.search(r"\d+\s?%", text.split("<main")[1] if "<main" in text else text)      # no invented percentages


def test_nav_and_footer_link_the_page(client):
    for path in ("/", "/docs", "/use-cases"):
        html = client.get(path).text
        nav = html.split('id="site-nav"')[1].split("</nav>")[0]
        footer = html.split('class="footer-links"')[1].split("</nav>")[0]
        assert '<a href="/use-cases"' in nav and ">Use cases</a>" in nav, path
        assert '<a href="/use-cases">Use cases</a>' in footer, path
    assert '<a href="/use-cases" aria-current=page>' in client.get("/use-cases").text


def test_markdown_twin_sitemap_and_llms(client):
    r = client.get("/use-cases.md")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    md = r.text
    assert md.startswith("# Use cases") and "{{" not in md and "<div" not in md and "<svg" not in md
    for ind in use_cases.INDUSTRIES:
        assert f"## {ind['name']}" in md
    assert use_cases.FOOTNOTE in md and "https://krusgraph.test/start" in md and "hello@krusgraph.test" in md
    assert "<loc>https://krusgraph.test/use-cases</loc>" in client.get("/sitemap.xml").text
    assert "(https://krusgraph.test/use-cases.md)" in client.get("/llms.txt").text
    assert "<!-- https://krusgraph.test/use-cases.md -->" in client.get("/llms-full.txt").text


def _rel(p, source, cols, target):
    cols = cols.split("+")
    return next((r for r in p.relationships if r.source == source and r.source_cols == cols and r.target == target), None)


@pytest.mark.parametrize("ind", use_cases.INDUSTRIES, ids=lambda i: i["slug"])
def test_every_claim_is_what_the_engine_does(ind):
    c = ind["checks"]
    s = use_cases.schema_of(ind)
    names = plan(s)
    given = plan(s, keys=c.get("keys_given"))
    for table, cols, rule in c.get("keys", []):
        assert names.keys[table] == (cols.split("+"), rule), (table, names.keys.get(table))
    for source, col, target, rule, field in c.get("fields", []):                     # weaker R4 role matches
        r = _rel(names, source, col, target)
        assert r and r.rule == rule and r.field_name == field, (source, col)
    for source, cols, target, rule in c.get("links", []):
        r = _rel(names, source, cols, target)
        assert r and r.rule == rule, (source, cols, target)
    for source, cols, target, rule in c.get("links_after_keys", []):
        assert _rel(names, source, cols, target) is None, "only after the key is given"
        r = _rel(given, source, cols, target)
        assert r and r.rule == rule, (source, cols, target)
    assert sorted(names.keyless) == sorted(c.get("keyless", [])), names.keyless
    sugg = {(x["table"], "+".join(x["columns"])) for x in suggest_composite_keys(names)}
    assert sugg == set(c.get("suggested", [])), sugg
    for table, key in c.get("keys_given", {}).items():
        assert given.keys[table] == (key, "K1")
    for source, col, target, tcol, field in c.get("roles", []):          # role columns: unlinked by names, a field once confirmed
        assert not any(r.source == source and col in r.source_cols for r in given.relationships), col
        conf = plan(s, keys=c.get("keys_given"), confirmed=[{"source": source, "source_cols": [col], "target": target, "target_cols": [tcol]}])
        assert _rel(conf, source, col, target).field_name == field
    for source, col, target in c.get("gone_after_keys", []):
        assert _rel(names, source, col, target) and _rel(given, source, col, target) is None, (source, col)
    for source, col in c.get("not_linked", []):
        assert not any(r.source == source and col in r.source_cols for r in given.relationships)
    assert not names.ambiguous and not given.ambiguous


@pytest.mark.parametrize("ind", use_cases.INDUSTRIES, ids=lambda i: i["slug"])
def test_text_names_only_tables_and_columns_that_exist(ind):
    tables = {t: set(cols.split()) for t, cols in ind["tables"].items()}
    allcols = set().union(*tables.values())
    text = " ".join(t for _c, t in ind["finds"]) + " " + " ".join(ind["build"] + ind["value"])
    for code in re.findall(r"`([^`]+)`", text):
        for part in re.split(r"\s*\+\s*", code):
            if "." in part:
                t, col = part.split(".", 1)
                assert t in tables and col in tables[t], code
            elif (part.endswith("_id") or part.endswith("_no")) and not part.startswith("_"):
                assert part in allcols, code
    for code, _t in ind["finds"]:
        assert code in {"K1", "K2", "K3", "K4", "K5", "R1", "R2", "R3", "R4", "suggested", "confirm"}
    assert 4 <= len(ind["tables"]) <= 8 and 2 <= len(ind["finds"]) <= 3 and ind["color"] in use_cases.COLORS


def test_sections_in_the_maintainers_order():
    assert [i["slug"] for i in use_cases.INDUSTRIES] == ["retail", "manufacturing", "saas", "professional-services", "aml",
                                                         "financial-crime", "pharma-research", "environment", "property", "education"]


def test_sketch_is_engine_output():
    sk = use_cases.sketch("retail")
    lines = next(t for t in sk["tables"] if t["name"] == "order_lines")
    assert lines["key"] == ["order_id", "line_no"] and lines["rule"] == "K5"
    orders = next(t for t in sk["tables"] if t["name"] == "orders")
    assert orders["key"] == ["order_id"] and orders["rule"] == "K2"
    assert next(c for c in orders["columns"] if c["name"] == "customer_id")["link"] == ("customers", "R1")
