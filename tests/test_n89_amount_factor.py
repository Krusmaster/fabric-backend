"""n89: amount_levels wrote "comes out about {avg_lines} times too large", but the average number of lines per header is
not the ratio of the two sums once headers have different numbers of lines: /check?example=sap said "about 1.5 times
too large" for sap_vbak.NETWR over sap_vbap beside the sums 1 950 and 750 (2.6 times). The factor is written only when
every referenced header has the same number of lines (min_lines == max_lines > 1), and then it is exact; /check shows
the ratio from the counted sums. The hosted validate_plan still counts lines and sums nothing. Synthetic data, SQLite."""
import re

from fabric_backend import amounts, browser_check, evidence, evidence_report, sap_demo
from fabric_backend.demo_app import _ratio
from fabric_backend.infer import plan

F = {"line": "l", "header": "h", "amount_columns": ["amt"], "line_columns": ["id"], "header_columns": ["id"], "rule": "R1"}


def _sap_finding(findings, header, line):
    return next(f for f in findings if f["check"] == "amount_level" and f["amount"]["header"] == header and f["amount"]["line"] == line)


def test_sap_on_check_has_no_factor_that_contradicts_the_sums():
    r = browser_check.analyze("sap")
    f = _sap_finding(r["findings"], "sap_vbak", "sap_vbap")
    a = f["amount"]
    assert (a["wrong"], a["right"]) == (1950.0, 750.0)
    assert a["rows_per_header"]["min_lines"] == 1 and a["rows_per_header"]["max_lines"] == 3
    for text in (f["saw"], f["means"]):
        assert "1.5 times" not in text and "times too large" not in text, text
    assert "1 950" in f["saw"] and "750" in f["saw"] and "the join gives 2.6 times the sum per header" in f["saw"]
    assert "between 1 and 3 sap_vbap rows each" in f["means"] and "not the ratio of the two sums" in f["means"]
    # every factor anywhere on the result agrees with the sums it stands beside
    for g in r["findings"]:
        if g["check"] != "amount_level" or g["amount"].get("wrong") is None:
            continue
        for n in re.findall(r"comes out (\d+) times too large", g["means"]):
            assert float(g["amount"]["wrong"]) == int(n) * float(g["amount"]["right"]), g["means"]


def test_sap_n88_finding_keeps_its_sentence_on_check():
    r = browser_check.analyze("sap")
    f = _sap_finding(r["findings"], "sap_vbap", "sap_lips")
    assert "no row is repeated today" in f["saw"] and "The relationship." not in f["saw"]
    assert "the join gives the same sum" in f["saw"]


def test_equal_lines_per_header_keep_the_exact_factor():
    d = amounts.demo()                                                  # A total that doubles: one order, two lines
    assert (d["before"], d["after"]) == (2000.0, 1000.0)
    rp = d["finding"]["rows_per_header"]
    assert rp["min_lines"] == rp["max_lines"] == 2
    assert "comes out 2 times too large" in d["finding"]["explanation"] and "about" not in d["finding"]["explanation"]
    assert _ratio(2000.0, 1000.0) == "; the join gives 2 times the sum per header"
    schema, execute = sap_demo.sqlite()                                 # sap_vbrk over sap_vbrp: two lines on its one invoice
    levels = evidence.validate(plan(schema), execute, max_items=200)["amount_levels"]
    f = next(f for f in levels["findings"] if (f["header"], f["line"]) == ("sap_vbrk", "sap_vbrp"))
    assert "comes out 2 times too large" in f["explanation"]


def test_one_line_per_header_and_unknown_count_are_unchanged():
    one = amounts._explain(F, {"headers": 4, "avg_lines": 1.0, "min_lines": 1, "max_lines": 1})
    assert "no row is repeated today" in one and "times too large" not in one
    unknown = amounts._explain(F, None)
    assert "unknown until the data is counted" in unknown and "counts each h row once per l row" in unknown
    assert "times too large" not in unknown


def test_uneven_lines_write_no_factor_and_a_count_without_min_writes_none_either():
    uneven = amounts._explain(F, {"headers": 3, "avg_lines": 1.5, "min_lines": 1, "max_lines": 3})
    assert "times too large" not in uneven and "1.5 times" not in uneven and "between 1 and 3 l rows each" in uneven
    no_min = amounts._explain(F, {"headers": 3, "avg_lines": 2.0, "max_lines": 2})
    assert "times too large" not in no_min and "comes out too large" in no_min


def test_the_ratio_is_from_the_sums():
    assert _ratio(1950.0, 750.0) == "; the join gives 2.6 times the sum per header"
    assert _ratio(1000.0, 700.0) == "; the join gives about 1.43 times the sum per header"
    assert _ratio(500.0, 500.0) == "; the join gives the same sum"
    assert _ratio(None, 750.0) == "" and _ratio(100.0, 0) == ""


def test_the_counting_query_counts_lines_and_sums_no_amount():
    sql = amounts.lines_per_header_sql("sap", "sap_vbap", ["MANDT", "VBELN"], header="sap_vbak", header_cols=["MANDT", "VBELN"])
    assert "MIN(CASE WHEN f.in_header = 1 THEN f.n END) AS min_lines" in sql and "NETWR" not in sql
    # the SUMs add 0/1 flags and, since n150, the line counts of the orphan groups: never an amount
    assert "SUM(f.in_header)" in sql and sql.count("SUM(") == sql.count("SUM(f.in_header)") + sql.count("SUM(CASE WHEN f.in_header = 1 THEN 0 ELSE f.n END)")


def test_validate_plan_returns_counts_and_no_sums():
    schema, execute = sap_demo.sqlite()
    v = evidence.validate(plan(schema), execute, max_items=200)
    for f in v["amount_levels"]["findings"]:
        assert not {"summed_over_lines", "summed_per_header", "before", "after"} & set(f)
        rp = f["rows_per_header"]
        assert set(rp) <= {"headers", "avg_lines", "min_lines", "max_lines", "headers_in_table", "orphan_values", "orphan_lines"}
        assert "1 950" not in f["explanation"] and "750" not in f["explanation"]
    rep = evidence_report.report(plan(schema), v)
    counted = [c for c in rep["checks"] if c["check"] == "amount_level" and "counts" in c]
    assert counted and all("min_lines" in c["counts"] for c in counted)
    assert not any("times too large" in str(c) for c in rep["checks"])
