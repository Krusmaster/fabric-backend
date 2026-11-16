"""Krusgraph Connect, the schema export: a read-only metadata query a SQL Server administrator runs, and its parser.

B2, 15 November 2026 (backlog I-03; docs/CONNECT-DESIGN.md section 1.5). Krusgraph needs a source's tables, columns
and declared keys to plan, and must not read rows to get them. So the customer's DBA runs `EXPORT_SQL` (in SQL Server
Management Studio, Azure Data Studio or sqlcmd), saves the result as CSV or JSON, and gives Krusgraph the file.
`parse()` turns it into the same `Schema` that `sqlserver.py` reads over ODBC (`Schema.from_sql`: the rows of
`schema.COLUMNS_SQL` and `schema.KEYS_SQL`), so the plan from the file and the plan from a live connection are equal.

What the file holds: schema, table and column names, data types, column positions, and primary and foreign key
constraints with their names. Nothing else: no row values, no column defaults, no check clauses, no counts. The query
reads only INFORMATION_SCHEMA views (tests/test_b2_connect_export.py parses it and checks), and `parse()` refuses a
file with any column outside `FIELDS` or any row kind other than `column` and `key`, so a file with values added by
hand is refused, not read.

    sqlcmd -S sql01 -d erp -E -s"," -W -i export.sql -o krusgraph-schema.csv     # export.sql = export_sql()
    from fabric_backend import connect_export
    s = connect_export.parse(open("krusgraph-schema.csv").read(), schema="dbo")
    connect_export.schemas(text)                                                 # [{'schema': 'dbo', 'tables': 41}, ...]

Nothing here connects to anything. Not run against a live SQL Server in this round: the query is checked by parsing it
as T-SQL, and the parser on synthetic files.
"""
from __future__ import annotations

import csv
import io
import json

from .schema import Schema

# The columns of the export, in order. `kind` is 'column' (one row per column) or 'key' (one row per key column).
FIELDS = ("kind", "table_schema", "table_name", "column_name", "data_type", "ordinal_position",
          "constraint_type", "constraint_name", "ref_schema", "ref_table", "ref_column")
KINDS = ("column", "key")
CONSTRAINT_TYPES = ("PRIMARY KEY", "FOREIGN KEY")
_SYSTEM_SCHEMAS = ("INFORMATION_SCHEMA", "sys", "guest", "db_owner", "db_accessadmin", "db_securityadmin",
                   "db_ddladmin", "db_backupoperator", "db_datareader", "db_datawriter", "db_denydatareader",
                   "db_denydatawriter")

# One result set, every schema of the database: the column rows of schema.COLUMNS_SQL and the key rows of
# schema.KEYS_SQL, joined the same way (constraint names are unique per schema, so every join carries it), with NULL
# where a field does not apply. Only INFORMATION_SCHEMA views; a sign-in that can see the tables' metadata
# (db_datareader, or VIEW DEFINITION) is enough, and nothing is written.
EXPORT_SQL = """-- Krusgraph schema export: names, types and declared keys only; no rows are read
SET NOCOUNT ON;
SELECT 'column' AS kind, c.TABLE_SCHEMA AS table_schema, c.TABLE_NAME AS table_name, c.COLUMN_NAME AS column_name,
       c.DATA_TYPE AS data_type, c.ORDINAL_POSITION AS ordinal_position,
       CAST(NULL AS NVARCHAR(20)) AS constraint_type, CAST(NULL AS NVARCHAR(128)) AS constraint_name,
       CAST(NULL AS NVARCHAR(128)) AS ref_schema, CAST(NULL AS NVARCHAR(128)) AS ref_table,
       CAST(NULL AS NVARCHAR(128)) AS ref_column
FROM INFORMATION_SCHEMA.COLUMNS c
JOIN INFORMATION_SCHEMA.TABLES t
  ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME AND t.TABLE_TYPE = 'BASE TABLE'
WHERE c.TABLE_SCHEMA NOT IN ({system})
UNION ALL
SELECT 'key', tc.TABLE_SCHEMA, tc.TABLE_NAME, kcu.COLUMN_NAME, NULL, kcu.ORDINAL_POSITION,
       tc.CONSTRAINT_TYPE, tc.CONSTRAINT_NAME, ref.TABLE_SCHEMA, ref.TABLE_NAME, refcol.COLUMN_NAME
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
  ON kcu.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA AND kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
LEFT JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
  ON rc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA AND rc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
LEFT JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS ref
  ON ref.CONSTRAINT_SCHEMA = rc.UNIQUE_CONSTRAINT_SCHEMA AND ref.CONSTRAINT_NAME = rc.UNIQUE_CONSTRAINT_NAME
LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE refcol
  ON refcol.CONSTRAINT_SCHEMA = rc.UNIQUE_CONSTRAINT_SCHEMA AND refcol.CONSTRAINT_NAME = rc.UNIQUE_CONSTRAINT_NAME
 AND refcol.ORDINAL_POSITION = kcu.ORDINAL_POSITION
WHERE tc.CONSTRAINT_TYPE IN ('PRIMARY KEY', 'FOREIGN KEY') AND tc.TABLE_SCHEMA NOT IN ({system})
ORDER BY kind, table_schema, table_name, constraint_name, ordinal_position;
""".format(system=", ".join("'" + s + "'" for s in _SYSTEM_SCHEMAS))


class ExportError(ValueError):
    """The file is not a Krusgraph schema export, or holds something an export must not hold."""


def export_sql() -> str:
    """The query to hand to the DBA, as text."""
    return EXPORT_SQL


def _none(v):
    if v is None:
        return None
    v = str(v).strip()
    return None if v == "" or v.upper() == "NULL" else v


def rows(text: str) -> list[dict]:
    """The export's rows as dicts with exactly `FIELDS`, from CSV (a header row first; sqlcmd's dashed line under it
    is skipped) or JSON (a list of objects, as FOR JSON or a tool's 'save as JSON' writes). Raises ExportError on any
    other column, kind or constraint type."""
    text = text.lstrip("﻿").strip()
    if not text:
        raise ExportError("the file is empty")
    if text[0] in "[{":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ExportError(f"not valid JSON: {e.msg} at line {e.lineno}") from None
        if isinstance(data, dict):
            data = data.get("rows", data.get("value"))
        if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
            raise ExportError("JSON must be a list of objects, one per row")
        raw = data
    else:
        reader = csv.reader(io.StringIO(text))
        lines = [r for r in reader if r and any(x.strip() for x in r)]
        header = [h.strip().lower() for h in lines[0]]
        body = [r for r in lines[1:] if not all(set(x.strip()) <= {"-"} for x in r)]   # sqlcmd's ----- line
        for r in body:
            if len(r) != len(header):
                raise ExportError(f"a row has {len(r)} fields, the header {len(header)}: {r[:3]}")
        raw = [dict(zip(header, r)) for r in body]
    out = []
    for i, r in enumerate(raw, 1):
        got = {str(k).strip().lower(): v for k, v in r.items()}
        extra = sorted(set(got) - set(FIELDS))
        if extra:
            raise ExportError(f"columns that are not in a schema export: {extra}. The export holds names, types and "
                              "keys only; run the query from export_sql() unchanged")
        row = {f: _none(got.get(f)) for f in FIELDS}
        if row["kind"] not in KINDS:
            raise ExportError(f"row {i}: kind {row['kind']!r}; an export has only {list(KINDS)}")
        if row["kind"] == "key" and row["constraint_type"] not in CONSTRAINT_TYPES:
            raise ExportError(f"row {i}: constraint type {row['constraint_type']!r}; only {list(CONSTRAINT_TYPES)}")
        if not row["table_name"] or not row["column_name"]:
            raise ExportError(f"row {i}: no table or column name")
        if row["ordinal_position"] is not None:
            try:
                row["ordinal_position"] = int(row["ordinal_position"])
            except ValueError:
                raise ExportError(f"row {i}: ordinal_position {row['ordinal_position']!r} is not a number") from None
        out.append(row)
    if not any(r["kind"] == "column" for r in out):
        raise ExportError("no column rows: the file holds no tables")
    return out


def schemas(text: str) -> list[dict]:
    """Every schema in the export with its number of tables, largest first: what a table picker shows first."""
    seen: dict[str, set[str]] = {}
    for r in rows(text):
        if r["kind"] == "column":
            seen.setdefault(r["table_schema"] or "dbo", set()).add(r["table_name"])
    return sorted(({"schema": s, "tables": len(t)} for s, t in seen.items()), key=lambda d: (-d["tables"], d["schema"]))


def parse(text: str, schema: str = "dbo") -> Schema:
    """One schema of the export as a `Schema`, equal to what `Schema.from_sql` reads from the same database: columns
    in their ordinal order, declared primary keys, foreign keys within the schema. Raises ExportError when the file is
    not an export or the schema is not in it."""
    rs = rows(text)
    names = {r["table_schema"] for r in rs if r["kind"] == "column"}
    if schema not in names and schema.lower() not in {(n or "").lower() for n in names}:
        raise ExportError(f"schema {schema!r} is not in the export (it has {sorted(n or 'dbo' for n in names)})")
    want = schema.lower()
    columns = sorted((r for r in rs if r["kind"] == "column" and (r["table_schema"] or "").lower() == want),
                     key=lambda r: (r["table_name"], r["ordinal_position"] or 0))
    keys = sorted((r for r in rs if r["kind"] == "key" and (r["table_schema"] or "").lower() == want),
                  key=lambda r: (r["table_name"], r["constraint_name"] or "", r["ordinal_position"] or 0))
    return Schema.from_information_schema(
        [{k: r[k] for k in ("table_schema", "table_name", "column_name", "data_type", "ordinal_position")} for r in columns],
        [{k: r[k] for k in ("table_name", "constraint_type", "column_name", "ordinal_position", "constraint_name",
                            "ref_table", "ref_column", "ref_schema")} for r in keys],
        schema=schema)


def to_csv(rows_: list[dict]) -> str:
    """Rows with `FIELDS` as the CSV the parser reads (for tests and for a tool that already has the metadata)."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader()
    for r in rows_:
        w.writerow({f: "" if r.get(f) is None else r.get(f) for f in FIELDS})
    return buf.getvalue()
