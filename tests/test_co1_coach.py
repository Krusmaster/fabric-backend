"""CO1: the coach (fabric_backend/coach.py), after Gustav's phone test of 19 November 2026: one guided path with named
stages, said the way the home page's demo chat says it.

- The stage rules: every plan state gives exactly one primary next step, never the call just made (unless it failed),
  and never no step; at most two secondary steps; "Step N of 8".
- The Coach block in every tool result's text: short, stable (golden files under tests/golden/coach/), no rule codes.
- The words shared with the demo chat appear word for word in static/chat-demo.js (one source for both).
- Two cards in Chromium at 390 px, light and dark: the stage line and one mascot line under the title, one primary
  button and at most two others, nothing technical on the first view, Mascots: off hides the figure and keeps the words.

Everything runs on synthetic data: the shop of fabric_backend/seed.py through tests/golden_support's fake Fabric.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from fabric_backend import coach, mcp_apps, mcp_apps_start, server, start_flow
from test_golden import SRC, fabric  # noqa: F401  (the hosted server against the synthetic shop workspace)

TESTS = Path(__file__).resolve().parent
GOLDEN = TESTS / "golden" / "coach"
UPDATE = os.environ.get("KRUSGRAPH_UPDATE_GOLDEN") == "1"
DEMO_JS = Path(coach.__file__).with_name("static") / "chat-demo.js"
B = {"workspace": "demo", "source": "demo_lh", "schema": "sap_silver"}
CLEAN = {"totals": {"keys": {"checked": 6, "passed": 6, "failed": 0},
                    "relationships": {"checked": 7, "passed": 7, "failed": 0},
                    "amount_levels": {"checked": 0, "passed": 0, "failed": 0}}}
BAD_KEY = {"totals": {"keys": {"checked": 6, "passed": 5, "failed": 1}},
           "attention": {"keys": [{"table": "VBAP"}]}}
ORPHANS = {"totals": {"keys": {"checked": 6, "passed": 6, "failed": 0}},
           "attention": {"relationships": [{"source": "VBAP", "columns": ["MATNR"], "target": "MARA", "orphans": 3}]}}
JARGON = re.compile(r"\b[RK][0-9]\b|\bTTL\b|_key\b|@prefix")

# (name, tool, call, answer): the plan states of the path, from nothing chosen to done
STATES = [
    ("nothing", "list_workspaces", {}, {"workspaces": [{"name": "demo"}]}),
    ("workspace", "list_sources", {"workspace": "demo"}, {"sources": []}),
    ("source", "list_tables", {"workspace": "demo", "source": "demo_lh"}, {"tables": []}),
    ("schema", "list_tables", B, {"tables": []}),
    ("read", "plan_backend", B, {"summary": "17 tables"}),
    ("ontology_draft", "ontology_draft", B, {"summary": "an ontology"}),
    ("checked_clean", "validate_plan", B, CLEAN),
    ("checked_bad_key", "validate_plan", B, BAD_KEY),
    ("fixes_asked", "validate_plan", {**B, "fixes": True}, BAD_KEY),
    ("orphans", "validate_plan", B, ORPHANS),
    ("gold_draft", "gold_views_draft", B, {"sql": "select 1"}),
    ("pipeline_dry", "create_pipeline", {**B, "name": "sap_silver_pipeline", "dry_run": True}, {"would_create": []}),
    ("pipeline_made", "create_pipeline", {**B, "name": "sap_silver_pipeline", "dry_run": False}, {"created": []}),
    ("model_draft", "semantic_model_draft", B, {"tmdl": "model Model"}),
    ("model_dry", "create_semantic_model", {**B, "name": "sap_silver_model", "dry_run": True}, {"would_create": []}),
    ("model_made", "create_semantic_model", {**B, "name": "sap_silver_model", "dry_run": False}, {"created": []}),
    ("agent_dry", "create_data_agent", {**B, "name": "sap_silver_agent", "dry_run": True}, {"would_create": []}),
    ("agent_made", "create_data_agent", {**B, "name": "sap_silver_agent", "dry_run": False}, {"created": []}),
    ("error", "validate_plan", B, {"error": "The SQL endpoint did not answer.", "kind": "timeout"}),
    ("start_first", "start", {}, start_flow.guide()),
    ("start_map", "start", B, start_flow.guide(**B)),
    ("start_check", "start", {**B, "step": "check"}, start_flow.guide(**B, step="check")),
    ("start_dry_run", "start", {**B, "step": "dry_run"}, start_flow.guide(**B, step="dry_run")),
]
EXPECT = {                                     # name: (step n of the start path's 9, the primary step's label); WB15: one numbering
    "nothing": (1, "Choose a workspace"), "workspace": (2, "Choose the lakehouse"), "source": (3, "Choose the schema"),
    "schema": (3, "Read the tables"), "read": (4, "Check against the rows"), "ontology_draft": (4, "Check against the rows"),
    "checked_clean": (8, "Build silver and gold (dry run first)"), "checked_bad_key": (6, "Propose a fix per failure"),
    "fixes_asked": (6, "Decide the open links"), "orphans": (6, "Show what points at nothing"),
    "gold_draft": (8, "Build silver and gold (dry run first)"), "pipeline_dry": (8, "Build silver and gold in Fabric"),
    "pipeline_made": (8, "Create the semantic model (dry run first)"),
    "model_draft": (8, "Create the semantic model (dry run first)"), "model_dry": (8, "Create the semantic model in Fabric"),
    "model_made": (8, "Create the data agent (dry run first)"), "agent_dry": (8, "Create the data agent in Fabric"),
    "agent_made": (9, "Start again on another schema"), "error": (5, "Show where we are"),
    "start_first": (1, "List my workspaces"), "start_map": (4, "Show the map"), "start_check": (5, "Check against the rows"),
}
# SM2: the start path has five steps; the stages of the nine steps before it map onto them (coach.STAGE_STEP)
NINE_TO_FIVE = {1: 1, 2: 1, 3: 1, 4: 2, 5: 2, 6: 3, 7: 2, 8: 4, 9: 5}
EXPECT = {k: (NINE_TO_FIVE[n], label) for k, (n, label) in EXPECT.items()}
EXPECT["start_map"] = (1, "Next: Check")              # all chosen: "demo › demo_lh › dbo ✓" and Next


@pytest.mark.parametrize("name,tool,call,answer", STATES, ids=[s[0] for s in STATES])
def test_each_plan_state_has_exactly_one_primary_step_that_is_new(name, tool, call, answer):
    c = coach.coach(tool, call, answer)
    assert 1 <= c["n"] <= c["of"] == 5                            # SM2: the start path's five steps everywhere
    if tool == "start":
        assert c["title"] == start_flow.SHORT[answer["step"]["key"]]
    else:
        assert c["title"] in [x[1] for x in coach.STAGES]
    p = c["primary"]
    assert p.get("primary") is True and p["label"] and p["say"] and p["ask"]           # never no step
    assert len(c["secondary"]) <= 2 and not any(s.get("primary") for s in c["secondary"])
    assert p["label"] not in [s["label"] for s in c["secondary"]]
    steps = coach.next_steps(c)
    assert sum(1 for s in steps if s.get("primary")) == 1 and len(steps) <= 3
    raw = coach.plan(tool, call, answer)
    if not answer.get("error"):                                   # never the call just made, unless it failed
        assert not coach._is_same(tool, {k: v for k, v in call.items()}, raw["primary"]), name
    if name in EXPECT:
        assert (c["n"], p["label"]) == EXPECT[name], (name, c["n"], p["label"])
    assert c["line"] and not JARGON.search(c["line"]) and len(c["line"]) < 160          # one plain sentence or two


def test_a_creating_step_waits_for_the_users_yes():
    c = coach.coach("create_pipeline", {**B, "name": "sap_silver_pipeline", "dry_run": True}, {"would_create": []})
    assert c["writes"] and "the user's yes to the names" in c["text"]
    assert "tool" not in c["primary"]                              # a card never runs a creating call by itself
    assert '"dry_run": false' not in json.dumps(c["primary"]) or "tool" not in c["primary"]
    clean = coach.coach("validate_plan", B, CLEAN)
    assert not clean["writes"] and clean["primary"]["say"].endswith("dry_run=True).")


def test_a_step_for_the_chat_still_names_its_call():
    from fabric_backend import next_rules
    step = next_rules._decide(dict(B), 2, B)                       # a sentence that starts the start card's step 6
    c = coach.coach("validate_plan", B, BAD_KEY, steps=[step])
    assert c["primary"]["label"] == "Decide the 2 open links" and "tool" not in c["primary"]
    assert 'Possible next step for the user: Decide the 2 open links (start(workspace="demo"' in c["text"] and 'step="decide"' in c["text"]


def test_the_same_state_gives_the_same_coach():
    for name, tool, call, answer in STATES:
        assert coach.coach(tool, call, answer) == coach.coach(tool, json.loads(json.dumps(call)), json.loads(json.dumps(answer)))


@pytest.mark.parametrize("name,tool,call,answer", STATES, ids=[s[0] for s in STATES])
def test_the_coach_block_is_short_stable_and_plain(name, tool, call, answer):
    text = coach.coach(tool, call, answer)["text"]
    assert len(text) <= coach.TEXT_MAX and text.startswith("Coach (step ")
    assert "Possible next step for the user: " in text and text.count("\n") <= 5
    said = text.split("\n")[1]
    assert not JARGON.search(said)
    path = GOLDEN / f"{name}.txt"
    if UPDATE:
        GOLDEN.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    assert path.exists(), f"no golden file {path.name}: run with KRUSGRAPH_UPDATE_GOLDEN=1 once"
    assert text + "\n" == path.read_text(encoding="utf-8")


def test_the_demo_chats_words_are_the_products_words():
    js = DEMO_JS.read_text(encoding="utf-8")
    for key, words in coach.DEMO.items():
        assert words in js, f"coach.DEMO[{key!r}] is no longer said in chat-demo.js: change both together"
    for key, words in coach.DEMO.items():
        if key != "next":
            assert any(words in line for line in coach.LINE.values()), key


def test_mascots_are_the_sites():
    from fabric_backend import mcp_apps_mascots as m
    assert {s[2] for s in coach.STAGES} <= set(m.KINDS) and set(coach.NAMES.values()) <= set(m.NAMES.values())
    assert {s[3] for s in coach.STAGES} <= set(m.POSES)


# ------------------------------------------------------------------ in the hosted server's results --------------------

def _sc(tool, /, **kw):
    return mcp_apps.structured(getattr(server, tool), tool)(**kw)


@pytest.mark.parametrize("tool,args", [("list_workspaces", {}), ("list_sources", {"workspace": "demo"}),
                                       ("plan_backend", SRC), ("validate_plan", SRC), ("review_plan", {**SRC, "validate": True}),
                                       ("semantic_model_draft", SRC), ("start", {}), ("start", SRC)])
def test_every_result_carries_the_coach_and_keeps_its_json_last(fabric, tool, args):
    r = _sc(tool, **args)
    texts = [c.text for c in r.content]
    assert json.loads(texts[-1])                                   # the JSON answer, last and unchanged in shape
    lead = "\n\n".join(texts[:-1])
    assert lead.count("Coach (step ") == 1 and " = ." not in lead and "Possible next step for the user: " in lead
    d = r.structured_content
    assert set(d["coach"]) == {"n", "of", "stage", "title", "who", "name", "pose", "line"}
    if tool != "start" and "next" in d:
        assert len(d["next"]) <= 3 and sum(1 for s in d["next"] if s.get("primary")) <= 1


def test_a_plain_sentence_starts_the_path(fabric):
    assert "'help me with my SAP data in Fabric'" in server.mcp.instructions
    assert "Coach block" in server.mcp.instructions
    r = _sc("start")
    d = r.structured_content
    # SM2: the one workspace is chosen for you; its two sources are the choice, still step 1, "Your data"
    assert d["step"]["key"] == "data" and d["stage"] == "source" and d["coach"]["n"] == 1 and d["coach"]["title"] == "Your data"
    choices = [a for a in d["actions"] if a.get("kind") == "choose"]
    assert choices and all(a["arguments"].get("workspace") for a in choices)   # clickable workspaces, nothing else asked


# ------------------------------------------------------------------ two cards at 390 px --------------------------------

needs_browser = pytest.mark.skipif(not shutil.which("node") or subprocess.run(["node", "-e", "require('playwright')"],
                                                                              capture_output=True).returncode != 0,
                                   reason="node + playwright not available")


def _browse(tmp_path, html: str, data: dict) -> dict:
    (tmp_path / "card.html").write_text(html, encoding="utf-8")
    (tmp_path / "data.json").write_text(json.dumps(data), encoding="utf-8")
    run = subprocess.run(["node", str(TESTS / "co1_card_browser.js"), str(tmp_path / "card.html"), str(tmp_path / "data.json")],
                         capture_output=True, text=True, timeout=180)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout)
    assert out["errors"] == [], out["errors"]
    return out


def _result(r) -> dict:
    return {"content": [{"type": "text", "text": c.text} for c in r.content], "structuredContent": r.structured_content}


def _first_view(out, c):
    assert out["stage"] == f"Step {c['n']} of 5: {c['title']}" and out["line"] == c["line"] and out["who"] == c["name"]
    assert out["firstAfterHead"] and out["lineShown"] and out["figure"] and out["oldFigures"] == 0
    assert not out["figureAfterToggle"] and out["lineAfterToggle"]                     # Mascots: off keeps the words
    assert not out["overflow"]
    assert out["background"] != out["ink"]


@needs_browser
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_the_check_card_coaches_at_390(fabric, tmp_path, scheme):
    r = _sc("validate_plan", **SRC)
    d = r.structured_content
    out = _browse(tmp_path, mcp_apps.card_html(), {"result": _result(r), "args": SRC, "scheme": scheme, "width": 390})
    _first_view(out, d["coach"])
    nexts = [s["label"] for s in d["next"]]
    assert [b for b in out["buttons"] if b in nexts] == nexts and len(nexts) <= 3
    assert out["primary"] == [nexts[0]]
    assert not re.search(r"\bR[0-9]\b|_key\b", out["visible"]), out["visible"]            # the rule codes under Details
    assert "Details: every key and link" in out["visible"]


@needs_browser
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_the_start_card_coaches_at_390(fabric, tmp_path, scheme):
    # WB15: the start card draws its own coach (the mascot on top, one sentence) under "Step N of 5: <step>"; the rest of
    # it, and the click-through, is tests/test_wb15_click_through.py
    r = _sc("start")
    (tmp_path / "card.html").write_text(mcp_apps_start.card_html(), encoding="utf-8")
    (tmp_path / "data.json").write_text(json.dumps({"result": _result(r), "scheme": scheme, "width": 390, "frame": 900}), encoding="utf-8")
    run = subprocess.run(["node", str(TESTS / "wb13_card_browser.js"), str(tmp_path / "card.html"), str(tmp_path / "data.json")],
                         capture_output=True, text=True, timeout=180)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout)
    assert out["errors"] == [] and not out["overflow"]
    assert out["text"].startswith("Step 1 of 5: Your data") and "Onto" in out["text"]
    assert any("demo" in b["text"] for b in out["buttons"])                                # the workspace as a click
    assert "Details" in out["text"] and "The map: keys and links" not in out["text"]
