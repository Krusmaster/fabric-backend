"""Round n218: Krusgraph's cards in Claude act, not just tell (founder, 11 November 2026: "It gives recommendations but I
cannot click on any suggestion. It is mostly text.").

Checked here, with the hosted server against the synthetic shop workspace (test_golden.fabric, seed.py's shop schema):
- every card's answer carries 2 to 4 next steps, each naming the tool it runs; none of them writes;
- the text answer leads with the result and lists the same next steps, the JSON answer unchanged after it;
- validate_plan's card gets every key and link as passed, failed or not checked with its counts, and for a failure the
  SQL that counts it; never a row value;
- in Chromium, under a fake host: a next-step button sends tools/call with exactly the step's tool and arguments; a host
  without serverTools gets the step's message with ui/message (the SDK's array form); Show the SQL reveals the
  statement; Accept / Reject then Re-plan sends one review_plan call with the decisions; Create writes only on a second
  click that names the item; the card makes no request of its own; buttons work from the keyboard;
- routing: "check shop" reads as validate_plan in the listing and the instructions, app_readiness on a name no API has
  asks which one is meant; list_tables shows every schema; plan_drift stops at its time limit and says what it did not read.
What this does not show: that Claude renders the cards or runs a card's tools/call. That is tried by hand after a deploy.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from fabric_backend import errors, lineage, mcp_apps, mcp_apps_build as build, mcp_apps_next as nxt, mcp_apps_review, server

from test_golden import SRC, fabric  # noqa: F401  (the hosted server against the synthetic shop workspace)

TESTS = Path(__file__).parent


def _registered(tool, /):
    fn = getattr(server, tool)
    if tool in build.ACTION_TOOLS:
        fn = build.with_actions(tool, fn, server._item_names, server._workspace_id_ctx)
    return mcp_apps.structured(fn, tool)


def _sc(tool, /, **kw):
    r = _registered(tool)(**kw)
    return r, r.structured_content


def _listing():
    return {t.name: t for t in asyncio.run(server.mcp.list_tools())}


def _row_values() -> set[str]:
    from fabric_backend import seed
    return {v for rows in seed.rows().values() for row in rows for v in row if isinstance(v, str) and len(v) > 3}


# ------------------------------------------------------------------ next steps and the lead ---------------------------

def test_the_plan_card_offers_check_doubled_totals_draft_and_review(fabric):
    r, d = _sc("plan_backend", **SRC)
    steps = d["next"]
    assert [s["label"] for s in steps] == ["Check against the rows", "Show the doubled totals", "Draft a semantic model",
                                           "Review keys and links"]
    assert [s["tool"] for s in steps] == ["validate_plan", "validate_plan", "semantic_model_draft", "review_plan"]
    assert steps[1]["arguments"]["detail"] == "full" and steps[2]["arguments"]["validate"] is True
    listing = _listing()
    for s in steps:
        assert {k: s["arguments"][k] for k in SRC} == SRC
        assert set(s["arguments"]) <= set(listing[s["tool"]].input_schema["properties"]), s
        assert listing[s["tool"]].annotations.read_only_hint is True, s                 # a next step never writes
        assert s["tool"] in s["say"] and s["label"] in s["say"]
    assert "next" not in json.loads(r.content[-1].text)                             # structuredContent only


def test_the_text_answer_leads_with_the_result_and_lists_the_same_next_steps(fabric):
    for tool, args in (("plan_backend", SRC), ("validate_plan", SRC), ("review_plan", {**SRC, "validate": True})):
        r, d = _sc(tool, **args)
        lead, full = r.content[0].text, r.content[-1].text
        assert len(r.content) == 2 and not lead.lstrip().startswith("{") and len(lead) < 1400, (tool, lead)
        plain, shown = json.loads(getattr(server, tool)(**args)), json.loads(full)
        assert {k: v for k, v in shown.items() if k in plain} == plain                # the JSON answer, unchanged
        first, _, rest = lead.partition("\n\n")
        assert first and "Next steps:" in rest
        for s in d["next"]:
            assert f"- {s['label']} ({s['tool']})" in lead, (tool, s)
        assert 2 <= len(d["next"]) <= 4
    v = _sc("validate_plan", **SRC)[0].content[0].text
    assert v.startswith("6 of 6 keys hold. 7 of 7 links hold, with no orphans.") and "\n\nNext steps:\n- " in v


def test_the_check_card_lists_every_key_and_link_with_counts_and_no_row_values(fabric):
    r, d = _sc("validate_plan", **SRC)
    c = d["checks"]
    assert c["counts"] == {"passed": 13, "failed": 1, "not_checked": 0}            # the shop repeats one header amount
    assert {x["kind"] for x in c["rows"]} == {"key", "link", "amount"} and len(c["rows"]) == 14
    [amount] = [x for x in c["rows"] if x["kind"] == "amount"]
    assert amount["state"] == "failed" and amount["counts"] == "repeated on every line: do not sum over the lines"
    links = [x for x in c["rows"] if x["kind"] == "link"]
    assert all(x["counts"].startswith("0 of ") and x["counts"].endswith(" point at nothing") for x in links)
    assert not any("sql" in x for x in c["rows"] if x["kind"] in ("key", "link"))   # SQL only for a failure
    shown = json.dumps(c)
    assert not [v for v in _row_values() if v in shown]
    assert "checks" not in json.loads(r.content[-1].text)


def test_a_failed_key_has_the_sql_that_counts_it_and_a_fix_step(fabric):
    r, d = _sc("validate_plan", **SRC, keys={"order_items": ["order_id"]})
    [bad] = [x for x in d["checks"]["rows"] if x["state"] == "failed" and x["kind"] == "key"]
    assert bad["id"] == "key:order_items" and bad["kind"] == "key" and "repeated" in bad["counts"]
    assert bad["sql"].startswith("SELECT COUNT_BIG(*) AS n") or bad["sql"].startswith("SELECT COUNT(*) AS n")
    assert "[order_items]" in bad["sql"] and "[order_id]" in bad["sql"]
    assert d["checks"]["rows"][0] == bad                                              # failures first
    assert d["next"][0]["label"] == "Propose a fix per failure" and d["next"][0]["arguments"]["fixes"] is True


def test_not_checked_when_the_budget_runs_out(fabric):
    r, d = _sc("validate_plan", **SRC, max_items=3)
    rows = [x for x in d["checks"]["rows"] if x["kind"] in ("key", "link")]
    assert sum(x["state"] == "not_checked" for x in rows) == 10 and sum(x["state"] == "passed" for x in rows) == 3
    assert all("budget" in x["counts"] for x in rows if x["state"] == "not_checked")


def test_a_question_back_gets_no_next_steps(fabric):
    assert nxt.steps("plan_backend", SRC, {"choose_schema": True, "schemas": []}) == []
    assert nxt.steps("validate_plan", SRC, {"error": "x"}) == []
    assert nxt.steps("validate_plan", {"workspace": "demo"}, {"summary": "x"}) == []


def test_with_the_flag_off_nothing_changes(fabric):
    assert isinstance(server.validate_plan(**SRC), str) and "next" not in json.loads(server.validate_plan(**SRC))
    assert mcp_apps.extensions(on=False) == [] and mcp_apps.registration("validate_plan", on=False) == {}


# ------------------------------------------------------------------ the cards in a browser ----------------------------

needs_browser = pytest.mark.skipif(not shutil.which("node") or subprocess.run(["node", "-e", "require('playwright')"],
                                                                              capture_output=True).returncode != 0,
                                   reason="node + playwright not available")


def _browse(tmp_path, card: str, data: dict) -> dict:
    (tmp_path / "card.html").write_text(card, encoding="utf-8")
    (tmp_path / "data.json").write_text(json.dumps(data), encoding="utf-8")
    run = subprocess.run(["node", str(TESTS / "mcp_apps_n218_browser.js"), str(tmp_path / "card.html"), str(tmp_path / "data.json")],
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout)
    assert out["errors"] == [] and out["requests"] == []                             # no request of its own (CSP)
    return out


def _result(r) -> dict:
    return {"content": [{"type": "text", "text": c.text} for c in r.content], "structuredContent": r.structured_content}


def _calls(out, method="tools/call"):
    return [m["params"] for m in out["log"] if m.get("method") == method]


@needs_browser
@pytest.mark.parametrize("card,tool", [("validate", "validate_plan"), ("build", "plan_backend"), ("review", "review_plan")])
def test_a_next_step_button_sends_its_tool_and_arguments(tmp_path, fabric, card, tool):
    args = {**SRC, "validate": True} if tool == "review_plan" else SRC
    r, d = _sc(tool, **args)
    html = {"validate": mcp_apps.card_html, "build": build.card_html, "review": mcp_apps_review.card_html}[card]()
    step = d["next"][0]
    out = _browse(tmp_path, html, {"args": args, "result": _result(r), "caps": {"serverTools": {}},
                                   "clicks": [{"css": f'.nx-b[data-tool="{step["tool"]}"]'}]})
    assert _calls(out) == [{"name": step["tool"], "arguments": step["arguments"]}]
    assert not _calls(out, "ui/message")
    for s in d["next"]:
        assert s["label"] in out["text"] and s["tool"] in out["text"]                # each button names its tool


@needs_browser
def test_without_server_tools_the_button_sends_the_exact_message(tmp_path, fabric):
    r, d = _sc("plan_backend", **SRC)
    step = d["next"][0]
    out = _browse(tmp_path, build.card_html(), {"args": SRC, "result": _result(r), "caps": {},
                                                "clicks": [{"css": '.nx-b[data-tool="validate_plan"]'}]})
    assert not _calls(out)
    assert _calls(out, "ui/message") == [{"role": "user", "content": [{"type": "text", "text": step["say"]}]}]
    assert f"Sent to the chat: “{step['say']}”" in out["text"]


@needs_browser
def test_a_host_that_refuses_both_shows_the_sentence_to_ask(tmp_path, fabric):
    r, d = _sc("plan_backend", **SRC)
    out = _browse(tmp_path, build.card_html(), {"args": SRC, "result": _result(r), "caps": {"refuseMessages": True},
                                                "clicks": [{"css": '.nx-b[data-tool="validate_plan"]'}]})
    assert "This host runs neither tools nor messages from the card. Ask in the chat: “" + d["next"][0]["say"] in out["text"]


@needs_browser
def test_the_check_card_shows_states_and_the_sql_on_request(tmp_path, fabric):
    args = {**SRC, "keys": {"order_items": ["order_id"]}}
    r, d = _sc("validate_plan", **args)
    out = _browse(tmp_path, mcp_apps.card_html(), {"args": args, "result": _result(r), "caps": {"serverTools": {}},
                                                   "clicks": [{"text": "Show the SQL that counts it"}], "scheme": "dark"})
    n = d["checks"]["counts"]
    assert out["pills"] == [[x["id"], x["state"].replace("_", " ")] for x in d["checks"]["rows"]]
    assert ["key:order_items", "failed"] in out["pills"]
    first_sql = next(x["sql"] for x in d["checks"]["rows"] if x.get("sql"))
    assert out["sql"] == [first_sql] and not _calls(out)                             # shown on the card, nothing run
    assert f"{n['failed']} failed" in out["text"] and f"{n['passed']} passed" in out["text"]


@needs_browser
def test_accept_and_reject_then_replan_sends_one_review_plan_call(tmp_path, fabric):
    args = {**SRC, "validate": True}
    r, d = _sc("review_plan", **args)
    rel = next(it["id"] for it in d["review"]["items"] if it["type"] == "relationship")
    out = _browse(tmp_path, mcp_apps_review.card_html(), {
        "args": args, "result": _result(r), "caps": {"serverTools": {}},
        "clicks": [{"css": f'button[data-item="key:customers"][data-review="accepted"]'},
                   {"css": f'button[data-item="{rel}"][data-review="rejected"]'},
                   {"css": "#replan"}]})
    assert "This link holds in the rows: 0 of " in out["text"] and " point at nothing." in out["text"]
    [call] = _calls(out)
    assert call["name"] == "review_plan" and call["arguments"]["previous"] == d["review"]
    assert call["arguments"]["decisions"] == [{"item": "key:customers", "review": "accepted"}, {"item": rel, "review": "rejected"}]
    assert {k: call["arguments"][k] for k in SRC} == SRC


@needs_browser
def test_accept_works_from_the_keyboard_and_replan_falls_back_to_the_chat(tmp_path, fabric):
    args = {**SRC, "validate": True}
    r, d = _sc("review_plan", **args)
    out = _browse(tmp_path, mcp_apps_review.card_html(), {
        "args": args, "result": _result(r), "caps": {},
        "clicks": [{"css": 'button[data-item="key:orders"][data-review="accepted"]', "key": "Enter"},
                   {"css": "#replan", "key": "Space"}]})
    assert "key:orders:accepted" in out["pressed"] and not _calls(out)
    [msg] = _calls(out, "ui/message")
    assert msg["content"][0]["text"].startswith("Re-plan shop with my decisions using review_plan: accept key:orders.")


@needs_browser
def test_create_writes_only_on_the_second_click_with_the_name(tmp_path, fabric):
    r, d = _sc("create_semantic_model", **SRC, name="shop_model_2", dry_run=True)
    args = {**SRC, "name": "shop_model_2", "dry_run": True}
    out = _browse(tmp_path, build.card_html(), {"args": args, "result": _result(r), "caps": {"serverTools": {}},
                                                "clicks": [{"css": "button.act-create"}]})
    assert not _calls(out) and "Yes, create shop_model_2 in Fabric" in out["text"] and "Nothing has been created yet." in out["text"]
    out = _browse(tmp_path, build.card_html(), {"args": args, "result": _result(r), "caps": {"serverTools": {}},
                                                "clicks": [{"css": "button.act-create"}, {"css": "button.act-create"}]})
    assert _calls(out) == [{"name": "create_semantic_model", "arguments": {**args, "dry_run": False}}]


def test_the_cards_load_nothing_and_declare_no_domain():
    for html in (mcp_apps.card_html(), build.card_html(), mcp_apps_review.card_html()):
        low = html.lower()
        for banned in ("fetch(", "xmlhttprequest", "websocket", "@import", "url(", "localstorage", "innerhtml"):
            assert banned not in low, banned
        assert "prefers-color-scheme" in low or "light-dark(" in low                  # light and dark
        assert ":focus-visible" in low                                                  # keyboard focus is visible
    assert "csp" not in json.dumps(build.tool_meta(on=True)) and "csp" not in json.dumps(mcp_apps.tool_meta(on=True))


# ------------------------------------------------------------------ routing ------------------------------------------

def test_check_shop_reads_as_validate_plan_not_app_readiness():
    listing = _listing()
    v, a = listing["validate_plan"], listing["app_readiness"]
    assert "keys and links" in v.title and '"check shop"' in v.description and "run a check" in v.description
    assert "validate_plan" in a.description and "Only for an API the user names" in a.description
    ins = server.mcp.instructions
    assert '"check shop"' in ins and "not app_readiness" in ins and "ask which" in ins


def test_app_readiness_on_a_word_no_api_has_asks_which_one(fabric):
    out = json.loads(server.app_readiness(workspace="demo", api="shop"))
    assert "error" not in out and out["ask"].startswith("Which 'shop' do you mean?")
    tools = {(c["tool"], c.get("api") or c.get("source")) for c in out["choices"]}
    assert ("app_readiness", "shop_api") in tools and ("validate_plan", "demo_lh") in tools
    assert all(c["schema"] == "shop" for c in out["choices"] if c["tool"] == "validate_plan")
    assert json.loads(server.app_readiness(workspace="demo", api="nothing_like_it"))["kind"] == "not_found"


def test_list_tables_shows_every_schema(fabric, monkeypatch):
    monkeypatch.setattr(server, "_source_schemas", lambda w, s, c: [{"schema": "sap", "tables": 4}, {"schema": "shop", "tables": 7}])
    out = json.loads(server.list_tables(**SRC))
    assert out["schemas"] == [{"schema": "sap", "tables": 4}, {"schema": "shop", "tables": 7}]
    empty = json.loads(server.list_tables(workspace="demo", source="demo_lh"))           # dbo has no tables
    assert empty["choose_schema"] is True and [s["schema"] for s in empty["schemas"]] == ["sap", "shop"]
    assert "Which one should be listed?" in empty["summary"] and "list_tables" in empty["hint"]


# ------------------------------------------------------------------ plan_drift's time limit ----------------------------

def test_a_reader_after_the_deadline_is_refused_once_and_said_as_the_time_limit():
    calls = []
    read = server._before(time.monotonic() - 1, lambda *a: calls.append(a))
    with pytest.raises(errors.TimeLimit):
        read("x")
    assert calls == [] and errors.explain(errors.TimeLimit("t"), "x")["kind"] == "time_limit"
    assert "time_limit" in lineage._FINAL                                              # never retried after a pause
    t0 = time.monotonic()
    with pytest.raises(errors.TimeLimit):
        lineage._read(lambda: read("y"), "y")
    assert time.monotonic() - t0 < lineage.RETRY_PAUSE


def test_plan_drift_returns_what_it_read_when_the_time_limit_is_reached(fabric, monkeypatch):
    monkeypatch.setattr(server, "DRIFT_SECONDS", -1)                                    # the deadline has passed
    real = server._drift.compare

    def compare(*a, **k):
        out = real(*a, **k)
        out["tables_gone"] = [{"table": "orders"}]                                    # a change, so lineage is read
        return out
    monkeypatch.setattr(server._drift, "compare", compare)
    out = json.loads(server.plan_drift(**SRC, api="shop_api"))
    assert "error" not in out and out["time_limit"]["seconds"] == -1 and out["time_limit"]["not_read"]
    assert out["time_limit"]["said"].startswith("Stopped after") and "impact" in out
