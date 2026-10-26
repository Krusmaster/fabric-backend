"""SQL dialects for the queries the engine writes itself: the counting queries of validate_plan and
suggest_relationships, the sample of sample_rows and the join of join_path.

The engine writes each of those through a `Dialect`, so one plan gives the same check on every platform. The platform
adapter that runs the SQL (fabric_backend/platforms/) says which dialect its connection speaks, as `execute.dialect`;
a connection without one speaks T-SQL, which is what every answer was written in before there were adapters.

- TSQL: the Fabric SQL analytics endpoint, a Fabric warehouse or SQL database, SQL Server. `[name]`, COUNT_BIG,
  SELECT TOP (n).
- SQLite (the local demo's database) reads the T-SQL through `sqlite_sql`: COUNT_BIG becomes COUNT, TOP (n) becomes
  LIMIT n, and SQLite accepts the brackets as they are.
- DATABRICKS: Databricks SQL on a SQL warehouse (platforms/databricks.py). Backticks, COUNT, LIMIT n, length() for the
  size of a binary value, and three-part names `catalog`.`schema`.`table` (the connection binds the catalog). The
  documentation each piece rests on is cited where DATABRICKS is defined.

Pure string building; nothing here runs a query.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Dialect:
    name: str
    open_quote: str
    close_quote: str
    count: str                     # the aggregate that counts rows without overflowing (COUNT_BIG on SQL Server)
    limit_style: str               # "top": SELECT TOP (n) …; "limit": SELECT … LIMIT n
    byte_length: str = "DATALENGTH"  # the size of a binary value in bytes
    create_view: str = "CREATE OR ALTER VIEW"
    comments: bool = False         # whether CREATE VIEW takes COMMENT '<text>' after the name
    catalog: str | None = None     # three-part names catalog.schema.table when set

    def quote(self, name: str) -> str:
        """Quote an identifier: the closing quote inside a name is doubled."""
        return self.open_quote + str(name).replace(self.close_quote, self.close_quote * 2) + self.close_quote

    def table(self, schema: str, table: str) -> str:
        parts = ([self.catalog] if self.catalog else []) + [schema, table]
        return ".".join(self.quote(p) for p in parts)

    def schema(self, schema: str) -> str:
        return ".".join(self.quote(p) for p in ([self.catalog] if self.catalog else []) + [schema])

    def literal(self, text: str) -> str:
        """A string literal for comments: single quotes inside become a typographic apostrophe and backslashes go, so the
        literal never depends on a platform's escaping rules."""
        return "'" + str(text).replace("\\", "").replace("'", "’") + "'"

    def view_comment(self, text: str) -> str:
        return f" COMMENT {self.literal(text)}" if self.comments and text else ""

    def select(self, columns: str, rest: str, n: int | None = None) -> str:
        """SELECT <columns> <rest>, limited to n rows in this dialect's syntax."""
        if n is None:
            return f"SELECT {columns}{rest}"
        if self.limit_style == "top":
            return f"SELECT TOP ({int(n)}) {columns}{rest}"
        return f"SELECT {columns}{rest}\nLIMIT {int(n)}" if "\n" in rest else f"SELECT {columns}{rest} LIMIT {int(n)}"

    def with_catalog(self, catalog: str | None) -> "Dialect":
        return replace(self, catalog=catalog or None)


TSQL = Dialect("tsql", "[", "]", "COUNT_BIG", "top")

# Databricks SQL, read 26 October 2026 (docs.databricks.com, sql/language-manual/...):
# - sql-ref-identifiers: delimited identifiers are enclosed in backticks; a backtick inside one is written twice.
# - functions/count: count(*) returns a BIGINT, so COUNT needs no 64-bit variant.
# - sql-ref-syntax-qry-select-limit: SELECT ... LIMIT n.
# - functions/length: length(expr) is the number of bytes of a BINARY value.
# - Unity Catalog addresses a table as catalog.schema.table (data-governance/unity-catalog).
# - sql-ref-syntax-ddl-create-view: CREATE OR REPLACE VIEW name [COMMENT view_comment] AS query.
DATABRICKS = Dialect("databricks", "`", "`", "COUNT", "limit", byte_length="length", create_view="CREATE OR REPLACE VIEW", comments=True)


def of(execute) -> Dialect:
    """The dialect a connection speaks: `execute.dialect`, or T-SQL for a plain callable."""
    d = getattr(execute, "dialect", None)
    return d if isinstance(d, Dialect) else TSQL


def sqlite_sql(sql: str) -> str:
    """The engine's T-SQL for SQLite: COUNT instead of COUNT_BIG and LIMIT instead of TOP."""
    sql = sql.replace("COUNT_BIG(", "COUNT(")
    m = re.match(r"^\s*SELECT\s+TOP\s*\(?\s*(\d+)\s*\)?\s+", sql, re.I)
    if m:
        sql = "SELECT " + sql[m.end():] + f"\nLIMIT {int(m.group(1))}"
    return sql
