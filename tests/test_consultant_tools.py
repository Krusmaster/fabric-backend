"""semantic_model_draft, join_path, data_dictionary, dbt_schema and plan_drift: the modules on the shop schema and on
the benchmark fixtures, then the thin MCP tools with Fabric mocked."""
import json
import re

import pytest

from fabric_backend import dbt, dictionary, drift, paths, seed, semantic_model, server
from fabric_backend.graphql import decode, definition
from fabric_backend.infer import PlanInputError, plan
from fabric_backend.schema import Schema
from test_inference_quality import load, names_only

INFO = dict(workspace_id="ws", item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse", schema="shop",
            sql_endpoint="x.datawarehouse.fabric.microsoft.com", sql_db="shop_lh")


@pytest.fixture
def shop_plan():
    return plan(seed.schema("shop"))


@pytest.fixture
def tpch():
    return plan(names_only(load("tpch")))


@pytest.fixture
def sakila():
    return plan(names_only(load("sakila")))


# ------------------------------------------------------------------ TMDL -------------------------

KNOWN = {"database", "model", "table", "column", "partition", "source", "expression", "relationship", "annotation", "ref",
         "dataAccessOptions", "legacyRedirects", "returnErrorValuesAsNull"}


def check_tmdl(text: str) -> None:
    """The shape every sample definition has: tab indentation, each nested line under a parent one level up, object
    lines start with a known keyword, property lines are `name: value` or a bare flag."""
    depth_prev, in_block = 0, False
    for line in text.splitlines():
        if not line.strip():
            continue
        assert not line.startswith(" "), f"space indentation: {line!r}"
        depth = len(line) - len(line.lstrip("\t"))
        if depth <= 1:
            in_block = False
        assert depth <= depth_prev + 1 or in_block, f"indented more than one level: {line!r}"   # M code after `expression X =` sits two levels in
        body = line.strip()
        if depth == 0:
            assert body.split()[0] in KNOWN or body.startswith("//"), body
        if body.endswith(" ="):
            in_block = True
        depth_prev = depth


def test_semantic_model_tmdl_files_tables_partitions_and_relationships(shop_plan):
    out = semantic_model.draft(shop_plan, INFO, "shop_model")
    parts = out["parts"]
    assert {"definition/database.tmdl", "definition/model.tmdl", "definition/expressions.tmdl", "definition/relationships.tmdl",
            "definition.pbism", "README.generated.md"} <= set(parts)
    assert {p for p in parts if p.startswith("definition/tables/")} == {f"definition/tables/{t}.tmdl" for t in
            ("customers", "categories", "products", "addresses", "orders", "order_items", "audit_log")}
    for path, text in parts.items():
        if path.endswith(".tmdl"):
            check_tmdl(text)
    assert "compatibilityLevel: 1604" in parts["definition/database.tmdl"]
    model = parts["definition/model.tmdl"]
    assert model.startswith("model Model\n\tculture: en-US") and model.count("\nref table ") == 7
    assert 'Sql.Database("x.datawarehouse.fabric.microsoft.com", "shop_lh")' in parts["definition/expressions.tmdl"]
    assert "annotation PBI_IncludeFutureArtifacts = False" in parts["definition/expressions.tmdl"]
    orders = parts["definition/tables/orders.tmdl"]
    assert orders.startswith("table orders\n\tlineageTag: ") and "\tsourceLineageTag: [shop].[orders]" in orders
    assert "\tcolumn order_id\n\t\tdataType: int64\n\t\tisKey\n" in orders                       # single-column key
    assert "\tpartition orders = entity\n\t\tmode: directLake\n\t\tsource\n\t\t\tentityName: orders\n\t\t\tschemaName: shop\n\t\t\texpressionSource: DatabaseQuery" in orders
    assert "isKey" not in parts["definition/tables/order_items.tmdl"]                               # composite key: no isKey
    assert "isKey" not in parts["definition/tables/audit_log.tmdl"]
    rels = parts["definition/relationships.tmdl"]
    assert rels.count("\nrelationship ") + rels.startswith("relationship ") == 6 and "isActive: false" not in rels
    assert "\tfromColumn: orders.customer_id\n\ttoColumn: customers.customer_id" in rels
    assert "\tfromColumn: audit_log.customer_id" in rels and "toColumn: audit_log." not in rels    # keyless: nothing points at it
    assert "toColumn: order_items." not in rels                                                      # composite key: nothing points at it
    assert out["summary"]["relationships_active"] == 6 and out["summary"]["keyless"] == ["audit_log"]
    readme = parts["README.generated.md"]
    assert "Direct Lake" in readme and "audit_log" in readme and "order_items" in readme and "validate_plan" in readme
    assert json.loads(parts["definition.pbism"])["version"] == "4.2"
    # the same plan gives the same files (lineage tags are deterministic)
    assert semantic_model.draft(shop_plan, INFO, "shop_model")["parts"] == parts


def test_semantic_model_quotes_names_maps_types_and_omits_schema_for_plain_lakehouses():
    s = Schema.from_information_schema([
        ("dbo", "Order Details", "OrderID", "int", 1), ("dbo", "Order Details", "Unit Price", "money", 2), ("dbo", "Order Details", "Shipped", "bit", 3),
        ("dbo", "Order Details", "When", "datetime2", 4), ("dbo", "Order Details", "Blob", "varbinary", 5), ("dbo", "Order Details", "Ratio", "float", 6),
        ("dbo", "Orders", "OrderID", "int", 1), ("dbo", "Orders", "Note", "nvarchar", 2)])
    out = semantic_model.draft(plan(s), {**INFO, "schema": "dbo", "item_kind": "Lakehouse"}, "m")
    t = out["parts"]["definition/tables/Order Details.tmdl"]
    assert t.startswith("table 'Order Details'") and "\tcolumn 'Unit Price'\n\t\tdataType: decimal" in t
    assert "dataType: boolean" in t and "dataType: dateTime" in t and "dataType: binary" in t and "dataType: double" in t
    assert "\t\t\tentityName: Order Details\n\t\t\texpressionSource: DatabaseQuery" in t and "schemaName" not in t
    assert "ref table 'Order Details'" in out["parts"]["definition/model.tmdl"]
    assert "fromColumn: 'Order Details'.OrderID\n\ttoColumn: Orders.OrderID" in out["parts"]["definition/relationships.tmdl"]
    assert semantic_model.data_type("numeric(18,2)") == "decimal" and semantic_model.data_type("string") == "string"
    assert semantic_model.data_type("DATE") == "dateTime" and semantic_model.data_type("bigint") == "int64"
    check_tmdl(t)
    # a lakehouse created with schemas (REST: properties.defaultSchema) keeps schemaName, dbo included
    out = semantic_model.draft(plan(s), {**INFO, "schema": "dbo", "item_kind": "Lakehouse", "schemas_enabled": True}, "m")
    assert "\t\t\tschemaName: dbo\n" in out["parts"]["definition/tables/Orders.tmdl"]
    # a Fabric SQL database's database name (properties.databaseName, with its suffix) is what the expression opens
    out = semantic_model.draft(plan(s), {**INFO, "item_kind": "SQLDatabase", "sql_db": "shopdb-1234-abcd"}, "m")
    assert 'Sql.Database("x.datawarehouse.fabric.microsoft.com", "shopdb-1234-abcd")' in out["parts"]["definition/expressions.tmdl"]


def test_semantic_model_makes_second_paths_inactive_and_skips_composite_relationships(tpch, sakila):
    out = semantic_model.draft(tpch, {**INFO, "schema": "dbo", "item_kind": "Warehouse"}, "tpch")
    s = out["summary"]
    assert s["tables"] == 8 and s["relationships_not_expressible"] == 1          # LINEITEM (L_PARTKEY, L_SUPPKEY) -> PARTSUPP
    assert s["relationships_active"] + s["relationships_inactive"] == 9
    inactive = {(i["source"], i["target"]) for i in s["inactive"]}
    # the active set maximises confidence: every R1 link stays, the two R2 links that would close cycles go inactive
    assert inactive == {("ORDERS", "CUSTOMER"), ("PARTSUPP", "SUPPLIER")}
    assert all("cycle" in i["why"] or "already active" in i["why"] for i in s["inactive"])
    rules = {(r.source, r.target): r.rule for r in tpch.relationships}
    assert all(rules[pair] == "R2" for pair in inactive)
    rels = out["parts"]["definition/relationships.tmdl"]
    assert rels.count("isActive: false") == len(inactive) and "PARTSUPP" in out["parts"]["README.generated.md"]
    assert "schemaName: dbo" in out["parts"]["definition/tables/LINEITEM.tmdl"]  # a warehouse keeps the schema
    check_tmdl(rels)
    # Sakila: film -> language twice (language_id, original_language_id): one active, one inactive, same pair
    out = semantic_model.draft(sakila, {**INFO, "schema": "dbo", "item_kind": "Lakehouse"}, "sakila")
    pair = [i for i in out["summary"]["inactive"] if i["target"] == "language"]
    assert len(pair) == 1 and pair[0]["columns"] == ["original_language_id"] and "already active" in pair[0]["why"]


def test_semantic_model_tables_filter(shop_plan):
    out = semantic_model.draft(shop_plan, INFO, "m", tables=["orders", "customers"])
    assert {p for p in out["parts"] if p.startswith("definition/tables/")} == {"definition/tables/orders.tmdl", "definition/tables/customers.tmdl"}
    assert out["summary"]["relationships_active"] == 1


# ------------------------------------------------------------------ join paths --------------------

def test_join_path_customers_to_categories(shop_plan):
    out = paths.join_path(shop_plan, "customers", "categories")
    assert len(out["paths"]) == 1
    p = out["paths"][0]
    assert p["tables"] == ["customers", "orders", "order_items", "products", "categories"] and p["hops"] == 4
    assert [s["rule"] for s in p["steps"]] == ["R1"] * 4
    assert [s["direction"] for s in p["steps"]] == ["one-to-many", "one-to-many", "many-to-one", "many-to-one"]
    sql = p["sql"]
    assert sql.startswith("SELECT TOP (100) t0.[customer_id] AS [customers_customer_id], t4.[id], t4.[name]\nFROM [shop].[customers] AS t0\n")
    assert "JOIN [shop].[orders] AS t1 ON t0.[customer_id] = t1.[customer_id]" in sql
    assert sql.rstrip().endswith("JOIN [shop].[categories] AS t4 ON t3.[category_id] = t4.[id]")
    assert "note" not in out
    # case does not matter; the same table twice is answered, not searched
    assert paths.join_path(shop_plan, "Customers", "CATEGORIES")["paths"][0]["hops"] == 4
    assert paths.join_path(shop_plan, "orders", "orders")["paths"] == []
    with pytest.raises(PlanInputError):
        paths.join_path(shop_plan, "orders", "ghost")


def test_join_path_lists_equally_short_paths_and_runs_on_sqlite(tpch, shop_plan):
    out = paths.join_path(tpch, "CUSTOMER", "PART")
    assert out["paths"] and all(p["hops"] == out["paths"][0]["hops"] for p in out["paths"])
    assert out["paths"][0]["hops"] == 3                                         # CUSTOMER - ORDERS - LINEITEM - PART
    assert out["paths"][0]["tables"][1:3] == ["ORDERS", "LINEITEM"]
    # the generated SQL is valid: run the shop one against the seed rows in SQLite (TOP and brackets rewritten)
    import datetime
    import sqlite3
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS shop")
    for name, ddl in seed.SCHEMAS.items():
        con.execute(f"CREATE TABLE shop.[{name}] ({ddl})")
        data = [tuple(v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v for v in r) for r in seed.rows()[name]]
        con.executemany(f"INSERT INTO shop.[{name}] VALUES ({','.join('?' * len(data[0]))})", data)
    sql = paths.join_path(shop_plan, "customers", "categories")["paths"][0]["sql"]
    rows = con.execute(re.sub(r"SELECT TOP \((\d+)\)", "SELECT", sql) + " LIMIT 100").fetchall()
    assert rows and len(rows[0]) == 3


def test_join_path_without_a_path_suggests_the_missing_relationship():
    s = Schema.from_information_schema([
        ("dbo", "orders", "order_id", "int", 1), ("dbo", "orders", "ship_to_id", "int", 2),
        ("dbo", "addresses", "address_id", "int", 1), ("dbo", "addresses", "city", "varchar", 2),
        ("dbo", "notes", "note_id", "varchar", 1), ("dbo", "notes", "text", "varchar", 2),
        ("dbo", "shippers", "shipper_id", "int", 1), ("dbo", "shippers", "name", "varchar", 2)])
    out = paths.join_path(plan(s), "orders", "addresses")
    assert out["paths"] == [] and "no chain of relationships" in out["note"]
    best = out["suggestions"][0]
    assert best["confirmed"] == {"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}
    assert "ship_to_id" in best["why"] and best["strength"] == "type only"
    assert [s["target"] for s in out["suggestions"]] == ["addresses"]                               # only the end table's side is searched
    assert [s["target"] for s in paths.join_path(plan(s), "orders", "shippers")["suggestions"]] == ["shippers"]
    assert paths.join_path(plan(s), "orders", "notes")["suggestions"] == []                           # notes.note_id is a varchar: not a candidate
    # the suggestion is enough to connect them
    p2 = plan(s, confirmed=[best["confirmed"]])
    assert paths.join_path(p2, "orders", "addresses")["paths"][0]["hops"] == 1
    out = paths.join_path(plan(s), "orders", "notes")
    assert out["suggestions"] == [] and "confirmed" in out["note"]


# ------------------------------------------------------------------ dictionary -------------------

def test_data_dictionary_has_every_section_and_no_business_text(shop_plan):
    md = dictionary.data_dictionary(shop_plan, "shop_lh", "shop")
    for head in ("# Data dictionary: shop_lh / shop", "## Summary", "## Tables", "### orders", "## Keys", "## Relationships",
                 "## Tables without a key", "## Ambiguous columns", "## Diagram", "```mermaid", "erDiagram", "## Rules"):
        assert head in md, head
    assert "| Column | Type | Key | Refers to | Description |" in md
    assert "| customer_id | int |  | customers.customer_id (R1) |  |" in md                      # orders.customer_id row, empty description
    assert "| order_id | int | yes |  |  |" in md
    assert "- audit_log: can be queried" in md and "None." in md                                     # keyless listed; no ambiguity
    assert "| order_items | order_id+line_no | K5 |" in md
    assert "## Checked against the data" not in md
    assert md.count("Description |") >= 7 and "business" in md.split("## Summary")[0]            # the blank column is explained


def test_data_dictionary_includes_validation_counts(shop_plan):
    from fabric_backend.demo import demo_validation
    v = demo_validation()
    md = dictionary.data_dictionary(plan(seed.schema("shop"), keys={"order_items": ["order_id", "line_no"]}), "shop_lh", "shop", v)
    assert "## Checked against the data" in md and "| order_items | order_id+line_no | 134 | 0 | 134 |" in md
    assert "- Checked against the data: 6 of 6 keys unique" in md


def test_data_dictionary_on_a_fixture_escapes_pipes_and_lists_ambiguity(sakila):
    md = dictionary.data_dictionary(sakila, "sakila", "dbo")
    assert "### film_actor" in md and "| film_actor | actor_id+film_id | K4 |" in md
    s = Schema.from_information_schema([("dbo", "a|b", "x|y", "int", 1)])
    assert "| x\\|y | int |" in dictionary.data_dictionary(plan(s), "s", "dbo")


# ------------------------------------------------------------------ dbt --------------------------

def test_dbt_schema_sources_keys_and_relationships(shop_plan):
    yml = dbt.schema_yml(shop_plan, "shop", "shop", database="shop_lh")
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(yml)
    assert doc["version"] == 2 and len(doc["sources"]) == 1
    src = doc["sources"][0]
    assert src["name"] == "shop" and src["database"] == "shop_lh" and "schema" not in src
    tables = {t["name"]: t for t in src["tables"]}
    assert set(tables) == {"customers", "categories", "products", "addresses", "orders", "order_items", "audit_log"}
    cols = {c["name"]: c for c in tables["orders"]["columns"]}
    assert cols["order_id"]["data_tests"] == ["unique", "not_null"]
    assert cols["customer_id"]["data_tests"] == [{"relationships": {"arguments": {"to": "source('shop', 'customers')", "field": "customer_id"}}}]
    assert cols["ship_to_id"].get("data_tests") is None and cols["ship_to_id"]["description"] == ""
    items = {c["name"]: c for c in tables["order_items"]["columns"]}
    assert items["order_id"]["data_tests"][0] == "not_null" and "unique" not in items["order_id"]["data_tests"]   # composite key part
    assert "unique_combination_of_columns" in yml and "[order_id, line_no]" in yml
    assert all("data_tests" not in c for c in tables["audit_log"]["columns"] if c["name"] != "customer_id")
    # pre-1.10.5 syntax: arguments at the top level
    old = yaml.safe_load(dbt.schema_yml(shop_plan, "shop", "shop", arguments_block=False))
    rel = {c["name"]: c for c in {t["name"]: t for t in old["sources"][0]["tables"]}["orders"]["columns"]}["customer_id"]["data_tests"][0]
    assert rel == {"relationships": {"to": "source('shop', 'customers')", "field": "customer_id"}}
    assert dbt._y("Order Details") == '"Order Details"' and dbt._y("yes") == '"yes"' and dbt._y("orders") == "orders"


def test_dbt_schema_on_tpch_notes_composite_relationships(tpch):
    yml = dbt.schema_yml(tpch, "tpch", "dbo", tables=["LINEITEM", "PARTSUPP", "ORDERS"])
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(yml)
    names = [t["name"] for t in doc["sources"][0]["tables"]]
    assert names == ["PARTSUPP", "ORDERS", "LINEITEM"] and "L_PARTKEY+L_SUPPKEY -> PARTSUPP (R3) spans several columns" in yml
    assert doc["sources"][0]["schema"] == "dbo"


# ------------------------------------------------------------------ drift ------------------------

def test_plan_drift_detects_new_columns_gone_tables_and_unsupported_relationships(shop_plan):
    old = decode(definition(shop_plan, "shop_api", "ws", "ep-1", "SqlAnalyticsEndpoint"))
    same = drift.compare(shop_plan, old, "shop_api", "ws", "ep-1", "SqlAnalyticsEndpoint")
    assert same["would_change"] is False and same["summary"].startswith("no drift")
    # the source changed: products lost category_id, orders gained a column, categories is gone
    cols = [("shop", t.name, c.name, c.data_type, i) for t in seed.schema("shop") for i, c in enumerate(t.columns, 1)
            if not (t.name == "products" and c.name == "category_id") and t.name != "categories"]
    cols.append(("shop", "orders", "channel", "string", 99))
    newer = plan(Schema.from_information_schema(cols, schema="shop"))
    d = drift.compare(newer, old, "shop_api", "ws", "ep-1", "SqlAnalyticsEndpoint")
    assert d["would_change"] is True
    assert d["new_columns"] == [{"table": "shop.orders", "column": "channel"}]
    assert d["tables_gone"] == [{"table": "shop.categories", "why": "the table is no longer in the schema"}]
    assert {(r["table"], r["field"]) for r in d["relationships_unsupported"]} == {("shop.products", "category"), ("shop.categories", "products")}
    assert d["removed_columns"] == [{"table": "shop.products", "column": "category_id", "why": "the API still maps a column the source no longer has"}]
    assert "1 table(s) the API has that the plan does not" in d["summary"] and "update the item" in d["summary"]
    # a confirmed link the API lacks is a new relationship; excluding a table says so
    more = plan(seed.schema("shop"), confirmed=[{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}])
    d2 = drift.compare(more, old, "shop_api", "ws", "ep-1", "SqlAnalyticsEndpoint")
    assert {r["field"] for r in d2["new_relationships"]} == {"ship_to", "orders_as_ship_to"}
    d3 = drift.compare(shop_plan, old, "shop_api", "ws", "ep-1", "SqlAnalyticsEndpoint", tables=["orders", "customers"])
    assert len(d3["tables_gone"]) == 5 and d3["tables_gone"][0]["why"] == "the table is excluded by `tables`"
    d4 = drift.compare(shop_plan, old, "shop_api", "ws", "ep-2", "SqlAnalyticsEndpoint")
    assert d4["source_changed"] == [{"api_source_item": "ep-1", "plan_source_item": "ep-2"}] and d4["would_change"]


# ------------------------------------------------------------------ the MCP tools ----------------

@pytest.fixture
def shop(monkeypatch):
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: "11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": "Lakehouse", "id": "lh-1", "displayName": src,
                                                                             "sql_host": "x.datawarehouse.fabric.microsoft.com", "sql_db": src})
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: []))
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    return "Sales", "shop_lh"


def test_tools_answer_on_the_shop_schema(shop, monkeypatch):
    out = json.loads(server.semantic_model_draft(*shop, name="shop_model", schema="shop"))
    assert out["summary"]["tables"] == 7 and "definition/tables/orders.tmdl" in out["parts"] and "not yet created" in out["note"]
    assert 'Sql.Database("x.datawarehouse.fabric.microsoft.com", "shop_lh")' in out["parts"]["definition/expressions.tmdl"]
    out = json.loads(server.join_path(*shop, start="customers", end="categories", schema="shop"))
    assert out["paths"][0]["hops"] == 4 and out["paths"][0]["sql"].startswith("SELECT TOP (100)")
    out = json.loads(server.data_dictionary(*shop, schema="shop"))
    assert out["path"] == "docs/shop_lh-shop-data-dictionary.md" and "### orders" in out["markdown"] and "## Checked" not in out["markdown"]
    out = json.loads(server.dbt_schema(*shop, schema="shop"))
    assert out["path"] == "models/sources/shop.yml" and "source('shop', 'customers')" in out["yaml"] and "database: shop_lh" in out["yaml"]
    out = json.loads(server.dbt_schema(*shop, schema="shop", source_name="demo_lh", tables=["orders"]))
    assert out["path"] == "models/sources/demo_lh.yml" and "- name: customers" not in out["yaml"] and "schema: shop" in out["yaml"]
    bad = json.loads(server.join_path(*shop, start="orders", end="ghost", schema="shop"))
    assert bad["kind"] == "bad_input"
    bad = json.loads(server.semantic_model_draft(*shop, schema="shop", tables=["ghost"]))
    assert bad["kind"] == "bad_input"


def test_data_dictionary_with_validate_runs_the_counts(shop, monkeypatch):
    from fabric_backend import evidence
    monkeypatch.setattr(evidence, "validate", lambda p, execute, max_items=60: {"summary": "6 of 6 keys unique, 6 of 6 relationships hold without orphans",
                                                                               "keys": [], "relationships": [], "note": "counted"})
    out = json.loads(server.data_dictionary(*shop, schema="shop", validate=True))
    assert "## Checked against the data" in out["markdown"] and "6 of 6 keys unique" in out["markdown"]


def test_plan_drift_tool_reads_the_existing_api(shop, monkeypatch):
    existing = decode(definition(plan(seed.schema("shop")), "shop_api", "11111111-1111-1111-1111-111111111111", "ep-1", "SqlAnalyticsEndpoint"))
    monkeypatch.setattr(server, "find_item_by_name", lambda ws, name, headers, types=None: {"id": "api-1"} if name == "shop_api" else None)
    monkeypatch.setattr(server, "_graphql_definition", lambda ws, api_id, headers: existing)
    monkeypatch.setattr(server, "source_for", lambda ws, item, headers: ("ep-1", "SqlAnalyticsEndpoint"))
    out = json.loads(server.plan_drift(*shop, api="shop_api", schema="shop"))
    assert out["would_change"] is False and out["summary"].startswith("no drift")
    out = json.loads(server.plan_drift(*shop, api="shop_api", schema="shop",
                                       confirmed=[{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}]))
    assert out["would_change"] is True and len(out["new_relationships"]) == 2
    missing = json.loads(server.plan_drift(*shop, api="nope", schema="shop"))
    assert missing["kind"] == "not_found"


def test_new_tools_are_listed_read_only_with_titles():
    from starlette.testclient import TestClient
    with TestClient(server.build_app()) as client:
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                        headers={"Accept": "application/json, text/event-stream"})
        body = r.text
        payload = json.loads(body.split("data: ", 1)[1].split("\n", 1)[0]) if "data: " in body else r.json()
        tools = {t["name"]: t for t in payload["result"]["tools"]}
    for name in ("semantic_model_draft", "join_path", "data_dictionary", "dbt_schema", "plan_drift"):
        t = tools[name]
        assert t["annotations"]["readOnlyHint"] is True and t["annotations"]["destructiveHint"] is False and t["title"], name
        assert "ctx" not in t["inputSchema"]["properties"] and {"workspace", "source"} <= set(t["inputSchema"]["properties"])
    assert {"start", "end"} <= set(tools["join_path"]["inputSchema"]["properties"])
    assert "api" in tools["plan_drift"]["inputSchema"]["properties"] and "validate" in tools["data_dictionary"]["inputSchema"]["properties"]
    for word in ("semantic_model_draft", "join_path", "data_dictionary", "dbt_schema", "plan_drift"):
        assert word in server.mcp.instructions
