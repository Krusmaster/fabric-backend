# The Model workload, tested on 17 November 2026 (round W13)

Gustav, 16 November 2026: *"vi behöver testa workloaden och bygga vidare på den. Vi behöver göra den bättre, testa och
utveckla den. Kanske även UI:t."* This page covers what was run, what failed, what was fixed and what changed in the
UI. It also has the next steps with other Fabric workloads, the Workload Hub page, and the ten minutes that only Gustav
can click through in the Fabric portal.

**Where this ran.** In a cloud session with no Fabric credentials, so **nothing ran against the demo Fabric
workspace**. The writes Gustav allowed there were not used. Everything below ran locally:

- the real editor (`ModelItemEditor`), bundled from this branch and opened in Chromium;
- a stand-in for the Fabric host (`workload/scripts/e2e/harness.tsx`);
- the real engine routes (`/workload/v1/*`, `fabric_backend/workload_api.py`);
- Fabric's REST API and the SQL analytics endpoint as doubles (`tests/golden_support.py`: the golden workspace,
  lakehouse `demo_lh`, and `seed.py`'s synthetic shop rows).

`workload/scripts/e2e/run.js` repeats the whole walk. It writes the screenshots in `docs/workload-test-2026-11-17/` and
`results-before.json` / `results-after.json` there. The before run is the same walk on `main` at 616a22b.

Suites on this branch: vitest 318 passed (35 files), `tsc --noEmit` clean, and `pytest -n 4` 4364 passed, 9 skipped
(without PySpark, as CI runs it). The generated Data Science notebook also ran on a local Spark 3.5 (below).

## 1. Each flow, pass or fail, with evidence

| # | Flow | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Create item → empty state | pass | `after-01-empty.png`. The item is created only by Fabric's own dialog (`createItemDialogConfig`); that dialog is Fabric's and is not run here |
| 2 | Pick a lakehouse (Fabric's picker, stand-in) and its schema | pass | The schemas listed are `dbo (no tables)`, disabled, and `shop (7 tables)`, preselected |
| 3 | Find keys and relationships | pass | 7 tables, 6 keys, 7 links in 870 ms (`after-03-review.png`) |
| 4 | Check against the rows (prove keys and links) | pass | 13 passed, 0 failed. The tiles show 232 rows counted, 6 of 6 keys unique, 7 of 7 links holding, 0 orphans and 0 duplicate keys. Onto: 134 order_items rows over 60 orders rows, 2.2× (`after-04-check.png`) |
| 5 | Accept what passed → Choose what to build | pass | `after-05-outputs.png`. A screen reader now reads "Semantic model" once (it read "Semantic model Semantic model") |
| 6 | Dry run: semantic model, API for GraphQL, data agent | pass | "Nothing was created or changed in Fabric" |
| 7 | Create | pass | The doubles received `semanticModels` and `graphQLApis`. The data agent's card shows Try again because the double has no data-agent route. Its refresh shows the 404 of the double (`after-07-result.png`) |
| 8 | Next steps with other Fabric workloads | pass | 7 cards. The Data Science starter is `orders_features.ipynb` (`after-08-next-steps.png`) |
| 9 | A next step's Dry run | pass | Only its outputs are ticked (Fabric IQ → Ontology) on Choose what to build |
| 10 | Reopen the item | pass | It reopens on the Data product page from the saved definition |
| 11 | Data product page: health and drift | pass, with notes | Check against the rows again: "0 up to date, 0 out of date, 3 not in the workspace". The double lists a fixed set of items, so the new items are not there. Look for leftovers: the engine refuses the double's ids, which are not GUIDs, and its sentence names `outputs.created` (finding F5) |
| 12 | No permission (Fabric answers 403) | **fail before, pass after** | Before: "The schemas could not be listed: The signed-in account has no access to schemas: workspace '1111…', source 'demo_lh' (HTTP 403 …). Type the schema …", then a text field and an enabled Find keys. After: one sentence and no dead end (`before-/after-12-no-access.png`) |
| 13 | Network failure (the review request aborted) | pass | "The connection to the Krusgraph engine closed after 0 s without an answer … Check the connection and try again …" (`after-13-network.png`) |
| 14 | Big schema (247 tables, 493 suggestions) | pass | Review 1.7 s, check 1.9 s. The check counts 60 and leaves 433 "not checked" (the engine's cap per check, shown as such) (`after-14-big.png`) |
| 15 | No tables (schema `dbo`) | pass | Picker: the schema is disabled with "(no tables)". The engine answers a typed `dbo` with 404 `schema_not_found` (`tests/test_w13_workload_e2e.py`) |
| 16 | Phone width (390 px) | pass | No horizontal overflow before or after. W13's labelled ribbon first wrapped and cut off Next and Back at 390 px; the labels now give way to icons under 640 px (`after-15-phone-review.png`) |
| 17 | Keyboard only | pass | Tab, then Enter on Choose a source, then Tab and Enter on Find keys and relationships, reaches the review |
| 18 | Uncaught errors in the page | pass | none |

**The Data Science starter on a local Spark** (PySpark 3.5.3, seed.py's `orders` and `order_items`):

- cells 1–3 ran;
- 60 feature rows for 60 orders;
- columns `order_items_rows` and `order_items_quantity_sum`;
- cell 4 (MLflow) compiles.

The first version also summed `product_id`, a link column. The starter now leaves every key and link column out, and a
test keeps it so. Delta and Fabric's MLflow tracking were not run here.

## 2. What was found and fixed (smallest first, each with a test)

| # | Finding | Fix | Test |
| --- | --- | --- | --- |
| F1 | Output checkboxes and cards read their type twice to a screen reader ("Semantic model Semantic model", "API for GraphQL API for GraphQL") | The icon's alt is empty when the label already names the type (`fabricIcons.altBeside`). "Notebook" beside "Gold views" is kept | `fabricIcons.test.ts` |
| F2 | The name field read "Name of the api for graphql" | `nameLabel`: "Name of the API for GraphQL" | `buildWords.test.ts` |
| F3 | No access to the source showed the engine's route name and the workspace id, then a schema field and Find keys that could only fail the same way | `schemaProblem`: "Your sign-in cannot open demo_lh. Ask the workspace's admin for access (Viewer is enough to find keys and links, Contributor to create), or choose another source." No field, and Find keys is disabled | `noAccess.test.tsx` |
| F4 | After the review, the next step was only an unlabelled arrow in the ribbon. The Builder said "choose Next" and nothing on the page was called Next | A primary **Next: choose what to build** on the page, and labels in the ribbon | `nextSteps.test.tsx`, run.js step 5 |
| F5 | Not fixed (engine, CSN2 holds `workload_api.py`): Look for leftovers, given ids that are not GUIDs, says "each of outputs.created has the Fabric id and workspace (GUIDs) Create recorded" | Word it for a person when CSN2 releases the file. Real Fabric ids are GUIDs, so a person should not normally see it | — |
| F6 | Not fixed (a decision): review decisions are saved only by Save or by Create. An item closed after Accept all and before Save comes back without them | Recommend saving after each decision with the existing throttled `persist` (n197). It is a behaviour change, so it is left for Gustav | — |
| F8 | Not fixed (engine, found on the way; **the same on `main`**): `tests/test_spark_notebooks.py::test_pipeline_check_notebook_runs_after_silver_and_gold_in_pyspark` passes on PySpark 4.0.1, which CI's notebooks job uses (all 9 Spark tests pass). It fails on PySpark 3.5.3, the Spark line of Fabric Runtime 1.3, which the notebooks name: "gold.order_items: 135 rows after the join, 134 in silver.order_items; SUM(quantity) is 327.0 after the join, 324.0 in silver". A gold join that repeats a line on Spark 3.5 would be a doubled total in Fabric. Not verified in Fabric | An Engine round: run the test on PySpark 3.5 and find which join of `gold.order_items` repeats a row; consider a second CI notebooks job on 3.5 | the failing test on 3.5 |
| F7 | Not fixed (Microsoft's kit): the empty state's picture is the kit's check mark (`EditorEmpty.svg`), which reads as "done" on a page where nothing is done yet | Replace it with Onto (`static/mascots/`) when the mascot art is final | — |

## 3. UI against Microsoft's guidelines, and what changed

**Read on 17 November 2026:**

- *Fabric Extensibility toolkit validation guidelines and requirements for items*, Microsoft Learn,
  `learn.microsoft.com/en-us/fabric/extensibility-toolkit/publishing-requirements-item` (ms.date 24 February 2026):
  - 3.1: one sticky ribbon; its tabs never switch the view.
  - 3.2: ribbon actions use the Fabric button "in subtle state".
  - 3.3: Home first.
  - 3.4: Save or AutoSave, the "button is icon only".
  - 4.3: empty states give "helpful messaging and clear actions".
- *… requirements for workloads*, same site, `…/publishing-requirements-workload` (ms.date 24 February 2026):
  - 2.9 Accessibility: comply with the Fabric UX guidelines.
  - 1.4.2: Getting started material exists.
  - 1.4.3: At a glance has an image or video.
  - 3.1.3 and 3.1.4: subtitle and description.
  - 3.1.5: a banner of 1920×240.
  - 5.2.1 and 5.2.2: help link and support contact.
- *Machine learning experiment*, Microsoft Learn, `learn.microsoft.com/en-us/fabric/data-science/machine-learning-experiment`
  (ms.date 15 May 2026): "If an experiment with this name does not exist, a new experiment with this name is created"
  (`mlflow.set_experiment`).
- **Fluent 2** (`fluent2.microsoft.design`) could not be opened from this session; the host is outside its network
  allowance. Nothing here cites it. The changes use Fluent v9 components and tokens already in the editor, and follow
  `docs/WORKLOAD-UX-DESIGN.md` (D1) section 9.

| Area | Before | After |
| --- | --- | --- |
| Layout and where you are | No indication of the step | A step indicator at the top of the canvas: Source, Keys and links, Choose, Dry run, Built, Data product. It is a `nav` named "Where you are" with `aria-current="step"`; done steps are buttons back. On a canvas under 640 px it becomes one line ("Step 2 of 6 · Keys and links · Next: Choose"). It sits in the canvas because ribbon tabs must not switch views (3.1) |
| Ribbon | Icon-only buttons with tooltips | Subtle buttons with labels (3.2); Save stays icon only (3.4). The labels hide under 640 px |
| Empty state | A 50-word paragraph, and two primary-styled buttons | One sentence in the mascots' voice: "Pick a lakehouse: I find its keys and links, prove them on the rows, and build only what you choose." The paragraph is behind "What Krusgraph reads, and what it changes". One primary at a time: Choose a source, then Find keys and relationships |
| Evidence | "6 of 6 keys are unique … 7 of 7 links hold" in a sentence | Tiles: rows counted, keys unique, links holding, orphans, duplicate keys. Onto names the doubled total the proven grain prevents |
| Primary action on the review | Only the ribbon's arrow | **Next: choose what to build**, primary once checked, with one line on what happens |
| Loading | Onto's wait (n223) | unchanged; it was already a step, then a slow line, then Cancel |
| Errors | The engine's sentence | unchanged except no access (F3) |
| Accessibility | Duplicate names (F1) | Fixed. The keyboard path was checked. States carry a word and a mark, never colour alone (✓ on done steps, status words on the cards). Colours are Fluent tokens only |
| Dark mode | The editor wraps itself in Fabric's light theme (`index.ui.tsx`, `fabricLightTheme`); a dark browser shows the same light editor (`17-dark.png`) | unchanged. Whether Fabric's frame offers a dark theme to workloads (`workloadClient.theme`) is item 9 of Gustav's checklist. The new styles use tokens only, so a dark theme would carry through |

**Before and after** (`docs/workload-test-2026-11-17/`):

| Screen | Before | After |
| --- | --- | --- |
| Empty state | `before-01-empty.png` | `after-01-empty.png` |
| Review | `before-03-review.png` | `after-03-review.png` |
| Checked | `before-04-check.png` | `after-04-check.png` |
| Choose | `before-05-outputs.png` | `after-05-outputs.png` |
| No access | `before-12-no-access.png` | `after-12-no-access.png` |
| Next steps | (none) | `after-08-next-steps.png` |
| Phone | (none) | `after-15-phone-review.png` |

## 4. Next, with other Fabric workloads

After a Create, and on the Data product page, the item shows **Next, with other Fabric workloads**
(`nextSteps.ts`, `NextStepsView.tsx`).

The suggestions are **rules over what the check counted**: `review.json`'s rows, distinct values and orphans per key and
link, and `outputs.json`'s built items. No AI. Before a key has passed the check, the panel only says to check against
the rows first. Each card names the workload, one line of why, a status word (never colour alone) and one button. A
phone shows one column.

The proven grain drives the starter and the why-lines: a passed link whose source has more rows than its target, header
and lines first (`order_items → orders`, 134 over 60, 2.2×).

| Workload | Suggestion (shop example) | What Krusgraph does |
| --- | --- | --- |
| Data Science | Feature table at the grain of orders, with an Experiment: "Your order_items → orders link is proven (134 rows, 0 orphans), so this notebook sums order_items per orders row first: one row per orders row, no total counted 2.2×." | **Starter to download**: `orders_features.ipynb`, plus Copy the code. The cells sum the lines per order (ids left out), join once on the proven key, assert one row per order before writing `orders_features`, then `mlflow.set_experiment("orders_experiment")` and one run. Krusgraph creates no item and trains no model |
| Power BI | Semantic model and report, or the report alone once the model exists | **Builds it**: Dry run ticks those outputs |
| Data agent | A data agent written from the proven keys and links | **Builds it** (left unpublished unless Publish is ticked) |
| Data Factory | Silver notebook, gold views and a pipeline (lakehouse sources only) | **Builds it** (not run or scheduled unless ticked) |
| Data Engineering | API for GraphQL | **Builds it** |
| Fabric IQ | Ontology (preview), from 2 or more proven keys and 1 or more proven links | **Builds it** |
| Real-Time Intelligence | A drift monitor, then an alert | **Krusgraph in Claude**: the monitor is `create_drift_monitor` in the hosted tools, not in the item. The card copies the request. An Activator alert on it is **guide only** |
| Apps | Rayfin App (preview) | **Builds it** (an empty App item and one package command, as the card says) |

What this item built is not suggested again: a phase 1 API without a recorded output counts by its Fabric type.

## 5. The Workload Hub page

**What the manifest shows today** (`workload/Workload/Manifest/Product.json` and `assets/locales/en-US/translations.json`):

- **Name and card:** "Krusgraph". The card description is "Finds the keys and relationships …".
- **Slogan:** "Keys and relationships for your Fabric tables, mirrored ones included, with the rule behind each one."
- **Description:** what Krusgraph reads; mirrored sources; a list of eight outputs; dry run first; the network hosts.
- **Media:** a banner (`Workload_Hub_Banner.png`), one YouTube video and one image.
- **Get started:** one learning card, "Get started / From a lakehouse or a mirrored database to Fabric items in three
  steps", linking to `krusgraph.com/docs`.
- **Item types:** one, Krusgraph Model, in home, create hub, + New and Teams.
- **Support links:** documentation, attestation (`{{ATTESTATION_URL}}`, filled at build), help, privacy, terms and
  licence.
- **Publisher:** Kruse Consulting AB.
- **`compatibleItemTypes`:** Lakehouse and Warehouse.

**What Microsoft's own workload pages carry and ours could add.** These are proposals; nothing here changes the name,
the identity, the publisher, pricing or licence links.

1. **Get started cards, three instead of one**, each to a static page (1.4.4):
   - "Find and prove keys and links" (the review and the check);
   - "Build Fabric items from the review" (dry run and Create);
   - "Next steps with other workloads" (section 4).
   Each needs an image; the current single card has one.
2. **The description:** one line on what comes after the build: *"After the check, the item suggests what to do next
   with other Fabric workloads, built on the proven keys and links: a Data Science notebook starter at the right grain,
   Power BI, a data agent, a pipeline, an ontology."* Prepared in the companion PR labelled needs-gustav.
3. **The Get started description:** a fourth step, "4. Use the next steps: each says why it fits what was proven." Also
   in that PR.
4. **`compatibleItemTypes`:** the description names SQL databases and mirrored databases; the list has only Lakehouse
   and Warehouse. Whether adding `SQLDatabase` and `MirroredDatabase` is valid there is for Gustav to check against
   the manifest schema (`WorkloadDefinition.xsd` does not constrain the values). It is not changed.
5. **At a glance:** a second image showing the proof tiles and the next-steps cards (`after-04-check.png`,
   `after-08-next-steps.png` as a start, on synthetic data).

## 6. Gustav's ten minutes in the Fabric portal

These are what the doubles cannot show. Use the demo workspace, synthetic shop data, and the dev workload
(`docs/WORKLOAD-DEV.md`):

1. **+ New item → Krusgraph Model** (1 min). The create dialog names the item. The editor opens on the empty state
   with the step row and the one sentence. Is the iframe wide enough for the step row? Note the width.
2. **Choose a source → `shop_lh`, schema `shop` → Find keys and relationships** (1 min). Is the ribbon readable with
   labels in the real frame?
3. **Check against the rows** (1 min). The tiles show real counts. Is the 2.2× line right for `order_items` over
   `orders`?
4. **Next: choose what to build** → tick **Semantic model** and **Data agent** → **Preview → Create** (2 min). Does the
   data agent get created? The double could not show it.
5. **Next steps panel** (2 min):
   - **Download notebook (.ipynb)**: does the download work inside Fabric's frame (a `data:` link, as draw.io's)?
   - Import it (Workspace → Import → Notebook), attach it to `shop_lh`, Run all. Expect `orders_features`, 60 rows,
     and the Experiment `orders_experiment`.
6. **Copy the request for Claude** on the drift card (½ min). Does the clipboard work in the frame? If not, the text
   shows under the button.
7. **A next step's Dry run** (½ min), e.g. Ontology. Only it is ticked.
8. **Close the item without Save after an Accept**, reopen (1 min). Are the decisions gone (F6)? Decide whether to
   autosave.
9. **Theme** (½ min). If Fabric offers a dark theme, switch it: does the editor stay light?
10. **Phone** (½ min). Open the item on the phone. The ribbon shows icons only under 640 px; the step row is one line.

## 7. Not done, and why

- **Not run against the demo Fabric workspace:** no credentials in this session. Section 6 covers it.
- **Workload package:** not uploaded; that is manual.
- **Manifest:** no change to the name, identity, publisher, pricing or licence links.
- **Fluent 2 site:** not reachable from this session.
- **F5 and F6:** left as findings. F5 is in a file CSN2 holds; F6 is a behaviour decision.

## 8. Gustav's live test, 18 Nov

Gustav used the Model item in the real Fabric portal on 18 November 2026 (workspace *Test*, lakehouse `shop_lh`, schema
`shop`; a silver notebook `shop_lh_silver` and an API for GraphQL `shop_lh_api` built). Round WB10 opened one issue per
finding and fixed them with tests. No Fabric credentials were used: what was verified ran in unit tests (pytest, vitest)
and in the end-to-end harness on the doubles, not in Fabric.

| # | Finding | Issue | Fix | Test |
| --- | --- | --- | --- | --- |
| 2 | *Owner of the data products* showed `demo_lh_api9`, an API for GraphQL item, and the cards said *Owner: demo_lh_api9* | #58 | The field had no `autocomplete` and Fluent's generated id, so the browser could fill it with a value typed in another field (most likely the output name field); nothing in the code prefilled it from an output. It now has `autocomplete="off"`, the name `kg-catalog-owner`, the Data product page's people list and a **Me** button. An item's name is refused in the editor and by the engine (`catalog_publish/owner.py`); where the workspace's role assignments are readable, so is anyone who is not a person or group in them. A saved owner that is an item's name is not prefilled | `wb10Catalog.test.tsx`, `tests/test_wb10_catalog.py` |
| 3 | Counts disagreed: cards 6 keys and 5 links, the lakehouse's description 6 links, the silver notebook, next steps and Thinker 7 links | #59 | One source: the check recorded in the item's `review.json`, the set the Thinker line counts. Every link is counted once, as inside one data product, between two (stated separately: *1 link between customers and products*) or to a table in no data product; the totals equal the Thinker's. The cards and the written descriptions use the same counts (`catalog_publish/cards.py`, `link_split`, `page_evidence`) | `tests/test_wb10_catalog.py` (the route's totals against the review's) |
| 4 | Two dates: Thinker *checked 2026-11-14 14:54 UTC*, cards *checked 18 Nov 2026* | #60 | The catalog no longer dates its own count "today": it states the latest check recorded in this item, with the time, written as the Thinker writes it (`2026-11-14 14:54 UTC`). Only when the item holds no check does it count and state that time | `tests/test_wb10_catalog.py`, `wb10Catalog.test.tsx` |
| 5 | The catalog write replaced `shop_lh_silver`'s own description, and wrote to the lakehouse | #61 | Each item keeps its own first sentence; the data-product sentence is appended (the plan marker stays last), and a second run does not repeat it. Items Krusgraph did not build are not written to by default: they are offered as an unticked option with one line why, and ticking prepares the dry run again with them, so the confirm covers what is shown | `tests/test_wb10_catalog.py`, `tests/test_ca1_*.py`, `wb10Catalog.test.tsx` |
