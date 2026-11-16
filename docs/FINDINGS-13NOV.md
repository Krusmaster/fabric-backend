# Findings of a first-user test, 13 November round (F1)

Round F1, run on 15 November 2026 on `main` at `f3c0561` (after n224, n225, n226, n228 and D1), and the findings that
F2's engine change could move (A3, B4, B5, B7, B8, C1, C3) run again on `dc87973`, after F2 landed: all of them still stand. The founder, 12 November
2026: "test, develop, find new solutions and update: the MCP, the website and the workload."

This is a test without Fabric, read the way a first user reads. Nothing here was run against a Fabric workspace, and
nothing says how fast anything is. Every finding was seen in an answer, a page or a log during this run; where a
finding is a reading of the words and not a wrong number, it says so.

## 1. What was run

| Part | How | Result |
| --- | --- | --- |
| Python tests | `pytest -q` with the pins of `deploy/constraints.txt`, Python 3.12, Chromium for the browser checks | One test failed on `main` before this round: `tests/test_n200_health.py::test_the_health_step_reads_no_source_rows` (A5). The run after the fixes is in the release commit of this round. |
| Hosted MCP server | `fabric_backend.server.mcp` called through the MCP protocol (an in-memory client): 40 tools and the prompt `start`. Fabric's REST API and the SQL endpoint were replaced at the boundary: a workspace `Sales` with two lakehouses, `shop_lh` (schema `shop`, the synthetic shop of `seed.py`) and `demo_lh` (schema `dbo`, the synthetic SAP tables of `sap_demo.py`), both as rows in SQLite, so every counting query ran. Every write was refused by the test double. | Every tool answered; no traceback reached an answer. Findings below. |
| Local MCP server | `fabric_backend.mcp_server.mcp` the same way: 24 tools, first with nothing configured, then on the shop rows | Four first-run problems (A1 to A3, B8, B9) |
| Website | Served locally with the production settings' names (`MCP_PUBLIC_URL`, `PRODUCT_NAME`, `CONTACT_EMAIL`); 74 pages (the sitemap's 66 and what they link to) opened in Chromium at 375, 768 and 1280 px, light and dark: status, console errors, failed requests, broken images, horizontal scroll, every internal link and anchor; the page texts searched for claim words; the Try a demo chat clicked through to its end at 1280 px light and 375 px dark | No 404 among linked pages, no broken image, no horizontal scroll, no console error. The old `/docs#...` anchors forward to their sub-pages. Three findings on words (B12, B15, C1). |
| Model editor | `npm ci`, `npm test` (31 files, 288 tests), `npm run typecheck`, the production webpack build, and the pages of `tests/fixtures/n225/` at 375, 412 and 1280 px | All green; no horizontal scroll, no text under 14 px and no tap target under 44 px at 375 px. Findings on words (C6 to C8). |

Not run: anything in Fabric, the cards inside Claude (their browser tests ran in the suite), a SQL Server over ODBC, a
screen reader.

## 2. Findings

Ranked: **A** blocks a tester, **B** misleads, **C** looks bad. Each has where it is, what the user sees, the fix and
the round that should take it (n227 chat cards, n228 drawio, n229 verify/next/gate, n230 CDS, F2, or new).

### A1. `fabric-backend-mcp --help` printed nothing and waited

**Where:** `fabric_backend/mcp_server.py` `main()`; `docs/LOCAL.md` section 2 and the page `/local`.
**Sees:** The install step says to run `fabric-backend-mcp --help` to prove the command is on the PATH. `main()` ignored
its arguments and started the stdio server, so a terminal showed nothing and waited for a client.
**Fix:** `--help` prints the settings and returns; `--version` prints one line.
**Round:** fixed in F1.

### A2. The local server's first errors sent the reader to "the operator"

**Where:** `mcp_server.py` `_execute_factory`, `deploy.py` `token_from_az`.
**Sees:** With `FABRIC_ODBC` not set: "This is a configuration problem on the connector itself, not with your account.
Contact the operator." Locally the reader is the operator. With the ODBC driver missing: `ImportError ... libodbc.so.2`,
kind `unexpected`, "Try again". With the Azure CLI missing, `create_backend` answered `FileNotFoundError ... 'az'`, kind
`unexpected`, "Try again".
**Fix:** Each answer now says what to set or install and where the guide has it; a missing or signed-out Azure CLI is
kind `sign_in` with `az login` or `FABRIC_TOKEN` as the step.
**Round:** fixed in F1.

### A3. The local `list_tables` answers `{}` when the schema has no tables

**Where:** `mcp_server.py` `list_tables` and `_plan_on` (every local tool plans the same way).
**Sees:** The default schema is `dbo`. A first user whose tables are in another schema gets `{}` and nothing else;
`plan_backend` answers "0 tables". The hosted server answers kind `schema_not_found` with the next step for the same
case.
**Fix:** Raise `SchemaEmpty` in `_plan_on` when the schema read has no tables, as `_plan_read` does in `server.py`, and
list the schemas that have tables in the hint.
**Round:** F2 (it holds the neighbouring call in `plan_from`), otherwise new.

### A4. `review_plan(validate=true)` hides counting queries that failed

**Where:** `fabric_backend/review.py` and `review_plan` in `server.py`.
**Sees:** When the counting queries fail (seen here with every query refused by the test double), `validate_plan` says
"51 not counted because the query failed (see not_counted)". `review_plan(validate=true)` on the same source says
"checks: 0 passed, 0 failed, 0 stale, 41 not checked", `attention: []`, and its report says "Nothing open". A tester who
keeps the review file concludes nothing needs attention.
**Fix:** Carry `not_counted` with its reason into the review's `attention` and the report ("41 checks could not be
counted: <reason>"), and tell a check that was not asked for apart from one that failed to run.
**Round:** n229.

### A5. CI on `main` has been red since 14 November

**Where:** `tests/test_n200_health.py::test_the_health_step_reads_no_source_rows`.
**Sees:** The notebook's cells read the real clock, the fixture's commit times are fixed at 11 November 2026, so the
freshness row turned stale three days later. Every round since reports "one failure, the clock test".
**Fix:** The test sets the commits three hours before the real now.
**Round:** fixed in F1.

### B1. "total NETWR per sales order" does not say which NETWR it sums

**Where:** `fabric_backend/answers.py` (`answer_query_draft`), on `demo_lh` / `dbo` with `tables=["sap_vbak", "sap_vbap"]`.
**Sees:** NETWR is a column of both tables. "total NETWR per sales order" sums `sap_vbak.NETWR` once per order
(DISTINCT on MANDT + VBELN). "total net value per sales order" sums `sap_vbap.NETWR` over the item rows, with
`assumptions: []`. Neither answer says the other column exists. On the sample the two agree (600, 100, 50); on real
data a header value and the sum of its items can differ, and the reader is not told a choice was made.
**Fix:** When the measure's name is a column of more than one table in the path, say so in `assumptions`: which one was
summed, why, and the one-line change for the other; give both phrasings the same choice.
**Round:** n229.

### B2. The same draft drops rows without saying so, and joins where no join is needed

**Where:** `answers.py`, same call.
**Sees:** The query starts at `sap_vbap` and inner-joins `sap_vbak`. `validate_plan` on the same source reports one item
row whose order is missing (1 of 6, 40.00 on order 0000000009); the draft's totals add up to 750, the item table holds
790, and nothing in the answer mentions the row that fell out. An order without items would fall out the same way. For
a header amount per header key the header table answers alone.
**Fix:** When group and measure sit on the same table, select from that table only. When a join is needed and the plan's
check is known to have orphans, add the sentence and the count; otherwise say that rows without a match are left out.
**Round:** n229.

### B3. SAP table names are refused although the pack recognised the tables

**Where:** `answers.py` / `infer.check_tables`; the hint in `errors.py` (`HINTS["bad_input"]`).
**Sees:** `tables=["VBAK", "VBAP"]` answers "not in the schema: 'VBAK', 'VBAP'" although `plan_backend` says "17
table(s) recognised by the sap pack" for `sap_vbak` and the rest. The hint reads "Check the keys and confirmed you
passed", and the user passed neither; `join_path` with an unknown table gives the same hint.
**Fix:** Resolve a pack name to the table the pack matched, or name it in the error ("VBAK is sap_vbak here"). Word the
hint for names in general: "Check the names you passed (tables, keys, confirmed, start, end)". The hint is in
`tests/golden/hosted_tools.json`, which n227 holds.
**Round:** n229 for the names, n227 for the hint's golden file.

### B4. The synthetic walk of Start Krusgraph shows another plan than the tools give

**Where:** `fabric_backend/start_flow.py` (`start` with `sample=true`), from `demo.py`.
**Sees:** Step 4 says "7 tables, 6 with keys, 6 relationships", step 5 "6 of 6 relationships hold", step 6 asks whether
`orders.ship_to_id` points at addresses. `plan_backend` on the same rows answers 7 relationships, the seventh being that
link by rule R5, "counted and holds: 15 of 15 value(s)". A tester who tries the sample and then the tool sees two
different answers for the same shop.
**Fix:** Build the sample's steps from the tools' own answers on the seed (see idea 3), or say in step 4 that the hosted
plan counts role columns and would already propose the link.
**Round:** n227.

### B5. One plan, four different counts of its links

**Where:** `plan_backend`, `validate_plan`, `review_plan` on `demo_lh` / `dbo`.
**Sees:** `plan_backend`: "24 relationships". `validate_plan`: "32 of 34 relationships hold" and "51 passing check(s)".
`review_plan`: "17 keys and 24 relationships ... 40 passed, 1 failed" (41). Since F2, `plan_backend`'s own answer holds
both: "24 relationships" in the summary and "34 links proposed" in the coverage line. The ten extra are the pack's
`extended_relationships`; no answer says so next to its number.
**Fix:** One sentence where the number changes ("34 = 24 in the plan + 10 the SAP pack lists with a condition"), and the
same total in `review_plan` as in `validate_plan`, or the reason it checks fewer.
**Round:** n229.

### B6. "32 of 34 relationships hold" reads as two failures

**Where:** `validate_plan`'s summary (`evidence.py`).
**Sees:** `totals.relationships` is checked 34, passed 32, failed 1, not_counted 1; the one not counted has "no rows
with a value: nothing to check". The summary line gives only 32 of 34.
**Fix:** "32 of 34 hold, 1 fails, 1 has no rows to check".
**Round:** n229.

### B7. A link counted in the rows is called unverified, and made inactive for it

**Where:** `fabric_backend/graphs.py` (`analyze_schema`), `semantic_model.py`.
**Sees:** `plan_backend` says of `orders.ship_to_id -> addresses`: "counted and holds, 15 of 15 value(s)".
`analyze_schema` lists the same link with `verified: false` and certainty 0.5, and the semantic model draft makes it the
inactive one "because the active path has certainty 0.8, this link 0.5". The links at 0.8 are by name only.
**Fix:** Let the evidence state set the certainty: a link counted and holding ranks above a link by name only, and
`verified` follows the count.
**Round:** new (Engine; F2's evidence states are the input).

### B8. The local plan and the hosted plan differ on the same tables

**Where:** `mcp_server.py` `_plan_on` (no R5 count) against `server.py` `_hosted_plan`.
**Sees:** Shop sample: 6 relationships locally, 7 hosted. `docs/LOCAL.md` said "the same engine".
**Fix:** `docs/LOCAL.md` section 4 now says what differs and that `suggest_relationships` finds the candidates locally.
Counting in the local plan's own call is F2's claimed hook.
**Round:** fixed in F1 (the words); F2 (the counting).

### B9. Local `create_backend` on a SQL Server asks for a Fabric sign-in

**Where:** `platforms/local.py` `OdbcPlatform.unsupported`.
**Sees:** With `FABRIC_SOURCE_KIND=SQLServer`, `semantic_model_draft` and `ontology_draft` answer kind `unsupported` with
the alternative. `create_backend` does not: it goes on to ask for a Fabric token, for a source Fabric cannot serve.
**Fix:** Add `create_backend` and `rayfin_connector`'s Fabric form to the tools `unsupported` refuses for SQLServer.
**Round:** new.

### B10. "0 open" beside an open question

**Where:** `review_plan`'s summary.
**Sees:** Shop: "0 accepted, 0 rejected, 0 open, 13 still proposed" and under it `attention`: "Open question
(key:audit_log): Does audit_log have a key?"
**Fix:** Count the open questions in the summary, or call them "1 question" there.
**Round:** n229.

### B11. Errors name the workspace by its id when the user typed its name

**Where:** `server.py` `describe_backend`, `query_graphql`, `_plan_read` (schema not found), `resolve_source` in
`platforms/fabric.py`.
**Sees:** "no API for GraphQL named 'shop_api' in workspace 11111111-1111-..." from two tools, "in workspace Sales" from
`app_starter`, `app_readiness` and `plan_drift` for the same call.
**Fix:** Keep the word the user typed for the message; the id only when that is what was typed.
**Round:** new.

### B12. The demo chat's status paragraph contradicts itself

**Where:** `fabric_backend/static/chat-demo.js` with the status sentences of `tool_status.py`; "Fix data issues".
**Sees:** "Proposing fixes: tested with unit tests, not yet against a live Fabric workspace; the check itself ran
against one. ... Created in a live Fabric workspace." in one grey paragraph. The first half and the last sentence are
about different things, and the reader cannot tell which. The answer above it shows a field name, "(summed_per_header)",
and "27 row(s)".
**Fix:** One status sentence per thing, each naming its thing ("The silver notebook: created in a live workspace. The
proposed fixes: unit tests only."); the field name out of the sentence.
**Round:** new (Website).

### B13. An unknown step in `start` starts over without a word

**Where:** `start_flow.py`.
**Sees:** `start(step="bogus")` answers step 1 of 9 as if nothing had been asked. A model that misspells a step loses
the user's place and the user is asked for the workspace again.
**Fix:** Answer kind `bad_input` with the nine step keys, or keep the place and say the step was not known.
**Round:** n227.

### B14. The fix plan counts two findings where the check counts one

**Where:** `fix_plan.py` with `validate_plan(fixes=true)`, shop sample.
**Sees:** `needs_attention: 1` and, in the same answer, `fix_plan.counts.findings: 2` (the second is `audit_log` without
a key, which the check does not count as needing attention).
**Fix:** Either count the table without a key in `needs_attention`, or say "1 finding from the check, 1 open question
from the plan".
**Round:** n229.

### B15. The footer and `/trust` can be read against each other

**Where:** `pages.py` `BEHIND` (the footer of every page) and `page_templates/trust.html`.
**Sees:** `/trust`: "Nothing on this page claims ... a partnership with Microsoft". The footer of the same page: "Member
of the Microsoft AI Cloud Partner Program". Both can be true (membership of a programme is not a partnership about this
product), but a careful buyer reads them side by side.
**Fix:** The founder's decision: keep the footer line and add half a sentence on `/trust` that says what the membership
is and is not, or leave the line off `/trust`.
**Round:** new (the founder decides; nothing changed here).

### C1. "(s)" and "(ies)" in answers a person reads

**Where:** 213 places in `fabric_backend/*.py` (`infer.py`, `evidence.py`, `amounts.py`, `fix_plan.py`, `silver.py`,
`drift.py`, `graphs.py` and others); the demo chat on the site shows `fix_plan.py`'s.
**Sees:** "R5 counted 1 code or role column(s) in the rows: 1 counting query(ies)", "8 referenced header value(s)", "13
passing check(s)", "7 silver table(s)", "1 cycle(s)", "up to 27 row(s) per products row", and since F2 "counted in this call: 6 key(s), 6
unique".
**Fix:** One helper (`n_of(1, "query", "queries")`) and a test that no answer of the golden files holds "(s)" (idea 5).
Many of these strings are asserted in tests and golden files of other rounds, so it is one round's job, not a patch.
**Round:** new.

### C2. Table names used as nouns in the next step

**Where:** `evidence.py` / `amounts.py` (`next_steps`, `do_instead`).
**Sees:** `answer_query_draft(question="total list_price per products")`, "total NETWR per sap_vbak", "one row per
products", "sum a order_items amount".
**Fix:** "per row of products", "an amount of order_items"; for a pack table the pack's label ("per sales order").
**Round:** n229.

### C3. "7 links proposed, 1 counted, 1 hold"

**Where:** `coverage.py` headline, on every answer.
**Sees:** "1 hold" for one link.
**Fix:** "1 holds".
**Round:** F2 (it holds the states in `coverage.py`).

### C4. `analyze_schema`'s summary says the size twice

**Where:** `graphs.py` / `server.py` `analyze_schema`.
**Sees:** "7 tables, 6 with keys, 7 relationships; 7 tables, 7 relationships; roles: ...".
**Fix:** Drop the second count.
**Round:** new.

### C5. The data dictionary explains rule K2 in one 600-character table cell

**Where:** `dictionary.py`, the Keys table's "Meaning" column.
**Sees:** A cell that lists fourteen suffixes, the Swedish genitive and the synonym table, in the hand-over document.
**Fix:** One short sentence in the cell and the full rule as a footnote under the table.
**Round:** new.

### C6. Four texts in the Model editor

**Where:** `workload/Workload/app/index.html`, `DataProductView.tsx`, `saveState.ts`, `ModelItemViews.tsx`.
**Sees:** The browser tab's title was the starter kit's "Microsoft Fabric UX Sample Workload"; "1 people and groups have
a role"; "after 1 tries"; "SAP via SAP Datasphere among it".
**Fix:** "Krusgraph Model"; "1 person or group has"; "1 try"; "for example SAP through SAP Datasphere".
**Round:** fixed in F1.

### C7. "item(s)" on the Data product page

**Where:** `DataProductView.tsx`, four places ("1 item(s) this item built from another plan", "item(s) chosen above",
"leftover(s) found", "Delete 3 item(s) from Fabric").
**Sees:** As written.
**Fix:** Singular and plural forms, as `roleLine` now does.
**Round:** n229 if it touches the page for its next-step list, otherwise new.

### C8. A React warning in the editor's test log

**Where:** `app/components/ItemEditor/ItemEditor.tsx`, seen in `npm test` under `reopenFirstPaint.test.tsx`.
**Sees:** "Do not call Hooks inside useEffect(...), useMemo(...), or other built-in Hooks." The tests pass.
**Fix:** Find the hook called inside the effect; React's rule is there because the order of hooks can change between
renders.
**Round:** new (Workload).

### C9. `plan_backend(drawio=true)` answers with a validation trace

**Where:** `tool_params.py`, the `drawio` parameter (a string: `map`, ...).
**Sees:** A model that passes a boolean gets "1 validation error for plan_backendArguments ... Input should be a valid
string [type=string_type ...] For further information visit https://errors.pydantic.dev/...".
**Fix:** Accept `true` as `map`, or answer kind `bad_input` naming the accepted words.
**Round:** n228.

## 3. Fixed in this round

| Finding | Change | Test |
| --- | --- | --- |
| A1 | `mcp_server.main()` answers `--help` and `--version` | `tests/test_f1_findings_fixes.py` |
| A2 | `_execute_factory` and `token_from_az` answer in the user's words with the next step | same file |
| A5 | the clock test sets its commits against the real now | `tests/test_n200_health.py` |
| B8 (words) | `docs/LOCAL.md` section 4 rewritten against the code: 24 tools, which need a Fabric item, which belong to Databricks, what the local plan does not count; `create_backend` is no longer listed as hosted only | same file as A1 |
| C6 | the four editor texts | `workload/Workload/app/items/ModelItem/f1Words.test.ts` |

Everything else is left to the rounds named above. Nothing was changed in the engine's rules, the cards, the site or
the SAP pack.

## 4. Five ideas for a tester to trust Krusgraph sooner

All by rules, no AI in Krusgraph for Fabric, and each says only what it counted.

### Idea 1. A receipt for every number

Each count in `validate_plan` already comes from one SQL statement. Give the tester a file, `krusgraph-receipt.md`, with
one row per claim: the sentence, the SQL that counted it, the count and the time. The tester pastes any statement into
the SQL endpoint and gets the same number, or sees why not. In the Model editor: "Show the query" beside each check.
**Effort:** 1 round.

### Idea 2. Planted faults: show that a failure is found

A first user on clean sample data only ever sees "holds". A sample `shop_faults` (in memory, synthetic) with five known
faults (a duplicate key, a NULL key, an orphan, a doubled total, a renamed column) and a walk where each answer names
the fault that was planted and the count that found it. The list of planted faults is a file in the repository, so the
tester can compare it with what was found. It also serves as a regression test for `tests/corpus/`.
**Effort:** 2 rounds.

### Idea 3. The demo is the tool's own answer

B4 exists because the sample walk and the site's chat are written beside the tools. Generate both from the tools' answers
on the seed at build time, and add a test that fails when a sample step's numbers differ from the tool's. Then "what the
demo shows is what the tool says" is checked on every push, and the site can say so.
**Effort:** 1 round.

### Idea 4. One count, said the same everywhere

B5, B6, B10 and B14 are one problem: each tool counts the plan its own way. One function gives the plan's numbers (keys,
links in the plan, links the pack adds, checked, hold, fail, nothing to check, not counted) and every summary is written
from it, with a test that the tools agree on the two samples.
**Effort:** 1 round.

### Idea 5. A gate on the words

C1, C2, C3 and B11 are words, and words are what a tester judges first. A test over the golden answers and the page
texts that fails on "(s)", on "1" followed by a plural verb form the helper knows, on a table name after "per" without
"row of", and on a workspace id in a message where the call had a name. It runs in the ordinary suite and costs nothing
at run time.
**Effort:** 1 round.
