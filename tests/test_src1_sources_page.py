"""SRC1 (20 November 2026): /sources, /sources/salesforce and /sources/dynamics365 (fabric_backend/sources_page.py).

The pages render; every table they name exists in a pack manifest; every data product is what the engine proposes and
matches the outputs other tests pin; the honesty sentences are there; no ruled-out words; no sideways scroll at 390 px
(tests/browser_src1_sources.js, skipped where Node and Playwright are missing)."""
from __future__ import annotations

import html
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import server, sources_page as sp
from fabric_backend.discovery import PUBLIC_PAGES
from test_site import SALES

ROOT = Path(__file__).resolve().parents[1]
PATHS = ("/sources", "/sources/salesforce", "/sources/dynamics365")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    with TestClient(server.build_app()) as c:
        yield c


@pytest.fixture
def pages(client):
    return {p: client.get(p) for p in PATHS}


def test_the_pages_render_and_are_public(pages):
    for p, r in pages.items():
        assert r.status_code == 200, p
        assert "{{" not in r.text, p
        assert set(PATHS) <= set(PUBLIC_PAGES)


def test_every_table_named_is_in_a_manifest(pages):
    named = 0
    for p, r in pages.items():
        for pack, table in re.findall(r'data-pack="([^"]+)" data-pack-table="([^"]+)"', r.text):
            assert table in {x["name"] for x in sp.manifest(pack)["entities"]}, (p, pack, table)
            named += 1
    assert named > 300


def test_the_tables_come_from_the_manifests(pages):
    text = pages["/sources"].text + pages["/sources/salesforce"].text + pages["/sources/dynamics365"].text
    for pack in ("sap", "salesforce", "dynamics365"):
        for ent in sp.manifest(pack)["entities"]:
            assert f'data-pack="{pack}" data-pack-table="{ent["name"]}"' in text, (pack, ent["name"])


def _products(text: str) -> list[tuple[str, list[str]]]:
    """(product title, pack tables) per row of a data-product table on a page."""
    out = []
    for row in re.findall(r'<tr><th scope="row" data-label="Data product">(.*?)</th><td[^>]*>(.*?)</td>', text, re.S):
        out.append((html.unescape(row[0]), re.findall(r'data-pack-table="([^"]+)"', row[1])))
    return out


def test_dynamics_products_match_the_golden_output(pages):
    golden = json.loads((ROOT / "tests" / "golden" / "pk2_dynamics_products.json").read_text(encoding="utf-8"))
    golden.pop("_about")
    from fabric_backend import dynamics_demo as dd, sap_pack
    want = [(g["title"], [sap_pack.pack_table(t, "dynamics365") for t in dd.PRODUCTS[pid]["tables"]]) for pid, g in golden.items()]
    assert all(len(dd.PRODUCTS[pid]["tables"]) == g["tables"] for pid, g in golden.items())
    assert _products(pages["/sources/dynamics365"].text) == want


def test_salesforce_products_match_the_pinned_doc_section(pages):
    """docs/SALESFORCE.md's generated table is pinned to the engine by tests/test_pk1_salesforce_pack.py."""
    from fabric_backend import sap_pack
    doc = (ROOT / "docs" / "SALESFORCE.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| \d+ \| ([^|]+) \| ([^|]+) \|$", doc, re.M)
    want = [(n.strip(), [sap_pack.pack_table(t.strip(), "salesforce") for t in ts.split(",")]) for n, ts in rows]
    assert len(want) == 4
    assert _products(pages["/sources/salesforce"].text) == want


def test_sap_products_are_what_test_domains_pins(pages):
    """SAPD1: /sources shows the products of the SAP full demo (sap_demo.tables(full=True)), which
    tests/test_sapd1_sap_full_demo.py pins; the small demo's two stay pinned by tests/test_domains.py."""
    from fabric_backend import sap_demo
    got = dict(_products(pages["/sources"].text))
    assert tuple(got) == sap_demo.EXPECTED_FULL["products"]
    assert {"VBAK", "VBAP", "LIKP", "LIPS", "VBRK", "VBRP"} <= set(got["order-to-cash"])
    assert {"EKKO", "EKPO", "RBKP", "RSEG"} <= set(got["procure-to-pay"]) and {"ACDOCA", "BKPF"} <= set(got["finance"])
    assert {"ADRC"} <= set(got["customer master"]) and set(got["pricing"]) == {"KONH", "KONP", "PRCD_ELEMENTS", "T685"}
    assert sorted(t for ts in got.values() for t in ts) == sorted(sap_demo.tables(full=True))


def test_every_product_has_a_question_and_no_question_is_stale():
    for s in sp.SOURCES:
        names = [p["name"] for p in sp.products(s["key"])]
        assert all(p["question"] for p in sp.products(s["key"])), s["key"]
        assert set(sp.QUESTIONS[s["key"]]) == set(names), s["key"]


def test_the_routes_rest_on_sources_that_were_opened():
    for key, routes in sp.ROUTES.items():
        src = {x["id"]: x for x in sp.manifest(key)["sources"]}
        for r in routes:
            assert r["status"] in ("read", "unverified", "not read by the pack")
            for i in r["sources"]:
                assert i in src and src[i].get("verified") is True, (key, i)


def test_the_honesty_sentences_are_on_every_page(pages):
    for p, r in pages.items():
        text = html.unescape(r.text)
        for sentence in sp.HONESTY + (sp.INDEPENDENT,):
            assert sentence in text, (p, sentence)
    sources = html.unescape(pages["/sources"].text)
    assert "verified against data: nothing yet" in sources and "No org was read" in sources
    assert "nothing has been checked against a real environment" in sources
    assert sp.CROSS_NOT_BUILT in sources


def test_no_ruled_out_words_no_prices_no_names(pages):
    for p, r in pages.items():
        low = r.text.lower()
        for word in SALES + ("certified", "certification", "endorsed", "solutions partner", "microsoft partner", "works with claude",
                             "faster", "compliant", "gdpr-ready", "api.sap.com", "help.sap.com"):
            assert word not in low, (p, word)
        assert not re.search(r"(€|\bsek|\beur|\busd|\bkr)\s?\d|\$\s?\d+[.,]\d\d\b", low), p          # no prices
        assert "Use it in Claude" in r.text, p


def test_linked_from_home_and_use_cases(client):
    assert 'href="/sources"' in client.get("/").text
    assert 'href="/sources"' in client.get("/use-cases").text
    assert 'href="/sap"' in client.get("/sources").text


def test_onto_says_the_numbers_on_the_three_cards(pages):
    text = pages["/sources"].text
    cards = re.findall(r'<li class="card src-card".*?</li>', text, re.S)
    assert len(cards) == 3
    for card, s in zip(cards, sp.summary()):
        assert 'data-mascot="onto"' in card
        assert f'knows {s["tables"]} tables' in html.unescape(card)


# ---------------------------------------------------------------- the phone

def _playwright() -> bool:
    import shutil
    return bool(shutil.which("node")) and subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


def _run_browser(script):
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    env = os.environ | {"PRODUCT_NAME": "Krusgraph", "MCP_PUBLIC_URL": "https://krusgraph.test/mcp", "CONTACT_EMAIL": "hello@krusgraph.test",
                        "ENTRA_CLIENT_ID": "00000000-0000-0000-0000-000000000000", "ENTRA_CLIENT_SECRET": "test-only", "KRUSGRAPH_PREVIEW": "1"}
    proc = subprocess.Popen([sys.executable, "-m", "fabric_backend.server", "--host", "127.0.0.1", "--port", str(port)], env=env,
                            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(base + "/healthz", timeout=1); break
            except Exception:
                time.sleep(0.25)
        from tests.test_browser import CHROMIUM
        out = subprocess.run(["node", str(ROOT / "tests" / script), base] + ([CHROMIUM] if CHROMIUM else []),
                             capture_output=True, text=True, timeout=300)
        assert out.returncode == 0, out.stderr[-2000:]
        return json.loads(out.stdout.strip().splitlines()[-1])
    finally:
        proc.terminate(); proc.wait(timeout=10)


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_no_sideways_scroll_at_390_px_light_and_dark():
    res = _run_browser("browser_src1_sources.js")
    assert res["errors"] == []
    for key, r in res["pages"].items():
        assert r["scrollWidth"] <= r["width"] and r["wide"] == [], (key, r)


def test_the_cards_and_tables_ask_the_demo_button_to_step_aside(pages):
    """SRC2: every card, table and module block (a table inside a module's <details> through the <details>) carries data-kgc-avoid, so site.js hides the "Try a demo" button while
    it would cover one (as on /check)."""
    for p, r in pages.items():
        mods = re.findall(r'<details class="src-mod"[^>]*>', r.text)
        assert mods and all("data-kgc-avoid" in m for m in mods), p
        outside = re.sub(r'<details class="src-mod".*?</details>', "", r.text, flags=re.S)
        found = re.findall(r'<(?:li|div) class="(?:card[^"]*|table-wrap[^"]*)"[^>]*>', outside)
        assert found and all("data-kgc-avoid" in m for m in found), (p, [m for m in found if "data-kgc-avoid" not in m])


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_the_demo_button_covers_no_card_or_table_at_390_768_1280_1440():
    """SRC2: at 1280 px the button covered the top right corner of the Dynamics 365 card on /sources. Scrolled from top
    to bottom at four widths, wherever the button is visible its box intersects no card and no table."""
    res = _run_browser("browser_src1_pill.js")
    assert res["errors"] == []
    assert len(res["runs"]) == 12
    for key, r in res["runs"].items():
        assert r["pill"] and r["steps"] > 1, (key, r)
        assert r["hits"] == [], (key, r["hits"])
