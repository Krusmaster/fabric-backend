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


def _rel_parts(schema: str, source_cols: list[str], target: str, target_cols: list[str], dialect: Dialect,
               blank_is_none: bool, target_unique: bool, t: str = "t") -> tuple[str, str, str, str]:
    """The pieces of one relationship's count, with the target side under alias `t`: (has_value, joined target, ON,
    the target column that is NULL when nothing matched). relationship_sql and combined_relationship_sql share them."""
    q = dialect.quote
    on = " AND ".join(f"s.{q(a)} = {t}.{q(b)}" for a, b in zip(source_cols, target_cols))
    has_value = " AND ".join(f"s.{q(a)} IS NOT NULL" for a in source_cols)
    if blank_is_none:
        has_value += "".join(f" AND LTRIM(RTRIM(s.{q(a)})) <> ''" for a in source_cols if a.upper() not in ("MANDT", "RCLNT", "CLIENT"))
    tcs = ", ".join(q(c) for c in target_cols)
    # DISTINCT on the target side: a duplicated target key must not multiply the source rows being counted. A target key
    # counted unique with no NULLs cannot multiply them, and its NULL-free rows are the DISTINCT rows: join it directly
    joined = (_t(schema, target, dialect) if target_unique
              else f"(SELECT DISTINCT {tcs} FROM {_t(schema, target, dialect)})")
    return has_value, joined, on, f"{t}.{q(target_cols[0])}"


def relationship_sql(schema: str, source: str, source_cols: list[str], target: str, target_cols: list[str],
                     dialect: Dialect = TSQL, blank_is_none: bool = False, target_unique: bool = False) -> str:
    """blank_is_none: a blank reference ('' or spaces) counts as no value, as SAP writes "none" (the SAP pack's joins).
    target_unique (round n104): the same run has counted exactly these target columns as unique with no NULLs
    (target_key_unique), so the target table is joined directly; otherwise through SELECT DISTINCT. The counts are the
    same either way; the default is the DISTINCT form."""
    count = dialect.count
    has_value, joined, on, first = _rel_parts(schema, source_cols, target, target_cols, dialect, blank_is_none, target_unique)
    return (f"SELECT {count}(*) AS with_value, SUM(CASE WHEN {first} IS NULL THEN 1 ELSE 0 END) AS orphans "
            f"FROM {_t(schema, source, dialect)} AS s LEFT JOIN {joined} AS t ON {on} "
            f"WHERE {has_value}")


def combined_relationship_sql(schema: str, source: str, rels: list[dict], dialect: Dialect = TSQL) -> str:
    """Round n108: the relationships of one source table in one statement, so the source table is read once. `rels` are
    relationship_sql's arguments per relationship ({source_cols, target, target_cols, blank_is_none, target_unique}).
    Relationship i gets its own LEFT JOIN (alias t{i}, built exactly as relationship_sql builds it: DISTINCT unless the
    same run counted the target key unique) and two columns: with_value_{i}, the source rows with a value
    (relationship_sql's WHERE, here as a condition), and orphans_{i}, those of them the join finds no row for.

    Why the counts equal relationship_sql's: each joined target side has at most one row per value of its join columns
    (DISTINCT, or a key counted unique with no NULLs), so no LEFT JOIN multiplies a source row; every source row appears
    exactly once, and the conditions count the same rows relationship_sql's WHERE keeps. with_value_{i} is a count, not
    an integer SUM, so it overflows where relationship_sql's COUNT does, which is never."""
    count = dialect.count
    cols, joins = [], []
    for i, r in enumerate(rels, 1):
        has_value, joined, on, first = _rel_parts(schema, r["source_cols"], r["target"], r["target_cols"], dialect,
                                                  r.get("blank_is_none", False), r.get("target_unique", False), t=f"t{i}")
        cols.append(f"{count}(CASE WHEN {has_value} THEN 1 END) AS with_value_{i}, "
                    f"SUM(CASE WHEN {has_value} AND {first} IS NULL THEN 1 ELSE 0 END) AS orphans_{i}")
        joins.append(f"LEFT JOIN {joined} AS t{i} ON {on}")
    return f"SELECT {', '.join(cols)} FROM {_t(schema, source, dialect)} AS s " + " ".join(joins)


def _base_type(t: str) -> str:
    return (t or "").lower().split("(")[0].strip()


def combinable(plan: Plan, r) -> bool:
    """Whether a relationship may go into its source table's combined statement. Only when the equal counts follow from
    the SQL alone: every join column is known on both sides with the same type, so the comparison converts nothing (a
    conversion could make two distinct target values equal one source value, and a join that matches twice would then
    change every relationship's counts in the statement, not only its own). Otherwise it keeps its own statement."""
    try:
        s, t = plan.schema[r.source], plan.schema[r.target]
    except Exception:
        return False
    if not r.source_cols or len(r.source_cols) != len(r.target_cols):
        return False
    stypes = {c.name.lower(): _base_type(c.data_type) for c in s.columns}
    ttypes = {c.name.lower(): _base_type(c.data_type) for c in t.columns}
    for a, b in zip(r.source_cols, r.target_cols):
        st, tt = stypes.get(str(a).lower(), ""), ttypes.get(str(b).lower(), "")
        if not st or st != tt:
            return False
    return True


def target_key_unique(keys: list[dict], target: str, target_cols: list[str]) -> bool:
    """True only when a key entry of the same validate run (its "keys") is for `target`, has exactly the columns
    `target_cols` (the same names, in any order, none left over or missing) and was counted unique: rows > 0, no NULL,
    as many distinct values as rows. Anything else (not checked, a key on other or only some of the columns, not
    unique, NULLs, an empty table) is False, and the relationship check keeps SELECT DISTINCT."""
    cols = [str(c) for c in target_cols]
    if not cols or len(set(cols)) != len(cols):
        return False
    for k in keys:
        if k.get("table") != target or sorted(str(c) for c in k.get("columns", [])) != sorted(cols):
            continue
        n, nulls, distinct = k.get("rows"), k.get("nulls"), k.get("distinct")
        if (isinstance(n, int) and n > 0 and nulls == 0 and distinct == n
                and str(k.get("verdict", "")).startswith("unique")):
            return True
    return False


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


def _rel_id(r) -> str:
    return f"rel:{r.source}.{'+'.join(r.source_cols)}>{r.target}"


def _in_scope(r, keep) -> bool:
    return keep is None or r.source in keep or r.target in keep


def check_order(plan: Plan, tables=None) -> list[tuple[str, object]]:
    """n226: the order validate counts in, and what `resume_from` counts from: [("key", table) | ("rel", i) | ("ext", j)],
    i and j indexes into plan.relationships and plan.extended. Links come by importance, each right after the key of
    its target: a link touching tables that many links touch first (degree of the target, then of the source), then plan
    order. The keys no counted link needs come last, the most linked tables first. Before n226 every key came before
    any link, so above max_items keyed tables no link was ever counted.
    `tables` (names) scopes it: the keys of those tables and the links with an end among them (as compact.sub_plan)."""
    keep = set(tables) if tables is not None else None
    rels = list(plan.relationships)
    ext = list(getattr(plan, "extended", []))
    degree: dict[str, int] = {}
    for r in rels + ext:
        for t in {r.source, r.target}:
            degree[t] = degree.get(t, 0) + 1
    links = [("rel", i, r) for i, r in enumerate(rels) if _in_scope(r, keep)] + \
            [("ext", j, r) for j, r in enumerate(ext) if _in_scope(r, keep)]
    links.sort(key=lambda x: (-degree.get(x[2].target, 0), -degree.get(x[2].source, 0), x[0] == "ext", x[1]))
    key_tables = [t for t in plan.keys if keep is None or t in keep]
    queue: list[tuple[str, object]] = []
    seen: set[str] = set()
    for kind, i, r in links:
        if r.target in plan.keys and r.target not in seen and (keep is None or r.target in keep):
            queue.append(("key", r.target))
            seen.add(r.target)
        queue.append((kind, i))
    order = {t: n for n, t in enumerate(plan.keys)}
    for t in sorted((t for t in key_tables if t not in seen), key=lambda t: (-degree.get(t, 0), order[t])):
        queue.append(("key", t))
    return queue


def item_id(plan: Plan, item: tuple[str, object]) -> str:
    """The id of a queue item, as review.py writes it: key:<table>, rel:<source>.<cols>><target>."""
    from .review import key_id, rel_id
    kind, x = item
    if kind == "key":
        return key_id(x)
    r = (plan.relationships if kind == "rel" else plan.extended)[x]
    return rel_id(r.source, r.source_cols, r.target)


STOP_AFTER_FAILURES = 3            # n226: so many failed queries in a row (same error) and the rest is not counted, said why


def failed_reason(e: BaseException) -> str:
    """n226: the state of an item whose counting query failed: "not counted: <reason>", or NOT_CHECKED when the call's
    time ran out under it (the statement timeout is cut to the budget)."""
    from . import budget as _budget
    if isinstance(e, _budget.TimeUp) or _budget.expired():
        return _budget.NOT_CHECKED
    detail = " ".join(str(e).split())[:200]
    return f"not counted: the counting query failed ({type(e).__name__}{': ' + detail if detail else ''})"


def validate(plan: Plan, execute, max_items: int = 60, on_step=None, tables=None, resume_from: int = 0) -> dict:
    """Run the checks for the keys and relationships of the plan (up to max_items checks: a key, a relationship and an
    extended relationship count one each, however many statements count them). Since round n108 the relationships of
    one source table are counted in one statement when there are two or more of them and their join columns have the
    same types on both sides; the counts are those of their own statements (relationship_sql), and if that statement
    fails their own statements run instead and combined_relationship_queries says so.

    n226: the items are taken in check_order (links by importance, each after its target's key), `tables` scopes them
    and `resume_from` skips the first so many of that order (the resume call of an answer cut by time or max_items). The
    call's time budget (budget.py) is looked at before every item: past it, the rest is "not checked (time)" and the
    answer says how to resume. A query that fails makes its item "not counted: <reason>" and the check goes on; after
    STOP_AFTER_FAILURES failures in a row with the same error the rest is not counted with that reason. Both are under
    `not_counted`, never among the counted keys and relationships, which keep the plan's order."""
    from . import budget as _budget
    schema = plan.schema.schema
    dialect = dialect_of(execute)
    queue = check_order(plan, tables)
    start = max(0, int(resume_from or 0))
    selected = queue[start:start + max(max_items, 0)]
    beyond = max(0, len(queue) - start - len(selected))
    rels_all = list(plan.relationships)
    ext_all = list(getattr(plan, "extended", []))
    key_out: dict[str, dict] = {}
    rel_out: dict[int, dict] = {}
    ext_out: dict[int, dict] = {}
    unique: dict[str, bool] = {}
    not_done: dict[tuple, str] = {}                                  # item -> "not counted: ..." or NOT_CHECKED
    step_total, step_done = len(selected), [0]
    failures = {"in_a_row": 0, "last": None, "stopped": None}

    def stepped(n: int = 1) -> None:
        # n223: on_step(done, total) after each key and relationship counted (the editor shows "3 of 7 ... counted")
        step_done[0] += n
        if on_step is not None:
            on_step(min(step_done[0], step_total), step_total)

    def failed(item, e: BaseException) -> None:
        reason = failed_reason(e)
        not_done[item] = reason
        stepped()
        if reason == _budget.NOT_CHECKED:
            return
        kind = type(e).__name__
        failures["in_a_row"] = failures["in_a_row"] + 1 if failures["last"] == kind else 1
        failures["last"] = kind
        if failures["in_a_row"] >= STOP_AFTER_FAILURES:
            failures["stopped"] = (f"not counted: {STOP_AFTER_FAILURES} counting queries in a row failed ({kind}); "
                                   "the rest was not tried")

    def ok() -> None:
        failures["in_a_row"], failures["last"] = 0, None

    def blocked(item) -> bool:
        """True when the item cannot be counted now (time, or the failures stopped the check); records why."""
        if _budget.expired():
            not_done[item] = _budget.NOT_CHECKED
            return True
        if failures["stopped"]:
            not_done[item] = failures["stopped"]
            return True
        return False

    def count_key(table: str) -> None:
        item = ("key", table)
        if table in key_out or item in not_done or blocked(item):
            return
        cols, rule = plan.keys[table]
        try:
            row = execute(key_sql(schema, table, cols, dialect))[0]
        except Exception as e:                                       # noqa: BLE001 - n226: this item, not the call
            failed(item, e)
            return
        ok()
        n, nulls, distinct = _int(row.get("n")), _int(row.get("nulls")), _int(row.get("distinct_keys"))
        unique[table] = n > 0 and nulls == 0 and distinct == n
        key_out[table] = {"table": table, "columns": cols, "rule": rule, "rows": n, "nulls": nulls,
                          "distinct": distinct, "verdict": key_verdict(n, nulls, distinct)}
        stepped()

    def args_of(r) -> dict:
        return dict(source_cols=r.source_cols, target=r.target, target_cols=r.target_cols, blank_is_none=r.rule == "SAP pack",
                    target_unique=target_key_unique(list(key_out.values()), r.target, r.target_cols))

    def rel_entry(r, with_value: int, orphans: int) -> dict:
        verdict = relationship_verdict(with_value, orphans)
        if r.target in unique and not unique[r.target]:
            verdict += f"; but the target key of {r.target} is not unique, so a row can match more than one"
        return {"source": r.source, "columns": r.source_cols, "target": r.target, "target_columns": r.target_cols,
                "rule": r.rule, "rows_with_value": with_value, "orphans": orphans, "verdict": verdict}

    # Round n108: the selected relationships of one source table with two or more of them are read in one statement
    sel_rels = [x for k, x in selected if k == "rel"]
    groups: dict[str, list[int]] = {}
    for i in sel_rels:
        if combinable(plan, rels_all[i]):
            groups.setdefault(rels_all[i].source, []).append(i)
    groups = {s: sorted(idx) for s, idx in groups.items() if len(idx) >= 2}
    group_of = {i: s for s, idx in groups.items() for i in idx}
    selected_keys = {x for k, x in selected if k == "key"}
    combined: list[dict] = []
    ran_group: set[str] = set()

    def run_group(source: str) -> None:
        ran_group.add(source)
        idx = groups[source]
        for i in idx:                                                # the targets' keys first, as before n226
            if rels_all[i].target in selected_keys:
                count_key(rels_all[i].target)
        idx = [i for i in idx if ("rel", i) not in not_done]
        if len(idx) < 2 or blocked(("rel", idx[0])):
            not_done.pop(("rel", idx[0]), None) if idx else None    # each is looked at again on its own
            return
        args = {i: args_of(rels_all[i]) for i in idx}
        sql = combined_relationship_sql(schema, source, [args[i] for i in idx], dialect)
        entry = {"source": source, "sql": sql, "relationships": [
            {"id": _rel_id(rels_all[i]), "sql": relationship_sql(schema, rels_all[i].source, rels_all[i].source_cols, rels_all[i].target,
                                                                 rels_all[i].target_cols, dialect, **{k: args[i][k] for k in ("blank_is_none", "target_unique")})}
            for i in idx]}
        try:
            row = execute(sql)[0]
            got = {}
            for n, i in enumerate(idx, 1):
                if f"with_value_{n}" not in row or f"orphans_{n}" not in row:   # not the answer this statement gives
                    raise LookupError(f"no with_value_{n} or orphans_{n} in the answer")
                got[i] = (_int(row.get(f"with_value_{n}")), _int(row.get(f"orphans_{n}")))
            for i, (w, o) in got.items():
                rel_out[i] = rel_entry(rels_all[i], w, o)
            ok()
            stepped(len(got))
        except Exception as e:                                       # noqa: BLE001 - the separate statements count them instead
            if isinstance(e, _budget.TimeUp) or _budget.expired():
                for i in idx:
                    not_done[("rel", i)] = _budget.NOT_CHECKED
            entry["fell_back"] = (f"the combined statement failed ({type(e).__name__}); each relationship of {source} "
                                  "was counted with its own statement instead")
        combined.append(entry)

    def count_rel(i: int) -> None:
        item = ("rel", i)
        if i in rel_out or item in not_done:
            return
        if i in group_of and group_of[i] not in ran_group:
            run_group(group_of[i])
            if i in rel_out or item in not_done:
                return
        if blocked(item):
            return
        r = rels_all[i]
        a = args_of(r)
        try:
            row = execute(relationship_sql(schema, r.source, r.source_cols, r.target, r.target_cols, dialect,
                                           blank_is_none=a["blank_is_none"], target_unique=a["target_unique"]))[0]
        except Exception as e:                                       # noqa: BLE001 - n226: this item, not the call
            failed(item, e)
            return
        ok()
        rel_out[i] = rel_entry(r, _int(row.get("with_value")), _int(row.get("orphans")))
        stepped()

    def count_ext(j: int) -> None:
        item = ("ext", j)
        if j in ext_out or item in not_done or blocked(item):
            return
        r = ext_all[j]
        entry = {"source": r.source, "columns": r.source_cols, "target": r.target, "target_columns": r.target_cols,
                 "rule": r.rule, "kind": r.kind, "join": r.join_sql(quote=dialect.quote)}
        try:
            row = execute(extended_sql(schema, r, dialect))[0]
        except Exception as e:                                       # noqa: BLE001 - n226: this item, not the call
            failed(item, e)
            return
        ok()
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
        ext_out[j] = entry
        stepped()

    for kind, x in selected:
        if kind == "key":
            count_key(x)
        elif kind == "rel":
            count_rel(x)
        else:
            count_ext(x)

    keys = [key_out[t] for t in plan.keys if t in key_out]                         # the plan's order, as before n226
    rels = [rel_out[i] for i in range(len(rels_all)) if i in rel_out] + [ext_out[j] for j in range(len(ext_all)) if j in ext_out]
    checked = len(keys) + len(rels)
    in_scope = len(queue)
    ok_keys = sum(1 for k in keys if k["verdict"].startswith("unique"))
    ok_rels = sum(1 for r in rels if r["verdict"].startswith("holds"))
    timed = [it for it in selected if not_done.get(it) == _budget.NOT_CHECKED]
    failed_items = [it for it in selected if it in not_done and not_done[it] != _budget.NOT_CHECKED]
    summary = (f"{ok_keys} of {len(keys)} keys unique, {ok_rels} of {len(rels)} relationships hold without orphans"
               + ("" if checked == in_scope and start == 0 else
                  f" (checked {checked} of {in_scope}" + (f", from item {start}" if start else "")
                  + ("; raise max_items to check the rest)" if beyond and not timed and not failed_items else ")")))
    if failed_items:
        summary += f"; {len(failed_items)} not counted because the query failed (see not_counted)"
    resume_at = None
    if timed:
        resume_at = start + selected.index(timed[0])
        summary += (f"; the time budget ran out: {len(timed)} not checked (time)"
                    + (f" and {beyond} beyond max_items" if beyond else "") + f", resume with resume_from={resume_at}")
    elif beyond:
        resume_at = start + len(selected)
    from . import amounts
    left = max_items - len(selected)
    levels = amounts.check(plan, execute if left > 0 and not _budget.expired() else None, max_items=min(20, max(left, 0)))
    out = {"summary": summary, "keys": keys, "relationships": rels, "amount_levels": levels}
    if combined:
        # Round n108: the statement that ran, once per source table with two or more relationships, and each of its
        # relationships' own statement (relationship_sql), which gives the same counts and can be run alone.
        out["combined_relationship_queries"] = combined
    if not_done:
        out["not_counted"] = [{"id": item_id(plan, it), "kind": {"key": "key", "rel": "relationship", "ext": "extended relationship"}[it[0]],
                               "evidence": not_done[it]} for it in selected if it in not_done]
    if beyond:
        out["not_checked_beyond_max_items"] = beyond
    if tables is not None or start:
        out["scope"] = {"items": in_scope, "resume_from": start, **({"tables": sorted(set(tables))} if tables is not None else {})}
    d = _budget.current()
    if d is not None or resume_at is not None:
        tb = {**(d.as_dict() if d is not None else {}), "ran_out": bool(timed), "counted": checked,
              "not_checked_time": len(timed)}
        if resume_at is not None:
            tb["resume_from"] = resume_at
            tb["resume"] = (f"validate_plan with resume_from={resume_at} and the same other arguments counts the next "
                            f"{in_scope - resume_at} item(s) in the same order"
                            + (" (tables= keeps the same scope)" if tables is not None else ""))
        out["time_budget" if d is not None else "resume"] = tb if d is not None else {k: tb[k] for k in ("resume_from", "resume")}
    out["note"] = ( "Counts over the whole tables at the moment of the call. They show the data agrees with the plan "
                    "today; they do not prove the meaning, and new rows can change them.")
    from . import coverage
    coverage.note(plan, out)                                       # n226: the call's answer gets the counted coverage
    return out


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
    if "header_column" in f:                                     # n106: a flat table's amount, counted per header value
        return "failed" if f.get("pattern") else "passed"
    per = f.get("rows_per_header")
    if not isinstance(per, dict):
        return "not_counted"
    return "failed" if per.get("max_lines", 0) > 1 else "passed"


def _amount_items(full: dict) -> list[dict]:
    """amount_levels' findings (a header amount a join repeats) and, since n106, its flat_tables entries (an amount a
    flat table repeats on every row of a header value): one group in the summary, as in the full answer."""
    levels = full.get("amount_levels") or {}
    return list(levels.get("findings", [])) + list(levels.get("flat_tables", []))


def summarize(full: dict, plan: Plan | None = None) -> dict:
    """validate_plan's summary form (round n101), written only from the full answer: nothing is counted or queried
    again. It keeps the verdict line, the totals per kind of check, and every check that failed, was not counted or
    holds with a warning ("; but ...") exactly as the full answer has it (counts, rule, SQL). Passing checks become a
    count, and the answer says how many were left out and that detail="full" lists them. `plan` gives the number of
    checks max_items left out."""
    groups = (("keys", full.get("keys", []), _key_status),
              ("relationships", full.get("relationships", []), _rel_status),
              ("amount_levels", _amount_items(full), _amount_status))
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
        # n226: validate says how many items max_items left out (its scope may be narrower than the plan)
        skipped = full.get("not_checked_beyond_max_items", 0)
        if skipped > 0:
            totals["not_checked_beyond_max_items"] = skipped
    nc = list(full.get("not_counted") or [])
    if nc:                                                           # n226: time ran out, or a query failed: never "passed"
        attention["not_counted"] = nc
        totals["not_counted_items"] = len(nc)
    passing = sum(left.values())
    skipped = totals.get("not_checked_beyond_max_items", 0)
    out = {"detail": "summary", "summary": full.get("summary", "")}
    for k in ("time_budget", "resume", "scope"):
        if k in full:
            out[k] = full[k]
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
    out["next_steps"] = next_steps(full, totals)
    if "personal_data" in full:
        out["personal_data"] = full["personal_data"]
    out["note"] = full.get("note", "")
    return out


# Round n103: what to do after validate_plan, in the summary form only. Fixed rules over the full answer, in this
# order; each rule gives at most one step, a tool appears at most once, and the first three steps are kept. Only tools
# that read or draft, in both the local and the hosted server; no creating tool, so no dry run is needed either.
NEXT_STEP_TOOLS = ("sample_rows", "review_plan", "answer_query_draft", "validate_plan", "suggest_relationships",
                   "semantic_model_draft", "ontology_draft", "plan_backend", "list_tables")
MAX_NEXT_STEPS = 3


def _step(tool: str, arguments: dict, why: str) -> dict:
    import json
    shown = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in arguments.items())
    return {"tool": tool, "arguments": arguments, "why": why,
            "text": f"{tool}({shown}), other arguments as in this call: {why}"}


def next_steps(full: dict, totals: dict | None = None) -> list[dict]:
    """Up to three steps after validate_plan, each {tool, arguments, why, text}: the arguments come from this result
    only (table names, the item id, the amount column); the other arguments (workspace, source, schema, keys,
    confirmed) are this call's. The rules, in order:
      1. a key that is not unique or has NULLs: sample_rows on its table;
      2. a relationship with orphans: review_plan with validate=true on its two tables, to record a decision on it;
      3. a header amount that a join repeats: answer_query_draft for its total per header over header and line;
      4. a relationship that holds with a warning (a target matched more than once): sample_rows on the target;
      5. checks left out by time (n226: validate_plan with resume_from) or by max_items: validate_plan with a max_items
         that covers them (at most 200), or resume_from with 200 when more are left;
      6. a relationship with orphans: suggest_relationships, for another target of the column;
      7. nothing failed, nothing left out and at least one check passed: semantic_model_draft, then ontology_draft;
      8. no check ran at all: plan_backend, then list_tables;
      9. fewer than two steps so far: review_plan with validate=true, to keep the checks as a file."""
    from .review import key_id, rel_id
    keys = full.get("keys", [])
    rels = full.get("relationships", [])
    findings = (full.get("amount_levels") or {}).get("findings", [])
    totals = totals or {}
    skipped = totals.get("not_checked_beyond_max_items", 0)
    bad_keys = [k for k in keys if _key_status(k) == "failed"]
    orphans = [r for r in rels if _rel_status(r) == "failed" and r.get("orphans", 0) > 0]
    warned = [r for r in rels if _rel_status(r) == "warning"]
    repeated = [f for f in findings if _amount_status(f) == "failed" and f.get("amount_columns")]
    failed = bad_keys or orphans or warned or repeated or any(
        t.get("failed") for t in totals.values() if isinstance(t, dict))
    passed = sum(t.get("passed", 0) for t in totals.values() if isinstance(t, dict))
    steps: list[dict] = []

    def add(tool, arguments, why):
        if all(s["tool"] != tool for s in steps):
            steps.append(_step(tool, arguments, why))

    if bad_keys:
        k = bad_keys[0]
        add("sample_rows", {"table": k["table"], "n": 10},
            f"{key_id(k['table'])} on {', '.join(k['columns'])} is {k['verdict']}; a few rows show which columns "
            "identify a row, to pass as keys to validate_plan.")
    if orphans:
        r = orphans[0]
        add("review_plan", {"validate": True, "tables": sorted({r["source"], r["target"]})},
            f"{rel_id(r['source'], r['columns'], r['target'])}: {r['verdict']}; record in decisions whether it is "
            "accepted or rejected, with the reason.")
    if repeated:
        f = repeated[0]
        col = f["amount_columns"][0]
        add("answer_query_draft", {"question": f"total {col} per {f['header']}", "tables": [f["header"], f["line"]]},
            f"{f['header']}.{col} is repeated on every {f['line']} row in a join; the draft sums it once per "
            f"{f['header']} row.")
    if warned:
        r = warned[0]
        add("sample_rows", {"table": r["target"], "n": 10},
            f"{rel_id(r['source'], r['columns'], r['target'])} holds, but a row can match more than one row of "
            f"{r['target']}; a few rows of {r['target']} show why.")
    resume = (full.get("time_budget") or full.get("resume") or {}).get("resume_from")
    timed = (full.get("time_budget") or {}).get("not_checked_time", 0)
    if timed and resume is not None:                                  # n226: the call's time ran out
        add("validate_plan", {"resume_from": resume},
            f"{timed} check(s) were not checked because the call's time budget ran out; this counts on from there.")
    elif skipped:
        checked = len(keys) + len(rels)
        if checked + skipped <= 200 or resume is None:
            add("validate_plan", {"max_items": min(200, checked + skipped)},
                f"{skipped} check(s) did not run because max_items was reached.")
        else:                                                         # n226: more than one call can count
            add("validate_plan", {"resume_from": resume, "max_items": 200},
                f"{skipped} check(s) did not run because max_items was reached; this counts the next 200.")
    if orphans:
        r = orphans[0]
        add("suggest_relationships", {},
            f"{r['source']}.{'+'.join(r['columns'])} has rows that point at nothing in {r['target']}; the candidates "
            "show whether another table fits it, counted against the data.")
    if not failed and not skipped and passed:
        add("semantic_model_draft", {}, f"all {passed} counted checks passed; the draft shows the Power BI model "
                                        "built on these keys and relationships, creating nothing.")
        add("ontology_draft", {}, "the draft shows the Fabric IQ ontology built on the same plan, creating nothing.")
    if not keys and not rels and not _amount_items(full) and not skipped:
        add("plan_backend", {}, "no check ran; the plan shows which keys and relationships were inferred and which "
                                "keys to give.")
        add("list_tables", {}, "the tables and columns show which columns could be a key.")
    if len(steps) < 2:
        add("review_plan", {"validate": True}, "keeps the plan, its checks and the decisions made about it as one file.")
    return steps[:MAX_NEXT_STEPS]


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
