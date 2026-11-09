# Krusgraph and Fabric IQ at scale

Round n182. A design note, docs only, nothing implemented here. Written 9 November 2026, after a Microsoft talk on
Fabric IQ, ahead of a meeting with Microsoft on 11 or 13 November.

The audience's comment at the talk: all of this is complex. Fabric IQ gives the building blocks. Krusgraph builds them
for you from your tables and checks them against your rows.

How to read the status columns:

- **Verified** means a learn.microsoft.com page was opened on 9 November 2026 and says it. The link and the page's
  date (ms.date / last updated) are given.
- **Unverified** means no official page was found that says it. Treat it as an open question, not a fact.
- The Fabric blog (blog.fabric.microsoft.com) could not be opened from the session that wrote this. No blog post is
  cited as verified.

---

## 1. What Fabric offers today (research)

### 1.1 The ontology item

Key pages:

- Ontology definition, TMDL format ("generation 2"):
  https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/ontology-definition
  (ms.date 2026-09-10, updated 2026-09-29)
- Ontology (old) definition, JSON format:
  https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/ontology-old-definition
  (2026-08-19, updated 2026-09-29)
- REST operations: https://learn.microsoft.com/en-us/rest/api/fabric/ontology/items (updated 2026-09-23). Create,
  Get, List, Update, Delete, Get Definition (with `?format=`), Update Definition. The Get Definition page (updated
  2026-10-19) says "Ontology item is currently in Preview".
- Overview: https://learn.microsoft.com/en-us/fabric/iq/ontology/overview (2026-10-16)
- Rules: how-to-use-rules (2026-09-15), under learn.microsoft.com/en-us/fabric/iq/ontology/
- Graph from an ontology: how-to-use-ontology-graph (2026-09-18), same folder
- Ontology MCP server: how-to-use-ontology-mcp-server (2026-04-14, updated 2026-10-01), same folder

The definition parts in the TMDL format: `.platform`, `database.tmdl`, `model.tmdl`, `tables/*.tmdl` (Direct Lake
partitions and measures), `entities/{namespace}#{name}.tmdl`, `relationships.tmdl`, `entityRelationships.tmdl`,
`expressions.tmdl`, `namespaces/*.tmdl`, `rules/*.tmdl`.

| Building block (Microsoft's slide) | Status | Writable via REST / definition? | Source |
|---|---|---|---|
| Ontology item, Items API | Preview | Yes | Verified: ontology/items (2026-09-23) |
| Namespaces | Preview | Yes: `namespaces/*.tmdl`, references as `ns#name` | Verified: ontology-definition |
| Entity types | Preview | Yes: `entities/*.tmdl` | Verified: ontology-definition |
| Properties | Preview | Yes: string, int64, double, dateTime, boolean, decimal, Any, `TimeSeries<T>` | Verified: ontology-definition |
| Complex types | Preview | Yes: `complex` (struct, timeSeries; no array kind) | Verified: ontology-definition |
| Entity keys | Preview | Yes: `keyProperty`. Keyless entity types are allowed. | Verified: ontology-definition, overview |
| Relationships | Preview | Yes: `entityRelationships.tmdl`, backed by a table relationship or a junction table | Verified: ontology-definition |
| Binding to lakehouse tables | Preview | Yes: backing tables with a Direct Lake partition | Verified: ontology-definition |
| Binding to eventhouse | Preview | Old JSON format only (`KustoTable`, time series). Not shown in the TMDL format. | Verified: old definition; overview lists eventhouse as a source |
| Metrics | Preview | Partly. `explicit` metrics (KQL, SQL, generic, natural language) yes. Metrics projected from semantic-model DAX measures: no. | Verified: ontology-definition |
| Taxonomy and metadata | Preview | Descriptions (`///`), `synonym`, `annotation`, `resourceLink`: yes. A separate "taxonomy" object: not documented. | Verified for the four; taxonomy Unverified |
| Rules | Preview | Yes: `rules/*.tmdl`, natural-language statements. Not executed. | Verified: how-to-use-rules |
| Actions | Not documented | No. The rules page says the ontology does not execute actions. Activator alerts were in the old experience only. | Verified: how-to-use-rules |
| Inheritance | Preview, rolling out | Yes: `baseEntityType` (cannot change later), `redefines`, `reusableProperty` | Verified: ontology-definition |
| Versioning | Preview | Named version history in the portal. No API found. | Verified (portal): overview. API: Unverified |
| Health | Unknown | No page found | Unverified |
| Graph from the ontology | Preview | Portal only ("Manage graph"). Makes a separate graph model item. Needs a key on every entity; lakehouse or mirrored Delta sources only. | Verified: how-to-use-ontology-graph |
| Ontology MCP endpoint | Preview | `https://api.fabric.microsoft.com/v1/mcp/dataPlane/workspaces/{ws}/items/{id}/ontologyEndpoint`. Service principals not supported yet (known issue). | Verified: how-to-use-ontology-mcp-server |
| Old JSON format retires | Dated | The old experience retires 31 January 2027 | Verified: old definition page |

Overall status:

- The IQ workload is labelled "IQ (preview)", and the ontology is preview. No Learn page says it is GA.
  Verified: https://learn.microsoft.com/en-us/fabric/iq/overview (2026-07-08).
- Fabric IQ in Microsoft 365 Copilot Chat is GA, but it answers from Power BI reports and semantic models.
  Ontologies and data agents need a published Microsoft 365 agent. Verified:
  https://learn.microsoft.com/en-us/fabric/iq/connectors/microsoft-365-copilot-overview (2026-09-15).
- The public preview announcement at Ignite 2025 (Fabric blog, "From data platform to intelligence platform:
  introducing Microsoft Fabric IQ"): Unverified, blog not reachable.
- "Fabric IQ with Power BI" as a plugin in Copilot Cowork, as on the slide: no Learn page found. Unverified.

### 1.2 Graph and data agent

| Feature | Status | Via REST / definition? | Source |
|---|---|---|---|
| Graph model item | Unclear: the graph overview has no preview banner, the IQ overview calls it preview | Yes: create, get and update definition (`dataSources`, `graphDefinition`, `graphType`, `stylingConfiguration`). Execute Query is beta. | Verified: rest/api/fabric/graphmodel/items (2026-02-04); graph-model-definition (2026-07-01) |
| Fabric data agent | GA | Yes: definition parts under `Files/Config/...`, and the staging API | Verified: fabric/data-science/concept-data-agent (2026-10-21); data-agent-definition (2026-02-11) |
| Data agent with an ontology as source | Preview | Portal: yes. The definition's datasource type list has no ontology value. | Verified: data-agent-add-datasources (2026-08-31). Via API: Unverified |

### 1.3 Semantic model features that ground Copilot

| Feature | Status | Via REST / definition? | Source |
|---|---|---|---|
| Descriptions on tables, columns, measures | GA | Yes: `///` lines in `definition/*.tmdl` | Verified: analysis-services/tmdl/tmdl-overview (2026-06-11); semantic-model-definition (2026-03-18) |
| Synonyms (linguistic schema) | GA, Q&A going away | Yes: `cultures/*.tmdl` with linguistic metadata | Verified: tmdl-overview |
| Power BI Q&A | Deprecated | Learn: "Q&A experiences are going away in February 2027" | Verified: power-bi/natural-language/q-and-a-intro (2026-09-10). A December 2026 date seen elsewhere: Unverified |
| Prep data for AI (AI schema, verified answers, AI instructions) | Preview | Stored with the model. The definition page's sample tree shows a `Copilot/` folder (`Instructions/instructions.md`, `VerifiedAnswers/`, `schema.json`, `examplePrompts.json`, `settings.json`), but its parts table does not list it. Changes deployed by Git need a refresh. "Approved for Copilot" is a portal setting. | Verified: power-bi/create-reports/copilot-prepare-data-ai (2026-09-16). Writing the folder via REST: Unverified |
| Endorsement (promoted, certified, master data) | GA | No public API to set it was found | Verified (portal): fundamentals/endorsement-promote-certify (2026-02-17). API: Unverified |
| Domains | GA | Yes: admin API (create domain, assign workspaces, roles) | Verified: rest/api/fabric/admin/domains (2025-09-17) |
| Tags | GA | Yes: apply, unapply, list | Verified: rest/api/fabric/core/tags (2025-07-23) |
| OneLake catalog search | Preview | Yes: `POST /v1/catalog/search`, filters on type and workspace only | Verified: rest/api/fabric/core/catalog/search (2026-11-06) |
| Item description | GA | Yes: Update Item, 256 characters | Verified in specs, see `fabric_backend/catalog.py` header |

Definition pages for the other items Krusgraph writes all exist: Lakehouse (2026-03-30), Report (PBIR, 2026-03-18),
GraphQLApi (2025-05-14), DataAgent (2026-02-11), Notebook (2025-07-02), under
learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/.

What this means for us:

1. Most ontology building blocks **are** writable through the definition, in preview. Namespaces, inheritance,
   synonyms, rules and descriptions can be generated.
2. Versioning, health, graph creation from an ontology, endorsement and "Approved for Copilot" are portal-only or
   undocumented. We should not build on them yet. We ask Microsoft (section 5).
3. Actions are not an ontology feature today. Rules are text.

---

## 2. Each building block against the Krusgraph engine today

Code read on 9 November 2026 at `a6b4c2a`.

| Building block | Krusgraph today | Status | Where |
|---|---|---|---|
| Entity types | One per keyed table, named from the table | Done | `fabric_backend/ontology.py` (`ontology_parts`, `entity_name`) |
| Properties and types | Column types mapped to ontology types; `decimal(p,s)` binds as string | Done | `ontology.py` `_TYPES`, `prop_type` |
| Keys | Inferred (rules K0-K5), checked against rows for uniqueness and empty values | Done | `infer.py`; `evidence.py` `validate` |
| Relationships | Inferred (rules R0-R5), each checked against the rows for orphans | Done | `infer.py`; `evidence.py` `validate`; `ontology.py` `entityRelationships.tmdl` |
| Data bindings | Direct Lake binding to the source lakehouse; a binding checklist for the portal route | Done | `ontology.py` `ontology_parts`, `bindings` |
| Create and update the item | `ontology_draft` (read only), `create_ontology` (dry run by default, updates in place). Created live on 28 October 2026. | Done | `server.py:876`, `server.py:916`; `deploy.py:359`; `tool_status.py` |
| Namespaces | One namespace, `default`, per ontology | Partial | `ontology.py:157`, `:178` |
| Descriptions | Every entity and relationship carries the rule that found it | Partial (rule text, not business meaning) | `ontology.py:204`, `:222` |
| Synonyms | Used inside inference to match names; not written to the ontology or the model | Missing | `infer.py` `_synonym_words` |
| Metrics | Sum and count measures in the semantic model, with the reason; none in the ontology | Partial | `semantic_model.py` (measures), `amounts.py`, `level_measures.py` |
| Rules | None written | Missing | n/a |
| Actions | n/a (not a Fabric feature today) | n/a | n/a |
| Inheritance, complex types | None | Missing | n/a |
| Versioning | Our side: the review file and outputs are versioned, nightly plan snapshots are saved. Fabric's version history: not used. | Partial | `workload/.../ModelItemDefinition.ts`; `monitor.py` `snapshot`, `save` |
| Health | Row check (keys, links); nightly drift monitor that reports schema changes and what they reach | Partial (not shown as ontology health) | `evidence.py`; `monitor.py`; `server.py:2032`, `:2048`; `server.py:1283` `plan_drift` |
| Semantic model | Direct Lake TMDL from the plan, relationships with cardinality, date table, measures. Created live on 29 October 2026. | Done | `semantic_model.py`; `server.py:967`, `:1471` |
| Model descriptions | On measures and the date table only; not on tables or columns | Partial | `semantic_model.py:244`, `:452` |
| Linguistic schema / prep data for AI | Not written | Missing | n/a |
| Data agent instructions | AI instructions, data source instructions and example questions from the plan | Done (no recorded live run) | `data_agent.py`; `server.py:1687` |
| Domains, data products | Proposed domains from the graph, each with an ODCS v3.2.0 contract | Partial (draft; no Fabric domain is created) | `domains.py` |
| OneLake catalog | Item descriptions and tags drafted with the exact REST calls; not sent | Partial | `catalog.py`; `server.py` `export_item_definitions` with `items=["catalog"]` |
| Several sources in one plan | One source and one schema per plan; shortcuts into one lakehouse work today | Missing (design note exists) | `docs/MULTI-SOURCE.md` |
| Model item as manifest | `review.json`, `source.json`, `outputs.json` (outputs, created ids, data product), `item.json` | Partial (no owner, no contract) | `workload/Workload/app/items/ModelItem/ModelItemDefinition.ts`; `workload_api.py` |
| Cleanup | Tools never delete. The Model item updates only items whose ids it recorded as created. | Missing | `server.py:916` docstring; `workload_api.py` header |

One thing to check, not a known bug: the Learn page names entity parts `entities/{namespace}#{name}.tmdl`. Krusgraph
writes `entities/{name}.tmdl`. The live create on 28 October worked. We should run a Get Definition on that item and
compare before we add namespaces.

---

## 3. Scale design

The idea: a team does not want one ontology. It wants one per data product, and a shared core across them. Krusgraph
proposes each piece from checked data, shows it as a diff, and builds it on Create.

### 3.1 Microsoft's four "when to use the ontology" cases

| Case | How Krusgraph helps today | What is missing |
|---|---|---|
| **(a) Connecting data across systems** (customer in CRM, orders in ERP, deliveries in a warehouse) | One source at a time: keys and links checked against rows. Across sources: only when they are shortcuts in one lakehouse. | Plans across several lakehouses, shared keys checked across them, shared entities proposed. **This is where the row check matters most.** |
| (b) Modelling real-world operations (machines, lines, sensors, maintenance) | Entities and links from tables in a lakehouse | Eventhouse and time-series bindings; complex types |
| (c) Consistent meaning (Revenue, Customer, Product defined once) | Measures with a reason; amount level checks (a header amount is not summed per line) | Measures as ontology metrics; descriptions and synonyms in business words; one definition shared by model and ontology |
| (d) Operational apps and AI (a delayed shipment belongs to an order and a customer) | GraphQL API, data agent, app (Rayfin, n181), all from the same checked links | Ontology as data agent source via API (not documented) |

**Lead case (a).** A name match across systems is a guess. `customer_id` in a CRM and `KUNNR` in an ERP may or may
not be the same customer. An ontology that links them without a check gives Copilot confident wrong answers.
Krusgraph would:

1. Plan each source as today.
2. Propose cross-source links from shared keys (same type, name rules, the SAP and Salesforce packs).
3. Count the overlap on the rows: how many CRM customers exist in the ERP and the other way round. Show the share.
4. Propose a shared entity (`Customer`) in a shared namespace only when the overlap passes. Otherwise propose two
   entities and a link, or nothing, and say why.
5. Show it as a diff for review, then build.

### 3.2 The pieces

| # | Piece | What it means | Needs from Fabric | API status | Effort | Order |
|---|---|---|---|---|---|---|
| 1 | Namespace per domain or data product | Each data product writes its own namespace; shared entities live in a `core` namespace | `namespaces/*.tmdl`, `ns#name` references | Verified (preview) | S | 1 |
| 2 | Model item as manifest | Add `owner`, `version` and the ODCS `contract` (from `domains.py`) to `outputs.json`, next to sources, checked links and created ids | Nothing new (our item definition) | n/a | S | 2 |
| 3 | Descriptions, synonyms, metrics for Copilot | Business descriptions on tables, columns and entities; synonyms from name rules and packs; measures with a description; data agent instructions already exist | TMDL `///`, `cultures/*.tmdl`, ontology `synonym`; `Copilot/` folder | Descriptions and synonyms Verified; `Copilot/` folder via REST Unverified | M | 3 |
| 4 | Health from the row check and drift | One health line per data product: keys and links passed, failed, not checked; schema changes since last night and what they reach | Nothing (our own check and monitor). A Fabric health surface: none found. | Health in Fabric Unverified | M | 4 |
| 5 | Versioning when the schema changes | The drift monitor finds a change; Krusgraph proposes the new definition as a diff; on accept it bumps the manifest version and calls Update Definition | Update Definition | Verified. Fabric's named versions: portal only | M | 5 |
| 6 | Ontologies across several lakehouses (case a) | Plans per source, cross-source links checked on rows, shared entities proposed, reviewed as a diff | Bindings to tables in several lakehouses in one ontology | Bindings Verified; multi-source binding in one item: confirm with Microsoft | L | 6 |
| 7 | Cleanup and rebuild | Delete only items whose ids are in `outputs.json`'s created list, after a dry run that lists them; rebuild from the plan | Items Delete per type | Verified (ontology Delete); per other type: check specs | M | 7 |
| 8 | Inheritance and complex types | Propose a base type when tables share a key and most columns (e.g. `Party` for customer and supplier) | `baseEntityType`, `complex` | Verified (rolling out) | M | later |
| 9 | Rules | Write each checked key and link as a natural-language rule ("every order has a customer: 99.8% of rows checked") | `rules/*.tmdl` | Verified (text only) | S | later |
| 10 | Domains and tags in Fabric | Send the catalog draft: tags and descriptions; domains only for admins | Tags apply, Update Item, admin domains | Verified | S | after 3 |

Not planned: actions (not a Fabric feature), endorsement (no API found, and a human decision), graph creation from
the ontology (portal only).

---

## 4. Positioning

**One sentence:** Fabric IQ gives you the building blocks; Krusgraph builds them for you from your tables, checked
against your rows.

**Line to test:** "One checked plan, every starting point."

Three proof points that are true today:

1. Every key and link carries the rule that found it, and can be counted against the rows before anything is built
   (`infer.py`, `evidence.py`).
2. The same plan becomes a semantic model, a report, an ontology, an API for GraphQL, a data agent, silver and gold
   notebooks and a pipeline, consistent with each other (`workload_api.py` `KINDS`).
3. Nothing changes in Fabric until Create: every creating tool is a dry run by default, and the Model item never
   writes over an item of the same name that it did not build (`workload_api.py`).

Microsoft's "best starting point" slide, and what Krusgraph builds from one plan:

| Requirement (Microsoft's slide) | Best starting point | Krusgraph builds it today? |
|---|---|---|
| Store, transform, process data | Lakehouse or warehouse | Yes: silver and gold notebooks, pipeline, views |
| Power BI reports, trusted KPIs | Semantic model | Yes: semantic model and a report |
| Shared entities and relationships for AI agents | Ontology | Yes, one source per ontology (preview item) |
| Relationship paths, dependencies, impact | Graph, optionally from an ontology | Partly: our own path finding (`join_path`); Fabric's graph is made from the ontology in the portal |
| Natural-language questions over a domain | Data agent, with ontology when useful | Yes: data agent over the source; ontology as its source not via API |
| Apps on the data | (not on the slide) | API for GraphQL today; app (Rayfin, preview) in n181 |
| Budgets and forecasts | Fabric Planning | Out of scope |

Today vs direction:

| Today | Direction |
|---|---|
| One source and schema per plan | Several lakehouses, shared entities from checked shared keys |
| One `default` namespace | A namespace per data product, a shared core |
| Descriptions name the rule | Business descriptions and synonyms for Copilot |
| Measures in the semantic model | The same metrics in the ontology |
| Row check and nightly drift report | A health line per data product, a proposed new version on schema change |
| Creates and updates, never deletes | Cleanup and rebuild of what Krusgraph made |
| Domain proposals and ODCS contracts as drafts | Owner, version and contract in the Model item |

We make no claims about speed, compliance or endorsement. Microsoft does not endorse or partner with Krusgraph.

---

## 5. For the Microsoft meeting

**The story in five bullets**

- Fabric IQ has the right building blocks. Customers find them complex to assemble.
- Krusgraph reads the tables, proposes keys and links with the rule behind each, and counts them against the rows.
- One reviewed plan becomes the semantic model, report, ontology, data agent, GraphQL API and app, consistent with
  each other.
- Everything is a dry run until Create, inside the customer's Fabric, as the signed-in user.
- Next: ontologies across several sources, where checking shared keys on the rows matters most.

**Demo path** (synthetic shop data)

1. Plan: open the Krusgraph Model item, pick the lakehouse; keys and links appear with their rules.
2. Check: count every key and link on the rows; show one that fails and why.
3. Dry run: pick outputs (model, report, ontology, data agent); show what would be created.
4. Create: build them; open the ontology and the report in Fabric.

**Five questions to ask Microsoft**

1. Which ontology features are writable via the definition API, and which will stay portal-only (graph from
   ontology, named versions, data agent with an ontology source)? Is the `entities/{ns}#{name}.tmdl` naming required?
2. What is the roadmap for namespaces across items, versioning and a health signal for ontologies? Is there an API
   planned for version history?
3. Can a partner workload item (the Krusgraph Model) publish to or sit behind the Fabric IQ MCP endpoint, and when
   will service principals work there?
4. How does Copilot's grounding choose between a semantic model's prep-for-AI settings and an ontology over the same
   tables? Is writing the `Copilot/` folder through the semantic model definition supported?
5. What does a Workload Hub listing need for a workload that creates IQ items, and is there a preview path for
   partners?
