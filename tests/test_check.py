"""n38: /check, the engine in the visitor's browser (Pyodide) on files that are never uploaded."""
import io
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


@pytest.mark.parametrize("kind", ["sample", "sap", "crm"])
def test_the_examples_report_each_engine_step_with_its_time(kind):
    events = []
    r = bc.analyze(kind, emit=events.append)
    assert [e["step"] for e in events] == ["read", "keys", "relationships", "validate", "suggest", "findings"]
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
    assert r.text.count("Synthetic Data") == 3 and "Synthetic data<" not in r.text and "A total that doubles" in r.text and "SAP sales tables" in r.text and "Salesforce + ERP" in r.text
    assert "<input type=\"text\"" not in r.text and "chat" not in r.text.lower().split("<main")[1]
    assert "are not uploaded" in r.text and 'href="/demo"' in r.text and 'href="/local"' in r.text and "Get help with a question" in r.text
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
    assert ts.label("semantic_model_draft") in readme and "Not yet tried: opening this project in Power BI Desktop" in readme
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
    assert bb.build("sample")["report"]["doubled"] is None              # the shop plan has no header amount


def test_build_from_files_and_from_a_columns_list():
    r = bb.build("files", [("orders.csv", b"order_id,customer_id,amount\n1,1,10\n2,9,20\n"), ("customers.csv", b"customer_id,name\n1,a\n")])
    assert r["app"]["list"]["rows"] and {m["name"]: m["value"] for m in r["report"]["measures"]}["Total amount"] == 30
    c = bb.build("columns", None, "orders.order_id\norders.customer_id\ncustomers.customer_id")
    assert not c["report"]["has_data"] and not c["report"]["measures"] and len(c["downloads"]) == 2


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
    box = html[html.index('id="check-build"'):html.index("</section>", html.index('id="check-build"'))]
    assert "Build a Power BI model" in box and "See it as an app" in box
    assert 'href="/start">Create it in your own Fabric<' in box and 'href="/start">Connect to Claude<' in box and 'href="/support">Get help with a question<' in box
    assert 'id="check-loading"' in html and 'data-mascot="onto"' in html.split('id="check-loading"')[1][:200]
    css = client.get("/static/site.css").text
    assert "@media (prefers-reduced-motion:reduce){.check-hop{animation:none}}" in css


@pytest.mark.skipif(not _playwright_available(), reason="node + playwright not available")
def test_in_a_browser_the_mascot_hops_while_loading_and_the_drafts_download_without_a_request(site):
    out = subprocess.run(["node", str(ROOT / "tests/check_build_browser.js"), site] + ([CHROMIUM] if CHROMIUM else []),
                         capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stderr[-2000:]
    r = json.loads(out.stdout.strip().splitlines()[-1])
    assert not r["errors"] and all(x.startswith("GET ") for x in r["requests"]), r
    for motion, anim in (("no-preference", "check-hop"), ("reduce", "none")):
        o = r[motion]
        assert o["loading_at_start"] and o["mascot_drawn"] and o["hop_animation"] == anim, o
        assert o["loading_after_result"] is False and o["build_shown"]
        assert "Draft only" in o["model_text"] and "Right: summed once per sales_orders row" in o["model_text"] and "14,400" in o["model_text"]
        assert o["focus"] == "check-model" and o["download_name"] == "crm_erp_model.zip" and o["download_head"] == "PK"
        assert o["requests_while_building"] == [], o["requests_while_building"]
        assert o["app_rows"] > 0 and "Download crm_erp_app.zip" in o["app_text"]
        assert o["next_links"] == ["Create it in your own Fabric /start", "Connect to Claude /start", "Get help with a question /support"]
        assert not o["overflow_375"] and not o["overflow_1280"] and min(o["contrast"]) >= 4.5, o["contrast"]


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
    assert "connect-src testserver/static/pyodide/ testserver/check/engine.zip;" in csp and "connect-src 'self'" not in csp
    assert 'data-check-prefetch="/static/pyodide/pyodide.mjs ' in r.text and f"/check/engine.zip?v={pages.check_vars()['CHECK_ENGINE_V']}" in r.text
    assert client.get("/start").headers["content-security-policy"].count("connect-src 'self'") == 1
    privacy = client.get("/privacy").text
    assert "can download <code>/check</code>" in privacy or "can download `/check`" in privacy
    assert "has not asked to save data" in privacy and "write no usage record" in privacy
