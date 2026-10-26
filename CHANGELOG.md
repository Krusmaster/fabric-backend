# Changelog

Dates are the commit dates on `main`. Versions are the `version` in `pyproject.toml`, mirrored in
`fabric_backend/__init__.py` and `server.json` (a test keeps them equal).

## Unreleased

- `lineage` (read-only, new): which GraphQL APIs, semantic models, views and data agents in the workspace build on a
  source's tables, from each object's own definition (`fabric_backend/lineage.py`), with what a change to one table
  reaches; `plan_drift` adds `impact` for the tables and columns a re-run would drop. `docs/MULTI-SOURCE.md` is the
  design note for a graph over several sources (not built).
- Local server against SQL Server on-prem: the constraint query joins INFORMATION_SCHEMA on the constraint schema too
  (two schemas may share constraint names) and leaves out foreign keys into another schema; `FABRIC_SOURCE_KIND=SQLServer`
  makes the Fabric-only drafts (Direct Lake semantic model, Fabric IQ ontology) answer with an explanation instead of
  wrong output. Tested against recorded INFORMATION_SCHEMA rows (spaces in names, composite declared keys, nvarchar(max),
  datetimeoffset, uniqueidentifier, computed columns, views); no SQL Server was available to run live.
- Claude plugin in `plugin/krusgraph/` (connector reference, skill `fabric-graph-backend`, commands plan / document /
  explain-schema, README, tests); not published; `docs/PUBLISHING.md` says how it is submitted as a plugin bundle.
- Lovable on Fabric without getting stuck: `docs/LOVABLE-END-TO-END.md` maps every step of the chain with its owner,
  whether it is automated and what blocks, with sources. New read-only tool `app_readiness` (keyless and unlinked types,
  write access, one introspection probe, "unknown" with the click path for what Fabric's API cannot read). `app_starter`
  adds the backend piece: a Supabase edge function (client credentials, secrets as Supabase secrets, mutations refused),
  the frontend helper, the per-user alternative and a checklist that starts with the app's own Entra registration.
  Dynamic client registration for agents outside Claude behind `KRUSGRAPH_DCR=1` (`fabric_backend/dcr.py`, design and
  alternatives in `docs/AUTH-DCR.md`): RFC 8414 metadata pointing at Entra, an RFC 7591 registration endpoint that
  answers the app's public client id for allow-listed redirect URIs, nothing stored; off by default, Claude's sign-in
  unchanged. Introspection cannot be set through the Fabric REST API (spec read 26 October 2026), so it stays a
  documented click.
- Review fixes in the stdio server and CLI: the CLI's `semantic-model` writes `schemaName` exactly when the lakehouse has
  schemas (it never did for a lakehouse); a Rayfin `metadata.json` source labels every command's output with the schema
  it read, and `plan`/`definition` accept it too; `views` prints `GO` between batches; a missing `FABRIC_ODBC` answers
  `server_config`; the ODBC string is parsed with braces, quotes and the Server/Database synonyms; `FABRIC_SOURCE_KIND`
  is read without case; a string without a database keeps the drafts' placeholders; every stdio tool opens one
  connection and closes it; a bad `views_schema` is `bad_input`; a failing `create_views` keeps the partial log and the
  warehouse hint (remote too); the stdio tools carry titles and read-only/destructive hints; a missing or wrong columns
  file is one line and exit 2 in the CLI.
- Live run of the consultant, graph and creating tools against the demo workspace (26 October 2026): read-only tools and
  dry runs, then `create_views` for real (schema and one view) and the two other creates answering `consent`; the tool answers, the docs page and the README say what has run live and what has not.
  Site texts updated to the current rules (K0–K5, R0–R4) and the twenty-two tools.

## 0.6.0 — 2026-10-26

- The local stdio server (`fabric-backend-mcp`) gets the SQL-only tools of the remote one over the connection in
  `FABRIC_ODBC`: `validate_plan`, `sample_rows`, `semantic_model_draft`, `join_path`, `data_dictionary`, `dbt_schema`,
  `analyze_schema`, `suggest_relationships` and `create_views` (dry run by default; the ODBC connection gained
  `statement` and `close`). The SQL endpoint host and database come from the ODBC string, the item kind from
  `FABRIC_SOURCE_KIND`, the schemas flag from `FABRIC_SCHEMAS_ENABLED`. The tools that need Fabric item ids stay remote.
- CLI commands from a columns CSV, nothing created: `semantic-model`, `join-path`, `dictionary`, `dbt`, `analyze`,
  `views`. Tested on the synthetic shop schema, including the views applied in SQLite.
- `suggest_relationships` treats an inclusion query that answers no rows as no evidence instead of failing.
- Graph theory on the plan (`fabric_backend/graphs.py`, pure Python, deterministic): certainty per rule (R0/confirmed 1.0,
  verified 0.9, R1 0.8, R2 0.6, R3/R4 0.5) and cost 1/certainty; `analyze_schema` (roles with the numbers behind them,
  degree/betweenness/PageRank, subject areas by label propagation, cycles and multi-path pairs, maximum spanning forest
  of active relationships); `suggest_relationships` (candidate columns ranked by name, type and triangular closure,
  checked against the data with an inclusion count in evidence.py; suggestions only). `join_path` adds the safest path
  next to the shortest; `semantic_model_draft` takes its active set and table roles from the graph; `data_dictionary`
  gets a roles/areas/ambiguity section.
- Review pass: the semantic model draft writes `schemaName` for a lakehouse created with schemas (the REST property
  `properties.defaultSchema`, lakehouse/definitions.json) and omits it for one without, instead of guessing from the
  schema name alone; the Direct Lake expression opens the database name the SQL endpoint actually has (a Fabric SQL
  database's `properties.databaseName`), as `_resolve_source` already resolved it.
- Creating tools with a dry run first: `create_semantic_model` (SemanticModel item from the TMDL draft via
  `POST /semanticModels` / `updateDefinition`), `create_views` (`CREATE OR ALTER VIEW` in a schema of its own on the SQL
  analytics endpoint or warehouse: a wide view per fact table, one per hard-to-read relationship; never DROP), and
  `create_data_agent` (a Fabric data agent through the staging REST API: instructions from the plan, the source as data
  source with the tables selected, example question/T-SQL pairs, publish); `app_starter` (read-only) for an app on a
  created API. A 401/403 from a create answers `kind: consent` naming the missing delegated permission; `docs/SCOPES.md`
  lists permissions per tool and the `az` commands. The SQL connection gained a `statement` runner for DDL.
- Five read-only consultant tools from the same plan, nothing created: `semantic_model_draft` (Power BI model in TMDL,
  Direct Lake on the SQL analytics endpoint, active/inactive relationships, README with decisions), `join_path`
  (shortest relationship chain with T-SQL, or the missing link), `data_dictionary` (Markdown hand-over with optional
  counts), `dbt_schema` (sources with unique/not_null/relationships tests), `plan_drift` (plan vs an existing API's
  definition). New modules semantic_model.py, paths.py, dictionary.py, dbt.py, drift.py; server.py has thin wrappers.
- Security review of the sign-in path (`docs/SECURITY.md`, `tests/test_security.py`): issuer tenant ids compare
  without case; an empty `Bearer` answers `invalid_request`; chunked request bodies are capped at 4 MiB like declared
  ones; the on-behalf-of cache evicts expired entries first and then the oldest half instead of emptying; a token
  endpoint answer without `access_token` is a `TokenError`. Tests cover wrong audience/issuer/tenant/scope, expired and
  immature tokens, `alg: none` and key confusion, altered signatures, path variants around `/mcp`, oversized headers
  and bodies, cache isolation between users, and that no token or secret reaches logs or output.
- Engine: an inference benchmark on Northwind, Chinook, TPC-H, AdventureWorks and Sakila (official DDL as ground
  truth, `tests/fixtures/schemas/`, numbers in `docs/INFERENCE.md`) and the rules it led to: table-wide column
  prefixes (`N_NATIONKEY`), `_code` suffixes, `<X>Header` names, abbreviations of four letters or more, a role before
  the target's name (`manager_staff_id` → staff, rule R4), junction keys (K4) and header-plus-line keys (K5). The shop
  schema's `order_items` now gets `order_id + line_no` by rule K5 without an override. GraphQL field names for
  previously matched columns are unchanged. `plan_backend` suggests `reference + start_date` keys for history tables.

## 0.5.0 — 2026-10-25

- Fabric IQ: `ontology_draft` writes the plan as an ontology (preview) draft: entity types with a key and properties,
  relationship types, data bindings, in the item's generation-2 definition (TMDL parts for `POST /ontologies` or Git),
  plus a Turtle file for the portal's Import ontology and a binding checklist with the rule behind every key and link.
  `create_ontology` exists behind `KRUSGRAPH_ONTOLOGY_WRITE=1` (needs `Item.ReadWrite.All`). CLI `ontology` command and
  `fabric_backend.ontology_files`. Deploy config `ontology_write` turns the create tool on; a large schema's draft keeps
  summary and bindings and says what it left out. Checked against recorded definitions, not live yet.
- Site: robots.txt names the AI crawlers, `/llms-full.txt` serves every Markdown page in one file, llms.txt has a
  Connect section, pages link their Markdown twin with `rel=alternate`, the home page declares the WebSite; the hero
  names the sources it works with and the home graph scrolls inside its card on phones.
- Snowflake and Databricks: Snowflake database items, mirrored Azure Databricks catalogs and mirrored catalogs (preview) are
  source item types next to mirrored databases, each read through its SQL analytics endpoint as Microsoft's REST
  specification documents it; the schema reader's schema match is case-insensitive on every dialect and a missing
  `KEY_COLUMN_USAGE` view (Snowflake) means "no declared keys", so the library, CLI and stdio server plan Snowflake
  and Unity Catalog schemas directly. Docs describe the two routes.
- `list_workspaces`: the workspaces the signed-in account can see, with id and capacity; every other tool now takes
  the workspace by name as well as by id (a duplicate name is reported with the ids to choose from).
- HSTS and `X-Content-Type-Options: nosniff` on every response, the MCP endpoint and the 401 challenge included.
- A request that announces a body over 4 MB is refused with 413 before anything reads it.
- The local stdio server (`fabric-backend-mcp`) answers failures with the same `error`/`kind`/`hint` as the remote
  one and never echoes the ODBC string; the CLI prints an input error as one line and exits 2.
- Input checks: `keys`, `confirmed` and `tables` must name tables and columns that exist (case does not matter);
  a typo is answered as `bad_input` instead of becoming a definition Fabric rejects or an API with missing tables.
  The schema name is escaped inside its SQL literal.
- Engine: the R2 lookup is indexed once instead of rescanning every key per column; a 1 000-table schema plans in
  a tenth of a second instead of ten seconds, with identical output.
- Exact package versions for the server image in `deploy/constraints.txt` (resolved for CPython 3.12 on manylinux,
  audited); the Dockerfile and CI install with it, a weekly workflow audits it, and it is part of the source tag.

## 0.4.0 — 2026-10-25
- Tool errors a user can act on: every MCP tool answers a failure with `error` (plain words), `kind` (a stable code
  such as `not_found`, `no_access`, `capacity`, `sign_in`, `consent`, `schema_not_found`, `table_not_found`,
  `timeout`) and `hint` (what to do next). Fabric's message is quoted only after tokens and secret-bearing headers
  are removed; stack traces never appear. The server's MCP instructions describe the format.
- Deploy check waits for the build it just deployed: the server echoes `KRUSGRAPH_BUILD` on `/healthz`, the deploy
  script sets it to the image's source tag in the full run and in `--update`, and the check passes only when the
  live server reports that tag. `--status` says whether the live build is the one in the checkout.
- `--update` respects `min_replicas` (0 scales to zero, 1 keeps an instance warm); health probes start after a
  second instead of ten so a cold start takes seconds. Seed works on lakehouses without schemas.
- SQL analytics endpoint: 30 s login timeout, 120 s per metadata query, connection closed after the plan.
- Waiting for Fabric's long-running operation tolerates 429/5xx and reports a lost sign-in at once.
- Large `query_graphql` results come back as valid JSON with lists cut to their first items and a `truncated` note.
- CI: plain `pytest` finds `deploy/` (every run since the deployment tests failed at collection); current action
  majors. Tests for the Fabric plumbing, the four tools end to end on the demo schema, the Python API, deployment
  polling and the deploy script's Python 3.8 compatibility. 202 tests.

## 0.3.0 — 2026-10-25

- The "Little Connections" site served by the same process: `/`, `/explore` (the engine's own plan of a synthetic
  shop schema, with the rule behind every link), `/start`, `/support`, `/partners`, restyled `/docs` and
  `/privacy`, styled 404, `sitemap.xml`, `robots.txt`, `llms.txt`, MCP server card, `/lovable`. Self-hosted fonts,
  dark mode, no external resources, CSP, gzip, accessibility audits and browser tests.
- Deploy: `krusgraph.sh --update` (new image only, no Entra, secrets or domains), `--status`, `--check`,
  `company_orgnr` in the config, deploy check covers the site pages and waits for the new revision.
- Privacy page states the logging setup (`--logs-destination none`) and the data path; `docs/PILOT.md` and
  `docs/FET-PLAN.md`.
- Honest wording about which MCP clients are tested today.

## 0.2.0 — 2026-10-21

- Rayfin (Fabric Apps) connector entities from the same plan: entity classes with typed fields, keys and
  `@one`/`@many` relationships, `schema.ts`; CLI, library and MCP tool. Verified with `npx rayfin up`.
- Remote MCP server (Streamable HTTP) with six annotated tools including read-only `query_graphql`; Entra sign-in
  with 401 challenge, protected resource metadata, token validation and on-behalf-of to Fabric and SQL;
  Dockerfile with ODBC Driver 18; Azure Container Apps deploy script.

## 0.1.1 — 2026-10-21

- Fixes from the first live run: by-name lookup skips the SQL analytics endpoint that shares the lakehouse's
  name, create tolerates Fabric's `202` with an empty body, every action spelled out in the definition, SQL
  endpoint accepted as a resolved source.

## 0.1.0 — 2026-10-21

- Tables in a Fabric lakehouse, warehouse or SQL database → an API for GraphQL item with inferred keys and
  relationships (rules K0–K3, R0–R3, ambiguity reported rather than guessed); library, CLI and MCP server.
