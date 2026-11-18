"""UM1: anonymous daily usage counts (usage_metrics.py) and the operator's /metrics page. Throw-away tokens and fake
storage; nothing here calls Azure, Entra or Fabric."""
import json
import os
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import server, usage, usage_metrics as um

TID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OID = "11111111-0000-0000-0000-000000000001"
TOKEN = "t" * 64
DAY = 86400
T0 = 1_795_000_000          # a fixed instant in November 2026


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def fresh(monkeypatch):
    """A Counts of its own, with an in-memory 'table' that behaves like the durable one."""
    monkeypatch.setenv("KRUSGRAPH_USAGE_SALT", "salt-" + "x" * 30)
    monkeypatch.setenv("KRUSGRAPH_USAGE_LOG", "0")
    monkeypatch.delenv("KRUSGRAPH_METRICS", raising=False)
    rows, clock = um.MemoryRows(), Clock()
    c = um.Counts(rows, durable=True, clock=clock)
    monkeypatch.setattr(um, "counts", c)
    monkeypatch.setattr(usage, "usage", usage.Usage())
    return c, rows, clock


def everything_stored(rows) -> str:
    return json.dumps(rows.data)


# ------------------------------------------------------------------ hashes, never ids -------

def test_no_raw_ids_are_stored_only_salted_hashes(fresh):
    c, rows, _ = fresh
    c.tool_call("plan_backend", "ok", TID, OID)
    c.tool_call("plan_backend", "not_found", TID.upper(), OID)          # the same tenant, other case: one organisation
    c.flush()
    text = everything_stored(rows)
    assert TID not in text and TID.upper() not in text and OID not in text
    day = next(iter(rows.data.values()))
    assert len(day["orgs"]) == 1 and len(day["users"]) == 1
    assert all(re.fullmatch(r"[0-9a-f]{16}", h) for h in day["orgs"] + day["users"])
    org, user = um.hashes(TID, OID)
    assert day["orgs"] == [org] and day["users"] == [user] and org != user


def test_without_the_salt_no_hash_is_made_and_nobody_is_counted(fresh, monkeypatch):
    c, rows, _ = fresh
    monkeypatch.delenv("KRUSGRAPH_USAGE_SALT")
    assert um.hashes(TID, OID) == (None, None)
    c.tool_call("plan_backend", "ok", TID, OID)
    c.flush()
    day = next(iter(rows.data.values()))
    assert day["orgs"] == [] and day["users"] == [] and day["tools"] == {"plan_backend": 1}
    assert um.report(c)["salt_set"] is False


def test_the_hash_depends_on_the_salt(monkeypatch):
    monkeypatch.setenv("KRUSGRAPH_USAGE_SALT", "a" * 32)
    a = um.hashes(TID, OID)
    monkeypatch.setenv("KRUSGRAPH_USAGE_SALT", "b" * 32)
    assert um.hashes(TID, OID) != a


# ------------------------------------------------------------------ what is counted ---------

def test_aggregation_across_replicas_restarts_and_days(fresh, monkeypatch):
    c, rows, clock = fresh
    c.session("claude-ai")
    c.tool_call("plan_backend", "ok", TID, "u1")
    c.tool_call("plan_backend", "consent", TID, "u2")
    c.route("review", 200)
    c.route("build", 502)
    c.flush()
    other = um.Counts(rows, durable=True, clock=clock)                     # a second replica, the same day
    other.session("Cursor")
    other.tool_call("create_views", "ok", "cccccccc-0000-0000-0000-000000000000", "u3")
    other.tool_call("plan_backend", "ok", TID, "u1")                       # the same user on the other replica
    other.flush()
    clock.t += DAY                                                         # tomorrow, on the first replica
    c.tool_call("plan_backend", "ok", TID, "u1")
    rep = um.report(c)
    w7 = rep["windows"]["7d"]
    assert w7["organisations"] == 2 and w7["users"] == 3 and w7["sessions"] == 2
    assert w7["tool_calls"] == 5 and w7["errors"] == 1 and w7["workload_calls"] == 2
    assert w7["top_tools"][0] == {"name": "plan_backend", "count": 4}
    assert w7["errors_by_tool_and_kind"] == [{"name": "plan_backend:consent", "count": 1}]
    assert {x["name"] for x in w7["clients"]} == {"claude-ai", "cursor"}
    assert w7["workload_route_errors"] == [{"name": "build", "count": 1}]
    assert [d["tool_calls"] for d in rep["days"]] == [1, 4]               # newest first
    assert rep["days"][1]["organisations"] == 2 and rep["days"][0]["users"] == 1
    for h in rows.data[next(iter(rows.data))]["orgs"]:
        assert h not in json.dumps(rep)


def test_a_restart_keeps_the_stored_counts(fresh):
    c, rows, clock = fresh
    c.tool_call("plan_backend", "ok", TID, OID)
    c.flush()
    after = um.Counts(rows, durable=True, clock=clock)                     # the replica restarted: a new id, same table
    after.tool_call("plan_backend", "ok", TID, OID)
    w = um.report(after)["windows"]["7d"]
    assert w["tool_calls"] == 2 and w["organisations"] == 1 and w["users"] == 1


def test_client_names_are_cleaned():
    assert um.client_name("claude-ai") == "claude-ai"
    assert um.client_name("Visual Studio Code") == "visual studio code"
    assert um.client_name(None) == um.NONE and um.client_name("") == um.NONE
    assert um.client_name("eve@example.com") == um.OTHER
    assert um.client_name("x" * 41) == um.OTHER
    assert um.client_name("<script>") == um.OTHER


def test_the_mcp_initialize_body_gives_only_method_and_client_name():
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"clientInfo": {"name": "cursor", "version": "1"}, "capabilities": {}}}).encode()
    assert um.mcp_initialize_client(body) == (True, "cursor")
    call = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "plan_backend",
                       "arguments": {"workspace": "initialize"}}}).encode()
    assert um.mcp_initialize_client(call) == (False, None)
    assert um.mcp_initialize_client(b"not json initialize") == (False, None)


def test_no_tool_arguments_or_answers_are_captured(fresh, monkeypatch):
    """Real tool calls through the server's wrapper: workspace, table and column names, the query and the rows never
    reach what is stored or reported."""
    from fabric_backend import seed
    from fabric_backend.schema import Schema
    c, rows, _ = fresh
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda w, h: "ws-secretive")
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, h: {"type": "Lakehouse", "id": "lh-1", "displayName": src, "sql_host": "h", "sql_db": src})
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: [{"customer_id": 1, "name": "Harbour Bikes"}]))
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    server.plan_backend("Confidential Workspace", "secret_lakehouse", schema="shop")
    server.sample_rows("Confidential Workspace", "secret_lakehouse", "customers", schema="shop")
    server.query_graphql("Confidential Workspace", "api", "mutation { deleteEverything }")
    c.flush()
    text = everything_stored(rows) + json.dumps(um.report(c)) + um.report_html(um.report(c))
    assert '"plan_backend": 1' in everything_stored(rows) and "query_graphql:read_only" in text
    for secret in ("Confidential", "secret_lakehouse", "ws-secretive", "customers", "Harbour", "deleteEverything",
                   "shop", "test-only", "sql-token"):
        assert secret not in text, secret


def test_listing_caps_hold(fresh):
    c, rows, _ = fresh
    for i in range(um.MAX_KEYS["clients"] + 20):
        c.session(f"client-{i}")
    c.flush()
    clients = next(iter(rows.data.values()))["clients"]
    assert len(clients) == um.MAX_KEYS["clients"] + 1 and clients[um.OTHER] == 20


# ------------------------------------------------------------------ retention ---------------

def test_retention_hashes_then_counts_then_nothing(fresh):
    c, rows, clock = fresh
    c.tool_call("plan_backend", "ok", TID, OID)
    c.flush()
    first = clock.t
    clock.t = first + um.HASH_DAYS * DAY                                   # past the hash window
    c.tidy()
    keys = list(rows.data)
    assert len(keys) == 1 and keys[0].endswith("_total")
    total = rows.data[keys[0]]
    assert total["orgs"] == [] and total["users"] == [] and total["orgs_n"] == 1 and total["users_n"] == 1
    assert total["tools"] == {"plan_backend": 1}
    clock.t = first + (um.KEEP_DAYS - 1) * DAY                             # still inside 400 days
    c.tidy()
    assert list(rows.data) == keys
    clock.t = first + um.KEEP_DAYS * DAY                                   # 400 days later: gone
    c.tidy()
    assert rows.data == {}


def test_retention_in_memory_without_a_table(monkeypatch):
    monkeypatch.setenv("KRUSGRAPH_USAGE_SALT", "s" * 32)
    monkeypatch.delenv("KRUSGRAPH_METRICS", raising=False)
    clock = Clock()
    c = um.Counts(um.MemoryRows(), durable=False, clock=clock)
    c.tool_call("plan_backend", "ok", TID, OID)
    clock.t += um.HASH_DAYS * DAY
    c.tool_call("plan_backend", "ok", TID, OID)
    old = c._days[um._today(T0)]
    assert old["orgs"] == [] and old["orgs_n"] == 1
    clock.t = T0 + um.KEEP_DAYS * DAY
    c.tool_call("plan_backend", "ok", TID, OID)
    assert um._today(T0) not in c._days
    rep = um.report(c)
    assert rep["durable"] is False and "since the last restart" in rep["scope"]
    assert "Since the last restart" in um.report_html(rep)


def test_without_a_table_setting_the_counts_stay_in_memory(monkeypatch):
    monkeypatch.delenv("KRUSGRAPH_REGISTRATION_STORE", raising=False)
    rows, durable = um.rows_from_env()
    assert isinstance(rows, um.MemoryRows) and durable is False
    monkeypatch.setenv("KRUSGRAPH_REGISTRATION_STORE", "memory")
    assert um.rows_from_env()[1] is False
    monkeypatch.setenv("KRUSGRAPH_REGISTRATION_STORE", "https://stx.table.core.windows.net/krusgraphoauth")
    rows, durable = um.rows_from_env()
    assert isinstance(rows, um.TableRows) and durable is True


def test_table_rows_use_their_own_partition(monkeypatch):
    calls = []

    class R:
        def __init__(self, status=204, body=None, headers=None):
            self.status_code, self._body, self.headers = status, body or {}, headers or {}

        def json(self):
            return self._body

    def http(method, url, headers=None, data=None, params=None):
        calls.append((method, url, data, params))
        if method == "GET":
            return R(200, {"value": [{"RowKey": "2026-11-18_ab", "data": json.dumps(um.empty_day())}]})
        return R()
    t = um.TableRows("https://stx.table.core.windows.net/krusgraphoauth", http=http, token=lambda: "tok")
    t.put("2026-11-18_ab", um.empty_day())
    assert "PartitionKey='usage'" in calls[0][1] and json.loads(calls[0][2])["PartitionKey"] == "usage"
    assert list(t.rows("2026-11-01")) == ["2026-11-18_ab"]
    assert "PartitionKey eq 'usage'" in calls[1][3]["$filter"]
    t.delete("2026-11-18_ab")
    assert calls[2][0] == "DELETE" and "PartitionKey='usage'" in calls[2][1]
    assert um.PARTITION not in __import__("fabric_backend.registration_store", fromlist=["KINDS"]).KINDS


def test_a_failed_write_keeps_the_counts(fresh):
    c, rows, _ = fresh

    def broken(*a, **k):
        raise RuntimeError("no table")
    c.tool_call("plan_backend", "ok", TID, OID)
    c.rows.put = broken
    c.flush()
    assert c.last_error == "RuntimeError" and c._dirty and c._days


# ------------------------------------------------------------------ kill switch -------------

def test_kill_switch_counts_and_writes_nothing(fresh, monkeypatch):
    c, rows, _ = fresh
    monkeypatch.setenv("KRUSGRAPH_METRICS", "off")
    prom_before = usage.usage.prometheus()
    c.tool_call("plan_backend", "ok", TID, OID)
    c.session("cursor")
    c.route("review", 200)
    c.identity(TID, OID)
    c.flush()
    assert c._days == {} and rows.data == {}
    wrapped = server._instrumented(lambda: '{"ok": true}', "plan_backend")
    assert wrapped() == '{"ok": true}'                                     # the call still runs
    assert "krusgraph_tool_calls_total{" not in usage.usage.prometheus() and prom_before
    assert c._days == {}
    assert um.report(c)["counting"].startswith("off")


def test_kill_switch_skips_the_asgi_counting(fresh, monkeypatch):
    c, _, _ = fresh
    monkeypatch.setenv("KRUSGRAPH_METRICS", "off")
    with TestClient(server.build_app()) as client:
        client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                  "params": {"clientInfo": {"name": "cursor"}, "protocolVersion": "2025-06-18", "capabilities": {}}},
                    headers={"Accept": "application/json, text/event-stream"})
    assert c._days == {}


def test_an_initialize_through_the_app_counts_a_session_and_its_client(fresh, monkeypatch):
    c, _, _ = fresh
    with TestClient(server.build_app()) as client:
        client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                  "params": {"clientInfo": {"name": "claude-ai"}, "protocolVersion": "2025-06-18", "capabilities": {}}},
                    headers={"Accept": "application/json, text/event-stream"})
    day = next(iter(c._days.values()))
    assert day["sessions"] == 1 and day["clients"] == {"claude-ai": 1}


def test_workload_routes_are_counted_by_name_only():
    seen = []

    class Fake:
        def route(self, name, status):
            seen.append((name, status))

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 403, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})
    from starlette.testclient import TestClient as TC
    wrapped = um.asgi(app, get_counts=lambda: Fake())
    c = TC(wrapped)
    c.post("/workload/v1/review", json={"workspace": "Secret WS"})
    c.options("/workload/v1/review")
    c.get("/workload/v1/file/abc123token")
    assert seen == [("review", 403), ("file-get", 403)]


# ------------------------------------------------------------------ the page and its token --

def test_metrics_404_when_the_token_is_unset(monkeypatch):
    monkeypatch.delenv("KRUSGRAPH_METRICS_TOKEN", raising=False)
    client = TestClient(server.build_app())
    assert client.get("/metrics").status_code == 404
    assert client.get("/metrics?format=json").status_code == 404
    assert client.get("/metrics", headers={"Accept": "text/html"}).status_code == 404
    assert client.post("/metrics", data={"token": TOKEN}).status_code == 404


def test_metrics_401_for_a_wrong_token(fresh, monkeypatch):
    monkeypatch.setenv("KRUSGRAPH_METRICS_TOKEN", TOKEN)
    client = TestClient(server.build_app())
    assert client.get("/metrics?format=json").status_code == 401
    assert client.get("/metrics?format=json", headers={"Authorization": "Bearer " + "t" * 63}).status_code == 401
    r = client.get("/metrics", headers={"Accept": "text/html"})
    assert r.status_code == 401 and 'type="password"' in r.text and 'method="post"' in r.text
    r = client.post("/metrics", data={"token": "wrong"}, headers={"Accept": "text/html"})
    assert r.status_code == 401 and "not right" in r.text and "Top tools" not in r.text


def test_metrics_with_the_right_token(fresh, monkeypatch):
    c, _, _ = fresh
    monkeypatch.setenv("KRUSGRAPH_METRICS_TOKEN", TOKEN)
    c.tool_call("plan_backend", "ok", TID, OID)
    client = TestClient(server.build_app())
    auth = {"Authorization": f"Bearer {TOKEN}"}
    r = client.get("/metrics?format=json", headers=auth)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["windows"]["7d"]["organisations"] == 1 and body["windows"]["30d"]["tool_calls"] == 1
    r = client.get("/metrics", headers={**auth, "Accept": "text/html"})
    assert r.status_code == 200 and "Last 30 days" in r.text and "Per day" in r.text and "<script" not in r.text
    assert "default-src 'none'" in r.headers["content-security-policy"] and "noindex" in r.headers["x-robots-tag"]
    assert 'name="viewport"' in r.text
    r = client.post("/metrics", data={"token": TOKEN}, headers={"Accept": "text/html"})
    assert r.status_code == 200 and "Top tools" in r.text and TOKEN not in r.text
    r = client.get("/metrics", headers=auth)                               # a scraper: Prometheus as before
    assert r.headers["content-type"].startswith("text/plain") and "krusgraph_uptime_seconds" in r.text
    for text in (json.dumps(body), client.get("/metrics", headers={**auth, "Accept": "text/html"}).text):
        assert TID not in text and OID not in text and TOKEN not in text


def test_the_page_compares_the_token_in_constant_time():
    src = Path(server.__file__).read_text()
    block = src[src.index("async def metrics(request):"):src.index('Route("/metrics", metrics')]
    assert "hmac.compare_digest" in block and "operator_refusal(request)" in block


def test_metrics_is_never_in_the_public_site():
    root = Path(server.__file__).parent
    for p in list((root / "page_templates").glob("*")) + [root / "pages.py", root / "discovery.py"]:
        if p.is_file():
            text = p.read_text(errors="replace")
            assert 'href="/metrics' not in text and "](/metrics" not in text, p.name


def test_the_usage_doc_says_what_is_and_is_not_counted():
    doc = (Path(__file__).parents[1] / "docs" / "USAGE.md").read_text()
    section = doc[doc.index("## Daily counts and /metrics"):]
    for word in ("salted hash", "KRUSGRAPH_METRICS=off", "KRUSGRAPH_METRICS_TOKEN", "400 days", "35 days",
                 "tool arguments", "IP addresses", "clientInfo.name"):
        assert word in section, word
