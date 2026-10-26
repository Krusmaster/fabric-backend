"""The boundary between the engine and the platform adapters (docs/ARCHITECTURE.md), checked on the source.

The engine is platform-neutral and does no I/O of its own: it imports no network, driver or subprocess library and no
adapter, server or front end. Every adapter implements platforms/base.py's Platform. A change that breaks either is
a change to the architecture and fails here first.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

PKG = Path(__file__).parent.parent / "fabric_backend"

# The engine: inference, validation as counting queries, join paths, the graph, drift, dictionary, dbt, privacy rules,
# the question-to-SQL drafts, the silver and gold logic, the SQL dialects, the answer shaping, the review file.
ENGINE = ("schema", "infer", "evidence", "paths", "graphs", "drift", "dictionary", "dbt", "privacy", "compact", "answers",
          "silver", "gold", "dialects", "review")

# No engine module imports these, at the top or inside a function.
IO_LIBRARIES = {"requests", "pyodbc", "sqlite3", "subprocess", "socket", "http", "urllib.request", "notebookutils",
                "databricks", "uvicorn", "mcp"}
NOT_ENGINE = {"deploy", "server", "mcp_server", "cli", "demo_app", "demo", "pages", "platforms", "entra", "keyvault", "dcr",
              "lineage", "data_agent", "monitor", "limits", "usage", "entitlements", "discovery", "use_cases", "app_starter",
              "readiness", "git_export"}

# Pure Fabric format modules four engine modules borrow from today (no I/O in any of them). Listed so that a new one is
# a decision, not an accident: answers writes GraphQL field names, drift compares with a GraphQL definition, graphs uses
# the TMDL type families to compare column types, silver and gold render their notebook in Fabric's file format.
FORMAT_BORROWS = {("answers", "graphql"), ("drift", "graphql"), ("graphs", "semantic_model"), ("silver", "notebook"),
                  ("gold", "notebook")}
FORMATS = {"graphql", "semantic_model", "notebook", "ontology", "rayfin", "views"}


def _imports(module: str) -> set[str]:
    """Every module name a file imports, package-relative names as their last part (`.infer` -> `infer`)."""
    tree = ast.parse((PKG / f"{module}.py").read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.module:
                out.add(node.module.split(".")[0])
            elif node.level:
                out.update(a.name for a in node.names)          # from . import evidence
            else:
                out.add(node.module or "")
    return out


@pytest.mark.parametrize("module", ENGINE)
def test_the_engine_does_no_io_and_imports_no_adapter(module):
    names = _imports(module)
    io = {n for n in names if n in IO_LIBRARIES or n.split(".")[0] in IO_LIBRARIES}
    assert not io, f"{module}.py imports {sorted(io)}: I/O belongs in an adapter (fabric_backend/platforms/)"
    leaked = names & NOT_ENGINE
    assert not leaked, f"{module}.py imports {sorted(leaked)}: the engine imports no adapter, server or front end"
    borrowed = {(module, n) for n in names & FORMATS}
    assert borrowed <= FORMAT_BORROWS, f"{module}.py borrows {sorted(borrowed - FORMAT_BORROWS)} from a platform format"


def test_every_adapter_implements_the_platform_interface():
    from fabric_backend.dialects import Dialect
    from fabric_backend.platforms import Platform, Builder
    from fabric_backend.platforms import fabric, local
    adapters = [fabric.PLATFORM, local.OdbcPlatform(), local.OdbcPlatform("SQLServer"), local.SqlitePlatform(),
                local.ColumnsListPlatform()]
    for a in adapters:
        assert isinstance(a, Platform) and a.name and a.title and isinstance(a.dialect, Dialect)
        assert callable(a.connect) and callable(a.read_schema) and callable(a.unsupported)
        assert all(isinstance(b, Builder) for b in a.builders)
    names = [b.draft_tool or b.create_tool for b in fabric.BUILDERS]
    assert len(names) == len(set(names)) and "create_backend" in {b.create_tool for b in fabric.BUILDERS}


def test_the_fabric_builders_name_tools_the_hosted_server_has():
    import asyncio
    from fabric_backend import server
    from fabric_backend.platforms import fabric
    tools = {t.name for t in asyncio.run(server.mcp.list_tools())}
    for b in fabric.BUILDERS:
        for tool in (b.draft_tool, b.create_tool):
            assert tool is None or tool in tools, f"builder {b.kind!r} names {tool}, which the hosted server does not have"


def test_a_connection_carries_its_dialect_and_the_engine_uses_it():
    """The counting queries are written in the dialect of the connection that runs them; T-SQL without one."""
    from fabric_backend import evidence, seed
    from fabric_backend.dialects import TSQL, Dialect
    from fabric_backend.infer import plan
    from fabric_backend.platforms import connection
    seen = []
    other = Dialect("other", '"', '"', "COUNT", "limit")
    p = plan(seed.schema("shop"))
    evidence.validate(p, connection(lambda sql: seen.append(sql) or [{}], dialect=other), max_items=2)
    assert seen and all('"shop"."' in s and "COUNT_BIG" not in s for s in seen)
    seen.clear()
    evidence.validate(p, lambda sql: seen.append(sql) or [{}], max_items=2)
    assert seen and all("[shop].[" in s and "COUNT_BIG" in s for s in seen)
    assert evidence.sample_sql("shop", "orders", ["order_id"], 5, dialect=other) == 'SELECT "order_id" FROM "shop"."orders" LIMIT 5'
    assert evidence.sample_sql("shop", "orders", ["order_id"], 5) == "SELECT TOP (5) [order_id] FROM [shop].[orders]"
    assert TSQL.with_catalog("main").table("shop", "orders") == "[main].[shop].[orders]"
