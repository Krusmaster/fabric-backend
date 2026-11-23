"""W1 (23 November 2026): the engine's part of what Gustav found in the Model item editor, on the synthetic shop sample.

- /schemas leaves Fabric's system schemas out (_rsc and any name starting with "_"; the SQL already left out sys,
  INFORMATION_SCHEMA, queryinsights, guest and db_*), also on the fallback query; a schema named in a request is still
  read as before.
- The suggested data products' rule is in plain words (the method's name is for the docs).
- The data flow says what the data agent's own card says: an agent on silver reads silver when it is filled, the
  source until then; the "reads the source tables directly" note no longer names it.
- The editor's dry run carries BL54's two lines: the workspace roles proposed and the data contract.
- The pipeline card's "Run the pipeline once" is left out when Create started a run whose first read did not answer.
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("jwt")

import golden_support as gs  # noqa: E402
from test_workload_api import SRC, keys, tok  # noqa: E402,F401
from test_workload_build import _build, _post, _review, make  # noqa: E402,F401
from fabric_backend import data_flow, server, workload_api  # noqa: E402


# ------------------------------------------------------------------ 1. the schema list ------------------------------

@pytest.mark.parametrize("name", ["_rsc", "_anything", "sys", "INFORMATION_SCHEMA", "queryinsights", "guest", "db_owner"])
def test_system_schemas_are_told_apart(name):
    assert workload_api.system_schema(name)


@pytest.mark.parametrize("name", ["dbo", "shop", "sap", "silver", "gold", "krusgraph", "sap_silver", "rsc", "sys_data"])
def test_source_and_krusgraph_schemas_are_not_system_schemas(name):
    assert not workload_api.system_schema(name)


def _schemas(monkeypatch, rows, fail_schemata=False):
    """run_schemas over a SQL endpoint double that answers `rows` (TABLE_SCHEMA, TABLE_COUNT)."""
    seen = []

    def execute(sql):
        seen.append(sql)
        if fail_schemata and sql == workload_api.SCHEMATA_SQL:
            raise RuntimeError("no SCHEMATA")
        return [{"TABLE_SCHEMA": s, "TABLE_COUNT": n} for s, n in rows]
    monkeypatch.setattr(server, "_headers", lambda ctx: {})
    monkeypatch.setattr(server, "_workspace_id", lambda ws, h: ws)
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, h: {"id": src})
    monkeypatch.setattr(server, "_execute_factory", lambda item, cred: execute)
    monkeypatch.setattr(server.auth, "sql", lambda ctx: None)
    return workload_api.run_schemas({"workspace": gs.WS, "source": "demo_lh", "source_name": "demo_lh"}), seen


@pytest.mark.parametrize("fallback", [False, True])
def test_the_list_leaves_rsc_out_and_counts_and_preselects_without_it(monkeypatch, fallback):
    out, seen = _schemas(monkeypatch, [("_rsc", 0), ("dbo", 0), ("shop", 7)], fail_schemata=fallback)
    assert out["schemas"] == [{"schema": "dbo", "tables": 0}, {"schema": "shop", "tables": 7}]
    assert out["preselect"] == "shop"
    assert out["note"].startswith("1 of 2 schema(s) hold tables.")
    assert seen[-1] == (server.SCHEMAS_SQL if fallback else workload_api.SCHEMATA_SQL)


def test_an_empty_lakehouse_lists_dbo_alone_and_preselects_it(monkeypatch):
    out, _ = _schemas(monkeypatch, [("_rsc", 0), ("dbo", 0)])
    assert out["schemas"] == [{"schema": "dbo", "tables": 0}] and out["preselect"] == "dbo"


def test_a_schema_named_in_a_request_is_not_filtered():
    """Only the list leaves system schemas out: a request that names one is passed on as it is."""
    req = workload_api._source({"workspace": gs.WS, "source": "demo_lh", "schema": "_rsc"})
    assert req["schema"] == "_rsc"


# ------------------------------------------------------------------ 3. the suggestions in plain words ----------------

def test_the_suggestion_rule_names_no_method():
    for word in ("domain_draft", "propose_plan", "Leiden", "("):
        assert word not in workload_api.SUGGEST_RULE
    assert workload_api.SUGGEST_RULE.endswith("stays with that parent.")


# ------------------------------------------------------------------ the dry run's words agree -----------------------

AGENT_SILVER = "The agent reads the silver tables in silver only (cleaned, keys and links held), when they are in the lakehouse; otherwise the source tables in shop. Never two layers at once."


def test_agent_reads_follows_the_agent_card():
    assert workload_api.agent_reads({"agent": {"layer_words": AGENT_SILVER}}, "shop") == \
        "reads the silver tables in silver when they are filled; until then the source tables in shop"
    assert workload_api.agent_reads({"answer": {"layer": AGENT_SILVER.replace("silver tables in silver", "gold views in gold")}}, "shop") == \
        "reads the gold views in gold when they are filled; until then the source tables in shop"
    assert workload_api.agent_reads({"agent": {"layer_words": "The agent reads the source tables in shop only."}}, "shop") is None
    assert workload_api.agent_reads({}, "shop") is None


def test_the_flow_box_and_note_say_what_the_agent_card_says(make):
    client, fake, priv = make()
    outputs = [{"kind": "silver_notebook", "name": "shop_silver"}, {"kind": "gold_views", "name": "shop_gold"},
               {"kind": "pipeline", "name": "shop_flow"}, {"kind": "graphql", "name": "shop_model_api"},
               {"kind": "data_agent", "name": "shop_agent", "agent": {"layer": "silver", "publish": False, "copilot": False}}]
    r, _ = _build(client, priv, outputs, dry_run=True)
    out = r.json()
    assert r.status_code == 200 and out["refused"] == 0, out
    card = next(c for c in out["outputs"] if c["output"] == "data_agent")
    said = card["agent"]["layer_words"]
    assert said.startswith("The agent reads the silver tables in silver only")
    box = next(n for n in out["flow"]["nodes"] if n["id"] == "item:data_agent")
    assert box["lines"] == ["reads the silver tables in silver when they are filled; until then the source tables in shop"]
    notes = " ".join(out["flow"]["notes"])
    assert "Data agent reads the source tables" not in notes and "Data agent" not in notes
    assert "API for GraphQL reads the source tables (bronze) directly" in notes          # the others as before
    edge = next(e for e in out["flow"]["edges"] if e["to"] == "item:data_agent")
    assert edge["label"] == "until silver is filled"


def test_an_agent_on_the_source_is_drawn_as_before():
    items = [{"output": "data_agent", "label": "Data agent", "name": "a", "reads": "reads the source tables in shop (bronze) directly"}]
    from fabric_backend import demo
    p = demo.plan(demo.schema("shop"), keys=demo.DEMO_KEYS)
    flow = data_flow.flow(p, demo.FLOW_INFO, {"gold_views": "g"}, items=items)
    assert any(n.startswith("Data agent reads the source tables") for n in flow["notes"])
    assert next(e for e in flow["edges"] if e["to"] == "item:data_agent")["label"] == "reads the source tables"


def test_the_dry_run_carries_bl54_s_two_lines(make):
    client, fake, priv = make()
    outputs = [{"kind": "pipeline", "name": "shop_flow"}, {"kind": "semantic_model", "name": "shop_sales"}]
    plain = _build(client, priv, outputs, dry_run=True)[0].json()
    assert plain["access"].startswith("Workspace roles proposed: ") and plain["access"].endswith("Nothing is written.")
    assert "contract" not in plain                                    # no data product in this build
    product = _build(client, priv, outputs, dry_run=True, product={"name": "Shop sales"})[0].json()
    assert product["contract"] == ("Data contract: an ODCS v3.1.0 draft from the counted checks comes with the data product. "
                                   "Nothing is written to Fabric.")
    assert "data_contract.draft" not in json.dumps(product)


def test_access_line_maps_the_editor_s_outputs():
    line = workload_api.access_line(["silver_notebook", "gold_views", "pipeline", "semantic_model", "report", "data_agent"])
    assert line.startswith("Workspace roles proposed: ") and "(the report inherits the model's)" in line


# ------------------------------------------------------------------ the pipeline card after Create -----------------

@pytest.mark.parametrize("run,left", [
    ({"status": "Running", "run_id": "r1"}, False),
    ({"status": "Unknown", "run_id": "r1"}, False),
    ({"status": "Unknown"}, True),
    ({"status": "NotStarted"}, True),
    ({}, True),
])
def test_run_once_step_only_when_no_run_was_started(run, left):
    steps = workload_api._portal_steps("pipeline", {"result": {"run": run} if run else {}}, {"pipeline": "p"})
    assert (workload_api.RUN_STEP in steps) is left


# ------------------------------------------------------------------ the Data product step: words of the analyses ----

def test_one_row_of_a_table_in_words():
    from fabric_backend.advanced_stages import one_row_of
    assert [one_row_of(t) for t in ("orders", "order_items", "categories", "addresses", "boxes", "people", "status",
                                    "VBRK", "sap_vbak")] == \
        ["order", "order item", "category", "address", "box", "person", "status", "VBRK", "sap_vbak"]


def test_the_analyses_say_one_row_per_order_and_the_text_columns_of_orders():
    from fabric_backend import advanced_stages as A
    case = A.FIXTURE_CASES[0]
    got = A.stages(case["grain"], case["source"], case["links"])
    why = "\n".join(a["why"] for a in got["analyses"])
    assert "One row per order with its date: the number of orders per week" in why
    assert "the text columns of orders" in why and "orders's" not in why and "per orders with" not in why
    cells = json.dumps(got["analyses"])
    assert "one row per orders" not in cells and "one row per order" in cells
