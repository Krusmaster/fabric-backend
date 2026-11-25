"""Round LFD5 (25 November 2026): the three-layer diff (fabric_backend/change_diff.py) and the read-only tool
propose_change behind KRUSGRAPH_CHANGES, off by default (docs/CHANGES.md, "Proposing a change").

Off, nothing changes: the hosted listing is tests/golden/hosted_listing.json byte for byte and the default listing holds
16 tools. On, propose_change is registered on both servers and listed by default, and the default read-only listing
stays under 23 500 characters. Scenario A on the synthetic shop_lfd sample (SQLite, no network): remove the test
customers (two questions, then ok), add region (a link question and a new plan, or ok), add a measure (order value per
customer), each with the plan and the items layers as expected and the numbers layer "not counted yet" until round
LFD4's module is wired in (a test double here). The hosted tool against the golden tests' fake Fabric sends no write."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fabric_backend import change_diff, changes, lfd_demo, server, tool_listing, tool_status
from fabric_backend.infer import plan as make_plan
from test_golden import fabric  # noqa: F401  (the synthetic shop workspace, Fabric REST and SQL faked)
from test_n123_switches import _LIST

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).parent / "golden"
INFO = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse",
            schema="shop", schemas_enabled=True)
IS_TEST = {"column": "is_test", "op": "is_true"}
CASCADE = ["orders", "order_items", "addresses", "audit_log"]
A2 = {"type": "filter_rows", "table": "customers", "drop_where": IS_TEST, "cascade": CASCADE}
SHIP_TO = {"from": {"table": "orders", "columns": ["ship_to_id"]}, "to": {"table": "addresses", "columns": ["address_id"]}}
A3 = {"type": "add_column", "table": "orders", "from": "addresses", "columns": ["region"]}
A4 = {"type": "add_measure", "name": "Order value per customer",
      "measure": {"form": "ratio", "numerator": {"measure": "Order amount"},
                  "denominator": {"form": "distinct_count", "table": "orders", "column": "customer_id"}}}


# ------------------------------------------------------------------ the flag and the listings ------------------------

_GOLDEN_LISTING = r"""
import asyncio, inspect, json, os
from fabric_backend import server
def listing():
    out = []
    for t in sorted(asyncio.run(server.mcp.list_tools()), key=lambda t: t.name):
        e = json.loads(t.model_dump_json(exclude_none=True))
        if e.get("description"):
            e["description"] = inspect.cleandoc(e["description"])
        out.append(e)
    return out
os.environ.pop("KRUSGRAPH_ADVANCED_TOOLS", None)
default = [t["name"] for t in listing()]
os.environ["KRUSGRAPH_ADVANCED_TOOLS"] = "1"
print(json.dumps({"default": default, "tools": listing(), "instructions": server.mcp.instructions}, indent=1, sort_keys=True,
                 default=str, ensure_ascii=False))
"""


def _env(**extra) -> dict:
    base = {k: v for k, v in os.environ.items() if not k.startswith("KRUSGRAPH_")}
    return base | {"PYTHONPATH": str(ROOT)} | extra


def _run(code: str, *args, **env) -> str:
    return subprocess.run([sys.executable, "-c", code, *args], env=_env(**env), cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout


def _listing(module: str, **env) -> dict:
    return json.loads(_run(_LIST, module, **env))


def test_the_flag_is_off_by_default_and_read_from_the_environment():
    assert tool_listing.CHANGES == "KRUSGRAPH_CHANGES"
    assert not tool_listing.changes_on({}) and not tool_listing.changes_on({"KRUSGRAPH_CHANGES": "0"})
    assert tool_listing.changes_on({"KRUSGRAPH_CHANGES": "1"}) and tool_listing.changes_on({"KRUSGRAPH_CHANGES": "on"})
    assert tool_listing.default_names({}) == tool_listing.DEFAULT and len(tool_listing.DEFAULT) == 16
    assert tool_listing.default_names({"KRUSGRAPH_CHANGES": "1"}) == (*tool_listing.DEFAULT, "propose_change", "apply_change")   # LFD6


def test_flag_off_the_hosted_listing_is_the_golden_file_byte_for_byte():
    text = _run(_GOLDEN_LISTING)
    assert text == (GOLDEN / "hosted_listing.json").read_text(encoding="utf-8")
    assert len(json.loads(text)["default"]) == 16 and "propose_change" not in text


def test_flag_off_no_server_registers_the_tool_and_no_status_names_it():
    if tool_listing.changes_on():
        pytest.skip("KRUSGRAPH_CHANGES is on in this environment")
    assert not hasattr(server, "propose_change") and "propose_change" not in tool_status.STATUS
    assert "propose_change" not in tool_status.LOCAL_TOOLS
    off = _listing("server", KRUSGRAPH_ADVANCED_TOOLS="0")
    assert [t["name"] for t in off["tools"]] == sorted(tool_listing.DEFAULT)
    assert "propose_change" not in [t["name"] for t in _listing("mcp_server")["tools"]]


def test_flag_on_the_tool_is_listed_read_only_and_the_default_read_only_listing_stays_under_23_500():
    on = _listing("server", KRUSGRAPH_CHANGES="1", KRUSGRAPH_ADVANCED_TOOLS="0")
    off = _listing("server", KRUSGRAPH_ADVANCED_TOOLS="0")
    names = [t["name"] for t in on["tools"]]
    assert sorted(names) == sorted((*tool_listing.DEFAULT, "propose_change", "apply_change")) and len(names) == 18   # LFD6
    tool = next(t for t in on["tools"] if t["name"] == "propose_change")
    assert tool["annotations"]["read_only_hint"] is True and tool["annotations"]["destructive_hint"] is False
    assert set(tool["input_schema"]["properties"]) == {"workspace", "source", "change", "schema", "applied", "confirmed"}
    assert tool["input_schema"]["required"] == ["workspace", "source", "change"]
    assert all(p.get("description") for p in tool["input_schema"]["properties"].values())
    # LFD5, 25 November 2026: 21 583 characters off, 23 364 on (propose_change adds about 1 800)
    assert off["ro_size"] <= on["ro_size"] <= 23_500
    local = _listing("mcp_server", KRUSGRAPH_CHANGES="1")
    assert "propose_change" in [t["name"] for t in local["tools"]]
    status = json.loads(_run("import json; from fabric_backend import tool_status as t; "
                             "s = t.STATUS['propose_change']; print(json.dumps([s.kind, s.changes, 'propose_change' in t.LOCAL_TOOLS]))",
                             KRUSGRAPH_CHANGES="1"))
    assert status[0] == tool_status.READS and status[1].startswith("nothing") and status[2] is True


# ------------------------------------------------------------------ scenario A on shop_lfd (SQLite) ------------------

@pytest.fixture(scope="module")
def shop():
    schema, execute = lfd_demo.sqlite("shop_lfd")
    return schema, server._hosted_plan(schema, None, None, execute)       # the plan as plan_backend makes it (R5 ship_to)


def _items(answer: dict) -> dict:
    return {x["item"]: x for x in answer["diff"]["items"]}


def test_a2_remove_test_customers_asks_twice_then_diffs_the_silver_notebook(shop):
    _, p = shop
    q1 = change_diff.propose({"type": "filter_rows", "table": "customers"}, p, INFO)
    assert q1["result"] == "question" and q1["kind"] == "filter_column" and q1["at"] == 0
    assert q1["candidates"][0]["drop_where"] == IS_TEST and "diff" not in q1
    q2 = change_diff.propose({"type": "filter_rows", "table": "customers", "drop_where": IS_TEST}, p, INFO)
    assert q2["result"] == "question" and q2["kind"] == "cascade"
    assert {c["table"] for c in q2["candidates"]} == set(CASCADE)
    ok = change_diff.propose(A2, p, INFO)
    assert ok["result"] == "ok" and ok["id"] == changes.apply([A2], p)["changes"][0]["id"]
    plan = ok["diff"]["plan"]
    assert plan["filters_added"] == [{"id": ok["id"], "table": "customers", "drop_where": "is_test is true",
                                      "cascade": sorted(CASCADE)}]
    assert not plan["links_added"] and not plan["measures_added"] and plan["summary"] == "1 filter added"
    items = _items(ok)
    assert list(items) == list(change_diff.ITEMS)
    silver = items["silver_notebook"]
    assert silver["status"] == change_diff.UPDATE and silver["summary"] == "1 filter step on customers and its 4 dependents"
    assert silver["lines_removed"] == 0 and "+def exclude_rows(df, condition, table, change, reason):" in silver["diff"]
    assert silver["diff"].startswith("--- silver_shop (now)\n+++ silver_shop (after the change)")
    for same in ("check_notebook", "gold_views", "pipeline"):
        assert items[same]["status"] == change_diff.UNCHANGED and "diff" not in items[same]
    model = items["semantic_model"]                                         # the README says where the filter is drafted
    assert model["status"] == change_diff.UPDATE and model["summary"].startswith("README: the filter_rows change is drafted in the silver notebook")
    assert ok["diff"]["numbers"]["status"] == change_diff.NOT_COUNTED == "not counted yet"
    assert ok["confirm"].startswith("upd-") and ok["changes"] == [ok["id"]]


def test_a3_add_region_is_ok_where_the_plan_has_the_ship_to_link(shop):
    _, p = shop
    ok = change_diff.propose(A3, p, INFO, [A2])
    assert ok["result"] == "ok" and ok["change"]["via"] == [SHIP_TO]
    plan = ok["diff"]["plan"]
    assert [c["columns"] for c in plan["columns_added"]] == [["region"]] and not plan["filters_added"] and not plan["filters_removed"]
    items = _items(ok)
    assert items["silver_notebook"]["status"] == items["pipeline"]["status"] == change_diff.UNCHANGED
    assert items["gold_views"]["status"] == change_diff.UPDATE
    assert items["gold_views"]["summary"] == "addresses_region already in gold.orders, marked with the change"


def test_a3_add_region_asks_for_the_link_then_plans_again_with_it(shop):
    schema, _ = shop
    p = make_plan(schema)                                                   # names only: no R5 count, no ship_to link
    q = change_diff.propose(A3, p, INFO, [A2])
    assert q["result"] == "question" and q["kind"] == "link" and q["at"] == 1
    link = q["candidates"][0]["change"]
    assert link == {"type": "add_link", **SHIP_TO}
    replans = []

    def replan(confirmed):
        replans.append(confirmed)
        return make_plan(schema, None, confirmed)
    assert change_diff.propose(link, p, INFO, [A2])["result"] == "replan"          # without a way to plan again
    ok = change_diff.propose(link, p, INFO, [A2], replan=replan)
    entry = {"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}
    assert ok["result"] == "ok" and replans == [[entry]] and ok["confirmed"] == [entry]
    plan = ok["diff"]["plan"]
    assert [(r["source"], r["target"], r["rule"]) for r in plan["links_added"]] == [("orders", "addresses", "confirmed")]
    assert not plan["filters_added"] and not plan["filters_removed"]          # A2, checked again on the new plan, is the same change
    items = _items(ok)
    assert items["gold_views"]["status"] == change_diff.UPDATE and items["pipeline"]["status"] == change_diff.UNCHANGED
    # then the column, on the plan with the link: ok, with one join and one column in gold.orders
    p2 = make_plan(schema, None, ok["confirmed"])
    col = change_diff.propose({**A3, "via": [SHIP_TO]}, p2, INFO, [A2, link], confirmed=ok["confirmed"])
    assert col["result"] == "ok" and _items(col)["gold_views"]["status"] == change_diff.UPDATE
    assert "in gold.orders" in _items(col)["gold_views"]["summary"]


def test_a4_add_measure_changes_the_semantic_model_only(shop):
    _, p = shop
    ok = change_diff.propose(A4, p, INFO, [A2, {**A3, "via": [SHIP_TO]}])
    assert ok["result"] == "ok"
    assert ok["diff"]["plan"]["measures_added"] == [{"id": ok["id"], "name": "Order value per customer", "form": "ratio"}]
    items = _items(ok)
    assert [k for k, v in items.items() if v["status"] == change_diff.UPDATE] == ["semantic_model"]
    model = items["semantic_model"]
    assert model["summary"] == "1 measure: Order value per customer"
    assert "DIVIDE([Order amount], DISTINCTCOUNT('orders'[customer_id]))" in model["diff"] and model["lines_removed"] == 0
    assert ok["diff"]["summary"] == "1 measure added; 1 item updated in place (semantic model)"


def test_the_same_proposal_gives_the_same_answer_and_another_list_another_token(shop):
    _, p = shop
    one, two = change_diff.propose(A4, p, INFO, [A2]), change_diff.propose(A4, p, INFO, [A2])
    assert one == two
    other = change_diff.propose(A4, p, INFO)
    assert other["id"] == one["id"] and other["confirm"] != one["confirm"]


def test_a_revert_shows_the_filter_step_taken_out(shop):
    _, p = shop
    cid = changes.apply([A2], p)["changes"][0]["id"]
    ok = change_diff.propose({"type": "revert", "change": cid}, p, INFO, [A2])
    assert ok["result"] == "ok" and ok["changes"] == []
    assert [f["id"] for f in ok["diff"]["plan"]["filters_removed"]] == [cid]
    silver = _items(ok)["silver_notebook"]
    assert silver["status"] == change_diff.UPDATE and silver["summary"] == "the filter step on customers taken out"
    assert silver["lines_added"] == 0


# ------------------------------------------------------------------ questions and denials pass through ---------------

def test_denials_pass_through_and_nothing_is_drafted(shop, monkeypatch):
    _, p = shop
    monkeypatch.setattr(change_diff, "drafts", lambda *a, **k: pytest.fail("a denial drafts nothing"))
    free = change_diff.propose({"type": "filter_rows", "table": "customers", "drop_where": "is_test = 1", "cascade": []}, p, INFO)
    assert free["result"] == "denied" and free["kind"] == "free_text" and free["at"] == 0
    unknown = change_diff.propose({"type": "drop_table", "table": "customers"}, p, INFO, [A2])
    assert unknown["result"] == "denied" and unknown["kind"] == "unknown_type" and unknown["at"] == 1
    earlier = change_diff.propose(A4, p, INFO, [{"type": "add_column", "table": "nowhere", "from": "addresses", "columns": ["region"]}])
    assert earlier["result"] == "denied" and earlier["at"] == 0                # the list before it is checked first
    assert change_diff.propose("remove test customers", p, INFO)["kind"] == "bad_request"


# ------------------------------------------------------------------ the numbers layer (LFD4's interface) ------------

def test_the_numbers_layer_calls_the_injected_counter_with_both_sides(shop):
    _, p = shop
    seen = {}

    def counter(*, before, after):                                         # a test double for change_numbers.py
        seen["before"], seen["after"] = before, after
        return {"before": {"customers": 12}, "after": {"customers": 10}}
    ok = change_diff.propose(A2, p, INFO, numbers=counter)
    assert ok["diff"]["numbers"] == {"status": "counted", "counted": {"before": {"customers": 12}, "after": {"customers": 10}}}
    assert seen["before"]["plan"] is p and seen["before"]["applied"]["changes"] == []
    assert [x["id"] for x in seen["after"]["applied"]["changes"]] == [ok["id"]]

    def broken(**_):
        raise RuntimeError("no rows")
    failed = change_diff.propose(A2, p, INFO, numbers=broken)["diff"]["numbers"]
    assert failed["status"] == change_diff.NOT_COUNTED and "RuntimeError" in failed["note"]


# ------------------------------------------------------------------ the hosted tool: no HTTP write ------------------

def test_the_hosted_tool_reads_the_plan_and_sends_no_write(fabric):  # noqa: F811
    change = {"type": "add_measure", "name": "Orders counted", "measure": {"form": "count", "table": "orders"}}
    out = json.loads(server._propose_change("demo", "demo_lh", change, schema="shop"))
    assert out["result"] == "ok" and out["writes"].startswith("Nothing was written")
    model = next(x for x in out["diff"]["items"] if x["item"] == "semantic_model")
    assert model["status"] == change_diff.UPDATE and model["summary"] == "1 measure: Orders counted"
    assert fabric.created == []
    writes = [c for c in fabric.calls if c[0] != "GET" and not c[1].endswith(("/getDefinition", "/graphql"))]
    assert writes == [], writes
    denied = json.loads(server._propose_change("demo", "demo_lh", {"type": "filter_rows", "table": "customers", "drop_where": "x"},
                                               schema="shop"))
    assert denied["result"] == "denied" and "writes" not in denied
    assert [c for c in fabric.calls if c[0] in ("PATCH", "PUT", "DELETE")] == []


def test_a_long_answer_drops_the_largest_diffs_first(shop):
    _, p = shop
    ok = change_diff.propose(A2, p, INFO)
    before = json.dumps(ok)
    text = change_diff.answer(ok, 4000)
    assert json.dumps(ok) == before                                         # the answer is not changed in place
    out = json.loads(text)
    silver = next(x for x in out["diff"]["items"] if x["item"] == "silver_notebook")
    assert "diff" not in silver and silver["diff_omitted"] and silver["summary"]
    assert json.loads(change_diff.answer(ok, 10**6))["diff"] == ok["diff"]
