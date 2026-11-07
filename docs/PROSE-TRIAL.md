# Prose trial: Get started (n142)

Internal and not linked from the site. Round n142 rewrote one page, `/docs/get-started` (the `## Get started` section of
`fabric_backend/page_templates/DOCS.md`), to see whether plainer prose reads better. The aim is clarity. The page says
the same things as before. Every heading and anchor is unchanged.

## Style rules applied

- Short, direct sentences. Long sentences joined by semicolons or colons were split.
- No em-dash asides. The tool list used ` — ` twice per line. It now uses a label colon and full sentences.
- No colon-then-reveal sentences ("…, only https and local addresses", "…: [/local]").
- Plainer words ("returns the admin" became "sends the admin", "allows" became "lets").
- Kept as they were: the five first questions (pinned by tests and quoted by the server), the error table's first two
  columns, all template markers, links, commands and JSON.
- Three sentences about Cursor stay long on purpose. The site test
  `test_no_page_claims_every_tool_nothing_stored_or_cursor_as_a_working_client` needs each sentence that names Cursor to
  carry its caveat in the same sentence.

## Factual statements, and where they sit

"Same place" means the same subsection and the same list item or table row in both versions.

| # | Statement | Old | New |
| --- | --- | --- | --- |
| 1 | The guided demo (`/check?example=sample&guide=1`) runs the engine on a synthetic shop in the browser | intro, sentence 3 | intro, sentence 4 |
| 2 | Onto leads four steps: how tables connect, the total that doubles, a suggestion to decide on, on to Power BI or an app | intro, sentence 3 | intro, sentences 6–8 |
| 3 | The demo needs no account | intro, end of sentence 3 | intro, sentence 5 |
| 4 | The Entra admin grants consent once per organization, via the admin-consent link | Connect, step 1 | same place |
| 5 | Consent lets the connector call Fabric and SQL as each signed-in user, and nothing more | Connect, step 1 | same place (two sentences) |
| 6 | Microsoft returns the admin to `/consent/done`, which says whether consent was granted and, if not, what to do | Connect, step 1 | same place (two sentences) |
| 7 | In Claude: Customize → Connectors → Add → Add custom connector with `{{MCP_URL}}`; sign in with a Microsoft work account | Connect, step 2 | same place |
| 8 | (with client registration) VS Code, Cursor and other self-signing clients use `{{CONNECT_URL}}`, link to `#other-mcp-clients` | Connect, step 2 | same place, unchanged |
| 9 | (without client registration) the hosted service supports Claude and was tested with Claude | Connect, step 2 | same place |
| 10 | (without) Claude Code and Cursor use a local redirect not registered on the Entra app, so cannot sign in today | Connect, step 2 | same place |
| 11 | (without) other MCP clients should work when self-hosted; not tested yet | Connect, step 2 | same place (two sentences) |
| 12 | In Fabric you need access to the workspace and a Fabric capacity; a trial is fine | Connect, step 3 | same place (three sentences) |
| 13 | Every call runs with your own Fabric permissions | Connect, paragraph after the steps | same place |
| 14 | Step-by-step version on `/start` | same paragraph | same place |
| 15 | Published in the official MCP Registry as `com.krusgraph/krusgraph`, verified 26 October 2026, with the registry link | same paragraph | same place |
| 16 | The same engine runs locally over ODBC against SQL Server: `/local` | same paragraph, last sentence | same place (two sentences) |
| 17 | Self-registering clients sign in at `{{CONNECT_URL}}`, not the Claude address | Other MCP clients, para 1, s1 | same place, s1–2 |
| 18 | The client is identified by its metadata document, or a strict registration if it has none | para 1, s2 | s3–4 |
| 19 | Own approval page with client name, domain and where the answer goes, then Microsoft | para 1, s2 | s5–6 |
| 20 | Calls still run with your own permissions; nothing changes for Claude | para 1, s3 | s7–8 |
| 21 | `{{CONNECT_TESTED}}` sentence | para 1, end | same place, unchanged |
| 22 | VS Code config (`.vscode/mcp.json` or *MCP: Open User Configuration*, JSON, *MCP: List Servers* → Start) | VS Code item | same place |
| 23 | VS Code: approval page returns at each new sign-in because the answer goes to a local program | VS Code item | same place |
| 24 | Cursor config (`~/.cursor/mcp.json`, JSON, sign in from MCP settings) | Cursor item | same place |
| 25 | Some Cursor builds register `cursor://`, not accepted; only https and local addresses | Cursor item, in a parenthesis | same item, own sentences |
| 26 | Workaround: register once with the `curl` command, then use the `client_id` as `"auth"` next to `url` | Cursor item | same place, command unchanged |
| 27 | Glama: add `{{CONNECT_URL}}`; it identifies itself with its metadata document | Glama item | same place |
| 28 | Claude Code command, not tried yet | Claude Code item | same place, unchanged |
| 29 | Approval page and Microsoft sign-in open in your browser; a company web filter can block them ("uses an unsupported protocol"); use another network or ask IT to allow `{{DOMAIN}}` | last paragraph | same place (three sentences) |
| 30 | One example per tool, in the usual first-session order (list, plan, rows, check, create, describe, query) | What you can ask, intro | same place (two sentences) |
| 31 | The fifteen tools and their example questions | tool list | same place, same order, same quoted questions |
| 32 | `plan_backend` deploys nothing; returns keys, relationships, the rule for each, ambiguous columns, suggested composite keys, ER diagram; the `keys` example | `plan_backend` item | same place |
| 33 | `sample_rows` is for a column whose meaning is unclear before deciding keys | `sample_rows` item | same place |
| 34 | `validate_plan` counts every key for uniqueness and NULLs and every relationship for orphans; example on `/check?example=sample` | `validate_plan` item | same place |
| 35 | `create_backend` creates the API for GraphQL item, or updates it in place if the name exists; dry run first | `create_backend` item | same place (three sentences) |
| 36 | `describe_backend` gives types, fields, relationship names | item | same place |
| 37 | `query_graphql` is read-only; relationships nest | item | same place |
| 38 | `rayfin_connector`: TypeScript entity classes for Fabric Apps | item | same place |
| 39 | `ontology_draft`: entity types, keys, relationship types with rules, ready to import | item | same place |
| 40 | `compare_semantic_model`: what the model lacks, what a rule or the data contradicts, measures it could add | item | same place |
| 41 | `gold_views_draft`: one materialized lake view per fact table over silver tables, with data quality rules | item | same place |
| 42 | `export_item_definitions`: item folders in Fabric's Git format to commit | item | same place |
| 43 | `review_plan`: a file to commit next to the code; read back next time | item | same place |
| 44 | The five first questions and their tools | numbered list | same place, unchanged |
| 45 | Every first-time error answer carries this section's link in its `hint` | First-time errors, intro | same place |
| 46 | `sign_in` row: reconnect path; MFA if it loops | table | same row |
| 47 | `consent` row: consent link on `/start` opens Microsoft's page; Accept, then reconnect; the five creating tools name the missing scope (`Item.ReadWrite.All`, `SemanticModel.ReadWrite.All`); operator adds it, `docs/SCOPES.md`; dry runs work meanwhile | table | same row |
| 48 | `no_access` row: HTTP 403; Viewer enough for reading and planning, Contributor for `create_backend`, `create_views` and other creating tools; `list_workspaces` | table | same row |
| 49 | `capacity` row: Workspace settings → License info; trial enough; SQL endpoints answer a minute after capacity is up | table | same row |
| 50 | `schema_not_found` row: `dbo` without schemas; by name with schemas; new tables need an endpoint metadata refresh | table | same row |
| 51 | `sql_sign_in` row: reconnect; else share the lakehouse or warehouse, not only the workspace | table | same row |
| 52 | Other kinds (`not_found`, `timeout`, `throttled`, `bad_input`, …) are explained in the answer, same three fields | last paragraph | same place |

No statement was added. One wording was checked against the meaning and kept: "published in the official MCP Registry"
(a draft said "listed"; that was reverted).

## Old and new, by subsection

### Get started

**Old**

````markdown
New to a Fabric lakehouse? Start by understanding how its tables fit together: connect the hosted server to Claude, then ask a first question. The [guided demo](/check?example=sample&guide=1) runs the engine on a synthetic shop in your browser, and Onto leads four steps over its map: how the tables connect, the total that doubles, a suggestion to decide on and on to Power BI or an app; it needs no account.
````

**New**

````markdown
New to a Fabric lakehouse? Start with how its tables fit together. Connect the hosted server to Claude, then ask a first question. The [guided demo](/check?example=sample&guide=1) runs the engine on a synthetic shop in your browser. It needs no account. Onto leads four steps over its map. The first three show how the tables connect, the total that doubles and a suggestion to decide on. The fourth leads on to Power BI or an app.
````

### Connect

**Old**

````markdown
1. **Your Entra admin grants consent once** for your organization:
   [grant admin consent](https://login.microsoftonline.com/organizations/adminconsent?client_id={{CLIENT_ID}}&redirect_uri={{CONSENT_URL_ENC}}).
   It allows the connector to call Fabric and SQL as each signed-in user — nothing more. Microsoft then returns the admin
   to [{{DOMAIN}}/consent/done](/consent/done), which says whether the consent was granted and, if not, what to do next.
2. **In Claude:** Customize → Connectors → Add → Add custom connector, with the URL
   `{{MCP_URL}}`. Sign in with your Microsoft work account. {{#IF CLIENT_REGISTRATION}}VS Code, Cursor and other MCP clients
   that sign in on their own use `{{CONNECT_URL}}` instead ([below](#other-mcp-clients)).{{/IF}}{{#IF NO_CLIENT_REGISTRATION}}The hosted service supports Claude, and that is the client
   it has been tested with. Claude Code and Cursor sign in through a local redirect that is not registered on the Entra
   app yet, so they can't sign in to {{DOMAIN}} today. Other MCP clients should work when you host {{PRODUCT}} yourself (not tested yet).{{/IF}}
3. **In Fabric:** you need access to the workspace you want to use, and a Fabric capacity (a trial is fine).

Every call runs with your own Fabric permissions. The step-by-step version is on [/start](/start). The server is
published in the official [MCP Registry](https://registry.modelcontextprotocol.io/v0.1/servers?search=com.krusgraph%2Fkrusgraph) as `com.krusgraph/krusgraph` (verified 26 October 2026).
Prefer your own machine and a SQL Server? The same engine runs locally over ODBC: [/local](/local).
{{#IF CLIENT_REGISTRATION}}
````

**New**

````markdown
1. **Your Entra admin grants consent once** for your organization:
   [grant admin consent](https://login.microsoftonline.com/organizations/adminconsent?client_id={{CLIENT_ID}}&redirect_uri={{CONSENT_URL_ENC}}).
   This lets the connector call Fabric and SQL as each signed-in user. It allows nothing more. Microsoft then sends the
   admin to [{{DOMAIN}}/consent/done](/consent/done). That page says whether the consent was granted, and what to do next if it was not.
2. **In Claude:** Customize → Connectors → Add → Add custom connector, with the URL
   `{{MCP_URL}}`. Sign in with your Microsoft work account. {{#IF CLIENT_REGISTRATION}}VS Code, Cursor and other MCP clients
   that sign in on their own use `{{CONNECT_URL}}` instead ([below](#other-mcp-clients)).{{/IF}}{{#IF NO_CLIENT_REGISTRATION}}The hosted service supports Claude, and Claude is the client
   it has been tested with. Claude Code and Cursor sign in through a local redirect that is not registered on the Entra
   app yet. So they can't sign in to {{DOMAIN}} today. Other MCP clients should work when you host {{PRODUCT}} yourself. This is not tested yet.{{/IF}}
3. **In Fabric:** you need access to the workspace you want to use. You also need a Fabric capacity. A trial is fine.

Every call runs with your own Fabric permissions. The step-by-step version is on [/start](/start). The server is
published in the official [MCP Registry](https://registry.modelcontextprotocol.io/v0.1/servers?search=com.krusgraph%2Fkrusgraph) as `com.krusgraph/krusgraph` (verified 26 October 2026).
Prefer your own machine and a SQL Server? The same engine runs locally over ODBC. See [/local](/local).
{{#IF CLIENT_REGISTRATION}}
````

### Other MCP clients

**Old**

````markdown
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
````

**New**

````markdown
VS Code, Cursor and other MCP clients that register themselves sign in at `{{CONNECT_URL}}`. They do not use the
address for Claude. {{PRODUCT}} identifies the client by the metadata document it publishes. A client without one gets a
strict registration. {{PRODUCT}} then shows its own approval page with the client's name, its domain and where the answer
goes. Only after that does it send you to Microsoft. Every call still runs with your own Fabric permissions. Nothing
changes for Claude.
{{CONNECT_TESTED}}.

- **VS Code** (GitHub Copilot agent mode): in `.vscode/mcp.json` or *MCP: Open User Configuration*, add
  `{"servers": {"{{PRODUCT_LOWER}}": {"type": "http", "url": "{{CONNECT_URL}}"}}}`, then *MCP: List Servers* → Start.
  The answer goes to a program on your computer, so the approval page comes back at each new sign-in.
- **Cursor:** in `~/.cursor/mcp.json`, add `{"mcpServers": {"{{PRODUCT_LOWER}}": {"url": "{{CONNECT_URL}}"}}}`, then sign in
  from Cursor's MCP settings. {{PRODUCT}} does not accept the `cursor://` address that some Cursor builds register. It
  accepts only https and local addresses. If the sign-in stops on the redirect address, register Cursor once with its local
  address, `curl -s {{CONNECT_URL_OAUTH}}/register -H 'Content-Type: application/json' -d '{"client_name": "Cursor", "redirect_uris": ["http://localhost:8787/callback"]}'`,
  and give Cursor the `client_id` from the answer as `"auth": {"CLIENT_ID": "…"}` next to the `url`.
- **Glama:** add `{{CONNECT_URL}}` in Glama's MCP connector. Glama identifies itself with its metadata document.
- **Claude Code:** `claude mcp add --transport http {{PRODUCT_LOWER}} {{CONNECT_URL}}` (not tried yet).

The approval page and Microsoft's sign-in open in your own browser. A web filter on a company network can stop them.
The browser then says the site "uses an unsupported protocol". Sign in from another network, or ask IT to allow
{{DOMAIN}}.
{{/IF}}
````

### What you can ask

**Old**

````markdown
One example per tool, in the order a first session usually goes (list, plan, look at rows if needed, check, create, describe, query):

- `list_workspaces` — *"Which Fabric workspaces can I see?"*
- `list_sources` — *"List the data sources in the demo workspace."*
- `list_tables` — *"Which tables are in demo_lh, schema shop?"*
- `plan_backend` — *"Plan a backend over demo_lh, schema shop."* — nothing is deployed; you get keys, relationships, the rule for each, ambiguous columns, suggested composite keys and an ER diagram. *"Treat order_id plus line_no as the key of order_items"* passes `keys`.
- `sample_rows` — *"Show me a few rows of orders."* — when a column's meaning is unclear before deciding on keys.
- `validate_plan` — *"Check the plan against the data."* — every key counted for uniqueness and NULLs, every relationship for orphans; the [example on /check](/check?example=sample) shows what the answer looks like.
- `create_backend` — *"Create it as shop_api."* — creates the API for GraphQL item, or updates it in place if the name exists (a dry run first).
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
````

**New**

````markdown
Here is one example per tool. They are in the order a first session usually goes (list, plan, look at rows if needed, check, create, describe, query).

- `list_workspaces`: *"Which Fabric workspaces can I see?"*
- `list_sources`: *"List the data sources in the demo workspace."*
- `list_tables`: *"Which tables are in demo_lh, schema shop?"*
- `plan_backend`: *"Plan a backend over demo_lh, schema shop."* Nothing is deployed. You get keys, relationships, the rule for each, ambiguous columns, suggested composite keys and an ER diagram. *"Treat order_id plus line_no as the key of order_items"* passes `keys`.
- `sample_rows`: *"Show me a few rows of orders."* Use it when a column's meaning is unclear before you decide on keys.
- `validate_plan`: *"Check the plan against the data."* Every key is counted for uniqueness and NULLs, and every relationship for orphans. The [example on /check](/check?example=sample) shows what the answer looks like.
- `create_backend`: *"Create it as shop_api."* This creates the API for GraphQL item. If the name exists, it updates that item in place. It does a dry run first.
- `describe_backend`: *"What can I query in shop_api?"* You get the types, fields and relationship names a query uses.
- `query_graphql`: *"Using shop_api, which customers ordered a trail bike in October?"* The query is read-only. Relationships nest.
- `rayfin_connector`: *"Generate Rayfin connector entities for it."* You get TypeScript entity classes for Fabric Apps.
- `ontology_draft`: *"Draft a Fabric IQ ontology from demo_lh."* You get entity types, keys and relationship types with their rules, ready to import.
- `compare_semantic_model`: *"Compare our Sales model with the plan for demo_lh."* You see what the model lacks, what a rule or the data contradicts, and the measures it could add.
- `gold_views_draft`: *"Draft gold views for demo_lh, schema shop."* You get one materialized lake view per fact table over the silver tables, with data quality rules.
- `export_item_definitions`: *"Export what you would create, in Fabric's Git format."* You get the item folders to commit to your own repository.
- `review_plan`: *"Keep this review as a file: accept ship_to_id as the ship-to address, leave audit_log without a key, and run the checks."* You get a file to commit next to your code. Next time, ask *"Read back krusgraph-review.demo-lh.shop.json and tell me what changed."*

**Five first questions on a lakehouse nobody has documented** (each is useful on its own):

1. *"Read demo_lh, schema shop, as a graph: which tables are facts, which are dimensions, and what are the subject areas?"* (`analyze_schema`)
2. *"Plan the keys and relationships for schema shop and tell me which rule made each one."* (`plan_backend`)
3. *"Check that plan against the data: are the keys unique and do the references hold?"* (`validate_plan`)
4. *"Which columns look like they should point at another table but are in no relationship?"* (`suggest_relationships`)
5. *"Write the data dictionary for schema shop."* (`data_dictionary`; `dbt_schema` when the team tests with dbt)
````

### First-time errors

**Old**

````markdown
What a new user meets first, what the tool answers (`kind`) and exactly what to do. Every such answer carries this
section's link in its `hint`.

| `kind` | What happened | What to do, in order |
| --- | --- | --- |
| `sign_in` | The connector has no valid sign-in for this request (expired, revoked, or never completed) | In Claude: **Customize → Connectors → Yours → Reconnect** on {{PRODUCT}}, and finish the Microsoft sign-in with your work account. If it loops, your organisation requires multi-factor authentication for new apps: complete it when asked. |
| `consent` | Your Microsoft Entra organisation has not consented to the app (Entra AADSTS65001), or the tool needs a permission the app has not been granted | Send your Entra admin the consent link on [/start](/start) (it opens Microsoft's own page); after they click **Accept**, disconnect and reconnect the connector. For `create_semantic_model`, `create_ontology`, `create_data_agent`, `create_silver_notebook` and `create_drift_monitor` the answer names the missing scope (such as `Item.ReadWrite.All` or `SemanticModel.ReadWrite.All`); that is a permission the operator adds to the app, see `docs/SCOPES.md`; the dry runs work meanwhile. |
| `no_access` | You can sign in, but this workspace or item is not shared with you (HTTP 403) | Ask the workspace owner for a role on the workspace: **Viewer** is enough for everything that reads and plans, **Contributor** for `create_backend`, `create_views` and the other creating tools. Then run the same request again; `list_workspaces` shows what you can see. |
| `capacity` | The workspace has no active Fabric capacity (paused, not assigned, or expired trial) | In Fabric: **Workspace settings → License info**, assign a capacity or resume the paused one; a trial capacity is enough. Lakehouse SQL endpoints answer again a minute after the capacity is up. |
| `schema_not_found` | The schema has no tables for this sign-in | A lakehouse without "Lakehouse schemas" has everything in `dbo`; one created with schemas has them by name (`list_tables` with another schema). Tables created minutes ago are not in the SQL analytics endpoint yet: open the endpoint in Fabric and refresh its metadata, then try again. |
| `sql_sign_in` | The SQL analytics endpoint refused the token | Reconnect the connector; if it persists, the account lacks access to the item itself (share the lakehouse or warehouse, not only the workspace). |

Everything else (`not_found`, `timeout`, `throttled`, `bad_input`, …) is explained in the answer itself; the format is
the same three fields.
````

**New**

````markdown
These are the errors a new user usually meets first. The table gives the `kind` the tool answers with and exactly
what to do. Every such answer carries a link to this section in its `hint`.

| `kind` | What happened | What to do, in order |
| --- | --- | --- |
| `sign_in` | The connector has no valid sign-in for this request (expired, revoked, or never completed) | In Claude: **Customize → Connectors → Yours → Reconnect** on {{PRODUCT}}, and finish the Microsoft sign-in with your work account. If it loops, your organisation requires multi-factor authentication for new apps. Complete it when asked. |
| `consent` | Your Microsoft Entra organisation has not consented to the app (Entra AADSTS65001), or the tool needs a permission the app has not been granted | Send your Entra admin the consent link on [/start](/start). It opens Microsoft's own page. After they click **Accept**, disconnect and reconnect the connector. For `create_semantic_model`, `create_ontology`, `create_data_agent`, `create_silver_notebook` and `create_drift_monitor` the answer names the missing scope (such as `Item.ReadWrite.All` or `SemanticModel.ReadWrite.All`). The operator adds that permission to the app, see `docs/SCOPES.md`. The dry runs work meanwhile. |
| `no_access` | You can sign in, but this workspace or item is not shared with you (HTTP 403) | Ask the workspace owner for a role on the workspace. **Viewer** is enough for everything that reads and plans. **Contributor** is needed for `create_backend`, `create_views` and the other creating tools. Then run the same request again. `list_workspaces` shows what you can see. |
| `capacity` | The workspace has no active Fabric capacity (paused, not assigned, or expired trial) | In Fabric, open **Workspace settings → License info** and assign a capacity or resume the paused one. A trial capacity is enough. Lakehouse SQL endpoints answer again a minute after the capacity is up. |
| `schema_not_found` | The schema has no tables for this sign-in | A lakehouse without "Lakehouse schemas" has everything in `dbo`. One created with schemas has them by name (`list_tables` with another schema). Tables created minutes ago are not in the SQL analytics endpoint yet. Open the endpoint in Fabric, refresh its metadata, then try again. |
| `sql_sign_in` | The SQL analytics endpoint refused the token | Reconnect the connector. If it persists, the account lacks access to the item itself. Share the lakehouse or warehouse, not only the workspace. |

Other kinds (`not_found`, `timeout`, `throttled`, `bad_input`, …) are explained in the answer itself. Their answers use
the same three fields.
````

