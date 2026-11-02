"""n87, point 10: lineage reads an item's definition through getDefinition; when Fabric answers 202, the result is fetched
from /operations/{id}/result. That GET is now sent the way deploy.py sends reads (deploy.send, round n81): a 429 or 503
is waited out after Retry-After and asked again, within a budget; other answers come back as they are. The answer's
shape does not change. Fake answers only."""
import base64
import json

import requests

import importlib

from fabric_backend import lineage

deploy = importlib.import_module("fabric_backend.deploy")     # the package exports a function named deploy too

WS, ITEM = "ws-1", "sm-1"
PARTS = {"definition/model.tmdl": "model Model\n", "definition.pbism": "{}"}


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
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


def _definition():
    return {"definition": {"parts": [{"path": p, "payload": base64.b64encode(t.encode()).decode(), "payloadType": "InlineBase64"}
                                     for p, t in PARTS.items()]}}


def _fabric(monkeypatch, results):
    """getDefinition answers 202; the operation has Succeeded; the result answers `results` in turn."""
    seen, slept = [], []
    answers = iter(results)
    monkeypatch.setattr(requests, "post", lambda url, **k: seen.append(("POST", url)) or Resp(
        202, None, {"x-ms-operation-id": "op-9", "Location": f"{deploy.FABRIC}/v1/operations/op-9"}))

    def get(url, **k):
        seen.append(("GET", url))
        if url.endswith("/operations/op-9"):
            return Resp(200, {"status": "Succeeded"})
        assert url.endswith("/operations/op-9/result")
        return next(answers)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))
    return seen, slept


def test_a_throttled_result_is_asked_again_after_retry_after(monkeypatch):
    seen, slept = _fabric(monkeypatch, [Resp(429, {"errorCode": "TooManyRequests"}, {"Retry-After": "3"}), Resp(200, _definition())])
    parts = lineage.rest_definition_parts(WS, "semanticModels", ITEM, {"Authorization": "Bearer x"}, fmt="TMDL")
    assert parts == PARTS                                                    # the same shape as an answer read at once
    results = [u for m, u in seen if u.endswith("/result")]
    assert len(results) == 2 and 3 in slept


def test_a_503_without_retry_after_backs_off_and_then_reads(monkeypatch):
    seen, slept = _fabric(monkeypatch, [Resp(503, None), Resp(200, _definition())])
    assert lineage.rest_definition_parts(WS, "semanticModels", ITEM, {}) == PARTS
    assert deploy.FALLBACK_RETRY_SECONDS in slept


def test_a_result_that_stays_refused_raises_as_before(monkeypatch):
    _fabric(monkeypatch, [Resp(404, {"errorCode": "NotFound"})])
    try:
        lineage.rest_definition_parts(WS, "semanticModels", ITEM, {})
    except requests.HTTPError as e:
        assert e.response.status_code == 404
    else:
        raise AssertionError("a 404 must raise as it did")


def test_lineage_sends_the_result_get_through_deploy_send(monkeypatch):
    calls = []
    real = deploy.send

    def spy(method, url, headers, **k):
        calls.append((method, url, k.get("write")))
        return real(method, url, headers, **k)
    monkeypatch.setattr(deploy, "send", spy)
    _fabric(monkeypatch, [Resp(200, _definition())])
    lineage.rest_definition_parts(WS, "semanticModels", ITEM, {})
    assert ("get", f"{deploy.FABRIC}/v1/operations/op-9/result", False) in calls
