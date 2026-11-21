"""One count of a plan's keys and links (round BL3, 21 November 2026; backlog C-31 and C-07).

    summary(plan, validation, *, tables=None, carried=None) -> dict

F1 (docs/FINDINGS-13NOV.md B5, B6, B10, B14, A4) found one plan giving four different counts of its links, and a review
that could say "Nothing open" when nothing was counted. Here every key and every link of the plan gets exactly one of
four states, from validate_plan's answer (`evidence.validate`) and nothing else:

    holds        counted, and the rows agree: a key unique in all its rows; a link whose every value is found in a
                 target whose key is unique
    fails        counted, and the rows disagree: duplicates or NULLs in a key; a link with rows pointing at nothing, a
                 link to a target whose key is not unique, or a link whose join repeats rows ("; but ...")
    no_rows      counted, and there was nothing to check: an empty table, a link column with no value in any row
    not_counted  not counted in this answer: no validation at all, a query that failed, the time budget ran out, left
                 out by max_items or by scope, or (in a review) a check that went stale since

"not counted" is a state of its own and is never folded into "holds"; "no rows" is counted but is not "holds" either.
Only "holds" passes. Everything else is open: `open` lists those items, so a summary can never say "nothing open" while
one check was not counted.

The links are the plan's relationships plus the joins a knowledge pack lists with a condition (`plan.extended`: on a
non-key column, valid on a date, or filtered), said apart in the sentence so that "34" is never read against "24":
"Links: 32 of 34 hold, 1 fails, 1 has no rows to check (24 in the plan, 10 the SAP pack lists with a condition)."

`carried` (review.py): item id -> {"state", "reason"} for items whose earlier counted check a review file carries
forward; used only for items this validation did not count. Counts only, never a row value; no query is run here.
"""
from __future__ import annotations

STATES = ("holds", "fails", "no_rows", "not_counted")
NOT_ASKED = "not counted: no check against the rows was run in this call"
LEFT_OUT = "not counted: not reached in this call (max_items, scope or time); count it again to see it"


def _key_id(table: str) -> str:
    return f"key:{table}"


def _rel_id(source: str, cols, target: str) -> str:
    return f"rel:{source}.{'+'.join(cols)}>{target}"


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def key_state(entry: dict) -> tuple[str, str]:
    """A key entry of validate_plan's answer -> (state, reason)."""
    v = str(entry.get("verdict", ""))
    if int(entry.get("rows") or 0) == 0 or v.startswith("empty table"):
        return "no_rows", v or "empty table: nothing to check"
    if v.startswith("unique") and not entry.get("nulls") and entry.get("distinct") == entry.get("rows"):
        return "holds", v
    return "fails", v


def link_state(entry: dict, target_unique: bool | None = None) -> tuple[str, str]:
    """A relationship entry of validate_plan's answer -> (state, reason). `target_unique`: False when the same answer
    counted the target's key and found it not unique (a link to it is never "holds")."""
    v = str(entry.get("verdict", ""))
    if int(entry.get("rows_with_value") or 0) == 0 or v.startswith("no rows with a value"):
        return "no_rows", v or "no rows with a value: nothing to check"
    if int(entry.get("orphans") or 0) or not v.startswith("holds"):
        return "fails", v
    if target_unique is False or "not unique" in v:
        return "fails", (v if "not unique" in v else f"{v}; but the target key of {entry.get('target')} is not unique, "
                                                      "so a row can match more than one")
    if "; but" in v or int(entry.get("several") or 0):
        return "fails", v
    return "holds", v


def _tally(items: list[dict]) -> dict:
    out = {"total": len(items)}
    for s in STATES:
        out[s] = sum(1 for it in items if it["state"] == s)
    return out


def _sentence(what: str, t: dict) -> str:
    """"32 of 34 hold, 1 fails, 1 has no rows to check, 2 not counted"; the parts that are 0 are left out after "hold"."""
    if not t["total"]:
        return f"no {what}"
    parts = [f"{t['holds']} of {t['total']} {'holds' if t['total'] == 1 else 'hold'}"]
    if t["fails"]:
        parts.append(f"{t['fails']} {'fails' if t['fails'] == 1 else 'fail'}")
    if t["no_rows"]:
        parts.append(f"{t['no_rows']} {'has' if t['no_rows'] == 1 else 'have'} no rows to check")
    if t["not_counted"]:
        parts.append(f"{t['not_counted']} not counted")
    return ", ".join(parts)


def summary(plan, validation: dict | None, *, tables=None, carried: dict | None = None) -> dict:
    """The plan's one count. Returns {"keys", "links", "items", "open", "questions", "sentence"}:
    keys and links: {"total", "holds", "fails", "no_rows", "not_counted", "sentence"} (links also "in_plan", "extended");
    items: one {"id", "kind", "state", "reason"} per key and link in the plan's order (kind "key", "link" or
    "extended link"); open: the items that do not hold, as items; questions: the open questions the plan itself asks
    (a table without a key, a column that could point at several tables), counted apart from the checks;
    sentence: "Keys: 17 of 17 hold. Links: 32 of 34 hold, 1 fails, 1 has no rows to check (24 in the plan, 10 ...)."
    `tables` scopes it as review.py does: the keys of those tables and the links with an end among them."""
    keep = {str(t).lower() for t in tables} if tables is not None else None
    v = validation or {}
    carried = {str(k).lower(): x for k, x in (carried or {}).items()}
    not_done = {str(x.get("id", "")).lower(): str(x.get("evidence") or LEFT_OUT) for x in v.get("not_counted") or []}
    keys_v = {k["table"]: k for k in v.get("keys") or []}
    rels_v: dict[tuple, list[dict]] = {}
    for r in v.get("relationships") or []:
        rels_v.setdefault((r["source"], tuple(str(c).lower() for c in r["columns"]), r["target"], bool(r.get("kind"))), []).append(r)
    unique = {}
    for t, k in keys_v.items():
        st, _ = key_state(k)
        if st in ("holds", "fails"):
            unique[t] = st == "holds"

    def uncounted(item_id: str) -> tuple[str, str]:
        c = carried.get(item_id.lower())
        if c and c.get("state") in STATES:
            return c["state"], str(c.get("reason") or "")
        if validation is None:
            return "not_counted", NOT_ASKED
        return "not_counted", not_done.get(item_id.lower(), LEFT_OUT)

    items: list[dict] = []
    for table, (cols, _rule) in plan.keys.items():
        if keep is not None and table.lower() not in keep:
            continue
        iid = _key_id(table)
        state, reason = key_state(keys_v[table]) if table in keys_v else uncounted(iid)
        items.append({"id": iid, "kind": "key", "table": table, "columns": list(cols), "state": state, "reason": reason})
    links = [(r, False) for r in plan.relationships] + [(r, True) for r in getattr(plan, "extended", []) or []]
    for r, ext in links:
        if keep is not None and r.source.lower() not in keep and r.target.lower() not in keep:
            continue
        iid = _rel_id(r.source, r.source_cols, r.target)
        found = rels_v.get((r.source, tuple(str(c).lower() for c in r.source_cols), r.target, ext)) or []
        if found:
            state, reason = link_state(found.pop(0), unique.get(r.target))
        else:
            state, reason = uncounted(iid)
        items.append({"id": iid, "kind": "extended link" if ext else "link", "source": r.source, "columns": list(r.source_cols),
                      "target": r.target, "target_columns": list(r.target_cols), "state": state, "reason": reason})

    key_items = [it for it in items if it["kind"] == "key"]
    link_items = [it for it in items if it["kind"] != "key"]
    keys = {**_tally(key_items)}
    keys["sentence"] = _sentence("keys", keys)
    lk = {**_tally(link_items), "in_plan": sum(1 for it in link_items if it["kind"] == "link"),
          "extended": sum(1 for it in link_items if it["kind"] == "extended link")}
    lk["sentence"] = _sentence("links", lk)
    if lk["extended"]:
        rule = str((getattr(plan, "pack", None) or {}).get("rule") or "")
        lk["sentence"] += (f" ({lk['in_plan']} in the plan, {lk['extended']} "
                           f"{'the ' + rule + ' lists' if rule.endswith(' pack') else 'other joins'} with a condition)")
    questions = [{"about": f"{a['table']}.{a['column']}", "kind": "ambiguous_target"} for a in getattr(plan, "ambiguous", []) or []
                 if keep is None or a["table"].lower() in keep]
    questions += [{"about": _key_id(t), "kind": "no_key"} for t in getattr(plan, "keyless", []) or []
                  if keep is None or t.lower() in keep]
    sentence = f"Keys: {keys['sentence']}. Links: {lk['sentence']}."
    if questions:
        sentence += f" The plan also asks {_plural(len(questions), 'open question', 'open questions')}."
    return {"keys": keys, "links": lk, "items": items, "open": [it for it in items if it["state"] != "holds"],
            "questions": questions, "sentence": sentence}


def nothing_open(counts: dict) -> bool:
    """True only when every key and link was counted and holds, and the plan asks no question."""
    return not counts["open"] and not counts["questions"]
