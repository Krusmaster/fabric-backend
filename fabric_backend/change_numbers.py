"""The numbers before and after each change, counted on the rows (round LFD4, 25 November 2026; docs/CHANGES.md).

changes.apply says a list of changes is allowed against the plan. This module says what each change does to the
numbers, by counting: for every change of the list, the SELECT statements that give the numbers before it (the changes
before it in the list applied) and after it (it applied too), run on the source, and the answers. No model and no
guess: every number comes with the statement that produced it, as receipt.build gives them for validate_plan, so anyone
can run the statement on the same tables and get the same number back.

    count(applied, plan, execute)        -> per change: its numbers, before and after, each with its SQL; the doubling
                                            checks of the joins it adds; a receipt row per statement
    count_path(change, plan, execute)    -> an add_column's join path counted as it is, also one changes.validate denied
                                            (fan_out): the rows and amounts before and after the join, and whether they
                                            differ
    statements(applied, plan)            -> the statements alone, nothing run
    markdown(answer)                     -> the receipt as krusgraph-receipt.md (receipt.markdown)

What is counted, per change type:

- filter_rows: the rows of the filtered table and of each table in its cascade, before and after, with the distinct
  values of each single-column reference of those tables; the sum of every amount of the plan that reads those tables
  (amounts.order_amount_measures: quantity × price and the amounts a line carries; the header amounts, summed once per
  header row), before and after, with the difference and its share. The other amounts, and the tables that point at the
  filtered ones from outside the cascade, are counted once and said to be untouched.
- add_column: the rows of the table's view before and after the join (they must be equal: no row is repeated), how
  many rows have no value in each new column, and how many distinct values it has. The doubling check: every amount on
  the table, or on a line table that points at it, is summed before and after the join; the sums must be equal.
- add_measure: the measure's value (a ratio is its numerator and denominator, each counted, divided as DAX's DIVIDE
  does), also on the source as it is when filters come before it, and the plan's other measures, unchanged.
- add_link: nothing is counted here (it changes no row; validate_plan counts the link).

The state "after a filter_rows" is counted on the source: a row is left out when the change's drop_where holds for it
(a NULL never matches), and a row of a cascade table when it points, over the links changes.validate resolved, at a row
the change leaves out, as the silver notebook and silver.simulate do it. Several filters: a row stays when no filter
leaves it out. A gold view's rows are the table's rows in that state; an add_column joins with LEFT JOINs to rows in
that state too.

Rules that hold for every answer:

- Only SELECT statements; nothing is written. Names are quoted by the dialect (dialects.py: T-SQL for Fabric, SQLite
  for the tests, Databricks) and come from the plan; a value comes only from the change's own drop_where.
- Counts and sums only, never a row value: a distinct count is a number, not the values. With KRUSGRAPH_NO_ROW_VALUES=1
  a sum over fewer than MIN_GROUP rows is hidden and only the count is shown (one or two rows would show their values).
- One time budget per call (budget.py): a statement that is not reached in time is NOT_COUNTED, "not counted (time)",
  with no number; a statement that fails is "not counted: <reason>". Never a guess.

Pure apart from the `execute` the caller hands in; no network, no clock but the budget's.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from . import amounts, budget, changes as _changes
from .dialects import TSQL, Dialect, sqlite_sql

NOT_COUNTED = "not counted (time)"
COUNTED = "counted"
NOT_RUN = "not run"
MIN_GROUP = 3                              # a sum over fewer rows is hidden with KRUSGRAPH_NO_ROW_VALUES=1
HIDDEN = (f"hidden: fewer than {MIN_GROUP} rows, so the sum would show row values (KRUSGRAPH_NO_ROW_VALUES); "
          "only the count is shown")
MAX_DEPTH = 6                              # cascade links followed at most this deep (changes.MAX_HOPS is 5)
_STRING = ("char", "string", "text", "varchar")
_BOOL = ("bool", "bit")


class NumbersError(ValueError):
    """The input cannot be counted: not an applied list, or a name that is not in the plan."""


# ------------------------------------------------------------------ dialect and formatting ---------------------------

def _dialect(dialect, execute) -> tuple[Dialect, str]:
    """(the dialect the statements are written in, the name the receipt states). None: the connection's own
    (execute.dialect, else T-SQL); "sqlite": the engine's T-SQL as dialects.sqlite_sql gives it to SQLite."""
    if isinstance(dialect, Dialect):
        return dialect, dialect.name
    if dialect in (None, ""):
        d = getattr(execute, "dialect", None)
        return (d, d.name) if isinstance(d, Dialect) else (TSQL, "tsql")
    if dialect == "tsql":
        return TSQL, "tsql"
    if dialect == "sqlite":
        return TSQL, "sqlite"
    raise NumbersError(f"unknown dialect {dialect!r}: tsql, sqlite or a dialects.Dialect")


def _dec(v) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(repr(v) if isinstance(v, float) else str(v))
    except (InvalidOperation, ValueError):
        return None


def money(v) -> str | None:
    """An amount as text with two decimals ("51296.70"); a float from the driver is read by its shortest repr."""
    d = _dec(v)
    return None if d is None else str(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _int(v) -> int | None:
    d = _dec(v)
    return None if d is None else int(d)


def _percent(before: Decimal, diff: Decimal) -> str | None:
    if not before:
        return None
    return str((diff * 100 / before).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _spaced(text: str | int | None) -> str:
    """56834.70 -> 56 834.70, for the sentences."""
    if text is None:
        return "(none)"
    s = str(text)
    sign, s = ("-", s[1:]) if s.startswith("-") else ("", s)
    whole, _, frac = s.partition(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    return sign + " ".join([whole, *groups]) + (f".{frac}" if frac else "")


# ------------------------------------------------------------------ the SQL --------------------------------------------

class _Sql:
    """The statements of one plan in one dialect. Aliases follow the nesting (t, tp0, tp0p1, j1, j1p0), so the same
    number gives the same text wherever it is asked for, and the runner counts it once."""

    def __init__(self, plan, d: Dialect):
        self.plan, self.d = plan, d
        self.schema = plan.schema.schema

    def table(self, name: str) -> str:
        if name not in self.plan.schema:
            raise NumbersError(f"{name!r} is not a table of the plan")
        return self.d.table(self.schema, name)

    def col(self, alias: str, table: str, column: str) -> str:
        if column not in self.plan.schema[table].column_names:
            raise NumbersError(f"{table}.{column} is not a column of the plan")
        return f"{alias}.{self.d.quote(column)}"

    def type_of(self, table: str, column: str) -> str:
        c = next((c for c in self.plan.schema[table].columns if c.name == column), None)
        return str(getattr(c, "data_type", "") or "").lower()

    # a drop_where, as the silver notebook's condition: a NULL never matches -------------------------------------------
    def predicate(self, p: dict, alias: str, table: str) -> str:
        for op, word in (("any", " OR "), ("all", " AND ")):
            if op in p:
                return "(" + word.join(self.predicate(x, alias, table) for x in p[op]) + ")"
        c, typ = self.col(alias, table, p["column"]), self.type_of(table, p["column"])
        if p["op"] == "equals":
            v = p["value"]
            if isinstance(v, bool):
                lit = ("TRUE" if v else "FALSE") if self.d.name == "databricks" else ("1" if v else "0")
            elif isinstance(v, (int, float)):
                lit = repr(v)
            else:
                lit = "'" + str(v).replace("'", "''") + "'"
            return f"({c} IS NOT NULL AND {c} = {lit})"
        if p["op"] == "is_true":
            if any(s in typ for s in _STRING):
                return f"({c} IS NOT NULL AND LOWER(LTRIM(RTRIM({c}))) IN ('true', 't', 'yes', 'y', '1'))"
            if any(s in typ for s in _BOOL) and self.d.name == "databricks":
                return f"({c} IS NOT NULL AND {c} = TRUE)"
            return f"({c} IS NOT NULL AND {c} <> 0)"
        if any(s in typ for s in _STRING) or not typ:
            return f"({c} IS NOT NULL AND LTRIM(RTRIM({c})) <> '')"
        return f"({c} IS NOT NULL)"

    def goes(self, entry: dict, table: str, alias: str, depth: int = 0) -> str | None:
        """The condition under which a row of `table` (as `alias`) is left out by one filter_rows: its drop_where, or for
        a cascade table, a link that points at a row the change leaves out. None: the change does not touch the table."""
        c = entry["change"]
        if table == c["table"]:
            return self.predicate(c["drop_where"], alias, table)
        through = next((x["through"] for x in entry.get("resolved", {}).get("cascade", []) if x["table"] == table), None)
        if not through or depth >= MAX_DEPTH:
            return None
        parts = []
        for i, link in enumerate(through):
            parent, inner_alias = link["to"]["table"], f"{alias}p{i}"
            inner = self.goes(entry, parent, inner_alias, depth + 1)
            if inner is None:
                continue
            on = " AND ".join(f"{self.col(inner_alias, parent, b)} = {self.col(alias, table, a)}"
                              for a, b in zip(link["from"]["columns"], link["to"]["columns"]))
            parts.append(f"EXISTS (SELECT 1 FROM {self.table(parent)} AS {inner_alias} WHERE {on} AND {inner})")
        if not parts:
            return None
        return parts[0] if len(parts) == 1 else "(" + " OR ".join(parts) + ")"

    def kept(self, table: str, alias: str, state: list[dict]) -> str | None:
        conds = [g for e in state if (g := self.goes(e, table, alias)) is not None]
        return " AND ".join(f"NOT {g}" for g in conds) or None

    @staticmethod
    def where(*conds) -> str:
        conds = [c for c in conds if c]
        return (" WHERE " + " AND ".join(conds)) if conds else ""

    # statements --------------------------------------------------------------------------------------------------
    def rows(self, table: str, state: list[dict], distinct: list[str] = ()) -> str:
        cols = "".join(f", COUNT(DISTINCT {self.col('t', table, c)}) AS d{i}" for i, c in enumerate(distinct, 1))
        return f"SELECT {self.d.count}(*) AS n{cols} FROM {self.table(table)} AS t{self.where(self.kept(table, 't', state))}"

    def distinct(self, table: str, column: str, state: list[dict]) -> str:
        return (f"SELECT COUNT(DISTINCT {self.col('t', table, column)}) AS n FROM {self.table(table)} AS t"
                f"{self.where(self.kept(table, 't', state))}")

    def amount_from(self, src: dict, state: list[dict], alias: str = "t") -> tuple[str, str, list[str]]:
        """(the expression summed, the FROM part, the conditions) of an amount source over its table as `alias`."""
        frm = f"{self.table(src['table'])} AS {alias}"
        if src.get("dim"):
            dim, on = src["dim"], " AND ".join(f"d.{self.d.quote(b)} = {alias}.{self.d.quote(a)}" for a, b in src["on"])
            kd = self.kept(dim, "d", state)
            frm += f" LEFT JOIN {self.table(dim)} AS d ON {on}" + (f" AND {kd}" if kd else "")
            expr = f"{self.col(alias, src['table'], src['quantity'])} * {self.col('d', dim, src['price'])}"
        else:
            expr = self.col(alias, src["table"], src["column"])
        return expr, frm, [self.kept(src["table"], alias, state)]

    def total(self, src: dict, state: list[dict]) -> str:
        expr, frm, conds = self.amount_from(src, state)
        return f"SELECT {self.d.count}(*) AS n, SUM({expr}) AS total FROM {frm}{self.where(*conds)}"

    def path_joins(self, steps: list[dict], anchor: str, state: list[dict]) -> tuple[str, str]:
        """LEFT JOINs along a path from the table at `anchor`: (the joins, the alias of the last table)."""
        out, prev = "", anchor
        for i, s in enumerate(steps, 1):
            a = f"j{i}"
            on = " AND ".join(f"{self.col(a, s['to'], b)} = {self.col(prev, s['from'], c)}" for c, b in zip(s["columns"], s["to_columns"]))
            k = self.kept(s["to"], a, state)
            out += f" LEFT JOIN {self.table(s['to'])} AS {a} ON {on}" + (f" AND {k}" if k else "")
            prev = a
        return out, prev

    def view_rows(self, table: str, state: list[dict], steps: list[dict] | None = None, columns: list[str] = ()) -> str:
        if steps is None:
            return f"SELECT {self.d.count}(*) AS n FROM {self.table(table)} AS t{self.where(self.kept(table, 't', state))}"
        joins, last = self.path_joins(steps, "t", state)
        end = steps[-1]["to"] if steps else table
        cols = "".join(f", SUM(CASE WHEN {self.col(last, end, c)} IS NULL THEN 1 ELSE 0 END) AS missing_{i}, "
                       f"COUNT(DISTINCT {self.col(last, end, c)}) AS distinct_{i}" for i, c in enumerate(columns, 1))
        return f"SELECT {self.d.count}(*) AS n{cols} FROM {self.table(table)} AS t{joins}{self.where(self.kept(table, 't', state))}"

    def doubling(self, src: dict, target: str, link, state: list[dict], steps: list[dict] | None) -> str:
        """The sum of an amount over the target's view, before (steps None) or after the join path. An amount on a line
        table that points at the target is summed over the lines joined to the target (`link`: (line cols, target cols))."""
        if src["table"] == target:
            expr, frm, conds = self.amount_from(src, state, "t")
            anchor = "t"
        else:
            expr, frm, conds = self.amount_from(src, state, "l")
            on = " AND ".join(f"{self.col('t', target, b)} = {self.col('l', src['table'], a)}" for a, b in zip(*link))
            frm += f" JOIN {self.table(target)} AS t ON {on}"
            conds.append(self.kept(target, "t", state))
            anchor = "t"
        joins = self.path_joins(steps, anchor, state)[0] if steps else ""
        return f"SELECT {self.d.count}(*) AS n, SUM({expr}) AS total FROM {frm}{joins}{self.where(*conds)}"

    def operand(self, op: dict, state: list[dict]) -> tuple[str, str]:
        """(statement, kind) of a count, distinct_count or sum operand of a measure."""
        t = op["table"]
        kept = self.where(self.kept(t, "t", state))
        if op["form"] == "count":
            return f"SELECT {self.d.count}(*) AS n FROM {self.table(t)} AS t{kept}", "count"
        if op["form"] == "distinct_count":
            return f"SELECT COUNT(DISTINCT {self.col('t', t, op['column'])}) AS n FROM {self.table(t)} AS t{kept}", "count"
        return f"SELECT {self.d.count}(*) AS n, SUM({self.col('t', t, op['column'])}) AS total FROM {self.table(t)} AS t{kept}", "sum"


# ------------------------------------------------------------------ the plan's amounts ---------------------------------

def amount_sources(plan) -> list[dict]:
    """Every amount the plan sums, from amounts.py and no query: the quantity × price measures and the amounts a line
    carries (order_amount_measures), and the header amounts (amounts.header_amounts), each summed once over its own
    table. A price is not an amount to add up, so a header column that is a price is left out."""
    out, seen = [], set()
    am = amounts.order_amount_measures(plan)
    for m in am["measures"]:
        r = next((r for r in plan.relationships if r.source == m["table"] and r.target == m["dimension"]
                  and [c.lower() for c in r.source_cols] == [m["via"].lower()]), None)
        if r is None:
            continue
        out.append({"name": m["name"], "table": m["table"], "quantity": m["column"], "dim": m["dimension"], "price": m["price"],
                    "on": list(zip(r.source_cols, r.target_cols)), "measure": True,
                    "said": f"{m['name']}: {m['table']}.{m['column']} × {m['dimension']}.{m['price']}"})
        seen.add((m["table"], m["column"]))
    for o in am["own_amounts"]:
        for c in o["amounts"]:
            if (o["line"], c) not in seen:
                seen.add((o["line"], c))
                out.append({"name": f"{o['line']}.{c}", "table": o["line"], "column": c, "said": f"sum of {o['line']}.{c}"})
    for f in amounts.header_amounts(plan):
        for c in f["amount_columns"]:
            typ = next((x.data_type for x in plan.schema[f["header"]].columns if x.name == c), "decimal")
            if (f["header"], c) in seen or amounts.is_price(c, typ):
                continue
            seen.add((f["header"], c))
            out.append({"name": f"{f['header']}.{c}", "table": f["header"], "column": c,
                        "said": f"sum of {f['header']}.{c}, once per {f['header']} row"})
    return out


# ------------------------------------------------------------------ running ---------------------------------------------

class _Runner:
    """Runs each distinct statement once, under the call's budget, and keeps it as a receipt row."""

    def __init__(self, execute, name: str, no_rows: bool):
        self.execute, self.name, self.no_rows = execute, name, no_rows
        self.done: dict[str, dict] = {}
        self.order: list[str] = []

    def shown(self, sql: str) -> str:
        return sqlite_sql(sql) if self.name == "sqlite" else sql

    def run(self, sql: str, item: str) -> dict:
        if not sql.startswith("SELECT ") or ";" in sql:
            raise NumbersError("only a single SELECT statement is counted")          # never reached: the builders write SELECTs
        if sql in self.done:
            return self.done[sql]
        got = {"item": item, "sql": self.shown(sql), "state": NOT_RUN, "row": None}
        if self.execute is not None:
            if budget.expired():
                got["state"] = NOT_COUNTED
            else:
                try:
                    budget.check(item)
                    rows = list(self.execute(sql))
                    got["row"] = dict(rows[0]) if rows else {}
                    got["state"] = COUNTED
                except budget.TimeUp:
                    got["state"] = NOT_COUNTED
                except Exception as e:                                          # noqa: BLE001 - one failed count is one number
                    got["state"] = f"not counted: {amounts.readable_count_error(e)}"
        self.done[sql] = got
        self.order.append(sql)
        return got

    def value(self, sql: str, item: str, field: str = "n"):
        got = self.run(sql, item)
        return (got["row"] or {}).get(field) if got["state"] == COUNTED else None, got["state"]

    def receipt(self, generated_at: str) -> list[dict]:
        rows = []
        for sql in self.order:
            g = self.done[sql]
            counts = None
            if g["state"] == COUNTED:
                counts = {}
                for k, v in (g["row"] or {}).items():
                    if k == "total":
                        n = _int((g["row"] or {}).get("n")) or 0
                        counts[k] = None if self.no_rows and n < MIN_GROUP else money(v)
                    else:
                        counts[k] = _int(v)
            rows.append({"n": len(rows) + 1, "kind": "change number", "item": g["item"],
                         "sentence": (f"{g['item']}: counted by the statement below." if g["state"] == COUNTED
                                      else f"{g['item']}: {g['state']}."), "sql": g["sql"] if g["state"] == COUNTED else None,
                         "statement": g["sql"], "counts": counts, "state": g["state"], "dialect": self.name,
                         "generated_at": generated_at})
        return rows


def _state_of(*states: str) -> str:
    for s in states:
        if s != COUNTED:
            return s
    return COUNTED


# ------------------------------------------------------------------ numbers of one kind -------------------------------

def _count_pair(r: _Runner, item: str, what: str, before_sql: str, after_sql: str, field: str = "n", **extra) -> dict:
    before, sb = r.value(before_sql, item, field)
    after, sa = (before, sb) if before_sql == after_sql else r.value(after_sql, item, field)
    out = {"item": item, "what": what, **extra, "before": _int(before), "after": _int(after),
           "before_sql": r.shown(before_sql), "after_sql": r.shown(after_sql), "state": _state_of(sb, sa)}
    if out["before"] is not None and out["after"] is not None:
        out["difference"] = out["after"] - out["before"]
    return out


def _sum_side(r: _Runner, sql: str, item: str) -> tuple[Decimal | None, int | None, str, bool]:
    got = r.run(sql, item)
    if got["state"] != COUNTED:
        return None, None, got["state"], False
    n = _int((got["row"] or {}).get("n")) or 0
    total = _dec((got["row"] or {}).get("total"))
    if r.no_rows and n < MIN_GROUP:
        return None, n, COUNTED, True
    return (None if total is None else Decimal(money(total))), n, COUNTED, False


def _sum_pair(r: _Runner, item: str, before_sql: str, after_sql: str, **extra) -> dict:
    b, nb, sb, hb = _sum_side(r, before_sql, item)
    a, na, sa, ha = (b, nb, sb, hb) if before_sql == after_sql else _sum_side(r, after_sql, item)
    out = {"item": item, "what": "sum", **extra, "rows_before": nb, "rows_after": na,
           "before": None if b is None else str(b), "after": None if a is None else str(a),
           "before_sql": r.shown(before_sql), "after_sql": r.shown(after_sql), "state": _state_of(sb, sa)}
    if ha or hb:
        out["hidden"] = HIDDEN
    if a is not None and b is not None:
        diff = a - b
        out["difference"] = str(diff)
        pct = _percent(b, diff)
        if pct is not None:
            out["percent"] = pct
    return out


def _said(n: dict) -> str:
    """One number in words."""
    if n["state"] != COUNTED:
        return f"{n['item']}: {n['state']}."
    if n["what"] == "rows":
        tail = "" if n.get("difference") is None or n["difference"] == 0 else f" ({n['difference']:+d})"
        same = " (untouched)" if n.get("untouched") else ""
        return f"{n['table']}: {_spaced(n['before'])} → {_spaced(n['after'])} rows{tail}{same}."
    if n["what"] == "distinct":
        return f"{n['table']}.{n['column']}: {_spaced(n['before'])} → {_spaced(n['after'])} distinct value(s)."
    if n["what"] == "sum":
        if n.get("hidden"):
            return f"{n['name']}: over {n['rows_before']} → {n['rows_after']} rows; the sum is hidden (fewer than {MIN_GROUP} rows)."
        tail = ""
        if n.get("difference") not in (None, "0.00"):
            tail = f" ({_spaced(n['difference'])}" + (f", {n['percent'].lstrip('-')} %" if n.get("percent") else "") + ")"
        same = " (untouched)" if n.get("untouched") else (" (equal)" if n.get("equal") else "")
        return f"{n['name']}: {_spaced(n['before'])} → {_spaced(n['after'])}{tail}{same}."
    if n["what"] == "missing":
        return f"{n['column']}: no value on {n['after']} of {n['of']} rows."
    if n["what"] == "distinct_values":
        return f"{n['column']}: {n['after']} distinct value(s)."
    if n["what"] == "measure":
        if n.get("hidden"):
            return f"{n['name']}: hidden (a sum over fewer than {MIN_GROUP} rows)."
        src = f" ({_spaced(n['on_source'])} on the source as it is)" if n.get("on_source") is not None else ""
        return f"{n['name']}: {_spaced(n['value'])}{src}."
    return f"{n['item']}."


# ------------------------------------------------------------------ per change type -----------------------------------

def _refs(plan, table: str) -> list[str]:
    """The single-column references of a table, in the plan's order, without repeats."""
    out = []
    for r in plan.relationships:
        if r.source == table and len(r.source_cols) == 1 and r.source_cols[0] not in out:
            out.append(r.source_cols[0])
    return out


def _filter_numbers(q: _Sql, r: _Runner, entry: dict, before: list[dict], after: list[dict], sources: list[dict]) -> list[dict]:
    c, plan = entry["change"], q.plan
    touched = [c["table"]] + [x["table"] for x in entry.get("resolved", {}).get("cascade", []) if x["table"] in plan.schema]
    out = []
    for t in touched:
        refs = _refs(plan, t)
        b, a = q.rows(t, before, refs), q.rows(t, after, refs)
        out.append(_count_pair(r, f"rows:{t}", "rows", b, a, table=t))
        for i, col in enumerate(refs, 1):
            out.append(_count_pair(r, f"distinct:{t}.{col}", "distinct", b, a, field=f"d{i}", table=t, column=col))
    for s in sources:
        hit = s["table"] in touched or s.get("dim") in touched
        b, a = q.total(s, before), q.total(s, after)
        out.append(_sum_pair(r, f"sum:{s['name']}", b, a if hit else b, name=s["name"], table=s["table"],
                             **({} if hit else {"untouched": True})))
    # the tables outside the cascade that point at a table that loses rows keep every row: counted once
    outside = sorted({x.source for x in plan.relationships if x.target in touched and x.source not in touched and x.source != x.target})
    amount_tables = [s["table"] for s in sources if s["table"] not in touched and s.get("dim") not in touched]
    for t in [*outside, *[t for t in dict.fromkeys(amount_tables) if t not in outside]]:
        sql = q.rows(t, before)
        out.append(_count_pair(r, f"rows:{t}", "rows", sql, sql, table=t, untouched=True))
    return out


def _target_links(plan, target: str) -> dict:
    """line table -> (its columns, the target's columns) for each table that points at `target` many-to-one."""
    out = {}
    for x in plan.relationships:
        if x.target == target and x.source != target and x.source not in out:
            out[x.source] = (list(x.source_cols), list(x.target_cols))
    return out


def _join_numbers(q: _Sql, r: _Runner, target: str, steps: list[dict], columns: list[str], state: list[dict],
                  sources: list[dict]) -> tuple[list[dict], list[dict], bool | None]:
    """(numbers, doubling checks, doubled) of a join path from `target`."""
    end = steps[-1]["to"] if steps else target
    before, after = q.view_rows(target, state), q.view_rows(target, state, steps, columns)
    rows = _count_pair(r, f"view_rows:{target}", "rows", before, after, table=target, view=True)
    rows["equal"] = rows["state"] == COUNTED and rows["before"] == rows["after"]
    numbers = [rows]
    for i, col in enumerate(columns, 1):
        name = f"{end}.{col}"
        m, sm = r.value(after, f"view_rows:{target}", f"missing_{i}")
        dv, sd = r.value(after, f"view_rows:{target}", f"distinct_{i}")
        numbers.append({"item": f"missing:{name}", "what": "missing", "table": target, "column": name, "after": _int(m),
                        "of": rows["after"], "after_sql": r.shown(after), "state": sm})
        numbers.append({"item": f"distinct_values:{name}", "what": "distinct_values", "table": target, "column": name,
                        "after": _int(dv), "after_sql": r.shown(after), "state": sd})
    checks = [{**rows, "item": f"doubling:rows:{target}"}]
    links = _target_links(q.plan, target)
    for s in sources:
        if s["table"] != target and s["table"] not in links:
            continue
        link = links.get(s["table"])
        b = q.doubling(s, target, link, state, None)
        a = q.doubling(s, target, link, state, steps)
        n = _sum_pair(r, f"doubling:{s['name']}", b, a, name=s["name"], table=s["table"])
        n["equal"] = n["state"] == COUNTED and n["before"] == n["after"] and n["rows_before"] == n["rows_after"]
        checks.append(n)
    counted = [x for x in checks if x["state"] == COUNTED]
    doubled = None if not counted else any(not x["equal"] for x in counted)
    return numbers, checks, doubled


def _steps_from_via(plan, table: str, via: list) -> list[dict]:
    """The join steps of a via as written (also one validate denies): each link's columns must be the plan's."""
    node, out = table, []
    for link in via or []:
        try:
            f, t = link["from"], link["to"]
            ft, tt, fc, tc = f["table"], t["table"], list(f["columns"]), list(t["columns"])
        except (KeyError, TypeError) as e:
            raise NumbersError("a link of via is {from: {table, columns}, to: {table, columns}}") from e
        for name, cols in ((ft, fc), (tt, tc)):
            if name not in plan.schema or any(c not in plan.schema[name].column_names for c in cols):
                raise NumbersError(f"{name}.{'+'.join(map(str, cols))} is not in the plan")
        if len(fc) != len(tc) or not fc:
            raise NumbersError("a link joins as many columns on each side")
        if ft == node:
            out.append({"from": node, "to": tt, "columns": fc, "to_columns": tc})
            node = tt
        elif tt == node:
            out.append({"from": node, "to": ft, "columns": tc, "to_columns": fc})
            node = ft
        else:
            raise NumbersError(f"the link {ft} -> {tt} does not continue from {node}")
    return out


def _operand_value(q: _Sql, r: _Runner, op: dict, state: list[dict], sources: dict, defined: dict, item: str, seen=()) -> dict:
    """{value (Decimal or int), hidden, state, sql: [statements]} of a measure operand."""
    if "measure" in op:
        name = op["measure"]
        if name.casefold() in sources:
            sql = q.total(sources[name.casefold()], state)
            v, n, st, hid = _sum_side(r, sql, item)
            return {"value": v, "hidden": hid, "state": st, "sql": [r.shown(sql)], "kind": "sum"}
        inner = defined.get(name.casefold())
        if inner is None or name.casefold() in seen:
            return {"value": None, "hidden": False, "state": f"not counted: the form of {name} is not known here", "sql": []}
        return _operand_value(q, r, inner, state, sources, defined, item, (*seen, name.casefold()))
    if op.get("form") == "ratio":
        n = _operand_value(q, r, op["numerator"], state, sources, defined, item, seen)
        d = _operand_value(q, r, op["denominator"], state, sources, defined, item, seen)
        st = _state_of(n["state"], d["state"])
        value = None
        if st == COUNTED and not (n["hidden"] or d["hidden"]) and n["value"] is not None and d["value"]:
            value = Decimal(n["value"]) / Decimal(d["value"])                # DIVIDE: BLANK where the denominator is 0
        return {"value": value, "hidden": n["hidden"] or d["hidden"], "state": st, "sql": n["sql"] + d["sql"], "kind": "ratio"}
    sql, kind = q.operand(op, state)
    if kind == "sum":
        v, n, st, hid = _sum_side(r, sql, item)
        return {"value": v, "hidden": hid, "state": st, "sql": [r.shown(sql)], "kind": "sum"}
    v, st = r.value(sql, item)
    return {"value": _int(v), "hidden": False, "state": st, "sql": [r.shown(sql)], "kind": "count"}


def _shown_value(got: dict):
    v = got["value"]
    if v is None:
        return None
    if got["kind"] == "count":
        return int(v)
    return str(Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _measure_numbers(q: _Sql, r: _Runner, entry: dict, state: list[dict], sources: list[dict], defined: dict) -> list[dict]:
    c = entry["change"]
    by = {s["name"].casefold(): s for s in sources if s.get("measure")}
    name = c["name"]
    got = _operand_value(q, r, c["measure"], state, by, defined, f"measure:{name}")
    n = {"item": f"measure:{name}", "what": "measure", "name": name, "value": _shown_value(got), "sql": got["sql"],
         "state": got["state"]}
    if got["hidden"]:
        n["hidden"], n["value"] = HIDDEN, None
    if state:
        raw = _operand_value(q, r, c["measure"], [], by, defined, f"measure:{name} on the source")
        n["on_source"] = None if raw["hidden"] else _shown_value(raw)
        n["on_source_sql"] = raw["sql"]
        n["state"] = _state_of(n["state"], raw["state"])
    out = [n]
    for s in sources:                                    # the other measures: an add_measure changes no row
        if not s.get("measure"):
            continue
        sql = q.total(s, state)
        x = _sum_pair(r, f"sum:{s['name']}", sql, sql, name=s["name"], table=s["table"], untouched=True)
        x["unchanged"] = x["state"] == COUNTED
        out.append(x)
    return out


# ------------------------------------------------------------------ the calls ------------------------------------------

def _ok(applied) -> list[dict]:
    if not isinstance(applied, dict) or applied.get("result") != "ok":
        raise NumbersError("count takes changes.apply's ok answer"
                           + (f"; this list was not applied ({applied.get('result')})" if isinstance(applied, dict) else ""))
    return list(applied.get("changes") or [])


def _answer(r: _Runner, out_changes: list[dict], generated_at, extra: dict) -> dict:
    from .receipt import _now
    at = _now(generated_at)
    rows = r.receipt(at)
    states = [x["state"] for x in rows]
    counted = sum(1 for s in states if s == COUNTED)
    result = "counted" if counted == len(states) else ("not run" if all(s == NOT_RUN for s in states) else
                                                       ("not counted" if counted == 0 else "partly counted"))
    out = {"result": result, **extra, "dialect": r.name, "changes": out_changes,
           "statements": {"counted": counted, "not_counted": len(states) - counted,
                          "not_counted_time": sum(1 for s in states if s == NOT_COUNTED)},
           "receipt": rows, "generated_at": at}
    left = budget.ran_out()
    if left is not None:
        out["budget"] = left
    if r.no_rows:
        out["row_values"] = f"KRUSGRAPH_NO_ROW_VALUES: a sum over fewer than {MIN_GROUP} rows is hidden; counts are shown"
    return out


def _no_rows(no_row_values) -> bool:
    if no_row_values is not None:
        return bool(no_row_values)
    from .switches import no_row_values as on
    return on()


def count(applied: dict, plan, execute, *, dialect=None, seconds: float | None = None, clock=None,
          no_row_values: bool | None = None, generated_at=None) -> dict:
    """The numbers of every change in `applied` (changes.apply's ok answer), counted with `execute(sql) -> rows` under
    one time budget (`seconds`, default budget.call_seconds(); `clock` for tests). `dialect`: None (the connection's),
    "tsql", "sqlite" or a dialects.Dialect. `no_row_values`: None reads KRUSGRAPH_NO_ROW_VALUES.

    {"result": "counted" | "partly counted" | "not counted" | "not run", "plan", "dialect",
     "changes": [{"id", "type", "position", "numbers": [...], "said": [...], ("doubling", "doubled")}],
     "statements": {counted, not_counted, not_counted_time}, "receipt": [one row per statement], "generated_at"}

    A number: {"item", "what", "before", "after", ("difference", "percent"), "before_sql", "after_sql", "state"}; a sum
    has its rows on each side and amounts as text with two decimals; an add_measure's number has "value", "sql" (its
    statements) and, after a filter, "on_source"."""
    entries = _ok(applied)
    d, name = _dialect(dialect, execute)
    q, r = _Sql(plan, d), _Runner(execute, name, _no_rows(no_row_values))
    sources = amount_sources(plan)
    out, state, defined = [], [], {}
    with budget.call(seconds, clock):
        for e in entries:
            row = {"id": e["id"], "type": e["type"], "position": e.get("position")}
            if e["type"] == "filter_rows":
                after = [*state, e]
                row["numbers"] = _filter_numbers(q, r, e, list(state), after, sources)
                state = after
            elif e["type"] == "add_column":
                c = e["change"]
                steps = e.get("resolved", {}).get("steps") or _steps_from_via(plan, c["table"], c["via"])
                nums, checks, doubled = _join_numbers(q, r, c["table"], steps, list(c["columns"]), list(state), sources)
                row.update(numbers=nums, doubling=checks, doubled=doubled)
            elif e["type"] == "add_measure":
                row["numbers"] = _measure_numbers(q, r, e, list(state), sources, defined)
                defined[e["change"]["name"].casefold()] = e["change"]["measure"]
            else:
                row["numbers"] = []
                row["note"] = "An add_link changes no row; validate_plan counts the link against the rows."
            row["said"] = [_said(n) for n in row["numbers"]]
            if row.get("doubled"):
                row["said"].append("The join repeats rows: a number above differs after it (doubled).")
            out.append(row)
        return _answer(r, out, generated_at, {"plan": _changes.plan_mark(plan)})


def count_path(change: dict, plan, execute, *, applied: dict | None = None, dialect=None, seconds: float | None = None,
               clock=None, no_row_values: bool | None = None, generated_at=None) -> dict:
    """An add_column's join path counted as written, after the filters of `applied` (optional): the rows of the
    table's view and the amounts that reach it, before and after the join. For a change changes.validate denied as
    fan_out this shows the repetition in numbers (orders → customers → addresses: 60 rows become 103). The change is
    {"table", "columns", "via"} as the client sent it; every name must be in the plan."""
    if not isinstance(change, dict) or not isinstance(change.get("table"), str) or not isinstance(change.get("via"), list):
        raise NumbersError("count_path takes an add_column with table, columns and via")
    if change["table"] not in plan.schema:
        raise NumbersError(f"{change['table']!r} is not a table of the plan")
    steps = _steps_from_via(plan, change["table"], change["via"])
    end = steps[-1]["to"] if steps else change["table"]
    columns = [c for c in (change.get("columns") or []) if isinstance(c, str)]
    if any(c not in plan.schema[end].column_names for c in columns):
        raise NumbersError(f"a column is not in {end}")
    state = [e for e in (_ok(applied) if applied is not None else []) if e["type"] == "filter_rows"]
    d, name = _dialect(dialect, execute)
    q, r = _Sql(plan, d), _Runner(execute, name, _no_rows(no_row_values))
    with budget.call(seconds, clock):
        nums, checks, doubled = _join_numbers(q, r, change["table"], steps, columns, state, amount_sources(plan))
        said = [_said(n) for n in nums] + [_said(n) for n in checks[1:]]
        if doubled:
            said.append("The join repeats rows: the rows and the amounts differ after it (doubled).")
        row = {"type": "add_column", "table": change["table"], "path": [change["table"], *[s["to"] for s in steps]],
               "numbers": nums, "doubling": checks, "doubled": doubled, "said": said}
        return _answer(r, [row], generated_at, {"plan": _changes.plan_mark(plan)})


def statements(applied: dict, plan, dialect="tsql") -> list[dict]:
    """The statements count would run, in order, with nothing run: [{"n", "item", "sql"}]."""
    got = count(applied, plan, None, dialect=dialect, no_row_values=False, generated_at="1970-01-01T00:00:00Z")
    return [{"n": x["n"], "item": x["item"], "sql": x["statement"]} for x in got["receipt"]]


def markdown(answer: dict, source: str = "") -> str:
    """The answer's receipt as krusgraph-receipt.md: one section per statement with its counts (receipt.markdown)."""
    from .receipt import markdown as _md
    return _md(answer["receipt"], source)
