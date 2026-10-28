"""Round n18: how the tools describe themselves to agents. Every parameter of every tool carries a description in
tools/list (inputSchema.properties.*.description), and a tool's description describes rather than instructs (the
Claude directory's policy: "Returns …" and "Use when …" are fine, "Always call X first" and "You must" are not)."""
import asyncio
import json
import re

import pytest

from fabric_backend import server

INSTRUCTING = ("always", "must", "start here", "use it before")


def _flat(text) -> str:
    return " ".join(str(text or "").split())


def _tools():
    return asyncio.run(server.mcp.list_tools())


TOOLS = _tools()


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_every_parameter_has_a_description(tool):
    props = tool.input_schema.get("properties", {})
    missing = [name for name, p in props.items() if not str(p.get("description", "")).strip()]
    assert not missing, f"{tool.name}: no description for {missing}"


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_description_describes_and_does_not_instruct(tool):
    text = _flat(tool.description).lower()
    found = [w for w in INSTRUCTING if re.search(r"\b" + re.escape(w) + r"\b", text)]
    assert not found, f"{tool.name}: instructing phrase {found}"
    for p in tool.input_schema.get("properties", {}).values():
        found = [w for w in INSTRUCTING if re.search(r"\b" + re.escape(w) + r"\b", p.get("description", "").lower())]
        assert not found, f"{tool.name}: instructing phrase {found} in a parameter"


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_description_names_what_it_returns_and_the_error_shape(tool):
    text = _flat(tool.description)
    assert "Returns" in text and "{error, kind, hint}" in text, tool.name


def test_creating_tools_say_what_changes_in_fabric():
    by = {t.name: _flat(t.description) for t in TOOLS}
    for name in ("create_backend", "create_ontology", "create_semantic_model", "create_views", "create_data_agent",
                 "create_silver_notebook", "create_gold_views", "create_drift_monitor"):
        assert "Changes Fabric" in by[name] and ("deleted" in by[name] or "dropped" in by[name]), name
    assert "does not run validate_plan" in by["create_backend"]


def test_read_only_listing_stays_small():
    """Round n26: the tools an agent gets with read-only access, as compact JSON of list_tools(), stay under a cap a
    little above what n26 landed on (57 974 characters), so the listing does not grow again by accident."""
    ro = [t.model_dump(by_alias=True, exclude_none=True, mode="json") for t in TOOLS
          if t.annotations and t.annotations.read_only_hint]
    size = len(json.dumps({"tools": ro}, separators=(",", ":"), ensure_ascii=False))
    assert size <= 60_000, f"read-only tools/list is {size} characters"
