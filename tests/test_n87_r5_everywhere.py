"""n87, point 2: every tool that builds on the plan sees the same relationships as plan_backend, R5 included
(orders.ship_to_id -> addresses, counted in the rows), through one path in server.py with the same bounds (200 values,
20 counting queries), and nothing kept between calls. Run against the golden doubles: Fabric answered from memory and
an SQL endpoint backed by SQLite with the shop seed (tests/golden_support.py)."""
import json
import time

import pytest

from fabric_backend import infer, server
from tests.test_golden import HOSTED_CALLS, SRC, fabric  # noqa: F401  (fabric: fixture)

SHIP = ("orders", ("ship_to_id",), "addresses")


def _rels(out: dict) -> set[tuple]:
    return {(r["source"], tuple(r.get("source_cols") or r.get("columns")), r["target"]) for r in out["relationships"]}


def test_every_plan_in_a_tool_counts_r5_with_the_same_bounds(fabric, monkeypatch):
    seen = []
    real = server.make_plan

    def spy(s, keys=None, confirmed=None, *a, **k):
        seen.append((k.get("execute") is not None, k.get("sample"), k.get("max_queries")))
        return real(s, keys, confirmed, *a, **k)
    monkeypatch.setattr(server, "make_plan", spy)
    for name, kwargs in HOSTED_CALLS:
        before = len(seen)
        getattr(server, name)(**kwargs)
        for got in seen[before:]:
            assert got == (True, server.R5_SAMPLE, server.R5_MAX_QUERIES), (name, kwargs, got)
    assert len(seen) > 30
    assert (server.R5_SAMPLE, server.R5_MAX_QUERIES) == (200, 20)


def test_validate_review_and_analyze_see_seven_relationships(fabric):
    planned = json.loads(server.plan_backend(**SRC))
    assert len(planned["relationships"]) == 7 and SHIP in _rels(planned)
    checked = json.loads(server.validate_plan(**SRC, detail="full"))
    assert len(checked["relationships"]) == 7 and any(r["source"] == "orders" and r["columns"] == ["ship_to_id"] for r in checked["relationships"])
    review = json.loads(server.review_plan(**SRC))
    assert "7 relationships" in review["summary"] and "ship_to_id" in json.dumps(review["review"])
    graph = json.loads(server.analyze_schema(**SRC))
    assert graph["summary"].startswith("7 tables, 6 with keys, 7 relationships")


def test_the_other_tools_no_longer_say_the_link_is_missing(fabric):
    sug = server.suggest_relationships(**SRC)
    assert not any(c["source"] == "orders" and c["source_cols"] == ["ship_to_id"] for c in json.loads(sug)["candidates"])
    assert "ship_to_id" not in sug
    drift = server.plan_drift(**SRC, api="shop_api")
    assert "no longer supports" not in drift
    cmp = server.compare_semantic_model(**SRC, model="shop_model")
    assert "no rule made this link" not in cmp


def test_join_path_takes_the_direct_relationship(fabric):
    out = json.loads(server.join_path(**SRC, start="orders", end="addresses"))
    safest = out["safest"]
    assert safest["hops"] == 1 and safest["steps"][0]["rule"] == "R5" and safest["steps"][0]["on"] == ["ship_to_id = address_id"]
    assert "customers" not in safest["tables"]


def test_nothing_is_kept_between_calls(fabric, monkeypatch):
    counts = []
    real = infer.infer_from_rows

    def spy(*a, **k):
        counts.append(1)
        return real(*a, **k)
    monkeypatch.setattr(infer, "infer_from_rows", spy)
    server.validate_plan(**SRC)
    server.validate_plan(**SRC)
    assert len(counts) == 2                                                  # counted again on every call


def test_the_time_r5_adds_is_measured(fabric, monkeypatch):
    """With 50 ms per counting query (a slow endpoint), R5 adds at most 20 queries, so about a second; measured here
    against the doubles only."""
    real = server._execute_factory
    queries = []

    def slow(item, token):
        execute = real(item, token)

        def run(sql, *a, **k):
            if "COUNT" in sql.upper() and "DISTINCT" in sql.upper():
                queries.append(sql)
                time.sleep(0.05)
            return execute(sql, *a, **k)
        run.close = getattr(execute, "close", lambda: None)
        return run
    monkeypatch.setattr(server, "_execute_factory", slow)
    start = time.monotonic()
    server.validate_plan(**SRC)
    took = time.monotonic() - start
    assert 0 < len(queries) <= server.R5_MAX_QUERIES and took < 0.05 * server.R5_MAX_QUERIES + 2
