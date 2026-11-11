"""The shop seed with the problems a real bronze layer has, and what the silver notebook must make of it (shared by
test_silver_notebook.py and test_spark_notebooks.py)."""
import datetime

from fabric_backend import seed


def seed_rows() -> dict[str, list[dict]]:
    """The seed as dicts, plus the problems a real bronze layer has."""
    cols = {t: [c.split()[0] for c in spec.split(", ")] for t, spec in seed.SCHEMAS.items()}
    data = {t: [dict(zip(cols[t], r)) for r in rows] for t, rows in seed.rows().items()}
    data["customers"] += [{"customer_id": None, "name": "Nameless", "country": "SE"},
                          {"customer_id": 3, "name": "Lakeside Tea House", "country": "SE"}]            # a NULL key, an exact duplicate
    first = dict(data["orders"][0])
    data["orders"] += [dict(first, order_date=datetime.date(2026, 12, 1)),                              # a newer version of order 100
                       {"order_id": 200, "customer_id": 77, "order_date": datetime.date(2026, 10, 2), "ship_to_id": 1}]   # unknown customer
    data["order_items"] += [{"order_id": 200, "line_no": 1, "product_id": 1, "quantity": 1.0},           # its order goes to quarantine
                            {"order_id": 999, "line_no": 1, "product_id": 1, "quantity": 2.0}]           # no such order
    data["products"] += [{"product_id": 9, "name": "Spare tube", "category_id": None, "list_price": 4.5}]  # a NULL reference stays
    data["audit_log"] += [{"event": "login", "customer_id": 55, "happened_at": datetime.datetime(2026, 10, 5, 12, 0)}]
    return data


# n208: the silver notebook removes rows only on a key that was declared (K0), given by a person (K1) or counted in the rows
# (R5). The seed's keys are guessed from names (K2), so the tests that exercise de-duplication give the two keys whose
# rows have real duplicates here, as a person does after the review; EXPECTED_QUARANTINE is what silver makes of the
# seed then. Without them (EXPECTED_QUARANTINE_GUESSED) every row of customers and orders stays, and only references fail.
GIVEN_KEYS = {"customers": ["customer_id"], "orders": ["order_id"]}

EXPECTED_QUARANTINE = {("customers", "K1", "the key (customer_id) is NULL"): 1,
                       ("customers", "K1", "another row has the same key (customer_id); one row per key was kept (no ordering column: pass order_by)"): 1,
                       ("orders", "K1", "another row has the same key (order_id); the row with the latest order_date was kept"): 1,
                       ("orders", "R1", "customer_id has no row in customers (orders.customer_id = customers.customer_id)"): 1,
                       ("order_items", "R1", "order_id has no row in orders (order_items.order_id = orders.order_id)"): 2,
                       ("audit_log", "R1", "customer_id has no row in customers (audit_log.customer_id = customers.customer_id)"): 1}


def counts(quarantine):
    out: dict = {}
    for q in quarantine:
        k = (q["source_table"], q["rule"], q["reason"])
        out[k] = out.get(k, 0) + 1
    return out


def sqlite_execute(data: dict[str, list[dict]]):
    """Round n115: the same rows in SQLite (schema shop), as validate_plan reads them: an execute(sql) -> list of dicts."""
    import sqlite3

    from fabric_backend.dialects import sqlite_sql
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS shop")
    for t, spec in seed.SCHEMAS.items():
        cols = [c.split()[0] for c in spec.split(", ")]
        con.execute(f"CREATE TABLE shop.[{t}] ({', '.join(cols)})")
        con.executemany(f"INSERT INTO shop.[{t}] VALUES ({','.join('?' * len(cols))})",
                        [tuple(str(v) if hasattr(v, "isoformat") else v for v in r.values()) for r in data.get(t, [])])

    def execute(sql: str):
        cur = con.execute(sqlite_sql(sql))
        return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    return execute


# n208: the same seed with the keys only guessed from names: no row leaves for its key (the NULL customer, the copy of
# customer 3 and the older version of order 100 stay in silver); the references fail exactly as before.
EXPECTED_QUARANTINE_GUESSED = {k: v for k, v in EXPECTED_QUARANTINE.items() if k[1] != "K1"}


# n208: the audit's two cases (tests/test_n208_guessed_keys.py, and on a local Spark in tests/test_spark_notebooks.py). A
# fact table `sales` that starts with three references gets the K4 key of the three; a line table with a column `no` gets
# `no` alone (K2). Both keys are guessed from names.
N208_TABLES = {
    "customers": [("customer_id", "int"), ("name", "varchar")],
    "products": [("product_id", "int"), ("name", "varchar")],
    "stores": [("store_id", "int"), ("city", "varchar")],
    "sales": [("customer_id", "int"), ("product_id", "int"), ("store_id", "int"), ("quantity", "int"), ("amount", "decimal(18,2)")],
    "invoices": [("invoice_id", "int"), ("customer_id", "int")],
    "invoice_lines": [("no", "int"), ("invoice_id", "int"), ("product_id", "int"), ("amount", "decimal(18,2)")],
}


def n208_rows() -> dict[str, list[dict]]:
    """Genuine repeated rows: customer 1 buys product 1 in store 1 twice (two sales of 5.00), and invoice 1 and invoice 2
    both have a line `no` 1."""
    return {
        "customers": [{"customer_id": 1, "name": "Ada"}, {"customer_id": 2, "name": "Bo"}],
        "products": [{"product_id": 1, "name": "Tea"}, {"product_id": 2, "name": "Cup"}],
        "stores": [{"store_id": 1, "city": "Umeå"}],
        "sales": [{"customer_id": 1, "product_id": 1, "store_id": 1, "quantity": 1, "amount": 5.0},
                  {"customer_id": 1, "product_id": 1, "store_id": 1, "quantity": 1, "amount": 5.0},
                  {"customer_id": 2, "product_id": 2, "store_id": 1, "quantity": 2, "amount": 8.0}],
        "invoices": [{"invoice_id": 1, "customer_id": 1}, {"invoice_id": 2, "customer_id": 2}],
        "invoice_lines": [{"no": 1, "invoice_id": 1, "product_id": 1, "amount": 5.0},
                          {"no": 2, "invoice_id": 1, "product_id": 2, "amount": 3.0},
                          {"no": 1, "invoice_id": 2, "product_id": 2, "amount": 8.0}],
    }
