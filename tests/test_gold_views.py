"""gold_views_draft / create_gold_views: materialized lake views over the silver tables. The generated SQL is checked
against the documented CREATE syntax, its SELECT runs with the rules on SQLite over the silver tables of the shop seed,
every column a view uses exists, and no target is ever a source or a silver table. The same SELECTs run on a local
Spark in tests/test_spark_notebooks.py."""
import base64
import json
import re
import sqlite3

import pytest
import requests

from fabric_backend import gold, privacy, seed, server, silver
from fabric_backend.infer import PlanInputError, plan
from fabric_backend.schema import Schema
from silver_cases import seed_rows
from test_inference_quality import load, names_only

INFO = dict(workspace_id="ws", item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse", schema="shop", schemas_enabled=True)
WS = "11111111-1111-1111-1111-111111111111"


def shop_plan(confirmed=None):
    return plan(seed.schema("shop"), None, confirmed)


# ------------------------------------------------------------------ the views --------------------------------------

def test_one_view_per_fact_table_over_the_safest_paths():
    s = gold.spec(shop_plan(), INFO)
    assert [v["name"] for v in s["views"]] == ["gold.audit_log", "gold.order_items", "gold.orders"]
    items = next(v for v in s["views"] if v["fact"] == "order_items")
    assert [(j["from"], j["to"], j["rule"]) for j in items["joins"]] == [
        ("order_items", "orders", "R1"), ("order_items", "products", "R1"), ("products", "categories", "R1"), ("orders", "customers", "R1")]
    assert [c["name"] for c in items["constraints"]] == ["order_items_key_present", "order_items_order_id_in_orders", "order_items_product_id_in_products",
                                                         "order_items_products_category_id_in_categories", "order_items_orders_customer_id_in_customers"]
    assert all("rule" in c["why"] for c in items["constraints"])
    # the safest path wins over the shortest: a declared or confirmed link (1.0) beats an R4 guess (0.5)
    confirmed = shop_plan([{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}])
    orders = next(v for v in gold.spec(confirmed, INFO)["views"] if v["fact"] == "orders")
    assert ("orders", "addresses", "confirmed") in [(j["from"], j["to"], j["rule"]) for j in orders["joins"]]
    assert [j["to"] for j in orders["joins"]].count("customers") == 1                        # each table once, over one path


def test_create_statement_follows_the_documented_syntax():
    """CREATE [OR REPLACE] MATERIALIZED LAKE VIEW [IF NOT EXISTS] schema.name [( CONSTRAINT name CHECK (condition) [ON MISMATCH
    DROP | FAIL], ... )] [PARTITIONED BY (...)] [COMMENT "..."] [TBLPROPERTIES ("key"="val", ...)] AS select (fabric-docs a2de7f9,
    data-engineering/materialized-lake-views/create-materialized-lake-view.md)."""
    s = gold.spec(shop_plan(), INFO)
    grammar = re.compile(r"^(?:--[^\n]*\n)*CREATE OR REPLACE MATERIALIZED LAKE VIEW `[a-z_]+`\.`[A-Za-z_][A-Za-z0-9_]*`\n"
                         r"(?:\(\n(?:    --[^\n]*\n    CONSTRAINT [a-z0-9_]+ CHECK \((?P<checks>.*?)\) ON MISMATCH (?:DROP|FAIL),?\n)+\)\n)?"
                         r'COMMENT "[^"\n]*"\nTBLPROPERTIES \("krusgraph\.gold"="[^"\n]*"\)\nAS\nSELECT\n', re.S)
    for st in gold.statements(s):
        assert grammar.match(st["sql"]), st["sql"][:400]
        assert "IF NOT EXISTS" not in st["sql"]                                   # can't be combined with OR REPLACE
        for line in st["sql"].splitlines():
            if line.strip().startswith("CONSTRAINT"):
                check = line.split(" CHECK ", 1)[1].rsplit(" ON MISMATCH", 1)[0]
                depth = 0
                for ch in check:
                    depth += {"(": 1, ")": -1}.get(ch, 0)
                    assert depth >= 0
                assert depth == 0 and not re.search(r"\b(rand|uuid|current_timestamp|now)\s*\(", check, re.I)   # deterministic only


def _silver_db(s, extra_orphan=False):
    """SQLite with the silver tables the silver notebook makes of the seed (silver.simulate), in an attached `silver` schema."""
    data = seed_rows()
    sim = silver.simulate(silver.spec(shop_plan(), INFO, order_by={"orders": "order_date"}), data)["silver"]
    if extra_orphan:
        sim["order_items"] = sim["order_items"] + [{"order_id": 100, "line_no": 9, "product_id": 999, "quantity": 1.0}]
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS silver")
    for t, rows in sim.items():
        cols = [c.split()[0] for c in seed.SCHEMAS[t].split(", ")]
        con.execute(f"CREATE TABLE silver.`{t}` ({', '.join('`' + c + '`' for c in cols)})")
        con.executemany(f"INSERT INTO silver.`{t}` VALUES ({', '.join('?' * len(cols))})",
                        [tuple(str(v) if hasattr(v, "isoformat") else v for v in (r.get(c) for c in cols)) for r in rows])   # dates as ISO text
    con.row_factory = sqlite3.Row

    def execute(sql):
        return [dict(r) for r in con.execute(sql).fetchall()]
    return sim, execute


def test_every_view_runs_with_its_rules_on_sqlite_over_the_silver_tables():
    s = gold.spec(shop_plan(), INFO)
    sim, execute = _silver_db(s)
    for v in s["views"]:
        rows = gold.run_select(v, s, execute)
        assert len(rows) == len(sim[v["fact"]]), v["name"]                       # silver is clean: no rule drops a row
        assert list(rows[0]) == [c["as"] for c in v["columns"]]
    items = next(v for v in s["views"] if v["fact"] == "order_items")
    row = next(r for r in gold.run_select(items, s, execute) if r["order_id"] == 100 and r["line_no"] == 1)
    assert row["orders_customer_id"] == row["customers_customer_id"] and row["categories_name"] in ("Bikes", "Tea", "Accessories")
    # a reference that finds nothing is dropped by its rule (what ON MISMATCH DROP does), a NULL reference is kept
    sim, execute = _silver_db(s, extra_orphan=True)
    rows = gold.run_select(items, s, execute)
    assert len(rows) == len(sim["order_items"]) - 1 and not any(r["product_id"] == 999 for r in rows)


def test_every_column_a_view_uses_exists_in_its_table():
    for p, info in ((shop_plan(), INFO), (plan(names_only(load("tpch"))), dict(INFO, schema="dbo")),
                    (plan(names_only(load("sakila"))), dict(INFO, schema="dbo"))):
        s = gold.spec(p, info)
        assert s["views"]
        for v in s["views"]:
            alias = {"f": v["fact"], **{j["alias"]: j["to"] for j in v["joins"]}}
            sql = gold.select_sql(v, s["silver_schema"])
            for a, col in re.findall(r"\b([fd]\d*)\.`([^`]+)`", sql):
                assert col in p.schema[alias[a]].column_names, (v["name"], a, col)
            outputs = {c["as"] for c in v["columns"]}
            for c in v["constraints"]:
                assert set(re.findall(r"`([^`]+)`", c["check"])) <= outputs, (v["name"], c["name"])
            assert len(outputs) == len(v["columns"])                              # no two output columns share a name


def test_no_target_is_ever_a_source_or_a_silver_table():
    for p, info in ((shop_plan(), INFO), (plan(names_only(load("tpch"))), dict(INFO, schema="dbo")),
                    (plan(names_only(load("sakila"))), dict(INFO, schema="dbo")), (plan(names_only(load("northwind"))), dict(INFO, schema="dbo"))):
        for gold_schema in ("gold", "analytics", "silver_gold"):
            s = gold.spec(p, info, gold_schema=gold_schema)
            protected = {f"{info['schema']}.{t.name}".lower() for t in p.schema} | {f"silver.{t.name}".lower() for t in p.schema}
            assert not set(gold.written(s)) & protected
            assert all(w.startswith(gold_schema + ".") for w in gold.written(s))
    for bad, why in (("shop", "source"), ("silver", "silver"), ("GOLD", "uppercase"), ("gold-x", "letters")):
        with pytest.raises(PlanInputError, match=why):
            gold.spec(shop_plan(), INFO, gold_schema=bad)
    with pytest.raises(PlanInputError, match="schemas"):
        gold.spec(shop_plan(), dict(INFO, schemas_enabled=False))


def test_the_notebook_guard_stops_before_a_protected_or_foreign_target():
    s = gold.spec(shop_plan(), INFO)
    cells = gold.cells(s)

    class Catalog:
        def __init__(self, existing):
            self.existing = existing

        def tableExists(self, name):
            return name.replace("`", "").lower() in self.existing

    class Spark:
        def __init__(self, existing, props=None):
            self.catalog, self.props, self.sql_run = Catalog(existing), props or {}, []

        def sql(self, text):
            self.sql_run.append(text)

            class Result:
                def __init__(self, rows):
                    self.rows = rows

                def collect(self):
                    return self.rows
            if text.startswith("SHOW TBLPROPERTIES"):
                name = text.split(" ", 2)[2].replace("`", "").lower()
                return Result(list(self.props.get(name, {}).items()))
            return Result([])

    silver_tables = {f"silver.{t}" for t in ("audit_log", "customers", "orders", "order_items", "products", "categories")}

    def run(spark, overrides=""):
        ns = {"spark": spark, "display": lambda x: None}
        for kind, code in cells:
            if kind == "markdown":
                continue
            exec(compile(code, "<notebook>", "exec"), ns)
            if kind == "parameters":
                exec(overrides, ns)
        return ns
    ok = Spark(silver_tables)
    ns = run(ok)
    creates = [x for x in ok.sql_run if "MATERIALIZED LAKE VIEW" in x and x.lstrip().startswith("--")]
    assert len(creates) == 3 and ns["created"] == ["audit_log", "order_items", "orders"]
    assert [c.strip() for c in creates] == [st["sql"] for st in gold.statements(s)]          # the notebook sends exactly the drafted SQL
    for overrides, match in (('GOLD_SCHEMA = "shop"', "source or silver"), ('GOLD_SCHEMA = "silver"', "source or silver")):
        spark = Spark(silver_tables)
        with pytest.raises(ValueError, match=match):
            run(spark, overrides)
        assert not any("MATERIALIZED" in x for x in spark.sql_run)
    theirs = Spark(silver_tables | {"gold.orders"}, {"gold.orders": {"owner": "someone"}})
    with pytest.raises(ValueError, match="was not created by this notebook"):
        run(theirs)
    ours = Spark(silver_tables | {"gold.orders"}, {"gold.orders": {"krusgraph.gold": "lh-1/shop"}})
    assert run(ours)["created"] == ["audit_log", "order_items", "orders"]
    with pytest.raises(ValueError, match="Run the silver notebook"):
        run(Spark({"silver.orders"}))


def test_a_mixed_case_gold_schema_is_one_name_for_the_guard_and_the_create():
    s = gold.spec(shop_plan(), INFO, gold_schema="Reporting", silver_schema="Silver")
    assert s["gold_schema"] == "reporting" and all(w.startswith("reporting.") for w in gold.written(s))
    sent = []

    class Spark:
        class catalog:
            @staticmethod
            def tableExists(name):
                return name.replace("`", "").lower().startswith("silver.")

        def sql(self, text):
            sent.append(text)

            class R:
                def collect(self):
                    return []
            return R()
    ns = {"spark": Spark(), "display": lambda x: None}
    for kind, code in gold.cells(s):
        if kind != "markdown":
            exec(compile(code, "<notebook>", "exec"), ns)
            if kind == "parameters":
                exec('GOLD_SCHEMA = "gold_dev"', ns)                       # what a pipeline's parameter does
    creates = [x for x in sent if "CREATE OR REPLACE MATERIALIZED LAKE VIEW" in x]
    assert creates and all("`gold_dev`." in c and "`reporting`." not in c for c in creates)


def test_odd_names_survive_the_notebook_cell():
    from fabric_backend.schema import Column
    sch = seed.schema("shop")
    odd = "path\\Nx " + '"' * 3 + " {a}"                                    # a backslash, a triple quote and braces
    sch.tables["order_items"].columns.append(Column(odd, "string"))
    s = gold.spec(plan(sch), INFO)
    cells = [c for k, c in gold.cells(s) if k != "markdown"]
    for code in cells:
        compile(code, "<notebook>", "exec")
    items = next(c for c in cells if "gold.order_items ----" in c)
    sent = []
    ns = {"GOLD_SCHEMA": "gold", "SILVER_SCHEMA": "silver", "created": [], "spark": type("S", (), {"sql": lambda self, t: sent.append(t)})()}
    exec(items, ns)
    assert sent[0].strip() == next(st["sql"] for st in gold.statements(s) if st["name"] == "gold.order_items") and odd in sent[0]


def test_personal_columns_are_left_out_unless_asked_for():
    s = gold.spec(shop_plan(), INFO)
    names = {c["as"] for v in s["views"] for c in v["columns"]}
    assert "customers_name" not in names and "customers_country" in names
    assert {(o["table"], o["column"], o["rule"]) for o in s["personal_data"]["omitted"]} == {("customers", "name", "P1")}
    assert "show_personal_data=true" in gold.cells(s)[0][1]
    s = gold.spec(shop_plan(), INFO, show_personal_data=True)
    assert "customers_name" in {c["as"] for v in s["views"] for c in v["columns"]} and s["personal_data"]["omitted"] == []
    assert privacy.classify("customers", "customer_id") is None                               # keys are kept for the joins


# ------------------------------------------------------------------ the tools --------------------------------------

class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers, self.text = status, body, headers or {}, json.dumps(body or {})

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


@pytest.fixture
def shop(monkeypatch):
    import importlib
    deploy = importlib.import_module("fabric_backend.deploy")
    kind = {"type": "Lakehouse", "schemas_enabled": True}
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": kind["type"], "id": "lh-1", "displayName": src,
                                                                             "sql_host": "x", "sql_db": src, "schemas_enabled": kind["schemas_enabled"]})
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: []))
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    monkeypatch.setattr(deploy.time, "sleep", lambda s: None)
    return kind


def test_draft_returns_the_views_and_the_notebook_and_creates_nothing(shop, monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("a draft never posts"))
    out = json.loads(server.gold_views_draft("Sales", "shop_lh", schema="shop"))
    assert [v["name"] for v in out["views"]] == ["gold.audit_log", "gold.order_items", "gold.orders"]
    assert out["notebook"]["content"].startswith("# Fabric notebook source") and "generally available" in out["status"]
    assert out["refresh"]["run_now_scope"] == "Lakehouse.Execute.All or Item.Execute.All" and "customers.name (P1)" in out["personal_data"]["notice"]
    from fabric_backend import tool_status
    assert "have not been created in a Fabric workspace" in out["note"] and tool_status.answer_note("gold_views_draft") in out["note"]
    bad = json.loads(server.gold_views_draft("Sales", "shop_lh", schema="shop", gold_schema="silver"))
    assert bad["kind"] == "bad_input"


def test_create_gold_views_dry_run_then_create(shop, monkeypatch):
    posted = []
    monkeypatch.setattr(requests, "post", lambda url, **k: posted.append(url) or Resp(500))
    out = json.loads(server.create_gold_views("Sales", "shop_lh", name="gold_shop", schema="shop"))
    assert out["dry_run"] is True and posted == [] and out["rest"]["url"].endswith(f"/workspaces/{WS}/notebooks")
    calls = []
    polls = iter([Resp(200, {"status": "Succeeded"})])
    monkeypatch.setattr(requests, "get", lambda url, **k: next(polls) if "/operations/" in url else Resp(200, {"value": []}))
    monkeypatch.setattr(requests, "post", lambda url, **k: calls.append((url, k.get("json"))) or Resp(202, None, {"x-ms-operation-id": "op-1"}))
    out = json.loads(server.create_gold_views("Sales", "shop_lh", name="gold_shop", schema="shop", dry_run=False))
    assert out["result"]["status"] == "Succeeded" and "error" not in out and len(calls) == 1
    parts = {p["path"]: base64.b64decode(p["payload"]).decode() for p in calls[0][1]["definition"]["parts"]}
    assert "CREATE OR REPLACE MATERIALIZED LAKE VIEW" in parts["notebook-content.py"] and not any("delete" in u.lower() for u, _ in calls)


def test_create_gold_views_403_is_consent_and_a_lakehouse_without_schemas_is_refused(shop, monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, **k: Resp(200, {"value": []}))
    monkeypatch.setattr(requests, "post", lambda url, **k: Resp(403, {"errorCode": "InsufficientScopes"}))
    out = json.loads(server.create_gold_views("Sales", "shop_lh", name="gold_shop", schema="shop", dry_run=False))
    assert out["kind"] == "consent" and "Notebook.ReadWrite.All" in out["hint"]
    shop["schemas_enabled"] = False
    out = json.loads(server.gold_views_draft("Sales", "shop_lh", schema="dbo"))
    assert out["kind"] == "unsupported" and "schemas" in out["error"]
    shop["type"] = "Warehouse"
    assert json.loads(server.create_gold_views("Sales", "wh", name="x", schema="shop", dry_run=False))["kind"] == "unsupported"
