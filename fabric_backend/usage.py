"""Anonymous usage statistics: how often each tool is called, how it ends, and how long it takes.

What one call records, and nothing else:
  tool        the tool's name (plan_backend, create_views, ...)
  outcome     "ok", or the error `kind` the tool answered with (not_found, consent, rate_limited, ...)
  ms          the duration in milliseconds
  dry_run     for the creating tools: whether it ran as a dry run (absent for the others)
  org         only when KRUSGRAPH_USAGE_SALT is set: the first 16 hex characters of SHA-256(salt + tenant id), so
              organisations can be counted without the tenant id being written down; without the salt, no org field
Never: user ids, names, e-mail, IP addresses, workspace/item/table/column names, queries, plans or results.

Where it goes:
  - one JSON line per call on stdout (event "krusgraph.tool_call"); Container Apps hands stdout to Log Analytics when
    the environment has a Log Analytics destination (docs/OPERATIONS.md), otherwise it is only in the live console
    stream. KRUSGRAPH_USAGE_LOG=0 turns the line off.
  - totals since the replica started, served at /metrics in the Prometheus text format, only when
    KRUSGRAPH_METRICS_TOKEN is set and the request carries it as a bearer token; /metrics is a 404 otherwise.
The privacy page (/privacy) lists the same fields; a test keeps the two in step.

Two more kinds of line, for the site (n39), with no field beyond these:
  krusgraph.page_view   path   one of PAGE_VIEW_PATHS, served as HTML (no IP, referrer, user agent or query string)
  krusgraph.check       step   "loaded" (the engine started in the visitor's browser) or "done" (a check finished);
                               /check sends no file, file name, table or column name: the step is all the request says

n240: campaign counts for /check, without cookies or personal data. A visit to /check and its check events may carry
the address's utm_source, utm_medium and utm_campaign (each lower-cased; a value outside [a-z0-9_.-], or longer than 64
characters, is counted as "(other)"; an absent one is left out of the line and counted as "(none)"). On the "done" event
the page adds `kind` ("sample" for one of the examples, "real" for the visitor's own files or columns) and `first`
(true for the first check of that page load, so visits that ran a check can be counted without anything kept in the
browser). The same fields go on the console line; per UTC day and per (source, medium, campaign) the replica keeps
totals in memory (CAMPAIGN_DAYS days, at most CAMPAIGN_KEYS combinations a day), readable at /admin/campaigns with the
/metrics token. No IP address, user agent, referrer, cookie or identifier is read or kept.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone

FIELDS = ("tool", "outcome", "ms", "dry_run", "org")              # everything a usage line can carry (privacy page lists these)
PAGE_VIEW_PATHS = ("/", "/check", "/start", "/partners")   # n158: not /explore, a redirect the server never counts (review L13)
CHECK_STEPS = ("loaded", "done")
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign")
CHECK_KINDS = ("sample", "real")
CAMPAIGN_DAYS = 120                                              # days of per-day totals kept in memory
CAMPAIGN_KEYS = 200                                              # (source, medium, campaign) combinations per day; more go to "(other)"
NONE, OTHER = "(none)", "(other)"
_UTM_OK = re.compile(r"[a-z0-9][a-z0-9_.\-]{0,63}")
BUCKETS = (0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120)          # seconds; Fabric calls take from a tenth of a second to minutes
_write_lock = threading.Lock()


def _emit(line: str) -> None:
    """One line on stdout (looked up at each call, so a redirected stdout is honoured), never interleaved."""
    with _write_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def outcome_of(text) -> str:
    """'ok', or the top-level `kind` of a tool's JSON answer when it carries an `error` (the shape errors.safe and the
    tools' own refusals give). Only the kind is read; the answer itself is never kept."""
    if not isinstance(text, str) or not text.lstrip().startswith("{") or '"error"' not in text:
        return "ok"
    try:
        body = json.loads(text)
    except ValueError:
        return "ok"
    if isinstance(body, dict) and body.get("error") and isinstance(body.get("kind"), str):
        return body["kind"][:40]
    return "error" if isinstance(body, dict) and body.get("error") else "ok"


def org_hash(tid: str | None, salt: str | None = None) -> str | None:
    salt = os.environ.get("KRUSGRAPH_USAGE_SALT", "") if salt is None else salt
    if not tid or not salt:
        return None
    return hashlib.sha256((salt + str(tid).lower()).encode()).hexdigest()[:16]


def _log_on() -> bool:
    return os.environ.get("KRUSGRAPH_USAGE_LOG", "1").strip().lower() not in {"0", "off", "false", "no"}


def utm_of(params) -> dict[str, str]:
    """The three utm_* values of a query string (any mapping with .get), cleaned: lower-cased and trimmed; a value outside
    [a-z0-9_.-] or over 64 characters becomes "(other)", so nothing free-form (an e-mail, a name) is ever written down.
    Absent or empty values are left out. Nothing else of the query string is read."""
    out = {}
    for k in UTM_KEYS:
        v = (params.get(k) or "").strip().lower() if params is not None else ""
        if v:
            out[k] = v if _UTM_OK.fullmatch(v) else OTHER
    return out


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class Campaigns:
    """Per UTC day and per (utm_source, utm_medium, utm_campaign): visits to /check, engines loaded, checks done (by kind)
    and visits that ran at least one check. In memory, per replica, since it started; bounded in days and keys."""
    COUNTS = ("visits", "engine_loaded", "checks", "checks_sample", "checks_real", "visits_with_check")

    def __init__(self, today=_today) -> None:
        self._lock = threading.Lock()
        self._today = today
        self.started = time.time()
        self.days: dict[str, dict[tuple[str, str, str], dict[str, int]]] = {}

    def add(self, counter: str, utm: dict | None) -> None:
        utm = utm or {}
        key = tuple(utm.get(k, NONE) for k in UTM_KEYS)
        day = self._today()
        with self._lock:
            rows = self.days.setdefault(day, {})
            if key not in rows and len(rows) >= CAMPAIGN_KEYS:
                key = (OTHER, OTHER, OTHER)
            row = rows.setdefault(key, dict.fromkeys(self.COUNTS, 0))
            row[counter] += 1
            for old in sorted(self.days)[:-CAMPAIGN_DAYS]:
                del self.days[old]

    def report(self) -> dict:
        """The totals as JSON: one entry per day (newest first), one row per campaign, and the day's sum."""
        with self._lock:
            days = {d: {k: dict(v) for k, v in rows.items()} for d, rows in self.days.items()}
        out = []
        for day in sorted(days, reverse=True):
            rows = [{"utm_source": k[0], "utm_medium": k[1], "utm_campaign": k[2], **v}
                    for k, v in sorted(days[day].items(), key=lambda kv: (-kv[1]["visits"], kv[0]))]
            total = {c: sum(r[c] for r in rows) for c in self.COUNTS}
            out.append({"day": day, "total": total, "campaigns": rows})
        return {"what": "Visits to /check and the checks run from them, per UTC day and utm_source/utm_medium/utm_campaign. "
                        "No cookies, IP addresses or identifiers: each row is a count. visits_with_check counts page loads "
                        "that finished at least one check; checks counts every finished check (sample: an example, real: "
                        "the visitor's own files or columns).",
                "scope": "this replica, in memory, since it started; the console lines (krusgraph.page_view, krusgraph.check) "
                         "in Log Analytics carry the same fields for every replica and restart",
                "replica_started": datetime.fromtimestamp(self.started, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "days": out}


campaigns = Campaigns()


def page_view(path: str, utm: dict | None = None) -> dict | None:
    """One krusgraph.page_view line for the pages in PAGE_VIEW_PATHS; None (and nothing written) for any other path.
    n240: on /check, the cleaned utm values (utm_of) go on the line and the visit is counted per day and campaign."""
    if path not in PAGE_VIEW_PATHS:
        return None
    line = {"event": "krusgraph.page_view", "path": path}
    if path == "/check":
        line.update(utm or {})
        campaigns.add("visits", utm)
    if _log_on():
        _emit(json.dumps(line, separators=(",", ":")))
    return line


def check_event(step: str, kind: str | None = None, first: bool = False, utm: dict | None = None) -> dict | None:
    """One krusgraph.check line for a step in CHECK_STEPS; anything else is ignored. n240: `kind` (sample or real) and
    `first` on "done", and the visit's cleaned utm values, counted per day and campaign."""
    if step not in CHECK_STEPS:
        return None
    line = {"event": "krusgraph.check", "step": step}
    if step == "done" and kind in CHECK_KINDS:
        line["kind"] = kind
        if first:
            line["first"] = True
    line.update(utm or {})
    if step == "loaded":
        campaigns.add("engine_loaded", utm)
    else:
        campaigns.add("checks", utm)
        if kind in CHECK_KINDS:
            campaigns.add("checks_" + kind, utm)
        if first:
            campaigns.add("visits_with_check", utm)
    if _log_on():
        _emit(json.dumps(line, separators=(",", ":")))
    return line


class Usage:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started = time.time()
        self.calls: dict[tuple[str, str], int] = {}
        self.durations: dict[str, list] = {}                    # tool -> [bucket counts..., sum, count]
        self.orgs: set[str] = set()

    def record(self, tool: str, outcome: str, seconds: float, dry_run: bool | None = None, tid: str | None = None) -> dict:
        org = org_hash(tid)
        with self._lock:
            self.calls[(tool, outcome)] = self.calls.get((tool, outcome), 0) + 1
            d = self.durations.setdefault(tool, [0] * len(BUCKETS) + [0.0, 0])
            for i, edge in enumerate(BUCKETS):
                if seconds <= edge:
                    d[i] += 1
            d[-2] += seconds
            d[-1] += 1
            if org:
                self.orgs.add(org)
        line = {"event": "krusgraph.tool_call", "tool": tool, "outcome": outcome, "ms": int(round(seconds * 1000))}
        if dry_run is not None:
            line["dry_run"] = bool(dry_run)
        if org:
            line["org"] = org
        if _log_on():
            _emit(json.dumps(line, separators=(",", ":")))
        return line

    def prometheus(self) -> str:
        """Totals since this replica started, in the Prometheus text exposition format."""
        def esc(v: str) -> str:
            return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
        with self._lock:
            calls = dict(self.calls)
            durations = {k: list(v) for k, v in self.durations.items()}
            orgs = len(self.orgs)
        out = ["# HELP krusgraph_tool_calls_total Tool calls by tool and outcome (ok or the error kind) since this replica started.",
               "# TYPE krusgraph_tool_calls_total counter"]
        out += [f'krusgraph_tool_calls_total{{tool="{esc(t)}",outcome="{esc(o)}"}} {n}' for (t, o), n in sorted(calls.items())]
        out += ["# HELP krusgraph_tool_duration_seconds How long tool calls took.", "# TYPE krusgraph_tool_duration_seconds histogram"]
        for t, d in sorted(durations.items()):
            out += [f'krusgraph_tool_duration_seconds_bucket{{tool="{esc(t)}",le="{edge}"}} {d[i]}' for i, edge in enumerate(BUCKETS)]
            out += [f'krusgraph_tool_duration_seconds_bucket{{tool="{esc(t)}",le="+Inf"}} {d[-1]}',
                    f'krusgraph_tool_duration_seconds_sum{{tool="{esc(t)}"}} {round(d[-2], 6)}',
                    f'krusgraph_tool_duration_seconds_count{{tool="{esc(t)}"}} {d[-1]}']
        if os.environ.get("KRUSGRAPH_USAGE_SALT"):
            out += ["# HELP krusgraph_organisations_seen Distinct organisations (salted hashes of the tenant id, never listed) since this replica started.",
                    "# TYPE krusgraph_organisations_seen gauge", f"krusgraph_organisations_seen {orgs}"]
        out += ["# HELP krusgraph_uptime_seconds Seconds since this replica started.", "# TYPE krusgraph_uptime_seconds gauge",
                f"krusgraph_uptime_seconds {int(time.time() - self.started)}"]
        return "\n".join(out) + "\n"


usage = Usage()
