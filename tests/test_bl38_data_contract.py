"""BL38 (backlog P-29), 23 November 2026: a data contract beside the product, from the counted checks.

On the planted-faults shop (fabric_backend/shop_faults.py, synthetic rows in SQLite) the contract carries the faults as
failing rules with their counts, validates against the ODCS v3.1.0 JSON schema (tests/fixtures/odcs, Apache 2.0, see its
README), writes what was not counted as "declared, not counted", holds no row value, and is the same byte for byte on
two runs."""
import json
from pathlib import Path

import pytest

from fabric_backend import data_contract as dc
from fabric_backend import shop_faults
from fabric_backend.shop_faults import make_plan

yaml = pytest.importorskip("yaml")
jsonschema = pytest.importorskip("jsonschema")
SCHEMA = json.loads((Path(__file__).parent / "fixtures" / "odcs" / "odcs-json-schema-v3.1.0-20251208.json").read_text("utf-8"))
DAY = "2026-11-23"


@pytest.fixture(scope="module")
def faults():
    r = shop_faults.check()
    plan = make_plan(shop_faults.schema())
    return plan, r["validate"], dc.draft(plan, r["validate"], counted_on=DAY)


def _rules(contract):
    return {q["id"]: q for o in contract["schema"] for q in o.get("quality", [])}


def _status(q):
    return {p["property"]: p["value"] for p in q.get("customProperties", [])}


def test_the_planted_faults_are_failing_rules_with_their_counts(faults):
    _plan, _v, c = faults
    rules = _rules(c)
    f1 = rules["key_customers"]                                                           # F1: a repeated customer_id
    assert f1["type"] == "sql" and f1["mustBe"] == 0 and _status(f1) == {"countedValue": 1, "countedOn": DAY, "status": "failed", "rule": "K2"}
    f2 = rules["link_order_items_order_id_orders"]                                        # F2: three lines without an order
    assert _status(f2)["countedValue"] == 3 and _status(f2)["status"] == "failed"
    f4 = rules["link_newsletter_signups_customer_id_customers"]                           # F4: old customer numbers
    assert _status(f4)["countedValue"] == 8 and _status(f4)["status"] == "failed"
    f3 = rules["amount_orders_order_amount_order_items"]                                  # F3: a header amount
    assert f3["type"] == "text" and "sum it per orders row" in f3["description"]
    clean = [q for q in rules.values() if q["type"] == "sql" and _status(q)["status"] == "passed"]
    assert clean and all(_status(q)["countedValue"] == 0 for q in clean)


def test_it_validates_against_the_odcs_schema(faults):
    _plan, _v, c = faults
    doc = yaml.safe_load(dc.to_yaml(c))
    assert doc == c
    errors = list(jsonschema.Draft201909Validator(SCHEMA).iter_errors(doc))
    assert errors == [], [e.message for e in errors[:3]]
    assert doc["apiVersion"] == "v3.1.0" and doc["kind"] == "DataContract" and doc["status"] == "draft"


def test_two_runs_are_byte_equal(faults):
    plan, v, c = faults
    assert dc.to_yaml(dc.draft(plan, v, counted_on=DAY)) == dc.to_yaml(c)


def test_what_was_not_counted_is_declared_never_a_passing_rule(faults):
    plan, v, _c = faults
    v2 = dict(v, keys=[k for k in v["keys"] if k["table"] != "orders"],
              relationships=[{k: x for k, x in r.items() if k != "orphans"} if r["source"] == "orders" else r
                             for r in v["relationships"]])
    rules = _rules(dc.draft(plan, v2, counted_on=DAY))
    assert rules["key_orders"]["type"] == "text" and rules["key_orders"]["description"].startswith(dc.NOT_COUNTED)
    orders_links = [q for i, q in rules.items() if i.startswith("link_orders_")]
    assert orders_links and all(q["type"] == "text" and q["description"].startswith(dc.NOT_COUNTED) for q in orders_links)
    none = _rules(dc.draft(plan, None, counted_on=DAY))
    assert all(q["type"] == "text" for q in none.values())                               # nothing counted, no rule


def test_no_row_value_reaches_the_contract(faults):
    _plan, _v, c = faults
    text = dc.to_yaml(c)
    for value in ("Elbe Sport", "SEK", "EUR", "1001"):
        assert value not in text


def test_the_schema_carries_keys_types_and_foreign_keys(faults):
    _plan, _v, c = faults
    items = next(o for o in c["schema"] if o["name"] == "order_items")
    pk = [(p["name"], p["primaryKeyPosition"]) for p in items["properties"] if p.get("primaryKey")]
    assert pk == [("order_id", 1), ("line_no", 2)]
    assert {"type": "foreignKey", "from": "order_items.order_id", "to": "orders.order_id"} in items["relationships"]


def test_counted_on_must_be_a_date(faults):
    plan, v, _c = faults
    with pytest.raises(ValueError):
        dc.draft(plan, v, counted_on="today")
