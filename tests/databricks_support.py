"""A Databricks workspace answered from memory, for tests/test_databricks.py: the SQL Statement Execution API backed by
SQLite with the shop seed, Unity Catalog's information_schema as rows, and the workspace and pipelines REST routes.

Databricks SQL runs on SQLite after three small translations: the catalog part of a three-part name is dropped (SQLite
attaches one database per schema), xxhash64 is a Python function, and to_json(named_struct(...)) is json_object(...).
Backticks, COUNT, LIMIT, row_number() OVER and NULLS LAST SQLite reads as they are.
"""
from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import json
import re
import sqlite3
from urllib.parse import urlsplit

from fabric_backend import seed

HOST = "https://adb-1234567890.0.azuredatabricks.net"
CATALOG = "workspace"
WAREHOUSE = "abcdef1234567890"
USER = "someone@example.com"

# Unity Catalog's full_data_type spelling of the seed's Spark types
TYPES = {"INT": "int", "STRING": "string", "DATE": "date", "DOUBLE": "double", "TIMESTAMP": "timestamp"}


def columns_rows(schema: str = "shop", not_null: set[tuple[str, str]] = frozenset()) -> list[dict]:
    out = []
    for t, spec in seed.SCHEMAS.items():
        for i, col in enumerate(spec.split(", "), 1):
            name, typ = col.split()
            out.append({"table_schema": schema, "table_name": t, "column_name": name, "data_type": TYPES[typ],
                        "ordinal_position": i, "is_nullable": "NO" if (t, name) in not_null else "YES"})
    return out


def pk(table: str, cols: list[str], name: str | None = None) -> list[dict]:
    return [{"table_name": table, "constraint_type": "PRIMARY KEY", "column_name": c, "ordinal_position": i, "constraint_name": name or f"{table}_pk",
             "ref_table": None, "ref_column": None, "ref_schema": None} for i, c in enumerate(cols, 1)]


def fk(table: str, cols: list[str], ref: str, ref_cols: list[str], schema: str = "shop") -> list[dict]:
    return [{"table_name": table, "constraint_type": "FOREIGN KEY", "column_name": c, "ordinal_position": i,
             "constraint_name": f"{table}_{'_'.join(cols)}_fk", "ref_table": ref, "ref_column": rc, "ref_schema": schema}
            for i, (c, rc) in enumerate(zip(cols, ref_cols), 1)]


def _xxhash64(*values) -> int:
    return int.from_bytes(hashlib.sha256(repr(values).encode()).digest()[:7], "big")


def to_sqlite(sql: str) -> str:
    sql = re.sub(r"`" + CATALOG + r"`\.", "", sql)
    sql = sql.replace("to_json(named_struct(", "json(json_object(").replace("current_timestamp()", "CURRENT_TIMESTAMP")
    return sql


class Response:
    def __init__(self, status: int = 200, body=None):
        self.status_code, self._body = status, body
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        return self._body


def _type_name(v) -> str:
    if isinstance(v, bool):
        return "BOOLEAN"
    if isinstance(v, int):
        return "LONG"
    if isinstance(v, float):
        return "DOUBLE"
    return "STRING"


class FakeDatabricks:
    """requests.get/post/put for the routes the adapter uses. `columns`, `constraints`, `tags` and `lineage` are the
    information_schema and system table rows; other SQL runs on the SQLite shop (`rows` replaces the seed's rows)."""

    def __init__(self, columns=None, constraints=None, tags=None, lineage=None, rows: dict | None = None, pending: int = 0,
                 chunk: int | None = None):
        self.columns = columns if columns is not None else columns_rows()
        self.constraints, self.tags, self.lineage = constraints or [], tags or [], lineage or []
        self.calls: list[tuple[str, str]] = []
        self.statements: list[str] = []
        self.ddl: list[str] = []
        self.pending, self.chunk = pending, chunk
        self.workspace: dict[str, str] = {}
        self.pipelines: dict[str, dict] = {}
        self.fail: dict[str, tuple[int, dict]] = {}
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.create_function("xxhash64", -1, _xxhash64)
        for s in ("shop", "silver", "gold", "krusgraph"):
            self.db.execute(f"ATTACH DATABASE ':memory:' AS {s}")
        data = rows if rows is not None else {t: [dict(zip([c.split()[0] for c in seed.SCHEMAS[t].split(', ')], r)) for r in rs]
                                              for t, rs in seed.rows().items()}
        for name, spec in seed.SCHEMAS.items():
            cols = [c.split()[0] for c in spec.split(", ")]
            self.db.execute(f"CREATE TABLE shop.`{name}` ({', '.join('`' + c + '`' for c in cols)})")
            self.db.executemany(f"INSERT INTO shop.`{name}` VALUES ({','.join('?' * len(cols))})",
                                [tuple(v.isoformat() if isinstance(v, (_dt.date, _dt.datetime)) else v for v in (r.get(c) for c in cols))
                                 for r in data.get(name, [])])
        self._results: dict[str, dict] = {}

    # ---------------------------------------------------------------- SQL
    def _rows(self, sql: str) -> tuple[list[str], list[tuple]]:
        low = sql.lower()
        if "information_schema.columns" in low:
            schema = re.search(r"lower\('([^']*)'\)", sql).group(1)
            rows = [r for r in self.columns if r["table_schema"].lower() == schema.lower()]
            names = ["table_schema", "table_name", "column_name", "data_type", "ordinal_position", "is_nullable"]
            return names, [tuple(r[n] for n in names) for r in rows]
        if "information_schema.table_constraints" in low:
            names = ["table_name", "constraint_type", "column_name", "ordinal_position", "constraint_name", "ref_table", "ref_column", "ref_schema"]
            return names, [tuple(r[n] for n in names) for r in self.constraints]
        if "information_schema.column_tags" in low:
            names = ["table_name", "column_name", "tag_name", "tag_value"]
            return names, [tuple(r[n] for n in names) for r in self.tags]
        if "system.access.table_lineage" in low:
            names = ["source_table_full_name", "target_table_full_name", "entity_type", "entity_id", "last_seen", "events"]
            return names, [tuple(r.get(n) for n in names) for r in self.lineage]
        if re.match(r"\s*(ALTER|CREATE|DROP)\b", sql, re.I):
            self.ddl.append(sql)
            return [], []
        cur = self.db.execute(to_sqlite(sql))
        return ([d[0] for d in cur.description] if cur.description else []), cur.fetchall()

    def _statement(self, body: dict) -> Response:
        sql = body["statement"]
        self.statements.append(sql)
        assert body["warehouse_id"] == WAREHOUSE and body["catalog"] == CATALOG and body["format"] == "JSON_ARRAY"
        if sql in self.fail:
            status, error = self.fail[sql]
            return Response(200, {"statement_id": "st-f", "status": {"state": "FAILED", "error": error}})
        names, rows = self._rows(sql)
        values = [[None if v is None else (str(v).lower() if isinstance(v, bool) else str(v)) for v in r] for r in rows]
        types = [_type_name(next((r[i] for r in rows if r[i] is not None), "")) for i in range(len(names))]
        manifest = {"format": "JSON_ARRAY", "schema": {"column_count": len(names),
                    "columns": [{"name": n, "position": i, "type_name": t} for i, (n, t) in enumerate(zip(names, types))]}}
        sid = f"st-{len(self.statements)}"
        chunks = [values] if not self.chunk else [values[i:i + self.chunk] for i in range(0, max(len(values), 1), self.chunk)] or [[]]
        result = {"statement_id": sid, "status": {"state": "SUCCEEDED"}, "manifest": manifest,
                  "result": self._chunk(sid, chunks, 0)}
        self._results[sid] = {"chunks": chunks, "done": result, "polls": self.pending}
        if self.pending:
            return Response(200, {"statement_id": sid, "status": {"state": "PENDING"}})
        return Response(200, result)

    def _chunk(self, sid: str, chunks: list, i: int) -> dict:
        out = {"chunk_index": i, "data_array": chunks[i], "row_count": len(chunks[i])}
        if i + 1 < len(chunks):
            out["next_chunk_index"] = i + 1
            out["next_chunk_internal_link"] = f"/api/2.0/sql/statements/{sid}/result/chunks/{i + 1}"
        return out

    # ---------------------------------------------------------------- HTTP
    def _route(self, method: str, url: str, body=None, params=None) -> Response:
        path = urlsplit(url).path
        self.calls.append((method, path))
        if (method, path) in self.fail:
            status, err = self.fail[(method, path)]
            return Response(status, err)
        if method == "POST" and path == "/api/2.0/sql/statements":
            return self._statement(body)
        m = re.match(r"^/api/2.0/sql/statements/([^/]+)(?:/result/chunks/(\d+))?$", path)
        if method == "GET" and m:
            st = self._results[m.group(1)]
            if m.group(2):
                return Response(200, self._chunk(m.group(1), st["chunks"], int(m.group(2))))
            if st["polls"] > 0:
                st["polls"] -= 1
                return Response(200, {"statement_id": m.group(1), "status": {"state": "RUNNING"}})
            return Response(200, st["done"])
        if method == "POST" and path.endswith("/cancel"):
            return Response(200, {})
        if method == "GET" and path == "/api/2.0/preview/scim/v2/Me":
            return Response(200, {"userName": USER})
        if method == "POST" and path == "/api/2.0/workspace/mkdirs":
            return Response(200, {})
        if method == "POST" and path == "/api/2.0/workspace/import":
            assert body["format"] == "SOURCE" and body["language"] == "SQL"
            self.workspace[body["path"]] = base64.b64decode(body["content"]).decode()
            return Response(200, {})
        if method == "GET" and path == "/api/2.0/pipelines":
            name = re.match(r"name LIKE '(.*)'", (params or {}).get("filter", "")).group(1)
            return Response(200, {"statuses": [{"pipeline_id": pid, "name": p["name"]} for pid, p in self.pipelines.items() if p["name"] == name]})
        if method == "POST" and path == "/api/2.0/pipelines":
            pid = f"pl-{len(self.pipelines) + 1}"
            self.pipelines[pid] = dict(body)
            return Response(200, {"pipeline_id": pid})
        m = re.match(r"^/api/2.0/pipelines/([^/]+)$", path)
        if m and method == "GET":
            return Response(200, {"pipeline_id": m.group(1), "name": self.pipelines[m.group(1)]["name"], "spec": self.pipelines[m.group(1)]})
        if m and method == "PUT":
            self.pipelines[m.group(1)] = {k: v for k, v in body.items() if k != "id"}
            return Response(200, {})
        return Response(404, {"error_code": "ENDPOINT_NOT_FOUND", "message": f"no route {method} {path}"})

    def get(self, url, headers=None, params=None, timeout=None, **kw):
        assert headers and headers.get("Authorization") == "Bearer test-only"
        return self._route("GET", url, params=params)

    def post(self, url, headers=None, json=None, params=None, timeout=None, **kw):
        assert headers and headers.get("Authorization") == "Bearer test-only"
        return self._route("POST", url, json, params)

    def put(self, url, headers=None, json=None, params=None, timeout=None, **kw):
        assert headers and headers.get("Authorization") == "Bearer test-only"
        return self._route("PUT", url, json, params)
