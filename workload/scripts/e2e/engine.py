"""W13: the Krusgraph engine's /workload/v1 routes on the Fabric and SQL doubles, served on 127.0.0.1 for the editor.

The end-to-end check of the Model editor (run.js) opens the real editor (ModelItemEditor, bundled by run.js) in
Chromium with a stand-in for the Fabric host (harness.tsx). The editor calls this server exactly as it calls the hosted
engine: POST /workload/v1/<route> with a bearer token. Only Fabric's REST API and the SQL analytics endpoint are doubles
(tests/golden_support.py: the golden workspace, lakehouse demo_lh, seed.py's synthetic shop rows in SQLite), as in
tests/test_workload_*.py and workload/scripts/screens/build_fixtures.py. No tenant, no secret, no network.

Scenarios (POST /e2e/scenario {"name": ...}, or --scenario):
    shop        the golden workspace (default)
    forbidden   Fabric answers 403 to every workspace read (the person has no access)
    big         the schema `shop` has the seven shop tables plus 240 more (a big schema)
    sap         WB4: the lakehouse also has the schema `sap_sd`, the 24-month synthetic SAP sample (fabric_backend/sap_sample.py)
    The empty state uses the schema `dbo`, which the lakehouse has with no tables.

    python workload/scripts/e2e/engine.py --port 8765 --static <bundle dir>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

TID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
URI = f"api://localdevinstance/{TID}/Org.Krusgraph/Ab"


class _JWKS:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": self.key})()


class _OBO:
    def token(self, user_token, tenant, scope):
        return f"obo:{scope}"


EXTRA = 240


def big_database(extra: int = EXTRA):
    """The shop rows plus `extra` small tables in shop, each with its own id and a customer_id (a link to customers)."""
    import golden_support as gs
    db = gs.shop_database()
    for i in range(extra):
        db.execute(f"CREATE TABLE shop.[extra_{i:03d}] (extra_{i:03d}_id INTEGER, customer_id INTEGER, amount REAL)")
        db.executemany(f"INSERT INTO shop.[extra_{i:03d}] VALUES (?, ?, ?)", [(j, 1 + j % 5, j * 1.5) for j in range(1, 6)])
    db.commit()
    return db


def big_metadata(on: bool) -> None:
    """INFORMATION_SCHEMA as the big schema has it: the double answers from seed.schema, so the extra tables are added."""
    import golden_support as gs
    base = getattr(gs._Cursor, "_w13_execute", gs._Cursor.execute)
    gs._Cursor._w13_execute = base
    if not on:
        gs._Cursor.execute = base
        return

    def execute(self, sql: str):
        base(self, sql)
        if "INFORMATION_SCHEMA.COLUMNS" in sql and "UPPER('shop')" in sql:
            for i in range(EXTRA):
                for n, (c, t) in enumerate([(f"extra_{i:03d}_id", "int"), ("customer_id", "int"), ("amount", "float")], 1):
                    self._rows.append(("shop", f"extra_{i:03d}", c, t, n))
        elif "TABLE_COUNT" in sql:
            self._rows = [(s, n + EXTRA if s == "shop" else n) for s, n in self._rows]
        return self
    gs._Cursor.execute = execute


SAP = "sap_sd"


def sap_database():
    """WB4: the shop rows plus the synthetic SAP sample sap_sd (24 months, SAP-shaped, not SAP data) in its own schema."""
    import golden_support as gs
    from datetime import date
    from fabric_backend import sap_sample
    db = gs.shop_database()
    db.execute(f"ATTACH DATABASE ':memory:' AS [{SAP}]")
    for table, data in sap_sample.rows(SAP).items():
        cols = sap_sample._cols(SAP, table)
        db.execute(f"CREATE TABLE [{SAP}].[{table}] ({', '.join(f'[{c}] ' + ('TEXT' if ty == 'STRING' else ty) for c, ty in cols)})")
        if data:
            db.executemany(f"INSERT INTO [{SAP}].[{table}] VALUES ({','.join('?' * len(cols))})",
                           [tuple(v.isoformat() if isinstance(v, date) else v for v in r) for r in data])
    db.commit()
    return db


def sap_metadata() -> None:
    """WB4: INFORMATION_SCHEMA as the lakehouse with the SAP sample has it: the schema list gets sap_sd, and its columns
    come from fabric_backend.sap_sample (the double answers only the shop's otherwise). Wraps the double's own execute,
    which big_metadata(False) has put back (one original for both scenarios)."""
    import golden_support as gs
    from fabric_backend import sap_sample
    base = getattr(gs._Cursor, "_w13_execute", gs._Cursor.execute)
    gs._Cursor._w13_execute = base
    names = ["TABLE_SCHEMA", "TABLE_NAME", "COLUMN_NAME", "DATA_TYPE", "ORDINAL_POSITION"]

    def execute(self, sql: str):
        if "INFORMATION_SCHEMA.COLUMNS" in sql and f"UPPER('{SAP}')" in sql:
            self.conn.log.append(sql)
            self._set(names, [tuple(r[n.lower()] for n in names) for r in sap_sample.schema(SAP).to_rows()])
            return self
        base(self, sql)
        if "TABLE_COUNT" in sql:
            self._rows = sorted(self._rows + [(SAP, len(sap_sample.SCHEMAS[SAP]))])
        return self
    gs._Cursor.execute = execute


def app(static: str | None):
    import jwt
    import requests
    from cryptography.hazmat.primitives.asymmetric import rsa
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route
    from starlette.staticfiles import StaticFiles

    import golden_support as gs
    from fabric_backend import server, workload_api
    from fabric_backend.entra import Validator, WorkloadConfig

    wl = WorkloadConfig("99999999-8888-7777-6666-555555555555", "wl-secret", URI)
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    state = {"scenario": "shop", "fake": gs.FakeFabric(), "log": []}

    def route(method):
        def call(url, *a, **kw):
            state["log"].append(f"{method} {url.split('?')[0]}")
            if state["scenario"] == "forbidden" and "api.fabric.microsoft.com" in url:
                return gs.Response(403, {"errorCode": "InsufficientPrivileges",
                                         "message": "The caller does not have permission to perform the operation."})
            return getattr(state["fake"], method)(url, *a, **kw)
        return call
    for verb in ("get", "post", "patch"):
        setattr(requests, verb, route(verb))

    def use(name: str) -> None:
        state["scenario"] = name
        state["fake"] = gs.FakeFabric()
        big_metadata(name == "big")
        if name == "sap":
            sap_metadata()
        sys.modules["pyodbc"] = gs.fake_pyodbc(big_database() if name == "big" else sap_database() if name == "sap" else None)
    use("shop")
    server.limiter = None

    async def token(request):
        claims = {"aud": URI, "iss": f"https://login.microsoftonline.com/{TID}/v2.0", "tid": TID,
                  "exp": int(time.time()) + 3600, "scp": "user_impersonation", "oid": "e2e-user"}
        return JSONResponse({"token": jwt.encode(claims, priv, algorithm="RS256")})

    async def scenario(request):
        body = await request.json()
        use(body.get("name", "shop"))
        return JSONResponse({"scenario": state["scenario"]})

    async def log(request):
        return JSONResponse({"scenario": state["scenario"], "fabric_calls": state["log"][-400:],
                             "created": [c.get("route") for c in state["fake"].created]})

    # the editor is served from this server (http://127.0.0.1:<port>): its calls are same-origin, as on the hosted editor
    from fabric_backend import workload_host
    workload_host.same_host_origin = lambda origin: bool(origin and origin.startswith("http://127.0.0.1:"))
    routes = workload_api.routes(wl, Validator(wl, _JWKS(priv.public_key())), _OBO())
    routes += [Route("/e2e/token", token), Route("/e2e/scenario", scenario, methods=["POST"]), Route("/e2e/log", log)]
    if static:
        routes.append(Mount("/", StaticFiles(directory=static, html=True)))
    return Starlette(routes=routes)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--static")
    a = ap.parse_args()
    import uvicorn
    uvicorn.run(app(a.static), host="127.0.0.1", port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
