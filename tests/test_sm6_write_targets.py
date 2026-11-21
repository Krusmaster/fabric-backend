"""SM6 (docs/SMOOTH/PLAN.md, row 5; G2 and G3 in docs/SMOOTH/MULTI-LAKEHOUSE.md): write to the right lakehouse. On the
synthetic fixture tests/fixtures/multi_lakehouse.py, layout (a) `bronze_lh`, `silver_lh`, `gold_lh`: the dry run says
"silver → silver_lh, gold → gold_lh" in one line, the silver notebook reads bronze through its OneLake path, the gold
views and the check read the silver tables by their three-part name, and the model, the ontology and the agent read
the lakehouse the build wrote. Start reaches all three dry runs in at most 4 taps with the suggestion taken. Nothing is
written: the fixture fails any POST, PATCH, PUT or DELETE. Without the new parameters nothing changes."""
from __future__ import annotations

import json

import pytest
import wb15_fake
from fixtures import multi_lakehouse as mlh

from fabric_backend import flow_state, server
from fabric_backend import start_flow as sf

W = mlh.WORKSPACE
E = mlh.EXPECTED["a"]
LINE = f"silver → {E['dry_run']['silver']}, gold → {E['dry_run']['gold']}"
BRONZE_PATH = f"abfss://{mlh.WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{mlh.ITEMS['bronze_lh']['id']}/Tables"
ARGS = {"workspace": W, "source": "bronze_lh", "schema": "sap"}
TARGETS = {"target_lakehouse": "silver_lh", "gold_lakehouse": "gold_lh"}


@pytest.fixture(autouse=True)
def _clean():
    flow_state.clear()
    yield
    assert mlh.WRITES == [] and wb15_fake.WRITES == []
    flow_state.clear()


def _build(monkeypatch, **targets):
    """create_pipeline's three notebooks, whole (the dry run's answer leaves the large ones out)."""
    p, info = server._source_inputs(W, "bronze_lh", "sap", None, None, None)
    info, refusal = server._write_info(info, "x", None, targets.get("target_lakehouse", ""))
    assert refusal is None
    ginfo, refusal = server._gold_info(info, targets.get("gold_lakehouse", ""), None)
    assert refusal is None
    b = server._pipeline_build(p, info, "sap", "silver", "gold", None, False, "sap_pipeline", "", "", None, gold_info=ginfo)
    return {n["name"]: n["content"] for n in b["notebooks"]}


# ------------------------------------------------------------------------------------------------ the dry run's line
def test_start_dry_run_says_where_each_layer_goes_in_one_line(monkeypatch):
    mlh.install(monkeypatch, "a")
    d = json.loads(server.start(**ARGS, step="dry_run"))
    assert d["stage"] == "dry_run" and d["layers_to"] == LINE
    assert LINE in d["say"] and len(d["say"].split()) <= 15
    runs = {r["tool"]: r["arguments"] for r in next(a for a in d["actions"] if a["kind"] == "dry_run_all")["runs"]}
    assert {k: runs["create_pipeline"][k] for k in TARGETS} == TARGETS
    assert runs["create_semantic_model"]["target_lakehouse"] == "silver_lh"
    assert "target_lakehouse" not in runs["create_data_agent"]               # the agent reads the source tables, as before


def test_the_first_card_says_where_silver_and_gold_go(monkeypatch):
    mlh.install(monkeypatch, "a")
    a = json.loads(server.start())
    assert a["suggested"]["rule"] == "L1" and a["say"].endswith(f"S{LINE[1:]}.") and len(a["say"].split()) <= 15


def test_all_three_dry_runs_in_at_most_four_taps_with_the_suggestion_taken(monkeypatch):
    mlh.install(monkeypatch, "a")
    card, taps = json.loads(server.start()), 0
    while card["stage"] != "dry_run":
        card = json.loads(server.start(**card["after"]["arguments"]))
        taps += 1
        assert taps < 5
    everything = next(a for a in card["actions"] if a["kind"] == "dry_run_all")
    taps += 1
    assert taps <= 4
    answers = {r["tool"]: json.loads(getattr(server, r["tool"])(**r["arguments"])) for r in everything["runs"]}
    assert not [t for t, a in answers.items() if a.get("error")]
    assert answers["create_pipeline"]["layers_to"] == LINE
    assert all(a["dry_run"] is True for a in answers.values())


# ------------------------------------------------------------------------------------------------ G2: the notebooks
def test_pipeline_dry_run_names_silver_lh_and_gold_lh(monkeypatch):
    mlh.install(monkeypatch, "a")
    a = json.loads(server.create_pipeline(**ARGS, name="sap_pipeline", **TARGETS))
    assert a["layers_to"] == LINE and a["target"]["lakehouse"] == "silver_lh" and a["gold_target"]["lakehouse"] == "gold_lh"
    assert all(r["url"].startswith(f"{server.FABRIC}/v1/workspaces/{mlh.WORKSPACE_ID}/") for r in a["rest"])


def test_silver_reads_bronze_by_its_onelake_path_and_is_attached_to_silver_lh(monkeypatch):
    mlh.install(monkeypatch, "a")
    nb = _build(monkeypatch, **TARGETS)
    silver = nb["silver_sap"]
    assert f'MIRROR_TABLES_PATH = "{BRONZE_PATH}"' in silver
    assert '"default_lakehouse_name": "silver_lh"' in silver and "of this workspace (one lakehouse per layer)" in silver
    assert "in another workspace" not in silver and "read-only, so" not in silver
    one = json.loads(server.create_silver_notebook(**ARGS, name="s", tables=["KNA1"], target_lakehouse="silver_lh"))
    assert one["layers_to"] == "silver → silver_lh" and "bronze_lh tables are only read" in one["summary"]


def test_gold_and_check_go_to_gold_lh_and_read_silver_by_three_part_name(monkeypatch):
    mlh.install(monkeypatch, "a")
    nb = _build(monkeypatch, **TARGETS)
    gold, check = nb["gold_sap"], nb["sap_pipeline_check"]
    assert '"default_lakehouse_name": "gold_lh"' in gold and '"default_lakehouse_name": "gold_lh"' in check
    assert 'SILVER_LAKEHOUSE = "silver_lh"' in gold and "q(SILVER_LAKEHOUSE, SILVER_SCHEMA, t)" in gold
    assert 'SILVER_SCHEMA = "silver_lh.silver"' in check
    from fabric_backend import pipeline as _pipeline
    assert _pipeline._CHECK["_tbl"]("silver_lh.silver", "KNA1") == "`silver_lh`.`silver`.`KNA1`"
    assert _pipeline._CHECK["_tbl"]("silver", "KNA1") == "`silver`.`KNA1`"            # one lakehouse: as before
    g = json.loads(server.create_gold_views(**ARGS, name="g", **TARGETS))
    assert g["layers_to"] == LINE and "of silver_lh, written to gold_lh" in g["summary"]
    assert all("`silver_lh`.`silver`." in v["sql"] and "`gold`." in v["sql"] for v in g["views"])


def test_gold_beside_silver_when_only_a_silver_lakehouse_is_named(monkeypatch):
    mlh.install(monkeypatch, "a")
    a = json.loads(server.create_pipeline(**ARGS, name="sap_pipeline", target_lakehouse="silver_lh"))
    assert a["layers_to"] == "silver → silver_lh, gold → silver_lh" and "gold_target" not in a
    assert sf.layer_targets("bronze_lh", ["bronze_lh", "silver_lh"]) == {"silver": "silver_lh", "gold": "silver_lh"}
    assert sf.layer_targets("bronze_lh", ["bronze_lh", "gold_lh"]) is None              # no silver: into the source
    assert sf.layer_targets("sap_lh", ["sap_lh", "silver_lh", "gold_lh"]) is None       # not named as the raw layer


def test_a_target_that_is_not_in_the_workspace_is_refused_and_nothing_is_written(monkeypatch):
    mlh.install(monkeypatch, "a")
    a = json.loads(server.create_pipeline(**ARGS, name="p", target_lakehouse="nowhere_lh"))
    assert a["kind"] == "not_found" and "'nowhere_lh' is not a lakehouse of this workspace" in a["error"]
    b = json.loads(server.create_pipeline(**ARGS, name="p", target_lakehouse="silver_lh", gold_lakehouse="nowhere_lh"))
    assert b["kind"] == "not_found" and "gold lakehouse 'nowhere_lh'" in b["error"]


# ------------------------------------------------------------------------------------------------ G3: what reads it
def test_model_ontology_and_agent_read_the_lakehouse_the_build_wrote(monkeypatch):
    mlh.install(monkeypatch, "a")
    m = json.loads(server.create_semantic_model(**ARGS, name="m", target_lakehouse="silver_lh"))
    assert 'Sql.Database("mlh.datawarehouse.fabric.microsoft.com", "silver_lh")' in m["parts"]["definition/expressions.tmdl"]
    assert m["layers_to"] == "model → silver_lh (silver)" and "silver_lh" in m["first"]   # not run yet: said first
    assert "`silver_lh`, schema `silver`" in m["parts"]["README.generated.md"]          # each table's schemaName: silver
    o = json.loads(server.create_ontology(**ARGS, name="o", target_lakehouse="silver_lh"))
    assert mlh.ITEMS["silver_lh"]["id"] in json.dumps(o) and mlh.ITEMS["bronze_lh"]["id"] not in json.dumps(o)
    g = json.loads(server.create_data_agent(**ARGS, name="ag", layer="gold", **TARGETS))
    assert g["agent"]["datasource"]["lakehouseReference"]["itemId"] == mlh.ITEMS["gold_lh"]["id"]
    assert g["layers_to"] == "agent → gold_lh (gold)"
    s = json.loads(server.create_data_agent(**ARGS, name="ag", layer="silver", **TARGETS))
    assert s["agent"]["datasource"]["lakehouseReference"]["itemId"] == mlh.ITEMS["silver_lh"]["id"]


# ------------------------------------------------------------------------------------------------ nothing else changes
def test_without_the_new_parameters_nothing_changes(monkeypatch):
    mlh.install(monkeypatch, "a")
    plain = json.loads(server.create_pipeline(**ARGS, name="p"))
    same = json.loads(server.create_pipeline(**ARGS, name="p", target_lakehouse="bronze_lh", gold_lakehouse="bronze_lh"))
    assert plain == same and "layers_to" not in plain and "target" not in plain
    assert _build(monkeypatch) == _build(monkeypatch, target_lakehouse="bronze_lh", gold_lakehouse="")
    model = json.loads(server.create_semantic_model(**ARGS, name="m"))
    assert "layers_to" not in model and '"bronze_lh")' in model["parts"]["definition/expressions.tmdl"]


def test_the_one_lakehouse_demo_passes_no_targets(monkeypatch):
    wb15_fake.install(monkeypatch)
    chosen = json.loads(server.start())["chosen"]
    d = json.loads(server.start(**{k: chosen[k] for k in ("workspace", "source", "schema")}, step="dry_run"))
    assert "layers_to" not in d and d["say"] == "One tap dry-runs everything. Nothing is created."
    runs = next(a for a in d["actions"] if a["kind"] == "dry_run_all")["runs"]
    assert not any(k in r["arguments"] for r in runs for k in TARGETS)
