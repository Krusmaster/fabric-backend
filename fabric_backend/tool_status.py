"""Each hosted tool's status as data, so one tool cannot carry two statuses on two pages (the website brief of
26 October 2026, /docs: "a shared status source with separate fields for availability, what the tool changes, test
level and latest verification").

`label()` turns the fields into the site's status words (Tested end to end, Experimental, Draft only, Available when
enabled by the operator, Planned); the docs' tool table, its test status list, llms.txt, the use-case tasks, the
home page's test line, the start page's hub (`SOURCES`, `BUILDS`, `build_word()`, `clients_working()`), the server's
instructions and the notes in the tools' own answers (`answer_note()`) render from here. "Draft only" says what a tool changes (nothing), "Tested end to end" how far it has been run: a draft that
ran live is "Tested end to end (a draft; creates nothing)", and a creating tool whose dry run ran live says "tested end
to end as a dry run" while creating keeps its status.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .tool_listing import changes_on as _changes_on   # LFD5: KRUSGRAPH_CHANGES, off by default
from .record_match import on as _match_on             # GR1: KRUSGRAPH_MATCH_RECORDS, off by default

HOSTED, OPERATOR = "hosted", "operator"          # operator: needs a permission the hosted app does not ask for today
READS, DRAFT, CREATES = "reads", "draft", "creates"

# The run that counts as tested end to end: from Claude through the hosted connector and Microsoft sign-in, against
# the demo workspace (a Fabric workspace with synthetic data: demo / demo_lh / shop), read-only, as drafts or as dry
# runs, and then, with the maintainer's approval, one creating call: create_backend updated shop_api in place (docs,
# Test status; the checklist is docs/LIVE-TEST.md).
LIVE_RUN_DATE = "27 October 2026"
LIVE_RUN_BUILD = "src-df29c45febaec4b0 (main 5adace8)"
# the tools of that run: read, then drafted, then the dry runs
LIVE_RUN = ("list_workspaces", "list_sources", "list_tables", "sample_rows", "plan_backend", "validate_plan",
            "suggest_relationships", "analyze_schema", "join_path", "describe_backend", "query_graphql", "answer_query_draft",
            "app_readiness", "app_starter", "plan_drift", "lineage", "review_plan", "compare_semantic_model",
            "dbt_schema", "data_dictionary", "semantic_model_draft", "ontology_draft", "rayfin_connector", "silver_notebook_draft",
            "gold_views_draft", "drift_monitor_draft", "export_item_definitions",
            "create_views", "create_semantic_model", "create_data_agent", "create_backend")
# a tool that ran only part of the way, with how far
LIVE_RUN_PARTLY = {"compare_semantic_model": "as far as the model lookup, which answered not_found: the demo workspace had no model that day",
                   "create_backend": "as an update in place of shop_api with confirmed; no new item was created"}
# Creating calls run live after that run, with dry_run=false against the same workspace (from 28 October 2026, after the
# Entra app got Notebook.ReadWrite.All, DataPipeline.ReadWrite.All and Item.ReadWrite.All): what each one did, in the
# order they first created something.
LATER_LIVE = {
    "create_silver_notebook": "On 28 October 2026 it created the notebook silver_shop live against a Fabric workspace with "
                              "synthetic data; the notebook has not been run in Fabric.",
    "create_gold_views": "On 28 October 2026 it created the notebook gold_shop live against a Fabric workspace with synthetic "
                         "data; the notebook has not been run in Fabric.",
    "create_drift_monitor": "On 28 October 2026 it created drift_shop and drift_shop_nightly live with schedule=false against a "
                            "Fabric workspace with synthetic data; neither has been run in Fabric, and the schedule needs "
                            "DataPipeline.Execute.All.",
    "create_ontology": "On 28 October 2026 it created the ontology shop_ontology live against a Fabric workspace with synthetic "
                       "data (7 entity types, 5 with a key; 7 relationship types). Before that, with the ontology (preview) turned off in the tenant's settings, Fabric "
                       "answered HTTP 403 FeatureNotAvailable. On 29 October 2026 Gustav reviewed the item in the Fabric portal. On 26 "
                       "November 2026 it created shop_ontology_2 from Claude (the dry run found shop_ontology taken and offered "
                       "the new name); Fabric was still working when the call returned, a status check then read it in Fabric "
                       "as an ontology, the portal showed 7 entity types and 7 relationship types, and verify_build passed on it.",
    "create_semantic_model": "On 29 October 2026 it created the semantic model shop_model_live live against a Fabric workspace "
                             "with synthetic data (7 tables, 6 active and 1 inactive relationship, Direct Lake, 4 measures, "
                             "the date table Calendar); the same day Gustav refreshed it and reviewed it in the Fabric portal. On 30 October "
                             "2026 shop_model was updated in place from Lovable (as an MCP client at /mcp/connect).",
    "create_report": "On 30 October 2026 it created the report shop_report_live live against a Fabric workspace with synthetic data "
                     "(dry run first, then dry_run=false; one blank page bound to shop_model_live; status Succeeded, mode created). "
                     "Later that day Lovable (as an MCP client at /mcp/connect) created shop_report on shop_model; Gustav opened "
                     "shop_report in the Fabric portal, added a visualisation (Calendar) and saw data. On 7 November 2026 it "
                     "created shop_report_visuals on shop_model with the page drawn from the model's measures (round n144; status "
                     "Succeeded); Gustav opened it in Power BI and every figure was right (60 orders, 134 order lines, 40 audit_log "
                     "rows; units by category; products by units, total 324). shop_report_lovable was created the same way from "
                     "Lovable through the Krusgraph connector.",
}
# n87: the same runs as a tool's own answer says them: no person's or client's name, no counts of that day's item that
# today's draft need not have.
LATER_LIVE_ANSWER = {
    "create_ontology": "On 28 October 2026 it created the ontology shop_ontology live against a Fabric workspace with synthetic "
                       "data; the item was reviewed in the Fabric portal on 29 October 2026. On 26 November 2026 it created another "
                       "ontology the same way, which a status check read in Fabric and verify_build passed.",
    "create_semantic_model": "On 29 October 2026 it created the semantic model shop_model_live live against a Fabric workspace "
                             "with synthetic data; it was refreshed and reviewed in the Fabric portal the same day, and a model "
                             "was updated in place on 30 October 2026. The counts in this answer are today's draft's.",
    "create_report": "On 30 October 2026 it created the report shop_report_live live against a Fabric workspace with synthetic "
                     "data (one blank page bound to shop_model_live; status Succeeded, mode created); a report made the same "
                     "way was opened in the Fabric portal, given a visual and showed data. On 7 November 2026 it created a report "
                     "with the page drawn from the model's measures (status Succeeded); its figures were checked in Power BI.",
}
# n143: a creating tool whose created item has been run in Fabric, as its own answer says it; nothing more is claimed.
RAN_LIVE = {
    "create_pipeline": "Run live in the demo workspace (synthetic data) on 7 November 2026: the pipeline pipeline_shop, "
                       "run 9de8bc49, all three steps succeeded.",
}
# n88: a later live run of a tool that ran on LIVE_RUN_DATE, as docs/LIVE-TEST.md records it: `said` goes into the tool's
# own answer, `evidence` is the words of docs/LIVE-TEST.md that record it (tests/test_n88_live_notes.py checks both).
LATEST_LIVE = {
    "lineage": {"said": "Last run live on 2 November 2026 (build src-69aa8afa445e6c97) against the same workspace: 7 tables "
                        "and 7 objects, none skipped.",
                "evidence": "**`lineage`**: 7 tables and 7 objects, none skipped."},
    "validate_plan": {"said": "Last run live on 26 November 2026 against the same workspace: on schema shop 6 of 6 keys held, "
                              "7 of 7 links held, no orphans; 13 passed, 0 failed, 0 not checked.",
                      "evidence": "**`validate_plan`** on schema `shop`: 6 of 6 keys held, 7 of 7 links held, no orphans; 13 "
                                  "passed, 0 failed, 0 not checked."},
    "join_path": {"said": "Last run live on 2 November 2026, after round n87's deployment: orders to addresses took the direct "
                          "step through ship_to_id, rule R5.",
                  "evidence": "**`join_path`** from `orders` to `addresses`: the direct step through `ship_to_id`, rule R5."},
}
# n87: creating tools whose creating has no recorded run, with what docs/LIVE-TEST.md does record.
CREATE_RECORD = {
    "create_views": "creating has no recorded live run (docs/LIVE-TEST.md, row 20), although the demo lakehouse holds the view "
                    "krusgraph.vw_order_items, which create_views made at a time no protocol records.",
    "create_data_agent": "on 26 November 2026 it created shop_agent from the Start Krusgraph card (step 5, after the dry run "
                         "and the confirmed name); the agent has not yet been read back by verify_build (docs/LIVE-TEST.md).",
}
# LV1: a create run live on 26 November 2026 whose item has not been read back or used yet, as the tool's own answer says it
# (docs/LIVE-TEST.md, "26 Nov 2026 LV1"). Only that: the status word and build_word() do not change for it.
LATER_CREATE = {
    "create_backend": "On 26 November 2026 it created a new API, shop_api_2, live against the same workspace, and verify_build "
                      "read it back as verified; no query has been run against it yet.",
}
LATER_CREATE_SENTENCE = ("On 26 November 2026 a new API was made with create_backend and read back by verify_build as "
                         "verified, and a data agent was made with create_data_agent from the Start Krusgraph card; the data "
                         "agent has not been read back, and no query has used either yet.")
# Creating tools whose live item has been reviewed in the Fabric portal, and when (only that: not each part, no agent use).
REVIEWED = {"create_ontology": "29 October 2026", "create_semantic_model": "29 October 2026", "create_report": "30 October 2026"}
# n177: a tool's option that changes what it does, and the date it first ran live with that option against the demo
# workspace, as docs/LIVE-TEST.md records it. The chat demo's fixes step is validate_plan with fixes=true and its dbt step
# dbt_schema with project=true; LIVE-TEST's rows 6 and 16 ran both tools without them, so neither is here.
# tests/test_chat_demo.py reads LIVE-TEST and fails when a dated row with the option is added and this is not.
OPTION_WORDS = {("validate_plan", "fixes=true"): ("Proposing fixes", "the check itself"),
                ("dbt_schema", "project=true"): ("The dbt project", "the sources file alone")}
LIVE_OPTIONS: dict[tuple[str, str], str] = {}
# The creating tools without a dry_run argument: they would write on the call. None since round n111 (create_backend
# has one); tests/test_site.py checks this against the tools' signatures in server.py.
NO_DRY_RUN: tuple[str, ...] = ()
# The first such run, kept for the record: 14 steps, 16 tools, no creating call.
FIRST_RUN_DATE, FIRST_RUN_STEPS = "26 October 2026", 14
FIRST_RUN = ("list_workspaces", "list_sources", "sample_rows", "plan_backend", "validate_plan", "suggest_relationships",
             "analyze_schema", "join_path", "describe_backend", "query_graphql", "semantic_model_draft", "data_dictionary",
             "dbt_schema", "create_views", "plan_drift", "app_starter")
# What a sentence about the run says it covered (the home page's test line).
LIVE_RUN_SUMMARY = ("from Claude to a Fabric workspace with synthetic data: sign-in, plan, check, query, the drafts, three dry "
                    "runs and an update in place of an existing API; no new item was created")


@dataclass(frozen=True)
class ToolStatus:
    available: str             # HOSTED or OPERATOR
    kind: str                  # READS, DRAFT or CREATES
    changes: str               # what it changes in Fabric, in plain words
    tested: str                # how it is tested beyond the live run
    dry_run_only: bool = False  # in the live run, only as a dry run
    note: str = ""             # a qualifier after the status word, with its leading punctuation
    name: str = ""

    @property
    def live(self) -> bool:
        """Ran in the live run of LIVE_RUN_DATE (for a creating tool: its dry run)."""
        return self.name in LIVE_RUN


_NO = "nothing"
_ITEM = "creates/updates one item; never deletes"
# n146: the qualifiers that used to follow the status word are now separate fields (LIVE: the last operation tried
# live, its date and its result; OPEN: what is still open), so `note` stays empty and label() builds the text.
_RAW = {
    "start": (HOSTED, READS, "nothing (answers the next step; calls no tool itself)",
              "unit tests; the card's steps 1 to 5 live on 26 November 2026"),   # n219
    "publish_catalog": (HOSTED, CREATES, "sets item descriptions and adds existing tags; never removes, deletes or endorses",
                        "unit tests (Fabric replaced by a test double); not run against Fabric"),   # CA1
    "verify_build": (HOSTED, READS, _NO, "unit tests (definitions, rows and Power BI answers replaced by test doubles); "
                     "run live on 26 November 2026: verified, a real differs at relationship level, and not checked with "
                     "its reason"),   # n229
    "list_workspaces": (HOSTED, READS, _NO, "unit tests"),
    "list_sources": (HOSTED, READS, _NO, "unit tests"),
    "list_tables": (HOSTED, READS, _NO, "unit tests"),
    "plan_backend": (HOSTED, READS, "nothing (counting queries for rule R5)", "unit tests"),
    "validate_plan": (HOSTED, READS, "nothing (counting queries)", "unit tests"),
    "sample_rows": (HOSTED, READS, _NO, "unit tests; the masking live since 27 October 2026"),
    "create_backend": (HOSTED, CREATES, _ITEM, "unit tests; live as an update in place, and one new item created live on 26 November 2026 and "
                       "verified by verify_build, not yet queried"),
    "describe_backend": (HOSTED, READS, _NO, "unit tests"),
    "query_graphql": (HOSTED, READS, _NO, "unit tests; with `question` live since 27 October 2026"),
    "rayfin_connector": (HOSTED, DRAFT, _NO, "unit tests"),
    "ontology_draft": (HOSTED, DRAFT, _NO, "unit tests"),
    "semantic_model_draft": (HOSTED, DRAFT, _NO, "unit tests"),
    "join_path": (HOSTED, READS, _NO, "unit tests"),
    "data_dictionary": (HOSTED, DRAFT, _NO, "unit tests"),
    "dbt_schema": (HOSTED, DRAFT, _NO, "unit tests"),
    "domain_draft": (HOSTED, DRAFT, _NO, "unit tests (shop, the synthetic SAP demo, Salesforce + ERP)"),
    "sap_pack_draft": (HOSTED, DRAFT, _NO, "unit tests (synthetic SAP schema; no SAP system)"),
    "plan_drift": (HOSTED, READS, _NO, "unit tests"),
    "create_semantic_model": (HOSTED, CREATES, _ITEM, "unit tests; created live on 29 October 2026", True),
    "create_report": (HOSTED, CREATES, "creates one item; never updates or deletes",
                      "unit tests with the REST calls mocked (201, 202 with a long-running operation, 403, a name already taken); created live on 30 October 2026, "
                      "the page with visuals on 7 November 2026"),
    "create_views": (HOSTED, CREATES, "creates/alters views in that schema only; never drops",
                     "unit tests; creating by unit tests only", True),
    "create_data_agent": (HOSTED, CREATES, "creates/updates one item and its staging config; never deletes",
                          "unit tests; created once from the start card on 26 November 2026, not read back", True),
    "create_ontology": (HOSTED, CREATES, _ITEM, "unit tests; created live on 28 October 2026, again on 2 and 26 November 2026"),
    "app_starter": (HOSTED, DRAFT, _NO, "unit tests"),
    "app_readiness": (HOSTED, READS, "nothing (one introspection query)", "unit tests"),
    "analyze_schema": (HOSTED, READS, _NO, "unit tests"),
    "lineage": (HOSTED, READS, _NO, "unit tests"),
    "silver_notebook_draft": (HOSTED, DRAFT, _NO, "unit tests and a local PySpark 4.0.1"),
    "create_silver_notebook": (HOSTED, CREATES, _ITEM, "unit tests; created live on 28 October 2026"),
    "drift_monitor_draft": (HOSTED, DRAFT, _NO, "unit tests; the notebook ran two nights on a local PySpark"),
    "create_drift_monitor": (HOSTED, CREATES, "creates/updates two items and a schedule; never deletes",
                             "unit tests; created live with schedule=false on 28 October 2026"),
    "answer_query_draft": (HOSTED, DRAFT, _NO, "unit tests on the shop schema"),
    "suggest_relationships": (HOSTED, READS, "nothing (counting queries)", "unit tests"),
    "compare_semantic_model": (HOSTED, READS, _NO, "unit tests; live only as far as the model lookup"),
    "gold_views_draft": (HOSTED, DRAFT, _NO, "unit tests; the SQL on SQLite and a local PySpark 4.0.1"),
    "create_gold_views": (HOSTED, CREATES, "creates/updates one notebook; never deletes", "unit tests; created live on 28 October 2026"),
    "create_pipeline": (HOSTED, CREATES, "creates/updates three notebooks and one pipeline; never deletes, runs or schedules",
                        "unit tests; run live on 7 November 2026 (pipeline_shop, run 9de8bc49)"),
    "export_item_definitions": (HOSTED, DRAFT, _NO, "unit tests"),
    "review_plan": (HOSTED, READS, "nothing (counting queries with validate=true)", "unit tests; reading a file back by unit tests only"),
    # Q2: Krusgraph Migrate, from Qlik to Power BI (qlik_tools.py). No Qlik installation and no customer's script was read.
    "qlik_plan": (HOSTED, DRAFT, "nothing (counting queries when a workspace and a source are named)",
                  "unit tests (a synthetic load script with synthetic rows, and public load scripts; no Qlik installation)"),
    "qlik_measures_draft": (HOSTED, DRAFT, _NO, "unit tests (synthetic expressions; the DAX was not run)"),
    "qlik_reconcile_draft": (HOSTED, DRAFT, _NO, "unit tests (the statements run on SQLite over synthetic rows)"),
    # AP2: the analysis pack, phase 1. Rules over metadata and counts; the notebook runs in Fabric, started by the analyst.
    "analysis_plan": (HOSTED, READS, "nothing (counting queries)", "unit tests on the synthetic SAP samples (SQLite)"),
    "analysis_notebook_draft": (HOSTED, DRAFT, _NO, "unit tests; the notebooks ran on a local PySpark 4.0.1 against synthetic SAP data"),
    # RQ1: a pasted requirements list matched to the checked SAP data by rules; reads names and counts, never a value
    "requirements_draft": (HOSTED, READS, "nothing (counting queries)", "unit tests and goldens on the synthetic SAP demo (SQLite)"),    # BL64: the plan as Fabric semantic view YAML (preview); writing to the lakehouse and Publish are left for later
    "semantic_view_draft": (HOSTED, DRAFT, "nothing (counting queries with validate=true)",
                            "unit tests on the synthetic samples (SQLite); not run against Fabric"),
}
# LFD5: the change-by-chat tool exists only with KRUSGRAPH_CHANGES=1 (off by default); off, it has no status, so no page,
# listing or instruction names it.
# GR1: match_records exists only with KRUSGRAPH_MATCH_RECORDS=1 (off by default); off, it has no status, like propose_change.
if _match_on():
    _RAW["match_records"] = (HOSTED, READS, "nothing (counting queries)",
                             "unit tests on the synthetic CRM, ERP and MDM customers (SQLite); not run against Fabric")
if _changes_on():
    _RAW["propose_change"] = (HOSTED, READS, "nothing (plans and drafts; never writes to Fabric)",
                              "unit tests on the synthetic shop_lfd sample (SQLite); not run against Fabric")
    # LFD6: the change applied through Update; a creating tool, so KRUSGRAPH_READ_ONLY=1 leaves it out (switches.creates)
    _RAW["apply_change"] = (HOSTED, CREATES, "updates in place the notebooks, pipeline and semantic model a proposed change marks, "
                                             "runs the pipeline once when rows change and refreshes the model; never deletes",
                            "unit tests on the synthetic shop_lfd sample against a fake Fabric; not run against Fabric")
STATUS: dict[str, ToolStatus] = {name: ToolStatus(*v, name=name) for name, v in _RAW.items()}


DRY_RUN = "tested end to end as a dry run"
TRIED = "Tried live"

# n146: each tool's last operation tried against a live workspace, separate from its status word: (date, operation,
# result). A tool of the run of LIVE_RUN_DATE without an entry here gets that run's row (live_fields()). Every entry is
# a dated record of docs/LIVE-TEST.md or of the dicts above (LATER_LIVE, RAN_LIVE, LATEST_LIVE, LIVE_RUN_PARTLY).
LIVE = {
    "start": ("26 November 2026", "the Start Krusgraph card from Claude, steps 1 to 5 on demo / demo_lh / shop",
              "step 2: 6 tables, 7 links, 1 needs you, 13 of 13 checks hold; step 3: orders.ship_to_id → addresses, 60 of 60 "
              "found, accepted; step 4: the dry run; step 5: shop_pipeline, shop_model and shop_agent confirmed and Yes, create "
              "for each, with progress lines, ending in Done. What next?; each item's own final state is not recorded"),
    "verify_build": ("26 November 2026", "shop_ontology_2, shop_ontology and shop_api_2 one by one from Claude, and the "
                     "whole shop data product",
                     "each single item verified, by rules (an ontology: 7 entity types, 7 relationships, 14 data bindings; "
                     "shop_api_2: 7 types, 14 relationships); over the whole product 10 items verified, shop_model_film "
                     "differs (two relationships with active and inactive swapped; never refreshed; its figures still match "
                     "the rows), shop_pipeline differs (definition as the plan, never run), and shop_report not checked: no "
                     "item of that name in the workspace; the product's report, shop_overview, verified on its own: 6 "
                     "visuals, its 3 figures as the rows (324 units, 60 orders, 134 order lines)"),
    "create_data_agent": ("26 November 2026", "created shop_agent from the Start Krusgraph card, after the dry run and the "
                          "confirmed name", "created from the start card; not yet read back by verify_build"),
    "lineage": ("2 November 2026", "read-only call from Claude (build src-69aa8afa445e6c97)", "7 tables and 7 objects, none skipped"),
    "validate_plan": ("26 November 2026", "read-only call from Claude",
                      "schema shop: 6 of 6 keys held, 7 of 7 links held, no orphans; 13 passed, 0 failed, 0 not checked"),
    "join_path": ("2 November 2026", "read-only call from Claude, after round n87's deployment",
                  "orders to addresses through ship_to_id, rule R5"),
    "create_backend": ("26 November 2026", "created shop_api_2 as a new item from the validate_plan card (dry run: new, 7 "
                       "tables and 14 relationship fields; then Yes, create)", "Created shop_api_2, an API for GraphQL, in "
                       "Fabric; verify_build: verified (7 types, 14 relationships, 0 differ); not yet queried; updated shop_api "
                       "in place from Claude on 27 October 2026 and from Lovable on 30 October 2026"),
    "create_semantic_model": ("30 October 2026", "update in place of shop_model from Lovable (as an MCP client)",
                              "updated; created live on 29 October 2026 as shop_model_live, refreshed and reviewed in the "
                              "Fabric portal by Gustav the same day"),
    "create_report": ("7 November 2026", "created shop_report_visuals on shop_model with the page drawn from the model's "
                      "measures (round n144), and shop_report_lovable the same way from Lovable", "status Succeeded; every figure "
                      "checked in Power BI was right; the first blank-page report was created on 30 October 2026"),
    "create_ontology": ("26 November 2026", "created shop_ontology_2 from Claude with dry_run=false (the dry run found "
                        "shop_ontology taken); Fabric was still working when the call returned, and Check status read it",
                        "in Fabric as an ontology; the portal showed 7 entity types and 7 relationship types; verify_build "
                        "passed; created live before on 28 October and 2 November 2026"),
    "create_silver_notebook": ("28 October 2026", "created the notebook silver_shop with dry_run=false", "created"),
    "create_gold_views": ("28 October 2026", "created the notebook gold_shop with dry_run=false", "created"),
    "create_drift_monitor": ("28 October 2026", "created drift_shop and drift_shop_nightly with dry_run=false and schedule=false",
                             "created"),
    "create_pipeline": ("7 November 2026", "created pipeline_shop and its three notebooks, then the pipeline was run in Fabric "
                        "(run 9de8bc49)", "all three steps succeeded"),
    "compare_semantic_model": ("27 October 2026", "looking up a semantic model by name, from Claude",
                               "not_found: the demo workspace had no model that day"),
}
_PIPELINE_RAN = "create_pipeline writes the same notebook and ran it in Fabric on 7 November 2026 (run 9de8bc49)"
# n146: what is still open for each tool: what has not been tried live, or what it needs that the hosted app lacks.
OPEN = {
    "start": "step 5's Create buttons on the card are not seen by the model in the chat (being fixed); each item's own final "
             "state from the card is not recorded",
    "verify_build": "on 26 November 2026 Verify what was built first picked the older shop_ontology over shop_ontology_2 "
                    "(being fixed), and the whole-product run looked for shop_report while the product's report is "
                    "shop_overview (verified when named); which 2 items differed in an earlier run that day (8 items: 6 "
                    "verified, 2 differ) is not recorded",
    "create_backend": "no query has been run against the new API created live on 26 November 2026 (shop_api_2)",
    "create_views": "creating them: Experimental; creating has no recorded live run",
    "create_data_agent": "creating: Experimental; shop_agent, created from the start card on 26 November 2026, has not been "
                         "read back by verify_build",
    "create_report": "the page's look of round n151 (plain titles, layout, theme, slicers, the date table's Year Month) has not run live",
    "create_ontology": "needs the tenant setting \"Users can create Ontology (preview) items\" (HTTP 403 FeatureNotAvailable "
                       "while it was off, 28 October 2026)",
    "create_silver_notebook": "the notebook it created has not been run in Fabric; " + _PIPELINE_RAN,
    "create_gold_views": "the notebook it created has not been run in Fabric; " + _PIPELINE_RAN,
    "silver_notebook_draft": "the notebook ran on a local PySpark 4.0.1; " + _PIPELINE_RAN,
    "analysis_notebook_draft": "the notebooks ran on a local PySpark 4.0.1 without MLflow, AutoML or scikit-learn; not yet in Fabric",
    "gold_views_draft": "the SQL ran on SQLite and a local PySpark 4.0.1; " + _PIPELINE_RAN,
    "drift_monitor_draft": "the notebook ran two nights on a local PySpark, not yet in Fabric",
    "create_drift_monitor": "neither item has been run in Fabric; the schedule needs DataPipeline.Execute.All, opt-in on the "
                            "hosted app",
    "create_pipeline": "Run once and Schedule (after a dry run and the person's confirmation) need DataPipeline.Execute.All, "
                       "opt-in on the hosted app, and have not run live: on 26 November 2026 Run once from the chat was "
                       "refused because the signed-in token lacks it (only the dry run happened, nothing changed); without "
                       "it someone runs the pipeline in Fabric",
    "compare_semantic_model": "comparing with a live model, and comparing from `tmdl` files, have not run live",
    "review_plan": "reading a file back is unit-tested only",
}


def live_fields(name: str) -> tuple[str, str, str]:
    """(date, operation, result) of the tool's last operation tried live, or ("", "", "") when it has none."""
    if name in LIVE:
        return LIVE[name]
    s = STATUS[name]
    if not s.live:
        return "", "", ""
    op = ("dry run from Claude; nothing created" if s.dry_run_only else
          "draft from Claude; creates nothing" if s.kind == DRAFT else "read-only call from Claude")
    return LIVE_RUN_DATE, op, "passed (docs/LIVE-TEST.md)"


def word(name: str) -> str:
    """The status word: availability first, then how far it has run live, then what it changes. n146: Experimental only
    for a tool that has never been tried live; a tool tried live after the run of LIVE_RUN_DATE, or only partly that
    day, is Tried live, with the operation, the date and the result in its fields."""
    s = STATUS[name]
    if s.available == OPERATOR:
        return "Available when enabled by the operator" + (f"; {DRY_RUN}" if s.live and s.dry_run_only else "")
    if name in LIVE and name not in LIVE_RUN or name in LATER_LIVE or name in RAN_LIVE or \
            (s.live and name in LIVE_RUN_PARTLY and s.kind != CREATES):
        return TRIED
    if s.live:
        if s.dry_run_only:
            return DRY_RUN[0].upper() + DRY_RUN[1:]
        if s.kind == CREATES and name in LIVE_RUN_PARTLY:        # create_backend: live only as an update in place
            return "Tested end to end as an update in place"
        return "Tested end to end (a draft; creates nothing)" if s.kind == DRAFT else "Tested end to end"
    return "Draft only" if s.kind == DRAFT else "Experimental"


def label(name: str) -> str:
    """The word with the fields: the last operation tried live (date, what, result) and what is still open."""
    date, op, result = live_fields(name)
    out = word(name)
    if date:
        out += f"; last tried live {date}: {op}; result: {result}"
    if name in OPEN:
        out += f"; still open: {OPEN[name]}"
    return out


WORDS = ("Tested end to end", "Tried live", "Experimental", "Draft only", "Available when enabled by the operator", "Planned")
# n79: the evidence report (evidence_report.py) is a file, not a tool: /check and fabric-backend demo offer it with this
# status; the person who hands it over reads and signs it off.
EVIDENCE_REPORT = "Draft"
# n80: the ontology as RDF/XML for Microsoft's Ontology Playground (ontology.ontology_rdfxml), a file on /check, not a tool:
# a draft to open there with a file import; nothing is created in Fabric.
ONTOLOGY_RDFXML = "Draft"
# n82: Gustav opened an RDF/XML file from /check in Microsoft's Ontology Playground on 2 November 2026, with a good result
# (docs/LIVE-TEST.md, section 6). Only that: the file stays Draft, and no partnership with Microsoft is claimed.
ONTOLOGY_RDFXML_TRIED = "Gustav tried a file from /check there on 2 November 2026, with a good result"


def phrase(name: str) -> str:
    """The label inside a sentence: the status words in lower case."""
    text = label(name)
    for w in WORDS:
        text = text.replace(w, w[0].lower() + w[1:])
    return text


def short(name: str) -> str:
    """The status next to an offer on a sales page (the home page): the word without the history behind it. A creating
    tool that has not created anything live is "draft; deployment not yet verified"; the long form (`label`, with the
    dates and Fabric's answers) is on /docs#test-status. A tool whose item has been reviewed in Fabric says so instead."""
    if name in REVIEWED:
        return "created live; reviewed in Fabric"
    if name in LATER_LIVE or name in RAN_LIVE:      # n205: create_pipeline created pipeline_shop live and it ran (RAN_LIVE)
        return "created live"
    if STATUS[name].kind == CREATES and build_word(name) == "draft":
        return "draft; deployment not yet verified"
    w = word(name)
    return w[0].lower() + w[1:]


# n205: the tool list in an AI client says what the site and the README say. A tool whose short status is neither "tested
# end to end" (in any of its forms) nor "created live" gets EXPERIMENTAL at the end of its title (never its name);
# server.py's _titled_tool applies it, and tests/test_n205_labels.py checks every hosted tool against this.
EXPERIMENTAL = " (experimental)"


def experimental(name: str) -> bool:
    """True when the tool's short status is not "tested end to end ..." or "created live ..."; a tool without a status
    record counts as experimental."""
    if name not in STATUS:
        return True
    s = short(name)
    return not (s.startswith("tested end to end") or s.startswith("created live"))


def titled(name: str, title: str) -> str:
    """The tool's title as an MCP client shows it: with EXPERIMENTAL at the end when experimental(name)."""
    return title + EXPERIMENTAL if experimental(name) and not title.endswith(EXPERIMENTAL) else title


README_BEGIN = "<!-- tool-status:begin (generated from fabric_backend/tool_status.py by readme_status_md(); do not edit by hand) -->"
README_END = "<!-- tool-status:end -->"


def readme_status_md() -> str:
    """n205: the README's status line per hosted tool, the same short status the site uses and whether the tool's title in
    an AI client ends in "(experimental)". tests/test_n205_labels.py checks that README.md carries exactly this block."""
    rows = ["| Tool | Status | Title in the tool list |", "| --- | --- | --- |"]
    rows += [f"| `{t}` | {short(t)} | {'ends in (experimental)' if experimental(t) else 'no label'} |" for t in STATUS]
    return "\n".join([README_BEGIN, *rows, README_END])


def _listed(names) -> str:
    names = list(names)
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else "".join(names)


def live_run_list() -> str:
    """The live run's tools as the docs list them: in run order, the dry runs and partial runs marked."""
    def one(t: str) -> str:
        if STATUS[t].dry_run_only:
            return f"`{t}` (dry run only; nothing was created)"
        return f"`{t}` ({LIVE_RUN_PARTLY[t]})" if t in LIVE_RUN_PARTLY else f"`{t}`"
    return _listed(one(t) for t in LIVE_RUN)


def not_run_list() -> str:
    """The hosted tools that did not run in the live run, not even as a dry run."""
    return _listed(f"`{t}`" for t in STATUS if not STATUS[t].live)


def answer_note(name: str) -> str:
    """One sentence for a tool's own answer: how far it has run against a live workspace, from the same fields."""
    s, where = STATUS[name], "against a Fabric workspace with synthetic data"
    if name in LATER_LIVE:
        return LATER_LIVE_ANSWER.get(name, LATER_LIVE[name])
    if name in RAN_LIVE:
        return RAN_LIVE[name]
    if not s.live:
        if name in LIVE:          # LV1: tried live after the run of LIVE_RUN_DATE, read-only
            date, op, result = LIVE[name]
            return f"Tried live on {date} {where}: {op}; result: {result}."
        return "Not yet run against a live workspace."
    if name in LIVE_RUN_PARTLY:
        later = (" " + LATER_CREATE[name]) if name in LATER_CREATE else ""
        return f"Run live on {LIVE_RUN_DATE} {where} only {LIVE_RUN_PARTLY[name]}.{later} The rest is unit-tested."
    if s.dry_run_only:
        return f"The dry run was tested end to end on {LIVE_RUN_DATE} {where}; " + CREATE_RECORD.get(
            name, "creating has no recorded live run (docs/LIVE-TEST.md).")
    latest = (" " + LATEST_LIVE[name]["said"]) if name in LATEST_LIVE else ""
    if s.kind == DRAFT:
        return f"This tool's call was tested end to end on {LIVE_RUN_DATE} {where} as a draft; it creates nothing." + latest
    return f"Tested end to end on {LIVE_RUN_DATE} {where}." + latest


def later_sentence() -> str:
    """n146: the tools whose status word is Tried live, each with the date of its last operation tried live."""
    tried = [t for t in STATUS if word(t) == TRIED]
    return ("Tried live, each with its own date and result: " + _listed(f"`{t}` ({LIVE[t][0]})" for t in tried) + "."
            if tried else "")


def instructions_sentence() -> str:
    """The test status in the server's instructions."""
    creating = [t for t in STATUS if STATUS[t].kind == CREATES]
    dry = [t for t in creating if STATUS[t].live and STATUS[t].dry_run_only]
    partly = "; ".join(f"{t} only {why.split(',')[0].split(';')[0]}" for t, why in LIVE_RUN_PARTLY.items())
    return (f"Test status: on {LIVE_RUN_DATE} every tool but {not_run_list().replace('`', '')} ran from Claude against a Fabric workspace "
            f"with synthetic data, read-only or as a draft, and {_listed(dry)} as dry runs" + (f" ({partly})" if partly else "")
            + "; no new item was created that day. Since then " + _listed(list(LATER_LIVE) + list(RAN_LIVE))
            + " have created items live against the same workspace. " + LATER_CREATE_SENTENCE
            + " Status per tool: /docs#test-status.")


def create_api_status() -> str:
    """create_backend in a sentence for the pages that offer creating the API: what ran live and what did not."""
    s = STATUS["create_backend"]
    if s.live and "create_backend" in LIVE_RUN_PARTLY:
        later = ("; one new API was created live on 26 November 2026 and verified, not yet queried"
                 if "create_backend" in LATER_CREATE else "")
        return f"Creating a new API is experimental{later}; updating one in place was tested end to end on {LIVE_RUN_DATE}"
    return "Creating the API is " + phrase("create_backend")


def create_api_word() -> str:
    """The status tag next to create_api_status(): the word for creating a new API."""
    s = STATUS["create_backend"]
    return "Experimental" if s.live and "create_backend" in LIVE_RUN_PARTLY else word("create_backend")


# n234, the founder's marks of 12 November 2026: visitor pages carry no test-status badges, no "last tried live" lines,
# no docs/ file names and no tool names in a status line; that record stays in docs/ and the tests. Where a visitor still
# needs a qualifier, these few plain words are all a page says.
def plain(name: str) -> str:
    """The plain qualifier for one tool on a visitor page: "draft" for a tool that creates nothing, "experimental" when
    experimental() says so, the operator's switch when it needs one, else nothing."""
    s = STATUS[name]
    if s.available == OPERATOR:
        return "available when enabled by the operator"
    if s.kind == DRAFT:
        return "draft"
    return "experimental" if experimental(name) else ""


def create_api_plain() -> str:
    """create_backend on a visitor page: only whether creating a new API is experimental."""
    s = STATUS["create_backend"]
    if (s.live and "create_backend" in LIVE_RUN_PARTLY) or experimental("create_backend"):
        return "Creating a new API is experimental"
    return "Creating the API is available"


def experimental_builds() -> str:
    """"creating views and a data agent is experimental": the BUILDS whose creating tool plain() calls experimental."""
    names = [n for n, t in BUILDS if t != "create_backend" and plain(t) == "experimental"]
    return (f"creating {_listed(['the ' + n for n in names])} is experimental" if names
            else "the other items are available")


def task_status(tools: list[str]) -> str:
    """One line for a group of tools: the live date when all ran live, otherwise each tool with its word."""
    if all(word(t).startswith("Tested end to end") and not STATUS[t].dry_run_only and t not in OPEN for t in tools):
        drafts = [f"`{t}`" for t in tools if STATUS[t].kind == DRAFT]
        what = "" if not drafts else (f" ({_listed(drafts)}: a draft; creates nothing)" if len(drafts) == 1
                                      else f" ({_listed(drafts)}: drafts; they create nothing)")
        return f"tested end to end on {LIVE_RUN_DATE}{what}"
    return "; ".join(f"`{t}`: {phrase(t)}" for t in tools)


# ------------------------------------------------------------------ the start page's hub --------------------------------
# Gustav's brief of 27 October 2026: what Krusgraph reads in Fabric, what it builds there from one plan, and where people
# build, each part with its status from the fields above, so the hub follows when another part is tested live.

# Sources, by whether one has been read end to end on the hosted service (the docs' Sources section says the same).
SOURCES = (("Lakehouse", True), ("Warehouse", False), ("SQL database", False))

# What is built in Fabric, by the creating tool that builds it.
BUILDS = (("GraphQL API", "create_backend"), ("Power BI semantic model", "create_semantic_model"),
          ("Fabric IQ ontology", "create_ontology"), ("views", "create_views"), ("data agent", "create_data_agent"),
          ("silver notebooks", "create_silver_notebook"))

# The clients, one row each (Gustav's brief of 28 October 2026): where each one reaches Krusgraph, its status word, and
# since when it works. VS Code, Cursor and Glama signed in through client registration at /mcp/connect and ran tools on
# 27 October 2026, Lovable on 30 October 2026 (docs/LIVE-TEST.md). n82: by Gustav's decision of 2 November 2026
# (CLIENTS_DECIDED) VS Code, Cursor and Lovable are Tested end to end; Glama and Claude Code stay Experimental. A client is named as
# working (the hub, the /mcp/connect sentence) when it has a `works_since`. Lovable has two rows: as an MCP client at
# /mcp/connect, and as the app builder that reads the GraphQL API create_backend makes (the hub's last row).
@dataclass(frozen=True)
class ClientStatus:
    name: str
    where: str                 # how it connects, in words
    path: str                  # /mcp, /mcp/connect, or "" for a client that does not use MCP
    status: str                # one of WORDS
    works_since: str = ""      # the date it first signed in and ran tools on the hosted service
    note: str = ""


CONNECT_NOTE = "client registration is switched on at krusgraph.com since 27 October 2026"
# n80: the one-click buttons on the site's Connect menu, checked by Gustav on 2 November 2026: each button works in its
# client. Only that: the button, not a new sign-in or run through it.
BUTTONS_VERIFIED = "2 November 2026"
BUTTON_NOTE = "the {button} button on the site's Connect menu works in {client} (verified by Gustav on " + BUTTONS_VERIFIED + ")"
# n82: Gustav decided on 2 November 2026 that VS Code and Cursor are no longer marked Experimental (he verified them; their
# sign-in and tool runs at /mcp/connect were on 27 October 2026), and neither is Lovable, whose flow ran live on
# 30 October 2026 (docs/LOVABLE-END-TO-END.md). Claude Code (not tried) and Glama are unchanged.
CLIENTS_DECIDED = "2 November 2026"
DECIDED_NOTE = "status set by Gustav on " + CLIENTS_DECIDED
CLIENTS = (
    ClientStatus("Claude", "hosted, via /mcp (the connector)", "/mcp", "Tested end to end", "26 October 2026",
                 "the live runs of 26 and 27 October 2026; on 26 November 2026 also added as a custom connector at "
                 "/mcp/connect (Krusgraph's approval page, then Microsoft's consent with the verified publisher)"),
    ClientStatus("VS Code", "hosted, via /mcp/connect", "/mcp/connect", "Tested end to end", "27 October 2026",
                 CONNECT_NOTE + "; " + BUTTON_NOTE.format(button="Add to VS Code", client="VS Code") + "; " + DECIDED_NOTE),
    ClientStatus("Claude Code", "hosted, via /mcp/connect", "/mcp/connect", "Experimental", note=CONNECT_NOTE + "; not tried yet"),
    ClientStatus("Cursor", "hosted, via /mcp/connect", "/mcp/connect", "Tested end to end", "27 October 2026",
                 CONNECT_NOTE + "; " + BUTTON_NOTE.format(button="Add to Cursor", client="Cursor") + "; " + DECIDED_NOTE),
    ClientStatus("Glama", "hosted, via /mcp/connect", "/mcp/connect", "Experimental", "27 October 2026",
                 CONNECT_NOTE + "; signed in with its client ID metadata document, connection test Healthy, 27 October 2026"),
    ClientStatus("Lovable", "via the GraphQL API that create_backend makes", "", "Tested end to end",
                 note="Lovable's own Microsoft Fabric connector reads the API; a Lovable app read shop_api live on 30 October 2026; "
                      "the chain is in docs/LOVABLE-END-TO-END.md; " + DECIDED_NOTE),
    ClientStatus("Lovable", "via MCP (/mcp/connect)", "/mcp/connect", "Tested end to end", "30 October 2026",
                 "signed in and ran plan, check and creates on 30 October 2026 (Entra sign-in through Krusgraph's OAuth with dynamic "
                 "client registration, from a phone: plan_backend, validate_plan, create_backend, create_semantic_model, create_report); "
                 + DECIDED_NOTE),
)
# derived, for the hub and the /mcp/connect sentence: the clients that have signed in and run tools
CLIENTS_TESTED = {c.name: (c.path, c.works_since) for c in CLIENTS if c.works_since and c.path}
WHERE_YOU_BUILD = ("Claude", "VS Code", "Cursor")       # the MCP clients the hub names, in this order; Lovable comes last


def source_word(tested: bool) -> str:
    return "tested end to end" if tested else "experimental"


def build_word(tool: str) -> str:
    """"creates" only for what has been created live on the hosted service (in the live run or, LATER_LIVE, after it),
    "updates" for what has only been updated in place there; "draft" for the rest, whose tools ran live only as drafts
    or dry runs, or not yet."""
    s = STATUS[tool]
    if s.kind == CREATES and (tool in LATER_LIVE or (s.live and not s.dry_run_only)):
        return "updates" if tool in LIVE_RUN_PARTLY else "creates"     # create_backend: live only as an update in place (n30)
    return "draft"


def clients_tested_at(path: str) -> list[tuple[str, str]]:
    """(client, date) for the clients recorded at one address, the hub's clients first, in its order, then the others."""
    rank = {c: i for i, c in enumerate(WHERE_YOU_BUILD)}
    names = sorted((c for c, (where, _) in CLIENTS_TESTED.items() if where == path), key=lambda c: (rank.get(c, len(rank)), c))
    return [(c, CLIENTS_TESTED[c][1]) for c in names]


def clients_working(registration_on: bool) -> list[str]:
    """The MCP clients the site names as working with the hosted service, in WHERE_YOU_BUILD order."""
    return [c for c in WHERE_YOU_BUILD if c in CLIENTS_TESTED and (CLIENTS_TESTED[c][0] == "/mcp" or registration_on)]


def connect_sentence() -> str:
    """What the site says about /mcp/connect: the clients that have been tried there, each under its own status word from
    CLIENTS. The word comes first, so a client cannot read as tested end to end before its row says so (n30); n82: VS Code,
    Cursor and Lovable are Tested end to end by Gustav's decision of 2 November 2026, Glama stays Experimental."""
    seen = clients_tested_at("/mcp/connect")
    if not seen:
        return "Experimental: " + CONNECT_NOTE + "; not tried with a client yet"
    status = {c.name: c.status for c in CLIENTS if c.path == "/mcp/connect"}

    def by_date(pairs, verb):
        groups: dict[str, list[str]] = {}
        for n, d in pairs:
            groups.setdefault(d, []).append(n)
        return _listed(f"{_listed(names)} {verb + ' here ' if i == 0 else ''}on {d}" for i, (d, names) in enumerate(groups.items()))
    tested = [(n, d) for n, d in seen if status.get(n) == "Tested end to end"]
    other = [(n, d) for n, d in seen if status.get(n) != "Tested end to end"]
    parts = []
    if tested:
        parts.append(f"Tested end to end: {by_date(tested, 'signed in and ran tools')} ({DECIDED_NOTE})")
    if other:
        many = len(other) > 1
        parts.append(f"Experimental: {by_date(other, 'were tried' if many else 'was tried')}; "
                     f"{'they stay' if many else 'it stays'} Experimental until a full sign-in {'with each ' if many else ''}is confirmed")
    return "; ".join(parts)


# ------------------------------------------------------------------ the overview of tools, functions and clients -------
# One table on /docs, /docs.md and llms-full.txt (Gustav's brief of 28 October 2026), rendered from here: every hosted
# tool with its status and where it runs, the functions outside the hosted tools, and one row per client.

# the hosted tools the local stdio server (fabric_backend/mcp_server.py) has too; tests/test_capabilities.py locks it
LOCAL_TOOLS = ("list_tables", "plan_backend", "validate_plan", "sample_rows", "join_path", "data_dictionary", "dbt_schema",
               "analyze_schema", "suggest_relationships", "rayfin_connector", "create_views", "answer_query_draft",
               "semantic_model_draft", "ontology_draft", "silver_notebook_draft", "review_plan", "create_backend",
               "qlik_plan", "qlik_measures_draft", "qlik_reconcile_draft",       # Q2: the same three, the text stays local
               "analysis_plan", "analysis_notebook_draft")                      # AP2: the analysis pack, local first
if _changes_on():
    LOCAL_TOOLS += ("propose_change",)                                           # LFD5: with KRUSGRAPH_CHANGES=1 only

# what is not a hosted tool: (name, status word, where, what it is)
# n146, Gustav's decision of 7 November 2026: what ran against SQL Server 2022 in a container on 28 October 2026
# (docs/LOCAL.md) is Tried live with this note, because SQL Server is its real target; what did not run stays
# Experimental; the demo keeps its own wording.
LOCAL_TRIED_NOTE = "SQL Server 2022 in a container, 28 Oct 2026; not run from Windows/Claude Desktop yet"
LOCAL_TRIED_TOOLS = ("plan_backend", "validate_plan", "data_dictionary", "dbt_schema", "answer_query_draft")
FUNCTIONS = (
    ("`validate_plan` → `amount_levels`", TRIED, "hosted, local demo, library",
     "the total that doubles: header amounts a join with their line rows would repeat, with the line rows per header counted; "
     f"unit-tested, and run with synthetic data ({LOCAL_TRIED_NOTE})"),
    ("`plan_sql_server`", TRIED, "library",
     "`from fabric_backend import plan_sql_server`: plan, validate, data dictionary and dbt schema over ODBC from your own Python "
     f"({LOCAL_TRIED_NOTE})"),
    ("`fabric-backend demo`", "Experimental", "local demo",
     "the 20-minute demo on 127.0.0.1: SQL Server over ODBC, a folder of CSV / Excel files, a columns list (file or pasted), "
     "or the synthetic shop; step 1 ends with one of five answers; over ODBC run on 28 October 2026 against SQL Server 2022 in a container"),
    ("`fabric-backend-mcp`", TRIED, "local",
     "the local stdio MCP server over one ODBC connection string; " + ", ".join(f"`{t}`" for t in LOCAL_TRIED_TOOLS[:-1])
     + f" and `{LOCAL_TRIED_TOOLS[-1]}` ran ({LOCAL_TRIED_NOTE}); its other tools are Experimental: unit-tested, not run "
     "against a live SQL Server"),
    ("`plan_from` / `create`", "Experimental", "library", "the engine in a Fabric notebook (Spark catalog) or over any execute(sql)"),
    ("Claude plugin", "Planned", "—", "the connector with a skill and `/krusgraph` commands, built in the repository (`plugin/krusgraph`), not published; see *For agents*"),
    ("Databricks adapter", "Draft only", "library, local",
     "Unity Catalog metadata, informational constraints, and the `databricks_*` tools of the local server; see docs/DATABRICKS.md"),
)


def where(name: str) -> str:
    return "hosted, local" if name in LOCAL_TOOLS else "hosted"


def _plain_word(w: str) -> str:
    """A WORDS entry as the visitor pages say it (n234): experimental, draft, planned, the operator's switch, or nothing."""
    if w.startswith("Tested end to end"):
        return ""
    if w.startswith("Draft"):
        return "draft"
    if w.startswith(("Planned", "Available when")):
        return w[0].lower() + w[1:]
    return "experimental"                                  # Experimental, Tried live


def overview_md(registration_on: bool = True) -> str:
    """The table, as Markdown, for /docs and llms-full.txt. n234: plain words only (tool_status.plain); the test record,
    its dates and the docs/ files stay in docs/ and the tests. With client registration off (a server hosted elsewhere),
    the clients that would use /mcp/connect cannot sign in, and the table says so."""
    rows = ["| Tool | Status | Available |", "| --- | --- | --- |"]
    rows += [f"| `{t}` | {plain(t) or '—'} | {where(t)} |" for t in STATUS]
    rows += ["", "| Function or client | Status | Where |", "| --- | --- | --- |"]
    for n, w, at, what in FUNCTIONS:
        what = (what.replace(f" ({LOCAL_TRIED_NOTE})", "").replace(f"; unit-tested, and run with synthetic data", "; unit-tested")
                .replace("; see docs/DATABRICKS.md", ""))
        what = re.sub(r"; over ODBC run on [^;]*$", "", what)
        what = re.sub(r"; `plan_backend`.*$", "", what)                  # fabric-backend-mcp: the tools that ran, and when
        rows.append(f"| {n} | {(_plain_word(w) + ': ') if _plain_word(w) else ''}{what} | {at} |")
    for c in CLIENTS:
        status, at = _plain_word(c.status) or "—", c.where
        if c.path == "/mcp/connect" and not registration_on:
            status, at = "cannot sign in to this server: client registration is not switched on here", "hosted elsewhere"
        rows.append(f"| {c.name} (client) | {status} | {at} |")
    return "\n".join(rows)


def overview_words() -> set[str]:
    """The status words the table uses: always from WORDS."""
    used = {word(t) for t in STATUS} | {w for _, w, _, _ in FUNCTIONS} | {c.status for c in CLIENTS}
    return {next(w for w in WORDS if u.startswith(w) or u.lower().startswith(w.lower())) for u in used}
