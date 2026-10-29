"""n39: usage that survives a restart. Page views and /check's two events as console lines, the Log Analytics step in the
deploy script (rerunnable, never switched off), and the report script, formatted from made-up answers (no Azure)."""
import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from deploy import azure_containerapp as d
from deploy import usage_report as ur
from fabric_backend import pages, usage

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {"subscription_id": "sub", "tenant_id": "t", "resource_group": "rg-test", "environment": "cae-test", "app": "krusgraph",
          "location": "swedencentral", "log_retention_days": 30, "log_analytics_workspace": "law-test"}


def lines(buf):
    return [json.loads(x) for x in buf.getvalue().splitlines() if x.startswith("{")]


# ------------------------------------------------------------------ the lines ------------------------------------

def test_page_views_only_for_the_five_pages_and_check_only_two_steps(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(usage.sys, "stdout", buf)
    for p in ("/", "/check", "/explore", "/start", "/partners", "/docs", "/check?x=customers.csv"):
        usage.page_view(p)
    for s in ("loaded", "done", "orders.csv", ""):
        usage.check_event(s)
    got = lines(buf)
    assert got[:5] == [{"event": "krusgraph.page_view", "path": p} for p in ("/", "/check", "/explore", "/start", "/partners")]
    assert got[5:] == [{"event": "krusgraph.check", "step": "loaded"}, {"event": "krusgraph.check", "step": "done"}]
    monkeypatch.setenv("KRUSGRAPH_USAGE_LOG", "0")
    usage.page_view("/")
    assert len(lines(buf)) == 7


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    from fabric_backend.server import build_app
    with TestClient(build_app()) as c:
        yield c


def test_the_server_writes_page_views_and_check_events(client, monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(usage.sys, "stdout", buf)
    assert client.get("/").status_code == 200 and client.get("/docs").status_code == 200
    assert client.get("/check/event?e=done").status_code == 204
    assert client.get("/check/event?e=sales.xlsx").status_code == 204
    assert lines(buf) == [{"event": "krusgraph.page_view", "path": "/"}, {"event": "krusgraph.check", "step": "done"}]
    # the page may fetch nothing; the event is an image from this host, which its policy already allows
    csp = client.get("/check").headers["content-security-policy"]
    assert "connect-src 'none'" in csp and "img-src 'self'" in csp
    js = (ROOT / "fabric_backend/static/check.js").read_text()
    assert js.count('ping("') == 2 and '"/check/event?e=" + step' in js


def test_privacy_names_the_page_views_and_how_long(monkeypatch):
    md = pages.privacy_md()
    assert "page-view record" in md and "`loaded`" in md and "deleted after" not in md
    monkeypatch.setenv("KRUSGRAPH_LOG_RETENTION_DAYS", "30")
    md = pages.privacy_md()
    assert "these lines are deleted after 30 days" in md and "{{" not in md


# ------------------------------------------------------------------ the deploy step -------------------------------

class FakeAzure:
    def __init__(self, workspace=None, destination="none", customer=None):
        self.calls, self.secret = [], "entra-secret"
        self.workspace = workspace
        self.logs = {"destination": destination, "logAnalyticsConfiguration": {"customerId": customer} if customer else None}

    def run(self, *args, **kwargs):
        self.calls.append(args)
        if args[:4] == ("monitor", "log-analytics", "workspace", "show"):
            return self.workspace
        if args[:4] == ("monitor", "log-analytics", "workspace", "create"):
            self.workspace = {"customerId": "cust-1", "tags": dict(d.OWNER_TAG),
                              "retentionInDays": int(args[args.index("--retention-time") + 1])}
            return self.workspace
        if args[:4] == ("monitor", "log-analytics", "workspace", "update"):
            self.workspace["retentionInDays"] = int(args[args.index("--retention-time") + 1])
            return self.workspace
        if args[:4] == ("monitor", "log-analytics", "workspace", "get-shared-keys"):
            return {"primarySharedKey": "law-key"}
        if args[:3] == ("containerapp", "env", "show"):
            return {"properties": {"appLogsConfiguration": self.logs}}
        if args[:3] == ("containerapp", "env", "update"):
            assert self.secret == "law-key"                       # hidden in error messages while it is used
            self.logs = {"destination": args[args.index("--logs-destination") + 1],
                         "logAnalyticsConfiguration": {"customerId": args[args.index("--logs-workspace-id") + 1]}}
            return None
        raise AssertionError(args)


def test_log_analytics_is_created_connected_and_a_rerun_changes_nothing():
    az = FakeAzure()
    assert d.connect_log_analytics(az, CONFIG) == "cust-1"
    create = next(c for c in az.calls if c[3] == "create")
    assert create[create.index("--retention-time") + 1] == "30" and "managed-by=krusgraph-deploy" in create
    update = next(c for c in az.calls if c[:3] == ("containerapp", "env", "update"))
    assert update[update.index("--logs-destination") + 1] == "log-analytics" and update[update.index("--logs-workspace-id") + 1] == "cust-1"
    assert az.secret == "entra-secret"                            # the deploy's own secret is put back
    az.calls.clear()
    d.connect_log_analytics(az, CONFIG)
    assert not any(c[:3] == ("containerapp", "env", "update") or "create" in c for c in az.calls)


def test_retention_follows_the_config_and_other_workspaces_are_refused():
    az = FakeAzure(workspace={"customerId": "cust-1", "tags": dict(d.OWNER_TAG), "retentionInDays": 90},
                   destination="log-analytics", customer="cust-1")
    d.connect_log_analytics(az, CONFIG)
    assert az.workspace["retentionInDays"] == 30 and not any(c[:3] == ("containerapp", "env", "update") for c in az.calls)
    with pytest.raises(d.DeploymentError):
        d.connect_log_analytics(FakeAzure(workspace={"customerId": "x", "tags": {"managed-by": "someone-else"}}), CONFIG)


def test_off_without_the_key_and_never_switched_off():
    az = FakeAzure()
    assert d.connect_log_analytics(az, {k: v for k, v in CONFIG.items() if k != "log_analytics_workspace"}) is None
    assert d.connect_log_analytics(az, CONFIG | {"log_analytics_workspace": ""}) is None and az.calls == []
    with pytest.raises(d.DeploymentError, match="log_retention_days"):
        d.connect_log_analytics(az, CONFIG | {"log_retention_days": 0})
    source = (ROOT / "deploy/azure_containerapp.py").read_text()
    assert source.count('"--logs-destination", "none"') == 1      # only when a new environment is created
    example = json.loads((ROOT / "deploy/krusgraph.example.json").read_text())
    assert example["log_analytics_workspace"] == ""


def test_update_connects_after_the_app_is_updated(monkeypatch):
    order = []
    monkeypatch.setattr(d, "build_image", lambda *a: "img")
    monkeypatch.setattr(d, "report", lambda *a, **k: order.append("report"))
    monkeypatch.setattr(d, "source_tag", lambda: "tag")
    monkeypatch.setattr(d, "connect_log_analytics", lambda az, config: order.append("logs"))

    class Az:
        def run(self, *args, **kwargs):
            if args[:2] == ("containerapp", "update"):
                order.append("app")
            if args[:2] in (("containerapp", "show"), ("acr", "show")):
                return {"tags": dict(d.OWNER_TAG), "loginServer": "reg"}
    d.update(Az(), CONFIG | {"client_id": "c", "domain": "x.test", "product_name": "K", "contact_email": "a@x.test", "registry": "reg"})
    assert order == ["app", "logs", "report"]


# ------------------------------------------------------------------ the report -----------------------------------

FAKE = {
    "totals": [{"calls": "200", "p50_ms": 840.0, "p95_ms": 5120.0, "orgs": 3, "consent": 10, "no_access": 4, "rate_limited": 0}],
    "calls_per_day": [{"day": "2026-11-01T00:00:00Z", "calls": 120, "errors": 9}, {"day": "2026-11-02T00:00:00Z", "calls": 80, "errors": 5}],
    "per_tool": [{"tool": "plan_backend", "calls": 120, "errors": 4, "p50_ms": 900, "p95_ms": 4000}],
    "errors_by_kind": [{"error_kind": "consent", "calls": 10}, {"error_kind": "no_access", "calls": 4}],
    "page_views": [{"path": "/", "views": 50}, {"path": "/check", "views": 12}],
    "check": [{"step": "loaded", "events": 9}, {"step": "done", "events": 6}],
}


def test_the_summary_from_made_up_answers():
    text = ur.summary(7, FAKE)
    assert "Senaste 7 dagarna" in text and "Anrop: 200, median 840 ms, 95:e percentilen 5120 ms" in text
    assert "Organisationer (saltade hashar): 3" in text and "consent: 10 (5.0 %)" in text and "no_access: 4 (2.0 %)" in text
    assert "2026-11-01 120, 2026-11-02 80" in text and "plan_backend" in text and "consent 10, no_access 4" in text
    assert "Sidvisningar: / 50, /check 12, /explore 0, /start 0, /partners 0" in text
    assert "/check: motorn laddad 9, kontroll klar 6" in text
    empty = ur.summary(30, {})
    assert "Anrop: 0" in empty and "/check: motorn laddad 0, kontroll klar 0" in empty


def test_the_report_runs_each_query_for_7_and_30_days():
    seen = []

    def runner(command, **kwargs):
        if "--analytics-query" not in command:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        text = command[command.index("--analytics-query") + 1]
        seen.append((command[command.index("--timespan") + 1], text))
        name = next(n for n in ur.QUERIES if ur.kql(n, 7 if "ago(7d)" in text else 30, "krusgraph") == text)
        return SimpleNamespace(returncode=0, stdout=json.dumps(FAKE.get(name, [])), stderr="")
    out = ur.report("cust-1", "krusgraph", runner)
    assert "Senaste 7 dagarna" in out and "Senaste 30 dagarna" in out
    assert len(seen) == 2 * len(ur.QUERIES) and {s[0] for s in seen} == {"P7D", "P30D"}
    assert all('ContainerAppName_s == "krusgraph"' in s[1] and "{" not in s[1].replace('{\\"event', "") for s in seen)


def test_usage_md_has_every_query_of_the_script():
    doc = (ROOT / "docs/USAGE.md").read_text(encoding="utf-8")
    for name in ur.QUERIES:
        assert ur.kql(name, 30, "krusgraph") in doc, name
    for word in ("consent", "no_access", "rate_limited", "percentile(toint(e.ms), 95)", "dcountif", "/partners", "krusgraph.check"):
        assert word in doc


# n42: kind and views (then step) gave SYN0002 against the real workspace on 29 October 2026; reserved words in KQL.
RESERVED = ("kind", "views", "step", "count", "type", "range", "project", "where", "order", "by")


def _unquoted_names(text: str) -> list:
    import re
    bad = []
    for line in text.splitlines():
        if line.startswith("| summarize"):
            bad += [m for m in re.findall(r'(?:^|,|\bby)\s*([A-Za-z_]\w*)\s*=(?!=)', line[len("| summarize"):])]
        if line.startswith("| order by"):
            bad += [c.split()[0] for c in line[len("| order by"):].split(",") if not c.strip().startswith('["')]
    return bad


def _all_query_texts():
    yield from ((n, ur.kql(n, 30, "krusgraph")) for n in ur.QUERIES)
    import re
    for doc in ("docs/USAGE.md", "docs/OPERATIONS.md"):
        for block in re.findall(r"```kusto\n(.*?)```", (ROOT / doc).read_text(encoding="utf-8"), re.S):
            yield doc, "\n".join(line.strip() for line in block.splitlines())


def test_every_alias_and_order_column_is_quoted():
    for name, text in _all_query_texts():
        assert _unquoted_names(text) == [], name
        for word in RESERVED:
            for line in text.splitlines():
                if line.startswith(("| summarize", "| order by")):
                    assert f" {word} =" not in line and f",{word} =" not in line and f"by {word}" not in line, (name, word)


def test_the_quoting_check_catches_the_failing_queries():
    assert _unquoted_names("| summarize calls = count() by kind = tostring(e.outcome)") == ["calls", "kind"]
    assert _unquoted_names("| order by views desc") == ["views"]
    assert _unquoted_names('| summarize ["events"] = count() by ["step"] = tostring(e.step)') == []


def test_the_extension_is_added_without_a_question_and_az_has_a_timeout():
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="[]", stderr="")
    ur.report("cust-1", "krusgraph", runner)
    assert calls[0][0][:5] == ["az", "extension", "add", "--name", "log-analytics"] and "--yes" in calls[0][0]
    assert all(kw.get("timeout") for _, kw in calls)

    def slow(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])
    try:
        ur.report("cust-1", "krusgraph", slow)
    except RuntimeError as exc:
        assert "svarade inte" in str(exc)
    else:
        raise AssertionError("no timeout error")
