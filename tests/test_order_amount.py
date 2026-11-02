"""The amount that is not there (round n71): a line table with a quantity and no amount of its own, pointing at a table
that carries the price, gets the measure quantity × RELATED(price) summed over the lines; a line that carries an amount
keeps it and gets no product. Shop (products.list_price), the synthetic SAP model (VBAP.NETWR on the row) and the
Salesforce + ERP example (sales_order_lines.line_amount)."""
import sys
from pathlib import Path

import yaml

from fabric_backend import amounts, browser_check as bc, dictionary, domains, graphs, seed, semantic_model
from fabric_backend.infer import plan
from fabric_backend.schema import Column, Schema, Table

sys.path.insert(0, str(Path(__file__).parent))
import sap_support  # noqa: E402

INFO = dict(workspace_id="w", item_id="i", item_name="src", item_kind="Lakehouse", schema="shop",
            sql_endpoint="x.datawarehouse.fabric.microsoft.com", sql_db="src", schemas_enabled=True)
DAX = "SUMX('order_items', 'order_items'[quantity] * RELATED('products'[list_price]))"


def test_the_name_rules_for_quantities_and_prices():
    assert all(amounts.is_quantity(c) for c in ("quantity", "qty", "OrderQty", "MENGE", "KWMENG", "WMENG", "antal"))
    assert not any(amounts.is_quantity(c) for c in ("quantity_unit", "quantity_id", "order_id", "name", "line_no"))
    assert not amounts.is_quantity("quantity", "varchar")                       # a text column is no quantity
    assert all(amounts.is_price(c) for c in ("price", "list_price", "unit_price", "ListPrice", "UnitPrice", "NETPR", "pris", "styckpris"))
    assert not any(amounts.is_price(c) for c in ("price_type", "price_list_id", "PriceLevel", "TotalPrice", "O_TOTALPRICE",
                                                  "L_EXTENDEDPRICE", "net_amount", "quantity"))


def test_shop_gets_the_order_amount_from_quantity_times_the_list_price():
    p = plan(seed.schema("shop"))
    oa = amounts.order_amount_measures(p)
    assert [m["expression"] for m in oa["measures"]] == [DAX] and oa["own_amounts"] == [] and oa["not_created"] == []
    m = oa["measures"][0]
    assert (m["table"], m["column"], m["dimension"], m["price"], m["via"], m["rule"], m["name"]) == \
           ("order_items", "quantity", "products", "list_price", "product_id", "R1", "Order amount")
    assert "products.list_price" in m["price_note"] and "list price, not necessarily the price paid" in m["price_note"]
    # a products table with a list price is still a dimension (the price is an attribute of the product, not a measure)
    assert graphs.analyze(p)["roles"]["products"]["role"] == "dimension"


def test_the_semantic_model_draft_writes_the_measure_and_does_not_sum_the_price():
    out = semantic_model.draft(plan(seed.schema("shop")), INFO, "shop_model")
    names = {m["name"]: m for m in out["summary"]["measures"]}
    assert names["Order amount"]["expression"] == DAX and names["Order amount"]["table"] == "order_items"
    assert "Total list_price" not in names and "Total quantity" in names                      # the quantity's own sum stays
    items = out["parts"]["definition/tables/order_items.tmdl"]
    assert f"\tmeasure 'Order amount' = {DAX}\n\t\tformatString: #,##0.00\n\t\tlineageTag: " in items
    assert "/// Suggested by Krusgraph: order_items has a quantity (quantity) and no amount of its own; the price is on products.list_price" in items
    assert "The price comes from products.list_price" in items and "..\n" not in items
    products = out["parts"]["definition/tables/products.tmdl"]
    assert "\tmeasure " not in products                                                        # a dimension: no sum of prices
    assert "/// A price at the level of products, read by the measure 'Order amount' through RELATED." in products
    assert "\tcolumn list_price\n\t\tdataType: double\n" in products
    block = products.split("\tcolumn list_price\n", 1)[1].split("\tpartition", 1)[0]
    assert "summarizeBy: none" in block
    readme = out["parts"]["README.generated.md"]
    assert "## Order amount (quantity × price)" in readme and f"- `Order amount` = `{DAX}` on `order_items`" in readme
    assert "- `products.list_price`: a price on `products`, read by the measure `Order amount` through RELATED" in readme
    summary = out["summary"]["order_amount"]
    assert [m["expression"] for m in summary["measures"]] == [DAX] and summary["own_amounts"] == [] and summary["not_created"] == []
    assert "products.list_price" in summary["measures"][0]["price_note"]


def test_create_semantic_model_uses_the_same_draft():
    """create_semantic_model builds its envelope from semantic_model.draft: the measure is in the part it sends."""
    out = semantic_model.draft(plan(seed.schema("shop")), INFO, "shop_model")
    body = semantic_model.envelope(out["parts"], "shop_model")
    import base64
    parts = {x["path"]: base64.b64decode(x["payload"]).decode("utf-8") for x in body["definition"]["parts"]}
    assert f"measure 'Order amount' = {DAX}" in parts["definition/tables/order_items.tmdl"]


def test_the_data_dictionary_and_the_odcs_contract_name_the_measure():
    p = plan(seed.schema("shop"))
    md = dictionary.data_dictionary(p, "src", "shop")
    assert "## Order amount (quantity × price)" in md and f"`Order amount` on order_items: `{DAX}`" in md
    assert "The price comes from products.list_price" in md
    contracts = domains.draft(p, "shop", "src")["contracts"]
    with_measure = {name: yaml.safe_load(text) for name, text in contracts.items() if "customProperties" in text}
    assert len(with_measure) == 1                                      # the domain that holds order_items, whichever table names it
    doc = next(iter(with_measure.values()))
    assert "order_items" in [o["name"] for o in doc["schema"]]
    prop = doc["customProperties"][0]
    assert prop["property"] == "measure.order_amount" and prop["value"] == DAX
    assert "products.list_price" in prop["description"] and "list price, not necessarily the price paid" in prop["description"]


def test_the_sap_order_item_keeps_netwr_and_gets_no_product():
    """VBAP has KWMENG (a quantity) and NETWR (the item's net value, which the pack names): the amount is summed as it is."""
    p = plan(sap_support.schema(["VBAK", "VBAP", "MARA", "KNA1", "TVKO", "T001"]))
    assert amounts.is_quantity("KWMENG")
    oa = amounts.order_amount_measures(p)
    assert oa["measures"] == [] and oa["not_created"] == []
    own = {x["line"]: x for x in oa["own_amounts"]}
    assert own["VBAP"]["quantity"] == "KWMENG" and "NETWR" in own["VBAP"]["amounts"]
    out = semantic_model.draft(p, {**INFO, "schema": "sap"}, "sap_model")
    assert not any("SUMX" in m["expression"] for m in out["summary"]["measures"])
    assert out["summary"]["order_amount"]["measures"] == []
    assert "- `VBAP` keeps its own amount: VBAP carries NETWR" in out["parts"]["README.generated.md"]


def test_the_crm_example_has_the_amount_on_the_line_and_gets_no_product():
    src = bc._sqlite_source("folder", "crm", "crm", bc.crm_tables(), "synthetic")
    try:
        p = plan(src.schema)
    finally:
        src.close()
    oa = amounts.order_amount_measures(p)
    assert oa == {"measures": [], "own_amounts": [], "not_created": []}  # no quantity column at all: line_amount is the amount
    out = semantic_model.draft(p, {**INFO, "schema": "crm"}, "crm_model")
    names = {m["name"]: m["expression"] for m in out["summary"]["measures"]}
    assert names["Total line_amount"] == "SUM('sales_order_lines'[line_amount])"
    assert not any("SUMX" in e for e in names.values())
    assert "- None: no table has a quantity column with a price" in out["parts"]["README.generated.md"]


def _schema(tables: dict[str, list[tuple[str, str]]]) -> Schema:
    s = Schema(schema="x")
    for name, cols in tables.items():
        s.tables[name] = Table(name, [Column(c, t) for c, t in cols], schema="x")
    return s


def test_an_amount_on_the_line_is_used_and_no_product_is_computed():
    s = _schema({"products": [("product_id", "int"), ("name", "varchar"), ("list_price", "decimal")],
                 "orders": [("order_id", "int"), ("order_date", "date")],
                 "order_items": [("order_id", "int"), ("line_no", "int"), ("product_id", "int"), ("quantity", "decimal"), ("net_amount", "decimal")]})
    oa = amounts.order_amount_measures(plan(s))
    assert oa["measures"] == [] and [x["line"] for x in oa["own_amounts"]] == ["order_items"]
    assert oa["own_amounts"][0]["amounts"] == ["net_amount"] and "summed as it is" in oa["own_amounts"][0]["why"]
    out = semantic_model.draft(plan(s), {**INFO, "schema": "x"}, "m")
    names = {m["name"]: m["expression"] for m in out["summary"]["measures"]}
    assert names["Total net_amount"] == "SUM('order_items'[net_amount])" and not any("SUMX" in e for e in names.values())


def test_without_an_active_relationship_to_the_price_the_measure_is_not_created_and_the_reason_is_given():
    p = plan(seed.schema("shop"))
    oa = amounts.order_amount_measures(p, relationships=[])          # RELATED follows the active relationship; none given
    assert oa["measures"] == [] and [x["line"] for x in oa["not_created"]] == ["order_items"]
    assert oa["not_created"][0]["prices"] == ["products.list_price"] and "RELATED needs one" in oa["not_created"][0]["why"]


def test_a_line_that_is_not_an_order_names_the_measure_after_itself():
    s = _schema({"stock_items": [("stock_item_id", "int"), ("unit_price", "decimal")],
                 "movements": [("movement_id", "int"), ("stock_item_id", "int"), ("quantity", "int")]})
    oa = amounts.order_amount_measures(plan(s))
    assert [m["name"] for m in oa["measures"]] == ["movements amount"]
    assert oa["measures"][0]["expression"] == "SUMX('movements', 'movements'[quantity] * RELATED('stock_items'[unit_price]))"
