"""Schedules drafted (round BL27, 21 November 2026; sprint item BL27, backlog B-26): the pipeline's daily run and the
semantic model refresh after it, as request bodies and plain sentences. A dry run only: nothing here sends anything,
and nothing calls this module yet (docs/SCHEDULES.md says what wiring Create needs).

  draft(outputs, timezone="UTC", time="02:00")   the Fabric Job Scheduler body for the pipeline's daily run, and the
                                                  model refresh as the pipeline's last step (after the check); with no
                                                  pipeline, a Power BI refresh schedule for the model on its own. Each
                                                  with the reason for the choice and the delegated scopes per call.
  preview(drafted)                                one sentence per schedule, at most 25 words, for the chain to show.

`outputs` is a Krusgraph Model's outputs.json ({"created": [{type, id, name, workspace}], "removed": [...]}); an item
without an id gets a placeholder, so the draft can be shown before anything is created.

What it rests on (Microsoft Learn, read 21 November 2026 for this round):
- Fabric REST API, Core / Job Scheduler, "Items - Create Item Schedule" (page updated 10 November 2026):
  POST /v1/workspaces/{workspaceId}/items/{itemId}/jobs/{jobType}/schedules with {enabled, configuration}; a Daily
  configuration is {startDateTime, endDateTime, localTimeZoneId, type: "Daily", times: ["hh:mm"]} (the page's example
  "create item schedule with execution data"); Required Delegated Scopes "Item.Execute.All and Item.ReadWrite.All".
  For a data pipeline Krusgraph uses the dataPipelines route with job type `execute` and the narrower scopes, as
  pipeline_jobs.py has done since n185 (microsoft/fabric-rest-api-specs dataPipeline/swagger.json, read 11 November
  2026): (DataPipeline.Execute.All or Item.Execute.All) and (DataPipeline.ReadWrite.All or Item.ReadWrite.All).
- Data Factory, "Semantic model refresh activity in Data Factory for Microsoft Fabric" (ms.date 7 April 2026): a
  pipeline activity that refreshes a semantic model through a Power BI connection, set by Connection, Workspace and
  Dataset; "Wait on completion" is on by default; a full refresh by default; it "works only with semantic models you
  create yourself" and needs a Premium, Premium Per User or Embedded capacity. The page shows the editor only; it gives
  no JSON for the activity, so none is drafted here (see REFRESH_ACTIVITY).
- Power BI REST API, "Datasets - Update Refresh Schedule In Group" (page updated 5 February 2025):
  PATCH https://api.powerbi.com/v1.0/myorg/groups/{groupId}/datasets/{datasetId}/refreshSchedule with
  {"value": {days, times, enabled, localTimeZoneId, notifyOption}}; at least one day; Required Scope
  Dataset.ReadWrite.All; the user must be the dataset owner; notifyOption NoNotification or MailOnFailure.
Not verified against Fabric: none of these bodies has been sent to a workspace.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from . import access
from .pipeline_jobs import FABRIC, JOB_TYPE, SCHEDULE_YEARS, WINDOWS_ZONES

POWERBI = "https://api.powerbi.com/v1.0/myorg"
READ_ON = "21 November 2026"
LEARN = {
    "create_item_schedule": "Microsoft Learn, Fabric REST API, Core / Job Scheduler, Items - Create Item Schedule "
                            "(learn.microsoft.com/rest/api/fabric/core/job-scheduler/create-item-schedule, updated "
                            "10 November 2026), read " + READ_ON,
    "refresh_activity": "Microsoft Learn, Data Factory, Semantic model refresh activity in Data Factory for Microsoft "
                        "Fabric (learn.microsoft.com/fabric/data-factory/semantic-model-refresh-activity, ms.date "
                        "7 April 2026), read " + READ_ON,
    "refresh_schedule": "Microsoft Learn, Power BI REST API, Datasets - Update Refresh Schedule In Group "
                        "(learn.microsoft.com/rest/api/power-bi/datasets/update-refresh-schedule-in-group, updated "
                        "5 February 2025), read " + READ_ON,
    "pipeline_scopes": "microsoft/fabric-rest-api-specs dataPipeline/swagger.json (ScheduleExecute), read 11 November "
                       "2026, as cited in pipeline_jobs.py",
}
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
MAX_PREVIEW_WORDS = 25
REFRESH_ACTIVITY = {
    "step": "refresh the semantic model",
    "kind": "Semantic model refresh (Data Factory pipeline activity)",
    "settings": {"connection": "a Power BI connection the workspace owner creates in Fabric",
                 "workspace": None, "dataset": None, "wait_on_completion": True, "refresh": "full (the default)"},
    "json": None,
    "why_no_json": "Learn documents this activity in the pipeline editor only, with no JSON shape; Krusgraph does not "
                   "guess one. Until it is documented, the step is added in Fabric's editor after the check.",
}


class ScheduleDraftError(ValueError):
    """A time or time zone the draft cannot use; the message says which and why."""


def _check(timezone: str, time: str) -> tuple[str, str]:
    t = str(time or "")
    if not _HHMM.match(t):
        raise ScheduleDraftError(f"time is hh:mm on a 24-hour clock, like 02:00; got {time!r}.")
    tz = str(timezone or "")
    if tz not in WINDOWS_ZONES:
        raise ScheduleDraftError(f"timezone {timezone!r} is not one Krusgraph maps to Fabric's time zones; choose one of "
                                 + ", ".join(sorted(WINDOWS_ZONES)) + ".")
    return tz, t


def _active(outputs: dict | None) -> list[dict]:
    outputs = outputs or {}
    gone = {r.get("id") for r in outputs.get("removed") or [] if isinstance(r, dict)}
    return [c for c in outputs.get("created") or [] if isinstance(c, dict) and (not c.get("id") or c["id"] not in gone)]


def _first(items: list[dict], kind: str) -> dict | None:
    return next((c for c in items if c.get("type") == kind), None)


def _placeholder(kind: str, item: dict) -> str:
    return f"<id of the {kind} {item['name']}>" if item.get("name") else f"<id of the {kind}>"


def _scope(scope: str) -> dict:
    """A delegated scope and whether Krusgraph's Entra app has it today (access.py is the source)."""
    if scope in access.scopes():
        state = "granted"
    elif any(o.scope == scope for o in access.OPT_IN):
        state = "opt-in, off unless the operator turns it on"
    else:
        state = "not asked for today"
    return {"scope": scope, "krusgraph_app": state}


def _scopes(all_of: list[tuple[str, ...]]) -> list[dict]:
    """All of the groups, any one scope per group: [{any_of: [{scope, krusgraph_app}]}]."""
    return [{"any_of": [_scope(s) for s in group]} for group in all_of]


def _window(start: date) -> tuple[str, str]:
    end = start + timedelta(days=3652) if (start.month, start.day) == (2, 29) else start.replace(year=start.year + SCHEDULE_YEARS)
    return f"{start.isoformat()}T00:00:00", f"{end.isoformat()}T23:59:00"


def pipeline_schedule_body(timezone: str, time: str, start: date) -> dict:
    """Create Item Schedule's body: Daily at `time` in the Windows time zone of `timezone`, from `start`, with the end
    Fabric requires (SCHEDULE_YEARS later, as pipeline_jobs.schedule_body sets it)."""
    tz, t = _check(timezone, time)
    begin, end = _window(start)
    return {"enabled": True, "configuration": {"startDateTime": begin, "endDateTime": end,
                                               "localTimeZoneId": WINDOWS_ZONES[tz], "type": "Daily", "times": [t]}}


def refresh_schedule_body(timezone: str, time: str) -> dict:
    """Update Refresh Schedule In Group's body: every day at `time`, a mail to the owner when a refresh fails."""
    tz, t = _check(timezone, time)
    return {"value": {"days": list(DAYS), "times": [t], "enabled": True, "localTimeZoneId": WINDOWS_ZONES[tz],
                      "notifyOption": "MailOnFailure"}}


def draft(outputs: dict | None, timezone: str = "UTC", time: str = "02:00", today: date | None = None) -> dict:
    """The schedules for this data product, drafted and not sent: {dry_run, timezone, time, schedules: [...], said}."""
    tz, t = _check(timezone, time)
    start = (today or date.today()) + timedelta(days=1)
    items = _active(outputs)
    pipe, model = _first(items, "DataPipeline"), _first(items, "SemanticModel")
    out: dict = {"dry_run": True, "sent": [], "timezone": tz, "time": t, "start": start.isoformat(), "schedules": [], "said": []}
    if pipe:
        ws = pipe.get("workspace") or "<workspace id>"
        pid = pipe.get("id") or _placeholder("pipeline", pipe)
        out["schedules"].append({
            "what": "pipeline", "name": pipe.get("name"), "every": "day", "at": t, "time_zone": tz,
            "method": "POST", "url": f"{FABRIC}/v1/workspaces/{ws}/dataPipelines/{pid}/jobs/{JOB_TYPE}/schedules",
            "learn_route": f"{FABRIC}/v1/workspaces/{ws}/items/{pid}/jobs/Pipeline/schedules",
            "body": pipeline_schedule_body(tz, t, start),
            "scopes": _scopes([("DataPipeline.Execute.All", "Item.Execute.All"), ("DataPipeline.ReadWrite.All", "Item.ReadWrite.All")]),
            "cites": [LEARN["create_item_schedule"], LEARN["pipeline_scopes"]],
            "why": ("One schedule, on the pipeline: silver, gold and the check run in order, each after the one before "
                    "succeeded. Daily, because the sources Krusgraph reads are loaded daily; the start is tomorrow, since "
                    "Fabric starts a run at once when the start time is in the past."),
        })
        if model:
            act = {**REFRESH_ACTIVITY, "settings": {**REFRESH_ACTIVITY["settings"],
                                                    "workspace": model.get("workspace") or ws, "dataset": model.get("name")}}
            out["schedules"].append({
                "what": "model refresh", "name": model.get("name"), "every": "after the pipeline", "after": "the check",
                "method": None, "url": None, "body": None, "activity": act,
                "scopes": [{"any_of": [_scope("DataPipeline.ReadWrite.All"), _scope("Item.ReadWrite.All")],
                            "for": "adding the step to the pipeline's definition (updateDefinition)"}],
                "runs_as": "the Power BI connection's credentials, not Krusgraph's token",
                "cites": [LEARN["refresh_activity"]],
                "why": ("The refresh is the pipeline's last step, after the check, not a schedule of its own: a model on "
                        "its own clock can refresh before the load ends or after a load the check failed, and then shows "
                        "yesterday's numbers as today's. As the last step it runs only after a load that passed."),
            })
    elif model:
        ws = model.get("workspace") or "<workspace id>"
        mid = model.get("id") or _placeholder("semantic model", model)
        out["schedules"].append({
            "what": "model refresh", "name": model.get("name"), "every": "day", "at": t, "time_zone": tz,
            "method": "PATCH", "url": f"{POWERBI}/groups/{ws}/datasets/{mid}/refreshSchedule",
            "body": refresh_schedule_body(tz, t),
            "scopes": _scopes([("Dataset.ReadWrite.All",)]),
            "needs": "the signed-in person owns the semantic model (Learn: the user must be the dataset owner)",
            "cites": [LEARN["refresh_schedule"]],
            "why": ("No Krusgraph pipeline loads these tables, so there is nothing to follow; the model refreshes daily on "
                    "its own schedule. Choose a time after the tables' own load ends."),
        })
    else:
        out["said"].append("No pipeline and no semantic model in outputs.json yet: nothing to schedule.")
    out["said"].append("A draft only: nothing was sent to Fabric or Power BI.")
    return out


def _sentence(s: dict) -> str:
    if s["what"] == "pipeline":
        return f"Pipeline {s.get('name') or ''} runs daily at {s['at']} {s['time_zone']}.".replace("  ", " ")
    if s.get("every") == "after the pipeline":
        return f"Model {s.get('name') or ''} refreshes after it, once the check has passed.".replace("  ", " ")
    return f"Model {s.get('name') or ''} refreshes daily at {s['at']} {s['time_zone']}.".replace("  ", " ")


def preview(drafted: dict) -> list[str]:
    """One sentence per schedule, each at most MAX_PREVIEW_WORDS words; an empty draft says so."""
    out = [_sentence(s) for s in drafted.get("schedules") or []] or ["Nothing to schedule yet."]
    for line in out:
        if len(line.split()) > MAX_PREVIEW_WORDS:      # a very long item name: drop it, keep the sentence short
            out[out.index(line)] = re.sub(r"^(Pipeline|Model) \S+ ", r"\1 ", line)
    return out
