"""Hosted plan_backend and R5 (round n71). On 30 October 2026 the hosted plan_backend did not find orders.ship_to_id ->
addresses although rule R5 existed, because R5 needs rows and only validate_plan and suggest_relationships read them.
plan_backend now runs R5 over its open connection, bounded: the first 200 distinct values of a candidate column, one
counting query per candidate target, at most 20 per call. The other tools plan by names, as before."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_golden import SRC, fabric  # noqa: E402,F401 - the hosted server against the workspace in golden_support


def _counting(log: list[str]) -> list[str]:
    return [q for q in log if "with_value" in q]


def test_plan_backend_finds_ship_to_id_in_the_rows_with_one_bounded_query(fabric):
    from fabric_backend import server
    out = json.loads(server.plan_backend(**SRC))
    r5 = [r for r in out["relationships"] if r["rule"] == "R5"]
    assert [(r["source"], r["source_cols"], r["target"], r["target_cols"]) for r in r5] == [("orders", ["ship_to_id"], "addresses", ["address_id"])]
    assert "counted in the rows: 15 of 15 value(s) of orders.ship_to_id are in addresses.address_id" in r5[0]["note"]
    assert out["counted_in_rows"] == {"sample": 200, "max_queries": 20, "rule": "R5", "candidates": 1, "queries": 1, "not_counted": 0}
    assert "proposed" not in out
    queries = _counting(fabric.odbc.log)
    assert len(queries) == 1 and "SELECT DISTINCT TOP (200) [ship_to_id] FROM [shop].[orders]" in queries[0]
    assert "R5 counted 1 code or role column(s) in the rows: 1 counting query(ies), at most 200 distinct values" in out["summary"]
    # the summary form carries the same two additions
    short = json.loads(server.plan_backend(**SRC, detail="summary"))
    assert "orders.ship_to_id -> addresses [R5]" in " ".join(short["relationships"]) and short["counted_in_rows"]["queries"] == 1


def test_the_other_tools_still_plan_by_names(fabric):
    from fabric_backend import server
    before = len(_counting(fabric.odbc.log))
    draft = json.loads(server.semantic_model_draft(**SRC))
    assert len(_counting(fabric.odbc.log)) == before                     # no counting query: the draft plans by names
    assert "orders.ship_to_id" not in draft["parts"].get("definition/relationships.tmdl", "")
    dd = json.loads(server.data_dictionary(**SRC))
    assert len(_counting(fabric.odbc.log)) == before and "R5" not in dd["summary"]


def test_a_candidate_that_cannot_be_counted_is_proposed_with_the_next_step(fabric, monkeypatch):
    from fabric_backend import server
    monkeypatch.setattr(server, "R5_MAX_QUERIES", 0)
    out = json.loads(server.plan_backend(**SRC))
    assert not any(r["rule"] == "R5" for r in out["relationships"])
    assert len(out["proposed"]) == 1 and out["proposed"][0]["confirmed"] == {"source": "orders", "source_cols": ["ship_to_id"],
                                                                             "target": "addresses", "target_cols": ["address_id"]}
    assert out["proposed"][0]["reason"].startswith("not counted: the counting queries allowed in this call were used up; validate_plan")
    assert out["counted_in_rows"]["queries"] == 0 and out["counted_in_rows"]["not_counted"] == 1
    short = json.loads(server.plan_backend(**SRC, detail="summary"))
    assert short["proposed"] == [f"orders.ship_to_id -> addresses [R5, proposed]: {out['proposed'][0]['reason']}"]
