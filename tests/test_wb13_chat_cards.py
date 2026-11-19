"""Round WB13: Gustav's phone test in claude.ai on 19 November 2026 (Android, about 390 px wide, dark mode, demo/demo_lh,
SAP order-to-cash tables): "a lot of empty space below the cards, and you cannot really get further in the process".
And the three findings of 18 November that WB12 fixed only in part (#66, #71, #76).

Everything here runs on synthetic data: fabric_backend/sap_demo.py's SAP-shaped tables in SQLite (17 tables, 24 key
links and 10 other joins, one planted orphan and header amounts that repeat on every line: the same counts as on
Gustav's card) and the synthetic shop workspace of tests/golden_support.py. The browser tests draw each card in Chromium
under a fake host at 390 px, light and dark, in a frame 4000 px tall.

One section per finding: #66 step 6 decides on your own data, #71 the small map, #76 the workspace hints, #89 the blank
space, #90 the check results and the counts, #91 the next steps, #92 the Turtle file, #93 the buttons first.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fabric_backend import (evidence, mcp_apps, mcp_apps_build, mcp_apps_next as nxt, mcp_apps_pictures as pictures,
                            mcp_apps_review, mcp_apps_start, mcp_apps_words as words, next_rules, review, sap_demo, server,
                            start_flow as sf)
from fabric_backend import ontology as onto
from fabric_backend.infer import plan

from test_golden import SRC, fabric  # noqa: F401  (the hosted server against the synthetic shop workspace)

TESTS = Path(__file__).parent
SAP = {"workspace": "demo", "source": "demo_lh", "schema": "sap_silver"}
VBAP = "rel:sap_vbap.MANDT+VBELN>sap_vbak"          # the planted orphan: an item of an order that does not exist


@pytest.fixture(scope="module")
def sap():
    schema, execute = sap_demo.sqlite()
    p = plan(schema)
    full = evidence.validate(p, execute, max_items=200)
    rv = review.build(p, plan(schema), {"platform": "fabric", **SAP}, checks=full, checked_at="2026-11-19T10:00Z")
    return {"schema": schema, "plan": p, "full": full, "summary": evidence.summarize(full, p),
            "checks": nxt.check_rows(p, full), "review": rv}


def _structured(tool: str, answer: dict, keep: dict | None = None, call: dict | None = None):
    """The card's CallToolResult for an answer computed here: the same wrapper the hosted server registers."""
    def fn(workspace, source, schema="dbo", ctx=None, **kw):
        for k, v in (keep or {}).items():
            pictures.keep(k, lambda v=v: v)
        return json.dumps(answer)
    fn.__name__ = tool
    return mcp_apps.structured(fn, tool)(**(call or SAP))


def _result(r) -> dict:
    return {"content": [{"type": "text", "text": c.text} for c in r.content], "structuredContent": r.structured_content}


# ------------------------------------------------------------------ #66: step 6 on your own data -----------------------

def test_step_6_on_own_data_asks_each_open_link_with_review_plans_evidence(sap):
    a = sf.guide(**SAP, step="decide", review=sap["review"])
    [d] = a["found"]["decisions"]
    assert d["item"] == VBAP and d["state"] == "open" and d["check"] == "failed"
    assert d["question"].startswith("Is sap_vbap.MANDT+VBELN → sap_vbak right? Some rows point at nothing")
    it = next(x for x in sap["review"]["items"] if x["id"] == VBAP)
    assert d["evidence"][:2] == review.decision_evidence(it)                 # review_plan's own counts, not a copy
    assert any("quarantine" in x for x in d["evidence"])
    decide = [x for x in a["actions"] if x["kind"] == "decide"]
    assert [x["label"] for x in decide] == ["Accept with quarantine", "Reject", "Skip for now"]
    assert all(x["tool"] == "start" and x["arguments"]["step"] == "decide" for x in decide)
    assert decide[0]["arguments"]["plan"]["confirmed"] == [{"source": "sap_vbap", "source_cols": ["MANDT", "VBELN"],
                                                            "target": "sap_vbak", "target_cols": ["MANDT", "VBELN"]}]
    assert a["after"]["secondary"] is True and a["open_decisions"] == 1
    assert not any(x["tool"].startswith("create_") or x["arguments"].get("dry_run") is False for x in a["actions"])


def test_the_decision_is_kept_and_travels_into_steps_7_to_9(sap):
    accept = [x for x in sf.guide(**SAP, step="decide", review=sap["review"])["actions"] if x.get("decision") == "accepted"][0]
    plan_ = accept["arguments"]["plan"]
    b = sf.guide(**SAP, step="decide", review=sap["review"], confirmed=plan_["confirmed"], decisions=plan_["decisions"])
    assert b["found"]["decisions"][0]["state"] == "accepted" and "secondary" not in b["after"]
    assert b["say"].startswith("Every decision is answered.")
    assert [x["label"] for x in b["actions"] if x["kind"] == "decide"] == ["Change to Reject"]
    for step in ("totals", "dry_run", "create"):
        c = sf.guide(**SAP, step=step, confirmed=plan_["confirmed"], decisions=plan_["decisions"])
        assert c["decided"] == ["sap_vbap.MANDT+VBELN → sap_vbak: accepted: the next steps use this link."]
    rejected = sf.guide(**SAP, step="totals", decisions=[{"item": VBAP, "review": "rejected"}])
    assert "the other tools' rules may still propose it" in rejected["decided"][0]          # honest on your own data


def test_the_start_tool_reads_the_review_on_step_6_and_deciding_writes_nothing(fabric, monkeypatch):
    import requests
    a = json.loads(server.start(**SRC, step="decide"))
    assert [d["item"] for d in a["found"]["decisions"]] == ["rel:orders.ship_to_id>addresses"]
    assert "60 of 60 orders.ship_to_id values found in addresses.address_id (100%)." in a["found"]["decisions"][0]["evidence"]
    writes = []
    for verb in ("post", "patch", "put", "delete"):
        orig = getattr(requests, verb)
        monkeypatch.setattr(requests, verb, lambda *x, _o=orig, **k: writes.append(x) or _o(*x, **k))
    accept = [x for x in a["actions"] if x.get("decision") == "accepted"][0]
    b = json.loads(server.start(**accept["arguments"]))
    assert b["found"]["decisions"][0]["state"] == "accepted" and writes == []      # deciding writes nothing to Fabric
    c = json.loads(server.start(**b["after"]["arguments"]))
    assert c["step"]["key"] == "totals" and c["decided"][0].startswith("orders.ship_to_id → addresses: accepted")


def test_one_rule_decides_what_waits_for_a_person():
    base = {"type": "relationship", "review": "proposed", "check": {"status": "passed"}}
    assert not review.needs_decision({**base, "rule": "R1"}) and not review.needs_decision({**base, "rule": "SAP pack"})
    assert review.needs_decision({**base, "rule": "R5"}) and review.needs_decision({**base, "rule": "R6"})
    assert review.needs_decision({**base, "rule": "R1", "check": {"status": "failed"}})
    assert not review.needs_decision({**base, "rule": "R5", "review": "accepted"})
    assert not review.needs_decision({"type": "key", "review": "proposed", "rule": "K5", "check": {"status": "failed"}})


# ------------------------------------------------------------------ #71: the small map ---------------------------------

def test_a_big_map_is_drawn_small_first_with_the_rule_codes_in_words(sap):
    m = pictures.map_from_review({"review": sap["review"]})
    small = pictures.mini_map(m)
    assert len(m["tables"]) == 17 and small["mini"] == {"tables": 8, "of_tables": 17, "links": small["mini"]["links"], "of_links": 24}
    names = {t["name"] for t in small["tables"]}
    assert all(r["source"] in names and r["target"] in names for r in small["relationships"])
    assert "sap_kna1" in names                                               # the customer master has the most links
    assert any(x.startswith("R") or "SAP" in x for x in small["rules"]) or small["rules"] == []
    assert pictures.mini_map({"tables": [{"name": f"t{i}"} for i in range(8)], "relationships": []}) is None


def test_the_start_card_has_the_map_on_steps_4_and_6_with_approved_and_open_links(sap):
    a = sf.guide(**SAP, step="decide", review=sap["review"])
    assert a["map"]["tables"] and a["map_mini"]["mini"]["of_tables"] == 17
    states = {r["id"]: r["review"] for r in a["map"]["relationships"]}
    assert states[VBAP[4:]] == "open"
    m4 = sf.guide(**SAP, step="map", review=sap["review"])
    assert m4["map_mini"] and m4["found"]["summary"].startswith("17 keys and 24 relationships")
    shop = sf.guide(sample=True, step="map")
    assert shop["map"]["tables"] and "map_mini" not in shop                  # 7 tables fit as they are
    assert {r["review"] for r in shop["map"]["relationships"]} == {"accepted", "open"}
    assert shop["map"]["rules"][0].startswith("R1: the column is named after the table it points at")


def test_a_big_ontology_is_drawn_small_first(sap):
    p = sap["plan"]
    o = pictures.ontology_from(onto.bindings(p, "sap_ontology", "sap_silver", None), onto.summary(p, None))
    small = pictures.mini_ontology(o)
    assert len(o["entities"]) == 17 and small["mini"]["tables"] == 8 and len(small["links"]) < len(o["links"])
    out = pictures.extras("ontology_draft", {"summary": {}}, {"ontology": o})
    assert out["ontology"] == o and out["ontology_mini"] == small             # the full picture stays, the small one is added


# ------------------------------------------------------------------ #76: what each workspace holds ---------------------

class _R:
    def __init__(self, code, body):
        self.status_code, self._b = code, body
        self.content = b"x"

    def json(self):
        return self._b


def test_workspace_hints_count_only_what_documented_apis_say(monkeypatch):
    import requests
    calls = []
    items = {"w1": [{"type": "Lakehouse", "id": "l1"}], "w2": [{"type": "Lakehouse", "id": "l2"}],
             "w3": [{"type": "Warehouse", "id": "x"}, {"type": "Lakehouse", "id": "l3"}], "w4": []}
    tables = {"l1": _R(200, {"data": [{"name": "a"}, {"name": "b"}, {"name": "c"}]}),
              "l2": _R(400, {"errorCode": "UnsupportedOperationForSchemasEnabledLakehouse"})}

    def get(url, headers=None, timeout=None, **kw):
        calls.append(url)
        parts = url.split("/v1/workspaces/")[1].split("/")
        if parts[1] == "items":
            return _R(200, {"value": items[parts[0]]})
        return tables[parts[2]]
    monkeypatch.setattr(requests, "get", get)
    server._HINTS.clear()
    h = server._workspace_hints(["w1", "w2", "w3", "w4"], {"Authorization": "Bearer t"})
    assert h == {"w1": "1 lakehouse, 3 tables", "w2": "1 lakehouse", "w3": "1 lakehouse, 1 warehouse",
                 "w4": "no lakehouse or warehouse"}
    assert all("/v1/workspaces/" in c and (c.endswith("/items") or c.endswith("/tables")) for c in calls)
    n = len(calls)
    assert server._workspace_hints(["w1"], {"Authorization": "Bearer t"}) == {"w1": "1 lakehouse, 3 tables"}
    assert len(calls) == n                                                    # from the brief cache


def test_a_slow_workspace_gets_no_hint_never_a_wrong_one(monkeypatch):
    import requests
    import time
    monkeypatch.setattr(server, "HINT_BUDGET", 0.3)

    def get(url, **kw):
        time.sleep(1.0)
        return _R(200, {"value": [{"type": "Lakehouse", "id": "l"}]})
    monkeypatch.setattr(requests, "get", get)
    server._HINTS.clear()
    t0 = time.monotonic()
    assert server._workspace_hints(["slow"], {"Authorization": "Bearer u"}) == {}
    assert time.monotonic() - t0 < 0.9


def test_step_1_shows_the_hint_under_each_workspace(fabric):
    server._HINTS.clear()
    a = json.loads(server.start())
    picks = [x for x in a["actions"] if x["kind"] == "choose"]
    assert picks and all(isinstance(x["hint"], str) for x in picks)
    assert any("lakehouse" in x["hint"] for x in picks)


# ------------------------------------------------------------------ #90: the check results travel ----------------------

def test_the_check_card_says_what_its_numbers_count(sap):
    lines = words.check_lines(sap["summary"], sap["checks"])
    assert lines[0] == "17 of 17 keys hold."
    assert lines[1].startswith("32 of 34 links hold (24 key links and 10 other joins: on a non-key column, valid on a date, or filtered)")
    assert lines[-1] == "In all: 51 passed, 4 failed (1 link, 3 header amounts), 1 not checked (1 link)."


def test_the_review_carries_the_checks_and_says_what_it_does_not_list(sap):
    s = review.summary(sap["review"])
    assert s.startswith("17 keys and 24 relationships") and "checks: 40 passed, 1 failed, 0 stale, 0 not checked." in s
    assert "10 other joins (on a non-key column, valid on a date, or filtered): 9 passed, 0 failed, 1 not counted" in s
    assert "5 header amounts: 3 repeat on every line" in s
    # 41 items + 10 other joins + 5 header amounts = 56 = the check card's 51 + 4 + 1
    assert 17 + 24 + 10 + 5 == sum(sap["checks"]["counts"].values())
    again = review.build(sap["plan"], sap["plan"], {"platform": "fabric", **SAP}, previous=sap["review"])
    assert again["other_checks"] == sap["review"]["other_checks"]           # carried in the file, like the items' checks


def test_every_review_step_after_a_check_carries_the_checks(fabric):
    for tool in ("validate_plan", "ontology_draft", "semantic_model_draft"):
        r = (mcp_apps.structured(getattr(server, tool), tool))(**SRC)
        for s in r.structured_content.get("next") or []:
            if s.get("tool") == "review_plan":
                assert s["arguments"].get("validate") is True or s["arguments"].get("previous"), (tool, s)


# ------------------------------------------------------------------ #91: one next step first, no loops ----------------

def test_each_card_ends_with_one_primary_step_chosen_from_the_plan_state(sap):
    st = next_rules.steps("validate_plan", SAP, sap["summary"], sap["checks"])
    assert [s["label"] for s in st] == ["Decide the 1 open link", "Show what points at nothing", "Use the line amounts"]
    assert st[0]["primary"] is True and sum(1 for s in st if s.get("primary")) == 1
    assert st[0]["start"]["step"] == "decide" and "run start with" in st[0]["say"]
    assert st[1]["arguments"]["fixes"] is True and st[1]["arguments"]["tables"] == ["sap_vbap"]
    assert "line amounts" in st[2]["why"]


def test_all_decided_leads_to_the_builds_dry_run_first(sap):
    conf = [{"source": "sap_vbap", "source_cols": ["MANDT", "VBELN"], "target": "sap_vbak", "target_cols": ["MANDT", "VBELN"]}]
    rows = {**sap["checks"], "rows": [x for x in sap["checks"]["rows"] if x["kind"] != "amount"]}
    st = next_rules.steps("validate_plan", {**SAP, "confirmed": conf}, sap["summary"] | {"totals": {**sap["summary"]["totals"]}}, rows)
    labels = [s["label"] for s in st]
    assert "Decide" not in " ".join(labels) and labels[1:4] == ["Create the semantic model (dry run first)", "Draft the gold views",
                                                                "Create the data agent (dry run first)"]
    model = st[1]
    assert model["tool"] == "create_semantic_model" and model["arguments"]["dry_run"] is True
    agent = st[3]
    assert "tool" not in agent and "create_data_agent" in agent["say"] and "dry_run=True" in agent["say"]


def test_no_dead_end_and_no_loop_after_the_drafts(fabric):
    for tool in ("semantic_model_draft", "ontology_draft", "review_plan"):
        r = mcp_apps.structured(getattr(server, tool), tool)(**SRC)
        steps = r.structured_content.get("next") or []
        assert steps and steps[0].get("primary") is True, tool                   # never a card without a next step
        loop = {"Check against the rows", "Review keys and links", "Draft a semantic model"}
        assert {s["label"] for s in steps} != loop and len({s["label"] for s in steps} & loop) <= 1, tool
        assert not any(s.get("tool") == tool and not s["arguments"].get("fixes") for s in steps), tool   # not what was just done
    r = mcp_apps.structured(server.ontology_draft, "ontology_draft")(**SRC, confirmed=[
        {"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}])
    labels = [s["label"] for s in r.structured_content["next"]]
    assert "Create the ontology (dry run first)" in labels


def test_the_review_card_names_no_creating_tool(fabric):
    rv = mcp_apps.structured(server.review_plan, "review_plan")(**SRC, validate=True,
                                                                confirmed=[{"source": "orders", "source_cols": ["ship_to_id"],
                                                                            "target": "addresses", "target_cols": ["address_id"]}])
    steps = rv.structured_content["next"]
    assert not any(str(s.get("tool", "")).startswith("create_") for s in steps)
    assert any("create_semantic_model" in s["say"] for s in steps)               # a sentence for the chat instead


# ------------------------------------------------------------------ #92: the Turtle file -------------------------------

def test_the_lead_asks_not_to_print_the_turtle_file(fabric):
    r = mcp_apps.structured(server.ontology_draft, "ontology_draft")(**SRC)
    assert nxt.FILES_STAY in r.content[0].text and "ttl" in json.loads(r.content[-1].text)
    v = mcp_apps.structured(server.validate_plan, "validate_plan")(**SRC)
    assert nxt.FILES_STAY not in v.content[0].text


# ------------------------------------------------------------------ the cards in a browser, 390 px, light and dark -----

needs_browser = pytest.mark.skipif(not shutil.which("node") or subprocess.run(["node", "-e", "require('playwright')"],
                                                                              capture_output=True).returncode != 0,
                                   reason="node + playwright not available")
MARGIN = 8                                                                     # px: the card ends where its content ends


def _browse(tmp_path, html: str, data: dict) -> dict:
    (tmp_path / "card.html").write_text(html, encoding="utf-8")
    (tmp_path / "data.json").write_text(json.dumps(data), encoding="utf-8")
    run = subprocess.run(["node", str(TESTS / "wb13_card_browser.js"), str(tmp_path / "card.html"), str(tmp_path / "data.json")],
                         capture_output=True, text=True, timeout=180)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout)
    assert out["errors"] == [], out["errors"]
    return out


def _fits(out: dict) -> None:
    """The reported height never exceeds where the content ends by more than MARGIN, and never cuts it off."""
    for ph in out["phases"]:
        assert ph["reported"] is not None, ph
        assert ph["reported"] <= ph["content"] + MARGIN, f"blank space under the card: {ph}"
        assert ph["reported"] >= ph["content"] - MARGIN, f"the card is cut off: {ph}"
        assert ph["content"] < ph["frame"], ph                                 # the frame is much taller: the test means it


def _cards(sap) -> dict:
    """Each card with a synthetic SAP answer, as the hosted server would send it."""
    p, full = sap["plan"], sap["full"]
    v = _structured("validate_plan", sap["summary"], {"map": pictures.map_from_plan(p, full), "checks": sap["checks"]})
    rv = _structured("review_plan", json.loads(review.answer(sap["review"], 200_000)))
    o = pictures.ontology_from(onto.bindings(p, "sap_ontology", "sap_silver", None), onto.summary(p, None))
    od = _structured("ontology_draft", {"summary": onto.summary(p, None), "ttl": onto.ontology_ttl(p, "sap_ontology", "sap_silver")},
                     {"ontology": o})
    st = mcp_apps.call_result(json.dumps(sf.guide(**SAP, step="decide", review=sap["review"])))
    return {"validate": (mcp_apps.card_html(), v), "review": (mcp_apps_review.card_html(), rv),
            "ontology": (mcp_apps_build.card_html(), od), "start": (mcp_apps_start.card_html(), st)}


@needs_browser
@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("card", ["validate", "review", "ontology", "start"])
def test_every_card_reports_its_content_height_also_after_details_open_and_close(tmp_path, sap, card, scheme):
    html, r = _cards(sap)[card]
    clicks = [{"css": "details.kg-full > summary"}, {"css": "details.kg-full > summary"}] if card != "review" else \
        [{"css": "details.kg-more > summary"}, {"css": "details.kg-more > summary"}]
    if card == "ontology":
        clicks += [{"css": "details.res-file > summary"}, {"css": "details.res-file > summary"}]
    out = _browse(tmp_path, html, {"result": _result(r), "args": SAP, "caps": {"serverTools": {}}, "width": 390,
                                   "scheme": scheme, "clicks": clicks})
    _fits(out)
    # SAP's 17 tables, folded at 390 px (unfolded, the check card was 7031 px and the review card 12524 px). The bound
    # leaves room for other fonts (2324 px here, 2445 px on the CI runner); the folds themselves are checked too.
    assert out["phases"][0]["content"] < 3200, out["phases"][0]
    folds = {"validate": "Show every check (56)", "review": "Show every key and link (", "ontology": "Show the map (all 17",
             "start": "Show the map (all 17"}
    assert any(s.startswith(folds[card]) for s in out["details"]), out["details"]
    opened, closed = out["phases"][1], out["phases"][2]
    assert opened["content"] > out["phases"][0]["content"] and closed["content"] < opened["content"]   # it grew and shrank
    assert not out["overflow"], "the card scrolls sideways at 390 px"
    dark = out["background"] in ("rgb(27, 27, 31)",)
    assert dark == (scheme == "dark"), out["background"]


@needs_browser
@pytest.mark.parametrize("card", ["validate", "ontology", "start"])
def test_on_a_phone_the_next_step_comes_before_the_big_blocks(tmp_path, sap, card):
    html, r = _cards(sap)[card]
    out = _browse(tmp_path, html, {"result": _result(r), "args": SAP, "caps": {"serverTools": {}}, "width": 390, "scheme": "dark"})
    o = out["order"]
    assert o["firstButton"] and o["bigTop"] is not None and o["firstButtonTop"] < o["bigTop"], o
    assert o["firstButtonTop"] < 420, o                                       # within the first phone screen
    if card != "start":
        assert any(b["primary"] for b in out["buttons"]), out["buttons"]
    if card in ("validate", "start"):
        assert any(s.startswith("Show the map (all 17 tables)") for s in out["details"]), out["details"]
    if card == "ontology":
        assert any(s.startswith("Show the map (all 17 entity types)") for s in out["details"]), out["details"]
        assert any(s.startswith("Show the ontology file (Turtle, ") for s in out["details"])
        assert out["pre"] and not out["pre"][0]["open"] and out["pre"][0]["ws"] == "pre"
        assert "a owl:Class" not in out["text"]                                 # the Turtle is not on the card until asked


@needs_browser
def test_step_6_draws_accept_with_quarantine_reject_and_skip(tmp_path, sap):
    html, r = _cards(sap)["start"]
    out = _browse(tmp_path, html, {"result": _result(r), "args": SAP, "caps": {"serverTools": {}}, "width": 390, "scheme": "light"})
    texts = [b["text"] for b in out["buttons"]]
    assert {"Accept with quarantine", "Reject", "Skip for now"} <= set(texts)
    assert "Some rows point at nothing" in out["text"] and "values found in sap_vbak" in out["text"]
