"""Round n219: Start Krusgraph, a guided path in the chat (fabric_backend/start_flow.py, the `start` prompt and tool).

What is pinned here: the prompt is listed with its title; the tool is read-only; each step returns the next step's
button (tool and arguments) and the `start` call that follows, with what was chosen carried over; every button names a
tool of the hosted listing with arguments its inputSchema accepts; a vague first message ('start', 'help', 'what can
you do', 'check my data') is pointed at the flow by the server's instructions and the tool's description; writing
needs the dry run's names and a second, explicit confirmation; the synthetic shop runs the same path without Fabric.
"""
import asyncio
import json

import pytest

from fabric_backend import server, start_flow as sf

TOOLS = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
CHOSEN = {"workspace": "ws", "source": "lh", "schema": "shop"}
WRITERS = {"create_pipeline", "create_semantic_model", "create_report", "create_backend", "create_ontology",
           "create_data_agent"}


def _buttons(answer):
    return [a for a in answer["actions"] if a.get("tool")]


def _accepts(tool: str, arguments: dict) -> None:
    props = TOOLS[tool].input_schema.get("properties", {})
    extra = set(arguments) - set(props)
    assert not extra, f"{tool} does not take {extra}"
    for req in TOOLS[tool].input_schema.get("required", []):
        assert req in arguments, f"{tool} needs {req}"


def test_the_prompt_is_listed_with_its_title():
    prompts = {p.name: p for p in asyncio.run(server.mcp.list_prompts())}
    assert sf.PROMPT in prompts and prompts[sf.PROMPT].title == "Start Krusgraph"
    got = asyncio.run(server.mcp.get_prompt(sf.PROMPT, {}))
    text = got.messages[0].content.text
    assert got.messages[0].role == "user" and "start tool" in text and "Create nothing unless I confirm" in text
    sample = asyncio.run(server.mcp.get_prompt(sf.PROMPT, {"sample": "yes"})).messages[0].content.text
    assert "sample=true" in sample


def test_the_tool_is_listed_read_only():
    t = TOOLS["start"]
    assert t.annotations.read_only_hint is True and t.annotations.destructive_hint is False
    assert t.title and "Start Krusgraph" in t.title


@pytest.mark.parametrize("phrase", sf.VAGUE)
def test_a_vague_first_message_reaches_the_flow(phrase):
    instructions = server.mcp.instructions
    assert f"'{phrase}'" in instructions and "start tool" in instructions
    assert f"'{phrase}'" in " ".join(TOOLS["start"].description.split())


def _walk():
    """Every step of the path from nothing chosen to the dry run, following `after` each time."""
    seen = []
    a = sf.guide()
    seen.append(a)
    a = sf.guide(workspace="ws")
    seen.append(a)
    a = sf.guide(workspace="ws", source="lh")
    seen.append(a)
    a = sf.guide(**CHOSEN)
    while True:
        seen.append(a)
        if "after" not in a or a["step"]["key"] == "dry_run":
            break
        nxt = a["after"]
        assert nxt["tool"] == "start"
        a = json.loads(server.start(**nxt["arguments"]))
    return seen


EXPECTED = {"workspace": "list_workspaces", "source": "list_sources", "schema": "plan_backend", "map": "plan_backend",
            "check": "validate_plan", "decide": "review_plan", "totals": "validate_plan", "dry_run": "create_pipeline"}


def test_each_step_returns_the_next_steps_button_with_the_right_tool_and_arguments():
    steps = _walk()
    assert [s["step"]["key"] for s in steps] == list(EXPECTED)
    for s in steps:
        key = s["step"]["key"]
        first = _buttons(s)[0]
        assert first["tool"] == EXPECTED[key], key
        assert first["say"].startswith(first["label"]) and first["tool"] in first["say"]
        for b in _buttons(s):
            _accepts(b["tool"], b["arguments"])
            assert b["arguments"].get("dry_run") is not False, f"step {key} writes"
        if "after" in s:
            _accepts("start", s["after"]["arguments"])
    by = {s["step"]["key"]: s for s in steps}
    assert _buttons(by["source"])[0]["arguments"] == {"workspace": "ws"}
    assert _buttons(by["schema"])[0]["arguments"] == {"workspace": "ws", "source": "lh"}     # no schema: every one listed
    assert _buttons(by["map"])[0]["arguments"] == CHOSEN
    assert _buttons(by["totals"])[0]["arguments"] == {**CHOSEN, "fixes": True}
    assert by["map"]["after"]["arguments"] == {**CHOSEN, "step": "check"}


def test_what_was_chosen_travels_with_the_steps():
    keys = {"order_items": ["order_id", "line_no"]}
    confirmed = [{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}]
    decisions = [{"item": "rel:orders.ship_to_id>addresses", "review": "accepted", "reason": "checked"}]
    a = sf.guide(**CHOSEN, keys=keys, confirmed=confirmed, decisions=decisions, step="decide")
    b = _buttons(a)[0]
    assert b["tool"] == "review_plan" and b["arguments"]["decisions"] == decisions and b["arguments"]["confirmed"] == confirmed
    after = a["after"]["arguments"]
    assert after["plan"] == {"keys": keys, "confirmed": confirmed, "decisions": decisions} and after["step"] == "totals"
    again = json.loads(server.start(**after))                     # the tool unpacks plan into the same choices
    assert _buttons(again)[0]["arguments"] == {**CHOSEN, "keys": keys, "confirmed": confirmed, "fixes": True}


def test_a_step_cannot_be_skipped_before_its_choice():
    assert sf.guide(step="check")["step"]["key"] == "workspace"
    assert sf.guide(workspace="ws", step="create")["step"]["key"] == "source"
    assert sf.guide(workspace="ws", source="lh", step="totals")["step"]["key"] == "schema"


def test_each_step_says_whether_it_reads_or_writes():
    for s in _walk():
        assert all(p["does"] == ("writes" if p["key"] == "create" else "reads") for p in s["path"])
        assert "Only step 9 writes" in s["honest"] and "no row values" in s["honest"]
    assert not any(b["tool"] == "sample_rows" for s in _walk() for b in _buttons(s))


def test_the_dry_run_names_every_build_and_the_data_flow():
    a = sf.guide(**CHOSEN, step="dry_run")
    assert {w["tool"] for w in a["would_build"]} == WRITERS
    assert {b["tool"] for b in _buttons(a)} == WRITERS - {"create_report"}           # the report waits for its model
    assert all(b["kind"] == "dry_run" and "dry_run" not in b["arguments"] for b in _buttons(a))
    assert any("silver" in f and "gold" in f and "check" in f for f in a["data_flow"])


@pytest.mark.parametrize("create, confirm", [(None, True), (["shop_model"], False), (["not_in_the_dry_run"], True),
                                             (["shop_model", "someone_elses_table"], True)])
def test_writes_need_the_dry_runs_names_and_a_second_confirmation(create, confirm):
    a = sf.guide(**CHOSEN, step="create", create=create, confirm=confirm)
    assert a["needs_confirmation"] is True
    assert not any(b["arguments"].get("dry_run") is False for b in _buttons(a))
    assert "confirm" in a["say"]


def test_confirmed_names_are_created_and_nothing_else():
    a = sf.guide(**CHOSEN, step="create", create=["shop_model", "shop_report", "shop_api"], confirm=True)
    writes = [b for b in _buttons(a) if b["arguments"].get("dry_run") is False]
    assert [b["arguments"]["name"] for b in writes] == ["shop_model", "shop_api"]
    report = [b for b in _buttons(a) if b["tool"] == "create_report"]
    assert report and report[0]["kind"] == "dry_run" and "dry_run" not in report[0]["arguments"]   # its own dry run first
    for b in _buttons(a):
        _accepts(b["tool"], b["arguments"])


def test_the_synthetic_shop_runs_the_same_path_without_fabric():
    a = json.loads(server.start(sample=True))
    assert a["sample"] is True and a["step"]["key"] == "map" and "links" in a["found"]
    keys = []
    while True:
        keys.append(a["step"]["key"])
        if "after" not in a:
            break
        assert a["after"]["arguments"]["sample"] is True
        a = json.loads(server.start(**a["after"]["arguments"]))
    assert keys == ["map", "check", "decide", "totals", "dry_run", "create"]
    totals = sf.guide(sample=True, step="totals")["found"]["doubled"]
    assert totals and "summed over the joined" in totals[0]
    assert "nothing can be created" in sf.guide(sample=True, step="create")["found"]["note"]
    first = sf.guide()
    assert any(b.get("arguments") == {"sample": True} and "synthetic shop" in b["label"] for b in first["actions"])
