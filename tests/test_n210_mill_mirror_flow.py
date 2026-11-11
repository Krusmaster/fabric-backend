"""n210, item 2: the editor's flow on the mill sample read from a mirrored database (n201), after n198, n200 and n209:
the review, the dry run, Create one output at a time (the pipeline with Run once), the Data product page's status, the
health request as the page sends it (the Model's own workspace; the health table is in source.json's target lakehouse,
not in the read-only mirror), and Retire's dry run. Each step reads what the one before wrote. Test doubles only."""
import base64
import json

import pytest

pytest.importorskip("jwt")

import golden_support as gs  # noqa: E402
from test_n201_mirrored import MILL, MILL_SRC, MirrorFabric, _post, _writes, mill_endpoint  # noqa: E402,F401
from test_n209_integration import Guids  # noqa: E402
from test_workload_api import FakeJWKS, WL, keys  # noqa: E402,F401
from test_workload_build import EVERY_SCOPE, ScopedOBO  # noqa: E402
from fabric_backend import lineage, server, workload_api  # noqa: E402
from fabric_backend.entra import Validator  # noqa: E402


class MillMirror(MirrorFabric, Guids):
    """n201's mirrored databases with n209's GUID ids, where what Create makes is listed among the workspace's items."""

    def _items(self):
        return super()._items() + [i for i in self.items if i not in gs.ITEMS]


@pytest.fixture
def make(keys, monkeypatch):
    import sys
    import requests
    from starlette.applications import Starlette
    from starlette.testclient import TestClient
    priv, pub = keys
    monkeypatch.setattr(server, "MODEL_DEFINITION_PAUSES", (0, 0, 0))

    def build(sql):
        fake = MillMirror()
        for verb in ("get", "post", "patch"):
            monkeypatch.setattr(requests, verb, getattr(fake, verb))
        mod = sql()
        monkeypatch.setitem(sys.modules, "pyodbc", mod)
        monkeypatch.setattr(server, "limiter", None)
        app = Starlette(routes=workload_api.routes(WL, Validator(WL, FakeJWKS(pub)), ScopedOBO(EVERY_SCOPE)))
        return TestClient(app), fake, priv, mod
    return build

ITEM = "22222222-3333-4444-5555-777777777777"
OUTPUTS = [{"kind": "silver_notebook", "name": "mill_silver"}, {"kind": "gold_views", "name": "mill_gold"},
           {"kind": "pipeline", "name": "mill_flow", "jobs": {"run_once": True}}]


def test_mill_mirror_review_dry_run_create_page_health_and_retire_agree(make, monkeypatch):
    client, fake, priv, _sql = make(mill_endpoint)
    rv = _post(client, "/review", {**MILL_SRC, "decisions": []}, priv).json()["review"]
    assert rv["plan_id"].startswith("plan-")

    fake.calls.clear()
    dry = _post(client, "/build", {**MILL_SRC, "review": rv, "outputs": OUTPUTS, "dry_run": True, "created": []}, priv).json()
    assert [c["decision"]["action"] for c in dry["outputs"]] == ["create"] * len(OUTPUTS), [c.get("decision") for c in dry["outputs"]]
    assert not _writes(fake), _writes(fake)

    created = []
    for o in OUTPUTS:
        r = _post(client, "/build", {**MILL_SRC, "review": rv, "outputs": OUTPUTS, "only": [o["kind"]], "dry_run": False,
                                     "created": created, "skip_built": True}, priv).json()
        card = r["outputs"][0]
        assert card["decision"]["action"] == "create" and card.get("created"), card
        created += card["created"]
    assert {c["plan"]["plan_id"] for c in created} == {rv["plan_id"]}
    assert MILL not in {c["id"] for c in created}                  # nothing is written into the mirror
    assert {c["workspace"] for c in created} == {gs.WS}

    again = _post(client, "/build", {**MILL_SRC, "review": rv, "outputs": OUTPUTS, "dry_run": True, "created": created}, priv).json()
    assert [c["decision"]["action"] for c in again["outputs"]] == ["skip"] * len(OUTPUTS), [c.get("decision") for c in again["outputs"]]

    outputs_json = {"created": created, "removed": [], "pending": [],
                    "product": {"name": "Mill", "plan": {"plan_id": rv["plan_id"], "schema_fingerprint": rv["schema_fingerprint"]}}}
    page = {"workspace": gs.WS, "item_id": ITEM, "outputs": outputs_json, "product": "Mill", "plan_id": rv["plan_id"]}
    st = _post(client, "/product", {**page, "action": "status"}, priv)
    assert st.status_code == 200, st.text
    assert {r["state"] for r in st.json()["items"]} == {"built"}, st.json()["items"]

    # health: the page's form; the lakehouse is source.json's target, never the mirror
    source = {"version": 1, "platform": "fabric", "workspaceId": gs.WS, "itemId": MILL, "itemType": "MirroredDatabase",
              "displayName": "mill_mirror", "schema": "dbo", "target": {"itemId": gs.LH, "displayName": "demo_lh"}}
    parts = [{"path": k, "payload": base64.b64encode(json.dumps(v).encode()).decode()}
             for k, v in (("source.json", source), ("outputs.json", outputs_json))]
    asked = []

    class R:
        def json(self):
            return {"definition": {"parts": parts}}
    monkeypatch.setattr(lineage, "_definition_response", lambda url, headers: asked.append(url) or R())
    seen = {}
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: seen.setdefault("source", (ws, src)) and
                        {"type": "Lakehouse", "id": src, "displayName": "demo_lh", "schemas_enabled": True})
    monkeypatch.setattr(server, "_execute_factory", lambda item, token: (lambda sql: [{"n": 0}]))
    h = _post(client, "/health", {"workspace": gs.WS, "item_id": ITEM, "product": "Mill"}, priv)
    assert h.status_code == 200, h.text
    assert h.json()["word"] == "not checked yet" and h.json()["products"][0]["plan_id"] == rv["plan_id"]
    assert seen["source"] == (gs.WS, gs.LH) and asked[0].endswith(f"/items/{ITEM}/getDefinition")

    fake.calls.clear()
    ret = _post(client, "/product", {**page, "action": "retire", "scope": "delete"}, priv)
    assert ret.status_code == 200, ret.text
    assert {x["id"] for x in ret.json()["items"]} == {c["id"] for c in created} and not ret.json()["refused"]
    assert not _writes(fake), _writes(fake)
