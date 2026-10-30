# {{PRODUCT}} docs

See how your business tables really connect – with the proof behind every link – so your reports, apps and agents get the numbers right.

- The proof: every key and link comes with the rule or source behind it, and is checked against your data.
- The errors before anyone sees them: the total that doubles, keys that are not unique, references with no matching row.
- SAP knowledge from public sources: keys with MANDT and the order-to-cash links for VBAK, VBAP and their neighbours, each with its source.
- One plan for what you build: the same reviewed plan drafts a GraphQL API, a Power BI model, a Fabric IQ ontology and a data agent.

Connect {{PRODUCT}} to Claude to inspect a Fabric schema, review the suggested relationships, check them against your
data and build from the plan. Start with the connection guide, or try the [guided demo](/check?example=sample&guide=1) and
[the example's map](/check?example=sample#check-map) without an account. The tool reference explains what each tool reads, returns or changes, and
how far it has been tested.

## Why {{PRODUCT}}

**{{PRODUCT}} stores no table contents.** It reads your lakehouse, warehouse or SQL database where it is (lakehouses are
tested end to end; the other sources are Experimental until a live run). Plans come from table and column metadata,
checks run as counting queries in Fabric, and the samples and query results you ask for pass through to your MCP
client without being kept. What it creates is created in Fabric.

**Rules you can check, not guesses.** Keys and relationships come from documented rules ([K0–K5, R0–R4](#how-relationships-are-inferred))
and, for SAP tables, a pack built from public SAP documentation (`sap_pack_draft`: Draft only, tested on a synthetic
SAP schema, not on an SAP system). Every key and relationship shows the rule or source behind it. Columns that could
mean more than one thing are reported, not guessed.

**Checked against the data.** `validate_plan` counts, per key, the rows, the empty key values and the distinct values,
and, per relationship, the references with no matching row. It is a separate step: run it before you create anything,
because `create_backend` does not run it for you.

**One reviewed plan, several Fabric items.** The same plan drafts the API for GraphQL, a Power BI semantic model, a
Fabric IQ ontology, views, a data agent and silver notebooks, so they agree on how the tables relate. How far creating
each one has run live differs; the words below come from the same list as the [tool reference](#test-status):

- the API for GraphQL: {{CREATE_API_STATUS}}
- the views: {{SHORT_CREATE_VIEWS}}
- the Power BI semantic model: {{SHORT_CREATE_SEMANTIC_MODEL}}
- the Fabric IQ ontology: {{SHORT_CREATE_ONTOLOGY}}
- the data agent: {{SHORT_CREATE_DATA_AGENT}}
- the silver notebooks: {{SHORT_CREATE_SILVER_NOTEBOOK}}

**Your Microsoft account and permissions.** On the hosted service you sign in with your work account, and {{PRODUCT}}
acts with delegated permissions as you, so it sees only what your Fabric permissions allow. An app built on the API
has its own identity and access settings; see [App access](#app-access) before you publish one.

**Drafts first.** Every creating tool except `{{NO_DRY_RUN_TOOLS}}` answers with what it would create until you pass
`dry_run=false`. `{{NO_DRY_RUN_TOOLS}}` creates or updates directly and has no dry run; use `plan_backend`, `validate_plan`
and, for an existing API, `plan_drift` first.

**Open source.** MIT-licensed. Use the hosted service or run it yourself ([locally](/local), or in your own Azure
subscription with `deploy/krusgraph.sh`).

**When {{PRODUCT}} is not the right tool:** if your data isn't in Fabric yet, if you're building a transactional app
that needs its own database, or if you need row-level security defined in the API itself. Fabric's API for GraphQL has
no row-level security of its own; it applies what the source enforces for the identity that queries it (see
[App access](#app-access)), and {{PRODUCT}} does not create security policies.

## Get started

New to a Fabric lakehouse? Start by understanding how its tables fit together: connect the hosted server to Claude, then ask a first question. The [guided demo](/check?example=sample&guide=1) runs the engine on a synthetic shop in your browser, and Onto leads four steps over its map: how the tables connect, the total that doubles, a suggestion to decide on and on to Power BI or an app; it needs no account.

### Connect

1. **Your Entra admin grants consent once** for your organization:
   [grant admin consent](https://login.microsoftonline.com/organizations/adminconsent?client_id={{CLIENT_ID}}).
   It allows the connector to call Fabric and SQL as each signed-in user — nothing more.
2. **In Claude:** Settings → Connectors → Add custom connector, with the URL
   `{{MCP_URL}}`. Sign in with your Microsoft work account. {{#IF CLIENT_REGISTRATION}}VS Code, Cursor and other MCP clients
   that sign in on their own use `{{CONNECT_URL}}` instead ([below](#other-mcp-clients)).{{/IF}}{{#IF NO_CLIENT_REGISTRATION}}The hosted service supports Claude, and that is the client
   it has been tested with. Claude Code and Cursor sign in through a local redirect that is not registered on the Entra
   app yet, so they can't sign in to {{DOMAIN}} today. Other MCP clients should work when you host {{PRODUCT}} yourself (not tested yet).{{/IF}}
3. **In Fabric:** you need access to the workspace you want to use, and a Fabric capacity (a trial is fine).

Every call runs with your own Fabric permissions. The step-by-step version is on [/start](/start). The server is
published in the official [MCP Registry](https://registry.modelcontextprotocol.io/v0.1/servers?search=com.krusgraph%2Fkrusgraph) as `com.krusgraph/krusgraph` (verified 26 October 2026).
Prefer your own machine and a SQL Server? The same engine runs locally over ODBC: [/local](/local).
{{#IF CLIENT_REGISTRATION}}
### Other MCP clients

VS Code, Cursor and other MCP clients that register themselves sign in at `{{CONNECT_URL}}`, not at the address for
Claude. {{PRODUCT}} identifies the client by the metadata document it publishes (or, for a client without one, a strict
registration), shows its own approval page with the client's name, its domain and where the answer goes, and only then
sends you to Microsoft. Every call still runs with your own Fabric permissions, and nothing changes for Claude.
{{CONNECT_TESTED}}.

- **VS Code** (GitHub Copilot agent mode): in `.vscode/mcp.json` or *MCP: Open User Configuration*,
  `{"servers": {"{{PRODUCT_LOWER}}": {"type": "http", "url": "{{CONNECT_URL}}"}}}`, then *MCP: List Servers* → Start.
  Because the answer goes to a program on your computer, the approval page comes back at each new sign-in.
- **Cursor:** in `~/.cursor/mcp.json`, `{"mcpServers": {"{{PRODUCT_LOWER}}": {"url": "{{CONNECT_URL}}"}}}`, then sign in
  from Cursor's MCP settings. If the sign-in stops on the redirect address (some Cursor builds register a `cursor://`
  address, which {{PRODUCT}} does not accept: only https and local addresses), register Cursor once with its local
  address, `curl -s {{CONNECT_URL_OAUTH}}/register -H 'Content-Type: application/json' -d '{"client_name": "Cursor", "redirect_uris": ["http://localhost:8787/callback"]}'`,
  and give Cursor the `client_id` from the answer as `"auth": {"CLIENT_ID": "…"}` next to the `url`.
- **Glama:** add `{{CONNECT_URL}}` in Glama's MCP connector; it identifies itself with its metadata document.
- **Claude Code:** `claude mcp add --transport http {{PRODUCT_LOWER}} {{CONNECT_URL}}` (not tried yet).

The approval page and Microsoft's sign-in open in your own browser. A web filter on a company network can stop them
(the browser then says the site "uses an unsupported protocol"); sign in from another network, or ask IT to allow
{{DOMAIN}}.
{{/IF}}
### What you can ask

One example per tool, in the order a first session usually goes (list, plan, look at rows if needed, check, create, describe, query):

- `list_workspaces` — *"Which Fabric workspaces can I see?"*
- `list_sources` — *"List the data sources in the demo workspace."*
- `list_tables` — *"Which tables are in demo_lh, schema shop?"*
- `plan_backend` — *"Plan a backend over demo_lh, schema shop."* — nothing is deployed; you get keys, relationships, the rule for each, ambiguous columns, suggested composite keys and an ER diagram. *"Treat order_id plus line_no as the key of order_items"* passes `keys`.
- `sample_rows` — *"Show me a few rows of orders."* — when a column's meaning is unclear before deciding on keys.
- `validate_plan` — *"Check the plan against the data."* — every key counted for uniqueness and NULLs, every relationship for orphans; the [example on /check](/check?example=sample) shows what the answer looks like.
- `create_backend` — *"Create it as shop_api."* — creates the API for GraphQL item, or updates it in place if the name exists.
- `describe_backend` — *"What can I query in shop_api?"* — the types, fields and relationship names a query uses.
- `query_graphql` — *"Using shop_api, which customers ordered a trail bike in October?"* — a read-only query; relationships nest.
- `rayfin_connector` — *"Generate Rayfin connector entities for it."* — TypeScript entity classes for Fabric Apps.
- `ontology_draft` — *"Draft a Fabric IQ ontology from demo_lh."* — entity types, keys and relationship types with their rules, ready to import.
- `compare_semantic_model` — *"Compare our Sales model with the plan for demo_lh."* — what the model lacks, what a rule or the data contradicts, and the measures it could add.
- `gold_views_draft` — *"Draft gold views for demo_lh, schema shop."* — one materialized lake view per fact table over the silver tables, with data quality rules.
- `export_item_definitions` — *"Export what you would create, in Fabric's Git format."* — the item folders to commit to your own repository.
- `review_plan` — *"Keep this review as a file: accept ship_to_id as the ship-to address, leave audit_log without a key, and run the checks."* — a file to commit next to your code; next time, *"Read back krusgraph-review.demo-lh.shop.json and tell me what changed."*

**Five first questions on a lakehouse nobody has documented** (each is useful on its own):

1. *"Read demo_lh, schema shop, as a graph: which tables are facts, which are dimensions, and what are the subject areas?"* (`analyze_schema`)
2. *"Plan the keys and relationships for schema shop and tell me which rule made each one."* (`plan_backend`)
3. *"Check that plan against the data: are the keys unique and do the references hold?"* (`validate_plan`)
4. *"Which columns look like they should point at another table but are in no relationship?"* (`suggest_relationships`)
5. *"Write the data dictionary for schema shop."* (`data_dictionary`; `dbt_schema` when the team tests with dbt)

### First-time errors

What a new user meets first, what the tool answers (`kind`) and exactly what to do. Every such answer carries this
section's link in its `hint`.

| `kind` | What happened | What to do, in order |
| --- | --- | --- |
| `sign_in` | The connector has no valid sign-in for this request (expired, revoked, or never completed) | In Claude: **Settings → Connectors → {{PRODUCT}} → Disconnect**, then **Connect** again and finish the Microsoft sign-in with your work account. If it loops, your organisation requires multi-factor authentication for new apps: complete it when asked. |
| `consent` | Your Microsoft Entra organisation has not consented to the app (Entra AADSTS65001), or the tool needs a permission the app has not been granted | Send your Entra admin the consent link on [/start](/start) (it opens Microsoft's own page); after they click **Accept**, disconnect and reconnect the connector. For `create_semantic_model`, `create_ontology`, `create_data_agent`, `create_silver_notebook` and `create_drift_monitor` the answer names the missing scope (such as `Item.ReadWrite.All` or `SemanticModel.ReadWrite.All`); that is a permission the operator adds to the app, see `docs/SCOPES.md`; the dry runs work meanwhile. |
| `no_access` | You can sign in, but this workspace or item is not shared with you (HTTP 403) | Ask the workspace owner for a role on the workspace: **Viewer** is enough for everything that reads and plans, **Contributor** for `create_backend`, `create_views` and the other creating tools. Then run the same request again; `list_workspaces` shows what you can see. |
| `capacity` | The workspace has no active Fabric capacity (paused, not assigned, or expired trial) | In Fabric: **Workspace settings → License info**, assign a capacity or resume the paused one; a trial capacity is enough. Lakehouse SQL endpoints answer again a minute after the capacity is up. |
| `schema_not_found` | The schema has no tables for this sign-in | A lakehouse without "Lakehouse schemas" has everything in `dbo`; one created with schemas has them by name (`list_tables` with another schema). Tables created minutes ago are not in the SQL analytics endpoint yet: open the endpoint in Fabric and refresh its metadata, then try again. |
| `sql_sign_in` | The SQL analytics endpoint refused the token | Reconnect the connector; if it persists, the account lacks access to the item itself (share the lakehouse or warehouse, not only the workspace). |

Everything else (`not_found`, `timeout`, `throttled`, `bad_input`, …) is explained in the answer itself; the format is
the same three fields.

## Explore and check

How a plan is made, how to read it, how to check it against the rows before anything is built, and how to keep the review.

### Review, check, then create

A plan is a proposal, so read it before anything is built.

1. **Review the plan.** Each key and relationship carries the rule that made it; ambiguous columns and tables without a key are listed. Correct a key with `keys` and add a relationship the rules did not make with `confirmed`.
2. **Check it against the data.** `validate_plan` counts duplicate and NULL key values and references with no matching row. `create_backend` does not run it for you, so ask for it. A check that passes shows the data agrees with the plan today; it does not show that the plan means the right thing.
3. **Create the API.** `create_backend` creates the API for GraphQL item, or updates the one with that name. It has no dry run: run `plan_drift` first to see what an update would change. An update keeps the field names the existing API has for the same relationships. If it would still remove relationships the API has, nothing is written and the answer lists them with the `confirmed` entries that keep them (both field names included); `allow_removals=true` drops them on purpose.
4. **Query it.** `describe_backend` gives the field names; `query_graphql` runs read-only queries and refuses mutations. Two portal steps stay manual (see below).
5. **Keep the review.** `review_plan` writes the plan, your decisions with their reasons and the check results as one
   file for your own repository. Pass it back later as `previous`: the corrections apply again and what changed since
   is listed (see *Keep your review*).

### Keep your review

A review is worth keeping when the next report or app builds on the same tables. `review_plan` returns one JSON file
(`krusgraph-review.<source>.<schema>.json`) and a short Markdown report; it creates nothing in Fabric.

- **What it holds:** the format and its version, a plan id, the source (workspace, item and schema names), a
  fingerprint of the tables' columns and types, the plan snapshot (the same one the drift monitor keeps), every key and
  relationship as an item (`key:orders`, `rel:orders.customer_id>customers`) with its rule and what the rules alone
  proposed when you corrected it, open questions (ambiguous columns, tables without a key, items you left open), and the
  `keys` and `confirmed` arguments that carry your corrections into the other tools. Names, types, rules, decisions and
  counts only: no row values, samples, connection strings or tokens.
- **Two statuses per item.** *Review* is what a person decided: proposed, accepted, rejected or open, with a reason
  (`decisions`). *Check* is what the counting queries found: not checked, passed, failed or stale, with the counts and
  the time. They are kept apart: an accepted relationship can fail its check, and a passing check does not show that a
  relationship means the right thing.
- **Reading it back.** With `previous`, the decisions apply again, the schema is compared with the file's (tables,
  columns, types, keys and relationships added or removed), decisions that no longer match the plan are listed, and a
  check on a table whose columns changed becomes *stale*: an old pass is not carried forward as new evidence.
  `validate=true` runs the checks again.
- **Limits.** A relationship you reject stays rejected in the file, but the other tools still infer it from the names;
  leave it out of what you build. A large schema may not fit one answer; `tables` limits the file to an area. The file
  is unit-tested and not yet run against a live workspace (*Experimental*).

### How relationships are inferred

A lakehouse has no declared keys, so names are all there is — and every result says which rule produced it,
so you can overrule it. Declared keys and foreign keys (warehouses) always win. A column that could point at
two tables is reported, never guessed; a column no rule matches is left unlinked and you can pass it as
`confirmed`. The [example on /check](/check?example=sample) shows the rules on a synthetic schema. The rules, in the engine's own words:

{{RULES_TABLE}}

Names are matched literally first. When nothing matches, a small documented **synonym table** is tried: abbreviations
(`cust`, `prod`, `ord`, `emp`, `dept`, `acct`, …), Swedish and German business words in singular and plural (`kund`/`kunder`,
`artikel`/`artiklar`, `leverantör`, `kunde`/`kunden`, `bestellung`, `rechnung`, `mitarbeiter`, …), after transliteration of
`å ä ö ü ß`; a leading `dim_`, `fact_` or `tbl_` is not part of a table's name, and `_sk`/`_bk` count as key suffixes. Every
match that rests on the table is listed under `synonyms` in `plan_backend` and on the relationship's `note`, and counts as
the weakest rule (R4), so the plan never hides that it translated a name. Measured on eleven schemas in
`docs/INFERENCE.md`; the five public schemas that need no synonyms are unchanged to the number.

More on how they interact, with examples: https://github.com/Krusmaster/fabric-backend#how-the-relationships-are-inferred

### Sources

**Tested end to end:** a lakehouse with schemas (the demo workspace's `demo_lh`, schema `shop`), read through its SQL
analytics endpoint. **Experimental:** warehouses and Fabric SQL databases, read the same way through their SQL endpoint
and covered by unit tests; warehouses also give declared keys and foreign keys (rules K0 and R0). **Experimental:** the
mirrored and Snowflake item types below. Tables a lakehouse holds as OneLake shortcuts (to another lakehouse, a
warehouse, ADLS or S3) are listed by its SQL analytics endpoint like its own tables, so they are planned with it.

{{PRODUCT}} reads sources through Fabric, so data that lives elsewhere takes one of two routes:

1. **Bring it into Fabric.** A *Snowflake database* item, a *Mirrored database* (Snowflake, Azure SQL, Cosmos DB, SAP via
   Datasphere, …), a *Mirrored Azure Databricks catalog* or a *Mirrored catalog* (preview) is a source like a lakehouse:
   `list_sources` shows it, `plan_backend` plans it and `create_backend` builds the API over its SQL analytics endpoint.
   The item is set up once in the Fabric portal; {{PRODUCT}} reads the endpoint id from the item, as Microsoft's REST
   specification documents it for each of these item types. Experimental: unit-tested, not yet run against a live item.
2. **Plan it where it is.** The engine reads `INFORMATION_SCHEMA`, which Snowflake and Databricks (Unity Catalog)
   expose like the Fabric SQL endpoint does. The open-source library, the CLI and the local `fabric-backend-mcp` server
   give you the graph, the rules, the diagram and the Rayfin entities straight from those systems (for Databricks with
   its own adapter, [below](#databricks-draft-only)); the API for GraphQL item is a Fabric object, so that last step
   needs route 1.

Snowflake has no `KEY_COLUMN_USAGE` view, so keys there come from names (rule K2) and are shown as such. Unity Catalog's
informational primary and foreign keys are read as declared keys (K0, R0). The item types, routes and `sqlEndpointProperties`
follow Microsoft's published REST specification; these source types are experimental until a live run.

### How {{PRODUCT}} uses graph theory

The plan is a graph: tables are nodes, relationships are edges from the many side to the one side, and every edge
carries a certainty from its rule (declared or confirmed 1.0; checked against the data 0.9; R1 0.8; R2 0.6; R3 and
R4 0.5). `fabric_backend/graphs.py` is plain Python and deterministic: the same plan always gives the same answer.
What each method does for you, in plain terms:

- **Roles** (`analyze_schema`): a table that points at several others and nothing points at is a fact table; one that
  is pointed at and points at little is a dimension; a table whose key is just two references (a junction) is a bridge.
  The numbers that decided each role are in the answer, so you can disagree.
- **Centrality**: in/out degree says what a table refers to and what refers to it; betweenness says how often a
  table sits on the route between two others; PageRank on the directed graph says where the references end up
  (shared dimensions score high). The top ten is where to start reading an unknown schema.
- **Subject areas**: label propagation on the undirected graph groups tables that are more connected to each other
  than to the rest; each area is named after its most central table. A first cut at the domains in a lakehouse.
- **Ambiguity**: every relationship beyond a spanning forest closes a cycle, and any two tables on a cycle can be
  reached two ways. That is exactly what makes filter paths ambiguous in a Power BI model, so the answer lists the
  cycles and the pairs, and the maximum spanning forest (highest certainty first) says which relationships can be active
  at once; `semantic_model_draft` uses it for active/inactive.
- **Paths** (`join_path`): the shortest path counts hops; the safest path (Dijkstra on cost = 1/certainty) prefers
  declared and R1 links. When they differ the answer says why.
- **Link prediction** (`suggest_relationships`): a column with a reference suffix and the type of another table's
  key, in no relationship yet, is a candidate; a name that resembles the target, or a target the table already
  reaches in two hops, ranks it higher; then the data decides — the share of its values that exist in the target key.
  Nothing is applied; you pass the suggestion you accept as `confirmed`.

Unit-tested on the synthetic shop schema and the public benchmark schemas; `analyze_schema` and `suggest_relationships`
were run against the demo workspace (synthetic shop data) on 26 October 2026: the one column outside every relationship, `orders.ship_to_id`, came back with
every value present in `addresses.address_id` (15 distinct values) and well below that for the other candidates. On
27 October 2026, after the ranking was fixed, `addresses.address_id` came first before the data check (3.94 against
1.5 or less) and held for every value after it (inclusion 1.0). The [guided demo](/check?example=sample&guide=1) walks through this column on the
synthetic sample: the suggestion, its data check and the decision that stays yours.

### SAP on Fabric

SAP tables do not follow general naming rules: `VBAP.VBELN` is the order an item belongs to, `LIPS.VBELN` a delivery,
`VBRP.VBELN` an invoice, and every key starts with the client `MANDT`. For these tables Krusgraph uses its SAP pack:
declarative files with the keys and the order-to-cash relationships of `KNA1`, `KNVV`, `MARA`, `MAKT`, `TVKO`, `VBAK`,
`VBAP`, `VBEP`, `VBPA`, `LIKP`, `LIPS`, `VBRK`, `VBRP`, `VBFA`, and the procure-to-pay relationships of `LFA1`, `EBAN`, `EKKO`, `EKPO`, `EKET`, `EKBE`, `RBKP`, `RSEG`, and the finance relationships of `BKPF`, `BSEG`, `ACDOCA`, `SKA1`, `SKB1`, `BSID`, `BSIK`, `CSKS`, the pricing conditions `KONV`/`PRCD_ELEMENTS`, and the business partner `BUT000` with its links to customers and suppliers, each with the public source it rests
on, for ECC and S/4HANA. It does not depend on how the tables arrive: Fabric mirroring of SAP (through SAP
Datasphere), Databricks, a pipeline of your own; names are recognised with or without a prefix (`VBAK`, `vbak`,
`sap_vbak`). Every relationship it adds carries the rule `SAP pack`; `sap_pack_draft` shows what it recognises and
what is missing, and `validate_plan` checks it against the rows, because a pack is a sourced suggestion, not proof.

A synthetic example (no data from any SAP system):

```
plan_backend(workspace="demo", source="sap_lh", schema="sap")
  sap_vbap.mandt+vbeln          -> sap_vbak.mandt+vbeln          SAP pack   (item to its order)
  sap_vbep.mandt+vbeln+posnr    -> sap_vbap.mandt+vbeln+posnr    SAP pack   (schedule line to its item)
  sap_lips.mandt+vgbel+vgpos    -> sap_vbap.mandt+vbeln+posnr    SAP pack   (delivery item to the order item)
  sap_vbrk.mandt+kunrg          -> sap_kna1.mandt+kunnr          SAP pack   (payer, not the sold-to party)
  sap_vbfa                      listed, not applied: many-to-many document flow
validate_plan(...) -> amount_levels: sap_vbak.netwr is repeated on every sap_vbap row in a join of the two
```

On the synthetic SAP schema of the tests, the name rules alone find none of the 117 relationships. Given every key,
they find most of them but also 26 joins that read a document number as another kind of document (a delivery number
as an order, an invoice number as an accounting document); the pack applies none of those. The schema is generated
from the pack, so this shows what the pack adds over the name rules, not that the pack is right about SAP
([measurement](https://github.com/Krusmaster/fabric-backend/blob/main/docs/INFERENCE.md)). It has not been run against
an SAP system or a real installation. Contents, sources and how to contribute:
[docs/SAP.md](https://github.com/Krusmaster/fabric-backend/blob/main/docs/SAP.md).

## Build from a plan

What you can build once the plan is reviewed. Each tool's status is in the [tool reference](#test-status).

### One plan, five Fabric pieces

Everything {{PRODUCT}} creates comes from one plan: the keys and relationships inferred from a source, with the rule behind
each one, checked against the rows and corrected by you through `keys` and `confirmed`. From that plan:
`create_backend` makes the **API for GraphQL** with nested relationships (no dry run; `plan_drift` shows what an update
would change); `create_views` the **wide T-SQL views** on the SQL analytics endpoint; and, once the operator has enabled
the permission, `create_semantic_model` the **Power BI semantic model** in Direct Lake mode with the same relationships,
`create_ontology` the **Fabric IQ ontology** with entity types, keys, relationship types and bindings, and
`create_data_agent` the **data agent** with the plan as instructions and examples. Those four answer with a dry run
first; how far each has created live, in the words of the [tool reference](#test-status): the views ({{SHORT_CREATE_VIEWS}}),
the semantic model ({{SHORT_CREATE_SEMANTIC_MODEL}}), the ontology ({{SHORT_CREATE_ONTOLOGY}}) and the data agent
({{SHORT_CREATE_DATA_AGENT}}). Change the plan once (a confirmed relationship, a key) and every piece is rebuilt from it; `plan_drift` and
`lineage` tell you what a change reaches. The pieces agree with each other because none of them was modelled by hand.

From the same plan, further down the lakehouse: `silver_notebook_draft` writes de-duplicated silver tables with every
reference checked, and `gold_views_draft` the **gold views** on top of them, as materialized lake views (generally
available in Fabric since September 2026) whose data quality rules are the plan's keys and relationships. A model you
already have is checked against the plan with `compare_semantic_model`. And when changes go through Git rather than
straight into the workspace, `export_item_definitions` gives every piece as the files Fabric's Git integration reads.

### Fabric IQ: the same graph as an ontology

Fabric IQ's **ontology (preview)** item describes a business as entity types with properties and a key, relationship
types between them, and data bindings to tables. That is the information {{PRODUCT}} already infers for a source, with
the rule behind every key and relationship. `ontology_draft` writes the plan in the ontology item's own shape, nothing deployed:

- a **summary** with what needs a hand (keyless tables, composite keys, composite-column relationships);
- a **binding checklist**: entity type → table, key column, property → column, relationship → columns, each with its rule;
- a **Turtle file** the portal's *Import ontology* accepts into an empty ontology item, using the mappings Microsoft documents
  for import (`owl:Class` → entity type, `owl:DatatypeProperty` → property, `owl:ObjectProperty` → relationship type,
  `rdfs:label`, `rdfs:comment`, `skos:altLabel` → display name, description, synonym); bindings are then done in the portal
  following the checklist;
- the **item definition** (generation 2, TMDL parts) that `POST /workspaces/{id}/ontologies` and Git integration take,
  with tables bound DirectLake-style to the source, entities with keys and properties, and the relationships.

Creating the item through the API needs the delegated scope `Item.ReadWrite.All` and Contributor on the workspace,
and the workspace on a Fabric capacity (`POST /workspaces/{id}/ontologies`, `updateDefinition`; Microsoft's REST
specification, read 26 October 2026). `create_ontology` does that with a dry run by default (creating the item: {{SHORT_CREATE_ONTOLOGY}});
without the permission it answers `consent` naming the scope when asked to create. The portal route (Import ontology
with the Turtle file) needs nothing beyond what you already have. Once an ontology exists, Fabric IQ's own pieces take
over: the ontology agent and data agents use it as context, and the built-in graph can be materialised from its entity
and relationship types. Ontology is in preview and its definition format can change; the draft follows the item's own
definition as of 2026, checked against recorded definitions and, through `create_ontology`, against Fabric itself
({{SHORT_CREATE_ONTOLOGY}}).

### Two steps stay manual

Fabric has no API for these yet, and the connector tells you when they are needed:

1. **Introspection** on the GraphQL item (item → Settings → Introspection) — needed by tools such as Lovable that read the schema.
2. **Permissions** on the item for other apps or service principals that should query it.

### App access

An app built on the API for GraphQL does not use your {{PRODUCT}} sign-in. It calls the API with its own identity,
usually a Microsoft Entra service principal (the route `app_starter` drafts), and what it can read depends on two
settings in Fabric:

- **Who may call the API.** The app's identity needs *Run Queries and Mutations* on the item (the second manual step
  above), and for a service principal the tenant setting that lets service principals use Fabric APIs.
- **Which identity reads the data.** The API connects to its source either with **single sign-on**, where each caller's
  own identity reads the source and that caller's permissions (row-level security defined on the source included)
  apply, or with **saved credentials**, where one stored identity reads the source for every caller. With saved
  credentials a caller needs only access to the API, so **the app's users can see data they have no permission to read
  themselves.** {{PRODUCT}} does not set this; check it in the item's settings in the Fabric portal before you publish an app.

The API for GraphQL has no row-level security of its own. Restrict rows at the source and use single sign-on, or
expose only views that hold the rows the app may show. `app_readiness` lists what it can read about an API and marks the
permissions as "unknown" with the portal path, because the Fabric API does not return them.

### Use with Lovable

Lovable's Microsoft Fabric connector reads an existing API for GraphQL item. {{PRODUCT}} creates that item; after the
two manual steps above, Lovable connects to it. Step by step: [Use {{PRODUCT}} with Lovable](/lovable). `app_readiness`
says what is still missing on the API; `app_starter` gives the prompt, the queries and a Supabase edge function that
keeps the app's Entra secret on the server side. The whole chain, with who does each step and what still blocks, is in
the repository's `docs/LOVABLE-END-TO-END.md`.

### Databricks (Draft only)

The same engine reads Databricks too, in the local server only (`KRUSGRAPH_PLATFORM=databricks`): a Unity Catalog
schema through its `information_schema`, where declared primary and foreign keys count as K0 and R0 and column tags feed
the personal-data rules; the checks run as counting queries on a SQL warehouse. From the same plan it drafts
informational constraints (with `RELY` only where the counts hold), views, a Lakeflow pipeline whose expectations are
the plan's keys and relationships, metric views and a bundle. **Draft only:** unit-tested with Databricks mocked, not
yet run against a Databricks workspace. The hosted service at {{DOMAIN}} reads Fabric only. Set-up, the status of each tool
and the documentation each draft rests on: [docs/DATABRICKS.md](https://github.com/Krusmaster/fabric-backend/blob/main/docs/DATABRICKS.md).
Databricks' own managed MCP servers (Genie, Databricks SQL, Unity Catalog functions) answer questions and run SQL;
{{PRODUCT}} is the part that works out how the tables relate. {{PRODUCT}} is not affiliated with Databricks.

## Tool reference

The status words, then each tool: what it reads, returns or changes.

### Test status

Each tool in the table below carries one of these. They come from one list of fields per tool (where it is available,
what it changes, how it is tested and whether it ran live; `fabric_backend/tool_status.py`), so a tool has the same
status on every page. *Draft only* says what a tool changes, *Tested end to end* how far it has been run: a draft tool
that ran live is listed as tested, and its *What it changes* column says it creates nothing.

- **Tested end to end** — run from Claude as a custom connector, through Microsoft sign-in, against a Fabric workspace
  with synthetic data (an F2 capacity, the lakehouse `demo_lh` with the shop schema from `fabric_backend/seed.py`) on
  {{LIVE_RUN_DATE}}, through the hosted server's build {{LIVE_RUN_BUILD}}, read-only, as drafts or as dry runs, and
  then, with the maintainer's approval, one creating call that updated an existing API in place: {{LIVE_RUN_LIST}}. A draft that ran so is marked *(a draft; creates nothing)*, a creating tool
  whose dry run ran *tested end to end as a dry run*; creating keeps its own status. Not run that day, not even as a
  dry run: {{NOT_RUN_LIST}}. The first such run was on {{FIRST_RUN_DATE}} ({{FIRST_RUN_STEPS}} steps). Changes made
  after the run are covered by unit tests.
- **Experimental** — on the hosted server and unit-tested, not yet run against a live workspace.
- **Draft only** — returns a draft or files and creates nothing in Fabric.
- **Available when enabled by the operator** — needs a permission the hosted app does not ask for today. The dry run
  works; asked to create, the tool answers `consent` with the permission's name
  ([docs/SCOPES.md](https://github.com/Krusmaster/fabric-backend/blob/main/docs/SCOPES.md)).
- **Planned** — not available yet, such as the Claude plugin (see *For agents*).

### Overview: tools, functions and clients

Each tool, each function outside the hosted tools, and each client, with its status and where it runs: *hosted*
(krusgraph.com), *local* (the stdio server `fabric-backend-mcp` on your machine), *local demo* (`fabric-backend demo`)
or *library* (the Python package in your own scripts or notebooks). Generated from the same source as the tool table
below and the server's instructions.

{{OVERVIEW_TABLE}}

### Tools

All tools take the workspace by id or display name. `schema` defaults to `dbo`; `keys` overrides a table's key
(`{"order_items": ["order_id", "line_no"]}`), `confirmed` adds relationships the rules did not make
(`[{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}]`),
`tables` limits what is built. A `confirmed` entry can also name the relationship's two GraphQL fields: `field_name`
on the source (`"address"`: `orders.address`) and `reverse_name` on the target (`"orders"`: `addresses.orders`); without
them the rules name the fields (`ship_to` and `orders_as_ship_to` here). When an API of that name exists, `create_backend`
and `plan_drift` keep the field names it already has for the same relationship (the same columns in the same direction)
unless `confirmed` names them otherwise, and their `keep_with_confirmed` entries carry both names.

| Tool | Status | What it changes | Does | Arguments |
| --- | --- | --- | --- | --- |
| `list_workspaces` | {{status}} | {{changes}} | the workspaces the signed-in account can see, with id, name and capacity | — |
| `list_sources` | {{status}} | {{changes}} | lakehouses, warehouses, SQL databases, Snowflake databases, mirrored databases and catalogs in the workspace, plus existing API for GraphQL items | `workspace` |
| `list_tables` | {{status}} | {{changes}} | tables and columns with types in one schema; `tables` narrows to names or patterns (`["sales_*"]`), `detail` is `auto` (full up to 60 tables, then the column count per table), `full` or `summary` | `workspace`, `source`, `schema`, `tables`, `detail` |
| `plan_backend` | {{status}} | {{changes}} | inferred keys and relationships, each with its rule, ambiguous columns, keyless tables, suggested composite keys, the names read through the synonym table (`synonyms`), a Mermaid ER diagram; `tables` narrows the answer to names or patterns while the plan is still made from the whole schema, `detail` is `auto` (full up to 60 tables, then one line per key and relationship without field names or diagram), `full` or `summary`, `mermaid=false` leaves the diagram out; every answer stays under 60 000 characters and says when it was cut | `workspace`, `source`, `schema`, `keys`, `confirmed`, `tables`, `detail` |
| `validate_plan` | {{status}} | {{changes}} | checks the plan against the rows: is each key unique and free of NULLs, does every reference find its target (orphan count); one small counting query per key and relationship; returns counts and a verdict, no row values | `workspace`, `source`, `schema`, `keys`, `confirmed`, `max_items` |
| `sample_rows` | {{status}} | {{changes}} | the first n rows (at most 20) of one table, long text shortened, to check what a column means; columns that look like personal data come back as `***` with the rule, and the source's sensitivity label is named | `workspace`, `source`, `table`, `schema`, `n`, `show_personal_data` |
| `create_backend` | {{status}} | {{changes}} | creates the API for GraphQL item with nested relationships, or updates the item of that name in place, keeping the field names it has for the same relationships; refuses an update that would drop relationships the API has unless `allow_removals=true`, and names the `confirmed` entries (with `field_name` and `reverse_name`) that keep them; returns the endpoint and the two portal steps; no dry run, and it does not run `validate_plan` | `workspace`, `source`, `name`, `schema`, `writable`, `keys`, `confirmed`, `tables`, `allow_removals` |
| `describe_backend` | {{status}} | {{changes}} | types, fields and relationships of an existing API for GraphQL item, in the names a query uses, read from its definition (no introspection needed) | `workspace`, `api` |
| `query_graphql` | {{status}} | {{changes}} | runs a read-only GraphQL query against an API (name or id); mutations are refused; with `question`, `tables` and `source` instead of `query` it builds the query `answer_query_draft` suggests, runs it, and shows it beside the result | `workspace`, `api`, `query`, `variables`, `question`, `tables`, `source`, `schema` |
| `rayfin_connector` | {{status}} | {{changes}} | Rayfin (Fabric Apps) connector entity classes and `schema.ts` | `workspace`, `source`, `connector`, `schema`, `keys`, `confirmed`, `tables`, `relationships` |
| `ontology_draft` | {{status}} | {{changes}} | the plan as a Fabric IQ ontology (preview) draft: summary, binding checklist, a Turtle file for the portal import, the item definition | `workspace`, `source`, `name`, `schema`, `keys`, `confirmed`, `tables` |
| `semantic_model_draft` | {{status}} | {{changes}} | a Power BI semantic model in TMDL (`definition/` files) with suggested measures (the row count of each fact table, sums only where `summarizeBy` sums, each with its reason) and a calendar marked as the date table when fact tables have date columns: one Direct Lake table per source table on the SQL analytics endpoint, relationships with cardinality and one active path per table pair, keyless tables unrelated, `README.generated.md` with every decision to check; unit-tested against Microsoft's sample definitions | `workspace`, `source`, `name`, `schema`, `keys`, `confirmed`, `tables` |
| `join_path` | {{status}} | {{changes}} | the shortest chain of relationships between two tables with the rule per hop and a ready T-SQL `SELECT … JOIN …`; equally short paths all listed; with no path, which relationship is missing as a `confirmed` entry | `workspace`, `source`, `start`, `end`, `schema`, `keys`, `confirmed` |
| `data_dictionary` | {{status}} | {{changes}} | hand-over documentation in Markdown: tables, columns and types, keys and relationships with rules, keyless and ambiguous items, the ER diagram, an empty Description column; `validate=true` adds the counts from `validate_plan`; `tables` (names or patterns) documents one part of a large schema at a time, with the roles and subject areas of the whole schema, and an answer over 60 000 characters is cut on a line and says so | `workspace`, `source`, `schema`, `keys`, `confirmed`, `validate`, `max_items`, `tables` |
| `dbt_schema` | {{status}} | {{changes}} | a dbt `schema.yml` with sources: `unique` and `not_null` on key columns, `relationships` on single-column relationships, in the syntax of the dbt documentation; composite keys noted as comments; `tables` takes names or patterns, an answer over 60 000 characters is cut and says so | `workspace`, `source`, `schema`, `source_name`, `keys`, `confirmed`, `tables`, `arguments_block` |
| `domain_draft` | {{status}} | {{changes}} | proposed domains (candidate data products) from the plan's graph: deterministic Leiden-style communities weighted by each relationship's rule, a name and a reason per table, the relationships that cross domains (interfaces), unassigned tables, and one ODCS v3.2.0 contract per domain; the customer's Fabric admin creates the domains | `workspace`, `source`, `schema`, `confirmed`, `check_rows` (inferred keys) |
| `sap_pack_draft` | {{status}} | {{changes}} | which tables the SAP pack recognises (with or without a prefix such as `sap_`), their keys with `MANDT`, the order-to-cash relationships it applies with the public source of each, what it lists but does not apply (`VBFA` is many-to-many), what is missing, and the traps; optionally one export: Krusgraph keys/confirmed, Data API builder config, an extraction list with open-mirroring `keyColumns`, or dbt sources. See [SAP on Fabric](#sap-on-fabric) | `workspace`, `source`, `schema`, `keys`, `confirmed`, `variant`, `export` |
| `plan_drift` | {{status}} | {{changes}} | today's plan against an existing API for GraphQL item: new tables and columns, columns the API still maps that are gone, relationships the plan no longer supports, and whether `create_backend` with that name would change anything | `workspace`, `source`, `api`, `schema`, `keys`, `confirmed`, `tables`, `writable` |
| `create_semantic_model` | {{status}} | {{changes}} | creates a Power BI semantic model item from the TMDL draft (Direct Lake on the SQL analytics endpoint) or updates the one of that name in place; `dry_run=true` (default) returns the parts and the REST call only; needs `SemanticModel.ReadWrite.All` or `Item.ReadWrite.All` | `workspace`, `source`, `name`, `schema`, `keys`, `confirmed`, `tables`, `dry_run` |
| `create_report` | {{status}} | {{changes}} | creates an empty Power BI report item (one blank page, no visuals) bound to an existing semantic model through Fabric's `creationPayload`; no report definition is sent; a report of that name is left alone and the call answers `kind: already_exists`; `dry_run=true` (default) returns the REST call only; needs `Report.ReadWrite.All` or `Item.ReadWrite.All` and read permission on the model | `workspace`, `model`, `name`, `dry_run` |
| `create_views` | {{status}} | {{changes}} | `CREATE OR ALTER VIEW` in a schema of its own (default `krusgraph`, created if missing) on the source's SQL analytics endpoint or warehouse: one wide view per fact table with its dimensions, one per header table (`vw_orders`: each order with its customer and, once `orders.ship_to_id` is confirmed, its ship-to address), one per hard-to-read relationship; `dry_run=true` returns the SQL; needs the SQL right to create objects (Contributor) | `workspace`, `source`, `schema`, `views_schema`, `keys`, `confirmed`, `dry_run` |
| `create_data_agent` | {{status}} | {{changes}} | creates or updates a Fabric data agent through the staging REST API: the plan as instructions, the source as data source with the plan's tables selected, 5–10 question/T-SQL examples, then publishes; columns that look like personal data are left out of the instructions and the examples unless `show_personal_data=true` (the key stands in); `dry_run=true` returns instructions, examples and the calls; needs `Item.ReadWrite.All` | `workspace`, `source`, `name`, `schema`, `keys`, `confirmed`, `publish`, `show_personal_data`, `dry_run` |
| `create_ontology` | {{status}} | {{changes}} | creates a Fabric IQ ontology (preview) item from the plan or updates the one of that name in place: entity types with keys and properties, relationship types and Direct Lake-style bindings in the item's generation-2 definition; `dry_run=true` (default) returns the parts and the REST call only; needs `Item.ReadWrite.All` and Contributor on the workspace (`POST /workspaces/{id}/ontologies`, `updateDefinition`; fabric-rest-api-specs read 26 October 2026) | `workspace`, `source`, `name`, `schema`, `keys`, `confirmed`, `tables`, `dry_run` |
| `app_starter` | {{status}} | {{changes}} | from an existing API's definition: a Lovable prompt with the data model and main views, a connection description, five GraphQL queries walking the relationships, the portal checklist, and the backend an app needs so that no secret reaches the browser: a Supabase edge function (service principal, client credentials, secrets as Supabase secrets), the frontend helper, and the per-user alternative | `workspace`, `api` |
| `app_readiness` | {{status}} | {{changes}} | what an app still needs on an existing API: types without a key, types in no relationship, write access (from the definition), whether introspection is on (one introspection query to the endpoint), and "unknown" with the portal path for what the Fabric API cannot read (permissions, the tenant setting for service principals); a next step per item | `workspace`, `api` |
| `analyze_schema` | {{status}} | {{changes}} | the plan as a graph, metadata only (`tables` and `detail` as in `plan_backend`; the summary groups tables by role and keeps the central tables, the areas by size and counts): table roles (fact, dimension, bridge, isolated) with the numbers behind them, the ten most central tables (degree, betweenness, PageRank), subject areas, cycles and table pairs with more than one path, and which relationships can be active at once | `workspace`, `source`, `schema`, `keys`, `confirmed`, `tables`, `detail` |
| `lineage` | {{status}} | {{changes}} | which objects in the workspace build on the source's tables: GraphQL APIs (from their definition), semantic models (from their TMDL definition), views on the SQL analytics endpoint (`INFORMATION_SCHEMA.VIEW_TABLE_USAGE`), data agents (named in their definition, marked as not certain); a graph of tables and objects, the objects per table, the tables used by nothing, the items that could not be read; with `table`, what a change to it reaches | `workspace`, `source`, `schema`, `table` |
| `silver_notebook_draft` | {{status}} | {{changes}} | a Fabric notebook (PySpark) that builds silver tables from a lakehouse's tables: de-duplicated on each table's key (the latest row by `order_by` wins), every relationship checked with the rows whose reference is missing put in `krusgraph_quarantine` with the reason, Delta tables written only in `silver_schema`, each step commented with its rule; re-runnable. The steps and the notebook source | `workspace`, `source`, `schema`, `silver_schema`, `order_by`, `keys`, `confirmed`, `tables` |
| `create_silver_notebook` | {{status}} | {{changes}} | creates that notebook in the workspace, attached to the lakehouse, or updates the one of that name; creating runs nothing; `dry_run=true` (default) returns the notebook and the call; needs `Notebook.ReadWrite.All` or `Item.ReadWrite.All` (fabric-rest-api-specs `notebook/swagger.json`) | `workspace`, `source`, `name`, `schema`, `silver_schema`, `order_by`, `keys`, `confirmed`, `tables`, `dry_run` |
| `drift_monitor_draft` | {{status}} | {{changes}} | a notebook and a pipeline that every night read the lakehouse's schema, compare the plan with the last saved one (the `plan_drift` and `lineage` logic as a library), save the new plan in `krusgraph.plans`, and send a short summary to a webhook (Teams or Power Automate) set as a pipeline parameter in Fabric; plus the daily schedule; the notebook installs the library at the tag of the server's version unless `library_ref` names another tag, a commit or `main` | `workspace`, `source`, `schema`, `name`, `at`, `time_zone`, `library_ref` |
| `create_drift_monitor` | {{status}} | {{changes}} | creates or updates that notebook and pipeline and adds the daily schedule unless one at that time exists; no secret anywhere; `dry_run=true` (default) returns the items and the calls; needs `Notebook.ReadWrite.All` and `DataPipeline.ReadWrite.All` (or `Item.ReadWrite.All`), and `DataPipeline.Execute.All` (or `Item.Execute.All`) for the schedule | `workspace`, `source`, `name`, `schema`, `at`, `time_zone`, `library_ref`, `schedule`, `dry_run` |
| `answer_query_draft` | {{status}} | {{changes}} | a question in Swedish or English about the given tables as T-SQL over the safest join path (each step with its rule), and with `api` as GraphQL in that API's field names, or why GraphQL cannot answer it; reads counts, sums, averages, "per"/"för varje" groupings, top N and "latest", and lists what it assumed; runs nothing; columns that look like personal data are left out unless `show_personal_data=true` (the key stands in) | `workspace`, `source`, `question`, `tables`, `schema`, `api`, `keys`, `confirmed`, `show_personal_data` |
| `suggest_relationships` | {{status}} | {{changes}} | columns that could point at another table's key but are in no relationship, ranked by name, type and triangular closure, the best `check` counted against the data (inclusion share, distinct values); each with a ready `confirmed` entry; suggests only, never applies | `workspace`, `source`, `schema`, `keys`, `confirmed`, `check` |
| `compare_semantic_model` | {{status}} | {{changes}} | an existing semantic model (name or id) against the plan: relationships the model lacks, ones a rule or the data contradicts (with the rule or the count), other cardinality, filters in both directions, active against inactive, links the plan lacks (with a `confirmed` entry), columns summed that the `summarizeBy` rule would not sum, suggested measures it lacks; reads the model's TMDL through Fabric's getDefinition (needs `SemanticModel.ReadWrite.All` or `Item.ReadWrite.All`), or `tmdl` from a PBIP folder or Git, which needs nothing; `check_data=true` counts against the rows | `workspace`, `source`, `model`, `schema`, `keys`, `confirmed`, `check_data`, `max_items`, `tmdl` |
| `gold_views_draft` | {{status}} | {{changes}} | materialized lake views in Spark SQL for a lakehouse with schemas: one wide view per fact table in `gold_schema` over the silver tables, joined over the safest many-to-one paths, with `CONSTRAINT … CHECK … ON MISMATCH DROP` rules for the plan's keys and relationships, each commented with its rule; personal-data columns left out unless `show_personal_data=true`; the notebook that creates them | `workspace`, `source`, `schema`, `silver_schema`, `gold_schema`, `keys`, `confirmed`, `tables`, `show_personal_data` |
| `create_gold_views` | {{status}} | {{changes}} | creates that notebook in the workspace, attached to the lakehouse, or updates the one of that name; the views are created when the notebook runs, and it stops before a source table, a silver table or any table it did not create; `dry_run=true` (default) returns the views, the notebook and the call; needs `Notebook.ReadWrite.All` or `Item.ReadWrite.All` | `workspace`, `source`, `name`, `schema`, `silver_schema`, `gold_schema`, `keys`, `confirmed`, `tables`, `show_personal_data`, `dry_run` |
| `export_item_definitions` | {{status}} | {{changes}} | what `create_backend`, `create_semantic_model`, `create_silver_notebook`, `create_drift_monitor` and `create_gold_views` would create, as folders in Fabric's Git format (`<name>.<type>` with `.platform` and the definition files), plus `create_views`' T-SQL as a script (Fabric's Git integration does not carry SQL analytics endpoint views) and a README; for your own repository, so that Fabric's Git integration or a deployment pipeline makes the change; calls no Git provider | `workspace`, `source`, `schema`, `items`, `names`, `keys`, `confirmed`, `tables`, `silver_schema`, `gold_schema`, `views_schema`, `writable`, `show_personal_data` |
| `review_plan` | {{status}} | {{changes}} | the plan with the decisions made about it and its checks as one JSON file for your own repository, plus a short Markdown report and what needs attention: each key and relationship with a review status (proposed, accepted, rejected, open, with a reason) and, apart from it, a check status (not checked, passed, failed, stale); `validate=true` records `validate_plan`'s counts with the time; `previous` takes an earlier file, applies its corrections again, lists what changed in the schema and marks checks on changed tables stale; names, types, rules, decisions and counts only, never row values or credentials | `workspace`, `source`, `schema`, `keys`, `confirmed`, `decisions`, `previous`, `validate`, `tables`, `max_items` |

When a call cannot be completed, the tool answers with three fields instead of a bare failure: `error` (what
happened, in plain words), `kind` (a stable code such as `not_found`, `no_access`, `capacity`, `sign_in`,
`consent`, `schema_not_found`, `table_not_found`, `bad_input`, `timeout`, or `rate_limited` with `retry_after` in seconds when
an account or organisation makes too many calls in a short time) and `hint` (what to do next). Tokens, request
headers and stack traces never appear in these answers. A query result too large for one answer comes back as valid
JSON with every list cut to its first items and a `truncated` note saying so; page with `first:`/`after` for the rest.

### For agents

A Markdown version of these docs is at [/docs.md](/docs.md); [/llms.txt](/llms.txt) lists the rest and
[/llms-full.txt](/llms-full.txt) has every page in one file. MCP clients can read the server's identity and transport
from its Server Card at `{{MCP_URL}}/server-card`, and the OAuth metadata at `/.well-known/oauth-protected-resource`.
Claude Code takes the same URL (`claude mcp add --transport http {{PRODUCT_LOWER}} {{MCP_URL}}`), but its local sign-in
redirect is not registered on the Entra app yet, so it can't sign in to {{DOMAIN}} today; Claude is the supported client.
A Claude plugin that bundles this connector with a skill for the whole workflow and the commands `/krusgraph:plan`,
`/krusgraph:document` and `/krusgraph:explain-schema` is built and tested in the repository (`plugin/krusgraph`) and
coming soon (Planned); it is not published yet.

### With Microsoft's Fabric MCP servers

Microsoft publishes its own MCP servers for Fabric and Power BI. They manage workspaces and items, read files and run
queries; {{PRODUCT}} works out how your tables relate, with the rule behind every link, checks it against the rows, and
builds from that plan. Both can be added to the same client, each doing its own part:

- **Workspaces, items and OneLake files:** the local [Fabric MCP Server](https://github.com/microsoft/mcp/blob/main/servers/Fabric.Mcp.Server/README.md)
  ([Learn](https://learn.microsoft.com/fabric/onelake/onelake-local-mcp)) and the remote Fabric Core MCP server
  ([tools reference](https://learn.microsoft.com/rest/api/fabric/articles/mcp-servers/core-remote/tools-core-mcp-server)).
- **Questions to a Power BI semantic model or report:** [Fabric IQ MCP](https://learn.microsoft.com/fabric/iq/connectors/fabric-iq-mcp),
  read-only, with DAX queries under your own permissions.
- **Editing a semantic model:** the [Power BI Modeling MCP server](https://github.com/microsoft/powerbi-modeling-mcp).
- **T-SQL on a warehouse:** the [Fabric Data Warehouse MCP server](https://learn.microsoft.com/fabric/data-warehouse/data-warehouse-mcp-server) (preview).
- **Eventhouse and real-time data:** [Real-Time Intelligence MCP](https://learn.microsoft.com/fabric/real-time-intelligence/mcp-overview).
- **{{PRODUCT}}:** the plan (keys and relationships with their rules, checked against the rows) and what is built from it:
  the GraphQL API, the semantic model, views, silver and gold layers, drift monitoring, the item files for Git, and a
  check of an existing model against the plan.

A typical pairing: Microsoft's server finds the workspace and the lakehouse; {{PRODUCT}} plans it and drafts the model;
Fabric IQ MCP then answers questions on the model once it exists. {{PRODUCT}} is an independent open-source project of
Kruse Consulting AB and is not affiliated with Microsoft.

## Hosting and permissions

What the hosted server reads and asks for, and what to know when you run it yourself.

### What it accesses

The Entra app asks for delegated permissions only, all acting as the signed-in user: `User.Read` (sign-in),
`Workspace.Read.All` and `Item.Read.All` (listing sources, reading metadata), `GraphQLApi.ReadWrite.All` (creating or
updating the one item you ask for; it never deletes), `GraphQLApi.Execute.All` (your read-only queries) and Azure SQL
`user_impersonation` (table and column names from the SQL analytics endpoint, and the checks and samples you ask for).
The tools that create semantic models, ontologies, data agents, notebooks and pipelines need more (`Item.ReadWrite.All`
or a narrower permission per item type), which the hosted app does not ask for today; they are marked *Available when
enabled by the operator* below.

**The data path.** Planning uses schema metadata: workspace, item, table and column names and types. `validate_plan`
and `suggest_relationships` check keys and references against the rows in Fabric with counting queries and return only
the counts. `sample_rows` returns up to 20 example rows of one table, and `query_graphql` returns the results you ask
for. `describe_backend`, `plan_drift`, `app_starter` and `lineage` read the definitions of items in the workspace.
Metadata, requested samples and query results pass through {{PRODUCT}} on their way to your MCP client and are not kept
after the request. From Claude, your tokens are exchanged on your behalf and held in memory only, never written to disk
or logs.{{#IF CLIENT_REGISTRATION}} From an MCP client other than Claude (signing in through {{DOMAIN}}/oauth), the Microsoft
tokens of a sign-in are kept encrypted in {{REGISTRATION_WHERE}} until your client collects them (at most 60 seconds), and
Microsoft's refresh token stays there encrypted for as long as your client keeps renewing its access, at most 90 days,
and is never given to the client ([sign-in from MCP clients other than Claude](/privacy#sign-in-from-mcp-clients-other-than-claude));
apart from those sign-in records there is no database and no file storage.{{/IF}}{{#IF NO_CLIENT_REGISTRATION}} There is no
database and no file storage.{{/IF}} Each tool call leaves an anonymous usage record (the tool, how the call ended, how long it took), and the
service writes technical logs. Details: [privacy policy](/privacy).

**Personal data and sensitivity labels.** Columns whose name looks like personal data are flagged by one rule per
pattern, from the name alone and never from the values: a person's name (P1: `first_name`, `last_name`, and `name` in a
table that holds people such as customers or employees), e-mail (P2), telephone (P3), national identity number (P4,
such as `personnummer`), address (P5: street, postal code, and the city in a table of addresses or people) and birth
date (P6). By default `sample_rows` returns their values as `***` with a notice naming the rule, `answer_query_draft`
and `gold_views_draft` leave them out (the key stands in), and the silver notebook masks them in its quarantine table;
`show_personal_data=true` shows them, and your own Fabric permissions still decide what you can read. When Fabric
returns a Microsoft Purview sensitivity label on the source item, `sample_rows` and `validate_plan` name it: Fabric
gives the label's id only, and a label covers the whole item, so the column rules still decide what is masked.

### Cold start, and `min_replicas` if you run it yourself

If the hosted service has been idle, the first request may take longer while Azure starts the container. If that
request times out, try again after a short pause. If the problem continues, check the error message or
[get help](/support).

If you run the server yourself with `deploy/krusgraph.sh`, `min_replicas` in `deploy/krusgraph.json` decides whether it
scales to zero: `0` (the default) scales to zero when idle and is the cheapest, `1` keeps one instance running so idle
time does not cause a cold start, at the cost of one always-on instance. A new revision or a restart can still delay a
request. The change takes effect with `--update`. A container on a VM or in Docker does not scale to zero.

### Support

[Get help](/support): email Gustav at {{CONTACT}} with the `error`, `kind` and `hint` from the tool's answer (there is no
promised response time), or report a bug or a plan that came out wrong on
[GitHub Issues](https://github.com/Krusmaster/fabric-backend/issues). Source (MIT): https://github.com/Krusmaster/fabric-backend
