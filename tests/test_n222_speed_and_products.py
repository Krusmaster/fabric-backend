"""Round n222, from the founder's live test of 11 November 2026 ("it must go faster, and I want suggestions on which data
products to create"), with Fabric and the SQL endpoint faked (tests/golden_support.py):

- the dry run lists the workspace's items once per request (19 listings for six outputs before), its outputs are
  prepared side by side with the report after its semantic model, the cards in the engine's order and the same as one
  after another, and the progress words say how many are prepared;
- a write empties the request's listing, and a Create's tool calls never read it;
- Fabric's long-running operations are read after a short first wait (FIRST_POLLS), never longer than Retry-After, then
  at Retry-After's pace; throttling is waited out in full;
- the review and the check answer domain_draft's proposal as suggested data products (tables, the rule, the interface,
  the evidence), deterministic, on the plan the review left; ticked ones come back on the dry run as data products.
The editor's side (Create's steps at once, the Create button, the panel) is tested in workload/ with vitest."""
import importlib
import json
import threading
import time

import pytest

pytest.importorskip("jwt")

import golden_support as gs  # noqa: E402
from test_workload_api import SRC, keys, tok  # noqa: E402,F401
from test_workload_build import ALL, _build, _post, _review, make  # noqa: E402,F401
from test_fabric_operations import Fabric as LroFabric, Resp, SUCCEEDED, create  # noqa: E402
from fabric_backend import operations, workload_api  # noqa: E402

dep = importlib.import_module("fabric_backend.deploy")
SIX = [o for o in ALL if o["kind"] in ("silver_notebook", "gold_views", "pipeline", "semantic_model", "report", "graphql")]


def _listings(fake):
    return [c for c in fake.calls if c[0] == "GET" and c[1].split("?")[0].endswith(f"/workspaces/{gs.WS}/items")]


# ------------------------------------------------------------------ one listing per request ---------------------------

def test_the_dry_run_of_six_outputs_lists_the_workspace_once(make):
    client, fake, priv = make()
    rv = _review(client, priv)
    fake.calls.clear()
    r, _ = _build(client, priv, SIX, review=rv)
    assert r.status_code == 200, r.text
    assert r.json()["refused"] == 0
    assert len(_listings(fake)) == 1                                   # 19 before n222


def test_a_write_empties_the_listing_and_a_tool_call_reads_none(monkeypatch):
    calls = []

    class R:
        status_code = 200
        headers = {}

        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

        def raise_for_status(self):
            pass
    import requests
    monkeypatch.setattr(requests, "get", lambda url, **kw: calls.append(("GET", url)) or R({"value": [{"id": "1", "displayName": "a", "type": "Notebook"}]}))
    monkeypatch.setattr(requests, "post", lambda url, **kw: calls.append(("POST", url)) or R({}))
    with dep.one_listing():
        assert dep.find_item("ws", "a", {}, "Notebook") == "1" and dep.find_item("ws", "a", {}, "Report") is None
        assert dep.find_item_by_name("ws", "a", {}, ("Notebook",))["id"] == "1"
        assert len(calls) == 1                                         # three lookups, one listing
        dep.send("post", "https://x/write", {}, write=True)
        dep.find_item("ws", "a", {}, "Notebook")
        assert [c[0] for c in calls] == ["GET", "POST", "GET"]         # listed again after the write
        dep.outside_listing(lambda: dep.find_item("ws", "a", {}, "Notebook"))
        assert calls[-1][1].endswith("items?type=Notebook")            # a tool call lists on its own, as before n222
    dep.find_item("ws", "a", {}, "Notebook")
    assert calls[-1][1].endswith("items?type=Notebook")                # outside the block nothing changed


# ------------------------------------------------------------------ the dry run side by side ---------------------------

def test_the_dry_run_prepares_outputs_side_by_side_and_the_report_after_its_model(make, monkeypatch):
    client, fake, priv = make()
    rv = _review(client, priv)
    one_by_one, _ = _build(client, priv, SIX, review=rv)
    monkeypatch.setattr(workload_api, "DRY_RUN_THREADS", 1)
    sequential, _ = _build(client, priv, SIX, review=rv)
    monkeypatch.setattr(workload_api, "DRY_RUN_THREADS", 4)
    assert one_by_one.json()["outputs"] == sequential.json()["outputs"]   # the same cards, in the same order

    real = workload_api._call
    lock, now, most, seen = threading.Lock(), [0], [0], {}

    def slow(kind, *a, **kw):
        with lock:
            now[0] += 1
            most[0] = max(most[0], now[0])
            seen[kind] = {"start": time.monotonic()}
        time.sleep(0.15)
        try:
            return real(kind, *a, **kw)
        finally:
            with lock:
                now[0] -= 1
                seen[kind]["end"] = time.monotonic()
    monkeypatch.setattr(workload_api, "_call", slow)
    r, _ = _build(client, priv, SIX, review=rv)
    out = r.json()
    assert out["order"] == ["silver_notebook", "gold_views", "pipeline", "semantic_model", "report", "graphql"]
    assert most[0] >= 3                                                # several outputs at once
    assert seen["report"]["start"] >= seen["semantic_model"]["end"]    # drawn on its model's dry run
    assert out["outputs"] == sequential.json()["outputs"]


def test_the_progress_words_count_the_prepared_outputs(make, monkeypatch):
    client, fake, priv = make()
    rv = _review(client, priv)
    said = []
    monkeypatch.setattr(operations, "progress", lambda status=None, **f: said.append(f.get("words")))
    r, _ = _build(client, priv, SIX, review=rv)
    assert r.status_code == 200
    words = [w for w in said if w]
    assert len(words) == 6 and words[-1].startswith("Dry run: 6 of 6 outputs prepared (")
    assert all(f"Dry run: {n} of 6 outputs prepared" in words[n - 1] for n in range(1, 7))
    assert "Report" in words[-1] and words[-1].index("Semantic model") < words[-1].index("Report")


def test_a_create_still_builds_one_output_after_the_other(make, monkeypatch):
    client, fake, priv = make()
    rv = _review(client, priv)
    order = []
    real = workload_api._call
    monkeypatch.setattr(workload_api, "_call", lambda kind, *a, **kw: order.append(kind) or real(kind, *a, **kw))
    r, _ = _build(client, priv, [o for o in SIX if o["kind"] in ("semantic_model", "report")], review=rv, dry_run=False, created=[])
    assert r.status_code == 200, r.text
    assert order == ["semantic_model", "report"]


# ------------------------------------------------------------------ Fabric's operations: a short first wait ------------

def test_the_first_status_reads_come_soon_then_retry_after_sets_the_pace(monkeypatch):
    running = Resp(200, {"status": "Running"}, {"Retry-After": "4"})
    fake = LroFabric(monkeypatch, posts=[Resp(202, None, {"x-ms-operation-id": "op-1", "Retry-After": "20"})],
                     polls=[running] * 9 + [SUCCEEDED], results=[Resp(200, {"id": "sm-1"})])
    assert create(poll_seconds=3)["status"] == "Succeeded"
    assert dep.FIRST_POLLS == (1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 3.0, 5.0)
    assert fake.sleeps == [1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 3.0, 4, 4, 4]   # never longer than asked; then Retry-After itself


def test_an_operation_done_in_three_seconds_is_seen_after_three_not_twenty(monkeypatch):
    fake = LroFabric(monkeypatch, posts=[Resp(202, None, {"x-ms-operation-id": "op-1", "Retry-After": "20"})],
                     polls=[Resp(200, {"status": "Running"}, {"Retry-After": "20"})] * 2 + [SUCCEEDED], results=[Resp(200, {"id": "sm-1"})])
    assert create(poll_seconds=3)["id"] == "sm-1"
    assert sum(fake.sleeps) == 3.0


def test_throttling_while_polling_is_still_waited_out_in_full(monkeypatch):
    fake = LroFabric(monkeypatch, posts=[Resp(202, None, {"x-ms-operation-id": "op-1"})],
                     polls=[Resp(429, None, {"Retry-After": "30"}), SUCCEEDED], results=[Resp(200, {"id": "sm-1"})])
    assert create(poll_seconds=2)["id"] == "sm-1" and fake.sleeps == [30]


# ------------------------------------------------------------------ suggested data products ----------------------------

def _shop_suggestions(out):
    s = out["suggested_products"]
    return s, {p["id"]: p for p in s["products"]}


def test_the_review_suggests_data_products_with_tables_rule_interface_and_evidence(make):
    client, fake, priv = make()
    out = _post(client, "/review", SRC, tok(priv)).json()
    s, by = _shop_suggestions(out)
    assert by["customers"]["tables"] == ["addresses", "customers", "order_items", "orders"]
    assert by["products"]["tables"] == ["categories", "products"]
    assert all(p["rule"] == workload_api.SUGGEST_RULE for p in s["products"])
    assert by["customers"]["interface"]["consumes"] == [{"product": "products", "id": "products",
                                                         "link": "order_items.product_id → products", "rule": by["customers"]["interface"]["consumes"][0]["rule"]}]
    assert by["products"]["interface"]["provides"][0]["link"] == "order_items.product_id → products"
    assert any(e.startswith("link orders.customer_id → customers (") and "not checked against the rows" in e for e in by["customers"]["evidence"])
    assert any(e.startswith("key products.product_id (") for e in by["products"]["evidence"])
    assert "order_items" in by["customers"]["why"]
    assert [u["table"] for u in s["unassigned"]] == ["audit_log"]
    assert s["checked"] is False and "domain_draft" in s["from"]
    again = _post(client, "/review", SRC, tok(priv)).json()
    assert again["suggested_products"] == s                            # deterministic: no AI, no randomness


def test_the_check_weighs_the_suggestions_by_the_rows(make):
    client, fake, priv = make()
    rv = _review(client, priv)
    out = _post(client, "/check", {**SRC, "review": rv}, tok(priv)).json()
    s, by = _shop_suggestions(out)
    assert s["checked"] is True
    assert any("the rows:" in e for e in by["customers"]["evidence"])


def test_a_rejected_link_in_the_review_changes_the_suggestions(make):
    client, fake, priv = make()
    rv = _review(client, priv)
    link = next(it for it in rv["items"] if it["type"] == "relationship" and it["source"] == "order_items" and it["target"] == "products")
    out = _post(client, "/review", {**SRC, "previous": rv, "decisions": [{"item": link["id"], "review": "rejected", "reason": "test"}]}, tok(priv)).json()
    _, by = _shop_suggestions(out)
    assert not by["customers"]["interface"]["consumes"]               # the rejected link is no interface any more


def test_ticked_suggestions_come_back_on_the_dry_run_as_data_products(make):
    client, fake, priv = make()
    rv = _review(client, priv)
    r, _ = _build(client, priv, SIX, review=rv, products=[{"id": "products", "name": "products"}, {"id": "gone_one", "name": "old"}])
    assert r.status_code == 200, r.text
    got = {p["id"]: p for p in r.json()["products"]}
    assert got["products"]["tables"] == ["categories", "products"]
    assert {i["output"] for i in got["products"]["items"]} == {o["kind"] for o in SIX}
    assert got["products"]["interface"]["provides"][0]["product"] == "customers"
    assert got["gone_one"]["gone"] is True and "no longer suggests" in got["gone_one"]["words"]
    assert _writes(fake) == []


def test_products_must_be_ticked_suggestions(make):
    client, fake, priv = make()
    rv = _review(client, priv)
    for bad in ("products", [{"id": "Bad Id"}], [{"name": "no id"}], [{"id": "x"}] * 31):
        r, _ = _build(client, priv, SIX, review=rv, products=bad)
        assert r.status_code == 400 and "products" in r.json()["error"], bad


def _writes(fake):
    return [c for c in fake.calls if c[0] != "GET" and not c[1].endswith(("/getDefinition", "/graphql"))]
