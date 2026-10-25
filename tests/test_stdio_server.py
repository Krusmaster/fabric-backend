"""The local stdio server (fabric-backend-mcp): same engine, same answers on failure as the remote one."""
import json

import pytest

from fabric_backend import mcp_server, seed
from fabric_backend.schema import Schema


@pytest.fixture
def local_shop(monkeypatch):
    monkeypatch.setattr(mcp_server, "_execute_factory", lambda schema: (lambda sql: []))
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))


def test_local_tools_plan_the_source_behind_the_odbc_string(local_shop):
    out = json.loads(mcp_server.list_tables("shop"))
    assert set(out) == {"customers", "categories", "products", "orders", "order_items", "addresses", "audit_log"}
    out = json.loads(mcp_server.plan_backend("shop"))
    assert out["summary"].startswith("7 tables, 6 with keys, 6 relationships") and "erDiagram" in out["mermaid"]
    out = json.loads(mcp_server.rayfin_connector("shop", schema="shop", tables=["orders"]))
    assert "rayfin/connectors/shop/Orders.ts" in out and "rayfin/connectors/shop/Customers.ts" not in out


def test_local_tools_answer_failures_like_the_remote_ones(local_shop, monkeypatch):
    out = json.loads(mcp_server.plan_backend("shop", keys={"orders": ["ghost"]}))
    assert out["kind"] == "bad_input" and "'ghost'" in out["error"]
    out = json.loads(mcp_server.rayfin_connector("shop", schema="shop", tables=["ghost"]))
    assert out["kind"] == "bad_input"

    def no_driver(schema):
        raise ImportError("No module named 'pyodbc'")
    monkeypatch.setattr(mcp_server, "_execute_factory", no_driver)
    out = json.loads(mcp_server.list_tables("shop"))
    assert out["kind"] == "server_config" and "Traceback" not in json.dumps(out)
    # a login failure must not echo the ODBC connection string
    monkeypatch.setenv("FABRIC_ODBC", "Driver=x;Server=s;PWD=super-secret-password")

    def bad_login(schema):
        class OperationalError(Exception):
            pass
        raise OperationalError("('28000', '[28000] Login failed for user. (18456)')")
    monkeypatch.setattr(mcp_server, "_execute_factory", bad_login)
    text = mcp_server.list_tables("shop")
    assert json.loads(text)["kind"] == "sql_sign_in" and "super-secret-password" not in text


def test_local_tools_keep_their_signatures_for_the_mcp_schema():
    import inspect
    assert list(inspect.signature(mcp_server.create_backend.__wrapped__).parameters)[:3] == ["workspace", "source", "name"]
