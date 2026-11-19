"""AP2 (18 Nov 2026): SAP's blank partner field is no reference, not an orphan.

Found in the live demo run of sap_lt1_pipeline (schema sap_silver): the silver notebook quarantined 5 rows of sap_vbpa
because KUNNR or PARNR was blank ('') and so found no row in sap_kna1 / sap_knvk. In SAP a blank partner field means
"not applicable for this partner function". validate_plan already counted a blank as no value for SAP pack links; the
silver notebook, its in-memory simulation and the pipeline's check notebook now do the same, and a value of zeros only
counts as none too where the SAP pack marks the relationship "optional". The real orphan stays caught: the item of order
0000000009, which has no header in sap_vbak, is still quarantined.
"""
from __future__ import annotations

import sqlite3

from fabric_backend import evidence, pipeline, sap_demo, sap_pack, silver
from fabric_backend.infer import plan
from fabric_backend.schema import Schema

INFO = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="demo_lh", item_kind="Lakehouse",
            schema="sap", schemas_enabled=True)
VBAP_ORPHAN = "MANDT, VBELN has no row in sap_vbak (sap_vbap.MANDT = sap_vbak.MANDT and sap_vbap.VBELN = sap_vbak.VBELN)"


def _tables(extra_vbpa: list[tuple] = ()) -> dict:
    t = sap_demo.tables()
    cols, kinds, rows = t["VBPA"]
    t["VBPA"] = (cols, kinds, list(rows) + list(extra_vbpa))
    return t


def _sqlite(tables: dict, schema: str = "sap"):
    """The demo rows in SQLite (as sap_demo.sqlite, with rows added): (Schema, execute, connection)."""
    con = sqlite3.connect(":memory:")
    con.execute(f"ATTACH DATABASE ':memory:' AS {schema}")
    info = []
    for name, (cols, kinds, rows) in tables.items():
        t = "sap_" + name.lower()
        con.execute(f"CREATE TABLE {schema}.[{t}] ({', '.join(f'[{c}]' for c in cols)})")
        con.executemany(f"INSERT INTO {schema}.[{t}] VALUES ({','.join('?' * len(cols))})", rows)
        info += [(schema, t, c, "decimal" if k != "string" else "nvarchar", i) for i, (c, k) in enumerate(zip(cols, kinds), 1)]

    def execute(sql: str):
        from fabric_backend.dialects import sqlite_sql
        cur = con.execute(sqlite_sql(sql))
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]
    return Schema.from_information_schema(info, schema=schema), execute, con


def _rows(tables: dict) -> dict[str, list[dict]]:
    return {"sap_" + n.lower(): [dict(zip(cols, r)) for r in rows] for n, (cols, kinds, rows) in tables.items()}


def test_the_pack_marks_the_optional_partner_fields():
    assert sap_pack.initial_columns("sap_vbpa", ["MANDT", "KUNNR"], "sap_kna1") == ["KUNNR"]
    assert sap_pack.initial_columns("VBPA", ["MANDT", "PARNR"], "KNVK") == ["PARNR"]
    assert sap_pack.initial_columns("VBPA", ["MANDT", "ADRNR"], "ADRC") == ["ADRNR"]
    assert sap_pack.initial_columns("KNVK", ["MANDT", "LIFNR"], "LFA1") == ["LIFNR"]
    # a header-item link is not optional: an item's order number of zeros is a value that must find its order
    assert sap_pack.initial_columns("sap_vbap", ["MANDT", "VBELN"], "sap_vbak") == []
    assert sap_pack.blank_columns(["MANDT", "KUNNR"]) == ["KUNNR"]


def test_silver_keeps_blank_partners_and_still_quarantines_the_real_orphan():
    tables = _tables()
    s = silver.spec(plan(_sqlite(tables)[0]), INFO, silver_schema="sap_silver")
    out = silver.simulate(s, _rows(tables))
    reasons = [(q["source_table"], q["reason"]) for q in out["quarantine"]]
    assert reasons == [("sap_vbap", VBAP_ORPHAN)]
    assert out["quarantine"][0]["row"]["VBELN"] == "0000000009"
    assert len(out["silver"]["sap_vbpa"]) == len(tables["VBPA"][2]) == 5          # every partner row stays
    text = "\n".join(code for _, code in silver.cells(s))
    assert 'blank=["KUNNR"], initial=["KUNNR"])' in text and 'blank=["PARNR"], initial=["PARNR"])' in text
    assert 'blank=["VBELN"])' in text and "def has_reference(columns, blank=(), initial=()):" in text


def test_silver_quarantines_a_partner_that_is_set_but_unknown_and_keeps_zeros():
    extra = [("100", "0000000002", "000000", "AG", "0000000000", "", ""),           # zeros only: SAP's initial value
             ("100", "0000000002", "000000", "WE", "   ", "", ""),                  # spaces: blank
             ("100", "0000000002", "000000", "RG", None, None, None),               # NULL
             ("100", "0000000002", "000000", "ZZ", "0000000099", "", "")]           # set, and no such customer: an orphan
    tables = _tables(extra)
    s = silver.spec(plan(_sqlite(tables)[0]), INFO, silver_schema="sap_silver")
    out = silver.simulate(s, _rows(tables))
    vbpa = [q for q in out["quarantine"] if q["source_table"] == "sap_vbpa"]
    assert [q["row"]["KUNNR"] for q in vbpa] == ["0000000099"]
    assert "KUNNR has no row in sap_kna1" in vbpa[0]["reason"]
    assert [q["row"]["VBELN"] for q in out["quarantine"] if q["source_table"] == "sap_vbap"] == ["0000000009"]


def test_validate_plan_counts_blank_and_initial_partners_as_no_reference():
    extra = [("100", "0000000002", "000000", "AG", "0000000000", "", ""),
             ("100", "0000000002", "000000", "ZZ", "0000000099", "", "")]
    sch, execute, _ = _sqlite(_tables(extra))
    p = plan(sch)
    out = evidence.validate(p, execute, max_items=200)
    rels = {(r["source"], tuple(r["columns"]), r["target"]): r for r in out["relationships"]}
    kunnr = rels[("sap_vbpa", ("MANDT", "KUNNR"), "sap_kna1")]
    assert (kunnr["rows_with_value"], kunnr["orphans"]) == (5, 1), kunnr          # 4 set in the demo + the unknown one
    parnr = rels[("sap_vbpa", ("MANDT", "PARNR"), "sap_knvk")]
    assert (parnr["rows_with_value"], parnr["orphans"]) == (1, 0), parnr
    vbap = rels[("sap_vbap", ("MANDT", "VBELN"), "sap_vbak")]
    assert vbap["orphans"] == 1


def test_the_relationship_sql_leaves_out_zeros_only_where_asked():
    plain = evidence.relationship_sql("sap", "sap_vbpa", ["MANDT", "KUNNR"], "sap_kna1", ["MANDT", "KUNNR"], blank_is_none=True)
    marked = evidence.relationship_sql("sap", "sap_vbpa", ["MANDT", "KUNNR"], "sap_kna1", ["MANDT", "KUNNR"], blank_is_none=True,
                                       initial=["KUNNR"])
    assert "REPLACE" not in plain and "REPLACE(LTRIM(RTRIM(s.[KUNNR])), '0', '') <> ''" in marked


def test_the_pipeline_check_counts_like_validate_plan():
    extra = [("100", "0000000002", "000000", "AG", "0000000000", "", ""),
             ("100", "0000000002", "000000", "ZZ", "0000000099", "", "")]
    tables = _tables(extra)
    sch, _, con = _sqlite(tables)
    p = plan(sch)
    s = silver.spec(p, INFO, silver_schema="sap_silver")
    rels = [r for r in pipeline.check_spec(p, s, {"gold_schema": "gold", "views": []})["relationships"] if r["source"] == "sap_vbpa"]
    by = {tuple(r["columns"]): r for r in rels}
    assert by[("MANDT", "KUNNR")]["blank"] == ["KUNNR"] and by[("MANDT", "KUNNR")]["initial"] == ["KUNNR"]

    def execute(sql):
        cur = con.execute(sql)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]
    kunnr = pipeline._CHECK["check_reference"](execute, "sap", by[("MANDT", "KUNNR")])
    assert (kunnr["rows"], kunnr["orphans"]) == (5, 1), kunnr
    parnr = pipeline._CHECK["check_reference"](execute, "sap", by[("MANDT", "PARNR")])
    assert (parnr["rows"], parnr["orphans"], parnr["holds"]) == (1, 0, True)
    # without the rule (a relationship that is not the SAP pack's), a blank is a value, as before
    vbap = next(r for r in pipeline.check_spec(p, s, {"gold_schema": "gold", "views": []})["relationships"]
                if r["source"] == "sap_vbap" and r["columns"] == ["MANDT", "VBELN"])
    assert pipeline._CHECK["check_reference"](execute, "sap", vbap)["orphans"] == 1
