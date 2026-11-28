"""Round WB12: what Gustav found on 18 November 2026 running the hosted connector's `start` flow in claude.ai (issues
#66-#77, docs/CHAT-TEST-2026-11-18.md). One test (or a few) per finding: the card's model (start_flow.guide), its texts,
the lead the client model reads, the prompt's argument, and the card rendered in Chromium at 390 px and at desktop width,
light and dark, in a frame much taller than its content.
"""
import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fabric_backend import fix_plan, mcp_apps_next, mcp_apps_start, number_words as nw, server, start_flow as sf

CHOSEN = {"workspace": "ws", "source": "lh", "schema": "shop"}
G = nw.GROUP


def _sample(step, **kw):
    return sf.guide(sample=True, step=step, **kw)


def _start(**kw):
    return json.loads(server.start(**kw))


# ------------------------------------------------------------------ 1 (#66): step 6 decides with buttons ---------------

def test_step_6_has_accept_reject_and_skip_with_the_counted_evidence():
    a = _sample("decide")
    d = a["found"]["decisions"]
    assert len(d) == 1 and d[0]["item"] == "rel:orders.ship_to_id>addresses" and d[0]["state"] == "open"
    assert "60 of 60 orders.ship_to_id values found in addresses.address_id (100%)." in d[0]["evidence"]
    assert "15 distinct values." in d[0]["evidence"]
    decide = [x for x in a["actions"] if x["kind"] == "decide"]
    assert [x["decision"] for x in decide] == ["accepted", "rejected", "skipped"]
    assert [x["label"] for x in decide] == ["Accept", "Reject", "Skip for now"]
    for x in decide:
        assert x["tool"] == "start" and x["arguments"]["sample"] is True and x["arguments"]["step"] == "decide"
        assert x["arguments"]["plan"]["decisions"] == [{"item": d[0]["item"], "review": x["decision"],
                                                        "reason": "decided on the start card"}]
    accepted = decide[0]["arguments"]["plan"]
    assert accepted["confirmed"] == [{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses",
                                      "target_cols": ["address_id"]}]
    assert "confirmed" not in decide[1]["arguments"]["plan"]


def test_next_is_secondary_until_every_decision_is_answered_or_skipped():
    a = _sample("decide")
    assert a["after"]["secondary"] is True and "leaves the open decision open" in a["after"]["why"]
    assert a["say"] == "One link needs you."
    for x in [x for x in a["actions"] if x["kind"] == "decide"]:
        b = _start(**x["arguments"])                     # the button's own call, through the tool
        assert b["step"]["key"] == "decide" and b["found"]["decisions"][0]["state"] == x["decision"]
        assert "secondary" not in b["after"] and b["say"].startswith("Every decision is answered.")


def test_the_decision_travels_into_steps_7_to_9():
    accept = [x for x in _sample("decide")["actions"] if x.get("decision") == "accepted"][0]
    b = _start(**accept["arguments"])
    for _ in range(3):
        b = _start(**b["after"]["arguments"])
        assert b["found"]["decided"] == ["orders.ship_to_id → addresses: accepted: the next steps use this link."]
        assert b["after"]["arguments"]["plan"]["confirmed"][0]["source_cols"] == ["ship_to_id"] if "after" in b else True
        if b["step"]["key"] == "create":
            break
    assert b["step"]["key"] == "create"
    real = sf.guide(**CHOSEN, step="dry_run", confirmed=accept["arguments"]["plan"]["confirmed"],
                    decisions=accept["arguments"]["plan"]["decisions"])
    assert real["actions"][0]["arguments"]["confirmed"] == accept["arguments"]["plan"]["confirmed"]
    assert real["decided"][0].endswith("accepted: the next steps use this link.")


def test_a_skipped_decision_is_never_sent_to_review_plan():
    skip = [{"item": "rel:orders.ship_to_id>addresses", "review": "skipped", "reason": "x"},
            {"item": "rel:a.b>c", "review": "rejected", "reason": "y"}]
    a = sf.guide(**CHOSEN, step="decide", decisions=skip)
    assert a["actions"][0]["tool"] == "review_plan" and a["actions"][0]["arguments"]["decisions"] == [skip[1]]


# ------------------------------------------------------------------ 2 (#67): numbers a person reads ---------------------

@pytest.mark.parametrize("value, text", [(22610.900000000016, f"22{G}610.90"), (1666.6000000000001, f"1{G}666.60"),
                                         (1200, f"1{G}200"), (0.5, "0.50"), (-1234567.891, f"-1{G}234{G}567.89"),
                                         (None, "(blank)"), ("x", "(blank)"), (float("nan"), "(blank)")])
def test_amounts_are_grouped_with_two_decimals(value, text):
    assert nw.amount(value) == text


def test_the_factor_and_rounding():
    assert nw.factor(22610.900000000016, 1666.6000000000001) == "about 13.6x"
    assert nw.factor(2000, 1000) == "2x" and nw.factor(1, 0) == "" and nw.factor(None, 1) == ""
    assert nw.rounded(22610.900000000016) == 22610.9 and nw.rounded(3.0) == 3 and nw.rounded(None) is None


def test_step_7_prints_formatted_sums_the_factor_and_one_plain_sentence():
    f = _sample("totals")["found"]
    assert f["doubled"] == [f"products.list_price summed over the joined order_items rows: 22{G}610.90; once per products "
                            f"row: 1{G}666.60 (about 13.6x)."]
    assert f["advice"] == ["A sum of list_price after joining order_items counts each product once per order_items row; "
                           "sum per product first."]
    assert "0000" not in json.dumps(f)


def test_the_fan_out_sums_are_rounded_at_the_source():
    f = {"counts": {"before": {"max_lines": 3}}, "table": "orders", "column": "amount", "line": "order_items",
         "compare": {"summed_over_lines": "SELECT 1", "summed_per_header": "SELECT 2"}, "questions": [{}]}
    out = fix_plan._fan_out(f, lambda sql: [{"total": 22610.900000000016 if "1" in sql else 1666.6000000000001}])
    assert out["sums"] == {"summed_over_lines": 22610.9, "summed_per_header": 1666.6}


# ------------------------------------------------------------------ 4 (#69): no prose copy of the card --------------------

@pytest.mark.parametrize("step", ["map", "check", "decide", "totals", "dry_run", "create"])
def test_the_lead_says_the_card_shows_it_and_asks_for_one_sentence(step):
    a = _sample(step)
    text = mcp_apps_next.lead("start", a, [], a.get("actions"))
    # DIR1: facts about the display, no instruction to the model (directory review criteria)
    assert "the card already shows this step" in text and "The step's question for the user" in text
    assert "About the display" in text and "Where no card was drawn" in text and "please" not in text.lower()
    assert text.endswith("The full answer follows as JSON.")
    # the findings are on the card and in the JSON, not in the lead (SM2: the step's one sentence may hold a count)
    assert "links hold" not in text and "would count twice" not in text


def test_the_tool_result_keeps_the_full_json_for_clients_without_cards(monkeypatch):
    from fabric_backend import mcp_apps
    wrapped = mcp_apps.structured(server.start, "start")
    r = wrapped(sample=True, step="decide")
    assert "the card already shows this step" in r.content[0].text
    assert json.loads(r.content[1].text)["found"]["decisions"]
    assert r.structured_content["found"]["decisions"][0]["evidence"]


# ------------------------------------------------------------------ 5 (#70): the proof tiles -------------------------------

def test_step_5_shows_the_items_proof_tiles_and_the_grain_line():
    p = _sample("check")["found"]["proof"]
    assert [t[1] for t in p["tiles"]] == ["rows counted", "keys unique", "links holding", "orphans", "duplicate keys"]
    assert p["tiles"][1][0] == "6 of 6" and p["tiles"][2][0] == "6 of 6" and p["orphans"] == 0 and p["duplicates"] == 0
    assert p["rows"] > 0
    assert p["grain"].startswith("134 order_items rows over 60 orders rows") and "2.2×" in p["grain"]


# ------------------------------------------------------------------ 6 (#71): rules in words, arrows -----------------------

def test_step_4_says_r1_in_words_once_and_uses_an_arrow():
    f = _sample("map")["found"]
    assert f["rules"] == ["R1: the column is named after the table it points at"]
    assert all("→" in x and "->" not in x for x in f["links"])
    assert sf.rule_words(["R1", "R2", "R1", "K9"]) == ["R1: the column is named after the table it points at",
                                                        "R2: the column has the same name as the other table's key"]


# ------------------------------------------------------------------ 7 (#72): the footer once ------------------------------

def test_the_footer_is_in_full_on_the_first_card_only():
    assert sf.guide()["honest_open"] is True and _sample("check")["honest_open"] is True
    assert sf.guide(**CHOSEN)["honest_open"] is True              # SM2: step 1 is one card, choosing or chosen
    for a in (sf.guide(**CHOSEN, step="check"), _sample("decide"), _sample("create")):
        assert a["honest_open"] is False and a["honest_short"] == "Only step 5 writes." and "Only step 5 writes" in a["honest"]


# ------------------------------------------------------------------ 8 (#73): a short step list -----------------------------

def test_finished_steps_fold_and_the_sample_skips_step_1():
    a = _sample("dry_run")
    states = {p["key"]: p["state"] for p in a["path"]}
    assert states["data"] == "skipped"
    assert all(p["note"] == "skipped (sample)" for p in a["path"] if p["state"] == "skipped")
    assert a["done_line"] == "Done: 2-3; skipped on the sample: 1"
    assert sf.guide(**CHOSEN, step="dry_run")["done_line"] == "Done: 1-3" and sf.guide()["done_line"] == ""


# ------------------------------------------------------------------ 9 (#74): no dead end on the sample -------------------

def test_step_9_on_the_sample_offers_my_data_and_the_dry_run_again():
    a = _sample("create")
    by = {x["label"]: x for x in a["actions"]}
    assert by["Start on my data"]["arguments"] == {} and by["Start on my data"]["tool"] == "start"
    assert by["Show the dry run again"]["arguments"] == {"sample": True, "step": "dry_run"}
    assert _start(**by["Start on my data"]["arguments"])["step"]["key"] == "data"


# ------------------------------------------------------------------ 10 (#75): the prompt's input -------------------------

def test_the_prompt_argument_reads_as_the_question():
    prompt = {p.name: p for p in asyncio.run(server.mcp.list_prompts())}["start"]
    [arg] = prompt.arguments
    assert arg.name == "use_sample" and arg.required is False
    assert arg.description == "Use the synthetic shop sample? Type yes. Leave empty to use your own Fabric data."


@pytest.mark.parametrize("answer, sample", [("yes", True), ("Yes", True), ("true", True), ("TRUE ", True), ("1", True),
                                            ("no", False), ("false", False), ("", False), (None, False), ("maybe", False)])
def test_the_prompt_accepts_yes_no_true_false_and_empty(answer, sample):
    assert sf.wants_sample(answer) is sample
    args = {} if answer is None else {"use_sample": answer}
    text = asyncio.run(server.mcp.get_prompt("start", args)).messages[0].content.text
    assert ("sample=true" in text) is sample


# ------------------------------------------------------------------ 11 (#76): steps 1-3 list the choices -----------------

def test_step_1_lists_the_workspaces_as_buttons(monkeypatch):
    monkeypatch.setattr(server, "_headers", lambda ctx: {})
    monkeypatch.setattr(server, "_workspaces", lambda h: [{"name": "sales", "id": "1", "capacity_id": "c"},
                                                          {"name": "Archive", "id": "2", "capacity_id": None}])
    a = _start(step="workspace")                         # SM2: the list, as Change shows it (no choosing for you)
    picks = [x for x in a["actions"] if x["kind"] == "choose"]
    assert [(x["label"], x["arguments"], x["hint"]) for x in picks] == [
        ("sales", {"workspace": "sales"}, ""), ("Archive", {"workspace": "Archive"}, "no capacity: nothing can run here")]
    # WB15 (A): Archive has no capacity, so sales is the one usable workspace and comes chosen, with Next on
    assert a["say"] == "Hi! You have one workspace I can use, sales. Shall we start there?" and a["choices"]["search"] is False
    assert a["after"]["arguments"] == {"workspace": "sales"}
    assert not any(x.get("tool") == "list_workspaces" for x in a["actions"])
    assert any(x.get("arguments") == {"sample": True} for x in a["actions"])          # the sample stays offered


def test_a_long_list_gets_a_search_box_and_a_cap(monkeypatch):
    monkeypatch.setattr(server, "_headers", lambda ctx: {})
    monkeypatch.setattr(server, "_workspaces", lambda h: [{"name": f"w{i:03}", "capacity_id": "c"} for i in range(75)])
    a = _start()
    assert a["choices"] == {"count": 75, "shown": sf.CHOICES_MAX, "search": True}
    assert a["say"] == "Hi! Which workspace shall we start in?"          # WB15: the counts are not said


def test_step_2_lists_the_sources_and_step_3_the_schemas_with_counts(monkeypatch):
    monkeypatch.setattr(server, "list_sources", lambda workspace, ctx=None: json.dumps(
        {"workspace": "1", "sources": [{"name": "lh", "id": "a", "type": "Lakehouse"},
                                       {"name": "wh", "id": "b", "type": "Warehouse"}], "graphql_apis": []}))
    a = _start(workspace="ws")
    assert a["stage"] == "source"                        # two sources: nothing is chosen for you
    assert [(x["label"], x["hint"], x["arguments"]) for x in a["actions"] if x["kind"] == "choose"] == [
        ("lh", "lakehouse", {"workspace": "ws", "source": "lh"}), ("wh", "warehouse", {"workspace": "ws", "source": "wh"})]
    monkeypatch.setattr(server, "_source_schemas", lambda w, s, ctx: [{"schema": "dbo", "tables": 0},
                                                                     {"schema": "shop", "tables": 7}])
    b = _start(workspace="ws", source="lh", step="schema")
    picks = {x["label"]: x for x in b["actions"] if x["kind"] == "choose"}
    assert picks["shop"]["hint"] == "7 tables" and picks["shop"]["arguments"] == {**CHOSEN, "step": "check"}
    assert "disabled" not in picks["shop"]
    c = _start(workspace="ws", source="lh")              # SM2: one usable schema is chosen: "ws › lh › shop ✓"
    assert c["stage"] == "data" and c["line"] == "ws › lh › shop ✓" and c["picked"] == ["schema"]
    assert picks["dbo"]["disabled"] == "no tables"


def test_without_a_sign_in_step_1_keeps_its_listing_button():
    a = _start()
    assert a["actions"][0]["tool"] == "list_workspaces" and a["choices_error"]
    assert not any(x["kind"] == "choose" for x in a["actions"])


def test_an_empty_workspace_says_so_and_offers_another(monkeypatch):
    monkeypatch.setattr(server, "list_sources", lambda workspace, ctx=None: json.dumps({"sources": [], "graphql_apis": []}))
    a = _start(workspace="ws")
    assert a["say"].startswith("ws has no lakehouse") and a["actions"][0]["arguments"] == {"step": "workspace"}


def test_the_start_tool_is_listed_as_reaching_fabric():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    ann = tools["start"].annotations
    assert ann.read_only_hint is True and ann.open_world_hint is True and ann.destructive_hint is False


# ------------------------------------------------------------------ 12 (#77): no Next before a choice --------------------

@pytest.mark.parametrize("chosen, why", [({}, "Choose a workspace first."), ({"workspace": "ws"}, "Choose a source first."),
                                         ({"workspace": "ws", "source": "lh"}, "Choose a schema first.")])
def test_next_waits_for_the_choice(chosen, why):
    a = sf.guide(**chosen)
    assert "after" not in a and a["next_waits"]["why"] == why and a["next_waits"]["label"].startswith("Next")
    assert "after" in sf.guide(**CHOSEN) and "next_waits" not in sf.guide(**CHOSEN)


# ------------------------------------------------------------------ the card, rendered (#68 and the rest) ----------------

needs_browser = pytest.mark.skipif(not shutil.which("node") or subprocess.run(["node", "-e", "require('playwright')"],
                                                                              capture_output=True).returncode != 0,
                                   reason="node + playwright not available")


def _res(a: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(a)}], "structuredContent": a}


def _render(tmp_path, answer: dict, width: int = 720, scheme: str = "light", clicks=None, reply=None, caps=None) -> dict:
    (tmp_path / "card.html").write_text(mcp_apps_start.card_html(), encoding="utf-8")
    data = {"result": _res(answer), "width": width, "scheme": scheme, "clicks": clicks or [],
            "caps": {"serverTools": {}} if caps is None else caps}
    if reply is not None:
        data["reply"] = _res(reply)
    (tmp_path / "data.json").write_text(json.dumps(data), encoding="utf-8")
    run = subprocess.run(["node", str(Path(__file__).parent / "wb12_card_browser.js"), str(tmp_path / "card.html"),
                          str(tmp_path / "data.json")], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout)
    assert out["errors"] == []
    return out


SAMPLE_STEPS = ("check", "decide", "dry_run", "create")


@needs_browser
@pytest.mark.parametrize("width", [390, 1024])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_each_sample_card_fits_its_content_at_phone_and_desktop_width(tmp_path, width, scheme):
    backgrounds = set()
    for step in SAMPLE_STEPS:
        out = _render(tmp_path, _sample(step), width=width, scheme=scheme)
        assert not out["overflow"], (step, width)
        assert out["sizes"], step
        last = out["sizes"][-1]["height"]
        assert abs(last - out["mainHeight"]) <= 2 and last < out["frameHeight"] - 300, (step, last, out["frameHeight"])
        backgrounds.add(out["background"])
    assert len(backgrounds) == 1
    assert (backgrounds.pop() == "rgb(255, 255, 255)") is (scheme == "light")


@needs_browser
def test_the_card_draws_the_decision_and_its_buttons(tmp_path):
    a = _sample("decide")
    out = _render(tmp_path, a, width=390)
    kinds = [(b["text"], b["kind"]) for b in out["buttons"]]
    assert ("Accept", "decide") in kinds and ("Reject", "decide") in kinds
    assert ("Skip for now", "decide") not in kinds                # SM2: Next leaves it open; two buttons plus Next
    nxt = [b for b in out["buttons"] if b["text"].startswith("Next:")]
    assert nxt and "st-secondary" in nxt[0]["cls"]
    assert "60 of 60 found (100%)." in out["text"]
    accept = [x for x in a["actions"] if x.get("decision") == "accepted"][0]
    after = _sample("decide", decisions=accept["arguments"]["plan"]["decisions"], confirmed=accept["arguments"]["plan"]["confirmed"])
    clicked = _render(tmp_path, a, clicks=[{"text": "Accept"}], reply=after)
    calls = [dict(m["params"]) for m in clicked["log"] if m.get("method") == "tools/call"]
    assert all(c.pop("_meta", None) == {"io.krusgraph/from": "card"} for c in calls), calls   # SC2: the card's mark, only that
    assert calls == [{"name": "start", "arguments": accept["arguments"]}]
    assert "Your decision: accepted." in clicked["text"]


@needs_browser
def test_the_card_draws_tiles_rules_folded_steps_and_the_short_footer(tmp_path):
    check = _render(tmp_path, _sample("check"), width=390)
    # SM2: one line each for the map, the rows and the totals; the tiles, the sums, the grain line, the step list, the
    # footer and the rule codes in words are under the one Details fold
    for word in ("7 tables, 6 links, 1 needs you.", "6 of 6 links hold.", "1 amount would count twice."):
        assert word in check["text"], word
    for word in ("rows counted", "2.2×", "1. Your data", "Steps 1-4 only read", "Only step 5 writes", f"22{G}610.90"):
        assert word not in check["text"], word
    assert "Details" in check["text"]
    first = _render(tmp_path, _sample("check"), width=390, clicks=[{"css": "details#details > summary"}])
    assert "Steps 1-4 only read" in first["text"] and "R1: the column is named after the table it points at" in first["text"]
    assert "→" in first["text"] and "rows counted" in first["text"] and "keys unique" in first["text"]
    assert f"22{G}610.90" in first["text"] and "about 13.6x" in first["text"]


@needs_browser
def test_the_card_lists_choices_disables_empty_ones_and_waits_for_the_choice(tmp_path):
    options = {"step": "schema", "items": [{"name": "dbo", "tables": 0}, {"name": "shop", "tables": 7}, {"name": "sales", "tables": 3}]}
    out = _render(tmp_path, sf.guide(workspace="ws", source="lh", options=options), width=390)
    by = {b["text"]: b for b in out["buttons"]}
    assert by["shop7 tables"]["disabled"] is False and by["dbono tables"]["disabled"] is True
    waits = [b for b in out["buttons"] if b["kind"] == "next-waits"]
    assert waits and waits[0]["disabled"] is True and "Choose a schema first." in out["text"]
    many = {"step": "workspace", "items": [{"name": f"w{i}"} for i in range(12)]}
    searched = _render(tmp_path, sf.guide(options=many), width=390, clicks=[{"text": "w11"}], reply=sf.guide(workspace="w11"))
    calls = [dict(m["params"]) for m in searched["log"] if m.get("method") == "tools/call"]
    assert all(c.pop("_meta", None) == {"io.krusgraph/from": "card"} for c in calls), calls   # SC2: the card's mark, only that
    assert calls == [{"name": "start", "arguments": {"workspace": "w11"}}] and "Step 1 of 5" in searched["text"]


@needs_browser
def test_the_sample_create_card_offers_the_way_out(tmp_path):
    out = _render(tmp_path, _sample("create"), width=390)
    texts = [b["text"] for b in out["buttons"]]
    assert "Start on my data" in texts and "Show the dry run again" in texts
