"""Round LFD8 (25 November 2026): the diff card for propose_change (fabric_backend/mcp_apps_change.py; docs/CHANGES.md,
"The diff card (LFD8)"), behind KRUSGRAPH_MCP_APPS and KRUSGRAPH_CHANGES, both off by default.

Off, nothing changes: no resource, no `_meta`, the listings as before (tests/golden/hosted_listing.json byte for byte is
tests/test_lfd5_propose.py's). On, propose_change points at the card and the default read-only listing stays under
23 500 characters. The card is drawn for each answer on the synthetic shop_lfd sample (SQLite, no network): ok,
question, denied, replan, numbers counted and not counted yet. The click test (the wb15 pattern: tests/lfd8_card_click.js
in Chromium under a fake host, every tools/call answered by the product's own code) measures it with
tools/smooth_measure.py (--change): at most 25 words outside the buttons, one primary button, no dead end, 390 px,
light and dark; Yes calls apply_change only with the token and only when apply_change is registered; No calls nothing.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from fabric_backend import change_diff, changes, mcp_apps, mcp_apps_change as card, tool_listing
from fabric_backend.infer import plan as make_plan

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import smooth_measure  # noqa: E402

from test_n123_switches import _LIST  # noqa: E402

INFO = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse",
            schema="shop", schemas_enabled=True)
IS_TEST = {"column": "is_test", "op": "is_true"}
A2 = {"type": "filter_rows", "table": "customers", "drop_where": IS_TEST, "cascade": ["orders", "order_items", "addresses", "audit_log"]}
A4 = {"type": "add_measure", "name": "Order value per customer",
      "measure": {"form": "ratio", "numerator": {"measure": "Order amount"},
                  "denominator": {"form": "distinct_count", "table": "orders", "column": "customer_id"}}}
SHIP = {"from": {"table": "orders", "columns": ["ship_to_id"]}, "to": {"table": "addresses", "columns": ["address_id"]}}
CALL = {"workspace": "demo", "source": "shop_lh", "schema": "shop"}


def _env(**extra) -> dict:
    base = {k: v for k, v in os.environ.items() if not k.startswith("KRUSGRAPH_")}
    return base | {"PYTHONPATH": str(ROOT)} | extra


def _run(code: str, *args, **env) -> str:
    return subprocess.run([sys.executable, "-c", code, *args], env=_env(**env), cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout


_RESOURCES = r"""
import asyncio, json
from fabric_backend import server
tool = server.mcp._tool_manager.get_tool("propose_change") if hasattr(server, "propose_change") else None
print(json.dumps({"resources": sorted(str(r.uri) for r in asyncio.run(server.mcp.list_resources())),
                  "meta": tool.meta if tool else None}))
"""


@pytest.fixture(scope="module")
def schema():
    from fabric_backend import lfd_demo
    return lfd_demo.sqlite("shop_lfd")[0]


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("KRUSGRAPH_CHANGES", "1")


def _propose(schema, change, applied=None, confirmed=None, numbers=None):
    out = change_diff.propose(change, make_plan(schema, None, confirmed), INFO, applied, confirmed=confirmed,
                              replan=lambda links: make_plan(schema, None, links), numbers=numbers)
    call = {**CALL, "change": change, **({"applied": applied} if applied else {}), **({"confirmed": confirmed} if confirmed else {})}
    return out, call


# ------------------------------------------------------------------ the flags and the listings -----------------------

def test_off_by_default_no_resource_no_meta():
    assert not card.enabled({}) and not card.enabled({"KRUSGRAPH_MCP_APPS": "1"}) and not card.enabled({"KRUSGRAPH_CHANGES": "1"})
    assert card.enabled({"KRUSGRAPH_MCP_APPS": "1", "KRUSGRAPH_CHANGES": "1"})
    assert card.tool_meta(on=False) is None
    off = json.loads(_run(_RESOURCES, KRUSGRAPH_MCP_APPS="1"))                  # cards on, changes off: as before
    assert card.CARD_URI not in off["resources"] and off["meta"] is None
    none = json.loads(_run(_RESOURCES, KRUSGRAPH_CHANGES="1"))                  # changes on, cards off: no card
    assert none["resources"] == [] and none["meta"] is None


def test_on_the_tool_points_at_the_card_and_the_read_only_listing_stays_under_23_500():
    both = json.loads(_run(_RESOURCES, KRUSGRAPH_MCP_APPS="1", KRUSGRAPH_CHANGES="1"))
    assert card.CARD_URI in both["resources"]
    assert both["meta"] == {"ui": {"resourceUri": card.CARD_URI}, "ui/resourceUri": card.CARD_URI}
    for env in ({"KRUSGRAPH_CHANGES": "1"}, {"KRUSGRAPH_CHANGES": "1", "KRUSGRAPH_MCP_APPS": "1"}):
        listed = json.loads(_run(_LIST, "server", KRUSGRAPH_ADVANCED_TOOLS="0", **env))
        assert "propose_change" in [t["name"] for t in listed["tools"]]
        assert listed["ro_size"] <= 23_500, (env, listed["ro_size"])


def test_with_changes_off_the_card_adds_nothing_to_the_apps_extension(monkeypatch):
    monkeypatch.delenv("KRUSGRAPH_CHANGES", raising=False)
    added = []

    class Apps:
        def add_html_resource(self, *a, **k):
            added.append(a[0])
    card.add_to(Apps())
    assert added == []
    monkeypatch.setenv("KRUSGRAPH_CHANGES", "1")
    card.add_to(Apps())
    assert added == [card.CARD_URI]


def test_the_card_loads_nothing_and_names_two_tools_only():
    html = card.card_html()
    low = html.lower()
    for bad in ("src=", "href=", "url(", "@import", "fetch(", "http://", "https://", "xmlhttprequest", "<link"):
        assert bad not in low, bad
    assert "var ALLOWED = [\"propose_change\", \"apply_change\"]" in html
    assert "__" not in html.replace("__proto__", "")                             # every placeholder filled


# ------------------------------------------------------------------ the card for each state ---------------------------

def test_ok_says_what_the_change_does_and_yes_waits_for_apply_change(schema, on):
    out, call = _propose(schema, A4, [A2])
    c = card.card(out, call)
    assert c["result"] == "ok" and c["sentence"] == "Adds the measure Order value per customer."
    assert c["plan"] == ["Measure added: Order value per customer"]
    assert c["numbers"] == {"status": card.NOT_COUNTED, "rows": []}
    assert c["yes"] == {"disabled": card.NOT_READY}                           # LFD6's apply_change is not registered here
    earlier = changes.apply([A2], make_plan(schema))["changes"][0]["id"]
    assert c["undo"]["tool"] == "propose_change"
    assert c["undo"]["arguments"]["change"] == {"type": "revert", "change": earlier}
    assert c["undo"]["arguments"]["applied"] == [A2] and "confirm" not in c["undo"]["arguments"]


def test_yes_carries_the_token_only_when_apply_change_is_listed_and_registered(schema, on, monkeypatch):
    out, call = _propose(schema, A4, [A2])
    from fabric_backend import server
    monkeypatch.setattr(tool_listing, "CHANGE_TOOLS", (*tool_listing.CHANGE_TOOLS, "apply_change"))
    assert card.apply_tool() is None                                            # listed, not registered
    monkeypatch.setattr(server, "apply_change", lambda **k: "{}", raising=False)
    assert card.apply_tool() == {"properties": None}                            # the SDK has no such tool: carry everything
    yes = card.card(out, call)["yes"]
    assert yes["tool"] == "apply_change" and yes["arguments"]["confirm"] == out["confirm"]
    assert yes["arguments"] == {**CALL, "applied": [A2], "change": A4, "confirm": out["confirm"]}
    monkeypatch.setenv("KRUSGRAPH_ADVANCED_TOOLS", "0")
    monkeypatch.setattr(tool_listing, "CHANGE_TOOLS", ("propose_change",))
    assert card.apply_tool() is None and card.card(out, call)["yes"] == {"disabled": card.NOT_READY}   # never an unlisted tool
    no_token = {**out, "confirm": None}
    monkeypatch.setattr(card, "apply_tool", lambda: {"properties": None})
    assert card.card(no_token, call)["yes"] == {"disabled": card.NOT_READY}


def test_yes_carries_only_the_arguments_apply_change_takes(schema, on, monkeypatch):
    out, call = _propose(schema, A4, [A2])
    monkeypatch.setattr(card, "apply_tool", lambda: {"properties": {"workspace", "source", "schema", "applied", "change"}})
    assert set(card.card(out, call)["yes"]["arguments"]) == {"workspace", "source", "schema", "applied", "change", "confirm"}


def test_undo_hides_when_the_list_is_empty_or_revert_is_unknown(schema, on, monkeypatch):
    out, call = _propose(schema, A2)
    assert "undo" not in card.card(out, call)                                   # no earlier change
    out, call = _propose(schema, A4, [A2])
    monkeypatch.setattr(changes, "TYPES", tuple(t for t in changes.TYPES if t != "revert"))
    assert "undo" not in card.card(out, call)


def test_a_revert_says_what_it_takes_out(schema, on):
    cid = changes.apply([A2], make_plan(schema))["changes"][0]["id"]
    out, call = _propose(schema, {"type": "revert", "change": cid}, [A2])
    c = card.card(out, call)
    assert c["sentence"] == "Takes out the filter on customers." and "undo" not in c


def test_questions_show_their_choices_as_new_proposals_and_no_yes(schema, on):
    out, call = _propose(schema, {"type": "filter_rows", "table": "customers"})
    c = card.card(out, call)
    assert c["sentence"] == "Which column marks the customers rows to remove?" and "yes" not in c
    assert c["question"] == out["question"]
    assert [x["label"] for x in c["choices"]] == ["is_test"]
    assert c["choices"][0]["arguments"]["change"] == {"type": "filter_rows", "table": "customers", "drop_where": IS_TEST}
    assert all(x["tool"] == "propose_change" and not x.get("primary") for x in c["choices"])   # a question chooses nothing
    out, call = _propose(schema, {"type": "filter_rows", "table": "customers", "drop_where": IS_TEST})
    c = card.card(out, call)
    assert c["sentence"] == "4 tables point at customers. Remove their rows too?"
    assert [x["label"] for x in c["choices"]] == ["Yes, from all 4", "No, keep their rows"]
    assert sorted(c["choices"][0]["arguments"]["change"]["cascade"]) == sorted(A2["cascade"])
    assert c["choices"][1]["arguments"]["change"]["cascade"] == []
    out, call = _propose(schema, {"type": "add_column", "table": "orders", "from": "addresses", "columns": ["region"]}, [A2])
    c = card.card(out, call)
    assert out["kind"] == "link" and c["sentence"] == "Which column links orders to addresses?"
    assert c["choices"][0]["arguments"]["change"] == {"type": "add_link", **SHIP}
    assert c["choices"][0]["arguments"]["applied"] == [A2]


def test_a_question_about_an_earlier_entry_changes_that_entry(schema, on):
    out, call = _propose(schema, A4, [{"type": "filter_rows", "table": "customers", "drop_where": IS_TEST}])
    assert out["result"] == "question" and out["at"] == 0
    c = card.card(out, call)
    first = c["choices"][0]["arguments"]
    assert first["change"] == A4 and first["applied"][0]["cascade"]


def test_denied_shows_the_reason_and_no_yes(schema, on):
    out, call = _propose(schema, {"type": "add_column", "table": "orders", "from": "addresses", "columns": ["region"], "via": [
        {"from": {"table": "orders", "columns": ["customer_id"]}, "to": {"table": "customers", "columns": ["customer_id"]}},
        {"from": {"table": "addresses", "columns": ["customer_id"]}, "to": {"table": "customers", "columns": ["customer_id"]}}]})
    c = card.card(out, call)
    assert out["kind"] == "fan_out" and "yes" not in c and "choices" not in c
    assert c["sentence"] == "Not allowed: The join path orders → customers → addresses fans out."
    assert c["why"] == out["reason"] and c["back"]["label"].startswith("Back to Start")


def test_replan_offers_to_plan_again_with_the_link(schema, on):
    out, call = _propose(schema, A4, [{"type": "add_link", **SHIP}])
    c = card.card(out, call)
    assert out["result"] == "replan" and c["sentence"] == "The earlier changes need a link the plan does not hold yet."
    (again,) = c["choices"]
    assert again["primary"] is True and again["arguments"]["confirmed"] == out["confirmed"]
    nxt, _ = _propose(schema, A4, [{"type": "add_link", **SHIP}], again["arguments"]["confirmed"])
    assert nxt["result"] == "ok"


def test_numbers_counted_show_before_after_and_the_difference(schema, on):
    from fabric_backend import change_numbers, lfd_demo
    _, execute = lfd_demo.sqlite("shop_lfd")
    out, call = _propose(schema, A2, numbers=lambda *, before, after: change_numbers.count(after["applied"], after["plan"], execute))
    rows = {r["label"]: r for r in card.card(out, call)["numbers"]["rows"]}
    assert rows["customers rows"] == {"label": "customers rows", "before": "12", "after": "10", "difference": "-2"}
    assert rows["Order amount"] == {"label": "Order amount", "before": "56 834.70", "after": "51 296.70", "difference": "\u22125 538.00"}
    double = card.number_rows({"status": "counted", "counted": {"before": {"customers": 12}, "after": {"customers": 10}}})
    assert double["rows"] == [{"label": "customers", "before": "12", "after": "10", "difference": "-2"}]
    late = card.number_rows({"status": "counted", "counted": [{"what": "rows", "table": "orders", "state": "not counted (time)"}]})
    assert late["rows"][0]["before"] == card.NOT_COUNTED


def test_the_hosted_wrapper_adds_the_card_to_structured_content_only(schema, on):
    out, call = _propose(schema, A4, [A2])
    text = change_diff.answer(out, 30_000)

    def propose_change(workspace, source, change, schema="dbo", applied=None, confirmed=None, ctx=None):
        return text
    r = mcp_apps.structured(propose_change, "propose_change")(**call)
    assert r.content[-1].text == text and len(r.content) == 1                  # the text every client gets is unchanged
    assert r.structured_content["change_card"]["sentence"] == "Adds the measure Order value per customer."
    assert r.structured_content["confirm"] == out["confirm"]
    error = mcp_apps.structured(lambda **k: json.dumps({"error": "x", "kind": "not_found"}), "propose_change")(**CALL)
    assert "change_card" not in (error.structured_content or {})


def test_every_sentence_stays_short(schema, on):
    for change, applied in ((A2, None), (A4, [A2]), ({"type": "add_link", **SHIP}, None), ({"type": "filter_rows", "table": "customers"}, None),
                            ({"type": "filter_rows", "table": "customers", "drop_where": "is_test = 1", "cascade": []}, None)):
        out, call = _propose(schema, change, applied)
        assert len(card.card(out, call)["sentence"].split()) <= card.SENTENCE_WORDS + 3, out


# ------------------------------------------------------------------ clicked in Chromium (the wb15 pattern) ------------

def _browser_ready() -> bool:
    if not shutil.which("node"):
        return False
    r = subprocess.run(["node", "-e", "require('playwright').chromium.launch().then(b => b.close())"],
                       capture_output=True, cwd=ROOT, timeout=60)
    return r.returncode == 0


@pytest.fixture(scope="module")
def clicked():
    if not _browser_ready():
        if os.environ.get("CI"):
            pytest.fail("LFD8: the card's click test runs in CI, and Chromium did not start")
        pytest.skip("Chromium (playwright) is not available here; CI runs this test")
    shots = os.environ.get("LFD8_SHOTS", "")
    runs = smooth_measure.change_run(shots) + smooth_measure.change_run("", apply_ready=True)
    return {(r["name"], r["scheme"]): r for r in runs}


def test_click_every_state_renders_and_the_smooth_measures_hold(clicked):
    assert smooth_measure.change_checks(list(clicked.values())) == []
    for scheme in ("light", "dark"):
        for name in ("ok", "not-counted", "counted", "question", "denied", "replan", "undo"):
            run = clicked[(name, scheme)]
            assert not run["errors"] and run["steps"][0]["line"], (name, scheme, run["errors"])
    light, dark = clicked[("ok", "light")]["steps"][0], clicked[("ok", "dark")]["steps"][0]
    assert light["background"] != dark["background"] and light["ink"] != dark["ink"]
    shown = clicked[("ok", "light")]["steps"][0]
    assert shown["folds"] == ["Plan", "Items", "Numbers"]
    assert [b["kind"] for b in shown["buttons"]] == ["yes", "no", "undo"]
    yes = shown["buttons"][0]
    assert yes["primary"] and yes["disabled"] and yes["title"] == card.NOT_READY and card.NOT_READY in shown["text"]


def test_click_folds_open_the_plan_items_with_diffs_and_numbers(clicked):
    steps = {s["key"]: s for s in clicked[("ok-open", "light")]["steps"]}
    assert "Measure added: Order value per customer" in steps["fold:Plan"]["text"]
    items = steps["fold:Items"]["text"]
    assert "semantic model" in items and "update in place" in items and "unchanged" in items and "Show the diff" in items
    assert "1 measure: Order value per customer" in items
    assert "The numbers are not counted yet." in steps["fold:Numbers"]["text"]
    counted = clicked[("counted", "dark")]["steps"][-1]["text"]
    assert "12 → 10" in counted and "(\u22125 538.00)" in counted and "56 834.70 → 51 296.70" in counted
    assert "(-2)" in counted                                                   # a count keeps its form


def test_click_yes_calls_apply_change_only_with_the_token(clicked, schema):
    token = _propose(schema, A4, [A2])[0]["confirm"]
    for scheme in ("light", "dark"):
        off = clicked[("ok", scheme)]
        assert off["calls"] == [] and off["messages"] == []                   # a disabled Yes and No call nothing
        assert off["steps"][1]["line"] == "Adds the measure Order value per customer."
        on = clicked[("ok-ready", scheme)]
        assert [c["name"] for c in on["calls"]] == ["apply_change"]
        args = on["calls"][0]["args"]
        assert args["confirm"] == token and token.startswith("upd-") and args["change"] == A4 and args["applied"] == [A2]
        assert on["steps"][-1]["line"] == "Applied."
        chat = clicked[("ok-ready-chat", scheme)]
        assert chat["calls"] == [] and chat["messages"] == ["Yes, apply this change."]


def test_click_no_changes_nothing(clicked):
    for scheme in ("light", "dark"):
        for name in ("ok", "ok-ready-no"):
            run = clicked[(name, scheme)]
            no = run["steps"][-1]
            assert no["line"] == "Nothing changed." and run["calls"] == [] and run["messages"] == []
            assert [b["kind"] for b in no["buttons"]] == ["back"]               # a way on, not a dead end


def test_click_question_choices_and_undo_propose_again(clicked):
    q = clicked[("question", "light")]
    assert [c["name"] for c in q["calls"]] == ["propose_change", "propose_change"]
    assert q["calls"][0]["args"]["change"]["drop_where"] == IS_TEST
    assert q["steps"][1]["line"] == "4 tables point at customers. Remove their rows too?"
    assert q["steps"][2]["result"] == "ok" and q["steps"][2]["primaries"] == 1
    assert all(b["kind"] != "yes" for b in q["steps"][0]["buttons"] + q["steps"][1]["buttons"])
    u = clicked[("undo", "dark")]
    assert [c["name"] for c in u["calls"]] == ["propose_change"] and u["calls"][0]["args"]["change"]["type"] == "revert"
    assert u["steps"][-1]["line"] == "Takes out the filter on customers."
    r = clicked[("replan", "light")]
    assert r["calls"][0]["args"]["confirmed"] and r["steps"][-1]["result"] == "ok"
    d = clicked[("denied", "light")]
    assert all(b["kind"] == "back" for b in d["steps"][0]["buttons"]) and d["calls"] == []
    assert d["messages"] and "Start Krusgraph" in d["messages"][0]
    assert {c["name"] for run in clicked.values() for c in run["calls"]} <= {"propose_change", "apply_change"}
    assert all(not run["applied"] or run["name"].startswith("ok-ready") for run in clicked.values())
