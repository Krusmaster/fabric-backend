#!/usr/bin/env python3
"""Write THIRD_PARTY_NOTICES.md from the pinned versions in deploy/constraints.txt and the extras in pyproject.toml.

    python tools/third_party_notices.py            # rewrite THIRD_PARTY_NOTICES.md (asks PyPI for each package's metadata)
    python tools/third_party_notices.py --check    # exit 1 when the committed file differs from what would be written (for CI)
    python tools/third_party_notices.py --from-installed   # read the metadata of the packages installed here instead of PyPI

What it reads, per package: the licence (the `License-Expression` field, else a short `License` field, else the
licence classifiers), the licence files the package ships, and its home page. Nothing is guessed: a package whose
metadata states no licence is written as "not stated in metadata", and the row says so. The text outside the tables
is in this file, so a run is reproducible and the committed file can be checked in CI.

The notices for what is vendored into the repository without a package manager (Pyodide, the two fonts) and for the
container image are written by hand below, from the licence files next to those assets (`fabric_backend/static/pyodide/README.txt`,
`fabric_backend/static/fonts/OFL-*.txt`) and the `Dockerfile`. Standard library only, no dependencies.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSTRAINTS = ROOT / "deploy" / "constraints.txt"
PYPROJECT = ROOT / "pyproject.toml"
OUT = ROOT / "THIRD_PARTY_NOTICES.md"
PYPI = "https://pypi.org/pypi/{name}/{version}/json"
PYPI_LATEST = "https://pypi.org/pypi/{name}/json"
# Classifier text -> SPDX-style short name. A classifier that names a family without the variant (BSD) stays a family.
CLASSIFIERS = {
    "MIT License": "MIT", "Apache Software License": "Apache-2.0", "BSD License": "BSD (variant not in the classifier)",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0", "Python Software Foundation License": "PSF-2.0", "ISC License (ISCL)": "ISC",
    "GNU Lesser General Public License v2 or later (LGPLv2+)": "LGPL-2.0-or-later", "GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "GNU General Public License v3 (GPLv3)": "GPL-3.0-only", "GNU Affero General Public License v3": "AGPL-3.0-only",
    "The Unlicense (Unlicense)": "Unlicense", "zlib/libpng License": "Zlib",
}
# Licences this repository does not take code from (CONTRIBUTING.md, "Reusing external code"). A dependency under one of
# them is a decision, not an accident: the script stops on it.
REFUSED = ("AGPL", "SSPL")


def pins(text: str) -> list[tuple[str, str]]:
    out = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s;]+)", line)
        if not m:
            raise SystemExit(f"deploy/constraints.txt: not a pin: {line!r}")
        out.append((m.group(1).lower().replace("_", "-"), m.group(2)))
    return out


def extras(text: str) -> dict[str, list[str]]:
    """extra name -> requirement names (without specifiers or extras), from pyproject.toml."""
    project = tomllib.loads(text)["project"]
    out = {}
    for extra, reqs in project.get("optional-dependencies", {}).items():
        out[extra] = [re.split(r"[\[<>=!~ ;]", r, maxsplit=1)[0].lower().replace("_", "-") for r in reqs]
    return out


def licence_from(info: dict) -> str:
    expr = (info.get("license_expression") or "").strip()
    if expr:
        return expr
    lic = (info.get("license") or "").strip()
    if lic and "\n" not in lic and len(lic) <= 60:
        return lic
    found = [CLASSIFIERS.get(c.split("::")[-1].strip(), c.split("::")[-1].strip())
             for c in info.get("classifiers", []) if c.startswith("License ::") and c != "License :: OSI Approved"]
    if found:
        return " / ".join(dict.fromkeys(found))
    if lic:
        return "licence text in metadata (see the package's licence file)"
    return "not stated in metadata"


def home_of(info: dict) -> str:
    urls = info.get("project_urls") or {}
    for key in ("Homepage", "Home", "homepage", "Source", "Source Code", "Repository", "Documentation", "Changelog"):
        if urls.get(key):
            return urls[key]
    return info.get("home_page") or ""


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "krusgraph-third-party-notices (tools/third_party_notices.py)"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)["info"]
    except urllib.error.HTTPError as e:
        raise SystemExit(f"PyPI answered {e.code} for {url}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise SystemExit(f"PyPI could not be reached ({e}); use --from-installed, or run where pypi.org is reachable") from e


def installed(name: str, version: str | None) -> dict:
    from importlib import metadata
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError as e:
        raise SystemExit(f"{name} is not installed here; install with: pip install -c deploy/constraints.txt -e '.[server,test,databricks]'") from e
    if version and dist.version != version:
        raise SystemExit(f"{name}: installed {dist.version}, pinned {version}")
    md = dist.metadata
    urls = {}
    for u in md.get_all("Project-URL") or []:
        k, _, v = u.partition(",")
        urls[k.strip()] = v.strip()
    return {"license_expression": md.get("License-Expression", ""), "license": md.get("License", ""),
            "classifiers": md.get_all("Classifier") or [], "license_files": md.get_all("License-File") or [],
            "project_urls": urls, "home_page": md.get("Home-page", ""), "summary": md.get("Summary", ""), "version": dist.version}


def row(name: str, version: str, info: dict) -> str:
    files = ", ".join(f"`{f}`" for f in (info.get("license_files") or [])) or "—"
    home = home_of(info)
    link = f"[{name}](https://pypi.org/project/{name}/{version}/)" if version else f"[{name}](https://pypi.org/project/{name}/)"
    home_cell = f"[{re.sub(r'^https?://', '', home).rstrip('/')}]({home})" if home else "—"
    return f"| {link} | {version or '(not pinned)'} | {licence_from(info)} | {files} | {home_cell} |"


HEAD = """# Third-party notices

What Krusgraph's server image and its optional extras are built from, with each package's licence as its own metadata
states it. Generated by `tools/third_party_notices.py` from `deploy/constraints.txt` (the image's exact versions) and the
extras in `pyproject.toml`; regenerate after a pin changes, and `python tools/third_party_notices.py --check` fails when
this file is stale. Krusgraph itself is MIT (`LICENSE`). Nothing here is legal advice: the licence files inside each
package govern, and every package below ships its own (`License-File` column) in its `.dist-info` directory when
installed.

Rules for taking code into this repository, as opposed to depending on a package, are in `CONTRIBUTING.md` under
"Reusing external code": a verified licence file at a pinned commit, notices preserved, no AGPL or SSPL code.

## The server image (`deploy/constraints.txt`)

Installed into `python:3.12-slim-bookworm` by the `Dockerfile` with `pip install -c deploy/constraints.txt ".[server]"`;
CI installs the same pins. Versions are exact.

| Package | Version | Licence (from metadata) | Licence files in the package | Home |
| --- | --- | --- | --- | --- |
"""

EXTRAS_HEAD = """
## Extras that are not in the image (`pyproject.toml`)

Installed only where someone asks for them: `[databricks]` for the Databricks adapter, `[test]` for the test suite,
`[deploy]`, `[sql]` and `[mcp]` for the local tools. Not pinned, so the licence is the one on the package's current
PyPI release when this file was generated, and no version is written.

| Package | Extras | Licence (from metadata) | Licence files in the package | Home |
| --- | --- | --- | --- | --- |
"""

VENDORED = """
## Vendored into the repository (no package manager)

| What | Where | Version | Licence | Notice |
| --- | --- | --- | --- | --- |
| Pyodide (CPython compiled to WebAssembly, for `/check` in the browser) | `fabric_backend/static/pyodide/` | 0.27.7, unmodified, from the npm package `pyodide@0.27.7` and the release archive | Mozilla Public License 2.0 | `fabric_backend/static/pyodide/README.txt` names the files and their SHA-256 sums; `pyodide-lock.json` says the bundle carries CPython 3.12.7 (PSF licence) and the `sqlite3` wheel Pyodide builds from CPython's module over SQLite |
| Fredoka (variable font) | `fabric_backend/static/fonts/fredoka-var.woff2` | — | SIL Open Font License 1.1 | `fabric_backend/static/fonts/OFL-Fredoka.txt` (Copyright 2016 The Fredoka Project Authors) |
| Nunito (variable font) | `fabric_backend/static/fonts/nunito-var.woff2` | — | SIL Open Font License 1.1 | `fabric_backend/static/fonts/OFL-Nunito.txt` (Copyright 2014 The Nunito Project Authors) |

## The container image

| Component | Source | Licence |
| --- | --- | --- |
| `python:3.12-slim-bookworm` | the official Docker image (`Dockerfile`, `FROM`) | Python: the PSF licence; Debian bookworm: the licences of its packages (`/usr/share/doc/*/copyright` in the image) |
| `msodbcsql18` (ODBC Driver 18 for SQL Server) | `packages.microsoft.com`, installed with `ACCEPT_EULA=Y` in the `Dockerfile` | Microsoft's end-user licence agreement for the driver, accepted at build time; not open source |
| `unixodbc-dev`, `gcc`, `curl`, `gnupg2`, `ca-certificates`, `apt-transport-https` | Debian bookworm packages, installed by the `Dockerfile` | each package's own licence, in `/usr/share/doc/<package>/copyright` inside the image; this script does not read the image, so no licence is written here |

## Licences this repository does not take code from

No dependency above is under the AGPL or the SSPL, and the script stops if one appears. Code under those licences is not
copied into this repository either (`CONTRIBUTING.md`, "Reusing external code"). Depending on a package and copying its
code are different acts: this file covers the first; the contributing rules cover the second.
"""


def build(from_installed: bool) -> str:
    pinned = pins(CONSTRAINTS.read_text(encoding="utf-8"))
    ex = extras(PYPROJECT.read_text(encoding="utf-8"))
    pinned_names = {n for n, _ in pinned}
    lines = [HEAD.rstrip("\n")]
    for name, version in pinned:
        info = installed(name, version) if from_installed else fetch(PYPI.format(name=name, version=version))
        lic = licence_from(info)
        if any(bad in lic.upper() for bad in REFUSED):
            raise SystemExit(f"{name}=={version} is under {lic}: not accepted (CONTRIBUTING.md, Reusing external code)")
        lines.append(row(name, version, info))
    unpinned: dict[str, list[str]] = {}
    for extra, names in ex.items():
        for n in names:
            if n not in pinned_names:
                unpinned.setdefault(n, []).append(extra)
    lines.append(EXTRAS_HEAD.rstrip("\n"))
    for name in sorted(unpinned):
        info = installed(name, None) if from_installed else fetch(PYPI_LATEST.format(name=name))
        files = ", ".join(f"`{f}`" for f in (info.get("license_files") or [])) or "—"
        home = home_of(info)
        home_cell = f"[{re.sub(r'^https?://', '', home).rstrip('/')}]({home})" if home else "—"
        lines.append(f"| [{name}](https://pypi.org/project/{name}/) | {', '.join(unpinned[name])} | {licence_from(info)} | {files} | {home_cell} |")
    lines.append(VENDORED)
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="compare with the committed file; exit 1 when it differs")
    ap.add_argument("--from-installed", action="store_true", help="read the installed packages' metadata instead of PyPI")
    args = ap.parse_args()
    text = build(args.from_installed)
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            import difflib
            sys.stdout.writelines(difflib.unified_diff(current.splitlines(True), text.splitlines(True), "THIRD_PARTY_NOTICES.md (committed)", "THIRD_PARTY_NOTICES.md (generated)"))
            print("THIRD_PARTY_NOTICES.md is stale: run python tools/third_party_notices.py", file=sys.stderr)
            return 1
        print("THIRD_PARTY_NOTICES.md is up to date")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
