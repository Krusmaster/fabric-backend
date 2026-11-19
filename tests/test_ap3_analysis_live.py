"""AP3 (19-20 Nov 2026): what the live run of analysis_plan in the demo workspace found.

1. On the Fabric SQL analytics endpoint the per-customer count failed (ProgrammingError) on both datasets: its subquery
   named a column `top`, a reserved word in T-SQL that SQLite accepts. The tests ran on SQLite, so they never saw it.
2. With that count gone, A8 said "Only 0 customers with documents" while the same answer's totals counted 1: a count
   that did not run was read as zero.
3. analysis_notebook_draft's "not ready" error came with the hint about keys and confirmed, which is not the cause.
"""
from __future__ import annotations

import re

from fabric_backend import analysis_plan, errors, sap_demo, sap_demo36
from fabric_backend.dialects import TSQL
from fabric_backend.infer import PlanInputError, plan

# Reserved keywords of T-SQL (Microsoft Learn, "Reserved keywords (Transact-SQL)") that look like column names.
TSQL_RESERVED = {"top", "key", "order", "group", "user", "file", "plan", "percent", "current", "public", "rule",
                 "schema", "table", "view", "open", "close", "function", "index", "identity", "begin", "end", "check",
                 "primary", "foreign", "default", "distinct", "values", "union", "trigger", "transaction", "read", "add"}


def _aliases(sql: str) -> set[str]:
    return {m.lower() for m in re.findall(r"\bAS\s+([A-Za-z_]\w*)", sql)}


def _counted_sqls(src):
    s, _ = src
    p = plan(s)
    roles = analysis_plan.resolve(p, analysis_plan.catalogue())
    out = []
    for ds in roles["datasets"].values():
        if analysis_plan._usable(ds):
            out += list(analysis_plan.count_sql(p, ds, TSQL, ["G2", "RE"]).values())
    return out


def test_no_counting_statement_names_a_column_after_a_tsql_reserved_word():
    sqls = _counted_sqls(sap_demo.sqlite())
    assert sqls
    for sql in sqls:
        bad = _aliases(sql) & TSQL_RESERVED
        assert not bad, f"T-SQL reserved word used as a name: {bad}"
        assert not re.search(r"\.\s*top\b", sql, re.I)


def _like_fabric(execute):
    """SQLite plus the one T-SQL rule the live run hit: a reserved word as a column name is a syntax error."""
    class ProgrammingError(Exception):
        pass

    def run(sql: str):
        if _aliases(sql) & TSQL_RESERVED:
            raise ProgrammingError("Incorrect syntax near the keyword")
        return execute(sql)
    return run


def test_every_count_runs_where_reserved_words_are_refused():
    s, execute = sap_demo.sqlite()
    out = analysis_plan.recommend(plan(s), _like_fabric(execute))
    for ds in out["signals"]["counts"].values():
        assert not ds["not_counted"], ds["not_counted"]
        assert "per_customer" in ds


def _without_per_customer(execute):
    def run(sql: str):
        if "repeat_customers" in sql:
            raise RuntimeError("the count could not run")
        return execute(sql)
    return run


def test_a_per_customer_count_that_did_not_run_is_not_read_as_zero_customers():
    s, execute = sap_demo36.sqlite()
    out = analysis_plan.recommend(plan(s), _without_per_customer(execute))
    by = {e["analysis"]: e for e in out["recommendations"]}
    assert any(n.startswith("per_customer") for n in out["signals"]["counts"]["billing"]["not_counted"])
    a8 = by["A8"]
    assert not any("Only 0 customers" in m for m in a8["missing"])
    assert a8["readiness"] == "partial"
    assert any("the per-customer count did not run" in c for c in a8["caveats"])
    a4 = by["A4"]
    assert a4["readiness"] == "partial"
    assert any("the per-customer count did not run" in c for c in a4["caveats"])
    assert by["A7"]["readiness"] == "ready"                      # A7 needs no per-customer count


def test_too_few_customers_in_the_totals_is_still_missing_when_the_per_customer_count_failed():
    s, execute = sap_demo.sqlite()
    out = analysis_plan.recommend(plan(s), _without_per_customer(execute))
    a8 = {e["analysis"]: e for e in out["recommendations"]}["A8"]
    n = out["signals"]["counts"]["billing"]["totals"]["customers"]
    assert a8["readiness"] == "missing"
    assert f"Only {n} customers with documents; RFM needs at least 50." in a8["missing"]


def test_the_not_ready_error_hints_at_the_data_not_at_the_keys():
    out = errors.explain(PlanInputError("A7 is not ready on this data: Only 1 month(s) of billing documents history"),
                         "analysis_notebook_draft")
    assert out["kind"] == "bad_input"
    assert "keys and confirmed" not in out["hint"]
    assert "land_next" in out["hint"]
