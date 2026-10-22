# {{PRODUCT}} for Microsoft Fabric

Turn the tables in a Fabric lakehouse, warehouse or SQL database into a GraphQL API and an app backend —
keys and relationships inferred, with the rule behind every link shown. Use it from Claude, Claude Code,
Cursor or any MCP client.

## Connect

1. **Your Entra admin grants consent once** for your organization:
   [grant admin consent](https://login.microsoftonline.com/organizations/v2.0/adminconsent?client_id={{CLIENT_ID}}&scope=https://api.fabric.microsoft.com/.default%20https://database.windows.net/.default&redirect_uri=https://claude.ai/api/mcp/auth_callback).
   It allows the connector to call Fabric and SQL as each signed-in user — nothing more.
2. **In Claude:** add the {{PRODUCT}} connector from the directory, or as a custom connector with the URL
   `{{MCP_URL}}`. Sign in with your Microsoft work account.
3. **In Fabric:** you need access to the workspace you want to use, and a Fabric capacity (a trial is fine).

Every call runs with your own Fabric permissions. Nothing is stored — see the [privacy policy](https://{{DOMAIN}}/privacy).

## What you can ask

- *"List the data sources in workspace <id>."*
- *"Plan a backend over the sales lakehouse."* — nothing is deployed; you get keys, relationships, the rule for each, ambiguous columns and an ER diagram.
- *"Create it as sales_api."* — creates a Fabric API for GraphQL item with nested relationships, or updates it in place if the name exists.
- *"Using sales_api, which customers ordered a trail bike in October?"* — a read-only GraphQL query.
- *"Generate Rayfin connector entities for it."* — TypeScript entity classes for Fabric Apps.

## Tools

| Tool | Does | Changes anything |
| --- | --- | --- |
| `list_sources` | lakehouses, warehouses, SQL and mirrored databases, existing GraphQL APIs in a workspace | no |
| `list_tables` | tables and columns with types | no |
| `plan_backend` | inferred keys and relationships, each with its rule (K0–K3, R0–R3); ambiguous and keyless tables | no |
| `create_backend` | creates or updates one API for GraphQL item | creates/updates one item; never deletes |
| `rayfin_connector` | Rayfin (Fabric Apps) connector entities | no |
| `query_graphql` | runs a read-only query; mutations are refused | no |

## How relationships are inferred

A lakehouse has no declared keys, so names are all there is — and every result says which rule produced it,
so you can overrule it. Declared keys and foreign keys (warehouses) always win. A column that could point at
two tables is reported, never guessed. Full rules: https://github.com/Krusmaster/fabric-backend#how-the-relationships-are-inferred

## Two steps stay manual

Fabric has no API for these yet, and the connector tells you when they are needed:

1. **Introspection** on the GraphQL item (item → Settings → Introspection) — needed by tools such as Lovable that read the schema.
2. **Permissions** on the item for other apps or service principals that should query it.

## Support

{{CONTACT}} · Source (MIT): https://github.com/Krusmaster/fabric-backend
