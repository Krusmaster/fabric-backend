"""Round n56: domain drafts (domains.py) and domain_draft on the shop schema, the synthetic SAP demo and Salesforce + ERP."""
import json

import pytest
import yaml

from fabric_backend import browser_check as bc, domains, evidence, seed, server, tool_status
from fabric_backend.infer import plan
from fabric_backend.schema import Schema


def _src(kind):
    src, _ = bc._source(kind, None, "")
    return src


def _by_name(out):
    return {d["name"]: d["tables"] for d in out["domains"]}


def test_shop_splits_orders_from_products_and_leaves_the_keyless_log_unassigned():
    out = domains.draft(plan(seed.schema("shop")), "shop", "shop_lh")
    assert _by_name(out) == {"customers": ["addresses", "customers", "order_items", "orders"], "products": ["categories", "products"]}
    assert [u["table"] for u in out["unassigned"]] == ["audit_log"] and "no key" in out["unassigned"][0]["reason"]
    assert [(i["consumer"], i["provider"], i["source"], i["target"]) for i in out["interfaces"]] == [("customers", "products", "order_items", "products")]
    assert "aggregate" in next(d for d in out["domains"] if d["name"] == "customers")["reasons"]["order_items"]


def test_shop_contract_is_odcs_with_uniqueness_relationships_and_orphan_rules():
    out = domains.draft(plan(seed.schema("shop")), "shop", "shop_lh")
    doc = yaml.safe_load(out["contracts"]["customers"])
    assert doc["apiVersion"] == "v3.2.0" and doc["kind"] == "DataContract" and doc["status"] == "draft"
    items = next(o for o in doc["schema"] if o["name"] == "order_items")
    uniq = next(q for q in items["quality"] if q.get("metric") == "duplicateValues")
    assert uniq["mustBe"] == 0 and uniq["dimension"] == "uniqueness" and uniq["arguments"]["properties"] == ["order_id", "line_no"]
    assert {"type": "foreignKey", "from": "order_items.product_id", "to": "products.product_id"} in items["relationships"]
    orphan = next(q for q in items["quality"] if q["type"] == "sql" and "products" in q["query"])
    assert orphan["mustBe"] == 0 and orphan["dimension"] == "consistency" and "NOT EXISTS" in orphan["query"]
    assert "value: <agree>" in out["contracts"]["customers"] and "slaProperties:\n" not in out["contracts"]["customers"].replace("# slaProperties:\n", "")


def test_sap_demo_proposes_order_to_cash_and_customer_master():
    out = domains.draft(plan(_src("sap").schema), "sap")
    names = _by_name(out)
    assert set(names) == {"order-to-cash", "customer master"}
    assert {"sap_vbak", "sap_vbap", "sap_likp", "sap_lips", "sap_vbrk", "sap_vbrp"} <= set(names["order-to-cash"])
    assert {"sap_kna1", "sap_adrc"} <= set(names["customer master"])
    assert any(i["source"] == "sap_vbak" and i["target"] == "sap_kna1" for i in out["interfaces"])
    for c in out["contracts"].values():
        yaml.safe_load(c)


def test_salesforce_and_erp_stay_two_domains_and_validation_lands_in_the_contracts():
    src = _src("crm")
    p = plan(src.schema)
    v = evidence.validate(p, src.execute)
    out = domains.draft(p, "crm", validation=v)
    assert _by_name(out) == {"Account": ["Account", "Contact", "Opportunity"], "sales_orders": ["customers", "sales_order_lines", "sales_orders"]}
    assert out["interfaces"] == [] and out["method"]["validated"]
    assert "lastCheck" in out["contracts"]["account"] and "orphan" in out["contracts"]["account"]


def test_same_schema_same_proposal_and_the_browser_entry_point_agrees():
    p = plan(_src("sap").schema)
    a, b = domains.propose_plan(p), domains.propose_plan(plan(_src("sap").schema))
    assert a == b
    r = bc.analyze("crm")
    assert _by_name(domains.propose_from_check(r)) == {"Account": ["Account", "Contact", "Opportunity"],
                                                       "sales_orders": ["customers", "sales_order_lines", "sales_orders"]}
    assert "fabric_backend/domains.py" in __import__("zipfile").ZipFile(__import__("io").BytesIO(bc.engine_zip())).namelist()


def test_leiden_keeps_communities_connected_and_small_groups_unassigned():
    out = domains.propose([{"name": "a", "key": ["id"]}, {"name": "b", "key": ["id"]}, {"name": "c", "key": ["id"]}],
                          [{"source": "a", "source_cols": ["b_id"], "target": "b", "target_cols": ["id"], "rule": "R1"}])
    assert _by_name(out) == {"b": ["a", "b"]} or _by_name(out) == {"a": ["a", "b"]}
    assert out["unassigned"] == [{"table": "c", "reason": "linked to no other table with a key"}]


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


def test_domain_draft_tool(shop):
    out = json.loads(server.domain_draft(*shop, schema="shop"))
    assert set(out["contracts"]) == {"customers", "products"} and "Fabric administrator" in out["note"]
    assert tool_status.STATUS["domain_draft"].changes and tool_status.label("domain_draft")
    import asyncio
    t = next(t for t in asyncio.run(server.mcp.list_tools()) if t.name == "domain_draft")
    assert t.annotations.read_only_hint is True and set(t.input_schema["properties"]) >= {"check_rows", "confirmed"}
