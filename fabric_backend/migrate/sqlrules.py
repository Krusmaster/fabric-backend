"""View SQL from Snowflake or Databricks against Fabric T-SQL: the constructs found, a translation by fixed rules for
the simple ones, "manual" for the rest (round MG1). No model, no guessing: every rewrite is a regular expression with
a name, and the same input always gives the same output. A view gets a T-SQL draft only when every construct found in
it is translated or supported as it is; otherwise it is "manual" and lists why, with the line.

The target is T-SQL as the Fabric SQL analytics endpoint and Warehouse take it. What Fabric supports is read from
Microsoft's page "T-SQL surface area in Fabric Data Warehouse"
(https://learn.microsoft.com/en-us/fabric/data-warehouse/tsql-surface-area, ms.date 16 September 2026, read 16
November 2026): QUALIFY, GROUP BY ALL and MERGE (Warehouse) are supported; recursive queries are listed as not supported.
The source-side meaning of a function (Snowflake IFF, NVL, ...) is the usual one and is not re-read here: Snowflake's
pages could not be opened from this session. A draft is a draft: run it and compare (the before/after report does).
"""
from __future__ import annotations

import re

TSQL_PAGE = "https://learn.microsoft.com/en-us/fabric/data-warehouse/tsql-surface-area"

_TYPES = {
    "STRING": "varchar(8000)", "TEXT": "varchar(8000)", "VARCHAR": "varchar(8000)", "CHAR": "char(1)",
    "INT": "int", "INTEGER": "int", "BIGINT": "bigint", "SMALLINT": "smallint", "TINYINT": "smallint",
    "NUMBER": "decimal(38,0)", "NUMERIC": "decimal(38,0)", "DECIMAL": "decimal(38,0)",
    "FLOAT": "float", "DOUBLE": "float", "REAL": "real",
    "DATE": "date", "TIMESTAMP": "datetime2(6)", "TIMESTAMP_NTZ": "datetime2(6)", "DATETIME": "datetime2(6)",
    "BOOLEAN": "bit", "BOOL": "bit", "BINARY": "varbinary(8000)",
}
_SEMI = ("VARIANT", "OBJECT", "ARRAY", "MAP", "STRUCT", "GEOGRAPHY", "GEOMETRY", "TIMESTAMP_TZ", "TIMESTAMP_LTZ", "INTERVAL")


def tsql_type(t: str) -> str | None:
    """A source type as a Fabric T-SQL type for CAST, or None when there is no plain counterpart."""
    m = re.match(r"^\s*([A-Za-z_]+)\s*(?:\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\))?\s*$", t or "")
    if not m:
        return None
    base, p, s = m.group(1).upper(), m.group(2), m.group(3)
    if base in _SEMI:
        return None
    if base in ("NUMBER", "NUMERIC", "DECIMAL") and p:
        return f"decimal({p},{s or 0})"
    if base in ("VARCHAR", "STRING", "TEXT") and p:
        return f"varchar({p})"
    if base == "CHAR" and p:
        return f"char({p})"
    return _TYPES.get(base)


# ---------------------------------------------------------------------------------------------------------- masking

_LIT = re.compile(r"'(?:[^']|'')*'")


def _strip_comments(sql: str) -> str:
    """Comments to blanks of the same length (newlines kept), outside string literals."""
    out, i, n = [], 0, len(sql)
    while i < n:
        c = sql[i]
        if c == "'":
            j = i + 1
            while j < n and not (sql[j] == "'" and (j + 1 >= n or sql[j + 1] != "'")):
                j += 2 if sql[j] == "'" else 1
            out.append(sql[i:j + 1]); i = j + 1
        elif sql.startswith("--", i):
            j = sql.find("\n", i); j = n if j < 0 else j
            out.append(" " * (j - i)); i = j
        elif sql.startswith("/*", i):
            j = sql.find("*/", i + 2); j = n if j < 0 else j + 2
            out.append(re.sub(r"[^\n]", " ", sql[i:j])); i = j
        else:
            out.append(c); i += 1
    return "".join(out)


def _blank_literals(sql: str) -> str:
    """String literals with their content as x's (same length, newlines kept): for finding constructs and lines."""
    return _LIT.sub(lambda m: "'" + re.sub(r"[^\n]", "x", m.group(0)[1:-1]) + "'", sql)


def _tokens(sql: str) -> tuple[str, list[str]]:
    lits: list[str] = []

    def keep(m):
        lits.append(m.group(0))
        return f"\x00{len(lits) - 1}\x00"
    return _LIT.sub(keep, sql), lits


def _untokens(sql: str, lits: list[str]) -> str:
    return re.sub(r"\x00(\d+)\x00", lambda m: lits[int(m.group(1))], sql)


# ---------------------------------------------------------------------------------------------------------- the rules

_ID = r"[A-Za-z_][\w$]*"
_QID = rf"(?:{_ID}|\[[^\]]+\]|\"[^\"]+\")(?:\.(?:{_ID}|\[[^\]]+\]|\"[^\"]+\"))*"
_SIMPLE_ARG = r"(?:[^(),]|\([^()]*\))+?"      # no comma at the top level; one level of parentheses

# (construct, regex on the masked SQL, sources, note): found means the view needs a person
MANUAL = [
    ("FLATTEN (semi-structured to rows)", r"\bFLATTEN\s*\(", ("snowflake",), "T-SQL has OPENJSON; the rewrite depends on the data's shape"),
    ("LATERAL VIEW / explode", r"\bLATERAL\s+VIEW\b|\b(?:pos)?explode(?:_outer)?\s*\(|\binline(?:_outer)?\s*\(", ("databricks",),
     "arrays to rows; T-SQL has OPENJSON over JSON text, not arrays"),
    ("semi-structured construction or parsing",
     r"\b(?:PARSE_JSON|TRY_PARSE_JSON|OBJECT_CONSTRUCT\w*|ARRAY_CONSTRUCT\w*|OBJECT_AGG|TO_VARIANT|TO_OBJECT|TO_ARRAY|from_json|to_json|named_struct|parse_json)\s*\(",
     ("snowflake", "databricks"), "VARIANT, OBJECT, ARRAY, STRUCT and MAP have no persisted Fabric Warehouse type (JSON as varchar)"),
    ("array aggregation", r"\b(?:ARRAY_AGG|collect_list|collect_set|ARRAY_UNIQUE_AGG)\s*\(", ("snowflake", "databricks"),
     "returns an array; T-SQL has STRING_AGG or JSON functions, with different semantics"),
    ("time travel", r"\b(?:AT|BEFORE)\s*\(\s*(?:TIMESTAMP|OFFSET|STATEMENT|STREAM)\s*=>|\b(?:VERSION|TIMESTAMP)\s+AS\s+OF\b|@v\d+\b",
     ("snowflake", "databricks"), "a past version of a table; decide what the view should read in Fabric"),
    ("recursive query", r"\bCONNECT\s+BY\b|\bWITH\s+RECURSIVE\b", ("snowflake", "databricks"),
     "recursive queries are listed as not supported on the T-SQL surface area page"),
    ("sequence", r"\.NEXTVAL\b|\bSEQ[1248]\s*\(", ("snowflake",), "no sequence in a Fabric view"),
    ("MATCH_RECOGNIZE", r"\bMATCH_RECOGNIZE\b", ("snowflake",), "no counterpart"),
    ("PIVOT / UNPIVOT", r"\b(?:UN)?PIVOT\s*\(", ("snowflake", "databricks"), "T-SQL has PIVOT with a different syntax"),
    ("ILIKE / RLIKE / regular expression", r"\bILIKE\b|\bRLIKE\b|\bREGEXP\b|\bREGEXP_\w+\s*\(", ("snowflake", "databricks"),
     "case and pattern semantics differ; Fabric's collation is case-sensitive by default and its regular expression functions are a preview"),
    ("NVL2 / DECODE", r"\b(?:NVL2|DECODE)\s*\(", ("snowflake", "databricks"), "NULL handling differs from a CASE written naively"),
    ("sampling", r"\bSAMPLE\s*\(|\bTABLESAMPLE\b", ("snowflake", "databricks"), "not row-for-row reproducible"),
    ("stage or positional column", r"@~?[A-Za-z_]\w*/|@~|(?<![\w$])\$\d+\b", ("snowflake",), "reads files from a stage"),
    ("lambda / higher-order function", r"\b(?:transform|aggregate|exists|forall|zip_with|map_filter)\s*\(|\w+\s*->", ("databricks",),
     "no lambda in T-SQL"),
    ("LISTAGG DISTINCT", r"\bLISTAGG\s*\(\s*DISTINCT\b", ("snowflake",), "STRING_AGG has no DISTINCT"),
    ("semi-structured path with an index", r"(?<!:):(?!:)\s*[\w.]*\[", ("snowflake", "databricks"), "an array index in a path"),
]

SUPPORTED = [
    ("QUALIFY", r"\bQUALIFY\b", "supported: the T-SQL surface area page lists SELECT - QUALIFY for Warehouse and the SQL analytics endpoint"),
    ("GROUP BY ALL", r"\bGROUP\s+BY\s+ALL\b", "supported: the T-SQL surface area page lists GROUP BY ALL"),
    ("MERGE", r"\bMERGE\s+INTO\b", "supported in Warehouse (generally available per the T-SQL surface area page); the SQL analytics endpoint has no DML"),
]


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _rewrites(source: str, functions: set[str]) -> list[tuple[str, re.Pattern, object, str]]:
    """(construct, pattern, replacement, rule) in the order applied, on SQL whose literals are tokens."""
    def path(m, cast=None):
        p = m.group(2)
        expr = f"JSON_VALUE({m.group(1)}, '$.{p}')"
        if cast is None:
            return expr
        t = tsql_type(cast)
        return f"CAST({expr} AS {t})" if t else None

    def path_cast(m):
        return path(m, m.group(3))

    def cast(m):
        t = tsql_type(m.group(2))
        return f"CAST({m.group(1)} AS {t})" if t else None

    rules = []
    if source == "databricks":
        rules.append(("backtick identifier", re.compile(r"`([^`]+)`"), lambda m: f"[{m.group(1)}]", "`x` -> [x]"))
    rules += [
        ("semi-structured path with a cast", re.compile(rf"({_QID})\s*(?<!:):(?!:)\s*({_ID}(?:\.{_ID})*)\s*::\s*({_ID}(?:\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))?)"),
         path_cast, "col:a.b::type -> CAST(JSON_VALUE(col, '$.a.b') AS type)"),
        ("semi-structured path", re.compile(rf"({_QID})\s*(?<!:):(?!:)\s*({_ID}(?:\.{_ID})*)\b(?!\s*\()"), path,
         "col:a.b -> JSON_VALUE(col, '$.a.b')"),
        (":: cast", re.compile(rf"({_QID}|\x00\d+\x00|\d+(?:\.\d+)?)\s*::\s*({_ID}(?:\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))?)"), cast,
         "x::type -> CAST(x AS type)"),
        ("IFF", re.compile(r"\bIFF\s*\(", re.I), "IIF(", "IFF( -> IIF("),
        ("NVL / IFNULL", re.compile(r"\b(?:NVL|IFNULL)\s*\(", re.I), "COALESCE(", "NVL( / IFNULL( -> COALESCE("),
        ("ZEROIFNULL", re.compile(rf"\bZEROIFNULL\s*\(\s*({_SIMPLE_ARG})\s*\)", re.I), lambda m: f"COALESCE({m.group(1)}, 0)",
         "ZEROIFNULL(x) -> COALESCE(x, 0)"),
        ("LISTAGG", re.compile(r"\bLISTAGG\s*\(", re.I), "STRING_AGG(", "LISTAGG( -> STRING_AGG( (WITHIN GROUP kept)"),
        ("TO_DATE with one argument", re.compile(rf"\bTO_DATE\s*\(\s*({_SIMPLE_ARG})\s*\)", re.I), lambda m: f"CAST({m.group(1)} AS date)",
         "TO_DATE(x) -> CAST(x AS date)"),
        ("CURRENT_TIMESTAMP()", re.compile(r"\bCURRENT_TIMESTAMP\s*\(\s*\)", re.I), "CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP() -> CURRENT_TIMESTAMP"),
    ]
    rules.append(("CREATE OR REPLACE VIEW", re.compile(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\b", re.I), "CREATE OR ALTER VIEW",
                  "CREATE [OR REPLACE] VIEW -> CREATE OR ALTER VIEW"))
    if source == "databricks":
        rules += [
            ("if()", re.compile(r"(?<![\w.])if\s*\(", re.I), "IIF(", "if( -> IIF("),
            ("date_add with two arguments", re.compile(rf"\bdate_add\s*\(\s*({_SIMPLE_ARG})\s*,\s*({_SIMPLE_ARG})\s*\)", re.I),
             lambda m: f"DATEADD(day, {m.group(2)}, {m.group(1)})", "date_add(d, n) -> DATEADD(day, n, d)"),
        ]
    return rules


# forms a rule did not rewrite (an argument too complex for it): found after the rewrites, the view is manual
LEFTOVER = {
    "both": [(":: cast of an expression", r"::"), ("LIMIT", r"\bLIMIT\b"), ("semi-structured path", r"(?<![:\w])(?:[A-Za-z_][\w$]*|\])\s*:(?!:)\s*[A-Za-z_]"),
             ("source function not rewritten", r"\b(?:IFF|NVL|IFNULL|ZEROIFNULL|LISTAGG|TO_DATE|TO_VARCHAR|TO_CHAR|TO_NUMBER|DATE_ADD|DATE_SUB|"
                                               r"CURRENT_DATE|SPLIT_PART|ARRAY_SIZE|DATE_TRUNC|TRUNC|DATEDIFF|ADD_MONTHS)\s*\(")],
    "snowflake": [("SECURE view", r"\bSECURE\s+VIEW\b")],
    "databricks": [("backtick identifier", r"`"), ("if()", r"(?<![\w.])if\s*\(")],
}


def _paren_casts(text: str, lits: list[str], found: list[dict]) -> str:
    """(expr)::type and f(args)::type -> CAST(f(args) AS type), with the parentheses matched; unknown types stay (and are
    then reported by LEFTOVER)."""
    while True:
        m = re.search(rf"\)\s*::\s*({_ID}(?:\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))?)", text)
        if not m:
            return text
        depth, i = 0, m.start()
        while i >= 0:
            depth += {")": 1, "(": -1}.get(text[i], 0)
            if depth == 0:
                break
            i -= 1
        t = tsql_type(m.group(1))
        line = _line(_untokens(text[:m.start()], lits), len(_untokens(text[:m.start()], lits)))
        if i < 0 or t is None:
            found.append({"construct": ":: cast of an expression", "line": line, "status": "manual",
                          "note": "the cast's type has no plain Fabric T-SQL type" if t is None else "unbalanced parentheses"})
            return text
        f = re.search(rf"({_ID})\s*$", text[:i])
        start = f.start() if f and f.group(1).upper() not in ("SELECT", "AND", "OR", "NOT", "WHERE", "ON", "WHEN", "THEN", "ELSE", "IN", "AS") else i
        text = text[:start] + f"CAST({text[start:m.start() + 1]} AS {t})" + text[m.end():]
        found.append({"construct": ":: cast", "line": line, "status": "translated", "rule": "f(x)::type / (x)::type -> CAST(... AS type)"})


def translate(sql: str, source: str, functions: list[str] | None = None, name: str = "") -> dict:
    """{view, status, constructs, tsql}. status: "no change needed", "translated by rule" or "manual"."""
    source = source.lower()
    funcs = {f.upper() for f in (functions or [])}
    clean = _strip_comments(sql or "")
    seen = _blank_literals(clean)
    found: list[dict] = []
    for construct, rx, sources, note in MANUAL:
        if source not in sources:
            continue
        for m in re.finditer(rx, seen, re.I):
            found.append({"construct": construct, "line": _line(seen, m.start()), "status": "manual", "note": note})
    for construct, rx, note in SUPPORTED:
        for m in re.finditer(rx, seen, re.I):
            found.append({"construct": construct, "line": _line(seen, m.start()), "status": "supported in Fabric", "note": note,
                          "source": TSQL_PAGE})
    for f in sorted(funcs):
        for m in re.finditer(rf"(?<![\w.\"]){re.escape(f)}\s*\(", seen, re.I):
            found.append({"construct": f"user-defined function {f}", "line": _line(seen, m.start()), "status": "manual",
                          "note": "a function the export lists as user-defined: rewrite it in Fabric or inline it"})

    text, lits = _tokens(clean)
    for construct, rx, repl, rule_text in _rewrites(source, funcs):
        out, pos, any_hit = [], 0, False
        for m in rx.finditer(text):
            new = repl(m) if callable(repl) else repl
            line = _line(_untokens(text[:m.start()], lits), len(_untokens(text[:m.start()], lits)))
            if new is None:
                found.append({"construct": construct, "line": line, "status": "manual",
                              "note": "the cast's type has no plain Fabric T-SQL type (semi-structured, time zone, interval)"})
                continue
            out.append(text[pos:m.start()]); out.append(new); pos = m.end(); any_hit = True
            found.append({"construct": construct, "line": line, "status": "translated", "rule": rule_text})
        if any_hit:
            out.append(text[pos:]); text = "".join(out)

    text = _paren_casts(text, lits, found)

    limit = re.search(r"\bLIMIT\s+(\d+)\s*;?\s*$", text, re.I)
    if limit:
        line = _line(_untokens(text, lits), len(_untokens(text[:limit.start()], lits)))
        if re.search(r"\bOFFSET\b", text, re.I) or len(re.findall(r"\bSELECT\b", text, re.I)) != 1:
            found.append({"construct": "LIMIT", "line": line, "status": "manual", "note": "LIMIT with OFFSET or over more than one SELECT"})
        else:
            text = text[:limit.start()].rstrip()
            text = re.sub(r"\bSELECT(\s+DISTINCT)?\b", lambda m: f"SELECT{m.group(1) or ''} TOP {limit.group(1)}", text, count=1, flags=re.I)
            found.append({"construct": "LIMIT", "line": line, "status": "translated", "rule": "SELECT ... LIMIT n -> SELECT TOP n ..."})

    for construct, rx in LEFTOVER.get(source, []) + LEFTOVER["both"]:
        for m in re.finditer(rx, _blank_literals(_untokens(text, lits)), re.I):
            found.append({"construct": construct, "line": _line(_untokens(text, lits), m.start()), "status": "manual",
                          "note": "left as written: no rule applies to this form (an argument too complex for the rule)"})
    uniq = {}
    for f in found:
        uniq.setdefault((f["line"], f["construct"], f["status"]), f)
    found = list(uniq.values())
    found.sort(key=lambda f: (f["line"], f["construct"]))
    manual = [f for f in found if f["status"] == "manual"]
    translated = [f for f in found if f["status"] == "translated"]
    status = "manual" if manual else ("translated by rule" if translated else "no change needed")
    return {"view": name, "status": status, "constructs": found,
            "tsql": None if manual else re.sub(r"\n[ \t]*(?=\n)", "", _untokens(text, lits)).strip(),
            "why": "; ".join(sorted({f"{f['construct']} (line {f['line']})" for f in manual})) or None}
