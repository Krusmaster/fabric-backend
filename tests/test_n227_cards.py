"""Round n227: the MCP Apps chat cards after the founder's test in claude.ai on 12 November 2026 (deploy
src-37ff21adce4ff691). docs/MCP-APPS-N227.md says what was seen and what changed, point by point (1 to 13).

Checked here, with the hosted server against the synthetic shop workspace (test_golden.fabric, seed.py's shop schema):
- every hosted tool's answer gets a `kg_card` whose `result` is one plain line, with at most five lines after it and
  the repeated notes collapsed; none of them names a tool, and numbers agree with their nouns;
- before the check a plan offers one primary step (Check against the rows) and no build; the builds come after a
  check whose keys hold; a suggested name that ends in _2 or _3 says why;
- the schema choice never offers krusgraph_quarantine, and no silver or gold layer while a source schema is there;
- "Open in Fabric" is the item's own address for each kind a card creates;
- a create that Fabric has not finished in time answers `started`; `check` on the same tool reads how it went and sends
  nothing; the same definition is not sent a second time while the first one's outcome is unknown;
- the text lead is a numbered list in plain words ("Reply 1, 2 or 3"), with the calls only in a paragraph for the model;
- the servers' instructions ask the model not to repeat a card nor to add what the tool did not say, without threats;
- in Chromium at 375 px, under a fake host: no card scrolls sideways; a sentence the mascot says is not on the card a
  second time; no button or status line names a tool; a running step shows who works on what and for how long, without
  motion when the user asked for less; Create is never sent twice (also when the host stops waiting); a created
  ontology is drawn; details are readable lines first and the raw JSON behind a second toggle.
What this does not show: that Claude renders the cards, runs a card's tools/call, or how long the host waits; that the
item addresses open the item in the Fabric portal (the ontology's form is from Microsoft Learn; the API for GraphQL's
is not confirmed there). Those are tried by hand after a deploy.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

import fabric_backend.deploy  # noqa: F401  (the module; `fabric_backend.deploy` by attribute is the function)
from fabric_backend import (mcp_apps, mcp_apps_build as build, mcp_apps_next as nxt, mcp_apps_result as result,
                            mcp_apps_review, mcp_apps_start, mcp_apps_words as words, mcp_server, server, start_flow)

import golden_support as gs
from test_golden import SRC, fabric  # noqa: F401  (the hosted server against the synthetic shop workspace)

TESTS = Path(__file__).parent
GOLDEN = json.loads((TESTS / "golden" / "hosted_tools.json").read_text(encoding="utf-8"))
OP = "0f9a3c1e-6b1d-4a52-9c0e-5d2b7a1f4e88"
deploy = sys.modules["fabric_backend.deploy"]


def _registered(tool, /):
    fn = getattr(server, tool)
    if tool in build.ACTION_TOOLS:
        fn = build.with_actions(tool, fn, server._item_names, server._workspace_id_ctx)
    return mcp_apps.structured(fn, tool)


def _sc(tool, /, **kw):
    r = _registered(tool)(**kw)
    return r, r.structured_content


def _said(card: dict) -> str:
    """Everything a kg_card puts in front of a person."""
    notes = card.get("notes") or []
    return " ".join([card.get("result", ""), card.get("onto", ""), card.get("thinker", ""), card.get("builder", "")]
                    + list(card.get("lines") or []) + [n["line"] for n in notes] + [i for n in notes for i in n["items"]])


# ------------------------------------------------------------------ 3, 4, 13: every tool's words ----------------------

def test_every_hosted_tool_gets_one_plain_line_and_at_most_five_more():
    seen = set()
    for entry in GOLDEN:
        tool, answer = entry.get("tool"), entry.get("answer")
        if not isinstance(answer, dict):
            continue
        card = words.card(tool, answer, {}, entry.get("args") or {})
        if answer.get("error"):
            assert card is None, tool                     # the card shows the error itself, with its next steps
            continue
        seen.add(tool)
        assert card and (card.get("result") or card.get("lines") or card.get("thinker")), tool
        if not answer.get("choose_schema"):
            assert card.get("result") or card.get("lines"), tool
        assert len(card.get("lines") or []) <= words.LINES_MAX, tool
        said = _said(card)
        assert not words.TOOL_NAME.search(said), (tool, words.TOOL_NAME.search(said).group(0), said)
        assert "(s)" not in said and "(ies)" not in said and "no summary" not in said, (tool, said)
        assert not re.search(r"\b1 (tables|rows|links|keys|columns|relationships|measures|schemas|views|queries)\b", said), (tool, said)
        assert not words.WORDS_WITH_ARGUMENTS.search(card.get("result", "")), (tool, card["result"])
    assert len(seen) >= 30                                   # the golden file calls nearly every hosted tool


def test_the_tool_names_the_words_look_for_are_the_servers_own():
    import asyncio
    listed = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {n for n in listed if "_" in n} <= set(words.TOOLS_NAMED)
    assert words.plain("products.list_price is not summed over order_items") == "products.list_price is not summed over order_items"
    assert "validate_plan" not in words.plain("counts from validate_plan; nothing sent")


def test_numbers_agree_with_their_nouns_and_no_label_is_doubled():
    assert words.agree("R5 counted 1 code or role column(s) in the rows: 1 counting query(ies), at most 200 distinct values") == \
        "R5 counted 1 code or role column in the rows: 1 counting query, at most 200 distinct values"
    assert words.agree("2 counting query(ies); 3 view(s); 0 candidate(s)") == "2 counting queries; 3 views; 0 candidates"
    assert words.agree("krusgraph (1 tables)") == "krusgraph (1 table)" and words.agree("1 rows, 0 empty") == "1 row, 0 empty"
    assert words.agree("11 tables, 21 rows") == "11 tables, 21 rows"
    assert words.undoubled("Total NETWR (sap_vbrk) (sap_vbrk)") == "Total NETWR (sap_vbrk)"
    assert words.labelled("Total NETWR (sap_vbrk)", "sap_vbrk") == "Total NETWR (sap_vbrk)"
    assert words.labelled("Total quantity", "order_items") == "Total quantity (order_items)"
    choice = server._schema_choice("demo_lh", [{"schema": "krusgraph", "tables": 1}])
    assert "1 schema with tables: krusgraph (1 table)." in choice["summary"]
    acts, _ = build.actions_for("plan_backend", {"workspace": "demo", "source": "demo_lh"},
                                {"choose_schema": True, "schemas": [{"schema": "shop", "tables": 7}, {"schema": "one", "tables": 1}]})
    assert [a["label"] for a in acts] == ["Plan shop (7 tables)", "Plan one (1 table)"]


def test_the_checks_rows_say_one_row_and_explain_nothing_twice(fabric):
    _, d = _sc("validate_plan", **SRC)
    counts = [r["counts"] for r in d["checks"]["rows"]]
    assert counts and not any(re.search(r"\b1 rows\b", c) for c in counts)
    one = nxt.check_rows.__globals__["words"]._plural(1, "row")
    assert one == "1 row"


def test_repeated_notes_become_one_line_with_the_list_behind_it():
    links = [{"source": f"sap_vbap_{i}", "columns": ["mandt", "vbeln"], "target": "sap_vbak", "target_columns": ["mandt", "vbeln"],
              "why": "the target's key has two columns"} for i in range(24)]
    summary = {"tables": 10, "roles": {f"t{i}": "fact" if i < 3 else "dimension" for i in range(10)}, "relationships_active": 0,
               "relationships_inactive": 0, "relationships_not_expressible": 24, "not_expressible": links, "measures": [
                   {"name": "Total NETWR (sap_vbrk)", "table": "sap_vbrk"}], "keyless": [], "composite_keys": [], "inactive": []}
    card = words.card("semantic_model_draft", {"summary": summary}, {}, {})
    assert card["result"] == "A semantic model draft: nothing was created."
    note = [n for n in card["notes"] if "combined key column" in n["line"]]
    assert [n["line"] for n in note] == ["24 links need a combined key column; Krusgraph can add them in a gold view."]
    assert len(note[0]["items"]) == 24 and "Not expressible" not in _said(card)
    assert "1 measure: Total NETWR (sap_vbrk)." in card["lines"]
    one = words.card("semantic_model_draft", {"summary": {**summary, "not_expressible": links[:1]}}, {}, {})
    assert "1 link needs a combined key column; Krusgraph can add it in a gold view." in [n["line"] for n in one["notes"]]


def test_the_five_summaries_share_one_form(fabric):
    forms = {}
    for tool, kw in (("semantic_model_draft", SRC), ("ontology_draft", SRC),
                     ("create_backend", {**SRC, "name": "shop_api_v2"}), ("create_semantic_model", {**SRC, "name": "shop_model_v2"}),
                     ("create_ontology", {**SRC, "name": "shop_onto"})):
        _, d = _sc(tool, **kw)
        c = d[words.KEY]
        forms[tool] = c
        assert isinstance(c["result"], str) and c["result"].endswith(".") and "\n" not in c["result"], tool
        assert 1 <= len(c["lines"]) <= 5 and all(isinstance(x, str) for x in c["lines"]), tool
        assert all(set(n) <= {"line", "items", "more"} for n in c.get("notes") or []), tool
        assert c["onto"] == c["result"], tool                 # Onto says the result, once
    assert forms["create_backend"]["result"] == "Dry run of shop_api_v2: nothing was created. It would be new."
    assert forms["ontology_draft"]["lines"][:2] == ["7 entity types, 5 with a key.", "7 relationship types."]
    said = [n["line"] for n in forms["ontology_draft"]["notes"]]
    assert said == ["1 entity type has no key, so nothing can point at it. You can set a key in Fabric if the table has one.",
                    "1 entity type has a key of several columns. An ontology key is one column, so it is kept without a key, "
                    "with the key columns as properties."]
    assert forms["ontology_draft"]["notes"][1]["items"] == ["OrderItems: order_id + line_no"]


def test_a_created_item_is_named_and_the_plan_is_not_repeated(fabric):
    r, d = _sc("create_backend", **SRC, name="shop_api_v2", dry_run=False)
    c = d[words.KEY]
    assert c["result"] == "Created shop_api_v2, an API for GraphQL, in Fabric."
    assert c["lines"][0].startswith("Endpoint: https://api.fabric.microsoft.com/v1/workspaces/")
    assert "7 tables" not in _said(c) and "R5 counted" not in _said(c)
    assert r.content[0].text.startswith("Created shop_api_v2, an API for GraphQL, in Fabric.")
    _, m = _sc("create_semantic_model", **SRC, name="shop_model_v2", dry_run=False)
    assert m[words.KEY]["result"] == "Created shop_model_v2, a semantic model, in Fabric."


def test_every_tool_answers_with_its_words_when_the_flag_is_on_and_as_before_when_off(fabric):
    assert mcp_apps.registration("list_workspaces", on=True) == {"structured_output": False}
    assert mcp_apps.registration("list_workspaces", on=False) == {} and mcp_apps.registration("validate_plan", on=False) == {}
    r = mcp_apps.structured(server.list_workspaces, "list_workspaces")()
    assert r.structured_content[words.KEY]["result"] == "1 workspace: demo."
    # CO1: the Coach block for the host model comes first, the JSON answer last, unchanged
    assert len(r.content) == 2 and r.content[0].text.startswith("Coach (step 1 of 9: Choose data)")
    assert json.loads(r.content[-1].text) == {k: v for k, v in r.structured_content.items() if k not in (words.KEY, "coach")}
    assert "next" not in r.structured_content                     # a card that ran it draws the words; nothing else is added
    s = mcp_apps.structured(server.list_sources, "list_sources")(workspace="demo")
    assert s.structured_content[words.KEY]["result"] == "2 sources: demo_lh (Lakehouse) and demo_wh (Warehouse)."


# ------------------------------------------------------------------ 5, 12: what is offered, and when -------------------

def test_before_the_check_a_plan_leads_with_one_primary_step_and_no_build(fabric):
    r, d = _sc("plan_backend", **SRC)
    acts = d["actions"]
    assert [(a["kind"], a["tool"], a.get("primary")) for a in acts] == [("call", "validate_plan", True)]
    assert acts[0]["label"] == "Check against the rows" and acts[0]["ask"] == "Check against the rows for shop."
    assert "offered after the check" in d["actions_note"]
    assert not any(s["tool"].startswith(("create_", "semantic_model")) or s["label"] == "Check against the rows" for s in d["next"])
    assert d[words.KEY]["builder"] == words.BUILDER_AFTER_CHECK
    assert gs.WS and not any(m == "GET" and p.endswith("/items") for m, p in fabric.calls[-1:])   # no name lookup for a plan


def test_the_builds_come_after_a_check_whose_keys_hold(fabric):
    _, d = _sc("validate_plan", **SRC)
    kinds = [(a["kind"], a["tool"]) for a in d["actions"]]
    assert kinds == [("dry_run", "create_semantic_model"), ("dry_run", "create_ontology"), ("dry_run", "create_backend")]
    args = {"workspace": "demo", "source": "demo_lh", "schema": "shop"}
    failed = {"totals": {"keys": {"checked": 6, "passed": 5, "failed": 1}, "relationships": {"checked": 7, "passed": 7, "failed": 0}}}
    acts, note = build.actions_for("validate_plan", args, failed, taken=set())
    assert acts == [] and note.startswith("1 key does not hold in the rows, so no build is offered here")
    links = {"totals": {"keys": {"checked": 17, "passed": 17, "failed": 0}, "relationships": {"checked": 34, "passed": 32, "failed": 2}}}
    acts, note = build.actions_for("validate_plan", args, links, taken=set())
    assert len(acts) == 3 and note.startswith("The keys hold. 2 links have rows that point at nothing")
    steps = nxt.steps("validate_plan", args, failed)
    assert "Draft a semantic model" not in [s["label"] for s in steps]


def test_a_name_that_ends_in_3_says_why():
    args = {"workspace": "demo", "source": "demo_lh", "schema": "shop"}
    ok = {"totals": {"keys": {"checked": 6, "passed": 6, "failed": 0}}}
    acts, _ = build.actions_for("validate_plan", args, ok, taken={"shop_model", "Shop_Model_2", "shop_api"})
    by = {a["tool"]: a for a in acts}
    assert by["create_semantic_model"]["name"] == "shop_model_3"
    assert by["create_semantic_model"]["name_why"] == ("Named shop_model_3 because shop_model and shop_model_2 are already in "
                                                       "this workspace; nothing that exists is changed.")
    assert by["create_backend"]["name"] == "shop_api_2" and "because shop_api is already in this workspace" in by["create_backend"]["name_why"]
    assert by["create_ontology"]["name"] == "shop_ontology" and "name_why" not in by["create_ontology"]
    assert build.name_why("shop_model", "shop_model", {"x"}) is None


def test_the_schema_choice_never_offers_what_krusgraph_wrote():
    found = [{"schema": "dbo", "tables": 12}, {"schema": "gold", "tables": 3}, {"schema": "krusgraph_quarantine", "tables": 1},
             {"schema": "silver", "tables": 8}]
    assert [s["schema"] for s in server._candidate_schemas(found)] == ["dbo", "gold", "silver"]
    assert [s["schema"] for s in build.plannable(found)] == ["dbo"]
    assert [s["schema"] for s in build.plannable(found[1:])] == ["gold", "silver"]          # nothing else to plan: they stay
    acts, _ = build.actions_for("plan_backend", {"workspace": "demo", "source": "demo_lh"}, {"choose_schema": True, "schemas": found})
    assert [a["label"] for a in acts] == ["Plan dbo (12 tables)"]
    only = server._candidate_schemas([{"schema": "dbo", "tables": 12}, {"schema": "Krusgraph_Quarantine", "tables": 1}])
    assert [s["schema"] for s in only] == ["dbo"]                                             # one left: planned at once


# ------------------------------------------------------------------ 8: the item itself ---------------------------------

@pytest.mark.parametrize("tool,path", [("create_report", "reports/it-1"), ("create_semantic_model", "datasets/it-1/details"),
                                       ("create_ontology", "ontologies/it-1"), ("create_backend", "graphql/it-1")])
def test_open_in_fabric_is_the_items_own_address_for_every_kind(tool, path):
    assert build.open_url(gs.WS, tool, "it-1") == f"https://app.fabric.microsoft.com/groups/{gs.WS}/{path}"
    args = {"workspace": "demo", "source": "demo_lh", "schema": "shop", "name": "shop_x", "dry_run": False}
    acts, _ = build.actions_for(tool, args, {"dry_run": False, "result": {"status": "Succeeded", "id": "it-1"}}, taken=set(), workspace_id=gs.WS)
    link = acts[0]
    assert link["kind"] == "link" and link["label"] == "Open shop_x in Fabric" and link["url"].endswith("/" + path)
    assert not link["url"].endswith("/list")
    assert ("fallback" in link) == (tool in build.LINK_UNVERIFIED)       # an address not confirmed on Learn names the list too
    if "fallback" in link:
        assert link["fallback"] == f"https://app.fabric.microsoft.com/groups/{gs.WS}/list"
    assert set(build.ITEM_PATHS) == set(build.BUILD_TOOLS)


def test_a_kind_without_a_path_opens_the_list():
    assert build.open_url(gs.WS, "create_pipeline", "x") == build.list_url(gs.WS)


# ------------------------------------------------------------------ 9: a create that answers in time -------------------

def test_a_wait_inside_answer_by_ends_at_the_deadline():
    assert deploy._budget_seconds(3, 60, None) == 180
    with deploy.answer_by(time.monotonic() + 12):
        assert 11 < deploy._budget_seconds(3, 60, None) <= 12
        assert deploy._budget_seconds(3, 60, 5) == 5
    with deploy.answer_by(time.monotonic() - 100):
        assert deploy._budget_seconds(3, 60, None) == deploy.MIN_WAIT_SECONDS
    assert deploy._budget_seconds(3, 60, None) == 180
    assert server.CREATE_ANSWER_SECONDS < 60


def test_a_create_fabric_has_not_finished_answers_started_and_is_not_sent_twice(fabric, monkeypatch):
    sent = []

    def slow(env, ws, **k):
        sent.append(env["displayName"])
        return {"status": "Timeout", "mode": "created", "operation": OP, "note": deploy.WAIT_STOPPED.format(op=OP)}
    monkeypatch.setattr(server, "deploy", slow)
    server._RECENT.clear()
    r, d = _sc("create_backend", **SRC, name="shop_api_v2", dry_run=False)
    assert d["kind"] == "timeout" and d["started"] == {"name": "shop_api_v2", "operation": OP, "check": OP,
                                                       "note": deploy.WAIT_STOPPED.format(op=OP)}
    assert "Do not run the create again" in d["hint"] and f"check='{OP}'" in d["hint"]
    assert [(a["kind"], a["tool"], a["arguments"].get("check"), "dry_run" in a["arguments"]) for a in d["actions"]] == \
        [("status", "create_backend", OP, False)]
    assert d.get("next") in (None, [])                                          # no "Try again"
    c = d[words.KEY]
    assert c["result"] == "Fabric is still working on shop_api_v2. Nothing needs to be sent again; check its status in a moment."
    assert r.content[0].text.startswith(c["result"]) and "1. Check status" in r.content[0].text
    again = json.loads(server.create_backend(**SRC, name="shop_api_v2", dry_run=False))
    assert sent == ["shop_api_v2"] and "nothing was sent again" in again["not_sent_again"] and again["started"]["check"] == OP
    server._RECENT.clear()


def test_check_reads_how_a_started_create_went_and_sends_nothing(fabric, monkeypatch):
    import requests
    real_get, state = requests.get, {"status": "Running"}

    def get(url, **kw):
        if "/v1/operations/" in url:
            fabric.calls.append(("GET", "/v1/operations/" + url.rsplit("/", 1)[-1]))
            return gs.Response(200, dict(state))
        return real_get(url, **kw)
    monkeypatch.setattr(requests, "get", get)
    before = len(fabric.created)
    running = json.loads(server.create_backend(**SRC, name="shop_api_v2", check=OP))
    assert running["checked"] is True and running["started"]["check"] == OP and "the operation is Running" in running["error"]
    state.update({"status": "Failed", "error": {"errorCode": "InvalidDefinition", "message": "bad part"}})
    failed = json.loads(server.create_backend(**SRC, name="shop_api_v2", check=OP))
    assert failed["kind"] == "fabric_error" and "bad part" in failed["error"] and "started" not in failed
    missing = json.loads(server.create_backend(**SRC, name="shop_api_v2", check="name"))
    assert "is in the workspace yet" in missing["error"] and missing["started"]["check"] == "name"
    state.clear(); state.update({"status": "Succeeded"})
    r, there = _sc("create_backend", **SRC, name="shop_api", check=OP, dry_run=False)        # an item of that name and kind exists
    assert there["checked"] is True and there["result"]["status"] == "Succeeded" and "error" not in there
    assert there[words.KEY]["result"] == "shop_api is in Fabric now: an API for GraphQL."
    assert [a["kind"] for a in there["actions"]] == ["link"] and "/graphql/" in there["actions"][0]["url"]
    assert len(fabric.created) == before                                                     # nothing was written by any of them
    assert not [c for c in fabric.calls if c[0] == "POST" and "getDefinition" not in c[1] and "/graphql" not in c[1].lower()]
    for tool, kw in (("create_semantic_model", {**SRC, "name": "ghost"}), ("create_ontology", {**SRC, "name": "ghost"}),
                     ("create_report", {"workspace": "demo", "model": "shop_model", "name": "ghost"})):
        out = json.loads(getattr(server, tool)(**kw, check="name", dry_run=False))
        assert out["checked"] is True and out["started"]["check"] == "name", tool
    assert len(fabric.created) == before


def test_the_other_three_creates_answer_started_too(fabric, monkeypatch):
    slow = {"status": "Timeout", "mode": "created", "operation": OP}
    monkeypatch.setattr(server, "_create_semantic_model", lambda body, ws, token_provider=None: dict(slow))
    monkeypatch.setattr(server, "_create_ontology", lambda body, ws, token_provider=None: dict(slow))
    server._RECENT.clear()
    for tool, name in (("create_semantic_model", "shop_model_v2"), ("create_ontology", "shop_onto")):
        _, d = _sc(tool, **SRC, name=name, dry_run=False)
        assert d["started"]["check"] == OP and d["kind"] == "timeout", tool
        assert [a["kind"] for a in d["actions"]] == ["status"], tool
        assert "ontology" not in d                                   # no picture of something Fabric has not made yet
    server._RECENT.clear()


def test_the_listing_gains_check_on_the_four_creates_only():
    import asyncio
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    with_check = sorted(n for n, t in tools.items() if "creates nothing" in t.input_schema["properties"].get("check", {}).get("description", ""))
    assert with_check == sorted(server.CARD_ITEM_TYPES)
    for n in with_check:
        p = tools[n].input_schema["properties"]["check"]
        assert p["default"] == "" and "check" not in tools[n].input_schema.get("required", [])


# ------------------------------------------------------------------ 10: the ontology after Create ----------------------

def test_a_created_ontology_carries_its_picture_and_its_notes_in_plain_words(fabric):
    _, d = _sc("create_ontology", **SRC, name="shop_onto", dry_run=False)
    assert d["result"]["status"] == "Succeeded"
    onto = d["ontology"]
    by = {e["name"]: e for e in onto["entities"]}
    assert by["Orders"]["key"] and not by["AuditLog"]["key"] and by["OrderItems"]["key_columns"] == ["order_id", "line_no"]
    assert all(l["name"] for l in onto["links"]) and len(onto["links"]) == 7
    c = d[words.KEY]
    assert c["result"] == "Created shop_onto, an ontology, in Fabric." and c["title"] == "Ontology: created"
    assert not any("rule K3" in n["line"] or "emitted" in n["line"] for n in c["notes"])


# ------------------------------------------------------------------ 7: the text a client without cards shows ----------

def test_the_text_lead_is_a_numbered_list_in_plain_words(fabric):
    r, d = _sc("plan_backend", **SRC)
    lead = r.content[0].text
    user, model = lead.split("For the assistant, not for the user:")
    assert "Next steps:\n1. Check against the rows\n2. Show the doubled totals\n3. Review keys and links\nReply 1, 2 or 3." in user
    assert not words.TOOL_NAME.search(user) and "run " not in user
    assert "1 = validate_plan" in model and "2 = validate_plan (detail='full')" in model and "3 = review_plan" in model
    assert nxt.AFTER_CARD in model and lead.endswith("The full answer follows as JSON.")
    assert json.loads(r.content[1].text)["relationships"]                # the JSON answer follows, unchanged
    r2, _ = _sc("validate_plan", **SRC)
    user2 = r2.content[0].text.split("For the assistant")[0]
    # WB13 (#91): the most useful step first (the shop's one open link), then the builds, then the doubled totals
    assert ("1. Decide the 1 open link\n2. Build a semantic model (shop_model_2)\n3. Create an ontology (shop_ontology)" in user2
            and "5. Use the line amounts\nReply 1, 2, 3, 4 or 5." in user2)
    assert not words.TOOL_NAME.search(user2)
    one = nxt.lead("create_backend", {"kg_card": {"result": "Fabric is still working on x."}, "started": {}}, [],
                   [{"kind": "status", "label": "Check status", "tool": "create_backend", "arguments": {"check": "name"}}])
    assert "1. Check status\nReply 1." in one and "1 = create_backend (check='name')" in one


# ------------------------------------------------------------------ 6: what the model is asked ------------------------

COERCIVE = re.compile(r"\b(must|never|always|forbidden|important|critical|do not ever|under no circumstances|you will)\b", re.I)


def test_the_instructions_ask_for_no_repeat_and_no_added_claim_without_threats():
    import asyncio
    hosted = server.mcp.instructions
    assert nxt.AFTER_RESULT in hosted
    for text in (nxt.AFTER_RESULT, nxt.AFTER_CARD):
        assert not COERCIVE.search(text), COERCIVE.search(text)
        assert "no need to repeat" in text or "repeating them is not needed" in text
        assert "add no reason, source or name" in text and "please" in text.lower()
    assert "the SAP pack is Krusgraph's list of known SAP keys and links" in hosted
    assert "come from public sources" not in hosted                      # what Claude turned into "SAP's own documentation"
    assert "do not send it again" in hosted and "check set reads how it went" in hosted
    assert "add no reason, source or name that is not in it" in mcp_server.INSTRUCTIONS
    assert asyncio.run(server.mcp.list_tools())                          # the server still lists its tools


def test_sap_pack_is_explained_the_first_time_it_appears():
    assert words.SAP_PACK == "SAP pack: Krusgraph's list of known SAP keys"
    facts = {"tables": 12, "keyed": 12, "keyless": [], "links": 9, "by_name": 2, "from_values": [], "confirmed": 0, "ambiguous": 0,
             "failed": [], "dropped": True, "budget": 0, "unsupported": 0, "sap": True, "sap_keys": 10}
    lines = words.plan_lines(facts)
    assert "9 links: 2 by name, 7 from the SAP pack." in lines and lines.count(words.SAP_PACK + ".") == 1
    assert words.SAP_PACK + "." not in words.plan_lines({**facts, "sap": False, "sap_keys": 0})
    for html in (mcp_apps.card_html(), build.card_html(), mcp_apps_start.card_html(), mcp_apps_review.card_html()):
        assert "sapNote(" in html and json.dumps(words.SAP_PACK) in html


# ------------------------------------------------------------------ 1, 2: the Start path's words ----------------------

def test_the_start_path_names_no_tool_in_what_a_person_reads():
    for sample in (False, True):
        for step in start_flow.KEYS:
            g = start_flow.guide(sample=True, step=step) if sample else start_flow.guide(workspace="demo", source="demo_lh", schema="shop", step=step)
            said = " ".join([g.get("say", ""), g["honest"]] + [a["label"] + " " + a.get("ask", "") for a in g["actions"]]
                            + ([g["after"]["label"] + " " + g["after"]["ask"]] if g.get("after") else []))
            assert not words.TOOL_NAME.search(said), (step, words.TOOL_NAME.search(said).group(0))
            assert all(a.get("ask") for a in g["actions"] if a.get("tool")), step
    first = start_flow.guide()
    assert first["say"] == "Hi! Which workspace shall we start in?"                  # WB15: one short sentence
    card = words.card("start", first, {}, {})
    assert card == {"title": "Start Krusgraph", "result": first["say"], "onto": first["say"]}
    lost = start_flow.guide(workspace="demo", source="demo_lh", schema="shop", step="bogus")       # F1 B13: the place is kept
    assert lost["step"]["key"] == "map" and lost["unknown_step"]["asked"] == "bogus" and lost["say"].startswith("I don't know a step called “bogus”")
    assert "would already propose that link (rule R5)" in start_flow.guide(sample=True)["found"]["note"]   # F1 B4
    confirm = start_flow.guide(workspace="demo", source="demo_lh", schema="shop", step="create")
    assert "call start" not in confirm["say"] and 'call start with step="create"' in confirm["then"]


def test_no_card_names_a_tool_in_its_own_sentences():
    for html in (mcp_apps.card_html(), build.card_html(), mcp_apps_start.card_html()):
        body = re.sub(r"<script>.*</script>", "", html, flags=re.S)
        assert not words.TOOL_NAME.search(body), words.TOOL_NAME.search(body)
        for line in ("Asked the host to run", "no summary in it", '"Run " + s.tool', "nx-tool", "tool + \" answered"):
            assert line not in html, line
        assert "Show the raw answer (JSON)" in html and "prefers-reduced-motion: reduce" in html and "wait-dots" in html
        assert "@keyframes" not in html and "animation:" not in html.replace("animation: none !important", "")
    assert json.loads(re.search(r"var STEP_LABEL = (\{.*?\});", mcp_apps.card_html()).group(1))["semantic_model_draft"] == "Draft a semantic model"


# ------------------------------------------------------------------ the cards in a browser, at 375 px -----------------

needs_browser = pytest.mark.skipif(not shutil.which("node") or subprocess.run(["node", "-e", "require('playwright')"],
                                                                              capture_output=True).returncode != 0,
                                   reason="node + playwright not available")
CAPS = {"serverTools": {}, "openLinks": {}}
TOOLS_SHOWN = re.compile(r"\b(?:" + "|".join(sorted((t for t in words.TOOLS_NAMED), key=len, reverse=True)) + r")\b")


def _browse(tmp_path, card: str, data: dict) -> dict:
    (tmp_path / "card.html").write_text(card, encoding="utf-8")
    (tmp_path / "data.json").write_text(json.dumps(data), encoding="utf-8")
    run = subprocess.run(["node", str(TESTS / "mcp_apps_n227_browser.js"), str(tmp_path / "card.html"), str(tmp_path / "data.json")],
                         capture_output=True, text=True, timeout=180)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout)
    assert out["errors"] == [] and out["requests"] == []                             # no request of its own (CSP)
    assert out["overflow"][0] <= out["overflow"][1], f"the card scrolls sideways at {data.get('width', 375)} px: {out['overflow']}"
    return out


def _result(r) -> dict:
    return {"content": [{"type": "text", "text": c.text} for c in r.content], "structuredContent": r.structured_content}


def _calls(out, method="tools/call"):
    return [m["params"] for m in out["log"] if m.get("method") == method]


def _info(tool):
    return {"tool": {"name": tool}}


@needs_browser
def test_at_375_px_the_plan_card_leads_with_the_check_and_says_each_sentence_once(tmp_path, fabric):
    r, d = _sc("plan_backend", **SRC)
    check, _ = _sc("validate_plan", **SRC)
    out = _browse(tmp_path, build.card_html(), {
        "args": SRC, "result": _result(r), "caps": CAPS, "toolInfo": _info("plan_backend"), "delay": 1500,
        "replies": {"validate_plan": [_result(check)]},
        "clicks": [{"text": "Check against the rows", "wait": 700}, {"css": "h1", "wait": 1600}],
        "query": {"primary": "button.act-primary", "buttons": "button", "builds": "button[data-kind='dry_run']", "why": ".act-name-why"}})
    onto = d[words.KEY]["onto"]
    assert out["snaps"][0].count("7 tables, 6 with a key.") == 1 and out["snaps"][0].count(onto) == 1     # in the bubble only
    assert out["found"]["primary"] == ["Check against the rows"]
    waiting = out["snaps"][0]
    assert "Thinker: Check against the rows…" in waiting and re.search(r"\b\d+ s\b", waiting)
    assert out["spin"][0] == "steps" and out["spin"][1] in ("0", "1", "2") and out["spin"][2] == "none"   # stepped by the timer; no CSS animation
    done = out["snaps"][1]
    assert "Thinker: Check against the rows…" not in done and "6 of 6 keys hold." in done
    assert [b for b in out["found"]["builds"]] == ["Build a semantic model (shop_model_2)", "Create an ontology (shop_ontology)",
                                                   "Create an API for GraphQL (shop_api_2)"]
    assert out["found"]["why"] == ["Named shop_model_2 because shop_model is already in this workspace; nothing that exists is changed.",
                                   "Named shop_api_2 because shop_api is already in this workspace; nothing that exists is changed."]
    assert not TOOLS_SHOWN.search(out["text"].split("Show the raw answer")[0].replace("Show details", "")), TOOLS_SHOWN.search(out["text"])
    assert not any(TOOLS_SHOWN.search(b) for b in out["found"]["buttons"])
    assert [(c["name"], c["arguments"]) for c in _calls(out)] == [("validate_plan", d["actions"][0]["arguments"])]


@needs_browser
def test_at_375_px_a_create_shows_its_progress_and_names_what_it_made(tmp_path, fabric):
    dry, d = _sc("create_backend", **SRC, name="shop_api_v2")
    made, m = _sc("create_backend", **SRC, name="shop_api_v2", dry_run=False)
    out = _browse(tmp_path, build.card_html(), {
        "args": {**SRC, "name": "shop_api_v2"}, "result": _result(dry), "caps": CAPS, "toolInfo": _info("create_backend"), "delay": 1400,
        "replies": {"create_backend": [_result(made)]}, "reducedMotion": True,
        "clicks": [{"text": "Create"}, {"text": "Yes, create shop_api_v2 in Fabric", "wait": 600}, {"css": "h1", "wait": 1500},
                   {"text": "Open shop_api_v2 in Fabric"}],
        "query": {"create": "button.act-create", "disabled": "button.act-create:disabled", "done": ".res-done", "raw": ".res-raw > summary",
                  "details": ".res-details > summary", "notes": ".res-note summary"}})
    assert d[words.KEY]["result"] in out["snaps"][0] and "Press again to create shop_api_v2" in out["snaps"][0]
    assert "Builder: Creating shop_api_v2 in Fabric…" in out["snaps"][1] and re.search(r"\b\d+ s\b", out["snaps"][1])
    assert out["spin"] == ["still", "all", "none"]                                      # reduced motion: the indicator stands still
    assert "Created shop_api_v2, an API for GraphQL, in Fabric." in out["found"]["done"]
    assert "Builder: Creating" not in out["snaps"][2]
    assert len(out["found"]["disabled"]) == 1                                           # Create is off for good after it ran
    creates = [c for c in _calls(out) if c["arguments"].get("dry_run") is False]
    assert len(creates) == 1
    assert out["found"]["details"] and out["found"]["raw"] and len(out["found"]["raw"]) == len(out["found"]["details"])
    assert any(n.startswith("3 steps are left to do in the Fabric portal.") for n in out["found"]["notes"])
    opened = [m_["params"]["url"] for m_ in out["log"] if m_.get("method") == "ui/open-link"]
    assert opened == [f"https://app.fabric.microsoft.com/groups/{gs.WS}/graphql/new-graphQLApis"]
    assert "the workspace's list" in out["text"]


@needs_browser
def test_at_375_px_a_host_that_stops_waiting_never_gets_a_second_create(tmp_path, fabric):
    dry, _ = _sc("create_semantic_model", **SRC, name="shop_model_v2")
    there = {"checked": True, "name": "shop_model_v2", "result": {"status": "Succeeded", "id": "sm-9", "mode": "created"},
             "kg_card": {"result": "shop_model_v2 is in Fabric now: a semantic model.", "title": "Semantic model: created"},
             "actions": [{"kind": "link", "label": "Open shop_model_v2 in Fabric", "who": "builder", "say": "x",
                          "url": f"https://app.fabric.microsoft.com/groups/{gs.WS}/datasets/sm-9/details"}]}
    out = _browse(tmp_path, build.card_html(), {
        "args": {**SRC, "name": "shop_model_v2"}, "result": _result(dry), "caps": CAPS, "toolInfo": _info("create_semantic_model"),
        "fail": {"create_semantic_model": {"code": -32001, "message": "Request timed out"}},
        "clicks": [{"text": "Create"}, {"text": "Yes, create shop_model_v2 in Fabric", "wait": 500}],
        "query": {"disabled": "button.act-create:disabled", "status": "button[data-kind='status']"}})
    assert "The host stopped waiting (Request timed out). Fabric may still be creating shop_model_v2, so Create is not offered again here." in out["text"]
    assert len(out["found"]["disabled"]) == 1 and out["found"]["status"] == ["Check status"]
    # the status step: the host answers it; it carries check and never dry_run=false
    out = _browse(tmp_path, build.card_html(), {
        "args": {**SRC, "name": "shop_model_v2"}, "result": _result(dry), "caps": CAPS, "toolInfo": _info("create_semantic_model"),
        "replies": {"create_semantic_model": [{"isError": False, "content": [{"type": "text", "text": json.dumps(
            {"error": "Fabric is still working on 'shop_model_v2'; the operation did not finish before this answer.", "kind": "timeout",
             "started": {"name": "shop_model_v2", "operation": OP, "check": OP}, "dry_run": False,
             "kg_card": {"result": "Fabric is still working on shop_model_v2. Nothing needs to be sent again; check its status in a moment."},
             "actions": [{"kind": "status", "label": "Check status", "who": "builder", "tool": "create_semantic_model", "name": "shop_model_v2",
                          "arguments": {**SRC, "name": "shop_model_v2", "check": OP}, "say": "x", "ask": "y"}]})}]},
            {"content": [{"type": "text", "text": json.dumps(there)}]}]},
        "clicks": [{"text": "Create"}, {"text": "Yes, create shop_model_v2 in Fabric", "wait": 400}, {"text": "Check status", "wait": 400}],
        "query": {"disabled": "button.act-create:disabled", "open": "button[data-kind='link']"}})
    assert "Fabric is still working on shop_model_v2." in out["snaps"][1] and "Try again" not in out["text"]
    calls = _calls(out)
    assert [c["arguments"].get("dry_run") for c in calls] == [False, None] and calls[1]["arguments"]["check"] == OP
    assert "shop_model_v2 is in Fabric now: a semantic model." in out["text"] and out["found"]["open"] == ["Open shop_model_v2 in Fabric"]
    assert len(out["found"]["disabled"]) == 1


@needs_browser
def test_at_375_px_a_created_ontology_is_drawn_with_its_keys_marked(tmp_path, fabric):
    made, d = _sc("create_ontology", **SRC, name="shop_onto", dry_run=False)
    out = _browse(tmp_path, build.card_html(), {
        "args": {**SRC, "name": "shop_onto", "dry_run": False}, "result": _result(made), "caps": CAPS, "toolInfo": _info("create_ontology"),
        "query": {"keyed": "svg.onto-svg g[data-key='key'] .onto-name", "none": "svg.onto-svg g[data-key='none'] .onto-name",
                  "multi": "svg.onto-svg g[data-key='composite'] .onto-name", "labels": "svg.onto-svg .onto-lab", "svgs": "svg.onto-svg title",
                  "legend": ".onto-legend li",
                  "notes": ".res-note summary", "old": "#pic-onto svg"}})
    assert len(out["found"]["keyed"]) == 5 and out["found"]["none"] == ["AuditLog"] and out["found"]["multi"] == ["OrderItems"]
    assert out["found"]["labels"] == [str(i) for i in range(1, 8)]                           # every relationship is labelled: its number,
    assert len(out["found"]["legend"]) == 7 and "OrderItems → Orders: OrderItemsHasOrders" in out["found"]["legend"]   # and its name
    assert out["found"]["svgs"][0] == "The ontology: 7 entity types, 5 with a key; 7 relationship types."
    assert out["found"]["old"] == []                                                         # one picture, not two
    assert "Created shop_onto, an ontology, in Fabric." in out["text"]
    assert any(n.startswith("1 entity type has no key, so nothing can point at it.") for n in out["found"]["notes"])
    assert "rule K3" not in out["text"].split("Show the raw answer")[0]


@needs_browser
def test_at_375_px_the_start_card_says_its_sentence_once_and_names_no_tool(tmp_path):
    for step, sample in ((None, False), ("check", False), ("map", True)):
        g = start_flow.guide(sample=True, step=step) if sample else start_flow.guide(
            **({"workspace": "demo", "source": "demo_lh", "schema": "shop", "step": step} if step else {}))
        res = mcp_apps.call_result(json.dumps(g, indent=2), {words.KEY: words.card("start", g)})
        out = _browse(tmp_path, mcp_apps_start.card_html(), {"args": {}, "result": _result(res), "caps": CAPS, "toolInfo": _info("start"),
                                                              "query": {"buttons": "button", "said": ".kg-line"}})
        assert out["text"].count(g["say"]) == 1 if g.get("say") else True, step               # once, in the mascot's bubble
        assert not TOOLS_SHOWN.search(out["text"]), (step, TOOLS_SHOWN.search(out["text"]).group(0))
        assert not any(TOOLS_SHOWN.search(b) for b in out["found"]["buttons"]), step
    off = _browse(tmp_path, mcp_apps_start.card_html(), {"args": {}, "result": _result(mcp_apps.call_result(json.dumps(start_flow.guide()))),
                                                          "caps": CAPS, "clicks": [{"css": "#kg-toggle"}]})
    assert off["text"].count(start_flow.guide()["say"]) == 1                                  # mascots off: on the card instead


@needs_browser
def test_at_375_px_a_host_that_runs_nothing_gets_plain_words_to_type(tmp_path, fabric):
    r, d = _sc("plan_backend", **SRC)
    out = _browse(tmp_path, build.card_html(), {"args": SRC, "result": _result(r), "caps": {"refuseMessages": True},
                                                 "toolInfo": _info("plan_backend"), "clicks": [{"text": "Check against the rows"}]})
    assert "This host runs no steps from the card. Type this in the chat: “Check against the rows for shop.”" in out["text"]
    assert not TOOLS_SHOWN.search(out["text"])
    sent = [m["params"]["content"] for m in out["log"] if m.get("method") == "ui/message"]
    assert sent and sent[0][0]["text"] == "Check against the rows for shop."


@needs_browser
def test_at_375_px_an_answer_without_words_still_gets_a_line_and_readable_details(tmp_path, fabric):
    r, _ = _sc("validate_plan", **SRC)
    old = {"content": [{"type": "text", "text": json.dumps({"workspaces": [{"id": "1", "name": "demo"}, {"id": "2", "name": "test"}]})}]}
    model = json.loads(server.semantic_model_draft(**SRC))
    model["summary"]["not_expressible"] = [{"source": f"t{i}", "target": "h", "why": "two columns"} for i in range(24)]
    out = _browse(tmp_path, mcp_apps.card_html(), {
        "args": SRC, "result": _result(r), "caps": CAPS,
        # WB13 (#91): the check card's steps are now Decide the open link and Use the line amounts, then the builds
        "replies": {"validate_plan": [{"content": [{"type": "text", "text": json.dumps(model)}]}], "create_semantic_model": [old]},
        "clicks": [{"text": "Use the line amounts"}, {"text": "Build a semantic model"}],
        "query": {"notes": ".res-note summary", "lines": ".res-line", "buttons": "button", "raw": ".res-raw > summary"}})
    assert "no summary in it" not in out["text"]
    assert "2 workspaces." in out["found"]["lines"]
    assert "24 notes: Not expressible Show" in out["snaps"][0].replace("\n", " ")           # an older server's answer: collapsed too
    assert out["snaps"][0].count("Not expressible: t") == 0                                  # the 24 are behind Show, not on the card
    assert not any(b.startswith("Run ") for b in out["found"]["buttons"])
    assert set(out["found"]["raw"]) == {"Show the raw answer (JSON)"}                        # behind Show details, a second toggle


@needs_browser
@pytest.mark.parametrize("width", [375, 720])
def test_the_check_card_and_the_review_card_do_not_scroll_sideways(tmp_path, fabric, width):
    r, _ = _sc("validate_plan", **SRC)
    out = _browse(tmp_path, mcp_apps.card_html(), {"width": width, "args": SRC, "result": _result(r), "caps": CAPS})
    assert "6 of 6 keys hold." in out["text"] and "Build a semantic model (shop_model_2)" in out["text"]
    rv, _ = _sc("review_plan", **SRC)
    out = _browse(tmp_path, mcp_apps_review.card_html(), {"width": width, "args": SRC, "result": _result(rv), "caps": CAPS})
    assert out["text"]
