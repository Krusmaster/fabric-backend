"""A larger synthetic SAP order-to-cash demo: 36 months, about 300 customers and 500 materials (round AP2, 18 Nov 2026).

The 17 tables and their columns are exactly those of `sap_demo` (sap_t001 ... sap_adr6), so every tool that runs on the
small demo runs on this one. The small demo covers a few days of October 2026 and a handful of customers: enough for
keys, joins and traps, too little for analyses over time (analysis_plan rightly says forecasting has no history).
This one has 36 calendar months (November 2023 to October 2026) with a trend and a yearly season, customers that
start and stop buying, and materials whose value is skewed (a few carry most of the revenue) and whose demand is steady,
seasonal or sporadic, so ABC/XYZ, RFM and a forecast have something to find.

Every value is made up. Names are "Demo Customer 0042", "Demo Material 0137", "Demo Contact 0007"; streets "Demo Street
42"; e-mail addresses at example.com; telephone numbers "+00 000 0042". No real company, person, address or SAP system
is behind any row; the rows are written from the SAP pack's tables and relationships, not read from SAP.

Deterministic: GENERATOR is plain Python on `random.Random(seed)` using only `random()`, so the same seed gives the same
rows on every machine and Python version. The same text is the code cell of the Fabric notebook (notebook_cells), so
what the tests count is what the notebook writes.

Planted (PLANTED lists each; tests/test_ap2_sap_demo36.py checks them):
  - one orphan: an item (VBAP) of order 0000099999, which does not exist in VBAK;
  - one doubled amount: invoice HEADER_DOUBLED's VBRK.NETWR is twice the sum of its items;
  - a few NULLs: three VBRP.MATNR, two KNA1.ORT01, one VBAK.KNUMV;
  - legitimately blank partner fields in VBPA: contact-person rows (PARVW AP) have a blank KUNNR, customer partner rows a
    blank PARNR, and most rows a blank ADRNR (no address typed into the document); these are no reference, not orphans.

    tables(seed=36)            -> {name: (columns, types, rows)} as sap_demo.tables()
    sqlite(seed=36)            -> (Schema, execute) over the rows in SQLite (prefix sap_), for tests and a local run
    notebook_cells(...)        -> the Fabric notebook's cells: DRY_RUN = True by default, writes only in TARGET_SCHEMA
    notebook_source(...)       -> the notebook as Fabric's notebook-content.py (fabricGitSource)
    notebook_ipynb(...)        -> the same as a Jupyter .ipynb (JSON), for Fabric's Import notebook
    sample(folder)             -> the small CSV sample in examples/sap_demo36/ (the first SAMPLE_CUSTOMERS customers' rows)

    python -m fabric_backend.sap_demo36 --ipynb sap_demo36.ipynb      # write the notebook to import in Fabric
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from . import notebook as _nb

SEED = 36
DEFAULT_SCHEMA = "sap_demo36"
PREFIX = "sap_"
REFUSED_SCHEMAS = ("dbo", "sap_silver", "sap_gold", "silver", "gold", "krusgraph", "krusgraph_analysis")
OWNER_MARK = "krusgraph.demo"                     # the table property the notebook sets, and checks before it replaces a table
SAMPLE_CUSTOMERS = 4

# The generator, verbatim in the notebook's code cell. Plain Python and the standard library only.
GENERATOR = r'''
import math
import random
from datetime import date, timedelta
from decimal import Decimal

D = "decimal(15,2)"
FIRST_MONTH, MONTHS = (2023, 11), 36            # November 2023 to October 2026
LAST_DAY = date(2026, 10, 31)
FOREVER, START = "99991231", "00010101"
N_CUSTOMERS, N_MATERIALS = 300, 500
ORPHAN_ORDER = "0000099999"
COLUMNS = {
    "T001": ["MANDT", "BUKRS", "KTOPL", "WAERS", "ADRNR"],
    "TVKO": ["MANDT", "VKORG", "BUKRS", "WAERS"],
    "KNA1": ["MANDT", "KUNNR", "NAME1", "STRAS", "PSTLZ", "ORT01", "LAND1", "TELF1", "ADRNR"],
    "MARA": ["MANDT", "MATNR", "MTART", "MEINS"],
    "MAKT": ["MANDT", "MATNR", "SPRAS", "MAKTX"],
    "VBAK": ["MANDT", "VBELN", "AUART", "VBTYP", "KUNNR", "VKORG", "NETWR", "WAERK", "ERDAT", "AEDAT", "KNUMV"],
    "VBAP": ["MANDT", "VBELN", "POSNR", "MATNR", "NETWR", "WAERK", "KWMENG", "VRKME", "ERDAT"],
    "VBEP": ["MANDT", "VBELN", "POSNR", "ETENR", "EDATU", "WMENG", "VRKME"],
    "LIKP": ["MANDT", "VBELN", "LFART", "KUNNR", "KUNAG", "VKORG", "ERDAT"],
    "LIPS": ["MANDT", "VBELN", "POSNR", "MATNR", "VGBEL", "VGPOS", "LFIMG", "VRKME"],
    "VBRK": ["MANDT", "VBELN", "FKART", "KUNAG", "KUNRG", "VKORG", "BUKRS", "NETWR", "MWSBK", "WAERK", "FKDAT", "KNUMV"],
    "VBRP": ["MANDT", "VBELN", "POSNR", "MATNR", "AUBEL", "AUPOS", "VGBEL", "VGPOS", "NETWR", "FKIMG", "VRKME"],
    "VBFA": ["MANDT", "VBELV", "POSNV", "VBELN", "POSNN", "VBTYP_N", "VBTYP_V", "RFMNG"],
    "VBPA": ["MANDT", "VBELN", "POSNR", "PARVW", "KUNNR", "PARNR", "ADRNR"],
    "KNVK": ["MANDT", "PARNR", "KUNNR", "LIFNR", "NAMEV", "NAME1", "TELF1", "PAFKT"],
    "ADRC": ["CLIENT", "ADDRNUMBER", "DATE_FROM", "NATION", "DATE_TO", "NAME1", "STREET", "POST_CODE1", "CITY1", "COUNTRY"],
    "ADR6": ["CLIENT", "ADDRNUMBER", "PERSNUMBER", "DATE_FROM", "CONSNUMBER", "SMTP_ADDR", "FLGDEFAULT"],
}
DECIMALS = {"VBAK": ("NETWR",), "VBAP": ("NETWR", "KWMENG"), "VBEP": ("WMENG",), "LIPS": ("LFIMG",), "VBRK": ("NETWR", "MWSBK"),
            "VBRP": ("NETWR", "FKIMG"), "VBFA": ("RFMNG",)}


def generate(seed=36):
    """{name: (columns, types, rows)}: the same rows for the same seed, everywhere."""
    rng = random.Random(seed)
    r = rng.random

    def pick(n):                                  # 0 .. n-1
        return min(int(r() * n), n - 1)

    def normal():                                 # Box-Muller on r() only, so no library version changes the rows
        return math.sqrt(-2.0 * math.log(1.0 - r())) * math.cos(2.0 * math.pi * r())

    def weighted(cum):                            # an index by cumulative weights
        x, lo, hi = r() * cum[-1], 0, len(cum) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if cum[mid] < x:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def num(n, width=10):
        return str(n).zfill(width)

    def money(cents):
        return Decimal(cents) / 100

    def ymd(d):
        return d.strftime("%Y%m%d")

    def month_start(i):
        y, m = FIRST_MONTH[0] + (FIRST_MONTH[1] - 1 + i) // 12, (FIRST_MONTH[1] - 1 + i) % 12 + 1
        return date(y, m, 1)

    t = {name: [] for name in COLUMNS}
    t["T001"].append(("100", "1000", "DEMO", "EUR", "0000000001"))
    t["TVKO"].append(("100", "1000", "1000", "EUR"))
    t["ADRC"].append(("100", "0000000001", START, "", FOREVER, "Demo Company Code", "Demo Street 1", "10000", "Demo City", "DE"))

    # Customers: when they start and stop buying, and how often they buy (a few buy a lot: RFM has something to rank)
    customers = []
    countries = ("DE", "SE", "AT", "NL", "DK")
    for i in range(1, N_CUSTOMERS + 1):
        kunnr, adrnr = num(i), num(100000 + i)
        start = 0 if r() < 0.55 else pick(MONTHS - 3)
        stop = MONTHS if r() < 0.8 else start + 3 + pick(max(1, MONTHS - start - 3))
        rate = 0.15 + 2.5 * r() ** 3                                  # orders per month while active: skewed
        customers.append((kunnr, start, stop, rate))
        city = None if i in (17, 211) else f"Demo City {1 + i % 40}"  # planted: two NULL cities
        country = countries[pick(len(countries))]
        t["KNA1"].append(("100", kunnr, f"Demo Customer {i:04d}", f"Demo Street {i}", f"{10000 + i}", city, country,
                          f"+00 000 {i:04d}", adrnr))
        t["ADRC"].append(("100", adrnr, START, "", FOREVER, f"Demo Customer {i:04d}", f"Demo Street {i}", f"{10000 + i}",
                          city or "Demo City", country))
        t["ADR6"].append(("100", adrnr, "", START, "001", f"orders@customer{i:04d}.example.com", "X"))
        if i % 3 == 0:                                                # a contact person for every third customer
            parnr = num(700000 + i)
            t["KNVK"].append(("100", parnr, kunnr, "", "Demo", f"Contact {i:04d}", f"+00 000 9{i:03d}", "01"))
    contacts = {row[2]: row[1] for row in t["KNVK"]}
    cust_cum, acc = [], 0.0
    for c in customers:
        acc += c[3]
        cust_cum.append(acc)

    # Materials: a skewed price and popularity (ABC), and a demand pattern (XYZ): steady, seasonal or sporadic
    materials = []
    for i in range(1, N_MATERIALS + 1):
        matnr = num(i, 18)
        price = max(150, int(round(math.exp(8.2 + 1.1 * normal()))))  # cents, lognormal: a long tail of dear materials
        popularity = 1.0 / (i ** 0.85)
        pattern = "steady" if r() < 0.45 else ("seasonal" if r() < 0.55 else "sporadic")
        months_on = {m for m in range(MONTHS) if pattern != "sporadic" or r() < 0.3}
        materials.append((matnr, price, popularity, pattern, months_on))
        t["MARA"].append(("100", matnr, "FERT" if i % 4 else "HAWA", "ST"))
        t["MAKT"].append(("100", matnr, "E", f"Demo Material {i:04d}"))
        t["MAKT"].append(("100", matnr, "D", f"Demo Material {i:04d} (D)"))
    mat_cum, acc = [], 0.0
    for m in materials:
        acc += m[2]
        mat_cum.append(acc)

    order_no, delivery_no, invoice_no, knumv = 10000, 80000000, 90000000, 500000
    for month in range(MONTHS):
        first = month_start(month)
        days = (month_start(month + 1) - first).days if month + 1 < MONTHS else 31
        season = 1.0 + 0.3 * math.cos(2.0 * math.pi * (first.month - 11) / 12.0)   # peak in November, low in May
        trend = 1.0 + 0.5 * month / (MONTHS - 1)
        n_orders = int(round(95 * season * trend * (0.9 + 0.2 * r())))
        active = [k for k, c in enumerate(customers) if c[1] <= month < c[2]]
        for _ in range(n_orders):
            k = weighted(cust_cum)
            if k not in active:
                k = active[pick(len(active))]
            kunnr = customers[k][0]
            order_no += 1
            knumv += 1
            vbeln = num(order_no)
            erdat = first + timedelta(days=pick(days))
            items, total = [], 0
            for pos in range(1, 2 + pick(4)):
                for _try in range(20):
                    mi = weighted(mat_cum)
                    if month in materials[mi][4]:
                        break
                matnr, price, _, pattern, _ = materials[mi]
                factor = 1.0 + (0.6 * math.cos(2.0 * math.pi * (first.month - 12) / 12.0) if pattern == "seasonal" else 0.0)
                qty = max(1, int(round((1 + pick(8)) * factor)))
                net = qty * price
                total += net
                items.append((num(pos * 10, 6), matnr, qty, net))
            t["VBAK"].append(("100", vbeln, "TA", "C", kunnr, "1000", money(total), "EUR", ymd(erdat), ymd(erdat),
                              None if order_no == 10077 else num(knumv)))          # planted: one NULL KNUMV
            t["VBPA"].append(("100", vbeln, "000000", "AG", kunnr, "", ""))
            t["VBPA"].append(("100", vbeln, "000000", "WE", kunnr, "", num(900000 + order_no) if order_no % 25 == 0 else ""))
            t["VBPA"].append(("100", vbeln, "000000", "RG", kunnr, "", ""))
            if kunnr in contacts and r() < 0.5:                                    # a contact person: KUNNR blank
                t["VBPA"].append(("100", vbeln, "000000", "AP", "", contacts[kunnr], ""))
            if order_no % 25 == 0:                                                 # an address typed into the order
                t["ADRC"].append(("100", num(900000 + order_no), START, "", FOREVER, "Demo Ship-to", f"Dock {order_no % 97}",
                                  "19999", "Demo Harbour", "DE"))
            for posnr, matnr, qty, net in items:
                t["VBAP"].append(("100", vbeln, posnr, matnr, money(net), "EUR", Decimal(qty), "ST", ymd(erdat)))
                t["VBEP"].append(("100", vbeln, posnr, "0001", ymd(erdat + timedelta(days=7)), Decimal(qty), "ST"))
            delivered = erdat + timedelta(days=2 + pick(9))
            if delivered > LAST_DAY:
                continue                                                           # still open at the end of October 2026
            delivery_no += 1
            likp = num(delivery_no)
            t["LIKP"].append(("100", likp, "LF", kunnr, kunnr, "1000", ymd(delivered)))
            t["VBPA"].append(("100", likp, "000000", "WE", kunnr, "", ""))
            billed = delivered + timedelta(days=pick(4))
            if billed > LAST_DAY:
                for posnr, matnr, qty, net in items:
                    t["LIPS"].append(("100", likp, posnr, matnr, vbeln, posnr, Decimal(qty), "ST"))
                    t["VBFA"].append(("100", vbeln, posnr, likp, posnr, "J", "C", Decimal(qty)))
                continue
            invoice_no += 1
            vbrk = num(invoice_no)
            tax = int(round(total * 0.19))
            t["VBRK"].append(("100", vbrk, "F2", kunnr, kunnr, "1000", "1000", money(total), money(tax), "EUR", ymd(billed),
                              num(knumv + 400000)))
            for posnr, matnr, qty, net in items:
                t["LIPS"].append(("100", likp, posnr, matnr, vbeln, posnr, Decimal(qty), "ST"))
                t["VBRP"].append(("100", vbrk, posnr, matnr, vbeln, posnr, likp, posnr, money(net), Decimal(qty), "ST"))
                t["VBFA"].append(("100", vbeln, posnr, likp, posnr, "J", "C", Decimal(qty)))
                t["VBFA"].append(("100", vbeln, posnr, vbrk, posnr, "M", "C", Decimal(qty)))

    # Planted, at fixed places
    t["VBAP"].append(("100", ORPHAN_ORDER, "000010", materials[0][0], Decimal("10.00"), "EUR", Decimal(1), "ST", "20261015"))
    doubled = 25                                                                   # the 25th invoice's header counts twice
    row = t["VBRK"][doubled]
    t["VBRK"][doubled] = row[:7] + (row[7] * 2,) + row[8:]
    nulls = 0
    for i, row in enumerate(t["VBRP"]):
        if i % 4001 == 1000 and nulls < 3:                                         # three billing items without a material
            t["VBRP"][i] = row[:3] + (None,) + row[4:]
            nulls += 1
    out = {}
    for name, cols in COLUMNS.items():
        kinds = [D if c in DECIMALS.get(name, ()) else "string" for c in cols]
        out[name] = (cols, kinds, t[name])
    return out
'''.strip("\n") + "\n"

_NS: dict = {}
exec(compile(GENERATOR, "<sap_demo36 generator>", "exec"), _NS)
COLUMNS = _NS["COLUMNS"]
ORPHAN_ORDER = _NS["ORPHAN_ORDER"]


def tables(seed: int = SEED) -> dict[str, tuple[list[str], list[str], list[tuple]]]:
    """{name: (columns, types, rows)}, the shape of sap_demo.tables(); decimals as Decimal, dates as 'YYYYMMDD' text."""
    return _NS["generate"](seed)


def planted(seed: int = SEED) -> dict:
    """What GENERATOR plants, found in its own rows (so a changed seed still says where)."""
    t = tables(seed)
    vbrk, vbrp = t["VBRK"][2], t["VBRP"][2]
    items: dict[str, object] = {}
    for row in vbrp:
        items[row[1]] = items.get(row[1], 0) + row[8]
    doubled = [row[1] for row in vbrk if row[1] in items and row[7] == 2 * items[row[1]]]
    return {"orphan": {"table": "VBAP", "VBELN": ORPHAN_ORDER, "missing_in": "VBAK"},
            "doubled_amount": {"table": "VBRK", "VBELN": doubled, "column": "NETWR", "times": 2},
            "nulls": {"VBRP.MATNR": sum(1 for r in vbrp if r[3] is None),
                      "KNA1.ORT01": sum(1 for r in t["KNA1"][2] if r[5] is None),
                      "VBAK.KNUMV": sum(1 for r in t["VBAK"][2] if r[10] is None)},
            "blank_partners": {"VBPA.KUNNR": sum(1 for r in t["VBPA"][2] if r[4] == ""),
                               "VBPA.PARNR": sum(1 for r in t["VBPA"][2] if r[5] == "")}}


def sqlite(seed: int = SEED, prefix: str = PREFIX, schema: str = "sap", data: dict | None = None):
    """(Schema, execute) over the rows in an in-memory SQLite database, like sap_demo.sqlite(); `data` replaces the
    generated tables (the tests change a column or a row)."""
    import sqlite3

    from .dialects import sqlite_sql
    from .schema import Schema
    con = sqlite3.connect(":memory:")
    con.execute(f"ATTACH DATABASE ':memory:' AS {schema}")
    info = []
    for name, (cols, kinds, rows) in (data if data is not None else tables(seed)).items():
        t = prefix + name.lower()
        con.execute(f"CREATE TABLE {schema}.[{t}] ({', '.join(f'[{c}]' for c in cols)})")
        con.executemany(f"INSERT INTO {schema}.[{t}] VALUES ({','.join('?' * len(cols))})",
                        [tuple(float(v) if k != "string" and v is not None else v for v, k in zip(r, kinds)) for r in rows])
        info += [(schema, t, c, "decimal" if k != "string" else "nvarchar", i) for i, (c, k) in enumerate(zip(cols, kinds), 1)]

    def execute(sql: str):
        cur = con.execute(sqlite_sql(sql))
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]
    return Schema.from_information_schema(info, schema=schema), execute


# ------------------------------------------------------------------ the Fabric notebook --------------------------------

def _py(v) -> str:
    return json.dumps(v)


def notebook_cells(target_schema: str = DEFAULT_SCHEMA, seed: int = SEED, prefix: str = PREFIX) -> list[tuple[str, str]]:
    """The notebook: a markdown cell, the parameters (DRY_RUN = True: generate and count, write nothing), the generator
    (GENERATOR verbatim) and the write cell. It writes only <TARGET_SCHEMA>.<prefix><table>, refuses dbo and the
    silver/gold schemas, and replaces a table only when this notebook wrote it (table property krusgraph.demo)."""
    intro = ("# Krusgraph synthetic SAP demo, 36 months (sap_demo36)\n\n"
             "Synthetic, SAP-shaped, not SAP data: every name, address and e-mail address is made up (example.com). "
             "Generated by `fabric_backend/sap_demo36.py` (round AP2). The 17 tables and columns of the small SAP demo, with "
             "36 monthly periods (November 2023 to October 2026), about 300 customers and 500 materials, a few planted "
             "quality issues (one orphan item, one doubled header amount, a few NULLs) and legitimately blank partner "
             "fields in VBPA.\n\n"
             "**DRY_RUN = True** (the default) generates the rows and prints the counts; nothing is written. Set "
             "DRY_RUN = False to write Delta tables in TARGET_SCHEMA only. dbo and the silver/gold schemas are refused, "
             "and a table this notebook did not write is never replaced.")
    params = (f"DRY_RUN = True                 # True: generate and count only; False: write the tables\n"
              f"TARGET_SCHEMA = {_py(target_schema)}   # a new schema of this lakehouse; never dbo, sap_silver or sap_gold\n"
              f"PREFIX = {_py(prefix)}               # table names: {prefix}vbak, {prefix}kna1, ...\n"
              f"SEED = {int(seed)}                     # the same seed gives the same rows")
    write = f'''# Write the tables (only when DRY_RUN is False), each as a Delta table in TARGET_SCHEMA.
from pyspark.sql.types import DecimalType, StringType, StructField, StructType

REFUSED = {_py(list(REFUSED_SCHEMAS))}
OWNER = "sap_demo36"
if TARGET_SCHEMA.lower() in REFUSED:
    raise ValueError(f"TARGET_SCHEMA {{TARGET_SCHEMA}} is refused: choose a new schema such as sap_demo36. Nothing was written.")

data = generate(SEED)
for name, (cols, kinds, rows) in data.items():
    print(f"{{PREFIX}}{{name.lower():6}} {{len(rows):7}} rows")
TABLE_FORMAT = globals().get("TABLE_FORMAT", "delta")


def q(*parts):
    return ".".join("`" + p.replace("`", "``") + "`" for p in parts)


def ours_or_absent(name):
    if not spark.catalog.tableExists(name):
        return True
    props = {{r[0]: r[1] for r in spark.sql(f"SHOW TBLPROPERTIES {{name}}").collect()}}
    return props.get("{OWNER_MARK}") == OWNER


if DRY_RUN:
    print("DRY_RUN = True: nothing was written. Set DRY_RUN = False to write", len(data), "tables in", TARGET_SCHEMA)
else:
    targets = {{name: q(TARGET_SCHEMA, PREFIX + name.lower()) for name in data}}
    foreign = [t for t in targets.values() if not ours_or_absent(t)]
    if foreign:
        raise ValueError("these tables exist and were not written by this notebook: " + ", ".join(foreign) + ". Nothing was written.")
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {{q(TARGET_SCHEMA)}}")
    for name, (cols, kinds, rows) in data.items():
        schema = StructType([StructField(c, DecimalType(15, 2) if k != "string" else StringType(), True) for c, k in zip(cols, kinds)])
        df = spark.createDataFrame(rows, schema)
        df.write.mode("overwrite").format(TABLE_FORMAT).option("overwriteSchema", "true").saveAsTable(targets[name])
        spark.sql(f"ALTER TABLE {{targets[name]}} SET TBLPROPERTIES ('{OWNER_MARK}' = '{{OWNER}}')")
        print(targets[name], spark.read.table(targets[name]).count(), "rows written")'''
    return [("markdown", intro), ("parameters", params), ("code", "# The generator (fabric_backend/sap_demo36.py, GENERATOR).\n" + GENERATOR),
            ("code", write)]


def notebook_source(target_schema: str = DEFAULT_SCHEMA, seed: int = SEED, workspace_id: str = "", lakehouse_id: str = "",
                    lakehouse_name: str = "") -> str:
    """notebook-content.py (fabricGitSource); with a lakehouse id, attached to it as the default lakehouse."""
    return _nb.fabric_source(notebook_cells(target_schema, seed), _nb.notebook_metadata(workspace_id, lakehouse_id, lakehouse_name))


def notebook_ipynb(target_schema: str = DEFAULT_SCHEMA, seed: int = SEED) -> dict:
    """The same cells as a Jupyter notebook (nbformat 4), for Fabric's Import notebook; the parameters cell is tagged."""
    return ipynb(notebook_cells(target_schema, seed))


def ipynb(cells: list[tuple[str, str]]) -> dict:
    """Cells as a Jupyter notebook (nbformat 4.5) with the Synapse PySpark kernel Fabric uses; a parameters cell carries
    the "parameters" tag, as Fabric's toggle parameter cell does. Valid JSON; ids are the cell's position."""
    out = []
    for i, (kind, text) in enumerate(cells):
        lines = text.splitlines(keepends=True)
        if kind == "markdown":
            out.append({"cell_type": "markdown", "id": f"cell-{i}", "metadata": {}, "source": lines})
        else:
            out.append({"cell_type": "code", "id": f"cell-{i}", "execution_count": None, "outputs": [], "source": lines,
                        "metadata": {"tags": ["parameters"]} if kind == "parameters" else {}})
    return {"nbformat": 4, "nbformat_minor": 5, "cells": out,
            "metadata": {"kernel_info": {"name": "synapse_pyspark"}, "language_info": {"name": "python"},
                         "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark"}}}


def sample(folder: str | Path, seed: int = SEED) -> list[Path]:
    """The small CSV sample kept in the repository (examples/sap_demo36/): every row that belongs to the first
    SAMPLE_CUSTOMERS customers (their master data, orders, deliveries, invoices, flow and partners) plus T001 and TVKO.
    Text as text (leading zeros kept), decimals as written, NULL as an empty field."""
    t = tables(seed)
    keep_cust = {r[1] for r in t["KNA1"][2][:SAMPLE_CUSTOMERS]}
    orders = {r[1] for r in t["VBAK"][2] if r[4] in keep_cust}
    deliveries = {r[1] for r in t["LIKP"][2] if r[3] in keep_cust}
    invoices = {r[1] for r in t["VBRK"][2] if r[4] in keep_cust}
    docs = orders | deliveries | invoices
    mats = {r[3] for r in t["VBAP"][2] if r[1] in orders}
    addr = {r[8] for r in t["KNA1"][2] if r[1] in keep_cust} | {r[6] for r in t["VBPA"][2] if r[1] in docs and r[6]}
    keep = {"T001": lambda r: True, "TVKO": lambda r: True, "KNA1": lambda r: r[1] in keep_cust, "MARA": lambda r: r[1] in mats,
            "MAKT": lambda r: r[1] in mats, "VBAK": lambda r: r[1] in orders, "VBAP": lambda r: r[1] in orders,
            "VBEP": lambda r: r[1] in orders, "LIKP": lambda r: r[1] in deliveries, "LIPS": lambda r: r[1] in deliveries,
            "VBRK": lambda r: r[1] in invoices, "VBRP": lambda r: r[1] in invoices, "VBFA": lambda r: r[1] in orders,
            "VBPA": lambda r: r[1] in docs, "KNVK": lambda r: r[2] in keep_cust, "ADRC": lambda r: r[1] in addr or r[1] == "0000000001",
            "ADR6": lambda r: r[1] in addr}
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for name, (cols, kinds, rows) in t.items():
        path = folder / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(cols)
            w.writerows(["" if v is None else str(v) for v in r] for r in rows if keep[name](r))
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> None:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m fabric_backend.sap_demo36", description=__doc__.splitlines()[0])
    ap.add_argument("--ipynb", help="write the Fabric notebook as .ipynb (Import notebook in Fabric)")
    ap.add_argument("--source", help="write the notebook as notebook-content.py (fabricGitSource)")
    ap.add_argument("--sample", help="write the small CSV sample into this folder")
    ap.add_argument("--schema", default=DEFAULT_SCHEMA, help=f"TARGET_SCHEMA in the notebook (default {DEFAULT_SCHEMA})")
    a = ap.parse_args(argv)
    if a.ipynb:
        Path(a.ipynb).write_text(json.dumps(notebook_ipynb(a.schema), indent=1) + "\n", encoding="utf-8")
    if a.source:
        Path(a.source).write_text(notebook_source(a.schema), encoding="utf-8")
    if a.sample:
        sample(a.sample)
    if not (a.ipynb or a.source or a.sample):
        for name, (cols, kinds, rows) in tables().items():
            print(f"{PREFIX}{name.lower():6} {len(rows):7} rows")


if __name__ == "__main__":
    main()
