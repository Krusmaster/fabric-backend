"""n200: health over time and alerts (docs/LIFECYCLE-DESIGN.md section 8, round 1; docs/HEALTH.md).

The check notebook appends one row per check to `krusgraph`.`health`; the pipeline's silver notebook first compares the
source with the plan it was built from; a failed check posts an Adaptive Card to the owner's webhook (its address a Key
Vault secret); and POST /workload/v1/health gives one health word per data product. Everything here runs the code the
notebooks carry (health.ALERT_CODE, DRIFT_CODE, HEALTH_CODE, pipeline.CHECK_CODE), on SQLite through tests/health_cases.py;
tests/test_spark_notebooks.py runs the same cells on a local Spark."""
import datetime as dt
import json
import re
import sys
from collections import Counter

import pytest

import health_cases as hc
from fabric_backend import health, notebook, pipeline, silver
from silver_cases import EXPECTED_QUARANTINE

NS = health.namespace()
SETTINGS = dict(health.DEFAULTS)


def ctx(run_id="run-1", at=hc.NOW, mark=hc.MARK):
    return {"run_id": run_id, "checked_at": at, "plan_id": mark["plan_id"], "schema_fingerprint": mark["schema_fingerprint"]}


def one_run(lh, run_id="run-1", at=hc.NOW, mark=hc.MARK, settings=None, schedule=None, write=True):
    """The check notebook's health step through the library: check, the previous run as baseline, the rows, the write."""
    spec = lh.check_spec(mark, schedule)
    exists = lh.exists
    prev = NS["previous_run"](lh.execute, exists, spec["health"]["table"], mark["plan_id"], run_id)
    try:
        result = NS["check"](spec, lh.execute, exists)
    except NS["CheckFailed"]:
        result = None
    s = dict(SETTINGS, interval_minutes=spec["health"]["interval_minutes"], **(settings or {}))
    rows = NS["health_rows"](spec, result, lh.execute, exists, ctx(run_id, at, mark), prev, s,
                             history=lambda name: NS["last_write"](lambda sql: [r.asDict() for r in lh.spark().sql(sql).collect()], name))
    if write:
        NS["write_health"](lh.spark(), spec["health"]["table"], rows, "delta")
    return rows


def by(rows, check):
    return {(r["object"], r["rule"]): (r["status"], r["count"]) for r in rows if r["check"] == check}


# ------------------------------------------------------------------ one row per check ---------------------------------

def test_the_shop_gets_one_row_per_check_with_the_right_statuses():
    lh = hc.shop()
    rows = one_run(lh)
    assert set(Counter(r["check"] for r in rows)) == {"key", "orphans", "join_rows", "join_sums", "row_count", "freshness", "quarantine"}
    assert set(r["check"] for r in rows) <= set(health.CHECKS)
    spec = lh.check_spec()
    assert by(rows, "key") == {(f"silver.{k['table']}", k["rule"]): ("pass", 0) for k in spec["keys"]}
    assert len(by(rows, "orphans")) == len(spec["relationships"]) and {v for v in by(rows, "orphans").values()} == {("pass", 0)}
    assert by(rows, "join_rows") == {(f"gold.{v['view']}", "rows"): ("pass", 0) for v in spec["views"]}
    assert by(rows, "join_sums") == {("gold.order_items", "sums"): ("pass", 0)}          # only views with an amount
    counts = by(rows, "row_count")
    assert set(counts) == {(f"silver.{t}", "rows") for t in spec["health"]["silver_tables"]} | \
                          {(f"gold.{v['view']}", "rows") for v in spec["views"]}
    assert all(s == "pass" and n > 0 for s, n in counts.values())
    assert counts[("silver.orders", "rows")][1] == lh.execute("SELECT COUNT(*) AS n FROM silver.orders")[0]["n"]
    assert by(rows, "freshness") == {(f"shop.{t}", "minutes since last write"): ("pass", 180) for t in spec["health"]["silver_tables"]}
    # the quarantine counts per table and rule are the silver notebook's own (silver_cases.EXPECTED_QUARANTINE)
    expected = Counter()
    for (table, rule, _reason), n in EXPECTED_QUARANTINE.items():
        expected[(f"silver.{table}", rule)] += n
    assert by(rows, "quarantine") == {k: ("warn", n) for k, n in expected.items()}
    assert {r["run_id"] for r in rows} == {"run-1"} and {r["plan_id"] for r in rows} == {hc.MARK["plan_id"]}
    assert all(r["baseline"] is None for r in rows)                                       # the first run has none
    assert lh.health_rows() and len(lh.health_rows()) == len(rows)                         # appended to krusgraph.health


def test_the_mill_rows_show_exactly_its_planted_problems():
    lh = hc.mill_lakehouse()
    rows = one_run(lh)
    planted = json.loads((__import__("pathlib").Path(__file__).parent / "fixtures/mill/planted_issues.json").read_text())
    # the duplicate supplier price: a key guessed from names (K2), counted and reported, never a failure (n208)
    dup = planted["non_unique_keys"][0]
    assert by(rows, "key")[(f"silver.{dup['table']}", dup["rule"])] == ("warn", dup["rows"] - dup["distinct"])
    assert [r for r in rows if r["check"] == "key" and r["status"] != "pass"] == \
           [r for r in rows if r["check"] == "key" and r["object"] == f"silver.{dup['table']}"]
    # the orphans: the silver notebook put them in quarantine, so silver has none and the counts are the planted ones;
    # deliveries of the two orphan order lines follow their lines there (R3)
    q = by(rows, "quarantine")
    for o in planted["orphans"]:
        assert q[(f"silver.{o['source']}", "R1")] == ("warn", o["orphans"]), o
    assert q[("silver.deliveries", "R3")][0] == "warn"
    assert set(q) == {(f"silver.{o['source']}", "R1") for o in planted["orphans"]} | {("silver.deliveries", "R3")}
    assert all(s == "pass" for s, _ in by(rows, "orphans").values())
    assert not [r for r in rows if r["status"] == "fail"]
    # the keyless event log has a row count, no key row
    assert ("silver.machine_events", "rows") in by(rows, "row_count")
    assert not any(r["object"] == "silver.machine_events" for r in rows if r["check"] == "key")


def test_a_failed_check_is_a_fail_row_and_a_missing_table_too():
    lh = hc.shop()
    lh.con.execute("INSERT INTO silver.order_items VALUES (4242, 1, 1, 1.0)")              # an orphan after silver
    lh.con.execute("UPDATE gold.order_items SET quantity = 99.0 WHERE rowid = 1")          # a sum that no longer matches
    rows = one_run(lh)
    assert by(rows, "orphans")[("silver.order_items.order_id", "R1")] == ("fail", 1)
    assert by(rows, "join_sums")[("gold.order_items", "sums")] == ("fail", 1)
    lh2 = hc.shop()
    lh2.con.execute("DROP TABLE gold.orders")
    rows = one_run(lh2)
    assert by(rows, "row_count")[("gold.orders", "missing")] == ("fail", 0)


# ------------------------------------------------------------------ never a row value --------------------------------

def test_no_row_value_reaches_the_health_table():
    for lh in (hc.shop(), hc.mill_lakehouse()):
        rows = one_run(lh)
        written = lh.health_rows()
        hc.no_row_values(written, lh)
        assert [c[1] for c in lh.con.execute("PRAGMA krusgraph.table_info(health)").fetchall()] == hc.health_columns()
        text = json.dumps(written, default=str)
        # the sums the check computes (SUM(quantity) is 324.0 on the shop) are never stored, only pass or fail
        result = NS["check"](lh.check_spec(), lh.execute, lh.exists)
        for j in result["joins"]:
            for s in j["sums"]:
                assert f'"{s["before"]}"' not in text and f": {s['before']}," not in text
        assert all(isinstance(r["count"], (int, type(None))) for r in rows)


def test_the_health_step_reads_no_source_rows():
    """Freshness comes from Delta's table history (a commit time); the step never selects from a source table."""
    lh = hc.shop()
    seen = []
    real = lh.execute
    lh.execute = lambda sql: seen.append(sql) or real(sql)
    cells = pipeline.check_cells(lh.check_spec(), "shop_lh.shop")
    hc.run_cells(cells, lh.spark(), {"RUN_ID": "run-1"})
    assert not [s for s in seen if re.search(r"FROM\s+`?shop`?\.", s)], seen
    assert any(r["check"] == "freshness" and r["status"] == "pass" for r in lh.health_rows())


# ------------------------------------------------------------------ baseline and thresholds -------------------------

def test_the_baseline_is_the_previous_run_of_the_same_plan():
    lh = hc.shop()
    first = one_run(lh, "run-1")
    second = one_run(lh, "run-2", hc.NOW + dt.timedelta(days=1))
    was = {(r["check"], r["object"], r["rule"]): r["count"] for r in first}
    assert all(r["baseline"] == was[(r["check"], r["object"], r["rule"])] for r in second if r["check"] != "freshness")
    other = {"plan_id": "plan-abcdefabcdef", "schema_fingerprint": "sha256:ff"}
    third = one_run(lh, "run-3", hc.NOW + dt.timedelta(days=2), mark=other)
    assert all(r["baseline"] is None for r in third)                                       # another plan: no baseline
    fourth = one_run(lh, "run-4", hc.NOW + dt.timedelta(days=3))
    assert {r["baseline"] for r in fourth if r["check"] == "row_count"} == \
           {r["count"] for r in second if r["check"] == "row_count"}                          # run-2, not run-3


@pytest.mark.parametrize("keep,status", [(0.5, "warn"), (0.49, "warn"), (0.52, "pass"), (1.0, "pass")])
def test_a_row_count_that_falls_by_half_or_more_warns(keep, status):
    lh = hc.shop()
    one_run(lh, "run-1")
    n = lh.execute("SELECT COUNT(*) AS n FROM silver.order_items")[0]["n"]
    lh.con.execute(f"DELETE FROM silver.order_items WHERE rowid IN (SELECT rowid FROM silver.order_items LIMIT {n - round(n * keep)})")
    rows = one_run(lh, "run-2", hc.NOW + dt.timedelta(days=1), write=False)
    got = next(r for r in rows if r["check"] == "row_count" and r["object"] == "silver.order_items")
    assert (got["status"], got["count"], got["baseline"]) == (status, round(n * keep), n)


def test_the_owner_s_threshold_is_a_parameter():
    lh = hc.shop()
    one_run(lh, "run-1")
    lh.con.execute("DELETE FROM silver.orders WHERE rowid IN (SELECT rowid FROM silver.orders LIMIT 10)")
    rows = one_run(lh, "run-2", write=False, settings={"row_drop": 0.1})
    assert by(rows, "row_count")[("silver.orders", "rows")][0] == "warn"
    params = dict(pipeline.check_cells(lh.check_spec(), "x"))["parameters"]
    assert "ROW_COUNT_DROP = 0.5" in params and "FRESHNESS_WARN_INTERVALS = 2" in params and "FRESHNESS_FAIL_INTERVALS = 3" in params


# ------------------------------------------------------------------ freshness from table history ---------------------

@pytest.mark.parametrize("hours_ago,schedule,status", [
    (47, None, "pass"), (49, None, "warn"), (73, None, "fail"),                     # daily: warn after 2 days, fail after 3
    (7, {"every": "hours", "hours": 4}, "pass"), (9, {"every": "hours", "hours": 4}, "warn"), (13, {"every": "hours", "hours": 4}, "fail"),
])
def test_freshness_warns_after_two_intervals_and_fails_after_three(hours_ago, schedule, status):
    lh = hc.shop()
    lh.commit("shop.orders", hc.NOW - dt.timedelta(hours=hours_ago))
    rows = one_run(lh, schedule=schedule, write=False)
    assert by(rows, "freshness")[("shop.orders", "minutes since last write")] == (status, hours_ago * 60)
    assert lh.check_spec(schedule=schedule)["health"]["interval_minutes"] == (240 if schedule else 1440)


def test_freshness_reads_the_last_commit_that_wrote_rows():
    lh = hc.shop()
    lh.commit("shop.orders", hc.NOW - dt.timedelta(hours=80))
    lh.commit("shop.orders", hc.NOW - dt.timedelta(hours=1), "OPTIMIZE")                  # maintenance: no new rows
    lh.commit("shop.orders", hc.NOW - dt.timedelta(minutes=30), "VACUUM END")
    rows = one_run(lh, write=False)
    assert by(rows, "freshness")[("shop.orders", "minutes since last write")] == ("fail", 80 * 60)
    lh.commit("shop.orders", hc.NOW - dt.timedelta(minutes=10), "MERGE")
    assert by(one_run(lh, write=False), "freshness")[("shop.orders", "minutes since last write")] == ("pass", 10)
    del lh.commits["shop.customers"]                                                        # not a Delta table
    assert by(one_run(lh, write=False), "freshness")[("shop.customers", "no history")] == ("warn", None)


# ------------------------------------------------------------------ drift against the plan ----------------------------

def drift_run(lh, run_id="run-1"):
    s = dict(lh.silver_spec, drift=lh.drift_spec())
    cells = silver.cells(s)
    ns = {"spark": lh.spark()}
    for kind, code in cells:
        if kind == "parameters":
            exec(code, ns)
            ns["RUN_ID"] = run_id
        elif kind == "code" and "n200: drift" in code:
            exec(compile(code, "<silver drift cell>", "exec"), ns)
            return ns


def test_the_drift_step_is_the_silver_notebook_s_first_code_cell_and_only_in_the_pipeline():
    lh = hc.shop()
    cells = silver.cells(dict(lh.silver_spec, drift=lh.drift_spec()))
    code = [c for k, c in cells if k == "code"]
    assert "n200: drift" in code[0] and "CREATE SCHEMA IF NOT EXISTS {{q(SILVER_SCHEMA)}}" not in code[0]
    assert code.index(code[0]) < next(i for i, c in enumerate(code) if "def write_silver" in c)
    assert "spark.createDataFrame" not in code[0].split("def write_health")[0]              # the only write is the health row
    assert not any("n200: drift" in c for _k, c in silver.cells(lh.silver_spec))             # the stand-alone draft is unchanged
    assert "RUN_ID" in dict(cells)["parameters"] and "ALERT_KEY_VAULT" in dict(cells)["parameters"]


def test_no_drift_is_one_pass_row():
    lh = hc.shop()
    drift_run(lh)
    assert [(r["check"], r["object"], r["rule"], r["status"]) for r in lh.health_rows()] == [("drift", "shop", "plan", "pass")]


def test_a_drift_that_does_not_break_silver_is_recorded_and_the_run_goes_on():
    lh = hc.shop()
    d = lh.drift_spec()
    unused = next((t, c) for t, b in d["tables"].items() for c in b["columns"] if c not in b["uses"])
    lh.types[("shop", "orders")]["coupon_code"] = "string"                                  # a new column
    lh.types[("shop", "products")]["list_price"] = "decimal(10,2)"                          # double -> decimal
    del lh.types[("shop", unused[0])][unused[1]]                                            # a column nothing uses
    lh.load("shop", "returns", [("return_id", "int")], [])                                  # a new table
    lh.types[("shop", "customers")]["customer_id"] = "bigint"                               # int -> bigint: same family
    drift_run(lh)                                                                           # no exception: the run goes on
    got = {(r["object"], r["rule"]): r["status"] for r in lh.health_rows()}
    assert got == {("shop.orders.coupon_code", "column_added"): "warn", ("shop.products.list_price", "type_changed"): "warn",
                   (f"shop.{unused[0]}.{unused[1]}", "column_removed"): "warn", ("shop.returns", "table_added"): "warn"}


@pytest.mark.parametrize("break_it,expect", [
    (lambda lh: lh.types[("shop", "orders")].pop("order_id"), "orders.order_id is gone"),          # a key column
    (lambda lh: lh.types[("shop", "order_items")].pop("product_id"), "order_items.product_id is gone"),   # a relationship column
    (lambda lh: lh.types[("shop", "orders")].pop("order_date"), "orders.order_date is gone"),      # the ordering column
    (lambda lh: lh.con.execute("DROP TABLE shop.addresses"), "the source table addresses is gone"),
])
def test_a_drift_that_breaks_silver_stops_the_run_before_anything_is_written(break_it, expect):
    lh = hc.shop()
    break_it(lh)
    with pytest.raises(Exception) as e:
        drift_run(lh)
    assert type(e.value).__name__ == "DriftBreaks"
    assert "the run stops before anything is written" in str(e.value) and expect in str(e.value)
    assert {name for name, _n in lh.writes} == {"`krusgraph`.`health`"}                     # only the health rows
    assert any(r["status"] == "fail" and r["check"] == "drift" for r in lh.health_rows())


def test_drift_compares_types_by_family():
    fam = NS["type_family"]
    assert fam("varchar") == fam("string") == fam("nvarchar(50)") and fam("datetime2") == fam("timestamp")
    assert fam("int") == fam("bigint") and fam("decimal(18,2)") == fam("numeric") and fam("float") == fam("double")
    assert fam("int") != fam("string") and fam("date") != fam("timestamp")


# ------------------------------------------------------------------ the alert -------------------------------------------

def fail_rows():
    lh = hc.shop()
    lh.con.execute("INSERT INTO silver.order_items VALUES (4242, 1, 1, 1.0)")
    lh.con.execute("UPDATE gold.order_items SET quantity = 99.0 WHERE rowid = 1")
    return lh, one_run(lh)


def test_a_failed_check_posts_an_adaptive_card_without_row_values():
    lh, rows = fail_rows()
    sent, asked = [], []
    msg = NS["alert"]("Krusgraph health for shop_lh.shop: 2 check(s) failed", rows, "https://vault.vault.azure.net/", "teams-hook", "fail",
                      lambda v, n: asked.append((v, n)) or "https://example.invalid/workflows/abc?sig=SECRET",
                      post=lambda url, card: sent.append((url, card)) or 202)
    assert msg == "Alert sent (HTTP 202)." and asked == [("https://vault.vault.azure.net/", "teams-hook")]
    (url, card), = sent
    assert url.endswith("sig=SECRET") and "SECRET" not in msg
    content = card["attachments"][0]["content"]
    assert card["type"] == "message" and content["type"] == "AdaptiveCard" and content["version"] == "1.4"
    texts = [b["text"] for b in content["body"]]
    assert texts[0].endswith("2 check(s) failed")
    assert "FAIL orphans silver.order_items.order_id (R1): 1" in texts and "FAIL join_sums gold.order_items (sums): 1" in texts
    assert not any(t.startswith(("PASS", "WARN")) for t in texts)                          # alert_on fail: failures only
    body = json.dumps(card)
    for value in ("99.0", "4242", "324", "Lakeside", "SECRET"):                            # amounts, keys, names, the address
        assert value not in body, value


def test_no_alert_without_a_failure_a_vault_or_an_https_address_and_never_the_address_in_an_error():
    lh = hc.shop()
    ok = one_run(lh)
    never = lambda *a: pytest.fail("nothing should be posted")                             # noqa: E731
    assert NS["alert"]("t", ok, "https://v/", "s", "fail", lambda v, n: "https://x", post=never) == "No alert: nothing failed."
    _lh, bad = fail_rows()
    assert "no webhook is set" in NS["alert"]("t", bad, "", "", "fail", never, post=never)
    assert "not an https:// address" in NS["alert"]("t", bad, "https://v/", "s", "fail", lambda v, n: "http://x", post=never)

    def boom(v, n):
        raise PermissionError("Forbidden: vault https://v/ secret s for user x")
    assert NS["alert"]("t", bad, "https://v/", "s", "fail", boom, post=never) == \
        "No alert sent: the secret could not be read from the Key Vault (PermissionError)."

    def down(url, card):
        raise ConnectionError(url)
    msg = NS["alert"]("t", bad, "https://v/", "s", "fail", lambda v, n: "https://hook/?sig=SECRET", post=down)
    assert "SECRET" not in msg and "could not be sent (ConnectionError)" in msg
    # alert_on "warn": the shop's quarantine warnings are sent too
    sent = []
    NS["alert"]("t", ok, "https://v/", "s", "warn", lambda v, n: "https://x", post=lambda u, c: sent.append(c) or 200)
    assert any(b["text"].startswith("WARN quarantine") for b in sent[0]["attachments"][0]["content"]["body"])


def test_the_webhook_address_is_never_in_code_and_the_pipeline_carries_the_alert_parameters():
    lh = hc.shop()
    text = pipeline.check_source(lh.check_spec(), "shop_lh.shop", hc.WS, "lh-1", "shop_lh")
    assert 'ALERT_KEY_VAULT = ""' in text and 'ALERT_SECRET_NAME = ""' in text
    assert "credentials.getSecret(vault, name)" in text and "webhook.office.com" not in text and "logic.azure.com" not in text
    content = pipeline.pipeline_content("s", "g", "c", "x")
    props = content["properties"]
    assert props["parameters"] == {"alert_key_vault": {"type": "string", "defaultValue": ""},
                                   "alert_secret_name": {"type": "string", "defaultValue": ""},
                                   "alert_on": {"type": "string", "defaultValue": "fail"}}
    silver_a, gold_a, check_a = props["activities"]
    for a in (silver_a, check_a):
        p = a["typeProperties"]["parameters"]
        assert p["RUN_ID"]["value"] == {"value": "@pipeline().RunId", "type": "Expression"}
        assert p["ALERT_KEY_VAULT"]["value"]["value"] == "@pipeline().parameters.alert_key_vault"
    assert "parameters" not in gold_a["typeProperties"]


# ------------------------------------------------------------------ the notebooks run as written ----------------------

def guarded():
    import builtins

    def imp(name, *a, **k):
        if name.split(".")[0] == "fabric_backend":
            raise ImportError(f"the notebook imported {name}")
        return builtins.__import__(name, *a, **k)
    return dict(vars(builtins), __import__=imp)


def test_the_check_notebook_runs_twice_and_its_rows_share_the_pipeline_run_id(capsys):
    lh = hc.shop()
    now = dt.datetime.now(dt.timezone.utc)
    for t in lh.check_spec()["health"]["silver_tables"]:
        lh.commit(f"shop.{t}", now - dt.timedelta(hours=1))
    cells = pipeline.check_cells(lh.check_spec(), "shop_lh.shop")
    hc.run_cells(cells, lh.spark(), {"RUN_ID": "pipeline-run-1"}, guarded())
    hc.run_cells(cells, lh.spark(), {"RUN_ID": "pipeline-run-2"}, guarded())
    rows = lh.health_rows()
    assert {r["run_id"] for r in rows} == {"pipeline-run-1", "pipeline-run-2"}
    second = [r for r in rows if r["run_id"] == "pipeline-run-2"]
    assert all(r["baseline"] is not None for r in second if r["check"] in ("row_count", "key", "orphans"))
    out = capsys.readouterr().out
    assert "The check holds." in out and "No alert: nothing failed." in out and "Health: 38 row(s) for run pipeline-run-1" in out


def test_a_failing_check_notebook_writes_its_rows_before_it_stops():
    lh = hc.shop()
    lh.con.execute("INSERT INTO silver.order_items VALUES (4242, 1, 1, 1.0)")
    cells = pipeline.check_cells(lh.check_spec(), "shop_lh.shop")
    with pytest.raises(Exception) as e:
        hc.run_cells(cells, lh.spark(), {"RUN_ID": "r1"}, guarded())
    assert type(e.value).__name__ == "CheckFailed"
    assert any(r["status"] == "fail" and r["check"] == "orphans" for r in lh.health_rows())
    lh2 = hc.shop()
    lh2.con.execute("DROP TABLE gold.orders")
    with pytest.raises(Exception, match="gold views missing in gold: orders"):
        hc.run_cells(cells, lh2.spark(), {"RUN_ID": "r1"}, guarded())
    assert ("row_count", "gold.orders", "missing", "fail") in {(r["check"], r["object"], r["rule"], r["status"]) for r in lh2.health_rows()}


def test_the_notebooks_import_only_the_standard_library():
    lh = hc.shop()
    texts = [pipeline.check_source(lh.check_spec(), "x"), silver.notebook_source(dict(lh.silver_spec, drift=lh.drift_spec()))]
    allowed = {"json", "math", "urllib", "datetime", "uuid", "pyspark", "hashlib", "re"}
    for text in texts:
        assert "%pip" not in text and "fabric_backend" not in text
        for kind, code in notebook.parse(text):
            if kind == "markdown":
                continue
            imported = {n.split(".")[0] for line in code.splitlines() for n in
                        (line.split()[1:2] if line.lstrip().startswith(("import ", "from ")) else [])}
            assert imported <= allowed, imported
    assert health.HEALTH_CODE in texts[0] and health.ALERT_CODE in texts[0] and pipeline.CHECK_CODE in texts[0]
    assert health.DRIFT_CODE in texts[1] and health.ALERT_CODE in texts[1]


# ------------------------------------------------------------------ the item reads it ----------------------------------

def product(name="Sales", plan_id=hc.MARK["plan_id"]):
    return {"name": name, "plan_id": plan_id}


def test_one_health_word_per_product():
    lh = hc.shop()
    assert health.summarize([], [product()]) == [{"name": "Sales", "plan_id": hc.MARK["plan_id"], "health": "not checked yet",
                                                   "run_id": None, "checked_at": None, "checks": 0, "findings": []}]
    rows = one_run(lh)
    amber = health.summarize(rows, [product(), product("Other", "plan-999999999999")])
    assert [p["health"] for p in amber] == ["amber", "not checked yet"]                      # the shop's quarantined rows
    assert {f["check"] for f in amber[0]["findings"]} == {"quarantine"} and amber[0]["checks"] == len(rows)
    assert set(amber[0]["findings"][0]) == {"check", "object", "rule", "status", "count", "baseline"}
    green = health.summarize([r for r in rows if r["status"] == "pass"], [product()])[0]
    assert green["health"] == "green" and green["findings"] == []
    _lh, bad = fail_rows()
    red = health.summarize(bad, [product()])[0]
    assert red["health"] == "red" and red["findings"][0]["status"] == "fail"
    assert [f["status"] for f in red["findings"]] == sorted((f["status"] for f in red["findings"]), key=["fail", "warn"].index)
    only_drift = [dict(r, check="drift", object="shop", rule="plan", status="pass") for r in rows[:1]]
    stopped = health.summarize(only_drift, [product()])[0]
    assert stopped["health"] == "amber" and stopped["findings"][0]["check"] == "run"


def test_the_read_sql_takes_the_latest_run_of_each_plan():
    lh = hc.shop()
    one_run(lh, "run-1", hc.NOW)
    lh.con.execute("INSERT INTO silver.order_items VALUES (4242, 1, 1, 1.0)")
    one_run(lh, "run-2", hc.NOW + dt.timedelta(days=1))
    sql = health.read_sql(True, [hc.MARK["plan_id"]])
    rows = lh.execute(sql)                                                                 # brackets and ROW_NUMBER read in SQLite too
    assert {r["run_id"] for r in rows} == {"run-2"}
    assert health.summarize(rows, [product()])[0]["health"] == "red"
    assert "[dbo].[krusgraph_health]" in health.read_sql(False, [hc.MARK["plan_id"]])
    with pytest.raises(ValueError):
        health.read_sql(True, ["plan-1'; DROP TABLE x; --"])


jwt = pytest.importorskip("jwt")


@pytest.fixture
def api(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from starlette.applications import Starlette
    from starlette.testclient import TestClient
    import test_workload_api as twa
    from fabric_backend import server, workload_api
    from fabric_backend.entra import Validator
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    obo = twa.FakeOBO()
    monkeypatch.setattr(server, "limiter", None)
    lh = hc.shop()
    seen = {}

    def execute_factory(item, token):
        seen["token"], seen["item"] = token, item

        def execute(sql):
            seen.setdefault("sql", []).append(sql)
            if "INFORMATION_SCHEMA.TABLES" in sql:
                return [{"n": 1 if lh.exists("`krusgraph`.`health`") else 0}]
            return lh.execute(sql)
        return execute
    monkeypatch.setattr(server, "_workspace_id", lambda ws, headers: hc.WS)
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": "Lakehouse", "id": "lh-1", "displayName": src,
                                                                            "schemas_enabled": True})
    monkeypatch.setattr(server, "_execute_factory", execute_factory)
    app = Starlette(routes=workload_api.routes(twa.WL, Validator(twa.WL, twa.FakeJWKS(priv.public_key())), obo))
    return TestClient(app), lh, seen, obo, twa.tok(priv)


def post_health(client, token, body):
    return client.post("/workload/v1/health", json=body, headers={"Authorization": f"Bearer {token}",
                                                                  "Origin": "https://app.fabric.microsoft.com"})


def test_the_health_endpoint_answers_as_the_signed_in_user_with_the_documented_shape(api):
    client, lh, seen, obo, token = api
    body = {"workspace": hc.WS, "source": "shop_lh", "products": [product(), product("Finance", "plan-abcdefabcdef")]}
    r = post_health(client, token, body)
    assert r.status_code == 200, r.text
    first = r.json()
    assert [p["health"] for p in first["products"]] == ["not checked yet", "not checked yet"]
    assert "does not exist yet" in first["note"]
    one_run(lh)
    r = post_health(client, token, body)
    out = r.json()
    assert set(out) == {"products", "table", "read_as", "note"} and out["table"] == "krusgraph.health"
    assert out["read_as"] == "the signed-in user" and seen["token"].startswith("obo:")      # on behalf of the user
    assert any("database.windows.net" in scope or "sql" in scope.lower() for _t, scope in obo.calls)
    sales, finance = out["products"]
    assert set(sales) == {"name", "plan_id", "health", "run_id", "checked_at", "checks", "findings"}
    assert (sales["health"], sales["run_id"], finance["health"]) == ("amber", "run-1", "not checked yet")
    assert sales["checked_at"].startswith("2026-11-11T06:00:00")
    assert all(set(f) == {"check", "object", "rule", "status", "count", "baseline"} for f in sales["findings"])
    assert not [s for s in seen["sql"] if not s.lstrip().upper().startswith(("SELECT", "WITH"))]   # read-only
    # the shape is the one docs/HEALTH.md documents
    doc = (__import__("pathlib").Path(__file__).resolve().parents[1] / "docs/HEALTH.md").read_text(encoding="utf-8")
    for key in ("products", "health", "findings", "not checked yet", "green", "amber", "red", "/workload/v1/health"):
        assert key in doc, key


@pytest.mark.parametrize("body,why", [
    ({"workspace": hc.WS, "source": "shop_lh"}, "'products'"),
    ({"workspace": hc.WS, "source": "shop_lh", "products": []}, "'products'"),
    ({"workspace": hc.WS, "source": "shop_lh", "products": [{"name": "x", "plan_id": "plan-1'; --"}]}, "plan_id"),
])
def test_the_health_endpoint_refuses_a_bad_request(api, body, why):
    client, _lh, seen, _obo, token = api
    r = post_health(client, token, body)
    assert r.status_code == 400 and why in r.json()["error"] and "sql" not in seen


# ------------------------------------------------------------------ the item's Create hands over its plan ---------------

from test_workload_build import make, keys, _build, _review  # noqa: E402,F401  (the workload build harness)


def test_the_item_s_create_gives_the_pipeline_its_review_s_plan_and_the_health_steps(make, monkeypatch):
    """The pipeline card of an item's dry run: the health rows will name the plan outputs.json records (the review's
    plan id), the pipeline's silver notebook starts with the drift step, and the steps say how the owner hears of a failure."""
    from fabric_backend import server
    monkeypatch.setattr(server, "MAX_RESULT_CHARS", 10 ** 6)          # the notebooks' text in the answer, to read it here
    client, fake, priv = make()
    rv = _review(client, priv)
    r, _ = _build(client, priv, [{"kind": "silver_notebook", "name": "shop_silver"}, {"kind": "gold_views", "name": "shop_gold"},
                                 {"kind": "pipeline", "name": "shop_flow"}], review=rv)
    assert r.status_code == 200, r.text
    card = next(c for c in r.json()["outputs"] if c["output"] == "pipeline")
    answer = card["answer"]
    assert answer["health"]["plan_id"] == rv["plan_id"] and answer["health"]["schema_fingerprint"] == rv["schema_fingerprint"]
    assert answer["health"]["table"] == "krusgraph.health" and answer["health"]["alert"]["in_code"] is False
    steps = " ".join(answer["steps"])
    assert "krusgraph.health" in steps and "Key Vault" in steps and "Schedule failure emails" not in steps
    assert "Monitor hub" in steps and "scheduled runs only" in steps
    notebooks = {n["name"]: n.get("content", "") for n in answer["notebooks"]}
    assert "n200: drift" in notebooks["shop_silver"] and rv["plan_id"] in notebooks["shop_silver"]
    assert rv["plan_id"] in notebooks["shop_flow_check"]
