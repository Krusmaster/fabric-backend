#!/usr/bin/env python3
"""The workload package for the hosted editor (n168, n176; docs/WORKLOAD-DEV.md, docs/WORKLOAD-PUBLISH.md).

Builds the NuGet package (.nupkg) that the founder uploads in Fabric (OneLake catalog -> Govern -> Workloads) from the
templates in workload/Workload/Manifest, with the frontend at https://workload.krusgraph.com. Python's standard library
only, so it runs in GitHub Actions and in Azure Cloud Shell without nuget, mono or npm. It does what the starter kit's
scripts/Build/BuildManifestPackage.ps1 does (items moved to the root, {{PLACEHOLDERS}} replaced, the nuspec's file
rules: *.xml -> BE, *.json -> FE, assets -> FE/assets) and writes the package the way `nuget pack` lays it out (the
nuspec at the root, [Content_Types].xml, _rels/.rels and the core-properties part).

It never uploads anything and never contacts Fabric, Entra or Azure. Two names are allowed (n176):

  Org.Krusgraph       the default: the founder's development workload, internal to the company tenant
  Krusgraph.Modeler   the permanent name chosen on 9 November 2026 (publisher part Krusgraph, workload part Modeler),
                      published to up to 20 selected tenants (docs/WORKLOAD-PUBLISH.md)

Every other Krusgraph.* name is refused: a Krusgraph.* name is reserved in the tenant for good at its first upload
(docs/WORKLOAD-FEASIBILITY.md, section 5, step 3). The item type is <name>.Model; the manifest, the nuspec, Product.json
and the item files all take the name from here, through the {{WORKLOAD_NAME}} placeholder, never written twice.

  workload/scripts/build-package --frontend-app-id <the workload app's Application (client) ID> [--version 1.0.N]
                                 [--name Krusgraph.Modeler] [--frontend-url https://workload.krusgraph.com]
                                 [--out workload/build/package]
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
WORKLOAD_NAME = "Org.Krusgraph"                 # the default: the founder's development path
PUBLISHED_NAME = "Krusgraph.Modeler"            # the permanent name (founder's decision, 9 November 2026)
NAMES = (WORKLOAD_NAME, PUBLISHED_NAME)
FRONTEND_URL = "https://workload.krusgraph.com"
# n195: the attestation link, Product.json productDetail.supportLink.certification.url. Microsoft's requirement 1.4.1
# ("Attestation Link in workload page is correct", publishing-requirements-workload on Learn, ms.date 24 February 2026)
# and its validator (microsoft/fabric-extensibility-toolkit-validator 78e17c3, Testcases_Workload.json) read the
# attestation URL from that field; WorkloadManifest.xml has no attestation element in the kit's WorkloadDefinition.xsd
# (dacab1b), so "AttestationUrl in the manifest" is this field. Only the published name points at the attestation page;
# Org.Krusgraph keeps the /it page it always had.
ATTESTATION_URL = "https://krusgraph.com/workload/attestation"
CERTIFICATION_URL = {WORKLOAD_NAME: "https://krusgraph.com/it", PUBLISHED_NAME: ATTESTATION_URL}
PUBLISHER = "Kruse Consulting AB"
# The Product.json links Microsoft's validator fetches (publishing-requirements-workload 1.2.1, 1.2.2, 1.3.1, 1.4.1,
# 1.4.5, 5.2.1): each must be an https URL. The license link must also be a Marketplace offer (1.3.1, 1.3.2); there is
# none yet, so that one is reported by publishing_gaps(), not refused.
SUPPORT_LINKS = ("terms", "privacy", "license", "certification", "documentation", "help")
MARKETPLACE_HOSTS = ("azuremarketplace.microsoft.com", "appsource.microsoft.com", "marketplace.microsoft.com")
# The validator's ImageValidator default sizes for icons and its banner size (78e17c3; tests/test_workload_manifest.py)
ICON_SIZES = {(n, n) for n in (16, 20, 24, 32, 40, 48, 64)}
BANNER_SIZE = (1920, 240)
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


def check_name(name: str) -> str:
    """Org.Krusgraph or Krusgraph.Modeler; any other name, a Krusgraph.* one above all, is refused."""
    if name in NAMES:
        return name
    if name.lower().startswith("krusgraph."):
        raise PackageError(f"{name} is a Krusgraph.* name other than {PUBLISHED_NAME}; its first upload would reserve it in "
                           f"the tenant for good. Only {PUBLISHED_NAME} (or {WORKLOAD_NAME}) is built")
    raise PackageError(f"--name must be {WORKLOAD_NAME} or {PUBLISHED_NAME}, not {name!r}")


def item_type(name: str, item: str = "Model") -> str:
    """The item type Fabric registers: <workload name>.<item>, e.g. Krusgraph.Modeler.Model."""
    return f"{check_name(name)}.{item}"


def values(frontend_app_id: str, version: str, frontend_url: str, name: str = WORKLOAD_NAME) -> dict:
    name = check_name(name)
    if not _GUID.match(frontend_app_id or ""):
        raise PackageError("--frontend-app-id must be the workload Entra app's Application (client) ID, a GUID")
    if frontend_app_id == "00000000-0000-0000-0000-000000000000":
        raise PackageError("--frontend-app-id is the starter kit's placeholder; use the workload app's own id")
    if not _VERSION.match(version):
        raise PackageError(f"--version must look like 1.0.12, not {version!r}")
    url = check_frontend_url(frontend_url)
    return {"WORKLOAD_NAME": name, "WORKLOAD_ID": name, "WORKLOAD_VERSION": version,
            "ATTESTATION_URL": CERTIFICATION_URL[name],
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
    name = check_name(vals["WORKLOAD_NAME"])
    workload_xml = files["BE/WorkloadManifest.xml"].decode()
    if f'WorkloadName="{name}"' not in workload_xml or f"<Url>{vals['FRONTEND_URL']}</Url>" not in workload_xml:
        raise PackageError(f"WorkloadManifest.xml does not name {name} and the hosted frontend URL")
    if f"<AppId>{vals['FRONTEND_APPID']}</AppId>" not in workload_xml:
        raise PackageError("WorkloadManifest.xml does not carry the workload app's id")
    if f'TypeName="{item_type(name)}"' not in files["BE/ModelItem.xml"].decode():
        raise PackageError(f"ModelItem.xml does not register the item type {item_type(name)}")
    other = [n for n in NAMES if n != name]
    for path, data in files.items():
        if not path.endswith((".xml", ".json")):
            continue
        rest = data.replace(name.encode(), b"")
        if any(n.encode() in rest for n in other):
            raise PackageError(f"{path} names {other[0]} in a {name} package; the name comes from the build only")
        found = re.search(rb"Krusgraph\.(?!com)[A-Za-z][A-Za-z.]*", rest.replace(b"Org.Krusgraph", b""))
        if found:
            raise PackageError(f"{path} names the workload {found.group().decode()}; only {name} may be used here")
        if b"localhost" in data:
            raise PackageError(f"{path} still points at localhost")
    product = files["FE/Product.json"]
    json.loads(product)
    if len(product) > 50 * 1024:
        raise PackageError("Product.json is over 50 KB")
    if name == PUBLISHED_NAME:
        check_publishing(files)


def _png_size(data: bytes) -> tuple[int, int] | None:
    if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _words(files: dict[str, bytes]) -> dict:
    return json.loads(files.get("FE/assets/locales/en-US/translations.json", b"{}"))


def check_publishing(files: dict[str, bytes]) -> None:
    """n195: what Microsoft's publishing review reads from Product.json and that we can fill truthfully, for
    Krusgraph.Modeler only (publishing-requirements-workload 1.2-1.4, 3.1, 5.2.1; manifest-product on Learn). Refused
    when missing: the publisher, the names and descriptions in en-US, the attestation link, https support links, the
    icons and banner at the validator's sizes, getting-started material. The Marketplace link is reported by
    publishing_gaps(), because no offer exists yet."""
    product = json.loads(files["FE/Product.json"])
    words = _words(files)
    detail = product.get("productDetail") or {}
    problems = []
    if detail.get("publisher") != PUBLISHER:
        problems.append(f"productDetail.publisher is {detail.get('publisher')!r}, not {PUBLISHER!r}")
    texts = {"displayName": product.get("displayName"), "description": product.get("description"),
             "productDetail.slogan": detail.get("slogan"), "productDetail.description": detail.get("description"),
             "createExperience.description": (product.get("createExperience") or {}).get("description")}
    for field, key in texts.items():
        if not key or not str(words.get(key, "")).strip():
            problems.append(f"{field} has no en-US text (key {key!r} in assets/locales/en-US/translations.json)")
    links = detail.get("supportLink") or {}
    for kind in SUPPORT_LINKS:
        url = (links.get(kind) or {}).get("url") or ""
        if not url.startswith("https://"):
            problems.append(f"productDetail.supportLink.{kind}.url is not an https URL: {url!r}")
    if (links.get("certification") or {}).get("url") != ATTESTATION_URL:
        problems.append(f"productDetail.supportLink.certification.url (the attestation link) must be {ATTESTATION_URL}")
    images = {"icon.name": ((product.get("icon") or {}).get("name"), ICON_SIZES),
              "favicon": (product.get("favicon"), ICON_SIZES),
              "productDetail.image.source": ((detail.get("image") or {}).get("source"), {BANNER_SIZE})}
    for i, card in enumerate((product.get("createExperience") or {}).get("cards") or []):
        images[f"createExperience.cards[{i}].icon.name"] = ((card.get("icon") or {}).get("name"), ICON_SIZES)
        images[f"createExperience.cards[{i}].icon_small.name"] = ((card.get("icon_small") or {}).get("name"), ICON_SIZES)
    for field, (ref, sizes) in images.items():
        size = _png_size(files.get("FE/" + (ref or ""), b""))
        if size is None:
            problems.append(f"{field} names no PNG in the package: {ref!r}")
        elif size not in sizes:
            problems.append(f"{field} ({ref}) is {size[0]}x{size[1]}, not one of " + ", ".join(f"{w}x{h}" for w, h in sorted(sizes)))
    if not (product.get("homePage") or {}).get("learningMaterials"):
        problems.append("homePage.learningMaterials is empty (1.4.2 getting started material)")
    if not detail.get("slideMedia"):
        problems.append("productDetail.slideMedia is empty (1.4.3 at a glance)")
    if problems:
        raise PackageError(f"{PUBLISHED_NAME} is not ready for Microsoft's publishing review: " + "; ".join(problems))


def publishing_gaps(files: dict[str, bytes]) -> list[str]:
    """What the package cannot fill truthfully yet; printed by the build, never refused (docs/WORKLOAD-PUBLISH.md)."""
    product = json.loads(files["FE/Product.json"])
    license_url = (((product.get("productDetail") or {}).get("supportLink") or {}).get("license") or {}).get("url", "")
    host = re.sub(r"^https://([^/]+).*$", r"\1", license_url)
    gaps = []
    if host not in MARKETPLACE_HOSTS:
        gaps.append(f"license link {license_url} is not a Microsoft Marketplace offer (requirements 1.3.1 and 1.3.2, "
                    "required at Preview): no offer exists yet")
    return gaps


def content_types(names) -> str:
    exts = sorted({n.rsplit(".", 1)[-1].lower() for n in names if "." in n.rsplit("/", 1)[-1]} | {"rels", "psmdcp"})
    kinds = {"rels": "application/vnd.openxmlformats-package.relationships+xml",
             "psmdcp": "application/vnd.openxmlformats-package.core-properties+xml"}
    defaults = "".join(f'<Default Extension="{e}" ContentType="{kinds.get(e, "application/octet")}" />' for e in exts)
    return ('<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            + defaults + "</Types>")


def build(frontend_app_id: str, version: str | None = None, frontend_url: str = FRONTEND_URL,
          out_dir: Path | None = None, manifest: Path = MANIFEST, name: str = WORKLOAD_NAME) -> Path:
    vals = values(frontend_app_id, version or default_version(), frontend_url, name)
    wname = vals["WORKLOAD_NAME"]
    files = staged_files(vals, manifest)
    check(files, vals)
    spec_name = f"{wname}.nuspec"
    spec = nuspec(vals, manifest)
    core_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{wname}/{vals['WORKLOAD_VERSION']}").hex
    core_name = f"package/services/metadata/core-properties/{core_id}.psmdcp"
    rels = ('<?xml version="1.0" encoding="utf-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Type="http://schemas.microsoft.com/packaging/2010/07/manifest" Target="/{spec_name}" Id="R1" />'
            f'<Relationship Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
            f'Target="/{core_name}" Id="R2" /></Relationships>')
    core = ('<?xml version="1.0" encoding="utf-8"?><coreProperties xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns="http://schemas.openxmlformats.org/package/2006/metadata/core-properties">'
            f"<dc:creator>Kruse Consulting AB</dc:creator><dc:description>A NuGet package that holds the manifests for the "
            f"{wname} workload.</dc:description><dc:identifier>{wname}</dc:identifier>"
            f"<version>{vals['WORKLOAD_VERSION']}</version><keywords></keywords>"
            "<lastModifiedBy>workload/scripts/build-package</lastModifiedBy></coreProperties>")
    out_dir = Path(out_dir or WORKLOAD / "build" / "package")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{wname}.{vals['WORKLOAD_VERSION']}.nupkg"
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
    ap.add_argument("--name", default=WORKLOAD_NAME,
                    help=f"{WORKLOAD_NAME} (default, the development workload) or {PUBLISHED_NAME} (the published one)")
    ap.add_argument("--version", help="the package version, 1.0.N; default 1.0.<commits on this checkout>")
    ap.add_argument("--frontend-url", default=FRONTEND_URL, help=f"default {FRONTEND_URL}")
    ap.add_argument("--out", type=Path, help="output folder; default workload/build/package (git-ignored)")
    a = ap.parse_args(argv)
    try:
        path = build(a.frontend_app_id, a.version, a.frontend_url, a.out, name=a.name)
    except PackageError as e:
        print(f"STOP: {e}", file=sys.stderr)
        return 1
    print(f"Built {path} ({path.stat().st_size} bytes): {a.name}, item type {item_type(a.name)}, "
          f"frontend {a.frontend_url.rstrip('/')}.")
    print("Nothing was uploaded. Upload it yourself in Fabric: OneLake catalog -> Govern -> Workloads -> Upload workload "
          "(docs/WORKLOAD-DEV.md, \"Hosted (no laptop)\").")
    if a.name == PUBLISHED_NAME:
        print(f"{PUBLISHED_NAME}: the first upload asks you to confirm the name, and that cannot be undone. "
              "Read docs/WORKLOAD-PUBLISH.md first.")
        print(f"Attestation link in Product.json: {ATTESTATION_URL} (it must answer before Microsoft's review).")
        with zipfile.ZipFile(path) as z:
            files = {n: z.read(n) for n in z.namelist() if n.startswith("FE/")}
        for gap in publishing_gaps(files):
            print(f"Not ready for Microsoft's publishing review yet: {gap}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
