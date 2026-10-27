"""The four read/build tools end to end on the synthetic shop schema, with Fabric and the SQL endpoint mocked:
what a user sees when everything works. The engine is the real one; nothing is stubbed below `_plan`."""
import json

import pytest

from fabric_backend import seed, server
from fabric_backend.schema import Schema

_REAL_EXISTING_API = server._existing_api          # tests/conftest.py stubs it out; the guard test puts it back


@pytest.fixture(autouse=True)
def _workspace_ids_pass_through(monkeypatch):
    """These tests mock Fabric per route; a workspace given as a plain string is used as the id."""
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: workspace)



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
    assert out["summary"].startswith("7 tables, 6 with keys, 6 relationships")
    assert out["keys"]["orders"]["columns"] == ["order_id"] and out["keys"]["orders"]["rule"].startswith("K")
    rels = {(r["source"], tuple(r["source_cols"])): r for r in out["relationships"]}
    assert rels[("products", ("category_id",))]["target"] == "categories" and rels[("products", ("category_id",))]["rule"] == "R1"
    assert all(r["rule"] in {"R0", "R1", "R2", "R3", "R4"} for r in out["relationships"])     # every link says which rule made it
    assert "erDiagram" in out["mermaid"]
    assert out["ambiguous"] == [] and out["keyless"] == ["audit_log"]
    assert out["keys"]["order_items"] == {"columns": ["order_id", "line_no"], "rule": "K5"}   # header reference + line number
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


def test_a_tables_filter_must_name_real_tables(shop, monkeypatch):
    monkeypatch.setattr(server, "source_for", lambda ws, item, headers: ("ep-1", "SqlAnalyticsEndpoint"))
    monkeypatch.setattr(server, "deploy", lambda env, ws, **k: {"status": "Succeeded", "mode": "created", "id": "api-1"})
    out = json.loads(server.create_backend(*shop, name="shop_api", schema="shop", tables=["orders", "ghost"]))
    assert out["kind"] == "bad_input" and "'ghost'" in out["error"] and "result" not in out       # nothing was deployed
    out = json.loads(server.create_backend(*shop, name="shop_api", schema="shop", tables=["ORDERS", "customers"]))
    assert out["result"]["status"] == "Succeeded"                                                  # case does not matter
    out = json.loads(server.rayfin_connector(*shop, connector="shop", schema="shop", tables=[]))
    assert out["kind"] == "bad_input" and "empty" in out["error"]


def test_create_backend_will_not_silently_drop_a_relationship_the_api_has(shop, monkeypatch):
    """The live shop_api has orders.ship_to_id -> addresses, confirmed earlier. A plain re-run must not remove it."""
    from fabric_backend.graphql import decode, definition
    from fabric_backend.infer import plan
    ship_to = {"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}
    existing = decode(definition(plan(seed.schema("shop"), confirmed=[ship_to]), "shop_api", "ws-1", "ep-1", "SqlAnalyticsEndpoint"))
    monkeypatch.setattr(server, "source_for", lambda ws, item, headers: ("ep-1", "SqlAnalyticsEndpoint"))
    monkeypatch.setattr(server, "_api_id", lambda ws, api, headers: "api-1" if api == "shop_api" else None)
    monkeypatch.setattr(server, "_graphql_definition", lambda ws, api_id, headers: existing)
    monkeypatch.setattr(server, "_existing_api", _REAL_EXISTING_API)
    deployed = []
    monkeypatch.setattr(server, "deploy", lambda env, ws, **k: deployed.append(env) or {"status": "Succeeded", "mode": "updated", "id": "api-1"})

    out = json.loads(server.create_backend(*shop, name="shop_api", schema="shop"))
    assert out["kind"] == "would_remove" and not deployed and "allow_removals" in out["hint"]
    assert {r["field"] for r in out["relationships_lost"]} == {"ship_to", "orders_as_ship_to"}
    assert out["keep_with_confirmed"] == [{**ship_to, "field_name": "ship_to", "reverse_name": "orders_as_ship_to"}]   # both of the API's names

    kept = json.loads(server.create_backend(*shop, name="shop_api", schema="shop", confirmed=out["keep_with_confirmed"]))
    assert kept["result"]["status"] == "Succeeded" and len(deployed) == 1
    dropped = json.loads(server.create_backend(*shop, name="shop_api", schema="shop", allow_removals=True))
    assert dropped["result"]["status"] == "Succeeded" and len(deployed) == 2
    new_name = json.loads(server.create_backend(*shop, name="shop_api_v2", schema="shop"))
    assert new_name["result"]["status"] == "Succeeded"                       # a new name has nothing to lose
