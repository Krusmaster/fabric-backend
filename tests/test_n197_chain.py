"""Round n197, items 2 and 3: the run Create started, followed, and what waits for its success.

- a pipeline run that succeeds and one that fails, read through POST /workload/v1/pipeline-run (Fabric's job instance
  and activity runs, the documented Job Scheduler API, with the scopes the card lists);
- an already-built pipeline (skipped by Create) still runs once when Run once is ticked, so Next is truthful;
- with Run once ticked, the semantic model is refreshed after the run, by a refresh_only step;
- the agent's example queries: "not checked yet" while the run writes the tables; after it, an example Fabric marked
  invalid because it could not connect is sent once more, and any other reason stands.
"""
import pytest

from fabric_backend import workload_api as W
from test_n185_pipeline_jobs import FakeFabric, RUN_ID, _jobs_fabric, _pipeline_card, _with_jobs  # noqa: F401
from test_workload_build import make  # noqa: F401  (the editor's fixture)
from test_workload_api import keys  # noqa: F401
import test_workload_build as wl
import golden_support as gs


def _run(client, priv, job, monkeypatch, final):
    import requests
    job.final, job.polls_to_end, job.reads = final, 1, 0
    monkeypatch.setattr(requests, "get", lambda url, *a, **k: job("get", url.replace(RUN_ID, "run-1")))
    monkeypatch.setattr(requests, "post", lambda url, *a, **k: job("post", url, json=k.get("json")))
    body = {"workspace": gs.WS, "pipeline_id": "bbbbbbbb-0000-0000-0000-00000000000b", "pipeline_name": "shop_flow",
            "run_id": RUN_ID, "started": "2026-11-09T18:30:00Z"}
    r = wl._post(client, "/pipeline-run", body, wl.tok(priv))
    assert r.status_code == 200, r.text
    return r.json()


def test_a_run_that_succeeds_and_one_that_fails_are_read_per_activity_with_fabrics_message(make, monkeypatch):
    client, fake, priv, job = _jobs_fabric(make, monkeypatch, None)
    ok = _run(client, priv, job, monkeypatch, "Completed")
    assert ok["status"] == "Succeeded" and [a["status"] for a in ok["activities"]] == ["Succeeded"] * 3 and ok["links"]["run"]
    bad = _run(client, priv, job, monkeypatch, "Failed")
    assert bad["status"] == "Failed" and "1 orphan in order_items" in bad["why"]
    assert bad["activities"][-1]["status"] == "Failed" and bad["links"]["run"]


def test_an_already_built_pipeline_still_runs_once_when_run_once_is_ticked(monkeypatch):
    import importlib
    d = importlib.import_module("fabric_backend.deploy")
    job = FakeFabric(polls_to_end=None)
    monkeypatch.setattr(d, "send", lambda method, url, headers, write=False, **kw: job(method, url.replace("/dataPipelines/pl-1/", "/items/pl-1/"), json=kw.get("json")))
    done = [{"type": "DataPipeline", "id": "pl-1", "name": "shop_flow", "workspace": gs.WS, "output": "pipeline"}]
    granted = {"granted": True, "scope": "DataPipeline.Execute.All", "or": "Item.Execute.All"}
    o = {"kind": "pipeline", "name": "shop_flow", "jobs": {"run_once": True, "schedule": None}}
    card = W._jobs_on_built(o, done, granted, False, gs.WS, {}, [])
    assert card["run"]["status"] == "Running" and card["run"]["run_id"] == "run-1"
    assert W._runs_note([{"output": "pipeline", "jobs": card}]).startswith(" One pipeline run was started")
    dry = W._jobs_on_built(o, done, granted, True, gs.WS, {}, [])
    assert "run" not in dry and dry["words"][0].startswith("Create starts one run of shop_flow")
    off = W._jobs_on_built({**o, "jobs": {"run_once": False, "schedule": None}}, done, granted, False, gs.WS, {}, [])
    assert "run" not in off and len([c for c in job.calls if c[0] == "POST" and c[1].endswith("/instances")]) == 1


def test_with_run_once_the_model_is_refreshed_after_the_run_by_its_own_step(make, monkeypatch):
    client, fake, priv, job = _jobs_fabric(make, monkeypatch, wl.EVERY_SCOPE + " DataPipeline.Execute.All Dataset.ReadWrite.All")
    outs = _with_jobs({"run_once": True, "schedule": None}) + [{"kind": "semantic_model", "name": "shop_model_n197"}]
    dry = wl._build(client, priv, outs)[0].json()
    sm = next(c for c in dry["outputs"] if c["output"] == "semantic_model")
    assert "refresh" in sm, {k: sm.get(k) for k in ("answer", "refusal", "would")}
    assert sm["refresh"]["note"] == W.AFTER_RUN_REFRESH
    refreshed = []
    monkeypatch.setattr(W, "refresh_new_model", lambda ws, mid, scopes, app: refreshed.append(mid) or {"status": "refreshed"})
    out = wl._build(client, priv, outs, dry_run=False, only=["semantic_model"], skip_built=True)[0].json()
    card = out["outputs"][0]
    assert card["refresh"] == {"status": "planned", "note": W.AFTER_RUN_REFRESH} and refreshed == []
    r = wl._build(client, priv, outs, dry_run=False, only=["semantic_model"], refresh_only=True, created=out["created"])[0]
    assert r.status_code == 200, r.text
    card = r.json()["outputs"][0]
    assert card["refresh"] == {"status": "refreshed"} and refreshed == [out["created"][0]["id"]]
    bad = wl._build(client, priv, outs, dry_run=True, only=["semantic_model"], refresh_only=True)[0]
    assert bad.status_code == 400


class Shots:
    def __init__(self, states):
        self.states, self.patched, self.reads = list(states), [], 0

    def __call__(self, method, url, headers=None, write=False, **kw):
        if method == "patch":
            self.patched.append(url.rsplit("/", 1)[-1])
            return gs.Response(200, {})
        self.reads += 1
        state = self.states[min(self.reads - 1, len(self.states) - 1)]
        return gs.Response(200, {"value": [{"id": "f1", "question": "Sales by month?", "query": "SELECT 1",
                                            "validationStatus": {"value": state, "reason": "x" if state != "Invalid" else "bad column"}}]})


def test_an_example_invalid_for_a_connection_is_sent_once_more_and_another_reason_stands(monkeypatch):
    import importlib
    d = importlib.import_module("fabric_backend.deploy")
    shots = Shots(["Invalid", "Validating", "Valid"])
    monkeypatch.setattr(d, "send", shots)
    before = {"status": "read", "count": 1, "invalid": 1, "invalid_examples": [
        {"question": "Sales by month?", "reason": "Failed to connect to server x.datawarehouse.fabric.microsoft.com"}]}
    now = W.recheck_examples(gs.WS, "agent-1", "ds-1", before, {}, sleep=lambda s: None)
    assert shots.patched == ["f1"] and now["valid"] == 1 and now["rechecked"] == 1
    wrong = {"status": "read", "count": 1, "invalid": 1, "invalid_examples": [{"question": "Sales by month?", "reason": "Invalid column name 'x'"}]}
    shots.patched.clear()
    assert W.recheck_examples(gs.WS, "agent-1", "ds-1", wrong, {}, sleep=lambda s: None) == wrong and shots.patched == []


def test_examples_are_not_checked_yet_while_the_run_writes_the_tables():
    res = {"result": {"examples": {"status": "read", "count": 4, "invalid": 4}, "id": "a", "datasource_id": "d"}}
    card = W.agent_card({"name": "shop_agent", "agent": {"layer": "silver", "publish": True, "copilot": False}}, res,
                        {"run_once": True}, None, False, gs.WS, {}, None)
    assert card["examples"] == {"status": "not_checked", "count": 4, "words": W.NOT_CHECKED_WORDS}
