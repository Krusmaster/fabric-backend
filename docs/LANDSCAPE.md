# MCP landscape: what other servers do, and how ideas from them are reused

Internal working note, not linked from the site. Round n118, 6 November 2026. It records which MCP servers around
Microsoft Fabric, Power BI, OneLake, dbt, data quality, data catalogs, lineage and MCP Apps were looked at, what each
does that Krusgraph's tools do not, and a verdict per server. The process at the end is how this is kept up to date and
how an idea or a line of code from one of them may ever reach this repository. `docs/ECOSYSTEM-WATCHLIST.md` stays the
register of servers a user may be pointed at; `docs/COMPANION-MCP.md` stays Krusgraph's position beside Microsoft's
servers. This file is the wider scan behind both.

Krusgraph's side of each comparison is its 39 tools as listed in `fabric_backend/tool_status.py` on this date. "Does
not" below means only that none of those tools does the thing; it says nothing about which is better.

## How this was read

| Source | Reached | How it was used |
| --- | --- | --- |
| glama.ai/mcp/servers | **No.** The session's proxy refused the tunnel (`CONNECT tunnel failed, response 403`). The network policy was not changed. | Not used. Nothing in this file comes from Glama. |
| Official MCP Registry, `registry.modelcontextprotocol.io/v0/servers?search=…` | Yes | Searched for fabric, powerbi, power bi, onelake, dbt, great expectations, data quality, data-quality, quality, expectations, catalog, datahub, openmetadata, lineage, openlineage, purview, unity, soda, montecarlo, atlan, collibra, dataplex, semantic model, data contract, dax, tmdl, mcp apps, mcp-ui. Registry text is quoted below as **listing**. |
| GitHub search API (`gh api search/repositories`) | Yes | Candidate repositories, stars, GitHub's licence detection and last push. Used to find repositories only, never as the licence. |
| github.com web pages, `api.github.com/repos/…` | **No** (HTTP 403; the repository endpoints are not enabled for this session) | Not used. |
| `git clone --depth 1` through the session's git proxy | Yes | Each repository below was cloned into a scratch directory outside this repository, read, and not built, installed or run. The licence column is the `LICENSE` file at the commit given; tool names were read in the source at that commit. For `microsoft/mcp` and `open-metadata/OpenMetadata` only the server's directories were checked out (sparse). |
| Vendor sites (semanticops.dev, docs.datakitchen.io, getcollate.io, docs.getdbt.com, learn.microsoft.com) | Not attempted | Nothing in this file comes from them. |

"Last commit" is the newest commit on the default branch at clone time (6 November 2026), not GitHub's "pushed at".
"Tools (read in code)" lists names found in the source; where a README or the registry gives a different number, that
is in the **Listing / README** column, and the two are not reconciled further.

## Servers reviewed

33 repositories at a pinned commit: 28 MCP servers and 5 that are a specification, SDKs or frameworks for MCP Apps or a
skill pack. Verdicts: **build** (write it ourselves from the idea, no code taken), **alongside** (the user runs that
server next to Krusgraph in the same client; no code or dependency here), **skip**.

### Microsoft Fabric and OneLake

| Server | Owner | Licence (LICENSE file) | Last commit | Tools (read in code) | Listing / README | What it does that Krusgraph does not | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [Fabric MCP Server](https://github.com/microsoft/mcp/tree/main/servers/Fabric.Mcp.Server) (`servers/Fabric.Mcp.Server` + `tools/Fabric.Mcp.Tools.*`) | Microsoft | MIT, "Copyright 2025 (c) Microsoft Corporation." | `42c66a2`, 2026-11-06 (monorepo) | Toolsets `core` (workspaces, items, capacities, item definition get/update, job runs, schedules, OneLake catalog search), `docs` (platform and item API specs, item definitions, best practices, examples), `onelake` (files, blobs, directories, tables, shortcuts to ADLS Gen2, S3, GCS, Dataverse, OneDrive/SharePoint, OneLake data access roles), `datafactory` (pipelines, dataflows, run, query) | Registry `com.microsoft/microsoft-fabric` 1.4.0: "MCP tools for interacting with Microsoft Fabric" | Generic item create/update/delete, OneLake file I/O, shortcuts, data access roles, catalog search, bundled API specifications | **alongside**: already the pairing in `docs/COMPANION-MCP.md` |
| [fabric-rti-mcp](https://github.com/microsoft/fabric-rti-mcp) | Microsoft | MIT, "Copyright (c) Microsoft Corporation." | `3c765f9`, 2026-09-24 | `kusto_*` (query, command, describe, sample, graph query, query plan, inline ingest), `eventstream_*` (create, build, definitions), `activator_*` (create trigger, list), `map_*` | — | KQL on eventhouses, Eventstream, Activator, maps | **alongside**: eventhouses are outside Krusgraph's sources |
| [skills-for-fabric](https://github.com/microsoft/skills-for-fabric) | Microsoft | MIT, "Copyright (c) 2026 Microsoft Corporation" | `f8fac11`, 2026-11-05 | Not a server: agent skills (e.g. `semantic-model-authoring`, `onelake-catalog-cli`, `ontology-cli`, `e2e-medallion-architecture`, `powerbi-report-cli`) and scripts that register the Fabric MCP Server | GitHub: "A collection of skills and MCP systems…" | Packaged how-to knowledge for CLI agents across many Fabric workloads | **skip**: Krusgraph ships its own plugin (`plugin/krusgraph`); nothing to take |
| [Fabric-Analytics-MCP](https://github.com/santhoshravindran7/Fabric-Analytics-MCP) | santhoshravindran7 (individual) | MIT, copyright line "Copyright (c) 2025 Microsoft Fabric Analytics MCP Server" (a project name, not a person or company) | `6781eb2`, 2025-12-23 | About 82 `server.tool` names: item, notebook and dataflow CRUD, Livy sessions and statements, Spark application monitoring, Synapse-to-Fabric migration, capacity assignment | README: "52 Total Tools" | Runs Spark and Livy work, monitors runs, migrates Synapse workspaces | **skip**: outside Krusgraph's scope; the copyright holder is unclear, so code would need the owner identified first |
| [fabric-dw-mcp-cli](https://github.com/sdebruyn/fabric-dw-mcp-cli) | Sam Debruyn | MIT, "Copyright (c) 2026 Sam Debruyn"; vendors an MIT `html_query_plan` asset | `a85c04c`, 2026-09-09 | About 60: `execute_sql`, query plans, running and long queries, `kill_session`, audit settings, restore points, snapshots, permissions, masked columns, security policies, `get_table_health_metrics`, `generate_dbt_profile` | — | Warehouse operations and monitoring, security inventory (RLS policies, masking), a dbt `profiles.yml` for Fabric | **alongside** for warehouse operations; the dbt-profile idea is noted under idea 1 |
| [Force-Fabric-MCP-Server](https://github.com/tmdaidevs/Force-Fabric-MCP-Server) | Tobi Muller | MIT, "Copyright (c) 2026 Tobi Muller" | `5d2a297`, 2026-04-27 | 33: `*_optimization_recommendations`, `*_fix`, `*_auto_optimize` for lakehouse, warehouse, eventhouse, semantic model and gateway; `lakehouse_run_table_maintenance` | — | Performance recommendations, and changes that apply them | **skip**: performance is outside Krusgraph's scope, and "fix" writes go against its create-only, dry-run-first tools |

### Power BI

| Server | Owner | Licence (LICENSE file) | Last commit | Tools (read in code) | Listing / README | What it does that Krusgraph does not | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [powerbi-modeling-mcp](https://github.com/microsoft/powerbi-modeling-mcp) | Microsoft | Repository: MIT, "Copyright (c) Microsoft Corporation." The repository has **no source code**; the npm package is under `EULA.txt`, which the server makes the user accept (`accept_eula`) | `2b25def`, 2026-09-29 | Not readable in code. README table: connection, database (TMDL import/export, deploy), transaction, model, table, column, measure, relationship, DAX query, trace, partition, hierarchy, calculation group, security role, perspective, named expression, function, culture, translation `*_operations` | Registry `com.microsoft/powerbi-modeling-mcp` 1.0.1 | Edits an existing model: measures, DAX run and validate, RLS roles, translations, transactions | **alongside**: already in `docs/COMPANION-MCP.md` |
| [powerbi-mcp](https://github.com/sulaiman013/powerbi-mcp) | Sulaiman Ahmed | MIT, "Copyright (c) 2025 Sulaiman Ahmed" | `977b4d1`, 2026-07-23 | Names include `desktop_connect`, `execute_dax`, `dax_lint`, `dax_suggest_rewrite`, `audit_star_schema`, `audit_naming`, `audit_ai_readiness`, `bpa_validate_rules`, `find_unused_objects`, `impact_analysis`, `cross_workspace_lineage`, `batch_rename_*`, `desktop_set_rls_role` | README: "82 tools" plus resources, prompts and completion | Model audits (star schema, naming, Best Practice Analyzer rules), DAX lint, unused objects, Desktop editing | **alongside** for model audits after `create_semantic_model` |
| [horizun-pbi-mcp](https://github.com/HorizunGroup/horizun-pbi-mcp) | HorizunGroup | Apache-2.0, with a `NOTICE` ("Copyright 2026 HorizunGroup and Horizun PBI MCP contributors") | `e2ff437`, 2026-11-03 | 140 `pbi_*` names: PBIP/Desktop model build, audit and repair; report pages, visuals, themes; `pbi_backup_pbip_project`; `pbi_check_contract`; `pbi_find_tool` over tools a local profile hides | README: "140 tools"; `docs/TOOL_CATALOG.md` marks each tool read-only or destructive | Report visuals and pages, Desktop/PBIP editing, a backup and journal before changes, a tool profile that hides destructive tools | **alongside** for Desktop work; the profile idea is idea 3 |
| [SemanticOps MCP](https://github.com/maxanatsko/mcp-engine-public) (formerly MCP Engine) | Maxim Anatsko | **Proprietary**: `LICENSE.txt` "SemanticOps MCP License (Proprietary) … All rights reserved." GitHub shows NOASSERTION | `dd9e70a`, 2026-10-16 | No source in the repository (binaries in releases) | README: "Rollback mistakes. Test before deploy. Control what AI can change." | Per README: rollback and pre-deploy tests for Desktop models (not verified) | **skip**: proprietary, ideas only |
| [pbixray-mcp-server](https://github.com/jonaolden/pbixray-mcp-server) | jonaolden | MIT, "Copyright (c) 2025 jonaolden" | `3f44779`, 2025-05-26 | 14: `load_pbix_file`, `get_tables`, `get_relationships`, `get_dax_measures`, `get_power_query`, `get_model_size`, `get_statistics`, `get_table_contents`, … | — | Reads a `.pbix` file offline | **skip**: no commit since May 2025; Krusgraph reads TMDL from Fabric |
| [powerbi-mcp](https://github.com/gurvinder-dhillon/powerbi-mcp) | Gurvinder Dhillon | MIT, "Copyright (c) 2026 Gurvinder Dhillon" | `0407c00`, 2026-02-04 | 7: `get_workspaces`, `get_datasets`, `get_dataset`, `get_parameters`, `get_refresh_history`, `get_reports`, `query_dataset` | Registry `io.github.gurvinder-dhillon/powerbi-mcp` 0.1.2 | DAX on a dataset, refresh history | **skip**: Fabric IQ MCP (Microsoft-hosted) covers DAX with RLS applied |
| [pbix-lineage / pbix-atlas](https://github.com/fabienfrfr/pbix-lineage) | Fabien Furfaro | MIT, "Copyright (c) 2026 Fabien FURFARO" | `3b489b6`, 2026-07-29 | FastAPI routes mounted as tools (`FastMCP.from_fastapi`): `build_graph`, `search_nodes`, `get_upstream`, `get_downstream`, `get_lineage_tree`, `export_graph`, `get_source_schema`, graph invalidation; M-query and DAX parsers in code | Registry `io.github.fabienfrfr/pbix-lineage`: "Bidirectional data lineage graph for Power BI (.pbix) files, from source to display"; README names it pbix-atlas | Column-to-visual lineage inside a report, through Power Query and DAX | **alongside** for `.pbix` files; column lineage is idea 5 |
| [pbi-context](https://github.com/Osc2405/pbi-context) | Oscar Eduardo Rosero | MIT, "Copyright (c) 2025 Oscar Eduardo Rosero" | `a7135a0`, 2026-08-03 | 10 (hand-written JSON-RPC over stdio): `list_tables`, `get_table`, `get_measure`, `search_measures`, `search_columns`, `get_relationships`, `get_measure_dependencies`, `find_measure_usages`, `find_column_usages`, `diff_impact` | — | Measure dependency graph and column usage across measures, from PBIP/TMDL folders; impact of a diff | **build** (idea 5), from the TMDL Krusgraph already reads; no code taken |

### dbt

| Server | Owner | Licence (LICENSE file) | Last commit | Tools (read in code) | Listing / README | What it does that Krusgraph does not | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [dbt-mcp](https://github.com/dbt-labs/dbt-mcp) | dbt Labs | Apache-2.0, "Copyright 2025 dbt Labs" | `0671ec0`, 2026-11-05 | 61 names in `tools/tool_names.py`: dbt CLI (`build`, `run`, `test`, `compile`, `show`, …), Discovery API (models, sources, exposures, `get_lineage`, `get_column_lineage`, model health and performance), Semantic Layer (`list_metrics`, `query_metrics`, …), Admin API (jobs, runs, artifacts), codegen (`generate_source`, `generate_model_yaml`, `generate_staging_model`), `text_to_sql`, `execute_sql`; an MCP App `ui://dbt-mcp/get-lineage` (`text/html;profile=mcp-app`) fetched from a CDN | — | Runs dbt, reads the dbt Platform, shows lineage as an MCP App in the client | **alongside** for running Krusgraph's `dbt_schema project=true` draft; the MCP App is idea 2 |
| [dbt-doctor](https://github.com/Astoriel/dbt-doctor) | Astoriel | MIT, "Copyright (c) 2024 dbt-doctor contributors" | `f55dbc9`, 2026-09-29 | 12: `audit_project`, `check_test_coverage`, `profile_model`, `suggest_tests`, `detect_schema_drift`, `update_model_yaml`, `generate_model_docs`, `analyze_dag`, `execute_query`, … | GitHub: "AI-driven quality & governance MCP Server for dbt projects" | Test coverage of an existing dbt project; tests suggested from data statistics; YAML written in place | **skip** as code; coverage reporting is folded into idea 1 |
| [dbt-lineage-viewer](https://github.com/sipemu/dbt-lineage-viewer) | Simon Müller | MIT, "Copyright (c) 2025 Simon Müller" | `0ff0235`, 2026-11-06 | 10 (Rust): `summary`, `search_models`, `lineage`, `impact`, `get_model_details`, `read_model_sql`, `column_upstream`, `column_downstream`, `lineage_bundle`, `propose_test` (not_null, unique, accepted_values, relationships, each with a rationale) | Registry `io.github.sipemu/dbt-lineage`: "no warehouse or dbt compile" | Column lineage over dbt SQL files, impact inside a dbt project | **skip**: Krusgraph does not read dbt projects; a rule per proposed test is already how Krusgraph reports keys |
| [dbt-plan](https://github.com/PresentJay/dbt-plan) | PresentJay | Apache-2.0 | `a0b8875`, 2026-11-04 | 2: `plan` (the DDL a dbt change will run, from files), `snapshot` | Registry `io.github.PresentJay/dbt-plan` 0.18.6 | Predicts the DDL of a dbt change | **skip**: Krusgraph does not run dbt |
| [dbt-mcp-server](https://github.com/us-all/dbt-mcp-server) | us-all | MIT, "Copyright (c) 2026 us-all" | `3af1107`, 2026-07-10 | 27: `dbt-*` over manifest, run_results, sources and catalog (coverage, failed tests, slow models, freshness, SLA), `dq-*` over data-quality result tables, `search-tools`; categories switched with `DBT_TOOLS` / `DBT_DISABLE` | Registry `io.github.us-all/dbt` 1.0.7 | Reads dbt run results; a tool-search meta tool; tool categories turned on and off by environment | **skip** as code; the category switch is idea 3 |

### Data quality

| Server | Owner | Licence (LICENSE file) | Last commit | Tools (read in code) | Listing / README | What it does that Krusgraph does not | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [gx-mcp-server](https://github.com/davidf9999/gx-mcp-server) | David Front | MIT, "Copyright (c) 2025 David Front" | `57a934f`, 2025-08-25 (GitHub "pushed at" says 2025-12-14, another branch) | 7: `load_dataset`, `create_suite`, `add_expectation`, `run_checkpoint`, `get_validation_result`, `get_version`, `ping` | GitHub: "exposes Great Expectations data quality tools" | Builds and runs Great Expectations suites | **build** (idea 1): a suite drafted from the plan, written from Great Expectations' documentation; no code taken |
| [DataOps TestGen](https://github.com/DataKitchen/dataops-testgen) | DataKitchen | Apache-2.0, with a `NOTICE` ("Copyright 2024 DataKitchen, Inc.") | `9a4accb`, 2026-10-21 | MCP server inside the TestGen application, 108 `tool_wrapper` registrations in `testgen/mcp/server.py`: profiling runs, hygiene issues, `generate_tests`, `run_tests`, monitors (freshness, volume, schema), quality scores and scorecards, PII categories, `export_contract`, notifications. A "source data protection" mode: at `strict`, tools that return row values are not registered | README: "a REST API and an MCP server" in the open-source edition | Profiling, generated test suites on a schedule, anomaly monitors, scorecards; a server-wide switch that removes tools returning row values | **alongside** for profiling and monitoring; the protection switch is idea 3 |
| [OpenDQV](https://github.com/OpenDQV/OpenDQV) | Sunny Sharma, BGMS Consultants Limited and contributors | MIT | `b54c700`, 2026-11-03 | 15: `validate_record`, `validate_batch`, `get_contract`, `list_contracts`, `compare_contracts`, `create_contract_draft`, `get_contract_jsonschema`, quality metrics and trends, audit events | GitHub: "contract-driven data quality validation" | Validates records against a contract at write time | **skip**: write-time validation is outside Krusgraph; `domain_draft` already drafts ODCS contracts |

### Data catalogs and lineage

| Server | Owner | Licence (LICENSE file) | Last commit | Tools (read in code) | Listing / README | What it does that Krusgraph does not | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [mcp-server-datahub](https://github.com/acryldata/mcp-server-datahub) | Acryl Data | Apache-2.0, "Copyright 2025 Acryl Data, Inc." | `e4de4c0`, 2026-11-05 | `search`, `get_entities`, `get_lineage`, `get_lineage_paths_between`, `get_dataset_queries`, `list_schema_fields`, `get_aspect_history`, `get_dataset_assertions`, `search_documents`, `grep_documents`, `get_me`; mutation tools (tags, terms, owners, domains, description, structured properties, `save_document`) registered only with `TOOLS_IS_MUTATION_ENABLED=true` | GitHub: "The official Model Context Protocol (MCP) server for DataHub" | A catalog; writes descriptions, terms and owners; the lineage path between two datasets | **alongside**: a client can carry `data_dictionary`'s text into DataHub through this server; the mutation switch is idea 3 |
| [OpenMetadata MCP](https://github.com/open-metadata/OpenMetadata/tree/main/openmetadata-mcp) (`openmetadata-mcp`) | Collate / OpenMetadata | Repository root: Apache-2.0. **The `openmetadata-mcp` directory has its own `LICENSE`: Collate Community License Agreement 1.0**, which excludes offering a competing hosted service. GitHub shows Apache-2.0 for the repository | `e906dd7`, 2026-11-06 | 21 in `tools.json`: `search_metadata`, `semantic_search`, `get_entity_details`, `get_entity_lineage`, `create_lineage`, `create_entity`, `patch_entity`, `get_test_definitions`, `create_test_case`, `root_cause_analysis`, `sparql_query`, `entity_neighborhood`, `shacl_validate`, `ontology_describe`, … | Registry `io.github.open-metadata/openmetadata-mcp` 1.1.1: "21 read and write tools" (agrees with the code) | Catalog writes, test cases in the catalog, root-cause analysis, SPARQL and SHACL over the catalog's graph | **alongside**; code: ideas only (not an allowed licence) |
| [openmetadata-mcp-server](https://github.com/us-all/openmetadata-mcp-server) | us-all | MIT, "Copyright (c) 2026 us-all" | `81d7309`, 2026-07-10 | 173: CRUD for every OpenMetadata entity, `add-lineage`, `lineage-impact`, `validate-data-contract`, `run-data-contract-validation`, `run-test-suite`, `quality-rollup`, `search-tools` | Registry `io.github.us-all/openmetadata` 1.16.10 | As the official server, as a community wrapper | **skip**: point users at the official server |
| [Marmot](https://github.com/marmotdata/marmot) | Charlie Haley | MIT, "Copyright (c) 2024 Charlie Haley" | `633e9bd`, 2026-11-05 | 11 in `internal/mcp/server.go`: `discover_data`, `trace_lineage`, `find_ownership`, `lookup_term`, `list_queryable_sources`, `query_data`, `manage_tags`, `manage_owners`, `update_documentation`, `explore_data_products`, `explore_teams` | GitHub: "The open-source context layer for your AI" | A catalog with lineage; 71 plugin directories under `plugins/`, none for Fabric or Power BI | **skip**: no Fabric overlap |
| [ade-catalog](https://github.com/rbutinar/ade-catalog) | Roberto Butinar | Apache-2.0, with a `NOTICE` ("Copyright 2024-2026 Roberto Butinar") | `2a21e0e`, 2026-10-26 | 7 over HTTP JSON-RPC: `search_catalog`, `get_object_detail`, `get_lineage`, `list_platforms`, `list_views`, `get_graph_stats`, `get_dashboard_stats` | README: "A local, self-hostable metadata catalog for Databricks + Power BI" (preview) | Cross-platform lineage between Databricks and Power BI from exported files | **skip**: preview, file-based; nothing Krusgraph would build or point to yet |
| [mcp-server-unitycatalog](https://github.com/ognis1205/mcp-server-unitycatalog) | Shingo Okawa | MIT text (the file has no "MIT License" title line; GitHub detects MIT), "Copyright (c) 2025 Shingo OKAWA" | `0933eba`, 2025-03-29 | 4: `uc_list_functions`, `uc_get_function`, `uc_create_function`, `uc_delete_function`, plus each Unity Catalog function in the configured schema exposed as a tool | — | Runs Unity Catalog functions as tools | **skip**: no commit since March 2025, and about functions, not tables |
| [purview-dlm-mcp](https://github.com/microsoft/purview-dlm-mcp) | Microsoft | MIT, "Copyright (c) Microsoft Corporation." | `f5cdcb9`, 2026-10-31 | 5: `run_powershell`, `get_execution_log`, `ask_learn`, `create_issue`, `submit_feedback` | — | Purview data lifecycle management (retention) through PowerShell | **skip**: retention, not catalog or lineage |

**OpenLineage.** No MCP server for OpenLineage or Marquez was found: the registry returned nothing for "openlineage"
and GitHub search found only projects that mention it. OpenLineage itself (OpenLineage/OpenLineage) is Apache-2.0 per
GitHub's metadata; its `LICENSE` file was not opened in this round, so that is **not verified**. The idea that follows
from it is idea 4.

### MCP Apps (UI in the client)

| Project | Owner | Licence (LICENSE file) | Last commit | What it is (read in code) | Listing / README | What it does that Krusgraph does not | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [ext-apps](https://github.com/modelcontextprotocol/ext-apps) | Model Context Protocol (LF Projects) | **Mixed**: the file says the project is moving from MIT to Apache-2.0; new code is Apache-2.0, some older contributions stay MIT, documentation is CC-BY-4.0. GitHub shows NOASSERTION | `19256f5`, 2026-11-04 | Specification (`specification/2026-01-26`, `draft`) and SDK; `RESOURCE_MIME_TYPE = "text/html;profile=mcp-app"` in `src/constants.ts`; about 25 example servers | GitHub: "Official repo for spec & SDK of MCP Apps protocol" | An interactive view rendered in the client from a `ui://` resource linked to a tool | **build** (idea 2), from the specification; no SDK dependency until reviewed |
| [mcp-ui](https://github.com/MCP-UI-Org/mcp-ui) | Ido Salomon / MCP-UI-Org | Apache-2.0, "Copyright 2025 Ido Salomon" | `2b10490`, 2026-07-08 | Client renderers and server helpers for UI resources | — | Same area, an earlier SDK | **skip**: the ext-apps specification is the one to follow |
| [Skybridge](https://github.com/alpic-ai/skybridge) | Alpic | MIT, "Copyright (c) 2025 Alpic" | `9afa5fa`, 2026-10-29 | TypeScript framework for MCP Apps and ChatGPT apps | — | A framework | **skip**: Krusgraph is Python; it would be a new dependency |
| [mcp-use](https://github.com/mcp-use/mcp-use) | pietrozullo / mcp-use | MIT, "Copyright (c) 2025 pietrozullo"; its `skills/` folders carry Apache-2.0 files | `ac0b6a5`, 2026-11-05 | TypeScript and Python framework for servers, clients, MCP Apps and an inspector | — | A framework | **skip**: same reason |

### Seen in a listing, not opened

Registry entries without a repository, or not cloned this round: `io.github.mbrummerstedt/powerbi-analyst-mcp`
("Browse Power BI workspaces, run DAX queries…", no repository in the entry), `io.github.asklokesh/powerbi-mcp-server`,
`io.github.txn2/mcp-datahub`, `ai.contentsweep/data-quality-gate` (remote). No registry or GitHub hit was an MCP server
for Soda, Monte Carlo, Atlan, Collibra or Purview's Unified Catalog. Earlier readings of datumnova/ms-fabric-mcp and
Jasuni69/ms-core-mcp (no licence file), mkoziel2000/mcp-fabric-api (AGPL-3.0) and Augustab/microsoft_fabric_mcp (MIT)
are in `docs/ECOSYSTEM-WATCHLIST.md` and were not re-read.

## Licence findings

- **OpenMetadata MCP**: the repository is Apache-2.0, but the `openmetadata-mcp` directory carries the Collate Community
  License 1.0, which excludes offering a competing hosted service. GitHub's metadata shows only Apache-2.0. Ideas only.
- **SemanticOps MCP** (maxanatsko/mcp-engine-public): proprietary EULA, all rights reserved; GitHub shows NOASSERTION.
  Ideas only.
- **powerbi-modeling-mcp**: the MIT `LICENSE` covers a repository that holds only documentation; the server people run
  is an npm binary under Microsoft's EULA. Nothing to copy.
- **ext-apps**: mixed MIT and Apache-2.0 during a relicensing, documentation CC-BY-4.0; GitHub shows NOASSERTION. Both
  are allowed, but which applies to a given file is not clear from the file alone; keep both notices if anything is
  ever taken.
- **Fabric-Analytics-MCP**: MIT, but the copyright line names "Microsoft Fabric Analytics MCP Server", not a person or a
  company, in a personal repository. The holder would need to be identified before reuse.
- **mcp-server-unitycatalog**: MIT text without its title line; not a problem, noted because a scanner may not see it.
- No GPL or AGPL code turned up in the servers read this round (the AGPL server from the watchlist was not re-read).

## Top five ideas

Ranked by value to Krusgraph against effort. Each is an idea only: nothing is built until Gustav approves it (see
Process), and none needs code from the servers above.

| # | Idea | Seen in | Value | Effort | Why this rank |
| --- | --- | --- | --- | --- | --- |
| 1 | **Checks for more than dbt**: draft a Great Expectations suite (and, as a later step, Soda checks) from the checked plan, the way `dbt_schema` drafts dbt tests: unique and not null on keys, referential checks on relationships, with the rule behind each check; optionally a Fabric dbt `profiles.yml` next to `dbt_schema project=true` | gx-mcp-server (`create_suite`, `add_expectation`), dbt-doctor (`suggest_tests`, `check_test_coverage`), dbt-lineage-viewer (`propose_test` with a rationale), TestGen (`generate_tests`), fabric-dw-mcp-cli (`generate_dbt_profile`) | High: the plan's keys and relationships become runnable checks for teams that do not use dbt | Low: a new draft beside `dbt_schema`, pure text from the plan, written from each tool's own documentation; no new dependency | Most value for the least work; reuses what `validate_plan` already establishes |
| 2 | **An MCP App for review**: a `ui://` resource (`text/html;profile=mcp-app`) linked to `review_plan` or `lineage` that shows the ER diagram with each relationship's rule and counts in the client | ext-apps specification; dbt-mcp's `ui://dbt-mcp/get-lineage` | High: review is where a person decides; today the client shows JSON and Mermaid text | Medium: a self-contained HTML page served by the server, client support varies, browser tests needed | Clear value, more moving parts than idea 1 |
| 3 | **Server-wide switches**: an environment setting that does not register the creating tools at all (read-only Krusgraph), and one that removes `sample_rows` and any other tool that returns row values | DataHub (`TOOLS_IS_MUTATION_ENABLED`), TestGen (source data protection, `strict`), us-all (`DBT_TOOLS` / `DBT_DISABLE`), horizun-pbi-mcp (profiles), Microsoft's toolsets | Medium–high: an answer to `docs/RISK-REGISTER.md` R3 and to customers who forbid row values leaving the tenant | Low: registration-time checks in `server.py` and tests; touches the MCP tools area | Small change, real effect on trust; ranked under 2 only because dry run and per-tool notes already cover part of it |
| 4 | **Lineage out in OpenLineage form**: export `lineage`'s graph (table → GraphQL API, semantic model, view, data agent) as OpenLineage JSON so a catalog that reads OpenLineage can take it in | No OpenLineage MCP server found; which catalogs accept OpenLineage events was not checked this round and is the first step | Medium: Krusgraph's edges reach the catalog a customer already runs | Medium: map the four edge kinds to OpenLineage datasets and jobs from the specification; licence of the spec to be read first | Useful but depends on which catalog a customer has |
| 5 | **Column-level usage**: from the TMDL Krusgraph already reads, which measures and columns of a semantic model use a given source column, so `plan_drift` can say which measures a dropped or renamed column breaks | pbi-context (`find_column_usages`, `get_measure_dependencies`, `diff_impact`), pbix-lineage (column-to-visual), dbt-lineage-viewer (`column_upstream` / `column_downstream`) | Medium–high: drift today names tables and objects, not measures | High: a DAX reference parser is needed and must be tested against real models | Highest effort of the five |

Considered and not ranked: catalog write-back (descriptions, terms, owners) is better done by a catalog's own server
with Krusgraph's `data_dictionary` text in the same client; profiling and anomaly monitors are TestGen's and similar
products' work; performance tuning (Force-Fabric) is outside Krusgraph's scope.

## Process

1. **Scan monthly.** Once a month a Docs round repeats this scan with the same sources (Glama, the MCP Registry, GitHub
   search) and the same scope, updates this file's tables and dates, and lists what could not be reached. A server whose
   last commit or licence changed gets its row re-read; a row is never deleted, a change is written beside the old
   reading.
2. **Read code and listings separately.** Tool names and behaviour come from the source at a pinned commit; what a
   README, the registry or Glama says is quoted as a listing and marked as such. Where they disagree, both are written
   down.
3. **Licence gate**, decided from the `LICENSE` file at the commit in question, never from GitHub's metadata or a
   listing:
   - **MIT, Apache-2.0, BSD**: code may be reused. The copyright line and the licence travel with the code, the source,
     commit and file are named in a comment at the top of the copied code and in the commit message, and the project
     gets a line in `THIRD_PARTY_NOTICES.md` (the vendored section) in the same commit, kept current with
     `python tools/third_party_notices.py`. Apache-2.0 `NOTICE` text is carried along.
   - **GPL and AGPL** (and SSPL): no code, in any amount. The server may still be run alongside by a user.
   - **No licence file, a proprietary or source-available licence, or a licence that cannot be verified**: ideas only.
   - A directory with its own `LICENSE` (as in OpenMetadata) is judged by that file, not by the repository root.
4. **Reused code is our code.** Every reused line is reviewed and tested like a line written here: it goes through the
   whole suite, gets its own tests, and meets `CONTRIBUTING.md` like any other change.
5. **No new dependency without review.** A package, SDK or framework seen here (an MCP Apps SDK, Great Expectations,
   an OpenLineage client) is added to `deploy/constraints.txt` or `pyproject.toml` only after a review of its licence,
   maintenance and size, and the notices check (`tools/third_party_notices.py --check`) passes.
6. **Gustav approves each idea before it is built.** An idea from this file becomes work only when the maintainer has
   said yes to it; the round that builds it names this file and the idea's number in its claim.
