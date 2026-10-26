"""drift_monitor_draft / create_drift_monitor: the comparison of two plans, what a change reaches (lineage edges and
plan_drift per GraphQL API), the message, the generated notebook and pipeline, and the REST calls (mocked). The
generated notebook runs two nights on a local Spark session in tests/test_spark_notebooks.py when PySpark is installed."""
import ast
import base64
import datetime
import json

import pytest

from fabric_backend import monitor, notebook, seed
from fabric_backend.graphql import decode, definition
from fabric_backend.infer import plan
from fabric_backend.schema import Column, Schema, Table

WS = "11111111-1111-1111-1111-111111111111"
SRC = {"workspace_id": WS, "item_id": "lh-1", "item_name": "shop_lh", "schema": "shop", "schemas_enabled": True, "sql_db": "shop_lh",
       "source_id": "ep-1", "source_type": "SqlAnalyticsEndpoint"}


def shop(drop=None, retype=None, add=None):
    s = seed.schema("shop")
    if drop:
        t, c = drop
        s.tables[t] = Table(t, [x for x in s.tables[t].columns if x.name != c], schema="shop")
    if retype:
        t, c, ty = retype
        s.tables[t] = Table(t, [Column(x.name, ty if x.name == c else x.data_type) for x in s.tables[t].columns], schema="shop")
    if add:
        s.tables[add] = Table(add, [Column(f"{add[:-1]}_id", "int"), Column("order_id", "int")], schema="shop")
    return plan(s)


# ------------------------------------------------------------------ the comparison ------------------------------

def test_snapshot_is_plain_data_with_rules():
    snap = monitor.snapshot(shop())
    assert snap["schema"] == "shop" and snap["tables"]["orders"]["key"] == ["order_id"] and snap["tables"]["orders"]["key_rule"] == "K2"
    assert snap["tables"]["audit_log"]["key_rule"] == "K3" and snap["tables"]["customers"]["columns"]["country"] == "string"
    assert {"source": "orders", "columns": ["customer_id"], "target": "customers", "target_columns": ["customer_id"], "rule": "R1"} in snap["relationships"]
    assert json.loads(json.dumps(snap)) == snap and monitor.snapshot(shop()) == snap


def test_first_run_and_no_change():
    snap = monitor.snapshot(shop())
    first = monitor.diff(None, snap)
    assert first["first_run"] and not first["changed"]
    same = monitor.diff(snap, monitor.snapshot(shop()))
    assert not same["first_run"] and not same["changed"]
    assert monitor.summary_text("shop_lh.shop", same, since="2026-10-25 02:00 UTC")[0] == "Drift monitor for shop_lh.shop: no change since 2026-10-25 02:00 UTC"


def test_diff_names_every_kind_of_change():
    old = monitor.snapshot(shop())
    new = monitor.snapshot(shop(drop=("customers", "country"), retype=("orders", "order_date", "timestamp"), add="returns"))
    d = monitor.diff(old, new)
    assert d["changed"] and d["tables_added"] == ["returns"] and d["tables_removed"] == []
    assert d["columns_removed"] == [{"table": "customers", "column": "country", "type": "string"}]
    assert d["types_changed"] == [{"table": "orders", "column": "order_date", "from": "date", "to": "timestamp"}]
    assert any(r["source"] == "returns" for r in d["relationships_added"])
    gone = monitor.diff(old, monitor.snapshot(shop(drop=("orders", "customer_id"))))
    assert {"source": "orders", "columns": ["customer_id"], "target": "customers", "target_columns": ["customer_id"], "rule": "R1"} in gone["relationships_removed"]
    assert monitor.touched_tables(gone) == ["orders"]
    keyed = monitor.diff(old, monitor.snapshot(shop(drop=("orders", "order_id"))))
    orders = next(k for k in keyed["keys_changed"] if k["table"] == "orders")
    assert orders["from"] == ["order_id"] and orders["from_rule"] == "K2"


def test_what_a_change_reaches_and_the_message():
    old_plan, new_plan = shop(), shop(drop=("customers", "country"))
    changes = monitor.diff(monitor.snapshot(old_plan), monitor.snapshot(new_plan))
    edges = [{"table": "customers", "kind": "graphql_api", "object": "shop_api", "id": "api-1", "via": "x", "certain": True},
             {"table": "customers", "kind": "view", "object": "krusgraph.vw_orders", "id": "lh-1", "via": "y", "certain": True},
             {"table": "products", "kind": "semantic_model", "object": "shop_model", "id": "sm-1", "via": "z", "certain": True}]
    api_body = decode(definition(old_plan, "shop_api", WS, "ep-1", "SqlAnalyticsEndpoint"))
    apis = monitor.api_drift(new_plan, {"shop_api": api_body, "other_api": dict(api_body, datasources=[dict(api_body["datasources"][0], sourceItemId="elsewhere")])},
                             WS, "ep-1", "SqlAnalyticsEndpoint")
    assert [a["api"] for a in apis] == ["shop_api"] and apis[0]["removed_columns"] == ["shop.customers.country"]
    impact = monitor.affected(changes, edges, apis)
    assert impact["objects"] == [{"kind": "graphql_api", "object": "shop_api"}, {"kind": "view", "object": "krusgraph.vw_orders"}]
    title, lines = monitor.summary_text("shop_lh.shop", changes, impact, since="2026-10-25 02:00 UTC")
    assert title == "Drift monitor for shop_lh.shop: changes since 2026-10-25 02:00 UTC"
    assert lines[0] == "Column country in table customers disappeared — used by GraphQL API shop_api, view krusgraph.vw_orders."
    assert any("GraphQL API shop_api still maps shop.customers.country" in x and "plan_drift" in x for x in lines)
    msg = monitor.teams_message(title, lines)
    card = msg["attachments"][0]
    assert msg["type"] == "message" and card["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert card["content"]["type"] == "AdaptiveCard" and card["content"]["body"][0]["text"] == title
    assert [b["text"] for b in card["content"]["body"][1:]] == lines
    many = monitor.teams_message("t", [f"line {i}" for i in range(40)])
    assert len(many["attachments"][0]["content"]["body"]) == 32


def test_send_posts_json_only_to_https_and_fails_loudly():
    sent = []

    class R:
        def __init__(self, status):
            self.status_code = status
    assert monitor.send("https://example.test/hook", {"x": 1}, post=lambda url, json, timeout: sent.append((url, json)) or R(202)) == 202
    assert sent == [("https://example.test/hook", {"x": 1})]
    with pytest.raises(ValueError):
        monitor.send("http://example.test/hook", {}, post=lambda *a, **k: R(200))
    with pytest.raises(RuntimeError, match="HTTP 400"):
        monitor.send("https://example.test/hook", {}, post=lambda *a, **k: R(400))


# ------------------------------------------------------------------ the generated items -------------------------

def test_notebook_has_no_secret_reads_the_webhook_from_its_parameter_and_is_valid_python():
    cells = monitor.notebook_cells(SRC, "abc1234")
    kinds = [k for k, _ in cells]
    assert kinds[:3] == ["markdown", "code", "parameters"]
    assert cells[1][1] == '%pip install "fabric-backend @ git+https://github.com/Krusmaster/fabric-backend@abc1234" --quiet'
    params = cells[2][1]
    assert 'webhook_url = ""' in params and 'notify = "changes"' in params
    for kind, code in cells[3:]:
        ast.parse(code)
    text = notebook.fabric_source(cells, notebook.notebook_metadata(WS, "lh-1", "shop_lh"))
    assert notebook.parse(text) == cells
    assert "getToken('pbi')" in text and "secret" not in text.lower().replace("no secret is stored", "")
    assert "monitor.diff(last, today)" in text and "lineage.workspace_edges" in text and "monitor.api_drift" in text
    assert "monitor.save(" in text and text.index("monitor.send(") < text.index("monitor.save(")      # a failed webhook keeps tomorrow's report


def test_pipeline_passes_the_parameters_and_hides_the_webhook():
    content = monitor.pipeline_content("nb-1", WS, "shop_lh.shop")
    act = content["properties"]["activities"][0]
    assert act["type"] == "TridentNotebook" and act["typeProperties"]["notebookId"] == "nb-1" and act["typeProperties"]["workspaceId"] == WS
    p = act["typeProperties"]["parameters"]
    assert p["webhook_url"] == {"value": {"value": "@pipeline().parameters.webhook_url", "type": "Expression"}, "type": "string"}
    assert p["_inlineInstallationEnabled"] == {"value": True, "type": "bool"} and act["policy"]["secureInput"] is True
    assert content["properties"]["parameters"]["webhook_url"] == {"type": "string", "defaultValue": ""}
    body = notebook.pipeline_envelope("m_nightly", content)
    parts = {x["path"]: base64.b64decode(x["payload"]).decode() for x in body["definition"]["parts"]}
    assert json.loads(parts["pipeline-content.json"]) == content and json.loads(parts[".platform"])["metadata"]["type"] == "DataPipeline"


def test_schedule_is_daily_with_an_end():
    s = monitor.schedule_body("02:30", "W. Europe Standard Time", start=datetime.date(2026, 10, 27))
    assert s == {"enabled": True, "configuration": {"type": "Daily", "startDateTime": "2026-10-27T00:00:00", "endDateTime": "2036-10-24T23:59:00",
                                                     "localTimeZoneId": "W. Europe Standard Time", "times": ["02:30"]}}


# ------------------------------------------------------------------ the tools (REST mocked) ---------------------

import requests  # noqa: E402

from fabric_backend import server  # noqa: E402


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
def lakehouse(monkeypatch):
    import importlib
    deploy = importlib.import_module("fabric_backend.deploy")
    kind = {"type": "Lakehouse"}
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": kind["type"], "id": "lh-1", "displayName": src, "sql_host": "h",
                                                                             "sql_db": src, "schemas_enabled": True})
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: []))
    monkeypatch.setattr(server, "source_for", lambda ws, item, headers: ("ep-1", "SqlAnalyticsEndpoint"))
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    monkeypatch.setattr(deploy.time, "sleep", lambda s: None)
    return kind


def test_draft_gives_notebook_pipeline_and_schedule_and_creates_nothing(lakehouse, monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("a draft never posts"))
    out = json.loads(server.drift_monitor_draft("Sales", "shop_lh", schema="shop", at="03:15"))
    assert out["notebook"]["content"].startswith("# Fabric notebook source") and out["notebook"]["name"] == "drift_monitor_shop"
    assert out["pipeline"]["name"] == "drift_monitor_shop_nightly" and out["schedule"]["configuration"]["times"] == ["03:15"]
    assert out["plans_table"] == "krusgraph.plans" and "webhook_url" in out["set_up_in_fabric"][0]
    assert out["message_example"]["attachments"][0]["content"]["body"][0]["text"] == "Drift monitor for shop_lh.shop: first run"
    assert '"source_id": "ep-1"' in out["notebook"]["content"]
    bad = json.loads(server.drift_monitor_draft("Sales", "shop_lh", schema="shop", at="25:00"))
    assert bad["kind"] == "bad_input" and "hh:mm" in bad["error"]
    lakehouse["type"] = "Warehouse"
    assert json.loads(server.drift_monitor_draft("Sales", "wh", schema="shop"))["kind"] == "unsupported"


def test_create_drift_monitor_creates_notebook_pipeline_and_schedule_then_updates_in_place(lakehouse, monkeypatch):
    posted = []
    monkeypatch.setattr(requests, "post", lambda url, **k: posted.append(url) or Resp(500))
    out = json.loads(server.create_drift_monitor("Sales", "shop_lh", name="shop_monitor", schema="shop"))
    assert out["dry_run"] is True and posted == [] and [r["step"] for r in out["rest"]] == ["notebook", "pipeline", "schedule"]
    items = {"value": []}
    schedules = {"value": []}
    calls = []

    def get(url, **k):
        if url.endswith("/jobs/execute/schedules"):
            return Resp(200, schedules)
        return Resp(200, items)

    def post(url, **k):
        calls.append((url, k.get("json")))
        if url.endswith("/notebooks"):
            return Resp(201, {"id": "nb-1"})
        if url.endswith("/dataPipelines"):
            return Resp(201, {"id": "pl-1"})
        if url.endswith("/jobs/execute/schedules"):
            return Resp(201, {"id": "sch-1"})
        return Resp(200, None)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", post)
    out = json.loads(server.create_drift_monitor("Sales", "shop_lh", name="shop_monitor", schema="shop", dry_run=False))
    assert out["result"]["status"] == "Succeeded" and "error" not in out
    assert out["result"]["notebook"]["mode"] == "created" and out["result"]["pipeline"]["id"] == "pl-1"
    assert out["result"]["schedule"] == {"status": "Succeeded", "mode": "created", "id": "sch-1"}
    pipeline_body = next(b for u, b in calls if u.endswith("/dataPipelines"))
    content = json.loads(base64.b64decode(pipeline_body["definition"]["parts"][0]["payload"]))
    assert content["properties"]["activities"][0]["typeProperties"]["notebookId"] == "nb-1"     # the pipeline runs the notebook just made
    assert next(b for u, b in calls if u.endswith("/schedules"))["configuration"]["type"] == "Daily"
    # again: both items exist and the schedule is there -> updated in place, schedule kept, nothing deleted
    items["value"] = [{"id": "nb-1", "displayName": "shop_monitor", "type": "Notebook"}, {"id": "pl-1", "displayName": "shop_monitor_nightly", "type": "DataPipeline"}]
    schedules["value"] = [{"id": "sch-1", "configuration": {"type": "Daily", "times": ["02:00"]}}]
    calls.clear()
    out = json.loads(server.create_drift_monitor("Sales", "shop_lh", name="shop_monitor", schema="shop", dry_run=False))
    assert out["result"]["notebook"]["mode"] == "updated" and out["result"]["pipeline"]["mode"] == "updated"
    assert out["result"]["schedule"]["mode"] == "kept"
    assert [u.rsplit("/", 2)[-2:] for u, _ in calls] == [["nb-1", "updateDefinition"], ["pl-1", "updateDefinition"]]


def test_create_drift_monitor_names_the_scope_of_the_step_that_was_refused(lakehouse, monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, **k: Resp(200, {"value": []}))

    def post(url, **k):
        if url.endswith("/notebooks"):
            return Resp(201, {"id": "nb-1"})
        return Resp(403, {"errorCode": "InsufficientScopes", "message": "missing scope"})
    monkeypatch.setattr(requests, "post", post)
    out = json.loads(server.create_drift_monitor("Sales", "shop_lh", name="m", schema="shop", dry_run=False))
    assert out["kind"] == "consent" and "DataPipeline.ReadWrite.All" in out["hint"] and out["result"]["notebook"]["status"] == "Succeeded"

    def post2(url, **k):
        if url.endswith("/notebooks"):
            return Resp(201, {"id": "nb-1"})
        if url.endswith("/dataPipelines"):
            return Resp(201, {"id": "pl-1"})
        return Resp(403, {"errorCode": "InsufficientScopes", "message": "missing scope"})
    monkeypatch.setattr(requests, "post", post2)
    out = json.loads(server.create_drift_monitor("Sales", "shop_lh", name="m", schema="shop", dry_run=False))
    assert out["kind"] == "consent" and "DataPipeline.Execute.All" in out["hint"] and out["result"]["pipeline"]["status"] == "Succeeded"
    assert "fabric-token" not in json.dumps(out)


def test_the_new_tools_are_annotated_for_the_directory_and_the_measurement_rig():
    """Drafts are read-only; the creating tools say so (readOnlyHint false), which is how the measurement rig in
    fabric-eval leaves them out of its read-only line-up."""
    import asyncio
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    for name in ("silver_notebook_draft", "drift_monitor_draft", "answer_query_draft"):
        a = tools[name].annotations
        assert tools[name].title and a.title == tools[name].title and a.read_only_hint is True and a.destructive_hint is False, name
    for name in ("create_silver_notebook", "create_drift_monitor"):
        a = tools[name].annotations
        assert a.read_only_hint is False and a.destructive_hint is True and a.idempotent_hint is True, name
        assert tools[name].input_schema["properties"]["dry_run"]["default"] is True
    assert "webhook_url" not in tools["create_drift_monitor"].input_schema["properties"]     # no secret through a tool
    q = tools["query_graphql"].input_schema
    assert {"question", "tables", "source"} <= set(q["properties"]) and "query" not in q.get("required", [])


def test_paid_plan_check_covers_the_monitor_and_the_notebook_only_when_switched_on(lakehouse, monkeypatch):
    monkeypatch.setattr(server, "_identity", lambda ctx: {"oid": "u", "tid": "tenant-1"})
    monkeypatch.delenv("KRUSGRAPH_ENTITLEMENTS", raising=False)
    assert "notebook" in json.loads(server.drift_monitor_draft("Sales", "shop_lh", schema="shop"))
    monkeypatch.setenv("KRUSGRAPH_ENTITLEMENTS", "1")
    monkeypatch.setenv("KRUSGRAPH_ENTITLED_TENANTS", "{}")
    assert json.loads(server.drift_monitor_draft("Sales", "shop_lh", schema="shop"))["kind"] == "upgrade"
    assert json.loads(server.create_drift_monitor("Sales", "shop_lh", name="m", schema="shop"))["dry_run"] is True       # dry run free
    assert json.loads(server.create_drift_monitor("Sales", "shop_lh", name="m", schema="shop", dry_run=False))["kind"] == "upgrade"
    assert json.loads(server.create_silver_notebook("Sales", "shop_lh", name="s", schema="shop", dry_run=False))["kind"] == "upgrade"
    assert "notebook" in json.loads(server.silver_notebook_draft("Sales", "shop_lh", schema="shop"))
    assert "tsql" in json.loads(server.answer_query_draft("Sales", "shop_lh", "How many orders?", ["orders"], schema="shop"))
    monkeypatch.setenv("KRUSGRAPH_ENTITLED_TENANTS", json.dumps({"tenant-1": ["drift_monitor"]}))
    assert "notebook" in json.loads(server.drift_monitor_draft("Sales", "shop_lh", schema="shop"))
