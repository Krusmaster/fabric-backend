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

The checklist (round n100) is the same findings as a list of things to do: one row per open question, in the same
order, with the table and column it is about, the counts behind it, a suggested action, an empty owner and the status
"open". The suggested action comes from ACTIONS, one fixed sentence per kind of finding; a kind without one says
"Review". Where a question needs a business decision the action says who is to be asked what, never what the answer
is. Owners are never filled in. Given a review file (review.py, `review=`), a finding whose key or relationship a person
has already accepted or rejected there shows that decision as its status instead of "open".

Round n115: every checklist row also carries `fix`, the fix suggestion for its finding (fixes.py): a fix (a mechanical
step with a stated rule), a choice (two mechanical steps, none chosen) or a question (a business decision, no default),
with the counts before and after taken from validate_plan's own counts and the query that counted them, and for a fix or
a choice the exact PySpark the silver notebook draft adds. They apply only in silver; the source tables are never
written, and nothing here runs. An amount that a flat table repeats on every row of a header value (n106) is a finding of
its own, flat_amount_repeated, with its check.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

STATUS = "Draft"
NOT_CHECKED = "not checked"
NOT_RECORDED = "not recorded"
FORMAT = 1

# n100: the suggested action per kind of finding, neutral and imperative. A question that needs a business decision is
# put as a question to ask, not as a fix. A kind not listed here gets REVIEW, never an invented remedy.
ACTIONS = {
    "key_not_unique": "Look at the duplicate and empty values in the key columns, then record the columns that identify one row.",
    "orphans": "List the values that match no row of the target table, then find out whether the data or the relationship is wrong.",
    "amount_repeated": "Find out which table this amount belongs to; until then, do not sum it over the joined line rows.",
    "flat_amount_repeated": "Review the draft that keeps this amount once per header value in silver; until it has run, sum it once per header value.",
    "ambiguous_target": "Ask which table the column refers to, then record the answer with confirmed or leave the column unlinked.",
    "no_key": "Ask whether the table has a key, then record it with keys or keep the table query only.",
    "proposed_not_applied": "Count the proposed relationship against the rows, then record it with confirmed or leave it out.",
    "not_counted": "Run the checks against the rows (validate_plan), then write the report again.",
}
REVIEW = "Review"
OPEN = "open"
DECIDED = ("accepted", "rejected")                      # review.py's decisions; "proposed" and "open" are not decided yet
# every kind of finding the report writes, in the order report() looks for them
FINDING_TYPES = ("key_not_unique", "orphans", "amount_repeated", "flat_amount_repeated", "ambiguous_target", "no_key",
                 "proposed_not_applied", "pack_not_applied", "not_counted")


def action(kind: str) -> str:
    """The suggested action for a kind of finding: the fixed sentence in ACTIONS, else "Review"."""
    return ACTIONS.get(kind, REVIEW)

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


def _decided(review) -> dict[str, str]:
    """item id (lower case) -> accepted or rejected, from a review file; undecided items are left out."""
    if review is None:
        return {}
    from .review import read
    rv = read(review)
    return {it["id"].lower(): it["review"] for it in rv["items"] if it["review"] in DECIDED}


def checklist(findings: list[dict], review=None) -> list[dict]:
    """The findings as rows to work through, in the report's order: what was found, where, the counts, a suggested
    action, the fix suggestion (n115; a question when the finding has none), an empty owner and the status ("open", or
    the decision the review file already holds)."""
    from . import fixes
    decided = _decided(review)
    return [{"finding": f["finding"], "type": f["type"], "table": f.get("table", ""), "column": f.get("column", ""),
             "counts": dict(f.get("counts") or {}), "action": action(f["type"]),
             "fix": f.get("fix") or fixes.question(f["type"], f.get("table", ""), f.get("column", "")), "owner": "",
             "status": decided.get((f.get("item") or "").lower(), OPEN)} for f in findings]


def report(plan, validation: dict | None = None, decisions: list[dict] | None = None, created: list[dict] | None = None,
           source: str = "", generated_at: str | None = None, review=None, dialect=None) -> dict:
    """The evidence report as JSON. `decisions`: [{"what", "decision", "by"?, "at"?, "note"?}] as the caller recorded
    them; `created`: [{"kind", "id", "name"?}] the ids the creating tools returned. Both are copied as given.
    `review`: a review file as review_plan wrote it (text or parsed); its accepted and rejected items set the status
    of the checklist rows they are about. `dialect` (T-SQL by default): the dialect of the counting queries the fix
    suggestions quote."""
    from . import __version__, evidence, fixes
    from .dialects import TSQL
    from .review import key_id, rel_id
    dialect = dialect or TSQL
    schema = plan.schema.schema or ""
    label = getattr(plan, "label", None) or (lambda rule: rule)
    v = validation or {}
    keys_checked = {k["table"]: k for k in v.get("keys", [])}
    rels_checked = {(r["source"], tuple(c.lower() for c in r["columns"]), r["target"]): r for r in v.get("relationships", [])}
    rows_of = {k["table"]: k["rows"] for k in v.get("keys", [])}

    keys, checks, questions, findings = [], [], [], []

    def find(kind: str, text: str, table: str = "", cols=(), counts: dict | None = None, item: str = "", fix: dict | None = None) -> None:
        """One open question, and the same finding with what the checklist needs to know about it."""
        questions.append(text)
        findings.append({"type": kind, "finding": text, "table": table, "column": "+".join(cols), "counts": counts or {}, "item": item,
                         "fix": fix})

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
            find("key_not_unique", f"The key {t.name}.{'+'.join(cols)} is not unique or has NULLs ({k['verdict']}): give the real key.",
                 t.name, cols, {"rows": k["rows"], "nulls": k["nulls"], "distinct": k["distinct"]}, key_id(t.name),
                 fixes.for_key(schema, t.name, list(cols), label(rule), k["rows"], k["nulls"], k["distinct"], dialect))

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
            fx = fixes.for_orphans(schema, r.source, list(r.source_cols), r.target, list(r.target_cols), label(r.rule), c["rows_with_value"],
                                   c["orphans"], plan.keys.get(r.source, ([], ""))[0], dialect, blank_is_none=r.rule == "SAP pack",
                                   target_unique=evidence.target_key_unique(v.get("keys", []), r.target, r.target_cols),
                                   in_silver=not extended,
                                   query=evidence.extended_sql(schema, r, dialect) if extended else None)
            find("orphans", f"{what}: {c['orphans']} of {c['rows_with_value']} rows point at nothing. Gaps in the data, or another target?",
                 r.source, r.source_cols, counts, rel_id(r.source, r.source_cols, r.target), fx)

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
                       "counts": {k: per[k] for k in ("headers", "avg_lines", "min_lines", "max_lines") if k in per},
                       "read": f"all rows of {f['line']}", "passed": not doubled})
        if doubled:
            find("amount_repeated", f"{what}: summed over the joined rows it counts each {f['header']} row once per {f['line']} row. Sum it on {f['header']}.",
                 f["header"], f["amount_columns"], checks[-1]["counts"], "",
                 fixes.for_amount_repeated(schema, f, checks[-1]["counts"], dialect))
    for e in levels.get("flat_tables", []):                              # n115: n106's flat tables, as checks and findings
        what = f"{e['table']}.{e['amount_column']} per {e['header_column']}"
        counts = {"rows": e["rows"], "header_values": e["header_values"], "repeated_header_values": e["repeated_header_values"],
                  "differing_header_values": e["differing_header_values"]}
        checks.append({"check": "flat_amount", "what": what, "result": e["explanation"], "counts": counts,
                       "read": f"all rows of {e['table']} with a value in {e['header_column']}", "passed": not e["pattern"]})
        if e["pattern"]:
            find("flat_amount_repeated", f"{what}: one value per {e['header_column']}, repeated on each of its rows; summed over "
                                         f"{e['table']} it counts each {e['header_column']} once per row.",
                 e["table"], [e["amount_column"]], counts, "", fixes.for_flat_amount(e, schema, dialect))

    for a in plan.ambiguous:
        find("ambiguous_target", f"{a['table']}.{a['column']} could point at {', '.join(a['candidates'])}: not linked; which one?",
             a["table"], [a["column"]])
    for t in plan.keyless:
        find("no_key", f"{t} has no key: nothing can point at it. Is there one?", t, (), None, key_id(t))
    for x in getattr(plan, "proposed", []) or []:
        find("proposed_not_applied",
             f"{x['source']}.{'+'.join(x['source_cols'])} -> {x['target']} was proposed by R5 and not applied: {x.get('why', '')}".rstrip(": "),
             x["source"], x["source_cols"], None, rel_id(x["source"], x["source_cols"], x["target"]))
    for n in (plan.pack or {}).get("not_applied", []):
        cols = n.get("source_cols") or n.get("pack_source_cols") or []
        find("pack_not_applied", f"{n['source']} -> {n['target']} is listed by the pack and not applied: {n['why']}",
             n["source"], cols, None, rel_id(n["source"], cols, n["target"]) if cols else "")
    if validation is None:
        find("not_counted", "Nothing was counted against the rows: every key and relationship is not checked.")

    decided = [{"what": d.get("what", ""), "decision": d.get("decision", ""), "by": d.get("by") or NOT_RECORDED,
                "at": d.get("at") or NOT_RECORDED, **({"note": d["note"]} if d.get("note") else {})} for d in decisions or []]
    made = [{"kind": c.get("kind", ""), "id": c.get("id", ""), **({"name": c["name"]} if c.get("name") else {})} for c in created or []]
    rows = checklist(findings, review)
    fixes.with_draft(plan, [r["fix"] for r in rows])                     # n115: the lines the silver draft adds
    counted = sum(1 for c in checks if c["result"] != NOT_CHECKED)
    return {"format": FORMAT, "status": STATUS,
            "source": source or plan.schema.schema or "", "schema": plan.schema.schema or "",
            "generated_at": generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "engine": {"name": "fabric-backend", "version": __version__},
            "pack": ({"pack": plan.pack["pack"], "rule": label(plan.pack["rule"]), "status": plan.pack.get("status", "")} if plan.pack else None),
            "summary": {"tables": len(plan.schema), "keys": len(keys), "relationships": len(relationships),
                        "checks": len(checks), "counted": counted, "not_checked": len(checks) - counted,
                        "open_questions": len(questions), "checklist": len(findings), "decisions": len(decided), "created": len(made)},
            "keys": keys, "relationships": relationships, "checks": checks, "open_questions": questions,
            "checklist": rows,
            "decisions": decided, "created": made,
            "note": "Written from the plan, validate_plan's counts and the decisions and ids given to it: no row values. "
                    "Counts are over the whole tables at the time of the check; a check that did not run is 'not checked', "
                    "never passed. A draft for the person who hands it over to read and sign off."}


def _cell(x) -> str:
    return str(x).replace("|", "\\|").replace("\n", " ")


def checklist_markdown(rows: list[dict]) -> list[str]:
    """The checklist as Markdown lines: a table, or one sentence when there are no findings."""
    if not rows:
        return ["No findings: the report holds nothing to do."]
    out = ["The open questions above as things to do, in the same order. The suggested action is where to start, not a "
           "decision; Owner is left empty for the team to fill in.", "",
           "| # | Finding | Table | Column | Counts | Suggested action | Owner | Status |",
           "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for i, r in enumerate(rows, 1):
        counts = ", ".join(f"{k} {v}" for k, v in r["counts"].items()) or "—"
        out.append(f"| {i} | {_cell(r['finding'])} | {_cell(r['table'] or '—')} | {_cell(r['column'] or '—')} | {_cell(counts)} "
                   f"| {_cell(r['action'])} | {_cell(r['owner'])} | {_cell(r['status'])} |")
    return out


def _counts_text(d: dict) -> str:
    return ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in (d or {}).items()) or "—"


def fixes_markdown(rows: list[dict]) -> list[str]:
    """n115: the fix suggestion of each checklist row, numbered as the checklist is: the kind, the stated rule, the counts
    before and after with the query that counted them, the questions with no default, and the draft's PySpark."""
    from .fixes import WHERE
    if not rows:
        return ["None: there are no findings."]
    out = [WHERE + " A choice and a question have no default: the draft stops until the answer is written in.", ""]
    for i, r in enumerate(rows, 1):
        f = r["fix"]
        out.append(f"### {i}. {f['kind']}: {_cell(r['table'] or '—')} {_cell(r['column'] or '')}".rstrip())
        out.append("")
        if f.get("rule"):
            out.append(f["rule"])
        if f.get("why_not_a_fix"):
            out.append(f"Why no fix: {f['why_not_a_fix']}")
        c = f.get("counts") or {}
        if c.get("before"):
            out.append(f"- Before (the check's counts): {_counts_text(c['before'])}")
        if c.get("after"):
            out.append(f"- After, once the silver notebook has run: {_counts_text(c['after'])}")
        for ch in f.get("choices", []):
            out.append(f"- If {ch['id']}: {ch['text']} After: {_counts_text(ch['after'])}")
        if c.get("how"):
            out.append(f"- {c['how']}")
        if f.get("set_null_not_offered"):
            out.append(f"- set_null is not offered: {f['set_null_not_offered']}")
        for q in f.get("questions", []):
            out.append(f"- Question (no default): {q['ask']}" + (f" Options: {'; '.join(q['options'])}." if q.get("options") else "")
                       + (f" Until it is answered, {q['until_answered']}." if q.get("until_answered") else ""))
        out.append(f"- Status: {f['status']}")
        if c.get("query"):
            out += ["", "The check's query:", "", "```sql", c["query"], "```"]
        d = f.get("draft") or {}
        if d.get("pyspark"):
            out += ["", f"What the silver notebook draft adds (cell {d['cell']}):", "", "```python"]
            out += ([d["parameter"]] if d.get("parameter") else []) + [d["pyspark"], "```"]
        elif d.get("not_drafted"):
            out.append(f"- Not in the draft: {d['not_drafted']}")
        out.append("")
    return out[:-1]


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
    out += ["", "## Checklist", ""] + checklist_markdown(rep.get("checklist") or [])
    out += ["", "## Fix suggestions", ""] + fixes_markdown(rep.get("checklist") or [])
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
