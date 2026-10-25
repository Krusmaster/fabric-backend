# {{PRODUCT}} docs

Using {{PRODUCT}} with Microsoft Fabric: turn the tables in a lakehouse, warehouse or SQL database into an explainable graph and a GraphQL API —
keys and relationships inferred, with the rule behind every link shown. Use it from Claude today, and from other
MCP clients once their sign-in redirects are registered (see *Connect*). Try the [demo](/explore) first if you
like; it needs no account.

## Connect

1. **Your Entra admin grants consent once** for your organization:
   [grant admin consent](https://login.microsoftonline.com/organizations/adminconsent?client_id={{CLIENT_ID}}).
   It allows the connector to call Fabric and SQL as each signed-in user — nothing more.
2. **In Claude:** Settings → Connectors → Add custom connector, with the URL
   `{{MCP_URL}}`. Sign in with your Microsoft work account. Claude Code and Cursor take the same URL, but their
   sign-in uses a local redirect that is not registered on the Entra app yet; until it is, Claude is the tested client.
3. **In Fabric:** you need access to the workspace you want to use, and a Fabric capacity (a trial is fine).

Every call runs with your own Fabric permissions. The step-by-step version is on [/start](/start).

## What it accesses

The Entra app asks for delegated permissions only, all acting as the signed-in user: `User.Read` (sign-in),
`Workspace.Read.All` and `Item.Read.All` (listing sources, reading metadata), `GraphQLApi.ReadWrite.All` (creating or
updating the one item you ask for; it never deletes), `GraphQLApi.Execute.All` (your read-only queries) and Azure SQL
`user_impersonation` (table and column names from the SQL analytics endpoint).

**The data path.** Metadata (workspace, item, table and column names) and the query results you ask for pass through
the server on their way to your MCP client. Your tokens are exchanged on your behalf and held in memory only. The
server has no database, keeps no files and stores nothing between requests. Details: [privacy policy](/privacy).

## What you can ask

- *"Which Fabric workspaces can I see?"* — then any tool takes the workspace by name or id.
- *"List the data sources in the Sales workspace."*
- *"Plan a backend over the sales lakehouse."* — nothing is deployed; you get keys, relationships, the rule for each, ambiguous columns and an ER diagram.
- *"Create it as sales_api."* — creates a Fabric API for GraphQL item with nested relationships, or updates it in place if the name exists.
- *"Using sales_api, which customers ordered a trail bike in October?"* — a read-only GraphQL query.
- *"Generate Rayfin connector entities for it."* — TypeScript entity classes for Fabric Apps.
- *"Draft a Fabric IQ ontology from the sales lakehouse."* — entity types, keys and relationship types with their rules, ready to import or create.

## Tools

| Tool | Does | Changes anything |
| --- | --- | --- |
| `list_workspaces` | the workspaces the signed-in account can see, with id and capacity | no |
| `list_sources` | lakehouses, warehouses, SQL and mirrored databases, existing GraphQL APIs in a workspace (id or name) | no |
| `list_tables` | tables and columns with types | no |
| `plan_backend` | inferred keys and relationships, each with its rule (K0–K3, R0–R3); ambiguous and keyless tables | no |
| `create_backend` | creates or updates one API for GraphQL item | creates/updates one item; never deletes |
| `rayfin_connector` | Rayfin (Fabric Apps) connector entities | no |
| `ontology_draft` | the plan as a Fabric IQ ontology (preview) draft: entity types, keys, relationship types, bindings, TTL and item definition | no |
| `query_graphql` | runs a read-only query; mutations are refused | no |

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

More on how they interact, with examples: https://github.com/Krusmaster/fabric-backend#how-the-relationships-are-inferred

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

Creating the item through the API needs the delegated scope `Item.ReadWrite.All` and Contributor on the workspace.
The connector asks for that scope only when its operator enables `create_ontology`; the portal route needs nothing
beyond what you already have. Once an ontology exists, Fabric IQ's own pieces take over: the ontology agent and data
agents use it as context, and the built-in graph can be materialised from its entity and relationship types. Ontology
is in preview and its definition format can change; the draft follows the item's own definition as of 2026 and has been
checked against recorded definitions, not yet live from {{PRODUCT}}.

## Snowflake, Databricks and other data

{{PRODUCT}} reads sources through Fabric, so data that lives elsewhere takes one of two routes:

1. **Mirror it into Fabric.** A *Mirrored database* (Snowflake, Azure SQL, Cosmos DB, SAP via Datasphere, …) or a
   *Mirrored Azure Databricks catalog* is a source like a lakehouse: `list_sources` shows it, `plan_backend` plans it
   and `create_backend` builds the API over its SQL analytics endpoint. Mirroring is set up once in the Fabric portal.
2. **Plan it where it is.** The engine reads `INFORMATION_SCHEMA`, which Snowflake and Databricks (Unity Catalog)
   expose like the Fabric SQL endpoint does. The open-source library, the CLI and the local `fabric-backend-mcp` server
   give you the graph, the rules, the diagram and the Rayfin entities straight from those systems; the API for GraphQL
   item is a Fabric object, so that last step needs route 1.

Snowflake has no `KEY_COLUMN_USAGE` view, so keys there come from names (rule K2) and are shown as such. Unity Catalog's
informational primary and foreign keys are read as declared keys (K0, R0). The mirrored-catalog route has been
verified against recorded Fabric answers, not live yet.

## Two steps stay manual

Fabric has no API for these yet, and the connector tells you when they are needed:

1. **Introspection** on the GraphQL item (item → Settings → Introspection) — needed by tools such as Lovable that read the schema.
2. **Permissions** on the item for other apps or service principals that should query it.

## Use with Lovable

Lovable's Microsoft Fabric connector reads an existing API for GraphQL item. {{PRODUCT}} creates that item; after the
two manual steps above, Lovable connects to it. Step by step: [Use {{PRODUCT}} with Lovable](/lovable).

## For agents

A Markdown version of these docs is at [/docs.md](/docs.md); [/llms.txt](/llms.txt) lists the rest and
[/llms-full.txt](/llms-full.txt) has every page in one file. MCP clients can read the server's identity and transport
from its Server Card at `{{MCP_URL}}/server-card`, and the OAuth metadata at `/.well-known/oauth-protected-resource`.
The same URL works from the command line once a client's sign-in redirect is registered on the Entra app
(for Claude Code: `claude mcp add --transport http {{PRODUCT_LOWER}} {{MCP_URL}}`); until then Claude is the tested client.

## Support

{{CONTACT}} · [Support the work](/support) · Source (MIT): https://github.com/Krusmaster/fabric-backend
