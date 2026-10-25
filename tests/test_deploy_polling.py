"""deploy(): the create/update call and the long-running operation it starts, with Fabric mocked."""
import importlib
import json

import requests

dep = importlib.import_module("fabric_backend.deploy")          # the package re-exports the function under the same name

ENV = {"displayName": "shop_api", "type": "GraphQLApi", "definition": {"parts": []}, "skipped_relationships": []}


class Resp:
    def __init__(self, status, body=None, headers=None, text=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = text if text is not None else (json.dumps(body) if body is not None else "")

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


def run(monkeypatch, polls, create=Resp(202, None, {"x-ms-operation-id": "op-1"}), existing=None):
    gets = iter(polls)
    seen = {"polls": 0}
    monkeypatch.setattr(dep, "find_item", lambda *a, **k: existing)
    monkeypatch.setattr(requests, "post", lambda url, **k: create)

    def get(url, **k):
        assert url.endswith("/v1/operations/op-1")
        seen["polls"] += 1
        return next(gets)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(dep.time, "sleep", lambda s: None)
    result = dep.deploy(ENV, "ws-1", token_provider=lambda: "tok", max_polls=5)
    return result, seen["polls"]


def test_created_item_is_found_after_the_operation_succeeds(monkeypatch):
    answers = iter([None, "item-9"])                                 # no item before the create; found after the operation
    result, polls = run(monkeypatch, [Resp(200, {"status": "Running"}), Resp(200, {"status": "Succeeded"})])
    assert result == {"status": "Succeeded", "mode": "created", "id": None} and polls == 2
    monkeypatch.setattr(dep, "find_item", lambda *a, **k: next(answers))
    monkeypatch.setattr(requests, "get", lambda url, **k: Resp(200, {"status": "Succeeded"}))
    result = dep.deploy(ENV, "ws-1", token_provider=lambda: "tok", max_polls=5)
    assert result == {"status": "Succeeded", "mode": "created", "id": "item-9"}


def test_transient_errors_while_polling_are_retried(monkeypatch):
    polls = [Resp(503, None, text="<html>upstream</html>"), Resp(429, {"error": "throttled"}), Resp(200, {"status": "Succeeded"})]
    result, n = run(monkeypatch, polls, existing="item-1")
    assert result["status"] == "Succeeded" and result["mode"] == "updated" and result["id"] == "item-1" and n == 3


def test_lost_sign_in_while_polling_is_reported_not_waited_out(monkeypatch):
    polls = [Resp(200, {"status": "Running"}), Resp(401, {"error": {"code": "Unauthorized", "message": "token expired"}})]
    result, n = run(monkeypatch, polls, existing="item-1")
    assert result["status"] == "Failed" and result["http"] == 401 and "token expired" in result["body"] and n == 2


def test_operation_that_never_finishes_is_a_timeout(monkeypatch):
    result, n = run(monkeypatch, [Resp(200, {"status": "Running"})] * 5)
    assert result == {"status": "Timeout", "mode": "created", "operation": "op-1"} and n == 5


def test_failed_operation_and_refused_create_keep_fabrics_answer(monkeypatch):
    result, _ = run(monkeypatch, [Resp(200, {"status": "Failed", "error": {"errorCode": "InvalidDefinition", "message": "bad part"}})])
    assert result["status"] == "Failed" and result["mode"] == "created" and result["error"]["errorCode"] == "InvalidDefinition"
    refused = Resp(403, {"errorCode": "InsufficientPrivileges", "message": "no"}, {})
    result, n = run(monkeypatch, [], create=refused)
    assert result == {"status": "Failed", "mode": "created", "http": 403, "body": refused.text} and n == 0
