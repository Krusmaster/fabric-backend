"""WB10 (Gustav's live test, 18 Nov 2026): one source of truth for the counts and the time on the Data product page.

The editor's Thinker line counts review.json's recorded row check (each key's and link's check: passed or failed, with
its counts and checked_at). The catalog step used to count the rows again and date it "today", so the same page showed
two dates and different link totals. The catalog now reads the same recorded check: the keys and links counted, as
validate_plan's shape, and the latest checked_at. Only when the review holds no check does it count the rows itself,
and then it says when it did, to the minute."""
from __future__ import annotations

COUNTED = ("passed", "failed")


def recorded(review: dict | None) -> tuple[dict | None, str | None]:
    """(validation, checked_at) from review.json's recorded check: keys {table, columns, rows, nulls, distinct, verdict,
    status} and relationships {source, columns, target, rows_with_value, orphans, verdict, status} of the items a person
    did not reject; (None, None) when nothing was checked."""
    keys, rels, latest = [], [], None
    for it in (review or {}).get("items") or []:
        if not isinstance(it, dict) or it.get("review") == "rejected":
            continue
        c = it.get("check") or {}
        if c.get("status") not in COUNTED:
            continue
        r = c.get("result") or {}
        at = c.get("checked_at")
        if at and (latest is None or at > latest):
            latest = at
        if it.get("type") == "key":
            keys.append({"table": it.get("table", ""), "columns": list(it.get("columns") or []), "rows": int(r.get("rows") or 0),
                         "nulls": r.get("nulls"), "distinct": r.get("distinct"), "verdict": c.get("verdict", ""),
                         "status": c["status"]})
        elif it.get("type") == "relationship":
            rels.append({"source": it.get("source", ""), "columns": list(it.get("columns") or []),
                         "target": it.get("target", ""), "rows_with_value": int(r.get("rows_with_value") or 0),
                         "orphans": int(r.get("orphans") or 0), "verdict": c.get("verdict", ""), "status": c["status"]})
    if not keys and not rels:
        return None, None
    return {"keys": keys, "relationships": rels}, latest


def with_recorded(validation: dict | None, review: dict | None, now_iso: str) -> tuple[dict | None, str]:
    """The validation the page uses and the time it states: the recorded check's keys and links (the amount levels the
    fresh count found stay, for the quality rules) and its latest checked_at; else the fresh count, at `now_iso`."""
    got, at = recorded(review)
    if got is None:
        return validation, now_iso
    return {**(validation or {}), **got}, at or now_iso
