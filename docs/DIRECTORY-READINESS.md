# Directory readiness: the hosted connector against Claude's review criteria

Round DIR1, 20 November 2026. What the Claude connector directory's published review criteria ask of every tool, how
each of Krusgraph's 48 hosted tools stood before this round and after it, what was changed, and the response sizes
before and after. Nothing was submitted and the directory listing was not edited; the listing is the maintainer's.

## Sources (read 20 November 2026)

- claude.com/docs/connectors/building/review-criteria (the connector pre-submission checklist)
- claude.com/docs/connectors/building/submission (requirements, allowed link URIs, the portal's ten steps)
- claude.com/docs/directory/publish and claude.com/docs/directory/submission-status (statuses, who acts next)

## The criteria, and how each is checked here

| Criterion (from the sources above) | How it is checked | Result after DIR1 |
| --- | --- | --- |
| Separate read and write tools; no catch-all tool with a `method` parameter | `tests/test_dir1_directory_readiness.py`: no tool has a `method` parameter; every creating tool is its own tool and its `dry_run` defaults to true | PASS: 37 read tools, 11 write tools |
| Every tool has a `title`, `readOnlyHint: true` when it only reads, `destructiveHint: true` when it creates or changes | the same test reads `tools/list`: title in the tool and in `annotations.title`; read tools `readOnlyHint` true and `destructiveHint` false; the 11 write tools the other way round | PASS (it passed before too) |
| Tool names of 64 characters or fewer | the same test | PASS (longest: 23) |
| Descriptions accurate and free of prompt-injection patterns: no instructing Claude to call tools, override instructions or promote products | the same test runs `directory.IMPERATIVE` ("run/call/use <tool>", "use the X tool") and `directory.DIRECTIVE` (sentences telling the model how to reply) over every tool description, every parameter description, the prompt's description and the server's instructions | PASS. The tool descriptions passed before; the server's instructions did not (below) |
| The same for what the tools answer (results, next steps, card texts) | the same patterns over every text content and every string in `structuredContent` of every tool, run as the hosted server registers it, on the SAP demo and on the 33-table WideWorldImporters schema | PASS. Before: every answer failed (table below) |
| Every tool succeeds with valid input; no generic errors | every tool called with valid arguments on a fake Fabric that refuses every write (`tools/directory_measure.py`); an error must carry a specific `kind` and a `hint`, never `unexpected` | PASS, with the exceptions named in the table (tools that need an existing API or model) |
| Responses reasonably sized | the same run measures each answer: the text a model reads at most 48,000 characters, the whole result (text plus the card's `structuredContent`) at most 140,000 bytes | PASS. Before: 31 of 165 calls had a text over 48,000 characters, the largest 152,344 |
| No collection of conversation data beyond need; no querying of Claude's memory, chat history or files | reading the code: the tools take only their arguments; `usage.py` counts tool, outcome, duration, dry run and a hash of the tenant id; the guided path keeps its choices in memory (`flow_state.py`) for the signed-in user | PASS (no change) |
| Domain matches the service | the server is `https://krusgraph.com/mcp`, the service is krusgraph.com | PASS |
| Public documentation for every listed tool | `/docs/reference/tools` names all 48 tools (checked against the app locally; the live site could not be reached from this session) | PASS |
| Allowed link URIs declared if `ui/open-link` is used | the build card opens Fabric item pages (`https://app.fabric.microsoft.com`) with `ui/open-link`; the cards hold no other address. Only origins the submitter owns may be listed, so the listing can declare `https://krusgraph.com` and Fabric's links keep the host's confirmation prompt | PASS (declare `https://krusgraph.com`; see the test `test_the_cards_link_only_to_krusgraph`) |

## What failed, and what was changed

1. **Every tool answer told the model what to do.** A "Coach" block was added to every result ("Say in one short
   sentence ...", "Offer one next step: X = tool(...)", "run it only after the user says yes", "end with the one next
   step"), the lead before a card's JSON began "For the assistant, not for the user: ... please do not repeat ...",
   and next steps read "Verify what was built: run verify_build with ...". Now the Coach block states where the user is
   and the options ("Possible next step for the user: Check against the rows (validate_plan(...))", "Other options:
   ..."), the lead says what the card already shows ("About the display: ..."), and each step is written as an option
   ("Verify what was built (verify_build with ...)"). The choice stays with the user and Claude. The cards' buttons
   still call the tools directly through the host bridge; what a button puts in the chat is the plain label
   (`plainAsk` in the cards also cuts at the new "(tool with ...)" form), so nothing changes for a person who presses
   a button. The click-through of the guided path (`tests/test_wb15_click_through.py`) is green.
2. **The server's instructions directed the model** (9,132 characters: "call the start tool and follow its steps",
   "say that, offer that step, nothing more", "offer them", "Show its lines as Krusgraph's", "please add no reason",
   "do not send it again"). They are now a description of the server, its tools, their usual order and the facts
   that matter (dry runs by default, nothing deleted, errors with kind and hint), 6,098 characters.
3. **A last pass in one place** (`fabric_backend/directory.py`, `bounded`): every answer leaves the server through
   it, so an instruction to call a tool that a later change writes the old way is said as an option, and an answer
   past 40,000 characters of JSON is folded: its longest texts (file contents) shortened at a line end only as far as
   needed, then its longest lists cut to their first items, with a `folded` entry that says what was shortened and
   that the same call with fewer `tables` returns it whole. The summary, the counts, the error and the hint are never
   shortened. The modules' own functions still return the whole answer (the Fabric workload and the tests use them).
4. **`review_plan` refused a large schema with default arguments** (33 tables: "does not fit in one answer",
   `bad_input`). It now answers successfully: what needs attention, the summary and the tables in groups of 10, each
   the `tables` of one review file.
5. **`plan_backend` answered `unexpected`** when `detail` was not a string (`'bool' object has no attribute
   'strip'`). It now answers `bad_input` with the allowed values.

## Response sizes, before and after

The largest answer per data set, as a host receives it (`python tools/directory_measure.py`; 55 calls per data set,
every tool at least once, the creating tools as dry runs). "Text" is what the model reads; "total" adds the card's
`structuredContent`, which an MCP Apps host gives to the card.

| Data set | Largest text before | Largest text after | Largest total before | Largest total after | Calls with text over 48,000 chars, before → after |
| --- | --- | --- | --- | --- | --- |
| SAP order-to-cash demo (17 tables, `sap_demo.py`) | 63,824 (create_data_agent) | 41,772 (create_semantic_model) | 122,058 (create_data_agent) | 93,501 (validate_plan) | 10 → 0 |
| SAP demo, 36 months (`sap_demo36.py`) | 63,824 (create_data_agent) | 41,772 (create_semantic_model) | 122,058 (create_data_agent) | 91,174 (validate_plan) | 10 → 0 |
| WideWorldImporters, 33 tables (`tests/fixtures/schemas/`) | 152,344 (create_views) | 44,830 (validate_plan) | 301,259 (create_views) | 125,285 (validate_plan) | 11 → 0 |

## Every tool

"Result text" is the patterns above over every answer of the tool on both data sets. "Valid input" is whether the
tool answered successfully with valid arguments on the fake Fabric. "Largest text" is the largest text content of the
tool's answers there, in characters.

| Tool | Title | Read/write | Annotations | Title + hints, name ≤ 64 | Description | Result text before → after | Valid input before → after | Largest text before → after (chars) | What changed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `start` | Start Krusgraph: a guided path (experimental) | read | readOnly, idempotent, openWorld | PASS | PASS | FAIL (16 directives) → PASS | PASS → PASS | 42,000 → 28,167 | `then`, `say` and the Coach block state the next step as an option ("Next: start with workspace set to the one the user names"); the prompt text no longer says "call the start tool" |
| `list_workspaces` | List workspaces | read | readOnly, openWorld | PASS | PASS | FAIL (3 directives) → PASS | PASS → PASS | 495 → 414 | Coach block and next steps state options, not instructions |
| `list_sources` | List data sources in a workspace | read | readOnly, openWorld | PASS | PASS | FAIL (3 directives) → PASS | PASS → PASS | 469 → 388 | Coach block and next steps state options, not instructions |
| `list_tables` | List tables and columns | read | readOnly, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 20,520 → 20,433 | `schema_not_found` hint and the schema-choice hint as facts |
| `plan_backend` | Plan keys and relationships (nothing deployed) | read | readOnly, openWorld | PASS | PASS | FAIL (8 directives) → PASS | FAIL: wrong `detail` type gave `unexpected` → PASS | 43,252 → 41,335 | a `detail` of the wrong type answers `bad_input` with the allowed values, not an `unexpected` error; folded on 33 tables |
| `validate_plan` | Check a schema's keys and links against the rows | read | readOnly, openWorld | PASS | PASS | FAIL (10 directives) → PASS | PASS → PASS | 82,689 → 44,830 | lead and Coach block as facts; folded on 33 tables (detail="full") |
| `review_plan` | Keep the reviewed plan as a file (nothing in Fabric changes) | read | readOnly, openWorld | PASS | PASS | FAIL (6 directives) → PASS | FAIL: bad_input → PASS | 39,260 → 39,120 | a review too large for one answer (33 tables) is now a successful answer split into groups of 10 tables, not a `bad_input` refusal |
| `sample_rows` | Show a few rows of a table | read | readOnly, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 1,532 → 1,445 | Coach block and next steps state options, not instructions |
| `create_backend` | Create or update the GraphQL API (dry run by default) | write (dry run by default) | destructive, idempotent, openWorld | PASS | PASS | FAIL (9 directives) → PASS | PASS → PASS | 43,802 → 39,736 | `would_remove` hint as a fact; next steps after a create as options |
| `rayfin_connector` | Generate Rayfin connector entities | read | readOnly, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 97,693 → 42,384 | folded (33 tables: 98k to 43k characters) |
| `ontology_draft` | Draft a Fabric IQ ontology from the plan (nothing deployed) | read | readOnly, openWorld | PASS | PASS | FAIL (9 directives) → PASS | PASS → PASS | 50,255 → 37,531 | Coach block and next steps state options, not instructions; folded on 33 tables |
| `create_ontology` | Create or update a Fabric IQ ontology from the plan (dry run by default) | write (dry run by default) | destructive, idempotent, openWorld | PASS | PASS | FAIL (9 directives) → PASS | PASS → PASS | 44,111 → 41,561 | Coach block and next steps state options, not instructions |
| `semantic_model_draft` | Draft a Power BI semantic model (TMDL, nothing created) | read | readOnly, openWorld | PASS | PASS | FAIL (5 directives) → PASS | PASS → PASS | 60,449 → 40,586 | Coach block and next steps state options, not instructions; folded on 33 tables |
| `compare_semantic_model` | Compare a Power BI semantic model with the plan (experimental) | read | readOnly, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 11,918 → 11,831 | Coach block and next steps state options, not instructions |
| `join_path` | Shortest join path between two tables | read | readOnly, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 4,336 → 4,249 | Coach block and next steps state options, not instructions |
| `analyze_schema` | Analyse the schema as a graph (roles, centrality, areas, ambiguity) | read | readOnly, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 45,449 → 38,771 | Coach block and next steps state options, not instructions |
| `suggest_relationships` | Suggest missing relationships, checked against the data | read | readOnly, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 51,658 → 29,163 | Coach block and next steps state options, not instructions; folded on 33 tables |
| `data_dictionary` | Data dictionary in Markdown | read | readOnly, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 50,483 → 40,562 | folded at a line end (33 tables: 50k to 41k characters) |
| `dbt_schema` | dbt schema.yml with source tests | read | readOnly, openWorld | PASS | PASS | FAIL (9 directives) → PASS | PASS → PASS | 144,760 → 41,632 | folded (project=true on 33 tables: 145k to 42k characters) |
| `domain_draft` | Draft domains and contracts (experimental) | read | readOnly, openWorld | PASS | PASS | FAIL (9 directives) → PASS | PASS → PASS | 55,289 → 40,856 | Coach block and next steps state options, not instructions; folded on 33 tables |
| `sap_pack_draft` | SAP tables and links the SAP pack recognises (nothing created) (experimental) | read | readOnly, openWorld | PASS | PASS | FAIL (5 directives) → PASS | PASS → PASS | 58,266 → 36,618 | pack status line as a fact; folded |
| `plan_drift` | Compare today's plan with an existing GraphQL API | read | readOnly, openWorld | PASS | PASS | FAIL (3 directives) → PASS | not here: needs an existing API or model; live run of 27 Oct / per tool_status → not here: needs an existing API or model; live run of 27 Oct / per tool_status | 582 → 501 | Coach block and next steps state options, not instructions |
| `create_semantic_model` | Create or update a Power BI semantic model (dry run by default) | write (dry run by default) | destructive, idempotent, openWorld | PASS | PASS | FAIL (10 directives) → PASS | PASS → PASS | 143,409 → 41,768 | after-create steps (refresh) as options; folded on 33 tables |
| `create_report` | Create a Power BI report on a semantic model (dry run by default) | write (dry run by default) | destructive, idempotent, openWorld | PASS | PASS | FAIL (5 directives) → PASS | not here: needs an existing API or model; live run of 27 Oct / per tool_status → not here: needs an existing API or model; live run of 27 Oct / per tool_status | 1,527 → 1,387 | Coach block and next steps state options, not instructions |
| `create_views` | Create or alter T-SQL views in a schema of their own (dry run by default) (experimental) | write (dry run by default) | destructive, idempotent, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 152,344 → 42,575 | folded (33 tables: 152k to 43k characters) |
| `create_data_agent` | Create or update a Fabric data agent from the plan (dry run by default) (experimental) | write (dry run by default) | destructive, idempotent, openWorld | PASS | PASS | FAIL (5 directives) → PASS | PASS → PASS | 103,561 → 40,870 | after-create step and the agent's own "nothing was counted" line as facts; folded on 33 tables |
| `analysis_plan` | Which SAP analyses this data supports, by rules (experimental) | read | readOnly, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 17,616 → 17,529 | Coach block and next steps state options, not instructions |
| `analysis_notebook_draft` | Draft a Fabric Data Science notebook for a recommended analysis (nothing created) (experimental) | read | readOnly, openWorld | PASS | PASS | FAIL (3 directives) → PASS | PASS on the 36-month SAP demo; on the small demo a specific refusal (only 1 month of billing) → PASS on the 36-month SAP demo; on the small demo a specific refusal (only 1 month of billing) | 869 → 788 | Coach block and next steps state options, not instructions |
| `requirements_draft` | Match requirements to the checked SAP data (by rules) (experimental) | read | readOnly, openWorld | PASS | PASS | FAIL (9 directives) → PASS | PASS → PASS | 7,054 → 6,908 | its own next step ("Match the same requirements list on my lakehouse") in plain words |
| `silver_notebook_draft` | Draft a PySpark notebook that builds silver tables (nothing created) | read | readOnly, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 30,402 → 30,315 | Coach block and next steps state options, not instructions |
| `create_silver_notebook` | Create or update the silver-tables notebook in Fabric (dry run by default) | write (dry run by default) | destructive, idempotent, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 31,166 → 31,079 | Coach block and next steps state options, not instructions |
| `gold_views_draft` | Draft gold views as materialized lake views (nothing created) | read | readOnly, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 45,863 → 40,669 | "no schemas" error names create_views as the alternative, not "use create_views"; folded |
| `create_gold_views` | Create or update the gold-views notebook in Fabric (dry run by default) | write (dry run by default) | destructive, idempotent, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 46,652 → 40,689 | as gold_views_draft; folded |
| `drift_monitor_draft` | Draft a nightly drift monitor: notebook, pipeline and schedule (nothing created) | read | readOnly, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 12,131 → 12,044 | Coach block and next steps state options, not instructions |
| `create_drift_monitor` | Create or update the nightly drift monitor in Fabric (dry run by default) | write (dry run by default) | destructive, idempotent, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 13,517 → 13,430 | Coach block and next steps state options, not instructions |
| `create_pipeline` | Create or update the silver, gold and check pipeline in Fabric (dry run by default) | write (dry run by default) | destructive, idempotent, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 53,936 → 40,675 | `jobs.ask` states what runs and that nothing runs without the person's yes; timeout hint as a fact |
| `export_item_definitions` | Export what the creating tools would create, in Fabric's Git format | read | readOnly, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 59,938 → 41,462 | Coach block and next steps state options, not instructions; folded on 33 tables |
| `verify_build` | Verify what was built (by rules, no AI) (experimental) | read | readOnly, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 3,010 → 2,923 | "not checked (time)" says which call reads it, not "run verify_build again" |
| `app_starter` | Starter pack for an app on a GraphQL API | read | readOnly, openWorld | PASS | PASS | FAIL (3 directives) → PASS | not here: needs an existing API or model; live run of 27 Oct / per tool_status → not here: needs an existing API or model; live run of 27 Oct / per tool_status | 563 → 482 | Coach block and next steps state options, not instructions |
| `app_readiness` | What an app still needs on an API or a model | read | readOnly, openWorld | PASS | PASS | FAIL (3 directives) → PASS | not here: needs an existing API or model; live run of 27 Oct / per tool_status → not here: needs an existing API or model; live run of 27 Oct / per tool_status | 563 → 482 | Coach block and next steps state options, not instructions |
| `lineage` | Lineage: what builds on a source's tables | read | readOnly, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 6,601 → 6,514 | Coach block and next steps state options, not instructions |
| `describe_backend` | Describe a GraphQL API | read | readOnly, openWorld | PASS | PASS | FAIL (3 directives) → PASS | not here: needs an existing API or model; live run of 27 Oct / per tool_status → not here: needs an existing API or model; live run of 27 Oct / per tool_status | 537 → 456 | Coach block and next steps state options, not instructions |
| `answer_query_draft` | Suggest a GraphQL or T-SQL query for a question (runs nothing) | read | readOnly, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 2,884 → 2,797 | Coach block and next steps state options, not instructions |
| `query_graphql` | Run a GraphQL query | read | readOnly, openWorld | PASS | PASS | FAIL (3 directives) → PASS | not here: needs an existing API or model; live run of 27 Oct / per tool_status → not here: needs an existing API or model; live run of 27 Oct / per tool_status | 553 → 472 | Coach block and next steps state options, not instructions |
| `publish_catalog` | Publish data products to the OneLake catalog (dry run by default) (experimental) | write (dry run by default) | destructive, idempotent, openWorld | PASS | PASS | FAIL (4 directives) → PASS | PASS → PASS | 54,949 → 40,874 | Coach block and next steps state options, not instructions; folded on 33 tables |
| `qlik_plan` | Plan from a Qlik load script (nothing created) (experimental) | read | readOnly, openWorld | PASS | PASS | FAIL (3 directives) → PASS | PASS → PASS | 21,727 → 21,646 | Coach block and next steps state options, not instructions |
| `qlik_measures_draft` | Draft DAX measures from Qlik expressions (nothing created) (experimental) | read | readOnly, openWorld | PASS | PASS | FAIL (3 directives) → PASS | PASS → PASS | 2,591 → 2,510 | Coach block and next steps state options, not instructions |
| `qlik_reconcile_draft` | Draft SQL comparing Qlik KPI values with the migrated tables (runs nothing) (experimental) | read | readOnly, openWorld | PASS | PASS | FAIL (3 directives) → PASS | PASS → PASS | 3,292 → 3,211 | Coach block and next steps state options, not instructions |

The server's instructions: before FAIL (5 directives: "call the start", "follow its steps", "offer that step,
nothing more", "please add no", "do not send it again"), after PASS. The prompt `start` ("Start Krusgraph") is a
message the user chooses, so it may ask for something; it no longer names a tool call ("Start Krusgraph (the start
tool) and lead me through it one step at a time").

## What is not verified here

- The run is local, on a fake Fabric (`tools/directory_measure.py`): the Fabric REST readers, the SQL endpoint and
  the tokens are replaced; everything between a tool call and those seams is the product's own code. No Fabric tenant
  was read or written in this round. The tools' live record is in `fabric_backend/tool_status.py` (`/docs/reference/test-status`).
- `plan_drift`, `create_report`, `app_starter`, `app_readiness`, `describe_backend` and `query_graphql` need an existing
  API for GraphQL or semantic model; on the fake Fabric they answer `not_found` with a hint. They are not counted as
  successes here.
- Whether a host puts `structuredContent` in front of the model as well as `content` is the host's choice; the sizes
  above give both.
- The directory's automated scan is not public; this report checks the published criteria, not the scanner.

## How to run it again

```bash
python tools/directory_measure.py                 # every tool on the three data sets, largest answer first
python -m pytest -q tests/test_dir1_directory_readiness.py
```
