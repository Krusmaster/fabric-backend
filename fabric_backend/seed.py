"""Synthetic shop data for a demo / reviewer Fabric workspace. Run in a Fabric notebook attached to the lakehouse.

    %pip install git+https://github.com/Krusmaster/fabric-backend
    from fabric_backend.seed import seed
    seed(spark, schema="shop")
    seed(spark, schema="shop", mill=True)      # also the synthetic manufacturing company in its own schema 'mill'
    seed(spark, schema="shop", sap=True)       # also the SAP-shaped samples sap_sd and sap_mm (synthetic, not SAP data)

Seven tables shaped like examples/columns.csv (plus a list price on the products), deterministic (same rows every run), no real names or companies
beyond obviously invented ones. This is what reviewers of the Claude directory listing connect to — never a
customer's or an employer's workspace.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

CUSTOMERS = [
    (1, "Harbour Bikes", "DE"), (2, "Fjord Outdoor", "NO"), (3, "Lakeside Tea House", "SE"), (4, "Elbe Sport", "DE"),
    (5, "Nordic Pedal", "SE"), (6, "Rhine Velo", "DE"), (7, "Baltic Leaf", "FI"), (8, "Heath Cycles", "DE"),
    (9, "Gotland Gear", "SE"), (10, "Moorland Tea Co", "DE"),
]
CATEGORIES = [(1, "Bikes"), (2, "Tea"), (3, "Accessories")]
# list_price: the shop's only price, on the product (one row per product). An order line has a quantity and no amount,
# so the order amount is quantity × list_price summed over the lines (fabric_backend/amounts.py, order_amount_measures).
PRODUCTS = [
    (1, "Trail bike", 1, 899.0), (2, "City bike", 1, 649.0), (3, "Green tea 100 g", 2, 6.5), (4, "Black tea 100 g", 2, 5.9),
    (5, "Rooibos 100 g", 2, 6.2), (6, "Helmet", 3, 59.0), (7, "Bottle", 3, 12.0), (8, "Lights set", 3, 29.0),
]
CITIES = {"DE": ["Hamburg", "Leipzig", "Freiburg", "Kiel"], "SE": ["Uppsala", "Visby", "Lund"], "NO": ["Bergen"], "FI": ["Turku"]}


def rows(seed_value: int = 42) -> dict[str, list[tuple]]:
    rnd = random.Random(seed_value)
    addresses, aid = [], 1
    for cid, _, country in CUSTOMERS:
        for _ in range(rnd.choice([1, 1, 2])):
            addresses.append((aid, cid, rnd.choice(CITIES[country])))
            aid += 1
    orders, items, audit = [], [], []
    start = date(2026, 9, 1)
    for oid in range(100, 160):
        cid = rnd.choice([c[0] for c in CUSTOMERS])
        own = [a[0] for a in addresses if a[1] == cid]
        orders.append((oid, cid, start + timedelta(days=rnd.randrange(0, 61)), rnd.choice(own)))
        for line in range(1, rnd.choice([2, 2, 3]) + 1):
            pid = rnd.choice([p[0] for p in PRODUCTS])
            items.append((oid, line, pid, float(rnd.choice([1, 1, 2, 3, 5]))))
    for i in range(40):
        cid = rnd.choice([c[0] for c in CUSTOMERS])
        audit.append((rnd.choice(["login", "address_changed", "order_viewed", "export"]), cid,
                      datetime(2026, 10, 1) + timedelta(hours=rnd.randrange(0, 24 * 30))))
    return {
        "customers": [(c[0], c[1], c[2]) for c in CUSTOMERS],
        "categories": CATEGORIES,
        "products": PRODUCTS,
        "addresses": addresses,
        "orders": orders,
        "order_items": items,
        "audit_log": audit,
    }


SCHEMAS = {
    "customers": "customer_id INT, name STRING, country STRING",
    "categories": "id INT, name STRING",
    "products": "product_id INT, name STRING, category_id INT, list_price DOUBLE",
    "addresses": "address_id INT, customer_id INT, city STRING",
    "orders": "order_id INT, customer_id INT, order_date DATE, ship_to_id INT",
    "order_items": "order_id INT, line_no INT, product_id INT, quantity DOUBLE",
    "audit_log": "event STRING, customer_id INT, happened_at TIMESTAMP",
}

# The total that doubles (fabric_backend/amounts.py): one order of 1 000 with two lines. Kept apart from the seven shop
# tables so the shop's plan, the site's demo and the live workspace stay as they are; `fabric-backend demo` shows it as
# a finding of its own.
AMOUNT_DEMO = {
    "orders": ("order_id INT, order_date DATE, order_amount DOUBLE", [(1, "2026-10-01", 1000.0)]),
    "order_lines": ("order_id INT, line_no INT, line_amount DOUBLE", [(1, 1, 600.0), (1, 2, 400.0)]),
}


def schema(name: str = "shop"):
    """The seven tables as a `Schema` (no data), for planning offline — the site's demo runs `plan()` on this."""
    from .schema import Schema, Table, Column
    s = Schema(schema=name)
    for table, cols in SCHEMAS.items():
        s.tables[table] = Table(table, [Column(c.split()[0], c.split()[1].lower()) for c in cols.split(", ")], schema=name)
    return s


def schemas_enabled(spark) -> bool:
    """True when the attached lakehouse was created with "Lakehouse schemas" (it then has a `dbo` schema).

    Without schemas, `CREATE SCHEMA x` makes a separate Spark database whose tables the lakehouse's SQL analytics
    endpoint never shows, so Krusgraph (which reads through that endpoint) would find nothing."""
    try:
        names = {str(r[0]).lower().split(".")[-1].strip("`") for r in spark.sql("SHOW SCHEMAS").collect()}
    except Exception:                                                    # noqa: BLE001 - be permissive, decide below
        return False
    return "dbo" in names


def seed(spark, schema: str = "shop", seed_value: int = 42, mill: bool = False, mill_schema: str = "mill",
         sap: bool = False) -> dict[str, int]:
    """Create (or replace) the seven tables in `schema` of the attached lakehouse. Returns row counts.

    mill=True (default off) also writes the sixteen tables of the synthetic manufacturing company in fabric_backend/mill.py
    to `mill_schema`; their counts come back as "mill.<table>". The shop is written either way and stays the default.
    sap=True (default off, n202) also writes the two SAP-shaped samples of fabric_backend/sap_sample.py, synthetic and
    not SAP data, to the schemas `sap_sd` (order to invoice) and `sap_mm` (purchase to pay); counts as "sap_sd.VBAK".

    On a lakehouse without schemas the tables go to the default schema (`dbo` as seen by the SQL endpoint) instead,
    with a printed note, so they are visible to Krusgraph; use schema="dbo" in the tools then. The mill's tables are
    then not written (they would overwrite nothing of the shop's, but two companies in one schema read as one)."""
    target = schema
    if schema.lower() != "dbo" and not schemas_enabled(spark):
        print(f"This lakehouse was created without 'Lakehouse schemas', so a '{schema}' schema would be invisible "
              f"to its SQL endpoint. Writing the tables to the default schema instead: use schema='dbo' in Krusgraph.")
        target = None
    else:
        spark.sql(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    counts = {}
    for name, data in rows(seed_value).items():
        df = spark.createDataFrame(data, SCHEMAS[name])
        df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{target}.{name}" if target else name)
        counts[name] = len(data)
    if mill:
        if target is None:
            print("The 'mill' sample needs a lakehouse with 'Lakehouse schemas'; it was not written.")
        else:
            from . import mill as _mill
            counts.update({f"{mill_schema}.{k}": n for k, n in _mill.seed(spark, mill_schema).items()})
    if sap:
        if target is None:
            print("The SAP-shaped samples need a lakehouse with 'Lakehouse schemas'; they were not written.")
        else:
            from . import sap_sample as _sap
            for sample in _sap.SAMPLES:
                counts.update({f"{sample}.{k}": n for k, n in _sap.seed(spark, sample).items()})
    return counts
