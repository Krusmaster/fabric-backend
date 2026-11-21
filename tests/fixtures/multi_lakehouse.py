"""SM5: a synthetic workspace with several lakehouses, local only (docs/SMOOTH/PLAN.md, "The synthetic multi-lakehouse
fixture"). Every row is made up: the SAP rows are fabric_backend/sap_demo.py's default demo tables, the CRM rows are
fabric_backend/salesforce_demo.py's, and the two demos and their goldens stay unchanged.

One fake workspace, `mlh_demo`, holds six lakehouses:

| Lakehouse | Schemas | Rows from | For layout |
|---|---|---|---|
| bronze_lh | sap (17 tables) | sap_demo.tables() | (a) the source |
| silver_lh | (empty) | | (a) a target |
| gold_lh | (empty) | | (a) a target |
| sap_lh | sap_silver | sap_demo.tables() | (b) |
| crm_lh | crm_silver | salesforce_demo.tables(), plus Account.SAP_Customer_No__c and Account.VAT__c | (b) |
| sales_product_lh | sap, crm: shortcuts (simulated) | the two above | (b) -> (c) |

How it is built:
- Each (lakehouse, schema) is one SQLite database file in a temporary folder. A lakehouse's connection ATTACHes its
  schemas' files under their schema names, so `[sap].[KNA1]` is a two-part name on one connection, as on the SQL
  endpoint. (SQLite has no third part, so three-part names across lakehouses, gap G8, are not simulated.)
- A schema shortcut is simulated by ATTACHing the source lakehouse's file under the shortcut's schema name: the same
  rows, nothing copied, the source unchanged. (SQLite views cannot read another attached file, so a view would not do.)
- The CRM's extra column is filled for 4 of 5 accounts with the demo's KNA1.KUNNR values; one has its leading zeros
  stripped ("11" for "0000000011"), so a raw count finds 3 of 4 and a normalised one (M2, SM7) 4 of 4.
- `install(monkeypatch, layout)` replaces the same outer seams as tests/wb15_fake.py: the Fabric REST readers, the SQL
  endpoint and the tokens. A POST, PATCH, PUT or DELETE to any address fails the test. `layout` lists only that
  layout's lakehouses on the source step: "a", "b", "c", or None for all six.

`EXPECTED` says, per layout, what plan, check and dry run must say. SM5 measures the plan and the suggestion; SM6 and
SM7 measure the dry runs against the same lines. SM6 added the workspace's item list (a target lakehouse is chosen from
it) and each lakehouse's SQL host and OneLake tables path to what the fake readers answer; still nothing is written.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
from pathlib import Path

from fabric_backend import sap_demo, salesforce_demo, server
from fabric_backend.dialects import sqlite_sql
from fabric_backend.schema import Schema

WORKSPACE = "mlh_demo"
WORKSPACE_ID = "w-mlh"
# lakehouse -> {schema: (where the rows come from, the file's schema)}; a shortcut points at another lakehouse's file
LAKEHOUSES: dict[str, dict[str, tuple[str, str]]] = {
    "bronze_lh": {"sap": ("sap", "bronze_lh.sap")},
    "silver_lh": {},
    "gold_lh": {},
    "sap_lh": {"sap_silver": ("sap", "sap_lh.sap_silver")},
    "crm_lh": {"crm_silver": ("crm", "crm_lh.crm_silver")},
    "sales_product_lh": {"sap": ("sap", "sap_lh.sap_silver"), "crm": ("crm", "crm_lh.crm_silver")},   # shortcuts
}
SHORTCUTS = {("sales_product_lh", "sap"): "sap_lh.sap_silver", ("sales_product_lh", "crm"): "crm_lh.crm_silver"}
LAYOUTS = {"a": ("bronze_lh", "silver_lh", "gold_lh"), "b": ("sap_lh", "crm_lh", "sales_product_lh"),
           "c": ("sales_product_lh",)}
ITEMS = {name: {"id": f"aaaaaaaa-0000-0000-0000-{i:012d}", "displayName": name, "type": "Lakehouse",
                "schemas_enabled": True} for i, name in enumerate(LAKEHOUSES, 1)}

# The CRM column of the fixture only (SM5): 4 of 5 accounts carry an SAP customer number, one without leading zeros
SAP_NO = ["0000000010", "0000000011", "0000000012", "11", None]
VAT = ["SE556000001001", "SE556000001101", "FI10000012", "SE556000001101", None]

EXPECTED = {
    "a": {"lakehouses": LAYOUTS["a"], "suggested": "bronze_lh", "rule": "L1", "schema": "sap", "tables": 17,
          "extra_taps": 0, "untouched": ["silver_lh", "gold_lh"],
          "dry_run": {"silver": "silver_lh", "gold": "gold_lh"}},                       # SM6 measures this line
    "b": {"lakehouses": LAYOUTS["b"], "suggested": "sales_product_lh", "rule": "L2",
          "sources": {"sap_lh": "sap_silver", "crm_lh": "crm_silver"},
          "shortcuts": {"sap": "sap_lh.sap_silver", "crm": "crm_lh.crm_silver"},
          "match": {"rule": "M0", "from": "crm.Account.SAP_Customer_No__c", "to": "sap.KNA1.KUNNR",
                    "filled": 4, "of": 5, "found_raw": 3, "found_normalised": 4}},     # SM7 measures this line
    "c": {"lakehouses": LAYOUTS["c"], "schema": "sap+crm", "schemas": {"sap": 17, "crm": 21}, "tables": 38,
          "examples": ["sap.KNA1", "crm.Account"],
          "link": {"source": "crm.Account", "source_cols": ["SAP_Customer_No__c"], "target": "sap.KNA1",
                   "target_cols": ["KUNNR"]},
          "link_found": 3, "link_values": 4},
}

WRITES: list = []


def _kind(k: str) -> str:
    return {"string": "nvarchar", getattr(salesforce_demo, "_I", "int"): "int",
            getattr(salesforce_demo, "_B", "bit"): "bit"}.get(k, "decimal")


def rows(source: str) -> dict[str, tuple[list[str], list[str], list[tuple]]]:
    """{table: (columns, kinds, rows)} of one synthetic source: "sap" (the default demo tables) or "crm"."""
    if source == "sap":
        return sap_demo.tables()
    out = dict(salesforce_demo.tables())
    cols, kinds, rws = out["Account"]
    ids = [r[0] for r in rws]
    extra = {i: (SAP_NO[n], VAT[n]) for n, i in enumerate(ids[:len(SAP_NO)])}
    out["Account"] = (cols + ["SAP_Customer_No__c", "VAT__c"], kinds + ["string", "string"],
                      [tuple(r) + extra.get(r[0], (None, None)) for r in rws])
    return out


class Workspace:
    """The six lakehouses as SQLite files in one temporary folder."""

    def __init__(self):
        self._dir = tempfile.TemporaryDirectory(prefix="sm5_mlh_")
        self.folder = Path(self._dir.name)
        self.info: dict[str, list[tuple]] = {}               # file key -> INFORMATION_SCHEMA rows (schema left blank)
        for lh, schemas in LAKEHOUSES.items():
            for schema, (source, key) in schemas.items():
                if (lh, schema) in SHORTCUTS or key in self.info:
                    continue
                con = sqlite3.connect(self.file(key))
                info = []
                for name, (cols, kinds, rws) in rows(source).items():
                    con.execute(f"CREATE TABLE [{name}] ({', '.join(f'[{c}]' for c in cols)})")
                    con.executemany(f"INSERT INTO [{name}] VALUES ({','.join('?' * len(cols))})", rws)
                    info += [(name, c, _kind(k), i) for i, (c, k) in enumerate(zip(cols, kinds), 1)]
                con.commit()
                con.close()
                self.info[key] = info

    def file(self, key: str) -> str:
        return str(self.folder / (key.replace(".", "__") + ".db"))

    def schemas(self, lakehouse: str) -> list[dict]:
        """[{schema, tables}], as _source_schemas answers: only schemas that hold tables."""
        return [{"schema": s, "tables": len({r[0] for r in self.info[key]})}
                for s, (_, key) in sorted(LAKEHOUSES[lakehouse].items())]

    def read_schema(self, lakehouse: str, schema: str) -> Schema:
        hit = next(((s, key) for s, (_, key) in LAKEHOUSES[lakehouse].items() if s.lower() == str(schema).lower()), None)
        if hit is None:
            return Schema(schema=schema)
        s, key = hit
        return Schema.from_information_schema([(s, t, c, k, i) for t, c, k, i in self.info[key]], schema=s)

    def connect(self, lakehouse: str) -> "Connection":
        return Connection(self, lakehouse)

    def close(self):
        self._dir.cleanup()


class Connection:
    """One lakehouse's SQL endpoint: its schemas ATTACHed under their names, one connection, two-part names."""

    def __init__(self, ws: Workspace, lakehouse: str):
        self.lakehouse = lakehouse
        self.queries: list[str] = []
        self._lock = threading.Lock()
        self._con = sqlite3.connect(":memory:", check_same_thread=False)
        for schema, (_, key) in LAKEHOUSES[lakehouse].items():
            self._con.execute(f"ATTACH DATABASE ? AS [{schema}]", (ws.file(key),))

    def __call__(self, sql: str, *a, **k):
        with self._lock:
            self.queries.append(sql)
            cur = self._con.execute(sqlite_sql(sql))
            names = [d[0] for d in cur.description or []]
            return [dict(zip(names, r)) for r in cur.fetchall()]

    def close(self):
        with self._lock:
            self._con.close()


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


def install(monkeypatch, layout: str | None = None) -> Workspace:
    """The tools over the fixture; `layout` ("a", "b", "c" or None) is which lakehouses the source step lists. Returns
    the Workspace (its `connections` keep every query that ran, for the one-connection checks)."""
    import requests
    ws = Workspace()
    ws.connections = []
    listed = LAYOUTS[layout] if layout else tuple(LAKEHOUSES)
    by_id = {it["id"]: it for it in ITEMS.values()}

    def get(url, *a, **k):
        if str(url).rstrip("/").endswith(f"/workspaces/{WORKSPACE_ID}/items"):    # SM6: the workspace's items, for a target
            return _Response({"value": [{k: v for k, v in it.items() if k != "schemas_enabled"} for it in ITEMS.values()]})
        for iid, it in by_id.items():
            if f"/lakehouses/{iid}" in str(url) and str(url).rstrip("/").endswith(iid):
                return _Response({**it, "properties": {"defaultSchema": "dbo", "sqlEndpointProperties": {
                    "id": f"ep-{it['displayName']}", "connectionString": "mlh.datawarehouse.fabric.microsoft.com",
                    "provisioningStatus": "Success"}}})
        return _Response()

    def no_write(*a, **k):
        WRITES.append(a[:1])
        raise AssertionError(f"SM5: a write was attempted: {a[:1]}")

    def resolve(workspace, source, headers):
        it = ITEMS.get(str(source).strip()) or by_id.get(str(source).strip())      # SM6: a target is resolved by its id
        if it is None:
            raise LookupError(f"no lakehouse {source!r} in {WORKSPACE}")
        return {**it, "sql_host": "mlh.datawarehouse.fabric.microsoft.com",
                "onelake_tables_path": f"https://onelake.dfs.fabric.microsoft.com/{WORKSPACE_ID}/{it['id']}/Tables"}

    def execute_factory(item, token):
        con = ws.connect(item["displayName"])
        ws.connections.append(con)
        return con

    WRITES.clear()
    monkeypatch.setattr(requests, "get", get)
    for verb in ("post", "patch", "put", "delete"):
        monkeypatch.setattr(requests, verb, no_write)
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "limiter", None)
    monkeypatch.setattr(server, "_workspaces", lambda headers: [{"id": WORKSPACE_ID, "name": WORKSPACE, "capacity_id": "cap-1"}])
    monkeypatch.setattr(server, "_workspace_hints", lambda ids, headers: {WORKSPACE_ID: f"{len(listed)} lakehouses"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WORKSPACE_ID)
    monkeypatch.setattr(server, "_resolve_source", resolve)
    monkeypatch.setattr(server, "_execute_factory", execute_factory)
    monkeypatch.setattr(server, "_item_names", lambda workspace, ctx: [])
    monkeypatch.setattr(server, "list_sources", lambda workspace, ctx=None: json.dumps({
        "workspace": WORKSPACE_ID, "sources": [{"name": n, "id": ITEMS[n]["id"], "type": "Lakehouse"} for n in listed],
        "graphql_apis": []}))
    monkeypatch.setattr(server, "_source_schemas", lambda workspace, source, ctx: ws.schemas(str(source)))
    monkeypatch.setattr(server._fabric.PLATFORM, "read_schema", lambda ex, name: ws.read_schema(ex.lakehouse, name))
    return ws
