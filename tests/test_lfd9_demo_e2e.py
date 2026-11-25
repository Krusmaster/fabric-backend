"""Round LFD9 (25 November 2026): the change-by-chat demo end to end, and `krusgraph demo change`
(docs/demo/CHANGE-BY-CHAT.md, docs/CHANGES.md "The demo end to end (LFD9)").

Scenario A on the synthetic shop_lfd sample and scenario B on sap_lfd, locally: the rows in SQLite, Fabric an in-memory
stand-in (fabric_backend/change_demo.py, the same seams as tests/test_lfd6_apply.py). The data product is built first by
create_pipeline and create_semantic_model (a dry run, then dry_run=false); every change then goes through the functions
behind propose_change and apply_change. Every number of docs/SAMPLE-LFD.md is asserted at the step that shows it. No
socket is opened, and both scenarios together run in under a minute.
"""
from __future__ import annotations

import json
import socket
import time

import pytest

from fabric_backend import change_demo, krusgraph_cli as cli, lfd_demo

MINUTE = 60.0


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the LFD9 demo must not reach the network")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.delenv("KRUSGRAPH_NO_ROW_VALUES", raising=False)      # the demo shows every sum


@pytest.fixture(scope="module")
def runs():
    with pytest.MonkeyPatch.context() as mp:
        def refuse(*a, **k):
            raise AssertionError("the LFD9 demo must not reach the network")
        mp.setattr(socket, "create_connection", refuse)
        mp.setattr(socket.socket, "connect", refuse)
        mp.delenv("KRUSGRAPH_NO_ROW_VALUES", raising=False)
        started = time.perf_counter()
        a = change_demo.run("shop_lfd")
        b = change_demo.run("sap_lfd")
        seconds = time.perf_counter() - started
    return {"A": a, "B": b, "seconds": seconds}


def _step(result: dict, label: str) -> dict:
    return next(s for s in result["steps"] if s["step"] == label)


def _numbers(answer: dict, change_id: str | None = None) -> dict:
    """{item: number} of the numbers layer for one change of the list (default: the answer's own)."""
    cid = change_id or answer["id"]
    counted = answer["diff"]["numbers"]["counted"]
    return {n["item"]: n for c in counted["changes"] if c["id"] == cid for n in c["numbers"]}


def _pair(n: dict) -> tuple:
    return n["before"], n["after"]


def _card_rows(step: dict) -> dict:
    return {r["label"]: r for r in step["card"]["numbers"]["rows"]}


def _no_write_while_proposing(result: dict) -> None:
    for s in result["steps"]:
        if s["kind"] == "propose":
            assert s["writes"] == [], f"{s['step']}: propose_change wrote to Fabric"


# ------------------------------------------------------------------ runtime, network, deletes --------------------------

def test_both_scenarios_run_in_under_a_minute_with_no_delete(runs):
    assert runs["seconds"] < MINUTE, f"the LFD9 demo took {runs['seconds']:.1f} s"
    for r in (runs["A"], runs["B"]):
        assert r["deletes_or_puts"] == [] and r["seconds"] < MINUTE


def test_the_demo_puts_the_server_back_as_it_was(runs):
    import requests

    from fabric_backend import change_apply, server, usage
    assert server.R5_MAX_QUERIES == 20 and server.REFRESH_PAUSE > 0
    for verb in ("get", "post", "patch", "delete", "put"):
        assert not isinstance(getattr(getattr(requests, verb), "__self__", None), change_demo.FakeFabric), verb
    assert server._execute_factory.__module__ == "fabric_backend.server"
    assert server._workspace_id.__module__ == "fabric_backend.server"
    assert change_apply.pause is time.sleep and usage._log_on.__module__ == "fabric_backend.usage"


# ------------------------------------------------------------------ scenario A: the first build ---------------------

def test_a_first_build_is_a_dry_run_then_the_items(runs):
    build = _step(runs["A"], "build")
    for name, dry in build["dry_run"].items():
        assert isinstance(dry, dict) and dry.get("dry_run", True) is not False, name
    assert {k: (v.get("result") or {}).get("status") for k, v in build["created"].items()} == \
        {"pipeline_shop": "Succeeded", "shop_model": "Succeeded"}
    assert build["items"] == ["gold_shop", "pipeline_shop", "pipeline_shop_check", "shop_model", "silver_shop"]


# ------------------------------------------------------------------ A2: remove the test customers ---------------------

def test_a2_asks_for_the_column_and_the_cascade_then_counts_the_sample_numbers(runs):
    a = runs["A"]
    q1, q2 = _step(a, "A2a")["answer"], _step(a, "A2b")["answer"]
    assert q1["result"] == "question" and q1["kind"] == "filter_column"
    assert q1["candidates"][0]["drop_where"] == change_demo.IS_TEST
    assert q2["result"] == "question" and q2["kind"] == "cascade"
    assert sorted(c["table"] for c in q2["candidates"]) == sorted(change_demo.CASCADE)
    assert [c["label"] for c in _step(a, "A2b")["card"]["choices"]] == ["Yes, from all 4", "No, keep their rows"]
    step = _step(a, "A2c")
    ok = step["answer"]
    assert ok["result"] == "ok" and ok["pipeline_run"]["needed"] is True and ok["writes"].startswith("Nothing was written")
    n = _numbers(ok)
    # docs/SAMPLE-LFD.md: 12 -> 10 customers, 19 -> 17 addresses, 66 -> 60 orders, 146 -> 134 lines, 56 834.70 -> 51 296.70
    assert _pair(n["rows:customers"]) == (12, 10) and _pair(n["rows:addresses"]) == (19, 17)
    assert _pair(n["rows:orders"]) == (66, 60) and _pair(n["rows:order_items"]) == (146, 134)
    assert _pair(n["sum:Order amount"]) == ("56834.70", "51296.70") and n["sum:Order amount"]["difference"] == "-5538.00"
    want = lfd_demo.EXPECTED["shop_lfd"]["numbers"]                       # LFD1's counts, the table in SAMPLE-LFD.md
    assert [_pair(n[k]) for k in ("rows:customers", "rows:addresses", "rows:orders", "rows:order_items", "sum:Order amount")] == \
        [(want[k], want["real_" + k]) for k in ("customers", "addresses", "orders", "order_lines", "order_value")]
    rows = _card_rows(step)
    assert (rows["Order amount"]["before"], rows["Order amount"]["after"], rows["Order amount"]["difference"]) == \
        ("56 834.70", "51 296.70", "−5 538.00")
    assert step["card"]["sentence"] == "Removes rows from customers where is_test is true, and their rows in 4 tables."
    _no_write_while_proposing(a)
    _no_write_while_proposing(runs["B"])


def test_a2_applied_writes_the_silver_notebook_runs_once_and_the_silver_tables_hold_the_numbers(runs):
    step = _step(runs["A"], "A2 applied")
    dry, out = step["dry_run"], step["answer"]
    assert dry["dry_run"] is True and dry["written"] == [] and dry["writes"].startswith("Nothing was written: a dry run")
    assert out["result"] == "ok" and out["written"] == ["silver_shop"]
    assert [(s["action"], s["name"], s["status"]) for s in out["steps"]] == [
        ("update definition", "silver_shop", "written"), ("run once", "pipeline_shop", "Succeeded"),
        ("refresh once", "shop_model", "refreshed")]
    assert out["verify"]["definition"]["state"] == "verified" and out["verify"]["numbers_after_run"]["state"] == "verified"
    assert {k: step["silver"][k] for k in ("customers", "addresses", "orders", "order_items")} == \
        {"customers": 10, "addresses": 17, "orders": 60, "order_items": 134}
    assert step["silver_amount"] == "51296.70"


# ------------------------------------------------------------------ A3: region, over a link the person confirms ----

def test_a3_asks_for_the_link_then_applies_it_then_the_column(runs):
    a = runs["A"]
    q = _step(a, "A3a")["answer"]
    assert q["result"] == "question" and q["kind"] == "link"
    assert q["candidates"][0]["change"] == {"type": "add_link", **change_demo.SHIP_TO}
    link = _step(a, "A3b")["answer"]
    entry = {"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}
    assert link["result"] == "ok" and link["confirmed"] == [entry]
    assert [(r["source"], r["target"], r["rule"]) for r in link["diff"]["plan"]["links_added"]] == [("orders", "addresses", "confirmed")]
    assert _step(a, "A3b")["card"]["plan"] == ["Link added: orders.ship_to_id → addresses"]
    applied = _step(a, "A3b applied")["answer"]
    assert applied["result"] == "ok" and set(applied["written"]) <= {"silver_shop", "pipeline_shop_check", "gold_shop", "shop_model"}
    assert "gold_shop" in applied["written"] and applied["verify"]["definition"]["state"] == "verified"
    col = _step(a, "A3c")["answer"]
    assert col["result"] == "ok" and col["change"]["via"] == [change_demo.SHIP_TO]
    n = _numbers(col)
    # docs/SAMPLE-LFD.md: 60 of 60 orders find their address; two regions; the order value unchanged by the join
    assert _pair(n["view_rows:orders"]) == (60, 60) and n["missing:addresses.region"]["after"] == 0
    assert n["distinct_values:addresses.region"]["after"] == 2
    doubling = next(c for c in col["diff"]["numbers"]["counted"]["changes"] if c["id"] == col["id"])
    assert doubling["doubled"] is False
    assert [_pair(x) for x in doubling["doubling"] if x.get("name") == "Order amount"] == [("51296.70", "51296.70")]
    out = _step(a, "A3 applied")["answer"]
    assert out["result"] == "ok" and out["written"] == ["gold_shop"] and out["pipeline_run"]["needed"] is True
    assert out["verify"]["definition"]["state"] == "verified"


# ------------------------------------------------------------------ A4: the measure, no run ---------------------------

def test_a4_the_measure_is_5_129_67_and_applies_with_no_pipeline_run(runs):
    a = runs["A"]
    ok = _step(a, "A4")["answer"]
    n = _numbers(ok)["measure:Order value per customer"]
    assert n["value"] == "5129.67" and n["on_source"] == "4736.23"                       # SAMPLE-LFD: 5 129.67, 4 736.23
    want = lfd_demo.EXPECTED["shop_lfd"]["numbers"]
    assert (n["value"], n["on_source"]) == (want["real_order_value_per_customer"], want["order_value_per_customer"])
    assert [x["item"] for x in ok["diff"]["items"] if x["status"] == "update in place"] == ["semantic_model"]
    assert ok["pipeline_run"]["needed"] is False
    step = _step(a, "A4 applied")
    out = step["answer"]
    assert out["written"] == ["shop_model"] and [s["action"] for s in out["steps"]] == ["update definition", "refresh once"]
    before = _step(a, "A3 applied")
    assert step["runs"] == before["runs"] and step["refreshes"] == before["refreshes"] + 1        # no run, one refresh
    assert out["verify"]["numbers_after_run"]["state"] == "not checked"
    assert _card_rows(_step(a, "A4"))["Order value per customer"]["after"] == "5 129.67"


# ------------------------------------------------------------------ A6: undo the filter -------------------------------

def test_a6_the_revert_takes_the_filter_out_and_the_numbers_go_back(runs):
    a = runs["A"]
    ok = _step(a, "A6")["answer"]
    assert ok["result"] == "ok" and ok["diff"]["numbers"]["reverts"]["type"] == "filter_rows"
    assert [f["table"] for f in ok["diff"]["plan"]["filters_removed"]] == ["customers"]
    n = _numbers(ok, ok["diff"]["numbers"]["reverts"]["id"])                # the undone change, read back
    assert _pair(n["rows:customers"]) == (12, 10) and _pair(n["sum:Order amount"]) == ("56834.70", "51296.70")
    step = _step(a, "A6 applied")
    out = step["answer"]
    assert out["result"] == "ok" and out["written"] == ["silver_shop"]
    assert [s["action"] for s in out["steps"]] == ["update definition", "run once", "refresh once"]
    assert out["verify"]["definition"]["state"] == "verified" and out["verify"]["numbers_after_run"]["state"] == "verified"
    # back to the source's numbers: 12 customers, 19 addresses, 66 orders, 146 lines, 56 834.70
    assert {k: step["silver"][k] for k in ("customers", "addresses", "orders", "order_items")} == \
        {"customers": 12, "addresses": 19, "orders": 66, "order_items": 146}
    assert step["silver_amount"] == "56834.70"
    assert [c["type"] for c in out["applied_next"]] == ["add_link", "add_column", "add_measure"]


def test_a_the_items_in_fabric_at_the_end(runs):
    a = runs["A"]
    assert a["runs"] == 4 and a["refreshes"] == 5                               # A2, A3b, A3, A6 run; A4 refreshes only
    assert set(a["items"]) == {"silver_shop", "gold_shop", "pipeline_shop_check", "pipeline_shop", "shop_model"}


# ------------------------------------------------------------------ LFD9b: the report shows the chat's numbers ----------

def _partitions(fake_item: dict) -> set[tuple[str, str]]:
    """(schemaName, entityName) of every Direct Lake partition of a model's TMDL parts."""
    import re
    out = set()
    for path, text in fake_item["parts"].items():
        if path.startswith("definition/tables/"):
            for m in re.finditer(r"entityName: (\S+)\n\t+schemaName: (\S+)", text):
                out.add((m.group(2), m.group(1)))
    return out


def test_lfd9b_the_model_is_built_on_the_pipelines_silver_tables(runs):
    build = _step(runs["A"], "build")
    reads = build["dry_run"]["shop_model"]["summary"]["reads"]
    assert reads["layer"] == "silver" and reads["schema"] == "silver" and "pipeline_shop" in reads["schema_from"]
    assert "combined_key_columns" not in build["dry_run"]["shop_model"]["summary"]
    for label in ("A2 applied", "A3 applied", "A4 applied", "A6 applied"):
        assert _step(runs["A"], label)["model"]["reads"] == ["silver"], label
    assert _step(runs["B"], "B1 applied")["model"]["reads"] == ["silver"]


def test_lfd9b_the_report_shows_10_customers_and_5_129_67_after_a2_and_a4_and_the_source_after_the_undo(runs):
    a = runs["A"]
    after_a2 = _step(a, "A2 applied")["model"]["measures"]
    assert after_a2["Rows in orders"] == 60 and after_a2["Order amount"] == "51296.70"     # the 10 customers' orders
    after_a4 = _step(a, "A4 applied")["model"]["measures"]
    want = lfd_demo.EXPECTED["shop_lfd"]["numbers"]
    assert after_a4["Order value per customer"] == "5129.67" == want["real_order_value_per_customer"]
    assert after_a4["Order value per customer"] == _numbers(_step(a, "A4")["answer"])["measure:Order value per customer"]["value"]
    after_a6 = _step(a, "A6 applied")["model"]["measures"]
    assert (after_a6["Rows in orders"], after_a6["Order amount"], after_a6["Order value per customer"]) == \
        (66, "56834.70", "4736.23")
    assert after_a6["Order value per customer"] == want["order_value_per_customer"]
    assert _step(runs["B"], "B1 applied")["model"]["measures"]["Rows in sap_vbrp"] == 2


def test_lfd9b_the_model_in_the_store_reads_silver_and_a_filter_leaves_its_definition_alone():
    with change_demo.offline("shop_lfd") as fake:
        sc = change_demo._Scenario("shop_lfd", fake)
        change_demo.scenario_a(sc)
        model = fake.by_name("shop_model")
        parts = _partitions(model)
        assert parts and {s for s, _ in parts} == {"silver"}
        assert {t for _, t in parts} >= {"customers", "orders", "order_items", "products"}
    for label in ("A2 applied", "A6 applied"):                     # a filter reaches the model through the run, not its definition
        assert "shop_model" not in _step({"steps": sc.steps}, label)["answer"]["written"]


def test_lfd9b_without_a_pipeline_the_model_reads_the_source_tables_as_before():
    from fabric_backend import server
    src = change_demo.SOURCES["shop_lfd"]
    with change_demo.offline("shop_lfd") as fake:
        dry = json.loads(server.create_semantic_model(name="shop_model", dry_run=True, **src))
        assert "reads" not in dry["summary"] and "layers_to" not in dry
        json.loads(server.create_semantic_model(name="shop_model", dry_run=False, **src))
        assert {s for s, _ in _partitions(fake.by_name("shop_model"))} == {src["schema"]}


def test_lfd9b_a_model_built_before_its_pipeline_is_compared_and_written_on_the_source_tables():
    """The diff drafts the model on silver (the source has a pipeline now); the model in Fabric reads the source, as it
    was built before the pipeline. apply_change compares "now" on the model's own layer: no items_differ, and the
    measure is written on the source tables, where the model reads."""
    from fabric_backend import server
    src = change_demo.SOURCES["shop_lfd"]
    with change_demo.offline("shop_lfd") as fake:
        json.loads(server.create_semantic_model(name="shop_model", dry_run=False, **src))
        json.loads(server.create_pipeline(name="pipeline_shop", dry_run=False, **src))
        sc = change_demo._Scenario("shop_lfd", fake)
        ok = sc.propose("A4", change_demo.SAID["A4"], change_demo.A4)
        assert ok["result"] == "ok"
        out = sc.apply("A4 applied", change_demo.A4, ok)
        assert out["result"] == "ok" and out["written"] == ["shop_model"], out.get("reason")
        assert {s for s, _ in _partitions(fake.by_name("shop_model"))} == {src["schema"]}
        assert out["verify"]["definition"]["state"] == "verified"


# ------------------------------------------------------------------ scenario B on sap_lfd ------------------------------

def test_b_cancelled_billing_documents_go_and_the_orders_stay(runs):
    b = runs["B"]
    assert _step(b, "build")["items"] == ["gold_sap", "pipeline_sap", "pipeline_sap_check", "sap_model", "silver_sap"]
    ok = _step(b, "B1")["answer"]
    assert ok["result"] == "ok"
    n = _numbers(ok)
    # docs/SAMPLE-LFD.md: 3 -> 1 billing documents, 4 -> 2 items, 600.00 -> 400.00; the orders 4 and 950.00 untouched
    assert _pair(n["rows:sap_vbrk"]) == (3, 1) and _pair(n["rows:sap_vbrp"]) == (4, 2)
    assert _pair(n["sum:sap_vbrk.NETWR"]) == ("600.00", "400.00")
    assert _pair(n["rows:sap_vbak"]) == (4, 4) and n["rows:sap_vbak"]["untouched"]
    assert _pair(n["sum:sap_vbak.NETWR"]) == ("950.00", "950.00") and n["sum:sap_vbak.NETWR"]["untouched"]
    want = lfd_demo.EXPECTED["sap_lfd"]["numbers"]                        # LFD1's counts, the table in SAMPLE-LFD.md
    assert _pair(n["rows:sap_vbrk"]) == (want["billing_documents"], want["billing_documents_counted"])
    assert _pair(n["sum:sap_vbrk.NETWR"]) == (want["billed"], want["billed_without_cancellations"])
    assert (n["rows:sap_vbak"]["before"], n["sum:sap_vbak.NETWR"]["before"]) == (want["orders"], want["order_value_per_header"])
    step = _step(b, "B1 applied")
    out = step["answer"]
    assert out["result"] == "ok" and out["written"] == ["silver_sap"]
    assert out["verify"]["definition"]["state"] == "verified" and out["verify"]["numbers_after_run"]["state"] == "verified"
    assert step["silver"]["sap_vbrk"] == 1 and step["silver"]["sap_vbrp"] == 2 and step["silver"]["sap_vbak"] == 4
    assert step["silver_amount"] == "400.00"


# ------------------------------------------------------------------ the CLI ------------------------------------------

def test_krusgraph_demo_change_prints_the_chat(capsys):
    started = time.perf_counter()
    code = cli.main(["demo", "change", "--human"])
    out, _err = capsys.readouterr()
    assert code == 0 and time.perf_counter() - started < MINUTE
    for line in ("krusgraph demo change: scenario A on shop_lfd (synthetic), against an in-memory Fabric. Nothing leaves this machine.",
                 "[A2a] You: Remove the test customers.",
                 "  Krusgraph: Removes rows from customers where is_test is true, and their rows in 4 tables.",
                 "    customers rows: 12 → 10 (-2)",
                 "    orders rows: 66 → 60 (-6)",
                 "    order_items rows: 146 → 134 (-12)",
                 "    Order amount: 56 834.70 → 51 296.70 (−5 538.00)",
                 "  Krusgraph: Which column links orders to addresses?",
                 "  Plan:    Link added: orders.ship_to_id → addresses",
                 "    Order value per customer: 4 736.23 → 5 129.67 (+393.44)",
                 "  Krusgraph: Takes out the filter on customers.",
                 "    silver customers: 12 rows (expected 12)",
                 "  report (the model reads silver): Rows in orders 60, Order amount 51 296.70, Order value per customer 5 129.67",
                 "  report (the model reads silver): Rows in orders 66, Order amount 56 834.70, Order value per customer 4 736.23",
                 "  Written, in this order: silver_shop. Nothing was deleted; only items Krusgraph made were written."):
        assert line in out.splitlines(), line
    assert "definition: verified; numbers after the run: verified" in out
    assert "0 delete(s)" in out


def test_krusgraph_demo_change_sap_and_json(capsys):
    code = cli.main(["demo", "change", "--sap", "--human"])
    out, _ = capsys.readouterr()
    assert code == 0
    for line in ("[B1] You: Leave out cancelled billing documents and their cancellations.",
                 "    sap_vbrk rows: 3 → 1 (-2)", "    sap_vbrp rows: 4 → 2 (-2)",
                 "    sap_vbrk.NETWR: 600.00 → 400.00 (−200.00)", "    sap_vbak.NETWR: 950.00", "    sap_vbak rows: 4"):
        assert line in out.splitlines(), line
    code = cli.main(["demo", "change", "--json"])
    payload = json.loads(capsys.readouterr()[0])
    r = payload["result"]
    assert code == 0 and payload["ok"] is True and r["scenario"] == "A" and r["deletes_or_puts"] == 0
    assert [s["step"] for s in r["steps"]] == ["build", "A2a", "A2b", "A2c", "A2 applied", "A3a", "A3b", "A3b applied", "A3c",
                                               "A3 applied", "A4", "A4 applied", "A6", "A6 applied"]
    assert next(s for s in r["steps"] if s["step"] == "A6 applied")["silver_rows"]["customers"] == 12
    assert next(s for s in r["steps"] if s["step"] == "A4 applied")["model"]["measures"]["Order value per customer"] == "5129.67"
    code = cli.main(["demo", "change", "--apply", "--json"])
    assert code == cli.REFUSED
    capsys.readouterr()


# ------------------------------------------------------------------ the two fixes this round needed ------------------

def test_numbers_after_run_compares_a_revert_with_the_rows_it_brings_back_and_skips_untouched_tables():
    from fabric_backend import change_apply
    counted = {"changes": [{"id": "chg-a", "type": "filter_rows", "numbers": [
        {"what": "rows", "table": "customers", "before": 12, "after": 10},
        {"what": "rows", "table": "regions", "before": 7, "after": 7, "untouched": True}]}]}
    counts = {"customers": 12, "regions": 6}                                   # silver dropped an orphan of regions

    def execute(sql):
        return [{"n": next(v for k, v in counts.items() if f"[{k}]" in sql)}]
    targets = {"customers": ["silver", "customers"], "regions": ["silver", "regions"]}
    back = change_apply.numbers_after_run(counted, targets, execute, reverts={"id": "chg-a", "type": "filter_rows"})
    assert back["state"] == "verified" and [(r["table"], r["expected"], r["counted"]) for r in back["rows"]] == [("customers", 12, 12)]
    counts["customers"] = 10
    assert change_apply.numbers_after_run(counted, targets, execute)["state"] == "verified"           # not a revert: after
    later = {"changes": counted["changes"] + [{"id": "chg-b", "type": "filter_rows", "numbers": [
        {"what": "rows", "table": "customers", "before": 10, "after": 9}]}]}
    unsure = change_apply.numbers_after_run(later, targets, execute, reverts={"id": "chg-a"})
    assert unsure["state"] == "not checked" and "reverted change in place" in unsure["rows"][0]["said"]
