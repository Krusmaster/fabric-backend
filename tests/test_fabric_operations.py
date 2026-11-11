"""Long-running Fabric operations in deploy.py with Fabric faked (n81): Retry-After in seconds and as an HTTP date, 429
and 503 sent again within a time budget, a write never sent again after an answer that may mean it was carried out,
GET /operations/{id}/result for a created item's id, a 202 without an operation id, and a wait that stops saying the
operation may go on in Fabric. Behaviour as Microsoft documents it (microsoft/mcp at 7257a94, long-running-operation.md,
throttling.md); no call leaves the process."""
import importlib
import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest
import requests

from fabric_backend import errors, limits, server

dep = importlib.import_module("fabric_backend.deploy")
WS = "ws-1"
ENV = {"displayName": "shop_model", "definition": {"parts": [{"path": "definition.pbism", "payload": "e30=", "payloadType": "InlineBase64"}]}}


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)


class Fabric:
    """Answers in order per kind of call, records every call and every sleep; the clock moves only when it sleeps."""

    def __init__(self, monkeypatch, posts=(), polls=(), results=(), items=None):
        self.posts, self.polls, self.results = list(posts), list(polls), list(results)
        self.items = items if items is not None else {"value": []}
        self.calls, self.sleeps, self.now = [], [], 0.0
        monkeypatch.setattr(requests, "post", self.post)
        monkeypatch.setattr(requests, "get", self.get)
        monkeypatch.setattr(dep.time, "sleep", self.sleep)
        monkeypatch.setattr(dep.time, "monotonic", lambda: self.now)

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    @staticmethod
    def _next(answers):
        a = answers.pop(0)
        if isinstance(a, BaseException):
            raise a
        return a

    def post(self, url, **kw):
        self.calls.append(("POST", url))
        return self._next(self.posts)

    def get(self, url, **kw):
        self.calls.append(("GET", url))
        if url.endswith("/result"):
            return self._next(self.results)
        if "/operations/" in url:
            return self._next(self.polls)
        return Resp(200, self.items)

    def count(self, method, part=""):
        return sum(1 for m, u in self.calls if m == method and part in u)


def create(**kw):
    return dep.create_item_with_definition("semanticModels", "SemanticModel", ENV, WS, token_provider=lambda: "tok", **kw)


ACCEPTED = Resp(202, None, {"x-ms-operation-id": "op-1"})
RUNNING, SUCCEEDED = Resp(200, {"status": "Running"}), Resp(200, {"status": "Succeeded"})


# ------------------------------------------------------------------ Retry-After ------------------------------------

def test_retry_after_in_seconds_and_as_an_http_date():
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc)
    assert dep.retry_after_seconds("30") == 30 and dep.retry_after_seconds(" 0 ") == 0 and dep.retry_after_seconds("2.5") == 2.5
    assert dep.retry_after_seconds(format_datetime(now + timedelta(seconds=45), usegmt=True), now=now) == 45
    assert dep.retry_after_seconds("Mon, 02 Nov 2026 12:00:20 GMT", now=now) == 20
    assert dep.retry_after_seconds("Mon, 02 Nov 2026 11:59:00 GMT", now=now) == 0          # a date gone by: no wait
    for bad in (None, "", "-5", "soon", "inf", "nan"):
        assert dep.retry_after_seconds(bad) is None


def test_the_operation_id_comes_from_the_header_or_from_location():
    assert dep.operation_id(Resp(202, None, {"x-ms-operation-id": "op-1"})) == "op-1"
    assert dep.operation_id(Resp(202, None, {"X-Ms-Operation-Id": "op-2"})) == "op-2"                 # headers ignore case
    assert dep.operation_id(Resp(202, None, {"Location": f"{dep.FABRIC}/v1/operations/op-3"})) == "op-3"
    assert dep.operation_id(Resp(202, None, {"Location": f"{dep.FABRIC}/v1/workspaces/ws/items/x"})) is None
    assert dep.operation_id(Resp(202, None, {})) is None


# ------------------------------------------------------------------ writes ------------------------------------------

def test_a_throttled_write_is_sent_again_after_retry_after(monkeypatch):
    fake = Fabric(monkeypatch, posts=[Resp(429, {"errorCode": "TooManyRequests"}, {"Retry-After": "7"}), ACCEPTED],
                  polls=[SUCCEEDED], results=[Resp(200, {"id": "sm-1", "type": "SemanticModel"})])
    assert create() == {"status": "Succeeded", "mode": "created", "id": "sm-1"}
    assert fake.count("POST") == 2 and fake.sleeps[0] == 7


def test_a_503_write_waits_until_the_http_date(monkeypatch):
    when = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30), usegmt=True)
    fake = Fabric(monkeypatch, posts=[Resp(503, None, {"Retry-After": when}), Resp(201, {"id": "sm-2"})])
    assert create() == {"status": "Succeeded", "mode": "created", "id": "sm-2"}
    assert fake.count("POST") == 2 and 25 <= fake.sleeps[0] <= 30


@pytest.mark.parametrize("answer", [Resp(500, {"errorCode": "InternalError"}), Resp(502, None), Resp(504, None),
                                    Resp(400, {"errorCode": "InvalidDefinition"})])
def test_a_write_is_never_sent_again_after_an_answer_that_may_mean_it_was_carried_out(monkeypatch, answer):
    fake = Fabric(monkeypatch, posts=[answer, ACCEPTED])
    result = create()
    assert result["status"] == "Failed" and result["http"] == answer.status_code and fake.count("POST") == 1


def test_a_write_that_timed_out_is_not_sent_again_and_says_so(monkeypatch):
    fake = Fabric(monkeypatch, posts=[requests.exceptions.ReadTimeout("read timed out"), ACCEPTED])
    result = create()
    assert result == {"status": "Timeout", "mode": "created", "note": dep.MAY_HAVE_ARRIVED} and fake.count("POST") == 1
    assert "not sent again" in result["note"]


def test_a_202_without_an_operation_id_is_unknown_and_not_sent_again(monkeypatch):
    fake = Fabric(monkeypatch, posts=[Resp(202, None, {}), ACCEPTED])
    result = create()
    assert result == {"status": "Timeout", "mode": "created", "note": dep.NO_OPERATION_ID}
    assert "unknown" in result["note"] and "do not send it again" in result["note"]
    assert fake.count("POST") == 1 and fake.count("GET", "/operations/") == 0


def test_a_202_with_only_a_location_header_is_followed(monkeypatch):
    fake = Fabric(monkeypatch, posts=[Resp(202, None, {"Location": f"{dep.FABRIC}/v1/operations/op-7"})], polls=[SUCCEEDED],
                  results=[Resp(200, {"id": "sm-7"})])
    assert create()["id"] == "sm-7" and ("GET", f"{dep.FABRIC}/v1/operations/op-7") in fake.calls


def test_throttling_that_never_ends_is_a_refusal_with_the_usual_error_form(monkeypatch):
    fake = Fabric(monkeypatch, posts=[Resp(429, {"errorCode": "TooManyRequests"}, {"Retry-After": "1"})] * 5)
    result = create()
    assert result["status"] == "Failed" and result["http"] == 429 and fake.count("POST") == dep.WRITE_ATTEMPTS
    answer = errors.classify_http(429, result["body"], "creating 'shop_model'")
    assert set(answer) == {"error", "kind", "hint"} and answer["kind"] == "throttled"


def test_a_retry_after_longer_than_the_budget_is_not_waited(monkeypatch):
    fake = Fabric(monkeypatch, posts=[Resp(429, None, {"Retry-After": "600"}), ACCEPTED])
    result = create(max_wait_seconds=60)
    assert result["status"] == "Failed" and result["http"] == 429 and fake.count("POST") == 1 and fake.sleeps == []


# ------------------------------------------------------------------ the wait -----------------------------------------

def test_retry_after_from_the_202_and_from_each_poll_sets_the_pace(monkeypatch):
    fake = Fabric(monkeypatch, posts=[Resp(202, None, {"x-ms-operation-id": "op-1", "Retry-After": "20"})],
                  polls=[Resp(202, {"status": "Running"}, {"Retry-After": "4"}), Resp(200, {"status": "NotStarted"}), SUCCEEDED],
                  results=[Resp(200, {"id": "sm-1"})])
    assert create(poll_seconds=3)["status"] == "Succeeded"
    # n222: the first reads come after deploy.FIRST_POLLS (1 s), never longer than the 202's Retry-After, a poll's or
    # poll_seconds; after FIRST_POLLS each one's own (tests/test_n222_speed_and_products.py)
    assert fake.sleeps == [1.0, 1.0, 1.0]


def test_throttled_and_unavailable_polls_are_waited_out(monkeypatch):
    fake = Fabric(monkeypatch, posts=[ACCEPTED], polls=[Resp(429, None, {"Retry-After": "9"}), Resp(503, None), SUCCEEDED],
                  results=[Resp(200, {"id": "sm-1"})])
    assert create(poll_seconds=2)["id"] == "sm-1" and fake.sleeps == [9, 2]


def test_the_time_budget_ends_the_wait_and_says_the_operation_may_go_on(monkeypatch):
    fake = Fabric(monkeypatch, posts=[ACCEPTED], polls=[Resp(200, {"status": "Running"}, {"Retry-After": "4"})] * 50)
    result = create(max_wait_seconds=10)
    assert result["status"] == "Timeout" and result["operation"] == "op-1" and "may still finish" in result["note"]
    assert sum(fake.sleeps) <= 10 and fake.count("GET", "/operations/") < 50 and fake.count("POST") == 1


def test_polls_spent_end_the_wait_the_same_way(monkeypatch):
    fake = Fabric(monkeypatch, posts=[ACCEPTED], polls=[RUNNING] * 4)
    result = create(max_polls=4)
    assert result == {"status": "Timeout", "mode": "created", "operation": "op-1", "note": dep.WAIT_STOPPED.format(op="op-1")}
    assert fake.count("GET", "/operations/") == 4


def test_a_status_read_that_fails_now_and_then_is_read_again_and_three_in_a_row_stop_the_wait(monkeypatch):
    blip = requests.exceptions.ConnectionError("reset")
    fake = Fabric(monkeypatch, posts=[ACCEPTED], polls=[blip, RUNNING, blip, SUCCEEDED], results=[Resp(200, {"id": "sm-1"})])
    assert create()["id"] == "sm-1" and fake.count("POST") == 1
    fake = Fabric(monkeypatch, posts=[ACCEPTED], polls=[blip, blip, blip, SUCCEEDED])
    result = create()
    assert result["status"] == "Timeout" and "may still finish" in result["note"] and fake.count("POST") == 1


def test_a_lost_sign_in_while_waiting_keeps_fabrics_answer_and_says_the_operation_may_go_on(monkeypatch):
    Fabric(monkeypatch, posts=[ACCEPTED], polls=[RUNNING, Resp(401, {"errorCode": "TokenExpired", "message": "expired"})])
    result = create()
    assert result["status"] == "Failed" and result["http"] == 401 and "expired" in result["body"] and "may still finish" in result["note"]


def test_an_interrupted_wait_says_the_operation_goes_on(monkeypatch):
    fake = Fabric(monkeypatch, posts=[ACCEPTED], polls=[RUNNING])
    monkeypatch.setattr(dep.time, "sleep", lambda s: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt) as stopped:
        create()
    assert isinstance(stopped.value, dep.WaitInterrupted) and "may still finish" in str(stopped.value) and "op-1" in str(stopped.value)
    assert fake.count("POST") == 1


def test_a_failed_operation_is_reported_and_nothing_is_sent_again(monkeypatch):
    fake = Fabric(monkeypatch, posts=[ACCEPTED, ACCEPTED], polls=[Resp(200, {"status": "Failed", "error": {"errorCode": "X", "message": "bad"}})])
    result = create()
    assert result["status"] == "Failed" and result["error"]["errorCode"] == "X" and fake.count("POST") == 1


# ------------------------------------------------------------------ the result --------------------------------------

def test_the_created_items_id_comes_from_the_operation_result(monkeypatch):
    fake = Fabric(monkeypatch, posts=[ACCEPTED], polls=[SUCCEEDED],
                  results=[Resp(429, None, {"Retry-After": "2"}), Resp(200, {"id": "sm-9", "displayName": "shop_model"})])
    assert create(update_existing=False) == {"status": "Succeeded", "mode": "created", "id": "sm-9"}
    assert fake.count("GET", "/operations/op-1/result") == 2 and fake.count("GET", "/items") == 0     # no item-list lookup


def test_without_a_result_the_item_is_found_by_name(monkeypatch):
    fake = Fabric(monkeypatch, posts=[ACCEPTED], polls=[SUCCEEDED], results=[Resp(400, {"errorCode": "OperationHasNoResult"})],
                  items={"value": [{"id": "sm-4", "displayName": "shop_model", "type": "SemanticModel"}]})
    assert create(update_existing=False)["id"] == "sm-4" and fake.count("GET", "/items") == 1


def test_an_update_needs_no_result(monkeypatch):
    fake = Fabric(monkeypatch, posts=[ACCEPTED], polls=[SUCCEEDED],
                  items={"value": [{"id": "sm-5", "displayName": "shop_model", "type": "SemanticModel"}]})
    assert create() == {"status": "Succeeded", "mode": "updated", "id": "sm-5"}
    assert fake.count("GET", "/result") == 0 and fake.calls[1][1].endswith("/semanticModels/sm-5/updateDefinition")


def test_the_item_list_is_read_again_after_throttling(monkeypatch):
    answers = [Resp(429, None, {"Retry-After": "3"}), Resp(200, {"value": [{"id": "a-1", "displayName": "shop_api"}]})]
    monkeypatch.setattr(requests, "get", lambda url, **k: answers.pop(0))
    slept = []
    monkeypatch.setattr(dep.time, "sleep", slept.append)
    assert dep.find_item(WS, "shop_api", {}) == "a-1" and slept == [3]


# ------------------------------------------------------------------ the parts are checked before anything is sent ---

def test_a_wrong_definition_is_not_sent(monkeypatch):
    fake = Fabric(monkeypatch, posts=[ACCEPTED])
    bad = {"displayName": "shop_model", "definition": {"parts": [
        {"path": "model.bim", "payload": "e30=", "payloadType": "InlineBase64"},
        {"path": "Model.bim", "payload": "not base64!", "payloadType": "InlineBase64"}]}}
    with pytest.raises(limits.DefinitionError) as refused:
        dep.create_item_with_definition("semanticModels", "SemanticModel", bad, WS, token_provider=lambda: "tok")
    assert "not sent" in str(refused.value) and "same path when case is ignored" in str(refused.value)
    assert fake.count("POST") == 0


def test_the_tool_answer_keeps_its_form_when_the_outcome_is_unknown():
    out = json.loads(server._finish_create({}, {"status": "Timeout", "mode": "created", "note": dep.NO_OPERATION_ID},
                                           "Item.ReadWrite.All", "creating 'shop_model'"))
    assert {"error", "kind", "hint", "result"} <= set(out) and out["kind"] == "timeout"
    assert out["result"]["note"] == dep.NO_OPERATION_ID
