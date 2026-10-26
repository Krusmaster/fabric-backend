"""The review file: a plan together with the decisions made about it and the checks run on it, to keep in your own
repository and read back later (the website brief of 26 October 2026, sections 15 and 18 D; the first product goal:
review a small schema, keep the decisions and reuse them without help).

What it reuses rather than invents: the plan snapshot the drift monitor keeps (`drift.plan_snapshot`: tables, column
types, keys and relationships with their rules) and its comparison (`drift.snapshot_diff`), the `keys` and `confirmed`
arguments every planning tool already takes (they carry the corrections into the next tool), and `validate_plan`'s
counting checks (`evidence.validate`), which return counts only.

One JSON file, the same bytes for the same schema, decisions and checks. It holds names, types, rules, decisions, reasons
and counts; never a row value, a sample, a connection string, a token or a secret.

Two statuses per key and relationship, kept apart on purpose: `review` is what a person decided (proposed, accepted,
rejected, open), `check` is what the data said (not_checked, passed, failed, stale). An accepted relationship can fail its
check; a passing check does not make a relationship mean the right thing. When a table's columns change after a check,
the check becomes stale: an old pass is never carried forward as new evidence.
"""
from __future__ import annotations

import hashlib
import json

from .infer import Plan
from .drift import plan_snapshot as _snapshot, snapshot_diff as _diff

FORMAT = "krusgraph-review"
VERSION = 1
REVIEW = ("proposed", "accepted", "rejected", "open")
CHECK = ("not_checked", "passed", "failed", "stale")
CHECK_SCOPE = "one counting query over the whole table (validate_plan); counts only, no values"


class ReviewFileError(ValueError):
    """The review file passed back cannot be read: not this format, a newer version, or a field missing."""


# ------------------------------------------------------------------ ids and fingerprints -----------------------------

def key_id(table: str) -> str:
    return f"key:{table}"


def rel_id(source: str, cols, target: str) -> str:
    return f"rel:{source}.{'+'.join(cols)}>{target}"


def _digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def table_fingerprints(snap: dict) -> dict[str, str]:
    """Per table, a digest of its column names and types: what a check rests on."""
    return {t: _digest({c.lower(): ty for c, ty in v["columns"].items()})[:16] for t, v in snap["tables"].items()}


def schema_fingerprint(snap: dict) -> str:
    return "sha256:" + _digest(sorted(table_fingerprints(snap).items()))[:16]


def plan_id(snap: dict) -> str:
    """The plan's identity: its tables, keys and relationships with their rules. Outputs built from this plan can name it."""
    return "plan-" + _digest({"tables": snap["tables"], "relationships": snap["relationships"]})[:12]


# ------------------------------------------------------------------ reading a file back ------------------------------

def read(raw) -> dict:
    """A review file as review_plan wrote it (the JSON text or the parsed object), checked before anything is reused."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ReviewFileError(f"The review file is not valid JSON: {e.msg} at line {e.lineno}.") from None
    if not isinstance(raw, dict) or raw.get("format") != FORMAT:
        raise ReviewFileError(f"This is not a {FORMAT} file: its 'format' field must be {FORMAT!r}.")
    if not isinstance(raw.get("version"), int) or raw["version"] > VERSION:
        raise ReviewFileError(f"Review file version {raw.get('version')!r} is newer than this server reads ({VERSION}).")
    for f, kind in (("source", dict), ("snapshot", dict), ("items", list)):
        if not isinstance(raw.get(f), kind):
            raise ReviewFileError(f"The review file has no valid {f!r} field.")
    for it in raw["items"]:
        if not isinstance(it, dict) or not isinstance(it.get("id"), str) or it.get("review") not in REVIEW:
            raise ReviewFileError(f"An item in the review file is malformed: {str(it)[:120]}")
        if (it.get("check") or {}).get("status", "not_checked") not in CHECK:
            raise ReviewFileError(f"Item {it['id']} has an unknown check status.")
    snap = raw["snapshot"]
    if not isinstance(snap.get("tables"), dict) or not isinstance(snap.get("relationships"), list):
        raise ReviewFileError("The review file's snapshot has no tables or relationships.")
    return raw


def carried_arguments(review: dict) -> dict:
    """The `keys` and `confirmed` arguments that reproduce the file's corrections in any planning tool: keys a person
    gave (rule K1) and relationships a person added (rule confirmed), unless they were later rejected."""
    keys, confirmed = {}, []
    for it in review["items"]:
        if it["review"] == "rejected":
            continue
        if it.get("type") == "key" and it.get("rule") == "K1":
            keys[it["table"]] = list(it["columns"])
        elif it.get("type") == "relationship" and it.get("rule") == "confirmed":
            confirmed.append({"source": it["source"], "source_cols": list(it["columns"]),
                              "target": it["target"], "target_cols": list(it["target_columns"])})
    return {"keys": keys, "confirmed": confirmed}


def merge_arguments(carried: dict, keys: dict | None, confirmed: list | None) -> tuple[dict | None, list | None]:
    """The call's own keys and confirmed win over the file's: a key per table, a relationship per source column."""
    k = dict(carried["keys"])
    k.update(keys or {})
    mine = {(c["source"].lower(), tuple(x.lower() for x in c["source_cols"])) for c in confirmed or []}
    conf = [c for c in carried["confirmed"] if (c["source"].lower(), tuple(x.lower() for x in c["source_cols"])) not in mine]
    conf += list(confirmed or [])
    return (k or None), (conf or None)


# ------------------------------------------------------------------ building the file --------------------------------

def _items(plan: Plan, base: Plan, snap: dict) -> list[dict]:
    """One item per key and per relationship of the plan, with what the rules alone proposed when that differs."""
    items = []
    for table in sorted(snap["tables"], key=str.lower):
        if table not in plan.keys:
            continue
        cols, rule = plan.keys[table]
        it = {"id": key_id(table), "type": "key", "table": table, "columns": list(cols), "rule": rule}
        if table in base.keys and (list(base.keys[table][0]), base.keys[table][1]) != (list(cols), rule):
            it["proposed"] = {"columns": list(base.keys[table][0]), "rule": base.keys[table][1]}
        elif table not in base.keys:
            it["proposed"] = {"columns": [], "rule": "K3"}
        items.append(it)
    for r in sorted(plan.relationships, key=lambda r: (r.source.lower(), [c.lower() for c in r.source_cols], r.target.lower())):
        if r.source not in snap["tables"] and r.target not in snap["tables"]:
            continue
        items.append({"id": rel_id(r.source, r.source_cols, r.target), "type": "relationship", "source": r.source,
                      "columns": list(r.source_cols), "target": r.target, "target_columns": list(r.target_cols), "rule": r.rule})
    return items


def _check_from(entry: dict, kind: str, checked_at: str) -> dict:
    v = entry["verdict"]
    if kind == "key":
        status = "not_checked" if entry["rows"] == 0 else ("passed" if v.startswith("unique") else "failed")
        result = {"rows": entry["rows"], "nulls": entry["nulls"], "distinct": entry["distinct"]}
    else:
        status = ("not_checked" if entry["rows_with_value"] == 0
                  else "passed" if v.startswith("holds") and "not unique" not in v else "failed")
        result = {"rows_with_value": entry["rows_with_value"], "orphans": entry["orphans"]}
    return {"status": status, "checked_at": checked_at, "result": result, "verdict": v, "scope": CHECK_SCOPE}


def _tables_of(it: dict) -> list[str]:
    return [it["table"]] if it["type"] == "key" else [it["source"], it["target"]]


def build(plan: Plan, base: Plan, source: dict, *, decisions: list[dict] | None = None, checks: dict | None = None,
          checked_at: str = "", previous: dict | None = None, tables: list[str] | None = None) -> dict:
    """The review file for `plan` (made with the person's keys and confirmed) next to `base` (the rules alone).

    decisions: [{"item": "<id>", "review": "accepted|rejected|open|proposed", "reason": "..."}], the call's own; they win
    over the previous file's. checks: validate_plan's answer for this plan, run at `checked_at`. previous: an earlier
    review file (already read()), whose decisions and checks are carried where they still apply. tables: limit the
    file to these tables and the relationships that touch them."""
    snap = _snapshot(plan)
    if tables is not None:
        keep = {t.lower() for t in tables}
        touching = {x for r in snap["relationships"] if r["source"].lower() in keep or r["target"].lower() in keep
                    for x in (r["source"], r["target"])}
        snap = {**snap, "tables": {t: v for t, v in snap["tables"].items() if t.lower() in keep or t in touching},
                "relationships": [r for r in snap["relationships"] if r["source"].lower() in keep or r["target"].lower() in keep]}
    prints = table_fingerprints(snap)
    items = _items(plan, base, snap)
    if tables is not None:
        items = [it for it in items if any(t.lower() in keep for t in _tables_of(it))]
    by_id = {it["id"]: it for it in items}

    # the person's decisions: the previous file's first, then this call's
    prev_items = {it["id"]: it for it in (previous or {}).get("items", [])}
    prev_prints = (previous or {}).get("table_fingerprints", {})
    for it in items:
        old = prev_items.get(it["id"])
        it["review"], it["reason"] = ("accepted", "") if it["rule"] in ("K1", "confirmed") else ("proposed", "")
        if old and old["review"] != "proposed":
            it["review"], it["reason"] = old["review"], old.get("reason", "")
    unknown = [d.get("item") for d in decisions or [] if d.get("item") not in by_id]
    if unknown:
        raise ReviewFileError(f"decisions name items that are not in this review: {unknown[:5]}; "
                             f"the ids look like {next(iter(by_id), 'key:<table>')!r} or 'rel:<table>.<column>><table>'")
    for d in decisions or []:
        if d.get("review", "accepted") not in REVIEW:
            raise ReviewFileError(f"decision for {d['item']}: review must be one of {', '.join(REVIEW)}")
        by_id[d["item"]]["review"] = d.get("review", "accepted")
        by_id[d["item"]]["reason"] = str(d.get("reason", ""))[:500]

    # the checks: this call's, else the previous file's where nothing they rest on changed, else stale or not checked
    fresh = {}
    if checks:
        fresh.update({key_id(k["table"]): _check_from(k, "key", checked_at) for k in checks.get("keys", [])})
        fresh.update({rel_id(r["source"], r["columns"], r["target"]): _check_from(r, "relationship", checked_at)
                      for r in checks.get("relationships", [])})
    for it in items:
        if it["id"] in fresh:
            it["check"] = fresh[it["id"]]
            continue
        old = (prev_items.get(it["id"]) or {}).get("check") or {}
        if old.get("status") in ("passed", "failed"):
            same_item = all(prev_items[it["id"]].get(f) == it.get(f) for f in ("columns", "target_columns", "rule"))
            changed = [t for t in _tables_of(it) if prev_prints.get(t) != prints.get(t)]
            if same_item and not changed:
                it["check"] = old
            else:
                why = (f"{', '.join(changed)} changed since the check" if changed else "the key or relationship changed since the check")
                it["check"] = {**old, "status": "stale", "was": old["status"], "stale_because": why}
        elif old.get("status") == "stale":
            it["check"] = old
        else:
            it["check"] = {"status": "not_checked"}

    # what the rules alone proposed that the corrections took out of the plan (a key on the referencing column, say)
    final_rels = {rel_id(r.source, r.source_cols, r.target) for r in plan.relationships}
    dropped = [{"id": rel_id(r.source, r.source_cols, r.target), "rule": r.rule,
                "relationship": f"{r.source}.{'+'.join(r.source_cols)} → {r.target}.{'+'.join(r.target_cols)}"}
               for r in base.relationships if rel_id(r.source, r.source_cols, r.target) not in final_rels
               and (tables is None or r.source.lower() in keep or r.target.lower() in keep)]
    out = {"format": FORMAT, "version": VERSION, "plan_id": plan_id(snap), "source": source,
           "schema_fingerprint": schema_fingerprint(snap), "table_fingerprints": prints,
           "scope": sorted(tables) if tables is not None else "all tables", "snapshot": snap, "items": items,
           "open_questions": _questions(plan, items, snap), "left_out_by_corrections": dropped, "arguments": None}
    if previous:
        ps = previous.get("source", {})
        differs = [k for k in ("platform", "source", "schema") if str(ps.get(k, "")).lower() != str(source.get(k, "")).lower()]
        gone = [{"id": i, "review": o["review"], "reason": o.get("reason", "")}
                for i, o in sorted(prev_items.items()) if i not in by_id and o["review"] != "proposed"]
        out["since_previous"] = {"previous_plan_id": previous.get("plan_id"), "changes": _diff(previous["snapshot"], snap),
                                 "decisions_no_longer_in_plan": gone, "source_differs": differs}
    out["arguments"] = carried_arguments(out)
    return out


def _questions(plan: Plan, items: list[dict], snap: dict) -> list[dict]:
    qs = []
    for a in plan.ambiguous:
        if a["table"] in snap["tables"]:
            qs.append({"about": f"{a['table']}.{a['column']}",
                       "question": f"Which table does {a['table']}.{a['column']} refer to: {' or '.join(a['candidates'])}? "
                                   f"Add it with confirmed, or leave it unlinked."})
    for t in plan.keyless:
        if t in snap["tables"]:
            qs.append({"about": key_id(t), "question": f"Does {t} have a key? The rules found none; give one with keys, "
                                                       f"or keep it query only (it can reference others, nothing can reference it)."})
    for it in items:
        if it["review"] == "open":
            qs.append({"about": it["id"], "question": it["reason"] or f"Open: {it['id']}"})
    return qs


# ------------------------------------------------------------------ what needs attention, and the report -------------

def _what(it: dict) -> str:
    if it["type"] == "key":
        was = it.get("proposed")
        alone = (f"; the rules alone: {' + '.join(was['columns']) or 'none'} ({was['rule']})" if was else "")
        return f"key of {it['table']}: {' + '.join(it['columns'])} ({it['rule']}{alone})"
    return f"{it['source']}.{'+'.join(it['columns'])} → {it['target']}.{'+'.join(it['target_columns'])} ({it['rule']})"


def attention(review: dict) -> list[str]:
    """Short lines, most important first: failed checks, stale checks, open decisions, then open questions."""
    out = []
    differs = (review.get("since_previous") or {}).get("source_differs")
    if differs:
        out.append(f"The previous file was written for another {' and '.join(differs)}; its decisions were applied where the "
                   f"names match. Check that this is the schema you meant.")
    for it in review["items"]:
        c = it.get("check", {})
        if c.get("status") == "failed":
            pre = "Accepted, but the check failed" if it["review"] == "accepted" else "Check failed"
            out.append(f"{pre}: {_what(it)}: {c.get('verdict', '')}.")
    for it in review["items"]:
        c = it.get("check", {})
        if c.get("status") == "stale":
            out.append(f"Check is stale ({c.get('stale_because')}): {_what(it)}; run the checks again.")
    for d in review.get("left_out_by_corrections", []):
        out.append(f"Not in the plan after your corrections: {d['relationship']} ({d['rule']}, proposed by the rules alone). "
                   f"Add it with confirmed if it should stay.")
    for g in (review.get("since_previous") or {}).get("decisions_no_longer_in_plan", []):
        out.append(f"A decision no longer matches the plan: {g['id']} ({g['review']}{': ' + g['reason'] if g['reason'] else ''}).")
    for q in review.get("open_questions", []):
        out.append(f"Open question ({q['about']}): {q['question']}")
    for it in review["items"]:
        if it["review"] == "rejected":
            out.append(f"Rejected: {_what(it)}. The other tools still infer it from the names; leave it out of what you build.")
    return out


def markdown(review: dict) -> str:
    """A short report to keep next to the file: what needs attention, then every key and relationship."""
    s = review["source"]
    where = " / ".join(str(s[k]) for k in ("workspace", "source", "schema") if s.get(k))
    lines = [f"# Review of {where or 'the schema'}", "",
             f"Plan `{review['plan_id']}`, schema fingerprint `{review['schema_fingerprint']}`, scope: "
             f"{review['scope'] if isinstance(review['scope'], str) else ', '.join(review['scope'])}.", "",
             "Review status is what a person decided; check status is what the counting checks found. They are separate: "
             "a check that passes shows the data agrees with the plan, not that the plan means the right thing.", ""]
    todo = attention(review)
    lines += ["## Needs attention", ""] + ([f"- {t}" for t in todo] or ["- Nothing open."]) + [""]
    lines += ["## Keys and relationships", "", "| Item | Review | Reason | Check | Checked |", "| --- | --- | --- | --- | --- |"]
    for it in review["items"]:
        c = it.get("check", {})
        check = c.get("status", "not_checked").replace("_", " ") + (f": {c['verdict']}" if c.get("verdict") else "")
        lines.append(f"| {_what(it)} | {it['review']} | {(it.get('reason') or '').replace('|', '/')} | "
                     f"{check.replace('|', '/')} | {c.get('checked_at', '')} |")
    sp = review.get("since_previous")
    if sp:
        ch = sp["changes"]
        moved = {k: v for k, v in ch.items() if isinstance(v, list) and v}
        lines += ["", f"## Since `{sp['previous_plan_id']}`", ""]
        lines += [f"- {k.replace('_', ' ')}: {len(v)}" for k, v in moved.items()] or ["- No change in tables, columns, keys or relationships."]
    lines += ["", "To reuse the decisions, pass this file back to `review_plan` as `previous`, or pass its `arguments` "
                  "(`keys`, `confirmed`) to the other tools.", ""]
    return "\n".join(lines)


# ------------------------------------------------------------------ the tool's answer --------------------------------

def _slug(s: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in s.lower()).strip("-") or "schema"


def summary(review: dict) -> str:
    items = review["items"]
    n = lambda f, v: sum(1 for it in items if f(it) == v)                    # noqa: E731
    rv, ck = (lambda it: it["review"]), (lambda it: it.get("check", {}).get("status", "not_checked"))
    return (f"{n(lambda it: it['type'], 'key')} keys and {n(lambda it: it['type'], 'relationship')} relationships: "
            f"{n(rv, 'accepted')} accepted, {n(rv, 'rejected')} rejected, {n(rv, 'open')} open, {n(rv, 'proposed')} still "
            f"proposed; checks: {n(ck, 'passed')} passed, {n(ck, 'failed')} failed, {n(ck, 'stale')} stale, "
            f"{n(ck, 'not_checked')} not checked.")


def answer(review: dict, limit: int) -> str:
    """The tool's answer: the file to save, its suggested name, the report, and what needs attention first."""
    s = review["source"]
    name = f"krusgraph-review.{_slug(str(s.get('source') or s.get('platform') or 'source'))}.{_slug(str(s.get('schema', '')))}.json"
    out = {"file_name": name, "summary": summary(review), "attention": attention(review), "review": review,
           "report_file_name": name[:-5] + ".md", "report": markdown(review),
           "note": "Nothing was created or changed in the source. Save `review` as file_name (and the report next to it) "
                   "in your own repository; pass it back as `previous` to apply the decisions again."}
    text = json.dumps(out, indent=1, ensure_ascii=False)
    if len(text) > limit:
        out.pop("report")
        out["report_file_name"] = None
        out["note"] += " The Markdown report was left out to fit one answer."
        text = json.dumps(out, indent=1, ensure_ascii=False)
    if len(text) > limit:
        raise ReviewFileError(f"The review of {len(review['snapshot']['tables'])} tables does not fit in one answer "
                              f"({len(text)} characters); limit it with tables=[...] and keep one file per area.")
    return text
