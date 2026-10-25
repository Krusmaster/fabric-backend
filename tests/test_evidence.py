"""validate_plan / sample_rows / describe_backend building blocks, without a database."""
import base64
import json

from fabric_backend import evidence as ev
from fabric_backend.graphql import definition
from fabric_backend.infer import plan as make_plan
from fabric_backend.schema import Schema
from fabric_backend.seed import SCHEMAS, rows
from fabric_backend.server import describe_definition


def shop_plan(keys=None, confirmed=None):
    cols = [("shop", t, c.split(" ")[0], c.split(" ")[1].lower(), i + 1)
            for t, s in SCHEMAS.items() for i, c in enumerate(s.split(", "))]
    return make_plan(Schema.from_information_schema(cols, schema="shop"), keys, confirmed)


def python_execute():
    """Answer the counting queries from the synthetic rows, by recognising which table/columns they ask about."""
    data = rows()
    names = {t: [c.split(" ")[0] for c in s.split(", ")] for t, s in SCHEMAS.items()}

    def col(table, c):
        i = names[table].index(c)
        return [r[i] for r in data[table]]

    def execute(sql):
        p = shop_plan(keys={"order_items": ["order_id", "line_no"]})
        for t, (cs, _) in p.keys.items():
            if sql == ev.key_sql("shop", t, cs):
                vals = list(zip(*[col(t, c) for c in cs]))
                nulls = sum(1 for v in vals if any(x is None for x in v))
                return [{"n": len(vals), "nulls": nulls, "distinct_keys": len({v for v in vals if None not in v})}]
        for r in p.relationships:
            if sql == ev.relationship_sql("shop", r.source, r.source_cols, r.target, r.target_cols):
                src = [v for v in zip(*[col(r.source, c) for c in r.source_cols]) if None not in v]
                tgt = set(zip(*[col(r.target, c) for c in r.target_cols]))
                return [{"with_value": len(src), "orphans": sum(1 for v in src if v not in tgt)}]
        raise AssertionError(sql)
    return execute


def test_synthetic_shop_keys_are_unique_and_relationships_hold():
    out = ev.validate(shop_plan(keys={"order_items": ["order_id", "line_no"]}), python_execute())
    assert out["summary"].startswith("6 of 6 keys unique, 6 of 6 relationships hold")
    assert all(k["verdict"].startswith("unique") for k in out["keys"])
    orders = next(k for k in out["keys"] if k["table"] == "orders")
    assert orders["rows"] == 60 and orders["distinct"] == 60


def test_verdicts_for_bad_data():
    assert ev.key_verdict(10, 0, 8) == "not unique: 2 duplicate rows (8 distinct values in 10 rows)"
    assert ev.key_verdict(10, 1, 9).startswith("not a key: 1 of 10 rows have a NULL")
    assert ev.relationship_verdict(50, 5) == "5 of 50 rows (10.0%) point at nothing"


def test_validate_respects_the_budget():
    calls = []

    def execute(sql):
        calls.append(sql)
        return [{"n": 1, "nulls": 0, "distinct_keys": 1, "with_value": 1, "orphans": 0}]
    out = ev.validate(shop_plan(), execute, max_items=3)
    assert len(calls) == 3 and "checked 3 of" in out["summary"]


def test_identifiers_are_quoted():
    sql = ev.sample_sql("shop", "we]ird", ["a]b"], 5)
    assert "[we]]ird]" in sql and "[a]]b]" in sql and sql.startswith("SELECT TOP (5)")


def test_composite_key_is_suggested_for_order_items():
    p = shop_plan()
    assert p.keys["order_items"] == (["order_id", "line_no"], "K5")           # rule K5 now infers it; nothing left to suggest
    assert ev.suggest_composite_keys(p) == []
    del p.keys["order_items"]                                                  # a plan without it: the suggestion is the same key
    s = ev.suggest_composite_keys(p)
    assert {"table": "order_items", "columns": ["order_id", "line_no"]}.items() <= s[0].items()
    assert s[0]["use"] == {"order_items": ["order_id", "line_no"]} and len(s) == 1   # not product_id + line_no
    assert ev.suggest_composite_keys(shop_plan(keys={"order_items": ["order_id", "line_no"]})) == []


def test_history_tables_get_a_reference_plus_start_date_suggestion():
    from fabric_backend.infer import plan
    from fabric_backend.schema import Schema
    s = Schema.from_information_schema([
        ("dbo", "products", "product_id", "int", 1), ("dbo", "products", "name", "varchar", 2),
        ("dbo", "product_cost_history", "product_id", "int", 1), ("dbo", "product_cost_history", "start_date", "date", 2),
        ("dbo", "product_cost_history", "end_date", "date", 3), ("dbo", "product_cost_history", "cost", "decimal", 4),
    ])
    p = plan(s)
    assert "product_cost_history" in p.keyless                                  # K4/K5 do not guess history keys
    s = ev.suggest_composite_keys(p)
    assert len(s) == 1 and s[0]["use"] == {"product_cost_history": ["product_id", "start_date"]} and "validity" in s[0]["why"]


def test_describe_definition_reads_back_what_create_backend_writes():
    p = shop_plan(keys={"order_items": ["order_id", "line_no"]},
                  confirmed=[{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}])
    env = definition(p, "shop_api", "ws", "src")
    body = json.loads(base64.b64decode(env["definition"]["parts"][0]["payload"]))
    d = describe_definition(body)
    orders = next(t for t in d["types"] if t["type"] == "orders")
    assert orders["query_field"] == "orders"
    assert next(t for t in d["types"] if t["type"] == "audit_log")["query_field"] == "audit_logs"
    assert {"ship_to", "customer", "order_items"} <= {r["field"] for r in orders["relationships"]}
    assert orders["by_key"] and not orders["writable"]
