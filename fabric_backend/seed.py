"""Synthetic shop data for a demo / reviewer Fabric workspace. Run in a Fabric notebook attached to the lakehouse.

    %pip install git+https://github.com/Krusmaster/fabric-backend
    from fabric_backend.seed import seed
    seed(spark, schema="shop")
    seed(spark, schema="shop", mill=True)      # also the synthetic manufacturing company in its own schema 'mill'
    seed(spark, schema="shop", sap=True)       # also the SAP-shaped samples sap_sd and sap_mm (synthetic, not SAP data)
    seed(spark, schema="sap_cds")              # only the CDS-view-shaped sample (n230: I_SalesDocument, ...; synthetic, not SAP data)

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


# GR1: the same customers in three systems (a CRM, an ERP shaped like SAP's KNA1, an MDM hub), for match_records
# (fabric_backend/record_match.py). Invented companies, organisation numbers in a made-up format (QX-nnnn-nn, no real
# register uses it), written the way each system writes them: dashes in the CRM, nothing in the ERP, dots in the MDM, so
# rule N2 (spaces, dashes, dots and slashes removed) is what makes them meet. Deliberate faults: a lower-case and a
# padded number in the CRM (N1), Theta Tryck twice in the CRM and My Media twice in the ERP (duplicates), Delta Logistik
# in Norway in the CRM only and Zeta Data with another name in the ERP (conflicts), Kappa Kemi, Ny Nät, Xi Textil and a
# mistyped Omikron Optik in one or two systems only, and Lambda Lås without a number. Kept apart from the shop's seven
# tables, so the shop's plan, the site's demo and the goldens stay as they are; seed(records=True) writes it to the
# schemas crm, erp and mdm.
RECORDS = {
    "crm": {"accounts": ("account_id INT, account_name STRING, org_no STRING, country STRING, email STRING", [
        (101, "Alpha AB", "QX-1001-01", "SE", "info@alpha.example"),
        (102, "Beta Bygg AB", "QX-1002-02", "SE", "order@beta.example"),
        (103, "Gamma Foods AB", "QX-1003-03", "SE", "hello@gamma.example"),
        (104, "Delta Logistik AB", "QX-1004-04", "NO", "info@delta.example"),
        (105, "Epsilon Energi AB", "qx-1005-05", "SE", "info@epsilon.example"),
        (106, "Zeta Data AB", "QX-1006-06", "SE", "kontakt@zeta.example"),
        (107, "Eta Verkstad AB", " QX-1007-07 ", "SE", "info@eta.example"),
        (108, "Theta Tryck AB", "QX-1008-08", "SE", "info@theta.example"),
        (109, "Theta Tryck AB", "QX 1008 08", "SE", "sales@theta.example"),
        (110, "Iota Instrument AB", "QX-1009-09", "SE", "info@iota.example"),
        (111, "Kappa Kemi AB", "QX-1010-10", "SE", "info@kappa.example"),
        (112, "Omikron Optik AB", "QX-1016-16", "SE", "info@omikron.example"),
        (113, "Lambda Lås AB", None, "SE", "info@lambda.example"),
    ])},
    "erp": {"KNA1": ("KUNNR STRING, NAME1 STRING, LAND1 STRING, STCD1 STRING", [
        ("0000200001", "Alpha AB", "SE", "QX100101"),
        ("0000200002", "Beta Bygg AB", "SE", "QX100202"),
        ("0000200003", "Gamma Foods AB", "SE", "QX100303"),
        ("0000200004", "Delta Logistik AB", "SE", "QX100404"),
        ("0000200005", "Epsilon Energi AB", "SE", "QX100505"),
        ("0000200006", "Zeta Data Aktiebolag", "SE", "QX100606"),
        ("0000200007", "Eta Verkstad AB", "SE", "QX100707"),
        ("0000200008", "Theta Tryck AB", "SE", "QX100808"),
        ("0000200009", "Iota Instrument AB", "SE", "QX100909"),
        ("0000200011", "My Media AB", "SE", "QX101111"),
        ("0000200012", "My Media AB", "SE", "QX101111"),
        ("0000200013", "Ny Nät AB", "SE", "QX101212"),
    ])},
    "mdm": {"customer": ("customer_id INT, customer_name STRING, org_number STRING, country_code STRING", [
        (1, "Alpha AB", "QX.1001.01", "SE"),
        (2, "Beta Bygg AB", "QX.1002.02", "SE"),
        (3, "Gamma Foods AB", "QX.1003.03", "SE"),
        (4, "Delta Logistik AB", "QX.1004.04", "SE"),
        (5, "Epsilon Energi AB", "QX.1005.05", "SE"),
        (6, "Zeta Data AB", "QX.1006.06", "SE"),
        (7, "Eta Verkstad AB", "QX.1007.07", "SE"),
        (8, "Theta Tryck AB", "QX.1008.08", "SE"),
        (9, "Iota Instrument AB", "QX.1009.09", "SE"),
        (10, "Kappa Kemi AB", "QX.1010.10", "SE"),
        (12, "Ny Nät AB", "QX.1012.12", "SE"),
        (13, "Xi Textil AB", "QX.1013.13", "SE"),
        (14, "Omikron Optik AB", "QX.1014.14", "SE"),
    ])},
}


def records_schema(name: str):
    """GR1: one schema of RECORDS ("crm", "erp" or "mdm") as a `Schema` (no data)."""
    from .schema import Schema, Table, Column
    s = Schema(schema=name)
    for table, (cols, _) in RECORDS[name].items():
        s.tables[table] = Table(table, [Column(c.split()[0], c.split()[1].lower()) for c in cols.split(", ")], schema=name)
    return s


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
         sap: bool = False, records: bool = False) -> dict[str, int]:
    """Create (or replace) the seven tables in `schema` of the attached lakehouse. Returns row counts.

    mill=True (default off) also writes the sixteen tables of the synthetic manufacturing company in fabric_backend/mill.py
    to `mill_schema`; their counts come back as "mill.<table>". The shop is written either way and stays the default.
    sap=True (default off, n202) also writes the two SAP-shaped samples of fabric_backend/sap_sample.py, synthetic and
    not SAP data, to the schemas `sap_sd` (order to invoice) and `sap_mm` (purchase to pay); counts as "sap_sd.VBAK".
    schema="sap_cds" (n230) writes only the sample shaped like released SAP CDS views (fabric_backend/sap_cds_demo.py:
    I_SalesDocument, I_SalesDocumentItem, ..., synthetic and not SAP data) to that schema, and not the shop.
    records=True (default off, GR1) also writes RECORDS, the same customers in three systems, to the schemas crm, erp and
    mdm; counts as "crm.accounts".

    On a lakehouse without schemas the tables go to the default schema (`dbo` as seen by the SQL endpoint) instead,
    with a printed note, so they are visible to Krusgraph; use schema="dbo" in the tools then. The mill's tables are
    then not written (they would overwrite nothing of the shop's, but two companies in one schema read as one)."""
    if schema.lower() == "sap_cds":                 # n230: the sample shaped like released SAP CDS views, and nothing else
        from . import sap_cds_demo
        if not schemas_enabled(spark):
            print("This lakehouse was created without 'Lakehouse schemas', so a 'sap_cds' schema would be invisible to its SQL "
                  "endpoint. Writing the tables to the default schema instead: use schema='dbo' in Krusgraph.")
            return sap_cds_demo.seed(spark, None)
        return sap_cds_demo.seed(spark, schema)
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
    if records:
        if target is None:
            print("The three-system customer sample needs a lakehouse with 'Lakehouse schemas'; it was not written.")
        else:
            for part, tables in RECORDS.items():
                spark.sql(f"CREATE SCHEMA IF NOT EXISTS {part}")
                for name, (ddl, data) in tables.items():
                    df = spark.createDataFrame(data, ddl)
                    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{part}.{name}")
                    counts[f"{part}.{name}"] = len(data)
    if sap:
        if target is None:
            print("The SAP-shaped samples need a lakehouse with 'Lakehouse schemas'; they were not written.")
        else:
            from . import sap_sample as _sap
            for sample in _sap.SAMPLES:
                counts.update({f"{sample}.{k}": n for k, n in _sap.seed(spark, sample).items()})
    return counts
