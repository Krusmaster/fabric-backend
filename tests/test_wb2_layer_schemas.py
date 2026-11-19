"""WB2 (issues #54 and #55): every output that reads silver or gold reads the schemas the silver and gold steps wrote.

LT1, 17-18 November 2026, demo workspace, synthetic SAP tables: sap_lt1_pipeline wrote sap_silver and sap_gold; a
semantic model of the same plan read silver.<table>, and verify_build called the pipeline's three notebooks "differs"
only because it rebuilt them with silver and gold. Here Fabric's REST API is a test double holding exactly what the
creating tools would send, and the plans are the repository's synthetic samples (seed.py's shop, sap_sample.py's
SAP-shaped sap_sd): no Fabric, no customer data, no SAP system. Each case runs with sap_silver/sap_gold and with the
defaults.
"""
import json

import pytest

from fabric_backend import after_create, layer_schemas as ls, pipeline as pipeline_mod, sap_sample, seed, server, workload_api
from fabric_backend.infer import plan

WS = "11111111-1111-1111-1111-111111111111"
INFO = {"workspace_id": WS, "item_id": "33333333-3333-3333-3333-333333333333", "item_name": "demo_lh", "item_kind": "Lakehouse",
        "schema": "sap_sd", "sql_endpoint": "h", "sql_db": "demo_lh", "schemas_enabled": True, "onelake_tables_path": ""}
LAYERS = [("sap_silver", "sap_gold"), ("silver", "gold")]


def sap_plan():
    return plan(sap_sample.schema("sap_sd"))


class Workspace:
    """A Fabric workspace holding one Krusgraph pipeline of demo_lh.<schema>, built by create_pipeline's own code."""

    def __init__(self, p, info, silver, gold, name="sap_lt1_pipeline", silver_name="sap_lt1_silver", gold_name="sap_lt1_gold"):
        build = server._pipeline_build(p, info, info["schema"], silver, gold, None, False, name, silver_name, gold_name)
        self.notebooks = {n["name"]: n["content"] for n in build["notebooks"]}
        ids = {n: f"aaaaaaaa-0000-0000-0000-00000000000{i}" for i, n in enumerate(self.notebooks, start=1)}
        self.pipelines = {"p-1": server._pipeline_content(build, ids, WS)}
        self.items = [{"id": "p-1", "displayName": name, "type": "DataPipeline",
                       "description": f"Krusgraph pipeline for {build['label']}"}]
        self.items += [{"id": i, "displayName": n, "type": "Notebook"} for n, i in ids.items()]
        self.reads: list[str] = []

    def add_pipeline(self, other: "Workspace", pid: str, name: str):
        offset = len(self.items)
        for n, c in other.notebooks.items():
            nid = f"bbbbbbbb-0000-0000-0000-0000000000{offset:02d}"
            offset += 1
            self.notebooks[n] = c
            self.items.append({"id": nid, "displayName": n, "type": "Notebook"})
        content = json.loads(json.dumps(other.pipelines["p-1"]))
        by_name = {i["displayName"]: i["id"] for i in self.items if i["type"] == "Notebook"}
        old = {i["id"]: i["displayName"] for i in other.items if i["type"] == "Notebook"}
        for a in content["properties"]["activities"]:
            a["typeProperties"]["notebookId"] = by_name[old[a["typeProperties"]["notebookId"]]]
        self.pipelines[pid] = content
        self.items.append({"id": pid, "displayName": name, "type": "DataPipeline", "description": other.items[0]["description"]})

    def parts(self, ws, route, item_id, headers, fmt=None):
        self.reads.append(f"{route}/{item_id}")
        if route == "dataPipelines":
            return {"pipeline-content.json": json.dumps(self.pipelines[item_id])}
        if route == "notebooks":
            name = next(i["displayName"] for i in self.items if i["id"] == item_id)
            return {"notebook-content.py": self.notebooks[name]}
        raise KeyError(route)


def _double(monkeypatch, p, info, w):
    monkeypatch.setattr(server, "_source_inputs", lambda workspace, source, schema, keys, confirmed, ctx: (p, dict(info)))
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_items", lambda ws, headers: list(w.items) if w else [])
    monkeypatch.setattr(server, "_list_items", lambda ws, headers: list(w.items) if w else [])
    monkeypatch.setattr(server, "_item_definition_parts", w.parts if w else (lambda *a, **k: {}))
    monkeypatch.setattr(server, "_model_reads", lambda *a, **k: {"date_range": None, "whole": set(), "said": []})
    monkeypatch.setattr(server, "_model_replacement", lambda *a, **k: None)
    monkeypatch.setattr(server, "_source_schemas", lambda workspace, source, ctx: [{"schema": "sap_sd"}, {"schema": "sap_silver"}])
    monkeypatch.setattr(server, "_job_instances", lambda ws, item_id, headers: [{"status": "Completed"}])


@pytest.fixture
def sap(monkeypatch):
    def make(silver, gold, with_pipeline=True):
        p = sap_plan()
        w = Workspace(p, INFO, silver, gold) if with_pipeline else None
        _double(monkeypatch, p, INFO, w)
        return p, w
    return make


# ------------------------------------------------------------------ the parameter cells --------------------------------

@pytest.mark.parametrize("silver,gold", LAYERS)
def test_the_three_notebooks_parameter_cells_give_the_schemas_back(silver, gold):
    w = Workspace(sap_plan(), INFO, silver, gold)
    got = {n: ls.from_notebook(c) for n, c in w.notebooks.items()}
    assert got["sap_lt1_silver"] == {"silver": silver}
    assert got["sap_lt1_gold"] == {"silver": silver, "gold": gold}
    assert got["sap_lt1_pipeline_check"] == {"silver": silver, "gold": gold}
    assert ls.read_pipeline(w.items[0], lambda route, i: w.parts(WS, route, i, {})) == {"silver": silver, "gold": gold}


def test_resolve_takes_the_call_then_the_pipeline_then_the_defaults():
    found = {"silver": "sap_silver", "gold": "sap_gold"}
    assert ls.resolve("mine", "", found=found, found_from="the pipeline x") == {
        "silver": "mine", "gold": "sap_gold", "from": {"silver": "the call's arguments", "gold": "the pipeline x"},
        "said": "Silver tables in mine (from the call's arguments), gold views in sap_gold (from the pipeline x)."}
    assert ls.resolve()["silver"] == "silver" and ls.resolve()["gold"] == "gold" and ls.resolve()["from"]["silver"] == "the default"
    with pytest.raises(ls.LayerSchemaError):
        ls.resolve("sap silver; drop")
    assert ls.from_notebook('SILVER_SCHEMA = "a b"\nGOLD_SCHEMA = \'g1\'  # where') == {"gold": "g1"}   # never a bad name


# ------------------------------------------------------------------ #54: the readers -----------------------------------

@pytest.mark.parametrize("silver,gold", LAYERS)
def test_the_semantic_model_reads_the_pipelines_silver_and_dry_run_and_create_agree(sap, monkeypatch, silver, gold):
    sap(silver, gold)
    sent = {}
    monkeypatch.setattr(server, "_create_semantic_model", lambda body, ws, token_provider=None: sent.setdefault("body", body)
                        and {"status": "Succeeded", "id": "m-1"})
    two = ["VBAK", "VBAP"]                                                     # small enough for every part to be shown
    dry = json.loads(server.create_semantic_model("demo", "demo_lh", "sap_model", schema="sap_sd", tables=two))
    reads = dry["summary"]["reads"]
    assert reads["schema"] == silver and reads["schema_from"] == "the pipeline sap_lt1_pipeline (its notebooks' parameters)"
    assert f"\t\t\tschemaName: {silver}\n" in dry["parts"]["definition/tables/VBAK.tmdl"]
    assert "schemaName: silver\n" not in dry["parts"]["definition/tables/VBAK.tmdl"] or silver == "silver"
    assert f"{silver}.<table>" in reads["said"]
    created = json.loads(server.create_semantic_model("demo", "demo_lh", "sap_model", schema="sap_sd", tables=two, dry_run=False))
    assert created["result"]["status"] == "Succeeded"
    import base64
    tmdl = next(base64.b64decode(x["payload"]).decode() for x in sent["body"]["definition"]["parts"]
                if x["path"] == "definition/tables/VBAK.tmdl")
    assert tmdl == dry["parts"]["definition/tables/VBAK.tmdl"]                 # the Create sends what the dry run showed
    draft = json.loads(server.semantic_model_draft("demo", "demo_lh", "sap_model", schema="sap_sd"))
    assert draft["summary"]["reads"]["schema"] == silver


def test_the_calls_own_silver_schema_wins_over_the_pipeline_and_none_is_read(sap):
    _, w = sap("sap_silver", "sap_gold")
    out = json.loads(server.semantic_model_draft("demo", "demo_lh", "m", schema="sap_sd", silver_schema="other_silver"))
    assert out["summary"]["reads"]["schema"] == "other_silver" and out["summary"]["reads"]["schema_from"] == "the call's arguments"
    assert w.reads == []                                                       # nothing read in Fabric for it


def test_without_a_pipeline_the_model_reads_silver_and_says_the_default(sap):
    sap("x", "y", with_pipeline=False)
    out = json.loads(server.semantic_model_draft("demo", "demo_lh", "m", schema="sap_sd"))
    assert out["summary"]["reads"]["schema"] == "silver" and out["summary"]["reads"]["schema_from"] == "the default"


def test_two_pipelines_that_disagree_are_not_guessed_and_pipeline_names_the_one(sap, monkeypatch):
    p, w = sap("sap_silver", "sap_gold")
    other = Workspace(p, INFO, "silver", "gold", name="old_pipeline", silver_name="old_silver", gold_name="old_gold")
    w.add_pipeline(other, "p-2", "old_pipeline")
    out = json.loads(server.semantic_model_draft("demo", "demo_lh", "m", schema="sap_sd"))
    assert out["summary"]["reads"]["schema"] == "silver" and "None is guessed" in out["summary"]["reads"]["note"]
    named = json.loads(server.create_semantic_model("demo", "demo_lh", "m", schema="sap_sd", pipeline="sap_lt1_pipeline"))
    assert named["summary"]["reads"]["schema"] == "sap_silver"


def test_a_workspace_that_cannot_be_listed_gives_the_default_and_says_so(sap, monkeypatch):
    sap("sap_silver", "sap_gold")

    def refuse(ws, headers):
        raise RuntimeError("no")
    monkeypatch.setattr(server, "_workspace_items", refuse)
    out = json.loads(server.semantic_model_draft("demo", "demo_lh", "m", schema="sap_sd"))
    assert out["summary"]["reads"]["schema"] == "silver" and "could not be read (RuntimeError)" in out["summary"]["reads"]["note"]


@pytest.mark.parametrize("silver,gold", LAYERS)
def test_the_ontology_binds_to_the_pipelines_silver(sap, silver, gold):
    sap(silver, gold)
    out = json.loads(server.ontology_draft("demo", "demo_lh", "sap_onto", schema="sap_sd"))
    assert out["summary"]["reads_schema"]["silver"] == silver and f"{silver}.<table>" in out["summary"]["reads"]
    assert all(b["table"].startswith(f"{silver}.") for b in out["bindings"])
    created = json.loads(server.create_ontology("demo", "demo_lh", "sap_onto", schema="sap_sd"))
    assert created["summary"]["reads_schema"] == {"silver": silver, "from": "the pipeline sap_lt1_pipeline (its notebooks' parameters)"}
    other = "silver" if silver != "silver" else "sap_silver"
    assert created["parts"] == json.loads(server.create_ontology("demo", "demo_lh", "sap_onto", schema="sap_sd",
                                                                 silver_schema=silver))["parts"]
    assert created["parts"] != json.loads(server.create_ontology("demo", "demo_lh", "sap_onto", schema="sap_sd",
                                                                 silver_schema=other))["parts"]


@pytest.mark.parametrize("silver,gold", LAYERS)
def test_the_data_agent_reads_the_pipelines_silver_or_gold(sap, silver, gold):
    sap(silver, gold)
    s = json.loads(server.create_data_agent("demo", "demo_lh", "agent", schema="sap_sd", layer="silver"))
    assert s["layers"]["silver"] == silver and f"silver tables in {silver} only" in s["layer"]
    g = json.loads(server.create_data_agent("demo", "demo_lh", "agent", schema="sap_sd", layer="gold"))
    assert g["layers"]["gold"] == gold and f"gold views in {gold} only" in g["layer"]
    src = json.loads(server.create_data_agent("demo", "demo_lh", "agent", schema="sap_sd"))
    assert "layers" not in src                                                 # the source: nothing read for it


# ------------------------------------------------------------------ #55: verify_build -----------------------------------

@pytest.fixture
def shop(monkeypatch):
    def make(silver, gold):
        p = plan(seed.schema("shop"))
        info = {**INFO, "schema": "shop"}
        w = Workspace(p, info, silver, gold)
        _double(monkeypatch, p, info, w)
        monkeypatch.setattr(server, "_job_instances", lambda ws, item_id, headers: [{"status": "Completed"}])
        return w
    return make


@pytest.mark.parametrize("silver,gold", LAYERS)
def test_verify_build_rebuilds_the_pipeline_with_its_own_schemas(shop, silver, gold):
    shop(silver, gold)
    out = json.loads(server.verify_build("demo", "demo_lh", {"pipeline": "sap_lt1_pipeline"}, schema="shop"))
    states = {x["item"]: x["state"] for x in out["lines"]}
    assert states == {"sap_lt1_pipeline": "verified", "sap_lt1_silver": "verified", "sap_lt1_gold": "verified",
                      "sap_lt1_pipeline_check": "verified"}
    pl = next(x for x in out["lines"] if x["item"] == "sap_lt1_pipeline")
    assert f"silver tables in {silver} and gold views in {gold} (as the notebooks' parameters set them)" in json.dumps(pl)


def test_a_notebook_changed_in_the_portal_still_differs(shop):
    w = shop("sap_silver", "sap_gold")
    w.notebooks["sap_lt1_gold"] += "\nprint('added in the portal')\n"
    out = json.loads(server.verify_build("demo", "demo_lh", {"pipeline": "sap_lt1_pipeline"}, schema="shop"))
    states = {x["item"]: x["state"] for x in out["lines"]}
    assert states["sap_lt1_gold"] == "differs" and states["sap_lt1_silver"] == states["sap_lt1_pipeline_check"] == "verified"


def test_verify_build_compares_the_model_with_the_pipelines_silver(sap, monkeypatch):
    p, w = sap("sap_silver", "sap_gold")
    model = server._semantic_model.draft(p, {**INFO, "silver_schema": "sap_silver"}, "sap_model")["parts"]
    w.items.append({"id": "m-1", "displayName": "sap_model", "type": "SemanticModel"})
    w.notebooks.update({})
    base = w.parts

    def parts(ws, route, item_id, headers, fmt=None):
        return model if route == "semanticModels" else base(ws, route, item_id, headers, fmt)
    monkeypatch.setattr(server, "_item_definition_parts", parts)
    monkeypatch.setattr(server, "_powerbi_refreshes", lambda ws, mid, ctx: [{"status": "Completed", "endTime": "2026-11-18T10:00:00Z"}])
    monkeypatch.setattr(server, "_powerbi_dax", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("not here")))
    monkeypatch.setattr(server, "_connected", lambda *a, **k: (p.schema, lambda sql: []))
    out = json.loads(server.verify_build("demo", "demo_lh", {"semantic_model": "sap_model", "pipeline": "sap_lt1_pipeline"},
                                         schema="sap_sd"))
    line = next(x for x in out["lines"] if x["item"] == "sap_model")
    assert "Definition as the dry run" in line["said"] and "27 combined key columns compared" in line["said"]
    assert {x["item"]: x["state"] for x in out["lines"]}["sap_lt1_pipeline"] == "verified"
    wrong = server._semantic_model.draft(p, {**INFO, "silver_schema": "silver"}, "sap_model")["parts"]   # LT1's model
    model.clear(), model.update(wrong)
    out = json.loads(server.verify_build("demo", "demo_lh", {"semantic_model": "sap_model", "pipeline": "sap_lt1_pipeline"},
                                         schema="sap_sd"))
    line = next(x for x in out["lines"] if x["item"] == "sap_model")
    assert line["state"] == "differs" and "12 difference(s)" in line["said"]
    assert any("silver.VBAK in Fabric" in json.dumps(d) and "sap_silver.VBAK" in json.dumps(d) for d in line["differences"])


# ------------------------------------------------------------------ #55: next steps after a pipeline -------------------

def test_after_a_pipeline_an_older_model_of_the_same_lakehouse_is_not_proposed():
    mark = {"plan_id": "plan-aaaaaaaaaaaa", "schema_fingerprint": "sha256:1111111111111111"}
    items = [{"displayName": "demo_lh_model_3", "type": "SemanticModel", "description": "Created by Krusgraph from demo_lh (dbo)"},
             {"displayName": "other_plan_model", "type": "SemanticModel",
              "description": "Created by Krusgraph from demo_lh (dbo) [Krusgraph plan plan-bbbbbbbbbbbb, schema dbo (sha256:2222222222222222), 3 links]"},
             {"displayName": "sap_model", "type": "SemanticModel",
              "description": "Created by Krusgraph from demo_lh (dbo) [Krusgraph plan plan-cccccccccccc, schema dbo (sha256:1111111111111111), 24 links]"},
             {"displayName": "sap_lt1_pipeline", "type": "DataPipeline", "description": "Krusgraph pipeline for demo_lh.dbo"}]
    assert after_create.built_from_plan(items, "demo_lh", "dbo")["semantic_model"] == ["demo_lh_model_3", "other_plan_model", "sap_model"]
    built = after_create.built_from_plan(items, "demo_lh", "dbo", mark=mark)
    assert built["semantic_model"] == ["sap_model"]                            # the same tables (schema fingerprint)
    nothing = after_create.built_from_plan(items[:2] + items[3:], "demo_lh", "dbo", mark=mark)
    steps = after_create.next_steps("pipeline", {"workspace": "demo", "source": "demo_lh", "schema": "dbo"}, nothing, "sap_lt1_pipeline")
    verify = next(s for s in steps["next_steps"] if s["step"] == "verify")
    assert verify["args"]["items"] == {"pipeline": "sap_lt1_pipeline"} and "demo_lh_model_3" not in json.dumps(steps)


def test_the_pipeline_create_hands_its_plan_to_the_next_steps(monkeypatch):
    p = plan(seed.schema("shop"))
    mark = pipeline_mod.plan_mark_of(p)
    items = [{"displayName": "demo_lh_model_3", "type": "SemanticModel", "description": "Created by Krusgraph from demo_lh (shop)"},
             {"displayName": "pipeline_shop", "type": "DataPipeline", "description": "Krusgraph pipeline for demo_lh.shop"}]
    monkeypatch.setattr(server, "_headers", lambda ctx: {})
    monkeypatch.setattr(server, "_list_items", lambda ws, headers: items)
    out = server._next_after("pipeline", {"workspace": WS, "source": "demo_lh", "schema": "shop", "name": "pipeline_shop"}, WS,
                             {"plan_id": mark["plan_id"], "schema_fingerprint": mark["schema_fingerprint"]})
    assert next(s for s in out["next_steps"] if s["step"] == "verify")["args"]["items"] == {"pipeline": "pipeline_shop"}
    marked = server._marked("Created by Krusgraph from demo_lh (shop)", p, "shop")
    assert after_create.same_plan(marked, mark) and len(marked) <= 256


# ------------------------------------------------------------------ the Model editor ------------------------------------

def test_the_editors_schemas_reach_every_output_alike_in_dry_run_and_create():
    req = {"silver_schema": "sap_silver", "gold_schema": "sap_gold"}
    chosen = {"pipeline": "p", "semantic_model": "m", "data_agent": "a", "ontology": "o"}
    assert workload_api.layer_args("pipeline", chosen, req) == req
    assert workload_api.layer_args("semantic_model", chosen, req) == {"silver_schema": "sap_silver"}
    assert workload_api.layer_args("data_agent", chosen, req) == req
    none = {"silver_schema": "", "gold_schema": ""}
    assert workload_api.layer_args("semantic_model", chosen, none) == {"silver_schema": "silver"}     # this build writes silver
    assert workload_api.layer_args("semantic_model", {"semantic_model": "m"}, none) == {"silver_schema": ""}   # read from the pipeline
    assert workload_api.layers_request({"silver_schema": "sap_silver"}) == {"silver_schema": "sap_silver", "gold_schema": ""}
    for bad in ({"silver_schema": "a b"}, {"silver_schema": "x", "gold_schema": "X"}, {"gold_schema": 3}):
        with pytest.raises(workload_api.BadRequest):
            workload_api.layers_request(bad)


# ------------------------------------------------------------------ #55: the hint of a wrong tables= --------------------

def test_a_wrong_tables_argument_gets_a_hint_about_tables_not_keys():
    from fabric_backend import errors
    from fabric_backend.infer import PlanInputError
    out = errors.explain(PlanInputError("tables: only fact tables get a gold view; not a fact table in the plan: VBAK"))
    assert out["kind"] == "bad_input" and out["hint"].startswith("Check tables=") and "analyze_schema" in out["hint"]
    bad = errors.explain(ls.LayerSchemaError("silver_schema: letters, digits and underscores"))
    assert bad["kind"] == "bad_input" and "silver_schema and gold_schema" in bad["hint"]
    assert errors.explain(PlanInputError("keys: no such table"))["hint"].startswith("Check the keys and confirmed")
