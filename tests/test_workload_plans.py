"""Round n180: "already built" means built from this plan, after the founder's live re-run of 9 November 2026, 12:14 CET.

The re-run (schema shop, 7 links) showed seven items built that morning from schema "Shop" with 6 links as "already
built", with "0 silver table(s)", "0 visual(s)" and "0 table(s) selected" on their cards. Now:

- every item a Create writes records the plan it was built from: outputs.json's created[].plan, and a marker at the end
  of its Fabric description (workload_api.mark_text);
- a re-run skips an output only when its items were built from this same plan; an item built from another plan (other
  schema spelling, other links) or with no plan recorded gets a card that says so, with Update (only where the tool
  updates in place) or a new name, and nothing is written for it;
- Update is a dry run first: its card gives confirm_update, and the Create that updates must send it back;
- an existing item's card shows what the item holds where its definition says it (cells, views, pages, visuals,
  example questions), and no count at all where nothing was read: never a zero for an item that has them.
Fabric REST and the SQL endpoint are the doubles of tests/golden_support.py, with definitions kept for each item."""
import base64
import json

import pytest

pytest.importorskip("jwt")

import golden_support as gs  # noqa: E402
from test_workload_api import SRC, keys, tok  # noqa: E402,F401
from test_workload_create import Workspace, _one, _post, _review, make  # noqa: E402,F401
from fabric_backend import notebook, workload_api  # noqa: E402

OLD = "[Krusgraph plan plan-0123456789ab, schema Shop (sha256:00112233aabbccdd), 6 links]"


def _parts(files: dict[str, str]) -> list[dict]:
    return [{"path": p, "payload": base64.b64encode(t.encode()).decode(), "payloadType": "InlineBase64"} for p, t in files.items()]


def _notebook(cells: int, views: int = 0) -> list[dict]:
    code = [("code", f"spark.sql('CREATE OR REPLACE MATERIALIZED LAKE VIEW gold.v{i} AS SELECT 1')") for i in range(views)]
    code += [("code", f"print({i})") for i in range(cells - views)]
    return _parts({"notebook-content.py": notebook.fabric_source(code, notebook.notebook_metadata())})


def _report(pages: int, visuals: int) -> list[dict]:
    files = {"definition/report.json": "{}"}
    for p in range(pages):
        files[f"definition/pages/p{p}/page.json"] = "{}"
        for v in range(visuals):
            files[f"definition/pages/p{p}/visuals/v{v}/visual.json"] = "{}"
    return _parts(files)


class Defined(Workspace):
    """The build's workspace, where every item keeps its definition (getDefinition answers it), a description can be
    changed (PATCH items/{id}), and a data agent answers its staging data sources and example questions."""

    def __init__(self, items=(), definitions=None, agent_questions=0):
        super().__init__(items=items)
        self.definitions = dict(definitions or {})
        self.agent_questions = agent_questions
        self.patches: list[tuple[str, dict]] = []

    def _route(self, method, url, body=None):
        path = url.split("?")[0]
        rest = path.split(f"/workspaces/{gs.WS}/")[-1].split("/") if f"/workspaces/{gs.WS}/" in path else []
        if method == "POST" and len(rest) == 3 and rest[0] == "items" and rest[2] == "getDefinition" and rest[1] in self.definitions:
            self.calls.append((method, path))
            return gs.Response(200, {"definition": {"parts": self.definitions[rest[1]]}})
        if method == "PATCH" and len(rest) == 2 and rest[0] == "items":
            self.calls.append((method, path))
            self.patches.append((rest[1], body))
            for it in self.items:
                if it["id"] == rest[1]:
                    it["description"] = body["description"]
            return gs.Response(200, {"id": rest[1], **body})
        if method == "GET" and len(rest) == 2 and rest[0] == "items" and any(i["id"] == rest[1] for i in self.items):
            self.calls.append((method, path))
            return gs.Response(200, next(i for i in self.items if i["id"] == rest[1]))
        if method == "GET" and rest[:1] == ["dataAgents"] and rest[-1] == "datasources":
            return gs.Response(200, {"value": [{"id": "ds-1", "type": "LakehouseTables"}]})
        if method == "GET" and rest[:1] == ["dataAgents"] and rest[-1] == "fewshots":
            return gs.Response(200, {"value": [{"id": f"q{i}", "question": f"q{i}"} for i in range(self.agent_questions)]})
        r = super()._route(method, url, body)
        if method == "POST" and r.status_code == 201 and isinstance(body, dict) and body.get("definition"):
            self.definitions[r.json()["id"]] = body["definition"]["parts"]
        return r


def _writes(fake):
    return [c for c in fake.calls if c[0] in ("POST", "PATCH") and not c[1].endswith("/getDefinition")]


SILVER = {"kind": "silver_notebook", "name": "demo_lh_silver"}


# ------------------------------------------------------------------ the plan is recorded -----------------------------

def test_create_records_the_plan_in_outputs_json_and_in_the_items_description(make):
    client, fake, priv = make(Defined())
    rv = _review(client, priv)
    out = _one(client, priv, rv, SILVER).json()
    made = out["created"][0]
    assert made["plan"]["plan_id"] == rv["plan_id"] and made["plan"]["schema_fingerprint"] == rv["schema_fingerprint"]
    assert made["plan"]["schema"] == "shop" and made["plan"]["links"] > 0
    item = next(i for i in fake.items if i["id"] == made["id"])
    assert workload_api.mark_of_description(item["description"]) == made["plan"]
    assert "krusgraph" in item["description"].lower() and len(item["description"]) <= 256


def test_the_marker_fits_256_characters_and_replaces_an_older_one():
    mark = {"plan_id": "plan-abcdefabcdef", "schema": "shop", "schema_fingerprint": "sha256:0011223344556677", "links": 7}
    d = workload_api.with_mark("x" * 300 + " " + OLD, mark)
    assert len(d) <= 256 and d.endswith(workload_api.mark_text(mark)) and "plan-0123456789ab" not in d
    assert workload_api.mark_of_description(d) == mark
    assert workload_api.mark_of_description(OLD) == {"plan_id": "plan-0123456789ab", "schema": "Shop",
                                                     "schema_fingerprint": "sha256:00112233aabbccdd", "links": 6}


# ------------------------------------------------------------------ same plan, different plan, unknown plan ---------

def test_a_rerun_with_the_same_plan_is_already_built_with_what_the_item_holds(make):
    client, fake, priv = make(Defined())
    rv = _review(client, priv)
    created = _one(client, priv, rv, SILVER).json()["created"]
    fake.calls.clear()
    card = _one(client, priv, rv, SILVER, created).json()["outputs"][0]
    assert card["already_built"] is True and not card.get("built_from") and card["created"][0]["id"] == created[0]["id"]
    assert card["existing"]["cells"] > 0 and 0 not in card["existing"].values()
    assert _writes(fake) == []


def test_the_same_plan_is_recognised_from_the_description_when_outputs_json_lost_the_ids(make):
    """A Create whose answer the browser lost: the item carries this plan's marker, outputs.json has nothing."""
    client, fake, priv = make(Defined())
    rv = _review(client, priv)
    _one(client, priv, rv, SILVER)
    fake.calls.clear()
    card = _one(client, priv, rv, SILVER, created=[]).json()["outputs"][0]
    assert card["already_built"] is True and _writes(fake) == []


def test_an_item_built_from_another_plan_gets_a_card_with_update_or_a_new_name_and_nothing_is_written(make):
    """The live case: built in the morning from schema 'Shop' with 6 links; the plan is now shop with 7 links."""
    old = [{"id": "nb-old", "displayName": "demo_lh_silver", "type": "Notebook",
            "description": "Silver tables for demo_lh.Shop, generated by Krusgraph from the plan " + OLD}]
    client, fake, priv = make(Defined(items=old, definitions={"nb-old": _notebook(9)}))
    rv = _review(client, priv)
    fake.calls.clear()
    out = _one(client, priv, rv, SILVER).json()
    card = out["outputs"][0]
    now = card["built_from"]["now"]
    assert not card.get("already_built") and not card.get("created") and out["created"] == []
    assert card["built_from"]["status"] == "different" and card["built_from"]["was"]["schema"] == "Shop"
    assert card["built_from"]["words"] == f"built from a different plan (schema Shop, 6 links; now shop, {now['links']} links)"
    assert card["choices"] == ["update", "new_name"] and card["existing_items"][0]["id"] == "nb-old"
    assert card["existing"] == {"cells": 9}
    assert out["to_decide"] == 1 and "wait for your choice" in out["note"]
    assert _writes(fake) == []


def test_a_plan_recorded_in_outputs_json_counts_too(make):
    client, fake, priv = make(Defined())
    rv = _review(client, priv)
    created = _one(client, priv, rv, SILVER).json()["created"]
    old = [{**c, "plan": {**c["plan"], "links": c["plan"]["links"] - 1, "plan_id": "plan-ffffffffffff"}} for c in created]
    for it in fake.items:                                           # the description says nothing about a plan
        it["description"] = "generated by Krusgraph"
    card = _one(client, priv, rv, SILVER, old).json()["outputs"][0]
    assert card["built_from"]["status"] == "different" and card["built_from"]["was"]["plan_id"] == "plan-ffffffffffff"


def test_an_item_from_before_plans_were_recorded_is_plan_unknown(make):
    lost = [{"id": "nb-silver", "displayName": "demo_lh_silver", "type": "Notebook",
             "description": "Silver tables for demo_lh.shop, generated by Krusgraph from the plan"}]
    client, fake, priv = make(Defined(items=lost))
    rv = _review(client, priv)
    fake.calls.clear()
    card = _one(client, priv, rv, SILVER).json()["outputs"][0]
    assert card["built_from"]["status"] == "unknown" and card["built_from"]["was"] is None
    assert card["built_from"]["words"].startswith("built by Krusgraph, plan unknown (now shop, ")
    assert card["choices"] == ["update", "new_name"]
    assert card["existing"] == {}                                   # its definition could not be read: no counts, not zeros
    assert _writes(fake) == []


def test_a_report_from_another_plan_offers_only_a_new_name_with_its_pages_and_visuals(make):
    old = [{"id": "rep-old", "displayName": "demo_lh_report", "type": "Report", "description": "Created by Krusgraph " + OLD}]
    client, fake, priv = make(Defined(items=old, definitions={"rep-old": _report(1, 6)}))
    rv = _review(client, priv)
    card = _one(client, priv, rv, {"kind": "report", "name": "demo_lh_report", "model": "shop_model"}).json()["outputs"][0]
    assert card["choices"] == ["new_name"] and card["existing"] == {"pages": 1, "visuals": 6}
    r = _post(client, "/build", {**SRC, "review": rv, "outputs": [{"kind": "report", "name": "demo_lh_report", "model": "shop_model"}],
                                 "dry_run": True, "update": ["report"]}, priv)
    assert r.status_code == 400 and "never updated" in r.json()["error"]


def test_a_data_agent_shows_its_example_questions_and_no_zero_tables(make):
    old = [{"id": "ag-old", "displayName": "demo_lh_agent", "type": "DataAgent", "description": "Created by Krusgraph " + OLD}]
    client, fake, priv = make(Defined(items=old, agent_questions=4))
    rv = _review(client, priv)
    card = _one(client, priv, rv, {"kind": "data_agent", "name": "demo_lh_agent"}).json()["outputs"][0]
    assert card["existing"] == {"data_sources": 1, "questions": 4}


# ------------------------------------------------------------------ Update: the dry run first ------------------------

def test_update_is_a_dry_run_first_and_writes_only_with_its_confirmation(make):
    old = [{"id": "nb-old", "displayName": "demo_lh_silver", "type": "Notebook", "description": "generated by Krusgraph " + OLD}]
    client, fake, priv = make(Defined(items=old, definitions={"nb-old": _notebook(9)}))
    rv = _review(client, priv)
    fake.calls.clear()
    dry = _one(client, priv, rv, SILVER, dry_run=True, update=["silver_notebook"]).json()["outputs"][0]
    assert dry["dry_run"] is True and dry["would"] == "update" and not dry.get("refusal"), dry
    assert dry["built_from"]["status"] == "different" and dry["confirm_update"].startswith("upd-")
    assert _writes(fake) == []

    unconfirmed = _one(client, priv, rv, SILVER, update=["silver_notebook"]).json()["outputs"][0]
    assert unconfirmed["refusal"]["kind"] == "dry_run_first" and _writes(fake) == []

    out = _one(client, priv, rv, SILVER, update=["silver_notebook"], confirm={"silver_notebook": dry["confirm_update"]}).json()
    card = out["outputs"][0]
    assert not card.get("refusal") and card["would"] == "update" and "error" not in card["answer"], card
    assert any(c[1].endswith("/updateDefinition") for c in _writes(fake))
    assert card["created"][0]["id"] == "nb-old" and card["created"][0]["plan"]["schema"] == "shop"
    marked = workload_api.mark_of_description(next(i for i in fake.items if i["id"] == "nb-old")["description"])
    assert marked == card["created"][0]["plan"]

    fake.calls.clear()                                              # and now it is built from this plan
    again = _one(client, priv, rv, SILVER, out["created"]).json()["outputs"][0]
    assert again["already_built"] is True and _writes(fake) == []


def test_someone_elses_item_is_not_updated_even_when_update_is_asked(make):
    theirs = [{"id": "nb-x", "displayName": "demo_lh_silver", "type": "Notebook", "description": "my own notebook"}]
    client, fake, priv = make(Defined(items=theirs))
    rv = _review(client, priv)
    card = _one(client, priv, rv, SILVER, dry_run=True, update=["silver_notebook"]).json()["outputs"][0]
    assert card["refusal"]["kind"] == "already_exists"


def test_the_round_trip_keeps_the_plan_of_created_items():
    req = workload_api.build_request({**SRC, "review": {}, "outputs": [SILVER], "created": [
        {"type": "Notebook", "id": "a", "name": "n", "workspace": gs.WS, "output": "silver_notebook", "plan": {"plan_id": "plan-1"}},
        {"type": "Notebook", "id": "b", "name": "m", "workspace": gs.WS, "plan": "not a plan"}]})
    assert req["created"][0]["plan"] == {"plan_id": "plan-1"} and "plan" not in req["created"][1]
    assert json.dumps(req)
