"""Round LFD4 (25 November 2026): the numbers before and after each change, counted on the rows (change_numbers.py,
the ratio form of verify_build.measure_sql, docs/CHANGES.md).

Every number of scenario A (shop_lfd) and scenario B (sap_lfd) comes out of the statements, each with its SQL; the
denied path (orders -> customers -> addresses) counts 60 rows as 103; only SELECT statements; no row value in the
answer; KRUSGRAPH_NO_ROW_VALUES hides a sum over fewer than three rows; what the time budget does not reach is "not
counted (time)". No network, no model: SQLite over the synthetic samples of fabric_backend/lfd_demo.py."""
from __future__ import annotations

import json
import re
from decimal import Decimal

import pytest

from fabric_backend import change_numbers as cn
from fabric_backend import changes, gold, lfd_demo, semantic_model, server, silver
from fabric_backend import model_compare as mc
from fabric_backend import verify_build as vb
from fabric_backend.dialects import DATABRICKS

INFO = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse",
            schema="shop", schemas_enabled=True)
IS_TEST = {"column": "is_test", "op": "is_true"}
C1 = {"type": "filter_rows", "table": "customers", "drop_where": IS_TEST, "cascade": ["orders", "order_items", "addresses", "audit_log"]}
SHIP_TO = {"from": {"table": "orders", "columns": ["ship_to_id"]}, "to": {"table": "addresses", "columns": ["address_id"]}}
C2 = {"type": "add_column", "table": "orders", "from": "addresses", "columns": ["region"], "via": [SHIP_TO]}
C3 = {"type": "add_measure", "name": "Order value per customer",
      "measure": {"form": "ratio", "numerator": {"measure": "Order amount"},
                  "denominator": {"form": "distinct_count", "table": "orders", "column": "customer_id"}}}
VIA_CUSTOMER = {"type": "add_column", "table": "orders", "from": "addresses", "columns": ["region"], "via": [
    {"from": {"table": "orders", "columns": ["customer_id"]}, "to": {"table": "customers", "columns": ["customer_id"]}},
    {"from": {"table": "addresses", "columns": ["customer_id"]}, "to": {"table": "customers", "columns": ["customer_id"]}}]}
B1 = {"type": "filter_rows", "table": "sap_vbrk", "cascade": ["sap_vbrp"],
      "drop_where": {"any": [{"column": "FKSTO", "op": "equals", "value": "X"}, {"column": "SFAKN", "op": "is_not_empty"}]}}


@pytest.fixture(scope="module")
def shop():
    schema, execute = lfd_demo.sqlite("shop_lfd")
    return server._hosted_plan(schema, None, None, execute), execute


@pytest.fixture(scope="module")
def sap():
    schema, execute = lfd_demo.sqlite("sap_lfd")
    return server._hosted_plan(schema, None, None, execute), execute


@pytest.fixture(scope="module")
def scenario_a(shop):
    p, execute = shop
    applied = changes.apply([C1, C2, C3], p)
    assert applied["result"] == "ok"
    return applied, cn.count(applied, p, execute, dialect="sqlite", no_row_values=False)


def by_item(change: dict, key: str = "numbers") -> dict:
    return {n["item"]: n for n in change[key]}


def run(execute, sql: str) -> dict:
    """A statement as the answer gives it, run again on the same rows."""
    return list(execute(sql))[0]


# ------------------------------------------------------------------ scenario A ---------------------------------------

def test_scenario_a_filter_test_customers(scenario_a, shop):
    _, execute = shop
    applied, got = scenario_a
    assert got["result"] == "counted" and got["statements"]["not_counted"] == 0
    c1 = got["changes"][0]
    assert c1["id"] == applied["changes"][0]["id"] and c1["type"] == "filter_rows"
    n = by_item(c1)
    want = {"customers": (12, 10), "orders": (66, 60), "order_items": (146, 134), "addresses": (19, 17)}
    for t, (b, a) in want.items():
        assert (n[f"rows:{t}"]["before"], n[f"rows:{t}"]["after"]) == (b, a), t
        assert n[f"rows:{t}"]["difference"] == a - b
    amount = n["sum:Order amount"]
    assert (amount["before"], amount["after"], amount["difference"], amount["percent"]) == ("56834.70", "51296.70", "-5538.00", "-9.7")
    assert (amount["rows_before"], amount["rows_after"]) == (146, 134)
    assert "Order amount: 56 834.70 → 51 296.70 (-5 538.00, 9.7 %)." in c1["said"]
    assert (n["distinct:orders.customer_id"]["before"], n["distinct:orders.customer_id"]["after"]) == (12, 10)
    # the numbers are LFD1's, and each comes out of its own statement when run again
    want1 = lfd_demo.EXPECTED["shop_lfd"]["numbers"]
    assert (want1["customers"], want1["real_customers"], want1["order_value"], want1["real_order_value"]) == (12, 10, "56834.70", "51296.70")
    assert run(execute, n["rows:orders"]["after_sql"])["n"] == 60
    assert cn.money(run(execute, amount["after_sql"])["total"]) == "51296.70"


def test_the_filter_counts_on_the_source_what_silver_simulate_leaves(shop):
    p, execute = shop
    applied = changes.apply([C1], p)
    data = {t.name: execute(f"SELECT * FROM [shop].[{t.name}]") for t in p.schema}
    sim = silver.simulate(silver.spec(p, INFO, changes=applied), data)["silver"]
    got = by_item(cn.count(applied, p, execute, dialect="sqlite")["changes"][0])
    for t in ("customers", "addresses", "orders", "order_items", "audit_log"):
        assert got[f"rows:{t}"]["after"] == len(sim[t]), t


def test_scenario_a_region_add_column_repeats_no_row(scenario_a):
    _, got = scenario_a
    c2 = got["changes"][1]
    n = by_item(c2)
    rows = n["view_rows:orders"]
    assert (rows["before"], rows["after"], rows["equal"]) == (60, 60, True)
    assert "LEFT JOIN [shop].[addresses] AS j1 ON j1.[address_id] = t.[ship_to_id]" in rows["after_sql"]
    assert (n["missing:addresses.region"]["after"], n["missing:addresses.region"]["of"]) == (0, 60)
    assert n["distinct_values:addresses.region"]["after"] == 2
    assert c2["doubled"] is False
    checks = by_item(c2, "doubling")
    assert (checks["doubling:Order amount"]["before"], checks["doubling:Order amount"]["after"]) == ("51296.70", "51296.70")
    assert checks["doubling:Order amount"]["equal"] and checks["doubling:rows:orders"]["equal"]
    assert "addresses.region: no value on 0 of 60 rows." in c2["said"]


def test_scenario_a_measure_value_per_customer(scenario_a, shop):
    p, execute = shop
    _, got = scenario_a
    c3 = got["changes"][2]
    m = by_item(c3)["measure:Order value per customer"]
    assert (m["value"], m["on_source"]) == ("5129.67", "4736.23")
    assert len(m["sql"]) == 2 and len(m["on_source_sql"]) == 2                 # the numerator and the denominator
    num, den = (run(execute, s) for s in m["sql"])
    assert (cn.money(num["total"]), den["n"]) == ("51296.70", 10)
    other = by_item(c3)["sum:Order amount"]
    assert other["unchanged"] and other["before"] == other["after"] == "51296.70"
    assert "Order value per customer: 5 129.67 (4 736.23 on the source as it is)." in c3["said"]


def test_the_same_list_gives_the_same_statements(scenario_a, shop):
    p, execute = shop
    applied, got = scenario_a
    again = cn.count(changes.apply([C1, C2, C3], p), p, execute, dialect="sqlite", no_row_values=False, generated_at=got["generated_at"])
    assert again == got
    assert [x["sql"] for x in cn.statements(applied, p, "sqlite")] == [x["statement"] for x in got["receipt"]]
    assert len({x["statement"] for x in got["receipt"]}) == len(got["receipt"])         # each statement once


# ------------------------------------------------------------------ the denied path ----------------------------------

def test_the_denied_path_counts_60_rows_as_103(shop):
    p, execute = shop
    assert changes.validate(VIA_CUSTOMER, p)["kind"] == "fan_out"
    got = cn.count_path(VIA_CUSTOMER, p, execute, applied=changes.apply([C1], p), dialect="sqlite")
    row = got["changes"][0]
    assert row["path"] == ["orders", "customers", "addresses"] and row["doubled"] is True
    rows = by_item(row)["view_rows:orders"]
    assert (rows["before"], rows["after"], rows["equal"]) == (60, 103, False)
    want = lfd_demo.EXPECTED["shop_lfd"]["numbers"]
    assert rows["after"] == want["real_via_customer_rows"]
    value = by_item(row, "doubling")["doubling:Order amount"]
    assert (value["before"], value["after"], value["equal"]) == ("51296.70", want["real_via_customer_value"], False)
    assert any("repeats rows" in s for s in row["said"])
    # the plan's own path counts the same orders once
    ok = cn.count_path(C2, p, execute, applied=changes.apply([C1], p), dialect="sqlite")["changes"][0]
    assert ok["doubled"] is False and by_item(ok)["view_rows:orders"]["after"] == 60


def test_count_path_refuses_names_outside_the_plan(shop):
    p, execute = shop
    bad = {**C2, "via": [{"from": {"table": "orders", "columns": ["ship_to_id"]}, "to": {"table": "nowhere", "columns": ["id"]}}]}
    with pytest.raises(cn.NumbersError):
        cn.count_path(bad, p, execute)
    with pytest.raises(cn.NumbersError):
        cn.count({"result": "denied"}, p, execute)


# ------------------------------------------------------------------ scenario B ---------------------------------------

def test_scenario_b_billing_without_cancelled_and_cancellations(sap):
    p, execute = sap
    applied = changes.apply([B1], p)
    assert applied["result"] == "ok"
    got = cn.count(applied, p, execute, dialect="sqlite", no_row_values=False)
    n = by_item(got["changes"][0])
    assert (n["rows:sap_vbrk"]["before"], n["rows:sap_vbrk"]["after"]) == (3, 1)
    assert (n["rows:sap_vbrp"]["before"], n["rows:sap_vbrp"]["after"]) == (4, 2)
    billed = n["sum:sap_vbrk.NETWR"]
    assert (billed["before"], billed["after"], billed["difference"]) == ("600.00", "400.00", "-200.00")
    want = lfd_demo.EXPECTED["sap_lfd"]["numbers"]
    assert (billed["before"], billed["after"]) == (want["billed"], want["billed_without_cancellations"])
    orders, value = n["rows:sap_vbak"], n["sum:sap_vbak.NETWR"]
    assert orders["untouched"] and (orders["before"], orders["after"]) == (4, 4)
    assert value["untouched"] and value["before"] == value["after"] == want["order_value_per_header"] == "950.00"
    assert orders["before_sql"] == orders["after_sql"]                         # untouched: one statement, counted once
    assert "sap_vbak: 4 → 4 rows (untouched)." in got["changes"][0]["said"]


# ------------------------------------------------------------------ the rules of every answer -----------------------

def test_only_select_statements_in_tsql_sqlite_and_databricks(scenario_a, shop, sap):
    p, _ = shop
    applied, got = scenario_a
    texts = [x["statement"] for x in got["receipt"]]
    texts += [x["sql"] for x in cn.statements(applied, p)]                    # T-SQL, as Fabric runs it
    texts += [x["sql"] for x in cn.statements(applied, p, DATABRICKS)]
    texts += [x["sql"] for x in cn.statements(changes.apply([B1], sap[0]), sap[0])]
    assert texts
    for sql in texts:
        assert sql.startswith("SELECT ") and ";" not in sql
        assert not re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|CREATE|ALTER|EXEC|TRUNCATE|INTO)\b", sql, re.I), sql
    tsql = [x["sql"] for x in cn.statements(applied, p)]
    assert any("COUNT_BIG(*)" in s for s in tsql) and all("COUNT_BIG" not in s for s in [x["statement"] for x in got["receipt"]])
    assert all("`shop`.`" in x["sql"] for x in cn.statements(applied, p, DATABRICKS))


def _row_values(execute) -> set[str]:
    out = set()
    for t in ("customers", "addresses"):
        for r in execute(f"SELECT * FROM [shop].[{t}]"):
            out.update(v for v in r.values() if isinstance(v, str) and len(v) >= 4)
    return out


def test_no_row_value_in_the_answer(scenario_a, shop):
    _, execute = shop
    _, got = scenario_a
    text = json.dumps(got) + json.dumps(cn.count_path(VIA_CUSTOMER, *shop, dialect="sqlite")) + cn.markdown(got)
    values = _row_values(execute)
    assert {"North", "South"} <= values and any(v.startswith("Test Customer") for v in values)
    assert not [v for v in values if v in text]


def test_no_row_values_hides_a_sum_over_fewer_than_three_rows(sap, monkeypatch):
    p, execute = sap
    applied = changes.apply([B1], p)
    monkeypatch.setenv("KRUSGRAPH_NO_ROW_VALUES", "1")
    got = cn.count(applied, p, execute, dialect="sqlite")
    n = by_item(got["changes"][0])
    billed = n["sum:sap_vbrk.NETWR"]
    assert billed["after"] is None and billed["rows_after"] == 1 and billed["hidden"] == cn.HIDDEN
    assert billed["before"] == "600.00" and "difference" not in billed                  # three rows: shown
    assert n["rows:sap_vbrk"]["after"] == 1                                             # the count is shown
    assert "400.00" not in json.dumps(got)
    assert all(r["counts"]["total"] is None for r in got["receipt"] if r["counts"] and "total" in r["counts"] and r["counts"]["n"] < 3)
    monkeypatch.delenv("KRUSGRAPH_NO_ROW_VALUES")
    assert by_item(cn.count(applied, p, execute, dialect="sqlite")["changes"][0])["sum:sap_vbrk.NETWR"]["after"] == "400.00"


def test_the_budget_leaves_numbers_not_counted_never_guessed(shop):
    p, execute = shop
    applied = changes.apply([C1, C2, C3], p)
    none = cn.count(applied, p, execute, dialect="sqlite", seconds=0)
    assert none["result"] == "not counted" and none["statements"]["counted"] == 0
    for c in none["changes"]:
        for n in c["numbers"]:
            assert n["state"] == cn.NOT_COUNTED == "not counted (time)"
            assert all(n.get(k) is None for k in ("before", "after", "value"))
    assert all(r["sql"] is None and r["counts"] is None for r in none["receipt"])

    now = [0.0]

    def slow(sql):                                  # every statement takes one second on the test's clock
        now[0] += 1
        return execute(sql)
    part = cn.count(applied, p, slow, dialect="sqlite", seconds=3.5, clock=lambda: now[0])
    assert part["result"] == "partly counted"
    assert part["statements"]["counted"] == 4 and part["statements"]["not_counted_time"] == len(part["receipt"]) - 4
    late = [n for c in part["changes"] for n in c["numbers"] if n["state"] == cn.NOT_COUNTED]
    assert late and all(n.get("after") is None and n.get("value") is None for n in late)
    assert part["budget"]["seconds"] == 3.5


def test_a_failed_statement_is_not_counted_with_its_reason(shop):
    p, execute = shop

    def broken(sql):
        if "order_items" in sql:
            raise RuntimeError("Invalid object name 'shop.order_items'.")
        return execute(sql)
    got = cn.count(changes.apply([C1], p), p, broken, dialect="sqlite")
    n = by_item(got["changes"][0])
    assert n["rows:order_items"]["state"].startswith("not counted: ") and n["rows:order_items"]["after"] is None
    assert n["rows:customers"]["after"] == 10 and got["result"] == "partly counted"


def test_an_add_link_and_an_empty_list_count_nothing(shop):
    p, execute = shop
    empty = cn.count(changes.apply([], p), p, execute, dialect="sqlite")
    assert empty["changes"] == [] and empty["receipt"] == []
    link = cn.count(changes.apply([{"type": "add_link", **SHIP_TO}], p), p, execute, dialect="sqlite")
    assert link["changes"][0]["type"] == "add_link" and link["changes"][0]["numbers"] == [] and link["receipt"] == []


# ------------------------------------------------------------------ verify_build counts a ratio ----------------------

def test_verify_build_measure_sql_counts_the_ratio_form(shop):
    p, execute = shop
    applied = changes.apply([C3], p)
    model = mc.from_tmdl(semantic_model.draft(p, INFO, "shop_model", changes=applied)["parts"])
    expr = next(m["expression"] for t in model["tables"].values() for n, m in t["measures"].items() if n == "Order value per customer")
    assert vb._norm_expr(expr) == "DIVIDE([Order amount], DISTINCTCOUNT('orders'[customer_id]))"
    q = vb.measure_sql(model, expr, "shop")
    assert q["ratio"] and q["sql"].startswith("SELECT CASE WHEN d.v IS NULL OR d.v = 0 THEN NULL ELSE 1.0 * n.v / d.v END AS v FROM (")
    v = run(execute, q["sql"])["v"]
    assert abs(Decimal(repr(v)) - Decimal("4736.225")) < Decimal("1e-6")                # 56 834.70 / 12, on the source as it is
    assert vb.measure_sql(model, "DIVIDE(COUNTROWS('orders'), DISTINCTCOUNT('orders'[customer_id]))", "shop")["sql"]
    assert "not translated" in vb.measure_sql(model, "DIVIDE(1, 2)", "shop")["why"]
    assert "ratio of a ratio" in vb.measure_sql(model, "DIVIDE(DIVIDE(COUNTROWS('orders'), 2), 3)", "shop")["why"]
    assert "not a measure" in vb.measure_sql(model, "DIVIDE([Nothing], COUNTROWS('orders'))", "shop")["why"]
    zero = vb.measure_sql(model, "DIVIDE(COUNTROWS('orders'), COUNTROWS('orders'))", "shop")["sql"].replace(
        "FROM [shop].[orders])", "FROM [shop].[orders] WHERE 1 = 0)")
    assert run(execute, zero)["v"] is None                                             # DIVIDE: BLANK on 0


def test_the_gold_view_of_the_change_has_the_rows_the_numbers_say(shop):
    """add_column's after-statement counts what gold.apply_changes' view gives: 60 orders with addresses_region."""
    p, execute = shop
    applied = changes.apply([C1, C2], p)
    g = gold.spec(p, INFO, changes=applied)
    assert "addresses_region" in repr(g)
    got = by_item(cn.count(applied, p, execute, dialect="sqlite")["changes"][1])
    assert got["view_rows:orders"]["after"] == lfd_demo.EXPECTED["shop_lfd"]["numbers"]["real_orders"] == 60
