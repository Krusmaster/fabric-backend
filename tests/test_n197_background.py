"""Round n197: Create runs in the background (fabric_backend/operations.py, workload_api.run_build_step).

The founder's live Create of 10 November 2026 built 7 of 9: the semantic model hit Fabric's long-running-operation wait,
the report got "No answer from the Krusgraph engine after 230 s", on a phone five steps failed with "Failed to fetch",
and an item Fabric finished after the wait (demo_lh_model4) was refused as "not built by this Krusgraph Model". Checked
here, with the Fabric doubles of tests/test_workload_create.py:

- the operation store: start, progress, the answer kept in chunks, owner only, lost when the heartbeat stops, an item's
  latest Create listed (a reopened editor resumes it);
- every route answers 202 at once with `Prefer: respond-async` (no request held open: measured), and POST /operation
  gives the state and, once done, the route's own answer and HTTP status;
- a slow long-running operation is pending (never failed) and the item is adopted when Fabric finishes it;
- throttling (HTTP 429, PFE_FABRIC_THROTTLED) is "waiting for capacity" and the step is sent again;
- an item recorded as pending in outputs.json is adopted, not refused;
- the dry run predicts Create: built from the same plan is "already built, skipped".
"""
import json
import threading
import time

import pytest

pytest.importorskip("jwt")

import golden_support as gs  # noqa: E402
from test_workload_api import SRC, tok  # noqa: E402
from test_workload_build import NEW_SM  # noqa: E402
from test_workload_create import Workspace, _post, _review, make  # noqa: E402,F401
from test_workload_api import keys  # noqa: E402,F401
from fabric_backend import errors, operations, registration_store, workload_api  # noqa: E402

ASYNC = {"Prefer": "respond-async"}


@pytest.fixture(autouse=True)
def fresh_store(monkeypatch):
    operations.use_store(registration_store.MemoryStore())
    monkeypatch.setattr(workload_api, "CAPACITY_WAITS", (0, 0, 0))
    monkeypatch.setattr(workload_api, "PENDING_POLL", 0)
    yield
    operations.use_store(None)


def _async(client, path, body, priv, **claims):
    return client.post(workload_api.PREFIX + path, json=body,
                       headers={"Authorization": f"Bearer {tok(priv, **claims)}", "Origin": "https://app.fabric.microsoft.com", **ASYNC})


def _wait(client, priv, op_id, seconds=20, **claims):
    until = time.monotonic() + seconds
    seen = []
    while time.monotonic() < until:
        r = _async(client, "/operation", {"operation_id": op_id}, priv, **claims)
        assert r.status_code == 200, r.text
        s = r.json()
        seen.append(s["status"])
        if s["status"] in ("done", "lost"):
            return s, seen
        time.sleep(0.02)
    raise AssertionError(f"not done: {seen[-5:]}")


# ------------------------------------------------------------------ the operation store ------------------------------

def test_an_operation_runs_in_a_thread_keeps_its_answer_and_is_its_owners_only():
    gate = threading.Event()

    def work():
        operations.progress("waiting_capacity", words="waiting")
        gate.wait(5)
        return {"outputs": [{"output": "report", "name": "x" * 70000}]}, 200     # larger than one Table property
    op = operations.start("build", "owner-a", work, item="11111111-2222-3333-4444-555555555555", output="report", create="c1")
    assert op["status"] == "running" and len(op["operation_id"]) == 32
    for _ in range(100):
        s = operations.state(op["id"], "owner-a")
        if s["status"] == "waiting_capacity":
            break
        time.sleep(0.01)
    assert s["progress"]["words"] == "waiting"
    assert operations.state(op["id"], "owner-b") is None                         # someone else's sign-in finds nothing
    gate.set()
    for _ in range(200):
        s = operations.state(op["id"], "owner-a")
        if s["status"] == "done":
            break
        time.sleep(0.01)
    assert s["http"] == 200 and s["answer"]["outputs"][0]["name"] == "x" * 70000
    listed = operations.of_item("11111111-2222-3333-4444-555555555555", "owner-a")
    assert listed["create"] == "c1" and [o["id"] for o in listed["operations"]] == [op["id"]]
    assert listed["operations"][0]["answer"]["outputs"][0]["output"] == "report"   # resume: the cards come back
    assert operations.of_item("11111111-2222-3333-4444-555555555555", "owner-b")["operations"] == []


def test_a_new_create_of_the_item_starts_a_new_list_and_a_silent_operation_is_lost(monkeypatch):
    item = "11111111-2222-3333-4444-555555555555"
    a = operations.start("build", "o", lambda: ({}, 200), item=item, output="report", create="first")
    b = operations.start("build", "o", lambda: ({}, 200), item=item, output="report", create="second")
    assert [x["id"] for x in operations.of_item(item, "o")["operations"]] == [b["id"]]
    assert a["id"] != b["id"]
    # an operation another replica ran, whose heartbeat stopped: lost, with the reason
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - operations.LOST_AFTER - 5))
    operations.store().put(operations.KIND, "f" * 32, {"id": "f" * 32, "owner": "o", "route": "build", "status": "running",
                                                       "started": old, "updated": old})
    s = operations.state("f" * 32, "o")
    assert s["status"] == "lost" and "no sign of it" in s["lost"]


def test_the_table_store_takes_operation_records():
    assert "op" in registration_store.KINDS
    registration_store._check("op", "item-" + "a" * 40)
    registration_store._check("op", "a" * 32 + "-r3")


# ------------------------------------------------------------------ the routes answer at once ------------------------

def test_no_request_is_held_open_while_the_work_runs(make, monkeypatch):
    """Any route with Prefer: respond-async answers 202 within a second while its work takes longer (the founder's 230 s
    'no answer' and the phone's 'Failed to fetch' came from requests held open). Measured, with the work blocked."""
    gate = threading.Event()
    real = workload_api.run_build_many

    def slow(req):
        gate.wait(10)
        return real(req)
    monkeypatch.setattr(workload_api, "run_build_many", slow)
    client, fake, priv = make()
    rv = _review(client, priv)
    started = time.monotonic()
    r = _async(client, "/build", {**SRC, "review": rv, "outputs": [{"kind": "silver_notebook", "name": "demo_lh_silver"}],
                                  "only": ["silver_notebook"], "dry_run": False, "skip_built": True,
                                  "item_id": "11111111-2222-3333-4444-555555555555", "create_id": "c1"}, priv)
    assert r.status_code == 202 and time.monotonic() - started < 2, r.text
    assert r.headers["preference-applied"] == "respond-async"
    op = r.json()["operation_id"]
    started = time.monotonic()
    s = _async(client, "/operation", {"operation_id": op}, priv).json()
    assert s["status"] == "running" and time.monotonic() - started < 2                 # the poll does not wait either
    gate.set()
    s, _ = _wait(client, priv, op)
    assert s["http"] == 200 and s["answer"]["outputs"][0]["created"], s
    item = _async(client, "/operation", {"item_id": "11111111-2222-3333-4444-555555555555"}, priv).json()
    assert item["create"] == "c1" and item["operations"][0]["output"] == "silver_notebook"
    other = _async(client, "/operation", {"operation_id": op}, priv, oid="user-2")
    assert other.status_code == 404                                                    # another user's poll finds nothing


def test_every_route_can_answer_in_the_background_and_cors_allows_prefer(make):
    client, _, priv = make()
    r = _async(client, "/review", SRC, priv)
    assert r.status_code == 202
    s, _ = _wait(client, priv, r.json()["operation_id"])
    assert s["http"] == 200 and s["answer"]["review"]["format"] == "krusgraph-review"
    pre = client.options(workload_api.PREFIX + "/operation", headers={"Origin": "https://app.fabric.microsoft.com",
                                                                       "Access-Control-Request-Method": "POST"})
    assert pre.status_code == 204 and "Prefer" in pre.headers["access-control-allow-headers"]


def test_an_error_answer_keeps_its_http_status_in_the_operation(make):
    client, _, priv = make()
    r = _async(client, "/review", {**SRC, "schema": "nope"}, priv)
    s, _ = _wait(client, priv, r.json()["operation_id"])
    assert s["http"] >= 400 and s["answer"]["error"]


# ------------------------------------------------------------------ Fabric's waits -----------------------------------

class SlowFabric(Workspace):
    """The model's create answers 202 with an operation that runs `polls` reads before it succeeds; the model is listed
    only then. `throttle` POSTs of the report answer 429 (PFE_FABRIC_THROTTLED) first."""

    def __init__(self, polls=0, throttle=0, fail_op=False, **kw):
        super().__init__(**kw)
        self.polls, self.throttle, self.fail_op, self.op_reads = polls, throttle, fail_op, 0

    def _route(self, method, url, body=None):
        path = url.split("?")[0]
        if method == "POST" and path.endswith(f"/workspaces/{gs.WS}/semanticModels") and self.polls:
            self.calls.append((method, path))
            self.pending_name = (body or {}).get("displayName")
            return gs.Response(202, None, {"x-ms-operation-id": "op-sm", "Retry-After": "0"})
        if method == "GET" and path.endswith("/operations/op-sm"):
            self.op_reads += 1
            if self.op_reads < self.polls:
                return gs.Response(200, {"status": "Running"})
            if self.fail_op:
                return gs.Response(200, {"status": "Failed", "error": {"errorCode": "CapacityNotActive",
                                                                       "message": "The capacity is paused"}})
            if not any(i["id"] == NEW_SM for i in self.items):
                self.items.append({"id": NEW_SM, "displayName": self.pending_name, "type": "SemanticModel",
                                   "description": "Created by Krusgraph"})
            return gs.Response(200, {"status": "Succeeded"})
        if method == "POST" and path.endswith(f"/workspaces/{gs.WS}/reports") and self.throttle:
            self.throttle -= 1
            self.calls.append((method, path))
            return gs.Response(429, {"errorCode": "PFE_FABRIC_THROTTLED", "message": "The capacity is throttled"}, {"Retry-After": "0"})
        return super()._route(method, url, body)


@pytest.fixture
def no_sleep(monkeypatch):
    import importlib
    d = importlib.import_module("fabric_backend.deploy")
    monkeypatch.setattr(d.time, "sleep", lambda s: None)


def _step(client, priv, rv, output, created=(), pending=(), **extra):
    r = _async(client, "/build", {**SRC, "review": rv, "outputs": [output], "only": [output["kind"]], "dry_run": False,
                                  "created": list(created), "skip_built": True, "pending": list(pending),
                                  "item_id": "11111111-2222-3333-4444-555555555555", "create_id": "c1", **extra}, priv)
    assert r.status_code == 202, r.text
    return _wait(client, priv, r.json()["operation_id"], seconds=60)


def test_a_slow_long_running_operation_is_pending_and_the_model_is_adopted_when_fabric_finishes(make, no_sleep):
    client, fake, priv = make(SlowFabric(polls=75))         # more reads than the tool's own wait (60): it stops first
    rv = _review(client, priv)
    s, seen = _step(client, priv, rv, {"kind": "semantic_model", "name": "demo_lh_model4"})
    card = s["answer"]["outputs"][0]
    assert "error" not in card["answer"], card["answer"]
    assert card["already_built"] and card["answer"]["adopted"] == 1 and "Fabric finished it" in card["answer"]["note"]
    assert card["created"][0]["id"] == NEW_SM and card["created"][0]["plan"]["plan_id"] == rv["plan_id"]
    assert sum(1 for c in fake.calls if c[0] == "POST" and c[1].endswith("/semanticModels")) == 1   # sent once, never twice
    assert "failed" not in seen


def test_a_long_running_operation_that_fails_in_fabric_says_fabrics_reason(make, no_sleep):
    client, fake, priv = make(SlowFabric(polls=70, fail_op=True))
    rv = _review(client, priv)
    s, _ = _step(client, priv, rv, {"kind": "semantic_model", "name": "demo_lh_model"})
    a = s["answer"]["outputs"][0]["answer"]
    assert a["kind"] == "capacity" and "paused" in a["error"]


def test_throttling_is_waiting_for_capacity_and_the_step_is_sent_again(make, no_sleep, monkeypatch):
    client, fake, priv = make(SlowFabric(throttle=2))       # create_report sends once per attempt: two attempts throttled
    rv = _review(client, priv)
    states = []
    real = operations.Live.progress

    def spy(self, status=None, **fields):
        if status:
            states.append((status, fields.get("words")))
        return real(self, status, **fields)
    monkeypatch.setattr(operations.Live, "progress", spy)
    created = _step(client, priv, rv, {"kind": "semantic_model", "name": "demo_lh_model"})[0]["answer"]["created"]
    s, _ = _step(client, priv, rv, {"kind": "report", "name": "demo_lh_report", "model": NEW_SM}, created)
    card = s["answer"]["outputs"][0]
    assert "error" not in card["answer"] and card["created"][0]["type"] == "Report", card
    waiting = [w for st, w in states if st == "waiting_capacity"]
    assert waiting and "Waiting for capacity" in waiting[0] and "Nothing failed" in waiting[0]


def test_pfe_fabric_throttled_is_throttling_with_the_capacity_metrics_link():
    a = errors.classify_http(400, json.dumps({"errorCode": "PFE_FABRIC_THROTTLED", "message": "Request is throttled"}), "the report")
    assert a["kind"] == "throttled" and "metrics-app" in a["hint"]
    assert errors.classify_http(429, "", "x")["kind"] == "throttled"


def test_an_item_recorded_as_pending_is_adopted_not_refused(make):
    """demo_lh_model4: Fabric made it after the editor stopped waiting; outputs.json had it as pending (no id)."""
    there = [{"id": NEW_SM, "displayName": "demo_lh_model4", "type": "SemanticModel", "description": "Created by Krusgraph"}]
    client, fake, priv = make(Workspace(items=there))
    rv = _review(client, priv)
    pending = [{"output": "semantic_model", "type": "SemanticModel", "name": "demo_lh_model4"}]
    s, _ = _step(client, priv, rv, {"kind": "semantic_model", "name": "demo_lh_model4"}, pending=pending)
    card = s["answer"]["outputs"][0]
    assert not card.get("refusal") and card["already_built"] and card["created"][0]["id"] == NEW_SM, card
    # without the pending entry, an item of that name nobody recorded is still not taken for this Model's
    plain = [{"id": "someone", "displayName": "theirs_model", "type": "SemanticModel", "description": "made by hand"}]
    client, fake, priv = make(Workspace(items=plain))
    rv = _review(client, priv)
    s, _ = _step(client, priv, rv, {"kind": "semantic_model", "name": "theirs_model"})
    assert s["answer"]["outputs"][0]["refusal"]["kind"] == "already_exists"


def test_the_dry_run_predicts_create_for_an_item_built_from_the_same_plan(make):
    client, fake, priv = make()
    rv = _review(client, priv)
    s, _ = _step(client, priv, rv, {"kind": "silver_notebook", "name": "demo_lh_silver"})
    created = s["answer"]["created"]
    r = _post(client, "/build", {**SRC, "review": rv, "outputs": [{"kind": "silver_notebook", "name": "demo_lh_silver"}],
                                 "dry_run": True, "created": created}, priv)
    card = r.json()["outputs"][0]
    assert card["already_built"] and card["answer"]["dry_run"] is True, card
    assert card["answer"]["note"] == "Already built from this plan by an earlier Create; Create skips it."
    assert card["would"] == "create"                                                  # never "would be updated"

