"""UM1 (18 November 2026): anonymous usage counts per UTC day, kept across restarts and replicas, for the operator's
/metrics page. It builds on usage.py (the per-call console line and the Prometheus totals since a replica started),
which it leaves as it is.

What is counted, per UTC day, and nothing else:
  orgs         distinct organisations: HMAC-SHA256(KRUSGRAPH_USAGE_SALT, tenant id), 16 hex characters. Never the id.
  users        distinct signed-in users: HMAC-SHA256(salt, tenant id + object id), 16 hex characters. Never the ids.
               Without KRUSGRAPH_USAGE_SALT neither is counted (no hash is made at all).
  sessions     MCP connections: the `initialize` requests that reach /mcp
  clients      the name an MCP client gives in `initialize` (clientInfo.name, e.g. "claude-ai", "cursor"), lower-cased;
               a name outside [a-z0-9 ._-] or over 40 characters is counted as "(other)"; none sent is "(none)"
  tools        tool calls per tool name
  errors       per tool and error kind (the `kind` a tool answers with: not_found, consent, rate_limited, ...)
  routes       Fabric workload API calls per route (review, build, ...) and how many of them answered 4xx/5xx
Never: user names, e-mail, IP addresses, user agents, workspace/item/table/column names, row values, prompts, tool
arguments or answers. The tool's answer is read only for its error `kind` (usage.outcome_of), the MCP request body only
for `method` and `clientInfo.name`.

Where it is kept: the Azure table the client registration already uses (KRUSGRAPH_REGISTRATION_STORE, through the
container app's managed identity, registration_store.TableStore), under its own PartitionKey "usage". Each replica writes
one row per day with its own totals (RowKey <day>_<replica>), replaced at most every FLUSH_EVERY seconds, so two
replicas never overwrite each other; the page adds the rows up. Without that table (unset, or `memory`) the counts are
kept in memory only, and the page says "since the last restart, this replica only".

Retention: hashes HASH_DAYS days (long enough for a 30-day distinct count); after that a day is folded into one row
of counts only (RowKey <day>_total), and after KEEP_DAYS days that row is deleted too.

Kill switch: KRUSGRAPH_METRICS=off counts nothing and writes nothing (the page still shows what is stored).
"""
from __future__ import annotations

import atexit
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

PARTITION = "usage"
KEEP_DAYS = 400                 # daily aggregates are kept this long
HASH_DAYS = 35                  # the salted hashes only this long; then the day keeps counts only
FLUSH_EVERY = 60                # seconds between two writes of a replica's row
TIDY_EVERY = 6 * 3600           # seconds between two retention sweeps per replica
MAX_HASHES = 5000               # per set and row (a Table Storage property holds 64 KiB)
MAX_KEYS = {"tools": 300, "errors": 600, "routes": 60, "route_errors": 60, "clients": 60}
COUNTERS = tuple(MAX_KEYS)
NONE, OTHER = "(none)", "(other)"
_CLIENT_OK = re.compile(r"[a-z0-9][a-z0-9 ._\-]{0,39}")
_KIND_OK = re.compile(r"[a-z0-9_\-]{1,40}")
_NAME_OK = re.compile(r"[a-z0-9_\-]{1,64}")


def enabled() -> bool:
    return os.environ.get("KRUSGRAPH_METRICS", "on").strip().lower() not in {"off", "0", "false", "no"}


def _salt() -> str:
    return os.environ.get("KRUSGRAPH_USAGE_SALT", "")


def _hash(kind: str, value: str, salt: str) -> str:
    return hmac.new(salt.encode(), f"{kind}|{value}".encode(), hashlib.sha256).hexdigest()[:16]


def hashes(tid, oid) -> tuple[str | None, str | None]:
    """(organisation hash, user hash) for a tenant id and object id; (None, None) without the salt or the tenant id."""
    salt = _salt()
    tid = str(tid or "").strip().lower()
    if not salt or not tid:
        return None, None
    oid = str(oid or "").strip().lower()
    return _hash("org", tid, salt), (_hash("user", f"{tid}|{oid}", salt) if oid else None)


def client_name(name) -> str:
    if not isinstance(name, str) or not name.strip():
        return NONE
    v = name.strip().lower()
    return v if _CLIENT_OK.fullmatch(v) else OTHER


def _clean(value, pattern) -> str:
    v = str(value or "").strip().lower()
    return v if pattern.fullmatch(v) else OTHER


def _today(now: float | None = None) -> str:
    return datetime.fromtimestamp(time.time() if now is None else now, timezone.utc).strftime("%Y-%m-%d")


def _day_minus(day: str, n: int) -> str:
    return (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=n)).strftime("%Y-%m-%d")


def empty_day() -> dict:
    return {"orgs": [], "users": [], "orgs_n": 0, "users_n": 0, "sessions": 0, **{c: {} for c in COUNTERS}}


# -------------------------------------------------------------------------------------------------- storage -------
class TableRows:
    """Rows of PartitionKey "usage" in the registration table, through registration_store.TableStore's plumbing (the
    managed identity's bearer token, the Table service headers). put / rows / delete; errors raise StoreError."""

    def __init__(self, table_url: str, http=None, token=None) -> None:
        from .registration_store import TableStore
        self.t = TableStore(table_url, http=http, token=token)

    def _url(self, key: str) -> str:
        return f"{self.t.base}(PartitionKey='{PARTITION}',RowKey='{quote(key, safe='')}')"

    def put(self, key: str, data: dict) -> None:
        body = json.dumps({"PartitionKey": PARTITION, "RowKey": key, "data": json.dumps(data, separators=(",", ":"))}).encode()
        r = self.t._request("PUT", self._url(key), self.t._headers(**{"Content-Type": "application/json"}), body)
        if r.status_code not in (200, 201, 204):
            raise self.t._fail("a usage write", r)

    def rows(self, since: str) -> dict[str, dict]:
        out, params = {}, {"$filter": f"PartitionKey eq '{PARTITION}' and RowKey ge '{since}'", "$select": "RowKey,data"}
        for _ in range(100):
            r = self.t._request("GET", f"{self.t.base}()", self.t._headers(), params=params)
            if r.status_code != 200:
                raise self.t._fail("a usage read", r)
            for row in (r.json() or {}).get("value", []):
                try:
                    out[row["RowKey"]] = json.loads(row.get("data") or "{}")
                except (KeyError, TypeError, ValueError):
                    continue
            nxt_p, nxt_r = r.headers.get("x-ms-continuation-NextPartitionKey"), r.headers.get("x-ms-continuation-NextRowKey")
            if not nxt_p and not nxt_r:
                break
            params = {**params, "NextPartitionKey": nxt_p or "", "NextRowKey": nxt_r or ""}
        return out

    def delete(self, key: str) -> None:
        r = self.t._request("DELETE", self._url(key), self.t._headers(**{"If-Match": "*"}))
        if r.status_code not in (200, 204, 404):
            raise self.t._fail("a usage delete", r)


class MemoryRows:
    """The same three operations on a dict: tests, and the fallback when there is no table."""

    def __init__(self) -> None:
        self.data: dict[str, dict] = {}

    def put(self, key, data):
        self.data[key] = json.loads(json.dumps(data))

    def rows(self, since):
        return {k: json.loads(json.dumps(v)) for k, v in self.data.items() if k >= since}

    def delete(self, key):
        self.data.pop(key, None)


def rows_from_env():
    """(rows, durable): the registration table when KRUSGRAPH_REGISTRATION_STORE names one, else memory."""
    raw = os.environ.get("KRUSGRAPH_REGISTRATION_STORE", "").strip()
    if raw.lower().startswith("https://"):
        try:
            return TableRows(raw), True
        except ValueError:
            pass
    return MemoryRows(), False


# -------------------------------------------------------------------------------------------------- counting ------
class Counts:
    def __init__(self, rows=None, durable: bool | None = None, clock=time.time) -> None:
        if rows is None:
            rows, durable = rows_from_env()
        self.rows, self.durable, self.clock = rows, bool(durable), clock
        self.replica = secrets.token_hex(4)
        self.started = clock()
        self._lock = threading.Lock()
        self._days: dict[str, dict] = {}               # this replica's totals of the days it has counted
        self._dirty = False
        self._flushed = clock()
        self._tidied = 0.0
        self._flushing = False
        self.last_error = ""

    # -- recording ------------------------------------------------------------------------------------------
    def _day(self) -> dict:
        today = _today(self.clock())
        if today not in self._days:
            self._prune_memory(today)
        return self._days.setdefault(today, empty_day())

    def _prune_memory(self, today: str) -> None:
        """The same retention for the days held in memory (the only copy when there is no table). Lock held."""
        oldest, hash_limit = _day_minus(today, KEEP_DAYS - 1), _day_minus(today, HASH_DAYS - 1)
        for day in list(self._days):
            if day < oldest:
                del self._days[day]
            elif day < hash_limit and (self._days[day]["orgs"] or self._days[day]["users"]):
                self._days[day] = fold([self._days[day]], counts_only=True)

    @staticmethod
    def _bump(d: dict, counter: str, key: str) -> None:
        bucket = d[counter]
        if key not in bucket and len(bucket) >= MAX_KEYS[counter]:
            key = OTHER
        bucket[key] = bucket.get(key, 0) + 1

    @staticmethod
    def _add_hash(d: dict, which: str, h: str | None) -> None:
        if h and h not in d[which] and len(d[which]) < MAX_HASHES:
            d[which].append(h)

    def _record(self, fn) -> None:
        if not enabled():
            return
        try:
            with self._lock:
                fn(self._day())
                self._dirty = True
            self._maybe_flush()
        except Exception:  # noqa: BLE001 — counting must never break a call
            pass

    def identity(self, tid, oid) -> None:
        org, user = hashes(tid, oid)
        if org:
            self._record(lambda d: (self._add_hash(d, "orgs", org), self._add_hash(d, "users", user)))

    def tool_call(self, tool: str, outcome: str, tid=None, oid=None) -> None:
        """One tool call: its name and, when it ended in an error, the error's kind. Nothing of its arguments."""
        name, kind = _clean(tool, _NAME_OK), (outcome or "ok")
        def add(d):
            self._bump(d, "tools", name)
            if kind != "ok":
                self._bump(d, "errors", f"{name}:{_clean(kind, _KIND_OK)}")
        self._record(add)
        self.identity(tid, oid)

    def session(self, client) -> None:
        name = client_name(client)
        self._record(lambda d: (d.__setitem__("sessions", d["sessions"] + 1), self._bump(d, "clients", name)))

    def route(self, route: str, status: int) -> None:
        name = _clean(route, _NAME_OK)
        def add(d):
            self._bump(d, "routes", name)
            if status >= 400:
                self._bump(d, "route_errors", name)
        self._record(add)

    # -- storing --------------------------------------------------------------------------------------------
    def _maybe_flush(self) -> None:
        if not self.durable:
            return
        with self._lock:
            if self._flushing or not self._dirty or self.clock() - self._flushed < FLUSH_EVERY:
                return
            self._flushing = True
        threading.Thread(target=self.flush, daemon=True, name="usage-flush").start()

    def flush(self) -> None:
        """Write this replica's row of every day it has counted (replacing its earlier version), then forget the days
        before yesterday. A failed write keeps everything in memory for the next try."""
        try:
            with self._lock:
                self._flushing = True
                days = json.loads(json.dumps(self._days))
                self._dirty = False
                self._flushed = self.clock()
            if not self.durable:
                return
            for day, data in days.items():
                self.rows.put(f"{day}_{self.replica}", data)
            self.last_error = ""
            with self._lock:
                keep = _day_minus(_today(self.clock()), 1)
                for day in [d for d in self._days if d < keep]:
                    del self._days[day]
            self._maybe_tidy()
        except Exception as exc:  # noqa: BLE001 — logged by type only; the counts stay in memory
            self.last_error = type(exc).__name__
            with self._lock:
                self._dirty = True
            print(json.dumps({"krusgraph": "usage_metrics", "event": "store_failed", "error": self.last_error}), file=sys.stderr, flush=True)
        finally:
            with self._lock:
                self._flushing = False

    def _maybe_tidy(self) -> None:
        if self.clock() - self._tidied >= TIDY_EVERY:
            self._tidied = self.clock()
            self.tidy()

    def tidy(self) -> None:
        """Retention: delete rows older than KEEP_DAYS; fold the replica rows of days older than HASH_DAYS into one
        row of counts (no hashes)."""
        today = _today(self.clock())
        oldest, hash_limit = _day_minus(today, KEEP_DAYS - 1), _day_minus(today, HASH_DAYS - 1)
        rows = self.rows.rows("0000")
        by_day: dict[str, list[str]] = {}
        for key in rows:
            by_day.setdefault(key[:10], []).append(key)
        for day, keys in by_day.items():
            if day < oldest:
                for key in keys:
                    self.rows.delete(key)
            elif day < hash_limit and any(not k.endswith("_total") for k in keys):
                self.rows.put(f"{day}_total", fold([rows[k] for k in keys], counts_only=True))
                for key in keys:
                    if not key.endswith("_total"):
                        self.rows.delete(key)
        with self._lock:
            for day in [d for d in self._days if d < hash_limit]:
                del self._days[day]

    # -- reading --------------------------------------------------------------------------------------------
    def days(self, n: int = 30) -> dict[str, dict]:
        """Day -> the day's merged totals, for the last n days (today included), every replica's row added up; this
        replica's own row comes from memory, so a page right after a call already shows it."""
        today = _today(self.clock())
        since = _day_minus(today, n - 1)
        stored: dict[str, list[dict]] = {}
        with self._lock:
            own = json.loads(json.dumps({d: v for d, v in self._days.items() if d >= since}))
        if self.durable:
            try:
                for key, data in self.rows.rows(since).items():
                    if not (key.endswith("_" + self.replica) and key[:10] in own):
                        stored.setdefault(key[:10], []).append(data)
                self.last_error = ""
            except Exception as exc:  # noqa: BLE001
                self.last_error = type(exc).__name__
        for day, data in own.items():
            stored.setdefault(day, []).append(data)
        return {day: fold(parts) for day, parts in stored.items() if since <= day <= today}


def fold(parts: list[dict], counts_only: bool = False) -> dict:
    """Several rows of one day (or of several days) as one: counters added up, hash sets united. counts_only: the
    distinct counts are kept as numbers and the hashes dropped."""
    out = empty_day()
    orgs, users = set(), set()
    for p in parts:
        orgs.update(p.get("orgs") or [])
        users.update(p.get("users") or [])
        out["orgs_n"] += int(p.get("orgs_n") or 0)
        out["users_n"] += int(p.get("users_n") or 0)
        out["sessions"] += int(p.get("sessions") or 0)
        for c in COUNTERS:
            for k, v in (p.get(c) or {}).items():
                out[c][k] = out[c].get(k, 0) + int(v)
    if counts_only:
        out["orgs_n"] += len(orgs)
        out["users_n"] += len(users)
    else:
        out["orgs"], out["users"] = sorted(orgs), sorted(users)
    return out


def distinct(days: list[dict], which: str) -> int:
    """Distinct organisations or users over several days: the union of the hashes, plus the counts of days whose
    hashes are gone (an upper bound for those)."""
    seen = set()
    for d in days:
        seen.update(d.get(which) or [])
    return len(seen) + sum(int(d.get(which + "_n") or 0) for d in days)


def _top(counter: dict, n: int = 15) -> list[dict]:
    return [{"name": k, "count": v} for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


def report(counts: "Counts", days: int = 30) -> dict:
    """What /metrics shows, as JSON: windows of 7 and 30 days and one row per day. Counts only; no hash leaves here."""
    per_day = counts.days(days)
    today = _today(counts.clock())
    windows = {}
    for n in (7, 30):
        sel = [per_day[d] for d in per_day if d >= _day_minus(today, n - 1)]
        merged = fold(sel, counts_only=False)
        windows[f"{n}d"] = {"organisations": distinct(sel, "orgs"), "users": distinct(sel, "users"),
                            "sessions": merged["sessions"], "tool_calls": sum(merged["tools"].values()),
                            "errors": sum(merged["errors"].values()), "workload_calls": sum(merged["routes"].values()),
                            "top_tools": _top(merged["tools"]), "errors_by_tool_and_kind": _top(merged["errors"]),
                            "clients": _top(merged["clients"]), "workload_routes": _top(merged["routes"]),
                            "workload_route_errors": _top(merged["route_errors"])}
    rows = []
    for d in sorted(per_day, reverse=True):
        x = per_day[d]
        rows.append({"day": d, "organisations": distinct([x], "orgs"), "users": distinct([x], "users"), "sessions": x["sessions"],
                     "tool_calls": sum(x["tools"].values()), "errors": sum(x["errors"].values()),
                     "workload_calls": sum(x["routes"].values())})
    scope = ("all replicas, kept in Azure Table Storage (the registration table, PartitionKey usage)" if counts.durable
             else "since the last restart, this replica only (no Azure table configured: KRUSGRAPH_REGISTRATION_STORE)")
    return {"what": "Anonymous usage counts per UTC day. Organisations and users are counted as salted hashes, never ids; "
                    "no names, e-mail, IP addresses, workspace/table/column names, prompts or tool arguments are kept.",
            "scope": scope, "durable": counts.durable, "counting": "on" if enabled() else "off (KRUSGRAPH_METRICS=off)",
            "salt_set": bool(_salt()), "store_error": counts.last_error or None, "today": today,
            "windows": windows, "days": rows}


# -------------------------------------------------------------------------------------------------- the page ------
def _esc(v) -> str:
    return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


PAGE_CSS = ("body{font:15px/1.45 system-ui,-apple-system,sans-serif;margin:0;padding:16px;background:#fff;color:#1a1a1a}"
            "main{max-width:880px;margin:0 auto}h1{font-size:1.4em;margin:.2em 0}h2{font-size:1.1em;margin:1.4em 0 .4em}"
            ".note{color:#555;font-size:.9em}.warn{background:#fff4d6;padding:8px 10px;border-radius:6px}"
            ".tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px}"
            ".tile{border:1px solid #ddd;border-radius:8px;padding:8px 10px}.tile b{display:block;font-size:1.5em}"
            ".wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}"
            "th,td{text-align:left;padding:4px 8px;border-bottom:1px solid #eee;white-space:nowrap}td.n,th.n{text-align:right}"
            "input,button{font:inherit;padding:8px;margin:4px 0;max-width:100%}"
            "@media (prefers-color-scheme:dark){body{background:#111;color:#eee}.note{color:#aaa}.tile{border-color:#333}"
            "th,td{border-color:#2a2a2a}.warn{background:#3a3000}}")
PAGE_CSP = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"


def _page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{_esc(title)}</title><style>{PAGE_CSS}</style></head>'
            f"<body><main>{body}</main></body></html>")


def login_html(wrong: bool = False) -> str:
    """The form a browser gets instead of the numbers: the token goes in a POST body, never in the address."""
    msg = '<p class="warn">That token was not right.</p>' if wrong else ""
    return _page("Krusgraph usage", "<h1>Krusgraph usage</h1>" + msg +
                 '<form method="post" action="/metrics"><label for="t">Metrics token</label><br>'
                 '<input id="t" name="token" type="password" autocomplete="current-password" size="40" required><br>'
                 '<button type="submit">Show</button></form>')


def _table(items: list[dict], what: str) -> str:
    if not items:
        return '<p class="note">None.</p>'
    rows = "".join(f'<tr><td>{_esc(i["name"])}</td><td class="n">{i["count"]}</td></tr>' for i in items)
    return f'<div class="wrap"><table><tr><th>{_esc(what)}</th><th class="n">count</th></tr>{rows}</table></div>'


def report_html(rep: dict) -> str:
    parts = ["<h1>Krusgraph usage</h1>",
             f'<p class="note">Per UTC day, today {rep["today"]}. Scope: {_esc(rep["scope"])}. Counting: {_esc(rep["counting"])}.</p>']
    if not rep["durable"]:
        parts.append('<p class="warn">Since the last restart (this replica only): the counts are not stored.</p>')
    if not rep["salt_set"]:
        parts.append('<p class="warn">KRUSGRAPH_USAGE_SALT is not set: organisations and users are not counted.</p>')
    if rep.get("store_error"):
        parts.append(f'<p class="warn">The table could not be read ({_esc(rep["store_error"])}): this replica\'s counts only.</p>')
    for key, label in (("7d", "Last 7 days"), ("30d", "Last 30 days")):
        w = rep["windows"][key]
        tiles = "".join(f'<div class="tile"><b>{w[k]}</b>{_esc(t)}</div>' for k, t in (
            ("organisations", "organisations"), ("users", "users"), ("sessions", "MCP sessions"), ("tool_calls", "tool calls"),
            ("errors", "tool errors"), ("workload_calls", "workload API calls")))
        parts.append(f'<h2>{label}</h2><div class="tiles">{tiles}</div>')
        parts.append("<h2>Top tools</h2>" + _table(w["top_tools"], "tool"))
        parts.append("<h2>Errors (tool:kind)</h2>" + _table(w["errors_by_tool_and_kind"], "tool:kind"))
        parts.append("<h2>MCP clients</h2>" + _table(w["clients"], "client"))
        parts.append("<h2>Workload API routes</h2>" + _table(w["workload_routes"], "route"))
    head = "".join(f'<th class="n">{h}</th>' for h in ("orgs", "users", "sessions", "calls", "errors", "workload"))
    body = "".join(f'<tr><td>{r["day"]}</td><td class="n">{r["organisations"]}</td><td class="n">{r["users"]}</td>'
                   f'<td class="n">{r["sessions"]}</td><td class="n">{r["tool_calls"]}</td><td class="n">{r["errors"]}</td>'
                   f'<td class="n">{r["workload_calls"]}</td></tr>' for r in rep["days"])
    parts.append(f'<h2>Per day</h2><div class="wrap"><table><tr><th>day</th>{head}</tr>{body}</table></div>')
    parts.append('<p class="note">Counts only: no names, e-mail, IP addresses, workspace/table/column names, prompts or tool '
                 "arguments. Organisations and users are salted hashes, kept 35 days, then only their number.</p>")
    return _page("Krusgraph usage", "".join(parts))


# -------------------------------------------------------------------------------------------------- the MCP wire ---
MAX_PEEK = 65536


def mcp_initialize_client(body: bytes) -> tuple[bool, str | None]:
    """(is it an initialize request, the client's name) from a JSON-RPC body (one message or a batch). Only `method`
    and params.clientInfo.name are looked at."""
    if b'"initialize"' not in body:
        return False, None
    try:
        msg = json.loads(body)
    except ValueError:
        return False, None
    for m in (msg if isinstance(msg, list) else [msg]):
        if isinstance(m, dict) and m.get("method") == "initialize":
            info = ((m.get("params") or {}).get("clientInfo") or {}) if isinstance(m.get("params"), dict) else {}
            return True, info.get("name") if isinstance(info, dict) else None
    return False, None


WORKLOAD_PREFIX = "/workload/v1/"


def asgi(app, get_counts=lambda: counts):
    """Around the whole app: an MCP `initialize` POST to /mcp counts a session (and its client name); a call to the
    workload API counts its route and whether it answered 4xx/5xx. The request and the answer pass unchanged."""
    async def wrapped(scope, receive, send):
        if scope["type"] != "http" or not enabled():
            return await app(scope, receive, send)
        path, method = scope.get("path", ""), scope.get("method", "")
        if method == "POST" and path.rstrip("/") == "/mcp":
            buf, state = bytearray(), {"seen": False}

            async def peek():
                message = await receive()
                if message["type"] == "http.request" and not state["seen"]:
                    if len(buf) < MAX_PEEK:
                        buf.extend((message.get("body") or b"")[:MAX_PEEK - len(buf)])
                    if not message.get("more_body"):
                        state["seen"] = True
                        try:
                            is_init, client = mcp_initialize_client(bytes(buf))
                            if is_init:
                                get_counts().session(client)
                        except Exception:  # noqa: BLE001
                            pass
                return message
            return await app(scope, peek, send)
        if path.startswith(WORKLOAD_PREFIX) and method != "OPTIONS":
            route = path[len(WORKLOAD_PREFIX):].split("/")[0] or OTHER
            route = route + ("-get" if method == "GET" else "")

            async def watch(message):
                if message["type"] == "http.response.start":
                    try:
                        get_counts().route(route, int(message.get("status") or 0))
                    except Exception:  # noqa: BLE001
                        pass
                await send(message)
            return await app(scope, receive, watch)
        return await app(scope, receive, send)
    return wrapped


counts = Counts()


@atexit.register
def _flush_at_exit() -> None:
    try:
        if counts.durable and counts._dirty:
            counts.flush()
    except Exception:  # noqa: BLE001
        pass
