"""Round n150: six small datasets an outside tester ran through /check on 7 November 2026, with the answer key written
before the run (tests/fixtures/check_cases/<case>/). Each test runs the Python the /check worker runs
(browser_check.analyze for the check, browser_build.build for the Power BI preview and the downloads), on the same bytes
the page would hand it. The checks that were right before n150 are kept here as regression tests; each n150 fix has a
test that fails on the code before it."""
from __future__ import annotations

import base64
import io
import re
import zipfile
from pathlib import Path

import pytest

from fabric_backend import browser_build as bb
from fabric_backend import browser_check as bc

CASES = Path(__file__).resolve().parent / "fixtures" / "check_cases"


def files(case: str) -> list[tuple[str, bytes]]:
    return [(p.name, p.read_bytes()) for p in sorted((CASES / case).iterdir())]


_RUNS: dict = {}


def check(case: str) -> dict:
    if case not in _RUNS:
        _RUNS[case] = bc.analyze("files", files(case))
    return _RUNS[case]


def build(case: str, **kw) -> dict:
    return bb.build("files", files(case), **kw)


def model_files(b: dict) -> dict[str, str]:
    name = next(n for n in b["downloads"] if n.endswith("_model.zip"))
    z = zipfile.ZipFile(io.BytesIO(base64.b64decode(b["downloads"][name])))
    return {n: z.read(n).decode("utf-8") for n in z.namelist()}


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
