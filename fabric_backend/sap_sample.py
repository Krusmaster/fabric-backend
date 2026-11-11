"""Synthetic, SAP-shaped sample data, not SAP data: 'sap_sd' (order to invoice) and 'sap_mm' (purchase to pay).

    %pip install git+https://github.com/Krusmaster/fabric-backend
    from fabric_backend.seed import seed
    seed(spark, schema="shop", sap=True)            # the shop as before, and sap_sd and sap_mm in schemas of their own

What it is. Two small sets of tables with the structure of SAP ERP / SAP S/4HANA sales and purchasing tables, for demos,
/check and films, generated from one seed with `random.Random`: the same seed gives the same rows on every machine. No
row comes from an SAP system, an SAP customer or SAP's own demo data. Company, customer, supplier and material names
are invented ("Example Customer 0007"). Two years of dates, November 2024 to October 2026.

Where the names come from. Every standard table and every column of a standard table is a name the repository's SAP
pack already has (fabric_backend/packs/sap/, which cites SAP's public documentation for each table): `pack_columns()`
lists what the pack names for a table, and tests/test_sap_sample.py fails when a standard table here carries a column
outside it. A column the pack does not name is not added: MAKT therefore has only its key (the pack names no text
column), and there is no material document table (MATDOC, MKPF/MSEG): the pack does not describe one (docs/SAP.md lists
it as not built). The goods receipts are the purchase order history EKBE, rows with VGABE '1', which the pack has.

Customer-specific tables. SAP reserves the names that start with Z or Y for its customers' own tables and ZZ for their
own fields (a public naming convention). The Z tables here, their names and their fields are invented for this sample
and the SAP pack knows none of them, so the engine reads them with its generic name rules only:

  sap_sd  ZSD_ORDER_EXT  MANDT + VBELN, the standard key fields of a sales order, and invented ZZ_ fields;
                         one row points at an order that does not exist (planted orphan);
          ZSD_KAM_ASSIGN only custom names: ZZ_KUNDE_NR holds KNA1 customer numbers, nothing in its name says so;
  sap_mm  ZMM_PO_CONF    MANDT + EBELN + EBELP, the supplier's confirmed date per purchase order item (ZZ_CONF_DATE),
                         which the late-delivery KPI compares with the goods receipt.

No ZZ_ append field is added to a standard table: the pack has no rule for appends, and a standard table here carries
only the pack's columns.

What is planted, at fixed places (tests/fixtures/sap_sample/planted.json lists each and the engine's measured answer):
  - VBAK.NETWR is the sum of the order's VBAP.NETWR: summed over a join with VBAP it counts once per item (the total
    that doubles); GOLD_VIEWS holds a view that does it wrong and the right one;
  - orphan items: VBAP rows of orders that do not exist, one EKPO row of a purchase order that does not exist;
  - an orphan in a Z table (ZSD_ORDER_EXT);
  - late goods receipts: every LATE_EVERY-th purchase order item is received after its confirmed date.
"""
from __future__ import annotations

import json
import random
import re
from datetime import date, timedelta
from decimal import Decimal

LABEL = "synthetic, SAP-shaped, not SAP data"
START, END = date(2024, 11, 1), date(2026, 10, 31)
CLIENT = "100"                                   # MANDT: one client
SAMPLES = ("sap_sd", "sap_mm")

# Spark DDL per table, in the order written. Standard tables: only the pack's names. Z tables: invented.
SCHEMAS: dict[str, dict[str, str]] = {
    "sap_sd": {
        "T001": "MANDT STRING, BUKRS STRING, KTOPL STRING, WAERS STRING",
        "KNA1": "MANDT STRING, KUNNR STRING, NAME1 STRING, STRAS STRING, PSTLZ STRING, ORT01 STRING, ERDAT DATE",
        "MARA": "MANDT STRING, MATNR STRING, ERSDA DATE, LAEDA DATE",
        "MAKT": "MANDT STRING, MATNR STRING, SPRAS STRING",
        "VBAK": "MANDT STRING, VBELN STRING, AUART STRING, ERDAT DATE, KUNNR STRING, NETWR DECIMAL(15,2), WAERK STRING",
        "VBAP": "MANDT STRING, VBELN STRING, POSNR STRING, MATNR STRING, KWMENG DECIMAL(13,3), VRKME STRING, NETWR DECIMAL(15,2), WAERK STRING, ERDAT DATE",
        "LIKP": "MANDT STRING, VBELN STRING, KUNNR STRING, KUNAG STRING, ERDAT DATE",
        "LIPS": "MANDT STRING, VBELN STRING, POSNR STRING, MATNR STRING, VGBEL STRING, VGPOS STRING, LFIMG DECIMAL(13,3), VRKME STRING, ERDAT DATE",
        "VBRK": "MANDT STRING, VBELN STRING, FKART STRING, BUKRS STRING, KUNAG STRING, KUNRG STRING, NETWR DECIMAL(15,2), MWSBK DECIMAL(15,2), WAERK STRING, ERDAT DATE",
        "VBRP": ("MANDT STRING, VBELN STRING, POSNR STRING, MATNR STRING, AUBEL STRING, AUPOS STRING, VGBEL STRING, VGPOS STRING, "
                 "FKIMG DECIMAL(13,3), VRKME STRING, NETWR DECIMAL(15,2), ERDAT DATE"),
        "ZSD_ORDER_EXT": "MANDT STRING, VBELN STRING, ZZ_REGION STRING, ZZ_CAMPAIGN STRING",
        "ZSD_KAM_ASSIGN": "ZZ_KUNDE_NR STRING, ZZ_KAM_NAME STRING, ZZ_SEGMENT STRING",
    },
    "sap_mm": {
        "T001": "MANDT STRING, BUKRS STRING, KTOPL STRING, WAERS STRING",
        "LFA1": "MANDT STRING, LIFNR STRING, NAME1 STRING, STRAS STRING, PSTLZ STRING, ORT01 STRING, ERDAT DATE",
        "MARA": "MANDT STRING, MATNR STRING, ERSDA DATE, LAEDA DATE",
        "MAKT": "MANDT STRING, MATNR STRING, SPRAS STRING",
        "EKKO": "MANDT STRING, EBELN STRING, BSART STRING, BUKRS STRING, LIFNR STRING, WAERS STRING, AEDAT DATE",
        "EKPO": "MANDT STRING, EBELN STRING, EBELP STRING, MATNR STRING, MENGE DECIMAL(13,3), MEINS STRING, NETWR DECIMAL(15,2), LOEKZ STRING, AEDAT DATE",
        "EKBE": ("MANDT STRING, EBELN STRING, EBELP STRING, ZEKKN STRING, VGABE STRING, GJAHR STRING, BELNR STRING, BUZEI STRING, "
                 "MENGE DECIMAL(13,3), WRBTR DECIMAL(15,2), WAERS STRING, CPUDT DATE"),
        "ZMM_PO_CONF": "MANDT STRING, EBELN STRING, EBELP STRING, ZZ_CONF_DATE DATE, ZZ_CONF_BY STRING",
    },
}
STANDARD = {s: [t for t in SCHEMAS[s] if not t.startswith(("Z", "Y"))] for s in SAMPLES}
Z_TABLES = {s: [t for t in SCHEMAS[s] if t.startswith(("Z", "Y"))] for s in SAMPLES}

# ---------------------------------------------------------------- the planted places (fixed) -------------------------
N_ORDERS = 300                     # sales orders over the two years
N_CUSTOMERS, N_MATERIALS, N_SUPPLIERS, N_POS = 120, 150, 40, 260
ORPHAN_ORDERS = ("0000019901", "0000019902", "0000019903")      # VBAP items of these orders exist; the orders do not
ORPHAN_Z_ORDER = "0000019950"      # ZSD_ORDER_EXT row for an order that does not exist
ORPHAN_PO = "4500099901"           # an EKPO item of a purchase order that does not exist
LATE_EVERY = 11                    # every 11th received purchase order item is received after its confirmed date
REGIONS = ("NORTH", "SOUTH", "EAST", "WEST")
CAMPAIGNS = ("SPRING24", "AUTUMN25", "WINTER25", "SPRING26", "NONE")
SEGMENTS = ("KEY ACCOUNT", "GROWTH", "STANDARD")
CITIES = ("Example City North", "Example City South", "Example City East", "Example City West")


def _kunnr(i: int) -> str:
    return f"{100000 + i:010d}"


def _lifnr(i: int) -> str:
    return f"{300000 + i:010d}"


def _matnr(i: int) -> str:
    return f"{200000 + i:018d}"


def _pos(n: int) -> str:
    return f"{n * 10:06d}"


def _dec(x: float, n: int = 2) -> float:
    return float(round(x, n))


def _day(rnd: random.Random, k: int, n: int) -> date:
    days = (END - START).days
    return START + timedelta(days=min(days, int(k * days / n) + rnd.randrange(0, 3)))


def _masters(rnd: random.Random):
    t001 = [(CLIENT, "1000", "EXCA", "EUR"), (CLIENT, "2000", "EXCA", "SEK")]
    mara = [(CLIENT, _matnr(i), START - timedelta(days=400 - i), START - timedelta(days=30 - (i % 20))) for i in range(1, N_MATERIALS + 1)]
    makt = [(CLIENT, _matnr(i), lang) for i in range(1, N_MATERIALS + 1) for lang in ("E", "D")]    # two languages: filter SPRAS
    price = {_matnr(i): _dec(rnd.uniform(8, 900)) for i in range(1, N_MATERIALS + 1)}
    return t001, mara, makt, price


def rows(sample: str, seed_value: int = 7) -> dict[str, list[tuple]]:
    """Every table of one sample ('sap_sd' or 'sap_mm') as tuples in SCHEMAS' column order. Deterministic."""
    if sample == "sap_sd":
        return _sd(seed_value)
    if sample == "sap_mm":
        return _mm(seed_value)
    raise ValueError(f"unknown sample {sample!r}: one of {', '.join(SAMPLES)}")


def _sd(seed_value: int) -> dict[str, list[tuple]]:
    rnd = random.Random(seed_value)
    t001, mara, makt, price = _masters(random.Random(1000 + seed_value * 0))       # master data fixed across seeds
    kna1 = [(CLIENT, _kunnr(i), f"Example Customer {i:04d}", f"Example Street {i}", f"{10000 + i * 7:05d}", CITIES[i % 4],
             START - timedelta(days=500 - i)) for i in range(1, N_CUSTOMERS + 1)]
    mats = [m[1] for m in mara]
    vbak, vbap, likp, lips, vbrk, vbrp, zext = [], [], [], [], [], [], []
    deliv_no, bill_no = 80010000, 90010000
    for n in range(1, N_ORDERS + 1):
        vbeln = f"{10000 + n:010d}"
        erdat = _day(rnd, n - 1, N_ORDERS)
        kunnr = _kunnr(rnd.randrange(1, N_CUSTOMERS + 1))
        items = []
        for p in range(1, rnd.choice([1, 2, 2, 3, 3, 4, 5]) + 1):
            m = rnd.choice(mats)
            qty = float(rnd.choice([1, 2, 5, 10, 20, 50]))
            items.append((CLIENT, vbeln, _pos(p), m, qty, "ST", _dec(qty * price[m]), "EUR", erdat))
        vbak.append((CLIENT, vbeln, "TA", erdat, kunnr, _dec(sum(i[6] for i in items)), "EUR"))   # the header holds the items' sum
        vbap += items
        zext.append((CLIENT, vbeln, REGIONS[rnd.randrange(4)], rnd.choice(CAMPAIGNS)))
        if erdat > END - timedelta(days=20):
            continue                                          # still open: no delivery, no invoice yet
        deliv_no += 1
        dv = f"{deliv_no:010d}"
        ddate = erdat + timedelta(days=rnd.choice([3, 5, 7, 10, 14]))
        likp.append((CLIENT, dv, kunnr, kunnr, ddate))
        for k, it in enumerate(items, start=1):
            lips.append((CLIENT, dv, _pos(k), it[3], vbeln, it[2], it[4], "ST", ddate))
        bill_no += 1
        bv = f"{bill_no:010d}"
        bdate = ddate + timedelta(days=rnd.choice([0, 1, 2]))
        net = _dec(sum(i[6] for i in items))
        vbrk.append((CLIENT, bv, "F2", "1000", kunnr, kunnr, net, _dec(net * 0.25), "EUR", bdate))
        for k, it in enumerate(items, start=1):
            vbrp.append((CLIENT, bv, _pos(k), it[3], vbeln, it[2], dv, _pos(k), it[4], "ST", it[6], bdate))
    for o in ORPHAN_ORDERS:                                   # planted: items of orders that do not exist
        m = mats[int(o[-1])]
        vbap.append((CLIENT, o, _pos(1), m, 1.0, "ST", price[m], "EUR", date(2026, 6, 1)))
    zext.append((CLIENT, ORPHAN_Z_ORDER, "NORTH", "NONE"))   # planted: a Z row for an order that does not exist
    kam = [(_kunnr(i), f"Example Account Manager {i % 9 + 1:02d}", SEGMENTS[i % 3]) for i in range(1, N_CUSTOMERS + 1) if i % 3 != 0]
    return {"T001": t001, "KNA1": kna1, "MARA": mara, "MAKT": makt, "VBAK": vbak, "VBAP": vbap, "LIKP": likp, "LIPS": lips,
            "VBRK": vbrk, "VBRP": vbrp, "ZSD_ORDER_EXT": zext, "ZSD_KAM_ASSIGN": kam}


def _mm(seed_value: int) -> dict[str, list[tuple]]:
    rnd = random.Random(seed_value + 1)
    t001, mara, makt, _price = _masters(random.Random(1000))
    price = {m: _dec(p * 0.6) for m, p in _price.items()}
    lfa1 = [(CLIENT, _lifnr(i), f"Example Supplier {i:04d}", f"Example Road {i}", f"{20000 + i * 11:05d}", CITIES[(i + 1) % 4],
             START - timedelta(days=600 - i)) for i in range(1, N_SUPPLIERS + 1)]
    mats = [m[1] for m in mara]
    ekko, ekpo, ekbe, conf = [], [], [], []
    received, belnr = 0, 5000000000
    for n in range(1, N_POS + 1):
        ebeln = f"{4500000000 + n:010d}"
        aedat = _day(rnd, n - 1, N_POS)
        lifnr = _lifnr(rnd.randrange(1, N_SUPPLIERS + 1))
        ekko.append((CLIENT, ebeln, "NB", "1000", lifnr, "EUR", aedat))
        for p in range(1, rnd.choice([1, 2, 2, 3, 4]) + 1):
            ebelp = f"{p * 10:05d}"
            m = rnd.choice(mats)
            qty = float(rnd.choice([10, 20, 50, 100, 200]))
            ekpo.append((CLIENT, ebeln, ebelp, m, qty, "ST", _dec(qty * price[m]), "", aedat))
            confirmed = aedat + timedelta(days=rnd.choice([7, 10, 14, 21, 28]))
            conf.append((CLIENT, ebeln, ebelp, confirmed, rnd.choice(["EDI", "MAIL", "PORTAL"])))
            if confirmed + timedelta(days=30) > END:
                continue                                      # not received yet
            received += 1
            late = received % LATE_EVERY == 0
            gr = confirmed + timedelta(days=rnd.choice([3, 6, 9, 15])) if late else confirmed - timedelta(days=rnd.choice([0, 0, 1, 2, 4]))
            belnr += 1
            ekbe.append((CLIENT, ebeln, ebelp, "00", "1", str(gr.year), f"{belnr:010d}", "0001", qty, _dec(qty * price[m]), "EUR", gr))
    m = mats[0]
    ekpo.append((CLIENT, ORPHAN_PO, "00010", m, 5.0, "ST", _dec(5 * price[m]), "", date(2026, 5, 4)))   # planted orphan item
    return {"T001": t001, "LFA1": lfa1, "MARA": mara, "MAKT": makt, "EKKO": ekko, "EKPO": ekpo, "EKBE": ekbe, "ZMM_PO_CONF": conf}


# A reference through a custom column name: nothing in the name says what it points at. The engine is not expected to
# find it; facts() records whether a name rule, R5 or suggest_relationships did.
CUSTOM_REFERENCES = {"sap_sd": [("ZSD_KAM_ASSIGN", "ZZ_KUNDE_NR", "KNA1.KUNNR")]}

# ---------------------------------------------------------------- gold views for the doubled-totals demo -------------
# The wrong one sums the header's NETWR after joining the items: each order counts once per item. The right one sums the
# items' own NETWR over the same join. T-SQL, as on a lakehouse's SQL endpoint; `{schema}` is the sample's schema.
GOLD_VIEWS = {
    "gold_revenue_by_customer_wrong": (
        "CREATE VIEW {schema}.gold_revenue_by_customer_wrong AS\n"
        "SELECT k.KUNNR, SUM(k.NETWR) AS order_value\n"
        "FROM {schema}.VBAK k\n"
        "JOIN {schema}.VBAP p ON p.MANDT = k.MANDT AND p.VBELN = k.VBELN\n"
        "GROUP BY k.KUNNR"),
    "gold_revenue_by_customer": (
        "CREATE VIEW {schema}.gold_revenue_by_customer AS\n"
        "SELECT k.KUNNR, SUM(p.NETWR) AS order_value\n"
        "FROM {schema}.VBAK k\n"
        "JOIN {schema}.VBAP p ON p.MANDT = k.MANDT AND p.VBELN = k.VBELN\n"
        "GROUP BY k.KUNNR"),
}


def gold_views(schema: str = "sap_sd") -> list[dict]:
    """The two gold views as rows of a view-definitions query (what sql_sums.check reads)."""
    return [{"VIEW_SCHEMA": schema, "VIEW_NAME": n, "VIEW_DEFINITION": sql.format(schema=schema)} for n, sql in GOLD_VIEWS.items()]


# ---------------------------------------------------------------- the pack's vocabulary -------------------------------

def pack_columns(table: str) -> set[str]:
    """Every column the SAP pack names for a standard table: its key and unique keys, its number, date, amount,
    quantity, currency, unit and personal columns, the columns of every pack relationship and filter on it, `TABLE.COL`
    anywhere in the pack, and a column a note of the table's own entry names in capitals. Empty for a table the pack
    does not describe (the Z tables)."""
    from . import sap_pack
    p = sap_pack.load("sap")
    t = p["tables"].get(table)
    if t is None:
        return set()
    out = set(t["key"]) | {c for u in t.get("unique_keys", []) for c in u}
    for f in ("number_columns", "delta", "currency_columns", "unit_columns"):
        out |= set(t.get(f, []))
    word = re.compile(r"[A-Z][A-Z0-9_]*")
    for a in t.get("amounts", []) + t.get("quantities", []):
        out.add(a["column"])
        for u in (a.get("currency"), a.get("unit")):
            if u and word.fullmatch(u):
                out.add(u)
    out |= {x["column"] for x in t.get("personal", [])}
    for r in p["relationships"]:
        if r["source"] == table:
            out |= set(r["source_cols"])
        if r["target"] == table:
            out |= set(r["target_cols"])
        for w in r.get("where", []):
            if (r["source"] if w["side"] == "source" else r["target"]) == table:
                out.add(w["column"])
    text = json.dumps(p, ensure_ascii=False)
    out |= set(re.findall(rf"\b{re.escape(table)}\.([A-Z][A-Z0-9_]+)\b", text))
    own = json.dumps({k: v for k, v in t.items() if k in ("note", "title", "key_note")}, ensure_ascii=False)
    for tr in p["traps"]:
        if re.search(rf"\b{re.escape(table)}\b", tr["text"]):
            own += " " + tr["text"]
    out |= {w for w in re.findall(r"\b([A-Z][A-Z0-9_]{3,9})\b", own) if w not in p["tables"]} & _documented_words(p)
    return out


def _documented_words(p: dict) -> set[str]:
    """Capitalised words the pack uses as column names somewhere (keys, number columns, relationship columns) or names in
    a note as a field (AUART, VBTYP, FKART, BSART, LOEKZ): what a note may add."""
    words = set()
    for t in p["tables"].values():
        words |= set(t["key"]) | set(t.get("number_columns", [])) | set(t.get("delta", []))
        notes = " ".join(str(t.get(k, "")) for k in ("note", "key_note"))
        words |= set(re.findall(r"\b([A-Z][A-Z0-9_]{3,9})\b", notes))
    for tr in p["traps"]:
        words |= set(re.findall(r"\b([A-Z][A-Z0-9_]{3,9})\b", tr["text"]))
    return words - set(p["tables"])


# ---------------------------------------------------------------- schema, source, seed -------------------------------

def _cols(sample: str, table: str) -> list[tuple[str, str]]:
    return [(c.split()[0], c.split(None, 1)[1]) for c in re.split(r", (?![^()]*\))", SCHEMAS[sample][table])]


def schema(sample: str):
    """The tables of one sample as a `Schema` (no data), for planning offline."""
    from .schema import Column, Schema, Table
    s = Schema(schema=sample)
    for table in SCHEMAS[sample]:
        s.tables[table] = Table(table, [Column(c, t.lower()) for c, t in _cols(sample, table)], schema=sample)
    return s


def source(sample: str = "sap_sd", seed_value: int = 7):
    """One sample's rows in an in-memory SQLite database, as a local Source (what /check and the tests read)."""
    import sqlite3
    from .platforms.local import Source, _sqlite_execute
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute(f"ATTACH DATABASE ':memory:' AS [{sample}]")
    for table, data in rows(sample, seed_value).items():
        cols = _cols(sample, table)
        # TEXT, not STRING: SQLite gives a STRING column numeric affinity and would drop the leading zeros of VBELN
        con.execute(f"CREATE TABLE [{sample}].[{table}] ({', '.join(f'[{c}] ' + ('TEXT' if t == 'STRING' else t) for c, t in cols)})")
        if data:
            data = [tuple(v.isoformat() if isinstance(v, date) else v for v in r) for r in data]
            con.executemany(f"INSERT INTO [{sample}].[{table}] VALUES ({','.join('?' * len(cols))})", data)
    what = "order to invoice" if sample == "sap_sd" else "purchase to pay"
    return Source("folder", f"SAP-shaped sample, {what} ({LABEL}; fabric_backend.sap_sample)", schema(sample),
                  _sqlite_execute(con), "sqlite",
                  [f"Synthetic rows from fabric_backend.sap_sample ({sample}): {LABEL}. Invented customers, suppliers and "
                   "materials; the table and column names follow the repository's SAP pack."], con.close)


def seed(spark, sample: str, schema_name: str | None = None, seed_value: int = 7) -> dict[str, int]:
    """Create (or replace) one sample's tables in a schema of the attached lakehouse (a lakehouse with schemas).
    Returns row counts. seed.seed(spark, sap=True) calls this for both samples after the shop."""
    target = schema_name or sample
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {target}")
    counts = {}
    for name, data in rows(sample, seed_value).items():
        cols = _cols(sample, name)
        dec = [t.upper().startswith("DECIMAL") for _c, t in cols]
        data = [tuple(Decimal(str(v)) if d and v is not None else v for v, d in zip(r, dec)) for r in data]
        df = spark.createDataFrame(data, SCHEMAS[sample][name])
        df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{target}.{name}")
        counts[name] = len(data)
    return counts


# ---------------------------------------------------------------- what the engine finds (measured, not typed) ---------
# The KPI queries of docs/SAMPLE-SAP.md, T-SQL that also runs in SQLite. The film scripts' numbers come from these and
# from facts(); tests/test_sap_sample.py checks the docs against both.
KPI_SQL = {
    "late_goods_receipts": (
        "SELECT COUNT(*) AS received_items,\n"
        "       SUM(CASE WHEN b.CPUDT > c.ZZ_CONF_DATE THEN 1 ELSE 0 END) AS late_items\n"
        "FROM {schema}.EKBE b\n"
        "JOIN {schema}.ZMM_PO_CONF c ON c.MANDT = b.MANDT AND c.EBELN = b.EBELN AND c.EBELP = b.EBELP\n"
        "WHERE b.VGABE = '1'"),
}


def facts(sample: str) -> dict:
    """What the engine finds on one sample, measured now: the plan (keys and links with their rules), validate_plan's
    counts, R5 and suggest_relationships (the row checks), amount_levels and, on sap_sd, sql_sums on the gold views.
    Z-table entries are split out. The sample's fixture and docs are compared with this; nothing here is typed by hand."""
    from . import browser_check, evidence, sql_sums
    from .infer import plan
    src = source(sample)
    try:
        names = plan(src.schema)
        p = plan(src.schema, execute=src.execute)
        v = evidence.validate(p, src.execute)
        z = set(Z_TABLES[sample])
        link = lambda x: {"source": x.source, "source_cols": list(x.source_cols), "target": x.target, "target_cols": list(x.target_cols), "rule": x.rule}
        orphans = {(o["source"], tuple(o["columns"]), o["target"]): o["orphans"] for o in v["relationships"]}
        out = {
            "sample": sample,
            "keys": {t: {"columns": list(k), "rule": r} for t, (k, r) in p.keys.items()},
            "keyless": list(p.keyless),
            "links": [link(x) for x in p.relationships],
            "r5": [link(x) for x in p.relationships if x.rule == "R5"],
            "r5_proposed": [{k: e[k] for k in ("source", "source_cols", "target", "reason") if k in e} for e in p.proposed],
            "same_without_rows": [link(x) for x in names.relationships] == [link(x) for x in p.relationships],
            "summary": v["summary"],
            "orphans": [{"source": s_, "columns": list(c), "target": t, "orphans": n} for (s_, c, t), n in orphans.items() if n],
            "amount_levels": sorted({(f["header"], f["line"]) for f in v["amount_levels"]["findings"]}),
            "pack_tables": sorted(set((p.pack or {}).get("tables", {}).values())),
        }
        linked = {(x["source"], c) for x in out["links"] for c in x["source_cols"]}
        from . import graphs
        cands = graphs.suggest(p, src.execute, check=15)["candidates"]
        out["not_found"] = [{"source": t, "column": c, "points_at": tgt, "by_name": (t, c) in linked,
                             "by_rows": any(x["source"] == t and x["source_cols"] == [c] for x in cands)}
                            for t, c, tgt in CUSTOM_REFERENCES.get(sample, [])]
        out["z"] = {
            "keys": {t: out["keys"].get(t) for t in sorted(z)},
            "links": [dict(x, orphans=orphans.get((x["source"], tuple(x["source_cols"]), x["target"]))) for x in out["links"]
                      if x["source"] in z or x["target"] in z],
        }
    finally:
        src.close()
    checked = browser_check.analyze(sample)
    out["check"] = {"headline": checked["verdict"]["headline"]["title"],
                    "findings": sorted([f["severity"], f["check"], f["title"]] for f in checked["findings"]),
                    "suggestions": sorted(f["title"] for f in checked["suggestions"])}
    out["amount_levels"] = [list(x) for x in out["amount_levels"]]
    ex = next((f["amount"] for f in checked["findings"] if f["check"] == "amount_level" and f.get("amount")
               and (f["amount"]["header"], f["amount"]["line"]) == ("VBAK", "VBAP")), None)
    if ex and sample == "sap_sd":
        out["doubled"] = {k: ex[k] for k in ("header", "line", "column", "wrong", "right", "example")}
    if sample == "sap_sd":
        g = sql_sums.check(plan(schema(sample)), gold_views(sample))
        out["gold_views"] = {"flagged": [f["view"] for f in g["flagged"]], "not_flagged": list(g["read_not_flagged"])}
    if sample == "sap_mm":
        src = source(sample)
        try:
            (row,) = src.execute(KPI_SQL["late_goods_receipts"].format(schema=sample))
        finally:
            src.close()
        out["late"] = {"received_items": int(row["received_items"]), "late_items": int(row["late_items"]),
                       "on_time_percent": round(100 * (row["received_items"] - row["late_items"]) / row["received_items"], 1)}
    return out


if __name__ == "__main__":                                  # python -m fabric_backend.sap_sample: the measured facts as JSON
    print(json.dumps({s: facts(s) for s in SAMPLES}, indent=1, ensure_ascii=False))
