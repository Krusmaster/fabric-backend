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

## Tools

| Tool | Does | Changes anything |
| --- | --- | --- |
| `list_workspaces` | the workspaces the signed-in account can see, with id and capacity | no |
| `list_sources` | lakehouses, warehouses, SQL and mirrored databases, existing GraphQL APIs in a workspace (id or name) | no |
| `list_tables` | tables and columns with types | no |
| `plan_backend` | inferred keys and relationships, each with its rule (K0–K3, R0–R3); ambiguous and keyless tables | no |
| `create_backend` | creates or updates one API for GraphQL item | creates/updates one item; never deletes |
| `rayfin_connector` | Rayfin (Fabric Apps) connector entities | no |
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

## Two steps stay manual

Fabric has no API for these yet, and the connector tells you when they are needed:

1. **Introspection** on the GraphQL item (item → Settings → Introspection) — needed by tools such as Lovable that read the schema.
2. **Permissions** on the item for other apps or service principals that should query it.

## Use with Lovable

Lovable's Microsoft Fabric connector reads an existing API for GraphQL item. {{PRODUCT}} creates that item; after the
two manual steps above, Lovable connects to it. Step by step: [Use {{PRODUCT}} with Lovable](/lovable).

## For agents

A Markdown version of these docs is at [/docs.md](/docs.md), and [/llms.txt](/llms.txt) lists the rest. MCP clients
can read the server's identity and transport from its Server Card at `{{MCP_URL}}/server-card`.

## Support

{{CONTACT}} · [Support the work](/support) · Source (MIT): https://github.com/Krusmaster/fabric-backend
