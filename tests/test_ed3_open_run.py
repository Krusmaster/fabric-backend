"""ED3: Gustav's editor test of 21 November 2026, part 3 (the engine's side), on the Fabric doubles.

- the Data Science starter and the analysis notebooks are created in the item's workspace (like every other output),
  attached to the data product's lakehouse, reading the source through OneLake; the answer says where, in one line;
- Run now: one run on the person's click (Run On Demand Item Job), its state read (queued, running, succeeded,
  failed with Fabric's message once), the output table's row count and first rows after success; no new permission;
- the lakehouse an earlier Create made in this very workspace (shop_lh_krusgraph_test) is reused, also when Fabric
  answers 409 "already in use" because its listing had not caught up.
Synthetic shop data only; nothing reaches Fabric.
"""
from __future__ import annotations

import uuid

import pytest

pytest.importorskip("jwt")

import golden_support as gs  # noqa: E402
from test_workload_api import SRC, keys  # noqa: E402,F401
from test_workload_create import _post, make  # noqa: E402,F401
from test_n221_build_in import SANDVIK, TwoWorkspaces, _in  # noqa: E402
from fabric_backend import workload_api as W  # noqa: E402

CELLS = ["# Krusgraph starter\nprint('cell 1')", "features.write.saveAsTable('orders_features')"]
LH_ID = "12345678-1234-1234-1234-123456789abc"
NB_ID = "22222222-2222-2222-2222-222222222222"
WS = "11111111-1111-1111-1111-111111111111"


# ------------------------------------------------------------------ 9a: where the starter goes -------------------

def test_the_starter_is_created_in_the_items_workspace_attached_to_the_data_products_lakehouse(make):
    lake = {"id": LH_ID, "displayName": "shop_lh_krusgraph_test", "type": "Lakehouse"}
    client, fake, priv = make(TwoWorkspaces([lake]))
    body = {**SRC, "source": gs.LH, "name": "shop_lh_orders_features", "cells": CELLS,
            **_in(create_lakehouse="shop_lh_krusgraph_test")}
    dry = _post(client, "/starter", body, priv).json()
    assert dry["workspace"] == SANDVIK and dry["would"] == "create"
    assert dry["lakehouse"] == "shop_lh_krusgraph_test" and dry["lakehouse_id"] == LH_ID
    assert "reads demo_lh through OneLake" in dry["words"] and "runs it only when you choose Run now" in dry["words"]
    assert not fake.sent
    out = _post(client, "/starter", {**body, "dry_run": False, "confirm": dry["confirm"]}, priv).json()
    assert out["would"] == "created" and out["created"]["workspace"] == SANDVIK and out["created"]["attached"] == LH_ID
    assert fake.sent == [("POST", "demo_Sandvik", "notebooks")]               # the item's workspace, never the source's
    # one sentence of what was made and where: no "run it yourself", nothing said twice
    assert out["words"].count(".") == 1 and "yourself" not in out["words"]


def test_without_a_lakehouse_in_the_items_workspace_nothing_is_created_and_it_says_why(make):
    client, fake, priv = make(TwoWorkspaces([]))
    out = _post(client, "/starter", {**SRC, "source": gs.LH, "name": "orders_features", "cells": CELLS, **_in()}, priv).json()
    assert out["kind"] == "bad_input" and "silver notebook and gold views first" in out["hint"]
    assert not fake.sent


def test_the_starters_lakehouse_rule():
    items = [{"id": "a", "displayName": "other_lh", "type": "Lakehouse"}, {"id": "b", "displayName": "shop_lh_2", "type": "Lakehouse"},
             {"id": "c", "displayName": "shop_lh", "type": "Notebook"}]
    place = {"cross": True}
    assert W.starter_lakehouse({"target": {"lakehouse": "b"}, "source_name": "s"}, place, items, {}) == {"id": "b", "name": "shop_lh_2"}
    # the name ED2 moved the lakehouse to (shop_lh is a notebook here) is the one used
    assert W.starter_lakehouse({"target": {"create_lakehouse": "shop_lh"}, "source_name": "s"}, place, items, {})["id"] == "b"
    assert W.starter_lakehouse({"target": {}, "source_name": "s"}, place, items, {})["id"] == "a"
    assert W.starter_lakehouse({"target": {}, "source_name": "s"}, place, [], {}) is None
    # in the source's own workspace: the source lakehouse, as before
    assert W.starter_lakehouse({"target": {}, "source_name": "s"}, {"cross": False}, [], {"id": "src", "displayName": "s"}) == {"id": "src", "name": "s"}


def test_an_analysis_notebook_is_recorded_as_its_analysis():
    req = W.starter_request({**SRC, "source": gs.LH, "name": "a7_forecast", "cells": CELLS, "output": "analysis_A7"})
    assert req["output"] == "analysis_A7"
    with pytest.raises(W.BadRequest):
        W.starter_request({**SRC, "source": gs.LH, "name": "x", "cells": CELLS, "output": "silver_notebook"})


# ------------------------------------------------------------------ 2: Run now ------------------------------------

class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body or {}, headers or {}

    def json(self):
        return self._body


class FakeJobs:
    """Fabric's Job Scheduler for one notebook: 202 with Location, then NotStarted -> InProgress -> Completed."""

    def __init__(self, states=("NotStarted", "InProgress", "Completed"), start=202, failure=None):
        self.states, self.start, self.failure, self.calls = list(states), start, failure, []

    def __call__(self, method, url, **kw):
        self.calls.append((method, url))
        if method == "post":
            if self.start != 202:
                return Resp(self.start, {"message": "The caller is not authorized"})
            return Resp(202, headers={"Location": f"{url.split('?')[0]}/{'44444444-4444-4444-4444-444444444444'}", "Retry-After": "5"})
        st = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        body = {"status": st, "startTimeUtc": "2026-11-21T13:40:00Z"}
        if st == "Failed":
            body["failureReason"] = {"message": self.failure or "Table or view not found: shop.orders"}
        return Resp(200, body)


def test_run_now_starts_one_run_with_the_documented_job_type(monkeypatch):
    jobs = FakeJobs()
    monkeypatch.setattr(W, "_fabric", lambda: "https://api.fabric.microsoft.com")
    started = W.start_item_run(jobs, WS, NB_ID, "Notebook")
    assert started == {"state": "queued", "run_id": "44444444-4444-4444-4444-444444444444"}
    assert jobs.calls == [("post", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/items/{NB_ID}/jobs/instances?jobType=RunNotebook")]
    W.start_item_run(jobs, WS, NB_ID, "DataPipeline")
    assert jobs.calls[-1][1].endswith("jobType=Pipeline")


def test_run_now_states_queued_running_succeeded_and_failed_said_once(monkeypatch):
    monkeypatch.setattr(W, "_fabric", lambda: "https://api.fabric.microsoft.com")
    jobs = FakeJobs()
    seen = [W.read_item_run(jobs, WS, NB_ID, "r")["state"] for _ in range(3)]
    assert seen == ["queued", "running", "succeeded"]
    bad = W.read_item_run(FakeJobs(states=("Failed",)), WS, NB_ID, "r")
    words = W.run_state_words(bad, "shop_lh_orders_features")
    assert bad["state"] == "failed" and words.count("Table or view not found") == 1
    assert W.read_item_run(FakeJobs(states=("Cancelled",)), WS, NB_ID, "r")["state"] == "failed"


def test_run_now_needs_no_new_permission_and_says_the_way_without_one():
    assert W.run_permission(None, "Notebook") is None                       # unknown: Fabric is asked
    assert W.run_permission({"Item.Execute.All"}, "Notebook") is None
    assert W.run_permission({"DataPipeline.Execute.All"}, "DataPipeline") is None
    no = W.run_permission({"Item.ReadWrite.All"}, "Notebook")
    assert no["kind"] == "needs_permission" and "no new permission" in no["error"] and "Open in Fabric" in no["hint"]


def test_run_now_request_accepts_only_notebooks_and_pipelines():
    ok = W.run_item_request({"workspace": WS, "item_id": NB_ID, "item_type": "Notebook", "name": "shop_lh_orders_features",
                             "preview": {"lakehouse": LH_ID, "table": "orders_features"}})
    assert ok["run_id"] is None and ok["preview"] == {"lakehouse": LH_ID, "table": "orders_features", "schema": "dbo"}
    for bad in ({"item_type": "Report"}, {"item_id": "nb"}, {"preview": {"lakehouse": LH_ID, "table": "x; drop"}}):
        with pytest.raises(W.BadRequest):
            W.run_item_request({"workspace": WS, "item_id": NB_ID, "item_type": "Notebook", "name": "n", **bad})


def test_run_item_after_success_reads_the_preview_once_and_keeps_nothing(monkeypatch):
    from fabric_backend import server as S
    import importlib
    D = importlib.import_module("fabric_backend.deploy")
    jobs = FakeJobs(states=("Completed",))
    monkeypatch.setattr(S, "_headers", lambda _ctx: {"Authorization": "Bearer x"})
    monkeypatch.setattr(D, "send", lambda method, url, headers, **kw: jobs(method, url))
    monkeypatch.setattr(W, "_fabric", lambda: "https://api.fabric.microsoft.com")
    monkeypatch.setattr(W, "token_scopes", lambda: None)
    reads = []
    monkeypatch.setattr(W, "preview_table", lambda ws, lh, schema, table: reads.append((ws, lh, schema, table)) or
                        {"table": table, "columns": ["order_id"], "rows": [{"order_id": 1}], "row_count": 1, "words": f"{table}: 1 rows"})
    req = W.run_item_request({"workspace": WS, "item_id": NB_ID, "item_type": "Notebook", "name": "shop_lh_orders_features",
                              "run_id": "44444444-4444-4444-4444-444444444444", "preview": {"lakehouse": LH_ID, "table": "orders_features"}})
    out = W.run_item(req)
    assert out["state"] == "succeeded" and out["preview"]["row_count"] == 1
    assert reads == [(WS, LH_ID, "dbo", "orders_features")]
    assert out["only_when"] == "Krusgraph runs it only when you choose Run now."
    # a run still going: no preview read
    jobs.states = ["InProgress"]
    assert "preview" not in W.run_item(req) and len(reads) == 1


def test_the_run_route_is_served():
    import inspect
    assert "f\"{PREFIX}/run\"" in inspect.getsource(W.routes)


# ------------------------------------------------------------------ 9c: the same-name lakehouse -------------------

def test_the_lakehouse_an_earlier_create_made_here_is_reused_even_after_409(monkeypatch):
    """shop_lh_krusgraph_test is in the item's workspace (an earlier Create made it); Fabric's first answer is 409
    'already in use' because the item check ran before the listing caught up. It is used, not shop_lh_krusgraph_test_2."""
    lake = {"id": LH_ID, "displayName": "shop_lh_krusgraph_test", "type": "Lakehouse"}
    monkeypatch.setattr(W, "ensure_lakehouse", lambda ws, name, headers, req: {
        "error": f"Requested '{name}' is already in use", "http": 409, "kind": "conflict"})
    got = W.make_lakehouse(SANDVIK, {"name": "shop_lh_krusgraph_test", "action": "make"}, {}, {}, list_items=lambda: [lake])
    assert got["name"] == "shop_lh_krusgraph_test" and got["id"] == LH_ID and got["made"] is False
    assert "already in this workspace" in got["words"]


def test_the_dry_run_plans_to_use_the_same_name_lakehouse_in_the_items_workspace(make):
    lake = {"id": str(uuid.uuid4()), "displayName": "shop_lh_krusgraph_test", "type": "Lakehouse", "description": ""}
    from test_ed2_create_finishes import InUse, _create_all
    from test_n221_build_in import OUTPUTS
    from test_workload_create import _review
    client, fake, priv = make(InUse(sandvik_items=[lake]))
    rv = _review(client, priv)
    tick = _in(create_lakehouse="shop_lh_krusgraph_test")
    dry = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS[:1], "dry_run": True, "created": [], **tick}, priv).json()
    assert dry["lakehouse"]["action"] == "use" and dry["lakehouse"]["name"] == "shop_lh_krusgraph_test"
    _create_all(client, priv, rv, OUTPUTS[:1], tick)
    assert fake.lakehouse_posts == []                                  # never made again, never _2
