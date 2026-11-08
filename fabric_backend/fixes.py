"""Fix suggestions for what validate_plan found (round n115): drafts a customer reviews, applied only in silver.

    for_key(...), for_orphans(...), for_amount_repeated(...), for_flat_amount(...), question(...)   -> one suggestion
    suggest(plan, validation)                                                                       -> all, in the checklist's order

Every finding of the evidence report's checklist (evidence_report.py, round n100) gets exactly one entry here, of one of
three kinds:

    fix       a mechanical step with a stated rule and nothing to decide: rows with a NULL key and exact copies of a row go
              to quarantine; an amount that a flat table repeats on every row of a header value moves to a table with one
              row per header value
    choice    two mechanical steps, and the customer picks one: a row whose reference matches nothing goes to quarantine,
              or stays with the reference set to NULL. No choice is made for them; the draft stops until one is written in
    question  a business decision, with no default: which of two rows that share a key and differ is the right one,
              whether an orphan's target exists elsewhere, which table an amount belongs to, which table a column means

A fix or a choice may carry questions too (a duplicate key: which row wins when the rows differ).

The counts before and after come only from the counts validate_plan returned, with the SQL of the query that counted them;
nothing is counted or queried again here. "After" is what the silver tables hold once the silver notebook has run with
the suggestion in it; it has not run when this is written, so nothing here is fixed. Where silver can differ from the
check (a row whose parent row is itself put in quarantine in silver), the entry says so.

Where it applies: only in the silver notebook draft (silver.py, `apply_fixes`), which reads the source tables and writes
only the silver tables and krusgraph_quarantine. The source tables are never written, and nothing here runs anything.
"""
from __future__ import annotations

from . import amounts, evidence
from .dialects import TSQL, Dialect

FIX, CHOICE, QUESTION = "fix", "choice", "question"
KINDS = (FIX, CHOICE, QUESTION)
STATUS = "draft: not run"
WHERE = ("Applied only in the silver notebook draft: it reads the source tables and writes only the silver tables and "
         "krusgraph_quarantine. The source tables are never written. The draft runs nothing; nothing is fixed until the "
         "notebook has run, and its summary prints the counts.")
QUARANTINE, SET_NULL = "quarantine", "set_null"


def _key(cols) -> str:
    return "+".join(cols)


def _entry(kind: str, finding: str, table: str, column: str, **rest) -> dict:
    return {"kind": kind, "finding": finding, "table": table, "column": column, **rest, "status": STATUS}


def for_key(schema: str, table: str, cols: list[str], rule: str, rows: int, nulls: int, distinct: int,
            dialect: Dialect = TSQL) -> dict:
    """A key that is not unique or has NULLs. The fix: rows with a NULL in the key and exact copies of another row go to
    quarantine; one row per key value stays. Which row stays when rows that share a key differ is a question."""
    dup = rows - nulls - distinct
    k = _key(cols)
    rule_text = [f"A row with a NULL in {k} goes to quarantine: it cannot be told apart from another row."] if nulls else []
    if dup:
        rule_text.append(f"Of the rows that share a value of {k}, one stays in silver and the others go to quarantine. An "
                         "exact copy (every column equal) needs no decision: one copy stays.")
    out = _entry(FIX, "key_not_unique", table, k,
                 rule=" ".join(rule_text),
                 counts={"query": evidence.key_sql(schema, table, cols, dialect),
                         "before": {"rows": rows, "rows_with_null_key": nulls, "distinct_key_values": distinct, "duplicate_rows": dup},
                         "after": {"silver_rows": distinct, "quarantined": rows - distinct,
                                   "of_which_null_key": nulls, "of_which_duplicate": dup},
                         "how": f"After = the check's counts: one row per distinct value of {k} ({distinct}); the other "
                                f"{rows - distinct} of the {rows} rows go to quarantine with the reason."},
                 silver={"step": "key", "table": table, "key": list(cols), "rule": rule},
                 questions=[])
    if dup:
        out["questions"].append({
            "id": f"winner:{table}",
            "ask": f"When rows of {table} share {k} but differ in other columns, which one stays in silver?",
            "options": ["the latest by a column you name (DUPLICATE_WINNER in the draft)",
                        f"none: {k} does not identify one row of {table}; record the columns that do (keys=...) and check again"],
            "default": None,
            "until_answered": ("the draft keeps one of each exact copy and stops before writing anything if rows that share "
                               "the key still differ")})
    return out


def _set_null_allowed(reference_cols, key_cols) -> tuple[bool, str]:
    shared = [c for c in reference_cols if c.lower() in {k.lower() for k in key_cols}]
    if shared:
        return False, (f"{', '.join(shared)} is part of the key, so setting it to NULL would take the key away; only quarantine "
                       "is offered")
    return True, ""


def for_orphans(schema: str, source: str, cols: list[str], target: str, target_cols: list[str], rule: str, rows_with_value: int,
                orphans: int, key_cols: list[str] = (), dialect: Dialect = TSQL, blank_is_none: bool = False,
                target_unique: bool = False, in_silver: bool = True, query: str | None = None) -> dict:
    """A relationship with rows that point at nothing. A choice between quarantine and a NULL reference (none is made), and
    the question whether the values exist elsewhere. `in_silver` False (a knowledge pack's join on a period or a filter,
    which the silver draft does not check): only the question."""
    k = _key(cols)
    rid = f"rel:{source}.{k}>{target}"
    q = query or evidence.relationship_sql(schema, source, cols, target, target_cols, dialect, blank_is_none, target_unique)
    before = {"rows_with_value": rows_with_value, "orphans": orphans}
    ask = {"id": f"elsewhere:{rid}",
           "ask": f"Do the values of {source}.{k} that match no row of {target} exist elsewhere: in another table, or in "
                  f"{target} rows that are not loaded yet?",
           "options": [f"yes, in another table: name it, and the relationship is checked against that table instead",
                       f"yes, not loaded yet: the rows can wait in quarantine until they are",
                       f"no: the reference is wrong in the source and is corrected there by its owner"],
           "default": None,
           "until_answered": "the choice below does not depend on it; it only says where the rows go meanwhile"}
    if not in_silver:
        return _entry(QUESTION, "orphans", source, k, rule="", counts={"query": q, "before": before},
                      why_not_a_fix=f"The silver draft does not check {rid} (a join on a period or a filter), so there is "
                                    "no step to suggest.",
                      questions=[ask])
    allowed, why = _set_null_allowed(cols, key_cols)
    choices = [{"id": QUARANTINE, "text": f"The {orphans} row(s) go to quarantine with the reason; silver keeps the "
                                         f"{rows_with_value - orphans} whose reference matches.",
                "after": {"silver_rows_with_value": rows_with_value - orphans, "quarantined": orphans}}]
    if allowed:
        choices.append({"id": SET_NULL, "text": f"The {orphans} row(s) stay in silver with {k} set to NULL (\"unknown\"); a "
                                               "copy of each original row goes to quarantine, so the value is not lost.",
                        "after": {"silver_rows_with_value": rows_with_value - orphans, "silver_rows_set_to_null": orphans,
                                  "copies_in_quarantine": orphans}})
    out = _entry(CHOICE, "orphans", source, k,
                 rule=f"A row of {source} whose {k} matches no row of {target} either goes to quarantine or keeps its place "
                      f"with {k} set to NULL: your choice (ORPHANS in the draft), none is made for you.",
                 choices=choices, default=None,
                 counts={"query": q, "before": before,
                         "how": f"After = the check's counts, over the same {source} rows. In silver two earlier steps can "
                                f"change them: a row of {source} that its key step put in quarantine (a NULL key or a duplicate) is "
                                f"not there to count, and {source} is checked against the silver {target}, so a row whose "
                                f"{target} row itself went to quarantine there is added. The run's summary shows the totals."},
                 silver={"step": "reference", "table": source, "columns": list(cols), "parent": target, "id": rid},
                 questions=[ask])
    if why:
        out["set_null_not_offered"] = why
    return out


def for_amount_repeated(schema: str, f: dict, counts: dict, dialect: Dialect = TSQL) -> dict:
    """A header amount that a join with the line rows repeats. In silver it already sits on the header table, one row
    per header row: nothing moves, so this is a question about the reports, with the two sums to compare."""
    header, line, col = f["header"], f["line"], f["amount_columns"][0]
    before_sql, after_sql = amounts.before_after_sql(schema, f, col, dialect)
    return _entry(QUESTION, "amount_repeated", header, _key(f["amount_columns"]), rule="", line=line,
                  counts={"query": amounts.lines_per_header_sql(schema, line, f["line_columns"], dialect, header, f["header_columns"]),
                          "before": dict(counts)},
                  why_not_a_fix=(f"In silver, {header}.{col} already sits on {header}, one row per {header} row: there is "
                                 f"nothing to move. It is repeated only when a report joins {line} to it."),
                  compare={"summed_over_lines": before_sql, "summed_per_header": after_sql},
                  questions=[{"id": f"level:{header}.{col}",
                              "ask": f"Is {header}.{col} a value of each {header} row (sum it once per {header} row), or "
                                     f"does it belong to each {line} row?",
                              "options": [f"of {header}: reports sum it on {header} (summed_per_header)",
                                          f"of each {line} row: it belongs in {line}, and the source owner says how it splits",
                                          "not summed at all (a price or a rate)"],
                              "default": None,
                              "until_answered": f"the two read-only sums in compare show the difference; neither is run here"}])


def header_table(table: str, header: str) -> str:
    """The silver table a flat table's header amounts move to: one row per header value."""
    return f"{table}_per_{header}"


def for_flat_amount(e: dict, schema: str = "", dialect: Dialect = TSQL) -> dict:
    """An amount a flat table repeats on every row of a header value (n106, the pattern holds: one value per header value,
    and header values repeat). The fix: the amount moves to a silver table with one row per header value."""
    t, h, a = e["table"], e["header_column"], e["amount_column"]
    target = header_table(t, h)
    n, v, r = e["rows"], e["header_values"], e["repeated_header_values"]
    return _entry(FIX, "flat_amount_repeated", t, a,
                  rule=(f"{a} has one value per {h} value (validate_plan counted it), so it belongs to the {h}, copied onto "
                        f"each of its rows. In silver it moves to {target}, one row per {h} value, and {t} keeps every row and "
                        f"every other column. If one {h} value carries two different {a} values when the notebook runs, it stops "
                        "before writing anything: the move is then no longer mechanical."),
                  counts={"query": e["sql"],
                          "before": {"rows_with_a_header_value": n, "header_values": v, "repeated_header_values": r,
                                     "differing_header_values": e["differing_header_values"], "copies_of_the_amount": n},
                          "after": {"silver_rows_of_the_table": n, "silver_rows_of_the_header_table": v, "copies_of_the_amount": v},
                          "sum_once_query": e.get("sum_once_sql") or amounts.flat_sum_once_sql(schema, t, h, a, dialect),
                          "how": (f"After = the check's counts: {t} keeps its {n} rows without {a}, and {target} has one row "
                                  f"per {h} value ({v}). Rows with no {h} were not counted by the check; one that carries "
                                  f"{a} keeps its place without it, and a copy goes to quarantine. Rows that went to "
                                  "quarantine earlier in silver (a key or a reference) are not in either table.")},
                  silver={"step": "move_amount", "table": t, "header_column": h, "amount_column": a, "target": target},
                  questions=[])


# The findings that are a business decision only, with the question to ask. No fix and no default.
QUESTIONS = {
    "ambiguous_target": ("Which table does {table}.{column} refer to?",
                         "The name fits more than one table; which one it means is not in the data."),
    "no_key": ("Does {table} have a key, and which columns are it?",
               "Without a key there is nothing to de-duplicate on; the silver draft copies the rows as they are."),
    "proposed_not_applied": ("Is {table}.{column} a reference to the table proposed for it?",
                             "The proposal was not counted against the rows; whether it is right is a decision."),
    "pack_not_applied": ("Does the pack's relationship from {table} apply to this data?",
                         "The pack lists it, and it was not applied; whether it holds here is a decision."),
    "not_counted": ("May the checks count the rows (validate_plan, read-only)?",
                    "Nothing was counted, so there is no count to base a suggestion on."),
}


def question(kind: str, table: str = "", column: str = "") -> dict:
    """A finding with no mechanical fix: the question to ask, and why there is no fix. A kind not listed asks for a review."""
    ask, why = QUESTIONS.get(kind, ("What should happen with this finding?", "No suggestion is defined for this kind of finding."))
    return _entry(QUESTION, kind, table, column, rule="", why_not_a_fix=why,
                  questions=[{"id": f"{kind}:{table}.{column}".rstrip(".:"), "ask": ask.format(table=table or "the table",
                                                                                          column=column or "the column"),
                              "options": [], "default": None, "until_answered": "nothing is suggested for it"}])


def default_silver_spec(plan) -> dict | None:
    """The silver notebook's spec with its defaults (every table, schema 'silver'), to show the exact lines a draft adds;
    None when no default spec can be made for the plan."""
    from . import silver
    from .infer import PlanInputError
    info = {"schema": plan.schema.schema or "dbo", "schemas_enabled": True}
    for name in ("silver", "krusgraph_silver"):
        try:
            return silver.spec(plan, info, name)
        except PlanInputError:
            continue
    return None


def with_draft(plan, suggestions: list[dict]) -> list[dict]:
    """Each fix and choice with the exact PySpark the silver notebook draft adds for it (silver.apply_fixes on the default
    spec): the parameter line, the lines in the table's cell, and the cell's table."""
    from . import silver
    from .infer import PlanInputError
    s = default_silver_spec(plan)
    if s is None:
        return suggestions
    try:
        drafted = silver.apply_fixes(s, suggestions)
    except PlanInputError as e:
        for x in suggestions:
            if x.get("silver"):
                x["draft"] = {"not_drafted": str(e)}
        return suggestions
    lines = {f["at"]: f["draft"] for f in drafted["fixes"]}
    for i, x in enumerate(suggestions):
        if i in lines:
            x["draft"] = lines[i]
        elif x.get("silver"):
            x["draft"] = {"not_drafted": f"{x['silver']['table']} is not a table of the silver draft"}
    return suggestions


def suggest(plan, validation: dict | None, dialect: Dialect = TSQL) -> list[dict]:
    """One suggestion per checklist row of the evidence report, in its order, with the draft's lines."""
    from . import evidence_report
    rep = evidence_report.report(plan, validation, generated_at="-", dialect=dialect)
    return [r["fix"] for r in rep["checklist"]]
