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

The amount that is not there: a line table with a quantity (order_items.quantity) and no amount of its own, pointing at
a table that carries the price (products.list_price). A model with only `SUM(quantity)` shows a total quantity where a
report wants an order amount, so `order_amount_measures` writes the amount as quantity × price summed over the line
rows (DAX: SUMX with RELATED over the relationship), and says where the price comes from. A line that carries an amount
(order_items.net_amount, VBAP.NETWR) keeps it: that amount is summed, and no product is computed.
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

# a quantity on a line row and a price on the row it points at (English, Swedish, SAP): quantity, qty, OrderQty, antal,
# MENGE/KWMENG/WMENG; price, list_price, unit_price, ListPrice, pris, NETPR (the last word says price, so PriceLevel is none). The product of the two, summed over the line rows,
# is the amount when the line carries none of its own.
_QUANTITY = ("quantity", "qty", "meng", "antal")
_PRICE = ("price", "pris", "netpr")
_TOTAL = ("total", "extended", "amount", "summa", "belopp")   # TotalPrice, ExtendedPrice: an amount, not a price per unit
_NOT_QUANTITY_END = _NOT_AMOUNT_END + ("unit", "uom", "flag")
ORDER_AMOUNT = "Order amount"


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


def is_quantity(column: str, sql_type: str = "decimal") -> bool:
    """A numeric column whose name reads as a quantity: quantity, qty, OrderQty, antal, MENGE, KWMENG (never quantity_unit)."""
    if not is_numeric(sql_type) and (sql_type or "unknown").lower() != "unknown":
        return False
    words = _words(column)
    if not words or words[-1] in _NOT_QUANTITY_END or column.lower().endswith(("_id", "id")):
        return False
    return any(q in w for w in words for q in _QUANTITY)


def is_price(column: str, sql_type: str = "decimal") -> bool:
    """A numeric column whose name reads as a price per unit: price, list_price, unit_price, ListPrice, pris, NETPR (never
    price_type, price_list_id, or TotalPrice and ExtendedPrice, which are amounts)."""
    if not is_numeric(sql_type) and (sql_type or "unknown").lower() != "unknown":
        return False
    words = _words(column)
    if not words or words[-1] in _NOT_AMOUNT_END or column.lower().endswith(("_id", "id")):
        return False
    if any(x in w for w in words for x in _TOTAL) or "sum" in words:
        return False
    return words[-1] in _PRICE or words[-1].endswith(_PRICE)


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
        packed = {x["column"].lower() for x in (plan.pack or {}).get("amounts", []) if x["table"] == r.target}  # NETWR: the pack knows
        cols = [c.name for c in header.columns if c.name.lower() not in key | refs
                and (looks_like_amount(c.name, c.data_type) or c.name.lower() in packed)]
        if cols:
            out.append({"header": r.target, "line": r.source, "line_columns": list(r.source_cols),
                        "header_columns": list(r.target_cols), "rule": r.rule, "amount_columns": cols})
    return out


def line_amounts(plan: Plan) -> list[dict]:
    """Every line table with a quantity column, from names and types alone (no query): the amount columns it carries
    itself (by name, or named by the pack: VBAP.NETWR) and the price columns on the tables it points at many-to-one,
    each with the relationship that reaches it. `order_amount_measures` turns these into measures."""
    packed = {(x["table"], x["column"].lower()) for x in (plan.pack or {}).get("amounts", [])}
    out = []
    for t in plan.schema:
        key = {c.lower() for c in plan.keys.get(t.name, ([], ""))[0]}
        refs = {c.lower() for r in plan.relationships if r.source == t.name for c in r.source_cols}
        plain = [c for c in t.columns if c.name.lower() not in key | refs]
        qty = [c.name for c in plain if is_quantity(c.name, c.data_type)]
        if not qty:
            continue
        own = [c.name for c in plain if c.name not in qty and (looks_like_amount(c.name, c.data_type) or (t.name, c.name.lower()) in packed)]
        prices = []
        for r in plan.relationships:
            if r.source != t.name or r.target == t.name or r.target not in plan.keys or _one_to_one(plan, r):
                continue
            d = plan.schema[r.target]
            dkey = {c.lower() for c in plan.keys[r.target][0]}
            drefs = {c.lower() for x in plan.relationships if x.source == r.target for c in x.source_cols}
            for c in d.columns:
                if c.name.lower() not in dkey | drefs and is_price(c.name, c.data_type):
                    prices.append({"table": r.target, "column": c.name, "line_columns": list(r.source_cols),
                                   "target_columns": list(r.target_cols), "rule": r.rule})
        out.append({"line": t.name, "quantity": qty[0], "quantities": qty, "amounts": own, "prices": prices})
    return out


def _dax_table(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _dax_column(name: str) -> str:
    return name.replace("]", "]]")


def _amount_name(plan: Plan, line: str) -> str:
    """"Order amount" for an order line (order_items, or a line whose header is an orders table), else "<line> amount"
    (Movement amount, StockItemTransactions amount): the measure says what it adds up."""
    around = [line] + [r.target for r in plan.relationships if r.source == line]
    if any("order" in w for t in around for w in _words(t)):
        return ORDER_AMOUNT
    return f"{line} amount"


def order_amount_measures(plan: Plan, relationships=None, tables: set[str] | None = None) -> dict:
    """The amount measures a semantic model (or a data dictionary) gets from quantity × price:

    - `measures`: one per line table with a quantity, no amount of its own and a price on a table it reaches through a
      relationship in `relationships` (default: the plan's single-column relationships; the semantic model draft passes
      its active ones, because RELATED follows the active relationship). Each has the DAX, where the price comes from
      and why: `SUMX('order_items', 'order_items'[quantity] * RELATED('products'[list_price]))`.
    - `own_amounts`: line tables that carry an amount (line_amount, NETWR): that amount is summed as it is, no product.
    - `not_created`: a quantity with a price in reach, but not over a relationship in `relationships`."""
    allowed = relationships if relationships is not None else \
        [r for r in plan.relationships if len(r.source_cols) == 1 and len(r.target_cols) == 1]
    ok = {(r.source, r.source_cols[0].lower(), r.target) for r in allowed if len(r.source_cols) == 1}
    measures, own, skipped = [], [], []
    for f in line_amounts(plan):
        line, qty = f["line"], f["quantity"]
        if tables is not None and line not in tables:
            continue
        if f["amounts"]:
            own.append({"line": line, "quantity": qty, "amounts": f["amounts"],
                        "why": f"{line} carries {', '.join(f['amounts'])}: an amount on the row is summed as it is, nothing is computed from {qty}"})
            continue
        prices = [p for p in f["prices"] if tables is None or p["table"] in tables]
        if not prices:
            continue
        pr = next((p for p in prices if len(p["line_columns"]) == 1 and (line, p["line_columns"][0].lower(), p["table"]) in ok), None)
        if pr is None:
            skipped.append({"line": line, "quantity": qty, "prices": [f"{p['table']}.{p['column']}" for p in prices],
                            "why": f"{line} has a quantity and no amount, and a price is in reach, but not over an active single-column "
                                   "relationship (RELATED needs one); the lakehouse needs a combined key column, or the price on the line"})
            continue
        dim, price, via = pr["table"], pr["column"], pr["line_columns"][0]
        expr = f"SUMX({_dax_table(line)}, {_dax_table(line)}[{_dax_column(qty)}] * RELATED({_dax_table(dim)}[{_dax_column(price)}]))"
        others = [f"{p['table']}.{p['column']}" for p in prices if p is not pr]
        note = (f"The price comes from {dim}.{price}, one row per {dim}, as it stands at query time: a list price, not necessarily the "
                f"price paid, and a later change of it changes the history. Check against an invoiced amount if there is one"
                + (f"; other prices in reach: {', '.join(others)}" if others else "") + ".")
        measures.append({"table": line, "column": qty, "name": _amount_name(plan, line), "expression": expr, "format": "#,##0.00",
                         "dimension": dim, "price": price, "via": via, "rule": pr["rule"],
                         "why": (f"{line} has a quantity ({qty}) and no amount of its own; the price is on {dim}.{price}, reached through "
                                 f"{line}.{via} → {dim} ({pr['rule']}). The amount is quantity × price summed over the {line} rows (SUMX with "
                                 f"RELATED), so it is at line level and SUM({qty}) alone no longer stands for the order amount. {note.rstrip('.')}"),
                         "price_note": note})
    return {"measures": measures, "own_amounts": own, "not_created": skipped}


def columns(plan: Plan) -> set[tuple[str, str]]:
    """(header table, column) for every header amount: what the drafts treat as header-level."""
    return {(f["header"], c) for f in header_amounts(plan) for c in f["amount_columns"]}


def lines_per_header_sql(schema: str, line: str, cols: list[str], dialect: Dialect = TSQL,
                         header: str | None = None, header_cols: list[str] | None = None) -> str:
    """Header values the line rows reference, how many of them the header table holds, average and largest number of
    line rows per referenced value: read-only."""
    q = dialect.quote
    cs = ", ".join(q(c) for c in cols)
    not_null = " AND ".join(f"{q(c)} IS NOT NULL" for c in cols)
    found = ""
    if header and header_cols:
        on = " AND ".join(f"h.{q(b)} = g.{q(a)}" for a, b in zip(cols, header_cols))
        found = (f", SUM(CASE WHEN EXISTS (SELECT 1 FROM {dialect.table(schema, header)} AS h WHERE {on}) "
                 f"THEN 1 ELSE 0 END) AS headers_in_table")
    return (f"SELECT {dialect.count}(*) AS headers, AVG(1.0 * n) AS avg_lines, MAX(n) AS max_lines{found} "
            f"FROM (SELECT {cs}, {dialect.count}(*) AS n FROM {dialect.table(schema, line)} WHERE {not_null} GROUP BY {cs}) AS g")


def _explain(f: dict, counts: dict | None) -> str:
    line, header, cols = f["line"], f["header"], f["amount_columns"]
    first = cols[0]
    link = f"{line}.{'+'.join(f['line_columns'])} → {header}.{'+'.join(f['header_columns'])}"
    if counts and counts.get("headers"):
        avg = f"{counts['avg_lines']:g}"
        many = (f"{line} has {avg} rows for each row of {header} on average and up to {counts['max_lines']} "
                f"({counts['headers']} referenced header value(s)"
                + (f", {counts['headers_in_table']} of them in {header})" if "headers_in_table" in counts else ")"))
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
                row = list(execute(lines_per_header_sql(plan.schema.schema, f["line"], f["line_columns"], dialect,
                                                         f["header"], f["header_columns"])))[0]
                avg = row.get("avg_lines")
                counts = {"headers": int(row.get("headers") or 0), "avg_lines": round(float(avg), 2) if avg is not None else 0,
                          "max_lines": int(row.get("max_lines") or 0)}
                if row.get("headers_in_table") is not None:
                    counts["headers_in_table"] = int(row["headers_in_table"])
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
