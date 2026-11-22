"""DPM1 (Gustav, 21 November 2026, on the shop sample's data flow: "ska vi inte använda dataprodukterna för den
semantiska modellen?"). When a build has gold views, the semantic model reads them (a star schema: the fact views and the
dimension views), grouped by the data products domains.data_products draws (ED2's one grouping): one perspective and one
display folder per data product, the interface between two data products a relationship, a table in no data product out
of the model. Only onto keys the row check counted unique; never from one fact to another. The silver boxes say what the
row check counted. Checked on the shop sample, the SAP demo and the SAP full demo; nothing calls Fabric."""
from __future__ import annotations

import json
import re
from dataclasses import replace

import pytest

from fabric_backend import data_flow, demo, domains, evidence, gold, sap_demo, semantic_model as sm
from fabric_backend.infer import plan

INFO = demo.FLOW_INFO
SAP_INFO = {"item_name": "sap_lh", "item_kind": "Lakehouse", "schema": "sap", "schemas_enabled": True}


def _rels(parts: dict) -> list[tuple[str, str]]:
    return re.findall(r"fromColumn: (\S+)\n\ttoColumn: (\S+)", parts.get("definition/relationships.tmdl", ""))


@pytest.fixture(scope="module")
def shop():
    p = demo.plan(demo.schema("shop"), keys=demo.DEMO_KEYS)
    g = gold.spec(p, INFO, "silver", "gold", dimensions=True)
    return p, g, sm.draft_on_gold(p, INFO, g, "shop_model", validation=demo.demo_validation())


@pytest.fixture(scope="module", params=[False, True], ids=["sap_demo", "sap_full_demo"])
def sap(request):
    schema, execute = sap_demo.sqlite(full=request.param)
    p = plan(schema)
    v = evidence.validate(p, execute, max_items=200)
    g = gold.spec(p, SAP_INFO, "silver", "gold", dimensions=True)
    return p, g, sm.draft_on_gold(p, SAP_INFO, g, "sap_model", validation=v)


# ------------------------------------------------------------------ the shop sample ------------------------------------

def test_the_shop_model_reads_the_gold_views_not_bronze(shop):
    p, g, d = shop
    s = d["summary"]
    assert s["reads"]["layer"] == "gold" and s["reads"]["said"].startswith("Built on gold: reads the gold views in schema gold")
    for path, text in d["parts"].items():
        if path.startswith("definition/tables/") and "partition" in text and "directLake" in text:
            assert "\t\t\tschemaName: gold" in text, path
            assert "[shop]" not in text
    assert {v["name"] for v in gold.all_views(g)} >= {"gold.orders", "gold.order_items", "gold.customers", "gold.products"}


def test_the_shop_model_is_grouped_by_the_same_data_products_the_picture_draws(shop):
    p, _, d = shop
    picture = demo.demo_drafts()["as_is"]["domains"]
    s = d["summary"]
    assert [g["name"] for g in s["data_products"]] == [x["name"] for x in picture["domains"]] == ["customers", "products"]
    assert {g["name"]: g["tables"] for g in s["data_products"]} == {
        "customers": ["addresses", "customers", "order_items", "orders"], "products": ["categories", "products"]}
    for g in s["data_products"]:
        persp = d["parts"][f"definition/perspectives/{g['name']}.tmdl"]
        assert persp.splitlines()[1] == f"perspective {g['name']}"
        for t in g["tables"]:
            assert f"\tperspectiveTable {t}\n" in persp
            assert f"annotation Krusgraph_DataProduct = {g['name']}" in d["parts"][f"definition/tables/{t}.tmdl"]
        assert f"ref perspective {g['name']}" in d["parts"]["definition/model.tmdl"]
    # the measures sit with their data product: each one's display folder is its table's data product
    for path, text in d["parts"].items():
        if path.startswith("definition/tables/") and "measure " in text:
            table = path.rsplit("/", 1)[1][:-5]
            product = next(g["name"] for g in s["data_products"] if table in g["tables"])
            for block in text.split("\tmeasure ")[1:]:
                assert f"\t\tdisplayFolder: {product}\n" in block
    assert sum(len(g["measures"]) for g in s["data_products"]) == len(s["measures"])


def test_the_interface_between_the_shop_s_data_products_is_a_relationship(shop):
    _, _, d = shop
    picture = demo.demo_drafts()["as_is"]["domains"]["interfaces"]
    assert [(i["source"], i["source_cols"], i["target"]) for i in picture] == [("order_items", ["product_id"], "products")]
    assert [(i["source"], i["column"], i["target"], i["from_product"], i["to_product"]) for i in d["summary"]["interfaces"]] == [
        ("order_items", "product_id", "products", "customers", "products")]
    rel = d["parts"]["definition/relationships.tmdl"]
    block = rel[rel.index("fromColumn: order_items.product_id"):].split("relationship ")[0]
    assert "annotation Krusgraph_Interface = customers -> products" in block


def test_audit_log_stays_out_of_the_shop_model_with_one_line_why(shop):
    _, _, d = shop
    s = d["summary"]
    assert "audit_log" not in s["roles"] and "definition/tables/audit_log.tmdl" not in d["parts"]
    assert [x["table"] for x in s["left_out"]] == ["audit_log"]
    assert "no data product" in s["left_out"][0]["why"] and "\n" not in s["left_out"][0]["why"]


def test_the_shop_star_has_no_fact_to_fact_relationship_and_only_checked_keys(shop):
    _, _, d = shop
    roles = d["summary"]["roles"]
    rels = _rels(d["parts"])
    assert set(rels) >= {("order_items.product_id", "products.product_id"), ("order_items.orders_customer_id", "customers.customer_id"),
                         ("orders.customer_id", "customers.customer_id"), ("products.category_id", "categories.id"),
                         ("addresses.customer_id", "customers.customer_id")}
    for a, b in rels:
        ta, tb = a.split(".")[0], b.split(".")[0]
        assert not (roles.get(ta) == "fact" and roles.get(tb) == "fact"), (a, b)
    assert [(x["source"], x["target"]) for x in d["summary"]["fact_to_fact_left_out"]] == [("order_items", "orders")]
    checked = {k["table"] for k in demo.demo_validation()["keys"] if k["verdict"].startswith("unique")}
    assert all(b.split(".")[0] in checked | {"Calendar"} for _, b in rels)
    assert d["summary"]["keys_checked"] is True and d["summary"]["not_related"] == []


def test_a_key_the_rows_did_not_count_unique_gets_no_relationship():
    p = demo.plan(demo.schema("shop"), keys=demo.DEMO_KEYS)
    g = gold.spec(p, INFO, "silver", "gold", dimensions=True)
    v = json.loads(json.dumps(demo.demo_validation()))
    for k in v["keys"]:
        if k["table"] == "products":
            k["verdict"] = "not unique: 2 duplicate value(s)"
    d = sm.draft_on_gold(p, INFO, g, "shop_model", validation=v)
    assert not any(b.startswith("products.") for _, b in _rels(d["parts"]))
    assert {(x["source"], x["target"]) for x in d["summary"]["not_related"]} == {("order_items", "products")}
    assert d["summary"]["interfaces"] == []


def test_the_advanced_analytics_folder_is_ready(shop):
    _, _, d = shop
    assert sm.ADVANCED_ANALYTICS == "Advanced analytics"
    assert "annotation Krusgraph_AdvancedAnalyticsFolder = Advanced analytics" in d["parts"]["definition/model.tmdl"]
    assert d["summary"]["advanced_analytics"]["display_folder"] == "Advanced analytics"
    assert d["summary"]["advanced_analytics"]["tables"] == []


def test_every_document_of_the_gold_model_holds_an_object(shop):
    _, _, d = shop
    for path, text in d["parts"].items():
        if path.endswith(".tmdl"):
            assert sm.has_object(text), path
    assert any(p["path"].startswith("definition/perspectives/") for p in sm.envelope(d["parts"], "shop_model")["definition"]["parts"])


def test_the_gold_dimension_views_read_silver_and_keep_personal_data_out(shop):
    _, g, _ = shop
    dims = {v["fact"]: v for v in g["dimension_views"]}
    assert set(dims) == {"addresses", "categories", "customers", "products"}
    cols = [c["as"] for c in dims["customers"]["columns"]]
    assert "customer_id" in cols and not any(c in cols for c in ("email", "name", "first_name", "last_name"))
    sql = gold.create_sql(dims["customers"], g)
    assert "CREATE OR REPLACE MATERIALIZED LAKE VIEW `gold`.`customers`" in sql and "FROM `silver`.`customers` AS f" in sql
    notebook = gold.notebook_source(g)
    assert "dimension view(s)" in notebook and '"customers"' in notebook
    assert "gold.customers" in gold.written(g)


def test_without_dimensions_the_gold_spec_is_as_before():
    p = demo.plan(demo.schema("shop"), keys=demo.DEMO_KEYS)
    before = gold.spec(p, INFO, "silver", "gold")
    assert "dimension_views" not in before
    assert gold.all_views(before) == before["views"]


def test_the_bronze_model_stays_when_no_gold_is_built_and_is_labelled():
    from fabric_backend import workload_api as W
    p = demo.plan(demo.schema("shop"), keys=demo.DEMO_KEYS)
    d = sm.draft(p, INFO, "shop_model")
    assert "reads" not in d["summary"] and not any(k.startswith("definition/perspectives/") for k in d["parts"])
    req = {"source_name": "demo_lh", "schema": "shop"}
    assert W.model_reads({"summary": d["summary"]}, req).endswith("(bronze, Direct Lake): no gold views in this build.")
    shop_gold = sm.draft_on_gold(p, INFO, gold.spec(p, INFO, "silver", "gold", dimensions=True), "m", demo.demo_validation())
    assert W.model_reads({"summary": shop_gold["summary"]}, req).startswith("Reads: Built on gold: reads the gold views")
    assert W.model_on_gold({"semantic_model": "m"}, {}) is None
    assert W.model_on_gold({"semantic_model": "m", "gold_views": "g"}, {}) == {"silver_schema": "silver", "gold_schema": "gold"}
    assert W.model_on_gold({"gold_views": "g"}, {}) is None


# ------------------------------------------------------------------ the data flow card -----------------------------------

def test_the_demo_flow_draws_built_on_gold_with_lines_from_gold(shop):
    f = demo.demo_drafts()["as_is"]["flow"]
    assert [c["title"] for c in f["columns"]][-1] == "Built on gold"
    model = next(n for n in f["nodes"] if n["id"] == "item:semantic_model")
    assert model["lines"] == [shop[2]["summary"]["reads"]["said"]]
    into = sorted(e["from"] for e in f["edges"] if e["to"] == "item:semantic_model")
    assert into == sorted(f"gold:gold.{t}" for t in ("order_items", "orders", "addresses", "categories", "customers", "products"))
    assert not any(e["from"] == "bronze" for e in f["edges"])
    assert not any("later option" in n for n in f["notes"])
    assert [g["name"] for g in f["model"]["data_products"]] == [x["name"] for x in demo.demo_drafts()["as_is"]["domains"]["domains"]]
    assert [x["table"] for x in f["model"]["left_out"]] == ["audit_log"]


def test_the_silver_boxes_say_what_the_row_check_counted():
    f = demo.demo_drafts()["as_is"]["flow"]
    lines = {n["table"] if "table" in n else n["label"].split(".", 1)[1]: n["lines"][0] for n in f["nodes"] if n["column"] == "silver"}
    assert lines["customers"] == "key checked: 10 of 10 unique"
    assert lines["orders"] == "key checked: 60 of 60 unique"
    assert lines["order_items"] == "key checked: 134 of 134 unique"
    assert lines["audit_log"] == "no key: rows kept as they are"
    assert not any("not checked" in x for x in lines.values())


def test_not_checked_is_said_only_when_the_row_check_did_not_run():
    p = demo.plan(demo.schema("shop"), keys=demo.DEMO_KEYS)
    f = data_flow.flow(p, INFO, {"silver_notebook": "s"})
    lines = {n["label"]: n["lines"][0] for n in f["nodes"] if n["column"] == "silver"}
    assert lines["silver.customers"] == "every row kept: key customer_id not checked"
    checked = replace(p, checked_keys=demo.demo_checked_keys(p))
    f = data_flow.flow(checked, INFO, {"silver_notebook": "s"})
    lines = {n["label"]: n["lines"][0] for n in f["nodes"] if n["column"] == "silver"}
    assert lines["silver.customers"] == "key checked: 10 of 10 unique"


def test_the_editor_s_row_check_carries_its_counts_into_silver():
    from fabric_backend import workload_api as W
    rv = {"items": [{"type": "key", "table": "customers", "columns": ["customer_id"],
                     "check": {"status": "passed", "checked_at": "2026-11-22T07:00:00Z", "result": {"rows": 10, "nulls": 0, "distinct": 10}}}]}
    ck = W.checked_keys(rv)
    assert ck["customers"]["rows"] == 10 and ck["customers"]["distinct"] == 10
    p = replace(demo.plan(demo.schema("shop"), keys=demo.DEMO_KEYS), checked_keys=ck)
    f = data_flow.flow(p, INFO, {"silver_notebook": "s"})
    assert next(n for n in f["nodes"] if n["label"] == "silver.customers")["lines"][0] == "key checked: 10 of 10 unique"


# ------------------------------------------------------------------ the SAP demo and the SAP full demo -------------------

def test_the_sap_models_read_gold_grouped_by_data_product(sap):
    p, g, d = sap
    s = d["summary"]
    assert s["reads"]["layer"] == "gold"
    assert [x["name"] for x in s["data_products"]] == [x["name"] for x in domains.data_products(p)["domains"]]
    assert s["relationships_active"] > 5 and s["relationships_not_expressible"] == 0
    assert g["dimension_views"]                                  # composite keys relate on silver's combined key column
    assert any(b.endswith("MANDT_KUNNR_key") for _, b in _rels(d["parts"]))


def test_the_sap_models_have_interfaces_and_no_fact_to_fact_relationship(sap):
    _, _, d = sap
    s = d["summary"]
    assert s["interfaces"]
    rel = d["parts"]["definition/relationships.tmdl"]
    assert rel.count("annotation Krusgraph_Interface = ") == len(s["interfaces"])
    roles = s["roles"]
    for a, b in _rels(d["parts"]):
        assert not (roles.get(a.split(".")[0]) == "fact" and roles.get(b.split(".")[0]) == "fact"), (a, b)


def test_the_sap_header_totals_stay_protected(sap):
    _, g, d = sap
    left = {(x["view"], x["table"], x["column"]) for x in d["summary"]["header_amounts_left_out"]}
    assert ("gold.sap_vbap", "sap_vbak", "NETWR") in left
    vbap = d["parts"]["definition/tables/sap_vbap.tmdl"]
    assert "sap_vbak_NETWR" not in vbap
    for m in d["summary"]["measures"]:
        assert "sap_vbak_NETWR" not in m["expression"]


# ------------------------------------------------------------------ the golden TMDL ---------------------------------------

def test_the_shop_model_on_gold_is_the_golden_tmdl(shop):
    """The whole definition of the shop's model on gold, byte for byte. Changed on purpose only: regenerate with
    KRUSGRAPH_UPDATE_GOLDEN=1 and say why in the commit."""
    import os
    from pathlib import Path
    path = Path(__file__).parent / "golden" / "dpm1_shop_model_on_gold.json"
    got = {k: v for k, v in sorted(shop[2]["parts"].items())}
    if os.environ.get("KRUSGRAPH_UPDATE_GOLDEN") == "1":
        path.write_text(json.dumps(got, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    assert path.exists(), "no golden file: run with KRUSGRAPH_UPDATE_GOLDEN=1 once"
    assert got == json.loads(path.read_text(encoding="utf-8"))
