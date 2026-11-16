"""Reconciling KPIs after a migration from Qlik (Q2): the numbers the customer exported from the Qlik app against the
same KPIs computed on the migrated tables.

`draft(read, kpis)` writes, per KPI, one T-SQL statement for the lakehouse's SQL analytics endpoint. The statement
holds the exported Qlik values, computes the KPI on the migrated tables at the same grain, and returns the comparison:
one row per grain value with `qlik_value`, `new_value`, `difference` and `status`. This module runs nothing. When the
statement's rows are given back (`results`), the same comparison is filled in here, by the same rule.

What a KPI needs: a name, a Qlik expression, the exported value or values, and the fields the values are grouped by.
The export must be made with no selections in the app: a set expression that clears a selection, `{1}` and `{$}` are
then the same set, and the statement treats them so.

What gets SQL: Sum, Min, Max, Avg, Count and Count(DISTINCT) of one field or of an expression over one table's rows;
`+ - * /`, If, Abs and brackets around them; set modifiers that set a field to literal values (a CASE inside the
aggregation). A grouping field or a set field of another table is reached through the plan's relationships, from the
many side to the one side, with LEFT JOINs: a row without a match is grouped under NULL, as Qlik shows it under `-`.
Everything else is listed with its reason and gets no SQL: nothing is guessed.

The status of a row is `equal` (within the tolerance given, 0.005 by default: exported numbers are rounded),
`different`, `only in Qlik` or `only on the migrated tables`. It is never "probably": a difference is listed as open,
with the checks that may explain it; a reason is the person's to confirm with a count. Tested on synthetic rows only
(tests/test_q2_qlik_tools.py). The rules about Qlik are **Unverified** (see expr.py).
"""
from __future__ import annotations

from ..dialects import TSQL
from . import expr as _expr
from .expr import Unsupported
from .measures import field_index, set_variables
from .model import map_associations

MAX_KPIS, MAX_ROWS = 50, 2000
DEFAULT_TOLERANCE = 0.005
CANDIDATES = [
    "Rows without a match on a relationship: Qlik shows them under `-`, the statement groups them under NULL, and a "
    "Power BI model puts them on the blank row. The total is the same; the groups differ.",
    "A synthetic key that became one relationship: rows that matched on the link field but differed on the other shared "
    "field did not associate in Qlik and do relate now (the plan lists each with its count once the tables are landed).",
    "Upper and lower case: Qlik keeps `ABC` and `abc` apart; a collation without case sensitivity groups them together.",
    "Null and empty text: Qlik's Count(F) leaves out null; an empty string is a value in SQL.",
    "Rounding: the exported number carries the app's number format; raise or lower the tolerance to what was exported.",
    "The load itself: a WHERE, a Concatenate or a join in the script that the migrated table does not repeat (the plan "
    "lists the steps per table).",
    "Dates and periods: a grouping field computed in the script (a month, a year) must be computed the same way in the "
    "migrated table.",
]


def _lit(v) -> str:
    if v is None:
        return "NULL"
    return "N'" + str(v).replace("'", "''") + "'"


def _number(v, what: str) -> float | None:
    if v is None or v == "" or v == "-":
        return None
    if isinstance(v, bool):
        raise ValueError(f"{what} is not a number")
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip().replace(" ", "").replace(" ", ""))
    except ValueError:
        raise ValueError(f"{what} is not a number ({v!r}): export the values without thousand separators and with a "
                         "point as the decimal sign") from None


class _Sql:
    """One KPI's expression as T-SQL over a base table and the tables reached from it."""

    def __init__(self, index: dict, rels: list[dict], dialect):
        self.index, self.rels, self.d = index, rels, dialect
        self.base: str | None = None
        self.alias: dict[str, str] = {}
        self.joins: list[dict] = []

    def base_column(self, field: str) -> str:
        """A field read row by row inside an aggregation: it must be in one table, and all such fields in the same."""
        hits = self.index.get(field)
        if not hits:
            raise Unsupported(f"the field {field} is not in the load script that was given")
        tables = [t for t, _ in hits]
        if self.base is None:
            if len(hits) > 1:
                raise Unsupported(f"the field {field} is in {len(hits)} tables ({', '.join(tables)}): a person says which "
                                  "table's rows the KPI is computed over")
            self.base = tables[0]
            self.alias[self.base] = "b"
        if self.base not in tables:
            raise Unsupported(f"the aggregation reads {field} of {tables[0]} and fields of {self.base} row by row: a KPI "
                              "over two tables' rows is a person's decision")
        return f"b.{self.d.quote(dict(hits)[self.base])}"

    def path(self, target: str) -> list[dict] | None:
        prev, queue = {self.base: None}, [self.base]
        while queue:
            x = queue.pop(0)
            if x == target:
                break
            for r in self.rels:
                if r["source"] == x and r["target"] not in prev:
                    prev[r["target"]] = r
                    queue.append(r["target"])
        if target not in prev:
            return None
        out, x = [], target
        while prev[x] is not None:
            out.append(prev[x])
            x = prev[x]["source"]
        return out[::-1]

    def reached_column(self, field: str, what: str) -> str:
        """A grouping field or a set field: the base table's own column, else the one table that holds it and is
        reached from the base table through relationships, many side to one side."""
        hits = self.index.get(field)
        if not hits:
            raise Unsupported(f"the {what} {field} is not in the load script that was given")
        by_table = dict(hits)
        if self.base in by_table:
            return f"b.{self.d.quote(by_table[self.base])}"
        reachable = [(t, self.path(t)) for t in by_table]
        reachable = [(t, p) for t, p in reachable if p is not None]
        if not reachable:
            raise Unsupported(f"the {what} {field} is in {', '.join(by_table)}, and the plan has no relationship path "
                              f"from {self.base} to it (many side to one side): a person says how the rows relate")
        if len(reachable) > 1:
            raise Unsupported(f"the {what} {field} is in {len(reachable)} tables reached from {self.base} "
                              f"({', '.join(t for t, _ in reachable)}): a person says which")
        table, steps = reachable[0]
        for r in steps:
            if r["target"] not in self.alias:
                self.alias[r["target"]] = f"t{len(self.alias)}"
                self.joins.append(r)
        return f"{self.alias[table]}.{self.d.quote(by_table[table])}"

    def row(self, node) -> str:
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "str":
            return _lit(node[1])
        if kind == "field":
            return self.base_column(node[1])
        if kind == "paren":
            return f"({self.row(node[1])})"
        if kind == "neg":
            return f"-{self.row(node[1])}"
        if kind == "not":
            return f"NOT ({self.row(node[1])})"
        if kind == "bin":
            return self.binary(node, self.row)
        if kind == "call":
            return self.function(node, self.row)
        raise Unsupported("an aggregation inside an aggregation: in Qlik that needs Aggr(), which gets no SQL here")

    def binary(self, node, sub) -> str:
        _, op, a, b = node
        if op == "/":
            return f"CAST({sub(a)} AS FLOAT) / NULLIF({sub(b)}, 0)"
        if op == "&":
            return f"CONCAT({sub(a)}, {sub(b)})"
        return f"{sub(a)} {op.upper() if op in ('and', 'or') else op} {sub(b)}"

    def function(self, node, sub) -> str:
        _, name, args = node
        if name == "if" and len(args) in (2, 3):
            other = f" ELSE {sub(args[2])}" if len(args) == 3 else ""
            return f"CASE WHEN {sub(args[0])} THEN {sub(args[1])}{other} END"
        if name == "abs" and len(args) == 1:
            return f"ABS({sub(args[0])})"
        if name == "num" and args:
            return sub(args[0])
        raise Unsupported(f"the function {name}() has no rule yet")

    def top(self, node) -> str:
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "paren":
            return f"({self.top(node[1])})"
        if kind == "neg":
            return f"-{self.top(node[1])}"
        if kind == "bin" and node[1] in ("+", "-", "*", "/"):
            return self.binary(node, self.top)
        if kind == "call":
            return self.function(node, self.top)
        if kind == "agg":
            return self.aggregation(node[1])
        if kind == "field":
            raise Unsupported(f"{node[1]} outside an aggregation: if it is another measure, give that measure's expression "
                              "in its place")
        raise Unsupported("a comparison or text outside an aggregation gets no SQL here")

    def aggregation(self, a: dict) -> str:
        if a["total"] is not None:
            raise Unsupported("TOTAL: export and compare the part and the total as two KPIs instead")
        body = self.row(a["arg"])
        when = []
        for f, values in (a["set"] or {}).get("modifiers", []):
            if values is None:
                continue                                    # a cleared selection: the export was made with none
            if not values:
                raise Unsupported(f"the set modifier {f} = {{}} selects no value")
            col = self.reached_column(f, "set field")
            when.append(f"CAST({col} AS NVARCHAR(4000)) IN ({', '.join(_lit(v) for _, v in values)})")
        if when:
            body = f"CASE WHEN {' AND '.join(when)} THEN {body} END"
        fn = a["fn"]
        if fn == "count":
            return f"COUNT({'DISTINCT ' if a['distinct'] else ''}{body})"
        if a["distinct"]:
            raise Unsupported(f"{fn.capitalize()}(DISTINCT ...) has no rule yet")
        if fn == "avg":
            return f"AVG(CAST({body} AS FLOAT))"
        return f"{fn.upper()}({body})"


def _statement(kpi: dict, tree, index: dict, rels: list[dict], schema: str, tolerance: float, dialect) -> dict:
    s = _Sql(index, rels, dialect)
    value = s.top(tree)
    if s.base is None:
        raise Unsupported("no aggregation of a field in it")
    grain = kpi["by"]
    cols = [s.reached_column(g, "grouping field") for g in grain]
    q = dialect.quote
    gnames = [q(f"g{i + 1}") for i in range(len(grain))]
    rows = kpi["rows"]
    qlik_rows = "\n    UNION ALL ".join(
        "SELECT " + ", ".join([("CAST(NULL AS NVARCHAR(4000))" if r["by"][g] is None else _lit(r["by"][g])) for g in grain]
                              + [("CAST(NULL AS FLOAT)" if r["value"] is None else repr(r["value"])), "1"])
        for r in rows)
    joins = "".join(
        f"\n    LEFT JOIN {dialect.table(schema, r['target'])} AS {s.alias[r['target']]} ON "
        + " AND ".join(f"{s.alias[r['source']]}.{q(a)} = {s.alias[r['target']]}.{q(b)}" for a, b in zip(r["source_cols"], r["target_cols"]))
        for r in s.joins)
    select = ", ".join([f"CAST({c} AS NVARCHAR(4000)) AS {g}" for c, g in zip(cols, gnames)] + [f"{value} AS {q('value')}"])
    group = ("\n    GROUP BY " + ", ".join(cols)) if cols else ""
    on = " AND ".join(f"(q.{g} = n.{g} OR (q.{g} IS NULL AND n.{g} IS NULL))" for g in gnames) or "1 = 1"
    shown = ", ".join(f"COALESCE(q.{g}, n.{g}) AS {q(name)}" for g, name in zip(gnames, grain))
    tol = repr(float(tolerance))
    sql = (f"WITH qlik ({', '.join(gnames + [q('value'), q('present')])}) AS (\n    "
           + qlik_rows + "\n),\n"
           f"migrated ({', '.join(gnames + [q('value'), q('present')])}) AS (\n    SELECT {select}, 1\n"
           f"    FROM {dialect.table(schema, s.base)} AS b{joins}{group}\n)\n"
           f"SELECT {shown + ', ' if shown else ''}q.{q('value')} AS qlik_value, n.{q('value')} AS new_value, "
           f"n.{q('value')} - q.{q('value')} AS difference,\n"
           f"    CASE WHEN n.{q('present')} IS NULL THEN 'only in Qlik' WHEN q.{q('present')} IS NULL THEN 'only on the migrated tables'\n"
           f"         WHEN q.{q('value')} IS NULL AND n.{q('value')} IS NULL THEN 'equal'\n"
           f"         WHEN ABS(n.{q('value')} - q.{q('value')}) <= {tol} THEN 'equal' ELSE 'different' END AS status\n"
           f"FROM qlik AS q FULL OUTER JOIN migrated AS n ON {on}"
           + (f"\nORDER BY {', '.join(str(i + 1) for i in range(len(grain)))}" if grain else ""))
    return {"sql": sql, "computed_over": s.base,
            "joins": [f"{r['source']}.{'+'.join(r['source_cols'])} -> {r['target']}" for r in s.joins]}


def read_kpis(kpis) -> list[dict]:
    """The KPIs as [{name, expression, by, rows: [{by: {field: value}, value}]}]. A KPI is given as {name, expression,
    value} for one number, or {name, expression, by: [fields], values: [{field: ..., value: ...}]} per grain."""
    if not isinstance(kpis, list) or not kpis:
        raise ValueError("kpis must be a list of {name, expression, value} or {name, expression, by, values}")
    if len(kpis) > MAX_KPIS:
        raise ValueError(f"{len(kpis)} KPIs were given; at most {MAX_KPIS} are read in one call")
    out = []
    for i, k in enumerate(kpis, 1):
        if not isinstance(k, dict) or not isinstance(k.get("name"), str) or not isinstance(k.get("expression"), str):
            raise ValueError(f"KPI {i} needs a name and an expression")
        by = k.get("by") or []
        if isinstance(by, str):
            by = [by]
        if not isinstance(by, list) or not all(isinstance(g, str) and g for g in by):
            raise ValueError(f"KPI {k['name']}: by must be a list of field names")
        if "values" in k:
            vals = k["values"]
            if not isinstance(vals, list) or not vals:
                raise ValueError(f"KPI {k['name']}: values must be a list of rows")
            if len(vals) > MAX_ROWS:
                raise ValueError(f"KPI {k['name']}: {len(vals)} rows were given; at most {MAX_ROWS} per KPI")
            rows = []
            for n, v in enumerate(vals, 1):
                if not isinstance(v, dict) or "value" not in v:
                    raise ValueError(f"KPI {k['name']}, row {n}: a row is an object with the grouping fields and `value`")
                missing = [g for g in by if g not in v]
                if missing:
                    raise ValueError(f"KPI {k['name']}, row {n}: no value for {', '.join(missing)}")
                rows.append({"by": {g: (None if v[g] in (None, "-") else str(v[g])) for g in by},
                             "value": _number(v["value"], f"KPI {k['name']}, row {n}: value")})
        elif "value" in k:
            if by:
                raise ValueError(f"KPI {k['name']}: with by, give values (one row per grain value), not value")
            rows = [{"by": {}, "value": _number(k["value"], f"KPI {k['name']}: value")}]
        else:
            raise ValueError(f"KPI {k['name']} has no exported value: give value, or by and values")
        seen = set()
        for r in rows:
            key = tuple(r["by"][g] for g in by)
            if key in seen:
                raise ValueError(f"KPI {k['name']}: the grain value {' / '.join(str(x) for x in key) or '(total)'} is given twice")
            seen.add(key)
        out.append({"name": k["name"].strip(), "expression": k["expression"].strip(), "by": list(by), "rows": rows})
    return out


def _compare(kpi: dict, result_rows: list, tolerance: float) -> list[dict]:
    """The comparison rows from the statement's rows given back, or from rows of {grouping fields, new_value}."""
    by = kpi["by"]
    new: dict[tuple, float | None] = {}
    for n, r in enumerate(result_rows, 1):
        if not isinstance(r, dict):
            raise ValueError(f"results for {kpi['name']}, row {n}: a row is an object")
        if r.get("status") == "only in Qlik":
            continue
        key = tuple(None if r.get(g) in (None, "-") else str(r.get(g)) for g in by)
        new[key] = _number(r.get("new_value", r.get("value")), f"results for {kpi['name']}, row {n}: new_value")
    out, seen = [], set()
    for r in kpi["rows"]:
        key = tuple(r["by"][g] for g in by)
        seen.add(key)
        row = {**r["by"], "qlik_value": r["value"]}
        if key not in new:
            row.update({"new_value": None, "difference": None, "status": "only in Qlik"})
        else:
            v = new[key]
            both = v is not None and r["value"] is not None
            diff = round(v - r["value"], 10) if both else None
            same = (v is None and r["value"] is None) or (both and abs(diff) <= tolerance)
            row.update({"new_value": v, "difference": diff, "status": "equal" if same else "different"})
        out.append(row)
    for key, v in new.items():
        if key not in seen:
            out.append({**dict(zip(by, key)), "qlik_value": None, "new_value": v, "difference": None,
                        "status": "only on the migrated tables"})
    return out


def draft(read: dict, kpis, schema: str = "dbo", tolerance: float = DEFAULT_TOLERANCE, results: dict | None = None,
          tables: dict[str, str] | None = None, confirmed: list[dict] | None = None, dialect=TSQL) -> dict:
    """Per KPI the statement and the comparison table. `read` is `read_script`'s answer; `schema` is where the migrated
    tables are; `confirmed` replaces the relationships taken from the script's associations (the plan's `confirmed`
    list); `results` maps a KPI's name to the rows its statement returned, and fills the comparison in."""
    if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool) or tolerance < 0:
        raise ValueError("tolerance must be a number that is zero or more")
    rows = read_kpis(kpis)
    if results is not None and not isinstance(results, dict):
        raise ValueError("results must map a KPI's name to the rows its statement returned")
    index = field_index(read, tables)
    variables = set_variables(read)
    if confirmed is None:
        mapping = map_associations(read, tables=tables)
        rels = [r for r in mapping["relationships"] if r["in_plan"] == "relationship"]
        rel_source = "the script's associations, by name: nothing was counted"
    else:
        rels = [{"source": r["source"], "source_cols": list(r["source_cols"]), "target": r["target"],
                 "target_cols": list(r["target_cols"])} for r in confirmed]
        rel_source = "the relationships given"
    out = []
    totals = {"kpis": len(rows), "with_sql": 0, "without_sql": 0, "rows": 0, "equal": 0, "different": 0,
              "only_in_qlik": 0, "only_on_the_migrated_tables": 0, "to_compute": 0}
    for k in rows:
        item = {"name": k["name"], "qlik": k["expression"], "by": k["by"]}
        try:
            text, used = _expr.expand(k["expression"], variables)
            tree = _expr.parse(text)
            item.update(_statement(k, tree, index, rels, schema, tolerance, dialect))
            if used:
                item["expanded"] = [f"$({v}) from its SET in the script" for v in dict.fromkeys(used)]
            totals["with_sql"] += 1
        except Unsupported as e:
            item["sql"] = None
            item["why_no_sql"] = str(e)
            totals["without_sql"] += 1
        given = (results or {}).get(k["name"])
        if given is not None:
            if not isinstance(given, list):
                raise ValueError(f"results for {k['name']} must be a list of rows")
            table = _compare(k, given, tolerance)
        else:
            table = [{**r["by"], "qlik_value": r["value"], "new_value": None, "difference": None,
                      "status": "to compute: run the statement" if item["sql"] else "open: no statement was written"}
                     for r in k["rows"]]
        for r in table:
            totals["rows"] += 1
            key = {"equal": "equal", "different": "different", "only in Qlik": "only_in_qlik",
                   "only on the migrated tables": "only_on_the_migrated_tables"}.get(r["status"], "to_compute")
            totals[key] += 1
        item["comparison"] = {"columns": k["by"] + ["qlik_value", "new_value", "difference", "status"], "rows": table}
        open_rows = [r for r in table if r["status"] in ("different", "only in Qlik", "only on the migrated tables")]
        if open_rows:
            item["open"] = (f"{len(open_rows)} row(s) differ. No reason is named: a reason counts only when a count "
                            "reproduces the difference exactly (see checks_that_may_explain_a_difference)")
        out.append(item)
    return {"kind": "qlik_reconcile_draft", "schema": schema, "tolerance": tolerance, "relationships_from": rel_source,
            "totals": totals, "kpis": out,
            "export_rule": "export each KPI from the Qlik app with no selections, one row per grain value, numbers with a "
                           "point as the decimal sign and no thousand separators",
            "checks_that_may_explain_a_difference": CANDIDATES}
