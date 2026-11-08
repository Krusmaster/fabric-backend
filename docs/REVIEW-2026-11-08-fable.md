# Independent code review, 8 November 2026

Read-only review of what changed between 29 October 2026 (`566bdf0`, round n50) and `b2bcb84` (rounds n155 and n156),
423 commits, about 24 000 added lines. Reviewer: a scheduled Claude session (model Fable 5.1) with no live user; the
rounds that pushed to `main` the same day were not touched. Nothing but this file was written to the repository.

How it was done: the sign-in and token code was read line by line by the reviewer; the Fabric-writing tools, `/check`
and the site's claims were each read by one sub-reviewer on the same checkout, and every finding below was then
re-verified by the reviewer against the code at `b2bcb84` (a probe script, the fixture, or the page in Chromium). The
whole suite was run first on Python 3.12: 2 627 passed, 4 skipped. Findings are sorted by severity; "plausible" marks a
precondition that was not verified. Line numbers are those of `b2bcb84`.

## Findings

### High

**H1. Code injection into the generated silver and gold notebooks through a table or column name containing a newline.**
`fabric_backend/silver.py:451-452` (`_key_comment`), `:468` and `:482-483` (`_table_cell`'s `# ---- name` and
`# Reference` lines), `fabric_backend/gold.py:308` (`# {c['name']}: {c['why']}`). The Python literals in the cells go
through `_py()` (`json.dumps`) and are safe; the comment lines interpolate the raw names, and `notebook.fabric_source`
(`notebook.py:50`) writes code cells line by line as they are. A name with a newline therefore ends the comment and
starts a statement at column 0. Verified on the shop seed with the customers key renamed to
`customer_id\nimport os; os.system('id') #` (passed as `keys=`): the customers cell contains the line
`import os; os.system('id') # (rule K1: ...)` at column 0 and parses. The statement runs under the identity of whoever
runs the notebook in Fabric, so a person who can write a bronze table's schema (or who writes the `keys=` argument)
plants code that the data engineer executes. Plausible precondition: Delta column mapping allows such names, and the
SQL analytics endpoint returns INFORMATION_SCHEMA names as they are; this was not tried against Fabric. Smallest fix:
one helper that strips control characters (or `json.dumps`) applied to every name written into a comment line in
`silver.py`, `gold.py` and the pipeline's check notebook; `tests/test_silver_notebook.py` gets a column name with `\n`.

### Medium

**M1. `create_views` accepts `views_schema` equal to the source schema and writes views into it.**
`fabric_backend/views.py:31` (`schema_sql`) and `:170` (`statements`) check only the characters of the target schema;
`server.py:1410-1421` (`create_views`) and `:2085` (`export_item_definitions`) pass `views_schema` through.
`silver.spec` refuses `silver_schema == schema` and `gold.spec` refuses `gold_schema in (schema, silver_schema)`; views
have no such check. Verified: `views.statements(plan, "dbo")` on the shop seed returns `CREATE OR ALTER VIEW
[dbo].[vw_order_items] ...` with no refusal. Scenario: `create_views(schema="dbo", views_schema="dbo", dry_run=false)`
replaces an existing user view `dbo.vw_orders`, against the docstring (`server.py:1416`, "in a schema of their own"),
DOCS.md line 671 and README line 130. Fix: in `views.statements()`, `if target.lower() == plan.schema.schema.lower():
raise PlanInputError(...)`, as silver and gold do.

**M2. n155: an accepted fix id whose table is outside `tables=[...]` is dropped without a word.**
`fabric_backend/silver.py:359` (`apply_fixes`: `if ... t is None: continue`), `fabric_backend/fix_plan.py:346-352`
(`accept` never checks that every resolved id produced an entry in `out["fixes"]`); the same pattern in
`fabric_backend/dbt.py:544`. Verified: shop seed, `fix_plan.accept(silver.spec(p, INFO, tables=["products"]),
proposal, ["key:customers"], p)` gives `out["fixes"] == []` and a notebook without `keep_one_per_key(`, no error.
Through the tool, `create_silver_notebook(tables=["products"], fixes=["key:customers"], dry_run=false)` creates a
notebook without the fix, while the docs promise "applies exactly the accepted ones"; the empty `fixes` list in the
answer is the only sign. Fix: after `apply_fixes`, compare the chosen ids with the ids taken and raise
`PlanInputError("fixes: <id> is for table X, which is not in tables")`; the same in `dbt.project`.

**M3. `/check`: the Power BI export panel renders the literal text "nullnull" in the common case.**
`fabric_backend/static/check.js:261` pushes `notBuilt(r), decisionsInModel(r)` into `kids`; both return `null` when
nothing is unbuilt and no decision was taken; `:265` ends with a raw `panels.model.replaceChildren(...kids)`, and the
DOM turns `null` into the text "null". `el()` (`:324`) and `fill()` (`:327`) filter such children; `drawModel` does
not use them. Verified in Chromium on `/check?example=sample`, "Build a Power BI model": "...once the tables are in a
Fabric lakehouse.nullnullThis file is tested end to end...". Fixtures 04 to 06 do not show it because `notBuilt`
returns a list there, which is why the n150 browser tests pass. Fix: `fill(panels.model, ...kids)` at `:265` (and the
same hardening for `panels.app` at `:314`).

**M4. `/check`: CSV ids with 16 to 19 digits are read through `float` and lose precision; distinct keys collapse.**
`fabric_backend/platforms/local.py:34` (`_INT_RE` caps at 18 digits), `:115-118` (a 19-digit value falls to
`_FLOAT_RE`, type `real`), `:129` (`_coerce` for `int` is `int(float(v))`), `:134`. Verified:
`int(float("9007199254740993")) == 9007199254740992`; a CSV column with 9007199254740993 and 9007199254740992 loads as
one value, so such a key is reported "not unique" and orphan counts are wrong, with nothing on the page to tell.
Predates the window (`6a839ba`, 27 October) but it is the path every uploaded file takes, next to the n150 leading-zero
rule. Fix: `int(v)` for strings matching `_INT_RE`, and treat an all-digit string longer than 18 as `text` in
`_guess_type`, as the leading-zero rule does.

**M5. README contradicts `tool_status.py` and the docs on three live-test facts.**
- `README.md:148-150`: "the page with visuals is ... not yet created in Fabric" against `tool_status.py:204-206`
  (`LIVE["create_report"]`, 7 November 2026, `shop_report_visuals`), DOCS.md line 670 and README itself at line 125.
- `README.md:257-258`: client registration "not yet tried with a real client" against `tool_status.py:430-449`
  (VS Code, Cursor, Glama on 27 October, Lovable on 30 October) and `docs/LIVE-TEST.md:140-145`.
- `README.md:288`: rule R5 "plan_backend and `/check` do not pass them yet" against `server.py:226-234` (`_hosted_plan`
  counts R5 on every hosted plan since n87), `server.py:408-417` and `browser_check.py:246-258`.
Why the tests missed it: `tests/test_n146_one_source.py:157` parametrises the status checks over the rendered pages
only; README is in the permissions and Claude Code tests alone. Fix: the three sentences, and README added to that
parametrisation.

### Low

**L1. `create_drift_monitor` defaults to `schedule=True`, which the hosted app's permissions cannot do.**
`server.py:1809-1811`. `docs/SCOPES.md:25,44`, `README.md:173`, `access.py:58-59` and `tool_status.py:232` all say
`DataPipeline.Execute.All` is not requested, "so use `schedule=false`". A default call with `dry_run=false` creates
the notebook and the pipeline and then stops at the schedule step with kind `consent`; a second call with
`schedule=false` updates the two items in place, so nothing is lost, but the first real call always fails. Also
`DOCS.md:625-626` ("the app has every permission the tools use") is wrong for this one step. Fix: default
`schedule=False` on the hosted server, or mark the step Skipped with the reason when the scope is not granted.

**L2. `create_drift_monitor` adds a duplicate schedule when the schedule listing fails.**
`server.py:1862-1863`: a non-200 on `GET .../jobs/execute/schedules` gives `existing = []`, so a new daily schedule is
POSTed although one at that time may exist, against "unless one at that time exists". Fix: on a non-200, return
`_step_failed(...)` or mark the step Skipped with the status.

**L3. The package declares Python 3.10+ but `pages.py` needs 3.12.**
`fabric_backend/pages.py:769` nests the same quote kind inside an f-string replacement field (PEP 701, 3.12 only).
`python3.11 -m compileall fabric_backend` fails there; `import fabric_backend.server` fails on 3.10 and 3.11
(`server` imports `discovery`, which imports `pages`); `demo_app` and `sales_demo` too. `pyproject.toml:7` says
`>=3.10`, `README.md:624` and `docs/LOCAL.md:23` say 3.10 or later. The local stdio server, the CLI and
`browser_check` do not import `pages`, the Docker image and CI are 3.12, so nothing caught it (introduced `fb64423f`,
1 November). Fix: join the names into a variable before the f-string, and add 3.10 and 3.11 to the CI matrix (or
raise `requires-python` to 3.12 with the two docs lines).

**L4. `KRUSGRAPH_NO_ROW_VALUES` does not remove the values `create_semantic_model` puts in `read_from_rows` (n151).**
`server.py:1243-1279` (`_model_reads`) writes "Dates: 2024-01-03 to 2025-11-30 in orders.order_date" (MIN/MAX of a
column); `switches.py:123-137` (`_walk`) shapes only `data`, `rows`, `next_steps`, `error` and `hint`. Verified:
`switches.answer(...)` with the switch on returns the dates unchanged while removing the `rows` key beside them. Fix:
in `_model_reads`, say only that a date range was read when `switches.no_row_values()`, or add `read_from_rows` to
`_walk`.

**L5. n155 ids can differ between `validate_plan` and the applying call on a plan with more than 60 checks.**
`server.py:1541` (`_silver` counts with the default `max_items=60`) and `dbt_schema` (`server.py` about line 1027)
while `validate_plan` lets the caller count up to 200. An id accepted from `validate_plan(max_items=200)` is then
refused as "no such finding" (fail-safe, but the feature does not work for a large schema). Fix: pass `max_items=200`
to the validate calls when `fixes` is given.

**L6. dbt project: the sources file path is built from the raw `source_name`.**
`fabric_backend/dbt.py:539` `files[f"models/sources/{source_name}.yml"]` (the folders use `_slug`, this one does not).
Verified: `dbt.project(p, "../../etc/evil", "dbo")` returns the key `models/sources/../../etc/evil.yml`. The server
writes nothing; a client that writes the files as given would. Fix: `_slug(source_name)` for the path.

**L7. `views._dedupe` mangles the alias of a column whose name contains `]` (relationship views).**
`fabric_backend/views.py:166`: `c.rsplit(" AS ", 1)[1].strip("[]")` strips the doubled `]]` with the quotes and
re-quotes. Verified: `addresses.city]x` becomes alias `addresses_city]]x`. Valid SQL, wrong column name. Fix: carry the
raw alias names next to the expressions instead of re-parsing the SQL, as `wide_view_sql` does.

**L8. TMDL and M written with bare names (plausible).**
`fabric_backend/semantic_model.py:436` `Sql.Database("{endpoint}", "{database}")` (a `"` in the item's display name
breaks the M expression); `sourceColumn`, `sourceLineageTag`, `entityName` lines in `semantic_model.py` and
`ontology.py` are bare while the object names go through `tmdl_name`. A column `na\nme` splits a TMDL line. The effect
is a definition Fabric rejects, not a write elsewhere; whether Fabric allows such names was not verified. Fix:
`tmdl_name()` for those values and `""` escaping for the M string.

**L9. `_py` is not a faithful Python literal for non-BMP characters.** `silver.py:153` and the other `json.dumps`
sites in gold and pipeline cells: `ast.literal_eval(json.dumps("ord😀")) != "ord😀"` (surrogate pair), so a column
with an emoji becomes two lone surrogates and `F.col(...)` fails at run time. Fix: `json.dumps(value,
ensure_ascii=False)`.

**L10. `/check` findings tell the visitor to "Accept" something the page has no button for.**
`browser_check.py:115` gives `confirmed` only to `suggestion` findings and `check.js:379` shows Accept/Skip only then;
the texts for `key_candidate`, `composite_key` and ambiguous findings (`demo_app.py:409,432`, `browser_check.py:167`
"accept it and the check counts") still say Accept. Verified in Chromium with a keyless CSV: six "Next: Accept to use
... as the key" lines, zero `button[data-decide]`. Fix: rewrite `next` for those kinds on `/check` (point at
`keys=` in Claude), or add key decisions to `decide()`/`build()` as n150 did for relationships.

**L11. `/check`: after Accept the page's own summary does not follow the decision; only the downloads and the export
panel do.** `check.js:519-531` (`decideRel` replaces `lastResult.evidence_report` only) and `:515-517` (`saidFor` says
"counted in the rows and in the Power BI model" even when `build()` reports `not_built reason key_not_unique`, which
the panel below then states). The downloads are right; two texts on one page disagree. Fix: build `saidFor` from the
`decide` result. Related, by code reading: `decideButtons` (`:533-540`) and the guided demo (`:408-410`) do not mirror
each other's status line.

**L12. `/check` file chooser offers `.txt`, which the engine refuses with a temp path in the message.**
`page_templates/check.html:17` (`accept=".csv,.xlsx,.txt,text/csv"`), `platforms/local.py:245-249`. Verified:
"no .csv or .xlsx files in /tmp/check-...". Fix: drop `.txt` from `accept` or route it to the pasted-text path.

**L13. `/privacy` says a page-view record is written for `/explore`; the server never writes one.**
`PRIVACY.md:83,101` and `README.md:258`; `/explore` is a 301 (`pages.py:535` `REDIRECTS`) outside `page_route`
(`server.py:2621`), so `_usage.page_view` never sees it; `usage.py:35` still lists it. Over-declares a record. Fix:
remove `/explore` from `PAGE_VIEW_PATHS`, the two sentences and `tests/test_usage_stored.py:27` ("five pages").

**L14. `/privacy` row 74 describes the exchanged tokens' lifetime as a deletion time.** `PRIVACY.md:74` "in memory
only, until 120 seconds before they expire"; `entra.py:165-182` keeps a cached entry past expiry until the cache
exceeds 5 000 entries or the process restarts (the 120 s is the reuse margin), and never holds Claude's own token
beyond the request (only its SHA-256 as the cache key). Fix: "reused until 120 seconds before expiry and never after;
dropped when the cache is trimmed or the server restarts".

**L15. `offline_access` is requested but not in the permissions table.** `entra.py:86,94` and
`registration_flow.py:123,288` ask Microsoft for `offline_access`; `access.py:38-70` lists `User.Read` as the only
Microsoft Graph permission and `deploy/azure_containerapp.py:80-86` does not include it. Entra's consent dialog shows
it; the site's table does not. The only requested-but-unlisted scope found. Fix: one row or footnote in `access.py`.

**L16. llms.txt states unconditionally that other MCP clients' sign-ins keep encrypted records.**
`discovery.py:181`; with `KRUSGRAPH_CLIENT_REGISTRATION` off there is no store and `/privacy` omits the section
(`PRIVACY.md:130-145`). Verified by rendering with the flag off. Fix: condition the clause on `CLIENT_REGISTRATION`.

**L17. The site advertises `/mcp/connect` whenever the env flag is set, even when the layer refused to start.**
`pages.py:178-180` (`_registration_on` = `registration.enabled()`, the env flag only) while `server.py:2821-2823`
mounts the routes only when `registration_flow.install()` returns a layer (no `KRUSGRAPH_REGISTRATION_KEY`: it logs
"stays off"). Verified: `/mcp/connect` 404 while `/start` showed "Two addresses". Fix: `install()` records the
effective state and `_registration_on()` reads it.

**L18. `/docs` tells Cursor users to `curl .../oauth/register`, a route that exists only with
`KRUSGRAPH_CLIENT_REGISTRATION_DCR=1`.** `DOCS.md:88-89,99-101`; `registration_flow.py:721-722`. Fine on
krusgraph.com (DCR is on there per LIVE-TEST), wrong for a self-hosted server. Fix: a conditional or "(when the
operator has turned DCR on)".

**L19. Repo docs that predate 28 October still say the hosted app lacks the write permissions.**
`docs/NOTEBOOKS.md:153-156`, `docs/SEGMENTATION.md:92-93`, `docs/DEPLOY-NEXT.md:67-72` against `access.py:51-63`;
`docs/INFERENCE.md:272` says 36 tools (39); `docs/SITE.md:150,192` lists chat steps `fix`, `dbt` and the label "Write
dbt tests" that `chat-demo.js:16,474-480` does not have; `deploy/KRUSGRAPH-START.md:144` and
`deploy/azure_containerapp.py:203-204,843` still carry `KRUSGRAPH_ONTOLOGY_WRITE`, which no module reads
(`README.md:268` says so). Fix: one sentence each; `test_n146_one_source` would catch the first three if `docs/*.md`
were in its parametrisation.

**L20. The chat's two exits do not use the n149 labels.** `chat-demo.js:471-472` ("Try your own files", "Connect to
your agent") against `pages.py:829-830` (`CHECK_LABEL`, `CONNECT_LABEL`); `tests/test_n149_lead_with_problem.py:34`
checks `<main>` buttons only. Fix: pass the labels as data attributes on the launch button.

**L21. (plausible) Two home-page statements the repository's records do not back.** `home.html:37` "questions 1 and 2
read only (29 October 2026)": `docs/LIVE-TEST.md` records plan_backend/validate_plan on 26, 27 October and 2 November,
and the 29 October entries concern create_ontology and create_semantic_model. `README.md:260` "Operations ...
unit-tested, not deployed": the limits, usage line and `/metrics` ship in the deployed image; whether they are on live
is not in the repository.

## Looked at and found fine

**Sign-in and tokens (read in full by the reviewer).** `entra.py`: RS256 only against the common JWKS, `exp`/`iss`/
`aud`/`tid` required, the issuer rebuilt from the token's own `tid`, audience one of the app's three forms, `scp` must
hold `user_impersonation` (so a client-credentials token with `roles` is refused), allowed tenants; the on-behalf-of
cache is keyed by SHA-256 of the user's token and the scope, bounded at 5 000, never shared between users. `server.py`
`guarded`: every `/mcp` and `/mcp/connect` request is validated before the SDK sees it; `/mcp/connect` is rewritten to
`/mcp` only after validation; the tools validate again and exchange per call; `_identity` and the limiter work on the
same token. `registration.py` and `registration_flow.py`: redirect addresses are https on a DNS name or loopback on any
port, matched exactly otherwise and, for CIMD, on the client id's host; the CIMD fetch vets every resolved address,
pins the connection to it, checks the certificate, follows no redirect, reads 5 KB, ends after 6 s and runs four at a
time; errors before the approval stay on this server's page; the consent form is signed with the client inside it,
bound to a CSRF cookie, single use (`j`), and checked for Origin/Sec-Fetch-Site; the Entra state is single use and
bound to the browser by the flow cookie; the approval is stored for the account that actually signed in at Entra, and
a remembered approval for another account shows the page again; loopback approvals are never remembered; the code is
60 s, single use, checked for client id, redirect and PKCE S256, and a second redemption revokes the family; the
refresh line rotates, the 60 s replay window (n83) is sealed with the old secret and the server's key and gives the
answer only while the new secret is still current; the user is re-checked on every refresh. `registration_store.py`:
keys validated, Table Storage take = read then `If-Match` delete, expired records never handed out, purge by ETag.
Logs: `reg.log` carries no token, address, user id or state; `usage.py` writes the five fields the privacy page lists;
`errors.scrub()` on every quoted message; the SQL token goes through `attrs_before`, not the connection string; Key
Vault reader never puts the secret in a repr. `consent_done_html`: the error code is filtered, the description escaped,
the tenant must be a GUID. `_check_query` refuses mutations and subscriptions by parsing. The 49 client-registration
tests, the Entra and refresh-rotation tests pass.

**Fabric-writing tools.** Every `create_*` has `dry_run=True` and returns before any POST or DDL on every path
(`_backend_dry_run`, `_model_replacement` and `_model_reads` are reads, `create_report` reads the model only,
`create_drift_monitor` and `create_pipeline` return before the first item); verified with mocked `requests` that no
write happens. No DELETE or DROP in the Fabric paths. Items are matched by name and type in the given workspace only.
Silver refuses `silver_schema == schema` and any target equal to a source table and re-checks ownership at run time;
gold refuses `gold_schema in (schema, silver_schema)`; the pipeline reuses those specs. T-SQL identifiers double `]`
everywhere (`Order]; DROP TABLE x--` renders as `[Order]]; DROP TABLE x--]`), literals double `'`, backticks are
doubled in the PySpark SQL, `library_ref` and `at` are regex-checked, `time_zone` goes into JSON only, PBIR parts are
`json.dumps`, dbt YAML through `_y`, Git export folder names encoded. Quarantine: left-anti/left-semi on distinct parent
keys, NULL references kept, the decisions cell stops before any write while a question is open. The read-only switch
removes the creating tools from the listing and refuses them at call time; MCP Apps wraps the guarded function.
n155/n156: unknown ids, question-only ids, a `choice` not offered, a `winner` the table lacks are refused;
`dbt_schema(fixes=)` requires `project=true`.

**`/check`.** With three marker-named and marker-valued CSVs, a run, every finding, the model build, both downloads and
every Ask Onto question: 18 requests, all GET without a body, none carrying a marker, a file, table or column name;
after the run only `/check/event?e=loaded|done`; `ping()` is called with the two literals only and `usage.check_event`
drops anything else; `localStorage`, `sessionStorage` and cookies empty; the page's CSP is `connect-src 'none'`, the
worker's names Pyodide and the engine zip only; downloads are Blob URLs; the `/start` links carry no query. Totals and
keys on fixtures 01 to 06 agree with a hand computation (01: 600 vs 1 300; 02: 600/1 200 and the n150 hours rule; 03:
one orphan, NULLs not orphans; 04: key rejected, no relationship, no `isKey`, chart 600 not 700; 05: 600 vs 700, the
orphan group apart, `0000000010` kept as text; 06: suggestion not applied). Accept and Skip reach the plan, the
evidence report and the TMDL from one `decisions` map, re-read at execution; the export panel's counts equal the TMDL's
relationships on all four examples. The Power BI preview's measures were recounted in SQL and agree.

**Site claims.** `access.GRANTED` equals `deploy/azure_containerapp.py` `REQUIRED_SCOPES` and the table on every
rendered page; the server asks only for `.default` on Fabric and SQL; every status word on the rendered pages comes from
`tool_status.py`; 39 tools everywhere the tests look (29 read-only, 10 write); every "Tested end to end" tool has a
LIVE-TEST row; 3 380 internal links over 61 pages and 8 Markdown twins resolve, registration on and off; the TTLs on
`/privacy` equal the constants; `KRUSGRAPH_ACCESS_LOG=0` is set exactly when logs are kept; the banned sales words are
absent from the whole public site and the chat.

## Not reviewed

`deploy/azure_containerapp.py` beyond the scopes and the log setting (the maintainer's deploy script);
`fabric_backend/concepts.py`, `use_cases.py` and the blog beyond links and status words; `rayfin.py` (n141) and the
Rayfin examples; `sap_mirror.py`, `pack_manifest.py` and the Younium/Salesforce pack; `sql_sums.py`, `profile.py`,
`catalog.py`, `domains.py`, `openlineage.py`, `agent_context.py`, `agent_tests.py`, `quality_suites.py`,
`run_results.py` beyond its message cap; the MCP Apps cards (`mcp_apps*.py`, off unless `KRUSGRAPH_MCP_APPS=1`, not
set by the deploy script); `examples/benchmark/`; Databricks drafts; the Dependabot and SBOM workflows. Nothing was run
against Fabric, Entra or Azure.
