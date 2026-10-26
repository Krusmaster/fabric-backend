"""The local server against SQL Server on-prem, with the metadata queries run for real against recorded answers of the
INFORMATION_SCHEMA views (SQLite with an attached database named INFORMATION_SCHEMA holds the recordings, so the exact
query text of schema.py executes). No SQL Server runs in the sandbox; this is the stand-in the task asked for.

Recorded: two schemas (shop and audit) whose constraints share names (PK_orders, FK_orders_customers), a table with a
space in its name and a composite declared key, nvarchar(max), datetimeoffset, uniqueidentifier, decimal, a computed
column, and a view. These are the SQL Server shapes a first on-prem user hits."""
import json
import sqlite3

import pytest

from fabric_backend import dbt, evidence, mcp_server, semantic_model
from fabric_backend.infer import plan
from fabric_backend.schema import Schema

COLUMNS = [
    # (schema, table, column, data_type, ordinal)
    ("shop", "customers", "customer_id", "int", 1), ("shop", "customers", "customer_no", "uniqueidentifier", 2),
    ("shop", "customers", "name", "nvarchar", 3), ("shop", "customers", "notes", "nvarchar", 4),
    ("shop", "orders", "order_id", "int", 1), ("shop", "orders", "customer_id", "int", 2),
    ("shop", "orders", "placed_at", "datetimeoffset", 3), ("shop", "orders", "total_amount", "decimal", 4),
    ("shop", "orders", "total_with_vat", "decimal", 5),                                  # a computed column
    ("shop", "Order Lines", "order_id", "int", 1), ("shop", "Order Lines", "line_no", "int", 2),
    ("shop", "Order Lines", "product_id", "int", 3), ("shop", "Order Lines", "quantity", "decimal", 4),
    ("shop", "products", "product_id", "int", 1), ("shop", "products", "name", "nvarchar", 2),
    ("shop", "vw_open_orders", "order_id", "int", 1), ("shop", "vw_open_orders", "name", "nvarchar", 2),   # a view
    ("audit", "orders", "order_id", "int", 1), ("audit", "orders", "event_id", "int", 2),
    ("audit", "events", "event_id", "int", 1), ("audit", "events", "what", "nvarchar", 2),
]
TABLES = [("shop", "customers", "BASE TABLE"), ("shop", "orders", "BASE TABLE"), ("shop", "Order Lines", "BASE TABLE"),
          ("shop", "products", "BASE TABLE"), ("shop", "vw_open_orders", "VIEW"), ("audit", "orders", "BASE TABLE"), ("audit", "events", "BASE TABLE")]
# TABLE_CONSTRAINTS: (constraint_schema, constraint_name, table_schema, table_name, constraint_type)
CONSTRAINTS = [
    ("shop", "PK_customers", "shop", "customers", "PRIMARY KEY"), ("shop", "PK_orders", "shop", "orders", "PRIMARY KEY"),
    ("shop", "PK_order_lines", "shop", "Order Lines", "PRIMARY KEY"), ("shop", "PK_products", "shop", "products", "PRIMARY KEY"),
    ("shop", "FK_orders_customers", "shop", "orders", "FOREIGN KEY"), ("shop", "FK_lines_orders", "shop", "Order Lines", "FOREIGN KEY"),
    ("shop", "FK_lines_products", "shop", "Order Lines", "FOREIGN KEY"),
    ("audit", "PK_orders", "audit", "orders", "PRIMARY KEY"), ("audit", "PK_events", "audit", "events", "PRIMARY KEY"),
    ("audit", "FK_orders_customers", "audit", "orders", "FOREIGN KEY"),                   # same name, other schema, other target
]
# KEY_COLUMN_USAGE: (constraint_schema, constraint_name, table_schema, table_name, column_name, ordinal)
USAGE = [
    ("shop", "PK_customers", "shop", "customers", "customer_id", 1), ("shop", "PK_orders", "shop", "orders", "order_id", 1),
    ("shop", "PK_order_lines", "shop", "Order Lines", "order_id", 1), ("shop", "PK_order_lines", "shop", "Order Lines", "line_no", 2),
    ("shop", "PK_products", "shop", "products", "product_id", 1),
    ("shop", "FK_orders_customers", "shop", "orders", "customer_id", 1),
    ("shop", "FK_lines_orders", "shop", "Order Lines", "order_id", 1), ("shop", "FK_lines_products", "shop", "Order Lines", "product_id", 1),
    ("audit", "PK_orders", "audit", "orders", "order_id", 1), ("audit", "PK_events", "audit", "events", "event_id", 1),
    ("audit", "FK_orders_customers", "audit", "orders", "event_id", 1),
]
# REFERENTIAL_CONSTRAINTS: (constraint_schema, constraint_name, unique_constraint_schema, unique_constraint_name)
REFERENTIAL = [
    ("shop", "FK_orders_customers", "shop", "PK_customers"), ("shop", "FK_lines_orders", "shop", "PK_orders"),
    ("shop", "FK_lines_products", "shop", "PK_products"), ("audit", "FK_orders_customers", "audit", "PK_events"),
]


def recorded_execute():
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS INFORMATION_SCHEMA")
    con.execute("CREATE TABLE INFORMATION_SCHEMA.COLUMNS (TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, ORDINAL_POSITION)")
    con.execute("CREATE TABLE INFORMATION_SCHEMA.TABLES (TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE)")
    con.execute("CREATE TABLE INFORMATION_SCHEMA.TABLE_CONSTRAINTS (CONSTRAINT_SCHEMA, CONSTRAINT_NAME, TABLE_SCHEMA, TABLE_NAME, CONSTRAINT_TYPE)")
    con.execute("CREATE TABLE INFORMATION_SCHEMA.KEY_COLUMN_USAGE (CONSTRAINT_SCHEMA, CONSTRAINT_NAME, TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, ORDINAL_POSITION)")
    con.execute("CREATE TABLE INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS (CONSTRAINT_SCHEMA, CONSTRAINT_NAME, UNIQUE_CONSTRAINT_SCHEMA, UNIQUE_CONSTRAINT_NAME)")
    con.executemany("INSERT INTO INFORMATION_SCHEMA.COLUMNS VALUES (?,?,?,?,?)", COLUMNS)
    con.executemany("INSERT INTO INFORMATION_SCHEMA.TABLES VALUES (?,?,?)", TABLES)
    con.executemany("INSERT INTO INFORMATION_SCHEMA.TABLE_CONSTRAINTS VALUES (?,?,?,?,?)", CONSTRAINTS)
    con.executemany("INSERT INTO INFORMATION_SCHEMA.KEY_COLUMN_USAGE VALUES (?,?,?,?,?,?)", USAGE)
    con.executemany("INSERT INTO INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS VALUES (?,?,?,?)", REFERENTIAL)
    sent = []

    def execute(sql):
        sent.append(sql)
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    execute.sent = sent
    execute.close = lambda: None                                   # the tools close after use; the test reuses one connection
    return execute


def test_declared_keys_and_foreign_keys_become_k0_and_r0_and_the_other_schema_does_not_leak():
    execute = recorded_execute()
    s = Schema.from_sql(execute, "shop")
    assert set(s.tables) == {"customers", "orders", "Order Lines", "products", "vw_open_orders"}
    assert s.tables["Order Lines"].keys == ["order_id", "line_no"] and s.tables["customers"].keys == ["customer_id"]
    assert s.tables["orders"].foreign_keys == [(["customer_id"], "customers", ["customer_id"])]
    assert sorted(fk[1] for fk in s.tables["Order Lines"].foreign_keys) == ["orders", "products"]
    p = plan(s)
    assert p.keys["Order Lines"] == (["order_id", "line_no"], "K0") and p.keys["orders"] == (["order_id"], "K0")
    rels = {(r.source, r.target): r.rule for r in p.relationships}
    assert rels == {("orders", "customers"): "R0", ("Order Lines", "orders"): "R0", ("Order Lines", "products"): "R0",
                    ("vw_open_orders", "orders"): "R1"}                                   # the view is read like a table: its order_id links by name
    assert "vw_open_orders" in p.keyless and "events" not in {r.target for r in p.relationships}     # the view is planned, audit's FK is not ours
    audit = plan(Schema.from_sql(execute, "audit"))
    assert audit.keys["orders"] == (["order_id"], "K0") and {(r.source, r.target, r.rule) for r in audit.relationships} == {("orders", "events", "R0")}
    assert "UPPER(TABLE_SCHEMA) = UPPER('shop')" in execute.sent[0] and "CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA" in execute.sent[1]


def test_sql_server_shapes_survive_quoting_types_and_the_drafts():
    s = Schema.from_sql(recorded_execute(), "shop")
    p = plan(s)
    assert evidence.key_sql("shop", "Order Lines", ["order_id", "line_no"]).startswith("SELECT COUNT_BIG(*)") and "[shop].[Order Lines]" in evidence.key_sql("shop", "Order Lines", ["order_id", "line_no"])
    assert "[Order Lines]" in evidence.relationship_sql("shop", "Order Lines", ["order_id"], "orders", ["order_id"])
    assert evidence.sample_sql("shop", "Order Lines", ["order_id", "line_no"], 5) == "SELECT TOP (5) [order_id], [line_no] FROM [shop].[Order Lines]"
    info = dict(workspace_id="", item_id="", item_name="shopdb", item_kind="Warehouse", schema="shop", sql_endpoint="sql01", sql_db="shopdb", schemas_enabled=True)
    parts = semantic_model.draft(p, info, "m")["parts"]
    orders = parts["definition/tables/orders.tmdl"]
    assert "column placed_at\n\t\tdataType: dateTime" in orders and "column total_amount\n\t\tdataType: decimal" in orders
    assert "column customer_no\n\t\tdataType: string" in parts["definition/tables/customers.tmdl"]
    assert "table 'Order Lines'" in parts["definition/tables/Order Lines.tmdl"]
    yml = dbt.schema_yml(p, "shop", "shop", database="shopdb")
    assert '      - name: "Order Lines"' in yml and "to: source('shop', 'orders')" in yml


def test_source_kind_sqlserver_plans_and_documents_but_explains_the_fabric_only_drafts(monkeypatch):
    execute = recorded_execute()
    monkeypatch.setattr(mcp_server, "_execute_factory", lambda schema: execute)
    monkeypatch.setenv("FABRIC_ODBC", "Driver={ODBC Driver 18 for SQL Server};Server=sql01;Database=shopdb;Trusted_Connection=yes;TrustServerCertificate=yes")
    monkeypatch.setenv("FABRIC_SOURCE_KIND", "sqlserver")
    assert mcp_server._source_info("shop")["item_kind"] == "SQLServer"
    out = json.loads(mcp_server.plan_backend("shop"))
    assert out["summary"].startswith("5 tables, 4 with keys, 4 relationships") and out["keys"]["Order Lines"]["rule"] == "K0"
    out = json.loads(mcp_server.dbt_schema(schema="shop"))
    assert "database: shopdb" in out["yaml"]
    out = json.loads(mcp_server.data_dictionary(schema="shop"))
    assert "# Data dictionary: shopdb / shop" in out["markdown"]
    out = json.loads(mcp_server.semantic_model_draft("m", schema="shop"))
    assert out["kind"] == "unsupported" and "Direct Lake" in out["error"] and "Power BI Desktop" in out["hint"]
    out = json.loads(mcp_server.ontology_draft("o", schema="shop"))
    assert out["kind"] == "unsupported" and "Fabric" in out["error"]
    out = json.loads(mcp_server.create_views(schema="shop"))
    assert out["dry_run"] is True and out["schema"] == "krusgraph"                     # T-SQL views work on SQL Server too
