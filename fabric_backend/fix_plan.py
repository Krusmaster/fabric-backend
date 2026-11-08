"""Proposed fixes per finding (round n155): validate_plan with fixes=true, and the fixes create_silver_notebook applies.

    propose(plan, validation, execute=None, review=None, tables=None, dialect=None) -> dict   (the proposal; runs nothing)
    accept(spec, proposal_entries, accepted) -> spec                                          (the silver spec with them in)

Why an option on validate_plan and not a tool of its own: a proposal stands on validate_plan's counts and nothing else,
takes the same inputs (workspace, source, schema, keys, confirmed), is read-only like it, and agents already call it
when they look for problems. A new tool would also change the tool count that the site's discovery text, the README
and the registry submission state, while the site is being changed by another round.

Built on round n115 (fixes.py and evidence_report.py): one suggestion per finding of the evidence report's checklist, with
the counts from validate_plan's own counts and the PySpark the silver notebook draft adds. This module gives each one:

    id             how create_silver_notebook's `fixes` names it ("key:<table>", "rel:<source>.<cols>><target>",
                   "move:<table>.<amount>"; a business decision has the id of its question)
    type           mechanical: a stated rule with nothing to decide. Exact copies of a row with the same key; a NULL key;
                   rows that share a key and differ, when the table has a load or change time column (the latest row
                   by it stays); a reference that matches nothing (the rows go to quarantine, nothing is lost); a header
                   amount that a flat table repeats (it moves to one row per header value).
                   business_decision: a question with options and no default. Which of two differing rows is right when
                   no time column orders them; whether an orphan's parent exists elsewhere or should be created; which
                   level a repeated header amount belongs to; anything with no mechanical fix.
    what_is_wrong, proposed_fix   in plain words
    snippet        the exact PySpark lines create_silver_notebook writes for it once accepted (parameter and table cell),
                   and the T-SQL query that counted it
    counts         before (the check's counts) and expected_after (what silver holds after the notebook has run with it)

Only two extra read-only queries run here, both with `execute`: per key that is not unique, how many of its key values
have rows that differ in another column (so exact copies are told apart from conflicting rows), and per header amount a
join repeats, the two sums (over the joined line rows, and once per header row) that /check also shows. Nothing runs
anything else, nothing is written, and nothing is applied: create_silver_notebook applies exactly the accepted ids, and
its dry run stays the default.
"""
from __future__ import annotations

import copy

from . import fixes
from .dialects import TSQL, Dialect, of as dialect_of
from .infer import PlanInputError

MECHANICAL, DECISION = "mechanical", "business_decision"
STATUS = "proposed: nothing ran and nothing was written"
WHERE = ("Applied only when you pass the ids you accept to create_silver_notebook (or silver_notebook_draft) as fixes=[...]: "
         "the notebook then reads the source tables and writes only the silver tables and krusgraph_quarantine, with every "
         "row it leaves out in quarantine and a table of counts per fix at the end. The source tables are never written. "
         "create_silver_notebook stays a dry run unless dry_run=false, and the notebook runs only when you run it.")


def differing_sql(schema: str, table: str, key: list[str], dialect: Dialect = TSQL) -> str:
    """The number of key values whose rows differ in some column (distinct whole rows per key value > 1). Exact copies
    count once, so they do not count here."""
    q = dialect.quote
    ks = ", ".join(q(c) for c in key)
    not_null = " AND ".join(f"{q(c)} IS NOT NULL" for c in key)
    return (f"SELECT {dialect.count}(*) AS differing FROM (SELECT {ks} FROM (SELECT DISTINCT * FROM {dialect.table(schema, table)}) AS d "
            f"WHERE {not_null} GROUP BY {ks} HAVING {dialect.count}(*) > 1) AS g")


def _one(execute, sql: str, column: str):
    try:
        rows = list(execute(sql))
    except Exception:                                                    # noqa: BLE001  a type DISTINCT cannot compare
        return None
    if not rows:
        return None
    v = rows[0].get(column)
    return int(v) if v is not None and not isinstance(v, float) else v


def _id(f: dict) -> str:
    st = f.get("silver") or {}
    if st.get("step") == "key":
        return f"key:{st['table']}"
    if st.get("step") == "reference":
        return st["id"]
    if st.get("step") == "move_amount":
        return f"move:{st['table']}.{st['amount_column']}"
    q = (f.get("questions") or [{}])[0].get("id")
    return q or f"{f['finding']}:{f['table']}.{f['column']}".rstrip(".:")


def _key(plan, f: dict, schema: str, execute, dialect: Dialect) -> dict:
    from .silver import _order_column
    table = plan.schema[f["table"]]
    key = f["silver"]["key"]
    b = f["counts"]["before"]
    order, why = _order_column(table, None)
    differing = _one(execute, differing_sql(schema, f["table"], key, dialect), "differing") if execute and b["duplicate_rows"] else (0 if not b["duplicate_rows"] else None)
    k = "+".join(key)
    wrong = []
    if b["rows_with_null_key"]:
        wrong.append(f"{b['rows_with_null_key']} row(s) of {f['table']} have no value in {k}")
    if b["duplicate_rows"]:
        wrong.append(f"{b['duplicate_rows']} row(s) repeat a value of {k} that another row has"
                     + ("" if differing is None else f" ({differing} value(s) with rows that differ in another column)" if differing
                        else " (every one an exact copy of another row)"))
    out = {"what_is_wrong": f"The key {f['table']}.{k} is not unique or has NULLs: " + "; ".join(wrong) + "."}
    steps = []
    if b["rows_with_null_key"]:
        steps.append("rows with a NULL key go to quarantine")
    winner = None
    if b["duplicate_rows"] and differing == 0:
        steps.append("of each set of exact copies one row stays and the others go to quarantine")
        out["type"] = MECHANICAL
    elif b["duplicate_rows"] and order:
        winner = order
        steps.append(f"exact copies keep one row; of rows that share {k} and differ, the latest by {order} stays ({why}) "
                     "and the others go to quarantine")
        out["type"] = MECHANICAL
    elif b["duplicate_rows"]:
        steps.append("exact copies keep one row; which of the rows that share a key and differ is right is a business decision "
                     "(the question below), and until it is answered the notebook stops before writing anything")
        out["type"] = DECISION
    else:
        out["type"] = MECHANICAL
    out["proposed_fix"] = "In silver: " + "; ".join(steps) + "."
    out["decision"] = {"winner": winner}
    out["counted"] = {"differing_key_values": differing, "query": differing_sql(schema, f["table"], key, dialect)} if b["duplicate_rows"] else {}
    if differing == 0 or winner:                                         # nothing left to ask: no winner question
        out["questions"] = []
    return out


def _orphans(f: dict) -> dict:
    b = f["counts"]["before"]
    st = f.get("silver")
    src, cols = f["table"], f["column"]
    tgt = st["parent"] if st else f["questions"][0]["id"].rsplit(">", 1)[-1]
    out = {"what_is_wrong": f"{b['orphans']} of the {b['rows_with_value']} row(s) of {src} with a value in {cols} point at no row of "
                            f"{tgt}. Rows with no value (NULL) are not orphans and are not counted here."}
    if not st:
        out.update(type=DECISION, proposed_fix="None in silver: the silver notebook does not check this relationship (a join on a "
                                               "period or a filter). The question below is for the data's owner.", decision={})
        return out
    out.update(type=MECHANICAL,
               proposed_fix=(f"In silver: the {b['orphans']} row(s) go to quarantine with the reason, so nothing is lost and silver "
                             f"keeps the {b['rows_with_value'] - b['orphans']} whose reference matches. "
                             + ("Instead, the choice set_null keeps them in silver with the reference set to NULL and a copy in "
                                "quarantine. " if any(c["id"] == fixes.SET_NULL for c in f.get("choices", [])) else "")
                             + f"Whether they should be dropped for good, or a {tgt} row created for each missing value, is the "
                               "business decision below; quarantine waits for it."),
               decision={"choice": fixes.QUARANTINE},
               expected_after=next(c["after"] for c in f["choices"] if c["id"] == fixes.QUARANTINE))
    out["extra_question"] = {
        "id": f"drop_or_create:{st['id']}",
        "ask": f"Should the rows of {src} whose {cols} matches no row of {tgt} be dropped from silver for good, or should a row of "
               f"{tgt} be created for each missing value?",
        "options": ["drop them: they stay in quarantine, with the reason, and are not in silver",
                    f"create the missing {tgt} rows in the source system, by its owner; the next run of the notebook then keeps them",
                    "keep them in silver with the reference set to NULL (choice set_null, where offered)"],
        "default": None,
        "until_answered": "the proposed fix puts them in quarantine, from where nothing is lost"}
    return out


def _fan_out(f: dict, execute) -> dict:
    b = f["counts"]["before"]
    header, col = f["table"], f["column"]
    line = f.get("line") or "the line table"
    sums = None
    if execute is not None:
        sb, sa = f["compare"]["summed_over_lines"], f["compare"]["summed_per_header"]
        bv, av = _one(execute, sb, "total"), _one(execute, sa, "total")
        if bv is not None or av is not None:
            sums = {"summed_over_lines": bv, "summed_per_header": av}
    out = {"type": DECISION,
           "what_is_wrong": (f"{header}.{col} sits on {header}, and {line} has up to {b.get('max_lines')} row(s) per {header} row: a "
                             f"report that joins the two and sums {col} counts it once per {line} row (a fan-out)."),
           "proposed_fix": (f"None in silver: {header}.{col} already sits on {header}, one row per {header} row. Sum it once per {header} "
                            f"row (the query summed_per_header), never over the joined {line} rows. Which level the amount "
                            "belongs to is the business decision below."),
           "decision": {}}
    if sums:
        out["sums"] = sums
        f["questions"][0]["until_answered"] = ("the two read-only sums ran (counts.sums) and their queries are in snippet.tsql_compare; "
                                               "nothing is changed")
    return out


def _flat(f: dict) -> dict:
    b = f["counts"]["before"]
    st = f["silver"]
    return {"type": MECHANICAL,
            "what_is_wrong": (f"{st['table']}.{st['amount_column']} has one value per {st['header_column']} and is repeated on each of "
                              f"its rows ({b['rows_with_a_header_value']} rows, {b['header_values']} {st['header_column']} values): "
                              f"summed over {st['table']} it counts each {st['header_column']} several times."),
            "proposed_fix": (f"In silver: {st['amount_column']} moves to {st['target']}, one row per {st['header_column']}; "
                             f"{st['table']} keeps every row and its other columns."),
            "decision": {}}


def _question(f: dict) -> dict:
    return {"type": DECISION, "what_is_wrong": f.get("why_not_a_fix") or "", "decision": {},
            "proposed_fix": "None: " + (f.get("why_not_a_fix") or "this needs a decision, not a step.")}


def _draft(spec: dict | None, f: dict, entry: dict, plan=None) -> dict:
    """The exact parameter line and table-cell lines create_silver_notebook writes once this entry is accepted."""
    if spec is None or not f.get("silver"):
        return {}
    try:
        s = accept(spec, [entry], [entry["id"]], plan)
    except PlanInputError as e:
        return {"not_drafted": str(e)}
    if not s.get("fixes"):
        return {"not_drafted": f"{f['silver']['table']} is not a table of the silver notebook"}
    return dict(s["fixes"][0]["draft"])


def propose(plan, validation: dict | None, execute=None, review=None, tables=None, dialect: Dialect | None = None) -> dict:
    """The proposal: one entry per finding of the evidence report's checklist, in its order. `execute` (optional) runs
    the two extra read-only counts; `review` is a review_plan file whose accepted and rejected items set `review`;
    `tables` keeps the entries about those tables. Same plan and counts, same answer."""
    from . import evidence_report
    dialect = dialect or (dialect_of(execute) if execute is not None else TSQL)
    schema = plan.schema.schema or ""
    rep = evidence_report.report(plan, validation, generated_at="-", review=review, dialect=dialect)
    spec = fixes.default_silver_spec(plan)
    wanted = {t.lower() for t in tables} if tables else None
    out = []
    for row in rep["checklist"]:
        f = copy.deepcopy(row["fix"])
        if wanted is not None and (f.get("table") or "").lower() not in wanted:
            continue
        kind = f["finding"]
        if kind == "key_not_unique":
            e = _key(plan, f, schema, execute, dialect)
        elif kind == "orphans":
            e = _orphans(f)
        elif kind == "amount_repeated":
            e = _fan_out(f, execute)
        elif kind == "flat_amount_repeated":
            e = _flat(f)
        else:
            e = _question(f)
        questions = e.pop("questions", f.get("questions", []))
        if e.get("extra_question"):
            questions = questions + [e.pop("extra_question")]
        counts = f.get("counts") or {}
        entry = {"id": _id(f), "finding": kind, "type": e["type"], "table": f.get("table", ""), "column": f.get("column", ""),
                 "what_is_wrong": e["what_is_wrong"], "proposed_fix": e["proposed_fix"],
                 "counts": {"before": counts.get("before", {}),
                            **({"expected_after": e.get("expected_after") or counts["after"]} if (e.get("expected_after") or counts.get("after")) else {}),
                            **({"how": counts["how"]} if counts.get("how") else {}),
                            **({"sums": e["sums"]} if e.get("sums") else {}),
                            **({k: v for k, v in e["counted"].items() if k != "query"} if e.get("counted") else {})},
                 "snippet": {**({"tsql_count": counts["query"]} if counts.get("query") else {}),
                             **({"tsql_differing": e["counted"]["query"]} if e.get("counted") else {}),
                             **({"tsql_compare": f["compare"]} if f.get("compare") else {})},
                 "questions": questions,
                 "review": row["status"],
                 "silver": f.get("silver"), "choices": f.get("choices", []), "decision": e["decision"],
                 "applies": (f"create_silver_notebook(..., fixes=[\"{_id(f)}\"])" if f.get("silver") and e["type"] == MECHANICAL else
                             "accepting it applies only the mechanical part; the notebook stops before writing anything until "
                             "the question is answered" if f.get("silver") else
                             "nothing to apply: it is a question for a person"),
                 "_suggestion": f}
        if f.get("set_null_not_offered"):
            entry["set_null_not_offered"] = f["set_null_not_offered"]
        entry["snippet"].update(_draft(spec, f, entry, plan))
        out.append(entry)
    for e in out:
        e.pop("_suggestion")
    counts = {"findings": len(out), MECHANICAL: sum(e["type"] == MECHANICAL for e in out),
              DECISION: sum(e["type"] == DECISION for e in out)}
    return {"status": STATUS, "dry_run": True, "counts": counts, "fixes": out, "where": WHERE,
            "accept": ("Pass the ids you accept to create_silver_notebook as fixes=[\"key:customers\", ...]. An orphan fix takes "
                       "{\"id\": ..., \"choice\": \"set_null\"} instead of the proposed quarantine where set_null is offered; a "
                       "duplicate key takes {\"id\": ..., \"winner\": \"<column>\"} to name the column whose latest row stays. "
                       "Business decisions are never applied for you: an id that is only a question is refused.")}


def _suggestion_of(entry: dict) -> dict:
    """The n115 suggestion an entry stands on, as silver.apply_fixes reads it."""
    return {"kind": "choice" if (entry["silver"] or {}).get("step") == "reference" else "fix",
            "finding": entry["finding"], "table": entry["table"], "column": entry["column"],
            "rule": entry["proposed_fix"], "silver": entry["silver"],
            "counts": {"before": entry["counts"].get("before", {}), "after": entry["counts"].get("expected_after", {})},
            "choices": entry.get("choices", []), "questions": entry.get("questions", [])}


def parse_accepted(accepted) -> dict[str, dict]:
    """fixes=[...] as {id: {"choice"?, "winner"?}}: each item an id, or {"id", "choice"?, "winner"?}."""
    out: dict[str, dict] = {}
    for a in accepted or []:
        if isinstance(a, str):
            out[a] = {}
        elif isinstance(a, dict) and isinstance(a.get("id"), str):
            extra = {k: a[k] for k in ("choice", "winner") if a.get(k) is not None}
            bad = set(a) - {"id", "choice", "winner"}
            if bad:
                raise PlanInputError(f"fixes: {a['id']!r} has {', '.join(sorted(bad))}; an item takes id, choice and winner only")
            out[a["id"]] = extra
        else:
            raise PlanInputError('fixes: each item is an id from validate_plan(fixes=true), or {"id": ..., "choice"?: ..., "winner"?: ...}')
    return out


def resolve(entries: list[dict], accepted, plan=None) -> list[dict]:
    """The accepted entries with their decisions: [{"entry", "winner", "choice"}], in the order given. The winner and the
    choice are the caller's where given, else what the entry proposes. An id that is not an entry, an entry that is only
    a question, a choice that is not offered or a winner column the table does not have raises PlanInputError."""
    want = parse_accepted(accepted)
    by_id = {e["id"]: e for e in entries}
    unknown = [i for i in want if i not in by_id]
    if unknown:
        raise PlanInputError("fixes: no such finding: " + ", ".join(repr(u) for u in unknown)
                             + ". The ids are in validate_plan(fixes=true)'s answer, under fixes[].id")
    only_questions = [i for i in want if not by_id[i].get("silver")]
    if only_questions:
        raise PlanInputError("fixes: " + ", ".join(repr(i) for i in only_questions) + " is a business decision with nothing for "
                             "silver to do; it is answered by a person, not applied")
    out = []
    for i, give in want.items():
        e = by_id[i]
        step = e["silver"]["step"]
        winner = choice = None
        if step == "key":
            winner = give.get("winner") or e["decision"].get("winner")
            if winner is not None and plan is not None:
                hit = next((c for c in plan.schema[e["silver"]["table"]].column_names if c.lower() == str(winner).lower()), None)
                if hit is None:
                    raise PlanInputError(f"fixes: {i!r}: {e['silver']['table']} has no column {winner!r} to keep the latest row by")
                winner = hit
            if give.get("choice"):
                raise PlanInputError(f"fixes: {i!r} takes a winner, not a choice")
        elif step == "reference":
            choice = give.get("choice") or e["decision"].get("choice")
            offered = [c["id"] for c in e.get("choices", [])]
            if choice not in offered:
                raise PlanInputError(f"fixes: {i!r} offers {' or '.join(offered)}, not {choice!r}")
            if give.get("winner"):
                raise PlanInputError(f"fixes: {i!r} takes a choice, not a winner")
        elif give:
            raise PlanInputError(f"fixes: {i!r} takes no choice or winner")
        out.append({"entry": e, "winner": winner, "choice": choice, "given": bool(give)})
    return out


def accept(spec: dict, entries: list[dict], accepted, plan=None) -> dict:
    """The silver spec with exactly the accepted entries in it (silver.apply_fixes), each decision the entry proposes (or
    the caller gives) written into the notebook's parameters; nothing is applied that was not accepted (resolve)."""
    from . import silver
    chosen = resolve(entries, accepted, plan)
    out = silver.apply_fixes(spec, [_suggestion_of(c["entry"]) for c in chosen])
    by_table = {t["table"]: t for t in out["tables"]}
    # every accepted id is in the notebook, or the call stops: "applies exactly the accepted ones" (review M2)
    taken = {f["at"] for f in out["fixes"]}
    for at, c in enumerate(chosen):
        if at in taken:
            continue
        e = c["entry"]
        table = e["silver"].get("table")
        if table not in by_table:
            raise PlanInputError(f"fixes: {e['id']!r} is for table {table}, which is not in tables; add {table} to tables "
                                 "or leave the fix out")
        raise PlanInputError(f"fixes: {e['id']!r} has no step in this notebook (its key or reference is not in the plan "
                             "the notebook is built from); run validate_plan(fixes=true) again")
    for c in chosen:
        e, st = c["entry"], c["entry"]["silver"]
        t = by_table.get(st["table"])
        if t is None:
            continue
        if st["step"] == "key" and c["winner"] is not None:
            t["fix_key"].update(winner=c["winner"], named=None,
                                accepted="given in fixes" if c["given"] else "proposed by validate_plan(fixes=true)")
        elif st["step"] == "reference":
            for chk in t["checks"]:
                if chk.get("fix_id") == st["id"]:
                    chk["fix_choice"] = c["choice"]
    for f in out["fixes"]:
        c = chosen[f["at"]]
        e = c["entry"]
        f["id"], f["type"] = e["id"], e["type"]
        if c["choice"] and c["choice"] != fixes.QUARANTINE:
            f["after"] = next(dict(x["after"]) for x in e["choices"] if x["id"] == c["choice"])
        f["draft"] = {"cell": f["table"], "parameter": silver._fix_parameter(by_table[f["table"]], _suggestion_of(e)),
                      "pyspark": silver._fix_lines(by_table[f["table"]], _suggestion_of(e))}
    return out
