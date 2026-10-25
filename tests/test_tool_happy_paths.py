"""The four read/build tools end to end on the synthetic shop schema, with Fabric and the SQL endpoint mocked:
what a user sees when everything works. The engine is the real one; nothing is stubbed below `_plan`."""
import json

import pytest

from fabric_backend import seed, server
from fabric_backend.schema import Schema


@pytest.fixture
def shop(monkeypatch):
    """A lakehouse called shop_lh whose SQL endpoint serves the seven demo tables."""
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": "Lakehouse", "id": "lh-1", "displayName": src,
                                                                             "sql_host": "x.datawarehouse.fabric.microsoft.com", "sql_db": src})
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: []))
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    return "ws-1", "shop_lh"


def test_list_tables_names_every_demo_table_with_typed_columns(shop):
    out = json.loads(server.list_tables(*shop, schema="shop"))
    assert set(out) == {"customers", "categories", "products", "orders", "order_items", "addresses", "audit_log"}
    assert ["order_id", "int"] in out["orders"] and all(isinstance(c, list) and len(c) == 2 for cols in out.values() for c in cols)


def test_plan_backend_reports_rules_ambiguity_and_a_diagram(shop):
    out = json.loads(server.plan_backend(*shop, schema="shop"))
    assert out["summary"].startswith("7 tables, 5 with keys, 6 relationships")
    assert out["keys"]["orders"]["columns"] == ["order_id"] and out["keys"]["orders"]["rule"].startswith("K")
    rels = {(r["source"], tuple(r["source_cols"])): r for r in out["relationships"]}
    assert rels[("products", ("category_id",))]["target"] == "categories" and rels[("products", ("category_id",))]["rule"] == "R1"
    assert all(r["rule"] in {"R0", "R1", "R2", "R3"} for r in out["relationships"])     # every link says which rule made it
    assert "erDiagram" in out["mermaid"]
    assert out["ambiguous"] == [] and set(out["keyless"]) == {"order_items", "audit_log"}
    # composite key override and a confirmed link both reach the engine
    with_keys = json.loads(server.plan_backend(*shop, schema="shop", keys={"order_items": ["order_id", "line_no"]}))
    assert with_keys["keys"]["order_items"]["columns"] == ["order_id", "line_no"]


def test_create_backend_returns_the_card_when_fabric_succeeds(shop, monkeypatch):
    monkeypatch.setattr(server, "source_for", lambda ws, item, headers: ("ep-1", "SqlAnalyticsEndpoint"))
    envs = []

    def fake_deploy(env, workspace, token_provider=None, **kw):
        envs.append(env)
        assert callable(token_provider)                                                 # deploy() fetches the token itself
        return {"status": "Succeeded", "mode": "created", "id": "api-1"}
    monkeypatch.setattr(server, "deploy", fake_deploy)
    out = json.loads(server.create_backend(*shop, name="shop_api", schema="shop"))
    assert out["result"] == {"status": "Succeeded", "mode": "created", "id": "api-1"}
    assert out["source"] == {"id": "ep-1", "type": "SqlAnalyticsEndpoint"}
    assert "graphqlapis/api-1/graphql" in out["card"] and "Introspection" in out["card"]
    assert envs[0]["displayName"] == "shop_api" and "definition" in envs[0]
    assert "error" not in out and "kind" not in out


def test_create_backend_explains_a_refusal_and_a_timeout(shop, monkeypatch):
    monkeypatch.setattr(server, "source_for", lambda ws, item, headers: ("ep-1", "SqlAnalyticsEndpoint"))
    monkeypatch.setattr(server, "deploy", lambda *a, **k: {"status": "Failed", "mode": "created", "http": 403,
                                                           "body": '{"errorCode":"InsufficientPrivileges","message":"Contributor needed"}'})
    out = json.loads(server.create_backend(*shop, name="shop_api", schema="shop"))
    assert out["kind"] == "no_access" and "Contributor needed" in out["error"] and "body" not in out["result"]
    monkeypatch.setattr(server, "deploy", lambda *a, **k: {"status": "Timeout", "mode": "created", "operation": "op-1"})
    out = json.loads(server.create_backend(*shop, name="shop_api", schema="shop"))
    assert out["kind"] == "timeout" and out["result"]["operation"] == "op-1"


def test_rayfin_connector_writes_entities_for_the_endpoint_type(shop):
    out = json.loads(server.rayfin_connector(*shop, connector="shop", schema="shop"))
    assert {"rayfin/connectors/shop/schema.ts", "rayfin/connectors/shop/Orders.ts", "rayfin/connectors/shop/README.generated.md"} <= set(out)
    assert "Orders" in out["rayfin/connectors/shop/Orders.ts"] and "order_id" in out["rayfin/connectors/shop/Orders.ts"]


def test_a_typo_in_keys_or_confirmed_is_a_bad_input_answer_not_a_fabric_error(shop):
    out = json.loads(server.plan_backend(*shop, schema="shop", keys={"orders": ["ghost"]}))
    assert out["kind"] == "bad_input" and "'ghost'" in out["error"] and "Fabric" not in out["error"]
    out = json.loads(server.plan_backend(*shop, schema="shop", confirmed=[{"source": "orders", "source_cols": ["customer_id"], "target": "nowhere"}]))
    assert out["kind"] == "bad_input" and "nowhere" in out["error"] and "list_tables" in out["hint"]
