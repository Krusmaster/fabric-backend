"""The review file (review_plan): keep the plan, the decisions and the checks, read them back, and never let an old
check pass for new evidence after the schema changed. The first product goal of the brief of 26 October 2026: review a
small schema, keep the decisions and reuse them without help. Run on the shop seed in SQLite, so the counts are real."""
import copy
import json

import pytest

from fabric_backend import mcp_server, review, seed, server
from fabric_backend.infer import plan
from fabric_backend.schema import Column, Schema

from test_stdio_server import sqlite_execute

SHIP_TO = {"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}
SHIP_ID = "rel:orders.ship_to_id>addresses"


@pytest.fixture
def shop(monkeypatch):
    """The local server over the seed rows; `use(schema)` swaps the schema the source reports (a changed lakehouse)."""
    execute = sqlite_execute()
    ran = []

    def spy(sql):
        ran.append(sql)
        return execute(sql)
    spy.statement = execute.statement
    monkeypatch.setattr(mcp_server, "_execute_factory", lambda schema: spy)
    monkeypatch.setenv("FABRIC_ODBC", "Driver={ODBC Driver 18 for SQL Server};Server=x.datawarehouse.fabric.microsoft.com;"
                                      "Database=shop_lh;UID=someone;PWD=not-a-real-secret")
    current = {"schema": seed.schema("shop")}
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: current["schema"]))

    def use(s):
        current["schema"] = s
    use.ran = ran
    return use


def _review(**kw) -> dict:
    out = json.loads(mcp_server.review_plan(schema="shop", **kw))
    assert "error" not in out, out
    return out


def _item(rv: dict, item_id: str) -> dict:
    return next(it for it in rv["review"]["items"] if it["id"] == item_id)


def test_the_file_keeps_decisions_and_checks_apart_and_holds_no_values(shop):
    out = _review(keys={"order_items": ["order_id", "line_no"]}, confirmed=[SHIP_TO], validate=True,
                  decisions=[{"item": SHIP_ID, "review": "accepted", "reason": "the seed stores address ids here"},
                             {"item": "rel:audit_log.customer_id>customers", "review": "open", "reason": "is audit_log ours to model?"}])
    rv = out["review"]
    assert rv["format"] == "krusgraph-review" and rv["version"] == 1 and rv["plan_id"].startswith("plan-")
    assert rv["schema_fingerprint"].startswith("sha256:") and set(rv["table_fingerprints"]) == set(seed.SCHEMAS)
    assert out["file_name"] == "krusgraph-review.odbc.shop.json" and out["report_file_name"].endswith(".md")
    ship = _item(out, SHIP_ID)
    assert (ship["rule"], ship["review"], ship["reason"]) == ("confirmed", "accepted", "the seed stores address ids here")
    assert ship["check"]["status"] == "passed" and ship["check"]["result"]["orphans"] == 0 and ship["check"]["checked_at"]
    key = _item(out, "key:order_items")                      # given with keys: accepted, and what the rules alone proposed
    assert key["review"] == "accepted" and key["rule"] == "K1" and key["proposed"] == {"columns": ["order_id", "line_no"], "rule": "K5"}
    assert _item(out, "key:customers")["review"] == "proposed"                  # nobody decided: the check alone is no decision
    assert _item(out, "key:customers")["check"]["status"] == "passed"
    assert {q["about"] for q in rv["open_questions"]} == {"key:audit_log", "rel:audit_log.customer_id>customers"}
    assert rv["arguments"] == {"keys": {"order_items": ["order_id", "line_no"]}, "confirmed": [SHIP_TO]}
    # names, types, rules, decisions and counts: no value from the rows, no part of the connection string
    text = json.dumps(out)
    for table, rows in seed.rows().items():
        for row in rows[:20]:
            for v in row:
                if isinstance(v, str) and len(v) > 3 and not v.isdigit():
                    assert v not in text, (table, v)
    assert "not-a-real-secret" not in text and "UID=" not in text and "datawarehouse" not in text
    assert all(s.lstrip().upper().startswith(("SELECT", "WITH")) for s in shop.ran)                  # read-only


def test_the_same_input_gives_the_same_file(shop):
    a = mcp_server.review_plan(schema="shop", confirmed=[SHIP_TO])
    b = mcp_server.review_plan(schema="shop", confirmed=[SHIP_TO])
    assert a == b and json.loads(a)["review"]["items"][0]["check"] == {"status": "not_checked"}


def test_reading_it_back_applies_the_decisions_and_stales_checks_on_changed_tables(shop):
    first = _review(keys={"order_items": ["order_id", "line_no"]}, confirmed=[SHIP_TO], validate=True,
                    decisions=[{"item": SHIP_ID, "review": "accepted", "reason": "ship-to address"},
                               {"item": "rel:audit_log.customer_id>customers", "review": "rejected", "reason": "log only"}])
    saved = json.dumps(first["review"])                                     # as it would sit in the repository

    # the same schema, read back without passing keys or confirmed again: nothing lost, nothing stale
    again = _review(previous=saved)
    assert _item(again, SHIP_ID)["rule"] == "confirmed" and _item(again, SHIP_ID)["reason"] == "ship-to address"
    assert _item(again, "key:order_items")["rule"] == "K1"
    assert _item(again, "rel:audit_log.customer_id>customers")["review"] == "rejected"
    assert _item(again, "key:orders")["check"] == _item(first, "key:orders")["check"]           # carried, with its own date
    assert again["review"]["plan_id"] == first["review"]["plan_id"]
    assert not any(v for v in again["review"]["since_previous"]["changes"].values() if isinstance(v, list))
    assert any("Rejected" in a and "audit_log" in a for a in again["attention"])

    # the lakehouse changes: orders gets a column, addresses loses customer_id
    changed = copy.deepcopy(seed.schema("shop"))
    changed.tables["orders"].columns.append(Column("channel", "varchar"))
    changed.tables["addresses"].columns = [c for c in changed.tables["addresses"].columns if c.name != "customer_id"]
    shop(changed)
    later = _review(previous=saved)
    ch = later["review"]["since_previous"]["changes"]
    assert {"table": "orders", "column": "channel", "type": "varchar"} in ch["columns_added"]
    assert any(c["table"] == "addresses" and c["column"] == "customer_id" for c in ch["columns_removed"])
    orders_key = _item(later, "key:orders")["check"]
    assert orders_key["status"] == "stale" and orders_key["was"] == "passed" and "orders changed" in orders_key["stale_because"]
    assert _item(later, SHIP_ID)["check"]["status"] == "stale"                 # touches orders and addresses
    assert _item(later, "key:customers")["check"]["status"] == "passed"         # customers did not change
    assert later["review"]["schema_fingerprint"] != first["review"]["schema_fingerprint"]
    assert later["review"]["since_previous"]["decisions_no_longer_in_plan"] == []     # only undecided items left the plan
    assert any(a.startswith("Check is stale") for a in later["attention"])

    # checking again turns stale into fresh evidence
    fresh = _review(previous=saved, validate=True)
    assert _item(fresh, "key:orders")["check"]["status"] == "passed"


def test_a_decision_on_something_that_left_the_plan_is_listed_not_dropped(shop):
    first = _review(decisions=[{"item": "rel:addresses.customer_id>customers", "review": "accepted", "reason": "billing"}])
    changed = copy.deepcopy(seed.schema("shop"))
    changed.tables["addresses"].columns = [c for c in changed.tables["addresses"].columns if c.name != "customer_id"]
    shop(changed)
    later = _review(previous=first["review"])
    assert later["review"]["since_previous"]["decisions_no_longer_in_plan"] == [
        {"id": "rel:addresses.customer_id>customers", "review": "accepted", "reason": "billing"}]
    assert any("no longer matches the plan" in a for a in later["attention"])


def test_an_accepted_key_that_fails_its_check_says_so_first(shop):
    out = _review(keys={"order_items": ["order_id"]}, validate=True,
                  decisions=[{"item": "key:order_items", "review": "accepted", "reason": "one row per order?"}])
    check = _item(out, "key:order_items")["check"]
    assert check["status"] == "failed" and "not unique" in check["verdict"]
    assert out["attention"][0].startswith("Accepted, but the check failed: key of order_items")
    assert "failed" in out["summary"] and "## Needs attention" in out["report"]
    # the single-column key took order_items.order_id -> orders out of the plan; the file says so instead of dropping it
    assert out["review"]["left_out_by_corrections"] == [
        {"id": "rel:order_items.order_id>orders", "rule": "R1", "relationship": "order_items.order_id → orders.order_id"}]
    assert any(a.startswith("Not in the plan after your corrections: order_items.order_id") for a in out["attention"])
    assert "the rules alone: order_id + line_no (K5)" in out["report"]


def test_bad_files_and_unknown_items_answer_bad_input(shop):
    for bad in ("not json", {"format": "something-else"}, {"format": "krusgraph-review", "version": 99},
                {"format": "krusgraph-review", "version": 1, "source": {}, "snapshot": {}, "items": [{"id": "x", "review": "maybe"}]}):
        out = json.loads(mcp_server.review_plan(schema="shop", previous=bad))
        assert out["kind"] == "bad_input" and "review_plan wrote it" in out["hint"], bad
    out = json.loads(mcp_server.review_plan(schema="shop", decisions=[{"item": "rel:ghost.x>y", "review": "accepted"}]))
    assert out["kind"] == "bad_input" and "rel:ghost.x>y" in out["error"]
    out = json.loads(mcp_server.review_plan(schema="shop", decisions=[{"item": "key:orders", "review": "maybe"}]))
    assert out["kind"] == "bad_input"


def test_tables_limits_the_file_to_an_area(shop):
    out = _review(tables=["orders"])
    ids = {it["id"] for it in out["review"]["items"]}
    assert "key:orders" in ids and "rel:orders.customer_id>customers" in ids and "rel:order_items.order_id>orders" in ids
    assert "key:categories" not in ids and "rel:products.category_id>categories" not in ids
    assert out["review"]["scope"] == ["orders"]


def test_the_hosted_tool_writes_the_same_file_for_a_fabric_source(monkeypatch):
    execute = sqlite_execute()
    monkeypatch.setattr(server, "_connected", lambda workspace, source, schema, ctx: (seed.schema("shop"), execute))
    out = json.loads(server.review_plan("demo", "demo_lh", schema="shop", confirmed=[SHIP_TO], validate=True))
    assert out["review"]["source"] == {"platform": "fabric", "workspace": "demo", "source": "demo_lh", "schema": "shop"}
    assert out["file_name"] == "krusgraph-review.demo-lh.shop.json"
    assert _item(out, SHIP_ID)["check"]["status"] == "passed" and "Nothing was created" in out["note"]


def test_review_module_reads_what_it_writes():
    p = plan(seed.schema("shop"), confirmed=[SHIP_TO])
    rv = review.build(p, plan(seed.schema("shop")), {"platform": "test", "schema": "shop"})
    assert review.read(json.dumps(rv)) == rv
    assert review.carried_arguments(rv)["confirmed"] == [SHIP_TO]
    k, c = review.merge_arguments(review.carried_arguments(rv), {"orders": ["order_id"]}, None)
    assert k == {"orders": ["order_id"]} and c == [SHIP_TO]
