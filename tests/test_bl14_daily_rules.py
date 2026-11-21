"""BL14 (P-27), 21 November 2026: the proven rules as a daily check with history.

From validate_plan's answer on the shop (SQLite, synthetic rows) health.daily_rules makes the rule set; the nightly
rules notebook (monitor.daily_rules_cells: plain Python, no %pip) runs it on tests/health_cases' Spark double, appends
one row per rule to `krusgraph`.`health` and alerts on a break with since when. Between two runs a break is planted
(an order line whose product is not in products); the history shows it, once, with its alert text. Nothing here talks
to Fabric, Azure or a webhook: the Key Vault and the post are fakes, and urllib is never reached."""
import datetime as dt
import urllib.request

import pytest

import health_cases as hc
from fabric_backend import evidence, health, monitor
from fabric_backend.dialects import DATABRICKS

DAY = dt.timedelta(days=1)


def validated(lh):
    def execute(sql):
        return lh.execute(sql)
    execute.dialect = DATABRICKS
    return evidence.validate(lh.plan, execute)


@pytest.fixture()
def shop():
    lh = hc.shop()
    return lh, health.daily_rules(lh.plan, validated(lh), hc.MARK)


class Secrets:
    def __init__(self):
        self.read = []

    def getSecret(self, vault, name):
        self.read.append((vault, name))
        return "https://example.invalid/webhook"


def run_notebook(lh, rule_set, run_id, at, posts):
    """The notebook's cells as Fabric runs them, with the pipeline's values on top of the parameters cell, a fake Key
    Vault and a fake post. Returns the cell namespace."""
    cells = monitor.daily_rules_cells(rule_set, "shop_lh.shop")
    secrets = Secrets()
    ns = {"spark": lh.spark(), "notebookutils": type("NU", (), {"credentials": secrets})()}
    for kind, code in cells:
        if kind == "markdown":
            continue
        if kind == "code" and "HEALTH_CTX = " in code:
            code = code.replace("datetime.now(timezone.utc).replace(microsecond=0)", "AT")
            ns["AT"] = at
            ns["_post"] = lambda url, card: posts.append((url, card)) or 200
        exec(compile(code, "<notebook cell>", "exec"), ns)
        if kind == "parameters":
            ns.update(RUN_ID=run_id, ALERT_KEY_VAULT="https://vault.example.invalid/", ALERT_SECRET_NAME="hook")
    return ns


def plant_break(lh):
    """An order line for an order that exists, with a product that does not: one more orphan on
    order_items.product_id -> products and nothing else (the line's key is new)."""
    order = lh.execute("SELECT order_id FROM shop.orders WHERE order_id IS NOT NULL LIMIT 1")[0]["order_id"]
    lh.con.execute("INSERT INTO shop.order_items (order_id, line_no, product_id) VALUES (?, 99, 'P-NOT-THERE')", (order,))


def proven_rows(lh):
    return [r for r in lh.health_rows() if r["check"] == "proven"]


# ------------------------------------------------------------------ the rule set -------------------------------------

def test_the_rule_set_has_only_what_validate_plan_proved(shop):
    lh, rs = shop
    ids = {r["id"]: r for r in rs["rules"]}
    assert {i for i in ids if i.startswith("key:")} == {"key:categories", "key:products", "key:addresses", "key:order_items"}
    assert {n["id"] for n in rs["not_rules"]} >= {"key:customers", "key:orders"}        # not unique when counted
    assert all(n["why"].startswith("not proven") for n in rs["not_rules"])
    orphans = {i: r["allowed"] for i, r in ids.items() if r["kind"] == "orphans"}
    assert orphans == {"orphans:products.category_id:categories": 0, "orphans:addresses.customer_id:customers": 0,
                       "orphans:orders.customer_id:customers": 1, "orphans:order_items.order_id:orders": 1,
                       "orphans:order_items.product_id:products": 0, "orphans:audit_log.customer_id:customers": 1}
    assert ids["level:products.list_price"]["allowed"] == 0
    assert rs["plan_id"] == hc.MARK["plan_id"] and rs["table"] == ["krusgraph", "health"]
    assert all("`shop`.`" in r["sql"] and r["sql"].startswith("SELECT ") for r in rs["rules"])
    for r in rs["rules"]:                                 # read-only statements, one row with a count n
        assert not any(w in r["sql"].upper() for w in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "MERGE ", "CREATE "))


def test_each_rule_counts_what_validate_plan_counted(shop):
    lh, rs = shop
    for r in rs["rules"]:
        assert lh.execute(r["sql"])[0]["n"] == r["allowed"], r["id"]


def test_without_schemas_the_tables_are_named_alone():
    lh = hc.shop()
    rs = health.daily_rules(lh.plan, validated(lh), hc.MARK, schemas_enabled=False)
    assert rs["table"] == [None, "krusgraph_health"]
    assert all("`shop`." not in r["sql"] for r in rs["rules"])


# ------------------------------------------------------------------ the notebook -------------------------------------

def test_the_notebook_is_plain_python_with_the_code_verbatim(shop):
    _lh, rs = shop
    cells = monitor.daily_rules_cells(rs, "shop_lh.shop")
    text = "\n".join(c for k, c in cells if k != "markdown")
    assert "%pip" not in text and "fabric_backend" not in text
    assert health.RULES_CODE in text and health.ALERT_CODE in text
    assert [k for k, _c in cells] == ["markdown", "parameters", "code", "code", "code"]
    assert "key:orders" in cells[0][1]                     # the not proven ones are named, not checked
    for _k, c in cells[1:]:
        compile(c, "<cell>", "exec")


def test_two_runs_with_a_planted_break_give_history_one_break_and_its_alert(shop, monkeypatch):
    lh, rs = shop
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("a real POST was attempted"))
    posts = []
    t1 = hc.NOW
    ns1 = run_notebook(lh, rs, "run-1", t1, posts)
    first = proven_rows(lh)
    assert len(first) == len(rs["rules"]) and {r["status"] for r in first} == {"pass"}
    assert all(r["baseline"] is None for r in first) and posts == []
    assert ns1["title"] == f"Krusgraph daily rules for shop_lh.shop: all {len(rs['rules'])} rule(s) hold"

    plant_break(lh)
    t2 = t1 + DAY
    ns2 = run_notebook(lh, rs, "run-2", t2, posts)
    second = [r for r in proven_rows(lh) if r["run_id"] == "run-2"]
    assert len(second) == len(rs["rules"])
    broke = [r for r in second if r["status"] == "fail"]
    assert [(r["rule"], r["count"], r["baseline"]) for r in broke] == [("orphans:order_items.product_id:products", 1, 0)]
    assert all(r["count"] == r["baseline"] for r in second if r["status"] == "pass")       # the change is marked
    assert [hc_change for hc_change in (ns2["change"](r, ns2["last"]) for r in broke)] == ["new break"]
    assert ns2["title"] == f"Krusgraph daily rules for shop_lh.shop: 1 of {len(rs['rules'])} rule(s) broke"
    assert ns2["lines"] == [
        "BROKE orphans:order_items.product_id:products: every order_items row with a value in product_id finds its products "
        "row, but for at most 0 (rule R1). Now 1 order_items row(s) without their products row, allowed 0 (counted when the "
        "plan was validated); broken since 2026-11-12 06:00 UTC (1 run(s), new break); last held 2026-11-11 06:00 UTC."]
    assert len(posts) == 1 and posts[0][0] == "https://example.invalid/webhook"
    card = hc.card_text(posts[0][1])
    assert "orphans:order_items.product_id:products" in card and "broken since 2026-11-12 06:00 UTC" in card
    assert "P-NOT-THERE" not in card                       # no row value in the alert
    hc.no_row_values(proven_rows(lh), lh)

    # a third run, still broken: since stays at the first failing run
    ns3 = run_notebook(lh, rs, "run-3", t2 + DAY, posts)
    assert ns3["lines"][0].endswith("broken since 2026-11-12 06:00 UTC (2 run(s), still broken); last held 2026-11-11 06:00 UTC.")
    assert len(proven_rows(lh)) == 3 * len(rs["rules"])     # appended, never updated


def test_a_gone_table_fails_its_rules_without_a_count(shop):
    lh, rs = shop
    lh.con.execute("DROP TABLE shop.categories")
    ns = run_notebook(lh, rs, "run-1", hc.NOW, [])
    gone = {r["rule"]: r for r in proven_rows(lh) if r["status"] == "fail"}
    assert set(gone) == {"key:categories", "orphans:products.category_id:categories"}
    assert all(r["count"] is None for r in gone.values())
    assert any("could not be counted" in line for line in ns["lines"])


def test_the_daily_runs_do_not_become_the_pipelines_baseline(shop):
    lh, rs = shop
    run_notebook(lh, rs, "rules-1", hc.NOW, [])
    ns = health.namespace()
    assert ns["previous_run"](lh.execute, lh.exists, ["krusgraph", "health"], hc.MARK["plan_id"], "pipeline-2") == {}


def test_without_a_webhook_nothing_is_sent(shop):
    lh, rs = shop
    plant_break(lh)
    ns = health.namespace()
    rows = [ns["health_row"]({"run_id": "r", "checked_at": hc.NOW, "plan_id": "p", "schema_fingerprint": "f"},
                             "proven", "shop.order_items.product_id", "orphans:order_items.product_id:products", "fail", 1, 0)]
    said = ns["alert"]("t", rows, "", "", "fail", lambda *a: pytest.fail("no secret is read"), lines=["x"])
    assert said.startswith("No alert sent")


# ------------------------------------------------------------------ the same notebook on a local Spark ---------------

def test_the_notebook_runs_on_a_local_spark_with_the_planted_break(tmp_path, shop):
    """Skipped without PySpark (CI's test job); runs where PySpark and Java are installed:
    python -m pytest -q tests/test_bl14_daily_rules.py. Parquet stands in for Delta, as in test_spark_notebooks."""
    pytest.importorskip("pyspark")
    from pyspark.sql import SparkSession

    from fabric_backend import seed
    from silver_cases import seed_rows
    _lh, rs = shop
    spark = (SparkSession.builder.master("local[1]").appName("krusgraph-bl14").config("spark.ui.enabled", "false")
             .config("spark.sql.warehouse.dir", str(tmp_path / "warehouse")).config("spark.sql.shuffle.partitions", "2")
             .config("spark.sql.session.timeZone", "UTC").getOrCreate())
    try:
        spark.sql("CREATE SCHEMA IF NOT EXISTS shop")
        data = seed_rows()
        for t, rows in data.items():
            spark.createDataFrame([tuple(r.values()) for r in rows], seed.SCHEMAS[t]).write.format("parquet") \
                .mode("overwrite").saveAsTable(f"shop.{t}")

        def run(run_id, at):
            ns = {"spark": spark}
            for kind, code in monitor.daily_rules_cells(rs, "shop_lh.shop"):
                if kind == "markdown":
                    continue
                if "HEALTH_CTX = " in code:
                    code = code.replace("datetime.now(timezone.utc).replace(microsecond=0)", "AT")
                    ns["AT"] = at
                exec(compile(code, "<notebook cell>", "exec"), ns)
                if kind == "parameters":
                    ns.update(RUN_ID=run_id, TABLE_FORMAT="parquet")
            return ns

        run("run-1", hc.NOW)
        first = spark.sql("SELECT status, COUNT(*) AS n FROM krusgraph.health GROUP BY status").collect()
        assert {r["status"]: r["n"] for r in first} == {"pass": len(rs["rules"])}
        items = spark.read.table("shop.order_items")
        extra = spark.sql("SELECT i.* FROM shop.order_items AS i JOIN (SELECT DISTINCT order_id FROM shop.orders) AS o "
                          "ON o.order_id = i.order_id LIMIT 1").collect()[0].asDict()
        extra.update(line_no=99, product_id=999999)        # an order that exists, a product that does not
        spark.createDataFrame([tuple(extra[c] for c in items.columns)], items.schema).write.format("parquet") \
            .mode("append").saveAsTable("shop.order_items")
        ns = run("run-2", hc.NOW + DAY)
        broke = spark.sql("SELECT rule, `count`, baseline FROM krusgraph.health WHERE run_id = 'run-2' AND status = 'fail'").collect()
        assert [(r["rule"], r["count"], r["baseline"]) for r in broke] == [("orphans:order_items.product_id:products", 1, 0)]
        assert "broken since 2026-11-12 06:00 UTC (1 run(s), new break); last held 2026-11-11 06:00 UTC." in ns["lines"][0]
    finally:
        spark.stop()
