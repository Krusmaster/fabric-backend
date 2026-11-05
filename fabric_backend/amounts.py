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

The flat table (round n106): an export where the order lines already carry the order's amount (one CSV, one row per
line, order_id and order_amount on every row) repeats the amount without any join. With a connection, `check` counts,
one query per (table, header column), whether an amount column has exactly one value per header value while header
values repeat across rows:

    for each table: header candidates (a column named like an id of another entity, order_id in order_lines, or the
    source column of a declared or confirmed relationship) x the table's amount columns
        -> rows, distinct header values, header values on more than one row, header values whose amount differs
        -> no differing value and some repeated: summing the amount over the table counts each header once per row

A header value whose amount differs between its rows is an exception: then the column is not a clean header amount,
and the count is reported without the claim. So is a single repeated header value (one customer with two orders of the
same total): the claim needs at least MIN_REPEATED of them. These queries share `max_items` with the line counts above.
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
    """Header values the line rows reference, how many of them the header table holds, average, smallest and largest
    number of line rows per referenced value: read-only."""
    q = dialect.quote
    cs = ", ".join(q(c) for c in cols)
    not_null = " AND ".join(f"{q(c)} IS NOT NULL" for c in cols)
    grouped = f"(SELECT {cs}, {dialect.count}(*) AS n FROM {dialect.table(schema, line)} WHERE {not_null} GROUP BY {cs}) AS g"
    if header and header_cols:
        # n87: the EXISTS is worked out per group first and summed one level up; SQL Server refuses an aggregate over a
        # subquery (error 130), which is what the SUM(CASE WHEN EXISTS ...) of earlier rounds was
        on = " AND ".join(f"h.{q(b)} = g.{q(a)}" for a, b in zip(cols, header_cols))
        flagged = (f"(SELECT g.n, CASE WHEN EXISTS (SELECT 1 FROM {dialect.table(schema, header)} AS h WHERE {on}) "
                   f"THEN 1 ELSE 0 END AS in_header FROM {grouped}) AS f")
        return (f"SELECT {dialect.count}(*) AS headers, AVG(1.0 * f.n) AS avg_lines, MIN(f.n) AS min_lines, MAX(f.n) AS max_lines, "
                f"SUM(f.in_header) AS headers_in_table FROM {flagged}")
    return f"SELECT {dialect.count}(*) AS headers, AVG(1.0 * n) AS avg_lines, MIN(n) AS min_lines, MAX(n) AS max_lines FROM {grouped}"


def readable_count_error(e: BaseException) -> str:
    """A failed counting query in plain words: the endpoint's own message without the driver's prefixes, SQLSTATE and
    call name, with SQL Server's error number when there is one."""
    import re
    text = str(e).strip()
    wrapped = re.match(r"^\(\s*'[0-9A-Z]{5}'\s*,\s*['\"](.*)['\"]\s*\)$", text, re.S)     # pyodbc: ('42000', '[42000] [...]...')
    if wrapped:
        text = wrapped.group(1)
    text = re.sub(r"\(SQL\w+\)", "", re.sub(r"\[[^\]]*\]", "", text))                  # driver prefixes, the call name
    code = re.search(r"\((\d{2,6})\)", text)
    msg = " ".join(re.sub(r"\(\d{2,6}\)", "", text).split()).strip(" .;")
    code = code.group(1) if code else ""
    msg = msg[:300]
    return ("the SQL endpoint refused the counting query" + (f" (SQL Server error {code})" if code else "")
            + (f": {msg}" if msg else "") + "; the rows per header are not known")


def _explain(f: dict, counts: dict | None, label=None) -> str:
    line, header, cols = f["line"], f["header"], f["amount_columns"]
    first = cols[0]
    link = f"{line}.{'+'.join(f['line_columns'])} → {header}.{'+'.join(f['header_columns'])}"
    if counts and counts.get("headers"):
        avg = f"{counts['avg_lines']:g}"
        many = (f"{line} has {avg} rows for each row of {header} on average and up to {counts['max_lines']} "
                f"({counts['headers']} referenced header value(s)"
                + (f", {counts['headers_in_table']} of them in {header})" if "headers_in_table" in counts else ")"))
        if counts.get("min_lines") == counts["max_lines"] > 1:           # n89: every header has n lines: the factor is exact
            size = f"so SUM({header}.{first}) over the joined rows comes out {counts['max_lines']} times too large"
        else:                                                            # n89: the average of lines is not the ratio of the sums
            spread = (f", because the {header} rows have between {counts['min_lines']} and {counts['max_lines']} {line} rows each"
                      if counts.get("min_lines") else "")
            size = (f"so SUM({header}.{first}) over the joined rows counts each {header} row once per {line} row and comes out "
                    f"too large; by how much depends on the amounts{spread}, and the average number of rows is not the ratio "
                    f"of the two sums")
        if counts["max_lines"] <= 1:                                     # n88: one line per header today: nothing doubles yet
            return (f"{header}.{', '.join(cols)} {'is an amount' if len(cols) == 1 else 'are amounts'} on {header}. In the data "
                    f"no row is repeated today: {line} has at most one row for each row of {header} ({counts['headers']} "
                    f"referenced header value(s)" + (f", {counts['headers_in_table']} of them in {header})" if "headers_in_table" in counts else ")")
                    + f", so SUM({header}.{first}) over a join of the two is correct today. The relationship (rule "
                    f"{(label or str)(f['rule'])}: {link}) allows several {line} rows per {header} row, so the sum can come out "
                    f"too large as soon as there are. Sum it on {header} itself, or sum an amount of {line} instead: {LEVELS}.")
    else:
        many = f"{line} can have several rows for each row of {header} (rows per {header} row: unknown until the data is counted)"
        size = f"so SUM({header}.{first}) over the joined rows counts each {header} row once per {line} row"
    return (f"{header}.{', '.join(cols)} {'is an amount' if len(cols) == 1 else 'are amounts'} on {header}, and {many} "
            f"(rule {(label or str)(f['rule'])}: {link}). In a join of the two, each {header} amount is repeated on every {line} row, {size}. "
            f"Sum it on {header} itself, or sum an amount of {line} instead: {LEVELS}.")


FLAT_RULE = ("In a flat table an amount with exactly one value per header value (order_amount per order_id), where header "
             "values repeat across rows, is the header's amount copied onto each of its rows; summing it over the table "
             "counts each header once per row.")
_ID_END = ("id", "no", "nr", "number", "num", "key")
MIN_REPEATED = 2        # one repeated header value with one amount can be chance; the claim needs at least two
_POSITION = {"line", "pos", "position", "seq", "sequence", "row", "item", "rad", "radnr"}   # line_no numbers rows, it names no entity


def _entity(words: list[str]) -> str:
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words)


def flat_candidates(plan: Plan) -> list[dict]:
    """Every (table, header column, amount columns) the flat check counts, from names and types alone: no query. A header
    column is the source column of a single-column relationship of the plan (declared, confirmed or inferred) or a column
    named like an id of another entity (order_id in order_lines; never the table's own OrderID in Orders, nor its whole
    single-column key). The amount columns are the table's amounts by name (or named by the pack) that are neither key,
    reference nor header column, and not a price per unit. Ordered so that a header whose entity the amount names comes
    first (order_id with order_amount)."""
    packed = {(x["table"], x["column"].lower()) for x in (plan.pack or {}).get("amounts", [])}
    out = []
    for t in plan.schema:
        key = [c.lower() for c in plan.keys.get(t.name, ([], ""))[0]]
        own_key = key[0] if len(key) == 1 else None
        own = _entity(_words(t.name))
        headers: dict[str, tuple[str, str]] = {}
        for r in plan.relationships:
            if r.source == t.name and r.target != t.name and len(r.source_cols) == 1 and r.source_cols[0].lower() != own_key:
                c = r.source_cols[0]
                headers.setdefault(c.lower(), (c, f"relationship {t.name}.{c} → {r.target} (rule {plan.label(r.rule)})"))
        for c in t.columns:
            w = _words(c.name)
            ent = _entity(w[:-1])
            if (len(w) >= 2 and w[-1] in _ID_END and ent != own and not own.endswith(" " + ent) and w[-2] not in _POSITION
                    and c.name.lower() != own_key and not looks_like_amount(c.name, c.data_type)):
                headers.setdefault(c.name.lower(), (c.name, f"named like an id of {ent}"))
        refs = {c.lower() for r in plan.relationships if r.source == t.name for c in r.source_cols}
        amounts_ = [c.name for c in t.columns if c.name.lower() not in set(key) | refs | set(headers)
                    and not is_price(c.name, c.data_type)
                    and (looks_like_amount(c.name, c.data_type) or (t.name, c.name.lower()) in packed)]
        if not amounts_:
            continue
        for col, why in headers.values():
            ent = set(_entity(_words(col)[:-1]).split())
            near = [a for a in amounts_ if ent & set(_entity(_words(a)).split())]
            out.append({"table": t.name, "header_column": col, "header_rule": why,
                        "amount_columns": near + [a for a in amounts_ if a not in near], "_near": bool(near)})
    out.sort(key=lambda f: not f.pop("_near"))                       # stable: schema order within each group
    return out


def flat_sql(schema: str, table: str, header: str, amount_columns: list[str], dialect: Dialect = TSQL) -> str:
    """One read-only query for one header column and its amount columns: rows with a header value (row_count), distinct
    header values, header values on more than one row (repeated_values) and, per amount column i, header values whose
    amount differs between their rows (differs_i; a NULL beside a value counts as different). Counts only, no values."""
    q, count = dialect.quote, dialect.count
    h = q(header)
    inner = "".join(f", {count}(DISTINCT {q(a)}) AS d{i}, {count}({q(a)}) AS c{i}" for i, a in enumerate(amount_columns))
    outer = "".join(f", SUM(CASE WHEN g.d{i} > 1 OR (g.c{i} > 0 AND g.c{i} < g.n) THEN 1 ELSE 0 END) AS differs_{i}"
                    for i in range(len(amount_columns)))
    return (f"SELECT SUM(g.n) AS row_count, {count}(*) AS header_values, SUM(CASE WHEN g.n > 1 THEN 1 ELSE 0 END) AS repeated_values"
            f"{outer} FROM (SELECT {h}, {count}(*) AS n{inner} FROM {dialect.table(schema, table)} WHERE {h} IS NOT NULL "
            f"GROUP BY {h}) AS g")


def flat_sum_once_sql(schema: str, table: str, header: str, amount: str, dialect: Dialect = TSQL) -> str:
    """The amount summed once per header value: read-only."""
    q = dialect.quote
    return (f"SELECT SUM(x.{q(amount)}) AS total FROM (SELECT {q(header)}, MAX({q(amount)}) AS {q(amount)} "
            f"FROM {dialect.table(schema, table)} WHERE {q(header)} IS NOT NULL GROUP BY {q(header)}) AS x")


def _flat_entry(schema: str, c: dict, amount: str, n: int, values: int, repeated: int, differs: int, dialect: Dialect) -> dict:
    t, h = c["table"], c["header_column"]
    pattern = repeated >= MIN_REPEATED and differs == 0
    e = {"table": t, "header_column": h, "header_rule": c["header_rule"], "amount_column": amount, "rows": n,
         "header_values": values, "repeated_header_values": repeated, "differing_header_values": differs,
         "pattern": pattern, "sql": flat_sql(schema, t, h, [amount], dialect)}
    if pattern:
        e["explanation"] = (f"{t}.{amount} has one value per {h}, and {repeated} of the {values} {h} values are on more than one "
                            f"of the {n} rows, so SUM({amount}) over {t} counts each {h}'s amount once per row instead of once.")
        e["sum_once_sql"] = flat_sum_once_sql(schema, t, h, amount, dialect)
        e["do_instead"] = (f"Sum {amount} once per {h} (sum_once_sql), or sum an amount that belongs to each row; never "
                           f"SUM({amount}) over the {t} rows.")
    elif not differs:
        e["explanation"] = (f"{t}.{amount} has one value per {h}, but only {repeated} of the {values} {h} values is on more than "
                            f"one of the {n} rows: too few to tell a header amount from chance, so it is not taken for one.")
    else:
        e["explanation"] = (f"{t}.{amount} is not one value per {h}: of the {repeated} {h} values on more than one row, "
                            f"{differs} carry different {amount} values on different rows ({n} rows, {values} {h} values), so it "
                            "is not taken for a header amount.")
    return e


def _flat(plan: Plan, execute, budget: int, dialect: Dialect) -> tuple[list[dict], int, list[str]]:
    """The flat check within `budget` queries: (entries, candidates not counted, errors). An entry is listed when the
    pattern holds or a header value's amount differs; a header that never repeats, or no rows, is nothing to report."""
    schema = plan.schema.schema
    entries, errors, left = [], [], 0
    for c in flat_candidates(plan):
        if budget <= 0:
            left += 1
            continue
        budget -= 1
        try:
            row = list(execute(flat_sql(schema, c["table"], c["header_column"], c["amount_columns"], dialect)))[0]
        except Exception as e:                                           # noqa: BLE001 - one failed count never stops the rest
            errors.append(readable_count_error(e))
            continue
        n, values, repeated = (int(row.get(k) or 0) for k in ("row_count", "header_values", "repeated_values"))
        for i, a in enumerate(c["amount_columns"]):
            differs = int(row.get(f"differs_{i}") or 0)
            if n and (differs or repeated):
                entries.append(_flat_entry(schema, c, a, n, values, repeated, differs, dialect))
    return entries, left, errors


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
                if row.get("min_lines") is not None:                     # n89: equal to max_lines, the factor is exact
                    counts["min_lines"] = int(row["min_lines"])
                if row.get("headers_in_table") is not None:
                    counts["headers_in_table"] = int(row["headers_in_table"])
            except Exception as e:                                       # noqa: BLE001 - one failed count never hides the finding
                f["count_error"] = readable_count_error(e)
        f["rows_per_header"] = counts if counts and counts["headers"] else "unknown"
        f["explanation"] = _explain(f, counts, plan.label)
        f["do_instead"] = (f"Aggregate {', '.join(f['amount_columns'])} on {f['header']} (one row per {f['header']}) and join the "
                           f"result, or sum a {f['line']} amount; never SUM({f['header']}.{f['amount_columns'][0]}) over {f['line']} rows.")
    flat = flat_left = flat_errors = None
    if execute is not None:                                              # n106: the flat check, in what is left of the budget
        flat, flat_left, flat_errors = _flat(plan, execute, max_items - counted, dialect)
    repeated = [f for f in found if isinstance(f["rows_per_header"], dict) and f["rows_per_header"]["max_lines"] > 1]
    failed = [f for f in found if "count_error" in f]
    counted_ok = [f for f in found if isinstance(f["rows_per_header"], dict)]
    if execute is None:
        counts = "; rows per header unknown (no rows counted)"
    elif failed and not counted_ok:                                  # never a 0 for counts that did not run
        counts = (f"; {len(failed)} could not be counted, so whether a header has more than one line in the data is not "
                  f"known ({failed[0]['count_error']})")
    else:
        counts = (f"; {len(repeated)} of {len(counted_ok)} counted with more than one line per header in the data"
                  + (f"; {len(failed)} could not be counted ({failed[0]['count_error']})" if failed else "")
                  if failed else f"; {len(repeated)} with more than one line per header in the data")
    summary = (f"{len(found)} header amount(s) that a join with their line rows would repeat" + counts
               if found else "no header table with an amount column that a line table points at")
    out = {"summary": summary, "rule": RULE, "findings": found}
    if flat or flat_left or flat_errors:
        claimed = [e for e in flat if e["pattern"]]
        out["summary"] += ((f"; {len(claimed)} amount(s) in a flat table repeated on every row of a header value ("
                            + ", ".join(f"{e['table']}.{e['amount_column']} per {e['header_column']}" for e in claimed[:3])
                            + (", ..." if len(claimed) > 3 else "") + ")" if claimed else "")
                           + (f"; {differ} flat-table amount(s) whose value differs within a header value (not header amounts)"
                              if (differ := sum(1 for e in flat if e["differing_header_values"])) else "")
                           + (f"; {few} flat-table amount(s) with one value per header value but too few repeated header values "
                              "to tell" if (few := len(flat) - len(claimed) - differ) else "")
                           + (f"; {flat_left} flat-table check(s) not run: amount_levels' budget of {max_items} queries was used up" if flat_left else "")
                           + (f"; {len(flat_errors)} flat-table check(s) could not be counted ({flat_errors[0]})" if flat_errors else ""))
        out.update({"flat_rule": FLAT_RULE, "flat_tables": flat})
        if flat_left:
            out["flat_not_counted"] = flat_left
        if flat_errors:
            out["flat_count_errors"] = flat_errors
    out["note"] = ("Names and types say where an amount sits; whether a report sums it over the lines is not in the plan. "
                   "The counts are over the whole tables at the moment of the call.")
    return out


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
