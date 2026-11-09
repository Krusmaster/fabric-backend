"""Run once and schedule (round n185): the two opt-in choices for the pipeline create_pipeline makes. Both are off by
default; with neither, Krusgraph runs nothing and schedules nothing, as before.

  run once     start one run of the pipeline (silver, then gold, then the check), then read it with a bounded wait:
               the run's status and, per activity, Succeeded / Failed / Running with its duration, and a link
  schedule     daily at a chosen time, or every N hours, in a time zone (default Europe/Stockholm) from a start date;
               the next run time is said. A schedule Krusgraph made (its id recorded in outputs.json) is updated in
               place; a schedule Krusgraph did not make is never changed or removed

Nothing here talks to Fabric by itself: every call goes through `http(method, url, **kw)`, so the tests use a fake
Fabric job and the server passes deploy.send with the signed-in user's token.

What it rests on (read 9 November 2026):
- Microsoft Learn, Fabric REST API, Core / Job Scheduler (fabric-rest-apis-docs b4d803a, updated 15 September 2026):
  Run On Demand Item Job  POST /v1/workspaces/{ws}/items/{id}/jobs/{jobType}/instances, 202 with Location (the job
                          instance) and Retry-After; delegated scope Item.Execute.All or <itemType>.Execute.All
  Get Item Job Instance   GET .../items/{id}/jobs/instances/{jobInstanceId}; status NotStarted, InProgress, Completed,
                          Failed, Cancelled or Deduped, startTimeUtc, endTimeUtc, failureReason; Item.ReadWrite.All or
                          Item.Read.All (or the item type's)
  Create Item Schedule    POST .../items/{id}/jobs/{jobType}/schedules; {enabled, configuration}; at most 20 per item;
                          Item.Execute.All and Item.ReadWrite.All
  List Item Schedules     GET .../items/{id}/jobs/{jobType}/schedules (paged); Item.ReadWrite.All or Item.Read.All
  Update Item Schedule    PATCH .../items/{id}/jobs/{jobType}/schedules/{scheduleId}; Item.Execute.All and Item.ReadWrite.All
  Schedule configuration  Daily {times: ["hh:mm"]} or Cron {interval: minutes}, with startDateTime, endDateTime and
                          localTimeZoneId (a Windows time zone id); "If the start time is in the past, it will trigger a
                          job instantly"
- microsoft/fabric-rest-api-specs 6f817cb, dataPipeline/swagger.json: the same operations for a data pipeline, with the
  job type `execute` (BackgroundJobs_RunOnDemandExecute, BackgroundJobs_GetExecuteJobInstance,
  BackgroundJobs_ListExecuteSchedules, BackgroundJobs_ScheduleExecute, BackgroundJobs_UpdateExecuteSchedule) under
  /v1/workspaces/{ws}/dataPipelines/{id}/jobs/execute/..., whose scopes are DataPipeline.Execute.All or
  Item.Execute.All for running and scheduling, with DataPipeline.ReadWrite.All or Item.ReadWrite.All for a schedule.
  These are the routes used here: they take the narrower DataPipeline.Execute.All, which the generic schedule routes
  do not list. (Learn's data-factory/pipeline-rest-api-capabilities.md, ms.date 08/28/2025, gives the generic route's
  job type for a pipeline as `Pipeline`.)
- The same Learn page, "Query activity runs": POST /v1/workspaces/{ws}/datapipelines/pipelineruns/{jobId}/queryactivityruns
  with {filters, orderBy, lastUpdatedAfter, lastUpdatedBefore}, answering a list of {activityName, status,
  activityRunStart, activityRunEnd, durationInMs, error}; "job id" is the Job Scheduler's job instance id. The page
  names no scope; when Fabric refuses it the run's own status is still shown.
Not verified against Fabric: none of this has run against a live workspace yet (unit-tested with a fake Fabric job), and
the run link is the Monitor hub's address pattern, which Microsoft does not document.
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FABRIC = "https://api.fabric.microsoft.com"
FABRIC_APP = "https://app.fabric.microsoft.com"
JOB_TYPE = "execute"                       # dataPipeline/swagger.json; the generic Job Scheduler route calls it "Pipeline"
EXECUTE_SCOPE = "DataPipeline.Execute.All"
EXECUTE_ALT = "Item.Execute.All"
DEFAULT_TIME_ZONE = "Europe/Stockholm"
DEFAULT_AT = "06:00"
RUN_WAIT_SECONDS = 120                     # the MCP tool's bounded wait; the editor polls on its own, 10 minutes at most
SCHEDULE_YEARS = 10                        # the end date Fabric requires, as create_drift_monitor sets it
MAX_EVERY_HOURS = 24
SPEC = ("Microsoft Learn, Fabric REST API Core / Job Scheduler (Run On Demand Item Job, Get Item Job Instance, Create, List "
        "and Update Item Schedule), read 9 November 2026; microsoft/fabric-rest-api-specs 6f817cb dataPipeline/swagger.json "
        "(job type execute); Learn data-factory/pipeline-rest-api-capabilities.md (Query activity runs)")
# The Windows time zone ids Fabric's localTimeZoneId takes, for the IANA names a person picks. Unicode CLDR's
# windowsZones.xml maps them; these are the ones the editor offers. Anything else is refused with this list.
WINDOWS_ZONES = {
    "Europe/Stockholm": "W. Europe Standard Time", "Europe/Oslo": "W. Europe Standard Time",
    "Europe/Copenhagen": "Romance Standard Time", "Europe/Berlin": "W. Europe Standard Time",
    "Europe/Amsterdam": "W. Europe Standard Time", "Europe/Paris": "Romance Standard Time",
    "Europe/Helsinki": "FLE Standard Time", "Europe/London": "GMT Standard Time", "UTC": "UTC",
    "America/New_York": "Eastern Standard Time", "America/Chicago": "Central Standard Time",
    "America/Los_Angeles": "Pacific Standard Time", "Asia/Tokyo": "Tokyo Standard Time",
    "Australia/Sydney": "AUS Eastern Standard Time",
}
TERMINAL = {"Completed": "Succeeded", "Failed": "Failed", "Cancelled": "Failed", "Deduped": "Failed"}
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
MANUAL = ("Run it once: open the pipeline in Fabric and choose Run; the run shows under Run history (or in the Monitor hub).",
          "Run it regularly: on the pipeline choose Schedule, turn it on, pick Daily (or By the hour), the time, the time zone "
          "and the start date, and Apply.")


class ScheduleError(ValueError):
    """A schedule the person chose that Fabric would not take; the message says which part and why."""


# ------------------------------------------------------------------ the schedule --------------------------------------

def schedule_spec(raw: dict | None, today: date | None = None) -> dict | None:
    """The person's choice, checked: {"every": "day", "at": "06:00"} or {"every": "hours", "hours": 4, "at": "06:00"},
    with "time_zone" (an IANA name, default Europe/Stockholm) and "start" (YYYY-MM-DD, default tomorrow). None or
    {"every": None} means no schedule."""
    if not raw or not raw.get("every"):
        return None
    today = today or date.today()
    every = str(raw["every"]).lower()
    if every in ("daily", "days"):
        every = "day"
    if every not in ("day", "hours"):
        raise ScheduleError('schedule.every is "day" (daily at a time) or "hours" (every N hours).')
    at = str(raw.get("at") or DEFAULT_AT)
    if not _HHMM.match(at):
        raise ScheduleError(f"schedule.at is a time as hh:mm, like 06:00; got {at!r}.")
    tz = str(raw.get("time_zone") or DEFAULT_TIME_ZONE)
    if tz not in WINDOWS_ZONES:
        raise ScheduleError(f"schedule.time_zone {tz!r} is not one Krusgraph maps to Fabric's time zones; choose one of "
                            + ", ".join(sorted(WINDOWS_ZONES)) + ".")
    try:
        start = date.fromisoformat(str(raw["start"])) if raw.get("start") else today + timedelta(days=1)
    except ValueError:
        raise ScheduleError(f"schedule.start is a date as YYYY-MM-DD; got {raw.get('start')!r}.") from None
    if start < today:
        raise ScheduleError("schedule.start is in the past; Fabric would start a run at once. Choose today or a later date.")
    out = {"every": every, "at": at, "time_zone": tz, "start": start.isoformat()}
    if every == "hours":
        try:
            hours = int(raw.get("hours") or 0)
        except (TypeError, ValueError):
            hours = 0
        if not 1 <= hours <= MAX_EVERY_HOURS:
            raise ScheduleError(f"schedule.hours is a whole number from 1 to {MAX_EVERY_HOURS}.")
        out["hours"] = hours
    return out


def schedule_body(spec: dict) -> dict:
    """The request body of Create / Update Item Schedule: Daily at `at`, or Cron every N hours from `at` on the start
    date, in the Windows time zone of the person's choice, ending SCHEDULE_YEARS later (Fabric requires an end)."""
    start = date.fromisoformat(spec["start"])
    end = start.replace(year=start.year + SCHEDULE_YEARS) if not (start.month == 2 and start.day == 29) else start + timedelta(days=3652)
    cfg = {"startDateTime": f"{spec['start']}T{spec['at']}:00" if spec["every"] == "hours" else f"{spec['start']}T00:00:00",
           "endDateTime": f"{end.isoformat()}T23:59:00", "localTimeZoneId": WINDOWS_ZONES[spec["time_zone"]]}
    if spec["every"] == "day":
        cfg.update(type="Daily", times=[spec["at"]])
    else:
        cfg.update(type="Cron", interval=spec["hours"] * 60)
    return {"enabled": True, "configuration": cfg}


def next_run(spec: dict, now: datetime | None = None) -> datetime:
    """When the schedule first runs after `now`, in its own time zone."""
    tz = ZoneInfo(spec["time_zone"])
    now = (now or datetime.now(timezone.utc)).astimezone(tz)
    h, m = (int(x) for x in spec["at"].split(":"))
    first = datetime.combine(date.fromisoformat(spec["start"]), datetime.min.time(), tz).replace(hour=h, minute=m)
    if first > now:
        return first
    if spec["every"] == "day":
        cand = now.replace(hour=h, minute=m, second=0, microsecond=0)
        return cand if cand > now else (cand + timedelta(days=1)).replace(hour=h, minute=m)
    step = timedelta(hours=spec["hours"])
    k = int((now - first) / step) + 1
    return (first.astimezone(timezone.utc) + k * step).astimezone(tz)


def when_words(dt: datetime) -> str:
    """'10 November 2026 06:00 (Europe/Stockholm)'"""
    return f"{dt.day} {dt.strftime('%B %Y %H:%M')} ({dt.tzinfo})"


def schedule_words(spec: dict) -> str:
    """What the dry run says Create adds: 'Create adds a daily schedule at 06:00 Europe/Stockholm'."""
    if spec["every"] == "day":
        what = f"a daily schedule at {spec['at']} {spec['time_zone']}"
    else:
        n = spec["hours"]
        what = f"a schedule every {n} hour{'s' if n != 1 else ''} from {spec['at']} {spec['time_zone']}"
    d = date.fromisoformat(spec["start"])
    return f"Create adds {what}, starting {d.day} {d.strftime('%B %Y')}"


def run_words(pipeline: str) -> str:
    """What the dry run says about Run once."""
    return f"Create starts one run of {pipeline}: silver, then gold, then the check"


def describe(pipeline: str, run_once: bool, spec: dict | None) -> list[str]:
    """The dry run's sentences, exactly what will run and when; none when both are off."""
    out = []
    if run_once:
        out.append(run_words(pipeline))
    if spec:
        out.append(f"{schedule_words(spec)}; the first run is {when_words(next_run(spec))}")
    return out


def base(workspace: str, pipeline_id: str) -> str:
    return f"{FABRIC}/v1/workspaces/{workspace}/dataPipelines/{pipeline_id}/jobs/{JOB_TYPE}"


def ensure_schedule(http, workspace: str, pipeline_id: str, spec: dict, ours: set[str] | list[str]) -> dict:
    """Create the schedule, or update the one Krusgraph made before (its id in `ours`, from outputs.json). Lists the
    pipeline's schedules first; any schedule whose id Krusgraph did not record is left exactly as it is."""
    url = base(workspace, pipeline_id) + "/schedules"
    body = schedule_body(spec)
    existing, page, pages = [], url, 0
    while page and pages < 3:
        r = http("get", page)
        if getattr(r, "status_code", 0) >= 400:
            return {"status": "Failed", "http": getattr(r, "status_code", 0), "step": "list",
                    "why": "listing the pipeline's schedules failed, so none was added (one may exist already)"}
        data = r.json() or {}
        existing += data.get("value") or []
        page, pages = data.get("continuationUri"), pages + 1
    mine = [s for s in existing if s.get("id") in set(ours)]
    others = len(existing) - len(mine)
    if mine:
        sid = mine[0]["id"]
        r = http("patch", f"{url}/{sid}", json=body)
        mode = "updated"
    else:
        r = http("post", url, json=body)
        mode = "created"
    status = getattr(r, "status_code", 0)
    if status >= 400:
        return {"status": "Failed", "http": status, "step": mode[:-1] if mode == "updated" else "create",
                "why": f"Fabric answered HTTP {status}", "others_untouched": others}
    try:
        got = r.json() or {}
    except ValueError:
        got = {}
    sid = got.get("id") or (mine[0]["id"] if mine else None)
    nxt = next_run(spec)
    return {"status": "Succeeded", "mode": mode, "id": sid, "every": spec["every"], "spec": spec,
            "next_run": nxt.isoformat(), "next_run_words": when_words(nxt), "words": schedule_words(spec),
            "others_untouched": others,
            "note": (f"{others} schedule(s) Krusgraph did not make are left as they are." if others else "")}


# ------------------------------------------------------------------ the run -------------------------------------------

def run_link(workspace: str, pipeline_id: str, pipeline_name: str, run_id: str | None) -> dict:
    """Where to see the run in Fabric: the run's page in the Monitor hub (an address pattern Microsoft does not
    document) and the pipeline itself, whose Run history lists it."""
    out = {"pipeline": f"{FABRIC_APP}/groups/{workspace}/pipelines/{pipeline_id}"}
    if run_id:
        out["run"] = f"{FABRIC_APP}/workloads/data-pipeline/monitoring/workspaces/{workspace}/pipelines/{pipeline_name}/{run_id}"
    return out


def start_run(http, workspace: str, pipeline_id: str, pipeline_name: str) -> dict:
    """Run On Demand: one run, its job instance id from the Location header."""
    r = http("post", base(workspace, pipeline_id) + "/instances")
    status = getattr(r, "status_code", 0)
    if status != 202:
        return {"status": "NotStarted", "http": status,
                "why": "Fabric refused to start the run" + (" (the permission to run pipelines is missing)" if status in (401, 403) else
                                                            f" (HTTP {status})")}
    loc = (getattr(r, "headers", {}) or {}).get("Location") or ""
    run_id = loc.rstrip("/").rsplit("/", 1)[-1] if "/instances/" in loc else None
    try:
        retry = int((getattr(r, "headers", {}) or {}).get("Retry-After") or 0)
    except ValueError:
        retry = 0
    return {"status": "Running", "run_id": run_id, "location": loc or None, "retry_after": retry,
            "started": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "links": run_link(workspace, pipeline_id, pipeline_name, run_id)}


def _seconds(a: str | None, b: str | None) -> int | None:
    def parse(s):
        s = s.rstrip("Z")
        if "." in s:
            head, frac = s.split(".", 1)
            s = f"{head}.{frac[:6]}"
        return datetime.fromisoformat(s)
    try:
        return max(0, round((parse(b) - parse(a)).total_seconds())) if a and b else None
    except ValueError:
        return None


def duration_words(seconds: int | None) -> str:
    if seconds is None:
        return ""
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s" if m else f"{s}s"


def activities(http, workspace: str, run_id: str, started: str | None = None) -> list[dict] | None:
    """Per activity of the run: name, Succeeded / Failed / Running (InProgress, Queued), duration and Fabric's error
    message. None when Fabric does not answer the query (the run's own status still stands)."""
    now = datetime.now(timezone.utc)
    body = {"filters": [], "orderBy": [{"orderBy": "ActivityRunStart", "order": "ASC"}],
            "lastUpdatedAfter": started or (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lastUpdatedBefore": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    try:
        r = http("post", f"{FABRIC}/v1/workspaces/{workspace}/datapipelines/pipelineruns/{run_id}/queryactivityruns", json=body)
        if getattr(r, "status_code", 0) >= 400:
            return None
        rows = r.json()
    except Exception:  # noqa: BLE001 — the activity list is a detail; the run's status is the answer
        return None
    rows = rows.get("value", []) if isinstance(rows, dict) else rows or []
    out = []
    for a in rows:
        st = str(a.get("status") or "")
        st = st if st in ("Succeeded", "Failed") else ("Failed" if st in ("Cancelled", "Canceled") else "Running")
        ms = a.get("durationInMs")
        sec = round(ms / 1000) if isinstance(ms, (int, float)) and ms >= 0 else _seconds(a.get("activityRunStart"), a.get("activityRunEnd"))
        row = {"activity": a.get("activityName"), "status": st, "seconds": sec, "duration": duration_words(sec)}
        msg = ((a.get("error") or {}).get("message") or "").strip()
        if st == "Failed" and msg:
            row["error"] = msg[:300]
        out.append(row)
    return out


def read_run(http, workspace: str, pipeline_id: str, pipeline_name: str, run_id: str, started: str | None = None) -> dict:
    """The run now: Succeeded, Failed or Running, its duration so far, the activities and the links."""
    links = run_link(workspace, pipeline_id, pipeline_name, run_id)
    r = http("get", base(workspace, pipeline_id) + f"/instances/{run_id}")
    if getattr(r, "status_code", 0) >= 400:
        return {"status": "Unknown", "run_id": run_id, "links": links, "http": getattr(r, "status_code", 0),
                "why": "Fabric did not answer about the run; open it in Fabric"}
    j = r.json() or {}
    status = TERMINAL.get(j.get("status"), "Running")
    out = {"status": status, "fabric_status": j.get("status"), "run_id": run_id, "links": links,
           "start": j.get("startTimeUtc"), "end": j.get("endTimeUtc")}
    sec = _seconds(j.get("startTimeUtc"), j.get("endTimeUtc"))
    if sec is not None:
        out.update(seconds=sec, duration=duration_words(sec))
    if status == "Failed":
        fr = j.get("failureReason") or {}
        out["why"] = (fr.get("message") or j.get("status") or "")[:300]
    acts = activities(http, workspace, run_id, started)
    if acts is not None:
        out["activities"] = acts
    return out


def wait_run(http, workspace: str, pipeline_id: str, pipeline_name: str, run: dict, wait_seconds: float = RUN_WAIT_SECONDS,
             poll_seconds: float = 15, sleep=time.sleep, clock=time.monotonic) -> dict:
    """Read the run until it ends or `wait_seconds` pass. At the bound the answer says it is still running, with the link."""
    if run.get("status") != "Running" or not run.get("run_id"):
        return run
    deadline = clock() + wait_seconds
    first = max(poll_seconds, float(run.get("retry_after") or 0)) if wait_seconds else 0
    now = read = None
    if first and clock() + first <= deadline:
        sleep(first)
    while True:
        read = read_run(http, workspace, pipeline_id, pipeline_name, run["run_id"], run.get("started"))
        now = clock()
        if read["status"] in ("Succeeded", "Failed") or now + poll_seconds > deadline:
            break
        sleep(poll_seconds)
    if read["status"] == "Running" or read["status"] == "Unknown":
        read["still_running"] = True
        read["note"] = (f"Still running after {int(wait_seconds)} s; it goes on in Fabric. Follow it with the link."
                        if wait_seconds else "Started; it goes on in Fabric. Follow it with the link.")
    read["started"] = run.get("started")
    return read


def run_note(run: dict) -> str:
    """One line for the card: 'Succeeded in 4m12s', 'Failed: <why>', 'Still running ...'."""
    s = run.get("status")
    if s == "Succeeded":
        return f"The run succeeded{' in ' + run['duration'] if run.get('duration') else ''}."
    if s == "Failed":
        return f"The run failed{': ' + run['why'] if run.get('why') else ''}."
    if s == "NotStarted":
        return run.get("why") or "The run did not start."
    return run.get("note") or "The run is still going on in Fabric."


# ------------------------------------------------------------------ which schedule is Krusgraph's --------------------
# A Fabric schedule has no name or description, so Krusgraph knows its own by id: the editor records it in
# outputs.json, and the pipeline's description carries it as "[Krusgraph schedule <id>]" for the MCP tool (which has no
# outputs.json). A schedule whose id is in neither was not made by Krusgraph and is never changed.
SCHEDULE_MARK = re.compile(r"\s*\[Krusgraph schedule ([0-9a-fA-F-]{36})\]")
DESCRIPTION_LIMIT = 256


def schedule_ids_of(description) -> list[str]:
    return SCHEDULE_MARK.findall(str(description or ""))


def with_schedule_mark(description, schedule_id: str) -> str:
    """The description with this schedule's marker (an older one replaced), kept within Fabric's 256 characters."""
    tag = f"[Krusgraph schedule {schedule_id}]"
    rest = SCHEDULE_MARK.sub("", str(description or "")).strip()
    room = DESCRIPTION_LIMIT - len(tag) - 1
    rest = rest if len(rest) <= room else rest[:max(room - 1, 0)].rstrip() + "…"
    return f"{tag} {rest}".strip() if rest else tag


def mark_schedule(http, workspace: str, pipeline_id: str, schedule_id: str) -> bool:
    """Best effort: write the schedule's id into the pipeline's description (GET then PATCH /items/{id})."""
    try:
        r = http("get", f"{FABRIC}/v1/workspaces/{workspace}/items/{pipeline_id}")
        desc = (r.json() or {}).get("description") if getattr(r, "status_code", 0) < 400 else None
        if schedule_id in schedule_ids_of(desc):
            return True
        p = http("patch", f"{FABRIC}/v1/workspaces/{workspace}/items/{pipeline_id}",
                 json={"description": with_schedule_mark(desc, schedule_id)})
        return getattr(p, "status_code", 0) < 400
    except Exception:  # noqa: BLE001 — the schedule stands; outputs.json keeps its id for the editor
        return False


def consent(scope_missing_why: str) -> dict:
    """The answer when Fabric refuses for want of the Execute permission."""
    return {"kind": "consent", "scope": EXECUTE_SCOPE,
            "why": scope_missing_why,
            "hint": f"An administrator adds the delegated permission {EXECUTE_SCOPE} (Power BI Service) to the app and grants "
                    "admin consent; until then run and schedule the pipeline in Fabric.", "manual": list(MANUAL)}


def apply(http, workspace: str, pipeline_id: str, pipeline_name: str, run_once: bool, spec: dict | None,
          ours=(), wait_seconds: float = RUN_WAIT_SECONDS, sleep=time.sleep, clock=time.monotonic) -> dict:
    """After the pipeline exists: the schedule (created or updated), then the run (started, then read until it ends or
    the wait is over). Each part answers on its own; a refusal for want of the permission says which and what to do."""
    out: dict = {}
    if spec:
        listed = None
        try:
            r = http("get", f"{FABRIC}/v1/workspaces/{workspace}/items/{pipeline_id}")
            listed = (r.json() or {}).get("description") if getattr(r, "status_code", 0) < 400 else None
        except Exception:  # noqa: BLE001
            listed = None
        mine = set(ours) | set(schedule_ids_of(listed))
        s = ensure_schedule(http, workspace, pipeline_id, spec, mine)
        if s.get("status") == "Failed" and s.get("http") in (401, 403):
            s.update(consent("Fabric refused the schedule: adding or changing a schedule needs " + EXECUTE_SCOPE + "."))
        elif s.get("status") == "Succeeded" and s.get("id"):
            s["marked"] = mark_schedule(http, workspace, pipeline_id, s["id"])
        out["schedule"] = s
    if run_once:
        run = start_run(http, workspace, pipeline_id, pipeline_name)
        if run.get("http") in (401, 403):
            run.update(consent("Fabric refused to start the run: running a pipeline needs " + EXECUTE_SCOPE + "."))
        elif run.get("status") == "Running":
            run = wait_run(http, workspace, pipeline_id, pipeline_name, run, wait_seconds, sleep=sleep, clock=clock)
        run["note"] = run_note(run) if not run.get("note") else run["note"]
        out["run"] = run
    return out
