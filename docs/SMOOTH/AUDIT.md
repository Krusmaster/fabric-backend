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
