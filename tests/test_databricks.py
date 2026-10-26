"""The Databricks adapter (round n13, Draft only), with Databricks mocked at its REST API (tests/databricks_support.py):
the shop seed as Unity Catalog information_schema rows gives the same plan as on Fabric, declared constraints win over
inference, column tags reach the personal-data rules, the counting queries run in Databricks SQL, the drafts parse as
Databricks SQL and their logic runs on SQLite, no target is ever a source table, and the creating tools are dry runs
by default and never drop anything."""
from __future__ import annotations

import json
import re

import pytest

import databricks_support as dx
from fabric_backend import databricks_drafts as dd, evidence, mcp_server, seed
from fabric_backend.dialects import DATABRICKS
from fabric_backend.infer import plan
from fabric_backend.platforms import databricks as adapter

AUTH = (dx.HOST, lambda: {"Authorization": "Bearer test-only"})


def _plan_view(p) -> dict:
    return {"summary": p.summary(), "keyless": p.keyless, "ambiguous": p.ambiguous, "keys": {t: [c, r] for t, (c, r) in p.keys.items()},
            "relationships": [(r.source, r.source_cols, r.target, r.target_cols, r.rule, r.field_name, r.reverse_name) for r in p.relationships]}


@pytest.fixture
def workspace(monkeypatch):
    """The stdio server on Databricks: KRUSGRAPH_PLATFORM=databricks, the catalog and warehouse set, sign-in and REST mocked."""
    import requests
    fake = dx.FakeDatabricks()
    for verb in ("get", "post", "put"):
        monkeypatch.setattr(requests, verb, getattr(fake, verb))
    monkeypatch.setattr(adapter, "sdk_auth", lambda host=None, profile=None: AUTH)
    monkeypatch.setenv("KRUSGRAPH_PLATFORM", "databricks")
    monkeypatch.setenv("DATABRICKS_CATALOG", dx.CATALOG)
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", dx.WAREHOUSE)
    monkeypatch.setenv("DATABRICKS_HOST", dx.HOST)
    monkeypatch.delenv("FABRIC_ODBC", raising=False)
    return fake


def call(tool, **kw):
    return json.loads(getattr(mcp_server, tool)(**kw))


# ------------------------------------------------------------------ reading Unity Catalog ---------------------------

def test_the_shop_seed_in_unity_catalog_gives_the_same_plan_as_on_fabric(workspace):
    out = call("plan_backend", schema="shop")
    fabric = plan(seed.schema("shop"))
    assert out["summary"] == fabric.summary()
    assert {t: [v["columns"], v["rule"]] for t, v in out["keys"].items()} == {t: [c, r] for t, (c, r) in fabric.keys.items()}
    assert [(r["source"], r["source_cols"], r["target"], r["rule"]) for r in out["relationships"]] == \
           [(r.source, r.source_cols, r.target, r.rule) for r in fabric.relationships]
    sql = [s for s in workspace.statements if "information_schema.columns" in s][0]
    assert "`workspace`.information_schema.columns" in sql and "full_data_type AS data_type" in sql
    tables = call("list_tables", schema="shop")
    assert ["order_date", "date"] in tables["orders"]


def test_declared_constraints_win_over_inference_as_k0_and_r0(workspace):
    workspace.constraints = (dx.pk("customers", ["customer_id"]) + dx.pk("order_items", ["order_id", "line_no"]) + dx.pk("addresses", ["address_id"])
                             + dx.fk("orders", ["ship_to_id"], "addresses", ["address_id"])
                             + dx.fk("orders", ["customer_id"], "customers", ["customer_id"], schema="workspace.other"))
    out = call("plan_backend", schema="shop")
    assert out["keys"]["customers"]["rule"] == "K0" and out["keys"]["order_items"] == {"columns": ["order_id", "line_no"], "rule": "K0"}
    rels = {(r["source"], tuple(r["source_cols"])): r for r in out["relationships"]}
    assert rels[("orders", ("ship_to_id",))]["target"] == "addresses" and rels[("orders", ("ship_to_id",))]["rule"] == "R0"
    # a foreign key into another catalog or schema has no target here: left out, so the name rule applies
    assert rels[("orders", ("customer_id",))]["rule"] == "R1"
    keys_sql = [s for s in workspace.statements if "table_constraints" in s][0]
    assert "coalesce(kcu.position_in_unique_constraint, kcu.ordinal_position)" in keys_sql and "'PRIMARY KEY', 'FOREIGN KEY'" in keys_sql


def test_a_catalog_without_the_constraint_views_still_plans_from_names(workspace):
    workspace.fail[[s for s in [adapter.KEYS_SQL.format(catalog="`workspace`", schema="shop")]][0]] = (200, {"error_code": "BAD_REQUEST", "message": "[TABLE_OR_VIEW_NOT_FOUND] x"})
    assert call("plan_backend", schema="shop")["summary"] == plan(seed.schema("shop")).summary()


def test_column_tags_flag_personal_data_under_the_p_rules_and_are_masked(workspace):
    workspace.tags = [{"table_name": "customers", "column_name": "country", "tag_name": "class.location", "tag_value": None},
                      {"table_name": "orders", "column_name": "order_date", "tag_name": "pii", "tag_value": "true"}]
    out = call("sample_rows", table="customers", schema="shop", n=3)
    flagged = {f["column"]: f for f in out["personal_data"]["columns"]}
    assert flagged["country"]["rule"] == "P5" and flagged["country"]["tag"] == "class.location" and flagged["name"]["rule"] == "P1"
    assert {r["country"] for r in out["rows"]} == {"***"} and len(out["rows"]) == 3
    assert [s for s in workspace.statements if s.startswith("SELECT `customer_id`")][0].endswith("FROM `workspace`.`shop`.`customers` LIMIT 3")
    orders = call("sample_rows", table="orders", schema="shop", n=2)
    assert orders["personal_data"]["columns"][0]["rule"] == "tag" and {r["order_date"] for r in orders["rows"]} == {"***"}


def test_counting_queries_run_in_databricks_sql_and_agree_with_fabric(workspace):
    out = call("validate_plan", schema="shop")
    assert out["summary"].startswith("6 of 6 keys unique, 6 of 6 relationships hold")
    counts = [s for s in workspace.statements if "AS distinct_keys" in s or "AS orphans" in s]
    assert counts and all("COUNT_BIG" not in s and "[" not in s and "`workspace`.`shop`." in s for s in counts)
    from fabric_backend.demo import demo_validation
    fabric = {k["table"]: (k["rows"], k["distinct"]) for k in demo_validation()["keys"] if k["table"] != "order_items"}
    assert {k["table"]: (k["rows"], k["distinct"]) for k in out["keys"] if k["table"] in fabric} == fabric
    sugg = call("suggest_relationships", schema="shop")
    best = [c for c in sugg["candidates"] if c["source"] == "orders" and c["source_cols"] == ["ship_to_id"] and c["target"] == "addresses"][0]
    assert best["evidence"]["inclusion"] == 1.0


def test_join_path_dictionary_dbt_and_analysis_on_databricks(workspace):
    jp = call("join_path", start="customers", end="categories", schema="shop")
    assert jp["paths"][0]["sql"].startswith("SELECT t0.`customer_id`") and jp["paths"][0]["sql"].endswith("\nLIMIT 100")
    assert "`workspace`.`shop`.`orders`" in jp["paths"][0]["sql"]
    assert call("dbt_schema", schema="shop")["yaml"].count("database: workspace") == 1
    assert "workspace" in call("data_dictionary", schema="shop")["markdown"]
    assert call("analyze_schema", schema="shop")["roles"]["order_items"]["role"] == "fact"


def test_fabric_only_tools_answer_unsupported_with_the_databricks_way(workspace):
    for tool, kw, word in (("create_backend", {"workspace": "w", "source": "s", "name": "n", "schema": "shop"}, "Mirrored Azure Databricks catalog"),
                           ("rayfin_connector", {"schema": "shop"}, "Mirror"), ("ontology_draft", {"schema": "shop"}, "plan_backend"),
                           ("semantic_model_draft", {"schema": "shop"}, "databricks_metric_view_draft"),
                           ("silver_notebook_draft", {"schema": "shop"}, "databricks_pipeline_draft"),
                           ("answer_query_draft", {"question": "orders per customer", "tables": ["orders"], "schema": "shop"}, "join_path")):
        out = call(tool, **kw)
        assert out["kind"] == "unsupported" and word in out["hint"] and set(out) == {"error", "kind", "hint"}, tool
    assert not workspace.statements                                              # refused before any query


def test_the_databricks_tools_refuse_on_fabric(monkeypatch):
    monkeypatch.delenv("KRUSGRAPH_PLATFORM", raising=False)
    for tool in ("databricks_constraints_draft", "create_databricks_constraints", "databricks_pipeline_draft", "databricks_metric_view_draft",
                 "export_databricks_bundle", "databricks_lineage"):
        out = call(tool)
        assert out["kind"] == "unsupported" and "KRUSGRAPH_PLATFORM=databricks" in out["hint"]
    assert call("create_databricks_pipeline", name="x")["kind"] == "unsupported"


def test_missing_settings_and_a_missing_sdk_are_configuration_answers(workspace, monkeypatch):
    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID")
    out = call("plan_backend", schema="shop")
    assert out["kind"] == "server_config" and "DATABRICKS_WAREHOUSE_ID" in out["error"]
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", dx.WAREHOUSE)
    monkeypatch.setattr(adapter, "sdk_auth", _real_sdk_auth)
    import builtins
    real_import = builtins.__import__

    def no_sdk(name, *a, **k):
        if name.startswith("databricks.sdk"):
            raise ImportError("No module named 'databricks'")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_sdk)
    out = call("list_tables", schema="shop")
    assert out["kind"] == "server_config" and "fabric-backend[databricks]" in out["hint"]


_real_sdk_auth = adapter.sdk_auth


def test_schema_names_are_checked_before_they_reach_sql(workspace):
    out = call("plan_backend", schema="shop'; DROP TABLE x; --")
    assert out["kind"] == "bad_input" and not workspace.statements
    assert call("plan_backend", schema="workspace.shop")["kind"] == "bad_input"
    assert call("plan_backend", schema="nothere")["kind"] == "schema_not_found"


# ------------------------------------------------------------------ the Statement Execution API ---------------------

def test_statements_poll_follow_chunks_and_are_typed(monkeypatch):
    import requests
    fake = dx.FakeDatabricks(pending=2, chunk=3)
    monkeypatch.setattr(requests, "get", fake.get)
    monkeypatch.setattr(requests, "post", fake.post)
    monkeypatch.setattr(adapter.time, "sleep", lambda s: None)
    execute = adapter.connect(dx.HOST, dx.WAREHOUSE, AUTH[1], dx.CATALOG)
    rows = execute("SELECT `customer_id`, `name` FROM `workspace`.`shop`.`customers` ORDER BY `customer_id`")
    assert len(rows) == 10 and rows[0] == {"customer_id": 1, "name": "Harbour Bikes"} and isinstance(rows[9]["customer_id"], int)
    assert ("GET", "/api/2.0/sql/statements/st-1/result/chunks/3") in fake.calls and execute.dialect.catalog == "workspace"


def test_statement_failures_and_timeouts_answer_in_the_tools_error_format(monkeypatch):
    import requests
    from fabric_backend.errors import PlatformError, explain
    fake = dx.FakeDatabricks()
    monkeypatch.setattr(requests, "get", fake.get)
    monkeypatch.setattr(requests, "post", fake.post)
    execute = adapter.connect(dx.HOST, dx.WAREHOUSE, AUTH[1], dx.CATALOG)
    fake.fail["SELECT 1 FROM nowhere"] = (200, {"error_code": "BAD_REQUEST", "message": "[TABLE_OR_VIEW_NOT_FOUND] The table `nowhere` cannot be found."})
    with pytest.raises(PlatformError) as e:
        execute("SELECT 1 FROM nowhere")
    assert explain(e.value)["kind"] == "table_not_found"
    fake.fail[("POST", "/api/2.0/sql/statements")] = (403, {"error_code": "PERMISSION_DENIED", "message": "no CAN USE"})
    with pytest.raises(PlatformError) as e:
        execute("SELECT 1")
    answer = explain(e.value)
    assert answer["kind"] == "no_access" and "CAN USE" in answer["hint"] and "Bearer" not in json.dumps(answer)
    fake.fail[("POST", "/api/2.0/sql/statements")] = (401, {"error_code": "UNAUTHENTICATED"})
    with pytest.raises(PlatformError) as e:
        execute("SELECT 1")
    assert explain(e.value)["kind"] == "sign_in" and "databricks auth login" in explain(e.value)["hint"]
    del fake.fail[("POST", "/api/2.0/sql/statements")]
    slow = dx.FakeDatabricks(pending=10_000)
    monkeypatch.setattr(requests, "get", slow.get)
    monkeypatch.setattr(requests, "post", slow.post)
    client = adapter.StatementClient(dx.HOST, dx.WAREHOUSE, AUTH[1], dx.CATALOG, timeout=0.05, poll_seconds=0.01)
    with pytest.raises(PlatformError) as e:
        client.run("SELECT 1")
    assert e.value.kind == "timeout" and ("POST", "/api/2.0/sql/statements/st-1/cancel") in slow.calls


# ------------------------------------------------------------------ constraints ----------------------------------

def _not_null_columns(workspace):
    workspace.columns = dx.columns_rows(not_null={("customers", "customer_id"), ("orders", "order_id"), ("products", "product_id"),
                                                  ("categories", "id"), ("addresses", "address_id"), ("order_items", "order_id"),
                                                  ("order_items", "line_no")})


def test_constraints_draft_writes_rely_only_where_the_counts_hold(workspace):
    _not_null_columns(workspace)
    plain = call("databricks_constraints_draft", schema="shop")
    assert all(not s.get("rely") for s in plain["statements"]) and plain["validated"] is False
    out = call("databricks_constraints_draft", schema="shop", validate=True)
    pks = {s["table"]: s for s in out["statements"] if s["kind"] == "primary_key"}
    fks = [s for s in out["statements"] if s["kind"] == "foreign_key"]
    assert set(pks) == {"customers", "orders", "products", "categories", "addresses", "order_items"} and all(s["rely"] for s in pks.values())
    assert pks["order_items"]["sql"] == ("ALTER TABLE `workspace`.`shop`.`order_items` ADD CONSTRAINT `order_items_pk` PRIMARY KEY "
                                         "(`order_id`, `line_no`) RELY")
    assert len(fks) == 6 and all(s["rely"] for s in fks) and all("REFERENCES `workspace`.`shop`." in s["sql"] for s in fks)
    assert not [s for s in out["statements"] if s["kind"] == "not_null"]          # every key column is NOT NULL already
    assert "-- key order_id by rule K2" in out["sql"] and "DROP" not in out["sql"]


def test_a_nullable_or_contradicted_key_is_left_out_with_the_reason(workspace):
    out = call("databricks_constraints_draft", schema="shop", validate=True)
    assert not [s for s in out["statements"] if s["kind"] == "primary_key"]
    assert all("NOT NULL" in s["why"] or "FOREIGN KEY needs a PRIMARY KEY" in s["why"] for s in out["skipped"])
    with_nn = call("databricks_constraints_draft", schema="shop", validate=True, set_not_null=True)
    nn = [s for s in with_nn["statements"] if s["kind"] == "not_null"]
    assert nn and nn[0]["sql"].startswith("ALTER TABLE `workspace`.`shop`.") and nn[0]["sql"].endswith("SET NOT NULL")
    no_counts = call("databricks_constraints_draft", schema="shop", set_not_null=True)
    assert not [s for s in no_counts["statements"] if s["kind"] == "not_null"] and "validate=true first" in no_counts["skipped"][0]["why"]
    workspace.db.execute("INSERT INTO shop.`customers` VALUES (3, 'Again', 'SE')")
    _not_null_columns(workspace)
    dup = call("databricks_constraints_draft", schema="shop", validate=True)
    assert "customers" in {s["table"] for s in dup["skipped"] if s["constraint"] == "PRIMARY KEY"}
    assert any("not unique" in s["why"] for s in dup["skipped"])


def test_declared_constraints_are_not_added_again(workspace):
    _not_null_columns(workspace)
    workspace.constraints = dx.pk("customers", ["customer_id"]) + dx.fk("orders", ["customer_id"], "customers", ["customer_id"])
    out = call("databricks_constraints_draft", schema="shop", validate=True)
    assert {d["table"] for d in out["declared"]} == {"customers", "orders"}
    assert "customers" not in {s["table"] for s in out["statements"] if s["kind"] == "primary_key"}
    assert not [s for s in out["statements"] if s["kind"] == "foreign_key" and s["table"] == "orders" and s["columns"] == ["customer_id"]]


def test_create_constraints_is_a_dry_run_by_default_and_only_adds(workspace):
    _not_null_columns(workspace)
    dry = call("create_databricks_constraints", schema="shop")
    assert dry["dry_run"] is True and dry["statements"] and not workspace.ddl
    out = call("create_databricks_constraints", schema="shop", dry_run=False)
    assert out["result"] == {"status": "Succeeded", "statements": len(out["statements"])}
    assert len(workspace.ddl) == len(out["statements"]) and all(s.startswith("ALTER TABLE") and "ADD CONSTRAINT" in s for s in workspace.ddl)
    assert not any(re.search(r"\bDROP\b", s) for s in workspace.ddl)


# ------------------------------------------------------------------ views, pipeline, metric views, bundle --------

def test_create_views_on_databricks_writes_databricks_views_in_their_own_schema(workspace):
    out = call("create_views", schema="shop")
    assert out["schema_sql"] == "CREATE SCHEMA IF NOT EXISTS `workspace`.`krusgraph`"
    assert out["views"][0]["sql"].startswith("CREATE OR REPLACE VIEW `workspace`.`krusgraph`.`vw_order_items` COMMENT '")
    assert call("create_views", schema="shop", views_schema="shop")["kind"] == "bad_input"
    made = call("create_views", schema="shop", dry_run=False)
    assert made["result"]["status"] == "Succeeded" and len(workspace.ddl) == len(out["views"]) + 1


def _sqlglot():
    return pytest.importorskip("sqlglot")


def test_generated_sql_parses_as_databricks_sql(workspace):
    sqlglot = _sqlglot()
    _not_null_columns(workspace)
    stmts = [s["sql"] for s in call("databricks_constraints_draft", schema="shop", validate=True, set_not_null=True)["statements"]]
    v = call("create_views", schema="shop")
    stmts += [v["schema_sql"]] + [x["sql"] for x in v["views"]]
    stmts += [call("join_path", start="customers", end="categories", schema="shop")["paths"][0]["sql"]]
    pipe = call("databricks_pipeline_draft", schema="shop")
    for body in re.findall(r"\nAS SELECT(.*?);", pipe["files"]["silver.sql"] + pipe["files"]["gold.sql"], re.S):
        stmts.append("SELECT" + body)
    stmts += [q.strip() for q in re.findall(r"\nAS\n(SELECT .*?);", pipe["files"]["silver.sql"], re.S)]
    assert len(stmts) > 25
    for s in stmts:
        e = sqlglot.parse_one(s, read="databricks")
        assert not isinstance(e, sqlglot.exp.Command), s[:120]


def test_pipeline_draft_mirrors_the_silver_and_gold_rules_and_never_writes_a_source(workspace):
    out = call("databricks_pipeline_draft", schema="shop", order_by={"orders": "order_date"})
    silver, gold = out["files"]["silver.sql"], out["files"]["gold.sql"]
    assert silver.startswith("-- Databricks notebook source") and "-- COMMAND ----------" in silver
    assert "CONSTRAINT orders_key_present EXPECT (`order_id` IS NOT NULL) ON VIOLATION DROP ROW" in silver
    assert "CONSTRAINT orders_customer_id_in_customers EXPECT ((`customer_id` IS NULL) OR `_krusgraph_found_1` IS NOT NULL) ON VIOLATION DROP ROW" in silver
    assert "ORDER BY `order_date` DESC NULLS LAST" in silver and "-- R1: orders.customer_id points at customers.customer_id" in silver
    assert "CREATE OR REFRESH MATERIALIZED VIEW `workspace`.`gold`.`order_items`" in gold and "ON VIOLATION DROP ROW" in gold
    written = set(re.findall(r"MATERIALIZED VIEW `workspace`\.`(\w+)`\.`(\w+)`", silver + gold))
    assert written and not any(s == "shop" for s, _ in written)
    assert out["settings"]["serverless"] is True and out["settings"]["catalog"] == "workspace"
    for bad in ({"silver_schema": "shop"}, {"gold_schema": "silver"}, {"gold_schema": "shop"}):
        assert call("databricks_pipeline_draft", schema="shop", **bad)["kind"] == "bad_input"


def _run_pipeline_on_sqlite(fake, sql: str) -> None:
    """Run a pipeline notebook on SQLite: each materialized view becomes a table, an expectation that drops the row
    becomes a DELETE of the rows it fails, SELECT * EXCEPT becomes DROP COLUMN."""
    for stmt in [s.strip() for s in re.split(r";\s*\n", sql.replace("-- COMMAND ----------", "")) if "MATERIALIZED VIEW" in s]:
        m = re.search(r"MATERIALIZED VIEW (\S+)", stmt)
        name = dx.to_sqlite(m.group(1))
        expects = re.findall(r"EXPECT \((.*)\) ON VIOLATION DROP ROW", stmt)
        query = re.split(r"\nAS\s*\n?", stmt, maxsplit=1)[1].rstrip(";")
        drop = []
        ex = re.match(r"SELECT \* EXCEPT \(([^)]*)\)", query)
        if ex:
            drop = [c.strip() for c in ex.group(1).split(",")]
            query = "SELECT *" + query[ex.end():]
        fake.db.execute(f"DROP TABLE IF EXISTS {name}")
        fake.db.execute(f"CREATE TABLE {name} AS {dx.to_sqlite(query)}")
        for cond in expects:
            fake.db.execute(f"DELETE FROM {name} WHERE NOT ({cond})")
        for c in drop:
            fake.db.execute(f"ALTER TABLE {name} DROP COLUMN {c}")


def test_the_pipeline_logic_runs_on_sqlite_with_the_fabric_notebooks_outcome(monkeypatch):
    """The dirty shop seed of tests/silver_cases.py through the pipeline's SQL: the same rows reach silver and the same
    rows land in quarantine, per table and rule, as in the Fabric silver notebook; gold has one row per silver line."""
    from silver_cases import EXPECTED_QUARANTINE, seed_rows
    import requests
    fake = dx.FakeDatabricks(rows=seed_rows())
    monkeypatch.setattr(requests, "get", fake.get)
    monkeypatch.setattr(requests, "post", fake.post)
    execute = adapter.connect(dx.HOST, dx.WAREHOUSE, AUTH[1], dx.CATALOG)
    p = plan(adapter.read_schema(execute, "shop", dx.CATALOG))
    out = dd.pipeline(p, dx.CATALOG, order_by={"orders": "order_date"})
    _run_pipeline_on_sqlite(fake, out["files"]["silver.sql"])
    got: dict = {}
    for t, rule in fake.db.execute("SELECT source_table, rule FROM silver.krusgraph_quarantine"):
        got[(t, rule)] = got.get((t, rule), 0) + 1
    want: dict = {}
    for (t, rule, _), n in EXPECTED_QUARANTINE.items():
        want[(t, rule)] = want.get((t, rule), 0) + n
    assert got == want
    raw = {t: len(rows) for t, rows in seed_rows().items()}
    for t, n in raw.items():
        kept = fake.db.execute(f"SELECT COUNT(*) FROM silver.`{t}`").fetchone()[0]
        assert kept == n - sum(v for (qt, _), v in got.items() if qt == t), t
    newest = fake.db.execute("SELECT order_date FROM silver.`orders` WHERE order_id = 100").fetchone()[0]
    assert newest == "2026-12-01"                                                  # the latest by order_by won
    masked = fake.db.execute("SELECT row_json FROM silver.krusgraph_quarantine WHERE source_table = 'customers' LIMIT 1").fetchone()[0]
    assert json.loads(masked)["name"] == "***"
    _run_pipeline_on_sqlite(fake, out["files"]["gold.sql"])
    lines = fake.db.execute("SELECT COUNT(*) FROM silver.`order_items`").fetchone()[0]
    assert fake.db.execute("SELECT COUNT(*) FROM gold.`order_items`").fetchone()[0] == lines


def test_create_pipeline_is_a_dry_run_by_default_then_creates_and_updates_in_place(workspace):
    dry = call("create_databricks_pipeline", name="shop_silver", schema="shop")
    assert dry["dry_run"] is True and not workspace.pipelines and not workspace.workspace
    made = call("create_databricks_pipeline", name="shop_silver", schema="shop", dry_run=False)
    folder = f"/Workspace/Users/{dx.USER}/krusgraph/shop_silver"
    assert made["result"]["mode"] == "created" and set(workspace.workspace) == {f"{folder}/silver", f"{folder}/gold"}
    spec = workspace.pipelines[made["result"]["pipeline_id"]]
    assert spec["libraries"] == [{"notebook": {"path": f"{folder}/silver"}}, {"notebook": {"path": f"{folder}/gold"}}] and spec["serverless"]
    again = call("create_databricks_pipeline", name="shop_silver", schema="shop", dry_run=False)
    assert again["result"] == {**made["result"], "mode": "updated"} and len(workspace.pipelines) == 1
    assert not [c for c in workspace.calls if c[0] == "DELETE" or c[1].endswith(("/delete", "/updates"))]   # deletes and runs nothing
    workspace.pipelines["pl-9"] = {"name": "theirs", "libraries": [{"notebook": {"path": "/Repos/team/etl"}}]}
    refused = call("create_databricks_pipeline", name="theirs", schema="shop", dry_run=False)
    assert refused["kind"] == "bad_input" and workspace.pipelines["pl-9"]["libraries"][0]["notebook"]["path"] == "/Repos/team/etl"


def test_metric_views_carry_the_suggested_measures_and_parse_as_yaml(workspace):
    yaml = pytest.importorskip("yaml")
    out = call("databricks_metric_view_draft", schema="shop")
    mv = {v["fact"]: v for v in out["views"]}["order_items"]
    assert mv["sql"].startswith("CREATE OR REPLACE VIEW `workspace`.`krusgraph`.`order_items_metrics`\nWITH METRICS\nLANGUAGE YAML\nAS $$")
    spec = yaml.safe_load(mv["yaml"])
    assert spec["version"] == 1.1 and spec["source"] == "workspace.shop.order_items"
    assert {m["expr"] for m in spec["measures"]} >= {"COUNT(1)", "SUM(`quantity`)"}
    assert {j["name"] for j in spec["joins"]} == {"orders", "products"} and spec["joins"][0]["on"].startswith("source.`")
    assert all("customers" not in d["expr"] for d in spec["dimensions"])          # one step from the fact, no further
    assert call("databricks_metric_view_draft", schema="shop", metrics_schema="shop")["kind"] == "bad_input"


def test_bundle_export_has_the_pipeline_jobs_and_sql_files(workspace):
    yaml = pytest.importorskip("yaml")
    files = call("export_databricks_bundle", schema="shop", name="shop")["files"]
    assert {"databricks.yml", "resources/shop.pipeline.yml", "resources/shop.job.yml", "src/silver.sql", "src/gold.sql",
            "src/constraints.sql", "src/views.sql", "src/metric_views.sql", "README.generated.md"} == set(files)
    bundle = yaml.safe_load(files["databricks.yml"])
    assert bundle["bundle"]["name"] == "shop" and bundle["targets"]["dev"]["mode"] == "development" and bundle["include"] == ["resources/*.yml"]
    pipe = yaml.safe_load(files["resources/shop.pipeline.yml"])["resources"]["pipelines"]["shop_pipeline"]
    assert pipe["serverless"] is True and pipe["catalog"] == "${var.catalog}" and pipe["libraries"][0] == {"notebook": {"path": "../src/silver.sql"}}
    jobs = yaml.safe_load(files["resources/shop.job.yml"])["resources"]["jobs"]
    assert jobs["shop_build"]["tasks"][1]["pipeline_task"]["pipeline_id"] == "${resources.pipelines.shop_pipeline.id}"
    assert jobs["shop_constraints"]["tasks"][0]["sql_task"]["file"]["path"] == "../src/constraints.sql"
    assert not workspace.ddl and not workspace.pipelines


def test_lineage_reads_the_system_table_for_the_schema(workspace):
    workspace.lineage = [{"source_table_full_name": "workspace.shop.orders", "target_table_full_name": "workspace.gold.order_items",
                          "entity_type": "PIPELINE", "entity_id": "pl-1", "last_seen": "2026-10-20", "events": 3}]
    out = call("databricks_lineage", schema="shop", table="orders")
    assert out["downstream_tables"] == ["workspace.gold.order_items"] and out["entities"] == ["PIPELINE pl-1"]
    sql = [s for s in workspace.statements if "system.access.table_lineage" in s][0]
    assert "lower('workspace.shop.%')" in sql and "date_sub(current_date(), 90)" in sql


def test_every_databricks_tool_has_a_title_hints_and_a_status_line():
    import asyncio
    tools = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
    for name in adapter.TOOLS:
        assert name in tools and tools[name].title, name
    writing = {"create_databricks_constraints", "create_databricks_pipeline", "create_views"}
    for name in ("databricks_constraints_draft", "create_databricks_constraints", "databricks_pipeline_draft", "create_databricks_pipeline",
                 "databricks_metric_view_draft", "export_databricks_bundle", "databricks_lineage"):
        a = tools[name].annotations
        assert a.read_only_hint is (name not in writing) and a.destructive_hint is (name in writing), name
        assert adapter.TOOLS[name][0] in ("Draft only", "Experimental")
    assert set(adapter.TOOLS) | set(adapter.NOT_ON_DATABRICKS) == set(tools)                       # every local tool has a line


def test_the_engine_does_not_know_databricks():
    from fabric_backend import views
    from fabric_backend.dialects import TSQL
    p = plan(seed.schema("shop"))
    assert views.statements(p, "krusgraph") == views.statements(p, "krusgraph", TSQL)
    assert evidence.key_sql("shop", "t", ["a"], DATABRICKS.with_catalog("c")) == (
        "SELECT COUNT(*) AS n, SUM(CASE WHEN `a` IS NULL THEN 1 ELSE 0 END) AS nulls, (SELECT COUNT(*) FROM (SELECT DISTINCT `a` FROM "
        "`c`.`shop`.`t` WHERE `a` IS NOT NULL) AS d) AS distinct_keys FROM `c`.`shop`.`t`")


def test_docs_give_every_local_tool_its_databricks_line_with_the_code_status():
    import pathlib
    md = (pathlib.Path(__file__).resolve().parents[1] / "docs" / "DATABRICKS.md").read_text(encoding="utf-8")
    rows = {}
    for r in md.splitlines():
        if r.startswith("| `"):
            cells = [c.strip() for c in r.split("|")[1:-1]]
            for name in re.findall(r"`([a-z_]+)`", cells[0]):
                rows[name] = cells[1]
    for tool, (status, _note) in adapter.TOOLS.items():
        assert rows.get(tool) == status, tool
    for tool in adapter.NOT_ON_DATABRICKS:
        assert rows.get(tool) in ("Not on Databricks", "Planned"), tool
    assert "Draft only: unit-tested with Databricks mocked" in md and "never run against a Databricks workspace" in md
    assert "not affiliated with Databricks" in md and "partner" not in md.lower()
