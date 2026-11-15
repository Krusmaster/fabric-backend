# Analysis of Krusgraph, November 2026 (A1)

Round A1, 15 November 2026. Docs only: this one file was written, no code, site, test or other document changed.
Written by a scheduled Claude session with no live user, for the backlog round B1. The founder, 12 November 2026:
"the backlog must be filled, after a real analysis."

`main` was read at `e5c7068` (n235's claim). Nothing was run against Fabric, the hosted service or any customer
system. No customer or person is named; Microsoft contacts are "Microsoft SAP architects". Nothing here is a claim
about speed, compliance, certification, partnership or endorsement, and no non-public Microsoft material was used.

## How it was done, and how far to trust it

- **Part 1** rests on the repository: the code, `CHANGELOG.md`, `docs/SCOPE-REVIEW.md` (S1, 12 November),
  `docs/MISSING-EVIDENCE.md`, `docs/RISK-REGISTER.md`, `docs/REVIEW-2026-11-08-fable.md`, `docs/LIVE-TEST*.md`,
  `fabric_backend/tool_status.py` and the head of every `docs/*-DESIGN.md`. Two sub-readers read the code (the
  architecture; the tests and security) and gave file and line; the lines quoted here are theirs at `e5c7068` and were
  not all re-opened. The checkout is shallow (50 commits), so history before 11 November was read from the CHANGELOG.
- **Part 2** rests on the web as read on **15 November 2026**. From this session only `learn.microsoft.com` and
  `claude.com` could be opened. Every other host (Microsoft's blogs and community, vendor sites, press) was refused by
  the session's network policy. So each source below carries one of two marks: **Opened** (the page was read) or
  **Unverified** (a search-result summary only; the page was not opened). Vendor numbers are vendors' claims.
  **Guess:** marks this analysis's own inference.
- **Microsoft Ignite 2026 is reported for 17 to 20 November 2026** (Unverified; https://itdaily.com/events/microsoft-ignite/,
  no date shown, accessed 15 Nov 2026). Everything in Part 2 about Microsoft's direction should be re-read after it.
- The suite was not run by the main session. What the test sub-reader ran is said in section 1.6.

## Part 1. The product as it is

### 1.1 What it is, in one paragraph

One Python engine (`fabric_backend/`, 119 files, about 52 000 lines) reads the table and column names of a schema,
proposes keys (rules K0 to K5) and relationships (R0 to R5), each with the rule that made it, and a separate check
counts them against the rows: duplicates, NULLs, orphans, and totals that double across a join. From an accepted plan
it writes Fabric items: silver and gold notebooks with a pipeline, a Direct Lake semantic model, a report, an API for
GraphQL, an ontology (Fabric IQ, preview), a data agent, and an empty App item (Fabric Apps, preview). The engine uses
no AI model. Version 0.8.0, MIT.

### 1.2 Evidence classes

Three classes are used, as in S1: **S** live in the publisher's own tenant on synthetic data; **U** unit tests only;
**C** a real customer or SAP system. **There is no C for anything** (`docs/MISSING-EVIDENCE.md` rows 8 and 9).

**Built and proven live in Fabric (S: own tenant, synthetic `shop` and SAP-shaped samples)**

| Capability | Last recorded live | Note |
| --- | --- | --- |
| Reading: workspaces, sources, tables, sample rows | 26 to 27 Oct | one schema reported at the time; fixed since in code |
| `plan_backend`, keys and links with rules | 27 Oct, 2 Nov | on names that fit the rules |
| `validate_plan`, the row check | 2 Nov (shop 6/6 keys, 7/7 links; SAP-shaped 17/17, 32/34) | before n226's budget and ordering |
| Doubled totals | 29 Oct | SAP-shaped sample |
| `create_backend` updating an API for GraphQL in place | 27 Oct | a new API is U only |
| `create_ontology` | 28 Oct, 2 Nov | preview item; tenant setting needed |
| `create_semantic_model` | 29 Oct, 9 Nov | single-column keys |
| `create_report` | 30 Oct, 7 Nov | never updated in place |
| `create_pipeline` (silver, gold, check) | 7 Nov | three steps succeeded once |
| The Krusgraph Model editor (workload item `Org.Krusgraph`) | the founder's runs, 9 to 12 Nov | exists only in the publisher's tenant; no outside user |
| Clients that signed in to the hosted MCP server | 27 and 30 Oct | Claude, VS Code, Cursor, Glama, Lovable |

**Built, unit-tested only (U)**

- Round n226, the three most important mechanisms of S1: evidence state and coverage on every plan answer, one
  45-second budget per call with partial results and `resume_from`, composite keys carried into silver, the model and
  the ontology. The CHANGELOG says "unit tests only, not run in Fabric" and "needs a redeploy".
- The guided `start` path; suggested data products; the health table and alerts; the Data product page's retire and
  delete; the drift monitor (created in Fabric on 28 October, never run there).
- Sources other than a lakehouse: mirrored databases (SAP through SAP Datasphere among them), warehouse, SQL
  database, Snowflake, Databricks. `mirroring.py:31-35` says the folder layout is "not documented, so not assumed" and
  it was "not run against a mirrored database in Fabric"; `platforms/databricks.py:1-2` says "Draft only".
- The SAP pack (six modules, 60 tables listed) and the Younium and Salesforce pack: every module is `documented`,
  none verified; the public SAP pages behind it were cited from memory and not re-opened (`docs/SAP.md:196`, per S1).
- Commerce, all off by default: Marketplace landing page and webhook, the 30-day trial and billing rows,
  entitlements, the own OAuth server for clients other than Claude.
- Drafts for other tools: dbt project, Great Expectations and Soda checks, OpenLineage events, catalog tags.
- `create_views` and the MCP `create_data_agent`: dry runs only. No data agent answer has ever been scored.

**Designed only (a text, nothing built)**

`CONNECT-DESIGN` (sources into OneLake), `LIFECYCLE-DESIGN` (a product that watches itself), `PROMOTE-DESIGN` (dev,
test, prod), `DOMAINS-DESIGN` (several domains), `MIGRATION-PLATFORMS-DESIGN` (Databricks, Snowflake, Qlik Sense),
`WORKLOAD-UX-DESIGN` (a shorter editor flow, with mockups), `FABRIC-IQ-AT-SCALE`. Together about 3 300 lines.

**Claimed in `CONTRIBUTING.md` but not on `main` on 15 November**

`docs/MIGRATION-DESIGN.md` and `fabric_backend/migration_read.py` (W7), `docs/PRICING-DESIGN.md` (P1),
`docs/INTEGRATE-AND-HEAL-DESIGN.md` (W9), `docs/LEARNING-DESIGN.md` (L1), marketing drafts under `docs/marketing/`
(M1; the folder holds W10's `MIGRATIONS.md` only), and this file from an earlier A1 run of 12 November. Five claims
held open for three days without a file. `MIGRATION-PLATFORMS-DESIGN.md` builds on W7's text without having read it.

**Claimed, or easy to read as claimed, without evidence**

1. Anything about a customer's data or a real SAP system. The SAP work is a pack written from public knowledge and
   tested on tables generated from the pack itself; it shows the engine applies the pack, not that the pack is right.
2. Inference quality beyond naming conventions. The repository's own score on AdventureWorks is 47 of 71 keys right,
   4 wrong, 20 missed; 62 of 90 links found, 17 wrong (unchanged by n226). Every benchmark answer key was written by
   the project that wrote the rules, and the comparison with Power BI is against "an approximation of documented
   autodetect rules", not against Power BI (`examples/benchmark/README.md`).
3. S1 listed ten sentences that promised more than the evidence. Round n224 reworded the site ("S1's site wording");
   this analysis did not re-audit every sentence, so B1 should treat S1 section 4 as a checklist to close, not as closed.
4. What the hosted service runs. The CHANGELOG's head still says "not yet deployed after the build of 6 November",
   while the founder tested workload package 1.0.1074 on 12 November. What a tester meets at krusgraph.com today
   cannot be told from the repository.
5. The migration sales draft (`docs/marketing/MIGRATIONS.md`) describes an offer for which no reader, tool or test is
   on `main`, and whose Snowflake, dbt and Qlik facts are all marked Unverified by its own design text.

One small finding for the founder: `docs/WORKLOAD-PUBLISH.md` prints the company tenant id in a public repository,
while `docs/MISSING-EVIDENCE.md` forbids tenant ids in screenshots. A tenant id is not a secret, but the two rules
should agree.

### 1.3 The products and how they relate

The task names three products; the site names four (`offering.py:127-189`): Krusgraph for Fabric, Krusgraph for
Claude, Krusgraph for Lovable and Krusgraph Open Source.

| Product | What it is in the code | Who can use it today | State |
| --- | --- | --- | --- |
| **Krusgraph for Fabric** | The workload item "Krusgraph Model" (`workload/`, a fork of Microsoft's Extensibility Toolkit, frontend-only manifest, one item, about 160 TypeScript files, 30 test files). The editor calls `/workload/v1/*` in `workload_api.py` (2 737 lines), which calls the same functions as the MCP tools | Only the publisher's tenant, as `Org.Krusgraph`. The permanent name `Krusgraph.Modeler` is proposed, not registered | Pilot. The founder's own runs only |
| **Krusgraph for Claude** | The hosted MCP server (`server.py`, 3 606 lines, 40 tools, about ten that write to Fabric, each with a dry run by default). Sign-in with a multi-tenant Entra app and on-behalf-of tokens. Listed in the official MCP Registry | Anyone whose Entra administrator consents to the app | The most tried surface |
| **Krusgraph for Lovable** | The same hosted service reached from Lovable; the API for GraphQL as the app's backend | As above | One run, 30 October |
| **Open source and the website** | The package under MIT (a second, local MCP server in `mcp_server.py` with 24 tools; a CLI), and the site with `/check`, which runs the engine in the browser through Pyodide with no upload | Anyone | No outside user recorded |

How they relate: one engine, and that is the architecture's best property (`tests/test_architecture.py` guards that
the engine imports no adapter). The cost is that every surface needs its own wording, tests and live evidence, and one
founder now maintains a chat product, a Fabric workload with a React editor, a website with an in-browser engine, a
local server, and dormant commerce code. **Guess:** the workload is the product a Fabric buyer will pay for, the MCP
server is the cheapest way for an expert to try the engine this week, and the open source code is the trust argument
for both. Lovable is a client of the second, not a product.

### 1.4 The architecture

One container image (a Node stage that builds the editor, then Python 3.12 with the SQL Server ODBC driver) on one
Azure Container App: 0.25 CPU, 0.5 GiB, at most two replicas, scale to zero by default
(`deploy/azure_containerapp.py:605-619`). It serves the site, `/mcp`, the workload API and the editor host. The MCP
server is stateless over HTTP. There is no database: Azure Table Storage holds registration, billing and entitlement
rows when those features are on; tokens, rate-limit buckets and metrics are in memory per replica. Customer data is
read with the signed-in person's own Fabric permissions and the items are created in the customer's workspace.

### 1.5 The weak points

| Weak point | What the code does | Why it matters | State after n226 |
| --- | --- | --- | --- |
| **Inference by names** | Keys and links come from name rules: suffixes `id, key, code, nr, no, sk, bk` (`infer.py:236`), table prefixes, one hard-coded synonym table of about 25 abbreviations and Swedish and German nouns (`infer.py:248-270`). Rows are read only by R5 (candidates still chosen by name; 200 values, 20 queries on the hosted server) and by the separate check. A table whose names match nothing is keyless, and nothing can point at it. No profiling proposes a key from the data | The first real schema will not follow `<table>_id`. S1 tried a Nordic ERP shape: 4 keys of 8, one wrong, 1 link. This is the largest credibility risk | Not solved. n226 made the weakness visible (evidence states, coverage headline), which is the right first step. S1's mechanism 4, "count before claiming, and let the data propose", is not built |
| **SAP recognition by table name** | The pack matches table names after a fixed prefix list and needs two recognised tables (`sap_pack.py:38, 179`). `ecc_VBAK`, `VBAK_800`, Z tables, CDS views, MATDOC get nothing | An SAP architect tries a prefixed table and a Z table in the first ten minutes | Not solved. Matching by key-column signature is not built |
| **Composite keys** | One text column per key, parts cast to string and joined with a separator (`combined_keys.py:37-43, 158-171`). A NULL part gives a NULL key. No trim, padding or type normalisation, so `1` and `0001` do not meet. Carried only when the link targets the target's full key; lakehouse only; the model then depends on the silver step having run. The data agent, the API and the views do not use it | Every SAP link has MANDT or a second column. Before n226 the SAP sample's model had 0 relationships | Built, unit-tested on the synthetic SAP sample only (19 of 19 links carried). Not run in Fabric |
| **Value representation** | The check compares `s.a = t.b` as stored. Leading zeros, case, trailing blanks and type differences read as orphans | SAP document and material numbers are padded. A false orphan count ends a session | Not solved |
| **Large schemas** | The plan is fast (measured in a unit test: 1 000 tables in under a second). The check is not: 60 items per call, 200 at most, with a resume call. Above 60 tables answers switch to a summary; answers are cut at 60 000 characters. The editor's map is capped at 60 tables and 120 links. 5 000 tables: not measured | An SAP landing zone has hundreds to thousands of tables | Ordering and resume built (U). No scoping workflow ("start with these 20 tables") in the product |
| **Time budgets** | 45 s per read-only MCP call; statements are not interrupted, only given a shorter timeout (5 s floor). Creating calls are unbounded. The workload API does not use the budget; it uses background operations that are lost when a replica dies. The ingress limit is 240 s | A call that never returns is the worst first impression | Built for MCP (U). Not for the workload API |
| **Fabric preview surfaces** | Ontology, data agent configuration, Fabric Apps, catalog search and parts of Git integration are preview. Microsoft's Learn says the "old ontology experience" retires 31 January 2027 (Part 2) | A format change breaks a tool with an error that looks like Krusgraph's | Controls exist: recorded definitions, Fabric's error passed through, dry run by default. No scheduled contract test against live Fabric |
| **Single founder** | One person holds the Azure subscription, the Entra app, the GitHub organisation, the domain and Partner Center (`RISK-REGISTER` R6). A handover text exists; no second person is named | A buyer's IT asks who answers when the founder is away | Open |
| **One container app** | Site, MCP, workload API and editor host in one small process with in-memory state and cold starts | A marketing visit and a customer's build share 0.25 CPU; a restart loses running operations | Open |
| **Breadth** | About a quarter of the Python is site, demos, cards, mascots and commerce rather than engine. Two MCP servers define overlapping tools. `server.py` mixes tools, routing and site serving. 147 broad `except Exception` | Each surface taxes every change; S1 already asked for a 12-tool core profile | Open |

### 1.6 Quality of tests

*The reader of this section had not finished when the first commit was made; the next A1 commit fills it in.*

### 1.7 Security and privacy posture

*As 1.6: the next A1 commit fills it in.*

### 1.8 The process itself

Since late October the repository has taken several hundred agent rounds (the round counter is at n235), each with a
claim, a release and unit tests. That discipline is real and unusual. Three side effects are worth naming:

- **Building outruns proving.** `tool_status.py` records one full live run (27 October) and single later runs per
  item. The three mechanisms that matter most (n226) have not met Fabric.
- **Design texts outrun builds.** Seven design documents and five unlanded doc claims in one week.
- **The founder is the only live tester and the only deployer.** Every "run it once in Fabric" row waits for one
  person's evening.

## Part 2. The market

Every source: URL, the page's own date where one was seen, accessed 15 November 2026. **Opened** or **Unverified** as
defined at the top.

### 2.1 Who builds on Fabric, and what hurts

**Adoption.** Microsoft is reported to have said "more than 40 000" Fabric customers around its Barcelona conference
in late September 2026, after 28 000 at Ignite 2025 and 31 000 in March 2026. Unverified
(https://azure.microsoft.com/blog/fabcon-and-sqlcon-2026-in-barcelona-building-the-data-foundation-for-microsoft-copilot-and-agents/,
about 28 Sep 2026; https://adastracorp.com/podcast/31000-customers-have-adopted-fabric-in-the-last-two-and-a-half-years/,
no date seen). No 2026 figure for a share of large companies was found.

**What hurts**, by theme:

| Theme | What was found | Source |
| --- | --- | --- |
| Trust in numbers and in agents' answers | Practitioners blame vague names, overlapping measures and missing descriptions for confident wrong answers; forum threads report data agents ignoring their instructions | Unverified: https://www.emergentsoftware.net/resources/insights/why-aren-t-semantic-models-alone-enough-for-ai/ ; https://community.fabric.microsoft.com/t5/Fabric-platform/Microsoft-Fabric-Data-Agent-Ignores-Its-Own-AI-Instructions-Also/m-p/4705096 (no dates seen) |
| Data agent limits | English only, at most five sources, answers capped at 25 rows and 25 columns | Opened: https://learn.microsoft.com/en-us/fabric/data-science/concept-data-agent (ms.date 11 May 2026) |
| Relationship detection | Microsoft's own tutorial says Power BI's autodetection "misses many relationships" and shows wrong ones | Opened: https://learn.microsoft.com/en-us/fabric/data-science/tutorial-power-bi-relationships (ms.date 26 Aug 2025) |
| SAP extraction | SAP Note 3255746 restricts third-party use of ODP through RFC; vendor sources report technical enforcement from mid-2026 | Unverified, vendor sources: https://sapinsider.org/blogs/sap-note-3255746-odp-rfc-deadline-2026/ ; https://theobald-software.com/en/blog/sap-note-325574 (no dates seen) |
| SAP mirroring | Two steps: an SAP Datasphere replication flow lands data in ADLS Gen2, Fabric mirrors it; it needs SAP Datasphere's premium outbound integration, priced by SAP | Opened: https://learn.microsoft.com/en-us/fabric/mirroring/sap (ms.date 26 Feb 2026) |
| Lifecycle | In Git integration, semantic models, reports and the ontology are still tagged preview; unsupported items are ignored | Opened: https://learn.microsoft.com/en-us/fabric/cicd/git-integration/intro-to-git-integration (ms.date 1 Sep 2026) |
| Capacity cost | Capacity overage is generally available for F SKUs since September 2026 and on by default for new capacities; throttling is the most cited surprise | Opened: https://learn.microsoft.com/en-us/fabric/fundamentals/whats-new (ms.date 2 Oct 2026). The "most cited" part is Unverified |
| Preview churn | The "old ontology experience" retires 31 January 2027, with manual re-creation | Opened: https://learn.microsoft.com/en-us/fabric/iq/ontology/overview (ms.date 16 Oct 2026) |
| Governance | Purview's Unified Catalog and classic data governance are being retired: no new accounts, maintenance mode through 12 November 2027; governance is consolidated in Fabric (OneLake catalog, Govern, generally available since September 2026). Purview's security and compliance side continues (the last sentence Unverified) | Opened: https://learn.microsoft.com/en-us/purview/data-governance-overview (ms.date 13 Oct 2026, updated 12 Nov 2026) |
| Qlik to Power BI | Set analysis is the most underestimated part; the associative model is often rebuilt as a star schema; load scripts are rewritten | Unverified, vendor blogs: https://kanerika.com/blogs/qlik-to-power-bi-migration/ (no date seen) |
| Tableau to Power BI | Driven by licence cost and bundling with Microsoft 365; level-of-detail expressions have no direct DAX form | Unverified, vendor blogs: https://kanerika.com/blogs/tableau-to-power-bi-migration/ (no date seen) |

No Reddit evidence was reachable. **Guess:** the pains that Krusgraph's actual core touches are the first three and
the SAP modelling that follows extraction. It does nothing for extraction, licensing or capacity cost today.

### 2.2 Microsoft's own direction

| Area | State | Source |
| --- | --- | --- |
| Fabric IQ and the ontology item | Preview | Opened: https://learn.microsoft.com/en-us/fabric/iq/overview (ms.date 8 Jul 2026) |
| **Generate Ontology from a semantic model** | Creates entity types, properties, bindings, relationship types and metrics from DAX measures. Left to the person: reviewing keys, "especially for multi-key scenarios", and binding relationships to data | Opened: https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-generate-from-semantic-models (ms.date 9 Sep 2026) |
| **Ontology agent** | Preview, LLM-based: finds lakehouse, eventhouse and semantic model sources, "samples a few rows per table", drafts entities, relationships and bindings, runs "structural and grounding checks". The page does not describe counting whole tables | Opened: https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-ontology-agent (ms.date 20 Oct 2026) |
| Data agent | Generally available; an ontology as its source is preview | Opened: the data agent page and whats-new above |
| **Fabric data engineering agent (Project Osmos)** | Preview. Driven from GitHub Copilot CLI, Codex or Claude Code; builds bronze, silver and gold as one task; validates "row counts, nulls, schemas". Microsoft bought Osmos in January 2026 (Unverified) | Opened: https://learn.microsoft.com/en-us/fabric/data-engineering/data-engineering-agent-overview (ms.date 23 Oct 2026). Unverified: https://redmondmag.com/articles/2026/01/06/microsoft-acquires-osmos-to-bring-autonomous-data-engineering-to-fabric.aspx (6 Jan 2026) |
| Microsoft's MCP servers | Fabric IQ and Fabric Core MCP servers generally available (September 2026); a Data Warehouse MCP in preview; the Power BI authoring MCP server creates and edits tables, measures and relationships (local version generally available, hosted in preview) | Opened: whats-new above; https://learn.microsoft.com/en-us/power-bi/developer/mcp/mcp-servers-overview (ms.date 24 Sep 2026) |
| **Semantic Link** | `find_relationships` proposes relationships from name similarity and value coverage; `list_relationship_violations` checks them against the data, in a notebook, free | Opened: the relationships tutorial above |
| Fabric Apps and Rayfin | Fabric Apps is a preview item hosting web apps (SQL database in Fabric, GraphQL, Entra sign-in) built with the Rayfin SDK | Opened: https://learn.microsoft.com/en-us/fabric/apps/overview (ms.date 15 Sep 2026) |
| Business Process Solutions | Prebuilt SAP data models and semantic content in Fabric, finance first; public preview September 2025; no general availability found | Unverified: https://techcommunity.microsoft.com/blog/SAPApplications/announcing-public-preview-for-business-process-solutions/4453658 (Sep 2025) |
| SAP Business Data Cloud Connect for Fabric | Announced November 2025 with general availability planned for the third quarter of 2026; no confirmation found | Unverified: https://news.sap.com/2025/11/sap-bdc-connect-for-microsoft-fabric-business-insights-ai-innovation/ |
| Workload publishing | Upload a package; test with up to 20 tenants without certification; then a publishing request, Microsoft's validation, Preview, general availability. Needs a verified publisher, a public attestation page, a Marketplace SaaS offer (may be "contact us") and a trial. Monetisation is "Not Supported" in Preview and optional at general availability | Opened: https://learn.microsoft.com/en-us/fabric/extensibility-toolkit/publishing-overview (ms.date 8 Apr 2026); https://learn.microsoft.com/en-us/fabric/workload-development-kit/publish-workload-requirements (ms.date 29 Apr 2026) |
| Workloads listed by Microsoft | Thirteen partner workloads named on Learn (testing, data quality, master data, planning, graph, process mining, mirroring); September 2026 added more. None is described as inferring keys and relationships or as SAP-specific | Opened: https://learn.microsoft.com/en-us/fabric/cicd/partners/partner-integration (ms.date 15 Dec 2025, updated 22 Jul 2026) |

**What this means.** Microsoft now has an answer, in preview and mostly LLM-based, for each link of Krusgraph's
chain: medallion layers (the data engineering agent), relationships (Semantic Link, the Power BI authoring MCP
server), ontology (Generate Ontology, the ontology agent), SAP models (Business Process Solutions). "It builds the
items" is no longer a difference. What the opened pages do **not** describe is the thing Krusgraph's core does:
a named rule for every key and link, counted over whole tables, with what was not counted said. And Microsoft's own
page leaves multi-column keys to the person, which is n226's ground. **Guess:** the stable place for a small vendor is
before Microsoft's generators, not beside them: hand them a model whose keys and relationships have been counted.

### 2.3 Competitors and neighbours

| Group | Who, and what they do | How Krusgraph differs, and where it does not |
| --- | --- | --- |
| Fabric workload vendors | 2TEST and Informatica (data quality tests), Profisee and Semarchy (master data), Lumel (planning), Neo4j (graph), Celonis, Quantexa, SAS, Teradata, Striim. Sources as in 2.2; Semarchy Unverified | They test or repair data, or bring their own engine. None found builds the model from counted keys. Adjacent, not overlapping. They are established companies with sales teams |
| Model tooling | Tabular Editor 3: Enterprise edition listed at USD 950 per seat and year for the first seats, an AI assistant and an MCP server (Unverified: https://docs.tabulareditor.com/te3/editions.html). Microsoft's Semantic Link and Semantic Link Labs | Tabular Editor is where the expert already works, and its Best Practice Analyzer is also deterministic rules. Semantic Link is the nearest in mechanism: it proposes and checks relationships against data, free, in a notebook. Krusgraph's edge over it is packaging (plan, check, review, build in one flow), not the idea |
| dbt and SQLMesh | Fivetran and dbt Labs are reported merged (1 June 2026); a dbt job item in Fabric in preview; a dbt MCP server; MetricFlow open-sourced. Unverified: https://www.fivetran.com/press/fivetran-dbt-labs-complete-merger-to-create-the-data-infrastructure-for-trusted-ai-agents | dbt tests (`unique`, `not_null`, `relationships`) are the same checks, written by hand by an engineer. Krusgraph proposes them. Teams with dbt need an export, not a replacement; `dbt_schema` exists as a draft |
| Catalogs | Purview (2.1). Atlan, Collibra, Alation with Fabric connectors (Unverified, vendor-authored: https://atlan.com/best-data-catalogs-for-microsoft-fabric/) | Catalogs describe and govern; they do not count keys. With Purview's catalog in maintenance mode, the OneLake catalog is where descriptions and evidence should land |
| SAP side | SAP Datasphere and Business Data Cloud (data products); extraction vendors with Fabric destinations such as Theobald Software and ASAPIO; template vendors such as AnalyticsCreator (vendor claim of time saved, Unverified: https://www.analyticscreator.com/blog/best-way-to-integrate-your-sap-data-into-microsoft-fabric); Microsoft's Business Process Solutions | They ship extraction or fixed templates for standard tables. A check against the customer's own rows, including customised tables, is different in kind. But Krusgraph's SAP pack is unverified, matches by table name only and gives a Z table no key. Today the difference is a design intent, not a result |
| Migration tools | Qlik to Power BI and Tableau to Power BI converters, several in Microsoft Marketplace, each claiming a large automated share (vendor claims, Unverified: https://marketplace.microsoft.com/en-ca/product/axisgroupllc1682009980233.automated-qlik-to-powerbi-migration-conversion ; https://www.sparity.com/accelerators/tableau-to-power-bi-migration-accelerator/) | Krusgraph has no migration reader on `main`. Its honest angle is the step the converters skip: proving that the migrated totals equal the old ones, with counted differences. That is a design text today |
| Agents that build | Microsoft's agents (2.2); coding agents driving Fabric through MCP; Databricks and Snowflake semantic layers on their own platforms; ontology vendors such as Timbr over OneLake (Unverified: https://timbr.ai/architectures/microsoft-fabric). No third-party tool that generates Fabric IQ ontologies was found | An LLM agent drafts fast and samples. Krusgraph is slower to impress and can be audited. "No AI" is an audit argument for a careful buyer, not a moat, and the MIT licence means anyone, Microsoft included, may absorb the rules |

**Where Krusgraph is different, stated only as far as the evidence goes:** (1) every proposed key and link names its
rule; (2) the check counts whole tables and says what it did not count; (3) the same engine is in a chat, in a Fabric
item and in open code that a buyer's architect can read; (4) the mascots give a careful tool a friendly face, which
the founder's own test confirmed as worth keeping. **Where it is not different:** building Fabric items; relationship
discovery as an idea; SAP content.

### 2.4 Buyers, budgets and the channel

- **The segment.** DSAG, the German-speaking SAP user group that includes Switzerland, reports about 4 000 member
  companies (Unverified: https://dsag.de/info/). No public count of mid-size Nordic or Swiss industrial companies on
  both SAP and Fabric was found, and no public survey of their data budgets. **Guess:** the reachable first market is
  tens of companies through people the founder already knows, not a segment that can be sized today.
- **The trigger.** Mainstream maintenance for SAP Business Suite 7 is reported to end in 2027, extended maintenance in
  2030 (Unverified: https://sapinsider.org/blogs/sap-support-deadlines-2027-2030-2033/). **Guess:** an S/4HANA move
  re-opens the reporting layer, and with it the question of which platform models the SAP data.
- **The budget.** The repository's only prices are hypotheses: a guided pilot proposed at 15 000 SEK
  (`docs/PILOT.md`), and a decision of 11 November for a 30-day trial then a Marketplace subscription per user, with
  no price set. **Guess:** at this stage money comes as a small fixed pilot or as partner days, not as licences; a
  per-user price is hard to defend for a tool one architect uses for two weeks per data product.
- **Partners.** Consultancies with a Fabric practice in the Nordics and in German-speaking Switzerland are the people
  who sit with the buyer's SAP tables. Two state a Fabric featured-partner status publicly (Unverified:
  https://www.knowit.eu/news-press/knowit-recognized-as-a-microsoft-fabric-featured-partner/). **Guess:** a partner
  adopts a tool that makes its first two weeks at a customer look good and costs nothing to try; the partner-led pilot
  in `docs/PILOT.md` is the right shape.
- **Marketplace.** The standard store fee on a transactable offer is 3 per cent; a transactable SaaS offer must be
  multitenant, use Entra ID and the SaaS fulfilment APIs. Opened:
  https://learn.microsoft.com/en-us/partner-center/marketplace-offers/marketplace-commercial-transaction-capabilities-and-considerations
  (ms.date 22 Jul 2026). Multiparty private offers, where a partner sells the vendor's offer, list Sweden, Norway,
  Denmark, Finland, Germany and Austria; **Switzerland is not in the table**. Opened:
  https://learn.microsoft.com/en-us/partner-center/marketplace-offers/multiparty-private-offers-overview (ms.date 13
  Nov 2026).
- **Co-sell.** "Co-sell ready" needs a published offer, enrolment, a sales contact, a one-pager and a pitch deck.
  "Azure IP co-sell eligible", which also gates counting against a customer's Azure commitment, adds USD 100 000 of
  Azure consumption or of Marketplace billed revenue, a technical validation and a transactable offer. Opened:
  https://learn.microsoft.com/en-us/partner-center/referrals/co-sell-requirements (ms.date 11 Nov 2026). The ISV
  Success programme offers Azure credit and consultations to a vendor with a business application and at least one
  developer. Opened: https://learn.microsoft.com/en-us/partner-center/membership/isv-success (ms.date 5 Oct 2026).
  Practitioner surveys report that few vendors see a large effect from marketplaces alone (Unverified:
  https://state-of-cloud-gtm-report-2026.tackle.io/).
- **MCP directories.** Anthropic's connector directory takes a remote server with OAuth, a title and a read-only or
  destructive hint on every tool, documentation, a privacy policy and a support contact. Opened:
  https://claude.com/docs/connectors/building/submission (no date shown). The official MCP Registry is self-service;
  GitHub's is curated (`docs/MCP-REGISTRY.md`).

**Guess, for a one-person vendor:** Marketplace is a way to be paid and a requirement of the workload listing, not a
source of leads. Co-sell eligibility is far away and should not be planned on. The 20-tenant test route for workloads
is exactly the size of the next six months. The real channel is three or four partners and the Microsoft SAP
architects' goodwill, which is earned by one clean hour on SAP-shaped data.

## Part 3. Synthesis

### 3.1 The five biggest opportunities

1. **Be the counted step in front of Microsoft's generators.** Generate Ontology leaves multi-column keys and
   relationship bindings to the person; the ontology agent samples. A model whose keys and links were counted over
   whole tables is what those tools need as input. Position as the input to Fabric IQ, not as a rival to it.
2. **SAP tables that arrive raw in OneLake.** Extraction is getting narrower and dearer (2.1), so more customers land
   raw tables with MANDT, padded numbers and Z tables. Composite keys carried through (n226) plus a value-normalised
   re-count plus recognition by key-column signature is a concrete, checkable offer that no neighbour found makes.
3. **Evidence as the product.** A dated, exportable record per data product: which keys and links were counted, when,
   over how many rows, what failed, who accepted what. Trust in agents' answers is the most cited pain, Purview's
   catalog is in maintenance mode, and the OneLake catalog is where such a record can land.
4. **The partner's first two weeks.** A free, open, deterministic tool that gives a consultancy a counted map of a
   customer's schema on day two is easy to adopt and needs no procurement. The partner-led pilot already describes it.
5. **Migrations as proof of equal totals.** Not conversion, where many vendors compete with large claims, but the
   reconciliation: the old report's totals against the new model's, with counted reasons for each difference. It uses
   the engine's real strength and needs only a truths file and the difference rules of W10's design.

### 3.2 The five biggest risks

1. **The first real schema.** Name rules meet names they do not know, the answer is thin or wrong, and the one
   audience that offered to recommend the product sees it. Likelihood high until the data can propose keys.
2. **Microsoft ships the same thing.** Each link of the chain has a Microsoft answer in preview, and Ignite is days
   away. Anything positioned as "builds Fabric items for you" can be made redundant by one announcement.
3. **One person.** Operations, security answers, sales, every live test and every deploy. A buyer's risk review will
   ask, and an illness stops everything. Also: founder attention spent reviewing hundreds of agent rounds.
4. **Breadth without depth.** Four products, forty tools, three sources of commerce code, seven designs, demos for
   several industries, and no outside user. Each addition raises the cost of the one thing that matters: a result on
   real data.
5. **Words ahead of evidence.** A sales draft for migrations with nothing built; SAP pages whose sources were not
   re-opened; preview surfaces that change. One sentence a Microsoft or SAP person can disprove costs more than ten
   features earn. The repository's own honesty rules are the control; they need to cover drafts too.

### 3.3 What to stop doing

- **New design texts.** Seven exist and five more are claimed. No design round until one design has become a build
  that ran in Fabric. Close or land the five open claims this week.
- **New surfaces and demos.** Freeze Krusgraph for Lovable as a product name (keep it as a documented client), the
  Younium and planning demos, the industry cards, Databricks and Snowflake drafts, dbt, Great Expectations, Soda and
  OpenLineage drafts, and the App. Keep the code; take them off the default path, as S1 said.
- **Forty tools by default.** Ship the core profile of about twelve.
- **Rounds on wording, mascots and film** while the core has not met Fabric since 9 November. They are pleasant and
  safe, which is why they multiply.
- **Tests that pin sentences** as a main activity (section 1.6). Pin behaviour.
- **Selling what is a text.** No migration, lifecycle, self-healing or multi-domain sentence leaves the repository
  until a build exists. Keep the drafts labelled as drafts.
- **Measuring against a self-written answer key and a self-written "autodetect".** Either run the real tools once and
  record it, or stop quoting the comparison.
- **Planning on co-sell and on a per-user subscription** before one paid pilot has shown what a buyer pays for.

### 3.4 What Microsoft's SAP architects would need to see in the next month

They said they want to try it and to recommend it. A recommendation is their name on it, so the bar is: nothing they
can disprove in an hour. In order:

1. **A deployed build that includes n226**, with the build id and date on the site, and the three mechanisms run once
   in Fabric on the synthetic SAP sample and written down: evidence states, the budget with a resumed check, combined
   keys giving a model with relationships.
2. **The first hour of S1 section 8, rehearsed and recorded** on an SAP-shaped schema of a few hundred tables: every
   schema listed, an answer inside the budget, coverage said, "not checked" never shown as passed.
3. **Their first three probes handled:** a prefixed table name, a Z table, MANDT dropped. Each either works or
   answers "not recognised" or "not supported" in one sentence.
4. **Padded numbers.** Orphans re-counted after trimming and stripping leading zeros, reported as "N of M match
   after stripping leading zeros".
5. **One run on SAP data that is not written from the pack**: a public demo or training data set that the publisher
   may describe, landed in a lakehouse, with the pack's links recorded as verified or wrong per link. Without a real
   SAP system this is the nearest honest thing; with access to a sandbox, `docs/LIVE-TEST-SAP.md` is the script.
6. **A one-page statement of limits** they can forward: what is read, with which permission, what leaves the tenant
   (names and counts, per section 1.7), what is preview, what is not supported, who answers and how fast (stated
   honestly: one person, no promised response time).
7. **A way to try it without the publisher's tenant:** the hosted connector with admin-consent steps, and for the
   workload either the test-tenant route or a recorded walk-through, said plainly.
8. **A scored agent demo, only if 1 to 4 hold:** ten fixed questions with known answers on the synthetic SAP sample,
   published as the count it gets, with the manual steps and the capacity it needs.

What they do not need: migrations, domains, self-healing, more mascots, a price.

### 3.5 A positioning sentence that needs no unproven claim

> Krusgraph proposes keys and relationships for the tables in your Fabric lakehouse from named rules, counts each one
> against your rows and says what it did not count, and builds the Fabric items you choose from what you accepted.
> The engine is open source and uses no AI model.

Each part is backed today: the rules and the count exist and ran live on synthetic data; "says what it did not count"
is n226 (true in code, to be true on the hosted service after the redeploy); the items were created live in the
publisher's own tenant; the licence and the absence of a model can be read in the code. It says nothing about SAP,
speed, correctness on a customer's data, Microsoft or any standard. A shorter form for a headline: "Keys and
relationships for your Fabric tables, counted against the rows."

### 3.6 The evidence each future claim needs

| The claim someone will want to make | What must exist first |
| --- | --- |
| "Works on SAP tables" | A recorded run on SAP data not generated from the pack; per-link verified entries; prefixed, Z and MANDT-less cases in the regression corpus with published scores |
| "Works on S/4HANA / ECC" | The same, per release, with the tables named; CDS views said to be outside until they are not |
| "Works with SAP mirrored through SAP Datasphere" | One run against a mirrored database in Fabric, recorded; today `mirroring.py` says it was never run |
| "Finds N per cent of keys and links" | An answer key written by someone outside the project, on schemas the rules were not tuned on; the score published as it is, misses and wrong ones included |
| "Better than Power BI's autodetect / Semantic Link" | The real tools run on the same schemas, by date and version, with the method published. Not an approximation |
| "Handles large schemas" | A recorded run at 500 and 2 000 tables in Fabric: time per call, items counted, resumes needed |
| "Answers in N seconds / minutes" | A measurement against the hosted service, with the method and date, on a named sample. Otherwise no number |
| "Ask your SAP data in Copilot" | Combined keys live; an agent on the SAP sample; fixed questions scored and published; the manual publishing step and capacity need stated |
| "Keeps your data product healthy" | The health check and the monitor run on a schedule in Fabric for a stated period, with one detected change and one fix by rule, recorded with its undo |
| "Migrate from Qlik / Tableau / Snowflake / Databricks" | A reader on `main` with tests on public sample apps; one end-to-end run with a truths file where totals match; every source-system fact opened and dated |
| "Used by / piloted with" | A customer's written consent. Until then, numbers without a name, or nothing |
| "Available in the Fabric Workload Hub / Microsoft Marketplace" | The listing's own URL |
| "Secure", "GDPR", "ISO 27001" | Never as an adjective. Say what is read, stored and logged; a signed data processing agreement; a third-party test report when one exists; a certificate only if one is held |
| "Recommended by / partner of Microsoft or SAP" | Their written permission for the exact words. Otherwise never |
| "No AI" | Stays true only for the engine and the workload; say so when the chat product is described, since Claude is a model |

## Part 4. Backlog candidates for B1

One line each: id, track, candidate, why, size. Size: **S** about one round; **M** two to four rounds; **L** a week
or more; **F** a founder-only step (a sign-in, a decision, a conversation). Nothing here is decided or ordered; B1
sorts. Where a candidate depends on another, its id is named.

| Id | Track | Candidate | Why | Size |
| --- | --- | --- | --- | --- |
| C01 | core | Let the data propose keys: within the budget, profile columns that are unique and not NULL as key candidates where names give none | The largest credibility risk (S1 mechanism 4); serves every schema without a pack | L |
| C02 | core | Let the data propose links: type-compatible columns whose values are contained in a counted key, ranked by name | Finds links on Z tables and foreign-language names | L |
| C03 | core | Re-count orphans under trim, case fold, leading-zero strip and cast, and report "N of M match after ..." | Padded SAP numbers read as orphans today | M |
| C04 | core | Normalise the parts of a combined key (trim, pad, type) by the same rules as C03, and say which rule was applied | `1` and `0001` do not meet in a combined key | M |
| C05 | core | A key by name is a "candidate" until counted unique in the same call, in every answer | S1 mechanism 4, first half | S |
| C06 | core | SAP pack matching by key-column signature as well as by table name | `ecc_VBAK`, `VBAK_800` and renamed tables get no pack today | M |
| C07 | core | A configurable table prefix and suffix for a source ("names here start with ecc_") | The cheapest fix for prefixed landing zones | S |
| C08 | core | Keys for Z tables from SAP field names used as domains (VBELN, MATNR, KUNNR) when standard tables are absent | A Z-only schema gets nothing today | M |
| C09 | core | S/4HANA tables in the pack: MATDOC, ACDOCA links, business partner | An SAP architect will ask in the first hour | M |
| C10 | core | "Not supported" answers for CDS views and extractor-shaped tables, by recognisable name patterns | Silence reads as broken | S |
| C11 | core | Re-open every public SAP page the pack cites, record URL and date per link, mark what could not be opened | The pack's sources were cited from memory | M |
| C12 | core | Carry partial-key links (a link to part of a composite key) or say precisely why not | Still "not expressible" after n226 | M |
| C13 | core | Combined keys for a warehouse source, not only a lakehouse | `combined_keys.layer()` returns nothing for a warehouse | M |
| C14 | core | Use combined keys in the data agent, the API for GraphQL and the views | Only the model and the ontology read them | M |
| C15 | core | A link to a non-unique target must not count as "holds" | S1 soft spot in `evidence.py` | S |
| C16 | core | Currency and unit awareness for amounts: name the currency column, refuse to sum across currencies, say so | Measures sum across currencies today | M |
| C17 | core | Sign and cancellation handling for document amounts (credit notes, reversed documents) as stated limits or rules | Doubled-total logic ignores them | M |
| C18 | core | One synonym source per language as data files (Swedish, German, Norwegian, Danish, Finnish), not a dict in code | 25 hard-coded entries; a missing word means no match | M |
| C19 | core | Business Central naming: stop keying every table on a bare `No_` | S1 found a wrong key on Sales Line | S |
| C20 | core | A regression corpus of realistic shapes with exact expected plans: Nordic ERP, Business Central, SAP prefixed, Z-only, MANDT dropped | The corpus today was written for the rules | L |
| C21 | core | Row-level regression cases: leading zeros, case, blanks, mixed types, NULL parts | Nothing tests value representation | M |
| C22 | core | A 500, 2 000 and 5 000 table synthetic schema in the tests with time and memory asserted | 5 000 tables was never measured | M |
| C23 | core | Remove the quadratic scans in R3, R4 and R5 candidate search (index by name and type) | They dominate above a few thousand tables | M |
| C24 | core | A scoping step in the engine: propose the 20 most connected tables to start with | Nobody checks 2 000 tables at once | M |
| C25 | core | One definition each for the duplicated helpers (`_family`, line-like words, result limits) | Two copies drift | S |
| C26 | core | The time budget in the workload API, with the same partial result and resume | The editor's check has no budget | M |
| C27 | core | Interrupt a running SQL statement at the deadline where the driver allows it | A statement is only given a shorter timeout | M |
| C28 | core | Evidence state on every answer built from a plan (model, ontology, agent, views): "built from N counted and M uncounted links" | S1: those answers do not say it | S |
| C29 | core | A plan file format with a version, a schema and a hash, so a plan can be re-run and compared | The basis for lifecycle, audit and migrations | M |
| C30 | core | An explanation command: "why is there no link between A and B", listing the rules tried and why each failed | Turns a miss into something a person can correct | M |
| I01 | integration | Run the engine once against a mirrored database in Fabric and record it | `mirroring.py` says never run | F+S |
| I02 | integration | Run once against a warehouse and a SQL database in Fabric and record it | U only | F+S |
| I03 | integration | Run once against SAP data mirrored through SAP Datasphere, if a system the publisher may describe exists | The claim buyers will ask about first | F+M |
| I04 | integration | Land a public SAP-shaped data set that is not generated from the pack in the demo lakehouse, with its licence checked | The nearest honest SAP evidence without a system | M |
| I05 | integration | A read-only "what is in this source" report: schemas, table counts, row counts, last change, in one call | The first five minutes of S1's hour | S |
| I06 | integration | Check tenant settings and capacity needs in the dry run, not at Create | An ontology 403 arrives too late today | M |
| I07 | integration | Write descriptions, tags and the evidence summary to the OneLake catalog for each built item | Purview's catalog is in maintenance mode; the catalog is where governance moves | M |
| I08 | integration | Export the checked plan as dbt tests (`unique`, `not_null`, `relationships`) and run the export in CI | Teams with dbt want the checks in their project | M |
| I09 | integration | Hand a checked semantic model to Microsoft's Generate Ontology and document the path step by step | Position before Microsoft's generator, not beside it | M |
| I10 | integration | Compare a Krusgraph plan with Semantic Link's `find_relationships` on the same lakehouse, as a notebook the customer runs | An honest comparison and a companion story | M |
| I11 | integration | A notebook edition: the engine as a package in a Fabric notebook, no hosted service | Removes the admin-consent wait and the data-leaves-tenant question | M |
| I12 | integration | A companion page for Microsoft's Fabric and Power BI MCP servers: what to use each for, tested together once | Buyers will have both | S |
| I13 | integration | Read an existing semantic model and check its relationships against the rows | Most customers already have models; no build needed to show value | M |
| I14 | integration | Read declared constraints and existing dbt tests as K0 and R0 evidence | Declared knowledge beats names | S |
| I15 | integration | The Connect step, smallest version: detect which Fabric route a source has (mirroring, Copy job) and print the steps | CONNECT-DESIGN, narrowed to advice | M |
| I16 | integration | Decide Snowflake and Databricks: one recorded run each, or remove them from every list | U only and labelled drafts | F |
| B01 | build | Deploy n226 and run evidence state, budget and combined keys live on the SAP sample; record in LIVE-TEST | The three mechanisms have not met Fabric | F+S |
| B02 | build | Silver de-duplication on every counted key, with the number of rows removed reported | Only some key rules de-duplicate today | M |
| B03 | build | The model refuses, or marks, a relationship that failed the check | A failed link must not be built silently | S |
| B04 | build | Gold without a schema-enabled lakehouse, or a clear refusal before Create | `gold.py:112` needs schemas | M |
| B05 | build | Update a report in place | Never updated today | M |
| B06 | build | Measures only for additive amounts, with the unit or currency column named, and "not proposed" otherwise | A SUM rule can sum a unit price | M |
| B07 | build | A calendar and date relationships by counted date columns, with fiscal year as an option | A model needs time; SAP has fiscal variants | M |
| B08 | build | Descriptions and synonyms on model tables, columns and measures from the plan | Vague names are the cited cause of wrong agent answers | M |
| B09 | build | An agent test harness: fixed questions with known answers, run and scored, the score stored | No agent answer was ever scored | L |
| B10 | build | The ontology follows the new ontology experience before the old one retires on 31 January 2027 | A dated break on Learn | M |
| B11 | build | A build manifest: every item created, its id, the plan hash, the evidence state at build time | Needed for retire, promote and audit | S |
| B12 | build | Idempotent Create: a second run changes nothing and says so | "Already built" logic was wrong once (n221) | M |
| B13 | build | Roll back a partly failed Create, or list exactly what exists | Half-built products confuse | M |
| B14 | build | Row-level security carried as a design note in the model draft | Asked by every buyer; not handled | S |
| B15 | build | Direct Lake limits checked in the dry run (table and column counts, fallback) | A model that falls back surprises | S |
| B16 | build | Data products from counted links only, called groupings until built | S1: a ticked product changes nothing in the build | M |
| B17 | build | Freeze the App (Fabric Apps, preview): off by default, one line of status | Preview on preview; not what the architects come for | S |
| L01 | lifecycle | Run the drift monitor once in Fabric and record it | Created 28 October, never run | F+S |
| L02 | lifecycle | "What changed since the last check": names and re-counted keys, one function, inside the budget | One meaning for "drift" (S1) | M |
| L03 | lifecycle | Rename the three things called drift | Naming sent a tester to the wrong tool | S |
| L04 | lifecycle | Git integration: a data product's items in a repository, tried once, with what Fabric ignores listed | PROMOTE-DESIGN's first step | M |
| L05 | lifecycle | Promote with Fabric deployment pipelines: a runbook tried once in the demo tenant | PROMOTE-DESIGN, as evidence not code | M |
| L06 | lifecycle | Version the plan with the product: each Create stores the plan and a diff to the previous | Audit and undo need it | M |
| L07 | lifecycle | A dated evidence report per product, exportable as Markdown and PDF | Opportunity 3 | M |
| L08 | lifecycle | Retire and delete run once live and recorded | U only | F+S |
| L09 | lifecycle | A scheduled re-check with a stored history of counts | Trend of orphans and duplicates over time | M |
| L10 | lifecycle | An owner and a review date per data product, shown on its page | Governance asks who owns it | S |
| L11 | lifecycle | Schema change handling: a new column, a dropped column, a changed type, each with a stated effect on the product | The commonest real change | M |
| L12 | lifecycle | Upgrade notes per version: what a product built with an older plan needs | Preview formats change | S |
| H01 | self-healing | Run the health table and alerts once in Fabric on a schedule, and record a week | U only | F+M |
| H02 | self-healing | A fixed catalogue of findings and their proposed fix by rule (duplicate key, new orphans, NULL in key, type change) | The honest core of "self-healing": proposals | M |
| H03 | self-healing | Dry run, opt-in, audit line and undo for each fix, starting with one: quarantine duplicate key rows in silver | One fix proven end to end beats ten designed | L |
| H04 | self-healing | A quarantine table for rows that fail a key or link check, with counts | Keeps gold clean without deleting anything | M |
| H05 | self-healing | Stop a pipeline on a failed check and say which rows, already built: record a live failing run | Exists; unproven on a failure | S |
| H06 | self-healing | Autonomy levels as a setting with only "propose" enabled | LIFECYCLE-DESIGN, narrowed | S |
| H07 | self-healing | Alerts through Fabric's own means (Activator or email), tried once | No own notification service to operate | M |
| H08 | self-healing | A weekly health summary per product | What a product owner reads | S |
| H09 | self-healing | Detect a refresh that did not run or ran late | The commonest silent failure | M |
| H10 | self-healing | An "explain this finding" text with the rows' counts and the rule, no row values | A finding must be actionable | S |
| U01 | UX | The core tool profile: about twelve tools by default, the rest behind a switch | Forty tools confuse (S1) | S |
| U02 | UX | Rename `validate_plan` to a check name and `app_readiness` out of the way, with aliases | "Check" reached nine tools | S |
| U03 | UX | The coverage headline at the top of every editor page and every chat answer | The visible quality score | S |
| U04 | UX | The editor's shorter flow from WORKLOAD-UX-DESIGN, first step only | The founder's phone test asked for it | M |
| U05 | UX | A map for more than 60 tables: areas, then tables, drawn by evidence state, with the same content as a list | The map caps at 60 tables | L |
| U06 | UX | Search and filter in the review: by state, table, rule | Accept-all over hundreds is unsafe | M |
| U07 | UX | Bulk accept only for counted items; uncounted ones need a deliberate step | Guards the product's own promise | S |
| U08 | UX | A correction path: add a key or link by hand, counted at once | When rules miss, the person must win quickly | M |
| U09 | UX | An onboarding page: what is read, which permission, which tenant settings, the limits, what is not supported | S1: "build first" | S |
| U10 | UX | `/check` limits stated and enforced: file size, rows, a clear message beyond them | The first real export can hang the tab | S |
| U11 | UX | Error answers reviewed as a set: each says what happened, whose side, and the next step | An error must not look like Krusgraph's when it is Fabric's | M |
| U12 | UX | Accessibility pass on the editor: keyboard, contrast, screen reader, colour never the only signal | A requirement in public procurement | M |
| U13 | UX | The editor in Swedish and German | The first buyers | M |
| U14 | UX | An empty-state and a sample mode inside the workload item | Try without touching own data | M |
| U15 | UX | Mascots: one switch to turn them off, remembered | Some buyers want a plain tool | S |
| U16 | UX | Progress and partial results in the chat for long checks | The budget returns parts; show them well | S |
| U17 | UX | A printable one-page summary of a plan for a meeting | Architects carry paper to steering groups | S |
| M01 | migrations | Decide whether migrations are a product line this quarter, before any build | Nothing is on `main`; a sales draft exists | F |
| M02 | migrations | Land or release W7's claimed design and reader | A claim open since 12 November | S |
| M03 | migrations | A truths file: named totals from the old system, compared with the new model, with counted differences | The reconciliation step; opportunity 5 | M |
| M04 | migrations | Ten difference rules, each naming a reason only when it reproduces the number | W10's design, the testable core | L |
| M05 | migrations | A Qlik load script reader on public sample apps: tables, joins, synthetic keys listed | The smallest proof for Qlik | L |
| M06 | migrations | Set analysis to DAX: classify expressions as translatable, needs review, not translatable; translate none automatically at first | An inventory is honest; a converter is a claim | M |
| M07 | migrations | A Tableau workbook reader: data sources, joins, level-of-detail expressions listed | The same for Tableau | L |
| M08 | migrations | Re-open and date every Snowflake, dbt, Databricks and Qlik fact in W10's design | All marked Unverified by its own text | M |
| M09 | migrations | An assessment report: what a migration contains, counted, with nothing promised | A partner can sell an assessment | M |
| M10 | migrations | ECC to S/4HANA: map the pack's ECC tables to their S/4HANA successors and compare totals across | The trigger event in the segment | L |
| M11 | migrations | Hold the migration sales draft back until M03 exists | Words ahead of evidence | S |
| M12 | migrations | A list of what migration tools in Marketplace claim, re-read with pages opened | The neighbour scan here is Unverified | S |
| S01 | sales | Rehearse and record S1's first hour on an SAP-shaped schema of a few hundred tables | What the Microsoft SAP architects will do | F+M |
| S02 | sales | A one-page statement of limits to forward | Section 3.4, item 6 | S |
| S03 | sales | A 20-minute demo script on the SAP sample that shows a miss and how it is corrected | Showing a miss earns trust | S |
| S04 | sales | Find one outside reviewer to run `/check` on own tables and write down right and wrong | MISSING-EVIDENCE row 8, open since 1 November | F |
| S05 | sales | The first pilot: one company, one workspace, one outcome, written consent for what may be said | MISSING-EVIDENCE row 9 | F |
| S06 | sales | A partner kit: the partner-led pilot, a checklist for day one, what the partner may say | The real channel | M |
| S07 | sales | A short list of consultancies with a Fabric and SAP practice in the Nordics and Switzerland, from public pages, opened and dated | Partner names here are Unverified | S |
| S08 | sales | Test the pilot price hypotheses with three conversations and write down the answers | Prices are hypotheses | F |
| S09 | sales | Decide the unit of price: per data product, per workspace or per user, after S08 | Per user is hard to defend for an architect's tool | F |
| S10 | sales | A security questionnaire answered once (a common format), kept current | Every enterprise buyer sends one | M |
| S11 | sales | A data processing agreement a customer can sign | `DPA-DRAFT.md` is a draft | F+S |
| S12 | sales | An objection page from real questions: "why not Microsoft's own agents", "why not Tabular Editor", "why not dbt" | Part 2 gives the material; keep it factual | S |
| S13 | sales | A follow-up note for the Microsoft SAP architects after each session: what worked, what did not, what changed | Keeps the one warm audience informed | F |
| S14 | sales | A reference architecture drawing: where Krusgraph sits beside extraction, OneLake, Fabric IQ and Copilot | Architects think in pictures; also asked for co-sell later | S |
| S15 | sales | A Swiss route to purchase, since multiparty private offers do not list Switzerland | Stated on Learn, 13 November 2026 | F |
| K01 | marketing | Close S1 section 4 line by line and record which sentences changed | n224 reworded; nobody re-audited | S |
| K02 | marketing | The positioning sentence of 3.5 on the home page, README, `server.json` and `llms.txt` | One sentence everywhere | S |
| K03 | marketing | Publish the regression scores as they are, misses included | An honest score earns more than a headline | S |
| K04 | marketing | One article: "Counting keys before you build a semantic model", with the method, no product claim | Teaches the idea; draws the right reader | M |
| K05 | marketing | One article on SAP composite keys in Direct Lake models, on synthetic data | The n226 story, useful on its own | M |
| K06 | marketing | A short film of the first hour, recorded live, uncut where possible | Evidence that it runs | F+M |
| K07 | marketing | Remove or label the industry cards and any timing sentence still on the site | S1: cut | S |
| K08 | marketing | The build id and deploy date in the site's footer | Nobody can tell what is deployed | S |
| K09 | marketing | A changelog page for users, not rounds | The CHANGELOG is written for agents | S |
| K10 | marketing | The founder's GitHub settings and the v0.8.0 release from FOUNDER-TODO | Open since 10 November | F |
| K11 | marketing | A talk proposal for a Nordic or Swiss Fabric or SAP user-group meeting | Where the segment meets | F |
| K12 | marketing | A "what we do not do" page | Fits the brand; saves sales time | S |
| K13 | marketing | Re-read Part 2 after Ignite and correct this file's market section | Ignite is reported for 17 to 20 November | S |
| T01 | standards and certification | The workload's publishing requirements as a checklist with the state of each: verified publisher, attestation page, SaaS offer, trial | Learn lists them; HUB-READINESS is from 9 November | S |
| T02 | standards and certification | Register the permanent workload name, a founder decision that cannot be undone | The first upload reserves it for good | F |
| T03 | standards and certification | The test-tenant route: the steps for one outside tenant to add the workload, tried once | Up to 20 tenants without certification, per Learn | F+M |
| T04 | standards and certification | Marketplace SaaS offer as "contact us" first | Required for a workload listing; no price needed yet | F |
| T05 | standards and certification | Anthropic's connector directory: title and read-only or destructive hint on every tool, then submit | Requirements on the submission page | S+F |
| T06 | standards and certification | A third-party penetration test of the hosted service, scoped small | Self-assessment only today | F+M |
| T07 | standards and certification | ISO 27001: decide whether to pursue, and when; until then keep the self-assessment labelled as such | Buyers ask; a one-person company cannot certify cheaply | F |
| T08 | standards and certification | WCAG 2.1 AA review of site and editor with a written result | Procurement in the public sector | M |
| T09 | standards and certification | An OpenLineage and a DCAT or data-contract export decided: keep one, test it against a real consumer, drop the rest | Drafts without a consumer | S |
| T10 | standards and certification | A software bill of materials and a vulnerability report per release, linked from the trust page | `sbom.yml` and `audit.yml` exist; publish the output | S |
| T11 | standards and certification | A signed release and container image | Supply-chain questions from IT | M |
| T12 | standards and certification | ISV Success: read the current terms and decide | Azure credit and consultations, per Learn | F |
| T13 | standards and certification | The EU AI Act and "no AI": a short factual note on what the engine is and what the chat product is | Buyers' legal teams will ask | S |
| O01 | operations | Name a second person with access to Azure, the Entra app, GitHub, the domain and Partner Center | RISK-REGISTER R6 | F |
| O02 | operations | Run `--doctor` against the real subscription and record secret and certificate dates | The register asks for it | F |
| O03 | operations | Separate the site from the service: two container apps, or the site as static files | A marketing visit and a build share 0.25 CPU | M |
| O04 | operations | Keep at least one replica warm for the service | Cold starts on the first call of a demo | F+S |
| O05 | operations | Durable background operations: an operation survives a replica restart or is resumable | Lost operations today | M |
| O06 | operations | Rate limits shared across replicas, or one replica | In-memory buckets per replica | M |
| O07 | operations | A staging environment and a deploy from CI with a manual approval | Only the founder deploys, by script | M |
| O08 | operations | A nightly contract test against live Fabric in the demo tenant: each API family once, with an alert | Preview formats change without notice | L |
| O09 | operations | Uptime and error monitoring with an alert to a phone | One person cannot watch logs | S |
| O10 | operations | A status page | Buyers ask where to look | S |
| O11 | operations | Log retention and content checked against the trust page, with a test | Docs and code must agree | S |
| O12 | operations | A backup and restore drill for the table storage, recorded | `--backup` exists; a restore was not recorded | S |
| O13 | operations | An incident drill from INCIDENT-RESPONSE, recorded | A plan nobody ran | S |
| O14 | operations | Split `server.py`: tools, routing and site serving in separate modules | 3 606 lines; every round touches it | M |
| O15 | operations | One set of tool definitions for the hosted and the local server | Two parallel sets | M |
| O16 | operations | Narrow the 147 broad `except Exception` in the engine paths first | Swallowed errors hide real faults | M |
| O17 | operations | Remove or archive dormant modules (`entitlements.py` superseded by billing; demo modules) | Less to maintain | S |
| O18 | operations | Live-test automation: a script that runs the LIVE-TEST checklist against the demo tenant and writes the protocol | Every live row waits for one person's evening | L |
| O19 | operations | Coverage measurement, type checking and a linter in CI | Section 1.6 | S |
| O20 | operations | Fewer text-pinning tests: one snapshot per page, behaviour tests for the rest | Section 1.6 | M |
| P01 | company | A rule for rounds: no new design claim while five are open; a claim expires after 48 hours | Five unlanded claims | S |
| P02 | company | A weekly live day: the founder runs what the week built, in Fabric, and records it | Building outruns proving | F |
| P03 | company | A work-in-progress limit: one track at a time until the first hour holds | Breadth without depth | F |
| P04 | company | Decide the three products and their order, in writing; Lovable becomes a client, not a product | Four names on the site | F |
| P05 | company | A 90-day goal with one measure: one outside party ran it on own data and wrote down the result | Gives the backlog a test | F |
| P06 | company | Legal basics checked by a lawyer: terms, the data processing agreement, liability for wrong numbers | A wrong relationship gives wrong figures | F |
| P07 | company | Trade mark and name check for Krusgraph and the workload name in the EU and Switzerland | Before the name is reserved for good | F |
| P08 | company | Insurance for professional liability and cyber risk | Asked in enterprise procurement | F |
| P09 | company | A continuity note for customers: what keeps working if the publisher stops (their items, the open code) | The honest answer to the single-founder question | S |
| P10 | company | Decide on a first collaborator: a second engineer, a partner company, or a maintainer from the community | Risk 3 | F |
| P11 | company | The open-source stance in writing: what stays MIT, what a paid offer adds | Absorption risk; buyers ask what they pay for | F |
| P12 | company | A contributor path that an outsider can follow in an hour, tried by one outsider | The claims convention is written for agents | M |
| P13 | company | Keep person names and tenant ids out of public docs; one pass over `docs/` | Found in this read | S |

### Count per track

| Track | Candidates |
| --- | --- |
| core | 30 |
| integration | 16 |
| build | 17 |
| lifecycle | 12 |
| self-healing | 10 |
| UX | 17 |
| migrations | 12 |
| sales | 15 |
| marketing | 13 |
| standards and certification | 13 |
| operations | 20 |
| company | 13 |
| **Total** | **188** |

## Limits of this analysis

- No live run, no customer conversation, no SAP system. Part 1 is what the repository says about itself.
- Part 2 could open two hosts. Everything marked Unverified should be opened from a network that allows it before it
  is quoted anywhere, and all of it re-read after Ignite.
- The guesses are marked. The segment size, the budgets and the partner behaviour are guesses throughout.
- The backlog is a long list on purpose. Its order, and what is dropped, is B1's and the founder's.
