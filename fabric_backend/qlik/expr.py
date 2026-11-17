"""A Qlik chart expression as a tree (Q2), for the measure drafts (measures.py) and the reconciliation SQL
(reconcile.py). Fixed rules only: nothing is evaluated and no AI model is used.

It reads the part of the expression language that a rule can carry over, and stops with a reason at the rest:

- numbers, 'strings', fields (`Field`, `[Field name]`, `"Field name"`), `+ - * /`, `&`, comparisons, `and`, `or`,
  `not`, brackets, function calls;
- the aggregations Sum, Min, Max, Avg and Count, with `DISTINCT`, with `TOTAL` and `TOTAL <fields>`, and with a set
  expression of this shape: the identifier `$` or `1`, and modifiers `Field = {literal values}` or `Field =` (cleared).

`Unsupported` carries the reason in plain words: an alternate state or a bookmark as the set identifier, set operators,
`P()` and `E()`, a search inside a set, `+=` and `-=`, a dollar-sign expansion that was not resolved, and anything the
grammar does not know. Every Qlik fact here is **Unverified** (help.qlik.com could not be opened from the sessions
that wrote this, 15 and 16 November 2026): written from public knowledge of Qlik's documentation.
"""
from __future__ import annotations

import re

AGGREGATIONS = {"sum", "min", "max", "avg", "count"}
# Aggregation and inter-record functions that are known and have no rule: named in the reason instead of "unknown".
NO_RULE = {
    "aggr": "Aggr() builds a virtual table over dimensions; its DAX depends on the model and is a person's decision",
    "only": "Only() takes a field's value when there is exactly one; a measure needs a decision about the other cases",
    "firstsortedvalue": "FirstSortedValue() has no rule yet", "concat": "Concat() has no rule yet",
    "mode": "Mode() has no rule yet", "median": "Median() has no rule yet", "fractile": "Fractile() has no rule yet",
    "stdev": "Stdev() has no rule yet", "rank": "Rank() depends on the chart it is used in",
    "above": "Above() reads another row of the chart: it depends on the chart's sort order",
    "below": "Below() reads another row of the chart: it depends on the chart's sort order",
    "before": "Before() reads another column of a pivot table", "after": "After() reads another column of a pivot table",
    "rangesum": "RangeSum() is mostly used with Above() or Below() for a running total, which depends on the chart",
    "getfieldselections": "it reads the user's selections", "getselectedcount": "it reads the user's selections",
    "getcurrentselections": "it reads the user's selections", "column": "Column() refers to a column of the chart",
    "dimensionality": "it depends on the chart", "rowno": "it depends on the chart", "pick": "Pick() has no rule yet",
    "match": "Match() has no rule yet", "wildmatch": "WildMatch() has no rule yet", "round": "Qlik's Round() takes a "
    "step and DAX's ROUND takes a number of digits: a person decides", "date": "date formatting belongs to the column's "
    "format in the model", "applymap": "ApplyMap() belongs to the load script",
}
_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<str>'(?:[^']|'')*')
  | (?P<field>\[[^\]]+\]|"[^"]+")
  | (?P<op><>|<=|>=|\+=|-=|\*=|/=|[-+*/&=<>(),{}])
  | (?P<name>[A-Za-z_%\#@][\w%\#@.]*|\$(?![(\w]))
  | (?P<dollar>\$\(|\$\w)
""", re.X)


class Unsupported(ValueError):
    """The expression holds something no rule carries over; the message says what, in plain words."""


def tokens(text: str) -> list[tuple[str, str]]:
    out, i = [], 0
    while i < len(text):
        m = _TOKEN.match(text, i)
        if not m:
            raise Unsupported(f"the character {text[i]!r} at position {i + 1} is not read")
        kind = m.lastgroup
        if kind == "dollar":
            raise Unsupported("a dollar-sign expansion: its text is computed when the app runs")
        if kind != "ws":
            out.append((kind, m.group(0)))
        i = m.end()
    return out


def expand(text: str, variables: dict[str, str]) -> tuple[str, list[str]]:
    """`$(name)` replaced by the variable's text where the script defines it with SET (its text as written). Answers
    the new text and the names that were expanded; any other dollar-sign expansion stays and stops the parse."""
    used: list[str] = []

    def sub(m):
        name = m.group(1)
        if name in variables:
            used.append(name)
            return variables[name]
        return m.group(0)
    for _ in range(5):                                   # a variable may hold another; five levels, then it stays
        new = re.sub(r"\$\(\s*([\w.]+)\s*\)", sub, text)
        if new == text:
            break
        text = new
    return text, used


class _Parser:
    def __init__(self, toks: list[tuple[str, str]]):
        self.t, self.i = toks, 0

    def peek(self, k: int = 0):
        return self.t[self.i + k] if self.i + k < len(self.t) else ("end", "")

    def take(self, value: str | None = None):
        kind, v = self.peek()
        if value is not None and v.lower() != value:
            raise Unsupported(f"expected {value!r} and found {v or 'the end of the expression'!r}")
        self.i += 1
        return kind, v

    def word(self, w: str) -> bool:
        kind, v = self.peek()
        return kind == "name" and v.lower() == w

    # precedence, loosest first: or, and, not, comparison, &, + -, * /, unary minus
    def expr(self):
        left = self.conj()
        while self.word("or") or self.word("xor"):
            op = self.take()[1].lower()
            if op == "xor":
                raise Unsupported("xor has no rule yet")
            left = ("bin", "or", left, self.conj())
        return left

    def conj(self):
        left = self.neg()
        while self.word("and"):
            self.take()
            left = ("bin", "and", left, self.neg())
        return left

    def neg(self):
        if self.word("not"):
            self.take()
            return ("not", self.neg())
        return self.compare()

    def compare(self):
        left = self.concat()
        while self.peek()[1] in ("=", "<>", "<", ">", "<=", ">=") and self.peek()[0] == "op":
            op = self.take()[1]
            left = ("bin", op, left, self.concat())
        if self.word("like") or self.word("precedes") or self.word("follows"):
            raise Unsupported(f"the operator {self.peek()[1]} has no rule yet")
        return left

    def concat(self):
        left = self.add()
        while self.peek() == ("op", "&"):
            self.take()
            left = ("bin", "&", left, self.add())
        return left

    def add(self):
        left = self.mul()
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.take()[1]
            left = ("bin", op, left, self.mul())
        return left

    def mul(self):
        left = self.unary()
        while self.peek() in (("op", "*"), ("op", "/")):
            op = self.take()[1]
            left = ("bin", op, left, self.unary())
        return left

    def unary(self):
        if self.peek() == ("op", "-"):
            self.take()
            return ("neg", self.unary())
        if self.peek() == ("op", "+"):
            self.take()
            return self.unary()
        return self.atom()

    def atom(self):
        kind, v = self.peek()
        if kind == "num":
            self.take()
            return ("num", v)
        if kind == "str":
            self.take()
            return ("str", v[1:-1].replace("''", "'"))
        if kind == "field":
            self.take()
            return ("field", v[1:-1])
        if (kind, v) == ("op", "("):
            self.take()
            inner = self.expr()
            self.take(")")
            return ("paren", inner)
        if kind == "name":
            self.take()
            if self.peek() == ("op", "("):
                return self.call(v)
            return ("field", v)
        raise Unsupported(f"{v or 'the end of the expression'!r} is not expected here")

    def call(self, name: str):
        low = name.lower()
        self.take("(")
        if low in AGGREGATIONS:
            return self.aggregation(low)
        if low in NO_RULE:
            raise Unsupported(f"{name}(): {NO_RULE[low]}")
        args = []
        if self.peek() != ("op", ")"):
            args.append(self.expr())
            while self.peek() == ("op", ","):
                self.take()
                args.append(self.expr())
        self.take(")")
        return ("call", low, args)

    def aggregation(self, name: str):
        node = {"fn": name, "distinct": False, "total": None, "set": None}
        while True:
            if self.peek() == ("op", "{"):
                if node["set"] is not None:
                    raise Unsupported("two set expressions in one aggregation")
                node["set"] = self.set_expression()
            elif self.word("distinct"):
                self.take()
                node["distinct"] = True
            elif self.word("all"):
                raise Unsupported("the ALL qualifier has no rule yet")
            elif self.word("total"):
                self.take()
                node["total"] = []
                if self.peek() == ("op", "<"):
                    self.take()
                    while True:
                        k, v = self.take()
                        if k not in ("name", "field"):
                            raise Unsupported("TOTAL <...> must list fields")
                        node["total"].append(v[1:-1] if k == "field" else v)
                        if self.peek() == ("op", ","):
                            self.take()
                            continue
                        break
                    self.take(">")
            else:
                break
        if self.peek() == ("op", "*") and name == "count":
            raise Unsupported("Count(*) is not allowed in a chart expression in Qlik; say which field is counted")
        node["arg"] = self.expr()
        if self.peek() == ("op", ","):
            raise Unsupported(f"{name.capitalize()}() with more than one argument has no rule yet")
        self.take(")")
        return ("agg", node)

    def set_expression(self):
        self.take("{")
        ident, mods = "$", []
        kind, v = self.peek()
        if (kind, v) != ("op", "<"):
            if kind == "num" and v == "1":
                ident = "1"
            elif kind == "name" and v == "$":
                ident = "$"
            elif kind == "name":
                raise Unsupported(f"the set identifier {v}: an alternate state or a bookmark holds a user's selection, "
                                  "which a measure cannot read")
            else:
                raise Unsupported("a set expression this reader does not know")
            self.take()
        if self.peek() == ("op", "<"):
            self.take()
            while True:
                k, f = self.take()
                if k not in ("name", "field"):
                    raise Unsupported("a set modifier must start with a field")
                f = f[1:-1] if k == "field" else f
                k, op = self.take()
                if op in ("+=", "-=", "*=", "/="):
                    raise Unsupported(f"the set modifier {f} {op} ... changes the user's selection instead of replacing it")
                if op != "=":
                    raise Unsupported("a set modifier this reader does not know")
                values = None                                  # `Field =`: the selection in the field is cleared
                if self.peek() == ("op", "{"):
                    self.take()
                    values = []
                    while self.peek() != ("op", "}"):
                        k, v = self.take()
                        if k == "num":
                            values.append(("num", v))
                        elif k == "op" and v == "-" and self.peek()[0] == "num":
                            values.append(("num", "-" + self.take()[1]))
                        elif k == "str":
                            values.append(("str", v[1:-1].replace("''", "'")))
                        elif k == "field" and v.startswith('"'):
                            raise Unsupported(f"a search inside the set ({v}): which values it finds depends on the data")
                        elif k == "name" and self.peek() == ("op", "("):
                            raise Unsupported(f"{v}() inside a set: the values come from another selection")
                        elif k == "name":
                            values.append(("str", v))
                        elif k == "end":
                            raise Unsupported("a set expression that does not end")
                        else:
                            raise Unsupported("a set element this reader does not know (a search or a comparison)")
                        if self.peek() == ("op", ","):
                            self.take()
                elif self.peek()[0] == "name" and self.peek(1) == ("op", "("):
                    raise Unsupported(f"{self.peek()[1]}() as the set modifier of {f}: the values come from another "
                                      "selection or another field (P() and E() have no rule yet)")
                elif self.peek()[0] in ("name", "field", "num", "str"):
                    raise Unsupported(f"the set modifier of {f} is not a list of values in braces")
                if values is not None:
                    self.take("}")
                mods.append((f, values))
                if self.peek() == ("op", ","):
                    self.take()
                    continue
                break
            self.take(">")
        if self.peek() != ("op", "}"):
            raise Unsupported("set operators (+, -, *, /) between sets: the result is a set of rows no single filter "
                              "describes")
        self.take("}")
        return {"identifier": ident, "modifiers": mods}


def parse(text: str):
    """The expression as a tree, or `Unsupported` with the reason. A leading `=` is dropped."""
    text = text.strip()
    if text.startswith("="):
        text = text[1:]
    if not text.strip():
        raise Unsupported("the expression is empty")
    if "$(" in text:                                     # also inside quotes, where Qlik expands it all the same
        raise Unsupported("a dollar-sign expansion: its text is computed when the app runs")
    p = _Parser(tokens(text))
    tree = p.expr()
    if p.peek()[0] != "end":
        raise Unsupported(f"{p.peek()[1]!r} is not expected after the expression")
    return tree


def walk(node):
    """Every node of a tree, the node itself first."""
    yield node
    kind = node[0]
    if kind in ("neg", "not", "paren"):
        yield from walk(node[1])
    elif kind == "bin":
        yield from walk(node[2])
        yield from walk(node[3])
    elif kind == "call":
        for a in node[2]:
            yield from walk(a)
    elif kind == "agg":
        yield from walk(node[1]["arg"])


def fields(node) -> list[str]:
    """The field names of a tree, in order, each once (set modifiers and TOTAL fields included)."""
    out: list[str] = []
    for n in walk(node):
        names = [n[1]] if n[0] == "field" else []
        if n[0] == "agg":
            names += list(n[1]["total"] or []) + [f for f, _ in (n[1]["set"] or {}).get("modifiers", [])]
        for f in names:
            if f not in out:
                out.append(f)
    return out
