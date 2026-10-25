# Changelog

Dates are the commit dates on `main`. Versions are the `version` in `pyproject.toml`, mirrored in
`fabric_backend/__init__.py` and `server.json` (a test keeps them equal).

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
- Snowflake and Databricks: mirrored Azure Databricks catalogs are a source item type (next to mirrored databases,
  which cover Snowflake); the schema reader's schema match is case-insensitive on every dialect and a missing
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
