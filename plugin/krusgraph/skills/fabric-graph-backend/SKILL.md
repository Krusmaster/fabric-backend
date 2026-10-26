---
name: fabric-graph-backend
description: Build or document a backend on Microsoft Fabric data with the Krusgraph connector. Use when the user names a Fabric lakehouse, warehouse or SQL database and wants a GraphQL API, an app on Fabric data, keys and relationships explained, a Power BI semantic model, a data dictionary or dbt tests from it.
---

# Fabric tables to a graph, an API and hand-over documents

Krusgraph infers keys and relationships from a source's metadata and names the rule behind each one (K0–K5 for keys,
R0–R4 for relationships). Nothing is created until the user says so. Every tool answers JSON; a call that cannot be
completed answers `error`, `kind` and `hint`: read the hint and act on it instead of retrying blindly.

## The main path: from a source to a working API

1. **Find the source.** `list_workspaces` when the workspace is unknown, then `list_sources` (lakehouses,
   warehouses, SQL and mirrored databases, existing GraphQL APIs). Take the names the user gives; do not guess ids.
2. **Plan.** `plan_backend(workspace, source, schema)`. Tell the user the summary line (tables, keys, relationships),
   the keyless tables and the ambiguous columns. Default schema is `dbo`; a lakehouse created with schemas has others.
3. **Unclear column?** `sample_rows(table)` shows a few rows so the meaning can be settled before deciding on a key
   or a relationship. Never decide a relationship from a column's name alone when the plan says it is ambiguous.
4. **Check against the data.** `validate_plan` counts uniqueness, NULLs and orphans for every key and relationship.
   Report the verdicts. A key that is not unique or a relationship with orphans is a reason to stop and ask.
   **Large schemas:** above 60 tables `list_tables`, `plan_backend` and `analyze_schema` answer in summary form on
   their own (one line per key and relationship, no field names, no diagram) and say so; `detail="full"` asks for
   everything, `tables=["sales_*", "customers"]` narrows the answer to matching tables while the plan is still made
   from the whole schema. Work one area at a time rather than asking for a thousand tables in full.
5. **Plan lacks links?** `suggest_relationships` ranks candidate columns and checks the best against the data
   (inclusion share). Suggestions only: show them to the user with the evidence and **ask which to accept**; pass the
   accepted ones as `confirmed` to the next calls. Do not add a relationship the user has not confirmed.
6. **Existing API?** `plan_drift(api)` before any `create_backend` on a name that already exists: it lists what the
   re-run would add, change or remove. Show removals to the user; keep a relationship the API has by passing its
   `confirmed` entry (the answer's `keep_with_confirmed`).
7. **Create.** `create_backend(workspace, source, name, keys, confirmed)` creates or updates one API for GraphQL item.
   **Ask for the user's go-ahead first**, naming the item and the workspace; it changes an item in their workspace.
   If the answer is `kind: would_remove`, show the list and ask again before passing `allow_removals=true`.
8. **Describe and query.** `describe_backend(api)` gives the exact type, field and relationship names;
   `query_graphql(api, query)` runs a read-only query. Build queries from `describe_backend`, not from memory.
9. **Hand over.** Repeat the two portal steps the answer names (introspection, permissions): Fabric has no API for
   them. `app_readiness(api)` lists what an app still needs; `app_starter(api)` gives the prompt, the queries and the
   backend piece (a Supabase edge function) for an app that never holds a secret in the browser.

## Branches from the same plan (nothing is created)

- **Power BI semantic model:** `semantic_model_draft(name)` writes TMDL (Direct Lake) with one active path per table
  pair and a `README.generated.md` of decisions to check. `create_semantic_model` creates the item; it is a dry run
  until `dry_run=false`, and that needs the user's go-ahead.
- **Fabric IQ ontology (preview):** `ontology_draft(name)` writes the entity types with keys, the relationship types
  and the bindings; `create_ontology` creates or updates the item of that name in place, a dry run until
  `dry_run=false` with the user's go-ahead. Without the permission it answers `kind: consent`.
- **Data dictionary:** `data_dictionary(validate=true)` writes the hand-over Markdown with the counts from the data.
- **dbt:** `dbt_schema(source_name)` writes the sources file with `unique`, `not_null` and `relationships` tests.
- **How two tables connect:** `join_path(start, end)` gives the chain, the rule per hop and ready T-SQL;
  `analyze_schema` reads an unknown source as a graph (roles, central tables, subject areas, cycles).
- **Wide views:** `create_views` (dry run by default) writes `CREATE OR ALTER VIEW` in a schema of its own, never DROP.
  Running it for real needs the user's go-ahead.
- **A question in words:** `answer_query_draft(question, tables)` gives T-SQL over the safest join path (and GraphQL
  with `api`) and lists what it assumed; show the assumptions. `query_graphql(api, question=..., tables=..., source=...)`
  runs the GraphQL version instead of a hand-written query.

## Building on the plan (dry run first)

- **Silver tables:** `silver_notebook_draft` shows the PySpark notebook (de-duplication on each key, references checked,
  rows that fail in `krusgraph_quarantine`, never written over a source table). Ask which column says "latest" when
  the answer has no `latest_by`, and pass it as `order_by`. `create_silver_notebook` creates the notebook item.
- **Nightly drift monitor:** `drift_monitor_draft` shows the notebook, the pipeline and the schedule;
  `create_drift_monitor` creates them. The webhook address is never passed to a tool: tell the user to set
  `webhook_url` on the pipeline in Fabric.
- **Gold views:** `gold_views_draft` shows materialized lake views over the silver tables (a lakehouse with schemas),
  one per fact table, with the plan's keys and relationships as data quality rules; `create_gold_views` creates the
  notebook that makes them. Run the silver notebook first.
- **An existing semantic model:** `compare_semantic_model(model)` lists what the model lacks or gets wrong against the
  plan. Without the permission it answers `kind: consent`; the model's TMDL files passed as `tmdl` need none.
- **Changes through Git:** `export_item_definitions` gives what the creating tools would create as folders in Fabric's
  Git format, for the user's own repository.
- **Personal data:** columns that look like personal data by name come back masked or left out; pass
  `show_personal_data=true` only when the user asks to see them.

## A lakehouse nobody has documented: five first questions

In this order, each answer feeding the next: `analyze_schema` (which tables are facts, which are dimensions, what
the subject areas are), `plan_backend` (the keys and relationships with the rule behind each), `validate_plan` (are
the keys unique, do the references hold), `suggest_relationships` (which columns look like references but are in no
relationship), `data_dictionary` (the hand-over document with everything above).

## When to stop and confirm with the user

- Before `create_backend`, `create_semantic_model`, `create_ontology`, `create_views`, `create_data_agent`,
  `create_silver_notebook`, `create_drift_monitor` or `create_gold_views` run for real.
- Before passing `show_personal_data=true`.
- Before accepting any suggested relationship or composite key into `confirmed` / `keys`.
- When `validate_plan` finds duplicates or orphans, or `plan_drift` lists removals.
- When a tool answers `kind: consent`, `sign_in`, `no_access` or `capacity`: the hint names what the user or an admin
  must do; do not work around it. `kind: rate_limited` says how many seconds to wait (`retry_after`).

## What to say back

Lead with the summary line and the rule per relationship (`orders.customer_id -> customers [R1]`), name what was not
inferred (keyless tables, ambiguous columns) and what still needs a click in the Fabric portal. Quote counts from
`validate_plan` as counts of the moment, not as proof of meaning.
