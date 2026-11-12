"""n226: evidence state and coverage on every plan answer (SCOPE-REVIEW section 6, item 1) and one time budget per call
with partial results (item 2), on a synthetic schema of more than 200 keyed tables and on the shop sample.

Before n226 the check counted every key before any link with a ceiling of 200 items, so above 200 keyed tables no link
was ever counted; one failed query aborted the call; nothing bounded a call's time. The numbers below are those of the
counting double (a fake connection that answers every count), not of a database, and say nothing about speed.
"""
from __future__ import annotations

import json
import sys

import pytest

from fabric_backend import budget, coverage, evidence, seed
from fabric_backend.infer import plan
from fabric_backend.schema import Schema

N = 260                                         # keyed tables: above the 200-item ceiling


def _big_schema(n: int = N) -> Schema:
    """t000..t{n-1}: each keyed by t<i>_id (rule K2) and pointing at the next table by t<j>_id (rule R1), plus one
    column that looks like a reference and points at nothing (legacy_ref_id)."""
    rows = []
    for i in range(n):
        j = (i + 1) % n
        for k, (c, typ) in enumerate([(f"t{i:03d}_id", "int"), (f"t{j:03d}_id", "int"), ("legacy_ref_id", "int"),
                                      ("amount_text", "varchar")], 1):
            rows.append(("dbo", f"t{i:03d}", c, typ, k))
    return Schema.from_information_schema(rows, schema="dbo")


class Counter:
    """A connection double: every key unique (1000 rows), every link holds (800 rows with a value). `fail` names
    tables whose statements raise; `tick` advances `clock` by one second per statement."""

    def __init__(self, fail=(), clock=None):
        self.fail, self.clock, self.statements = set(fail), clock, []

    def __call__(self, sql):
        self.statements.append(sql)
        if self.clock is not None:
            self.clock.now += 1.0
        if any(f"[{t}]" in sql for t in self.fail):
            raise RuntimeError("Invalid object name (a stand-in for the endpoint's error)")
        row = {"n": 1000, "nulls": 0, "distinct_keys": 1000, "with_value": 800, "orphans": 0, "several": 0}
        for i in range(1, 40):
            row[f"with_value_{i}"], row[f"orphans_{i}"] = 800, 0
        return [row]


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_the_plan_of_the_big_schema():
    p = plan(_big_schema())
    assert len(p.keys) == N and len(p.relationships) == N
    assert {r for _, r in p.keys.values()} == {"K2"} and {r.rule for r in p.relationships} == {"R1"}


def test_links_are_counted_above_200_keyed_tables():
    """The 200-item ceiling no longer starves the links: each link comes right after its target's key."""
    p = plan(_big_schema())
    queue = evidence.check_order(p)
    assert len(queue) == 2 * N
    assert queue[:4] == [("key", "t001"), ("rel", 0), ("key", "t002"), ("rel", 1)]
    out = evidence.validate(p, Counter(), max_items=200)
    assert len(out["keys"]) == 100 and len(out["relationships"]) == 100       # before n226: 200 keys and 0 links
    assert out["not_checked_beyond_max_items"] == 2 * N - 200
    assert "checked 200 of 520" in out["summary"] and out["resume"]["resume_from"] == 200
    # the resume call counts the next 200 in the same order, and a third the last 120
    nxt = evidence.validate(p, Counter(), max_items=200, resume_from=200)
    assert len(nxt["keys"]) + len(nxt["relationships"]) == 200 and nxt["resume"]["resume_from"] == 400
    last = evidence.validate(p, Counter(), max_items=200, resume_from=400)
    assert len(last["keys"]) + len(last["relationships"]) == 120 and "resume" not in last
    counted = {k["table"] for x in (out, nxt, last) for k in x["keys"]}
    linked = {(r["source"], r["target"]) for x in (out, nxt, last) for r in x["relationships"]}
    assert len(counted) == N and len(linked) == N                             # three calls, every item once


def test_coverage_headline_before_and_after_the_check():
    p = plan(_big_schema())
    before = coverage.coverage(p)
    assert before["headline"] == ("260 tables: 0 with a counted key, 260 with a key by name only, 0 without a key; "
                                  "260 links proposed, 0 counted, 0 hold; 260 columns that look like references are unlinked.")
    assert before["unlinked_first"][0] == "t000.legacy_ref_id"
    out = evidence.validate(p, Counter(), max_items=200)
    after = coverage.coverage(p, out)
    assert after["headline"] == ("260 tables: 100 with a counted key, 160 with a key by name only, 0 without a key; "
                                 "260 links proposed, 100 counted, 100 hold; 260 columns that look like references are unlinked.")
    st = coverage.states(p, out)
    assert st["key:t001"] == "counted unique" and st["rel:t000.t001_id>t001"] == "counted and holds"
    assert st["key:t000"] == "by name only"                                   # its key comes last in the order: not counted
    g = coverage.grouped(st)
    assert list(g) == ["counted unique", "counted and holds", "by name only"]
    assert len(g["by name only"]) == 2 * N - 200


def test_the_time_budget_returns_what_was_counted_and_how_to_resume():
    p = plan(_big_schema())
    clock = Clock()
    with budget.call(seconds=45, clock=clock):
        out = evidence.validate(p, Counter(clock=clock), max_items=200)
    counted = len(out["keys"]) + len(out["relationships"])
    assert counted == 45                                                     # one second per statement in the double
    timed = [x for x in out["not_counted"] if x["evidence"] == budget.NOT_CHECKED]
    assert len(timed) == 200 - 45
    tb = out["time_budget"]
    assert tb["ran_out"] is True and tb["seconds"] == 45 and tb["not_checked_time"] == 155 and tb["resume_from"] == 45
    assert "not checked (time)" in out["summary"] and "resume_from=45" in out["summary"]
    assert evidence.next_steps(out, {"not_checked_beyond_max_items": out["not_checked_beyond_max_items"]})[0]["arguments"] == {"resume_from": 45}
    summary = evidence.summarize(out, p)
    assert summary["totals"]["not_counted_items"] == 155 and "time_budget" in summary
    assert "All" not in summary.get("result", "")                             # never "all passed" over a part
    head = coverage.coverage(p, out)["headline"]
    assert "155 not checked (time)" in head
    # the resume call starts where the time ran out: its first statement is the 46th item of the order
    clock2 = Clock()
    log = Counter(clock=clock2)
    with budget.call(seconds=45, clock=clock2):
        nxt = evidence.validate(p, log, max_items=200, resume_from=tb["resume_from"])
    kind, x = evidence.check_order(p)[45]
    name = x if kind == "key" else p.relationships[x].source
    assert f"[{name}]" in log.statements[0] and nxt["time_budget"]["resume_from"] == 90


def test_no_budget_outside_a_call_and_the_statement_timeout_is_cut():
    assert budget.current() is None and not budget.expired() and budget.statement_timeout(120) == 120
    clock = Clock()
    with budget.call(seconds=45, clock=clock):
        assert budget.statement_timeout(120) == 45
        clock.now = 43.5
        assert budget.statement_timeout(120) == budget.MIN_STATEMENT_SECONDS
        clock.now = 46
        with pytest.raises(budget.TimeUp):
            budget.check("a SQL read")
    with budget.call(bounded=False):                                          # a creating call: no deadline
        assert budget.current() is None
    assert budget.call_seconds() == budget.CALL_SECONDS == 45.0


def test_a_failed_query_is_one_item_not_counted_and_the_check_goes_on():
    p = plan(_big_schema(12))
    out = evidence.validate(p, Counter(fail={"t005"}))
    bad = {x["id"]: x["evidence"] for x in out["not_counted"]}
    assert set(bad) == {"key:t005", "rel:t004.t005_id>t005", "rel:t005.t006_id>t006"}
    assert all(v.startswith("not counted: the counting query failed (RuntimeError") for v in bad.values())
    assert len(out["keys"]) == 11 and len(out["relationships"]) == 10        # everything else counted
    assert "3 not counted because the query failed" in out["summary"]
    st = coverage.states(p, out)
    assert st["key:t005"].startswith("not counted: ") and st["key:t004"] == "counted unique"


def test_queries_that_keep_failing_stop_the_check_with_the_reason():
    p = plan(_big_schema(12))
    out = evidence.validate(p, Counter(fail={f"t{i:03d}" for i in range(12)}))
    tried = [x for x in out["not_counted"] if "query failed" in x["evidence"]]
    stopped = [x for x in out["not_counted"] if "in a row failed" in x["evidence"]]
    assert len(tried) == evidence.STOP_AFTER_FAILURES and len(stopped) == 24 - evidence.STOP_AFTER_FAILURES
    assert out["keys"] == [] and out["relationships"] == []


def test_tables_scopes_the_check():
    p = plan(_big_schema(12))
    log = Counter()
    out = evidence.validate(p, log, tables=["t003"])
    assert [k["table"] for k in out["keys"]] == ["t003"]
    assert {(r["source"], r["target"]) for r in out["relationships"]} == {("t002", "t003"), ("t003", "t004")}
    assert out["scope"] == {"items": 3, "resume_from": 0, "tables": ["t003"]}
    assert len(log.statements) == 3 + 0                                       # one per item; the amounts find no header


def test_r5_under_the_time_budget_says_not_checked():
    s = seed.schema("shop")
    calls = []

    def execute(sql):
        calls.append(sql)
        return [{}]
    with budget.call(seconds=45, clock=Clock()) as d:
        d.start = -100                                                        # spent before the plan starts
        p = plan(s, execute=execute, sample=200, max_queries=20)
    assert calls == []                                                        # no counting query after the budget
    assert p.counted["scan"].startswith("the search for code and role columns stopped")
    assert "not checked (time)" in p.summary()


@pytest.fixture
def local(monkeypatch):
    """The local stdio server over the shop rows in SQLite, as tests/test_golden.py runs it."""
    import golden_support as gs
    import requests
    fake = gs.FakeFabric()
    for verb in ("get", "post", "patch"):
        monkeypatch.setattr(requests, verb, getattr(fake, verb))
    monkeypatch.setitem(sys.modules, "pyodbc", gs.fake_pyodbc())
    monkeypatch.setenv("FABRIC_ODBC", f"Driver={{ODBC Driver 18 for SQL Server}};Server={gs.SQL_HOST};Database=demo_lh;Authentication=ActiveDirectoryInteractive")
    monkeypatch.setenv("FABRIC_TOKEN", "fabric-token")
    for var in ("FABRIC_SOURCE_KIND", "FABRIC_SCHEMAS_ENABLED"):
        monkeypatch.delenv(var, raising=False)
    return fake


def test_the_local_tools_carry_evidence_and_coverage(local):
    from fabric_backend import mcp_server
    out = json.loads(mcp_server.plan_backend(schema="shop", detail="full"))
    assert out["coverage"]["headline"] == ("7 tables: 0 with a counted key, 6 with a key by name only, 1 without a key; "
                                           "6 links proposed, 0 counted, 0 hold; 1 column that looks like a reference is "
                                           "unlinked.")
    assert out["coverage"]["unlinked_first"] == ["orders.ship_to_id"]
    assert {k["evidence"] for k in out["keys"].values()} == {r["evidence"] for r in out["relationships"]} == {"by name only"}
    summary = json.loads(mcp_server.plan_backend(schema="shop", detail="summary"))
    assert list(summary["evidence"]) == ["by name only"] and len(summary["evidence"]["by name only"]) == 12
    checked = json.loads(mcp_server.validate_plan(schema="shop"))
    assert checked["coverage"]["headline"] == ("7 tables: 6 with a counted key, 0 with a key by name only, 1 without a key; "
                                               "6 links proposed, 6 counted, 6 hold; 1 column that looks like a reference "
                                               "is unlinked.")
    assert list(checked["evidence"]) == ["counted unique", "counted and holds"]
    assert checked["time_budget"]["ran_out"] is False and checked["time_budget"]["seconds"] == 45


def test_the_check_order_puts_busy_tables_first():
    """Importance: a link into a table that many links touch comes before a link between two quiet tables."""
    rows = [("dbo", "customers", "customer_id", "int", 1)]
    for t in ("orders", "invoices", "visits"):
        rows += [("dbo", t, f"{t[:-1]}_id", "int", 1), ("dbo", t, "customer_id", "int", 2)]
    rows += [("dbo", "colours", "colour_id", "int", 1), ("dbo", "shades", "shade_id", "int", 1), ("dbo", "shades", "colour_id", "int", 2)]
    p = plan(Schema.from_information_schema(rows, schema="dbo"))
    q = evidence.check_order(p)
    first_rel = p.relationships[q[1][1]]
    assert q[0] == ("key", "customers") and first_rel.target == "customers"
    shade = next(i for i, r in enumerate(p.relationships) if r.source == "shades")
    assert q.index(("rel", shade)) > q.index(("key", "customers"))


@pytest.fixture
def hosted(monkeypatch):
    """The hosted server against the golden workspace (Fabric REST and the SQL endpoint over the shop rows in SQLite)."""
    import golden_support as gs
    import requests
    from fabric_backend import server
    fake = gs.FakeFabric()
    for verb in ("get", "post", "patch"):
        monkeypatch.setattr(requests, verb, getattr(fake, verb))
    odbc = gs.fake_pyodbc()
    monkeypatch.setitem(sys.modules, "pyodbc", odbc)
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "limiter", None)
    fake.odbc = odbc
    return server


SRC = {"workspace": "demo", "source": "demo_lh", "schema": "shop"}


def test_hosted_validate_plan_scopes_resumes_and_says_each_state(hosted):
    full = json.loads(hosted.validate_plan(**SRC, detail="full"))
    n = len(full["keys"]) + len(full["relationships"])
    scoped = json.loads(hosted.validate_plan(**SRC, detail="full", tables=["order_items"]))
    assert [k["table"] for k in scoped["keys"]] == ["order_items"]
    assert {r["source"] for r in scoped["relationships"]} == {"order_items"}
    assert scoped["scope"]["tables"] == ["order_items"]
    first = json.loads(hosted.validate_plan(**SRC, detail="full", max_items=5))
    assert first["time_budget"]["resume_from"] == 5 and first["not_checked_beyond_max_items"] == n - 5
    rest = json.loads(hosted.validate_plan(**SRC, detail="full", resume_from=5))
    assert len(first["keys"]) + len(first["relationships"]) + len(rest["keys"]) + len(rest["relationships"]) == n
    summary = json.loads(hosted.validate_plan(**SRC, max_items=5))
    assert {"tool": "validate_plan", "arguments": {"max_items": n}} in [{k: s[k] for k in ("tool", "arguments")} for s in summary["next_steps"]]
    # five items in check order: 2 keys and 3 links counted here, plus the link R5 counted while planning (ship_to_id)
    assert summary["coverage"]["headline"] == ("7 tables: 2 with a counted key, 4 with a key by name only, 1 without a key; "
                                               "7 links proposed, 4 counted, 4 hold; 0 columns that look like references "
                                               "are unlinked.")
    plan_answer = json.loads(hosted.plan_backend(**SRC))
    assert plan_answer["coverage"]["headline"].startswith("7 tables: ")
    assert "counted and holds" in {r["evidence"] for r in plan_answer["relationships"]}      # R5's ship_to_id, counted


def test_hosted_sql_reads_use_the_call_budget(hosted, monkeypatch):
    """The statement timeout of every SQL read is the connection's own (120 s) cut to what is left of the call."""
    seen = []
    import golden_support as gs
    real = gs._Connection

    class Watching(real):
        def cursor(self):
            seen.append(getattr(self, "timeout", None))
            return super().cursor()
    monkeypatch.setattr(gs, "_Connection", Watching)
    json.loads(hosted.validate_plan(**SRC, max_items=3))
    assert seen and all(t is not None and t <= budget.CALL_SECONDS for t in seen)
