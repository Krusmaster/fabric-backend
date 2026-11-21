"""SM4 (fewer doors, docs/SMOOTH/PLAN.md row 3): about 15 tools listed by default, every tool still answering by name,
KRUSGRAPH_ADVANCED_TOOLS=1 for the full listing, and no card that leads nowhere."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from fabric_backend import directory, mcp_apps_next, server, tool_listing

ROOT = Path(__file__).resolve().parent.parent
HIDDEN = {  # the tools that leave the default listing (docs/DIRECTORY-READINESS.md, "SM4")
    "list_workspaces", "list_sources", "list_tables", "sample_rows", "analyze_schema", "suggest_relationships",
    "join_path", "data_dictionary", "dbt_schema", "domain_draft", "sap_pack_draft", "rayfin_connector",
    "compare_semantic_model", "plan_drift", "semantic_model_draft", "ontology_draft", "silver_notebook_draft",
    "gold_views_draft", "drift_monitor_draft", "export_item_definitions", "create_silver_notebook", "create_gold_views",
    "create_views", "create_drift_monitor", "analysis_plan", "analysis_notebook_draft", "app_starter", "app_readiness",
    "answer_query_draft", "qlik_plan", "qlik_measures_draft", "qlik_reconcile_draft"}


def _names(monkeypatch, advanced: bool) -> list[str]:
    if advanced:
        monkeypatch.setenv(tool_listing.ADVANCED, "1")
    else:
        monkeypatch.delenv(tool_listing.ADVANCED, raising=False)
    return [t.name for t in asyncio.run(server.mcp.list_tools())]


def test_the_default_listing_has_at_most_16_tools_and_the_switch_lists_all_48(monkeypatch):
    default, every = _names(monkeypatch, False), _names(monkeypatch, True)
    assert len(default) <= 16 and set(default) == set(tool_listing.DEFAULT)
    assert len(every) == 48 and set(default) < set(every)
    assert set(every) - set(default) == HIDDEN


def test_the_plan_s_tools_and_the_newer_ones_are_placed_on_purpose(monkeypatch):
    default = set(_names(monkeypatch, False))
    for name in ("start", "plan_backend", "validate_plan", "review_plan", "create_pipeline", "create_semantic_model",
                 "create_data_agent", "create_report", "create_backend", "create_ontology", "publish_catalog",
                 "requirements_draft", "verify_build", "lineage", "query_graphql", "describe_backend"):
        assert name in default, name
    for name in ("list_workspaces", "list_sources", "list_tables", "analyze_schema", "suggest_relationships",
                 "join_path", "semantic_model_draft", "ontology_draft", "silver_notebook_draft", "gold_views_draft",
                 "drift_monitor_draft", "export_item_definitions", "create_silver_notebook", "create_gold_views",
                 "create_views"):
        assert name not in default, name


def test_every_listed_tool_keeps_its_title_and_hints(monkeypatch):
    monkeypatch.delenv(tool_listing.ADVANCED, raising=False)
    for t in asyncio.run(server.mcp.list_tools()):
        a = t.annotations
        assert t.title and a.title == t.title, t.name
        assert (a.read_only_hint, a.destructive_hint) in ((True, False), (False, True)), t.name


def test_a_hidden_tool_still_answers_when_called_by_name(monkeypatch):
    monkeypatch.delenv(tool_listing.ADVANCED, raising=False)
    assert "qlik_measures_draft" not in _names(monkeypatch, False)
    out = asyncio.run(server.mcp.call_tool("qlik_measures_draft",
                                           {"measures": [{"name": "Sales", "expression": "Sum(Sales)"}]}))
    text = json.dumps(out, default=str)
    assert "Sales" in text and "Unknown tool" not in text


def test_the_instructions_say_what_is_listed_as_facts():
    text = server.mcp.instructions
    assert "KRUSGRAPH_ADVANCED_TOOLS=1" in text and "answer when called by name" in text
    assert not directory.IMPERATIVE.search(tool_listing.sentence()) and not directory.DIRECTIVE.search(tool_listing.sentence())


def test_a_draft_step_becomes_its_create_tool_s_dry_run(monkeypatch):
    monkeypatch.delenv(tool_listing.ADVANCED, raising=False)
    s = {"label": "Draft the gold views", "tool": "gold_views_draft",
         "arguments": {"workspace": "demo", "source": "demo_lh", "schema": "dbo"}}
    out = tool_listing.default_step(s)
    assert out["tool"] == "create_pipeline" and out["arguments"]["dry_run"] is True and out["arguments"]["name"]
    assert tool_listing.default_step({"label": "x", "tool": "join_path", "arguments": {}}) is None
    monkeypatch.setenv(tool_listing.ADVANCED, "1")
    assert tool_listing.default_step(s) == s


@pytest.mark.parametrize("tool,call,step", [
    ("lineage", {"workspace": "w", "source": "s", "schema": "dbo"}, "check"),
    ("validate_plan", {"workspace": "w", "source": "s"}, "decide"),
    ("create_pipeline", {"workspace": "w", "source": "s", "dry_run": True}, "dry_run"),
    ("create_pipeline", {"workspace": "w", "source": "s", "dry_run": False}, "done"),
    ("query_graphql", {"workspace": "w"}, "data")])
def test_the_hand_back_continues_start_at_the_right_step(tool, call, step):
    h = tool_listing.hand_back(tool, call, {})
    assert h["start"].get("step", "data") == step and "tool" not in h
    assert not directory.IMPERATIVE.search(h["say"]) and not directory.DIRECTIVE.search(h["say"])
    assert tool_listing.forward([h])


def test_no_card_is_a_dead_end_and_no_button_points_at_an_unlisted_tool(monkeypatch):
    """Every card's last state on the SAP demo (tools/smooth_measure.py --tools): 0 dead ends."""
    monkeypatch.delenv(tool_listing.ADVANCED, raising=False)
    monkeypatch.setenv("KRUSGRAPH_MCP_APPS", "1")
    sys.path.insert(0, str(ROOT / "tools"))
    import smooth_measure_tools
    out = smooth_measure_tools.dead_ends("sap")
    assert out["calls"] >= 15
    assert out["dead_ends"] == 0, [r for r in out["rows"] if r["dead_end"]]
    assert out["buttons_to_unlisted_tools"] == 0, [r for r in out["rows"] if r.get("unlisted")]


def test_next_steps_under_the_default_listing_name_only_listed_tools(monkeypatch):
    monkeypatch.delenv(tool_listing.ADVANCED, raising=False)
    allowed = set(mcp_apps_next.STEP_TOOLS) | set(mcp_apps_next.DRY_RUN_TOOLS)
    for t in allowed:
        if not tool_listing.listed(t):
            assert t in tool_listing.ALIAS or tool_listing.default_step({"label": "x", "tool": t}) is None, t
