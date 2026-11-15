"""A synthetic sample shaped like released SAP CDS views, not SAP data (round n230).

    %pip install git+https://github.com/Krusmaster/fabric-backend
    from fabric_backend.seed import seed
    seed(spark, schema="sap_cds")          # fourteen small tables: I_SalesDocument, I_SalesDocumentItem, ...

What it is. The small order-to-cash story of fabric_backend/sap_demo.py (the `sap_` tables of the dbo sample), told in
the shape a released CDS view of SAP S/4HANA has: the view's name as the table name (`I_SalesDocument`), the view's
field names in camelCase (`SalesDocument`, `SoldToParty`, `TotalNetAmount`), and no client column, because a CDS view's
field list does not carry one. Every value is made up: customers "Demo Customer 10", materials numbered from 1. No row
comes from an SAP system, an SAP customer or SAP's own demo data. The view and field names are the ones the pack
modules `packs/sap/cds_*.json` name, each with its public source; tests/test_n230_sap_cds.py fails when a table here
carries a column outside them.

A run on these rows shows that the engine reads CDS-shaped tables, never that the pack is right about SAP: the rows
are written from the pack (sap-verify refuses to record such a run).

What is planted, and EXPECTED says what each check should find:
- order 0000000001 has three items, so I_SalesDocument.TotalNetAmount summed over its I_SalesDocumentItem rows counts
  three times: 1 900 over the join against 700 summed once per order (the total that doubles);
- the invoice 0090000001 has two items, so I_BillingDocument.TotalNetAmount doubles over them the same way (800, 400);
- an item of an order that does not exist (I_SalesDocumentItem 0000000009/000010): an orphan the check must report;
- a payer that differs from the sold-to party, a ship-to party on the delivery;
- the invoice's posting in the universal journal in two ledgers (0L and 2L): the ledger is part of the key of
  I_JournalEntryItem, and a sum over both ledgers counts the posting twice.

    tables()        -> {name: (columns, types, rows)}
    schema(name)    -> the tables as a Schema (no data), for planning offline
    source(name)    -> the rows in an in-memory SQLite database, as a local Source (what the tests read)
    seed(spark, s)  -> the tables as Delta tables in schema s of the attached lakehouse; seed.seed(spark, schema="sap_cds")
    facts()         -> what the engine finds on the sample, measured now (the numbers in docs/SAP-CDS.md)
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

LABEL = "synthetic, shaped like SAP CDS views, not SAP data"
SCHEMA = "sap_cds"
_D, _Q = "DECIMAL(15,2)", "DECIMAL(13,3)"
ORPHAN_ORDER = "0000000009"                      # an item of this order exists; the order does not


def _t(spec: str, rows: list[tuple]) -> tuple[list[str], list[str], list[tuple]]:
    """'Name TYPE, Name TYPE' -> (columns, Spark types, rows)."""
    parts = [c.strip().split(None, 1) for c in spec.split(";")]
    return [c for c, _ in parts], [t for _, t in parts], rows


def tables() -> dict[str, tuple[list[str], list[str], list[tuple]]]:
    m1, m2, m3 = "000000000000000001", "000000000000000002", "000000000000000003"
    c10, c11, c12 = "0000000010", "0000000011", "0000000012"
    o1, o2, dv, bv = "0000000001", "0000000002", "0080000001", "0090000001"
    d = date
    journal = []
    for ledger in ("0L", "2L"):                                           # the same posting once per ledger
        journal += [
            (ledger, "1000", "2026", bv, "000001", ledger, "0012100000", c12, d(2026, 10, 11), 480.00, "EUR", 480.00, "EUR"),
            (ledger, "1000", "2026", bv, "000002", ledger, "0041000000", "", d(2026, 10, 11), -400.00, "EUR", -400.00, "EUR"),
            (ledger, "1000", "2026", bv, "000003", ledger, "0022000000", "", d(2026, 10, 11), -80.00, "EUR", -80.00, "EUR")]
    return {
        "I_CompanyCode": _t("CompanyCode STRING; CompanyCodeName STRING; Currency STRING; ChartOfAccounts STRING; Country STRING",
                            [("1000", "Demo Company Code", "EUR", "DEMO", "DE")]),
        "I_SalesOrganization": _t("SalesOrganization STRING; CompanyCode STRING; SalesOrganizationCurrency STRING", [("1000", "1000", "EUR")]),
        "I_Customer": _t("Customer STRING; CustomerName STRING; StreetName STRING; PostalCode STRING; CityName STRING; Country STRING", [
            (c10, "Demo Customer 10", "Demo Street 1", "11111", "Demo City", "DE"),
            (c11, "Demo Customer 11", "Demo Street 2", "11112", "Demo City", "DE"),
            (c12, "Demo Customer 12", "Demo Street 3", "11113", "Demo City", "DE")]),
        "I_Product": _t("Product STRING; ProductType STRING; BaseUnit STRING; CreationDate DATE",
                        [(m1, "FERT", "ST", d(2025, 1, 10)), (m2, "FERT", "ST", d(2025, 1, 10)), (m3, "HAWA", "ST", d(2025, 2, 1))]),
        "I_ProductText": _t("Product STRING; Language STRING; ProductName STRING",
                            [(m, lang, f"Demo material {m[-1]} ({lang})") for m in (m1, m2, m3) for lang in ("E", "D")]),
        "I_SalesDocument": _t("SalesDocument STRING; SalesDocumentType STRING; SDDocumentCategory STRING; SoldToParty STRING; "
                              f"SalesOrganization STRING; TotalNetAmount {_D}; TransactionCurrency STRING; CreationDate DATE; LastChangeDate DATE", [
            (o1, "TA", "C", c10, "1000", 600.00, "EUR", d(2026, 10, 1), d(2026, 10, 2)),
            (o2, "TA", "C", c11, "1000", 100.00, "EUR", d(2026, 10, 3), d(2026, 10, 3))]),
        "I_SalesDocumentItem": _t(f"SalesDocument STRING; SalesDocumentItem STRING; Material STRING; Product STRING; OrderQuantity {_Q}; OrderQuantityUnit STRING; "
                                  f"NetAmount {_D}; TransactionCurrency STRING; CreationDate DATE", [
            (o1, "000010", m1, m1, 3.0, "ST", 300.00, "EUR", d(2026, 10, 1)),
            (o1, "000020", m2, m2, 2.0, "ST", 200.00, "EUR", d(2026, 10, 1)),
            (o1, "000030", m3, m3, 1.0, "ST", 100.00, "EUR", d(2026, 10, 1)),
            (o2, "000010", m1, m1, 1.0, "ST", 100.00, "EUR", d(2026, 10, 3)),
            (ORPHAN_ORDER, "000010", m2, m2, 1.0, "ST", 40.00, "EUR", d(2026, 10, 4))]),            # planted: no such order
        "I_SalesDocumentScheduleLine": _t(f"SalesDocument STRING; SalesDocumentItem STRING; ScheduleLine STRING; DeliveryDate DATE; "
                                          f"ScheduleLineOrderQuantity {_Q}; OrderQuantityUnit STRING", [
            (o1, "000010", "0001", d(2026, 10, 10), 2.0, "ST"), (o1, "000010", "0002", d(2026, 10, 20), 1.0, "ST"),
            (o1, "000020", "0001", d(2026, 10, 10), 2.0, "ST"), (o1, "000030", "0001", d(2026, 10, 10), 1.0, "ST"),
            (o2, "000010", "0001", d(2026, 10, 12), 1.0, "ST")]),
        "I_DeliveryDocument": _t("DeliveryDocument STRING; DeliveryDocumentType STRING; ShipToParty STRING; SoldToParty STRING; "
                                 "SalesOrganization STRING; CreationDate DATE", [(dv, "LF", c11, c10, "1000", d(2026, 10, 10))]),
        "I_DeliveryDocumentItem": _t("DeliveryDocument STRING; DeliveryDocumentItem STRING; Material STRING; Product STRING; ReferenceSDDocument STRING; "
                                     f"ReferenceSDDocumentItem STRING; ActualDeliveryQuantity {_Q}; DeliveryQuantityUnit STRING", [
            (dv, "000010", m1, m1, o1, "000010", 2.0, "ST"), (dv, "000020", m2, m2, o1, "000020", 2.0, "ST")]),
        "I_BillingDocument": _t("BillingDocument STRING; BillingDocumentType STRING; SoldToParty STRING; PayerParty STRING; SalesOrganization STRING; "
                                f"CompanyCode STRING; FiscalYear STRING; AccountingDocument STRING; TotalNetAmount {_D}; TotalTaxAmount {_D}; "
                                "TransactionCurrency STRING; BillingDocumentDate DATE", [
            (bv, "F2", c10, c12, "1000", "1000", "2026", bv, 400.00, 80.00, "EUR", d(2026, 10, 11))]),
        "I_BillingDocumentItem": _t("BillingDocument STRING; BillingDocumentItem STRING; Material STRING; Product STRING; SalesDocument STRING; SalesDocumentItem STRING; "
                                    f"ReferenceSDDocument STRING; ReferenceSDDocumentItem STRING; BillingQuantity {_Q}; BillingQuantityUnit STRING; "
                                    f"NetAmount {_D}; TaxAmount {_D}; TransactionCurrency STRING", [
            (bv, "000010", m1, m1, o1, "000010", dv, "000010", 2.0, "ST", 200.00, 40.00, "EUR"),
            (bv, "000020", m2, m2, o1, "000020", dv, "000020", 2.0, "ST", 200.00, 40.00, "EUR")]),
        "I_JournalEntry": _t("CompanyCode STRING; FiscalYear STRING; AccountingDocument STRING; AccountingDocumentType STRING; PostingDate DATE; "
                             "TransactionCurrency STRING", [("1000", "2026", bv, "RV", d(2026, 10, 11), "EUR")]),
        "I_JournalEntryItem": _t("SourceLedger STRING; CompanyCode STRING; FiscalYear STRING; AccountingDocument STRING; LedgerGLLineItem STRING; "
                                 f"Ledger STRING; GLAccount STRING; Customer STRING; PostingDate DATE; AmountInTransactionCurrency {_D}; "
                                 f"TransactionCurrency STRING; AmountInCompanyCodeCurrency {_D}; CompanyCodeCurrency STRING", journal),
    }


# What the checks should find on these rows; tests/test_n230_sap_cds.py compares the engine's answer with this.
EXPECTED = {
    "tables": 14,
    "orphan": ("I_SalesDocumentItem", "I_SalesDocument", 1),              # the planted item of order 0000000009
    "header_amounts": [("I_SalesDocument", "I_SalesDocumentItem", "TotalNetAmount", 1900.0, 700.0),
                       ("I_BillingDocument", "I_BillingDocumentItem", "TotalNetAmount", 800.0, 400.0)],
}


def ddl(name: str) -> str:
    cols, types, _rows = tables()[name]
    return ", ".join(f"{c} {t}" for c, t in zip(cols, types))


def schema(name: str = SCHEMA, style: str = "view"):
    """The sample's tables as a Schema (no data). style: 'view' (I_SalesDocument, SalesDocument: as the view writes
    them), 'plain' (SalesDocument: without the I_ prefix), 'lower' (i_salesdocument, salesdocument), 'snake'
    (i_sales_document, sales_document) or 'upper' (I_SALESDOCUMENT, SALESDOCUMENT): the renames a landing makes."""
    from .schema import Column, Schema, Table
    s = Schema(schema=name)
    for table, (cols, types, _rows) in tables().items():
        t = rename(table, style)
        s.tables[t] = Table(t, [Column(rename(c, style, column=True), k.lower()) for c, k in zip(cols, types)], schema=name)
    return s


def rename(name: str, style: str, column: bool = False) -> str:
    import re
    if style == "view":
        return name
    if style == "plain":
        return name if column else name[2:]
    if style == "lower":
        return name.lower()
    if style == "upper":
        return name.upper()
    if style == "snake":                                                  # SDDocumentCategory -> sd_document_category
        return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", name).lower().replace("__", "_")
    raise ValueError(f"unknown style {style!r}")


def source(name: str = SCHEMA, style: str = "view"):
    """The sample's rows in an in-memory SQLite database, as a local Source."""
    import sqlite3
    from .platforms.local import Source, _sqlite_execute
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute(f"ATTACH DATABASE ':memory:' AS [{name}]")
    for table, (cols, types, rows) in tables().items():
        # TEXT, not STRING: SQLite gives a STRING column numeric affinity and would drop the leading zeros
        defs = ", ".join(f"[{rename(c, style, column=True)}] {'TEXT' if t == 'STRING' else t}" for c, t in zip(cols, types))
        con.execute(f"CREATE TABLE [{name}].[{rename(table, style)}] ({defs})")
        data = [tuple(v.isoformat() if isinstance(v, date) else v for v in r) for r in rows]
        con.executemany(f"INSERT INTO [{name}].[{rename(table, style)}] VALUES ({','.join('?' * len(cols))})", data)
    return Source("folder", f"Sample shaped like SAP CDS views ({LABEL}; fabric_backend.sap_cds_demo)", schema(name, style),
                  _sqlite_execute(con), "sqlite",
                  [f"Synthetic rows from fabric_backend.sap_cds_demo: {LABEL}. Invented customers and materials; the view and "
                   "field names follow the repository's SAP pack (packs/sap/cds_*.json)."], con.close)


def seed(spark, schema_name: str | None = SCHEMA) -> dict[str, int]:
    """Create (or replace) the sample's tables in a schema of the attached lakehouse; schema_name None writes them to
    the default schema (a lakehouse without schemas). Returns row counts. seed.seed(spark, schema="sap_cds") calls this."""
    if schema_name:
        spark.sql(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
    counts = {}
    for name, (cols, types, rows) in tables().items():
        dec = [t.upper().startswith("DECIMAL") for t in types]
        data = [tuple(Decimal(str(v)) if is_dec and v is not None else v for v, is_dec in zip(r, dec)) for r in rows]
        df = spark.createDataFrame(data, ", ".join(f"{c} {t}" for c, t in zip(cols, types)))
        df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{schema_name}.{name}" if schema_name else name)
        counts[name] = len(data)
    return counts


def _sums(src, f: dict) -> dict:
    """The first amount of a header-amount finding summed over the join with its lines (wrong) and on the header (right)."""
    h, l, col = f["header"], f["line"], f["amount_columns"][0]
    on = " AND ".join(f"l.[{a}] = h.[{b}]" for a, b in zip(f["line_columns"], f["header_columns"]))
    s = src.schema.schema
    (w,) = src.execute(f"SELECT SUM(h.[{col}]) AS x FROM [{s}].[{h}] h JOIN [{s}].[{l}] l ON {on}")
    (r,) = src.execute(f"SELECT SUM([{col}]) AS x FROM [{s}].[{h}]")
    return {"over_the_join": float(w["x"]), "on_the_header": float(r["x"])}


def facts(style: str = "view") -> dict:
    """What the engine finds on the sample, measured now: the plan (keys and links with their rules), validate_plan's
    counts, the orphans and the header amounts a join repeats. docs/SAP-CDS.md and the test are compared with this."""
    from . import evidence
    from .infer import plan
    src = source(style=style)
    try:
        p = plan(src.schema, execute=src.execute)
        v = evidence.validate(p, src.execute, max_items=200)
        keys = [k for k in v["keys"]]
        rels = v["relationships"]
        return {
            "tables": len(src.schema.tables),
            "pack": (p.pack or {}).get("pack"),
            "pack_tables": len((p.pack or {}).get("tables", {})),
            "keys": {t: {"columns": list(k), "rule": r} for t, (k, r) in p.keys.items()},
            "keyless": list(p.keyless),
            "links": [{"source": x.source, "source_cols": list(x.source_cols), "target": x.target, "target_cols": list(x.target_cols),
                       "rule": x.rule} for x in p.relationships],
            "keys_checked": len(keys), "keys_unique": sum(1 for k in keys if str(k.get("verdict", "")).startswith("unique")),
            "links_checked": len(rels), "links_held": sum(1 for r in rels if not r.get("orphans")),
            "orphans": [{"source": r["source"], "columns": list(r["columns"]), "target": r["target"], "orphans": r["orphans"]}
                        for r in rels if r.get("orphans")],
            "header_amounts": [{"header": f["header"], "line": f["line"], "columns": list(f["amount_columns"]),
                                "max_lines": f["rows_per_header"]["max_lines"], **_sums(src, f)}
                               for f in v["amount_levels"]["findings"]],
            "summary": v["summary"],
        }
    finally:
        src.close()


if __name__ == "__main__":                                  # python -m fabric_backend.sap_cds_demo: the measured facts as JSON
    print(json.dumps(facts(), indent=1, ensure_ascii=False))
