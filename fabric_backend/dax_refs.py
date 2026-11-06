"""Column-level usage in a semantic model: which measures, calculated columns and relationships use a given column.

LANDSCAPE idea 5. The model is the TMDL Krusgraph already reads (model_compare.from_tmdl for tables, sources, columns,
measures and relationships); this module adds the DAX expressions of measures and calculated columns and a small,
conservative reference scanner over them. Nothing here talks to Fabric or runs DAX.

What the scanner reads:
  - `Table[Column]` and `'Quoted Table'[Column]` (`''` inside a quoted name, `]]` inside a bracketed one), also with
    blanks between the table and the bracket;
  - `[Name]`: a measure when a measure has that name; a column when exactly one table the expression names (plus, for a
    calculated column, its own table) has a column of that name;
  - `Table[Measure]`, a measure written with a table in front;
  - a bare or quoted table name (`COUNTROWS(orders)`), which uses the table but no one column;
  - measures that use measures or calculated columns, followed to the end (transitively), with the path.
  Text in strings ("...") and in comments (`//`, `--`, `/* */`) is skipped.

What it does not read, and says so per expression as "could not be read" instead of guessing:
  - a name that resolves to more than one thing: `[x]` with several candidate columns, `[x]` that is both a measure and
    a column, `[x]` that the expression may add itself (a string "x" in ADDCOLUMNS, SELECTCOLUMNS, SUMMARIZE; a table
    constructor `{...}`, CALENDAR, CALENDARAUTO, GENERATESERIES or DATATABLE, which make columns of their own), a
    variable named like a table;
  - a name it does not know: a table or column that is not in the model, a bare word that is neither a function, a
    keyword, a variable nor a table;
  - dynamic references, whose target depends on the query: SELECTEDMEASURE, SELECTEDMEASURENAME,
    SELECTEDMEASUREFORMATSTRING, ISSELECTEDMEASURE, EXTERNALMEASURE;
  - syntax outside the above: an unterminated string, name or comment, or a character DAX expressions here do not use.
  An expression that uses one that could not be read is listed too ("depends on ..."). Not read at all: calculation
  groups and their items, calculated tables' expressions, dynamic format strings, KPIs, row-level security roles,
  `sortByColumn`, hierarchies and perspectives; usage there is not reported.
"""
from __future__ import annotations

import re
from collections import deque

from . import model_compare as _mc

# ------------------------------------------------------------------ the scanner (model-independent) ----------------

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
_NUMBER = re.compile(r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_OPERATORS = set("+-*/^&=<>!,(){};|")
# Words that are neither functions (those are followed by "(") nor names: operators, VAR/RETURN, and the enumerations
# some functions take as arguments (RANKX ties, sort order, CROSSFILTER directions, CONVERT types, WINDOW anchors).
_KEYWORDS = {"VAR", "RETURN", "IN", "NOT", "AND", "OR", "TRUE", "FALSE", "ASC", "DESC", "SKIP", "DENSE", "BOTH", "NONE",
             "ONEWAY", "ONEWAY_LEFTFILTERSRIGHT", "ONEWAY_RIGHTFILTERSLEFT", "INTEGER", "DOUBLE", "STRING", "BOOLEAN",
             "CURRENCY", "DATETIME", "REL", "ABS", "KEEP", "DEFAULT", "FIRST", "LAST", "BLANKS"}
_DYNAMIC = {"SELECTEDMEASURE", "SELECTEDMEASURENAME", "SELECTEDMEASUREFORMATSTRING", "ISSELECTEDMEASURE", "EXTERNALMEASURE"}
_MAKES_COLUMNS = {"CALENDAR", "CALENDARAUTO", "GENERATESERIES", "DATATABLE"}


def _tokens(expr: str) -> tuple[list[tuple[str, str]], str | None]:
    """(kind, text) tokens of a DAX expression, without blanks, strings and comments: `quoted` ('Table'), `bracket`
    ([Name]), `ident`, `string` (kept for the names an expression may add), `number`, `op`. The second value is why
    the scan stopped early (unsupported syntax), or None."""
    out: list[tuple[str, str]] = []
    i, n = 0, len(expr)
    while i < n:
        ch = expr[i]
        if ch.isspace():
            i += 1
        elif expr.startswith("//", i) or expr.startswith("--", i):
            j = expr.find("\n", i)
            i = n if j < 0 else j + 1
        elif expr.startswith("/*", i):
            j = expr.find("*/", i + 2)
            if j < 0:
                return out, "a /* comment is not closed"
            i = j + 2
        elif ch in "\"'[":
            close = {'"': '"', "'": "'", "[": "]"}[ch]
            j, text = i + 1, []
            while True:
                if j >= n:
                    what = {'"': "a string", "'": "a quoted table name", "[": "a [name]"}[ch]
                    return out, f"{what} is not closed"
                if expr[j] == close:
                    if j + 1 < n and expr[j + 1] == close:
                        text.append(close)
                        j += 2
                        continue
                    break
                text.append(expr[j])
                j += 1
            out.append(({'"': "string", "'": "quoted", "[": "bracket"}[ch], "".join(text)))
            i = j + 1
        elif ch.isdigit() or (ch == "." and i + 1 < n and expr[i + 1].isdigit()):
            m = _NUMBER.match(expr, i)
            out.append(("number", m.group(0)))
            i = m.end()
        elif ch.isalpha() or ch == "_":
            m = _IDENT.match(expr, i)
            out.append(("ident", m.group(0)))
            i = m.end()
        elif ch in _OPERATORS:
            out.append(("op", ch))
            i += 1
        else:
            return out, f"the character {ch!r} is not DAX this scanner reads"
    return out, None


def scan(expr: str) -> dict:
    """The references an expression makes, before they are matched with a model:
    qualified: [(table, name)]   Table[Name]
    unqualified: [name]          [Name]
    tables: [table]              a bare or quoted table name
    bare: [word]                 a bare word that is not a function, keyword or variable (a table, or unknown)
    variables, strings: the names the expression declares (VAR) and the string literals it holds
    makes_columns: whether it builds a table with columns of its own (a constructor, CALENDAR, ...)
    dynamic: the dynamic functions it calls; syntax: why the scan stopped, or None."""
    toks, syntax = _tokens(expr)
    out = {"qualified": [], "unqualified": [], "tables": [], "bare": [], "variables": set(), "strings": set(),
           "makes_columns": False, "dynamic": [], "syntax": syntax}
    i = 0
    while i < len(toks):
        kind, text = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else (None, None)
        if kind in ("quoted", "ident") and nxt[0] == "bracket":
            out["qualified"].append((text, nxt[1]))
            i += 2
            continue
        if kind == "quoted":
            out["tables"].append(text)
        elif kind == "bracket":
            out["unqualified"].append(text)
        elif kind == "string":
            out["strings"].add(text.lower())
        elif kind == "op" and text == "{":
            out["makes_columns"] = True
        elif kind == "ident":
            word = text.upper()
            if nxt == ("op", "("):
                if word in _DYNAMIC:
                    out["dynamic"].append(word)
                if word in _MAKES_COLUMNS:
                    out["makes_columns"] = True
            elif word == "VAR" and nxt[0] == "ident":
                out["variables"].add(nxt[1].lower())
                i += 2
                continue
            elif word not in _KEYWORDS:
                out["bare"].append(text)
        i += 1
    return out


# ------------------------------------------------------------------ expressions from TMDL ---------------------------

_OBJECT = re.compile(r"^(\t*)(table|column|measure|partition|relationship|calculationGroup|calculationItem|hierarchy|"
                     r"annotation|expression|role|perspective|culture|ref|kpi)\b(.*)$")


def _dedent(lines: list[str]) -> str:
    body = [ln for ln in lines if ln.strip()]
    cut = min((len(ln) - len(ln.lstrip("\t ")) for ln in body), default=0)
    return "\n".join(ln[cut:] for ln in lines).strip("\n")


def expressions(parts: dict[str, str]) -> dict[tuple[str, str, str], str]:
    """(kind, table, name) -> DAX text for every measure and calculated column in a TMDL definition, with its line
    breaks kept (a `//` comment ends at the end of its line). Three forms: on the same line (`measure x = SUM(...)`),
    on the lines below, one level deeper than the object's properties, and between ``` fences."""
    out: dict[tuple[str, str, str], str] = {}
    for path in sorted(parts):
        if not path.endswith(".tmdl"):
            continue
        table = None
        key: tuple[str, str, str] | None = None
        lines: list[str] = []
        fenced = False
        obj_depth = 0

        def finish():
            if key is not None:
                out[key] = _dedent(lines)

        for raw in parts[path].splitlines():
            if key is not None and fenced:
                if raw.strip().startswith("```"):
                    fenced = False
                    finish()
                    key = None
                    continue
                lines.append(raw)
                continue
            depth = len(raw) - len(raw.lstrip("\t"))
            if key is not None:
                if not raw.strip() or depth >= obj_depth + 2:
                    lines.append(raw)
                    continue
                finish()
                key = None
            o = _OBJECT.match(raw)
            if not o:
                continue
            if depth == 0:
                table = _mc._name_and_rest(o.group(3))[0] if o.group(2) == "table" else None
                continue
            if table is None or depth != 1 or o.group(2) not in ("measure", "column"):
                continue
            name, rest = _mc._name_and_rest(o.group(3))
            if not rest.startswith("="):
                continue                                                      # a column read from the source
            body = rest[1:].strip()
            key, obj_depth = (o.group(2), table, name), depth
            if body.startswith("```"):
                fenced, lines = True, []
                inline = body[3:]
                if inline.strip().endswith("```"):                           # ```expr``` on one line
                    lines, fenced = [inline.strip()[:-3]], False
                    finish()
                    key = None
                elif inline.strip():
                    lines.append(inline)
            else:
                lines = [body] if body else []
        if key is not None:
            finish()
    return out


# ------------------------------------------------------------------ resolving against the model ---------------------

def dax_column(table: str, column: str) -> str:
    """How DAX writes a column: orders[amount], 'Order Lines'[unit price]."""
    t = table if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table) else "'" + table.replace("'", "''") + "'"
    return f"{t}[{column.replace(']', ']]')}]"


def _label(node: tuple[str, str, str]) -> str:
    kind, table, name = node
    return "[" + name.replace("]", "]]") + "]" if kind == "measure" else dax_column(table, name)


class Model:
    """A semantic model read for usage: tables with their columns, measures (model-wide names), relationships and,
    per measure and calculated column, what its expression refers to and what could not be read."""

    def __init__(self, parts: dict[str, str]):
        self.shape = _mc.from_tmdl(parts)
        self.tables = {name.lower(): name for name in self.shape["tables"]}
        self.columns = {name: {c.lower(): c for c in t["columns"]} for name, t in self.shape["tables"].items()}
        self.calculated = {(name, c) for name, t in self.shape["tables"].items() for c, col in t["columns"].items() if col.get("calculated")}
        measures: dict[str, list[tuple[str, str]]] = {}
        for name, t in self.shape["tables"].items():
            for m in t["measures"]:
                measures.setdefault(m.lower(), []).append((name, m))
        self.measures = measures
        self.exprs = {k: v for k, v in expressions(parts).items() if k[1] in self.shape["tables"]}
        for (kind, table, name) in [("measure", t, m) for t, x in self.shape["tables"].items() for m in x["measures"]] + \
                                   [("column", t, c) for (t, c) in sorted(self.calculated)]:
            self.exprs.setdefault((kind, table, name), "")
        self.refs: dict[tuple, dict] = {k: self._resolve(k, v) for k, v in sorted(self.exprs.items())}

    def _measure(self, name: str) -> tuple[str, str] | None:
        hits = self.measures.get(name.lower(), [])
        return hits[0] if len(hits) == 1 else None

    def _resolve(self, key: tuple[str, str, str], expr: str) -> dict:
        """columns: {(table, column)}, uses: {node} (measures and calculated columns), tables: {table},
        unread: [why], ambiguous: {(table, column)} the candidates of a name that could not be settled, anywhere: whether
        something that could not be read may refer to any column (a stopped scan, an unknown or dynamic name)."""
        kind, home, _ = key
        s = scan(expr)
        r = {"columns": set(), "uses": set(), "tables": set(), "unread": [], "ambiguous": set(), "anywhere": False}

        def unread(why: str, candidates=None):
            """`candidates`: the columns an ambiguous name may be; None: the expression may refer to anything."""
            r["unread"].append(why)
            if candidates is None:
                r["anywhere"] = True
            else:
                r["ambiguous"].update(candidates)
        if not expr.strip():
            unread("the expression could not be found in the TMDL")
            return r
        if s["syntax"]:
            unread(s["syntax"])
        for f in sorted(set(s["dynamic"])):
            unread(f"{f}() refers to whatever the query puts in context (a dynamic reference)")
        named: set[str] = set()                                               # tables the expression names
        for t in s["tables"]:
            canon = self.tables.get(t.lower())
            if canon:
                r["tables"].add(canon)
                named.add(canon)
            else:
                unread(f"'{t}' is not a table of the model")
        for w in s["bare"]:
            canon, var = self.tables.get(w.lower()), w.lower() in s["variables"]
            if canon and var:
                unread(f"{w} is both a variable and a table")
            elif canon:
                r["tables"].add(canon)
                named.add(canon)
            elif not var:
                unread(f"{w} is neither a table, a variable, a keyword nor a function")
        for t, name in s["qualified"]:
            canon = self.tables.get(t.lower())
            if not canon:
                unread(f"{t}[{name}]: {t} is not a table of the model")
                continue
            named.add(canon)
            col = self.columns[canon].get(name.lower())
            m = self._measure(name)
            if col and m:
                unread(f"{dax_column(canon, name)} names both a column and the measure [{m[1]}]")
            elif col:
                r["columns"].add((canon, col))
                if (canon, col) in self.calculated:
                    r["uses"].add(("column", canon, col))
            elif m:
                r["uses"].add(("measure", *m))
            else:
                unread(f"{dax_column(canon, name)}: no column or measure of that name")
        for name in s["unqualified"]:
            low = name.lower()
            m = self._measure(name)
            everywhere = sorted((t, cols[low]) for t, cols in self.columns.items() if low in cols)
            local = low in s["strings"] or s["makes_columns"]
            if m and not everywhere:
                r["uses"].add(("measure", *m))
                continue
            if len(self.measures.get(low, [])) > 1:
                unread(f"[{name}]: more than one measure has that name")
                continue
            scope = named | ({home} if kind == "column" else set())
            near = [(t, c) for t, c in everywhere if t in scope]
            if m:
                unread(f"[{name}] names both a measure and a column ({', '.join(dax_column(*x) for x in everywhere)})")
            elif local and everywhere:
                unread(f"[{name}] may be a column the expression makes itself or a column of the model", everywhere)
            elif local:
                continue                                                      # a column the expression adds: not a model reference
            elif len(near) == 1:
                r["columns"].add(near[0])
                if near[0] in self.calculated:
                    r["uses"].add(("column", *near[0]))
            elif near:
                unread(f"[{name}] could be any of {', '.join(dax_column(*x) for x in near)}", near)
            elif everywhere:
                unread(f"[{name}] has no table named in the expression to belong to "
                       f"(candidates: {', '.join(dax_column(*x) for x in everywhere)})", everywhere)
            else:
                unread(f"[{name}]: no measure or column of that name")
        r["unread"] = sorted(set(r["unread"]))
        return r

    # -------------------------------------------------------------- usage ----------------------------------------

    def _users(self) -> dict[tuple, list[tuple]]:
        back: dict[tuple, list[tuple]] = {}
        for node, r in self.refs.items():
            for used in r["uses"]:
                back.setdefault(used, []).append(node)
        return {k: sorted(v) for k, v in back.items()}

    def _walk(self, direct: list[tuple], start: str) -> dict[tuple, list[str]]:
        """node -> the shortest path from `start` (a column's label) through the expressions in between, breadth first
        and in sorted order so the same model gives the same answer."""
        back = self._users()
        paths: dict[tuple, list[str]] = {}
        queue = deque()
        for node in sorted(set(direct)):
            paths[node] = [start, _label(node)]
            queue.append(node)
        while queue:
            node = queue.popleft()
            for user in back.get(node, []):
                if user not in paths:
                    paths[user] = paths[node] + [_label(user)]
                    queue.append(user)
        return paths

    def _report(self, start: str, direct: list[tuple], maybe: list[tuple], relationships: list[dict]) -> dict:
        paths = self._walk(direct, start)
        out = {"measures": [], "calculated_columns": [], "relationships": relationships, "could_not_be_read": []}
        for node in sorted(paths):
            kind, table, name = node
            out["measures" if kind == "measure" else "calculated_columns"].append(
                {"table": table, "name": name, "direct": len(paths[node]) == 2, "path": paths[node]})
        # what could not be read: an expression that might use this column, and every expression that uses one of those
        unread = {node: "; ".join(self.refs[node]["unread"]) for node in sorted(set(maybe)) if node not in paths}
        back = self._users()
        queue = deque(sorted(unread))
        while queue:
            node = queue.popleft()
            for user in back.get(node, []):
                if user not in unread and user not in paths:
                    unread[user] = f"depends on {_label(node)}, which could not be read"
                    queue.append(user)
        out["could_not_be_read"] = [{"object": "measure" if k[0] == "measure" else "calculated column", "table": k[1], "name": k[2],
                                     "why": unread[k]} for k in sorted(unread)]
        return out

    def _maybe(self, hit) -> list[tuple]:
        """Expressions that could not be read and might refer to the target: those that may refer to anything (a
        stopped scan, an unknown or dynamic name) and those with an ambiguous name whose candidates `hit` accepts."""
        return [node for node, r in self.refs.items()
                if r["unread"] and (r["anywhere"] or any(hit(t, c) for t, c in r["ambiguous"]))]

    def column_usage(self, table: str, column: str) -> dict:
        """What uses one column of the model (its model name)."""
        direct = [n for n, r in self.refs.items() if (table, column) in r["columns"] and n != ("column", table, column)]
        rels = [r for r in self.shape["relationships"]
                if (r["from_table"], r["from_column"].lower()) == (table, column.lower()) or (r["to_table"], r["to_column"].lower()) == (table, column.lower())]
        return {"column": dax_column(table, column),
                **self._report(dax_column(table, column), direct, self._maybe(lambda t, c: (t, c) == (table, column)), _rels(rels))}

    def table_usage(self, table: str) -> dict:
        """What uses a table of the model at all: by name, through any of its columns, or as the home of a measure."""
        own = [n for n in self.refs if n[1] == table]
        direct = [n for n, r in self.refs.items() if n[1] != table and (table in r["tables"] or any(t == table for t, _ in r["columns"]))]
        rels = [r for r in self.shape["relationships"] if table in (r["from_table"], r["to_table"])]
        label = table if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table) else "'" + table.replace("'", "''") + "'"
        out = self._report(label, direct + own, self._maybe(lambda t, c: t == table), _rels(rels))
        for group in ("measures", "calculated_columns"):
            for x in out[group]:
                if x["table"] == table and x["direct"]:
                    x["defined_on_the_table"] = True
        return {"table": label, **out}

    def source_columns(self, source_table: str, source_column: str, schema: str | None = None) -> list[tuple[str, str]]:
        """The model columns read from one source column: the table's partition names the source table (or, without
        a source, the table has that name) and the column's sourceColumn names the column."""
        out = []
        for tname in self.source_tables(source_table, schema):
            for cname, c in sorted(self.shape["tables"][tname]["columns"].items()):
                if not c.get("calculated") and str(c.get("source_column") or cname).lower() == source_column.lower():
                    out.append((tname, cname))
        return out

    def source_tables(self, source_table: str, schema: str | None = None) -> list[str]:
        out = []
        for tname, t in sorted(self.shape["tables"].items()):
            if str(t.get("kind") or "").lower() == "calculated":
                continue
            src = t.get("source") or tname
            if str(src).lower() != source_table.lower():
                continue
            if schema and t.get("source_schema") and str(t["source_schema"]).lower() != schema.lower():
                continue
            out.append(tname)
        return out


def _rels(rels: list[dict]) -> list[dict]:
    return sorted(({"from": dax_column(r["from_table"], r["from_column"]), "to": dax_column(r["to_table"], r["to_column"]),
                    "active": r["active"]} for r in rels), key=lambda x: (x["from"], x["to"]))


NOTE = ("Read from the DAX of measures and calculated columns in the model's TMDL: Table[Column], [Measure], quoted names "
        "and measures over measures, strings and comments skipped. Anything the scanner cannot settle (a name with more "
        "than one meaning, an unknown name, SELECTEDMEASURE and other dynamic references, unsupported syntax) is listed "
        "under could_not_be_read rather than guessed. Calculation groups, calculated tables, format string expressions, "
        "security roles, sortByColumn and hierarchies are not read.")


# ------------------------------------------------------------------ the answers of plan_drift and compare_semantic_model

def for_source_changes(parts: dict[str, str], removed_columns: list[dict], tables_gone: list[dict]) -> dict:
    """plan_drift: per column the source no longer has ({table: "schema.table", column}) and per table it lost, what of
    this model uses it. A renamed column shows in plan_drift as one removed and one new; the removed name is the one
    the model still reads."""
    model = Model(parts)
    columns, tables = [], []
    for x in sorted(removed_columns, key=lambda x: (str(x["table"]).lower(), str(x["column"]).lower())):
        schema, _, table = str(x["table"]).rpartition(".")
        for mt, mc in model.source_columns(table, str(x["column"]), schema or None):
            columns.append({"source": f"{x['table']}.{x['column']}", **model.column_usage(mt, mc)})
    for x in sorted(tables_gone, key=lambda x: str(x["table"]).lower()):
        schema, _, table = str(x["table"]).rpartition(".")
        for mt in model.source_tables(table, schema or None):
            tables.append({"source": str(x["table"]), **model.table_usage(mt)})
    return {"columns": columns, "tables": tables}


def for_drift(edges: list[dict], drift: dict, read_parts) -> dict | None:
    """The `column_usage` of plan_drift: for each semantic model lineage found on a table the drift touches, the model's
    definition is read again (`read_parts(model_id)` -> {path: TMDL}) and its usage of the removed columns and lost
    tables reported. None when no semantic model is touched."""
    touched = {str(x["table"]).split(".")[-1].lower() for x in drift.get("tables_gone", []) + drift.get("removed_columns", [])}
    models = sorted({(e["object"], e["id"]) for e in edges if e.get("kind") == "semantic_model" and str(e["table"]).lower() in touched})
    if not models:
        return None
    out = []
    for name, model_id in models:
        try:
            parts = read_parts(model_id)
        except Exception as e:  # noqa: BLE001 — one unreadable model must not hide the others
            out.append({"model": name, "id": model_id, "could_not_read_the_model": f"{type(e).__name__}: {str(e)[:200]}"})
            continue
        out.append({"model": name, "id": model_id,
                    **for_source_changes(parts, drift.get("removed_columns", []), drift.get("tables_gone", []))})
    return {"models": out, "note": NOTE}


def for_compare(parts: dict[str, str], columns_gone: list[dict]) -> dict:
    """compare_semantic_model: per model column whose source column is gone (`tables.columns_gone`), what uses it."""
    model = Model(parts)
    names = sorted(model.shape["tables"], key=lambda t: (-len(t), t))
    out = []
    for g in columns_gone:
        ref = str(g.get("model", ""))
        table = next((t for t in names if ref.startswith(t + ".")), None)
        if table is None:
            continue
        column = ref[len(table) + 1:]
        out.append({"source_table": g.get("source_table"), **model.column_usage(table, column)})
    return {"columns": out, "note": NOTE}
