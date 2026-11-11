"""Round n137: the MCP Apps cards read the tool result in every form a host may deliver it.

Seen live in Claude on the web and in the Claude desktop app on 6 November 2026: validate_plan's card listed the whole
answer as one JSON string under "Needs attention" (no mascots, no next-step buttons) and review_plan's card said "The
answer holds no review file". The tools return `str`, so the SDK derives the output schema {"result": string} and
sends `structuredContent: {"result": "<JSON text>"}`; the cards only parsed the text content and showed the wrapper's
`result` as an attention line. Checked here, with the live shop answers (validate_plan: 6 keys, 7 relationships, 13
passed, next steps semantic_model_draft and ontology_draft; review_plan: 13 items passed, the open question
key:audit_log): each card renders the same DOM from the text content, from the wrapper (in the text or as
structuredContent), from structuredContent, and from what the hosted server now returns with the flag on; what cannot
be read gives a short sentence and no JSON; with the flag on validate_plan and review_plan return the answer as
structuredContent with the text unchanged; with the flag off nothing changes.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from fabric_backend import mcp_apps, mcp_apps_review, server

from test_golden import SRC, fabric  # noqa: F401  (the hosted server against the synthetic shop workspace)

ROOT = Path(__file__).resolve().parents[1]
CARDS = {"validate_plan": mcp_apps.card_html, "review_plan": mcp_apps_review.card_html}


def _playwright() -> bool:
    if not shutil.which("node"):
        return False
    return subprocess.run(["node", "-e", "require('playwright')"], capture_output=True, cwd=ROOT).returncode == 0


needs_browser = pytest.mark.skipif(not _playwright(), reason="node + playwright not available")


@pytest.fixture
def live_shop(fabric, monkeypatch):  # noqa: F811
    """The shop as the live run of 6 November 2026 answered: no header amount finding, so every check passes."""
    from fabric_backend import amounts
    monkeypatch.setattr(amounts, "check", lambda *a, **k: {"findings": []})
    return fabric


def _shapes(answer: str) -> dict:
    """Every form of a CallToolResult the specification lets a host deliver, for one text answer."""
    data = json.loads(answer)
    wrapped = json.dumps({"result": answer})
    return {
        "text": {"content": [{"type": "text", "text": answer}]},
        "sdk_wrapper": {"content": [{"type": "text", "text": answer}], "structuredContent": {"result": answer}},
        "wrapper_in_text": {"content": [{"type": "text", "text": wrapped}]},
        "wrapper_everywhere": {"content": [{"type": "text", "text": wrapped}], "structuredContent": {"result": answer}},
        "wrapper_pretty": {"content": [{"type": "text", "text": json.dumps({"result": answer}, indent=2)}]},
        "structured": {"content": [{"type": "text", "text": answer}], "structuredContent": data},
        "structured_only": {"content": [], "structuredContent": data},
        "bare_wrapper": {"result": answer},
    }


def _browse(tmp_path, tool: str, args: dict, result: dict, reply: dict | None = None) -> dict:
    (tmp_path / "card.html").write_text(CARDS[tool]())
    (tmp_path / "input.json").write_text(json.dumps(args))
    (tmp_path / "result.json").write_text(json.dumps(result))
    (tmp_path / "reply.json").write_text(json.dumps(reply or {"content": [{"type": "text", "text": "{}"}]}))
    run = subprocess.run(["node", str(Path(__file__).parent / "mcp_apps_result_browser.js"),
                          *(str(tmp_path / f) for f in ("card.html", "input.json", "result.json", "reply.json"))],
                         capture_output=True, text=True, cwd=ROOT, timeout=90)
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    assert out["requests"] == [] and out["errors"] == [] and out["violations"] == []
    return out


def _no_json(view: dict):
    """No raw JSON anywhere on the card: not in a list, not in a bubble, not in the verdict."""
    for line in view["attention"] + [view["verdict"], view["result"]] + [f["text"] for f in view["figures"]]:
        assert not line.lstrip().startswith(("{", "[")), line
    for marker in ('"detail"', '"summary"', '{"result"', '"review":', '\\"'):
        assert marker not in view["text"], marker


def _structured_server():
    """The hosted registration with the flag on, as server.py does it."""
    from mcp.server.mcpserver import MCPServer
    m = MCPServer("n137", extensions=mcp_apps.extensions(on=True))
    for fn, meta in ((server.validate_plan, mcp_apps.tool_meta(on=True)), (server.review_plan, mcp_apps_review.tool_meta(on=True))):
        m.add_tool(mcp_apps.structured(fn), name=fn.__name__, annotations=server.RO, meta=meta,
                   **mcp_apps.registration(fn.__name__, on=True))
    return m


def _call(tool: str, args: dict) -> dict:
    from mcp import Client

    async def go():
        async with Client(_structured_server()) as c:
            return await c.call_tool(tool, args)
    return asyncio.run(go()).model_dump(by_alias=True, exclude_none=True, mode="json")


# ------------------------------------------------------------------ the live answers ----------------------------------

def test_the_live_shop_answers(live_shop):
    v = json.loads(server.validate_plan(**SRC))
    assert v["summary"] == "6 of 6 keys unique, 7 of 7 relationships hold without orphans"
    assert not v.get("needs_attention") and not v.get("attention")         # an all-passed summary has neither
    assert v["totals"]["keys"]["passed"] + v["totals"]["relationships"]["passed"] == 13
    assert [s["tool"] for s in v["next_steps"]] == ["semantic_model_draft", "ontology_draft"]
    assert v["result"].startswith("All 13 counted checks passed")
    r = json.loads(server.review_plan(**SRC, validate=True))
    assert len(r["review"]["items"]) == 13 and all(i["check"]["status"] == "passed" for i in r["review"]["items"])
    assert [q["about"] for q in r["review"]["open_questions"]] == ["key:audit_log"]


# ------------------------------------------------------------------ the server's structuredContent --------------------

def test_structured_content_with_the_flag_and_the_text_unchanged(live_shop):
    for tool, args in (("validate_plan", SRC), ("review_plan", {**SRC, "validate": True})):
        plain = getattr(server, tool)(**args)
        assert isinstance(plain, str)                                         # the module's function answers text
        r = _call(tool, args)
        lead, part = r["content"]                                             # n218: the result and next steps first
        assert lead["type"] == "text" and "Next steps:" in lead["text"] and not lead["text"].lstrip().startswith("{")
        assert part["type"] == "text" and json.loads(part["text"]) == json.loads(plain)
        # n170: structuredContent is the answer plus the picture's data (`map`), which the text does not carry
        assert {k: v for k, v in r["structuredContent"].items() if k not in ("map", "kg_card", "checks", "next")} == json.loads(plain) and not r.get("isError")   # n172: + the card's words
        assert "map" in r["structuredContent"] and "map" not in json.loads(plain)


def test_an_answer_that_is_not_an_object_has_no_structured_content():
    r = mcp_apps.call_result("not json").model_dump(by_alias=True, exclude_none=True)
    assert r["content"][0]["text"] == "not json" and "structuredContent" not in r
    assert "structuredContent" not in mcp_apps.call_result("[1, 2]").model_dump(by_alias=True, exclude_none=True)


def test_the_listing_with_and_without_the_flag():
    code = r"""
import asyncio, json
from fabric_backend import server
tools = asyncio.run(server.mcp.list_tools())
print(json.dumps({t.name: t.model_dump(by_alias=True, exclude_none=True, mode="json") for t in tools}))
"""
    env = {k: v for k, v in os.environ.items() if k != mcp_apps.FLAG}
    on = json.loads(subprocess.run([sys.executable, "-c", code], env=env | {mcp_apps.FLAG: "1"}, cwd=ROOT,
                                   capture_output=True, text=True, check=True).stdout)
    off = json.loads(subprocess.run([sys.executable, "-c", code], env=env, cwd=ROOT,
                                    capture_output=True, text=True, check=True).stdout)
    assert set(on) == set(off)                                               # the same tools
    for name in off:
        if name in mcp_apps.STRUCTURED:
            assert "outputSchema" not in on[name] and on[name]["inputSchema"] == off[name]["inputSchema"]
            assert {k: v for k, v in on[name].items() if k not in ("_meta",)} == \
                   {k: v for k, v in off[name].items() if k != "outputSchema"}
        else:
            assert on[name] == off[name], name                               # every other tool as it was
    assert mcp_apps.registration("validate_plan", on=False) == {} and mcp_apps.registration("list_tables", on=True) == {}


# ------------------------------------------------------------------ the validate_plan card ----------------------------

def _check_validate(view: dict, data: dict, words: dict | None = None):
    if words:                                                                # n172: the server's own words for the card
        assert view["verdict"] == " ".join(words["lines"]) and not view["resultShown"]
        said = {f["kind"]: f for f in view["figures"] if f["shown"]}
        assert said["onto"]["text"] == words["onto"] and said["onto"]["glad"]
        assert said["builder"]["text"] == data["next_steps"][0]["why"]     # no builds offered here: the draft step, open
        assert "Run semantic_model_draft" in view["buttons"]
        _no_json(view)
        return
    assert view["verdict"] == data["summary"]
    assert view["counts"] == [["Keys", "6 of 6 passed"], ["Relationships", "7 of 7 passed"], ["Needs attention", "0"]]
    assert view["attention"] == [] and view["attentionShown"]              # n138: "Nothing needs attention."
    assert view["resultShown"] and view["result"] == ". " + data["result"]  # n138: in the summary line
    assert view["steps"] == [s["why"] for s in data["next_steps"]]
    assert "Run semantic_model_draft" in view["buttons"] and "Run ontology_draft" in view["buttons"]
    said = {f["kind"]: f for f in view["figures"] if f["shown"]}
    assert view["mascotsShown"] and set(said) == {"onto", "builder"}         # nothing needs attention: no Thinker
    assert said["onto"]["text"] == data["summary"] and said["onto"]["pose"] == "celebrate" and said["onto"]["glad"]
    assert said["builder"]["text"] == data["next_steps"][0]["why"] and said["builder"]["pose"] == "heart"
    _no_json(view)


@needs_browser
def test_validate_card_reads_every_shape(tmp_path, live_shop):
    answer = server.validate_plan(**SRC)
    data = json.loads(answer)
    shapes = _shapes(answer)
    shapes["hosted_server"] = _call("validate_plan", SRC)                    # what the server now returns, flag on
    assert {k: v for k, v in shapes["hosted_server"]["structuredContent"].items() if k not in ("map", "kg_card", "checks", "next")} == data   # n170: + the map; n172: + the words
    drafted = json.dumps({"tmdl": "model Model", "note": "a draft; nothing was created."})
    for name, result in shapes.items():
        out = _browse(tmp_path, "validate_plan", SRC, result,
                      reply={"content": [{"type": "text", "text": drafted}], "structuredContent": {"result": drafted}})
        _check_validate(out["before"], data, result.get("structuredContent", {}).get("kg_card") if isinstance(result, dict) else None)
        [call] = out["calls"]                                                 # the button asked the host for the step
        assert call["params"]["name"] == "semantic_model_draft"
        assert call["params"]["arguments"] == {k: SRC[k] for k in ("workspace", "source", "schema")}, name
        [shown] = out["after"]["outputs"]                                     # n138: a summary, the JSON under details
        assert "Show details" in shown and json.dumps(json.loads(drafted), indent=2) in shown, name


@needs_browser
def test_validate_card_attention_as_readable_lines(tmp_path, fabric):  # noqa: F811
    answer = server.validate_plan(**SRC)                                     # the shop's header amount needs attention
    data = json.loads(answer)
    [finding] = data["attention"]["amount_levels"]
    for name in ("sdk_wrapper", "wrapper_in_text", "structured_only"):
        view = _browse(tmp_path, "validate_plan", SRC, _shapes(answer)[name])["before"]
        assert view["attention"] == [f"{finding['header']} / {finding['line']}: {finding['do_instead']}"], name
        said = {f["kind"]: f for f in view["figures"] if f["shown"]}
        assert said["thinker"]["text"] == finding["do_instead"] and not any(f["glad"] for f in view["figures"])
        assert ["Needs attention", "1"] in view["counts"] and not view["resultShown"]
        _no_json(view)


@needs_browser
@pytest.mark.parametrize("tool", sorted(CARDS))
def test_an_unreadable_result_gives_a_short_sentence(tmp_path, tool):
    for result in ({"content": [{"type": "text", "text": "The tool failed before it answered."}]},
                   {"content": [{"type": "text", "text": '{"detail": "summary", "summ'}]},       # cut-off JSON
                   {"content": [], "structuredContent": {"result": "a sentence, not an answer"}},
                   {"content": [{"type": "text", "text": json.dumps({"result": "[1, 2"})}]}):
        view = _browse(tmp_path, tool, SRC, result)["before"]
        assert view["verdict"] == f"The card could not read {tool}'s answer; it is in the text of the tool result."
        assert view["attention"] == [] and not view["mascotsShown"] and not view["decisions"]
        assert view["buttons"] == ["Mascots: on"] and view["diagram"] is None
        _no_json(view)


# ------------------------------------------------------------------ the review_plan card ------------------------------

def _check_review(view: dict, data: dict):
    rv = data["review"]
    assert view["verdict"] == data["summary"]
    assert view["attention"] == data["attention"] and view["attention"][0].startswith("Open question (key:audit_log)")
    d = view["diagram"]
    assert d is not None and len(d["rels"]) == 7 and {t["name"] for t in d["tables"]} >= {"audit_log", "orders"}
    assert {r["rule"] for r in d["rels"]} == {i["rule"] for i in rv["items"] if i["type"] == "relationship"}
    assert all(r["rule"] for r in d["rels"])
    assert len(d["labels"]) == 7 and all("orphan" in l for l in d["labels"]), d["labels"]   # rule and counts
    [audit] = [t for t in d["tables"] if t["name"] == "audit_log"]
    assert audit["finding"] and "no key" in audit["text"]                   # the open question is on the diagram
    assert sorted(set(view["decisions"])) == sorted(i["id"] for i in rv["items"])  # n218: Accept and Reject for each of the 13
    assert view["note"] == [data["note"]]
    said = {f["kind"]: f for f in view["figures"] if f["shown"]}
    assert said["onto"]["text"] == data["summary"] and said["thinker"]["text"] == data["attention"][0]
    assert said["builder"]["text"] == data["note"]
    assert not any(f["glad"] for f in view["figures"])                     # an open question: nobody is glad
    _no_json(view)


@needs_browser
def test_review_card_reads_every_shape(tmp_path, live_shop):
    args = {**SRC, "validate": True}
    answer = server.review_plan(**args)
    data = json.loads(answer)
    shapes = _shapes(answer)
    shapes["hosted_server"] = _call("review_plan", args)
    assert {k: v for k, v in shapes["hosted_server"]["structuredContent"].items() if k not in ("map", "kg_card", "checks", "next")} == data   # n170: + the map; n172: + the words
    for name, result in shapes.items():
        probe = _browse(tmp_path, "review_plan", args, result)
        _check_review(probe["before"], data)
        [call] = probe["calls"]                                               # the first decision button
        first = call["params"]["arguments"]["decisions"][0]["item"]
        assert call["params"]["name"] == "review_plan" and call["params"]["arguments"]["previous"] == data["review"], name
        # the host's answer to the decision, in the SDK's wrapper form: the card renders it again
        decided = server.review_plan(**SRC, previous=data["review"],
                                     decisions=[{"item": first, "review": "accepted"}])
        out = _browse(tmp_path, "review_plan", args, result,
                      reply={"content": [{"type": "text", "text": decided}], "structuredContent": {"result": decided}})
        after = out["after"]
        assert after["verdict"] == json.loads(decided)["summary"] and "1 accepted" in after["verdict"], name
        assert len(set(after["decisions"])) == 13                             # n218: every item keeps Accept / Reject
        assert after["call"][0].startswith("review_plan answered with 1 decision.")
        _no_json(after)
