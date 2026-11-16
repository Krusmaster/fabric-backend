"""n229, parts B and C: the next steps after a Create (fabric_backend/after_create.py, the creating tools' answers, the
build card's buttons) and the gate before a build that would be of little use (the SAP-shaped sample whose dry run said
"0 active, 0 inactive, 24 not expressible" and still offered Create first).

Synthetic data only: the shop sample and the SAP-shaped sample (sap_demo.py; not SAP data, not an SAP system). Fabric's
REST API is replaced by test doubles.
"""
import json

import pytest

from fabric_backend import after_create as ac, mcp_apps_build as build, mcp_apps_next as nxt, ontology, sap_demo, seed, semantic_model, server
from fabric_backend.infer import plan

WS = "11111111-1111-1111-1111-111111111111"
ARGS = {"workspace": "demo", "source": "demo_lh", "schema": "shop", "keys": None, "confirmed": None}
INFO = {"workspace_id": WS, "item_id": "33333333-3333-3333-3333-333333333333", "item_name": "demo_lh", "item_kind": "Lakehouse",
        "schema": "shop", "sql_endpoint": "h", "sql_db": "demo_lh", "schemas_enabled": True, "onelake_tables_path": ""}


def keys(out):
    return [s["step"] for s in out["next_steps"]]


# ------------------------------------------------------------------ B: the order after each kind of Create -----------

@pytest.mark.parametrize("created,name,expected", [
    ("semantic_model", "shop_model", ["verify", "refresh", "pipeline", "report", "data_agent", "app", "drift_monitor", "data_product"]),
    ("ontology", "shop_ontology", ["verify", "pipeline", "data_agent", "app", "drift_monitor", "data_product"]),
    ("api", "shop_api", ["verify", "pipeline", "data_agent", "app", "drift_monitor", "data_product"]),
    ("pipeline", "pipeline_shop", ["verify", "data_agent", "app", "drift_monitor", "data_product"]),
    ("data_agent", "shop_agent", ["pipeline", "app", "drift_monitor", "data_product"]),
])
def test_the_next_steps_after_each_kind_of_create(created, name, expected):
    out = ac.next_steps(created, ARGS, {}, name)
    assert keys(out) == expected
    assert [s["order"] for s in out["next_steps"]] == list(range(1, len(expected) + 1))
    for s in out["next_steps"]:
        assert s["who"] in ("thinker", "builder", "onto") and s["why"].endswith(".") and s["why"].count(". ") == 0, s   # one sentence
        assert s["label"] == ac.LABEL[s["step"]] and (s.get("ask") or s.get("tool"))
    assert [m["step"] for m in out["more"]] == ["dbt"] and out["more"][0]["draft"] is True
    assert out["more"][0]["label"] == "Download a dbt project draft" and "draft" in out["more"][0]["why"]
    assert "dbt" not in keys(out)                                           # only under More


def test_after_a_report_the_report_is_already_built_and_not_suggested_again():
    built = {"semantic_model": ["shop_model"], "report": ["shop_model_report"]}
    out = ac.next_steps("report", ARGS, built, "shop_model_report")
    assert keys(out) == ["verify", "refresh", "pipeline", "data_agent", "app", "drift_monitor", "data_product"]
    assert out["already_built"] == [{"step": "report", "label": "Create a report on it", "state": "already built",
                                     "name": "shop_model_report"}]
    verify = out["next_steps"][0]
    assert verify["tool"] == "verify_build" and verify["who"] == "thinker"
    assert verify["args"] == {"workspace": "demo", "source": "demo_lh", "schema": "shop",
                              "items": {"semantic_model": "shop_model", "report": "shop_model_report"}}


def test_everything_built_leaves_verify_refresh_app_and_the_data_product():
    built = {"semantic_model": ["shop_model"], "report": ["shop_model_report"], "pipeline": ["pipeline_shop"],
             "data_agent": ["shop_agent"], "drift_monitor": ["drift_monitor_shop_nightly"], "ontology": ["shop_ontology"]}
    out = ac.next_steps("ontology", ARGS, built, "shop_ontology")
    assert keys(out) == ["verify", "refresh", "app", "data_product"]
    assert [d["step"] for d in out["already_built"]] == ["pipeline", "report", "data_agent", "drift_monitor"]
    assert all(d["state"] == "already built" for d in out["already_built"])


def test_no_step_writes_and_the_names_it_suggests_are_free():
    out = ac.next_steps("semantic_model", ARGS, {}, "shop_model", taken=["shop_model", "shop_model_report", "pipeline_shop"])
    by = {s["step"]: s for s in out["next_steps"]}
    assert by["report"]["tool"] == "create_report" and by["report"]["args"]["dry_run"] is True
    assert by["report"]["args"]["name"] == "shop_model_report_2" and by["report"]["args"]["model"] == "shop_model"
    assert 'name="pipeline_shop_2"' in by["pipeline"]["ask"] and "dry_run=true" in by["pipeline"]["ask"]
    assert by["pipeline"]["choices"] == ["Run once", "Schedule"] and "Run once (run_once=true)" in by["pipeline"]["ask"]
    for s in out["next_steps"]:
        if s.get("tool"):
            assert s["tool"] == "verify_build" or s["args"]["dry_run"] is True, s
    # the refresh is the one step that changes anything, and it is a sentence to confirm in the chat, never a tool call from a card
    assert "tool" not in by["refresh"] and "ask me to confirm first" in by["refresh"]["ask"] and "refresh=true" in by["refresh"]["ask"]
    assert "empty App item" in by["app"]["why"] and "one command" in by["app"]["why"] and "inside Fabric only" in by["app"]["why"]
    assert "tool" not in by["app"] and "rayfin_connector" in by["app"]["ask"]


def test_a_source_that_is_not_a_lakehouse_gets_no_pipeline_and_says_why():
    out = ac.next_steps("semantic_model", {**ARGS, "source": "demo_wh"}, {}, "shop_model", lakehouse=False)
    pipe = next(s for s in out["next_steps"] if s["step"] == "pipeline")
    assert pipe["state"] == "not available" and "not one" in pipe["why"] and "ask" not in pipe and "tool" not in pipe
    assert "drift_monitor" not in keys(out)


def test_built_from_plan_reads_type_and_description_and_never_takes_anothers_item():
    items = [
        {"displayName": "shop_model", "type": "SemanticModel", "description": "Created by Krusgraph from demo_lh (shop)"},
        {"displayName": "finance_model", "type": "SemanticModel", "description": "Created by Krusgraph from demo_lh (finance)"},
        {"displayName": "sales", "type": "SemanticModel", "description": "The sales team's model"},
        {"displayName": "shop_model_report", "type": "Report", "description": "Created by Krusgraph on the semantic model shop_model"},
        {"displayName": "finance_report", "type": "Report", "description": "Created by Krusgraph on the semantic model finance_model"},
        {"displayName": "pipeline_shop", "type": "DataPipeline", "description": "Krusgraph pipeline for demo_lh.shop: the silver tables ..."},
        {"displayName": "drift_monitor_shop_nightly", "type": "DataPipeline", "description": "Krusgraph drift monitor for demo_lh.shop"},
        {"displayName": "nightly_load", "type": "DataPipeline", "description": ""},
        {"displayName": "shop_ontology", "type": "Ontology", "description": "Created by Krusgraph from demo_lh (shop)"},
    ]
    assert ac.built_from_plan(items, "demo_lh", "shop") == {
        "semantic_model": ["shop_model"], "ontology": ["shop_ontology"], "pipeline": ["pipeline_shop"],
        "drift_monitor": ["drift_monitor_shop_nightly"], "report": ["shop_model_report"]}
    assert ac.built_from_plan(items, "33333333-3333-3333-3333-333333333333", "shop", "demo_lh")["semantic_model"] == ["shop_model"]
    assert ac.built_from_plan(items, "other_lh", "shop") == {}


# ------------------------------------------------------------------ B: in the creating tools' answers ----------------

@pytest.fixture
def fabric(monkeypatch):
    p = plan(seed.schema("shop"))
    items = [{"id": "lh", "displayName": "demo_lh", "type": "Lakehouse", "description": ""},
             {"id": "p-1", "displayName": "pipeline_shop", "type": "DataPipeline", "description": "Krusgraph pipeline for demo_lh.shop"}]
    monkeypatch.setattr(server, "_source_inputs", lambda workspace, source, schema, keys, confirmed, ctx: (p, dict(INFO)))
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server, "_list_items", lambda ws, headers: list(items))
    monkeypatch.setattr(server, "_model_reads", lambda *a, **k: {"date_range": None, "whole": set(), "said": []})
    monkeypatch.setattr(server, "_model_replacement", lambda *a, **k: None)
    monkeypatch.setattr(server, "_source_schemas", lambda workspace, source, ctx: [{"schema": "shop", "tables": 7}])
    monkeypatch.setattr(server, "_create_semantic_model", lambda body, ws, token_provider=None: {"status": "Succeeded", "id": "m-1", "mode": "created"})
    monkeypatch.setattr(server, "_create_ontology", lambda body, ws, token_provider=None: {"status": "Succeeded", "id": "o-1", "mode": "created"})
    return items


def test_a_create_that_succeeded_ends_with_the_next_steps_and_a_dry_run_does_not(fabric):
    dry = json.loads(server.create_semantic_model("demo", "demo_lh", "shop_model", schema="shop"))
    assert dry["dry_run"] is True and "next_steps" not in dry and "gate" not in dry
    out = json.loads(server.create_semantic_model("demo", "demo_lh", "shop_model", schema="shop", dry_run=False))
    assert out["result"]["status"] == "Succeeded"
    assert keys(out) == ["verify", "refresh", "report", "data_agent", "app", "drift_monitor", "data_product"]
    assert out["already_built"] == [{"step": "pipeline", "label": ac.LABEL["pipeline"], "state": "already built", "name": "pipeline_shop"}]
    assert out["next_steps"][0]["args"]["items"] == {"semantic_model": "shop_model", "pipeline": "pipeline_shop"}
    assert out["more"][0]["label"] == "Download a dbt project draft" and "No step writes" in out["next_steps_note"]
    onto = json.loads(server.create_ontology("demo", "demo_lh", "shop_ontology", schema="shop", dry_run=False))
    assert keys(onto)[0] == "verify" and "report" not in keys(onto) and "refresh" not in keys(onto)


def test_a_create_that_failed_gets_no_next_steps(fabric, monkeypatch):
    monkeypatch.setattr(server, "_create_semantic_model", lambda body, ws, token_provider=None: {"status": "Failed", "http": 403, "body": "{}"})
    out = json.loads(server.create_semantic_model("demo", "demo_lh", "shop_model", schema="shop", dry_run=False))
    assert out["result"]["status"] == "Failed" and "next_steps" not in out


def test_when_the_workspace_cannot_be_listed_the_create_still_answers_with_its_own_item_as_built(fabric, monkeypatch):
    def refuse(ws, headers):
        raise RuntimeError("HTTP 500")
    monkeypatch.setattr(server, "_list_items", refuse)
    out = json.loads(server.create_semantic_model("demo", "demo_lh", "shop_model", schema="shop", dry_run=False))
    assert keys(out) == ["verify", "refresh", "pipeline", "report", "data_agent", "app", "drift_monitor", "data_product"]
    assert out["next_steps"][0]["args"]["items"] == {"semantic_model": "shop_model"}


def test_refresh_true_is_said_in_the_dry_run_and_only_refreshes_a_model_that_exists(fabric, monkeypatch):
    dry = json.loads(server.create_semantic_model("demo", "demo_lh", "shop_model", schema="shop", refresh=True))
    assert dry["refresh"]["planned"] is True and "refreshed once right after it is created" in dry["refresh"]["said"]
    asked = []
    monkeypatch.setattr(server, "_refresh_once", lambda ws, model_id, ctx: asked.append((ws, model_id)) or {"status": "refreshed"})
    new = json.loads(server.create_semantic_model("demo", "demo_lh", "shop_model", schema="shop", refresh=True, dry_run=False))
    assert new["refresh"] == {"status": "refreshed"} and asked == [(WS, "m-1")] and new["result"]["mode"] == "created"
    monkeypatch.setattr(server, "_model_replacement", lambda *a, **k: {"existing": True, "id": "m-9", "said": "exists"})
    monkeypatch.setattr(server, "_create_semantic_model", lambda *a, **k: pytest.fail("an existing model's definition is not sent again"))
    old = json.loads(server.create_semantic_model("demo", "demo_lh", "shop_model", schema="shop", refresh=True, dry_run=False))
    assert old["refresh"] == {"status": "refreshed"} and asked[-1] == (WS, "m-9") and old["result"]["mode"] == "refreshed_only"


def test_refresh_once_says_what_happened_and_never_guesses(monkeypatch):
    import sys
    deploy = sys.modules["fabric_backend.deploy"]

    class R:
        def __init__(self, status, body=None, headers=None):
            self.status_code, self._b, self.headers = status, body or {}, headers or {}

        def json(self):
            return self._b
    monkeypatch.setattr(server, "REFRESH_PAUSE", 0)
    monkeypatch.setattr(server.auth, "powerbi", lambda ctx: "pbi-token")
    calls = []

    def send(method, url, headers, write=False, **kw):
        calls.append((method, write))
        if method == "post":
            return R(202, headers={"x-ms-request-id": "req-1"})
        return R(200, {"value": [{"requestId": "req-1", "status": "Completed"}]})
    monkeypatch.setattr(deploy, "send", send)
    assert server._refresh_once(WS, "m-1", None) == {"status": "refreshed"}
    assert calls[0] == ("post", True) and all(c == ("get", False) for c in calls[1:])
    monkeypatch.setattr(deploy, "send", lambda method, url, headers, write=False, **kw: R(403))
    out = server._refresh_once(WS, "m-1", None)
    assert out["status"] == "not_run" and out["scope"] == "Dataset.ReadWrite.All" and "Refresh now" in out["hint"]

    def no_token(ctx):
        raise PermissionError("sign-in required")
    monkeypatch.setattr(server.auth, "powerbi", no_token)
    assert server._refresh_once(WS, "m-1", None)["status"] == "not_run"


# ------------------------------------------------------------------ B: the build card's buttons ----------------------

def test_after_a_create_the_card_draws_the_next_steps_as_buttons_with_the_mascots_sentence():
    answer = {"dry_run": False, "result": {"status": "Succeeded", "id": "m-1"},
              **ac.next_steps("semantic_model", ARGS, {"pipeline": ["pipeline_shop"]}, "shop_model")}
    call = {"workspace": "demo", "source": "demo_lh", "schema": "shop", "name": "shop_model", "dry_run": False}
    acts, note = build.actions_for("create_semantic_model", call, answer, taken={"shop_model"}, workspace_id=WS)
    assert note is None
    assert [(a["kind"], a["label"]) for a in acts] == [
        ("link", "Open in Fabric"), ("call", "Verify what was built"), ("say", "Refresh the model once"),
        ("dry_run", "Create a report on it"), ("say", "Create a data agent (experimental)"), ("say", "A Rayfin App (preview)"),
        ("say", "Add a drift monitor"), ("say", "Register it as a data product"),
        ("done", "Build the pipeline (silver, gold, check)"), ("say", "More: Download a dbt project draft (a draft)")]
    verify = acts[1]
    assert verify["tool"] == "verify_build" and verify["who"] == "thinker" and verify["why"] == ac.WHY["verify"]
    assert verify["arguments"]["items"] == {"semantic_model": "shop_model", "pipeline": "pipeline_shop"}
    assert acts[3]["tool"] == "create_report" and acts[3]["arguments"]["dry_run"] is True and acts[3]["name"] == "shop_model_report"
    assert acts[8]["say"] == "Build the pipeline (silver, gold, check): already built (pipeline_shop)." and "tool" not in acts[8]
    assert all(a.get("why") for a in acts if a["kind"] in ("call", "say", "dry_run")) and all("tool" not in a for a in acts if a["kind"] == "say")
    assert nxt.steps("create_semantic_model", call, answer) == []           # no second list of other suggestions beside them


def test_the_card_script_allows_verify_build_as_a_read_and_a_say_button_runs_no_tool():
    js = build.actions_js()
    assert '"verify_build":"call"' in js and build.ALLOWED["verify_build"] == "call"
    assert 'if (a.kind === "say") { viaChat(a, out, button); return; }' in js
    assert 'a.kind === "say" || a.kind === "done"' in js and "a.tool === undefined" in js
    assert "already built" in js and "act-reason" in js and "renderChecks(d, out)" in js
    assert "verify_build" in build.card_html() and build.ALLOWED["create_semantic_model"] == "build"   # creating tools: dry run first, as before
    assert 'c.sql_for_all === true ? "Show the SQL"' in nxt.js() and "c.words" in nxt.js()


def test_the_lead_text_lists_the_next_steps_for_a_text_only_client():
    answer = {"dry_run": False, "result": {"status": "Succeeded", "id": "m-1"}, **ac.next_steps("semantic_model", ARGS, {}, "shop_model")}
    call = {"workspace": "demo", "source": "demo_lh", "schema": "shop", "name": "shop_model", "dry_run": False}
    acts, _ = build.actions_for("create_semantic_model", call, answer, taken=set(), workspace_id=WS)
    lead = nxt.lead("create_semantic_model", answer, [], acts)
    assert "- Verify what was built (verify_build)" in lead and "- Refresh the model once" in lead
    assert "- More: Download a dbt project draft (a draft)" in lead


def test_older_answers_without_next_steps_keep_the_old_two_buttons():
    answer = {"dry_run": False, "result": {"status": "Succeeded", "id": "m-1"}}
    call = {"workspace": "demo", "source": "demo_lh", "name": "shop_model", "dry_run": False}
    acts, _ = build.actions_for("create_semantic_model", call, answer, taken={"shop_model"}, workspace_id=WS)
    assert [a["kind"] for a in acts] == ["link", "dry_run"] and acts[1]["tool"] == "create_report"


# ------------------------------------------------------------------ C: the gate --------------------------------------

@pytest.fixture(scope="module")
def sap():
    schema, _ = sap_demo.sqlite(schema="dbo")
    return plan(schema)


SAP_ARGS = {"workspace": "demo", "source": "demo_lh", "schema": "dbo", "keys": None, "confirmed": None}


def test_the_sap_sample_without_combined_keys_has_24_relationships_none_expressible_and_the_gate_says_so(sap):
    info = {**INFO, "schema": "dbo", "item_kind": "Warehouse", "item_name": "demo_wh"}
    summary = semantic_model.draft(sap, info, "demo_lh_model_3")["summary"]
    assert (summary["relationships_active"], summary["relationships_inactive"], summary["relationships_not_expressible"]) == (0, 0, 24)
    gate = ac.model_gate(summary, SAP_ARGS, lakehouse=False, name="demo_lh_model_3")
    assert gate["gate"] == "relationships" and gate["create"] == "Create anyway"
    assert gate["said"] == ("24 of the plan's 24 relationship(s) cannot be expressed in the model as the tables stand and none can: "
                            "demo_lh_model_3 would be tables side by side, with nothing to slice by. They use several columns per side "
                            "(a composite key).")
    assert gate["first"]["label"] == "Add combined key columns first" and gate["counts"] == {"active": 0, "inactive": 0, "not_expressible": 24}
    carried = semantic_model.draft(sap, {**INFO, "schema": "dbo"}, "demo_lh_model_3", combined=False)["summary"]   # a lakehouse, keys not carried
    gate = ac.model_gate(carried, SAP_ARGS, lakehouse=True, name="demo_lh_model_3")
    assert gate["first"]["step"] == "pipeline" and gate["first"]["label"] == "Build the silver step first"
    assert "create_pipeline" in gate["first"]["ask"] and "dry_run=true" in gate["first"]["ask"] and "combined key" in gate["first"]["why"]


def test_on_a_lakehouse_the_model_reads_silver_and_the_gate_asks_for_the_silver_step_until_it_is_there(sap):
    summary = semantic_model.draft(sap, {**INFO, "schema": "dbo"}, "demo_lh_model_3")["summary"]
    assert summary["relationships_not_expressible"] == 0 and summary["reads"]["layer"] == "silver"       # n226 carries the keys
    gate = ac.model_gate(summary, SAP_ARGS, lakehouse=True, silver_there=False, name="demo_lh_model_3")
    assert gate["gate"] == "silver_missing" and gate["first"]["step"] == "pipeline" and gate["create"] == "Create anyway"
    assert "which are not there yet" in gate["said"] and "24 relationship(s)" in gate["said"] and "only the silver step writes" in gate["said"]
    assert ac.model_gate(summary, SAP_ARGS, lakehouse=True, silver_there=True) is None
    assert ac.model_gate(summary, SAP_ARGS, lakehouse=True, silver_there=None) is None                    # not known is not a gate


def test_the_shop_sample_has_no_gate_and_create_stays_the_first_button():
    p = plan(seed.schema("shop"))
    summary = semantic_model.draft(p, INFO, "shop_model")["summary"]
    assert ac.model_gate(summary, ARGS, True, None, "shop_model") is None
    assert ac.ontology_gate(ontology.summary(p), ARGS, True, "shop_ontology") is None
    answer = {"dry_run": True, "summary": summary}
    call = {"workspace": "demo", "source": "demo_lh", "schema": "shop", "name": "shop_model", "dry_run": True}
    acts, note = build.actions_for("create_semantic_model", call, answer, taken=set())
    assert [(a["kind"], a["label"]) for a in acts] == [("create", "Create")] and note is None and "secondary" not in acts[0]


def test_with_a_gate_the_card_puts_the_fix_first_and_create_anyway_second(sap):
    summary = semantic_model.draft(sap, {**INFO, "schema": "dbo"}, "demo_lh_model_3", combined=False)["summary"]
    gate = ac.model_gate(summary, SAP_ARGS, lakehouse=True, name="demo_lh_model_3")
    answer = {"gate": gate, "dry_run": True, "summary": summary}
    call = {"workspace": "demo", "source": "demo_lh", "name": "demo_lh_model_3", "dry_run": True}
    acts, note = build.actions_for("create_semantic_model", call, answer, taken=set())
    assert [(a["kind"], a["label"]) for a in acts] == [("say", "Build the silver step first"), ("create", "Create anyway")]
    assert note == gate["said"] and note.startswith("24 of the plan's 24 relationship(s) cannot be expressed")
    assert acts[1]["secondary"] is True and acts[1]["arguments"] == {**call, "dry_run": False} and acts[1]["name"] == "demo_lh_model_3"
    assert "little use" in acts[1]["why"] and "create_pipeline" in acts[0]["say"]
    js = build.actions_js()
    assert 'a.kind === "create" && a.secondary !== true ? "act-create" : "act-b"' in js    # no primary style on Create anyway


def test_an_ontology_with_most_entities_keyless_is_gated_the_same_way(sap):
    summary = {"entity_types": 17, "with_key": 0, "relationship_types": 0, "skipped_relationships": 24, "notes": []}
    gate = ac.ontology_gate(summary, SAP_ARGS, lakehouse=False, name="demo_lh_ontology")
    assert gate["gate"] == "keyless" and gate["create"] == "Create anyway" and gate["first"]["label"] == "Give the keys first"
    assert gate["said"].startswith("17 of the 17 entity types have no key") and "24 relationship(s) are left out" in gate["said"]
    assert ac.ontology_gate({"entity_types": 7, "with_key": 5}, ARGS) is None
    assert ac.ontology_gate({"entity_types": 10, "with_key": 5}, ARGS) is None                           # half is not most
    assert ac.ontology_gate({"entity_types": 10, "with_key": 4}, ARGS)["gate"] == "keyless"
    acts, note = build.actions_for("create_ontology", {"workspace": "demo", "source": "demo_wh", "name": "demo_lh_ontology", "dry_run": True},
                                   {"gate": gate, "dry_run": True}, taken=set())
    assert [a["label"] for a in acts] == ["Give the keys first", "Create anyway"] and note == gate["said"]


def test_the_dry_run_of_the_sap_sample_carries_the_gate_first_in_the_answer(sap, monkeypatch):
    monkeypatch.setattr(server, "_source_inputs", lambda workspace, source, schema, keys, confirmed, ctx: (
        sap, {**INFO, "schema": "dbo", "item_kind": "Lakehouse"}))
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_model_reads", lambda *a, **k: {"date_range": None, "whole": set(), "said": []})
    monkeypatch.setattr(server, "_model_replacement", lambda *a, **k: None)
    monkeypatch.setattr(server, "_source_schemas", lambda workspace, source, ctx: [{"schema": "dbo", "tables": 17}])
    out = json.loads(server.create_semantic_model("demo", "demo_lh", "demo_lh_model_3"))
    assert next(iter(out)) == "gate" and out["gate"]["gate"] == "silver_missing" and out["dry_run"] is True
    assert out["gate"]["first"]["label"] == "Build the silver step first" and out["gate"]["create"] == "Create anyway"
    monkeypatch.setattr(server, "_source_schemas", lambda workspace, source, ctx: [{"schema": "dbo", "tables": 17}, {"schema": "silver", "tables": 17}])
    assert "gate" not in json.loads(server.create_semantic_model("demo", "demo_lh", "demo_lh_model_3"))

    def unreadable(workspace, source, ctx):
        raise RuntimeError("endpoint asleep")
    monkeypatch.setattr(server, "_source_schemas", unreadable)
    assert "gate" not in json.loads(server.create_semantic_model("demo", "demo_lh", "demo_lh_model_3"))    # not known: no gate


# ------------------------------------------------------------------ the card in a browser ----------------------------

def _result(answer: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(answer)}], "structuredContent": answer}


def test_the_card_in_a_browser_after_a_create_and_at_a_gated_dry_run(tmp_path, sap, monkeypatch):
    import shutil
    import subprocess
    from pathlib import Path
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    probe = subprocess.run(["node", "-e", "require('playwright')"], capture_output=True, cwd=Path(__file__).parent)
    if probe.returncode != 0:
        pytest.skip("playwright is not installed")
    from fabric_backend import verify_build as vb
    # after a Create: the answer as the tool gives it, with the card's buttons
    call = {"workspace": "demo", "source": "demo_lh", "schema": "shop", "name": "shop_model", "dry_run": False}
    created = {"summary": {"tables": 8, "roles": {}, "relationships_active": 7, "relationships_inactive": 0, "relationships_not_expressible": 0},
               "dry_run": False, "result": {"status": "Succeeded", "id": "m-1", "mode": "created"},
               **ac.next_steps("semantic_model", ARGS, {"pipeline": ["pipeline_shop"]}, "shop_model")}
    created["actions"], _ = build.actions_for("create_semantic_model", call, created, taken={"shop_model"}, workspace_id=WS)
    # the verifier's answer for the button: one item that differs (never refreshed), three figures verified
    figs = [{"kpi": k, "measure": m, "state": "verified", "said": f"{k} = {n}: the model and the source rows agree.", "source_rows": n, "model": n,
             "sql": s, "expression": ""} for k, m, n, s in (
        ("Orders", "orders[Rows in orders]", 60, "SELECT COUNT_BIG(*) AS v FROM [shop].[orders]"),
        ("Units", "order_items[Total quantity]", 324, "SELECT SUM([quantity]) AS v FROM [shop].[order_items]"))]
    lines = [vb.line("semantic_model", "shop_model", {"differences": [], "checked": {"tables": 8}}, state_check=vb.model_state([])),
             vb.line("report", "shop_model_report", {"differences": [], "checked": {"visuals": 8}}, figs=figs, doubles=[])]
    verify = vb.result(lines, {"seconds": 45})
    monkeypatch.setattr(server._mcp_apps, "enabled", lambda environ=None: True)
    verify["checks"] = server._verify_checks(verify)
    # a gated dry run: the SAP-shaped sample, keys not carried
    summary = semantic_model.draft(sap, {**INFO, "schema": "dbo"}, "demo_lh_model_3", combined=False)["summary"]
    gcall = {"workspace": "demo", "source": "demo_lh", "name": "demo_lh_model_3", "dry_run": True}
    gated = {"gate": ac.model_gate(summary, SAP_ARGS, lakehouse=True, name="demo_lh_model_3"), "summary": summary, "dry_run": True}
    gated["actions"], gated["actions_note"] = build.actions_for("create_semantic_model", gcall, gated, taken=set())
    (tmp_path / "card.html").write_text(build.card_html(), encoding="utf-8")
    (tmp_path / "cases.json").write_text(json.dumps({
        "created": {"result": _result(created), "args": call, "tool": "create_semantic_model"},
        "gated": {"result": _result(gated), "args": gcall, "tool": "create_semantic_model"}, "verify": _result(verify)}), encoding="utf-8")
    run = subprocess.run(["node", str(Path(__file__).parent / "n229_cards_browser.js"), str(tmp_path / "card.html"), str(tmp_path / "cases.json")],
                         capture_output=True, text=True, timeout=180)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout)
    assert out["errors"] == []
    c = out["created"]
    assert c["verdict"] == "Created in Fabric." and c["primary"] == 0 and c["nextHeading"] == 0 and c["overflow"] is False
    assert c["buttons"] == ["Open in Fabric", "Verify what was built", "Refresh the model once", "Create a report on it (shop_model_report)",
                            "Create a data agent (experimental)", "A Rayfin App (preview)", "Add a drift monitor",
                            "Register it as a data product", "More: Download a dbt project draft (a draft)"]
    assert c["reasons"][1] == "Thinker: " + ac.WHY["verify"] and c["reasons"][2] == "Builder: " + ac.WHY["refresh"]
    assert c["reasons"][7] == "Onto: " + ac.WHY["data_product"] and all(c["reasons"][1:])
    assert c["done"] == ["Build the pipeline (silver, gold, check): already built (pipeline_shop)."] and c["groups"] == ["Next steps, in order", "Already built"]
    assert [x["name"] for x in c["verifyCalls"]] == ["verify_build"]
    assert c["verifyCalls"][0]["arguments"]["items"] == {"semantic_model": "shop_model", "pipeline": "pipeline_shop"}
    assert c["pills"] == ["3 verified", "1 differs", "0 not checked"] and c["label"] == vb.LABEL
    assert c["rowStates"] == ["differs", "verified", "verified", "verified"]
    assert c["rowWhat"][0].startswith("Semantic model shop_model") and c["rowWhat"][2].startswith("Figure Orders")
    assert c["sqlButtons"] == ["Show the SQL", "Show the SQL"] and c["sqlHiddenFirst"] is True
    assert c["sqlShown"] == "SELECT COUNT_BIG(*) AS v FROM [shop].[orders]"
    assert c["callsAfterSay"] == 0 and len(c["said"]) == 1 and c["said"][0].startswith("Refresh the semantic model shop_model once")
    assert c["sayNote"].startswith("Sent to the chat")
    g = out["gated"]
    assert g["verdict"].startswith("Dry run: nothing was created. 24 of the plan's 24 relationship(s) cannot be expressed")
    assert g["buttons"] == ["Build the silver step first", "Create anyway"] and g["primary"] == 0 and g["anywayClass"] == "act-b"
    assert g["note"].startswith("24 of the plan's 24 relationship(s)")
    assert g["armed"] == "Yes, create demo_lh_model_3 in Fabric" and g["callsAfterFirstClick"] == 0      # still two clicks, and second
    assert g["calls"] == [] and len(g["said"]) == 1 and "create_pipeline" in g["said"][0]
