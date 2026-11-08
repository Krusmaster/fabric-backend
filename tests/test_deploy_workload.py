"""Round n168: deploy/krusgraph.sh --update carries the Fabric workload's variables and, with --workload-host, prints
the Namecheap records and binds workload.krusgraph.com with a managed certificate once its CNAME resolves. Fake Azure
only; nothing here calls Azure, Entra, DNS or Fabric. And the workload package (workload/scripts/build-package) points
at the hosted editor and keeps the name Org.Krusgraph."""
import copy
import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from deploy import azure_containerapp as d

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "deploy/krusgraph.example.json").read_text(encoding="utf-8"))
WL_ID = "99999999-8888-7777-6666-555555555555"
WL_URI = "https://krusgraph.com/workload/Org.Krusgraph"
FQDN = "krusgraph.happy-sea.swedencentral.azurecontainerapps.io"
WL_CONFIG = {"workload_client_id": WL_ID, "workload_app_id_uri": WL_URI, "workload_allowed_tenants": "d2fcf72a-9b80-451d-868b-8d47af30d8ae"}


class FakeApp:
    """The container app as `az containerapp show` returns it, and every command the run sends."""

    def __init__(self, env=None, secret=True, domains=("krusgraph.com",)):
        self.calls, self.secret = [], ""
        env = dict(env or {})
        entries = [{"name": k, "value": v} for k, v in env.items()]
        secrets = [{"name": "entra-secret"}]
        if secret:
            entries.append({"name": "KRUSGRAPH_WORKLOAD_CLIENT_SECRET", "secretRef": "workload-secret"})
            secrets.append({"name": "workload-secret"})
        self.app = {"id": "app-id", "tags": dict(d.OWNER_TAG), "properties": {
            "customDomainVerificationId": "ABC123VERIFY",
            "configuration": {"ingress": {"fqdn": FQDN, "customDomains": [{"name": n, "bindingType": "SniEnabled"} for n in domains]},
                              "secrets": secrets},
            "template": {"containers": [{"name": "krusgraph", "env": entries}]}}}

    def run(self, *args, **kwargs):
        self.calls.append(args)
        if args[0] == "extension":
            return None
        if args[:2] == ("containerapp", "show"):
            return copy.deepcopy(self.app)
        if args[:3] == ("containerapp", "env", "show"):
            return {"id": "env-id", "tags": dict(d.OWNER_TAG), "properties": {"staticIp": "192.0.2.8"}}
        if args[:2] == ("acr", "show"):
            return {"id": "acr-id", "tags": dict(d.OWNER_TAG), "loginServer": "test.azurecr.io"}
        if args[:3] == ("acr", "repository", "show"):
            return {"digest": "sha256:new"}
        if args[:2] in (("acr", "build"), ("containerapp", "update")) or args[:3] in (
                ("containerapp", "hostname", "add"), ("containerapp", "hostname", "bind")):
            return None
        pytest.fail(f"unexpected command: {args}")

    def sent(self, *head):
        return [c for c in self.calls if c[:len(head)] == head]


@pytest.fixture
def quiet(monkeypatch, tmp_path):
    monkeypatch.setattr(d, "ROOT", tmp_path)
    monkeypatch.setattr(d, "source_tag", lambda *a: "src-new")
    monkeypatch.setattr(d, "verify_server", lambda *a, **k: None)
    monkeypatch.setattr(d.getpass, "getpass", lambda *a, **k: pytest.fail("never asks for a secret"))


def env_of(update_call):
    return update_call[update_call.index("--set-env-vars") + 1:]


def test_update_sets_the_workload_variables_from_the_config(quiet, capsys):
    az = FakeApp()
    d.update(az, CONFIG | WL_CONFIG)
    env = env_of(az.sent("containerapp", "update")[0])
    assert f"KRUSGRAPH_WORKLOAD_CLIENT_ID={WL_ID}" in env and f"KRUSGRAPH_WORKLOAD_APP_ID_URI={WL_URI}" in env
    assert "KRUSGRAPH_WORKLOAD_ALLOWED_TENANTS=d2fcf72a-9b80-451d-868b-8d47af30d8ae" in env
    assert "KRUSGRAPH_WORKLOAD_CLIENT_SECRET=secretref:workload-secret" in env          # a reference, never a value
    assert not az.sent("containerapp", "hostname")                                       # no --workload-host: no host name


def test_update_keeps_workload_variables_set_by_hand_and_says_so(quiet, capsys):
    az = FakeApp(env={"KRUSGRAPH_WORKLOAD_CLIENT_ID": WL_ID, "KRUSGRAPH_WORKLOAD_APP_ID_URI": WL_URI,
                      "KRUSGRAPH_WORKLOAD_HOST": "workload.krusgraph.com", "KRUSGRAPH_MCP_APPS": "1"})
    d.update(az, {k: v for k, v in CONFIG.items() if k != "mcp_apps"})
    env = env_of(az.sent("containerapp", "update")[0])
    assert f"KRUSGRAPH_WORKLOAD_CLIENT_ID={WL_ID}" in env and "KRUSGRAPH_WORKLOAD_HOST=workload.krusgraph.com" in env
    assert "KRUSGRAPH_MCP_APPS=1" in env                                                 # n159's switches are still kept
    out = capsys.readouterr().out
    assert f'lägg till "workload_client_id": "{WL_ID}"' in out and '"workload_host": "workload.krusgraph.com"' in out


def test_update_stops_before_building_when_the_workload_secret_is_missing(quiet, capsys):
    az = FakeApp(secret=False)
    with pytest.raises(d.DeploymentError, match="workload-secret") as e:
        d.update(az, CONFIG | WL_CONFIG)
    assert 'read -rsp' in str(e.value) and "--secrets workload-secret=\"$WS\"" in str(e.value)
    assert "--set-env-vars" not in str(e.value)        # storing the secret alone never changes the running server
    assert not az.sent("acr", "build") and not az.sent("containerapp", "update")


def test_update_needs_both_the_id_and_the_uri(quiet):
    az = FakeApp()
    with pytest.raises(d.DeploymentError, match="både"):
        d.update(az, CONFIG | {"workload_client_id": WL_ID})
    assert not az.sent("acr", "build")


def test_dry_run_shows_the_carry_over_and_the_dns_records_and_changes_nothing(quiet, capsys):
    az = FakeApp(env={"KRUSGRAPH_WORKLOAD_SCOPE": "user_impersonation"})
    assert d.update(az, CONFIG | WL_CONFIG, workload_host=True, dry_run=True) is None
    assert {c[:2] for c in az.calls} == {("containerapp", "show")}                       # read only
    out = capsys.readouterr().out
    assert "TORRKÖRNING" in out
    assert f"KRUSGRAPH_WORKLOAD_CLIENT_ID={WL_ID}" in out and "KRUSGRAPH_WORKLOAD_HOST=workload.krusgraph.com" in out
    assert "KRUSGRAPH_WORKLOAD_SCOPE=user_impersonation" in out and '"workload_scope"' in out   # carried, and named
    assert f"CNAME Host: workload" in out and FQDN in out
    assert "TXT   Host: asuid.workload" in out and "ABC123VERIFY" in out
    assert "Namecheap" in out and "--validation-method CNAME" in out


def test_dry_run_through_the_command_line(monkeypatch, tmp_path, capsys, quiet):
    cfg = tmp_path / "krusgraph.json"
    cfg.write_text(json.dumps(CONFIG | WL_CONFIG), encoding="utf-8")
    az = FakeApp()
    monkeypatch.setattr(d, "Azure", lambda config: az)
    monkeypatch.setattr(FakeApp, "check_context", lambda self: None, raising=False)
    monkeypatch.setattr(d.sys, "argv", ["azure_containerapp.py", "--config", str(cfg), "--update", "--workload-host", "--dry-run"])
    d.main()
    out = capsys.readouterr().out
    assert "asuid.workload" in out and "KRUSGRAPH_WORKLOAD_HOST=workload.krusgraph.com" in out
    assert not az.sent("acr", "build")


def test_workload_host_only_with_update(monkeypatch, tmp_path):
    cfg = tmp_path / "krusgraph.json"
    cfg.write_text(json.dumps(CONFIG), encoding="utf-8")
    for extra in (["--workload-host"], ["--dry-run"], ["--status", "--workload-host"]):
        monkeypatch.setattr(d.sys, "argv", ["azure_containerapp.py", "--config", str(cfg), *extra])
        with pytest.raises(SystemExit):
            d.main()


def test_workload_host_waits_for_dns_then_binds_with_a_managed_certificate(quiet, monkeypatch, capsys):
    az = FakeApp()
    monkeypatch.setattr(d, "resolves_to_app", lambda *a: False)
    d.update(az, CONFIG | WL_CONFIG, workload_host=True)
    assert az.sent("containerapp", "update") and not az.sent("containerapp", "hostname")
    out = capsys.readouterr().out
    assert out.index("asuid.workload") < out.index("KLART")                             # records first, before the step
    assert "lades inte till" in out
    env = env_of(az.sent("containerapp", "update")[0])
    assert "KRUSGRAPH_WORKLOAD_HOST=workload.krusgraph.com" in env

    az = FakeApp()
    monkeypatch.setattr(d, "resolves_to_app", lambda *a: True)
    d.update(az, CONFIG | WL_CONFIG, workload_host="workload.krusgraph.com")
    add, bind = az.sent("containerapp", "hostname", "add"), az.sent("containerapp", "hostname", "bind")
    assert add and add[0][add[0].index("--hostname") + 1] == "workload.krusgraph.com"
    assert bind and bind[0][bind[0].index("--validation-method") + 1] == "CNAME"
    assert bind[0][bind[0].index("--environment") + 1] == CONFIG["environment"]

    az = FakeApp(domains=("krusgraph.com", "workload.krusgraph.com"))                 # already bound: nothing to do
    d.update(az, CONFIG | WL_CONFIG, workload_host=True)
    assert not az.sent("containerapp", "hostname")


@pytest.mark.parametrize("host", ["workload.example.com", "krusgraph.com", "work load.krusgraph.com"])
def test_workload_host_must_be_a_subdomain(host):
    with pytest.raises(d.DeploymentError):
        d.workload_host_name(CONFIG, host)


def test_full_run_keeps_hand_set_workload_variables_but_not_without_the_secret(capsys):
    existing = FakeApp(env={"KRUSGRAPH_WORKLOAD_HOST": "workload.krusgraph.com", "KRUSGRAPH_WORKLOAD_CLIENT_ID": WL_ID,
                            "KRUSGRAPH_WORKLOAD_APP_ID_URI": WL_URI}).app
    manifest = d.make_manifest(CONFIG, "env", "identity", "registry", "image", "s", existing)
    env = {e["name"]: e for e in manifest["properties"]["template"]["containers"][0]["env"]}
    assert env["KRUSGRAPH_WORKLOAD_HOST"]["value"] == "workload.krusgraph.com"
    # the full run replaces the secret list, so the engine's variables would start a server without its secret
    assert "KRUSGRAPH_WORKLOAD_CLIENT_ID" not in env and "KRUSGRAPH_WORKLOAD_CLIENT_SECRET" not in env
    assert "--secrets workload-secret=" in capsys.readouterr().out


def test_the_editor_sources_are_part_of_the_image_tag(tmp_path):
    for name in ("Dockerfile", ".dockerignore", "pyproject.toml", "README.md"):
        (tmp_path / name).write_text("x")
    (tmp_path / "deploy").mkdir(); (tmp_path / "fabric_backend").mkdir()
    (tmp_path / "deploy" / "constraints.txt").write_text("requests==1.0\n")
    app = tmp_path / "workload" / "Workload" / "app"
    app.mkdir(parents=True)
    (app / "index.ts").write_text("a")
    before = d.source_tag(tmp_path)
    (app / "index.ts").write_text("b")
    assert d.source_tag(tmp_path) != before
    (app / "x.test.ts").write_text("tests are not in the image")
    after = d.source_tag(tmp_path)
    (app / "x.test.ts").write_text("changed")
    assert d.source_tag(tmp_path) == after


def test_dockerfile_builds_the_editor_with_a_pinned_node_lts():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    import re
    stage = re.search(r"^FROM node:(\d+)\.(\d+)\.(\d+)-bookworm-slim AS editor$", text, re.M)
    assert stage and int(stage.group(1)) % 2 == 0                                   # an even major: an LTS line
    assert "npm ci" in text and "webpack" in text and "COPY --from=editor /editor /app/workload-dist" in text
    assert "WORKLOAD_NAME=Org.Krusgraph" in text and "Krusgraph." not in text.replace("Org.Krusgraph", "")
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "!workload/Workload/app/**" in ignore and "!workload/Workload/package-lock.json" in ignore


# ------------------------------------------------------------------ the workload package ---------------------------

def _builder():
    spec = importlib.util.spec_from_file_location("build_package", ROOT / "workload/scripts/build_package.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_package_points_at_the_hosted_editor_and_keeps_org_krusgraph(tmp_path):
    run = subprocess.run(["bash", str(ROOT / "workload/scripts/build-package"), "--frontend-app-id", WL_ID,
                          "--version", "1.0.7", "--out", str(tmp_path)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "Nothing was uploaded" in run.stdout
    pkg = tmp_path / "Org.Krusgraph.1.0.7.nupkg"
    with zipfile.ZipFile(pkg) as z:
        names = set(z.namelist())
        assert {"Org.Krusgraph.nuspec", "_rels/.rels", "[Content_Types].xml", "BE/WorkloadManifest.xml", "BE/ModelItem.xml",
                "FE/Product.json", "FE/ModelItem.json", "FE/assets/images/Workload_Icon.png"} <= names
        manifest = z.read("BE/WorkloadManifest.xml").decode()
        assert 'WorkloadName="Org.Krusgraph"' in manifest and "<Url>https://workload.krusgraph.com</Url>" in manifest
        assert f"<AppId>{WL_ID}</AppId>" in manifest and "<Version>1.0.7</Version>" in manifest
        assert 'TypeName="Org.Krusgraph.Model"' in z.read("BE/ModelItem.xml").decode()
        spec = z.read("Org.Krusgraph.nuspec").decode()
        assert "<id>Org.Krusgraph</id>" in spec and "<version>1.0.7</version>" in spec and "<files>" not in spec
        product = json.loads(z.read("FE/Product.json"))
        assert product["createExperience"]["cards"][0]["itemType"] == "Model"
        for name in names:
            if name.endswith((".xml", ".json", ".nuspec", ".rels")):
                text = z.read(name).decode()
                assert "{{" not in text and "localhost" not in text, name
                assert "Krusgraph." not in text.replace("Org.Krusgraph", "").replace("Krusgraph.com", ""), name
    again = tmp_path / "again"
    subprocess.run(["bash", str(ROOT / "workload/scripts/build-package"), "--frontend-app-id", WL_ID, "--version", "1.0.7",
                    "--out", str(again)], check=True, capture_output=True)
    assert (again / pkg.name).read_bytes() == pkg.read_bytes()                       # same inputs, same bytes


@pytest.mark.parametrize("kwargs, word", [
    ({"frontend_app_id": "not-a-guid"}, "GUID"),
    ({"frontend_app_id": "00000000-0000-0000-0000-000000000000"}, "placeholder"),
    ({"frontend_url": "https://workload.example.com"}, "verified domain"),
    ({"frontend_url": "http://workload.krusgraph.com"}, "https"),
    ({"frontend_url": "https://workload.krusgraph.com/a/b"}, "segment"),
    ({"version": "2"}, "1.0.12"),
])
def test_the_package_refuses_what_fabric_would(tmp_path, kwargs, word):
    b = _builder()
    args = {"frontend_app_id": WL_ID, "version": "1.0.1", "out_dir": tmp_path} | kwargs
    with pytest.raises(b.PackageError, match=word):
        b.build(**args)
    assert not list(tmp_path.glob("*.nupkg"))


def test_the_package_refuses_a_krusgraph_dot_name(tmp_path):
    b = _builder()
    manifest = tmp_path / "Manifest"
    import shutil
    shutil.copytree(ROOT / "workload/Workload/Manifest", manifest)
    xml = manifest / "WorkloadManifest.xml"
    xml.write_text(xml.read_text().replace("{{WORKLOAD_NAME}}", "Krusgraph.Model"))
    with pytest.raises(b.PackageError):
        b.build(WL_ID, "1.0.1", out_dir=tmp_path / "out", manifest=manifest)


def test_the_package_version_grows_with_the_history():
    b = _builder()
    version = b.default_version()
    assert version.startswith("1.0.") and int(version.split(".")[-1]) > 0
