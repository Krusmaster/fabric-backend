"""Round n103: validate_plan's summary ends with `next_steps`, two or three steps chosen by fixed rules from the result.

Each step names a tool that both servers have, the arguments it needs from this result, one sentence on why, and the
same as one line of text. Only reading and drafting tools appear; detail="full" is unchanged (no next_steps there).
"""
from __future__ import annotations

import asyncio
import copy
import inspect
import json
from pathlib import Path

import pytest

from fabric_backend import evidence, mcp_server, seed, server
from fabric_backend.infer import plan

from test_n101_validate_summary import _adventureworks, _shop

GOLDEN = Path(__file__).parent / "golden"


def _key(table, verdict="unique in all 10 rows"):
    return {"table": table, "columns": [f"{table}_id"], "rule": "K2", "rows": 10, "nulls": 0, "distinct": 10,
            "verdict": verdict}


def _rel(source, target, verdict="holds for all 8 rows with a value", orphans=0):
    return {"source": source, "columns": [f"{target}_id"], "target": target, "target_columns": [f"{target}_id"],
            "rule": "R1", "rows_with_value": 8, "orphans": orphans, "verdict": verdict}


def _amount(max_lines):
    return {"header": "orders", "line": "order_items", "line_columns": ["order_id"], "header_columns": ["order_id"],
            "rule": "R1", "amount_columns": ["freight"],
            "rows_per_header": {"headers": 5, "avg_lines": 2.0, "max_lines": max_lines, "min_lines": 1, "headers_in_table": 5}}


def _full(keys=(), rels=(), amounts=()):
    return {"summary": "s", "keys": list(keys), "relationships": list(rels),
            "amount_levels": {"findings": list(amounts)}, "note": "n"}


def _tools(full, p=None):
    return [s["tool"] for s in evidence.summarize(full, p)["next_steps"]]


BAD_KEY = _key("orders", "not unique: 2 duplicate rows (8 distinct values in 10 rows)")
ORPHANS = _rel("orders", "customers", "3 of 8 rows (37.5%) point at nothing", orphans=3)
WARNED = _rel("orders", "customers", "holds for all 8 rows with a value; but the target key of customers is not unique, "
                                     "so a row can match more than one")


# ------------------------------------------------------------------ each rule -----------------------------------------

def test_a_failed_key_suggests_sample_rows_on_its_table():
    steps = evidence.summarize(_full([BAD_KEY, _key("customers")]))["next_steps"]
    assert steps[0]["tool"] == "sample_rows" and steps[0]["arguments"] == {"table": "orders", "n": 10}
    assert "key:orders" in steps[0]["why"] and "not unique" in steps[0]["why"]


def test_orphans_suggest_a_decision_in_review_plan_and_suggest_relationships():
    steps = evidence.summarize(_full([_key("customers")], [ORPHANS]))["next_steps"]
    assert [s["tool"] for s in steps] == ["review_plan", "suggest_relationships"]
    assert steps[0]["arguments"] == {"validate": True, "tables": ["customers", "orders"]}
    assert "rel:orders.customers_id>customers" in steps[0]["why"] and "decisions" in steps[0]["why"]
    assert steps[1]["arguments"] == {}


def test_a_repeated_header_amount_suggests_answer_query_draft_at_the_header_level():
    steps = evidence.summarize(_full([_key("orders")], amounts=[_amount(3)]))["next_steps"]
    assert steps[0]["tool"] == "answer_query_draft"
    assert steps[0]["arguments"] == {"question": "total freight per orders", "tables": ["orders", "order_items"]}
    assert [s["tool"] for s in steps] == ["answer_query_draft", "review_plan"]          # rule 9 fills to two


def test_the_drafted_question_is_understood_on_the_shop():
    p, full = _shop()
    step = evidence.summarize(full, p)["next_steps"][0]
    from fabric_backend import answers
    out = answers.draft(p, **step["arguments"])
    assert out["tsql"] and "SUM" in out["tsql"] and "DISTINCT" in out["tsql"] and "not_understood" not in out


def test_a_warning_suggests_sample_rows_on_the_target():
    steps = evidence.summarize(_full([_key("orders")], [WARNED]))["next_steps"]
    assert steps[0]["tool"] == "sample_rows" and steps[0]["arguments"] == {"table": "customers", "n": 10}


def test_checks_beyond_max_items_suggest_validate_plan_with_room_for_them():
    def execute(sql):
        return [{"n": 1, "nulls": 0, "distinct_keys": 1, "with_value": 1, "orphans": 0}]
    p = plan(seed.schema("shop"))
    full = evidence.validate(p, execute, max_items=3)
    steps = evidence.summarize(full, p)["next_steps"]
    total = len(p.keys) + len(p.relationships)
    assert steps[0] == {**steps[0], "tool": "validate_plan", "arguments": {"max_items": total}}
    assert f"{total - 3} check(s) did not run" in steps[0]["why"]
    assert "semantic_model_draft" not in [s["tool"] for s in steps]                     # not all checked: no model yet


def test_an_all_passing_plan_suggests_the_semantic_model_and_ontology_drafts():
    p, full = _shop()
    full["amount_levels"]["findings"] = []
    steps = evidence.summarize(full, p)["next_steps"]
    assert [s["tool"] for s in steps] == ["semantic_model_draft", "ontology_draft"]
    assert all(s["arguments"] == {} for s in steps)
    assert "all 12 counted checks passed" in steps[0]["why"]


def test_a_plan_with_nothing_to_check_suggests_plan_backend_and_list_tables():
    assert _tools(_full()) == ["plan_backend", "list_tables"]


def test_a_check_that_could_not_count_is_not_a_failure():
    empty = _key("orders", "empty table: nothing to check")
    assert _tools(_full([empty, _key("customers")])) == ["semantic_model_draft", "ontology_draft"]


# ------------------------------------------------------------------ cap, order, names ---------------------------------

def test_never_more_than_three_and_at_least_two_when_anything_was_checked():
    every = _full([BAD_KEY], [ORPHANS, WARNED], [_amount(3)])
    steps = evidence.summarize(every)["next_steps"]
    assert len(steps) == evidence.MAX_NEXT_STEPS == 3
    assert [s["tool"] for s in steps] == ["sample_rows", "review_plan", "answer_query_draft"]
    p, full = _adventureworks()
    assert len(evidence.summarize(full, p)["next_steps"]) == 3
    for full in (_full([_key("a")]), _full([BAD_KEY]), _full(rels=[ORPHANS]), _full(amounts=[_amount(2)]),
                 _full(rels=[WARNED])):
        assert 2 <= len(evidence.summarize(full)["next_steps"]) <= 3, full


def test_the_order_is_fixed_and_a_tool_appears_once():
    every = _full([BAD_KEY, _key("x", "not a key: 1 of 10 rows have a NULL in it")], [ORPHANS, WARNED], [_amount(3)])
    first = evidence.summarize(every)["next_steps"]
    for _ in range(3):
        assert evidence.summarize(copy.deepcopy(every))["next_steps"] == first
    assert first[0]["arguments"]["table"] == "orders"                                    # the first failed key in the result
    for full in (every, _full([BAD_KEY], [WARNED])):
        tools = [s["tool"] for s in evidence.summarize(full)["next_steps"]]
        assert len(tools) == len(set(tools))


def _registered(mcp):
    return {t.name: t for t in asyncio.run(mcp.list_tools())}


@pytest.mark.parametrize("mcp", [server.mcp, mcp_server.mcp], ids=["hosted", "local"])
def test_every_tool_a_step_can_name_exists_reads_only_and_takes_the_arguments(mcp):
    tools = _registered(mcp)
    module = server if mcp is server.mcp else mcp_server
    for name in evidence.NEXT_STEP_TOOLS:
        assert name in tools, name
        assert tools[name].annotations.read_only_hint is True, name                        # no creating tool, so no dry run
    assert "create_backend" not in evidence.NEXT_STEP_TOOLS
    fulls = [_full([BAD_KEY], [ORPHANS, WARNED], [_amount(3)]), _full([BAD_KEY], [WARNED]), _full(),
             _full(rels=[ORPHANS]), _shop()[1], _adventureworks()[1]]
    for full in fulls:
        for s in evidence.summarize(full)["next_steps"]:
            assert s["tool"] in evidence.NEXT_STEP_TOOLS
            params = inspect.signature(getattr(module, s["tool"])).parameters
            assert set(s["arguments"]) <= set(params), (s["tool"], s["arguments"])


def test_a_creating_tool_would_only_be_named_as_its_dry_run():
    writing = {n for n, t in _registered(server.mcp).items() if not t.annotations.read_only_hint}
    assert "create_backend" in writing and not writing & set(evidence.NEXT_STEP_TOOLS)
    for full in (_full([BAD_KEY], [ORPHANS, WARNED], [_amount(3)]), _shop()[1], _full()):
        for s in evidence.summarize(full)["next_steps"]:
            assert s["tool"] != "create_backend"
            assert s["tool"] not in writing or s["arguments"].get("dry_run") is True


def test_each_step_reads_as_plain_text():
    for full in (_full([BAD_KEY], [ORPHANS], [_amount(3)]), _shop()[1], _full()):
        for s in evidence.summarize(full)["next_steps"]:
            assert sorted(s) == ["arguments", "text", "tool", "why"]
            assert s["text"].startswith(s["tool"] + "(") and s["text"].endswith(s["why"])
            assert "\n" not in s["text"] and s["why"].endswith(".") and s["why"].count(". ") == 0
            for word in ("second", "minute", "fast", "quick", "one click", "one-click", "instant"):
                assert word not in s["text"].lower(), word


# ------------------------------------------------------------------ full unchanged ------------------------------------

def test_full_has_no_next_steps_and_summarize_does_not_change_it():
    p, full = _shop()
    before = json.dumps(full, sort_keys=True, default=str)
    evidence.summarize(full, p)
    assert json.dumps(full, sort_keys=True, default=str) == before and "next_steps" not in full
    for name in ("hosted_tools", "local_tools"):
        for e in json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8")):
            if e.get("tool") == "validate_plan":
                assert ("next_steps" in e["answer"]) == (e["args"].get("detail") != "full"), e["args"]
