"""The 20-minute demo on your own laptop: `fabric-backend demo`.

One local page (127.0.0.1 only; it talks to nothing but the database or files you connect; no account, no service of ours) in the graph explorer's design, four
steps with a time budget each:

  1. Connect   a SQL Server over ODBC with a read-only sign-in, a folder of CSV / Excel files (loaded into a local
               SQLite database), a columns list, or the synthetic shop schema ("try without your own data")
  2. The map   the plan: keys and relationships with their rules, table roles, subject areas
  3. Health    validate_plan and suggest_relationships as findings: what we saw, what it means, the next step (a
               `confirmed` entry, a key, or SQL) and the evidence; Accept or Skip, the plan updates at once
  4. Value     five questions the data can answer, proposed from the graph, run locally with the SQL shown; exports
               (data dictionary, dbt tests, a Lovable prompt, the plan)

The engine is the same as the hosted connector's. Everything the page shows comes from the engine or from counting
queries against the connected source; a suggestion is never drawn as verified.
"""
from __future__ import annotations

import csv
import datetime as _dt
import json
import re
import sqlite3
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from xml.etree import ElementTree as ET

from . import evidence, graphs, paths as _paths
from .infer import RULES, Plan, PlanInputError, plan
from .schema import Schema

HOST = "127.0.0.1"                                   # the one address the demo listens on; not configurable on purpose
DEFAULT_PORT = 8765
STEPS = [  # the time budget adds up to the twenty minutes
    {"n": 1, "key": "connect", "title": "Connect", "minutes": 4, "what": "Point the demo at the customer's data. The page talks only to that database or folder."},
    {"n": 2, "key": "map", "title": "The map", "minutes": 4, "what": "Keys and relationships, each with the rule that made it. Roles and subject areas."},
    {"n": 3, "key": "health", "title": "Health check", "minutes": 7, "what": "The plan checked against the rows. Each finding: what we saw, what it means, the next step, the evidence."},
    {"n": 4, "key": "value", "title": "The value", "minutes": 5, "what": "Five questions the data can answer, run here with the SQL shown. Exports for the hand-over."},
]
ROW_CAP = 10                                         # result rows shown per question
CELL_CAP = 60                                        # characters per cell
NUMERIC = {"int", "integer", "bigint", "smallint", "tinyint", "decimal", "numeric", "float", "real", "double", "money", "smallmoney", "int64", "number"}
DATES = {"date", "datetime", "datetime2", "smalldatetime", "datetimeoffset", "timestamp", "time"}
STRINGS = {"string", "varchar", "nvarchar", "char", "nchar", "text", "ntext"}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_]+")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?$")
_INT_RE = re.compile(r"^[+-]?\d{1,18}$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+[.,]\d*|\d*[.,]\d+|\d+)([eE][+-]?\d+)?$")


# ------------------------------------------------------------------ sources ---------------------------------------

@dataclass
class Source:
    """What the demo is connected to. `execute` is None for a columns list (plan only, no counts)."""
    kind: str                                        # sample | folder | odbc | columns
    label: str
    schema: Schema
    execute: object = None
    dialect: str = "sqlite"                          # sqlite | tsql
    notes: list[str] = field(default_factory=list)
    close: object = None

    @property
    def has_data(self) -> bool:
        return self.execute is not None


def _sqlite_execute(con: sqlite3.Connection):
    """The engine writes T-SQL; SQLite needs COUNT instead of COUNT_BIG and LIMIT instead of TOP."""
    def execute(sql: str):
        cur = con.execute(sqlite_sql(sql))
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    return execute


def sqlite_sql(sql: str) -> str:
    sql = sql.replace("COUNT_BIG(", "COUNT(")
    m = re.match(r"^\s*SELECT\s+TOP\s*\(?\s*(\d+)\s*\)?\s+", sql, re.I)
    if m:
        sql = "SELECT " + sql[m.end():] + f"\nLIMIT {int(m.group(1))}"
    return sql


def sample_source() -> Source:
    """The synthetic shop schema and rows from fabric_backend.seed in an in-memory SQLite database."""
    from .seed import SCHEMAS, rows, schema
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute("ATTACH DATABASE ':memory:' AS shop")
    for name, ddl in SCHEMAS.items():
        con.execute(f"CREATE TABLE shop.[{name}] ({ddl})")
        data = [tuple(v.isoformat() if isinstance(v, (_dt.date, _dt.datetime)) else v for v in r) for r in rows()[name]]
        con.executemany(f"INSERT INTO shop.[{name}] VALUES ({','.join('?' * len(data[0]))})", data)
    return Source("sample", "Synthetic shop data (seven tables, no real company)", schema("shop"), _sqlite_execute(con), "sqlite",
                  ["Synthetic rows from fabric_backend.seed: invented shop names, no customer data."], con.close)


_IDENT_BAD = re.compile(r"[\[\]\x00-\x1f\"'`]")


def _column_name(header: str, i: int) -> str:
    """A column name SQLite and the engine's bracket quoting both accept: brackets, quotes and control characters
    become underscores (SQLite does not take the T-SQL `]]` escape inside [...])."""
    name = _IDENT_BAD.sub("_", str(header)).strip() or f"column_{i + 1}"
    return name


def _table_name(stem: str, used: set[str]) -> str:
    name = _SAFE_NAME.sub("_", stem.strip()).strip("_") or "table"
    if name[0].isdigit():
        name = "t_" + name
    base, i = name, 2
    while name.lower() in used:                                     # SQLite compares table names without case
        name, i = f"{base}_{i}", i + 1
    used.add(name.lower())
    return name


def _guess_type(values: list) -> str:
    """int, real, date or text from the non-empty values; a column with mixed content is text."""
    vals = [v for v in values if v not in (None, "")]
    if not vals:
        return "text"
    if all(isinstance(v, bool) for v in vals):
        return "int"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
        return "int" if all(float(v).is_integer() and abs(v) < 2 ** 63 for v in vals) else "real"
    s = [str(v).strip() for v in vals]
    if all(_INT_RE.match(x) for x in s):
        return "int"
    if all(_FLOAT_RE.match(x) for x in s):
        return "real"
    if all(_DATE_RE.match(x) for x in s):
        return "date"
    return "text"


def _coerce(v, t: str):
    if v in (None, ""):
        return None
    if t == "int":
        try:
            return int(float(v)) if not isinstance(v, bool) else int(v)
        except (TypeError, ValueError):
            return None
    if t == "real":
        try:
            return float(str(v).replace(",", ".")) if isinstance(v, str) else float(v)
        except (TypeError, ValueError):
            return None
    return str(v)


def read_csv(path: Path) -> tuple[list[str], list[list]]:
    """Header and rows; the delimiter is sniffed (comma or semicolon, as Excel exports it in Swedish and German locales)."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    sample = text[:4096]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    rows = list(csv.reader(text.splitlines(), delimiter=delim))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return [], []
    header = [h.strip() or f"column_{i + 1}" for i, h in enumerate(rows[0])]
    return header, [r[:len(header)] + [""] * (len(header) - len(r)) for r in rows[1:]]


_XLSX_DATE_FORMATS = {14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47}
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
       "p": "http://schemas.openxmlformats.org/package/2006/relationships"}


def read_xlsx(path: Path) -> list[tuple[str, list[str], list[list]]]:
    """Every sheet of an .xlsx workbook as (sheet name, header, rows), with no library beyond the standard one:
    shared and inline strings, numbers, booleans, and date cells (by their number format) as ISO dates.
    Formulas give their cached value. Merged cells, rich text colours and charts are ignored."""
    out = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
        date_styles: set[int] = set()
        if "xl/styles.xml" in names:
            st = ET.fromstring(z.read("xl/styles.xml"))
            custom = {int(nf.get("numFmtId")): nf.get("formatCode", "") for nf in st.iter(f"{{{_NS['m']}}}numFmt") if nf.get("numFmtId", "").isdigit()}
            xfs = st.find("m:cellXfs", _NS)
            for i, xf in enumerate(xfs.findall("m:xf", _NS) if xfs is not None else []):
                fid = int(xf.get("numFmtId", "0"))
                code = custom.get(fid, "").lower()
                if fid in _XLSX_DATE_FORMATS or (code and re.search(r"[ymd]", re.sub(r"\[[^]]*]|\"[^\"]*\"", "", code)) and "0" not in code):
                    date_styles.add(i)
        rels = {}
        if "xl/_rels/workbook.xml.rels" in names:
            for rel in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).findall("p:Relationship", _NS):
                rels[rel.get("Id")] = rel.get("Target")
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        for sheet in wb.find("m:sheets", _NS).findall("m:sheet", _NS):
            target = rels.get(sheet.get(f"{{{_NS['r']}}}id"), "")
            target = target.lstrip("/")
            part = target if target.startswith("xl/") else "xl/" + target             # relative or absolute targets both occur
            if part not in names:
                continue
            grid: dict[int, dict[int, object]] = {}
            row_no = 0
            for row_el in ET.fromstring(z.read(part)).iter(f"{{{_NS['m']}}}row"):
                row_no = int(row_el.get("r")) if str(row_el.get("r", "")).isdigit() else row_no + 1
                col_no = 0
                for c in row_el.findall("m:c", _NS):
                    ref = c.get("r")                                       # optional: without it the cell follows the previous one
                    m_ref = re.match(r"([A-Z]+)(\d+)$", ref or "")
                    if m_ref:
                        col_no = 0
                        for ch in m_ref.group(1):
                            col_no = col_no * 26 + ord(ch) - 64
                        row = int(m_ref.group(2))
                    else:
                        col_no += 1
                        row = row_no
                    col = col_no
                    t, v = c.get("t"), c.find("m:v", _NS)
                    if t == "s" and v is not None:
                        val = shared[int(v.text)] if int(v.text) < len(shared) else ""
                    elif t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(f"{{{_NS['m']}}}t"))
                    elif t == "b" and v is not None:
                        val = v.text == "1"
                    elif v is None or v.text is None:
                        val = ""
                    elif t in ("str", "e", "d"):                          # formula string, error, ISO date cell
                        val = v.text
                    else:
                        num = float(v.text)
                        if int(c.get("s", "0")) in date_styles and 0 < num < 2958466:
                            d = _dt.datetime(1899, 12, 30) + _dt.timedelta(days=num)
                            val = d.date().isoformat() if num == int(num) else d.replace(microsecond=0).isoformat(sep=" ")
                        else:
                            val = int(num) if num.is_integer() and abs(num) < 2 ** 63 else num
                    grid.setdefault(row, {})[col] = val
            if not grid:
                continue
            width = max(max(r) for r in grid.values())
            ordered = [[grid.get(r, {}).get(c, "") for c in range(1, width + 1)] for r in sorted(grid)]
            ordered = [r for r in ordered if any(x not in ("", None) for x in r)]
            if not ordered:
                continue
            header = [str(h).strip() or f"column_{i + 1}" for i, h in enumerate(ordered[0])]
            out.append((sheet.get("name", "Sheet"), header, ordered[1:]))
    return out


def folder_source(folder: str | Path, schema_name: str = "data") -> Source:
    """Every .csv and .xlsx in the folder becomes a table in a local SQLite database (in memory, gone when the demo
    stops): the file name is the table name, a workbook with several sheets gives one table per sheet."""
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"{folder} is not a folder")
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".csv", ".xlsx") and not p.name.startswith("~$"))
    if not files:
        raise FileNotFoundError(f"no .csv or .xlsx files in {folder}")
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute(f"ATTACH DATABASE ':memory:' AS [{schema_name}]")
    used: set[str] = set()
    rows_out, notes, loaded = [], [], 0
    for p in files:
        try:
            sheets = read_xlsx(p) if p.suffix.lower() == ".xlsx" else [("", *read_csv(p))]
        except Exception as e:                                     # noqa: BLE001 - one bad file never stops the demo
            notes.append(f"{p.name}: could not be read ({type(e).__name__}: {e})")
            continue
        for sheet, header, data in sheets:
            if not header:
                notes.append(f"{p.name}{' / ' + sheet if sheet else ''}: empty, skipped")
                continue
            name = _table_name(p.stem if len(sheets) == 1 else f"{p.stem}_{sheet}", used)
            seen: set[str] = set()
            cols = []
            for i, h in enumerate(header):
                h = _column_name(h, i)
                base, k = h, 2
                while base.lower() in seen:
                    base, k = f"{h}_{k}", k + 1
                seen.add(base.lower()); cols.append(base)
            types = [_guess_type([r[i] for r in data]) for i in range(len(cols))]
            try:
                con.execute(f"CREATE TABLE [{schema_name}].[{name}] (" + ", ".join(f"[{c}] {t.upper()}" for c, t in zip(cols, types)) + ")")
                con.executemany(f"INSERT INTO [{schema_name}].[{name}] VALUES ({','.join('?' * len(cols))})",
                                [tuple(_coerce(v, t) for v, t in zip(r, types)) for r in data])
            except Exception as e:                                 # noqa: BLE001 - one table that SQLite refuses never stops the demo
                con.execute(f"DROP TABLE IF EXISTS [{schema_name}].[{name}]")
                notes.append(f"{p.name}{' / ' + sheet if sheet else ''}: could not be loaded ({type(e).__name__}: {e})")
                continue
            for i, (c, t) in enumerate(zip(cols, types)):
                rows_out.append({"table_schema": schema_name, "table_name": name, "column_name": c, "data_type": t, "ordinal_position": i + 1})
            loaded += 1
            notes.append(f"{p.name}{' / ' + sheet if sheet else ''} → {name}: {len(data)} rows, {len(cols)} columns")
    if not loaded:
        con.close()
        raise ValueError("no file in the folder could be read: " + "; ".join(notes))
    return Source("folder", f"{loaded} table(s) from {folder}", Schema.from_information_schema(rows_out, schema=schema_name),
                  _sqlite_execute(con), "sqlite", notes, con.close)


def columns_source(path: str | Path, schema_name: str = "dbo") -> Source:
    """A columns list (INFORMATION_SCHEMA.COLUMNS export): the plan and the map, no counts and no questions."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    s = Schema.from_information_schema(rows, schema=schema_name)
    if not len(s):
        raise ValueError(f"no columns for schema {schema_name!r} in {path}")
    return Source("columns", f"columns list {Path(path).name} (schema {schema_name})", s, None, "tsql",
                  ["A columns list has no rows: the plan is from names alone; the health check and the questions need a connection."])


def odbc_source(dsn: str, schema_name: str = "dbo") -> Source:
    """A SQL Server, Azure SQL or Fabric SQL endpoint over ODBC. The connection string is never shown on the page."""
    try:
        import pyodbc
    except ImportError as e:
        raise RuntimeError("pyodbc is not installed: pip install pyodbc, and Microsoft ODBC Driver 18 for SQL Server") from e
    conn = pyodbc.connect(dsn)

    def execute(sql: str):
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    s = Schema.from_sql(execute, schema_name)
    if not len(s):
        conn.close()
        raise ValueError(f"schema {schema_name!r} has no tables for this sign-in")
    m = re.search(r"(?:server|addr|address)\s*=\s*([^;]+)", dsn, re.I)
    host = m.group(1).strip() if m else "the server"
    return Source("odbc", f"{host}, schema {schema_name}", s, execute, "tsql",
                  ["Read with your own sign-in over ODBC; the demo runs counting queries only, nothing is written."], conn.close)


def open_source(kind: str, value: str = "", schema_name: str = "") -> Source:
    kind = (kind or "sample").lower()
    if kind == "sample":
        return sample_source()
    if kind == "folder":
        return folder_source(value, schema_name or "data")
    if kind == "columns":
        return columns_source(value, schema_name or "dbo")
    if kind == "odbc":
        return odbc_source(value, schema_name or "dbo")
    raise ValueError(f"unknown source kind {kind!r}: sample, folder, odbc or columns")


# ------------------------------------------------------------------ the session -----------------------------------

def _plan_json(p: Plan, source: Source, decisions: dict) -> dict:
    """The plan in the shape the graph explorer draws (the site's /demo/plan.json)."""
    linked: set[tuple[str, str]] = set()
    for r in p.relationships:
        linked.update((r.source, c.lower()) for c in r.source_cols)
        linked.update((r.target, c.lower()) for c in r.target_cols)
    tables = []
    for t in p.schema:
        key, rule = p.keys.get(t.name, ([], "K3"))
        tables.append({"name": t.name, "key": key, "key_rule": rule,
                       "columns": [{"name": c.name, "type": c.data_type, "key": c.name in key, "linked": (t.name, c.name.lower()) in linked} for c in t.columns]})
    confirmed = {(c["source"], tuple(x.lower() for x in c["source_cols"]), c["target"]) for c in decisions["confirmed"]}
    return {"name": p.schema.schema, "summary": p.summary(), "rules": RULES, "tables": tables,
            "relationships": [{"source": r.source, "source_cols": r.source_cols, "target": r.target, "target_cols": r.target_cols,
                               "rule": r.rule, "field": r.field_name, "reverse": r.reverse_name,
                               "accepted_here": (r.source, tuple(c.lower() for c in r.source_cols), r.target) in confirmed} for r in p.relationships],
            "ambiguous": p.ambiguous, "keyless": p.keyless, "mermaid": p.mermaid()}


def _label_column(t) -> str | None:
    """The column that names a row: the first string column that is not the key and not a reference."""
    for c in t.columns:
        n = c.name.lower()
        if c.data_type.lower() in STRINGS and not n.endswith(("_id", "id", "_key", "_code", "_nr", "_no")):
            return c.name
    return None


def _measures(p: Plan, t) -> list[str]:
    key = {c.lower() for c in p.keys.get(t.name, ([], ""))[0]}
    refs = {c.lower() for r in p.relationships if r.source == t.name for c in r.source_cols}
    return [c.name for c in t.columns if c.data_type.lower() in NUMERIC and c.name.lower() not in key | refs and not c.name.lower().endswith(("_id", "id", "_no", "_nr"))]


def _dates(t) -> list[str]:
    return [c.name for c in t.columns if c.data_type.lower() in DATES]


def _has_rows(execute, sql: str) -> bool:
    try:
        return bool(list(execute(sql)))
    except Exception:                                              # noqa: BLE001
        return False


def questions(p: Plan, analysis: dict, dialect: str, n: int = 5, execute=None) -> list[dict]:
    """Five questions the data can answer, from the graph: counts and sums over a relationship, the rows nothing refers
    to, a month profile, a join across a path, and the row counts of every table. Each carries its SQL and why."""
    qi = evidence.qi
    schema = p.schema.schema
    tn = lambda name: f"{qi(schema)}.{qi(name)}"                                        # noqa: E731
    top = (lambda sql, k: sql.replace("SELECT ", f"SELECT TOP ({k}) ", 1)) if dialect == "tsql" else (lambda sql, k: sql + f"\nLIMIT {k}")
    month = (lambda col: f"CONVERT(varchar(7), {qi(col)}, 120)") if dialect == "tsql" else (lambda col: f"substr({qi(col)}, 1, 7)")
    roles = analysis.get("roles", {})
    pr = analysis.get("centrality", {}).get("pagerank", {})
    def busy(name: str) -> int:                                   # transactional tables first: a date column, a measure, a fact role
        t = p.schema[name]
        return (2 if _dates(t) else 0) + (1 if _measures(p, t) else 0) + (1 if roles.get(name, {}).get("role") == "fact" else 0)
    rels = sorted(p.relationships, key=lambda r: (-busy(r.source), -pr.get(r.target, 0), -pr.get(r.source, 0), r.source))
    out: list[dict] = []

    def add(qid, title, why, sql):
        if len(out) < n and all(q["id"] != qid for q in out):
            out.append({"id": qid, "title": title, "why": why, "sql": sql})
    for r in rels:
        t = p.schema[r.target]
        label = _label_column(t)
        if label and len(r.source_cols) == 1:
            on = " AND ".join(f"s.{qi(a)} = t.{qi(b)}" for a, b in zip(r.source_cols, r.target_cols))
            add(f"count:{r.source}>{r.target}", f"How many {r.source} rows per {r.target}?",
                f"{r.source}.{r.source_cols[0]} points at {r.target} (rule {r.rule}); {label} names each {r.target} row.",
                top(f"SELECT t.{qi(label)} AS {qi(label)}, COUNT(*) AS {qi('rows')}\nFROM {tn(r.source)} AS s\nJOIN {tn(r.target)} AS t ON {on}\nGROUP BY t.{qi(label)}\nORDER BY COUNT(*) DESC", ROW_CAP))
            break
    for r in rels:
        t, s = p.schema[r.target], p.schema[r.source]
        label, ms = _label_column(t), _measures(p, s)
        if label and ms and len(r.source_cols) == 1:
            on = " AND ".join(f"s.{qi(a)} = t.{qi(b)}" for a, b in zip(r.source_cols, r.target_cols))
            add(f"sum:{r.source}.{ms[0]}>{r.target}", f"Total {ms[0]} per {r.target}",
                f"{ms[0]} is a number in {r.source} that is neither its key nor a reference; summed over the {r.rule} link to {r.target}.",
                top(f"SELECT t.{qi(label)} AS {qi(label)}, SUM(s.{qi(ms[0])}) AS {qi('total_' + ms[0])}\nFROM {tn(r.source)} AS s\nJOIN {tn(r.target)} AS t ON {on}\nGROUP BY t.{qi(label)}\nORDER BY SUM(s.{qi(ms[0])}) DESC", ROW_CAP))
            break
    none_tried, first_none = 0, None
    for r in rels:
        t = p.schema[r.target]
        label = _label_column(t)
        if label and len(r.source_cols) == 1 and roles.get(r.target, {}).get("role") != "fact" and none_tried < 3:
            none_tried += 1
            on = " AND ".join(f"s.{qi(a)} = t.{qi(b)}" for a, b in zip(r.source_cols, r.target_cols))
            q = (f"none:{r.target}<{r.source}", f"Which {r.target} have no {r.source}?",
                 f"Rows of {r.target} that nothing in {r.source} points at: often the first data-quality question a customer asks.",
                 top(f"SELECT t.{qi(label)} AS {qi(label)}\nFROM {tn(r.target)} AS t\nLEFT JOIN {tn(r.source)} AS s ON {on}\nWHERE s.{qi(r.source_cols[0])} IS NULL\nORDER BY t.{qi(label)}", ROW_CAP))
            first_none = first_none or q
            if execute is None or _has_rows(execute, q[3]):
                add(*q); first_none = None
                break
    if first_none:
        add(*first_none)
    for t in sorted(p.schema, key=lambda x: (-pr.get(x.name, 0), x.name)):
        ds = _dates(t)
        if ds:
            add(f"month:{t.name}.{ds[0]}", f"Rows in {t.name} per month",
                f"{ds[0]} is a date column; the month profile shows how far the data reaches and where the gaps are.",
                top(f"SELECT {month(ds[0])} AS {qi('month')}, COUNT(*) AS {qi('rows')}\nFROM {tn(t.name)}\nWHERE {qi(ds[0])} IS NOT NULL\nGROUP BY {month(ds[0])}\nORDER BY {month(ds[0])} DESC", 12))
            break
    best = None
    for a in p.schema:
        for b in p.schema:
            if a.name >= b.name or a.name not in p.keys or b.name not in p.keys:
                continue
            found = _paths.shortest_paths(p, a.name, b.name, limit=1)
            if found and (best is None or len(found[0]) > len(best[2])) and len(found[0]) >= 2:
                best = (a.name, b.name, found[0])
    if best:
        sql = _paths.sql_for(p, best[0], best[2], top=ROW_CAP)
        if dialect != "tsql":
            sql = sqlite_sql(sql)
        hops = " → ".join([best[0]] + [(r.target if fwd else r.source) for r, fwd in best[2]])
        add(f"path:{best[0]}>{best[1]}", f"From {best[0]} to {best[1]} in one query", f"The longest shortest path in the graph: {hops}. join_path writes this SQL.", sql)
    counts = "\nUNION ALL\n".join(f"SELECT '{t.name.replace(chr(39), chr(39) * 2)}' AS {qi('table_name')}, COUNT(*) AS {qi('rows')} FROM {tn(t.name)}" for t in p.schema)
    add("counts", "How many rows in every table?", "The first thing to know, and the fastest way to see that the connection works.", counts)
    return out[:n]


def run_question(q: dict, execute) -> dict:
    out = dict(q)
    if execute is None:
        out.update(columns=[], rows=[], note="needs a connection with rows")
        return out
    try:
        rows = list(execute(q["sql"]))[:ROW_CAP]
        cols = list(rows[0].keys()) if rows else []
        out.update(columns=cols, rows=[[_cell(r.get(c)) for c in cols] for r in rows])
    except Exception as e:                                         # noqa: BLE001 - one failing question never hides the rest
        out.update(columns=[], rows=[], error=f"{type(e).__name__}: {e}")
    return out


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        v = f"{v:.2f}".rstrip("0").rstrip(".") if not v.is_integer() else str(int(v))
    s = str(v)
    return s if len(s) <= CELL_CAP else s[:CELL_CAP - 1] + "…"


class Session:
    """One demo: the source, the decisions taken on the page (accepted relationships and keys, skipped findings), and
    everything derived from them. `state()` is what the page renders; `handle()` is the HTTP surface."""

    def __init__(self, source: Source | None = None):
        self.source = source
        self.confirmed: list[dict] = []
        self.keys: dict[str, list[str]] = {}
        self.skipped: list[str] = []
        self.started = time.time()
        self.step_entered: dict[int, float] = {1: self.started}
        self.current_step = 1
        self._cache: dict | None = None
        self._validation: dict | None = None                      # the last health check, reused by the exports
        self._lock = threading.RLock()                             # one request at a time: the sqlite connection and the cache are shared

    # -- decisions ---------------------------------------------------------------------------------------------------
    def connect(self, kind: str, value: str = "", schema_name: str = "") -> None:
        src = open_source(str(kind or "sample"), str(value or ""), str(schema_name or ""))
        old = self.source
        self.source, self.confirmed, self.keys, self.skipped, self._cache = src, [], {}, [], None
        self._validation = None
        if old and old.close:
            try:
                old.close()                                        # after the swap, so a request in flight sees the new source
            except Exception:                                      # noqa: BLE001
                pass
        self.enter_step(2)

    def enter_step(self, n: int) -> None:
        n = max(1, min(4, int(n)))
        self.step_entered.setdefault(n, time.time())
        self.current_step = n

    def plan(self) -> Plan:
        return plan(self.source.schema, keys=self.keys or None, confirmed=self.confirmed or None)

    def accept(self, finding_id: str) -> dict:
        f = next((x for x in self.state()["health"]["findings"] if x["id"] == finding_id), None)
        if f is None:
            raise KeyError(finding_id)
        nxt = f.get("next", {})
        if "confirmed" in nxt:
            c = nxt["confirmed"]
            if finding_id.startswith("amb:"):                      # one target per column: accepting a candidate drops the others
                self.confirmed = [x for x in self.confirmed if not (x["source"] == c["source"] and x["source_cols"] == c["source_cols"])]
            if not any(x["source"] == c["source"] and x["source_cols"] == c["source_cols"] and x["target"] == c["target"] for x in self.confirmed):
                self.confirmed.append(c)
        elif "keys" in nxt:
            self.keys.update(nxt["keys"])
        else:
            raise ValueError("this finding has no accept action: it carries SQL to run yourself")
        if finding_id in self.skipped:
            self.skipped.remove(finding_id)
        self._cache = None
        return f

    def skip(self, finding_id: str) -> None:
        f = next((x for x in self.state()["health"]["findings"] if x["id"] == finding_id), None)
        if f is not None and f.get("accepted"):                    # undo: the decision leaves the plan again
            nxt = f.get("next", {})
            if "confirmed" in nxt:
                c = nxt["confirmed"]
                self.confirmed = [x for x in self.confirmed if not (x["source"] == c["source"] and x["source_cols"] == c["source_cols"] and x["target"] == c["target"])]
            for t in nxt.get("keys", {}):
                self.keys.pop(t, None)
        if finding_id not in self.skipped:
            self.skipped.append(finding_id)
        self._cache = None

    def reset(self) -> None:
        self.confirmed, self.keys, self.skipped, self._cache = [], {}, [], None

    # -- derived -----------------------------------------------------------------------------------------------------
    def findings(self, p: Plan, validation: dict | None, suggestions: dict | None) -> list[dict]:
        schema = p.schema.schema
        out: list[dict] = []
        accepted_keys = set(self.keys)
        confirmed = {(c["source"], tuple(x.lower() for x in c["source_cols"]), c["target"]) for c in self.confirmed}
        for k in (validation or {}).get("keys", []):
            if k["verdict"].startswith("unique"):
                continue
            cols = ", ".join(k["columns"])
            out.append({"id": f"key:{k['table']}", "kind": "key", "severity": "problem", "table": k["table"],
                        "title": f"Key of {k['table']} is not clean: {cols}",
                        "saw": f"{k['rows']} rows, {k['distinct']} distinct values, {k['nulls']} NULLs (rule {k['rule']}).",
                        "means": "A GraphQL API, a semantic model or a join on this key would return the wrong row or several rows. The key the names suggest is not the key the data has.",
                        "next": {"sql": f"SELECT {', '.join(evidence.qi(c) for c in k['columns'])}, COUNT(*) AS n FROM {evidence.qi(schema)}.{evidence.qi(k['table'])} GROUP BY {', '.join(evidence.qi(c) for c in k['columns'])} HAVING COUNT(*) > 1"},
                        "next_text": "List the duplicated values with the SQL, then give the real key (a composite one, or another column) as `keys`.",
                        "evidence": evidence.key_sql(schema, k["table"], k["columns"])})
        for r in (validation or {}).get("relationships", []):
            if r["verdict"].startswith("holds"):
                continue
            out.append({"id": f"rel:{r['source']}.{'+'.join(r['columns'])}>{r['target']}", "kind": "relationship", "severity": "warning", "table": r["source"],
                        "title": f"{r['source']}.{'+'.join(r['columns'])} → {r['target']}: {r['orphans']} orphan(s)",
                        "saw": f"{r['rows_with_value']} rows with a value, {r['orphans']} of them point at nothing in {r['target']} (rule {r['rule']}). {r['verdict']}.",
                        "means": "Either the link is right and the data has gaps (deleted parents, loads out of order), or the column points at another table. Both are worth knowing before an app is built on it.",
                        "next": {"sql": f"SELECT s.* FROM {evidence.qi(schema)}.{evidence.qi(r['source'])} AS s LEFT JOIN {evidence.qi(schema)}.{evidence.qi(r['target'])} AS t ON " + " AND ".join(f"s.{evidence.qi(a)} = t.{evidence.qi(b)}" for a, b in zip(r['columns'], r['target_columns'])) + f" WHERE t.{evidence.qi(r['target_columns'][0])} IS NULL AND s.{evidence.qi(r['columns'][0])} IS NOT NULL"},
                        "next_text": "Look at the orphan rows with the SQL; if the link is wrong, skip it here and pass another target as `confirmed`.",
                        "evidence": evidence.relationship_sql(schema, r["source"], r["columns"], r["target"], r["target_columns"])})
        decided_cols = {(c["source"], tuple(x.lower() for x in c["source_cols"])) for c in self.confirmed}
        for a in p.ambiguous:
            if (a["table"], (a["column"].lower(),)) in decided_cols:   # already linked by a decision here: the question is answered
                continue
            for cand in a["candidates"]:
                target = p.schema[cand]
                tkey = p.keys.get(cand, ([], ""))[0]
                if len(tkey) != 1:
                    continue
                c = {"source": a["table"], "source_cols": [a["column"]], "target": cand, "target_cols": tkey}
                out.append({"id": f"amb:{a['table']}.{a['column']}>{cand}", "kind": "ambiguous", "severity": "question", "table": a["table"],
                            "title": f"{a['table']}.{a['column']} could point at {cand}",
                            "saw": f"The name fits {len(a['candidates'])} tables ({', '.join(a['candidates'])}); rule {a.get('rule', 'R1')} applies nothing rather than guess.",
                            "means": "The engine never guesses between two targets. You decide; the choice becomes a `confirmed` entry.",
                            "next": {"confirmed": c}, "next_text": f"Accept to link it to {cand}.{tkey[0]}.",
                            "evidence": evidence.inclusion_sql(schema, a["table"], a["column"], cand, tkey[0]) if self.source.has_data else "names only"})
        for s in (suggestions or {}).get("candidates", []):
            ev = s.get("evidence")
            if ev is None:
                continue
            key = (s["source"], tuple(x.lower() for x in s["source_cols"]), s["target"])
            if key in confirmed:
                continue
            inc = ev.get("inclusion")
            strength = ("strong" if inc == 1.0 and (ev.get("distinct_values") or 0) >= 3 else "weak" if inc is not None and inc >= 0.9 else "poor")
            if strength == "poor":
                continue
            out.append({"id": f"sug:{s['source']}.{s['source_cols'][0]}>{s['target']}", "kind": "suggestion", "severity": "suggestion", "table": s["source"],
                        "title": f"Suggested: {s['source']}.{s['source_cols'][0]} → {s['target']}.{s['target_cols'][0]}",
                        "saw": f"{ev['rows_with_value']} rows with a value, {ev['matched']} found in {s['target']}'s key, {ev['distinct_values']} distinct values (inclusion {round((inc or 0) * 100)}%). {ev['verdict']}.",
                        "means": ("Every value exists in the target key and there are enough distinct values for that to mean something: " + s.get("why", "names and types fit.")
                                  if strength == "strong" else "Most values exist in the target key; a few do not. Likely a link with gaps, possibly a coincidence. " + s.get("why", "")),
                        "next": {"confirmed": s["confirmed"]}, "next_text": "Accept to add it as a confirmed relationship; Skip to leave the column alone. Accepted is your decision, not a verified fact.",
                        "evidence": evidence.inclusion_sql(schema, s["source"], s["source_cols"][0], s["target"], s["target_cols"][0]), "strength": strength})
        for c in self.confirmed:                                   # decided earlier on this page: stays visible under "decided"
            fid = f"sug:{c['source']}.{c['source_cols'][0]}>{c['target']}"
            if any(f["id"] == fid or f["id"] == f"amb:{c['source']}.{c['source_cols'][0]}>{c['target']}" for f in out):
                continue
            out.append({"id": fid, "kind": "suggestion", "severity": "suggestion", "table": c["source"],
                        "title": f"Confirmed by you: {c['source']}.{'+'.join(c['source_cols'])} → {c['target']}.{'+'.join(c['target_cols'])}",
                        "saw": "Accepted on this page; the health check above now counts it like any other relationship.",
                        "means": "A confirmed relationship is your decision, applied before inference. Skip here takes it out again.",
                        "next": {"confirmed": c}, "next_text": "In the hosted tools this is the `confirmed` entry to pass to plan_backend or create_backend.",
                        "evidence": evidence.relationship_sql(schema, c["source"], c["source_cols"], c["target"], c["target_cols"])})
        for t, cols in self.keys.items():
            if any(f["id"] in (f"ckey:{t}", f"nokey:{t}.{cols[0]}") for f in out):
                continue
            out.append({"id": f"ckey:{t}" if len(cols) > 1 else f"nokey:{t}.{cols[0]}", "kind": "composite_key", "severity": "suggestion", "table": t,
                        "title": f"Key of {t} set by you: {' + '.join(cols)}", "saw": "Accepted on this page; the health check counts whether it is unique.",
                        "means": "A key given by you is rule K1 in the plan.", "next": {"keys": {t: cols}},
                        "next_text": "In the hosted tools this is the `keys` entry.", "evidence": evidence.key_sql(schema, t, cols)})
        for ck in evidence.suggest_composite_keys(p):
            if ck["table"] in accepted_keys or ck["table"] in p.keys:
                continue
            out.append({"id": f"ckey:{ck['table']}", "kind": "composite_key", "severity": "suggestion", "table": ck["table"],
                        "title": f"{ck['table']} could have the key {' + '.join(ck['columns'])}",
                        "saw": f"No column names a key. {ck['why']}.", "means": "With a key the table can be referenced and gets a `by primary key` query; without one it can only be listed.",
                        "next": {"keys": ck["use"]}, "next_text": "Accept to use it as the key; the health check will then count whether it is unique.",
                        "evidence": evidence.key_sql(schema, ck["table"], ck["columns"]) if self.source.has_data else "names only"})
        for t in p.keyless:
            if any(f["table"] == t and f["kind"] == "composite_key" for f in out) or t in accepted_keys:
                continue
            cands = []
            if self.source.has_data:
                for c in p.schema[t].columns[:6]:
                    try:
                        row = self.source.execute(evidence.key_sql(schema, t, [c.name]))[0]
                    except Exception:                              # noqa: BLE001
                        continue
                    n, nulls, distinct = evidence._int(row.get("n")), evidence._int(row.get("nulls")), evidence._int(row.get("distinct_keys"))
                    if n and nulls == 0 and distinct == n:
                        cands.append(c.name)
            if cands:
                for c in cands[:2]:
                    out.append({"id": f"nokey:{t}.{c}", "kind": "key_candidate", "severity": "suggestion", "table": t,
                                "title": f"{t} has no key; {c} is unique in the data",
                                "saw": f"No column is named like a key (rule K3). Counting {c}: every row has a value and no two rows share one.",
                                "means": "A unique column can serve as the key even if its name does not say so. The engine does not take that step alone.",
                                "next": {"keys": {t: [c]}}, "next_text": f"Accept to use {c} as the key of {t}.",
                                "evidence": evidence.key_sql(schema, t, [c])})
            else:
                out.append({"id": f"nokey:{t}", "kind": "keyless", "severity": "info", "table": t,
                            "title": f"{t} has no key", "saw": "No column is named like a key (rule K3)" + (", and none of the first six columns is unique." if self.source.has_data else "."),
                            "means": "The table can be listed and can point at others, but nothing can point at it. Logs and event tables are often like this, and that is fine.",
                            "next": {"sql": f"SELECT COUNT(*) AS n, COUNT(DISTINCT {evidence.qi(p.schema[t].column_names[0])}) AS distinct_first FROM {evidence.qi(schema)}.{evidence.qi(t)}"},
                            "next_text": "If it does have a key, give it as `keys`.", "evidence": "names only"})
        for f in out:
            f["skipped"] = f["id"] in self.skipped
            f["accepted"] = ("confirmed" in f.get("next", {}) and (f["next"]["confirmed"]["source"], tuple(x.lower() for x in f["next"]["confirmed"]["source_cols"]), f["next"]["confirmed"]["target"]) in confirmed) \
                or ("keys" in f.get("next", {}) and all(self.keys.get(t) == cols for t, cols in f["next"]["keys"].items()))
            f["can_accept"] = "confirmed" in f.get("next", {}) or "keys" in f.get("next", {})
        order = {"problem": 0, "warning": 1, "question": 2, "suggestion": 3, "info": 4}
        out.sort(key=lambda f: (f["accepted"], f["skipped"], order.get(f["severity"], 9), f["table"], f["id"]))
        return out

    def exports(self, p: Plan, validation: dict | None, qs: list[dict]) -> dict[str, tuple[str, str]]:
        """name -> (content type, text)."""
        from .dbt import schema_yml
        from .dictionary import data_dictionary
        src = self.source
        name = {"sample": "shop", "folder": "data", "odbc": p.schema.schema, "columns": p.schema.schema}[src.kind]
        return {
            "dictionary.md": ("text/markdown; charset=utf-8", data_dictionary(p, src.label, p.schema.schema, validation)),
            "schema.yml": ("text/yaml; charset=utf-8", schema_yml(p, name, p.schema.schema)),
            "lovable-prompt.md": ("text/markdown; charset=utf-8", lovable_prompt(p, qs, src)),
            "plan.json": ("application/json; charset=utf-8", json.dumps(_plan_json(p, src, {"confirmed": self.confirmed}), indent=1)),
            "er.mmd": ("text/plain; charset=utf-8", p.mermaid()),
        }

    def state(self) -> dict:
        return {**self._base(), **self._derived()}

    def _base(self) -> dict:
        """The part that is never cached: the clock and the step."""
        steps = [{**s, "entered": self.step_entered.get(s["n"]), "current": s["n"] == self.current_step} for s in STEPS]
        return {"host": HOST, "steps": steps, "started": self.started, "now": time.time(), "current_step": self.current_step,
                "decisions": {"confirmed": self.confirmed, "keys": self.keys, "skipped": self.skipped}}

    def _derived(self) -> dict:
        """Plan, analysis, health check, questions and exports: computed once per set of decisions (the counting queries
        run again only when a decision changes the plan)."""
        if self._cache is not None:
            return self._cache
        if self.source is None:
            self._cache = {"source": None, "plan": None, "analysis": None, "health": None, "questions": [], "exports": []}
            return self._cache
        src = self.source
        try:
            p = self.plan()
        except PlanInputError as e:                                # a key accepted earlier no longer fits: drop the decisions, say so
            self.keys, self.confirmed = {}, []
            p = self.plan()
            _note(src, f"decisions dropped: {e}")
        analysis = graphs.analyze(p)
        validation = suggestions = None
        if src.has_data:
            try:
                validation = evidence.validate(p, src.execute)
            except Exception as e:                                 # noqa: BLE001 - the map still shows without counts
                _note(src, f"health check could not run: {type(e).__name__}: {e}")
            try:
                suggestions = graphs.suggest(p, src.execute, check=15)
            except Exception as e:                                 # noqa: BLE001
                _note(src, f"suggestions could not be checked: {type(e).__name__}: {e}")
        else:
            suggestions = graphs.suggest(p, None)
        self._validation = validation
        findings = self.findings(p, validation, suggestions)
        qs = [run_question(q, src.execute) for q in questions(p, analysis, src.dialect, execute=src.execute)]
        open_findings = [f for f in findings if not f["accepted"] and not f["skipped"]]
        health = {"checked": validation is not None,
                  "summary": (validation["summary"] if validation else "No rows to check: a columns list gives the plan only."),
                  "findings": findings,
                  "open": len(open_findings), "note": "Counts over the whole tables now. Accepting a suggestion is your decision; nothing here calls it verified."}
        self._cache = {"source": {"kind": src.kind, "label": src.label, "schema": p.schema.schema, "dialect": src.dialect, "has_data": src.has_data,
                                  "tables": len(p.schema), "notes": src.notes},
                       "plan": _plan_json(p, src, {"confirmed": self.confirmed}),
                       "analysis": {"summary": analysis["summary"], "roles": analysis["roles"], "areas": analysis["areas"],
                                    "central": analysis["centrality"]["top"][:5], "inactive": analysis["inactive_relationships"]},
                       "health": health, "questions": qs,
                       "exports": [{"name": n, "href": f"/export/{n}"} for n in self.exports(p, validation, qs)]}
        return self._cache

    # -- HTTP --------------------------------------------------------------------------------------------------------
    def handle(self, method: str, path: str, body: bytes = b"") -> tuple[int, str, bytes]:
        """(status, content type, body). The whole surface of the demo server; tests call it directly."""
        with self._lock:
            return self._handle(method, path, body)

    def _handle(self, method: str, path: str, body: bytes = b"") -> tuple[int, str, bytes]:
        from .pages import STATIC_DIR, STATIC_TYPES
        u = urlsplit(path)
        route = u.path
        try:
            if method == "GET" and route == "/":
                return 200, "text/html; charset=utf-8", demo_page().encode("utf-8")
            if method == "GET" and route.startswith("/static/"):
                f = (STATIC_DIR / route[len("/static/"):]).resolve()
                if not str(f).startswith(str(STATIC_DIR.resolve())) or not f.is_file():
                    return 404, "text/plain; charset=utf-8", b"not found"
                return 200, STATIC_TYPES.get(f.suffix, "application/octet-stream"), f.read_bytes()
            if method == "GET" and route == "/api/state":
                return 200, "application/json; charset=utf-8", json.dumps(self.state(), default=str).encode("utf-8")
            if method == "GET" and route.startswith("/export/"):
                if self.source is None:
                    return 409, "text/plain; charset=utf-8", b"connect a source first"
                st = self.state()
                exp = self.exports(self.plan(), self._validation, st["questions"])   # the health check already run, or None when it failed
                name = route[len("/export/"):]
                if name not in exp:
                    return 404, "text/plain; charset=utf-8", b"no such export"
                ct, text = exp[name]
                return 200, ct, text.encode("utf-8")
            if method == "POST":
                data = json.loads(body.decode("utf-8") or "{}") if body else {}
                if not isinstance(data, dict):
                    return 400, "application/json; charset=utf-8", json.dumps({"error": "the body must be a JSON object", "kind": "bad_input"}).encode("utf-8")
                if route in ("/api/accept", "/api/skip", "/api/reset") and self.source is None:
                    return 409, "application/json; charset=utf-8", json.dumps({"error": "connect a source first", "kind": "bad_input"}).encode("utf-8")
                if route == "/api/connect":
                    self.connect(data.get("kind", "sample"), data.get("value", ""), data.get("schema", ""))
                elif route == "/api/step":
                    self.enter_step(int(data.get("step", 1)))
                elif route == "/api/accept":
                    self.accept(str(data.get("id", "")))
                elif route == "/api/skip":
                    self.skip(str(data.get("id", "")))
                elif route == "/api/reset":
                    self.reset()
                else:
                    return 404, "text/plain; charset=utf-8", b"not found"
                return 200, "application/json; charset=utf-8", json.dumps(self.state(), default=str).encode("utf-8")
            return 404, "text/plain; charset=utf-8", b"not found"
        except (FileNotFoundError, ValueError, KeyError, TypeError, PlanInputError, RuntimeError) as e:
            return 400, "application/json; charset=utf-8", json.dumps({"error": str(e), "kind": "bad_input"}).encode("utf-8")
        except Exception as e:                                     # noqa: BLE001 - an ODBC failure gives a message, never a traceback page
            return 500, "application/json; charset=utf-8", json.dumps({"error": f"{type(e).__name__}: {e}", "kind": "failed"}).encode("utf-8")


def _note(src: Source, text: str) -> None:
    if text not in src.notes:
        src.notes.append(text)


def lovable_prompt(p: Plan, qs: list[dict], src: Source) -> str:
    """A prompt for Lovable from the plan: the model, the screens the five questions suggest, and the honest note that
    the data connection comes when the GraphQL API exists (create_backend) or through Lovable's Fabric connector."""
    lines = [f"Build a small internal app on the data model below (schema `{p.schema.schema}`, {len(p.schema)} tables).", "",
             "## Data model", ""]
    for t in p.schema:
        key = p.keys.get(t.name)
        lines.append(f"- **{t.name}**: " + ", ".join(t.column_names) + (f" (key: {' + '.join(key[0])})" if key else " (no key)"))
    lines += ["", "## Relationships (many → one)", ""]
    for r in p.relationships:
        lines.append(f"- {r.source}.{'+'.join(r.source_cols)} → {r.target}.{'+'.join(r.target_cols)}")
    lines += ["", "## Screens", "", "One screen per question, each a table or a bar chart with a filter on the grouping column:", ""]
    for q in qs:
        lines.append(f"- **{q['title']}** — {q['why']}")
    lines += ["", "## Data connection", "",
              "The app reads through a GraphQL API that Krusgraph creates from this same plan (create_backend), or through Lovable's "
              "Microsoft Fabric connector once the tables are in a Fabric lakehouse. Until then, use mock data with these exact field names. "
              "Never put a database password or an Entra client secret in the frontend.", "",
              f"Source of this prompt: fabric-backend demo on {src.label}; keys and relationships inferred by rules K0–K5 and R0–R4, "
              "reviewed by a person on the demo page."]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ the page and the server ------------------------

def demo_page() -> str:
    from .pages import HERE, asset_version
    tpl = (HERE / "page_templates" / "demo_local.html").read_text(encoding="utf-8")
    steps = "".join(f'<button type="button" class="step-tab" data-step="{s["n"]}" aria-pressed="false"><span class="step-n {["coral", "sage", "lav", "mustard"][s["n"] - 1]}">{s["n"]}</span>'
                    f'<span class="st-title">{s["title"]}</span><span class="st-min">{s["minutes"]} min</span></button>' for s in STEPS)
    from .pages import _LOGO
    return tpl.replace("{{STEP_TABS}}", steps).replace("{{ASSET_V}}", asset_version()).replace("{{HOST}}", HOST).replace("{{LOGO}}", _LOGO)


def make_server(session: Session, port: int = DEFAULT_PORT):
    """The HTTP server, bound to 127.0.0.1 and nothing else. Port 0 picks a free port (tests)."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, ctype: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):                                          # noqa: N802
            self._send(*session.handle("GET", self.path))

        def do_POST(self):                                         # noqa: N802
            n = int(self.headers.get("Content-Length") or 0)
            self._send(*session.handle("POST", self.path, self.rfile.read(n) if n else b""))

        def log_message(self, fmt, *args):                         # quiet: the terminal shows the URL and nothing else
            pass

    server = ThreadingHTTPServer((HOST, port), Handler)
    server.daemon_threads = True
    return server


def serve(session: Session, port: int = DEFAULT_PORT, open_browser: bool = True) -> int:
    import webbrowser
    server = make_server(session, port)
    url = f"http://{HOST}:{server.server_address[1]}/"
    print(f"Krusgraph demo on {url}  (this machine only; Ctrl+C stops it)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if session.source and session.source.close:
            session.source.close()
    return 0
