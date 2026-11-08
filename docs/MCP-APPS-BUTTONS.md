# Clickable next steps on the MCP Apps cards (round n169)

The founder, 8 November 2026: *"I want to click the mascots' suggestions and have everything created, without writing
text."* With `KRUSGRAPH_MCP_APPS=1` the cards in Claude ended with next steps the user had to type. Since n169 each card
ends with the Builder's or the Thinker's buttons, and a build is one click for its dry run and one click on Create.
Code: `fabric_backend/mcp_apps_build.py`; tests: `tests/test_n169_clickable_cards.py`. Since n172 the mascots say what
the buttons offer in plain English, never the call (`docs/MCP-APPS-POLISH.md`). Since n170 the cards also draw the
chat demo's pictures, and `domain_draft`'s data products carry their own build buttons: `docs/MCP-APPS-PICTURES.md`.

## What the specification allows, and what the cards use

Source: `modelcontextprotocol/ext-apps`, `specification/2026-01-26/apps.mdx` ("SEP-1865: MCP Apps", Status: Stable),
commit `19256f52cad5517ba8272581ed2e11d6a81273d5`, read again on 8 November 2026. Only the specification was read.

| What the card does | Where the specification defines it | Used for |
| --- | --- | --- |
| `tools/call` to the host, which forwards it to this server | "Standard MCP Messages" (Tools: `tools/call`, "Execute a tool on the MCP server"); the host announces it with `hostCapabilities.serverTools`, "Host can proxy tool calls to the MCP server" ("Host Capabilities") | every button: a dry run, Create, "Check against the rows", a schema choice |
| The host may ask the user first | "Transport Layer", point 8: the host "MAY decide to block some messages or subject them to further user approval" | the card says "it may ask you first" and waits; after 20 s it says what to ask in the chat instead |
| `ui/message` (role `user`, text content) | "MCP Apps Specific Messages", Requests (View → Host); "Host MAY request user consent" | the fallback when the host has no `serverTools` or answers `-32601`: the button's exact prompt goes into the chat as the user's message and Claude runs it |
| `ui/open-link` | same section; `hostCapabilities.openLinks` | "Open in Fabric" |
| Tool visibility | "Visibility": without `_meta.ui.visibility` a tool is callable by the model and by the app | nothing sets it: every tool a button names is one Claude can also call from the chat |

Nothing else is used: no `ui/update-model-context`, no network access from the card (no `_meta.ui.csp`, so the host's
restrictive default applies), no storage.

## The buttons, all built from the tool's own answer

The server adds `actions` to the answer (with the flag on only); the card draws only what that list holds, and only for
`validate_plan`, `plan_backend`, `create_semantic_model`, `create_ontology`, `create_backend` and `create_report`.

| After | Buttons |
| --- | --- |
| `plan_backend` (new build card) | Thinker: **Check against the rows** (`validate_plan`). Builder: **Build a semantic model**, **Create an ontology**, **Create an API for GraphQL** |
| `plan_backend` on a source with several schemas, no schema named | Thinker: one **Plan *schema* (*n* tables)** per schema, nothing else: the tool asks instead of picking one |
| `validate_plan` (its card) | the Builder's three builds (the check has just run); since n172 the n103 drafts are folded under **More** (still in the text answer) |
| `plan_backend` when a counting query could not run (n172) | Thinker: **Count again** (`plan_backend`, the same arguments), then as above |
| a build button | the dry run, drawn on the card, with **Create** under it |
| **Create** | the same tool, `dry_run: false`, the dry run's arguments unchanged |
| a semantic model created | **Open in Fabric**, **Create a report on it** (`create_report`, again a dry run first) |
| any other item created | **Open in Fabric** |

- **Dry run first, always.** A build button's arguments have `dry_run: true` (the card refuses one that does not).
  Only an answer with `dry_run: true` carries Create, and the card shows Create only when its arguments equal the dry
  run's with `dry_run: false` (compared key by key; since n172 a null argument or one equal to the tool's default
  counts as not given, because the MCP SDK fills in defaults: `docs/MCP-APPS-POLISH.md`, 9). There is no create without a visible dry run and a click on Create.
- **Names.** Each build gets a free name derived from the source: the schema, or the source's name when the schema is
  `dbo` (`shop_model`, then `shop_model_2`, `shop_model_3` ...), checked against every item name in the workspace, any
  type, case-insensitive. The button shows the name before the click. When the item names cannot be read, no build
  button is offered and the answer says why (`actions_note`); a dry run whose name an item already has gets no Create.
- **Open in Fabric** comes from the result's item id: a report opens at `/groups/{workspace}/reports/{id}`, a semantic
  model at `/groups/{workspace}/datasets/{id}/details` (the Power BI paths, which `app.fabric.microsoft.com` serves); an
  API for GraphQL and an ontology open the workspace's item list, where the item is.
- **Several schemas.** `plan_backend` without `schema` lists the schemas that hold base tables
  (`INFORMATION_SCHEMA.TABLES`, system schemas left out). With more than one it answers `choose_schema` and plans
  nothing; with one it plans it and says `schema_chosen`. On 8 November Claude planned the SAP tables when the founder
  meant shop; the tool no longer picks.
- **Text-only clients** (Lovable, VS Code, Cursor) get the same answer text; with the flag on it holds the same
  `actions`, each with its `say` sentence, which is the next step as text. With the flag off nothing changes.

## Which host path Claude takes

The card decides from Claude's `ui/initialize` answer: `tools/call` when it has `hostCapabilities.serverTools`,
`ui/message` otherwise. **Not tried in Claude yet** (this round cannot deploy). Tested on 8 November 2026 in Chromium
under a fake host, both paths (`tests/mcp_apps_build_browser.js`): with `serverTools` a click sent `tools/call` with the
dry run, Create sent the same arguments with `dry_run: false`, Open in Fabric sent `ui/open-link`; without it the click
sent the button's prompt with `ui/message`. Write the path Claude takes here after the first try.

## What the founder clicks in Claude to test it

After a deploy with `"mcp_apps": true` (`KRUSGRAPH_MCP_APPS=1`):

1. Ask: *"Plan the demo lakehouse."* with no schema. Expect the Thinker's schema buttons (one per schema); click **Plan
   shop**.
2. On the plan card click **Check against the rows**, then on the plan card **Build a semantic model (shop_model …)**.
   Claude may ask to allow the call; allow it. The dry run appears under the button.
3. Read the dry run, click **Create**. Then **Open in Fabric**, and **Create a report on it** → **Create**.
4. Note which happened on the first click: the dry run appeared on the card (`tools/call`), or the prompt appeared in the
   chat as your message (`ui/message`). Write it in "Which host path Claude takes" above.
