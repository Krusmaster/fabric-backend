# Krusgraph beside Microsoft's MCP servers

Krusgraph is one MCP server among several a person can add to the same client. Microsoft publishes its own MCP servers
for Fabric and Power BI; they manage workspaces and items, read OneLake files, run T-SQL and DAX, and edit semantic
models. Krusgraph works out how the tables in a source relate, with the rule behind every link, checks it against the
rows, and builds from that plan. The two are complements in one client: there is no server-to-server connection, no
shared state and no dependency between them. Each tool call goes from the client to one server, with the person's own
permissions on each side.

This is the long form of the `/docs` section "With Microsoft's Fabric MCP servers" (`fabric_backend/page_templates/DOCS.md`),
which carries the links to Microsoft Learn. Written 2 November 2026 (round n76). `learn.microsoft.com` could not be
opened from the session that wrote this file, so no new Learn link is added here; Microsoft's pages were read from the
documentation's source repository, MicrosoftDocs/fabric-docs (branch `main`), and each is cited by its file and
`ms.date`. The server rows are kept in `docs/ECOSYSTEM-WATCHLIST.md`. Krusgraph is an independent open-source project of
Kruse Consulting AB and is not affiliated with Microsoft.

## Who does what

| Need | Server | Why that one |
| --- | --- | --- |
| Find the workspace and the lakehouse; list items; read a file in OneLake; look up a Fabric REST specification or an item-definition example | Microsoft's Fabric MCP Server (microsoft/mcp, `servers/Fabric.Mcp.Server`; local, toolsets `core`, `docs`, `onelake`, `datafactory`) | Its README: a local-first server with "comprehensive access to Microsoft Fabric's public APIs, item definitions, and best practices"; the OneLake tools "use your existing Azure identity and Fabric permissions" (fabric-docs `docs/onelake/onelake-local-mcp.md`, ms.date 10/21/2026). Krusgraph lists workspaces, sources and tables too (`list_workspaces`, `list_sources`, `list_tables`), but only as the way in to a plan. |
| Which tables relate, on what rule, and does it hold against the rows | Krusgraph (`plan_backend`, `validate_plan`, `suggest_relationships`, `analyze_schema`, `join_path`) | The rule behind every key and relationship (K0–K5, R0–R5 or a pack's source) and the counts: duplicate key values, references with no matching row, the total that doubles (`fabric_backend/infer.py`, `evidence.py`, `amounts.py`). None of Microsoft's servers above describes this in its own pages. |
| Build from the reviewed plan: an API for GraphQL, a semantic model, an ontology item, views, notebooks, a drift monitor, item files for Git | Krusgraph (`create_backend`, `create_semantic_model`, `create_ontology`, `create_views`, `create_silver_notebook`, `create_gold_views`, `create_drift_monitor`, `export_item_definitions`), dry run by default, never deleting | The status per tool, in the site's words, is https://krusgraph.com/docs#test-status (`fabric_backend/tool_status.py`). |
| Edit the semantic model afterwards: measures, DAX, TMDL files, deploy to Fabric | Microsoft's Power BI modeling MCP server (microsoft/powerbi-modeling-mcp) | Its README: connect to or create a model, import and export TMDL folders, deploy to Fabric, manage measures, run and validate DAX. A model Krusgraph creates is an ordinary semantic model (`create_semantic_model` created `shop_model_live` on 29 October 2026, `fabric_backend/tool_status.py`), so that server can open it. `compare_semantic_model` in Krusgraph then checks the edited model against the plan. |
| Ask questions of the model or a report, in DAX, with row-level security applied | Fabric IQ MCP (remote, Microsoft-hosted) | "exposes a read-only toolset that helps an agent find Power BI content, inspect report and semantic model metadata, locate relevant values, and run DAX queries against data the signed-in user can access"; needs the delegated `Item.Read.All` and `Item.Execute.All` (fabric-docs `docs/iq/connectors/fabric-iq-mcp.md`, ms.date 10/21/2026). Krusgraph's `query_graphql` answers read-only GraphQL on an API it created, which is a different route to the same tables. |
| Run T-SQL on a warehouse from the agent | Fabric Data Warehouse MCP server (remote, preview) | One tool, `executeSQL`, with a global or an item-scoped endpoint (fabric-docs `docs/data-warehouse/data-warehouse-mcp-server.md`, ms.date 06/16/2026). Krusgraph runs its own counting queries on the SQL analytics endpoint and drafts T-SQL (`answer_query_draft`, `join_path`); it does not run arbitrary T-SQL for the user. |
| Eventhouses, KQL, Activator | Real-Time Intelligence MCP servers (local and remote, preview) | fabric-docs `docs/real-time-intelligence/mcp-overview.md`, ms.date 10/21/2026. Outside Krusgraph's sources. |

## A typical pairing

1. Microsoft's Fabric MCP Server finds the workspace and the lakehouse, or the person names them.
2. Krusgraph plans the schema, the person reviews the rules and the counts, confirms what the rules could not decide
   (`keys=`, `confirmed=`), and creates the API and the semantic model from the reviewed plan.
3. The Power BI modeling MCP server adds measures and descriptions to that model; `compare_semantic_model` says
   where the model and the plan now differ.
4. Fabric IQ MCP answers questions on the model, with the person's own permissions.

Each step is a call from the client to one server. Krusgraph never calls Microsoft's servers and they never call
Krusgraph; what they share is the client.

## Permissions, side by side

Each server asks for its own permissions and sees nothing through the other. Krusgraph's are delegated Fabric, Azure SQL
and Microsoft Graph scopes approved once by an administrator (`docs/SCOPES.md`); Fabric IQ MCP asks for `Item.Read.All`
and `Item.Execute.All` from the Power BI Service API and "doesn't require administrator consent by default" (the same
fabric-docs page); the local Fabric MCP Server uses the person's `az login` identity. Revoking one leaves the others
untouched.

## What is not claimed

- Nothing about what Microsoft's servers cannot do; the rows quote what their own pages say they do.
- No measurement comparing Krusgraph's checks with any Microsoft tool on the same data; none exists
  (`docs/FAQ-COMPETITION.md`, `docs/MISSING-EVIDENCE.md`).
- No partnership, endorsement or certification. "Microsoft Fabric" is used descriptively.
