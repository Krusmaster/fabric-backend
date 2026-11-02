"""n87, point 9: the small errors of the live review of 2 November 2026. query_graphql on an unknown API answered without
kind and hint, and an unknown field came back as Fabric's raw errors; sample_rows with n=500 returned 20 rows without a
word; data_dictionary repeated the same K2 text on every key; suggest_relationships counted rows as "value(s)". Against
the golden doubles and the shop seed."""
import json

import requests

from fabric_backend import graphs, server
from tests.test_answer_query import Resp, shop, shop_plan  # noqa: F401  (shop: fixture)
from tests.test_golden import SRC, fabric  # noqa: F401  (fabric: fixture)
from tests.test_graphs import sqlite_execute


def test_query_graphql_on_an_unknown_api_has_kind_and_hint(shop, monkeypatch):
    out = json.loads(server.query_graphql("Sales", "nope_api", "{ customers { items { customer_id } } }"))
    assert out["kind"] == "not_found" and "list_sources" in out["hint"] and "nope_api" in out["error"]


def test_an_unknown_field_is_said_in_words(shop, monkeypatch):
    raw = {"errors": [{"message": "The field `nickname` does not exist on the type `customers`.", "locations": [{"line": 1, "column": 30}],
                       "extensions": {"code": "HC0002"}}], "data": None}
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp(200, raw))
    out = json.loads(server.query_graphql("Sales", "shop_api", "{ customers { items { nickname } } }"))
    assert out["kind"] == "invalid_query" and "nickname" in out["error"] and "describe_backend" in out["hint"]
    assert out["errors"] == raw["errors"]                                   # what Fabric said stays, under errors


def test_partial_data_with_errors_keeps_the_data(shop, monkeypatch):
    raw = {"errors": [{"message": "Something on one field"}], "data": {"customers": {"items": [{"customer_id": 1}]}}}
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp(200, raw))
    out = json.loads(server.query_graphql("Sales", "shop_api", "{ customers { items { customer_id } } }"))
    assert out["data"] == raw["data"] and out["errors"] == raw["errors"] and "kind" not in out


def test_sample_rows_says_when_it_returns_fewer_rows_than_asked(fabric):
    out = json.loads(server.sample_rows(**SRC, table="customers", n=500))
    assert len(out["rows"]) <= 20 and "500" in out["limited"] and "20" in out["limited"]
    out = json.loads(server.sample_rows(**SRC, table="customers", n=5))
    assert "limited" not in out


def test_data_dictionary_says_each_rule_once(fabric):
    md = server.data_dictionary(**SRC)
    keys = md.split("## Keys", 1)[1].split("## Relationships", 1)[0]
    from fabric_backend.infer import RULES
    for rule, text in RULES.items():
        assert keys.count(text.replace("|", "\\|")) <= 1, rule


def test_suggest_relationships_counts_rows_as_rows():
    p = shop_plan()
    execute = sqlite_execute()

    def broken(sql):                                                         # three rows whose value is not in the key
        rows = execute(sql)
        if rows and "matched" in rows[0] and rows[0]["with_value"]:
            rows[0]["matched"] = rows[0]["with_value"] - 3
        return rows
    out = graphs.suggest(p, broken, check=1)
    verdict = out["candidates"][0]["evidence"]["verdict"]
    assert verdict == "3 row(s) whose value is not in the target key"
