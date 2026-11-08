"""Round n124: a second MCP Apps card, for review_plan: the plan as an ER diagram (inline SVG) with each relationship's
rule and counts, keys marked, findings highlighted, and one button per undecided item that asks the host to call
review_plan with that decision. Behind the n119 flag KRUSGRAPH_MCP_APPS (off by default).

Checked here: the resource and review_plan's _meta follow the same specification names as n119's card; the card loads
nothing from outside; its buttons can only ask for review_plan, with the call's own arguments plus `previous` and one
decision; the diagram holds every table and relationship of the synthetic shop schema; review_plan's text answer is
the same with the card as without; the flag off means no resource. What this does not show: that a given client
renders the card. That is tried by hand after a deploy with the flag on.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

from fabric_backend import mcp_apps, mcp_apps_review, review, server

from test_golden import SRC, fabric  # noqa: F401  (the hosted server against the synthetic shop workspace)

ROOT = Path(__file__).resolve().parents[1]
SHOP_TABLES = {"addresses", "audit_log", "categories", "customers", "order_items", "orders", "products"}
SHOP_RELS = {"rel:addresses.customer_id>customers", "rel:audit_log.customer_id>customers", "rel:order_items.order_id>orders",
             "rel:order_items.product_id>products", "rel:orders.customer_id>customers", "rel:orders.ship_to_id>addresses",
             "rel:products.category_id>categories"}


def _app_server():
    """A server built the way server.py builds it with the flag on, holding the real review_plan."""
    from mcp.server.mcpserver import MCPServer
    m = MCPServer("n124", extensions=mcp_apps.extensions(on=True))
    m.add_tool(server.review_plan, title="Keep the reviewed plan as a file (nothing in Fabric changes)",
               annotations=server.RO, meta=mcp_apps_review.tool_meta(on=True))
    return m


# ------------------------------------------------------------------ the flag ------------------------------------------

def test_flag_off_means_no_resource_and_no_meta_on_review_plan():
    if mcp_apps.enabled():
        pytest.skip("KRUSGRAPH_MCP_APPS is set in this environment")
    assert mcp_apps_review.tool_meta() is None
    assert asyncio.run(server.mcp.list_resources()) == []
    [tool] = [t for t in asyncio.run(server.mcp.list_tools()) if t.name == "review_plan"]
    assert tool.meta is None and "_meta" not in tool.model_dump(by_alias=True, exclude_none=True)


# ------------------------------------------------------------------ the declaration -----------------------------------

def test_the_resource_is_declared_like_the_n119_card():
    m = _app_server()
    res = {str(r.uri): r for r in asyncio.run(m.list_resources())}
    from fabric_backend import mcp_apps_build                            # n169: the build card
    assert set(res) == {mcp_apps.CARD_URI, mcp_apps_review.CARD_URI, mcp_apps_build.CARD_URI}
    card = res[mcp_apps_review.CARD_URI]
    assert mcp_apps_review.CARD_URI.startswith("ui://krusgraph/")
    assert card.mime_type == "text/html;profile=mcp-app" == mcp_apps.APP_MIME_TYPE
    assert m._lowlevel_server.extensions == {"io.modelcontextprotocol/ui": {}}
    [tool] = asyncio.run(m.list_tools())
    meta = tool.model_dump(by_alias=True, exclude_none=True)["_meta"]
    assert meta == {"ui": {"resourceUri": mcp_apps_review.CARD_URI}, "ui/resourceUri": mcp_apps_review.CARD_URI}
    assert "visibility" not in meta["ui"]                                    # the model still calls review_plan


def test_resources_read_returns_the_html_over_the_protocol():
    from mcp import Client

    async def go():
        async with Client(_app_server()) as c:
            return await c.read_resource(mcp_apps_review.CARD_URI)
    [content] = asyncio.run(go()).contents
    assert content.mime_type == "text/html;profile=mcp-app"
    assert content.text == mcp_apps_review.card_html() and content.text.startswith("<!DOCTYPE html>")
    assert content.meta == {"ui": {"prefersBorder": True}}                   # no csp: the host's restrictive default


# ------------------------------------------------------------------ the HTML ------------------------------------------

class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.attrs = [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs += [(tag, k, v) for k, v in attrs]


def test_no_external_loads():
    html = mcp_apps_review.card_html()
    p = _Tags()
    p.feed(html)
    assert p.tags[:1] == ["html"] and html.lower().startswith("<!doctype html>")
    assert not {"img", "image", "link", "iframe", "object", "embed", "video", "audio", "source", "base", "form",
                "use", "foreignobject"} & set(p.tags)
    assert not [a for a in p.attrs if a[1] in ("src", "href", "xlink:href", "action", "srcset", "poster", "data")]
    # the one URL-shaped string is the SVG namespace name createElementNS needs; it is an identifier, nothing loads it
    assert html.count(mcp_apps_review.SVG_NS) == 1 and mcp_apps_review.SVG_NS == "http://www.w3.org/2000/svg"
    low = html.replace(mcp_apps_review.SVG_NS, "").lower()
    for banned in ("http://", "https://", "//cdn", "url(", "@import", "fetch(", "xmlhttprequest", "websocket",
                   "eventsource", "sendbeacon", "import(", "importscripts", "localstorage", "sessionstorage",
                   "document.cookie", "indexeddb", "navigator.", "innerhtml", "outerhtml", "insertadjacenthtml",
                   "document.write", "eval(", "new function", "href", "ui/open-link", "ui/message",
                   "ui/update-model-context"):
        assert banned not in low, banned


def test_the_view_uses_the_spec_method_names():
    html = mcp_apps_review.card_html()
    assert 'protocolVersion: "2026-01-26"' in html and "appInfo" in html and "appCapabilities" in html
    assert set(re.findall(r'"((?:ui|tools|resources)/[a-z/-]+)"', html)) == {
        "ui/initialize", "ui/notifications/initialized", "ui/notifications/tool-input", "ui/notifications/tool-result",
        "ui/notifications/tool-cancelled", "ui/resource-teardown", "ui/notifications/size-changed", "tools/call"}


# ------------------------------------------------------------------ the buttons ---------------------------------------

def test_buttons_map_only_to_review_plan():
    html = mcp_apps_review.card_html()
    allowed = json.loads(re.search(r"var ALLOWED = (\{.*?\});", html).group(1))
    assert allowed == {"review_plan": list(mcp_apps_review.CARRIED)}
    assert html.count('request("tools/call"') == 1 and "callTool(TOOL, args," in html     # n138: through callTool
    assert 'var TOOL = "review_plan";' in html
    listing = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    rp = listing["review_plan"]
    assert rp.annotations.read_only_hint is True and not rp.annotations.destructive_hint
    assert set(mcp_apps_review.CARRIED) | {"previous", "decisions"} <= set(rp.input_schema["properties"])
    others = [n for n in listing if n != "review_plan" and re.search(rf"\b{n}\b", html)]
    assert others == [], others                                              # no other tool is named on the card
    assert set(mcp_apps_review.DECISIONS) <= set(review.REVIEW) and "proposed" not in mcp_apps_review.DECISIONS


# ------------------------------------------------------------------ the text answer -----------------------------------

def test_the_text_answer_is_unchanged_with_the_card(fabric):  # noqa: F811
    from mcp import Client
    plain = server.review_plan(**SRC)

    async def go():
        async with Client(_app_server()) as c:
            return await c.call_tool("review_plan", SRC)
    r = asyncio.run(go())
    [part] = r.content
    assert part.type == "text" and json.loads(part.text) == json.loads(plain)
    assert r.structured_content in (None, {"result": part.text})


# ------------------------------------------------------------------ the card in a browser -----------------------------

def _playwright() -> bool:
    if not shutil.which("node"):
        return False
    return subprocess.run(["node", "-e", "require('playwright')"], capture_output=True, cwd=ROOT).returncode == 0


def _browse(tmp_path, args: dict, answer: str, reply: str, width: int = 520, scheme: str = "light", shot: str | None = None):
    (tmp_path / "card.html").write_text(mcp_apps_review.card_html())
    (tmp_path / "input.json").write_text(json.dumps(args))
    (tmp_path / "result.json").write_text(json.dumps({"content": [{"type": "text", "text": answer}]}))
    (tmp_path / "reply.json").write_text(json.dumps({"content": [{"type": "text", "text": reply}]}))
    run = subprocess.run(["node", str(Path(__file__).parent / "mcp_apps_review_browser.js"),
                          *(str(tmp_path / f) for f in ("card.html", "input.json", "result.json", "reply.json")),
                          str(width), scheme, *([shot] if shot else [])],
                         capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    assert out["requests"] == [] and out["errors"] == [] and out["violations"] == []
    return out


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_the_diagram_has_every_table_and_relationship_of_the_shop(tmp_path, fabric):  # noqa: F811
    args = {**SRC, "validate": True}
    text = server.review_plan(**args)
    data = json.loads(text)
    rv = data["review"]
    assert set(rv["snapshot"]["tables"]) == SHOP_TABLES
    first = next(it for it in rv["items"] if it["review"] in mcp_apps_review.UNDECIDED)
    reply = server.review_plan(**SRC, previous=rv, decisions=[{"item": first["id"], "review": "accepted"}])
    shot = os.environ.get("KRUSGRAPH_CARD_SHOT")
    out = _browse(tmp_path, args, text, reply, shot=shot and f"{shot}-wide.png")
    d = out["diagram"]

    # every table, with its key columns marked
    assert {t["name"] for t in d["tables"]} == SHOP_TABLES
    for t in d["tables"]:
        assert sorted(t["keys"]) == sorted(rv["snapshot"]["tables"][t["name"]]["key"]), t
    [audit] = [t for t in d["tables"] if t["name"] == "audit_log"]
    assert audit["finding"] and "no key" in audit["text"]                  # the open question is highlighted
    assert [t["name"] for t in d["tables"] if t["finding"]] == ["audit_log"]

    # every relationship, labelled with its rule and its counts
    assert {r["id"] for r in d["rels"]} == SHOP_RELS == {it["id"] for it in rv["items"] if it["type"] == "relationship"}
    items = {it["id"]: it for it in rv["items"]}
    labels = {lb["for"]: lb["text"] for lb in d["labels"]}
    assert set(labels) == SHOP_RELS
    for rid, lines in labels.items():
        res = items[rid]["check"]["result"]
        assert lines == [items[rid]["rule"], f"{res['rows_with_value']} rows, {res['orphans']} orphans"], (rid, lines)
    assert d["overlaps"] == 0, d["labels"]                                   # no label over a table or another label

    # every word of the card is in the text answer: the summary, the attention lines, each item and its verdict
    assert data["summary"] in out["text"]
    for line in data["attention"]:
        assert line in out["text"]
    for it in rv["items"]:
        assert it["check"]["verdict"] in out["text"] and it["check"]["verdict"] in text

    # one button per undecided item; the first asks for review_plan with that one decision and the file on screen
    undecided = [it["id"] for it in rv["items"] if it["review"] in mcp_apps_review.UNDECIDED]
    assert out["buttons"] == undecided and len(undecided) == 13
    calls = [m["params"] for m in out["log"] if m.get("method") == "tools/call"]
    assert len(calls) == 1 and calls[0]["name"] == "review_plan"
    a = calls[0]["arguments"]
    assert set(a) <= set(mcp_apps_review.CARRIED) | {"previous", "decisions"}
    assert {k: a[k] for k in ("workspace", "source", "schema")} == SRC and "validate" not in a
    assert a["previous"] == rv and a["decisions"] == [{"item": first["id"], "review": "accepted"}]
    assert out["after"]["buttons"] == undecided[1:]                          # the card shows the new answer
    assert "Nothing was created or changed in the source." in out["after"]["text"]


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_findings_are_highlighted_and_the_card_fits_a_narrow_dark_screen(tmp_path, fabric):  # noqa: F811
    args = {**SRC, "validate": True, "keys": {"order_items": ["order_id"]}}   # a key that does not hold
    text = server.review_plan(**args)
    rv = json.loads(text)["review"]
    assert next(it for it in rv["items"] if it["id"] == "key:order_items")["check"]["status"] == "failed"
    shot = os.environ.get("KRUSGRAPH_CARD_SHOT")
    out = _browse(tmp_path, args, text, text, width=340, scheme="dark", shot=shot and f"{shot}-narrow-dark.png")
    d = out["diagram"]
    assert {t["name"] for t in d["tables"] if t["finding"]} == {"audit_log", "order_items"}
    assert {r["id"] for r in d["rels"]} == {it["id"] for it in rv["items"] if it["type"] == "relationship"}
    assert d["overlaps"] == 0, json.dumps([d["labels"], [t["box"] | {"n": t["name"]} for t in d["tables"]]])
    assert d["docWidth"] <= d["viewWidth"] and d["svgWidth"] <= d["viewWidth"]  # no sideways scroll at 340 px
    assert d["colors"]["body"] != "rgb(255, 255, 255)"                          # dark background in a dark host
    assert "Accepted, but the check failed: key of order_items" in out["text"]
    calls = [m["params"] for m in out["log"] if m.get("method") == "tools/call"]
    assert calls[0]["arguments"]["keys"] == {"order_items": ["order_id"]}      # the call's own keys are carried
