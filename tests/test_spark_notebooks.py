"""The generated notebooks run for real on a local Spark session: the silver notebook against the shop seed with
duplicates and broken references (it must agree with silver.simulate), and the drift monitor two nights in a row.
Skipped when PySpark is not installed; CI's `notebooks` job installs PySpark 4.0.1 with Java 17 and runs it, and it ran in
the sandbox on 26 October 2026 with PySpark 4.0.1 and Java 21:

    python -m pytest -q --noconftest tests/test_spark_notebooks.py

Only pure modules are imported here (no MCP server), so a PySpark environment without the server's dependencies runs it.
Delta is not available in a local Spark; the notebooks' TABLE_FORMAT parameter (and the monitor's save) use parquet here."""
import datetime
import json

import pytest

from fabric_backend import monitor, seed, silver
from fabric_backend.graphql import decode, definition
from fabric_backend.infer import plan
from silver_cases import EXPECTED_QUARANTINE, seed_rows

pytest.importorskip("pyspark")
requests = pytest.importorskip("requests")

INFO = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse",
            schema="shop", schemas_enabled=True)
WS = INFO["workspace_id"]
SRC = {"workspace_id": WS, "item_id": "lh-1", "item_name": "shop_lh", "schema": "shop", "schemas_enabled": True, "sql_db": "shop_lh",
       "source_id": "ep-1", "source_type": "SqlAnalyticsEndpoint"}


class Resp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def shop_plan(confirmed=None):
    return plan(seed.schema("shop"), None, confirmed)


def test_generated_notebook_runs_in_pyspark_and_matches_the_python_steps(tmp_path):
    pyspark = pytest.importorskip("pyspark")
    from pyspark.sql import SparkSession
    spark = (SparkSession.builder.master("local[1]").appName("krusgraph-silver-test")
             .config("spark.sql.warehouse.dir", str(tmp_path / "warehouse")).config("spark.ui.enabled", "false")
             .config("spark.sql.shuffle.partitions", "2").getOrCreate())
    try:
        spark.sql("CREATE SCHEMA IF NOT EXISTS shop")
        data = seed_rows()
        for t, rows in data.items():
            spark.createDataFrame([tuple(r.values()) for r in rows], seed.SCHEMAS[t]).write.format("parquet").mode("overwrite").saveAsTable(f"shop.{t}")
        s = silver.spec(shop_plan(), INFO, order_by={"orders": "order_date"})
        cells = silver.cells(s)

        def run(overrides: str):
            ns = {"spark": spark}
            for kind, code in cells:
                if kind == "markdown":
                    continue
                exec(compile(code, "<notebook>", "exec"), ns)
                if kind == "parameters":
                    exec(overrides, ns)                       # what a pipeline's parameter cell does
            return ns

        before = {t: spark.read.table(f"shop.{t}").count() for t in data}
        run('TABLE_FORMAT = "parquet"')                       # no Delta in a local Spark; Fabric keeps "delta"
        expected = silver.simulate(s, data)
        for t in data:
            assert spark.read.table(f"silver.{t}").count() == len(expected["silver"][t]), t
            assert spark.read.table(f"shop.{t}").count() == before[t], t                     # the source is unchanged
        q = spark.read.table("silver.krusgraph_quarantine")
        got = {(r["source_table"], r["rule"], r["reason"]): r["count"] for r in q.groupBy("source_table", "rule", "reason").count().collect()}
        assert got == EXPECTED_QUARANTINE
        assert spark.read.table("silver.orders").filter("order_id = 100").collect()[0]["order_date"] == datetime.date(2026, 12, 1)
        assert json.loads(q.filter("source_table = 'orders' and rule = 'R1'").collect()[0]["row_json"])["customer_id"] == 77
        first = sorted(map(tuple, spark.read.table("silver.orders").collect()))
        run('TABLE_FORMAT = "parquet"')                       # idempotent: the same tables again, quarantine not doubled
        assert sorted(map(tuple, spark.read.table("silver.orders").collect())) == first
        assert spark.read.table("silver.krusgraph_quarantine").count() == sum(EXPECTED_QUARANTINE.values())
        # the run-time guards: the source schema as SILVER_SCHEMA, and a schema holding someone else's table
        with pytest.raises(ValueError, match="is a source table"):
            run('TABLE_FORMAT = "parquet"; SILVER_SCHEMA = "shop"')
        spark.sql("CREATE SCHEMA IF NOT EXISTS other")
        spark.createDataFrame([(1,)], "x int").write.format("parquet").saveAsTable("other.customers")
        with pytest.raises(ValueError, match="was not written by this notebook"):
            run('TABLE_FORMAT = "parquet"; SILVER_SCHEMA = "other"')
        assert spark.read.table("other.customers").count() == 1 and not spark.catalog.tableExists("other.orders")
        assert {t: spark.read.table(f"shop.{t}").count() for t in data} == before
        # a notebook for another source never overwrites this one's silver tables or quarantine
        other_cells = silver.cells(silver.spec(shop_plan(), dict(INFO, item_id="lh-2"), order_by={"orders": "order_date"}))
        ns = {"spark": spark}
        with pytest.raises(ValueError, match="was not written by this notebook"):
            for kind, code in other_cells:
                if kind != "markdown":
                    exec(compile(code, "<notebook>", "exec"), ns)
                    if kind == "parameters":
                        exec('TABLE_FORMAT = "parquet"', ns)
        assert sorted(map(tuple, spark.read.table("silver.orders").collect())) == first
        # a table that points at itself: the rows under a quarantined manager follow it, as in silver.simulate
        from fabric_backend.schema import Column, Schema, Table
        spark.sql("CREATE SCHEMA IF NOT EXISTS hr")
        rows = [(1, "a", None), (2, "b", 1), (3, "c", 99), (4, "d", 3), (5, "e", 4)]
        spark.createDataFrame(rows, "employee_id int, name string, manager_id int").write.format("parquet").saveAsTable("hr.employees")
        sch = Schema(schema="hr")
        sch.tables["employees"] = Table("employees", [Column("employee_id", "int"), Column("name", "string"), Column("manager_id", "int")], schema="hr")
        hr = silver.spec(plan(sch, None, [{"source": "employees", "source_cols": ["manager_id"], "target": "employees", "target_cols": ["employee_id"]}]),
                         dict(INFO, schema="hr"), silver_schema="hr_silver")
        ns = {"spark": spark}
        for kind, code in silver.cells(hr):
            if kind != "markdown":
                exec(compile(code, "<notebook>", "exec"), ns)
                if kind == "parameters":
                    exec('TABLE_FORMAT = "parquet"', ns)
        assert sorted(r["employee_id"] for r in spark.read.table("hr_silver.employees").collect()) == [1, 2]
        assert spark.read.table("hr_silver.krusgraph_quarantine").count() == 3
    finally:
        spark.stop()


def test_generated_monitor_runs_two_nights_in_pyspark(tmp_path, monkeypatch):
    pytest.importorskip("pyspark")
    from pyspark.sql import SparkSession
    from fabric_backend import lineage
    spark = (SparkSession.builder.master("local[1]").appName("krusgraph-monitor-test")
             .config("spark.sql.warehouse.dir", str(tmp_path / "warehouse")).config("spark.ui.enabled", "false").getOrCreate())
    try:
        spark.sql("CREATE SCHEMA IF NOT EXISTS shop")
        for t, rows in seed.rows().items():
            spark.createDataFrame(rows, seed.SCHEMAS[t]).write.format("parquet").mode("overwrite").saveAsTable(f"shop.{t}")
        api_body = decode(definition(plan(seed.schema("shop")), "shop_api", WS, "ep-1", "SqlAnalyticsEndpoint"))
        monkeypatch.setattr(lineage, "rest_items", lambda ws, headers: [{"id": "api-1", "displayName": "shop_api", "type": "GraphQLApi"}])
        monkeypatch.setattr(lineage, "rest_graphql_definition", lambda ws, api_id, headers: api_body)
        monkeypatch.setattr(monitor, "save", (lambda real: lambda *a, **k: real(*a, **dict(k, fmt="parquet")))(monitor.save))
        sent, exits = [], []

        class Utils:
            class credentials:
                @staticmethod
                def getToken(audience):
                    assert audience == "pbi"
                    return "pbi-token"

            class notebook:
                @staticmethod
                def exit(value):
                    exits.append(json.loads(value))
        monkeypatch.setattr(requests, "post", lambda url, json=None, timeout=None: sent.append((url, json)) or Resp(200, {}))
        cells = monitor.notebook_cells(SRC)

        same_second = datetime.datetime(2026, 10, 26, 17, 40, 21, tzinfo=datetime.timezone.utc)

        def night(params: str):
            ns = {"spark": spark, "notebookutils": Utils}
            for kind, code in cells:
                if kind == "markdown" or code.startswith("%pip"):
                    continue                                       # the library is already importable here
                exec(compile(code, "<monitor>", "exec"), ns)
                if kind == "parameters":
                    exec(params, ns)
                if "RUN_AT =" in code:                             # every night in the same second, as when two runs follow
                    ns["RUN_AT"] = same_second                     # each other closely: the order must not hang on the clock
        night('webhook_url = "https://example.test/hook"')
        assert exits[-1]["first_run"] is True and sent == []                                   # a baseline, no message
        cust = spark.read.table("shop.customers").drop("country")
        cust.write.format("parquet").mode("overwrite").saveAsTable("shop.customers_tmp")
        spark.sql("DROP TABLE shop.customers")                     # the test's own source table, changed overnight
        spark.read.table("shop.customers_tmp").write.format("parquet").saveAsTable("shop.customers")
        spark.sql("DROP TABLE shop.customers_tmp")
        night('webhook_url = "https://example.test/hook"')
        assert exits[-1]["changed"] is True and len(sent) == 1
        url, message = sent[0]
        lines = [b["text"] for b in message["attachments"][0]["content"]["body"]]
        assert url == "https://example.test/hook" and lines[0].startswith("Drift monitor for shop_lh.shop: changes since ")
        assert "Column country in table customers disappeared — used by GraphQL API shop_api." in lines
        assert any("shop_api still maps shop.customers.country" in x for x in lines)
        assert spark.read.table("krusgraph.plans").count() == 2
        night('webhook_url = "https://example.test/hook"')
        assert exits[-1]["changed"] is False and len(sent) == 1                               # no change, no message
        assert sorted(r["run"] for r in spark.read.table("krusgraph.plans").collect()) == [1, 2, 3]
        # a plans table saved before the run column: the latest taken_at is still the last run
        old = [("lh-1/shop", "shop", same_second - datetime.timedelta(days=d), json.dumps({"night": d}), False, "{}") for d in (2, 1)]
        spark.createDataFrame(old, "source string, schema string, taken_at timestamp, plan_json string, changed boolean, counts string") \
            .write.format("parquet").saveAsTable("krusgraph.plans_before_run")
        assert monitor.load_last(spark, "krusgraph.plans_before_run", "lh-1/shop")[0] == {"night": 1}
    finally:
        spark.stop()
