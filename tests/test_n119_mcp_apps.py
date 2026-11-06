"""Round n119: an MCP Apps prototype. validate_plan's summary also declares a ui:// resource, a card with the counts, what
needs attention and the n103 next steps as buttons, behind the flag KRUSGRAPH_MCP_APPS (off by default).

Checked here: the resource and the tool's _meta use the names of the stable specification (2026-01-26); the card loads
nothing from outside; its buttons can only ask for read and draft tools; validate_plan's text answer is the same with
the card as without it; the flag off means no resource, no _meta and the listing as before. What this does not show:
that a given client (Claude or another) renders the card. That is tried by hand after a deploy with the flag on.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

from fabric_backend import evidence, mcp_apps, server

from test_golden import SRC, fabric  # noqa: F401  (the hosted server against the synthetic shop workspace)

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).parent / "golden"


def _app_server():
    """A server built the way server.py builds it with the flag on, holding the real validate_plan."""
    from mcp.server.mcpserver import MCPServer
    m = MCPServer("n119", extensions=mcp_apps.extensions(on=True))
    m.add_tool(server.validate_plan, title="Check the plan against the data", annotations=server.RO,
               meta=mcp_apps.tool_meta(on=True))
    return m


# ------------------------------------------------------------------ the flag ------------------------------------------

def test_the_flag_is_off_unless_it_is_exactly_one():
    assert not mcp_apps.enabled({})
    for value in ("", "0", "true", "yes", "on"):
        assert not mcp_apps.enabled({mcp_apps.FLAG: value}), value
    assert mcp_apps.enabled({mcp_apps.FLAG: "1"})


def test_flag_off_means_no_resource_no_meta_and_no_extension():
    if mcp_apps.enabled():
        pytest.skip("KRUSGRAPH_MCP_APPS is set in this environment")
    assert mcp_apps.tool_meta() is None and mcp_apps.extensions() == []
    assert asyncio.run(server.mcp.list_resources()) == []
    assert asyncio.run(server.mcp.list_resource_templates()) == []
    assert all(t.meta is None for t in asyncio.run(server.mcp.list_tools()))
    assert "io.modelcontextprotocol/ui" not in server.mcp._lowlevel_server.extensions


# ------------------------------------------------------------------ the declaration -----------------------------------

def test_the_resource_is_declared_with_the_spec_mime_type_and_a_ui_uri():
    m = _app_server()
    res = next(r for r in asyncio.run(m.list_resources()) if str(r.uri) == mcp_apps.CARD_URI)   # n124 adds review_plan's card
    assert str(res.uri) == mcp_apps.CARD_URI and str(res.uri).startswith("ui://")
    assert res.mime_type == "text/html;profile=mcp-app" == mcp_apps.APP_MIME_TYPE
    from mcp.server.apps import APP_MIME_TYPE, EXTENSION_ID
    assert APP_MIME_TYPE == mcp_apps.APP_MIME_TYPE and EXTENSION_ID == "io.modelcontextprotocol/ui"
    assert m._lowlevel_server.extensions == {EXTENSION_ID: {}}               # advertised under capabilities.extensions
    [tool] = asyncio.run(m.list_tools())
    meta = tool.model_dump(by_alias=True, exclude_none=True)["_meta"]
    assert meta == {"ui": {"resourceUri": mcp_apps.CARD_URI}, "ui/resourceUri": mcp_apps.CARD_URI}
    assert "visibility" not in meta["ui"]                                    # default ["model", "app"]: Claude still calls it


def test_resources_read_returns_the_html_over_the_protocol():
    from mcp import Client

    async def go():
        async with Client(_app_server()) as c:
            caps = c.server_capabilities
            read = await c.read_resource(mcp_apps.CARD_URI)
            return caps, read
    caps, read = asyncio.run(go())
    assert "io.modelcontextprotocol/ui" in (caps.extensions or {})
    [content] = read.contents
    assert str(content.uri) == mcp_apps.CARD_URI
    assert content.mime_type == "text/html;profile=mcp-app"
    assert content.text == mcp_apps.card_html() and content.text.startswith("<!DOCTYPE html>")
    assert content.meta == {"ui": {"prefersBorder": True}}                   # no csp: the host's restrictive default


# ------------------------------------------------------------------ the HTML ------------------------------------------

class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.attrs = [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs += [(tag, k, v) for k, v in attrs]


def test_the_html_is_self_contained_with_no_external_load_and_no_tracking():
    html = mcp_apps.card_html()
    p = _Tags()
    p.feed(html)
    assert p.tags[:1] == ["html"] and html.lower().startswith("<!doctype html>")
    assert not {"img", "link", "iframe", "object", "embed", "video", "audio", "source", "base", "form"} & set(p.tags)
    assert not [a for a in p.attrs if a[1] in ("src", "href", "action", "srcset", "poster", "data")]
    low = html.lower()
    for banned in ("http://", "https://", "//cdn", "url(", "@import", "fetch(", "xmlhttprequest", "websocket",
                   "eventsource", "sendbeacon", "import(", "importscripts", "localstorage", "sessionstorage",
                   "document.cookie", "indexeddb", "navigator.", "innerhtml", "outerhtml", "insertadjacenthtml",
                   "document.write", "eval(", "new function", "ui/open-link", "ui/message", "ui/update-model-context"):
        assert banned not in low, banned
    # n136: the only pictures are the mascots, inline SVG with no reference of any kind (tests/test_n136_card_mascots.py)
    assert not {"image", "use", "foreignobject"} & set(p.tags)
    assert low.count("<svg") == 3 and all('class="mascot ' in t for t in re.findall(r"<svg[^>]*>", low))


def test_the_view_uses_the_spec_method_names():
    html = mcp_apps.card_html()
    for name in ('"ui/initialize"', '"ui/notifications/initialized"', '"ui/notifications/tool-input"',
                 '"ui/notifications/tool-result"', '"ui/notifications/size-changed"', '"tools/call"',
                 "appInfo", "appCapabilities", 'protocolVersion: "2026-01-26"'):
        assert name in html, name
    assert set(re.findall(r'"((?:ui|tools|resources)/[a-z/-]+)"', html)) == {
        "ui/initialize", "ui/notifications/initialized", "ui/notifications/tool-input", "ui/notifications/tool-result",
        "ui/notifications/tool-cancelled", "ui/resource-teardown", "ui/notifications/size-changed", "tools/call"}


# ------------------------------------------------------------------ the buttons ---------------------------------------

def _allowed() -> dict:
    return json.loads(re.search(r"var ALLOWED = (\{.*?\});", mcp_apps.card_html()).group(1))


def test_buttons_map_only_to_read_and_draft_tools():
    allowed = _allowed()
    assert set(allowed) == set(evidence.NEXT_STEP_TOOLS)
    listing = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    for name, carried in allowed.items():
        tool = listing[name]
        assert tool.annotations.read_only_hint is True and not tool.annotations.destructive_hint, name
        assert not name.startswith(("create_", "delete_", "update_")), name
        assert set(carried) <= set(tool.input_schema["properties"]), (name, carried)
    creating = [n for n, t in listing.items() if not t.annotations.read_only_hint]
    assert creating and not [n for n in creating if n in mcp_apps.card_html()]
    assert "hasOwnProperty.call(ALLOWED, s.tool)" in mcp_apps.card_html()     # a step outside ALLOWED gets no button


def test_every_next_step_argument_exists_on_its_tool():
    listing = {t.name: t.input_schema["properties"] for t in asyncio.run(server.mcp.list_tools())}
    summary = json.loads((GOLDEN / "hosted_tools.json").read_text())
    steps = [s for e in summary if isinstance(e, dict) and e.get("tool") == "validate_plan"
             for s in (e["answer"].get("next_steps") or [])]
    assert steps
    for s in steps:
        assert set(s["arguments"]) <= set(listing[s["tool"]]), s


# ------------------------------------------------------------------ the text answer -----------------------------------

def test_the_text_answer_is_unchanged_with_the_card(fabric):  # noqa: F811
    from mcp import Client
    plain = server.validate_plan(**SRC)

    async def go():
        async with Client(_app_server()) as c:
            return await c.call_tool("validate_plan", SRC)
    r = asyncio.run(go())
    [part] = r.content
    assert part.type == "text" and json.loads(part.text) == json.loads(plain)
    assert r.structured_content in (None, {"result": part.text})            # nothing added beside the text
    golden = [e["answer"] for e in json.loads((GOLDEN / "hosted_tools.json").read_text())
              if isinstance(e, dict) and e.get("tool") == "validate_plan" and e.get("args") == SRC]
    assert golden == [json.loads(plain)]


# ------------------------------------------------------------------ the real server with the flag on ------------------

def test_the_hosted_server_with_the_flag_on_keeps_its_tool_count_and_listing_cap():
    code = r"""
import asyncio, inspect, json
from fabric_backend import server, mcp_apps
tools = asyncio.run(server.mcp.list_tools())
ro = [t.model_dump(by_alias=True, exclude_none=True, mode="json") for t in tools if t.annotations and t.annotations.read_only_hint]
for t in ro:
    t["description"] = inspect.cleandoc(t.get("description", ""))
print(json.dumps({"names": sorted(t.name for t in tools),
                  "meta": {t.name: t.meta for t in tools if t.meta},
                  "resources": [[str(r.uri), r.mime_type] for r in asyncio.run(server.mcp.list_resources())],
                  "ro_size": len(json.dumps({"tools": ro}, separators=(",", ":"), ensure_ascii=False))}))
"""
    env = {k: v for k, v in os.environ.items() if k != mcp_apps.FLAG}
    on = json.loads(subprocess.run([sys.executable, "-c", code], env=env | {mcp_apps.FLAG: "1"}, cwd=ROOT,
                                   capture_output=True, text=True, check=True).stdout)
    off = json.loads(subprocess.run([sys.executable, "-c", code], env=env, cwd=ROOT,
                                    capture_output=True, text=True, check=True).stdout)
    assert on["names"] == off["names"]                                      # the tool count does not change
    assert off["meta"] == {} and off["resources"] == []
    from fabric_backend import mcp_apps_review                           # n124: the second card, review_plan's
    assert on["meta"] == {"validate_plan": mcp_apps.tool_meta(on=True), "review_plan": mcp_apps_review.tool_meta(on=True)}
    assert on["resources"] == [[mcp_apps.CARD_URI, "text/html;profile=mcp-app"],
                               [mcp_apps_review.CARD_URI, "text/html;profile=mcp-app"]]
    assert on["ro_size"] <= 64_000 and on["ro_size"] - off["ro_size"] < 400, (on["ro_size"], off["ro_size"])


# ------------------------------------------------------------------ the card in a browser -----------------------------

def _playwright() -> bool:
    if not shutil.which("node"):
        return False
    return subprocess.run(["node", "-e", "require('playwright')"], capture_output=True, cwd=ROOT).returncode == 0


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_the_card_renders_and_asks_the_host_for_read_tools_only(tmp_path, fabric):  # noqa: F811
    summary = json.loads(server.validate_plan(**SRC))
    args = {**SRC, "keys": {"order_items": ["order_id", "line_no"]}, "detail": "summary", "max_items": 60}
    (tmp_path / "card.html").write_text(mcp_apps.card_html())
    (tmp_path / "input.json").write_text(json.dumps(args))
    (tmp_path / "result.json").write_text(json.dumps({"content": [{"type": "text", "text": json.dumps(summary, indent=2)}]}))
    run = subprocess.run(["node", str(Path(__file__).parent / "mcp_apps_card_browser.js"), *(str(tmp_path / f)
                          for f in ("card.html", "input.json", "result.json"))], capture_output=True, text=True,
                         cwd=ROOT, timeout=60)
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    assert out["requests"] == [] and out["errors"] == [] and out["violations"] == []
    text = out["text"]
    assert summary["summary"] in text
    assert "Keys" in text and "6 of 6 passed" in text and "Relationships" in text and "7 of 7 passed" in text
    assert "Needs attention" in text and "products / order_items" in text
    first = [m for m in out["log"] if m.get("method")][:2]
    assert [m["method"] for m in first] == ["ui/initialize", "ui/notifications/initialized"]
    assert first[0]["params"]["protocolVersion"] == "2026-01-26" and "appInfo" in first[0]["params"]
    calls = [m["params"] for m in out["log"] if m.get("method") == "tools/call"]
    assert out["buttons"] == len(summary["next_steps"]) == len(calls) >= 1
    for call, step in zip(calls, summary["next_steps"]):
        assert call["name"] == step["tool"] and call["name"] in evidence.NEXT_STEP_TOOLS
        carried = {k: args[k] for k in mcp_apps.CARRIED[step["tool"]] if k in args}
        assert call["arguments"] == {**carried, **step["arguments"]}         # detail and max_items are not carried
    assert any(m.get("method") == "ui/notifications/size-changed" for m in out["log"])
