"""What a platform adapter is: the three things the engine never does itself.

1. Read sources and schemas: `read_schema(execute, schema)` gives the engine a `Schema` (tables, columns with types,
   declared primary and foreign keys) from whatever the platform offers.
2. Run SQL: `connect(...)` opens a connection, which is the engine's `execute`: `execute(sql) -> list[dict]`, with
   `.dialect` (fabric_backend/dialects.py, the SQL the engine writes for it), `.close()`, and `.statement(sql)` for DDL
   when the platform lets the tools write through it. `connection()` below builds one from plain functions.
3. Build objects: `builders` names each kind of object the platform can make from a plan, the tool that drafts it and
   the tool that creates it (dry run by default), and the module that writes it. A builder's draft is pure: it turns
   a plan into files or SQL and calls nothing.

Everything else (inference K0–K5/R0–R4, validation as counting queries, join paths, the graph analysis, plan drift,
the data dictionary, dbt tests, the silver logic) is the engine's, and the engine imports no adapter
(tests/test_architecture.py checks it). docs/ARCHITECTURE.md has the picture and the checklist for a new adapter.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..dialects import TSQL, Dialect
from ..schema import Schema

# The site's status words (round n11): every claim about a tool on a platform uses one of them.
STATUS_WORDS = ("Tested end to end", "Experimental", "Draft only", "Available when enabled by the operator", "Planned")


def connection(execute, *, dialect: Dialect = TSQL, statement=None, close=None, **attributes):
    """Turn a function that runs SQL and returns rows as dicts into the engine's connection: the same function with
    .dialect, .close() (a no-op when not given) and .statement(sql) when the platform can run DDL through it."""
    execute.dialect = dialect
    execute.close = close or (lambda: None)
    if statement is not None:
        execute.statement = statement
    for name, value in attributes.items():
        setattr(execute, name, value)
    return execute


@dataclass(frozen=True)
class Builder:
    """One kind of object a platform builds from a plan."""
    kind: str                    # what it is, in a few words
    draft_tool: str | None       # the read-only tool that returns it without creating anything
    create_tool: str | None      # the tool that creates it (dry run by default); None when there is only a draft
    module: str                  # where the generator lives
    needs: str = ""              # the permission or right creating it needs


@dataclass(frozen=True)
class Unsupported:
    """What a tool answers on a platform that cannot serve it: the error format of every tool (errors.py)."""
    error: str
    hint: str

    def answer(self) -> dict:
        return {"error": self.error, "kind": "unsupported", "hint": self.hint}


class Platform(ABC):
    """A platform adapter. Subclasses set the class attributes and implement connect(); read_schema() reads
    INFORMATION_SCHEMA unless the platform says otherwise."""
    name: str = ""
    title: str = ""
    dialect: Dialect = TSQL
    builders: tuple[Builder, ...] = ()

    @abstractmethod
    def connect(self, *args, **kwargs):
        """Open a connection: the engine's `execute` (see connection())."""

    def read_schema(self, execute, schema: str) -> Schema:
        """Tables, columns and declared keys of one schema, from INFORMATION_SCHEMA (schema.py)."""
        return Schema.from_sql(execute, schema)

    def unsupported(self, tool: str) -> Unsupported | None:
        """Why `tool` cannot run on this platform, or None when it can."""
        return None
