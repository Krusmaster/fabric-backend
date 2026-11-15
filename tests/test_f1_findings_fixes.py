"""F1 (15 November 2026), the small fixes of docs/FINDINGS-13NOV.md: the local server says what to do when it has no
Fabric token, and docs/LOCAL.md lists the local tools the code registers."""
import asyncio
import json
import re
import subprocess
from pathlib import Path

import pytest

from fabric_backend import errors, mcp_server
from fabric_backend.deploy import token_from_az          # the package's `deploy` is the function, not the module

ROOT = Path(__file__).resolve().parents[1]


def _az(monkeypatch, raises):
    def run(cmd, **kw):
        assert cmd[0] == "az"
        raise raises
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.delenv("FABRIC_TOKEN", raising=False)


def test_a_missing_azure_cli_is_a_sign_in_answer_that_names_both_ways_to_a_token(monkeypatch):
    _az(monkeypatch, FileNotFoundError(2, "No such file or directory", "az"))
    with pytest.raises(errors.PlatformError) as e:
        token_from_az()
    out = errors.explain(e.value, "workspace 'ws'")
    assert out["kind"] == "sign_in" and "not installed" in out["error"]
    assert "FABRIC_TOKEN" in out["hint"] and "az login" in out["hint"]
    assert "FileNotFoundError" not in json.dumps(out) and "Traceback" not in json.dumps(out)


def test_a_signed_out_azure_cli_quotes_what_it_said_without_a_token(monkeypatch):
    said = "ERROR: Please run 'az login' to setup account.\nAuthorization: Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.c2lnbmF0dXJl"
    _az(monkeypatch, subprocess.CalledProcessError(1, ["az"], stderr=said))
    with pytest.raises(errors.PlatformError) as e:
        token_from_az()
    out = errors.explain(e.value)
    assert out["kind"] == "sign_in" and "Please run 'az login'" in out["error"]
    assert "eyJhbGciOiJSUzI1NiJ9" not in json.dumps(out)                      # errors.scrub takes a token out of the quote


def test_the_local_create_backend_answers_sign_in_not_unexpected(monkeypatch):
    """What a first user of fabric-backend-mcp saw without the Azure CLI: kind 'unexpected', FileNotFoundError 'az'."""
    _az(monkeypatch, FileNotFoundError(2, "No such file or directory", "az"))

    def create(*a, token_provider=None, **k):
        token_provider()
    monkeypatch.setattr(mcp_server, "create", create)
    monkeypatch.setattr(mcp_server, "_execute_factory", lambda schema: (lambda sql: []))
    out = json.loads(mcp_server.create_backend("ws", "shop_lh", "shop_api", schema="shop"))
    assert out["kind"] == "sign_in" and "FABRIC_TOKEN" in out["hint"], out


def test_docs_local_lists_the_tools_the_local_server_registers():
    """docs/LOCAL.md said create_backend exists in the hosted connector only and left out review_plan."""
    text = (ROOT / "docs" / "LOCAL.md").read_text(encoding="utf-8")
    section = text.split("## 4. What works locally", 1)[1].split("\n## ", 1)[0]
    registered = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    missing = sorted(n for n in registered if f"`{n}`" not in section)
    assert not missing, missing
    hosted_only = section.split("The other tools that need Fabric item ids", 1)[1]
    wrongly_hosted_only = sorted(n for n in re.findall(r"`([a-z_]+)`", hosted_only) if n in registered - {"answer_query_draft"})
    assert not wrongly_hosted_only, wrongly_hosted_only
