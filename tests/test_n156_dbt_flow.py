"""Round n156: dbt_schema(project=true) as a whole dbt flow from the checked plan (fabric_backend/dbt.py `project`), on the
shop seed and the /check datasets of round n150 (tests/fixtures/check_cases/): staging columns in snake_case, composite
keys and references tested by singular tests without a package, marts only over relationships the counts confirmed and
never a header amount at line grain, a profile without a secret, a README that says how to run it, and the fixes accepted
from validate_plan(fixes=true) as staging logic. Every SQL file parses as T-SQL (n139's parser), every YAML file loads,
and three projects are compared with golden files (KRUSGRAPH_UPDATE_GOLDEN=1 writes them). Nothing runs dbt."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

import pytest

from fabric_backend import dbt, evidence, fix_plan, seed, server
from fabric_backend.dialects import sqlite_sql
from fabric_backend.infer import plan
from fabric_backend.platforms.local import folder_source
from test_n139_sql_parses import parse_error, without_jinja

yaml = pytest.importorskip("yaml")
CASES = Path(__file__).parent / "fixtures" / "check_cases"
GOLDEN = Path(__file__).parent / "golden"
UPDATE = os.environ.get("KRUSGRAPH_UPDATE_GOLDEN") == "1"


def _case(name: str, fixes=None) -> tuple[dict, dict]:
    src = folder_source(CASES / name)
    try:
        p = plan(src.schema)
        v = evidence.validate(p, src.execute)
        resolved = fix_plan.resolve(fix_plan.propose(p, v, src.execute)["fixes"], fixes, p) if fixes else None
        rows = {t.name: [dict(r) for r in src.execute(f"SELECT * FROM [data].[{t.name}]")] for t in src.schema}
        return dbt.project(p, "data", "data", "lh", v, fixes=resolved), rows
    finally:
        src.close()


def _shop() -> dict:
    p = plan(seed.schema("shop"))
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS shop")
    for name, rows in seed.rows().items():
        con.execute(f"CREATE TABLE shop.[{name}] ({seed.SCHEMAS[name]})")
        con.executemany(f"INSERT INTO shop.[{name}] VALUES ({','.join('?' * len(rows[0]))})",
                        [tuple(v.isoformat() if hasattr(v, "isoformat") else v for v in r) for r in rows])

    def execute(sql):
        cur = con.execute(sqlite_sql(sql))
        return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    return dbt.project(p, "shop", "shop", "shop_lh", evidence.validate(p, execute))


def _sqlite(rows: dict[str, list[dict]], files: dict[str, str], model: str) -> list[dict]:
    """The staging models as views over the rows in SQLite (source() -> the table, ref() -> the view), then `model`."""
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS data")
    for t, rs in rows.items():
        cols = list(rs[0])
        con.execute(f"CREATE TABLE data.[{t}] ({', '.join(f'[{c}]' for c in cols)})")
        con.executemany(f"INSERT INTO data.[{t}] VALUES ({','.join('?' * len(cols))})", [tuple(r[c] for c in cols) for r in rs])
    def lite(sql: str) -> str:                                           # SQLite has no varchar(max); the type is only a name there
        return sqlite_sql(without_jinja(sql)).replace("[data].", "data.").replace("(max)", "")
    staged = [(k.rsplit("/", 1)[1][:-4], v) for k, v in files.items() if "/staging/" in k and k.endswith(".sql")]
    for _ in range(len(staged)):                                         # a view after the views it reads
        for name, sql in staged:
            try:
                con.execute(f"CREATE TEMP VIEW IF NOT EXISTS [{name}] AS {lite(sql)}")
            except sqlite3.OperationalError:
                pass
    sql = next(v for k, v in files.items() if k.endswith(f"/{model}.sql"))
    cur = con.execute(lite(sql))
    return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]


# ------------------------------------------------------------------ parse, load, golden ---------------------------

PROJECTS = {"shop": lambda: _shop(), "01_composite_key": lambda: _case("01_composite_key")[0],
            "05_sap_mandt": lambda: _case("05_sap_mandt")[0]}


@pytest.mark.parametrize("name", sorted(PROJECTS))
def test_every_sql_file_parses_and_every_yaml_file_loads_and_matches_the_golden_file(name):
    out = PROJECTS[name]()
    files = out["files"]
    bad = [f"{k}: {err}" for k, v in files.items() if k.endswith(".sql") and (err := parse_error(without_jinja(v)))]
    assert not bad, bad
    for k, v in files.items():
        if k.endswith(".yml"):
            assert yaml.safe_load(v) is not None, k
    golden = GOLDEN / f"dbt_project_{name}.json"
    if UPDATE:
        golden.write_text(json.dumps(files, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    assert json.loads(golden.read_text(encoding="utf-8")) == files, f"{golden.name} differs; KRUSGRAPH_UPDATE_GOLDEN=1 rewrites it"


def test_the_tests_in_the_yaml_follow_the_plans_keys_and_relationships():
    files = _shop()["files"]
    src = yaml.safe_load(files["models/sources/shop.yml"])["sources"][0]["tables"]
    tests = {(t["name"], c["name"]): c.get("data_tests") for t in src for c in t.get("columns", [])}
    assert tests[("orders", "order_id")][:2] == ["unique", "not_null"]
    rel = next(x for x in tests[("orders", "customer_id")] if isinstance(x, dict))["relationships"]["arguments"]
    assert rel == {"to": "source('shop', 'customers')", "field": "customer_id"}
    stg = {m["name"]: m for m in yaml.safe_load(files["models/staging/shop/_stg_shop__models.yml"])["models"]}
    assert stg["stg_shop__customers"]["columns"] == [{"name": "customer_id", "data_tests": ["unique", "not_null"]}]
    assert "tests/stg_shop__order_items__unique_order_id_line_no.sql" in files["models/staging/shop/_stg_shop__models.yml"]
    assert yaml.safe_load(files["dbt_project.yml"])["test-paths"] == ["tests"]


# ------------------------------------------------------------------ the n156 parts ---------------------------------

def test_05_staging_renames_to_snake_case_and_composite_keys_are_singular_tests():
    out, rows = _case("05_sap_mandt")
    files = out["files"]
    assert out["renamed"]["VBAK"] == {"MANDT": "mandt", "VBELN": "vbeln", "NETWR": "netwr"}
    vbak = files["models/staging/data/stg_data__vbak.sql"]
    assert "as [mandt]" in vbak and "partition by [MANDT], [VBELN]" in vbak
    assert "MANDT: " not in files["models/sources/data.yml"] and "name: MANDT" in files["models/sources/data.yml"]   # sources keep the names
    unique = files["tests/stg_data__vbak__unique_mandt_vbeln.sql"]
    assert "group by [mandt], [vbeln]\nhaving count(*) > 1" in unique and "dbt-utils is not supported" in unique
    ref = files["tests/stg_data__vbap__references_vbak.sql"]
    assert "not exists (select 1 from {{ ref('stg_data__vbak') }} as p where p.[mandt] = c.[mandt] and p.[vbeln] = c.[vbeln])" in ref
    assert "dbt_utils" not in files["dbt_project.yml"] and "packages.yml" not in files
    # the orphan (200, 0000000020) is what the reference test finds over the staging models
    assert _sqlite(rows, files, "stg_data__vbap__references_vbak") == [{"mandt": 200, "vbeln": "0000000020"}]
    assert _sqlite(rows, files, "stg_data__vbak__unique_mandt_vbeln") == []


@pytest.mark.parametrize("name, header, amount", [("01_composite_key", "orders", "order_total"), ("05_sap_mandt", "VBAK", "NETWR")])
def test_no_mart_sums_a_header_amount_at_line_grain(name, header, amount):
    out, rows = _case(name)
    for m in out["marts"]:
        sql = next(v for k, v in out["files"].items() if k.endswith(f"/{m['model']}.sql"))
        if m["fact"] != header:
            assert f"Left out: {header}.{amount}" in sql and f"[{dbt.snake(header)}_{dbt.snake(amount)}]" not in sql, m["model"]
    assert not re.search(rf"sum\(\[{dbt.snake(amount)}\]\)", "".join(v for k, v in out["files"].items()
                                                                      if f"fct_{dbt.snake(header)}" not in k))


def test_01_the_header_mart_sums_the_lines_once_per_order():
    out, rows = _case("01_composite_key")
    got = _sqlite(rows, out["files"], "fct_orders")
    assert sum(r["order_total"] for r in got) == 600                                     # the fixture's right answer, not 1300
    assert sum(r["order_items_line_amount_sum"] or 0 for r in got) == 600


def test_04_a_relationship_onto_a_key_counted_not_unique_is_left_out_and_listed():
    out, _ = _case("04_duplicate_parent")
    assert out["checked"]["joined_over"] == []
    assert out["checked"]["not_joined"] == [{"relationship": "orders.customer_id -> customers.customer_id (R1)",
                                             "why": "the key customer_id of customers was not counted unique, so a row can match more than one"}]
    assert "## Not joined over" in out["files"]["README.md"]


def test_the_profile_has_no_secret_and_the_readme_says_how_to_run_it():
    files = _shop()["files"]
    prof = yaml.safe_load(files["profiles.example.yml"])["krusgraph_shop"]["outputs"]["dev"]
    assert prof["type"] == "fabric" and prof["authentication"] == "CLI" and not {"password", "client_secret", "secret"} & set(prof)
    readme = files["README.md"]
    assert "## How to run it" in readme and "`dbt build` creates the staging views" in readme
    assert "Krusgraph has not run these commands on this project" in readme


# ------------------------------------------------------------------ fixes as staging logic --------------------------

def test_03_an_accepted_orphan_fix_leaves_the_orphan_out_and_keeps_the_nulls():
    out, rows = _case("03_null_foreign_key", ["rel:orders.customer_id>customers"])
    sql = out["files"]["models/staging/data/stg_data__orders.sql"]
    assert "-- Fix rel:orders.customer_id>customers (accepted from validate_plan(fixes=true), mechanical)" in sql
    assert ("(s.[customer_id] is null or exists (select 1 from {{ ref('stg_data__customers') }} as p where "
            "p.[customer_id] = s.[customer_id]))") in sql
    got = _sqlite(rows, out["files"], "stg_data__orders")
    assert len(got) == 4 and sum(r["customer_id"] is None for r in got) == 2              # 2 matching, 2 NULL; 999 left out
    assert out["fixes"] == [{"id": "rel:orders.customer_id>customers", "table": "orders", "step": "reference", "choice": "quarantine"}]
    assert "## Fixes in the staging models" in out["files"]["README.md"]


def test_03_set_null_keeps_the_row_with_no_reference():
    out, rows = _case("03_null_foreign_key", [{"id": "rel:orders.customer_id>customers", "choice": "set_null"}])
    assert "case when exists (select 1 from {{ ref('stg_data__customers') }}" in out["files"]["models/staging/data/stg_data__orders.sql"]
    got = _sqlite(rows, out["files"], "stg_data__orders")
    assert len(got) == 5 and sum(r["customer_id"] is None for r in got) == 3


def test_04_exact_copies_need_no_todo_and_a_named_winner_orders_the_rows():
    out, _ = _case("04_duplicate_parent", ["key:customers"])
    sql = out["files"]["models/staging/data/stg_data__customers.sql"]
    assert "Rows that share the key are exact copies" in sql and "TODO (customer): which of several rows" not in sql
    assert not any(t["table"] == "customers" and t["what"] == "which duplicate to keep" for t in out["todo"])
    out, _ = _case("04_duplicate_parent", [{"id": "key:customers", "winner": "customer_name"}])
    assert "order by [customer_name] desc" in out["files"]["models/staging/data/stg_data__customers.sql"]


def test_without_fixes_the_staging_models_have_no_fix_logic():
    out, _ = _case("03_null_foreign_key")
    assert "exists (" not in out["files"]["models/staging/data/stg_data__orders.sql"] and out["fixes"] == []


# ------------------------------------------------------------------ the tool ----------------------------------------

@pytest.fixture()
def hosted(monkeypatch):
    opened = []

    def connected(workspace, source, schema, ctx):
        src = folder_source(CASES / source)
        opened.append(src)
        return src.schema, src.execute
    monkeypatch.setattr(server, "_connected", connected)
    yield
    for s in opened:
        s.close()


def test_dbt_schema_takes_the_accepted_fixes_only_with_a_project(hosted):
    out = json.loads(server.dbt_schema("ws", "03_null_foreign_key", schema="data", project=True,
                                       fixes=["rel:orders.customer_id>customers"]))
    assert out["fixes"][0]["id"] == "rel:orders.customer_id>customers" and "counts" in out
    bad = json.loads(server.dbt_schema("ws", "03_null_foreign_key", schema="data", fixes=["rel:orders.customer_id>customers"]))
    assert bad["kind"] == "bad_input" and "project=true" in bad["error"]
    bad = json.loads(server.dbt_schema("ws", "05_sap_mandt", schema="data", project=True, fixes=["level:VBAK.NETWR"]))
    assert bad["kind"] == "bad_input" and "business decision" in bad["error"]
