"""AP2 (18 Nov 2026): the 36-month synthetic SAP demo generator (fabric_backend/sap_demo36.py)."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from fabric_backend import notebook, sap_demo, sap_demo36

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sap_demo36"


def test_same_tables_and_columns_as_the_small_demo():
    small, big = sap_demo.tables(), sap_demo36.tables()
    assert list(big) == list(small) and len(big) == 17
    for name in small:
        assert big[name][0] == small[name][0], name
        assert big[name][1] == small[name][1], name


def test_deterministic():
    a, b = sap_demo36.tables(), sap_demo36.tables()
    assert json.dumps(a, default=str) == json.dumps(b, default=str)
    assert json.dumps(sap_demo36.tables(seed=7), default=str) != json.dumps(a, default=str)


def test_sizes_periods_and_skew():
    t = sap_demo36.tables()
    assert len(t["KNA1"][2]) == 300 and len(t["MARA"][2]) == 500
    months = {r[10][:6] for r in t["VBRK"][2]}
    assert len(months) == 36 and min(months) == "202311" and max(months) == "202610"
    assert 3000 < len(t["VBAK"][2]) < 6000 and 8000 < len(t["VBAP"][2]) < 20000
    revenue: dict[str, float] = {}
    for r in t["VBRP"][2]:
        revenue[r[3]] = revenue.get(r[3], 0) + float(r[8])
    top = sorted(revenue.values(), reverse=True)
    assert sum(top[:50]) / sum(top) > 0.5                     # 10 % of the materials carry more than half the revenue
    by_month: dict[str, float] = {}
    for r in t["VBRK"][2]:
        by_month[r[10][:6]] = by_month.get(r[10][:6], 0) + float(r[7])
    assert by_month["202511"] > by_month["202505"]           # the season: November above May
    assert by_month["202610"] > by_month["202410"]           # the trend


def test_names_and_addresses_are_obviously_fake():
    t = sap_demo36.tables()
    assert all(re.fullmatch(r"Demo Customer \d{4}", r[2]) for r in t["KNA1"][2])
    assert all(r[5].endswith(".example.com") for r in t["ADR6"][2])
    assert all(r[7].startswith("+00 000 ") for r in t["KNA1"][2])


def test_the_planted_issues_are_where_the_doc_says():
    p = sap_demo36.planted()
    assert p["orphan"]["VBELN"] == "0000099999"
    headers = {r[1] for r in sap_demo36.tables()["VBAK"][2]}
    assert "0000099999" not in headers
    assert len(p["doubled_amount"]["VBELN"]) == 1
    assert p["nulls"] == {"VBRP.MATNR": 3, "KNA1.ORT01": 2, "VBAK.KNUMV": 1}
    assert p["blank_partners"]["VBPA.KUNNR"] > 0 and p["blank_partners"]["VBPA.PARNR"] > 0


def test_validate_plan_finds_the_orphan_and_no_blank_partner_orphans():
    """validate_plan's own relationship statements (evidence.relationship_sql, as args_of builds them for SAP pack links);
    the whole validate run is left out here: its correlated checks of the extended links take minutes in SQLite."""
    from fabric_backend import evidence, sap_pack
    _, execute = sap_demo36.sqlite()

    def orphans(source, cols, target):
        sql = evidence.relationship_sql("sap", source, cols, target, cols, blank_is_none=True,
                                        initial=sap_pack.initial_columns(source, cols, target) or None)
        return execute(sql)[0]["orphans"]
    assert orphans("sap_vbap", ["MANDT", "VBELN"], "sap_vbak") == 1
    assert orphans("sap_vbpa", ["MANDT", "KUNNR"], "sap_kna1") == 0
    assert orphans("sap_vbpa", ["MANDT", "PARNR"], "sap_knvk") == 0


def test_the_csv_sample_in_the_repository_is_what_the_generator_writes(tmp_path):
    sap_demo36.sample(tmp_path)
    for f in sorted(tmp_path.glob("*.csv")):
        assert (SAMPLE / f.name).read_text(encoding="utf-8") == f.read_text(encoding="utf-8"), f.name
    total = sum(f.stat().st_size for f in SAMPLE.glob("*.csv"))
    assert total < 200_000                                    # a sample, not the data
    with (SAMPLE / "KNA1.csv").open(encoding="utf-8") as fh:
        assert len(list(csv.reader(fh))) == sap_demo36.SAMPLE_CUSTOMERS + 1


def test_the_notebook_is_a_dry_run_by_default_and_writes_only_its_schema():
    text = sap_demo36.notebook_source()
    cells = notebook.parse(text)
    params = next(c for k, c in cells if k == "parameters")
    assert "DRY_RUN = True" in params and 'TARGET_SCHEMA = "sap_demo36"' in params
    for kind, code in cells:
        if kind != "markdown":
            compile(code, "sap_demo36", "exec")
    assert sap_demo36.GENERATOR in text
    assert '"dbo", "sap_silver", "sap_gold"' in text and "krusgraph.demo" in text
    nb = json.loads(json.dumps(sap_demo36.notebook_ipynb()))
    assert nb["nbformat"] == 4 and any(c["metadata"].get("tags") == ["parameters"] for c in nb["cells"])
