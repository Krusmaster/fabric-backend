"""WB15: the hosted server's tools on the synthetic SAP demo, the way Gustav's phone test of 19 November 2026 saw it:
the workspace `demo`, one lakehouse `demo_lh`, the SAP order-to-cash tables in the schema `dbo` (fabric_backend/sap_demo.py,
17 tables in SQLite with one planted orphan: sap_vbap.MANDT+VBELN -> sap_vbak, 5 of 6 found).

`install(monkeypatch)` replaces only the outer seams: the Fabric REST readers (workspaces, sources, schemas, item lookups),
the SQL endpoint (SQLite with the demo rows) and the two tokens. Everything between a tool call and those seams is the
product's own code, the same functions the hosted server registers. Nothing reaches Fabric; nothing can be written: a
POST, PATCH, PUT or DELETE to any address fails the test.

`call(name, arguments)` runs a tool as the hosted server registers it with the cards on (mcp_apps.structured over the
instrumented tool) and returns the CallToolResult as the JSON a host sends a card.
"""
from __future__ import annotations

import json

from fabric_backend import mcp_apps, sap_demo, server

ITEM = {"id": "aaaaaaaa-0000-0000-0000-0000000000a1", "displayName": "demo_lh", "type": "Lakehouse", "schemas_enabled": True}
WRITES: list = []


class _Response:
    ok, headers, status_code = True, {}, 200

    def __init__(self, body=None):
        self._body = body if body is not None else {"value": []}
        self.text = json.dumps(self._body)
        self.content = self.text.encode()

    def json(self):
        return self._body

    def raise_for_status(self):
        return None


def _get(url, *a, **k):
    """Fabric's GET answers: the lakehouse (with schemas, as demo_lh is) and empty lists for everything else."""
    if f"/lakehouses/{ITEM['id']}" in str(url) and str(url).rstrip("/").endswith(ITEM["id"]):
        return _Response({**ITEM, "properties": {"defaultSchema": "dbo", "sqlEndpointProperties": {
            "id": "ep-1", "connectionString": "demo.datawarehouse.fabric.microsoft.com", "provisioningStatus": "Success"}}})
    return _Response()


def install(monkeypatch) -> None:
    import requests
    from concurrent.futures import ThreadPoolExecutor
    db = ThreadPoolExecutor(max_workers=1)                  # SQLite answers only in the thread that opened it
    schema, raw = db.submit(sap_demo.sqlite, schema="dbo").result()

    def execute(sql, *a, **k):
        return db.submit(raw, sql, *a, **k).result()
    WRITES.clear()

    def no_write(*a, **k):
        WRITES.append(a[:1])
        raise AssertionError(f"WB15: a write was attempted: {a[:1]}")
    monkeypatch.setattr(requests, "get", _get)
    for verb in ("post", "patch", "put", "delete"):
        monkeypatch.setattr(requests, verb, no_write)
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "limiter", None)
    monkeypatch.setattr(server, "_workspaces", lambda headers: [{"id": "w-demo", "name": "demo", "capacity_id": "cap-1"}])
    monkeypatch.setattr(server, "_workspace_hints", lambda ids, headers: {"w-demo": "1 lakehouse"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: "w-demo")
    monkeypatch.setattr(server, "_resolve_source", lambda workspace, source, headers: dict(ITEM))
    monkeypatch.setattr(server, "_execute_factory", lambda item, token: execute)
    monkeypatch.setattr(server, "_item_names", lambda workspace, ctx: [])
    monkeypatch.setattr(server, "list_sources",
                        lambda workspace, ctx=None: json.dumps({"workspace": "w-demo", "sources": [
                            {"name": "demo_lh", "id": ITEM["id"], "type": "Lakehouse"}], "graphql_apis": []}))
    monkeypatch.setattr(server, "_source_schemas", lambda workspace, source, ctx: [
        {"schema": "dbo", "tables": len(schema)}, {"schema": "sap_bronze", "tables": 0}])
    monkeypatch.setattr(server._fabric.PLATFORM, "read_schema", lambda ex, name: schema)


def call(name: str, arguments: dict) -> dict:
    """The tool's CallToolResult as JSON: {content, structuredContent, isError}."""
    fn = mcp_apps.structured(getattr(server, name), name)
    try:
        r = fn(**arguments)
    except Exception as e:                                  # noqa: BLE001 - a host answers an error as isError
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)[:300]})}], "isError": True}
    if isinstance(r, str):
        return {"content": [{"type": "text", "text": r}]}
    return {"content": [{"type": "text", "text": c.text} for c in r.content], "structuredContent": r.structured_content,
            "isError": bool(getattr(r, "isError", False))}
