"""SM5 (docs/SMOOTH/PLAN.md, row 4): a workspace with several lakehouses, on the synthetic fixture
tests/fixtures/multi_lakehouse.py. Layouts (a) one lakehouse per layer, (b) one per source and (c) schemas in one
lakehouse each plan; in (a) the source is suggested by name rules with 0 extra taps; in (c) one plan over `sap` + `crm`
keys its tables `schema.table`, and the join check counts a link across the two schemas on one connection. Nothing is
written: the fixture fails any POST, PATCH, PUT or DELETE."""
from __future__ import annotations

import json

import pytest
import wb15_fake
from fixtures import multi_lakehouse as mlh

from fabric_backend import flow_state, infer, multi_schema, server
from fabric_backend import start_flow as sf
from fabric_backend.dialects import TSQL

W = mlh.WORKSPACE


@pytest.fixture(autouse=True)
def _clean():
    flow_state.clear()
    yield
    assert mlh.WRITES == [] and wb15_fake.WRITES == []
    flow_state.clear()


def _words(text: str) -> int:
    return len(str(text).split())


# ------------------------------------------------------------------------------------------------ (a) one per layer
def test_layout_a_suggests_bronze_lh_with_zero_extra_taps(monkeypatch):
    e = mlh.EXPECTED["a"]
    mlh.install(monkeypatch, "a")
    a = json.loads(server.start())                       # the first card, no tap yet
    assert a["stage"] == "data" and a["line"] == f"{W} › {e['suggested']} › {e['schema']} ✓"
    assert a["suggested"]["rule"] == e["rule"] and sorted(a["suggested"]["others"]) == sorted(e["untouched"])
    assert e["suggested"] in a["say"] and _words(a["say"]) <= 15
    assert a["after"]["label"] == "Next: Check" and a["after"]["arguments"]["source"] == e["suggested"]
    assert set(a["picked"]) == {"workspace", "source", "schema"}
    monkeypatch.undo()
    wb15_fake.install(monkeypatch)                       # the one-lakehouse demo starts on the same card: 0 extra taps
    one = json.loads(server.start())
    assert one["stage"] == a["stage"] == "data" and "suggested" not in one
    assert one["say"] == "Your data, picked for you. Change it if it is wrong."


def test_layout_a_change_shows_the_suggestion_chosen_and_next_works(monkeypatch):
    mlh.install(monkeypatch, "a")
    s = json.loads(server.start(workspace=W, step="source"))
    chosen = [x for x in s["actions"] if x["kind"] == "choose" and x.get("selected")]
    assert [x["label"] for x in chosen] == ["bronze_lh"] and "next_waits" not in s
    assert s["choices"]["suggested"]["rule"] == "L1" and s["say"].startswith("I suggest bronze_lh")
    hints = {x["label"]: x["hint"] for x in s["actions"] if x["kind"] == "choose"}
    assert hints["silver_lh"].endswith("silver layer: not read") and hints["gold_lh"].endswith("gold layer: not read")
    assert s["after"]["arguments"] == {"workspace": W, "source": "bronze_lh"}


def test_layout_a_plans_bronze_and_leaves_silver_and_gold_alone(monkeypatch):
    ws = mlh.install(monkeypatch, "a")
    p = json.loads(server.plan_backend(workspace=W, source="bronze_lh", schema="sap", detail="summary"))
    assert p["summary"].startswith(f"{mlh.EXPECTED['a']['tables']} tables")
    assert {c.lakehouse for c in ws.connections} == {"bronze_lh"}


# ------------------------------------------------------------------------------------------------ (b) one per source
def test_layout_b_plans_each_source_lakehouse_and_suggests_the_product_lakehouse(monkeypatch):
    e = mlh.EXPECTED["b"]
    mlh.install(monkeypatch, "b")
    a = json.loads(server.start())
    assert a["stage"] == "schema" and a["chosen"]["source"] == e["suggested"]    # two schemas: the person picks
    labels = [x["label"] for x in a["actions"] if x["kind"] == "choose"]
    assert set(labels) == {"crm", "sap", "crm+sap"} and a["next_waits"]["why"] == "Choose a schema first."
    for lakehouse, schema in e["sources"].items():
        p = json.loads(server.plan_backend(workspace=W, source=lakehouse, schema=schema, detail="full"))
        assert p["relationships"] and not any("." in k for k in p["keys"])     # one schema: bare names, as before
    p = json.loads(server.plan_backend(workspace=W, source="crm_lh", schema="crm_silver", detail="full"))
    assert "Account" in p["keys"]
    cols, _, rows = mlh.rows("crm")["Account"]
    i = cols.index("SAP_Customer_No__c")
    assert sum(r[i] is not None for r in rows) == e["match"]["filled"] and len(rows) == e["match"]["of"]


# ------------------------------------------------------------------------------------------------ (c) schemas in one
def test_layout_c_one_plan_over_sap_and_crm_keys_tables_schema_dot_table(monkeypatch):
    e = mlh.EXPECTED["c"]
    ws = mlh.install(monkeypatch, "c")
    p = json.loads(server.plan_backend(workspace=W, source="sales_product_lh", schema=e["schema"], detail="full"))
    tables = set(p["keys"]) | {t for t in p.get("keyless") or []}
    assert len(tables) == e["tables"] and all(t.split(".")[0] in e["schemas"] for t in tables)
    assert all(x in tables for x in e["examples"])
    assert p["keys"]["sap.KNA1"]["columns"] == ["MANDT", "KUNNR"]               # the SAP pack in sap ...
    assert p["keys"]["crm.Account"]["columns"] == ["Id"]                        # ... and the Salesforce pack in crm
    assert p["pack"]["by_schema"] == {"sap": "sap", "crm": "salesforce"}
    assert p["summary"].startswith(f"{e['tables']} tables, {e['tables']} with keys")
    assert "recognised by a pack per schema" in p["summary"]
    assert len(ws.connections) == 1                                             # both schemas on one connection
    whole = infer.plan(multi_schema.combine([ws.read_schema("sales_product_lh", n) for n in ("sap", "crm")]))
    rels = {(r.source, r.target) for r in whole.relationships}                  # every link (the answer is cut for size)
    assert ("sap.VBAK", "sap.KNA1") in rels and ("crm.Contact", "crm.Account") in rels
    assert all(r.source.split(".")[0] == r.target.split(".")[0] for r in whole.relationships)   # none guessed across
    assert "sap_KNA1" in whole.mermaid()                                        # the map's names stay valid


def test_layout_c_the_join_check_counts_across_the_two_schemas_on_one_connection(monkeypatch):
    e = mlh.EXPECTED["c"]
    ws = mlh.install(monkeypatch, "c")
    v = json.loads(server.validate_plan(workspace=W, source="sales_product_lh", schema=e["schema"],
                                        confirmed=[e["link"]], detail="full"))
    link = next(r for r in v["relationships"] if r["source"] == "crm.Account" and r["target"] == "sap.KNA1")
    assert link["rows_with_value"] == e["link_values"] and link["orphans"] == e["link_values"] - e["link_found"]
    assert len(ws.connections) == 1
    q = next(x for x in ws.connections[0].queries if "SAP_Customer_No__c" in x and "orphans" in x)
    assert "[crm].[Account]" in q and "[sap].[KNA1]" in q                      # one query, two schemas


def test_layout_c_start_offers_both_schemas_as_one_plan_and_checks_it(monkeypatch):
    mlh.install(monkeypatch, "c")
    a = json.loads(server.start(workspace=W, source="sales_product_lh"))
    both = next(x for x in a["actions"] if x["kind"] == "choose" and "+" in x["label"])
    assert both["hint"] == "38 tables, one plan" and not both.get("selected")
    c = json.loads(server.start(**both["arguments"]))
    assert c["stage"] == "check" and "error" not in json.dumps(c.get("review_error") or "")
    assert c["chosen"]["schema"] == "crm+sap"


# ------------------------------------------------------------------------------------------------ the rules, pure
def test_the_name_rules():
    def pick(names):
        hit = sf.suggest_source([{"name": n} for n in names])
        return hit and (hit["name"], hit["rule"])
    assert pick(["bronze_lh", "silver_lh", "gold_lh"]) == ("bronze_lh", "L1")
    assert pick(["Raw-Sales", "Curated-Sales"]) == ("Raw-Sales", "L1")
    assert pick(["landing", "reports"]) == ("landing", "L1")
    assert pick(["sap_lh", "crm_lh", "sales_product_lh"]) == ("sales_product_lh", "L2")
    assert pick(["bronze_a", "bronze_b", "silver"]) is None                     # two raw layers: not guessed
    assert pick(["sap_lh", "crm_lh"]) is None and pick(["a", "b"]) is None and pick(["bronze_lh"]) is None
    assert pick(["brownbronze", "x"]) is None                                   # a word, not a substring
    assert sf.only_choice("source", {"step": "source", "items": [{"name": "bronze_lh"}, {"name": "gold_lh"}]}) == "bronze_lh"
    assert sf.only_choice("schema", {"step": "schema", "items": [{"name": "sap", "tables": 17}, {"name": "crm", "tables": 21},
                                                                {"name": "sap+crm", "tables": 38}]}) is None


def test_several_schemas_in_one_name():
    assert multi_schema.parts("sap+crm") == ["sap", "crm"] == multi_schema.parts(" sap, crm ,sap")
    assert multi_schema.parts("dbo") == ["dbo"] and not multi_schema.is_multi("dbo")
    assert TSQL.table("sap+crm", "sap.KNA1") == "[sap].[KNA1]"
    assert TSQL.table("dbo", "a.b") == "[dbo].[a.b]"                           # one schema: a dot stays in the name
