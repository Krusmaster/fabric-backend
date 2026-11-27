"""SC2 (27 November 2026): the verify card as a picture, and Claude told what the card's buttons did.

1. verify_build's card (kg_card.verify, mcp_apps_words.verify_view, drawn by mcp_apps_verify.JS): a header with the
   overall state (all verified, some differ, not checked) as a pill and an icon, one row per item with an icon of its
   kind, its name, the state's icon and one plain line, and for a differing row the plan beside what Fabric has under
   Show details, with the counts as numbers. Every word comes from the answer.
2. A create (or a check) a card's button ran is a tools/call Claude never sees. The cards mark their calls with
   _meta {"io.krusgraph/from": "card"}; the server keeps one line per such create for the person (flow_state.card_did)
   and the next answer to a call without the mark says it once under `from_the_card`, then forgets it.

Synthetic data only: the shop of fabric_backend/seed.py through tests/golden_support's fake Fabric.
"""
from __future__ import annotations

import inspect
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from fabric_backend import flow_state, mcp_apps, mcp_apps_build, mcp_apps_review, mcp_apps_start, mcp_apps_words, server
from fabric_backend import verify_build as vb
from fabric_backend.registration_store import MemoryStore
from test_golden import SRC, fabric  # noqa: F401  (the hosted server against the synthetic shop workspace)

TESTS = Path(__file__).resolve().parent

SWAPPED = {"differences": [
    {"what": "relationship", "said": "Relationship orders.customer_id -> customers.customer_id is active in the dry run and inactive in Fabric."},
    {"what": "relationship", "said": "Relationship order_lines.order_id -> orders.order_id is inactive in the dry run and active in Fabric."}],
    "checked": {"tables": 5, "relationships": 4, "active": 3, "inactive": 1, "measures": 3, "combined_key_columns": 0}}


def _ok(kind, name, checked=None):
    return vb.line(kind, name, {"differences": [], "checked": checked or {"tables": 5}})


def _answer(lines):
    out = vb.result(lines, None)
    out["kg_card"] = mcp_apps_words.card("verify_build", out)
    return out


ALL_VERIFIED = [_ok("semantic_model", "shop_model"), _ok("ontology", "shop_ontology_2"), _ok("api", "shop_api")]
SOME_DIFFER = [_ok("ontology", "shop_ontology_2"), vb.line("semantic_model", "shop_model", SWAPPED),
               vb.line("pipeline", "shop_pipeline", {"differences": [], "checked": {"steps": 3}}, state_check=vb.pipeline_state([])),
               vb.line("report", "shop_report", not_checked="not read in time")]
NONE_CHECKED = [vb.line("semantic_model", "shop_model", not_checked="no semantic model named shop_model in the workspace")]


# ------------------------------------------------------------------ 1. the picture's data ------------------------------

def test_the_three_overall_states_and_their_words():
    for lines, state, head in ((ALL_VERIFIED, "verified", "All verified"), (SOME_DIFFER, "differs", "Some differ"),
                               (NONE_CHECKED, "not checked", "Not checked")):
        v = _answer(lines)["kg_card"]["verify"]
        assert (v["state"], v["head"]) == (state, head)
        assert v["counts"]["items"] == len(lines)
    mixed = _answer([_ok("api", "shop_api"), NONE_CHECKED[0]])["kg_card"]["verify"]
    assert (mixed["state"], mixed["head"]) == ("not checked", "Not all checked")     # never "verified" with one unread


def test_one_row_per_item_in_plain_words_what_differs_first():
    v = _answer(SOME_DIFFER)["kg_card"]["verify"]
    rows = {r["name"]: r for r in v["items"]}
    assert [r["state"] for r in v["items"]] == ["differs", "differs", "not checked", "verified"]
    assert rows["shop_ontology_2"]["line"] == "Matches the plan" and rows["shop_ontology_2"]["kind"] == "ontology"
    assert rows["shop_model"]["line"] == "2 relationships differ: active and inactive swapped"
    assert rows["shop_pipeline"]["line"] == "Never run — run the pipeline once, then check again"
    assert rows["shop_report"]["line"] == "Not checked: not read in time"
    assert v["fixes"] == ["Fix for shop_pipeline: Run the pipeline once"]


def test_a_differing_row_has_plan_and_built_and_the_counts_as_numbers():
    row = next(r for r in _answer(SOME_DIFFER)["kg_card"]["verify"]["items"] if r["name"] == "shop_model")
    assert [(e["from"], e["to"], e["plan"], e["built"]) for e in row["edges"]] == [
        ("orders", "customers", "active", "inactive"), ("order_lines", "orders", "inactive", "active")]
    assert ["relationships", 4] in row["numbers"] and ["differences", 2] in row["numbers"]
    assert all(isinstance(n, int) for _, n in row["numbers"])


def test_every_relationship_difference_the_verifier_writes_is_read_as_an_edge():
    said = {"missing": "Relationship a.x -> b.y is in the dry run and not in Fabric.",
            "extra": "Relationship a.x -> b.y is in Fabric and not in the dry run.",
            "cardinality": "Relationship a.x -> b.y is many-to-one in the dry run and one-to-one in Fabric.",
            "filter": "Relationship a.x -> b.y filters oneDirection in the dry run and bothDirections in Fabric."}
    got = {k: mcp_apps_words._edge(s) for k, s in said.items()}
    assert (got["missing"]["plan"], got["missing"]["built"]) == ("present", "absent")
    assert (got["extra"]["plan"], got["extra"]["built"]) == ("absent", "present")
    assert (got["cardinality"]["plan"], got["cardinality"]["built"]) == ("many-to-one", "one-to-one")
    assert (got["filter"]["plan"], got["filter"]["built"]) == ("oneDirection", "bothDirections")
    assert mcp_apps_words._edge("Measure Sales is SUM(x) in Fabric.") is None
    src = Path(vb.__file__).read_text(encoding="utf-8")                # the sentences read here are the verifier's own
    for words in ("is in the dry run and not in Fabric.", "is in Fabric and not in the dry run.", "in the dry run and {",
                  "filters {e.get('cross_filter')} in the dry run and "):
        assert words in src


def test_the_text_lines_and_notes_stay_for_clients_without_the_picture():
    w = _answer(SOME_DIFFER)["kg_card"]
    assert w["lines"][0].startswith("shop_model (semantic model): differs.")
    assert w["notes"][0]["line"].startswith("Every item with its verdict (4)")


def test_the_cards_budget_is_raised_only_by_what_the_picture_needs():
    from fabric_backend import mcp_apps_verify
    added = len(mcp_apps_verify.JS) + len(mcp_apps_verify.CSS)
    assert added < 9_000
    sizes = [len(h) for h in (mcp_apps.card_html(), mcp_apps_review.card_html(), mcp_apps_build.card_html())]
    assert max(sizes) < 143_000                                    # tests/test_n170_card_pictures.py: 134_000 before SC2


# ------------------------------------------------------------------ 1. the picture in Chromium -------------------------

needs_browser = pytest.mark.skipif(not shutil.which("node") or subprocess.run(["node", "-e", "require('playwright')"],
                                                                              capture_output=True).returncode != 0,
                                   reason="node + playwright not available")


def _browse(tmp_path, html: str, data: dict) -> dict:
    (tmp_path / "card.html").write_text(html, encoding="utf-8")
    (tmp_path / "data.json").write_text(json.dumps(data), encoding="utf-8")
    run = subprocess.run(["node", str(TESTS / "sc2_verify_browser.js"), str(tmp_path / "card.html"), str(tmp_path / "data.json")],
                         capture_output=True, text=True, timeout=180)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout)
    assert out["errors"] == [] and not out["overflow"], out
    return out


def _result(answer: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(answer)}], "structuredContent": answer}


@needs_browser
@pytest.mark.parametrize("width,scheme", [(375, "light"), (375, "dark"), (1280, "light")])
@pytest.mark.parametrize("lines,state", [(ALL_VERIFIED, "verified"), (SOME_DIFFER, "differs"), (NONE_CHECKED, "not checked")])
def test_the_card_draws_each_state_with_icons_that_have_words(tmp_path, lines, state, width, scheme):
    out = _browse(tmp_path, mcp_apps_build.card_html(), {"result": _result(_answer(lines)), "width": width, "scheme": scheme})
    v = out["vf"]
    assert v["state"] == state and v["pill"] == {"verified": "All verified", "differs": "Some differ", "not checked": "Not checked"}[state]
    assert v["rows"] == [[x["name"], x["state"]] for x in _answer(lines)["kg_card"]["verify"]["items"]]
    assert all(label for label in v["labels"])                    # every icon has its text alternative
    assert {"Verified", "Differs", "Not checked"} & set(v["labels"])
    assert v["fits"]                                              # nothing past the card's right edge
    if state == "differs":
        assert v["summaries"] == ["Show details", "Show details"]
        assert v["opened"]["edges"] == 4 and v["opened"]["dashed"] == 2      # plan and built, two relationships
        assert "2 relationships differ: active and inactive swapped" in out["text"]
        assert v["keyboard"]                                      # Enter on the focused summary opens it


# ------------------------------------------------------------------ 2. what the card's buttons did ---------------------

@pytest.fixture(autouse=True)
def fresh_flows():
    flow_state.clear()
    yield
    flow_state.clear()


def ctx(who: str, card: bool = False):
    """A request as the SDK hands it to a tool: the bearer token says who (flow_state.who_of), _meta says from where."""
    return SimpleNamespace(headers={"authorization": f"Bearer token-of-{who}"},
                           request_context=SimpleNamespace(meta={server.CARD_META: "card"} if card else None))


def _events(tool: str, text: str, c, **call) -> str:
    fn = getattr(server, tool)
    return server._card_events(tool, inspect.signature(fn), (), {**call, "ctx": c}, text)


CREATED = json.dumps({"dry_run": False, "result": {"status": "Succeeded", "id": "o-2", "mode": "created"}})


def test_the_cards_mark_every_call_and_the_server_reads_the_same_mark():
    assert '_meta: { "io.krusgraph/from": "card" }' in mcp_apps.CALL_JS and server.CARD_META == "io.krusgraph/from"
    for html in (mcp_apps.card_html(), mcp_apps_build.card_html(), mcp_apps_start.card_html(), mcp_apps_review.card_html()):
        assert html.count('request("tools/call"') == 1 and '"io.krusgraph/from": "card"' in html
    assert server._from_card(ctx("a", card=True)) and not server._from_card(ctx("a")) and not server._from_card(None)


def test_a_create_from_the_card_is_recorded_and_said_once_in_the_next_answer(fabric):
    created = server.create_ontology(**SRC, name="shop_ontology_2", dry_run=False, ctx=ctx("a", card=True))
    assert json.loads(created)["result"]["status"] == "Succeeded" and "from_the_card" not in created
    nxt = json.loads(server.list_workspaces(ctx=ctx("a")))
    assert nxt["from_the_card"] == {"note": "Since your last message, from the card: created shop_ontology_2 (ontology).",
                                    "events": ["created shop_ontology_2 (ontology)"]}
    assert list(nxt)[0] == "from_the_card" and "workspaces" in nxt                # first, and the answer unchanged after it
    again = json.loads(server.list_workspaces(ctx=ctx("a")))
    assert "from_the_card" not in again                                           # said once, then cleared


def test_a_check_from_the_card_is_said_with_its_verdict():
    _events("create_ontology", CREATED, ctx("a", card=True), name="shop_ontology_2")
    _events("verify_build", json.dumps(_answer([_ok("ontology", "shop_ontology_2")])), ctx("a", card=True))
    said = _events("list_workspaces", '{"workspaces": []}', ctx("a"))
    assert json.loads(said)["from_the_card"]["note"] == ("Since your last message, from the card: created shop_ontology_2 "
                                                         "(ontology); checked shop_ontology_2 (ontology): verified.")


def test_what_one_person_did_is_never_said_to_another():
    _events("create_ontology", CREATED, ctx("a", card=True), name="shop_ontology_2")
    assert "from_the_card" not in _events("list_workspaces", '{"workspaces": []}', ctx("b"))
    assert "from_the_card" in _events("list_workspaces", '{"workspaces": []}', ctx("a"))


def test_nothing_is_said_when_nothing_was_created_from_the_card():
    text = '{"workspaces": []}'
    assert _events("list_workspaces", text, ctx("a")) == text                    # nothing kept: the answer as it was
    dry = json.dumps({"dry_run": True, "would_create": [{"name": "shop_ontology_2"}]})
    refused = json.dumps({"error": "No.", "kind": "consent", "hint": "Ask."})
    for t in (dry, refused):
        _events("create_ontology", t, ctx("a", card=True), name="shop_ontology_2")
    _events("list_workspaces", text, ctx("a", card=True))                       # a card's read says and keeps nothing
    assert _events("list_workspaces", text, ctx("a")) == text


def test_claudes_own_create_is_not_said_again():
    _events("create_ontology", CREATED, ctx("a"), name="shop_ontology_2")         # Claude read this answer itself
    assert _events("list_workspaces", '{"workspaces": []}', ctx("a")) == '{"workspaces": []}'


def test_a_card_call_does_not_take_what_is_kept_for_claude():
    _events("create_ontology", CREATED, ctx("a", card=True), name="shop_ontology_2")
    _events("start", '{"step": "done"}', ctx("a", card=True))                    # the start card's own next call
    assert "created shop_ontology_2" in _events("start", '{"step": "done"}', ctx("a"))


def test_a_create_still_running_is_said_as_started():
    started = json.dumps({"started": {"name": "shop_api", "operation": "op-1", "check": "op-1"}})
    _events("create_backend", started, ctx("a", card=True), name="shop_api")
    note = json.loads(_events("list_workspaces", "{}", ctx("a")))["from_the_card"]["note"]
    assert note.endswith("started creating shop_api (API for GraphQL), not finished when the card last looked.")


def test_both_replicas_see_it_through_the_shared_store():
    flow_state.use_store(MemoryStore())                                          # BL44: Table Storage in the service
    _events("create_semantic_model", CREATED, ctx("a", card=True), name="shop_model")
    flow_state._FLOWS.clear()                                                    # the other replica has nothing in memory
    assert "created shop_model (semantic model)" in _events("list_workspaces", "{}", ctx("a"))
    assert "from_the_card" not in _events("list_workspaces", "{}", ctx("a"))


def test_the_mark_travels_through_the_mcp_endpoint(fabric, monkeypatch):
    from starlette.testclient import TestClient
    monkeypatch.setattr(server.auth, "entra", None)
    accept = {"Accept": "application/json, text/event-stream", "Authorization": "Bearer token-of-a"}

    def call(name, arguments, meta=None):
        params = {"name": name, "arguments": arguments, **({"_meta": meta} if meta else {})}
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}, headers=accept)
        body = r.text
        payload = json.loads(body.split("data: ", 1)[1].split("\n", 1)[0]) if "data: " in body else r.json()
        return payload["result"]["content"][-1]["text"]
    with TestClient(server.build_app()) as client:
        call("create_ontology", {**SRC, "name": "shop_ontology_2", "dry_run": False}, {server.CARD_META: "card"})
        assert "created shop_ontology_2 (ontology)" in call("list_workspaces", {})
        assert "from_the_card" not in call("list_workspaces", {})
