"""silver_notebook_draft / create_silver_notebook: the plan of the notebook, its PySpark code, the same steps run in
Python on the shop seed with duplicates and broken references added, the guarantee that no source table is ever a
write target, and the REST calls (mocked). The generated notebook itself runs on a local Spark session in
tests/test_spark_notebooks.py when PySpark is installed."""
import ast
import base64
import datetime
import json

import pytest

from fabric_backend import notebook, seed, silver
from fabric_backend.infer import PlanInputError, plan

INFO = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse",
            schema="shop", schemas_enabled=True)
SHIP_TO = [{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}]


def shop_plan(confirmed=None):
    return plan(seed.schema("shop"), None, confirmed)


from silver_cases import EXPECTED_QUARANTINE, counts, seed_rows  # noqa: E402


# ------------------------------------------------------------------ the plan of the notebook --------------------

def test_spec_orders_parents_first_and_names_every_rule():
    s = silver.spec(shop_plan(), INFO, order_by={"orders": "order_date"})
    order = [t["table"] for t in s["tables"]]
    assert order.index("customers") < order.index("orders") < order.index("order_items")
    assert order.index("products") < order.index("order_items") and order.index("categories") < order.index("products")
    by = {t["table"]: t for t in s["tables"]}
    assert by["order_items"]["key"] == ["order_id", "line_no"] and by["order_items"]["key_rule"] == "K5"
    assert by["audit_log"]["key"] == [] and by["audit_log"]["key_rule"] == "K3"
    assert by["orders"]["order_by"] == "order_date" and by["orders"]["order_why"] == "given in order_by"
    assert by["customers"]["order_by"] is None
    assert [(c["parent"], c["rule"], c["parent_from"]) for c in by["order_items"]["checks"]] == [("orders", "R1", "silver"), ("products", "R1", "silver")]
    assert by["orders"]["target"] == ["silver", "orders"] and s["quarantine"] == ["silver", "krusgraph_quarantine"]


def test_an_ordering_column_is_found_by_its_name():
    from fabric_backend.schema import Column, Schema, Table
    sch = Schema(schema="dbo")
    sch.tables["customers"] = Table("customers", [Column("customer_id", "int"), Column("name", "varchar"), Column("LastModified", "datetime2")], schema="dbo")
    sch.tables["orders"] = Table("orders", [Column("order_id", "int"), Column("customer_id", "int"), Column("_ingested_at", "datetime2")], schema="dbo")
    s = silver.spec(plan(sch), dict(INFO, schema="dbo"))
    by = {t["table"]: t for t in s["tables"]}
    assert by["customers"]["order_by"] == "LastModified" and by["orders"]["order_by"] == "_ingested_at"
    assert "load or change time" in by["orders"]["order_why"]


def test_bad_inputs_are_refused_before_anything_is_generated():
    p = shop_plan()
    for kwargs, needle in (({"silver_schema": "shop"}, "source schema"), ({"silver_schema": "my silver"}, "letters"),
                           ({"order_by": {"orders": "nope"}}, "no column"), ({"order_by": {"nope": "x"}}, "not in the schema"),
                           ({"tables": ["nope"]}, "not in the schema")):
        with pytest.raises(PlanInputError, match=needle):
            silver.spec(p, INFO, **kwargs)


def test_no_source_table_is_ever_a_write_target():
    """Every combination the tool accepts: schemas or not, any silver schema name, a source table named like a target."""
    from fabric_backend.schema import Column, Schema, Table
    p = shop_plan(SHIP_TO)
    for schemas_enabled in (True, False):
        for name in ("silver", "clean", "SILVER", "gold_v2"):
            s = silver.spec(p, dict(INFO, schemas_enabled=schemas_enabled), silver_schema=name)
            assert not set(silver.written_tables(s)) & set(silver.source_tables(s)), (schemas_enabled, name)
            code = silver.notebook_source(s)
            assert "saveAsTable(name)" in code and code.count("saveAsTable") == 1               # one write path, through the guard
            assert ".write" not in code.replace("df.write.format(TABLE_FORMAT)", "")
    # a lakehouse without schemas, planned again after the first run: its silver_* tables and the quarantine table are
    # the notebook's own outputs, not sources (a table named like that which the notebook did not write is protected by
    # the run-time mark, tests/test_spark_notebooks.py)
    sch = seed.schema("dbo")
    for t in list(sch.tables) + ["krusgraph_quarantine"]:
        sch.tables[f"silver_{t}"] = Table(f"silver_{t}", [Column("x", "int")], schema="dbo")
    s = silver.spec(plan(sch), dict(INFO, schema="dbo", schemas_enabled=False))
    assert sorted(t["table"] for t in s["tables"]) == sorted(seed.schema("dbo").tables)
    assert not set(silver.written_tables(s)) & set(silver.source_tables(s))
    # with schemas a table of that name in the source schema is a source like any other
    sch = seed.schema("shop")
    sch.tables["silver_orders"] = Table("silver_orders", [Column("x", "int")], schema="shop")
    assert "silver_orders" in [t["table"] for t in silver.spec(plan(sch), INFO)["tables"]]


def test_the_ownership_mark_names_the_source():
    one = silver.notebook_source(silver.spec(shop_plan(), INFO))
    two = silver.notebook_source(silver.spec(shop_plan(), dict(INFO, item_id="lh-2")))
    assert 'OWNER = "lh-1/shop"' in one and 'OWNER = "lh-2/shop"' in two
    assert "props.get(\"krusgraph.silver\") == OWNER" in one


def test_the_notebook_guards_at_run_time_too():
    code = silver.notebook_source(silver.spec(shop_plan(), INFO))
    assert "is a source table; choose another SILVER_SCHEMA. Nothing was written." in code
    assert "was not written by this notebook" in code and "krusgraph.silver" in code
    assert "DROP " not in code.upper().replace("DROP_NULL_KEYS", "") and "DELETE" not in code.upper() and "TRUNCATE" not in code.upper()


# ------------------------------------------------------------------ the notebook text ----------------------------

def test_notebook_is_fabric_source_with_the_lakehouse_attached_and_valid_python():
    s = silver.spec(shop_plan(), INFO, order_by={"orders": "order_date"})
    text = silver.notebook_source(s)
    assert text.startswith("# Fabric notebook source\n\n# METADATA ********************\n")
    meta = json.loads("\n".join(x[7:] if x.startswith("# META ") else "" for x in text.split("# MARKDOWN")[0].splitlines() if x.startswith("# META")))
    assert meta["kernel_info"] == {"name": "synapse_pyspark"}
    assert meta["dependencies"]["lakehouse"] == {"default_lakehouse": "lh-1", "default_lakehouse_name": "shop_lh",
                                                  "default_lakehouse_workspace_id": INFO["workspace_id"]}
    cells = notebook.parse(text)
    assert [k for k, _ in cells][:3] == ["markdown", "parameters", "code"] and cells[0][1].startswith("# Silver tables for shop_lh.shop")
    for kind, code in cells:
        if kind != "markdown":
            ast.parse(code)
    assert cells == silver.cells(s)                                                       # the text round-trips
    tables_cells = {c.split("\n", 1)[0]: c for k, c in cells if c.startswith("# ---- ")}
    orders = tables_cells["# ---- orders -> silver.orders ----"]
    assert "rule K2" in orders and "Latest row wins by order_date (given in order_by)" in orders and "rule R1" in orders
    assert "keep_latest(df, [\"order_id\"], \"order_date\"" in orders
    items = tables_cells["# ---- order_items -> silver.order_items ----"]
    assert "rule K5" in items and "rows whose orders was quarantined follow it there" in items
    assert "No key (rule K3" in tables_cells["# ---- audit_log -> silver.audit_log ----"]
    assert silver.notebook_source(s) == text                                              # deterministic


def test_without_schemas_the_targets_carry_a_prefix():
    s = silver.spec(seed and plan(seed.schema("dbo")), dict(INFO, schema="dbo", schemas_enabled=False), silver_schema="silver")
    assert s["tables"][0]["target"][0] is None and s["tables"][0]["target"][1].startswith("silver_")
    code = silver.notebook_source(s)
    assert "SCHEMAS_ENABLED = False" in code and "SOURCE_SCHEMA = null" not in code and "SOURCE_SCHEMA = None" in code


def test_envelope_is_the_specification_layout():
    body = notebook.envelope("silver_shop", "# Fabric notebook source\n", "d" * 300)
    assert body["displayName"] == "silver_shop" and len(body["description"]) == 256
    assert body["definition"]["format"] == "fabricGitSource"
    parts = {p["path"]: base64.b64decode(p["payload"]).decode() for p in body["definition"]["parts"]}
    assert set(parts) == {"notebook-content.py", ".platform"} and parts["notebook-content.py"] == "# Fabric notebook source\n"
    assert json.loads(parts[".platform"])["metadata"] == {"type": "Notebook", "displayName": "silver_shop"}


# ------------------------------------------------------------------ the steps on the seed ------------------------

def test_python_steps_deduplicate_and_quarantine_on_the_seed():
    s = silver.spec(shop_plan(), INFO, order_by={"orders": "order_date"})
    data = seed_rows()
    out = silver.simulate(s, data)
    assert counts(out["quarantine"]) == EXPECTED_QUARANTINE
    sil = out["silver"]
    assert len(sil["customers"]) == 10 and len(sil["orders"]) == 60 and len(sil["order_items"]) == len(seed.rows()["order_items"])
    assert len(sil["products"]) == 9 and len(sil["audit_log"]) == 40 and len(sil["categories"]) == 3
    assert next(o for o in sil["orders"] if o["order_id"] == 100)["order_date"] == datetime.date(2026, 12, 1)   # the latest version won
    assert any(p["category_id"] is None for p in sil["products"])                            # a NULL reference is not an error
    # every row read is either in silver or in quarantine, exactly once
    for t, rows in data.items():
        assert len(rows) == len(sil[t]) + sum(1 for q in out["quarantine"] if q["source_table"] == t), t
    assert silver.simulate(s, data) == out                                                   # idempotent: a re-run gives the same


def test_a_confirmed_relationship_is_checked_too():
    s = silver.spec(shop_plan(SHIP_TO), INFO)
    data = seed_rows()
    data["orders"].append({"order_id": 201, "customer_id": 1, "order_date": datetime.date(2026, 10, 3), "ship_to_id": 4242})
    out = silver.simulate(s, data)
    assert ("orders", "confirmed", "ship_to_id has no row in addresses (orders.ship_to_id = addresses.address_id)") in counts(out["quarantine"])


# ------------------------------------------------------------------ the tools (REST mocked) ----------------------

import requests  # noqa: E402

from fabric_backend import server  # noqa: E402
from fabric_backend.schema import Schema  # noqa: E402

WS = INFO["workspace_id"]


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


@pytest.fixture
def shop(monkeypatch):
    import importlib
    deploy = importlib.import_module("fabric_backend.deploy")
    kind = {"type": "Lakehouse"}
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": kind["type"], "id": "lh-1", "displayName": src,
                                                                             "sql_host": "x.datawarehouse.fabric.microsoft.com", "sql_db": src,
                                                                             "schemas_enabled": True})
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: []))
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    monkeypatch.setattr(deploy.time, "sleep", lambda s: None)
    return kind


def test_draft_returns_the_steps_and_the_notebook_and_creates_nothing(shop, monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("a draft never posts"))
    out = json.loads(server.silver_notebook_draft("Sales", "shop_lh", schema="shop", order_by={"orders": "order_date"}))
    assert "error" not in out and out["notebook"]["content"].startswith("# Fabric notebook source")
    assert [s["table"] for s in out["steps"]][-1] == "order_items" and "krusgraph_quarantine" in out["summary"]
    assert next(s for s in out["steps"] if s["table"] == "orders")["deduplicate_on"]["latest_by"] == "order_date"
    from fabric_backend import tool_status
    assert "has not run in a Fabric workspace" in out["note"] and tool_status.answer_note("silver_notebook_draft") in out["note"]
    bad = json.loads(server.silver_notebook_draft("Sales", "shop_lh", schema="shop", silver_schema="shop"))
    assert bad["kind"] == "bad_input" and "source schema" in bad["error"]


def test_create_silver_notebook_dry_run_then_create_then_update_in_place(shop, monkeypatch):
    posted = []
    monkeypatch.setattr(requests, "post", lambda url, **k: posted.append(url) or Resp(500))
    out = json.loads(server.create_silver_notebook("Sales", "shop_lh", name="silver_shop", schema="shop"))
    assert out["dry_run"] is True and posted == [] and out["rest"]["url"].endswith(f"/workspaces/{WS}/notebooks")
    assert out["rest"]["delegated_scope"] == "Notebook.ReadWrite.All (or Item.ReadWrite.All)" and "a96c37a" in out["rest"]["spec"]
    calls, items = [], {"value": []}
    polls = iter([Resp(200, {"status": "Running"}), Resp(200, {"status": "Succeeded"})])
    monkeypatch.setattr(requests, "get", lambda url, **k: next(polls) if "/operations/" in url else Resp(200, items))
    monkeypatch.setattr(requests, "post", lambda url, **k: calls.append((url, k.get("json"))) or Resp(202, None, {"x-ms-operation-id": "op-1"}))
    out = json.loads(server.create_silver_notebook("Sales", "shop_lh", name="silver_shop", schema="shop", dry_run=False))
    assert out["result"]["status"] == "Succeeded" and out["result"]["mode"] == "created" and "error" not in out
    url, body = calls[0]
    assert url.endswith(f"/workspaces/{WS}/notebooks") and body["displayName"] == "silver_shop"
    parts = {p["path"]: base64.b64decode(p["payload"]).decode() for p in body["definition"]["parts"]}
    assert parts["notebook-content.py"].startswith("# Fabric notebook source") and '"default_lakehouse": "lh-1"' in parts["notebook-content.py"]
    assert "content" not in out["notebook"]                                              # sent to Fabric, not repeated
    items["value"] = [{"id": "nb-1", "displayName": "silver_shop", "type": "Notebook"}]
    calls.clear()
    monkeypatch.setattr(requests, "post", lambda url, **k: calls.append((url, k.get("json"))) or Resp(200, None))
    out = json.loads(server.create_silver_notebook("Sales", "shop_lh", name="silver_shop", schema="shop", dry_run=False))
    assert out["result"] == {"status": "Succeeded", "mode": "updated", "id": "nb-1"}
    assert calls[0][0].endswith("/notebooks/nb-1/updateDefinition") and set(calls[0][1]) == {"definition"}
    assert not any("delete" in u.lower() for u, _ in calls)


def test_create_silver_notebook_403_is_consent_with_the_exact_scope(shop, monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, **k: Resp(200, {"value": []}))
    monkeypatch.setattr(requests, "post", lambda url, **k: Resp(403, {"errorCode": "InsufficientScopes", "message": "The caller does not have the required scopes"}))
    out = json.loads(server.create_silver_notebook("Sales", "shop_lh", name="silver_shop", schema="shop", dry_run=False))
    assert out["kind"] == "consent" and "Notebook.ReadWrite.All" in out["hint"] and "fabric-token" not in json.dumps(out)


def test_a_warehouse_source_is_unsupported_with_the_way_round(shop):
    shop["type"] = "Warehouse"
    for out in (json.loads(server.silver_notebook_draft("Sales", "wh", schema="shop")),
                json.loads(server.create_silver_notebook("Sales", "wh", name="x", schema="shop", dry_run=False))):
        assert out["kind"] == "unsupported" and "shortcut" in out["hint"]


def test_a_table_that_points_at_itself_loses_the_rows_under_a_quarantined_parent():
    from fabric_backend.schema import Column, Schema, Table
    sch = Schema(schema="hr")
    sch.tables["employees"] = Table("employees", [Column("employee_id", "int"), Column("name", "varchar"), Column("manager_id", "int")], schema="hr")
    p = plan(sch, None, [{"source": "employees", "source_cols": ["manager_id"], "target": "employees", "target_cols": ["employee_id"]}])
    s = silver.spec(p, dict(INFO, schema="hr"))
    rows = [{"employee_id": 1, "name": "a", "manager_id": None}, {"employee_id": 2, "name": "b", "manager_id": 1},
            {"employee_id": 3, "name": "c", "manager_id": 99}, {"employee_id": 4, "name": "d", "manager_id": 3},
            {"employee_id": 5, "name": "e", "manager_id": 4}]
    out = silver.simulate(s, {"employees": rows})
    assert [r["employee_id"] for r in out["silver"]["employees"]] == [1, 2]
    assert sorted(q["row"]["employee_id"] for q in out["quarantine"]) == [3, 4, 5]
    code = silver.notebook_source(s)
    assert "for _round in range(100):" in code and "again until no more rows drop out" in code
