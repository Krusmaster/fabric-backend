"""BL33 (21-22 November 2026, backlog C-31): one count everywhere.

Four modules state the same numbers in different places: `counts.summary` (the plan's one count), `receipt.build`
(a statement per number), `health.daily_rules` (the rules the nightly notebook keeps) and `receipt_notebook.cells`
(the receipt as a notebook the customer runs). On the synthetic `shop`, `shop_faults` and `sap_demo` (small) samples
the plan and validate_plan run once, the same answer goes to all four, and this test holds them to one count:

- the same keys and links, by the same ids, in the same state;
- each number equal everywhere (rows, NULLs, distinct keys, rows with a value, orphans), and the receipt notebook's
  cells, run on BL19's fake SQLite `spark`, print every stated number back as "same";
- every daily rule passes on the rows it was made from, with the counted number as its value;
- an item that is "not counted" (here: cut by max_items) is never a receipt row with a count, a notebook cell that
  runs, or a daily rule.

SQLite only, synthetic rows only; nothing talks to Fabric, Azure or any service.
"""
from __future__ import annotations

import datetime as dt
import re

import pytest

from fabric_backend import counts, evidence, health, receipt, receipt_notebook, sap_demo, shop_faults
from fabric_backend.dialects import DATABRICKS
from fabric_backend.infer import plan as infer_plan
from fabric_backend.platforms import local
from test_bl19_receipt_notebook import FakeSpark, _execute, _run, _sap_db, _shop_db

AT = dt.datetime(2026, 11, 22, 0, 0, tzinfo=dt.timezone.utc)
MARK = {"plan_id": "bl33", "schema_fingerprint": "bl33"}


def _faults_db():
    """shop_faults' rows (the five planted faults) in SQLite, connection kept for the notebook's fake spark."""
    import sqlite3
    con = sqlite3.connect(":memory:")
    con.execute(f"ATTACH DATABASE ':memory:' AS {shop_faults.SCHEMA}")
    for t, (cols, rows) in shop_faults.tables().items():
        con.execute(f"CREATE TABLE {shop_faults.SCHEMA}.[{t}] ({', '.join(f'[{c}]' for c, _ty in cols)})")
        if rows:
            con.executemany(f"INSERT INTO {shop_faults.SCHEMA}.[{t}] VALUES ({','.join('?' * len(cols))})", rows)
    return con


SAMPLES = {
    "shop": (_shop_db, lambda: local.sample_source().schema),
    "shop_faults": (_faults_db, shop_faults.schema),
    "sap_demo": (_sap_db, lambda: sap_demo.sqlite()[0]),
}


def _answer(name: str, max_items: int = 200):
    """The plan and validate_plan's answer, once, and the four modules fed the same answer."""
    db, schema = SAMPLES[name]
    con = db()
    p = infer_plan(schema())
    v = evidence.validate(p, _execute(con), max_items)
    return {"con": con, "plan": p, "validation": v,
            "counts": counts.summary(p, v),
            "receipt": receipt.build(p, v, AT, dialect="sqlite"),
            "spark_receipt": receipt.build(p, v, AT, dialect=DATABRICKS),
            "rules": health.daily_rules(p, v, MARK),
            "cells": receipt_notebook.cells(p, v, AT, f"sample {name}")}


@pytest.fixture(scope="module", params=sorted(SAMPLES))
def full(request):
    return request.param, _answer(request.param)


def _rule_rel_id(rule_id: str) -> str:
    """health's orphans:<source>.<cols>:<target> -> counts' and receipt's rel:<source>.<cols>><target>."""
    body = rule_id.split(":", 1)[1]
    head, target = body.rsplit(":", 1)
    return f"rel:{head}>{target}"


def test_every_sample_counts_something_and_shop_faults_finds_its_faults(full):
    name, a = full
    c = a["counts"]
    assert c["keys"]["total"] and c["links"]["total"], name
    assert c["keys"]["not_counted"] == c["links"]["not_counted"] == 0, c["open"]
    if name == "shop_faults":
        assert c["keys"]["fails"] >= 1 and c["links"]["fails"] >= 1, c["sentence"]


def test_receipt_rows_are_the_counted_items_with_the_same_numbers(full):
    name, a = full
    v, c = a["validation"], a["counts"]
    items = {it["id"]: it for it in c["items"]}
    counted = [r for r in a["receipt"] if r["kind"] in ("key", "link", "extended link")]
    assert {r["item"] for r in counted} == {i for i, it in items.items() if it["state"] != "not_counted"}, name
    assert len(counted) == len(items)                     # one receipt row per key and link, no double
    keys_v = {k["table"]: k for k in v["keys"]}
    for r in counted:
        it = items[r["item"]]
        assert r["kind"] == it["kind"], r["item"]
        if r["kind"] == "key":
            k = keys_v[it["table"]]
            assert r["counts"] == {"n": k["rows"], "nulls": k["nulls"], "distinct_keys": k["distinct"]}, r["item"]
            assert counts.key_state(k)[0] == it["state"]
        else:
            e = next(e for e in v["relationships"] if e["source"] == it["source"] and e["target"] == it["target"]
                     and list(e["columns"]) == it["columns"] and ("kind" in e) == (it["kind"] == "extended link"))
            assert r["counts"]["with_value"] == e["rows_with_value"] and r["counts"]["orphans"] == e["orphans"], r["item"]
        assert it["reason"].rstrip(".") in r["sentence"], (r["item"], it["reason"], r["sentence"])


def test_receipt_sql_gives_back_the_counts_it_states(full):
    name, a = full
    run = _execute(a["con"])
    for r in a["receipt"]:
        if not r["sql"]:
            continue
        got = run(r["sql"])[0]
        for k, stated in r["counts"].items():
            now = got.get(k)
            if isinstance(stated, float) or isinstance(now, float):
                assert round(float(now or 0), 2) == round(float(stated), 2), (name, r["item"], k)
            else:
                assert int(now or 0) == int(stated), (name, r["item"], k, now, stated)


def test_receipt_notebook_states_the_receipts_numbers_and_prints_same(full):
    name, a = full
    rows = a["spark_receipt"]
    assert [(r["n"], r["item"], r["counts"]) for r in rows] == [(r["n"], r["item"], r["counts"]) for r in a["receipt"]]
    code = [t for k, t in a["cells"] if k == "code" and t.startswith("krusgraph_check(")]
    assert len(code) == sum(1 for r in rows if r["sql"])
    for r, cell in zip([r for r in rows if r["sql"]], code):
        assert cell.startswith(f"krusgraph_check({r['n']}, ")
        assert cell.endswith(receipt_notebook._counts(r["counts"]) + ")"), r["item"]
    printed, spark = _run(a["cells"], a["con"])
    numbers = [line for line in printed if re.match(r"\d+\. (same|changed): ", line)]
    assert len(numbers) == len(code) == len(spark.statements)
    assert all(". same: " in line for line in numbers), [x for x in numbers if "changed" in x]


def test_daily_rules_are_the_counted_items_and_pass_on_the_same_rows(full):
    name, a = full
    items = {it["id"]: it for it in a["counts"]["items"]}
    v = a["validation"]
    keys_v = {k["table"]: k for k in v["keys"]}
    receipt_counts = {r["item"]: r["counts"] for r in a["receipt"] if r["counts"]}
    spark = FakeSpark(a["con"])
    for rule in a["rules"]["rules"]:
        if rule["kind"] == "key":
            it = items[rule["id"]]
            assert it["state"] == "holds", (name, rule["id"], it)           # only a key that holds is a rule
            k = keys_v[it["table"]]
            assert k["rows"] == k["distinct"] and not k["nulls"]
        elif rule["kind"] == "orphans":
            rid = _rule_rel_id(rule["id"])
            it = items[rid]
            assert it["state"] in ("holds", "fails", "no_rows"), (name, rid, it)
            assert rule["allowed"] == receipt_counts[rid]["orphans"], (name, rid)
        n = spark.sql(rule["sql"]).collect()[0].asDict()["n"]
        assert int(n or 0) <= rule["allowed"], (name, rule["id"], n, rule["allowed"])
        if rule["kind"] == "orphans":
            assert int(n or 0) == rule["allowed"], (name, rule["id"])       # the same number, counted again
    # every key that holds is a rule; a key that does not hold never is
    rule_ids = {r["id"] for r in a["rules"]["rules"]}
    for it in items.values():
        if it["kind"] == "key":
            assert (it["id"] in rule_ids) == (it["state"] == "holds"), (name, it["id"], it["state"])
        elif it["kind"] == "link":
            assert f"orphans:{it['source']}.{'+'.join(it['columns'])}:{it['target']}" in rule_ids, (name, it["id"])
        else:
            assert f"orphans:{it['source']}.{'+'.join(it['columns'])}:{it['target']}" not in rule_ids, (name, it["id"])


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_not_counted_is_never_a_count_a_cell_or_a_rule(name):
    a = _answer(name, max_items=3)
    c = a["counts"]
    nc = {it["id"] for it in c["items"] if it["state"] == "not_counted"}
    assert nc, "max_items=3 leaves items out"
    assert {it["id"] for it in c["open"]} >= nc and not counts.nothing_open(c)
    by_item = {}
    for r in a["receipt"]:
        by_item.setdefault(r["item"], []).append(r)
    for i in nc:
        rows = by_item.get(i, [])
        assert rows and all(r["kind"] == "not counted" and r["sql"] is None and r["counts"] is None for r in rows), (i, rows)
    rule_ids = {r["id"] for r in a["rules"]["rules"]}
    rel_rule_ids = {_rule_rel_id(r) for r in rule_ids if r.startswith("orphans:")}
    assert not (nc & (rule_ids | rel_rule_ids)), nc & (rule_ids | rel_rule_ids)
    assert nc <= {r["id"] for r in a["rules"]["not_rules"]}
    stated = {r["n"] for r in a["spark_receipt"] if r["item"] in nc}
    for kind, text in a["cells"]:
        m = re.match(r"krusgraph_check\((\d+), ", text) if kind == "code" else None
        assert not (m and int(m.group(1)) in stated), text[:80]
    printed, _ = _run(a["cells"], a["con"])
    assert all(". same: " in line for line in printed if re.match(r"\d+\. (same|changed): ", line))
