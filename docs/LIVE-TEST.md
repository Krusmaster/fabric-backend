# Live test checklist

For the maintainer, after `bash deploy/krusgraph.sh --update`, against the demo workspace `demo`, the lakehouse
`demo_lh` and the schema `shop` (the synthetic data of `fabric_backend/seed.py`), from Claude with the connector
signed in. The workspace id is not written here; the protocol of a run stays outside the repository. Fill in the
**Result** (✓, or what came instead) and the **Date**; a row is passed when the answer says what **Expected** says.
"26 Oct" marks the tools that passed in the 14 steps of 26 October 2026 (no creating call that day).

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
| 1 | `list_workspaces` | *"Which Fabric workspaces can I see?"* | `demo` among them, with its capacity | 26 Oct | | |
| 2 | `list_sources` | *"List the data sources in the demo workspace."* | `demo_lh` (Lakehouse) and the API `shop_api` | 26 Oct | | |
| 3 | `list_tables` | *"Which tables and columns are in demo_lh, schema shop?"* | 7 tables: customers, categories, products, addresses, orders, order_items, audit_log, with types | — | | |
| 4 | `plan_backend` | *"Plan a backend over demo_lh, schema shop."* | 7 tables, 6 with keys, 6 relationships (all R1); `audit_log` without a key; `order_items` keyed `order_id + line_no` (K5) | 26 Oct | | |
| 5 | `sample_rows` | *"Show me five rows of customers in demo_lh, schema shop."* | 5 rows; `name` shows `***` with a `personal_data` notice (rule P1) and the parameter `show_personal_data`; the lakehouse's sensitivity label id if it has one | 26 Oct (before masking) | | |
| 6 | `validate_plan` | *"Check the plan against the data."* | 6 of 6 keys unique, 6 of 6 relationships hold without orphans | 26 Oct | | |
| 7 | `create_backend` | *"Update shop_api from demo_lh, schema shop, and keep orders.ship_to_id → addresses.address_id."* | `mode: updated`, the endpoint; nothing dropped (see section 3) | — | | |
| 8 | `describe_backend` | *"What can I query in shop_api?"* | the types of the seven tables with fields and relationship names | 26 Oct | | |
| 9 | `query_graphql` | *"Using shop_api, list five orders with their customer."* | 5 orders, each with its customer object; a mutation asked for is refused | 26 Oct | | |
| 10 | `query_graphql` with `question` | *"Using shop_api, how many orders per customer? Run it."* | the suggested query beside the result, grouped by `customer_id` | — | | |
| 11 | `rayfin_connector` | *"Generate Rayfin connector entities for demo_lh, schema shop."* | 9 files: 7 entity classes, `schema.ts`, `README.generated.md` | — | | |
| 12 | `ontology_draft` | *"Draft a Fabric IQ ontology from demo_lh, schema shop."* | 7 entity types (5 with a key; `order_items` and `audit_log` noted), 6 relationship types, a Turtle file | — | | |
| 13 | `semantic_model_draft` | *"Draft a Power BI semantic model for demo_lh, schema shop."* | 7 Direct Lake tables plus `Calendar` (marked as date table), 6 relationships plus `orders.order_date → Calendar.Date`, 4 suggested measures each with its reason, `ship_to_id` not summed | 26 Oct (before measures) | | |
| 14 | `join_path` | *"How do customers and categories connect?"* | 4 hops, each R1, and the T-SQL | 26 Oct | | |
| 15 | `data_dictionary` | *"Write the data dictionary for schema shop, with the checks."* | Markdown with the 7 tables and the counts of row 6 | 26 Oct | | |
| 16 | `dbt_schema` | *"Give me the dbt sources file for schema shop."* | `models/sources/shop.yml` with `unique`, `not_null` and `relationships` tests | 26 Oct | | |
| 17 | `plan_drift` | *"What would change in shop_api if I re-ran create_backend?"* | the `ship_to_id → addresses` relationship the plan does not infer, with its `confirmed` entry | 26 Oct | | |
| 18 | `create_semantic_model` | *"Create the semantic model shop_model from demo_lh, schema shop. Dry run first, then create."* | dry run: the parts and the REST call; create: `kind: consent` naming `SemanticModel.ReadWrite.All` (or `Item.ReadWrite.All`) | — | | |
| 19 | `create_views` | *"Which views would create_views make in demo_lh, schema shop? Dry run."* | `vw_order_items`, `vw_orders`; with the confirmed `ship_to_id` also `vw_orders_ship_to` | 26 Oct (dry run) | | |
| 20 | `create_views` (create) | *"Create those views."* (only if a test schema `krusgraph` on `demo_lh` is wanted) | schema `krusgraph` and the views created; `list_tables` with schema `krusgraph` lists them | — | | |
| 21 | `create_data_agent` | *"Draft a data agent over demo_lh, schema shop. Dry run."* | instructions, the source with the plan's tables, 10 example questions with T-SQL; asked to create: `kind: consent` | — | | |
| 22 | `create_ontology` | *"Create the ontology shop_ontology. Dry run first."* | dry run: the parts and the call; create: `kind: consent` naming `Item.ReadWrite.All` | — | | |
| 23 | `app_starter` | *"Give me the starter pack for an app on shop_api."* | a Lovable prompt, five queries, the Supabase edge function | 26 Oct (prompt and queries) | | |
| 24 | `app_readiness` | *"What does shop_api still need before an app can use it?"* | introspection on or off (one probe), the types without a key, permissions reported as unknown with the portal path | — | | |
| 25 | `analyze_schema` | *"Read demo_lh, schema shop, as a graph."* | 3 fact tables (orders, order_items, audit_log), 4 dimensions, 6 relationships active at once, no cycles | 26 Oct | | |
| 26 | `lineage` | *"What builds on the tables in demo_lh, schema shop?"* | `shop_api` on the seven tables; views if row 20 ran; items that could not be read are listed | — | | |
| 27 | `suggest_relationships` | *"Which columns look like references but are in no relationship? Check the best against the data."* | `orders.ship_to_id → addresses.address_id` first, holding for every value | 26 Oct | | |
| 28 | `silver_notebook_draft` | *"Draft the silver notebook for demo_lh, schema shop."* | steps for 7 tables in schema `silver`, quarantine `krusgraph_quarantine`, `customers.name` and `addresses.city` masked in quarantine | — | | |
| 29 | `create_silver_notebook` | *"Create it as silver_shop. Dry run first, then create."* | dry run: the notebook and the call; create: `kind: consent` naming `Notebook.ReadWrite.All` (or `Item.ReadWrite.All`) | — | | |
| 30 | `drift_monitor_draft` | *"Draft a nightly drift monitor for demo_lh, schema shop."* | a notebook, a pipeline `<name>_nightly` and a daily schedule at 02:00 | — | | |
| 31 | `create_drift_monitor` | *"Create it as drift_shop. Dry run."* | the items and the three REST calls; asked to create: `kind: consent` | — | | |
| 32 | `answer_query_draft` | *"How many orders per customer in demo_lh, schema shop? Only the query."* | T-SQL grouped by `customer_id`, with `customers.name` left out by the privacy rule; with `api=shop_api` also the GraphQL | — | | |
| 33 | `compare_semantic_model` | *"Draft the semantic model for demo_lh, schema shop, then compare it with the plan using its files."* | through `tmdl`: the 6 relationships agree, nothing missing or contradicted, `Calendar` outside the plan | — | | |
| 34 | `compare_semantic_model` (by name) | *"Compare the semantic model <a model in demo> with the plan for demo_lh, schema shop."* | without the permission: `kind: consent` naming `SemanticModel.ReadWrite.All (or Item.ReadWrite.All)` and the `tmdl` way round | — | | |
| 35 | `gold_views_draft` | *"Draft the gold views for demo_lh, schema shop."* | `gold.audit_log`, `gold.order_items`, `gold.orders`, each with its constraints and their rules; `customers.name` left out | — | | |
| 36 | `create_gold_views` | *"Create the gold notebook gold_shop. Dry run first."* | dry run: the notebook and the call; create: `kind: consent` naming `Notebook.ReadWrite.All` | — | | |
| 37 | `export_item_definitions` | *"Export what you would create for demo_lh, schema shop, in Fabric's Git format."* | folders `demo_lh_api.GraphQLApi`, `demo_lh_model.SemanticModel`, `silver_shop.Notebook`, `drift_monitor_shop.Notebook`, `drift_monitor_shop_nightly.DataPipeline`, `gold_shop.Notebook`, `krusgraph-sql/`; the largest file named under `omitted` | — | | |
| 38 | `review_plan` | *"Keep this review as a file: confirm orders.ship_to_id → addresses.address_id as the ship-to address, reject audit_log → customers as log only, and run the checks."* Save the file; then add a column to `orders` in the lakehouse and ask *"Read back the review file and tell me what changed."* | first answer: 6 keys and 7 relationships, the ship-to relationship `accepted` with its reason, `audit_log` as an open question, every check `passed` with the time, no row values in the file; second answer: the new column under `since_previous`, the checks on `orders` and its relationships `stale`, the others `passed` with their first date, the decisions still there | — | | |

## 2. Fixed after the 26 October run, unit-tested only

The 26 October run found these three; each is fixed and covered by unit tests, and none has run live since.

| What the run showed | Fixed in | Question in Claude | Expected now | Result | Date |
| --- | --- | --- | --- | --- | --- |
| `semantic_model_draft` summed `orders.ship_to_id` (`summarizeBy: sum` on an id) | 77c9cbc | *"Draft a semantic model for demo_lh, schema shop, and show me orders.tmdl."* | `ship_to_id` has `summarizeBy: none`; only `order_items.quantity` is summed | | |
| `suggest_relationships` gave all four candidates for `orders.ship_to_id` the same score | 7791941 | *"Which columns in demo_lh, schema shop, look like references but are in no relationship? Check the best ones against the data."* | `addresses.address_id` ranks first before the data check (about 3.94 against 1.5 or less) and holds for every value after it | | |
| `create_views` (dry run) proposed one view only | 961f8b6 | *"Which views would create_views make in demo_lh, schema shop? Dry run."* | `vw_order_items`, `vw_orders` and, once `orders.ship_to_id` is confirmed, `vw_orders_ship_to` | | |

## 3. Before the next `create_backend shop_api`

`plan_drift` on `shop_api` showed that the API carries `orders.ship_to_id → addresses.address_id` and the plan does not
infer it. The next `create_backend` with the name `shop_api` must pass it, or the relationship is dropped (the tool then
stops with `kind: would_remove` and nothing is written):

```json
"confirmed": [{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}]
```

In Claude: *"Update shop_api from demo_lh, schema shop, and keep orders.ship_to_id → addresses.address_id."* (row 7).

## 4. Clients

Prepared, not switched on: `bash deploy/krusgraph.sh --client-redirects` prints the commands, and
`docs/OPERATIONS.md` section 5 has the sources. After registering the addresses:

| Client | How | Expected | Result | Date |
| --- | --- | --- | --- | --- |
| Claude Code | `claude mcp add --transport http --client-id <APP_ID> --callback-port 8080 krusgraph https://krusgraph.com/mcp`, then `claude mcp login krusgraph`; ask *"Which Fabric workspaces can I see?"* | Microsoft sign-in in the browser, then `demo` in the answer | | |
| VS Code (GitHub Copilot agent mode) | `mcp.json` with `"oauth": {"clientId": "<APP_ID>"}`; *MCP: List Servers* → Start; ask the same in agent mode | the same | | |
| Cursor | `~/.cursor/mcp.json` with `"auth": {"CLIENT_ID": "<APP_ID>"}`; sign in from the MCP settings; note the `redirect_uri` in the address that opens | the same, and a `redirect_uri` that is registered | | |

## 5. From the filled-in checklist to the status words

1. A tool whose rows in section 1 all passed is **Tested end to end**; when only its dry run ran, **Tested end to end
   (dry run)**. A creating tool that answered `consent` stays **Available when enabled by the operator** until it has
   created something live. A row that did not pass keeps the tool where it is, and the difference goes to an issue.
2. In `fabric_backend/page_templates/DOCS.md`: the tool's Status column, and in *Test status* the date and the list of
   tools the run covered.
3. The same list in `fabric_backend/discovery.py` (the *Test status* sentence of `llms.txt`), in the README's *Status*
   section, and in `deploy/SUBMISSION.md` row 5.
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
