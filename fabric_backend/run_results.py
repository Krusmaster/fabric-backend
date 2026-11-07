"""Run results: the latest runs of a pipeline or notebook in a Fabric workspace, per activity, with Fabric's error text,
a category and a suggested next step from a small catalog of Spark/Fabric errors (round n143).

Read-only. Nothing here starts, cancels, schedules or changes a run or an item. The functions are pure: the server
fetches the bodies (lineage with runs=..., server._job_instances) and passes them in; the tests pass recorded ones.

Where the call shapes come from (read as documentation; no code copied from either):

  microsoft/fabric-rest-api-specs 6f817cb (3 November 2026), platform/swagger.json:
    GET /v1/workspaces/{workspaceId}/items/{itemId}/jobs/instances                 JobScheduler_ListItemJobInstances
    GET /v1/workspaces/{workspaceId}/items/{itemId}/jobs/instances/{jobInstanceId} JobScheduler_GetItemJobInstance
    Required delegated scopes: Item.Read.All or Item.ReadWrite.All, or the item type's own Read.All/ReadWrite.All
    (DataPipeline.Read.All, Notebook.Read.All). Pagination by continuationToken / continuationUri. "Most items have a
    limit of 100 recently completed entities." ItemJobInstance (platform/definitions/platform.json): id, itemId,
    jobType, invokeType (Scheduled, Manual), status (NotStarted, InProgress, Completed, Failed, Cancelled, Deduped),
    rootActivityId, startTimeUtc, endTimeUtc, failureReason (common ErrorResponse: errorCode, message, requestId,
    moreDetails, isRetriable). dataPipeline/swagger.json and notebook/swagger.json add item-specific routes
    (…/dataPipelines/{id}/jobs/execute/instances, and for notebooks only a beta GET); the generic route above is the
    one used, as Microsoft's own server uses it.
  microsoft/mcp ee11217 (6 November 2026), tools/Fabric.Mcp.Tools.Core/src/Services/FabricCoreService.JobList.cs and
    FabricCoreService.Jobs.cs: the same two GETs on {base}/workspaces/{ws}/items/{item}/jobs/instances[/{id}], a
    continuationToken query parameter, HTTP 200 with application/json expected. That server keeps only errorCode,
    requestId and isRetriable of failureReason; Krusgraph keeps the message as well, as Fabric returns it.

Per-activity status: neither source documents an endpoint for a pipeline run's activity runs, so none is called. The
activities are read from the pipeline's own definition (pipeline-content.json, getDefinition, as lineage reads other
items); a Notebook activity's status is that notebook's own job instance whose start falls inside the pipeline run's
time window. That match is a heuristic and is marked as one.

The catalog's structure (an ordered list of (pattern, category, hint), searched case-insensitively against the
message text, first match wins) and the loop that applies it follow error_catalog.py (UNDERLYING_PATTERNS) and
diagnostics.py (_classify_refresh) of github.com/FreelexHo/power-bi-mcp at commit 8d2e873 (9 October 2026), MIT:

    MIT License
    Copyright (c) 2026 Freelex Ho
    Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
    documentation files (the "Software"), to deal in the Software without restriction, including without limitation
    the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and
    to permit persons to whom the Software is furnished to do so, subject to the following conditions: The above
    copyright notice and this permission notice shall be included in all copies or substantial portions of the
    Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
    LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
    SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
    OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
    DEALINGS IN THE SOFTWARE.

Taken from there: the list-of-tuples layout, the first-match loop, the "Capacity level limit exceeded|Node level limit
exceeded|exceeded the capacity limit" part of its CapacityThrottle pattern and the "timed out|timeout|timeoutexception"
of its Timeout pattern. The other patterns, the categories and every next step are written here for Spark and Fabric.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

LATEST = 5                    # runs per item in an answer
MESSAGE_CAP = 4000            # characters of one error message; longer ones are cut and marked, never reworded
WINDOW_SLACK = timedelta(seconds=60)
ACTIVITY_NOTEBOOK = "TridentNotebook"

READ_SCOPE = "Item.Read.All (or DataPipeline.Read.All / Notebook.Read.All, or Item.ReadWrite.All)"
DEFINITION_SCOPE = "DataPipeline.ReadWrite.All (or Item.ReadWrite.All)"
HEURISTIC = ("heuristic: the first catalog entry whose pattern occurs in Fabric's error text; a guess at the cause, "
             "not a diagnosis")

# (name, pattern, category, next step). Order matters: the first match wins, so the narrow entries come first and the
# generic timeout last (a missing module can mention a timeout further down a traceback; the reverse is rarer).
CATALOG: list[tuple[str, str, str, str]] = [
    ("import_error",
     r"\bModuleNotFoundError\b|\bImportError\b|No module named|cannot import name",
     "A notebook imports a module or a name that its Spark environment does not have.",
     "Compare the notebook's imports with the environment attached to it (or the default runtime). A notebook created "
     "by Krusgraph should need no package of its own: create it again with the current release (the create tool that "
     "made it, dry run first), then run it or its pipeline again in Fabric."),
    ("table_not_found",
     r"TABLE_OR_VIEW_NOT_FOUND|Table or view not found|Invalid object name|"
     r"\[(?:TABLE|VIEW)_NOT_FOUND\]|(?:table|view)\s+\S+\s+(?:was\s+)?not\s+found|(?:table|view) does not exist",
     "A table or view the step reads is not there under that name: a wrong default lakehouse or schema, or an earlier "
     "step that did not write it.",
     "Check the notebook's default lakehouse and schema, and that the steps ran in order (silver before gold before "
     "the check); list_tables shows what the source holds. If a table was renamed, plan_drift shows what changed."),
    ("permission_denied",
     r"\bHTTP 403\b|\b403\b.*Forbidden|\bForbidden\b|PermissionDenied|Permission denied|Access(?:\s+is)?\s*denied|"
     r"AuthorizationFailed|InsufficientPrivileges|not authorized|does not have (?:the )?permission|Unauthorized",
     "The identity the run used is not allowed to read or write something the step touches.",
     "A person checks who the run ran as (the pipeline's owner or the last person who changed it) and gives that "
     "identity the workspace role or the item permission it lacks; Krusgraph grants nothing."),
    ("capacity_paused_or_throttled",
     r"CapacityNotActive|capacity\s+(?:is\s+)?(?:paused|not active|inactive|suspended)|TooManyRequestsForCapacity|"
     r"\bHTTP 430\b|Capacity level limit exceeded|Node level limit exceeded|exceeded the capacity limit|"
     r"spark compute or API rate limit|throttl",
     "The capacity is paused, or busy enough that Fabric refused or throttled the Spark job.",
     "A person resumes the capacity (Azure portal) or waits for its load to fall, then runs it again in Fabric; "
     "nothing in the item needs to change."),
    ("timeout",
     r"timed out|timeout|timeoutexception|exceeded the (?:maximum )?(?:execution )?time",
     "The step ran longer than a limit: the activity's timeout, the Spark session's, or a source's.",
     "Look at how long earlier runs took and at the data volume; a person decides whether to raise the activity's "
     "timeout in Fabric or make the step smaller. Krusgraph's pipeline activities time out after 12 hours."),
]
_COMPILED = [(name, re.compile(p, re.IGNORECASE), cat, step) for name, p, cat, step in CATALOG]
UNKNOWN_STEP = ("No catalog entry matches. Read the whole error in the Fabric monitoring hub (the run's request id is "
                "given) and decide there.")


def classify(message: str | None, error_code: str | None = None) -> dict:
    """Category and next step for one error text, marked as a heuristic. Searches the message, then the error code."""
    text = " ".join(x for x in (message or "", error_code or "") if x)
    for name, rx, cat, step in _COMPILED:
        m = rx.search(text)
        if m:
            return {"category": name, "what_it_means": cat, "next_step": step, "matched": m.group(0), "heuristic": HEURISTIC}
    return {"category": "unknown", "next_step": UNKNOWN_STEP, "heuristic": HEURISTIC} if text else {}


def created_by_krusgraph(item: dict) -> bool:
    """The create tools write a description that names Krusgraph ("Krusgraph pipeline for …", "… generated by
    Krusgraph from the plan", "created by Krusgraph"); an item someone else made, or whose description was changed,
    is not recognised."""
    return "krusgraph" in (item.get("description") or "").lower()


def _time(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.rstrip("Z")
    head, _, frac = s.partition(".")
    try:
        t = datetime.strptime(head, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    return t + timedelta(microseconds=int((frac + "000000")[:6])) if frac.isdigit() else t


def failure(instance: dict) -> dict | None:
    """failureReason as Fabric returns it: errorCode, message, requestId, isRetriable. The message is only cut when it
    is longer than MESSAGE_CAP, and then says so; it is never reworded."""
    f = instance.get("failureReason")
    if not isinstance(f, dict):
        return None
    out = {k: f[k] for k in ("errorCode", "message", "requestId", "isRetriable") if f.get(k) not in (None, "")}
    msg = out.get("message")
    if isinstance(msg, str) and len(msg) > MESSAGE_CAP:
        out["message"] = msg[:MESSAGE_CAP]
        out["message_cut"] = f"the first {MESSAGE_CAP} of {len(msg)} characters"
    return out


def run(instance: dict) -> dict:
    """One job instance in the answer's shape, with a classification when it failed."""
    out = {k: instance.get(k) for k in ("id", "status", "jobType", "invokeType", "startTimeUtc", "endTimeUtc")}
    f = failure(instance)
    if f:
        out["failure"] = f
        out["diagnosis"] = classify(f.get("message"), f.get("errorCode"))
    return out


def latest(instances: list[dict], n: int = LATEST) -> list[dict]:
    """The n most recent instances by start time (the API does not document an order); not started ones first."""
    return sorted(instances or [], key=lambda i: _time(i.get("startTimeUtc")) or datetime.max, reverse=True)[:n]


def activities(content: dict) -> list[dict]:
    """The activities of pipeline-content.json: name, type, the notebook it runs, what it waits for."""
    acts = ((content or {}).get("properties") or {}).get("activities") or []
    return [{"name": a.get("name"), "type": a.get("type"),
             "notebook_id": (a.get("typeProperties") or {}).get("notebookId"),
             "depends_on": [(d.get("activity"), list(d.get("dependencyConditions") or [])) for d in a.get("dependsOn") or []]}
            for a in acts]


def _in_window(instance: dict, start: datetime | None, end: datetime | None) -> bool:
    t = _time(instance.get("startTimeUtc"))
    if t is None or start is None:
        return False
    return start - WINDOW_SLACK <= t and (end is None or t <= end + WINDOW_SLACK)


def per_activity(pipeline_run: dict, acts: list[dict], notebook_runs: dict[str, list[dict] | dict], items: dict[str, dict]) -> list[dict]:
    """Each activity's status in one pipeline run. `notebook_runs` is {notebook id: its job instances, or {"skipped":
    {...}} when they could not be read}; `items` is {id: workspace item}."""
    start, end = _time(pipeline_run.get("startTimeUtc")), _time(pipeline_run.get("endTimeUtc"))
    done: dict[str, str] = {}
    out = []
    for a in acts:
        row = {"activity": a["name"], "type": a["type"]}
        nb = items.get(a.get("notebook_id") or "")
        if a.get("notebook_id"):
            row["notebook"] = (nb or {}).get("displayName") or a["notebook_id"]
            row["created_by_krusgraph"] = created_by_krusgraph(nb or {})
        blocked = [dep for dep, conds in a["depends_on"] if done.get(dep) and done[dep] not in conds]
        if blocked:
            row.update(status="NotRun", why=f"it waits for {', '.join(blocked)} to end as its dependsOn asks, which did not "
                                             "happen in this run (read from the pipeline's definition, not from Fabric)")
            done[a["name"]] = "Skipped"
            out.append(row)
            continue
        runs = notebook_runs.get(a.get("notebook_id") or "")
        if a["type"] != ACTIVITY_NOTEBOOK or runs is None:
            row.update(status="unknown", why="no per-activity read for this activity type")
        elif isinstance(runs, dict):
            row.update(status="unknown", why="the notebook's runs could not be read", skipped=runs.get("skipped"))
        else:
            hit = [r for r in runs if _in_window(r, start, end)]
            hit = latest(hit, 1)
            if hit:
                row.update(run(hit[0]))
                row["matched_by"] = ("heuristic: the notebook's own run that started inside this pipeline run's time window "
                                     "(± 60 s); Fabric's activity-run API was not called")
            else:
                row.update(status="unknown", why="the notebook's job list shows no run inside this pipeline run's time window")
        status = row.get("status")
        done[a["name"]] = {"Completed": "Succeeded", "Failed": "Failed", "Cancelled": "Skipped"}.get(status, "")
        out.append(row)
    return out


def summary(item: dict, runs: list[dict]) -> str:
    if not runs:
        return f"{item.get('displayName')}: no runs in Fabric's job list"
    last = runs[0]
    s = f"{item.get('displayName')}: latest run {last.get('status')}"
    if last.get("startTimeUtc"):
        s += f", started {last['startTimeUtc']} UTC"
    failed = [a["activity"] for a in last.get("activities") or [] if a.get("status") == "Failed"]
    if failed:
        s += f"; failed: {', '.join(failed)}"
    d = last.get("diagnosis") or next((a.get("diagnosis") for a in last.get("activities") or [] if a.get("diagnosis")), None)
    if d:
        s += f"; category {d['category']} (heuristic)"
    return s + f"; {len(runs)} run(s) shown"


LIMITS = [
    {"what": "Category and next step", "is": "a heuristic",
     "detail": "The first catalog entry whose pattern occurs in the error text. Several causes can share one text; an error "
               "no entry matches is 'unknown'."},
    {"what": "Per-activity status", "is": "a heuristic",
     "detail": "Each Notebook activity is matched to the notebook's own run that started in the pipeline run's time window; "
               "two pipeline runs at once, or the notebook run by hand meanwhile, can match the wrong run. Activities after a "
               "failed one are 'NotRun' from the definition's dependsOn."},
    {"what": "Which runs", "is": "Fabric's job list",
     "detail": "The latest five runs by start time, of the about 100 completed ones Fabric keeps for the item."},
    {"what": "Error text", "is": "as Fabric returns it",
     "detail": "failureReason's message, errorCode and requestId; cut only past 4 000 characters, and then marked. No row values "
               "are read."},
    {"what": "Krusgraph-created", "is": "read from the description",
     "detail": "The item's description names Krusgraph (the create tools write it); one whose description was changed is not recognised."},
    {"what": "Fixing", "is": "a person's decision",
     "detail": "Granting a role, resuming a capacity, changing a timeout, re-running: the answer suggests, a person does it in Fabric."},
    {"what": "Starting, cancelling, scheduling, changing an item", "is": "never",
     "detail": "Only GET requests and getDefinition; there is no write call in this option."},
]


RUN_TYPES = {"DataPipeline": "dataPipelines", "Notebook": "notebooks"}


def _skipped(item: str, kind: str, exc: BaseException, where: str) -> dict:
    from .lineage import skipped_item
    return skipped_item(item, kind, exc, where)


def find(items: list[dict], name: str) -> dict | None:
    """A pipeline or notebook by display name (case does not matter) or by id."""
    want = (name or "").strip().lower()
    hits = [i for i in items if i.get("type") in RUN_TYPES and want in ((i.get("displayName") or "").lower(), (i.get("id") or "").lower())]
    return hits[0] if hits else None


def answer(workspace_id: str, name: str, items: list[dict], job_instances, definition_parts, hosted: bool) -> dict:
    """The run results of one pipeline or notebook. `job_instances(workspace, item_id)` returns a list of job instances
    (raises on an HTTP error); `definition_parts(workspace, route, item_id)` returns {path: text}. Only reads."""
    import json as _json
    item = find(items, name)
    if item is None:
        kinds = sorted({i.get("displayName") for i in items if i.get("type") in RUN_TYPES})
        return {"error": f"no pipeline or notebook named {name!r} in workspace {workspace_id}", "kind": "not_found",
                "hint": "runs takes a data pipeline's or a notebook's name or id; this workspace has: "
                        + (", ".join(kinds[:30]) or "none")}
    by_id = {i.get("id"): i for i in items}
    out = {"item": {"name": item.get("displayName"), "id": item.get("id"), "type": item.get("type"),
                    "created_by_krusgraph": created_by_krusgraph(item)},
           "runs": [], "skipped": []}
    runs = latest(job_instances(workspace_id, item["id"]))
    acts: list[dict] = []
    if item["type"] == "DataPipeline" and runs:
        try:
            parts = definition_parts(workspace_id, "dataPipelines", item["id"])
            acts = activities(_json.loads(parts.get("pipeline-content.json") or "{}"))
        except Exception as e:  # noqa: BLE001 — reported as skipped, the runs are still shown
            out["skipped"].append(_skipped(item.get("displayName"), "DataPipeline definition", e,
                                           f"reading the definition of the pipeline {item.get('displayName')!r}"))
    nb_runs: dict[str, list[dict] | dict] = {}
    for a in acts:
        nid = a.get("notebook_id")
        if a.get("type") == ACTIVITY_NOTEBOOK and nid and nid not in nb_runs:
            try:
                nb_runs[nid] = job_instances(workspace_id, nid)
            except Exception as e:  # noqa: BLE001
                nb = by_id.get(nid) or {}
                nb_runs[nid] = {"skipped": _skipped(nb.get("displayName") or nid, "Notebook", e,
                                                    f"reading the runs of the notebook {nb.get('displayName') or nid!r}")}
    for r in runs:
        row = run(r)
        if acts:
            row["activities"] = per_activity(r, acts, nb_runs, by_id)
        out["runs"].append(row)
    if not out["skipped"]:
        out.pop("skipped")
    out["summary"] = summary(item, out["runs"])
    out["reads"] = [f"GET /v1/workspaces/{workspace_id}/items/{{id}}/jobs/instances (JobScheduler_ListItemJobInstances)"]
    if item["type"] == "DataPipeline":
        out["reads"].append(f"POST /v1/workspaces/{workspace_id}/dataPipelines/{item['id']}/getDefinition (reads the activities)")
    out["scopes"] = {"needs": [READ_SCOPE] + ([DEFINITION_SCOPE + " for the activities"] if item["type"] == "DataPipeline" else []),
                     "hosted_app": ("The hosted app has these today (Item.Read.All and Item.ReadWrite.All, docs/SCOPES.md)."
                                    if hosted else "The hosted app does not ask for these today; without them Fabric answers 401/403.")}
    out["changes"] = "nothing: no run is started, cancelled or scheduled, and no item is changed"
    out["limits"] = LIMITS
    return out
