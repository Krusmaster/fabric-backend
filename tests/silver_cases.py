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


EXPECTED_QUARANTINE = {("customers", "K2", "the key (customer_id) is NULL"): 1,
                       ("customers", "K2", "another row has the same key (customer_id); one row per key was kept (no ordering column: pass order_by)"): 1,
                       ("orders", "K2", "another row has the same key (order_id); the row with the latest order_date was kept"): 1,
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
