"""The plan as a Fabric IQ ontology: definition parts, TTL for the portal import, bindings, envelope."""
import base64
import json
import re

import pytest

from fabric_backend import ontology, seed
from fabric_backend.infer import PlanInputError, plan

ARGS = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="shop_lh", schema="shop",
            sql_endpoint="x.datawarehouse.fabric.microsoft.com")


@pytest.fixture
def shop_plan():
    return plan(seed.schema("shop"), None, None)


def test_definition_has_the_generation_2_skeleton_and_one_table_and_entity_per_source_table(shop_plan):
    parts = ontology.ontology_parts(shop_plan, "shop_ontology", **ARGS)
    assert {".platform", "database.tmdl", "model.tmdl", "namespaces/default.tmdl", "expressions.tmdl", "relationships.tmdl", "entityRelationships.tmdl"} <= set(parts)
    assert {p for p in parts if p.startswith("entities/")} == {f"entities/{e}.tmdl" for e in ("Customers", "Categories", "Products", "Orders", "OrderItems", "Addresses", "AuditLog")}
    assert {p for p in parts if p.startswith("tables/")} == {f"tables/{e}.tmdl" for e in ("Customers", "Categories", "Products", "Orders", "OrderItems", "Addresses", "AuditLog")}
    platform = json.loads(parts[".platform"])
    assert platform["metadata"] == {"type": "Ontology", "displayName": "shop_ontology"} and platform["config"]["version"] == "2.0"
    assert parts["database.tmdl"].startswith("database shop_ontology\n\tcompatibilityLevel: 1000000")
    assert "ref table Orders" in parts["model.tmdl"] and "ref entity Orders" in parts["model.tmdl"] and "ref namespace default" in parts["model.tmdl"]
    assert 'AzureStorage.DataLake("https://onelake.dfs.fabric.microsoft.com/11111111-1111-1111-1111-111111111111/lh-1"' in parts["expressions.tmdl"]


def test_entity_and_table_parts_carry_key_properties_bindings_and_the_rule(shop_plan):
    parts = ontology.ontology_parts(shop_plan, "shop_ontology", **ARGS)
    orders = parts["entities/Orders.tmdl"]
    assert orders.startswith("/// orders: key order_id by rule K2\nentity Orders\n")
    assert "\tbackingTable: Orders\n\tkeyProperty: order_id\n" in orders
    assert "\tproperty order_date\n\t\tdataType: dateTime\n" in orders and "\t\t\tvalueColumn: Orders.order_date\n" in orders
    table = parts["tables/Orders.tmdl"]
    assert "\tpartition Orders = entity\n\t\tmode: directLake\n\t\tsource\n\t\t\tentityName: orders\n\t\t\tschemaName: shop\n" in table
    assert "\t\tannotation ONT_ItemKind = Lakehouse\n" in table and "\t\tannotation ONT_SqlEndpoint = x.datawarehouse.fabric.microsoft.com\n" in table
    assert "\tcolumn quantity\n\t\tdataType: double\n" in parts["tables/OrderItems.tmdl"]
    # the lineage tag of a property equals that of its backing column, and the whole thing is deterministic
    tag = re.search(r"property order_id\n\t\tdataType: int64\n\t\tlineageTag: (\S+)", orders).group(1)
    assert f"column order_id\n\t\tdataType: int64\n\t\tlineageTag: {tag}\n" in table
    assert ontology.ontology_parts(shop_plan, "shop_ontology", **ARGS) == parts


def test_relationships_are_single_column_pairs_with_an_entity_relationship_each(shop_plan):
    parts = ontology.ontology_parts(shop_plan, "shop_ontology", **ARGS)
    assert "relationship Orders_customer_id_Customers\n\tfromColumn: Orders.customer_id\n\ttoColumn: Customers.customer_id\n" in parts["relationships.tmdl"]
    erel = parts["entityRelationships.tmdl"]
    assert "/// orders.customer_id -> customers.customer_id by rule R1\nentityRelationship OrdersHasCustomers\n" in erel
    assert "\tfromEntity: Orders\n\ttoEntity: Customers\n\n\tbackingConfiguration\n\t\trelationship: Orders_customer_id_Customers\n" in erel
    assert erel.count("entityRelationship ") == 6


def test_keyless_and_composite_key_entities_are_emitted_keyless_with_a_note(shop_plan):
    s = ontology.summary(shop_plan)
    assert s["entity_types"] == 7 and s["with_key"] == 5 and s["relationship_types"] == 6 and s["skipped_relationships"] == 0
    assert any(n.startswith("AuditLog: no key was found") for n in s["notes"])
    parts = ontology.ontology_parts(shop_plan, "shop_ontology", **ARGS)
    assert "keyProperty" not in parts["entities/AuditLog.tmdl"]
    composite = plan(seed.schema("shop"), {"order_items": ["order_id", "line_no"]}, None)
    s2 = ontology.summary(composite)
    assert any("OrderItems: composite key ['order_id', 'line_no']" in n for n in s2["notes"])
    parts2 = ontology.ontology_parts(composite, "shop_ontology", **ARGS)
    assert "keyProperty" not in parts2["entities/OrderItems.tmdl"] and "/// order_items: key order_id+line_no by rule K1" in parts2["entities/OrderItems.tmdl"]


def test_tables_filter_and_duplicate_entity_names_are_checked(shop_plan):
    parts = ontology.ontology_parts(shop_plan, "small", tables=["orders", "customers"], **ARGS)
    assert {p for p in parts if p.startswith("entities/")} == {"entities/Orders.tmdl", "entities/Customers.tmdl"}
    assert parts["relationships.tmdl"].count("relationship ") == 1                      # only the link between the two
    with pytest.raises(PlanInputError):
        ontology.ontology_parts(shop_plan, "x", tables=["ghost"], **ARGS)
    from fabric_backend.schema import Column, Schema, Table
    s = Schema(schema="dbo")
    s.tables["order_items"] = Table("order_items", [Column("order_items_id", "int")], schema="dbo")
    s.tables["OrderItems"] = Table("OrderItems", [Column("OrderItems_id", "int")], schema="dbo")
    with pytest.raises(ValueError, match="same entity name"):
        ontology.ontology_parts(plan(s, None, None), "x", **ARGS)


def test_envelope_is_the_rest_body_with_base64_parts(shop_plan):
    parts = ontology.ontology_parts(shop_plan, "shop_ontology", **ARGS)
    env = ontology.envelope("shop_ontology", parts)
    assert env["displayName"] == "shop_ontology" and len(env["definition"]["parts"]) == len(parts)
    part = next(p for p in env["definition"]["parts"] if p["path"] == "entities/Orders.tmdl")
    assert part["payloadType"] == "InlineBase64" and base64.b64decode(part["payload"]).decode() == parts["entities/Orders.tmdl"]


def test_ttl_for_the_portal_import_has_classes_properties_and_object_properties_with_rules(shop_plan):
    ttl = ontology.ontology_ttl(shop_plan, "shop ontology \"v1\"", "shop")
    assert ttl.startswith("@prefix rdf:") and '<urn:krusgraph:ontology:shop_ontology_v1> a owl:Ontology' in ttl
    assert 'rdfs:label "shop ontology \\"v1\\""' in ttl                                   # quotes escaped
    assert ":Orders a owl:Class ;\n    rdfs:label \"Orders\" ;\n    skos:altLabel \"orders\" ;\n    rdfs:comment \"Table shop.orders; key order_id (K2).\" ." in ttl
    assert ":Orders__order_date a owl:DatatypeProperty ;\n    rdfs:label \"order_date\" ;\n    rdfs:domain :Orders ;\n    rdfs:range xsd:dateTime ;" in ttl
    assert ":OrdersHasCustomers a owl:ObjectProperty ;\n    rdfs:label \"OrdersHasCustomers\" ;\n    rdfs:domain :Orders ;\n    rdfs:range :Customers ;\n    rdfs:comment \"orders.customer_id -> customers.customer_id by rule R1.\" ." in ttl
    assert ttl.count(" a owl:Class ;") == 7 and ttl.count(" a owl:ObjectProperty ;") == 6


def test_bindings_checklist_and_files(shop_plan):
    b = {x["entity_type"]: x for x in ontology.bindings(shop_plan, "shop_lh", "shop")}
    assert b["Orders"]["table"] == "shop.orders" and b["Orders"]["key"] == "order_id" and b["Orders"]["key_rule"] == "K2"
    assert {"name": "customer_id", "column": "customer_id", "type": "integer", "source_type": "int"} in b["Orders"]["properties"]
    assert b["Orders"]["relationships"] == [{"name": "OrdersHasCustomers", "to": "Customers", "from_columns": ["customer_id"], "to_columns": ["customer_id"], "rule": "R1"}]
    assert b["AuditLog"]["key"] is None and b["AuditLog"]["key_rule"] == "K3"
    files = ontology.ontology_files(shop_plan, "shop ontology", **ARGS)
    assert "ontology/shop_ontology/definition/entities/Orders.tmdl" in files and "ontology/shop_ontology/shop_ontology.ttl" in files
    assert json.loads(files["ontology/shop_ontology/bindings.json"])[0]["entity_type"] == "Customers"
    readme = files["ontology/shop_ontology/README.generated.md"]
    assert "7 entity types (5 with a key), 6 relationship types" in readme and "Item.ReadWrite.All" in readme and "Import ontology" in readme


@pytest.mark.parametrize("sql,expect", [("int", ("int64", "integer")), ("BIGINT", ("int64", "integer")), ("decimal(10,2)", ("string", "string")), ("decimal", ("double", "double")),
                                        ("varchar(50)", ("string", "string")), ("timestamp_ntz", ("string", "string")), ("date", ("dateTime", "datetime")),
                                        ("bit", ("boolean", "boolean")), ("", ("string", "string"))])
def test_property_types_follow_the_ontology_table(sql, expect):
    assert ontology.prop_type(sql) == expect


def test_entity_names_are_identifiers():
    assert ontology.entity_name("order_items") == "OrderItems" and ontology.entity_name("2024_sales") == "E2024Sales"
    assert ontology.entity_name("dim.customer") == "DimCustomer" and ontology.entity_name("") == "Entity"
