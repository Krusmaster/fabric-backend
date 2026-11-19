"""UM2 (19 November 2026): a short weekly usage digest to the founder's existing webhook, so the numbers arrive without
opening /metrics and without the metrics token ever leaving Azure.

What it sends: the same stored daily rows /metrics reads (usage_metrics.Counts.days), as one Adaptive Card. The last
complete ISO week (Monday to Sunday, UTC) next to the week before it: organisations, users, MCP sessions, tool calls,
tool errors and workload API calls; the 5 most used tools, the 3 most common error kinds, the MCP client names, and a
link to https://krusgraph.com/metrics. Counts and the names the counters already hold (tool names, error kinds, client
names) only: never a hash, tenant or object id, user name, e-mail, IP address, workspace/table/column name, the
webhook address or the metrics token.

When: once per ISO week, on Monday 07:00 UTC or the first check after that (every CHECK_EVERY seconds, in a daemon
thread of the running server; no new Azure resource, function or role). A server that is down the whole week does not
send last week's digest late into the next one.

Exactly once across replicas and restarts: before sending, the replica inserts the row RowKey "digest-<YYYY>-W<ww>"
under PartitionKey "usage" in the registration table (Insert Entity, which the Table service refuses with 409 when the
row exists). Only the replica whose insert made the row sends. A lost insert, a table that cannot be read or written,
or no table at all (KRUSGRAPH_REGISTRATION_STORE unset or `memory`): nothing is sent.

Switches: KRUSGRAPH_USAGE_DIGEST=off, or KRUSGRAPH_METRICS=off, and nothing runs. KRUSGRAPH_FOUNDER_WEBHOOK_URL unset
(the state of the hosted app on 19 November 2026): nothing runs and one console line says so, once. The POST has a
10-second timeout and is tried at most twice; a failure is logged by its type only, never with the address.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone

from . import usage_metrics as um

PREFIX = "digest-"
SEND_HOUR = 7                    # Monday 07:00 UTC
CHECK_EVERY = 900                # seconds between two checks per replica
TIMEOUT = 10                     # seconds for the webhook POST
RETRY_AFTER = 30                 # seconds before the one retry
METRICS_URL = "https://krusgraph.com/metrics"
OFF = {"off", "0", "false", "no"}


def enabled() -> bool:
    return um.enabled() and os.environ.get("KRUSGRAPH_USAGE_DIGEST", "on").strip().lower() not in OFF


def _log(event: str, **fields) -> None:
    print(json.dumps({"krusgraph": "usage_digest", "event": event, **fields}), file=sys.stderr, flush=True)


# -------------------------------------------------------------------------------------------------- the week ------
def week_label(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def due(now: float) -> tuple[str, date] | None:
    """(the ISO week label, its Monday) when this week's digest is due: on or after Monday 07:00 UTC. Else None."""
    t = datetime.fromtimestamp(now, timezone.utc)
    monday = t.date() - timedelta(days=t.weekday())
    if t < datetime(monday.year, monday.month, monday.day, SEND_HOUR, tzinfo=timezone.utc):
        return None
    return week_label(monday), monday


# -------------------------------------------------------------------------------------------------- the content ---
def _window(per_day: dict, first: date) -> list[dict]:
    days = {(first + timedelta(days=i)).isoformat() for i in range(7)}
    return [v for k, v in per_day.items() if k in days]


def _totals(sel: list[dict]) -> dict:
    merged = um.fold(sel)
    return {"organisations": um.distinct(sel, "orgs"), "users": um.distinct(sel, "users"), "sessions": merged["sessions"],
            "tool_calls": sum(merged["tools"].values()), "tool_errors": sum(merged["errors"].values()),
            "workload_calls": sum(merged["routes"].values()), "_merged": merged}


def _top(counter: dict, n: int) -> list[list]:
    return [[k, v] for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:n] if v > 0]


def build(per_day: dict, monday: date) -> dict:
    """The digest for the week that ends the day before `monday`, from the merged daily rows (day -> totals) that
    usage_metrics.Counts.days returns. Numbers and counter names only."""
    last_first, prev_first = monday - timedelta(days=7), monday - timedelta(days=14)
    cur, prev = _totals(_window(per_day, last_first)), _totals(_window(per_day, prev_first))
    merged = cur.pop("_merged")
    prev.pop("_merged")
    kinds: dict[str, int] = {}
    for key, v in merged["errors"].items():
        kind = key.rsplit(":", 1)[-1] if ":" in key else key
        kinds[kind] = kinds.get(kind, 0) + int(v)
    return {"week": week_label(last_first), "from": last_first.isoformat(), "to": (monday - timedelta(days=1)).isoformat(),
            "this_week": cur, "week_before": prev, "top_tools": _top(merged["tools"], 5),
            "top_error_kinds": _top(kinds, 3), "clients": _top(merged["clients"], 10), "details": METRICS_URL}


LABELS = (("organisations", "Organisationer"), ("users", "Användare"), ("sessions", "MCP-sessioner"),
          ("tool_calls", "Verktygsanrop"), ("tool_errors", "Verktygsfel"), ("workload_calls", "Workload-API-anrop"))


def _list(pairs: list[list]) -> str:
    return ", ".join(f"{k} {v}" for k, v in pairs) or "inga"


def card(d: dict) -> dict:
    """The digest as the founder webhook's Adaptive Card message (billing.card_message, the same envelope as the
    trial notices)."""
    from .billing import card_message
    facts = [{"title": label, "value": f"{d['this_week'][key]} (veckan före: {d['week_before'][key]})"} for key, label in LABELS]
    lines = [f"Mest använda verktyg: {_list(d['top_tools'])}", f"Vanligaste fel: {_list(d['top_error_kinds'])}",
             f"MCP-klienter: {_list(d['clients'])}", f"Se /metrics för detaljer: {d['details']}"]
    week = d["week"].split("-W")[-1].lstrip("0")
    body = [{"type": "TextBlock", "text": f"Krusgraph vecka {week}: användning", "weight": "Bolder", "size": "Medium", "wrap": True},
            {"type": "TextBlock", "text": f"{d['from']} till {d['to']} (UTC)", "isSubtle": True, "spacing": "None", "wrap": True},
            {"type": "FactSet", "facts": facts}]
    body += [{"type": "TextBlock", "text": x, "wrap": True, "spacing": "Small"} for x in lines]
    return card_message(body)


# -------------------------------------------------------------------------------------------------- sending -------
class Digest:
    """One replica's sender. tick() checks once and says what it did; the thread calls it every CHECK_EVERY seconds."""

    def __init__(self, counts=None, post=None, clock=time.time, sleep=time.sleep) -> None:
        self.counts = counts if counts is not None else um.counts
        self.post = post
        self.clock, self.sleep = clock, sleep
        self.done: set[str] = set()              # weeks this replica already settled (sent, or lost the insert)
        self._said_no_webhook = False

    def _post(self, message: dict) -> bool:
        if self.post is not None:
            return bool(self.post(message))
        from .billing import post_founder_card
        return post_founder_card(message, timeout=TIMEOUT)

    def tick(self) -> str:
        if not enabled():
            return "off"
        from .billing import founder_webhook_url
        if not founder_webhook_url():
            if not self._said_no_webhook:
                self._said_no_webhook = True
                _log("no_webhook", note="KRUSGRAPH_FOUNDER_WEBHOOK_URL is not set; no weekly digest is sent")
            return "no_webhook"
        when = due(self.clock())
        if when is None:
            return "not_due"
        week, monday = when
        if week in self.done:
            return "done"
        if not self.counts.durable:
            return "no_table"
        today = datetime.fromtimestamp(self.clock(), timezone.utc).date()
        per_day = self.counts.days((today - (monday - timedelta(days=14))).days + 1)
        if self.counts.last_error:               # the rows could not be read: try again at the next check
            return "read_failed"
        try:
            won = self.counts.rows.add(PREFIX + week, {"week": week, "claimed": datetime.fromtimestamp(
                self.clock(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
        except Exception as exc:  # noqa: BLE001 — logged by type; nothing is sent without the row
            _log("claim_failed", week=week, error=type(exc).__name__)
            return "claim_failed"
        self.done.add(week)
        if not won:
            return "taken"
        message = card(build(per_day, monday))
        sent = self._post(message)
        if not sent:
            self.sleep(RETRY_AFTER)
            sent = self._post(message)
        _log("sent" if sent else "send_failed", week=week)
        return "sent" if sent else "send_failed"


_thread: threading.Thread | None = None
_said_no_webhook = False


def start(counts=None) -> bool:
    """The daemon thread, started once by server.build_app. Off switches or no webhook: no thread (one line for the
    missing webhook)."""
    global _thread
    if not enabled() or (_thread is not None and _thread.is_alive()):
        return False
    digest = Digest(counts)
    from .billing import founder_webhook_url
    if not founder_webhook_url():
        global _said_no_webhook
        if not _said_no_webhook:                 # the one console line per process
            _said_no_webhook = True
            digest.tick()
        return False

    def loop():
        while True:
            time.sleep(60)
            try:
                digest.tick()
            except Exception as exc:  # noqa: BLE001 — the next check tries again
                _log("failed", error=type(exc).__name__)
            time.sleep(max(60, CHECK_EVERY - 60))
    _thread = threading.Thread(target=loop, name="krusgraph-usage-digest", daemon=True)
    _thread.start()
    return True
