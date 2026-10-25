import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deploy import azure_containerapp as d


_CONFIG_FILE = next(p for p in (d.ROOT / "deploy/krusgraph.json", d.ROOT / "deploy/krusgraph.example.json") if p.exists())
CONFIG = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))      # the real file is git-ignored; CI uses the example


@pytest.mark.parametrize("change", [{"tenantId": "another-tenant"}, {"id": "another-subscription"}, {"state": "Disabled"}])
def test_wrong_account_stops_before_any_resource_change(monkeypatch, change):
    calls = []
    account = {"tenantId": CONFIG["tenant_id"], "id": CONFIG["subscription_id"], "state": "Enabled"} | change

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps(account), stderr="")

    monkeypatch.setattr(d.subprocess, "run", run)
    with pytest.raises(d.DeploymentError):
        d.Azure(CONFIG).check_context()
    assert len(calls) == 1 and calls[0][1:3] == ["account", "show"]


def test_registration_permissions_and_consent_are_both_required():
    app = {"signInAudience": "AzureADMultipleOrgs", "identifierUris": ["https://krusgraph.com/mcp"],
           "api": {"requestedAccessTokenVersion": 2, "oauth2PermissionScopes": [{"value": "user_impersonation", "isEnabled": True}]},
           "requiredResourceAccess": []}
    resources, grants = {}, []
    for resource, scopes in d.REQUIRED_SCOPES.items():
        resources[resource] = {"id": "sp-" + resource, "displayName": resource, "accountEnabled": True,
                               "oauth2PermissionScopes": [{"id": scope + "-id", "value": scope, "isEnabled": True} for scope in scopes]}
        app["requiredResourceAccess"].append({"resourceAppId": resource,
                                             "resourceAccess": [{"id": scope + "-id", "type": "Scope"} for scope in scopes]})
        grants.append({"resourceId": "sp-" + resource, "scope": " ".join(scopes), "consentType": "AllPrincipals"})

    class ReadOnlyAzure:
        def run(self, *args, **kwargs):
            if args[:3] == ("ad", "app", "show"):
                return app
            if args[:4] == ("ad", "app", "permission", "list-grants"):
                return grants
            if args[:3] == ("ad", "sp", "show"):
                return resources[args[-1]]
            pytest.fail("Preflight must only read Entra configuration")

    d.check_entra(ReadOnlyAzure(), CONFIG)
    grants[-1]["scope"] = ""
    with pytest.raises(d.DeploymentError, match="Administratörsmedgivande"):
        d.check_entra(ReadOnlyAzure(), CONFIG)


def test_manifest_keeps_domains_and_puts_secret_only_in_secret_storage():
    existing = {"properties": {"configuration": {"ingress": {"customDomains": [{"name": "krusgraph.com", "bindingType": "SniEnabled"}]}}}}
    manifest = d.make_manifest(CONFIG, "env-id", "identity-id", "registry.azurecr.io", "image@sha256:abc", "test-secret", existing)
    props = manifest["properties"]
    assert props["configuration"]["ingress"]["customDomains"] == existing["properties"]["configuration"]["ingress"]["customDomains"]
    env = {e["name"]: e for e in props["template"]["containers"][0]["env"]}
    assert env["ENTRA_REQUIRED"]["value"] == "true"
    assert env["ENTRA_CLIENT_SECRET"] == {"name": "ENTRA_CLIENT_SECRET", "secretRef": "entra-secret"}
    assert "test-secret" not in json.dumps(props["template"])
    assert props["template"]["scale"]["maxReplicas"] == 2
    assert props["configuration"]["registries"][0]["identity"] == "identity-id"


@pytest.mark.parametrize("fail", [False, True])
def test_secret_file_is_removed_even_when_azure_rejects_deployment(fail):
    seen = []

    class FakeAzure:
        def run(self, *args, **kwargs):
            assert "test-secret" not in args
            path = Path(args[args.index("--yaml") + 1])
            seen.append(path)
            assert "test-secret" in path.read_text(encoding="utf-8")
            if fail:
                raise d.DeploymentError("Simulated failure")

    manifest = d.make_manifest(CONFIG, "env", "identity", "registry", "image", "test-secret")
    if fail:
        with pytest.raises(d.DeploymentError):
            d.apply_manifest(FakeAzure(), CONFIG, manifest, False)
    else:
        d.apply_manifest(FakeAzure(), CONFIG, manifest, False)
    assert seen and not seen[0].exists()


def test_cli_errors_do_not_leak_secret_or_hide_access_denial(monkeypatch):
    monkeypatch.setattr(d.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=1, stdout="", stderr="AuthorizationFailed test-secret"))
    az = d.Azure(CONFIG)
    az.secret = "test-secret"
    with pytest.raises(d.DeploymentError) as error:
        az.run("acr", "show", missing_ok=True)
    assert "test-secret" not in str(error.value)
    assert "AuthorizationFailed" in str(error.value)


class FakeHosting:
    def __init__(self):
        self.calls, self.resources = [], {}
        self.secret = ""

    def run(self, *args, **kwargs):
        self.calls.append(args)
        if args[0] == "extension" or args[:3] == ("acr", "config", "authentication-as-arm"):
            return None
        if args[0] == "provider":
            return {"registrationState": "Registered"}
        if args[:3] == ("role", "assignment", "list"):
            return [{"principalId": "identity-principal", "roleDefinitionName": "AcrPull"}]
        if args[:2] == ("acr", "build"):
            return None
        if args[:3] == ("acr", "repository", "show"):
            return {"digest": "sha256:123"}
        if args[:2] == ("group", "exists"):
            return "group" in self.resources
        kind = "environment" if args[:2] == ("containerapp", "env") else args[0]
        action = args[2] if kind == "environment" else args[1]
        if action == "show":
            return copy.deepcopy(self.resources.get(kind))
        if action in {"create", "update"}:
            obj = {"id": kind + "-id", "tags": dict(d.OWNER_TAG)}
            if kind == "acr":
                assert "false" == args[args.index("--admin-enabled") + 1]
                obj.update(loginServer="test.azurecr.io", roleAssignmentMode="LegacyRegistryPermissions")
            elif kind == "identity":
                obj["principalId"] = "identity-principal"
            elif kind == "environment":
                obj["properties"] = {"staticIp": "192.0.2.8"}
            elif kind == "containerapp":
                obj = json.loads(Path(args[args.index("--yaml") + 1]).read_text(encoding="utf-8"))
                obj["properties"]["configuration"]["ingress"]["fqdn"] = "app.test.azurecontainerapps.io"
                obj["properties"]["customDomainVerificationId"] = "public-verification-code"
            self.resources[kind] = copy.deepcopy(obj)
            return obj
        pytest.fail(f"Unexpected command: {args}")


def test_deploy_can_be_rerun_and_reports_apex_dns_without_secret(monkeypatch, tmp_path, capsys):
    az = FakeHosting()
    monkeypatch.setattr(d, "ROOT", tmp_path)
    monkeypatch.setattr(d, "check_entra", lambda *args: None)
    monkeypatch.setattr(d, "source_tag", lambda: "src-test")
    monkeypatch.setattr(d, "verify_server", lambda *args, **kwargs: None)
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", "test-secret")
    d.deploy(az, CONFIG)
    d.deploy(az, CONFIG)
    for prefix in (("group", "create"), ("acr", "create"), ("identity", "create"), ("containerapp", "env", "create")):
        assert sum(call[:len(prefix)] == prefix for call in az.calls) == 1
    assert sum(call[:2] == ("containerapp", "update") for call in az.calls) == 1
    result = json.loads((tmp_path / "azure-result.json").read_text())
    assert result["dns"][0] == {"type": "A", "host": "@", "value": "192.0.2.8"}
    assert {r["host"] for r in result["dns"]} == {"@", "asuid", "www", "asuid.www"}
    assert "test-secret" not in json.dumps(result)
    assert "test-secret" not in capsys.readouterr().out


def test_server_check_rejects_unprotected_deployment(monkeypatch):
    monkeypatch.setattr(d, "http_response", lambda *args: (200, {}, '{"ok":true,"auth":"bearer-or-service-principal"}'))
    with pytest.raises(d.DeploymentError, match="inloggningen"):
        d.verify_server("https://example.test", CONFIG)


def test_server_check_covers_the_site_pages_and_the_demo(monkeypatch):
    seen = []

    def fake(url, method="GET"):
        seen.append((method, url.replace("https://example.test", "")))
        if url.endswith("/healthz"):
            return 200, {}, '{"ok":true,"auth":"entra"}'
        if "oauth-protected-resource" in url:
            return 200, {}, '{"resource":"https://%s/mcp"}' % CONFIG["domain"]
        if method == "POST":
            return 401, {"WWW-Authenticate": 'Bearer resource_metadata="https://%s/.well-known/oauth-protected-resource"' % CONFIG["domain"]}, ""
        return 200, {}, "<html>"

    monkeypatch.setattr(d, "http_response", fake)
    d.verify_server("https://example.test", CONFIG)
    checked = {path for method, path in seen if method == "GET"}
    assert {"/", "/explore", "/start", "/docs", "/privacy", "/demo/plan.json", "/static/site.css"} <= checked
    assert ("POST", "/mcp") in seen


def test_server_check_waits_for_the_new_revision(monkeypatch):
    """Right after an update the old revision may still answer: /explore 404 at first, then 200."""
    calls = {"explore": 0}

    def fake(url, method="GET"):
        if url.endswith("/healthz"):
            return 200, {}, '{"ok":true,"auth":"entra"}'
        if url.endswith("/explore"):
            calls["explore"] += 1
            return (404, {}, "") if calls["explore"] < 3 else (200, {}, "<html>")
        if "oauth-protected-resource" in url:
            return 200, {}, '{"resource":"https://%s/mcp"}' % CONFIG["domain"]
        if method == "POST":
            return 401, {"WWW-Authenticate": 'Bearer resource_metadata="https://%s/.well-known/oauth-protected-resource"' % CONFIG["domain"]}, ""
        return 200, {}, "<html>"

    monkeypatch.setattr(d, "http_response", fake)
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    d.verify_server("https://example.test", CONFIG)
    assert calls["explore"] >= 3


def test_server_check_waits_for_the_build_it_deployed(monkeypatch):
    """After an update the old revision answers /healthz first (old build tag, or none); the check waits for the new tag."""
    answers = iter(['{"ok":true,"auth":"entra"}', '{"ok":true,"auth":"entra","build":"src-old"}',
                    '{"ok":true,"auth":"entra","build":"src-new"}'])
    seen = {"healthz": 0}

    def fake(url, method="GET"):
        if url.endswith("/healthz"):
            seen["healthz"] += 1
            return 200, {}, next(answers, '{"ok":true,"auth":"entra","build":"src-new"}')
        if "oauth-protected-resource" in url:
            return 200, {}, '{"resource":"https://%s/mcp"}' % CONFIG["domain"]
        if method == "POST":
            return 401, {"WWW-Authenticate": 'Bearer resource_metadata="https://%s/.well-known/oauth-protected-resource"' % CONFIG["domain"]}, ""
        return 200, {}, "<html>"

    monkeypatch.setattr(d, "http_response", fake)
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    d.verify_server("https://example.test", CONFIG, "src-new")
    assert seen["healthz"] == 3


def test_server_check_fails_when_the_old_build_keeps_answering(monkeypatch):
    monkeypatch.setattr(d, "http_response", lambda *args: (200, {}, '{"ok":true,"auth":"entra","build":"src-old"}'))
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    with pytest.raises(d.DeploymentError, match="src-old.*src-new"):
        d.verify_server("https://example.test", CONFIG, "src-new")
    # Without a build to wait for (--status, --bind-domain) any healthy build passes, and so does a server without a tag.
    monkeypatch.setattr(d, "http_response", lambda url, method="GET": (
        (200, {}, '{"ok":true,"auth":"entra"}') if url.endswith("/healthz")
        else (200, {}, '{"resource":"https://%s/mcp"}' % CONFIG["domain"]) if "oauth-protected-resource" in url
        else (401, {"WWW-Authenticate": 'Bearer resource_metadata="https://%s/.well-known/oauth-protected-resource"' % CONFIG["domain"]}, "") if method == "POST"
        else (200, {}, "<html>")))
    d.verify_server("https://example.test", CONFIG)


@pytest.mark.parametrize("flag,target", [("--update", "update"), ("--check", "check_entra"), ("--status", "report"), ("--bind-domain", "bind_domains")])
def test_cli_flags_dispatch_without_touching_the_rest(monkeypatch, flag, target):
    called = []
    for name in ("update", "check_entra", "report", "bind_domains", "deploy"):
        monkeypatch.setattr(d, name, (lambda n: lambda *a, **k: called.append(n))(name))
    monkeypatch.setattr(d.Azure, "check_context", lambda self: called.append("check_context"))
    monkeypatch.setattr(d.sys, "argv", ["azure_containerapp.py", "--config", str(_CONFIG_FILE), flag])
    d.main()
    assert called == ["check_context", target]


@pytest.mark.parametrize("live,local,expect", [
    ("src-aaaa", "src-aaaa", "samma som denna utcheckning"),
    ("src-aaaa", "src-bbbb", "src-aaaa; denna utcheckning är src-bbbb. Kör --update"),
    (None, "src-bbbb", "inget byggmärke"),
])
def test_status_says_whether_the_live_build_is_this_checkout(monkeypatch, live, local, expect):
    health = {"ok": True, "auth": "entra"} | ({"build": live} if live else {})
    monkeypatch.setattr(d, "http_response", lambda url, method="GET": (200, {}, json.dumps(health)))
    monkeypatch.setattr(d, "source_tag", lambda: local)
    assert expect in d.build_status("https://example.test")
    monkeypatch.setattr(d, "http_response", lambda url, method="GET": (_ for _ in ()).throw(d.URLError("down")))
    assert "inget byggmärke" in d.build_status("https://example.test")     # unreachable: no crash, --status still prints the rest


def test_update_and_full_run_are_mutually_exclusive(monkeypatch, capsys):
    monkeypatch.setattr(d.sys, "argv", ["azure_containerapp.py", "--update", "--check"])
    with pytest.raises(SystemExit):
        d.main()
    assert "not allowed with" in capsys.readouterr().err


def test_existing_unrelated_resources_are_not_overwritten():
    with pytest.raises(d.DeploymentError):
        d.assert_owned({"tags": {"managed-by": "someone-else"}}, "shared-resource")


class FakeUpdateHosting:
    """The resources already exist; records every command so the test can prove what --update does not touch."""

    def __init__(self, app_exists=True):
        self.calls, self.secret = [], ""
        self.app_exists = app_exists

    def run(self, *args, **kwargs):
        self.calls.append(args)
        assert "entra-secret" not in " ".join(map(str, args)) or args[:2] == ("containerapp", "show")
        if args[0] == "extension":
            return None
        if args[:2] == ("containerapp", "show"):
            return {"id": "app-id", "tags": dict(d.OWNER_TAG), "properties": {"configuration": {"ingress": {"fqdn": "app.test.azurecontainerapps.io",
                    "customDomains": [{"name": "krusgraph.com", "bindingType": "SniEnabled"}]}, "secrets": [{"name": "entra-secret"}]},
                    "customDomainVerificationId": "code"}} if self.app_exists else None
        if args[:3] == ("containerapp", "env", "show"):
            return {"id": "env-id", "tags": dict(d.OWNER_TAG), "properties": {"staticIp": "192.0.2.8"}}
        if args[:2] == ("acr", "show"):
            return {"id": "acr-id", "tags": dict(d.OWNER_TAG), "loginServer": "test.azurecr.io"}
        if args[:2] == ("acr", "build"):
            return None
        if args[:3] == ("acr", "repository", "show"):
            return {"digest": "sha256:new"}
        if args[:2] == ("containerapp", "update"):
            return None
        pytest.fail(f"--update must not run: {args}")


def test_update_builds_and_swaps_the_image_only(monkeypatch, tmp_path, capsys):
    az = FakeUpdateHosting()
    monkeypatch.setattr(d, "ROOT", tmp_path)
    monkeypatch.setattr(d, "source_tag", lambda: "src-new")
    verified = []
    monkeypatch.setattr(d, "verify_server", lambda url, config, build=None: verified.append(build))
    monkeypatch.setattr(d.getpass, "getpass", lambda *a, **k: pytest.fail("--update must never ask for the secret"))
    monkeypatch.delenv("ENTRA_CLIENT_SECRET", raising=False)
    config = CONFIG | {"company_orgnr": "123456-7890"}
    d.update(az, config)
    heads = [c[:2] for c in az.calls]
    assert ("acr", "build") in heads
    update_call = next(c for c in az.calls if c[:2] == ("containerapp", "update"))
    assert "--image" in update_call and update_call[update_call.index("--image") + 1] == "test.azurecr.io/krusgraph@sha256:new"
    assert "--yaml" not in update_call and "--secrets" not in " ".join(update_call)
    env = update_call[update_call.index("--set-env-vars") + 1:]
    assert "COMPANY_ORGNR=123456-7890" in env and "PRODUCT_NAME=Krusgraph" in env and f"MCP_PUBLIC_URL=https://{CONFIG['domain']}/mcp" in env
    assert "KRUSGRAPH_BUILD=src-new" in env and "krusgraph:src-new" in next(c for c in az.calls if c[:2] == ("acr", "build"))
    assert not any(e.startswith("ENTRA_CLIENT_SECRET") for e in env)
    assert update_call[update_call.index("--min-replicas") + 1] == "0"          # default: scale to zero
    for untouched in (("ad",), ("containerapp", "hostname"), ("identity",), ("role",), ("group",), ("acr", "create"), ("containerapp", "create"), ("containerapp", "env", "create")):
        assert not any(c[:len(untouched)] == untouched for c in az.calls), untouched
    out = capsys.readouterr().out
    assert "test-secret" not in out and "KLART:" in out and "bind-domain" not in out   # no first-run DNS instructions
    assert verified == ["src-new"]           # the check waited for the build it just deployed, not any healthy one
    assert json.loads((tmp_path / "azure-result.json").read_text())["build"] == "src-new" and "src-new" in out


def test_update_refuses_before_the_first_full_run(monkeypatch):
    az = FakeUpdateHosting(app_exists=False)
    with pytest.raises(d.DeploymentError, match="full körning"):
        d.update(az, CONFIG)
    assert not any(c[:2] == ("acr", "build") for c in az.calls)


def test_company_orgnr_reaches_both_the_manifest_and_update():
    manifest = d.make_manifest(CONFIG | {"company_orgnr": " 123456-7890 "}, "env", "identity", "registry", "image", "s", build="src-abc")
    env = {e["name"]: e.get("value") for e in manifest["properties"]["template"]["containers"][0]["env"]}
    assert env["COMPANY_ORGNR"] == "123456-7890" and env["KRUSGRAPH_BUILD"] == "src-abc"
    assert "KRUSGRAPH_BUILD" not in d.plain_env(CONFIG)
    assert d.plain_env(CONFIG | {"company_orgnr": None})["COMPANY_ORGNR"] == ""
    assert d.plain_env(CONFIG)["COMPANY_ORGNR"] == "" or d.plain_env(CONFIG)["COMPANY_ORGNR"] == CONFIG.get("company_orgnr", "")


def test_min_replicas_and_fast_probes():
    assert d.min_replicas(CONFIG) == 0 and d.min_replicas(CONFIG | {"min_replicas": 1}) == 1
    with pytest.raises(d.DeploymentError):
        d.min_replicas(CONFIG | {"min_replicas": 5})
    startup = next(p for p in d.probes() if p["type"] == "Startup")
    assert startup["initialDelaySeconds"] <= 2 and startup["periodSeconds"] <= 2
    assert startup["initialDelaySeconds"] + startup["periodSeconds"] * startup["failureThreshold"] >= 60   # still patient
