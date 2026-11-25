"""AP2b: the founder's tenant of 25 November 2026 in invented names, behind the doubles of tests/ap1_support.py and
tests/wb15_fake.py (the synthetic SAP demo). Two workspaces: `demo` with the lakehouse `demo_lh` and the source schema
`shop`; `build_ws`, the build target, with the lakehouses `build_lh` and `out_lh`, whose schemas are dbo (a source) and
Krusgraph's own output gold, krusgraph and silver. The schema `shop` carries one more table than the demo, `sap_notes`,
which has no column a key rule can prove, so the check has a table without a key (finding 3)."""
from __future__ import annotations

import json

from fabric_backend import server
from fabric_backend.schema import Column, Schema, Table

WORKSPACES = [{"id": "w-demo", "name": "demo", "capacity_id": "cap-1"},
              {"id": "w-build", "name": "build_ws", "capacity_id": "cap-1"}]
SOURCES = {"demo": ["demo_lh"], "build_ws": ["build_lh", "out_lh"]}
SCHEMAS = {("demo", "demo_lh"): [("shop", 18)],
           ("build_ws", "build_lh"): [("dbo", 17), ("gold", 7), ("krusgraph", 3), ("silver", 17)],
           ("build_ws", "out_lh"): [("dbo", 17), ("_rsc", 1)]}


def install(monkeypatch) -> None:
    """After ap1_support.data(monkeypatch): the two workspaces, their sources and schemas, and the keyless table."""
    import wb15_fake
    ids = {w["name"]: w["id"] for w in WORKSPACES}
    monkeypatch.setattr(server, "_workspaces", lambda headers: [dict(w) for w in WORKSPACES])
    monkeypatch.setattr(server, "_workspace_hints", lambda ids_, headers: {})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: ids.get(workspace, workspace))
    monkeypatch.setattr(server, "list_sources", lambda workspace, ctx=None: json.dumps({
        "workspace": ids.get(workspace, workspace), "graphql_apis": [],
        "sources": [{"name": n, "id": wb15_fake.ITEM["id"], "type": "Lakehouse"} for n in SOURCES.get(workspace, [])]}))
    monkeypatch.setattr(server, "_source_schemas", lambda workspace, source, ctx: [
        {"schema": n, "tables": t} for n, t in SCHEMAS.get((workspace, source), [])])
    read = server._fabric.PLATFORM.read_schema

    def read_schema(ex, name):
        got = read(ex, name)
        if name != "shop":
            return got
        out = Schema(schema=got.schema)
        out.tables.update(got.tables)
        out.tables["sap_notes"] = Table("sap_notes", [Column("NOTE_TEXT", "varchar"), Column("WRITTEN_ON", "date")])
        return out
    monkeypatch.setattr(server._fabric.PLATFORM, "read_schema", read_schema)
