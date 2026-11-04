"""Round n92 (Gustav's decision of 4 November 2026): the chat demo on the start page.

The numbers the chat shows come from /demo/plan.json, the engine's output on the synthetic shop, and these tests fail when
they change: the ship_to_id suggestion counted in seed.rows(), the drafts' counts (ontology, semantic model, data
products) as the engine computes them, before and after the suggestion is confirmed. The page loads only a small button;
the chat's files load on the first click; the chat fetches /demo/plan.json and nothing else, stores nothing, and its
"Planned" choices run nothing. The browser checks of the flow are in tests/test_browser.py (chat_demo_browser.js).
"""
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import domains, evidence, ontology, pages, semantic_model, tool_status as ts
from fabric_backend.demo import DEMO_KEYS, _demo_db, demo_plan
from fabric_backend.infer import plan
from fabric_backend.seed import rows, schema

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "fabric_backend" / "static"
CHAT_JS = (STATIC / "chat-demo.js").read_text(encoding="utf-8")
CHAT_CSS = (STATIC / "chat-demo.css").read_text(encoding="utf-8")
SITE_JS = (STATIC / "site.js").read_text(encoding="utf-8")
CHAT_CODE = re.sub(r"(?m)^\s*//.*$|\s//\s.*$", "", re.sub(r"/\*.*?\*/", "", CHAT_JS, flags=re.S))     # without comments


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    from fabric_backend.server import build_app
    with TestClient(build_app()) as c:
        yield c


def _launcher(text: str) -> str:
    m = re.search(r'<button class="kgc-launch"[^>]*>.*?</button>', text, re.S)
    assert m, "no chat button on the start page"
    return m.group(0)


def _strings(js: str) -> str:
    """The text in the script's string literals: what the chat can say."""
    return " ".join(m.group(2) for m in re.finditer(r"(['\"])((?:\\.|(?!\1).)*)\1", js))


# ------------------------------------------------------------------ the numbers, from the engine ---------------------
def test_ship_to_id_counted_in_the_seed_rows_15_values_and_60_rows():
    """Counted in seed.rows() on 3 November 2026: 15 of 15 different values of orders.ship_to_id are in addresses, and
    60 of 60 rows. The plan's suggestion says the same, and the chat says "values" for 15 and "rows" for 60."""
    order_cols = [c.name for c in next(t for t in schema("shop") if t.name == "orders").columns]
    addr_cols = [c.name for c in next(t for t in schema("shop") if t.name == "addresses").columns]
    ship = [r[order_cols.index("ship_to_id")] for r in rows()["orders"] if r[order_cols.index("ship_to_id")] is not None]
    ids = {r[addr_cols.index("address_id")] for r in rows()["addresses"]}
    assert len(ship) == 60 and sum(v in ids for v in ship) == 60
    assert len(set(ship)) == 15 and len(set(ship) & ids) == 15
    [sug] = demo_plan()["suggestions"]
    ev = sug["evidence"]
    assert (sug["table"], sug["column"], sug["target"], sug["target_cols"]) == ("orders", "ship_to_id", "addresses", ["address_id"])
    assert (ev["distinct_values"], ev["matched"], ev["rows_with_value"]) == (15, 60, 60)
    # the chat: every row matches, so every one of the distinct values does
    assert "'All ' + ev.distinct_values + ' of its values exist in '" in CHAT_JS
    assert "', in ' + ev.matched + ' of ' + ev.rows_with_value + ' rows.'" in CHAT_JS


def test_the_drafts_in_the_plan_are_the_engines_and_these_are_the_counts():
    """The sketch said 6 entity types; the engine's ontology_draft gives 7 (5 with a key), with 6 relationship types, 7
    once ship_to_id is confirmed. domain_draft gives the data products customers and products with one interface and
    audit_log left out (no key). semantic_model_draft: 7 tables, 6 active relationships, and with the confirmed link a 7th,
    inactive (addresses.customer_id → customers would close a cycle); 5 measures and the Calendar date table."""
    d = demo_plan()["drafts"]
    sug = demo_plan()["suggestions"][0]["confirmed"]
    for name, confirmed in (("as_is", None), ("with_suggestion", [sug])):
        p = plan(schema("shop"), keys=DEMO_KEYS, confirmed=confirmed)
        o, m = ontology.summary(p), semantic_model.draft(p, {"item_name": "shop"}, "shop_model")["summary"]
        dom, v = domains.propose_plan(p), evidence.validate(p, _demo_db())
        got = d[name]
        assert got["relationships"] == len(p.relationships)
        assert got["ontology"] == {"tool": "ontology_draft", "entity_types": o["entity_types"], "with_key": o["with_key"],
                                   "relationship_types": o["relationship_types"]}
        assert (got["semantic_model"]["tables"], got["semantic_model"]["active"], got["semantic_model"]["measures"]) == (
            m["tables"], m["relationships_active"], len(m["measures"]))
        assert [x["name"] for x in got["domains"]["domains"]] == [x["name"] for x in dom["domains"]]
        assert got["validation"]["summary"] == v["summary"]
    a, w = d["as_is"], d["with_suggestion"]
    assert (a["relationships"], w["relationships"]) == (6, 7)
    assert a["ontology"]["entity_types"] == w["ontology"]["entity_types"] == 7
    assert a["ontology"]["with_key"] == w["ontology"]["with_key"] == 5
    assert (a["ontology"]["relationship_types"], w["ontology"]["relationship_types"]) == (6, 7)
    assert a["semantic_model"] == {"tool": "semantic_model_draft", "tables": 7, "active": 6, "inactive": [], "measures": 5, "date_table": "Calendar"}
    assert w["semantic_model"]["active"] == 6 and w["semantic_model"]["inactive"] == [
        {"source": "addresses", "columns": ["customer_id"], "target": "customers"}]
    assert (a["validation"]["hold"], a["validation"]["relationships"], w["validation"]["hold"], w["validation"]["relationships"]) == (6, 6, 7, 7)
    for x in (a, w):
        assert x["domains"]["domains"] == [{"name": "customers", "tables": ["addresses", "customers", "order_items", "orders"]},
                                           {"name": "products", "tables": ["categories", "products"]}]
        assert x["domains"]["interfaces"] == [{"source": "order_items", "source_cols": ["product_id"], "target": "products"}]
        assert x["domains"]["unassigned"] == ["audit_log"] == demo_plan()["keyless"]


def test_the_plan_json_carries_what_the_chat_reads(client):
    d = client.get("/demo/plan.json").json()
    assert len(d["tables"]) == 7 and len(d["relationships"]) == 6 and d["keyless"] == ["audit_log"]
    assert set(d["drafts"]) == {"as_is", "with_suggestion"}
    for key in ("P.tables", "P.relationships", "P.suggestions", "P.keyless", "P.drafts.with_suggestion", "P.drafts.as_is"):
        assert key in CHAT_JS, key
    # no number about the shop is typed into the chat
    said = _strings(CHAT_JS)
    assert not re.search(r"\b(6|7|15|60|134)\b", said), re.findall(r"[^.]*\b(?:6|7|15|60|134)\b[^.]*", said)
    assert "window.KGC_PLAN" not in CHAT_JS and "KGC_PLAN" not in CHAT_JS


# ------------------------------------------------------------------ the page loads only the button -------------------
def test_the_start_page_loads_only_the_button_and_not_the_chat(client):
    text = client.get("/").text
    button = _launcher(text)
    assert " hidden " in button and 'type="button"' in button and ">Try a demo</button>" in button
    v = pages.asset_version()
    assert f'data-js="/static/chat-demo.js?v={v}"' in button and f'data-css="/static/chat-demo.css?v={v}"' in button
    rest = text.replace(button, "")
    assert "chat-demo" not in rest
    assert re.findall(r'<script src="([^"?]+)', text) == ["/static/mascots.js", "/static/site.js"]
    assert re.findall(r'<link rel="stylesheet" href="([^"?]+)', text) == ["/static/site.css"]
    assert "kgc" not in client.get("/check").text and "kgc" not in client.get("/docs").text      # the start page only
    # the replay stays, and the chat's files are served
    assert "A replay of a session in Claude" in text
    for name, kind in (("chat-demo.js", "text/javascript"), ("chat-demo.css", "text/css")):
        r = client.get(f"/static/{name}?v={v}")
        assert r.status_code == 200 and r.headers["content-type"].startswith(kind)


def test_the_launcher_in_site_js_loads_the_chat_only_on_a_click():
    part = SITE_JS[SITE_JS.index("n92: the chat demo's button"):SITE_JS.index("window.KrusGraph = ")]
    click = part.index("addEventListener('click'")
    assert "createElement('script')" in part[click:] and "createElement('link')" in part[click:]
    assert "createElement('script')" not in part[:click] and "fetch(" not in part
    assert "kgc.hidden = false" in part and "KrusgraphChat.open" in part
    for word in ("localStorage", "sessionStorage", "cookie", "sendBeacon", "/check/event"):
        assert word not in part, word


# ------------------------------------------------------------------ no request but the plan, nothing stored ----------
def test_the_chat_fetches_the_plan_and_nothing_else_and_stores_nothing():
    assert re.findall(r"\bfetch\(([^,)]+)", CHAT_JS) == ["PLAN_URL"] and "var PLAN_URL = '/demo/plan.json';" in CHAT_JS
    for word in ("localStorage", "sessionStorage", "indexedDB", "document.cookie", "sendBeacon", "XMLHttpRequest", "WebSocket",
                 "EventSource", "new Image", "/check/event", "navigator.", "history.", "_blank", "http:", "https:",
                 "<input", "<textarea", "contenteditable", "prompt("):
        assert word not in CHAT_CODE, word
    assert not re.search(r"\.target\s*=[^=]|'target'|target=", CHAT_JS)          # links open in the same tab
    # the links: the check page, its example and the start page's Connect, in the same tab
    hrefs = set(re.findall(r"href: '([^']+)'", CHAT_JS))
    assert hrefs == {"/check", "/check?example=sample", "/#connect"}


def test_the_planned_choices_run_nothing():
    """Fix data issues and Create a dbt flow are "Planned": they have no step to run, a click only says what exists today,
    and the second click does nothing (the browser checks the same on screen). No dates or times."""
    block = CHAT_JS[CHAT_JS.index("function planned()"):CHAT_JS.index("function drafts()")]
    labels = re.findall(r"label: '([^']+)', planned: ", block)
    assert labels == ["Fix data issues", "Create a dbt flow"]
    assert "go:" not in block and "href:" not in block
    handler = CHAT_JS[CHAT_JS.index("if (p.planned) {"):CHAT_JS.index("log.focus({ preventScroll: true });")]
    assert "return;" in handler and "p.go" not in handler and "aria-disabled" in handler
    said = _strings(block)
    assert "is planned" in said and "today" in said.lower()
    assert not re.search(r"\b(soon|coming|shortly|later this|next (week|month|quarter|year)|Q[1-4]|20\d\d|in \d+ (days|weeks|months))\b", _strings(CHAT_JS), re.I)


def test_every_result_says_nothing_was_created_and_what_the_agent_does_by_tool_status(client):
    button = _launcher(client.get("/").text)
    for key, draft, create in pages.CHAT_RESULTS:
        tool = create or draft
        assert f'data-tool-{key}="{tool}"' in button
        status = pages.chat_status(tool)
        assert f'data-status-{key}="{status}"' in button and status.startswith(ts.word(tool)[0].lower() + ts.word(tool)[1:])
        does = "creates" if create and ts.build_word(create) == "creates" else "drafts"
        assert f'data-does-{key}="{does}"' in button
    assert 'data-does-products="drafts"' in button and 'data-status-products="draft only"' in button   # domain_draft creates nothing
    assert "This is a demo, so nothing was created. " in CHAT_JS
    assert "your agent creates this in your Fabric workspace when you ask." in CHAT_JS
    assert "your agent drafts this from your own tables when you ask; the draft creates nothing in Fabric." in CHAT_JS
    assert "Status of ' + code(data(key, 'tool'))" in CHAT_JS
    assert "The ontology item is in preview in Fabric." in CHAT_JS
    low = _strings(CHAT_JS).lower()
    assert "bubble" not in low and "in claude" not in low and "in your agent" not in low


def test_the_sales_word_test_covers_the_chat(client):
    from tests.test_site import SALES
    text = (_strings(CHAT_JS) + " " + _launcher(client.get("/").text)).lower()
    for word in SALES:
        assert word not in text, word


# ------------------------------------------------------------------ accessibility and the phone, in the code ---------
def test_the_chat_css_keeps_to_the_tokens_the_phone_and_reduced_motion():
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", CHAT_CSS)                 # colours are the site's tokens
    assert "@media (max-width: 560px)" in CHAT_CSS and "html.kgc-lock, html.kgc-lock body { overflow: hidden }" in CHAT_CSS
    for side in ("bottom", "left", "right"):
        assert f"env(safe-area-inset-{side}, 0px)" in CHAT_CSS, side
    reduced = CHAT_CSS[CHAT_CSS.index("@media (prefers-reduced-motion: reduce)"):]
    assert "animation: none !important; transition: none !important" in reduced
    assert 'html[data-mascots="off"] .kgc-fig { display: none }' in CHAT_CSS
    assert "e.key === 'Escape'" in CHAT_JS and "launch.focus(" in CHAT_JS and "setAttribute('inert'" in CHAT_JS


def test_site_md_describes_the_chat():
    md = (ROOT / "docs" / "SITE.md").read_text(encoding="utf-8")
    sec = md[md.index("## The chat demo on the start page"):]
    for words in ("chat-demo.js", "/demo/plan.json", "Planned", "localStorage", "560 px", "Mascots: off", "tool_status",
                  "connect-src"):
        assert words in sec, words
