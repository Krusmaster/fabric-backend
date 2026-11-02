"""n87, point 1: a question with a negation ("no", "without", "missing", "saknar", "utan") on a relationship is answered
with an anti-join (NOT EXISTS), never with the INNER JOIN that answers the opposite; GraphQL says it has no form for it,
and query_graphql runs nothing; a question the engine does not fully understand says what it did not understand.
Checked on the synthetic shop seed in SQLite, in English and Swedish."""
import json
import sqlite3

import pytest
import requests

from fabric_backend import answers, seed, server
from tests.test_answer_query import Resp, description, run_tsql, shop, shop_plan, sqlite_with_seed  # noqa: F401  (shop: fixture)


def _gaps():
    """A copy of the seed where some customers have no orders and some no address, so the anti-join has rows to find."""
    con = sqlite_with_seed()
    con.execute("DELETE FROM shop.orders WHERE customer_id IN (3, 7)")
    con.execute("DELETE FROM shop.addresses WHERE customer_id IN (2, 5)")
    return con


def _ids(con, sql):
    return {r[0] for r in run_tsql(con, sql)}


def test_orders_but_no_address_is_an_anti_join():
    con = _gaps()
    out = answers.draft(shop_plan(), "Which customers have orders but no address?", ["customers", "orders", "addresses"])
    assert "NOT EXISTS" in out["tsql"] and "JOIN [shop].[addresses]" not in out["tsql"].split("NOT EXISTS")[0]
    with_orders = {r[0] for r in con.execute("SELECT DISTINCT customer_id FROM shop.orders")}
    with_address = {r[0] for r in con.execute("SELECT DISTINCT customer_id FROM shop.addresses")}
    assert _ids(con, out["tsql"]) == with_orders - with_address == {2, 5}
    assert out["understood"]["without"] == ["addresses"] and out["understood"]["with"] == ["orders"]
    assert out["starts_at"] == "customers"


def test_swedish_count_per_country_without_orders():
    con = _gaps()
    out = answers.draft(shop_plan(), "Hur många kunder per land saknar order?", ["customers", "orders"])
    assert "NOT EXISTS" in out["tsql"] and "GROUP BY t0.[country]" in out["tsql"]
    got = {r[0]: r[1] for r in run_tsql(con, out["tsql"])}
    want = {}
    for cid, _, country in seed.CUSTOMERS:
        if cid in (3, 7):
            want[country] = want.get(country, 0) + 1
    assert got == want == {"SE": 1, "FI": 1}
    assert out["understood"]["without"] == ["orders"]


@pytest.mark.parametrize("question,tables,negated", [
    ("Customers without orders", ["customers", "orders"], "orders"),
    ("Customers with no orders", ["customers", "orders"], "orders"),
    ("Which customers have never placed an order?", ["customers", "orders"], "orders"),
    ("Kunder utan order", ["customers", "orders"], "orders"),
    ("Vilka kunder saknar adress?", ["customers", "addresses"], "addresses"),
    ("Vilka kunder har inte lagt någon order?", ["customers", "orders"], "orders"),
    ("Orders missing an address", ["orders", "addresses"], "addresses"),
])
def test_each_marker_gives_an_anti_join(question, tables, negated):
    con = _gaps()
    out = answers.draft(shop_plan(), question, tables)
    assert out["understood"]["without"] == [negated] and "NOT EXISTS" in out["tsql"], out
    run_tsql(con, out["tsql"])                                              # runs


def test_orders_missing_the_ship_to_address_follow_the_direct_relationship():
    con = _gaps()
    out = answers.draft(shop_plan(), "Orders missing an address", ["orders", "addresses"])
    # with the seed's own plan (no ship_to_id link) the anti-join goes through customers: orders of customers 2 and 5
    assert _ids(con, out["tsql"]) == {r[0] for r in con.execute("SELECT order_id FROM shop.orders WHERE customer_id IN (2, 5)")}


def test_graphql_has_no_form_for_a_negation():
    p = shop_plan()
    out = answers.draft(p, "Which customers have orders but no address?", ["customers", "orders", "addresses"], description(p), "shop_api")
    assert "query" not in out["graphql"]
    assert "NOT EXISTS" in out["graphql"]["not_possible"] or "anti-join" in out["graphql"]["not_possible"]


def test_a_negation_that_cannot_be_tied_gives_no_query_and_says_why():
    out = answers.draft(shop_plan(), "Which customers have no loyalty card?", ["customers"])
    assert out["tsql"] is None and out["not_understood"]
    assert any("loyalty" in x for x in out["not_understood"])


def test_query_graphql_does_not_answer_another_question(shop, monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("nothing may run"))
    out = json.loads(server.query_graphql("Sales", "shop_api", question="Which customers have orders but no address?",
                                          tables=["customers", "orders", "addresses"], source="shop_lh", schema="shop"))
    assert out["kind"] == "unsupported" and "NOT EXISTS" in out["tsql"]
    assert "SQL analytics endpoint" in out["hint"] and "query editor" in out["hint"]
    out = json.loads(server.query_graphql("Sales", "shop_api", question="Hur många kunder per land saknar order?",
                                          tables=["customers", "orders"], source="shop_lh", schema="shop"))
    assert out["kind"] == "unsupported" and "NOT EXISTS" in out["tsql"]
    # a filter the engine does not read is said, and nothing runs
    out = json.loads(server.query_graphql("Sales", "shop_api", question="Antal ordrar per kund efter 2024",
                                          tables=["orders", "customers"], source="shop_lh", schema="shop"))
    assert out["kind"] == "not_understood" and "2024" in out["error"]


def test_without_a_negation_nothing_changes():
    out = answers.draft(shop_plan(), "How many orders per customer?", ["orders", "customers"])
    assert "EXISTS" not in out["tsql"] and "not_understood" not in out
