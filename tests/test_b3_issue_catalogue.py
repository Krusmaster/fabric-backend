"""B3 (15 November 2026, backlog H-02 and the table of H-01): the issue catalogue as data, one recogniser per class.

The signals are produced by the code that emits them, on synthetic data: the health step and the drift step on the shop
and mill lakehouses in SQLite (tests/health_cases.py), run_results.classify on Fabric-shaped error texts, and
product_life.status on listings. Nothing ran against Fabric."""
import pathlib
import re

import pytest

import health_cases as hc
from fabric_backend import health, product_life, run_results
from fabric_backend import issue_catalogue as ic

NS = health.namespace()
DOC = pathlib.Path(__file__).parent.parent / "docs" / "ISSUE-POLICY.md"
CTX = {"run_id": "run-2", "checked_at": hc.NOW, "plan_id": hc.MARK["plan_id"], "schema_fingerprint": hc.MARK["schema_fingerprint"]}


def row(check, obj, rule, status, count=None, baseline=None):
    return NS["health_row"](CTX, check, obj, rule, status, count, baseline)


def classes(d):
    return [(i["class"], i["object"], i["severity"]) for i in d["issues"]]


def test_the_catalogue_is_the_designs_fifteen_classes_in_its_order():
    design = (pathlib.Path(__file__).parent.parent / "docs" / "LIFECYCLE-DESIGN.md").read_text(encoding="utf-8")
    section = design[design.index("## 2. Diagnose"):design.index("## 3. Propose")]
    named = re.findall(r"^\| `([a-z_.]+)` \|", section, flags=re.M)
    assert [c["id"] for c in ic.CLASSES] == named and len(named) == 15
    for c in ic.CLASSES:
        assert c["severity"] in ic.SEVERITIES and c["policy"] in ic.POLICIES and set(c["levels"]) == {0, 1, 2}
        assert set(c["levels"].values()) <= set(ic.ACTIONS) and c["why"] and c["proposed_fix"] and c["recognised_by"]
        assert c["levels"][0] in ("suggest", "inform"), c["id"]                       # level 0 never applies anything


def test_the_policy_follows_from_the_levels_and_matches_the_designs_level_table():
    for c in ic.CLASSES:
        acts = set(c["levels"].values())
        expected = ("never automatic" if acts == {"inform"} else "opt-in rule" if acts & {"auto", "rule"} else "always a person")
        assert c["policy"] == expected, c["id"]
    got = {c["id"].split(".")[-1]: tuple(c["levels"][n] for n in (0, 1, 2)) for c in ic.CLASSES}
    assert got == {
        "failed_run": ("suggest", "auto", "auto"), "capacity_limit": ("suggest", "auto", "auto"),
        "orphan_spike": ("suggest", "auto", "auto"), "added_column": ("suggest", "suggest", "rule"),
        "new_table": ("suggest", "suggest", "suggest"), "retyped_column": ("suggest", "suggest", "rule"),
        "dropped_column": ("suggest", "suggest", "suggest"), "dropped_table": ("suggest", "suggest", "suggest"),
        "duplicate_keys": ("suggest", "suggest", "suggest"), "sums_mismatch": ("suggest", "suggest", "suggest"),
        "permission_lost": ("suggest", "suggest", "suggest"), "item_deleted": ("suggest", "suggest", "suggest"),
        "item_changed_outside": ("suggest", "suggest", "suggest"), "row_drop": ("inform", "inform", "inform"),
        "stale_data": ("inform", "inform", "inform")}
    assert ic.action("failed_run", 0) == "suggest" and ic.action("failed_run", 1) == "auto"
    with pytest.raises(ValueError, match="autonomy level"):
        ic.action("failed_run", 3)


def test_the_five_drift_classes_from_the_drift_steps_own_rows():
    built = {"tables": {"orders": {"columns": {"order_id": "int", "customer_id": "int", "note": "varchar", "total": "int"},
                                   "uses": ["order_id", "customer_id"]},
                        "customers": {"columns": {"customer_id": "int"}, "uses": ["customer_id"]}}}
    live = {"orders": {"order_id": "int", "total": "varchar", "channel": "string"}, "customers": None}
    findings = NS["drift"](built, live, ["orders", "returns"])
    rows = NS["drift_rows"](CTX, "shop", findings)
    d = ic.diagnose(health=rows)
    assert classes(d) == [("schema_drift.dropped_table", "shop.customers", "red"),
                          ("schema_drift.dropped_column", "shop.orders.customer_id", "red"),      # a reference uses it
                          ("schema_drift.dropped_column", "shop.orders.note", "amber"),           # nothing uses it
                          ("schema_drift.retyped_column", "shop.orders.total", "amber"),
                          ("schema_drift.added_column", "shop.orders.channel", "amber"),
                          ("schema_drift.new_table", "shop.returns", "info")]
    assert d["health"] == "red" and d["counts"] == {"red": 2, "amber": 3, "info": 1} and not d["unclassified"]
    assert ic.diagnose(health=NS["drift_rows"](CTX, "shop", []))["issues"] == []                  # no drift: one pass row
    only_new = ic.diagnose(health=[r for r in rows if r["rule"] == "table_added"])
    assert only_new["health"] == "green" and classes(only_new) == [("schema_drift.new_table", "shop.returns", "info")]


def test_the_health_checks_classes_and_what_stays_quiet_or_unclassified():
    rows = [row("key", "silver.orders", "K1", "fail", 4, 0), row("key", "silver.stg_prices", "K2", "warn", 1, 1),
            row("join_sums", "gold.order_items", "sums", "fail", 1, 0), row("join_rows", "gold.order_items", "rows", "fail", 7, 0),
            row("row_count", "silver.orders", "rows", "warn", 20, 60), row("row_count", "silver.items", "rows", "pass", 50, 50),
            row("freshness", "shop.orders", "minutes since last write", "warn", 3000, 180),
            row("freshness", "shop.items", "minutes since last write", "fail", 5000, 180),
            row("quarantine", "silver.orders", "K1", "warn", 3, 3), row("row_count", "silver.gone", "missing", "fail", 0, None)]
    d = ic.diagnose(health=rows)
    assert classes(d) == [("duplicate_keys", "silver.orders", "red"), ("sums_mismatch", "gold.order_items", "red"),
                          ("stale_data", "shop.items", "red"), ("row_drop", "silver.orders", "amber"),
                          ("stale_data", "shop.orders", "amber")]
    assert d["health"] == "red"
    # a guessed key with duplicates, a join that changes the row count and a missing table have no class in the design
    assert [(u["check"], u["object"], u["status"]) for u in d["unclassified"]] == [
        ("key", "silver.stg_prices", "warn"), ("join_rows", "gold.order_items", "fail"), ("row_count", "silver.gone", "fail")]
    assert [(q["object"], q["rule"]) for q in d["quiet"]] == [("silver.orders", "K1")]
    assert ic.diagnose(health=[r for r in rows if r["status"] == "pass"]) == {
        "health": "green", "issues": [], "quiet": [], "unclassified": [], "counts": {"red": 0, "amber": 0, "info": 0}}


@pytest.mark.parametrize("count, baseline, settings, expect", [
    (40, 2, None, "spike"),          # above 3 x 2 and above 10
    (9, 2, None, "quiet"),           # above 3 x 2, but not above the floor of 10
    (12, 4, None, "quiet"),          # above the floor, but not above 3 x 4
    (11, 0, None, "spike"),          # none before, eleven now
    (40, None, None, "quiet"),       # the first run: nothing to compare with
    (12, 4, {"orphan_factor": 2}, "spike"), (40, 2, {"orphan_floor": 100}, "quiet")])
def test_an_orphan_spike_needs_the_factor_and_the_floor(count, baseline, settings, expect):
    d = ic.diagnose(health=[row("quarantine", "silver.order_items", "R1", "warn", count, baseline)], settings=settings)
    if expect == "spike":
        assert classes(d) == [("orphan_spike", "silver.order_items", "amber")] and d["health"] == "amber"
        assert d["issues"][0]["evidence"] == {"check": "quarantine", "rule": "R1", "status": "warn", "count": count, "baseline": baseline}
    else:
        assert d["issues"] == [] and len(d["quiet"]) == 1 and d["health"] == "green"
    # orphans left in silver itself: a spike is the class; fewer than a spike is no class and is shown as it is
    d = ic.diagnose(health=[row("orphans", "silver.order_items.product_id", "R1", "fail", count, baseline)], settings=settings)
    assert (classes(d) == [("orphan_spike", "silver.order_items.product_id", "amber")]) if expect == "spike" else \
        (d["issues"] == [] and len(d["unclassified"]) == 1)


def test_the_real_health_step_on_the_shop_and_the_mill_gives_no_issue_on_a_first_run():
    """The health rows of tests/test_n200_health.py: the shop's and the mill's planted problems are in quarantine, counted,
    and a first run has no baseline, so nothing is a spike; the mill's guessed duplicate key is the one unclassified signal."""
    import importlib
    one_run = importlib.import_module("test_n200_health").one_run
    for lh, unclassified in ((hc.shop(), []), (hc.mill_lakehouse(), [("key", "silver.stg_supplier_prices", "warn")])):
        rows = one_run(lh, write=False)
        d = ic.diagnose(health=rows)
        assert d["issues"] == [] and d["health"] == "green"
        assert [(u["check"], u["object"], u["status"]) for u in d["unclassified"]] == unclassified
        assert len(d["quiet"]) == sum(1 for r in rows if r["check"] == "quarantine" and r["status"] == "warn") > 0
        hc.no_row_values(rows, lh)
    # the same quarantine counts as a second run after a clean first one: every reference rule above the floor is a spike
    again = [dict(r, baseline=0) for r in rows if r["check"] == "quarantine"]
    spikes = ic.diagnose(health=again)
    assert {i["class"] for i in spikes["issues"]} <= {"orphan_spike"}
    assert len(spikes["issues"]) == sum(1 for r in again if str(r["rule"]).startswith("R") and r["count"] > 10)


@pytest.mark.parametrize("message, code, expect, sub", [
    ("ModuleNotFoundError: No module named 'fabric_backend'", None, "failed_run", "import_error"),
    ("[TABLE_OR_VIEW_NOT_FOUND] The table or view `silver`.`orders` cannot be found.", None, "failed_run", "table_not_found"),
    ("Operation on target Silver failed: the activity timed out", None, "failed_run", "timeout"),
    ("Something nobody has seen before", "Unknown", "failed_run", "unknown"),
    ("The capacity is paused. CapacityNotActive", None, "capacity_limit", None),
    ("Request failed: HTTP 430 TooManyRequestsForCapacity", None, "capacity_limit", None),
    ("User does not have permission to read the lakehouse", "Forbidden", "permission_lost", None)])
def test_a_failed_run_is_classified_by_run_results_and_three_classes_come_from_it(message, code, expect, sub):
    instance = {"id": "run-9", "status": "Failed", "failureReason": {"errorCode": code, "message": message}}
    for failure in (run_results.failure(instance), instance["failureReason"]):         # run_results' answer, or Fabric's own
        d = ic.diagnose(runs=[{"item": "shop_pipeline", "failure": failure}])
        (issue,) = d["issues"]
        assert (issue["class"], issue["object"], issue.get("sub_class")) == (expect, "shop_pipeline", sub)
        assert issue["evidence"]["message"] == message and issue["evidence"]["heuristic"] == run_results.HEURISTIC
        assert d["health"] == ("amber" if expect == "capacity_limit" else "red")
    assert ic.diagnose(runs=[{"item": "shop_pipeline", "failure": None}])["issues"] == []


def test_items_gone_or_changed_outside_and_a_refused_read():
    outputs = {"created": [{"id": "i1", "type": "SemanticModel", "name": "shop_model", "workspace": "w", "output": "model",
                            "plan": {"plan_id": "plan-0123456789ab"}},
                           {"id": "i2", "type": "Report", "name": "shop_report", "workspace": "w", "output": "report"},
                           {"id": "i3", "type": "Notebook", "name": "shop_silver", "workspace": "w", "output": "silver"}]}
    listings = {"w": {"i1": {"id": "i1", "type": "SemanticModel", "displayName": "shop_model_renamed", "description": ""},
                      "i3": {"id": "i3", "type": "Notebook", "displayName": "shop_silver", "description": ""}}}
    rows = product_life.status(outputs, listings)
    d = ic.diagnose(items=rows, reads=[{"object": "shop_api", "http_status": 403}, {"object": "shop_model", "http_status": 200},
                                       {"object": "shop_report", "http_status": 500}])
    assert classes(d) == [("item_deleted", "Report shop_report", "red"), ("permission_lost", "shop_api", "red"),
                          ("item_changed_outside", "SemanticModel shop_model", "amber")]
    assert d["issues"][2]["evidence"]["why"] == "Renamed in Fabric to shop_model_renamed."
    assert d["unclassified"] == [{"signal": "read", "object": "shop_report", "http_status": 500}]


def test_every_class_is_reached_and_evidence_holds_counts_never_values():
    reached = set()
    rows = [row("drift", "s.t.c", k, "warn", 1) for k in ("column_added", "column_removed", "type_changed")]
    rows += [row("drift", "s.t", "table_added", "warn", 1), row("drift", "s.t", "table_removed", "fail", 1),
             row("quarantine", "silver.t", "R1", "warn", 99, 1), row("key", "silver.t", "K1", "fail", 2),
             row("join_sums", "gold.v", "sums", "fail", 1), row("row_count", "silver.t", "rows", "warn", 1, 9),
             row("freshness", "s.t", "minutes since last write", "warn", 9999)]
    d = ic.diagnose(health=rows,
                    runs=[{"item": "p", "failure": {"message": m}} for m in ("boom", "CapacityNotActive", "Access denied")],
                    items=[{"state": "missing", "type": "Report", "name": "r", "id": "1"},
                           {"state": "changed_outside", "type": "Notebook", "name": "n", "id": "2", "why": "Renamed."}])
    for i in d["issues"]:
        reached.add(i["class"])
        assert set(i) >= {"class", "object", "severity", "evidence", "proposed_fix", "policy", "levels"}
        if "check" in i["evidence"]:
            assert set(i["evidence"]) == {"check", "rule", "status", "count", "baseline"}
    assert reached == {c["id"] for c in ic.CLASSES}
    assert [i["severity"] for i in d["issues"]] == sorted((i["severity"] for i in d["issues"]), key=ic.SEVERITIES.index, reverse=True)


def test_the_module_calls_nothing_and_the_policy_page_equals_the_catalogue():
    src = pathlib.Path(ic.__file__).read_text(encoding="utf-8")
    assert re.findall(r"^(?:from|import) .+$", src, flags=re.M) == ["from __future__ import annotations", "from . import run_results"]
    for word in ("requests", "http.client", "urlopen", "open(", "spark", "execute("):
        assert word not in src.split('"""', 2)[2], word
    text = DOC.read_text(encoding="utf-8")
    for name, table in (("policy", ic.policy_markdown()), ("catalogue", ic.catalogue_markdown())):
        a, b = f"<!-- {name}:begin -->\n", f"\n<!-- {name}:end -->"
        assert text.count(a) == 1 and text.count(b) == 1
        assert text[text.index(a) + len(a):text.index(b)] == table, f"docs/ISSUE-POLICY.md, {name} table: regenerate it from issue_catalogue.py"
    counts = {p: sum(1 for c in ic.CLASSES if c["policy"] == p) for p in ic.POLICIES}
    assert counts == {"always a person": 8, "opt-in rule": 5, "never automatic": 2}
    assert f"{counts['always a person']} classes always wait for a person" in text
