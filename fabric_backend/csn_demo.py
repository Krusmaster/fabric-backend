"""A synthetic sample described by a synthetic CSN file, not SAP data (round CDS2).

    python -m fabric_backend.csn_demo          # the measured facts as JSON (the numbers in docs/SAP-CSN.md)

The CSN is tests/fixtures/csn/synthetic_service_orders.json (hand-written for the tests: custom views named ZI_*, with
keys, associations with cardinality, @Semantics amounts, a quantity, text elements, @Analytics.dataCategory). The rows
here are made up and land the way a replication into OneLake might write them, so the name mapping is tested too:
table names in lower case with a layer prefix (`dsp_zi_serviceorder`), column names in upper case (`SERVICEORDER`),
and the three change columns a Datasphere replication flow appends (`__operation_type`, `__sequence_number`,
`__timestamp`). No row, name or figure comes from an SAP system.

What is planted, and EXPECTED says what each check should find:
- service order SO1 has two items, so ZI_ServiceOrder.TotalNetAmount summed over its items counts twice: 2 800 over
  the join against 1 800 on the orders (the total that doubles; the CSN marks it @Semantics.amount);
- an item of an order that does not exist (SO9/000010): an orphan the declared association does not prevent;
- customer C2 twice, once as inserted and once as updated, as an unmerged landing would hold it: the CSN declares
  Customer the key, the rows say it is not unique. Metadata is not proof.
"""
from __future__ import annotations

import json
from pathlib import Path

LABEL = "synthetic rows described by a synthetic CSN file, not SAP data"
SCHEMA = "csn_demo"
CSN_FILE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "csn" / "synthetic_service_orders.json"
PREFIX = "dsp_"
CDC = ("__operation_type", "__sequence_number", "__timestamp")

_T = "2026-11-16T08:00:00"
# table (as the CSN names it) -> (columns, SQL types, rows); the CDC columns are added by tables()
_TABLES = {
    "ZI_ServiceOrder": (["ServiceOrder", "ServiceOrderDescription", "Customer", "Status", "TotalNetAmount", "TransactionCurrency", "CreationDate"],
                        ["TEXT", "TEXT", "TEXT", "TEXT", "DECIMAL(15,2)", "TEXT", "TEXT"],
                        [("SO1", "Pump overhaul", "C1", "OP", 1000.00, "EUR", "2026-10-01"),
                         ("SO2", "Valve check", "C2", "CL", 300.00, "EUR", "2026-10-02"),
                         ("SO3", "Annual service", "C1", "OP", 500.00, "SEK", "2026-10-03")]),
    "ZI_ServiceOrderItem": (["ServiceOrder", "ServiceOrderItem", "Product", "Quantity", "QuantityUnit", "NetAmount", "TransactionCurrency"],
                            ["TEXT", "TEXT", "TEXT", "DECIMAL(13,3)", "TEXT", "DECIMAL(15,2)", "TEXT"],
                            [("SO1", "000010", "P1", 2, "PC", 600.00, "EUR"),
                             ("SO1", "000020", "P2", 1, "PC", 400.00, "EUR"),
                             ("SO2", "000010", "P1", 1, "PC", 300.00, "EUR"),
                             ("SO3", "000010", "P3", 5, "H", 500.00, "SEK"),
                             ("SO9", "000010", "P1", 1, "PC", 100.00, "EUR")]),
    "ZI_Customer": (["Customer", "CustomerName", "Country"], ["TEXT", "TEXT", "TEXT"],
                    [("C1", "Demo Customer 1", "SE"), ("C2", "Demo Customer 2", "FI"), ("C2", "Demo Customer 2 (renamed)", "FI")]),
    "ZI_Product": (["Product", "ProductGroup"], ["TEXT", "TEXT"], [("P1", "PUMPS"), ("P2", "VALVES"), ("P3", "SERVICE")]),
    "ZI_ProductText": (["Product", "Language", "ProductName"], ["TEXT", "TEXT", "TEXT"],
                       [("P1", "E", "Pump"), ("P1", "D", "Pumpe"), ("P2", "E", "Valve"), ("P3", "E", "Service hour")]),
}
_UPDATED = {("ZI_Customer", 2)}                  # the row index that is an update of an earlier row (C2 renamed)

EXPECTED = {
    "tables": 5, "csn_keys": 5, "csn_links": 4, "keys_unique": 4, "not_unique": "dsp_zi_customer",
    "orphans": [("dsp_zi_serviceorderitem", "dsp_zi_serviceorder", 1)],
    "header_amounts": [("dsp_zi_serviceorder", "dsp_zi_serviceorderitem", "TOTALNETAMOUNT", 2800.0, 1800.0)],
}


def landed(name: str, column: bool = False) -> str:
    """The name as this sample lands it: tables lower case with the prefix, columns upper case."""
    return name.upper() if column else f"{PREFIX}{name.lower()}"


def tables() -> dict[str, tuple[list[str], list[str], list[tuple]]]:
    out = {}
    for name, (cols, types, rows) in _TABLES.items():
        data = []
        for i, r in enumerate(rows):
            op = "U" if (name, i) in _UPDATED else "I"
            data.append(tuple(r) + (op, i + 1, _T))
        out[landed(name)] = ([landed(c, True) for c in cols] + list(CDC), types + ["TEXT", "INTEGER", "TEXT"], data)
    return out


def schema(name: str = SCHEMA):
    from .schema import Schema
    return Schema.from_information_schema([(name, t, c, ty.split("(")[0].lower() if ty != "TEXT" else "varchar", i + 1)
                                           for t, (cols, types, _) in tables().items() for i, (c, ty) in enumerate(zip(cols, types))],
                                          schema=name)


def source(name: str = SCHEMA):
    """The sample's rows in an in-memory SQLite database, as a local Source."""
    import sqlite3
    from .platforms.local import Source, _sqlite_execute
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute(f"ATTACH DATABASE ':memory:' AS [{name}]")
    for table, (cols, types, rows) in tables().items():
        con.execute(f"CREATE TABLE [{name}].[{table}] ({', '.join(f'[{c}] {t}' for c, t in zip(cols, types))})")
        con.executemany(f"INSERT INTO [{name}].[{table}] VALUES ({','.join('?' * len(cols))})", rows)
    return Source("folder", f"Sample described by a CSN file ({LABEL}; fabric_backend.csn_demo)", schema(name),
                  _sqlite_execute(con), "sqlite", [f"Synthetic rows from fabric_backend.csn_demo: {LABEL}."], con.close)


def facts() -> dict:
    """What the engine finds on the sample with the CSN file, measured now: the CSN's keys and links with their rule,
    validate_plan's counts, the orphans, the keys that are not unique, and the header amounts a join repeats."""
    from . import csn, evidence
    src = source()
    try:
        model = csn.read(CSN_FILE)
        p, report = csn.plan(src.schema, model)
        v = evidence.validate(p, src.execute, max_items=200)
        keys, rels = v["keys"], v["relationships"]
        sch = src.schema.schema

        def sums(f):
            h, l, col = f["header"], f["line"], f["amount_columns"][0]
            on = " AND ".join(f"l.[{a}] = h.[{b}]" for a, b in zip(f["line_columns"], f["header_columns"]))
            (w,) = src.execute(f"SELECT SUM(h.[{col}]) AS x FROM [{sch}].[{h}] h JOIN [{sch}].[{l}] l ON {on}")
            (r,) = src.execute(f"SELECT SUM([{col}]) AS x FROM [{sch}].[{h}]")
            return {"over_the_join": float(w["x"]), "on_the_header": float(r["x"])}
        return {
            "label": LABEL, "csn_file": CSN_FILE.name,
            "tables": len(src.schema.tables),
            "matched": report["matched"],
            "keys": {t: {"columns": list(k), "rule": r} for t, (k, r) in p.keys.items()},
            "links": [{"source": x.source, "source_cols": list(x.source_cols), "target": x.target, "target_cols": list(x.target_cols),
                       "rule": x.rule} for x in p.relationships],
            "csn_keys": sum(1 for _, r in p.keys.values() if r == csn.RULE),
            "csn_links": sum(1 for x in p.relationships if x.rule == csn.RULE),
            "not_applied": [{"association": x["association"], "why": x["why"]} for x in report["not_applied"]],
            "csn_amounts": [{k: a[k] for k in ("table", "column", "kind", "level", "currency" if a["kind"] == "amount" else "unit")}
                            for a in report["amounts"]],
            "cdc_columns": report["cdc_columns"],
            "keys_checked": len(keys), "keys_unique": sum(1 for k in keys if str(k.get("verdict", "")).startswith("unique")),
            "not_unique": sorted(k["table"] for k in keys if not str(k.get("verdict", "")).startswith("unique")),
            "links_checked": len(rels), "links_held": sum(1 for r in rels if not r.get("orphans")),
            "orphans": [{"source": r["source"], "columns": list(r["columns"]), "target": r["target"], "orphans": r["orphans"]}
                        for r in rels if r.get("orphans")],
            "header_amounts": [{"header": f["header"], "line": f["line"], "columns": list(f["amount_columns"]),
                                "max_lines": f["rows_per_header"]["max_lines"], **sums(f)} for f in v["amount_levels"]["findings"]],
            "summary": v["summary"],
        }
    finally:
        src.close()


if __name__ == "__main__":
    print(json.dumps(facts(), indent=1, ensure_ascii=False, default=str))
