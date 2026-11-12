"""Round n92 (Gustav's decision of 4 November 2026): the chat demo on the start page; round n93 (his decision of the same
day): pictures in the chat, Connect to the set-up guide, the button on every ordinary page, a memory within the tab.

The numbers the chat shows come from /demo/plan.json, the engine's output on the synthetic shop, and these tests fail when
they change: the ship_to_id suggestion counted in seed.rows(), the drafts' counts and lists (ontology, semantic model,
data products) as the engine computes them, before and after the suggestion is confirmed. A page loads only a small
button; the chat's files load on a click or to restore a chat left open; the chat fetches /demo/plan.json and nothing
else, keeps its steps in sessionStorage under one key and nowhere else, and its "Planned" choices run nothing. What it
says about creating is a sentence built from tool_status. The browser checks of the flow are in tests/test_browser.py
(chat_demo_browser.js).
"""
import json
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import demo, domains, evidence, ontology, pages, semantic_model, tool_status as ts
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
        assert {k: got["ontology"][k] for k in ("tool", "entity_types", "with_key", "relationship_types")} == {
            "tool": "ontology_draft", "entity_types": o["entity_types"], "with_key": o["with_key"], "relationship_types": o["relationship_types"]}
        assert (got["semantic_model"]["tables"], got["semantic_model"]["active"], got["semantic_model"]["measures"]) == (
            m["tables"], m["relationships_active"], len(m["measures"]))
        assert [x["name"] for x in got["domains"]["domains"]] == [x["name"] for x in dom["domains"]]
        assert got["validation"]["summary"] == v["summary"]
    a, w = d["as_is"], d["with_suggestion"]
    for x in (a, w):                                  # n93: the lists the pictures draw agree with the counts
        o, m = x["ontology"], x["semantic_model"]
        assert len(o["entities"]) == o["entity_types"] and sum(e["key"] for e in o["entities"]) == o["with_key"]
        assert len(o["links"]) == o["relationship_types"]
        assert len(m["table_names"]) == m["tables"] and sum(r["active"] for r in m["relationships"]) == m["active"]
        assert [{"source": r["source"], "columns": r["columns"], "target": r["target"]} for r in m["relationships"] if not r["active"]] == m["inactive"]
    assert (a["relationships"], w["relationships"]) == (6, 7)
    assert a["ontology"]["entity_types"] == w["ontology"]["entity_types"] == 7
    assert a["ontology"]["with_key"] == w["ontology"]["with_key"] == 5
    assert (a["ontology"]["relationship_types"], w["ontology"]["relationship_types"]) == (6, 7)
    counts = ("tool", "tables", "active", "inactive", "measures", "date_table")
    assert {k: a["semantic_model"][k] for k in counts} == {"tool": "semantic_model_draft", "tables": 7, "active": 6, "inactive": [], "measures": 5, "date_table": "Calendar"}
    assert w["semantic_model"]["active"] == 6 and w["semantic_model"]["inactive"] == [
        {"source": "addresses", "columns": ["customer_id"], "target": "customers"}]
    assert (a["validation"]["hold"], a["validation"]["relationships"], w["validation"]["hold"], w["validation"]["relationships"]) == (6, 6, 7, 7)
    assert [(e["name"], e["table"], e["key"]) for e in a["ontology"]["entities"]] == [
        ("Customers", "customers", True), ("Categories", "categories", True), ("Products", "products", True),
        ("Addresses", "addresses", True), ("Orders", "orders", True), ("OrderItems", "order_items", False),
        ("AuditLog", "audit_log", False)]                     # order_items: a composite key; audit_log: none
    assert {"source": "orders", "target": "addresses"} in w["ontology"]["links"] and {"source": "orders", "target": "addresses"} not in a["ontology"]["links"]
    assert a["semantic_model"]["table_names"] == ["customers", "categories", "products", "addresses", "orders", "order_items", "audit_log"]
    assert all(r["active"] for r in a["semantic_model"]["relationships"]) and len(a["semantic_model"]["relationships"]) == 6
    assert [(r["source"], r["columns"], r["target"], r["active"]) for r in w["semantic_model"]["relationships"][:3]] == [
        ("orders", ["ship_to_id"], "addresses", True), ("products", ["category_id"], "categories", True),
        ("addresses", ["customer_id"], "customers", False)]
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
    for key in ("o.entities", "o.links", "m.table_names", "m.relationships", "d.interfaces", "d.unassigned", "P.drafts.as_is.domains"):
        assert key in CHAT_JS, key                    # n93: what the pictures draw
    # no number about the shop is typed into the chat
    said = _strings(CHAT_JS)
    assert not re.search(r"\b(6|7|15|60|134)\b", said), re.findall(r"[^.]*\b(?:6|7|15|60|134)\b[^.]*", said)
    assert "window.KGC_PLAN" not in CHAT_JS and "KGC_PLAN" not in CHAT_JS


def test_no_table_column_or_entity_name_is_typed_into_the_chat():
    """n93: the pictures are drawn from /demo/plan.json: no table, column or entity type name of the shop is written in
    chat-demo.js, neither as a string nor as a word of the code, and no count of the shop either (the numbers in the code
    are the drawing's sizes)."""
    p = demo_plan()
    names = {t["name"] for t in p["tables"]} | {c["name"] for t in p["tables"] for c in t["columns"]}
    names |= {e["name"] for e in p["drafts"]["as_is"]["ontology"]["entities"]} | {p["drafts"]["as_is"]["semantic_model"]["date_table"]}
    strings = set(m.group(2) for m in re.finditer(r"(['\"])((?:\\.|(?!\1).)*)\1", CHAT_CODE))
    for name in sorted(names):
        assert name not in strings, name
        hits = [m.group(0) for m in re.finditer(r"[\w.]*\b%s\b[\w.]*" % re.escape(name), CHAT_CODE)]
        # English words that are also names of the shop's tables (the chat's "data products" and "customers"), never as
        # a name in a string or in a lookup: only inside longer text
        assert all(name in ("products", "customers", "orders", "name", "id", "event", "country", "city") for _ in hits), (name, hits)
    for word in ("ship_to_id", "order_items", "audit_log", "addresses", "categories", "OrderItems", "AuditLog", "Calendar"):
        assert word not in CHAT_CODE, word


# ------------------------------------------------------------------ the page loads only the button -------------------
def _html_routes(client):
    """Every HTML page the site serves, with its response (n93): the registered pages, the Markdown pages, the consent
    return page and the 404 page."""
    paths = list(pages.PAGES) + ["/privacy", "/docs", "/lovable", "/local", pages.CONSENT_PATH, "/no-such-page", "/blog", pages.BLOG_TOTALS]
    return {p: client.get(p, headers={"accept": "text/html"}) for p in paths}


def test_every_ordinary_page_loads_only_the_button_and_not_the_chat(client):
    """n93: the button is on every page with the site's header except /demo (n154: the home page and /check included);
    the page loads only the button (after the footer, hidden without JavaScript), never the chat's script or styles."""
    v = pages.asset_version()
    home = client.get("/").text
    assert re.findall(r'<script src="([^"?]+)', home) == ["/static/mascots.js", "/static/site.js"]
    assert re.findall(r'<link rel="stylesheet" href="([^"?]+)', home) == ["/static/site.css"]
    with_button = []
    for path, r in _html_routes(client).items():
        assert r.headers["content-type"].startswith("text/html"), path
        text = r.text
        assert 'class="site-header"' in text, path
        button = _launcher(text)
        assert text.count('id="kgcLaunch"') == 1, path
        assert " hidden " in button and 'type="button"' in button and ">Try a demo</button>" in button, path
        assert f'data-js="/static/chat-demo.js?v={v}"' in button and f'data-css="/static/chat-demo.css?v={v}"' in button, path
        assert text.index("</footer>") < text.index(button) < text.index('<script src="/static/mascots.js'), path
        assert "chat-demo" not in text.replace(button, "").replace(pages.chat_plan_html(), ""), path
        assert not [x for x in re.findall(r'<(?:script src|link rel="stylesheet" href)="([^"?]+)', text) if "chat" in x], path
        with_button.append(path)
    assert set(with_button) == set(pages.PAGES) | {"/privacy", "/docs", "/lovable", "/local", pages.CONSENT_PATH, "/no-such-page",
                                                  "/blog", pages.BLOG_TOTALS}
    # /demo is a redirect to /check
    r = client.get("/demo", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"].startswith("/check") and "kgc" not in r.text
    # the replay stays, and the chat's files are served
    assert '<p class="session-head">A replay of Krusgraph' in client.get("/").text            # n165: the head says whose answers
    for name, kind in (("chat-demo.js", "text/javascript"), ("chat-demo.css", "text/css")):
        r = client.get(f"/static/{name}?v={v}")
        assert r.status_code == 200 and r.headers["content-type"].startswith(kind)


# The pages' content security policies as they stood before n93 (main 64bd548): n93 changes none of them.
_THEME = pages.THEME_HASH
CSP_PAGE = ("default-src 'self'; script-src 'self' " + _THEME + "; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
CSP_HOME = CSP_PAGE.replace("connect-src 'self'", "connect-src testserver/static/pyodide/ testserver/check/engine.zip testserver/demo/plan.json")
CSP_CHECK = ("default-src 'self'; script-src 'self' " + _THEME + "; worker-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
             "font-src 'self'; connect-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'none'")


def test_no_page_policy_changed_and_the_button_only_where_the_chat_may_fetch_its_plan(client):
    """n93: every page's policy is the one it had; the button is on a page only where its connect-src lets the chat fetch
    /demo/plan.json ('self', or the start page's list that names it), or (n154) where the page carries the plan itself:
    /check, whose connect-src stays 'none'. The start page loses it when the request's Host header is one the policy
    cannot name."""
    for path, r in _html_routes(client).items():
        csp = r.headers["content-security-policy"]
        assert csp == {"/": CSP_HOME, "/check": CSP_CHECK}.get(path, CSP_PAGE), path
        allowed = "connect-src 'self'" in csp or "/demo/plan.json" in csp
        assert ('id="kgcLaunch"' in r.text) == (allowed or 'id="kgcPlan"' in r.text), path
        assert 'id="kgcLaunch"' in r.text and allowed == (path != "/check") and ('id="kgcPlan"' in r.text) == (path == "/check"), path
    r = client.get("/", headers={"host": "bad host!"})
    assert "connect-src 'none'" in r.headers["content-security-policy"] and "kgc" not in r.text
    assert pages.strip_chat(pages.render("/start")).count("kgcLaunch") == 0 and "</footer>" in pages.strip_chat(pages.render("/start"))


def test_the_launcher_in_site_js_loads_the_chat_only_on_a_click_or_to_restore_it():
    part = SITE_JS[SITE_JS.index("n92: the chat demo's button"):SITE_JS.index("window.KrusGraph = ")]
    load = part[part.index("var kgcLoad = function"):part.index("kgc.addEventListener('click'")]
    assert "createElement('script')" in load and "createElement('link')" in load
    assert "createElement('script')" not in part.replace(load, "") and "fetch(" not in part
    assert "kgc.hidden = false" in part and "KrusgraphChat.open" in part and "KrusgraphChat.restore" in part
    # n93: it reads the chat's one key, only to know whether the chat was open, and writes nothing
    assert re.findall(r"sessionStorage\.(\w+)\(([^)]*)\)", part) == [("getItem", "'krusgraph.chat'")]
    assert "kgcWas.open === true" in part and "matchMedia('(max-width: 560px)')" in part
    assert "try {" in part and "catch (e)" in part
    for word in ("localStorage", "setItem", "removeItem", "cookie", "sendBeacon", "/check/event"):
        assert word not in part, word


# ------------------------------------------------------------------ no request but the plan, nothing stored ----------
def test_the_chat_fetches_the_plan_and_nothing_else_and_keeps_only_its_steps_in_the_tab():
    assert re.findall(r"\bfetch\(([^,)]+)", CHAT_JS) == ["PLAN_URL"] and "var PLAN_URL = '/demo/plan.json';" in CHAT_JS
    for word in ("localStorage", "indexedDB", "document.cookie", "sendBeacon", "XMLHttpRequest", "WebSocket",
                 "EventSource", "new Image", "/check/event", "navigator.", "history.", "_blank", "http:", "https:",
                 "<input", "<textarea", "contenteditable", "prompt(", "console."):
        assert word not in CHAT_CODE, word
    assert not re.search(r"\.target\s*=[^=]|'target'|target=", CHAT_JS)          # links open in the same tab
    # n93: sessionStorage, one key, read and written in one place each, inside try/catch
    assert re.findall(r"sessionStorage\.(\w+)\((\w+)", CHAT_CODE) == [("getItem", "KEY"), ("setItem", "KEY")]
    assert "var KEY = 'krusgraph.chat';" in CHAT_JS
    read = CHAT_JS[CHAT_JS.index("function readState()"):CHAT_JS.index("function save()")]
    write = CHAT_JS[CHAT_JS.index("function save()"):CHAT_JS.index("function record(")]
    assert read.lstrip().startswith("function readState() {\n    try {") and "catch (e) { return null; }" in read
    assert "try {" in write and "catch (e)" in write
    # what is written: open as a boolean, and step names from the fixed list; nothing from the page or the plan
    assert "JSON.stringify({ open: !!(box && !box.hidden), steps: steps.filter(function (s) { return STEPS.indexOf(s) >= 0; }) })" in write
    assert "var STEPS = ['scan', 'yes', 'no', 'model', 'flow', 'ontology', 'domains', 'fixes', 'dbt'];" in CHAT_JS   # n162: fix and dbt run; n224: the data flow
    # what is read back is checked: an object, open a boolean, steps known names at most once, a short string at all
    for check in ("raw.length > 400", "typeof o.open !== 'boolean'", "!Array.isArray(o.steps)", "STEPS.indexOf(o.steps[i]) < 0",
                  "o.steps.indexOf(o.steps[i]) !== i", "Array.isArray(o)"):
        assert check in read, check
    # a step is replayed only by running the button it names, when that button is on screen
    assert "button.kgc-pick[data-key=\"' + restore[i] + '\"]" in CHAT_JS and "if (!b) break;" in CHAT_JS
    # the links: the check page, its example and the set-up guide, in the same tab
    hrefs = set(re.findall(r"href: '([^']+)'", CHAT_JS))
    assert hrefs == {"/check", "/check?example=sample", "/start"}
    # n158 (review L20): the two exits take pages.CHECK_LABEL and CONNECT_LABEL from the launch button
    assert "launch.getAttribute('data-label-connect') || 'Connect to my Fabric', why: 'Opens the set-up guide.', href: '/start' }" in CHAT_JS
    assert "launch.getAttribute('data-label-check') || 'Check my tables', href: '/check' }" in CHAT_JS


def test_fix_data_issues_and_dbt_are_steps_that_run_and_link_nothing(client):
    """n162: "Fix data issues" and "Draft a dbt project" (n154 to n161 links to the docs, before that "Planned") are steps
    like the others: buttons with a step name, offered until they have run, that show what the plan JSON carries. They
    link nothing and say nothing about the future."""
    block = CHAT_JS[CHAT_JS.index("function further()"):CHAT_JS.index("function drafts()")]
    picks = re.findall(r"\{ key: '(\w+)', label: '([^']+)', why: '([^']+)', go: (\w+) \}", block)
    assert [(k, label, go) for k, label, _, go in picks] == [("fixes", "Fix data issues", "fixes"), ("dbt", "Draft a dbt project", "dbtProject")]
    assert "href" not in block and "planned" not in block and "return !S[p.key];" in block
    assert "function fixes()" in CHAT_JS and "function dbtProject()" in CHAT_JS
    assert "drafts().fixes" in CHAT_JS and "drafts().dbt" in CHAT_JS
    assert "Files only; nothing runs." in CHAT_JS and "nothing was applied and no question was answered" in CHAT_JS
    assert "Create a dbt flow" not in CHAT_JS
    # what the step says exists: the tools, and the docs pages about them
    from fabric_backend import tool_status as ts
    for tool in ("validate_plan", "create_silver_notebook", "dbt_schema"):
        assert tool in ts.STATUS, tool
    fixes = client.get("/docs/explore-and-check/fix-data-issues").text
    assert "fixes=true" in fixes and "create_silver_notebook" in fixes and "krusgraph_quarantine" in fixes
    flow = client.get("/docs/build-from-a-plan/create-a-dbt-flow").text                    # n156
    assert "project=true" in flow and "profiles.example.yml" in flow
    assert not re.search(r"\b(soon|coming|shortly|later this|next (week|month|quarter|year)|Q[1-4]|20\d\d|in \d+ (days|weeks|months))\b", _strings(CHAT_JS), re.I)


def test_the_fixes_in_the_plan_are_what_validate_plan_with_fixes_answers():
    """n162: the plan JSON carries, for the plan as it is and with the suggestion confirmed, what validate_plan with
    fixes=true answers on the synthetic rows: the same counts (evidence.validate, validate_plan's ceiling of 200) and the
    same proposal (fix_plan.propose with the read-only counts), computed when the JSON is built. On the example the keys
    and links hold, so no fix is mechanical; what is left are two business decisions: the level of products.list_price,
    which a join with order_items repeats (with its options and the two sums), and audit_log without a key."""
    from fabric_backend import fix_plan
    d = demo_plan()["drafts"]
    sug = demo_plan()["suggestions"][0]["confirmed"]
    for name, confirmed in (("as_is", None), ("with_suggestion", [sug])):
        p = plan(schema("shop"), keys=DEMO_KEYS, confirmed=confirmed)
        v = evidence.validate(p, _demo_db(), max_items=200)
        pr = fix_plan.propose(p, v, _demo_db())
        got = d[name]["fixes"]
        assert got["tool"] == "validate_plan" and got["option"] == "fixes=true" and got["status"] == pr["status"]
        assert got["summary"] == v["summary"] and got["counts"] == pr["counts"]
        assert (got["keys"], got["relationships"]) == (len(v["keys"]), len(v["relationships"]))
        assert [(f["id"], f["type"], f["table"], f["column"], f["what_is_wrong"], f["proposed_fix"]) for f in got["findings"]] == [
            (e["id"], e["type"], e["table"], e["column"], e["what_is_wrong"], e["proposed_fix"]) for e in pr["fixes"]]
        for f, e in zip(got["findings"], pr["fixes"]):
            assert f["before"] == e["counts"].get("before", {}) and f["sums"] == e["counts"].get("sums", {})
            assert f["expected_after"] == e["counts"].get("expected_after", {})
            assert f["questions"] == [{"ask": q["ask"], "options": q.get("options", [])} for q in e["questions"]]
    a, w = d["as_is"]["fixes"], d["with_suggestion"]["fixes"]
    assert (a["keys_unique"], a["keys"], a["hold"], a["relationships"]) == (6, 6, 6, 6)
    assert (w["hold"], w["relationships"]) == (7, 7)
    for x in (a, w):
        assert x["counts"] == {"findings": 2, "mechanical": 0, "business_decision": 2}
        level, nokey = x["findings"]
        assert (level["id"], level["joined_with"]) == ("level:products.list_price", "order_items")
        assert level["before"]["headers"] == 8 and (level["before"]["min_lines"], level["before"]["max_lines"]) == (13, 27)
        assert level["sums"] == {"summed_over_lines": 22610.9, "summed_per_header": 1666.6}
        assert len(level["questions"][0]["options"]) == 3
        assert nokey["id"] == "no_key:audit_log" and nokey["questions"][0]["ask"].startswith("Does audit_log have a key")
    # the figures are summed again here over seed.rows(), outside the engine
    cols = {t.name: [c.name for c in t.columns] for t in schema("shop")}
    price = {r[cols["products"].index("product_id")]: r[cols["products"].index("list_price")] for r in rows()["products"]}
    lines = [r[cols["order_items"].index("product_id")] for r in rows()["order_items"]]
    assert round(sum(price[x] for x in lines if x in price), 1) == 22610.9
    assert round(sum(v for k, v in price.items() if k in set(lines)), 1) == 1666.6


def test_the_dbt_project_in_the_plan_is_what_dbt_schema_with_project_writes():
    """n162: the plan JSON carries what dbt_schema with project=true (and check_rows) writes for the demo plan: the file
    tree, the first lines of the staging model of the first single-column relationship's source, and that
    relationship's tests in the sources file, each cut from the engine's own files, never typed."""
    from fabric_backend import dbt
    d = demo_plan()["drafts"]
    sug = demo_plan()["suggestions"][0]["confirmed"]
    for name, confirmed in (("as_is", None), ("with_suggestion", [sug])):
        p = plan(schema("shop"), keys=DEMO_KEYS, confirmed=confirmed)
        out = dbt.project(p, "shop", "shop", "shop", evidence.validate(p, _demo_db()))
        got = d[name]["dbt"]
        assert got["tool"] == "dbt_schema" and got["option"] == "project=true" and got["project"] == out["project"]
        assert got["files"] == sorted(out["files"]) and got["created"] == out["created"]
        assert (got["staging"], got["marts"]) == (len(out["models"]["staging"]), len(out["models"]["marts"]))
        m, r = got["model"], got["relationship"]
        body = [x for x in out["files"][m["file"]].splitlines() if x.strip() and not x.lstrip().startswith("--")]
        assert m["lines"] == body[:len(m["lines"])] and m["more"] == len(body) - len(m["lines"]) and m["lines"]
        rel = next(x for x in p.relationships if len(x.source_cols) == 1 and len(x.target_cols) == 1)
        assert (r["source"], r["column"], r["target"], r["field"]) == (rel.source, rel.source_cols[0], rel.target, rel.target_cols[0])
        assert m["file"].endswith(f"__{rel.source}.sql")
        text = out["files"][r["file"]]
        assert r["lines"][0] == f"- name: {r['column']}" and "relationships:" in "\n".join(r["lines"])
        assert f"to: source('shop', '{r['target']}')" in r["lines"][-2] and r["lines"][-1].endswith(f"field: {r['field']}")
        src = text.splitlines()                     # a block of the sources file, as it is there (only dedented)
        starts = [i for i, x in enumerate(src) if x.strip() == r["lines"][0]]
        assert any([x[len(src[i]) - len(src[i].lstrip()):] for x in src[i:i + len(r["lines"])]] == r["lines"] for i in starts)
    a = d["as_is"]["dbt"]
    assert {"dbt_project.yml", "models/sources/shop.yml", "profiles.example.yml"} <= set(a["files"])
    assert any(f.startswith("models/staging/") for f in a["files"]) and any(f.startswith("models/marts/") for f in a["files"])
    assert a["relationship"]["source"] == "products" and a["model"]["file"] == "models/staging/shop/stg_shop__products.sql"


def test_every_result_says_nothing_was_created_and_what_the_agent_does_by_tool_status(client):
    button = _launcher(client.get("/use-cases").text)
    for key, draft, create in pages.CHAT_RESULTS:
        tool = create or draft
        option = pages.CHAT_OPTIONS.get(key, "") if not create else ""      # n177: the step's option, as LIVE-TEST has it
        assert f'data-status-{key}="{pages.chat_status(tool, option)}"' in button
        assert "data-tool-" not in button and tool not in button and tool not in pages.chat_status(tool)
        does = pages.chat_does(create)
        assert f'data-does-{key}="{does}"' in button
    assert 'data-does-domains="drafts"' in button
    # n162: fixes are proposed by validate_plan and applied by create_silver_notebook; dbt only drafts
    assert f'data-draft-status-fixes="{pages.chat_status("validate_plan", "fixes=true")}"' in button and "data-draft-status-model" not in button
    assert 'data-does-dbt="drafts"' in button
    assert "This is a demo, so nothing was created. " in CHAT_JS
    assert "your agent creates this in your Fabric workspace when you ask." in CHAT_JS
    assert "your agent drafts this from your own tables when you ask; the draft creates nothing in Fabric." in CHAT_JS
    assert "your agent drafts this from your own tables when you ask.'" in CHAT_JS
    assert "esc(note) + ' ' + esc(data(key, 'status'))" in CHAT_JS and "Status of" not in CHAT_JS
    assert "The ontology item is in preview in Fabric." in CHAT_JS
    low = _strings(CHAT_JS).lower()
    assert "bubble" not in low and "in claude" not in low and "in your agent" not in low


def test_the_status_sentence_is_built_from_tool_status_and_says_no_more():
    """n93: instead of "Status of create_semantic_model: available when enabled by the operator; created live; reviewed
    in Fabric", a short sentence without the tool's name. Today's three, and each part following its field."""
    model = pages.chat_status("create_semantic_model")
    assert model == "Created in a live Fabric workspace and reviewed there."      # n146: the hosted app has Item.ReadWrite.All
    assert pages.chat_status("create_ontology") == model
    assert pages.chat_status("domain_draft") == "Tested with unit tests, not yet against a live Fabric workspace."
    for key, draft, create in pages.CHAT_RESULTS:
        tool = create or draft
        s, said = ts.STATUS[tool], pages.chat_status(tool)
        assert ("Created in a live Fabric workspace" in said) == (ts.build_word(tool) == "creates"), tool
        assert ("reviewed there" in said) == (tool in ts.REVIEWED and ts.build_word(tool) == "creates"), tool
        assert ("permission the hosted service does not ask for today" in said) == (s.available == ts.OPERATOR), tool
        assert ("not yet against a live Fabric workspace" in said) == (s.kind != ts.CREATES and not s.live), tool
        assert not re.search(r"\b(soon|coming|shortly|Q[1-4]|20\d\d)\b", said), tool       # no dates, no promises


def test_the_status_sentence_changes_when_tool_status_does(monkeypatch):
    """The sentence is not typed: change tool_status and it says something else (and the line above fails)."""
    monkeypatch.delitem(ts.REVIEWED, "create_semantic_model")
    assert pages.chat_status("create_semantic_model") == "Created in a live Fabric workspace."
    monkeypatch.setitem(ts.STATUS, "create_semantic_model", ts.STATUS["create_semantic_model"].__class__(
        ts.OPERATOR, ts.CREATES, "x", "unit tests", name="create_semantic_model"))
    assert pages.chat_status("create_semantic_model") == ("Created in a live Fabric workspace. "
                                                          "Creating it needs a permission the hosted service does not ask for today.")
    monkeypatch.setitem(ts.STATUS, "create_semantic_model", ts.STATUS["create_semantic_model"].__class__(
        ts.HOSTED, ts.CREATES, "x", "unit tests", name="create_semantic_model"))
    monkeypatch.delitem(ts.LATER_LIVE, "create_semantic_model")
    monkeypatch.setattr(ts, "LIVE_RUN", tuple(t for t in ts.LIVE_RUN if t != "create_semantic_model"))
    assert pages.chat_status("create_semantic_model") == "Not yet created in a live Fabric workspace."
    monkeypatch.setitem(ts.STATUS, "domain_draft", ts.STATUS["domain_draft"].__class__(ts.HOSTED, ts.DRAFT, "nothing", "unit tests", name="domain_draft"))
    monkeypatch.setattr(ts, "LIVE_RUN", ts.LIVE_RUN + ("domain_draft",))
    assert pages.chat_status("domain_draft") == "Run against a live Fabric workspace as a draft."


def test_the_sales_word_test_covers_the_chat(client):
    from tests.test_site import SALES
    text = (_strings(CHAT_JS) + " " + _launcher(client.get("/use-cases").text) + " " +
            " ".join(pages.chat_status(c or d) for _, d, c in pages.CHAT_RESULTS)).lower()
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
    assert "e.key !== 'Escape'" in CHAT_JS and "launch.focus(" in CHAT_JS and "setAttribute('inert'" in CHAT_JS
    # n93: the pictures take their colours from the tokens too, a restored chat comes without animation, and Mascots:
    # off does not touch the pictures
    assert ".kgc.kgc-still, .kgc-msg.still, .kgc-you.still { animation: none }" in CHAT_CSS
    assert not re.search(r"data-mascots[^{]*\{[^}]*\}", CHAT_CSS.replace('html[data-mascots="off"] .kgc-fig { display: none }', "")
                         .replace('html[data-mascots="off"] .kgc-head { grid-template-columns: minmax(0, 1fr) auto }', "")
                         .replace('html[data-mascots="off"] .kgc-msg { grid-template-columns: minmax(0, 1fr) }', "")
                         .replace('html[data-mascots="off"] .kgc-picks { grid-column: 1 }', ""))
    for sel in (".kgc-n rect", ".kgc-e line", ".kgc-grp rect", ".kgc-key circle"):
        rule = CHAT_CSS[CHAT_CSS.index(sel + " {"):].split("}")[0]
        assert "var(--" in rule, sel
    assert "overflow-x: hidden" in CHAT_CSS[CHAT_CSS.index(".kgc-big-body {"):]
    assert "body.nav-open .kgc-launch{visibility:hidden}" in (STATIC / "site.css").read_text(encoding="utf-8")


def test_site_md_describes_the_chat():
    md = (ROOT / "docs" / "SITE.md").read_text(encoding="utf-8")
    sec = md[md.index("## The chat demo"):]
    for words in ("chat-demo.js", "/demo/plan.json", "Planned", "localStorage", "560 px", "Mascots: off", "tool_status",
                  "connect-src", "sessionStorage", "Start over", "/start", "Larger picture", "connect-src 'none'"):
        assert words in sec, words


def test_creates_is_never_said_next_to_the_missing_permission():
    """n94: "creates this in your Fabric workspace when you ask" and "Creating it needs a permission the hosted service
    does not ask for today." contradicted each other for the semantic model and the ontology."""
    gated = "Creating it needs a permission the hosted service does not ask for today."
    for key, draft, create in pages.CHAT_RESULTS:
        if gated in pages.chat_status(create or draft):
            assert pages.chat_does(create) != "creates", key
    assert pages.chat_does(None) == "drafts"


def test_creates_comes_back_when_the_permission_is_asked_for(monkeypatch):
    import dataclasses
    for key, draft, create in pages.CHAT_RESULTS:
        if create and ts.build_word(create) == "creates":
            monkeypatch.setitem(ts.STATUS, create, dataclasses.replace(ts.STATUS[create], available=ts.HOSTED))
            assert pages.chat_does(create) == "creates", key
            monkeypatch.setitem(ts.STATUS, create, dataclasses.replace(ts.STATUS[create], available=ts.OPERATOR))
            assert pages.chat_does(create) == "drafts-gated", key


# ------------------------------------------------------------------ n177: the status words match docs/LIVE-TEST.md ----

def _live_rows(tool: str) -> list[list[str]]:
    """LIVE-TEST.md section 1's rows for one tool: [#, tool, question, expected, earlier, result, date]."""
    text = (Path(__file__).resolve().parents[1] / "docs" / "LIVE-TEST.md").read_text(encoding="utf-8")
    sec = text.split("## 1. One row per tool", 1)[1].split("\n## ", 1)[0]
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in sec.splitlines() if ln.startswith("| ")]
    return [r for r in rows if len(r) >= 7 and r[1] == f"`{tool}`"]


def test_the_chat_says_an_option_ran_live_only_when_live_test_has_it():
    """The founder, 9 November 2026: the chat's 'Tested with unit tests, not yet against a live Fabric workspace' must
    match LIVE-TEST. The fixes step is validate_plan with fixes=true and the dbt step dbt_schema with project=true; the
    checklist's rows for both tools ran without them, so the chat says the option is unit-tested and the tool without it
    ran live. A dated row that names the option must come with tool_status.LIVE_OPTIONS, and the other way round."""
    for key, option in pages.CHAT_OPTIONS.items():
        tool = next(d for k, d, _ in pages.CHAT_RESULTS if k == key)
        rows = _live_rows(tool)
        assert rows, tool
        ran_plain = any(r[4] not in ("", "—") or r[6] for r in rows)
        ran_option = any(option in (r[2] + r[3]) and r[6] for r in rows)
        assert ran_option == ((tool, option) in ts.LIVE_OPTIONS), (tool, option)
        said = pages.chat_status(tool, option)
        assert ("tested with unit tests, not yet against a live Fabric workspace" in said) == (not ran_option), said
        assert ("ran against one" in said) == (ran_plain and not ran_option and ts.STATUS[tool].live), said
        assert tool not in said and option not in said
    assert pages.chat_status("dbt_schema", "project=true") == (
        "The dbt project: tested with unit tests, not yet against a live Fabric workspace; the sources file alone ran "
        "against one as a draft.")
    # data products: no LIVE-TEST row at all, and the chat says unit tests
    assert not _live_rows("domain_draft") and "not yet against a live Fabric workspace" in pages.chat_status("domain_draft")


def test_the_demo_ends_only_after_the_last_step():
    """n177: Onto said "That is the demo" while Fix data issues and the dbt project were still offered. The end comes
    only when no step is left; before it Onto asks what next, with the steps left first."""
    nxt = CHAT_JS[CHAT_JS.index("function next() {"):CHAT_JS.index("function done(")]
    assert "else if (further().length) say('onto', 'point', '<p>What next?</p>', further().concat(leave())" in nxt
    end = nxt.index("<h3>That is the demo")
    assert nxt.index("further().length") < end
    assert "leave().concat(further())" not in nxt


def test_the_dbt_step_draws_the_flow_from_the_project_files():
    """n177: the dbt step draws sources -> staging -> marts -> model (dbt_flow.py), boxes folded, a box's code the file's
    own text; the model is dashed (dbt does not make it)."""
    from fabric_backend import dbt_flow
    x = json.loads(demo.demo_plan_json())["drafts"]["as_is"]["dbt"]
    f = x["flow"]
    assert [c["id"] for c in f["columns"]] == ["sources", "staging", "marts", "model"]
    by = {c: [n for n in f["nodes"] if n["column"] == c] for c in ("sources", "staging", "marts", "model")}
    assert len(by["staging"]) == x["staging"] and len(by["marts"]) == x["marts"] and len(by["sources"]) == 7
    assert [n["built"] for n in by["model"]] == [False]
    for n in by["staging"] + by["marts"]:
        assert n["code"].startswith("-- " + n["label"] + ":") and n["file"].endswith(n["label"] + ".sql")
    for n in by["sources"]:
        assert n["code"].startswith("- name: " + n["label"]) and "data_tests:" in n["code"]
    edges = {(e["from"], e["to"]) for e in f["edges"]}
    assert ("source:shop.orders", "model:stg_shop__orders") in edges
    assert ("model:stg_shop__orders", "model:fct_orders") in edges and ("model:stg_shop__customers", "model:fct_orders") in edges
    assert all(not e["built"] for e in f["edges"] if e["to"] == "model:semantic_model")
    assert dbt_flow.flow({"models/sources/shop.yml": "version: 2"}) is None          # a sources file alone: no flow
    assert "KGF.build(document, x.flow)" in CHAT_JS and "aria-expanded" in CHAT_JS and "kgc-tree" not in CHAT_JS
