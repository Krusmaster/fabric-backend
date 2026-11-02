"""The evidence report: a pilot's hand-over in one file (round n79).

    report(plan, validation, decisions=None, created=None, source="", generated_at=None) -> dict   (the JSON)
    markdown(report) -> str                                                                     (the same, for a person)

It says what the engine proposed, on what grounds, and what was counted against the rows: the source as the user named
it, the time, the engine's version, every key and relationship with its rule and the ground the rule stands on, every
check validate_plan made with its counts and how much of the rows it read, the open questions, the decisions with who
made them and when, and the ids of objects that were created. It is written only from what the answers already hold
(the plan, validate_plan's counts, the caller's own decisions and ids): no row value, and no customer, tenant or
workspace id beyond what the caller passes in. Whatever validate_plan did not count is "not checked", never passed;
a decision without a name or a time says "not recorded". The report is a draft: the person who hands it over reads
it and signs it off; nothing here approves anything.

evidence.py, which counts the rows, is left as it is; this module only reads its output.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

STATUS = "Draft"
NOT_CHECKED = "not checked"
NOT_RECORDED = "not recorded"
FORMAT = 1

_NAMES = {"K0": "declared in the source", "R0": "declared in the source", "K1": "the caller's keys", "confirmed": "confirmed by a person"}


def _basis(rule: str, note: str = "") -> str:
    """The ground a key or relationship stands on, in a few words (the rule's own note when it has one)."""
    if note:
        return note
    if rule in _NAMES:
        return _NAMES[rule]
    if rule[:1] in "KR" and rule[1:].isdigit():
        return f"table and column names (rule {rule})"
    return rule


def _ref(source: str, cols, target: str) -> str:
    return f"{source}.{'+'.join(cols)} -> {target}"


def report(plan, validation: dict | None = None, decisions: list[dict] | None = None, created: list[dict] | None = None,
           source: str = "", generated_at: str | None = None) -> dict:
    """The evidence report as JSON. `decisions`: [{"what", "decision", "by"?, "at"?, "note"?}] as the caller recorded
    them; `created`: [{"kind", "id", "name"?}] the ids the creating tools returned. Both are copied as given."""
    from . import __version__
    label = getattr(plan, "label", None) or (lambda rule: rule)
    v = validation or {}
    keys_checked = {k["table"]: k for k in v.get("keys", [])}
    rels_checked = {(r["source"], tuple(c.lower() for c in r["columns"]), r["target"]): r for r in v.get("relationships", [])}
    rows_of = {k["table"]: k["rows"] for k in v.get("keys", [])}

    keys, checks, questions = [], [], []
    for t in plan.schema:
        if t.name not in plan.keys:
            continue
        cols, rule = plan.keys[t.name]
        basis = (f"{plan.pack['pack']} pack: the key of {plan.pack['tables'][t.name]} as the pack documents it"
                 if plan.pack and t.name in plan.pack.get("tables", {}) and rule == plan.pack.get("rule") else _basis(rule))
        keys.append({"table": t.name, "columns": list(cols), "rule": label(rule), "rule_code": rule, "basis": basis})
        k = keys_checked.get(t.name)
        if k is None:
            checks.append({"check": "key", "what": f"key {t.name}.{'+'.join(cols)}", "result": NOT_CHECKED, "read": NOT_CHECKED})
            continue
        checks.append({"check": "key", "what": f"key {t.name}.{'+'.join(cols)}", "result": k["verdict"],
                       "counts": {"rows": k["rows"], "nulls": k["nulls"], "distinct": k["distinct"]},
                       "read": f"all {k['rows']} rows of {t.name}", "passed": k["verdict"].startswith("unique")})
        if not k["verdict"].startswith("unique"):
            questions.append(f"The key {t.name}.{'+'.join(cols)} is not unique or has NULLs ({k['verdict']}): give the real key.")

    relationships = []
    for r in list(plan.relationships) + list(getattr(plan, "extended", [])):
        extended = r in getattr(plan, "extended", [])
        entry = {"source": r.source, "source_cols": list(r.source_cols), "target": r.target, "target_cols": list(r.target_cols),
                 "rule": label(r.rule), "rule_code": r.rule, "basis": _basis(r.rule, getattr(r, "note", ""))}
        if extended:
            entry["kind"] = r.kind
        relationships.append(entry)
        what = _ref(r.source, r.source_cols, r.target)
        c = rels_checked.get((r.source, tuple(x.lower() for x in r.source_cols), r.target))
        if c is None:
            checks.append({"check": "relationship", "what": what, "result": NOT_CHECKED, "read": NOT_CHECKED})
            continue
        total = rows_of.get(r.source)
        read = (f"all rows of {r.source}" + (f" ({total})" if total is not None else "") + f", {c['rows_with_value']} with a value")
        counts = {"rows_with_value": c["rows_with_value"], "orphans": c["orphans"]}
        if "several" in c:
            counts["several"] = c["several"]
        checks.append({"check": "relationship", "what": what, "result": c["verdict"], "counts": counts, "read": read,
                       "passed": c["verdict"].startswith("holds")})
        if c["orphans"]:
            questions.append(f"{what}: {c['orphans']} of {c['rows_with_value']} rows point at nothing. Gaps in the data, or another target?")

    levels = v.get("amount_levels") or {}
    for f in levels.get("findings", []):
        what = f"{f['header']}.{'+'.join(f['amount_columns'])} over {f['line']}"
        per = f.get("rows_per_header")
        if not isinstance(per, dict):
            checks.append({"check": "amount_level", "what": what, "result": NOT_CHECKED, "read": NOT_CHECKED})
            continue
        doubled = per.get("max_lines", 0) > 1
        checks.append({"check": "amount_level", "what": what,
                       "result": f"up to {per['max_lines']} {f['line']} rows per {f['header']} row" + ("; a join repeats the amount" if doubled else ""),
                       "counts": {k: per[k] for k in ("headers", "avg_lines", "max_lines") if k in per},
                       "read": f"all rows of {f['line']}", "passed": not doubled})
        if doubled:
            questions.append(f"{what}: summed over the joined rows it counts each {f['header']} row once per {f['line']} row. Sum it on {f['header']}.")

    for a in plan.ambiguous:
        questions.append(f"{a['table']}.{a['column']} could point at {', '.join(a['candidates'])}: not linked; which one?")
    for t in plan.keyless:
        questions.append(f"{t} has no key: nothing can point at it. Is there one?")
    for x in getattr(plan, "proposed", []) or []:
        questions.append(f"{x['source']}.{'+'.join(x['source_cols'])} -> {x['target']} was proposed by R5 and not applied: {x.get('why', '')}".rstrip(": "))
    for n in (plan.pack or {}).get("not_applied", []):
        questions.append(f"{n['source']} -> {n['target']} is listed by the pack and not applied: {n['why']}")
    if validation is None:
        questions.append("Nothing was counted against the rows: every key and relationship is not checked.")

    decided = [{"what": d.get("what", ""), "decision": d.get("decision", ""), "by": d.get("by") or NOT_RECORDED,
                "at": d.get("at") or NOT_RECORDED, **({"note": d["note"]} if d.get("note") else {})} for d in decisions or []]
    made = [{"kind": c.get("kind", ""), "id": c.get("id", ""), **({"name": c["name"]} if c.get("name") else {})} for c in created or []]
    counted = sum(1 for c in checks if c["result"] != NOT_CHECKED)
    return {"format": FORMAT, "status": STATUS,
            "source": source or plan.schema.schema or "", "schema": plan.schema.schema or "",
            "generated_at": generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "engine": {"name": "fabric-backend", "version": __version__},
            "pack": ({"pack": plan.pack["pack"], "rule": label(plan.pack["rule"]), "status": plan.pack.get("status", "")} if plan.pack else None),
            "summary": {"tables": len(plan.schema), "keys": len(keys), "relationships": len(relationships),
                        "checks": len(checks), "counted": counted, "not_checked": len(checks) - counted,
                        "open_questions": len(questions), "decisions": len(decided), "created": len(made)},
            "keys": keys, "relationships": relationships, "checks": checks, "open_questions": questions,
            "decisions": decided, "created": made,
            "note": "Written from the plan, validate_plan's counts and the decisions and ids given to it: no row values. "
                    "Counts are over the whole tables at the time of the check; a check that did not run is 'not checked', "
                    "never passed. A draft for the person who hands it over to read and sign off."}


def _cell(x) -> str:
    return str(x).replace("|", "\\|").replace("\n", " ")


def markdown(rep: dict) -> str:
    s = rep["summary"]
    out = [f"# Evidence report: {rep['source']}", "",
           f"Status: **{rep['status']}**. Generated {rep['generated_at']} by {rep['engine']['name']} {rep['engine']['version']}"
           + (f", schema `{rep['schema']}`" if rep["schema"] and rep["schema"] != rep["source"] else "") + ".", "",
           rep["note"], "",
           "## Summary", "",
           f"- {s['tables']} tables, {s['keys']} keys, {s['relationships']} relationships",
           f"- {s['checks']} checks: {s['counted']} counted in the rows, {s['not_checked']} {NOT_CHECKED}",
           f"- {s['open_questions']} open question(s), {s['decisions']} decision(s), {s['created']} created object(s)"]
    if rep.get("pack"):
        out.append(f"- Knowledge pack: {rep['pack']['rule']} ({rep['pack']['status']})")
    out += ["", "## Keys", "", "| Table | Columns | Rule | Basis |", "| --- | --- | --- | --- |"]
    out += [f"| {_cell(k['table'])} | {_cell('+'.join(k['columns']))} | {_cell(k['rule'])} | {_cell(k['basis'])} |" for k in rep["keys"]] or ["| — | | | |"]
    out += ["", "## Relationships", "", "| From | Columns | To | Columns | Rule | Basis |", "| --- | --- | --- | --- | --- | --- |"]
    out += [f"| {_cell(r['source'])} | {_cell('+'.join(r['source_cols']))} | {_cell(r['target'])} | {_cell('+'.join(r['target_cols']))} "
            f"| {_cell(r['rule'])} | {_cell(r['basis'])} |" for r in rep["relationships"]] or ["| — | | | | | |"]
    out += ["", "## Checks against the rows", "", "| Check | What | Result | Counts | Read |", "| --- | --- | --- | --- | --- |"]
    for c in rep["checks"]:
        counts = ", ".join(f"{k} {v}" for k, v in (c.get("counts") or {}).items()) or "—"
        out.append(f"| {c['check']} | {_cell(c['what'])} | {_cell(c['result'])} | {_cell(counts)} | {_cell(c['read'])} |")
    if not rep["checks"]:
        out.append("| — | | | | |")
    out += ["", "## Open questions", ""] + ([f"- {_cell(q)}" for q in rep["open_questions"]] or ["None."])
    out += ["", "## Decisions", ""]
    if rep["decisions"]:
        out += ["| What | Decision | By | When |", "| --- | --- | --- | --- |"]
        out += [f"| {_cell(d['what'])} | {_cell(d['decision'])} | {_cell(d['by'])} | {_cell(d['at'])} |" for d in rep["decisions"]]
    else:
        out.append("None recorded.")
    out += ["", "## Created objects", ""]
    out += [f"- {_cell(c['kind'])}: `{_cell(c['id'])}`" + (f" ({_cell(c['name'])})" if c.get("name") else "") for c in rep["created"]] or ["None."]
    out.append("")
    return "\n".join(out)


def to_json(rep: dict) -> str:
    return json.dumps(rep, indent=1, ensure_ascii=False)
