"""Round n209, item 6: n198 (the Data product page), n200 (health) and n201 (mirrored sources) were built in parallel;
this runs the editor's flow end to end through the workload routes with the test doubles on the shop sample, in the order
the editor sends it: the review, the dry run, Create one output at a time (the pipeline with Run once ticked), the Data
product page (status, and the health word after two pipeline runs, read from the Model item's own definition as n198's
page asks it), Update's dry run, and Retire's dry run. It checks that what one round writes is what the next reads: the
plan id Create records in outputs.json is the plan the pipeline's health rows carry and the page's health request finds;
every item Create records is 'built' on the page; Update's dry run gives its confirm and writes nothing; Retire's dry run
lists exactly the items Create recorded and deletes nothing. Fabric REST is tests/golden_support.py's double (with GUID
ids, as Fabric gives them); the health rows come from tests/health_cases.py's SQLite lakehouse, as in test_n200_health."""
import base64
import json
import uuid

import pytest

pytest.importorskip("jwt")

import health_cases as hc  # noqa: E402
from test_n200_health import one_run  # noqa: E402
from test_workload_api import SRC, keys  # noqa: E402,F401
from test_workload_create import _post, _review, make  # noqa: E402,F401
from test_workload_plans import Defined  # noqa: E402
from fabric_backend import lineage, server  # noqa: E402

ITEM = "22222222-3333-4444-5555-666666666666"                       # the Krusgraph Model item
OUTPUTS = [
    {"kind": "silver_notebook", "name": "shop_silver"},
    {"kind": "gold_views", "name": "shop_gold"},
    {"kind": "pipeline", "name": "shop_flow", "jobs": {"run_once": True}},
    {"kind": "semantic_model", "name": "n209_model"},
    {"kind": "graphql", "name": "n209_api"},
    {"kind": "ontology", "name": "shop_onto"},
]
WRITES = ("POST", "PATCH", "DELETE")


def _writes(fake) -> list:
    """Every call that writes (a getDefinition is a POST that only reads)."""
    return [c for c in fake.calls if c[0] in WRITES and not c[1].split("?")[0].endswith("/getDefinition")]


class Guids(Defined):
    """The build's workspace, giving every new item a GUID id as Fabric does (the page's routes accept only GUIDs)."""

    def _route(self, method, url, body=None):
        before = {it["id"] for it in self.items}
        r = super()._route(method, url, body)
        for it in self.items:
            if it["id"] not in before and not _is_guid(it["id"]):
                new = str(uuid.uuid4())
                if it["id"] in self.definitions:
                    self.definitions[new] = self.definitions.pop(it["id"])
                old, it["id"] = it["id"], new
                if isinstance(getattr(r, "_body", None), dict) and r._body.get("id") == old:
                    r._body["id"] = new
        return r


def _is_guid(x) -> bool:
    try:
        uuid.UUID(str(x))
        return True
    except ValueError:
        return False


def _definition(outputs: dict, source: dict) -> dict:
    parts = [{"path": k, "payload": base64.b64encode(json.dumps(v).encode()).decode(), "payloadType": "InlineBase64"}
             for k, v in (("source.json", source), ("outputs.json", outputs))]
    return {"definition": {"parts": parts}}


def test_review_dry_run_create_data_product_health_update_and_retire_agree(make, monkeypatch):
    client, fake, priv = make(Guids())

    # 1. the review
    rv = _review(client, priv)
    assert rv["plan_id"].startswith("plan-") and any(i["type"] == "relationship" for i in rv["items"])

    # 2. the dry run: every output is created, nothing is written
    fake.calls.clear()
    dry = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS, "dry_run": True, "product": {"name": "Shop sales"},
                                   "created": []}, priv).json()
    assert [c["decision"]["action"] for c in dry["outputs"]] == ["create"] * len(OUTPUTS), [c.get("decision") for c in dry["outputs"]]
    assert not _writes(fake), _writes(fake)
    assert {i["decision"] for i in dry["product"]["items"]} == {"create"}

    # 3. Create, one output at a time, the pipeline with Run once ticked
    created = []
    for o in OUTPUTS:
        card = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS, "only": [o["kind"]], "dry_run": False,
                                                    "product": None, "created": created, "skip_built": True}, priv).json()["outputs"][0]
        assert card["decision"]["action"] == "create" and card.get("created"), card
        if o["kind"] == "pipeline":                                 # n185: Run once asked; started or the permission it lacks
            assert card["jobs"]["run_once"] is True and ("run" in card["jobs"] or card["jobs"].get("permission")), card["jobs"]
        created += card["created"]
    assert all(_is_guid(c["id"]) for c in created), created
    plans = {c["plan"]["plan_id"] for c in created}
    assert plans == {rv["plan_id"]}, plans                         # n180: every item records the review's plan
    pipe = next(c for c in created if c["type"] == "DataPipeline")
    assert pipe["plan"]["plan_id"] == rv["plan_id"]

    # the dry run again predicts the second Create: everything is already built from this plan
    again = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS, "dry_run": True, "product": None,
                                     "created": created}, priv).json()
    assert [c["decision"]["action"] for c in again["outputs"]] == ["skip"] * len(OUTPUTS)

    outputs_json = {"created": created, "removed": [], "pending": [],
                    "product": {"name": "Shop sales", "owner": None, "plan": {"plan_id": rv["plan_id"],
                                                                               "schema_fingerprint": rv["schema_fingerprint"]}}}

    # 4. the Data product page: every item Create recorded is built
    st = _post(client, "/product", {"action": "status", "workspace": SRC["workspace"], "item_id": ITEM, "outputs": outputs_json,
                                    "product": "Shop sales", "plan_id": rv["plan_id"]}, priv)
    assert st.status_code == 200, st.text
    rows = st.json()["items"]
    assert {r["id"] for r in rows} == {c["id"] for c in created}
    assert {r["state"] for r in rows} == {"built"}, [(r["name"], r["state"], r.get("why")) for r in rows]

    # 5. health after two pipeline runs, asked as n198's page asks it ({workspace, item_id, product})
    source = {"version": 1, "platform": "fabric", "workspaceId": SRC["workspace"], "itemId": "lh-1", "itemType": "Lakehouse",
              "displayName": "demo_lh", "schema": "shop"}

    class R:
        def __init__(self, b):
            self._b = b

        def json(self):
            return self._b
    monkeypatch.setattr(lineage, "_definition_response", lambda url, headers: R(_definition(outputs_json, source)))
    lh = hc.shop()
    seen = {}

    def execute_factory(item, token):
        seen["item"] = item

        def execute(sql):
            if "INFORMATION_SCHEMA.TABLES" in sql:
                return [{"n": 1 if lh.exists("`krusgraph`.`health`") else 0}]
            return lh.execute(sql)
        return execute
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": "Lakehouse", "id": src, "displayName": src,
                                                                            "schemas_enabled": True})
    monkeypatch.setattr(server, "_execute_factory", execute_factory)
    body = {"workspace": SRC["workspace"], "item_id": ITEM, "product": "Shop sales"}
    first = _post(client, "/health", body, priv).json()
    assert first["word"] == "not checked yet", first
    mark = {"plan_id": rv["plan_id"], "schema_fingerprint": rv["schema_fingerprint"]}
    one_run(lh, run_id="run-1", mark=mark)
    one_run(lh, run_id="run-2", at=hc.NOW.replace(hour=7), mark=mark)
    out = _post(client, "/health", body, priv).json()
    assert out["word"] in ("green", "amber", "red"), out
    assert out["products"][0]["plan_id"] == rv["plan_id"] and out["products"][0]["run_id"] == "run-2", out["products"][0]
    assert seen["item"]["id"] == "lh-1"

    # 6. Update's dry run of the semantic model: a confirm, nothing written
    monkeypatch.undo()
    client, fake2, priv = make(fake)
    fake.calls.clear()
    upd = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS, "only": ["semantic_model"], "dry_run": True,
                                   "product": None, "created": created, "update": ["semantic_model"]}, priv).json()["outputs"][0]
    assert upd["decision"]["action"] == "update" and upd.get("confirm_update"), upd
    assert not _writes(fake), _writes(fake)

    # 7. Retire's dry run: exactly what Create recorded, nothing deleted
    fake.calls.clear()
    ret = _post(client, "/product", {"action": "retire", "scope": "delete", "workspace": SRC["workspace"], "item_id": ITEM,
                                     "outputs": outputs_json, "product": "Shop sales", "plan_id": rv["plan_id"]}, priv)
    assert ret.status_code == 200, ret.text
    got = ret.json()
    listed = got.get("items") or got.get("steps") or []
    assert {x["id"] for x in listed} == {c["id"] for c in created}, got
    assert not got["refused"], got["refused"]
    assert not _writes(fake), _writes(fake)
