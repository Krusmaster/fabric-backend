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


def sqlite_execute():
    """The seed rows in SQLite, with the few T-SQL spellings the engine uses rewritten. Schema prefixes are dropped:
    a SQLite view cannot reference an attached database, so tables and views share the one database."""
    import datetime
    import re
    import sqlite3
    con = sqlite3.connect(":memory:")
    for name, ddl in seed.SCHEMAS.items():
        con.execute(f"CREATE TABLE [{name}] ({ddl})")
        data = [tuple(v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v for v in r) for r in seed.rows()[name]]
        con.executemany(f"INSERT INTO [{name}] VALUES ({','.join('?' * len(data[0]))})", data)
    ran = []

    def execute(sql):
        sql = re.sub(r"\[(shop|krusgraph)\]\.", "", sql).replace("COUNT_BIG(", "COUNT(")
        sql = re.sub(r"SELECT TOP \((\d+)\) (.*)", lambda m: f"SELECT {m.group(2)} LIMIT {m.group(1)}", sql, flags=re.S)
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def statement(sql):
        ran.append(sql)
        if sql.startswith("IF NOT EXISTS"):
            return                                                             # sys.schemas: not in SQLite
        con.execute(re.sub(r"\[(shop|krusgraph)\]\.", "", sql).replace("CREATE OR ALTER VIEW", "CREATE VIEW"))
    execute.statement = statement
    execute.ran = ran
    execute.closed = []
    execute.close = lambda: execute.closed.append(1)                           # the tools close after use; the fixture reuses one connection
    return execute


@pytest.fixture
def local_shop_with_rows(monkeypatch):
    execute = sqlite_execute()
    monkeypatch.setattr(mcp_server, "_execute_factory", lambda schema: execute)
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    monkeypatch.setenv("FABRIC_ODBC", "Driver={ODBC Driver 18 for SQL Server};Server=x.datawarehouse.fabric.microsoft.com;Database=shop_lh;Authentication=ActiveDirectoryInteractive")
    monkeypatch.delenv("FABRIC_SOURCE_KIND", raising=False)
    monkeypatch.delenv("FABRIC_SCHEMAS_ENABLED", raising=False)
    return execute


def test_local_drafts_and_analyses_from_the_odbc_source(local_shop_with_rows):
    out = json.loads(mcp_server.semantic_model_draft("shop_model", schema="shop"))
    assert out["summary"]["tables"] == 7 and 'Sql.Database("x.datawarehouse.fabric.microsoft.com", "shop_lh")' in out["parts"]["definition/expressions.tmdl"]
    assert "schemaName: shop" in out["parts"]["definition/tables/orders.tmdl"] and "Drafted locally" in out["note"]
    out = json.loads(mcp_server.join_path("customers", "categories", schema="shop"))
    assert out["paths"][0]["hops"] == 4 and out["safest"]["why"] == "the shortest path is also the safest"
    out = json.loads(mcp_server.data_dictionary(schema="shop"))
    assert out["path"] == "docs/shop-data-dictionary.md" and "# Data dictionary: shop_lh / shop" in out["markdown"]
    out = json.loads(mcp_server.data_dictionary(schema="shop", validate=True))
    assert "## Checked against the data" in out["markdown"] and "| order_items | order_id+line_no | 134 | 0 | 134 |" in out["markdown"]
    out = json.loads(mcp_server.dbt_schema(schema="shop"))
    assert out["path"] == "models/sources/shop.yml" and "database: shop_lh" in out["yaml"] and "source('shop', 'customers')" in out["yaml"]
    out = json.loads(mcp_server.analyze_schema(schema="shop"))
    assert out["roles"]["order_items"]["role"] == "fact" and out["summary"].startswith("7 tables, 6 with keys")
    out = json.loads(mcp_server.validate_plan(schema="shop"))
    assert out["summary"] == "6 of 6 keys unique, 6 of 6 relationships hold without orphans"
    out = json.loads(mcp_server.sample_rows("orders", schema="shop", n=3))
    assert out["table"] == "orders" and len(out["rows"]) == 3 and "order_id" in out["rows"][0]
    out = json.loads(mcp_server.suggest_relationships(schema="shop", check=4))
    assert out["candidates"][0]["target"] == "addresses" and out["candidates"][0]["evidence"]["inclusion"] == 1.0 and out["checked_against_data"] == 4
    assert json.loads(mcp_server.sample_rows("ghost", schema="shop"))["kind"] == "bad_input"
    assert len(local_shop_with_rows.closed) == 10                            # every tool that ran queries closed its connection


def test_local_create_views_dry_run_then_apply(local_shop_with_rows):
    execute = local_shop_with_rows
    confirmed = [{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}]
    out = json.loads(mcp_server.create_views(schema="shop", confirmed=confirmed))
    assert out["dry_run"] is True and [v["name"] for v in out["views"]] == ["vw_order_items", "vw_orders", "vw_orders_ship_to"] and execute.ran == []
    out = json.loads(mcp_server.create_views(schema="shop", confirmed=confirmed, dry_run=False))
    assert out["result"] == {"status": "Succeeded", "views": 3, "schema": "krusgraph"} and len(execute.ran) == 4
    assert execute("SELECT COUNT(*) AS n FROM [vw_order_items]")[0]["n"] == 134
    assert execute("SELECT COUNT(*) AS n FROM [vw_orders] WHERE [addresses_city] IS NOT NULL AND [customers_name] IS NOT NULL")[0]["n"] == 60


def test_semantic_model_draft_reads_kind_and_schema_flag_from_the_environment(local_shop_with_rows, monkeypatch):
    monkeypatch.setenv("FABRIC_SCHEMAS_ENABLED", "1")
    out = json.loads(mcp_server.semantic_model_draft("m", schema="dbo"))
    assert "schemaName: dbo" in out["parts"]["definition/tables/orders.tmdl"]
    monkeypatch.setenv("FABRIC_SOURCE_KIND", "Warehouse")
    monkeypatch.delenv("FABRIC_SCHEMAS_ENABLED")
    out = json.loads(mcp_server.semantic_model_draft("m", schema="dbo"))
    assert "schemaName: dbo" in out["parts"]["definition/tables/orders.tmdl"] and "Warehouse" in out["parts"]["README.generated.md"]
    assert set(json.loads(mcp_server.plan_backend("dbo"))["keys"]) == {"customers", "categories", "products", "addresses", "orders", "order_items"}


def test_missing_fabric_odbc_is_a_configuration_error_not_not_found(monkeypatch):
    monkeypatch.delenv("FABRIC_ODBC", raising=False)
    out = json.loads(mcp_server.list_tables("shop"))
    assert out["kind"] == "server_config" and "FABRIC_ODBC" in out["error"]


def test_odbc_string_parsing_handles_braces_quotes_and_synonyms(monkeypatch):
    monkeypatch.setenv("FABRIC_ODBC", "Driver={ODBC Driver 18 for SQL Server};Server={h;x.fabric.microsoft.com};Database=\"shop lh\";Authentication=ActiveDirectoryInteractive")
    assert mcp_server._odbc_part("Server") == "h;x.fabric.microsoft.com" and mcp_server._odbc_part("Database") == "shop lh"
    monkeypatch.setenv("FABRIC_ODBC", "Driver=x;Network Address=host.example;Initial Catalog=lh")
    assert mcp_server._odbc_part("Server") == "host.example" and mcp_server._odbc_part("Database") == "lh"
    monkeypatch.setenv("FABRIC_ODBC", "Driver=x;Authentication=ActiveDirectoryInteractive")
    info = mcp_server._source_info("shop")
    assert info["sql_endpoint"] == "" and info["sql_db"] == "" and info["item_name"] == ""
    monkeypatch.setenv("FABRIC_SOURCE_KIND", "lakehouse")                   # case does not matter
    assert mcp_server._source_info("dbo")["item_kind"] == "Lakehouse" and mcp_server._source_info("dbo")["schemas_enabled"] is None
    monkeypatch.setenv("FABRIC_SOURCE_KIND", "WAREHOUSE")
    assert mcp_server._source_info("dbo")["item_kind"] == "Warehouse" and mcp_server._source_info("dbo")["schemas_enabled"] is True


def test_drafts_keep_their_placeholders_when_the_odbc_string_names_no_database(local_shop_with_rows, monkeypatch):
    monkeypatch.setenv("FABRIC_ODBC", "Driver={ODBC Driver 18 for SQL Server};Authentication=ActiveDirectoryInteractive")
    out = json.loads(mcp_server.dbt_schema(schema="shop"))
    assert "database:" not in out["yaml"]
    out = json.loads(mcp_server.semantic_model_draft("m", schema="shop"))
    assert '"<source item name>"' in out["parts"]["definition/expressions.tmdl"] and '"source"' not in out["parts"]["definition/expressions.tmdl"]
    assert "# Data dictionary: source / shop" in json.loads(mcp_server.data_dictionary(schema="shop"))["markdown"]


def test_create_views_bad_schema_name_is_bad_input_and_a_failed_apply_keeps_the_log(local_shop_with_rows):
    execute = local_shop_with_rows
    assert json.loads(mcp_server.create_views(schema="shop", views_schema="bad-name"))["kind"] == "bad_input"
    confirmed = [{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}]
    real = execute.statement

    def refuse_second(sql):
        if "vw_orders_ship_to" in sql:
            raise RuntimeError("CREATE VIEW is not allowed on this endpoint")
        real(sql)
    execute.statement = refuse_second
    out = json.loads(mcp_server.create_views(schema="shop", confirmed=confirmed, dry_run=False))
    assert [a.get("status") for a in out["applied"]] == ["ok", "ok", "ok", None] and out["applied"][3]["name"] == "vw_orders_ship_to"
    assert "error" in out and "warehouse" in out["hint"] and "result" not in out


def test_local_tools_carry_titles_and_hints_like_the_remote_ones():
    import asyncio
    tools = asyncio.run(mcp_server.mcp.list_tools())
    hints = {t.name: (t.annotations.read_only_hint, t.annotations.destructive_hint) for t in tools}
    writing = ("create_backend", "create_views", "create_databricks_constraints", "create_databricks_pipeline")   # the last two: round n13
    assert len(hints) == 23 and all(t.title for t in tools)
    assert all(hints[k] == (False, True) for k in writing)
    assert all(v == (True, False) for k, v in hints.items() if k not in writing)


def test_local_answer_and_silver_drafts(local_shop, monkeypatch):
    out = json.loads(mcp_server.answer_query_draft("Hur många ordrar per kund?", ["orders", "customers"], schema="shop"))
    # customers.name looks like a person's name (rule P1): the key stands in unless show_personal_data=true
    assert out["tsql"].startswith("SELECT t1.[customer_id], COUNT_BIG(*)") and "graphql" not in out
    assert out["personal_data"]["left_out"] == ["customers.name (P1: a person's name)"]
    shown = json.loads(mcp_server.answer_query_draft("Hur många ordrar per kund?", ["orders", "customers"], schema="shop", show_personal_data=True))
    assert shown["tsql"].startswith("SELECT t1.[customer_id], t1.[name], COUNT_BIG(*)") and "personal_data" not in shown
    assert out["path"][0]["rule"] == "R1" and "FABRIC_ODBC" in out["runs"]
    assert json.loads(mcp_server.answer_query_draft("x", ["ghost"], schema="shop"))["kind"] == "bad_input"
    monkeypatch.setenv("FABRIC_SOURCE_KIND", "Lakehouse")
    monkeypatch.delenv("FABRIC_SCHEMAS_ENABLED", raising=False)
    out = json.loads(mcp_server.silver_notebook_draft(schema="shop", order_by={"orders": "order_date"}))
    text = out["notebook"]["content"]
    assert text.startswith("# Fabric notebook source") and '"dependencies"' not in text and "SCHEMAS_ENABLED = True" in text
    assert [s["table"] for s in out["steps"]][-1] == "order_items"
    out = json.loads(mcp_server.silver_notebook_draft(schema="dbo"))
    assert "SCHEMAS_ENABLED = False" in out["notebook"]["content"] and out["steps"][0]["writes"].startswith("silver_")
    monkeypatch.setenv("FABRIC_SOURCE_KIND", "SQLServer")
    assert json.loads(mcp_server.silver_notebook_draft(schema="shop"))["kind"] == "unsupported"
