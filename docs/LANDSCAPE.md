# MCP landscape: what other servers do, and how ideas from them are reused

Internal working note, not linked from the site. Round n118, 6 November 2026; updated by round LS2 on 21 November
2026 (the next section, with the idea list). It records which MCP servers around
Microsoft Fabric, Power BI, OneLake, dbt, data quality, data catalogs, lineage and MCP Apps were looked at, what each
does that Krusgraph's tools do not, and a verdict per server. The process at the end is how this is kept up to date and
how an idea or a line of code from one of them may ever reach this repository. `docs/ECOSYSTEM-WATCHLIST.md` stays the
register of servers a user may be pointed at; `docs/COMPANION-MCP.md` stays Krusgraph's position beside Microsoft's
servers. This file is the wider scan behind both.

Krusgraph's side of each comparison is its 39 tools as listed in `fabric_backend/tool_status.py` on this date. "Does
not" below means only that none of those tools does the thing; it says nothing about which is better.

## Update of 21 November 2026 (round LS2)

Round LS2 re-ran the scan with the scout procedure and added what is new or changed since 6 November 2026. The tables
further down are n118's reading and are kept as they were; where a server changed, the new reading is in this section.
Nothing was built, no code was copied, nothing was installed or run, and no Fabric call was made.

### Ideas, for Gustav's yes or no

At most seven. Ideas 2 and 3 of n118 are built (the MCP Apps review card; the server-wide switches, round n123), so
they are not repeated. Each idea is written from documentation or from what a server does; **no idea needs code from
another project**, so the licence column is about the source of the idea, and about what could ever be reused under
Process 3 below.

| # | Idea | Seen in | Value | Effort | Licence of what it is seen in | Recommended |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **Checks for more than dbt** (n118 idea 1): draft a Great Expectations suite, later Soda checks, from the checked plan, the way `dbt_schema` drafts dbt tests | gx-mcp-server, dbt-doctor, dbt-lineage-viewer, TestGen; new: LakeLogic/lakelogic-mcp (YAML data contracts) | High: keys and relationships become runnable checks for teams without dbt | Low | MIT / Apache-2.0; written from each tool's documentation | **Ja** |
| 4 | **Lineage out in OpenLineage form** (n118 idea 4) | no OpenLineage MCP server found again on 21 Nov 2026 | Medium, and only for a customer whose catalog reads OpenLineage | Medium | the specification's licence still to be read | **Nej** (wait until a customer's catalog asks for it) |
| 5 | **Column-level usage** (n118 idea 5): which measures a dropped or renamed source column breaks | pbi-context, pbix-lineage (now pbix-atlas); new: akabyte-labs/data-platform-toolkit (where measures and columns are used in PBIR), clementlemon02/datawright | Medium–high: Drift would name broken measures | High: a DAX reference parser, tested on real models | MIT (pbix-atlas: see licence findings) | **Nej** for now (after Drift has run once in Fabric) |
| 6 | **Point users at Microsoft's remote servers**: update `docs/COMPANION-MCP.md` and `docs/ECOSYSTEM-WATCHLIST.md` for the Fabric Core MCP Server (remote), Fabric IQ MCP (now generally available, with a plugin for Claude), the ontology MCP endpoint and the hosted Power BI Authoring server; docs only | Learn, *Microsoft Fabric MCP servers* (below) | High: the pairing a user sets up becomes one URL each, nothing to install | Low (docs) | Microsoft's service terms; nothing to copy | **Ja** |
| 7 | **Check an agent's SQL against the checked plan**: a deterministic check that a query's joins are ones the plan counted, warns on a one-to-many fan-out over a header amount, and says when a question is not covered; first as part of Agent Guard | gogoymh/auto-ontology-mcp (`validate_sql`, `find_join_path`, `check_answerable`, fan-out checks) | High: the doubled total caught before a person sees it; fits Agent Guard | Medium | Apache-2.0 (`NOTICE` names gogoymh); idea only | **Ja** |
| 8 | **Join rules across systems**: an accepted cross-system match (SAP customer number to CRM account, VAT id) kept as a tenant rule with its counts and who decided, proposed again and recounted on every run; `docs/LEARNING-DESIGN.md` part A | benseverndev-oss/goldenmatch (golden records across sources), rhetratech/rhetra-ontology (links checked against rows), SM1's `docs/SMOOTH/COMBINE-SOURCES.md` | High: the second source and the second team do not start from zero | Medium, after SM7 | MIT / Apache-2.0; idea only, and Krusgraph keeps to rules M0–M3 (no fuzzy or model matching) | **Ja** |

### How it was read this time

| Source | Reached | Used for |
| --- | --- | --- |
| Official MCP Registry | Yes | 50 search terms; 215 entries kept |
| GitHub repository search (`gh api search/repositories`) | Yes | 28 queries; 693 repositories kept. Finding only, never the licence |
| `git ls-remote`, `git clone --depth 1` through the session's git proxy | Yes | Head commits of 814 repositories; 60 shallow clones scanned for signals by the script; 15 read by hand (below). Nothing built, installed or run |
| `raw.githubusercontent.com` | Yes | The `LICENSE` file of every repository, at the default branch on 21 November 2026 |
| Microsoft Learn | **Yes** (it was not on 2 or 6 November) | The pages cited below, with `ms.date` and "last updated" as each page showed them |
| glama.ai, mcp.so, smithery.ai | **No.** The proxy refused the tunnel (403), as on 6 and 12 November | Nothing in this file comes from them |
| github.com web pages, `api.github.com` | No (HTTP 403) | Not used |

### Microsoft's own servers and skills

Learn now keeps one list, *Microsoft Fabric MCP servers*
([page](https://learn.microsoft.com/en-us/rest/api/fabric/articles/mcp-servers/fabric-mcp-servers-list), ms.date
2026-11-02, last updated 2026-11-16). It names remote servers (Microsoft-hosted, Entra sign-in) and local ones.

| Server or project | Kind | What is new since 6 November 2026 | Source (ms.date / last updated, or commit) | Verdict |
| --- | --- | --- | --- | --- |
| **Fabric Core MCP Server** | remote, `https://api.fabric.microsoft.com/v1/mcp/core` | **New.** Workspaces, role assignments, folders, items and item definitions, OneLake catalog search, shortcuts, data access roles; "an agent can do only what its identity is allowed to do". The page warns that safeguards against destructive operations "are not standardized in the MCP specification" | [overview](https://learn.microsoft.com/en-us/rest/api/fabric/articles/mcp-servers/core-remote/overview-core-mcp-server) (2026-11-04 / 2026-11-16); [get started](https://learn.microsoft.com/en-us/rest/api/fabric/articles/mcp-servers/core-remote/get-started-core) (2026-11-03 / 2026-11-16) | **alongside** (idea 6) |
| **Fabric MCP Server (local)**, microsoft/mcp `servers/Fabric.Mcp.Server` | local | 1.7.0 (1 Nov) added `core_get-item-definition` and `core_update-item-definition`; **1.8.0 (11 Nov)** added folders, workspace role assignments, `core_move-item`, and a `jobs` namespace (run, cancel, schedules). The registry entry `com.microsoft/microsoft-fabric` still says 1.4.0 | `CHANGELOG.md` at `af0f050` (2026-11-20); LICENSE MIT, "Copyright 2025 (c) Microsoft Corporation." (unchanged) | **alongside** (unchanged) |
| **Fabric IQ MCP** | remote | Its page now says "Fabric IQ MCP is generally available"; read-only; RLS and OLS apply; endpoint `https://fabriciq.svc.cloud.microsoft/v1/mcp/fabriciq` | [page](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp) (2026-11-10 / 2026-11-11) | **alongside** (idea 6) |
| microsoft/fabriciq-thirdparty-plugins | plugin, not a server | **New.** "the Microsoft Fabric IQ plugin for third-party AI assistants: Claude and ChatGPT", connecting to the Fabric IQ remote server | `ba76148` (2026-11-18); LICENSE MIT, "Copyright (c) 2026 Microsoft Corporation" | **alongside** (idea 6) |
| **Ontology MCP server** | remote, one endpoint per ontology item, `…/v1/mcp/dataPlane/workspaces/<ws>/items/<id>/ontologyEndpoint` | **New page.** **Preview**; "you can't currently use Service Principal"; needs F2 or higher | [page](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-ontology-mcp-server) (2026-11-06 / 2026-11-17) | **alongside**: where an ontology Krusgraph created is read by an agent |
| **Power BI Authoring MCP** (formerly listed as powerbi-modeling-mcp) | hosted (**preview**) and local (generally available) | The hosted option is new; the repository README now says to use the hosted server for Fabric workspaces and that the local server does not support macOS | [page](https://learn.microsoft.com/en-us/power-bi/developer/mcp/power-bi-authoring-mcp) (2026-09-01 / 2026-11-17); repository `e293779` (2026-11-19), LICENSE MIT, still no source code | **alongside** (unchanged) |
| Power BI Agentic | a bundle of skills and tools | Learn describes a `powerbi-authoring` plugin from the skills-for-fabric marketplace, for GitHub Copilot CLI with "compatibility shims" for Claude Code and others | [page](https://learn.microsoft.com/en-us/power-bi/developer/agentic/power-bi-agentic-overview) (2026-06-04 / 2026-11-20) | **skip** (how-to for coding agents) |
| microsoft/skills-for-fabric | skills | 0.3.22 (12 Nov): `fabric-policies-cli`; 0.3.23 (19 Nov): `plan-cli`, `fabriciq` reads model-authored topics. 0.3.21 (5 Nov): `ontology-cli` sends questions about new-experience ontologies to the ontology's own agent endpoint, and "CLI authoring remains limited to legacy V1 definitions and cannot create or upgrade V2 items" | `CHANGELOG.md` at `540c3c5` (2026-11-20); LICENSE MIT, "Copyright (c) 2026 Microsoft Corporation" | **skip** (unchanged); the V1/V2 note matters to `create_ontology` and is worth a check before the next live run |
| microsoft/DataFactory.MCP | local | **Not in n118's scan.** Gateways, connections, dataflows, pipelines, copy jobs, Airflow jobs; one MCP App resource `ui://datafactory/create-connection`; interactive or service-principal sign-in | `171647e` (2026-11-16); `LICENSE.txt` MIT, "Copyright (c) Microsoft Corporation." | **alongside** for pipelines; nothing to take |
| microsoft/fabric-rti-mcp | local | New `kusto_deeplink_from_query`; read-only and destructive annotations on tools; external tables for OneLake shortcuts | `CHANGELOG.md` at `e0e4642` (2026-11-16); LICENSE MIT (unchanged) | **alongside** (unchanged) |
| Dataverse MCP (`com.microsoft/dataverse` 1.0.95) and microsoft/Dataverse-skills | registry entry; skills repository | **Not in n118's scan.** "Query, create, and manage Microsoft Dataverse tables, records, and solutions"; the skills cover Dataverse and Finance and Operations | registry 21 Nov 2026; repository `79ec1e2` (2026-11-16), LICENSE MIT, "Copyright (c) Microsoft Corporation." | **alongside** for the Dynamics 365 pack (`docs/DYNAMICS365.md`) |
| Fabric data agent as an MCP server; Data Warehouse MCP; Eventhouse, Activator and operations agent MCP | remote | Listed on the new page; nothing else new found | the list page above | unchanged |

Unchanged since 6 November 2026: microsoft/purview-dlm-mcp (`f5cdcb9`) and microsoft/Ontology-Playground (`7bf7acb`).

### Watched servers that changed (15 of 33)

Head commit moved since n118's pinned commit; the licence file was read again for each. Only what matters for a
verdict is noted; a moved head with no note means routine commits and an unchanged licence class.

| Server | Was (6 Nov) | Now (21 Nov) | Note |
| --- | --- | --- | --- |
| microsoft/mcp, skills-for-fabric, fabric-rti-mcp, powerbi-modeling-mcp | see above | see above | see Microsoft's table |
| dbt-labs/dbt-mcp | `0671ec0` | `3647587` | Apache-2.0, unchanged |
| sipemu/dbt-lineage-viewer | `0ff0235` | `73d7d04` | MIT, unchanged |
| DataKitchen/dataops-testgen | `9a4accb` | `7f8cab3` | Apache-2.0, unchanged |
| HorizunGroup/horizun-pbi-mcp | `e2ff437` | `984c62d` | Apache-2.0, unchanged |
| sulaiman013/powerbi-mcp | `977b4d1` | `72709fa` | MIT, unchanged |
| maxanatsko/mcp-engine-public | `dd9e70a` | `09b3e18` | still proprietary, "All rights reserved" |
| open-metadata/OpenMetadata | `e906dd7` | `78e4716` | root Apache-2.0; `openmetadata-mcp/LICENSE` is still the Collate Community License 1.0: ideas only |
| marmotdata/marmot | `633e9bd` | `3a5f116` | MIT, unchanged |
| modelcontextprotocol/ext-apps | `19256f5` | `ea3e9d0` | the file still says the project is moving from MIT to Apache-2.0 (mixed); a pattern match reads it as Apache-2.0, which is not the whole story |
| alpic-ai/skybridge, mcp-use/mcp-use | `9afa5fa`, `ac0b6a5` | `5cd3f8c`, `8ff4b86` | MIT, unchanged |

Not moved: the other 18, among them acryldata/mcp-server-datahub (`e4de4c0`), Osc2405/pbi-context, davidf9999/gx-mcp-server, OpenDQV/OpenDQV and the four community servers of `docs/ECOSYSTEM-WATCHLIST.md` (the AGPL one, mkoziel2000/mcp-fabric-api, is still AGPL-3.0; the two without a licence file still have none).

### New servers read by hand

From the 915 entries that were new to the scout, the ones about Fabric, Power BI, ontologies, joins and data
products were read. Most of the rest are demos, workshop material, Minecraft mods (the word "fabric") or have no
licence file.

| Server | Owner | Licence (LICENSE file) | Last commit | What it does (read in code and README) | What it does that Krusgraph does not | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| [auto-ontology-mcp](https://github.com/gogoymh/auto-ontology-mcp) | gogoymh | Apache-2.0; `NOTICE`: "Copyright 2026 gogoymh"; the README credits NVIDIA/auto-ontology (Apache-2.0) for ideas and code | `0fb5ecf`, 2026-11-18 | Tools include `scan_datasource`, `list_relationships`, `set_relationship`, `find_join_path`, `check_answerable`, `validate_sql`, `define_entity`, `save_glossary`; fan-out checks in `validation.py`; local SQLite; the client's model does the language steps | Checks a query's joins and fan-out against reviewed relationships; says when a question is not covered | **build the idea** (idea 7); no code |
| [rhetra-ontology](https://github.com/rhetratech/rhetra-ontology) | rhetratech | Apache-2.0 text, no copyright line found in the file | `3bedbd1`, 2026-11-16 | TypeScript CLI and MCP (`profile_source`, `infer_ontology`) over CSV, SQLite or Postgres: objects, links, "checks every relationship against the actual rows"; no test files found | The same idea as Krusgraph's evidence, outside Fabric | **skip**; noted as overlapping (no Fabric) |
| [ontopoc](https://github.com/Longado/ontopoc) | Longado | **AGPL-3.0** | `b15bf26`, 2026-11-21 | "draft, check, and confirm ontologies from business data" | Overlaps Krusgraph's ontology drafting | **skip**: AGPL, no code ever |
| [orionbelt-analytics](https://github.com/ralforion/orionbelt-analytics) | RALFORION d.o.o. | **Business Source License 1.1** | `cd62a2e`, 2026-11-20 | schemas of PostgreSQL, Snowflake, ClickHouse, Dremio to RDF/OWL ontologies with SQL mappings | Ontologies from other databases | **skip**: ideas only |
| [goldenmatch](https://github.com/benseverndev-oss/goldenmatch) | Ben Severn | MIT, "Copyright (c) 2024-2026 Ben Severn" | `d4e091a`, 2026-11-21 | entity resolution into golden records; an MCP server in its `goldenpipe` package (`run_pipeline`, `explain_pipeline`, …); many tests and CI workflows | Matches records across sources by learned or fuzzy scoring | **alongside** for teams that need fuzzy matching; Krusgraph keeps to rules (idea 8) |
| [databricks-explore](https://github.com/taslater/databricks-explore) | Thomas Slater | MIT, "Copyright (c) 2026 Thomas Slater" | `107fe7a`, 2026-11-19 | Unity Catalog browser with a relationship graph ("mined joins") and an MCP server | Mines joins on Databricks | **skip** (Databricks only) |
| [data-platform-toolkit](https://github.com/akabyte-labs/data-platform-toolkit) | Matteo Rossi | MIT, "Copyright (c) 2026 Matteo Rossi" | `5951acb`, 2026-11-17 | PBIP files on disk: TMDL edits (read-only by default), where measures and columns are used in PBIR, lineage to the source column | Column and measure usage | idea 5 |
| [datawright](https://github.com/clementlemon02/datawright) | Clement | MIT, "Copyright (c) 2026 Clement" | `4662a42`, 2026-11-21 | lineage, join paths and column meanings from a data repository's code, no warehouse access | Join paths from code | **skip**; idea 5 |
| [lineageiq](https://github.com/LargoLujan/lineageiq) | Manuel Luján Vilchez | MIT, "Copyright (c) 2026 Manuel Luján Vilchez" | `d6a52f8`, 2026-11-10 | read-only lineage and catalog mapper for Fabric with a graph UI, a REST API and MCP servers | Lineage below item level in Fabric | **skip** for now; re-read next month |

Seen in a listing and not opened: `LakeLogic/lakelogic-mcp` (Apache-2.0 per its file, data contracts; idea 1),
`microsoft/semantic-link-labs` (MIT, not an MCP server), `microsoft/azure-ai-search-foundry-iq-live-knowledge-source`
(MIT, a Foundry IQ accelerator with ontology knowledge sources), `enum-studio/powerbi-metrics-book` (Apache-2.0),
`Lee2277-t/pbip-forge` and `jeyssonlza/powerbi-mcp-server` (both AGPL-3.0), `bobzhou-source/powerbi-pbir-mcp` (LGPL).

### Licence findings, 21 November 2026

- **pbix-lineage is now pbix-atlas, and its licence file no longer holds the licence text.**
  `fabienfrfr/pbix-lineage` answers with a sign-in prompt (the repository is gone or private); GitHub search finds
  `fabienfrfr/pbix-atlas` (head `5f20960`, pushed 18 November 2026). Its `LICENSE` file is two lines, "MIT License"
  and "Copyright (c) 2026 Fabien FURFARO", without the permission text; GitHub shows NOASSERTION. Under Process 3 that
  is a licence that cannot be verified: **ideas only** from now on. n118's reading (MIT, `3b489b6`) stays above.
- **rhetra-ontology**: Apache-2.0 text with no copyright line and no `NOTICE`; the holder would have to be identified
  before any reuse. **auto-ontology-mcp**: Apache-2.0, holder in its `NOTICE`, and it carries code from
  NVIDIA/auto-ontology, so a reuse would carry both notices. Neither is proposed for reuse.
- **ext-apps**: still mixed MIT and Apache-2.0; a scanner that matches the Apache text alone misses the MIT part.
- **OpenMetadata MCP**: the directory's own licence is still the Collate Community License 1.0.
- New AGPL, LGPL and BUSL projects in the area (ontopoc, pbip-forge, powerbi-mcp-server by jeyssonlza,
  powerbi-pbir-mcp, orionbelt-analytics): no code, ideas only.


---

*The reading of 6 November 2026 (round n118) follows, unchanged.*

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
| [pbix-lineage / pbix-atlas](https://github.com/fabienfrfr/pbix-lineage) | Fabien Furfaro | MIT, "Copyright (c) 2026 Fabien FURFARO" | `3b489b6`, 2026-07-29 | FastAPI routes mounted as tools (`FastMCP.from_fastapi`): `build_graph`, `search_nodes`, `get_upstream`, `get_downstream`, `get_lineage_tree`, `export_graph`, `get_source_schema`, graph invalidation; M-query and DAX parsers in code | Registry `io.github.fabienfrfr/pbix-lineage`: "Bidirectional data lineage graph for Power BI (.pbix) files, from source to display"; README names it pbix-atlas | Column-to-visual lineage inside a report, through Power Query and DAX | **alongside** for `.pbix` files; column lineage is idea 5. *21 Nov 2026 (LS2): renamed pbix-atlas; its LICENSE file no longer holds the licence text, so ideas only (see the LS2 section)* |
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

*21 November 2026: ideas 2 and 3 are built; the current list, with ideas 1, 4 and 5 re-judged, is the LS2 section at
the top.* Ranked by value to Krusgraph against effort. Each is an idea only: nothing is built until Gustav approves it (see
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
