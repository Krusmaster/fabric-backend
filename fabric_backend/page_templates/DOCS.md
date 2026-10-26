# {{PRODUCT}} docs

Using {{PRODUCT}} with Microsoft Fabric: turn the tables in a lakehouse, warehouse or SQL database into an explainable graph and a GraphQL API —
keys and relationships inferred, with the rule behind every link shown. Use it from Claude today, and from other
MCP clients once their sign-in redirects are registered (see *Connect*). Try the [demo](/explore) first if you
like; it needs no account. The connector was run end to end against a live Fabric workspace with synthetic data on
25 October 2026: every tool, from sign-in in Claude through Entra to Fabric.

## Connect

1. **Your Entra admin grants consent once** for your organization:
   [grant admin consent](https://login.microsoftonline.com/organizations/adminconsent?client_id={{CLIENT_ID}}).
   It allows the connector to call Fabric and SQL as each signed-in user — nothing more.
2. **In Claude:** Settings → Connectors → Add custom connector, with the URL
   `{{MCP_URL}}`. Sign in with your Microsoft work account. Claude Code and Cursor take the same URL, but their
   sign-in uses a local redirect that is not registered on the Entra app yet; until it is, Claude is the tested client.
3. **In Fabric:** you need access to the workspace you want to use, and a Fabric capacity (a trial is fine).

Every call runs with your own Fabric permissions. The step-by-step version is on [/start](/start). The server is
listed in the official [MCP Registry](https://registry.modelcontextprotocol.io/v0.1/servers?search=com.krusgraph%2Fkrusgraph) as `com.krusgraph/krusgraph` (verified 26 October 2026).
Prefer your own machine and a SQL Server? The same engine runs locally over ODBC: [/local](/local).

## What it accesses

The Entra app asks for delegated permissions only, all acting as the signed-in user: `User.Read` (sign-in),
`Workspace.Read.All` and `Item.Read.All` (listing sources, reading metadata), `GraphQLApi.ReadWrite.All` (creating or
updating the one item you ask for; it never deletes), `GraphQLApi.Execute.All` (your read-only queries) and Azure SQL
`user_impersonation` (table and column names from the SQL analytics endpoint).

**The data path.** Metadata (workspace, item, table and column names) and the query results you ask for pass through
the server on their way to your MCP client. Your tokens are exchanged on your behalf and held in memory only. The
server has no database, keeps no files and stores nothing between requests. Details: [privacy policy](/privacy).

## What you can ask

One example per tool, in the order a first session usually goes (list, plan, look at rows if needed, check, create, describe, query):

- `list_workspaces` — *"Which Fabric workspaces can I see?"*
- `list_sources` — *"List the data sources in the demo workspace."*
- `list_tables` — *"Which tables are in demo_lh, schema shop?"*
- `plan_backend` — *"Plan a backend over demo_lh, schema shop."* — nothing is deployed; you get keys, relationships, the rule for each, ambiguous columns, suggested composite keys and an ER diagram. *"Treat order_id plus line_no as the key of order_items"* passes `keys`.
- `sample_rows` — *"Show me a few rows of orders."* — when a column's meaning is unclear before deciding on keys.
- `validate_plan` — *"Check the plan against the data."* — every key counted for uniqueness and NULLs, every relationship for orphans; the [demo](/explore#plan-check) shows what the answer looks like.
- `create_backend` — *"Create it as shop_api."* — creates the API for GraphQL item, or updates it in place if the name exists.
- `describe_backend` — *"What can I query in shop_api?"* — the types, fields and relationship names a query uses.
- `query_graphql` — *"Using shop_api, which customers ordered a trail bike in October?"* — a read-only query; relationships nest.
- `rayfin_connector` — *"Generate Rayfin connector entities for it."* — TypeScript entity classes for Fabric Apps.
- `ontology_draft` — *"Draft a Fabric IQ ontology from demo_lh."* — entity types, keys and relationship types with their rules, ready to import or create.

## Tools

Every tool takes the workspace by id or display name. `schema` defaults to `dbo`; `keys` overrides a table's key
(`{"order_items": ["order_id", "line_no"]}`), `confirmed` adds relationships the rules did not make
(`[{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}]`),
`tables` limits what is built.

| Tool | Arguments | Does | Changes anything |
| --- | --- | --- | --- |
| `list_workspaces` | — | the workspaces the signed-in account can see, with id, name and capacity | no |
| `list_sources` | `workspace` | lakehouses, warehouses, SQL databases, Snowflake databases, mirrored databases and catalogs in the workspace, plus existing API for GraphQL items | no |
| `list_tables` | `workspace`, `source`, `schema`, `tables`, `detail` | tables and columns with types in one schema; `tables` narrows to names or patterns (`["sales_*"]`), `detail` is `auto` (full up to 60 tables, then the column count per table), `full` or `summary` | no |
| `plan_backend` | `workspace`, `source`, `schema`, `keys`, `confirmed`, `tables`, `detail` | inferred keys and relationships, each with its rule (K0–K5, R0–R4), ambiguous columns, keyless tables, suggested composite keys, the names read through the synonym table (`synonyms`), a Mermaid ER diagram; `tables` narrows the answer to names or patterns while the plan is still made from the whole schema, `detail` is `auto` (full up to 60 tables, then one line per key and relationship without field names or diagram), `full` or `summary`, `mermaid=false` leaves the diagram out; every answer stays under 60 000 characters and says when it was cut | no |
| `validate_plan` | `workspace`, `source`, `schema`, `keys`, `confirmed`, `max_items` | checks the plan against the rows: is each key unique and free of NULLs, does every reference find its target (orphan count); one small counting query per key and relationship | no |
| `sample_rows` | `workspace`, `source`, `table`, `schema`, `n` | the first n rows (at most 20) of one table, long text shortened, to check what a column means | no |
| `create_backend` | `workspace`, `source`, `name`, `schema`, `writable`, `keys`, `confirmed`, `tables` | creates the API for GraphQL item with nested relationships, or updates the item of that name in place; returns the endpoint and the two portal steps | creates/updates one item; never deletes |
| `describe_backend` | `workspace`, `api` | types, fields and relationships of an existing API for GraphQL item, in the names a query uses, read from its definition (no introspection needed) | no |
| `query_graphql` | `workspace`, `api`, `query`, `variables` | runs a read-only GraphQL query against an API (name or id); mutations are refused | no |
| `rayfin_connector` | `workspace`, `source`, `connector`, `schema`, `keys`, `confirmed`, `tables`, `relationships` | Rayfin (Fabric Apps) connector entity classes and `schema.ts` | no |
| `ontology_draft` | `workspace`, `source`, `name`, `schema`, `keys`, `confirmed`, `tables` | the plan as a Fabric IQ ontology (preview) draft: summary, binding checklist, a Turtle file for the portal import, the item definition | no |
| `semantic_model_draft` | `workspace`, `source`, `name`, `schema`, `keys`, `confirmed`, `tables` | a Power BI semantic model in TMDL (`definition/` files): one Direct Lake table per source table on the SQL analytics endpoint, relationships with cardinality and one active path per table pair, keyless tables unrelated, `README.generated.md` with every decision to check; unit-tested against Microsoft's sample definitions; drafted from a live lakehouse on 26 October 2026, not yet created as an item | no |
| `join_path` | `workspace`, `source`, `start`, `end`, `schema`, `keys`, `confirmed` | the shortest chain of relationships between two tables with the rule per hop and a ready T-SQL `SELECT … JOIN …`; equally short paths all listed; with no path, which relationship is missing as a `confirmed` entry | no |
| `data_dictionary` | `workspace`, `source`, `schema`, `keys`, `confirmed`, `validate`, `max_items`, `tables` | hand-over documentation in Markdown: tables, columns and types, keys and relationships with rules, keyless and ambiguous items, the ER diagram, an empty Description column; `validate=true` adds the counts from `validate_plan`; `tables` (names or patterns) documents one part of a large schema at a time, and an answer over 60 000 characters is cut on a line and says so | no |
| `dbt_schema` | `workspace`, `source`, `schema`, `source_name`, `keys`, `confirmed`, `tables`, `arguments_block` | a dbt `schema.yml` with sources: `unique` and `not_null` on key columns, `relationships` on single-column relationships, in the syntax of the dbt documentation; composite keys noted as comments; `tables` takes names or patterns, an answer over 60 000 characters is cut and says so | no |
| `plan_drift` | `workspace`, `source`, `api`, `schema`, `keys`, `confirmed`, `tables`, `writable` | today's plan against an existing API for GraphQL item: new tables and columns, columns the API still maps that are gone, relationships the plan no longer supports, and whether `create_backend` with that name would change anything | no |
| `create_semantic_model` | `workspace`, `source`, `name`, `schema`, `keys`, `confirmed`, `tables`, `dry_run` | creates a Power BI semantic model item from the TMDL draft (Direct Lake on the SQL analytics endpoint) or updates the one of that name in place; `dry_run=true` (default) returns the parts and the REST call only; needs `SemanticModel.ReadWrite.All` or `Item.ReadWrite.All`; unit-tested; dry run answered from a live workspace on 26 October 2026, the create itself answered `consent` (HTTP 403) there because the app lacks the permission | creates/updates one item; never deletes |
| `create_views` | `workspace`, `source`, `schema`, `views_schema`, `keys`, `confirmed`, `dry_run` | `CREATE OR ALTER VIEW` in a schema of its own (default `krusgraph`, created if missing) on the source's SQL analytics endpoint or warehouse: one wide view per fact table with its dimensions, one per hard-to-read relationship; `dry_run=true` returns the SQL; needs the SQL right to create objects (Contributor); unit-tested on SQLite; ran for real on a live lakehouse SQL analytics endpoint on 26 October 2026 (schema and one wide view created, read back with `list_tables` and `sample_rows`) | creates/alters views in that schema only; never drops |
| `create_data_agent` | `workspace`, `source`, `name`, `schema`, `keys`, `confirmed`, `publish`, `dry_run` | creates or updates a Fabric data agent through the staging REST API: the plan as instructions, the source as data source with the plan's tables selected, 5–10 question/T-SQL examples, then publishes; `dry_run=true` returns instructions, examples and the calls; needs `Item.ReadWrite.All`; unit-tested with the calls mocked; dry run answered from a live workspace on 26 October 2026, the create itself answered `consent` (HTTP 403) there because the app lacks the permission | creates/updates one item and its staging config; never deletes |
| `create_ontology` | `workspace`, `source`, `name`, `schema`, `keys`, `confirmed`, `tables`, `dry_run` | creates a Fabric IQ ontology (preview) item from the plan or updates the one of that name in place: entity types with keys and properties, relationship types and Direct Lake-style bindings in the item's generation-2 definition; `dry_run=true` (default) returns the parts and the REST call only; needs `Item.ReadWrite.All` and Contributor on the workspace (`POST /workspaces/{id}/ontologies`, `updateDefinition`; fabric-rest-api-specs read 26 October 2026); unit-tested, not yet run live | creates/updates one item; never deletes |
| `app_starter` | `workspace`, `api` | from an existing API's definition: a Lovable prompt with the data model and main views, a connection description, five GraphQL queries walking the relationships, the portal checklist, and the backend an app needs so that no secret reaches the browser: a Supabase edge function (service principal, client credentials, secrets as Supabase secrets), the frontend helper, and the per-user alternative; the prompt and queries ran against a live API on 26 October 2026, the backend part is unit-tested | no |
| `app_readiness` | `workspace`, `api` | what an app still needs on an existing API: types without a key, types in no relationship, write access (from the definition), whether introspection is on (one introspection query to the endpoint), and "unknown" with the portal path for what the Fabric API cannot read (permissions, the tenant setting for service principals); a next step per item; unit-tested | no (one introspection query) |
| `analyze_schema` | `workspace`, `source`, `schema`, `keys`, `confirmed`, `tables`, `detail` | the plan as a graph, metadata only (`tables` and `detail` as in `plan_backend`; the summary groups tables by role and keeps the central tables, the areas by size and counts): table roles (fact, dimension, bridge, isolated) with the numbers behind them, the ten most central tables (degree, betweenness, PageRank), subject areas, cycles and table pairs with more than one path, and which relationships can be active at once; unit-tested | no |
| `lineage` | `workspace`, `source`, `schema`, `table` | which objects in the workspace build on the source's tables: GraphQL APIs (from their definition), semantic models (from their TMDL definition), views on the SQL analytics endpoint (`INFORMATION_SCHEMA.VIEW_TABLE_USAGE`), data agents (named in their definition, marked as not certain); a graph of tables and objects, the objects per table, the tables used by nothing, the items that could not be read; with `table`, what a change to it reaches; unit-tested, not yet run against a live workspace | no |
| `suggest_relationships` | `workspace`, `source`, `schema`, `keys`, `confirmed`, `check` | columns that could point at another table's key but are in no relationship, ranked by name, type and triangular closure, the best `check` counted against the data (inclusion share, distinct values); each with a ready `confirmed` entry; suggests only, never applies; unit-tested | no (counting queries) |

When a call cannot be completed, the tool answers with three fields instead of a bare failure: `error` (what
happened, in plain words), `kind` (a stable code such as `not_found`, `no_access`, `capacity`, `sign_in`,
`consent`, `schema_not_found`, `table_not_found`, `bad_input` or `timeout`) and `hint` (what to do next). Tokens, request
headers and stack traces never appear in these answers. A query result too large for one answer comes back as valid
JSON with every list cut to its first items and a `truncated` note saying so; page with `first:`/`after` for the rest.

## How relationships are inferred

A lakehouse has no declared keys, so names are all there is — and every result says which rule produced it,
so you can overrule it. Declared keys and foreign keys (warehouses) always win. A column that could point at
two tables is reported, never guessed; a column no rule matches is left unlinked and you can pass it as
`confirmed`. The [demo](/explore) shows the rules on a synthetic schema. The rules, in the engine's own words:

{{RULES_TABLE}}

Names are matched literally first. When nothing matches, a small documented **synonym table** is tried: abbreviations
(`cust`, `prod`, `ord`, `emp`, `dept`, `acct`, …), Swedish and German business words in singular and plural (`kund`/`kunder`,
`artikel`/`artiklar`, `leverantör`, `kunde`/`kunden`, `bestellung`, `rechnung`, `mitarbeiter`, …), after transliteration of
`å ä ö ü ß`; a leading `dim_`, `fact_` or `tbl_` is not part of a table's name, and `_sk`/`_bk` count as key suffixes. Every
match that rests on the table is listed under `synonyms` in `plan_backend` and on the relationship's `note`, and counts as
the weakest rule (R4), so the plan never hides that it translated a name. Measured on eleven schemas in
`docs/INFERENCE.md`; the five public schemas that need no synonyms are unchanged to the number.

More on how they interact, with examples: https://github.com/Krusmaster/fabric-backend#how-the-relationships-are-inferred

## How {{PRODUCT}} uses graph theory

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
every value present in `addresses.address_id` (15 distinct values) and well below that for the other candidates.

## One plan, five Fabric pieces

Everything {{PRODUCT}} creates comes from one plan: the keys and relationships inferred from a source, with the rule behind
each one, checked against the rows and corrected by you through `keys` and `confirmed`. From that plan, each with a
dry run first: `create_backend` makes the **API for GraphQL** with nested relationships; `create_semantic_model` the
**Power BI semantic model** in Direct Lake mode with the same relationships; `create_ontology` the **Fabric IQ ontology**
with entity types, keys, relationship types and bindings; `create_views` the **wide T-SQL views** on the SQL analytics
endpoint; `create_data_agent` the **data agent** with the plan as instructions and examples. Change the plan once (a
confirmed relationship, a key) and every piece is rebuilt from it; `plan_drift` and `lineage` tell you what a change
reaches. The pieces agree with each other because none of them was modelled by hand.

## Fabric IQ: the same graph as an ontology

Fabric IQ's **ontology (preview)** item describes a business as entity types with properties and a key, relationship
types between them, and data bindings to tables. That is the information {{PRODUCT}} already infers for a source, with
the rule behind every key and link. `ontology_draft` writes the plan in the ontology item's own shape, nothing deployed:

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
specification, read 26 October 2026). `create_ontology` does that with a dry run by default; without the permission it
answers `consent` naming the scope. The portal route (Import ontology with the Turtle file) needs nothing beyond what
you already have. Once an ontology exists, Fabric IQ's own pieces take over: the ontology agent and data
agents use it as context, and the built-in graph can be materialised from its entity and relationship types. Ontology
is in preview and its definition format can change; the draft follows the item's own definition as of 2026 and has been
checked against recorded definitions, not yet live from {{PRODUCT}}.

## Snowflake, Databricks and other data

{{PRODUCT}} reads sources through Fabric, so data that lives elsewhere takes one of two routes:

1. **Bring it into Fabric.** A *Snowflake database* item, a *Mirrored database* (Snowflake, Azure SQL, Cosmos DB, SAP via
   Datasphere, …), a *Mirrored Azure Databricks catalog* or a *Mirrored catalog* (preview) is a source like a lakehouse:
   `list_sources` shows it, `plan_backend` plans it and `create_backend` builds the API over its SQL analytics endpoint.
   The item is set up once in the Fabric portal; {{PRODUCT}} reads the endpoint id from the item, as Microsoft's REST
   specification documents it for each of these item types.
2. **Plan it where it is.** The engine reads `INFORMATION_SCHEMA`, which Snowflake and Databricks (Unity Catalog)
   expose like the Fabric SQL endpoint does. The open-source library, the CLI and the local `fabric-backend-mcp` server
   give you the graph, the rules, the diagram and the Rayfin entities straight from those systems; the API for GraphQL
   item is a Fabric object, so that last step needs route 1.

Snowflake has no `KEY_COLUMN_USAGE` view, so keys there come from names (rule K2) and are shown as such. Unity Catalog's
informational primary and foreign keys are read as declared keys (K0, R0). The item types, routes and `sqlEndpointProperties`
follow Microsoft's published REST specification; a live run of these source types is still pending.

## Cold start, and `min_replicas` if you run it yourself

The hosted instance runs on Azure Container Apps and may scale to zero when nobody has used it for a while. The
first call after such a pause starts the container, which takes tens of seconds; an MCP client that gives up after
about thirty seconds, as Claude does, may report the first call as failed. Ask again: the second call answers in
well under a second. Health probes start one second after the container does, so a cold start is as short as the
platform allows.

If you run the server yourself with `deploy/krusgraph.sh`, `min_replicas` in `deploy/krusgraph.json` decides this:
`0` (the default) scales to zero when idle and is the cheapest, `1` keeps one instance warm so there is never a cold
start, at the cost of one always-on instance. The change takes effect with `--update`. A container on a VM or in
Docker does not scale to zero and has no cold start.

## Two steps stay manual

Fabric has no API for these yet, and the connector tells you when they are needed:

1. **Introspection** on the GraphQL item (item → Settings → Introspection) — needed by tools such as Lovable that read the schema.
2. **Permissions** on the item for other apps or service principals that should query it.

## Use with Lovable

Lovable's Microsoft Fabric connector reads an existing API for GraphQL item. {{PRODUCT}} creates that item; after the
two manual steps above, Lovable connects to it. Step by step: [Use {{PRODUCT}} with Lovable](/lovable). `app_readiness`
says what is still missing on the API; `app_starter` gives the prompt, the queries and a Supabase edge function that
keeps the app's Entra secret on the server side. The whole chain, with who does each step and what still blocks, is in
the repository's `docs/LOVABLE-END-TO-END.md`.

## For agents

A Markdown version of these docs is at [/docs.md](/docs.md); [/llms.txt](/llms.txt) lists the rest and
[/llms-full.txt](/llms-full.txt) has every page in one file. MCP clients can read the server's identity and transport
from its Server Card at `{{MCP_URL}}/server-card`, and the OAuth metadata at `/.well-known/oauth-protected-resource`.
The same URL works from the command line once a client's sign-in redirect is registered on the Entra app
(for Claude Code: `claude mcp add --transport http {{PRODUCT_LOWER}} {{MCP_URL}}`); until then Claude is the tested client.
A Claude plugin that bundles this connector with a skill for the whole workflow and the commands `/krusgraph:plan`,
`/krusgraph:document` and `/krusgraph:explain-schema` is built and tested in the repository (`plugin/krusgraph`) and
coming soon; it is not published yet.

## Support

{{CONTACT}} · [Support the work](/support) · Source (MIT): https://github.com/Krusmaster/fabric-backend
