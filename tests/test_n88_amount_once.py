"""n88, point 2: amount_levels said "comes out about 1 times too large" where every header has one line (sap_vbap against
sap_lips and sap_vbrp in the live test of 2 November 2026). Then nothing is repeated today: the explanation says so and
that the relationship allows it, and keeps the counts. Checked on the synthetic SAP demo in SQLite."""
from fabric_backend import amounts, evidence, sap_demo
from fabric_backend.infer import plan


def test_one_line_per_header_says_nothing_is_repeated_today():
    schema, execute = sap_demo.sqlite()
    levels = evidence.validate(plan(schema), execute, max_items=200)["amount_levels"]
    once = [f for f in levels["findings"] if isinstance(f["rows_per_header"], dict) and f["rows_per_header"]["max_lines"] == 1]
    assert once, [(f["header"], f["line"], f["rows_per_header"]) for f in levels["findings"]]
    for f in once:
        assert "1 times too large" not in f["explanation"] and "times too large" not in f["explanation"]
        assert "no row is repeated today" in f["explanation"] and "can" in f["explanation"]
        assert f["rows_per_header"]["headers"] > 0                       # the counts stay
    many = [f for f in levels["findings"] if isinstance(f["rows_per_header"], dict) and f["rows_per_header"]["max_lines"] > 1]
    assert many
    for f in many:                                                       # n89: a factor only where it is exact
        rp = f["rows_per_header"]
        if rp["min_lines"] == rp["max_lines"]:
            assert f"comes out {rp['max_lines']} times too large" in f["explanation"], f["explanation"]
        else:
            assert "times too large" not in f["explanation"] and "comes out too large" in f["explanation"], f["explanation"]


def test_the_explanation_with_counts_of_one():
    f = {"line": "l", "header": "h", "amount_columns": ["amt"], "line_columns": ["id"], "header_columns": ["id"], "rule": "R1"}
    text = amounts._explain(f, {"headers": 4, "avg_lines": 1.0, "min_lines": 1, "max_lines": 1})
    assert "no row is repeated today" in text and "4 referenced header value(s)" in text and "1 times" not in text
