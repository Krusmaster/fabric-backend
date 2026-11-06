"""The total that doubles, in SQL views: a view that SUMs a header amount after joining the header to its line table.

amounts.py (validate_plan's `amount_levels`) knows from the plan which header amounts a join repeats: orders.order_amount
is repeated on every order_lines row of the order. This module reads the definitions of the SQL views on the source's
SQL endpoint and points at the views that do exactly that: SUM(o.order_amount) in a SELECT whose FROM joins orders to
order_lines on the relationship's columns. Per flagged view it reports the amount, the join and the line of the
definition the SUM is on.

What is read: one read-only query on the connection the caller already has, the view definitions in sys.sql_modules
(DEFINITIONS_SQL); where that view is not available, INFORMATION_SCHEMA.VIEWS (DEFINITIONS_SQL_INFO), whose
VIEW_DEFINITION column stops at 4000 characters, so a definition of that length is reported as not read. No rows of any
table or view are read, and no value from a definition is repeated: string and number literals in the SQL shown are
replaced by `?`.

The parser is conservative. It reads one CREATE VIEW ... AS SELECT statement: SELECT blocks joined by UNION, EXCEPT or
INTERSECT, FROM with base tables and derived tables (a SELECT in parentheses), INNER, LEFT, RIGHT, FULL and CROSS joins
with ON conditions, comma joins with their WHERE, GROUP BY, HAVING, ORDER BY, and subqueries in expressions. Anything
else is reported as "could not be read", with the reason and the line, and never guessed:

    dynamic SQL (EXEC, sp_executesql), OPENROWSET/OPENQUERY/OPENDATASOURCE/OPENJSON
    a CTE (WITH ... AS): CTE chains are not followed
    APPLY, PIVOT, UNPIVOT, a table-valued function, a parenthesised join, nested joins (A JOIN B JOIN C ON ... ON ...)
    a window SUM (SUM(...) OVER), SUM(DISTINCT ...), a definition that is truncated, encrypted (NULL) or ends inside a
    string, comment or bracket

A block that sums a header amount is judged by what else its FROM joins. A source joined on all the columns of its key
(the plan's key, bound to another source's column or to a literal) adds at most one row per row; a derived table grouped
by columns that are all bound does too. The line table joined to the header on the relationship's columns is the
finding. Any other source (a table outside the plan, another view, a derived table whose grain is not known, a join on
other columns) may repeat rows or may not: such a view is "could not be read", not flagged.

Only views whose definition names a header table of the plan are parsed; the others are counted. Notebooks are not read.
"""
from __future__ import annotations

import re

from .amounts import LEVELS, header_amounts
from .infer import Plan

DEFINITIONS_SQL = ("SELECT s.name AS VIEW_SCHEMA, v.name AS VIEW_NAME, m.definition AS VIEW_DEFINITION FROM sys.views v "
                   "JOIN sys.schemas s ON s.schema_id = v.schema_id JOIN sys.sql_modules m ON m.object_id = v.object_id")
DEFINITIONS_SQL_INFO = "SELECT TABLE_SCHEMA AS VIEW_SCHEMA, TABLE_NAME AS VIEW_NAME, VIEW_DEFINITION FROM INFORMATION_SCHEMA.VIEWS"
INFO_LIMIT = 4000            # INFORMATION_SCHEMA.VIEWS.VIEW_DEFINITION is nvarchar(4000): a longer definition is cut there
MAX_LISTED = 50              # entries per list in the answer; the counts are always complete

RULE = ("SUM over a header amount in a SELECT that joins the header to its line table on the relationship's columns counts "
        "each header row once per line row.")

_DYNAMIC = {"EXEC", "EXECUTE", "SP_EXECUTESQL"}
_EXTERNAL = {"OPENROWSET", "OPENQUERY", "OPENDATASOURCE", "OPENJSON", "OPENXML"}
_UNSUPPORTED_FROM = {"APPLY": "APPLY", "PIVOT": "PIVOT", "UNPIVOT": "UNPIVOT", "TABLESAMPLE": "TABLESAMPLE",
                     "FOR": "FOR SYSTEM_TIME", "MATCH": "MATCH"}
_SET_OPS = {"UNION", "EXCEPT", "INTERSECT"}
_CLAUSES = {"FROM", "WHERE", "GROUP", "HAVING", "ORDER", "OPTION", "FOR", "INTO", "OFFSET", "WINDOW"}
_JOIN_WORDS = {"JOIN", "INNER", "LEFT", "RIGHT", "FULL", "CROSS", "OUTER"}
_KEYWORDS = _CLAUSES | _SET_OPS | _JOIN_WORDS | {
    "SELECT", "AS", "ON", "AND", "OR", "NOT", "NULL", "IS", "IN", "LIKE", "BETWEEN", "EXISTS", "CASE", "WHEN", "THEN",
    "ELSE", "END", "DISTINCT", "ALL", "TOP", "PERCENT", "TIES", "WITH", "BY", "ASC", "DESC", "OVER", "PARTITION", "ROWS",
    "RANGE", "UNBOUNDED", "PRECEDING", "FOLLOWING", "CURRENT", "ROW", "ESCAPE", "COLLATE", "APPLY", "PIVOT", "UNPIVOT",
    "SOME", "ANY", "FETCH", "NEXT", "ONLY", "TRY_CAST", "CAST", "CONVERT", "TRY_CONVERT"}
# type names as they appear in CAST(x AS decimal(18, 2)) or CONVERT(int, x): never a column
_TYPES = {"INT", "BIGINT", "SMALLINT", "TINYINT", "BIT", "DECIMAL", "NUMERIC", "MONEY", "SMALLMONEY", "FLOAT", "REAL",
          "DATE", "DATETIME", "DATETIME2", "SMALLDATETIME", "DATETIMEOFFSET", "TIME", "CHAR", "VARCHAR", "NCHAR",
          "NVARCHAR", "TEXT", "NTEXT", "BINARY", "VARBINARY", "UNIQUEIDENTIFIER", "MAX"}


class Unreadable(Exception):
    """A part of the definition the parser cannot read with certainty."""

    def __init__(self, reason: str, line: int | None = None):
        super().__init__(reason)
        self.reason, self.line = reason, line


# ------------------------------------------------------------------ tokens ---------------------------------------------

class Tok:
    __slots__ = ("kind", "text", "line")

    def __init__(self, kind: str, text: str, line: int):
        self.kind, self.text, self.line = kind, text, line

    @property
    def word(self) -> str:
        """The upper-cased text of a bare word; "" for anything else (a quoted name is never a keyword)."""
        return self.text.upper() if self.kind == "id" else ""

    @property
    def name(self) -> str:
        """The identifier without its quotes."""
        if self.kind == "qid":
            return self.text[1:-1].replace("]]", "]") if self.text[0] == "[" else self.text[1:-1].replace('""', '"')
        return self.text

    def __repr__(self) -> str:                                            # pragma: no cover - debugging only
        return f"{self.kind}:{self.text}@{self.line}"


_BARE = re.compile(r"[A-Za-z_#À-￿][A-Za-z0-9_#$@À-￿]*")
_NUM = re.compile(r"(?:0x[0-9A-Fa-f]*|\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)")
_VAR = re.compile(r"@@?[A-Za-z0-9_#$@]*")


def tokens(text: str) -> list[Tok]:
    """T-SQL tokens with their line (1 = the first line of the definition); comments are dropped. An unterminated string,
    quoted name or comment is Unreadable."""
    out: list[Tok] = []
    i, n, line = 0, len(text), 1
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
        elif c.isspace():
            i += 1
        elif text.startswith("--", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            depth, j, start = 1, i + 2, line
            while j < n and depth:                                      # T-SQL block comments nest
                if text.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif text.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            if depth:
                raise Unreadable("the definition ends inside a comment", start)
            line += text.count("\n", i, j)
            i = j
        elif c == "'" or (c in "Nn" and text.startswith("'", i + 1)):
            j = i + (2 if c != "'" else 1)
            while True:
                k = text.find("'", j)
                if k < 0:
                    raise Unreadable("the definition ends inside a string", line)
                if text.startswith("''", k):
                    j = k + 2
                    continue
                break
            out.append(Tok("str", text[i:k + 1], line))
            line += text.count("\n", i, k + 1)
            i = k + 1
        elif c in '["':
            close = "]" if c == "[" else '"'
            j = i + 1
            while True:
                k = text.find(close, j)
                if k < 0:
                    raise Unreadable("the definition ends inside a quoted name", line)
                if text.startswith(close * 2, k):
                    j = k + 2
                    continue
                break
            out.append(Tok("qid", text[i:k + 1], line))
            line += text.count("\n", i, k + 1)
            i = k + 1
        elif c == "@":
            m = _VAR.match(text, i)
            out.append(Tok("var", m.group(0), line))
            i = m.end()
        elif c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):
            m = _NUM.match(text, i)
            out.append(Tok("num", m.group(0), line))
            i = m.end()
        elif _BARE.match(text, i):
            m = _BARE.match(text, i)
            out.append(Tok("id", m.group(0), line))
            i = m.end()
        else:
            two = text[i:i + 2]
            if two in ("<=", ">=", "<>", "!=", "!<", "!>", "::", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "||"):
                out.append(Tok("op", two, line))
                i += 2
            else:
                out.append(Tok("op", c, line))
                i += 1
    return out


def _shown(toks: list[Tok]) -> str:
    """The tokens as SQL, literals replaced by ?: code, never a value from the definition."""
    out, prev = "", None
    for t in toks:
        s = "?" if t.kind in ("str", "num") else t.text
        call = s == "(" and prev is not None and prev.kind == "id" and prev.word not in _KEYWORDS
        if out and not (s in (")", ",", ".") or out.endswith(("(", ".")) or call):
            out += " "
        out += s
        prev = t
    return out


def _close(toks: list[Tok], i: int) -> int:
    """The index of the ')' that closes the '(' at i."""
    depth = 0
    for j in range(i, len(toks)):
        if toks[j].text == "(" and toks[j].kind == "op":
            depth += 1
        elif toks[j].text == ")" and toks[j].kind == "op":
            depth -= 1
            if depth == 0:
                return j
    raise Unreadable("unbalanced parentheses", toks[i].line)


def _top(toks: list[Tok]):
    """(index, token) of the tokens outside any parentheses."""
    depth = 0
    for i, t in enumerate(toks):
        if t.kind == "op" and t.text == "(":
            depth += 1
            if depth == 1:
                yield i, t
            continue
        if t.kind == "op" and t.text == ")":
            depth -= 1
            if depth < 0:
                raise Unreadable("unbalanced parentheses", t.line)
            continue
        if depth == 0:
            yield i, t


def _is_op(t: Tok | None, s: str) -> bool:
    return t is not None and t.kind == "op" and t.text == s


def _at(toks: list[Tok], i: int) -> Tok | None:
    return toks[i] if 0 <= i < len(toks) else None


# ------------------------------------------------------------------ the structure --------------------------------------

class Source:
    """One entry of a FROM: a base table or a derived table, with what is known of its rows."""

    def __init__(self, alias: str, line: int, toks: list[Tok]):
        self.alias = alias
        self.line = line
        self.toks = toks                      # how it is written, for the answer
        self.table: str | None = None         # the plan table it reads, when known
        self.parts: list[str] = []            # the name as written: [db, schema, table] or fewer
        self.grain = "unknown"                # "rows" (one row per row of table), "grouped", "unknown"
        self.group: list[str] = []            # with "grouped": the exposed columns it is grouped by
        self.columns: dict[str, str | None] | None = None   # exposed name (lower) -> column of `table`; None: not known
        self.derived = False


class Block:
    def __init__(self):
        self.sources: list[Source] = []
        self.equal: list[tuple[tuple, tuple]] = []      # (ref, ref) column = column, from ON and WHERE
        self.bound_literal: list[tuple] = []            # ref = literal
        self.is_null: list[tuple] = []                  # ref IS NULL anywhere in ON or WHERE (an anti-join, maybe)
        self.sums: list[tuple] = []                     # (SUM(...) tokens, line, distinct, window, argument tokens)
        self.select: list[Tok] = []
        self.group: list[Tok] = []
        self.distinct = False
        self.top = False
        self.children: list[list[Block]] = []           # subqueries in expressions and derived tables
        self.joins: list[tuple[Source, list[Tok]]] = []  # source and its ON condition as written


def _strip_semicolons(toks: list[Tok]) -> list[Tok]:
    while toks and _is_op(toks[-1], ";"):
        toks = toks[:-1]
    return toks


def view_body(toks: list[Tok]) -> list[Tok]:
    """The query of CREATE [OR ALTER] VIEW name [(columns)] [WITH options] AS query."""
    toks = _strip_semicolons(toks)
    for t in toks:
        if t.word in _DYNAMIC:
            raise Unreadable(f"dynamic SQL ({t.text})", t.line)
        if t.word in _EXTERNAL:
            raise Unreadable(f"{t.text} reads outside the database", t.line)
    i = 0
    if not toks or toks[0].word not in ("CREATE", "ALTER"):
        raise Unreadable("not a CREATE VIEW statement", toks[0].line if toks else 1)
    i = 1
    if toks[0].word == "CREATE" and _at(toks, 1) and toks[1].word == "OR" and _at(toks, 2) and toks[2].word == "ALTER":
        i = 3
    if not (_at(toks, i) and toks[i].word == "VIEW"):
        raise Unreadable("not a CREATE VIEW statement", toks[min(i, len(toks) - 1)].line)
    i += 1
    while _at(toks, i) and (toks[i].kind in ("id", "qid") or _is_op(toks[i], ".")) and toks[i].word != "AS" and toks[i].word != "WITH":
        i += 1
    if _is_op(_at(toks, i), "("):
        i = _close(toks, i) + 1
    if _at(toks, i) and toks[i].word == "WITH":
        i += 1
        while _at(toks, i) and (toks[i].kind == "id" or _is_op(toks[i], ",")) and toks[i].word != "AS":
            i += 1
    if not (_at(toks, i) and toks[i].word == "AS"):
        raise Unreadable("CREATE VIEW without AS where it was expected", toks[min(i, len(toks) - 1)].line)
    body = toks[i + 1:]
    if not body:
        raise Unreadable("the view has no query", toks[i].line)
    if _at(body, len(body) - 1) and body[-1].word == "CHECK" and len(body) >= 3 and body[-2].word == "WITH":
        body = body[:-2]                                                # WITH CHECK OPTION
    elif len(body) >= 3 and body[-1].word == "OPTION" and body[-2].word == "CHECK" and body[-3].word == "WITH":
        body = body[:-3]
    return body


def parse_query(toks: list[Tok]) -> list[Block]:
    """SELECT blocks joined by UNION [ALL], EXCEPT or INTERSECT."""
    if not toks:
        raise Unreadable("an empty query")
    if toks[0].word == "WITH":
        raise Unreadable("a CTE (WITH ... AS): CTE chains are not followed", toks[0].line)
    parts, start = [], 0
    for i, t in _top(toks):
        if t.word in _SET_OPS:
            parts.append(toks[start:i])
            start = i + 1
            if _at(toks, start) and toks[start].word == "ALL":
                start += 1
    parts.append(toks[start:])
    out = []
    for p in parts:
        if not p:
            raise Unreadable("an empty part of a UNION", toks[0].line)
        if _is_op(p[0], "("):
            raise Unreadable("a SELECT in parentheses inside a UNION", p[0].line)
        if p[0].word != "SELECT":
            raise Unreadable(f"expected SELECT, found {p[0].text}", p[0].line)
        out.append(parse_block(p))
    return out


def parse_block(toks: list[Tok]) -> Block:
    b = Block()
    i = 1
    if _at(toks, i) and toks[i].word in ("ALL", "DISTINCT"):
        b.distinct = toks[i].word == "DISTINCT"
        i += 1
    if _at(toks, i) and toks[i].word == "TOP":
        b.top = True
        i += 1
        if _is_op(_at(toks, i), "("):
            i = _close(toks, i) + 1
        elif _at(toks, i) and toks[i].kind == "num":
            i += 1
        else:
            raise Unreadable("TOP without a number", toks[i - 1].line)
        if _at(toks, i) and toks[i].word == "PERCENT":
            i += 1
        if _at(toks, i) and toks[i].word == "WITH" and _at(toks, i + 1) and toks[i + 1].word == "TIES":
            i += 2
    clauses: list[tuple[str, int]] = []
    for j, t in _top(toks):
        if j < i:
            continue
        w = t.word
        if w in ("GROUP", "ORDER") and _at(toks, j + 1) and toks[j + 1].word == "BY":
            clauses.append((w, j))
        elif w in ("FROM", "WHERE", "HAVING", "OPTION", "INTO", "OFFSET", "WINDOW"):
            clauses.append((w, j))
        elif w == "FOR" and not (clauses and clauses[-1][0] == "FROM"):
            clauses.append((w, j))                                    # FOR XML / FOR JSON; FOR SYSTEM_TIME is a FROM matter
    parts = {}
    ends = [j for _, j in clauses] + [len(toks)]
    b.select = toks[i:ends[0]]
    for (w, j), end in zip(clauses, ends[1:]):
        if w in parts:
            raise Unreadable(f"{w} twice in one SELECT", toks[j].line)
        skip = 2 if w in ("GROUP", "ORDER") else 1
        parts[w] = toks[j + skip:end]
    if "INTO" in parts:
        raise Unreadable("SELECT ... INTO", toks[0].line)
    if "WINDOW" in parts:
        raise Unreadable("a WINDOW clause", toks[0].line)
    if "FROM" in parts:
        _parse_from(b, parts["FROM"])
    if "WHERE" in parts:
        _conditions(b, parts["WHERE"])
        _subqueries(b, parts["WHERE"])
    b.group = parts.get("GROUP", [])
    for name in ("GROUP", "HAVING", "ORDER"):
        if name in parts:
            _subqueries(b, parts[name])
    _subqueries(b, b.select)
    for name in ("SELECT", "HAVING", "ORDER"):
        _find_sums(b, b.select if name == "SELECT" else parts.get(name, []))
    return b


def _subqueries(b: Block, toks: list[Tok]) -> None:
    """Each (SELECT ...) inside an expression, as blocks of its own."""
    i = 0
    while i < len(toks):
        if _is_op(toks[i], "("):
            j = _close(toks, i)
            inner = toks[i + 1:j]
            if inner and inner[0].word in ("SELECT", "WITH"):
                b.children.append(parse_query(inner))
            else:
                _subqueries(b, inner)
            i = j + 1
        else:
            i += 1


def _without_subqueries(toks: list[Tok]) -> list[Tok]:
    out, i = [], 0
    while i < len(toks):
        if _is_op(toks[i], "("):
            j = _close(toks, i)
            inner = toks[i + 1:j]
            if inner and inner[0].word in ("SELECT", "WITH"):
                out.append(Tok("sub", "(subquery)", toks[i].line))
            else:
                out += [toks[i]] + _without_subqueries(inner) + [toks[j]]
            i = j + 1
        else:
            out.append(toks[i])
            i += 1
    return out


def _find_sums(b: Block, toks: list[Tok]) -> None:
    toks = _without_subqueries(toks)
    for i, t in enumerate(toks):
        if t.word == "SUM" and _is_op(_at(toks, i + 1), "("):
            j = _close(toks, i + 1)
            arg = toks[i + 2:j]
            distinct = bool(arg) and arg[0].word == "DISTINCT"
            if arg and arg[0].word in ("ALL", "DISTINCT"):
                arg = arg[1:]
            window = bool(_at(toks, j + 1)) and toks[j + 1].word == "OVER"
            b.sums.append((toks[i:j + 1], t.line, distinct, window, arg))


def _name_at(toks: list[Tok], i: int) -> tuple[list[str], int]:
    """A dotted name starting at i: ([parts], index after it). Empty parts stand for db..table."""
    parts = []
    if not (_at(toks, i) and toks[i].kind in ("id", "qid")):
        raise Unreadable(f"expected a name, found {toks[i].text if _at(toks, i) else 'the end'}",
                         toks[i].line if _at(toks, i) else None)
    parts.append(toks[i].name)
    i += 1
    while _is_op(_at(toks, i), "."):
        if _is_op(_at(toks, i + 1), "."):
            parts.append("")
            i += 1
            continue
        if not (_at(toks, i + 1) and toks[i + 1].kind in ("id", "qid")):
            raise Unreadable("a name ends with a dot", toks[i].line)
        parts.append(toks[i + 1].name)
        i += 2
    return parts, i


def _alias_at(toks: list[Tok], i: int) -> tuple[str | None, int]:
    if _at(toks, i) and toks[i].word == "AS":
        if not (_at(toks, i + 1) and toks[i + 1].kind in ("id", "qid", "str")):
            raise Unreadable("AS without an alias", toks[i].line)
        return toks[i + 1].name.strip("'"), i + 2
    t = _at(toks, i)
    if t is not None and (t.kind == "qid" or (t.kind == "id" and t.word not in _KEYWORDS)):
        return t.name, i + 1
    return None, i


def _parse_from(b: Block, toks: list[Tok]) -> None:
    for _, t in _top(toks):
        if t.word in _UNSUPPORTED_FROM:
            raise Unreadable(f"{_UNSUPPORTED_FROM[t.word]} in FROM", t.line)
    i, first = 0, True
    while i < len(toks):
        kind = "comma"
        if not first:
            t = toks[i]
            if _is_op(t, ","):
                i += 1
            else:
                words = []
                while _at(toks, i) and toks[i].word in _JOIN_WORDS | {"LOOP", "HASH", "MERGE", "REMOTE"}:
                    words.append(toks[i].word)
                    i += 1
                    if words[-1] == "JOIN":
                        break
                if not words or words[-1] != "JOIN":
                    raise Unreadable(f"unexpected {t.text} in FROM", t.line)
                if set(words) & {"LOOP", "HASH", "MERGE", "REMOTE"}:
                    raise Unreadable("a join hint", t.line)
                kind = "cross" if "CROSS" in words else "join"
        start = i
        src, i = _source(b, toks, i)
        if kind == "join":
            if not (_at(toks, i) and toks[i].word == "ON"):
                raise Unreadable("a join without ON right after its table (nested joins are not read)",
                                 toks[i].line if _at(toks, i) else toks[start].line)
            j = i + 1
            for k, t in _top(toks[j:]):
                if t.word in ("LEFT", "RIGHT") and _is_op(_at(toks, j + k + 1), "("):
                    continue                                            # LEFT(x, 3): the function
                if _is_op(t, ",") or t.word in _JOIN_WORDS:
                    end = j + k
                    break
            else:
                end = len(toks)
            cond = toks[j:end]
            if not cond:
                raise Unreadable("ON without a condition", toks[i].line)
            _conditions(b, cond)
            _subqueries(b, cond)
            b.joins.append((src, toks[start:end]))
            i = end
        else:
            b.joins.append((src, []))
        first = False


def _source(b: Block, toks: list[Tok], i: int) -> tuple[Source, int]:
    t = toks[i]
    if _is_op(t, "("):
        j = _close(toks, i)
        inner = toks[i + 1:j]
        if not inner or inner[0].word not in ("SELECT", "WITH"):
            raise Unreadable("a parenthesised join in FROM", t.line)
        blocks = parse_query(inner)
        b.children.append(blocks)
        alias, k = _alias_at(toks, j + 1)
        if alias is None:
            raise Unreadable("a derived table without an alias", t.line)
        if _is_op(_at(toks, k), "("):
            raise Unreadable("a derived table with a column list", t.line)
        s = Source(alias, t.line, toks[i:k])
        s.derived = True
        s._blocks = blocks
        b.sources.append(s)
        return s, k
    if t.kind not in ("id", "qid") or t.word in _KEYWORDS:
        raise Unreadable(f"unexpected {t.text} in FROM", t.line)
    parts, k = _name_at(toks, i)
    if _is_op(_at(toks, k), "("):
        raise Unreadable(f"a table-valued function in FROM ({'.'.join(parts)})", t.line)
    alias, k = _alias_at(toks, k)
    if _at(toks, k) and toks[k].word == "WITH" and _is_op(_at(toks, k + 1), "("):
        k = _close(toks, k + 1) + 1                                    # table hints: WITH (NOLOCK)
    s = Source(alias or parts[-1], t.line, toks[i:k])
    s.parts = parts
    b.sources.append(s)
    return s, k


def _ref(toks: list[Tok]) -> tuple | None:
    """A column reference [qualifier.]column as a tuple of lower-cased parts, or None."""
    if not toks or any(not (t.kind in ("id", "qid") or _is_op(t, ".")) for t in toks):
        return None
    try:
        parts, k = _name_at(toks, 0)
    except Unreadable:
        return None
    if k != len(toks) or toks[0].word in _KEYWORDS or "" in parts:
        return None
    return tuple(p.lower() for p in parts)


def _conditions(b: Block, toks: list[Tok]) -> None:
    """column = column and column = literal at the top level of an AND chain; under an OR nothing is taken.
    Every `column IS NULL`, under an OR or not, is kept apart."""
    for i, t in enumerate(toks):
        if t.word == "IS" and _at(toks, i + 1) and toks[i + 1].word == "NULL":
            j = i
            while j > 0 and (toks[j - 1].kind in ("id", "qid") or _is_op(toks[j - 1], ".")):
                j -= 1
            r = _ref(toks[j:i])
            if r:
                b.is_null.append(r)
    if any(t.word == "OR" for _, t in _top(toks)):
        return
    pieces, start = [], 0
    between = False
    for i, t in _top(toks):
        if t.word == "BETWEEN":
            between = True
        elif t.word == "AND":
            if between:
                between = False
                continue
            pieces.append(toks[start:i])
            start = i + 1
    pieces.append(toks[start:])
    for p in pieces:
        while len(p) >= 2 and _is_op(p[0], "(") and _close(p, 0) == len(p) - 1:
            p = p[1:-1]
        eq = [k for k, t in _top(p) if _is_op(t, "=")]
        if len(eq) != 1:
            continue
        left, right = p[:eq[0]], p[eq[0] + 1:]
        lr, rr = _ref(left), _ref(right)
        lit = lambda x: len(x) == 1 and x[0].kind in ("str", "num") or (len(x) == 2 and _is_op(x[0], "-") and x[1].kind == "num")
        if lr and rr:
            b.equal.append((lr, rr))
        elif lr and lit(right):
            b.bound_literal.append(lr)
        elif rr and lit(left):
            b.bound_literal.append(rr)


def _refs(toks: list[Tok]) -> list[tuple[tuple, int]]:
    """Column references in an expression, with their line: names not followed by '(' and not keywords or type names."""
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        if t.kind in ("id", "qid") and not (t.kind == "id" and (t.word in _KEYWORDS or t.word in _TYPES)):
            try:
                parts, k = _name_at(toks, i)
            except Unreadable:
                i += 1
                continue
            if _is_op(_at(toks, k), "("):                              # a function call
                i = k
                continue
            if i > 0 and toks[i - 1].word == "AS":                    # CAST(x AS type), a column alias
                i = k
                continue
            out.append((tuple(p.lower() for p in parts), t.line))
            i = k
        else:
            i += 1
    return out


# ------------------------------------------------------------------ meaning --------------------------------------------

class _Ctx:
    def __init__(self, plan: Plan, view_schema: str):
        self.plan = plan
        self.schema = plan.schema.schema.lower()
        self.view_schema = (view_schema or "").lower()
        self.tables = {t.name.lower(): t for t in plan.schema}

    def table(self, parts: list[str]) -> str | None:
        """The plan table a name in FROM reads, when that is certain; None for anything else."""
        if len(parts) > 2 or not parts[-1]:
            return None                                                 # db.schema.table: another database, maybe
        t = self.tables.get(parts[-1].lower())
        if t is None:
            return None
        if len(parts) == 2:
            return t.name if parts[0].lower() == self.schema else None
        # an unqualified name in a view resolves in the view's own schema first, then in dbo: certain only when the
        # view is in the source's schema (a table of the same name in the view's schema would come first otherwise)
        return t.name if self.view_schema in ("", self.schema) else None

    def columns(self, table: str) -> dict[str, str]:
        return {c.name.lower(): c.name for c in self.plan.schema[table].columns}

    def key(self, table: str) -> list[str]:
        return [c.lower() for c in self.plan.keys.get(table, ([], ""))[0]]


def _describe(ctx: _Ctx, s: Source) -> None:
    """What a source's rows are: a plan table's rows, a derived table over one plan table (its rows or grouped), or unknown."""
    if not s.derived:
        s.table = ctx.table(s.parts)
        if s.table:
            s.grain = "rows"
            s.columns = {c: c for c in ctx.columns(s.table)}
        return
    blocks = s._blocks
    if len(blocks) != 1:
        return
    d = blocks[0]
    if len(d.sources) != 1 or d.sources[0].derived or d.top:
        s.columns = _exposed(d, None, ctx)
        return
    inner = d.sources[0]
    _describe(ctx, inner)
    if inner.table is None:
        s.columns = _exposed(d, None, ctx)
        return
    s.table = inner.table
    s.columns = _exposed(d, inner, ctx)
    aggregated = any(True for _ in d.sums) or any(t.word in ("COUNT", "MIN", "MAX", "AVG", "COUNT_BIG") for t in d.select)
    if d.group:
        cols = []
        for piece in _split_commas(d.group):
            r = _ref(piece)
            if r is None or (len(r) == 2 and r[0] not in (inner.alias.lower(), inner.table.lower())) or len(r) > 2:
                return                                                  # grouped by an expression: grain unknown
            exposed = [k for k, v in (s.columns or {}).items() if v == r[-1]]
            if not exposed:
                return                                                  # grouped by a column the derived table hides
            cols.append(exposed[0])
        s.grain, s.group = "grouped", cols
    elif d.distinct or aggregated:
        return
    else:
        s.grain = "rows"


def _split_commas(toks: list[Tok]) -> list[list[Tok]]:
    out, start = [], 0
    for i, t in _top(toks):
        if _is_op(t, ","):
            out.append(toks[start:i])
            start = i + 1
    out.append(toks[start:])
    return [p for p in out if p]


def _exposed(d: Block, inner: Source | None, ctx: _Ctx) -> dict[str, str | None] | None:
    """Exposed column name -> the column of the inner table it is (None when computed); None when not known (*)."""
    out: dict[str, str | None] = {}
    for item in _split_commas(d.select):
        if len(item) == 1 and _is_op(item[0], "*") or (len(item) >= 2 and _is_op(item[-1], "*")):
            if inner is None or inner.table is None:
                return None
            out.update({c: c for c in ctx.columns(inner.table)})
            continue
        alias = None
        if len(item) >= 3 and item[-2].word == "AS":
            alias, item = item[-1].name.strip("'").lower(), item[:-2]
        elif len(item) >= 3 and _is_op(item[1], "=") and item[0].kind in ("id", "qid", "str"):
            alias, item = item[0].name.strip("'").lower(), item[2:]
        elif len(item) >= 2 and item[-1].kind in ("id", "qid") and item[-1].word not in _KEYWORDS and not _is_op(item[-2], "."):
            alias, item = item[-1].name.lower(), item[:-1]
        r = _ref(item)
        col = None
        if r and inner is not None and inner.table and (len(r) == 1 or (len(r) == 2 and r[0] in (inner.alias.lower(), inner.table.lower()))):
            col = r[-1] if r[-1] in ctx.columns(inner.table) else None
        name = alias or (r[-1] if r else None)
        if name is None:
            continue                                                    # an unnamed expression cannot be referenced
        out[name] = col
    return out


def _resolve(b: Block, ref: tuple) -> list[tuple[Source, str]] | None:
    """(source, exposed column) for a reference; [] when it is certainly not a column of any source of the block
    (an outer reference), several when ambiguous, None when a source's columns are not known."""
    col = ref[-1]
    if len(ref) >= 2:
        q = ref[-2]
        return [(s, col) for s in b.sources if s.alias.lower() == q]
    hits, unknown = [], False
    for s in b.sources:
        if s.columns is None:
            unknown = True
        elif col in s.columns:
            hits.append((s, col))
    if unknown and len(hits) <= 1:
        return None
    return hits


def _bound(b: Block, s: Source, col: str) -> bool:
    """The exposed column `col` of `s` is equal to a literal or to a column of another source of the block."""
    for r in b.bound_literal:
        got = _resolve(b, r)
        if got and len(got) == 1 and got[0] == (s, col):
            return True
    for left, right in b.equal:
        for this, other in ((left, right), (right, left)):
            got, there = _resolve(b, this), _resolve(b, other)
            if got and len(got) == 1 and got[0] == (s, col) and there and len(there) == 1 and there[0][0] is not s:
                return True
    return False


def _joined_on(b: Block, line: Source, header: Source, pairs: list[tuple[str, str]]) -> bool:
    """Every (line column, header column) of the relationship equal between the two sources."""
    def exposed(s: Source, col: str) -> str | None:
        return next((k for k, v in (s.columns or {}).items() if v == col.lower()), None)
    for lc, hc in pairs:
        le, he = exposed(line, lc), exposed(header, hc)
        if le is None or he is None:
            return False
        ok = False
        for left, right in b.equal:
            a, c = _resolve(b, left), _resolve(b, right)
            if a and c and len(a) == 1 and len(c) == 1 and {a[0], c[0]} == {(line, le), (header, he)}:
                ok = True
        if not ok:
            return False
    return True


def _at_most_one(ctx: _Ctx, b: Block, s: Source) -> bool:
    """`s` adds at most one row per row of the rest: joined on its whole key (or on every column it is grouped by)."""
    if s.grain == "rows" and s.table:
        key = ctx.key(s.table)
        if not key:
            return False
        names = []
        for k in key:
            e = next((x for x, v in (s.columns or {}).items() if v == k), None)
            if e is None:
                return False
            names.append(e)
        return all(_bound(b, s, n) for n in names)
    if s.grain == "grouped":
        return all(_bound(b, s, c) for c in s.group)
    return False


def _join_text(b: Block, s: Source, h: Source, pairs: list[tuple[str, str]]) -> tuple[str, int]:
    """The join as written (literals as ?); for a comma join, the table and the equalities of its WHERE."""
    toks = next((t for src, t in b.joins if src is s), [])
    if toks:
        return _shown(toks), s.line
    other = next((t for src, t in b.joins if src is h), [])
    if other:                                                           # the line table first, the header joined to it
        return f"{_shown(s.toks)} joined by {_shown(other)}", h.line
    on = " AND ".join(f"{s.alias}.{lc} = {h.alias}.{hc}" for lc, hc in pairs)
    return f"{_shown(s.toks)} (comma join; WHERE {on})", s.line


def _judge(ctx: _Ctx, b: Block, findings: list[dict], flagged: list, unread: list) -> None:
    for s in b.sources:
        _describe(ctx, s)
    for sum_toks, line, distinct, window, arg in b.sums:
        hits = []                                                       # (finding, header source, amount column)
        names = {c.lower() for f in findings for c in f["amount_columns"]}
        for ref, _ in _refs(arg):
            got = _resolve(b, ref)
            if got is None:
                if ref[-1] in names:
                    unread.append((f"{_shown(sum_toks)} names {ref[-1]}, and a source of its FROM has columns that are not "
                                   "known, so which table it comes from is not certain", line))
                continue
            if len(got) > 1:
                if ref[-1] in names:
                    unread.append((f"{_shown(sum_toks)}: {ref[-1]} is in more than one source of the FROM", line))
                continue
            if not got:
                if ref[-1] in names and len(ref) >= 2:
                    unread.append((f"{_shown(sum_toks)} refers to {'.'.join(ref[:-1])}, which is not in its FROM "
                                   "(an outer query's table is not followed)", line))
                continue
            s, col = got[0]
            base = (s.columns or {}).get(col)
            if not s.table or base is None or s.grain != "rows":
                if ref[-1] in names and s.derived:
                    unread.append((f"{_shown(sum_toks)} sums {col} of the derived table {s.alias}, whose rows are not known", line))
                continue
            for f in findings:
                if f["header"].lower() == s.table.lower() and base in {c.lower() for c in f["amount_columns"]}:
                    hits.append((f, s, ctx.columns(s.table)[base]))
        if hits:
            mixed = sorted({".".join(r) for r, _ in _refs(arg) if (g := _resolve(b, r)) is None or len(g) != 1
                            or g[0][0] not in {h for _, h, _ in hits}})
            if mixed:                                                   # quantity × price: a line amount, maybe
                unread.append((f"{_shown(sum_toks)} combines a header amount with {', '.join(mixed)}; such an "
                               "expression is not judged", line))
                continue
        for f, hs, amount in hits:
            if distinct:
                unread.append((f"{_shown(sum_toks)}: SUM(DISTINCT ...) over a header amount is not judged", line))
                continue
            if window:
                unread.append((f"{_shown(sum_toks)}: a window SUM (OVER) is not judged", line))
                continue
            doubled, unclear = [], []
            for o in b.sources:
                if o is hs or _at_most_one(ctx, b, o):
                    continue
                pairs = list(zip(f["line_columns"], f["header_columns"]))
                if o.table and o.table.lower() == f["line"].lower() and o.grain == "rows" and _joined_on(b, o, hs, pairs):
                    doubled.append(o)
                else:
                    unclear.append(o)
            nulls = [o for o in doubled if any((g := _resolve(b, r)) and len(g) == 1 and g[0][0] is o for r in b.is_null)]
            if nulls:
                unread.append((f"{_shown(sum_toks)} sums {f['header']}.{amount} after a join to {f['line']} with a "
                               f"condition IS NULL on {nulls[0].alias} (an anti-join, maybe); not judged", line))
                continue
            for o in doubled:
                join, jline = _join_text(b, o, hs, pairs)
                flagged.append({"amount": f"{f['header']}.{amount}", "line_table": f["line"],
                                "relationship": f"{f['line']}.{'+'.join(f['line_columns'])} → {f['header']}.{'+'.join(f['header_columns'])}",
                                "join": join, "join_line": jline, "sum": _shown(sum_toks), "line": line})
            if not doubled and unclear:
                o = unclear[0]
                what = (f"the derived table {o.alias}" if o.derived else ".".join(p for p in o.parts if p))
                why = ("its rows per row are not known" if o.table is None or o.grain == "unknown"
                       else f"it is not joined on its whole key" + (f" nor on {f['line']}'s relationship columns" if o.table.lower() == f["line"].lower() else ""))
                unread.append((f"{_shown(sum_toks)} sums {f['header']}.{amount} after a join to {what}, which may repeat "
                               f"{f['header']} rows: {why}", line))
    for child in b.children:
        for cb in child:
            _judge(ctx, cb, findings, flagged, unread)


# ------------------------------------------------------------------ the check ------------------------------------------

def _row(r) -> tuple[str, str, str | None]:
    if hasattr(r, "keys"):
        d = {str(k).lower(): r[k] for k in r.keys()}
        return str(d.get("view_schema") or ""), str(d.get("view_name") or ""), d.get("view_definition")
    a = (list(r) + [None] * 3)[:3]
    return str(a[0] or ""), str(a[1] or ""), a[2]


def _names(toks: list[Tok]) -> set[str]:
    return {t.name.lower() for t in toks if t.kind in ("id", "qid")}


def check_view(plan: Plan, schema: str, name: str, definition: str | None, findings: list[dict] | None = None,
               truncated_at: int | None = None) -> dict:
    """One view: {"view", "status": flagged | not_flagged | could_not_be_read | not_relevant, ...}."""
    findings = header_amounts(plan) if findings is None else findings
    view = f"{schema}.{name}" if schema else name
    if definition is None:
        return {"view": view, "status": "could_not_be_read",
                "reason": "the definition is not available (encrypted, or no permission to see it)", "line": None}
    if truncated_at and len(definition) >= truncated_at:
        return {"view": view, "status": "could_not_be_read", "line": None,
                "reason": f"INFORMATION_SCHEMA.VIEWS gives the first {truncated_at} characters only; the definition may be cut there"}
    try:
        toks = tokens(definition)
    except Unreadable as e:
        return {"view": view, "status": "could_not_be_read", "reason": e.reason, "line": e.line}
    headers = {f["header"].lower() for f in findings}
    if not (_names(toks) & headers):
        return {"view": view, "status": "not_relevant"}
    try:
        blocks = parse_query(view_body(toks))
        flagged, unread = [], []
        ctx = _Ctx(plan, schema)
        for b in blocks:
            _judge(ctx, b, findings, flagged, unread)
    except Unreadable as e:
        return {"view": view, "status": "could_not_be_read", "reason": e.reason, "line": e.line}
    except (IndexError, KeyError, ValueError, AttributeError, TypeError, RecursionError):
        # syntax the parser did not expect in a place it did not check: not read, never guessed
        return {"view": view, "status": "could_not_be_read", "reason": "syntax the parser does not read", "line": None}
    if flagged:
        out = {"view": view, "status": "flagged", "flagged": flagged}
        if unread:
            out["also_not_read"] = [{"reason": r, "line": ln} for r, ln in unread]
        return out
    if unread:
        r, ln = unread[0]
        return {"view": view, "status": "could_not_be_read", "reason": r, "line": ln,
                **({"more": [{"reason": x, "line": y} for x, y in unread[1:]]} if len(unread) > 1 else {})}
    return {"view": view, "status": "not_flagged"}


def check(plan: Plan, rows, read_with: str = DEFINITIONS_SQL) -> dict:
    """Every view definition in `rows` (dicts or tuples: view schema, view name, definition) against the plan's header
    amounts (amounts.header_amounts, no query)."""
    findings = header_amounts(plan)
    truncated_at = INFO_LIMIT if read_with == DEFINITIONS_SQL_INFO else None
    results = [check_view(plan, s, n, d, findings, truncated_at) for s, n, d in (_row(r) for r in rows)]
    flagged = [x for x in results if x["status"] == "flagged"]
    unread = [x for x in results if x["status"] == "could_not_be_read"]
    clean = [x["view"] for x in results if x["status"] == "not_flagged"]
    other = sum(1 for x in results if x["status"] == "not_relevant")
    entries = [{"view": x["view"], **e,
                "do_instead": (f"Sum {e['amount']} on {e['amount'].split('.')[0]} itself (one row per {e['amount'].split('.')[0]} "
                               f"row) and join the result, or sum an amount of {e['line_table']}: {LEVELS}.")}
               for x in flagged for e in x["flagged"]]
    if not findings:
        summary = (f"{len(results)} view definition(s) read; the plan has no header amount that a join repeats, so there is "
                   "nothing to look for")
    else:
        summary = (f"{len(results)} view definition(s) read, {len(results) - other} naming a header table "
                   f"({', '.join(sorted({f['header'] for f in findings}))}): {len(flagged)} flagged "
                   f"({len(entries)} SUM(s) of a header amount after a join to its line table), {len(clean)} read and not "
                   f"flagged, {len(unread)} could not be read")
    out = {"summary": summary, "rule": RULE, "read": read_with,
           "header_amounts": [{"amount": f"{f['header']}.{c}", "line_table": f["line"]} for f in findings for c in f["amount_columns"]],
           "flagged": entries[:MAX_LISTED],
           "could_not_be_read": [{k: v for k, v in x.items() if k != "status"} for x in unread][:MAX_LISTED],
           "read_not_flagged": clean[:MAX_LISTED],
           "views": {"read": len(results), "naming_a_header_table": len(results) - other, "flagged": len(flagged),
                     "not_flagged": len(clean), "could_not_be_read": len(unread)}}
    if len(entries) > MAX_LISTED or len(unread) > MAX_LISTED or len(clean) > MAX_LISTED:
        out["listed"] = f"at most {MAX_LISTED} entries per list; the counts under views are complete"
    out["note"] = ("Read from the view definitions only, no rows: a flagged view sums a header amount over the rows of a join "
                   "with its line table; whether a report reads that column is not known here. A view that could not be "
                   "read is not judged either way. String and number literals in the SQL shown are replaced by ?. "
                   "Notebooks are not read.")
    return out


def read(execute) -> tuple[list, str | None, str | None]:
    """The view definitions on the connection: (rows, the query that read them, error). sys.sql_modules first, then
    INFORMATION_SCHEMA.VIEWS; read-only."""
    try:
        return list(execute(DEFINITIONS_SQL)), DEFINITIONS_SQL, None
    except Exception:                                                   # noqa: BLE001 - try the INFORMATION_SCHEMA view
        try:
            return list(execute(DEFINITIONS_SQL_INFO)), DEFINITIONS_SQL_INFO, None
        except Exception as e:                                          # noqa: BLE001
            from .amounts import readable_count_error
            return [], None, readable_count_error(e).replace("counting query", "query for the view definitions") \
                .replace("; the rows per header are not known", "")


def check_connection(plan: Plan, execute) -> dict:
    """read() then check(); when nothing could be read, says so instead of a 0."""
    rows, used, error = read(execute)
    if used is None:
        return {"summary": f"the view definitions could not be read: {error}", "rule": RULE, "read": None, "error": error,
                "note": "No view was judged."}
    return check(plan, rows, used)
