"""Round n225, from the founder's phone test in Fabric of 12 November 2026 (package Org.Krusgraph 1.0.1074).

1. The Data product page: the health of this data product's plan (the page sends its plan id; the answer says the run and
   the plan the word comes from, so an older run's result is never shown as current), and the plan of the latest Create
   recorded in outputs.json (read back for the health when the page sends none).
2. Open in Fabric for an ontology goes to /groups/<workspace>/ontologies/<id> (Learn, "Use Ontology MCP Server").
3. The App card says what Create gives before Create (appWords.APP_BEFORE_CREATE).
4. The editor's own pages at 375, 412 and 1280 px in Chromium (tests/n225_browser.js over tests/fixtures/n225/, written by
   workload/Workload/app/items/ModelItem/phonePages.test.tsx): no horizontal scroll; at phone widths body text at least
   14 px and every tap target at least 44 px. Screenshots go to N225_SHOTS when it is set (never committed)."""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from fabric_backend import lineage, workload_api
from fabric_backend.workload_api import BadRequest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "workload" / "Workload" / "app"
PAGES = ROOT / "tests" / "fixtures" / "n225"
WS = "aaaaaaaa-0000-4000-8000-000000000001"
ITEM = "cccccccc-0000-4000-8000-000000000003"


# ------------------------------------------------------------------ 1. health of this plan, with its run --------------

def _definition(monkeypatch, outputs: dict):
    source = {"workspaceId": WS, "itemId": "lh-1", "itemType": "Lakehouse", "displayName": "demo_lh"}
    parts = [{"path": k, "payload": base64.b64encode(json.dumps(v).encode()).decode()}
             for k, v in (("source.json", source), ("outputs.json", outputs))]

    class R:
        def json(self):
            return {"definition": {"parts": parts}}
    monkeypatch.setattr(lineage, "_definition_response", lambda url, headers: R())


def test_the_page_sends_its_plan_and_that_plan_is_read(monkeypatch):
    _definition(monkeypatch, {"product": {"plan": {"plan_id": "plan-00000001"}}, "plan": {"plan_id": "plan-00000002", "at": "x"}})
    req = workload_api.health_request({"workspace": WS, "item_id": ITEM, "product": "Shop sales", "plan_id": "plan-0123abcd"})
    assert req["plan_id"] == "plan-0123abcd"
    assert workload_api._health_target(req, {})["products"] == [{"name": "Shop sales", "plan_id": "plan-0123abcd"}]


def test_without_one_the_latest_creates_plan_comes_before_the_products(monkeypatch):
    _definition(monkeypatch, {"product": {"plan": {"plan_id": "plan-00000001"}}, "plan": {"plan_id": "plan-00000002", "at": "x"}})
    req = workload_api.health_request({"workspace": WS, "item_id": ITEM, "product": "Shop sales"})
    assert workload_api._health_target(req, {})["products"][0]["plan_id"] == "plan-00000002"


def test_a_plan_id_that_is_not_one_is_refused():
    with pytest.raises(BadRequest):
        workload_api.health_request({"workspace": WS, "item_id": ITEM, "product": "x", "plan_id": "plan-1'; drop"})


def test_the_answer_says_which_run_and_plan_the_word_comes_from():
    got = workload_api._with_word({"products": [{"name": "Shop sales", "plan_id": "plan-0123abcd", "health": "red", "run_id": "r-17",
                                                 "checked_at": "2026-11-11T19:23:00Z", "findings": [{"status": "fail"}] * 7}]})
    assert (got["word"], got["run_id"], got["plan_id"], got["checked_at"]) == ("red", "r-17", "plan-0123abcd", "2026-11-11T19:23:00Z")
    assert got["words"] == "7 failed in the latest run"


# ------------------------------------------------------------------ 2. and 3. ---------------------------------------

def test_open_in_fabric_for_an_ontology_uses_learns_address():
    nav = (APP / "controller" / "NavigationController.ts").read_text()
    entry = nav[nav.index('"Ontology": {'):][:120]
    assert 'frontendTypePath: "ontologies"' in entry
    assert "Use Ontology MCP Server" in nav


def test_the_app_card_says_what_create_gives_and_nothing_more():
    words = (APP / "items" / "ModelItem" / "appWords.ts").read_text()
    line = words[words.index("export const APP_BEFORE_CREATE"):][:400]
    for said in ("empty App item", "the one step left is to run the package's command", "inside Fabric only"):
        assert said in line
    kinds = (APP / "items" / "ModelItem" / "buildWords.ts").read_text()
    assert "three commands" not in kinds and "Create makes the App item" not in kinds
    assert 'enabled: k.kind === "graphql" && saved.length === 0' in kinds   # the App stays unticked unless ticked


# ------------------------------------------------------------------ 4. the editor on a phone ------------------------

def test_the_editor_page_has_a_viewport():
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in (APP / "index.html").read_text()


def _browser() -> bool:
    return bool(shutil.which("node")) and subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


@pytest.fixture(scope="module")
def runs():
    if not _browser():
        pytest.skip("node + playwright not available")
    cmd = ["node", str(ROOT / "tests" / "n225_browser.js"), str(PAGES)] + ([os.environ["N225_SHOTS"]] if os.environ.get("N225_SHOTS") else [])
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, run.stderr[-3000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["errors"] == []
    return out["runs"]


def test_the_pages_are_rendered():
    assert {p.stem for p in PAGES.glob("*.html")} == {"review", "outputs", "product"}


def test_no_horizontal_scroll_at_375_412_and_1280(runs):
    assert {(r["file"], r["width"]) for r in runs} == {(f"{p}.html", w) for p in ("review", "outputs", "product") for w in (375, 412, 1280)}
    for r in runs:
        assert r["scroll"] <= 0, (r["file"], r["width"], r["scroll"])
        assert r["wide"] == [], (r["file"], r["width"], r["wide"])


def test_body_text_is_at_least_14_px_on_a_phone(runs):
    for r in runs:
        if r["width"] <= 412:
            assert r["small"] == [], (r["file"], r["width"], r["small"])


def test_tap_targets_are_at_least_44_px_on_a_phone(runs):
    for r in runs:
        if r["width"] <= 412:
            assert r["targets"], r["file"]
            assert [t for t in r["targets"] if t["h"] < 44] == [], (r["file"], r["width"])
