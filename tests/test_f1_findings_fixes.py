"""Round F1 (docs/FINDINGS-13NOV.md): the small fixes of the first-user test of 15 November 2026.

1. `fabric-backend-mcp --help` and `--version` answer and return; they used to start the stdio server, which waits on
   stdin and prints nothing (docs/LOCAL.md's install step runs --help).
2. The local server's first-run answers say what the reader, who is the operator there, does next: FABRIC_ODBC not set,
   the ODBC driver not loadable, the Azure CLI missing or signed out.
3. docs/LOCAL.md section 4 names every local tool the code has, and no tool it does not have as local.
4. The findings document names a round for every finding and makes none of the claims the repository forbids."""
from __future__ import annotations

import asyncio
import importlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from fabric_backend import errors, mcp_server

deploy = importlib.import_module("fabric_backend.deploy")        # the package's own `deploy` is the function

ROOT = Path(__file__).resolve().parents[1]
LOCAL = (ROOT / "docs" / "LOCAL.md").read_text(encoding="utf-8")
FINDINGS = (ROOT / "docs" / "FINDINGS-13NOV.md").read_text(encoding="utf-8")


# ------------------------------------------------------------------ 1. --help and --version ---------------------------

def test_help_prints_the_settings_and_does_not_start_the_server(monkeypatch, capsys):
    monkeypatch.setattr(mcp_server.mcp, "run", lambda *a, **k: pytest.fail("--help started the stdio server"))
    for flag in ("--help", "-h"):
        mcp_server.main([flag])
        out = capsys.readouterr().out
        for word in ("FABRIC_ODBC", "FABRIC_SOURCE_KIND", "FABRIC_SCHEMAS_ENABLED", "FABRIC_TOKEN", "KRUSGRAPH_PLATFORM", "docs/LOCAL.md"):
            assert word in out, word


def test_version_prints_one_line_and_does_not_start_the_server(monkeypatch, capsys):
    monkeypatch.setattr(mcp_server.mcp, "run", lambda *a, **k: pytest.fail("--version started the stdio server"))
    mcp_server.main(["--version"])
    out = capsys.readouterr().out.strip()
    assert out.startswith("fabric-backend-mcp") and "\n" not in out


def test_without_arguments_the_server_starts_as_before(monkeypatch):
    started = []
    monkeypatch.setattr(mcp_server.mcp, "run", lambda *a, **k: started.append(1))
    mcp_server.main([])
    assert started == [1]


def test_every_setting_the_help_names_is_one_the_code_reads():
    code = "".join((ROOT / "fabric_backend" / f).read_text(encoding="utf-8") for f in ("mcp_server.py", "platforms/local.py", "platforms/databricks.py"))
    for name in re.findall(r"^  ([A-Z_]{6,}) ", mcp_server.USAGE, flags=re.M):
        assert f'"{name}"' in code, name


# ------------------------------------------------------------------ 2. first-run answers ------------------------------

def test_no_connection_string_says_where_it_goes(monkeypatch):
    monkeypatch.delenv("FABRIC_ODBC", raising=False)
    monkeypatch.delenv("KRUSGRAPH_PLATFORM", raising=False)
    out = json.loads(mcp_server.list_tables("dbo"))
    assert out["kind"] == "server_config" and "FABRIC_ODBC is not set" in out["error"]
    assert "docs/LOCAL.md" in out["hint"] and '"env"' in out["hint"]
    assert "Contact the operator" not in out["hint"]              # locally the reader is the operator


def test_a_driver_that_cannot_be_loaded_is_a_configuration_answer_with_the_install_step(monkeypatch):
    monkeypatch.setenv("FABRIC_ODBC", "Driver={ODBC Driver 18 for SQL Server};Server=s;Database=d;PWD=super-secret-password")
    monkeypatch.delenv("KRUSGRAPH_PLATFORM", raising=False)

    def no_driver(dsn):
        raise ImportError("libodbc.so.2: cannot open shared object file: No such file or directory")
    monkeypatch.setattr(mcp_server._local, "odbc_connection", no_driver)
    text = mcp_server.list_tables("dbo")
    out = json.loads(text)
    assert out["kind"] == "server_config" and "libodbc.so.2" in out["error"]
    assert "ODBC Driver 18" in out["hint"] and "pyodbc" in out["hint"]
    assert "super-secret-password" not in text and "Traceback" not in text


def test_a_missing_azure_cli_is_a_sign_in_answer(monkeypatch):
    def missing(*a, **k):
        raise FileNotFoundError(2, "No such file or directory", "az")
    monkeypatch.setattr(deploy.subprocess, "run", missing)
    with pytest.raises(errors.PlatformError) as e:
        deploy.token_from_az()
    out = errors.explain(e.value, "workspace 'Sales'")
    assert out["kind"] == "sign_in" and "Azure CLI (az) was not found" in out["error"]
    assert "az login" in out["hint"] and "FABRIC_TOKEN" in out["hint"]
    assert "FileNotFoundError" not in json.dumps(out) and "Errno" not in json.dumps(out)


def test_a_signed_out_azure_cli_keeps_its_own_message(monkeypatch):
    def signed_out(cmd, **k):
        raise subprocess.CalledProcessError(1, cmd, stderr="ERROR: Please run 'az login' to setup account.\n")
    monkeypatch.setattr(deploy.subprocess, "run", signed_out)
    with pytest.raises(errors.PlatformError) as e:
        deploy.token_from_az()
    out = errors.explain(e.value)
    assert out["kind"] == "sign_in" and "Please run 'az login'" in out["error"] and "az login" in out["hint"]


def test_a_token_from_the_azure_cli_is_returned_as_before(monkeypatch):
    class R:
        stdout = "tok-123\n"
    seen = []
    monkeypatch.setattr(deploy.subprocess, "run", lambda cmd, **k: seen.append((cmd, k)) or R())
    assert deploy.token_from_az() == "tok-123"
    assert seen[0][0][:3] == ["az", "account", "get-access-token"] and seen[0][1]["check"] is True


# ------------------------------------------------------------------ 3. docs/LOCAL.md section 4 ------------------------

def _section_4() -> str:
    start = LOCAL.index("## 4. What works locally")
    return LOCAL[start:LOCAL.index("## 5. The 20-minute demo")]


def test_section_4_names_every_local_tool_and_their_number():
    tools = sorted(t.name for t in asyncio.run(mcp_server.mcp.list_tools()))
    section = _section_4()
    assert [t for t in tools if f"`{t}`" not in section] == []
    assert f"has {len(tools)} tools" in section


def test_section_4_calls_no_local_tool_hosted_only():
    tools = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    section = _section_4()
    hosted = section[section.index("The tools that need Fabric item ids"):]
    hosted = hosted[:hosted.index("connector\nonly")]
    named = set(re.findall(r"`([a-z_]+)`", hosted)) - {"answer_query_draft"}      # named there for its GraphQL form only
    assert "the GraphQL form of `answer_query_draft`" in hosted
    assert named and not (named & tools), sorted(named & tools)


def test_the_install_step_describes_what_help_does():
    assert "fabric-backend-mcp --help" in LOCAL and "prints the settings and returns" in LOCAL


# ------------------------------------------------------------------ 4. the findings document --------------------------

ROUNDS = ("n227", "n228", "n229", "n230", "new", "F2", "fixed in F1")


def _findings() -> list[str]:
    body = FINDINGS[FINDINGS.index("## 2. Findings"):FINDINGS.index("## 3. Fixed in this round")]
    return [b for b in re.split(r"\n(?=### )", body) if re.match(r"### [ABC]\d+", b)]


def test_every_finding_says_where_what_fix_and_round():
    found = _findings()
    assert len(found) >= 20
    for f in found:
        title = f.splitlines()[0]
        for field in ("**Where:**", "**Sees:**", "**Fix:**", "**Round:**"):
            assert field in f, (title, field)
        round_line = next(line for line in f.splitlines() if line.startswith("**Round:**"))
        assert any(r in round_line for r in ROUNDS), title


def test_the_findings_are_ranked_in_three_classes():
    for heading in ("### A", "### B", "### C"):
        assert heading in FINDINGS
    classes = [re.match(r"### ([ABC])", f).group(1) for f in _findings()]
    assert classes == sorted(classes)                       # blocks a tester, then misleads, then looks bad


def test_at_most_five_ideas_each_with_an_effort_in_rounds():
    ideas = FINDINGS[FINDINGS.index("## 4. Five ideas"):]
    heads = re.findall(r"^### Idea \d+.*$", ideas, flags=re.M)
    assert 1 <= len(heads) <= 5
    assert len(re.findall(r"\*\*Effort:\*\* \d+ rounds?", ideas)) == len(heads)


def test_the_document_makes_no_forbidden_claim():
    low = FINDINGS.lower()
    for phrase in ("sap-certified", "sap certified", "certified by", "endorsed by", "official partner", "times faster",
                   "x faster", "iso 27001 certified", "gdpr compliant", "gdpr-compliant"):
        assert phrase not in low, phrase
