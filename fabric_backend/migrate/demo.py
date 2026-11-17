"""Synthetic rows for the synthetic Snowflake export in tests/fixtures/mg1/snowflake/ (round MG1), not customer data.

    python -m fabric_backend.migrate.demo        # the measured facts as JSON (the numbers in docs/MIGRATE-DATABRICKS-SNOWFLAKE.md)

Two in-memory SQLite databases stand in for the two sides: "source" holds the rows as the Snowflake schema SALES would,
"landed" holds them as a Fabric SQL analytics endpoint would after mirroring. Nothing connects to Snowflake or Fabric.

What is planted, and EXPECTED says what each check should find:
- customer C2 twice (the declared PRIMARY KEY is not enforced): the key is not unique, on both sides;
- order O4 for a customer C3 that does not exist, and a line of an order O9 that does not exist: one orphan per link;
- on the landed side the line (O2, 1) is missing (a lost row): ORDER_LINES has 5 rows instead of 6, and its LINE_AMOUNT
  and QUANTITY totals differ by that row;
- EVENTS is a transient table: the plan says mirroring does not take it, and it is not on the landed side.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

LABEL = "synthetic rows for a synthetic Snowflake export, not customer data"
SCHEMA = "SALES"
EXPORT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "mg1" / "snowflake"

_TABLES = {
    "CUSTOMERS": (["CUSTOMER_ID", "NAME", "COUNTRY"], ["TEXT", "TEXT", "TEXT"],
                  [("C1", "Demo Customer 1", "SE"), ("C2", "Demo Customer 2", "FI"), ("C2", "Demo Customer 2 (again)", "FI")]),
    "ORDERS": (["ORDER_ID", "CUSTOMER_ID", "ORDER_DATE", "TOTAL_AMOUNT"], ["TEXT", "TEXT", "TEXT", "NUMERIC"],
               [("O1", "C1", "2026-10-01", 1000.00), ("O2", "C2", "2026-10-02", 300.00), ("O3", "C1", "2026-10-03", 500.00),
                ("O4", "C3", "2026-10-04", 200.00)]),
    "ORDER_LINES": (["ORDER_ID", "LINE_NO", "PRODUCT_ID", "QUANTITY", "LINE_AMOUNT"], ["TEXT", "INTEGER", "TEXT", "INTEGER", "NUMERIC"],
                    [("O1", 1, "P1", 2, 600.00), ("O1", 2, "P2", 1, 400.00), ("O2", 1, "P1", 1, 300.00), ("O3", 1, "P3", 5, 500.00),
                     ("O4", 1, "P1", 2, 200.00), ("O9", 1, "P1", 1, 100.00)]),
    "PRODUCTS": (["PRODUCT_ID", "NAME", "ATTRIBUTES"], ["TEXT", "TEXT", "TEXT"],
                 [("P1", "Pump", '{"color": "red"}'), ("P2", "Valve", '{"color": "blue"}'), ("P3", "Service hour", "{}")]),
    "EVENTS": (["EVENT_ID", "PAYLOAD", "CREATED_AT"], ["TEXT", "TEXT", "TEXT"],
               [("E1", '{"click": 1}', "2026-10-01T08:00:00+02:00"), ("E2", '{"click": 2}', "2026-10-01T09:00:00+02:00")]),
}
LOST = ("ORDER_LINES", ("O2", 1))       # the row the landing lost
NOT_LANDED = ("EVENTS",)

EXPECTED = {
    "tables_before": 5, "tables_after": 4, "declared_keys": 4, "declared_links": 3,
    "differences": 4,
    "rows": {"ORDER_LINES": (6, 5)}, "totals": {"ORDER_LINES.LINE_AMOUNT": (2100, 1800), "ORDER_LINES.QUANTITY": (12, 11)},
    "not_unique": ["CUSTOMERS"], "orphans": {"orders(customer_id)->customers": 1, "order_lines(order_id)->orders": 1},
}


def _db(landed: bool):
    from ..platforms.local import _sqlite_execute
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute(f"ATTACH DATABASE ':memory:' AS [{SCHEMA}]")
    for t, (cols, types, rows) in _TABLES.items():
        if landed and t in NOT_LANDED:
            continue
        con.execute(f"CREATE TABLE [{SCHEMA}].[{t}] ({', '.join(f'[{c}] {ty}' for c, ty in zip(cols, types))})")
        keep = [r for r in rows if not (landed and t == LOST[0] and (r[0], r[1]) == LOST[1])]
        con.executemany(f"INSERT INTO [{SCHEMA}].[{t}] VALUES ({','.join('?' * len(cols))})", keep)
    return con, _sqlite_execute(con)


def landed_schema():
    from ..schema import Schema
    rows = [(SCHEMA, t, c, ty.lower() if ty != "TEXT" else "varchar", i + 1) for t, (cols, types, _) in _TABLES.items()
            if t not in NOT_LANDED for i, (c, ty) in enumerate(zip(cols, types))]
    return Schema.from_information_schema(rows, schema=SCHEMA)


def run() -> dict:
    """plan_migration on the synthetic export with both sides counted on SQLite."""
    from . import compare, plan_migration
    src_con, src = _db(False)
    fab_con, fab = _db(True)
    try:
        dry = plan_migration(EXPORT, "snowflake", "SALES", fabric_schema=landed_schema())
        before = compare.run(src, compare.counting_sql(dry["spec"], "sqlite", SCHEMA))
        return plan_migration(EXPORT, "snowflake", "SALES", fabric_schema=landed_schema(), before=before, fabric_execute=fab,
                              fabric_dialect="sqlite")
    finally:
        src_con.close()
        fab_con.close()


def facts() -> dict:
    out = run()
    r, cmp = out["report"], out["report"]["comparison"]
    rows = {t["table"].upper(): (int(t["rows_before"]), None if t["rows_after"] is None else int(t["rows_after"])) for t in cmp["tables"]}
    return {
        "label": LABEL,
        "tables_before": sum(1 for t in cmp["tables"] if t["rows_before"] is not None),
        "tables_after": sum(1 for t in cmp["tables"] if t["rows_after"] is not None),
        "declared_keys": len(r["model"]["keys"]), "declared_links": len(r["model"]["links"]),
        "landing": {o["object"]: o["landing"]["how"] for o in r["objects"]},
        "views": {v["view"]: v["status"] for v in r["views"]},
        "verdict": cmp["verdict"], "differences": cmp["differences"], "rows": rows,
        "totals": {f"{t['table'].upper()}.{s['column'].upper()}": (s["before"], s["after"]) for t in cmp["tables"] for s in t.get("totals", [])},
        "not_unique": sorted(t["table"].upper() for t in cmp["tables"] if "key" in t and not t["key_unique_after"]),
        "orphans": {x["link"]: int(x["orphans_after"]) for x in cmp["links"] if x["orphans_after"]},
        "fabric_checks": r["fabric_checks"]["summary"],
        "report_markdown": r["report_markdown"],
    }


if __name__ == "__main__":
    print(json.dumps(facts(), indent=1, ensure_ascii=False, default=str))
