"""BL27 (21 Nov 2026): schedules drafted, the pipeline's daily run and the model refresh after it (fabric_backend/
schedules.py, docs/SCHEDULES.md). A dry run only: the tests check the bodies against the shapes Microsoft Learn shows
(fixtures copied from the pages, cited below), that nothing is sent (any HTTP call fails the test), and that the time
and time zone are checked.
"""
from __future__ import annotations

import socket
from datetime import date

import pytest

from fabric_backend import schedules

# Copied from Microsoft Learn, Fabric REST API, Core / Job Scheduler, "Items - Create Item Schedule", example "create
# item schedule with execution data" (request body without executionData), read 21 November 2026.
LEARN_DAILY = {"enabled": True, "configuration": {"startDateTime": "2024-04-28T00:00:00", "endDateTime": "2024-04-30T23:59:00",
                                                  "localTimeZoneId": "Central Standard Time", "type": "Daily",
                                                  "times": ["09:00", "15:00"]}}
# Copied from Microsoft Learn, Power BI REST API, "Datasets - Update Refresh Schedule In Group", example "Change the days
# and times of a refresh schedule", read 21 November 2026.
LEARN_REFRESH = {"value": {"days": ["Sunday", "Tuesday", "Friday", "Saturday"], "times": ["07:00", "11:30", "16:00", "23:30"],
                           "localTimeZoneId": "UTC"}}
REFRESH_FIELDS = {"days", "times", "enabled", "localTimeZoneId", "notifyOption"}     # the Refresh Schedule object
TODAY = date(2026, 11, 21)
WS = "11111111-1111-1111-1111-111111111111"
PIPE = {"type": "DataPipeline", "id": "22222222-2222-2222-2222-222222222222", "name": "shop_pipeline", "workspace": WS}
MODEL = {"type": "SemanticModel", "id": "33333333-3333-3333-3333-333333333333", "name": "shop_model", "workspace": WS}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any request fails the test: a socket, requests or the deploy sender."""
    def refuse(*a, **k):
        raise AssertionError("BL27 sends nothing")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    try:
        import requests
        monkeypatch.setattr(requests.Session, "request", refuse)
    except ImportError:
        pass
    from fabric_backend import deploy
    monkeypatch.setattr(deploy, "send", refuse, raising=False)


def _shape(x):
    """Keys and value types, recursively; lists by their first element."""
    if isinstance(x, dict):
        return {k: _shape(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_shape(x[0])] if x else []
    return type(x).__name__


def test_pipeline_body_matches_learn_daily_shape():
    d = schedules.draft({"created": [PIPE, MODEL]}, today=TODAY)
    pipe = d["schedules"][0]
    assert pipe["what"] == "pipeline" and pipe["method"] == "POST"
    assert pipe["url"] == f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/dataPipelines/{PIPE['id']}/jobs/execute/schedules"
    assert _shape(pipe["body"]) == _shape(LEARN_DAILY)
    cfg = pipe["body"]["configuration"]
    assert cfg == {"startDateTime": "2026-11-22T00:00:00", "endDateTime": "2036-11-22T23:59:00", "localTimeZoneId": "UTC",
                   "type": "Daily", "times": ["02:00"]}
    assert any("Create Item Schedule" in c for c in pipe["cites"]) and pipe["why"]


def test_model_refresh_is_the_pipelines_last_step():
    d = schedules.draft({"created": [PIPE, MODEL]}, today=TODAY)
    assert len(d["schedules"]) == 2
    ref = d["schedules"][1]
    assert ref["what"] == "model refresh" and ref["every"] == "after the pipeline" and ref["after"] == "the check"
    assert ref["body"] is None and ref["url"] is None              # no schedule of its own
    act = ref["activity"]
    assert act["json"] is None and "no JSON" in act["why_no_json"]   # Learn shows no JSON; none is guessed
    assert act["settings"]["dataset"] == "shop_model" and act["settings"]["wait_on_completion"] is True
    assert "check" in ref["why"] and ref["cites"]


def test_model_alone_gets_a_refresh_schedule_matching_learn():
    d = schedules.draft({"created": [MODEL]}, timezone="Europe/Stockholm", time="05:30", today=TODAY)
    (ref,) = d["schedules"]
    assert ref["method"] == "PATCH"
    assert ref["url"] == f"https://api.powerbi.com/v1.0/myorg/groups/{WS}/datasets/{MODEL['id']}/refreshSchedule"
    assert set(ref["body"]) == set(LEARN_REFRESH)
    assert set(ref["body"]["value"]) <= REFRESH_FIELDS and set(LEARN_REFRESH["value"]) <= set(ref["body"]["value"])
    assert ref["body"]["value"]["days"] == list(schedules.DAYS) and ref["body"]["value"]["times"] == ["05:30"]
    assert ref["body"]["value"]["localTimeZoneId"] == "W. Europe Standard Time"
    assert ref["body"]["value"]["notifyOption"] in {"NoNotification", "MailOnFailure"}


def test_scopes_per_call_and_what_the_app_has():
    d = schedules.draft({"created": [PIPE, MODEL]}, today=TODAY)
    groups = d["schedules"][0]["scopes"]
    names = [[s["scope"] for s in g["any_of"]] for g in groups]
    assert names == [["DataPipeline.Execute.All", "Item.Execute.All"], ["DataPipeline.ReadWrite.All", "Item.ReadWrite.All"]]
    state = {s["scope"]: s["krusgraph_app"] for g in groups for s in g["any_of"]}
    assert state["Item.Execute.All"] == "not asked for today"
    assert state["DataPipeline.Execute.All"].startswith("opt-in")
    assert state["DataPipeline.ReadWrite.All"] == "granted"
    alone = schedules.draft({"created": [MODEL]}, today=TODAY)["schedules"][0]["scopes"]
    assert alone == [{"any_of": [{"scope": "Dataset.ReadWrite.All", "krusgraph_app": "not asked for today"}]}]


def test_nothing_is_sent_and_it_says_so():
    d = schedules.draft({"created": [PIPE, MODEL]}, today=TODAY)
    assert d["dry_run"] is True and d["sent"] == []
    assert any("nothing was sent" in s for s in d["said"])


def test_placeholders_before_anything_is_created_and_removed_items_ignored():
    d = schedules.draft({"created": [{"type": "DataPipeline", "name": "p"}]}, today=TODAY)
    assert "<workspace id>" in d["schedules"][0]["url"] and "<id of the pipeline p>" in d["schedules"][0]["url"]
    gone = schedules.draft({"created": [PIPE, MODEL], "removed": [{"id": PIPE["id"]}]}, today=TODAY)
    assert [s["what"] for s in gone["schedules"]] == ["model refresh"] and gone["schedules"][0]["method"] == "PATCH"
    empty = schedules.draft({}, today=TODAY)
    assert empty["schedules"] == [] and "nothing to schedule" in empty["said"][0]


@pytest.mark.parametrize("time", ["2:00", "24:00", "02:60", "0200", "", None, "02:00:00"])
def test_time_is_checked(time):
    with pytest.raises(schedules.ScheduleDraftError, match="hh:mm"):
        schedules.draft({"created": [PIPE]}, time=time, today=TODAY)


@pytest.mark.parametrize("tz", ["Mars/Olympus", "CET", "", None, "W. Europe Standard Time"])
def test_timezone_is_checked(tz):
    with pytest.raises(schedules.ScheduleDraftError, match="time zone"):
        schedules.draft({"created": [PIPE]}, timezone=tz, today=TODAY)


def test_start_is_tomorrow_and_leap_day_ends_ten_years_on():
    body = schedules.pipeline_schedule_body("UTC", "02:00", date(2028, 2, 29))
    assert body["configuration"]["startDateTime"] == "2028-02-29T00:00:00"
    assert body["configuration"]["endDateTime"].startswith("2038-02-2")


def test_preview_is_short_and_plain():
    lines = schedules.preview(schedules.draft({"created": [PIPE, MODEL]}, today=TODAY))
    assert lines == ["Pipeline shop_pipeline runs daily at 02:00 UTC.",
                     "Model shop_model refreshes after it, once the check has passed."]
    alone = schedules.preview(schedules.draft({"created": [MODEL]}, timezone="Europe/Stockholm", time="05:30", today=TODAY))
    assert alone == ["Model shop_model refreshes daily at 05:30 Europe/Stockholm."]
    assert schedules.preview(schedules.draft({}, today=TODAY)) == ["Nothing to schedule yet."]
    for line in lines + alone:
        assert len(line.split()) <= schedules.MAX_PREVIEW_WORDS
