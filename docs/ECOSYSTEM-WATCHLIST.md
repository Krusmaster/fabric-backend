# Ecosystem watchlist: MCP servers around Microsoft Fabric

A manual register of MCP servers that touch Microsoft Fabric or Power BI, kept so that Krusgraph knows what sits next
to it, what is worth pointing a user at, and what is never copied. Every row says how it was read and when. "Observed"
for a licence means the LICENSE file itself was opened and read; "not verified" means it was not, and GitHub's own
metadata is written down for what it is. "Could not be opened from the session" is written where that was the case.
The code of none of these projects is in this repository; the rules for ever taking code from one are in
`CONTRIBUTING.md` under "Reusing external code".

How the rows were read on 2 November 2026: `github.com` pages and `api.github.com` were refused by the session's
network policy (HTTP 403); `raw.githubusercontent.com` served files, so LICENSE and README files were fetched from the
default branch at that address; repository metadata (description, licence as GitHub detects it, last push) came from
the GitHub search API through the `gh` command; `learn.microsoft.com` could not be opened, so Microsoft's pages were
read from the documentation's source repository, MicrosoftDocs/fabric-docs (branch `main`, file and `ms.date` given);
the MCP Registry (`registry.modelcontextprotocol.io`) answered.

## Microsoft's own

| Project | What it does (its own words) | Licence | Worth referring to | Not copied | Read |
| --- | --- | --- | --- | --- | --- |
| microsoft/mcp, `servers/Fabric.Mcp.Server` (the Fabric MCP Server; in the MCP Registry as `com.microsoft/microsoft-fabric`, latest 1.4.0) | "A local-first Model Context Protocol (MCP) server that provides AI agents with comprehensive access to Microsoft Fabric's public APIs, item definitions, and best practices. Documentation tools use bundled specifications without connecting to live Fabric environments; operational tools call Fabric APIs using the configured identity." Toolsets `core`, `docs`, `onelake`, `datafactory`; installed as a VS Code extension, a .NET tool or with `npx`. | MIT, observed (`LICENSE`: "Copyright 2025 (c) Microsoft Corporation") | The place to send a user for workspaces, items, OneLake files and the bundled API specifications and item-definition examples; `/docs` already links its README (`fabric_backend/page_templates/DOCS.md`, "With Microsoft's Fabric MCP servers"). Its OneLake page: fabric-docs `docs/onelake/onelake-local-mcp.md`, ms.date 10/21/2026 ("uses your existing Azure identity and Fabric permissions"). | Its tool code and its bundled specifications. Krusgraph reads Fabric's REST through its own adapter (`fabric_backend/platforms/fabric.py`) from the public API documentation, with the cases the docs do not say recorded in the module docstrings (`graphql.py`, `rayfin.py`). | README and LICENSE from raw.githubusercontent.com; registry entry; 2 November 2026 |
| Fabric IQ MCP (remote, Microsoft-hosted; no repository) | "a remote MCP server that connects AI agents … to Power BI reports and semantic models"; "exposes a read-only toolset" to find content, inspect metadata, locate values and run DAX "against data the signed-in user can access"; needs the delegated `Item.Read.All` and `Item.Execute.All` from the Power BI Service API; RLS and OLS apply; no service-principal sign-in. | Not a code project; Microsoft's service terms | Where questions to a model Krusgraph created should go (`docs/COMPANION-MCP.md`); `docs/SCOPES.md` already names its two permissions. | Nothing to copy. | fabric-docs `docs/iq/connectors/fabric-iq-mcp.md`, ms.date 10/21/2026 |
| microsoft/powerbi-modeling-mcp (the README calls it "Power BI Authoring MCP Server") | "brings Power BI semantic modeling capabilities to your AI agents": connect to or create a model, import and export TMDL folders, deploy to Fabric, manage measures, run and validate DAX, work with PBIP files; installed from the VS Code marketplace or by hand, with a step "Accept the EULA" in the README. | MIT for the repository, observed (`LICENSE`: "Copyright (c) Microsoft Corporation"); the README's EULA step suggests the distributed binary has terms of its own, not read | Where a user edits a semantic model after `create_semantic_model` or `semantic_model_draft`; `/docs` links it. | Its TMDL handling. Krusgraph writes TMDL from Fabric's documented format (`fabric_backend/semantic_model.py`). | README and LICENSE from raw.githubusercontent.com; 2 November 2026 |
| Fabric Data Warehouse MCP server (remote, preview) | "a hosted MCP endpoint that enables AI agents to work with a warehouse using natural language", one tool `executeSQL`, a global or an item-scoped endpoint, shown with VS Code and GitHub Copilot. | Microsoft's service terms | T-SQL on a warehouse from an agent; Krusgraph's counting queries run through the SQL analytics endpoint on its own (`fabric_backend/evidence.py`), so the two do not overlap. | Nothing to copy. | fabric-docs `docs/data-warehouse/data-warehouse-mcp-server.md`, ms.date 06/16/2026 |
| Real-Time Intelligence MCP (local open-source server and remote servers for eventhouses, Activator and operations agents; preview) | "two types of MCP servers: local and remote"; the local one "is an open-source server that you install, host, and manage yourself". | Not checked for the local server's repository (not opened) | Eventhouse and KQL are outside Krusgraph's sources; a reference only. | Nothing. | fabric-docs `docs/real-time-intelligence/mcp-overview.md`, ms.date 10/21/2026 |

## Community servers

| Project | What it does (its own words) | Licence | Worth referring to | Not copied | Read |
| --- | --- | --- | --- | --- | --- |
| datumnova/ms-fabric-mcp | "A comprehensive Python-based MCP server for interacting with Microsoft Fabric APIs, featuring advanced PySpark notebook development, testing, and optimization capabilities with LLM integration": workspace, lakehouse, warehouse and table management, Delta schemas, SQL execution, report and semantic model operations, notebook templates. | **Not verified.** No `LICENSE`, `LICENSE.md` or `LICENSE.txt` at the default branch (`main`) on 2 November 2026, and GitHub's metadata lists no licence. Without a licence, the code is all rights reserved. Last push per GitHub metadata: 27 May 2025. | Nothing for users: the overlap with Microsoft's own server is complete, and Krusgraph's part (keys, relationships, evidence) is not in it. | Everything. No licence means nothing may be copied, under `CONTRIBUTING.md`. | README from raw.githubusercontent.com; metadata from the GitHub search API; 2 November 2026 |
| Jasuni69/ms-core-mcp | "A Python MCP server that lets you manage Microsoft Fabric through natural language in Claude Code or Claude Desktop. 77+ tools covering workspaces, lakehouses, warehouses, SQL, DAX, semantic models, notebooks, pipelines, OneLake, and Microsoft Graph." Says it is "Inspired by" Augustab/microsoft_fabric_mcp (not opened). Signs in with `az login`. | **Not verified.** No licence file at `main` on 2 November 2026; GitHub's metadata lists none. Last push: 17 February 2026. | Nothing for users beyond what Microsoft's own server does; its DAX and SQL tools are what Fabric IQ MCP and the warehouse server do with the signed-in user's permissions. | Everything, for the same reason. | README from raw.githubusercontent.com; metadata from the GitHub search API; 2 November 2026 |
| mkoziel2000/mcp-fabric-api (npm `@einlogic/mcp-fabric-api`) | "MCP server for the Microsoft Fabric REST APIs. Built for data engineers and data analysts who want to use AI assistants beyond Copilot"; covers most item types including GraphQL APIs; "Safe by default: this server blocks all destructive operations (create, update, delete) until you explicitly configure the `WRITABLE_WORKSPACES` environment variable"; Node.js; `az login`, device code or service principal. | **AGPL-3.0, observed** (`LICENSE` is the GNU Affero General Public License, version 3). Last push: 8 September 2026. | Its `WRITABLE_WORKSPACES` idea (writes off until a workspace is named) is a design worth knowing about when R3 of `docs/RISK-REGISTER.md` is decided; the idea, not the code. | **All of it**: AGPL code is never taken into this repository (`CONTRIBUTING.md`). Using it as a separate server next to Krusgraph is the user's choice and is not affected. | README and LICENSE from raw.githubusercontent.com; metadata from the GitHub search API; 2 November 2026 |
| Augustab/microsoft_fabric_mcp | Named by Jasuni69/ms-core-mcp as its inspiration. | Not verified: could not be opened from the session (not attempted beyond the reference above). | — | Everything, until read. | Not read; 2 November 2026 |

## What this register is for

- Before a user is pointed at another server from `/docs` or a conversation, its row here says what it does in its own
  words and when that was read; a row older than a release of that server is re-read first.
- Before a line of code from any of them is considered, `CONTRIBUTING.md` ("Reusing external code") applies: a licence
  file read at a pinned commit, notices kept, no AGPL or SSPL, and nothing from a repository whose licence cannot be
  verified. Two rows above have no licence and one is AGPL; from those three nothing is ever copied.
- Krusgraph's own position next to all of them is `docs/COMPANION-MCP.md`.

## Updating a row

Change the "Read" column to the new date and say what changed. A project that disappears or changes licence keeps its
row with the old reading and a line about the change.
