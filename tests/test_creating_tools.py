"""create_semantic_model, create_views, create_data_agent and app_starter: the modules on the shop schema, the REST
calls mocked the way test_ontology_tools.py mocks create_ontology (create, update, long-running operation, 403 as
missing consent, 404), the views' SQL run on SQLite, and tools/list."""
import datetime
import importlib
import json
import re
import sqlite3

import pytest
import requests

from fabric_backend import app_starter, data_agent, seed, semantic_model, server, views
from fabric_backend.graphql import decode, definition
from fabric_backend.infer import plan
from fabric_backend.schema import Schema
from test_inference_quality import load, names_only

WS = "11111111-1111-1111-1111-111111111111"
SHIP_TO = [{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}]
deploy = importlib.import_module("fabric_backend.deploy")
INFO = dict(workspace_id=WS, item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse", schema="shop", sql_endpoint="x.datawarehouse.fabric.microsoft.com")


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


@pytest.fixture
def shop(monkeypatch):
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": "Lakehouse", "id": "lh-1", "displayName": src,
                                                                             "sql_host": "x.datawarehouse.fabric.microsoft.com", "sql_db": src})
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: []))
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    monkeypatch.setattr(deploy.time, "sleep", lambda s: None)
    return "Sales", "shop_lh"


# ------------------------------------------------------------------ semantic model -------------

def test_semantic_model_envelope_has_every_part_and_the_platform_file():
    draft = semantic_model.draft(plan(seed.schema("shop")), INFO, "shop_model")
    body = semantic_model.envelope(draft["parts"], "shop_model", "d")
    paths = [p["path"] for p in body["definition"]["parts"]]
    assert body["displayName"] == "shop_model" and body["description"] == "d" and body["definition"]["format"] == "TMDL"
    assert "README.generated.md" not in paths and ".platform" in paths and "definition.pbism" in paths
    assert "definition/model.tmdl" in paths and "definition/tables/orders.tmdl" in paths
    import base64
    platform = json.loads(base64.b64decode(next(p["payload"] for p in body["definition"]["parts"] if p["path"] == ".platform")))
    assert platform["metadata"] == {"type": "SemanticModel", "displayName": "shop_model"} and platform["config"]["version"] == "2.0"
    assert all(p["payloadType"] == "InlineBase64" for p in body["definition"]["parts"])
    assert semantic_model.envelope(draft["parts"], "shop_model") == semantic_model.envelope(draft["parts"], "shop_model")   # deterministic


def test_create_semantic_model_dry_run_creates_nothing(shop, monkeypatch):
    posted = []
    monkeypatch.setattr(requests, "post", lambda url, **k: posted.append(url) or Resp(500))
    out = json.loads(server.create_semantic_model(*shop, name="shop_model", schema="shop"))
    assert out["dry_run"] is True and posted == [] and "error" not in out
    assert out["rest"]["url"].endswith(f"/workspaces/{WS}/semanticModels") and ".platform" in out["rest"]["parts"]
    assert out["rest"]["delegated_scope"] == "SemanticModel.ReadWrite.All or Item.ReadWrite.All"
    assert "definition/tables/orders.tmdl" in out["parts"] and any("Refresh" in s for s in out["after_creation"])
    assert out["summary"]["tables"] == 7


def test_create_semantic_model_posts_then_updates_in_place(shop, monkeypatch):
    calls = []
    items = {"value": []}
    polls = iter([Resp(200, {"status": "Running"}), Resp(200, {"status": "Succeeded"})])
    monkeypatch.setattr(requests, "get", lambda url, **k: next(polls) if "/operations/" in url else Resp(200, items))
    monkeypatch.setattr(requests, "post", lambda url, **k: calls.append((url, k.get("json"))) or Resp(202, None, {"x-ms-operation-id": "op-1"}))
    out = json.loads(server.create_semantic_model(*shop, name="shop_model", schema="shop", dry_run=False))
    assert out["result"]["status"] == "Succeeded" and out["result"]["mode"] == "created" and "error" not in out
    url, body = calls[0]
    assert url.endswith(f"/workspaces/{WS}/semanticModels") and body["displayName"] == "shop_model" and body["definition"]["format"] == "TMDL"
    assert {p["path"] for p in body["definition"]["parts"]} >= {"definition/model.tmdl", "definition.pbism", ".platform"}
    # second run: the item exists -> updateDefinition on it, never a second create
    items["value"] = [{"id": "sm-1", "displayName": "shop_model", "type": "SemanticModel"}]
    calls.clear()
    monkeypatch.setattr(requests, "post", lambda url, **k: calls.append((url, k.get("json"))) or Resp(200, None))
    out = json.loads(server.create_semantic_model(*shop, name="shop_model", schema="shop", dry_run=False))
    assert out["result"] == {"status": "Succeeded", "mode": "updated", "id": "sm-1"}
    assert calls[0][0].endswith("/semanticModels/sm-1/updateDefinition") and set(calls[0][1]) == {"definition"}


def test_create_semantic_model_403_is_consent_and_404_is_not_found(shop, monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, **k: Resp(200, {"value": []}))
    monkeypatch.setattr(requests, "post", lambda url, **k: Resp(403, {"errorCode": "InsufficientScopes", "message": "The caller lacks the required scope"}))
    out = json.loads(server.create_semantic_model(*shop, name="shop_model", schema="shop", dry_run=False))
    assert out["kind"] == "consent" and "SemanticModel.ReadWrite.All" in out["hint"] and "docs/SCOPES.md" in out["hint"]
    assert "fabric-token" not in json.dumps(out)
    monkeypatch.setattr(requests, "post", lambda url, **k: Resp(404, {"errorCode": "WorkspaceNotFound", "message": "no such workspace"}))
    out = json.loads(server.create_semantic_model(*shop, name="shop_model", schema="shop", dry_run=False))
    assert out["kind"] == "not_found"
    # the long-running operation failing after acceptance
    polls = iter([Resp(200, {"status": "Failed", "error": {"errorCode": "InvalidDefinition", "message": "bad tmdl"}})])
    monkeypatch.setattr(requests, "get", lambda url, **k: next(polls) if "/operations/" in url else Resp(200, {"value": []}))
    monkeypatch.setattr(requests, "post", lambda url, **k: Resp(202, None, {"x-ms-operation-id": "op-2"}))
    out = json.loads(server.create_semantic_model(*shop, name="shop_model", schema="shop", dry_run=False))
    assert out["result"]["status"] == "Failed" and out["kind"] in ("fabric_error", "unexpected") and "bad tmdl" in out["error"]


# ------------------------------------------------------------------ views ----------------------

def sqlite_with_seed():
    con = sqlite3.connect(":memory:")
    for name, ddl in seed.SCHEMAS.items():
        con.execute(f"CREATE TABLE [{name}] ({ddl})")
        data = [tuple(v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v for v in r) for r in seed.rows()[name]]
        con.executemany(f"INSERT INTO [{name}] VALUES ({','.join('?' * len(data[0]))})", data)
    return con


def for_sqlite(sql: str) -> str:
    """SQLite has no schemas across databases in a view and no CREATE OR ALTER; the rest of the T-SQL is portable."""
    return re.sub(r"\[(shop|krusgraph)\]\.", "", sql).replace("CREATE OR ALTER VIEW", "CREATE VIEW")


def test_views_sql_only_touches_the_views_schema_and_runs_on_the_seed_rows():
    p = plan(seed.schema("shop"), confirmed=SHIP_TO)
    st = views.statements(p)
    assert st["schema"] == "krusgraph" and st["schema_sql"] == "IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'krusgraph') EXEC('CREATE SCHEMA [krusgraph]')"
    names = [v["name"] for v in st["views"]]
    assert names == ["vw_order_items", "vw_orders_ship_to"]                        # the fact table, and the hand-given link
    wide = st["views"][0]
    assert wide["tables"] == ["order_items", "orders", "products", "addresses", "customers", "categories"]
    assert wide["sql"].startswith("CREATE OR ALTER VIEW [krusgraph].[vw_order_items] AS\nSELECT\n    f.[order_id] AS [order_id]")
    assert "LEFT JOIN [shop].[customers] AS d4 ON d1.[customer_id] = d4.[customer_id]" in wide["sql"]
    assert "d5.[name] AS [categories_name]" in wide["sql"] and "d4.[name] AS [customers_name]" in wide["sql"]
    for v in st["views"]:
        assert "DROP" not in v["sql"].upper() and v["sql"].count("CREATE OR ALTER VIEW [krusgraph].") == 1
        assert re.findall(r"CREATE OR ALTER VIEW \[(\w+)\]", v["sql"]) == ["krusgraph"]
    con = sqlite_with_seed()
    for v in st["views"]:
        con.execute(for_sqlite(v["sql"]))
    assert con.execute("SELECT COUNT(*) FROM [vw_order_items]").fetchone()[0] == 134
    assert con.execute("SELECT COUNT(*) FROM [vw_order_items] WHERE [customers_name] IS NULL").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM [vw_orders_ship_to]").fetchone()[0] == 60
    assert views.statements(p) == st                                                # deterministic
    # names come from the metadata; a quote in a name is escaped, not interpreted
    s = Schema.from_information_schema([("dbo", "a]b", "x", "int", 1), ("dbo", "a]b", "c_id", "int", 2), ("dbo", "a]b", "d_id", "int", 3),
                                        ("dbo", "c", "c_id", "int", 1), ("dbo", "d", "d_id", "int", 1)])
    st2 = views.statements(plan(s), "my_views")
    assert st2["views"][0]["sql"].startswith("CREATE OR ALTER VIEW [my_views].[vw_a]]b] AS") and "[dbo].[a]]b] AS f" in st2["views"][0]["sql"]
    with pytest.raises(ValueError):
        views.schema_sql("bad;name")


def test_views_on_tpch_and_an_empty_plan():
    p = plan(names_only(load("tpch")))
    st = views.statements(p)
    names = [v["name"] for v in st["views"]]
    assert names[0] == "vw_LINEITEM" and any(n.startswith("vw_PARTSUPP_") or n.startswith("vw_ORDERS_") for n in names)   # R2 links are "hard"
    assert "LEFT JOIN [dbo].[ORDERS] AS d1 ON f.[L_ORDERKEY] = d1.[O_ORDERKEY]" in st["views"][0]["sql"]
    lonely = plan(Schema.from_information_schema([("dbo", "t", "id", "int", 1), ("dbo", "t", "x", "int", 2)]))
    assert views.statements(lonely)["views"] == []


def test_create_views_tool_dry_run_then_applies_through_the_statement_runner(shop, monkeypatch):
    ran = []

    def factory(item, tok):
        def execute(sql):
            return []
        execute.statement = lambda sql: ran.append(sql)
        return execute
    monkeypatch.setattr(server, "_execute_factory", factory)
    out = json.loads(server.create_views(*shop, schema="shop", confirmed=SHIP_TO))
    assert out["dry_run"] is True and ran == [] and [v["name"] for v in out["views"]] == ["vw_order_items", "vw_orders_ship_to"]
    assert out["schema_sql"].startswith("IF NOT EXISTS") and "not been created on a live endpoint yet" in out["note"]
    out = json.loads(server.create_views(*shop, schema="shop", confirmed=SHIP_TO, dry_run=False))
    assert out["result"] == {"status": "Succeeded", "views": 2, "schema": "krusgraph"}
    assert [a["status"] for a in out["applied"]] == ["ok", "ok", "ok"] and ran[0].startswith("IF NOT EXISTS") and len(ran) == 3
    out = json.loads(server.create_views(*shop, schema="shop", views_schema="reporting", confirmed=SHIP_TO))
    assert all("[reporting]." in v["sql"] for v in out["views"])
    bad = json.loads(server.create_views(*shop, schema="shop", views_schema="x;drop"))
    assert bad["kind"] in ("unexpected", "bad_input") and "DROP" not in json.dumps(bad).upper().replace("X;DROP", "")


def test_create_views_explains_a_refusing_endpoint_and_suggests_a_warehouse(shop, monkeypatch):
    def factory(item, tok):
        def execute(sql):
            return []

        def statement(sql):
            raise RuntimeError("('42000', \"[42000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]CREATE VIEW permission denied in database 'shop_lh'. (262)\")")
        execute.statement = statement
        return execute
    monkeypatch.setattr(server, "_execute_factory", factory)
    out = json.loads(server.create_views(*shop, schema="shop", dry_run=False))
    assert out["kind"] in ("sql_error", "no_access", "unexpected") and "warehouse" in out["hint"] and "result" not in out


# ------------------------------------------------------------------ data agent -----------------

def test_data_agent_draft_has_instructions_examples_and_rest_plan():
    p = plan(seed.schema("shop"), confirmed=SHIP_TO)
    d = data_agent.draft(p, INFO, "shop_agent", "shop")
    assert d["datasource"] == {"type": "LakehouseTables", "lakehouseReference": {"referenceType": "ById", "itemId": "lh-1", "workspaceId": WS}}
    text = d["instructions"]
    assert "shop.order_items: columns order_id, line_no, product_id, quantity; key order_id+line_no (rule K5)" in text
    assert "orders -> customers: orders.customer_id = customers.customer_id (rule R1, many-to-one)" in text
    assert "audit_log" in text and "square brackets" in text
    assert 5 <= len(d["fewshots"]) <= 10 and d["fewshots"][0] == {"question": "How many rows are there in order_items?",
                                                                 "query": "SELECT COUNT_BIG(*) AS row_count FROM [shop].[order_items]"}
    assert any("JOIN [shop].[customers]" in f["query"] for f in d["fewshots"]) and all(f["query"].count("[shop].") >= 1 for f in d["fewshots"])
    assert d["tables_to_select"] == ["customers", "categories", "products", "addresses", "orders", "order_items", "audit_log"]
    assert d["rest"][0].startswith(f"POST /v1/workspaces/{WS}/dataAgents") and d["delegated_scope"].startswith("Item.ReadWrite.All")
    assert data_agent.draft(p, INFO, "shop_agent", "shop") == d
    wh = data_agent.draft(p, {**INFO, "item_kind": "Warehouse"}, "a", "dbo")
    assert wh["datasource"]["type"] == "FabricItem" and wh["datasource"]["itemReference"]["itemId"] == "lh-1"
    # the few-shot SQL is runnable (on SQLite, with COUNT_BIG and TOP rewritten as the demo validation does)
    con = sqlite_with_seed()
    for f in d["fewshots"]:
        sql = re.sub(r"\[shop\]\.", "", f["query"]).replace("COUNT_BIG(", "COUNT(")
        sql = re.sub(r"SELECT TOP \((\d+)\) (.*)", lambda m: f"SELECT {m.group(2)} LIMIT {m.group(1)}", sql, flags=re.S)
        assert con.execute(sql).fetchall() is not None, f["question"]


class FakeFabric:
    """The data agent staging API as the specification describes it, in memory."""

    def __init__(self, existing_agent=None, fail=None):
        self.calls = []
        self.agents = {existing_agent: {"id": "da-1", "displayName": existing_agent, "type": "DataAgent"}} if existing_agent else {}
        self.settings, self.datasources, self.fewshots, self.published, self.selected = {}, [], [], [], []
        self.fail = fail or {}

    def _hit(self, method, url, **k):
        self.calls.append((method, url.split("/v1/")[1], k.get("json"), k.get("params")))
        for needle, resp in self.fail.items():
            if needle in url:
                return resp
        if method == "get" and url.endswith("/items?type=DataAgent"):
            return Resp(200, {"value": list(self.agents.values())})
        if method == "post" and url.endswith("/dataAgents"):
            self.agents["new"] = {"id": "da-2", "displayName": k["json"]["displayName"], "type": "DataAgent"}
            return Resp(201, self.agents["new"])
        if method == "patch" and url.endswith("/staging/settings"):
            self.settings = k["json"]
            return Resp(200, k["json"])
        if method == "get" and url.endswith("/staging/datasources"):
            return Resp(200, {"value": self.datasources})
        if method == "post" and url.endswith("/staging/datasources"):
            ds = {"id": "ds-1", **k["json"]}
            self.datasources.append(ds)
            return Resp(201, ds)
        if method == "patch" and url.endswith("/staging/datasources/ds-1"):
            return Resp(200, k["json"])
        if method == "get" and url.endswith("/elements"):
            root = (k.get("params") or {}).get("rootId")
            tree = {None: [{"id": "T", "type": "Tables", "displayName": "Tables", "hasSubElements": True}],
                    "T": [{"id": "t-orders", "type": "Table", "displayName": "orders", "isSelected": False, "hasSubElements": True},
                          {"id": "t-customers", "type": "Table", "displayName": "customers", "isSelected": True, "hasSubElements": True},
                          {"id": "t-other", "type": "Table", "displayName": "other", "isSelected": False, "hasSubElements": True}]}
            return Resp(200, {"value": tree.get(root, [])})
        if method == "patch" and url.endswith("/elements"):
            self.selected.append(k["params"]["id"])
            return Resp(200, {})
        if method == "get" and url.endswith("/fewshots"):
            return Resp(200, {"value": self.fewshots})
        if method == "post" and url.endswith("/fewshots"):
            shot = {"id": f"fs-{len(self.fewshots) + 1}", **k["json"]}
            self.fewshots.append(shot)
            return Resp(201, shot)
        if method == "patch" and "/fewshots/" in url:
            fid = url.rsplit("/", 1)[1]
            for f in self.fewshots:
                if f["id"] == fid:
                    f.update(k["json"])
            return Resp(200, {})
        if method == "post" and url.endswith("/staging/publish"):
            self.published.append(k["json"])
            return Resp(200, k["json"])
        return Resp(404, {"message": f"unexpected {method} {url}"})


@pytest.fixture
def fake(monkeypatch):
    def install(**kw):
        f = FakeFabric(**kw)
        for m in ("get", "post", "patch"):
            monkeypatch.setattr(requests, m, (lambda method: lambda url, **k: f._hit(method, url, **k))(m))
        return f
    return install


def test_create_data_agent_creates_configures_and_publishes_then_updates_in_place(shop, fake):
    out = json.loads(server.create_data_agent(*shop, name="shop_agent", schema="shop"))
    assert out["dry_run"] is True and "instructions" in out["agent"] and len(out["agent"]["fewshots"]) >= 5
    f = fake()
    out = json.loads(server.create_data_agent(*shop, name="shop_agent", schema="shop", dry_run=False))
    assert out["result"]["status"] == "Succeeded" and out["result"]["id"] == "da-2" and "error" not in out, out
    log = out["result"]["log"]
    assert log[0].startswith("created data agent 'shop_agent'") and "published" in log and "examples: 10 added, 0 updated, 0 unchanged" in log
    assert any("selected 2 of 7 tables" in line for line in log)                 # orders selected now, customers already was; 'other' left alone
    assert f.selected == ["t-orders"] and f.settings["aiInstructions"].startswith("You answer questions about the shop_lh data")
    assert f.datasources[0]["type"] == "LakehouseTables" and f.datasources[0]["lakehouseReference"]["itemId"] == "lh-1"
    assert len(f.fewshots) == 10 and f.published == [{"publishedDescription": "Published by Krusgraph from the inferred plan"}]
    assert not any(c[0] == "delete" for c in f.calls)
    # run again with one example changed: the agent and data source are reused, one fewshot patched, nothing added twice
    f.agents = {"shop_agent": {"id": "da-2", "displayName": "shop_agent", "type": "DataAgent"}}
    f.fewshots[0]["query"] = "SELECT 1"
    f.calls.clear()
    out = json.loads(server.create_data_agent(*shop, name="shop_agent", schema="shop", dry_run=False, publish=False))
    log = out["result"]["log"]
    assert log[0] == "reused data agent 'shop_agent' (da-2)" and "reused data source ds-1" in log
    assert "examples: 0 added, 1 updated, 9 unchanged" in log and "published" not in log and len(f.fewshots) == 10
    assert not any(c[0] == "post" and c[1].endswith("/dataAgents") for c in f.calls)


def test_create_data_agent_403_is_consent_404_is_not_found_and_a_strange_tree_is_reported(shop, fake):
    fake(fail={"/staging/settings": Resp(403, {"errorCode": "InsufficientScopes", "message": "scope"})})
    out = json.loads(server.create_data_agent(*shop, name="shop_agent", schema="shop", dry_run=False))
    assert out["kind"] == "consent" and "Item.ReadWrite.All" in out["hint"] and out["result"]["step"] == "setting the instructions"
    fake(fail={"/dataAgents": Resp(404, {"errorCode": "WorkspaceNotFound", "message": "gone"})})
    out = json.loads(server.create_data_agent(*shop, name="shop_agent", schema="shop", dry_run=False))
    assert out["kind"] == "not_found"
    f = fake(fail={"/elements": Resp(200, {"value": [{"weird": True}]})})
    out = json.loads(server.create_data_agent(*shop, name="shop_agent", schema="shop", dry_run=False))
    assert out["result"]["status"] == "Succeeded" and any("table selection skipped" in line for line in out["result"]["log"])


# ------------------------------------------------------------------ app starter ----------------

def test_app_starter_uses_the_api_definition_names():
    p = plan(seed.schema("shop"), confirmed=SHIP_TO)
    desc = server.describe_definition(decode(definition(p, "shop_api", WS, "ep", "SqlAnalyticsEndpoint")))
    s = app_starter.starter(desc, f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/graphqlapis/x/graphql", "shop_api", WS)
    assert len(s["queries"]) == 5 and len({q["query"].split("(")[0] for q in s["queries"]}) == 5     # five different root types
    assert any("customer { customer_id name country }" in q["query"] for q in s["queries"])             # the field names are the API's
    assert "ship_to → addresses (ManyToOne)" in s["lovable_prompt"]
    assert all(q["query"].startswith("query { ") and "(first: 10) { items {" in q["query"] for q in s["queries"])
    prompt = s["lovable_prompt"]
    assert 'GraphQL API "shop_api"' in prompt and "- orders (query `orders`, by key, read-only)" in prompt and "order_items" in prompt
    assert "client secret" in prompt and "```graphql" in prompt
    assert s["connection"]["endpoint"].endswith("/graphql") and "api.fabric.microsoft.com/.default" in s["connection"]["auth"]
    assert any("Introspection" in c for c in s["checklist"]) and any("Run Queries and Mutations" in c for c in s["checklist"])
    assert "run against a live API for GraphQL item" in s["note"]


def test_app_starter_tool_reads_the_definition(shop, monkeypatch):
    existing = decode(definition(plan(seed.schema("shop")), "shop_api", WS, "ep-1", "SqlAnalyticsEndpoint"))
    monkeypatch.setattr(server, "find_item_by_name", lambda ws, name, headers, types=None: {"id": "api-1"} if name == "shop_api" else None)
    monkeypatch.setattr(server, "_graphql_definition", lambda ws, api_id, headers: existing)
    out = json.loads(server.app_starter("Sales", "shop_api"))
    assert out["connection"]["endpoint"] == f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/graphqlapis/api-1/graphql"
    assert len(out["queries"]) == 5 and "shop_api" in out["lovable_prompt"]
    assert json.loads(server.app_starter("Sales", "nope"))["kind"] == "not_found"


# ------------------------------------------------------------------ tools/list -----------------

def test_creating_tools_are_listed_with_write_annotations_and_dry_run_default():
    from starlette.testclient import TestClient
    with TestClient(server.build_app()) as client:
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                        headers={"Accept": "application/json, text/event-stream"})
        body = r.text
        payload = json.loads(body.split("data: ", 1)[1].split("\n", 1)[0]) if "data: " in body else r.json()
        tools = {t["name"]: t for t in payload["result"]["tools"]}
    for name in ("create_semantic_model", "create_views", "create_data_agent"):
        a = tools[name]["annotations"]
        assert a["readOnlyHint"] is False and a["destructiveHint"] is True and a["idempotentHint"] is True, name
        assert tools[name]["inputSchema"]["properties"]["dry_run"]["default"] is True, name
        assert tools[name]["title"]
    assert tools["app_starter"]["annotations"]["readOnlyHint"] is True
    for word in ("create_semantic_model", "create_views", "create_data_agent", "app_starter"):
        assert word in server.mcp.instructions
