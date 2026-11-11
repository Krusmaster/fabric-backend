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
from silver_cases import EXPECTED_QUARANTINE, GIVEN_KEYS, seed_rows

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


def shop_plan(confirmed=None, keys=None):
    return plan(seed.schema("shop"), keys, confirmed)


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
        # n208: the seed's duplicate customers and orders leave silver on a given key (K1); a guessed one keeps them
        s = silver.spec(shop_plan(keys=GIVEN_KEYS), INFO, order_by={"orders": "order_date"})
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
        other_cells = silver.cells(silver.spec(shop_plan(keys=GIVEN_KEYS), dict(INFO, item_id="lh-2"), order_by={"orders": "order_date"}))
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


def _spark(tmp_path, name):
    from pyspark.sql import SparkSession
    return (SparkSession.builder.master("local[1]").appName(name)
            .config("spark.sql.warehouse.dir", str(tmp_path / "warehouse")).config("spark.ui.enabled", "false")
            .config("spark.sql.shuffle.partitions", "2").getOrCreate())


def _run_cells(spark, cells, overrides):
    ns = {"spark": spark}
    for kind, code in cells:
        if kind == "markdown":
            continue
        exec(compile(code, "<notebook>", "exec"), ns)
        if kind == "parameters":
            exec(overrides, ns)
    return ns


def test_n115_fix_suggestions_run_in_pyspark_with_the_counts_they_state(tmp_path):
    """Round n115: the silver draft with the fix suggestions in it stops before writing anything until the decisions are
    made, then ends with the counts the suggestions state and the Python steps reach; the source is unchanged."""
    from fabric_backend import evidence, fixes
    from silver_cases import sqlite_execute
    spark = _spark(tmp_path, "krusgraph-n115-test")
    try:
        spark.sql("CREATE SCHEMA IF NOT EXISTS shop")
        data = seed_rows()
        for t, rows in data.items():
            spark.createDataFrame([tuple(r.values()) for r in rows], seed.SCHEMAS[t]).write.format("parquet").mode("overwrite").saveAsTable(f"shop.{t}")
        p = shop_plan()
        sug = fixes.suggest(p, evidence.validate(p, sqlite_execute(data)))
        s = silver.apply_fixes(silver.spec(p, INFO, order_by={"orders": "order_date"}), sug)
        cells = silver.cells(s)
        with pytest.raises(ValueError, match="ORPHANS: choose"):
            _run_cells(spark, cells, 'TABLE_FORMAT = "parquet"')
        assert not spark.catalog.tableExists("silver.customers")                          # stopped before any write
        given = {f["silver"]["id"]: ("set_null" if "set_null" in [c["id"] for c in f["choices"]] else "quarantine")
                 for f in sug if f["kind"] == "choice"}
        before = {t: spark.read.table(f"shop.{t}").count() for t in data}
        _run_cells(spark, cells, 'TABLE_FORMAT = "parquet"\n' + "\n".join(f"ORPHANS[{k!r}] = {v!r}" for k, v in given.items()))
        expected = silver.simulate(s, data, {"ORPHANS": given})
        for t in data:
            assert spark.read.table(f"silver.{t}").count() == len(expected["silver"][t]), t
            assert spark.read.table(f"shop.{t}").count() == before[t], t                     # the source is unchanged
        for f in sug:
            if f["finding"] == "key_not_unique":
                assert spark.read.table(f"silver.{f['table']}").count() == f["counts"]["after"]["silver_rows"]
        assert spark.read.table("silver.orders").filter("customer_id IS NULL").count() == 1      # set_null: kept, reference NULL
        q = spark.read.table("silver.krusgraph_quarantine")
        got = {(r["source_table"], r["reason"]): r["count"] for r in q.groupBy("source_table", "reason").count().collect()}
        want: dict = {}
        for x in expected["quarantine"]:
            want[(x["source_table"], x["reason"])] = want.get((x["source_table"], x["reason"]), 0) + 1
        assert got == want
    finally:
        spark.stop()


def test_n115_a_flat_amount_moves_to_its_header_table_in_pyspark(tmp_path):
    from fabric_backend import fixes
    from fabric_backend.schema import Column, Schema, Table
    spark = _spark(tmp_path, "krusgraph-n115-flat")
    try:
        spark.sql("CREATE SCHEMA IF NOT EXISTS x")
        rows = [(1, 1, 987654.32, 600.0), (1, 2, 987654.32, 400.0), (2, 1, 123457.89, 250.0), (3, 1, 55501.07, 777.13),
                (3, 2, 55501.07, 30.0), (3, 3, 55501.07, 31.0), (None, 1, 5.0, 5.0)]
        ddl = "order_id INT, line_no INT, order_amount DOUBLE, line_amount DOUBLE"
        spark.createDataFrame(rows, ddl).write.format("parquet").mode("overwrite").saveAsTable("x.order_lines")
        sch = Schema(schema="x")
        sch.tables["order_lines"] = Table("order_lines", [Column(c.split()[0], c.split()[1].lower()) for c in ddl.split(", ")], schema="x")
        p = plan(sch)
        e = {"table": "order_lines", "header_column": "order_id", "amount_column": "order_amount", "rows": 6, "header_values": 3,
             "repeated_header_values": 2, "differing_header_values": 0, "pattern": True, "sql": "SELECT 1"}
        s = silver.apply_fixes(silver.spec(p, dict(INFO, schema="x")), [fixes.for_flat_amount(e, "x")])
        _run_cells(spark, silver.cells(s), 'TABLE_FORMAT = "parquet"')
        level = spark.read.table("silver.order_lines_per_order_id")
        assert level.count() == 3 and round(sum(r["order_amount"] for r in level.collect()), 2) == round(987654.32 + 123457.89 + 55501.07, 2)
        lines = spark.read.table("silver.order_lines")
        assert lines.count() == 7 and "order_amount" not in lines.columns
        assert "order_amount" in spark.read.table("x.order_lines").columns                     # the source keeps it
        q = spark.read.table("silver.krusgraph_quarantine").collect()
        assert [r["rule"] for r in q] == ["flat amount"]
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


def test_gold_views_run_on_the_silver_tables_in_pyspark(tmp_path):
    """The gold views' SELECTs, with their rules applied as ON MISMATCH DROP does, over the silver tables the silver notebook
    wrote: open-source Spark has no CREATE MATERIALIZED LAKE VIEW, so the notebook's CREATE cells are recorded instead of
    run, and everything else (the guards, the SELECTs, the columns) runs for real."""
    pytest.importorskip("pyspark")
    from pyspark.sql import SparkSession
    from fabric_backend import gold
    spark = (SparkSession.builder.master("local[1]").appName("krusgraph-gold-test")
             .config("spark.sql.warehouse.dir", str(tmp_path / "warehouse")).config("spark.ui.enabled", "false")
             .config("spark.sql.shuffle.partitions", "2").getOrCreate())
    try:
        spark.sql("CREATE SCHEMA IF NOT EXISTS shop")
        data = seed_rows()
        for t, rows in data.items():
            spark.createDataFrame([tuple(r.values()) for r in rows], seed.SCHEMAS[t]).write.format("parquet").mode("overwrite").saveAsTable(f"shop.{t}")
        s = silver.spec(shop_plan(keys=GIVEN_KEYS), INFO, order_by={"orders": "order_date"})
        ns = {"spark": spark}
        for kind, code in silver.cells(s):
            if kind != "markdown":
                exec(compile(code, "<notebook>", "exec"), ns)
                if kind == "parameters":
                    exec('TABLE_FORMAT = "parquet"', ns)
        expected = silver.simulate(s, data)["silver"]
        g = gold.spec(shop_plan(keys=GIVEN_KEYS), INFO)

        def execute(sql):
            return [r.asDict() for r in spark.sql(sql).collect()]
        for v in g["views"]:
            rows = gold.run_select(v, g, execute)
            assert len(rows) == len(expected[v["fact"]]), v["name"]                # silver is clean: no rule drops a row
            assert list(rows[0]) == [c["as"] for c in v["columns"]]
        # a row whose product is unknown is dropped by its rule, as ON MISMATCH DROP does
        spark.sql("CREATE SCHEMA IF NOT EXISTS silver_x")
        for t in data:
            df = spark.read.table(f"silver.{t}")
            if t == "order_items":
                df = df.unionByName(spark.createDataFrame([(100, 9, 999, 1.0)], seed.SCHEMAS[t]))
            df.write.format("parquet").mode("overwrite").saveAsTable(f"silver_x.{t}")
        gx = gold.spec(shop_plan(keys=GIVEN_KEYS), INFO, silver_schema="silver_x")
        items = next(v for v in gx["views"] if v["fact"] == "order_items")
        rows = gold.run_select(items, gx, execute)
        assert len(rows) == len(expected["order_items"]) and not any(r["product_id"] == 999 for r in rows)
        # the notebook: guards run for real, the CREATE statements are recorded
        real, created = spark.sql, []

        class Recording:
            catalog = spark.catalog

            def sql(self, text):
                if "MATERIALIZED LAKE VIEW" in text:
                    created.append(text.strip())
                    return real("SELECT 1")
                return real(text)
        nb = {"spark": Recording(), "display": lambda x: None}
        for kind, code in gold.cells(g):
            if kind != "markdown":
                exec(compile(code, "<notebook>", "exec"), nb)
        assert [c for c in created if c.startswith("--")] == [st["sql"] for st in gold.statements(g)]
        assert {t: spark.read.table(f"shop.{t}").count() for t in data} == {t: len(r) for t, r in data.items()}   # sources untouched
        nb = {"spark": Recording(), "display": lambda x: None}
        with pytest.raises(ValueError, match="source or silver"):
            for kind, code in gold.cells(g):
                if kind != "markdown":
                    exec(compile(code, "<notebook>", "exec"), nb)
                    if kind == "parameters":
                        exec('GOLD_SCHEMA = "silver"', nb)
    finally:
        spark.stop()


def test_pipeline_check_notebook_runs_after_silver_and_gold_in_pyspark(tmp_path):
    """n110: the pipeline's last step, the check notebook, on a local Spark: the silver notebook writes the silver tables,
    the gold views' SELECTs with their rules stand in for the materialized lake views (open-source Spark has none), and the
    check notebook's own cells count keys, orphans, rows and sums with spark.sql. It passes on what the steps produce, and
    raises, which fails the notebook and so the pipeline run, when a gold view repeats a row, and with a readable message
    on an orphan and a gold sum mismatch.
    n140: the notebook is self-contained (the first live run failed importing a pipeline module the published release did
    not have): every cell runs as written, with no %pip to skip, and an import of fabric_backend fails the test."""
    pytest.importorskip("pyspark")
    import builtins
    from pyspark.sql import SparkSession
    from fabric_backend import gold, notebook, pipeline
    spark = (SparkSession.builder.master("local[1]").appName("krusgraph-pipeline-check-test")
             .config("spark.sql.warehouse.dir", str(tmp_path / "warehouse")).config("spark.ui.enabled", "false")
             .config("spark.sql.shuffle.partitions", "2").getOrCreate())
    try:
        spark.sql("CREATE SCHEMA IF NOT EXISTS shop")
        for t, rows in seed_rows().items():
            spark.createDataFrame([tuple(r.values()) for r in rows], seed.SCHEMAS[t]).write.format("parquet").mode("overwrite").saveAsTable(f"shop.{t}")
        s = silver.spec(shop_plan(keys=GIVEN_KEYS), INFO, order_by={"orders": "order_date"})
        ns = {"spark": spark}
        for kind, code in silver.cells(s):
            if kind != "markdown":
                exec(compile(code, "<notebook>", "exec"), ns)
                if kind == "parameters":
                    exec('TABLE_FORMAT = "parquet"', ns)
        g = gold.spec(shop_plan(keys=GIVEN_KEYS), INFO)
        spark.sql("CREATE SCHEMA IF NOT EXISTS gold")
        for v in g["views"]:
            spark.sql(f"SELECT * FROM ({gold.select_sql(v, g['silver_schema'])}) AS v WHERE "
                      + (" AND ".join(f"({c['check']})" for c in v["constraints"]) or "1 = 1")).write.format("parquet").saveAsTable(v["name"])
        text = pipeline.check_source(pipeline.check_spec(shop_plan(keys=GIVEN_KEYS), s, g), "shop_lh.shop")
        assert "%pip" not in text and "fabric_backend" not in text

        def guarded(name, *a, **k):
            if name.split(".")[0] == "fabric_backend":
                raise ImportError(f"the check notebook imported {name}")
            return builtins.__import__(name, *a, **k)

        def run():
            nb = {"spark": spark, "__builtins__": dict(vars(builtins), __import__=guarded)}
            for kind, code in notebook.parse(text):
                if kind != "markdown":
                    exec(compile(code, "<pipeline_shop_check>", "exec"), nb)
            return nb
        nb = run()
        assert nb["result"]["passed"] and nb["result"]["lines"][-1] == "The check holds."
        assert len(nb["result"]["keys"]) == 6 and len(nb["result"]["relationships"]) == 6
        assert all(k["holds"] for k in nb["result"]["keys"]) and all(r["holds"] for r in nb["result"]["relationships"])
        spark.sql("INSERT INTO gold.order_items SELECT * FROM gold.order_items LIMIT 1")      # the join repeated a row
        with pytest.raises(Exception, match="gold.order_items: .* rows after the join") as e:
            run()
        assert type(e.value).__name__ == "CheckFailed"
        # an orphan in silver and a gold sum that does not match its fact table
        spark.sql("DROP TABLE gold.order_items")
        items = next(v for v in g["views"] if v["fact"] == "order_items")
        spark.sql(f"SELECT * FROM ({gold.select_sql(items, g['silver_schema'])}) AS v").createOrReplaceTempView("items_v")
        spark.sql("SELECT order_id, line_no, product_id, quantity + CASE WHEN line_no = 1 THEN 1 ELSE 0 END AS quantity, "
                  "* EXCEPT (order_id, line_no, product_id, quantity) FROM items_v").write.format("parquet").saveAsTable("gold.order_items")
        spark.sql("INSERT INTO silver.order_items SELECT 4242, 1, product_id, 1.0 FROM silver.order_items LIMIT 1")
        with pytest.raises(Exception) as e:
            run()
        msg = str(e.value)
        assert type(e.value).__name__ == "CheckFailed" and msg.startswith("The check failed, so the pipeline stops: ")
        assert "order_items.order_id -> orders: 1 of " in msg and "(orphans)" in msg
        assert "gold.order_items: SUM(quantity) is " in msg
    finally:
        spark.stop()


def test_sap_demo_one_cell_notebook_writes_every_table(tmp_path):
    """fabric_backend/sap_demo.notebook_inline() as pasted into Fabric (round n33): every table written with its rows
    and types, leading zeros kept. Parquet instead of Delta, as in the tests above."""
    pytest.importorskip("pyspark")
    from pyspark.sql import SparkSession
    from fabric_backend import sap_demo
    spark = (SparkSession.builder.master("local[1]").appName("krusgraph-sap-demo-test")
             .config("spark.sql.warehouse.dir", str(tmp_path / "warehouse")).config("spark.ui.enabled", "false").getOrCreate())
    try:
        cell = sap_demo.notebook_inline().replace('.format("delta")', '.format("parquet")')
        exec(compile(cell, "load_sap_demo_inline.py", "exec"), {"spark": spark})
        for name, (cols, kinds, rows) in sap_demo.tables().items():
            df = spark.table("sap_" + name.lower())
            assert df.columns == cols and df.count() == len(rows), name
        vbak = spark.table("sap_vbak")
        assert dict(vbak.dtypes)["NETWR"] == "decimal(15,2)" and dict(vbak.dtypes)["VBELN"] == "string"
        assert sorted(r.VBELN for r in vbak.collect()) == ["0000000001", "0000000001", "0000000002"]
    finally:
        spark.stop()


def test_n208_guessed_keys_keep_every_row_in_pyspark(tmp_path):
    """Round n208: the audit's two cases on a local Spark. `sales` (K4: customer_id + product_id + store_id) with the same
    customer buying the same product in the same store twice, and `invoice_lines` keyed by a bare `no` (K2) with line 1
    on two invoices: the generated notebook keeps every row, puts nothing in quarantine for a key, says so in its summary,
    and agrees with silver.simulate. The same customers loaded twice leave silver once the key is given (K1)."""
    from fabric_backend.schema import Column, Schema, Table
    from silver_cases import N208_TABLES as TABLES, n208_rows as rows
    spark = _spark(tmp_path, "krusgraph-n208-test")
    try:
        spark.sql("CREATE SCHEMA IF NOT EXISTS dbo")
        ddl = {"int": "int", "varchar": "string", "decimal(18,2)": "double"}
        data = rows()
        data["customers"].append({"customer_id": 1, "name": "Ada"})                        # a real duplicate, for the K1 run
        for t, rs in data.items():
            spark.createDataFrame([tuple(r[c] for c, _ in TABLES[t]) for r in rs],
                                  ", ".join(f"{c} {ddl[ty]}" for c, ty in TABLES[t])).write.format("parquet").mode("overwrite").saveAsTable(f"dbo.{t}")
        sch = Schema(schema="dbo")
        for t, cols in TABLES.items():
            sch.tables[t] = Table(t, [Column(c, ty) for c, ty in cols], schema="dbo")
        info = dict(INFO, schema="dbo")
        for keys, silver_schema in ((None, "silver"), ({"customers": ["customer_id"]}, "silver_k1")):
            s = silver.spec(plan(sch, keys), info, silver_schema=silver_schema)
            ns = _run_cells(spark, silver.cells(s), 'TABLE_FORMAT = "parquet"')
            expected = silver.simulate(s, data)
            for t in data:
                assert spark.read.table(f"{silver_schema}.{t}").count() == len(expected["silver"][t]), (keys, t)
            assert spark.read.table(f"{silver_schema}.sales").count() == 3 and spark.read.table(f"{silver_schema}.invoice_lines").count() == 3
            assert ns["summary"]["sales"]["duplicates"] == ("none removed: the key (customer_id, product_id, store_id) was not checked, "
                                                            "so every row was kept")
            q = spark.read.table(f"{silver_schema}.krusgraph_quarantine")
            got = sorted((r["source_table"], r["rule"]) for r in q.collect())
            assert got == sorted((x["source_table"], x["rule"]) for x in expected["quarantine"])
            if keys:
                assert got == [("customers", "K1")] and spark.read.table(f"{silver_schema}.customers").count() == 2
                assert "duplicates" not in ns["summary"]["customers"]
            else:
                assert got == [] and spark.read.table(f"{silver_schema}.customers").count() == 3
    finally:
        spark.stop()
