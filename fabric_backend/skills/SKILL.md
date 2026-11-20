---
name: "krusgraph"
description: "Read-only command-line access to Krusgraph's engine: the keys and relationships of a set of tables with the rule behind each, those keys and links checked against the rows (counts only), the SAP pack's view of SAP-shaped tables, and which SAP order-to-cash analyses the data supports. JSON output, stable exit codes, works offline on synthetic samples. Never writes to Microsoft Fabric."
version: 0.8.0
category: database
tags: [microsoft-fabric, sap, data-modeling, relationships, data-quality, read-only]
commands:
  - name: check
    description: What this install can do (version, sources, sign-in state, exit codes). Offline; opens nothing.
  - name: relationships
    description: Keys and relationships inferred from names and types, with the rule behind each.
    options: ["--sample", "--folder", "--columns", "--odbc-from-env", "--schema", "--mermaid"]
  - name: plan
    description: The keys and links checked against the rows (uniqueness, nulls, orphans); counts only, never row values.
    options: ["--sample", "--folder", "--odbc-from-env", "--schema", "--max-items", "--strict"]
  - name: sap
    description: The SAP tables and links the SAP pack recognises, the missing tables and columns, and the traps.
    options: ["--sample", "--folder", "--columns", "--odbc-from-env", "--schema"]
  - name: analysis
    description: Which of ten SAP order-to-cash analyses the data supports, ranked by rules (no AI).
    options: ["--sample", "--folder", "--odbc-from-env", "--schema", "--max-items"]
  - name: skill
    description: Print this file.
---

# krusgraph

`krusgraph` runs Krusgraph's engine from a terminal. It reads tables (a synthetic sample, local CSV files, a columns
list, or a SQL endpoint you are already signed in to) and answers what keys and relationships they have, whether those
hold in the rows, what the SAP pack recognises, and which SAP analyses the data supports.

It does not manage Fabric workspaces or items (that is Microsoft's Fabric CLI, `fab`), and it never writes to Fabric.

## Install

From a clone of the repository: `pip install .` (Python 3.12+; no extra packages are needed for the samples, local
files and columns lists). Reading over ODBC also needs `pyodbc` and Microsoft ODBC Driver 18 for SQL Server.

## Try it (offline)

```bash
krusgraph check
krusgraph plan --sample sap --human
```

The `sap` sample is 17 SAP-shaped tables with a few made-up rows; it has one planted orphan (an order line whose order
header is missing), so `plan` reports `"passed": false` on purpose.

## Sources (pick one per command)

| Flag | What | Rows? |
| --- | --- | --- |
| `--sample sap` / `sap36` / `shop` | synthetic data in the package (`sap36`: 36 months, ~130 000 rows) | yes |
| `--folder DIR` | every `.csv` / `.xlsx` in DIR becomes a table (read into memory) | yes |
| `--columns FILE` | an INFORMATION_SCHEMA.COLUMNS export | no (names only) |
| `--odbc-from-env` | the ODBC connection string in the `FABRIC_ODBC` environment variable | yes |

`--schema NAME` picks the schema (letters, digits and `_` only). `plan` and `analysis` need rows; with `--columns`
they exit 4.

## Output

- JSON on stdout when stdout is not a terminal (or with `--json`); text with `--human`.
- Every JSON answer has `schema_version` (`krusgraph-cli/1`), `command`, `read_only: true` and `ok`.
- Success: `ok: true`, `source` (`kind`, `label`, `schema`, `tables`, `has_rows`) and `result`.
- Failure: `ok: false`, `exit_code` and `error` (`kind`, `message`, `hint`). Read `hint` and correct the call.

Results by command:

- `relationships`: `keys[]` (`table`, `columns`, `rule`), `relationships[]` (`source`, `columns`, `target`,
  `target_columns`, `rule`), `ambiguous[]`.
- `plan`: `passed`, `keys_failed`, `relationships_with_orphans`, `summary`, and `validation` with every key's and
  link's counts and `verdict`.
- `sap`: `summary`, `tables`, `relationships`, `not_applied`, `missing_tables`, `missing_columns`, `traps`.
- `analysis`: `summary` and `recommendations[]` (`analysis`, `name`, `readiness`, `score`, `because`, `missing`).

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | ok |
| 1 | unexpected error inside Krusgraph (a bug) |
| 2 | bad arguments or bad input |
| 3 | the source could not be opened (missing file, `FABRIC_ODBC` not set, `pyodbc` missing, sign-in failed) |
| 4 | the command counts rows and the source has none |
| 5 | refused on purpose: `--apply` (this command does not write to Fabric) |
| 6 | `plan --strict` only: a key is not unique or a link has orphans |

## Workflows

1. Look before acting: `krusgraph check --json`.
2. Model a source: `krusgraph relationships --folder ./export --json`, then `krusgraph plan --folder ./export --json`.
3. In CI: `krusgraph plan --odbc-from-env --schema sap --strict` fails the job when a key or link breaks.
4. SAP: `krusgraph sap --sample sap`, then `krusgraph analysis --sample sap36`.

## Safety (for agents)

- Read-only. There is no command that creates, changes or deletes anything in Fabric. `--apply` is refused with
  exit 5. To create an API, model, views or notebook, use the Krusgraph MCP server's `create_*` tools, which run as a
  dry run first and apply the server's own guards.
- Never pass a connection string, password or token as an argument: there is no flag for one. Put the connection
  string in `FABRIC_ODBC` (docs/LOCAL.md); it is never printed, and error messages are redacted.
- Against a connection only read queries run (`SELECT` with counts and aggregates); `plan` answers with counts and
  verdicts, never a row value, and `analysis` with counts, months and document-type codes.
- No telemetry, no network use except the ODBC connection you configured, no subprocesses, no files written.
- Do not add customer data to issues or examples; use the synthetic samples.
