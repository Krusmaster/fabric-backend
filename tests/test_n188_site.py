"""Round n188: three shorter points on the home page and the SAP point on its own page (/sap); four tiles under "Go
further with these tables" on /check; "Which Krusgraph should I use?" first on the docs start page and in the docs menu (n196: after "What Krusgraph does").
The browser half runs tests/n188_browser.js."""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import discovery, offering, server, workload_api

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


# ------------------------------------------------------------------ 1. the home page's three points, and /sap ---------

def test_the_three_points_and_the_sap_line_left_the_home_page_for_the_docs(client):
    """n196: the sentence, the three points and the SAP line moved from the home page to the top of /docs
    (tests/test_n196_home_film.py pins their place there)."""
    html = client.get("/").text
    assert "See how your tables connect:" not in html and 'class="usp"' not in html and "usp-sap" not in html
    docs = client.get("/docs").text
    assert "See how your tables connect: the rule behind every proposed link, and the row counts once you run the check." in docs   # n224: S1 section 4 #1
    line = re.search(r'<a href="/sap">(SAP tables[^<]*)</a>', docs).group(1)
    assert "MANDT" in line and len(line.split()) <= 16


def test_the_third_point_says_creates_only_for_what_the_model_item_creates():
    """'Creates' is said for the Krusgraph Model item's outputs (workload_api.KINDS); the silver and gold tables fill when
    the pipeline runs, and /check stays a draft."""
    p3 = discovery.USP_POINTS[2]
    labels = {v["label"] for v in workload_api.KINDS.values()}
    assert {"Silver notebook", "Gold views", "Pipeline", "Semantic model", "Report", "API for GraphQL", "Ontology", "Data agent",
            "App (Rayfin, preview)"} == labels
    for word in ("silver and gold notebooks", "a pipeline", "a semantic model", "a report", "an ontology", "a data agent",
                 "an API for GraphQL", "an App (preview)", "from the plan you reviewed"):
        assert word in p3, word
    assert "the silver and gold tables fill when the pipeline runs" in p3 and "/check" in p3 and "drafts" in p3


def test_sap_page_exists_with_sources_and_its_links_resolve(client):
    r = client.get("/sap")
    assert r.status_code == 200
    html = r.text
    assert "<h1>SAP keys and order-to-cash links</h1>" in html
    assert "Keys with MANDT and the order-to-cash links for VBAK, VBAP and their neighbours, each citing a public SAP page (not all of them re-read yet; nothing is verified against an SAP system)." in html
    assert "Draft only" in html and "not on an SAP system" in html
    body = html[html.index('data-page="sap"'):]
    body = body[:body.index("</main>")] if "</main>" in body else body
    # every key starts with MANDT, and VBAP -> VBAK is applied with its sources
    keys = re.findall(r'<tr><th scope="row"><code>(\w+)</code></th><td>[^<]*</td><td><code>(\w+)</code>', body)
    assert keys[:2] == [("VBAK", "MANDT"), ("VBAP", "MANDT")] and all(k == "MANDT" for _, k in keys)
    assert re.search(r"<code>VBAP</code> \(<code>MANDT</code>, <code>VBELN</code>\) → <code>VBAK</code>", body)
    # numbered sources: every [n] points at a listed source, and each source links out
    refs = set(re.findall(r'href="#(sap-src-[\w-]+)"', body))
    ids = set(re.findall(r'<li id="(sap-src-[\w-]+)">', body))
    assert refs and refs == ids
    assert all(u.startswith("https://") for u in re.findall(r'<li id="sap-src-[\w-]+"><a href="([^"]+)"', body))
    # the site's own links on the page resolve
    for href in set(re.findall(r'href="(/[^"#?]*)', body)):
        assert client.get(href).status_code == 200, href
    assert "/sap" in discovery.PUBLIC_PAGES and "/sap</loc>" in client.get("/sitemap.xml").text
    assert 'href="/sap"' not in client.get("/").text and 'href="/sap"' in client.get("/docs").text   # n196: the line moved to /docs


def test_docs_and_llms_carry_the_three_points_and_the_sap_line(client):
    for path in ("/docs.md", "/llms.txt"):
        text = client.get(path).text
        assert all(p in text for p in discovery.USP_POINTS) and "SAP knowledge from public sources" not in text, path
        assert discovery.USP_SAP[0] in text and "/sap" in text, path


# ------------------------------------------------------------------ 2. /check: four tiles ----------------------------

def test_check_has_the_two_tiles_and_the_place_for_the_other_two():
    tpl = (ROOT / "fabric_backend/page_templates/check.html").read_text()
    grid = tpl[tpl.index('<div class="check-build-choices">'):tpl.index("</div>\n    </div>\n  </div>\n  <details class=\"check-engine\"")]
    assert grid.index('id="check-build-model"') < grid.index('id="check-build-app"') < grid.index('id="check-evidence"')
    js = (ROOT / "fabric_backend/static/check.js").read_text()
    assert '"lav", "check-tile-ontology", "Build a Fabric IQ ontology"' in js
    assert '"mustard", "check-tile-evidence", "Hand over the evidence"' in js
    css = (ROOT / "fabric_backend/static/site.css").read_text()
    assert ".check-build-head .check-build-choices{grid-template-columns:minmax(0,1fr)}" in css
    assert "@media (min-width:760px){.check-build-head .check-build-choices{grid-template-columns:repeat(2,minmax(0,1fr))}}" in css


def _playwright() -> bool:
    return bool(shutil.which("node")) and subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


@pytest.fixture(scope="module")
def browser():
    if not _playwright():
        pytest.skip("node + playwright not available")
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    env = os.environ | {"PRODUCT_NAME": "Krusgraph", "MCP_PUBLIC_URL": "https://krusgraph.test/mcp", "CONTACT_EMAIL": "hello@krusgraph.test",
                        "ENTRA_CLIENT_ID": "00000000-0000-0000-0000-000000000000", "ENTRA_CLIENT_SECRET": "test-only"}
    proc = subprocess.Popen([sys.executable, "-m", "fabric_backend.server", "--host", "127.0.0.1", "--port", str(port)], env=env,
                            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(base + "/healthz", timeout=1); break
            except Exception:
                time.sleep(0.25)
        else:
            pytest.fail("server did not start")
        run = subprocess.run(["node", str(ROOT / "tests" / "n188_browser.js"), base], capture_output=True, text=True, timeout=600)
        assert run.returncode == 0, run.stderr[-3000:]
        yield json.loads(run.stdout.strip().splitlines()[-1])
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_browser_four_tiles_two_by_two_on_desktop_and_stacked_on_a_phone(browser):
    assert browser["errors"] == []
    assert sorted(browser["runs"]) == ["dark-1280", "dark-375", "light-1280", "light-375"]
    for k, run in browser["runs"].items():
        t = run["tiles"]
        assert [x["title"] for x in t] == ["Build a Power BI model", "See it as an app", "Build a Fabric IQ ontology", "Hand over the evidence"], k
        assert all(c in x["cls"].split() for c, x in zip(("coral", "sage", "lav", "mustard"), t)), k
        assert len({tuple(x["bg"]) for x in t}) == 4, (k, [x["bg"] for x in t])      # four colours of the mascot palette
        if k.endswith("1280"):
            assert run["columns"] == 2, k
            assert t[0]["top"] == t[1]["top"] < t[2]["top"] == t[3]["top"], (k, t)
            assert t[0]["left"] == t[2]["left"] < t[1]["left"] == t[3]["left"], (k, t)
        else:
            assert run["columns"] == 1, k
            assert len({x["left"] for x in t}) == 1 and [x["top"] for x in t] == sorted(x["top"] for x in t), (k, t)
        assert not run["pageOverflow"], k
        assert run["status"] == "These files are drafts for you to review." and run["statusBelow"], (k, run["status"])
        assert t[2]["link"] == "Download ontology" and t[2]["tip"], k                    # the ? help stays
        assert t[3]["link"] == "Download evidence report", k


def test_browser_tile_text_contrast_is_aa_and_focus_is_visible(browser):
    for k, run in browser["runs"].items():
        for tile in run["tiles"]:
            for x in tile["texts"]:
                assert x["ratio"] >= 4.5, (k, tile["id"], x)
        assert all(f["active"] and f["outline"] for f in run["focus"].values()), (k, run["focus"])


def test_browser_each_tile_download_still_works(browser):
    for k, run in browser["runs"].items():
        d = run["downloads"]
        onto, ev = d["#check-tile-ontology a.check-dl"], d["#check-tile-evidence a.check-dl"]
        assert onto["name"] == "shop_ontology.rdf" and onto["head"].startswith('<?xml version="1.0"') and onto["bytes"] > 500, (k, onto)
        assert ev["name"] == "shop_evidence_report.md" and ev["head"].startswith("#") and ev["bytes"] > 500, (k, ev)


# ------------------------------------------------------------------ 3. the docs: Which Krusgraph first ----------------

def test_docs_start_page_has_which_krusgraph_after_what_krusgraph_does(client):
    """n196: "What Krusgraph does" (the home page's sentence and points) comes first, then "Which Krusgraph should I use?"."""
    html = client.get("/docs").text
    art = html[html.index('<article class="prose docs">'):]
    after_h1 = art[art.index("</h1>"):]
    which = after_h1[after_h1.index("<p><strong>Which Krusgraph should I use?</strong></p>"):]
    assert after_h1.index("See how your tables connect:") < after_h1.index("Which Krusgraph should I use?")
    rows = re.search(r"<ul>(.*?)</ul>", which, re.S).group(1)
    lis = re.findall(r"<li>(.*?)</li>", rows, re.S)
    assert len(lis) == 5 == len(offering.DECIDE)
    for (q, key), li in zip(offering.DECIDE, lis):
        assert q in _plain(li) and offering.way(key)["name"] in li, li
    assert 'href="/choose"' in which[:which.index("</ul>") + 200]
    md = client.get("/docs.md").text
    assert md.index("See how your tables connect:") < md.index("Which Krusgraph should I use?")


def test_docs_menu_starts_with_which_krusgraph(client):
    for path in ("/docs", "/docs/get-started"):
        html = client.get(path).text
        for nav in ('<nav class="docs-menu" aria-label="Docs">', '<details class="docs-menu-m"><summary>Docs menu</summary><nav aria-label="Docs">'):
            tree = html[html.index(nav) + len(nav):]
            first = re.search(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', tree)
            assert first.groups() == ("/choose", "Which Krusgraph should I use?"), (path, nav)
            assert tree[:tree.index("</nav>")].count('href="/choose"') == 1
