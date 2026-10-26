"""Build the schema fixtures from the official DDL files (see README.md in this folder).

    python tests/fixtures/schemas/extract.py <name> <ddl file> [<more ddl files>] > tests/fixtures/schemas/<name>.json

Only what the DDL declares is kept: table name (and its SQL schema), columns with their declared types in order,
the PRIMARY KEY columns, and FOREIGN KEY constraints with their referenced table and columns. Nothing is added.
Supports the T-SQL style of the five sources (CREATE TABLE with inline constraints, ALTER TABLE ... ADD
CONSTRAINT / ADD PRIMARY KEY / ADD FOREIGN KEY) — it is a fixture builder, not a SQL parser.
"""
from __future__ import annotations

import json
import re
import sys

IDENT = r'(?:\[[^\]]+\]|"[^"]+"|[A-Za-z_][A-Za-z0-9_$]*)'
QUAL = rf'{IDENT}(?:\s*\.\s*{IDENT})*'


def _clean(ident: str) -> str:
    return ident.strip().strip('[]"')


def _name(qualified: str) -> tuple[str | None, str]:
    parts = [_clean(p) for p in re.split(r"\s*\.\s*", qualified.strip())]
    return (parts[-2] if len(parts) > 1 else None), parts[-1]


def _cols(text: str) -> list[str]:
    return [_clean(c) for c in re.findall(IDENT, text)]


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", " ", sql)


def _split_top(body: str) -> list[str]:
    out, depth, cur = [], 0, []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur))
    return out


def _balanced(text: str, start: int) -> tuple[str, int]:
    """text[start] == '(' -> (inner text, index after the matching ')')."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
    raise ValueError("unbalanced parentheses")


PK_RE = re.compile(r"PRIMARY\s+KEY(?:\s+(?:NON)?CLUSTERED)?\s*\(", re.I)
FK_RE = re.compile(rf"FOREIGN\s+KEY(?:\s+{IDENT})?\s*\(([^)]*)\)\s*REFERENCES\s+({QUAL})\s*(\(([^)]*)\))?", re.I)
TYPE_RE = re.compile(rf"^\s*({IDENT})\s+(AS\b|{IDENT}(?:\s*\([^)]*\))?)", re.I)


def extract(files: list[str]) -> dict:
    tables: dict[str, dict] = {}
    for path in files:
        sql = _strip_comments(open(path, encoding="utf-8", errors="replace").read())
        for m in re.finditer(rf"CREATE\s+TABLE\s+({QUAL})\s*\(", sql, flags=re.I):
            schema, name = _name(m.group(1))
            body, _ = _balanced(sql, m.end() - 1)
            t = tables.setdefault(name, {"name": name, "schema": schema, "columns": [], "primary_key": [], "foreign_keys": []})
            for item in _split_top(body):
                s = item.strip()
                if not s:
                    continue
                head = s.upper()
                if head.startswith(("CONSTRAINT", "PRIMARY KEY", "FOREIGN KEY", "CHECK", "UNIQUE", "INDEX", "KEY ")):
                    _constraint(t, s, tables)
                    continue
                if head.startswith("PERIOD FOR"):               # system-versioned tables: PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo) is not a column
                    continue
                cm = TYPE_RE.match(s)
                if not cm:
                    continue
                col = _clean(cm.group(1))
                typ = "computed" if cm.group(2).upper() == "AS" else re.sub(r"\s+", "", _clean(cm.group(2).split("(")[0])).lower()
                t["columns"].append([col, typ])
        for m in re.finditer(rf"ALTER\s+TABLE\s+({QUAL})\s+(?:WITH\s+(?:NO)?CHECK\s+)?ADD\s+(.*?)(?:;|\bGO\b|(?=ALTER\s+TABLE)|(?=CREATE\s)|(?=COMMIT\b))",
                             sql, flags=re.I | re.S):
            _, name = _name(m.group(1))
            if name in tables:
                for piece in re.split(r",\s*(?=CONSTRAINT\b)", m.group(2), flags=re.I):
                    _constraint(tables[name], piece, tables)
    for t in tables.values():                       # a FOREIGN KEY ... REFERENCES T without columns points at T's primary key
        for fk in t["foreign_keys"]:
            if not fk["ref_columns"] and fk["ref_table"] in tables:
                fk["ref_columns"] = list(tables[fk["ref_table"]]["primary_key"])
    return {"tables": list(tables.values())}


def _constraint(t: dict, s: str, tables: dict) -> None:
    pk = PK_RE.search(s)
    if pk:
        inner, _ = _balanced(s, pk.end() - 1)
        t["primary_key"] = [c for c in _cols(re.sub(r"\b(ASC|DESC)\b", "", inner, flags=re.I))]
        return
    fk = FK_RE.search(s)
    if fk:
        _, ref = _name(fk.group(2))
        t["foreign_keys"].append({"columns": _cols(fk.group(1)), "ref_table": ref, "ref_columns": _cols(fk.group(4) or "")})


if __name__ == "__main__":
    name, files = sys.argv[1], sys.argv[2:]
    out = {"name": name, **extract(files)}
    json.dump(out, sys.stdout, indent=1)
    print()
