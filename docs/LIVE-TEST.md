# Live test checklist

For the maintainer, after `bash deploy/krusgraph.sh --update`, against the demo workspace `demo`, the lakehouse
`demo_lh` and the schema `shop` (the synthetic data of `fabric_backend/seed.py`), from Claude with the connector
signed in. The workspace id is not written here; the protocol of a run stays outside the repository. Fill in the
**Result** (✓, or what came instead) and the **Date**; a row is passed when the answer says what **Expected** says.
"27 Oct" marks the rows that passed on 27 October 2026 (from Claude through the hosted build `src-df29c45febaec4b0`,
main 5adace8: 30 tools read-only, as drafts or as dry runs, then one creating call, `create_backend` updating `shop_api`
in place, with the maintainer's approval); "26 Oct" the 14 steps of the day before.
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
| 4 | `plan_backend` | *"Plan a backend over demo_lh, schema shop."* | 7 tables, 6 with keys, 6 relationships (all R1); `audit_log` without a key; `order_items` keyed `order_id + line_no` (K5) | 26, 27 Oct | | |
| 5 | `sample_rows` | *"Show me five rows of customers in demo_lh, schema shop."* | 5 rows; `name` shows `***` with a `personal_data` notice (rule P1) and the parameter `show_personal_data`; the lakehouse's sensitivity label id if it has one | 26 Oct (before masking), 27 Oct (masked) | | |
| 6 | `validate_plan` | *"Check the plan against the data."* | 6 of 6 keys unique, 6 of 6 relationships hold without orphans | 26, 27 Oct | | |
| 7 | `create_backend` | *"Update shop_api from demo_lh, schema shop, and keep orders.ship_to_id → addresses.address_id."* | `mode: updated`, the endpoint; nothing dropped (see section 3) | 27 Oct (`Succeeded`, `updated`, after `would_remove`; see sections 2 and 3) | | |
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
| 18 | `create_semantic_model` | *"Create the semantic model shop_model from demo_lh, schema shop. Dry run first, then create."* | dry run: the parts and the REST call; create: `kind: consent` naming `SemanticModel.ReadWrite.All` (or `Item.ReadWrite.All`) | 27 Oct (dry run) | | |
| 19 | `create_views` | *"Which views would create_views make in demo_lh, schema shop? Dry run."* | `vw_order_items`, `vw_orders`; with `ship_to_id` confirmed also a view named after the relationship's field (`vw_orders_ship_to` with the entry of section 3; 27 October showed `vw_orders_address`, the field name Claude passed) | 26, 27 Oct (dry run) | | |
| 20 | `create_views` (create) | *"Create those views."* (only if a test schema `krusgraph` on `demo_lh` is wanted) | schema `krusgraph` and the views created; `list_tables` with schema `krusgraph` lists them | — | | |
| 21 | `create_data_agent` | *"Draft a data agent over demo_lh, schema shop. Dry run."* | instructions, the source with the plan's tables, 10 example questions with T-SQL; no example selects or groups by `customers.name` (`customer_id` instead) and `personal_data.left_out` names it, unless `show_personal_data=true`; asked to create: `kind: consent` | 27 Oct (dry run; see section 2) | | |
| 22 | `create_ontology` | *"Create the ontology shop_ontology. Dry run first."* | dry run: the parts and the call; create: `kind: consent` naming `Item.ReadWrite.All` | — | | |
| 23 | `app_starter` | *"Give me the starter pack for an app on shop_api."* | a Lovable prompt, five queries, the Supabase edge function | 26 Oct (prompt and queries), 27 Oct | | |
| 24 | `app_readiness` | *"What does shop_api still need before an app can use it?"* | introspection on or off (one probe), the types without a key, permissions reported as unknown with the portal path | 27 Oct | | |
| 25 | `analyze_schema` | *"Read demo_lh, schema shop, as a graph."* | 3 fact tables (orders, order_items, audit_log), 4 dimensions, 6 relationships active at once, no cycles | 26, 27 Oct | | |
| 26 | `lineage` | *"What builds on the tables in demo_lh, schema shop?"* | `shop_api` on the seven tables; the views on the SQL endpoint (`krusgraph.vw_order_items` is there already); an item that could not be read is listed with Fabric's `error`, its `reason` and a `hint` | 27 Oct (`shop_api` skipped: see section 2) | | |
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

Seen, not changed: `demo_lh` already holds the view `krusgraph.vw_order_items`, so `create_views` has created a view
there at some point, but no protocol of that run exists. Creating with `create_views` stays Experimental until row 20
is run and written down.

## 3. Before the next `create_backend shop_api`

`shop_api` carries `orders.ship_to_id → addresses.address_id`, which the plan does not infer, as the fields
`orders.address` and `addresses.orders`. The next `create_backend` with the name `shop_api` must pass the relationship,
or it is dropped (the tool then stops with `kind: would_remove`, nothing is written, and `keep_with_confirmed` gives the
entry with both names). Since the fix of finding 7 the entry needs no field names: an update keeps the names the API
has for the same relationship, and the answer lists them under `names_kept_from_api`.

```json
"confirmed": [{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}]
```

In Claude: *"Update shop_api from demo_lh, schema shop, and keep orders.ship_to_id → addresses.address_id."* (row 7).
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
