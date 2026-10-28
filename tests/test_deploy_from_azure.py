"""deploy/azure_containerapp.py --from-azure (round n14): the configuration read from the container app that already
runs, for a Cloud Shell without storage. `az` is faked as the subprocess the helper starts: two subscriptions in one
tenant, the app in one of them. Every id and name here is invented."""
import copy
import json
from types import SimpleNamespace

import pytest

from deploy import azure_containerapp as d

TENANT = "00000000-0000-4000-8000-0000000000aa"
DEFAULT_SUB = "00000000-0000-4000-8000-000000000001"     # what Cloud Shell selects
APP_SUB = "00000000-0000-4000-8000-000000000002"         # where the app runs
SUBSCRIPTIONS = {DEFAULT_SUB: "Standardprenumeration", APP_SUB: "Krusgraph drift"}
RG_ID = f"/subscriptions/{APP_SUB}/resourceGroups/rg-krusgraph"
IDENTITY_ID = RG_ID + "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/krusgraph-pull"
SECRET_VALUE = "not-a-real-client-secret-value"

ENV = {"MCP_PUBLIC_URL": "https://krusgraph.com/mcp", "ENTRA_CLIENT_ID": "00000000-0000-4000-8000-0000000000c1",
       "ENTRA_REQUIRED": "true", "PRODUCT_NAME": "Krusgraph", "CONTACT_EMAIL": "hello@krusgraph.com",
       "COMPANY_ORGNR": "556000-0000", "KRUSGRAPH_BUILD": "src-old", "KRUSGRAPH_ONTOLOGY_WRITE": "1",
       "KRUSGRAPH_LOG_RETENTION_DAYS": "30", "KRUSGRAPH_ACCESS_LOG": "0",
       "ENTRA_CLIENT_SECRET_KEYVAULT_URI": "https://kv-krusgraph-test.vault.azure.net/secrets/entra-client-secret",
       "AZURE_CLIENT_ID": "00000000-0000-4000-8000-0000000000c2", "KRUSGRAPH_RATE_USER": "60/minute,1000/hour"}

EXPECTED = {
    "tenant_id": TENANT, "subscription_id": APP_SUB, "client_id": ENV["ENTRA_CLIENT_ID"], "domain": "krusgraph.com",
    "location": "swedencentral", "resource_group": "rg-krusgraph", "environment": "cae-krusgraph", "app": "krusgraph",
    "registry": "krusgraphtest", "identity": "krusgraph-pull", "product_name": "Krusgraph",
    "contact_email": "hello@krusgraph.com", "company_orgnr": "556000-0000", "include_www": True, "min_replicas": 1,
    "ontology_write": True, "key_vault": "kv-krusgraph-test", "log_retention_days": 30, "log_analytics_workspace": "",
}


def live_app():
    """`az containerapp show` of the running app, as Azure answers it (secrets by name; the value is here only so the
    tests can prove it never travels)."""
    env = [{"name": k, "value": v} for k, v in ENV.items()] + [{"name": "ENTRA_CLIENT_SECRET", "secretRef": "entra-secret"},
                                                                {"name": "KRUSGRAPH_USAGE_SALT", "secretRef": "usage-salt"}]
    return {
        "id": RG_ID + "/providers/Microsoft.App/containerApps/krusgraph", "name": "krusgraph", "location": "Sweden Central",
        "tags": dict(d.OWNER_TAG),
        "identity": {"type": "UserAssigned", "userAssignedIdentities": {IDENTITY_ID: {"principalId": "p", "clientId": "c"}}},
        "properties": {
            "environmentId": RG_ID + "/providers/Microsoft.App/managedEnvironments/cae-krusgraph",
            "customDomainVerificationId": "public-verification-code",
            "configuration": {
                "ingress": {"fqdn": "krusgraph.test.swedencentral.azurecontainerapps.io",
                            "customDomains": [{"name": "krusgraph.com", "bindingType": "SniEnabled"},
                                              {"name": "www.krusgraph.com", "bindingType": "SniEnabled"}]},
                "registries": [{"server": "krusgraphtest.azurecr.io", "identity": IDENTITY_ID}],
                "secrets": [{"name": "entra-secret", "value": SECRET_VALUE}, {"name": "usage-salt"}]},
            "template": {"containers": [{"name": "krusgraph", "image": "krusgraphtest.azurecr.io/krusgraph@sha256:old", "env": env}],
                         "scale": {"minReplicas": 1, "maxReplicas": 2}},
        },
    }


class FakeCloud:
    """`az` as a subprocess. Records (arguments, --subscription) for every call and applies `containerapp update`
    to the app, so a test can compare the app before and after."""

    def __init__(self, selected=DEFAULT_SUB, app_in=APP_SUB, also=()):
        self.selected, self.app_in, self.also = selected, app_in, list(also)
        self.app = live_app()
        self.calls = []

    def __call__(self, command, **kwargs):
        assert command[0] == "az"
        args = tuple(command[1:command.index("--only-show-errors")])
        sub = command[command.index("--subscription") + 1] if "--subscription" in command else None
        self.calls.append((args, sub))
        answer = self.answer(args, sub)
        return SimpleNamespace(returncode=0, stdout="" if answer is None else json.dumps(answer), stderr="")

    def answer(self, args, sub):
        if args[:2] == ("account", "show"):
            return {"id": self.selected, "name": SUBSCRIPTIONS[self.selected], "tenantId": TENANT, "state": "Enabled"}
        if args[:2] == ("account", "list"):
            return [{"id": s, "name": n, "tenantId": TENANT, "state": "Enabled"} for s, n in SUBSCRIPTIONS.items()]
        if args[:2] == ("resource", "list"):
            assert args[args.index("--resource-type") + 1] == "Microsoft.App/containerApps"
            other = [{"name": "orders-api", "resourceGroup": "rg-other", "type": "Microsoft.App/containerApps"}]
            if sub != self.app_in:
                return other
            return other + self.also + [{"name": "krusgraph", "resourceGroup": "rg-krusgraph", "type": "Microsoft.App/containerApps"}]
        if args[0] == "extension":
            return None
        assert sub == self.app_in, f"{args} ran against {sub}, not the app's subscription"
        if args[:2] == ("group", "show"):
            return {"name": "rg-krusgraph", "location": "swedencentral"}
        if args[:2] == ("containerapp", "show"):
            return copy.deepcopy(self.app)
        if args[:3] == ("containerapp", "env", "show"):
            return {"id": "env-id", "tags": dict(d.OWNER_TAG), "properties": {"staticIp": "192.0.2.8"}}
        if args[:2] == ("acr", "build"):
            return None
        if args[:2] == ("acr", "show"):
            return {"id": "acr-id", "tags": dict(d.OWNER_TAG), "loginServer": "krusgraphtest.azurecr.io"}
        if args[:3] == ("acr", "repository", "show"):
            return {"digest": "sha256:new"}
        if args[:2] == ("containerapp", "update"):
            template = self.app["properties"]["template"]
            container = template["containers"][0]
            container["image"] = args[args.index("--image") + 1]
            if "--min-replicas" in args:
                template["scale"]["minReplicas"] = int(args[args.index("--min-replicas") + 1])
            env = {e["name"]: e for e in container["env"]}
            for pair in args[args.index("--set-env-vars") + 1:]:
                key, value = pair.split("=", 1)
                env[key] = {"name": key, "value": value}
            container["env"] = list(env.values())
            return None
        pytest.fail(f"Unexpected command: {args}")


def run_main(monkeypatch, tmp_path, cloud, *flags):
    monkeypatch.setattr(d.subprocess, "run", cloud)
    monkeypatch.setattr(d, "ROOT", tmp_path)
    monkeypatch.setattr(d, "source_tag", lambda: "src-new")
    monkeypatch.setattr(d, "verify_server", lambda *a, **k: None)
    monkeypatch.setattr(d.getpass, "getpass", lambda *a, **k: pytest.fail("--from-azure never asks for the secret"))
    monkeypatch.delenv("ENTRA_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(d.sys, "argv", ["azure_containerapp.py", "--config", str(tmp_path / "krusgraph.json"), *flags])
    d.main()


def test_app_in_another_subscription_stops_with_the_az_account_set_command(monkeypatch, tmp_path, capsys):
    cloud = FakeCloud(selected=DEFAULT_SUB, app_in=APP_SUB)
    with pytest.raises(SystemExit) as stop:
        run_main(monkeypatch, tmp_path, cloud, "--from-azure", "--update")
    assert stop.value.code == 1
    err = capsys.readouterr().err
    assert f"az account set --subscription {APP_SUB}" in err and "Krusgraph drift" in err and "rg-krusgraph" in err
    assert "byter inte prenumeration" in err
    # the other subscription was searched by listing container apps there, nothing else ran, nothing was switched
    assert ((("resource", "list", "--resource-type", "Microsoft.App/containerApps"), APP_SUB)) in cloud.calls
    assert [a[:2] for a, _ in cloud.calls] == [("account", "show"), ("resource", "list"), ("account", "list"), ("resource", "list")]
    assert not (tmp_path / "krusgraph.json").exists()


def test_built_configuration_is_shown_and_written_when_the_file_is_missing(monkeypatch, tmp_path, capsys):
    cloud = FakeCloud(selected=APP_SUB)
    run_main(monkeypatch, tmp_path, cloud, "--from-azure")
    assert json.loads((tmp_path / "krusgraph.json").read_text(encoding="utf-8")) == EXPECTED
    out = capsys.readouterr().out
    assert '"client_id": "%s"' % ENV["ENTRA_CLIENT_ID"] in out and "Sparade" in out
    # alone, --from-azure only reads: no build, no update, no secret command
    assert not any(a[:2] in {("acr", "build"), ("containerapp", "update")} or "secret" in a for a, _ in cloud.calls)
    assert SECRET_VALUE not in out and SECRET_VALUE not in (tmp_path / "krusgraph.json").read_text()


def test_the_fields_match_the_example_file():
    example = json.loads((d.ROOT / "deploy" / "krusgraph.example.json").read_text(encoding="utf-8"))
    assert sorted(EXPECTED) == sorted(example)


def test_an_existing_krusgraph_json_is_not_overwritten(monkeypatch, tmp_path, capsys):
    path = tmp_path / "krusgraph.json"
    old = json.dumps(dict(EXPECTED, min_replicas=0, company_orgnr="", registry="oldregistry"), indent=2) + "\n"
    path.write_text(old, encoding="utf-8")
    cloud = FakeCloud(selected=APP_SUB)
    run_main(monkeypatch, tmp_path, cloud, "--from-azure", "--update")
    assert path.read_text(encoding="utf-8") == old                          # byte for byte
    out = capsys.readouterr().out
    assert "skrevs inte över" in out and "registry, company_orgnr, min_replicas" in out
    # the run used the app's values, not the stale file: the image went to the app's registry, min_replicas stayed 1
    assert cloud.app["properties"]["template"]["containers"][0]["image"] == "krusgraphtest.azurecr.io/krusgraph@sha256:new"
    assert cloud.app["properties"]["template"]["scale"]["minReplicas"] == 1
    run_main(monkeypatch, tmp_path, cloud, "--from-azure", "--overwrite-config")    # only the explicit flag replaces it
    assert json.loads(path.read_text(encoding="utf-8")) == EXPECTED


def test_built_configuration_gives_the_environment_the_app_already_has(monkeypatch, tmp_path):
    cloud = FakeCloud(selected=APP_SUB)
    before = live_app()
    run_main(monkeypatch, tmp_path, cloud, "--from-azure", "--update")
    config = json.loads((tmp_path / "krusgraph.json").read_text(encoding="utf-8"))
    env_before = {e["name"]: e.get("value") for e in before["properties"]["template"]["containers"][0]["env"] if "value" in e}
    # what a run from this configuration sets is what the app has
    assert {k: env_before.get(k) for k in d.plain_env(config)} == d.plain_env(config)
    assert d.min_replicas(config) == before["properties"]["template"]["scale"]["minReplicas"]
    assert d.key_vault_uri(config) == env_before["ENTRA_CLIENT_SECRET_KEYVAULT_URI"]
    # and --from-azure --update changed the image and its build tag, nothing else
    update_call = next(a for a, _ in cloud.calls if a[:2] == ("containerapp", "update"))
    assert "--min-replicas" not in update_call and update_call[update_call.index("--set-env-vars") + 1:] == ("KRUSGRAPH_BUILD=src-new",)
    after = cloud.app["properties"]["template"]
    env_after = {e["name"]: e for e in after["containers"][0]["env"]}
    assert env_after.pop("KRUSGRAPH_BUILD") == {"name": "KRUSGRAPH_BUILD", "value": "src-new"}
    assert env_after == {e["name"]: e for e in before["properties"]["template"]["containers"][0]["env"] if e["name"] != "KRUSGRAPH_BUILD"}
    assert after["scale"] == before["properties"]["template"]["scale"]
    assert not any("secret" in a for a, _ in cloud.calls)                   # no secret is read or set


def test_two_krusgraph_apps_need_app_and_resource_group(monkeypatch, tmp_path, capsys):
    cloud = FakeCloud(selected=APP_SUB, also=[{"name": "krusgraph-preview", "resourceGroup": "rg-preview"}])
    with pytest.raises(SystemExit):
        run_main(monkeypatch, tmp_path, cloud, "--from-azure")
    assert "Flera container-appar passar: krusgraph-preview (rg-preview), krusgraph (rg-krusgraph)" in capsys.readouterr().err
    assert not (tmp_path / "krusgraph.json").exists()
    run_main(monkeypatch, tmp_path, cloud, "--from-azure", "--app", "krusgraph", "--resource-group", "rg-krusgraph")
    assert json.loads((tmp_path / "krusgraph.json").read_text(encoding="utf-8")) == EXPECTED


def test_flags_that_belong_to_from_azure_are_refused_without_it(monkeypatch, tmp_path, capsys):
    for flags in (["--app", "krusgraph"], ["--overwrite-config"], ["--from-azure", "--plan"]):
        monkeypatch.setattr(d.sys, "argv", ["azure_containerapp.py", "--config", str(tmp_path / "x.json"), *flags])
        with pytest.raises(SystemExit):
            d.main()
    monkeypatch.setattr(d.sys, "argv", ["azure_containerapp.py", "--config", str(tmp_path / "missing.json"), "--update"])
    with pytest.raises(SystemExit):
        d.main()
    assert "--from-azure --update" in capsys.readouterr().err               # a missing file says what to run instead
