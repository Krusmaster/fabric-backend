"""The total that doubles: an amount on a header table (orders.order_amount) summed over its line rows (order_items).

The most common report error: a join of orders and order_items repeats every order's amount on each of its lines, so
SUM(orders.order_amount) over the joined rows is too large — an order of 1 000 with two lines adds up to 2 000. This
module points out where a plan allows that, from names and types alone, and counts the lines per header when a
connection is given:

    for each relationship line -> header (many-to-one, not one-to-one)
        the numeric columns of the header that look like amounts (by their words: amount, total, price, belopp, ...)
        and are neither its key, a reference nor an id-like column
        -> each is repeated once per line row in a join of the two

The same answer feeds validate_plan (`amount_levels`), the demo's health check, the semantic model draft (such a column
is not summed by default, and gets a measure on its own table), answer_query_draft (sums at the header's level) and
the gold views (the column is left out of a view at line level). A finding says what could go wrong; whether anyone
sums the column that way is not something the plan can know.
"""
from __future__ import annotations

import re

from .dialects import TSQL, Dialect, of as dialect_of
from .infer import Plan

RULE = ("A number on the header table of a many-to-one relationship is repeated on every line row in a join of the "
        "two; summing it over the joined rows counts each header once per line.")
LEVELS = "order amount and line amount are different levels"

# words that make a numeric column look like money or another additive amount (English and Swedish)
_LONG = ("amount", "total", "price", "cost", "revenue", "value", "freight", "discount", "shipping", "subtotal", "balance",
         "belopp", "summa", "varde", "värde", "kostnad", "moms", "frakt", "rabatt", "netto", "brutto", "intakt", "intäkt", "pris",
         "totalt", "saldo", "avgift")
_SHORT = {"net", "gross", "tax", "vat", "fee", "sum", "amt", "sek", "eur", "usd"}
_NOT_AMOUNT_END = ("id", "key", "code", "no", "nr", "number", "num", "type", "status", "pct", "percent", "rate", "procent", "year", "date")
_NUMERIC = ("int", "bigint", "smallint", "tinyint", "decimal", "numeric", "float", "real", "double", "money", "smallmoney",
            "int64", "int32", "number", "long", "short")


def _words(name: str) -> list[str]:
    spaced = re.sub(r"([a-zåäö])([A-ZÅÄÖ])", r"\1 \2", str(name))
    return [w for w in re.split(r"[^A-Za-z0-9åäöÅÄÖ]+", spaced.lower()) if w]


def is_numeric(sql_type: str) -> bool:
    base = (sql_type or "").lower().split("(")[0].strip()
    return base in _NUMERIC or base.startswith(("decimal", "numeric"))


def looks_like_amount(column: str, sql_type: str = "decimal") -> bool:
    """A numeric column whose name reads as an amount: order_amount, TotalDue, freight, belopp, OrderVärde."""
    if not is_numeric(sql_type) and (sql_type or "unknown").lower() != "unknown":   # a columns list without types: names decide
        return False
    words = _words(column)
    if not words or words[-1] in _NOT_AMOUNT_END or column.lower().endswith(("_id", "id")):
        return False
    return any(w in _SHORT for w in words) or any(x in w for w in words for x in _LONG)


def _one_to_one(plan: Plan, r) -> bool:
    key = plan.keys.get(r.source, ([], ""))[0]
    return bool(key) and {c.lower() for c in key} == {c.lower() for c in r.source_cols}


def header_amounts(plan: Plan) -> list[dict]:
    """Every (line, header, amount columns) the plan allows, from names and types: no query."""
    out = []
    for r in plan.relationships:
        if r.source == r.target or r.target not in plan.keys or _one_to_one(plan, r):
            continue
        header = plan.schema[r.target]
        key = {c.lower() for c in plan.keys[r.target][0]}
        refs = {c.lower() for x in plan.relationships if x.source == r.target for c in x.source_cols}
        cols = [c.name for c in header.columns if c.name.lower() not in key | refs and looks_like_amount(c.name, c.data_type)]
        if cols:
            out.append({"header": r.target, "line": r.source, "line_columns": list(r.source_cols),
                        "header_columns": list(r.target_cols), "rule": r.rule, "amount_columns": cols})
    return out


def columns(plan: Plan) -> set[tuple[str, str]]:
    """(header table, column) for every header amount: what the drafts treat as header-level."""
    return {(f["header"], c) for f in header_amounts(plan) for c in f["amount_columns"]}


def lines_per_header_sql(schema: str, line: str, cols: list[str], dialect: Dialect = TSQL) -> str:
    """Headers referenced, average and largest number of line rows per header: three numbers, read-only."""
    q = dialect.quote
    cs = ", ".join(q(c) for c in cols)
    not_null = " AND ".join(f"{q(c)} IS NOT NULL" for c in cols)
    return (f"SELECT {dialect.count}(*) AS headers, AVG(1.0 * n) AS avg_lines, MAX(n) AS max_lines "
            f"FROM (SELECT {cs}, {dialect.count}(*) AS n FROM {dialect.table(schema, line)} WHERE {not_null} GROUP BY {cs}) AS g")


def _explain(f: dict, counts: dict | None) -> str:
    line, header, cols = f["line"], f["header"], f["amount_columns"]
    first = cols[0]
    link = f"{line}.{'+'.join(f['line_columns'])} → {header}.{'+'.join(f['header_columns'])}"
    if counts and counts.get("headers"):
        avg = f"{counts['avg_lines']:g}"
        many = (f"{line} has {avg} rows for each row of {header} on average and up to {counts['max_lines']} "
                f"({counts['headers']} row(s) of {header} referenced)")
        size = f"so SUM({header}.{first}) over the joined rows comes out about {avg} times too large"
    else:
        many = f"{line} can have several rows for each row of {header} (rows per {header} row: unknown until the data is counted)"
        size = f"so SUM({header}.{first}) over the joined rows counts each {header} row once per {line} row"
    return (f"{header}.{', '.join(cols)} {'is an amount' if len(cols) == 1 else 'are amounts'} on {header}, and {many} "
            f"(rule {f['rule']}: {link}). In a join of the two, each {header} amount is repeated on every {line} row, {size}. "
            f"Sum it on {header} itself, or sum an amount of {line} instead: {LEVELS}.")


def check(plan: Plan, execute=None, max_items: int = 20) -> dict:
    """The header amounts of the plan with an explanation each; with `execute`, the line rows per header counted."""
    found = header_amounts(plan)
    dialect = dialect_of(execute) if execute is not None else TSQL
    counted = 0
    for f in found:
        counts = None
        if execute is not None and counted < max_items:
            counted += 1
            try:
                row = list(execute(lines_per_header_sql(plan.schema.schema, f["line"], f["line_columns"], dialect)))[0]
                avg = row.get("avg_lines")
                counts = {"headers": int(row.get("headers") or 0), "avg_lines": round(float(avg), 2) if avg is not None else 0,
                          "max_lines": int(row.get("max_lines") or 0)}
            except Exception as e:                                       # noqa: BLE001 - one failed count never hides the finding
                f["count_error"] = f"{type(e).__name__}: {e}"
        f["rows_per_header"] = counts if counts and counts["headers"] else "unknown"
        f["explanation"] = _explain(f, counts)
        f["do_instead"] = (f"Aggregate {', '.join(f['amount_columns'])} on {f['header']} (one row per {f['header']}) and join the "
                           f"result, or sum a {f['line']} amount; never SUM({f['header']}.{f['amount_columns'][0]}) over {f['line']} rows.")
    repeated = [f for f in found if isinstance(f["rows_per_header"], dict) and f["rows_per_header"]["max_lines"] > 1]
    summary = (f"{len(found)} header amount(s) that a join with their line rows would repeat"
               + (f"; {len(repeated)} with more than one line per header in the data" if execute is not None else "; rows per header unknown (no rows counted)")
               if found else "no header table with an amount column that a line table points at")
    return {"summary": summary, "rule": RULE, "findings": found,
            "note": "Names and types say where an amount sits; whether a report sums it over the lines is not in the plan. "
                    "The counts are over the whole tables at the moment of the call."}


def before_after_sql(schema: str, f: dict, column: str, dialect: Dialect = TSQL) -> tuple[str, str]:
    """The sum the wrong way (the header amount over the joined line rows) and the right way (once per header that has
    lines), for the same headers: two read-only statements whose results can be put side by side."""
    q, t = dialect.quote, dialect.table
    on = " AND ".join(f"l.{q(a)} = h.{q(b)}" for a, b in zip(f["line_columns"], f["header_columns"]))
    before = f"SELECT SUM(h.{q(column)}) AS total FROM {t(schema, f['line'])} AS l JOIN {t(schema, f['header'])} AS h ON {on}"
    after = (f"SELECT SUM(h.{q(column)}) AS total FROM {t(schema, f['header'])} AS h "
             f"WHERE EXISTS (SELECT 1 FROM {t(schema, f['line'])} AS l WHERE {on})")
    return before, after


def before_after(schema: str, f: dict, execute) -> dict | None:
    """Both sums run against the connection, for the first amount column of a finding; None when they cannot run."""
    col = f["amount_columns"][0]
    before, after = before_after_sql(schema, f, col, dialect_of(execute))
    try:
        b = list(execute(before))[0].get("total")
        a = list(execute(after))[0].get("total")
    except Exception:                                                    # noqa: BLE001
        return None
    return {"column": col, "summed_over_lines": b, "summed_per_header": a, "sql_before": before, "sql_after": after}


def demo() -> dict:
    """The synthetic example of fabric_backend.seed.AMOUNT_DEMO, run in SQLite: one order of 1 000 with two lines (600 and
    400). Summed over the joined lines the order comes out at 2 000; summed on the order, 1 000; the lines add up to 1 000."""
    import sqlite3

    from .dialects import sqlite_sql
    from .infer import plan as make_plan
    from .schema import Column, Schema, Table
    from .seed import AMOUNT_DEMO
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS demo")
    s = Schema(schema="demo")
    for name, (ddl, data) in AMOUNT_DEMO.items():
        con.execute(f"CREATE TABLE demo.[{name}] ({ddl})")
        con.executemany(f"INSERT INTO demo.[{name}] VALUES ({','.join('?' * len(data[0]))})", data)
        s.tables[name] = Table(name, [Column(c.split()[0], c.split()[1].lower()) for c in ddl.split(", ")], schema="demo")

    def execute(sql: str):
        cur = con.execute(sqlite_sql(sql))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    p = make_plan(s)
    found = check(p, execute)
    f = found["findings"][0]
    ba = before_after("demo", f, execute)
    lines = execute("SELECT SUM(line_amount) AS total FROM demo.[order_lines]")[0]["total"]
    con.close()
    return {"finding": f, "before": ba["summed_over_lines"], "after": ba["summed_per_header"], "lines_total": lines,
            "sql_before": ba["sql_before"], "sql_after": ba["sql_after"], "explanation": LEVELS}
