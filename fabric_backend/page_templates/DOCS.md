# {{PRODUCT}} docs

<!-- figure:overview-film -->
<!-- /figure -->

See how your business tables really connect – with the proof behind every link – so your reports, apps and agents get the numbers right.

- The proof: every proposal shows its basis, and the checks you run show their results.
- The errors before anyone sees them: the total that doubles, keys that are not unique, references with no matching row.
- SAP knowledge from public sources: keys with MANDT and the order-to-cash links for VBAK, VBAP and their neighbours, each with its source.
- One plan for what you build: the same reviewed plan drafts a GraphQL API, a Power BI model, a Fabric IQ ontology and a data agent.

Connect {{PRODUCT}} to Claude to inspect a Fabric schema, review the suggested relationships, check them against your
data and build from the plan. Start with the connection guide, or try the [guided demo](/check?example=sample&guide=1) and
[the example's map](/check?example=sample#check-map) without an account. The tool reference explains what each tool reads, returns or changes, and
how far it has been tested.

## Why {{PRODUCT}}

**{{PRODUCT}} stores no table contents.** It reads your lakehouse, warehouse or SQL database where it is (lakehouses are
tested end to end; the other sources are Experimental until a live run). Plans come from table and column metadata
and the bounded counts of rule R5 (below), checks run as counting queries in Fabric, and the samples and query results you ask for pass through to your MCP
client without being kept. What it creates is created in Fabric.

**Rules you can check, not guesses.** Keys and relationships come from documented rules ([K0–K5, R0–R4](#how-relationships-are-inferred))
and, for SAP tables, a pack built from public SAP documentation (`sap_pack_draft`: Draft only, tested on a synthetic
SAP schema, not on an SAP system). Every key and relationship shows the rule or source behind it. Columns that could
mean more than one thing are reported, not guessed.

**Checked against the data.** `validate_plan` counts, per key, the rows, the empty key values and the distinct values,
and, per relationship, the references with no matching row, over the whole table, for up to `max_items` keys and
relationships per call (default {{VALIDATE_MAX_ITEMS}}); its summary says when it checked fewer than the plan has. By
default (`detail="summary"`) the answer is the verdict line, the totals checked, passed and failed, and every check that
failed or could not be counted in full, with its counts and rule; passing checks appear as a count, and the answer says
how many it left out. `detail="full"` lists every check with its counts. It is
a separate step: run it before you create anything, because `create_backend` does not run it for you. `plan_backend`
counts less on its own: its rule R5 reads the first {{R5_SAMPLE}} distinct values of a code or role column the names left
unlinked, with at most {{R5_MAX_QUERIES}} counting queries per call, and the answer's `counted_in_rows` says how many
candidates it counted and how many were left for `validate_plan` or `suggest_relationships`.

**One reviewed plan, several Fabric items.** The same plan drafts the API for GraphQL, a Power BI semantic model, a
Fabric IQ ontology, views, a data agent and silver notebooks, so they agree on how the tables relate. How far creating
each one has run live differs; the words below come from the same list as the [tool reference](#test-status):

- the API for GraphQL: {{CREATE_API_STATUS}}
- the views: {{SHORT_CREATE_VIEWS}}
- the Power BI semantic model: {{SHORT_CREATE_SEMANTIC_MODEL}}
- the Fabric IQ ontology: {{SHORT_CREATE_ONTOLOGY}}
- the data agent: {{SHORT_CREATE_DATA_AGENT}}
- the silver notebooks: {{SHORT_CREATE_SILVER_NOTEBOOK}}

**Your Microsoft account and permissions.** On the hosted service you sign in with your work account, and {{PRODUCT}}
acts with delegated permissions as you, so it sees only what your Fabric permissions allow. An app built on the API
has its own identity and access settings; see [App access](#app-access) before you publish one.

**Drafts first.** Every creating tool answers with what it would create until you pass `dry_run=false`; use
`plan_backend`, `validate_plan` and, for an existing API, `plan_drift` before `create_backend` writes.

**Open source.** MIT-licensed. Use the hosted service or run it yourself ([locally](/local), or in your own Azure
subscription with `deploy/krusgraph.sh`).

**When {{PRODUCT}} is not the right tool:** if your data isn't in Fabric yet, if you're building a transactional app
that needs its own database, or if you need row-level security defined in the API itself. Fabric's API for GraphQL has
no row-level security of its own; it applies what the source enforces for the identity that queries it (see
[App access](#app-access)), and {{PRODUCT}} does not create security policies.

## Get started

New to a Fabric lakehouse? Start with how its tables fit together. Connect the hosted server to Claude, then ask a first question. The [guided demo](/check?example=sample&guide=1) runs the engine on a synthetic shop in your browser. It needs no account. Onto leads four steps over its map. The first three show how the tables connect, the total that doubles and a suggestion to decide on. The fourth leads on to Power BI or an app.

### Connect

1. **Your Entra admin grants consent once** for your organization:
   [grant admin consent](https://login.microsoftonline.com/organizations/adminconsent?client_id={{CLIENT_ID}}&redirect_uri={{CONSENT_URL_ENC}}).
   This lets the connector call Fabric and SQL as each signed-in user. It allows nothing more. Microsoft then sends the
   admin to [{{DOMAIN}}/consent/done](/consent/done). That page says whether the consent was granted, and what to do next if it was not.
2. **In Claude:** Customize → Connectors → Add → Add custom connector, with the URL
   `{{CLAUDE_URL}}`. {{#IF CLIENT_REGISTRATION}}Keep **Register automatically** selected (no client ID or secret), add it,
   and sign in with your Microsoft work account now. {{CLAUDE_WHY}} VS Code, Cursor and other MCP clients that sign in on
   their own use the same `{{CONNECT_URL}}` ([below](#other-mcp-clients)).{{/IF}}{{#IF NO_CLIENT_REGISTRATION}}Sign in with your Microsoft work account. {{/IF}}{{#IF NO_CLIENT_REGISTRATION}}The hosted service supports Claude, and Claude is the client
   it has been tested with. Claude Code and Cursor sign in through a local redirect that is not registered on the Entra
   app yet. So they can't sign in to {{DOMAIN}} today. Other MCP clients should work when you host {{PRODUCT}} yourself. This is not tested yet.{{/IF}}
3. **In Fabric:** you need access to the workspace you want to use. You also need a Fabric capacity. A trial is fine.

Every call runs with your own Fabric permissions. The step-by-step version is on [/start](/start). The server is
published in the official [MCP Registry](https://registry.modelcontextprotocol.io/v0.1/servers?search=com.krusgraph%2Fkrusgraph) as `com.krusgraph/krusgraph` (verified 26 October 2026).
Prefer your own machine and a SQL Server? The same engine runs locally over ODBC. See [/local](/local).
{{#IF CLIENT_REGISTRATION}}
### Other MCP clients

VS Code, Cursor and other MCP clients that register themselves sign in at `{{CONNECT_URL}}`, the address Claude's
connector dialog uses too (with "Register automatically"). {{PRODUCT}} identifies the client by the metadata document it publishes. A client without one gets a
strict registration. {{PRODUCT}} then shows its own approval page with the client's name, its domain and where the answer
goes. Only after that does it send you to Microsoft. Every call still runs with your own Fabric permissions. Claude
connectors added earlier with `{{MCP_URL}}` keep working.
{{CONNECT_TESTED}}.

- **VS Code** (GitHub Copilot agent mode): in `.vscode/mcp.json` or *MCP: Open User Configuration*, add
  `{"servers": {"{{PRODUCT_LOWER}}": {"type": "http", "url": "{{CONNECT_URL}}"}}}`, then *MCP: List Servers* → Start.
  The answer goes to a program on your computer, so the approval page comes back at each new sign-in.
- **Cursor:** in `~/.cursor/mcp.json`, add `{"mcpServers": {"{{PRODUCT_LOWER}}": {"url": "{{CONNECT_URL}}"}}}`, then sign in
  from Cursor's MCP settings. {{PRODUCT}} does not accept the `cursor://` address that some Cursor builds register. It
  accepts only https and local addresses. If the sign-in stops on the redirect address and the operator has turned on
  dynamic registration (`KRUSGRAPH_CLIENT_REGISTRATION_DCR=1`, on at krusgraph.com; a self-hosted server has it off unless
  set), register Cursor once with its local address, `curl -s {{CONNECT_URL_OAUTH}}/register -H 'Content-Type: application/json' -d '{"client_name": "Cursor", "redirect_uris": ["http://localhost:8787/callback"]}'`,
  and give Cursor the `client_id` from the answer as `"auth": {"CLIENT_ID": "…"}` next to the `url`.
- **Glama:** add `{{CONNECT_URL}}` in Glama's MCP connector. Glama identifies itself with its metadata document.
- **Claude Code:** {{CLAUDE_CODE_CONNECT}}

The approval page and Microsoft's sign-in open in your own browser. A web filter on a company network can stop them.
The browser then says the site "uses an unsupported protocol". Sign in from another network, or ask IT to allow
{{DOMAIN}}.
{{/IF}}
### What you can ask

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

### First-time errors

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

Two more that a first-time user of the Krusgraph Model item in Fabric can meet:

| You see | What happened | What to do |
| --- | --- | --- |
| Krusgraph Model keeps loading in Fabric (or `ERR_SSL_VERSION_OR_CIPHER_MISMATCH` for `workload.krusgraph.com`) | A corporate web filter blocks a domain it does not know yet; the server supports TLS 1.2 and 1.3 | Ask your IT department to allow `workload.krusgraph.com` and `krusgraph.com` on port 443 (TLS 1.2 or later): [Network: hosts to allow](/it#network). Then reload the Fabric tab. |
| `schema_ambiguous` | Two schemas in the lakehouse differ only by case (`Shop` and `shop`) | Type the schema exactly as one of the names the answer lists. A schema typed in another case than the only one that exists is read under the lakehouse's spelling, and the answer says which name was used (`schema_used`). |

## Concepts

What the parts are and how they fit together. The examples on these pages are generated by the engine from the
synthetic shop schema each time a page is rendered: the same schema the [example on /check](/check?example=sample) runs
in your browser, with no account.

### How it works

{{PRODUCT}} sits between the AI client you ask in and Microsoft Fabric. It reads table and column metadata, makes one
plan of keys and relationships with the rule behind each one, counts checks against the rows as queries in Fabric, and
creates Fabric items from that plan only when you ask. Four parts, with how far each has been tested:

<!-- figure:how-it-works -->
{{CONCEPT_PARTS}}
<!-- /figure -->

The status words come from the same list as the [tool reference](#test-status), and change there first.

### Ontologies

An ontology gives your tables and relationships business names. Each table becomes an **entity type** with
properties and a **key**, and each relationship becomes a **relationship type** between two entity types, with a
binding to the table and columns it comes from. In Fabric this is Fabric IQ's ontology item (preview); the ontology agent
and data agents use it as context.

**A key is one property, a string or an integer.** A table whose key is one such column gets it as the entity type's
key. A composite key (two columns or more) cannot be one property, so a person chooses: pick one of its columns, or add
a column that combines them. {{PRODUCT}} does not choose for you: the entity type is drafted without a key, and the
draft's summary says why. On the shop schema that is {{CONCEPT_COMPOSITE}}.

What the engine drafts from the shop schema: {{CONCEPT_ONTOLOGY_COUNTS}}.

<!-- figure:ontology -->
{{CONCEPT_ENTITIES}}

Relationship types, each from a relationship in the plan:

{{CONCEPT_REL_TYPES}}
<!-- /figure -->

{{CONCEPT_ONTOLOGY_STATUS}} The [example on /check](/check?example=sample#check-evidence) offers the same ontology as an
RDF/XML file to download for Microsoft's Ontology Playground ({{CONCEPT_RDFXML_STATUS}}). How the draft maps to the
ontology item, and why {{PRODUCT}} comes before it, is in [Fabric IQ: the same graph as an ontology](#fabric-iq-the-same-graph-as-an-ontology).

### Data products

A **data product** is a domain's tables offered to the rest of the organisation: it has an **owner**, an
**interface** (the keys other domains use) and a **contract** that says what they can rely on. A **domain** is a group
of tables that belong together; in Fabric, a domain is set up by a Fabric administrator, and workspaces are assigned
to it.

**{{PRODUCT}} proposes; you decide.** `domain_draft` groups the plan's tables by how strongly their keys and
relationships tie them together, keeps a header with its lines, names each group and writes one contract per domain in
the Open Data Contract Standard (ODCS) v3.2.0. It creates nothing: your administrator creates the Fabric domain, and
you decide who owns each data product. A table without a key is left unassigned, because a contract cannot promise its
rows are unique.

What the engine proposes for the shop schema: {{CONCEPT_DOMAIN_NAMES}}, with one interface between them.

<!-- figure:domains -->
{{CONCEPT_DOMAINS}}
<!-- /figure -->

The start of the contract for the domain that uses the interface, cut from the draft the engine wrote:

```yaml
{{CONCEPT_ODCS}}
```

Status: {{CONCEPT_DOMAIN_STATUS}}. The domain proposals and their contracts are drafts to review, and nothing in
Fabric is created from them. On [/check](/check?example=sample) the example shows the same domains on its map under
**Proposed domains**; how the split is made is in `docs/DOMAINS.md` in the repository.

### How they connect

Everything comes from the same reviewed plan: {{CONCEPT_PLAN_COUNTS}} on the shop schema, each with the rule behind
it, counted against the rows and corrected by you through `keys` and `confirmed`. The API for GraphQL, the Power BI
semantic model, the ontology and the data products are each written from that plan, so they agree on how the tables
relate: change the plan once, and each is written again from it.

<!-- figure:connect -->
{{CONCEPT_FLOW}}
<!-- /figure -->

One relationship, {{CONCEPT_INTERFACE}}, in each of them:

{{CONCEPT_TRACE}}

A table without a key stays out wherever a key is needed: {{CONCEPT_UNASSIGNED}} has no entity key in the ontology and
no domain among the data products. What each piece is, and how far creating it has been tested, is in
[One plan, five Fabric pieces](#one-plan-five-fabric-pieces).

### Where it runs

Two choices shape an agent for a task: where it runs, and how capable an agent the task needs. Where it runs should
follow where your data access is: files on a laptop, a database in-house, your own Azure tenant or your Fabric through
the hosted service. {{PRODUCT}} is the same engine in four places, and each place can do a different part of a task.

<!-- figure:where -->
{{CONCEPT_WHERE}}
<!-- /figure -->

{{CONCEPT_WHERE_NOTES}}

### Vision

<!-- figure:vision -->
**One place for your Fabric data. Proof at every step.**

Where {{PRODUCT}} is today, and where it is going.

**Available today: Check and create**

- Map how your tables connect
- Count every link against the rows
- Create Fabric items when you ask

**Next: Check what comes in**

- See if incoming data matches its source
- Set up Fabric's own tools, with your approval

**Vision: One place for the whole chain**

- From source system to report
- Any source, with the tool you choose

**The goal: nothing gets built on a link nobody counted.**

Next and Vision are direction, not current features.
<!-- /figure -->

## Explore and check

How a plan is made, how to read it, how to check it against the rows before anything is built, how to keep the review, and the fixes proposed for what the check finds.

### Review, check, then create

A plan is a proposal, so read it before anything is built.

1. **Review the plan.** Each key and relationship carries the rule that made it; ambiguous columns and tables without a key are listed. Correct a key with `keys` and add a relationship the rules did not make with `confirmed`.
2. **Check it against the data.** `validate_plan` counts duplicate and NULL key values and references with no matching row. `create_backend` does not run it for you, so ask for it. A check that passes shows the data agrees with the plan today; it does not show that the plan means the right thing. With `fixes=true` it also proposes a fix per finding and applies nothing (see *Fix data issues*).
3. **Create the API.** `create_backend` creates the API for GraphQL item, or updates the one with that name. By default it answers with a dry run (created or updated, what changes, the checks that passed); `dry_run=false` writes. An update keeps the field names the existing API has for the same relationships. If it would still remove relationships the API has, nothing is written and the answer lists them with the `confirmed` entries that keep them (both field names included); `allow_removals=true` drops them on purpose.
4. **Query it.** `describe_backend` gives the field names; `query_graphql` runs read-only queries and refuses mutations. Two portal steps stay manual (see below).
5. **Keep the review.** `review_plan` writes the plan, your decisions with their reasons and the check results as one
   file for your own repository. Pass it back later as `previous`: the corrections apply again and what changed since
   is listed (see *Keep your review*).

### Keep your review

A review is worth keeping when the next report or app builds on the same tables. `review_plan` returns one JSON file
(`krusgraph-review.<source>.<schema>.json`) and a short Markdown report; it creates nothing in Fabric.

- **What it holds:** the format and its version, a plan id, the source (workspace, item and schema names), a
  fingerprint of the tables' columns and types, the plan snapshot (the same one the drift monitor keeps), every key and
  relationship as an item (`key:orders`, `rel:orders.customer_id>customers`) with its rule and what the rules alone
  proposed when you corrected it, open questions (ambiguous columns, tables without a key, items you left open), and the
  `keys` and `confirmed` arguments that carry your corrections into the other tools. Names, types, rules, decisions and
  counts only: no row values, samples, connection strings or tokens.
- **Two statuses per item.** *Review* is what a person decided: proposed, accepted, rejected or open, with a reason
  (`decisions`). *Check* is what the counting queries found: not checked, passed, failed or stale, with the counts and
  the time. They are kept apart: an accepted relationship can fail its check, and a passing check does not show that a
  relationship means the right thing.
- **Reading it back.** With `previous`, the decisions apply again, the schema is compared with the file's (tables,
  columns, types, keys and relationships added or removed), decisions that no longer match the plan are listed, and a
  check on a table whose columns changed becomes *stale*: an old pass is not carried forward as new evidence.
  `validate=true` runs the checks again.
- **Limits.** A relationship you reject stays rejected in the file, but the other tools still infer it from the names;
  leave it out of what you build. A large schema may not fit one answer; `tables` limits the file to an area. The
  first answer ran live on 27 October 2026; reading a file back is unit-tested and has not run against a live workspace.

### Fix data issues

`validate_plan` with `fixes=true` proposes one fix per finding of the check. It proposes only: nothing is applied,
written or run. Each entry has an `id`, what is wrong, the fix in plain words, the counts before (the check's own) and
the counts expected after, the PySpark lines the silver notebook would add, the T-SQL that counted it, and a `type`:

- **mechanical**, a stated rule with nothing to decide: a row with a NULL key goes to quarantine; of exact copies of a
  row one stays; rows that share a key and differ keep the latest by a load or change time column when the table has
  one (named like `updated_at`); a reference that matches no row goes to quarantine, so nothing is lost; an amount a
  flat table repeats on every row of a header value moves to a table with one row per header value.
- **business_decision**, a question with options and no default: which of two differing rows is right when no time
  column orders them, whether an orphan should be dropped for good or its parent created, which level a header amount
  belongs to when a join with its lines would sum it once per line (the two sums are run and returned side by side),
  and every finding with no mechanical fix.

A NULL in a reference column is not an orphan: it is not counted as one, and the row stays. To tell exact copies from
differing rows, `fixes=true` runs one more counting query per key that is not unique. `review` takes a file from
`review_plan` (its keys and relationships are used, and its decisions show on each entry); `tables` keeps the entries
about some tables.

To apply, pass the ids you accept to `silver_notebook_draft` or `create_silver_notebook` as `fixes=["key:customers",
"rel:orders.customer_id>customers"]`. An orphan fix takes `{"id": ..., "choice": "set_null"}` where that is offered; a
duplicate key takes `{"id": ..., "winner": "<column>"}`. The notebook applies exactly those fixes, in silver only: it
reads the source tables, writes the silver tables and `krusgraph_quarantine` (every row it removes, with the reason),
and prints a table of counts per fix at the end. An id that is only a question is refused, and a decision still open
stops the notebook before it writes anything. `create_silver_notebook` stays a dry run unless `dry_run=false`, and the
notebook runs only when you run it. Unit-tested on 8 November 2026 on the six datasets of /check and the shop example
(tests/test_n155_fix_plan.py); `fixes=true` has not been run against a live workspace.

### How relationships are inferred

A lakehouse has no declared keys, so names are all there is — and every result says which rule produced it,
so you can overrule it. Declared keys and foreign keys (warehouses) always win. A column that could point at
two tables is reported, never guessed; a column no rule matches is left unlinked and you can pass it as
`confirmed`. The [example on /check](/check?example=sample) shows the rules on a synthetic schema. The rules, in the engine's own words:

{{RULES_TABLE}}

Names are matched literally first. When nothing matches, a small documented **synonym table** is tried: abbreviations
(`cust`, `prod`, `ord`, `emp`, `dept`, `acct`, …), Swedish and German business words in singular and plural (`kund`/`kunder`,
`artikel`/`artiklar`, `leverantör`, `kunde`/`kunden`, `bestellung`, `rechnung`, `mitarbeiter`, …), after transliteration of
`å ä ö ü ß`; a leading `dim_`, `fact_` or `tbl_` is not part of a table's name, and `_sk`/`_bk` count as key suffixes. Every
match that rests on the table is listed under `synonyms` in `plan_backend` and on the relationship's `note`, and counts as
the weakest rule (R4), so the plan never hides that it translated a name. Measured on eleven schemas in
`docs/INFERENCE.md`; the five public schemas that need no synonyms are unchanged to the number.

More on how they interact, with examples: https://github.com/Krusmaster/fabric-backend#how-the-relationships-are-inferred

### Sources

**Tested end to end:** a lakehouse with schemas (the demo workspace's `demo_lh`, schema `shop`), read through its SQL
analytics endpoint. **Experimental:** warehouses and Fabric SQL databases, read the same way through their SQL endpoint
and covered by unit tests; warehouses also give declared keys and foreign keys (rules K0 and R0). **Experimental:** the
mirrored and Snowflake item types below. Tables a lakehouse holds as OneLake shortcuts (to another lakehouse, a
warehouse, ADLS or S3) are listed by its SQL analytics endpoint like its own tables, so they are planned with it.

{{PRODUCT}} reads sources through Fabric, so data that lives elsewhere takes one of two routes:

1. **Bring it into Fabric.** A *Snowflake database* item, a *Mirrored database* (Snowflake, Azure SQL, Cosmos DB, SAP via
   Datasphere, …), a *Mirrored Azure Databricks catalog* or a *Mirrored catalog* (preview) is a source like a lakehouse:
   `list_sources` shows it, `plan_backend` plans it and `create_backend` builds the API over its SQL analytics endpoint.
   The item is set up once in the Fabric portal; {{PRODUCT}} reads the endpoint id from the item, as Microsoft's REST
   specification documents it for each of these item types. Experimental: unit-tested, not yet run against a live item.
2. **Plan it where it is.** The engine reads `INFORMATION_SCHEMA`, which Snowflake and Databricks (Unity Catalog)
   expose like the Fabric SQL endpoint does. The open-source library, the CLI and the local `fabric-backend-mcp` server
   give you the graph, the rules, the diagram and the Rayfin entities straight from those systems (for Databricks with
   its own adapter, [below](#databricks-draft-only)); the API for GraphQL item is a Fabric object, so that last step
   needs route 1.

Snowflake has no `KEY_COLUMN_USAGE` view, so keys there come from names (rule K2) and are shown as such. Unity Catalog's
informational primary and foreign keys are read as declared keys (K0, R0). The item types, routes and `sqlEndpointProperties`
follow Microsoft's published REST specification; these source types are experimental until a live run.

### How {{PRODUCT}} uses graph theory

The plan is a graph: tables are nodes, relationships are edges from the many side to the one side, and every edge
carries a certainty from its rule (declared or confirmed 1.0; checked against the data 0.9; R1 0.8; R2 0.6; R3 and
R4 0.5). `fabric_backend/graphs.py` is plain Python and deterministic: the same plan always gives the same answer.
What each method does for you, in plain terms:

- **Roles** (`analyze_schema`): a table that points at several others and nothing points at is a fact table; one that
  is pointed at and points at little is a dimension; a table whose key is just two references (a junction) is a bridge.
  The numbers that decided each role are in the answer, so you can disagree.
- **Centrality**: in/out degree says what a table refers to and what refers to it; betweenness says how often a
  table sits on the route between two others; PageRank on the directed graph says where the references end up
  (shared dimensions score high). The top ten is where to start reading an unknown schema.
- **Subject areas**: label propagation on the undirected graph groups tables that are more connected to each other
  than to the rest; each area is named after its most central table. A first cut at the domains in a lakehouse.
- **Ambiguity**: every relationship beyond a spanning forest closes a cycle, and any two tables on a cycle can be
  reached two ways. That is exactly what makes filter paths ambiguous in a Power BI model, so the answer lists the
  cycles and the pairs, and the maximum spanning forest (highest certainty first) says which relationships can be active
  at once; `semantic_model_draft` uses it for active/inactive.
- **Paths** (`join_path`): the shortest path counts hops; the safest path (Dijkstra on cost = 1/certainty) prefers
  declared and R1 links. When they differ the answer says why.
- **Link prediction** (`suggest_relationships`): a column with a reference suffix and the type of another table's
  key, in no relationship yet, is a candidate; a name that resembles the target, or a target the table already
  reaches in two hops, ranks it higher; then the data decides — the share of its values that exist in the target key.
  Nothing is applied; you pass the suggestion you accept as `confirmed`.

Unit-tested on the synthetic shop schema and the public benchmark schemas; `analyze_schema` and `suggest_relationships`
were run against the demo workspace (synthetic shop data) on 26 October 2026: the one column outside every relationship, `orders.ship_to_id`, came back with
every value present in `addresses.address_id` (15 distinct values) and well below that for the other candidates. On
27 October 2026, after the ranking was fixed, `addresses.address_id` came first before the data check (3.94 against
1.5 or less) and held for every value after it (inclusion 1.0). The [guided demo](/check?example=sample&guide=1) walks through this column on the
synthetic sample: the suggestion, its data check and the decision that stays yours.

### SAP on Fabric

SAP tables do not follow general naming rules: `VBAP.VBELN` is the order an item belongs to, `LIPS.VBELN` a delivery,
`VBRP.VBELN` an invoice, and every key starts with the client `MANDT`. For these tables Krusgraph uses its SAP pack:
declarative files with the keys and the order-to-cash relationships of `KNA1`, `KNVV`, `MARA`, `MAKT`, `TVKO`, `VBAK`,
`VBAP`, `VBEP`, `VBPA`, `LIKP`, `LIPS`, `VBRK`, `VBRP`, `VBFA`, and the procure-to-pay relationships of `LFA1`, `EBAN`, `EKKO`, `EKPO`, `EKET`, `EKBE`, `RBKP`, `RSEG`, and the finance relationships of `BKPF`, `BSEG`, `ACDOCA`, `SKA1`, `SKB1`, `BSID`, `BSIK`, `CSKS`, the pricing conditions `KONV`/`PRCD_ELEMENTS`, and the business partner `BUT000` with its links to customers and suppliers, each with the public source it rests
on, for ECC and S/4HANA. It does not depend on how the tables arrive: Fabric mirroring of SAP (through SAP
Datasphere), Databricks, a pipeline of your own; names are recognised with or without a prefix (`VBAK`, `vbak`,
`sap_vbak`). Every relationship it adds carries the rule `SAP pack`; `sap_pack_draft` shows what it recognises and
what is missing, and `validate_plan` checks it against the rows, because a pack is a sourced suggestion, not proof.

A synthetic example (no data from any SAP system):

```
plan_backend(workspace="demo", source="sap_lh", schema="sap")
  sap_vbap.mandt+vbeln          -> sap_vbak.mandt+vbeln          SAP pack   (item to its order)
  sap_vbep.mandt+vbeln+posnr    -> sap_vbap.mandt+vbeln+posnr    SAP pack   (schedule line to its item)
  sap_lips.mandt+vgbel+vgpos    -> sap_vbap.mandt+vbeln+posnr    SAP pack   (delivery item to the order item)
  sap_vbrk.mandt+kunrg          -> sap_kna1.mandt+kunnr          SAP pack   (payer, not the sold-to party)
  sap_vbfa                      listed, not applied: many-to-many document flow
validate_plan(...) -> amount_levels: sap_vbak.netwr is repeated on every sap_vbap row in a join of the two
```

On the synthetic SAP schema of the tests, the name rules alone find none of the 117 relationships. Given every key,
they find most of them but also 26 joins that read a document number as another kind of document (a delivery number
as an order, an invoice number as an accounting document); the pack applies none of those. The schema is generated
from the pack, so this shows what the pack adds over the name rules, not that the pack is right about SAP
([measurement](https://github.com/Krusmaster/fabric-backend/blob/main/docs/INFERENCE.md)). It has not been run against
an SAP system or a real installation. Contents, sources and how to contribute:
[docs/SAP.md](https://github.com/Krusmaster/fabric-backend/blob/main/docs/SAP.md).

## Build from a plan

What you can build once the plan is reviewed. Each tool's status is in the [tool reference](#test-status).

### One plan, five Fabric pieces

Everything {{PRODUCT}} creates comes from one plan: the keys and relationships inferred from a source, with the rule behind
each one, checked against the rows when you run the checks, and corrected by you through `keys` and `confirmed`. From that plan:
`create_backend` makes the **API for GraphQL** with nested relationships (a dry run first, as with the others; `plan_drift`
shows what an update would change); `create_views` the **wide T-SQL views** on the SQL analytics endpoint;
`create_semantic_model` the **Power BI semantic model** in Direct Lake mode with the same relationships,
`create_ontology` the **Fabric IQ ontology** with entity types, keys, relationship types and bindings, and
`create_data_agent` the **data agent** with the plan as instructions and examples. Those four answer with a dry run
first; how far each has created live, in the words of the [tool reference](#test-status): the views ({{SHORT_CREATE_VIEWS}}),
the semantic model ({{SHORT_CREATE_SEMANTIC_MODEL}}), the ontology ({{SHORT_CREATE_ONTOLOGY}}) and the data agent
({{SHORT_CREATE_DATA_AGENT}}). Change the plan once (a confirmed relationship, a key) and every piece is rebuilt from it; `plan_drift` and
`lineage` tell you what a change reaches. The pieces agree with each other because none of them was modelled by hand.

From the same plan, further down the lakehouse: `silver_notebook_draft` writes de-duplicated silver tables with every
reference checked, and `gold_views_draft` the **gold views** on top of them, as materialized lake views (generally
available in Fabric since September 2026) whose data quality rules are the plan's keys and relationships. A model you
already have is checked against the plan with `compare_semantic_model`. And when changes go through Git rather than
straight into the workspace, `export_item_definitions` gives every piece as the files Fabric's Git integration reads.

### Create a dbt flow

`dbt_schema` with `project=true` writes a dbt project as files, for dbt-fabric 1.12 on dbt-core 1.12 and a Fabric
Warehouse; it creates nothing and runs no dbt. With `check_rows=true` the keys and relationships are counted first,
and the project is built from that checked plan:

- `dbt_project.yml`, `profiles.example.yml` (placeholders and `authentication: CLI`, no secret) and a `README.md` that
  says how to run it (`dbt debug`, `dbt parse`, then `dbt build`, the step that changes the Warehouse).
- `models/sources/`: the source tables with `unique` and `not_null` on single-column keys and `relationships` on
  single-column relationships.
- `models/staging/`: one view per table, columns renamed to snake_case (the README lists the renames), cast to a Fabric
  Warehouse type only where the metadata gives one, and de-duplicated on the key.
- `models/marts/`: a table per fact table, joined only over relationships whose target key was counted unique; the
  others are left out and listed with the reason. A header amount is never in a mart at line grain, and child rows are
  summed to the header before the join.
- `tests/`: a key or a relationship over several columns as a singular test. dbt_utils' `unique_combination_of_columns`
  is not used, because dbt-fabric's documentation says dbt-utils is not supported; no package is needed.

`fixes` takes the ids accepted from `validate_plan(fixes=true)` (see *Fix data issues*) and writes them as staging
logic: the latest row by the accepted column, a row whose reference has no parent left out (a NULL reference is kept),
or the reference set to NULL with `{"id": ..., "choice": "set_null"}`. Moving a header amount stays with the silver
notebook. The SQL of each file is checked to parse as T-SQL and the YAML to load, in unit tests on the shop example and
the /check datasets (tests/test_n156_dbt_flow.py, 8 November 2026); dbt itself has not been run on these files.

### Fabric IQ: the same graph as an ontology

Fabric IQ's **ontology (preview)** item describes a business as entity types with properties and a key, relationship
types between them, and data bindings to tables. That is the information {{PRODUCT}} already infers for a source, with
the rule behind every key and relationship. `ontology_draft` writes the plan in the ontology item's own shape, nothing deployed:

- a **summary** with what needs a hand (keyless tables, composite keys, composite-column relationships);
- a **binding checklist**: entity type → table, key column, property → column, relationship → columns, each with its rule;
- a **Turtle file** the portal's *Import ontology* accepts into an empty ontology item, using the mappings Microsoft documents
  for import (`owl:Class` → entity type, `owl:DatatypeProperty` → property, `owl:ObjectProperty` → relationship type,
  `rdfs:label`, `rdfs:comment`, `skos:altLabel` → display name, description, synonym); bindings are then done in the portal
  following the checklist;
- the **item definition** (generation 2, TMDL parts) that `POST /workspaces/{id}/ontologies` and Git integration take,
  with tables bound DirectLake-style to the source, entities with keys and properties, and the relationships.

Creating the item through the API needs the delegated scope `Item.ReadWrite.All` and Contributor on the workspace,
and the workspace on a Fabric capacity (`POST /workspaces/{id}/ontologies`, `updateDefinition`; Microsoft's REST
specification, read 26 October 2026). `create_ontology` does that with a dry run by default (creating the item: {{SHORT_CREATE_ONTOLOGY}});
without the permission it answers `consent` naming the scope when asked to create. The portal route (Import ontology
with the Turtle file) needs nothing beyond what you already have. Once an ontology exists, Fabric IQ's own pieces take
over: the ontology agent and data agents use it as context, and the built-in graph can be materialised from its entity
and relationship types. Ontology is in preview and its definition format can change; the draft follows the item's own
definition as of 2026, checked against recorded definitions and, through `create_ontology`, against Fabric itself
({{SHORT_CREATE_ONTOLOGY}}).

**Why not just Fabric IQ / the Fabric ontology?** The ontology (preview) item is where the plan lands. Microsoft Learn
describes three ways to fill one: by hand, generated from an existing Power BI semantic model (which then already carries
the relationships), or with the ontology agent, which "explores the workspace items you point it to", "samples a few rows
per table", drafts entity types, relationships and bindings "grounded in the discovered evidence" and "runs structural and
grounding checks on the draft" ([What is Fabric IQ?](https://learn.microsoft.com/en-us/fabric/iq/overview),
[What is ontology (preview)?](https://learn.microsoft.com/en-us/fabric/iq/ontology/overview),
[Use the ontology agent (preview)](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-ontology-agent); read
from the documentation's source repository on 1 November 2026). {{PRODUCT}} creates the ontology item; the evidence step
comes before it: `plan_backend` names the rule behind every key and relationship, `validate_plan` counts duplicate key
values, references with no matching row and the total that doubles against the rows, `suggest_relationships` checks
candidates against the data, and you decide with `keys=` and `confirmed=`; [/check](/check) does the plan and the counting
in the browser, with no account and no capacity. The same reviewed plan then becomes the ontology item (`create_ontology`:
{{SHORT_CREATE_ONTOLOGY}}) and, from one plan, the API for GraphQL, the semantic model and the notebooks. {{PRODUCT}} does
not replace the ontology item, its agent, its rules or its metrics, and the ontology agent's checks have not been compared
with `validate_plan` on the same data: no such measurement exists.

### Two steps stay manual

Fabric has no API for these yet, and the connector tells you when they are needed:

1. **Introspection** on the GraphQL item (item → Settings → Introspection) — needed by tools such as Lovable that read the schema.
2. **Permissions** on the item for other apps or service principals that should query it.

### App access

An app built on the API for GraphQL does not use your {{PRODUCT}} sign-in. It calls the API with its own identity,
usually a Microsoft Entra service principal (the route `app_starter` drafts), and what it can read depends on two
settings in Fabric:

- **Who may call the API.** The app's identity needs *Run Queries and Mutations* on the item (the second manual step
  above), and for a service principal the tenant setting that lets service principals use Fabric APIs.
- **Which identity reads the data.** The API connects to its source either with **single sign-on**, where each caller's
  own identity reads the source and that caller's permissions (row-level security defined on the source included)
  apply, or with **saved credentials**, where one stored identity reads the source for every caller. With saved
  credentials a caller needs only access to the API, so **the app's users can see data they have no permission to read
  themselves.** {{PRODUCT}} does not set this; check it in the item's settings in the Fabric portal before you publish an app.

The API for GraphQL has no row-level security of its own. Restrict rows at the source and use single sign-on, or
expose only views that hold the rows the app may show. `app_readiness` lists what it can read about an API and marks the
permissions as "unknown" with the portal path, because the Fabric API does not return them.

### Use with Lovable

Lovable meets {{PRODUCT}} twice. In Lovable's chat, {{PRODUCT}} is a custom MCP connector{{#IF CLIENT_REGISTRATION}} at `{{CONNECT_URL}}`{{/IF}} that plans,
checks and creates the API for GraphQL item (Lovable as an MCP client: {{LOVABLE_MCP_STATUS}}). Then Lovable's own
Microsoft Fabric connector reads that item with a service principal, after the introspection and permission steps above
and an app registration in Entra ({{LOVABLE_API_STATUS}}). Step by step: [Use {{PRODUCT}} with Lovable](/lovable). `app_readiness`
says what is still missing on the API; `app_starter` gives the prompt, the queries and a Supabase edge function that
keeps the app's Entra secret on the server side. The whole chain, with who does each step and what still blocks, is in
the repository's `docs/LOVABLE-END-TO-END.md`.

A live example: [Shop Desk](https://demo.krusgraph.com), built in Lovable, reads synthetic data in the demo workspace
through a read-only API for GraphQL that `create_backend` made.

### Databricks (Draft only)

The same engine reads Databricks too, in the local server only (`KRUSGRAPH_PLATFORM=databricks`): a Unity Catalog
schema through its `information_schema`, where declared primary and foreign keys count as K0 and R0 and column tags feed
the personal-data rules; the checks run as counting queries on a SQL warehouse. From the same plan it drafts
informational constraints (with `RELY` only where the counts hold), views, a Lakeflow pipeline whose expectations are
the plan's keys and relationships, metric views and a bundle. **Draft only:** unit-tested with Databricks mocked, not
yet run against a Databricks workspace. The hosted service at {{DOMAIN}} reads Fabric only. Set-up, the status of each tool
and the documentation each draft rests on: [docs/DATABRICKS.md](https://github.com/Krusmaster/fabric-backend/blob/main/docs/DATABRICKS.md).
Databricks' own managed MCP servers (Genie, Databricks SQL, Unity Catalog functions) answer questions and run SQL;
{{PRODUCT}} is the part that works out how the tables relate. {{PRODUCT}} is not affiliated with Databricks.

## Krusgraph in Fabric

{{PRODUCT}} also comes as an item inside Microsoft Fabric: **Krusgraph Model**. It is the same engine as the connector
in Claude, without a chat: you click through the review and the build in Fabric's own editor. It uses **no AI model**:
the keys and links come from the engine's named rules, the checks count your rows, and nothing goes to an AI provider.
A data agent it creates is Fabric's own item, and Fabric's AI answers there when someone asks it.

Today it is a pilot for selected organisations (Fabric allows up to 20 tenants for a workload that is not listed yet),
on request. A listing in Fabric's Workload Hub is planned and not available. Which of the four ways to use
{{PRODUCT}} suits you: [Which Krusgraph should I use?](/choose)

### What the Krusgraph Model item does

You create it with **+ New item → Krusgraph Model** in a workspace on a Fabric capacity. Then, in order:

1. **Choose a lakehouse and a schema.** The schema is picked from a list of the lakehouse's schemas, each with its
   number of tables.
2. **Review.** The proposed keys and links, each with the rule that found it (K0–K5, R0–R5) and what the rule means.
   Accept or reject each one, or **Accept all**. A rejection is never overturned by Accept all.
3. **Check against the rows.** Counting queries on the reviewed plan, as you: each key and link comes back passed,
   failed (with its orphans, duplicates or empty values) or not checked. Counts only, never a row value.
4. **The map and the mascots.** The tables and their links drawn as on the cards in Claude; **List** shows the same as
   rows for the keyboard and screen readers. Onto says the numbers, Thinker the check and the questions, Builder what
   comes next; a switch turns them off and their sentences become plain text.
5. **Choose what to build**: silver notebook, gold views, pipeline, semantic model, report, API for GraphQL, ontology
   and data agent, each with its name and the permission it needs, and optionally a **data product** over them.
6. **Dry run.** One card per output, made by that output's own tool, saying what it would create or update. Nothing is
   written yet. An item of the same name that this Model did not build is never written over.
7. **Create.** One output at a time, each card with its own result and **Open in Fabric**. The **data flow** is drawn:
   source tables, silver, gold and what is built on them; a box opens to show its code (the notebook cell, the SQL of
   a view, the pipeline step, the model's relationships and measures), exactly what was sent.

Nothing is run or scheduled: you run the notebooks or the pipeline yourself, refresh the semantic model once and turn
on introspection on the API, as each card says.

<!-- figure:shot-model-review -->
<!-- /figure -->

<!-- figure:shot-model-outputs -->
<!-- /figure -->

<!-- figure:shot-model-preview-cards -->
<!-- /figure -->

<!-- figure:shot-model-flow -->
<!-- /figure -->

### Add it to your Fabric

Today: ask for the pilot. Your administrator sends us your tenant id, turns on the tenant setting for workloads not
validated by Microsoft, grants admin consent for the workload app once and allows two addresses through the network.
The steps, in order, are on [Pilot in Microsoft Fabric](/pilot/fabric). After that anyone in the pilot creates a
**Krusgraph Model** with **+ New item**.

- **Workload Hub listing:** planned, not available. Until then the item shows only in organisations in the pilot.
- **What it needs:** a workspace on a Fabric capacity (it does not run on Power BI Pro alone), and it is blocked where
  Private Link is on.
- **Cost:** not on [Pricing](/pricing) yet; the pilot is agreed with you.

### Permissions in plain words

Every call runs as the person using the editor, with that person's own Fabric rights: {{PRODUCT}} can read and create
only what that person can. Your administrator consents once for the workload's Entra app. Reading the lakehouse's
tables and counting the checks uses the lakehouse's SQL endpoint as that person; building an output needs the
permission in this table on the person's sign-in. When one is missing, the dry run says so and Create refuses that
output, with the steps for your administrator.

<!-- figure:workload-permissions -->
<!-- /figure -->

The item never deletes anything, never runs or schedules a notebook or pipeline, and keeps no table contents. What is
stored and for how long is on [For your IT department](/it#permissions); to withdraw consent, your administrator
removes the app under **Enterprise applications** in Entra.

### Network hosts

The editor that Fabric shows comes from our own host. If outbound web traffic is filtered, allow HTTPS (port 443,
TLS 1.2 or later) to:

| Host | What it is for |
| --- | --- |
| `workload.krusgraph.com` | The Krusgraph Model editor in Fabric's frame, and the engine it calls, as the signed-in person |
| `krusgraph.com` | The docs, help, privacy and terms pages the item links to |

Both are hosted in Azure, Sweden Central. Fabric (`app.fabric.microsoft.com`) and Microsoft sign-in
(`login.microsoftonline.com`) must be reachable as for any use of Fabric. More: [Network: hosts to allow](/it#network).

### Troubleshooting

| You see | What to do |
| --- | --- |
| Krusgraph Model keeps loading, or `ERR_SSL_VERSION_OR_CIPHER_MISMATCH` for `workload.krusgraph.com` | A web filter blocks a domain it does not know yet. Ask IT to allow the two [network hosts](/docs/krusgraph-in-fabric/network-hosts), then reload the Fabric tab. |
| Krusgraph Model is not under + New item | Your organisation is not in the pilot yet, the tenant setting for workloads not validated by Microsoft is off for you, or the workspace is not on a capacity. [Pilot in Microsoft Fabric](/pilot/fabric) has the steps. |
| "{{PRODUCT}} is not turned on for your organisation yet." | Your tenant id is not on the pilot's list yet. Nothing was read or changed. Write to us with the tenant id it shows. |
| A card says `consent` | Your sign-in lacks the permission the card names. Your administrator adds it to the workload's Entra app and consents; the card lists the steps. Then reload the Fabric tab. |
| The schema list is empty, or a schema shows "no tables" | The lakehouse has no tables in that schema, or you cannot read its SQL endpoint. Choose a schema with tables; when the list cannot be read, the editor says why and lets you type the name. |
| `schema_ambiguous` | Two schemas differ only by case (`Shop` and `shop`). Type the one you mean exactly as listed. |
| A card says "no answer yet" after Create | Fabric may still be creating it. Reopen the item in a minute and choose Create again: what was built is skipped. |
| `already_exists` on a card | An item of that name exists and this Model did not build it. Choose another name. |

## Tool reference

The status words, then each tool: what it reads, returns or changes.

### Test status

Each tool in the table below carries one of these. They come from one list of fields per tool (where it is available,
what it changes, how it is tested and whether it ran live; `fabric_backend/tool_status.py`), so a tool has the same
status on every page. *Draft only* says what a tool changes, *Tested end to end* how far it has been run: a draft tool
that ran live is listed as tested, and its *What it changes* column says it creates nothing.

- **Tested end to end** — run from Claude as a custom connector, through Microsoft sign-in, against a Fabric workspace
  with synthetic data (an F2 capacity, the lakehouse `demo_lh` with the shop schema from `fabric_backend/seed.py`) on
  {{LIVE_RUN_DATE}}, through the hosted server's build {{LIVE_RUN_BUILD}}, read-only, as drafts or as dry runs, and
  then, with the maintainer's approval, one creating call that updated an existing API in place: {{LIVE_RUN_LIST}}. A draft that ran so is marked *(a draft; creates nothing)*, a creating tool
  whose dry run ran *tested end to end as a dry run*; creating keeps its own status. Not run that day, not even as a
  dry run: {{NOT_RUN_LIST}}. The first such run was on {{FIRST_RUN_DATE}} ({{FIRST_RUN_STEPS}} steps). Changes made
  after the run are covered by unit tests.
- **Tried live** — an operation of the tool ran against a live target after that run, or ran only part of the way
  that day: for the hosted tools a Fabric workspace with synthetic data, for the local tools SQL Server 2022 in a
  container. The overview below gives each tool's last operation tried live, its date, its result and what is still
  open, as separate fields.
- **Experimental** — unit-tested, never run against a live target.
- **Draft only** — returns a draft or files and creates nothing in Fabric.
- **Available when enabled by the operator** — needs a permission the hosted app does not request. No tool has this
  status today: the app has every permission the tools use ([What it accesses](#what-it-accesses)), except the drift
  monitor's schedule (`DataPipeline.Execute.All`), which is why `create_drift_monitor` has `schedule=false` by default.
- **Planned** — not available yet, such as the Claude plugin (see *For agents*).

### Overview: tools, functions and clients

Each tool, each function outside the hosted tools, and each client, with its status and where it runs: *hosted*
(krusgraph.com), *local* (the stdio server `fabric-backend-mcp` on your machine), *local demo* (`fabric-backend demo`)
or *library* (the Python package in your own scripts or notebooks). Generated from the same source as the tool table
below and the server's instructions.

{{OVERVIEW_TABLE}}

### Tools

All tools take the workspace by id or display name. `schema` defaults to `dbo`; `keys` overrides a table's key
(`{"order_items": ["order_id", "line_no"]}`), `confirmed` adds relationships the rules did not make
(`[{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}]`),
`tables` limits what is built. A `confirmed` entry can also name the relationship's two GraphQL fields: `field_name`
on the source (`"address"`: `orders.address`) and `reverse_name` on the target (`"orders"`: `addresses.orders`); without
them the rules name the fields (`ship_to` and `orders_as_ship_to` here). When an API of that name exists, `create_backend`
and `plan_drift` keep the field names it already has for the same relationship (the same columns in the same direction)
unless `confirmed` names them otherwise, and their `keep_with_confirmed` entries carry both names.

| Tool | Status | What it changes | Does | Arguments |
| --- | --- | --- | --- | --- |
| `list_workspaces` | {{status}} | {{changes}} | the workspaces the signed-in account can see, with id, name and capacity | — |
| `list_sources` | {{status}} | {{changes}} | lakehouses, warehouses, SQL databases, Snowflake databases, mirrored databases and catalogs in the workspace, plus existing API for GraphQL items | `workspace` |
| `list_tables` | {{status}} | {{changes}} | tables and columns with types in one schema; `tables` narrows to names or patterns (`["sales_*"]`), `detail` is `auto` (full up to 60 tables, then the column count per table), `full` or `summary` | `workspace`, `source`, `schema`, `tables`, `detail` |
| `plan_backend` | {{status}} | {{changes}} | inferred keys and relationships, each with its rule, ambiguous columns, keyless tables, suggested composite keys, the names read through the synonym table (`synonyms`), a Mermaid ER diagram; rule R5 counts code and role columns the names left unlinked against the rows (the first {{R5_SAMPLE}} distinct values per candidate, at most {{R5_MAX_QUERIES}} counting queries; `counted_in_rows` says what it took and what was left); `tables` narrows the answer to names or patterns while the plan is still made from the whole schema, `detail` is `auto` (full up to 60 tables, then one line per key and relationship without field names or diagram), `full` or `summary`, `mermaid=false` leaves the diagram out; every answer stays under 60 000 characters and says when it was cut | `workspace`, `source`, `schema`, `keys`, `confirmed`, `tables`, `detail` |
| `validate_plan` | {{status}} | {{changes}} | checks the plan against the rows: is each key unique and free of NULLs, does every reference find its target (orphan count); one small counting query per key and relationship over the whole table, up to `max_items` of them (default {{VALIDATE_MAX_ITEMS}}; the summary says when fewer than the plan has were checked); returns counts and a verdict, no row values; by default a summary (totals, and every failing or not-counted check in full), `detail="full"` for every check; `fixes=true` adds a proposed fix per finding ([Fix data issues](#fix-data-issues)) and applies nothing | `workspace`, `source`, `schema`, `keys`, `confirmed`, `max_items`, `detail`, `fixes`, `review`, `tables` |
| `sample_rows` | {{status}} | {{changes}} | the first n rows (at most 20) of one table, long text shortened, to check what a column means; columns that look like personal data come back as `***` with the rule, and the source's sensitivity label is named | `workspace`, `source`, `table`, `schema`, `n`, `show_personal_data` |
| `create_backend` | {{status}} | {{changes}} | creates the API for GraphQL item with nested relationships, or updates the item of that name in place, keeping the field names it has for the same relationships; refuses an update that would drop relationships the API has unless `allow_removals=true`, and names the `confirmed` entries (with `field_name` and `reverse_name`) that keep them; returns the endpoint and the two portal steps; `dry_run=true` (default) returns what would be created or updated instead; it does not run `validate_plan` | `workspace`, `source`, `name`, `schema`, `writable`, `keys`, `confirmed`, `tables`, `allow_removals`, `dry_run` |
| `describe_backend` | {{status}} | {{changes}} | types, fields and relationships of an existing API for GraphQL item, in the names a query uses, read from its definition (no introspection needed) | `workspace`, `api` |
| `query_graphql` | {{status}} | {{changes}} | runs a read-only GraphQL query against an API (name or id); mutations are refused; with `question`, `tables` and `source` instead of `query` it builds the query `answer_query_draft` suggests, runs it, and shows it beside the result | `workspace`, `api`, `query`, `variables`, `question`, `tables`, `source`, `schema` |
| `rayfin_connector` | {{status}} | {{changes}} | Rayfin (Fabric Apps) connector entity classes and `schema.ts` | `workspace`, `source`, `connector`, `schema`, `keys`, `confirmed`, `tables`, `relationships` |
| `ontology_draft` | {{status}} | {{changes}} | the plan as a Fabric IQ ontology (preview) draft: summary, binding checklist, a Turtle file for the portal import, the item definition | `workspace`, `source`, `name`, `schema`, `keys`, `confirmed`, `tables` |
| `semantic_model_draft` | {{status}} | {{changes}} | a Power BI semantic model in TMDL (`definition/` files) with suggested measures (the row count of each fact table, sums only where `summarizeBy` sums, each with its reason) and a calendar marked as the date table when fact tables have date columns: one Direct Lake table per source table on the SQL analytics endpoint, relationships with cardinality and one active path per table pair, keyless tables unrelated, `README.generated.md` with every decision to check; unit-tested against Microsoft's sample definitions | `workspace`, `source`, `name`, `schema`, `keys`, `confirmed`, `tables` |
| `join_path` | {{status}} | {{changes}} | the shortest chain of relationships between two tables with the rule per hop and a ready T-SQL `SELECT … JOIN …`; equally short paths all listed; with no path, which relationship is missing as a `confirmed` entry | `workspace`, `source`, `start`, `end`, `schema`, `keys`, `confirmed` |
| `data_dictionary` | {{status}} | {{changes}} | hand-over documentation in Markdown: tables, columns and types, keys and relationships with rules, keyless and ambiguous items, the ER diagram, an empty Description column; `validate=true` adds the counts from `validate_plan`; `tables` (names or patterns) documents one part of a large schema at a time, with the roles and subject areas of the whole schema, and an answer over 60 000 characters is cut on a line and says so | `workspace`, `source`, `schema`, `keys`, `confirmed`, `validate`, `max_items`, `tables` |
| `dbt_schema` | {{status}} | {{changes}} | a dbt `schema.yml` with sources: `unique` and `not_null` on key columns, `relationships` on single-column relationships, in the syntax of the dbt documentation; composite keys noted as comments; `tables` takes names or patterns, an answer over 60 000 characters is cut and says so; `project=true` writes a whole dbt project ([Create a dbt flow](#create-a-dbt-flow)), with `fixes` as staging logic | `workspace`, `source`, `schema`, `source_name`, `keys`, `confirmed`, `tables`, `arguments_block`, `project`, `check_rows`, `quality`, `profile`, `fixes` |
| `domain_draft` | {{status}} | {{changes}} | proposed domains (candidate data products) from the plan's graph: deterministic Leiden-style communities weighted by each relationship's rule, a name and a reason per table, the relationships that cross domains (interfaces), unassigned tables, and one ODCS v3.2.0 contract per domain; the customer's Fabric admin creates the domains | `workspace`, `source`, `schema`, `confirmed`, `check_rows` (inferred keys) |
| `sap_pack_draft` | {{status}} | {{changes}} | which tables the SAP pack recognises (with or without a prefix such as `sap_`), their keys with `MANDT`, the order-to-cash relationships it applies with the public source of each, what it lists but does not apply (`VBFA` is many-to-many), what is missing, and the traps; optionally one export: Krusgraph keys/confirmed, Data API builder config, an extraction list with open-mirroring `keyColumns`, or dbt sources. See [SAP on Fabric](#sap-on-fabric) | `workspace`, `source`, `schema`, `keys`, `confirmed`, `variant`, `export` |
| `plan_drift` | {{status}} | {{changes}} | today's plan against an existing API for GraphQL item: new tables and columns, columns the API still maps that are gone, relationships the plan no longer supports, and whether `create_backend` with that name would change anything | `workspace`, `source`, `api`, `schema`, `keys`, `confirmed`, `tables`, `writable` |
| `create_semantic_model` | {{status}} | {{changes}} | creates a Power BI semantic model item from the TMDL draft (Direct Lake on the SQL analytics endpoint) or updates the one of that name in place; it reads two counts first (read-only): the first and last date of the columns the date table relates to, so the calendar spans the data's whole years, and whether a quantity column of a decimal type holds whole numbers, so its sum is formatted `#,0` like a row count (`read_from_rows` says what was read); `dry_run=true` (default) returns the parts and the REST call only; needs `SemanticModel.ReadWrite.All` or `Item.ReadWrite.All` | `workspace`, `source`, `name`, `schema`, `keys`, `confirmed`, `tables`, `dry_run` |
| `create_report` | {{status}} | {{changes}} | creates a Power BI report item bound to an existing semantic model, with one page drawn from the model's own measures and columns (a PBIR definition built from the model's TMDL): cards for the row counts of business tables and the units, a clustered column chart by the date table's Year Month (or Month), a clustered bar chart by the most-referenced dimension and a table of the nearest dimension sorted by a measure with a total row; plain titles ("Orders", "Units by category"; other measures keep their names), a grid over 1280 × 720, a page title and a dated footnote, data labels, month and category slicers when those fields exist, and the Krusgraph theme (round n151); a plain SUM of a column the model does not sum, or of a header amount copied onto lines, is never drawn (`left_out` says why), and when nothing can be drawn the page is left blank; `empty_page=true` creates one blank page through Fabric's `creationPayload` and reads nothing of the model; a report of that name is left alone and the call answers `kind: already_exists`; `dry_run=true` (default) returns the REST call only; needs `Report.ReadWrite.All` or `Item.ReadWrite.All`, and `SemanticModel.ReadWrite.All` to read the model; the page with visuals was created in Fabric on 7 November 2026; its n151 look is validated against Microsoft's published PBIR schemas and has not run live | `workspace`, `model`, `name`, `empty_page`, `dry_run` |
| `create_views` | {{status}} | {{changes}} | `CREATE OR ALTER VIEW` in a schema of its own (default `krusgraph`, created if missing) on the source's SQL analytics endpoint or warehouse: one wide view per fact table with its dimensions, one per header table (`vw_orders`: each order with its customer and, once `orders.ship_to_id` is confirmed, its ship-to address), one per hard-to-read relationship; `dry_run=true` returns the SQL; needs the SQL right to create objects (Contributor) | `workspace`, `source`, `schema`, `views_schema`, `keys`, `confirmed`, `dry_run` |
| `create_data_agent` | {{status}} | {{changes}} | creates or updates a Fabric data agent through the staging REST API: the plan as instructions, the source as data source with the plan's tables selected, 5–10 question/T-SQL examples, then publishes; columns that look like personal data are left out of the instructions and the examples unless `show_personal_data=true` (the key stands in); `dry_run=true` returns instructions, examples and the calls; needs `Item.ReadWrite.All` | `workspace`, `source`, `name`, `schema`, `keys`, `confirmed`, `publish`, `show_personal_data`, `dry_run` |
| `create_ontology` | {{status}} | {{changes}} | creates a Fabric IQ ontology (preview) item from the plan or updates the one of that name in place: entity types with keys and properties, relationship types and Direct Lake-style bindings in the item's generation-2 definition; `dry_run=true` (default) returns the parts and the REST call only; needs `Item.ReadWrite.All` and Contributor on the workspace (`POST /workspaces/{id}/ontologies`, `updateDefinition`; fabric-rest-api-specs read 26 October 2026) | `workspace`, `source`, `name`, `schema`, `keys`, `confirmed`, `tables`, `dry_run` |
| `app_starter` | {{status}} | {{changes}} | from an existing API's definition: a Lovable prompt with the data model and main views, a connection description, five GraphQL queries walking the relationships, the portal checklist, and the backend an app needs so that no secret reaches the browser: a Supabase edge function (service principal, client credentials, secrets as Supabase secrets), the frontend helper, and the per-user alternative | `workspace`, `api` |
| `app_readiness` | {{status}} | {{changes}} | what an app still needs on an existing API: types without a key, types in no relationship, write access (from the definition), whether introspection is on (one introspection query to the endpoint), and "unknown" with the portal path for what the Fabric API cannot read (permissions, the tenant setting for service principals); a next step per item | `workspace`, `api` |
| `analyze_schema` | {{status}} | {{changes}} | the plan as a graph, metadata only (`tables` and `detail` as in `plan_backend`; the summary groups tables by role and keeps the central tables, the areas by size and counts): table roles (fact, dimension, bridge, isolated) with the numbers behind them, the ten most central tables (degree, betweenness, PageRank), subject areas, cycles and table pairs with more than one path, and which relationships can be active at once | `workspace`, `source`, `schema`, `keys`, `confirmed`, `tables`, `detail` |
| `lineage` | {{status}} | {{changes}} | which objects in the workspace build on the source's tables: GraphQL APIs (from their definition), semantic models (from their TMDL definition), views on the SQL analytics endpoint (`INFORMATION_SCHEMA.VIEW_TABLE_USAGE`), data agents (named in their definition, marked as not certain); a graph of tables and objects, the objects per table, the tables used by nothing, the items that could not be read; with `table`, what a change to it reaches | `workspace`, `source`, `schema`, `table` |
| `silver_notebook_draft` | {{status}} | {{changes}} | a Fabric notebook (PySpark) that builds silver tables from a lakehouse's tables: de-duplicated on each table's key (the latest row by `order_by` wins), every relationship checked with the rows whose reference is missing put in `krusgraph_quarantine` with the reason, Delta tables written only in `silver_schema`, each step commented with its rule; re-runnable; `fixes` applies the fixes accepted from `validate_plan(fixes=true)` and adds a table of counts per fix. The steps and the notebook source | `workspace`, `source`, `schema`, `silver_schema`, `order_by`, `keys`, `confirmed`, `tables`, `fixes` |
| `create_silver_notebook` | {{status}} | {{changes}} | creates that notebook in the workspace, attached to the lakehouse, or updates the one of that name; creating runs nothing; `dry_run=true` (default) returns the notebook and the call; needs `Notebook.ReadWrite.All` or `Item.ReadWrite.All` (fabric-rest-api-specs `notebook/swagger.json`) | `workspace`, `source`, `name`, `schema`, `silver_schema`, `order_by`, `keys`, `confirmed`, `tables`, `fixes`, `dry_run` |
| `drift_monitor_draft` | {{status}} | {{changes}} | a notebook and a pipeline that every night read the lakehouse's schema, compare the plan with the last saved one (the `plan_drift` and `lineage` logic as a library), save the new plan in `krusgraph.plans`, and send a short summary to a webhook (Teams or Power Automate) set as a pipeline parameter in Fabric; plus the daily schedule; the notebook installs the library at the tag of the server's version unless `library_ref` names another tag, a commit or `main` | `workspace`, `source`, `schema`, `name`, `at`, `time_zone`, `library_ref` |
| `create_drift_monitor` | {{status}} | {{changes}} | creates or updates that notebook and pipeline and, with `schedule=true`, adds the daily schedule unless one at that time exists (`schedule=false` is the default, as the hosted app does not request `DataPipeline.Execute.All`); no secret anywhere; `dry_run=true` (default) returns the items and the calls; needs `Notebook.ReadWrite.All` and `DataPipeline.ReadWrite.All` (or `Item.ReadWrite.All`), and `DataPipeline.Execute.All` (or `Item.Execute.All`) for the schedule | `workspace`, `source`, `name`, `schema`, `at`, `time_zone`, `library_ref`, `schedule`, `dry_run` |
| `answer_query_draft` | {{status}} | {{changes}} | a question in Swedish or English about the given tables as T-SQL over the safest join path (each step with its rule), and with `api` as GraphQL in that API's field names, or why GraphQL cannot answer it; reads counts, sums, averages, "per"/"för varje" groupings, top N and "latest", and lists what it assumed; runs nothing; columns that look like personal data are left out unless `show_personal_data=true` (the key stands in) | `workspace`, `source`, `question`, `tables`, `schema`, `api`, `keys`, `confirmed`, `show_personal_data` |
| `suggest_relationships` | {{status}} | {{changes}} | columns that could point at another table's key but are in no relationship, ranked by name, type and triangular closure, the best `check` counted against the data (inclusion share, distinct values); each with a ready `confirmed` entry; suggests only, never applies | `workspace`, `source`, `schema`, `keys`, `confirmed`, `check` |
| `compare_semantic_model` | {{status}} | {{changes}} | an existing semantic model (name or id) against the plan: relationships the model lacks, ones a rule or the data contradicts (with the rule or the count), other cardinality, filters in both directions, active against inactive, links the plan lacks (with a `confirmed` entry), columns summed that the `summarizeBy` rule would not sum, suggested measures it lacks; reads the model's TMDL through Fabric's getDefinition (needs `SemanticModel.ReadWrite.All` or `Item.ReadWrite.All`), or `tmdl` from a PBIP folder or Git, which needs nothing; `check_data=true` counts against the rows | `workspace`, `source`, `model`, `schema`, `keys`, `confirmed`, `check_data`, `max_items`, `tmdl` |
| `gold_views_draft` | {{status}} | {{changes}} | materialized lake views in Spark SQL for a lakehouse with schemas: one wide view per fact table in `gold_schema` over the silver tables, joined over the safest many-to-one paths, with `CONSTRAINT … CHECK … ON MISMATCH DROP` rules for the plan's keys and relationships, each commented with its rule; personal-data columns left out unless `show_personal_data=true`; the notebook that creates them | `workspace`, `source`, `schema`, `silver_schema`, `gold_schema`, `keys`, `confirmed`, `tables`, `show_personal_data` |
| `create_gold_views` | {{status}} | {{changes}} | creates that notebook in the workspace, attached to the lakehouse, or updates the one of that name; the views are created when the notebook runs, and it stops before a source table, a silver table or any table it did not create; `dry_run=true` (default) returns the views, the notebook and the call; needs `Notebook.ReadWrite.All` or `Item.ReadWrite.All` | `workspace`, `source`, `name`, `schema`, `silver_schema`, `gold_schema`, `keys`, `confirmed`, `tables`, `show_personal_data`, `dry_run` |
| `create_pipeline` | {{status}} | {{changes}} | creates or updates the silver and gold notebooks, a check notebook and a data pipeline that runs them in that order and stops on a failed check, as `export_item_definitions` drafts it with `items=["pipeline"]`; it neither runs nor schedules the pipeline; `dry_run=true` (default) returns the definitions and the calls; needs `Notebook.ReadWrite.All` and `DataPipeline.ReadWrite.All` (or `Item.ReadWrite.All`) | `workspace`, `source`, `name`, `schema`, `silver_schema`, `gold_schema`, `silver_name`, `gold_name`, `keys`, `confirmed`, `tables`, `show_personal_data`, `dry_run` |
| `export_item_definitions` | {{status}} | {{changes}} | what `create_backend`, `create_semantic_model`, `create_silver_notebook`, `create_drift_monitor` and `create_gold_views` would create, as folders in Fabric's Git format (`<name>.<type>` with `.platform` and the definition files), plus `create_views`' T-SQL as a script (Fabric's Git integration does not carry SQL analytics endpoint views) and a README; for your own repository, so that Fabric's Git integration or a deployment pipeline makes the change; calls no Git provider | `workspace`, `source`, `schema`, `items`, `names`, `keys`, `confirmed`, `tables`, `silver_schema`, `gold_schema`, `views_schema`, `writable`, `show_personal_data` |
| `review_plan` | {{status}} | {{changes}} | the plan with the decisions made about it and its checks as one JSON file for your own repository, plus a short Markdown report and what needs attention: each key and relationship with a review status (proposed, accepted, rejected, open, with a reason) and, apart from it, a check status (not checked, passed, failed, stale); `validate=true` records `validate_plan`'s counts with the time; `previous` takes an earlier file, applies its corrections again, lists what changed in the schema and marks checks on changed tables stale; names, types, rules, decisions and counts only, never row values or credentials | `workspace`, `source`, `schema`, `keys`, `confirmed`, `decisions`, `previous`, `validate`, `tables`, `max_items` |

When a call cannot be completed, the tool answers with three fields instead of a bare failure: `error` (what
happened, in plain words), `kind` (a stable code such as `not_found`, `no_access`, `capacity`, `sign_in`,
`consent`, `schema_not_found`, `table_not_found`, `bad_input`, `timeout`, or `rate_limited` with `retry_after` in seconds when
an account or organisation makes too many calls in a short time) and `hint` (what to do next). Tokens, request
headers and stack traces never appear in these answers. A query result too large for one answer comes back as valid
JSON with every list cut to its first items and a `truncated` note saying so; page with `first:`/`after` for the rest.

### For agents

A Markdown version of these docs is at [/docs.md](/docs.md); [/llms.txt](/llms.txt) lists the rest and
[/llms-full.txt](/llms-full.txt) has every page in one file. MCP clients can read the server's identity and transport
from its Server Card at `{{MCP_URL}}/server-card`, and the OAuth metadata at `/.well-known/oauth-protected-resource`.
Claude Code: {{CLAUDE_CODE_CONNECT}}
A Claude plugin that bundles this connector with a skill for the whole workflow and the commands `/krusgraph:plan`,
`/krusgraph:document` and `/krusgraph:explain-schema` is built and tested in the repository (`plugin/krusgraph`) and
coming soon (Planned); it is not published yet.

### With Microsoft's Fabric MCP servers

Microsoft publishes its own MCP servers for Fabric and Power BI. They manage workspaces and items, read files and run
queries; {{PRODUCT}} works out how your tables relate, with the rule behind every link, counts the checks you run against
the rows, and builds from that plan. Both can be added to the same client, each doing its own part:

- **Workspaces, items and OneLake files:** the local [Fabric MCP Server](https://github.com/microsoft/mcp/blob/main/servers/Fabric.Mcp.Server/README.md)
  ([Learn](https://learn.microsoft.com/fabric/onelake/onelake-local-mcp)) and the remote Fabric Core MCP server
  ([tools reference](https://learn.microsoft.com/rest/api/fabric/articles/mcp-servers/core-remote/tools-core-mcp-server)).
- **Questions to a Power BI semantic model or report:** [Fabric IQ MCP](https://learn.microsoft.com/fabric/iq/connectors/fabric-iq-mcp),
  read-only, with DAX queries under your own permissions.
- **Editing a semantic model:** the [Power BI Modeling MCP server](https://github.com/microsoft/powerbi-modeling-mcp).
- **T-SQL on a warehouse:** the [Fabric Data Warehouse MCP server](https://learn.microsoft.com/fabric/data-warehouse/data-warehouse-mcp-server) (preview).
- **Eventhouse and real-time data:** [Real-Time Intelligence MCP](https://learn.microsoft.com/fabric/real-time-intelligence/mcp-overview).
- **{{PRODUCT}}:** the plan (keys and relationships with their rules, and the checks you run against the rows) and what is built from it:
  the GraphQL API, the semantic model, views, silver and gold layers, drift monitoring, the item files for Git, and a
  check of an existing model against the plan.

A typical pairing: Microsoft's server finds the workspace and the lakehouse; {{PRODUCT}} plans it and drafts the model;
Fabric IQ MCP then answers questions on the model once it exists. {{PRODUCT}} is an independent open-source project of
Kruse Consulting AB and is not affiliated with Microsoft.

## Hosting and permissions

What the hosted server reads and asks for, and what to know when you run it yourself.

<!-- figure:hosting -->
{{CONCEPT_HOSTING}}
<!-- /figure -->

### What it accesses

The Entra app asks for delegated permissions only, all acting as the signed-in user. Each one, what the tools use it
for, and whether anything runs or is scheduled with it (the same table as on [/it](/it) and [/start](/start)):

{{ACCESS_SCOPES}}

Every creating tool is a dry run until you pass `dry_run=false`; then it creates or updates only the item named in the
call, and never deletes.

**The data path.** {{ACCESS_PLANNING}} `validate_plan` and `suggest_relationships` check keys and references against
the rows in Fabric with counting queries and return only the counts. {{ACCESS_CHECKS}} `sample_rows` returns up to 20 example rows of one table, and `query_graphql` returns the results you ask
for. `describe_backend`, `plan_drift`, `app_starter` and `lineage` read the definitions of items in the workspace.
Metadata, requested samples and query results pass through {{PRODUCT}} on their way to your MCP client and are not kept
after the request. From Claude, your tokens are exchanged on your behalf and held in memory only, never written to disk
or logs.{{#IF CLIENT_REGISTRATION}} From an MCP client other than Claude (signing in through {{DOMAIN}}/oauth), the Microsoft
tokens of a sign-in are kept encrypted in {{REGISTRATION_WHERE}} until your client collects them (at most 60 seconds), and
Microsoft's refresh token stays there encrypted for as long as your client keeps renewing its access, at most 90 days,
and is never given to the client; after each renewal the answer given (an access token and the next refresh token)
is kept there encrypted too, used for at most 60 seconds to answer the client again if it asks again ([sign-in from MCP clients other than Claude](/privacy#sign-in-from-mcp-clients-other-than-claude));
apart from those sign-in records there is no database and no file storage.{{/IF}}{{#IF NO_CLIENT_REGISTRATION}} There is no
database and no file storage.{{/IF}} Each tool call leaves an anonymous usage record (the tool, how the call ended, how long it took), and the
service writes technical logs. Details: [privacy policy](/privacy).

**Where the answers go.** Hosted or self-hosted, the AI client receives the tools' answers:

{{ACCESS_FLOWS}}

**Server-wide switches.** For a server you run yourself (hosted or local), two settings, both off by default: `KRUSGRAPH_READ_ONLY=1` leaves out the tools that create or change something in Fabric, and `KRUSGRAPH_NO_ROW_VALUES=1` leaves out `sample_rows` and removes row values from the other answers, keeping names and counts. A tool that is left out is not in the tool list, and `/healthz` names the mode the server runs in.

**Personal data and sensitivity labels.** Columns whose name looks like personal data are flagged by one rule per
pattern, from the name alone and never from the values: a person's name (P1: `first_name`, `last_name`, and `name` in a
table that holds people such as customers or employees), e-mail (P2), telephone (P3), national identity number (P4,
such as `personnummer`), address (P5: street, postal code, and the city in a table of addresses or people) and birth
date (P6). By default `sample_rows` returns their values as `***` with a notice naming the rule, `answer_query_draft`
and `gold_views_draft` leave them out (the key stands in), and the silver notebook masks them in its quarantine table;
`show_personal_data=true` shows them, and your own Fabric permissions still decide what you can read. When Fabric
returns a Microsoft Purview sensitivity label on the source item, `sample_rows` and `validate_plan` name it: Fabric
gives the label's id only, and a label covers the whole item, so the column rules still decide what is masked.

### Cold start, and `min_replicas` if you run it yourself

If the hosted service has been idle, the first request may take longer while Azure starts the container. If that
request times out, try again after a short pause. If the problem continues, check the error message or
[get help](/support).

If you run the server yourself with `deploy/krusgraph.sh`, `min_replicas` in `deploy/krusgraph.json` decides whether it
scales to zero: `0` (the default) scales to zero when idle and is the cheapest, `1` keeps one instance running so idle
time does not cause a cold start, at the cost of one always-on instance. A new revision or a restart can still delay a
request. The change takes effect with `--update`. A container on a VM or in Docker does not scale to zero.

### Support

[Get help](/support): email Gustav at {{CONTACT}} with the `error`, `kind` and `hint` from the tool's answer (there is no
promised response time), or report a bug or a plan that came out wrong on
[GitHub Issues](https://github.com/Krusmaster/fabric-backend/issues). Source (MIT): https://github.com/Krusmaster/fabric-backend
