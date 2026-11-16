"""Connect, the file route (docs/CONNECT-DESIGN.md 1.4): a load notebook for a customer who can only export files.

The customer puts CSV files (and Excel workbooks) under `Files/connect/<entity>/` of a lakehouse. `spec()` takes the
tables and column types from a `Schema` (the schema export of `connect_export.py`, a pack, or a plan's schema) and
`cells()` writes a PySpark notebook that, per entity:

- lists the files of the entity's folder with their modification time (Spark's `binaryFile` source, without the content);
- skips every file whose name is already recorded as loaded, so no file is loaded twice, and says so when such a file has
  changed since;
- reads a new file as text, checks its header against the expected columns, converts each column to its type, and refuses
  the whole file (nothing of it written) when a column is missing, a row has a different number of fields than the header,
  or a value cannot be read as its type (unless ON_BAD_VALUE is "null");
- appends the rows to `bronze.<entity>` and records the file in `bronze.krusgraph_connect_files`;
- reports freshness as the modification time of the newest file in the folder.

The notebook prints and keeps counts, names, types, statuses and times only: never a row or a value. It installs nothing
and calls nothing outside the lakehouse. It writes only tables it created itself (table property `krusgraph.connect`).

Verified, and how (B3, 15 November 2026): unit tests, and the notebook run on a local PySpark 4.0.1 session with parquet
tables (tests/test_b3_connect_files_spark.py; Delta is not available in a local Spark). Not run in Fabric. Two things
rest on Microsoft's documentation and were not tried: that a relative `Files/...` path resolves to the notebook's default
lakehouse, and that the same folder is mounted at `/lakehouse/default` for pandas (used for Excel only).
No tool, route or workload screen uses this module yet.
"""
from __future__ import annotations

import re

from . import notebook
from .schema import Schema

STATE = "krusgraph_connect_files"
FOLDER = "Files/connect"

# A source column type (Spark's, or SQL Server's as the schema export gives it) -> the Spark type the notebook casts to.
# Anything else is kept as text and listed in the notebook's first cell.
_TYPES = {
    "int": "int", "integer": "int", "bigint": "bigint", "long": "bigint", "smallint": "smallint", "short": "smallint",
    "tinyint": "smallint",                                 # SQL Server's tinyint is 0 to 255, Spark's is -128 to 127
    "byte": "smallint", "bit": "boolean", "boolean": "boolean", "bool": "boolean",
    "decimal": "decimal(38,10)", "numeric": "decimal(38,10)", "money": "decimal(19,4)", "smallmoney": "decimal(10,4)",
    "double": "double", "float": "double",                 # SQL Server's float is 8 bytes by default
    "real": "float", "date": "date",
    "timestamp": "timestamp", "timestamp_ntz": "timestamp", "datetime": "timestamp", "datetime2": "timestamp",
    "smalldatetime": "timestamp", "datetimeoffset": "timestamp",
}
_TEXT = {"string", "varchar", "nvarchar", "char", "nchar", "text", "ntext", "uniqueidentifier", "xml", "sysname"}
_DECIMAL = re.compile(r"^(decimal|numeric)\s*\(\s*(\d{1,2})\s*(?:,\s*(\d{1,2})\s*)?\)$")
_SAFE_NAME = re.compile(r"^[^/\\*?\[\]{}`\x00-\x1f]+$")     # a folder name and a table name: no path, glob or quote characters
_ALLOWED_OVERRIDES = set(_TYPES.values()) | {"string"}


def spark_type(data_type: str) -> tuple[str, bool]:
    """(the Spark type a column is cast to, whether the source type was recognised)."""
    t = " ".join(str(data_type or "string").lower().split())
    m = _DECIMAL.match(t)
    if m:
        precision, scale = int(m.group(2)), int(m.group(3) or 0)
        if 1 <= precision <= 38 and scale <= precision:
            return f"decimal({precision},{scale})", True
    base = t.split("(")[0].strip()
    if base in _TYPES:
        return _TYPES[base], True
    return "string", base in _TEXT


def _check_name(kind: str, name: str) -> str:
    if not name or name != name.strip() or name in (".", "..") or not _SAFE_NAME.match(name):
        raise ValueError(f"The {kind} name {name!r} cannot be a folder under Files/connect or a table name "
                         "(no slash, backslash, backtick, wildcard or leading or trailing space). Nothing was written.")
    return name


def spec(schema: Schema, tables: list[str] | None = None, bronze_schema: str = "bronze", folder: str = FOLDER,
         schemas_enabled: bool = True, types: dict[str, dict[str, str]] | None = None, owner: str | None = None) -> dict:
    """What the notebook loads: one entity per table of `schema` (or of `tables`), each with its columns and Spark types.

    `types` overrides a column's type per table ({"orders": {"row_version": "string"}}); `owner` is the mark written on
    every table the notebook creates (default: the source schema's name), so it never appends to someone else's table."""
    wanted = list(tables) if tables is not None else [t.name for t in schema]
    missing = [t for t in wanted if t not in schema]
    if missing:
        raise ValueError(f"Not in the schema {schema.schema!r}: {', '.join(missing)}. It holds: "
                         f"{', '.join(t.name for t in schema) or 'no tables'}.")
    if not wanted:
        raise ValueError("No tables to load: the schema is empty.")
    _check_name("bronze schema", bronze_schema)
    overrides = types or {}
    for table, cols in overrides.items():
        if table not in wanted:
            raise ValueError(f"types names the table {table!r}, which is not loaded.")
        for column, t in cols.items():
            if not schema[table].has(column):
                raise ValueError(f"types names the column {table}.{column}, which the table does not have.")
            if t not in _ALLOWED_OVERRIDES and not _DECIMAL.match(t):
                raise ValueError(f"types gives {table}.{column} the type {t!r}; use one of {', '.join(sorted(_ALLOWED_OVERRIDES))} "
                                 "or decimal(p,s).")
    entities = []
    for name in wanted:
        table = schema[name]
        _check_name("table", name)
        if name.lower() == STATE:
            raise ValueError(f"A table cannot be called {STATE}: the notebook keeps its own record there.")
        if not table.column_names:
            raise ValueError(f"The table {name} has no columns to load.")
        seen: set[str] = set()
        columns = []
        by_name = {c.name: c for c in table.columns}
        over = {k.lower(): v for k, v in overrides.get(name, {}).items()}
        for col in table.column_names:
            if col.lower() in seen:
                raise ValueError(f"The table {name} has the column {col} twice (names differ only in case).")
            seen.add(col.lower())
            cast, known = spark_type(over.get(col.lower()) or by_name[col].data_type)
            columns.append({"name": col, "type": cast, "source_type": by_name[col].data_type, "known": known})
        entities.append({"entity": name, "columns": columns})
    lowered = [e["entity"].lower() for e in entities]
    if len(set(lowered)) != len(lowered):
        raise ValueError("Two tables have the same name but for case; a folder and a table per entity need distinct names.")
    return {"folder": folder.rstrip("/"), "bronze_schema": bronze_schema, "schemas_enabled": bool(schemas_enabled),
            "owner": owner or f"connect-files/{schema.schema}", "source_schema": schema.schema, "entities": entities}


def kept_as_text(s: dict) -> list[str]:
    """`table.column (source type)` for every column whose source type was not recognised and is loaded as text."""
    return [f"{e['entity']}.{c['name']} ({c['source_type']})" for e in s["entities"] for c in e["columns"] if not c["known"]]


def _table_name(s: dict, table: str) -> str:
    return f"{s['bronze_schema']}.{table}" if s["schemas_enabled"] else f"{s['bronze_schema']}_{table}"


PARAMETERS = '''CONNECT_FOLDER = {folder}   # one folder per entity under it, in this notebook's default lakehouse
BRONZE_SCHEMA = {bronze}       # where the tables go (on a lakehouse without schemas: a prefix)
TABLE_FORMAT = "delta"         # lakehouse tables are Delta; leave as it is
DELIMITER = ","                # the field separator of the CSV files; many exports use ";"
ENCODING = "UTF-8"             # the CSV files' encoding, for example "windows-1252"
DECIMAL_COMMA = False          # True when numbers are written 1234,5 (spaces are removed; 1.234,5 is refused)
DATE_FORMAT = ""               # "" reads 2026-11-15; otherwise a Spark pattern such as "dd.MM.yyyy"
TIMESTAMP_FORMAT = ""          # "" reads 2026-11-15 08:30:00; otherwise a Spark pattern
ON_BAD_VALUE = "refuse"        # "refuse": a file with a value that is not of its column's type is not loaded at all;
                               # "null": the file is loaded with those values empty, and the count is reported
READ_EXCEL = True              # .xlsx files are read with pandas and openpyxl (first sheet); False leaves them unread
LOCAL_FILES_ROOT = "/lakehouse/default"   # where the default lakehouse is mounted for pandas (Excel only)'''

SETUP = '''import json
import os
from datetime import datetime, timezone
from urllib.parse import unquote, urlparse

from pyspark.sql import functions as F

# entity -> its columns and the type each is converted to. Written by Krusgraph from the schema; edit a type here if the
# files hold something else.
ENTITIES = {entities}
SCHEMAS_ENABLED = {schemas_enabled}
# Written on every table this notebook creates as the property krusgraph.connect: a table carrying another value (or none)
# belongs to someone else, and this notebook never writes to it.
OWNER = {owner}
STATE = {state}
RUN_AT = datetime.now(timezone.utc).replace(microsecond=0)
NUMERIC = ("int", "bigint", "smallint", "double", "float", "decimal")

if ON_BAD_VALUE not in ("refuse", "null"):
    raise ValueError('ON_BAD_VALUE is "refuse" or "null". Nothing was written.')
if len(DELIMITER) != 1:
    raise ValueError("DELIMITER is one character. Nothing was written.")


def q(*parts):
    """A table name with every part quoted, for names with spaces or other characters."""
    return ".".join("`" + str(p).replace("`", "``") + "`" for p in parts if p)


def target(table):
    return q(BRONZE_SCHEMA, table) if SCHEMAS_ENABLED else q(f"{{BRONZE_SCHEMA}}_{{table}}")


def col(name):
    return F.col("`" + name.replace("`", "``") + "`")


def is_ours_or_absent(name):
    if not spark.catalog.tableExists(name):
        return True
    props = {{r[0]: r[1] for r in spark.sql(f"SHOW TBLPROPERTIES {{name}}").collect()}}
    return props.get("krusgraph.connect") == OWNER


# Guard before anything is read or written: no target is someone else's table.
for _t in list(ENTITIES) + [STATE]:
    if not is_ours_or_absent(target(_t)):
        raise ValueError(f"{{target(_t)}} exists and was not written by this notebook (for {{OWNER}}); nothing was written. "
                         "Choose another BRONZE_SCHEMA.")
if SCHEMAS_ENABLED:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {{q(BRONZE_SCHEMA)}}")


def append(df, table):
    name = target(table)
    if not is_ours_or_absent(name):
        raise ValueError(f"{{name}} exists and was not written by this notebook; it was left as it is.")
    new = not spark.catalog.tableExists(name)
    df.write.format(TABLE_FORMAT).mode("append").saveAsTable(name)
    if new:
        spark.sql(f"ALTER TABLE {{name}} SET TBLPROPERTIES ('krusgraph.connect' = '{{OWNER.replace(chr(39), chr(39) * 2)}}')")


STATE_COLUMNS = "entity string, file_name string, file_modified timestamp, file_bytes long, status string, rows long, at timestamp"


def record(entity, f, status, rows=None):
    """One line per event, appended: 'started' before a file's rows are written, 'loaded' after, 'refused' with no rows."""
    row = [(entity, f["name"], f["modified"], f["bytes"], status, rows, datetime.now(timezone.utc).replace(microsecond=0))]
    append(spark.createDataFrame(row, STATE_COLUMNS), STATE)


def recorded(entity):
    """file name -> its 'started' and 'loaded' lines, for the files of one entity."""
    out = {{}}
    if spark.catalog.tableExists(target(STATE)):
        lines = spark.read.table(target(STATE)).filter(F.col("entity") == entity)
        for r in lines.withColumn("modified_s", F.col("file_modified").cast("long")).collect():
            out.setdefault(r["file_name"], {{}})[r["status"]] = r
    return out


def list_files(entity):
    """The entity's files with name, modification time (UTC, whole seconds) and size. The content is not read here."""
    try:
        rows = (spark.read.format("binaryFile").load(f"{{CONNECT_FOLDER}}/{{entity}}")
                .select("path", F.col("modificationTime").cast("long").alias("modified_s"), "length").collect())
    except Exception as e:  # noqa: BLE001 - the folder does not exist yet: nothing to load, said in the summary
        if "PATH_NOT_FOUND" in str(e) or "Path does not exist" in str(e):
            return None
        raise
    files = [{{"path": r["path"], "name": unquote(os.path.basename(urlparse(r["path"]).path)), "modified_s": r["modified_s"],
              "modified": datetime.fromtimestamp(r["modified_s"], timezone.utc), "bytes": r["length"]}} for r in rows]
    return sorted(files, key=lambda f: (f["modified_s"], f["name"]))


def read_csv(f):
    return (spark.read.option("header", "true").option("sep", DELIMITER).option("encoding", ENCODING)
            .option("quote", '"').option("escape", '"').option("multiLine", "true").option("mode", "FAILFAST")
            .option("inferSchema", "false").csv(f["path"]))


def read_xlsx(entity, f):
    import pandas as pd
    local = os.path.join(LOCAL_FILES_ROOT, CONNECT_FOLDER, entity, f["name"])
    pdf = pd.read_excel(local, sheet_name=0, dtype=str, engine="openpyxl")
    names = [str(c) for c in pdf.columns]
    rows = [tuple(None if pd.isna(v) else str(v) for v in r) for r in pdf.itertuples(index=False, name=None)]
    return spark.createDataFrame(rows, ", ".join("`" + n.replace("`", "``") + "` string" for n in names))


def typed(name, kind, as_text):
    """One column converted to its type. A value that cannot be read becomes NULL here and is counted by the caller.
    try_cast and try_to_timestamp return NULL instead of stopping, with ANSI mode on or off."""
    if kind == "string":
        return col(name)
    text = "trim(`" + name.replace("`", "``") + "`)"
    if as_text and DECIMAL_COMMA and kind.startswith(NUMERIC):
        text = f"replace(translate({{text}}, ' {{chr(160)}}', ''), ',', '.')"      # 1 234,5 -> 1234.5; a space or a no-break space
    if as_text and kind == "date" and DATE_FORMAT:
        return F.try_to_timestamp(F.expr(text), F.lit(DATE_FORMAT)).cast("date")
    if as_text and kind == "timestamp" and TIMESTAMP_FORMAT:
        return F.try_to_timestamp(F.expr(text), F.lit(TIMESTAMP_FORMAT))
    return F.expr(f"try_cast({{text}} as {{kind}})")


summary = {{}}


def load(entity):
    """Load the entity's new files into its bronze table. Counts, names and times only are kept and printed."""
    columns = ENTITIES[entity]
    out = {{"files_found": 0, "loaded": [], "skipped": [], "refused": [], "rows_loaded": 0, "newest_file": None}}
    summary[entity] = out
    files = list_files(entity)
    if files is None:
        out["folder"] = f"{{CONNECT_FOLDER}}/{{entity}} does not exist yet"
        return out
    out["files_found"] = len(files)
    if files:
        out["newest_file"] = max(f["modified"] for f in files).strftime("%Y-%m-%dT%H:%M:%SZ")
    seen = recorded(entity)
    for f in files:
        lines = seen.get(f["name"], {{}})
        ext = os.path.splitext(f["name"])[1].lower()
        if "loaded" in lines:
            was = lines["loaded"]
            changed = was["modified_s"] != f["modified_s"] or was["file_bytes"] != f["bytes"]
            out["skipped"].append({{"file": f["name"], "why": "loaded before; the file has changed since and was not loaded again "
                                   "(give a corrected file a new name)" if changed else "loaded before"}})
            continue
        if "started" in lines:
            out["skipped"].append({{"file": f["name"], "why": "a run stopped while loading this file; a person must check "
                                   f"{{target(entity)}} before it is loaded again"}})
            continue
        if ext not in (".csv", ".xlsx") or (ext == ".xlsx" and not READ_EXCEL):
            out["skipped"].append({{"file": f["name"], "why": "not read: not a .csv or .xlsx file" if ext not in (".csv", ".xlsx")
                                   else "not read: READ_EXCEL is False"}})
            continue
        why, bad, rows, df = None, {{}}, None, None
        try:
            raw = read_csv(f) if ext == ".csv" else read_xlsx(entity, f)
            have = {{c.lstrip("\\ufeff").strip().lower(): c for c in raw.columns}}
            missing = [c for c, _ in columns if c.lower() not in have]
            if missing:
                why = "missing column(s): " + ", ".join(missing)
            else:
                extra = sorted(set(have) - {{c.lower() for c, _ in columns}})
                if extra:
                    out.setdefault("columns_ignored", {{}})[f["name"]] = extra
                raw = raw.select(*[col(have[c.lower()]).alias(c) for c, _ in columns])
                df = raw.select(*[typed(c, kind, ext == ".csv").alias(c) for c, kind in columns])
                checks = [F.count(F.lit(1)).alias("_rows")] + [
                    F.sum(F.when(col(c).isNotNull() & (F.trim(col(c)) != "") & typed(c, kind, ext == ".csv").isNull(), 1)
                          .otherwise(0)).alias(c) for c, kind in columns if kind != "string"]
                counted = raw.agg(*checks).collect()[0].asDict()
                rows = counted.pop("_rows")
                bad = {{c: int(n) for c, n in counted.items() if n}}
                if bad and ON_BAD_VALUE == "refuse":
                    why = "value(s) that are not of the column's type: " + ", ".join(f"{{c}} ({{n}})" for c, n in bad.items())
        except Exception as e:  # noqa: BLE001 - the file could not be read: refused with the kind of error, never its text
            malformed = "MALFORMED" in str(e) or "Malformed" in str(e)
            why = ("a row has a different number of fields than the header" if malformed
                   else f"could not be read ({{type(e).__name__}})")
        if why:
            record(entity, f, "refused")
            out["refused"].append({{"file": f["name"], "why": why}})
            continue
        record(entity, f, "started")
        append(df, entity)
        record(entity, f, "loaded", rows)
        out["loaded"].append({{"file": f["name"], "rows": rows, **({{"values_left_empty": bad}} if bad else {{}})}})
        out["rows_loaded"] += rows
    return out
'''

FINISH = '''# ---- summary: counts, names and times only ----
for _e in ENTITIES:
    summary[_e]["bronze_rows"] = spark.read.table(target(_e)).count() if spark.catalog.tableExists(target(_e)) else 0
RESULT = {"run_at": RUN_AT.strftime("%Y-%m-%dT%H:%M:%SZ"), "folder": CONNECT_FOLDER, "entities": summary}
print(json.dumps(RESULT, indent=2, ensure_ascii=False))
'''


def cells(s: dict) -> list[tuple[str, str]]:
    """The notebook as (kind, text) cells: an introduction, the parameters, the setup, one cell per entity, the summary."""
    names = [e["entity"] for e in s["entities"]]
    text = kept_as_text(s)
    intro = (f"# Load file exports into {s['bronze_schema']}\n\n"
             f"Generated by Krusgraph for {len(names)} table(s) of `{s['source_schema']}`. Put each table's exported files in "
             f"its own folder under `{s['folder']}/` of this notebook's default lakehouse, for example "
             f"`{s['folder']}/{names[0]}/{names[0]}_2026-11-15.csv`, with the column names in the first row. CSV files and "
             "Excel workbooks (.xlsx, first sheet) are read.\n\n"
             f"Each run appends the files it has not loaded before to `{_table_name(s, '<table>')}` and records them in "
             f"`{_table_name(s, STATE)}`. A file is known by its name: it is never loaded twice, so give a corrected file a new "
             "name. A file with a missing column, a row with too few or too many fields, or a value that is not of its "
             "column's type is refused whole and nothing of it is written; the summary says why with counts, never with "
             "values. Freshness is the time of the newest file in each folder.\n\n"
             "The notebook reads only the files and writes only tables it created itself. It installs nothing and sends "
             "nothing anywhere.")
    if text:
        intro += ("\n\nLoaded as text, because the source type is not one this notebook converts: " + ", ".join(text) + ".")
    params = PARAMETERS.format(folder=repr(s["folder"]), bronze=repr(s["bronze_schema"]))
    entities = "{\n" + "".join(f"    {e['entity']!r}: {[(c['name'], c['type']) for c in e['columns']]!r},\n" for e in s["entities"]) + "}"
    setup = SETUP.format(entities=entities, schemas_enabled="True" if s["schemas_enabled"] else "False", owner=repr(s["owner"]),
                         state=repr(STATE))
    out = [("markdown", intro), ("parameters", params), ("code", setup.strip("\n"))]
    out += [("code", f"load({name!r})") for name in names]
    out.append(("code", FINISH.strip("\n")))
    return out


def source(s: dict, workspace_id: str = "", lakehouse_id: str = "", lakehouse_name: str = "") -> str:
    """The notebook as Fabric's notebook-content.py, with the lakehouse as its default when one is given."""
    return notebook.fabric_source(cells(s), notebook.notebook_metadata(workspace_id, lakehouse_id, lakehouse_name))
