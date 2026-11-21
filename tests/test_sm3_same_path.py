"""SM3 (docs/SMOOTH/PLAN.md row 2): the same path in the Fabric editor as in the chat.

One test reads both surfaces: the Start Krusgraph card (fabric_backend/start_flow.py) and the Model editor
(workload/Workload/app/items/ModelItem/stepWords.ts). They name the same five steps, in the same words and order, and the
same default build: the pipeline (with its silver and gold notebooks), the semantic model and the data agent. The
editor's e2e harness (workload/scripts/e2e/run.js, flow 26) clicks the lazy path and fails above 4 clicks.
"""
from __future__ import annotations

import re
from pathlib import Path

from fabric_backend import start_flow

ROOT = Path(__file__).resolve().parents[1]
ITEM = ROOT / "workload" / "Workload" / "app" / "items" / "ModelItem"

# the editor's output kinds and the chat's create tools they stand for
KIND_TOOL = {"pipeline": "create_pipeline", "semantic_model": "create_semantic_model", "data_agent": "create_data_agent"}


def _ts_list(src: str, name: str) -> list[str]:
    m = re.search(rf"export const {name} = \[([^\]]*)\]", src)
    assert m, f"{name} not found in stepWords.ts"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_the_chat_and_the_editor_name_the_same_five_steps():
    steps = (ITEM / "stepWords.ts").read_text()
    editor = _ts_list(steps, "STEP_WORDS")
    chat = [start_flow.SHORT[k] for k in start_flow.KEYS]
    assert editor == chat == ["Your data", "Check", "Decide", "Dry run", "Create"]
    # every label in the editor's step order is one of the five words, used once
    labels = re.findall(r"label: STEP_WORDS\[(\d)\]", steps)
    assert sorted(int(i) for i in labels) == [0, 1, 2, 3, 4]


def test_the_chat_and_the_editor_name_the_same_default_outputs():
    steps = (ITEM / "stepWords.ts").read_text()
    editor = _ts_list(steps, "DEFAULT_BUILD")
    assert [KIND_TOOL[k] for k in editor] == list(start_flow.SUGGESTED)
    # the chat's pipeline is silver and gold notebooks and the pipeline that runs them; the editor ticks them together
    assert _ts_list(steps, "PIPELINE_PARTS") == ["silver_notebook", "gold_views"]
    words = (ITEM / "buildWords.ts").read_text()
    assert "STARTS_ON: string[] = [...PIPELINE_PARTS, ...DEFAULT_BUILD]" in words
    assert 'k.kind === "graphql" && saved.length === 0' not in words          # the API for GraphQL is not preticked


def test_one_accept_all_and_no_request_to_copy_for_claude():
    views = (ITEM / "ModelItemViews.tsx").read_text()
    assert "Accept all that passed the check ({passed})" in views
    assert "Accept all ({all})" not in views
    nxt = (ITEM / "nextSteps.ts").read_text()
    assert 'label: "Copy the request for Claude"' not in nxt
    assert "Ask Krusgraph in Claude for app_readiness" not in nxt


def test_choose_shows_the_three_defaults_and_folds_the_other_six():
    views = (ITEM / "ModelItemViews.tsx").read_text()
    assert "{main.map(card)}" in views and "{more.map(card)}" in views
    assert '<summary>More outputs{moreTicked ? ` (${moreTicked} ticked)` : ""}</summary>' in views
    kinds = re.findall(r'\{ kind: "([a-z_]+)", label:', (ITEM / "buildWords.ts").read_text())
    assert len(kinds) == 9 and len([k for k in kinds if k not in KIND_TOOL]) == 6


def test_the_check_runs_on_its_own_after_find_keys():
    editor = (ITEM / "ModelItemEditor.tsx").read_text()
    assert "onReview={() => plan(def, {}, true)}" in editor
    assert "if (check && a.review) await checkRows(next);" in editor


def test_the_editor_e2e_counts_the_lazy_path_and_fails_above_four_clicks():
    run = (ROOT / "workload" / "scripts" / "e2e" / "run.js").read_text()
    assert "26 SM3: open to the dry run of pipeline + model + agent" in run
    assert 'expectTrue(clicks <= 4, `${clicks} clicks, more than 4`)' in run
    assert '["390 px", { width: 390, height: 844 }]' in run
