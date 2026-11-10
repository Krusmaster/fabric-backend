"""Background operations of the workload's engine API (n197): every editor request may answer at once with 202 and an
operation id, the work goes on in a thread here, and the editor reads its state until it ends.

Why (the founder's live Create of 10 November 2026): one request per output was held open while Fabric worked. The
semantic model hit Fabric's long-running-operation wait, the report got "No answer from the Krusgraph engine after
230 s" (the editor's own wait, BUILD_WAIT_MS, set just under Azure Container Apps' 240-second ingress timeout), and on a
phone five steps failed with "Failed to fetch" while the items were still being created in Fabric. Now no request waits
for Fabric: POST /workload/v1/<route> with the header `Prefer: respond-async` answers 202 {operation_id} within a
second, and POST /workload/v1/operation {operation_id} (or {item_id}: the latest Create of that item) answers the state.

States: running, waiting_capacity (Fabric throttles: the step is tried again after a pause, never failed for it),
pending_fabric (Fabric is still working on the item: its long-running operation is followed), done (the route's answer,
as the synchronous route gives it, with its HTTP status), lost (the replica that ran it stopped: no heartbeat for
LOST_AFTER seconds; the item may still exist in Fabric and is adopted on the next Create through outputs.json's pending
entries).

Where the state lives: the store the client registration uses (registration_store.py) when KRUSGRAPH_REGISTRATION_STORE
names one, so both replicas of the hosted service see every operation (Azure Table Storage); in memory otherwise (one
replica, tests). One record per operation (kind "op"), its answer compressed in chunks of CHUNK characters (a Table
Storage property holds at most 64 KiB), and one index per item with the operations of its latest Create. Every record
expires after TTL. Records carry names, states, counts and Fabric's own messages, as the answers do, never a row value
or a token; the owner is a keyed hash of tenant and user, so another user's poll of the same id finds nothing.
"""
from __future__ import annotations

import base64
import calendar
import contextvars
import hashlib
import json
import os
import secrets
import threading
import time
import zlib

KIND = "op"
TTL = 2 * 24 * 3600                   # an operation and its answer are kept two days
HEARTBEAT = 15                        # seconds between two writes of a running operation's `updated`
LOST_AFTER = 120                      # no heartbeat for this long: the replica that ran it is gone
CHUNK = 24000                         # characters of the compressed answer per record
MAX_THREADS = 24                      # operations running at once per replica; more wait for a free thread
ITEM_OPS = 40                         # operations an item's index keeps (one Create has at most a dozen steps)
FINAL = ("done", "lost")

_store = None
_store_lock = threading.Lock()
_slots = threading.BoundedSemaphore(MAX_THREADS)
_local: dict[str, dict] = {}          # operations this replica runs: their live token holder
_CURRENT: contextvars.ContextVar = contextvars.ContextVar("krusgraph_operation", default=None)


def store():
    """The registration store when one is configured, else a process-wide MemoryStore."""
    global _store
    with _store_lock:
        if _store is None:
            from . import registration_store as rs
            raw = os.environ.get("KRUSGRAPH_REGISTRATION_STORE", "").strip()
            _store = rs.from_env() if raw else rs.MemoryStore()
        return _store


def use_store(s) -> None:
    """Tests: a store of their own (None: back to the default)."""
    global _store
    with _store_lock:
        _store = s
        _local.clear()


def owner_of(claims: dict) -> str:
    """A keyed hash of tenant and user: who may read an operation. Never the ids themselves."""
    key = os.environ.get("KRUSGRAPH_SERVER_KEY", "") or "krusgraph-operations"
    raw = f"{claims.get('tid', '')}:{claims.get('oid') or claims.get('sub') or ''}"
    return hashlib.sha256(f"{key}|{raw}".encode()).hexdigest()[:40]


def _item_key(owner: str, item: str) -> str:
    return "item-" + hashlib.sha256(f"{owner}|{item}".encode()).hexdigest()[:40]


def _pack(answer: dict) -> list[str]:
    text = base64.urlsafe_b64encode(zlib.compress(json.dumps(answer, separators=(",", ":"), default=str).encode(), 6)).decode()
    return [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)] or [""]


def _unpack(parts: list[str]) -> dict:
    return json.loads(zlib.decompress(base64.urlsafe_b64decode("".join(parts).encode())).decode())


def _now() -> float:
    return time.time()


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _write(op: dict) -> None:
    store().put(KIND, op["id"], op, ttl=TTL)


def _read(op_id: str) -> dict | None:
    got = store().get(KIND, op_id)
    return got[0] if got else None


def _index(owner: str, item: str, op: dict) -> None:
    """The item's latest Create: its operations, newest last. A new Create (op["create"] differs) starts a new list."""
    s, key = store(), _item_key(owner, item)
    entry = {"id": op["id"], "route": op["route"], "output": op.get("output"), "create": op.get("create"), "at": op["started"]}
    for _ in range(5):
        got = s.get(KIND, key)
        if got is None:
            if s.add(KIND, key, {"create": op.get("create"), "ops": [entry]}, ttl=TTL):
                return
            continue
        data, etag = got
        ops = data.get("ops", []) if data.get("create") == op.get("create") or not op.get("create") else []
        ops = ([o for o in ops if o.get("id") != op["id"]] + [entry])[-ITEM_OPS:]
        if s.replace(KIND, key, {"create": op.get("create") or data.get("create"), "ops": ops}, etag, ttl=TTL):
            return


class Live:
    """What a running operation's work can say while it runs (progress) and the token holder a later poll refreshes."""

    def __init__(self, op: dict, tokens) -> None:
        self.op, self.tokens, self.lock = op, tokens, threading.Lock()
        self.last = 0.0

    def progress(self, status: str | None = None, **fields) -> None:
        with self.lock:
            if status:
                self.op["status"] = status
            self.op.setdefault("progress", {})
            for k, v in fields.items():
                if v is None:
                    self.op["progress"].pop(k, None)
                else:
                    self.op["progress"][k] = v
            self.op["updated"] = _iso(_now())
            self.last = _now()
            snapshot = dict(self.op)
        try:
            _write(snapshot)
        except Exception as exc:  # noqa: BLE001 — a lost progress write is caught up by the next one
            _log("op_progress_failed", error=type(exc).__name__)


def progress(status: str | None = None, **fields) -> None:
    """From inside an operation's work: say what it is doing (waiting_capacity, pending_fabric, a line of words). Outside
    an operation (a synchronous request, the MCP tools) it does nothing."""
    live = _CURRENT.get()
    if live is not None:
        live.progress(status, **fields)


def current() -> Live | None:
    return _CURRENT.get()


def _log(event: str, **fields) -> None:
    from .workload_api import log
    log(event, **fields)


def start(route: str, owner: str, work, *, tokens=None, item: str | None = None, output: str | None = None,
          create: str | None = None, wrap=None) -> dict:
    """Record a new operation and run `work()` (which returns the route's answer and HTTP status) in a thread. Answers
    at once with the record: {id, status: running, ...}. `wrap(fn)` runs fn inside the request's token context."""
    op_id = secrets.token_hex(16)
    now = _now()
    op = {"id": op_id, "owner": owner, "route": route, "status": "running", "started": _iso(now), "updated": _iso(now),
          "item": item, "output": output, "create": create}
    _write(op)
    if item:
        try:
            _index(owner, item, op)
        except Exception as exc:  # noqa: BLE001 — the operation runs either way; the editor keeps its id too
            _log("op_index_failed", error=type(exc).__name__)
    live = Live(op, tokens)
    _local[op_id] = {"live": live}

    def heartbeat(stop: threading.Event) -> None:
        while not stop.wait(HEARTBEAT):
            if _now() - live.last >= HEARTBEAT - 1:
                live.progress()

    def run() -> None:
        stop = threading.Event()
        beat = threading.Thread(target=heartbeat, args=(stop,), daemon=True)
        with _slots:
            beat.start()
            token = _CURRENT.set(live)
            started = time.monotonic()
            try:
                answer, status = (wrap or (lambda f: f()))(work)
            except Exception as exc:  # noqa: BLE001 — answered like the synchronous route's last resort
                _log("op_failed", route=route, error=type(exc).__name__)
                answer, status = ({"error": f"The Krusgraph engine stopped on this {route} request ({type(exc).__name__}); "
                                            "nothing more was done after that point.", "kind": "unexpected",
                                   "hint": "Try again. If it repeats, the server's log has the cause (event op_failed)."}, 500)
            finally:
                _CURRENT.reset(token)
                stop.set()
            finish(live, answer, status, round(time.monotonic() - started, 1))

    answer_now = public(dict(op))     # n204: taken before the thread starts, which may already change op (a CI race)
    threading.Thread(target=run, name=f"krusgraph-op-{op_id[:8]}", daemon=True).start()
    return answer_now


def finish(live: Live, answer: dict, status: int, seconds: float) -> None:
    op = live.op
    parts = _pack(answer)
    try:
        for n, part in enumerate(parts):
            store().put(KIND, f"{op['id']}-r{n}", {"part": part}, ttl=TTL)
    except Exception as exc:  # noqa: BLE001
        _log("op_answer_write_failed", error=type(exc).__name__)
    with live.lock:
        op.update(status="done", http=status, parts=len(parts), seconds=seconds, updated=_iso(_now()))
        op.pop("progress", None)
        snapshot = dict(op)
    for attempt in range(3):
        try:
            _write(snapshot)
            break
        except Exception as exc:  # noqa: BLE001 — the poll says lost if this never lands
            _log("op_finish_write_failed", error=type(exc).__name__, attempt=attempt)
            time.sleep(1 + attempt)
    _local.pop(op["id"], None)
    _log("op_done", route=op["route"], http=status, seconds=seconds)


def public(op: dict) -> dict:
    """The state as the editor sees it (no owner)."""
    out = {k: op.get(k) for k in ("id", "route", "status", "started", "updated", "output", "item", "create", "http", "seconds")
           if op.get(k) is not None}
    out["operation_id"] = op["id"]
    if op.get("progress"):
        out["progress"] = op["progress"]
    return out


def state(op_id: str, owner: str, tokens=None) -> dict | None:
    """The operation's state for its owner (None for anyone else or an unknown id); with its answer once done. A running
    operation whose heartbeat stopped is answered as lost. A poll on the replica that runs it refreshes its token."""
    op = _read(op_id)
    if not op or op.get("owner") != owner:
        return None
    if op_id in _local and tokens is not None:
        holder = _local[op_id]["live"].tokens
        if holder is not None and hasattr(holder, "refresh"):
            holder.refresh(tokens)
    out = public(op)
    if op.get("status") == "done":
        try:
            parts = []
            for n in range(int(op.get("parts") or 1)):
                got = store().get(KIND, f"{op_id}-r{n}")
                if got is None:
                    raise KeyError(n)
                parts.append(got[0]["part"])
            out["answer"] = _unpack(parts)
        except Exception:  # noqa: BLE001 — the record says done but its answer is gone (expired, a failed write)
            out.update(status="lost", lost="The answer of this step could not be read back.")
        return out
    try:
        updated = calendar.timegm(time.strptime(op.get("updated", ""), "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        updated = 0
    if op_id not in _local and _now() - updated > LOST_AFTER:
        out.update(status="lost", lost=f"The engine stopped working on this step (no sign of it for {LOST_AFTER} s).")
    return out


def of_item(item: str, owner: str) -> dict:
    """The operations of the item's latest Create, each with its state (answers included once done)."""
    got = store().get(KIND, _item_key(owner, item))
    if not got:
        return {"item": item, "create": None, "operations": []}
    data = got[0]
    ops = []
    for entry in data.get("ops", []):
        s = state(entry["id"], owner)
        if s is not None:
            ops.append(s)
    return {"item": item, "create": data.get("create"), "operations": ops}
