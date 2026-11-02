"""n87, point 4: "per X" groups by X, in English and Swedish, also where X is named by the knowledge pack rather than by
the table's name (sap_kna1 is SAP's customer master). The live run of 2 November gave one total without GROUP BY for
"total order value per customer" over sap_vbak, sap_vbap and sap_kna1. A "per" the engine cannot tie to a table or a
column is said, and no single total is offered in its place. Checked on the synthetic SAP demo in SQLite."""
import pytest

from fabric_backend import answers, sap_demo
from fabric_backend.infer import plan
from tests.test_answer_query import run_tsql, shop_plan

SAP = ["sap_vbak", "sap_vbap", "sap_kna1"]


@pytest.fixture(scope="module")
def sap():
    schema, execute = sap_demo.sqlite()
    return plan(schema), execute


@pytest.mark.parametrize("question", ["total order value per customer", "What is the total order value per customer?",
                                      "Totalt ordervärde per kund", "Summa ordervärde för varje kund"])
def test_per_customer_groups_by_the_customer(sap, question):
    p, execute = sap
    out = answers.draft(p, question, SAP)
    assert out["understood"]["group_table"] == "sap_kna1", out["understood"]
    assert "GROUP BY" in out["tsql"] and "KUNNR" in out["tsql"].split("GROUP BY")[1]
    rows = execute(out["tsql"].replace("SELECT TOP", "SELECT").replace("COUNT_BIG(", "COUNT("))
    assert len(rows) > 1                                                     # one row per customer, not one total


def test_a_per_that_names_nothing_is_said_and_gives_no_single_total():
    out = answers.draft(shop_plan(), "Total quantity per warehouse", ["order_items", "products"])
    assert out["tsql"] is None and any("per warehouse" in x for x in out["not_understood"])


def test_the_shop_still_groups_as_before():
    out = answers.draft(shop_plan(), "Total quantity per category", ["order_items", "categories"])
    assert "GROUP BY" in out["tsql"] and "not_understood" not in out
