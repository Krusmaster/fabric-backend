"""Round n198: the data product page's engine (fabric_backend/product_life.py, POST /workload/v1/product).

A fake Fabric workspace holds what a Krusgraph Model built, a lakehouse, a colleague's notebook, another Krusgraph Model
and a leftover (demo_lh_model4, made by Fabric after a timeout and never adopted). Checked: the state of every item;
Retire refuses anything outside outputs.json and never touches a lakehouse or a table; Delete needs the dry run's
confirmation and the data product's name typed; the schedule Krusgraph made is removed and no other; leftovers are found
by Krusgraph's plan marker, another Model's items are not leftovers, and adopt and delete work on leftovers only."""
from __future__ import annotations

import base64
import json

import pytest

pytest.importorskip("jwt")

from test_workload_api import FakeJWKS, FakeOBO, WL, keys, tok  # noqa: E402,F401
from fabric_backend import product_life as life, server, workload_api  # noqa: E402
from fabric_backend.entra import Validator  # noqa: E402

FABRIC_ORIGIN = "https://app.fabric.microsoft.com"
WS = "0f0f0f0f-0000-4000-8000-000000000001"
ME = "1a1a1a1a-0000-4000-8000-00000000000a"            # this Krusgraph Model
OTHER = "2b2b2b2b-0000-4000-8000-00000000000b"         # another Krusgraph Model in the workspace
PLAN = "plan-0123abcd"
MARK = f"[Krusgraph plan {PLAN}, schema shop (sha256:abcd), 7 links]"
OLD_MARK = "[Krusgraph plan plan-99999999, schema shop (sha256:ffff), 6 links]"


def gid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


LAKEHOUSE, SILVER, PIPE, MODEL, REPORT, AGENT, GONE, RENAMED = (gid(i) for i in range(1, 9))
COLLEAGUE, LEFTOVER, OLD_LEFTOVER, OTHERS_ITEM = gid(20), gid(21), gid(22), gid(23)
SCHED, FOREIGN_SCHED = "5c5c5c5c-0000-4000-8000-000000000001", "5c5c5c5c-0000-4000-8000-000000000002"


def created(i, typ, name, output, **kw):
    return {"id": i, "type": typ, "name": name, "workspace": WS, "output": output, "plan": {"plan_id": PLAN}, **kw}


OUTPUTS = {
    "created": [created(SILVER, "Notebook", "silver_shop", "silver_notebook"),
                created(PIPE, "DataPipeline", "demo_lh_pipeline", "pipeline"),
                created(MODEL, "SemanticModel", "demo_lh_model", "semantic_model"),
                created(REPORT, "Report", "demo_lh_report", "report"),
                created(AGENT, "DataAgent", "demo_lh_agent", "data_agent", published=True),
                created(GONE, "GraphQLApi", "demo_lh_api", "graphql"),
                created(RENAMED, "Ontology", "demo_lh_ontology", "ontology"),
                # a lakehouse slipped into outputs.json (hand-edited, or a bug): never deleted
                created(LAKEHOUSE, "Lakehouse", "demo_lh", "silver_notebook")],
    "pending": [{"output": "rayfin_app", "type": "AppBackend", "name": "demo_lh_app", "at": "2026-11-10T09:00:00Z"}],
    "pipeline_jobs": {"runs": [], "schedules": [{"id": SCHED, "pipeline_id": PIPE, "pipeline": "demo_lh_pipeline", "workspace": WS,
                                                 "every": "day", "at": "06:00", "recorded": "2026-11-10"}]},
}


def other_definition():
    out = {"version": 1, "created": [{"id": OTHERS_ITEM, "type": "Notebook", "name": "theirs_silver", "workspace": WS}]}
    return [{"path": "outputs.json", "payload": base64.b64encode(json.dumps(out).encode()).decode(), "payloadType": "InlineBase64"}]


class Response:
    def __init__(self, status, body=None):
        self.status_code, self._body, self.headers = status, body, {}

    def json(self):
        return self._body if self._body is not None else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Fabric:
    """The workspace: List Items, Get Item Definition of the other Model, Delete Item, Delete schedule. Records calls."""

    def __init__(self, other_readable=True):
        self.calls = []
        self.other_readable = other_readable
        self.items = {
            LAKEHOUSE: {"type": "Lakehouse", "displayName": "demo_lh", "description": ""},
            SILVER: {"type": "Notebook", "displayName": "silver_shop", "description": f"Silver tables, made by Krusgraph. {MARK}"},
            PIPE: {"type": "DataPipeline", "displayName": "demo_lh_pipeline", "description": f"[Krusgraph schedule {SCHED}] Krusgraph pipeline {MARK}"},
            MODEL: {"type": "SemanticModel", "displayName": "demo_lh_model", "description": f"Created by Krusgraph {MARK}"},
            REPORT: {"type": "Report", "displayName": "demo_lh_report", "description": f"Created by Krusgraph {MARK}"},
            AGENT: {"type": "DataAgent", "displayName": "demo_lh_agent", "description": f"Created by Krusgraph {MARK}"},
            RENAMED: {"type": "Ontology", "displayName": "sales_ontology", "description": f"Created by Krusgraph {MARK}"},
            COLLEAGUE: {"type": "Notebook", "displayName": "colleague_nb", "description": "Anna's notebook"},
            LEFTOVER: {"type": "SemanticModel", "displayName": "demo_lh_model4", "description": f"Created by Krusgraph {MARK}"},
            OLD_LEFTOVER: {"type": "Report", "displayName": "old_report", "description": f"Created by Krusgraph {OLD_MARK}"},
            OTHERS_ITEM: {"type": "Notebook", "displayName": "theirs_silver", "description": f"Created by Krusgraph {MARK}"},
            ME: {"type": "Org.Krusgraph.Model", "displayName": "demo_model", "description": ""},
            OTHER: {"type": "Org.Krusgraph.Model", "displayName": "their_model", "description": ""},
        }

    def __call__(self, method, url, **kw):
        self.calls.append((method.upper(), url))
        path = url.split("api.fabric.microsoft.com")[-1].split("?")[0]
        if method == "get" and path == f"/v1/workspaces/{WS}/items":
            return Response(200, {"value": [{"id": i, **it} for i, it in self.items.items()]})
        if method == "get" and path == f"/v1/workspaces/{WS}/roleAssignments":
            return Response(200, {"value": [
                {"id": "a1", "role": "Admin", "principal": {"id": "u1", "displayName": "Anna Berg", "type": "User",
                                                             "userDetails": {"userPrincipalName": "anna@example.com"}}},
                {"id": "a2", "role": "Member", "principal": {"id": "g1", "displayName": "Sales team", "type": "Group"}},
                {"id": "a3", "role": "Contributor", "principal": {"id": "s1", "displayName": "a robot", "type": "ServicePrincipal"}}]})
        if method == "post" and path.endswith("/getDefinition"):
            if OTHER in path and self.other_readable:
                return Response(200, {"definition": {"parts": other_definition()}})
            return Response(403, {"message": "no access"})
        if method == "delete" and "/schedules/" in path:
            return Response(200)
        if method == "delete" and path.startswith(f"/v1/workspaces/{WS}/items/"):
            iid = path.rsplit("/", 1)[-1]
            return Response(200) if self.items.pop(iid, None) else Response(404, {"message": "ItemNotFound"})
        return Response(404, {"message": f"not faked: {method} {path}"})

    def writes(self):
        return [c for c in self.calls if c[0] in ("DELETE", "PATCH", "PUT") or (c[0] == "POST" and not c[1].endswith("getDefinition"))]


def read_definition(fake):
    def read(ws, iid):
        r = fake("post", f"{life.FABRIC}/v1/workspaces/{ws}/items/{iid}/getDefinition")
        if r.status_code >= 400:
            raise RuntimeError("unreadable")
        return r.json()["definition"]["parts"]
    return read


def listings(fake):
    return {WS: life.list_items(fake, WS)}


# ------------------------------------------------------------------ status ---------------------------------------------

def test_every_item_gets_its_state_in_words():
    fake = Fabric()
    rows = {r["name"]: r for r in life.status(OUTPUTS, listings(fake))}
    assert rows["silver_shop"]["state"] == "built" and rows["demo_lh_model"]["state"] == "built"
    assert rows["demo_lh_api"]["state"] == "missing" and "does not list it" in rows["demo_lh_api"]["why"]
    assert rows["demo_lh_ontology"]["state"] == "changed_outside" and "sales_ontology" in rows["demo_lh_ontology"]["why"]
    assert rows["demo_lh_app"]["state"] == "pending"
    for r in rows.values():
        assert r["words"] == life.WORDS[r["state"]]                    # every state also in words, never colour alone
    assert fake.writes() == []


def test_a_description_naming_another_plan_is_changed_outside():
    fake = Fabric()
    fake.items[MODEL]["description"] = f"Created by Krusgraph {OLD_MARK}"
    rows = {r["name"]: r for r in life.status(OUTPUTS, listings(fake))}
    assert rows["demo_lh_model"]["state"] == "changed_outside" and "plan-99999999" in rows["demo_lh_model"]["why"]


def test_removed_items_are_not_listed_as_built():
    out = {**OUTPUTS, "removed": [{"id": REPORT, "removed_at": "2026-11-11T10:00:00+00:00", "by": "Anna"}]}
    assert REPORT not in {r["id"] for r in life.status(out, listings(Fabric()))}


# ------------------------------------------------------------------ retire -----------------------------------------------

def req(**kw):
    return {"scope": "delete", "items": None, "dry_run": True, "product": "Shop sales", "outputs": OUTPUTS, "by": "Anna", **kw}


def test_the_delete_dry_run_lists_exactly_what_goes_and_refuses_the_rest():
    fake = Fabric()
    got = life.retire(fake, req(), listings(fake))
    names = [x["name"] for x in got["items"]]
    assert names == ["demo_lh_report", "demo_lh_agent", "demo_lh_ontology", "demo_lh_model", "demo_lh_pipeline", "silver_shop"]
    refused = {x["id"]: x["why"] for x in got["refused"]}
    assert "never deletes a Lakehouse" in refused[LAKEHOUSE]
    assert "Already gone" in refused[GONE]
    assert got["confirm"].startswith("ret-") and "lakehouse" in got["keeps"]
    assert fake.writes() == []                                          # a dry run writes nothing


def test_retire_refuses_anything_outside_outputs_json():
    fake = Fabric()
    got = life.retire(fake, req(items=[COLLEAGUE, LEFTOVER, LAKEHOUSE]), listings(fake))
    assert got["items"] == [] and got["confirm"] is None
    assert {x["id"] for x in got["refused"]} == {COLLEAGUE, LEFTOVER, LAKEHOUSE}
    with pytest.raises(life.Refused):
        life.retire(fake, req(items=[COLLEAGUE], dry_run=False, confirm=life.confirm_token("delete", [COLLEAGUE], "Shop sales"),
                              typed_name="Shop sales"), listings(fake))
    assert fake.writes() == []


def test_an_item_fabric_lists_as_a_lakehouse_is_never_deleted_even_if_recorded_as_a_notebook():
    fake = Fabric()
    fake.items[SILVER]["type"] = "Lakehouse"
    got = life.retire(fake, req(items=[SILVER]), listings(fake))
    assert got["items"] == [] and "never deletes" in got["refused"][0]["why"]


def test_delete_needs_the_typed_name_and_the_dry_runs_confirmation():
    fake = Fabric()
    dry = life.retire(fake, req(items=[REPORT, MODEL]), listings(fake))
    for wrong in ("", "shop sales", "Shop", None):
        with pytest.raises(life.Refused, match="Type the data product's name"):
            life.retire(fake, req(items=[REPORT, MODEL], dry_run=False, confirm=dry["confirm"], typed_name=wrong), listings(fake))
    with pytest.raises(life.Refused, match="not the one the dry run showed"):
        life.retire(fake, req(items=[REPORT, MODEL, PIPE], dry_run=False, confirm=dry["confirm"], typed_name="Shop sales"), listings(fake))
    assert fake.writes() == []
    got = life.retire(fake, req(items=[REPORT, MODEL], dry_run=False, confirm=dry["confirm"], typed_name="  Shop sales "), listings(fake))
    deletes = [u for m, u in fake.writes()]
    assert deletes == [f"{life.FABRIC}/v1/workspaces/{WS}/items/{REPORT}", f"{life.FABRIC}/v1/workspaces/{WS}/items/{MODEL}"]
    assert all("hardDelete" not in u for u in deletes)
    assert [x["result"] for x in got["results"]] == ["deleted", "deleted"]
    assert {r["id"] for r in got["removed"]} == {REPORT, MODEL}
    assert all(r["by"] == "Anna" and r["removed_at"] for r in got["removed"])


def test_a_failed_delete_says_why_and_is_not_recorded_as_removed():
    fake = Fabric()
    real = fake.__call__

    def refuse(method, url, **kw):
        if method == "delete" and MODEL in url:
            fake.calls.append(("DELETE", url))
            return Response(403, {"message": "InsufficientPrivileges"})
        return real(method, url, **kw)
    dry = life.retire(fake, req(items=[MODEL]), listings(fake))
    got = life.retire(refuse, req(items=[MODEL], dry_run=False, confirm=dry["confirm"], typed_name="Shop sales"), listings(fake))
    assert got["results"][0]["result"] == "failed" and "Item.ReadWrite.All" in got["results"][0]["why"]
    assert got["removed"] == []


def test_soft_retire_removes_only_the_schedule_krusgraph_made_and_names_the_agent_step():
    fake = Fabric()
    dry = life.retire(fake, req(scope="soft"), listings(fake))
    acts = [(s["action"], s.get("schedule_id"), s["name"]) for s in dry["steps"]]
    assert ("remove_schedule", SCHED, "demo_lh_pipeline") in acts
    assert not any(s.get("schedule_id") == FOREIGN_SCHED for s in dry["steps"])
    assert any(a == "manual" and n == "demo_lh_agent" for a, _, n in acts)
    assert "no API to unpublish" in next(s["words"] for s in dry["steps"] if s["action"] == "manual")
    assert fake.writes() == []
    got = life.retire(fake, req(scope="soft", dry_run=False, confirm=dry["confirm"]), listings(fake))
    assert fake.writes() == [("DELETE", f"{life.FABRIC}/v1/workspaces/{WS}/dataPipelines/{PIPE}/jobs/execute/schedules/{SCHED}")]
    assert PIPE in fake.items                                            # soft deletes nothing
    assert any(s["result"] == "done" for s in got["steps"])


# ------------------------------------------------------------------ leftovers ---------------------------------------------

def test_leftovers_are_found_by_the_marker_and_another_models_items_are_not_leftovers():
    fake = Fabric()
    got = life.leftovers(fake, WS, OUTPUTS, ME, PLAN, read_definition(fake))
    found = {x["name"]: x for x in got["leftovers"]}
    assert set(found) == {"demo_lh_model4", "old_report"}                # not the colleague's, not the other Model's, not ours
    assert found["demo_lh_model4"]["adopt_ok"] and found["demo_lh_model4"]["delete_ok"]
    assert not found["old_report"]["adopt_ok"] and found["old_report"]["delete_ok"]
    assert got["unread_models"] == []
    assert fake.writes() == []


def test_an_unreadable_model_blocks_deleting_leftovers():
    fake = Fabric(other_readable=False)
    got = life.leftovers(fake, WS, OUTPUTS, ME, PLAN, read_definition(fake))
    assert got["unread_models"] == ["their_model"]
    assert {x["name"] for x in got["leftovers"]} >= {"demo_lh_model4", "theirs_silver"}
    assert not any(x["delete_ok"] for x in got["leftovers"])
    with pytest.raises(life.Refused):
        life.retire(fake, req(items=[LEFTOVER], leftovers=True, dry_run=False, typed_name="Shop sales",
                              confirm=life.confirm_token("delete:leftovers", [], "Shop sales")), listings(fake), got)
    assert fake.writes() == []


def test_adopt_takes_a_leftover_of_this_plan_only():
    fake = Fabric()
    lefts = life.leftovers(fake, WS, OUTPUTS, ME, PLAN, read_definition(fake))
    got = life.adopt(lefts, [LEFTOVER, OLD_LEFTOVER, COLLEAGUE], "Anna")
    assert [a["name"] for a in got["adopted"]] == ["demo_lh_model4"]
    a = got["adopted"][0]
    assert a["output"] == "semantic_model" and a["plan"]["plan_id"] == PLAN and a["adopted_by"] == "Anna"
    assert {r["id"] for r in got["refused"]} == {OLD_LEFTOVER, COLLEAGUE}
    assert fake.writes() == []


def test_deleting_leftovers_is_the_same_dry_run_and_typed_name():
    fake = Fabric()
    lefts = life.leftovers(fake, WS, OUTPUTS, ME, PLAN, read_definition(fake))
    dry = life.retire(fake, req(items=[LEFTOVER, COLLEAGUE, OTHERS_ITEM], leftovers=True), listings(fake), lefts)
    assert [x["name"] for x in dry["items"]] == ["demo_lh_model4"]
    assert {x["id"] for x in dry["refused"]} == {COLLEAGUE, OTHERS_ITEM}
    with pytest.raises(life.Refused):
        life.retire(fake, req(items=[LEFTOVER], leftovers=True, dry_run=False, confirm=dry["confirm"], typed_name="nope"), listings(fake), lefts)
    # the dry run had two refused ids; the confirmation covers what goes, so sending only the leftover is the same list
    got = life.retire(fake, req(items=[LEFTOVER], leftovers=True, dry_run=False, confirm=dry["confirm"], typed_name="Shop sales"),
                      listings(fake), lefts)
    assert [x["result"] for x in got["results"]] == ["deleted"]
    assert fake.writes() == [("DELETE", f"{life.FABRIC}/v1/workspaces/{WS}/items/{LEFTOVER}")]
    with pytest.raises(life.Refused, match="Adopt or Delete"):
        life.retire(fake, req(scope="soft", items=[OLD_LEFTOVER], leftovers=True), listings(fake), lefts)


# ------------------------------------------------------------------ the route ---------------------------------------------

@pytest.fixture
def client(keys, monkeypatch):
    import requests
    from starlette.applications import Starlette
    from starlette.testclient import TestClient
    priv, pub = keys
    fake = Fabric()
    for verb in ("get", "post", "patch", "delete", "put"):
        monkeypatch.setattr(requests, verb, lambda url, _v=verb, **kw: fake(_v, url, **kw))
    monkeypatch.setattr(server, "limiter", None)
    app = Starlette(routes=workload_api.routes(WL, Validator(WL, FakeJWKS(pub)), FakeOBO()))
    return TestClient(app, raise_server_exceptions=False), fake, priv


def post(c, priv, body):
    return c.post(workload_api.PREFIX + "/product", json=body,
                  headers={"Authorization": f"Bearer {tok(priv)}", "Origin": FABRIC_ORIGIN})


BASE = {"workspace": WS, "item_id": ME, "outputs": OUTPUTS, "product": "Shop sales", "plan_id": PLAN}


def test_the_route_answers_status_leftovers_and_a_delete_dry_run(client):
    c, fake, priv = client
    r = post(c, priv, {**BASE, "action": "status"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == FABRIC_ORIGIN
    assert {x["state"] for x in r.json()["items"]} == {"built", "missing", "changed_outside", "pending"}
    assert [p["name"] for p in r.json()["people"]] == ["Anna Berg", "Sales team"]     # people and groups, no service principal
    r = post(c, priv, {**BASE, "action": "leftovers"})
    assert {x["name"] for x in r.json()["leftovers"]} == {"demo_lh_model4", "old_report"}
    r = post(c, priv, {**BASE, "action": "retire", "scope": "delete"})
    assert r.status_code == 200 and r.json()["dry_run"] and r.json()["items"]
    r = post(c, priv, {**BASE, "action": "retire", "scope": "delete", "dry_run": False, "confirm": r.json()["confirm"], "typed_name": "wrong"})
    assert r.status_code == 400 and "Type the data product's name" in r.json()["error"]
    assert fake.writes() == []


def test_the_route_refuses_bad_bodies(client):
    c, _, priv = client
    for body, word in (({**BASE, "action": "drop"}, "action"), ({**BASE, "action": "status", "workspace": "x"}, "workspace"),
                       ({**BASE, "action": "retire"}, "scope"), ({**BASE, "action": "adopt"}, "items"),
                       ({**BASE, "action": "retire", "scope": "delete", "leftovers": True}, "leftovers"),
                       ({**BASE, "action": "status", "product": ""}, "product")):
        r = post(c, priv, body)
        assert r.status_code == 400 and word in r.json()["error"], (body, r.json())


def test_the_route_records_who_adopted(client):
    c, _, priv = client
    r = post(c, priv, {**BASE, "action": "adopt", "items": [LEFTOVER]})
    assert r.status_code == 200
    assert r.json()["adopted"][0]["name"] == "demo_lh_model4" and "adopted_by" in r.json()["adopted"][0]
