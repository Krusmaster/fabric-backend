"""WB9: the pilot's self-check. Read only, one sentence per check, documented APIs only; the tenant setting is said to be
unreadable instead of guessed."""
import pytest

from fabric_backend import server as S, workload_api as W

WS = "11111111-2222-3333-4444-555555555555"


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(str(self.status_code))


def _wire(monkeypatch, *, scopes, pages, items):
    import requests
    calls = []
    monkeypatch.setattr(W, "token_scopes", lambda: scopes)
    monkeypatch.setattr(S, "_headers", lambda ctx: {"Authorization": "Bearer x"})

    def get(url, headers=None, timeout=None):
        calls.append(url)
        return pages.pop(0)
    monkeypatch.setattr(requests, "get", get)

    def list_items(ws, headers):
        if isinstance(items, Exception):
            raise items
        return items
    monkeypatch.setattr(S, "_list_items", list_items)
    return calls


def _by_id(out):
    return {c["id"]: c for c in out["checks"]}


ALL = {"Workspace.Read.All", "Item.ReadWrite.All"}


def test_a_ready_workspace_says_ready_and_the_tenant_setting_is_unknown(monkeypatch):
    calls = _wire(monkeypatch, scopes=ALL, pages=[
        Resp(200, {"value": [{"id": "other"}], "continuationUri": "https://api.fabric.microsoft.com/v1/workspaces?c=2"}),
        Resp(200, {"value": [{"id": WS.upper(), "capacityId": "cap-1"}]})],
        items=[{"type": "Lakehouse"}, {"type": "Notebook"}])
    out = W.run_selfcheck(W.selfcheck_request({"workspace": WS}))
    c = _by_id(out)
    assert out["ready"] is True and len(calls) == 2                            # followed the continuation
    assert [c[k]["state"] for k in ("consent", "capacity", "workspace", "lakehouse")] == ["ok"] * 4
    assert c["tenant_setting"]["state"] == "unknown"
    assert out["note"] == W.NOTHING_CHANGED


def test_missing_consent_capacity_and_lakehouse_are_each_named(monkeypatch):
    _wire(monkeypatch, scopes={"Workspace.Read.All"}, pages=[Resp(200, {"value": [{"id": WS}]})], items=[])
    c = _by_id(W.run_selfcheck(W.selfcheck_request({"workspace": WS})))
    assert c["consent"]["state"] == "missing" and "Item.Read.All" in c["consent"]["words"]
    assert c["capacity"]["state"] == "missing" and "Pro alone" in c["capacity"]["words"]
    assert c["lakehouse"]["state"] == "missing"


def test_a_workspace_you_cannot_see_is_missing_not_an_error(monkeypatch):
    _wire(monkeypatch, scopes=None, pages=[Resp(403, {})], items=[])
    out = W.run_selfcheck(W.selfcheck_request({"workspace": WS}))
    c = _by_id(out)
    assert out["ready"] is False
    assert c["consent"]["state"] == "unknown" and c["workspace"]["state"] == "missing"
    assert "capacity" not in c


def test_items_that_cannot_be_read_are_reported(monkeypatch):
    _wire(monkeypatch, scopes=ALL, pages=[Resp(200, {"value": [{"id": WS, "capacityId": "c"}]})],
          items=RuntimeError("403"))
    c = _by_id(W.run_selfcheck(W.selfcheck_request({"workspace": WS})))
    assert c["workspace"]["state"] == "missing" and "lakehouse" not in c


def test_the_request_needs_a_workspace_guid():
    for bad in (None, {}, {"workspace": "x"}, {"workspace": 3}):
        with pytest.raises(W.BadRequest):
            W.selfcheck_request(bad)


def test_the_route_is_there():
    import inspect
    assert 'f"{PREFIX}/selfcheck"' in inspect.getsource(W.routes)
