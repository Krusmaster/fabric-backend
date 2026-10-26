"""The doubles behind tests/test_golden.py: a Fabric workspace answered from memory and an ODBC driver backed by SQLite.

They sit at the outermost seams the product has, `requests` (Fabric REST) and `pyodbc` (the SQL endpoint), so the
golden answers cover every line between a tool call and the wire, wherever that code lives. Nothing here imports a
helper from the package other than the engine pieces that build the canned definitions; the T-SQL to SQLite
translation is written out again on purpose, so moving the package's own copy cannot change what these doubles do.
"""
from __future__ import annotations

import base64
import datetime as _dt
import json
import re
import sqlite3
import types
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

FABRIC = "https://api.fabric.microsoft.com"
WS = "11111111-2222-3333-4444-555555555555"
LH, EP, WH, API, SM = ("aaaaaaaa-0000-0000-0000-00000000000" + c for c in "12345")
SQL_HOST = "abc123.datawarehouse.fabric.microsoft.com"
SHIP_TO = {"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}
MODEL_DIR = Path(__file__).parent / "fixtures" / "semantic_model_shop"

ITEMS = [
    {"id": EP, "displayName": "demo_lh", "type": "SQLEndpoint"},          # listed before the lakehouse, as Fabric does
    {"id": LH, "displayName": "demo_lh", "type": "Lakehouse"},
    {"id": WH, "displayName": "demo_wh", "type": "Warehouse"},
    {"id": API, "displayName": "shop_api", "type": "GraphQLApi"},
    {"id": SM, "displayName": "shop_model", "type": "SemanticModel"},
]

# The warehouse declares two constraints, so the golden answers also cover K0/R0 read from INFORMATION_SCHEMA.
DECLARED = [
    {"TABLE_NAME": "customers", "CONSTRAINT_TYPE": "PRIMARY KEY", "COLUMN_NAME": "customer_id", "ORDINAL_POSITION": 1,
     "CONSTRAINT_NAME": "pk_customers", "REF_TABLE": None, "REF_COLUMN": None, "REF_SCHEMA": None},
    {"TABLE_NAME": "orders", "CONSTRAINT_TYPE": "FOREIGN KEY", "COLUMN_NAME": "ship_to_id", "ORDINAL_POSITION": 1,
     "CONSTRAINT_NAME": "fk_orders_ship_to", "REF_TABLE": "addresses", "REF_COLUMN": "address_id", "REF_SCHEMA": "shop"},
]


class Response:
    def __init__(self, status: int = 200, body=None, headers: dict | None = None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.text = json.dumps(body) if body is not None else ""
        self.content = self.text.encode()
        self.ok = status < 400

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} for url", response=self)


def _parts(files: dict[str, str]) -> list[dict]:
    return [{"path": p, "payload": base64.b64encode(t.encode("utf-8")).decode(), "payloadType": "InlineBase64"}
            for p, t in files.items()]


def _api_definition() -> dict:
    """shop_api as it stands in the demo workspace: the plan with ship_to_id confirmed (README, 26 October)."""
    from fabric_backend import seed
    from fabric_backend.graphql import definition
    from fabric_backend.infer import plan
    return definition(plan(seed.schema("shop"), confirmed=[SHIP_TO]), "shop_api", WS, EP, "SqlAnalyticsEndpoint")["definition"]


def _model_parts() -> list[dict]:
    files = {str(p.relative_to(MODEL_DIR)).replace("\\", "/"): p.read_text(encoding="utf-8")
             for p in sorted(MODEL_DIR.rglob("*")) if p.is_file() and p.suffix in (".tmdl", ".pbism", ".json", ".platform")}
    return _parts(files)


_INTROSPECTION = {"data": {"__schema": {"queryType": {"name": "Query"}, "mutationType": None, "types": [
    {"kind": "OBJECT", "name": "Query", "fields": [{"name": "orders", "args": [], "type": {"kind": "OBJECT", "name": "orders", "ofType": None}}]},
]}}}


class FakeFabric:
    """GET/POST/PATCH like `requests`, answered from the workspace above. Every call is logged (method, path)."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.created: list[dict] = []

    def _route(self, method: str, url: str, body=None) -> Response:
        parts = urlsplit(url)
        path, query = parts.path, parse_qs(parts.query)
        self.calls.append((method, path + (f"?{parts.query}" if parts.query else "")))
        if parts.netloc.startswith("login.microsoftonline.com"):
            return Response(400, {"error": "invalid_client", "error_description": "no token endpoint in the golden tests"})
        if parts.netloc != "api.fabric.microsoft.com":
            return Response(404, {"errorCode": "NotFound", "message": f"no route {parts.netloc}"})
        seg = [s for s in path.split("/") if s][1:]                      # drop "v1"
        if method == "GET" and seg == ["workspaces"]:
            return Response(200, {"value": [{"id": WS, "displayName": "demo", "type": "Workspace", "capacityId": "cap-1"}]})
        if len(seg) < 2 or seg[0] != "workspaces" or seg[1] != WS:
            return Response(404, {"errorCode": "WorkspaceNotFound", "message": "The requested workspace was not found"})
        rest = seg[2:]
        if method == "GET" and rest == ["items"]:
            want = (query.get("type") or [None])[0]
            return Response(200, {"value": [i for i in ITEMS if want in (None, i["type"])]})
        if method == "GET" and rest == ["lakehouses", LH]:
            return Response(200, {"id": LH, "displayName": "demo_lh", "type": "Lakehouse", "properties": {
                "defaultSchema": "dbo", "oneLakeTablesPath": "https://onelake.dfs.fabric.microsoft.com/x/y/Tables",
                "sqlEndpointProperties": {"id": EP, "connectionString": SQL_HOST, "provisioningStatus": "Success"}}})
        if method == "GET" and rest == ["warehouses", WH]:
            return Response(200, {"id": WH, "displayName": "demo_wh", "type": "Warehouse", "properties": {"connectionString": SQL_HOST}})
        if method == "POST" and rest in (["items", API, "getDefinition"], ["graphQLApis", API, "getDefinition"]):
            return Response(200, {"definition": _api_definition()})
        if method == "POST" and rest in (["semanticModels", SM, "getDefinition"], ["items", SM, "getDefinition"]):
            return Response(200, {"definition": {"parts": _model_parts()}})
        if method == "POST" and len(rest) == 3 and rest[0].lower() == "graphqlapis" and rest[1] == API and rest[2] == "graphql":
            text = (body or {}).get("query", "")
            if "__schema" in text:
                return Response(200, _INTROSPECTION)
            return Response(200, {"data": {"orders": {"items": [{"order_id": 100}]}}})
        if method == "POST" and rest[-1:] == ["updateDefinition"]:
            self.created.append({"route": "/".join(rest), "body": body})
            return Response(200, None)
        if method == "POST" and len(rest) == 1 and rest[0] in ("graphQLApis", "semanticModels", "ontologies", "notebooks", "dataPipelines"):
            self.created.append({"route": rest[0], "body": body})
            return Response(201, {"id": f"new-{rest[0]}", "displayName": (body or {}).get("displayName")})
        return Response(404, {"errorCode": "EntityNotFound", "message": f"no route {method} /{'/'.join(rest)}"})

    def get(self, url, headers=None, params=None, timeout=None, **kw):
        return self._route("GET", url)

    def post(self, url, headers=None, json=None, data=None, timeout=None, **kw):
        return self._route("POST", url, json)

    def patch(self, url, headers=None, json=None, params=None, timeout=None, **kw):
        return self._route("PATCH", url, json)


# ------------------------------------------------------------------ the SQL endpoint ----------------------------

def _sqlite(sql: str) -> str:
    """T-SQL as the engine writes it → SQLite: COUNT_BIG is COUNT, TOP (n) becomes LIMIT n. Brackets SQLite reads as they are."""
    sql = sql.replace("COUNT_BIG(", "COUNT(")
    m = re.match(r"^\s*SELECT\s+TOP\s*\(?\s*(\d+)\s*\)?\s+", sql, re.I)
    if m:
        sql = "SELECT " + sql[m.end():] + f"\nLIMIT {int(m.group(1))}"
    return sql


def shop_database() -> sqlite3.Connection:
    from fabric_backend.seed import SCHEMAS, rows
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute("ATTACH DATABASE ':memory:' AS shop")
    for name, ddl in SCHEMAS.items():
        con.execute(f"CREATE TABLE shop.[{name}] ({ddl})")
        data = [tuple(v.isoformat() if isinstance(v, (_dt.date, _dt.datetime)) else v for v in r) for r in rows()[name]]
        con.executemany(f"INSERT INTO shop.[{name}] VALUES ({','.join('?' * len(data[0]))})", data)
    return con


class _Cursor:
    def __init__(self, conn: "_Connection"):
        self.conn, self.description, self._rows = conn, None, []

    def execute(self, sql: str):
        self.conn.log.append(sql)
        from fabric_backend import seed
        if "INFORMATION_SCHEMA.COLUMNS" in sql:
            schema = re.search(r"UPPER\('([^']*)'\)", sql).group(1)
            rows = seed.schema(schema).to_rows() if schema.lower() == "shop" else []
            names = ["TABLE_SCHEMA", "TABLE_NAME", "COLUMN_NAME", "DATA_TYPE", "ORDINAL_POSITION"]
            self._set(names, [tuple(r[n.lower()] for n in names) for r in rows])
        elif "INFORMATION_SCHEMA.TABLE_CONSTRAINTS" in sql:
            rows = DECLARED if self.conn.database == "demo_wh" else []
            names = list(DECLARED[0])
            self._set(names, [tuple(r[n] for n in names) for r in rows])
        elif "INFORMATION_SCHEMA.VIEW_TABLE_USAGE" in sql:
            self._set(["VIEW_SCHEMA", "VIEW_NAME", "TABLE_SCHEMA", "TABLE_NAME"], [("krusgraph", "vw_orders", "shop", "orders")])
        elif re.match(r"\s*(CREATE|ALTER|DROP|INSERT|UPDATE|DELETE|IF\b|EXEC)", sql, re.I):
            self.conn.ddl.append(sql)
            self._set([], [])
        else:
            cur = self.conn.db.execute(_sqlite(sql))
            self._set([d[0] for d in cur.description] if cur.description else [], cur.fetchall())
        return self

    def _set(self, names, rows):
        self.description = [(n, None, None, None, None, None, None) for n in names] if names else None
        self._rows = [tuple(r) for r in rows]

    def fetchall(self):
        return list(self._rows)


class _Connection:
    def __init__(self, dsn: str, db: sqlite3.Connection, log: list, ddl: list):
        m = re.search(r"Database=([^;]+)", dsn, re.I)
        self.database = m.group(1).strip("{}") if m else ""
        self.db, self.log, self.ddl, self.timeout, self.closed = db, log, ddl, 0, False

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        pass

    def close(self):
        self.closed = True


def fake_pyodbc(db: sqlite3.Connection | None = None):
    """A stand-in `pyodbc` module: connect() opens a connection to the shop database whatever the string says (the
    Database= part decides whether constraints are declared). `module.log` holds every statement, `module.ddl` the DDL."""
    db = db or shop_database()
    mod = types.ModuleType("pyodbc")
    mod.log, mod.ddl, mod.dsns = [], [], []

    def connect(dsn, attrs_before=None, timeout=None, **kw):
        mod.dsns.append(dsn)
        return _Connection(dsn, db, mod.log, mod.ddl)
    mod.connect = connect
    mod.Error = type("Error", (Exception,), {})
    return mod
