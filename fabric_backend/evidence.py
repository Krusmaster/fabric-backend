"""Evidence from the data: is an inferred key unique, does an inferred relationship hold?

Names suggest keys and relationships (infer.py); this module checks them against the rows, read-only. Every query is
built from table and column names that came from the source's own metadata, quoted as identifiers — never from
free text — and returns a handful of counts, not rows.

    key:          rows, distinct key values, rows with a NULL in the key   -> unique / duplicates / nulls
    relationship: rows with a value, rows whose value has no match         -> holds / orphans
"""
from __future__ import annotations

from .infer import Plan


def qi(name: str) -> str:
    """Quote a T-SQL identifier."""
    return "[" + str(name).replace("]", "]]") + "]"


def _t(schema: str, table: str) -> str:
    return f"{qi(schema)}.{qi(table)}"


def key_sql(schema: str, table: str, cols: list[str]) -> str:
    cs = ", ".join(qi(c) for c in cols)
    not_null = " AND ".join(f"{qi(c)} IS NOT NULL" for c in cols)
    any_null = " OR ".join(f"{qi(c)} IS NULL" for c in cols)
    return (f"SELECT COUNT_BIG(*) AS n, "
            f"SUM(CASE WHEN {any_null} THEN 1 ELSE 0 END) AS nulls, "
            f"(SELECT COUNT_BIG(*) FROM (SELECT DISTINCT {cs} FROM {_t(schema, table)} WHERE {not_null}) AS d) AS distinct_keys "
            f"FROM {_t(schema, table)}")


def relationship_sql(schema: str, source: str, source_cols: list[str], target: str, target_cols: list[str]) -> str:
    on = " AND ".join(f"s.{qi(a)} = t.{qi(b)}" for a, b in zip(source_cols, target_cols))
    has_value = " AND ".join(f"s.{qi(a)} IS NOT NULL" for a in source_cols)
    first = qi(target_cols[0])
    tcs = ", ".join(qi(c) for c in target_cols)
    # DISTINCT on the target side: a duplicated target key must not multiply the source rows being counted
    return (f"SELECT COUNT_BIG(*) AS with_value, SUM(CASE WHEN t.{first} IS NULL THEN 1 ELSE 0 END) AS orphans "
            f"FROM {_t(schema, source)} AS s LEFT JOIN (SELECT DISTINCT {tcs} FROM {_t(schema, target)}) AS t ON {on} "
            f"WHERE {has_value}")


def sample_sql(schema: str, table: str, columns: list[str], n: int) -> str:
    return f"SELECT TOP ({int(n)}) {', '.join(qi(c) for c in columns)} FROM {_t(schema, table)}"


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
    keys, rels, budget = [], [], max_items
    unique: dict[str, bool] = {}
    for table, (cols, rule) in plan.keys.items():
        if budget <= 0:
            break
        budget -= 1
        row = execute(key_sql(schema, table, cols))[0]
        n, nulls, distinct = _int(row.get("n")), _int(row.get("nulls")), _int(row.get("distinct_keys"))
        unique[table] = n > 0 and nulls == 0 and distinct == n
        keys.append({"table": table, "columns": cols, "rule": rule, "rows": n, "nulls": nulls,
                     "distinct": distinct, "verdict": key_verdict(n, nulls, distinct)})
    for r in plan.relationships:
        if budget <= 0:
            break
        budget -= 1
        row = execute(relationship_sql(schema, r.source, r.source_cols, r.target, r.target_cols))[0]
        with_value, orphans = _int(row.get("with_value")), _int(row.get("orphans"))
        verdict = relationship_verdict(with_value, orphans)
        if r.target in unique and not unique[r.target]:
            verdict += f"; but the target key of {r.target} is not unique, so a row can match more than one"
        rels.append({"source": r.source, "columns": r.source_cols, "target": r.target, "target_columns": r.target_cols,
                     "rule": r.rule, "rows_with_value": with_value, "orphans": orphans, "verdict": verdict})
    checked = len(keys) + len(rels)
    total = len(plan.keys) + len(plan.relationships)
    ok_keys = sum(1 for k in keys if k["verdict"].startswith("unique"))
    ok_rels = sum(1 for r in rels if r["verdict"].startswith("holds"))
    summary = (f"{ok_keys} of {len(keys)} keys unique, {ok_rels} of {len(rels)} relationships hold without orphans"
               + ("" if checked == total else f" (checked {checked} of {total}; raise max_items to check the rest)"))
    return {"summary": summary, "keys": keys, "relationships": rels,
            "note": "Counts over the whole tables at the moment of the call. They show the data agrees with the plan "
                    "today; they do not prove the meaning, and new rows can change them."}


def suggest_composite_keys(plan: Plan) -> list[dict]:
    """Keyless tables whose reference to a keyed table plus a line/position-like column could form a key,
    e.g. order_items: order_id + line_no. Suggestions only — pass them as `keys` after checking them."""
    line_like = ("line", "lineno", "linenumber", "lineno", "position", "pos", "seq", "sequence", "itemno", "rowno")
    out = []
    keyless = [t for t in plan.schema if t.name not in plan.keys]
    for t in keyless:
        refs = [r for r in plan.relationships if r.source == t.name and len(r.source_cols) == 1]
        lines = [c for c in t.column_names if c.lower().replace("_", "") in line_like
                 or c.lower().endswith(("_line", "_line_no", "_seq", "_pos"))]
        for r in refs:
            for line in lines:
                out.append({"table": t.name, "columns": [r.source_cols[0], line],
                            "why": f"{r.source_cols[0]} points at {r.target} and {line} numbers the rows within it",
                            "use": {t.name: [r.source_cols[0], line]}})
    return out
