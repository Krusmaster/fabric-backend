#!/usr/bin/env python3
"""W12: a dry, offline validation of a built workload package (.nupkg) before the founder uploads it.

  python3 workload/scripts/validate_package.py <package.nupkg> [--require-xsd] [--report report.md]

It reads only the file it is given. It never uploads anything and never contacts Fabric, Entra, Azure or Microsoft's
validator service. What it checks, each against a rule that can be read offline:

  1. The package parts the starter kit's BuildManifestPackage.ps1 and `nuget pack` produce: the nuspec at the root,
     _rels/.rels, [Content_Types].xml, BE/WorkloadManifest.xml, BE/<Item>Item.xml, FE/Product.json, FE/<Item>Item.json.
  2. The name: the one constant WORKLOAD_NAME in build_package.py (or DEV_NAME), the same in the file name, the nuspec
     id, WorkloadName and the item type; [Publisher].[Workload] with the workload part at most 32 characters
     (docs/WORKLOAD-LISTING-AND-PAYMENT.md, [L1]); never another Krusgraph.* name.
  3. The version: 1.0.N, the same in the file name, the nuspec and WorkloadManifest.xml.
  4. The XML against the kit's schemas (workload/Workload/Manifest/*.xsd, starter kit dacab1b) with xmllint, the same way
     tests/test_workload_manifest.py does. Without xmllint the step is reported as not run; --require-xsd makes that a
     failure (CI passes it).
  5. Every rule build_package.check() holds a package to: the hosted frontend URL, the app id, no localhost, Product.json
     under 50 KB, slides, compatible item types and, for the published name, the publishing fields Microsoft's review reads
     (publisher, en-US texts, https support links, the attestation link, icon and banner sizes).
  6. Every assets/... path named in FE/*.json is in the package; no {{PLACEHOLDER}} is left; the package is under 20 MB.

What it cannot check offline is printed as "not checked here": whether Fabric registers the name, the live validator
(microsoft/fabric-extensibility-toolkit-validator) against a published workload, and the license link until the
production offer is live (publishing_gaps()). Exit code 0 when every check passes, 1 otherwise.
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
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("build_package", HERE / "build_package.py")
bp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bp)

MAX_WORKLOAD_PART = 32
_FILE = re.compile(r"^(?P<name>[A-Za-z][A-Za-z0-9]*\.[A-Za-z][A-Za-z0-9]*)\.(?P<version>\d+\.\d+\.\d+)\.nupkg$")
SCHEMAS = {"BE/WorkloadManifest.xml": "WorkloadDefinition.xsd"}
NOT_CHECKED = (
    "whether Fabric registers the name at upload (that is Microsoft's side, docs/MODELER-GO-LIVE.md step 1)",
    "Microsoft's validator against the published workload (docs/MODELER-GO-LIVE.md, after the upload)",
)


def _assets(x, found: set[str]) -> set[str]:
    if isinstance(x, dict):
        for v in x.values():
            _assets(v, found)
    elif isinstance(x, list):
        for v in x:
            _assets(v, found)
    elif isinstance(x, str) and x.startswith("assets/"):
        found.add(x)
    return found


def _xsd(files: dict[str, bytes], item_files: list[str]) -> tuple[str, list[str]]:
    """("passed" | "not run", problems): the XML parts against the kit's schemas with xmllint."""
    if not shutil.which("xmllint"):
        return "not run", []
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for x in bp.MANIFEST.glob("*.xsd"):
            # The kit's CommonTypesDefinitions.xsd writes (?: groups, which .NET accepts and the XSD regex language
            # (libxml2) does not; an XSD group never captures, so "(" matches the same strings.
            (tmp / x.name).write_text(x.read_text(encoding="utf-8").replace("(?:", "("), encoding="utf-8")
        targets = dict(SCHEMAS)
        targets.update({f: "ItemDefinition.xsd" for f in item_files})
        for part, xsd in targets.items():
            out = tmp / Path(part).name
            out.write_bytes(files[part])
            run = subprocess.run(["xmllint", "--noout", "--schema", str(tmp / xsd), str(out)], capture_output=True, text=True)
            if run.returncode != 0:
                problems.append(f"{part} does not validate against {xsd}: {run.stderr.strip()}")
    return "passed" if not problems else "failed", problems


def validate(package: Path, require_xsd: bool = False) -> dict:
    """{"name", "version", "sha256", "size", "passed": [...], "problems": [...], "gaps": [...], "xsd": str}."""
    package = Path(package)
    result = {"package": package.name, "passed": [], "problems": [], "gaps": [], "xsd": "not run",
              "not_checked": list(NOT_CHECKED)}
    data = package.read_bytes()
    result["sha256"] = hashlib.sha256(data).hexdigest()
    result["size"] = len(data)
    problems, passed = result["problems"], result["passed"]

    m = _FILE.match(package.name)
    if not m:
        problems.append(f"the file name {package.name!r} is not <Publisher>.<Workload>.<1.0.N>.nupkg")
        return result
    name, version = m.group("name"), m.group("version")
    result["name"], result["version"] = name, version
    try:
        bp.check_name(name)
    except bp.PackageError as e:
        problems.append(str(e))
        return result
    workload_part = name.split(".", 1)[1]
    if len(workload_part) > MAX_WORKLOAD_PART:
        problems.append(f"the workload part {workload_part!r} is over {MAX_WORKLOAD_PART} characters")
    passed.append(f"name {name} is one the build allows (the constant is {bp.WORKLOAD_NAME}); workload part "
                  f"{len(workload_part)} characters")

    if len(data) > 20 * 1024 * 1024:
        problems.append("the package is over 20 MB")
    with zipfile.ZipFile(package) as z:
        files = {n: z.read(n) for n in z.namelist()}
    items = [f"BE/{i}Item.xml" for i in bp.ITEM_NAMES]
    required = [f"{name}.nuspec", "_rels/.rels", "[Content_Types].xml", "BE/WorkloadManifest.xml", "FE/Product.json",
                *items, *[f"FE/{i}Item.json" for i in bp.ITEM_NAMES]]
    missing = [r for r in required if r not in files]
    if missing:
        problems.append("missing parts: " + ", ".join(missing))
        return result
    passed.append("the parts nuget and the kit's script lay out are all there")

    spec = files[f"{name}.nuspec"].decode("utf-8")
    manifest = files["BE/WorkloadManifest.xml"].decode("utf-8")
    if f"<id>{name}</id>" not in spec or f"<version>{version}</version>" not in spec:
        problems.append(f"the nuspec's id and version are not {name} {version}")
    if f"<Version>{version}</Version>" not in manifest:
        problems.append(f"WorkloadManifest.xml's Version is not {version}")
    url = re.search(r"<Url>([^<]+)</Url>", manifest)
    app = re.search(r"<AppId>([^<]+)</AppId>", manifest)
    if not url or not app:
        problems.append("WorkloadManifest.xml has no frontend Url or AppId")
        return result
    passed.append(f"version {version} is the same in the file name, the nuspec and the manifest")

    for path, blob in files.items():
        if path.endswith((".xml", ".json", ".nuspec", ".rels")) and b"{{" in blob:
            problems.append(f"{path} still holds a {{{{PLACEHOLDER}}}}")
    fe = {p: b for p, b in files.items() if p.startswith("FE/") and p.endswith(".json") and "/locales/" not in p}
    refs: set[str] = set()
    for path, blob in fe.items():
        try:
            _assets(json.loads(blob), refs)
        except ValueError as e:
            problems.append(f"{path} is not JSON: {e}")
    absent = sorted(r for r in refs if f"FE/{r}" not in files)
    if absent:
        problems.append("assets named but not in the package: " + ", ".join(absent))
    else:
        passed.append(f"all {len(refs)} assets named in FE/*.json are in the package")

    vals = {"WORKLOAD_NAME": name, "FRONTEND_URL": url.group(1), "FRONTEND_APPID": app.group(1)}
    try:
        bp.check_frontend_url(vals["FRONTEND_URL"])
        bp.check(files, vals)
        passed.append("build_package.check(): name, frontend URL, app id, sizes, slides, compatible types"
                      + (", publishing fields" if name == bp.WORKLOAD_NAME else ""))
    except bp.PackageError as e:
        problems.append(str(e))

    result["xsd"], xsd_problems = _xsd(files, items)
    problems.extend(xsd_problems)
    if result["xsd"] == "passed":
        passed.append("WorkloadManifest.xml and the item XML validate against the kit's XSDs (xmllint)")
    elif result["xsd"] == "not run" and require_xsd:
        problems.append("xmllint is not installed, and --require-xsd was given")

    if name == bp.WORKLOAD_NAME:
        result["gaps"] = bp.publishing_gaps({p: b for p, b in files.items() if p.startswith("FE/")})
    return result


def report(r: dict) -> str:
    lines = [f"# Workload package validation: {r['package']}", "",
             f"- Result: **{'PASSED' if not r['problems'] else 'FAILED'}** (offline; nothing was uploaded)",
             f"- SHA-256: `{r['sha256']}`", f"- Size: {r['size']} bytes", f"- XSD check: {r['xsd']}", "", "## Passed", ""]
    lines += [f"- {p}" for p in r["passed"]] or ["- nothing"]
    lines += ["", "## Problems", ""] + ([f"- {p}" for p in r["problems"]] or ["- none"])
    lines += ["", "## Known gaps (do not stop the upload)", ""] + ([f"- {g}" for g in r["gaps"]] or ["- none"])
    lines += ["", "## Not checked here", ""] + [f"- {n}" for n in r["not_checked"]]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package", type=Path)
    ap.add_argument("--require-xsd", action="store_true", help="fail when xmllint is not installed")
    ap.add_argument("--report", type=Path, help="also write the report (Markdown) to this file")
    a = ap.parse_args(argv)
    if not a.package.is_file():
        print(f"STOP: no file {a.package}", file=sys.stderr)
        return 1
    r = validate(a.package, a.require_xsd)
    text = report(r)
    print(text)
    if a.report:
        a.report.write_text(text, encoding="utf-8")
    return 0 if not r["problems"] else 1


if __name__ == "__main__":
    sys.exit(main())
