"""n185: Run once and Schedule for the pipeline create_pipeline makes, both off by default. With neither, nothing runs
and nothing is scheduled (no call to a jobs route). Run once starts one run and reads it within a bound: succeeded,
failed and still running at the bound, each per activity with durations and a link. Schedule creates a schedule, or
updates the one Krusgraph made (its id recorded), never a second, and never touches a schedule Krusgraph did not make.
The dry run says exactly what will run and when. Fabric is a fake job (pipeline_jobs takes its http as an argument),
and for the MCP tool the requests double of tests/test_create_pipeline.py."""
import json
from datetime import date, datetime, timezone

import pytest
import requests

from fabric_backend import pipeline, pipeline_jobs as J, server
from test_create_pipeline import create, fabric  # noqa: F401  (the fixture)
from test_drift_monitor import Resp, WS, lakehouse  # noqa: F401
from test_workload_build import make  # noqa: F401,E402  (the editor's fixture)
from test_workload_api import keys  # noqa: F401,E402

PL = "pl-1"
TODAY = date(2026, 11, 9)
OURS = "11111111-2222-3333-4444-555555555555"
FOREIGN = "99999999-8888-7777-6666-555555555555"


class FakeFabric:
    """A pipeline's job routes: a run that goes InProgress -> `final` after `polls_to_end` reads (None: never ends),
    its activities, and the pipeline's schedules (POST adds one, PATCH changes one; nothing is ever deleted)."""

    def __init__(self, final="Completed", polls_to_end=1, schedules=None, refuse=None, description="Krusgraph pipeline for shop_lh.shop"):
        self.final, self.polls_to_end, self.reads = final, polls_to_end, 0
        self.schedules = [dict(s) for s in (schedules or [])]
        self.refuse, self.description, self.calls = refuse, description, []

    def __call__(self, method, url, **kw):
        self.calls.append((method.upper(), url, kw.get("json")))
        if self.refuse and self.refuse in url and method != "get":
            return Resp(403, {"errorCode": "InsufficientScopes"})
        if url.endswith(f"/items/{PL}"):
            if method == "patch":
                self.description = kw["json"]["description"]
                return Resp(200, {"id": PL})
            return Resp(200, {"id": PL, "description": self.description})
        if url.endswith("/jobs/execute/instances") and method == "post":
            return Resp(202, None, {"Location": f"{J.FABRIC}/v1/workspaces/{WS}/items/{PL}/jobs/instances/run-1", "Retry-After": "5"})
        if "/jobs/execute/instances/run-1" in url:
            self.reads += 1
            done = self.polls_to_end is not None and self.reads >= self.polls_to_end
            body = {"id": "run-1", "status": self.final if done else "InProgress", "startTimeUtc": "2026-11-09T18:30:00.1234567"}
            if done:
                body["endTimeUtc"] = "2026-11-09T18:34:12.1234567"
                if self.final == "Failed":
                    body["failureReason"] = {"message": "Check keys, orphans and sums failed: 1 orphan in order_items"}
            return Resp(200, body)
        if url.endswith("/queryactivityruns"):
            done = self.polls_to_end is not None and self.reads >= self.polls_to_end
            rows = [{"activityName": "Silver tables", "status": "Succeeded", "durationInMs": 119000},
                    {"activityName": "Gold views", "status": "Succeeded" if done else "InProgress", "durationInMs": 61000 if done else -1}]
            if done:
                rows.append({"activityName": "Check keys, orphans and sums", "status": "Failed" if self.final == "Failed" else "Succeeded",
                             "durationInMs": 32000, "error": {"message": "1 orphan in order_items" if self.final == "Failed" else ""}})
            return Resp(200, rows)
        if url.endswith("/jobs/execute/schedules") and method == "get":
            return Resp(200, {"value": self.schedules})
        if url.endswith("/jobs/execute/schedules") and method == "post":
            s = {"id": f"00000000-0000-0000-0000-{len(self.schedules) + 1:012d}", **kw["json"]}
            self.schedules.append(s)
            return Resp(201, s)
        if "/jobs/execute/schedules/" in url and method == "patch":
            sid = url.rsplit("/", 1)[-1]
            for s in self.schedules:
                if s["id"] == sid:
                    s.update(kw["json"])
                    return Resp(200, s)
            return Resp(404, {"errorCode": "ItemNotFound"})
        raise AssertionError(f"unexpected {method} {url}")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def daily(at="06:00", **kw):
    return J.schedule_spec({"every": "day", "at": at, **kw}, today=TODAY)


def apply(fake, run_once=False, spec=None, ours=(), wait=120):
    clock = Clock()
    return J.apply(fake, WS, PL, "demo_lh_pipeline", run_once, spec, ours=ours, wait_seconds=wait, sleep=clock.sleep, clock=clock)


# ------------------------------------------------------------------ off by default: nothing runs ------------------

def test_both_choices_are_off_by_default_and_nothing_runs_or_is_scheduled(fabric):  # noqa: F811
    out = create(dry_run=False)
    assert out["result"]["status"] == "Succeeded"
    assert "run" not in out["result"] and "schedule" not in out["result"] and "jobs" not in out
    assert not any("/jobs/" in u for _, u, _ in fabric["calls"])
    assert out["runs"] == pipeline.NOT_RUN
    assert out["scopes"]["not_needed"].startswith("DataPipeline.Execute.All")


def test_apply_with_neither_calls_nothing():
    fake = FakeFabric()
    assert apply(fake) == {} and fake.calls == []


# ------------------------------------------------------------------ run once ---------------------------------------

def test_run_once_that_succeeds_shows_each_activity_with_its_duration_and_a_link():
    fake = FakeFabric(final="Completed", polls_to_end=2)
    run = apply(fake, run_once=True)["run"]
    assert run["status"] == "Succeeded" and run["run_id"] == "run-1" and run["duration"] == "4m12s"
    assert [(a["activity"], a["status"], a["duration"]) for a in run["activities"]] == [
        ("Silver tables", "Succeeded", "1m59s"), ("Gold views", "Succeeded", "1m01s"), ("Check keys, orphans and sums", "Succeeded", "32s")]
    assert run["links"]["run"].endswith(f"/workspaces/{WS}/pipelines/demo_lh_pipeline/run-1")
    assert run["links"]["pipeline"] == f"{J.FABRIC_APP}/groups/{WS}/pipelines/{PL}"
    assert run["note"] == "The run succeeded in 4m12s." and "still_running" not in run
    assert [c[0] for c in fake.calls if "/jobs/" in c[1]][0] == "POST"     # one start, then only reads
    assert sum(1 for m, u, _ in fake.calls if m == "POST" and u.endswith("/instances")) == 1


def test_run_once_that_fails_says_why_and_which_activity():
    run = apply(FakeFabric(final="Failed", polls_to_end=1), run_once=True)["run"]
    assert run["status"] == "Failed" and "1 orphan" in run["why"]
    check = run["activities"][-1]
    assert check["status"] == "Failed" and check["error"] == "1 orphan in order_items"
    assert run["note"].startswith("The run failed: ")


def test_run_once_still_running_at_the_bound_says_so_with_the_link():
    fake = FakeFabric(polls_to_end=None)
    run = apply(fake, run_once=True, wait=60)["run"]
    assert run["status"] == "Running" and run["still_running"] is True
    assert "Still running after 60 s" in run["note"] and run["links"]["run"]
    assert [a["status"] for a in run["activities"]] == ["Succeeded", "Running"]
    assert fake.reads <= 60 // 15 + 1                                   # bounded: never more reads than the wait allows


def test_the_editor_does_not_wait_it_reads_the_run_itself():
    fake = FakeFabric(polls_to_end=None)
    run = apply(fake, run_once=True, wait=0)["run"]
    assert run["status"] == "Running" and run["note"].startswith("Started; it goes on in Fabric")
    assert fake.reads == 1
    later = J.read_run(FakeFabric(polls_to_end=1), WS, PL, "demo_lh_pipeline", "run-1")
    assert later["status"] == "Succeeded"


def test_a_refused_run_names_the_permission_and_the_manual_steps():
    run = apply(FakeFabric(refuse="/instances"), run_once=True)["run"]
    assert run["status"] == "NotStarted" and run["kind"] == "consent" and run["scope"] == "DataPipeline.Execute.All"
    assert any("choose Run" in m for m in run["manual"]) and any("Schedule" in m for m in run["manual"])


# ------------------------------------------------------------------ schedule ---------------------------------------

def test_schedule_is_created_with_the_chosen_time_zone_and_the_next_run():
    fake = FakeFabric()
    s = apply(fake, spec=daily())["schedule"]
    assert s["status"] == "Succeeded" and s["mode"] == "created"
    body = [b for m, u, b in fake.calls if m == "POST" and u.endswith("/schedules")][0]
    assert body["configuration"] == {"type": "Daily", "times": ["06:00"], "localTimeZoneId": "W. Europe Standard Time",
                                     "startDateTime": "2026-11-10T00:00:00", "endDateTime": "2036-11-10T23:59:00"}
    assert body["enabled"] is True and s["next_run"] and s["words"].startswith("Create adds a daily schedule at 06:00 Europe/Stockholm")
    assert J.schedule_ids_of(fake.description) == [s["id"]]               # the MCP tool knows its own next time


def test_a_second_create_updates_the_krusgraph_schedule_and_adds_no_second():
    fake = FakeFabric(schedules=[{"id": OURS, "enabled": True, "configuration": {"type": "Daily", "times": ["06:00"]}}])
    s = apply(fake, spec=daily("07:30"), ours=[OURS])["schedule"]
    assert s["mode"] == "updated" and s["id"] == OURS and len(fake.schedules) == 1
    assert fake.schedules[0]["configuration"]["times"] == ["07:30"]
    assert not any(m == "POST" and u.endswith("/schedules") for m, u, _ in fake.calls)


def test_the_marker_in_the_description_is_enough_for_the_mcp_tool():
    fake = FakeFabric(schedules=[{"id": OURS, "enabled": True, "configuration": {}}],
                      description=f"Krusgraph pipeline for shop_lh.shop [Krusgraph schedule {OURS}]")
    s = apply(fake, spec=J.schedule_spec({"every": "hours", "hours": 4}, today=TODAY))["schedule"]
    assert s["mode"] == "updated" and len(fake.schedules) == 1
    assert fake.schedules[0]["configuration"]["type"] == "Cron" and fake.schedules[0]["configuration"]["interval"] == 240


def test_a_schedule_krusgraph_did_not_make_is_never_touched():
    foreign = {"id": FOREIGN, "enabled": True, "configuration": {"type": "Daily", "times": ["02:00"]}}
    fake = FakeFabric(schedules=[foreign])
    s = apply(fake, spec=daily())["schedule"]
    assert s["mode"] == "created" and s["others_untouched"] == 1 and "did not make" in s["note"]
    assert fake.schedules[0] == foreign
    assert not any(FOREIGN in u for _, u, _ in fake.calls)              # not patched, not deleted, not even read on its own


def test_a_refused_schedule_names_the_permission():
    s = apply(FakeFabric(refuse="/schedules"), spec=daily())["schedule"]
    assert s["status"] == "Failed" and s["kind"] == "consent" and s["scope"] == "DataPipeline.Execute.All"


@pytest.mark.parametrize("raw, why", [({"every": "weekly"}, "every"), ({"every": "day", "at": "6am"}, "hh:mm"),
                                      ({"every": "day", "time_zone": "Mars/Olympus"}, "time_zone"),
                                      ({"every": "hours", "hours": 0}, "hours"), ({"every": "hours", "hours": 25}, "hours"),
                                      ({"every": "day", "start": "2026-11-01"}, "past")])
def test_a_schedule_fabric_would_not_take_is_refused_before_any_call(raw, why):
    with pytest.raises(J.ScheduleError, match=why):
        J.schedule_spec(raw, today=TODAY)


def test_next_run_in_the_time_zone():
    spec = daily()
    assert J.next_run(spec, datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc)).isoformat() == "2026-11-10T06:00:00+01:00"
    assert J.next_run(spec, datetime(2026, 11, 12, 4, 0, tzinfo=timezone.utc)).isoformat() == "2026-11-12T06:00:00+01:00"
    assert J.next_run(spec, datetime(2026, 11, 12, 6, 0, tzinfo=timezone.utc)).isoformat() == "2026-11-13T06:00:00+01:00"
    every4 = J.schedule_spec({"every": "hours", "hours": 4, "at": "06:00"}, today=TODAY)
    assert J.next_run(every4, datetime(2026, 11, 10, 6, 0, tzinfo=timezone.utc)).isoformat() == "2026-11-10T10:00:00+01:00"


# ------------------------------------------------------------------ dry-run wording and the MCP tool ---------------

def test_the_dry_run_says_exactly_what_will_run_and_when():
    words = J.describe("demo_lh_pipeline", True, daily())
    assert words[0] == "Create starts one run of demo_lh_pipeline: silver, then gold, then the check"
    assert words[1].startswith("Create adds a daily schedule at 06:00 Europe/Stockholm")
    assert J.describe("demo_lh_pipeline", False, None) == []


def test_the_mcp_tool_takes_both_parameters_off_by_default():
    import inspect
    sig = inspect.signature(server.create_pipeline)
    assert sig.parameters["run_once"].default is False and sig.parameters["schedule"].default is None
    tool = next(t for t in server.mcp._tool_manager.list_tools() if t.name == "create_pipeline")
    props = tool.parameters["properties"]
    assert "run_once" in props and "schedule" in props and "DataPipeline.Execute.All" in props["schedule"]["description"]


def test_the_mcp_dry_run_with_both_says_what_and_writes_nothing(lakehouse, monkeypatch):  # noqa: F811
    for verb in ("post", "put", "patch", "delete"):
        monkeypatch.setattr(requests, verb, lambda *a, **k: pytest.fail("a dry run writes nothing"))
    out = create(run_once=True, schedule={"every": "day", "at": "06:00"})
    assert out["dry_run"] is True and "result" not in out
    assert out["jobs"]["words"][0] == "Create starts one run of pipeline_shop: silver, then gold, then the check"
    assert out["jobs"]["words"][1].startswith("Create adds a daily schedule at 06:00 Europe/Stockholm")
    assert out["runs"].startswith("Create starts one run of pipeline_shop")
    assert "DataPipeline.Execute.All (or Item.Execute.All)" in out["scopes"]["needs"] and "not_needed" not in out["scopes"]
    assert [r["step"] for r in out["jobs"]["rest"]] == ["run once", "schedule"]


def test_the_mcp_tool_refuses_a_bad_schedule_before_reading_anything(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("nothing is read"))
    out = create(schedule={"every": "day", "at": "25:00"})
    assert out["kind"] == "bad_request" and "hh:mm" in out["error"]


def test_the_mcp_create_with_both_runs_and_schedules_after_the_pipeline(fabric, monkeypatch):  # noqa: F811
    fake = FakeFabric(polls_to_end=1)
    monkeypatch.setattr(J, "RUN_WAIT_SECONDS", 0)
    import importlib
    D = importlib.import_module("fabric_backend.deploy")
    real = D.send

    def send(method, url, headers, **kw):                               # the jobs and the pipeline's description: the fake job
        if "/jobs/" in url or "/queryactivityruns" in url or url.endswith(f"/items/{PL}"):
            return fake(method, url, **{k: v for k, v in kw.items() if k == "json"})
        return real(method, url, headers, **kw)
    monkeypatch.setattr(D, "send", send)
    dry = create(run_once=True, schedule={"every": "day", "at": "06:00"})     # n220: the dry run gives the code, then yes
    out = create(dry_run=False, run_once=True, schedule={"every": "day", "at": "06:00"}, confirm_jobs=dry["jobs"]["confirm"])
    assert out["result"]["status"] == "Succeeded"
    assert out["result"]["schedule"]["mode"] == "created" and out["result"]["run"]["run_id"] == "run-1"
    assert json.dumps(out)                                              # the answer is JSON


# ------------------------------------------------------------------ the Model editor's routes (workload_api) -------
import test_workload_build as wl  # noqa: E402

PIPE = [{"kind": "silver_notebook", "name": "shop_silver"}, {"kind": "gold_views", "name": "shop_gold"}]
RUN_ID = "aaaaaaaa-0000-0000-0000-00000000000a"
EXEC_SCOPES = "Workspace.Read.All Lakehouse.Read.All Item.ReadWrite.All DataPipeline.Execute.All"


def _jobs_fabric(make_client, monkeypatch, scp, schedules=None):
    """The golden workspace of test_workload_build, with the pipeline's job routes answered by FakeFabric above."""
    import requests
    client, fake, priv = make_client(scp)
    job = FakeFabric(polls_to_end=None, schedules=schedules)
    for verb in ("get", "post", "patch"):
        inner = getattr(requests, verb)

        def routed(url, *a, _inner=inner, _verb=verb, **k):
            if "/jobs/" in url or "/queryactivityruns" in url:
                fake.calls.append((_verb.upper(), url))
                return job(_verb, url.replace("/new-dataPipelines/", f"/{PL}/"), json=k.get("json"))
            return _inner(url, *a, **k)
        monkeypatch.setattr(requests, verb, routed)
    return client, fake, priv, job


def _pipeline_card(out):
    return next(c for c in out["outputs"] if c["output"] == "pipeline")


def _with_jobs(jobs):
    return PIPE + [{"kind": "pipeline", "name": "shop_flow", **({"jobs": jobs} if jobs is not None else {})}]


def test_the_editor_dry_run_says_what_will_run_and_when_and_writes_nothing(make, monkeypatch):
    client, fake, priv, job = _jobs_fabric(make, monkeypatch, wl.EVERY_SCOPE + " DataPipeline.Execute.All")
    r, _ = wl._build(client, priv, _with_jobs({"run_once": True, "schedule": {"every": "day", "at": "06:00"}}))
    assert r.status_code == 200, r.text
    jobs = _pipeline_card(r.json())["jobs"]
    assert jobs["permission"]["granted"] is True
    assert jobs["words"][0] == "Create starts one run of shop_flow: silver, then gold, then the check"
    assert jobs["words"][1].startswith("Create adds a daily schedule at 06:00 Europe/Stockholm")
    assert job.calls == [] and not wl._writes(fake)


def test_off_by_default_in_the_editor_nothing_runs(make, monkeypatch):
    client, fake, priv, job = _jobs_fabric(make, monkeypatch, wl.EVERY_SCOPE + " DataPipeline.Execute.All")
    dry, _ = wl._build(client, priv, _with_jobs(None))
    assert _pipeline_card(dry.json())["jobs"]["words"][0].startswith("Nothing runs and nothing is scheduled")
    out = wl._build(client, priv, _with_jobs(None), dry_run=False)[0].json()
    card = _pipeline_card(out)
    assert job.calls == [] and "run" not in card["jobs"] and out["note"].endswith("Nothing runs or is scheduled.")
    assert card["portal_steps"][0] == pipeline.NOT_RUN


def test_without_the_scope_the_choices_are_disabled_with_the_steps_and_nothing_runs(make, monkeypatch):
    client, fake, priv, job = _jobs_fabric(make, monkeypatch, wl.EVERY_SCOPE)
    asked = _with_jobs({"run_once": True, "schedule": {"every": "hours", "hours": 6}})
    perm = _pipeline_card(wl._build(client, priv, asked)[0].json())["jobs"]["permission"]
    assert perm["granted"] is False and perm["scope"] == "DataPipeline.Execute.All"
    assert perm["az"].startswith(f"az ad app permission add --id {wl.WL.client_id} --api 00000009-0000-0000-c000-000000000000")
    assert "DataPipeline.Execute.All" in perm["az"] and "Grant admin consent" in perm["consent_note"]
    assert "admin-consent` fails in Cloud Shell" in perm["consent_note"]
    assert any("choose Run" in m for m in perm["manual"]) and any("Schedule" in m for m in perm["manual"])
    out = wl._build(client, priv, asked, dry_run=False)[0].json()
    card = _pipeline_card(out)
    assert card["created"] and job.calls == []                        # the pipeline is built; nothing runs or is scheduled
    assert card["jobs"]["words"][0].startswith("Neither runs: ")


def test_create_starts_the_run_without_waiting_and_records_the_schedule(make, monkeypatch):
    client, fake, priv, job = _jobs_fabric(make, monkeypatch, wl.EVERY_SCOPE + " DataPipeline.Execute.All")
    out = wl._build(client, priv, _with_jobs({"run_once": True, "schedule": {"every": "day", "at": "06:00"}}), dry_run=False)[0].json()
    card = _pipeline_card(out)
    run, sched = card["jobs"]["run"], card["jobs"]["schedule_result"]
    assert run["status"] == "Running" and run["run_id"] == "run-1" and run["links"]["run"] and job.reads == 1   # no wait
    assert sched["status"] == "Succeeded" and sched["mode"] == "created" and sched["next_run"]
    assert card["portal_steps"] == []                                  # 'Run' and 'Schedule' are done: the Next list drops them
    assert "One pipeline run was started and the pipeline's schedule was created" in out["note"]


def test_a_second_create_updates_the_recorded_schedule_and_leaves_others(make, monkeypatch):
    foreign = {"id": FOREIGN, "enabled": True, "configuration": {"type": "Daily", "times": ["02:00"]}}
    mine = {"id": OURS, "enabled": True, "configuration": {"type": "Daily", "times": ["06:00"]}}
    client, fake, priv, job = _jobs_fabric(make, monkeypatch, wl.EVERY_SCOPE + " DataPipeline.Execute.All", schedules=[foreign, mine])
    out = wl._build(client, priv, _with_jobs({"run_once": False, "schedule": {"every": "day", "at": "05:00"}}), dry_run=False,
                    schedule_ids=[OURS])[0].json()
    sched = _pipeline_card(out)["jobs"]["schedule_result"]
    assert sched["mode"] == "updated" and sched["id"] == OURS and sched["others_untouched"] == 1
    assert len(job.schedules) == 2 and job.schedules[0] == foreign and job.schedules[1]["configuration"]["times"] == ["05:00"]


def test_a_bad_schedule_from_the_editor_is_a_bad_request(make, monkeypatch):
    client, fake, priv, job = _jobs_fabric(make, monkeypatch, None)
    r, _ = wl._build(client, priv, _with_jobs({"run_once": "yes"}))
    assert r.status_code == 400 and "run_once" in r.json()["error"]
    r, _ = wl._build(client, priv, _with_jobs({"schedule": {"every": "day", "time_zone": "Mars/Olympus"}}))
    assert r.status_code == 400 and "time_zone" in r.json()["error"]


def test_the_pipeline_run_route_reads_the_run_for_the_card(make, monkeypatch):
    client, fake, priv, job = _jobs_fabric(make, monkeypatch, None)
    job.polls_to_end = 1
    body = {"workspace": wl.gs.WS, "pipeline_id": "bbbbbbbb-0000-0000-0000-00000000000b", "pipeline_name": "shop_flow",
            "run_id": RUN_ID, "started": "2026-11-09T18:30:00Z"}
    import requests
    monkeypatch.setattr(requests, "get", lambda url, *a, **k: job("get", url.replace(RUN_ID, "run-1")))
    monkeypatch.setattr(requests, "post", lambda url, *a, **k: job("post", url, json=k.get("json")))
    r = wl._post(client, "/pipeline-run", body, wl.tok(priv))
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["status"] == "Succeeded" and [a["status"] for a in run["activities"]] == ["Succeeded"] * 3
    assert run["note"] == "The run succeeded in 4m12s."
    bad = wl._post(client, "/pipeline-run", {**body, "run_id": "not-an-id"}, wl.tok(priv))
    assert bad.status_code == 400


# ------------------------------------------------------------------ 5. the report's footer and table have room ------

def test_the_footer_line_and_the_last_table_row_have_room_at_1280_by_720():
    from fabric_backend import report
    from test_workload_refresh import _shop_page
    _, drawn = _shop_page()
    docs = [json.loads(t) if isinstance(t, str) else t for p, t in drawn["parts"].items() if p.endswith("visual.json")]
    foot = next(d for d in docs if d["visual"]["visualType"] == "textbox" and "Created by Krusgraph" in json.dumps(d))
    table = next(d for d in docs if d["visual"]["visualType"] == "tableEx")
    fp, tp = foot["position"], table["position"]
    text = foot["visual"]["objects"]["general"][0]["properties"]["paragraphs"][0]["textRuns"][0]["value"]
    assert text.endswith(". Created by Krusgraph from the checked plan.")
    assert report.text_problems({"type": "footnote", "text": text}, fp) == []          # the 9 pt line and its padding fit
    assert report.text_problems({"type": "footnote", "text": text}, {**fp, "height": 24}) != []   # the 9 November height did not
    assert fp["y"] + fp["height"] <= report.PAGE_H - report.MARGIN                      # not at the page's edge
    assert tp["y"] + tp["height"] + report.GAP <= fp["y"]                               # the table ends above the footer
    pad = table["visual"]["visualContainerObjects"]["padding"][0]["properties"]
    assert pad["bottom"]["expr"]["Literal"]["Value"] == f"{float(report.TABLE_PAD_PX):g}D"   # room below the last row
    assert "Products by" in json.dumps(table["visual"]["visualContainerObjects"]["title"])
