# Krusgraph plugin for Claude

Turn the tables of a Microsoft Fabric lakehouse, warehouse or SQL database into an explainable graph and a GraphQL
API, from a conversation with Claude. The plugin bundles the Krusgraph connector (`https://krusgraph.com/mcp`) with
a skill that walks Claude through the work in the right order and three commands for the common asks.

## What it does

- **Plan**: keys and relationships inferred from the source's metadata, each with the rule that produced it, checked
  against the rows (uniqueness, NULLs, orphans). Ambiguous columns are reported, never guessed.
- **Create**: one API for GraphQL item in your workspace, created or updated in place, never deleted; a drift check
  before a re-run on an existing API.
- **Hand over**: a Power BI semantic model (TMDL, Direct Lake), a data dictionary, a dbt sources file with tests, wide
  T-SQL views, and the starter pack for an app on the API (including the backend that keeps the app's secret out of
  the browser).

Commands: `/krusgraph:plan` (plan and validate a source), `/krusgraph:document` (data dictionary and dbt file),
`/krusgraph:explain-schema` (the source as a graph, and how two tables connect). The skill
`fabric-graph-backend` loads on its own when you talk about Fabric data.

## Requirements

- A Microsoft Fabric workspace you can read (a lakehouse, warehouse or SQL database on a running capacity).
- A Microsoft Entra work account. The connector signs you in with Microsoft; every call runs with your own Fabric
  permissions. The first user from an organisation needs the tenant admin's consent for the Krusgraph app.
- Creating the API needs the Fabric permission to create items in the workspace (Contributor).

## Install

- **Claude Code**: from a checkout of this repository, `claude --plugin-dir plugin/krusgraph`, or install it from a
  marketplace that lists it once one is published.
- **claude.ai and Cowork**: once the plugin is listed in Anthropic's directory, add it from there; until then, zip
  the `plugin/krusgraph` folder and upload it under Customize > Plugins > Add > Upload plugin. Connect the Krusgraph
  connector from the plugin's Connectors tab and sign in with Microsoft.

## Data

The plugin sends your questions and the tool calls Claude makes to `krusgraph.com`, which reads table and column
names from your Fabric workspace with your own sign-in, runs the counting queries you ask for, and stores nothing.
Privacy policy: https://krusgraph.com/privacy. Source and licence (MIT): https://github.com/Krusmaster/fabric-backend.
