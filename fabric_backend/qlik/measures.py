"""Qlik master measures and chart expressions as DAX drafts, where a fixed rule carries them over (Q2).

Every expression gets one of three labels, as docs/QLIK-MIGRATION-PRODUCT.md section 2.4 sets out:

- `translated`: every part has a rule and nothing depends on where the measure is used;
- `suggested`: a rule gives DAX, and the answer says in which case it gives another number than Qlik;
- `not_translated`: no rule; the reason is said, and a person decides.

No share of anything is promised: the counts per label are counted on the expressions given, and nothing is known
about any other app. The DAX is a draft that has not been run: this module evaluates neither Qlik nor DAX. The rules
about Qlik are **Unverified** (see expr.py); the DAX functions used are SUM, MIN, MAX, AVERAGE, COUNTA,
DISTINCTCOUNTNOBLANK, the X iterators, CALCULATE, REMOVEFILTERS, ALLSELECTED, VALUES, DIVIDE and IF.

The rules:

| Qlik | DAX | Label |
|---|---|---|
| `Sum(F)`, `Min(F)`, `Max(F)`, `Avg(F)` of one field | `SUM('T'[F])`, `MIN`, `MAX`, `AVERAGE` | translated |
| `Count(F)` | `COUNTA('T'[F])`: values that are not blank | translated |
| `Count(DISTINCT F)` | `DISTINCTCOUNTNOBLANK('T'[F])` | translated |
| `Sum(a * b)` with every field in one table | `SUMX('T', 'T'[a] * 'T'[b])` (`AVERAGEX`, `MINX`, `MAXX`) | translated |
| `a / b` | `DIVIDE(a, b)`: blank when b is zero, as Qlik's null | translated |
| `If(c, a, b)`, `Abs`, brackets, `+ - *`, `&`, comparisons, `and`, `or`, `not` | the same in DAX | translated |
| the name of another measure in the list | `[Measure]` | translated |
| `$(v)` where the script SETs `v` | the variable's text, expanded | translated, and it says so |
| `{$}` | nothing | translated |
| `{<F = {values}>}` | `CALCULATE(..., 'T'[F] IN {values})` | suggested |
| `{<F = >}` | `CALCULATE(..., REMOVEFILTERS('T'[F]))` | suggested |
| `{1}` | `CALCULATE(..., REMOVEFILTERS())` | suggested |
| `TOTAL` | `CALCULATE(..., ALLSELECTED())` | suggested |
| `TOTAL <F>` | `CALCULATE(..., ALLSELECTED(), VALUES('T'[F]))` | suggested |
| `Num(x, format)` | `x`; the format belongs to the measure's format string | suggested |
"""
from __future__ import annotations

import json
import re

from . import expr as _expr
from .expr import Unsupported

TRANSLATED, SUGGESTED, NOT_TRANSLATED = "translated", "suggested", "not_translated"
MAX_MEASURES = 500
_AGG = {"sum": ("SUM", "SUMX"), "min": ("MIN", "MINX"), "max": ("MAX", "MAXX"), "avg": ("AVERAGE", "AVERAGEX")}
_ROW_FUNCTIONS = {"if": "IF", "abs": "ABS"}
MAY_DIFFER = {
    "set_values": "{field} set to fixed values: equal to Qlik when {field} is not a dimension of the visual. Where it "
                  "is, Qlik shows the number on the matching rows only and this measure repeats it on every row",
    "set_clear": "the selection in {field} is cleared: equal to Qlik when {field} is not a dimension of the visual",
    "set_1": "the identifier 1 (all rows, whatever is selected): REMOVEFILTERS() also removes the visual's own "
             "grouping, so with a dimension this measure repeats one number where Qlik shows one per row",
    "total": "TOTAL: ALLSELECTED() keeps the filters from outside the visual and drops the visual's own grouping. A "
             "filter set on the visual itself is treated differently from a Qlik selection",
    "total_fields": "TOTAL <{field}>: the grouping is kept for {field} only; other columns of {field}'s table that the "
                    "visual groups by are dropped with the rest",
    "num": "Num() formats the number: the format {format} belongs to the measure's format string, written by a person",
    "no_table": "the table that holds {field} is not known (no load script was given, or the field is not in it): "
                "`{placeholder}` stands in its place",
}


def dax_table(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def dax_column(table: str, column: str) -> str:
    return f"{dax_table(table)}[{column.replace(']', ']]')}]"


def field_index(read: dict | None, tables: dict[str, str] | None = None) -> dict[str, list[tuple[str, str]]]:
    """Qlik field -> [(table in the lakehouse, column)], from `read_script`'s answer."""
    out: dict[str, list[tuple[str, str]]] = {}
    for t in (read or {}).get("tables", []):
        landed = (tables or {}).get(t["name"], t["table"])
        for c in t["columns"]:
            out.setdefault(c["field"], []).append((landed, c["column"]))
    return out


def set_variables(read: dict | None) -> dict[str, str]:
    """The script's variables that a rule may expand: defined with SET (their text as written), once."""
    seen: dict[str, list[dict]] = {}
    for v in (read or {}).get("variables", []):
        seen.setdefault(v["name"], []).append(v)
    return {n: vs[0]["value"] for n, vs in seen.items()
            if len(vs) == 1 and vs[0]["kind"] == "set" and not vs[0]["value"].startswith("(not shown")}


class _Draft:
    def __init__(self, index: dict, measure_names: set[str], own_name: str):
        self.index, self.measures, self.own = index, measure_names, own_name
        self.may_differ: list[str] = []
        self.rules: list[str] = []
        self.tables: list[str] = []

    def note(self, key: str, **kw):
        text = MAY_DIFFER[key].format(**kw)
        if text not in self.may_differ:
            self.may_differ.append(text)

    def rule(self, text: str):
        if text not in self.rules:
            self.rules.append(text)

    def column(self, field: str) -> tuple[str, str]:
        hits = self.index.get(field)
        if not hits:
            placeholder = "<table>"
            self.note("no_table", field=field, placeholder=placeholder)
            return placeholder, field
        if len(hits) > 1:
            raise Unsupported(f"the field {field} is in {len(hits)} tables ({', '.join(t for t, _ in hits)}): in Qlik it is "
                              "one field across them; a person says which table's column the measure reads")
        if hits[0][0] not in self.tables:
            self.tables.append(hits[0][0])
        return hits[0]

    def ref(self, field: str) -> str:
        t, c = self.column(field)
        return dax_column(t, c) if t != "<table>" else f"'<table>'[{c}]"

    # -- inside an aggregation: one row of one table
    def row(self, node, home: list[str]) -> str:
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "str":
            return '"' + node[1].replace('"', '""') + '"'
        if kind == "field":
            if node[1] in self.measures and node[1] not in self.index:
                raise Unsupported(f"the measure {node[1]} inside an aggregation: an aggregation of an aggregation needs Aggr()")
            t, _ = self.column(node[1])
            if t not in home:
                home.append(t)
            return self.ref(node[1])
        if kind == "paren":
            return f"({self.row(node[1], home)})"
        if kind == "neg":
            return f"-{self.row(node[1], home)}"
        if kind == "not":
            return f"NOT({self.row(node[1], home)})"
        if kind == "bin":
            return self.binary(node, lambda n: self.row(n, home))
        if kind == "call":
            return self.function(node, lambda n: self.row(n, home))
        if kind == "agg":
            raise Unsupported("an aggregation inside an aggregation: in Qlik that needs Aggr(), and its DAX depends on the "
                              "model")
        raise Unsupported("a part of the expression this reader does not know")

    def binary(self, node, sub) -> str:
        _, op, a, b = node
        if op == "/":
            self.rule("a / b as DIVIDE(a, b): blank when b is zero, as Qlik's null")
            return f"DIVIDE({sub(a)}, {sub(b)})"
        word = {"and": "&&", "or": "||"}.get(op, op)
        return f"{sub(a)} {word} {sub(b)}"

    def function(self, node, sub) -> str:
        _, name, args = node
        if name == "num":
            if not args:
                raise Unsupported("Num() without an argument")
            fmt = args[1][1] if len(args) > 1 and args[1][0] == "str" else "(Qlik's default)"
            self.note("num", format=fmt)
            return sub(args[0])
        if name in _ROW_FUNCTIONS:
            if name == "if" and len(args) not in (2, 3):
                raise Unsupported("If() takes two or three arguments")
            if name == "abs" and len(args) != 1:
                raise Unsupported("Abs() takes one argument")
            return f"{_ROW_FUNCTIONS[name]}({', '.join(sub(a) for a in args)})"
        raise Unsupported(f"the function {name}() has no rule yet")

    # -- outside an aggregation: numbers, measures and aggregations
    def top(self, node) -> str:
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "str":
            return '"' + node[1].replace('"', '""') + '"'
        if kind == "field":
            name = node[1]
            if name in self.measures and name in self.index:
                raise Unsupported(f"{name} is both a field and a measure in what was given: a person says which is meant")
            if name in self.measures:
                if name == self.own:
                    raise Unsupported("the measure refers to itself")
                self.rule("the name of another measure as a measure reference")
                return f"[{name.replace(']', ']]')}]"
            raise Unsupported(f"the field {name} outside an aggregation: Qlik takes its value when there is exactly one "
                              "(Only); a measure needs a decision about the other cases")
        if kind == "paren":
            return f"({self.top(node[1])})"
        if kind == "neg":
            return f"-{self.top(node[1])}"
        if kind == "not":
            return f"NOT({self.top(node[1])})"
        if kind == "bin":
            return self.binary(node, self.top)
        if kind == "call":
            return self.function(node, self.top)
        if kind == "agg":
            return self.aggregation(node[1])
        raise Unsupported("a part of the expression this reader does not know")

    def aggregation(self, a: dict) -> str:
        fn, arg = a["fn"], a["arg"]
        while arg[0] == "paren":
            arg = arg[1]
        one_field = arg[0] == "field" and not (arg[1] in self.measures and arg[1] not in self.index)
        if fn == "count":
            if not one_field:
                raise Unsupported("Count() of an expression has no rule yet; Count() of one field has")
            col = self.ref(arg[1])
            if a["distinct"]:
                self.rule("Count(DISTINCT F) as DISTINCTCOUNTNOBLANK")
                inner = f"DISTINCTCOUNTNOBLANK({col})"
            else:
                self.rule("Count(F) as COUNTA: the values that are not blank")
                inner = f"COUNTA({col})"
        else:
            if a["distinct"]:
                raise Unsupported(f"{fn.capitalize()}(DISTINCT ...) has no rule yet")
            plain, iterator = _AGG[fn]
            if one_field:
                inner = f"{plain}({self.ref(arg[1])})"
            else:
                home: list[str] = []
                body = self.row(a["arg"], home)
                if len(home) > 1:
                    raise Unsupported(f"the aggregation reads fields of {len(home)} tables ({', '.join(home)}) row by row: "
                                      "which table's rows it runs over, and RELATED() for the others, is a person's decision")
                if not home:
                    raise Unsupported(f"{fn.capitalize()}() of a constant has no rule")
                table = dax_table(home[0]) if home[0] != "<table>" else "'<table>'"
                self.rule(f"{fn.capitalize()}(expression) over one table's rows as {iterator}")
                inner = f"{iterator}({table}, {body})"
        filters = []
        s = a["set"]
        if s:
            if s["identifier"] == "1":
                filters.append("REMOVEFILTERS()")
                self.note("set_1")
            for f, values in s["modifiers"]:
                col = self.ref(f)
                if values is None:
                    filters.append(f"REMOVEFILTERS({col})")
                    self.note("set_clear", field=f)
                elif not values:
                    raise Unsupported(f"the set modifier {f} = {{}} selects no value at all: a person decides what that means "
                                      "in the model")
                else:
                    lits = ", ".join(v if k == "num" else '"' + v.replace('"', '""') + '"' for k, v in values)
                    filters.append(f"{col} IN {{{lits}}}")
                    self.note("set_values", field=f)
        if a["total"] is not None:
            filters.append("ALLSELECTED()")
            if a["total"]:
                for f in a["total"]:
                    filters.append(f"VALUES({self.ref(f)})")
                    self.note("total_fields", field=f)
            else:
                self.note("total")
        return f"CALCULATE({inner}, {', '.join(filters)})" if filters else inner


def read_measures(measures) -> list[dict]:
    """The measures as [{name, expression}], from a list of them, a JSON text (a list, or the objects a Qlik app's
    measure list holds: `qMeasure.qDef` with `qMeasure.qLabel` or `qMetaDef.title`; that layout is Unverified), or
    plain text with one `Name = expression` per line (the name ends at the first ` = `)."""
    if isinstance(measures, str):
        text = measures.strip()
        if text[:1] in "[{":
            try:
                measures = json.loads(text)
            except ValueError as e:
                raise ValueError(f"measures looks like JSON and could not be read: {e}") from None
            if isinstance(measures, dict):
                measures = measures.get("measures") or [measures]
        else:
            rows = []
            for n, line in enumerate(text.splitlines(), 1):
                if not line.strip() or line.strip().startswith("//"):
                    continue
                m = re.match(r"\s*(.+?)\s+=\s(.*)$", line) or re.match(r"\s*([^=]+?)\t+(.*)$", line)
                if not m:
                    raise ValueError(f"line {n} of measures is not `Name = expression`")
                rows.append({"name": m.group(1).strip().strip("[]"), "expression": m.group(2).strip()})
            measures = rows
    if not isinstance(measures, list):
        raise ValueError("measures must be a list of {name, expression}, a JSON text, or lines of `Name = expression`")
    out = []
    for i, m in enumerate(measures, 1):
        if not isinstance(m, dict):
            raise ValueError(f"measure {i} is not an object with name and expression")
        q = m.get("qMeasure") if isinstance(m.get("qMeasure"), dict) else {}
        meta = m.get("qMetaDef") if isinstance(m.get("qMetaDef"), dict) else {}
        name = m.get("name") or m.get("title") or q.get("qLabel") or meta.get("title")
        expression = m.get("expression") or m.get("definition") or q.get("qDef")
        if not isinstance(name, str) or not name.strip() or not isinstance(expression, str) or not expression.strip():
            raise ValueError(f"measure {i} needs a name and an expression")
        out.append({"name": name.strip(), "expression": expression.strip()})
    if len(out) > MAX_MEASURES:
        raise ValueError(f"{len(out)} measures were given; at most {MAX_MEASURES} are read in one call")
    return out


def draft(measures, read: dict | None = None, tables: dict[str, str] | None = None) -> dict:
    """Each measure with its label, its DAX where a rule gives one, and why otherwise. `read` is `read_script`'s answer
    for the app's load script (which table holds each field, and the SET variables); `tables` maps a Qlik table to its
    landed name when that differs from the proposed one."""
    rows = read_measures(measures)
    index = field_index(read, tables)
    variables = set_variables(read)
    names: dict[str, int] = {}
    for r in rows:
        names[r["name"]] = names.get(r["name"], 0) + 1
    out, counts = [], {TRANSLATED: 0, SUGGESTED: 0, NOT_TRANSLATED: 0}
    for r in rows:
        row = {"name": r["name"], "qlik": r["expression"]}
        try:
            if names[r["name"]] > 1:
                raise Unsupported(f"{names[r['name']]} measures are named {r['name']}: a model holds one measure per name, and "
                                  "which expression it keeps is a person's decision")
            text, used = _expr.expand(r["expression"], variables)
            tree = _expr.parse(text)
            d = _Draft(index, set(names), r["name"])
            dax = d.top(tree)
            if not any(n[0] == "agg" or (n[0] == "field" and n[1] in names) for n in _expr.walk(tree)):
                raise Unsupported("no aggregation and no other measure in it: it is a constant, which a person places")
            row["dax"] = dax
            if used:
                row["expanded"] = [f"$({v}) from its SET in the script" for v in dict.fromkeys(used)]
            if d.rules:
                row["rules"] = d.rules
            if d.tables:
                row["table"] = d.tables[0]                # where the measure is placed in the model: the first table read
            row["label"] = SUGGESTED if d.may_differ else TRANSLATED
            if d.may_differ:
                row["may_differ"] = d.may_differ
        except Unsupported as e:
            row["label"] = NOT_TRANSLATED
            row["why"] = str(e)
        counts[row["label"]] += 1
        out.append(row)
    return {"kind": "qlik_measures_draft", "counts": {**counts, "total": len(out)}, "measures": out,
            "field_tables": "from the load script" if index else "not known: no load script was given"}


def tmdl(result: dict) -> str:
    """The measures that have DAX as TMDL lines, per table, to paste into a semantic model draft. A measure with a
    placeholder table is left out."""
    by_table: dict[str, list[dict]] = {}
    for m in result["measures"]:
        if "dax" in m and "<table>" not in m["dax"] and m.get("table"):
            by_table.setdefault(m["table"], []).append(m)
    lines = []
    for t, ms in by_table.items():
        lines.append(f"/// measures for table {dax_table(t)}, drafted from Qlik expressions; not run")
        for m in ms:
            name = "'" + m["name"].replace("'", "''") + "'"
            if m["label"] == SUGGESTED:
                lines.append("/// suggested, may differ from Qlik: " + m["may_differ"][0])
            lines.append(f"measure {name} = {m['dax']}")
        lines.append("")
    return "\n".join(lines).rstrip() + ("\n" if lines else "")
