"""CD1 (16 November 2026): .github/workflows/deploy.yml and deploy/auto_deploy.py. Nothing here calls Azure: the
gate, the snapshot and the rollback run against a fake `az`."""
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy"))
_spec = importlib.util.spec_from_file_location("auto_deploy", ROOT / "deploy" / "auto_deploy.py")
ad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ad)
WF = yaml.safe_load((ROOT / ".github" / "workflows" / "deploy.yml").read_text())
FULL = {"AZURE_CLIENT_ID": "c", "AZURE_TENANT_ID": "t", "AZURE_SUBSCRIPTION_ID": "s", "KRUSGRAPH_RESOURCE_GROUP": "rg",
        "KRUSGRAPH_APP": "app", "KRUSGRAPH_AUTO_DEPLOY": "on"}


def test_gate_is_dormant_without_variables():
    go, reason = ad.gate({})
    assert not go and "AZURE_CLIENT_ID" in reason and "Nothing was deployed" in reason
    go, reason = ad.gate({**FULL, "KRUSGRAPH_APP": " "})
    assert not go and "KRUSGRAPH_APP" in reason


@pytest.mark.parametrize("switch", ["", "off", "0", "true"])
def test_gate_needs_the_switch_on(switch):
    go, reason = ad.gate({**FULL, "KRUSGRAPH_AUTO_DEPLOY": switch})
    assert not go and "switched off" in reason


def test_gate_on():
    assert ad.gate({**FULL, "KRUSGRAPH_AUTO_DEPLOY": " On "})[0]


def test_gate_cli_writes_a_clean_no_op(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    for name in FULL:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert ad.main(["gate"]) == 0
    assert out.read_text() == "go=false\n" and "not set up" in capsys.readouterr().out


def _app(image="reg.azurecr.io/krusgraph@sha256:old", build="src-old"):
    return {"name": "app", "tags": {"managed-by": "krusgraph-deploy"},
            "properties": {"latestReadyRevisionName": "app--r1", "configuration": {"ingress": {"fqdn": "app.example.io"}},
                           "template": {"containers": [{"name": "app", "image": image, "env": [
                               {"name": "KRUSGRAPH_BUILD", "value": build},
                               {"name": "MCP_PUBLIC_URL", "value": "https://krusgraph.example/mcp"},
                               {"name": "ENTRA_CLIENT_SECRET", "secretRef": "entra-secret"}]}]}}}


class FakeAz:
    def __init__(self, app):
        self.app, self.calls = app, []

    def run(self, *args, **kw):
        self.calls.append(args)
        if args[:2] == ("containerapp", "show"):
            return self.app
        if args[:2] == ("containerapp", "update"):
            image = args[args.index("--image") + 1]
            build = args[args.index("--set-env-vars") + 1].split("=", 1)[1]
            self.app = _app(image, build)
        return None


def test_snapshot_reads_image_build_revision_and_never_a_secret():
    state = ad.snapshot(FakeAz(_app()), "app", "rg")
    assert state == {"image": "reg.azurecr.io/krusgraph@sha256:old", "build": "src-old", "revision": "app--r1",
                     "fqdn": "app.example.io", "domain": "krusgraph.example"}


def test_snapshot_refuses_an_app_this_deployment_does_not_own():
    app = _app()
    app["tags"] = {}
    with pytest.raises(ad.aca.DeploymentError):
        ad.snapshot(FakeAz(app), "app", "rg")


def test_rollback_points_back_at_the_previous_image_and_runs_the_update_checks(monkeypatch):
    checked = []
    monkeypatch.setattr(ad.aca, "verify_server", lambda url, config, build=None: checked.append((url, config, build)))
    az = FakeAz(_app("reg.azurecr.io/krusgraph@sha256:new", "src-new"))
    message = ad.rollback(az, "app", "rg", "reg.azurecr.io/krusgraph@sha256:old", "src-old")
    update = [c for c in az.calls if c[:2] == ("containerapp", "update")]
    assert len(update) == 1 and "KRUSGRAPH_BUILD=src-old" in update[0] and "--image" in update[0]
    assert not any("secret" in str(part).lower() for part in update[0])
    assert checked == [("https://app.example.io", {"domain": "krusgraph.example"}, "src-old")]
    assert "Rolled back" in message


def test_rollback_changes_nothing_when_the_update_never_happened(monkeypatch):
    monkeypatch.setattr(ad.aca, "verify_server", lambda *a, **k: None)
    az = FakeAz(_app())
    message = ad.rollback(az, "app", "rg", "reg.azurecr.io/krusgraph@sha256:old", "src-old")
    assert not any(c[:2] == ("containerapp", "update") for c in az.calls) and "nothing was changed" in message


def test_workflow_runs_after_green_ci_on_main_only_one_at_a_time():
    on = WF[True] if True in WF else WF["on"]
    assert on["workflow_run"] == {"workflows": ["CI"], "types": ["completed"], "branches": ["main"]}
    assert "push" not in on and "pull_request" not in on and "pull_request_target" not in on
    assert WF["concurrency"] == {"group": "deploy-krusgraph", "cancel-in-progress": False}
    assert WF["permissions"] == {"contents": "read"}
    gate = "\n".join(s.get("run", "") for s in WF["jobs"]["gate"]["steps"])
    assert "RUN_CONCLUSION\" != success" in gate and "RUN_EVENT\" != push" in gate and '"$sha" != "$tip"' in gate


def test_deploy_job_is_gated_uses_oidc_and_the_same_update_command():
    job = WF["jobs"]["deploy"]
    assert job["needs"] == "gate" and job["if"] == "needs.gate.outputs.go == 'true'"
    assert job["permissions"] == {"contents": "read", "id-token": "write", "issues": "write"}
    steps = job["steps"]
    login = next(s for s in steps if s.get("uses", "").startswith("azure/login@"))
    assert set(login["with"]) == {"client-id", "tenant-id", "subscription-id"}       # no client secret, no creds JSON
    runs = [s.get("run", "") for s in steps]
    assert any("bash deploy/krusgraph.sh --from-azure --update" in r for r in runs)
    rollback = next(s for s in steps if s.get("id") == "rollback")
    assert rollback["if"] == "failure() && steps.before.outcome == 'success'"
    assert any("gh issue create" in r for r in runs)
    text = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    assert "secrets." not in text and "build_package" not in text and "nupkg" not in text   # no workload upload


def test_one_time_steps_doc_names_every_variable_and_the_switch():
    doc = (ROOT / "docs" / "AUTO-DEPLOY.md").read_text()
    for name in (*ad.REQUIRED_VARIABLES, ad.SWITCH):
        assert name in doc, name
    for phrase in ("repo:Krusmaster/fabric-backend:ref:refs/heads/main", "Contributor", "resource group", "Switch it off"):
        assert phrase in doc, phrase
