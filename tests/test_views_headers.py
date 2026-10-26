"""views.header_tables: the header of each fact table, in every benchmark schema, names only and with declared keys."""
import pytest

from fabric_backend import seed, views
from fabric_backend.infer import plan
from test_inference_quality import load, names_only
from test_tmdl_summarize import declared

EXPECTED = {
    "northwind": [("Orders", "Order Details")],
    "chinook": [("Invoice", "InvoiceLine")],
    "tpch": [("ORDERS", "LINEITEM")],
    "adventureworks": [("PurchaseOrderHeader", "PurchaseOrderDetail"), ("SalesOrderHeader", "SalesOrderDetail")],
    "sakila": [],
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
@pytest.mark.parametrize("mode", ["names only", "declared"])
def test_the_header_of_each_fact_table_is_found(name, mode):
    p = plan(names_only(load(name)) if mode == "names only" else declared(load(name)))
    assert views.header_tables(p) == EXPECTED[name]
    st = views.statements(p)
    got = [v["name"] for v in st["views"]]
    for header, lines in EXPECTED[name]:
        v = next(x for x in st["views"] if x["name"] == f"vw_{header}")
        assert v["tables"][0] == header and len(v["tables"]) >= 2 and f"{lines} holds its lines" in v["why"]
        assert got.index(f"vw_{lines}") < got.index(f"vw_{header}")               # the fact view first, then its header


def test_a_dimension_with_a_snowflake_is_not_a_header():
    # order_items -> products -> categories: products is pointed at by the fact and points on, but it is not the header
    p = plan(seed.schema("shop"))
    assert views.header_tables(p) == [("orders", "order_items")]
    assert all(v["name"] != "vw_products" for v in views.statements(p)["views"])
