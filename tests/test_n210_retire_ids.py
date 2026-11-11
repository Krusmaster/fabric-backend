"""n210: Turn off (the soft retire of n198) removes only schedules whose ids are GUIDs. A schedule id from outputs.json goes
into a DELETE path; '../../items/<id>?hardDelete=true' would otherwise be normalised by requests into a hard delete of any
item (a lakehouse among them) while the dry run says only 'Remove the schedule'. Fake HTTP; nothing calls Fabric."""
from __future__ import annotations

import pytest

pytest.importorskip("jwt")

from test_n198_product_page import (BASE, FABRIC_ORIGIN, LAKEHOUSE, OUTPUTS, PIPE, SCHED, WS, Fabric, client, listings,  # noqa: E402,F401
                                    req, tok)
from test_workload_api import keys  # noqa: E402,F401
from fabric_backend import product_life as life, workload_api  # noqa: E402

EVIL = f"../../../../../items/{LAKEHOUSE}?hardDelete=true"


def with_schedule(sid: str, pipeline: str = PIPE) -> dict:
    jobs = {"runs": [], "schedules": [{"id": sid, "pipeline_id": pipeline, "pipeline": "demo_lh_pipeline", "workspace": WS,
                                       "every": "day"}]}
    return {**OUTPUTS, "pipeline_jobs": jobs}


def test_requests_would_turn_a_path_in_a_schedule_id_into_another_delete():
    """Why the check exists: requests removes dot segments, so the id walks out of /schedules/."""
    import requests
    url = f"{life.FABRIC}/v1/workspaces/{WS}/dataPipelines/{PIPE}/jobs/execute/schedules/{EVIL}"
    assert requests.Request("DELETE", url).prepare().url == f"{life.FABRIC}/v1/workspaces/{WS}/items/{LAKEHOUSE}?hardDelete=true"


@pytest.mark.parametrize("sid", [EVIL, "..", "abc", f"{SCHED}/../x", ""])
def test_turn_off_never_uses_a_schedule_id_that_is_not_a_guid(sid):
    fake = Fabric()
    dry = life.retire(fake, req(scope="soft", outputs=with_schedule(sid)), listings(fake))
    assert not [s for s in dry["steps"] if s["action"] == "remove_schedule" and s.get("schedule_id") == sid]
    life.retire(fake, req(scope="soft", outputs=with_schedule(sid), dry_run=False, confirm=dry["confirm"]), listings(fake))
    assert all("/schedules/" in url and url.rsplit("/", 1)[1] != sid for _, url in fake.writes()), fake.writes()
    assert not any("hardDelete" in url or url.endswith(f"/items/{LAKEHOUSE}") for _, url in fake.writes())


def test_a_guid_schedule_is_still_removed():
    fake = Fabric()
    dry = life.retire(fake, req(scope="soft", outputs=with_schedule(SCHED)), listings(fake))
    life.retire(fake, req(scope="soft", outputs=with_schedule(SCHED), dry_run=False, confirm=dry["confirm"]), listings(fake))
    assert fake.writes() == [("DELETE", f"{life.FABRIC}/v1/workspaces/{WS}/dataPipelines/{PIPE}/jobs/execute/schedules/{SCHED}")]


def test_the_route_leaves_out_a_schedule_whose_ids_are_not_guids(client):
    c, fake, priv = client
    body = {**BASE, "outputs": with_schedule(EVIL), "action": "retire", "scope": "soft"}
    r = c.post(workload_api.PREFIX + "/product", json=body, headers={"Authorization": f"Bearer {tok(priv)}", "Origin": FABRIC_ORIGIN})
    assert r.status_code == 200, r.text
    assert not [s for s in r.json()["steps"] if s.get("schedule_id") == EVIL]
    r = c.post(workload_api.PREFIX + "/product", json={**body, "dry_run": False, "confirm": r.json()["confirm"]},
               headers={"Authorization": f"Bearer {tok(priv)}", "Origin": FABRIC_ORIGIN})
    assert r.status_code == 200, r.text
    assert all(f"/dataPipelines/{PIPE}/jobs/execute/schedules/" in url and "hardDelete" not in url for _, url in fake.writes())
    assert LAKEHOUSE in fake.items


def test_delete_from_fabric_leaves_an_item_recorded_in_another_workspace_alone():
    other_ws = "0f0f0f0f-0000-4000-8000-0000000000ff"
    fake = Fabric()
    planted = {"id": "00000000-0000-4000-8000-000000000099", "type": "Report", "name": "someone_elses", "workspace": other_ws,
               "output": "report", "plan": {}}
    outputs = {**OUTPUTS, "created": [*OUTPUTS["created"], planted]}
    seen = {**listings(fake), other_ws: {planted["id"]: {"id": planted["id"], "type": "Report", "displayName": "someone_elses"}}}
    dry = life.retire(fake, req(outputs=outputs, workspace=WS), seen)
    assert planted["id"] not in {x["id"] for x in dry["items"]}
    assert any(x["id"] == planted["id"] and "another workspace" in x["why"] for x in dry["refused"])
    life.retire(fake, req(outputs=outputs, workspace=WS, dry_run=False, confirm=dry["confirm"], typed_name="Shop sales"), seen)
    assert fake.writes() and not any(other_ws in url for _, url in fake.writes())
