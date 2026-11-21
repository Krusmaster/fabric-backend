"""SRC3 (21 November 2026, hotfix): /sources, /sources/salesforce and /sources/dynamics365 returned 500 in production.

sources_page.py did `import yaml` to read the pack manifests, but PyYAML is in the `test` extra only; the image installs
`.[server]` (Dockerfile), so the page module failed to import there while every test passed. The manifests are now read
by pack_manifest.parse(), which needs no YAML library. These tests keep it so:

- parse() gives what yaml.safe_load gives, for every manifest in the repository;
- in a fresh interpreter where the packages only the `test` extra installs cannot be imported, every module the site
  loads imports and every public page (PUBLIC_PAGES, the three source pages among them) renders without a 5xx.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from fabric_backend import pack_manifest

ROOT = Path(__file__).resolve().parents[1]


def _test_only_modules() -> list[str]:
    """Import names of the packages in the `test` extra that the `server` extra does not install."""
    extras = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["optional-dependencies"]
    name = lambda req: re.split(r"[\[<>=!~; ]", req, maxsplit=1)[0].lower()
    server = {name(r) for r in extras["server"]}
    imports = {"pyyaml": "yaml", "pytest-xdist": "xdist"}
    return sorted(imports.get(n, n.replace("-", "_")) for n in (name(r) for r in extras["test"]) if n not in server)


def test_yaml_is_one_of_the_blocked_modules():
    assert {"yaml", "sqlglot", "pytest"} <= set(_test_only_modules())


@pytest.mark.parametrize("pack", pack_manifest.available())
def test_parse_reads_every_manifest_as_yaml_does(pack):
    yaml = pytest.importorskip("yaml")
    text = pack_manifest.path(pack).read_text(encoding="utf-8")
    assert pack_manifest.parse(text) == yaml.safe_load(text)


def test_parse_refuses_what_is_not_the_layout():
    with pytest.raises(ValueError):
        pack_manifest.parse("id: sap\n  - not json at all: [\n")


SCRIPT = r'''
import sys
for m in sys.argv[1].split(","):
    sys.modules[m] = None                          # `import m` now raises ImportError, as in the server image
import importlib
from starlette.testclient import TestClient
from fabric_backend import server, sources_page, pages
from fabric_backend.discovery import PUBLIC_PAGES
import os
os.environ.update(PRODUCT_NAME="Krusgraph", MCP_PUBLIC_URL="https://krusgraph.test/mcp", CONTACT_EMAIL="hello@krusgraph.test")
for s in sources_page.SOURCES:                     # the demo modules the page imports by name
    importlib.import_module("fabric_backend." + s["demo"])
bad = []
with TestClient(server.build_app()) as c:
    for p in sorted(set(PUBLIC_PAGES) | {"/sources", "/sources/salesforce", "/sources/dynamics365"}):
        r = c.get(p)
        if r.status_code >= 500:
            bad.append(f"{p} {r.status_code}")
print("BAD:" + ";".join(bad) if bad else "OK")
'''


def test_every_public_page_renders_with_only_the_server_extra():
    env = {k: v for k, v in os.environ.items() if k != "MCP_PUBLIC_URL"} | {"PYTHONPATH": str(ROOT)}   # set after import, as test_src1 does
    r = subprocess.run([sys.executable, "-c", SCRIPT, ",".join(_test_only_modules())], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-3000:]
    assert r.stdout.strip().splitlines()[-1] == "OK", r.stdout[-3000:] + r.stderr[-3000:]
