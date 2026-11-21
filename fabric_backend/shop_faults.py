"""2026-11-21, round BL5 (sprint item BL5, backlog C-37). The synthetic shop with five planted faults.

Clean demo data only ever shows "holds". This is the shop of fabric_backend/seed.py with five faults put in on purpose,
each documented in FAULTS with the finding Krusgraph should give, so a demo (and a sceptical data engineer) can see the
checks find what was planted and nothing else. docs/PLANTED-FAULTS.md is the page; tests/test_bl5_shop_faults.py
asserts every line of FAULTS against the engine; tests/corpus/shop_faults.json is the case for the score tooling.

    from fabric_backend import shop_faults
    shop_faults.tables()      # {table: (columns, rows)}: the seven shop tables, changed, and newsletter_signups
    shop_faults.check()       # plan by names, then the counting checks of validate_plan (keys, links, amount levels)

The five faults:

  F1  customers           one customer_id twice (a second row for customer 4)               key not unique
  F2  order_items         three lines of two orders that are not in orders                  some lines point at nothing
  F3  orders              order_amount, the order's total, on the header of order_items     the total doubles over lines
  F4  newsletter_signups  customer_id from an older system: no value matches a customer     the link matches no rows
  F5  orders              order_amount in EUR and SEK, with a currency column beside it     not detected yet (see below)

F5 is not found by validate_plan or amounts today: nothing in either reads a currency column. FAULTS says so
(`detected` is False) instead of a test being tuned around it; sprint item BL10 (measures that respect currency, unit
and sign) is where it would be found.

One finding comes from the clean shop as well and is not a planted fault: products.list_price is a price on the header
of order_items, so summing it over the order lines repeats it (CLEAN_FINDINGS). It is listed so "nothing else is
flagged" means exactly that: the planted faults plus what the clean shop already shows.

Deterministic rules only: no model call, no network, synthetic rows only (invented names, no customer data).
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime

from . import evidence, seed
from .infer import plan as make_plan
from .schema import Column, Schema, Table

SCHEMA = "shop_faults"

# F1: a second row for customer 4, as a double load of a changed customer gives
DUPLICATE_CUSTOMER = (4, "Elbe Sport Kiel", "DE")
# F2: lines of orders 990 and 991, which the orders table does not have (deleted, or not loaded yet)
ORPHAN_LINES = [(990, 1, 3, 2.0), (990, 2, 7, 1.0), (991, 1, 1, 1.0)]
# F5: the orders of these customers (all Swedish) are in SEK; the rest in EUR. 10.0 SEK per EUR, a round synthetic rate
SEK_CUSTOMERS = (3, 5, 9)
SEK_PER_EUR = 10.0
# F4: customer numbers of an older newsletter system, 1001 to 1008: none is a customer_id of the shop
SIGNUPS = [(i, 1000 + i, (date(2026, 8, 1).toordinal() + 3 * i)) for i in range(1, 9)]

COLUMNS = {
    "customers": [("customer_id", "int"), ("name", "string"), ("country", "string")],
    "categories": [("id", "int"), ("name", "string")],
    "products": [("product_id", "int"), ("name", "string"), ("category_id", "int"), ("list_price", "double")],
    "addresses": [("address_id", "int"), ("customer_id", "int"), ("city", "string")],
    "orders": [("order_id", "int"), ("customer_id", "int"), ("order_date", "date"), ("ship_to_id", "int"),
               ("order_amount", "double"), ("currency", "string")],
    "order_items": [("order_id", "int"), ("line_no", "int"), ("product_id", "int"), ("quantity", "double")],
    "audit_log": [("event", "string"), ("customer_id", "int"), ("happened_at", "timestamp")],
    "newsletter_signups": [("signup_id", "int"), ("customer_id", "int"), ("signed_up_on", "date")],
}

# what the clean shop already shows (not planted): products.list_price summed over order_items rows
CLEAN_FINDINGS = ("amount:products.list_price over order_items",)

FAULTS = (
    {"id": "F1", "table": "customers", "item": "key:customers", "detected": True,
     "planted": "customer_id 4 is on two rows (a second row for Elbe Sport, as a double load of a changed customer gives).",
     "finding": "not unique: 1 duplicate rows (10 distinct values in 11 rows)"},
    {"id": "F2", "table": "order_items", "item": "link:order_items.order_id -> orders", "detected": True,
     "planted": "three order lines of orders 990 and 991, which are not in orders.",
     "finding": "3 of 137 rows (2.2%) point at nothing"},
    {"id": "F3", "table": "orders", "item": "amount:orders.order_amount over order_items", "detected": True,
     "planted": "orders.order_amount, each order's total, on the header of order_items: a join of the two repeats it on "
                "every line, so summing it over the lines doubles (or triples) each order.",
     "finding": "orders.order_amount is an amount on orders, and order_items has 2.23 rows for each row of orders on average "
                "and up to 3"},
    {"id": "F4", "table": "newsletter_signups", "item": "link:newsletter_signups.customer_id -> customers", "detected": True,
     "planted": "newsletter_signups.customer_id holds customer numbers of an older system (1001 to 1008): the link to "
                "customers is right by name and matches no row.",
     "finding": "8 of 8 rows (100.0%) point at nothing"},            # F1 adds: "but the target key of customers is not unique"
    {"id": "F5", "table": "orders", "item": "currency:orders.order_amount", "detected": False,
     "planted": "orders.order_amount is in SEK for the Swedish customers (3, 5, 9) and in EUR for the rest; the column "
                "currency says which. Summing order_amount adds SEK and EUR.",
     "finding": "not detected: validate_plan and amounts read no currency column (sprint item BL10 is where it belongs)"},
)


def _amount(lines: list[tuple], prices: dict[int, float], order_id: int) -> float:
    return round(sum(q * prices[p] for o, _n, p, q in lines if o == order_id), 2)


def tables(seed_value: int = 42) -> dict[str, tuple[list[tuple[str, str]], list[tuple]]]:
    """{table: (columns, rows)}: the seed shop with the five faults planted. Same rows on every run."""
    base = seed.rows(seed_value)
    iso = lambda v: v.isoformat() if isinstance(v, (date, datetime)) else v       # noqa: E731
    rows = {t: [tuple(iso(v) for v in r) for r in data] for t, data in base.items()}
    rows["customers"] = rows["customers"] + [DUPLICATE_CUSTOMER]                                   # F1
    prices = {p[0]: p[3] for p in seed.PRODUCTS}
    orders = []
    for oid, cid, day, ship_to in rows["orders"]:                                                 # F3 and F5
        eur = _amount(rows["order_items"], prices, oid)
        sek = cid in SEK_CUSTOMERS
        orders.append((oid, cid, day, ship_to, round(eur * SEK_PER_EUR, 2) if sek else eur, "SEK" if sek else "EUR"))
    rows["orders"] = orders
    rows["order_items"] = rows["order_items"] + ORPHAN_LINES                                      # F2
    rows["newsletter_signups"] = [(i, c, date.fromordinal(d).isoformat()) for i, c, d in SIGNUPS]  # F4
    return {t: (COLUMNS[t], rows[t]) for t in COLUMNS}


def schema(name: str = SCHEMA) -> Schema:
    """The eight tables as a `Schema` (no rows), for planning by names as validate_plan does."""
    s = Schema(schema=name)
    for t, cols in COLUMNS.items():
        s.tables[t] = Table(t, [Column(c, ty) for c, ty in cols], schema=name)
    return s


def _sqlite(data: dict, name: str):
    from .platforms.local import _sqlite_execute
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute(f"ATTACH DATABASE ':memory:' AS [{name}]")
    for t, (cols, rows) in data.items():
        con.execute(f"CREATE TABLE [{name}].[{t}] ({', '.join(f'[{c}]' for c, _ty in cols)})")
        if rows:
            con.executemany(f"INSERT INTO [{name}].[{t}] VALUES ({','.join('?' * len(cols))})", rows)
    return _sqlite_execute(con), con.close


def flagged(full: dict) -> dict[str, str]:
    """Every check of a validate result that is not a pass: {item: verdict or explanation}."""
    out = {}
    for k in full["keys"]:
        if not str(k.get("verdict", "")).startswith("unique in all"):
            out[f"key:{k['table']}"] = k.get("verdict") or k.get("error") or "not counted"
    for r in full["relationships"]:
        if not str(r.get("verdict", "")).startswith("holds for all"):
            out[f"link:{r['source']}.{'+'.join(r['columns'])} -> {r['target']}"] = r.get("verdict") or r.get("error") or "not counted"
    levels = full.get("amount_levels") or {}
    for f in levels.get("findings", []):
        for c in f["amount_columns"]:
            out[f"amount:{f['header']}.{c} over {f['line']}"] = f["explanation"]
    for e in levels.get("flat_tables", []) or []:
        if e.get("pattern"):
            out[f"flat:{e['table']}.{e['amount_column']} per {e['header_column']}"] = e.get("explanation", "")
    return out


def check(data: dict | None = None, max_items: int = 200) -> dict:
    """Plan by names (as validate_plan does with no decisions), then validate_plan's counting checks over the rows:
    every key and link counted, and the amount levels (amounts.check, inside evidence.validate). Read-only, in SQLite.
    Returns the validate result, the flagged items and, per planted fault, whether it was found with the expected reason."""
    data = tables() if data is None else data
    s = Schema(schema=SCHEMA)
    for t, (cols, _rows) in data.items():
        s.tables[t] = Table(t, [Column(c, ty) for c, ty in cols], schema=SCHEMA)
    p = make_plan(s)
    execute, close = _sqlite(data, SCHEMA)
    try:
        full = evidence.validate(p, execute, max_items=max_items)
    finally:
        close()
    got = flagged(full)
    faults = []
    for f in FAULTS:
        said = got.get(f["item"])
        faults.append({"id": f["id"], "item": f["item"], "found": said is not None, "said": said,
                       "as_expected": (said is not None and f["finding"] in said) if f["detected"] else said is None})
    planted = {f["item"] for f in FAULTS}
    return {"summary": full["summary"], "flagged": got, "faults": faults,
            "other": sorted(i for i in got if i not in planted and i not in CLEAN_FINDINGS), "validate": full}


def clean_check(max_items: int = 200) -> dict:
    """The same check on the clean seed shop (seven tables, no fault), for comparison."""
    iso = lambda v: v.isoformat() if isinstance(v, (date, datetime)) else v       # noqa: E731
    base = seed.rows()
    data = {t: ([(c.split()[0], c.split()[1].lower()) for c in ddl.split(", ")], [tuple(iso(v) for v in r) for r in base[t]])
            for t, ddl in seed.SCHEMAS.items()}
    return check(data, max_items)


__all__ = ["FAULTS", "CLEAN_FINDINGS", "SCHEMA", "tables", "schema", "check", "clean_check", "flagged"]
