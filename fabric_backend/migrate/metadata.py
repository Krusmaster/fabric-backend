"""Read the metadata a Snowflake database or an Azure Databricks Unity Catalog schema ships, from files the customer
exported (round MG1). Nothing here connects to anything: the customer runs the queries in
docs/MIGRATE-DATABRICKS-SNOWFLAKE.md section 2 in their own tool and saves each result as a CSV file in one folder
(or all of them in one JSON file). This module reads that folder.

Files read (a missing optional file means "nothing of that kind"; names are case-insensitive, `.csv` or `.json`):

  both sources   tables (required), columns (required), views, functions (Snowflake) / routines (Databricks)
  Snowflake      primary_keys, unique_keys, imported_keys   (SHOW PRIMARY | UNIQUE | IMPORTED KEYS IN SCHEMA ...)
  Databricks     constraints                                (information_schema TABLE_CONSTRAINTS joined to
                                                             KEY_COLUMN_USAGE and REFERENTIAL_CONSTRAINTS)
                 row_filters, column_masks                  (information_schema ROW_FILTERS, COLUMN_MASKS)

Column names in the files are matched without case and without surrounding quotes, so an export with "TABLE_NAME" or
table_name reads the same. Rows of other schemas than the one asked for are left out and counted. Everything not
understood is listed in SourceModel.ignored, never guessed.

A declared PRIMARY KEY, UNIQUE or FOREIGN KEY is read as what it is: a declaration. Snowflake does not enforce them on
standard tables (Snowflake's page could not be opened from this session: Unverified) and Azure Databricks says they
"are informational only and aren't enforced" (learn.microsoft.com/azure/databricks/tables/constraints, read 16 November
2026). They become candidates with the provenance "declared by metadata (Snowflake|Databricks)" and are counted in the
rows like any other key or link.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

SOURCES = ("snowflake", "databricks")
LABEL = {"snowflake": "Snowflake", "databricks": "Databricks"}


def provenance(source: str) -> str:
    return f"declared by metadata ({LABEL[source]})"


def rule(source: str) -> str:
    return f"{LABEL[source]} metadata"


@dataclass
class SrcColumn:
    name: str
    data_type: str
    nullable: bool | None = None
    comment: str | None = None


@dataclass
class SrcTable:
    schema: str
    name: str
    raw_type: str                      # TABLE_TYPE as exported: BASE TABLE, VIEW, MANAGED, EXTERNAL, ...
    kind: str = "table"                # table | view | materialized view | streaming table | foreign | external
    columns: list[SrcColumn] = field(default_factory=list)
    comment: str | None = None
    format: str | None = None          # Databricks data_source_format (DELTA, PARQUET, ...)
    flags: list[str] = field(default_factory=list)   # transient, temporary, dynamic, iceberg, external, row filter, column mask
    row_count: int | None = None       # Snowflake TABLES.ROW_COUNT, as the metadata says (not counted)
    primary_key: list[str] = field(default_factory=list)
    uniques: list[list[str]] = field(default_factory=list)
    foreign_keys: list[dict] = field(default_factory=list)   # {name, columns, ref_table, ref_columns, ref_schema}
    view_sql: str | None = None


@dataclass
class SourceModel:
    source: str
    schema: str
    tables: dict[str, SrcTable] = field(default_factory=dict)     # by name as exported
    functions: list[str] = field(default_factory=list)            # user-defined function names (upper case)
    files: list[str] = field(default_factory=list)
    ignored: list[dict] = field(default_factory=list)
    other_schemas: int = 0

    def table(self, name: str) -> SrcTable | None:
        if name in self.tables:
            return self.tables[name]
        low = {n.lower(): t for n, t in self.tables.items()}
        return low.get(str(name).lower())


# ------------------------------------------------------------------------------------------------------------ files

def _key(k: str) -> str:
    return str(k or "").strip().strip('"').strip("`").strip().lower()


def _rows_of(text: str, suffix: str) -> list[dict]:
    if suffix == ".json":
        data = json.loads(text)
        if isinstance(data, dict):            # {"rows": [...]} or {"data": [...]}
            data = data.get("rows") or data.get("data") or []
        return [{_key(k): v for k, v in r.items()} for r in data]
    return [{_key(k): v for k, v in r.items()} for r in csv.DictReader(io.StringIO(text))]


def _files(path: Path) -> dict[str, list[dict]]:
    """{kind: rows} from a folder of exports or one JSON file {kind: rows}."""
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{path}: a JSON export is one object {{\"tables\": [...], \"columns\": [...], ...}}")
        return {k.lower(): [{_key(c): v for c, v in r.items()} for r in rows] for k, rows in data.items() if isinstance(rows, list)}
    if not path.is_dir():
        raise ValueError(f"{path}: no such file or folder")
    out = {}
    for f in sorted(path.iterdir()):
        if f.suffix.lower() in (".csv", ".json") and f.is_file():
            out[f.stem.lower()] = _rows_of(f.read_text(encoding="utf-8-sig"), f.suffix.lower())
    return out


def _get(r: dict, *names, default=None):
    for n in names:
        if n in r and r[n] not in (None, ""):
            return r[n]
    return default


def _yes(v) -> bool:
    return str(v or "").strip().upper() in ("YES", "Y", "TRUE", "1")


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------------------ read

def read(path, source: str, schema: str | None = None) -> SourceModel:
    """The folder (or JSON file) of exports for one schema. `schema`: which schema to keep when the export holds more;
    None keeps the only one (two or more without `schema` is an error that names them)."""
    source = str(source).lower()
    if source not in SOURCES:
        raise ValueError(f"source must be one of {', '.join(SOURCES)}, not {source!r}")
    path = Path(path)
    files = _files(path)
    for need in ("tables", "columns"):
        if need not in files:
            raise ValueError(f"{path}: no {need}.csv (or {need} in the JSON file); docs/MIGRATE-DATABRICKS-SNOWFLAKE.md section 2 has the query")
    schemas = sorted({str(_get(r, "table_schema", "schema_name")) for r in files["tables"] if _get(r, "table_schema", "schema_name")})
    if schema is None:
        if len(schemas) > 1:
            raise ValueError(f"the export holds {len(schemas)} schemas ({', '.join(schemas)}); say which one")
        schema = schemas[0] if schemas else "default"
    m = SourceModel(source=source, schema=schema, files=sorted(files))
    same = lambda r: str(_get(r, "table_schema", "schema_name", default=schema)).lower() == schema.lower()

    for r in files["tables"]:
        if not same(r):
            m.other_schemas += 1
            continue
        name = _get(r, "table_name", "name")
        raw = str(_get(r, "table_type", "kind", default="BASE TABLE")).upper()
        t = SrcTable(schema=schema, name=name, raw_type=raw, comment=_get(r, "comment", "table_comment"),
                     format=(str(_get(r, "data_source_format", default="")).upper() or None), row_count=_int(_get(r, "row_count")))
        if source == "snowflake":
            t.kind = {"VIEW": "view", "MATERIALIZED VIEW": "materialized view", "EXTERNAL TABLE": "external",
                      "TEMPORARY TABLE": "table", "LOCAL TEMPORARY": "table", "EVENT TABLE": "table"}.get(raw, "table")
            if raw in ("TEMPORARY TABLE", "LOCAL TEMPORARY"):
                t.flags.append("temporary")
            if raw == "EXTERNAL TABLE":
                t.flags.append("external")
            if raw == "EVENT TABLE":
                t.flags.append("event table")
            for flag, cols in (("transient", ("is_transient",)), ("iceberg", ("is_iceberg",)), ("dynamic", ("is_dynamic",)),
                               ("hybrid", ("is_hybrid",))):
                if _yes(_get(r, *cols)):
                    t.flags.append(flag)
        else:
            t.kind = {"VIEW": "view", "METRIC_VIEW": "view", "MATERIALIZED_VIEW": "materialized view",
                      "STREAMING_TABLE": "streaming table", "FOREIGN": "foreign", "EXTERNAL": "table", "MANAGED": "table",
                      "EXTERNAL_SHALLOW_CLONE": "table", "MANAGED_SHALLOW_CLONE": "table"}.get(raw, "table")
            if raw == "METRIC_VIEW":
                t.flags.append("metric view")
            if raw.startswith("EXTERNAL"):
                t.flags.append("external")
            if raw == "FOREIGN":
                t.flags.append("federated")
            if raw not in ("VIEW", "METRIC_VIEW", "MATERIALIZED_VIEW", "STREAMING_TABLE", "FOREIGN", "EXTERNAL", "MANAGED",
                           "EXTERNAL_SHALLOW_CLONE", "MANAGED_SHALLOW_CLONE"):
                m.ignored.append({"what": f"table {name}", "why": f"table_type {raw} is not one this reader knows; read as a table"})
        m.tables[name] = t

    cols = sorted((r for r in files["columns"] if same(r)), key=lambda r: (str(_get(r, "table_name")), _int(_get(r, "ordinal_position")) or 0))
    for r in cols:
        t = m.table(_get(r, "table_name"))
        if t is None:
            m.ignored.append({"what": f"column {_get(r, 'table_name')}.{_get(r, 'column_name')}", "why": "its table is not in tables.csv"})
            continue
        ty = str(_get(r, "full_data_type", "data_type", default="")).upper()
        nul = _get(r, "is_nullable")
        t.columns.append(SrcColumn(_get(r, "column_name"), ty, None if nul is None else _yes(nul), _get(r, "comment", "column_comment")))

    for r in files.get("views", []):
        if not same(r):
            continue
        t = m.table(_get(r, "table_name", "name"))
        if t is not None:
            t.view_sql = _get(r, "view_definition", "text", "definition")

    fn_file = files.get("functions") or files.get("routines") or []
    m.functions = sorted({str(_get(r, "function_name", "routine_name", "name")).upper() for r in fn_file
                          if same(r) and _get(r, "function_name", "routine_name", "name")})

    if source == "snowflake":
        _snowflake_keys(m, files)
    else:
        _databricks_keys(m, files)
        for kind, flag in (("row_filters", "row filter"), ("column_masks", "column mask")):
            for r in files.get(kind, []):
                t = m.table(_get(r, "table_name"))
                if t is not None and same(r) and flag not in t.flags:
                    t.flags.append(flag)

    known = {"tables", "columns", "views", "functions", "routines", "primary_keys", "unique_keys", "imported_keys",
             "constraints", "row_filters", "column_masks"}
    for k in sorted(set(files) - known):
        m.ignored.append({"what": f"file {k}", "why": "not one of the exports this reader reads"})
    return m


def _snowflake_keys(m: SourceModel, files: dict) -> None:
    """SHOW PRIMARY KEYS / UNIQUE KEYS / IMPORTED KEYS output (RESULT_SCAN saved as CSV): one row per column with
    key_sequence; constraint_name (or pk_name / fk_name) groups them."""
    def same(r, k="schema_name"):
        s = _get(r, k, "schema_name", "table_schema")
        return s is None or str(s).lower() == m.schema.lower()
    groups: dict = {}
    for kind in ("primary_keys", "unique_keys"):
        for r in files.get(kind, []):
            if not same(r):
                continue
            key = (kind, _get(r, "table_name"), _get(r, "constraint_name", default=""))
            groups.setdefault(key, []).append((_int(_get(r, "key_sequence")) or 0, _get(r, "column_name")))
    for (kind, table, _), cols in sorted(groups.items(), key=lambda x: (x[0][0], str(x[0][1]), str(x[0][2]))):
        t = m.table(table)
        if t is None:
            m.ignored.append({"what": f"{kind} on {table}", "why": "its table is not in tables.csv"})
            continue
        c = [n for _, n in sorted(cols)]
        if kind == "primary_keys":
            t.primary_key = c
        else:
            t.uniques.append(c)
    fks: dict = {}
    for r in files.get("imported_keys", []):
        if not same(r, "fk_schema_name"):
            continue
        key = (_get(r, "fk_table_name"), _get(r, "fk_name", default=""), _get(r, "pk_table_name"))
        fks.setdefault(key, {"ref_schema": _get(r, "pk_schema_name"), "cols": []})["cols"].append(
            (_int(_get(r, "key_sequence")) or 0, _get(r, "fk_column_name"), _get(r, "pk_column_name")))
    for (table, name, ref), v in sorted(fks.items(), key=lambda x: tuple(str(p) for p in x[0])):
        _add_fk(m, table, name, ref, v["ref_schema"], v["cols"])


def _databricks_keys(m: SourceModel, files: dict) -> None:
    """One row per constraint column: table_name, constraint_name, constraint_type, column_name, ordinal_position and,
    for a foreign key, ref_schema, ref_table, ref_column (the query in the doc joins them)."""
    pk: dict = {}
    fks: dict = {}
    for r in files.get("constraints", []):
        s = _get(r, "table_schema")
        if s is not None and str(s).lower() != m.schema.lower():
            continue
        ctype = str(_get(r, "constraint_type", default="")).upper()
        table, name = _get(r, "table_name"), _get(r, "constraint_name", default="")
        pos = _int(_get(r, "ordinal_position")) or 0
        if ctype in ("PRIMARY KEY", "UNIQUE"):
            pk.setdefault((ctype, table, name), []).append((pos, _get(r, "column_name")))
        elif ctype == "FOREIGN KEY":
            fks.setdefault((table, name, _get(r, "ref_table")), {"ref_schema": _get(r, "ref_schema"), "cols": []})["cols"].append(
                (pos, _get(r, "column_name"), _get(r, "ref_column")))
        else:
            m.ignored.append({"what": f"constraint {name} on {table}", "why": f"constraint_type {ctype or '(empty)'} is not a key"})
    for (ctype, table, _), cols in sorted(pk.items(), key=lambda x: tuple(str(p) for p in x[0])):
        t = m.table(table)
        if t is None:
            m.ignored.append({"what": f"{ctype} on {table}", "why": "its table is not in tables.csv"})
            continue
        c = [n for _, n in sorted(cols)]
        if ctype == "PRIMARY KEY":
            t.primary_key = c
        else:
            t.uniques.append(c)
    for (table, name, ref), v in sorted(fks.items(), key=lambda x: tuple(str(p) for p in x[0])):
        _add_fk(m, table, name, ref, v["ref_schema"], v["cols"])


def _add_fk(m: SourceModel, table, name, ref, ref_schema, cols) -> None:
    t = m.table(table)
    if t is None:
        m.ignored.append({"what": f"foreign key {name} on {table}", "why": "its table is not in tables.csv"})
        return
    if ref_schema and str(ref_schema).lower() != m.schema.lower():
        m.ignored.append({"what": f"foreign key {name} on {table}", "why": f"it points into schema {ref_schema}, outside this plan"})
        return
    cols = sorted(cols)
    if not ref or any(not c or not rc for _, c, rc in cols):
        m.ignored.append({"what": f"foreign key {name} on {table}", "why": "the export does not name every referenced column"})
        return
    t.foreign_keys.append({"name": name, "columns": [c for _, c, _ in cols], "ref_table": ref,
                           "ref_columns": [rc for _, _, rc in cols], "ref_schema": ref_schema})


def summary(m: SourceModel) -> dict:
    kinds: dict[str, int] = {}
    for t in m.tables.values():
        kinds[t.kind] = kinds.get(t.kind, 0) + 1
    return {
        "source": LABEL[m.source], "schema": m.schema, "files": m.files, "objects": kinds,
        "declared_primary_keys": sum(1 for t in m.tables.values() if t.primary_key),
        "declared_unique": sum(len(t.uniques) for t in m.tables.values()),
        "declared_foreign_keys": sum(len(t.foreign_keys) for t in m.tables.values()),
        "comments": sum(1 for t in m.tables.values() if t.comment) + sum(1 for t in m.tables.values() for c in t.columns if c.comment),
        "views_with_sql": sum(1 for t in m.tables.values() if t.view_sql),
        "user_functions": len(m.functions), "other_schemas_left_out": m.other_schemas,
        "ignored": m.ignored, "provenance": provenance(m.source),
        "note": "metadata only: declared keys are candidates until counted in the rows",
    }


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())
