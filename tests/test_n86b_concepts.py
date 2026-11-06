"""n86b: the Concepts pages of /docs (How it works, Ontologies, Data products, How they connect, Vision), the question mark
next to "ontology" and "data products" in the chat demo and on /check, and the links into the pages. The examples come
from the engine on the shop schema and the statuses from tool_status, never typed by hand; the vision text is verbatim."""
import json
import re

import pytest
import yaml
from starlette.testclient import TestClient

from fabric_backend import concepts, domains, ontology, pages, seed, server, tool_status as ts
from fabric_backend.infer import plan

CONCEPTS = ["/docs/concepts", "/docs/concepts/how-it-works", "/docs/concepts/ontologies", "/docs/concepts/data-products",
            "/docs/concepts/how-they-connect", "/docs/concepts/vision"]
VISION = ["One place for your Fabric data. Proof at every step.", "Where Krusgraph is today, and where it is going.",
          "Available today", "Check and create", "Map how your tables connect", "Count every link against the rows",
          "Create Fabric items when you ask", "Next", "Check what comes in", "See if incoming data matches its source",
          "Set up Fabric's own tools, with your approval", "Vision", "One place for the whole chain",
          "From source system to report", "Any source, with the tool you choose",
          "The goal: nothing gets built on a link nobody counted.", "Next and Vision are direction, not current features."]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


def _main(text: str) -> str:
    return text[text.index('<article class="prose docs">'):text.index("</article>")]


def _plain(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).replace("&#x27;", "'").replace("&#39;", "'").replace("&amp;", "&")


def test_the_concepts_group_sits_after_get_started_with_its_pages_in_the_menu(client):
    ps = pages.docs_pages()
    assert [x["path"] for x in ps if x["path"].startswith("/docs/concepts")] == CONCEPTS
    assert pages.DOCS_GROUPS.index("Concepts") == pages.DOCS_GROUPS.index("Get started") + 1
    menu = re.search(r'<nav class="docs-menu"[^>]*>(.*?)</nav>', client.get("/docs").text, re.S).group(1)
    for path in CONCEPTS:
        assert f'href="{path}"' in menu and client.get(path).status_code == 200, path
    assert menu.index('href="/docs/get-started/first-time-errors"') < menu.index('href="/docs/concepts"') < menu.index('href="/docs/explore-and-check"')


def test_the_examples_are_the_engines_output_on_the_shop_schema(client):
    p = plan(seed.schema("shop"))
    d = domains.draft(p, "shop", "shop_lh")
    assert [x["name"] for x in d["domains"]] == ["customers", "products"]
    onto, dp, conn = (_plain(_main(client.get(x).text)) for x in CONCEPTS[2:5])
    for t, key, cols, _rule in ontology._model(p, None):                 # every entity type with its key, or why it has none
        assert ontology.entity_name(t.name) in onto
        assert (key in onto) if key else ("composite" in onto if len(cols) > 1 else "no key" in onto)
    s = ontology.summary(p)
    assert f"{s['entity_types']} entity types, {s['with_key']} of them with a key, and {s['relationship_types']} relationship types" in onto
    assert "OrderItemsHasProducts" in onto and "order_id + line_no" in onto and "a person chooses" in onto
    i = d["interfaces"][0]
    assert (i["source"], i["source_cols"], i["target"], i["target_cols"]) == ("order_items", ["product_id"], "products", ["product_id"])
    assert "order_items.product_id → products.product_id" in dp and "audit_log" in dp and "Unassigned" in dp and "no key" in dp
    for name in ("customers", "products"):
        assert name in dp
    # the ODCS excerpt is cut from the contract the engine wrote: every line of it is a line of that contract (or an elision)
    excerpt = concepts.odcs_excerpt()
    contract = d["contracts"]["customers"].splitlines()
    for line in excerpt.splitlines():
        assert line in contract or line.strip().startswith("# …"), line
    assert yaml.safe_load(excerpt)["kind"] == "DataContract" and "products.product_id" in excerpt and excerpt in pages.docs_md()
    assert "OrderItemsHasProducts" in conn and "customers holds the reference, products owns the key" in conn


def test_statuses_come_from_tool_status(client):
    onto, dp = (_plain(_main(client.get(x).text)) for x in CONCEPTS[2:4])
    assert f"Creating the ontology item from the plan: {ts.short('create_ontology')}." in onto and "preview" in onto
    assert f"domain_draft : {ts.label('domain_draft')}" in dp or f"domain_draft: {ts.label('domain_draft')}" in dp
    assert ts.label("domain_draft") == "Draft only" and "drafts to review" in dp
    how = _plain(_main(client.get(CONCEPTS[1]).text))
    for name, tool in ts.BUILDS:
        assert concepts._item_tag(tool) in how, tool
    for name, tested in ts.SOURCES:
        assert name in how
    assert ts.task_status(["plan_backend", "validate_plan"]) in how


def test_the_pages_link_to_the_rdfxml_download_the_example_and_each_other(client):
    onto = client.get(CONCEPTS[2]).text
    assert 'href="/check?example=sample#check-evidence"' in onto and "RDF/XML" in onto
    assert 'href="/check?example=sample"' in client.get(CONCEPTS[3]).text
    assert 'href="/docs/build-from-a-plan/fabric-iq-the-same-graph-as-an-ontology#fabric-iq-the-same-graph-as-an-ontology"' in onto


def test_the_vision_is_html_with_the_text_verbatim_and_said_as_direction(client):
    html = _main(client.get(CONCEPTS[5]).text)
    plain = _plain(html)
    for line in VISION:
        assert line in plain, line
        assert line in pages.docs_md().replace("**", ""), line
    assert "<img" not in html and html.count('class="cx-v-card') == 3 and html.count('class="cx-v-arrow"') == 2
    assert 'class="cx-v-card cx-v-now"' in html and 'class="cx-v-card cx-v-next"' in html and 'class="cx-v-card cx-v-vision"' in html
    css = (pages.STATIC_DIR / "site.css").read_text()
    assert "@media (max-width:760px)" in css[css.index(".cx-v-row"):]
    assert re.search(r"\.cx-v-now\{[^}]*var\(--coral-soft\)[^}]*2px solid var\(--coral\)", css)
    assert re.search(r"\.cx-v-next\{[^}]*var\(--card-2\)[^}]*1px solid", css)
    assert re.search(r"\.cx-v-vision\{[^}]*var\(--card\)[^}]*dashed", css)


def test_no_images_from_outside_no_logos_no_sales_words_and_no_claims_of_benefit_or_time(client):
    from tests.test_site import SALES
    for path in CONCEPTS:
        main = _main(client.get(path).text)
        assert "<img" not in main and "http://" not in main and not re.search(r'src="https?://', main), path
        low = _plain(main).lower()
        for w in SALES + ("logo", "faster", "minutes", "hours", "days", "save time", "data mesh"):
            assert w not in low, (path, w)


def test_markdown_llms_and_sitemap_carry_the_same_pages_and_facts(client):
    md = client.get("/docs.md").text
    assert "## Concepts" in md and "### Vision" in md and concepts.domains_md() in md and concepts.entities_md() in md
    full, llms, sitemap = client.get("/llms-full.txt").text, client.get("/llms.txt").text, client.get("/sitemap.xml").text
    assert concepts.trace_md() in full
    for path in CONCEPTS:
        assert f"(https://krusgraph.test{path})" in llms and f"<loc>https://krusgraph.test{path}</loc>" in sitemap


def test_the_tips_are_on_the_chat_pages_and_check_and_link_to_the_concept_pages(client):
    for path in ("/", "/docs", "/check", "/docs/concepts/vision"):
        raw = re.search(r'<script type="application/json" id="kg-tips">(.*?)</script>', client.get(path).text).group(1)
        data = json.loads(raw)
        assert set(data) == {"ontology", "data-products"}, path
        for t in data.values():
            assert client.get(t["href"]).status_code == 200 and "{P}" not in t["text"]
            assert len(re.findall(r"[.!?](?:\s|$)", t["text"])) == 2, t["text"]           # two sentences
    assert "id=\"kg-tips\"" not in client.get("/privacy").text or "kgcLaunch" in client.get("/privacy").text
    site = (pages.STATIC_DIR / "site.js").read_text()
    assert "window.KGTip" in site and "aria-expanded" in site and "'Escape'" in site and "mouseover" not in site[site.index("KGTip") - 3000:]
    chat = (pages.STATIC_DIR / "chat-demo.js").read_text()
    assert "tip('ontology')" in chat and "tip('data-products')" in chat
    check = (pages.STATIC_DIR / "check.js").read_text()
    assert 'tip("ontology")' in check and 'tip("data-products")' in check and 'href: "/docs/concepts/data-products"' in check


def test_the_home_page_steps_link_to_the_concept_pages(client):
    home = client.get("/").text
    steps = home[home.index('<ol class="steps">'):home.index("</ol>", home.index('<ol class="steps">'))]
    for path in ("/docs/concepts/how-it-works", "/docs/concepts/how-they-connect", "/docs/concepts/ontologies", "/docs/concepts/data-products"):
        assert f'href="{path}"' in steps, path
