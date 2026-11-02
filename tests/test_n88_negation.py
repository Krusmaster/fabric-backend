"""n88, point 1: the live test of 2 November 2026 after the n87 deployment. "customers who have not placed any orders" and
"customers who haven't placed an order" gave a plain JOIN on orders with understood {}, and query_graphql ran it and
returned 60 orders, the opposite. The markers now include "have not", "hasn't", "not placed" and their kin, and any
"not", "n't", "never", "inte", "ej" or "aldrig" no marker took gives not_understood and no query, never a plain JOIN.
English and Swedish, in answer_query_draft and query_graphql; questions without a negation are unchanged."""
import json

import pytest
import requests

from fabric_backend import answers, server
from tests.test_answer_query import run_tsql, shop, shop_plan, sqlite_with_seed  # noqa: F401  (shop: fixture)
from tests.test_n87_negation import _gaps, _ids

TABLES = ["customers", "orders"]
NO_ORDERS = {3, 7}                                                   # _gaps() deletes these customers' orders

TIED = ["customers who have not placed any orders", "customers who haven't placed an order", "Customers that hasn't got an order",
        "customers who had not placed an order", "customers who hadn't placed any order", "customers who do not have orders",
        "customers who don't have any orders", "customers who didn't place an order", "customers that have never placed an order",
        "customers with no orders", "Vilka kunder har inte lagt någon order?", "kunder som inte har någon order",
        "kunder som aldrig har lagt en order", "kunder som saknar order", "kunder utan ordrar", "kunder som ej har order"]


@pytest.mark.parametrize("question", TIED)
def test_each_tied_negation_is_an_anti_join(question):
    out = answers.draft(shop_plan(), question, TABLES)
    assert out["understood"].get("without") == ["orders"], out
    assert "NOT EXISTS" in out["tsql"] and "JOIN [shop].[orders]" not in out["tsql"]
    assert _ids(_gaps(), out["tsql"]) == NO_ORDERS


UNTIED = ["customers who have not ordered", "customers who never bought anything", "kunder som inte har beställt",
          "kunder som aldrig handlat", "customers that ej handlat", "customers not in Germany"]


@pytest.mark.parametrize("question", UNTIED)
def test_an_untied_negation_gives_no_query(question):
    out = answers.draft(shop_plan(), question, TABLES)
    assert out["tsql"] is None and out["not_understood"], out


@pytest.mark.parametrize("question", ["customers who have not placed any orders", "customers who haven't placed an order",
                                      "Vilka kunder har inte lagt någon order?", "customers who have not ordered"])
def test_query_graphql_never_runs_the_opposite(shop, monkeypatch, question):
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("nothing may run"))
    out = json.loads(server.query_graphql("Sales", "shop_api", question=question, tables=TABLES, source="shop_lh", schema="shop"))
    assert out["kind"] in ("unsupported", "not_understood"), out
    assert out["tsql"] is None or "NOT EXISTS" in out["tsql"]


@pytest.mark.parametrize("question", ["How many orders per customer?", "Hur många ordrar per kund?", "Customers per country",
                                      "Antal kunder per land", "Which customers have the most orders?", "Show the latest 10 orders",
                                      "Total quantity per category"])
def test_questions_without_a_negation_are_unchanged(question):
    tables = ["order_items", "categories"] if "category" in question else TABLES
    out = answers.draft(shop_plan(), question, tables)
    assert out["tsql"] and "EXISTS" not in out["tsql"] and "not_understood" not in out
    assert run_tsql(sqlite_with_seed(), out["tsql"])
