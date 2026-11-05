"""Evidence from the data: is an inferred key unique, does an inferred relationship hold?

Names suggest keys and relationships (infer.py); this module checks them against the rows, read-only. Every query is
built from table and column names that came from the source's own metadata, quoted as identifiers — never from
free text — and returns a handful of counts, not rows.

    key:          rows, distinct key values, rows with a NULL in the key   -> unique / duplicates / nulls
    relationship: rows with a value, rows whose value has no match         -> holds / orphans

Each statement is written in the dialect of the connection that runs it (`dialect=`, or `execute.dialect` in
validate(); fabric_backend/dialects.py). T-SQL is the default.
"""
from __future__ import annotations

from .dialects import TSQL, Dialect, of as dialect_of
from .infer import _HISTORY, _norm, Plan


def qi(name: str) -> str:
    """Quote a T-SQL identifier."""
    return "[" + str(name).replace("]", "]]") + "]"


def _t(schema: str, table: str, dialect: Dialect = TSQL) -> str:
    return dialect.table(schema, table)


def key_sql(schema: str, table: str, cols: list[str], dialect: Dialect = TSQL) -> str:
    q, count = dialect.quote, dialect.count
    cs = ", ".join(q(c) for c in cols)
    not_null = " AND ".join(f"{q(c)} IS NOT NULL" for c in cols)
    any_null = " OR ".join(f"{q(c)} IS NULL" for c in cols)
    return (f"SELECT {count}(*) AS n, "
            f"SUM(CASE WHEN {any_null} THEN 1 ELSE 0 END) AS nulls, "
            f"(SELECT {count}(*) FROM (SELECT DISTINCT {cs} FROM {_t(schema, table, dialect)} WHERE {not_null}) AS d) AS distinct_keys "
            f"FROM {_t(schema, table, dialect)}")


def relationship_sql(schema: str, source: str, source_cols: list[str], target: str, target_cols: list[str],
                     dialect: Dialect = TSQL, blank_is_none: bool = False) -> str:
    """blank_is_none: a blank reference ('' or spaces) counts as no value, as SAP writes "none" (the SAP pack's joins)."""
    q, count = dialect.quote, dialect.count
    on = " AND ".join(f"s.{q(a)} = t.{q(b)}" for a, b in zip(source_cols, target_cols))
    has_value = " AND ".join(f"s.{q(a)} IS NOT NULL" for a in source_cols)
    if blank_is_none:
        has_value += "".join(f" AND LTRIM(RTRIM(s.{q(a)})) <> ''" for a in source_cols if a.upper() not in ("MANDT", "RCLNT", "CLIENT"))
    first = q(target_cols[0])
    tcs = ", ".join(q(c) for c in target_cols)
    # DISTINCT on the target side: a duplicated target key must not multiply the source rows being counted
    return (f"SELECT {count}(*) AS with_value, SUM(CASE WHEN t.{first} IS NULL THEN 1 ELSE 0 END) AS orphans "
            f"FROM {_t(schema, source, dialect)} AS s LEFT JOIN (SELECT DISTINCT {tcs} FROM {_t(schema, target, dialect)}) AS t ON {on} "
            f"WHERE {has_value}")


def extended_sql(schema: str, r, dialect: Dialect = TSQL) -> str:
    """A relationship of plan.extended (a join on a unique non-key column, valid on a date, or filtered): the source rows
    it applies to (a value in every join column and the date, and the source-side filter), the ones no target row
    matches (orphans), and the ones more than one target row matches (overlapping periods, or a target that is not
    unique), which a join would repeat. One correlated count per source row: fine for a check, not for a report."""
    q, count = dialect.quote, dialect.count
    cond = [f"t.{q(b)} = s.{q(a)}" for a, b in zip(r.source_cols, r.target_cols)]
    has_value = [f"s.{q(a)} IS NOT NULL" for a in r.source_cols]
    # SAP writes "no value" as a blank, not NULL: a blank source column is no reference (VBPA.ADRNR without an own address)
    has_value += [f"COALESCE(LTRIM(RTRIM(s.{q(a)})), '') <> ''" for a in r.source_cols if a.upper() not in ("MANDT", "RCLNT", "CLIENT")]
    if r.kind == "valid_on" and r.valid_on:
        cond.append(r.period_sql("s", "t", q))
        if r.valid_on.get("source_date"):
            has_value.append(f"s.{q(r.valid_on['source_date'])} IS NOT NULL")
    cond += r.filter_sql("target", "t", q)
    has_value += r.filter_sql("source", "s", q)
    matches = f"(SELECT {count}(*) FROM {_t(schema, r.target, dialect)} AS t WHERE {' AND '.join(cond)})"
    # The count goes into a derived table first: SQL Server (Fabric's SQL endpoint) refuses a subquery inside SUM (error 130)
    return (f"SELECT {count}(*) AS with_value, SUM(CASE WHEN m.n = 0 THEN 1 ELSE 0 END) AS orphans, "
            f"SUM(CASE WHEN m.n > 1 THEN 1 ELSE 0 END) AS several "
            f"FROM (SELECT {matches} AS n FROM {_t(schema, r.source, dialect)} AS s WHERE {' AND '.join(has_value)}) AS m")


def inclusion_sql(schema: str, source: str, column: str, target: str, key: str, dialect: Dialect = TSQL,
                  sample: int | None = None) -> str:
    """Inclusion check for a candidate relationship: how many non-NULL values of source.column exist in target.key,
    and how many distinct values the column has. One counting statement, read-only. With `sample`, the first `sample`
    distinct values of the column stand for all of them (plan_backend's R5): with_value then equals distinct_values, and
    a column with more distinct values than the sample is only partly checked."""
    q, count = dialect.quote, dialect.count
    if sample:
        values = dialect.select(q(column), f" FROM {_t(schema, source, dialect)} WHERE {q(column)} IS NOT NULL", int(sample), distinct=True)
        return (f"SELECT {count}(*) AS with_value, {count}(t.{q(key)}) AS matched, {count}(DISTINCT s.{q(column)}) AS distinct_values "
                f"FROM ({values}) AS s LEFT JOIN (SELECT DISTINCT {q(key)} FROM {_t(schema, target, dialect)}) AS t "
                f"ON s.{q(column)} = t.{q(key)}")
    return (f"SELECT {count}(*) AS with_value, {count}(t.{q(key)}) AS matched, {count}(DISTINCT s.{q(column)}) AS distinct_values "
            f"FROM {_t(schema, source, dialect)} AS s LEFT JOIN (SELECT DISTINCT {q(key)} FROM {_t(schema, target, dialect)}) AS t "
            f"ON s.{q(column)} = t.{q(key)} WHERE s.{q(column)} IS NOT NULL")


# Column types a DB-API driver cannot fetch as they come, or that are noise in a sample. pyodbc answers "ODBC SQL type
# -151 is not yet supported" for SQL Server's CLR types and -150 for sql_variant, which fails the whole call; binary
# values are bytes that say nothing about a column's meaning. Read the CLR types as text, sql_variant as nvarchar,
# binary as its size in bytes.
_CLR_AS_TEXT = {"hierarchyid", "geography", "geometry"}
_VARIANT = {"sql_variant"}
_BINARY = {"binary", "varbinary", "image"}


def sample_expr(column: str, data_type: str = "", dialect: Dialect = TSQL) -> str:
    t = (data_type or "").lower().split("(")[0].strip()
    c = dialect.quote(column)
    if dialect is TSQL and t in _CLR_AS_TEXT:
        return f"{c}.ToString() AS {c}"
    if dialect is TSQL and t in _VARIANT:
        return f"CAST({c} AS nvarchar(4000)) AS {c}"
    if t in _BINARY:
        return f"{dialect.byte_length}({c}) AS {dialect.quote(column + ' (bytes)')}"
    return c


def sample_sql(schema: str, table: str, columns: list[str], n: int, types: dict[str, str] | None = None,
               dialect: Dialect = TSQL) -> str:
    """The first n rows. `types` (column -> SQL type, as INFORMATION_SCHEMA gives it) reads the columns a driver cannot
    fetch as text and binary columns as their size; without it every column is selected as it is."""
    types = {str(k).lower(): v for k, v in (types or {}).items()}
    cols = ", ".join(sample_expr(c, types.get(c.lower(), ""), dialect) for c in columns)
    return dialect.select(cols, f" FROM {_t(schema, table, dialect)}", n)


def _int(v) -> int:
    return int(v or 0)


def key_verdict(n: int, nulls: int, distinct: int) -> str:
    if n == 0:
        return "empty table: nothing to check"
    if nulls:
        return f"not a key: {nulls} of {n} rows have a NULL in it"
    if distinct < n:
        return f"not unique: {n - distinct} duplicate rows ({distinct} distinct values in {n} rows)"
    return f"unique in all {n} rows"


def relationship_verdict(with_value: int, orphans: int) -> str:
    if with_value == 0:
        return "no rows with a value: nothing to check"
    if orphans:
        pct = round(100 * orphans / with_value, 1)
        return f"{orphans} of {with_value} rows ({pct}%) point at nothing"
    return f"holds for all {with_value} rows with a value"


def validate(plan: Plan, execute, max_items: int = 60) -> dict:
    """Run the checks for every key and every relationship in the plan (up to max_items queries)."""
    schema = plan.schema.schema
    dialect = dialect_of(execute)
    keys, rels, budget = [], [], max_items
    unique: dict[str, bool] = {}
    for table, (cols, rule) in plan.keys.items():
        if budget <= 0:
            break
        budget -= 1
        row = execute(key_sql(schema, table, cols, dialect))[0]
        n, nulls, distinct = _int(row.get("n")), _int(row.get("nulls")), _int(row.get("distinct_keys"))
        unique[table] = n > 0 and nulls == 0 and distinct == n
        keys.append({"table": table, "columns": cols, "rule": rule, "rows": n, "nulls": nulls,
                     "distinct": distinct, "verdict": key_verdict(n, nulls, distinct)})
    for r in plan.relationships:
        if budget <= 0:
            break
        budget -= 1
        row = execute(relationship_sql(schema, r.source, r.source_cols, r.target, r.target_cols, dialect,
                                       blank_is_none=r.rule == "SAP pack"))[0]
        with_value, orphans = _int(row.get("with_value")), _int(row.get("orphans"))
        verdict = relationship_verdict(with_value, orphans)
        if r.target in unique and not unique[r.target]:
            verdict += f"; but the target key of {r.target} is not unique, so a row can match more than one"
        rels.append({"source": r.source, "columns": r.source_cols, "target": r.target, "target_columns": r.target_cols,
                     "rule": r.rule, "rows_with_value": with_value, "orphans": orphans, "verdict": verdict})
    for r in getattr(plan, "extended", []):                          # a knowledge pack's joins that are not key joins
        if budget <= 0:
            break
        budget -= 1
        entry = {"source": r.source, "columns": r.source_cols, "target": r.target, "target_columns": r.target_cols,
                 "rule": r.rule, "kind": r.kind, "join": r.join_sql(quote=dialect.quote)}
        row = execute(extended_sql(schema, r, dialect))[0]
        with_value, orphans, several = _int(row.get("with_value")), _int(row.get("orphans")), _int(row.get("several"))
        verdict = relationship_verdict(with_value, orphans)
        if several:
            verdict += (f"; but {several} row(s) fall in more than one validity period of {r.target}, so a join repeats them"
                        if r.kind == "valid_on" else f"; but {several} row(s) match more than one row of {r.target}, so a join repeats them")
        entry.update({"rows_with_value": with_value, "orphans": orphans, "several": several})
        if r.valid_on:
            entry["valid_on"] = r.valid_on
        if r.where:
            entry["where"] = r.where
        entry["verdict"] = verdict
        rels.append(entry)
    checked = len(keys) + len(rels)
    total = len(plan.keys) + len(plan.relationships) + len(getattr(plan, "extended", []))
    ok_keys = sum(1 for k in keys if k["verdict"].startswith("unique"))
    ok_rels = sum(1 for r in rels if r["verdict"].startswith("holds"))
    summary = (f"{ok_keys} of {len(keys)} keys unique, {ok_rels} of {len(rels)} relationships hold without orphans"
               + ("" if checked == total else f" (checked {checked} of {total}; raise max_items to check the rest)"))
    from . import amounts
    levels = amounts.check(plan, execute if budget > 0 else None, max_items=min(20, max(budget, 0)))
    return {"summary": summary, "keys": keys, "relationships": rels, "amount_levels": levels,
            "note": "Counts over the whole tables at the moment of the call. They show the data agrees with the plan "
                    "today; they do not prove the meaning, and new rows can change them."}


DETAILS = ("summary", "full")


def pick_detail(detail: str | None) -> str:
    """validate_plan's `detail` (round n101): "summary" (the default) or "full"; anything else is a bad_input error."""
    d = "summary" if detail is None else str(detail).strip().lower()
    if d not in DETAILS:
        from .infer import PlanInputError
        raise PlanInputError(f"detail: {detail!r} is not one of {', '.join(DETAILS)}; \"summary\" (default) lists what "
                             "needs attention, \"full\" every check")
    return d


def _key_status(k: dict) -> str:
    v = k["verdict"]
    return "passed" if v.startswith("unique") else "not_counted" if v.startswith("empty table") else "failed"


def _rel_status(r: dict) -> str:
    v = r["verdict"]
    if v.startswith("holds"):
        return "warning" if "; but" in v else "passed"
    return "not_counted" if v.startswith("no rows with a value") else "failed"


def _amount_status(f: dict) -> str:
    per = f.get("rows_per_header")
    if not isinstance(per, dict):
        return "not_counted"
    return "failed" if per.get("max_lines", 0) > 1 else "passed"


def summarize(full: dict, plan: Plan | None = None) -> dict:
    """validate_plan's summary form (round n101), written only from the full answer: nothing is counted or queried
    again. It keeps the verdict line, the totals per kind of check, and every check that failed, was not counted or
    holds with a warning ("; but ...") exactly as the full answer has it (counts, rule, SQL). Passing checks become a
    count, and the answer says how many were left out and that detail="full" lists them. `plan` gives the number of
    checks max_items left out."""
    groups = (("keys", full.get("keys", []), _key_status),
              ("relationships", full.get("relationships", []), _rel_status),
              ("amount_levels", (full.get("amount_levels") or {}).get("findings", []), _amount_status))
    attention: dict[str, list] = {}
    totals: dict[str, dict] = {}
    left: dict[str, int] = {}
    for name, items, status in groups:
        st = [status(x) for x in items]
        t = {"checked": len(items), "passed": st.count("passed"), "failed": st.count("failed")}
        if st.count("warning"):
            t["passed_with_warning"] = st.count("warning")
        if st.count("not_counted"):
            t["not_counted"] = st.count("not_counted")
        totals[name] = t
        shown = [x for x, s in zip(items, st) if s != "passed"]
        if shown:
            attention[name] = shown
        left[name] = t["passed"]
    if plan is not None:
        total = len(plan.keys) + len(plan.relationships) + len(getattr(plan, "extended", []))
        skipped = total - len(full.get("keys", [])) - len(full.get("relationships", []))
        if skipped > 0:
            totals["not_checked_beyond_max_items"] = skipped
    passing = sum(left.values())
    skipped = totals.get("not_checked_beyond_max_items", 0)
    out = {"detail": "summary", "summary": full.get("summary", "")}
    if attention:
        n = sum(len(v) for v in attention.values())
        out["needs_attention"] = n
        out["attention"] = attention
        out["totals"] = totals
        out["left_out"] = {"passing_checks": passing, **{k: v for k, v in left.items() if v},
                           "how": f'{passing} passing check(s) are left out of this summary; detail="full" lists every '
                                  "check with its counts and rule."
                                  + (f" {skipped} check(s) did not run: raise max_items." if skipped else "")}
    else:
        out["totals"] = totals
        out["result"] = ("No check ran: the plan has no key, relationship or header amount to count." if not passing and not skipped
                         else f"All {passing} counted checks passed" + (f" ({skipped} not checked: raise max_items)" if skipped else "")
                         + '; they are left out of this summary, and detail="full" lists each with its counts and rule.')
    if "personal_data" in full:
        out["personal_data"] = full["personal_data"]
    out["note"] = full.get("note", "")
    return out


def suggest_composite_keys(plan: Plan) -> list[dict]:
    """Keyless tables whose reference to a keyed table plus a line/position-like column could form a key,
    e.g. order_items: order_id + line_no. Suggestions only — pass them as `keys` after checking them."""
    line_like = ("line", "lineno", "linenumber", "lineno", "position", "pos", "seq", "sequence", "itemno", "rowno")
    out = []
    keyless = [t for t in plan.schema if t.name not in plan.keys]
    for t in keyless:
        refs = [r for r in plan.relationships if r.source == t.name and len(r.source_cols) == 1]
        # header/line: prefer the reference to the table the line table is named after (order_items -> orders)
        stem = t.name.lower().split("_")[0].rstrip("s")
        header = [r for r in refs if r.target.lower().rstrip("s").startswith(stem) or stem.startswith(r.target.lower().rstrip("s"))]
        refs = header or refs
        lines = [c for c in t.column_names if c.lower().replace("_", "") in line_like
                 or c.lower().endswith(("_line", "_line_no", "_seq", "_pos"))]
        for r in refs:
            for line in lines:
                out.append({"table": t.name, "columns": [r.source_cols[0], line],
                            "why": f"{r.source_cols[0]} points at {r.target} and {line} numbers the rows within it",
                            "use": {t.name: [r.source_cols[0], line]}})
        # history: one reference plus the column that starts the validity period (product_cost_history: product_id + start_date)
        starts = [c for c in t.column_names if _HISTORY.search(_norm(c))]
        if refs and starts and not lines:
            r, start = refs[0], starts[0]
            out.append({"table": t.name, "columns": [r.source_cols[0], start],
                        "why": f"{r.source_cols[0]} points at {r.target} and {start} starts a validity period; check that no two rows share both",
                        "use": {t.name: [r.source_cols[0], start]}})
    return out
