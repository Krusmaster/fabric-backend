# Changelog

Dates are the commit dates on `main`. Versions are the `version` in `pyproject.toml`, mirrored in
`fabric_backend/__init__.py` and `server.json` (a test keeps them equal).

## Not yet deployed — after build `src-8d6c473bf26f45f9` (6 November 2026, main up to n111)

Rounds n114, n115, n116 and n120 are listed under 0.8.0 below and are not deployed either. Round n126 was added to
the list after it was written (round n127). `docs/DEPLOY-NEXT.md` is the checklist for the
next deploy.

- Round BL44: **the guided path's state survives a second replica** (23 November 2026, issue #104, first part). With `KRUSGRAPH_REGISTRATION_STORE` set (the hosted service) `flow_state` keeps each flow as one record of kind `flow` in the registration store (Azure Table Storage), under a hashed key, written back with `If-Match` and retried when the other replica wrote in between; sequence numbers are per flow. Without it, memory as before. `docs/FLOW-STATE-REPLICAS.md` (the choice: a shared store, not state in the card's arguments, which WB15 had to leave). `tests/test_bl44_flow_state_store.py`: two module copies sharing only a store replay the taps to the same state as one. The card-fold part of #104 is still open.
- Round WB8: **a correlation id per workload request, and an accessibility check over every step** (23 November 2026). (1) Requirement 2.4: the editor sends a fresh `x-krusgraph-correlation-id` with every engine call; the engine keeps it (or a new UUID when missing or malformed) for the whole request, writes it as `cid` on every log line, returns it in the answer's header and as `correlation_id` in every error, and logs Fabric's `ActivityId`/`RequestId` beside it when Fabric sends them (Microsoft Learn, WDK and Extensibility Toolkit supportability pages; the toolkit's frontend-to-backend calls carry no Fabric id). The editor's error bar shows it as *Reference for support*. `docs/OPERATIONS.md`: confirming the 30-day retention live and finding one request by its reference. (2) Requirement 2.9: axe-core (WCAG 2.1 A and AA) runs after every step of the e2e harness on every page a flow opens, light and dark, desktop and 390 px; serious or critical findings fail the run. It finds none; Fluent UI's Tabster focus guards (`data-tabster-dummy`) are counted apart. Flow 21's check follows ED3's sentence. `tests/test_wb8_correlation.py`, `correlation.test.tsx`.
- Round WB6 (part B, F7 in `docs/WORKLOAD-TEST-2026-11-17.md`): **Onto on the item's first screen** (23 November 2026). The kit's check-mark picture (`EditorEmpty.svg`) is replaced by Onto, the 3D figure the editor's other screens use, with one plain sentence (`stepWords.ONTO_EMPTY`); the figure is decorative (`alt=""`), the sentence is text, and with the mascots off neither shows (the title and first line say the same). The n225 phone fixtures are refreshed for the two new CSS rules. `emptyOnto.test.tsx`.
- Round WB7: **the Marketplace licence check, ready to switch on and off by default** (23 November 2026). A Create (dry_run=false) on the workload's `/starter`, `/sap-demo` and `/catalog` now counts as writing, like `/build` and `/product` retire: refused with `kind: upgrade` once the trial has ended without a subscription (`billing.CREATE_ROUTES`), and under `KRUSGRAPH_ENTITLEMENTS` without the trial as well (the same licence gate as `/build`). Dry runs, reads and `/run` stay free. The editor's error bar shows a refused Create as a warning with a *Subscribe in Microsoft Marketplace* link (https only). `docs/MARKETPLACE-SETUP.md` section 5a: the settings for a test revision and the DEV offer test, step by step; production keeps `marketplace`, `entitlements` and `trial` false. `tests/test_wb7_marketplace_gate.py` (webhook lifecycle to engine on every create route, trial start and end, flags off), `upgradeLink.test.tsx`.
- Round WB9: **the pilot pack** (23 November 2026). A self-check on the item's first screen, *Is everything ready? Check this workspace* (`SelfCheck.tsx`, `POST /workload/v1/selfcheck`, `workload_api.run_selfcheck`): admin consent (the permissions on the user's token), a Fabric capacity (List Workspaces' `capacityId`), access to the workspace's items and a lakehouse, each OK or Missing in one sentence; the tenant setting for unvalidated workloads is said to be unknown, since no documented API reads it without a Fabric admin. Read only. `docs/PILOT-DAY.md`: Krusgraph's checklist for a pilot day (tenant id, Selected tenants and the ~10 minutes, the self-check, a 30-minute session on the shop sample or SAP demo data, notes kept privately). `tests/test_wb9_selfcheck.py`, `selfCheck.test.tsx`.
- Round WB5: **SAP in the Model item** (23 November 2026). (1) A CSN file chosen in the review (`csnUpload.ts`, `SapViews.tsx`): read in the browser, checked (a `definitions` object and a version marker, at most 5 MB), kept only in the item's source.json and sent with review and check as `csn_upload`; the engine checks it again, uses it like a CSN in the lakehouse's Files (`csn_onelake.from_upload`, reported as "a file uploaded in the editor") and never logs it. (2) The SAP fields in plain words under the review (`mirroring.sap_fields`): only what the SAP pack documents, a key column ("part of the key"; MANDT "SAP client: part of every key and every link") and a link column with its link's role ("links to the customer"); fields the pack says nothing about are left out. (3) Load SAP demo data, for a source without SAP tables: `POST /workload/v1/sap-demo` creates the sap_demo36 generator notebook (dry run, then Create with the confirm value), never runs it; the notebook writes nothing until DRY_RUN = False and refuses dbo, sap_silver, sap_gold. `tests/test_wb5_sap_item.py`, `csnUpload.test.ts`, `sapFields.test.ts`.
- Round AA1: **from the feature table to a model and predictions in gold** (22 November 2026; Gustav ran the Data Science starter in Fabric on 21 November). ED3's Advanced analytics section on the Data product step shows each analysis the rules recommend on the Data Science card's grain (weekly orders forecast, customer segments, top 10 drivers) in three stages, Feature table -> Model -> Predictions in gold, each with Dry run, Create (as a notebook in the workspace, recorded as `ds_model` / `ds_predictions`) and Download, and once created ED3's Open in Fabric and Run now. The notebooks come from `fabric_backend/advanced_stages.py`'s templates (the editor fills the same ones): a seasonal naive baseline and a scikit-learn regression backtested on 8 weeks, k-means on RFM with k by a stated silhouette rule, a descriptive top 10; MLflow autologging, the model registered, scoring through Fabric's PREDICT into gold with model version and run id on every row. Below 200 orders the editor and the notebook say once that there are too few rows for a model and the feature table is still useful (the shop sample). The semantic model on gold adds a prediction table only when it exists in gold, related on the proven customer key (SAP: the combined key column) or the calendar, with one measure in the display folder `Advanced analytics`, and the report one visual for each. Metrics stay in the experiment ("Open the experiment"): Fabric's REST API has no runs or metrics. `docs/ADVANCED-ANALYTICS.md`, `tests/test_aa1_advanced_stages.py`, `advancedStages.test.tsx`.
- Round DPM1: **the semantic model is built on gold, grouped by data product** (22 November 2026; Gustav on the shop sample's data flow: "ska vi inte använda dataprodukterna för den semantiska modellen?"). When a build has gold views and a semantic model, the gold notebook adds one dimension view per dimension table (`gold.spec(dimensions=True)`; a composite key through silver's combined key column) and the model reads the gold views as a star schema (`semantic_model.draft_on_gold`): each data product of `domains.data_products` is a perspective, its tables carry `Krusgraph_DataProduct` and its measures a display folder of its name, the interface between two data products is a relationship marked `Krusgraph_Interface`, a table in no data product (the shop's audit_log) stays out with one line why, no relationship between two facts, and only onto keys the row check counted unique when it ran. The model annotation names the reserved display folder `Advanced analytics` (round AA1). The data flow card's last column is "Built on gold" with a line from each gold view the model reads; the dry run and the card say what the model reads in one line; a model without gold says "bronze ... no gold views in this build". The silver boxes say "key checked: N of N unique" when the row check ran (the demo and the editor's Check against the rows), "not checked" only when it did not. `docs/MODEL-ON-GOLD.md`, `tests/test_dpm1_model_on_gold.py`.
- Round SM7: **combine SAP + CRM in one data product** (21 November 2026, docs/SMOOTH/PLAN.md row 6). New `fabric_backend/combine.py`: match rules M0-M2 between the sources' customer tables (DP1's catalog), counted on the rows; on a plan over several schemas Check says the counts in one line, Decide asks Accept the match / Keep them apart (kept in the flow state), and with an accepted match the semantic model dry run has facts from both sources sharing one `dim_customer`, no link between facts, with the gold SQL. Create of the combined model, schema shortcuts, M3 and the gold in the pipeline are issue #152. DP2's coverage reads each schema's own pack.
- Round BL33: **one count everywhere: the receipt, the counts, the daily rules and the receipt notebook agree** (21 November 2026, backlog C-31). `tests/test_bl33_one_count.py` runs the plan and validate_plan once on the synthetic `shop`, `shop_faults` and `sap_demo` samples and feeds the same answer to `counts.summary`, `receipt.build`, `health.daily_rules` and `receipt_notebook.cells`: the same keys and links by the same ids, each number equal everywhere, every receipt statement and notebook cell giving its stated count back, every daily rule passing on the rows it was made from. One mismatch found and fixed: when validate_plan stopped at `max_items` (or scope or time), `counts.summary` said the items it did not reach were not counted, while the receipt (and so the notebook) and the daily rules left them out without a word. `receipt.build` now lists them as not counted, with no number and no statement, and `health.daily_rules` lists them under `not_rules`; both take the list from `counts.summary` (`receipt.not_reached`).
- Round BL30: **`/scores`, the regression corpus's numbers on the site as they are** (21 November 2026, backlog C-09). The page reads `docs/scores.json` when it is opened (never rewrites it) and shows per corpus the keys right, wrong, missed and extra and the links found, missed and wrong, the misses next to the hits; it says the corpora are synthetic rows or public schemas and links `docs/SCORES.md` for how to run them again, and gives the commit and date of the numbers from git in a full clone or the file's history on GitHub otherwise. In the sitemap, not yet linked from the home page or /trust. The image carries the package only, so a deployed build says it does not carry the file until `docs/scores.json` ships with it. `tests/test_bl30_scores_page.py`.
- Round BL31: **why the deploy of `48f735d` failed, and the deploy checklist brought up to date** (`docs/DEPLOY-NEXT.md`, 21 November 2026, backlog C-01, issue #135). The failure was a one-off timeout of GitHub's OIDC token service in `azure/login`, before any Azure call; every later tip of `main` deployed, and `main` up to `27ea969` is live as build `src-bc278814ec357d5d` (21:15 UTC), so this heading's "not yet deployed" no longer holds for the lines above it at that time. Docs only; the troubleshooting table and a proposed `azure/login` retry for `docs/AUTO-DEPLOY.md` wait in PR #150 (needs-gustav).
- Round SM6: **write to the right lakehouse** (21 November 2026, docs/SMOOTH/PLAN.md row 5). `target_lakehouse` and `gold_lakehouse` on `create_pipeline`, `create_silver_notebook` and `create_gold_views`: with one lakehouse per layer (`bronze_lh`, `silver_lh`, `gold_lh`) the silver notebook goes to `silver_lh` and reads the source through its OneLake path, and the gold views and the check go to `gold_lh` and read the silver tables by their three-part name. `create_semantic_model` and `create_ontology` take `target_lakehouse` and read the silver tables there; `create_data_agent` reads the layer's lakehouse. Start passes them when the names say so, and the dry run says "silver → silver_lh, gold → gold_lh". Without the new parameters nothing changes. Tested on the synthetic fixture only; not yet run in Fabric.
- Round BL29: **a dated quality line and stable tags in the catalog draft** (`docs/CATALOG-ACCELERATOR.md`, 21 November 2026, backlog P-15). Every description `fabric_backend/catalog.py` drafts for the OneLake catalog now ends with one line from `counts.summary`, kept whole when the text is shortened: "Quality checked 2026-11-21: keys 6 of 6 hold; links 7 of 7 hold." (ISO date, counts only, no row value, no column name), or "Quality: not checked yet." without a check. The tags come from a fixed, documented set (`Krusgraph`, `krusgraph-checked`, one per knowledge pack such as `krusgraph-sap`, `domain: <name>`), never with a date. The draft answer gains `quality` and `tag_set`. Nothing is sent.
- Round BL25: **keys and links from the customer's own Dataverse `$metadata`** (`docs/DYNAMICS365.md`, "Keys and links from your own `$metadata`", 21 November 2026, backlog I-43). `fabric_backend/dataverse_meta.py` reads a Dataverse Web API CSDL `$metadata` file the customer exports: entity keys (inherited through `BaseType`), lookups from `NavigationProperty` with `ReferentialConstraint` on the column Link to Fabric lands (`_customerid_value` as `customerid`), multi-table lookups as filtered links on their type column, many-to-many listed and not applied. The output has the CSN reader's candidate shape, marked "declared by Dataverse metadata, not counted", with what does not map to the lake. Reads a file only, refuses a URL; unit tests on a synthetic `$metadata` against the synthetic Dynamics 365 demo (`tests/test_bl25_dataverse_meta.py`). Not fed to the plan yet (next step, touches `infer.py`).
- Round BL27: **schedules drafted, the pipeline's daily run and the model refresh after it** (`docs/SCHEDULES.md`, 21 November 2026, backlog B-26). `fabric_backend/schedules.py`: `draft(outputs, timezone, time)` gives the Fabric Job Scheduler body for the pipeline's daily run and the semantic model refresh as the pipeline's last step after the check (or a Power BI refresh schedule when there is no pipeline), with the reason, the Learn pages and the delegated scopes per call marked against what the app has; `preview` says each in one short sentence. A dry run only: nothing is sent, and Create does not use it yet.
- Round BL23: **the pilot scan notebook, names and counts only** (`docs/PILOT-SCAN.md`, 21 November 2026, backlog S-04, I-35). `fabric_backend/pilot_scan.py` builds a plain-Python Fabric notebook (no `%pip`, no network) that reads the Spark catalog of the attached lakehouse(s): databases, tables, column names and types and one `COUNT(*)` per table, names the tables a knowledge pack knows by name, links tables by name and suggests the 20 with the most links, and writes one JSON and one markdown file to `Files/krusgraph/pilot-scan/`. No row values. Tests run the cells on a fake catalog with the synthetic SAP demo and shop. Not yet run in Fabric (a founder step).
- Round SM5: **several lakehouses in one workspace** (21 November 2026, docs/SMOOTH/PLAN.md row 4). A synthetic fixture, `tests/fixtures/multi_lakehouse.py`, holds six lakehouses (one per layer, one per source, one product lakehouse with the sources as schemas). Start suggests the source by name rules (L1: the one raw layer, such as `bronze_lh`; L2: the one product lakehouse) and takes it like a single option, so layout (a) starts on "mlh_demo › bronze_lh › sap ✓" with no extra tap. `schema="sap+crm"` plans several schemas of one lakehouse in one plan, tables keyed `schema.table`, one pack per schema, and the join check counts a link across the schemas on one connection (`fabric_backend/multi_schema.py`). Writing to other lakehouses and combining sources come in SM6 and SM7.
- Round BL21: **`krusgraph demo faults`, the planted-faults walk as one command** (`docs/demo/PLANTED-FAULTS-WALK.md`, 21 November 2026, backlog C-37, C-38). Builds the synthetic `shop_faults` sample in memory, runs the plan and `validate_plan`'s checks, and prints per planted fault what was planted, what Krusgraph said (its own answer, not expected text) and the receipt SQL that counted it; F5 (currency) prints "not found yet". JSON when piped. Read-only, offline; `tests/test_bl21_demo_faults.py`.
- Round BL19: **the receipt as a notebook the customer runs** (21 November 2026, backlog C-36 next step, P-27). `fabric_backend/receipt_notebook.py` turns a receipt into `krusgraph-receipt.ipynb` (nbformat 4): per number a markdown cell with the sentence and a code cell that runs its Spark SQL statement (`receipt.build` with the Databricks dialect) with `spark.sql` and prints "stated N, now M, same" or "changed", and a summary cell. Plain Python, no `%pip`, no import, no write, no row value; nothing is uploaded. Every cell ran against a fake `spark` over SQLite with the synthetic shop and SAP demo, and a planted extra row prints "changed" (`tests/test_bl19_receipt_notebook.py`); not run in Fabric yet. `docs/RECEIPTS.md` says how a buyer imports and runs it; the download in the card and editor is the next step.
- Round DP2: **data products suggested for any table** (`docs/DATA-PRODUCT-CATALOG.md`, 21 November 2026). `data_product_match.suggest` gives each table no pack knows a catalog data product and role by rules: names in English, German and Swedish (also inside compounds), business-key columns, header and line pairs, and the row counts validate_plan runs; each suggestion has a confidence (high only when the rows confirm it) and its evidence. A coverage answer per process says how many products are present and which questions cannot be answered ("Order to cash: 5 of 7 products present; receivables and payables and payment missing ..."). It appears as `data_products` in plan_backend and validate_plan, as one line on the start card's Check step, and in requirements_draft's RQ-X0 answers. Golden answers on the three pack demos, an invented German ERP, WideWorldImporters, a Swedish schema and random tables (`tests/test_dp2_product_match.py`).
- Round BL17: **row-level and object-level security drafted from the plan** (`docs/SECURITY-ROLES.md`, 21 November 2026, backlog B-24). `fabric_backend/security_roles.py` proposes the columns a role would filter on by name rules and the packs (SAP's BUKRS, VKORG, WERKS, MANDT; Business Central's $Company; a company, region or country column in several tables or a key), drafts a TMDL role per column with a DAX filter through a `security_user_map` table the customer fills in, reaches other tables over counted links only and lists those it does not reach, and drafts object-level security (`metadataPermission: none`) for every column privacy.py flags. The SAP demo proposes BUKRS and VKORG; the shop proposes none. Nothing is written, no row value is read; not wired into the model dry run yet (next step, after the smooth chain).
- Round BL14: **the proven rules as a daily check with history** (21 November 2026, backlog P-27). `health.daily_rules` makes a rule set from `validate_plan`'s answer: each key counted unique stays unique, each counted link's orphans stay at or below the counted number, each counted header amount stays one value per header. `monitor.daily_rules_cells` is a nightly notebook (plain Python, no `%pip`) that appends one row per rule to `krusgraph.health` (check `proven`; rule id, pass or fail, count, time, last run's count; no row value) and posts which rule broke and since when to the existing webhook. Tested on SQLite and a local Spark with a break planted between two runs (`tests/test_bl14_daily_rules.py`); not run in Fabric, and no tool creates the notebook yet (`docs/HEALTH.md` section 6).
- Round SM4: **fewer doors** (`docs/SMOOTH/AUDIT.md` section 11, 21 November 2026). The hosted server lists 16 tools by default instead of 48 (`fabric_backend/tool_listing.py`); the other 32 stay registered and answer when called by name, and `KRUSGRAPH_ADVANCED_TOOLS=1` lists all 48. A card's draft step names its creating tool's dry run; a card with no way on hands back to the Start Krusgraph card at the right step (0 dead ends, from 1). The list of hidden tools is in `docs/DIRECTORY-READINESS.md`.
- Round DBT1: **dbt tests from Krusgraph's checks** (`docs/DBT.md`, 21 November 2026). `dbt_schema(project=true)` also writes `tests/krusgraph_checks/`: a duplicate test on the source per composite key, an orphan test per relationship over several columns (counted as validate_plan counts it), and per header amount that `amount_levels` found (and the pack trap with check `amount_level`) a sum test on the header's mart or a grain test on the line's mart; each file starts with the check it comes from. T-SQL for dbt-fabric, no CTE, no dbt-utils. The rest of the project is unchanged apart from one README line. Verified in unit tests on the synthetic SAP, Salesforce and Dynamics 365 demos in SQLite (`tests/test_dbt1_singular_tests.py`); dbt was not run. `docs/DBT.md` and `docs/demo/DBT-DEMO.md` say how to run the project yourself with dbt-core-mcp, a separate open-source project Krusgraph does not depend on. A spike compares sqlglot and sqllens for mining joins from existing SQL (`docs/spikes/SQL-LINEAGE-SPIKE.md`; report only).
- Round BL10: **measures that respect currency, unit and sign** (21 November 2026, backlog C-16). The semantic model draft keeps every suggested sum within one currency or unit: a currency or unit column in the same table or the document header (WAERK, VRKME, VBRK.WAERK for VBRP, RWCUR for WSL) turns `SUM` into `IF(HASONEVALUE(<currency>), SUM(...))` unless the rows were counted with one value; a price per unit (NETPR, unit_price) is never summed; an amount whose currency is in no table of the model (EKBE.DMBTR) gets no sum; a debit/credit indicator (SHKZG) is noted in the description. `docs/CURRENCY-AND-UNITS.md`, `tests/test_bl10_currency.py`; the benchmark and Salesforce goldens change only by the dropped price sums and the currency guards.
- Round DBTV1: **the dbt flow opens larger in the demo chat** (21 November 2026). The dbt project's flow has the same "Open larger" as the data flow: the same overlay over the page (Back to the chat or Esc returns, the focus goes back to the button), the same boxes with larger text, each still opening its SQL or YAML. One button helper and one overlay in `static/chat-demo.js` now serve both flows. `tests/test_dbtv1_enlarge.py` opens and closes every picture in the chat at 390 px (light and dark) and 1280 px.
- Round ED3, part 1: **Open in Fabric, Run now and Advanced analytics in the Model item** (`docs/SMOOTH/AUDIT.md` section 16, 21 November 2026). Every created item opens in a new tab; a notebook or pipeline Krusgraph created can be run on one click with its state and, after success, the output's first rows (not stored); one line after Create; the stale check said once; starters and analysis notebooks are created in the item's workspace on the data product's lakehouse; Advanced analytics is one section on the Data product step; a same-name lakehouse is reused after a 409.
- Round ED3, part 2: **the Data product step and Publish to OneLake catalog ask once** (`docs/SMOOTH/AUDIT.md` section 12, 21 November 2026). One owner, filled; what the latest Create built is found by its plan marker and added; failed rows point to Fix and finish; the catalog writes only what the data product built (the source is opt-in), never an e-mail address in a description, one grouping and one contract per data product, one description template, writing off said beside the button; the Purview retirement sentence quoted word for word from Learn.
- Round ED2: **Dry run and Create finish or explain once** (`docs/SMOOTH/AUDIT.md` section 10, 21 November 2026). The dry run uses the freshest review and check; the owner is the signed-in person by default, said the same everywhere; with no lakehouse the dry run names the one Create makes, checked against the workspace (a taken name moves to the next free one, said once); outputs are built in order and what is built on a failed one waits; Create stays off with one fix while a known blocker remains; Fix and finish builds only what is missing; an error shared by several outputs is said once; the report waits longer for a new model; this item's own items from an older plan are updated in place; Run once by default; this build's items apart from earlier builds; one grouping of data products everywhere.
- Round BL12: **the evidence register, checked by a test** (21 November 2026, backlog C-24). `tools/evidence_register.py` keeps 28 claims from the README, `docs/TRUST.md`, `fabric_backend/claims.py` and `docs/MISSING-EVIDENCE.md`, each with the file and text that state it, its test, its `docs/LIVE-TEST.md` row, date and class (U unit test, S synthetic run, C customer; no C row yet), writes `docs/EVIDENCE-REGISTER.md`, and `--check` fails on a missing file, text, test or row; `tests/test_bl12_evidence_register.py` runs it.
- Round ED1: **Gustav's editor test, fixed** (`docs/SMOOTH/AUDIT.md` section 9, 21 November 2026). The output cards' Fabric icons are carried in the editor bundle (no broken image); no sentence runs into the next; no "Plan ?"; Choose shows 4 decisions instead of 16 (three ticks and Change), with one line for where silver and gold go and the names shown, not asked; the report says "Built on: <the semantic model above>" by default, with a picker of the workspace's models under Change; Keys and links hides an accept-all at 0, says which items were not checked and why, and says the doubled totals in plain words.
- Round BL8: **SAP tables found with any prefix or suffix** (21 November 2026, backlog C-10). `sap_pack.match` and `pack_table` find a known SAP table with a system id, client, date, version or landing word before or after its name (`ecc_VBAK`, `VBAK_800`, `P01_VBAK`, `bronze.P01_VBAK_prd`), and say why ("VBAK matched as P01_VBAK, prefix P01_"). A table under an unknown name with a pack table's key columns (`MANDT` + `KUNNR`) is reported by the new `sap_pack.recognise` as a suggestion, not applied, so the `sap_renamed` corpus keeps its scores; two tables pointing at one pack table, or a key that fits several, are reported in `Match.ambiguous`, never guessed. No existing SAP test or corpus score changes. Section in `docs/SAP.md`; `tests/test_bl8_sap_names.py`.
- Round SM3: **the same path in the Fabric editor** (`docs/SMOOTH/AUDIT.md` section 8, 21 November 2026). The Model editor uses the chat's five steps and words (Your data · Check · Decide · Dry run · Create) and the same default build (the pipeline with its silver and gold notebooks, the semantic model and the data agent; the API for GraphQL is no longer preticked). The check against the rows runs on its own after Find keys; "Accept all that passed the check" is the only accept-all; Choose shows the three defaults and folds the other six outputs under More outputs; Preview is called Dry run; the drift monitor's "Copy the request for Claude" card is hidden. Open to the dry run: 4 clicks and 2.3 s locally (from 8 and 3.6-3.8 s), flow 26 of the editor's e2e; `tests/test_sm3_same_path.py` reads both surfaces.
- Round SM2: **the start card in five steps** (`docs/SMOOTH/AUDIT.md` section 7, 21 November 2026). Your data · Check · Decide · Dry run · Create instead of nine steps. One usable workspace, source or schema is chosen by the start tool itself ("demo › demo_lh › dbo ✓", Change on tap); Check runs the map, the row check and the doubled totals on its own and says them in one line each; one Dry run everything button runs the pipeline, model and agent dry runs; after Create a closing step offers Open in Fabric, Add a source and Schedule it; the sample has the same dry-run button. Measured locally with `tools/smooth_measure.py` on the synthetic SAP demo: Start to all three dry runs 10 taps and 4.2 s before, 4 taps and 2.8 s after; at most 25 words and 3 buttons plus Next per step; no step scrolls at 390 x 800. The click-through `tests/test_wb15_click_through.py` follows the new path (light and dark); the coach goldens and the hosted listing (the start tool's description) regenerated. Not yet run in claude.ai or Fabric.
- Round BL3: **one count, and "not counted" never reads as passed** (21 November 2026, backlog C-31, C-07). `fabric_backend/counts.py` puts every key and link of a plan in one of four states (holds, fails, no rows to check, not counted) from `validate_plan`'s answer, with one sentence ("Links: 32 of 34 hold, 1 fails, 1 has no rows to check (24 in the plan, 10 the SAP pack lists with a condition)"); a link to a non-unique target never holds. `review.py` writes its totals, check statuses and "Needs attention" from it, so a review can no longer say "Nothing open" with a check not counted (F1 A4, B5, B6, B10). Section in `docs/INFERENCE.md`; `tests/test_bl3_counts.py`.
- Round BL1: **a receipt for every number** (21 November 2026, backlog C-36). `fabric_backend/receipt.py` lists each count `validate_plan` states (keys, links, extended links, amount levels) with the sentence, the exact SQL from the same builders (`evidence.py`, `amounts.py`), the counts, the dialect and the UTC time; `krusgraph receipt` prints it as JSON or as `krusgraph-receipt.md` (`--human`). Tests re-run every statement on the synthetic shop and SAP demo to its stated count and check that no row value is in a receipt (`tests/test_bl1_receipt.py`); `docs/RECEIPTS.md` says how a buyer re-runs one. Not wired into the chat card or the editor yet.
- Round BL5: **planted faults, the shop with five known faults** (21 November 2026, backlog C-37). The new `fabric_backend/shop_faults.py` is the synthetic shop with a duplicate customer key, orphan order lines, an order total on the header of its lines, a link whose values match no row and two currencies in one amount column, each documented with the finding Krusgraph should give. `tests/test_bl5_shop_faults.py` asserts the first four word for word (also through the local `validate_plan` tool) and that nothing else is flagged; the currency fault is not detected yet and the test and `docs/PLANTED-FAULTS.md` say so. New corpus case `tests/corpus/shop_faults.json`; no existing score changes.
- Round BL2: **tenant settings per output, and the getting-started page** (21 November 2026). The new `fabric_backend/tenant_settings.py` lists, per output (lakehouse, notebook, pipeline, semantic model, report, ontology, data agent, API for GraphQL, OneLake catalog write), the Fabric tenant settings it needs, each with its Microsoft Learn page read on 21 November 2026 or marked unverified; `for_outputs` and `markdown` say what to ask the admin for, in order. The live value is not read (the Admin API needs admin permission): every row says "could not be read; ask your admin". `docs/GETTING-STARTED.md` is generated from the module and the new page `/getting-started` (in the sitemap) renders the same; `tests/test_bl2_tenant_settings.py` keeps the three equal. Showing the settings in the dry-run card is the next step, after the SM chain.
- Round DP1: **a catalog of classic data products, and what the packs cover of it** (21 November 2026). `fabric_backend/data_products/catalog.yaml` lists 30 products (customer, sales order, invoice, journal entry, opportunity, subscription ...) with grain, business key, conformed dimensions, measures and their level, typed traps and questions, written from general data-modelling knowledge; `mapping.yaml` places every table of the sap, salesforce, dynamics365 and younium_salesforce packs in it (role, key mapping, confidence, the pack's own evidence) or lists it as not a data product with a reason. `fabric_backend/data_product_catalog.py` loads and checks both and computes coverage per source; `docs/DATA-PRODUCT-CATALOG.md` has the coverage matrix, the gaps per source, the products that need a conformed key across systems, and a design for a rule-based matcher and coverage answer (not built). Data, a loader and tests only: no tool, page or Workload change, no Fabric call; nothing verified on a customer system. `tests/test_dp1_data_product_catalog.py`.
- Round SAPD1: **the SAP full demo, five data products instead of two** (21 November 2026). `sap_demo.tables(full=True)` (and `fabric-backend sap-demo --full`) adds 28 synthetic tables of the SAP pack's procure-to-pay, finance (S/4HANA `BKPF`/`ACDOCA`, cost and profit centers), business partner and pricing (`PRCD_ELEMENTS`) modules to the 17 order-to-cash tables, with planted traps (`EXPECTED_FULL`). `domains.py` names SAP domains of procure-to-pay, finance and pricing; /sources now shows the engine's five SAP data products on the 45-table demo. The 17-table demo is unchanged.
- Round WB4: **Recommended analyses in the Krusgraph Model item** (20 November 2026). Under Next, with other Fabric workloads (and on the Data product page), once a key or link has passed the check, the item ranks the ten SAP order-to-cash analyses of `analysis_plan` (round AP2) on its reviewed plan: a readiness word (never colour alone), one line "Recommended because …", what is missing, and one action. A ready A7, A8 or A3 offers its notebook (Download .ipynb, Copy the code); the rest offer the request to copy into Claude; the not-ready ones say what data would make them ready. New read-only route `POST /workload/v1/analysis` (counts only, nothing created or run, no AI). No Create in the workspace (no create path exists for analysis notebooks); no manifest change. Tests: `wb4Analyses.test.tsx`, `tests/test_wb4_analysis_route.py`, e2e flow 25 on the synthetic SAP sample at 390 px by keyboard; the n225 phone pages regenerated for the new styles. `docs/ANALYSIS-PLAN.md` section 7. Not yet run in Fabric.
- Round CL1: **`krusgraph`, a read-only command line for agents** (20 November 2026). `krusgraph check`, `relationships`, `plan` (validate_plan), `sap` (sap_pack_draft) and `analysis` (analysis_plan) over the local engine, JSON when piped and text with `--human`, stable exit codes 0-6, `--sample sap|sap36|shop` offline, `--folder`, `--columns`, or the ODBC string in `FABRIC_ODBC` (never as an argument). `--apply` is refused; nothing writes to Fabric. Agent instructions in `fabric_backend/skills/SKILL.md`; `docs/CLI.md` on how it follows HKUDS/CLI-Anything's harness conventions and sits next to Microsoft's `fab`; a CLI-Hub entry drafted in `docs/drafts/cli-hub-entry.md`, not submitted. The server is unchanged; no new dependency. `tests/test_cl1_cli.py`.
- Round WB14: **Save to lakehouse Files, behind a switch that is off** (issue #108, 20 November 2026). Beside Download and Copy of every generated file the Model editor can write the file to `Files/krusgraph/<item name>/<file>` in the lakehouse the item targets, through OneLake's DFS API as the signed-in person (delegated Azure Storage `user_impersonation`, asked of the Fabric host). A dry run shows the full path first; a file already there is replaced only after Replace; without the permission the editor says so and Download keeps working; the console gets the status and OneLake's request id only. On only with `KRUSGRAPH_ONELAKE_SAVE=on` on the hosting server; no manifest change. `docs/ONELAKE-SAVE-SETUP.md` has the permission, Gustav's Entra click-list, the test on demo_lh and how to turn it off. Tests: `onelakeSave.test.tsx`, `tests/test_wb14_onelake_save.py`, e2e flow 24. Not run against Fabric.
- Round DIR1: **the hosted connector against the Claude connector directory's review criteria** (`docs/DIRECTORY-READINESS.md`, 20 November 2026). Every tool answer used to tell the model what to do (the Coach block's "Say in one short sentence ... Offer one next step", the lead's "For the assistant, not for the user: please do not repeat", next steps such as "run verify_build with ..."), and the server's instructions did too; now answers, next steps and instructions state options and facts for the user ("Possible next step for the user: ...", "Verify what was built (verify_build with ...)") and leave the choice to the user and Claude. The cards' buttons still call the tools through the host bridge. New `fabric_backend/directory.py`: the last pass over every answer (an instruction to call a tool said as an option; an answer past 40,000 characters folded, its longest texts and lists shortened with a `folded` note). Largest text a model reads: 152,344 characters before, 44,830 after (33-table WideWorldImporters schema); SAP demo 63,824 to 41,772. Fixed: `review_plan` on a large schema answers with groups of tables instead of refusing; `plan_backend` with a `detail` that is not a string answers `bad_input`, not `unexpected`. New: `tools/directory_measure.py`, `tests/test_dir1_directory_readiness.py` (titles and annotations, no imperative to call a tool in any description or answer, every tool on valid input, sizes). Nothing was submitted to the directory and the listing was not edited; no Fabric tenant was read or written.
- Round SM1: **the guided path measured, and the direction for the next rounds** (`docs/SMOOTH/`, 20 November 2026). AUDIT.md walks the path in the chat card and in the Model editor on the synthetic SAP demo and shop: 10 taps and 4.2 s (local, fake host) from Start to the three dry runs, of which 6 taps answer nothing; the dry-run step shows 151-193 words and scrolls at 390 px; the editor needs 9 clicks and preticks only API for GraphQL; 48 tools, about 15 needed by default. MULTI-LAKEHOUSE.md: one lakehouse per layer or per source cannot be written to or combined today (a source lakehouse writes into itself; one source per model, ontology and agent); schemas in one lakehouse work one at a time. COMBINE-SOURCES.md designs SAP + CRM in one data product by counted rules; PLAN.md orders SM2-SM9 with measurable done-lines; PRINCIPLES.md is the list every UI round checks. Fixed: the shop sample's steps 4, 5, 7, 8 and 9 each say their own sentence (step 7 said step 6's). New: `tools/smooth_measure.py`. Nothing was run in claude.ai or Fabric.
- Rounds W12 and MOD1: **the workload package builds as `Krusgraph.Modeler` by default** (PR #26, opened 16 November, brought up to date with `main` and merged 20 November 2026). `workload/scripts/build_package.py` takes the name from one constant, `WORKLOAD_NAME`; `Org.Krusgraph`, the live development workload, is built with `--name Org.Krusgraph`, and the Dockerfile's fallback stays `Org.Krusgraph`. The new `workload/scripts/validate_package.py` checks a `.nupkg` offline (parts, name, version, the kit's XSDs, the publishing fields). CI's workload job builds, validates and keeps `Krusgraph.Modeler.1.0.<N>` as an artifact on every push to `main`, with no repository variable; `.github/workflows/workload-package.yml` (WP1) now builds `Org.Krusgraph` explicitly, so the two never offer packages for the same name. `docs/MODELER-GO-LIVE.md` has the 19 November upload result (the package passed Fabric's checks up to the name registration, which waits on Microsoft), the admin path and the download steps. Nothing was uploaded or registered.
- Round WB15: **one living start card, after Gustav's second phone test of 19 November 2026** (`docs/CHAT-TEST-2026-11-19.md`,
  second section). The guided path had regressed since 12 November: a new card after every choice, two numberings ("of
  9" and "of 8"), small mascots and much text. Now a card button runs the next step inside the same card; one usable
  workspace, source or schema comes chosen with Next on (A); one numbering, "Step N of 9", in the card, the Coach block
  and the lead (B, F); a card that hands a step to the chat folds to "Moved on: step N" (C); the lead asks Claude not to
  repeat the card (D); decisions are ordered by tap in a shared in-memory state (`flow_state.py`) and the buttons are off
  while a call runs (E); every building tool leaves a rejected link out and says so ("23 relationships; 1 left out by
  your decision") (G); the cards send plain words only, never a tool call (H); step 9 suggests the names and confirms
  them (11). Per step: the mascot at the top, one sentence, two or three buttons, Next, and one Details fold. Tests:
  the required click-through `tests/test_wb15_click_through.py` (390 px, light and dark, synthetic SAP demo); older card
  tests follow the new numbering and layout; the coach goldens regenerated. Not yet run in claude.ai.
- Round AP3: **`analysis_plan` counts customers on Fabric** (19-20 November 2026, the first live run of the analysis pack, `docs/LIVE-TEST.md`). The per-customer count named a column `top`, a reserved word in T-SQL, so it failed on the SQL analytics endpoint and A8 said "Only 0 customers"; the column is renamed, and a count that did not run is no longer read as zero (A8, A4 and A3 say which count did not run). `analysis_notebook_draft`'s "not ready" error now hints at `analysis_plan` and `land_next` instead of the keys. Tests: `tests/test_ap3_analysis_live.py`.
- Round RQ1: **`requirements_draft`, a pasted requirements list matched to the checked SAP data by rules** (19 November
  2026). A list the business wrote (for example one Copilot summarised in a Copilot Workspace; nothing is read from the
  Workspace, whose content Microsoft Learn documents no API for) is read one requirement per line (R1, R2 ...) and
  matched by fixed English and Swedish word lists, the SAP pack's table names and a small field glossary, with no AI:
  answerable now, answerable with a trap (a header amount that repeats on every line, a join with rows that point at
  nothing, quantities in several units), missing data (the table or field named: LIKP.WADAT_IST, BSID, VBAP.WAVWR) or
  unclear (one question). Each answerable one gets a T-SQL query starting with its id, the counted evidence from
  validate_plan and the tables for `gold_views_draft` and `semantic_model_draft`; `create_data_agent` takes the same list
  as `requirements=` and adds the answerable ones as example queries. `sample=true` runs it offline on the synthetic
  SAP demo. Read-only, never a row value (a test checks every answer against the demo's rows). On the build card with
  the next steps as buttons (390 px, light and dark). 48 tools (37 read-only); the read-only listing cap 81 500 -> 83 000
  characters, deliberately. Docs: `docs/REQUIREMENTS-TO-FABRIC.md`, `docs/demo/REQUIREMENTS-DEMO.md`. Tests:
  `tests/test_rq1_requirements_draft.py`, golden `tests/golden/rq1_sap_demo.json`. Not yet run against a live workspace.
- Round WB3: **every review decision in the Model item is saved without Save** (F6 in
  `docs/WORKLOAD-TEST-2026-11-17.md`, the founder's yes of 18 November 2026). Accept, reject, a key or a link and Accept
  all are saved to the item's definition a moment later; the line says Saving… and Saved; a save Fabric does not confirm
  is tried once more, then one sentence says so and Save still saves the decisions. An autosave never starts Create.
  **Look for leftovers** words ids that are not GUIDs for a person (F5). PR #99; e2e flow 23.
- Round WB2: **every output that reads silver or gold reads the schemas the pipeline wrote** (issues #54 and #55, from
  LT1 in `docs/LIVE-TEST.md`). The semantic model, the ontology and the data agent take `silver_schema` (the agent also
  `gold_schema`), else the schemas the source's Krusgraph pipeline sets in its notebooks' parameter cells (`pipeline=`
  names one; pipelines that disagree are never guessed between), else `silver` and `gold`; the answer says where the
  schema came from. `verify_build` reads a pipeline's notebooks first and rebuilds the dry run with their
  `SILVER_SCHEMA` and `GOLD_SCHEMA`, so `sap_silver`/`sap_gold` no longer make every notebook "differs"; it also takes
  `silver_schema` for the model. The Model editor's build and verify requests take `silver_schema` and `gold_schema`
  and pass them to the dry run and to Create alike (no field in the editor yet). After `create_pipeline` the next steps
  name a semantic model only when its description carries this plan's marker, which `create_semantic_model` now
  writes. A wrong `tables=` gets a hint about `tables=` instead of keys. New module `fabric_backend/layer_schemas.py`
  (rules only); tests in `tests/test_wb2_layer_schemas.py` with `sap_silver`/`sap_gold` and with the defaults.
- Round WB1: **gold keeps one row per silver row on the SAP path, on Spark 3.5 and 4.0** (F8 in
  `docs/WORKLOAD-TEST-2026-11-17.md`). A gold view's join rule now counts SAP's initial value (a blank, and zeros only in
  an optional field) as no reference, as silver has since AP2: `sap_gold.sap_vbpa` dropped every partner row with a blank
  `KUNNR` or `PARNR` (all five of the demo's), on any Spark; the check notebook's row count caught it. The Salesforce
  pack's views get the same rule. The failure F8 reported on PySpark 3.5.3 was the test's own `SELECT * EXCEPT`, which
  only Spark 4 parses; no join repeated a row. New: the SAP demo through silver, gold and the check notebook on a local
  Spark, and CI's notebooks job on PySpark 3.5.3 with Python 3.11 (Fabric Runtime 1.3) next to 4.0.1. SAP gold built
  before this needs a regenerated gold notebook run again.
- Round CO1: **the coach: one guided path, said like the home page's demo chat** (`docs/COACHING.md`). Every card shows
  "Step N of 8: <stage>" and one mascot line in plain words, one primary button and at most two others, with rule codes
  and the table of checks under Details; every tool result's text carries a short Coach block for the host model;
  "help me with my SAP data in Fabric" starts the path. Fixed rules in `fabric_backend/coach.py`, no LLM.
- Round WB13: **the chat cards after Gustav's phone test of 19 November 2026** (`docs/CHAT-TEST-2026-11-19.md`, issues
  #66, #71, #76 and #89-#93). Every card reports the height of its content, also after a section opens or closes
  (`mcp_apps_size.py`); the check results travel into the review and each card says what its numbers count; every
  card ends with the one most useful next step first, chosen by fixed rules from the plan state (`next_rules.py`);
  step 6 of the start card asks about each open link on your own data, with review_plan's evidence; a map of more
  than eight tables is drawn small first with "Show the map"; the Turtle file sits behind "Show the ontology file";
  the next-step buttons come right after the summary; step 1 says what each workspace holds where documented APIs say it.
- Round DA2: **data agent topics and example-query templates from checked joins.** `create_data_agent` now also writes
  one topic file per business area (Fabric preview, SQL sources on the preview runtime; Staging - Upload Datasource
  Topic) with the tables, what their fields point at, the joins validate_plan counted with their match rates, and the
  known traps (a header total that doubles over its lines), and one example query per checked join with comments where
  a customer, a period or another filter goes. Rules only, no AI; dry run by default; only `krusgraph-*.md` topic
  files are written, nothing is deleted. Unit-tested; not tested live. Sources and the parts that stay design:
  `docs/DATA-AGENT-TOPICS-TEMPLATES.md`. The Domains REST calls Krusgraph prepares were checked: none uses the removed
  preview version.
- Round FA1: **`app_readiness` for a semantic model**, before an app is built from it in Power BI Desktop for Apps
  (preview). With `semantic_model` (read with getDefinition, TMDL), the tool checks tables, measures, format
  strings, relationships, keys and the date table, and names what Fabric's API cannot read (Build and Read permission,
  three tenant settings, a workspace on Fabric capacity). Each check says whether it rests on a Microsoft Learn page
  (linked), on Krusgraph's own rule, or on nothing Microsoft documents. The Model editor's next steps add "Build an app
  in Power BI Desktop for Apps" (guide only) once a semantic model is built. Sources: `docs/APP-READINESS-MODEL.md`.
- Round AP2: **the analysis pack, phase 1** (Gustav's yes of 18 November 2026 to the design's phase 1). Two new tools,
  local and hosted: `analysis_plan` ranks ten SAP order-to-cash analyses by deterministic rules over the plan and counts
  of the rows (never a value; no AI), each with readiness ready/partial/missing, a score, "Recommended because …", what
  is missing, the tables and columns used and the next step, plus `land_next`; `analysis_notebook_draft` writes the
  Fabric notebook for A7 forecasting, A8 RFM segmentation or A3 ABC/XYZ, wired to those tables, with a data check and
  every run logged to an ML experiment (MLflow; AutoML for A7, k-means for A8); it creates and runs nothing. Rules as
  data in `fabric_backend/analysis/o2c.json`. New `fabric_backend/sap_demo36.py`: a seeded synthetic SAP demo with the
  same 17 tables over 36 months (300 customers, 500 materials), as a Fabric notebook (dry run by default, writes only
  its own schema, default `sap_demo36`) and a small CSV sample in `examples/sap_demo36/`. Read-only listing cap raised
  from 75 900 to 81 000 characters for the two tools. `docs/ANALYSIS-PLAN.md`; tests `tests/test_ap2_*.py`, goldens
  `tests/golden/ap2_*.json`, a PySpark case in `tests/test_spark_notebooks.py`. Not yet run in Fabric.
- Round AP2: **a blank partner field in SAP data is no reference, not an orphan** (found 18 November 2026 in the live demo run of
  `sap_lt1_pipeline`, where the silver notebook quarantined 5 `sap_vbpa` rows whose `KUNNR` or `PARNR` was blank). The
  silver notebook (and `silver.simulate`) and the pipeline's check notebook now count a NULL, a blank (`''` or spaces) or,
  where the SAP pack marks the relationship `optional` (VBPA -> KNA1, VBPA -> KNVK, KNVK -> KNA1/LFA1, the `ADRNR` links
  to ADRC), a value of zeros only as "no link" for SAP pack relationships, as `validate_plan` already did for blanks; it
  counts the zeros the same way now. Only a set value without a parent row is quarantined: the item of order 0000000009
  without a `sap_vbak` header still is. `tests/test_ap2_blank_partner.py` and a PySpark case in
  `tests/test_spark_notebooks.py`.
- Round WB11: **more Fabric item icons in the Model editor** (Gustav, 18 November 2026). The icons n184 put on the
  output cards, from Microsoft's `@fabric-msft/svg-icons@12.0.0`, now stand beside every Fabric item type the editor
  names: the next steps' cards (workload and item types at the top left), the Data product page's Built list, Retire,
  the catalog's "What would be written as you" and the source and target buttons. Item icons only, always beside the
  type's name, `alt=""` there; API for GraphQL and Activator use the package's generic item icon.
  `docs/WORKLOAD-DEV.md`, section 13.
- Round WB10: **Gustav's live test of the Model item in Fabric, 18 November 2026: the catalog step's owner, counts,
  dates and descriptions** (issues #58-#61). The owner field is the Data product page's people picker with Me, has
  autocomplete off and refuses an item's name (editor and engine). Every key and link count on the page comes from the
  check recorded in the item, with links between data products stated separately, and every sentence states that
  check's time. The catalog keeps each item's own first sentence and appends the data-product sentence; items
  Krusgraph did not build are offered unticked. `docs/WORKLOAD-TEST-2026-11-17.md`, section 8.
- Round WB10, next steps (issues #62-#64): the Data product page says "No pipeline built for this data product" and
  points to the Data Factory step; the Data Factory card says what is left when the silver notebook is built and ticks
  only that; the Data Science starter has Dry run, then Create of the notebook in the workspace (never run by Krusgraph).
- Round WB12: **The start cards in claude.ai, after Gustav's chat test of 18 November 2026** (issues #66-#77,
  `docs/CHAT-TEST-2026-11-18.md`). Step 6 has Accept, Reject and Skip per open decision with the counted evidence
  (share of values found, distinct values), the decision travels into steps 7-9, and Next is secondary until every
  decision is answered or skipped. Sums are formatted (`fabric_backend/number_words.py`: thousands grouped by a thin
  space, two decimals, the factor such as "about 13.6x") with one plain sentence, and validate_plan's fan-out sums are
  rounded where they are made (`fix_plan.py`). The card reports the height of its content, not of its frame, so frames
  no longer keep blank space. The text the client model reads after `start` says the card already shows the step and
  asks for one short sentence and the step's question. Step 5 shows the item's proof tiles and the 2.2x line; step 4
  says each rule code in words; the "Steps 1-8 only read" sentence is in full on the first card only; finished and
  later steps fold into one line each; steps 1-3 are "skipped (sample)" on the sample; step 9 on the sample offers
  "Start on my data" and "Show the dry run again". The prompt's argument is `use_sample` ("Use the synthetic shop
  sample? Type yes. Leave empty to use your own Fabric data."). Steps 1-3 list the workspaces, sources and schemas
  (with table counts; a schema without tables disabled) as buttons, with a search box over eight, read by `start`
  itself (names and counts only, so `start` is now listed with `open_world_hint: true`); Next waits for the choice.
- Round WB10, downloads (issue #57): every download in the Model editor works inside Fabric's sandboxed frame. The
  engine keeps the file ten minutes behind a signed, single-use link (`POST /workload/v1/file`), the Fabric host opens it
  in a new tab, and it is served once as an attachment; Copy falls back to a visible text area. E2E flow 20 runs the
  editor in an iframe sandboxed as Fabric's.
- Round Q2: **Krusgraph Migrate, from Qlik to Power BI: three tools, a public test corpus and the design of a
  workload of its own.** The founder decided on 16 November 2026 that Migrate becomes its own Fabric workload
  (name proposal `Krusgraph.Migrate`; "Qlik" not in the registered name), with chat tools and a guided page built
  first because name registration is still blocked. **Tools** (hosted and local, read-only, fixed rules, no AI model,
  no connection to Qlik; status "draft only", titles end in "(experimental)"): `qlik_plan` (a Qlik load script as
  tables, keys and associations, each synthetic key in one of five cases, circular references, a proposed star schema,
  and `plan.keys` and `plan.confirmed` for the planning and building tools; with a workspace and a source the keys and
  links are counted in the landed tables), `qlik_measures_draft` (expressions as DAX, labelled translated, suggested
  or not translated with the reason) and `qlik_reconcile_draft` (one T-SQL statement per KPI that compares values
  exported from Qlik with the migrated tables, and the comparison table; it runs nothing and names no reason for a
  difference). 44 hosted tools (41 before), 27 local (24 before); the read-only listing guard goes from 69 000 to
  75 500 characters. **Corpus**: 58 public load scripts from four repositories under the MIT licence as fixtures with
  attribution (`tests/fixtures/qlik/SOURCES.md`); of 1 856 statements the reader reads 1 092, lists 722 as control flow
  and 29 as includes, and leaves 13 not read (813 before the fixes). The reader (`migration_read.py`, the Qlik part) now
  lists control statements and includes on their own, reads variables with built names, `REPLACE`/`ADD` loads, labels
  built by dollar-sign expansion and `CROSSTABLE`, and no longer cuts `lib://` in an Include as a comment. A tool that
  writes its own `kg_card` has it shown as it is (`mcp_apps_words.card`). **Docs**: `docs/MIGRATE-WORKLOAD-DESIGN.md`
  (item type, editor flow, how it shares the engine with Modeler, manifest and Entra, the ask-list for Microsoft; nothing
  built and the name in no build), `docs/MIGRATE-GUIDED-PAGE-DRAFT.md` (a draft, not a page of the site), and section 0
  and 3b of `docs/QLIK-MIGRATION-PRODUCT.md`. Not tested: no script, measure or number came from a Qlik installation;
  the DAX was not run; the statements ran on SQLite, not on Fabric; nothing was deployed.
- Round n227: **The chat cards after the founder's test in claude.ai.** The founder tried the MCP Apps cards on
  12 November 2026 (deploy `src-37ff21adce4ff691`): the Start stepper and its buttons worked and real items were
  created, but the cards drew the raw `summary` where the answer already held plain words in `kg_card`. Now every card
  reads `kg_card` first and every tool has one (with `KRUSGRAPH_MCP_APPS=1` every tool's answer is also
  `structuredContent`; the text answer is unchanged): one result line, at most five lines, repeated notes collapsed
  ("24 links need a combined key column; Krusgraph can add them in a gold view", the list behind Show), details as
  readable lines with the raw JSON behind a second toggle, and never "no summary in it". No tool's name in a button or
  a sentence a person reads; "SAP pack: Krusgraph's list of known SAP keys" the first time it appears; numbers agree
  with their nouns ("1 table", "1 row") and no label is doubled. A sentence the mascot says is on the card only with
  the mascots off. Before the check a plan leads with one primary button, Check against the rows; the builds come
  after a check whose keys hold, and a name ending in `_3` says why. The schema choice never offers
  `krusgraph_quarantine`, and the card no `silver` or `gold` layer while a source schema is there. While a tool runs
  the card says who works on what and for how long (no CSS animation; still under reduced motion), and a create's
  result names the item ("Created shop_api_3, an API for GraphQL, in Fabric."), not the plan again. **A create answers
  in time:** `create_backend`, `create_semantic_model`, `create_ontology` and `create_report` end their wait for
  Fabric 40 seconds after the call began and answer `started` (kind `timeout`, as before) with the operation's id; the
  new parameter `check` on these four reads how it went and creates nothing; Create is never offered or sent a second
  time while the first one's outcome is unknown. "Open in Fabric" is the item's own address for each kind
  (`ontologies/{id}` from Microsoft Learn; `graphql/{id}` is Unverified and the card also offers the workspace's
  list). A created ontology is drawn as a static SVG with its keys marked, readable at 375 px. The text lead is a
  numbered list ("Reply 1, 2 or 3") for clients that draw no card, and the servers' instructions ask the model, with
  the reason, not to repeat a card nor add what the answer does not hold. `docs/MCP-APPS-N227.md` has each point with
  its before and after. Verified by unit tests and Chromium at 375 px under a fake host
  (`tests/test_n227_cards.py`); not tried in claude.ai, and not deployed.
- Round n229: **a verifier of what was built, next steps after every Create, and a gate before a build of little
  use.** The founder, 12 November 2026, in claude.ai with the hosted connector: "an agent that double-checks Krusgraph's
  deployed proposals", "no more suggestions after we built what was proposed", and a Create he pressed although the dry
  run said "Relationships: 0 active, 0 inactive, 24 not expressible". Krusgraph for Fabric uses no AI model, so the first
  is a verifier by rules, and every answer says so. **A, `verify_build`** (new tool, read-only; `verify_build.py`):
  each built item named in `items` is read back with getDefinition and compared with its dry run, built again by the
  same rules from the same plan: a semantic model's tables, columns (the combined key columns of a composite key among
  them), relationships (active or inactive, cardinality, cross-filter) and measures with the table each sits on; a
  report's visuals and the model it is bound to; an ontology's entity types, keys, relationship types and data bindings;
  an API for GraphQL's types, fields and relationships; a pipeline's steps and its three notebooks, line by line. Each
  card of the report (or each measure of a model without one) is counted again from the rows with one SQL statement and
  put beside the model's own number (one DAX query; without a Power BI answer the figure is shown and the line reads
  "not checked", never "verified"). A SUM of a header's amount repeated on every line, a SUMX over line rows of a RELATED
  header amount and a figure equal to a header amount summed over its lines are flagged as doubled totals with both
  sums. State: a model never refreshed, a pipeline never run, an ontology with no graph item beside it, an App still
  empty, each with its one action. One line per item (verified, differs, or not checked with the reason), the counts,
  every SQL statement, and the call's time budget: what it does not reach is "not checked (time)". The answer invites an
  AI client to add its own review under its own heading, apart from Krusgraph's states. 41 tools, 31 read-only; the
  read-only listing's guard goes from 66 700 to 69 000 characters for it. `answer_query_draft`: a sum or average of a
  header's column now starts at the header ("total NETWR per sales order" over sap_vbak and sap_vbap sums on sap_vbak
  alone; the join it replaces dropped orders without lines), a column that is on both the lines and the table the
  question groups by is read as the group's own, and when two of the tables carry the summed column the answer says
  which one was used and how to get the other (F1's B1 and the first half of B2). **B, after a Create** (`after_create.py`): the answer of every creating
  tool ends with `next_steps` in the order of what the data product still lacks (verify what was built; refresh the model
  once; the pipeline with Run once or Schedule; the report; the data agent; the Rayfin App, said as an empty App item and
  one package command that opens inside Fabric only; a drift monitor; register as a data product), each with one sentence
  from the mascot who says it; an item that exists from this plan (read from its type and the description Krusgraph
  wrote) is listed as "already built", and "Download a dbt project draft" is under More, labelled a draft. No step
  writes: a read, a dry run, or a sentence for the chat. `create_semantic_model(refresh=true)` refreshes a new model once
  and only refreshes one that exists. On the build card the steps are buttons in that order. **C, the gate:** a semantic
  model's dry run with no expressible relationship (or most not), or one that reads silver tables that are not there
  yet, and an ontology with most entity types keyless, carry `gate`: one sentence, the step that fixes it first (the
  silver step that writes the combined key columns, n226) and Create second as "Create anyway", no longer the filled
  button. **In the Model editor:** "Verify what was built" under Built in Fabric (`POST /workload/v1/verify`) with the
  result lines, Show the SQL and the next steps. Verified by unit tests on synthetic data with Fabric, the SQL endpoint
  and Power BI replaced by test doubles (`tests/test_n229_verify_build.py`, `tests/test_n229_after_create.py` with the
  card in a real browser, the editor's `verifyBuilt.test.tsx`). Not run against Fabric or Power BI, and not deployed. The
  two Power BI reads and the refresh need `Dataset.Read.All` and `Dataset.ReadWrite.All` (docs/SCOPES.md); the ontology
  graph's state is judged from the workspace's item list, since no documented call gives it. Not done, n227 holds them:
  the server instructions' own sentence inviting Claude's review (it is in the tool's answer instead) and the cards'
  own tests.
- Round F1: **A first-user test without Fabric, and its small fixes.** `docs/FINDINGS-13NOV.md` ranks what a first user
  meets in the hosted and the local MCP server (on the synthetic shop and the synthetic SAP tables), on the site at 375,
  768 and 1280 px and in the Model editor, each with where it is, the fix and the round that should take it, and ends
  with five ideas. Fixed: `fabric-backend-mcp --help` and `--version` answer and return (they started the stdio server,
  which waits and prints nothing); the local server says what to set or install when `FABRIC_ODBC`, the ODBC driver or
  the Azure CLI is missing (kind `server_config` or `sign_in` with the step, where it said "Contact the operator" or
  "Try again"); `docs/LOCAL.md` section 4 lists the 24 local tools as the code has them; four texts in the Model editor
  (the page title, "1 person or group has", "1 try", the source sentence); the health test that read the real clock and
  failed from 14 November 2026 on. Tests: `tests/test_f1_findings_fixes.py`, `f1Words.test.ts`.
- Round n228: **Krusgraph's diagrams as draw.io files.** The founder, 12 November 2026, looking at the semantic model
  draft card in claude.ai: "can I see this as a draw.io file/flow if I want?" The new `fabric_backend/drawio.py` writes
  three diagrams as draw.io's uncompressed mxfile XML, by rules, with the standard library only: the map (tables with
  their key, "no key" marked, composite keys in full; arrows labelled with the column and the rule: R1, R5, SAP pack),
  the semantic model draft (fact and dimension tables in two colours, many-to-one relationships, inactive ones dashed,
  the ones a tabular model cannot express dotted red with the reason, the date table, the measures in their table's
  box; read from the draft's own relationships.tmdl and summary) and the data flow (data_flow.py's nodes and edges:
  bronze, silver, gold, the items on the source, a report on the model, an app on the API). Left to right in columns;
  an edge runs in the gutters between columns and passes a column in a row of its own, so no edge goes through a box
  and no boxes overlap (checked by `drawio.problems()` on 60 and 200 synthetic tables). Ids come from the names and
  every cell is one line, so a re-export of an unchanged plan is the same text. **In the chat:**
  `plan_backend(..., drawio="map" | "model" | "flow")` answers `{filename, mime_type, content, boxes, arrows}` and reads
  what the plain call reads; no tool was added (40 tools, 30 read-only) and the read-only listing is at its cap of
  66 700 characters, which took three small cuts in `plan_backend`'s own words. A file over the answer's 60 000
  characters is left out with how to get a part (`tables`). **In the Model editor:** "Download as draw.io" under the map
  and under the data flow; `POST /workload/v1/drawio` turns what the editor shows into the file and calls nothing in
  Fabric. Not done, because n227 holds the chat cards: the button on the MCP Apps cards and the card map's own routing
  (sap_vbap -> sap_vbak drawn through sap_t001). Verified by unit tests (`tests/test_n228_drawio.py`, golden files in
  `tests/golden/drawio/`; the editor's `drawioDownload.test.tsx`); not yet opened in draw.io itself, and not deployed.
- Round n225: **the Krusgraph Model editor, from the founder's phone test in Fabric of 12 November 2026** (package
  1.0.1074). The Data product page: the plan of every Create is recorded in outputs.json (`plan`, `productWords.withPlan`)
  even when the finish did not answer, and shown with its date; the items are every item that plan built, from every
  Create, with another plan's items listed apart and an output the latest Create built without a saved id listed too
  (Look for leftovers finds it); Retire with nothing chosen takes this plan's items only. The editor's saves:
  `callUpdateItemDefinition` answers undefined when Fabric refuses a save, which the editor took for saved; now such a
  save is tried again (`saveState.saveWithRetry`, an older copy is never sent after a newer one) and the page says Saved,
  Saving or Not saved with Save again. Health: the page sends its plan id (`/workload/v1/health` takes `plan_id`), the
  answer names the run and the plan, and a result older than the latest Create, or another plan's, reads "not checked
  since this Create" before what that run found. The owner says why it matters. Open in Fabric for an ontology goes to
  `/groups/<workspace>/ontologies/<id>` (Learn, "Use Ontology MCP Server"; it went to `/ontologys/`, an error page). The
  App card says before Create, in one sentence by Builder, that Create makes an empty App item, that the package's
  command is the one step left, and that the app opens inside Fabric only; the App stays unticked by default. On a
  phone: the editor's page has a viewport, and at 600 px and below its pages stack to one column, wrap long names, keep
  text at 14 px or more and tap targets at 44 px or more. Tests: `n225DataProduct.test.ts`, `phonePages.test.tsx` (pages in
  `tests/fixtures/n225/`), `tests/test_n225_phone.py` with `tests/n225_browser.js` (Chromium at 375, 412 and 1280 px);
  the n198 pages rendered again.
- Round F2: **count before claiming, the data proposes, and a regression corpus with published scores**
  (`docs/SCOPE-REVIEW.md` section 6, items 4 and 5; unit tests only, not run in Fabric). With a connection the hosted
  plan counts every key by name or from a pack in the same call (`plan.profile`, evidence state "counted unique" in
  `plan_backend`'s own answer); K6 gives a keyless table a key from the rows (the identifier-named or first column
  that is unique and never NULL, else the shortest unique combination of the leading columns); R6 links a column the
  names left ambiguous or unlinked when every value is in one key and the name supports it, and proposes the rest
  with counts; a relationship with orphans is re-counted once under trim, case fold, leading-zero strip and cast
  (`recount` in `validate_plan`: "N of M rows with a value match after stripping leading zeros"); a table the SAP
  pack does not know by name is recognised by its key columns (`plan.pack.by_signature`). The profile uses at most
  half of the call's time budget and 60 statements (`KRUSGRAPH_PROFILE_QUERIES`, `0` turns it off). New
  `fabric_backend/propose.py`; hooks in `infer.py`, `evidence.py`, `coverage.py`, `profile.py`,
  `platforms/local.py` and `server.py`'s `_hosted_plan`. The corpus: `tests/f2_corpus.py`, `tests/corpus/*.json`
  (AdventureWorks with rows generated from its declared constraints, the shop, the two SAP-shaped samples, the same
  with renamed tables, a Nordic-ERP-like and a Business-Central-like shape), `tests/test_f2_corpus.py` and
  `tests/test_f2_propose.py`; the scores are `docs/SCORES.md` and `docs/scores.json`, written from the expected files
  and kept equal by a test. AdventureWorks: keys 47 of 71 before, 62 after; links 62 of 90 before, 87 after; wrong
  links 17 before, 6 after. All rows are synthetic.
- Round n226: **evidence state and coverage, one time budget per call, composite keys carried through**
  (`docs/SCOPE-REVIEW.md` section 6, items 1 to 3; unit tests only, not run in Fabric). Every key and link of
  plan_backend and validate_plan says its evidence state (counted unique, counted and holds, by name only, not counted:
  <reason>, not checked (time), ...) and every tool that makes a plan carries one `coverage` headline. Each read-only call
  has one 45 s budget (`budget.py`): SQL and REST reads are cut to it, the check returns what it counted, "not checked
  (time)" for the rest and a `resume_from`; a failed query is "not counted: <reason>" for its item, not an aborted call.
  The check counts links by importance, each after its target's key (260 keyed tables, max_items=200: 100 keys and 100
  links, before 200 keys and 0 links), and `tables=` scopes it. The silver step writes one combined key column per
  composite key and link, and the semantic model and the ontology relate on them, reading silver: on the synthetic SAP
  sample sap_sd the model goes from 0 relationships (19 not expressible) to 19, the ontology from 0 keyed entity types
  and 0 relationships to 10 and 19. AdventureWorks name-rule scores unchanged (keys 47 of 71, 4 wrong, 20 missed; links
  62 of 90, 17 wrong). Needs a redeploy; no new package or setting.
- Round n223: **the Krusgraph Model editor says what it waits for, and opens with less to wait for**. One loading component
  (`OntoWait.tsx`, words in `waitWords.ts`) for the first load, the review, the check, the dry run, the schema list and
  the Data product page: Onto at the top with a gentle motion (still under reduced motion; a spinner with the mascots
  off), the step's name ("Reading the tables in shop…"), progress where the parts are known (the check: "3 of 7 keys and
  links counted", from `evidence.validate`'s new `on_step` and `workload_api.check_progress`), skeleton rows instead of a
  blank page. After 10 s one line from what the code waits on (the SQL endpoint, a busy capacity (429), a Fabric
  operation, reads that did not get through, else "Still working on it."); after 30 s Keep waiting, See the steps so far
  and, for steps that only read, Cancel (nothing in Fabric changes). Light and dark, keyboard, aria-live polite. Loading:
  the item and its definition are read together; reopening an item with a review shows the saved review and the map kept
  in item.json at once and reads it again behind it (decisions made meanwhile are kept); the schema list is kept in the
  item and listed only where Choose source shows it; the engine's token is asked of the Fabric host once (it was asked
  on every request and every read of an operation); a background step is first read after 300 ms (was 1 s). The map,
  the data flow and the Data product page are their own chunks, prefetched after the editor opens, and the empty view no
  longer pulls in Fluent UI 8: what the editor downloads before it draws went from 1,099,659 to 1,051,956 bytes (313.8
  to 300.1 KB gzip). The manifest did not change: a redeploy, no new package.
- Round n221: **the Krusgraph Model builds in its own workspace, and a key that passed the row check de-duplicates
  silver**. From the founder's live test of 11 November 2026: a Model in a new workspace read a lakehouse of another
  workspace and every output went to that other workspace, "already built from this plan". Now Choose what to build has
  "Build in: this item's workspace (default) / the source's workspace"; the dry run's first line names the workspace;
  "already built" is looked up there; silver, gold and the pipeline's check go to a lakehouse of that workspace (chosen,
  the first by name, or made by Create with Lakehouse schemas when ticked, after the dry run named it) and read the source
  through OneLake; the model, API, ontology, agent and report are created there. The data product and Delete use the
  workspace the items were built in. After Check against the rows, a key whose check passed (or accepted in the review)
  is de-duplicated on in silver and the card says "one row per key: key ... checked against the rows on <date>".
  `docs/WORKLOAD-DEV.md` section 19 with the Learn sources; `tests/test_n221_build_in.py`, `buildPlace.test.ts`. The
  editor changed; the manifest did not, so no new package is needed.
- Round n219: **Start Krusgraph, a guided path in the chat.** After connecting, a customer types *start Krusgraph* (or picks the connector's prompt **Start Krusgraph**): the new read-only `start` tool leads through workspace, source, schema (every schema listed), the map of keys and links with their rules, the check against the rows, accept/reject, doubled totals and a dry run of what would be built (silver, gold, the pipeline with its check, semantic model, report, API, ontology, data agent, with the data flow). Each step is an existing tool; `start` itself reads and creates nothing, and hands over a writing call only for names the user confirmed after the dry run. *Show me on the synthetic shop sample* runs it without Fabric. With KRUSGRAPH_MCP_APPS=1 the answer is a stepper card whose buttons run the steps. The server's instructions offer it on a vague first message. /start, /docs, README and docs/START-KRUSGRAPH.md say *type start Krusgraph*. Forty tools; the read-only listing cap is 66 500 characters.
- Round n216: **one look for the mascots: the glossy 3D figures of the overview film everywhere the products and the
  workload show them**. New `tools/mascot_renders.py` cuts Onto, Thinker and Builder out of the film's closing frame
  (112 x 112 px, transparent ground, own soft shadow so they work on dark pages) into `fabric_backend/static/mascots/`
  and `workload/Workload/app/assets/mascots/`. The four product cards ("Choose how you work", home page and /choose) show
  the 3D figure at 56 px (2x) with the product's prop as a small badge and one alt text per card. The workload's banner,
  Get started card and quick look use the 3D figures (the banner at the render's own 112 px, so it stays sharp); the
  item icon, workload icon and favicon stay the logo mark, which reads at 16-32 px. In the Krusgraph Model editor Onto,
  Thinker and Builder are the 3D figures at 48 px, the pose kept as a small lean, tilt or hop (still under reduced
  motion), the Mascots on/off switch as before. The Claude card no longer says "or another MCP client": with
  /mcp/connect off it says only Claude signs in to the hosted service; with it on it names VS Code and Cursor and
  /mcp/connect, in "Who it is for", "What you need", "How you work" and the VS Code row of the decision guide.
  `docs/MASCOT-ART-NEEDED.md` lists what is still flat and the renders that would replace it (props, poses, 512 px,
  transparent). The manifest images changed, so a new package is needed.
- Round n220: **run and schedule the pipeline from the chat, and a report name already taken**, after the founder's
  chat of 11 November 2026 (Run once answered 403; create_report refused a name the dry run had found free). The hosted
  MCP app may now hold `DataPipeline.Execute.All` as an **opt-in** permission (deploy switch `pipeline_execute`, server
  `KRUSGRAPH_PIPELINE_EXECUTE`; the deploy check then demands it with admin consent), listed with why on /it, in
  `docs/SCOPES.md` and `docs/TRUST-PACK.md` section 5; scope names cited from microsoft/fabric-rest-api-specs
  `dataPipeline/swagger.json` and Learn's Job Scheduler pages (read 11 November 2026). `create_pipeline` runs or schedules
  only after a dry run that shows what runs and when and the person's yes: the dry run's `jobs.confirm` passed back as
  `confirm_jobs` (the Model editor confirms in its own review); the run is read by polling the job instance. A token
  without the permission gets no bare 403: the dry run already says so, Create makes the items without asking Fabric to
  run them, and the answer names the app, the permission, admin consent and reconnecting, with "Run it in the Fabric
  portal". `create_report` with a taken name offers the next free name (checked), the existing report, says whether
  Krusgraph made it on this model and whether the name was free at the dry run, and checks the name again right before
  the create. Every error or refusal now ends with 1 to 3 next steps, on n218's cards too (`mcp_apps_next.error_steps`):
  the answer's own steps first (a dry run under the free name, a link opened with `ui/open-link`, or a sentence sent to
  the chat), else Try again and "Explain this and what to do"; a step never writes, and review_plan's card still opens no
  link. The build card offers "Use <name>_N" as a dry run where the name is taken. `tests/test_n220_run_from_chat.py`.
  Redeploy; the founder adds the permission in Entra (`docs/SCOPES.md`).
- Round n202: **a synthetic, SAP-shaped sample for demos, /check and films, with customer-specific Z tables**. New
  `fabric_backend/sap_sample.py`: `sap_sd` (order to invoice: `T001`, `KNA1`, `MARA`, `MAKT`, `VBAK`, `VBAP`, `LIKP`,
  `LIPS`, `VBRK`, `VBRP`) and `sap_mm` (purchase to pay: `T001`, `LFA1`, `MARA`, `MAKT`, `EKKO`, `EKPO`, `EKBE`), from a
  seed, a few hundred rows per table, two years of dates, every standard table and column a name the SAP pack already has
  (no `MATDOC`: the pack does not describe it; `MAKT` has its key only). Invented Z tables: `ZSD_ORDER_EXT` (MANDT +
  VBELN, one planted orphan), `ZSD_KAM_ASSIGN` (custom names only, `ZZ_KUNDE_NR`), `ZMM_PO_CONF` (confirmed dates for the
  late-delivery KPI). Planted: `VBAK.NETWR` over `VBAP` (the doubled total, with a wrong and a right gold view that
  `sql_sums` tells apart), orphan items, late goods receipts. Measured on Z tables: no key by name (K3); links through the
  standard key fields by R3, the rows confirming `ZSD_ORDER_EXT` -> `VBAK` and `ZMM_PO_CONF` -> `EKKO`/`EKPO` and
  rejecting `ZSD_ORDER_EXT` -> `LIKP`/`VBRK`; nothing found by the row checks alone (R5 and suggest_relationships look
  at single-column keys, SAP keys start with `MANDT`); `ZZ_KUNDE_NR` -> `KNA1` not found. `seed(spark, sap=True)` writes
  both (default off); /check offers "SAP-shaped sample (synthetic)"; `docs/SAMPLE-SAP.md` (tables and pack sources,
  findings, film scripts with the engine's numbers); `/docs` answers "Does Krusgraph work on customised SAP tables (Z
  tables)?"; `tests/test_sap_sample.py`. Synthetic, SAP-shaped, not SAP data. Redeploy for /check and /docs.
- Round n213: **a 30-day trial per organisation, then a Microsoft Marketplace subscription**, off until
  `KRUSGRAPH_TRIAL=1` (`docs/BILLING-MODEL.md`). The first authenticated call from an Entra tenant on the hosted MCP
  server or the Fabric workload starts its trial (one row in the subscriptions' table, no names or e-mail); after 30 days
  without a subscription, writing to Fabric is refused in plain words with the offer link and reading, checks and dry
  runs still run (`fabric_backend/billing.py`, one decision for tools and routes). The publisher's tenant (and a guest in
  it) and the pilot tenants are exempt. Users per organisation are counted as salted hashes only (`/privacy`); over a
  plan's cap the users and the founder are told, nothing is blocked. Founder events with an Azure Monitor alert in
  `docs/OPERATIONS.md`; `POST /workload/v1/access` and one quiet line in the editor; `/pricing` says it is planned;
  `deploy/krusgraph.sh --update --dry-run` lists what is missing. What Microsoft Learn allows for terms and notice, with
  sources, and a recommendation (no monthly plan with a three-month notice exists) are in the doc. No prices.
- Round n212: **standards on `/trust`, an opt-out for AI training crawlers, and a trust page comparison**. `/trust`
  and `docs/TRUST-PACK.md` get a Standards table: one row each for ISO/IEC 27001, NIS2 and the Swedish cybersecurity
  act, GDPR and Microsoft's publisher requirements (publisher verification, the workload attestation), each with what
  Krusgraph has (linked), what it does not have and what would come next. `/robots.txt` keeps search engines and the
  fetchers AI assistants use for a person's question, and asks GPTBot, ClaudeBot, Google-Extended, Applebot-Extended,
  CCBot and Meta-ExternalAgent out of everything (sources and dates in `docs/SITE.md`; only Anthropic's page could be
  opened, the others are marked Unverified); `/trust` says in one sentence that it is a request, not a block. Stale
  lines fixed: "no tool deletes anything" (`/trust`, `/docs`, the trust pack, `docs/TRUST.md`,
  `docs/PILOT-ONBOARDING.md`) now names the data product page's Delete from Fabric (n198); the ISO 27001
  self-assessment knows the incident process and the supplier pack of n211 (5.25 and 5.28 from missing to partly).
  New `docs/TRUST-PAGE-COMPARISON.md` (Modern Requirements' public trust and pricing material, from search snippets
  since the host was blocked, and five improvements for `/trust` and `/pricing`). No claim of certification or
  compliance. Site and docs only; redeploy for `/trust`, `/docs` and `/robots.txt`.
- Round n211: **a supplier security pack for customers under NIS2 and the Swedish cybersecurity act**. New
  `docs/SECURITY-SUPPLIER.md` (what the texts say with sources, Krusgraph's place in a customer's supply chain, roles,
  what is and is not in place, subcontractors, the Article 21 measures against what Krusgraph has) and
  `docs/INCIDENT-RESPONSE.md` (detect, assess, contain, notify, review; the notification time is a proposal for the
  founder). The site serves a vulnerability disclosure policy at `/security` (and `/security.md`), and
  `/.well-known/security.txt` names it as its Policy instead of the file on GitHub. `/trust` and `docs/TRUST-PACK.md`
  get a section linking them; questionnaire row 18 moves from Planned to Today, partly. No claim of compliance,
  certification or approval. Docs and site only; redeploy for the new page and the security.txt Policy line.
- Round n210: **verification of the integrated main before the first guest users** (n197 to n209). Security: Turn off
  (the Data product page's soft retire) used a schedule id from outputs.json unchecked in a DELETE path, so a crafted id
  could become a hard delete of another item while the dry run said "Remove the schedule"; only GUID ids are used now,
  and Delete from Fabric leaves an item recorded in another workspace alone. Guests: "by whom" and **Me** fall back to
  the token's email (and a guest `#EXT#` sign-in name read back), tests with guest-shaped tokens, and
  `docs/GUEST-TRIAL.md` says which tenant id the allowed list needs. The page asks for health with the Model's own
  workspace (it sent the source's, which failed when they differ). `build-package` stops in a shallow clone instead of
  giving a version below the one in Fabric. An end-to-end test of the mill sample read from a mirrored database. Unit
  tests and test doubles only; redeploy for the engine and the editor, the workload manifest did not change.
- Round n209: **the Krusgraph Model ready for the first outside users** (the founder's live tests of 10 November 2026).
  The dry run and Create take one decision (`workload_api.existing_decision`, each card's `decision`): items built from
  this plan, also by another Krusgraph Model item, are "already built from this plan, will be skipped" in both; red only
  for an item someone else made; "would be updated" only where Create writes. Gold views no longer repeat the join keys
  (`orders_order_id` and the like); the orphan rule moved to the view's WHERE with the same rows kept and dropped. The
  review says "This link holds in the rows: 0 of N rows point at nothing." next to Reject and what rejecting such a link
  costs the semantic model, the API and the ontology. An App already built keeps its choices and package link on reopen.
  With Run once ticked the data agent's example queries are checked and the agent published only after the run
  succeeded; a failure to connect is retried once and reads "not checked yet", never "invalid". An end-to-end test of
  review, dry run, Create, the Data product page with health, Update and Retire (n198, n200, n201 together).
  `docs/GUEST-TRIAL.md` (new) and a section on /pilot/fabric: B2B guests in the publisher's tenant before the workload
  name is registered, cited to Microsoft Learn with Unverified where Learn is silent. Not run against a live workspace.
  Redeploy for the engine and the editor; the workload manifest did not change.
- Round n201: **the Krusgraph Model reads mirrored databases**, SAP mirrored through SAP Datasphere among them, and
  warehouses and SQL databases (the founder, 10 November 2026: the detail page said "Compatible with: Lakehouse"
  only). The source picker offers the four item types; review and check read the SQL analytics endpoint, read-only.
  A read-only source's silver notebook, gold views and pipeline (with its check) write to a lakehouse the person picks
  (Target lakehouse; default the first lakehouse of the workspace, said in the dry run), and the silver notebook reads
  the mirrored tables at `oneLakeTablesPath` (Get Mirrored Database on Learn) in OneLake, with no copy outside Fabric
  and no shortcut. For SAP tables the review marks the SAP pack's keys (with MANDT) and links "from the SAP pack" with
  the pack's public sources, and says what mirroring delivers (Initial and Delta, Parquet) and that SAP Datasphere
  Premium Outbound Integration is the customer's licence matter. Both workload packages list MirroredDatabase,
  Warehouse and SQLDatabase as compatible item types, show the founder's overview film first on the detail page, and
  point the "Certification" link at the attestation page, which says "Draft." at the top. New: `fabric_backend/mirroring.py`,
  `docs/SAP-MIRRORING.md`, `tests/test_n201_mirrored.py`, `tests/test_n201_manifest.py`, `sourceWords.ts`. Not run
  against a mirrored database in Fabric, and no SAP Datasphere was available. A new workload package is needed.
- Round n198: **the Data product page** in the Krusgraph Model item (the founder's question of 10 November 2026: how to
  remove items, update ontologies and data products, and look after the workspace after Create). An item with outputs
  opens on it: name, owner (picked from the workspace's people, kept in the item), health (n200's route when present,
  else "not checked yet"), the pipeline's last run, the plan id and every item with its state in words (built, pending,
  failed, changed outside Krusgraph, missing, removed) and Open in Fabric. *Check against the rows again* lists what is
  out of date with the existing Update path (an App only under a new name). *Retire* turns off the schedules Krusgraph
  made, then *Delete from Fabric*: a dry run of exactly what goes, the data product's name typed, Delete Item per item;
  only items in outputs.json, never a lakehouse, a table or a view's data; each removal recorded with when and by whom.
  *Clean up leftovers* finds items with Krusgraph's plan marker that no Krusgraph Model lists (such as demo_lh_model4)
  and offers Adopt or Delete. `fabric_backend/product_life.py`, `POST /workload/v1/product`, `DataProductView.tsx`,
  `productWords.ts`; `docs/PROMOTE-DESIGN.md` (dev → test → prod with Fabric's Git integration and deployment pipelines,
  design only). Not run against a live workspace yet. Redeploy and build a new workload package to see it.
- Round n200: **health over time and alerts** (Lifecycle round 1, `docs/LIFECYCLE-DESIGN.md` section 8;
  `docs/HEALTH.md`). The pipeline's check notebook appends one row per check to `krusgraph.health`
  (`krusgraph_health` without schemas): run id, time, plan id and fingerprint, check, object, rule, status, count and
  the previous run's count of the same plan. Checks: keys, orphans, rows and sums through each gold view's join (pass or
  fail only, never the sums), row counts of every silver table and gold view (warn when one falls by 50 % or more),
  freshness of each source table from Delta's table history (a commit time; warn after 2 schedule intervals, fail after
  3) and quarantine counts per rule. Never a row value. The pipeline's silver notebook starts with a drift step against
  the plan the outputs were built from: a source table or a used column gone stops the run before anything is written,
  with the reason; anything else is recorded. Optional alert: an Adaptive Card to a Teams workflow or Power Automate
  HTTP trigger whose address is an Azure Key Vault secret the owner names on the pipeline (`alert_key_vault`,
  `alert_secret_name`, `alert_on`), never in code; the pipeline card gives the steps for Fabric's free e-mail on a failed
  scheduled run. `POST /workload/v1/health` returns one health word per data product (green, amber, red, not checked
  yet) and the open findings, read as the signed-in user. All notebook code is written into the cells verbatim (no
  `%pip`, no import of this library), tested on SQLite and a local PySpark; not yet run in Fabric.
  Redeploy, then Create again to give an existing pipeline the health step.
- Round n205: **trust, honest labels, a comparison and findability** before the launch of 11 November 2026, after a
  reviewer's report of 10 November ("the biggest obstacle is trust, not technology"). `/trust` ("Security and data",
  Markdown twin `/trust.md`), written from `docs/TRUST-PACK.md`: what passes through, that no table contents are
  stored, the region, sub-processors, delegated permissions, how to revoke, what is and is not in place (no
  certification held, the attestation a draft, no penetration test) and the questionnaire answers; linked from the
  footer, `/pricing` and `/choose`, in the sitemap and llms.txt. Every hosted tool whose status is neither "tested end
  to end" nor "created live" has "(experimental)" at the end of its title (`tool_status.experimental`, applied in
  `_titled_tool`; today `domain_draft`, `sap_pack_draft`, `create_views`, `create_data_agent`,
  `compare_semantic_model`); `create_pipeline`'s short status is "created live" (it created and ran `pipeline_shop` on
  7 November). The README's status block per tool is generated from `tool_status` and tested equal; the README's
  first line says what Krusgraph does and that this is its source, and a Roadmap section lists what is planned.
  `/choose` has "Why not just Microsoft's tools?" (five rows, linked from `/docs`); `/pricing` says what is free today
  and that a Marketplace team plan is planned with no price. `docs/FOUNDER-TODO.md` lists the GitHub settings only the
  founder can change. Two titles were shortened to keep the read-only listing under its 64 500-character cap.
- Round n204: **the Marketplace landing page accepts personal Microsoft accounts as well as work accounts**, as
  Microsoft requires of a SaaS offer sold through Microsoft (Learn, "Plan a SaaS offer", Technical requirements;
  certification policy 1000.3). With `KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_ID` (deploy key
  `marketplace_signin_client_id`) and its secret (`marketplace_signin_secret_keyvault_uri` or the container-app secret
  `marketplace-signin-secret`) the buyer signs in through `/common` with a new, separate Entra app, *Krusgraph
  Marketplace sign-in* (work or school accounts of any organisation and personal Microsoft accounts), scopes `openid
  profile email`; unset, the page works as before (`/organizations`, the site's app, `openid profile`). The site's main
  app keeps its audience (`AzureADMultipleOrgs`). The ID token's issuer is checked for the consumer tenant
  (`9188040d-6c67-4c5b-b112-36a304b66dad`) and for organisational tenants; a token for another app is refused. A
  personal account resolves, sees and activates the subscription exactly like a work account (the beneficiary tenant
  comes from resolve), and the page says that Fabric needs a work account in the tenant shown, with that tenant's
  admin-consent link. The landing page's cookies are now signed (a hand-made cookie naming another subscription is
  refused), and the access log line of `/marketplace/` drops the query (the purchase token). `docs/MARKETPLACE-SETUP.md`
  section 2a: the founder's Entra steps; `docs/MARKETPLACE-CERTIFICATION-NOTES.md`: the *Notes for certification*
  draft and the listing checklist (policies 100.1–100.7, 1000.x). `tests/test_n204_marketplace_personal_accounts.py`.
  Redeploy to use it: create the app, set the two keys, `bash deploy/krusgraph.sh --update`.
- Round n197: **Create runs in the background, follows the pipeline run and finishes on its own.** Every editor request
  answers at once (202 and an operation id) and the editor reads the operation until it ends: no request is held open
  longer than 30 s, so the 230 s "no answer" and the phone's "Failed to fetch" are gone. Operations live in the client
  registration's store (Table Storage across replicas), so a reload, a closed tab or a phone asleep resumes the same run.
  Throttling (429, PFE_FABRIC_THROTTLED) is "waiting for capacity" and retried; Fabric's long-running operations are
  followed ("still running in Fabric", never failed) and adopted; items are recorded as pending before they are sent.
  With Run once ticked the run is followed on the pipeline's card, then the model is refreshed, the report made, the
  agent's examples checked and the agent published if ticked; a failed run stops them with the reason. Try again on
  every red card, Create the rest on the result; truthful dry run and Next; the App with one Cloud Shell command.
  `docs/WORKLOAD-DEV.md` section 15. Redeploy: `bash deploy/krusgraph.sh --from-azure --update`.
- Round n196: **The film at the top of the home page, under the headline.** The overview film moves from its section
  below the hero to directly under the headline, the sentence and the two buttons, centred, up to 960 px wide on a
  desktop (narrower on a short screen, so the headline, the buttons and at least the top half of the film fit at
  1280 x 720) and the full content width on a phone, where the 4:5 version still plays (n161). It is muted, loops, plays
  inline, preloads only its metadata, and has a visible Pause/Play button with an accessible name; site.js starts it
  unless the visitor prefers reduced motion, when the poster stays and nothing plays until asked. It is on the home page
  once; /docs keeps its own. Three blocks leave the home page: the before/after chip with the three points and the SAP
  line (the sentence and the points now open /docs as "What Krusgraph does", before "Which Krusgraph should I use?"; the
  SAP line stays on /docs and /sap), "Which Krusgraph should I use?" with its rows and the no-AI paragraph (on /docs and
  /choose already), and "What Krusgraph reads" (its two paragraphs and three points are now "Data and access" on the /docs start page).
  The footer on every page says "Krusgraph is a preview service" with links to the test status per tool and to how data
  and access are handled. A customer quote, Swedish with the English translation, anonymous by request and published
  with the person's written permission, on /docs' Get started page only; the docs' Markdown renders "> " as a quiet
  blockquote. No new copy otherwise. Tests: tests/test_n196_home_film.py and tests/n196_browser.js (375, 768, 1280 and
  1440 px, light and dark; reduced motion; the button by keyboard); the tests that pinned the old places moved with the
  blocks. Redeploy to see it live: `bash deploy/krusgraph.sh --from-azure --update`.
- Round n195: **Krusgraph.Modeler ready for Microsoft's publishing review, as far as the repository can make it.**
  The vendor attestation (Section III of Microsoft's template, filled from what the code does: no row values, delegated
  permissions only, Azure Container Apps in Sweden Central, the one read-only admin call, and every open point marked
  "Not yet") is a page at `/workload/attestation` with a Markdown twin, marked **Draft** and `noindex` until the
  founder removes the marker, not linked from the home page or the navigation. The Krusgraph.Modeler package's
  `Product.json` points `productDetail.supportLink.certification.url` (the attestation link Microsoft's review and
  validator read) at it; `Org.Krusgraph`'s package is byte for byte as before. `build_package.py` refuses a
  Krusgraph.Modeler package without what the review reads and we can fill (publisher, en-US texts, https links, icon
  and banner sizes, learning material) and prints the one gap it cannot fill (no Marketplace offer); the CI `workload`
  job builds both packages. `docs/WORKLOAD-PUBLISH.md` is now the founder's runbook: the name-registration blocker and
  a support ticket text, publisher verification, the upload with the name letter by letter, Microsoft's test tenant
  and pilots on the Publish tab, the target tenant's setting and consent, the form's page 2 answers and a TODO list.
  `tests/test_n195_attestation.py`. **To put the page live, redeploy** (`bash deploy/krusgraph.sh --from-azure
  --update`), **then build Krusgraph.Modeler again.**
- Round n192: **a synthetic manufacturing sample, 'mill', beside the shop.** `fabric_backend/mill.py` generates a
  fictional Swedish workshop (Ystervik Mekaniska) from a seed: sixteen tables with names of our own (customers,
  suppliers, items, bill_of_materials, work_centers, sales, purchase and production orders with their lines and
  operations, inventory_transactions, deliveries, item_prices, a staging table and an event log), 5 012 rows, two
  years of dates. It has single keys, two composite keys (order + line), role columns (bill-to and ship-to customer,
  parent and component item), a code key (`work_center_code`), a self-reference the engine does not link, and planted
  problems: four orphan rows, a duplicate id in `stg_supplier_prices`, 12 late deliveries and a keyless event log
  (`tests/fixtures/mill/planted_issues.json`). /check offers it as **Manufacturing sample** (`/check?example=mill`);
  `seed(spark, mill=True)` writes it to a schema `mill` (off by default; the shop stays the default).
  `tests/test_mill.py` pins the plan's 15 keys and 24 relationships with their rules, the exact findings, and runs the
  KPI queries of `docs/SAMPLE-MILL.md` (on-time delivery, order backlog, inventory value, work center load, BOM cost
  roll-up). **To see the button live, redeploy:** `bash deploy/krusgraph.sh --from-azure --update`.
- Round n194: **the home page from before n190 is back.** The founder looked at the live site after n190 and kept the
  previous home page: the film, the session replay, the hub, the FAQ and the developer note are on it again, with
  n188's navigation and the "Connect to my Fabric" label (n190's commits 868e063 and 3c3a9e2 reverted). Kept from
  n190: n190's **What you can build** grid (seven outputs, each with its status chip from `fabric_backend/claims.py`,
  the chip legend and the sentence on dry run, opt-in Run once or Schedule and /check's drafts), unchanged in look, now
  at the top of /docs after *Which Krusgraph should I use?* and the film, and in /docs.md; /choose no longer says Krusgraph for Fabric
  never runs the pipeline. Not kept: the chips on /start, /choose and /pricing and /check's `intent=` landing.
  `docs/WEBSITE_UX_AUDIT.md`, `WEBSITE_COPY_REWRITE.md` and `WEBSITE_IMPLEMENTATION_PLAN.md` stay as reference, marked
  not applied. The tests n190 retired or changed are back as they were; `tests/test_n194_site.py` replaces
  `test_n190_site.py` and `n190_browser.js`. **To see the old home page live, redeploy:**
  `bash deploy/krusgraph.sh --from-azure --update`.
- Round n190: **the home page redesigned after the outside UX review of 9 November 2026.** One promise ("Your data
  already has connections. Krusgraph finds them.") with **Try the free demo** (the guided demo, no account) and
  **Connect Microsoft Fabric** (the label is now that everywhere); four intent tiles (Find broken relationships,
  Understand how my tables connect, Build a Power BI model, Prepare my data for an AI agent) that open /check on the
  sample with `intent=…` and land on the findings, the map, the Power BI draft or the ontology and evidence; the
  engine's map of the sample under the hero; a before and after computed from the engine's run, with each issue in
  plain words and its check and rule on expand; **What you can build** with one status chip per output (Tested live,
  Preview, Experimental) from the new `fabric_backend/claims.py`, derived from `tool_status.py`, and the same chips on
  /start, /choose, /pricing, the docs' *Test status* and the Markdown twins; one sentence on running and scheduling
  (only Krusgraph for Fabric, opt-in, with `DataPipeline.Execute.All`), which resolves the contradiction the review
  found; /choose no longer says Krusgraph for Fabric never runs the pipeline (n185 added Run once and Schedule). The
  navigation is Product, Examples, How it works, Pricing, Docs and **Try free demo**. /check, the blog, the pilot,
  GitHub and the legal pages are in the footer. The session replay, the hub, the film, the FAQ and the developer
  note left the home page (the film stays on /docs). `docs/WEBSITE_UX_AUDIT.md`, `docs/WEBSITE_COPY_REWRITE.md` and
  `docs/WEBSITE_IMPLEMENTATION_PLAN.md`; tests in `tests/test_n190_site.py` and `tests/n190_browser.js` (375, 768
  and 1440 px, light and dark). Redeploy to publish.
- Round n188: the home page's points are three: **Checked against your rows**, **Errors before anyone sees them** and
  **One checked plan, every starting point** (what the Krusgraph Model item creates from the reviewed plan; the silver
  and gold tables fill when the pipeline runs; /check gives drafts). The SAP point moved to its own page, **/sap**: the
  keys with MANDT and the links of VBAK, VBAP and their neighbours from the SAP pack, each with its public source, linked
  from the home page in one line. /check's *Go further with these tables* has four tiles, 2 x 2 from 760 px and stacked
  below: Build a Power BI model, See it as an app, **Build a Fabric IQ ontology** (the RDF/XML download, with its ?) and
  **Hand over the evidence** (the evidence report). The docs start page and the docs menu begin with **Which Krusgraph
  should I use?**. Redeploy to publish.
- Round n185: **Run once and Schedule** for the pipeline the Krusgraph Model creates, both off by default. Run once
  starts one run after Create and shows each step with its duration and a link. Schedule is daily or every N hours, in
  a time zone (default Europe/Stockholm), with the next run time; a Krusgraph schedule is updated, never doubled, and
  others are never touched. Both need `DataPipeline.Execute.All`; without it they are shown disabled with the steps.
  Run and schedule ids are kept in `outputs.json`. The MCP tool `create_pipeline` takes `run_once` and `schedule` with
  the same dry-run wording.
- Round n185: the **data agent reads one layer** (silver, gold or the source, never two copies of a table; the founder
  saw shop and silver ticked together). Its examples' validation is shown, and the card says Fabric shows them as
  *Example queries*, not as the chat's suggestions. **Publish the agent in Fabric** and **Also make it available in
  Microsoft 365 Copilot** are separate ticks, both off. Publishing happens only with one layer and, with Run once, after
  the run succeeded. Copilot has no API and gets a preflight (capacity, tenant settings, licences).
  `docs/DATA-AGENT-PUBLISH.md`, also on the agent's MCP tab. The report's footer line and the last table row have room
  at 1280 x 720. `docs/WORKLOAD-DEV.md` step 14. Needs a redeploy, `DataPipeline.Execute.All` with consent in the Entra
  portal (only for Run once and Schedule), and a new workload package version.
- Round n184: the Krusgraph Model editor's **output cards show the Fabric icon of the item type** each creates (Notebook
  for the silver notebook and the gold views, Pipeline, Semantic model, Report, Ontology, Data agent, App; the generic
  Fabric item icon for the API for GraphQL, which Microsoft's package has no icon for), 20 px left of the title, with
  the item type as alt text, on *Choose what to build* and on the dry-run and Create cards. The icons are Microsoft's,
  unmodified, from the npm package `@fabric-msft/svg-icons@12.0.0` that Microsoft Learn offers for Fabric platform
  extension development; *About and notices* in the editor and `THIRD_PARTY_NOTICES.md` carry the terms and the
  trademark line. **Default names** follow one pattern from the lakehouse (`demo_lh_api`, no longer `demo_api`).
  `docs/WORKLOAD-DEV.md` step 13. Needs a redeploy and a new workload package version.
- Round n184, additions from the founder's live Create: while Create runs, the line counts "4 of 9 created, 1 creating,
  4 waiting"; the data product lists the pipeline's notebooks as notebooks; no card step names a tool ("Run
  demo_lh_silver first"), the report asks for a refresh only when Create's refresh did not happen; the report's visuals
  are counted alike in the dry run and on Create, with what was not drawn and why; a pipeline that did not exist says
  created; the App card says the App item is empty and puts its commands under "Still to do (in a terminal with Node)".
  **Create ends clearly**: a banner ("Done: 9 of 9 created in demo", or "Done with problems" with the reasons), the
  mascots celebrating (mascot switch and reduced motion respected), a green, amber or red mark on each card, *Next* and
  *Keep it up to date*, kept in `outputs.json` and shown again with its date when the item is reopened.
- Round n183: the **product diagram is a data flow**, on the home page and on `/choose`: your tables in Fabric
  (lakehouse, warehouse, mirrored databases) → one Krusgraph engine (keys and links, checked against your rows) → built
  in Fabric (semantic model, report, ontology, API for GraphQL, pipeline and notebooks, data agent, App (Rayfin, preview),
  data product). The four products sit above the engine as the ways to drive it, each with its "Data passes:" line;
  on a phone everything stacks in that order. "The diagram in words" is a collapsed `<details>` under it. Each product
  card has its **mascot hugging a symbol** we draw ourselves (the founder's decision): Onto with a data table for
  Fabric, the Thinker with a speech bubble for Claude, the Builder with an app screen for Lovable, Onto with code
  brackets for Open Source, with "for ..." under it; inline SVG with alt text, hidden by the mascot switch, and no
  partner logo anywhere. The **home page is calmer**: hero, demo, the diagram, the five-row guide ("We code in VS Code or
  Cursor" → Krusgraph for Claude (any MCP client)) and one line, "Krusgraph is a preview service. Test status per
  tool."; the "Build on the relationships you've reviewed" list moved to the docs' *How it works*, the long status
  paragraph to the docs' *Test status*, which now also says what the Krusgraph Model item creates, the App included.
  The **Krusgraph Model item icon** is Fluent-style (a rounded container, a soft gradient, a slight depth, the three
  connected nodes in Krusgraph's colours), sized by Microsoft's item icon guideline, and is the editor's logo at the top
  left. The workload's banner has no text, so the workload page's own text no longer runs into it. Needs a redeploy and
  a new workload package version (new icons and banner): `docs/WORKLOAD-DEV.md`, section 12.
- Round n181: **App (Rayfin, preview)** is one more output of the Krusgraph Model item. Preview first checks the tenant
  setting "Enable Fabric App Items (preview)". When it is off, a plain card names the setting and says where an
  administrator turns it on, and nothing more happens. Fabric's own 403 "The feature is not available" gets the same
  card. The person ticks key figures, list pages and charts; these are rules over the plan, use no AI and are stored in
  outputs.json. The dry run shows the pages and the read-only connector. Its API has queries only and no mutation
  types, and carries every link, R5 ship_to_id included. A package for the `dataapp` template comes with it, with
  `rayfin/tsconfig.json`; CI runs `tsc --noEmit` on it. It also gives the `rayfin login`, `connector add` and
  `rayfin up` commands. Create makes the App item with Microsoft's documented call (Create App Backend,
  Item.ReadWrite.All) and records its id and plan. The pages are published with the package, because no App item
  definition is documented. The MCP tool `rayfin_connector` runs the same preflight first and answers with the admin card
  when App items are off (no new parameter: the tool listing stays under its size cap). Sources: `docs/RAYFIN-APP.md`.
- Round n177, follow-up (the founder, 9 November 2026, evening): **four product names** on `/choose`, in the diagram and
  in the workload docs: Krusgraph for Fabric (the Krusgraph Model item), Krusgraph for Claude (the MCP connector, which
  works in other MCP clients too), Krusgraph for Lovable and Krusgraph Open Source. The docs group is now *Krusgraph for
  Fabric* (`/docs/krusgraph-for-fabric`). There is one Krusgraph logo, the site's own, on the engine: no product icons,
  no mascot per product, and partner names as plain text only. `/choose` says that the chat demo and /check are ways to
  try it, that the drift monitor, the SAP pack and the dbt export are features, and that buying through Microsoft
  Marketplace is planned.
- Round n177: **Which Krusgraph should I use?** A new page, `/choose` (and `/choose.md`), compares the four ways: in
  Claude, in other AI agents over MCP, run it yourself, and the Krusgraph Model item in Fabric. For each it says who it
  is for, what you need, how you work, what it builds, where the data passes, what is free or paid (only what /pricing
  says), its status (from tool_status and LIVE-TEST) and what it lacks today, followed by the founder's four-line decision
  guide. It says plainly that the Fabric item uses no AI model. The **product offering diagram** (one engine in the
  middle, the four ways around it, what is built in Fabric on the right) is on the home page and on `/choose`. It is
  inline HTML and SVG in the site's colours, stacks on a phone, has a list in words under it, and each way is a link
  with a focus ring. All of it is rendered from `fabric_backend/offering.py`. The docs have a new group, **Krusgraph in
  Fabric**: what the item does, with four screenshots of the editor's own components on synthetic data
  (`workload/scripts/screens/`), how to add it (pilot on request, `/pilot/fabric`; Workload Hub listing planned, not
  available), permissions in plain words (from `workload_api.KINDS`), network hosts and troubleshooting. `/start` has
  **Use it in Fabric** next to Claude and the other agents, in the path cards. Fixes from the
  founder (8-9 November):
  - In full screen the film is letterboxed (`object-fit: contain`), and its file follows the orientation: 16:9 in
    landscape, 4:5 upright.
  - The chat demo says "That is the demo" only after the last step.
  - The fixes and dbt steps' status sentences say what LIVE-TEST records: the option is unit-tested, and the tool
    without it ran live (`tool_status.LIVE_OPTIONS`; a test reads LIVE-TEST).
  - On the /check map, linked tables take neighbouring seats. Interface lines read "interface · product_id", and the
    dashed "?" line has hover text.
  - The dbt step in the chat demo and a new `dbt_schema` MCP Apps card draw the project's flow (sources → staging →
    marts → model, boxes folded, a click shows the SQL or YAML; `fabric_backend/dbt_flow.py`). The chat and the card
    share one renderer.
- Round n176: **Krusgraph.Modeler**, the permanent workload name (the founder's decision of 9 November 2026), for up to
  20 selected tenants. `workload/scripts/build-package --name Krusgraph.Modeler` builds it (item type
  `Krusgraph.Modeler.Model`); `Org.Krusgraph` stays the default, and every other `Krusgraph.*`
  name is refused. The name is written once, in the build. The hosted editor reads the workload from the item it opens,
  so one image serves both names; `KRUSGRAPH_WORKLOAD_APP_ID_URI` takes a comma list and tokens for each URI are accepted.
  A user from a tenant outside `KRUSGRAPH_WORKLOAD_ALLOWED_TENANTS` gets a 403 with `kind: tenant_not_allowed` and a plain
  message in the editor, no longer a 401 sign-in answer. `docs/WORKLOAD-PUBLISH.md` (the founder's steps: Entra, server,
  upload with the irreversible name dialog, Selected tenants, next pilot, withdrawing; keep the existing app as the
  production app), `docs/PILOT-ONBOARDING.md` and the page `/pilot/fabric` (the pilot administrator's five steps).
- Round n180: in the Krusgraph Model, "already built" means built from this plan. Every item a Create writes records
  the plan it was built from (plan id, schema fingerprint, exact schema, links) in outputs.json and at the end of its
  Fabric description. On a re-run, an item built from another plan gets the card "built from a different plan (schema
  Shop, 6 links; now shop, 7 links)", and one built before plans were recorded "built by Krusgraph, plan unknown"; nothing
  is written for either, and the card offers Update (where the tool updates in place; a dry run first, whose
  `confirm_update` the engine requires before it writes) or Choose a new name. Cards of existing items show what the item
  holds (notebook cells and views, report pages and visuals, model tables, data agent example questions) or no count,
  never "0 visual(s)" for a report that has them. Addition 4: Create refreshes a semantic model it has just created once
  (Power BI REST Refresh Dataset In Group, `Dataset.ReadWrite.All`), waits up to two minutes and says refreshed,
  refreshing, refresh failed with the reason, or the missing permission with the Entra steps, before the report is
  built; the dry run says so. The report's title names the model, not its id, and its cards and slicers are sized so
  their captions fit at 1280 x 720. Needs a redeploy, a new workload package version and `Dataset.ReadWrite.All` on the
  workload's Entra app.
- Round n179: Create in the Krusgraph Model sends one request per output (the model before its report), each card with
  its own progress and result; a lost answer says "no answer yet, it may still be running in Fabric" on its card instead
  of "Failed to fetch" for the page; the created ids are saved after each output. A re-run (`skip_built`) shows the
  outputs already in the workspace (built by this Model, or with Krusgraph's description from a Create whose answer was
  lost) as already built and writes nothing for them. The report tries a new model's definition again before it says
  why (`source_not_ready`). Every error on `/workload/v1` is JSON with the CORS headers, and the console log has one
  JSON line per output, failure and server start. `POST /workload/v1/schemas` lists the lakehouse's schemas with their
  tables; the editor offers them as a list (the only schema with tables preselected) and the free-text schema field is
  gone unless the list cannot be read. The semantic model's card is in words (it showed "[object Object]"); generated
  gold SQL names the rule without the certainty number; the flow says plainly that the model, API, ontology and agent
  read bronze even when gold views are built, and that building them on gold is a later option; the permissions are
  folded into a Permissions note. Needs a redeploy (`docs/WORKLOAD-DEV.md`, Hosted, step 9).
- Round n175: a schema typed in another case than the source spells it (`Shop` for the lakehouse schema `shop`) is
  read and queried under the metadata's spelling on every path: the MCP tools, the editor's review, check and build,
  R5's counting queries and the creating tools' definitions. Live on 9 November 2026 the check had failed with
  `Invalid object name 'Shop.addresses'` (42S02) and the review had shown 6 links instead of 7. Table and column names
  in `keys` and `confirmed` are spelled as the metadata spells them too. The answer says which name was used
  (`schema_used`: asked, used, note); the editor saves the exact name and shows a notification. Two schemas that differ
  only by case answer `kind: schema_ambiguous` with both names, and nothing is counted. The workload's page in Fabric:
  the Krusgraph logo mark as the workload icon (64 px), favicon (32 px), item icon and a distinct active item icon (48 px) and the New item card's 24 px icon, sizes Microsoft's validator approves, a banner in the
  site's style with the mascots, the getting-started steps, the editor's map as the quick look
  (`workload/scripts/build_manifest_images.py` draws all eight), a description of every output, the data product and the
  data flow, publisher Kruse Consulting AB, and the hosts IT must allow. The editor's loading view shows the Krusgraph
  mark instead of the Fabric logo. The site's /it has **Network: hosts to allow** (`workload.krusgraph.com` and
  `krusgraph.com`, 443, TLS 1.2 or later) with the symptom "Krusgraph Model keeps loading"; the docs' first-time errors
  and `docs/WORKLOAD-DEV.md` have it too. Needs a redeploy and a new package version (`docs/WORKLOAD-DEV.md`, Hosted,
  step 8).
- Round n174: the Krusgraph Model item builds everything the MCP tools build. **Choose what to build** offers the silver
  notebook, the gold views, the pipeline, the semantic model, a report (on that model or an existing one), the API for
  GraphQL, the ontology and the data agent (left unpublished); `POST /workload/v1/build` takes `outputs: [{kind, name}]`
  and calls each output's MCP tool (`create_silver_notebook`, `create_gold_views`, `create_pipeline`,
  `create_semantic_model`, `create_report`, `create_backend`, `create_ontology`, `create_data_agent`) on the plan the
  review left, on-behalf-of the user, dry run first: one card per output, the data flow first, the model before its
  report. It never writes over an item of the same name that this Model did not build (`already_exists`), and a report
  is never updated in place. Each card lists the delegated permissions the output needs; when the user's token lacks
  one the dry run says so and Create refuses that output with `kind: consent`, the permission and the Entra steps for
  the workload app. Nothing is run or scheduled; no Execute permission is used. **Data product**: an optional name over
  the build, with the domains `domain_draft` proposes, an owner nobody has chosen yet and the plan's version, kept in
  `outputs.json` with the created ids; a re-opened item shows it and offers **Update** where the tool updates in place.
  **The data flow, drawn**: bronze tables → silver tables (one row per key, the links each checks) → gold views (which
  silver tables each joins, on which columns, with the rule) → what is built on the source, and the pipeline's steps
  below; dashed where the build does not make it; Builder presents it. A click, Enter or Space on a box unfolds its code,
  exactly the dry run's: the notebook cell, the CREATE MATERIALIZED LAKE VIEW, the pipeline activity, the model's
  relationships and measures (`fabric_backend/data_flow.py`, `FlowView.tsx`). Not added to the Claude cards: the three
  flow tools have no MCP Apps card yet. Phase 1's form (`name` with `["graphql"]`) answers as before. Needs a redeploy,
  new Entra permissions on the workload app and a new package version (`docs/WORKLOAD-DEV.md`, Hosted, step 7).
- Round n173: the Krusgraph Model editor in Fabric (workload.krusgraph.com), from the founder's run on 8 November
  2026. **Check against the rows** in the review (Home ribbon and a button): a new route, `POST /workload/v1/check`
  (same workload audience and on-behalf-of path as `/review`), runs the counting queries on the reviewed plan and
  writes each key's and link's check into `review.json`: passed (green), failed with its orphans, duplicates or empty
  values (red), not checked (grey); the dry run then says what passed instead of "Not checked: validate_plan". The
  review draws the plan as the MCP Apps cards' map (the cards' own code, copied by `workload/scripts/build_card_map.py`
  and checked current by a test) with the review and check states; **List** keeps the rows. Onto, Thinker and Builder
  speak in the editor with the site's figures and colours; Thinker's question about a table without a key comes with
  its choices inline (`/review` takes the person's `keys` and `confirmed`). **Accept all** and **Accept all that passed
  the check**. Plain-English summary and rows; rule codes stay as pills with a tooltip. Needs a redeploy, then a new
  package version in Fabric (`docs/WORKLOAD-DEV.md`, Hosted, step 6). The MCP cards, the site and Marketplace are
  unchanged.
- Round n172: the MCP Apps cards polished for the film (`docs/MCP-APPS-POLISH.md`), from the founder's try in Claude on
  8 November 2026. A read on the SQL analytics endpoint that fails with a transient connection error (SQLSTATE 08S01,
  the TCP Provider's 0x2714 and other socket errors, Azure SQL's transient error numbers) is tried again on a fresh
  connection, at most three tries with 1 s and 3 s between them; the sign-in, syntax errors and timeouts never are.
  When every try fails, `plan_backend` says the count could not run (`proposed[].not_counted: "failed"`, a summary
  line, `counted_in_rows.failed`), the card draws the link grey, "not counted", and the Thinker offers **Count again**.
  The cards: the map's labels sit on their lines and cover no table; Onto says the plan in short sentences once ("7
  tables, 6 with a key. 7 links: 6 by name, 1 found from the values ..."), the Thinker and the Builder speak plain
  English and never show arguments (the buttons carry them; text clients keep each action's `say`); the titles are
  "Plan" and "Plan check"; the Plan check card shows the Builder's three builds with the drafts under **More**; how a
  tool was tested and "certainty" are left out of the cards (still in the text answer), the rule shown instead;
  `create_semantic_model`'s inactive relationships now carry their `rule`. Fixed: in Claude no **Create** appeared under
  a build's dry run (all four builds): the MCP SDK passes every default to the tool, so the Create action carried
  arguments the card had not sent; buttons are now built from the arguments the call changed, and the card compares
  effective arguments.
- Round n171: Krusgraph can be bought through Microsoft Marketplace, all off by default (`KRUSGRAPH_MARKETPLACE`,
  `docs/MARKETPLACE-SETUP.md`). `/marketplace/landing` signs the buyer in (the existing Entra app, `openid profile`
  only), resolves the purchase with the SaaS fulfilment API v2 and activates on the buyer's click (nothing to activate
  with auto activation); `/marketplace/webhook` checks Microsoft's bearer token (issuer and `tid` our tenant, `aud` the
  fulfilment app, `appid`/`azp` the Marketplace SaaS API), confirms each event with Get operation, records it once per
  operation id and acknowledges ChangePlan, ChangeQuantity and Reinstate. One row per beneficiary tenant in the
  entitlements table (subscription id, offer, plan, status, updated_at; no user data). With `KRUSGRAPH_ENTITLEMENTS=1`
  as well, creating calls (`dry_run=false`) in the MCP tools and the Fabric editor's Create (`/workload/v1/build`, HTTP
  402) answer `kind: upgrade` with the offer's link when the tenant has no active subscription; reads and dry runs stay
  free; the card's Create shows the message and a button to the offer. `deploy/krusgraph.sh --update` carries the new
  variables over and lists by name what is still missing. Not tried against a real offer yet.
- Round n170: the chat demo's pictures in the MCP Apps cards (the founder's ask of 8 November 2026,
  `docs/MCP-APPS-PICTURES.md`). With `KRUSGRAPH_MCP_APPS=1`: `plan_backend`, `validate_plan` and `review_plan` draw the
  map of tables and links (key columns, rule and column pair on each link, passed green, failed red with the orphan
  count, not checked grey, rejected dashed); `ontology_draft` and `create_ontology`'s dry run draw the ontology proposal
  with the keyless entity types and why; `domain_draft` (now on the build card) draws the data products, each a card with
  its tables, no owner yet and dry-run buttons for an API for GraphQL and a semantic model over its tables. The drawing
  is cut from `chat-demo.js` when the card is built; the pictures' data is in `structuredContent` only, so the text
  answer is unchanged. "Try in Claude" on the home page and `/start`: copies the first question and opens claude.ai/new
  (claude.ai documents no prefilled chat for the web), with "Open in Claude Desktop", which does
  (`claude://claude.ai/new?q=`), and "connect Krusgraph first" pointing at step 3. Not tried in Claude yet.
- Round n169: the mascots' next steps on the MCP Apps cards are buttons (the founder's ask of 8 November 2026,
  `docs/MCP-APPS-BUTTONS.md`). With `KRUSGRAPH_MCP_APPS=1`, `plan_backend` and the creating tools (`create_semantic_model`,
  `create_ontology`, `create_backend`, `create_report`) get a build card and every card ends with the Thinker's and the
  Builder's buttons, built from the answer's new `actions`: "Check against the rows", "Build a semantic model", "Create
  an ontology", "Create an API for GraphQL", each a dry run under a free name derived from the source (shop_model_2,
  never one the workspace has), then "Create" on the dry run's card only, with the same arguments and `dry_run=false`;
  after a create "Open in Fabric" and, after a semantic model, "Create a report on it". A host without app tool calls
  gets the button's prompt as a chat message (`ui/message`). `plan_backend` without `schema` on a source with several
  schemas asks which (`choose_schema`) instead of planning one. Claude's sign-in: `/start`, `/docs`, the connect
  chooser, `llms.txt` and `/consent/done` give Claude `https://krusgraph.com/mcp/connect` with "Register automatically",
  with one line on why; `/mcp` keeps working for existing connectors. Not tried in Claude yet.
- Round n164: the mascots' names follow their colours differently (the founder's decision of 7-8 November 2026).
  Onto is green (the wide, low figure; maps how the data connects and says the numbers), the Thinker violet (the round
  pear; checks against the rows, finds what does not hold, asks the questions), the Builder coral (the upright egg;
  builds, always after a dry run). Each role stays where it was; `KINDS` in `static/mascots.js` is the one place where a
  name meets its colour and figure, `site.css` has `--onto`, `--thinker` and `--builder` (with `-soft`, `-ink`, `-d`)
  from the palette, and the chat demo's names, the notes on `/demo`, `/mascots`, the MCP Apps cards and the alt texts
  follow. Two placeholders that named a "maker" (no such mascot; they drew Onto) now draw the Builder. The logo is
  unchanged. `docs/MASCOTS-RENAME-LOVABLE.md` has the prompt for the Shop Desk app in Lovable and what to change by hand.
- Round n154: n149 partly undone after the founder's feedback of 8 November 2026. The replay ("A replay of a session in
  Claude") is back in the home page's hero, under the two buttons as before n149 (on a phone directly under them), with
  the small 2 000 → 1 000 card under it; its first round starts with question 1 already sent and answered, and the
  thread starts under the panel's heading, so the panel no longer opens on about 200 px of empty space (same questions,
  answers and note). The chat's "Try a demo" button is back on the home page, now also on /check, and on every page the site
  renders (the blog included); on /check, whose policy still lets the page fetch nothing, the chat reads the same plan
  from the page, and the button steps aside while it would cover the drop area. In the chat, "Fix data issues" and
  "Write dbt tests" (until now "Create a dbt flow", both marked Planned) link the docs of what exists today: the silver
  notebook with its quarantine table (/docs/build-from-a-plan/one-plan-five-fabric-pieces) and dbt_schema's schema.yml
  with tests (/docs/reference/tools); only a whole dbt project is said to be planned. n149's headline, labels, Blog
  link, /check card and /start line stay. `tests/test_n154_replay_and_widget.py` (with tests/n154_browser.js).
- Round n151: create_report's default page reads like a report, after the first live run with visuals on 7 November
  2026 (`shop_report_visuals` on `shop_model`, every figure right; `shop_report_lovable` from Lovable; both recorded in
  docs/LIVE-TEST.md, and create_report's own note no longer says the page was not yet created in Fabric). Plain titles
  from a tested mapping ("Rows in orders" -> "Orders", "Rows in order_items" -> "Order lines" when order_items points at
  orders, a sum of a quantity column -> "Units"; any other measure keeps its name); cards only for business tables (not
  `audit_log`), at most four; a grid that fills 1280 × 720 between even margins, the category chart taking the month
  chart's width when there is none, the table across the page with its columns sized to fill it and a total row; data
  labels; a month and a category slicer when the fields exist; the page title "Overview · <model>", a dated footnote
  "Created by Krusgraph from the checked plan", and a Krusgraph theme in the site's colours (`StaticResources/
  RegisteredResources/Krusgraph.json`, registered in report.json). create_semantic_model formats counts and sums of whole
  numbers as `#,0`, reads (read-only) the first and last date of the related date columns so the calendar spans the
  data's years, and whether a decimal quantity column holds whole numbers only (the shop's `quantity` is DOUBLE), and its
  calendar has `Year Month`. Every PBIR part is validated against Microsoft's schemas, copied from microsoft/json-schemas
  eecc60d into tests/fixtures/pbir_schemas (MIT). Not run live yet. `tests/test_n151_report_look.py`.
- Round n149: the home page and /check lead with the problem (the UX review of 7 November 2026). The home hero asks
  "Why is your total twice what finance says?" and shows the 2 000 → 1 000 before and after as a small card under its
  two buttons; the replay moved down, after the steps. One primary and one secondary way in with the same labels
  everywhere: "Check my tables" (/check) and "Connect to my Fabric" (/start), in the hero, the middle section, the
  closing card, after a /check result, on /pricing, in the navigation and the footer. The client chooser (Claude,
  Lovable, VS Code, Cursor) moved from the hero's "Connect ▾" to step 3 of /start ("Choose your client"); /start opens
  with "Coming from /check?" and a jump to that step, the requirements folded under it. No floating "Try a demo" on the
  home page (nor /check, as before); one "Try the guided demo" button, after the total that doubles. The test status is
  said once, by the tools list. /check: a card after a result leads to /start and says what it needs (a Microsoft work
  account; an admin approves once, linking /it); the footer's "Run it locally" is a text link and its demo button is
  gone; at 375 px the drop area and the privacy line come before the example cards. Blog is in the main navigation; the
  article on the total that doubles is linked from the home page's example and /check's example cards (there is no
  /join-validation page). The data line on the home page and /pricing is n146's. `tests/test_n149_lead_with_problem.py`.

- Round n146: one source for permissions, data flow and test status, after the outside review of 7 November 2026.
  `fabric_backend/access.py` holds the app's delegated permissions (equal to the deploy check's `REQUIRED_SCOPES`, read
  7 November 2026), what each tool uses them for and whether anything runs or is scheduled, the tokens kept per client
  with their lifetimes from the code, and the two data flows (hosted, self-hosted); /start, /it, /privacy, llms.txt and
  docs/SCOPES.md render from it. create_semantic_model, create_ontology, create_data_agent and compare_semantic_model are
  no longer "available when enabled by the operator": the app has had Item.ReadWrite.All since 28 October 2026. Each
  tool now has separate fields (status word, where available, last operation tried live, date, result, still open);
  "Experimental" is kept for tools never tried live, and tools with a dated live run after 27 October 2026 (or a partial
  one that day) are "Tried live", create_pipeline among them. Planning is described with R5's bounded counting queries,
  the checks with what stays unchecked, the analytics line as "no third-party analytics", /start's step anchors work,
  /local separates what was tried on SQL Server 2022 from what was not, and Claude Code gets one connect instruction.
  Text only: no behaviour, scope or storage changed. `tests/test_n146_one_source.py` fails when two pages state
  different permission lists, status words or Claude Code advice; the texts in page_templates/DOCS.md and README.md that
  still contradict it (held by another round) are strict xfails there.
- Round n146, second part (after n145 released README.md, DOCS.md and LIVE-TEST.md): DOCS.md's "What it accesses" shows
  the generated permission table, the planning and checking sentences and the two data flows; "For agents" and "Other MCP
  clients" give Claude Code `{{CLAUDE_CODE_CONNECT}}`; the status definitions add "Tried live" and say no tool needs an
  operator-enabled permission; README's permission list and "not granted" lines follow access.py, and it records the
  pipeline run of 7 November 2026 (also filled in docs/LIVE-TEST.md). The promise line is now "every proposal shows its
  basis, and the checks you run show their results" on the home page, /docs, llms.txt and the README. By Gustav's
  decision of 7 November 2026, `amount_levels`, `plan_sql_server` and the local server's plan_backend, validate_plan,
  data_dictionary, dbt_schema and answer_query_draft are "Tried live" (SQL Server 2022 in a container, 28 Oct 2026;
  not run from Windows/Claude Desktop yet); the other local tools stay Experimental. The consistency test has no xfails.
- Round n143: lineage with runs=<pipeline or notebook> reads the item's latest runs (Fabric's job-instance list), each
  Notebook activity's status (its notebook's own run in the pipeline run's time window, a heuristic), the error text as
  Fabric returns it, and a category with a next step from a catalog of Spark/Fabric errors (import, table not found,
  permission, capacity paused or throttled, timeout), marked as a heuristic. Only GETs and getDefinition; Item.Read.All,
  which the hosted app has. Unit-tested only (docs/RUN-RESULTS.md). The catalog's layout follows FreelexHo/power-bi-mcp
  8d2e873 (MIT). create_pipeline's status now says pipeline_shop ran live on 7 November 2026 (run 9de8bc49, all three
  steps succeeded).
- Round n140: create_pipeline's check notebook is self-contained. Seen live on 7 November 2026: pipeline_shop's
  silver_shop and gold_shop succeeded, pipeline_shop_check failed with "ImportError: cannot import name 'pipeline' from
  'fabric_backend'", because its %pip installed the published release, which is older than main and has no pipeline
  module. The check (keys unique and never NULL, orphans, gold rows and sums against the silver fact table) is now plain
  PySpark and Python in the notebook (`pipeline.CHECK_CODE`), with no %pip and no import of the library; it still raises
  on a failed check, so the pipeline run fails, and prints a summary when the check holds. The check activity no
  longer sets _inlineInstallationEnabled. The drift monitor's notebook still installs the library (docs/LIVE-TEST.md).
- Round n139: dbt_schema project=true writes valid staging SQL. Seen live on 7 November 2026 on the shop schema: a
  column the draft keeps as the source has it (varchar without a length in the endpoint's metadata) carried a trailing
  comment, and the separating comma came after it, inside the comment, so the next select item followed without one
  (stg_shop__addresses, audit_log, categories, customers, products). `dbt._select_list` now writes the comma before
  the comment, and comment text is kept on one line. Only the staging models of the dbt project draft had the problem;
  the marts, the T-SQL views, gold views, join paths, evidence queries, data agent examples, answer drafts and fixes put
  their comments on lines of their own. `tests/test_n139_sql_parses.py` parses every SQL file and SQL draft for the shop
  schema (as the seed and as a SQL endpoint reports it), n138's synthetic 15-table fixture and every schema fixture
  (4 to 71 tables) with sqlglot's T-SQL parser (gold's Spark SQL with its spark dialect), 1 968 pieces, so a dropped
  comma or bracket fails CI.
- Round n138: MCP Apps card polish after the first live run (Claude desktop app, 6 November 2026, demo_lh/shop), still
  only with `KRUSGRAPH_MCP_APPS=1`. review_plan's ER diagram drew orders.customer_id → customers through the audit_log
  box and put labels on top of each other; it is now a layered layout (`mcp_apps_review.LAYOUT_JS`, inline SVG, no
  loads): referenced tables above the tables that refer to them, edges at right angles through the gaps between tables
  and rows, each label on its own edge on a track of its own. validate_plan's card with nothing to attend to says
  "Nothing needs attention." under Needs attention and the result sentence once, in the summary line. The buttons
  ("Run <tool>", "Record decision") send the specification's `tools/call` request only to a host whose
  `ui/initialize` answer has `hostCapabilities.serverTools`; a host without it, a JSON-RPC error, a result with
  `isError` and a host that does not answer within 20 s each give a sentence on the card (`mcp_apps.CALL_JS`). What a
  button's tool answers is no longer one large JSON block (seen live with semantic_model_draft and ontology_draft): a
  short summary read from names and counts only, never a row value (`mcp_apps.RESULT_JS`): semantic_model_draft its
  tables by role, relationships, measures and notes; ontology_draft its entity types with their keys, relationship
  types, and its notes as questions to the user; any other tool its `summary`; the whole answer behind a collapsed
  "Show details". The same on the review card for an answer without a review file. Tool
  count and listing cap unchanged. `tests/test_n138_card_polish.py` (Chromium) checks the diagram geometrically for
  the shop and a synthetic 15-table fixture, wide and light and narrow and dark, plus the empty-attention line and the
  request shape in each host mode, and the summaries with the live shapes of both draft answers.
- Round n137: the MCP Apps cards read the tool result. Seen live in Claude on the web and in the Claude desktop app on
  6 November 2026: validate_plan's card listed the whole answer as one JSON string under "Needs attention" (no
  mascots, no next-step buttons) and review_plan's card said it held no review file. Cause: the tools return `str`, so
  the SDK derives the output schema `{"result": string}` and sends `structuredContent: {"result": "<JSON text>"}`; the
  cards parsed only the text content and listed the wrapper's `result` as an attention line. Both cards now read the
  result in every form a host may deliver (`mcp_apps.READ_JS`): `structuredContent` when it holds the answer, else the
  text content as JSON, unwrapping `{"result": "<JSON text>"}` in either place; what cannot be read gives one short
  sentence, never a JSON dump, and a mascot never says a JSON text. validate_plan's card shows an all-passed answer's
  `result` sentence under the counts instead of under "Needs attention". With `KRUSGRAPH_MCP_APPS=1`, validate_plan and
  review_plan also return the answer as `structuredContent` (text content unchanged) and are listed without the derived
  output schema; with the flag off nothing changes. Tool count unchanged. Browser tests
  (`tests/test_n137_card_reads_result.py`, Chromium) feed both cards each payload shape with the live shop answers.
- Round n136: the site's mascots on both MCP Apps cards (`fabric_backend/mcp_apps_mascots.py`), still only with
  `KRUSGRAPH_MCP_APPS=1`. Onto says the counts (the answer's `summary`), the Thinker the first thing that needs
  attention, the Builder the next step (validate_plan's first next step; review_plan's `note`, now also shown under
  "Next steps"). Each sentence is a string of the text answer and is also on the card; a figure with nothing to say is
  not shown. Glad (celebrate, heart) only when every check passed and nothing needs attention; never on a failed or
  stale check, an error or a cancelled call. A visible "Mascots: on/off" button on each card hides them; no storage.
  The figures are inline SVG built from the shapes in `static/mascots.js` inside the package (flat colours, no `url()`
  references, no animation); nothing outside `fabric_backend/` is read. Text answers, tool count and listing size are
  unchanged. Unit and browser tests (`tests/test_n136_card_mascots.py`, Chromium at 340 and 480 px, light and dark,
  under the specification's default CSP); not yet tried in a real MCP Apps host.
- Round n126: column-level usage in semantic models (LANDSCAPE idea 5, `fabric_backend/dax_refs.py`). A small DAX
  reference scanner reads the measures and calculated columns of a model's TMDL: `Table[Column]`, `[Measure]`, quoted
  names and measures over measures, followed to the end with the path; strings and comments are skipped. A name it
  cannot settle (several candidates, unknown, SELECTEDMEASURE and other dynamic references, unsupported syntax) is
  listed as could not be read, never guessed, and so is every expression that depends on one. `plan_drift` adds
  `column_usage` when a removed column or lost table reaches a semantic model (the model's definition is read again);
  `compare_semantic_model` adds it for each model column whose source column is gone. No new tool; still the same
  count. Calculation groups, calculated tables, format string expressions, roles, sortByColumn and hierarchies are
  not read. Unit-tested on a TMDL fixture over the shop schema and on the shop model draft; not run against a model
  in Fabric.
- Round n122: `dbt_schema` takes `quality` (`"gx"`, `"soda"` or `"both"`) and writes the plan's key and relationship
  checks as a Great Expectations suite per table and as SodaCL checks, each with its rule and counts, as drafts.
  `profile=true` adds a dbt-fabric `profiles.yml` beside the n114 project, with placeholders and no secret. No new tool.
  Unit-tested; not run against GX, Soda or a Warehouse, not deployed.
- Round n125: `lineage` takes `format="openlineage"` and then returns its graph as OpenLineage run events instead of
  its own graph (the default, `format="graph"`, is unchanged). Tables become datasets with their column names and types,
  each object Krusgraph found or created becomes a job, and a Krusgraph facet carries the edges and each checked
  relationship's rule and counts. No row values. Tested against the OpenLineage 2-0-2 schema in unit tests; not deployed.
- Round n124: a second MCP Apps card, for `review_plan`: its answer drawn as an ER diagram (tables, keys, relationships
  with their rule and counts, failed or stale checks and open items highlighted), with one button per undecided item
  that asks the client to call `review_plan` with that decision. Off unless the operator sets `KRUSGRAPH_MCP_APPS=1`;
  the text answer is the same either way. Unit-tested and checked in Chromium; not deployed.
- Round n123: two server-wide operator settings, both off by default. `KRUSGRAPH_READ_ONLY=1` leaves out every tool
  that creates or changes something in Fabric. `KRUSGRAPH_NO_ROW_VALUES=1` leaves out `sample_rows` and takes row values
  out of the other answers, keeping names and counts. `/healthz` gains a `mode` field, and the server's instructions,
  `/llms.txt` and the Hosting and permissions section of `/docs` name the two settings. With both off the tools are as
  before. Unit-tested on the hosted and the local server; not deployed.
- Round n121: `docs/SEGMENTATION.md`, an internal note with candidate customer segments, where each would run, what
  exists and what is missing. Prices, customers and demand are unknown and the note says so. No change to the service.
- Round n119: the first MCP Apps card: `validate_plan`'s summary as a card in clients that show MCP Apps (counts per kind
  of check, what needs attention, next steps as buttons for read and draft tools only). Off unless the operator sets
  `KRUSGRAPH_MCP_APPS=1`; the text answer and the tool count are the same either way. Unit-tested and checked in
  Chromium; not deployed.
- Round n118: `docs/LANDSCAPE.md`, an internal scan of 33 MCP servers and frameworks near Krusgraph, with licences as
  read from their LICENSE files and five ranked ideas (idea 3 became round n123). No change to the service.
- Round n117: a new page in the docs' Concepts group, Where it runs (`/docs/concepts/where-it-runs`): what can be
  checked, drafted, created and reviewed in the browser, on your own computer, in your own Azure tenant and on the
  hosted service, each cell read from the code. Unit-tested; not deployed.
- Round n113: `docs/COMPARISON-MYRIADE.md`, an internal note on how Myriade infers relationships beside Krusgraph on
  the shop data, from public sources only. No change to the service.
- Round n86b: a Concepts group in `/docs` with pages on how it works, ontologies, data products, how they connect and
  the vision (`/docs/concepts/...`), with examples rendered from the engine on the shop schema, three architecture
  diagrams (layers, sign-in and request flow, plan to Fabric items) and a small explanation that opens next to
  "ontology" and "data products" in the chat demo and on `/check`. Every old docs anchor still leads to the same text.
  Unit-tested; not deployed.

## 0.8.0 — 2026-10-28

- Round n120: `create_pipeline` creates the pipeline of the n110 draft (a new tool; 39). It creates or updates in place
  the silver and gold notebooks the existing tools create, the check notebook, and a data pipeline that runs them in
  that order, each step only after the one before succeeded, so a failed check fails the run. `dry_run=true` (the
  default) makes no write call and returns the definitions and the REST calls; `dry_run=false` sends the same
  definitions with the notebook ids in place of their placeholders. It never runs or schedules the pipeline and says
  so. It uses the notebook and data pipeline create/updateDefinition calls the code already makes and needs
  `Notebook.ReadWrite.All` and `DataPipeline.ReadWrite.All` (or `Item.ReadWrite.All`), which the hosted app has.
  Unit-tested with a test double for Fabric's REST API; not created or run in Fabric, not deployed.
- Round n116: a OneLake catalog draft (`fabric_backend/catalog.py`). `export_item_definitions(items=["catalog"])` lists
  each Fabric item the plan touches with the description and tags it would get, and the exact REST calls for them. The
  items are the source lakehouse or warehouse and the API, model, notebooks and pipelines the creating tools would
  make. The calls are `PATCH /v1/workspaces/{id}/items/{id}` (Update Item, description at most 256 characters) and
  `POST .../items/{id}/applyTags`, which takes tag ids that `GET /v1/tags` finds. Tags that do not exist yet need
  `POST /v1/admin/tags/bulkCreateTags`, which only a Fabric administrator can call. A description holds table and
  entity names, roles, key and relationship rules, validate_plan's counts with `check_rows=true`, and the proposed
  domains. It never holds a column name or a row value. The tags are "Krusgraph" plus one per proposed domain.
  `catalog` alone answers without files; with other items the files stay. Nothing is set on lakehouse tables, T-SQL
  views, the SQL analytics endpoint or endorsement, because no public operation covers them. Sources:
  fabric-rest-api-specs 6f817cb, fabric-docs 28d4ff3 and microsoft/mcp 42c66a2, all read on 6 Nov 2026. No tool sends
  the calls; still 38 tools. Writing would also need `Tag.Read.All`. Unit-tested on the shop; not sent to Fabric.
- Round n115: a fix suggestion for each of validate_plan's findings (`fabric_backend/fixes.py`), as drafts. Each row of
  the evidence report's checklist carries `fix`, and the report has a "Fix suggestions" section. A fix is a mechanical
  step with a stated rule: rows with a NULL key and exact copies go to quarantine, one row per key stays, and an amount
  a flat table repeats on every row of a header value moves to `<table>_per_<header>` in silver. A choice is two such
  steps with none chosen: an orphan row goes to quarantine, or stays with its reference set to NULL. A question is a
  business decision with no default: which of two differing rows with one key wins, whether an orphan's target exists
  elsewhere, which table an amount belongs to. Counts before and after come from the check's own counts and its query.
  `silver.apply_fixes` puts the steps into the silver notebook draft: the decisions are None in its parameters cell,
  and the run stops before writing anything while one the data needs is None. Only the silver tables and
  `krusgraph_quarantine` are written, never a source table, and nothing here runs. n106's flat-table amounts are a
  checklist finding of their own. No tool added (38). Unit-tested on the synthetic shop and flat-table rows, and the
  draft ran on a local PySpark 4.0.1 with the counts it states; not run in Fabric, not deployed.
- Round n114: `dbt_schema` writes a whole dbt project draft with `project=true` (no new tool; still 38). The files are
  dbt_project.yml, the sources file with its tests from the plan's keys and relationships, one staging view per table
  (cast to Fabric Data Warehouse types where the metadata says enough, de-duplicated on the key) and marts in one folder
  per proposed domain. The marts join only over relationships whose target key `check_rows=true` counted unique, and
  child tables are summed to the fact's key before the join, so a header amount is never summed over its lines.
  Written for dbt-fabric 1.12.0 on dbt-core 1.12, T-SQL without CTEs. Untemplated parts (a table without a key, a type
  without an equivalent) and the customer's TODOs (business rules, which duplicate to keep) are listed. It creates and
  runs nothing. `dbt parse` passed on the shop project with dbt-core 1.12.6 and dbt-fabric 1.12.0 on 6 November 2026;
  not run against a Warehouse. Unit-tested; not deployed.
- Round n111: `create_backend` has a dry run, `dry_run` with the default of the other creating tools (`true`), in the
  hosted and the local server. It answers whether an item of that name exists and would be updated or created, the
  definition and what changes in it, and the checks that passed, reading only. A call that should create or update
  now passes `dry_run=false`; what a real create writes is unchanged. `tool_status.NO_DRY_RUN` is empty and the texts
  that said create_backend has no dry run say otherwise. Unit-tested with the Fabric test double; not deployed.
- Round n90: Claude's connectors page moved to Customize. The Connect button opens
  `https://claude.ai/customize/connectors` instead of `https://claude.ai/settings/connectors`, which now only says that
  Connectors moved; the instructions say Customize → Connectors → Add → Add custom connector, and for a new sign-in
  Customize → Connectors → Yours → Reconnect. Tried in Claude on the web on 2 November 2026; instructions for other
  clients unchanged. Unit-tested; not deployed.
- Round n89: `amount_levels` writes a factor only when it is true. The counting query also returns `min_lines`; where
  every referenced header has the same number of lines (`min_lines` = `max_lines` > 1) the sum "comes out n times too
  large", exactly; otherwise no factor, because the average number of lines is not the ratio of the sums (the SAP
  example said "about 1.5 times" beside 1 950 against 750). `/check` shows the ratio from the two counted sums;
  `validate_plan` still sums nothing. Unit-tested on synthetic data; not deployed.
- Round n88: a negation such as "customers who have not placed any orders" or "haven't placed an order" gives an
  anti-join (NOT EXISTS), and a "not", "n't", "never", "inte", "ej" or "aldrig" no marker ties to a table gives no query
  and says so; `amount_levels` says no row is repeated today where every header has one line; lineage's note names
  the live run of 2 November 2026; `/privacy` says that the tools that build on the plan run rule R5's counting queries
  (at most 20 per call, only counts, nothing kept between calls); `docs/LIVE-TEST.md` rows 4, 6 and 25 expect 7
  relationships, with the results of 2 November 2026 after round n87. Unit-tested on synthetic data; not deployed.
- Round n87: the ten findings of the live review of 2 November 2026 (negation, R5 in every plan-based tool, the
  counting query SQL Server refused, per X, value columns, silent replacements, personal data, contradicting notes,
  small errors, the operation result in lineage). Unit-tested on synthetic data and fake answers.
- Round n85: the evidence report downloaded on `/check` carries the decisions taken on the page (the guided demo's
  Accept and Reject): what, the decision, the browser's time and "by: not recorded", the latest choice when it changes,
  as of each download. They stay in the browser (nothing is sent or saved) and a new run starts without them. An
  accepted relationship is "accepted, not checked in the rows": it is not added to the relationships or the checks.
  Without a decision the report is the same as before. The four example buttons' descriptions fit on two lines at
  375 px, 1000 px (where the four sit in one row) and 1280 px; "Subscription billing" reads "Younium + Salesforce
  invoices". Browser tests in `tests/test_check_decisions.py`. `docs/LIVE-TEST.md` records the run of 2 November 2026
  (build `src-69aa8afa445e6c97`): `validate_plan`, `lineage`, and `create_ontology` creating and updating
  `shop_ontology_n81`, round n81's path against real Fabric without throttling; `Retry-After` and 429 tried only
  against fake answers.
- Round n84 (Deployment): the Dependabot PRs of November merged one at a time on green CI, `main` checked after each:
  actions/checkout v5 → v7 (its breaking change, no checkout of a fork's PR under `pull_request_target` or
  `workflow_run`, does not apply to these workflows), and opentelemetry-api 1.45.2, pydantic 2.14.2 and pydantic-core
  2.50.2 in `deploy/constraints.txt` (the image), with `THIRD_PARTY_NOTICES.md` regenerated (#16; #15, the same three
  pins from the `/deploy` entry of `dependabot.yml`, closed as a duplicate). A new CI job, `notices`,
  runs `tools/third_party_notices.py --check --from-installed`: a stale `THIRD_PARTY_NOTICES.md` or an AGPL/SSPL
  dependency, now in the extras too, stops the build; `--from-installed` names a package's home page the way PyPI does,
  so both modes write the same file.
- Round n83: a 60-second overlap window on the refresh-token rotation at `/mcp/connect` (`Layer._refresh`, the
  proposal of `docs/REFRESH-ROTATION.md`): the refresh token just replaced, from the same client id, gets the same
  answer again (no Entra call, no new rotation, `refresh_replayed` in the log), so a client's retry after a lost answer
  no longer signs the user out; after the window, reuse ends the line as before. An ETag conflict, and a final Entra
  refusal on a line another request has just renewed, answer with that request's answer instead of signing out or
  deleting the line. The answer is kept encrypted in the line (with the server's key and a key derived from the
  replaced token) and never opened after the window. The consequence, said in /privacy, `docs/CLIENT-REGISTRATION.md`,
  `docs/TRUST.md`, `docs/RISK-REGISTER.md` (R9) and `docs/REFRESH-ROTATION.md`: a stolen old refresh token used within
  60 seconds is not detected, and an encrypted access token now sits in the row after every refresh. Claude's path
  through `/mcp` is unchanged. Tested against a mocked Entra and store only; not deployed.
- Round n82: by Gustav's decision of 2 November 2026 VS Code and Cursor (verified by him) and Lovable (its flow ran live
  on 30 October 2026, `docs/LOVABLE-END-TO-END.md`) are **Tested end to end** in `tool_status.CLIENTS`, with the date in
  their notes; the Connect menu, the hub, /docs, /start, /lovable and the llms files follow, and "Experimental:" is gone
  from the three menu items. Claude Code and Glama are unchanged. Gustav opened an RDF/XML file from `/check` in
  Microsoft's Ontology Playground the same day, with a good result (`docs/LIVE-TEST.md`; one sentence at the download);
  the file stays Draft. `docs/REFRESH-ROTATION.md` with `tests/test_refresh_rotation.py`: an investigation of Glama's
  sign-out (a refresh token sent twice ends the whole line; what a deployment does to the lines and the key; the causes
  ranked; an overlap window proposed, not implemented). `tests/test_pack_label.py` freezes the evidence report's clock.
- Round n80: a simpler Connect menu (Claude first and open with one large button, Copy URL and a first question to copy
  that only reads; Lovable under it; VS Code and Cursor folded under *Other clients*; the admin line last with a note to
  copy for the admin: the consent link, what is approved, `/it`). No address is printed; each copy button holds its
  client's. `/consent/done` gives one next step, Connect and the question. At `/mcp/connect`, a sign-in Entra stops for
  want of admin consent shows a page that says so, with the same note, instead of an unexplained error in the client.
  Gustav verified on 2 November 2026 that the *Add to VS Code* and *Add to Cursor* buttons work in their clients
  (`tool_status.CLIENTS`, `docs/LIVE-TEST.md`). `/check` says "app starter for Lovable" without the word Supabase (the
  zip is unchanged). `ontology.ontology_rdfxml`: the plan as RDF/XML for Microsoft's Ontology Playground, which reads
  RDF/XML and not Turtle, written after its RDF/XML subset at commit 7bf7acb (MIT), with its validation rules ported to
  `tests/playground_rdf.py` and one official catalogue file as a fixture; a Draft download on `/check`, opened in the
  Playground with a file import; no new MCP tool. Not tried in the Playground app itself.
- Round n79: the pack's own name where a person reads the rule (Subscription billing on `/check`, the data dictionary,
  the Power BI README, the contracts, the Rayfin comments say *Younium + Salesforce pack*; the `rule` fields of the
  answers keep `SAP pack`, and the SAP texts are unchanged). Masking goes through the pack the engine reads, so the
  Younium + Salesforce pack's personal columns (Contact's and the accounts' names, e-mail and telephone numbers) are
  masked like SAP's; the account names were added to the pack. The evidence report
  (`fabric_backend/evidence_report.py`), a pilot's hand-over as JSON and Markdown from the plan and validate_plan's
  counts, with "not checked" for whatever was not counted and no row values: a Draft download on `/check` and
  `evidence-report.md`/`.json` from `fabric-backend demo`; no new MCP tool.
- Round n78: the engine reads the Younium + Salesforce pack. `infer._pack` calls `sap_pack.match_any`, so a schema the
  pack recognises gets its keys and applied relationships with the rule `SAP pack` (one rule for every pack) and the
  pack's name and source on each note, and `plan.pack` carries its tables, amounts and traps. The pack's ordinary table
  names (accounts, invoices, Contact and the like) are marked `common_name`, and a pack is taken only when one table it
  recognises has a name of the system's own, so the shop, SAP, crm and traps plans are the ones before (tested against
  the SAP-only engine). The benchmark's younium row: recall from 0/18 to 15/18 at precision 15/15, orphans 1/1 and
  doubled totals 2/2; the other rows unchanged. `/check` has a fourth example, *Subscription billing* (Younium +
  Salesforce, synthetic data). The pack is still written from sources that could not be opened, and the demo rows from
  the pack.
- Round n77: one manifest per knowledge pack, `fabric_backend/packs/<pack>/manifest.yaml` (`sap`, `younium_salesforce`), in one
  shape for every pack and checked by `packs/manifest.schema.json`: id, version, title, source systems, scope, sharing
  (public-synthetic), sources with `accessed` and `verified` (false wherever the pack's files say the page was not read),
  entities with their key candidates and sources, candidate relationships with the rule, the sources and which of
  `validate_plan`'s checks can confirm them (referential integrity, cardinality, amount level), traps with the check that
  shows them, the fixture module and the benchmark facit, and `review_status` with `reviewed_by`/`reviewed_at` empty until
  the maintainer has reviewed it. The loader `fabric_backend/pack_manifest.py` derives the four claim sections from the
  module files and `tests/test_pack_manifest.py` checks that every rule in the files has a row in the manifest and the
  other way round, that the fixtures build and the pack recognises every fixture table, and that the facit of
  `examples/benchmark` and the manifest's candidate relationships agree (the three links by number of the younium set
  are candidates listed as not applied). `sap_pack_draft` answers with a `pack_manifest` field (id, version, review
  status), read without a YAML library; nothing else in a tool's answer changes. `docs/PACKS.md` describes the format,
  how a pack is added (public sources, synthetic fixtures, never customer data), the review step, and what a pack is
  beside a connector and a finished analysis. The benchmark table is unchanged.
- Round n75: the sales path's last P1 items and the coverage lines. The home page offers two paths after the demo card:
  "Try it yourself" (`/check` and the Connect chooser) and "Get help with one number" (`/partners`), one sentence each and
  no new promise. `/partners` separates the first assessment (you describe one question, one data area and what the
  number is compared with; the answer is one of five words: ready to start, a business question must be decided, material
  missing, access missing, not supported) from the pilot ("Bring one number your team cannot agree on": the plan, the
  checks, the explanation of the number, a reviewed model, the contract and the hand-over; accepted when the number is
  explained with evidence, every relationship has a rule or a decision and the model opens in Power BI Desktop and
  refreshes in Fabric; the customer's part is one data owner with read access; "Quoted after a 30-minute scoping call;
  invoiced.", no amounts), and shows an illustrative delivery on synthetic data whose figures are the engine's own run
  of `seed.AMOUNT_DEMO` (`amounts.demo`), not typed into the page; `/pricing` carries the same price sentence. Coverage:
  every finding card on `/check` says how much of the rows its check read, from the result itself ("Checked on all 60
  rows of orders: 60 with a value", "Counted on all rows of products and order_items: …", "Not counted: a list of columns
  has no rows"), a line under the state says whether every key and relationship of the plan was counted, and the docs'
  `plan_backend` and `validate_plan` sentences carry R5's sample and query budget and `validate_plan`'s default
  `max_items` read from `server.py`. The Fabric IQ FAQ n73 put on `/docs` was checked and left as it is.
- Round n76: trust, risk and licences, as documents. `docs/RISK-REGISTER.md` (internal): eight risk hypotheses with
  cause, event, consequence, area, the existing controls with their file or function in the repository, action, owner
  and next review; probability and impact "not assessed" wherever the repository holds nothing to carry a value; product
  risks apart from business obstacles. `docs/TRUST.md`: the material for a public /trust page, every statement with its
  source in the repository and Microsoft's attestations marked as Microsoft's; the line "Krusgraph is not ISO 27001 or
  SOC 2 certified; here is what we do instead"; the subprocessor list (Microsoft Azure; the AI client is the customer's
  own vendor). `docs/ISO27001-SELF-ASSESSMENT.md`: the 93 Annex A controls, each in place, partly, missing or not
  applicable with its file, and no score. `docs/DPA-DRAFT.md`: a data processing agreement template as a draft, not legal
  advice. `THIRD_PARTY_NOTICES.md` generated from `deploy/constraints.txt` and the extras by `tools/third_party_notices.py`
  (`--check` for CI; the workflow step is left for the Deployment area), with the vendored Pyodide and fonts and the
  image's components; a "Reusing external code" section in `CONTRIBUTING.md` (verified licence file at a pinned commit,
  notices kept, no AGPL or SSPL, nothing from a repository whose licence cannot be verified). `docs/ECOSYSTEM-WATCHLIST.md`:
  the related MCP servers (Microsoft's Fabric MCP Server, Fabric IQ MCP, the Power BI modeling server, the warehouse
  and Real-Time Intelligence servers; datumnova/ms-fabric-mcp and Jasuni69/ms-core-mcp with no licence file found,
  mkoziel2000/mcp-fabric-api under the AGPL) with licence as observed or not verified, what is worth referring to, what
  is not copied, and the date. `docs/COMPANION-MCP.md`: Krusgraph beside Microsoft's servers in the same client, a
  complement with no server-to-server connection, cited from fabric-docs because Learn could not be opened.
- Round n73: the polish from the external review, on the site. `/check` shows the finding first: after a run the state
  line ("Enough to start · 4 things to check"), the most important finding and the folded list come right under the
  status line and before the map, and the engine's steps are a closed `<details>` under the map ("How the engine got
  here"), in the three examples and for the visitor's own files; a browser test reads the finding at 1280 px without
  scrolling. One order runs through "A total that doubles": the engine reads one header row per amount finding from the
  rows (its key, its amount, how many line rows point at it, what a join counts it as: `order_id 1`, 1 000, twice,
  2 000) and the finding's text, Onto's "Why does this total come out twice?", the Power BI preview and the domain's
  ODCS contract (a top-level `customProperties` entry, `amountLevel.<table>.<column>`) all repeat that row; the preview no
  longer shows a second total of its own. Every download button on `/check` says what the file holds and its status
  word from `tool_status` (the Power BI project, the app starter, the contract). `/lovable` is rewritten after the path
  that ran on 30 October 2026: Krusgraph as a custom MCP connector in Lovable at `/mcp/connect` (plan, check, create),
  the three portal steps (an app registration with a secret, Contributor on the workspace, introspection on the item:
  the one with no API), then Lovable's Microsoft Fabric connector; its status words come from Lovable's two rows in
  `tool_status.CLIENTS`. "Connect to Claude" is "Connect" everywhere (the footer, the session links, the closing card,
  `/check`'s answer, `/use-cases`, the consent pages), pointing at the n68 chooser (`/#connect`, which opens it and
  focuses its button); `/start` is "the set-up guide". Docs: the admin consent link on `/docs` carries
  `redirect_uri=https://krusgraph.com/consent/done` like `/start`, and the Fabric IQ section answers "Why not just Fabric
  IQ / the Fabric ontology?" with what Microsoft Learn says about filling an ontology item (by hand, from a semantic
  model, with the ontology agent; links to Learn) and the one angle of `docs/FAQ-COMPETITION.md`: Krusgraph creates the
  ontology item; the evidence step comes before it. `domains.draft` and `domains.contract` take an optional `extra`
  (more top-level custom properties) for `/check`. `docs/SCOPES.md` was not touched: Docs and submission is n72's.
- Round n72: a second knowledge pack, `younium_salesforce` (`fabric_backend/packs/younium_salesforce/`, modules `younium` and
  `salesforce`): Younium's API v2 objects (accounts, products with charge plans and charges, subscriptions with versions
  and charges, sales orders, invoices with lines, payments) beside the Salesforce standard objects the Younium connector
  meets (Account, Contact, Opportunity, OpportunityLineItem, Product2, PricebookEntry, Order, OrderItem, Contract), 20
  tables, 33 relationships (the Younium account to its Salesforce Account through External CRM Id; the links an invoice
  line carries by number are listed, not applied) and 13 traps (versions, amounts on lines, MRR/ARR as measures, one
  currency per account, usage charges, 15- against 18-character Salesforce ids, one customer as two account rows).
  Every source is marked unverified with the date: developer.younium.com, support.younium.com and
  developer.salesforce.com could not be opened from the session that wrote it (`docs/YOUNIUM-SALESFORCE.md` has the
  list and the questions for someone who runs the integration). The loader reads a system prefix (`younium_`, `sf_`,
  `salesforce_`, `crm_`) past like `sap_`, compares columns without case or underscores (`externalCrmId` and
  `external_crm_id` alike), and gains `match_any` (the pack that recognises most of a schema) and `plan_with` (a plan with
  a pack's keys and relationships as the caller's); the engine still calls `match` for the SAP pack alone, so the new
  pack is not applied by `plan_backend` or `/check` yet. The pack schema gets an optional `area` per table, which the
  domain proposal uses for a domain's name (billing, customers and sales), an optional Swedish name, and the level
  `version`. A synthetic demo, `fabric_backend/younium_demo.py` (14 tables, 58 rows, no real party), with a planted
  15-character id and an invoice total over three lines; the benchmark gains it as a fifth set, the four rows from
  before unchanged.
- Round n71: the amount that is not there. A line table with a quantity (`order_items.quantity`) and no amount of its own,
  pointing at a table that carries the price (`products.list_price`), gets the measure `Order amount` =
  `SUMX('order_items', 'order_items'[quantity] * RELATED('products'[list_price]))` in `semantic_model_draft` and
  `create_semantic_model`, with a note on where the price comes from (a list price as it stands at query time, not
  necessarily the price paid); the price column is not summed on its own (`summarizeBy: none`), and `data_dictionary`
  and the ODCS contracts name the measure (`customProperties`). Names: quantity/qty/menge/antal and
  price/list_price/unit_price/netpr (`fabric_backend/amounts.py`). A line that carries an amount (`net_amount`, SAP's
  `VBAP.NETWR`) keeps it and gets no product; a price per unit no longer counts as a measure when a table's role is
  decided, so a products table with a list price stays a dimension. The synthetic shop's products have a `list_price`
  (the live shop's model had shown only a total quantity). The hosted `plan_backend` runs rule R5 over its open
  connection, bounded: the first 200 distinct values of a candidate column, one counting query per candidate target,
  at most 20 per call (on 30 October 2026 it had not found `orders.ship_to_id → addresses`, because R5 needed rows only
  `validate_plan` read); the answer gains `counted_in_rows` and, for candidates it could not confirm or count,
  `proposed` with the reason and the next step. Name, title and annotations of the tool are unchanged; the other tools
  plan by names as before. The benchmark table is unchanged.
- Round n69: the status words after the live runs of 30 October 2026, text only (no tool's name, title, annotations
  or behaviour changed). `create_report` is "Experimental; created live on 30 October 2026 (shop_report_live,
  shop_report), opened and reviewed in the Fabric portal by Gustav the same day" and, next to the offer, "created live;
  reviewed in Fabric" (`LATER_LIVE`, `REVIEWED`). `create_backend`'s long form adds that `shop_api` was updated in
  place again from Lovable and is consumed live by a Lovable app on 30 October 2026; `create_semantic_model`'s that
  `shop_model` was updated in place from Lovable the same day. Lovable has a second row in `tool_status.CLIENTS`: via
  MCP (/mcp/connect), Experimental, signed in with Entra through Krusgraph's OAuth (dynamic client registration) and ran
  plan, check and creates on 30 October 2026; the /mcp/connect sentence names it with its date. The server's test
  status sentence names the tools that have created items live since the run of 27 October instead of saying creating is
  unit-tested only, and `semantic_model_draft`'s note no longer says the item is not yet created live. Docs: a 30 October
  section in docs/LIVE-TEST.md (and a `create_report` row and a Lovable client row), `create_report` in docs/SCOPES.md,
  the README's tool list and status, deploy/SUBMISSION.md row 5, and step 1 of docs/LOVABLE-END-TO-END.md no longer
  blocks. The Fabric REST API was not called in this round.
- Round n67: the TMDL writer never writes a document that holds only comments. On 30 October 2026 Power BI
  Desktop 2.151 opened the shop project from /check but refused the SAP one with "InvalidLineType ... Document:
  ./relationships, line 1": with no expressible relationship, `relationships.tmdl` had been one comment line. The file
  is now left out when there is nothing to put in it, the rule (`has_object`) is applied to every part of the draft, and
  `README.generated.md` says why. Composite keys (SAP's MANDT+VBELN) are listed in the summary as `not_expressible`
  with the reason: one column per side, no calculated columns in Direct Lake, so the lakehouse needs a combined key
  column (a gold view, `create_gold_views`) before the relationship can exist; the old "or a calculated column" advice
  is gone. The zip's README and the model's README say to extract the whole zip before opening the `.pbip` (opening it
  from inside the zip gives "definition.pbism is missing"). Tests: a TMDL document check over every generated document
  for the shop, the SAP demo and Salesforce + ERP, and the zip from /check holds `.pbip`, `definition.pbism`, both
  `.platform` files and the report folder for all three. The Fabric REST API was not called in this round; the SAP
  draft after the change has not been opened in Power BI Desktop yet.
- Round n66: three contradictions in the trust texts, found by an external review of the live site on 30 October
  2026, text only. "Your data stays in your tenant" (home, /it, /pricing) is replaced by the same sentence on all
  three pages: Krusgraph stores no table contents; names, counts and requested sample rows pass through in memory and
  reach the AI client; EU hosting, or your own Azure to keep everything in your tenant ("stays in your tenant" is
  now a banned phrase in tests). /it and /docs say about tokens exactly what /privacy says: Claude's in memory only;
  other MCP clients' sign-ins encrypted in Table Storage for the times /privacy gives, linked. The dry-run sentence
  on /terms, home, /it and /docs renders from `tool_status.NO_DRY_RUN` (create_backend has none), and a test holds it
  to the signatures in server.py. `build_word` and `short` count a tool created live after the run (`LATER_LIVE`)
  as created, so the hub and the docs no longer say "draft" beside "created live" for the ontology and the
  silver notebooks; the docs' hand-written statuses render from tool_status. The Power BI project from /check was
  opened in Power BI Desktop on 30 October 2026, and /check and its README say so. Anchor links in the docs
  Markdown render as links.
- Round n65: `deploy/krusgraph.sh --doctor` prints one table of the service's state (server and build, the
  certificate's expiry, the Entra client secret's expiry as dates only, replicas, domain binding, Log Analytics,
  budget), reads only; `--budget` creates a cost budget on the resource group with e-mail from two new keys,
  `budget_amount` and `budget_email` (empty = nothing); `--backup` exports the registration table's consent records
  to a git-ignored file, with the restore in `docs/OPERATIONS.md` section 8, and section 9 is the continuity
  checklist. Unit-tested against a faked `az`, not run against Azure. `docs/NORDIC-PACK-SPIKE.md` writes down the
  spike of 30 October 2026 on a Nordic ERP pack (Business Central first).
- Round n60: `SECURITY.md` at the repository root (report to gustav@krusgraph.com, as in security.txt; only the latest
  version supported; no customer data stored; no fixed response time, no certification). Dependabot for pip and
  GitHub Actions. `.github/workflows/sbom.yml` builds a CycloneDX SBOM of `deploy/constraints.txt` on every push to
  `main` and on a tag `vX.Y.Z`, kept as an artifact; on a tag it checks the version against `pyproject.toml` and puts
  the CHANGELOG section in the run summary. How to tag: `docs/OPERATIONS.md` section 7. No tag created yet.
- The start page's row under the hero is a hub (the brief of 27 October 2026): "Your data in Fabric" (Lakehouse,
  Warehouse, SQL database) and "What Krusgraph builds in Fabric" (GraphQL API, Power BI semantic model, Fabric IQ
  ontology, views, data agent, silver notebooks) on the left, Krusgraph in the middle ("one plan, the rule behind every
  relationship"), "Where you build" on the right, joined by lines as in the graph and stacked with Krusgraph in the
  middle on a phone. Every status comes from `tool_status.py` (`SOURCES`, `BUILDS`, `build_word()`): "creates" only for
  what has been created live on the hosted service (the GraphQL API), "draft" for the rest; the warehouse and the SQL
  database are marked experimental. Text names only, a text version for screen readers, and the "Independent
  product…" line, which names Anysphere when Cursor is shown. Checked in a browser at 375, 768, 1280 and 1440 px.
- Client registration is on at krusgraph.com since 27 October 2026, and the maintainer's live test that day signed in
  from Glama (client ID metadata document), VS Code and Cursor at `/mcp/connect`. With client registration on, the
  site names them: the hub lists Claude, VS Code and Cursor via MCP (`tool_status.CLIENTS_TESTED`,
  `clients_working()`), `/start`, `/docs` (a new section, *Other MCP clients*) and `llms.txt` send them to
  `/mcp/connect` with the date of the test, and the home page says Krusgraph connects Claude, VS Code and Cursor. With
  it off, the pages say what they said before. The run's findings are in `docs/CLIENT-REGISTRATION.md` and
  `docs/LIVE-TEST.md`; the README, `docs/OPERATIONS.md` and `docs/SECURITY.md` follow.

- Round n17: the guided demo ("Where should each order be delivered?") moved from the start page to a page of its own,
  `/demo`, unchanged in what it does: the four steps, the graph with its mascots, the details, the relationship list
  and the "Demo · synthetic data" pill, with its own title, description, canonical link and sitemap row, and links on to
  `/explore` and `/start`. The start page keeps a short way in (the heading, one sentence, "Try the guided demo"), and
  the hero's button goes to `/demo`; at 1280 px the start page is 3,132 px tall instead of 4,582. Old links into the
  demo on the start page (`/#guide`, `/#demo`, a step's or the graph's id) go on to the same anchor on `/demo`. The
  step headings are `h2` now, under the page's `h1`. `/demo` is not in the menu: it made the open menu at 375 px longer
  and wrapped the header at 768 px; the footer, `/docs`, `llms.txt` and the README link it.
- Under the start page's hero, a row of what Krusgraph connects: Microsoft Fabric (your tables), Power BI (model drafts)
  and Fabric IQ (ontology drafts) on one side, Claude (MCP) and Lovable (via the GraphQL API) on the other, as text
  names on tiles joined by a line, with no third-party logos or icons, a text version for screen readers and the line
  "Independent product. Not affiliated with or endorsed by Microsoft, Anthropic or Lovable." Claude is the only client
  named: the one MCP client tested against the hosted service; Lovable uses the API Krusgraph creates, not Krusgraph.

- Round n16: sign-in for MCP clients other than Claude, behind `KRUSGRAPH_CLIENT_REGISTRATION` (off by default;
  `docs/CLIENT-REGISTRATION.md`, turning it on in `docs/OPERATIONS.md` section 6). The clients use
  `https://<domain>/mcp/connect`, whose metadata names Krusgraph's own authorization server at `/oauth` in front of the
  one Entra app: Client ID Metadata Documents (VS Code, Claude Code, ChatGPT), strict dynamic registration with its own
  flag (Cursor, Glama), redirect addresses https or loopback only, Krusgraph's consent page per client before Entra
  (remembered per user and client for https addresses, shown every time for a program on the user's computer), no
  redirect to a client before it is approved, PKCE S256, single-use state and codes, rotating refresh tokens of its
  own, `iss` in every answer, and the same token validation as `/mcp`. An independent security review found eight
  problems before release, all fixed with tests (the list is in `docs/CLIENT-REGISTRATION.md`). Records in Azure Table Storage (`registration_store.py`).
  Claude's `/mcp`, its metadata and its 401 are the same in both modes (tests lock them). `/privacy` describes the
  records when the flag is on. `deploy/krusgraph.sh --client-registration` prints the commands (one web redirect
  address on the Entra app, the table, the key, the settings) and runs nothing. The earlier facade (`KRUSGRAPH_DCR`,
  `fabric_backend/dcr.py`, `docs/AUTH-DCR.md`) is removed: it handed out the Entra app's client id without a consent of
  its own and changed Claude's metadata when switched on. Unit-tested against a mocked Entra; not deployed.

## 0.7.0 — 2026-10-27

- Home page, round 1 of the brief of 27 October 2026: a shorter lede and a guided example in four steps that follows
  one order to its delivery address. The suggestion for `orders.ship_to_id` is now the engine's own
  (`suggest_relationships` on the synthetic sample, `demo.demo_suggestions()`), with its data check (all 60 orders have
  a `ship_to_id` in addresses, 15 different addresses) and the next candidate that does not hold (customers, 35 of 60).
  The visitor's review is a separate step from the check: accepting decides what the column means in the demo only,
  never "checked", and the graph below follows the same decision. The last step is a result card (what was reviewed,
  what the data shows, the decision, what is still open, next tools with their status) with a summary to copy. Every
  step is in the HTML, so the page reads without JavaScript. The headline and the mascots are unchanged.
- Finding 8 of 27 October 2026: the Glama catalog lists Krusgraph and asks the owner to confirm it with a file.
  `GET /.well-known/glama.json` serves the maintainer's claim (`$schema` and `claim`, a token made to be public) as
  `application/json`, without sign-in and outside the 401 in front of `/mcp`, only when the public host from
  `MCP_PUBLIC_URL` is krusgraph.com; any other host, or none, gets a 404, so a self-hosted copy claims nothing.
- Finding 7 of the live test of 27 October 2026, after a live `create_backend` the maintainer approved: an update of
  `shop_api` with the ship-to relationship confirmed stopped with `would_remove`, because the plan named the reverse
  field `orders_as_ship_to` where the API has `orders`, and `keep_with_confirmed` was empty. `create_backend` and
  `plan_drift` now keep an existing API's field names for the same relationship (the same columns in the same
  direction) unless `confirmed` names them otherwise (`names_kept_from_api` says which), and every `keep_with_confirmed`
  entry carries `field_name` and `reverse_name`. `/docs` and the README document both names in `confirmed`.
  `create_backend` is **Tested end to end (27 October 2026: update in place of shop_api with confirmed)**; creating a
  new API has not run live, and the pages that offer it say both (`tool_status.create_api_status()`).
- Round n15, the live test of 27 October 2026 (Claude through the hosted build `src-df29c45febaec4b0`, main 5adace8,
  against demo / demo_lh / shop; 30 tools read-only, as drafts or as dry runs, no creating call). Status words from
  `tool_status.py`: the tools that ran are **Tested end to end**, the drafts **Tested end to end (a draft; creates
  nothing)**, `create_views`, `create_semantic_model` and `create_data_agent` *tested end to end as a dry run* with
  creating as before; `create_backend` stays Experimental. The notes in the tools' answers now come from
  `tool_status.answer_note()`, so they follow the status instead of saying "not yet run against a live workspace";
  the docs' test status, `llms.txt`, the use cases, the home page's test line and the server's instructions render
  from the same fields. Fixes for what the run found, each reproduced in a test first: `lineage` reads a definition
  once more when Fabric's first answer could change and keeps Fabric's message in a skipped item (`error`, `reason`,
  `hint`); `create_data_agent`'s instructions and examples follow the privacy rules (the key in place of
  `customers.name`; `show_personal_data`); `data_dictionary` with `tables` takes roles and subject areas from the whole
  plan; the drift monitor's notebook installs the tag of the server's version (`v0.6.0`) by default, `main` only when
  asked (the tag is made with each release, docs/PUBLISHING.md).
- Round n13, the Databricks adapter (Draft only: unit-tested with Databricks mocked at its REST API, not yet run against
  a workspace; local stdio server only, `KRUSGRAPH_PLATFORM=databricks`; docs/DATABRICKS.md). Reads a Unity Catalog
  schema through `information_schema`: informational PRIMARY KEY / FOREIGN KEY constraints become K0 / R0 as on a Fabric
  warehouse, column tags feed the personal-data rules (`class.email_address` → P2; a bare `pii` tag → `tag`). Runs the
  checks in Databricks SQL on a SQL warehouse through the Statement Execution API, signed in with Databricks' own
  unified authentication (`databricks-sdk`, `pip install "fabric-backend[databricks]"`). Seven new local tools:
  `databricks_constraints_draft` and `create_databricks_constraints` (RELY only where validate_plan's counts hold; only
  ADD, never DROP; dry run by default), `databricks_pipeline_draft` and `create_databricks_pipeline` (a Lakeflow
  pipeline with the silver and gold rules of the Fabric notebooks as expectations and a quarantine; creates or updates
  the pipeline in place, starts nothing; dry run by default), `databricks_metric_view_draft`, `export_databricks_bundle`
  and `databricks_lineage` (system.access.table_lineage). `create_views` writes Databricks views there. The tools that
  build Fabric items answer `unsupported` on Databricks with the tool that does. The pipeline's SQL ran on SQLite in the
  tests with the same quarantine, per table and rule, as the Fabric silver notebook. One line about it in the hosted
  server's instructions and a section on /docs; nothing else on the site changes before a live run.
- CI runs Python 3.12, which keeps docstring indentation; the golden tool listings compare descriptions after
  `inspect.cleandoc`, so they hold on 3.12 and 3.13 alike.
- Round n13, platform adapters (no answer changed). The engine (inference, validation as counting queries, join paths,
  the graph, drift, dictionary, dbt, the silver logic) is separated from what is platform-specific: reading a source's
  schema, running SQL and building objects now sit behind `fabric_backend/platforms/` (`base.py` the interface,
  `fabric.py` the first adapter, moved out of `server.py`; `local.py` the ODBC string, SQLite, file and columns-list
  sources of the stdio server and the demo, moved out of `mcp_server.py` and `demo_app.py`). The counting, sample and join
  SQL is written through `dialects.py` in the dialect of the connection (T-SQL by default). `docs/ARCHITECTURE.md` says
  what a new adapter implements; `tests/test_architecture.py` checks that the engine imports no I/O library and no
  adapter. `tests/golden/` holds every answer of the engine, of all hosted and local tools, the listings, the
  instructions, the demo and the CLI, committed before the move and unchanged by it.
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
- /use-cases no longer calls the GraphQL API and the SQL views "tested end to end": creating the API is Experimental
  (`create_backend` has not been run live; querying an existing API with `describe_backend` and `query_graphql` is tested
  end to end) and the views were tested as a dry run only. The README's note of 25 October and docs/LOVABLE-END-TO-END.md
  said the same of `create_backend`; a test now scans the site, its Markdown and llms texts, the README, docs/ and the
  server instructions for either claim.
- Fixes from an independent review of round n12's code, each with a test: a question grouped by a personal column of a
  table without a key no longer groups by it (one total, and the reason); a mixed-case `gold_schema` is one lower-case
  name for the notebook's guard and its CREATE statements, and the notebook's SQL is a plain string with backslashes and
  triple quotes escaped; the calendar never adds a second active path (a line table whose header already relates to it
  stays inactive); the privacy rules read numbered and qualified names (`phone_no`, `email1`, `address2`, `birth_dt`) and a
  person named in another table (`orders.customer_name`); a suggested measure is matched by its column, so `Amount (EUR)`
  is not re-suggested; `--client-redirects` changes nothing when the app's list cannot be read; `export_item_definitions`
  keeps the gold views to the exported `tables` and refuses two items in one folder; gold views name a personal key they
  keep for a join.
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
