"""The guided path's shared state (round WB15, Gustav's phone test of 19 November 2026).

Why. The start tool is stateless: what was chosen and decided travels in its arguments. That broke in two ways on the
phone. (E) Accept, Reject and Accept again, tapped 1-2 s apart, ended as "rejected" in the next cards: an older call's
arguments carried an older decision on. (G) A link rejected on the start card was still in the semantic model's dry run
("24 relationships"): the building tools never saw the decision at all.

What this keeps, per signed-in person and per (workspace, source, schema), in memory only, for TTL seconds:
- each decision (item id, accepted / rejected / skipped, and an accepted link's columns), with the sequence number of the
  tap that made it. The latest tap wins: a start call on the decide step records its last decision (the one tapped);
  every other call that carries decisions (Next, a dry run, a call Claude makes from typed text) only fills in what is
  not known yet, so an older card's arguments never undo a newer tap;
- the step last shown and a sequence number, so a card can tell that the path moved on (`seq`).

The building tools (BUILD_TOOLS) read it: a rejected link or key is left out of the plan they build on (the same
`plan_scope` the Fabric workload uses for its review), an accepted link is passed as `confirmed` (silver quarantines its
rows that point at nothing), and the answer says so ("1 relationship left out by your decision").

Nothing here reaches Fabric or a disk. Names and decisions only, never row values. A restart or another replica starts
empty; the start card's arguments then seed it again on the next call.
"""
from __future__ import annotations

import hashlib
import threading
import time

TTL = 4 * 3600
MAX_FLOWS = 5000
REVIEWS = ("accepted", "rejected", "skipped")
# The tools that build on the plan: their dry runs and creates follow the decisions made on the path.
BUILD_TOOLS = ("create_pipeline", "create_semantic_model", "semantic_model_draft", "create_backend", "create_ontology",
               "ontology_draft", "create_data_agent", "create_views", "gold_views_draft", "create_gold_views",
               "silver_notebook_draft", "create_silver_notebook")

_LOCK = threading.Lock()
_FLOWS: dict[tuple, dict] = {}
_SEQ = [0]


def who_of(identity: dict | None, bearer: str | None) -> str:
    """The person, as a digest: oid and tid when signed in with Entra, else a digest of the bearer token, else 'local'."""
    if identity and identity.get("oid"):
        raw = f"{identity.get('tid')}/{identity.get('oid')}"
    elif bearer:
        raw = bearer
    else:
        return "local"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def _key(who: str, workspace, source, schema) -> tuple | None:
    if not (workspace and source):
        return None
    return (who, str(workspace).strip().lower(), str(source).strip().lower(), str(schema or "dbo").strip().lower())


def _next() -> int:
    _SEQ[0] += 1
    return _SEQ[0]


def _flow(k: tuple, create: bool = True) -> dict | None:
    now = time.monotonic()
    f = _FLOWS.get(k)
    if f and now - f["at"] > TTL:
        _FLOWS.pop(k, None)
        f = None
    if f is None and create:
        if len(_FLOWS) >= MAX_FLOWS:
            for old in sorted(_FLOWS, key=lambda x: _FLOWS[x]["at"])[: MAX_FLOWS // 10]:
                _FLOWS.pop(old, None)
        f = _FLOWS[k] = {"decisions": {}, "step": None, "seq": 0, "at": now}
    if f is not None:
        f["at"] = now
    return f


def _clean(d) -> dict | None:
    if not isinstance(d, dict) or not isinstance(d.get("item"), str) or d.get("review") not in REVIEWS:
        return None
    return {"item": d["item"], "review": d["review"]}


def _link_of(item: str, confirmed) -> dict | None:
    for c in confirmed or []:
        if isinstance(c, dict) and item == f"rel:{c.get('source')}.{'+'.join(c.get('source_cols') or [])}>{c.get('target')}":
            return dict(c)
    return None


def record(who: str, workspace, source, schema, step: str | None, decisions, confirmed, tapped: bool) -> dict:
    """Bring the flow up to date with a start call and return its state: {decisions, confirmed, seq}. `tapped`: the
    call is a decision tap (the decide step with decisions): its last decision is the newest and replaces what was
    kept; every other decision fills in only what is not known yet."""
    k = _key(who, workspace, source, schema)
    given = [x for x in (_clean(d) for d in decisions or []) if x]
    if k is None:
        return {"decisions": given or None, "confirmed": confirmed or None, "seq": 0}
    with _LOCK:
        f = _flow(k)
        last = given[-1] if (tapped and given) else None
        for d in given:
            if d is last or d["item"] not in f["decisions"]:
                f["decisions"][d["item"]] = {**d, "link": _link_of(d["item"], confirmed), "seq": _next()}
        f["step"] = step or f["step"]
        f["seq"] = _next()
        return _view(f, confirmed)


def _view(f: dict, confirmed=None) -> dict:
    ds = sorted(f["decisions"].values(), key=lambda x: x["seq"])
    decided = {d["item"] for d in ds}
    keep = [c for c in confirmed or [] if isinstance(c, dict) and
            f"rel:{c.get('source')}.{'+'.join(c.get('source_cols') or [])}>{c.get('target')}" not in decided]
    keep += [d["link"] for d in ds if d["review"] == "accepted" and d.get("link")]
    return {"decisions": [{"item": d["item"], "review": d["review"], "reason": "decided on the start card"} for d in ds] or None,
            "confirmed": keep or None, "seq": f["seq"]}


def state(who: str, workspace, source, schema) -> dict | None:
    """The kept state of one flow, or None."""
    k = _key(who, workspace, source, schema)
    if k is None:
        return None
    with _LOCK:
        f = _flow(k, create=False)
        return _view(f) if f else None


def rejected(who: str, workspace, source, schema) -> set[str]:
    s = state(who, workspace, source, schema) or {}
    return {d["item"] for d in s.get("decisions") or [] if d["review"] == "rejected"}


def accepted_links(who: str, workspace, source, schema) -> list[dict]:
    return list((state(who, workspace, source, schema) or {}).get("confirmed") or [])


def clear() -> None:
    with _LOCK:
        _FLOWS.clear()


def leave_out(plan, items: set[str]):
    """The plan without the rejected links and keys (a link to a table whose key was rejected goes too). Returns
    (plan, left_out): left_out lists each link taken out, as 'source.cols → target'."""
    from dataclasses import replace
    from .review import key_id, rel_id
    no_key = {t for t in plan.keys if key_id(t) in items}
    keep, left = [], []
    for r in plan.relationships:
        if rel_id(r.source, r.source_cols, r.target) in items or r.target in no_key:
            left.append(f"{r.source}.{'+'.join(r.source_cols)} → {r.target}")
        else:
            keep.append(r)
    if not left and not no_key:
        return plan, []
    return replace(plan, keys={t: v for t, v in plan.keys.items() if t not in no_key}, relationships=keep), left


def note(left: list[str], kept: int) -> str:
    """'1 relationship left out by your decision' (and how many were kept with quarantine)."""
    parts = []
    if left:
        parts.append(f"{len(left)} relationship{'' if len(left) == 1 else 's'} left out by your decision")
    if kept:
        parts.append(f"{kept} link{'' if kept == 1 else 's'} accepted by your decision (rows that point at nothing go to quarantine)")
    return "; ".join(parts)
