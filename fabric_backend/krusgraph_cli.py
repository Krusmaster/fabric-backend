"""krusgraph: Krusgraph's own capabilities as a read-only command for agents and people (round CL1, docs/CLI.md).

  krusgraph check                              what this install can do: version, sources, sign-in state, read-only
  krusgraph relationships --sample sap         keys and relationships, with the rule behind each (plan_backend)
  krusgraph plan --sample sap                  the keys and links checked against the rows, counts only (validate_plan)
  krusgraph sap --sample sap                   the SAP tables and links the SAP pack recognises (sap_pack_draft)
  krusgraph analysis --sample sap36            which SAP analyses the data supports, by rules (analysis_plan)
  krusgraph skill                              the agent instructions (SKILL.md) this command ships with

The structure follows HKUDS/CLI-Anything's harness conventions (read as documentation, no code copied): every command
answers JSON (`--json`, the default when stdout is not a terminal) or text for a person (`--human`), introspection
first, stable exit codes, and a SKILL.md for agents. It complements Microsoft's Fabric CLI (`fab`), which manages
workspaces and items; this command only runs Krusgraph's engine.

Safety (docs/CLI.md, "Safety model"): nothing here writes to Fabric, starts a process or sends anything anywhere. A
source is a sample in the package, local files, or the ODBC connection string in the FABRIC_ODBC environment variable
(the local server's sign-in, docs/LOCAL.md); a connection string or token is never accepted as an argument and never
printed. Only counting queries run against a connection. `--apply` is refused (exit 5).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

from . import __version__

SCHEMA_VERSION = "krusgraph-cli/1"
PROG = "krusgraph"

# Stable exit codes (docs/CLI.md and SKILL.md list them; tests/test_cl1_cli.py pins them).
OK, FAILED, USAGE, SOURCE, NEEDS_ROWS, REFUSED, CHECKS_FAILED = 0, 1, 2, 3, 4, 5, 6
EXIT_CODES = {
    OK: "ok",
    FAILED: "unexpected error inside Krusgraph (a bug: report it without customer data)",
    USAGE: "bad arguments or bad input (a typo, an unknown table, a file in the wrong shape)",
    SOURCE: "the source could not be opened (no such file or folder, FABRIC_ODBC not set, pyodbc missing, sign-in failed)",
    NEEDS_ROWS: "the command counts rows and the source has none (a columns list): use --sample, --folder or --odbc-from-env",
    REFUSED: "refused on purpose: this command does not write to Fabric (--apply)",
    CHECKS_FAILED: "plan --strict only: the answer is complete and a key or a link failed its check",
}

SAMPLES = {
    "sap": "the small synthetic SAP demo: 17 SAP-shaped tables, a few rows each (fabric_backend/sap_demo.py)",
    "sap36": "the 36-month synthetic SAP demo, about 130 000 rows, generated in memory (fabric_backend/sap_demo36.py)",
    "shop": "the synthetic shop schema: seven tables (fabric_backend/seed.py)",
}

ODBC_ENV = "FABRIC_ODBC"
MAX_FOLDER_BYTES = 512 * 1024 * 1024          # a folder of CSV/xlsx is read into memory; past this, say so instead
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_SCHEMA_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")

WRITE_REFUSAL = ("krusgraph does not write to Fabric: every command here reads and answers. Creating an API, a model, "
                 "views or notebooks goes through the Krusgraph MCP server's create_* tools, which run as a dry run first "
                 "and apply the server's own guards. Nothing was changed.")


class CliError(Exception):
    def __init__(self, code: int, kind: str, message: str, hint: str = ""):
        super().__init__(message)
        self.code, self.kind, self.message, self.hint = code, kind, message, hint


# ------------------------------------------------------------------ redaction -------------------------------------------

_SECRET_PAIRS = re.compile(r"(?i)\b(pwd|password|secret|client_?secret|token|access_?token|accountkey|sig)\s*=\s*('[^']*'|\"[^\"]*\"|\{[^}]*\}|[^;\s,]*)")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")


def redact(text: str) -> str:
    """Whatever the source or a driver says goes through here before it is printed: the FABRIC_ODBC string itself,
    key=value secrets, bearer tokens and JWTs are replaced."""
    if not text:
        return text
    dsn = os.environ.get(ODBC_ENV) or ""
    if len(dsn) >= 8:
        text = text.replace(dsn, "[FABRIC_ODBC]")
    for name in ("FABRIC_TOKEN",):
        v = os.environ.get(name) or ""
        if len(v) >= 8:
            text = text.replace(v, "[redacted]")
    text = _SECRET_PAIRS.sub(lambda m: f"{m.group(1)}=[redacted]", text)
    text = _JWT.sub("[redacted]", text)
    return _BEARER.sub("Bearer [redacted]", text)


# ------------------------------------------------------------------ sources ---------------------------------------------

def _schema_arg(value: str | None) -> str | None:
    if value is None:
        return None
    if not _SCHEMA_NAME.match(value):
        raise CliError(USAGE, "bad_input", f"--schema {value!r} is not a plain schema name",
                       "letters, digits and _ only, starting with a letter or _ (dbo, sap, shop)")
    return value


def _existing(path: str, want_dir: bool) -> Path:
    if "\x00" in path:
        raise CliError(USAGE, "bad_input", "a path may not contain a NUL character")
    p = Path(path).expanduser()
    try:
        p = p.resolve(strict=True)
    except (OSError, RuntimeError):
        raise CliError(SOURCE, "not_found", f"{path} does not exist", "give the path to a local "
                       + ("folder of .csv/.xlsx files" if want_dir else "INFORMATION_SCHEMA.COLUMNS export (.csv)")) from None
    if want_dir and not p.is_dir():
        raise CliError(SOURCE, "not_found", f"{path} is not a folder")
    if not want_dir and not p.is_file():
        raise CliError(SOURCE, "not_found", f"{path} is not a file")
    return p


def _size_guard(files: list[Path], where: str) -> None:
    """Files are read into memory, and an .xlsx is a zip: count what it unpacks to, so a small file that expands to
    gigabytes is refused before it is opened."""
    import zipfile
    size = 0
    for f in files:
        if f.suffix.lower() == ".xlsx":
            try:
                with zipfile.ZipFile(f) as z:
                    size += sum(i.file_size for i in z.infolist())
            except (zipfile.BadZipFile, OSError):
                raise CliError(USAGE, "bad_input", f"{f.name} is not a readable .xlsx workbook") from None
        else:
            size += f.stat().st_size
    if size > MAX_FOLDER_BYTES:
        raise CliError(SOURCE, "too_large", f"the files at {where} hold {size // 2**20} MB unpacked, more than "
                       f"{MAX_FOLDER_BYTES // 2**20} MB", "point at a sample of the rows, or use --odbc-from-env")


def open_source(a):
    """(Source, label for the answer). Reads only; the only network use is the ODBC connection the user configured."""
    from .platforms import local
    schema = _schema_arg(a.schema)
    try:
        if a.sample:
            if a.sample == "shop":
                return local.sample_source()
            from . import sap_demo, sap_demo36
            s, execute = (sap_demo if a.sample == "sap" else sap_demo36).sqlite()
            return local.Source("sample", f"sample {a.sample}: {SAMPLES[a.sample]}", s, execute, "sqlite",
                                ["Synthetic SAP-shaped rows; every value is made up."])
        if a.folder:
            folder = _existing(a.folder, want_dir=True)
            _size_guard([f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in (".csv", ".xlsx")], str(folder))
            return local.folder_source(folder, schema or "data")
        if a.columns:
            path = _existing(a.columns, want_dir=False)
            _size_guard([path], str(path))
            return local.columns_source(path, schema or "dbo")
        if a.odbc_from_env:
            dsn = os.environ.get(ODBC_ENV, "")
            if not dsn.strip():
                raise CliError(SOURCE, "not_configured", f"{ODBC_ENV} is not set",
                               "set it in the environment the way docs/LOCAL.md says (the same string the local MCP server "
                               "uses); it is never accepted as an argument")
            return local.odbc_source(dsn, schema or "dbo")
    except CliError:
        raise
    except RuntimeError as e:                                       # pyodbc missing
        raise CliError(SOURCE, "not_installed", redact(str(e))) from None
    except (FileNotFoundError, PermissionError, IsADirectoryError) as e:
        raise CliError(SOURCE, "not_found", redact(str(e))) from None
    except ValueError as e:
        raise CliError(USAGE, "bad_input", redact(str(e))) from None
    except Exception as e:                                          # a driver's sign-in or network error, redacted
        raise CliError(SOURCE, "connection_failed", redact(f"{type(e).__name__}: {e}"),
                       "check the sign-in behind FABRIC_ODBC (docs/LOCAL.md)") from None
    raise CliError(USAGE, "no_source", "no source given",
                   "add one of --sample sap|sap36|shop, --folder DIR, --columns FILE or --odbc-from-env")


def _source_info(src) -> dict:
    return {"kind": src.kind, "label": redact(src.label), "schema": src.schema.schema, "tables": len(src.schema),
            "has_rows": src.has_data}


def _needs_rows(src, command: str) -> None:
    if not src.has_data:
        raise CliError(NEEDS_ROWS, "needs_rows", f"'{command}' counts rows and {src.label} has none",
                       "use --sample sap, --folder DIR (CSV files with rows) or --odbc-from-env")


def _plan(src):
    from .infer import plan
    return plan(src.schema)


# ------------------------------------------------------------------ commands --------------------------------------------

def cmd_check(a) -> dict:
    """Introspection, cheap and offline: nothing is opened, no sign-in is attempted, no token is read."""
    from . import analysis_plan
    return {
        "version": __version__,
        "python": sys.version.split()[0],
        "read_only": True,
        "writes_to_fabric": False,
        "network": f"none, except the ODBC connection in {ODBC_ENV} when --odbc-from-env is given",
        "telemetry": False,
        "samples": SAMPLES,
        "sources": {
            "sample": "--sample sap|sap36|shop (offline, in the package)",
            "folder": "--folder DIR: .csv/.xlsx files, one table each, read into memory",
            "columns": "--columns FILE: an INFORMATION_SCHEMA.COLUMNS export; names only, no rows",
            "odbc": f"--odbc-from-env: the connection string in {ODBC_ENV} (never as an argument)",
        },
        "sign_in": {
            f"{ODBC_ENV}_set": bool(os.environ.get(ODBC_ENV, "").strip()),
            "pyodbc_installed": _has_module("pyodbc"),
            "az_on_path": shutil.which("az") is not None,
            "note": "Only reported, never used to fetch a token here. The ODBC driver signs in as the string says.",
        },
        "commands": {name: spec["help"] for name, spec in COMMANDS.items()},
        "analysis_available": hasattr(analysis_plan, "recommend"),
        "exit_codes": {str(k): v for k, v in EXIT_CODES.items()},
        "skill": "krusgraph skill  (prints SKILL.md)",
    }


def _has_module(name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(name) is not None


def cmd_relationships(a) -> dict:
    src = a._src
    p = _plan(src)
    return {
        "summary": p.summary().splitlines()[0],
        "keys": [{"table": t, "columns": list(k), "rule": r} for t, (k, r) in p.keys.items()],
        "relationships": [{"source": r.source, "columns": list(r.source_cols), "target": r.target,
                           "target_columns": list(r.target_cols), "rule": r.rule} for r in p.relationships],
        "ambiguous": p.ambiguous,
        "mermaid": p.mermaid() if a.mermaid else None,
        "next": "krusgraph plan with the same source checks these against the rows",
    }


def cmd_plan(a) -> dict:
    from . import evidence
    src = a._src
    _needs_rows(src, "plan")
    p = _plan(src)
    out = evidence.validate(p, src.execute, max(1, min(int(a.max_items), 200)))
    keys_failed = [k for k in out["keys"] if str(k.get("verdict", "")).startswith(("not a key", "not unique"))]
    rels_failed = [r for r in out["relationships"] if r.get("orphans")]
    return {
        "summary": out["summary"],
        "passed": not keys_failed and not rels_failed,
        "keys_failed": len(keys_failed), "relationships_with_orphans": len(rels_failed),
        "validation": out,
        "note": "Counts and verdicts only, never a row value. Read-only.",
    }


def cmd_sap(a) -> dict:
    from . import sap_pack
    src = a._src
    p = _plan(src)
    return sap_pack.draft(p, source_name=src.schema.schema, export="none")


def cmd_analysis(a) -> dict:
    from . import analysis_plan
    src = a._src
    _needs_rows(src, "analysis")
    p = _plan(src)
    return analysis_plan.recommend(p, src.execute, None, None, max(1, min(int(a.max_items), 60)), "o2c", True)


def cmd_skill(a) -> dict:
    return {"path": "fabric_backend/skills/SKILL.md", "text": skill_text()}


def skill_text() -> str:
    return (Path(__file__).parent / "skills" / "SKILL.md").read_text(encoding="utf-8")


# ------------------------------------------------------------------ human text ------------------------------------------

def _human(command: str, src_info: dict | None, r: dict) -> str:
    lines = []
    if src_info:
        lines.append(f"source: {src_info['label']} (schema {src_info['schema']}, {src_info['tables']} tables)")
    if command == "check":
        lines += [f"krusgraph {r['version']} (Python {r['python']}): read-only, no telemetry",
                  f"network: {r['network']}",
                  f"{ODBC_ENV} set: {'yes' if r['sign_in'][f'{ODBC_ENV}_set'] else 'no'}; pyodbc: "
                  f"{'yes' if r['sign_in']['pyodbc_installed'] else 'no'}; az on PATH: {'yes' if r['sign_in']['az_on_path'] else 'no'}",
                  "samples: " + ", ".join(r["samples"]), "commands:"]
        lines += [f"  {n:<14} {h}" for n, h in r["commands"].items()]
        lines.append("try: krusgraph plan --sample sap")
    elif command == "relationships":
        lines.append(r["summary"])
        lines += [f"  key {k['table']}({', '.join(k['columns'])})  [{k['rule']}]" for k in r["keys"]]
        lines += [f"  {x['source']}.{'+'.join(x['columns'])} -> {x['target']}.{'+'.join(x['target_columns'])}  [{x['rule']}]"
                  for x in r["relationships"]]
        lines += [f"  ? {x['table']}.{x['column']} could point at {x['candidates']}" for x in r["ambiguous"]]
        if r.get("mermaid"):
            lines.append(r["mermaid"])
        lines.append("next: " + r["next"])
    elif command == "plan":
        v = r["validation"]
        lines.append(("PASSED: " if r["passed"] else "NEEDS A LOOK: ") + r["summary"])
        lines += [f"  key {k['table']}({', '.join(k['columns'])}): {k.get('verdict', '')}" for k in v["keys"]]
        lines += [f"  {x.get('source')}.{'+'.join(x.get('columns', []))} -> {x.get('target')}: {x.get('verdict', '')}"
                  for x in v["relationships"]]
        lines.append(r["note"])
    elif command == "sap":
        lines.append(r.get("summary", ""))
        lines.append("status: " + str(r.get("status", "")))
        for t in r.get("missing_tables", [])[:10]:
            lines.append(f"  missing: {t if isinstance(t, str) else t.get('table', t)}")
        for t in r.get("traps", [])[:10]:
            lines.append(f"  trap: {t if isinstance(t, str) else t.get('title', t)}")
    elif command == "analysis":
        lines.append(r.get("summary", ""))
        for e in r.get("recommendations", []):
            lines.append(f"  {e['analysis']} {e['name']}: {e['readiness']} (score {e['score']})")
    elif command == "skill":
        return r["text"]
    return "\n".join(str(x) for x in lines)


# ------------------------------------------------------------------ the parser ------------------------------------------

COMMANDS = {
    "check": {"fn": cmd_check, "source": False, "help": "what this install can do: version, sources, sign-in state (offline)",
              "examples": ["krusgraph check", "krusgraph check --json"]},
    "relationships": {"fn": cmd_relationships, "source": True,
                      "help": "keys and relationships with the rule behind each, from names and types (plan_backend)",
                      "examples": ["krusgraph relationships --sample sap", "krusgraph relationships --columns columns.csv --human",
                                   "krusgraph relationships --sample shop --mermaid"]},
    "plan": {"fn": cmd_plan, "source": True,
             "help": "the keys and links checked against the rows: uniqueness, nulls, orphans; counts only (validate_plan)",
             "examples": ["krusgraph plan --sample sap", "krusgraph plan --folder ./csv_export --schema data",
                          "FABRIC_ODBC=... krusgraph plan --odbc-from-env --schema dbo"]},
    "sap": {"fn": cmd_sap, "source": True,
            "help": "the SAP tables and links the SAP pack recognises, what is missing, the traps (sap_pack_draft)",
            "examples": ["krusgraph sap --sample sap", "krusgraph sap --columns sap_columns.csv"]},
    "analysis": {"fn": cmd_analysis, "source": True,
                 "help": "which SAP order-to-cash analyses the data supports, ranked by rules (analysis_plan)",
                 "examples": ["krusgraph analysis --sample sap36", "krusgraph analysis --sample sap --human"]},
    "skill": {"fn": cmd_skill, "source": False, "help": "print the agent instructions (SKILL.md)",
              "examples": ["krusgraph skill --human"]},
}


def _epilog(name: str) -> str:
    ex = "\n".join(f"  {e}" for e in COMMANDS[name]["examples"])
    codes = "\n".join(f"  {k}  {v}" for k, v in EXIT_CODES.items())
    return f"examples:\n{ex}\n\nexit codes:\n{codes}\n\nRead-only: nothing is written to Fabric. docs/CLI.md"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog=PROG, formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Krusgraph's engine from a terminal, for agents and people. Read-only; JSON when piped.",
        epilog="examples:\n  krusgraph check\n  krusgraph plan --sample sap\n  krusgraph relationships --sample sap --human\n\n"
               "exit codes:\n" + "\n".join(f"  {k}  {v}" for k, v in EXIT_CODES.items()) + "\n\ndocs/CLI.md; agents: krusgraph skill")
    ap.add_argument("--version", action="version", version=f"{PROG} {__version__}")
    sub = ap.add_subparsers(dest="command", required=True, metavar="COMMAND")
    for name, spec in COMMANDS.items():
        s = sub.add_parser(name, help=spec["help"], description=spec["help"], epilog=_epilog(name),
                           formatter_class=argparse.RawDescriptionHelpFormatter)
        out = s.add_mutually_exclusive_group()
        out.add_argument("--json", dest="output", action="store_const", const="json",
                         help="JSON on stdout (the default when stdout is not a terminal)")
        out.add_argument("--human", dest="output", action="store_const", const="human", help="text for a person")
        s.add_argument("--apply", action="store_true",
                       help="refused: krusgraph does not write to Fabric (exit 5); writes go through the MCP create_* tools")
        if spec["source"]:
            g = s.add_mutually_exclusive_group()
            g.add_argument("--sample", choices=sorted(SAMPLES), help="a synthetic sample in the package (offline)")
            g.add_argument("--folder", help="a local folder of .csv/.xlsx files, one table each")
            g.add_argument("--columns", help="a local INFORMATION_SCHEMA.COLUMNS export (names only, no rows)")
            g.add_argument("--odbc-from-env", action="store_true",
                           help=f"read the source over the ODBC connection string in {ODBC_ENV} (never given as an argument)")
            s.add_argument("--schema", help="the schema to read (default: the sample's, data for --folder, dbo otherwise)")
        if name in ("plan", "analysis"):
            s.add_argument("--max-items", type=int, default=60, help="the most checks or analyses listed (default 60)")
        if name == "plan":
            s.add_argument("--strict", action="store_true",
                           help="exit 6 when a key is not unique or a link has orphans (for CI jobs); the JSON is the same")
        if name == "relationships":
            s.add_argument("--mermaid", action="store_true", help="add the diagram in Mermaid")
        s.set_defaults(command=name)
    return ap


def _emit(payload: dict, mode: str, human: str | None = None, stream=None) -> None:
    stream = stream or sys.stdout
    if mode == "json":
        stream.write(redact(json.dumps(payload, indent=2, ensure_ascii=False, default=str)) + "\n")
    else:                                          # no terminal control characters from a file name or a value
        text = redact(human if human is not None else json.dumps(payload, indent=2, default=str))
        stream.write(_CONTROL.sub("?", text) + "\n")


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)            # argparse exits 2 on a usage error, with the usage on stderr
    mode = a.output or ("human" if sys.stdout.isatty() else "json")
    base = {"schema_version": SCHEMA_VERSION, "command": a.command, "read_only": True}
    src = None
    try:
        if a.apply:
            raise CliError(REFUSED, "refused_write", WRITE_REFUSAL,
                           "run the same command without --apply; to create something in Fabric use the MCP server's "
                           "create_* tools with dry_run=true first")
        spec = COMMANDS[a.command]
        if spec["source"]:
            src = open_source(a)
            a._src = src
        try:
            result = spec["fn"](a)
        finally:
            if src is not None and callable(getattr(src, "close", None)):
                src.close()
        info = _source_info(src) if src is not None else None
        payload = {**base, "ok": True, **({"source": info} if info else {}), "result": result}
        _emit(payload, mode, _human(a.command, info, result) if mode == "human" else None)
        if getattr(a, "strict", False) and not result.get("passed", True):
            return CHECKS_FAILED
        return OK
    except CliError as e:
        err = {"kind": e.kind, "message": redact(e.message), "hint": redact(e.hint)}
        code = e.code
    except Exception as e:                         # the engine's own input errors are the user's to fix; the rest is ours
        from .infer import PlanInputError
        if isinstance(e, (PlanInputError, ValueError, KeyError)):
            err, code = {"kind": "bad_input", "message": redact(str(e)), "hint": "check the source's tables and the arguments"}, USAGE
        else:
            err, code = {"kind": "internal", "message": redact(f"{type(e).__name__}: {e}"),
                         "hint": "a bug in Krusgraph; report it without customer data"}, FAILED
    payload = {**base, "ok": False, "exit_code": code, "error": err}
    if mode == "json":
        _emit(payload, "json")
    else:
        _emit(payload, "human", f"{PROG} {a.command}: {err['message']}" + (f"\n  hint: {err['hint']}" if err["hint"] else ""),
              stream=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
