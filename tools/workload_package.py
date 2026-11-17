#!/usr/bin/env python3
"""W14 (17 November 2026): build, check and compare the Fabric workload package in one command; never upload it.

The frontend and the engine deploy with the container app, but a change to the workload's manifest (its name, item
types, icons, Workload Hub texts, version, the Entra app it names) reaches Fabric only when a Fabric administrator
uploads a new .nupkg and activates it. This tool does everything before that upload:

  1. builds the .nupkg from workload/Workload/Manifest exactly the way the repository builds it today (it calls
     workload/scripts/build_package.py, which it does not change);
  2. picks the next version: one patch above the last package (by default; --bump minor|major, or --version), and never
     below 1.0.<commits on this checkout>, the number the build has always used, so it also grows on a fresh clone;
  3. checks the manifest: build_package.check() (the name, the hosted URL, the app id, image sizes, the Workload Hub
     fields) and then the repository's manifest tests (pytest; --skip-tests only where pytest cannot be installed);
  4. prints a short diff of what changed for Fabric against the last package (a .nupkg file, or a git ref built the same
     way): the name, the version, the item types, the frontend app and URL, the Workload Hub texts, the images;
  5. stops and prints the Admin-portal steps with the file's path. It opens nothing.

Upload. docs/WORKLOAD-PACKAGE-UPDATES.md (W14, part 3a) found no documented Microsoft API, CLI or PowerShell command
that uploads or updates a workload package, so UPLOAD_API below is None and `--upload` only says so and prints the same
steps. The tool never calls an undocumented or private Fabric portal endpoint. Should Microsoft document such an API,
UPLOAD_API gets its URL, scope and role from that page (cited there), and `--upload` then signs in through `az` (no
secret stored, no client secret), shows what it would send and sends it only after the person types the package's
name and version; without --upload, or with --dry-run, nothing is sent.

    tools/workload-package.sh --frontend-app-id <the workload app's Application (client) ID>
                              [--name Org.Krusgraph|Krusgraph.Modeler] [--bump patch|minor|major] [--version 1.0.N]
                              [--previous <last .nupkg> | --previous-ref <git ref of the last upload>]
                              [--out workload/build/package] [--skip-tests] [--upload]

Runs in Azure Cloud Shell after `git clone` (python3 and git; pytest for step 3: `pip install --user pytest pillow`).
Python's standard library otherwise; no network unless --upload and a documented API.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "workload" / "scripts" / "build_package.py"
MANIFEST_DIR = "workload/Workload/Manifest"
DEFAULT_OUT = ROOT / "workload" / "build" / "package"
# The repository's tests for the manifest and the package (step 3)
MANIFEST_TESTS = ("tests/test_workload_manifest.py", "tests/test_n201_manifest.py", "tests/test_workload_build.py",
                  "tests/test_workload_publish.py")
DOC = "docs/WORKLOAD-PACKAGE-UPDATES.md"

# No documented upload API (docs/WORKLOAD-PACKAGE-UPDATES.md, read 17 November 2026): the Fabric REST API's admin
# Workloads group has only List Workloads and the workload assignments
# (https://learn.microsoft.com/en-us/rest/api/fabric/admin/workloads), Learn describes the upload only in the portal
# ("Go to OneLake catalog > Govern > Configurations > Workloads. Select Upload workload.", tutorial-publish-workload,
# updated 2026-09-29), and the toolkit's own DeployToAzureWebApp.ps1 says "Automatic manifest deployment is not yet
# implemented." (microsoft/fabric-extensibility-toolkit dacab1b, line 419). When one is documented this becomes
# {"url": ..., "method": "POST", "resource": ..., "role": ..., "source": <the Learn page and its date>}.
UPLOAD_API: dict | None = None

_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class StopError(RuntimeError):
    """A step that must not go on; the message says what to do."""


def load_build():
    """workload/scripts/build_package.py as a module, unchanged (the one way the repository builds the package)."""
    spec = importlib.util.spec_from_file_location("krusgraph_build_package", BUILD_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ the version ----------------------------------------

def parse_version(v: str) -> tuple[int, int, int]:
    m = _VERSION.match(v or "")
    if not m:
        raise StopError(f"{v!r} is not a version like 1.0.12")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def bump(v: str, part: str = "patch") -> str:
    major, minor, patch = parse_version(v)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise StopError(f"--bump must be patch, minor or major, not {part!r}")


def next_version(previous: str | None, part: str, floor: str | None, explicit: str | None = None) -> str:
    """The version to build: --version as given (it must be above the last package), else one `part` above the last
    package and never below `floor` (1.0.<commits>, the number the build has always used)."""
    if explicit:
        if previous and parse_version(explicit) <= parse_version(previous):
            raise StopError(f"--version {explicit} is not above the last package's {previous}; Fabric needs a higher one")
        parse_version(explicit)
        return explicit
    candidates = []
    if previous:
        candidates.append(bump(previous, part))
    if floor:
        candidates.append(floor)
    if not candidates:
        raise StopError("No last package and no git history: pass --version 1.0.N (above the version in Fabric)")
    return max(candidates, key=parse_version)


# ------------------------------------------------------------------ reading a package ----------------------------------

def package_files(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def package_version(files: dict[str, bytes]) -> str | None:
    for name, data in files.items():
        if name.endswith(".nuspec") and "/" not in name:
            m = re.search(rb"<version>\s*([^<\s]+)\s*</version>", data)
            if m:
                return m.group(1).decode()
    return None


def newest_package(out_dir: Path, name: str, build=None) -> Path | None:
    """The highest-version <name>.<version>.nupkg in the output folder, or None."""
    found = []
    for p in Path(out_dir).glob(f"{name}.*.nupkg"):
        v = p.name[len(name) + 1:-len(".nupkg")]
        if _VERSION.match(v):
            found.append((parse_version(v), p))
    return max(found)[1] if found else None


def files_at_ref(build, ref: str, vals: dict) -> dict[str, bytes]:
    """The package's files as the manifest at a git ref would build them, with this build's values (name, app id, URL)."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            archive = subprocess.run(["git", "archive", ref, MANIFEST_DIR], cwd=ROOT, capture_output=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError) as e:
            raise StopError(f"--previous-ref {ref}: git could not read {MANIFEST_DIR} there ({e})") from None
        tar = Path(tmp) / "m.tar"
        tar.write_bytes(archive)
        import tarfile
        with tarfile.open(tar) as t:
            try:
                t.extractall(tmp, filter="data")
            except TypeError:                                   # Python before 3.11.4: no extraction filters
                t.extractall(tmp)
        return build.staged_files(vals, Path(tmp) / MANIFEST_DIR)


# ------------------------------------------------------------------ the diff -------------------------------------------

def _xml_lines(data: bytes) -> dict[str, str]:
    """element/attribute path -> value, for a short diff of WorkloadManifest.xml and the item XML files."""
    out: dict[str, str] = {}
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return {"(not valid XML)": hashlib.sha256(data).hexdigest()[:12]}

    def walk(el, path):
        tag = el.tag.split("}")[-1]
        here = f"{path}/{tag}"
        for k, v in el.attrib.items():
            out[f"{here}@{k}"] = v
        text = (el.text or "").strip()
        if text and len(el) == 0:
            out[here] = text
        for child in el:
            walk(child, here)
    walk(root, "")
    return out


def _flat_json(value, path="") -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(value, dict):
        for k, v in value.items():
            out.update(_flat_json(v, f"{path}.{k}" if path else k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.update(_flat_json(v, f"{path}[{i}]"))
    else:
        out[path] = json.dumps(value, ensure_ascii=False)
    return out


@dataclass
class Diff:
    lines: list[str] = field(default_factory=list)
    identity: bool = False          # the workload name or an item type changed (reserved for good at the first upload)

    def add(self, line: str) -> None:
        self.lines.append(line)


def _short(v: str | None, n: int = 70) -> str:
    if v is None:
        return "(none)"
    return v if len(v) <= n else v[: n - 1] + "…"


def manifest_diff(old: dict[str, bytes] | None, new: dict[str, bytes]) -> Diff:
    """What changes for Fabric between two packages, in short lines a person reads before uploading."""
    d = Diff()
    if old is None:
        d.add("No last package to compare with (pass --previous <file> or --previous-ref <git ref>): everything is new.")
        return d
    ov, nv = package_version(old), package_version(new)
    if ov != nv:
        d.add(f"Version: {ov} -> {nv}")
    # the workload and the items (XML)
    for name in sorted({n for n in old.keys() | new.keys() if n.startswith("BE/") and n.endswith(".xml")}):
        a = _xml_lines(old[name]) if name in old else {}
        b = _xml_lines(new[name]) if name in new else {}
        if name not in old:
            d.add(f"{name}: new file")
        elif name not in new:
            d.add(f"{name}: removed")
        for key in sorted(a.keys() | b.keys()):
            if a.get(key) != b.get(key):
                label = {"@WorkloadName": "Workload name", "@TypeName": "Item type", "/AppId": "Frontend Entra app",
                         "/Url": "Frontend URL", "/Version": "Version (manifest)"}
                what = next((v for k, v in label.items() if key.endswith(k)), key)
                if what in ("Workload name", "Item type"):
                    d.identity = True
                if what == "Version (manifest)":
                    continue                                    # said once above
                d.add(f"{name.split('/')[-1]} {what}: {_short(a.get(key))} -> {_short(b.get(key))}")
    # Product.json and the texts (the Workload Hub page)
    for name in ("FE/Product.json", "FE/assets/locales/en-US/translations.json"):
        try:
            a = _flat_json(json.loads(old.get(name, b"{}")))
            b = _flat_json(json.loads(new.get(name, b"{}")))
        except ValueError:
            d.add(f"{name}: not valid JSON")
            continue
        changed = [k for k in sorted(a.keys() | b.keys()) if a.get(k) != b.get(k) and k != "version"]
        for k in changed[:12]:
            d.add(f"{name.split('/')[-1]} {k}: {_short(a.get(k))} -> {_short(b.get(k))}")
        if len(changed) > 12:
            d.add(f"{name.split('/')[-1]}: {len(changed) - 12} more changed fields")
    # images and other assets
    assets = sorted(n for n in old.keys() | new.keys() if n.startswith("FE/assets/") and not n.endswith(".json"))
    for n in assets:
        if n not in old:
            d.add(f"Image added: {n[len('FE/assets/'):]}")
        elif n not in new:
            d.add(f"Image removed: {n[len('FE/assets/'):]}")
        elif hashlib.sha256(old[n]).digest() != hashlib.sha256(new[n]).digest():
            d.add(f"Image changed: {n[len('FE/assets/'):]}")
    if len(d.lines) == (1 if ov != nv else 0):
        d.add("Nothing else changed in the manifest: an upload would only raise the version.")
    return d


# ------------------------------------------------------------------ checks ---------------------------------------------

def run_manifest_tests(runner: Callable[[list[str]], int] | None = None) -> tuple[bool, str]:
    """The repository's manifest tests (pytest). (ok, what was run). Missing pytest is a stop, not a pass."""
    if runner is None:
        if importlib.util.find_spec("pytest") is None:
            raise StopError("pytest is not installed, so the manifest tests cannot run. Install it "
                            "(`python3 -m pip install --user pytest pillow`) or pass --skip-tests to build without them.")

        def runner(cmd):
            return subprocess.run(cmd, cwd=ROOT).returncode
    tests = [t for t in MANIFEST_TESTS if (ROOT / t).exists()]
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests]
    return runner(cmd) == 0, " ".join(tests)


# ------------------------------------------------------------------ the upload -----------------------------------------

def portal_steps(path: Path, name: str, version: str, first_upload: bool) -> list[str]:
    """The Admin-portal steps (docs/WORKLOAD-DEV.md, section 6; docs/WORKLOAD-PUBLISH.md). Nothing is opened."""
    steps = [
        f"The package is {path}" + (" (in Cloud Shell: Manage files -> Download, that path)." if path else "."),
        "As a Fabric administrator, at https://app.fabric.microsoft.com: OneLake catalog -> Govern -> Workloads "
        "(on some tenants Govern -> Configurations -> Workloads).",
        (f"Upload workload -> choose the file. The dialog must name {name}; if it names anything else, cancel."
         if first_upload else f"{name} -> Upload -> choose the file (version {version})."),
        f"Activate it: the workload's page -> version {version} -> Activate. Reload the Fabric tab.",
        "Undo: activate the previous version again on the same page.",
    ]
    if name == "Krusgraph.Modeler":
        steps.insert(2, "Krusgraph.Modeler: the first upload asks you to confirm the name, and that cannot be undone. "
                        "Read docs/WORKLOAD-PUBLISH.md first.")
    return steps


def az_token(resource: str, run: Callable[[list[str]], str] | None = None) -> str:
    """A token for `resource` from the signed-in Azure CLI (Cloud Shell is signed in). Nothing is stored."""
    run = run or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
    try:
        out = run(["az", "account", "get-access-token", "--resource", resource, "--query", "accessToken", "-o", "tsv"])
    except (OSError, subprocess.CalledProcessError) as e:
        raise StopError(f"`az account get-access-token` failed ({e}); run `az login` first") from None
    token = (out or "").strip()
    if not token:
        raise StopError("az returned no token; run `az login` first")
    return token


def upload(path: Path, name: str, version: str, *, dry_run: bool, confirm: Callable[[str], str],
           http: Callable[..., int] | None = None, token: Callable[[str], str] | None = None,
           api: dict | None = None) -> str:
    """Only through a documented API (UPLOAD_API, from Microsoft's own page). Returns what happened, in words."""
    api = UPLOAD_API if api is None else api
    if not api:
        return (f"Not uploaded: Microsoft documents no API, CLI or PowerShell command that uploads a workload package "
                f"({DOC}), and this tool never calls the portal's own endpoints. Upload it by hand:")
    if dry_run:
        return f"Dry run: would send {path.name} with {api['method']} {api['url']} (as {api.get('role', 'the role the page names')})."
    typed = confirm(f"Type '{name} {version}' to upload {path.name} to {api['url']}: ")
    if typed.strip() != f"{name} {version}":
        return "Not uploaded: the confirmation did not match."
    bearer = (token or az_token)(api["resource"])
    status = (http or _http)(api["method"], api["url"], path.read_bytes(), {"Authorization": f"Bearer {bearer}",
                                                                          "Content-Type": "application/octet-stream"})
    if not 200 <= status < 300:
        raise StopError(f"The upload answered HTTP {status}; nothing was activated")
    return f"Uploaded {path.name} (HTTP {status}). Activate version {version} on the workload's page."


def _http(method: str, url: str, body: bytes, headers: dict) -> int:      # pragma: no cover - used only with UPLOAD_API
    import urllib.request
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status


# ------------------------------------------------------------------ the command ----------------------------------------

def main(argv=None, *, build=None, test_runner=None, confirm=input, out=print) -> int:
    build = build or load_build()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frontend-app-id", required=True, help="the workload Entra app's Application (client) ID")
    ap.add_argument("--name", default=build.WORKLOAD_NAME, help=f"{build.WORKLOAD_NAME} (default) or {build.PUBLISHED_NAME}")
    ap.add_argument("--bump", default="patch", choices=("patch", "minor", "major"), help="default patch")
    ap.add_argument("--version", help="this exact version instead of a bump (must be above the last package)")
    ap.add_argument("--previous", type=Path, help="the last package uploaded (.nupkg); default: the newest in --out")
    ap.add_argument("--previous-ref", help="or the git ref (tag, commit) whose manifest was uploaded last")
    ap.add_argument("--frontend-url", default=build.FRONTEND_URL)
    ap.add_argument("--offer-url", help="the live production Marketplace offer's page (Krusgraph.Modeler; see build_package.py)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output folder; default workload/build/package (git-ignored)")
    ap.add_argument("--skip-tests", action="store_true", help="build without the repository's manifest tests (not advised)")
    ap.add_argument("--upload", action="store_true", help="upload through a documented API, after a typed confirmation")
    ap.add_argument("--dry-run", action="store_true", help="with --upload: say what would be sent, send nothing")
    a = ap.parse_args(argv)
    try:
        name = build.check_name(a.name)
        # the last package: a file, a git ref, or the newest in the output folder
        previous_files = previous_label = None
        if a.previous and a.previous_ref:
            raise StopError("Pass --previous or --previous-ref, not both")
        if a.previous:
            if not a.previous.exists():
                raise StopError(f"--previous {a.previous} does not exist")
            previous_files, previous_label = package_files(a.previous), str(a.previous)
        elif not a.previous_ref:
            found = newest_package(a.out, name)
            if found:
                previous_files, previous_label = package_files(found), str(found)
        try:
            floor = build.default_version()
        except build.PackageError as e:
            if not a.version:
                out(f"Note: {e}")
            floor = None
        previous_version = package_version(previous_files) if previous_files else None
        if a.previous_ref:
            # the ref's manifest built with this build's values; its version is not known from git, so the floor rules
            previous_files = files_at_ref(build, a.previous_ref, build.values(a.frontend_app_id, "0.0.0", a.frontend_url, name))
            previous_label = f"the manifest at {a.previous_ref}"
        version = next_version(previous_version, a.bump, floor, a.version)

        # 1-3: build (build_package.check runs inside) and the manifest tests
        path = build.build(a.frontend_app_id, version, a.frontend_url, a.out, name=name, offer_url=a.offer_url)
        new_files = package_files(path)
        if a.previous_ref:                                      # git has no package version: name the ref instead
            previous_files[f"{name}.nuspec"] = f"<version>{a.previous_ref}</version>".encode()
        out(f"Built {path} ({path.stat().st_size} bytes): {name} {version}, item type {build.item_type(name)}.")
        out("Checked: the build's manifest checks passed (name, frontend URL and app id, images, Workload Hub fields).")
        if a.skip_tests:
            out("NOT checked: the repository's manifest tests were skipped (--skip-tests).")
        else:
            ok, ran = run_manifest_tests(test_runner)
            if not ok:
                path.unlink(missing_ok=True)
                raise StopError(f"The manifest tests failed ({ran}); the package was removed. Fix them, then build again.")
            out(f"Checked: the manifest tests passed ({ran}).")

        # 4: what changes for Fabric
        diff = manifest_diff(previous_files, new_files)
        out("")
        out(f"Changes against {previous_label or 'nothing'}:")
        for line in diff.lines:
            out(f"  - {line}")
        if diff.identity:
            out("  ! The workload name or an item type changed. Fabric keeps a name for good once uploaded; this needs "
                "Gustav's yes (label needs-gustav).")
        out("")

        # 5: upload, or the steps
        if a.upload:
            said = upload(path, name, version, dry_run=a.dry_run, confirm=confirm)
            out(said)
            if not said.startswith("Not uploaded") and not said.startswith("Dry run"):
                return 0
        else:
            out("Nothing was uploaded. To add it in Fabric:")
        for i, step in enumerate(portal_steps(path, name, version, first_upload=previous_files is None), 1):
            out(f"  {i}. {step}")
        if name == build.PUBLISHED_NAME:
            for gap in build.publishing_gaps({k: v for k, v in new_files.items() if k.startswith("FE/")}):
                out(f"Not ready for Microsoft's publishing review yet: {gap}.")
        return 0
    except (StopError, build.PackageError) as e:
        out(f"STOP: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
