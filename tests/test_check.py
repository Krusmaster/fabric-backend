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
    assert r.text.count("Synthetic data") == 3 and "A total that doubles" in r.text and "SAP sales tables" in r.text and "Salesforce + ERP" in r.text
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
