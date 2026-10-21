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
    # two relationships orders -> addresses? no: only one, so field name is plain "address"
    assert r[0].field_name == "address"


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
    assert names[("origin_airport_id",)] == ("airport_by_origin_airport_id", "flights_by_origin_airport_id")
    assert names[("dest_airport_id",)][0] == "airport_by_dest_airport_id"


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
    assert objs["orders"]["actions"] == {"Query": "Enabled", "Query_by_pk": "Enabled"}
    assert objs["audit_log"]["actions"] == {"Query": "Enabled"}
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
    assert "Create" not in lh and wh["Create"] == "Enabled" and wh["Delete"] == "Disabled"


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
