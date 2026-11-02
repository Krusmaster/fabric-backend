"""n87, point 5: "What is total order value per customer?" on the shop summed quantity, as if a count of items were a
value. With no value column the answer says so first, and offers quantity × products.list_price, labelled as such,
where the plan reaches a price; without a price it gives no query. Checked on the shop seed in SQLite."""
from collections import defaultdict

from fabric_backend import answers, seed
from tests.test_answer_query import run_tsql, shop, shop_plan, sqlite_with_seed  # noqa: F401  (shop: fixture)

TABLES = ["orders", "order_items", "customers"]


def test_order_value_per_customer_is_quantity_times_list_price_and_says_so_first():
    out = answers.draft(shop_plan(), "What is total order value per customer?", TABLES)
    assert list(out)[:2] == ["question", "value_column"]
    v = out["value_column"]
    assert v["found"] is False and "no value column" in v["said"] and "quantity × products.list_price" in v["offered"]
    assert "list price" in v["said"] and "not the price paid" in v["said"]
    assert "SUM(t0.[quantity])" not in out["tsql"] and "[quantity] * " in out["tsql"] and "[list_price]" in out["tsql"]
    assert out["assumptions"][0].startswith("no value column")
    price = {p[0]: p[3] for p in seed.PRODUCTS}
    customer_of = {o[0]: o[1] for o in seed.rows()["orders"]}
    want = defaultdict(float)
    for order_id, _, product_id, qty in seed.rows()["order_items"]:
        want[customer_of[order_id]] += qty * price[product_id]
    got = {r[0]: r[-1] for r in run_tsql(sqlite_with_seed(), out["tsql"])}
    assert got.keys() == want.keys() and all(abs(got[k] - want[k]) < 1e-6 for k in want)


def test_swedish_order_value_too():
    out = answers.draft(shop_plan(), "Totalt ordervärde per kund", TABLES)
    assert out["value_column"]["found"] is False and "[list_price]" in out["tsql"]


def test_without_a_price_in_reach_no_quantity_sum_is_offered_as_a_value():
    out = answers.draft(shop_plan(), "Total order value per order", ["order_items", "orders"])
    # products is outside the tables given but in the plan: the price is still reached through order_items.product_id
    assert "[list_price]" in out["tsql"]
    from fabric_backend.infer import plan
    from fabric_backend.schema import Schema
    s = Schema.from_information_schema([("x", "orders", "order_id", "int", 1), ("x", "order_items", "order_id", "int", 1),
                                        ("x", "order_items", "line_no", "int", 2), ("x", "order_items", "quantity", "decimal", 3)], schema="x")
    out = answers.draft(plan(s), "Total order value per order", ["order_items", "orders"])
    assert out["tsql"] is None and any("no value column" in x for x in out["not_understood"])


def test_a_named_quantity_is_summed_as_before():
    out = answers.draft(shop_plan(), "Total quantity per category", ["order_items", "categories"])
    assert "value_column" not in out and "SUM(" in out["tsql"] and "[quantity]" in out["tsql"]


def test_graphql_does_not_sum_the_quantity_and_query_graphql_says_where_the_tsql_runs(shop, monkeypatch):
    import json

    import pytest
    import requests

    from fabric_backend import server
    from tests.test_answer_query import description
    p = shop_plan()
    out = answers.draft(p, "What is total order value per customer?", TABLES, description(p), "shop_api")
    assert "query" not in out["graphql"] and "computed" in out["graphql"]["not_possible"]
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("nothing may run"))
    got = json.loads(server.query_graphql("Sales", "shop_api", question="What is total order value per customer?", tables=TABLES,
                                          source="shop_lh", schema="shop"))
    assert got["kind"] == "unsupported" and "[list_price]" in got["tsql"]
    assert "No Krusgraph tool runs T-SQL" in got["hint"] and "SQL query editor" in got["hint"]
