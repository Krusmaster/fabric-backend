"""Round n170: the chat demo's pictures in the MCP Apps cards (founder, 8 November 2026: "in the chat on krusgraph.com you
see the links visually, and proposals for ontology, relationships and data products. I want to see that in Claude too"),
and "Try in Claude" on /start and the home page.

Checked here, with the hosted server against the synthetic shop workspace (test_golden.fabric, seed.py's shop schema):
- the map's data is the tool's plan: one node per table, one edge per relationship, the states from validate_plan's
  counts (passed, failed with the orphan count, not checked) and the review statuses from review_plan;
- the ontology card marks the entity types without a key, with the tool's own reason (composite key, no key);
- the data products card lists only the products domain_draft returned, each with its tables and its two dry-run
  buttons over exactly those tables;
- the text answer is unchanged (the pictures' data is in structuredContent only), and nothing changes with the flag off;
- the drawing is cut from chat-demo.js when the card is built, and building fails loudly when that part changes;
- in Chromium: the cards draw it (nodes, edges, labels that cover no table and no other label, the list under the
  picture), and Try in Claude copies the first question and opens claude.ai/new.
What this does not show: that Claude renders the pictures. That is tried by hand after a deploy (docs/MCP-APPS-PICTURES.md).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote

import pytest

from fabric_backend import mcp_apps, mcp_apps_build as build, mcp_apps_pictures as pictures, mcp_apps_review, pages, server

from test_golden import SRC, fabric  # noqa: F401  (the hosted server against the synthetic shop workspace)
from test_browser import CHROMIUM, site  # noqa: F401  (the site served by the server, for Try in Claude)

TESTS = Path(__file__).parent
SHOP_TABLES = {"customers", "categories", "products", "addresses", "orders", "order_items", "audit_log"}


def _registered(tool, /):
    """The tool the way server.py registers it with the flag on: actions added, then the structured form."""
    fn = getattr(server, tool)
    if tool in build.ACTION_TOOLS:
        fn = build.with_actions(tool, fn, server._item_names, server._workspace_id_ctx)
    return mcp_apps.structured(fn, tool)


def _sc(tool, /, **kw):
    r = _registered(tool)(**kw)
    return r, r.structured_content


def _plan_ids(answer):
    return {f"{r['source']}.{'+'.join(r['source_cols'])}>{r['target']}" for r in answer["relationships"]}


# ------------------------------------------------------------------ the map ------------------------------------------

def test_plan_backends_map_is_the_plan(fabric):
    r, d = _sc("plan_backend", **SRC)
    m = d["map"]
    assert {t["name"] for t in m["tables"]} == SHOP_TABLES
    assert {x["id"] for x in m["relationships"]} == _plan_ids(d)
    keys = {t["name"]: t["key"] for t in m["tables"]}
    assert keys["order_items"] == ["order_id", "line_no"] and keys["audit_log"] == [] and keys["customers"] == ["customer_id"]
    assert {(x["id"], x["rule"]) for x in m["relationships"]} == {(f"{x['source']}.{'+'.join(x['source_cols'])}>{x['target']}", x["rule"]) for x in d["relationships"]}
    assert m["checked"] is False and all("state" not in x for x in m["relationships"])     # planned, not checked


def test_the_text_answer_is_unchanged_and_the_map_is_only_in_structured_content(fabric):
    r, d = _sc("plan_backend", **SRC)
    text = r.content[0].text
    assert "map" not in json.loads(text)
    assert json.loads(text) == json.loads(build.with_actions("plan_backend", server.plan_backend, server._item_names,
                                                             server._workspace_id_ctx)(**SRC))


def test_validate_plans_map_has_each_checks_state(fabric):
    r, d = _sc("validate_plan", **SRC)
    m = d["map"]
    assert m["checked"] is True and {t["name"] for t in m["tables"]} == SHOP_TABLES
    assert len(m["relationships"]) == d["totals"]["relationships"]["checked"] == 7
    assert {x["state"] for x in m["relationships"]} == {"passed"} and all(x["orphans"] == 0 for x in m["relationships"])
    assert "map" not in json.loads(r.content[0].text)


def test_a_failed_check_is_red_with_its_orphans_and_an_unreached_one_not_checked(fabric):
    from fabric_backend.server import _plan
    p, _, _ = _plan("demo", "demo_lh", "shop", None, None, None)
    rels = list(p.relationships)
    first, second = rels[0], rels[1]
    checks = {"relationships": [
        {"source": first.source, "columns": first.source_cols, "target": first.target, "target_columns": first.target_cols,
         "rule": first.rule, "rows_with_value": 40, "orphans": 3, "verdict": "3 of 40 rows point at nothing (orphans)"},
        {"source": second.source, "columns": second.source_cols, "target": second.target, "target_columns": second.target_cols,
         "rule": second.rule, "rows_with_value": 17, "orphans": 0, "verdict": "holds: every row with a value finds its target"}]}
    m = pictures.map_from_plan(p, checks)
    by = {x["id"]: x for x in m["relationships"]}
    a = by[f"{first.source}.{'+'.join(first.source_cols)}>{first.target}"]
    assert a["state"] == "failed" and a["orphans"] == 3
    assert by[f"{second.source}.{'+'.join(second.source_cols)}>{second.target}"]["state"] == "passed"
    assert sum(1 for x in m["relationships"] if x["state"] == "not_checked") == len(rels) - 2


def test_review_plans_map_carries_the_review_and_the_check(fabric):
    _, first = _sc("review_plan", **SRC, validate=True)
    rel = next(x for x in first["map"]["relationships"])
    _, d = _sc("review_plan", **SRC, previous=first["review"], decisions=[{"item": "rel:" + rel["id"], "review": "rejected", "reason": "test"}])
    m = d["map"]
    by = {x["id"]: x for x in m["relationships"]}
    assert by[rel["id"]]["review"] == "rejected"
    assert {x["review"] for k, x in by.items() if k != rel["id"]} == {"proposed"}
    assert {x["state"] for x in m["relationships"]} == {"passed"} and m["reviewed"] is True
    assert {t["name"] for t in m["tables"]} == SHOP_TABLES


# ------------------------------------------------------------------ the ontology proposal ----------------------------

@pytest.mark.parametrize("tool,kw", [("ontology_draft", {}), ("create_ontology", {"name": "shop_ontology"})])
def test_the_ontology_card_marks_the_entity_types_without_a_key_and_why(fabric, tool, kw):
    r, d = _sc(tool, **SRC, **kw)
    o = d["ontology"]
    assert len(o["entities"]) == d["summary"]["entity_types"] == 7
    keyless = {e["name"]: e for e in o["entities"] if not e["key"]}
    assert set(keyless) == {"OrderItems", "AuditLog"} and len(o["entities"]) - len(keyless) == d["summary"]["with_key"]
    assert "composite key" in keyless["OrderItems"]["why_no_key"] and keyless["OrderItems"]["key_columns"] == ["order_id", "line_no"]
    assert "no key was found (rule K3)" in keyless["AuditLog"]["why_no_key"]
    assert all(n.split(":")[0] in keyless for n in d["summary"]["notes"])             # each reason is the tool's own note
    assert sum(1 for l in o["links"] if l["in_ontology"]) == d["summary"]["relationship_types"]
    assert "ontology" not in json.loads(r.content[0].text)


def test_a_created_ontology_has_no_proposal_picture():
    assert pictures.extras("create_ontology", {"dry_run": False, "summary": {}}, {"ontology": {"entities": [1]}}) == {}


# ------------------------------------------------------------------ the data products --------------------------------

def test_the_data_products_card_lists_only_what_domain_draft_returned(fabric):
    r, d = _sc("domain_draft", **SRC)
    text = json.loads(r.content[0].text)
    p = d["products"]
    assert [(x["slug"], x["tables"]) for x in p["products"]] == [(x["slug"], x["tables"]) for x in text["domains"]]
    assert all(x["owner"] is None for x in p["products"])                            # nobody has chosen one
    assert [u["table"] for u in p["unassigned"]] == [u["table"] for u in text["unassigned"]] == ["audit_log"]
    assert len(p["interfaces"]) == len(text["interfaces"])
    # the Builder's buttons: per product an API for GraphQL and a semantic model, dry runs over exactly its tables
    by_product = {}
    for a in d["actions"]:
        assert a["kind"] == "dry_run" and a["arguments"]["dry_run"] is True and a["who"] == "builder"
        by_product.setdefault(a["product"], []).append(a)
    assert set(by_product) == {x["slug"] for x in text["domains"]}
    taken = {"demo_lh", "demo_wh", "shop_api", "shop_model"}
    for dom in text["domains"]:
        acts = by_product[dom["slug"]]
        assert [a["tool"] for a in acts] == ["create_backend", "create_semantic_model"]
        for a in acts:
            assert a["arguments"]["tables"] == dom["tables"] and a["arguments"]["name"].lower() not in taken
            assert a["arguments"]["workspace"] == "demo" and a["arguments"]["source"] == "demo_lh" and a["arguments"]["schema"] == "shop"


def test_a_product_dry_run_offers_create_with_the_same_arguments(fabric):
    _, d = _sc("domain_draft", **SRC)
    button = next(a for a in d["actions"] if a["tool"] == "create_semantic_model")
    dry = json.loads(build.with_actions("create_semantic_model", server.create_semantic_model, server._item_names,
                                        server._workspace_id_ctx)(**button["arguments"]))
    assert dry["dry_run"] is True
    [create] = dry["actions"]
    assert create["arguments"] == {**button["arguments"], "dry_run": False}


# ------------------------------------------------------------------ flag off, building the card ----------------------

def test_with_the_flag_off_nothing_is_kept_and_nothing_is_registered(fabric):
    pictures.keep("map", lambda: 1 / 0)                       # no card listens: nothing runs, nothing raises
    assert mcp_apps.registration("ontology_draft", on=False) == {} and mcp_apps.registration("domain_draft", on=False) == {}
    assert mcp_apps.registration("domain_draft", on=True)["meta"]["ui"]["resourceUri"] == build.CARD_URI
    assert "map" not in json.loads(server.plan_backend(**SRC))


def test_the_drawing_is_the_chat_demos_and_a_change_there_is_caught(tmp_path, monkeypatch):
    js = pictures.picture_js()
    demo = pictures.DEMO_JS.read_text(encoding="utf-8")
    for line in ("function placement()", "function search(names, edges, groups, rows)", "function picture(desc, nodes, edges, groups)"):
        assert line in js and line in demo
    changed = tmp_path / "chat-demo.js"
    changed.write_text(demo.replace("function picture(desc, nodes, edges, groups)", "function drawing(desc, nodes, edges, groups)"))
    monkeypatch.setattr(pictures, "DEMO_JS", changed)
    with pytest.raises(RuntimeError):
        pictures.picture_js()


def test_the_cards_stay_self_contained_and_small():
    for html in (mcp_apps.card_html(), mcp_apps_review.card_html(), build.card_html()):
        assert len(html) < 120_000
        assert 'id="pictures"' in html and "kgDemoPicture" in html
        for bad in ("fetch(", "XMLHttpRequest", " src=", "@import", "url("):
            assert bad not in html


# ------------------------------------------------------------------ in Chromium --------------------------------------

def _playwright() -> bool:
    return bool(shutil.which("node")) and subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


def _draw(tmp_path, card, sc, tool, theme="light", args=None):
    (tmp_path / "card.html").write_text(card, encoding="utf-8")
    (tmp_path / "sc.json").write_text(json.dumps({**sc, "__args": args or {}}, default=str), encoding="utf-8")
    run = subprocess.run(["node", str(TESTS / "mcp_apps_pictures_browser.js"), str(tmp_path / "card.html"), str(tmp_path / "sc.json"), tool, theme],
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-2000:]
    return json.loads(run.stdout)


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_validate_card_draws_the_map_with_states(fabric, tmp_path, theme):
    _, d = _sc("validate_plan", **SRC)
    m = d["map"]
    m["relationships"][0].update(state="failed", orphans=3)        # one red line, to see it drawn
    m["relationships"][1].update(state="not_checked"); m["relationships"][1].pop("orphans", None)
    out = _draw(tmp_path, mcp_apps.card_html(), d, "validate_plan", theme, SRC)
    assert out["errors"] == []
    assert {n["table"] for n in out["nodes"]} == SHOP_TABLES
    assert {e["id"] for e in out["edges"]} == {x["id"] for x in m["relationships"]}
    cls = {e["id"]: e["cls"] for e in out["edges"]}
    assert "st-failed" in cls[m["relationships"][0]["id"]] and "st-not_checked" in cls[m["relationships"][1]["id"]]
    assert sum("st-passed" in c for c in cls.values()) == len(m["relationships"]) - 2
    labels = {l["id"]: l["text"] for l in out["labels"]}
    assert "3 orphans" in labels[m["relationships"][0]["id"]][0] and labels[m["relationships"][0]["id"]][0].startswith(m["relationships"][0]["rule"])
    assert out["overlaps"] == 0 and out["keyMarks"] == 6 and out["noKeyTags"] == 1
    assert len(out["list"]) == 7 + 7 and any("3 orphans" in li for li in out["list"])
    assert out["svgWidth"] <= 720 and "7 tables" in out["svgLabel"]


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_the_build_card_draws_the_plans_map_and_the_review_card_the_rejected_link(fabric, tmp_path):
    _, d = _sc("plan_backend", **SRC)
    out = _draw(tmp_path, build.card_html(), d, "plan_backend", args=SRC)
    assert out["errors"] == [] and {e["id"] for e in out["edges"]} == _plan_ids(d) and out["overlaps"] == 0
    assert all("st-" not in e["cls"] for e in out["edges"])
    _, first = _sc("review_plan", **SRC, validate=True)
    rel = first["map"]["relationships"][0]["id"]
    _, rv = _sc("review_plan", **SRC, previous=first["review"], decisions=[{"item": "rel:" + rel, "review": "rejected"}])
    out = _draw(tmp_path, mcp_apps_review.card_html(), rv, "review_plan", args=SRC)
    assert out["errors"] == [] and out["overlaps"] == 0
    assert "rejected" in {e["id"]: e["cls"] for e in out["edges"]}[rel]
    assert any(li.startswith(rel.split(">")[0].split(".")[0]) and "rejected" in li for li in out["list"])


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_the_ontology_and_products_cards_in_a_browser(fabric, tmp_path):
    _, d = _sc("ontology_draft", **SRC)
    out = _draw(tmp_path, build.card_html(), d, "ontology_draft", args=SRC)
    assert out["errors"] == [] and out["overlaps"] == 0 and out["noKeyTags"] == 2 and out["keyMarks"] == 5
    nokey = {n["table"] for n in out["nodes"] if "nokey" in n["cls"]}
    assert nokey == {"order_items", "audit_log"}
    assert "composite key" in out["text"] and "no key was found (rule K3)" in out["text"]
    _, d = _sc("domain_draft", **SRC)
    out = _draw(tmp_path, build.card_html(), d, "domain_draft", args=SRC)
    assert out["errors"] == []
    assert [p["slug"] for p in out["products"]] == [x["slug"] for x in d["products"]["products"]]
    for p, want in zip(out["products"], d["products"]["products"]):
        assert ", ".join(want["tables"]) in p["text"] and "Owner: not chosen yet" in p["text"]
    assert len(out["productButtons"]) == 2 * len(d["products"]["products"])
    assert all(("Create an API for GraphQL for " in b) or ("Build a semantic model for " in b) for b in out["productButtons"])


# ------------------------------------------------------------------ Try in Claude ------------------------------------

def test_try_in_claude_is_on_the_home_page_and_start_with_the_question():
    # n190: the home page leads with the demo; Try it in Claude stays in step 3 of /start
    assert "data-try-claude" not in pages.render("/")
    for path, connect in (("/start", "#step-3"),):
        html = pages.render(path)
        assert 'data-try-claude' in html and 'href="https://claude.ai/new"' in html, path
        assert f'data-question="{pages.FIRST_QUESTION}"' in html
        assert f'<a href="{connect}">step 3 of the set-up guide</a>' in html
        assert "copies the first question" in html and "no documented way" in html
    q = pages.FIRST_QUESTION
    assert q == ("List my Fabric workspaces, then map how the tables in the lakehouse I choose connect, and check the links "
                 "against the rows.")
    desktop = pages.CLAUDE_DESKTOP_NEW + __import__("urllib.parse").parse.quote(q, safe="")
    assert desktop.startswith("claude://claude.ai/new?q=") and unquote(desktop.split("q=", 1)[1]) == q
    assert "{{TRY_IN_CLAUDE}}" not in pages.start_md() and q in pages.start_md()


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_try_in_claude_copies_the_question_and_opens_a_new_chat(site):  # noqa: F811
    run = subprocess.run(["node", str(TESTS / "try_claude_browser.js"), site] + ([CHROMIUM] if CHROMIUM else []),
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout)
    for path, info in out.items():
        assert info["errors"] == [] and info["visible"], path
        assert info["href"] == "https://claude.ai/new" and info["target"] == "_blank"
        assert info["opened"].startswith("https://claude.ai/new")
        assert info["clipboard"] == pages.FIRST_QUESTION
        assert "Copied the question" in info["noteAfter"]
        assert info["desktop"].startswith("claude://claude.ai/new?q=") and unquote(info["desktop"].split("q=", 1)[1]) == pages.FIRST_QUESTION
    assert out["/start#step-3"]["connect"] == "#step-3"
