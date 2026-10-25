"""Every failure a tool can hit comes back as one JSON answer a user can act on: `error`, `kind`, `hint`.
Nothing else: no tokens, no headers, no traceback. Fabric, Entra and the SQL endpoint are mocked."""
import json
import socket

import pytest
import requests

from fabric_backend import errors, server
from fabric_backend.entra import TokenError


@pytest.fixture(autouse=True)
def _workspace_ids_pass_through(monkeypatch):
    """These tests mock Fabric per route; a workspace given as a plain string is used as the id."""
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: workspace)


FAKE_TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJhdWQiOiJmYWtlIn0.c2lnbmF0dXJlLXNpZ25hdHVyZQ"
SECRET_HEADERS = {"Authorization": f"Bearer {FAKE_TOKEN}", "X-Fabric-SQL-Token": "sqltoken-should-never-show"}


def http_error(status, body="", url="https://api.fabric.microsoft.com/v1/workspaces/ws-1/items"):
    """A requests.HTTPError exactly as raise_for_status() builds it, with the secret headers on the request."""
    resp = requests.Response()
    resp.status_code = status
    resp._content = body.encode("utf-8")
    resp.url = url
    resp.request = requests.Request("GET", url, headers=SECRET_HEADERS).prepare()
    return requests.HTTPError(f"{status} Client Error for url: {url}", response=resp)


def call(monkeypatch, tool, exc, **kwargs):
    """Run a tool whose first Fabric call raises `exc`; return the parsed answer and the raw text."""
    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(server, "_headers", lambda ctx: dict(SECRET_HEADERS))
    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(requests, "post", boom)
    monkeypatch.setattr(server, "_plan", boom)
    text = getattr(server, tool)(**kwargs)
    return json.loads(text), text


def assert_clean(text):
    for leak in (FAKE_TOKEN, "sqltoken-should-never-show", "Authorization", "Traceback", "File \"", "X-Fabric-SQL-Token"):
        assert leak not in text, leak


def assert_answer(answer, kind):
    assert set(answer) >= {"error", "kind", "hint"} and answer["kind"] == kind
    assert answer["error"] and answer["hint"] and "Error executing tool" not in answer["error"]


@pytest.mark.parametrize("tool,kwargs", [
    ("list_sources", {"workspace": "ws-1"}),
    ("list_tables", {"workspace": "ws-1", "source": "shop"}),
    ("plan_backend", {"workspace": "ws-1", "source": "shop"}),
    ("create_backend", {"workspace": "ws-1", "source": "shop", "name": "shop_api"}),
    ("rayfin_connector", {"workspace": "ws-1", "source": "shop"}),
    ("query_graphql", {"workspace": "ws-1", "api": "shop_api", "query": "{ customers { items { name } } }"}),
])
def test_unknown_workspace_or_no_access_is_said_in_words_by_every_tool(monkeypatch, tool, kwargs):
    answer, text = call(monkeypatch, tool, http_error(404, '{"errorCode":"WorkspaceNotFound","message":"Workspace ws-1 not found"}'), **kwargs)
    assert_answer(answer, "not_found"); assert_clean(text)
    assert "ws-1" in answer["error"] and "list_sources" in answer["hint"]
    answer, text = call(monkeypatch, tool, http_error(403, '{"errorCode":"InsufficientPrivileges","message":"The caller does not have the required permissions"}'), **kwargs)
    assert_answer(answer, "no_access"); assert_clean(text)
    assert "no access" in answer["error"] and "Viewer" in answer["hint"]


@pytest.mark.parametrize("body", [
    '{"errorCode":"WorkspaceNotOnCapacity","message":"The workspace is not assigned to a capacity"}',
    '{"errorCode":"CapacityNotActive","message":"The capacity is paused"}',
    '{"error":{"code":"PowerBINotAuthorizedException","message":"Capacity is inactive or unavailable"}}',
])
def test_missing_or_paused_capacity(monkeypatch, body):
    answer, text = call(monkeypatch, "list_sources", http_error(403, body), workspace="ws-1")
    assert_answer(answer, "capacity"); assert_clean(text)
    assert "capacity" in answer["error"].lower() and "trial" in answer["hint"]


def test_fabric_401_and_missing_sign_in(monkeypatch):
    answer, text = call(monkeypatch, "list_sources", http_error(401, "Unauthorized"), workspace="ws-1")
    assert_answer(answer, "sign_in"); assert_clean(text)
    monkeypatch.setattr(server, "_headers", lambda ctx: (_ for _ in ()).throw(PermissionError("sign-in required")))
    answer = json.loads(server.list_sources("ws-1"))
    assert_answer(answer, "sign_in") and "Reconnect" in answer["hint"]


@pytest.mark.parametrize("message,kind", [
    ("on-behalf-of failed: invalid_grant — AADSTS65001: The user or administrator has not consented to use the application", "consent"),
    ("on-behalf-of failed: interaction_required — AADSTS50076: Due to a configuration change made by your administrator, you must use multi-factor authentication", "mfa"),
    ("on-behalf-of failed: invalid_client — AADSTS7000215: Invalid client secret provided", "server_config"),
    ("on-behalf-of failed: invalid_grant — AADSTS50173: The provided grant has expired due to it being revoked", "sign_in"),
    ("invalid token: ExpiredSignatureError", "sign_in"),
])
def test_entra_codes_become_the_right_advice(monkeypatch, message, kind):
    monkeypatch.setattr(server, "_headers", lambda ctx: (_ for _ in ()).throw(TokenError(message)))
    text = server.plan_backend("ws-1", "shop")
    answer = json.loads(text)
    assert_answer(answer, kind); assert_clean(text)
    if kind == "consent":
        assert "administrator" in answer["hint"]


def test_unknown_source_and_missing_schema_and_table(monkeypatch):
    monkeypatch.setattr(server, "_headers", lambda ctx: dict(SECRET_HEADERS))
    monkeypatch.setattr(server, "_resolve_source", lambda *a: (_ for _ in ()).throw(LookupError("no lakehouse/warehouse/SQL database named or with id 'nope' in workspace ws-1")))
    answer = json.loads(server.list_tables("ws-1", "nope"))
    assert_answer(answer, "not_found") and "nope" in answer["error"]
    # the source exists but the schema has no tables
    monkeypatch.setattr(server, "_resolve_source", lambda *a: {"type": "Lakehouse", "id": "lh", "sql_host": "x.datawarehouse.fabric.microsoft.com", "sql_db": "shop"})
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: []))
    answer = json.loads(server.plan_backend("ws-1", "shop", schema="sales"))
    assert_answer(answer, "schema_not_found")
    assert "'sales'" in answer["error"] and "'shop'" in answer["error"] and "dbo" in answer["hint"]

    class ProgrammingError(Exception):
        pass
    def execute_raises(item, tok):
        def execute(sql):
            raise ProgrammingError("('42S02', \"[42S02] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]Invalid object name 'dbo.orders'. (208) (SQLExecDirectW)\")")
        return execute
    monkeypatch.setattr(server, "_execute_factory", execute_raises)
    text = server.list_tables("ws-1", "shop")
    answer = json.loads(text)
    assert_answer(answer, "table_not_found"); assert_clean(text)
    assert "dbo.orders" in answer["error"]


def test_sql_login_failure_and_missing_driver(monkeypatch):
    monkeypatch.setattr(server, "_headers", lambda ctx: dict(SECRET_HEADERS))
    monkeypatch.setattr(server, "_resolve_source", lambda *a: {"type": "Lakehouse", "id": "lh", "sql_host": "x", "sql_db": "shop"})
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")

    class OperationalError(Exception):
        pass
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (_ for _ in ()).throw(OperationalError("('28000', '[28000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]Login failed for user. (18456)')")))
    answer = json.loads(server.list_tables("ws-1", "shop"))
    assert_answer(answer, "sql_sign_in")
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (_ for _ in ()).throw(ImportError("No module named 'pyodbc'")))
    answer = json.loads(server.list_tables("ws-1", "shop"))
    assert_answer(answer, "server_config")


@pytest.mark.parametrize("exc", [requests.exceptions.ReadTimeout("read timed out"), requests.exceptions.ConnectTimeout("connect timed out"),
                                 socket.timeout("timed out"), TimeoutError("timed out")])
def test_timeouts(monkeypatch, exc):
    answer, text = call(monkeypatch, "list_sources", exc, workspace="ws-1")
    assert_answer(answer, "timeout"); assert_clean(text)
    assert "did not answer in time" in answer["error"]


def test_sql_timeout_and_unreachable(monkeypatch):
    monkeypatch.setattr(server, "_headers", lambda ctx: dict(SECRET_HEADERS))
    monkeypatch.setattr(server, "_resolve_source", lambda *a: {"type": "Lakehouse", "id": "lh", "sql_host": "x", "sql_db": "shop"})
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")

    class OperationalError(Exception):
        pass
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (_ for _ in ()).throw(OperationalError("('HYT00', '[HYT00] [Microsoft][ODBC Driver 18 for SQL Server]Login timeout expired (0)')")))
    assert json.loads(server.list_tables("ws-1", "shop"))["kind"] == "timeout"
    answer, text = call(monkeypatch, "list_sources", requests.exceptions.ConnectionError("Max retries exceeded"), workspace="ws-1")
    assert_answer(answer, "unreachable"); assert_clean(text)


def test_throttling_and_server_errors(monkeypatch):
    assert call(monkeypatch, "list_sources", http_error(429, ""), workspace="ws-1")[0]["kind"] == "throttled"
    assert call(monkeypatch, "list_sources", http_error(503, "Service Unavailable"), workspace="ws-1")[0]["kind"] == "fabric_unavailable"


def test_fabric_messages_are_quoted_but_tokens_in_them_are_not(monkeypatch):
    body = json.dumps({"errorCode": "ItemDisplayNameNotAvailable", "message": f"Rejected token {FAKE_TOKEN} for Bearer abcdefghijklmnop; try again"})
    answer, text = call(monkeypatch, "list_sources", http_error(400, body), workspace="ws-1")
    assert_answer(answer, "fabric_error"); assert_clean(text)
    assert "[token removed]" in answer["error"] and "try again" in answer["error"]
    long = json.dumps({"errorCode": "X", "message": "y" * 2000})
    answer, _ = call(monkeypatch, "list_sources", http_error(400, long), workspace="ws-1")
    assert len(answer["error"]) < 400


def test_unexpected_exceptions_never_show_a_traceback(monkeypatch):
    answer, text = call(monkeypatch, "list_sources", ZeroDivisionError("division by zero"), workspace="ws-1")
    assert_answer(answer, "unexpected"); assert_clean(text)
    assert "ZeroDivisionError" in answer["error"] and "workspace 'ws-1'" in answer["error"]


def test_create_backend_explains_a_refused_create(monkeypatch):
    monkeypatch.setattr(server, "_plan", lambda *a: (_plan_stub(), {"type": "Lakehouse", "id": "lh"}, dict(SECRET_HEADERS)))
    monkeypatch.setattr(server, "source_for", lambda *a: ("ep-1", "SqlAnalyticsEndpoint"))
    monkeypatch.setattr(server, "deploy", lambda *a, **k: {"status": "Failed", "mode": "created", "http": 403,
                                                           "body": '{"errorCode":"WorkspaceNotOnCapacity","message":"Workspace is not on an active capacity"}'})
    text = server.create_backend("ws-1", "shop", "shop_api")
    answer = json.loads(text)
    assert answer["kind"] == "capacity" and "shop_api" not in answer["error"] or "capacity" in answer["error"].lower()
    assert "body" not in answer["result"] and answer["result"]["status"] == "Failed"
    assert_clean(text)
    monkeypatch.setattr(server, "deploy", lambda *a, **k: {"status": "Timeout", "mode": "created", "operation": "op-1"})
    answer = json.loads(server.create_backend("ws-1", "shop", "shop_api"))
    assert answer["kind"] == "timeout" and "shop_api" in answer["error"]


def _plan_stub():
    from fabric_backend.infer import plan
    from fabric_backend.seed import schema
    return plan(schema("shop"), keys={"order_items": ["order_id", "line_no"]})


def test_query_graphql_explains_http_refusals(monkeypatch):
    monkeypatch.setattr(server, "_headers", lambda ctx: dict(SECRET_HEADERS))
    monkeypatch.setattr(server, "find_item_by_name", lambda *args: {"id": "api-1", "displayName": "shop_api"})

    class Resp:
        status_code = 403
        text = '{"errorCode":"Unauthorized","message":"The user does not have Execute permission on the item"}'
        def json(self):
            return json.loads(self.text)
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp())
    text = server.query_graphql("ws-1", "shop_api", "{ customers { items { name } } }")
    answer = json.loads(text)
    assert_answer(answer, "no_access"); assert_clean(text)
    assert "shop_api" in answer["error"]


def test_tools_still_describe_themselves_to_mcp_clients():
    """The error wrapper must not hide the real signature from the MCP schema generator."""
    from starlette.testclient import TestClient
    with TestClient(server.build_app()) as client:
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                        headers={"Accept": "application/json, text/event-stream"})
        assert r.status_code == 200
        body = r.text
        payload = json.loads(body.split("data: ", 1)[1].split("\n", 1)[0]) if body.startswith("event:") or "data: " in body else r.json()
        tools = {t["name"]: t for t in payload["result"]["tools"]}
        assert set(tools) == {"list_workspaces", "list_sources", "list_tables", "plan_backend", "create_backend", "rayfin_connector", "query_graphql"}
        assert "workspace" in tools["list_sources"]["inputSchema"]["properties"]
        assert set(tools["create_backend"]["inputSchema"]["properties"]) >= {"workspace", "source", "name", "schema", "writable", "keys", "confirmed", "tables"}
        assert "ctx" not in tools["plan_backend"]["inputSchema"]["properties"]
        assert tools["plan_backend"]["annotations"]["readOnlyHint"] is True


def test_scrub_and_where():
    assert errors.scrub(f"token {FAKE_TOKEN} and Bearer abcdefghijkl end") == "token [token removed] and [token removed] end"
    assert errors.scrub("Authorization: Bearer x.y.z\nclient_secret=abc") == "Authorization: [removed] client_secret: [removed]"
    assert errors.where_from(server.list_tables.__wrapped__, ("ws", "lh"), {"schema": "sales"}) == "workspace 'ws', source 'lh', schema 'sales'"


def test_error_answers_reach_an_mcp_client_as_a_normal_result(monkeypatch):
    """Through /mcp (what Claude uses) a Fabric 404 arrives as the tool's JSON answer, not as a protocol error with
    the exception text in it; the secret headers on the failed request never reach the client."""
    from starlette.testclient import TestClient

    def boom(*a, **k):
        raise http_error(404, '{"errorCode":"WorkspaceNotFound","message":"Workspace ws-missing not found"}')
    monkeypatch.setattr(server, "_headers", lambda ctx: dict(SECRET_HEADERS))
    monkeypatch.setattr(requests, "get", boom)
    with TestClient(server.build_app()) as client:
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                                      "params": {"name": "list_sources", "arguments": {"workspace": "ws-missing"}}},
                        headers={"Accept": "application/json, text/event-stream"})
        assert r.status_code == 200
        body = r.text
        payload = json.loads(body.split("data: ", 1)[1].split("\n", 1)[0]) if "data: " in body else r.json()
        assert "error" not in payload, payload                                    # no JSON-RPC error
        result = payload["result"]
        assert not result.get("isError")
        answer = json.loads(result["content"][0]["text"])
        assert_answer(answer, "not_found"); assert_clean(body)
        assert "ws-missing" in answer["error"]


def test_server_instructions_tell_the_client_how_errors_look():
    from starlette.testclient import TestClient
    with TestClient(server.build_app()) as client:
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
                        headers={"Accept": "application/json, text/event-stream"})
        body = r.text
        payload = json.loads(body.split("data: ", 1)[1].split("\n", 1)[0]) if "data: " in body else r.json()
        text = payload["result"]["instructions"]
        assert "hint" in text and "kind" in text and "not_found" in text
