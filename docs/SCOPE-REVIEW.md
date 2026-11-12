# Scope and credibility review (S1), 12 November 2026

Read-only review of `main` at `4f6e2b8`. Nothing but this file was written. Reviewer: a scheduled Claude session with no
live user. Line numbers are those of `4f6e2b8`.

How it was done: four sub-reviews on the same checkout (site and README claims; the engine; the 40 MCP tools; the
workload and the weekend plan), each asked for file and line. The reviewer re-read the quoted sentences at their lines
and re-ran the SAP findings; findings marked "tried" are small Python probes on invented schemas (no Fabric, no
customer data). Nothing was run against Fabric or the hosted service. The pytest suite was not run; no code changed.

Evidence classes used below: **U** unit tests only; **S** live in the publisher's own tenant on synthetic data (with
date, from `tool_status.py`); **C** a real customer or SAP system: none exists for any capability
(`docs/MISSING-EVIDENCE.md` rows 8 and 9).

## 1. The short version

1. The honest core is real and good: a plan where every key and link names its rule, a row check that counts, and
   answers that say what was not checked. The founder's `plan_backend` answer on `dbo` is the standard, and the code
   that produces it (`infer.py:964`, `compact.py:122-124`) should be the template for every other answer.
2. The engine finds keys and links **by names**. On schemas that follow `<table>_id` it is good. On real ERP shapes it
   misses much or guesses wrong, and says little about what it missed. The repository's own benchmark says so:
   AdventureWorks 47 of 71 keys right, 4 wrong, 20 missed; 62 of 90 links found, 17 wrong
   (`tests/test_inference_quality.py:71-72`). This is the largest credibility risk, larger than any missing feature.
3. On SAP shapes the chain breaks after the check. Every pack link includes MANDT or a second column, the semantic
   model and the ontology take one column per side, and nothing builds a combined key. Tried on the repository's own
   SAP sample: the semantic model draft has **0 relationships, 19 "not expressible"**. It says so honestly, but "ask
   your SAP data in Copilot" cannot hold on a model without relationships.
4. Large schemas are not handled: the check counts keys before links with a ceiling of 200 items, so above 200 keyed
   tables no link is ever counted; no call has a time budget; one failed query aborts the whole check.
5. The site's body text is careful; its headlines, bullets and `llms.txt` drop the qualifiers.
6. Forty tools are too many for a first tester, and the plain word "check" reaches at least nine of them.
7. Weekend plan: build the onboarding guide and a narrow suggestion engine; spend the rest on section 6. The 3D
   plane, AutoML and streaming should wait. "SAP in Copilot" should wait for the combined key.

## 2. The founder's three observations, explained from the code

**"Show my lakehouses" did not mention the `shop` schema.** `list_sources` (`server.py:496-518`) returns names, ids and
types only: no schemas. `list_tables` defaults to `schema="dbo"` (`server.py:523`). Since n218 it appends a `schemas`
list when the source has more than one (`server.py:555-565`), but as the last JSON key after the table list, with no
sentence, and `_schemas_or_none` drops it silently on any error (`:547-552`). Thirty other tools take the same `"dbo"`
default and say nothing about other schemas; only `plan_backend` asks (`:582-586`). Whether the hosted service ran n218
that evening is not known from the repository. Fix, general: `list_sources` returns `schemas: [{schema, tables}]` per
source (the query exists, `SCHEMAS_SQL`, `:603-609`); every schema-taking answer starts with one sentence, "demo_lh
also has schema shop (7 tables), not shown here"; no tool defaults to `dbo` when the source has several schemas.

**"Can we run check against shop?" reached `app_readiness`.** An API named `shop_api` existed, `app_readiness`'s
description opens with "Checks" and returns `checks` (`server.py:2833-2838`), and the tool that does the check is named
`validate_plan`, which needs the user to think "plan". n218 added words to the descriptions and a sentence 40 lines
into the instructions (`server.py:119-121`). That helps but leaves the cause: the names. A plain "check" can still
reach `validate_plan`, `app_readiness`, `plan_drift`, `compare_semantic_model`, `suggest_relationships`, `review_plan`
(`validate=true`), `semantic_model_draft` (`validate=true`), `create_pipeline` ("check pipeline") and `start`. Fix:
rename `validate_plan` to `check_data` (old name kept as an alias) and `app_readiness` to `api_app_gaps`, rename its
output `checks` to `requirements`, and remove `app_readiness` from the default tool list (section 3).

**The drift check was cancelled after about four minutes.** The tool was `plan_drift` (`server.py:1369-1409`). It
compares today's plan with an existing GraphQL API and reads lineage; it is not a data drift check, which is a second
naming problem. Since n218 a 40-second deadline covers the lineage reads (`:1412`), but not the plan itself (two
metadata queries and up to 20 R5 queries at 120 s each, `:1380`) nor the API definition read (`:1388`), and a read
already started is not interrupted. No tool has an overall budget; `validate_plan` can in the worst case issue 200
statements at 120 s each (`platforms/fabric.py:26`). The four-minute ceiling itself is not documented in the
repository (a client or ingress limit; unverified). Fix: one deadline per call, section 6, mechanism 2.

## 3. Inventory and verdicts

Verdicts: **Core** keep and harden; **Narrow** keep, promise less; **Hide** keep the code, take it off the site and
the default tool list; **Cut** remove from the site or freeze.

### 3.1 The chain a tester will walk

| Capability | Evidence | How it fails on real data | How a tester judges it | Verdict |
| --- | --- | --- | --- | --- |
| `plan_backend`: keys and links, each with its rule | S 27 Oct, shop; SAP-shaped `dbo` 2 Nov | Names that are not `<table>_id`: tried, an AdventureWorks-like schema left `BusinessEntityID` tables keyless; a Nordic ERP shape (`Orderhuvud`, `Artikelnummer`, `LevNr`) gave 4 keys of 8 and 1 link, one key wrong; Business Central names keyed every table on a bare `No_` (`infer.py:366`), wrong on Sales Line. Above 60 tables the summary form omits the pack block (`compact.py:72-92`) | Good when names fit. Otherwise: "it missed the obvious ones and guessed one wrong" | **Core**; add evidence states and count-before-claim (section 6) |
| `validate_plan`: unique, null, orphans, counted over whole tables | S 2 Nov (shop 6/6 keys, 7/7 links; SAP-shaped 17/17, 32/34) | Default 60 items, ceiling 200, keys first (`evidence.py:242-244`); `tables=` does not scope it. Plain `s.a = t.b`: no trim, case, leading-zero or cast handling, so `0000012345` against `12345` reads as orphans; blank-as-none only for pack links (`evidence.py:47`). One failing query aborts the call (`evidence.py:255`) | The strongest part when it returns. A false orphan count from leading zeros ends the session | **Core**; needs budget, partial results, representation re-count |
| Doubled totals (amount levels, flat tables) | S 29 Oct, SAP-shaped | Amount columns found by English and Swedish words or the pack (`amounts.py:49-54`); no editor step shows it (`workload_api.py:640`) | The headline of the home page; must be shown, with counts, on their tables | **Core**; give it its own visible step |
| Review: accept, reject, corrections (`review_plan`, the editor) | S 27 Oct; reading a file back U | "Accept all" over hundreds of unchecked items | Useful if the evidence state is on every row | **Core** |
| `list_workspaces`, `list_sources`, `list_tables`, `sample_rows` | S 27 Oct | One schema reported (section 2) | First impression; a missing schema reads as "it cannot see my data" | **Core**; fix this week |
| `start`, the guided path | U only (`tool_status.py:144`) | Untried live; each step inherits the limits above | The right entry for a first tester | **Core**; run it live before anyone else does |
| SAP pack: keys with MANDT, order-to-cash and purchase-to-pay links | U on a schema generated from the pack; S on synthetic `sap_*` tables. Every module `documented`, none verified (`packs/sap/manifest.yaml:6,289`); the SAP pages were not opened (`docs/SAP.md:196`) | Matches by table name after a fixed prefix list (`sap_pack.py:38`). Tried: `VBAK` and `sap_vbak` match; `ecc_VBAK`, `VBAK_800`, `P01_VBAK`, `dbo_VBAK` get no pack, no keys, no links. A schema of Z tables only with VBELN/KUNNR/MATNR: 0 keys, 0 links. CDS view names unknown; MATDOC, MSEG, MKPF absent | An SAP architect will try a prefixed name and a Z table in the first ten minutes | **Narrow** now ("raw table names, not verified on an SAP system"); **Core** once it matches by key-column signature |
| `create_pipeline` (silver, gold, check) | S 7 Nov, three steps succeeded | Silver de-duplicates only on some key rules; gold needs a schema-enabled lakehouse (`gold.py:112`); capacity waits | Works on the sample; on SAP shapes the gold step meets composite keys | **Core** |
| `create_semantic_model` | S 29 Oct, 9 Nov, shop | Composite links are "not expressible" (`semantic_model.py:289`); tried on the SAP sample: 0 of 19 links in the model. Measures sum amounts across currencies; a fact-table SUM rule can sum a unit price | On shop: fine. On SAP: a model with a calendar and no relationships | **Core** on single-column keys; **Narrow** on SAP until a combined key exists |
| `create_report` | S 30 Oct, 7 Nov, figures checked | Never updated in place | A bonus, not a reason to buy | **Narrow** |
| `create_ontology` (Fabric IQ, preview) | S 28 Oct, 2 Nov | Tenant setting off gives 403, said only at Create; composite keys become keyless entities, composite links are skipped (`ontology.py:124-131`) | On SAP: entities without keys or links | **Narrow**; label preview everywhere |
| `create_data_agent` | MCP: dry run only (`tool_status.py:98`); editor created one 9 Nov | No agent answer has ever been scored; Copilot publish is a manual portal step and failed on trial capacity (`docs/DATA-AGENT-PUBLISH.md:76`) | Will be judged by one wrong answer | **Narrow**: experimental, off the default flow |
| `create_backend`, `describe_backend`, `query_graphql` | Update in place S; a new API U (`tool_status.py:229`) | Field mappings on wide tables | Works; not what the architects come for | **Narrow** |
| Suggested data products (n222) | U only | A ticked product changes nothing in the build (`workload_api.py:772-789`); evidence lines are verdict words, not counts; no cap or search in the panel | "It grouped my tables; then what?" | **Narrow**: call them proposed groupings |
| `suggest_relationships`, `analyze_schema`, `join_path` | S 27 Oct, 2 Nov | Fixed per-rule certainty (`graphs.py:25`), not counts | Useful to an expert | **Narrow**; fold `suggest_relationships` into the check |
| Krusgraph for Fabric (the Model item editor) | Founder's runs 9 to 11 Nov, shop; rounds n185 to n223 not run live (`docs/WORKLOAD-DEV.md:1058,1133`); exists only in the publisher's tenant | Map capped at 60 tables and 120 links; the editor never sends `max_items` | Nobody outside the tenant can try it yet | **Narrow**: "pilot, in our tenant" |
| `/check` (CSV, Excel, pasted columns in the browser) | Synthetic examples; no outside user | Pyodide and SQLite in a tab; no size guard found; the first real export can hang it | The cheapest way to lose a tester | **Narrow**: "for samples", with a stated row and file limit |
| Mirrored, Snowflake and Databricks sources | Mocked U; README says so (`README.md:464-489`) | Unknown | Will be asked | **Narrow**: "not run" |

### 3.2 Off the default path

| Capability | Evidence | Verdict |
| --- | --- | --- |
| `plan_drift` (API against plan) | S 27 Oct; long reads (section 2) | **Hide** from the default list; rename when it returns |
| `drift_monitor_draft`, `create_drift_monitor` | Created 28 Oct, never run in Fabric (`tool_status.py:234-235`) | **Hide** until it has run once |
| `create_views` | Dry run only (`tool_status.py:96`) | **Hide** |
| `create_silver_notebook`, `create_gold_views` and the nine `*_draft` twins | Created or drafted; superseded by `create_pipeline` and by each create tool's dry run | **Hide** |
| `app_readiness`, `app_starter`, `rayfin_connector`, the App | S as drafts; the App is pilot-only | **Hide** |
| `dbt_schema`, `domain_draft`, `export_item_definitions`, `compare_semantic_model`, `answer_query_draft`, `lineage` | Mixed; `domain_draft` U | **Hide** |
| `sap_pack_draft` | U | **Hide** unless SAP tables are recognised in the source |
| Ten industry cards on `/use-cases` (`use_cases.py:63-83`) | No dataset behind them | **Cut** from the site, or label "illustrative, not run" |
| Measured seconds on `/check` (`check.html:113`), "about N minutes" (`pages.py:849`) | Local server, seven synthetic tables | **Cut** |
| Databricks drafts, dbt project, Great Expectations and Soda drafts, OpenLineage, the Younium and planning demos | U | **Cut** in the sense of frozen: no rounds until the core holds on real data |

A default profile of about twelve tools would be: `start`, `list_workspaces`, `list_sources`, `list_tables`,
`plan_backend`, the check (`validate_plan`), `review_plan`, `sample_rows`, `create_pipeline`,
`create_semantic_model`, `create_report`, `create_backend`. There is no profile switch today; `switches.register()`
(`server.py:442`) is where `KRUSGRAPH_TOOLS=core|all` would go.

## 4. Sentences that promise more than the evidence

The body text is mostly careful. These are the lines a tester reads first.

| # | Where | Sentence | Why it does not hold | Honest replacement |
| --- | --- | --- | --- | --- |
| 1 | `README.md:5`, `discovery.py:26`, `DOCS.md:5` | "See how your business tables really connect – with the proof behind every link – so your reports, apps and agents get the numbers right." | A name rule is a reason, not proof; `sap.html:17` itself says a pack is "a sourced suggestion, not proof" | "See how your tables connect: the rule behind every proposed link, and the row counts once you run the check." |
| 2 | `DOCS.md:496` | "for ECC and S/4HANA. It does not depend on how the tables arrive: Fabric mirroring of SAP…" | No arrival route was tried; prefixed or suffixed names get no pack at all; CDS views are outside the pack (`docs/SAP.md:218`) | "Written for raw ECC and S/4HANA table names (`VBAK`, `sap_vbak`). Not yet run on an SAP extract, mirrored or otherwise; other naming is not recognised yet." |
| 3 | `DOCS.md:522` | "Yes, for keys and links that use SAP's standard field names, and the rows decide which of those links hold." | A Z table gets no key; a schema of Z tables only gets nothing | "Partly. A Z table gets no key from the pack; next to standard tables its standard fields are linked by rule R3. You add the key in the review." |
| 4 | `discovery.py:210`, `concepts.py:429`, `offering.py:478` | "checks every key … and every relationship" / "Count every link against the rows" / "the counts from all rows" | Default 60 items per call, ceiling 200, keys first | "Counts up to 60 keys and links per call (200 at most), over whole tables, and lists what it did not count." |
| 5 | `README.md:10`, `discovery.py:32`, the home diagram (`offering.py:197`) | "Krusgraph creates silver and gold notebooks, a pipeline, a semantic model, a report, an ontology, a data agent, an API for GraphQL and an App (preview)…" | A flat list over four evidence classes | Add the status per item: "created live on synthetic data: pipeline, model, report, ontology; experimental: data agent, views, a new API; pilot only: App." |
| 6 | `sap.html:5`, under "The proof" at `home.html:94` | "…each with its public source." | The sources were cited from memory and not opened (`docs/SAP.md:196`) | "…each citing a public SAP page; the pages are still to be re-read, and nothing is verified against an SAP system." |
| 7 | `check.html:113` | "With your own files, choosing them is most of the two minutes." | Unmeasured; measured on a local server | Remove; state the file and row limit instead |
| 8 | `check.html:6` | "Drop CSV or Excel exports, or paste a list of columns." | No stated limit | Add: "Meant for samples; tried on synthetic files of a few hundred rows." |
| 9 | `pages.py:849` | "From your tables to a checked plan in about {minutes} minutes" | A scripted demo on seven tables; admin consent comes first | "On the seven-table sample, about N minutes; not measured on a customer schema." |
| 10 | `offering.py:436` | "Each builds the same items in Microsoft Fabric." | Contradicted at `offering.py:199` (the App) | "The hosted products build the same items; the App is Krusgraph for Fabric only." |

Also out of step with the code: `README.md:659` ("none is built") against `health.py`, `product_life.py` and
`sap_mirror.py`; `TRUST.md:159` ("Today, partly" for rate limiting) against `README.md:280` ("not deployed");
`README.md:23` ("Five synthetic examples") against seven buttons in `check.html`.

Wording to copy, already on the site: `sap.html:17` ("a pack is a sourced suggestion, not proof");
`pages.py:1112-1113` ("Tested on a synthetic SAP schema, not on an SAP system or a real installation"); the status
chips in `claims.py:19-25`, which should also sit beside the home diagram's list.

## 5. The classic problems, and whether the solution is general

| Problem | Today | General or special case | Gap |
| --- | --- | --- | --- |
| Keys | Name rules K0 to K5; no rule reads rows, except R5 on bare `code`/`no`/`key` | Special cases by naming convention | A name-guessed key is shown as a key before anything is counted. No search for a unique column set from the data |
| Composite keys | From declared keys, the caller, the pack, junction and header-line rules | General in the plan | Not carried to the model or the ontology: no combined key column is generated |
| Joins that repeat totals | Amount level by header and line; sums before and after the join in the pipeline check | General in design | Amount columns found by name words; currency, unit, sign and cancelled documents not handled (`level_measures.py`, `semantic_model.py:118-147`) |
| Orphan rows | Full count per link | General | No representation tolerance; a link to a non-unique target still counts as "holds" (`evidence.py:331`) |
| Drift | Three things with one word: `plan_drift`, the nightly monitor (names only, never run in Fabric), the pipeline's check | Unclear to a user | One meaning needed: "what changed since the last check", with counts |
| SAP structures | Pack by table name, MANDT in keys, variants for ECC and S/4HANA | A curated special case, honestly labelled | Recognition by name only; nothing verified |
| Z tables | R3 links a Z table to standard tables when it carries their full key | General as far as it goes | No key for a Z table; no use of SAP field names as domains when standard tables are absent |

## 6. Mechanisms that make results credible at scale

| Mechanism | Exists | Missing |
| --- | --- | --- |
| Rule on every key and link | Yes, everywhere (`infer.py:80,146`) | Nothing |
| Counted evidence | After the check: rows, nulls, distinct, orphans | Not on the plan before the check; suggested products show verdict words |
| Confidence class | No. Only a fixed weight per rule (`graphs.py:25`) | One state per item: declared / counted and holds / counted and fails / documented in a pack / by name only / not checked |
| "Not checked" never shown as passed | Mostly: `not_counted`, `not_checked_beyond_max_items`, "All N counted checks passed (M not checked)" (`evidence.py:404-431`) | Soft spots: "holds; but the target key is not unique" counts as passed; `create_backend`'s `checks_passed` is structural; `app_readiness` says "N check(s) pass" about API metadata; answers built from an unchecked plan (model, ontology, agent, views) do not say so |
| Sampling limits stated | Yes: counts over whole tables; R5 on the first 200 distinct values in at most 20 queries (`server.py:297`), said in the note | The 60 and 200 ceilings are not on the site |
| Timeouts | Per statement 120 s, login 30 s, REST 30 to 60 s, `plan_drift` 40 s for part of its work | No budget per call; no partial result; no progress outside the workload (`on_step`) |
| Plain words reach the right tool | Partly, by description text since n218 | Names; a core tool profile; the schema question asked before any default |
| Regression corpus | Good start: golden plans for shop, Northwind, Chinook, TPC-H, AdventureWorks, Sakila, WideWorldImporters (both), two small Nordic fixtures; planted issues for the mill and SAP samples; exact scores asserted | A realistic Nordic ERP (the two fixtures have 5 and 6 tables, written for the rules); Business Central names; SAP with prefixed and suffixed names, Z-only, MANDT dropped, S/4HANA material documents; row-level cases (leading zeros, case, blanks, mixed types); anything at 500 tables or more |
| A score the user can see | No | Coverage, below |
| Degrading on 500+ tables | Summary form above 60 tables; answers cut at 60 000 characters with a note | Tried: the name plan takes about 1 s at 500 tables and 18 s at 2 000; the R5 candidate scan in Python adds about 6 s and 108 s before any SQL (`infer.py:658-683`). At 500 tables the check returned "60 of 60 keys unique, 0 of 0 relationships (checked 60 of 2496)". |

### The five to build first

1. **Evidence state and coverage on every answer.** One shared field on every plan-derived answer and every editor
   row: the state above, plus one headline: "412 tables: 96 with a counted key, 210 with a key by name only, 106
   without a key; 300 links proposed, 58 counted, 51 hold; 240 columns that look like references are unlinked." This
   is the visible quality score. It makes a weak result read as honest instead of broken, and it is what the SAP
   answer already does well.
2. **One time budget per call, with partial results.** A deadline (about 45 s) set in one place and passed to the
   plan, every query and every read. Past it, the answer carries what was counted, "not checked (time)" for the rest
   and the call that resumes. A failed query becomes "not counted: <reason>" for that item, not an aborted call.
   `tables=` scopes the check; links are ordered by importance, not after all keys.
3. **Composite keys carried through.** Silver or gold writes one combined key column per composite key and link
   (the text of `semantic_model.py:289` already describes it), and the model and ontology use it. Without this, no SAP
   source gets a usable model, and every later SAP feature stands on nothing.
4. **Count before claiming, and let the data propose.** A key by name is a candidate until counted unique in the same
   call. Where names give nothing, profile within the budget: columns that are unique and not null are key candidates;
   type-compatible columns whose values are contained in a key are link candidates; names rank them. When orphans are
   above zero, re-count once under trim, case fold, leading-zero strip and cast, and report "N of M match after
   stripping leading zeros". The same mechanism serves AdventureWorks, Nordic ERP, Business Central and Z tables; no
   pack per system is needed for the basics. The SAP pack then matches by key-column signature as well as by name.
5. **A regression corpus with published scores.** The missing shapes above, with expected plans and expected row
   results, asserted exactly as `test_inference_quality.py` does today, and the scores shown on the site as they are.
   An honest "AdventureWorks: 47 of 71 keys by name; 68 after the row profile" earns more trust than a headline.

Small fixes before any tester arrives (hours, not rounds): the schema sentence and `list_sources` schemas; the two
renames and the core tool profile; the sentences in section 4.

## 7. The weekend plan

| Feature | What exists | Minimum credible version | Do not build | What a tester sees | Verdict |
| --- | --- | --- | --- | --- | --- |
| 3D knowledge plane | No code or design. A 2D map capped at 60 tables and 120 links; an unbuilt overview layer in `docs/FABRIC-IQ-AT-SCALE.md` §8.2, which requires that colour is never the only signal and that the keyboard works | The 2D overview for more than 60 tables: areas, then tables, each node and link drawn by evidence state, with the same content as a list | A third dimension. It adds no evidence, and on 500 name-only links it draws a confident picture of guesses | With the 2D overview: where their data is checked and where not | **Wait.** Build the overview only if mechanism 1 is in |
| Suggestion engine (data products, ontology, KPIs) | Products: `workload_api.py:722-789`, community detection over the plan's links, rule and verdict lines; ontology: one entity per keyed table; measures: row count and SUM per numeric column | Three kinds of proposals from one function, each with rule, counts and state, each off by default until ticked: (a) groupings of tables, called groupings, from **counted** links only; (b) entities only for tables with a counted key; (c) measures only for additive amounts, with the currency or unit column named, and "not proposed: amounts in several currencies" when it applies | A KPI catalogue, industry templates, names invented for business concepts, proposals from unchecked links | Fewer proposals, each with a reason they can verify | **Build, narrow** |
| More lifecycle | Health table and alerts (n200), product page with retire and delete (n198), drift monitor: all unit-tested, none run in Fabric; promote is a design text (`docs/PROMOTE-DESIGN.md:3`) | Run what exists once in Fabric and record it. Then one function: "what changed since the last check", names and re-counted keys, within the time budget | Promotion between stages, autonomy levels, an agent, new item states | A dated record that the monitor ran, and a diff they can read | **Narrow**: evidence before features |
| ML suggestions with Fabric AutoML | Nothing. It conflicts with the standing sentence "uses no AI model" (`offering.py:202`); the conditions for changing that are written at `docs/FABRIC-IQ-AT-SCALE.md:600-607` | Later, a notebook draft the customer runs in their own capacity: candidate target column, row count, null rates, leakage warnings from the plan's links | Any model run by Krusgraph; any accuracy figure; anything on the site | Nothing this weekend | **Wait** |
| Data onboarding guide | `start` (unit only), `docs/START-KRUSGRAPH.md`, `docs/PILOT-ONBOARDING.md`; Connect is a design text (`docs/CONNECT-DESIGN.md:3`) | One page and the `start` path saying, in order: what is read and with which permission; which tenant settings each output needs, checked in the dry run and not at Create; every schema listed; the limits (items per check, time per call, table counts tried); what is not supported; how to scope to 20 tables first | Connectors, gateways, Copy jobs, mirroring set-up | They know before starting what will and will not work | **Build first** |
| "Ask your SAP data in Copilot through Fabric" | Data agent creation and Fabric publish; Copilot publish is a manual portal step with no documented REST call (`agent_publish.py:9-12`), failed on trial capacity; `agent_tests.py` writes questions that nobody runs; no SAP-shaped agent has run | After mechanism 3: on the synthetic SAP sample, a model with relationships, an agent, ten fixed questions with known answers scored and published as "8 of 10", and the manual steps and capacity need stated | The sentence on the site; any claim about a customer's SAP; currency-blind totals | A scored list of questions on synthetic data, labelled so | **Wait** for the combined key; then a labelled demo |
| Streaming | Nothing; Eventstream and Eventhouse are named only as outside the sources | A sentence: "not supported" | Everything | The sentence | **Wait** |

Round W0 should read section 6 before designing: the suggestion engine and the onboarding guide both depend on
mechanism 1, and every SAP item depends on mechanism 3.

## 8. The first hour with a skeptical architect

| Minute | They try | Must work | Must say "not supported" or "not checked" |
| --- | --- | --- | --- |
| 0 to 5 | "What can you see?" | Workspaces, sources, **every schema with its table count** | Sources that cannot be read, with the reason |
| 5 to 15 | "Plan this schema" on 30 to 300 tables with their own names | An answer inside the budget; each key and link with rule and state; the coverage line; keys by name marked as candidates | "No key found by name for 106 tables"; "not recognised as SAP: names such as ecc_VBAK" until fixed |
| 15 to 25 | "Check it" | The check tool is reached; counts over whole tables; partial result with a resume call when time runs out | "Not counted: 240 of 300 links"; never "all passed" over a part |
| 25 to 30 | A key they know is composite; a join they know has orphans | The composite key accepted as given and counted; orphans counted, with the re-count under leading-zero and trim rules | A type conversion that failed, per link |
| 30 to 40 | SAP architect: a prefixed table, a Z table, MANDT dropped, an S/4HANA table (ACDOCA, MATDOC) | MANDT first; conditional links explained; variants marked unverified, as on 11 November | "Z table: no key from the pack"; "MATDOC: not in the pack"; "CDS views: not supported"; "not verified on an SAP system" |
| 40 to 50 | "Why does my total double?" on their header and line tables | The level of each amount, lines per header counted, the sum before and after the join | "Amounts in several currencies: not summed" |
| 50 to 60 | "Build it": the dry run, then the model | The dry run names every item and every tenant setting it needs; the model has the relationships the check passed | "19 links need a combined key" until mechanism 3; ontology and data agent: preview or experimental; Copilot: manual, needs paid capacity; streaming, AutoML: not supported |

What ends the hour badly: a schema that is not mentioned; "check" reaching the wrong tool; a call that never returns;
a wrong key stated as fact; orphans that are leading zeros; an SAP model without relationships.

## 9. Limits of this review

- No live run. The live facts are those recorded in `tool_status.py` and `docs/LIVE-TEST*.md`.
- The probes used invented schemas of 3 to 10 tables and generated ones of 500 and 2 000; they show behaviour, not
  rates.
- The hosted build of 11 November is not known from the repository, so the first two observations may partly predate
  n218. The four-minute ceiling is unverified.
