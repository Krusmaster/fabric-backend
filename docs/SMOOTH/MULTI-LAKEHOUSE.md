# A workspace with several lakehouses: what Krusgraph does today (SM1, 20 November 2026)

This page reads the code and tests on `main` at `92bb936`. Nothing was created or read in Fabric. Three layouts are
common:

- **(a) One lakehouse per layer:** `bronze_lh`, `silver_lh`, `gold_lh`.
- **(b) One lakehouse per source:** `sap_lh`, `crm_lh`, and so on.
- **(c) Schemas inside one lakehouse:** today's `demo_lh`, with `dbo`, `sap_silver`, `sap_gold`.

`docs/MULTI-SOURCE.md` (26 October, n12) already said "design only" for several sources. This page brings that up to
date and adds layout (a).

## How the code is built, for all three layouts

| Fact | Where |
|---|---|
| A *source* is one item: a lakehouse, warehouse or SQL database | `tool_params.py:20`; `_resolve_source` in `server.py:330`, `platforms/fabric.py:63-96` |
| One SQL connection, to one database (`Database=<item>`) | `platforms/fabric.py:113-115` |
| A plan reads one schema through `INFORMATION_SCHEMA`; a foreign key into another schema is dropped | `server.py:441-455`; `schema.py:37,151` |
| SQL on Fabric uses two-part names (`[schema].[table]`); a three-part prefix exists only for Databricks' catalog | `dialects.py:34-42` |
| "A lakehouse source writes into itself" | `server.py:2699-2706` (`_write_info`) |
| A different target lakehouse only for a read-only source (mirrored database, warehouse, SQL database; n201) or a build in another workspace (n221) | `server.py:2706-2711`; `workload_api.py:2209-2213` |
| The MCP tools take `silver_schema` and `gold_schema`, not a target lakehouse | `tool_params.py:57-62`; `server.py:2914,3030,3282` |
| A notebook attaches one default lakehouse | `notebook.py:32-38` |
| The semantic model has one expression, `Sql.Database(endpoint, lakehouse)`: Direct Lake on SQL | `semantic_model.py:456` |
| The ontology binds to one item; the data agent has one data source | `ontology.py:226`; `data_agent.py:145-148,239-245` |
| Start, step 2: one usable source is preselected; with 2 or more, Next waits ("Choose a source first.") and nothing is suggested | `start_flow.py:255-257,301,420-421` |
| Editor: the source picker selects one item; "Target lakehouse" appears only for a read-only source | `ModelItemEditor.tsx:384-402`; `ModelItemViews.tsx:233-238` |

## What Microsoft documents (Microsoft Learn, opened 20 November 2026)

- **Cross-database T-SQL in one workspace.** "You can write cross database queries to warehouses and databases in the
  current active workspace", with three-part names such as `ContosoLakehouse.dbo.ContosoSalesTable`. Source: *Query the
  Warehouse or SQL analytics endpoint*, ms.date 2026-01-06, learn.microsoft.com/fabric/data-warehouse/query-warehouse.
  This works within one workspace, from one SQL endpoint connection.
- **Shortcuts.** "The shortcut can point to a folder location within the same item, across items within the same
  workspace, or even across items in different workspaces." Shortcuts in a lakehouse's **Tables** folder can link "to
  either a single table or a schema". Shortcut tables are read through the lakehouse's SQL analytics endpoint and by
  Direct Lake. "OneLake uses the identity of the calling user", except for Direct Lake over SQL and T-SQL in delegated
  mode, where "the calling item's owner's identity is passed". Schema shortcuts "can only be created in schema-enabled
  lakehouses". Source: *Unify data sources with OneLake shortcuts*, ms.date 2026-11-05,
  learn.microsoft.com/fabric/onelake/onelake-shortcuts.
- **Spark across lakehouses and workspaces.** Schema-enabled lakehouses let Spark SQL join tables with the four-part
  name `workspace.lakehouse.schema.table`. A schema shortcut "creates a new schema in your lakehouse that references
  Delta tables from another lakehouse". Source: *Lakehouse schemas*, ms.date 2026-02-24,
  learn.microsoft.com/fabric/data-engineering/lakehouse-schemas.
- **Direct Lake.** "Direct Lake on OneLake can use data from one or more Fabric data sources with Delta tables";
  "Direct Lake on SQL can use the data from a single Fabric data source". Shortcuts in a lakehouse can be the data
  source of semantic model tables. Source: *Direct Lake overview*, ms.date 2026-09-02,
  learn.microsoft.com/fabric/fundamentals/direct-lake-overview.

What this means for Krusgraph:

- A plan, a join check and one model over several sources all work without new Fabric features in one case: when the
  sources appear as **schemas of one lakehouse**, as schema shortcuts.
- That turns layouts (a) and (b) into layout (c), which already works one schema at a time.
- Three-part T-SQL inside one workspace is the second route, for reading and checking only.
- A model over several items without shortcuts needs Direct Lake on OneLake. Krusgraph writes Direct Lake on SQL today.

## Status per layout

Status words: **works**; **partial** (works with a workaround or only in part); **no**.

### (a) One lakehouse per layer: `bronze_lh`, `silver_lh`, `gold_lh`

| Capability | Status | Why |
|---|---|---|
| Plan | Partial | Each lakehouse can be planned on its own. Picking `bronze_lh` is a manual choice at step 2: no suggestion, and Next waits |
| Check joins across lakehouses | No | Two-part names on one connection. Not needed for (a), because the joins are inside bronze |
| Write silver to `silver_lh` and gold to `gold_lh` | **No** | A lakehouse source writes into itself, so silver and gold would land in `bronze_lh` under new schemas. A target exists only for read-only sources or another workspace, and even there silver and gold share one target |
| One model / ontology / agent over the gold layer | Partial | They read `silver_schema`/`gold_schema` inside the source item. When the build moves elsewhere (n221), only the data agent is pointed at the target (`server.py:2606-2611`); the model and the ontology are not, unverified |

### (b) One lakehouse per source: `sap_lh`, `crm_lh`

| Capability | Status | Why |
|---|---|---|
| Plan | Partial | One source per plan; two plans cannot be merged. The bare table name is the key everywhere |
| Check joins across lakehouses | No | Rules X0-X3 for links across items exist only as a design (`docs/MULTI-SOURCE.md`) |
| Write silver/gold | Works per source | Each lakehouse gets its own silver and gold, in itself |
| One model / ontology / agent / data product over both | **No** | One `Sql.Database` expression, one ontology item binding, one agent data source, one Model item per product. Workaround: shortcuts into one lakehouse, then plan that one |

### (c) Schemas inside one lakehouse: `demo_lh`

| Capability | Status | Why |
|---|---|---|
| Plan | Works, one schema at a time | `plan_backend` without a schema asks which (`server.py:890-895,964-973`) |
| Check joins | Works inside one schema | A foreign key to another schema is dropped (`schema.py:151`) |
| Write silver/gold | Works | `silver_schema`/`gold_schema` in the same lakehouse; the pipeline's own parameters are read back (WB2, `layer_schemas.py`) |
| One model / ontology / agent | Partial | Over one layer schema. Two source schemas (`sap_silver` + `crm_silver`) cannot be combined into one output |

## Gaps, in the order they unlock value

| # | Gap | Layout | Effort |
|---|---|---|---|
| G1 | Start's step 2: suggest the source by name rules (`bronze`/`raw`/`landing` = the source in (a); one per source in (b)) and say what it will do with the others | a, b | S |
| G2 | A target lakehouse for a lakehouse source in the same workspace: `target_lakehouse` (and `gold_lakehouse`) on the pipeline, silver and gold tools; the source is read through its OneLake path, as n201 already does for mirrors | a | M |
| G3 | Model, ontology and agent read the lakehouse the build wrote, in every case where the build moved (n201, n221, G2). Verify first | a | S-M |
| G4 | Plan over several schemas of one item: the table key becomes `schema.table` in infer, graphs and the generators; join checks across schemas in one T-SQL connection | b via shortcuts, c | M-L |
| G5 | Schema shortcuts as a build step: from each source lakehouse's silver schema into one product lakehouse. Dry run first, created on a second tap, only in a schema-enabled lakehouse | b | M |
| G6 | Matching across sources by rules (COMBINE-SOURCES.md): counted key overlap, normalised identifiers, conformed dimensions | b, c | M-L |
| G7 | One semantic model over several items without shortcuts (Direct Lake on OneLake); one ontology over several items (Microsoft has not documented multi-item bindings) | b | L, later |
| G8 | Cross-item join check with three-part T-SQL in one workspace (X3 in MULTI-SOURCE.md), for reading without shortcuts | b | M |

**No test today plans or joins across several lakehouses or schemas.** Related tests:
- `tests/test_n169_clickable_cards.py`: choosing a schema.
- `tests/test_wb2_layer_schemas.py`: layer schemas.
- `tests/test_n201_mirrored.py` and `tests/test_n221_build_in.py`: target lakehouse and build-in.
- `tests/test_wb15_click_through.py::test_one_usable_source_or_workspace_is_preselected_and_next_works`: two sources mean
  no preselection.

PLAN.md (SM5) adds the synthetic multi-lakehouse fixture that the gaps are measured against.
