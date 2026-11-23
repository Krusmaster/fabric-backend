"""WB8 (requirement 2.4): one correlation id per workload request, on every log line of that request, in the answer's
header and in every error answer; Fabric's ActivityId and RequestId logged beside it when Fabric sends them. Never a
token, a body or a name in the log."""
import json
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from fabric_backend import workload_api as W

CID = "0b9d6a1e-2c4f-4c55-9d3e-1f2a3b4c5d6e"
H = W.CORRELATION_HEADER


@pytest.fixture
def client(monkeypatch):
    claims = {"tid": "44444444-0000-0000-0000-000000000004", "oid": "u", "scp": "user_impersonation", "name": "Alex Example"}
    monkeypatch.setattr(W, "build_request", lambda b: {**b, "dry_run": True})

    def run_build(req):
        W.log("build_step", outputs=1)                        # a line written deep inside the request
        if req.get("boom"):
            raise RuntimeError("secret detail never shown")
        return {"dry_run": True}
    monkeypatch.setattr(W, "run_build", run_build)
    routes = W.routes(SimpleNamespace(), validator=SimpleNamespace(validate=lambda t: claims), obo=object())
    return TestClient(Starlette(routes=routes), raise_server_exceptions=False)


def _lines(capsys):
    return [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith("{")]


def test_the_editors_id_is_on_every_line_and_in_the_answer(client, capsys):
    r = client.post("/workload/v1/build", json={}, headers={"Authorization": "Bearer tok-SECRET", H: CID})
    assert r.status_code == 200 and r.headers[H] == CID
    lines = _lines(capsys)
    assert [x for x in lines if x["event"] == "build_step"][0]["cid"] == CID
    assert all(x.get("cid") == CID for x in lines if x.get("krusgraph") == "workload")
    out = json.dumps(lines)
    assert "tok-SECRET" not in out and "Alex Example" not in out


def test_a_missing_or_odd_id_is_replaced_and_errors_carry_it(client, capsys):
    r = client.post("/workload/v1/build", json={"boom": True}, headers={"Authorization": "Bearer t", H: "x y<script>"})
    cid = r.headers[H]
    assert r.status_code == 500 and cid != "x y<script>" and len(cid) == 36
    assert r.json()["correlation_id"] == cid and "secret detail" not in r.text
    assert {x["event"] for x in _lines(capsys) if x.get("cid") == cid} >= {"build_step", "route_failed"}
    r = client.post("/workload/v1/build", json={}, headers={"Authorization": ""})
    assert r.status_code == 401 and r.json()["correlation_id"] == r.headers[H]


def test_fabric_activity_and_request_ids_are_logged_beside_it(client, capsys):
    client.post("/workload/v1/build", json={}, headers={"Authorization": "Bearer t", H: CID,
                                                        "ActivityId": "11111111-aaaa-bbbb-cccc-000000000001",
                                                        "RequestId": "22222222-aaaa-bbbb-cccc-000000000002"})
    got = [x for x in _lines(capsys) if x["event"] == "fabric_ids"][0]
    assert got["fabric_activity_id"].startswith("1111") and got["fabric_request_id"].startswith("2222") and got["cid"] == CID


def test_the_id_does_not_leak_into_the_next_request(client, capsys):
    client.post("/workload/v1/build", json={}, headers={"Authorization": "Bearer t", H: CID})
    capsys.readouterr()
    W.log("outside")
    assert "cid" not in _lines(capsys)[0]


def test_the_browser_may_send_and_read_it():
    h = W.cors_headers("https://app.fabric.microsoft.com")
    assert H in h["Access-Control-Allow-Headers"] and h["Access-Control-Expose-Headers"] == H
