"""Synthetic SAP-shaped tables with rows, for running the SAP pack's checks end to end (round n32).

Every value is made up: customers "Demo Customer 10", e-mail addresses at example.invalid, materials numbered from 1.
Nothing comes from an SAP system or an installation. The tables follow the pack's keys and relationships, so a run on
them shows that the tools work on SAP-shaped data in Fabric, never that the pack is right about SAP: the rows are
written from the pack. A `verified` entry from such a run would prove nothing and must not be written (sap-verify
refuses a `where` that names this demo).

The traps are planted, and EXPECTED says what each check should find:
- two clients: client 200 has an order numbered like one in client 100, and the same customer number;
- order 0000000001 has three items, so VBAK.NETWR summed over VBAP rows comes out three times too large;
- an item of an order that does not exist (VBAP 0000000009): an orphan the check must report;
- a payer that differs from the sold-to party, a ship-to on the delivery, a document address in VBPA;
- the document flow from the order to its delivery (J) and its invoice (M);
- an address with an international version (NATION I) and one with an expired period: one row each is valid today;
- two e-mail addresses for one address, a contact person: personal data the pack names.

    tables()                -> {name: (columns, types, rows)}
    write_csv(folder)       -> one CSV per table, the types in _types.json, and load_sap_demo.py, a PySpark notebook
                               that loads them into a lakehouse as Delta tables (sap_vbak, ...): run it in Fabric yourself
    sqlite()                -> (Schema, execute) over the same rows in SQLite, as the tests and a local run use
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

PREFIX = "sap_"
DEMO_WHERE = "synthetic SAP demo"          # what a run on these tables is; sap-verify refuses to record it
_D = "decimal(15,2)"
FOREVER, START = "99991231", "00010101"


def _t(cols: list[str], rows: list[tuple], decimals: tuple[str, ...] = ()) -> tuple[list[str], list[str], list[tuple]]:
    return cols, [_D if c in decimals else "string" for c in cols], rows


def tables() -> dict[str, tuple[list[str], list[str], list[tuple]]]:
    m1, m2, m3 = "000000000000000001", "000000000000000002", "000000000000000003"
    return {
        "T001": _t(["MANDT", "BUKRS", "KTOPL", "WAERS", "ADRNR"], [("100", "1000", "DEMO", "EUR", "0000000101"),
                                                                ("200", "1000", "DEMO", "EUR", "")]),
        "TVKO": _t(["MANDT", "VKORG", "BUKRS", "WAERS"], [("100", "1000", "1000", "EUR"), ("200", "1000", "1000", "EUR")]),
        "KNA1": _t(["MANDT", "KUNNR", "NAME1", "STRAS", "PSTLZ", "ORT01", "LAND1", "TELF1", "ADRNR"], [
            ("100", "0000000010", "Demo Customer 10", "Demo Street 1", "11111", "Demo City", "DE", "+00 000 0010", "0000000201"),
            ("100", "0000000011", "Demo Customer 11", "Demo Street 2", "11112", "Demo City", "DE", "+00 000 0011", "0000000202"),
            ("100", "0000000012", "Demo Customer 12", "Demo Street 3", "11113", "Demo City", "DE", "+00 000 0012", "0000000203"),
            ("200", "0000000010", "Other Client Customer 10", "Other Street 1", "22221", "Other City", "DE", "", "")]),
        "MARA": _t(["MANDT", "MATNR", "MTART", "MEINS"], [("100", m1, "FERT", "ST"), ("100", m2, "FERT", "ST"), ("100", m3, "HAWA", "ST"),
                                                         ("200", m1, "FERT", "ST")]),
        "MAKT": _t(["MANDT", "MATNR", "SPRAS", "MAKTX"], [("100", m, l, f"Demo material {m[-1]} ({l})") for m in (m1, m2, m3) for l in ("E", "D")]),
        "VBAK": _t(["MANDT", "VBELN", "AUART", "VBTYP", "KUNNR", "VKORG", "NETWR", "WAERK", "ERDAT", "AEDAT", "KNUMV"], [
            ("100", "0000000001", "TA", "C", "0000000010", "1000", 600.00, "EUR", "20261001", "20261002", "0000000501"),
            ("100", "0000000002", "TA", "C", "0000000011", "1000", 100.00, "EUR", "20261003", "20261003", "0000000502"),
            ("200", "0000000001", "TA", "C", "0000000010", "1000", 50.00, "EUR", "20261001", "20261001", "0000000501")], ("NETWR",)),
        "VBAP": _t(["MANDT", "VBELN", "POSNR", "MATNR", "NETWR", "WAERK", "KWMENG", "VRKME", "ERDAT"], [
            ("100", "0000000001", "000010", m1, 300.00, "EUR", 3, "ST", "20261001"),
            ("100", "0000000001", "000020", m2, 200.00, "EUR", 2, "ST", "20261001"),
            ("100", "0000000001", "000030", m3, 100.00, "EUR", 1, "ST", "20261001"),
            ("100", "0000000002", "000010", m1, 100.00, "EUR", 1, "ST", "20261003"),
            ("100", "0000000009", "000010", m2, 40.00, "EUR", 1, "ST", "20261004"),       # planted: no such order
            ("200", "0000000001", "000010", m1, 50.00, "EUR", 1, "ST", "20261001")], ("NETWR", "KWMENG")),
        "VBEP": _t(["MANDT", "VBELN", "POSNR", "ETENR", "EDATU", "WMENG", "VRKME"], [
            ("100", "0000000001", "000010", "0001", "20261010", 2, "ST"), ("100", "0000000001", "000010", "0002", "20261020", 1, "ST"),
            ("100", "0000000001", "000020", "0001", "20261010", 2, "ST"), ("100", "0000000001", "000030", "0001", "20261010", 1, "ST"),
            ("100", "0000000002", "000010", "0001", "20261012", 1, "ST")], ("WMENG",)),
        "LIKP": _t(["MANDT", "VBELN", "LFART", "KUNNR", "KUNAG", "VKORG", "ERDAT"], [
            ("100", "0080000001", "LF", "0000000011", "0000000010", "1000", "20261010")]),
        "LIPS": _t(["MANDT", "VBELN", "POSNR", "MATNR", "VGBEL", "VGPOS", "LFIMG", "VRKME"], [
            ("100", "0080000001", "000010", m1, "0000000001", "000010", 2, "ST"),
            ("100", "0080000001", "000020", m2, "0000000001", "000020", 2, "ST")], ("LFIMG",)),
        "VBRK": _t(["MANDT", "VBELN", "FKART", "KUNAG", "KUNRG", "VKORG", "BUKRS", "NETWR", "MWSBK", "WAERK", "FKDAT", "KNUMV"], [
            ("100", "0090000001", "F2", "0000000010", "0000000012", "1000", "1000", 400.00, 80.00, "EUR", "20261011", "0000000601")], ("NETWR", "MWSBK")),
        "VBRP": _t(["MANDT", "VBELN", "POSNR", "MATNR", "AUBEL", "AUPOS", "VGBEL", "VGPOS", "NETWR", "FKIMG", "VRKME"], [
            ("100", "0090000001", "000010", m1, "0000000001", "000010", "0080000001", "000010", 200.00, 2, "ST"),
            ("100", "0090000001", "000020", m2, "0000000001", "000020", "0080000001", "000020", 200.00, 2, "ST")], ("NETWR", "FKIMG")),
        "VBFA": _t(["MANDT", "VBELV", "POSNV", "VBELN", "POSNN", "VBTYP_N", "VBTYP_V", "RFMNG"], [
            ("100", "0000000001", "000010", "0080000001", "000010", "J", "C", 2), ("100", "0000000001", "000020", "0080000001", "000020", "J", "C", 2),
            ("100", "0000000001", "000010", "0090000001", "000010", "M", "C", 2), ("100", "0000000001", "000020", "0090000001", "000020", "M", "C", 2)],
            ("RFMNG",)),
        "VBPA": _t(["MANDT", "VBELN", "POSNR", "PARVW", "KUNNR", "PARNR", "ADRNR"], [
            ("100", "0000000001", "000000", "AG", "0000000010", "", ""),
            ("100", "0000000001", "000000", "WE", "0000000011", "", "0000000901"),           # a ship-to address typed into the order
            ("100", "0000000001", "000000", "RG", "0000000012", "", ""),
            ("100", "0000000001", "000000", "AP", "", "0000000701", ""),                     # a contact person
            ("100", "0080000001", "000000", "WE", "0000000011", "", "")]),                   # a partner row of the delivery
        "KNVK": _t(["MANDT", "PARNR", "KUNNR", "LIFNR", "NAMEV", "NAME1", "TELF1", "PAFKT"], [
            ("100", "0000000701", "0000000010", "", "Demo", "Contact", "+00 000 0701", "01")]),
        "ADRC": _t(["CLIENT", "ADDRNUMBER", "DATE_FROM", "NATION", "DATE_TO", "NAME1", "STREET", "POST_CODE1", "CITY1", "COUNTRY"], [
            ("100", "0000000101", START, "", FOREVER, "Demo Company Code", "Demo Street 100", "11100", "Demo City", "DE"),
            ("100", "0000000201", START, "", FOREVER, "Demo Customer 10", "Demo Street 1", "11111", "Demo City", "DE"),
            ("100", "0000000201", START, "I", FOREVER, "DEMO CUSTOMER 10", "DEMO STREET 1", "11111", "DEMO CITY", "DE"),   # international version
            ("100", "0000000202", START, "", "20251231", "Demo Customer 11", "Old Street 2", "11112", "Demo City", "DE"),   # expired
            ("100", "0000000202", "20260101", "", FOREVER, "Demo Customer 11", "Demo Street 2", "11112", "Demo City", "DE"),
            ("100", "0000000203", START, "", FOREVER, "Demo Customer 12", "Demo Street 3", "11113", "Demo City", "DE"),
            ("100", "0000000901", START, "", FOREVER, "Demo Ship-to", "Dock 9", "11119", "Demo Harbour", "DE")]),
        "ADR6": _t(["CLIENT", "ADDRNUMBER", "PERSNUMBER", "DATE_FROM", "CONSNUMBER", "SMTP_ADDR", "FLGDEFAULT"], [
            ("100", "0000000201", "", START, "001", "orders@customer10.example.invalid", "X"),
            ("100", "0000000201", "", START, "002", "invoices@customer10.example.invalid", "")]),
    }


# What the checks should find on these rows. The tests run validate_plan, amount_levels, the privacy rules and
# sap-verify on them in SQLite and compare with this; docs/LIVE-TEST-SAP.md asks for the same on Fabric.
EXPECTED = {
    "tables": 17,
    "review": {("VBAP", "VBAK"): "the planted item of order 0000000009"},
    "no_evidence": [("VBFA", "VBAK")],                    # no flow row whose subsequent document is a sales document
    "verified_at_least": [("VBAP", "MARA"), ("VBRP", "VBRK"), ("LIPS", "VBAP"), ("VBRK", "KNA1"), ("VBFA", "LIPS"), ("VBFA", "VBRP"),
                          ("KNA1", "ADRC"), ("VBPA", "ADRC")],
    "header_amount": ("VBAK", "VBAP", "NETWR"),
    "masked": [("ADR6", "SMTP_ADDR"), ("KNA1", "TELF1"), ("KNVK", "NAMEV")],
}


def write_csv(folder: str | Path, prefix: str = PREFIX) -> list[Path]:
    """One CSV per table (header row; text as text, so leading zeros stay), _types.json with each column's type, and
    load_sap_demo.py, the PySpark cells that load them. Upload the folder to the lakehouse's Files/sap_demo and run
    the notebook there; nothing here connects to Fabric."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written, types = [], {}
    for name, (cols, kinds, rows) in tables().items():
        path = folder / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        written.append(path)
        types[name] = dict(zip(cols, kinds))
    (folder / "_types.json").write_text(json.dumps(types, indent=2) + "\n", encoding="utf-8")
    (folder / "load_sap_demo.py").write_text(notebook(prefix), encoding="utf-8")
    return written + [folder / "_types.json", folder / "load_sap_demo.py"]


def notebook(prefix: str = PREFIX) -> str:
    """PySpark for a Fabric notebook attached to the lakehouse that holds the CSVs under Files/sap_demo."""
    return f'''# Synthetic SAP demo tables for Krusgraph (fabric_backend/sap_demo.py). Every value is made up.
# Attach this notebook to the lakehouse, upload the CSV files and _types.json to Files/sap_demo, then run.
# Tables are written as {prefix}<name> (sap_vbak, ...) in the default schema; existing tables of that name are replaced.
import json
from pyspark.sql import functions as F

base = "Files/sap_demo"
types = json.loads("".join(r.value for r in spark.read.text(f"{{base}}/_types.json").collect()))
for name, cols in types.items():
    df = spark.read.option("header", True).option("inferSchema", False).csv(f"{{base}}/{{name}}.csv")
    for c, t in cols.items():
        if t != "string":
            df = df.withColumn(c, F.col(c).cast(t))
    df.write.mode("overwrite").format("delta").saveAsTable("{prefix}" + name.lower())
    print(name, df.count(), "rows")
'''


def sqlite(prefix: str = PREFIX, schema: str = "sap"):
    """(Schema, execute) over the demo rows in an in-memory SQLite database, the way the tests and a local run use them."""
    import sqlite3

    from .dialects import sqlite_sql
    from .schema import Schema
    con = sqlite3.connect(":memory:")
    con.execute(f"ATTACH DATABASE ':memory:' AS {schema}")
    info = []
    for name, (cols, kinds, rows) in tables().items():
        t = prefix + name.lower()
        con.execute(f"CREATE TABLE {schema}.[{t}] ({', '.join(f'[{c}]' for c in cols)})")
        con.executemany(f"INSERT INTO {schema}.[{t}] VALUES ({','.join('?' * len(cols))})", rows)
        info += [(schema, t, c, "decimal" if k != "string" else "nvarchar", i) for i, (c, k) in enumerate(zip(cols, kinds), 1)]

    def execute(sql: str):
        cur = con.execute(sqlite_sql(sql))
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]
    return Schema.from_information_schema(info, schema=schema), execute
