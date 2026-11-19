"""WB1 (F8 in docs/WORKLOAD-TEST-2026-11-17.md): a gold view keeps exactly one row per silver row on the SAP path.

SAP writes "no partner" as its initial value, a blank (and for an optional field, zeros only). Silver has kept such rows
since AP2 (silver.has_reference); the gold view's join rule treated the blank as a reference that found no row and dropped
the row, so sap_gold.sap_vbpa had none of the demo's five partner rows. The Spark run of the same path, on PySpark 3.5 and
4.0, is tests/test_spark_notebooks.py::test_wb1_sap_gold_keeps_one_row_per_silver_row_in_pyspark."""
from __future__ import annotations

from fabric_backend import gold, sap_demo
from fabric_backend.infer import plan

INFO = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="demo_lh", item_kind="Lakehouse",
            schema="sap")


def _views():
    schema, execute = sap_demo.sqlite()
    g = gold.spec(plan(schema), INFO, silver_schema="sap_silver", gold_schema="sap_gold")
    return {v["fact"]: v for v in g["views"]}, execute


def test_a_blank_partner_is_no_reference_in_the_gold_rule():
    views, _ = _views()
    vbpa = gold.select_sql(views["sap_vbpa"], "sap_silver")
    assert "TRIM(f.`KUNNR`) = ''" in vbpa and "TRIM(f.`PARNR`) = ''" in vbpa
    assert "TRIM(f.`MANDT`)" not in vbpa                       # the client is never blank (sap_pack._BLANK_EXEMPT)
    for v in views.values():                                    # the CHECK text of the MLV says the same
        assert all(fl["check"] == gold.filter_sql(fl) for fl in v["filters"])


def test_every_sap_gold_view_keeps_the_rows_of_its_fact_table():
    """The silver notebook's steps on the demo rows (silver.simulate) into an in-memory sap_silver, then the views'
    SELECTs over it: each keeps every row of its fact table, partner rows with a blank KUNNR or PARNR among them."""
    import sqlite3

    from fabric_backend import silver
    from fabric_backend.dialects import sqlite_sql
    schema, _ = sap_demo.sqlite()
    p = plan(schema)
    data = {"sap_" + name.lower(): [dict(zip(cols, r)) for r in rows] for name, (cols, _k, rows) in sap_demo.tables().items()}
    out = silver.simulate(silver.spec(p, INFO, silver_schema="sap_silver"), data)["silver"]
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS sap_silver")
    for t, rows in out.items():
        cols = list(data[t][0])
        con.execute(f"CREATE TABLE sap_silver.[{t}] ({', '.join(f'[{c}]' for c in cols)})")
        con.executemany(f"INSERT INTO sap_silver.[{t}] VALUES ({','.join('?' * len(cols))})", [[r[c] for c in cols] for r in rows])
    g = gold.spec(p, INFO, silver_schema="sap_silver", gold_schema="sap_gold")
    views = {v["fact"]: v for v in g["views"]}
    assert {"sap_vbrp", "sap_lips", "sap_vbap", "sap_vbpa", "sap_vbrk"} <= set(views)
    for fact, v in views.items():
        got = con.execute(sqlite_sql(f"SELECT COUNT(*) FROM ({gold.select_sql(v, 'sap_silver')}) AS v")).fetchone()[0]
        assert got == len(out[fact]) > 0, fact
