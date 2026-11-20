"""CL1 (20 Nov 2026): the read-only `krusgraph` command for agents (fabric_backend/krusgraph_cli.py, docs/CLI.md).

JSON shape, exit codes, read-only by default, --apply refused, no secret in any output, offline runs on the samples,
and the installed-command shape (`python -m`, pyproject's console script, SKILL.md shipped as package data).
"""
from __future__ import annotations

import ast
import json
import os
import socket
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from fabric_backend import krusgraph_cli as cli

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "fabric_backend" / "krusgraph_cli.py"
SECRET = "Pwd=Sup3rS3cretValue;"
JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4eHh4eHh4eCJ9.c2lnbmF0dXJlc2lnbmF0dXJl"


def run(capsys, *argv):
    code = cli.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def run_json(capsys, *argv):
    code, out, err = run(capsys, *argv, "--json") if "--human" not in argv else run(capsys, *argv)
    return code, json.loads(out), err


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """No test here may reach the network: the CLI's sample and file paths are offline by design."""
    def refuse(*a, **k):
        raise AssertionError("krusgraph tried to open a network connection")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.delenv("FABRIC_ODBC", raising=False)
    monkeypatch.delenv("FABRIC_TOKEN", raising=False)


# ------------------------------------------------------------------ the JSON contract ----------------------------------

ENVELOPE = {"schema_version", "command", "read_only", "ok"}
RESULT_KEYS = {
    "relationships": {"summary", "keys", "relationships", "ambiguous", "next"},
    "plan": {"summary", "passed", "keys_failed", "relationships_with_orphans", "validation", "note"},
    "sap": {"summary", "tables", "relationships", "not_applied", "missing_tables", "missing_columns", "traps"},
    "analysis": {"summary", "recommendations"},
}


@pytest.mark.parametrize("command", sorted(RESULT_KEYS))
def test_each_command_answers_the_documented_json_on_the_sap_sample(capsys, command):
    code, d, _ = run_json(capsys, command, "--sample", "sap")
    assert code == cli.OK
    assert ENVELOPE <= set(d) and d["ok"] is True and d["read_only"] is True
    assert d["schema_version"] == "krusgraph-cli/1" and d["command"] == command
    assert d["source"] == {"kind": "sample", "label": d["source"]["label"], "schema": "sap", "tables": 17, "has_rows": True}
    assert RESULT_KEYS[command] <= set(d["result"]), set(d["result"])


def test_relationships_items_have_their_rule(capsys):
    _, d, _ = run_json(capsys, "relationships", "--sample", "sap")
    r = d["result"]
    assert len(r["keys"]) == 17 and r["relationships"]
    for x in r["relationships"]:
        assert set(x) == {"source", "columns", "target", "target_columns", "rule"} and x["rule"]
    for k in r["keys"]:
        assert set(k) == {"table", "columns", "rule"}


def test_plan_finds_the_planted_orphan_and_never_returns_row_values(capsys):
    _, d, _ = run_json(capsys, "plan", "--sample", "sap")
    r = d["result"]
    assert r["passed"] is False and r["relationships_with_orphans"] >= 1
    hit = [x for x in r["validation"]["relationships"] if x["source"] == "sap_vbap" and x["target"] == "sap_vbak"]
    assert hit and hit[0]["orphans"] == 1
    from fabric_backend import sap_demo
    names = {str(v) for _, (cols, kinds, rows) in sap_demo.tables().items() for r_ in rows for v in r_
             if isinstance(v, str) and len(v) > 6 and not v.isdigit()}
    text = json.dumps(r)
    assert not [v for v in names if v in text], "a row value reached plan's answer"


def test_analysis_on_the_36_month_sample_makes_forecasting_ready(capsys):
    _, d, _ = run_json(capsys, "analysis", "--sample", "sap36")
    by = {e["analysis"]: e for e in d["result"]["recommendations"]}
    assert by["A7"]["readiness"] == "ready"


def test_check_is_offline_and_lists_every_command_and_exit_code(capsys):
    code, d, _ = run_json(capsys, "check")
    r = d["result"]
    assert code == 0 and r["read_only"] is True and r["writes_to_fabric"] is False and r["telemetry"] is False
    assert set(r["commands"]) == set(cli.COMMANDS)
    assert set(r["exit_codes"]) == {str(c) for c in range(7)}
    assert r["sign_in"]["FABRIC_ODBC_set"] is False


def test_json_is_the_default_when_not_a_terminal_and_human_is_text(capsys):
    code, out, _ = run(capsys, "relationships", "--sample", "shop")      # pytest's stdout is not a TTY
    assert code == 0 and json.loads(out)["ok"] is True
    code, out, _ = run(capsys, "plan", "--sample", "shop", "--human")
    assert code == 0 and out.startswith("source: ") and "PASSED" in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)


# ------------------------------------------------------------------ exit codes -----------------------------------------

def test_exit_codes_are_stable(capsys, tmp_path):
    assert (cli.OK, cli.FAILED, cli.USAGE, cli.SOURCE, cli.NEEDS_ROWS, cli.REFUSED, cli.CHECKS_FAILED) == (0, 1, 2, 3, 4, 5, 6)
    with pytest.raises(SystemExit) as e:                                  # argparse: unknown command
        cli.main(["no-such-command"])
    assert e.value.code == 2
    capsys.readouterr()
    code, d, _ = run_json(capsys, "plan")                                  # no source
    assert code == 2 and d["ok"] is False and d["error"]["kind"] == "no_source" and d["exit_code"] == 2
    code, d, _ = run_json(capsys, "plan", "--folder", str(tmp_path / "missing"))
    assert code == 3 and d["error"]["kind"] == "not_found"
    code, d, _ = run_json(capsys, "plan", "--odbc-from-env")               # FABRIC_ODBC unset
    assert code == 3 and d["error"]["kind"] == "not_configured"
    cols = tmp_path / "columns.csv"
    cols.write_text("table_schema,table_name,column_name,data_type,ordinal_position\n"
                    "dbo,orders,order_id,int,1\ndbo,orders,customer_id,int,2\ndbo,customers,customer_id,int,1\n", encoding="utf-8")
    code, d, _ = run_json(capsys, "plan", "--columns", str(cols))          # names only, no rows
    assert code == 4 and d["error"]["kind"] == "needs_rows"
    code, d, _ = run_json(capsys, "relationships", "--columns", str(cols))
    assert code == 0 and d["source"]["has_rows"] is False
    code, _, _ = run(capsys, "plan", "--sample", "sap", "--strict", "--json")
    assert code == 6
    code, _, _ = run(capsys, "plan", "--sample", "shop", "--strict", "--json")
    assert code == 0


def test_errors_go_to_stderr_in_human_mode(capsys):
    code, out, err = run(capsys, "plan", "--odbc-from-env", "--human")
    assert code == 3 and out == "" and "FABRIC_ODBC is not set" in err and "hint:" in err


def test_bad_schema_names_are_refused_before_any_sql(capsys):
    for bad in ("dbo; DROP TABLE x", "a]b", "x'--", "../etc", ""):
        code, d, _ = run_json(capsys, "relationships", "--sample", "shop", "--schema", bad)
        assert code == 2 and d["error"]["kind"] == "bad_input", bad


# ------------------------------------------------------------------ read-only and --apply -------------------------------

@pytest.mark.parametrize("command", sorted(cli.COMMANDS))
def test_apply_is_refused_on_every_command_without_opening_the_source(capsys, monkeypatch, command):
    monkeypatch.setattr(cli, "open_source", lambda a: pytest.fail("--apply must be refused before the source is opened"))
    argv = [command, "--apply"] + (["--sample", "sap"] if cli.COMMANDS[command]["source"] else [])
    code, d, _ = run_json(capsys, *argv)
    assert code == cli.REFUSED == 5
    assert d["ok"] is False and d["error"]["kind"] == "refused_write" and "dry run" in d["error"]["message"]
    assert "Nothing was changed" in d["error"]["message"]


def test_the_module_cannot_write_start_processes_or_call_fabric():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported = {n.name.split(".")[0] for x in ast.walk(tree) if isinstance(x, ast.Import) for n in x.names} | \
               {(x.module or "").split(".")[0] for x in ast.walk(tree) if isinstance(x, ast.ImportFrom) and x.level == 0}
    assert not imported & {"subprocess", "requests", "urllib", "http", "socket", "httpx", "mcp"}
    relative = {x.module for x in ast.walk(tree) if isinstance(x, ast.ImportFrom) and x.level}
    assert not relative & {"deploy", "server", "mcp_server", "entra", "access", "create"}, relative
    calls = {f"{x.func.value.id}.{x.func.attr}" if isinstance(x.func, ast.Attribute) and isinstance(x.func.value, ast.Name)
             else getattr(x.func, "id", "") for x in ast.walk(tree) if isinstance(x, ast.Call)}
    assert not calls & {"os.system", "os.popen", "eval", "exec", "open"}, calls & {"os.system", "os.popen", "eval", "exec", "open"}
    src = MODULE.read_text(encoding="utf-8")
    assert ".write_text(" not in src and "dry_run=False" not in src and "api.fabric.microsoft.com" not in src


def test_no_flag_takes_a_secret():
    flags = {o for s in cli.build_parser()._subparsers._group_actions[0].choices.values() for a in s._actions for o in a.option_strings}
    assert not {f for f in flags if any(w in f for w in ("token", "password", "secret", "odbc=", "--dsn", "--connection"))}
    assert "--odbc-from-env" in flags


# ------------------------------------------------------------------ redaction ------------------------------------------

def test_a_failing_connection_never_prints_the_connection_string_or_a_token(capsys, monkeypatch):
    dsn = f"Driver={{ODBC Driver 18 for SQL Server}};Server=demo.example.com;UID=me;{SECRET}"
    monkeypatch.setenv("FABRIC_ODBC", dsn)
    monkeypatch.setenv("FABRIC_TOKEN", JWT)

    def boom(value, schema):
        raise ConnectionError(f"login failed for [{value}] Authorization: Bearer {JWT} token={JWT}")
    from fabric_backend.platforms import local
    monkeypatch.setattr(local, "odbc_source", boom)
    for mode in ("--json", "--human"):
        code, out, err = run(capsys, "plan", "--odbc-from-env", mode)
        assert code == 3
        both = out + err
        assert "Sup3rS3cret" not in both and JWT not in both and dsn not in both, both
        assert "[FABRIC_ODBC]" in both or "[redacted]" in both


def test_redact_covers_the_usual_shapes(monkeypatch):
    monkeypatch.setenv("FABRIC_ODBC", "Server=x;Pwd=abc12345;")
    text = cli.redact(f"Server=x;Pwd=abc12345; password='p a s s' Token=abc ClientSecret={{x;y}} Bearer abcdefghijkl {JWT}")
    for s in ("abc12345", "p a s s", "Token=abc ", "x;y", "abcdefghijkl", JWT):
        assert s not in text, s


def test_check_reports_sign_in_state_without_reading_a_token(capsys, monkeypatch):
    monkeypatch.setenv("FABRIC_ODBC", f"Server=x;{SECRET}")
    monkeypatch.setenv("FABRIC_TOKEN", JWT)
    import importlib
    deploy = importlib.import_module("fabric_backend.deploy")          # the package exports a function of the same name
    monkeypatch.setattr(deploy, "token_from_az", lambda *a, **k: pytest.fail("check must not fetch a token"))
    code, out, _ = run(capsys, "check", "--json")
    assert code == 0 and json.loads(out)["result"]["sign_in"]["FABRIC_ODBC_set"] is True
    assert "Sup3rS3cret" not in out and JWT not in out


# ------------------------------------------------------------------ local files ----------------------------------------

def test_a_folder_of_csv_files_is_read_and_checked(capsys, tmp_path):
    from fabric_backend import sap_demo
    for path in sap_demo.write_csv(tmp_path, "sap_"):
        pass
    csvs = [p for p in tmp_path.rglob("*.csv")]
    assert csvs
    code, d, _ = run_json(capsys, "plan", "--folder", str(csvs[0].parent))
    assert code == 0 and d["source"]["kind"] == "folder" and d["source"]["has_rows"] is True
    assert d["result"]["validation"]["keys"]


def test_a_file_where_a_folder_is_expected_is_a_source_error(capsys, tmp_path):
    f = tmp_path / "x.csv"
    f.write_text("a\n1\n", encoding="utf-8")
    code, d, _ = run_json(capsys, "plan", "--folder", str(f))
    assert code == 3
    code, d, _ = run_json(capsys, "sap", "--columns", str(tmp_path))
    assert code == 3


# ------------------------------------------------------------------ packaging and docs ---------------------------------

def test_console_script_and_skill_are_packaged():
    py = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert py["project"]["scripts"]["krusgraph"] == "fabric_backend.krusgraph_cli:main"
    assert py["project"]["dependencies"] == []
    assert "skills/*.md" in py["tool"]["setuptools"]["package-data"]["fabric_backend"]


def test_skill_md_has_front_matter_and_matches_the_cli(capsys):
    text = cli.skill_text()
    assert text.startswith("---\nname: \"krusgraph\"\n")
    front = text.split("---", 2)[1]
    for name in cli.COMMANDS:
        assert f"- name: {name}\n" in front, name
    for code in range(7):
        assert f"| {code} |" in text
    assert "--apply" in text and "FABRIC_ODBC" in text and "never writes to microsoft fabric" in text.lower()
    code, d, _ = run_json(capsys, "skill")
    assert code == 0 and d["result"]["text"] == text


def test_help_has_examples_and_exit_codes(capsys):
    for name in cli.COMMANDS:
        with pytest.raises(SystemExit) as e:
            cli.main([name, "--help"])
        assert e.value.code == 0
        out = capsys.readouterr().out
        assert "examples:" in out and "exit codes:" in out and "krusgraph " in out


def test_docs_and_draft_say_nothing_is_published():
    doc = (ROOT / "docs" / "CLI.md").read_text(encoding="utf-8")
    assert "34f519533bc175d2fe287ab8316b0dd99bb9cc43" in doc and "20 November 2026" in doc
    assert "microsoft/fabric-cli" in doc and "Safety model" in doc
    draft = (ROOT / "docs" / "drafts" / "cli-hub-entry.md").read_text(encoding="utf-8")
    assert draft.startswith("# DRAFT") and "not submitted" in draft and "What Gustav must approve" in draft
    entry = json.loads(draft.split("```json", 1)[1].split("```", 1)[0])
    assert {"name", "display_name", "version", "description", "requires", "homepage", "source_url", "install_cmd",
            "entry_point", "skill_md", "category", "contributors"} == set(entry)
    assert entry["entry_point"] == "krusgraph"


def test_the_server_does_not_import_the_cli():
    for f in ("server.py", "mcp_server.py", "workload_host.py"):
        assert "krusgraph_cli" not in (ROOT / "fabric_backend" / f).read_text(encoding="utf-8"), f


def test_python_dash_m_runs_offline_in_a_subprocess():
    env = {k: v for k, v in os.environ.items() if k not in ("FABRIC_ODBC", "FABRIC_TOKEN")}
    p = subprocess.run([sys.executable, "-m", "fabric_backend.krusgraph_cli", "plan", "--sample", "sap"],
                       capture_output=True, text=True, cwd=ROOT, env=env, timeout=120)
    assert p.returncode == 0, p.stderr
    d = json.loads(p.stdout)
    assert d["ok"] and d["result"]["relationships_with_orphans"] >= 1
    p = subprocess.run([sys.executable, "-m", "fabric_backend.krusgraph_cli", "--version"],
                       capture_output=True, text=True, cwd=ROOT, env=env, timeout=60)
    assert p.returncode == 0 and p.stdout.startswith("krusgraph ")


def test_an_xlsx_that_unpacks_past_the_cap_is_refused_before_it_is_read(capsys, tmp_path, monkeypatch):
    import zipfile
    monkeypatch.setattr(cli, "MAX_FOLDER_BYTES", 1024 * 1024)
    with zipfile.ZipFile(tmp_path / "big.xlsx", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", "0" * (2 * 1024 * 1024))       # 2 MB unpacked, a few KB on disk
    assert (tmp_path / "big.xlsx").stat().st_size < 100_000
    from fabric_backend.platforms import local
    monkeypatch.setattr(local, "folder_source", lambda *a, **k: pytest.fail("the workbook must not be opened"))
    code, d, _ = run_json(capsys, "plan", "--folder", str(tmp_path))
    assert code == 3 and d["error"]["kind"] == "too_large"


def test_human_text_carries_no_terminal_control_characters(capsys, monkeypatch):
    monkeypatch.setattr(cli, "_human", lambda *a: "evil \x1b[2J\x1b]0;title\x07 name")
    code, out, _ = run(capsys, "check", "--human")
    assert code == 0 and "\x1b" not in out and "\x07" not in out and "evil" in out
