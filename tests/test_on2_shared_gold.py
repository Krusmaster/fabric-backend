"""ON2 (builds on ON1; docs/SMOOTH/COMBINE-SOURCES.md section 8): the pipeline builds the shared gold from the accepted
SAP and Dynamics 365 matches, and create_ontology creates the one shared Fabric IQ ontology once that gold exists.

On the synthetic pair tests/fixtures/sap_dynamics.py (SAP demo + Dataverse demo, schemas `sap` and `d365` of one product
lakehouse). What must hold: create_pipeline's dry run on the path is the shared gold notebook and a one-step pipeline;
its SQL, run on SQLite over the fixture's rows, builds dim_customer, dim_product and the re-keyed facts with every
ambiguous row apart, counted exactly as ON1 counts the match; create_ontology with dry_run=false answers not_yet and
names the pipeline while the gold is missing, and writes the shared ontology (the dry run's definition, part for part)
once it is there; verify_build reads it back and compares it with the dry run. Nothing reaches Fabric: the fixture
fails any POST, PATCH, PUT or DELETE, and the creates go to FakeFabric below, which records them. Not run against
Fabric."""
from __future__ import annotations

import base64
import importlib
import json
import sqlite3

import pytest
import wb15_fake
from fixtures import multi_lakehouse as mlh
from fixtures import sap_dynamics as sd

from fabric_backend import flow_state, server
from fabric_backend import shared_gold as sg
from fabric_backend import shared_ontology as so
from fabric_backend.notebook import parse

deploy_mod = importlib.import_module("fabric_backend.deploy")     # the package's `deploy` is a function of that name

ARGS = {"workspace": sd.WORKSPACE, "source": sd.SOURCE, "schema": sd.SCHEMA}
BOTH = [sd.CUSTOMER, sd.PRODUCT]
GOLD_KEY = f"{sd.SOURCE}.gold"
# ON1's counts, as the gold must keep them: matched, ambiguous, only in D365 (only_a), only in SAP (only_b)
COUNTS = {c: {k: sd.EXPECTED[c]["counts"][k] for k in ("matched", "ambiguous", "only_a", "only_b")} for c in sd.EXPECTED}


class FakeFabric:
    """Fabric's item store as the creating tools see it: every create is recorded (`writes`) and kept as an item with
    its definition, which verify_build reads back. Nothing leaves the process."""

    def __init__(self):
        self.writes: list[dict] = []
        self.items: list[dict] = []
        self.parts: dict[str, dict[str, str]] = {}

    def create(self, route, item_type, envelope, workspace, token_provider=None, *a, **k):
        name = envelope["displayName"]
        hit = next((i for i in self.items if i["type"] == item_type and i["displayName"] == name), None)
        iid = hit["id"] if hit else f"fake-{item_type.lower()}-{len(self.items) + 1}"
        if not hit:
            self.items.append({"id": iid, "type": item_type, "displayName": name})
        self.parts[iid] = {p["path"]: base64.b64decode(p["payload"]).decode("utf-8") for p in envelope["definition"]["parts"]}
        self.writes.append({"route": route, "type": item_type, "name": name, "workspace": workspace, "id": iid})
        return {"status": "Succeeded", "mode": "updated" if hit else "created", "id": iid}

    def install(self, monkeypatch):
        monkeypatch.setattr(deploy_mod, "create_item_with_definition", self.create)
        monkeypatch.setattr(server, "_create_ontology", lambda env, ws, token_provider=None: self.create("ontologies", "Ontology", env, ws))
        lakehouses = [{"id": it["id"], "type": "Lakehouse", "displayName": n} for n, it in sd.ITEMS.items()]
        monkeypatch.setattr(server, "_workspace_items", lambda ws, headers: lakehouses + list(self.items))
        monkeypatch.setattr(server, "_item_definition_parts", lambda ws, route, iid, headers, fmt=None: dict(self.parts[iid]))
        return self


@pytest.fixture(autouse=True)
def _clean():
    flow_state.clear()
    server._RECENT.clear()
    yield
    assert mlh.WRITES == [] and wb15_fake.WRITES == []
    flow_state.clear()


@pytest.fixture
def fabric(monkeypatch):
    ws = sd.install(monkeypatch)
    fake = FakeFabric().install(monkeypatch)
    fake.ws = ws
    return fake


def _accept(items):
    """The person's taps on the path: each match accepted through start's own decision (the flow state)."""
    kept = [{"item": i, "review": "accepted", "reason": "decided in the test"} for i in items]
    json.loads(server.start(**ARGS, step="decide", plan={"decisions": kept}))


def _notebook(pipeline_answer: dict) -> dict:
    return sg.notebook_cells_data(pipeline_answer["notebooks"][0]["content"])


def _lite(sql: str) -> str:
    """Spark SQL of the shared gold -> SQLite, by fixed replacements (as tests/test_sm7_combine.py does)."""
    sql = sql.replace("CREATE OR REPLACE TABLE", "CREATE TABLE").replace("`", '"').replace(" AS STRING)", " AS TEXT)")
    return sql.replace("REGEXP_REPLACE(", "LTRIM(").replace(", '^0+', '')", ", '0')")


def _build_gold(fake: FakeFabric, monkeypatch, statements, skip=()) -> sqlite3.Connection:
    """Runs the notebook's statements on the fixture's rows, into the product lakehouse's `gold` schema (a file of its
    own, as the other schemas), and lets the fake SQL endpoint list it."""
    ws = fake.ws
    con = sqlite3.connect(":memory:")
    con.create_function("PATINDEX", 2, mlh._patindex, deterministic=True)
    for schema in ("sap", "d365"):
        con.execute(f"ATTACH DATABASE ? AS [{schema}]", (ws.file(sd.LAKEHOUSES[sd.SOURCE][schema][1]),))
    con.execute("ATTACH DATABASE ? AS gold", (ws.file(GOLD_KEY),))
    info = []
    for name, sql in statements:
        if name in skip:
            continue
        con.execute(_lite(sql))
        info += [(name, r[1], r[2] or "nvarchar", r[0] + 1) for r in con.execute(f'PRAGMA gold.table_info("{name}")')]
    con.commit()
    ws.info[GOLD_KEY] = info
    monkeypatch.setitem(sd.LAKEHOUSES[sd.SOURCE], "gold", ("gold", GOLD_KEY))
    return con


# ------------------------------------------------------------------------------------------------ the pipeline
def test_the_pipeline_dry_run_is_the_shared_gold_from_the_accepted_matches(fabric):
    _accept(BOTH)
    o = json.loads(server.create_pipeline(**ARGS, name="sales_360_gold"))
    assert o["dry_run"] is True and fabric.writes == []
    assert o["combined"]["shared"] == ["Customer", "Product"]
    assert o["combined"]["builds"] == ["gold.xref_customer", "gold.dim_customer", "gold.fact_d365_opportunity",
                                       "gold.fact_sap_sales_order", "gold.fact_sap_delivery", "gold.fact_sap_invoice",
                                       "gold.xref_product", "gold.dim_product"]
    assert o["combined"]["binds"] == ["dim_customer", "dim_product", "fact_d365_opportunity", "fact_sap_delivery",
                                      "fact_sap_invoice", "fact_sap_sales_order"]
    assert o["steps"] == ["Shared gold: sales_360_gold_shared_gold"]
    nb = _notebook(o)
    assert [n for n, _ in nb["STATEMENTS"]] == [x.split(".", 1)[1] for x in o["combined"]["builds"]]
    assert all(s.startswith(f"CREATE OR REPLACE TABLE `gold`.`{n}` AS") for n, s in nb["STATEMENTS"])   # tables, no views
    assert nb["GOLD_SCHEMA"] == "gold" and nb["SOURCE_SCHEMAS"] == ["d365", "sap"]
    assert {c["entity"]: {k: c["accepted"][k] for k in COUNTS["customer"]} for c in nb["CHECKS"]} == {
        "Customer": COUNTS["customer"], "Product": COUNTS["product"]}
    for kind, text in parse(o["notebooks"][0]["content"]):
        if kind == "code":
            compile(text, "notebook", "exec")                                       # the cells are Python
    acts = o["pipeline"]["content"]["properties"]["activities"]
    assert [a["name"] for a in acts] == ["Shared gold"]
    assert acts[0]["typeProperties"]["notebookId"] == "<id of the notebook sales_360_gold_shared_gold>"
    assert "schedule" not in json.dumps(o["pipeline"]["content"]).lower().replace("no schedule", "")


def test_the_pipeline_and_the_ontology_dry_run_carry_the_same_gold(fabric):
    _accept(BOTH)
    nb = _notebook(json.loads(server.create_pipeline(**ARGS, name="p")))
    o = json.loads(server.create_ontology(**ARGS, name="sales_360"))
    assert dict(nb["STATEMENTS"]) == o["gold_sql"]
    assert o["gold_tables"] == ["dim_customer", "dim_product", "fact_d365_opportunity", "fact_sap_delivery",
                                "fact_sap_invoice", "fact_sap_sales_order"]


def test_the_gold_is_built_from_the_accepted_matches_with_ambiguous_rows_apart(fabric, monkeypatch):
    _accept(BOTH)
    nb = _notebook(json.loads(server.create_pipeline(**ARGS, name="p")))
    con = _build_gold(fabric, monkeypatch, nb["STATEMENTS"])
    for c in nb["CHECKS"]:
        cur = con.execute(_lite(c["counts_sql"]))
        got = dict(zip([d[0] for d in cur.description], cur.fetchone()))
        assert got == c["accepted"]                                                 # counted exactly as ON1 counts
        assert {k: got[k] for k in COUNTS[c["concept"]]} == COUNTS[c["concept"]]
        for label, sql in c["invariants"]:
            assert con.execute(_lite(sql)).fetchone()[0] == 0, label                # no rule is broken
    # the two accounts that carry SAP customer 13: two keys of their own, neither the SAP customer's
    rows = con.execute('SELECT x.customer_key, x.only_in, x.ambiguous FROM gold.xref_customer AS x JOIN d365.account AS a '
                       'ON a.accountid = x.d365_accountid WHERE a.accountnumber IN (\'13\', \'0000000013\')').fetchall()
    assert len(rows) == 2 and len({r[0] for r in rows}) == 2 and all(r[1:] == ("d365", 1) for r in rows)
    sap13 = con.execute("SELECT customer_key, only_in, ambiguous, d365_accountid FROM gold.xref_customer "
                        "WHERE sap_KUNNR = '0000000013'").fetchall()
    assert len(sap13) == 1 and sap13[0][1:] == ("sap", 1, None) and sap13[0][0] not in {r[0] for r in rows}
    # one row per conformed customer and product; every source row once
    assert con.execute("SELECT COUNT(*), COUNT(DISTINCT customer_key) FROM gold.dim_customer").fetchone() == (9, 9)
    assert con.execute("SELECT COUNT(*), COUNT(DISTINCT product_key) FROM gold.dim_product").fetchone() == (5, 5)
    assert con.execute("SELECT SUM(ambiguous) FROM gold.dim_customer").fetchone()[0] == 3     # 2 accounts + SAP's 13
    for fact, src in (("fact_sap_sales_order", "sap.VBAK"), ("fact_sap_invoice", "sap.VBRK"),
                      ("fact_sap_delivery", "sap.LIKP"), ("fact_d365_opportunity", "d365.opportunity")):
        assert con.execute(f"SELECT COUNT(*) FROM gold.{fact}").fetchone() == con.execute(f"SELECT COUNT(*) FROM {src}").fetchone()
    con.close()


def test_create_pipeline_writes_the_notebook_then_the_pipeline_and_runs_nothing_unasked(fabric):
    _accept(BOTH)
    o = json.loads(server.create_pipeline(**ARGS, name="p", dry_run=False))
    assert o["result"]["status"] == "Succeeded" and "kind" not in o
    assert [(w["type"], w["name"]) for w in fabric.writes] == [("Notebook", "p_shared_gold"), ("DataPipeline", "p")]
    content = json.loads(fabric.parts[fabric.writes[1]["id"]]["pipeline-content.json"])
    assert content["properties"]["activities"][0]["typeProperties"]["notebookId"] == fabric.writes[0]["id"]
    assert "run" not in o["result"] and "jobs" not in o
    n = len(fabric.writes)
    a = json.loads(server.create_pipeline(**ARGS, name="p", dry_run=False, run_once=True))      # no confirm_jobs: no
    assert a["kind"] == "needs_confirmation" and len(fabric.writes) == n


def test_without_an_accepted_match_the_pipeline_is_as_before(fabric):
    o = json.loads(server.create_pipeline(**ARGS, name="p"))
    assert "combined" not in o and [s.split(":")[0] for s in o["steps"][:3]] == ["Silver tables", "Gold views",
                                                                                 "Check keys, orphans and sums"]


# ------------------------------------------------------------------------------------------------ create_ontology
def test_without_the_gold_create_answers_not_yet_and_names_the_pipeline(fabric):
    _accept(BOTH)
    a = json.loads(server.create_ontology(**ARGS, name="sales_360", dry_run=False))
    assert a["kind"] == "not_yet" and fabric.writes == []
    assert a["first"] == "Run the pipeline that builds the shared gold."
    assert a["next_steps"][0]["tool"] == "create_pipeline" and a["next_steps"][0]["arguments"]["schema"] == sd.SCHEMA
    assert {"gold.dim_customer", "gold.dim_product", "gold.fact_sap_sales_order"} <= set(a["missing"])


def test_gold_with_a_table_missing_is_not_yet(fabric, monkeypatch):
    _accept(BOTH)
    nb = _notebook(json.loads(server.create_pipeline(**ARGS, name="p")))
    _build_gold(fabric, monkeypatch, nb["STATEMENTS"], skip=("dim_product",)).close()
    a = json.loads(server.create_ontology(**ARGS, name="sales_360", dry_run=False))
    assert a["kind"] == "not_yet" and a["missing"] == ["gold.dim_product"] and fabric.writes == []


def test_with_the_gold_create_writes_the_shared_ontology_of_the_dry_run(fabric, monkeypatch):
    _accept(BOTH)
    nb = _notebook(json.loads(server.create_pipeline(**ARGS, name="p")))
    _build_gold(fabric, monkeypatch, nb["STATEMENTS"]).close()
    dry = json.loads(server.create_ontology(**ARGS, name="sales_360"))
    assert fabric.writes == []
    o = json.loads(server.create_ontology(**ARGS, name="sales_360", dry_run=False))
    assert o["dry_run"] is False and o["result"]["status"] == "Succeeded" and "kind" not in o
    assert o["gold"]["missing"] == [] and o["combined"]["shared"] == ["Customer", "Product"]
    assert [(w["route"], w["type"], w["name"]) for w in fabric.writes] == [("ontologies", "Ontology", "sales_360")]
    written = fabric.parts[fabric.writes[0]["id"]]
    assert set(written) == set(dry["parts"]) | set(dry.get("omitted") or [])
    assert all(written[k] == v for k, v in dry["parts"].items())                   # part for part the dry run
    assert "entityName: dim_customer" in written["tables/Customer.tmdl"]
    assert "sourceColumn: ambiguous" in written["tables/Customer.tmdl"]


# ------------------------------------------------------------------------------------------------ verify_build
def test_verify_build_reads_the_shared_ontology_back_and_compares_it_with_the_dry_run(fabric, monkeypatch):
    _accept(BOTH)
    nb = _notebook(json.loads(server.create_pipeline(**ARGS, name="p")))
    _build_gold(fabric, monkeypatch, nb["STATEMENTS"]).close()
    json.loads(server.create_ontology(**ARGS, name="sales_360", dry_run=False))
    v = json.loads(server.verify_build(**ARGS, items={"ontology": "sales_360"}))
    line = v["lines"][0]
    assert v["writes"] == "nothing: every call is a read" and len(fabric.writes) == 1
    assert "Definition as the dry run (9 entity types, 6 with key, 7 relationship types" in line["said"]
    assert line["state"] == "differs" and line["state_check"]["check"] == "graph"    # the graph is the person's step
    fabric.items.append({"id": "fake-graph", "type": "GraphModel", "displayName": "sales_360_graph"})   # refreshed in Fabric
    line = json.loads(server.verify_build(**ARGS, items={"ontology": "sales_360"}))["lines"][0]
    assert line["state"] == "verified", line["said"]
    iid = fabric.writes[0]["id"]                                                    # someone removes an entity in Fabric
    fabric.parts[iid] = {k: t for k, t in fabric.parts[iid].items() if k != "entities/Product.tmdl"}
    line = json.loads(server.verify_build(**ARGS, items={"ontology": "sales_360"}))["lines"][0]
    assert line["state"] == "differs" and "Product" in line["said"], line["said"]


def test_missing_names_tables_and_columns():
    from fabric_backend.schema import Column, Schema, Table
    model = {"entities": [{"binding": {"table": "dim_customer", "built_by": "gold_sql"},
                           "properties": [{"name": "customer_key"}, {"name": "ambiguous"}]},
                          {"binding": {"table": "salesorder", "built_by": "source"}, "properties": [{"name": "x"}]},
                          {"binding": {"table": "dim_product", "built_by": "gold_sql"}, "properties": [{"name": "product_key"}]}]}
    g = Schema(schema="gold")
    g.tables["dim_customer"] = Table("dim_customer", [Column("customer_key", "bigint")], [], schema="gold")
    assert sg.missing(g, model) == ["gold.dim_customer.ambiguous", "gold.dim_product"]
    assert sg.missing(None, model) == ["gold.dim_customer", "gold.dim_product"]
    assert so.GOLD == sg.GOLD
