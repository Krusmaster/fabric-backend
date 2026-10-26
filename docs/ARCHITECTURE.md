# Architecture: the engine and the platform adapters

Krusgraph is one engine behind several front ends, and since round n13 the platform-specific code sits behind one
boundary. The engine never talks to a platform; an adapter does, and hands the engine a schema and a connection.

```
front ends      server.py (hosted, Fabric only)   mcp_server.py (local stdio)   cli.py   demo_app.py (20-minute demo)
                        │                                   │                       │            │
adapters        platforms/fabric.py               platforms/local.py  (ODBC string, SQLite, files, columns list)
                        │   read a schema · run SQL in a dialect · build objects from a plan
engine          schema · infer · evidence · paths · graphs · drift · dictionary · dbt · privacy · answers ·
                silver · gold · compact · dialects
```

## The engine

Platform-neutral and without I/O: inference (K0–K5, R0–R4), validation as counting queries (`evidence.py`),
`join_path` (`paths.py`), `analyze_schema` and `suggest_relationships` (`graphs.py`), `plan_drift` (`drift.py`), the
data dictionary, the dbt tests, the personal-data rules, the question-to-SQL drafts, the silver and gold logic, and the
SQL dialects the engine writes its own queries in (`dialects.py`: T-SQL by default; SQLite reads the T-SQL through
`sqlite_sql`). `tests/test_architecture.py` checks on the source that no engine module imports a network, driver or
subprocess library, an adapter, a server or a front end. Four engine modules borrow from Fabric's pure format modules
(GraphQL field names, the TMDL type families, the notebook file format); the test lists those five imports, so a new one
is a decision.

## What an adapter implements

An adapter is a subclass of `Platform` in `fabric_backend/platforms/base.py`:

| | What | Where Fabric does it |
| --- | --- | --- |
| `name`, `title` | a short id and the platform's name | `fabric`, `Microsoft Fabric` |
| `dialect` | the `Dialect` its SQL is written in: quoting, the 64-bit count, `TOP`/`LIMIT`, three-part names | T-SQL |
| `connect(...)` | opens a connection: the engine's `execute(sql) -> list[dict]`, with `.dialect`, `.close()` and, when the platform lets the tools write, `.statement(sql)` for DDL; `platforms.connection()` builds one | ODBC Driver 18 with an Entra token, login and statement timeouts |
| `read_schema(execute, schema)` | a `Schema`: tables, columns with types, declared primary and foreign keys (they become K0 and R0) | `INFORMATION_SCHEMA` (the default in `base.py`) |
| `builders` | each kind of object it builds from a plan: the draft tool, the create tool, the module, the permission | `platforms/fabric.py` `BUILDERS`: API for GraphQL, semantic model, ontology, views, data agent, notebooks, drift monitor, Git export |
| `unsupported(tool)` | why a tool cannot run here, answered in the tools' error format (`kind: unsupported`) | none |

A builder's draft is pure: it turns a plan into files or SQL and calls nothing. A create tool is dry run by default,
creates or updates under a name and never deletes. Every new tool gets a title, correct annotations, the
`error`/`kind`/`hint` error format and tests.

## Adding a platform

1. `fabric_backend/platforms/<name>.py` with a `Platform` subclass and, if its SQL differs, a `Dialect` in
   `dialects.py` (cite the platform's documentation for each piece of syntax).
2. Tests with the platform mocked at its outermost seam (its REST client or driver), and a fixture of the shop seed in
   the platform's own metadata format that gives the same plan as Fabric.
3. Front ends choose the adapter; the hosted server stays Fabric-only until the platform has its own sign-in.
4. A line per tool with its status in the site's words (Tested end to end, Experimental, Draft only, Available when
   enabled by the operator, Planned) in the platform's doc page.

## Proof that the move changed nothing

`tests/golden/` holds every answer of the engine (shop schema and the eleven benchmark fixtures), of every hosted and
local tool (Fabric REST and the SQL endpoint doubled at `requests` and `pyodbc`), the tool listings, the hosted
server's instructions, the demo and the CLI, committed before the code moved (`tests/test_golden.py`). The move did
not touch those files. A deliberate change of an answer regenerates them (`KRUSGRAPH_UPDATE_GOLDEN=1`) in the same
commit, where the diff shows it.
