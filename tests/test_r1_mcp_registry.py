"""R1: server.json, the MCP Registry entry for the hosted server, checked against the registry's own schema.

The schema (2025-12-11) is a copy in tests/fixtures/r1/ (see the README there), so the test needs no network.
What is checked beyond the schema: the name is in the domain namespace that is already published, the text makes no
claim the sales-word test rules out, there is no package entry while nothing is on PyPI, and docs/MCP-REGISTRY.md
names the things the founder needs. Nothing here publishes anything.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "tests" / "fixtures" / "r1" / "server.schema.json"


def _server_json():
    return json.loads((ROOT / "server.json").read_text(encoding="utf-8"))


def _validator():
    jsonschema = pytest.importorskip("jsonschema")                 # in deploy/constraints.txt, so CI always runs this
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator.check_schema(schema)
    return jsonschema.Draft7Validator(schema)


def test_server_json_is_valid_against_the_registry_schema():
    sj = _server_json()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert sj["$schema"] == schema["$id"]                          # the copy is the version server.json names
    errors = sorted(_validator().iter_errors(sj), key=lambda e: list(e.path))
    assert not errors, [f"{list(e.path)}: {e.message}" for e in errors]


@pytest.mark.parametrize("change, where", [
    ({"description": "x" * 101}, "description"),                  # the registry refuses more than 100 characters
    ({"name": "krusgraph"}, "name"),                              # a name needs namespace/name
    ({"remotes": [{"type": "http", "url": "https://krusgraph.com/mcp"}]}, "remotes"),
    ({"version": None}, "version"),
])
def test_the_schema_copy_rejects_what_the_registry_rejects(change, where):
    sj = {**_server_json(), **change}
    errors = list(_validator().iter_errors(sj))
    assert errors and any(where in [str(p) for p in e.path] or where in e.message for e in errors), where


def test_name_version_and_links():
    sj = _server_json()
    assert sj["name"] == "com.krusgraph/krusgraph"                 # the published name; a new name would be a second entry
    assert sj["title"] == "Krusgraph" and sj["websiteUrl"] == "https://krusgraph.com/"
    assert sj["repository"] == {"url": "https://github.com/Krusmaster/fabric-backend", "source": "github"}
    assert re.fullmatch(r"\d+\.\d+\.\d+", sj["version"])           # plain semver: the registry refuses ranges, and sorts by semver
    for remote in sj["remotes"]:
        assert remote["type"] == "streamable-http" and remote["url"].startswith("https://krusgraph.com/")
        assert "headers" not in remote                             # sign-in is OAuth, discovered from the server; no key to paste


def test_no_package_entry_while_nothing_is_on_pypi():
    # pyproject's `fabric-backend` is not on PyPI (checked 12 November 2026), and the registry verifies a package by
    # fetching it. A `packages` entry comes with the first PyPI release, together with the `mcp-name:` line in README.md.
    assert "packages" not in _server_json()


def test_description_makes_no_claim():
    d = _server_json()["description"].lower()
    for word in ("fast", "faster", "instant", "secure", "compliant", "gdpr", "iso", "certified", "partner", "endorsed",
                 "official", "ai-powered", "ai-driven", "seamless", "effortless", "best", "only", "unique"):
        assert not re.search(rf"\b{re.escape(word)}\b", d), word


def test_the_founder_doc_names_what_he_needs():
    doc = (ROOT / "docs" / "MCP-REGISTRY.md").read_text(encoding="utf-8")
    for needle in ("com.krusgraph/krusgraph", "registry.modelcontextprotocol.io", "github.com/mcp", "mcp-publisher login dns",
                   "mcp-publisher publish", "v=MCPv1; k=ed25519; p=", "private laptop", "two-factor", "6 December 2026",
                   "https://krusgraph.com/mcp/connect", "PUBLISHING.md"):
        assert needle in doc, needle
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/MCP-REGISTRY.md" in readme and "github.com/mcp" in readme
