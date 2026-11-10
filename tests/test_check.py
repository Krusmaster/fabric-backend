"""n38: /check, the engine in the visitor's browser (Pyodide) on files that are never uploaded."""
import io
import re
import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import browser_check as bc, pages

ROOT = Path(__file__).resolve().parents[1]


def test_sample_gives_map_findings_and_the_five_states():
    r = bc.analyze("sample")
    assert r["verdict"]["headline"]["title"] == "Enough to start"
    assert r["verdict"]["states"] == ["Enough to start", "We need your knowledge about", "Missing material:", "Missing access:", "Not supported yet:"]
    assert len(r["tables"]) == 7 and all(x["rule"] for x in r["relationships"])
    checks = {f["check"] for f in r["findings"]}
    assert "amount_level" in checks and "keyless" in checks
    assert any("K3" in f["rules"] for f in r["findings"])
    assert "%" not in r["verdict"]["headline"]["text"]


def test_every_finding_says_how_much_of_the_rows_it_checked():
    """n75: each finding carries a `checked` line read from the engine's own counts (validate_plan's rows per key and
    rows with a value per relationship, suggest_relationships' rows, the keyless count, the rows per header of an amount),
    and the result a `coverage` line for the run: every key and relationship, or how many of them; a columns list
    says nothing was counted."""
    from fabric_backend import evidence
    from fabric_backend.infer import plan
    r = bc.analyze("sample")
    assert r["coverage"] == {"counted": True, "complete": True, "keys": 6, "keys_total": 6, "relationships": 6, "relationships_total": 6,
                             "text": "Counted in the rows: all 6 keys and all 6 relationships of the plan, each over the whole table."}
    by = {f["title"]: f["checked"] for f in r["findings"] + r["suggestions"]}
    src, _ = bc._source("sample", None, "")
    try:
        v = evidence.validate(plan(src.schema), src.execute)
    finally:
        src.close()
    rows = {k["table"]: k["rows"] for k in v["keys"]}
    assert by["audit_log has no key"].startswith("Checked on all ") and by["audit_log has no key"].endswith(" rows of audit_log: the first 3 columns.")
    assert by["Suggested: orders.ship_to_id → addresses.address_id"] == f"Checked on all {rows['orders']} rows of orders: {rows['orders']} with a value."
    lp = next(f for f in v["amount_levels"]["findings"] if f["header"] == "products")["rows_per_header"]
    assert by["products.list_price would be summed once per order_items row"] == \
        f"Counted on all rows of products and order_items: {lp['headers']} products rows with order_items rows, at most {lp['max_lines']} each."
    assert by["The total that doubles: order amount and line amount are different levels"] == \
        "Counted on all rows of the example's two tables: 1 orders row with 2 order_lines rows."
    for text in by.values():
        assert not re.search(r"\b(?:all|every)\b.*\b(?:every|all)\b", text) or "whole" not in text    # one claim per line
    crm = bc.analyze("crm")
    assert crm["coverage"]["complete"] and all(f["checked"].startswith(("Checked on all ", "Counted on all rows of ")) for f in crm["findings"])
    cols = bc.analyze("columns", text="orders.order_id\norders.customer_id\ncustomers.customer_id\naudit_log.x")
    assert cols["coverage"]["counted"] is False and cols["coverage"]["text"].startswith("Nothing counted: a list of columns has no rows")
    assert all(f["checked"] == "Not counted: a list of columns has no rows, so this rests on the names alone." for f in cols["findings"] + cols["suggestions"])


def test_the_result_carries_domain_drafts_proposal_and_contracts():
    """n63: /check's engine runs domains.draft on the same plan; the page draws it and offers each contract."""
    from fabric_backend import domains
    from fabric_backend.infer import plan
    r = bc.analyze("sample")
    d = r["domains"]
    assert [(x["name"], x["tables"]) for x in d["domains"]] == [("customers", ["addresses", "customers", "order_items", "orders"]),
                                                                 ("products", ["categories", "products"])]
    src, _ = bc._source("sample", None, "")
    pair = lambda xs: [(i["source"], i["target"]) for i in xs]     # the weights differ: here validate_plan's counts are given
    assert pair(d["interfaces"]) == pair(domains.propose_plan(plan(src.schema))["interfaces"]) == [("order_items", "products")]
    c = d["domains"][0]
    assert c["keys"]["order_items"] == ["order_id", "line_no"] and all(x["source"] in c["tables"] and x["target"] in c["tables"] for x in c["relationships"])
    assert {"what": "key of customers", "verdict": "unique in all 10 rows"} in c["checks"]
    assert d["contracts"]["customers"].startswith("# ODCS v3.2.0") and "kind: DataContract" in d["contracts"]["customers"]
    sap = bc.analyze("sap")["domains"]
    assert [x["name"] for x in sap["domains"]] == ["order-to-cash", "customer master"] and "public SAP" in sap["domains"][0]["name_reason"]


@pytest.mark.parametrize("kind", ["sample", "sap", "crm", "billing", "mill"])
def test_the_examples_report_each_engine_step_with_its_time(kind):
    events = []
    r = bc.analyze(kind, emit=events.append)
    assert [e["step"] for e in events] == ["read", "keys", "relationships", "validate", "suggest", "domains", "findings"]
    assert all(isinstance(e["ms"], int) and e["detail"] for e in events)
    assert events[1]["tables"] == r["tables"] and events[2]["relationships"] == r["relationships"]
    assert events[-1]["result"] == r and r["verdict"]["headline"]["title"] == "Enough to start"


def test_the_salesforce_erp_link_is_found_only_in_the_rows():
    r = bc.analyze("crm")
    assert not any(x["source"] == "Account" and x["target"] == "customers" for x in r["relationships"])   # no name rule links them
    assert any(f["title"] == "Suggested: Account.ERP_Customer_No__c → customers.customer_no" for f in r["suggestions"])
    titles = [f["title"] for f in r["findings"]]
    assert "Contact.AccountId → Account: 1 orphan(s)" in titles and "sales_orders.customer_no → customers: 1 orphan(s)" in titles
    assert any(f["check"] == "amount_level" for f in r["findings"])


def test_the_sap_example_uses_the_pack_and_the_synthetic_demo():
    r = bc.analyze("sap")
    assert {x["rule"] for x in r["relationships"]} == {"SAP pack"} and len(r["tables"]) == 17
    assert any(f["check"] == "relationship" and "orphan" in f["title"] for f in r["findings"])


def test_the_subscription_billing_example_is_read_through_the_younium_salesforce_pack():
    """n78: the fourth example, fabric_backend.younium_demo's rows; the engine reads the pack itself, so the plan has
    the pack's 15 relationships and validate_plan shows the planted 15-character Salesforce id and both doubled totals."""
    r = bc.analyze("billing")
    assert len(r["tables"]) == 14 and len(r["relationships"]) == 15 and {x["rule"] for x in r["relationships"]} == {"Younium + Salesforce pack"}   # n79: by its own name
    assert r["coverage"]["complete"] and r["coverage"]["relationships"] == 15
    titles = [f["title"] for f in r["findings"]]
    assert "younium_accounts.external_crm_id → sf_account: 1 orphan(s)" in titles
    assert "sf_opportunity.Amount would be summed once per sf_opportunitylineitem row" in titles
    assert any(t.startswith("younium_invoices.") and t.endswith("once per younium_invoice_lines row") for t in titles)
    assert "synthetic" in r["source"]["label"].lower() or "Synthetic" in str(r["source"])


def test_files_are_read_with_the_demo_adapter_and_orphans_are_found():
    r = bc.analyze("files", [("customers.csv", b"customer_id,name\n1,a\n2,b\n"),
                             ("orders.csv", b"order_id,customer_id\n1,1\n2,9\n"), ("old.xls", b"x")])
    assert r["source"]["label"] == "3 files read in this browser"
    assert any(f["check"] == "relationship" and "orphan" in f["title"] for f in r["findings"])
    assert any(i["title"] == "Not supported yet:" for i in r["verdict"]["items"])


def test_xlsx_and_columns_list():
    Workbook = pytest.importorskip("openpyxl").Workbook
    wb = Workbook(); ws = wb.active; ws.title = "products"; ws.append(["product_id", "name"]); ws.append([1, "x"])
    buf = io.BytesIO(); wb.save(buf)
    r = bc.analyze("files", [("products.xlsx", buf.getvalue())])
    assert [t["name"] for t in r["tables"]] == ["products"] and r["tables"][0]["key_rule"] == "K2"
    r = bc.analyze("columns", text="orders.order_id\norders.customer_id\ncustomers.customer_id")
    assert r["relationships"][0]["rule"] == "R1" and not r["source"]["has_data"]
    assert bc.analyze("columns", text="")["verdict"]["headline"]["state"] == "material"


def test_engine_zip_is_the_package_python_only():
    names = zipfile.ZipFile(io.BytesIO(bc.engine_zip())).namelist()
    assert "fabric_backend/infer.py" in names and "fabric_backend/schema.py" in names and "fabric_backend/browser_check.py" in names
    assert not [n for n in names if "/static/" in n or "/page_templates/" in n or not n.endswith((".py", ".json"))]
    assert zipfile.ZipFile(io.BytesIO(bc.engine_zip())).read("fabric_backend/infer.py") == (ROOT / "fabric_backend/infer.py").read_bytes()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    from fabric_backend.server import build_app
    with TestClient(build_app()) as c:
        yield c


def test_check_page_policy_worker_and_files(client):
    r = client.get("/check")
    csp = r.headers["content-security-policy"]
    assert "connect-src 'none'" in csp and "worker-src 'self'" in csp and "form-action 'none'" in csp
    assert r.text.count("Synthetic Data") == 5 and "Synthetic data<" not in r.text and "A total that doubles" in r.text and "SAP sales tables" in r.text and "Salesforce + ERP" in r.text
    assert "Subscription billing" in r.text and 'data-example="billing"' in r.text                                 # n78
    assert "Manufacturing sample" in r.text and 'data-example="mill"' in r.text                                     # n192
    assert "<input type=\"text\"" not in r.text and "chat" not in r.text.lower().split("<main")[1].split("</main>")[0]   # n154: the chat's button and plan come after the footer
    assert "are not uploaded" in r.text and 'href="/check?example=sample&amp;guide=1"' in r.text and 'href="/local"' in r.text and "Get help" in r.text
    assert "http://" not in r.text.split("<main")[1].split("</main>")[0].replace("http://www.w3.org", "")
    w = client.get("/check/worker.js")
    assert w.headers["content-security-policy"].startswith("default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; connect-src testserver/static/pyodide/ testserver/check/engine.zip;")
    assert client.get("/check/engine.zip").content == bc.engine_zip()
    for n in pages.CHECK_DOWNLOAD:
        assert client.get("/static/pyodide/" + n).status_code == 200
    assert "/check" in client.get("/sitemap.xml").text and "/check" in client.get("/llms.txt").text
    assert 'href="/check"' in client.get("/").text


def test_no_external_url_in_the_scripts():
    for p in ("check.js", "check-worker.js"):
        text = (ROOT / "fabric_backend/static" / p).read_text()
        assert "https://" not in text and "http://" not in text.replace("http://www.w3.org/2000/svg", "")


import sys  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
from test_browser import CHROMIUM, _playwright_available, site  # noqa: E402,F401  the same local server fixture


@pytest.mark.skipif(not _playwright_available(), reason="node + playwright not available")
def test_in_a_browser_no_request_carries_the_files(site):
    out = subprocess.run(["node", str(ROOT / "tests/check_browser.js"), site] + ([CHROMIUM] if CHROMIUM else []),
                         capture_output=True, text=True, timeout=400)
    assert out.returncode == 0, out.stderr[-2000:]
    r = json.loads(out.stdout.strip().splitlines()[-1])
    assert not r["leaks"] and not r["foreign"] and not r["errors"], r
    assert all(x.startswith("GET ") for x in r["requests"]), r["requests"]
    assert r["page_fetch"] == "blocked"
    assert "orphan" in r["files_text"] and "Enough to start" in r["sample_text"] and "amount_level" in r["sample_text"]
    assert r["steps"][:2] == ["Python runtime", "The engine"] and "validate_plan: counted in the rows" in r["steps"]
    assert r["steps_while_running"] == 0, "with reduced motion the steps appear only when the run is done"
    assert r["crm_suggested_edges"] == 1 and r["sap_text"].count("SAP pack") > 0
    assert min(r["contrast"]) >= 4.5, r["contrast"]
    assert r["focused"] == "check-sample" and not r["overflow_375"] and not r["overflow_1280"]
    # n53: Ask Onto on the shop example: the questions come from what the engine found, the answers from its result
    assert r["ask_questions"] == ["Why does this total come out twice?", "What should I check first?", "Why is there no key on audit_log?",
                                  "These 4 tables hang together as customers. Package them as a data product?",
                                  "How do I get this into Power BI?", "Can I ask my own questions?"], r["ask_questions"]
    total = r["ask"]["total"]["text"]
    assert "Summed over the joined lines (order_lines)" in total and "Summed once per header (orders)" in total
    assert "2,000" in total and "1,000" in total and "amount_level" in total
    assert "rule K3" in r["ask"]["key"]["text"] and r["ask"]["key"]["lit"] == 1
    # n75: the coverage line under the state and a `checked` line on every finding card, from the result
    assert r["coverage"]["line"] == "Counted in the rows: all 6 keys and all 6 relationships of the plan, each over the whole table."
    assert r["coverage"]["onFirstScreen"] and r["coverage"]["cards"] >= 4 and all(c.startswith(("Checked on all ", "Counted on all rows of ")) for c in r["coverage"]["checked"]), r["coverage"]
    assert r["files_coverage"].startswith("Counted in the rows: all 2 keys and all 1 relationship of the plan") and "Checked on all 2 rows of orders: 2 with a value." in r["files_text"]
    assert "Yes, in Claude." in r["ask"]["own"]["text"] and "Connect" in r["ask"]["own"]["text"]
    assert all(a["expanded"] == "true" for a in r["ask"].values())
    assert r["ask_powerbi_focus"] == "check-model-h"
    assert not r["ask_requests"], r["ask_requests"]                   # answered from the result: no request at all
    assert r["ask_plain"] == {"figure": "none", "list": "block", "n": 6}
    # n63: the domains on the map, labelled (never colour alone) and tinted in both themes, and the data-product answer
    d = r["domains"]
    assert d["tinted"] == 6 and sorted(set(d["tags"])) == ["customers", "products"] and d["ifaces"] == 1, d
    assert "Proposed domains" in d["list"] and "order_items.product_id → products" in d["list"], d["list"]
    assert all(len(v) == 2 for v in r["domain_fill"].values()) and r["domain_fill"]["light"] != r["domain_fill"]["dark"], r["domain_fill"]
    prod = r["ask"]["product"]["text"]
    assert "A data product is a set of tables" in prod and "validate_plan counted" in prod and "unique in all" in prod and "[object" not in prod, prod
    assert ["Connect to my Fabric", "/start", None] in r["ask"]["product"]["html_links"]
    assert r["contract"]["name"] == "customers.odcs.yaml" and "apiVersion: v3.2.0" in r["contract"]["text"] and "kind: DataContract" in r["contract"]["text"]
    assert not r["ask_overflow_375"] and not r["ask_overflow_1280"]
    # n68: the domain buttons on Salesforce + ERP (two domains, no interface between them: the list once ended in "nullnullnull")
    cd = r["crm_domains"]
    assert "null" not in cd["before"]["list"] and cd["before"]["pressed"] == ["false", "false"] and cd["before"]["focus"] is False
    assert cd["before"]["question"] == "These 3 tables hang together as Account. Package them as a data product?"
    assert cd["one"]["pressed"] == ["false", "true"] and cd["one"]["focus"] is True and cd["one"]["on"] == 3 and cd["one"]["onEdges"] == 2
    assert cd["one"]["opacities"] == ["0.22", "1"] and cd["one"]["transition"] == "0s", cd["one"]            # dimmed, still, under reduced motion
    assert cd["one"]["question"] == "Package sales_orders as a data product?" and cd["one_links"] == ["sales_orders.odcs.yaml"]
    assert cd["two"]["pressed"] == ["true", "true"] and cd["two"]["on"] == 6 and cd["two"]["opacities"] == ["1"]
    assert cd["all"]["pressed"] == ["false", "false"] and cd["all"]["focus"] is False and cd["all"]["on"] == 0 and "null" not in cd["all"]["list"]
    # n55: the guided demo on /check, started from the address, four steps by keyboard, each marking the map
    assert [g["title"] for g in r["guide"]] == ["How the tables connect", "Here the total doubles", "A suggestion to decide on", "On to Power BI or an app"]
    assert [g["lit"] for g in r["guide"][:3]] == [1, 1, 1] and "2,000" in r["guide"][1]["text"] and "ship_to_id" in r["guide"][2]["text"]
    assert r["guide_next_disabled"] is True and not r["guide_overflow_375"] and "Accepted on this page" in r["guide_decided"]
    assert r["guide_plain"]["figure"] == "none" and r["guide_plain"]["text"] > 100
    assert r["plain_idle"] == {"check": None, "guide": True}
    for k, label in (("sample", "A total that doubles"), ("sap", "SAP sales tables"), ("crm", "Salesforce + ERP")):
        g = r["industries"][k]
        assert g["url"] == "/check?example=" + k and "Done: the example “" + label + "”" in g["status"] and g["guide"] is True, (k, g)
    # n73: the finding first: the state line, the most important finding and the folded list under the status line and
    # before the map; the engine's steps folded under the map. Four findings since n71: the keyless audit_log, the
    # suggestion, the synthetic total that doubles, and products.list_price over order_items
    assert r["folded"] == {"open": False, "summary": "Show all 4 findings", "line": "Enough to start · 4 things to check", "order": True, "findingsInside": True}
    fs = r["first_screen"]
    assert (fs["width"], fs["height"]) == (1280, 720) and 0 <= fs["verdictTop"] and fs["topFindingBottom"] <= fs["height"], fs   # seen without scrolling at 1280 px
    assert fs["mostImportant"].startswith("Most important: ") and fs["mapTop"] > fs["verdictBottom"], fs
    e = r["engine"]
    assert e["open"] is False and e["summary"] == "How the engine got here" and e["stepsInside"] and e["steps"] >= 7 and e["opened"] is True, e
    assert r["top_marks"] == {"lit": 1, "pressed": "true"}
    # n79: the evidence report as a download that says what it holds, with the status Draft
    ev = r["evidence"]
    assert ev and not ev["hidden"] and ev["download"] == "shop_evidence_report.md", ev
    assert ev["text"] == "Download evidence report", ev                              # n95: short, no file name, no tag
    # n80: beside it, the ontology as RDF/XML for Ontology Playground: what it holds, Draft, and how it is opened there
    rd = r["rdfxml"]
    assert rd and rd["download"] == "shop_ontology.rdf" and rd["head"].startswith('<?xml version="1.0" encoding="UTF-8"?>\n<rdf:RDF'), rd
    assert rd["text"] == "Download ontology", rd
    # n95: the description under each button, as plain text, and the status said once above the list
    items = {d["text"]: d for d in r["dl_items"]}
    for d in r["dl_items"]:
        assert d["children"] == 0 and d["desc"] and d["desc"] not in d["text"], d       # no description, tag or file name inside a button
        assert not re.search(r"\.(md|rdf|zip|yaml)\b|Draft|Experimental|Tested end to end", d["text"]), d
    assert items["Download evidence report"]["desc"].startswith("For a hand-over (Markdown): source, time, engine version") and "no row values" in items["Download evidence report"]["desc"]
    assert items["Download ontology"]["desc"] == ("For Microsoft's Ontology Playground (RDF/XML): 7 entity types with their columns and 6 relationships, "
                                                  "the rule in each description; no row values. Open it there with Import / Export.")
    assert items["Download evidence report"]["status"] == ["These files are drafts for you to review."] == items["Download ontology"]["status"]
    assert "Gustav tried" not in r["sample_text"] and "Gustav tried" not in (ROOT / "fabric_backend/static/check.js").read_text()
    # n78: four example buttons at 375 and 1280 px, none outside the viewport, and Subscription billing runs to the end
    for w in ("375", "1280"):
        bl = r["billing"][w]
        assert bl["ids"] == ["check-sample", "check-sap", "check-crm", "check-billing", "check-mill"] and bl["inside"] and not bl["overflow"], (w, bl)
        assert "Subscription billing" in bl["label"] and "Younium + Salesforce" in bl["label"] and "Synthetic Data" in bl["label"]
        assert "Done: the example “Subscription billing”" in bl["status"] and not bl["overflowAfter"], (w, bl["status"])
        assert "Younium + Salesforce pack" in bl["text"] and "SAP pack" not in bl["text"] and "external_crm_id" in bl["text"] and bl["ms"] > 0, w   # n79
    # n192: the manufacturing sample has a row of its own, loads and runs to the end with the planted problems
    for w in ("375", "1280"):
        m = r["mill"][w]
        assert "Manufacturing sample" in m["label"] and "Synthetic Data" in m["label"] and m["full"] and m["inside"] and not m["overflow"], (w, m)
    assert "Done: the example “Manufacturing sample”" in r["mill"]["status"] and r["mill"]["ms"] > 0, r["mill"]["status"]
    assert "stg_supplier_prices" in r["mill"]["text"] and "machine_events" in r["mill"]["text"] and "orphan" in r["mill"]["text"]
    assert len(r["finding_marks"]) == 1 and "audit_log" in r["finding_marks"][0]
    # n73: one order through "A total that doubles": order_id 1, 1 000 on the order, 2 000 over its two lines, in the
    # finding, in Onto's answer, in the Power BI preview and in the contract; every download button says what the file
    # holds and its status word
    so = r["same_order"]
    for text in (so["finding"], total, so["preview"]):
        assert "order_id 1" in text and "counts it twice" in text, text
    assert "2,000" in so["preview"] and "1,000" in so["preview"] and "orders.order_amount" in so["preview"] and "not in this model" in so["preview"], so["preview"]
    assert "1 000" in so["finding"] and "2 000" in so["finding"]
    c = r["contract"]["text"]
    assert "amountLevel.orders.order_amount" in c and "order_id 1 is 1 000 on its orders row" in c and "counts it twice (2 000)" in c, c[-900:]
    assert so["labels"] == ["Download Power BI project"], so["labels"]
    assert items["Download Power BI project"]["desc"] == "The model (.pbip) with the plan's keys and relationships as checked in the rows, and an empty report page."
    assert r["ask"]["product"]["dl"] == [[0, "ODCS 3.2 YAML: schema, keys, relationships and the checks that passed, with the total that doubles.",
                                          ["This file is a draft for you to review."]]], r["ask"]["product"]["dl"]
    assert ["Download data contract", "#", "customers.odcs.yaml"] in r["ask"]["product"]["html_links"], r["ask"]["product"]["html_links"]


def test_the_privacy_sentence_matches_what_the_page_sends(client):
    """n40: check.js sends two events, so the page must not claim it sends nothing, and must say what it does send."""
    js = (ROOT / "fabric_backend/static/check.js").read_text()
    sends = "/check/event" in js
    html = (ROOT / "fabric_backend/page_templates/check.html").read_text()
    page = client.get("/check").text
    llms = client.get("/llms.txt").text
    for text in (html, page, llms):
        assert ("send nothing" in text or "sends nothing" in text) is not sends
    if sends:
        assert "<strong>Your files are read in this browser and are not uploaded.</strong>" in page
        assert "sends only two anonymous events" in page and "no file contents, file names or table names" in page
        assert "sends only two anonymous events" in llms


# ------------------------------------------------------------------ n49: go further from the graph ----------------
from fabric_backend import browser_build as bb, tool_status as ts  # noqa: E402


@pytest.mark.parametrize("kind", ["sample", "sap", "crm"])
def test_build_gives_a_power_bi_project_and_an_app_starter_from_the_same_plan(kind):
    r = bb.build(kind)
    model = zipfile.ZipFile(io.BytesIO(__import__("base64").b64decode(r["downloads"][f"{r['name']}_model.zip"])))
    names = model.namelist()
    pbip = json.loads(model.read(f"{r['name']}_model.pbip"))
    assert pbip["artifacts"] == [{"report": {"path": f"{r['name']}_model.Report"}}]
    pbir = json.loads(model.read(f"{r['name']}_model.Report/definition.pbir"))
    assert pbir["datasetReference"]["byPath"]["path"] == f"../{r['name']}_model.SemanticModel"
    assert f"{r['name']}_model.SemanticModel/definition/model.tmdl" in names and f"{r['name']}_model.SemanticModel/definition.pbism" in names
    readme = model.read("README.md").decode()
    assert ts.label("semantic_model_draft") in readme and "Opened in Power BI Desktop on 30 October 2026" in readme
    app = zipfile.ZipFile(io.BytesIO(__import__("base64").b64decode(r["downloads"][f"{r['name']}_app.zip"])))
    assert "app/rayfin/connectors/data/schema.ts" in app.namelist() and "app/lovable-prompt.md" in app.namelist()
    assert r["status"] == {"model": ts.label("semantic_model_draft"), "report": "Draft only", "create_model": ts.short("create_semantic_model"),
                           "rayfin": ts.label("rayfin_connector"), "app_starter": ts.label("app_starter")}
    assert r["report"]["has_data"] and r["report"]["measures"] and r["app"]["kpis"]


def test_the_report_puts_the_right_total_beside_the_wrong_one_counted_in_the_rows():
    d = bb.build("crm")["report"]["doubled"]
    lines = bc.crm_tables()["sales_order_lines"][1]
    orders = bc.crm_tables()["sales_orders"][1]
    with_lines = {x[0] for x in lines}
    assert d["right"] == sum(o[3] for o in orders if o[0] in with_lines)
    assert d["wrong"] == sum(o[3] for o in orders for x in lines if x[0] == o[0]) and d["wrong"] > d["right"]
    d = bb.build("sample")["report"]["doubled"]                         # since n71 the shop's products carry a list price (n71)
    assert (d["column"], d["header"], d["line"], d["right"]) == ("products.list_price", "products", "order_items", 1666.6) and d["wrong"] > d["right"]


def test_build_from_files_and_from_a_columns_list():
    r = bb.build("files", [("orders.csv", b"order_id,customer_id,amount\n1,1,10\n2,9,20\n"), ("customers.csv", b"customer_id,name\n1,a\n")])
    assert r["app"]["list"]["rows"] and {m["name"]: m["value"] for m in r["report"]["measures"]}["Total amount"] == 30
    c = bb.build("columns", None, "orders.order_id\norders.customer_id\ncustomers.customer_id")
    assert not c["report"]["has_data"] and not c["report"]["measures"] and len(c["downloads"]) == 2


def test_one_example_row_runs_through_the_finding_the_contract_and_the_preview():
    """n73: the external review saw three totals in "A total that doubles": the finding's synthetic order (1 000 / 2 000),
    the Power BI preview's list price and a contract with nothing about it. The engine now reads one header row per
    amount finding from the rows (its key, its amount, its lines, what a join counts) and the finding, the domain's
    contract and (in check.js) Onto's answer and the preview repeat it; no number is computed twice."""
    r = bc.analyze("sample")
    f = next(x for x in r["findings"] if x["check"] == "amount_level" and x["amount"]["wrong"] > x["amount"]["right"])
    ex = f["amount"]["example"]
    assert (f["amount"]["header"], f["amount"]["line"], f["amount"]["column"]) == ("orders", "order_lines", "order_amount")
    assert ex == {"key": "order_id", "id": "1", "amount": 1000, "lines": 2, "repeated": 2000}
    assert f["saw"].endswith("For example order_id 1: 1 000 on its orders row; 2 order_lines rows point at it, so the join counts it twice: 2 000.")
    c = r["domains"]["contracts"]["customers"]
    assert c.count("amountLevel.orders.order_amount") == 1 and "order_id 1 is 1 000 on its orders row and 2 order_lines rows point at it, so the join counts it twice (2 000)" in c
    assert "A synthetic example beside these tables (fabric_backend.seed.AMOUNT_DEMO)" in c and r["domains"]["status"] == ts.label("domain_draft")
    other = next(x for x in r["findings"] if x["check"] == "amount_level" and x["amount"]["column"] == "list_price")
    assert other["amount"]["example"] == {"key": "product_id", "id": "4", "amount": 5.9, "lines": 27, "repeated": 159.3}
    assert "amountLevel.products.list_price" in r["domains"]["contracts"]["products"] and "product_id 4 is 5.90 on its products row" in c
    crm = bc.analyze("crm")
    f = next(x for x in crm["findings"] if x["check"] == "amount_level")
    assert f["amount"]["example"] == {"key": "sales_order_no", "id": "SO5001", "amount": 600, "lines": 3, "repeated": 1800}
    assert "sales_order_no SO5001 is 600 on its sales_orders row and 3 sales_order_lines rows point at it, so the join counts it 3 times (1 800)" in crm["domains"]["contracts"]["sales_orders"]
    assert "synthetic example" not in crm["domains"]["contracts"]["sales_orders"]
    cols = bc.analyze("columns", text="orders.order_id\norders.order_amount\norder_lines.order_id\norder_lines.line_no")
    f = next(x for x in cols["findings"] if x["check"] == "amount_level")
    assert "example" not in f["amount"] and "amountLevel" not in "".join(cols["domains"]["contracts"].values())   # no rows, no example


def test_the_browser_reads_an_api_definition_as_describe_backend_does():
    from fabric_backend import server
    from fabric_backend.graphql import decode, definition
    from fabric_backend.infer import plan
    from fabric_backend.seed import schema
    env = definition(plan(schema("shop")), "shop_api", "<ws>", "<item>")
    assert bb._describe(env) == server.describe_definition(decode(env))


def test_the_engine_zip_carries_what_build_imports():
    names = zipfile.ZipFile(io.BytesIO(bc.engine_zip())).namelist()
    for m in ("browser_build", "semantic_model", "rayfin", "app_starter", "graphql", "tool_status", "amounts"):
        assert f"fabric_backend/{m}.py" in names


def test_the_check_page_offers_the_model_and_the_app_and_where_to_go_next(client):
    html = client.get("/check").text
    head = html[html.index('id="check-build-head"'):html.index('id="check-build-head"') + 1500]
    assert "Build a Power BI model" in head and "See it as an app" in head and "Go further with these tables" in head
    # n73: the state line and the findings before the map, the two choices in the map column, the engine's steps folded after it
    assert (html.index('id="check-status"') < html.index('id="check-verdict"') < html.index('id="check-all"') < html.index('id="check-map"')
            < html.index('id="check-build-head"') < html.index('id="check-engine"') < html.index('id="check-steps"') < html.index('id="check-result"'))
    engine = html[html.index('<details class="check-engine"'):html.index("</details>", html.index('<details class="check-engine"'))]
    assert "<summary>How the engine got here</summary>" in engine and " open" not in engine.split(">")[0]
    box = html[html.index('id="check-build"'):html.index("</section>", html.index('id="check-build"'))]
    assert 'href="/start">Connect to my Fabric<' in box and box.count('href="/start"') == 1 and 'href="/support">Get help<' in box
    assert 'id="check-loading"' in html and 'data-mascot="onto"' in html.split('id="check-loading"')[1][:200]
    css = client.get("/static/site.css").text
    assert "@media (prefers-reduced-motion:reduce){.check-hop{animation:none}}" in css


@pytest.mark.skipif(not _playwright_available(), reason="node + playwright not available")
def test_in_a_browser_the_mascot_hops_while_loading_and_the_drafts_download_without_a_request(site):
    from fabric_backend.seed import AMOUNT_DEMO                       # the home page's before and after, as two CSV files
    csv = {n: ",".join(c.split()[0] for c in ddl.split(", ")) + "\n" + "".join(",".join(str(v) for v in r) + "\n" for r in rows)
           for n, (ddl, rows) in AMOUNT_DEMO.items()}
    out = subprocess.run(["node", str(ROOT / "tests/check_build_browser.js"), site] + ([CHROMIUM] if CHROMIUM else []),
                         capture_output=True, text=True, timeout=600,
                         env=os.environ | {"CHECK_ORDERS": csv["orders"], "CHECK_LINES": csv["order_lines"]})
    assert out.returncode == 0, out.stderr[-2000:]
    r = json.loads(out.stdout.strip().splitlines()[-1])
    assert not r["errors"] and all(x.startswith("GET ") for x in r["requests"]), r
    for motion, anim in (("no-preference", "check-hop"), ("reduce", "none")):
        o = r[motion]
        assert o["loading_at_start"] and o["mascot_drawn"] and o["hop_animation"] == anim, o
        assert o["loading_after_result"] is False and o["build_shown"]
        assert "Draft only" in o["model_text"] and "Summed once per header (sales_orders)" in o["model_text"]
        assert "Summed over the joined lines (sales_order_lines)" in o["model_text"] and "14,400" in o["model_text"]
        for w in ("at_1280", "at_375"):                              # n73: finding, folded list, map, the two choices, the folded steps
            assert o[w] == {"in_map_col": True, "below_map": True, "verdict_above_map": True, "engine_below_choices": True, "engine_closed": True, "dom_order": True}, (w, o[w])
        assert 0 <= o["heading_top"] < 120, o["heading_top"]
        assert o["focus"] == "check-model-h" and o["download_name"] == "crm_erp_model.zip" and o["download_head"] == "PK"
        assert o["requests_while_building"] == [], o["requests_while_building"]
        assert o["app_rows"] > 0 and "Download app starterFor Lovable, with Rayfin connector entities from the same plan; the API itself does not exist yet." in o["app_text"]
        assert "Supabase" not in o["app_text"] and "an app starter for Lovable" in o["app_text"]       # n80: the word stays in /docs and /lovable
        assert "This file is " + ts.label("semantic_model_draft")[0].lower() + ts.label("semantic_model_draft")[1:] + "." in o["model_text"]   # n95: said once, above
        assert "Download Power BI projectThe model (.pbip) with the plan's keys and relationships as checked in the rows, and an empty report page." in o["model_text"]
        assert "sales_order_no SO5001" in o["model_text"] and "counts it 3 times" in o["model_text"] and "The model's measure sums it the right way." in o["model_text"]   # n73: the row the finding names
        assert o["next_links"] == ["Connect to my Fabric /start", "Get help /support"]
        assert not o["overflow_375"] and not o["overflow_1280"] and min(o["contrast"]) >= 4.5, o["contrast"]
    o = r["reduce"]
    assert o["shop_doubled"] is True                                   # n73: the example's order, the one the finding and Onto show
    assert "orders.order_amount" in o["shop_doubled_text"] and "order_id 1" in o["shop_doubled_text"] and "2,000" in o["shop_doubled_text"] and "not in this model" in o["shop_doubled_text"]
    assert o["files_doubled"] == ["2,000Summed over the joined lines (order_lines)", "1,000Summed once per header (orders)"], o


@pytest.mark.skipif(not _playwright_available(), reason="node + playwright not available")
def test_the_start_page_fetches_the_engine_ahead_only_when_asked_and_check_then_uses_the_cache(tmp_path):
    """n49: a pointer on a link to /check fetches Pyodide and the engine ahead; /check afterwards asks the server for
    none of them again (counted in the server's own access log)."""
    import socket, sys as _sys, time, urllib.request
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    log = (tmp_path / "access.log").open("w")
    proc = subprocess.Popen([_sys.executable, "-m", "fabric_backend.server", "--host", "127.0.0.1", "--port", str(port)],
                            env=os.environ | {"PRODUCT_NAME": "Krusgraph"}, cwd=ROOT, stdout=log, stderr=log)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/healthz", timeout=1); break
            except Exception:
                time.sleep(0.25)
        out = subprocess.run(["node", str(ROOT / "tests/check_prefetch_browser.js"), base] + ([CHROMIUM] if CHROMIUM else []),
                             capture_output=True, text=True, timeout=300)
    finally:
        proc.terminate(); proc.wait(timeout=10); log.close()
    assert out.returncode == 0, out.stderr[-2000:]
    r = json.loads(out.stdout.strip().splitlines()[-1])
    assert not r["errors"], r["errors"]
    assert r["before_still"] == 0 and r["before_hover"] == 0, r
    if r["connection"] and r["connection"]["type"] == "4g" and not r["connection"]["save"]:
        assert r["after_still"] == 7, r                                # still for a while on a fast connection
    else:
        assert r["after_still"] == 0, r
    want = sorted([f"/static/pyodide/{n}" for n in pages.CHECK_DOWNLOAD] + [f"/check/engine.zip?v={pages.check_vars()['CHECK_ENGINE_V']}"])
    assert r["prefetched"] == want and r["check_done"]
    access = (tmp_path / "access.log").read_text()
    for u in want:
        n = access.count(f'"GET {u} HTTP')
        # once in part 1 (still, fast connection) and once ahead of /check in part 2: never a third time from /check
        assert n == (2 if r["after_still"] else 1), (u, n)


def test_the_start_page_policy_allows_only_the_engine_and_privacy_says_when_it_is_fetched(client):
    r = client.get("/")
    csp = r.headers["content-security-policy"]
    # n92: and the demo plan, which the chat demo fetches once it is opened; exactly these three sources, and the rest of
    # the policy is the other pages'
    src = csp.split("connect-src ", 1)[1].split(";", 1)[0].split()
    assert src == ["testserver/static/pyodide/", "testserver/check/engine.zip", "testserver/demo/plan.json"] and "connect-src 'self'" not in csp
    assert csp.replace("connect-src " + " ".join(src), "connect-src 'self'") == client.get("/start").headers["content-security-policy"]
    assert 'data-check-prefetch="/static/pyodide/pyodide.mjs ' in r.text and f"/check/engine.zip?v={pages.check_vars()['CHECK_ENGINE_V']}" in r.text
    assert client.get("/start").headers["content-security-policy"].count("connect-src 'self'") == 1
    privacy = client.get("/privacy").text
    assert "can download <code>/check</code>" in privacy or "can download `/check`" in privacy
    assert "has not asked to save data" in privacy and "write no usage record" in privacy


@pytest.mark.skipif(not _playwright_available(), reason="node + playwright not available")
def test_in_a_browser_the_download_buttons_keep_their_text_inside(site):
    """n95: under the page's own policy, at 375 and 1280 px, light and dark: each download on /check is a short button
    whose text stays inside its edge, and the page does not scroll sideways."""
    out = subprocess.run(["node", str(ROOT / "tests/check_dl_browser.js"), site] + ([CHROMIUM] if CHROMIUM else []),
                         capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stderr[-2000:]
    r = json.loads(out.stdout.strip().splitlines()[-1])
    assert not r["errors"], r["errors"]
    assert sorted(r["runs"]) == ["dark-1280", "dark-375", "light-1280", "light-375"]
    for k, run in r["runs"].items():
        texts = [i["text"] for i in run["items"]]
        assert texts == ["Download ontology", "Download evidence report", "Download data contract", "Download Power BI project", "Download app starter"], (k, texts)
        assert not run["pageOverflow"], k
        for i in run["items"]:
            assert not i["outside"] and not i["overflow"] and not i["offPage"], (k, i)
