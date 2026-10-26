"""Evidence from the data: is an inferred key unique, does an inferred relationship hold?

Names suggest keys and relationships (infer.py); this module checks them against the rows, read-only. Every query is
built from table and column names that came from the source's own metadata, quoted as identifiers — never from
free text — and returns a handful of counts, not rows.

    key:          rows, distinct key values, rows with a NULL in the key   -> unique / duplicates / nulls
    relationship: rows with a value, rows whose value has no match         -> holds / orphans
"""
from __future__ import annotations

from .infer import _HISTORY, _norm, Plan


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


def inclusion_sql(schema: str, source: str, column: str, target: str, key: str) -> str:
    """Inclusion check for a candidate relationship: how many non-NULL values of source.column exist in target.key,
    and how many distinct values the column has. One counting statement, read-only."""
    return (f"SELECT COUNT_BIG(*) AS with_value, COUNT_BIG(t.{qi(key)}) AS matched, COUNT_BIG(DISTINCT s.{qi(column)}) AS distinct_values "
            f"FROM {_t(schema, source)} AS s LEFT JOIN (SELECT DISTINCT {qi(key)} FROM {_t(schema, target)}) AS t "
            f"ON s.{qi(column)} = t.{qi(key)} WHERE s.{qi(column)} IS NOT NULL")


# Column types a DB-API driver cannot fetch as they come, or that are noise in a sample. pyodbc answers "ODBC SQL type
# -151 is not yet supported" for SQL Server's CLR types and -150 for sql_variant, which fails the whole call; binary
# values are bytes that say nothing about a column's meaning. Read the CLR types as text, sql_variant as nvarchar,
# binary as its size in bytes.
_CLR_AS_TEXT = {"hierarchyid", "geography", "geometry"}
_VARIANT = {"sql_variant"}
_BINARY = {"binary", "varbinary", "image"}


def sample_expr(column: str, data_type: str = "") -> str:
    t = (data_type or "").lower().split("(")[0].strip()
    c = qi(column)
    if t in _CLR_AS_TEXT:
        return f"{c}.ToString() AS {c}"
    if t in _VARIANT:
        return f"CAST({c} AS nvarchar(4000)) AS {c}"
    if t in _BINARY:
        return f"DATALENGTH({c}) AS {qi(column + ' (bytes)')}"
    return c


def sample_sql(schema: str, table: str, columns: list[str], n: int, types: dict[str, str] | None = None) -> str:
    """The first n rows. `types` (column -> SQL type, as INFORMATION_SCHEMA gives it) reads the columns a driver cannot
    fetch as text and binary columns as their size; without it every column is selected as it is."""
    types = {str(k).lower(): v for k, v in (types or {}).items()}
    cols = ", ".join(sample_expr(c, types.get(c.lower(), "")) for c in columns)
    return f"SELECT TOP ({int(n)}) {cols} FROM {_t(schema, table)}"


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
