"""W4 (24 November 2026): follow-ups from Gustav's end-to-end test of the workload in a real tenant, on synthetic data.

1. The Data product page's flow said the data agent reads the source tables (bronze), although it selects the silver
   tables: the finish (no tool runs) had no layer words, so the box fell back to the source. What the agent reads now
   comes from the recorded build: the card's words, the created item's `reads` (outputs.json), the request's layer.
2. (Removed items folded under "Removed (n)": the workload's own tests, productWords.test.ts and dataProductPage.)
3. verify_build: a source in another workspace than the build (source_workspace); the semantic model compared with the
   dry run it was built from (on the gold views when the model in Fabric reads gold, not with the model on the source);
   the pipeline's activities compared with the dry run also for a build in another workspace.
4. The Power BI reads ask for Dataset.Read.All by name; a refused read answers kind consent naming it.

Fabric's REST API, the SQL endpoint and the Power BI reads are test doubles (test_n229_verify_build's workspace); the
rows are the synthetic shop sample. No tenant, no customer data.
"""
from __future__ import annotations

import json

import pytest

from fabric_backend import data_flow, demo, server, verify_build as vb, workload_api as W
from fabric_backend import semantic_model
from test_n229_verify_build import INFO, WS, fabric, rows  # noqa: F401  (fixtures)

BUILD = "99999999-9999-9999-9999-999999999999"
LH = "44444444-4444-4444-4444-444444444444"
AGENT_SILVER = ("The agent reads the silver tables in silver only (cleaned, keys and links held), when they are in the "
                "lakehouse; otherwise the source tables in shop. Never two layers at once.")


# ------------------------------------------------------------------ 1. what the data agent reads ----------------------

def test_the_finish_card_without_words_reads_the_layer_of_the_request():
    req = {"schema": "shop", "workspace": WS, "outputs": [{"kind": "data_agent", "name": "a", "agent": {"layer": "silver"}}]}
    lay = W.agent_layer({"output": "data_agent"}, req)
    assert lay == {"layer": "silver", "schema": "silver", "fallback": True}
    assert W.agent_reads({}, "shop", req) == "reads the silver tables in silver when they are filled; until then the source tables in shop"
    gold = {**req, "gold_schema": "sap_gold", "outputs": [{"kind": "data_agent", "name": "a", "agent": {"layer": "gold"}}]}
    assert W.agent_layer({}, gold)["schema"] == "sap_gold"
    src = {**req, "outputs": [{"kind": "data_agent", "name": "a", "agent": {"layer": "source"}}]}
    assert W.agent_layer({}, src) is None


def test_the_editor_default_is_silver_and_a_build_elsewhere_has_no_fallback():
    req = {"schema": "shop", "workspace": WS, "target": {"workspace": BUILD}, "outputs": [{"kind": "data_agent", "name": "a"}]}
    assert W.agent_layer({}, req) == {"layer": "silver", "schema": "silver", "fallback": False}
    assert W.agent_reads({}, "shop", req) == "reads the silver tables in silver, once they are filled; never the source tables"


def test_the_created_item_records_what_the_agent_reads_and_wins_over_the_request():
    answer = {"layer": AGENT_SILVER, "result": {"status": "Succeeded", "id": "agent-1"}}
    made = W._created_ids("data_agent", answer, {}, WS, {"name": "shop_agent"}, {"schema": "shop"})
    assert made[0]["reads"] == {"layer": "silver", "schema": "silver", "fallback": True}
    card = {"output": "data_agent", "created": made}
    req = {"schema": "shop", "outputs": [{"kind": "data_agent", "name": "shop_agent", "agent": {"layer": "gold"}}]}
    assert W.agent_layer(card, req)["layer"] == "silver"
    on_source = W._created_ids("data_agent", {"layer": "The agent reads the source tables in shop only.",
                                              "result": {"status": "Succeeded", "id": "x"}}, {}, WS, {"name": "a"}, {"schema": "shop"})
    assert on_source[0]["reads"] == {"layer": "source", "schema": "shop"}
    assert W.agent_layer({"created": on_source}, req) is None


def test_layer_words_without_the_source_fallback():
    spec = {"schema": "shop", "layers": [{"layer": "silver", "schema": "silver"}]}
    words = server._layer_words(spec, "silver")
    assert words.startswith("The agent reads the silver tables in silver only") and "otherwise the source" not in words
    assert W.agent_layer({"answer": {"layer": words}}) == {"layer": "silver", "schema": "silver", "fallback": False}
    both = server._layer_words({**spec, "layers": spec["layers"] + [{"layer": "source", "schema": "shop"}]}, "silver")
    assert both == AGENT_SILVER


def _flow(items, chosen=None):
    p = demo.plan(demo.schema("shop"), keys=demo.DEMO_KEYS)
    return data_flow.flow(p, demo.FLOW_INFO, chosen or {"silver_notebook": "s", "gold_views": "g"}, items=items)


def test_the_flow_draws_the_agent_from_silver_and_titles_the_column_by_what_is_read():
    agent = {"output": "data_agent", "label": "Data agent", "name": "a", "layer_first": "silver", "fallback": False,
             "reads": "reads the silver tables in silver, once they are filled; never the source tables"}
    f = _flow([agent])
    into = [e for e in f["edges"] if e["to"] == "item:data_agent"]
    assert into and all(e["from"].startswith("silver:") and e["label"] == "reads silver" for e in into)
    assert {e["from"] for e in into} == {n["id"] for n in f["nodes"] if n["column"] == "silver"}
    assert f["columns"][-1]["title"] == "Built on silver"
    assert not any("Data agent" in n for n in f["notes"])
    with_fallback = _flow([{**agent, "fallback": True}])
    assert [e["label"] for e in with_fallback["edges"] if e["to"] == "item:data_agent"][0] == "until silver is filled"
    api = {"output": "graphql", "label": "API for GraphQL", "name": "api", "reads": "reads the source tables in shop (bronze) directly"}
    assert _flow([agent, api])["columns"][-1]["title"] == "Built on the source and silver"
    assert _flow([api])["columns"][-1]["title"] == "Built on the source"
    gold = _flow([{**agent, "layer_first": "gold"}])
    assert all(e["from"].startswith("gold:") for e in gold["edges"] if e["to"] == "item:data_agent")


def test_the_finish_s_flow_says_the_agent_reads_silver():
    """The finish builds cards from what was created, with no tool answer: the box and the note follow the request."""
    req = {"schema": "shop", "workspace": WS, "outputs": [{"kind": "data_agent", "name": "shop_agent", "agent": {"layer": "silver"}}]}
    card = {"output": "data_agent", "label": "Data agent", "name": "shop_agent", "created": [{"id": "a", "type": "DataAgent"}]}
    lay = W.agent_layer(card, req)
    item = {"output": "data_agent", "label": "Data agent", "name": "shop_agent", "reads": W.agent_layer_line(lay, "shop"),
            "layer_first": lay["layer"], "fallback": lay["fallback"]}
    f = _flow([item], {"pipeline": "p", "silver_notebook": "s", "gold_views": "g"})
    box = next(n for n in f["nodes"] if n["id"] == "item:data_agent")
    assert box["lines"] == ["reads the silver tables in silver when they are filled; until then the source tables in shop"]
    assert "bronze" not in box["lines"][0] and not any("Data agent reads the source" in n for n in f["notes"])


# ------------------------------------------------------------------ 3. verify_build ---------------------------------

@pytest.fixture
def elsewhere(fabric, monkeypatch):
    """The source in workspace "demo" (WS), the build in "demo_build" (BUILD) with its lakehouse build_lh: the items
    there are byte for byte what Create sent for a build in another workspace (the same functions, BUILD_IN set)."""
    monkeypatch.setattr(server, "_workspace_id", lambda ws, h: {"demo": WS, "demo_build": BUILD}.get(ws, ws))
    monkeypatch.setattr(server, "_list_items", lambda ws, h: [{"id": LH, "displayName": "build_lh", "type": "Lakehouse"}] if ws == BUILD else [])
    monkeypatch.setattr(server, "_resolve_source", lambda ws, item, h: {"id": LH, "displayName": "build_lh", "schemas_enabled": True})
    seen = []
    items_in = fabric.items

    def items_of(ws, headers):
        seen.append(ws)
        return list(items_in) if ws == BUILD else []
    monkeypatch.setattr(server, "_workspace_items", items_of)
    b, t = server.BUILD_IN.set(BUILD), server.WRITE_TARGET.set({})
    try:
        binfo, _ = server._write_info(dict(INFO), "test")
        ginfo, _ = server._gold_info(binfo, "")
        build = server._pipeline_build(fabric.plan, binfo, "shop", "silver", "gold", None, False, "pipeline_shop", "", "", gold_info=ginfo)
        tok = server.MODEL_ON_GOLD.set({"silver_schema": "silver", "gold_schema": "gold"})
        try:
            _, g_info, gspec, refusal = server._gold("demo", "demo_lh", "shop", "silver", "gold", None, None, None, False, None)
            assert refusal is None
            fabric.model_parts = semantic_model.draft_on_gold(fabric.plan, g_info, gspec, "shop_model",
                                                              server.checked_validation(fabric.plan))["parts"]
        finally:
            server.MODEL_ON_GOLD.reset(tok)
    finally:
        server.WRITE_TARGET.reset(t)
        server.BUILD_IN.reset(b)
    fabric.notebooks = {n["name"]: n["content"] for n in build["notebooks"]}
    ids = {n: next(i["id"] for i in fabric.items if i["displayName"] == n) for n in fabric.notebooks}
    fabric.pipeline = server._pipeline_content(build, ids, BUILD)
    fabric.seen = seen
    return fabric


def _verify(items, **kw):
    return json.loads(server.verify_build("demo_build", "demo_lh", items, schema="shop", source_workspace="demo", **kw))


def _line(out, name):
    return next(x for x in out["lines"] if x["item"] == name)


def test_a_source_in_another_workspace_is_verified_where_the_items_were_built(elsewhere):
    out = _verify({"pipeline": "pipeline_shop"})
    assert BUILD in elsewhere.seen and WS not in elsewhere.seen          # the items were listed in the build's workspace
    assert [x["item"] for x in out["lines"]] == ["pipeline_shop", "silver_shop", "gold_shop", "pipeline_shop_check"]
    assert {x["state"] for x in out["lines"]} == {"verified"}, out["result_lines"]
    assert any("in the lakehouse build_lh" in n for n in _line(out, "pipeline_shop")["notes"])
    assert server.BUILD_IN.get() is None and server.WRITE_TARGET.get() is None   # set for the call only


def test_a_changed_activity_in_another_workspace_differs(elsewhere):
    acts = elsewhere.pipeline["properties"]["activities"]
    acts[2]["dependsOn"][0]["dependencyConditions"] = ["Completed"]
    out = _verify({"pipeline": "pipeline_shop"})
    assert _line(out, "pipeline_shop")["state"] == "differs"
    assert "waits for" in _line(out, "pipeline_shop")["differences"][0]["said"]


def test_without_the_build_s_lakehouse_the_activities_are_still_compared(elsewhere, monkeypatch):
    monkeypatch.setattr(server, "_list_items", lambda ws, h: [])
    out = _verify({"pipeline": "pipeline_shop"})
    assert _line(out, "pipeline_shop")["state"] == "verified" and _line(out, "pipeline_shop")["checked"] == {"steps": 3}
    for n in ("silver_shop", "gold_shop", "pipeline_shop_check"):
        assert _line(out, n)["state"] == "not checked" and "build's lakehouse" in _line(out, n)["said"]


def test_a_model_on_gold_is_compared_with_the_dry_run_on_gold_not_with_the_source(elsewhere):
    assert vb.model_schemas(elsewhere.model_parts) == {"gold"}
    out = _verify({"semantic_model": "shop_model"})
    model = _line(out, "shop_model")
    assert "Definition as the dry run" in model["said"], model["said"]
    assert any("the model on the gold views in build_lh (gold)" in n for n in model["notes"])
    # before W4 the model was compared with the model on the source, and every table read as a difference
    before = vb.compare_model(semantic_model.draft(elsewhere.plan, INFO, "shop_model")["parts"], elsewhere.model_parts)
    assert before["differences"]


def test_model_basis_by_rules():
    assert vb.model_basis({"gold"}, "gold") == "gold"
    assert vb.model_basis({"sap_gold"}, "sap_gold") == "gold"
    assert vb.model_basis({"shop"}, "gold") == "source"
    assert vb.model_basis({"gold", "shop"}, "gold") == "source"
    assert vb.model_basis(set(), "gold") == "source"


def test_the_model_on_the_source_still_compares_with_the_source(fabric):
    out = json.loads(server.verify_build("demo", "demo_lh", {"semantic_model": "shop_model"}, schema="shop"))
    model = _line(out, "shop_model")
    assert model["state"] == "verified" and model["notes"] == ["Compared with the dry run on the plan's tables in demo_lh (shop)."]


# ------------------------------------------------------------------ 4. Power BI: Dataset.Read.All -------------------

class _Refused(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.response = type("R", (), {"status_code": status})()


def test_a_refused_refresh_history_answers_kind_consent_naming_the_scope(fabric):
    fabric.refreshes = _Refused(401)
    out = json.loads(server.verify_build("demo", "demo_lh", {"semantic_model": "shop_model"}, schema="shop"))
    c = out["consent"]
    assert c["kind"] == "consent" and c["scope"] == "Dataset.Read.All" and "shop_model" in c["error"]
    assert any("Power BI Service → Delegated permissions" in s for s in c["steps"])
    assert any(s.startswith("Tick Dataset.Read.All") for s in c["steps"])
    assert any("Grant admin consent" in s for s in c["steps"])
    sc = _line(out, "shop_model")["state_check"]
    assert sc["kind"] == "consent" and sc["scope"] == "Dataset.Read.All" and sc["state"] == "not checked"
    assert _line(out, "shop_model")["state"] == "not checked"                     # never verified without the read


def test_no_consent_answer_when_the_reads_work_or_fail_otherwise(fabric):
    out = json.loads(server.verify_build("demo", "demo_lh", {"semantic_model": "shop_model"}, schema="shop"))
    assert "consent" not in out
    fabric.refreshes = RuntimeError("timed out")
    out = json.loads(server.verify_build("demo", "demo_lh", {"semantic_model": "shop_model"}, schema="shop"))
    assert "consent" not in out and "kind" not in _line(out, "shop_model")["state_check"]


def test_the_power_bi_reads_ask_for_dataset_read_all_by_name(monkeypatch):
    from fabric_backend.entra import TokenError
    asked = []
    a = server.Auth.__new__(server.Auth)
    a.entra = True

    def user_token(ctx, scope):
        asked.append(scope)
        if scope == server.POWERBI_READ_SCOPE and getattr(user_token, "refuse", False):
            raise TokenError("on-behalf-of failed: invalid_grant — AADSTS65001: The user or administrator has not consented")
        return "t-" + scope.rsplit("/", 1)[-1]
    monkeypatch.setattr(a, "_user_token", user_token, raising=False)
    monkeypatch.setattr(server, "_WORKLOAD_TOKENS", type("V", (), {"get": staticmethod(lambda: None)})())
    assert a.powerbi(None, read=True) == "t-Dataset.Read.All"
    user_token.refuse = True
    assert a.powerbi(None, read=True) == "t-.default"                           # a consented ReadWrite reads too
    assert a.powerbi(None) == "t-.default"                                      # the refresh keeps .default
    assert server.POWERBI_READ_SCOPE == "https://analysis.windows.net/powerbi/api/Dataset.Read.All"
