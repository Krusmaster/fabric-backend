"""Round n132: validate_plan(profile=...) — a column profile of the checked tables without row values."""
from __future__ import annotations

import json

import pytest

import golden_support as gs
from fabric_backend import evidence, profile, seed, switches
from fabric_backend.infer import PlanInputError, plan


def _shop():
    db = gs.shop_database()
    seen: list[str] = []

    def execute(sql):
        seen.append(sql)
        cur = db.execute(gs._sqlite(sql))
        return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    return execute, seen


def _values():
    """Every value in the shop rows, as text, that could betray a row value (dates, numbers, names)."""
    out = set()
    for rows in seed.rows().values():
        for r in rows:
            for v in r:
                if isinstance(v, str) and len(v) > 2:
                    out.add(v)
                elif hasattr(v, "isoformat"):
                    out.add(v.isoformat()[:10])
    return out


def test_off_by_default_changes_nothing():
    execute, seen = _shop()
    p = plan(seed.schema("shop"))
    out, prof = profile.validate_with_profile(p, execute, 60, False)
    before = len(seen)
    execute2, seen2 = _shop()
    assert prof is None and out == evidence.validate(p, execute2, max_items=60) and before == len(seen2)


def test_one_query_per_checked_table():
    execute, seen = _shop()
    p = plan(seed.schema("shop"))
    out, prof = profile.validate_with_profile(p, execute, 60, True)
    tables = profile.checked_tables(p, out)
    profile_sql = [s for s in seen if "_nulls" in s]
    assert len(profile_sql) == len(tables) == prof["queries"] == len(prof["tables"])
    assert [t["table"] for t in prof["tables"]] == tables
    for sql, t in zip(profile_sql, tables):
        assert sql.endswith(f"FROM [shop].[{t}]")
    by = {t["table"]: t for t in prof["tables"]}
    cols = {c["column"] for c in by["orders"]["columns"]}
    assert cols == {c.name for c in p.schema.tables["orders"].columns}


def test_no_row_values_and_no_min_max_in_the_answer():
    execute, seen = _shop()
    p = plan(seed.schema("shop"))
    _, prof = profile.validate_with_profile(p, execute, 60, {"numbers": [1, 50], "dates": ["2026-01-01", "2026-06-30"]})
    text = json.dumps(prof)
    for v in _values():
        assert v not in text, v
    assert "min_value" not in text and "max_value" not in text
    for t in prof["tables"]:
        for c in t["columns"]:
            assert set(c) <= {"column", "type", "null_share", "distinct", "range", "personal_data"}
            if "range" in c:
                assert set(c["range"]) <= {"against", "min_below", "max_above", "result"}
                assert all(isinstance(c["range"][k], bool) for k in ("min_below", "max_above") if k in c["range"])
    for sql in (s for s in seen if "_nulls" in s):                 # the comparisons happen in the query; MIN/MAX never selected bare
        assert "MIN(" not in sql.replace("CASE WHEN MIN(", "") and "MAX(" not in sql.replace("CASE WHEN MAX(", "")


def test_ranges_compare_without_values():
    execute, _ = _shop()
    p = plan(seed.schema("shop"))
    _, prof = profile.validate_with_profile(p, execute, 60, {"numbers": [1, 50], "dates": ["2026-01-01", "2026-06-30"]})
    by = {(t["table"], c["column"]): c for t in prof["tables"] for c in t["columns"]}
    assert by[("orders", "order_id")]["range"] == {"against": [1, 50], "min_below": False, "max_above": True}
    assert by[("orders", "order_date")]["range"]["against"] == ["2026-01-01", "2026-06-30"]
    assert "dates" not in prof
    _, zero = profile.validate_with_profile(p, _shop()[0], 60, True)
    zb = {(t["table"], c["column"]): c for t in zero["tables"] for c in t["columns"]}
    assert zb[("orders", "order_id")]["range"] == {"against": "zero", "min_below": False, "max_above": True}
    assert "range" not in zb[("orders", "order_date")] and "dates" in zero


def test_masked_columns_get_counts_only():
    execute, seen = _shop()
    p = plan(seed.schema("shop"))
    _, prof = profile.validate_with_profile(p, execute, 60, {"numbers": [0, 1]})
    name = next(c for t in prof["tables"] if t["table"] == "customers" for c in t["columns"] if c["column"] == "name")
    assert name["personal_data"] and "range" not in name and isinstance(name["distinct"], int)
    sql = next(s for s in seen if s.endswith("[customers]"))
    assert "MIN([name])" not in sql and "MAX([name])" not in sql


def test_budget_is_respected():
    p = plan(seed.schema("shop"))
    for max_items in (1, 5, 10, 13, 16, 60, 200):
        execute, seen = _shop()
        out, prof = profile.validate_with_profile(p, execute, max_items, True)
        n = len([s for s in seen if "_nulls" in s])
        used = profile.items_used(out, len(seen) - n)
        tables = profile.checked_tables(p, out)
        assert n == prof["queries"] == min(len(tables), max(0, max_items - used))
        assert used + n <= max(max_items, used)                         # validate's own checks are never cut by the profile
        assert prof.get("not_profiled", []) == tables[n:]
        assert ("how" in prof) == bool(tables[n:])


def test_deterministic():
    p = plan(seed.schema("shop"))
    a = profile.validate_with_profile(p, _shop()[0], 60, True)[1]
    b = profile.validate_with_profile(p, _shop()[0], 60, True)[1]
    assert json.dumps(a) == json.dumps(b)


@pytest.mark.parametrize("bad", ["yes", {"numbers": [5, 1]}, {"numbers": [1]}, {"dates": ["2026-13-01", "2027-01-01"]},
                                 {"other": 1}, {}, {"numbers": ["a", 1]}])
def test_bad_profile_is_bad_input(bad):
    with pytest.raises(PlanInputError):
        profile.options(bad)


def test_a_failed_query_says_its_class_only():
    p = plan(seed.schema("shop"))
    inner, _ = _shop()

    def execute(sql):
        if "_nulls" in sql:
            raise RuntimeError("Conversion failed for value 'Alice'")
        return inner(sql)
    _, prof = profile.validate_with_profile(p, execute, 60, True)
    assert all(t["error"] == "the profile query failed (RuntimeError)" for t in prof["tables"])
    assert "Alice" not in json.dumps(prof)


def test_no_row_values_switch_still_holds(monkeypatch):
    execute, _ = _shop()
    p = plan(seed.schema("shop"))
    _, prof = profile.validate_with_profile(p, execute, 60, True)
    text = json.dumps({"summary": "x", "column_profile": prof})
    on = switches.answer(text, environ={switches.NO_ROW_VALUES: "1"})
    assert json.loads(on)["column_profile"] == prof                     # nothing in it is a row value to remove
    monkeypatch.setenv(switches.NO_ROW_VALUES, "1")
    assert json.loads(switches.answer(text))["column_profile"] == prof


# ------------------------------------------------------------------ through the tools ------------------------------

from tests.test_golden import SRC, fabric  # noqa: E402,F401  (fabric: fixture)


def test_the_hosted_tool_adds_the_profile_and_off_is_unchanged(fabric):
    from fabric_backend import server
    plain = server.validate_plan(**SRC)
    assert "column_profile" not in plain and plain == server.validate_plan(**SRC, profile=False)
    for detail in ("summary", "full"):
        out = json.loads(server.validate_plan(**SRC, detail=detail, profile=True))
        assert out["column_profile"]["tables"] and "column_profile" not in json.loads(server.validate_plan(**SRC, detail=detail))
    bad = json.loads(server.validate_plan(**SRC, profile={"numbers": [3, 1]}))
    assert bad["kind"] == "bad_input"


def test_the_hosted_tool_under_no_row_values(fabric, monkeypatch):
    from fabric_backend import server
    monkeypatch.setenv(switches.NO_ROW_VALUES, "1")
    out = json.loads(switches.answer(server.validate_plan(**SRC, profile=True)))
    assert out["column_profile"]["tables"]
    assert all(isinstance(t["rows"], int) for t in out["column_profile"]["tables"])


def test_a_bad_profile_from_the_local_tool_is_bad_input_before_any_query(monkeypatch):
    from fabric_backend import mcp_server
    monkeypatch.setattr(mcp_server, "_connection", lambda *a, **k: pytest.fail("no connection for a bad profile"))
    out = json.loads(mcp_server.validate_plan(schema="shop", profile={"dates": ["2026", "2027"]}))
    assert out["kind"] == "bad_input" and "profile.dates" in out["error"]
