"""A 30-day trial per organisation, then a Microsoft Marketplace subscription (round n213; docs/BILLING-MODEL.md).

Off unless KRUSGRAPH_TRIAL=1. With the switch off nothing here runs, no row is written and no tool or route changes
(tests/test_n213_trial.py locks that). Self-hosted Krusgraph never sets it: the open-source server stays free.

The organisation is the Microsoft Entra tenant id (`tid`) of the signed-in user's token, on both products:

  the hosted MCP server   server._instrumented: every tool call with a valid token
  the Fabric workload     workload_api.routes: every /workload/v1 call with a valid token (opening the Krusgraph Model
                          item calls /workload/v1/access, so opening the item is enough)

The first authenticated call from a tenant starts its trial: one row in the same table the Marketplace subscriptions
live in (KRUSGRAPH_ENTITLEMENTS_TABLE, marketplace.store()), PartitionKey "trial", RowKey the tenant id, with
first_seen, trial_ends (first_seen + 30 days), the product that was first, and the dates the founder notices were
sent. No names, no e-mail addresses, no object ids: users are kept only as a salted hash (below).

One decision (decide): an active Marketplace subscription, a running trial or an exempt tenant -> allowed; otherwise a
call that writes to Fabric is refused and every read, check and dry run still runs. With KRUSGRAPH_TRIAL=1 this replaces
the feature split of entitlements.py: during the trial and the subscription everything is open, after it only writing
is closed. A call writes when it is one of the creating tools (switches.creates) with dry_run=false, or the workload's
/build or /product retire with dry_run=false.

Exempt, never gated and never counted: the publisher's own tenant (KRUSGRAPH_PUBLISHER_TENANT_ID, else
KRUSGRAPH_MARKETPLACE_TENANT_ID), which also covers a B2B guest working in the publisher's tenant (the guest's token
carries the publisher's tid, so no trial starts for the guest's own organisation), and the pilot tenants in
KRUSGRAPH_TRIAL_EXEMPT_TENANTS (tenant ids separated by commas or spaces).

Users per organisation (the plan's cap): each user is kept as HMAC-SHA256(KRUSGRAPH_USER_HASH_SALT, tid:oid), the first
24 hex characters, with the last day seen, in the tenant's row; entries older than 30 days are dropped, and the count is
what is left. The salt is a container-app secret, never in code; without it no user is counted. Over the plan's cap
(KRUSGRAPH_PLAN_USER_CAPS, JSON {"<plan id>": <users>}) the users see one line and the founder gets an event. Nothing
is blocked for being over the cap.

Founder notices: one JSON line on the console per event ({"krusgraph": "billing", "event": ...}): trial_started,
trial_ends_soon (7 days before the end; on a call from the tenant or in the sweep that runs every 6 hours) and
plan_over_cap (at most once per tenant in 30 days). docs/OPERATIONS.md turns them into an Azure Monitor e-mail alert.
With KRUSGRAPH_FOUNDER_WEBHOOK_URL set (a container-app secret: a Teams workflow or Power Automate HTTP trigger, as in
n200) the same event is also posted as an Adaptive Card; the address is never logged.

A store that cannot be read refuses writing for that call and says so (the rule entitlements.py has); reading never
depends on the store.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
import re
import sys
import threading
import time

TRIAL_DAYS = 30
NOTICE_DAYS = 7
USER_WINDOW_DAYS = 30
CAP_EVENT_EVERY_DAYS = 30
PARTITION = "trial"
ROW_TTL = 60                        # seconds a tenant's row is cached for the decision
SWEEP_EVERY = 6 * 3600
MAX_USERS_KEPT = 2000               # a row stays far below the table's 64 KiB property limit
_ON = {"1", "true", "yes", "on"}
_GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
DAY = 86400

log = logging.getLogger("krusgraph.billing")


def enabled(environ=None) -> bool:
    return (os.environ if environ is None else environ).get("KRUSGRAPH_TRIAL", "0").strip().lower() in _ON


def publisher_tenant() -> str:
    return (os.environ.get("KRUSGRAPH_PUBLISHER_TENANT_ID", "").strip()
            or os.environ.get("KRUSGRAPH_MARKETPLACE_TENANT_ID", "").strip()).lower()


def exempt_tenants() -> set[str]:
    raw = os.environ.get("KRUSGRAPH_TRIAL_EXEMPT_TENANTS", "")
    found = {t.strip().lower() for t in re.split(r"[\s,;]+", raw) if t.strip()}
    pub = publisher_tenant()
    return {t for t in found | ({pub} if pub else set()) if _GUID.match(t)}


def exempt(tid: str | None) -> bool:
    return bool(tid) and tid.lower() in exempt_tenants()


def offer_url() -> str:
    from .entitlements import upgrade_url
    return upgrade_url()


def plan_caps() -> dict[str, int]:
    raw = os.environ.get("KRUSGRAPH_PLAN_USER_CAPS", "").strip() or "{}"
    try:
        caps = json.loads(raw)
    except ValueError:
        return {}
    return {str(k).lower(): int(v) for k, v in caps.items() if isinstance(v, int) and v > 0} if isinstance(caps, dict) else {}


def user_hash(tid: str, oid: str, salt: str) -> str:
    """The only form a user is kept in: never the object id itself."""
    return hmac.new(salt.encode("utf-8"), f"{tid.lower()}:{oid.lower()}".encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _day(t: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(t))


def _parse(iso: str) -> float:
    import calendar
    return float(calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")))


def date_words(iso: str) -> str:
    t = time.gmtime(_parse(iso))
    return f"{t.tm_mday} {time.strftime('%B %Y', t)}"


# ------------------------------------------------------------------ founder notices -------------------------------------

def _default_emit(event: dict) -> None:
    sys.stdout.write(json.dumps({"krusgraph": "billing", **event}, separators=(",", ":")) + "\n")   # starts {"krusgraph":"billing"
    sys.stdout.flush()
    url = os.environ.get("KRUSGRAPH_FOUNDER_WEBHOOK_URL", "").strip()
    if url.lower().startswith("https://"):
        threading.Thread(target=_post_card, args=(url, event), daemon=True).start()


def founder_card(event: dict) -> dict:
    """The Adaptive Card for the optional Teams / Power Automate webhook (the n200 shape): the event's own fields only."""
    titles = {"trial_started": "A new organisation started a Krusgraph trial",
              "trial_ends_soon": "A Krusgraph trial ends in 7 days or less",
              "plan_over_cap": "An organisation is over its plan's number of users"}
    lines = [f"{k}: {v}" for k, v in sorted(event.items()) if k != "event"]
    body = [{"type": "TextBlock", "text": titles.get(event.get("event"), str(event.get("event"))), "weight": "Bolder",
             "size": "Medium", "wrap": True}] + [{"type": "TextBlock", "text": x, "wrap": True, "spacing": "Small"} for x in lines]
    return {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None,
                                                "content": {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                                                            "type": "AdaptiveCard", "version": "1.4", "body": body}}]}


def _post_card(url: str, event: dict) -> None:
    import urllib.request
    try:
        req = urllib.request.Request(url, data=json.dumps(founder_card(event)).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15):
            pass
    except Exception as e:  # noqa: BLE001 — the address carries its own signature and is never shown
        log.warning("founder webhook not sent (%s)", type(e).__name__)


# ------------------------------------------------------------------ the trial rows --------------------------------------

class Trials:
    """The trial rows, in the Marketplace store (marketplace.MemoryStore or TableStore: get, put with etag, query)."""

    def __init__(self, store, clock=time.time, emit=None, salt: str | None = None) -> None:
        self.store, self.clock = store, clock
        self.emit = emit or _default_emit
        self._salt = salt
        self._cache: dict[str, tuple[dict | None, float]] = {}
        self._seen: set[tuple[str, str, str]] = set()          # (tid, user hash, day) already written by this replica
        self._lock = threading.Lock()

    def salt(self) -> str:
        return self._salt if self._salt is not None else os.environ.get("KRUSGRAPH_USER_HASH_SALT", "").strip()

    def row(self, tid: str, cached: bool = True) -> dict | None:
        tid = tid.lower()
        with self._lock:
            hit = self._cache.get(tid)
            if cached and hit and self.clock() - hit[1] < ROW_TTL:
                return hit[0]
        row, _ = self.store.get(PARTITION, tid)
        with self._lock:
            self._cache[tid] = (row, self.clock())
        return row

    def _keep(self, tid: str, row: dict) -> None:
        with self._lock:
            self._cache[tid] = (row, self.clock())

    def _update(self, tid: str, change) -> dict:
        """Read, change and write back with the etag; another replica's write first means read and try again."""
        for _ in range(5):
            row, etag = self.store.get(PARTITION, tid)
            new = change(dict(row) if row else None)
            if new is None:
                if row:
                    self._keep(tid, row)
                return row or {}
            new = {k: v for k, v in new.items() if not k.startswith("_")}
            if self.store.put(new, etag if row else ""):
                self._keep(tid, new)
                return new
        raise RuntimeError("the trial row kept changing while it was written")

    def touch(self, tid: str, oid: str | None, product: str, subscribed: bool = False) -> dict | None:
        """The first call from a tenant starts its trial; every call counts its user once a day per replica. Exempt
        tenants are not written at all. Returns the tenant's row (None for an exempt tenant)."""
        tid = (tid or "").lower()
        if not tid or exempt(tid):
            return None
        now = self.clock()
        row = self.row(tid)
        events: list[dict] = []
        if row is None:
            def start(old):
                if old is not None:
                    return None
                return {"PartitionKey": PARTITION, "RowKey": tid, "first_seen": _iso(now), "trial_ends": _iso(now + TRIAL_DAYS * DAY),
                        "first_product": product, "users": "{}", "notice_sent": "", "cap_warned": ""}
            before = self.store.get(PARTITION, tid)[0]
            row = self._update(tid, start)
            if before is None and row.get("first_seen") == _iso(now) and not subscribed:
                events.append({"event": "trial_started", "tenant": tid, "product": product, "first_seen": row["first_seen"],
                               "trial_ends": row["trial_ends"]})
        salt = self.salt()
        if oid and salt:
            h = user_hash(tid, oid, salt)
            key = (tid, h, _day(now))
            if key not in self._seen:
                def count(old):
                    old = old or {}
                    try:
                        users = json.loads(old.get("users") or "{}")
                    except ValueError:
                        users = {}
                    cutoff = _day(now - USER_WINDOW_DAYS * DAY)
                    users = {k: v for k, v in users.items() if v > cutoff}
                    if users.get(h) == _day(now):
                        return None
                    users[h] = _day(now)
                    if len(users) > MAX_USERS_KEPT:
                        users = dict(sorted(users.items(), key=lambda kv: kv[1])[-MAX_USERS_KEPT:])
                    return {**old, "users": json.dumps(users, sort_keys=True)}
                row = self._update(tid, count)
                self._seen.add(key)
        if not subscribed:
            events += self._notice_due(tid, row, now)
        for e in events:
            self.emit(e)
        return row

    def users(self, row: dict | None, now: float | None = None) -> int:
        try:
            users = json.loads((row or {}).get("users") or "{}")
        except ValueError:
            return 0
        cutoff = _day((now if now is not None else self.clock()) - USER_WINDOW_DAYS * DAY)
        return sum(1 for v in users.values() if v > cutoff)

    def _notice_due(self, tid: str, row: dict | None, now: float) -> list[dict]:
        """trial_ends_soon once per tenant, from 7 days before the end until the end."""
        if not row or row.get("notice_sent") or not row.get("trial_ends"):
            return []
        ends = _parse(row["trial_ends"])
        if not (ends - NOTICE_DAYS * DAY <= now < ends):
            return []
        claimed = {"done": False}

        def mark(old):
            if not old or old.get("notice_sent"):
                return None
            claimed["done"] = True
            return {**old, "notice_sent": _iso(now)}
        self._update(tid, mark)
        if not claimed["done"]:
            return []
        return [{"event": "trial_ends_soon", "tenant": tid, "trial_ends": row["trial_ends"],
                 "days_left": days_left(row["trial_ends"], now)}]

    def over_cap(self, tid: str, row: dict | None, plan: str, now: float | None = None) -> dict | None:
        """The plan's cap and the count when the tenant is over it; the founder event at most once in 30 days."""
        now = self.clock() if now is None else now
        cap = plan_caps().get((plan or "").lower())
        n = self.users(row, now)
        if not cap or n <= cap:
            return None
        last = (row or {}).get("cap_warned") or ""
        if not last or _parse(last) < now - CAP_EVENT_EVERY_DAYS * DAY:
            claimed = {"done": False}

            def mark(old):
                if not old or (old.get("cap_warned") and _parse(old["cap_warned"]) >= now - CAP_EVENT_EVERY_DAYS * DAY):
                    return None
                claimed["done"] = True
                return {**old, "cap_warned": _iso(now)}
            try:
                self._update(tid, mark)
            except Exception:  # noqa: BLE001 — a warning never breaks a call
                claimed["done"] = False
            if claimed["done"]:
                self.emit({"event": "plan_over_cap", "tenant": tid, "plan": plan, "cap": cap, "users_30_days": n})
        return {"cap": cap, "users": n, "plan": plan}

    def sweep(self) -> int:
        """Every trial row: send trial_ends_soon where it is due. Returns how many were sent."""
        now, sent = self.clock(), 0
        for row in self.store.query(PARTITION):
            tid = str(row.get("RowKey") or "").lower()
            if not tid or exempt(tid) or _subscribed(tid):
                continue
            for e in self._notice_due(tid, row, now):
                self.emit(e)
                sent += 1
        return sent


def days_left(trial_ends: str, now: float) -> int:
    return max(0, math.ceil((_parse(trial_ends) - now) / DAY))


_trials: Trials | None = None
_trials_lock = threading.Lock()


def trials() -> Trials:
    global _trials
    with _trials_lock:
        if _trials is None:
            from . import marketplace
            _trials = Trials(marketplace.store().store)
        return _trials


def set_trials(t: Trials | None) -> None:
    global _trials
    with _trials_lock:
        _trials = t


def _subscription(tid: str) -> dict | None:
    from . import marketplace
    if not marketplace.enabled():
        return None
    row = marketplace.store().tenant(tid)
    return row if row and row.get("status") in marketplace.ACTIVE else None


def _subscribed(tid: str) -> bool:
    try:
        return _subscription(tid) is not None
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------ the decision ----------------------------------------

def decide(tid: str | None, oid: str | None = None, *, write: bool, product: str) -> dict:
    """The one decision for both products. Records the call (touch) first, so the first call starts the trial.

    Returns {allowed, state, days_left, trial_ends, offer_url, words, refusal?, notice?}; state is off, exempt,
    subscribed, trial, ended or unknown. `refusal` (an error answer: error, kind upgrade, hint, upgrade_url) is there
    only when allowed is false; `words` is the one quiet line for the editor ("" when there is nothing to say)."""
    if not enabled():
        return {"allowed": True, "state": "off", "words": ""}
    url = offer_url()
    if not tid:
        return {"allowed": True, "state": "unknown", "words": "", "offer_url": url}
    tid = tid.lower()
    if exempt(tid):
        return {"allowed": True, "state": "exempt", "words": "", "offer_url": url}
    t = trials()
    try:
        sub = _subscription(tid)
        row = t.touch(tid, oid, product, subscribed=sub is not None)
    except Exception as e:  # noqa: BLE001 — an unreadable store closes writing for this call, never reading
        note = f"Krusgraph could not check your organisation's trial or subscription just now ({type(e).__name__})"
        out = {"allowed": not write, "state": "unknown", "words": "", "offer_url": url}
        if write:
            out["refusal"] = {"error": note + ", so nothing was created or changed in Fabric.", "kind": "upgrade",
                              "upgrade_url": url, "hint": "Try again in a minute. Reading, checks and dry runs (dry_run=true) "
                                                          "still work."}
        return out
    if sub is not None:
        out = {"allowed": True, "state": "subscribed", "words": "", "offer_url": url, "plan": sub.get("plan", "")}
        cap = t.over_cap(tid, row, sub.get("plan", ""))
        if cap:
            out["notice"] = out["words"] = (
                f"Your organisation's Krusgraph plan covers up to {cap['cap']} users, and {cap['users']} people used it in "
                f"the last 30 days. Nothing is blocked; an administrator can change the plan in Microsoft Marketplace.")
        return out
    ends = (row or {}).get("trial_ends", "")
    now = t.clock()
    left = days_left(ends, now) if ends else 0
    if ends and now < _parse(ends):
        words = (f"Trial: {left} day{'s' if left != 1 else ''} left (until {date_words(ends)}). Subscribe through "
                 f"Microsoft Marketplace: {url}")
        out = {"allowed": True, "state": "trial", "days_left": left, "trial_ends": ends, "offer_url": url, "words": words}
        if left <= NOTICE_DAYS:
            out["notice"] = (f"Your organisation's 30-day Krusgraph trial ends on {date_words(ends)}. After that, reading, "
                             f"checks and dry runs keep working, and creating or changing anything in Fabric needs a "
                             f"subscription: {url}")
        return out
    ended = date_words(ends) if ends else "earlier"
    words = (f"Trial ended on {ended}. Reading, checks and dry runs still work; Create needs a subscription: {url}")
    out = {"allowed": not write, "state": "ended", "days_left": 0, "trial_ends": ends, "offer_url": url, "words": words}
    if write:
        out["refusal"] = {
            "error": (f"Your organisation's 30-day Krusgraph trial ended on {ended}, and it has no active subscription, so "
                      "Krusgraph does not create or change anything in Fabric for it now. Nothing was created or changed."),
            "kind": "upgrade", "feature": "write", "upgrade_url": url, "trial_ends": ends, "days_left": 0,
            "hint": (f"Reading, checks and dry runs (dry_run=true) still work. An administrator or purchaser in your "
                     f"organisation can subscribe once for everyone through Microsoft Marketplace (Microsoft bills): {url}. "
                     "Items Krusgraph already made stay yours and can be changed or deleted in Fabric itself.")}
    return out


def tool_writes(name: str, dry_run: bool | None) -> bool:
    """An MCP tool call writes to Fabric: a creating tool (switches.creates) called with dry_run=false."""
    from . import switches
    return switches.creates(name, switches.KNOWN.get(name)) and dry_run is False


def route_writes(where: str, req: dict) -> bool:
    """A workload call writes to Fabric: /build or /product retire, with dry_run=false."""
    if where == "build":
        return req.get("dry_run") is False
    if where == "product":
        return req.get("action") == "retire" and req.get("dry_run") is False
    return False


def with_notice(text: str, notice: str | None) -> str:
    """Adds `billing_notice` to a tool's JSON object answer (an answer that is not a JSON object is left as it is)."""
    if not notice or not isinstance(text, str) or not text.lstrip().startswith("{"):
        return text
    try:
        body = json.loads(text)
    except ValueError:
        return text
    if not isinstance(body, dict) or "error" in body:
        return text
    body["billing_notice"] = notice
    return json.dumps(body, indent=2)


# ------------------------------------------------------------------ the sweep ------------------------------------------

_sweeper: threading.Thread | None = None


def start_sweeper(every: float = SWEEP_EVERY) -> bool:
    """A daemon thread that runs Trials.sweep every 6 hours (each replica; the row's notice_sent, written with its etag,
    keeps the event to one). Started by server.build_app only with KRUSGRAPH_TRIAL=1."""
    global _sweeper
    if not enabled() or (_sweeper is not None and _sweeper.is_alive()):
        return False

    def loop():
        while True:
            time.sleep(60)
            try:
                trials().sweep()
            except Exception as e:  # noqa: BLE001 — logged by type; the next sweep tries again
                log.warning("trial sweep failed (%s)", type(e).__name__)
            time.sleep(max(60.0, every - 60))
    _sweeper = threading.Thread(target=loop, name="krusgraph-trial-sweep", daemon=True)
    _sweeper.start()
    return True
