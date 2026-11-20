"""W14: tools/workload_package.py builds, checks and compares the workload package, and uploads nothing.

The package is built with the repository's own workload/scripts/build_package.py into a temporary folder. The manifest
tests, `az` and HTTP are stand-ins: no network, no Fabric, no Azure.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = "853a0cf0-7d35-42b7-b384-26178755a72a"     # the development workload app's public client id (docs/WORKLOAD-DEV.md)


def _tool():
    spec = importlib.util.spec_from_file_location("w14_workload_package", ROOT / "tools" / "workload_package.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod                  # dataclasses look the module up while the class is made
    spec.loader.exec_module(mod)
    return mod


wp = _tool()


def _build(floor="1.0.500"):
    b = wp.load_build()
    b.default_version = lambda root=None: floor                 # a fixed floor: the test does not depend on git's history
    return b


def _run(args, *, build=None, tests_ok=True, confirm=lambda prompt: "", ran=None):
    lines = []
    calls = ran if ran is not None else []

    def runner(cmd):
        calls.append(cmd)
        return 0 if tests_ok else 1
    # --min-version 1.0.0: these tests use the fixed floor 1.0.500; WP1's 1.0.1396 minimum is tested in test_wp1_*
    code = wp.main(["--frontend-app-id", APP, "--min-version", "1.0.0", *args], build=build or _build(),
                   test_runner=runner, test_find=lambda m: object(), test_probe=lambda: "", tags=[], confirm=confirm,
                   out=lines.append)
    return code, "\n".join(lines), calls


# ------------------------------------------------------------------ the version

def test_bump_and_next_version():
    assert wp.bump("1.0.9") == "1.0.10"
    assert wp.bump("1.0.9", "minor") == "1.1.0"
    assert wp.bump("1.4.9", "major") == "2.0.0"
    assert wp.next_version("1.0.1385", "patch", "1.0.1300") == "1.0.1386"      # one above the last package
    assert wp.next_version("1.0.12", "patch", "1.0.1385") == "1.0.1385"        # never below 1.0.<commits>
    assert wp.next_version(None, "patch", "1.0.1385") == "1.0.1385"
    with pytest.raises(wp.StopError):
        wp.next_version("1.0.9", "patch", None, explicit="1.0.9")              # Fabric refuses a version it has
    with pytest.raises(wp.StopError):
        wp.next_version(None, "patch", None)
    with pytest.raises(wp.StopError):
        wp.bump("1.0", "patch")


# ------------------------------------------------------------------ the whole command

def test_first_build_checks_tests_and_prints_the_steps(tmp_path):
    code, out, calls = _run(["--out", str(tmp_path)])
    assert code == 0, out
    pkg = tmp_path / "Org.Krusgraph.1.0.500.nupkg"
    assert pkg.exists()
    assert "Checked: the build's manifest checks passed" in out
    assert "Checked: the manifest tests passed" in out
    assert calls and calls[0][1:4] == ["-m", "pytest", "-q"] and "tests/test_workload_manifest.py" in calls[0]
    assert "--noconftest" in calls[0] and "tests/test_workload_build.py" in calls[1]
    assert "No last package to compare with" in out
    assert "Nothing was uploaded." in out
    assert "OneLake catalog -> Govern -> Configurations -> Workloads" in out and "Upload workload" in out and str(pkg) in out
    assert wp.PORTAL_URL in out and "Krusgraph (preview)" in out
    assert "Activate" in out


def test_second_build_bumps_the_patch_and_diffs_against_the_last_package(tmp_path):
    _run(["--out", str(tmp_path)])
    code, out, _ = _run(["--out", str(tmp_path)])
    assert code == 0, out
    assert (tmp_path / "Org.Krusgraph.1.0.501.nupkg").exists()
    assert "Version: 1.0.500 -> 1.0.501" in out
    assert "Nothing else changed in the manifest" in out


def test_the_diff_names_texts_images_item_types_and_the_app():
    b = _build()
    vals = b.values(APP, "1.0.1", b.FRONTEND_URL, b.DEV_NAME)   # MOD1: the build's default is Krusgraph.Modeler since W12
    old = b.staged_files(vals)
    old["Org.Krusgraph.nuspec"] = b"<version>1.0.1</version>"
    new = dict(old)
    words = json.loads(new["FE/assets/locales/en-US/translations.json"])
    words["Workload_Hub_Slogan"] = "A new slogan"
    new["FE/assets/locales/en-US/translations.json"] = json.dumps(words).encode()
    new["FE/assets/images/Workload_Icon.png"] = old["FE/assets/images/Workload_Icon.png"] + b"x"
    new["FE/ModelItem.xml"] = new["BE/ModelItem.xml"]
    new["BE/ModelItem.xml"] = new["BE/ModelItem.xml"].replace(b"Org.Krusgraph.Model", b"Org.Krusgraph.Other")
    new["BE/WorkloadManifest.xml"] = new["BE/WorkloadManifest.xml"].replace(APP.encode(), b"11111111-2222-3333-4444-555555555555")
    new["Org.Krusgraph.nuspec"] = b"<version>1.0.2</version>"
    d = wp.manifest_diff(old, new)
    text = "\n".join(d.lines)
    assert "Version: 1.0.1 -> 1.0.2" in text
    assert "translations.json Workload_Hub_Slogan:" in text and "A new slogan" in text
    assert "Image changed: images/Workload_Icon.png" in text
    assert "ModelItem.xml Item type: Org.Krusgraph.Model -> Org.Krusgraph.Other" in text
    assert "WorkloadManifest.xml Frontend Entra app:" in text
    assert d.identity is True


def test_failed_manifest_tests_stop_and_remove_the_package(tmp_path):
    code, out, _ = _run(["--out", str(tmp_path)], tests_ok=False)
    assert code == 1
    assert "STOP: The manifest tests failed" in out
    assert not list(tmp_path.glob("*.nupkg"))


def test_skip_tests_says_so(tmp_path):
    code, out, calls = _run(["--out", str(tmp_path), "--skip-tests"])
    assert code == 0 and not calls
    assert "NOT checked: the repository's manifest tests were skipped" in out


def test_without_pytest_it_stops_rather_than_passing(monkeypatch):
    monkeypatch.setattr(wp.importlib.util, "find_spec", lambda name: None)
    with pytest.raises(wp.StopError, match="pytest and pillow, which are not installed"):
        wp.run_manifest_tests()


def test_a_refused_name_stops(tmp_path):
    code, out, _ = _run(["--out", str(tmp_path), "--name", "Krusgraph.Other"])
    assert code == 1 and "STOP:" in out and "reserve it" in out
    assert not list(tmp_path.glob("*.nupkg"))


def test_previous_package_and_version_rules(tmp_path):
    _run(["--out", str(tmp_path)])
    last = tmp_path / "Org.Krusgraph.1.0.500.nupkg"
    code, out, _ = _run(["--out", str(tmp_path / "next"), "--previous", str(last), "--version", "1.0.500"])
    assert code == 1 and "is not above the last package's 1.0.500" in out
    code, out, _ = _run(["--out", str(tmp_path / "next"), "--previous", str(last), "--bump", "minor"])
    assert code == 0 and (tmp_path / "next" / "Org.Krusgraph.1.1.0.nupkg").exists()
    code, out, _ = _run(["--out", str(tmp_path), "--previous", str(last), "--previous-ref", "HEAD"])
    assert code == 1 and "not both" in out


def test_previous_ref_builds_the_manifest_at_that_commit(tmp_path):
    if subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True).returncode:
        pytest.skip("no git checkout")
    code, out, _ = _run(["--out", str(tmp_path), "--previous-ref", "HEAD"])
    assert code == 0, out
    assert "Changes against the manifest at HEAD:" in out
    assert "Version: HEAD -> 1.0.500" in out


# ------------------------------------------------------------------ the upload: never without a documented API

def test_upload_without_a_documented_api_sends_nothing(tmp_path):
    assert wp.UPLOAD_API is None                 # docs/WORKLOAD-PACKAGE-UPDATES.md: no documented upload API

    def no_http(*a, **k):
        raise AssertionError("no HTTP without a documented API")

    def no_az(*a, **k):
        raise AssertionError("no az without a documented API")
    said = wp.upload(tmp_path / "x.nupkg", "Org.Krusgraph", "1.0.1", dry_run=False, confirm=lambda p: "Org.Krusgraph 1.0.1",
                     http=no_http, token=no_az)
    assert said.startswith("Not uploaded") and "never calls the portal's own endpoints" in said
    code, out, _ = _run(["--out", str(tmp_path), "--upload"], confirm=lambda p: pytest.fail("no prompt without an API"))
    assert code == 0 and "Not uploaded" in out and "Upload workload" in out


FAKE_API = {"url": "https://example.invalid/documented-upload", "method": "POST", "resource": "https://example.invalid",
            "role": "Fabric administrator", "source": "a documented page (stand-in)"}


def test_documented_api_path_is_dry_run_and_confirmed(tmp_path):
    pkg = tmp_path / "Org.Krusgraph.1.0.1.nupkg"
    pkg.write_bytes(b"PK")
    sent = []

    def http(method, url, body, headers):
        sent.append((method, url, body, headers))
        return 202
    said = wp.upload(pkg, "Org.Krusgraph", "1.0.1", dry_run=True, confirm=lambda p: "Org.Krusgraph 1.0.1", http=http,
                     token=lambda r: "t", api=FAKE_API)
    assert said.startswith("Dry run") and not sent
    said = wp.upload(pkg, "Org.Krusgraph", "1.0.1", dry_run=False, confirm=lambda p: "yes", http=http,
                     token=lambda r: "t", api=FAKE_API)
    assert said == "Not uploaded: the confirmation did not match." and not sent
    said = wp.upload(pkg, "Org.Krusgraph", "1.0.1", dry_run=False, confirm=lambda p: "Org.Krusgraph 1.0.1", http=http,
                     token=lambda r: "tok", api=FAKE_API)
    assert said.startswith("Uploaded") and sent[0][3]["Authorization"] == "Bearer tok"
    with pytest.raises(wp.StopError, match="HTTP 403"):
        wp.upload(pkg, "Org.Krusgraph", "1.0.1", dry_run=False, confirm=lambda p: "Org.Krusgraph 1.0.1",
                  http=lambda *a: 403, token=lambda r: "t", api=FAKE_API)


def test_az_token_comes_from_the_signed_in_cli_and_is_not_stored():
    seen = []

    def run(cmd):
        seen.append(cmd)
        return "abc\n"
    assert wp.az_token("https://api.fabric.microsoft.com", run) == "abc"
    assert seen[0][:3] == ["az", "account", "get-access-token"] and "--resource" in seen[0]

    def failing(cmd):
        raise subprocess.CalledProcessError(1, cmd)
    with pytest.raises(wp.StopError, match="az login"):
        wp.az_token("r", failing)
    with pytest.raises(wp.StopError, match="az login"):
        wp.az_token("r", lambda cmd: "")


def test_no_secret_no_portal_endpoint_and_nothing_under_deploy():
    src = (ROOT / "tools" / "workload_package.py").read_text(encoding="utf-8")
    for bad in ("client_secret", "--password", "powerbi.com/metadata", "wabi-", "biazure", "/v1.0/myorg/"):
        assert bad not in src, bad
    assert "app.fabric.microsoft.com" in src            # only named in the printed steps, never called
    assert not (ROOT / "deploy" / "workload_package.py").exists()
    sh = (ROOT / "tools" / "workload-package.sh").read_text(encoding="utf-8")
    assert 'exec python3 "$(dirname "$0")/workload_package.py" "$@"' in sh


def test_the_package_is_the_one_build_package_makes(tmp_path):
    _run(["--out", str(tmp_path / "a")])
    b = _build()
    direct = b.build(APP, "1.0.500", b.FRONTEND_URL, tmp_path / "b", name=b.DEV_NAME)   # the tool's default (MOD1)
    with zipfile.ZipFile(tmp_path / "a" / "Org.Krusgraph.1.0.500.nupkg") as x, zipfile.ZipFile(direct) as y:
        assert {n: x.read(n) for n in x.namelist()} == {n: y.read(n) for n in y.namelist()}
