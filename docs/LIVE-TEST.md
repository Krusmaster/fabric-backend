# Live test checklist

For the maintainer, after `bash deploy/krusgraph.sh --update`, against the demo workspace `demo`, the lakehouse
`demo_lh` and the schema `shop` (the synthetic data of `fabric_backend/seed.py`), from Claude with the connector
signed in. The workspace id is not written here; the protocol of a run stays outside the repository. Fill in the
**Result** (✓, or what came instead) and the **Date**; a row is passed when the answer says what **Expected** says.
"27 Oct" marks the rows that passed on 27 October 2026 (from Claude through the hosted build `src-df29c45febaec4b0`,
main 5adace8: 30 tools read-only, as drafts or as dry runs, then one creating call, `create_backend` updating `shop_api`
in place, with the maintainer's approval); "26 Oct" the 14 steps of the day before. The rows filled in with
2 November 2026 ran through the hosted build `src-69aa8afa445e6c97` (section 6, *2 November 2026: round n81's path*),
except row 6's result, which comes from the second run that day, after round n87's deployment (section 6, *2 November
2026: after round n87*).
The status words follow from this file through `fabric_backend/tool_status.py` (section 5).

## 0. The service answers

| Check | Command | Expected | Result | Date |
| --- | --- | --- | --- | --- |
| Uptime endpoint | `curl -s https://krusgraph.com/health` | `{"status":"ok"}` | | |
| The new build is live | `curl -s https://krusgraph.com/healthz` | `"ok": true`, `"auth": "entra"`, and `"build"` equal to the tag `--update` printed | | |
| Sign-in challenge | `curl -s -i -X POST https://krusgraph.com/mcp` | `401` with a `WWW-Authenticate` header naming `resource_metadata` | | |
| OAuth metadata | `curl -s https://krusgraph.com/.well-known/oauth-protected-resource` | `authorization_servers` with `login.microsoftonline.com`, `scopes_supported` with `…/user_impersonation` | | |

## 1. One row per tool

| # | Tool | Question in Claude | Expected | Earlier | Result | Date |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `list_workspaces` | *"Which Fabric workspaces can I see?"* | `demo` among them, with its capacity | 26, 27 Oct | | |
| 2 | `list_sources` | *"List the data sources in the demo workspace."* | `demo_lh` (Lakehouse) and the API `shop_api` | 26, 27 Oct | | |
| 3 | `list_tables` | *"Which tables and columns are in demo_lh, schema shop?"* | 7 tables: customers, categories, products, addresses, orders, order_items, audit_log, with types | 27 Oct | | |
| 4 | `plan_backend` | *"Plan a backend over demo_lh, schema shop."* | 7 tables, 6 with keys, 7 relationships (6 R1, and `orders.ship_to_id → addresses.address_id` by R5, counted in the rows); `audit_log` without a key; `order_items` keyed `order_id + line_no` (K5) | 26, 27 Oct (6 relationships, before R5) | | |
| 5 | `sample_rows` | *"Show me five rows of customers in demo_lh, schema shop."* | 5 rows; `name` shows `***` with a `personal_data` notice (rule P1) and the parameter `show_personal_data`; the lakehouse's sensitivity label id if it has one | 26 Oct (before masking), 27 Oct (masked) | | |
| 6 | `validate_plan` | *"Check the plan against the data."* | 6 of 6 keys unique, 7 of 7 relationships hold without orphans (R5's `ship_to_id` among them) | 26, 27 Oct, 2 Nov with build `src-69aa8afa445e6c97` (6 of 6 relationships, before R5 reached validate_plan) | ✓ 6 of 6 keys unique, 7 of 7 relationships without orphans; on schema `dbo` 17 of 17 keys and 32 of 34 relationships | 2 November 2026 |
| 7 | `create_backend` | *"Update shop_api from demo_lh, schema shop, and keep orders.ship_to_id → addresses.address_id. Dry run first, then update."* | dry run (the default since n111): `would: update`, the changes and the checks passed; with `dry_run=false`: `mode: updated`, the endpoint; nothing dropped (see section 3) | 27 Oct (`Succeeded`, `updated`, after `would_remove`; see sections 2 and 3) | | |
| 8 | `describe_backend` | *"What can I query in shop_api?"* | the types of the seven tables with fields and relationship names | 26, 27 Oct | | |
| 9 | `query_graphql` | *"Using shop_api, list five orders with their customer."* | 5 orders, each with its customer object; a mutation asked for is refused | 26, 27 Oct | | |
| 10 | `query_graphql` with `question` | *"Using shop_api, how many orders per customer? Run it."* | the suggested query beside the result, grouped by `customer_id` | 27 Oct (in Swedish; the counts add up to 60) | | |
| 11 | `rayfin_connector` | *"Generate Rayfin connector entities for demo_lh, schema shop."* | 9 files: 7 entity classes, `schema.ts`, `README.generated.md` | 27 Oct | | |
| 12 | `ontology_draft` | *"Draft a Fabric IQ ontology from demo_lh, schema shop."* | 7 entity types (5 with a key; `order_items` and `audit_log` noted), 6 relationship types, a Turtle file | 27 Oct | | |
| 13 | `semantic_model_draft` | *"Draft a Power BI semantic model for demo_lh, schema shop."* | 7 Direct Lake tables plus `Calendar` (marked as date table), 6 relationships plus `orders.order_date → Calendar.Date`, 4 suggested measures each with its reason, `ship_to_id` not summed | 26 Oct (before measures), 27 Oct | | |
| 14 | `join_path` | *"How do customers and categories connect?"* | 4 hops, each R1, and the T-SQL | 26, 27 Oct | | |
| 15 | `data_dictionary` | *"Write the data dictionary for schema shop, with the checks."* Then *"Only for orders."* | Markdown with the 7 tables and the counts of row 6; with `tables=["orders"]`, `orders` is a fact table and the subject area lists all seven tables | 26, 27 Oct (with `tables`: see section 2) | | |
| 16 | `dbt_schema` | *"Give me the dbt sources file for schema shop."* | `models/sources/shop.yml` with `unique`, `not_null` and `relationships` tests | 26, 27 Oct | | |
| 17 | `plan_drift` | *"What would change in shop_api if I re-ran create_backend?"* | the `ship_to_id → addresses` relationship the plan does not infer, with its `confirmed` entry | 26, 27 Oct | | |
| 18 | `create_semantic_model` | *"Create the semantic model shop_model from demo_lh, schema shop. Dry run first, then create."* | dry run: the parts and the REST call; create: `kind: consent` naming `SemanticModel.ReadWrite.All` (or `Item.ReadWrite.All`) | 27 Oct (dry run); 29 Oct created `shop_model_live` (section 6) | | |
| 19 | `create_views` | *"Which views would create_views make in demo_lh, schema shop? Dry run."* | `vw_order_items`, `vw_orders`; with `ship_to_id` confirmed also a view named after the relationship's field (`vw_orders_ship_to` with the entry of section 3; 27 October showed `vw_orders_address`, the field name Claude passed) | 26, 27 Oct (dry run) | | |
| 20 | `create_views` (create) | *"Create those views."* (only if a test schema `krusgraph` on `demo_lh` is wanted) | schema `krusgraph` and the views created; `list_tables` with schema `krusgraph` lists them | — | | |
| 21 | `create_data_agent` | *"Draft a data agent over demo_lh, schema shop. Dry run."* | instructions, the source with the plan's tables, 10 example questions with T-SQL; no example selects or groups by `customers.name` (`customer_id` instead) and `personal_data.left_out` names it, unless `show_personal_data=true`; asked to create: `kind: consent` | 27 Oct (dry run; see section 2) | | |
| 22 | `create_ontology` | *"Create the ontology shop_ontology. Dry run first."* | dry run: the parts and the call; create: the item `shop_ontology`, or `kind: feature_disabled` quoting `FeatureNotAvailable` while "Users can create Ontology (preview) items" is off in the tenant (section 6) | 28 Oct (dry run; created after the tenant setting: section 6) | with `dry_run=false`: created `shop_ontology_n81` (status Succeeded, mode created; the id from the operation's result), then updated it (mode updated); a dry run that day is not recorded | 2 November 2026 |
| 23 | `app_starter` | *"Give me the starter pack for an app on shop_api."* | a Lovable prompt, five queries, the Supabase edge function | 26 Oct (prompt and queries), 27 Oct | | |
| 24 | `app_readiness` | *"What does shop_api still need before an app can use it?"* | introspection on or off (one probe), the types without a key, permissions reported as unknown with the portal path | 27 Oct | | |
| 25 | `analyze_schema` | *"Read demo_lh, schema shop, as a graph."* | 3 fact tables (orders, order_items, audit_log), 4 dimensions, 7 relationships of which 6 are active at once and 1 inactive, 1 cycle (orders → addresses → customers ← orders, through R5's `ship_to_id`) | 26, 27 Oct (6 relationships, no cycles, before R5) | | |
| 26 | `lineage` | *"What builds on the tables in demo_lh, schema shop?"* | `shop_api` on the seven tables; the views on the SQL endpoint (`krusgraph.vw_order_items` is there already); an item that could not be read is listed with Fabric's `error`, its `reason` and a `hint` | 27 Oct (`shop_api` skipped: see section 2) | 7 tables and 7 objects, none skipped | 2 November 2026 |
| 27 | `suggest_relationships` | *"Which columns look like references but are in no relationship? Check the best against the data."* | `orders.ship_to_id → addresses.address_id` first, holding for every value | 26, 27 Oct | | |
| 28 | `silver_notebook_draft` | *"Draft the silver notebook for demo_lh, schema shop."* | steps for 7 tables in schema `silver`, quarantine `krusgraph_quarantine`, `customers.name` and `addresses.city` masked in quarantine | 27 Oct | | |
| 29 | `create_silver_notebook` | *"Create it as silver_shop. Dry run first, then create."* | dry run: the notebook and the call; create: `kind: consent` naming `Notebook.ReadWrite.All` (or `Item.ReadWrite.All`) | — | | |
| 30 | `drift_monitor_draft` | *"Draft a nightly drift monitor for demo_lh, schema shop."* | a notebook, a pipeline `<name>_nightly` and a daily schedule at 02:00; the `%pip` cell installs `@v<version>` (the server's version), and the note says `library_ref="main"` follows main | 27 Oct (see section 2) | | |
| 31 | `create_drift_monitor` | *"Create it as drift_shop. Dry run."* | the items and the three REST calls; asked to create: `kind: consent` | — | | |
| 32 | `answer_query_draft` | *"How many orders per customer in demo_lh, schema shop? Only the query."* | T-SQL grouped by `customer_id`, with `customers.name` left out by the privacy rule; with `api=shop_api` also the GraphQL | 27 Oct | | |
| 33 | `compare_semantic_model` | *"Draft the semantic model for demo_lh, schema shop, then compare it with the plan using its files."* | through `tmdl`: the 6 relationships agree, nothing missing or contradicted, `Calendar` outside the plan | — | | |
| 34 | `compare_semantic_model` (by name) | *"Compare the semantic model <a model in demo> with the plan for demo_lh, schema shop."* | without the permission: `kind: consent` naming `SemanticModel.ReadWrite.All (or Item.ReadWrite.All)` and the `tmdl` way round | 27 Oct (`not_found`: no model in `demo`) | | |
| 35 | `gold_views_draft` | *"Draft the gold views for demo_lh, schema shop."* | `gold.audit_log`, `gold.order_items`, `gold.orders`, each with its constraints and their rules; `customers.name` left out | 27 Oct | | |
| 36 | `create_gold_views` | *"Create the gold notebook gold_shop. Dry run first."* | dry run: the notebook and the call; create: `kind: consent` naming `Notebook.ReadWrite.All` | — | | |
| 37 | `export_item_definitions` | *"Export what you would create for demo_lh, schema shop, in Fabric's Git format."* | folders `demo_lh_api.GraphQLApi`, `demo_lh_model.SemanticModel`, `silver_shop.Notebook`, `drift_monitor_shop.Notebook`, `drift_monitor_shop_nightly.DataPipeline`, `gold_shop.Notebook`, `krusgraph-sql/`; the largest file named under `omitted` | 27 Oct | | |
| 38 | `review_plan` | *"Keep this review as a file: confirm orders.ship_to_id → addresses.address_id as the ship-to address, reject audit_log → customers as log only, and run the checks."* Save the file; then add a column to `orders` in the lakehouse and ask *"Read back the review file and tell me what changed."* | first answer: 6 keys and 7 relationships, the ship-to relationship `accepted` with its reason, `audit_log` as an open question, every check `passed` with the time, no row values in the file; second answer: the new column under `since_previous`, the checks on `orders` and its relationships `stale`, the others `passed` with their first date, the decisions still there | 27 Oct (first answer only) | | |
| 39 | `create_report` | *"Create the report shop_report_visuals on shop_model_live. Dry run first, then create."* Then *"Create the report shop_report_blank on shop_model_live with an empty page."* | dry run: the call with a `definition` (PBIR parts) and `visuals`: cards per count measure, a clustered column chart by `Calendar` Month, a clustered bar chart (for shop: Total quantity by `categories.name`) and a table sorted by a measure, with `left_out` naming any header amount; create: status Succeeded, mode created, the page shows those visuals bound to the model; with `empty_page=true`: the call with `creationPayload.semanticModelReference`, one blank page; a second call with the same name answers `kind: already_exists` | 30 Oct, before the page with visuals (dry run, then created `shop_report_live` with one blank page; `shop_report` from Lovable: section 6) | | |

## 2. Fixed after the 27 October run, unit-tested only

The 27 October run found these; each is fixed and covered by unit tests, and none has run live since (the
`create_backend` row: the live update went through with `reverse_name`, the fix is that it is no longer needed). The three
fixes after the 26 October run (`summarizeBy: none` on `ship_to_id` in 77c9cbc, the ranking of `suggest_relationships`
in 7791941, the three views of `create_views` in 961f8b6) passed on 27 October.

| What the run showed | Fixed in | Question in Claude | Expected now | Result | Date |
| --- | --- | --- | --- | --- | --- |
| `lineage` skipped `shop_api` with `reason: fabric_error` while `describe_backend` read the same definition | 2be055c | *"What builds on the tables in demo_lh, schema shop?"* | `shop_api` on the seven tables; if a read still fails, the skipped entry carries Fabric's `error` and a `hint` (it is read twice first) | | |
| `create_data_agent`'s examples grouped on `customers.name` (P1) | 470fc98 | *"Draft a data agent over demo_lh, schema shop. Dry run."* | the examples group customers by `customer_id`; `personal_data.left_out` names `customers.name` and `addresses.city` | | |
| `data_dictionary` with `tables=["orders"]` called `orders` isolated next to two of its relationships | 4b05704 | *"Write the data dictionary for orders in demo_lh, schema shop."* | `orders` a fact table, the subject area with all seven tables, the whole schema's counts and a line saying what is shown | | |
| `create_backend shop_api` with the ship-to relationship confirmed (`field_name: "address"`) stopped with `would_remove`: the plan named the reverse field `orders_as_ship_to`, the API has `orders`, and `keep_with_confirmed` was empty | 2aeb238 | *"Update shop_api from demo_lh, schema shop, and keep orders.ship_to_id → addresses.address_id."* | `Succeeded`, `updated`, with `names_kept_from_api` naming `addresses.orders`; the API's fields unchanged; `plan_drift` first says no drift | | |
| `drift_monitor_draft` installed the library from `main` by default | cfee096 | *"Draft a nightly drift monitor for demo_lh, schema shop."* | the `%pip` cell installs `@v<version>`; the tag must exist on GitHub (docs/PUBLISHING.md) | | |

The first pipeline run, 7 November 2026 (`create_pipeline` of n120 created `pipeline_shop` in `demo`, default lakehouse
`demo_lh`; run in Fabric Runtime 2.0: Spark 4.1, Delta 4.2, Python 3.13):
`silver_shop` succeeded (1m59s), `gold_shop` succeeded (1m36s), `pipeline_shop_check` failed with `ImportError: cannot
import name 'pipeline' from 'fabric_backend'`: its `%pip` installed the published release, which is older than `main` and
has no `pipeline` module. Fixed in n140: the check notebook is self-contained (plain PySpark and Python, no `%pip`, no
import of the library), unit-tested on SQLite and on a local Spark.

| What the run showed | Fixed in | Question in Claude | Expected now | Result | Date |
| --- | --- | --- | --- | --- | --- |
| `pipeline_shop_check` failed importing `fabric_backend.pipeline` | n140 | *"Create the pipeline pipeline_shop for demo_lh, schema shop."*, then run `pipeline_shop` in Fabric | all three activities succeed; the check's output starts with `Keys in silver: 6 of 6` and ends with `The check holds.` | ✓ run 9de8bc49: all three activities succeeded (the check's output is not recorded here) | 7 November 2026 |

Still open after n140: the drift monitor's notebook (`drift_monitor_draft`, `create_drift_monitor`) installs the library
with `%pip` from GitHub at the tag of the server's version and imports it, so a run needs internet access and the tag, and
runs that release's inference, not `main`'s. It cannot be inlined the way the check was (it runs the whole inference,
lineage and `plan_drift`); left for a round of its own.

Seen, not changed: `demo_lh` already holds the view `krusgraph.vw_order_items`, so `create_views` has created a view
there at some point, but no protocol of that run exists. Creating with `create_views` stays Experimental until row 20
is run and written down.

## 3. Before the next `create_backend shop_api`

`shop_api` carries `orders.ship_to_id → addresses.address_id` as the fields `orders.address` and `addresses.orders`.
Since round n87 every tool plans with rule R5, which finds this relationship by counting the rows, so the plan has it
and an update keeps the API's names for it. Should R5 not count it (the 20 counting queries of a call used up), the
next `create_backend` with the name `shop_api` must pass the relationship, or it is dropped (the tool then stops with `kind: would_remove`, nothing is written, and `keep_with_confirmed` gives the
entry with both names). Since the fix of finding 7 the entry needs no field names: an update keeps the names the API
has for the same relationship, and the answer lists them under `names_kept_from_api`.

```json
"confirmed": [{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}]
```

In Claude: *"Update shop_api from demo_lh, schema shop, and keep orders.ship_to_id → addresses.address_id. Dry run first,
then update."* (row 7; since round n111 the update needs `dry_run=false`).
On 27 October, before that fix, the update stopped at `would_remove` until the entry also carried
`"field_name": "address", "reverse_name": "orders"`; with those it answered `Succeeded`, `updated`. Pass `field_name` or
`reverse_name` only to rename a field on purpose; a rename removes the field an app queries today, so the update then
stops at `would_remove` until `allow_removals=true`.

## 4. Clients

Prepared, not switched on: `bash deploy/krusgraph.sh --client-redirects` prints the commands, and
`docs/OPERATIONS.md` section 5 has the sources. After registering the addresses:

| Client | How | Expected | Result | Date |
| --- | --- | --- | --- | --- |
| Claude Code | `claude mcp add --transport http --client-id <APP_ID> --callback-port 8080 krusgraph https://krusgraph.com/mcp`, then `claude mcp login krusgraph`; ask *"Which Fabric workspaces can I see?"* | Microsoft sign-in in the browser, then `demo` in the answer | | |
| VS Code (GitHub Copilot agent mode) | `mcp.json` with `"oauth": {"clientId": "<APP_ID>"}`; *MCP: List Servers* → Start; ask the same in agent mode | the same | | |
| Cursor | `~/.cursor/mcp.json` with `"auth": {"CLIENT_ID": "<APP_ID>"}`; sign in from the MCP settings; note the `redirect_uri` in the address that opens | the same, and a `redirect_uri` that is registered | | |

Through client registration instead (`docs/OPERATIONS.md` section 6, after `bash deploy/krusgraph.sh
--client-registration`), all at `https://krusgraph.com/mcp/connect` with the test account:

| Client | How | Expected | Result | Date |
| --- | --- | --- | --- | --- |
| Claude (connector) | sign in and ask *"Which Fabric workspaces can I see?"* after switching on | exactly as before: Microsoft sign-in, no Krusgraph page, `demo` | | |
| VS Code (GitHub Copilot agent mode) | `mcp.json` with only `"url": "https://krusgraph.com/mcp/connect"`; *MCP: List Servers* → Start | Krusgraph's page names Visual Studio Code, `vscode.dev`, a program on this computer; Allow; Microsoft sign-in; `demo` | works (the maintainer) | 27 October 2026 |
| Cursor | register once with `http://localhost:8787/callback` (section 6), `"auth": {"CLIENT_ID": "<kgdcr.…>"}` | the page says the name is not verified and shows `http://localhost:8787/callback`; `demo` | works (the maintainer) | 27 October 2026 |
| Glama | add `https://krusgraph.com/mcp/connect` in Glama's connector | the page shows `glama.ai` as where the answer goes; `demo` in Glama | works: Glama identified itself with its client ID metadata document; its connection test "Healthy" at 17:59 | 27 October 2026 |
| VS Code: the *Add to VS Code* button | the button on the site's Connect menu (*Other clients*) | VS Code opens and offers to add the server | works in VS Code (Gustav) | 2 November 2026 |
| Cursor: the *Add to Cursor* button | the button on the site's Connect menu (*Other clients*) | Cursor opens its install dialog for the server | works in Cursor (Gustav) | 2 November 2026 |
| Lovable (custom MCP) | add `https://krusgraph.com/mcp/connect` as a custom MCP connector in Lovable (OAuth), from a phone | Microsoft sign-in through Krusgraph's OAuth (dynamic client registration), then the tools in Lovable's chat | works: signed in with Entra and ran `plan_backend`, `validate_plan`, `create_backend`, `create_semantic_model` and `create_report` against `demo` (section 6) | 30 October 2026 |

28 October 2026: VS Code, Cursor and Glama work through `/mcp/connect` (the rows above); they stay *Experimental* for
now in `fabric_backend/tool_status.CLIENTS`, which the hub, the docs' overview and the start page follow. 30 October 2026:
Lovable too, as a custom MCP connector; it stays *Experimental* as well, with its own row in `CLIENTS` next to the row
for the GraphQL API it reads. 2 November 2026: Gustav verified that the *Add to VS Code* and *Add to Cursor* buttons on the
site's Connect menu work in their clients (the two rows above); that is all the rows say, and `tool_status.CLIENTS`
carries the same sentence in both clients' notes. Later on 2 November 2026 Gustav decided that VS Code and Cursor are
no longer marked *Experimental* (he has verified them), and that Lovable is not either, since its flow ran live on
30 October 2026 (`docs/LOVABLE-END-TO-END.md`): the three are **Tested end to end** in `tool_status.CLIENTS` (both of
Lovable's rows), with "status set by Gustav on 2 November 2026" in their notes (`CLIENTS_DECIDED`), and the Connect
menu no longer puts "Experimental:" before them. Glama and Claude Code are unchanged (*Experimental*); section 6 has
the decision.
| Claude Code (optional) | `claude mcp add --transport http krusgraph-connect https://krusgraph.com/mcp/connect` | the page names Claude Code from `claude.ai`; `demo` | | |
| Deny | choose Deny on the page once | the client reports access denied | | |

What the run of 27 October 2026 found on the way, each fixed or written down: the approval form was refused with
`Origin: null` because the page said `Referrer-Policy: no-referrer` (fixed, 295b436); the sign-in table refused every
write (the expiry as an Edm.Int64 number, no `x-ms-date`; fixed, 15bd7fd); the container app's identity had no role on
the table because the maintainer's account is Contributor, which cannot assign roles (assigned by the subscription's
Owner); and a company laptop's web filter stopped the sign-in page in the browser (`ERR_SSL_VERSION_OR_CIPHER_MISMATCH`)
while the server answered normally (a private computer worked).

## 5. From the filled-in checklist to the status words

1. A tool whose rows in section 1 all passed is **Tested end to end**; a draft **Tested end to end (a draft; creates
   nothing)**; when only its dry run ran, *tested end to end as a dry run* after its word, while creating keeps its
   status. A creating tool that answered `consent` stays **Available when enabled by the operator** until it has
   created something live. A row that did not pass keeps the tool where it is, and the difference goes to an issue.
2. In `fabric_backend/tool_status.py`: `LIVE_RUN_DATE`, `LIVE_RUN_BUILD`, `LIVE_RUN` (the tools in run order),
   `LIVE_RUN_PARTLY`, and each tool's `dry_run_only` and `note`. The docs' Status column and *Test status*, `llms.txt`,
   the use-case tasks and outputs, the home page's test line, the server's instructions and the notes in the tools'
   own answers render from there.
3. By hand: the README's *Status* section and `deploy/SUBMISSION.md` row 5.
4. In `tests/test_site.py`, `test_docs_give_every_tool_a_status_in_the_shared_words`: the set `tested`.
5. A row in section 2 that passed: drop "unit-tested only" for that fix in the README's *Status* section.
6. A client in section 4 that worked: name it where the site says the hosted service supports Claude (/docs *Connect*,
   /start, `llms.txt`), with the date.
7. `python -m pytest -q`, push, and `bash deploy/krusgraph.sh --update`.

## 6. Test history behind the status words

What the site and the docs now give only as a status word, with the run behind it.

- **`create_ontology`, 28 October 2026.** Run live against the demo workspace with `dry_run=false`, after the Entra app
  got `Item.ReadWrite.All`. The dry run ran without errors. The first create was stopped by HTTP 403: first read as
  `kind: consent`, then, once round n33 quoted Fabric's own answer, as `errorCode` `FeatureNotAvailable`: the ontology
  (preview) was turned off in that tenant's settings. After n36, Gustav turned on "Users can create Ontology (preview)
  items" in Kruse Consulting's tenant settings, and the hosted connector ran it again with `dry_run=false` (workspace
  `demo`, lakehouse `demo_lh`, schema `shop`, with the confirmed relationship `orders.ship_to_id → addresses.address_id`).
  Fabric answered status Succeeded, mode created: the item `shop_ontology` with 7 entity types (5 with a key), 7
  relationship types and 0 skipped relationships. Notes: `AuditLog` has no key; `OrderItems` has a composite key and was
  left keyless. On 29 October 2026 Gustav reviewed the item in the Fabric portal; his verdict: "ontology ser väldigt bra
  ut". No single part (entity types, keys, relationships, data bindings) was recorded as checked on its own, and no
  ontology agent or question has used it. The site says "created live; reviewed in Fabric" next to the offer; the tool
  table in the docs gives the long form from `fabric_backend/tool_status.py`.

- **`create_semantic_model`, 29 October 2026.** Run live through the hosted connector with `dry_run=false` (workspace
  `demo`, lakehouse `demo_lh`, schema `shop`, name `shop_model_live`, with the confirmed relationship
  `orders.ship_to_id → addresses.address_id`). Fabric answered status Succeeded, mode created: 7 tables, 6 active and 1
  inactive relationship (`addresses.customer_id → customers`, which would close a cycle), Direct Lake, 4 measures and
  the date table `Calendar`. On 29 October 2026 Gustav refreshed (framed) both `shop_model_live` and `shop_model` in the Fabric portal, and the refresh succeeded. Afterwards he opened `shop_model_live` in the model view and confirmed that the relationships look right (7 tables plus `Calendar`, 6 active relationships, the inactive `addresses.customer_id → customers` dashed, 4 measures). No report or query has used the model. The site says "created live; reviewed in Fabric" next to the offer, as for `create_ontology`.

### 30 October 2026: `create_report`, Lovable as an MCP client, two updates in place

Everything below ran in the workspace `demo` (lakehouse `demo_lh`, schema `shop`, synthetic data), through the hosted
connector or through Lovable as an MCP client.

- **`create_report`.** The coordinator (Claude through the hosted connector) ran it with `dry_run=true` and then
  `dry_run=false` against `shop_model_live`. Fabric answered status Succeeded, mode created: the report
  `shop_report_live` (id `792145bf-8f5a-4ee2-86e7-20a1831d04f3`), one blank page bound to the model. Later the same day
  Lovable, as an MCP client, created `shop_report` on `shop_model`. Gustav updated `shop_model`, opened `shop_report` in
  the Fabric portal, added a visualisation (Calendar) and saw data. Status: *Experimental; created live on 30 October
  2026 (shop_report_live, shop_report), opened and reviewed in the Fabric portal by Gustav the same day*; next to the
  offer, "created live; reviewed in Fabric", as for `create_ontology` and `create_semantic_model`.
- **`create_backend`.** `shop_api` was updated in place from Lovable on 30 October 2026, and a Lovable app reads the
  API live: orders, customers and the ship-to address through `ship_to_id → addresses`. Creating a new API has still
  not run live. The long form now adds "consumed live by a Lovable app on 30 October 2026".
- **`create_semantic_model`.** `shop_model` was updated in place from Lovable on 30 October 2026 (after
  `shop_model_live` was created on 29 October). The same day Power BI Desktop opened the shop project from `/check`;
  the SAP project stopped on a TMDL error (a `relationships.tmdl` holding only comments), fixed by round n67 in
  181452e and not opened in Power BI Desktop since.
- **Lovable as a client.** Lovable connected to `https://krusgraph.com/mcp/connect` with an Entra sign-in through
  Krusgraph's OAuth (dynamic client registration), from a phone, and ran `plan_backend`, `validate_plan`,
  `create_backend`, `create_semantic_model` and `create_report`. It has a row of its own in
  `fabric_backend/tool_status.CLIENTS` ("via MCP (/mcp/connect)", *Experimental* at the time, works since 30 October
  2026; **Tested end to end** since Gustav's decision of 2 November 2026, below) next to the row for the GraphQL API it
  reads through its own Fabric connector. The Entra app is a verified publisher since
  the same day (`docs/SCOPES.md`).

### 2 November 2026: three clients without Experimental, and Ontology Playground

- **VS Code, Cursor and Lovable.** Gustav decided on 2 November 2026 that VS Code and Cursor are not to be marked
  *Experimental*: he has verified them (their sign-in and tool runs at `/mcp/connect` on 27 October 2026, section 4,
  and the *Add to VS Code* and *Add to Cursor* buttons the same morning). Lovable loses the word too, because its flow
  ran live on 30 October 2026 (`docs/LOVABLE-END-TO-END.md`, and the section above): as an MCP client, and with a
  Lovable app reading the API for GraphQL that create_backend updated. In `fabric_backend/tool_status.CLIENTS` the three are **Tested end to end** with
  "status set by Gustav on 2 November 2026" (`CLIENTS_DECIDED`); /docs, /start, /lovable, the home page, the Connect
  menu and the llms files render from there. Claude Code (not tried) and Glama stay *Experimental*. On the same day
  Glama's connection test went from Healthy to "Missing credentials" around 07:16 UTC; that is investigated in
  `docs/REFRESH-ROTATION.md` and does not change Glama's word.
- **Ontology Playground.** On 2 November 2026 Gustav opened the RDF/XML file from `/check` (the download "ontology for
  Microsoft's Ontology Playground", `ontology.ontology_rdfxml`) in Microsoft's Ontology Playground, with a good result
  (source: Gustav). That is what was tried: a file import in the Playground, not a Fabric item. The file stays
  **Draft** (`tool_status.ONTOLOGY_RDFXML`). Since n95 the download on `/check` no longer says it; the record is here
  and in `tool_status.ONTOLOGY_RDFXML_TRIED`: "Gustav tried a file from /check there on 2 November 2026, with a good
  result". Nothing more is claimed: no partnership with Microsoft and no relation to
  the Playground's project beyond the code taken from it under its licence (`docs/ECOSYSTEM-WATCHLIST.md`).

### 2 November 2026: round n81's path against Fabric

On 2 November 2026 the hosted build `src-69aa8afa445e6c97` ran three tools against the demo workspace `demo`, the
lakehouse `demo_lh` and the schema `shop` (synthetic data; rows 6, 22 and 26 of section 1):

- **`validate_plan`**: 6 of 6 keys unique and 6 of 6 relationships without orphans.
- **`lineage`**: 7 tables and 7 objects, none skipped.
- **`create_ontology`** with `dry_run=false`: created `shop_ontology_n81`, status Succeeded, mode created, with the
  item's id taken from the operation's result; a second call updated it, mode updated. The id is not written here.

That is round n81's way of waiting for a long-running Fabric operation (`deploy.py`: the 202, polling the operation,
the created item's id from `GET /operations/{id}/result`) run against real Fabric, without throttling. `Retry-After`
and the answer 429 have been tried only against fake answers in the unit tests, not against Fabric.

### 2 November 2026: after round n87

Later on 2 November 2026, after round n87 was deployed (every tool plans with R5), against the same workspace and
lakehouse (synthetic data):

- **`validate_plan`** on schema `shop`: 6 of 6 keys unique and 7 of 7 relationships without orphans.
- **`validate_plan`** on schema `dbo`: 17 of 17 keys unique and 32 of 34 relationships without orphans.
- **`join_path`** from `orders` to `addresses`: the direct step through `ship_to_id`, rule R5.

The same run found that a negation such as *"customers who have not placed any orders"* still gave a plain join and
that `amount_levels` said "about 1 times too large" where every header has one line; both are fixed in round n88 and
covered by unit tests only, not yet run live.

## Databricks

For a trial workspace of your own (Databricks Free Edition or a trial account), from the **local** stdio server with
`KRUSGRAPH_PLATFORM=databricks` (set-up in [DATABRICKS.md](DATABRICKS.md)); the hosted server reads Fabric only. Every
row is Draft only until it has passed here. Synthetic data only: the seed below, no customer data.

**Preparation, in a Python notebook of the workspace** (serverless compute; the catalog `workspace` is Free Edition's
default per community posts, use the one your workspace has):

```python
%pip install git+https://github.com/Krusmaster/fabric-backend
from fabric_backend.seed import SCHEMAS, rows
spark.sql("CREATE SCHEMA IF NOT EXISTS workspace.shop")
for name, data in rows().items():
    spark.createDataFrame(data, SCHEMAS[name]).write.mode("overwrite").saveAsTable(f"workspace.shop.{name}")
```

Rights for the signed-in user: CAN USE on the SQL warehouse; USE CATALOG, USE SCHEMA, SELECT; CREATE SCHEMA on the
catalog and ownership of the `shop` tables (you created them) for rows D9–D12. For D15: read access to
`system.access`.

| # | Tool | Question in Claude | Expected | Result | Date |
| --- | --- | --- | --- | --- | --- |
| D1 | `list_tables` | *"Which tables and columns are in schema shop?"* | the 7 tables, types as `int`, `string`, `date`, `double`, `timestamp` | | |
| D2 | `plan_backend` | *"Plan schema shop."* | 7 tables, 6 with keys, 6 relationships; `order_items` keyed `order_id + line_no` (K5); the same as row 4 on Fabric | | |
| D3 | `validate_plan` | *"Check the plan against the data."* | 6 of 6 keys unique, 6 of 6 relationships hold; the counting SQL uses backticks and `COUNT` | | |
| D4 | `sample_rows` | *"Show five rows of customers."* | 5 rows (`LIMIT 5`), `name` masked (P1) | | |
| D5 | `join_path` | *"How do customers and categories connect?"* | 4 hops, R1, and Databricks SQL with `workspace`.`shop`.… and `LIMIT 100` | | |
| D6 | `suggest_relationships` | *"Which columns look like references but are in no relationship?"* | `orders.ship_to_id → addresses.address_id` with inclusion 1.0 | | |
| D7 | `databricks_constraints_draft` | *"Draft the constraints for schema shop, checked against the data."* | 6 primary keys and 6 foreign keys, each `RELY`, or the keys left out with the reason "may hold NULLs" (the seed's columns are nullable) | | |
| D8 | `databricks_constraints_draft` with `set_not_null=true` | *"The same, and add NOT NULL where the data allows it."* | `ALTER COLUMN … SET NOT NULL` before each primary key | | |
| D9 | `create_databricks_constraints` | *"Add those constraints. Dry run first, then for real with set_not_null."* | dry run: the statements; then `result: Succeeded`; `DESCRIBE TABLE EXTENDED workspace.shop.orders` shows the constraints | | |
| D10 | `plan_backend` again | *"Plan schema shop again."* | keys K0 and relationships R0 (declared now) | | |
| D11 | `create_views` | *"Create the views for schema shop. Dry run first, then create."* | `workspace.krusgraph.vw_order_items` and `vw_orders`; `SELECT * FROM workspace.krusgraph.vw_orders LIMIT 5` works | | |
| D12 | `create_databricks_pipeline` | *"Create the pipeline shop_layers for schema shop, order_by orders: order_date. Dry run first."* | dry run: two notebooks; then the pipeline in Jobs & Pipelines; start it by hand: `workspace.silver.*`, `workspace.silver.krusgraph_quarantine` (empty on the clean seed), `workspace.gold.order_items` | | |
| D13 | `databricks_metric_view_draft` | *"Draft metric views for schema shop."* | `order_items_metrics` with `Rows in order_items` and `Total quantity`; run its SQL and `SELECT MEASURE(\`Total quantity\`) FROM workspace.krusgraph.order_items_metrics` | | |
| D14 | `export_databricks_bundle` | *"Export a bundle for schema shop."* | 9 files; in a folder with them, `databricks bundle validate -t dev` passes (set the host first) | | |
| D15 | `databricks_lineage` | first in SQL: `DESCRIBE system.access.table_lineage`; then *"What reads from schema shop?"* | the columns used (`source_table_full_name`, `target_table_full_name`, `entity_type`, `entity_id`, `event_time`, `event_date`) exist; after D12 the pipeline's reads and writes | | |
| D16 | a Fabric-only tool | *"Draft a Power BI semantic model for schema shop."* | `kind: unsupported`, pointing to `databricks_metric_view_draft` | | |

A row that passes moves that tool's status in [DATABRICKS.md](DATABRICKS.md) from Draft only to Experimental (the
local server against a real workspace); nothing on the site changes before that.
