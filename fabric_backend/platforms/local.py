"""The local adapter: what the local stdio server (mcp_server.py) and the 20-minute demo (demo_app.py) read, behind the
same boundary as Fabric (platforms/base.py).

1. Read: INFORMATION_SCHEMA over an ODBC connection string (a Fabric SQL analytics endpoint, warehouse or SQL database,
   or a SQL Server reached with Windows or SQL sign-in); a SQLite database built from the synthetic shop seed or from a
   folder of CSV and Excel files (one table per file or sheet); or a columns list (an INFORMATION_SCHEMA.COLUMNS
   export), which gives a plan from names and no rows.
2. Run SQL: pyodbc with the string as given (T-SQL), or SQLite reading the engine's T-SQL through
   dialects.sqlite_sql. Nothing is written except by create_views over ODBC, and only when asked.
3. Build: the stdio server drafts what the Fabric adapter builds (TMDL, ontology, views, the silver notebook) from
   the same plan; FABRIC_SOURCE_KIND says which kind of source the string reaches, and with SQLServer the drafts that
   only make sense for a Fabric item answer `unsupported` with the reason (OdbcPlatform.unsupported).

Moved here from demo_app.py and mcp_server.py in round n13 without a change to any answer (tests/test_golden.py);
both modules still export the old names.
"""
from __future__ import annotations

import csv
import datetime as _dt
import re
import sqlite3
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from ..dialects import TSQL, sqlite_sql
from ..schema import Schema
from .base import Platform, Unsupported, connection

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_]+")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?$")
_INT_RE = re.compile(r"^[+-]?\d{1,18}$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+[.,]\d*|\d*[.,]\d+|\d+)([eE][+-]?\d+)?$")


# ------------------------------------------------------------------ the demo's sources -----------------------------

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
    """The engine writes T-SQL; SQLite needs COUNT instead of COUNT_BIG and LIMIT instead of TOP (dialects.sqlite_sql)."""
    def execute(sql: str):
        cur = con.execute(sqlite_sql(sql))
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    return execute


def sample_source() -> Source:
    """The synthetic shop schema and rows from fabric_backend.seed in an in-memory SQLite database."""
    from ..seed import SCHEMAS, rows, schema
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


# ------------------------------------------------------------------ an ODBC connection string ----------------------

_ODBC_SYNONYMS = {"server": ("server", "addr", "address", "network address"), "database": ("database", "initial catalog")}


def odbc_parts(dsn: str) -> dict[str, str]:
    """key -> value of an ODBC connection string: `;` inside `{...}` does not split, one layer of braces or quotes
    around a value is removed, keys are compared without case."""
    out: dict[str, str] = {}
    for m in re.finditer(r"\s*([^=;]+?)\s*=\s*(\{[^}]*\}|\"[^\"]*\"|'[^']*'|[^;]*)\s*(?:;|$)", dsn):
        k, v = m.group(1).lower(), m.group(2).strip()
        if len(v) >= 2 and v[0] + v[-1] in ("{}", '""', "''"):
            v = v[1:-1]
        out[k] = v
    return out


def odbc_part(dsn: str, key: str) -> str:
    parts = odbc_parts(dsn)
    for name in _ODBC_SYNONYMS.get(key.lower(), (key.lower(),)):
        if parts.get(name):
            return parts[name]
    return ""


def odbc_connection(dsn: str):
    """The stdio server's connection: pyodbc with the string as given, rows as dicts, DDL committed."""
    import pyodbc
    conn = pyodbc.connect(dsn)

    def execute(sql: str):
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def statement(sql: str) -> None:                       # DDL for create_views: no rows, committed
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
    return connection(execute, dialect=TSQL, statement=statement, close=conn.close)


KINDS = {"lakehouse": "Lakehouse", "warehouse": "Warehouse", "sqldatabase": "SQLDatabase", "sqlserver": "SQLServer"}
FABRIC_ONLY = {"semantic_model_draft": "a Power BI semantic model in Direct Lake mode reads Delta tables through a Fabric SQL analytics endpoint",
               "ontology_draft": "a Fabric IQ ontology binds to tables of a Fabric item"}


def source_kind(raw: str | None) -> str:
    """FABRIC_SOURCE_KIND as one of KINDS' values (anything else is kept as given; empty is Lakehouse)."""
    raw = (raw if raw is not None else "Lakehouse").strip()
    return KINDS.get(raw.lower(), raw or "Lakehouse")


class OdbcPlatform(Platform):
    """A Fabric SQL endpoint, warehouse or SQL database, or a SQL Server, behind an ODBC connection string."""
    name = "odbc"
    title = "ODBC connection string (Fabric SQL endpoint or SQL Server)"
    dialect = TSQL

    def __init__(self, kind: str = "Lakehouse"):
        self.kind = kind

    def connect(self, dsn: str):
        return odbc_connection(dsn)

    def unsupported(self, tool: str) -> Unsupported | None:
        if tool in FABRIC_ONLY and self.kind == "SQLServer":
            return Unsupported(
                f"{tool} is Fabric-specific: {FABRIC_ONLY[tool]}; FABRIC_SOURCE_KIND is SQLServer, so there is no such endpoint or item.",
                ("For SQL Server, open the tables in Power BI Desktop (Import or DirectQuery) and use the plan's keys and relationships "
                 "from plan_backend, join_path or data_dictionary; dbt_schema, create_views and the rest work on SQL Server. "
                 "Mirror the database into Fabric (Mirrored database for SQL Server) to get the Fabric drafts." if tool == "semantic_model_draft"
                 else "Mirror the database into Fabric (Mirrored database for SQL Server) or use the plan directly; plan_backend, "
                      "join_path, data_dictionary, dbt_schema and create_views work on SQL Server."))
        if tool == "silver_notebook_draft" and self.kind != "Lakehouse":
            return Unsupported(
                f"The silver notebook writes Delta tables with Spark in a lakehouse; FABRIC_SOURCE_KIND is {self.kind}.",
                "Plan a lakehouse (FABRIC_SOURCE_KIND=Lakehouse), or mirror the tables into Fabric and add them to a lakehouse "
                "as OneLake shortcuts; answer_query_draft, create_views and the rest work on this source.")
        return None


class SqlitePlatform(Platform):
    """The demo's SQLite database: the synthetic shop, or a folder of CSV and Excel files loaded into memory."""
    name = "sqlite"
    title = "SQLite (synthetic shop data, or a folder of CSV / Excel files)"
    dialect = TSQL                                          # the engine's T-SQL, read through dialects.sqlite_sql

    def connect(self, con: sqlite3.Connection):
        return connection(_sqlite_execute(con), dialect=TSQL, close=con.close)


class ColumnsListPlatform(Platform):
    """An INFORMATION_SCHEMA.COLUMNS export: a plan from names, nothing to run SQL on."""
    name = "columns"
    title = "columns list (CSV export of INFORMATION_SCHEMA.COLUMNS)"

    def connect(self, *args, **kwargs):
        return None

    def read_schema(self, execute, schema: str) -> Schema:
        raise RuntimeError("a columns list has no connection: use columns_source(path, schema)")
