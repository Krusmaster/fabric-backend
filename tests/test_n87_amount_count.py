"""n87, point 3: validate_plan's amount_levels on the SAP schema. The live run of 2 November answered error 130 on every
header amount ("Cannot perform an aggregate function on an expression containing an aggregate or a subquery": the
counting query had SUM(CASE WHEN EXISTS (SELECT ...))), and the summary still said "0 with more than one line per
header". The query is now one SQL Server runs; a count that fails is said as such, in readable words, never as 0.
Checked on the synthetic SAP demo in SQLite, behind an endpoint that refuses what SQL Server refuses (error 130)."""
import sqlglot
from sqlglot import exp

from fabric_backend import amounts, evidence, sap_demo
from fabric_backend.infer import plan

ODBC_130 = ("('42000', '[42000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]Cannot perform an aggregate function "
            "on an expression containing an aggregate or a subquery. (130) (SQLExecDirectW)')")


class ProgrammingError(Exception):
    """What pyodbc raises; named the same so the error mapping treats it as the driver's."""


def _aggregate_over_subquery(sql: str) -> bool:
    tree = sqlglot.parse_one(sql, read="tsql")
    for agg in tree.find_all(exp.AggFunc):
        if any(agg.this is not None and node is not None for node in [agg.this.find(exp.Exists), agg.this.find(exp.Subquery)]):
            return True
    return False


def sql_server_like(execute):
    """The SQLite connection behind the rule SQL Server applies: no aggregate over a subquery (error 130)."""
    def run(sql, *a, **k):
        if _aggregate_over_subquery(sql):
            raise ProgrammingError(ODBC_130)
        return execute(sql, *a, **k)
    run.dialect = getattr(execute, "dialect", None)
    return run


def test_the_endpoint_double_refuses_what_sql_server_refuses():
    assert _aggregate_over_subquery("SELECT SUM(CASE WHEN EXISTS (SELECT 1 FROM t) THEN 1 ELSE 0 END) FROM g")
    assert not _aggregate_over_subquery("SELECT SUM(f) FROM (SELECT CASE WHEN EXISTS (SELECT 1 FROM t) THEN 1 ELSE 0 END AS f FROM g) AS x")


def test_the_lines_per_header_count_runs_on_the_sap_schema():
    schema, execute = sap_demo.sqlite()
    p = plan(schema)
    out = evidence.validate(p, sql_server_like(execute), max_items=200)
    levels = out["amount_levels"]
    assert levels["findings"] and not any("count_error" in f for f in levels["findings"]), levels["findings"]
    header, line, column = sap_demo.EXPECTED["header_amount"]
    f = next(f for f in levels["findings"] if column in f["amount_columns"] and f["rows_per_header"] != "unknown"
             and f["rows_per_header"]["max_lines"] == 3)
    assert f["rows_per_header"]["headers_in_table"] <= f["rows_per_header"]["headers"]


def test_a_count_that_fails_is_never_zero():
    schema, execute = sap_demo.sqlite()
    p = plan(schema)

    def refuses(sql, *a, **k):
        if "max_lines" in sql:
            raise ProgrammingError(ODBC_130)
        return execute(sql, *a, **k)
    refuses.dialect = getattr(execute, "dialect", None)
    levels = amounts.check(p, refuses)
    n = len(levels["findings"])
    assert n and "0 with more than one line" not in levels["summary"]
    assert f"{n} could not be counted" in levels["summary"]
    for f in levels["findings"]:
        assert "ODBC" not in f["count_error"] and "SQLExecDirectW" not in f["count_error"] and "42000" not in f["count_error"]
        assert "aggregate" in f["count_error"] and "error 130" in f["count_error"]
        assert f["rows_per_header"] == "unknown"
