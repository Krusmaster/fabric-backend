"""n126, column-level usage: the DAX reference scanner (fabric_backend/dax_refs.py) on a TMDL fixture built for it
(tests/fixtures/dax_refs), on the shop model draft, and in the answers of plan_drift and compare_semantic_model with
Fabric mocked."""
import json
import random
from pathlib import Path

import pytest

from fabric_backend import dax_refs, seed, semantic_model, server
from fabric_backend.graphql import decode, definition
from fabric_backend.infer import plan
from fabric_backend.schema import Schema

FIXTURE = Path(__file__).parent / "fixtures" / "dax_refs"
WS = "11111111-1111-1111-1111-111111111111"
INFO = dict(workspace_id=WS, item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse", schema="shop",
            sql_endpoint="x.datawarehouse.fabric.microsoft.com", sql_db="shop_lh", schemas_enabled=True)


def fixture_parts() -> dict[str, str]:
    return {str(p.relative_to(FIXTURE)).replace("\\", "/"): p.read_text(encoding="utf-8") for p in FIXTURE.rglob("*.tmdl")}


def names(group: list[dict]) -> list[str]:
    return [x["name"] for x in group]


# ------------------------------------------------------------------ the scanner ---------------------------------------

def test_scanner_reads_qualified_quoted_and_bare_references_and_skips_strings_and_comments():
    s = dax_refs.scan("SUMX ( 'Order Lines', 'Order Lines' [qty] * orders[a]]b] ) + [M] // x[y]\n"
                      "-- 'T'[z]\n/* [q] */ + COUNTROWS ( orders ) & \"t[c] and [m]\" & 'It''s'[v]")
    assert s["qualified"] == [("Order Lines", "qty"), ("orders", "a]b"), ("It's", "v")]
    assert s["unqualified"] == ["M"] and s["tables"] == ["Order Lines"] and s["bare"] == ["orders"]
    assert s["strings"] == {"t[c] and [m]"} and s["syntax"] is None and s["dynamic"] == []


def test_scanner_knows_variables_keywords_and_dynamic_functions_and_stops_on_unknown_syntax():
    s = dax_refs.scan("VAR total = [Sales] RETURN IF ( total > 0, total, BLANK () ) + RANKX ( ALL ( t ), [x], , DESC, Dense )")
    assert s["variables"] == {"total"} and s["bare"] == ["total", "total", "t"]
    assert dax_refs.scan("SELECTEDMEASURE () * 2")["dynamic"] == ["SELECTEDMEASURE"]
    assert dax_refs.scan("\"open")["syntax"] == "a string is not closed"
    assert dax_refs.scan("[a")["syntax"] == "a [name] is not closed"
    assert dax_refs.scan("1 /* open")["syntax"] == "a /* comment is not closed"
    assert dax_refs.scan("@param + 1")["syntax"].startswith("the character '@'")
    assert dax_refs.scan("{ 1, 2 }")["makes_columns"] and dax_refs.scan("GENERATESERIES ( 1, 3 )")["makes_columns"]


def test_expressions_are_read_in_all_three_tmdl_forms_with_their_line_breaks():
    e = dax_refs.expressions(fixture_parts())
    assert e[("measure", "Order Lines", "Total Quantity")] == "SUM('Order Lines'[quantity])"
    assert e[("measure", "Order Lines", "Revenue (net)")].splitlines()[0] == "// orders[ship_to_id] is mentioned only in this comment"
    assert e[("measure", "Order Lines", "Avg Price")] == ("/* a block comment: 'Order Lines'[quantity] / [Ghost] */\n"
                                                        "DIVIDE ( [Revenue], [Total Quantity] )")
    assert e[("column", "products", "Price Band")] == 'IF ( [List Price] > 100, "high", "low" )'
    assert ("column", "products", "List Price") not in e                    # a column read from the source has no expression


# ------------------------------------------------------------------ usage on the fixture ------------------------------

def test_direct_and_transitive_users_of_a_column_with_the_path_through_measures():
    u = dax_refs.Model(fixture_parts()).column_usage("Order Lines", "quantity")
    assert u["column"] == "'Order Lines'[quantity]"
    assert names(u["measures"]) == ["Avg Price", "Avg Price Label", "Quantity Unqualified", "Revenue", "Revenue (net)", "Total Quantity"]
    by = {x["name"]: x for x in u["measures"]}
    assert by["Total Quantity"]["direct"] and by["Quantity Unqualified"]["direct"]          # [quantity] inside SUMX('Order Lines', ...)
    assert by["Revenue"]["path"] == ["'Order Lines'[quantity]", "'Order Lines'[Line Amount]", "[Revenue]"]
    assert by["Avg Price Label"]["path"] == ["'Order Lines'[quantity]", "[Total Quantity]", "[Avg Price]", "[Avg Price Label]"]
    assert not by["Avg Price"]["direct"]
    assert u["calculated_columns"] == [{"table": "Order Lines", "name": "Line Amount", "direct": True,
                                        "path": ["'Order Lines'[quantity]", "'Order Lines'[Line Amount]"]}]


def test_quoted_names_and_a_model_column_named_differently_from_its_source():
    m = dax_refs.Model(fixture_parts())
    assert m.source_columns("order_items", "quantity", "shop") == [("Order Lines", "quantity")]
    assert m.source_columns("products", "list_price", "shop") == [("products", "List Price")]
    assert m.source_columns("products", "list_price", "dbo") == []                       # another schema: not this table
    u = m.column_usage("products", "List Price")
    assert u["column"] == "products[List Price]"
    assert names(u["calculated_columns"]) == ["Line Amount", "Price Band"]               # [List Price] on its own table
    assert names(u["measures"]) == ["Avg Price", "Avg Price Label", "Revenue", "Revenue (net)", "Unit Price Sum"]


def test_references_in_strings_and_comments_do_not_count():
    m = dax_refs.Model(fixture_parts())
    ship = m.column_usage("orders", "ship_to_id")
    assert names(ship["measures"]) == ["Orders Shipped"]                    # not Revenue (net), whose comment names it
    product = m.column_usage("Order Lines", "product_id")
    assert product["measures"] == [] and product["calculated_columns"] == []  # named only in a -- comment
    assert product["relationships"] == [{"from": "'Order Lines'[product_id]", "to": "products[product_id]", "active": True}]
    order_id = m.column_usage("Order Lines", "order_id")
    assert "Avg Price Label" not in names(order_id["measures"])              # named only inside a string


def test_what_could_not_be_read_is_reported_and_never_guessed():
    m = dax_refs.Model(fixture_parts())
    u = m.column_usage("Order Lines", "quantity")
    unread = {x["name"]: x["why"] for x in u["could_not_be_read"]}
    assert unread == {
        "Broken String": "a string is not closed",
        "Made Here": "[quantity] may be a column the expression makes itself or a column of the model",
        "Per Measure": "SELECTEDMEASURE() refers to whatever the query puts in context (a dynamic reference)",
        "Per Measure Twice": "depends on [Per Measure], which could not be read",
        "Unknown Measure": "[Ghost Measure]: no measure or column of that name"}
    assert "Made Here" not in names(u["measures"]) and "Per Measure Twice" not in names(u["measures"])
    # [order_id] with two candidate tables: reported for both candidates, counted as a use of neither
    for table in ("Order Lines", "orders"):
        x = m.column_usage(table, "order_id")
        assert "Two Order Ids" not in names(x["measures"])
        assert unread_of(x)["Two Order Ids"] == "[order_id] could be any of 'Order Lines'[order_id], orders[order_id]"
    assert "Two Order Ids" not in unread_of(m.column_usage("Order Lines", "line_no"))    # its ambiguity is about order_id only


def unread_of(u: dict) -> dict:
    return {x["name"]: x["why"] for x in u["could_not_be_read"]}


def test_table_usage_names_the_measures_on_it_and_those_that_use_it():
    u = dax_refs.Model(fixture_parts()).table_usage("orders")
    assert names(u["measures"]) == ["Two Order Ids", "Orders Shipped"]     # FILTER(orders, ...) names the table for certain
    by = {x["name"]: x for x in u["measures"]}
    assert by["Orders Shipped"]["defined_on_the_table"] and "defined_on_the_table" not in by["Two Order Ids"]
    assert by["Two Order Ids"]["path"] == ["orders", "[Two Order Ids]"]
    assert u["relationships"] == [{"from": "'Order Lines'[order_id]", "to": "orders[order_id]", "active": True}]
    assert "Two Order Ids" not in unread_of(u) and "Per Measure" in unread_of(u)


def test_output_is_deterministic_whatever_the_order_of_the_files():
    parts = fixture_parts()
    first = json.dumps(dax_refs.for_source_changes(parts, [{"table": "shop.order_items", "column": "quantity"},
                                                           {"table": "shop.products", "column": "list_price"}],
                                                   [{"table": "shop.orders"}]), sort_keys=False)
    for seed_ in range(5):
        keys = list(parts)
        random.Random(seed_).shuffle(keys)
        shuffled = {k: parts[k] for k in keys}
        again = dax_refs.for_source_changes(shuffled, [{"table": "shop.products", "column": "list_price"},
                                                       {"table": "shop.order_items", "column": "quantity"}],
                                            [{"table": "shop.orders"}])
        assert json.dumps(again, sort_keys=False) == first


def test_on_the_shop_model_draft():
    parts = semantic_model.draft(plan(seed.schema("shop")), INFO, "shop_model")["parts"]
    out = dax_refs.for_source_changes(parts, [{"table": "shop.order_items", "column": "quantity"},
                                              {"table": "shop.products", "column": "list_price"}], [])
    quantity, price = out["columns"]
    assert quantity["source"] == "shop.order_items.quantity" and names(quantity["measures"]) == ["Order amount", "Total quantity"]
    assert price["column"] == "products[list_price]" and names(price["measures"]) == ["Order amount"]
    assert all(not c["could_not_be_read"] for c in out["columns"])          # every draft measure reads with certainty


# ------------------------------------------------------------------ in the tools, Fabric mocked -----------------------

@pytest.fixture
def fabric(monkeypatch):
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": "Lakehouse", "id": "lh-1", "displayName": src,
                                                                             "sql_host": "x", "sql_db": src, "schemas_enabled": True})
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: []))
    return monkeypatch


def _source_without(drop: set[tuple[str, str]]):
    cols = [("shop", t.name, c.name, c.data_type, i) for t in seed.schema("shop") for i, c in enumerate(t.columns, 1)
            if (t.name, c.name) not in drop]
    return classmethod(lambda cls, execute, schema="dbo", with_keys=True: Schema.from_information_schema(cols, schema=schema))


def test_plan_drift_says_which_measures_a_dropped_column_breaks(fabric):
    full = plan(seed.schema("shop"))
    api_body = decode(definition(full, "shop_api", WS, "lh-1", "SqlAnalyticsEndpoint"))
    api_body["datasources"][0]["sourceItemId"] = "lh-1"
    items = [{"id": "api-1", "displayName": "shop_api", "type": "GraphQLApi"},
             {"id": "sm-1", "displayName": "sales_model", "type": "SemanticModel"},
             {"id": "sm-2", "displayName": "secret_model", "type": "SemanticModel"}]
    reads = []

    def parts_of(ws, route, item_id, headers, fmt=None):
        reads.append(item_id)
        if item_id == "sm-1":
            return fixture_parts()
        raise RuntimeError("HTTP 403 Forbidden for the definition")
    fabric.setattr(server, "_workspace_items", lambda ws, headers: items)
    fabric.setattr(server, "_graphql_definition", lambda ws, api_id, headers: api_body)
    fabric.setattr(server, "_item_definition_parts", parts_of)
    fabric.setattr(server, "find_item_by_name", lambda ws, name, headers, types=None: {"id": "api-1"} if name == "shop_api" else None)
    fabric.setattr(server, "source_for", lambda ws, item, headers: ("lh-1", "SqlAnalyticsEndpoint"))
    fabric.setattr(Schema, "from_sql", _source_without({("order_items", "quantity")}))
    out = json.loads(server.plan_drift("Sales", "shop_lh", api="shop_api", schema="shop"))
    assert out["removed_columns"][0] == {"table": "shop.order_items", "column": "quantity", "why": "the API still maps a column the source no longer has"}
    usage = out["column_usage"]
    assert [m["model"] for m in usage["models"]] == ["sales_model"] and reads.count("sm-1") == 2   # lineage, then usage
    col = usage["models"][0]["columns"][0]
    assert col["source"] == "shop.order_items.quantity" and col["column"] == "'Order Lines'[quantity]"
    assert "Revenue" in names(col["measures"]) and "Broken String" in unread_of(col)
    assert usage["note"].startswith("Read from the DAX of measures and calculated columns")


def test_plan_drift_without_a_touched_model_adds_nothing(fabric):
    fabric.setattr(server, "_workspace_items", lambda ws, headers: [])
    full = plan(seed.schema("shop"))
    api_body = decode(definition(full, "shop_api", WS, "lh-1", "SqlAnalyticsEndpoint"))
    fabric.setattr(server, "_graphql_definition", lambda ws, api_id, headers: api_body)
    fabric.setattr(server, "find_item_by_name", lambda ws, name, headers, types=None: {"id": "api-1"})
    fabric.setattr(server, "source_for", lambda ws, item, headers: ("lh-1", "SqlAnalyticsEndpoint"))
    fabric.setattr(Schema, "from_sql", _source_without({("orders", "ship_to_id")}))
    out = json.loads(server.plan_drift("Sales", "shop_lh", api="shop_api", schema="shop"))
    assert out["removed_columns"] and "column_usage" not in out


def test_for_drift_reports_a_model_it_could_not_read():
    edges = [{"table": "orders", "kind": "semantic_model", "object": "m", "id": "sm-9"}]

    def refuse(model_id):
        raise RuntimeError("HTTP 403")
    out = dax_refs.for_drift(edges, {"removed_columns": [{"table": "shop.orders", "column": "ship_to_id"}]}, refuse)
    assert out["models"] == [{"model": "m", "id": "sm-9", "could_not_read_the_model": "RuntimeError: HTTP 403"}]


def test_compare_semantic_model_lists_what_uses_each_column_whose_source_is_gone(fabric):
    fabric.setattr(Schema, "from_sql", _source_without({("products", "list_price")}))
    fabric.setattr(server, "_item_definition_parts", lambda *a, **k: pytest.fail("tmdl given: the model is not read"))
    out = json.loads(server.compare_semantic_model("Sales", "shop_lh", tmdl=fixture_parts(), schema="shop"))
    assert [g["model"] for g in out["tables"]["columns_gone"]] == ["products.List Price"]
    col = out["column_usage"]["columns"][0]
    assert col["source_table"] == "products" and col["column"] == "products[List Price]"
    assert names(col["calculated_columns"]) == ["Line Amount", "Price Band"]
    assert names(col["measures"]) == ["Avg Price", "Avg Price Label", "Revenue", "Revenue (net)", "Unit Price Sum"]
