"""n209 (founder's item 2, seen live on the shop sample): the gold views no longer repeat the join keys.

Next to order_items.order_id the view had orders_order_id, products_product_id and customers_customer_id: the joined
table's target key column, equal to the referencing column whenever the join found a row. Those columns are gone; the
rule each join carried (a row whose reference finds nothing is dropped, a NULL reference is kept) is the same predicate
on the joined tables' aliases in the SELECT's WHERE (gold.filter_sql), since a CHECK constraint sees only the view's
output columns. Run on SQLite over the silver tables of the shop seed (the PySpark run is in test_spark_notebooks.py).
"""
from __future__ import annotations

import json
import re
import sqlite3

from fabric_backend import data_agent, data_flow, databricks_drafts, gold, graphql, ontology, pipeline, seed, semantic_model, silver
from fabric_backend.infer import plan
from fabric_backend.schema import Schema
from silver_cases import GIVEN_KEYS, seed_rows

INFO = dict(workspace_id="ws", item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse", schema="shop", schemas_enabled=True,
            sql_endpoint="x.datawarehouse.fabric.microsoft.com", sql_db="shop_lh", sql_endpoint_id="ep-1")


def shop():
    return plan(seed.schema("shop"), GIVEN_KEYS)


def dropped_names(s: dict) -> set[str]:
    """Every name a joined key column had before n209: `{joined table}_{its join target column}`."""
    return {f"{j['to']}_{c}".lower() for v in s["views"] for j in v["joins"] for c in j["target_cols"]}


def test_no_view_repeats_a_join_key():
    s = gold.spec(shop(), INFO)
    assert {"orders_order_id", "products_product_id", "customers_customer_id", "categories_id"} <= dropped_names(s)
    for v in s["views"]:
        names = [c["as"].lower() for c in v["columns"]]
        for j in v["joins"]:
            for c in j["target_cols"]:
                assert f"{j['to']}_{c}".lower() not in names, (v["name"], j["to"], c)
                assert not any(x["table"] == j["to"] and x["column"].lower() == c.lower() for x in v["columns"])
        assert len(set(names)) == len(names)
        # where each left-out key's value is: the referencing column, followed back through the chain
        for k in v["keys_once"]:
            assert k["same_as"].lower() in names
    items = next(v for v in s["views"] if v["fact"] == "order_items")
    assert {(k["table"], k["column"]): k["same_as"] for k in items["keys_once"]} == {
        ("orders", "order_id"): "order_id", ("products", "product_id"): "product_id",
        ("categories", "id"): "products_category_id", ("customers", "customer_id"): "orders_customer_id"}


def test_every_view_keeps_the_fact_s_own_key_and_reference_columns():
    p = shop()
    s = gold.spec(p, INFO)
    for v in s["views"]:
        fact = v["fact"]
        out = {c["as"] for c in v["columns"] if c["table"] == fact}
        assert set(p.keys.get(fact, ([], ""))[0]) <= out
        for j in v["joins"]:
            if j["from"] == fact:
                assert set(j["source_cols"]) <= out, (v["name"], j["source_cols"])
            else:                                       # a dimension's reference to the next one stays, as table_column
                assert {f"{j['from']}_{c}" for c in j["source_cols"]} <= {c["as"] for c in v["columns"]}
        # every column a constraint names is an output column; every column a join rule names is in a joined table
        outputs = {c["as"] for c in v["columns"]}
        for c in v["constraints"]:
            assert set(re.findall(r"`([^`]+)`", c["check"])) <= outputs
        alias = {"f": fact, **{j["alias"]: j["to"] for j in v["joins"]}}
        for fl in v["filters"]:
            for a, col in fl["ref"] + fl["found"]:
                assert col in p.schema[alias[a]].column_names


def _silver_db(changes=None):
    sim = silver.simulate(silver.spec(shop(), INFO, order_by={"orders": "order_date"}), seed_rows())["silver"]
    for t, rows in (changes or {}).items():
        sim[t] = sim[t] + rows
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS silver")
    for t, rows in sim.items():
        cols = [c.split()[0] for c in seed.SCHEMAS[t].split(", ")]
        con.execute(f"CREATE TABLE silver.`{t}` ({', '.join('`' + c + '`' for c in cols)})")
        con.executemany(f"INSERT INTO silver.`{t}` VALUES ({', '.join('?' * len(cols))})",
                        [tuple(str(v) if hasattr(v, "isoformat") else v for v in (r.get(c) for c in cols)) for r in rows])
    con.row_factory = sqlite3.Row
    return sim, lambda sql: [dict(r) for r in con.execute(sql).fetchall()]


def test_the_orphan_rule_still_drops_a_reference_that_finds_nothing_and_keeps_a_null_one():
    s = gold.spec(shop(), INFO)
    items = next(v for v in s["views"] if v["fact"] == "order_items")
    sim, execute = _silver_db()
    clean = gold.run_select(items, s, execute)
    assert len(clean) == len(sim["order_items"])
    assert list(clean[0]) == [c["as"] for c in items["columns"]]
    order_ids = {r["order_id"] for r in sim["orders"]}
    some_order = min(order_ids)
    lost_order = max(order_ids) + 1000
    # a product that does not exist and an order that does not exist: both dropped; a NULL product is kept
    extra = {"order_items": [{"order_id": some_order, "line_no": 91, "product_id": 999999, "quantity": 1.0},
                             {"order_id": lost_order, "line_no": 92, "product_id": sim["products"][0]["product_id"], "quantity": 1.0},
                             {"order_id": some_order, "line_no": 93, "product_id": None, "quantity": 2.0}]}
    sim, execute = _silver_db(extra)
    rows = gold.run_select(items, s, execute)
    lines = {(r["order_id"], r["line_no"]) for r in rows}
    assert (some_order, 91) not in lines and (lost_order, 92) not in lines and (some_order, 93) in lines
    assert len(rows) == len(clean) + 1
    kept = next(r for r in rows if (r["order_id"], r["line_no"]) == (some_order, 93))
    assert kept["product_id"] is None and kept["products_name"] is None and kept["orders_customer_id"] is not None
    # two steps out: an order whose customer does not exist drops its lines, an order with no customer keeps them
    cust = {r["customer_id"] for r in sim["customers"]}
    extra = {"orders": [{"order_id": 880001, "customer_id": max(cust) + 1000, "order_date": None, "ship_to_id": None},
                        {"order_id": 880002, "customer_id": None, "order_date": None, "ship_to_id": None}],
             "order_items": [{"order_id": 880001, "line_no": 1, "product_id": sim["products"][0]["product_id"], "quantity": 1.0},
                             {"order_id": 880002, "line_no": 1, "product_id": sim["products"][0]["product_id"], "quantity": 1.0}]}
    sim, execute = _silver_db(extra)
    ids = {r["order_id"] for r in gold.run_select(items, s, execute)}
    assert 880001 not in ids and 880002 in ids
    orders = next(v for v in s["views"] if v["fact"] == "orders")
    ids = {r["order_id"] for r in gold.run_select(orders, s, execute)}
    assert 880001 not in ids and 880002 in ids


def test_composite_keys_chains_and_name_collisions():
    """A composite reference, a key column reached through a dimension whose own key column is left out, and a fact
    column that used to collide with a joined one."""
    rows = [("s", "lines", "order_no", "int", 1), ("s", "lines", "region", "varchar", 2), ("s", "lines", "line", "int", 3),
            ("s", "lines", "heads_note", "varchar", 4), ("s", "lines", "qty", "int", 5),
            ("s", "heads", "order_no", "int", 1), ("s", "heads", "region", "varchar", 2), ("s", "heads", "note", "varchar", 3),
            ("s", "extras", "ono", "int", 1), ("s", "extras", "reg", "varchar", 2), ("s", "extras", "flag", "varchar", 3)]
    sch = Schema.from_information_schema(rows, schema="s")
    p = plan(sch, {"lines": ["order_no", "region", "line"], "heads": ["order_no", "region"], "extras": ["ono", "reg"]},
             [{"source": "lines", "source_cols": ["order_no", "region"], "target": "heads", "target_cols": ["order_no", "region"]},
              {"source": "heads", "source_cols": ["order_no", "region"], "target": "extras", "target_cols": ["ono", "reg"]}])
    s = gold.spec(p, dict(INFO, schema="s"))
    v = next(v for v in s["views"] if v["fact"] == "lines")
    names = [c["as"] for c in v["columns"]]
    assert [(j["from"], j["to"]) for j in v["joins"]] == [("lines", "heads"), ("heads", "extras")]
    assert names == ["order_no", "region", "line", "heads_note", "qty", "heads_note_2", "extras_flag"]
    assert {(k["table"], k["column"]): k["same_as"] for k in v["keys_once"]} == {
        ("heads", "order_no"): "order_no", ("heads", "region"): "region", ("extras", "ono"): "order_no", ("extras", "reg"): "region"}
    sql = gold.select_sql(v, "silver")
    # the second join still joins on the first dimension's (not output) key columns, and its rule names them by alias
    assert "LEFT JOIN `silver`.`extras` AS d2 ON d1.`order_no` = d2.`ono` AND d1.`region` = d2.`reg`" in sql
    assert "((d1.`order_no` IS NULL OR d1.`region` IS NULL) OR (d2.`ono` IS NOT NULL AND d2.`reg` IS NOT NULL))" in sql


def test_what_reads_gold_names_no_dropped_column():
    p = shop()
    s = gold.spec(p, INFO)
    dropped = dropped_names(s)

    def names_none(text: str, where: str):
        hits = sorted(n for n in dropped if re.search(rf"\b{re.escape(n)}\b", text, re.I))
        assert not hits, (where, hits)
    names_none("\n".join(st["sql"] for st in gold.statements(s)), "gold statements")
    names_none(gold.notebook_source(s), "gold notebook")
    check = pipeline.check_spec(p, silver.spec(p, INFO), s)
    outputs = {v["name"].split(".", 1)[1]: {c["as"] for c in v["columns"]} for v in s["views"]}
    for v in check["views"]:
        assert {x["in_view"] for x in v["sums"]} <= outputs[v["view"]]
    names_none(json.dumps(check), "check spec")
    flow = data_flow.flow(p, INFO, {"silver_notebook": "n1", "gold_views": "n2"})
    names_none(json.dumps(flow), "data flow")
    names_none(json.dumps(databricks_drafts.pipeline(p, "main")["files"]), "databricks")
    agent = data_agent.draft(p, INFO, "agent", "shop", layers=[{"layer": "gold", "schema": "gold",
                                                                 "tables": [v["name"].split(".", 1)[1] for v in s["views"]]}])
    gold_layer = next(x for x in agent["layers"] if x["layer"] == "gold")
    assert "Each join key appears once" in gold_layer["instructions"]
    names_none(json.dumps({k: v for k, v in gold_layer.items() if k != "instructions"}), "agent gold layer")
    names_none(gold_layer["instructions"].replace("not orders_order_id", ""), "agent gold instructions")
    # the semantic model, the API and the ontology are built on the tables themselves, never on a dropped gold column
    names_none(json.dumps(semantic_model.draft(p, INFO, "model"), default=str), "semantic model")
    names_none(json.dumps(graphql.definition(p, "api", "ws", "ep-1")), "graphql")
    names_none(ontology.ontology_ttl(p, "onto", "shop"), "ontology")
