"""n105: suggest_relationships drops pairs that certainly give zero matches before the exact join count.

Rules (fabric_backend/graphs.py, _Prefilter): types from families that never compare equal, and number ranges that do
not overlap (one MIN/MAX per column, reused within the call). A pair is kept whenever a type is unknown or a min/max
cannot be read; the exact count decides every pair that is left.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

from fabric_backend import graphs, seed
from fabric_backend.dialects import sqlite_sql
from fabric_backend.infer import plan
from fabric_backend.schema import Schema

GOLDEN = Path(__file__).parent / "golden"


def _source(tables: dict[str, tuple[list[tuple[str, str]], list[tuple]]]):
    """A schema `s` in SQLite with the given (column, type) lists and rows, and an execute that records every statement."""
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS s")
    rows = []
    for name, (cols, data) in tables.items():
        con.execute(f"CREATE TABLE s.[{name}] ({', '.join(f'[{c}]' for c, _ in cols)})")
        if data:
            con.executemany(f"INSERT INTO s.[{name}] VALUES ({','.join('?' * len(cols))})", data)
        rows += [("s", name, c, t, i) for i, (c, t) in enumerate(cols, 1)]
    seen: list[str] = []

    def execute(sql):
        seen.append(sql)
        cur = con.execute(sqlite_sql(sql))
        return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    return Schema.from_information_schema(rows, schema="s"), execute, seen


def _shop_execute():
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS shop")
    import datetime
    for name, ddl in seed.SCHEMAS.items():
        con.execute(f"CREATE TABLE shop.[{name}] ({ddl})")
        data = [tuple(v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v for v in r) for r in seed.rows()[name]]
        con.executemany(f"INSERT INTO shop.[{name}] VALUES ({','.join('?' * len(data[0]))})", data)
    seen: list[str] = []

    def execute(sql):
        seen.append(sql)
        cur = con.execute(sqlite_sql(sql))
        return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    return execute, seen


def _pair(c: dict) -> str:
    return f"{c['source']}.{c['source_cols'][0]} -> {c['target']}.{c['target_cols'][0]}"


# Orders ship to an address (1..10). warehouses are keyed 500..510, so orders.ship_to_id -> warehouses cannot match.
RANGES = {
    "addresses": ([("address_id", "int"), ("city", "varchar")], [(i, f"City {i}") for i in range(1, 11)]),
    "warehouses": ([("warehouse_id", "int"), ("label", "varchar")], [(i, f"W{i}") for i in range(500, 511)]),
    "orders": ([("order_id", "int"), ("ship_to_id", "int")], [(100 + i, 1 + i % 10) for i in range(30)]),
}


def test_the_shop_fixtures_keep_the_same_suggestions_and_count_every_pair(monkeypatch):
    execute, seen = _shop_execute()
    out = graphs.suggest(plan(seed.schema("shop")), execute)
    golden = json.loads((GOLDEN / "engine_shop_rows.json").read_text(encoding="utf-8"))["suggest"]
    assert json.loads(json.dumps(out["candidates"], default=str)) == golden["candidates"]
    assert out["checked_against_data"] == golden["checked_against_data"] == 4
    assert out["join_counts"] == 4 and out["dropped_count"] == 0 and out["dropped"] == []    # every pair has matches here
    # and the same candidates as with the prefilter switched off
    monkeypatch.setattr(graphs._Prefilter, "reason", lambda self, cand: None)
    execute2, _ = _shop_execute()
    assert graphs.suggest(plan(seed.schema("shop")), execute2)["candidates"] == out["candidates"]


def test_non_overlapping_ranges_are_dropped_and_listed_with_the_reason():
    s, execute, seen = _source(RANGES)
    out = graphs.suggest(plan(s), execute)
    pairs = [_pair(c) for c in out["candidates"]]
    assert "orders.ship_to_id -> addresses.address_id" in pairs
    assert "orders.ship_to_id -> warehouses.warehouse_id" not in pairs
    assert out["dropped_count"] == len(out["dropped"]) >= 1
    assert "orders.ship_to_id -> warehouses.warehouse_id: value ranges do not overlap" in out["dropped"]
    joins = [q for q in seen if "LEFT JOIN" in q]
    assert len(joins) == out["join_counts"] == out["checked_against_data"] - out["dropped_count"]
    assert not any("[warehouses]" in q for q in joins)                              # the dropped pair was never counted
    best = next(c for c in out["candidates"] if c["target"] == "addresses")
    assert best["evidence"]["inclusion"] == 1.0                                     # the exact count still decides the rest


def test_one_min_max_query_per_column_reused_across_pairs():
    s, execute, seen = _source(RANGES)
    out = graphs.suggest(plan(s), execute)
    ranges = [q for q in seen if q.startswith("SELECT MIN(")]
    per_column = Counter(q.split(" FROM ")[1] + " " + q.split("MIN(")[1].split(")")[0] for q in ranges)
    assert per_column and set(per_column.values()) == {1}                         # never twice for one column
    assert out["range_queries"] == len(ranges) == len(per_column)
    source_reads = [q for q in ranges if "[orders]" in q and "[ship_to_id]" in q]
    in_pairs = sum(1 for c in out["candidates"] if c["source_cols"] == ["ship_to_id"]) + sum("orders.ship_to_id" in d for d in out["dropped"])
    assert len(source_reads) == 1 and in_pairs >= 2                                 # one read serves every pair of the column


def test_unknown_types_are_kept_and_counted():
    # sql_variant is in no family: the pair is counted although its ranges would not overlap.
    s, execute, seen = _source({
        "warehouses": ([("warehouse_id", "sql_variant"), ("label", "varchar")], [(i, f"W{i}") for i in range(500, 511)]),
        "orders": ([("order_id", "int"), ("warehouse_id_ref", "sql_variant")], [(100 + i, 1 + i % 10) for i in range(30)]),
    })
    out = graphs.suggest(plan(s), execute)
    pair = next(c for c in out["candidates"] if c["target"] == "warehouses")
    assert pair["evidence"]["matched"] == 0 and out["dropped"] == []
    assert not any(q.startswith("SELECT MIN(") for q in seen) and out["range_queries"] == 0


def test_a_min_max_that_cannot_be_read_keeps_the_pair():
    s, execute, seen = _source(RANGES)

    def no_ranges(sql):
        if sql.startswith("SELECT MIN("):
            raise RuntimeError("aggregate refused")
        return execute(sql)
    out = graphs.suggest(plan(s), no_ranges)
    assert out["dropped"] == [] and "orders.ship_to_id -> warehouses.warehouse_id" in [_pair(c) for c in out["candidates"]]
    assert out["join_counts"] == out["checked_against_data"]


def test_incompatible_types_are_dropped_without_a_query(monkeypatch):
    # candidates() itself requires the same type or the same int/text family, so a GUID against an int never reaches the
    # count today; the rule is a guard for a looser ranking. Simulate one here.
    s, execute, seen = _source({
        "batches": ([("batch_id", "int")], [(1,), (2,)]),
        "events": ([("event_id", "int"), ("batch_ref", "uniqueidentifier"), ("happened", "date")], []),
        "flags": ([("flag_id", "bit")], [(1,)]),
    })
    p = plan(s)
    fake = [{"source": "events", "source_cols": ["batch_ref"], "target": "batches", "target_cols": ["batch_id"], "score": 2.0},
            {"source": "events", "source_cols": ["happened"], "target": "flags", "target_cols": ["flag_id"], "score": 1.5},
            {"source": "events", "source_cols": ["event_id"], "target": "batches", "target_cols": ["batch_id"], "score": 1.0}]
    monkeypatch.setattr(graphs, "candidates", lambda plan, limit=50: [dict(c) for c in fake])
    out = graphs.suggest(p, execute)
    assert out["dropped"] == ["events.batch_ref -> batches.batch_id: types never compare equal (uniqueidentifier against int)",
                              "events.happened -> flags.flag_id: types never compare equal (date against bit)"]
    assert [_pair(c) for c in out["candidates"]] == ["events.event_id -> batches.batch_id"]
    assert out["join_counts"] == 1 and out["checked_against_data"] == 3
    assert not any("[batch_ref]" in q or "[happened]" in q for q in seen)             # dropped on the metadata alone
    # text, numbers and dates convert into each other: never dropped on types
    assert not graphs._types_never_match("varchar", "int") and not graphs._types_never_match("datetime", "int")
    assert not graphs._types_never_match(None, "uniqueidentifier") and not graphs._types_never_match("geography", "int")


def test_the_check_budget_never_runs_more_join_counts_than_before():
    s, execute, seen = _source(RANGES)
    out = graphs.suggest(plan(s), execute, check=1)
    assert out["checked_against_data"] == 1 and out["join_counts"] + out["dropped_count"] == 1


def test_without_data_the_answer_has_no_prefilter_keys():
    out = graphs.suggest(plan(seed.schema("shop")))
    assert not {"dropped", "dropped_count", "join_counts", "range_queries"} & set(out)


# n107: the same shape as RANGES with values that cannot occur by chance in an answer (ids, counts, scores).
LEAK = {
    "addresses": ([("address_id", "int"), ("city", "varchar")], [(i, f"City {i}") for i in range(73011, 73021)]),
    "warehouses": ([("warehouse_id", "int"), ("label", "varchar")], [(i, f"W{i}") for i in range(948201, 948212)]),
    "orders": ([("order_id", "int"), ("ship_to_id", "int")], [(610001 + i, 73011 + i % 10) for i in range(30)]),
}
LEAK_MINMAX = ("73011", "73020", "948201", "948211", "610001", "610030")


def test_no_min_or_max_value_anywhere_in_the_suggest_relationships_answer(monkeypatch):
    """n107: Krusgraph's answers give names and counts, not row values. The prefilter reads MIN/MAX per column; neither
    the reason of a dropped pair nor any other part of the tool's answer may carry them."""
    from fabric_backend import mcp_server
    s, execute, seen = _source(LEAK)
    out = graphs.suggest(plan(s), execute)
    assert "orders.ship_to_id -> warehouses.warehouse_id: value ranges do not overlap" in out["dropped"]
    assert out["range_queries"] >= 2 and any("MIN(" in q for q in seen)                # the min/max were read ...
    monkeypatch.setattr(mcp_server, "_execute_factory", lambda schema: _source(LEAK)[1])
    monkeypatch.setattr(mcp_server, "_plan_on", lambda execute, schema, keys=None, confirmed=None: plan(_source(LEAK)[0]))
    tool = mcp_server.suggest_relationships(schema="s")
    assert "value ranges do not overlap" in tool and "dropped before counting" in json.loads(tool)["summary"]
    for text in (json.dumps(out, default=str), tool):                                  # ... and appear nowhere in the answer
        for v in LEAK_MINMAX:
            assert v not in text, v
