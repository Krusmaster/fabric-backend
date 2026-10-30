"""deploy/azure_containerapp.py --doctor, --budget and --backup (round n65): operations as code, against a faked `az`
(the subprocess the helper starts), a faked /healthz and a faked TLS certificate. Nothing here reaches Azure. Every
id, name and date is invented."""
import json
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from deploy import azure_containerapp as d

TENANT = "00000000-0000-4000-8000-0000000000aa"
SUB = "00000000-0000-4000-8000-000000000002"
NOW = 1793404800.0                                   # 2026-10-31 00:00:00 UTC, a fixed clock for the day counts
CONFIG = {
    "tenant_id": TENANT, "subscription_id": SUB, "client_id": "00000000-0000-4000-8000-0000000000c1",
    "domain": "krusgraph.example", "location": "swedencentral", "resource_group": "rg-krusgraph",
    "environment": "cae-krusgraph", "app": "krusgraph", "registry": "krusgraphtest", "identity": "krusgraph-pull",
    "product_name": "Krusgraph", "contact_email": "hello@krusgraph.example", "include_www": True, "min_replicas": 1,
    "log_retention_days": 30, "log_analytics_workspace": "log-krusgraph", "budget_amount": 0, "budget_email": "",
}
STORE = "https://stkrusgraphabc123.table.core.windows.net/krusgraphoauth"
READ_ONLY = {("account", "show"), ("ad", "app", "credential", "list"), ("containerapp", "show"), ("containerapp", "replica", "list"),
             ("containerapp", "env", "show"), ("consumption", "budget", "list"), ("consumption", "budget", "show"),
             ("storage", "entity", "query")}


def credential(days, hint="not-shown"):
    return {"displayName": "krusgraph", "endDateTime": d._date(NOW + days * 86400) + "T10:00:00Z", "hint": hint,
            "keyId": "k-" + str(days), "secretText": None, "startDateTime": "2026-01-01T10:00:00Z"}


def consent_entity(n):
    data = {"user": "u" * 40, "client_id": f"https://client{n}.example/metadata.json", "client_name": f"Client {n}",
            "redirect_uri": f"https://client{n}.example/callback", "at": "2026-10-27"}
    return {"PartitionKey": "consent", "RowKey": f"row{n}", "data": json.dumps(data, separators=(",", ":")), "exp": "0",
            "Timestamp": "2026-10-27T10:00:00.000000Z", "etag": "W/\"datetime'2026-10-27'\""}


class FakeCloud:
    """`az` as the subprocess the helper starts. Records every call; answers like Azure would."""

    def __init__(self, credentials=None, logs="log-analytics", budgets=None, replicas=2, store=STORE, pages=None, bound=True):
        self.credentials = [credential(400)] if credentials is None else credentials
        self.logs, self.budgets, self.replicas, self.store, self.bound = logs, budgets or [], replicas, store, bound
        self.pages = pages if pages is not None else [{"items": [consent_entity(1), consent_entity(2)], "nextMarker": {}}]
        self.calls, self.bodies = [], []

    def __call__(self, command, **kwargs):
        assert command[0] == "az"
        args = tuple(command[1:command.index("--only-show-errors")])
        self.calls.append(args)
        answer = self.answer(args)
        return SimpleNamespace(returncode=0, stdout="" if answer is None else json.dumps(answer), stderr="")

    def app(self):
        env = [{"name": "MCP_PUBLIC_URL", "value": f"https://{CONFIG['domain']}/mcp"}, {"name": "ENTRA_CLIENT_SECRET", "secretRef": "entra-secret"}]
        if self.store:
            env.append({"name": "KRUSGRAPH_REGISTRATION_STORE", "value": self.store})
        domains = [{"name": CONFIG["domain"], "bindingType": "SniEnabled" if self.bound else "Disabled"},
                   {"name": "www." + CONFIG["domain"], "bindingType": "SniEnabled"}]
        return {"name": "krusgraph", "tags": dict(d.OWNER_TAG),
                "properties": {"configuration": {"ingress": {"customDomains": domains}},
                               "template": {"containers": [{"name": "krusgraph", "env": env}], "scale": {"minReplicas": 1, "maxReplicas": 2}}}}

    def answer(self, args):
        if args[:2] == ("account", "show"):
            return {"id": SUB, "tenantId": TENANT, "state": "Enabled"}
        if args[:4] == ("ad", "app", "credential", "list"):
            return self.credentials
        if args[:2] == ("containerapp", "show"):
            return self.app()
        if args[:3] == ("containerapp", "replica", "list"):
            return [{"name": f"krusgraph--r{i}"} for i in range(self.replicas)]
        if args[:3] == ("containerapp", "env", "show"):
            return {"properties": {"appLogsConfiguration": {"destination": self.logs, "logAnalyticsConfiguration": {"customerId": "cid"}}}}
        if args[:3] == ("consumption", "budget", "list"):
            return self.budgets
        if args[:3] == ("consumption", "budget", "show"):
            name = args[args.index("--budget-name") + 1]
            found = [b for b in self.budgets if b["name"] == name]
            if not found:
                raise_not_found()
            return found[0]
        if args[:3] == ("storage", "entity", "query"):
            index = 0
            if "--marker" in args:
                index = int(args[args.index("--marker") + 2].split("=")[1].removeprefix("row")) - 1
            return self.pages[index]
        if args[0] == "rest":
            body_file = args[args.index("--body") + 1].removeprefix("@")
            self.bodies.append((args[args.index("--method") + 1], args[args.index("--url") + 1], json.loads(Path(body_file).read_text(encoding="utf-8"))))
            return None
        raise AssertionError(f"unexpected az call {args}")


class NotFound(Exception):
    pass


def raise_not_found():
    raise NotFound()


@pytest.fixture
def cloud(monkeypatch):
    def install(fake):
        def run(command, **kwargs):
            try:
                return fake(command, **kwargs)
            except NotFound:
                return SimpleNamespace(returncode=1, stdout="", stderr="(NotFound) The specified budget was not found. ResourceNotFound")
        monkeypatch.setattr(d.subprocess, "run", run)
        return fake
    return install


@pytest.fixture
def served(monkeypatch):
    """/healthz answers with this checkout's build; the domain serves a certificate valid for 60 days."""
    import ssl
    build = d.source_tag()
    monkeypatch.setattr(d, "http_response", lambda url, method="GET": (200, {}, json.dumps({"ok": True, "auth": "entra", "build": build})))
    not_after = time.strftime("%b %d %H:%M:%S %Y GMT", time.gmtime(NOW + 60 * 86400))
    assert ssl.cert_time_to_seconds(not_after) == NOW + 60 * 86400
    monkeypatch.setattr(d, "served_certificate", lambda domain: {"notAfter": not_after, "subject": ((("commonName", domain),),)})
    return build


def test_doctor_reads_only_and_reports_every_check(cloud, served, capsys):
    fake = cloud(FakeCloud(budgets=[{"name": "budget-krusgraph", "amount": 500.0, "timeGrain": "Monthly"}]))
    rows = d.doctor(d.Azure(CONFIG), CONFIG, now=NOW)
    for call in fake.calls:
        assert any(call[:len(prefix)] == prefix for prefix in READ_ONLY), call
    assert [(check, status) for check, status, _ in rows] == [
        ("Server (/healthz)", "OK"), ("Certifikat", "OK"), ("Entra-klienthemlighet", "OK"), ("Repliker", "OK"),
        ("Domänbindning", "OK"), ("Registreringslager", "OK"), ("Log Analytics", "OK"), ("Budgetlarm", "OK")]
    table = d.format_rows(rows)
    assert served in table and "2026-12-30 (60 dagar kvar)" in table and "går ut 2027-12-05" in table
    assert "log-krusgraph" in table and "budget-krusgraph (500.0 per monthly)" in table and "2 kör nu; min 1, max 2" in table
    assert "stkrusgraphabc123" in table
    assert "not-shown" not in table and "k-400" not in table            # dates only from the credential list


def test_doctor_warns_and_fails_without_stopping(cloud, served):
    cloud(FakeCloud(credentials=[credential(-3, "old"), credential(20, "soon")], logs="none", replicas=0, store="", bound=False))
    rows = {check: (status, detail) for check, status, detail in d.doctor(d.Azure(CONFIG), CONFIG, now=NOW)}
    assert rows["Entra-klienthemlighet"][0] == "VARNING" and "2026-10-28, 2026-11-20" in rows["Entra-klienthemlighet"][1]
    assert rows["Log Analytics"][0] == "VARNING" and "--log-analytics" in rows["Log Analytics"][1]
    assert rows["Budgetlarm"][0] == "VARNING" and "--budget" in rows["Budgetlarm"][1]
    assert rows["Repliker"][0] == "VARNING" and rows["Repliker"][1].startswith("0 kör nu")
    assert rows["Domänbindning"][0] == "VARNING" and "krusgraph.example" in rows["Domänbindning"][1]
    assert rows["Registreringslager"][1].startswith("inget Table Storage")
    assert "old" not in rows["Entra-klienthemlighet"][1] and "soon" not in rows["Entra-klienthemlighet"][1]
    cloud(FakeCloud(credentials=[credential(-3)]))
    rows = {check: status for check, status, _ in d.doctor(d.Azure(CONFIG), CONFIG, now=NOW)}
    assert rows["Entra-klienthemlighet"] == "FEL"


def test_doctor_keeps_going_when_the_server_is_down(cloud, served, monkeypatch):
    cloud(FakeCloud(budgets=[{"name": "budget-krusgraph", "amount": 500.0, "timeGrain": "Monthly"}]))
    monkeypatch.setattr(d, "http_response", lambda url, method="GET": (503, {}, ""))
    monkeypatch.setattr(d, "served_certificate", lambda domain: (_ for _ in ()).throw(OSError("connection refused")))
    rows = d.doctor(d.Azure(CONFIG), CONFIG, now=NOW)
    assert [status for _, status, _ in rows[:2]] == ["FEL", "FEL"] and "HTTP 503" in rows[0][2] and "connection refused" in rows[1][2]
    assert len(rows) == 8 and all(status == "OK" for _, status, _ in rows[2:])


def test_doctor_marks_an_older_build(cloud, served, monkeypatch):
    cloud(FakeCloud())
    monkeypatch.setattr(d, "http_response", lambda url, method="GET": (200, {}, json.dumps({"ok": True, "auth": "entra", "build": "src-older"})))
    rows = d.doctor(d.Azure(CONFIG), CONFIG, now=NOW)
    assert rows[0][1] == "VARNING" and "src-older" in rows[0][2] and "--update" in rows[0][2]


def test_doctor_cli_exits_1_on_fel(cloud, served, tmp_path, monkeypatch, capsys):
    cloud(FakeCloud(credentials=[]))
    config = tmp_path / "krusgraph.json"
    config.write_text(json.dumps(CONFIG), encoding="utf-8")
    monkeypatch.setattr(d.sys, "argv", ["azure_containerapp.py", "--doctor", "--config", str(config)])
    with pytest.raises(SystemExit) as stop:
        d.main()
    out, err = capsys.readouterr()
    assert stop.value.code == 1 and "Kontroll" in out and "ingen klienthemlighet" in out and "Minst en kontroll gav FEL" in err


def test_budget_does_nothing_without_both_keys(cloud, capsys):
    for extra in ({}, {"budget_amount": 500}, {"budget_email": "ops@krusgraph.example"}, {"budget_amount": "", "budget_email": ""}):
        fake = cloud(FakeCloud())
        assert d.create_budget(d.Azure(CONFIG | extra), CONFIG | extra) is False
        assert fake.calls == [] and fake.bodies == []
        assert "Inget budgetlarm skapas" in capsys.readouterr().out


def test_budget_creates_once_with_email_and_amount(cloud, capsys):
    config = CONFIG | {"budget_amount": 500, "budget_email": "ops@krusgraph.example"}
    fake = cloud(FakeCloud())
    assert d.create_budget(d.Azure(config), config, today=date(2026, 10, 30)) is True
    assert [c[:3] for c in fake.calls] == [("consumption", "budget", "show"), ("rest", "--method", "put")]
    method, url, body = fake.bodies[0]
    assert url == (f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/rg-krusgraph/providers/Microsoft.Consumption"
                   "/budgets/budget-krusgraph?api-version=2023-05-01")
    props = body["properties"]
    assert props["category"] == "Cost" and props["amount"] == 500.0 and props["timeGrain"] == "Monthly"
    assert props["timePeriod"] == {"startDate": "2026-10-01T00:00:00Z", "endDate": "2031-10-01T00:00:00Z"}
    assert {k: (n["threshold"], n["thresholdType"], n["contactEmails"]) for k, n in props["notifications"].items()} == {
        "actual-80": (80, "Actual", ["ops@krusgraph.example"]), "actual-100": (100, "Actual", ["ops@krusgraph.example"])}
    assert "budget-krusgraph" in capsys.readouterr().out
    # rerun: the same budget exists, nothing is sent
    existing = {"name": "budget-krusgraph", "amount": 500.0, "timeGrain": "Monthly",
                "notifications": {k: {"enabled": True, "contactEmails": ["ops@krusgraph.example"]} for k in ("actual-80", "actual-100")}}
    fake = cloud(FakeCloud(budgets=[existing]))
    assert d.create_budget(d.Azure(config), config) is True
    assert [c[:3] for c in fake.calls] == [("consumption", "budget", "show")] and fake.bodies == []
    assert "finns redan" in capsys.readouterr().out
    # a different amount: replaced under the same name
    config = config | {"budget_amount": 800}
    fake = cloud(FakeCloud(budgets=[existing]))
    d.create_budget(d.Azure(config), config)
    assert len(fake.bodies) == 1 and fake.bodies[0][2]["properties"]["amount"] == 800.0


@pytest.mark.parametrize("bad", [{"budget_amount": "much"}, {"budget_amount": -5}, {"budget_email": "no-at-sign"}])
def test_budget_refuses_bad_settings(cloud, bad):
    config = CONFIG | {"budget_amount": 500, "budget_email": "ops@krusgraph.example"} | bad
    fake = cloud(FakeCloud())
    with pytest.raises(d.DeploymentError):
        d.create_budget(d.Azure(config), config)
    assert fake.calls == []


def test_backup_exports_consent_records_only_and_pages(cloud, tmp_path, capsys):
    pages = [{"items": [consent_entity(1), {"PartitionKey": "family", "RowKey": "f1", "data": "{\"rt\":\"ciphertext\"}", "exp": "1"}],
              "nextMarker": {"nextpartitionkey": "consent", "nextrowkey": "row2"}},
             {"items": [consent_entity(2), consent_entity(3)], "nextMarker": {}}]
    fake = cloud(FakeCloud(pages=pages))
    out = tmp_path / "backup.json"
    assert d.backup_registration(d.Azure(CONFIG), CONFIG, out, now=NOW) == 3
    queries = [c for c in fake.calls if c[:3] == ("storage", "entity", "query")]
    assert len(queries) == 2 and all("--auth-mode" in q and "login" in q for q in queries)
    assert all(q[q.index("--filter") + 1] == "PartitionKey eq 'consent'" for q in queries)
    assert queries[0].count("--marker") == 0 and queries[1][queries[1].index("--marker") + 1:][:2] == ("nextpartitionkey=consent", "nextrowkey=row2")
    assert "stkrusgraphabc123" in queries[0] and "krusgraphoauth" in queries[0]
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["count"] == 3 and document["kind"] == "consent" and document["exported"] == "2026-10-31"
    assert [e["RowKey"] for e in document["entities"]] == ["row1", "row2", "row3"]
    assert all(set(e) == {"PartitionKey", "RowKey", "data", "exp"} for e in document["entities"])
    text = out.read_text(encoding="utf-8")
    assert "ciphertext" not in text and "family" not in text and "Timestamp" not in text
    assert "3 consent-poster" in capsys.readouterr().out


def test_backup_stops_without_table_storage(cloud, tmp_path):
    for store in ("", "memory"):
        cloud(FakeCloud(store=store))
        with pytest.raises(d.DeploymentError, match="inget Table Storage"):
            d.backup_registration(d.Azure(CONFIG), CONFIG, tmp_path / "x.json")
        assert not (tmp_path / "x.json").exists()


def test_backup_files_are_git_ignored_and_the_example_has_the_budget_keys():
    assert "deploy/registration-backup-*.json" in (d.ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    example = json.loads((d.ROOT / "deploy/krusgraph.example.json").read_text(encoding="utf-8"))
    assert example["budget_amount"] == 0 and example["budget_email"] == ""
    assert d.budget_settings(example) is None


def test_cli_out_belongs_to_backup(monkeypatch, tmp_path):
    config = tmp_path / "krusgraph.json"
    config.write_text(json.dumps(CONFIG), encoding="utf-8")
    monkeypatch.setattr(d.sys, "argv", ["azure_containerapp.py", "--doctor", "--out", "x.json", "--config", str(config)])
    with pytest.raises(SystemExit) as stop:
        d.main()
    assert stop.value.code == 2


def test_doctor_through_the_shell_wrapper_with_a_fake_az(tmp_path, monkeypatch, served):
    """`bash deploy/krusgraph.sh --doctor` end to end: a fake `az` on PATH (a script that answers JSON), the real
    wrapper, the real argument parsing. The network calls are stubbed inside the helper via a sitecustomize hook."""
    import os
    import subprocess
    import sys
    import textwrap
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    az = fake_bin / "az"
    az.write_text(textwrap.dedent(f'''\
        #!{sys.executable}
        import json, sys
        a = sys.argv[1:]
        def out(x): print(json.dumps(x))
        if a[:2] == ["account", "show"]: out({{"id": "{SUB}", "tenantId": "{TENANT}", "state": "Enabled"}})
        elif a[:4] == ["ad", "app", "credential", "list"]: out([{{"endDateTime": "2027-10-30T00:00:00Z", "hint": "zzz"}}])
        elif a[:2] == ["containerapp", "show"]: out({{"properties": {{"configuration": {{"ingress": {{"customDomains": [
            {{"name": "krusgraph.example", "bindingType": "SniEnabled"}}, {{"name": "www.krusgraph.example", "bindingType": "SniEnabled"}}]}}}},
            "template": {{"containers": [{{"name": "krusgraph", "env": []}}], "scale": {{"minReplicas": 1, "maxReplicas": 2}}}}}}}})
        elif a[:3] == ["containerapp", "replica", "list"]: out([{{"name": "r1"}}])
        elif a[:3] == ["containerapp", "env", "show"]: out({{"properties": {{"appLogsConfiguration": {{"destination": "log-analytics"}}}}}})
        elif a[:3] == ["consumption", "budget", "list"]: out([])
        else: sys.exit("unexpected: " + " ".join(a))
        '''), encoding="utf-8")
    az.chmod(0o755)
    site = tmp_path / "site"
    site.mkdir()
    (site / "sitecustomize.py").write_text(textwrap.dedent('''\
        # The helper runs as __main__, so the network is stubbed below it: urlopen for /healthz, the TLS handshake
        # for the certificate. `az` is the fake script on PATH.
        import io, json, socket, ssl, time
        from deploy import azure_containerapp as d
        class Response(io.BytesIO):
            status, headers = 200, {}
        urllib_request = __import__("urllib.request").request
        urllib_request.urlopen = lambda request, timeout=30: Response(json.dumps({"ok": True, "auth": "entra", "build": d.source_tag()}).encode())
        class Tls:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def getpeercert(self): return {"notAfter": time.strftime("%b %d %H:%M:%S %Y GMT", time.gmtime(time.time() + 50 * 86400))}
        class Context:
            def wrap_socket(self, sock, server_hostname=None): return Tls()
        socket.create_connection = lambda *a, **k: Tls()
        ssl.create_default_context = lambda: Context()
        '''), encoding="utf-8")
    config = tmp_path / "krusgraph.json"
    config.write_text(json.dumps(CONFIG), encoding="utf-8")
    env = os.environ | {"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}", "PYTHONPATH": f"{site}{os.pathsep}{d.ROOT}"}
    result = subprocess.run(["bash", "deploy/krusgraph.sh", "--doctor", "--config", str(config)], cwd=d.ROOT, env=env,
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Kontroll" in result.stdout and "Budgetlarm" in result.stdout and "VARNING" in result.stdout
    assert "2027-10-30" in result.stdout and "zzz" not in result.stdout and "1 kör nu; min 1, max 2" in result.stdout
