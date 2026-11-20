# krusgraph: the command line for agents (round CL1)

`krusgraph` runs Krusgraph's own engine from a terminal, so an agent (Claude Code, Cursor, a CI job) or a person can
use it without the MCP server. It is read-only, answers JSON, and works offline on the synthetic SAP sample.

```bash
pip install .                       # from a clone; no extra packages for the samples and local files
krusgraph check
krusgraph plan --sample sap --human
```

The agent instructions are `fabric_backend/skills/SKILL.md` (`krusgraph skill` prints them). The code is
`fabric_backend/krusgraph_cli.py`; the tests are `tests/test_cl1_cli.py`. Status: experimental, verified by unit tests
and local runs on the synthetic samples on 20 November 2026; not run against a live Fabric SQL endpoint in this round.

## 1. What CLI-Anything is, and what we take from it

HKUDS/CLI-Anything (Apache-2.0) generates command-line "harnesses" that let agents drive software, and lists them in
a registry, CLI-Hub. Read as documentation on 20 November 2026 at commit `34f519533bc175d2fe287ab8316b0dd99bb9cc43`
(nothing installed, nothing run, no code copied):

- `README.md`: <https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/README.md>
- `CONTRIBUTING.md` (registry fields, standalone repositories):
  <https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/CONTRIBUTING.md>
- `cli-anything-plugin/HARNESS.md` (the harness rules):
  <https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/cli-anything-plugin/HARNESS.md>
- `registry.json` (79 entries on that date, 11 of them standalone repositories) and one example skill,
  `skills/cli-anything-jumpserver/SKILL.md`.
- CLI-Hub: <https://hkuds.github.io/CLI-Anything/hub/> (reads `registry.json` from their `main`).

The structure it asks for, and how `krusgraph` follows it:

| CLI-Anything | krusgraph |
| --- | --- |
| Every command supports `--json`; human-readable text for interactive use | `--json` (default when stdout is not a terminal) and `--human`; one envelope: `schema_version`, `command`, `read_only`, `ok`, `result` or `error` |
| Introspection commands (`info`, `status`) before acting | `krusgraph check`: version, sources, sign-in state, exit codes; offline |
| Fail loudly and clearly so agents can self-correct | stable exit codes 0-6 and `error.kind` / `message` / `hint` |
| `SKILL.md` with YAML front matter (name, description, commands) and agent guidance | `fabric_backend/skills/SKILL.md`, shipped in the package |
| Unit tests without the backend, plus subprocess tests of the installed command | `tests/test_cl1_cli.py`: JSON shape, exit codes, read-only, redaction, offline runs, and `python -m` subprocess runs |
| A registry entry in `registry.json`; a standalone repository submits a registry-only PR | a draft only: `docs/drafts/cli-hub-entry.md`, not submitted |

What we do not take: the stateful REPL and `repl_skin.py` (the harness rule says to copy that file; we copy nothing,
and one-shot commands suit agents and CI), the `cli-anything-<name>` package namespace, Click (the repository has no
runtime dependencies; `argparse` does the job), and session files (nothing is stored). Their example harness takes
`--password` as an argument; ours has no flag for a secret at all.

## 2. Commands

| Command | Engine function (MCP tool) | Needs rows |
| --- | --- | --- |
| `check` | none: introspection | no source |
| `relationships` | `infer.plan` (`plan_backend`) | no |
| `plan` | `evidence.validate` (`validate_plan`) | yes |
| `sap` | `sap_pack.draft` (`sap_pack_draft`) | no |
| `analysis` | `analysis_plan.recommend` (`analysis_plan`, round AP2) | yes |
| `skill` | prints SKILL.md | no source |

Sources: `--sample sap|sap36|shop` (in the package), `--folder DIR` (CSV/xlsx, one table each), `--columns FILE`
(an INFORMATION_SCHEMA.COLUMNS export, names only), `--odbc-from-env` (the connection string in `FABRIC_ODBC`, the
same one the local MCP server uses; docs/LOCAL.md). `plan --strict` exits 6 when a key or link fails, for CI.

Exit codes: 0 ok; 1 a bug in Krusgraph; 2 bad arguments or input; 3 the source could not be opened; 4 the command
needs rows and the source has none; 5 refused (`--apply`); 6 `plan --strict` found a failing key or link.

## 3. How it fits next to `fab` and the MCP server

- **Microsoft Fabric CLI (`fab`)**, <https://github.com/microsoft/fabric-cli> (MIT; README read on 20 November 2026 at
  `5b504195c63ef54c7382ca8e8a9d9759717f0ec5`): a file-system-style CLI for workspaces, items, OneLake files, tables and
  shortcuts (`ls`, `cd`, `cp`, `import`, `export`). `krusgraph` has none of that: no workspace or item command, no
  file transfer. Use `fab` to move and manage things; use `krusgraph` to ask what keys and links the tables have,
  whether they hold, and what the SAP pack and the analysis rules say. An agent can use both in one job.
- **The Krusgraph MCP server** (hosted, or `fabric-backend-mcp` locally): the same engine behind tools, with the
  guided path, cards, and the `create_*` tools that write to Fabric after a dry run. `krusgraph` is for terminals and
  CI where an MCP client is not there, and it stops before anything is created.
- **`fabric-backend`** (the older CLI, `fabric_backend/cli.py`): file-producing commands for people (`definition`,
  `rayfin`, `semantic-model`, `deploy`). It is unchanged. `krusgraph` is the agent-facing, read-only subset.

The server image is not affected: the new module is imported by nothing in `server.py`, adds no dependency, and
`deploy/constraints.txt` is unchanged.

## 4. Safety model

- **Read-only.** No command writes to Fabric. `--apply` exists on every command only to be refused (exit 5, with the
  pointer to the MCP `create_*` tools, which dry-run first and apply the server's allow-lists and guards). No
  undocumented Fabric endpoint is called; in fact no Fabric REST endpoint is called at all.
- **A future write command** must keep this contract: dry run by default with a digest of what would change printed
  in the answer; `--apply` only together with that digest; the same guards as the MCP `create_*` tools (the server's
  `_write_info`, allow-lists and consent); a test for each. None exists in this round.
- **Sign-in.** The only credentialed path is the ODBC connection string in `FABRIC_ODBC` (docs/LOCAL.md), used by the
  driver as written (for example `Authentication=ActiveDirectoryInteractive`). There is no flag for a connection
  string, password or token, so none lands in shell history. `check` only reports whether `FABRIC_ODBC` is set,
  whether `pyodbc` is installed and whether `az` is on the PATH; it reads no token and runs nothing.
- **Nothing leaks.** Every answer and error passes `redact()`: the `FABRIC_ODBC` value, `FABRIC_TOKEN`, key=value
  secrets (`Pwd=`, `Password=`, `token=`, …), bearer tokens and JWTs are replaced. `plan` returns counts and
  verdicts, never a row value.
- **No injection path.** No subprocess and no shell. `--schema` must be a plain identifier (`[A-Za-z_][A-Za-z0-9_]*`)
  before it reaches SQL; table and column names come from the source's own metadata and are quoted by the engine,
  as in the MCP tools.
- **Files.** Inputs are local paths, resolved and checked to be a file or a folder; a folder's CSV/xlsx are capped at
  512 MB in total. The CLI writes no file: answers go to stdout.
- **No telemetry**, and no network use except the ODBC connection the user configured.

The security review of this round's diff is in the pull request.

## 5. Publishing (not done)

Nothing is published: no PyPI upload, no pull request to HKUDS/CLI-Anything, no CLI-Hub entry. The draft entry and the
decisions it needs are in `docs/drafts/cli-hub-entry.md`.
