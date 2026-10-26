import csv
import json
from pathlib import Path

import pytest

from fabric_backend import Schema, plan, definition, decode, valid_item_name
from fabric_backend.cli import main
from fabric_backend.deploy import connection_card, endpoint_url

EX = Path(__file__).resolve().parent.parent / "examples"


def rows(name):
    with open(EX / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def schema():
    return Schema.from_information_schema(rows("columns.csv"))


@pytest.fixture
def keys():
    out = {}
    for r in rows("keys.csv"):
        out.setdefault(r["table_name"], []).append(r["column_name"])
    return out


def test_schema_reads_tables_and_drops_tech_cols(schema):
    assert len(schema) == 7
    assert "__timestamp" not in schema["order_items"].column_names
    assert schema["order_items"].has("LINE_NO")


def test_keys_by_name_prefer_specific_over_id(schema, keys):
    p = plan(schema, keys)
    assert p.keys["customers"] == (["customer_id"], "K2")
    assert p.keys["categories"] == (["id"], "K2")
    assert p.keys["order_items"] == (["order_id", "line_no"], "K1")
    assert "audit_log" in p.keyless


def test_relationships_by_name(schema, keys):
    p = plan(schema, keys)
    rel = {(r.source, tuple(r.source_cols), r.target): r.rule for r in p.relationships}
    assert rel[("orders", ("customer_id",), "customers")] == "R1"
    assert rel[("products", ("category_id",), "categories")] == "R1"
    assert rel[("order_items", ("order_id",), "orders")] == "R1"
    assert rel[("order_items", ("product_id",), "products")] == "R1"
    assert rel[("addresses", ("customer_id",), "customers")] == "R1"
    assert rel[("audit_log", ("customer_id",), "customers")] == "R1"   # keyless source can still point
    # ship_to_id matches nothing: no table "ship_to" — and it must not be guessed
    assert not any(r.source_cols == ["ship_to_id"] for r in p.relationships)
    assert p.ambiguous == []


def test_confirmed_relationship_applied_first(schema, keys):
    p = plan(schema, keys, confirmed=[{"source": "orders", "source_cols": ["ship_to_id"],
                                       "target": "addresses", "target_cols": ["address_id"]}])
    r = [x for x in p.relationships if x.source_cols == ["ship_to_id"]]
    assert r and r[0].rule == "confirmed" and r[0].target == "addresses"
    # the column names a role, not the table: the field is called after the role
    assert r[0].field_name == "ship_to" and r[0].reverse_name == "orders_as_ship_to"


def test_confirmed_field_names_are_kept(schema, keys):
    p = plan(schema, keys, confirmed=[{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses",
                                       "target_cols": ["address_id"], "field_name": "delivery_address",
                                       "reverse_name": "deliveries"}])
    r = next(x for x in p.relationships if x.source_cols == ["ship_to_id"])
    assert (r.field_name, r.reverse_name) == ("delivery_address", "deliveries")


def test_field_names_disambiguate_when_two_columns_point_at_same_table():
    s = Schema.from_information_schema([
        ("dbo", "flights", "flight_id", "int", 1), ("dbo", "flights", "origin_airport_id", "int", 2),
        ("dbo", "flights", "dest_airport_id", "int", 3),
        ("dbo", "airports", "airport_id", "int", 1), ("dbo", "airports", "name", "varchar", 2),
    ])
    p = plan(s, confirmed=[
        {"source": "flights", "source_cols": ["origin_airport_id"], "target": "airports", "target_cols": ["airport_id"]},
        {"source": "flights", "source_cols": ["dest_airport_id"], "target": "airports", "target_cols": ["airport_id"]},
    ])
    names = {tuple(r.source_cols): (r.field_name, r.reverse_name) for r in p.relationships}
    assert names[("origin_airport_id",)] == ("origin_airport", "flights_as_origin_airport")
    assert names[("dest_airport_id",)] == ("dest_airport", "flights_as_dest_airport")


def test_same_name_as_other_tables_key_is_r2_but_plain_id_never_matches():
    s = Schema.from_information_schema([
        ("dbo", "plant", "werks", "char", 1), ("dbo", "plant", "name", "varchar", 2),
        ("dbo", "stock", "id", "int", 1), ("dbo", "stock", "werks", "char", 2), ("dbo", "stock", "qty", "int", 3),
        ("dbo", "notes", "id", "int", 1), ("dbo", "notes", "text", "varchar", 2),
    ], schema="dbo")
    p = plan(s, keys={"plant": ["werks"]})
    rel = {(r.source, r.target): r.rule for r in p.relationships}
    assert rel == {("stock", "plant"): "R2"}          # notes.id -> stock.id must NOT appear


def test_ambiguous_column_is_reported_not_applied():
    s = Schema.from_information_schema([
        ("dbo", "users", "user_id", "int", 1), ("dbo", "user", "user_id", "int", 1),
        ("dbo", "posts", "post_id", "int", 1), ("dbo", "posts", "user_id", "int", 2),
    ])
    p = plan(s)
    assert not [r for r in p.relationships if r.source == "posts"]
    assert p.ambiguous and set(p.ambiguous[0]["candidates"]) == {"users", "user"}


def test_composite_key_r3_header_items():
    s = Schema.from_information_schema([
        ("dbo", "sales_org_plant", "sales_org", "char", 1), ("dbo", "sales_org_plant", "plant", "char", 2),
        ("dbo", "sales_org_plant", "name", "varchar", 3),
        ("dbo", "deliveries", "delivery_id", "int", 1), ("dbo", "deliveries", "sales_org", "char", 2),
        ("dbo", "deliveries", "plant", "char", 3),
    ])
    p = plan(s, keys={"sales_org_plant": ["sales_org", "plant"]})
    r = p.relationships[0]
    assert (r.source, r.source_cols, r.target, r.rule) == ("deliveries", ["sales_org", "plant"], "sales_org_plant", "R3")


def test_declared_keys_win(schema):
    cols = rows("columns.csv")
    keys = [("orders", "PRIMARY KEY", "order_id", 1, "PK_orders", None, None),
            ("orders", "FOREIGN KEY", "customer_id", 1, "FK_orders_customers", "customers", "customer_id")]
    s = Schema.from_information_schema(cols, keys)
    p = plan(s)
    assert p.keys["orders"] == (["order_id"], "K0")
    r = [x for x in p.relationships if x.source == "orders" and x.target == "customers"]
    assert r[0].rule == "R0"


def test_definition_shape(schema, keys):
    p = plan(schema, keys)
    env = definition(p, "shop_api", "ws-1", "ep-1")
    assert env["type"] == "GraphQLApi" and "format" not in env["definition"]   # InvalidDefinitionFormat otherwise
    body = decode(env)
    ds = body["datasources"][0]
    assert ds["sourceType"] == "SqlAnalyticsEndpoint" and ds["sourceItemId"] == "ep-1"
    objs = {o["graphqlType"]: o for o in ds["objects"]}
    assert objs["orders"]["sourceObject"] == "dbo.orders"
    ro = {"Create": "Disabled", "Update": "Disabled", "Delete": "Disabled"}      # spelled out: omitted => Enabled in Fabric
    assert objs["orders"]["actions"] == {"Query": "Enabled", "Query_by_pk": "Enabled", **ro}
    assert objs["audit_log"]["actions"] == {"Query": "Enabled", "Query_by_pk": "Disabled", **ro}
    # every endpoint column must be mapped, technical ones included; "__" is reserved in GraphQL names
    assert objs["order_items"]["fieldMappings"]["__timestamp"] == "timestamp"
    m2o = [r for r in objs["orders"]["relationships"] if r["cardinality"] == "ManyToOne"]
    assert m2o == [{"field": "customer", "cardinality": "ManyToOne", "targetObject": "dbo.customers",
                    "sourceFields": ["customer_id"], "targetFields": ["customer_id"]}]
    o2m = {r["field"]: r for r in objs["customers"]["relationships"]}
    assert set(o2m) == {"orders", "addresses", "audit_log"}
    assert o2m["orders"]["cardinality"] == "OneToMany"
    assert "skipped_relationships" not in env


def test_definition_drops_relationships_into_keyless_targets():
    s = Schema.from_information_schema([
        ("dbo", "events", "event_id", "int", 1), ("dbo", "events", "log_id", "int", 2),
        ("dbo", "logs", "log_id", "int", 1), ("dbo", "logs", "msg", "varchar", 2),
    ])
    p = plan(s, confirmed=[{"source": "events", "source_cols": ["log_id"], "target": "logs"}])
    p.keys.pop("logs")                     # pretend logs has no key
    env = definition(p, "x", "ws", "ep")
    assert env["skipped_relationships"] == ["events.log_id -> logs (confirmed)"]


def test_writable_only_for_warehouse(schema, keys):
    p = plan(schema, keys)
    lh = decode(definition(p, "a", "ws", "ep", writable=True))["datasources"][0]["objects"][0]["actions"]
    wh = decode(definition(p, "a", "ws", "wh", source_type="Warehouse", writable=True))["datasources"][0]["objects"][0]["actions"]
    assert lh["Create"] == "Disabled" and wh["Create"] == "Enabled" and wh["Update"] == "Enabled" and wh["Delete"] == "Disabled"


def test_tables_filter_and_names(schema, keys):
    p = plan(schema, keys)
    body = decode(definition(p, "a", "ws", "ep", tables=["orders", "customers"]))
    assert {o["graphqlType"] for o in body["datasources"][0]["objects"]} == {"orders", "customers"}
    with pytest.raises(ValueError):
        definition(p, "shop api", "ws", "ep")
    assert valid_item_name("shop_api_v1") and not valid_item_name("shop-api")


def test_mermaid_and_summary(schema, keys):
    p = plan(schema, keys)
    m = p.mermaid()
    assert m.startswith("erDiagram") and "customers ||--o{ orders" in m and "order_id int PK" in m
    assert "7 tables, 6 with keys, 6 relationships" in p.summary()


def test_cli_plan_and_definition(tmp_path):
    out = tmp_path / "g.json"
    assert main(["plan", str(EX / "columns.csv"), "--keys", str(EX / "keys.csv"), "--mermaid", str(tmp_path / "e.mmd")]) == 0
    assert main(["definition", str(EX / "columns.csv"), "--keys", str(EX / "keys.csv"), "--name", "shop_api",
                 "--workspace", "ws", "--source-item", "ep", "--out", str(out)]) == 0
    assert json.loads(out.read_text())["displayName"] == "shop_api"


def test_connection_card_lists_the_portal_clicks():
    card = connection_card("ws", "item", "shop_api")
    assert endpoint_url("ws", "item") in card and "Introspection" in card and "Run Queries and Mutations" in card


def test_reserved_relationship_field_names_are_suffixed():
    s = Schema.from_information_schema([
        ("dbo", "order", "order_id", "int", 1),
        ("dbo", "items", "item_id", "int", 1), ("dbo", "items", "order_id", "int", 2),
    ])
    p = plan(s)
    r = p.relationships[0]
    assert (r.source, r.target, r.reverse_name) == ("items", "order", "items_lines")   # "items" alone -> 500 in Fabric


def test_find_item_by_name_skips_sql_endpoint_with_same_name(monkeypatch):
    import importlib; dp = importlib.import_module("fabric_backend.deploy")

    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"value": [{"id": "ep", "displayName": "lh", "type": "SQLEndpoint"},
                              {"id": "lh-id", "displayName": "lh", "type": "Lakehouse"}]}
    import types, sys
    fake = types.SimpleNamespace(get=lambda *a, **k: R())
    monkeypatch.setitem(sys.modules, "requests", fake)
    assert dp.find_item_by_name("ws", "lh", {})["id"] == "lh-id"


def test_id_from_null_body():
    from fabric_backend.deploy import _id_from

    class R:
        def __init__(self, t): self.text = t
        def json(self):
            import json; return json.loads(self.text)
    assert _id_from(R("null")) is None and _id_from(R('{"id":"x"}')) == "x"
    class Bad:
        def json(self): raise ValueError
    assert _id_from(Bad()) is None


def test_rayfin_entities_and_schema(schema, keys):
    from fabric_backend.rayfin import rayfin_files, prop_name, class_name, rayfin_type
    assert prop_name("customer_id") == "customerId" and prop_name("OrderID") == "orderID" and prop_name("__timestamp") == "timestamp"
    assert class_name("order_items") == "OrderItems" and class_name("I_SALESDOCUMENT") == "ISalesdocument"
    assert rayfin_type("decimal(15,2)") == ("decimal", "number") and rayfin_type("varchar") == ("text", "string")
    assert rayfin_type("datetime2") == ("date", "Date") and rayfin_type("bit") == ("boolean", "boolean")
    files = rayfin_files(plan(schema, keys), "shop")
    assert set(files) == {f"rayfin/connectors/shop/{n}.ts" for n in
                          ["Customers", "Products", "Categories", "Orders", "OrderItems", "Addresses", "AuditLog", "schema"]} | {"rayfin/connectors/shop/README.generated.md"}
    orders = files["rayfin/connectors/shop/Orders.ts"]
    assert "export class Orders extends Source({ schema: 'dbo', table: 'orders', primaryKey: ['orderId'] })" in orders
    assert "@int({ column: 'order_id' }) orderId!: number;" in orders
    assert "@one(() => Customers, { sourceFields: ['customerId'], targetFields: ['customerId'] }) customer?: Customers;" in orders
    assert "@many(() => OrderItems, { sourceFields: ['orderId'], targetFields: ['orderId'] }) orderItems?: OrderItems[];" in orders
    assert "import { Customers } from './Customers.js';" in orders
    items = files["rayfin/connectors/shop/OrderItems.ts"]
    assert "primaryKey: ['orderId', 'lineNo']" in items and "@date({ column: '__timestamp' }) timestamp!: Date;" in items
    audit = files["rayfin/connectors/shop/AuditLog.ts"]
    assert "primaryKey" not in audit and "// no key (rule K3)" in audit and "@one(() => Customers, { sourceFields: ['customerId'], targetFields: ['customerId'] })" in audit
    sch = files["rayfin/connectors/shop/schema.ts"]
    assert "connector: 'fabric-sqlanalytics'" in sch and "entities: { Customers, Products, Categories, Orders, OrderItems, Addresses, AuditLog }" in sch
    assert "export type ShopSchema = GraphQLBackedConnector<" in sch
    no_rel = rayfin_files(plan(schema, keys), "shop", relationships=False)["rayfin/connectors/shop/Orders.ts"]
    assert "@one" not in no_rel and "many" not in no_rel.split("from '@microsoft/rayfin-core'")[0]


def test_rayfin_warehouse_type_and_rejects_semantic_model(schema, keys):
    from fabric_backend.rayfin import rayfin_files
    assert "connector: 'fabric-warehouse'" in rayfin_files(plan(schema, keys), "x", "Warehouse")["rayfin/connectors/x/schema.ts"]
    with pytest.raises(ValueError):
        rayfin_files(plan(schema, keys), "x", "AzureSql")


def test_cli_rayfin(tmp_path):
    assert main(["rayfin", str(EX / "columns.csv"), "--keys", str(EX / "keys.csv"), "--connector", "shop", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "rayfin/connectors/shop/Orders.ts").exists()


def test_schema_from_rayfin_metadata(tmp_path):
    meta = {"source": "shop", "connector": "fabric-sqlanalytics", "schemas": [{"schemaName": "shop", "tables": [
        {"tableName": "orders", "columns": [{"columnName": "order_id", "dataType": "int", "isNullable": False},
                                            {"columnName": "customer_id", "dataType": "int", "isNullable": True},
                                            {"columnName": "__timestamp", "dataType": "datetime2", "isNullable": True}]},
        {"tableName": "customers", "columns": [{"columnName": "customer_id", "dataType": "int"}, {"columnName": "name", "dataType": "varchar"}]}]}]}
    s = Schema.from_rayfin_metadata(meta)
    assert s.schema == "shop" and set(s.tables) == {"orders", "customers"}
    p = plan(s)
    assert [(r.source, r.target, r.rule) for r in p.relationships] == [("orders", "customers", "R1")]
    import json
    f = tmp_path / "metadata.json"; f.write_text(json.dumps(meta))
    assert main(["rayfin", str(f), "--schema", "shop", "--connector", "shop", "--out", str(tmp_path)]) == 0
    text = (tmp_path / "rayfin/connectors/shop/Orders.ts").read_bytes()
    assert b"\r\n" not in text and b"schema: 'shop', table: 'orders'" in text


def test_remote_server_tools_are_annotated_and_auth_reads_headers():
    pytest.importorskip("mcp.server.mcpserver")
    import asyncio
    from fabric_backend import server

    async def tools():
        return await server.mcp.list_tools()
    ts = asyncio.run(tools())
    assert {t.name for t in ts} == {"list_workspaces", "list_sources", "list_tables", "plan_backend", "create_backend", "rayfin_connector", "query_graphql", "ontology_draft", "validate_plan", "sample_rows", "describe_backend",
                                    "semantic_model_draft", "join_path", "data_dictionary", "dbt_schema", "plan_drift",
                                    "create_semantic_model", "create_views", "create_data_agent", "app_starter", "app_readiness", "lineage", "analyze_schema", "suggest_relationships", "create_ontology"}
    for t in ts:
        assert t.title and t.annotations is not None and t.annotations.read_only_hint is not None   # directory requirement
        assert t.annotations.title == t.title, t.name                                               # the directory reads annotations.title
    assert next(t for t in ts if t.name == "create_backend").annotations.read_only_hint is False
    # it can overwrite an existing API definition in place, so Claude asks before each call (directory review criteria)
    assert next(t for t in ts if t.name == "create_backend").annotations.destructive_hint is True

    class Ctx:
        headers = {"authorization": "Bearer abc", "x-fabric-sql-token": "sql123"}
    a = server.Auth()
    assert a.fabric(Ctx()) == "abc" and a.sql(Ctx()) == "sql123"
    a.tenant = a.client = a.secret = None
    with pytest.raises(RuntimeError):
        a.fabric(None)                      # no header, no service principal: refuse, never guess

    assert "not allowed" in server.query_graphql("ws", "api", "mutation { x }", ctx=Ctx())


def test_seed_rows_match_the_example_schema():
    from fabric_backend.seed import rows, SCHEMAS
    r = rows()
    assert r == rows()                                                    # deterministic
    cols = {}
    for row in csv.DictReader(open(EX / "columns.csv", encoding="utf-8")):
        cols.setdefault(row["table_name"], []).append(row["column_name"])
    for t, spec in SCHEMAS.items():
        names = [c.split()[0] for c in spec.split(", ")]
        assert names == [c for c in cols[t] if not c.startswith("__")], t
        assert all(len(x) == len(names) for x in r[t])
    order_ids = {o[0] for o in r["orders"]}
    assert all(i[0] in order_ids for i in r["order_items"])                 # every line has its order
    assert {o[3] for o in r["orders"]} <= {a[0] for a in r["addresses"]}    # ship_to points at an address


def test_plan_scales_to_a_large_warehouse():
    """Hundreds of tables must plan in well under a tool timeout; the R2 lookup is indexed, not rescanned per column."""
    import random
    import time
    from fabric_backend.schema import Column, Table
    rnd = random.Random(7)
    words = ["orders", "items", "customers", "products", "events", "regions", "stores", "users", "sales", "returns"]
    names = [f"{w}{i}" for i, w in enumerate(rnd.choices(words, k=600))]
    s = Schema(schema="dbo")
    for name in names:
        cols = [Column(f"{name}_id" if rnd.random() < 0.7 else "id", "int")]
        cols += [Column(f"{names[rnd.randrange(600)]}_id" if rnd.random() < 0.3 else f"col{j}", "int") for j in range(12)]
        s.tables[name] = Table(name, cols, schema="dbo")
    t0 = time.perf_counter()
    p = plan(s, None, None)
    assert time.perf_counter() - t0 < 5                      # ~0.1 s now; it was several seconds with the per-column rescan
    assert len(p.keys) == 600 and len(p.relationships) > 600
    assert all(r.rule in ("R1", "R2") for r in p.relationships)


def test_keys_and_confirmed_that_name_missing_tables_or_columns_are_rejected_up_front():
    from fabric_backend import seed
    from fabric_backend.infer import PlanInputError
    s = seed.schema("shop")
    plan(s, {"ORDER_ITEMS": ["Order_ID", "line_no"]}, [{"source": "Orders", "source_cols": ["CUSTOMER_ID"], "target": "customers"}])  # case-insensitive: fine
    import pytest
    with pytest.raises(PlanInputError, match="keys: column 'ghost' is not in table 'orders'"):
        plan(s, {"orders": ["ghost"]}, None)
    with pytest.raises(PlanInputError, match="keys: table 'nowhere' is not in the schema"):
        plan(s, {"nowhere": ["id"]}, None)
    with pytest.raises(PlanInputError, match="confirmed\\[0\\]: column 'ghost_col' is not in table 'orders'"):
        plan(s, None, [{"source": "orders", "source_cols": ["ghost_col"], "target": "customers", "target_cols": ["customer_id"]}])
    with pytest.raises(PlanInputError, match="target table 'nowhere' is not in the schema"):
        plan(s, None, [{"source": "orders", "source_cols": ["customer_id"], "target": "nowhere"}])
    with pytest.raises(PlanInputError, match="needs source, source_cols and target"):
        plan(s, None, [{"source": "orders"}])
    with pytest.raises(PlanInputError, match="keys: table 'orders' has an empty column list"):
        plan(s, {"orders": []}, None)


def test_rayfin_table_filter_drops_relationships_to_tables_not_generated():
    from fabric_backend.seed import SCHEMAS
    from fabric_backend.schema import Schema
    from fabric_backend.infer import plan as make_plan
    from fabric_backend.rayfin import rayfin_files
    cols = [("shop", t, c.split(" ")[0], c.split(" ")[1].lower(), i + 1)
            for t, s in SCHEMAS.items() for i, c in enumerate(s.split(", "))]
    p = make_plan(Schema.from_information_schema(cols, schema="shop"), keys={"order_items": ["order_id", "line_no"]})
    files = rayfin_files(p, tables=["orders", "customers"])
    customers = files["rayfin/connectors/data/Customers.ts"]
    assert "Addresses" not in customers and "AuditLog" not in customers and "OrderItems" not in files["rayfin/connectors/data/Orders.ts"]
    assert "@many(() => Orders" in customers and "@one(() => Customers" in files["rayfin/connectors/data/Orders.ts"]
    assert "2 entities, 1 relationships" in files["rayfin/connectors/data/README.generated.md"]
    assert len(p.relationships) == 6                                   # the caller's plan is not changed
