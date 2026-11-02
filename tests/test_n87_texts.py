"""n87, point 8: no tool answer contradicts itself or the record. Every hosted tool is called as in the golden run
(Fabric answered from memory, an SQL endpoint backed by SQLite) and its text is checked for what the live review of
2 November 2026 found: a compare that read the model saying the workspace has no model, creating tools saying they
never ran live while the workspace holds what they made (docs/LIVE-TEST.md is the record), an inactive relationship
the draft does not have, "tested end to end" next to "has not run", introspection "off" from a tool that never probed
it, rules R0-R4 now that R5 exists, a permission described as not granted that is, a reference "could not be fetched",
and notes that name the maintainer or a client."""
import json
import re

import pytest

from fabric_backend import server
from tests.test_golden import HOSTED_CALLS, SRC, fabric  # noqa: F401  (fabric: fixture)


@pytest.fixture
def answers(fabric):
    out = {}
    for name, kwargs in HOSTED_CALLS:
        out.setdefault(name, []).append(getattr(server, name)(**kwargs))
    return out


def _notes(value, key=""):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _notes(v, k)
    elif isinstance(value, list):
        for v in value:
            yield from _notes(v, key)
    elif isinstance(value, str) and ("note" in key or key in ("after_creation", "run")):
        yield value


def test_no_answer_names_the_maintainer_and_no_note_names_a_client(answers):
    for name, texts in answers.items():
        for text in texts:
            assert "Gustav" not in text, name
            try:
                body = json.loads(text)
            except ValueError:
                continue
            for note in _notes(body):
                assert "Lovable" not in note, (name, note)


def test_rules_are_named_up_to_r5(answers):
    for name in ("ontology_draft", "silver_notebook_draft", "drift_monitor_draft", "create_ontology", "create_silver_notebook",
                 "create_drift_monitor", "export_item_definitions"):
        for text in answers[name]:
            assert not re.search(r"R0\s*[-–]\s*R4", text), name
    assert not re.search(r"R0\s*[-–]\s*R4", server.mcp.instructions)


def test_compare_after_reading_the_model_does_not_say_there_is_none(answers):
    for text in answers["compare_semantic_model"]:
        assert "has no model" not in text and "no model in the demo workspace" not in text


def test_creating_tools_say_what_the_record_shows(answers):
    for name in ("create_views", "create_data_agent"):
        for text in answers[name]:
            assert "creating has not run against a live workspace" not in text, name
            assert "docs/LIVE-TEST.md" in text, name
    assert any("krusgraph.vw_order_items" in t for t in answers["create_views"])


def test_the_semantic_model_note_does_not_count_an_inactive_relationship_the_draft_lacks(answers):
    for text in answers["create_semantic_model"]:
        body = json.loads(text)
        m = re.search(r"(\d+) active, (\d+) inactive", json.dumps(body.get("summary", "")) + json.dumps(body.get("parts", {})))
        inactive = int(m.group(2)) if m else 0
        note = body["note"]
        claimed = re.findall(r"(\d+) inactive", note)
        assert not claimed or all(int(c) == inactive for c in claimed), note


def test_tested_end_to_end_and_has_not_run_are_not_side_by_side(answers):
    for name, texts in answers.items():
        for text in texts:
            for note in _notes(json.loads(text)) if text.startswith("{") else []:
                assert not ("has not run in a Fabric workspace" in note and "Tested end to end" in note), (name, note)


def test_app_starter_does_not_say_introspection_is_off(answers):
    for text in answers["app_starter"]:
        assert not json.loads(text)["connection"]["introspection"].startswith("off")
        assert "app_readiness" in json.loads(text)["connection"]["introspection"]


def test_the_ontology_note_says_the_permission_is_granted(answers):
    note = json.loads(answers["ontology_draft"][0])["note"]
    assert "only when its operator enables" not in note and "28 October 2026" in note


def test_no_reference_that_could_not_be_fetched(answers):
    for name, texts in answers.items():
        for text in texts:
            assert "could not be fetched" not in text, name
