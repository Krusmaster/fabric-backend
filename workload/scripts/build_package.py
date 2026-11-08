#!/usr/bin/env python3
"""The Org.Krusgraph workload package for the hosted editor (n168; docs/WORKLOAD-DEV.md, "Hosted (no laptop)").

Builds the NuGet package (.nupkg) that the founder uploads in Fabric (OneLake catalog -> Govern -> Workloads) from the
templates in workload/Workload/Manifest, with the frontend at https://workload.krusgraph.com. Python's standard library
only, so it runs in GitHub Actions and in Azure Cloud Shell without nuget, mono or npm. It does what the starter kit's
scripts/Build/BuildManifestPackage.ps1 does (items moved to the root, {{PLACEHOLDERS}} replaced, the nuspec's file
rules: *.xml -> BE, *.json -> FE, assets -> FE/assets) and writes the package the way `nuget pack` lays it out (the
nuspec at the root, [Content_Types].xml, _rels/.rels and the core-properties part).

It never uploads anything and never contacts Fabric, Entra or Azure. The workload name is Org.Krusgraph and nothing
else: a Krusgraph.* name is reserved in the tenant for good at its first upload (docs/WORKLOAD-FEASIBILITY.md, section 5,
step 3), so the script refuses it.

  workload/scripts/build-package --frontend-app-id <the workload app's Application (client) ID> [--version 1.0.N]
                                 [--frontend-url https://workload.krusgraph.com] [--out workload/build/package]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKLOAD = HERE.parent
MANIFEST = WORKLOAD / "Workload" / "Manifest"
WORKLOAD_NAME = "Org.Krusgraph"
FRONTEND_URL = "https://workload.krusgraph.com"
ITEM_NAMES = ("Model",)
VERIFIED_DOMAIN = "krusgraph.com"
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")
FIXED_TIME = (2026, 1, 1, 0, 0, 0)          # every entry gets this time, so the same inputs give the same bytes


class PackageError(ValueError):
    pass


def default_version(root: Path = WORKLOAD.parent) -> str:
    """1.0.<number of commits on this checkout>: grows with every commit on main, so each upload is a new version."""
    try:
        count = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=root, capture_output=True, text=True,
                               check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        raise PackageError("No git history here; pass --version 1.0.N (each upload needs a higher version)") from None
    return f"1.0.{count}"


def check_frontend_url(url: str) -> str:
    """https, a subdomain of the verified domain, at most one extra path segment (WORKLOAD-FEASIBILITY.md, section 2)."""
    m = re.fullmatch(r"https://([a-z0-9-]+(?:\.[a-z0-9-]+)*)(/[A-Za-z0-9_-]+)?/?", url.strip())
    if not m:
        raise PackageError(f"The frontend URL must be https://<host>[/<one segment>], not {url!r}")
    host = m.group(1)
    if not host.endswith("." + VERIFIED_DOMAIN):
        raise PackageError(f"The frontend must be on a subdomain of the verified domain {VERIFIED_DOMAIN}, not {host}")
    return url.strip().rstrip("/")


def values(frontend_app_id: str, version: str, frontend_url: str) -> dict:
    if not _GUID.match(frontend_app_id or ""):
        raise PackageError("--frontend-app-id must be the workload Entra app's Application (client) ID, a GUID")
    if frontend_app_id == "00000000-0000-0000-0000-000000000000":
        raise PackageError("--frontend-app-id is the starter kit's placeholder; use the workload app's own id")
    if not _VERSION.match(version):
        raise PackageError(f"--version must look like 1.0.12, not {version!r}")
    url = check_frontend_url(frontend_url)
    return {"WORKLOAD_NAME": WORKLOAD_NAME, "WORKLOAD_ID": WORKLOAD_NAME, "WORKLOAD_VERSION": version,
            "FRONTEND_APPID": frontend_app_id.lower(), "FRONTEND_URL": url, "FRONTEND_REDIRECT_URI": url + "/close",
            "ITEM_NAMES": ",".join(ITEM_NAMES), "WORKLOAD_HOSTING_TYPE": "FERemote", "ENVIRONMENT_DISPLAY_NAME_SUFFIX": ""}


def fill(text: str, vals: dict, where: str) -> str:
    def sub(m):
        if m.group(1) not in vals:
            raise PackageError(f"{where}: no value for {{{{{m.group(1)}}}}}")
        return vals[m.group(1)]
    return _PLACEHOLDER.sub(sub, text)


def staged_files(vals: dict, manifest: Path = MANIFEST) -> dict[str, bytes]:
    """{path inside the package: bytes}, after the starter kit's rules. The nuspec itself is not in the result."""
    root: dict[str, bytes] = {}
    for p in sorted(manifest.iterdir()):
        if p.is_file() and p.suffix in (".xml", ".json"):
            root[p.name] = p.read_bytes()
    for item in ITEM_NAMES:                 # items/<Name>Item/*.json|xml move to the root, as the kit's script does
        for p in sorted((manifest / "items" / f"{item}Item").glob("*")):
            if p.suffix in (".xml", ".json"):
                if p.name in root:
                    raise PackageError(f"Two manifest files named {p.name}")
                root[p.name] = p.read_bytes()
    out: dict[str, bytes] = {}
    for name, data in root.items():
        target = ("BE/" if name.endswith(".xml") else "FE/") + name
        out[target] = fill(data.decode("utf-8-sig"), vals, name).encode("utf-8")
    for p in sorted((manifest / "assets").rglob("*")):
        if p.is_file():
            rel = "FE/assets/" + p.relative_to(manifest / "assets").as_posix()
            data = p.read_bytes()
            if p.suffix == ".json":
                data = fill(data.decode("utf-8-sig"), vals, rel).encode("utf-8")
            out[rel] = data
    return out


def nuspec(vals: dict, manifest: Path = MANIFEST) -> str:
    text = (manifest / "ManifestPackage.nuspec").read_text(encoding="utf-8-sig")
    text = re.sub(r"<files>.*?</files>", "", text, flags=re.S)       # the files are placed by this script, not by nuget
    text = text.replace("<authors>author</authors>", "<authors>Kruse Consulting AB</authors>")
    text = text.replace("<owners>owner</owners>", "<owners>Kruse Consulting AB</owners>")
    return fill(text, vals, "ManifestPackage.nuspec")


def check(files: dict[str, bytes], vals: dict) -> None:
    """What must hold before the founder uploads: the name, the hosted URL, the app id, the sizes."""
    workload_xml = files["BE/WorkloadManifest.xml"].decode()
    if f'WorkloadName="{WORKLOAD_NAME}"' not in workload_xml or f"<Url>{vals['FRONTEND_URL']}</Url>" not in workload_xml:
        raise PackageError("WorkloadManifest.xml does not name Org.Krusgraph and the hosted frontend URL")
    if f"<AppId>{vals['FRONTEND_APPID']}</AppId>" not in workload_xml:
        raise PackageError("WorkloadManifest.xml does not carry the workload app's id")
    for name, data in files.items():
        if name.endswith((".xml", ".json")) and re.search(rb"Krusgraph\.(?!com)[A-Za-z]", data.replace(b"Org.Krusgraph", b"")):
            raise PackageError(f"{name} names a Krusgraph.* workload; only Org.Krusgraph may be used")
        if name.endswith((".xml", ".json")) and b"localhost" in data:
            raise PackageError(f"{name} still points at localhost")
    product = files["FE/Product.json"]
    json.loads(product)
    if len(product) > 50 * 1024:
        raise PackageError("Product.json is over 50 KB")


def content_types(names) -> str:
    exts = sorted({n.rsplit(".", 1)[-1].lower() for n in names if "." in n.rsplit("/", 1)[-1]} | {"rels", "psmdcp"})
    kinds = {"rels": "application/vnd.openxmlformats-package.relationships+xml",
             "psmdcp": "application/vnd.openxmlformats-package.core-properties+xml"}
    defaults = "".join(f'<Default Extension="{e}" ContentType="{kinds.get(e, "application/octet")}" />' for e in exts)
    return ('<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            + defaults + "</Types>")


def build(frontend_app_id: str, version: str | None = None, frontend_url: str = FRONTEND_URL,
          out_dir: Path | None = None, manifest: Path = MANIFEST) -> Path:
    vals = values(frontend_app_id, version or default_version(), frontend_url)
    files = staged_files(vals, manifest)
    check(files, vals)
    spec_name = f"{WORKLOAD_NAME}.nuspec"
    spec = nuspec(vals, manifest)
    core_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{WORKLOAD_NAME}/{vals['WORKLOAD_VERSION']}").hex
    core_name = f"package/services/metadata/core-properties/{core_id}.psmdcp"
    rels = ('<?xml version="1.0" encoding="utf-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Type="http://schemas.microsoft.com/packaging/2010/07/manifest" Target="/{spec_name}" Id="R1" />'
            f'<Relationship Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
            f'Target="/{core_name}" Id="R2" /></Relationships>')
    core = ('<?xml version="1.0" encoding="utf-8"?><coreProperties xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns="http://schemas.openxmlformats.org/package/2006/metadata/core-properties">'
            f"<dc:creator>Kruse Consulting AB</dc:creator><dc:description>A NuGet package that holds the manifests for the "
            f"{WORKLOAD_NAME} workload.</dc:description><dc:identifier>{WORKLOAD_NAME}</dc:identifier>"
            f"<version>{vals['WORKLOAD_VERSION']}</version><keywords></keywords>"
            "<lastModifiedBy>workload/scripts/build-package</lastModifiedBy></coreProperties>")
    out_dir = Path(out_dir or WORKLOAD / "build" / "package")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{WORKLOAD_NAME}.{vals['WORKLOAD_VERSION']}.nupkg"
    with tempfile.TemporaryDirectory() as tmp:
        partial = Path(tmp) / target.name
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as z:
            def put(name: str, data):
                info = zipfile.ZipInfo(name, FIXED_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, data)
            put("_rels/.rels", rels)
            put(spec_name, spec)
            for name in sorted(files):
                put(name, files[name])
            put(core_name, core)
            put("[Content_Types].xml", content_types(list(files) + [spec_name]))
        if partial.stat().st_size > 20 * 1024 * 1024:
            raise PackageError("The package is over 20 MB")
        shutil.move(str(partial), target)
    return target


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frontend-app-id", required=True, help="the workload Entra app's Application (client) ID")
    ap.add_argument("--version", help="the package version, 1.0.N; default 1.0.<commits on this checkout>")
    ap.add_argument("--frontend-url", default=FRONTEND_URL, help=f"default {FRONTEND_URL}")
    ap.add_argument("--out", type=Path, help="output folder; default workload/build/package (git-ignored)")
    a = ap.parse_args(argv)
    try:
        path = build(a.frontend_app_id, a.version, a.frontend_url, a.out)
    except PackageError as e:
        print(f"STOP: {e}", file=sys.stderr)
        return 1
    print(f"Built {path} ({path.stat().st_size} bytes): {WORKLOAD_NAME}, frontend {a.frontend_url.rstrip('/')}.")
    print("Nothing was uploaded. Upload it yourself in Fabric: OneLake catalog -> Govern -> Workloads -> Upload workload "
          "(docs/WORKLOAD-DEV.md, \"Hosted (no laptop)\").")
    return 0


if __name__ == "__main__":
    sys.exit(main())
