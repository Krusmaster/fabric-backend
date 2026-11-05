"""Round n106: a header amount in a flat table, inside validate_plan's amount_levels.

An export where the order lines already carry the order's amount repeats that amount without any join: summing it over
the table counts each order once per line. amounts.check counts, one query per (table, header column), whether an
amount column has exactly one value per header value while header values repeat. All rows here are synthetic.
"""
from __future__ import annotations

import json
import sqlite3

from fabric_backend import amounts, browser_check, evidence
from fabric_backend.dialects import sqlite_sql
from fabric_backend.infer import plan
from fabric_backend.schema import Schema

# Distinctive values: none of them may appear in any output (counts only, no row values).
SECRET = ("987654.32", "123457.89", "55501.07", "777.13", "ZXQ-41")


def _source(tables: dict[str, tuple[list[tuple[str, str]], list[tuple]]]):
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS x")
    info = []
    for name, (cols, rows) in tables.items():
        con.execute(f"CREATE TABLE x.[{name}] (" + ", ".join(f"[{c}] {t}" for c, t in cols) + ")")
        con.executemany(f"INSERT INTO x.[{name}] VALUES ({','.join('?' * len(cols))})", rows)
        info += [("x", name, c, t, i) for i, (c, t) in enumerate(cols, 1)]
    sent: list[str] = []

    def execute(sql: str):
        sent.append(sql)
        cur = con.execute(sqlite_sql(sql))
        return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    execute.sent = sent
    return plan(Schema.from_information_schema(info, schema="x")), execute


COLS = [("order_id", "int"), ("line_no", "int"), ("product_code", "varchar"), ("order_amount", "decimal"),
        ("line_amount", "decimal")]
# three orders: two of them on several lines, the order amount repeated on each line, the line amounts their own
FLAT = [(1, 1, "ZXQ-41", 987654.32, 600.0), (1, 2, "B", 987654.32, 400.0),
        (2, 1, "A", 123457.89, 250.0),
        (3, 1, "C", 55501.07, 777.13), (3, 2, "C", 55501.07, 30.0), (3, 3, "C", 55501.07, 31.0)]


def _flat(rows=FLAT, cols=COLS, name="order_lines"):
    return _source({name: (cols, rows)})


def _entry(levels, column, header="order_id"):
    return next(e for e in levels["flat_tables"] if e["amount_column"] == column and e["header_column"] == header)


def test_a_flat_orders_with_lines_table_is_found_with_its_counts():
    p, ex = _flat()
    levels = evidence.validate(p, ex)["amount_levels"]
    e = _entry(levels, "order_amount")
    assert e["pattern"] is True
    assert (e["rows"], e["header_values"], e["repeated_header_values"], e["differing_header_values"]) == (6, 3, 2, 0)
    assert e["header_rule"] == "named like an id of order"
    assert "counts each order_id's amount once per row" in e["explanation"] and e["explanation"].count(". ") == 0
    assert "order_lines.order_amount per order_id" in levels["summary"]
    assert levels["flat_rule"] == amounts.FLAT_RULE
    # the SQL the customer can run gives the same counts, and the sum once per order is the three orders' amounts
    row = ex(e["sql"])[0]
    assert (row["row_count"], row["header_values"], row["repeated_values"], row["differs_0"]) == (6, 3, 2, 0)
    assert round(ex(e["sum_once_sql"])[0]["total"], 2) == round(987654.32 + 123457.89 + 55501.07, 2)


def test_the_summary_shows_it_as_needing_attention():
    p, ex = _flat()
    s = evidence.summarize(evidence.validate(p, ex), p)
    shown = s["attention"]["amount_levels"]
    assert [(e["table"], e["amount_column"]) for e in shown] == [("order_lines", "order_amount")]
    assert s["totals"]["amount_levels"]["failed"] == 1 and s["needs_attention"] == 1
    assert "semantic_model_draft" not in [x["tool"] for x in s["next_steps"]]   # not "all checks passed"


def test_a_true_line_amount_is_not_flagged():
    p, ex = _flat()
    levels = evidence.validate(p, ex)["amount_levels"]
    e = _entry(levels, "line_amount")
    assert e["pattern"] is False and e["differing_header_values"] == 2 and "sum_once_sql" not in e
    assert not [x for x in levels["flat_tables"] if x["pattern"] and x["amount_column"] == "line_amount"]
    # line_no numbers the rows of an order: it is no header column
    assert all(x["header_column"] != "line_no" for x in levels["flat_tables"])


def test_exceptions_are_reported_and_the_pattern_is_not_claimed():
    rows = [r if r[:2] != (3, 3) else (3, 3, "C", 55502.07, 31.0) for r in FLAT]   # one line of order 3 differs
    p, ex = _flat(rows)
    full = evidence.validate(p, ex)
    e = _entry(full["amount_levels"], "order_amount")
    assert e["pattern"] is False
    assert (e["rows"], e["header_values"], e["repeated_header_values"], e["differing_header_values"]) == (6, 3, 2, 1)
    assert "is not one value per order_id" in e["explanation"] and "once per row" not in e["explanation"]
    assert "flat-table amount(s) whose value differs" in full["amount_levels"]["summary"]
    assert "repeated on every row of a header value" not in full["amount_levels"]["summary"]
    assert "attention" not in evidence.summarize(full, p) or "amount_levels" not in evidence.summarize(full, p)["attention"]


def test_a_null_beside_a_value_is_an_exception():
    rows = [r if r[:2] != (1, 2) else (1, 2, "B", None, 400.0) for r in FLAT]
    p, ex = _flat(rows)
    e = _entry(evidence.validate(p, ex)["amount_levels"], "order_amount")
    assert e["pattern"] is False and e["differing_header_values"] == 1


def test_one_repeated_header_value_is_too_few_to_claim_it():
    """/check's Salesforce + ERP example: one customer has two orders with the same total, by chance."""
    rows = [(1, 1, "A", 100.0, 100.0), (2, 1, "A", 100.0, 100.0), (2, 2, "A", 100.0, 0.0), (3, 1, "B", 70.0, 70.0)]
    p, ex = _flat(rows)
    levels = amounts.check(p, ex)
    e = _entry(levels, "order_amount")
    assert e["pattern"] is False and (e["repeated_header_values"], e["differing_header_values"]) == (1, 0)
    assert "too few to tell" in e["explanation"] and "too few repeated header values to tell" in levels["summary"]
    crm = browser_check.analyze("crm")
    assert not [f for f in crm["findings"] if f["check"] == "flat_amount"]


def test_no_header_candidate_gives_nothing():
    p, ex = _source({"payments": ([("payment_id", "int"), ("paid_on", "date"), ("amount", "decimal")],
                                  [(1, "2026-01-01", 10.0), (2, "2026-01-02", 10.0)])})
    assert amounts.flat_candidates(p) == []
    levels = amounts.check(p, ex)
    assert "flat_tables" not in levels and "flat_rule" not in levels
    assert not any("GROUP BY" in sql for sql in ex.sent)
    # own id in its own table is no header either, nor is anything counted without a connection
    p2, ex2 = _source({"orders": ([("OrderID", "int"), ("OrderAmount", "decimal")], [(1, 5.0), (1, 5.0)])})
    assert amounts.flat_candidates(p2) == []
    p3, _ = _flat()
    assert "flat_tables" not in amounts.check(p3)


def test_a_relationship_source_column_is_a_header_candidate():
    p, ex = _source({
        "customers": ([("customer_id", "int"), ("name", "varchar")], [(1, "a"), (2, "b")]),
        "invoice_export": ([("invoice_ref", "int"), ("cust", "int"), ("credit_limit_amount", "decimal")],
                           [(1, 1, 500.0), (2, 1, 500.0), (3, 2, 900.0), (4, 2, 900.0)]),
    })
    p = plan(p.schema, confirmed=[{"source": "invoice_export", "source_cols": ["cust"], "target": "customers",
                                   "target_cols": ["customer_id"]}])
    c = [x for x in amounts.flat_candidates(p) if x["table"] == "invoice_export"]
    assert [x["header_column"] for x in c] == ["cust"] and "relationship invoice_export.cust → customers" in c[0]["header_rule"]
    e = _entry(amounts.check(p, ex), "credit_limit_amount", "cust")
    assert e["pattern"] is True and (e["repeated_header_values"], e["differing_header_values"]) == (2, 0)


def test_the_budget_is_respected():
    cols = COLS + [("customer_id", "int"), ("store_id", "int")]
    rows = [r + (r[0] % 2, 7) for r in FLAT]
    p, ex = _flat(rows, cols)
    assert len(amounts.flat_candidates(p)) == 3
    assert amounts.flat_candidates(p)[0]["header_column"] == "order_id"        # the header the amount names comes first
    levels = amounts.check(p, ex, max_items=1)
    assert sum("repeated_values" in sql for sql in ex.sent) == 1
    assert levels["flat_not_counted"] == 2 and "2 flat-table check(s) not run: amount_levels' budget of 1 queries was used up" in levels["summary"]
    assert _entry(levels, "order_amount")["pattern"] is True
    ex.sent.clear()
    none = amounts.check(p, ex, max_items=0)
    assert none["flat_tables"] == [] and none["flat_not_counted"] == 3 and not ex.sent
    # validate_plan: keys and relationships first, then what is left (at most 20) for amount_levels
    ex.sent.clear()
    evidence.validate(p, ex, max_items=2)
    assert sum("repeated_values" in sql for sql in ex.sent) == 2


def test_no_row_values_in_any_output():
    p, ex = _flat()
    full = evidence.validate(p, ex)
    text = json.dumps([full, evidence.summarize(full, p)], default=str)
    csv = ("order_id,line_no,product_code,order_amount,line_amount\n"
           + "".join(",".join(str(v) for v in r) + "\n" for r in FLAT)).encode()
    out = browser_check.analyze("files", [("order_lines.csv", csv)])
    flat = [f for f in out["findings"] if f["check"] == "flat_amount"]
    text += json.dumps(flat, default=str)
    for v in SECRET:
        assert v not in text and v.rstrip("0") not in text


def test_check_in_the_browser_shows_the_flat_amount():
    """/check runs browser_check.analyze in Pyodide, the same engine: the finding comes with counts and a SQL."""
    csv = ("order_id,line_no,order_amount,line_amount\n"
           + "".join(f"{r[0]},{r[1]},{r[3]},{r[4]}\n" for r in FLAT)).encode()
    events: list[dict] = []
    out = browser_check.analyze("files", [("order_lines.csv", csv)], emit=events.append)
    flat = [f for f in out["findings"] if f["check"] == "flat_amount"]
    assert [f["title"] for f in flat] == ["order_lines.order_amount is one amount per order_id, repeated on every row"]
    f = flat[0]
    assert f["severity"] == "warning" and "GROUP BY [order_id]" in f["sql"]
    assert f["checked"].startswith("Counted on all 6 rows of order_lines")
    assert "1 amount(s) repeated on every row of a flat table" in next(e["detail"] for e in events if e["step"] == "validate")
