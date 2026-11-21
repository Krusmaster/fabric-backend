# The next rounds after SM1 (20 November 2026)

Each round is one PR. Each has a "done" line that a test or `tools/smooth_measure.py` can measure, and a list of what it
removes or hides. Every round keeps `tests/test_wb15_click_through.py` green. When a round changes the path on purpose,
it changes that test in the same PR (CONTRIBUTING.md, "The guided path is clicked through"). Every UI round follows
`PRINCIPLES.md`.

Baseline, measured by SM1 (AUDIT.md):
- **Chat:** 10 taps and 4.2 s (local) from Start to the three dry runs. 6 of those taps answer nothing. The dry-run step
  shows 151-193 words and scrolls at 390 px.
- **Editor:** 9 clicks to a dry run of pipeline + model + agent.
- **Tools:** 48 listed.

| Order | Round | What | Done when | Delete or hide |
|---|---|---|---|---|
| 1 | **SM2 Five steps** | The start card becomes 5 steps: **Your data** · **Check** · **Decide** · **Dry run** · **Create**. Steps 1-3 collapse into one line when each has one usable option ("demo › demo_lh › dbo ✓", with Change on tap). The map, the row check and the doubled totals run on their own and become one line each ("17 tables, 24 links, 1 needs you"; the map on tap). One **Dry run everything** button. The sample gets the same dry-run buttons. Create is followed by a closing step (Open in Fabric · Add a source · Schedule) | `smooth_measure`, lazy path: Start → all three dry runs in **≤ 4 taps** and **≤ 3 s** locally (from 10 taps / 4.2 s). Every step **≤ 25 words** besides buttons. **2-3 buttons** plus Next. **No step scrolls** at 390 x 800, the dry run included. The sample reaches the dry run in ≤ 3 taps. Click-through updated and green, light and dark | The "Mascots: on" toggle (into Details); the shop-sample button on step 1 when the user has data (into Details); the separate Check and Find doubled totals buttons; three dry-run buttons → one; "Step N of 9" → "Step N of 5" |
| 2 | **SM3 The same path in the editor** | The editor uses the same five steps and words (shared `stepWords`). The default build is **pipeline + semantic model + data agent** in both surfaces. The check runs on its own after Find keys. "Accept all that passed" is the only accept-all. Drift monitor and app readiness get Dry run/Create or are hidden | The editor's e2e: open → dry run of pipeline + model + agent in **≤ 4 clicks** (from 9), at 390 px and desktop. The Choose screen shows the 3 defaults and folds the other 6 under "More outputs". The chat and the editor name the same default outputs (one test reads both) | API for GraphQL preticked; "Accept all (n)" next to "Accept all that passed"; "Copy the request for Claude" cards |
| 3 | **SM4 Fewer doors** | A default listing of about 15 tools (start, plan_backend, validate_plan, review_plan, the 6 create tools, publish_catalog, requirements_draft, verify_build, lineage, query_graphql). The rest sit behind `KRUSGRAPH_ADVANCED_TOOLS=1` and still work. The `*_draft` tools become hidden aliases of their create tool's dry run. Every non-start card hands back to the living start card at the right step | Listing test: **≤ 16 tools** by default, 48 with the switch; the golden listings regenerated on purpose. A test walks every card's last state: **0 dead ends** (each has a forward button). The read-only listing cap goes down, not up | list_workspaces/list_sources/list_tables, analyze_schema, suggest_relationships, join_path, the six `*_draft` duplicates, create_silver_notebook/create_gold_views/create_views from the default listing |
| 4 | **SM5 Multi-lakehouse fixture + suggestion** | A synthetic, local fixture (below), 5 lakehouses in one fake workspace. Start's "Your data" suggests the source by name rules (G1). The plan works over several schemas of one item (G4) | `tests/test_sm5_multi_lakehouse.py`: layouts (a), (b) and (c) **plan** on the fixture. In (a) the suggestion is `bronze_lh` with **0 extra taps**. In (c) a plan over `sap` + `crm` in one lakehouse lists tables as `schema.table`, and the join check counts across the two schemas in one connection. The click-through still needs ≤ 4 taps on the one-lakehouse demo | "Choose a source first." with nothing suggested |
| 5 | **SM6 Write to the right lakehouse** | `target_lakehouse` and `gold_lakehouse` for a lakehouse source (G2). Model, ontology and agent read where the build wrote (G3). The dry run says it in one line ("silver → silver_lh, gold → gold_lh") | **Multi-lakehouse (a) passes the end-to-end test**: the dry run on the fixture names `silver_lh` and `gold_lh`, the notebooks read bronze through its OneLake path, and the model's expression points at `gold_lh`. ≤ 4 taps with the suggestion taken | |
| 6 | **SM7 Combine sources** | COMBINE-SOURCES.md: schema shortcuts in the dry run (G5); match rules M0-M3 with counts; the person's decisions in the flow state; conformed gold (xref, dims, re-keyed facts); one model, ontology and agent over it | **Multi-lakehouse (b) passes the end-to-end test** on the fixture: SAP + CRM → 1 `dim_customer`, the card shows the match counts in ≤ 25 words, and the model dry run has facts from both sources sharing `dim_customer` with no fact-to-fact relationship. Start → combined dry run in **≤ 6 taps** and ≤ 5 s locally | |
| 7 | **SM8 Demo workspace and the phone test** (needs Gustav's ok for Fabric writes in the **demo** workspace) | Lay out the demo workspace as (a) and (b): `bronze_lh`, `silver_lh`, `gold_lh`, `sap_lh`, `crm_lh` with the synthetic SAP and Salesforce rows (`sap_demo.write_csv`, `salesforce_demo.write_csv`); then Gustav's phone test, timed | **Start → model dry run in ≤ 6 taps and ≤ 90 s on Gustav's phone**, on (a) and on (b), recorded in `docs/CHAT-TEST-<date>.md` with the seconds per step. Nothing outside the demo tenant | |
| 8 | **SM9 A second team** (after SM7) | Reference a shared entity from a second product (COMBINE-SOURCES.md section 5; DOMAINS-DESIGN.md part 4) | On the fixture, a third source (cases) is offered Sales' `dim_customer` with a counted overlap; one tap references it; no second customer table is built | |

**SM2 is done** (21 November 2026): 4 taps and 2.8 s locally from Start to all three dry runs, at most 25 words and 3
buttons plus Next per step, no step scrolls at 390 x 800 (AUDIT.md section 7, `measure-2026-11-21.json`).

**SM3 is done** (21 November 2026): in the editor, open to the dry run of pipeline + semantic model + data agent in 4
clicks and 2.3 s locally, at 390 px and on a desktop (from 8 clicks and 3.6-3.8 s); five steps with the chat's words; 3
outputs shown and 6 under More outputs; one accept-all (AUDIT.md section 8, `measure-editor-2026-11-21.json`).

**SM4 is done** (21 November 2026): 16 tools listed by default (from 48), all 48 with `KRUSGRAPH_ADVANCED_TOOLS=1`;
every hidden tool still answers by name; 0 cards without a way on (from 1) and 0 card buttons for an unlisted tool
(AUDIT.md section 11, `measure-tools-2026-11-21.json`).

SM5-SM7 change the engine (`infer.py`, `graphs.py`, `server.py`'s write path). They come after SM2-SM4 because those
three change what every later round's UI looks like, and the multi-source flow should be built straight into five steps.

## The synthetic multi-lakehouse fixture (SM5, local only)

`tests/fixtures/multi_lakehouse.py` builds one fake workspace, `mlh_demo`, from synthetic rows only:

| Lakehouse | Schemas | Rows from | For layout |
|---|---|---|---|
| `bronze_lh` | `sap` (17 tables) | `sap_demo.tables()` | (a) source |
| `silver_lh` | (empty) | | (a) target |
| `gold_lh` | (empty) | | (a) target |
| `sap_lh` | `sap_silver` | `sap_demo.tables()` | (b) |
| `crm_lh` | `crm_silver` | `salesforce_demo.tables()`, plus one synthetic column, `Account.SAP_Customer_No__c`, filled for 4 of 5 accounts with the demo's `KNA1.KUNNR` values (one with leading zeros stripped) and `Account.VAT__c` for M1 | (b) |
| `sales_product_lh` | `sap`, `crm` as shortcuts (simulated) | the two above | (b) → (c) |

How it is built:
- Each lakehouse is a SQLite database. `ATTACH` gives three-part names, the same way the SQL endpoint does inside one
  workspace.
- Shortcuts are simulated as views.
- The fixture replaces the same outer seams as `tests/wb15_fake.py`: the REST readers, the SQL endpoint, the tokens.
  Any POST, PATCH, PUT or DELETE fails the test.
- The existing SAP and Salesforce demos and their goldens stay unchanged. The CRM column is added only in the fixture.

`EXPECTED` lists, for each layout, what plan, check and dry run must say. SM5-SM7 measure "done" against it.

## The demo-workspace round (SM8): what Gustav approves

- Create 5 lakehouses in the demo workspace, schema-enabled, named as above, and one product lakehouse with two schema
  shortcuts.
- Load the synthetic CSVs with the notebooks the demos already write.
- Run start on (a) and on (b) to the dry runs, then Create only what Gustav taps.
- Delete everything afterwards on request.
- Nothing outside the demo tenant. No secrets in the repo.
