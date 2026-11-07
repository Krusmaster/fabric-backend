"""n120: create_pipeline creates the pipeline of the n110 draft. The dry run (the default) makes no write call and returns
the definitions and the REST calls; dry_run=false sends exactly those definitions (the notebook ids in place of their
placeholders), notebooks first, then the pipeline, and never starts a run or adds a schedule. Fabric's REST API is the
test double of tests/test_drift_monitor.py (requests.get/post replaced); the check's stop on a failed check runs on
SQLite in tests/test_pipeline_draft.py, and here the definition is held to it."""
import base64
import json

import pytest
import requests

from fabric_backend import pipeline, server, tool_status
from test_drift_monitor import Resp, WS, lakehouse  # noqa: F401  (the fixture and the test double)

NB_IDS = {"silver_shop": "nb-silver", "gold_shop": "nb-gold", "pipeline_shop_check": "nb-check"}


def create(**kw):
    return json.loads(server.create_pipeline("Sales", "shop_lh", name="pipeline_shop", schema="shop", **kw))


def decoded(body: dict) -> dict:
    return {p["path"]: base64.b64decode(p["payload"]).decode("utf-8") for p in body["definition"]["parts"]}


@pytest.fixture
def fabric(lakehouse, monkeypatch):  # noqa: F811
    """Fabric with an empty workspace: every create answers 201 with an id; every call is recorded."""
    calls = []
    items = {"value": []}

    def get(url, **k):
        calls.append(("GET", url, None))
        return Resp(200, items)

    def post(url, **k):
        calls.append(("POST", url, k.get("json")))
        if url.endswith("/notebooks"):
            return Resp(201, {"id": NB_IDS[k["json"]["displayName"]]})
        if url.endswith("/dataPipelines"):
            return Resp(201, {"id": "pl-1"})
        return Resp(200, None)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "put", lambda *a, **k: pytest.fail("create_pipeline never puts"))
    monkeypatch.setattr(requests, "delete", lambda *a, **k: pytest.fail("create_pipeline never deletes"))
    return {"calls": calls, "items": items}


def test_the_dry_run_is_the_default_and_makes_no_write_call(lakehouse, monkeypatch):  # noqa: F811
    for verb in ("post", "put", "patch", "delete"):
        monkeypatch.setattr(requests, verb, lambda *a, **k: pytest.fail("a dry run writes nothing"))
    out = create()
    assert out["dry_run"] is True and "result" not in out and "error" not in out
    assert [r["step"] for r in out["rest"]] == ["silver_shop", "gold_shop", "pipeline_shop_check", "pipeline_shop"]
    assert [r["url"].rsplit("/", 1)[-1] for r in out["rest"]] == ["notebooks", "notebooks", "notebooks", "dataPipelines"]
    assert all(n["content"].startswith("# Fabric notebook source") for n in out["notebooks"])
    acts = out["pipeline"]["content"]["properties"]["activities"]
    assert [a["typeProperties"]["notebookId"] for a in acts] == [pipeline.placeholder(n) for n in NB_IDS]
    assert {a["typeProperties"]["workspaceId"] for a in acts} == {WS}


def test_a_real_create_sends_exactly_the_dry_run_definitions(fabric):
    dry = create()
    out = create(dry_run=False)
    assert out["result"]["status"] == "Succeeded" and "error" not in out
    posts = [(u, b) for m, u, b in fabric["calls"] if m == "POST"]
    assert [u.rsplit("/", 1)[-1] for u, _ in posts] == ["notebooks", "notebooks", "notebooks", "dataPipelines"]
    for (_, body), nb in zip(posts[:3], dry["notebooks"]):
        assert body["displayName"] == nb["name"] and body["description"] == nb["description"]
        assert decoded(body)["notebook-content.py"] == nb["content"]
    sent = json.loads(decoded(posts[3][1])["pipeline-content.json"])
    expected = json.dumps(dry["pipeline"]["content"])
    for name, nb_id in NB_IDS.items():
        expected = expected.replace(pipeline.placeholder(name), nb_id)
    assert sent == json.loads(expected)                                  # only the ids differ from the dry run
    assert posts[3][1]["displayName"] == "pipeline_shop" and out["pipeline"]["content"] == sent


def test_the_pipeline_runs_silver_then_gold_then_the_check_and_stops_on_a_failed_check(fabric):
    create(dry_run=False)
    body = [b for m, u, b in fabric["calls"] if m == "POST" and u.endswith("/dataPipelines")][0]
    acts = json.loads(decoded(body)["pipeline-content.json"])["properties"]["activities"]
    assert [(a["name"], a["typeProperties"]["notebookId"]) for a in acts] == [
        ("Silver tables", "nb-silver"), ("Gold views", "nb-gold"), ("Check keys, orphans and sums", "nb-check")]
    # each step only after the one before it Succeeded: a failed check (the notebook raises) fails the run, and a failed
    # silver or gold step stops the steps after it
    assert [a["dependsOn"] for a in acts] == [[], [{"activity": "Silver tables", "dependencyConditions": ["Succeeded"]}],
                                              [{"activity": "Gold views", "dependencyConditions": ["Succeeded"]}]]
    assert all(a["policy"]["retry"] == 0 for a in acts)
    check = [b for m, u, b in fabric["calls"] if m == "POST" and b and b.get("displayName") == "pipeline_shop_check"][0]
    source = decoded(check)["notebook-content.py"]
    assert source.index("result = check(CHECK, execute, spark.catalog.tableExists)") < source.index("\nraise_if_failed(result)") \
        < source.index("notebookutils.notebook.exit")
    assert "pip install" not in source and "fabric_backend" not in source                    # n140: self-contained


def test_nothing_runs_or_schedules_and_the_answer_says_so(fabric):
    for out in (create(), create(dry_run=False)):
        assert out["runs"] == pipeline.NOT_RUN and "schedules nothing" in out["runs"]
    urls = [u for _, u, _ in fabric["calls"]]
    assert urls and not [u for u in urls if "/jobs/" in u or "schedule" in u.lower() or "/run" in u]
    assert {m for m, _, _ in fabric["calls"]} == {"GET", "POST"}
    content = create()["pipeline"]["content"]
    assert "schedule" not in json.dumps(content["properties"]["activities"]).lower() and "trigger" not in json.dumps(content).lower()


def test_existing_items_are_updated_in_place(fabric):
    fabric["items"]["value"] = [{"id": i, "displayName": n, "type": "Notebook"} for n, i in NB_IDS.items()] + [
        {"id": "pl-1", "displayName": "pipeline_shop", "type": "DataPipeline"}]
    out = create(dry_run=False)
    assert {r["mode"] for k, r in out["result"].items() if k != "status"} == {"updated"}
    posts = [u.rsplit("/", 2)[-2:] for m, u, _ in fabric["calls"] if m == "POST"]
    assert posts == [["nb-silver", "updateDefinition"], ["nb-gold", "updateDefinition"], ["nb-check", "updateDefinition"],
                     ["pl-1", "updateDefinition"]]


def test_a_refused_step_stops_the_steps_after_it_and_names_the_scope(lakehouse, monkeypatch):  # noqa: F811
    posted = []
    monkeypatch.setattr(requests, "get", lambda url, **k: Resp(200, {"value": []}))

    def post(url, **k):
        posted.append(url)
        if url.endswith("/notebooks"):
            return Resp(201, {"id": NB_IDS[k["json"]["displayName"]]})
        return Resp(403, {"errorCode": "InsufficientScopes", "message": "missing scope"})
    monkeypatch.setattr(requests, "post", post)
    out = create(dry_run=False)
    assert out["kind"] == "consent" and "DataPipeline.ReadWrite.All" in out["hint"]
    assert out["result"]["pipeline_shop_check"]["status"] == "Succeeded" and "fabric-token" not in json.dumps(out)
    posted.clear()
    monkeypatch.setattr(requests, "post", lambda url, **k: posted.append(url) or Resp(403, {"errorCode": "InsufficientScopes"}))
    out = create(dry_run=False)
    assert out["kind"] == "consent" and "Notebook.ReadWrite.All" in out["hint"] and len(posted) == 1   # no pipeline without its notebooks


def test_the_notebooks_are_the_ones_the_existing_tools_and_the_export_produce(lakehouse, monkeypatch):  # noqa: F811
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("a dry run writes nothing"))
    nbs = {n["name"]: n["content"] for n in create()["notebooks"]}
    silver = json.loads(server.create_silver_notebook("Sales", "shop_lh", name="silver_shop", schema="shop"))
    gold = json.loads(server.create_gold_views("Sales", "shop_lh", name="gold_shop", schema="shop"))
    assert nbs["silver_shop"] == silver["notebook"]["content"] and nbs["gold_shop"] == gold["notebook"]["content"]
    files = json.loads(server.export_item_definitions("Sales", "shop_lh", schema="shop", items=["pipeline"]))["files"]
    for name, text in nbs.items():
        assert files[f"{name}.Notebook/notebook-content.py"] == text


def test_it_needs_a_lakehouse_with_schemas(lakehouse, monkeypatch):  # noqa: F811
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": "Lakehouse", "id": "lh-1", "displayName": src,
                                                                             "sql_host": "h", "sql_db": src, "schemas_enabled": False})
    assert create()["kind"] == "unsupported"
    lakehouse["type"] = "Warehouse"
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": "Warehouse", "id": "wh-1", "displayName": src,
                                                                             "sql_host": "h", "sql_db": src, "schemas_enabled": True})
    assert create()["kind"] == "unsupported"


def test_three_different_notebook_names(lakehouse):  # noqa: F811
    out = json.loads(server.create_pipeline("Sales", "shop_lh", name="p", schema="shop", gold_name="p_check"))
    assert out["kind"] == "bad_input" and "three different" in out["error"]


def test_scopes_and_status_say_the_hosted_app_has_them():
    s = tool_status.STATUS["create_pipeline"]
    assert s.available == tool_status.HOSTED and s.kind == tool_status.CREATES and not s.live
    assert "DataPipeline.ReadWrite.All" in s.note and "Notebook.ReadWrite.All" in s.note
    assert tool_status.word("create_pipeline") == "Experimental"
