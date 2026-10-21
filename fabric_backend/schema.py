"""Read what tables and columns exist, from whichever side of Fabric you are on.

Three ways in, one `Schema` out:

- `Schema.from_information_schema(columns, keys)` — rows you got yourself from the SQL analytics
  endpoint or a warehouse (`INFORMATION_SCHEMA.COLUMNS`, optionally key constraints). Pure Python,
  this is what the tests use.
- `Schema.from_sql(execute)` — give it any callable that runs SQL and returns rows (pyodbc cursor,
  `spark.sql(...).collect`, a Fabric SQL database connection); it runs the two INFORMATION_SCHEMA
  queries for you.
- `Schema.from_spark(spark, lakehouse_schema)` — inside a Fabric notebook attached to a lakehouse,
  with no SQL connection at all.

Nothing here infers anything. Keys and relationships are `infer.py`'s job.
"""
from __future__ import annotations

from dataclasses import dataclass, field

TECH_COLS = {"__SEQUENCE_NUMBER", "__TIMESTAMP", "__ROWMARKER__"}

COLUMNS_SQL = """
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, ORDINAL_POSITION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = '{schema}'
ORDER BY TABLE_NAME, ORDINAL_POSITION
"""

# Warehouse / SQL database only; a lakehouse SQL endpoint has no constraints.
KEYS_SQL = """
SELECT tc.TABLE_NAME, tc.CONSTRAINT_TYPE, kcu.COLUMN_NAME, kcu.ORDINAL_POSITION,
       tc.CONSTRAINT_NAME, ref.TABLE_NAME AS REF_TABLE, refcol.COLUMN_NAME AS REF_COLUMN
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
LEFT JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc ON rc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
LEFT JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS ref ON ref.CONSTRAINT_NAME = rc.UNIQUE_CONSTRAINT_NAME
LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE refcol
       ON refcol.CONSTRAINT_NAME = rc.UNIQUE_CONSTRAINT_NAME AND refcol.ORDINAL_POSITION = kcu.ORDINAL_POSITION
WHERE tc.TABLE_SCHEMA = '{schema}' AND tc.CONSTRAINT_TYPE IN ('PRIMARY KEY', 'FOREIGN KEY')
ORDER BY tc.TABLE_NAME, tc.CONSTRAINT_NAME, kcu.ORDINAL_POSITION
"""


@dataclass
class Column:
    name: str
    data_type: str = "string"


@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)          # declared primary key, if any
    foreign_keys: list[tuple[list[str], str, list[str]]] = field(default_factory=list)  # (cols, target, target cols)
    schema: str = "dbo"

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns if c.name.upper() not in TECH_COLS]

    def has(self, col: str) -> bool:
        return col.lower() in {c.lower() for c in self.column_names}

    def col(self, name: str) -> str:
        """Column name in the table's own casing."""
        for c in self.column_names:
            if c.lower() == name.lower():
                return c
        raise KeyError(name)


@dataclass
class Schema:
    tables: dict[str, Table] = field(default_factory=dict)
    schema: str = "dbo"

    def __iter__(self):
        return iter(self.tables.values())

    def __getitem__(self, name: str) -> Table:
        return self.tables[name]

    def __contains__(self, name: str) -> bool:
        return name in self.tables

    def __len__(self) -> int:
        return len(self.tables)

    @classmethod
    def from_information_schema(cls, columns, keys=None, schema: str = "dbo") -> "Schema":
        """columns: iterable of (table_schema, table_name, column_name, data_type, ordinal) or dicts
        with those keys (case-insensitive). keys: optional rows from KEYS_SQL."""
        s = cls(schema=schema)
        for row in columns:
            r = _row(row, ["table_schema", "table_name", "column_name", "data_type", "ordinal_position"])
            if r["table_schema"] and r["table_schema"].lower() != schema.lower():
                continue
            t = s.tables.setdefault(r["table_name"], Table(r["table_name"], schema=schema))
            t.columns.append(Column(r["column_name"], str(r["data_type"] or "string").lower()))
        fks: dict[tuple[str, str], tuple[list[str], str, list[str]]] = {}
        for row in keys or []:
            r = _row(row, ["table_name", "constraint_type", "column_name", "ordinal_position",
                           "constraint_name", "ref_table", "ref_column"])
            t = s.tables.get(r["table_name"])
            if t is None:
                continue
            if r["constraint_type"] == "PRIMARY KEY":
                t.keys.append(r["column_name"])
            elif r["constraint_type"] == "FOREIGN KEY" and r["ref_table"]:
                fk = fks.setdefault((t.name, r["constraint_name"]), ([], r["ref_table"], []))
                fk[0].append(r["column_name"])
                fk[2].append(r["ref_column"])
        for (tname, _), fk in fks.items():
            s.tables[tname].foreign_keys.append(fk)
        return s

    @classmethod
    def from_sql(cls, execute, schema: str = "dbo", with_keys: bool = True) -> "Schema":
        """execute(sql) -> iterable of rows (tuples or dict-like)."""
        columns = list(execute(COLUMNS_SQL.format(schema=schema)))
        keys = []
        if with_keys:
            try:
                keys = list(execute(KEYS_SQL.format(schema=schema)))
            except Exception:  # lakehouse endpoints have no constraints; that's fine
                keys = []
        return cls.from_information_schema(columns, keys, schema=schema)

    @classmethod
    def from_spark(cls, spark, lakehouse_schema: str = "dbo", database: str | None = None) -> "Schema":
        """Lakehouse tables via the Spark catalog. `database` is the lakehouse name (default: current)."""
        s = cls(schema=lakehouse_schema)
        db = database or spark.catalog.currentDatabase()
        for t in spark.catalog.listTables(db):
            if t.tableType and t.tableType.upper() == "TEMPORARY":
                continue
            cols = spark.catalog.listColumns(t.name, db)
            s.tables[t.name] = Table(t.name, [Column(c.name, c.dataType) for c in cols], schema=lakehouse_schema)
        return s

    def to_rows(self) -> list[dict]:
        return [{"table_schema": self.schema, "table_name": t.name, "column_name": c.name, "data_type": c.data_type,
                 "ordinal_position": i + 1} for t in self for i, c in enumerate(t.columns)]


def _row(row, names: list[str]) -> dict:
    if hasattr(row, "keys"):
        lower = {k.lower(): row[k] for k in row.keys()}
        return {n: lower.get(n) for n in names}
    if hasattr(row, "asDict"):  # Spark Row
        return _row(row.asDict(), names)
    return dict(zip(names, list(row) + [None] * (len(names) - len(row))))
