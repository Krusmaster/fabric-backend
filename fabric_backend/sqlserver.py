"""The engine on a SQL Server from your own Python: one ODBC connection string, everything on your machine.

    from fabric_backend import plan_sql_server
    local = plan_sql_server("Driver={ODBC Driver 18 for SQL Server};Server=sql01;Database=shopdb;"
                            "Trusted_Connection=yes;TrustServerCertificate=yes", schema="shop")
    print(local.plan.summary())
    checks = local.validate()               # keys, relationships, amount_levels (the total that doubles)
    open("dictionary.md", "w").write(local.data_dictionary(checks))
    open("schema.yml", "w").write(local.dbt_schema())
    local.close()

The same calls the local stdio server and `fabric-backend demo` make: metadata from INFORMATION_SCHEMA (declared keys
become K0 and R0), name inference for the rest, counting queries only. Nothing is written to the database and nothing
leaves the machine except the queries to it. A sign-in with db_datareader is enough.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import amounts, evidence
from .infer import Plan, plan as _plan
from .schema import Schema


@dataclass
class LocalPlan:
    """A plan of one schema on a SQL Server, with the connection that made it (for the counting queries)."""
    plan: Plan
    execute: object
    schema: str
    label: str = ""
    _close: object = field(default=None, repr=False)

    def validate(self, max_items: int = 60) -> dict:
        """validate_plan's answer: keys unique and free of NULLs, relationships without orphans, header amounts."""
        return evidence.validate(self.plan, self.execute, max_items=max_items)

    def amount_levels(self) -> dict:
        """Only the check for the total that doubles, with the line rows per header counted."""
        return amounts.check(self.plan, self.execute)

    def data_dictionary(self, validation: dict | None = None) -> str:
        from .dictionary import data_dictionary
        return data_dictionary(self.plan, self.label or "SQL Server", self.schema, validation)

    def dbt_schema(self, source_name: str | None = None) -> str:
        from .dbt import schema_yml
        return schema_yml(self.plan, source_name or self.schema, self.schema)

    def close(self) -> None:
        if self._close:
            self._close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def plan_sql_server(dsn: str, schema: str = "dbo", keys: dict[str, list[str]] | None = None,
                    confirmed: list[dict] | None = None, execute=None) -> LocalPlan:
    """Read `schema` over ODBC and infer keys and relationships. `execute` (sql -> list of dict rows) replaces the
    ODBC connection, for a connection you already have; `dsn` is then only a label."""
    close = None
    if execute is None:
        from .platforms.local import odbc_connection, odbc_part
        execute = odbc_connection(dsn)
        close = getattr(execute, "close", None)
        label = f"{odbc_part(dsn, 'server') or 'SQL Server'}/{odbc_part(dsn, 'database') or '?'}"
    else:
        label = dsn or "SQL Server"
    s = Schema.from_sql(execute, schema)
    if not len(s):
        if close:
            close()
        raise ValueError(f"schema {schema!r} has no tables for this sign-in")
    return LocalPlan(_plan(s, keys, confirmed), execute, schema, label, close)
