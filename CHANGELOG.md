# Changelog

Dates are the commit dates on `main`. Versions are the `version` in `pyproject.toml`, mirrored in
`fabric_backend/__init__.py` and `server.json` (a test keeps them equal).

## Unreleased

- Round n12, the layer on top of Microsoft's own Fabric MCP servers (unit-tested; nothing of it has run in Fabric).
  `compare_semantic_model` (read-only): an existing Power BI semantic model against the plan — relationships the model
  lacks, ones a rule or the data contradicts (with the rule or the count), other cardinality, both-way filters, active
  against the plan's spanning forest, links the plan lacks with a `confirmed` entry, columns summed against the
  `summarizeBy` rule, and the suggested measures it lacks; read from the model's TMDL through getDefinition
  (`SemanticModel.ReadWrite.All` or `Item.ReadWrite.All`; the read-only executeQueries is documented as not supporting
  the INFO functions, docs/SCOPES.md) or from `tmdl` files, which need no permission. `semantic_model_draft` suggests
  measures with their reason (row count per fact table, sums only where `summarizeBy` sums) and a `Calendar` table marked
  as the date table, related to `date` columns of fact tables. `gold_views_draft` and `create_gold_views` (dry run by
  default): materialized lake views over the silver tables, one wide view per fact table over the safest many-to-one
  paths, with `CONSTRAINT … CHECK … ON MISMATCH DROP` per key and relationship, each commented with its rule, never over
  a source, silver or foreign table; syntax and status from fabric-docs a2de7f9 (generally available since September
  2026); the SQL ran on SQLite and a local PySpark 4.0.1. `export_item_definitions` (read-only): what the creating tools
  would create, as folders in Fabric's Git format, `create_views`' SQL as a script beside them. Personal data
  (`fabric_backend/privacy.py`): one rule per name pattern (P1–P6), masked in `sample_rows` (hosted and local), left out
  of drafted queries and gold views, masked in the silver quarantine, named in `validate_plan`;
  `show_personal_data=true` shows them; the source's sensitivity label id is named. `deploy/krusgraph.sh
  --client-redirects` prints the az commands for Claude Code, VS Code and Cursor (docs/OPERATIONS.md section 5), runs
  nothing. `docs/LIVE-TEST.md`: the checklist for the next live run. /docs: a section on using Krusgraph beside
  Microsoft's Fabric MCP servers, and what is read about personal data and labels. Thirty-four tools.
- The status words follow the 26 October protocol (14 steps, no creating call): 16 tools are Tested end to end,
  `create_views` as a dry run; `create_backend` and `list_tables` are Experimental; texts that said the 22 tools of that day
  were tested, or that `create_views` created a schema and a view, are corrected. /local says exactly what leaves the
  machine. The menu says "Pilot projects" (/partners unchanged); the home page's JSON-LD has no price line.

- Drift monitor: the last saved plan is the one with the highest run number for the source (a new `run` column in
  `krusgraph.plans`), then the latest `taken_at`, now kept to the microsecond. Two runs in the same second (the run time
  was cut to whole seconds) could make the next run compare with the older plan and report the same changes again;
  CI's `notebooks` job failed on it once. A plans table from before the column gets it added on the next save.
- A column linked by a `confirmed` entry is settled: it is no longer also inferred to another table or listed in
  `plan.ambiguous`, and a confirmed header link counts for the line key (K5) as the inferred one did (confirming
  `order_items.order_id -> orders` moved the key to `product_id, line_no`). Confirmed entries take the schema's own
  spelling of table and column names, as `check_input` already accepted any case.
- Fixes from an independent review of this round's code, each with a test: the silver notebook can be generated again
  after its first run on a lakehouse without schemas (its own `silver_*` tables are no longer read as sources); its
  ownership mark names the source (`krusgraph.silver = <lakehouse id>/<schema>`), so two notebooks never overwrite each
  other's tables; a table that points at itself is checked until no more rows drop out. The drift monitor never shows
  the webhook address in an error, survives a failed listing of the workspace's items, does not retry (no double
  message), and refuses a `library_ref` that is not a plain ref. Only `--key-vault` switches the app to Key Vault (a
  `key_vault` in the config alone changed the app on `--update`); the full run keeps what `--key-vault` set. Rate limits:
  a zero window is refused at startup, `retry_after` is the slowest bucket's, idle ids are dropped about an hour after
  the last call (as `/privacy` says). Key Vault: a failed re-read after the hour keeps the secret held. Links built
  from `MCP_PUBLIC_URL` (docs, pricing) are parsed instead of split on "/mcp", which broke on a host like
  `mcp.example.com`. The paid-plan check counts `create_drift_monitor`'s dry run as the paid feature it gives away.
  `answer_query_draft` reads markers as whole words ("beräkna" is not "räkna"), takes top N only with a ranking word,
  prefers a column for "per order date", knows "order lines" means the table holding the lines, never groups a table by
  itself, counts per group when no aggregate is named, and lists every number or condition it did not apply.
- `Schema.from_spark` uses `listColumns` with one quoted name (the two-argument form is deprecated since Spark 3.4).
- The local stdio server has `answer_query_draft` (T-SQL only; GraphQL needs an API in Fabric) and, for a lakehouse,
  `silver_notebook_draft` (the notebook without a default lakehouse, since the item ids are not known locally; a schema
  other than `dbo` implies a lakehouse with schemas when `FABRIC_SCHEMAS_ENABLED` is not set). CI has a `notebooks` job
  that installs PySpark 4.0.1 with Java 17 and runs the generated silver notebook and the drift monitor on a local Spark
  (`tests/test_spark_notebooks.py`), so they no longer run only in a sandbox.
- From understanding to building ([docs/NOTEBOOKS.md](docs/NOTEBOOKS.md)); thirty tools. `silver_notebook_draft` and
  `create_silver_notebook` (dry run by default): a Fabric PySpark notebook generated from the plan that writes silver
  tables in a schema of their own, de-duplicated on each key (the latest row by `order_by` or a column named like
  `updated_at` wins), every relationship checked with the rows whose reference is missing in `krusgraph_quarantine`
  with the rule and the reason, each step commented with its rule, idempotent, and guarded twice against writing over a
  source table or a table it did not write. `drift_monitor_draft` and `create_drift_monitor` (dry run by default): a
  notebook and a pipeline with a daily schedule that compare the plan with the last saved one, save it in
  `krusgraph.plans`, and send what changed and which APIs, models and views it reaches to a webhook set as a pipeline
  parameter in Fabric (no secret in the code); the comparison is `plan_drift`'s and `lineage`'s logic as a library
  (`fabric_backend/monitor.py`). `answer_query_draft`: a question in Swedish or English about some tables as T-SQL over
  the safest join path with the rule per step, and as GraphQL for an existing API (or why GraphQL cannot answer it);
  `query_graphql` takes `question`/`tables`/`source` and runs the suggested query. Created through the notebook and data
  pipeline REST APIs (fabric-rest-api-specs a96c37a); without `Notebook.ReadWrite.All` / `DataPipeline.*` the creates
  answer `kind: consent` with the exact scope (docs/SCOPES.md). Unit-tested; the generated silver notebook and the drift
  monitor (two nights) also ran on a local PySpark 4.0.1 against the shop seed; nothing has run in Fabric yet.
- `lineage` (and `plan_drift`'s impact) now finds a GraphQL API over a lakehouse: the API names the lakehouse's SQL
  analytics endpoint as its source item, and the comparison used only the lakehouse's id. Reading the workspace's items
  moved to `lineage.py` (`workspace_edges`, `rest_*`), so the drift monitor uses the same code.
- `create_views` describes its header views (`vw_orders`) in the tool description, the docs page and the README; the
  hosted `sample_rows` passes the column types to the sampling SQL, as the local server does (binary as its size, CLR
  types as text). The plugin skill names the new tools and when to ask; `docs/PUBLISHING.md` notes the open question
  about `argument-hint` in plugin commands on claude.ai.
- Operations before real customers (unit-tested; nothing deployed or run against Azure). Fair-use limits per signed-in
  user (`oid`) and per organisation (`tid`): token buckets, 30/minute and 600/hour per user, 120/minute and 3000/hour per
  organisation by default, configurable or off (`KRUSGRAPH_RATE_*`); a refused call runs nothing and answers
  `kind: rate_limited` with `retry_after`, and only tool calls count, so `initialize`, `tools/list` and Claude's 401
  sign-in challenge are untouched. Anonymous usage statistics (`fabric_backend/usage.py`): one JSON line per tool call
  with tool, outcome kind, duration and dry run, optionally a salted organisation hash, nothing about users or data;
  `/metrics` in the Prometheus format, a 404 unless a token is configured. `/health` for uptime checks, without sign-in
  and without anything about the server. The Entra client secret can be read from Azure Key Vault with the container
  app's managed identity (`fabric_backend/keyvault.py`; as before when not configured), and
  `deploy/krusgraph.sh --key-vault` sets that up. `/privacy` lists exactly what is counted and says whether console
  logs are kept, from the deployment's own settings. `docs/OPERATIONS.md` has the commands, in order, for Key Vault,
  Log Analytics, the 5xx alert and the availability alert; `docs/SECURITY.md` says what is closed and what is open.
- A dormant paid-plan check (`fabric_backend/entitlements.py`, off unless `KRUSGRAPH_ENTITLEMENTS=1`): per organisation,
  from an environment variable or Azure Table Storage; paid features answer `kind: upgrade` with a link to a pricing
  page that does not exist yet, dry runs stay free. With the flag off nothing changes, and a test locks that.
  `docs/PRICING-NOTES.md` says how to switch it on.

- A faster first time: `/start` follows the design sketch (the three steps beside the current step, one at a time
  with JavaScript and all three without it; the real actions are the admin-consent link and the connector URL, no
  sign-in on the site) and its "What will Krusgraph access?" names every scope with the tools that use it, including
  the one the app does not ask for. The first-time error kinds (`sign_in`, `consent`, `no_access`, `capacity`,
  `schema_not_found`, `sql_sign_in`) carry a link to the new docs section "First-time errors", which gives the exact
  clicks per kind. Five first questions for an undocumented lakehouse in the server instructions and on the docs page.
- Fewer tokens per answer (before/after per tool in `docs/INFERENCE.md`): `analyze_schema` no longer repeats the
  constant rule weights and the three per-table centrality maps (the ten most central tables keep their numbers, every
  role its own); `plan_backend` leaves empty notes out and takes `mermaid=false`; `semantic_model_draft`,
  `data_dictionary` and `dbt_schema` take `tables` as names or patterns and are bounded at 60 000 characters (the
  document is cut on a line and the answer says so) instead of answering with a megabyte on 300 tables.
- Naming from the real world (`fabric_backend/infer.py`): a documented synonym table (abbreviations such as `cust`,
  `prod`, `ord`, `emp`; Swedish and German business words in singular and plural), transliteration of `å ä ö ü ß`,
  irregular English plurals (`People` → `person`), the table-kind prefixes `dim_`/`fact_`/`tbl_`/`stg_`/`vw_`, the
  `_sk`/`_bk` key suffixes, Swedish and German line words for K5, a suffix tie-break between two tables that answer to
  the same name, and a suffix guard for the weakest rule. Synonym matches count as R4, carry a `note` on the
  relationship and are listed under `plan.synonyms`; the five public benchmark schemas are unchanged to the number.
  Benchmark: WideWorldImporters (OLTP, 33 tables) and WideWorldImportersDW (star schema, 14 tables) from Microsoft's
  samples, plus four synthetic naming fixtures; before/after per schema in `docs/INFERENCE.md`.
- Compact answers for large schemas (`fabric_backend/compact.py`): `list_tables`, `plan_backend` and `analyze_schema`
  (remote and stdio) take `tables` (names or fnmatch patterns) and `detail` (`auto` = full up to 60 tables and a
  summary above, `full`, `summary`); every answer is bounded at 60 000 characters, a plan that is too large loses its
  diagram first, and the cut says to narrow with `tables`. Measured on 300 and 1 000 synthetic tables in
  `docs/INFERENCE.md` (plan_backend 443 kB → 44 kB, analyze_schema 747 kB → 21 kB at 300 tables).
- `create_ontology` is a regular tool now, dry run by default, no environment flag: it creates the Fabric IQ ontology
  (preview) item from the plan or updates the one of that name (`POST /workspaces/{id}/ontologies`, `updateDefinition`;
  delegated scope `Item.ReadWrite.All`, Contributor on the workspace, a Fabric capacity; checked in
  microsoft/fabric-rest-api-specs `ontology/swagger.json` on 26 October 2026, where the item is marked preview and the
  generation-2 example has the same part layout as the draft). Without the permission it answers `consent` naming the
  scope. The instructions and the docs page tell the one-plan story: API for GraphQL, Power BI semantic model, Fabric IQ
  ontology, wide views and data agent from the same plan, each with a dry run first. Twenty-five tools.
- `suggest_relationships` ranks before the data check: the 26 October live run gave every candidate for
  `orders.ship_to_id` the same score. Role words judged against the target's name and key column (`ship_to` names an
  address), weighted triangular closure (the certainty product of the two links that close the triangle, including a
  shared parent: orders → customers ← addresses), and penalties from the plan (a line table already joins the two, the
  target is a fact table, the source already refers to it). On shop without data: addresses 3.94, the rest 1.5 or less.
  After the check, `final_score` adds the inclusion damped below ten distinct values to the name score.
- `create_views` adds one view per header table: the table a fact table holds the lines of, with its own dimensions
  (`vw_orders` with the customer and, once confirmed, the ship-to address). Found in every benchmark schema: Orders,
  Invoice, ORDERS, SalesOrderHeader and PurchaseOrderHeader.
- TMDL drafts no longer sum CamelCase ids (`PersonID`, `TerritoryID`, `SalesPersonID` in AdventureWorks), codes or label
  numbers (`Status`, `RevisionNumber`, `TaxType`, `ExpYear`); no key, relationship column or id is summed in any
  benchmark schema. A reference with no id word that no rule links is summed until confirmed (pinned by a test).
- The local server's `sample_rows` reads SQL Server's hierarchyid, geography, geometry and sql_variant as text and binary
  columns as their size, so pyodbc's unsupported-type error does not fail the call. SQL text unit-tested only.
- Plugin: `supportUrl` is the issue tracker; the plugin passes `claude plugin validate --strict` (Claude Code 2.1.295,
  26 October 2026).
- `fabric-backend demo`: the 20-minute demo on a laptop (`fabric_backend/demo_app.py`, `docs/DEMO-20-MIN.md`). One local
  page on 127.0.0.1 in the graph explorer's design, four steps with a time budget: connect (a SQL Server over ODBC, a
  folder of CSV / Excel files loaded into SQLite in memory with a standard-library .xlsx reader, a columns list, or the
  synthetic shop schema), the map (plan, roles, subject areas), the health check (validate_plan and
  suggest_relationships as findings with what we saw / what it means / next step / evidence, Accept and Skip, the plan
  updating at once), the value (five questions proposed from the graph and run locally with the SQL, exports:
  dictionary, dbt, a Lovable prompt, the plan, the ER diagram). No account, no cloud, no external script; the figures
  follow the motion brief and prefers-reduced-motion. The site's graph gained a layered layout for any schema. Tests on
  the shop seed and on a CSV / Excel folder; a test that the server binds to 127.0.0.1 only.
- Site: `/local` (the local server over ODBC: SQL Server with Windows sign-in or a Fabric SQL endpoint, what it needs,
  the Claude Desktop configuration, what works locally, the CSV path), the MCP Registry listing named on the home page,
  the docs page and llms.txt, the Claude plugin mentioned as coming soon. `docs/PRICING-NOTES.md` (internal): what a
  free and a paid tier could contain, what would have to be measured per user, what it requires; nothing built.
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
