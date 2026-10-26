"""Platform adapters: where the engine's plans meet a data platform.

The engine (inference, validation, join paths, the graph, drift, dictionary, dbt, the silver logic) knows nothing of
where the tables live. An adapter reads a source's schema, runs the engine's SQL in its dialect and builds the
platform's objects from a plan; platforms/base.py says exactly what that means and docs/ARCHITECTURE.md what a new one
has to implement.

    fabric   Microsoft Fabric: REST for workspaces and items, the SQL analytics endpoint over ODBC with an Entra token
    local    what the local stdio server and the 20-minute demo read: an ODBC connection string (a Fabric SQL endpoint
             or SQL Server), a SQLite database (the synthetic shop, or a folder of CSV and Excel files), a columns list
    databricks  Unity Catalog through information_schema, a SQL warehouse through the Statement Execution API (Draft only)
"""
from __future__ import annotations

from .base import STATUS_WORDS, Builder, Platform, Unsupported, connection

__all__ = ["STATUS_WORDS", "Builder", "Platform", "Unsupported", "connection"]
