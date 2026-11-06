"""n134: views that SUM a header amount after joining it to its line table (fabric_backend/sql_sums.py).

The view definitions here are written for these tests over the synthetic schema of fabric_backend.seed.AMOUNT_DEMO
(orders.order_amount, order_lines) and the shop schema (products.list_price, order_items). Nothing is read from Fabric."""
import json

import pytest

from fabric_backend import sql_sums
from fabric_backend.infer import plan
from fabric_backend.seed import schema as shop_schema

from test_amounts import demo_execute, demo_schema

DOUBLED = """-- order totals per day, written for the n134 tests
CREATE VIEW demo.v_orders_per_day AS
SELECT o.order_date,
       SUM(o.order_amount) AS order_total,
       SUM(l.line_amount) AS line_total
FROM demo.orders AS o
JOIN demo.order_lines AS l
  ON l.order_id = o.order_id
WHERE o.order_date >= '2026-01-01'
GROUP BY o.order_date;
"""

PRE_AGGREGATED = """CREATE VIEW demo.v_orders_with_lines AS
SELECT o.order_date, SUM(o.order_amount) AS order_total, SUM(l.line_total) AS line_total
FROM demo.orders o
JOIN (SELECT order_id, SUM(line_amount) AS line_total
      FROM demo.order_lines
      GROUP BY order_id) l ON l.order_id = o.order_id
GROUP BY o.order_date"""

LINE_LEVEL = """CREATE VIEW demo.v_lines AS
SELECT o.order_date, SUM(l.line_amount) AS line_total, MAX(o.order_amount) AS order_amount
FROM demo.orders o JOIN demo.order_lines l ON l.order_id = o.order_id
GROUP BY o.order_date, o.order_id"""

HEADER_ONLY = "CREATE VIEW demo.v_orders AS SELECT order_date, SUM(order_amount) AS total FROM demo.orders GROUP BY order_date"

FIRST_LINE = """CREATE VIEW demo.v_first_line AS
SELECT SUM(o.order_amount) AS total FROM demo.orders o
JOIN demo.order_lines l ON l.order_id = o.order_id AND l.line_no = 1"""

COMMA = """create view [demo].[v_comma] as
select sum([orders].[order_amount]) as total
from [demo].[orders], [demo].[order_lines]
where [order_lines].[order_id] = [orders].[order_id]"""

UNION = """CREATE VIEW demo.v_union AS
SELECT order_date, order_amount FROM demo.orders
UNION ALL
SELECT o.order_date, SUM(o.order_amount)
FROM demo.order_lines l
LEFT OUTER JOIN demo.orders o ON o.order_id = l.order_id
GROUP BY o.order_date"""

CTE = """CREATE VIEW demo.v_cte AS
WITH lines AS (SELECT order_id, COUNT(*) AS n FROM demo.order_lines GROUP BY order_id)
SELECT SUM(o.order_amount) AS total FROM demo.orders o JOIN lines ON lines.order_id = o.order_id"""

DYNAMIC = "CREATE VIEW demo.v_dynamic AS SELECT * FROM demo.orders; EXEC sp_executesql N'SELECT SUM(order_amount) FROM demo.order_lines'"

APPLY = """CREATE VIEW demo.v_apply AS SELECT SUM(o.order_amount) AS total FROM demo.orders o
CROSS APPLY (SELECT TOP 1 l.line_no FROM demo.order_lines l WHERE l.order_id = o.order_id) x"""

UNKNOWN_SOURCE = """CREATE VIEW demo.v_other AS SELECT SUM(o.order_amount) AS total FROM demo.orders o
JOIN staging.shipments s ON s.order_id = o.order_id"""

OTHER_COLUMNS = """CREATE VIEW demo.v_wrong_columns AS SELECT SUM(o.order_amount) AS total FROM demo.orders o
JOIN demo.order_lines l ON l.line_no = o.order_id"""

CUT = "CREATE VIEW demo.v_cut AS SELECT SUM(o.order_amount) FROM demo.orders o WHERE o.order_date > 'unterminated"

UNRELATED = "CREATE VIEW demo.v_constants AS SELECT 1 AS one, 'x' AS letter"

VIEWS = {"v_orders_per_day": DOUBLED, "v_orders_with_lines": PRE_AGGREGATED, "v_lines": LINE_LEVEL,
         "v_orders": HEADER_ONLY, "v_first_line": FIRST_LINE, "v_comma": COMMA, "v_union": UNION, "v_cte": CTE,
         "v_dynamic": DYNAMIC, "v_apply": APPLY, "v_other": UNKNOWN_SOURCE, "v_wrong_columns": OTHER_COLUMNS,
         "v_cut": CUT, "v_constants": UNRELATED, "v_encrypted": None}


def rows():
    return [{"VIEW_SCHEMA": "demo", "VIEW_NAME": k, "VIEW_DEFINITION": v} for k, v in VIEWS.items()]


@pytest.fixture(scope="module")
def result():
    return sql_sums.check(plan(demo_schema()), rows())


def by_view(result):
    return {**{e["view"]: e for e in result["flagged"]}, **{e["view"]: e for e in result["could_not_be_read"]}}


def test_the_views_that_sum_the_header_amount_over_its_lines_are_flagged(result):
    flagged = {e["view"]: e for e in result["flagged"]}
    assert set(flagged) == {"demo.v_orders_per_day", "demo.v_comma", "demo.v_union"}
    e = flagged["demo.v_orders_per_day"]
    assert e["amount"] == "orders.order_amount" and e["line_table"] == "order_lines"
    assert e["relationship"] == "order_lines.order_id → orders.order_id"
    assert e["sum"] == "SUM(o.order_amount)" and e["line"] == 4               # line 1 is the comment
    assert e["join"] == "demo.order_lines AS l ON l.order_id = o.order_id" and e["join_line"] == 7
    assert "order amount and line amount are different levels" in e["do_instead"]
    comma = flagged["demo.v_comma"]
    assert comma["line"] == 2 and "comma join; WHERE order_lines.order_id = orders.order_id" in comma["join"]
    union = flagged["demo.v_union"]                                           # the second SELECT of the UNION
    assert union["line"] == 4 and union["join"] == "demo.order_lines l joined by demo.orders o ON o.order_id = l.order_id"
    assert union["join_line"] == 6


def test_a_correct_pre_aggregation_and_other_correct_views_are_not_flagged(result):
    assert set(result["read_not_flagged"]) == {"demo.v_orders_with_lines", "demo.v_lines", "demo.v_orders",
                                               "demo.v_first_line"}
    assert result["views"] == {"read": 15, "naming_a_header_table": 14, "flagged": 3, "not_flagged": 4,
                               "could_not_be_read": 7}


def test_what_cannot_be_read_is_reported_with_its_reason_never_guessed(result):
    unread = {e["view"]: e for e in result["could_not_be_read"]}
    assert set(unread) == {"demo.v_cte", "demo.v_dynamic", "demo.v_apply", "demo.v_other", "demo.v_wrong_columns",
                           "demo.v_cut", "demo.v_encrypted"}
    assert "CTE" in unread["demo.v_cte"]["reason"] and unread["demo.v_cte"]["line"] == 2
    assert unread["demo.v_dynamic"]["reason"].startswith("dynamic SQL")
    assert unread["demo.v_apply"]["reason"] == "APPLY in FROM"
    assert "staging.shipments" in unread["demo.v_other"]["reason"]
    assert "relationship columns" in unread["demo.v_wrong_columns"]["reason"]
    assert "inside a string" in unread["demo.v_cut"]["reason"]
    assert "not available" in unread["demo.v_encrypted"]["reason"]
    assert not set(unread) & {e["view"] for e in result["flagged"]}


def test_no_row_values_and_no_literal_of_a_definition_in_the_answer(result):
    text = json.dumps(result, ensure_ascii=False)
    for literal in ("2026-01-01", "unterminated", "'x'", "SELECT SUM(order_amount) FROM demo.order_lines"):
        assert literal not in text
    assert "1000" not in text and "600" not in text                           # AMOUNT_DEMO's rows are never read
    shown = sql_sums.check(plan(demo_schema()), [("demo", "v_lit", FIRST_LINE)])
    assert shown["read_not_flagged"] == ["demo.v_lit"]
    lit = sql_sums.check(plan(demo_schema()), [("demo", "v_lit", DOUBLED.replace("ON l.order_id = o.order_id",
                                                                                  "ON l.order_id = o.order_id AND l.line_amount > 250"))])
    assert lit["flagged"][0]["join"].endswith("l.line_amount > ?")


def test_the_shop_schema_finds_the_price_on_products():
    p = plan(shop_schema("shop"))
    view = ("CREATE VIEW shop.v_revenue AS SELECT c.name, SUM(p.list_price) AS price_total FROM shop.order_items i "
            "JOIN shop.products p ON p.product_id = i.product_id JOIN shop.orders o ON o.order_id = i.order_id "
            "JOIN shop.customers c ON c.customer_id = o.customer_id GROUP BY c.name")
    right = ("CREATE VIEW shop.v_revenue_right AS SELECT SUM(i.quantity * p.list_price) AS revenue FROM shop.order_items i "
             "JOIN shop.products p ON p.product_id = i.product_id")
    out = sql_sums.check(p, [("shop", "v_revenue", view), ("shop", "v_revenue_right", right)])
    assert [(e["view"], e["amount"], e["line_table"]) for e in out["flagged"]] == [("shop.v_revenue", "products.list_price", "order_items")]
    unread = out["could_not_be_read"]                                         # quantity × price: an expression, not judged
    assert [e["view"] for e in unread] == ["shop.v_revenue_right"] and "i.quantity" in unread[0]["reason"]


def test_an_anti_join_is_not_flagged_but_reported():
    anti = ("CREATE VIEW demo.v_no_lines AS SELECT SUM(o.order_amount) AS t FROM demo.orders o "
            "LEFT JOIN demo.order_lines l ON l.order_id = o.order_id WHERE l.order_id IS NULL")
    out = sql_sums.check(plan(demo_schema()), [("demo", "v_no_lines", anti)])
    assert out["views"]["flagged"] == 0 and "IS NULL" in out["could_not_be_read"][0]["reason"]


def test_unqualified_names_resolve_only_in_the_views_own_schema():
    p = plan(demo_schema())
    bare = "CREATE VIEW {s}.v AS SELECT SUM(order_amount) AS t FROM orders o INNER JOIN order_lines l ON o.order_id = l.order_id"
    assert sql_sums.check(p, [("demo", "v", bare.format(s="demo"))])["views"]["flagged"] == 1
    other = sql_sums.check(p, [("reporting", "v", bare.format(s="reporting"))])
    assert other["views"]["flagged"] == 0 and other["views"]["could_not_be_read"] == 1


def test_information_schema_definitions_of_4000_characters_are_not_read():
    long = DOUBLED + "\n-- " + "x" * (sql_sums.INFO_LIMIT - len(DOUBLED) - 4)
    assert len(long) == sql_sums.INFO_LIMIT
    out = sql_sums.check(plan(demo_schema()), [("demo", "v_long", long)], read_with=sql_sums.DEFINITIONS_SQL_INFO)
    assert out["views"]["could_not_be_read"] == 1 and "4000" in out["could_not_be_read"][0]["reason"]
    full = sql_sums.check(plan(demo_schema()), [("demo", "v_long", long)])
    assert full["views"]["flagged"] == 1


def test_reading_falls_back_and_a_failure_is_said_not_counted_as_zero():
    asked = []

    def info_only(sql):
        asked.append(sql)
        if "sys.sql_modules" in sql:
            raise RuntimeError("('42S02', \"[42S02] Invalid object name 'sys.sql_modules'. (208) (SQLExecDirectW)\")")
        return rows()
    out = sql_sums.check_connection(plan(demo_schema()), info_only)
    assert asked == [sql_sums.DEFINITIONS_SQL, sql_sums.DEFINITIONS_SQL_INFO] and out["read"] == sql_sums.DEFINITIONS_SQL_INFO
    assert out["views"]["flagged"] == 3
    assert all(q.lstrip().upper().startswith("SELECT") for q in asked)

    def refused(sql):
        raise RuntimeError("permission denied (229)")
    bad = sql_sums.check_connection(plan(demo_schema()), refused)
    assert bad["read"] is None and "could not be read" in bad["summary"] and "views" not in bad


def test_validate_plan_returns_it_only_when_asked(monkeypatch):
    from fabric_backend import server
    base = demo_execute()

    def execute(sql):
        if sql == sql_sums.DEFINITIONS_SQL:
            return rows()
        return base(sql)
    monkeypatch.setattr(server, "_connected", lambda *a: (demo_schema(), execute))
    plain = json.loads(server.validate_plan("ws", "lh", schema="demo"))
    assert "sql_sums" not in plain
    out = json.loads(server.validate_plan("ws", "lh", schema="demo", sql_sums=True))
    assert out["sql_sums"]["views"]["flagged"] == 3
    assert {e["view"] for e in out["sql_sums"]["flagged"]} == {"demo.v_orders_per_day", "demo.v_comma", "demo.v_union"}
