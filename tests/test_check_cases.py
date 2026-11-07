"""Round n150: six small datasets an outside tester ran through /check on 7 November 2026, with the answer key written
before the run (tests/fixtures/check_cases/<case>/). Each test runs the Python the /check worker runs
(browser_check.analyze for the check, browser_build.build for the Power BI preview and the downloads), on the same bytes
the page would hand it. The checks that were right before n150 are kept here as regression tests; each n150 fix has a
test that fails on the code before it."""
from __future__ import annotations

import base64
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from fabric_backend import browser_build as bb
from fabric_backend import browser_check as bc

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests" / "fixtures" / "check_cases"
sys.path.insert(0, str(ROOT / "tests"))
from test_browser import CHROMIUM, _playwright_available, site  # noqa: E402,F401  the same local server fixture


def files(case: str) -> list[tuple[str, bytes]]:
    return [(p.name, p.read_bytes()) for p in sorted((CASES / case).iterdir())]


_RUNS: dict = {}


def check(case: str) -> dict:
    if case not in _RUNS:
        _RUNS[case] = bc.analyze("files", files(case))
    return _RUNS[case]


def build(case: str, **kw) -> dict:
    return bb.build("files", files(case), **kw)


def model_files(b) -> dict[str, str]:
    """The files of the model zip: from build()'s answer, or a zip the page saved (its path)."""
    if isinstance(b, dict):
        name = next(n for n in b["downloads"] if n.endswith("_model.zip"))
        z = zipfile.ZipFile(io.BytesIO(base64.b64decode(b["downloads"][name])))
    else:
        z = zipfile.ZipFile(b)
    return {n: z.read(n).decode("utf-8") for n in z.namelist()}


def table_tmdl(mf: dict[str, str], table: str) -> str:
    return next(c for n, c in mf.items() if n.endswith(f"definition/tables/{table}.tmdl"))


@pytest.fixture(scope="module")
def browser(site, tmp_path_factory):  # noqa: F811
    """The page itself on 04, 05 and 06 (tests/check_cases_browser.js): what it shows and the files it saves."""
    if not _playwright_available():
        pytest.skip("node + playwright not available")
    saved = tmp_path_factory.mktemp("check_cases")
    out = subprocess.run(["node", str(ROOT / "tests" / "check_cases_browser.js"), site, str(CASES), str(saved)] + ([CHROMIUM] if CHROMIUM else []),
                         capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def tmdl_relationships(mf: dict[str, str]) -> list[tuple[str, str]]:
    text = next((c for n, c in mf.items() if n.endswith("definition/relationships.tmdl")), "")
    return re.findall(r"fromColumn: (\S+)\n\ttoColumn: (\S+)", text)


def keys_of(r: dict) -> dict[str, list[str]]:
    return {t["name"]: t["key"] for t in r["tables"]}


def rels_of(r: dict) -> set[tuple]:
    return {(x["source"], tuple(x["source_cols"]), x["target"], tuple(x["target_cols"])) for x in r["relationships"]}


def finding(r: dict, check_kind: str, table: str | None = None) -> dict | None:
    return next((f for f in r["findings"] + r["suggestions"] if f["check"] == check_kind and (table is None or f["table"] == table)), None)


# ------------------------------------------------------------------ the checks that were right: kept right ----------

def test_01_composite_key_the_line_key_and_every_reference():
    r = check("01_composite_key")
    assert keys_of(r) == {"order_items": ["order_id", "line_no"], "orders": ["order_id"]}
    assert rels_of(r) == {("order_items", ("order_id",), "orders", ("order_id",))}
    assert r["health"] == "2 of 2 keys unique, 1 of 1 relationships hold without orphans"      # 6 of 6 references match
    f = finding(r, "amount_level", "orders")
    assert f and f["amount"]["right"] == 600 and f["amount"]["wrong"] == 1300                 # SUM 600, naive join 1300


def test_02_many_to_many_the_bridge_and_both_relationships():
    r = check("02_many_to_many")
    assert keys_of(r)["enrollments"] == ["student_id", "course_id"]
    assert rels_of(r) == {("enrollments", ("student_id",), "students", ("student_id",)),
                          ("enrollments", ("course_id",), "courses", ("course_id",))}
    assert r["health"] == "3 of 3 keys unique, 2 of 2 relationships hold without orphans"
    f = finding(r, "amount_level", "students")
    assert f and (f["amount"]["right"], f["amount"]["wrong"]) == (600, 1200)


def test_03_null_foreign_key_a_null_is_not_an_orphan():
    r = check("03_null_foreign_key")
    assert r["health"] == "2 of 2 keys unique, 0 of 1 relationships hold without orphans"
    f = finding(r, "relationship", "orders")
    assert f["saw"].startswith("3 rows with a value, 1 of them point at nothing in customers")    # 5 rows, 2 NULL, 1 orphan (999)
    assert "Checked on all 5 rows of orders: 3 with a value." == f["checked"]


def test_04_duplicate_parent_the_key_is_reported_not_unique():
    r = check("04_duplicate_parent")
    f = finding(r, "key", "customers")
    assert f["severity"] == "problem" and f["saw"].startswith("4 rows, 3 distinct values, 0 NULLs")
    assert r["health"].startswith("1 of 2 keys unique")


def test_05_sap_keys_with_mandt_and_the_orphan():
    r = check("05_sap_mandt")
    assert keys_of(r) == {"VBAK": ["MANDT", "VBELN"], "VBAP": ["MANDT", "VBELN", "POSNR"]}
    assert rels_of(r) == {("VBAP", ("MANDT", "VBELN"), "VBAK", ("MANDT", "VBELN"))}
    f = finding(r, "relationship", "VBAP")
    assert f["saw"].startswith("5 rows with a value, 1 of them point at nothing in VBAK")      # 4 match, 1 orphan (200, 0000000020)
    a = finding(r, "amount_level", "VBAK")["amount"]
    assert (a["right"], a["wrong"]) == (600, 700)


def test_06_the_candidate_is_counted_and_not_applied():
    r = check("06_mismatched_names")
    assert rels_of(r) == set()                                                              # not an automatic relationship
    s = finding(r, "suggestion", "orders")
    assert s["title"] == "Suggested: orders.ship_to_id → addresses.address_id" and s["severity"] == "suggestion"
    assert s["saw"].startswith("4 rows with a value, 4 found in addresses's key, 3 distinct values (inclusion 100%)")


# ------------------------------------------------------------------ n150 fixes ---------------------------------------

def test_01_the_preview_never_counts_a_header_amount_as_rows():
    """Bug 1: "Total order_total by order_items" showed 3 (the rows of orders); its DAX sums order_total once per orders
    row that has lines: 600. A plain SUM of the header amount (summarizeBy: none) is left out, as create_report does."""
    rep = build("01_composite_key")["report"]
    m = {x["name"]: x["value"] for x in rep["measures"]}
    assert m.get("Total order_total by order_items") == 600, m
    assert "Total order_total" not in m and 3 not in [v for k, v in m.items() if "order_total" in k]
    assert m["Rows in order_items"] == 6 and m["Total line_amount"] == 600
    assert rep["doubled"]["right"] == 600 and rep["doubled"]["wrong"] == 1300


def test_04_a_key_that_is_not_unique_is_no_key_and_nothing_relates_onto_it():
    """Bug 2: after the duplicate warning the export marked customers.customer_id as isKey, built the relationship onto
    it, and the chart summed 700 against 600. Now the model is drafted with validate_plan's counts, as
    semantic_model_draft is: no isKey, the relationship is not built and says why, and no visual counts an order twice."""
    b = build("04_duplicate_parent")
    rep, mf = b["report"], model_files(b)
    assert "isKey" not in table_tmdl(mf, "customers") and "isKey" in table_tmdl(mf, "orders")
    assert tmdl_relationships(mf) == []
    assert rep["relationships"] == 0 and rep["plan_relationships"] == 1
    assert [(x["what"], x["reason"]) for x in rep["not_built"]] == [("orders.customer_id → customers", "key_not_unique")]
    assert "`customers.customer_id` is not unique in the rows (4 rows, 3 distinct values, 0 NULLs)" in rep["not_built"][0]["why"]
    assert rep["keys_not_unique"] == [{"table": "customers", "columns": ["customer_id"], "rows": 4, "distinct": 3, "nulls": 0}]
    readme = mf["data_model.SemanticModel/README.generated.md"]
    assert "`orders.customer_id -> customers.customer_id` (R1) is not in the model: `customers.customer_id` is not unique in the rows" in readme
    assert "no `isKey`, and no relationship is built onto it" in readme
    for chart in (rep["chart"], b["app"]["chart"]):                      # 600 in the rows; a join on the duplicate gives 700
        assert chart is None or sum(x["value"] for x in chart["bars"]) == 600, chart
    assert {m["name"]: m["value"] for m in rep["measures"]}["Total order_total"] == 600


def test_04_the_export_panel_says_the_key_is_not_exported(browser):
    o = browser["04_duplicate_parent"]
    assert "error" not in o and browser["errors"] == [], (o.get("error"), browser["errors"])
    text = o["model"]["text"]
    assert "2 tables and 1 relationship (0 exported, 1 not built: the key on the one side is not unique) from the plan" in text, text
    assert "customers.customer_id is not exported as a key: 4 rows, 3 distinct." in text
    assert "orders.customer_id → customers is not built: the key it points at is not unique in the rows (see README)." in text
    mf = model_files(o["model"]["zip"])                                  # the zip the page saved, not build()'s answer
    assert "isKey" not in table_tmdl(mf, "customers") and tmdl_relationships(mf) == []


SHIP_TO = {"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}
SHIP_TO_ROW = "| orders | ship_to_id | addresses | address_id | confirmed | confirmed by a person |"


def test_06_an_undecided_candidate_is_an_open_question():
    """Bug 4: before any decision the evidence report said 0 open questions; the candidate the page asks about is one."""
    e = check("06_mismatched_names")["evidence_report"]
    assert e["summary"]["open_questions"] == 1 and e["summary"]["relationships"] == 0
    assert ("- orders.ship_to_id -> addresses was suggested from the rows (4 of 4 rows with a value found in addresses's key) "
            "and not applied: nobody has accepted or rejected it yet.") in e["markdown"]


def test_06_accept_puts_the_relationship_in_the_report_and_the_model_and_reject_keeps_it_out():
    """Bug 3: Accept and Reject changed the page but not the export (all model files identical, no relationship). The
    decision now goes to the engine: accepted, the relationship is a confirmed entry of the plan, counted, and in the
    TMDL; rejected, it is in neither, and in both cases it is no longer an open question."""
    acc = bc.decide("files", files("06_mismatched_names"), accepted=[SHIP_TO])
    assert acc["health"] == "2 of 2 keys unique, 1 of 1 relationships hold without orphans"
    md = acc["evidence_report"]["markdown"]
    assert SHIP_TO_ROW in md and "| relationship | orders.ship_to_id -> addresses | holds for all 4 rows with a value |" in md
    assert acc["evidence_report"]["summary"]["open_questions"] == 0
    assert tmdl_relationships(model_files(build("06_mismatched_names", confirmed=[SHIP_TO]))) == [("orders.ship_to_id", "addresses.address_id")]
    rej = bc.decide("files", files("06_mismatched_names"), rejected=[SHIP_TO])
    assert "ship_to_id | addresses" not in rej["evidence_report"]["markdown"] and rej["evidence_report"]["summary"]["open_questions"] == 0
    assert rej["relationships"] == [] and tmdl_relationships(model_files(build("06_mismatched_names"))) == []


def test_06_on_the_page_accept_and_skip_are_in_the_plain_list(browser):
    """Bug 7: the plain CSV view said "Accept ...; Skip ..." with no buttons unless the guide was opened."""
    o = browser["06_mismatched_names"]
    assert "error" not in o and browser["errors"] == [], (o.get("error"), browser["errors"])
    assert o["buttons"] == ["Accept", "Skip"] and "Suggested: orders.ship_to_id → addresses.address_id" in o["suggestions"]


def test_06_on_the_page_the_report_and_the_model_follow_the_decision(browser):
    """Bugs 3 and 4 on the page itself: the files it saves before a decision, after Accept and after Skip."""
    o = browser["06_mismatched_names"]
    assert "error" not in o, o.get("error")
    before = Path(o["report_before"]).read_text()
    assert "- 1 open question(s), 0 decision(s)" in before and "orders.ship_to_id -> addresses was suggested from the rows" in before
    assert tmdl_relationships(model_files(o["model_before"]["zip"])) == []
    a = o["accepted"]
    md = Path(a["report"]).read_text()
    assert SHIP_TO_ROW in md and "- 0 open question(s), 1 decision(s)" in md and "accepted, in the plan as confirmed" in md
    assert tmdl_relationships(model_files(a["model"]["zip"])) == [("orders.ship_to_id", "addresses.address_id")]
    assert "2 tables and 1 relationship from the plan" in a["model"]["text"]
    assert "Accepted on this page: orders.ship_to_id → addresses is in the model as a confirmed relationship." in a["model"]["text"]
    assert a["said"].startswith("Accepted on this page: the relationship is in the plan as confirmed")
    j = o["rejected"]
    md = Path(j["report"]).read_text()
    assert "ship_to_id | addresses" not in md and "- 0 open question(s), 1 decision(s)" in md and "rejected, the column stays unlinked" in md
    assert tmdl_relationships(model_files(j["model"]["zip"])) == []
    assert "Skipped on this page: orders.ship_to_id → addresses is not in the model." in j["model"]["text"]


def test_05_the_export_counts_what_the_model_holds():
    """Bug 5: the panel said 1 relationship while the model held 0: VBAP.MANDT+VBELN → VBAK needs a combined key column."""
    b = build("05_sap_mandt")
    rep, mf = b["report"], model_files(b)
    assert rep["relationships"] == 0 and rep["plan_relationships"] == 1 and tmdl_relationships(mf) == []
    assert [(x["what"], x["reason"]) for x in rep["not_built"]] == [("VBAP.MANDT+VBELN → VBAK", "combined_key")]


def test_05_the_export_panel_says_0_exported_and_why(browser):
    o = browser["05_sap_mandt"]
    assert "error" not in o, o.get("error")
    assert "2 tables and 1 relationship (0 exported, 1 needs a combined key column (see README)) from the plan" in o["model"]["text"]
    assert tmdl_relationships(model_files(o["model"]["zip"])) == []

def test_05_the_fan_out_counts_only_headers_that_exist():
    """Bug 6: the text said VBAP has 1.25 rows per VBAK row over 4 referenced values (the orphan group among them); VBAK
    has 3 rows, 4 matching items: 4/3 ≈ 1.33, and the orphan is said apart."""
    f = finding(check("05_sap_mandt"), "amount_level", "VBAK")
    assert "VBAP has 1.33 rows for each row of VBAK on average and up to 2" in f["saw"]
    assert "(3 VBAK row(s) with VBAP rows; apart from those, 1 VBAP row(s) point at 1 value(s) that are not in VBAK)" in f["saw"]
    assert "1.25" not in f["saw"] and "4 referenced" not in f["saw"]
    assert f["checked"] == "Counted on all rows of VBAK and VBAP: 3 VBAK rows with VBAP rows, at most 2 each."

