"""Round n132: a column profile of the tables validate_plan checked, without row values.

validate_plan(profile=true) adds, per column of each checked table (a table a counted key or relationship is on): the
table's rows, the column's NULL share and its distinct count, and for numbers and dates whether the smallest value is
below and the largest above a range. Numbers are compared with zero unless a range is stated; dates only with a stated
range. Never a value: no MIN or MAX, no sample, no most-frequent value leaves the database. Each comparison is a CASE
around MIN/MAX inside the query (the n105 range pattern, graphs.range_sql), so the answer carries 1 or 0 and the values
are not even read by the server. KRUSGRAPH_NO_ROW_VALUES (n123) therefore needs nothing removed here.

- One aggregate query per table, with every column's counts in it; not one query per column.
- Each table is one item of max_items, after the checks validate_plan ran (keys, relationships, amount levels); tables
  beyond what is left are listed by name as not profiled.
- A column whose name or tag looks like personal data (privacy.personal_columns) gets counts only: no range check.
- Types COUNT(DISTINCT …) cannot read (text, ntext, image, xml, geography, geometry, map, array, struct, variant) get no
  distinct count.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from .dialects import of as dialect_of
from .graphs import _family, _type
from .infer import Plan, PlanInputError

NO_DISTINCT = {"text", "ntext", "image", "xml", "geography", "geometry", "map", "array", "struct", "variant"}
RULE = ("Per column of each checked table: rows, NULL share, distinct count; numbers compared with zero (or a stated range), "
        "dates with a stated range, as below/above only. Never a value; personal-data columns get counts only.")


def options(profile) -> dict | None:
    """validate_plan's `profile`: false/None (off), true (numbers against zero), or {"numbers": [lo, hi], "dates":
    ["YYYY-MM-DD", "YYYY-MM-DD"]} (either key optional). Anything else is a bad_input error."""
    if profile is None or profile is False:
        return None
    if profile is True:
        return {"numbers": None, "dates": None}
    if not isinstance(profile, dict) or not profile or set(profile) - {"numbers", "dates"}:
        raise PlanInputError('profile: true, false or {"numbers": [low, high], "dates": ["YYYY-MM-DD", "YYYY-MM-DD"]}')
    out = {"numbers": None, "dates": None}
    if profile.get("numbers") is not None:
        out["numbers"] = _pair(profile["numbers"], _number, "numbers", "two numbers")
    if profile.get("dates") is not None:
        out["dates"] = _pair(profile["dates"], _date, "dates", 'two dates "YYYY-MM-DD"')
    return out


def _pair(v, parse, name: str, what: str):
    if not isinstance(v, (list, tuple)) or len(v) != 2:
        raise PlanInputError(f"profile.{name}: {what}, low first")
    lo, hi = parse(v[0]), parse(v[1])
    if lo is None or hi is None or lo > hi:
        raise PlanInputError(f"profile.{name}: {what}, low first")
    return lo, hi


def _number(v):
    if isinstance(v, bool):
        return None
    try:
        n = Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        return None
    return n if n.is_finite() else None


def _date(v):
    try:
        return date.fromisoformat(v) if isinstance(v, str) and len(v) == 10 else None
    except ValueError:
        return None


def _bounds(family: str | None, opts: dict):
    """(low literal, high literal, how the answer names them) for a column, or None when it gets no range check."""
    if family == "number":
        if opts["numbers"] is None:
            return "0", "0", "zero"
        lo, hi = opts["numbers"]
        return str(lo), str(hi), [_plain(lo), _plain(hi)]
    if family == "datetime" and opts["dates"] is not None:
        lo, hi = opts["dates"]
        return f"'{lo.isoformat()}'", f"'{hi.isoformat()}'", [lo.isoformat(), hi.isoformat()]
    return None


def _plain(n: Decimal):
    return int(n) if n == n.to_integral_value() else float(n)


def _columns(table, flagged: dict, opts: dict) -> list[dict]:
    out = []
    for i, c in enumerate(table.columns, 1):
        masked = flagged.get((table.name, c.name))
        b = None if masked else _bounds(_family(c.data_type), opts)
        out.append({"i": i, "name": c.name, "type": _type(c.data_type), "masked": masked,
                    "distinct": _type(c.data_type) not in NO_DISTINCT, "bounds": b})
    return out


def profile_sql(schema: str, table: str, cols: list[dict], dialect) -> str:
    """One aggregate over the whole table. Per column c<i>: nulls, distinct (when the type allows), and with bounds
    lo/hi flags (1 when MIN is below the low bound / MAX above the high bound). No value is selected."""
    q = dialect.quote
    parts = [f"{dialect.count}(*) AS n"]
    for c in cols:
        col, i = q(c["name"]), c["i"]
        parts.append(f"SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) AS c{i}_nulls")
        if c["distinct"]:
            parts.append(f"COUNT(DISTINCT {col}) AS c{i}_distinct")
        if c["bounds"]:
            lo, hi, _ = c["bounds"]
            parts.append(f"CASE WHEN MIN({col}) < {lo} THEN 1 ELSE 0 END AS c{i}_lo")
            parts.append(f"CASE WHEN MAX({col}) > {hi} THEN 1 ELSE 0 END AS c{i}_hi")
    return f"SELECT {', '.join(parts)} FROM {dialect.table(schema, table)}"


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def checked_tables(plan: Plan, out: dict) -> list[str]:
    """The tables validate_plan's answer counted something on, in the schema's order."""
    seen = {k["table"] for k in out.get("keys", [])}
    for r in out.get("relationships", []):
        seen |= {r["source"], r["target"]}
    return [t.name for t in plan.schema if t.name in seen]


def items_used(out: dict, statements: int) -> int:
    """max_items used by validate_plan: one per key and relationship counted, plus each amount-level statement. The
    amount statements are what is left of `statements` after the key and relationship statements (n108 combines the
    relationships of a source table into one statement, so those are worked out from combined_relationship_queries)."""
    keys, rels = len(out.get("keys", [])), len(out.get("relationships", []))
    combined = out.get("combined_relationship_queries", [])
    folded = sum(len(e["relationships"]) for e in combined if "fell_back" not in e)
    rel_statements = len(combined) + rels - folded
    return keys + rels + max(0, statements - keys - rel_statements)


class Counting:
    """execute, counting the statements (to know what validate_plan used of max_items)."""

    def __init__(self, execute):
        self.execute, self.statements = execute, 0
        for a in ("dialect", "source_item"):
            if hasattr(execute, a):
                setattr(self, a, getattr(execute, a))

    def __call__(self, sql):
        self.statements += 1
        return self.execute(sql)


def run(plan: Plan, execute, opts: dict, tables: list[str], budget: int) -> dict:
    """The profile of `tables` (at most `budget` of them, one query each)."""
    from . import privacy
    dialect = dialect_of(execute)
    schema = plan.schema.schema
    flagged = privacy.personal_columns(plan.schema, tables)
    by_name = {t.name: t for t in plan.schema}
    profiled, left = [], []
    for name in tables:
        if budget <= 0:
            left.append(name)
            continue
        budget -= 1
        cols = _columns(by_name[name], flagged, opts)
        entry: dict = {"table": name}
        try:
            row = list(execute(profile_sql(schema, name, cols, dialect)))[0]
        except Exception as e:                                       # noqa: BLE001 - the class only: a message can quote a value
            entry["error"] = f"the profile query failed ({type(e).__name__})"
            profiled.append(entry)
            continue
        n = _int(row.get("n"))
        entry["rows"] = n
        entry["columns"] = [_column(c, row, n) for c in cols]
        profiled.append(entry)
    out = {"rule": RULE, "queries": len(profiled), "tables": profiled}
    if left:
        out["not_profiled"] = left
        out["how"] = f"{len(left)} table(s) not profiled: max_items was used up; raise max_items (at most 200)."
    if opts["dates"] is None and any(_family(c.data_type) == "datetime" for t in tables for c in by_name[t].columns):
        out["dates"] = 'Dates are compared only with a stated range: profile={"dates": ["YYYY-MM-DD", "YYYY-MM-DD"]}.'
    return out


def _column(c: dict, row: dict, n: int) -> dict:
    i = c["i"]
    nulls = _int(row.get(f"c{i}_nulls"))
    e = {"column": c["name"], "type": c["type"], "null_share": round(nulls / n, 4) if n else None}
    e["distinct"] = _int(row.get(f"c{i}_distinct")) if c["distinct"] else None
    if c["masked"]:
        e["personal_data"] = c["masked"].get("rule", "personal data") if isinstance(c["masked"], dict) else "personal data"
    elif c["bounds"]:
        _, _, against = c["bounds"]
        if n - nulls <= 0:
            e["range"] = {"against": against, "result": "no values"}
        else:
            lo, hi = bool(_int(row.get(f"c{i}_lo"))), bool(_int(row.get(f"c{i}_hi")))
            e["range"] = {"against": against, "min_below": lo, "max_above": hi}
    return e


def validate_with_profile(plan: Plan, execute, max_items: int, profile, **scope) -> tuple[dict, dict | None]:
    """evidence.validate, and with `profile` on, the profile of the checked tables in what is left of max_items.
    `scope` (n226): validate's tables= and resume_from=. The profile is skipped when the call's time has run out."""
    from . import budget, evidence
    scope = {k: v for k, v in scope.items() if v}
    opts = options(profile)
    if opts is None:
        return evidence.validate(plan, execute, max_items=max_items, **scope), None
    counting = Counting(execute)
    out = evidence.validate(plan, counting, max_items=max_items, **scope)
    if budget.expired():
        return out, {"not_counted": budget.NOT_CHECKED}
    left = max(0, max_items - items_used(out, counting.statements))
    return out, run(plan, execute, opts, checked_tables(plan, out), left)
