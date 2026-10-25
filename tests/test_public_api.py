"""The one-call Python API (`fabric_backend.create`, `plan_from`) that notebooks and scripts use, with Fabric mocked."""
import pytest
import requests

import fabric_backend
from fabric_backend import seed


def execute_for(schema_obj):
    """An execute(sql) that serves the given Schema as INFORMATION_SCHEMA rows and has no constraint views."""
    def execute(sql):
        if "CONSTRAINT" in sql.upper():
            raise RuntimeError("Invalid object name")
        return [(r["table_schema"], r["table_name"], r["column_name"], r["data_type"], r["ordinal_position"]) for r in schema_obj.to_rows()]
    return execute


def test_plan_from_needs_a_source_and_plans_the_demo_schema():
    with pytest.raises(ValueError, match="spark= .* or execute="):
        fabric_backend.plan_from()
    p = fabric_backend.plan_from(execute=execute_for(seed.schema("shop")), schema="shop")
    assert p.summary().startswith("7 tables, 5 with keys, 6 relationships")


def test_create_dry_run_builds_everything_but_deploys_nothing(monkeypatch):
    items = {"value": [{"displayName": "shop_lh", "type": "SQLEndpoint", "id": "ep-1"},
                       {"displayName": "shop_lh", "type": "Lakehouse", "id": "lh-1"}]}

    def get(url, **kwargs):
        if url.endswith("/items"):
            return type("R", (), {"status_code": 200, "json": lambda self: items, "raise_for_status": lambda self: None})()
        if url.endswith("/lakehouses/lh-1"):
            return type("R", (), {"status_code": 200, "raise_for_status": lambda self: None,
                                  "json": lambda self: {"properties": {"sqlEndpointProperties": {"id": "ep-1"}}}})()
        pytest.fail(f"unexpected GET {url}")
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("dry_run must not POST"))
    out = fabric_backend.create("ws-1", "shop_lh", "shop_api", execute=execute_for(seed.schema("shop")), schema="shop",
                                token_provider=lambda: "tok", dry_run=True)
    assert out["source"] == {"id": "ep-1", "type": "SqlAnalyticsEndpoint"}
    assert out["definition"]["displayName"] == "shop_api" and "definition" in out["definition"]
    assert out["plan"].summary().startswith("7 tables")
    assert "rayfin/connectors/shop_api/schema.ts" in out["rayfin"]                     # same plan, third consumer
    assert "result" not in out and "card" not in out


def test_create_resolves_an_id_and_fails_plainly_on_an_unknown_source(monkeypatch):
    empty = type("R", (), {"status_code": 200, "json": lambda self: {"value": []}, "raise_for_status": lambda self: None})()
    by_id = {"/warehouses/wh-1": type("R", (), {"status_code": 200, "json": lambda self: {"displayName": "dw"}})()}

    def get(url, **kwargs):
        if url.endswith("/items"):
            return empty
        for suffix, resp in by_id.items():
            if url.endswith(suffix):
                return resp
        return type("R", (), {"status_code": 404, "json": lambda self: {}})()
    monkeypatch.setattr(requests, "get", get)
    out = fabric_backend.create("ws-1", "wh-1", "dw_api", execute=execute_for(seed.schema("shop")), schema="shop",
                                token_provider=lambda: "tok", dry_run=True)
    assert out["source"] == {"id": "wh-1", "type": "Warehouse"}
    with pytest.raises(LookupError, match="no lakehouse/warehouse/SQL database named or with id 'ghost'"):
        fabric_backend.create("ws-1", "ghost", "x", execute=execute_for(seed.schema("shop")), schema="shop",
                              token_provider=lambda: "tok", dry_run=True)
