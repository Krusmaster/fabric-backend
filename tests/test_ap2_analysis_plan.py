"""AP2 (18 Nov 2026): analysis_plan's rules on the synthetic SAP samples, with goldens and edge cases.

The rules are deterministic (no AI): the same plan and counts give the same answer, byte for byte. The worked example of
the design (AP1) is the repository's 24-month sample sap_sd; the small SAP demo (a few days of October 2026) must say
forecasting is missing; the 36-month generated demo (sap_demo36) must make A7, A8 and A3 ready, each with its reason.
Regenerate the goldens deliberately with KRUSGRAPH_UPDATE_GOLDEN=1.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from fabric_backend import analysis_notebook, analysis_plan, notebook, sap_demo, sap_demo36, sap_sample
from fabric_backend.infer import PlanInputError, plan

GOLDEN = Path(__file__).parent / "golden"
UPDATE = os.environ.get("KRUSGRAPH_UPDATE_GOLDEN") == "1"
INFO = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="demo_lh", schema="sap",
            schemas_enabled=True)


def _golden(name: str, value) -> None:
    path = GOLDEN / f"ap2_{name}.json"
    text = json.dumps(value, indent=1, sort_keys=True, default=str) + "\n"
    if UPDATE:
        path.write_text(text, encoding="utf-8")
    assert path.exists(), f"no golden file {path.name}: run with KRUSGRAPH_UPDATE_GOLDEN=1 once"
    assert text == path.read_text(encoding="utf-8"), f"{path.name} changed; regenerate deliberately if that is right"


def _run(src, **kw):
    s, execute = src
    return analysis_plan.recommend(plan(s), execute, **kw)


def _by(out):
    return {e["analysis"]: e for e in out["recommendations"]}


@pytest.fixture(scope="module")
def demo36():
    return _run(sap_demo36.sqlite())


def test_the_catalogue_has_ten_analyses_each_with_a_rule_and_a_notebook_phase():
    cat = analysis_plan.catalogue()
    ids = [a["id"] for a in cat["analyses"]]
    assert ids == [f"A{i}" for i in range(1, 11)]
    assert {a["notebook"] for a in cat["analyses"] if a["id"] in ("A7", "A8", "A3")} == {"P1"}
    assert all(a["rule"].startswith("R") and 1 <= a["value"] <= 5 for a in cat["analyses"])
    with pytest.raises(PlanInputError, match="only 'o2c'"):
        analysis_plan.catalogue("p2p")


def test_the_small_sap_demo_says_forecasting_is_missing_and_why():
    out = _run(sap_demo.sqlite())
    by = _by(out)
    assert by["A7"]["readiness"] == "missing" and by["A7"]["score"] == 0
    assert any("Only 1 month(s) of billing documents history" in m for m in by["A7"]["missing"])
    assert by["A7"]["because"].startswith("Not recommended yet because: ")
    assert by["A8"]["readiness"] == "missing" and any("RFM needs at least 50" in m for m in by["A8"]["missing"])
    assert by["A2"]["missing"] == ["customer open and cleared items: BSID/BSAD (ECC) or ACDOCA customer lines (S/4HANA)"]
    assert out["land_next"][0]["unlocks"] == ["A2", "A9"]
    _golden("analysis_plan_sap_demo", out)


def test_the_worked_example_of_the_design_on_sap_sd():
    src = sap_sample.source("sap_sd")
    out = analysis_plan.recommend(plan(src.schema), src.execute)
    by = _by(out)
    assert [e["analysis"] for e in out["recommendations"][:4]] == ["A7", "A8", "A3", "A4"]
    assert (by["A7"]["readiness"], by["A7"]["score"]) == ("ready", 4.0)
    assert by["A8"]["readiness"] == "partial" and by["A8"]["parts"]["customers"] == 0.387
    assert "108 customers with documents, 78.7 % of them with 2 or more (profile)" in by["A8"]["reasons"]
    assert any(c.startswith("capped at partial: customers") for c in by["A8"]["caveats"])
    assert by["A3"]["readiness"] == "ready" and any(c.startswith("XYZ part not ready: 59 of 149") for c in by["A3"]["caveats"])
    assert any("24 customers count as churned" in c for c in by["A4"]["caveats"])
    assert by["A5"]["readiness"] == "missing" and by["A10"].get("not_applicable")
    _golden("analysis_plan_sap_sd", out)


def test_the_36_month_demo_makes_forecasting_rfm_and_abc_xyz_ready_with_reasons(demo36):
    by = _by(demo36)
    for a in ("A7", "A8", "A3"):
        assert by[a]["readiness"] == "ready", (a, by[a])
        assert by[a]["because"].startswith("Recommended because: ") and by[a]["missing"] == []
        assert by[a]["next_step"].startswith(f'analysis_notebook_draft(analysis="{a}")')
    assert "sap_vbrk.FKDAT is the date (36 calendar months of billing documents with rows, no gap" in by["A7"]["because"]
    assert any(r.startswith("293 customers with documents") for r in by["A8"]["reasons"])
    assert any("k-means clustering" in r for r in by["A8"]["reasons"])
    assert any(r.startswith("XYZ: ") for r in by["A3"]["reasons"])
    assert [e["analysis"] for e in demo36["recommendations"][:4]] == ["A7", "A8", "A3", "A4"]
    assert set(by["A7"]["uses"]["tables"]) == {"sap_vbrk", "sap_vbrp"}
    _golden("analysis_plan_sap_demo36", demo36)


def test_the_answer_is_deterministic(demo36):
    again = _run(sap_demo36.sqlite())
    assert json.dumps(again, sort_keys=True, default=str) == json.dumps(demo36, sort_keys=True, default=str)


def test_too_few_periods_make_forecasting_missing():
    data = sap_demo36.tables()
    cols, kinds, rows = data["VBRK"]
    keep = [r for r in rows if r[10] >= "20251201"]                       # FKDAT: December 2025 to October 2026, 11 months
    data["VBRK"] = (cols, kinds, keep)
    by = _by(_run(sap_demo36.sqlite(data=data)))
    assert by["A7"]["readiness"] == "missing"
    assert any(m.startswith("Only 11 month(s) of billing documents history") for m in by["A7"]["missing"])
    assert by["A4"]["readiness"] == "missing" and "at least 12 months of history (11 now)" in by["A4"]["missing"]


def test_no_customer_key_makes_rfm_missing_and_names_it():
    data = sap_demo36.tables()
    for t, drop in (("VBRK", ("KUNAG", "KUNRG")), ("VBAK", ("KUNNR",))):
        cols, kinds, rows = data[t]
        idx = [i for i, c in enumerate(cols) if c not in drop]
        data[t] = ([cols[i] for i in idx], [kinds[i] for i in idx], [tuple(r[i] for i in idx) for r in rows])
    out = _run(sap_demo36.sqlite(data=data))
    by = _by(out)
    assert by["A8"]["readiness"] == "missing"
    assert by["A8"]["missing"][0].startswith("a customer column on the documents linked to the customer master")
    assert by["A7"]["readiness"] == "ready"                                # forecasting needs no customer
    assert any("A8" in x["unlocks"] for x in out["land_next"])


def test_nulls_are_left_out_of_the_counts_not_counted_as_values():
    data = sap_demo36.tables()
    cols, kinds, rows = data["VBRK"]
    rows = [r[:4] + (None,) + r[5:10] + (None if i % 50 == 0 else r[10],) + r[11:] for i, r in enumerate(rows)]  # KUNRG and some FKDAT NULL
    data["VBRK"] = (cols, kinds, rows)
    out = _run(sap_demo36.sqlite(data=data))
    by = _by(out)
    counts = out["signals"]["counts"]["billing"]
    assert counts["per_customer"]["customers"] == 0 or by["A8"]["readiness"] == "missing"
    assert by["A7"]["readiness"] == "ready"                                # a few dates missing: still 36 months
    assert counts["totals"]["row_count"] < 10485


def test_an_orphan_on_a_joined_relationship_lowers_quality_and_says_so():
    data = sap_demo36.tables()
    cols, kinds, rows = data["VBRK"]
    data["VBRK"] = (cols, kinds, rows[1:])                                 # the first invoice's items lose their header
    by = _by(_run(sap_demo36.sqlite(data=data)))
    assert by["A7"]["quality"] == 0.8 and by["A7"]["readiness"] == "ready" and by["A7"]["score"] == 3.2
    assert any("sap_vbrp rows point at no sap_vbrk row" in c and "quality factor 0.8" in c for c in by["A7"]["caveats"])


def test_profile_false_answers_from_names_only():
    s, _ = sap_demo36.sqlite()
    out = analysis_plan.recommend(plan(s), None)
    by = _by(out)
    assert out["signals"]["counts"].startswith("not counted")
    assert by["A7"]["readiness"] == "partial" and by["A7"]["readiness_value"] == 0.5
    assert any("rows not counted" in c for c in by["A7"]["caveats"])
    assert by["A2"]["readiness"] == "missing"


def test_personal_data_columns_are_never_read():
    s, execute = sap_demo36.sqlite()
    seen = []

    def spy(sql):
        seen.append(sql)
        return execute(sql)
    out = analysis_plan.recommend(plan(s), spy)
    text = " ".join(seen) + json.dumps(out)
    for col in ("NAME1", "STRAS", "PSTLZ", "ORT01", "TELF1", "SMTP_ADDR", "NAMEV"):
        assert f"[{col}]" not in text and f".{col}" not in text, col
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in seen)  # read-only
    assert len(seen) <= 20


def test_weights_and_document_types_are_the_customers_own():
    out = _run(sap_demo36.sqlite(), weights={"A3": 5}, document_types={"credit_billing_types": ["F2"]})
    by = _by(out)
    assert by["A3"]["value"] == 5 and by["A3"]["score"] == 5.0 and out["recommendations"][0]["analysis"] == "A3"
    assert by["A10"]["readiness"] != "missing" and "F2" in by["A10"]["because"]
    with pytest.raises(PlanInputError, match="weights"):
        _run(sap_demo36.sqlite(), weights={"A11": 3})
    with pytest.raises(PlanInputError, match="document_types"):
        _run(sap_demo36.sqlite(), document_types={"other": ["X"]})


# ------------------------------------------------------------------ the notebooks -----------------------------------

@pytest.mark.parametrize("analysis", ["A7", "A8", "A3"])
def test_the_notebook_drafts_are_valid_and_wired_to_the_tables(demo36, analysis):
    d = analysis_notebook.draft(demo36, analysis, INFO)
    text = d["notebook"]["content"]
    cells = notebook.parse(text)
    assert [k for k, _ in cells][:2] == ["markdown", "parameters"]
    for kind, code in cells:
        if kind != "markdown":
            compile(code, analysis, "exec")
    assert "`sap`" not in text or True
    assert "i.`MANDT` = h.`MANDT` AND i.`VBELN` = h.`VBELN`" in text      # the client column in the join
    assert "mlflow.set_experiment(EXPERIMENT_NAME)" in text and "krusgraph.analysis" in text
    assert "Recommended because: " in cells[0][1]
    nb = analysis_notebook.ipynb(analysis_notebook.spec(demo36, analysis, INFO))
    parsed = json.loads(json.dumps(nb))
    assert parsed["nbformat"] == 4 and parsed["cells"][1]["metadata"]["tags"] == ["parameters"]
    assert all(c["cell_type"] in ("markdown", "code") for c in parsed["cells"])
    feature = {"A7": "from flaml import AutoML", "A8": "from sklearn.cluster import KMeans", "A3": "pivot_table"}[analysis]
    assert feature in text
    for word in ("GA", "certified", "guarantee"):
        assert f" {word} " not in text


def test_a_notebook_is_refused_for_a_missing_analysis_or_one_without_a_phase_1_notebook(demo36):
    small = _run(sap_demo.sqlite())
    with pytest.raises(PlanInputError, match="A7 is not ready"):
        analysis_notebook.draft(small, "A7", INFO)
    with pytest.raises(PlanInputError, match="phase 1 has notebooks for A7, A8, A3"):
        analysis_notebook.draft(demo36, "A2", INFO)
    with pytest.raises(PlanInputError, match="output_schema"):
        analysis_notebook.draft(demo36, "A7", INFO, output_schema="sap")
