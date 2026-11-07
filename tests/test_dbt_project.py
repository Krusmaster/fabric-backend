"""Round n114: dbt_schema(project=true), a dbt project draft from the plan (fabric_backend/dbt.py `project`).

On the synthetic shop schema (fabric_backend/seed.py), with the counts evidence.validate takes on its rows in SQLite,
and on the amount demo (seed.AMOUNT_DEMO: one order of 1 000 with two lines). The models are T-SQL for dbt-fabric;
SQLite runs them here only to show the joins and the sums (it reads [brackets] and CAST as T-SQL writes them).
"""
from __future__ import annotations

import json
import re
import sqlite3

import pytest

import sap_support
from fabric_backend import dbt, evidence, seed, server
from fabric_backend.dialects import sqlite_sql
from fabric_backend.infer import plan
from fabric_backend.schema import Column, Schema, Table

yaml = pytest.importorskip("yaml")


def _connection(schema: str, tables: dict[str, tuple[str, list[tuple]]]):
    con = sqlite3.connect(":memory:")
    con.execute(f"ATTACH DATABASE ':memory:' AS {schema}")
    for name, (ddl, data) in tables.items():
        con.execute(f"CREATE TABLE {schema}.[{name}] ({ddl})")
        con.executemany(f"INSERT INTO {schema}.[{name}] VALUES ({','.join('?' * len(data[0]))})",
                        [tuple(v.isoformat() if hasattr(v, "isoformat") else v for v in r) for r in data])

    def execute(sql):
        cur = con.execute(sqlite_sql(sql))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    return con, execute


def _schema(name: str, ddl: dict[str, str]) -> Schema:
    s = Schema(schema=name)
    for t, cols in ddl.items():
        s.tables[t] = Table(t, [Column(c.split()[0], c.split()[1].lower()) for c in cols.split(", ")], schema=name)
    return s


@pytest.fixture(scope="module")
def shop():
    p = plan(seed.schema("shop"))
    con, execute = _connection("shop", {t: (seed.SCHEMAS[t], rows) for t, rows in seed.rows().items()})
    return p, evidence.validate(p, execute), con


@pytest.fixture(scope="module")
def amount_demo():
    p = plan(_schema("demo", {t: ddl for t, (ddl, _) in seed.AMOUNT_DEMO.items()}))
    con, execute = _connection("demo", seed.AMOUNT_DEMO)
    return p, evidence.validate(p, execute), con


def _run(con, files: dict[str, str], schema: str, model: str):
    """Every staging model as a view (source() -> the table), then `model` with ref() -> those views, in SQLite."""
    def body(sql: str) -> str:
        sql = sql.replace("{{ config(materialized='view') }}", "").replace("{{ config(materialized='table') }}", "")
        sql = re.sub(r"\{\{ source\('[^']*', '([^']*)'\) \}\}", lambda m: f"{schema}.[{m.group(1)}]", sql)
        return re.sub(r"\{\{ ref\('([^']*)'\) \}\}", lambda m: f"[{m.group(1)}]", sql)
    for path, sql in files.items():
        if "/staging/" in path and path.endswith(".sql"):
            name = path.rsplit("/", 1)[1][:-4]
            con.execute(f"DROP VIEW IF EXISTS [{name}]")
            con.execute(f"CREATE TEMP VIEW [{name}] AS {body(sql)}")
    sql = next(v for k, v in files.items() if k.endswith(f"/{model}.sql"))
    cur = con.execute(body(sql))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _joins(sql: str) -> set[str]:
    return set(re.findall(r"left join \{\{ ref\('([^']*)'\) \}\} as d\d+", sql))


# ------------------------------------------------------------------ the files ---------------------------------------

def test_the_shop_project_has_its_files_and_every_yaml_file_parses(shop):
    p, validation, _ = shop
    out = dbt.project(p, "shop", "shop", "shop_lh", validation)
    files = out["files"]
    assert sorted(files) == [
        "README.md", "dbt_project.yml",
        "models/marts/customers/_customers__models.yml", "models/marts/customers/fct_order_items.sql",
        "models/marts/customers/fct_orders.sql", "models/marts/products/_products__models.yml",
        "models/sources/shop.yml", "models/staging/shop/_stg_shop__models.yml",
        *[f"models/staging/shop/stg_shop__{t}.sql" for t in sorted(seed.SCHEMAS)]]
    docs = {k: yaml.safe_load(v) for k, v in files.items() if k.endswith(".yml")}
    proj = docs["dbt_project.yml"]
    assert proj["name"] == proj["profile"] == "krusgraph_shop" and proj["config-version"] == 2
    assert proj["models"]["krusgraph_shop"] == {"staging": {"+materialized": "view"}, "marts": {"+materialized": "table"}}
    assert files["models/sources/shop.yml"] == dbt.schema_yml(p, "shop", "shop", "shop_lh", [t.name for t in p.schema])
    stg = {m["name"]: m for m in docs["models/staging/shop/_stg_shop__models.yml"]["models"]}
    assert stg["stg_shop__orders"]["columns"] == [{"name": "order_id", "data_tests": ["unique", "not_null"]}]
    assert "columns" not in stg["stg_shop__order_items"]           # a composite key: no built-in test, a comment
    # one folder per proposed domain, with a models file even where no mart is written
    assert [d["slug"] for d in out["domains"]] == ["customers", "products"]
    assert "no fact table among its tables" in files["models/marts/products/_products__models.yml"]
    assert out["models"]["marts"] == ["fct_order_items", "fct_orders"]
    for k, v in files.items():
        if k.endswith(".sql"):
            assert "with " not in v.lower().split("{{ config")[1], f"{k}: no CTE (dbt-fabric: nested CTEs are not supported)"
    assert out["created"] == dbt.NOTHING_CREATED and "nothing was created or run" in files["README.md"]
    assert out["adapter"] == {"package": "dbt-fabric", "version": "1.12.0", "dbt_core": "1.12", "target": "Fabric Data Warehouse (T-SQL)"}


def test_every_relationship_test_matches_the_plan(shop):
    p, validation, _ = shop
    doc = yaml.safe_load(dbt.project(p, "shop", "shop", "shop_lh", validation)["files"]["models/sources/shop.yml"])
    found = set()
    for t in doc["sources"][0]["tables"]:
        for c in t["columns"]:
            for test in c.get("data_tests") or []:
                if isinstance(test, dict) and "relationships" in test:
                    a = test["relationships"]["arguments"]
                    target = re.fullmatch(r"source\('shop', '([^']*)'\)", a["to"]).group(1)
                    found.add((t["name"], c["name"], target, a["field"]))
    assert found == {(r.source, r.source_cols[0], r.target, r.target_cols[0]) for r in p.relationships if len(r.source_cols) == 1}


def test_staging_casts_to_fabric_types_and_keeps_one_row_per_key(shop):
    p, validation, con = shop
    files = dbt.project(p, "shop", "shop", "shop_lh", validation)["files"]
    orders = files["models/staging/shop/stg_shop__orders.sql"]
    assert "cast([order_date] as date) as [order_date]" in orders and "cast([order_id] as int)" in orders
    assert "partition by [order_id] order by (select null)" in orders and "where [order_id] is not null" in orders
    assert "TODO (customer): which of several rows with one key to keep" in orders
    assert "cast([list_price] as float)" in files["models/staging/shop/stg_shop__products.sql"]
    assert "cast([name] as varchar(8000))" in files["models/staging/shop/stg_shop__customers.sql"]
    items = files["models/staging/shop/stg_shop__order_items.sql"]
    assert "partition by [order_id], [line_no]" in items
    con.execute("INSERT INTO shop.[orders] VALUES (100, 1, '2026-09-01', 1)")          # a duplicate key: one row stays
    try:
        rows = _run(con, files, "shop", "fct_orders")
        assert len(rows) == 60 and len({r["order_id"] for r in rows}) == 60
    finally:
        con.execute("DELETE FROM shop.[orders] WHERE rowid = (SELECT MAX(rowid) FROM shop.[orders])")


def test_fabric_types_follow_the_documented_alternatives():
    assert dbt.fabric_type("money") == ("decimal(19, 4)", "Fabric Data Warehouse type (data-types.md)")
    assert dbt.fabric_type("datetime")[0] == "datetime2(3)" and dbt.fabric_type("timestamp")[0] == "datetime2(6)"
    assert dbt.fabric_type("nvarchar(10)")[0] == "varchar(40)" and dbt.fabric_type("nvarchar(4000)")[0] == "varchar(max)"
    assert dbt.fabric_type("tinyint")[0] == "smallint" and dbt.fabric_type("decimal(18,2)")[0] == "decimal(18, 2)"
    assert dbt.fabric_type("varchar") == (None, "varchar without a length or precision in the metadata: kept as the source has it")
    assert dbt.fabric_type("xml")[0] is None and dbt.fabric_type("xml")[1].startswith("no type in Fabric Data Warehouse")


# ------------------------------------------------------------------ the marts ---------------------------------------

def test_marts_join_only_over_counted_many_to_one_relationships(shop):
    p, validation, _ = shop
    out = dbt.project(p, "shop", "shop", "shop_lh", validation)
    assert _joins(out["files"]["models/marts/customers/fct_order_items.sql"]) == {
        "stg_shop__orders", "stg_shop__products", "stg_shop__categories", "stg_shop__customers"}
    assert out["checked"]["joined_over"] == [dbt._rel_text(r) for r in p.relationships] and out["checked"]["not_joined"] == []
    # the key of customers counted not unique: nothing joins customers any more, and the answer says why
    bad = json.loads(json.dumps(validation))
    for k in bad["keys"]:
        if k["table"] == "customers":
            k.update(distinct=k["rows"] - 1, verdict="not unique: 1 duplicate rows")
    out = dbt.project(p, "shop", "shop", "shop_lh", bad)
    for k, sql in out["files"].items():
        if "/marts/" in k and k.endswith(".sql"):
            assert "stg_shop__customers" not in _joins(sql), k
    assert {x["relationship"] for x in out["checked"]["not_joined"]} == {
        "addresses.customer_id -> customers.customer_id (R1)", "orders.customer_id -> customers.customer_id (R1)",
        "audit_log.customer_id -> customers.customer_id (R1)"}
    assert all("was not counted unique" in x["why"] for x in out["checked"]["not_joined"])
    # nothing counted: no mart at all, and it says so
    out = dbt.project(p, "shop", "shop", "shop_lh", None)
    assert out["models"]["marts"] == [] and not any(k.endswith(".sql") and "/marts/" in k for k in out["files"])
    assert any(x["part"] == "marts" and "nothing was counted" in x["why"] for x in out["not_templated"])


def test_a_repeated_header_amount_is_aggregated_before_the_join(amount_demo):
    p, validation, con = amount_demo
    out = dbt.project(p, "demo", "demo", "demo_lh", validation)
    files = out["files"]
    orders = next(v for k, v in files.items() if k.endswith("/fct_orders.sql"))
    lines = next(v for k, v in files.items() if k.endswith("/fct_order_lines.sql"))
    # at line level the order's amount is left out, with the reason; at order level the lines are summed first
    assert "[order_amount]" not in lines.split("{{ config")[1] and "Left out: orders.order_amount" in lines
    assert "sum([line_amount]) as [order_lines_line_amount_sum]" in orders and "group by [order_id]\n) as a1" in orders
    assert not re.search(r"sum\(\[order_amount\]\)", "".join(files.values()))
    [m] = [m for m in out["marts"] if m["fact"] == "orders"]
    assert m["aggregated_before_join"] == [{"table": "order_lines", "to": "orders", "by": ["order_id"], "summed": ["line_amount"]}]
    rows = _run(con, files, "demo", "fct_orders")
    assert [{k: v for k, v in r.items() if k != "order_date"} for r in rows] == [      # SQLite's CAST AS date is not a date
        {"order_id": 1, "order_amount": 1000.0, "order_lines_rows": 2, "order_lines_line_amount_sum": 1000.0}]
    assert sum(r["order_amount"] for r in rows) == 1000.0                  # not 2 000: one row per order


def test_untemplatable_tables_and_types_are_reported_not_guessed(shop):
    p, validation, _ = shop
    out = dbt.project(p, "shop", "shop", "shop_lh", validation)
    parts = {(x["table"], x["part"]) for x in out["not_templated"]}
    assert ("audit_log", "de-duplication") in parts and ("audit_log", "mart") in parts
    assert "## Not templated" in out["files"]["README.md"] and "audit_log (mart)" in out["files"]["README.md"]
    assert "row_number" not in out["files"]["models/staging/shop/stg_shop__audit_log.sql"]
    assert any(x["what"] == "business rules" for x in out["todo"])
    assert "TODO (customer): what counts as revenue" in out["files"]["models/marts/customers/fct_order_items.sql"]
    odd = plan(_schema("x", {"things": "thing_id int, shape geography, note varchar"}))
    out = dbt.project(odd, "x", "x")
    [x] = [x for x in out["not_templated"] if x["part"].startswith("type")]
    assert x["table"] == "things" and x["part"] == "type of shape" and "no type in Fabric Data Warehouse for geography" in x["why"]
    sql = out["files"]["models/staging/x/stg_x__things.sql"]
    assert "[note],  -- varchar: varchar without a length" in sql and "cast([note]" not in sql


def test_a_pack_gives_business_names_and_the_dedup_order():
    p = plan(sap_support.schema(["VBAK", "VBAP", "KNA1"]))
    files = dbt.project(p, "sap", "dbo", "erp")["files"]
    vbak = files["models/staging/sap/stg_sap__vbak.sql"]
    assert "VBAK: Sales document, header (sap pack)" in vbak
    assert "partition by [MANDT], [VBELN] order by [ERDAT] desc, [AEDAT] desc" in vbak
    assert "VBAK: Sales document, header" in files["models/staging/sap/_stg_sap__models.yml"]


def test_the_project_is_deterministic(shop, amount_demo):
    for p, validation, _ in (shop, amount_demo):
        a = json.dumps(dbt.project(p, "s", p.schema.schema, "db", validation), sort_keys=False)
        b = json.dumps(dbt.project(p, "s", p.schema.schema, "db", json.loads(json.dumps(validation))), sort_keys=False)
        assert a == b


# ------------------------------------------------------------------ the tool ----------------------------------------

@pytest.fixture
def tool(monkeypatch):
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: "11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": "Lakehouse", "id": "lh-1", "displayName": src,
                                                                             "sql_host": "x.datawarehouse.fabric.microsoft.com", "sql_db": src})
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: []))
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    return "Sales", "shop_lh"


def test_dbt_schema_with_project_returns_the_files(tool, shop, monkeypatch):
    _, validation, _ = shop
    out = json.loads(server.dbt_schema(*tool, schema="shop", project=True))
    assert out["project"] == "krusgraph_shop" and "dbt_project.yml" in out["files"] and out["models"]["marts"] == []
    assert "database: shop_lh" in out["files"]["models/sources/shop.yml"] and out["created"] == dbt.NOTHING_CREATED
    monkeypatch.setattr(server._evidence, "validate", lambda p, execute, max_items=60: validation)
    out = json.loads(server.dbt_schema(*tool, schema="shop", project=True, check_rows=True))
    assert out["models"]["marts"] == ["fct_order_items", "fct_orders"] and out["counts"] == validation["summary"]
    plain = json.loads(server.dbt_schema(*tool, schema="shop"))                 # without project: the sources file as before
    assert plain["path"] == "models/sources/shop.yml" and "files" not in plain
