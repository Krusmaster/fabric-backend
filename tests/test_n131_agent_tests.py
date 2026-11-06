"""n131: test questions for a data agent, drafted from the checked plan (fabric_backend/agent_tests.py)."""
import json
import re

import pytest

from fabric_backend import agent_tests
from fabric_backend.review import key_id, rel_id
from fabric_backend.seed import rows


@pytest.fixture(scope="module")
def demo():
    d = agent_tests.demo()
    yield d
    d["connection"].close()


def test_deterministic(demo):
    again = agent_tests.demo()
    try:
        assert json.dumps(again["questions"], sort_keys=True) == json.dumps(demo["questions"], sort_keys=True)
        assert agent_tests.questions(demo["plan"], demo["checks"]) == demo["questions"]
    finally:
        again["connection"].close()


def test_ten_to_twenty_with_shape_and_scoring(demo):
    qs = demo["questions"]["questions"]
    assert agent_tests.MIN_QUESTIONS <= len(qs) <= agent_tests.MAX_QUESTIONS
    assert [q["id"] for q in qs] == [f"Q{i:02d}" for i in range(1, len(qs) + 1)]
    for q in qs:
        kind = q["expected"]["kind"]
        assert kind in ("count", "count_per_group", "sum", "sum_per_group")
        assert q["expected"]["compare"] == ("exact match" if kind.startswith("count") else
                                            f"within tolerance ({agent_tests.SUM_TOLERANCE})")
        assert ("group_by" in q["expected"]) == kind.endswith("per_group")
    assert "exact match" in agent_tests.SCORING and agent_tests.SUM_TOLERANCE in agent_tests.SCORING
    assert {"header_amount", "orphan", "many_to_many"} == {q["trap"]["kind"] for q in qs if q["trap"]}


def test_every_trap_uses_a_real_finding(demo):
    checks = demo["checks"]
    orphans = {rel_id(r["source"], r["columns"], r["target"]) for r in checks["relationships"] if r["orphans"] > 0}
    not_unique = {key_id(k["table"]) for k in checks["keys"] if not k["verdict"].startswith("unique")}
    many = {rel_id(r["source"], r["columns"], r["target"]) for r in checks["relationships"]
            if key_id(r["target"]) in not_unique}
    repeated = {rel_id(f["line"], f["line_columns"], f["header"]) for f in checks["amount_levels"]["findings"]
                if f["rows_per_header"]["max_lines"] > 1}
    real = {"orphan": orphans, "many_to_many": many, "header_amount": repeated}
    traps = [q["trap"] for q in demo["questions"]["questions"] if q["trap"]]
    assert traps
    for t in traps:
        assert t["finding"] in real[t["kind"]], t
    assert orphans == {"rel:order_items.product_id>products"}
    assert many == {"rel:products.category_id>categories"}


def test_sql_joins_only_over_checked_paths_and_runs(demo):
    q = demo["questions"]
    safe = set(q["safe_paths"])
    assert "rel:order_items.product_id>products" not in safe and "rel:products.category_id>categories" not in safe
    for item in q["questions"]:
        joined = re.findall(r"JOIN \[shop\]\.\[(\w+)\]", item["sql"])
        if joined:
            assert item.get("path") or (item["trap"] or {}).get("path")
            path = item.get("path") or item["trap"]["path"]
            assert set(path) <= safe
            src = re.search(r"FROM \[shop\]\.\[(\w+)\]", item["sql"]).group(1)
            assert all(any(p.startswith(f"rel:{a}.") and p.endswith(f">{b}") or p.startswith(f"rel:{b}.") and p.endswith(f">{a}")
                           for p in path) for a, b in [(src, joined[0])])
        if item["trap"]:
            if item["trap"]["kind"] != "header_amount":          # that one is about the amount's level, not the join
                assert item["trap"]["finding"] not in safe
            assert "JOIN" not in item["sql"] or set(item["trap"].get("path", [])) <= safe
        assert item["sql"].lstrip().startswith("SELECT")
        demo["execute"](item["sql"])                                 # every statement runs


def test_the_right_answers_avoid_the_traps(demo):
    ex = demo["execute"]
    by = {}
    for q in demo["questions"]["questions"]:
        if q["trap"]:
            by.setdefault(q["trap"]["kind"], q)
    data = rows()
    total = ex(by["header_amount"]["sql"])[0]["total_order_amount"]
    assert total == pytest.approx(sum(100.0 + o[0] for o in data["orders"]))
    assert ex(by["orphan"]["sql"])[0]["row_count"] == len(data["order_items"]) + 1


def test_no_row_values_in_the_questions(demo):
    text = json.dumps(demo["questions"])
    data = rows()
    for table in ("customers", "categories", "products"):
        for r in data[table]:
            for v in r[1:]:
                if isinstance(v, str) and len(v) > 3:
                    assert v not in text
    assert "Accessories (copy)" not in text
    assert not re.search(r"\b\d+\.\d+\b", text.replace("0.01", "").replace("0.1 %", ""))


def test_a_clean_plan_has_no_traps_and_few_questions_say_so():
    from fabric_backend.infer import plan
    from fabric_backend.seed import schema
    p = plan(schema())
    checks = {"keys": [{"table": t, "columns": c, "verdict": "unique, no NULLs"} for t, (c, _) in p.keys.items()],
              "relationships": [{"source": r.source, "columns": r.source_cols, "target": r.target,
                                 "target_columns": r.target_cols, "orphans": 0, "verdict": "holds for all rows"}
                                for r in p.relationships], "amount_levels": {"findings": []}}
    out = agent_tests.questions(p, checks)
    assert all(q["trap"] is None for q in out["questions"])
    assert len(out["questions"]) >= agent_tests.MIN_QUESTIONS
    none = agent_tests.questions(p, {"keys": [], "relationships": []})
    assert none["questions"] == [] and "fewer than 10" in none["note"]


def test_create_data_agent_returns_them_only_when_asked(demo, monkeypatch):
    from fabric_backend import server
    info = dict(workspace_id="ws-1", item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse", schema="shop")
    monkeypatch.setattr(server, "_source_inputs", lambda *a: (demo["plan"], info))
    monkeypatch.setattr(server, "_connected", lambda *a: (demo["plan"].schema, demo["execute"]))
    plain = json.loads(server.create_data_agent("ws", "shop_lh", name="shop_agent", schema="shop"))
    assert "test_questions" not in plain and plain["dry_run"] is True
    out = json.loads(server.create_data_agent("ws", "shop_lh", name="shop_agent", schema="shop", test_questions=True))
    tq = out["test_questions"]
    assert out["dry_run"] is True and agent_tests.MIN_QUESTIONS <= len(tq["questions"]) <= agent_tests.MAX_QUESTIONS
    assert {q["trap"]["kind"] for q in tq["questions"] if q["trap"]} == {"header_amount", "orphan", "many_to_many"}
    assert tq["scoring"] == agent_tests.SCORING
