"""DIR1 (20 November 2026): the hosted server against the Claude connector directory's review criteria.

Source: claude.com/docs/connectors/building/review-criteria and /submission (read 20 Nov 2026). What is checked here:

1. every tool has a title (also in annotations.title), readOnlyHint true for a tool that only reads and destructiveHint
   true for a tool that creates or changes something in Fabric, and a name of at most 64 characters;
2. no tool description, parameter description, prompt description or the server's instructions instruct the model to
   call a tool ("run <tool>", "call <tool>", "use the <tool> tool") or tell it how to reply (directory.DIRECTIVE);
3. no tool answer does either, in its text or its structuredContent, on the SAP demo and the 33-table
   WideWorldImporters schema (tools/directory_measure.py, a fake Fabric that refuses every write);
4. every tool answers successfully for valid input there, or with a specific error (kind and hint, never "unexpected");
5. the text a model reads stays under TEXT_MAX characters and the whole result under TOTAL_MAX bytes.
docs/DIRECTORY-READINESS.md has the table per tool and the sizes before and after.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from fabric_backend import directory, server

WRITE_TOOLS = {"create_backend", "create_ontology", "create_semantic_model", "create_report", "create_views",
               "create_data_agent", "create_silver_notebook", "create_gold_views", "create_drift_monitor",
               "create_pipeline", "publish_catalog"}
TEXT_MAX = 48_000          # characters of the text contents a model reads (the JSON is folded at directory.ANSWER_MAX)
TOTAL_MAX = 140_000        # bytes of the whole result: text contents plus the card's structuredContent (card data, not model text)


def _tools():
    return asyncio.run(server.mcp.list_tools())


def test_every_tool_has_a_title_and_the_right_annotations():
    tools = _tools()
    assert len(tools) >= 48
    for t in tools:
        a = t.annotations
        assert t.title and a is not None and a.title == t.title, t.name
        assert len(t.name) <= 64, t.name
        if t.name in WRITE_TOOLS:
            assert a.read_only_hint is False and a.destructive_hint is True, t.name
        else:
            assert a.read_only_hint is True and a.destructive_hint is False, t.name
    assert WRITE_TOOLS <= {t.name for t in tools}


def test_the_read_and_write_tools_are_separate():
    """No catch-all tool: no `method` parameter, and every creating tool is its own tool with a dry run by default."""
    for t in _tools():
        props = (t.input_schema or {}).get("properties", {})
        assert "method" not in props, t.name
        if t.name in WRITE_TOOLS and "dry_run" in props:
            assert props["dry_run"].get("default") is True, t.name


def _descriptions():
    for t in _tools():
        yield f"tool {t.name}", t.description or ""
        for p, spec in ((t.input_schema or {}).get("properties") or {}).items():
            yield f"{t.name}.{p}", json.dumps(spec)
    yield "instructions", server.mcp.instructions or ""
    for p in asyncio.run(server.mcp.list_prompts()):
        yield f"prompt {p.name}", (p.description or "") + " " + json.dumps([a.model_dump() for a in p.arguments or []])


def test_no_description_or_instruction_tells_the_model_to_call_a_tool():
    found = [(where, m.group(0)) for where, text in _descriptions()
             for m in list(directory.IMPERATIVE.finditer(text)) + list(directory.DIRECTIVE.finditer(text))]
    assert not found, found


@pytest.mark.parametrize("phrase", [
    "run validate_plan with workspace=\"demo\"", "Run create_data_agent with name=x", "call start with sample=true",
    "use the create_views tool", "Offer one next step: x", "For the assistant, not for the user: y",
    "Say in one short sentence, in plain words: z", "rerun create_backend"])
def test_the_pattern_finds_the_old_phrases(phrase):
    assert directory.IMPERATIVE.search(phrase) or directory.DIRECTIVE.search(phrase)


@pytest.mark.parametrize("phrase", [
    "Possible next step for the user: Check against the rows (validate_plan(workspace=\"demo\")).",
    "create_backend does not run `validate_plan`", "Run create_silver_notebook's notebook first",
    "Words: \"run a check\" means validate_plan", "list_tables with another schema shows its tables"])
def test_the_pattern_leaves_descriptions_alone(phrase):
    assert not directory.IMPERATIVE.search(phrase) and not directory.DIRECTIVE.search(phrase)


def test_neutral_says_an_instruction_as_an_option():
    assert directory.neutral("Verify it: run verify_build with items=x.") == "Verify it: verify_build with items=x."
    assert directory.neutral("use the create_views tool for views") == "the create_views tool for views"
    assert directory.neutral("nothing to change here") == "nothing to change here"


def test_fold_keeps_a_small_answer_and_bounds_a_large_one():
    small = {"summary": "ok", "files": {"a.sql": "select 1"}}
    assert directory.fold(small) is small
    big = {"summary": "3 views", "files": {f"v{i}.sql": "x" * 30_000 for i in range(3)},
           "rows": [{"n": i, "label": "y" * 50} for i in range(2_000)]}
    out = directory.fold(big)
    assert len(json.dumps(out, indent=2)) <= directory.ANSWER_MAX + 2_000
    assert out["summary"] == "3 views" and out["folded"]["texts"] and out["folded"]["lists"]
    assert "shortened by Krusgraph" in out["files"]["v0.sql"]
    assert len(out["rows"]) == directory.LIST_KEEP
    assert "fewer `tables`" in out["folded"]["note"]


def _strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x)
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)


@pytest.mark.parametrize("data", ["sap", "wwi"])
def test_every_tool_answers_neutrally_successfully_and_bounded(data):
    from tools import directory_measure as dm
    seen, problems = set(), []
    with dm.fake_fabric(data) as schema:
        for name, args in dm.calls(schema, data):
            seen.add(name)
            r = dm.run(name, args)
            texts = list(r["texts"])
            for t in texts + list(_strings(r["structured"])):
                for m in list(directory.IMPERATIVE.finditer(t)) + list(directory.DIRECTIVE.finditer(t)):
                    problems.append((name, "instructs", m.group(0)))
            if r["error"]:
                answer = json.loads(texts[-1])
                if r["kind"] in (None, "unexpected") or not answer.get("hint"):
                    problems.append((name, "generic error", r["error"]))
                elif name not in dm.NEEDS_ITEM and (data, name) not in dm.REFUSED:
                    problems.append((name, "failed on valid input", r["kind"], r["error"]))
            if sum(len(t) for t in texts) > TEXT_MAX:
                problems.append((name, "text too large", sum(len(t) for t in texts)))
            if r["bytes"] > TOTAL_MAX:
                problems.append((name, "result too large", r["bytes"]))
    assert seen == {t.name for t in _tools()}, sorted({t.name for t in _tools()} - seen)
    assert not problems, problems


def test_the_review_of_a_large_schema_is_split_not_refused():
    from tools import directory_measure as dm
    with dm.fake_fabric("wwi"):
        out = json.loads(server.review_plan(workspace="demo", source="demo_lh", schema="dbo"))
    assert "error" not in out
    groups = out["split"]["groups"]
    assert sum(len(g["tables"]) for g in groups) == out["split"]["tables"] == 33
    assert all(len(g["tables"]) <= 10 for g in groups)


def test_a_wrong_detail_is_a_clear_error():
    from tools import directory_measure as dm
    with dm.fake_fabric("sap"):
        out = json.loads(server.plan_backend(workspace="demo", source="demo_lh", schema="dbo", detail=True))
    assert out["kind"] != "unexpected" and "detail" in out["error"]


def test_the_cards_link_only_to_krusgraph():
    """Allowed link URIs (ui/open-link): the cards open only https://krusgraph.com pages and Fabric item pages; the
    listing declares https://krusgraph.com (an origin Kruse Consulting AB owns). Fabric's own origin is not ours to list,
    so opening it asks the user to confirm, as the documentation says."""
    import re

    from fabric_backend import mcp_apps, mcp_apps_build, mcp_apps_review, mcp_apps_start
    html = mcp_apps.card_html() + mcp_apps_review.card_html() + mcp_apps_build.card_html() + mcp_apps_start.card_html()
    literal = set(re.findall(r"https://[a-z0-9.-]+", html))
    assert literal <= {"https://krusgraph.com", "https://app.fabric.microsoft.com", "https://www.w3.org"}, literal
