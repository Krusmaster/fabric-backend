# SM1 audit: the whole path as a first-time user (20 November 2026)

Round SM1 'Smooth'. This is a design and audit round: it measures the path and changes almost nothing. Gustav's
direction: "insanely smooth and fast. Simple. [...] Easy as pie." I walked the guided path the way a first-time user
would, in both surfaces, after WB15 (PR #103), RQ1 (PR #100), MOD1 (PR #26) and AP3 (PR #101) were merged.

**What "measured" means here.** Everything was run locally on 20 November 2026 on `main` at `92bb936`. The chat card ran
under a fake host in Chromium, with the real hosted tools on the synthetic SAP demo (`tests/wb15_fake.py`: 17 tables,
one planted orphan) and the synthetic shop. The editor ran in the Model editor's e2e harness, `workload/scripts/e2e/run.js`,
against the Fabric and SQL doubles. That run passed 24 of 24 flows. Nothing was run in claude.ai or in Fabric. The seconds
below are the product's own time on a laptop. A real host adds network time, each call's trip to Fabric's REST API and
SQL endpoint, and on a typed message the model's turn. None of those were measured. The phone test in PLAN.md (SM8) is
where that gets measured.

To reproduce: `python tools/smooth_measure.py --shots <dir> --out <file>`. It writes the numbers in
`measure-2026-11-20.json` and the screenshots in `media/`.

## 1. The chat path (MCP card, "Start Krusgraph")

Two walks on the SAP demo, plus one on the shop sample:

- **Lazy** taps only the primary button on each step, then the three dry runs. This is the "lazy person's" path.
- **Careful** follows the WB15 click list: tap the choices, run the check, accept the link, find the doubled totals, then
  the three dry runs.
- **Shop** taps "Show me on the synthetic shop sample" and then the primary button.

| Step (card title) | Lazy: taps so far | Lazy: seconds | Words shown (excl. buttons) | Buttons | Fits 390 x 800 | Asks something Krusgraph could decide? |
|---|---|---|---|---|---|---|
| 1 Choose the workspace | 0 | 0.26 | 22 | 4 | yes | **Yes**: one usable workspace, already ticked |
| 2 Choose the source | 1 | 0.68 | 19 | 3 | yes | **Yes**: one lakehouse, already ticked |
| 3 Choose the schema | 2 | 1.03 | 21 | 4 | yes | **Yes**: one schema with tables, already ticked |
| 4 The map | 3 | 1.57 | **101** | 3 | yes (map is the exception) | Yes: nothing to answer |
| 5 Check against the rows | 4 | 1.93 | 27 | 3 | yes | **Yes**: step 6 counts the checks itself, even when this button was never tapped |
| 6 Your decisions | 5 | 2.52 | 45 | 5 | yes | No: the one real question (1 link, 5 of 6 rows found) |
| 7 Doubled totals | 6 | 2.86 | 22 | 3 | yes | **Yes**: read-only, and the model dry run repeats it ("4 header amounts are not summed") |
| 8 Dry run (before tapping) | 7 | 3.23 | 20 | 7 | yes | Partly: three separate dry-run taps |
| 8 after the three dry runs | **10** | **4.17** | **151** (careful path: **193**) | 7 | **no, scrolls** | |
| 9 Confirm the names | 11 | 4.59 | 28 | 3 | yes | Names suggested; confirming them is a deliberate human step |
| 9 Confirmed, Create buttons | 12 | 4.94 | 36 | 4 | yes | Each Create takes 2 taps, so 3 items take 6 more taps |

**Start to the dry run of silver/gold + semantic model + data agent:**
- Lazy: **10 taps, 4.2 s** of local product time.
- Careful: **13 taps, 5.1 s**.
- Typed messages: 1 ("start Krusgraph").
- Desktop (1280 px): the same taps, and 4.5 s lazy / 5.5 s careful.

To the confirmed names it takes 12 taps (lazy) or 15 (careful). Creating three items adds 6 more taps.

Of the 10 lazy taps, **6 answer nothing**: three Nexts on preselected choices, Next past the map, Next past a check that
step 6 runs anyway, and Next past a totals step the dry run repeats. Only 1 tap is a real decision (the link). The other
3 run the three dry runs one at a time.

**The shop sample:** 6 taps to step 9 in 2.7 s. Steps 1-3 are skipped.
- Step 8 has **no dry-run buttons**: it is a list of what would be built.
- Step 9 ends on "Start on my data" / "Show the dry run again".
- Until this round, steps 4, 5, 7, 8 and 9 had no sentence of their own, so the card showed the coach's line. On step 7
  that line was **the previous step's**: "A few links need you: I show the counts" (`media/shop-390-step7-before-sm1.png`).
  SM1 fixed this (see section 6).

Screenshots, 390 px at 2x (fake host; not claude.ai):
- `media/chat-390-step1-workspace.png`
- `media/chat-390-step4-map.png`: the eight-table map with `MANDT + VBELN` labels, before anything is asked
- `media/chat-390-step6-decide.png`
- `media/chat-390-step8-dry-runs-full.png`: three blocks with nested folds
- `media/chat-390-step9-confirmed.png`

Desktop, 1280 px:
- `media/chat-desktop-step1-workspace.png`: the card stretches to the full width, and the mascot looks small next to a
  1,800 px bubble
- `media/chat-desktop-step8-dry-runs.png`

## 2. The Fabric workload editor (Model item)

The main path, from `run.js` flows 1-6 on the synthetic shop in `demo_lh`:

| Screen | Clicks | What the user does | Notes |
|---|---|---|---|
| Empty | 1 | Choose a source | Opens Fabric's OneLake picker; its own clicks in real Fabric are not counted (the harness answers at once) |
| Source | 1 | Find keys and relationships | The one schema with tables is preselected; an empty schema is disabled |
| Keys and links | 2 | Check against the rows, then Accept all that passed | "Accept all (n)" and "Accept all that passed the check (n)" side by side; Check is optional |
| Keys and links | 1 | Next: choose what to build | |
| Choose | 2-3 | Tick Semantic model, Data agent (and Pipeline) | **9 output cards, only API for GraphQL ticked by default**; each ticked card adds a name field, permissions and options (`media/editor-desktop-5-choose.png`, `media/editor-390-choose.png`: several phone screens) |
| Choose | 1 | Preview | |
| Dry run | | Create | |

**Clicks from opening the item to the dry run of pipeline + semantic model + data agent:**
- **9** (10 if GraphQL is unticked); the minimum is 7 if Check and Accept are skipped.
- Find keys took 0.9 s on the doubles. The other seconds were not measured separately: the e2e run waits fixed
  settle times.

The two surfaces disagree on the default build:
- The chat builds **pipeline + semantic model + data agent**.
- The editor ticks **API for GraphQL** and leaves the pipeline off.

So the "safe, simple solution" is a different thing depending on where you start.

Screenshots, desktop: `media/editor-desktop-1-empty.png`, `-3-review.png`, `-5-choose.png`, `-6-preview.png`.
Phone: `media/editor-390-review.png`, `media/editor-390-choose.png`.

## 3. Dead ends and hand-offs

| # | Where | What happens | Proposed fix (round) |
|---|---|---|---|
| D1 | Start card after the Create buttons | Nothing follows: no "what now" (report, schedule, share, a second source); `start_flow.py` has no `after` at `create` | One closing step: "Open in Fabric", "Add another source", "Schedule it" (SM2) |
| D2 | Shop sample, step 9 | Stops on "Start on my data"; step 8 has no dry-run buttons | The sample's dry runs as buttons, the same as on your own data (SM2) |
| D3 | A host that runs no tool from the card | Every button becomes "Type this in the chat: ..." | Kept as the fallback; measure how often it happens in the usage digest (UM2) |
| D4 | Other cards (check, review, build): the pipeline and data-agent dry runs | Sentences for the chat, not buttons (`mcp_apps_next.py`) | Every path card hands back to the living start card at the right step (SM4) |
| D5 | Workspace with 2+ lakehouses (layouts (a) and (b) in MULTI-LAKEHOUSE.md) | Step 2 shows N buttons, Next is disabled ("Choose a source first."), and there is no suggestion | Suggest by name rules (bronze/raw = source; one per source); keep one tap (SM5) |
| D6 | Editor: data agent | Never verified in Fabric; the double has no route (shows Try again) | Live round with Gustav's ok (SM8) |
| D7 | Editor: drift monitor and app readiness cards | "Copy the request for Claude": a typed hand-off (`nextSteps.ts`) | A Dry run/Create pair, or hide them until they have one (SM3) |
| D8 | Editor: schemas cannot be listed | A typed schema field | Keep, but prefill `dbo` (SM3) |

## 4. Every tool and card that starts or continues a path

48 tools are registered (`server.py`), 11 of them creating (dry run by default), plus one prompt, `start`. The coach is
not a tool: it is a block added to every answer.

| Role in the path | Tools today | Proposal |
|---|---|---|
| Start | `start` tool, the `start` prompt, `start sample=true`, `requirements_draft sample=true`, the prompt's `use_sample` | **Keep `start`** as the only door; the samples are a `start` choice |
| Choose data | `list_workspaces`, `list_sources`, `list_tables` (start's steps 1-3 read them itself) | Hide from the default listing |
| Map | `plan_backend`, `analyze_schema`, `suggest_relationships`, `join_path`, `data_dictionary`, `sample_rows` | Keep `plan_backend`; hide the rest (advanced) |
| Check | `validate_plan` (also with `fixes=true` for totals), `review_plan`, `verify_build`, `compare_semantic_model`, `plan_drift`, `app_readiness` | Keep `validate_plan` and `review_plan`; the others belong after a build and are offered only there |
| Dry runs | `create_*` with `dry_run=true` **and** `semantic_model_draft`, `ontology_draft`, `silver_notebook_draft`, `gold_views_draft`, `drift_monitor_draft`, `export_item_definitions` | Each `*_draft` duplicates its create tool's dry run: fold them into it, keeping the names as hidden aliases for old prompts |
| Build | `create_pipeline`, `create_semantic_model`, `create_data_agent`, `create_report`, `create_backend`, `create_ontology` + parts `create_silver_notebook`, `create_gold_views`, `create_views`, `create_drift_monitor`, `publish_catalog` | Keep the first six and `publish_catalog`; hide the parts the pipeline already makes |
| SAP / requirements | `requirements_draft`, `sap_pack_draft`, `analysis_plan`, `analysis_notebook_draft` | One entry: a "What do you want to answer?" choice on start's step 6 |
| Apps and queries | `answer_query_draft`, `query_graphql`, `describe_backend`, `app_starter`, `rayfin_connector`, `dbt_schema`, `domain_draft`, `lineage`, `qlik_*` (3) | Off the default listing; offered by the coach where they fit |

Cards:
- **start**: the living card.
- **validate-plan**, **review** and **build**.
- **next** and **result**: shared scripts, not cards.

**Result:** about 15 tools in the default listing instead of 48, with no capability removed. Today no switch hides
tools other than `KRUSGRAPH_READ_ONLY` and `KRUSGRAPH_NO_ROW_VALUES`, so SM4 adds one.

## 5. The five biggest frictions

| # | Friction | Number today | Target |
|---|---|---|---|
| F1 | Taps that answer nothing | 6 of 10 lazy taps to the dry runs; 9 steps where 1 decision is needed | 4 taps to all three dry runs (Start, Looks right, the decision, Dry run everything) |
| F2 | Dry runs are three taps and a wall | 3 taps; 151-193 words; the only step besides the map that scrolls at 390 px | 1 tap, 3 lines of ≤ 25 words in all, the details on tap |
| F3 | The map comes before the question, in SAP field names | 101 words and a diagram with `MANDT+VBELN` labels on step 4 | "17 tables, 24 links, 1 needs you" plus the map on tap |
| F4 | Two surfaces, two defaults, 48 doors | Editor: 9 clicks, 9 checkboxes, GraphQL preticked; chat: pipeline+model+agent; 48 tools | One default build (pipeline + model + agent) everywhere; editor ≤ 5 clicks; ~15 tools listed |
| F5 | Dead ends and quiet stops | D1, D2, D5 above; nothing follows Create; a 2-lakehouse workspace blocks Next | Every step has a forward button; a multi-lakehouse workspace gets a suggestion |

## 6. Fixed in this round

- The sample's steps 4, 5, 7, 8 and 9 each have their own sentence (`start_flow.SAMPLE_SAY`). Before, step 7 said
  "A few links need you" (step 6's) and step 9 said "Try a dry run" (step 8's). Each sentence is at most 15 words.
  Test: `tests/test_wb15_click_through.py::test_sm1_each_sample_step_says_its_own_sentence`.
  Before and after: `media/shop-390-step7-before-sm1.png` and `media/shop-390-step7-after-sm1.png`.
- `coach.py`'s docstring still said "Step N of 8"; it now says "Step N of 9", as the code does.
- `tools/smooth_measure.py` and `tools/smooth_measure.js` are the measurement used above, so every later round can
  measure the same way.

## 7. After SM2: five steps (21 November 2026)

Round SM2 (PLAN.md row 1) changed the start card from nine steps to five: **Your data** · **Check** · **Decide** ·
**Dry run** · **Create**. Measured with `tools/smooth_measure.py` on the same synthetic SAP demo and fake host, locally,
before and after the change on the same machine; raw numbers in `measure-2026-11-21.json`. Nothing was run in claude.ai
or in Fabric, so the phone test (SM8) still has to confirm them.

| | Before (9 steps) | After (5 steps) |
|---|---|---|
| Lazy: Start to all three dry runs, 390 px | 10 taps, 4.2 s | **4 taps, 2.8 s** |
| Careful (accept the link), 390 px | 13 taps, 5.7 s | 5 taps, 3.2 s |
| Most words on one step, besides buttons | 151 (lazy) / 193 (careful), the dry runs | ≤ 25 on every step |
| Most buttons on one step | 7 | 3 plus Next |
| Steps that scroll at 390 x 800 | the dry run | none, the dry run included |
| The shop sample to its dry run | no dry-run buttons | 2 taps to the dry run, 3 to its result, from `start sample=true` |
| Tools listed | 48 | 48 (SM4) |

What changed for the person:
- **Your data.** The start tool chooses a workspace, source or schema itself when it is the only usable one and reads
  the next, so the first card says "demo › demo_lh › dbo ✓" with **Change** and **Next: Check**. With two or more, the
  card lists them as before; the last choice goes straight to Check.
- **Check.** The map, the row check and the doubled totals run on their own (review_plan's file with the checks
  counted, one read) and are one line each: "17 tables, 24 links, 1 needs you." · "40 of 41 checks hold." · "3 header
  amounts would count twice." The map, the rules in words and every count are under Details.
- **Decide.** The question, "5 of 6 found (83%).", Accept and Reject; Next leaves an open decision open (Skip is gone
  from the card, the reasons are under Why).
- **Dry run.** One **Dry run everything** button runs the pipeline, model and agent dry runs one after another in the
  card, one line each ("✓ demo_lh_model"); each tool's answer is under Details. The single dry runs are there too.
- **Create.** Confirm the names, one Create per item (each on a second tap), then **Next: what now?**: **Open in
  Fabric**, **Add a source**, **Schedule it** (D1).
- **The sample** has the same steps and the same Dry run everything button (D2); it starts on Check.
- Moved into Details: the "Mascots: on" switch, the shop-sample button when you have data, the map, the separate
  Check and Find doubled totals buttons, the three single dry-run buttons.

The names of the nine steps still work as `step` (map and totals open Check; workspace, source and schema open the
list on step 1), so an older card or a typed request lands on the right step.

## 8. After SM3: the same path in the editor (21 November 2026)

Round SM3 (PLAN.md row 2) gave the Fabric editor (the Model item) the chat's five steps and default build. Measured
with the editor's e2e harness (`workload/scripts/e2e/run.js`, flow 26) on the Fabric and SQL doubles, locally, the
same flow on the editor before and after the change; raw numbers in `measure-editor-2026-11-21.json`. Fabric's own
OneLake picker is answered at once by the harness, so its clicks in real Fabric come on top. Nothing ran in Fabric.

| | Before | After |
|---|---|---|
| Open to the dry run of pipeline + semantic model + data agent, desktop | 8 clicks, 3.8 s | **4 clicks, 2.3 s** |
| The same at 390 px | 8 clicks, 3.6 s | **4 clicks, 2.3 s** |
| Steps and their names | 6: Source · Keys and links · Choose · Dry run · Built · Data product | **5: Your data · Check · Decide · Dry run · Create**, as in the chat |
| Ticked by default | API for GraphQL | **Pipeline (with its silver and gold notebooks), semantic model, data agent**, as in the chat |
| Output cards shown on Choose | 9 | **3**; the other 6, the data product and the suggested products under **More outputs** |
| Words above the outputs on Choose | 45 | 23 |
| Accept-all buttons | 2: "Accept all (n)" and "Accept all that passed the check (n)" | 1: **Accept all that passed the check (n)** |
| Cards that hand a typed request to Claude | 2: the drift monitor ("Copy the request for Claude") and "Ask Krusgraph in Claude for app_readiness" | 0 |

The chat was not changed: `tools/smooth_measure.py` on this branch, Start to all three dry runs in 4 taps, 2.3 s.

What changed for the person:
- **Check runs on its own.** Find keys and relationships reads the lakehouse and then checks the keys and links
  against the rows, in one wait. "Check against the rows again" stays one click away.
- **Decide** is Choose what to build: the three defaults ticked, each with its name. Ticking or unticking the pipeline
  ticks its silver and gold notebooks with it. A next step's Dry run (an ontology, say) opens More outputs with it ticked.
- **Dry run** is the button's name (it was Preview). Create, the result and the data product are step 5.
- Hidden until they have a Dry run and Create here (D7): the drift monitor card. Microsoft's app builder card keeps
  its guide and no longer sends the person to Claude first.
- Kept and folded into the steps: WB4's Recommended analyses (under the result, after the check), WB14's Save to
  lakehouse Files (beside Download under the map).

One test reads both surfaces: `tests/test_sm3_same_path.py` (the five words and the default outputs in
`start_flow.py` and in the editor's `stepWords.ts`). Screenshots: `media/editor-sm3-desktop-choose.png`,
`media/editor-sm3-390-dry-run.png` (before: `media/editor-sm3-390-dry-run-before.png`).

## 9. After ED1: Gustav's editor test (21 November 2026)

Gustav opened the Model item in Fabric at about 12:30 UTC on the shop sample (`shop_lh` / `shop`, 7 tables). The goal:
one sign-in and one approval; every other choice a visible default that can be changed and never has to be. The editor
he saw was the one deployed before SM3: the Deploy runs for SM3 and the next commits were skipped because `main` moved
on while CI ran (`deploy.yml` deploys only main's tip), so the six old step names were still live. ED1 fixes what he saw.
Nothing ran in Fabric.

| What he saw | Before | After |
|---|---|---|
| Output cards on Choose | a broken image beside every title | the Fabric icon: the production bundle carries each icon file, byte for byte, as a `data:` URL (no second request), and the served copies under `/assets/fabric-icons/` stay; `tests/test_ed1_editor.py` fetches every `/assets/` path the built bundle references through the workload host (200, the package's exact bytes) |
| Help text | "…a lakehouse of this workspace.Silver and gold go to…" | one line; `ed1Editor.test.tsx` reads every Choose state, open and shut, for a sentence run into the next (`ed1Words.JOINED`) |
| Data product built so far | "Owner: … Plan ?." | "Owner: <name>." until the plan is known, then "Plan p-…" |
| Decisions on Choose (a build in a new workspace) | **16**: Build in, "Lakehouse for silver and gold: choose one", Make a lakehouse, 3 ticks, 3 names, Run once, Schedule, the agent's layer, Publish, 3 Permissions folds | **4**: the 3 ticks and **Change** |
| Where silver and gold go | a dropdown, a checkbox and a sentence that contradicted them ("the first lakehouse by name") | one line, read from the request the dry run sends: "Silver and gold go to a lakehouse shop_lh_krusgraph in this workspace. Create makes it if it is not there yet." (or "…go to sales_lh in this workspace." when one is chosen) |
| Names | a text box per output | shown ("Name: shop_lh_pipeline"), from the rule `<source>_<suffix>`; text boxes under Change |
| Report | an empty free-text "Built on" | "Built on: shop_lh_model (the semantic model above)", following the model's name; with the model unticked, the model this item built before, else "A report needs a semantic model: tick Semantic model, or choose one under Change."; Change offers a picker of the workspace's semantic models, no free text |
| Other outputs that read another | nothing said | "Built on: …" for the data agent (its layer), the ontology and the semantic model (the silver tables this build writes) and the API for GraphQL (the source's tables) |
| Keys and links | "Accept all that passed the check (0)" shown | hidden at 0 |
| "3 not checked" | a count | one line: which ones and why ("Not checked: the key of audit_log (audit_log has no rows); …"); those a check would count (changed since the check) are checked again on their own, once per plan |
| Onto's doubled totals | "134 order_items rows over 60 orders rows: an amount on orders summed over order_items would count each orders row 2.2× on average." | "Summing an orders amount over order items would count each order about 2 times; sum order items per order first." |
| Step names | 6 in the editor he saw, 5 in the chat | 5 in both (SM3, now deployed): Your data · Check · Decide · Dry run · Create; Data product is shown after Create, not as a step (`tests/test_wb15_click_through.py`, `test_ed1_…`) |

Counted on the rendered Choose step by `ed1Editor.test.tsx` (every enabled checkbox, radio group, text box, button and
Permissions fold visible without opening anything; the Dry run button and the More outputs fold not counted).

Where silver and gold go in another workspace is now a default with a name: Create makes `<source>_krusgraph` there,
or uses it when it is there (n221's "Make a lakehouse", ticked for you). Choosing another lakehouse is under Change.

Not drawn: a line from the semantic model to gold. The model, like the API, the ontology and the agent on silver,
binds to the tables the build writes or reads, not to the gold views (`fabric_backend/data_flow.py`, "Building them on
the gold views is a later option"); the data flow already draws the report on the model. Drawing model → gold would
say something the build does not do.

The chat was not changed: `tools/smooth_measure.py` on this branch, Start to all three dry runs in 4 taps (lazy, 390 px
and desktop), at most 25 words per step, no step scrolls; 3.0 s locally against 2.8 s on `main` (the same steps; the
difference is the laptop's load while the editor's e2e ran beside it).

## 10. After ED2: Dry run and Create finish or explain once (21 November 2026)

Gustav's second editor test (about 12:40 to 12:55 UTC, the shop sample, a Model item in a workspace with no lakehouse,
`shop_lh` read from another workspace) went past the dry run to two Creates. What he saw, and what Krusgraph does now.
Every rule is deterministic; nothing here uses AI.

| # | Before | After |
|---|---|---|
| 1 | The dry run said "Checked against the rows (2026-11-11 20:23 UTC)" and listed a rejection and a "no longer suggested" product minutes after a fresh check: a re-read of the item's saved review, started when the item opened, replaced the check run meanwhile | The editor keeps the freshest review (`ed2Create.freshestReview`, by the newest check time); the dry run counts that one and shows its check time; when the saved review was older it says so once |
| 2 | Choose: "Owner: (the signed-in person)"; dry run and result: "nobody has chosen one yet" | One sentence everywhere (`ownerLine`, `workload_api.owner_words`): the owner chosen, else the signed-in person, "Change it on the Choose step." |
| 3 | No lakehouse in the workspace: "2 of 6 created, 1 creating, 3 failed", the same long error per output, Try again off, "Plan ?." | The dry run says "Create will make the lakehouse shop_lh for silver and gold." and goes on; Create stays off while a blocker the dry run knows remains, with one line and one fixing button; after a partial result one "Fix and finish (N not built)" builds only what is missing; an error shared by several outputs is said once; Try again shows only where it can work, else the reason |
| 4 | HTTP 409 for `shop_lh_krusgraph_test` | The name is checked against the workspace's items before Create; a lakehouse of that name is used; a name taken by another item, or held by Fabric after a delete (409), moves to the next free name (`_2`, `_3`, ...), said once. The default is named after the data product (`shop_lh`), never `_test` |
| 5 | Silver failed, gold was created anyway | Built in order (`ed2Create.BUILT_ON`: silver, gold, the pipeline, the model, its report and the agent); what is built on a failed output is not sent and says once "Waiting for silver" |
| 6 | The report gave up after 3 tries on the new model's definition (404) and asked for Create again, with Try again off | In the editor's background step the report waits longer (5, 10, 20, 40, 60 and 90 s; Fabric's long-running operations are polled with waits, learn.microsoft.com/rest/api/fabric/articles/long-running-operation); if it still fails, Try again sends only the report |
| 7 | "already built ... Choose a new name to make another one" | An item this Model built from an older plan is updated in place ("Updated in place (this item built it from an older plan)."); the semantic model's card says in one line what it reads |
| 8 | "Creating runs nothing and schedules nothing ... Krusgraph adds none" | Run once after Create is the default (changeable); no schedule stays the default, with one line on how to add one |
| 9 | The Data product card listed 16 items with duplicates from earlier Creates, each with an Open button | This build's items, one line each with its status and Open; earlier builds under one collapsed "Earlier builds (N)" with "Clean up earlier builds", which opens the Delete dry run of exactly those items (nothing is deleted without the person's confirm) |
| 10 | Three groupings of the shop's tables (dry run, Data products, the site) | One function, `domains.data_products`: the plan the review left, by its rules; a row check adds evidence but never moves a table |
| 11 | "Create api for graphql", "Plan ?." | Labels keep their case in a sentence ("API for GraphQL"); the plan is named only when known |

Tests: `tests/test_ed2_create_finishes.py` (fake Fabric: a 409 name moves to the next free one; a name taken by a
notebook; a lakehouse of that name used; no lakehouse in the workspace; the report's model read 404 four times, then
drawn; the owner; one grouping; today's check in the dry run) and `workload/Workload/app/items/ModelItem/ed2Create.test.ts`
with `createEach.test.ts` (silver fails, gold is not created; Fix and finish sends only the missing outputs and reuses
what exists; the same error once; the blocker and its button).

## 11. After SM4: fewer doors (21 November 2026)

PLAN.md row 3. Measured with `python tools/smooth_measure.py --tools` (the synthetic SAP demo behind
`tools/directory_measure.py`'s fake Fabric, cards on, no write possible); raw numbers in
`measure-tools-2026-11-21.json`.

| Measure | Before (main, 21 Nov) | After SM4 |
|---|---|---|
| Tools in `tools/list` by default | 48 | **16** |
| Tools with `KRUSGRAPH_ADVANCED_TOOLS=1` | (no such setting) | 48 |
| Cards whose last state has no way on (a button for a listed tool, a hand-back to Start, or a link) | 1 (`create_report` on a missing model: only "Explain this") | **0** |
| Card buttons for a tool outside the 16, judged against the 16 | 5 (`gold_views_draft`, `semantic_model_draft` on the dbt, domains and requirements cards) | **0** |

What changed:
- `fabric_backend/tool_listing.py` holds the default listing: start, plan_backend, validate_plan, review_plan,
  requirements_draft, the six creating tools of a data product (create_pipeline, create_semantic_model,
  create_data_agent, create_report, create_backend, create_ontology), publish_catalog, verify_build, lineage,
  describe_backend and query_graphql. `describe_backend` stays beside `query_graphql`, because a query needs the API's
  field names. `requirements_draft` (RQ1) is in the default listing. The `krusgraph` CLI (CL1) is not an MCP tool and
  is not affected.
- Every other tool is still registered and answers a call by its name; only `tools/list` leaves it out.
  `KRUSGRAPH_ADVANCED_TOOLS=1` lists all 48 again. The n123 switches (`KRUSGRAPH_READ_ONLY`, `KRUSGRAPH_NO_ROW_VALUES`)
  still apply on top.
- A card's step for a draft becomes its creating tool's dry run (semantic_model_draft → create_semantic_model,
  ontology_draft → create_ontology, the silver, gold and drift drafts → create_pipeline). A step for another unlisted
  tool is left out. With the setting on, the steps are as before.
- A card with no way on gets one step: **Back to Start: <step>**, a sentence for the chat that continues the living
  Start Krusgraph card at the right step (data, check, decide, dry run or what next), with start's arguments, the
  same way next_rules' "Decide the open links" does.
- The server's instructions say, as facts, which tools are listed and that the others answer by name.

Not done here: the drafts are not yet literal aliases (one code path) of their create tool's dry run; they keep their
own answers and goldens, and only the cards' buttons point at the dry run. The local stdio server (`mcp_server.py`) is
unchanged. The chat path is unchanged (`tests/test_wb15_click_through.py`).


## 12. After ED3, part 2: the Data product step, the catalog and the handover files (21 November 2026)

The rest of Gustav's third editor test (points 5 to 8). Deterministic rules; nothing here uses AI.

| # | Before | After |
|---|---|---|
| 5 | The drift monitor card: "a Krusgraph tool in Claude, not in this item" | SM3 already took the card off the Next page (it had no Dry run here); the result's verify step says in one line why there is no monitor of its own here (the pipeline's first step compares the source with the plan on every run). A Create of the drift monitor from the item is not built in this round |
| 6a | "Nobody is the owner yet", and "Owner of the data products (optional)" with an empty picker and Me again under Publish to OneLake catalog | The owner is filled: the one chosen, else the signed-in person by default ("Owner: … (you, by default). Change it below."). Publish to OneLake catalog asks for no owner: it uses the data product's, set in one place |
| 6b | "Built. The latest Create built it, but this item has no id saved for it. Look for leftovers below … Adopt adds it here." | When the page opens, an output the latest Create built without a saved id is looked up by Krusgraph's plan marker and added when the marker is this data product's plan and the name is the one Create gave it: "Found and added: …", once. Look for leftovers stays for every other case |
| 6c | "Read Fabric again" as a main button | Fabric is read when the page opens and after every action; a small Refresh stays |
| 6d | Failed rows (silver 409, report 404) repeated Fabric's long error | One line per failed row and one "Fix and finish (N not built)", ED2's action; Fabric's message under Details |
| 6e | "Health: not checked yet since this Create"; "Last pipeline run: none recorded" | One "Check health now" button beside the health line; the last run is the one ED2's Run once records |
| 7a | The preview proposed a description for the source `shop_lh`, which lives in its own workspace | The catalog step reads the workspace the data product was built in (the item's); only what this data product built is written by default. The source is never treated as built here, even when an earlier write left Krusgraph's plan marker on it, and is offered unticked: "shop_lh belongs to its own workspace; tick to describe it too". A ticked item in a workspace where writing is off is refused |
| 7b | "Owner: <name> (<email>)" in descriptions | No e-mail address in any description, contract or handover text: the name only. The contact goes only into the Purview request's `add_by_hand.owner`, the data product's Owners a steward sets in Purview. Fabric items have no owner field; the owner is kept in this item (outputs.json) |
| 7c | "customers: 5 tables … 4 of 4 keys unique" beside "5 of 5 keys unique" and one product while the plan has two | Cards, contracts and lines use ED2's one grouping (`domains.data_products`); every data product is listed; the recorded check is the source, and what it did not reach takes this step's fresh count |
| 7d | The notebook's After text appended the data-product sentence to its starter text | One template for every item Krusgraph built: "Krusgraph <type> <name>. Data products … checked by Krusgraph: …" |
| 8a | A pasted `contracts/customers.odcs.yaml` held the whole `purview.json` | Not reproduced: each Download and each Copy gives exactly its file (tested for every file); each file is valid YAML or JSON and none contains another. Most likely two pastes in one |
| 8b | `purview.json` starts with a retirement statement | Kept, now word for word from learn.microsoft.com/en-us/purview/unified-catalog (ms.date 2026-10-13, updated 2026-11-12, read 21 November 2026): "Microsoft Purview Unified Catalog and classic Microsoft Purview data governance capabilities (formerly Azure Purview) are being retired. Microsoft is consolidating its data governance capabilities in Microsoft Fabric. New Microsoft Purview data governance accounts can no longer be created, and existing data governance capabilities will remain in maintenance mode through November 12, 2027." The file carries the page and the date |
| 8c | The owner's e-mail in a Purview description | Only in `add_by_hand.owner` |
| 8d | One "customers" contract for 5 tables | One contract per data product of the one grouping |
| 8e | Products' rules "not counted" | A key or link the recorded check did not reach takes this step's fresh count (proven when it holds); any still not counted are said once, with why |
| 8f | "Write 2 changes as me" disabled after ticking, with the operator's list in small text | Where writing is off, no checkbox; beside the disabled button: "Writing is off in this workspace while Krusgraph is in test; use the handover files." |

Tests: `tests/test_ed3_catalog_handover.py` and `workload/Workload/app/items/ModelItem/ed3Product.test.tsx`.

## 13. After SM5: several lakehouses, on a synthetic fixture (21 November 2026)

PLAN.md row 4. Everything below ran locally on `tests/fixtures/multi_lakehouse.py`: one fake workspace, `mlh_demo`,
with six lakehouses as SQLite files (`bronze_lh`, `silver_lh`, `gold_lh`, `sap_lh`, `crm_lh`, `sales_product_lh`),
synthetic rows only (the default SAP demo tables and the Salesforce demo, plus two CRM columns made up for the
fixture). Nothing reached Fabric; any POST, PATCH, PUT or DELETE fails the test. Tests:
`tests/test_sm5_multi_lakehouse.py`.

| Measure | Before (main, 21 Nov) | After SM5 |
|---|---|---|
| (a) Start on a workspace with `bronze_lh`, `silver_lh`, `gold_lh` | step 1 waits: "Choose a source first." | first card "mlh_demo › bronze_lh › sap ✓", **0 extra taps** |
| (a) taps to the first card, compared with the one-lakehouse demo | | the same card, 0 taps both |
| (b) Start on `sap_lh`, `crm_lh`, `sales_product_lh` | step 1 waits | `sales_product_lh` suggested (rule L2); its two schemas are the person's choice |
| (c) one plan over `sap` + `crm` in one lakehouse | not possible (one schema per plan) | **38 tables** keyed `schema.table`, SAP pack in `sap`, Salesforce pack in `crm`, 77 links, none guessed across |
| (c) a confirmed link `crm.Account.SAP_Customer_No__c` → `sap.KNA1.KUNNR` | a foreign key into another schema was dropped | counted in **one query on one connection**: 4 rows with a value, 3 found |
| One-lakehouse demo, lazy path, Start → all three dry runs | 4 taps, 2.8 s (SM2) | **4 taps, 2.8 s** at 390 px (`measure-sm5-2026-11-21.json`), every step ≤ 25 words, none scrolls |

What changed:
- **Name rules for the source (G1).** `start_flow.suggest_source`: L1, exactly one source named as the raw layer
  (`bronze`, `raw`, `landing`, `staging` as a word of its name) is the source, and the ones named silver or gold are
  said to stay untouched; L2, otherwise exactly one source named `product` holds the sources as schemas. Otherwise
  nothing is suggested and Next waits, as before. A suggestion is taken like a single option, so the first card can
  skip step 1, and Change shows it ticked with the reason under its name.
- **A plan over several schemas of one item (G4, plan and check).** `fabric_backend/multi_schema.py`:
  `schema="sap+crm"` (or `"sap,crm"`) reads each schema and keys every table `schema.table`; each schema gets its own
  knowledge pack; `Dialect.table` quotes `sap.KNA1` of a combined plan as `[sap].[KNA1]`, so every counting query runs
  on the one connection. Start's schema step offers the schemas together ("38 tables, one plan"), never chosen for you.
- Not done here: silver, gold, the model, ontology and agent over a combined plan, and writing to `silver_lh` and
  `gold_lh` (SM6); matching across sources and conformed gold (SM7). The fixture's `EXPECTED` already lists what they
  must say.

## 14. After SM6: write to the right lakehouse (21 November 2026)

PLAN.md row 5, gaps G2 and G3 of MULTI-LAKEHOUSE.md. Everything below ran locally on SM5's fixture
`tests/fixtures/multi_lakehouse.py`, layout (a): `bronze_lh` (the SAP demo's 17 tables in `sap`), `silver_lh` and
`gold_lh` (empty). Synthetic rows only. Nothing reached Fabric; any POST, PATCH, PUT or DELETE fails the test. Tests:
`tests/test_sm6_write_targets.py`.

| Measure | Before (main, 21 Nov) | After SM6 |
|---|---|---|
| (a) where the pipeline writes | silver and gold in `bronze_lh`, under new schemas | **silver → `silver_lh`, gold → `gold_lh`**, said in one line on the first card and the dry run |
| (a) how the silver notebook reads the source | | `bronze_lh` through its OneLake path (`abfss://…/<bronze_lh id>/Tables`), never changed; the notebook is attached to `silver_lh` |
| (a) how gold and the check read silver | | `silver_lh`.`silver`.`<table>`, the three-part Spark name; both notebooks attached to `gold_lh` |
| (a) the model, the ontology, the agent | the source (`bronze_lh`) | model and ontology: the silver tables in `silver_lh`; agent: `gold_lh` (layer gold) or `silver_lh` (layer silver) |
| (a) Start → all three dry runs, the suggestion taken | (step 1 waited before SM5) | **4 taps, 0.6 s** locally, server side, no browser (3 runs: 0.63, 0.61, 0.55 s), 0 writes |
| One-lakehouse demo, lazy path, Start → all three dry runs (tools/smooth_measure.py, 390 px, the same machine) | main: 4 taps, 2.92 s | **4 taps, 3.00 s** (`measure-sm6-2026-11-21.json`); no step scrolls. SM5 measured 2.8 s on another machine; the one-lakehouse path does not reach SM6's code (its source is not named as the raw layer) |

What changed:
- **Two parameters (G2).** `target_lakehouse` (the silver tables) and `gold_lakehouse` (the gold views and the
  pipeline's check; empty: beside silver) on `create_pipeline`, `create_silver_notebook` and `create_gold_views` (not on
  the read-only drafts, so the read-only listing stays under its cap). A lakehouse of the source's workspace, chosen by name; one that is not
  there is refused with what to do, and nothing is written. Empty, or the source itself, changes nothing.
- **What reads it (G3).** `target_lakehouse` on `create_semantic_model` and `create_ontology`: they read the silver
  tables where the build wrote them, and the model's dry run says first when they are not there yet ("Run the
  pipeline once first"). `create_data_agent` reads `gold_lakehouse` for layer gold and `target_lakehouse` for silver.
- **Start (name rule L1).** When the source is named as the raw layer and exactly one other lakehouse is named silver,
  the dry run and Create pass the targets; gold goes to the one named gold, else beside silver. The first card and the
  dry run say "silver → silver_lh, gold → gold_lh". Start's default data agent still reads the source tables.

Decision for Gustav: PLAN.md said the model's expression points at `gold_lh`. It points at `silver_lh`, because gold is
one wide view per fact table and the model's star (dimensions, facts and their relationships) is the silver tables. A
model over `gold_lh` needs the star in gold first (for example one materialized lake view per silver table, or a schema
shortcut), which is a new gold shape.

Not verified: none of this has run in Fabric. Spark SQL reads `lakehouse.schema.table` across schema-enabled
lakehouses of one workspace (*Lakehouse schemas*, Microsoft Learn); a materialized lake view over another lakehouse's
tables has not been created in a Fabric workspace by Krusgraph. SM8's demo workspace is where that is checked.

## 15. After SM7: combine SAP + CRM in one data product (21 November 2026)

PLAN.md row 6, COMBINE-SOURCES.md. Everything below ran locally on the synthetic fixture
`tests/fixtures/multi_lakehouse.py`, layout (b): `sap_lh`, `crm_lh` and `sales_product_lh`, whose `sap` and `crm` schemas
are the sources (simulated schema shortcuts). Synthetic rows only. Nothing reached Fabric; any POST, PATCH, PUT or DELETE
fails the test. Tests: `tests/test_sm7_combine.py`.

| Measure | Before (main, 21 Nov) | After SM7 |
|---|---|---|
| (b) customers matched across SAP and CRM | none: a link across schemas only when typed in `confirmed` | **M0 `crm.Account.SAP_Customer_No__c` → `sap.KNA1.KUNNR`**, counted: 4 of 5 accounts hold a value, 3 match as written, 4 after normalising; 3 of 4 SAP customers found (1 is in another client), 1 SAP customer matched by 2 accounts |
| (b) what the Check card says | "38 tables, 77 links, nothing needs you." | "38 tables, 77 links, 1 needs you." and, in 24 words, "SAP has 4 customers, the CRM 5 accounts. 4 accounts match on SAP_Customer_No__c after normalising. 1 only in SAP, 1 only in the CRM." |
| (b) the decision | | Decide: Accept the match / Keep them apart, with the counted evidence; kept in the flow state (the latest tap wins); nothing combined before Accept |
| (b) the model dry run | each source's tables, apart | **one `dim_customer` (5 customers), 3 SAP facts + 7 CRM facts re-keyed to `customer_key`, 10 relationships fact → dim_customer, 0 fact → fact**, Direct Lake on `sales_product_lh` (`gold`), with the gold SQL |
| (b) Start → combined dry run (`tools/smooth_measure.py --combine`, server side, no browser) | not possible | **5 taps, 1.81 / 1.68 / 1.86 s** (3 runs, `measure-sm7-2026-11-21.json`), 0 errors, 0 writes |
| One-lakehouse demo (browser, `tools/smooth_measure.py`) | 4 taps | unchanged: the combine step runs only on a plan over several schemas |

What changed:
- **`fabric_backend/combine.py`.** The party tables come from DP1's catalog (`customer`, `crm_account`, role master,
  with their business keys). Rules M0 (a column that names the other source and an identifier), M1 (the same official
  identifier: VAT id, organisation number, DUNS, GLN, by fixed normalising steps) and M2 (a key-shaped column, counted;
  0.9 only with ≥ 95 % found and ≥ 50 distinct values). M4 (names) is never used. Two counting statements per
  candidate, at most 4 candidates, on the one connection; counts only.
- **Start.** Check shows the match line and counts the open decision; Decide asks for it first; the dry run says what it
  combines ("SAP + CRM → 1 dim_customer (5 customers); 3 SAP facts and 7 CRM facts share it, no link between facts.").
- **`create_semantic_model`** over a plan of several schemas with an accepted match drafts the conformed model and
  returns the gold SQL (`xref_customer`, `dim_customer`, one view per fact). Its Create answers `not_yet` until the
  pipeline builds that gold (issue #152).
- **DP2's coverage on a plan over several schemas** now reads each schema's own pack (`data_product_match._pack_entries`):
  before, the SAP tables of `crm+sap` were looked up in the Salesforce mapping, and Check said "customer missing".

Decisions for Gustav: the master is the side the match points at (not "the most keys"), so no source row ever gets two
customer keys; the SAP side is matched within its client with the most rows when the CRM field holds no client. Both
are said on the card's evidence and in COMBINE-SOURCES.md.

Not verified: none of this has run in Fabric. The gold SQL was run on SQLite in a test after fixed translations
(`test_the_gold_sql_runs_and_conforms_the_fixture`), not on Spark. SM8's demo workspace is where that is checked.

