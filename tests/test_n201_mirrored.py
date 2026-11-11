"""Round n201: the Krusgraph Model reads mirrored databases, SAP mirrored through SAP Datasphere among them.

A fake mirrored database: Fabric's Get Mirrored Database answer (properties.oneLakeTablesPath, sqlEndpointProperties, the
shape Learn's REST page shows) and a SQL analytics endpoint backed by SQLite. Two of them:

- `sap_mirror`: SAP-named tables in dbo built only from the SAP pack's public table and column names (fabric_backend/packs/sap)
  with made-up values: sap_demo.tables() (written from the pack, n32) plus EKKO, EKPO and LFA1 here. No SAP data;
- `mill_mirror`: the synthetic mill sample (fabric_backend.mill), no SAP names: it plans as any other source.

What is tested: the review on the mirror (read-only, the SAP pack's keys with MANDT and its links, each "from the SAP pack"
with the pack's public source, beside the inferred ones, accepted or rejected as any other item); the build's dry run with a
target lakehouse (the default said, nothing written) and Create of the silver notebook (written to the target lakehouse,
reading the mirror's OneLake path); the silver notebook's setup run with stand-ins for Spark and notebookutils, so the path
each table is read from is the one the notebook computes. Not run against a mirrored database in Fabric.
"""
import base64
import json
import re
import sqlite3
import sys
import types

import pytest

jwt = pytest.importorskip("jwt")
from starlette.testclient import TestClient  # noqa: E402

import golden_support as gs  # noqa: E402
from test_workload_api import FABRIC_ORIGIN, WL, FakeJWKS, keys, tok  # noqa: E402,F401
from test_workload_build import EVERY_SCOPE, Fabric, ScopedOBO  # noqa: E402
from fabric_backend import mill, mirroring, sap_demo, sap_pack, server, silver, workload_api  # noqa: E402
from fabric_backend.dialects import sqlite_sql  # noqa: E402
from fabric_backend.entra import Validator  # noqa: E402

MD = "dddddddd-0000-0000-0000-000000000001"           # the SAP mirror
MILL = "dddddddd-0000-0000-0000-000000000002"         # the mill mirror
LH2 = "aaaaaaaa-0000-0000-0000-000000000009"          # a second lakehouse, without schemas
TABLES_PATH = f"https://onelake.dfs.fabric.microsoft.com/{gs.WS}/{MD}/Tables"
ABFSS = f"abfss://{gs.WS}@onelake.dfs.fabric.microsoft.com/{MD}/Tables"


# ------------------------------------------------------------------ the fake mirrored databases -----------------------

def sap_tables() -> dict:
    """{table: (columns, rows)}: sap_demo's tables under their SAP names, and purchasing (EKKO, EKPO, LFA1) with columns the
    pack names and made-up values."""
    out = {name: (cols, rows) for name, (cols, _k, rows) in sap_demo.tables().items()}
    mat = out["MARA"][1][0][1]
    out["LFA1"] = (["MANDT", "LIFNR", "NAME1"], [("100", "0000100001", "Demo Supplier 1"), ("100", "0000100002", "Demo Supplier 2")])
    out["EKKO"] = (["MANDT", "EBELN", "LIFNR", "BUKRS", "BEDAT"],
                   [("100", "4500000001", "0000100001", "1000", "20261001"), ("100", "4500000002", "0000100002", "1000", "20261002")])
    out["EKPO"] = (["MANDT", "EBELN", "EBELP", "MATNR", "MENGE"],
                   [("100", "4500000001", "00010", mat, 5), ("100", "4500000001", "00020", mat, 1), ("100", "4500000002", "00010", mat, 2)])
    return out


def test_the_fake_sap_mirror_uses_only_the_pack_s_table_and_column_names():
    pack = sap_pack.load("sap")
    named = {c for t in pack["tables"].values() for c in t["key"] + t.get("number_columns", []) + t.get("delta", [])
             + [a["column"] for a in t.get("amounts", [])] + t.get("currency_columns", [])}
    named |= {c for r in pack["relationships"] for c in r["source_cols"] + r["target_cols"]}
    for table, (cols, _rows) in sap_tables().items():
        assert table in pack["tables"], table
        if table in ("EKKO", "EKPO", "LFA1"):                     # the three written here: every column a name the pack uses
            assert set(cols) - {"NAME1", "BEDAT", "MENGE"} <= named, (table, set(cols) - named)


def _database(tables: dict, schema: str) -> tuple[sqlite3.Connection, list[tuple]]:
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute(f"ATTACH DATABASE ':memory:' AS [{schema}]")
    info = []
    for name, (cols, kinds, rows) in tables.items():
        con.execute(f"CREATE TABLE [{schema}].[{name}] ({', '.join(f'[{c}]' for c in cols)})")
        if rows:
            con.executemany(f"INSERT INTO [{schema}].[{name}] VALUES ({','.join('?' * len(cols))})",
                            [tuple(r[:len(cols)]) for r in rows])
        info += [(schema, name, c, k, i) for i, (c, k) in enumerate(zip(cols, kinds), 1)]
    return con, info


def endpoint(tables: dict, schema: str = "dbo"):
    """A stand-in `pyodbc` for a mirrored database's SQL analytics endpoint: INFORMATION_SCHEMA from the tables, no declared
    keys (mirroring documents none), every other query on SQLite. Read-only: DDL or DML fails."""
    con, info = _database(tables, schema)
    mod = types.ModuleType("pyodbc")
    mod.log = []
    mod.Error = type("Error", (Exception,), {})

    class Cursor:
        description, _rows = None, []

        def execute(self, sql):
            mod.log.append(sql)
            if re.match(r"\s*(CREATE|ALTER|DROP|INSERT|UPDATE|DELETE|MERGE|EXEC)\b", sql, re.I):
                raise mod.Error("('42000', 'The SQL analytics endpoint of a mirrored database is read-only')")
            if "INFORMATION_SCHEMA.COLUMNS" in sql:
                asked = re.search(r"UPPER\('([^']*)'\)", sql).group(1)
                self._set(["TABLE_SCHEMA", "TABLE_NAME", "COLUMN_NAME", "DATA_TYPE", "ORDINAL_POSITION"],
                          [r for r in info if r[0].upper() == asked.upper()])
            elif "INFORMATION_SCHEMA.SCHEMATA" in sql or ("INFORMATION_SCHEMA.TABLES" in sql and "TABLE_COUNT" in sql):
                self._set(["TABLE_SCHEMA", "TABLE_COUNT"], [(schema, len(tables))])
            elif "TABLE_CONSTRAINTS" in sql or "VIEW_TABLE_USAGE" in sql or "sys." in sql:
                self._set(["X"], [])
            else:
                cur = con.execute(sqlite_sql(sql))
                self._set([d[0] for d in cur.description] if cur.description else [], cur.fetchall())
            return self

        def _set(self, names, rows):
            self.description = [(n, None, None, None, None, None, None) for n in names] if names else None
            self._rows = [tuple(r) for r in rows]

        def fetchall(self):
            return list(self._rows)

    class Connection:
        timeout = 0

        def cursor(self):
            return Cursor()

        def commit(self):
            pass

        def close(self):
            pass
    mod.connect = lambda dsn, attrs_before=None, timeout=None, **kw: Connection()
    return mod


def sap_endpoint():
    return endpoint({n: (cols, ["nvarchar"] * len(cols), rows) for n, (cols, rows) in sap_tables().items()})


def mill_endpoint():
    from datetime import date, datetime
    data = mill.rows()
    tables = {}
    for name, ddl in mill.SCHEMAS.items():
        cols = [c.split()[0] for c in ddl.split(", ")]
        kinds = [{"INT": "int", "DOUBLE": "float", "DATE": "date", "TIMESTAMP": "datetime2"}.get(c.split()[1], "varchar") for c in ddl.split(", ")]
        rows = [tuple(v.isoformat() if isinstance(v, (date, datetime)) else v for v in r) for r in data[name]]
        tables[name] = (cols, kinds, rows)
    return endpoint(tables)


class MirrorFabric(Fabric):
    """The golden workspace with two mirrored databases (Get Mirrored Database as Learn's REST page shows it) and a second
    lakehouse; `lakehouses=False` leaves the workspace without any lakehouse."""

    def __init__(self, lakehouses: bool = True):
        super().__init__()
        self.lakehouses = lakehouses

    def _items(self):
        items = [i for i in gs.ITEMS if self.lakehouses or i["type"] not in ("Lakehouse", "SQLEndpoint")]
        items += [{"id": MD, "displayName": "sap_mirror", "type": "MirroredDatabase"},
                  {"id": MILL, "displayName": "mill_mirror", "type": "MirroredDatabase"}]
        if self.lakehouses:
            items.append({"id": LH2, "displayName": "zz_flat", "type": "Lakehouse"})
        return items

    def _route(self, method, url, body=None):
        path, query = url.split("?")[0], (url.split("?") + [""])[1]
        rest = path.split(f"/workspaces/{gs.WS}/")[-1].split("/") if f"/workspaces/{gs.WS}/" in path else []
        if method == "GET" and rest == ["items"]:
            self.calls.append((method, path))
            want = dict(x.split("=") for x in query.split("&") if "=" in x).get("type")
            return gs.Response(200, {"value": [i for i in self._items() if want in (None, i["type"])]})
        if method == "GET" and rest[:1] == ["mirroredDatabases"] and len(rest) == 2:
            self.calls.append((method, path))
            if rest[1] not in (MD, MILL):
                return gs.Response(404, {"errorCode": "ItemNotFound"})
            name = "sap_mirror" if rest[1] == MD else "mill_mirror"
            return gs.Response(200, {"id": rest[1], "displayName": name, "type": "MirroredDatabase", "workspaceId": gs.WS, "properties": {
                "oneLakeTablesPath": f"https://onelake.dfs.fabric.microsoft.com/{gs.WS}/{rest[1]}/Tables",
                "sqlEndpointProperties": {"connectionString": "mirror.datawarehouse.fabric.microsoft.com", "id": "ep-" + rest[1][-1],
                                          "provisioningStatus": "Success"}, "defaultSchema": "dbo"}})
        if method == "GET" and rest == ["lakehouses", LH2]:
            self.calls.append((method, path))
            return gs.Response(200, {"id": LH2, "displayName": "zz_flat", "type": "Lakehouse", "properties": {
                "sqlEndpointProperties": {"id": "ep-flat", "connectionString": gs.SQL_HOST, "provisioningStatus": "Success"}}})
        if method == "GET" and rest[:1] == ["lakehouses"] and not self.lakehouses:
            return gs.Response(404, {"errorCode": "ItemNotFound"})
        return super()._route(method, url, body)


@pytest.fixture
def make(keys, monkeypatch):
    import requests
    from starlette.applications import Starlette
    priv, pub = keys

    def build(sql, lakehouses=True):
        fake = MirrorFabric(lakehouses)
        for verb in ("get", "post", "patch"):
            monkeypatch.setattr(requests, verb, getattr(fake, verb))
        mod = sql()
        monkeypatch.setitem(sys.modules, "pyodbc", mod)
        monkeypatch.setattr(server, "limiter", None)
        app = Starlette(routes=workload_api.routes(WL, Validator(WL, FakeJWKS(pub)), ScopedOBO(EVERY_SCOPE)))
        return TestClient(app), fake, priv, mod
    return build


def _post(client, path, body, priv):
    return client.post(workload_api.PREFIX + path, json=body, headers={"Authorization": f"Bearer {tok(priv)}", "Origin": FABRIC_ORIGIN})


SAP_SRC = {"workspace": gs.WS, "source": MD, "source_name": "sap_mirror", "schema": "dbo"}
MILL_SRC = {"workspace": gs.WS, "source": MILL, "source_name": "mill_mirror", "schema": "dbo"}


def _writes(fake):
    return [c for c in fake.calls if c[0] != "GET" and not c[1].endswith("/getDefinition")]


# ------------------------------------------------------------------ 1. the source: review and check, read-only ---------

def test_the_review_reads_a_mirrored_database_through_its_sql_endpoint_and_says_it_is_read_only(make):
    client, fake, priv, sql = make(sap_endpoint)
    r = _post(client, "/review", {**SAP_SRC, "decisions": []}, priv)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["source_kind"] == "MirroredDatabase"
    assert "read-only" in a["read_only"]["words"] and "Target lakehouse" in a["read_only"]["words"]
    assert "Initial and Delta" in a["read_only"]["mirroring"] and "Parquet" in a["read_only"]["mirroring"]
    assert any(m == "GET" and u.endswith(f"/v1/workspaces/{gs.WS}/mirroredDatabases/{MD}") for m, u in fake.calls)
    assert not _writes(fake) and not any(re.match(r"\s*(CREATE|ALTER|DROP|INSERT|UPDATE|DELETE)", q, re.I) for q in sql.log)


def test_the_sap_pack_s_keys_and_links_are_offered_from_the_pack_with_its_public_sources(make):
    client, _fake, priv, _sql = make(sap_endpoint)
    a = _post(client, "/review", {**SAP_SRC, "decisions": []}, priv).json()
    items = {it["id"]: it for it in a["review"]["items"]}
    sap = a["sap"]
    assert sap["label"] == "SAP pack" and "from the SAP pack" in sap["note"]
    for table in ("VBAK", "VBAP", "KNA1", "MARA", "EKKO", "EKPO"):
        key = items[f"key:{table}"]
        assert key["rule"] == "SAP pack" and key["columns"][0] == "MANDT", key     # the client column, as the pack says
        offer = sap["items"][f"key:{table}"]
        assert offer["from"] == "from the SAP pack" and offer["client"] == "MANDT"
        assert offer["sources"] and all(s["url"].startswith("https://") and s["title"] for s in offer["sources"])
        assert key["review"] == "proposed"                         # the person accepts or rejects it as any other
    links = {i: it for i, it in items.items() if it["type"] == "relationship"}
    for rid in ("rel:EKPO.MANDT+EBELN>EKKO", "rel:EKKO.MANDT+LIFNR>LFA1", "rel:VBAP.MANDT+VBELN>VBAK", "rel:EKPO.MANDT+MATNR>MARA"):
        assert links[rid]["rule"] == "SAP pack", rid
        assert sap["items"][rid]["from"] == "from the SAP pack" and sap["items"][rid]["sources"]
    assert set(sap["items"]) <= set(items)                        # never an item the plan does not have: nothing beyond the pack
    assert all(items[i]["rule"] == "SAP pack" for i in sap["items"])
    assert "Premium Outbound Integration" in sap["licence"] and "between the customer and SAP" in sap["licence"]
    assert sap["learn"]["sap"].startswith("https://learn.microsoft.com/")


def test_a_pack_item_is_accepted_or_rejected_as_any_other(make):
    client, fake, priv, _sql = make(sap_endpoint)
    rv = _post(client, "/review", {**SAP_SRC, "decisions": []}, priv).json()["review"]
    a = _post(client, "/review", {**SAP_SRC, "previous": rv, "decisions": [
        {"item": "rel:EKPO.MANDT+EBELN>EKKO", "review": "accepted", "reason": ""},
        {"item": "rel:EKPO.MANDT+MATNR>MARA", "review": "rejected", "reason": "not needed"}]}, priv).json()
    items = {it["id"]: it for it in a["review"]["items"]}
    assert items["rel:EKPO.MANDT+EBELN>EKKO"]["review"] == "accepted"
    assert items["rel:EKPO.MANDT+MATNR>MARA"]["review"] == "rejected"
    c = _post(client, "/check", {**SAP_SRC, "review": a["review"]}, priv)
    assert c.status_code == 200, c.text
    assert c.json()["sap"]["items"] and not _writes(fake)


def test_a_mirror_of_the_mill_sample_plans_as_a_normal_source(make):
    client, _fake, priv, _sql = make(mill_endpoint)
    a = _post(client, "/review", {**MILL_SRC, "decisions": []}, priv).json()
    assert a["source_kind"] == "MirroredDatabase" and "sap" not in a
    rules = {it["rule"] for it in a["review"]["items"]}
    assert "SAP pack" not in rules
    links = [it for it in a["review"]["items"] if it["type"] == "relationship"]
    assert len(links) >= 10
    keys = {it["table"]: it["columns"] for it in a["review"]["items"] if it["type"] == "key"}
    assert keys["customers"] == ["customer_id"] and keys["sales_orders"] == ["sales_order_id"]


def test_the_sap_offer_needs_the_pack_and_returns_none_without_it():
    from fabric_backend.infer import plan
    assert mirroring.sap_offer(plan(mill.schema())) is None


# ------------------------------------------------------------------ 2. the target lakehouse --------------------------------

FLOW = [{"kind": "silver_notebook", "name": "sap_silver"}, {"kind": "gold_views", "name": "sap_gold"},
        {"kind": "pipeline", "name": "sap_flow"}]


def _build(client, priv, src, outputs, **extra):
    rv = _post(client, "/review", {**src, "decisions": []}, priv).json()["review"]
    return _post(client, "/build", {**src, "review": rv, "outputs": outputs, **extra}, priv)


def test_the_dry_run_writes_to_a_lakehouse_of_the_workspace_and_says_it_is_the_default(make):
    client, fake, priv, _sql = make(sap_endpoint)
    r = _build(client, priv, SAP_SRC, FLOW)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["target"]["lakehouse"] == "demo_lh" and a["target"]["how"] == "default"
    assert "default" in a["target"]["words"] and "Target lakehouse" in a["target"]["words"]
    assert "oneLakeTablesPath" in a["target"]["words"] and "nothing is copied outside Fabric" in a["target"]["words"]
    cards = {c["output"]: c for c in a["outputs"]}
    for kind in ("silver_notebook", "gold_views", "pipeline"):
        assert not cards[kind].get("refusal") and not cards[kind]["answer"].get("error"), cards[kind]
        assert cards[kind]["answer"]["target"]["id"] == gs.LH
    assert "in demo_lh" in cards["silver_notebook"]["answer"]["summary"]
    assert "the sap_mirror tables are only read" in cards["silver_notebook"]["answer"]["summary"]
    assert a["flow"] and a["flow"]["notes"][0] == a["target"]["words"]
    assert not _writes(fake)


def test_the_person_s_lakehouse_wins_and_an_unknown_one_is_refused(make):
    client, _fake, priv, _sql = make(sap_endpoint)
    a = _build(client, priv, SAP_SRC, FLOW[:1], target={"lakehouse": LH2}).json()
    assert a["target"]["how"] == "chosen" and a["target"]["lakehouse"] == "zz_flat"
    words = a["outputs"][0]["answer"]["summary"]
    assert "tables prefixed silver_" in words and "in zz_flat" in words       # a lakehouse without schemas: a prefix
    bad = _build(client, priv, SAP_SRC, FLOW[:1], target={"lakehouse": "nope"}).json()["outputs"][0]["answer"]
    assert bad["kind"] == "not_found" and "is not a lakehouse of this workspace" in bad["error"]


def test_a_workspace_without_a_lakehouse_says_what_to_do_and_writes_nothing(make):
    client, fake, priv, _sql = make(sap_endpoint, lakehouses=False)
    a = _build(client, priv, SAP_SRC, FLOW[:1], dry_run=False).json()
    ans = a["outputs"][0]["answer"]
    assert ans["kind"] == "not_found" and "has no lakehouse" in ans["error"] and "nothing was written" in ans["error"]
    assert not _writes(fake)


def test_bad_targets_are_refused_before_anything_is_read(make):
    client, fake, priv, _sql = make(sap_endpoint)
    rv = _post(client, "/review", {**SAP_SRC, "decisions": []}, priv).json()["review"]
    before = len(fake.calls)
    r = _post(client, "/build", {**SAP_SRC, "review": rv, "outputs": FLOW, "target": "demo_lh"}, priv)
    assert r.status_code == 400 and "'target'" in r.json()["error"]
    assert len(fake.calls) == before


def test_the_mcp_tools_still_refuse_a_mirrored_database_without_a_target():
    """WRITE_TARGET is set by the Krusgraph Model's build only; an MCP tool on a read-only source refuses as before."""
    info, refusal = server._write_info({"item_kind": "MirroredDatabase", "item_name": "sap_mirror"}, "The silver notebook")
    assert info is None and json.loads(refusal)["kind"] == "unsupported" and "needs a lakehouse" in json.loads(refusal)["error"]
    info = {"item_kind": "Lakehouse", "item_name": "demo_lh"}
    assert server._write_info(info, "The silver notebook") == (info, None)


# ------------------------------------------------------------------ 3. silver reads the mirror's OneLake path -----------

def _notebook_of(fake, route="notebooks") -> str:
    body = next(c["body"] for c in fake.created if c["route"] == route)
    part = next(p for p in body["definition"]["parts"] if p["path"] == "notebook-content.py")
    return base64.b64decode(part["payload"]).decode()


def test_create_writes_the_silver_notebook_on_the_target_lakehouse_reading_the_mirror_s_onelake_path(make):
    client, fake, priv, _sql = make(sap_endpoint)
    a = _build(client, priv, SAP_SRC, FLOW[:1], dry_run=False).json()
    assert not a["refused"], a
    text = _notebook_of(fake)
    assert f'MIRROR_TABLES_PATH = "{ABFSS}"' in text
    assert f'"default_lakehouse": "{gs.LH}"' in text               # attached to the target lakehouse, not the mirror
    assert MD in text and "OWNER = " in text and f"{MD}/dbo" in text   # the owner mark names the source it was built from
    assert "def source(table):\n    # Spark reads a Delta table by its path" in text
    assert "SOURCE_SCHEMA = \"dbo\"" in text
    assert "The source is the mirrored database sap_mirror" in text
    # only notebooks were created, in the workspace; nothing in the mirror
    assert [c["route"] for c in fake.created] == ["notebooks"]


class _Stub:
    """Just enough of Spark for the silver notebook's setup cell: no table exists yet, SQL is recorded."""

    def __init__(self):
        self.sql_log = []
        self.catalog = types.SimpleNamespace(tableExists=lambda name: False)

    def sql(self, text):
        self.sql_log.append(text)
        return types.SimpleNamespace(collect=lambda: [])


def _run_setup(text: str, folders: set[str]) -> dict:
    """Run the parameters and setup cells of a silver notebook with stand-ins for pyspark, spark and notebookutils."""
    cells = re.split(r"\n# (?:CELL|PARAMETERS CELL) \*+\n", text)
    params = next(c for c in cells if "SILVER_SCHEMA = " in c and "TABLE_FORMAT" in c)
    setup = next(c for c in cells if "def source(table):" in c)
    strip = lambda c: "\n".join(x for x in c.splitlines() if not x.startswith("# META"))  # noqa: E731
    fake_sql = types.ModuleType("pyspark.sql")
    fake_sql.Window, fake_sql.functions = object(), types.ModuleType("pyspark.sql.functions")
    mods = {"pyspark": types.ModuleType("pyspark"), "pyspark.sql": fake_sql, "pyspark.sql.functions": fake_sql.functions}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        exists = []
        env = {"spark": _Stub(), "notebookutils": types.SimpleNamespace(fs=types.SimpleNamespace(
            exists=lambda p: exists.append(p) or p in folders))}
        exec(strip(params), env)
        exec(strip(setup), env)
        env["_exists_calls"] = exists
        return env
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def test_the_silver_notebook_reads_each_table_where_it_is_in_onelake(make):
    client, fake, priv, _sql = make(sap_endpoint)
    _build(client, priv, SAP_SRC, FLOW[:1], dry_run=False)
    text = _notebook_of(fake)
    env = _run_setup(text, {f"{ABFSS}/dbo/VBAK/_delta_log", f"{ABFSS}/EKKO/_delta_log"})
    assert env["source"]("VBAK") == f"delta.`{ABFSS}/dbo/VBAK`"   # Tables/<schema>/<table> when it holds a Delta log
    assert env["source"]("EKKO") == f"delta.`{ABFSS}/EKKO`"       # else Tables/<table>
    assert env["target"]("VBAK") == "`silver`.`VBAK`"             # written to the target lakehouse's silver schema
    assert "CREATE SCHEMA IF NOT EXISTS `silver`" in env["spark"].sql_log
    assert all(p.startswith(ABFSS) for p in env["_exists_calls"])  # read in OneLake only


def test_the_lakehouse_notebook_is_unchanged_by_n201():
    """A lakehouse source writes into itself and reads its own tables: the generated text has no OneLake path."""
    from fabric_backend import seed
    from fabric_backend.infer import plan
    s = silver.spec(plan(seed.schema("shop")), {"item_id": gs.LH, "item_name": "demo_lh", "workspace_id": gs.WS, "schema": "shop"})
    text = silver.notebook_source(s)
    assert "MIRROR_TABLES_PATH" not in text and "def source(table):\n    return q(SOURCE_SCHEMA, table)" in text


def test_the_onelake_path_comes_from_onelaketablespath_or_the_two_guids():
    assert mirroring.abfss(TABLES_PATH) == ABFSS
    assert mirroring.abfss("https://westus-onelake.dfs.fabric.microsoft.com/w/i/Tables/") == "abfss://w@westus-onelake.dfs.fabric.microsoft.com/i/Tables"
    assert mirroring.abfss(None, gs.WS, MD) == ABFSS
    assert mirroring.abfss(None, "demo", "x") is None
    assert mirroring.choose_target([{"id": "2", "displayName": "b"}, {"id": "1", "displayName": "A"}]) == ({"id": "1", "displayName": "A"}, "default")
    assert mirroring.choose_target([], None) == (None, "none")


# ------------------------------------------------------------------ the words: no claims ---------------------------------

def test_no_claim_of_certification_partnership_or_endorsement():
    import inspect
    text = inspect.getsource(mirroring)
    for word in ("certified", "certification", "partner", "endorse", "approved by"):
        assert word not in text.lower(), word
