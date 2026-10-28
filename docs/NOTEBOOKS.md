# From understanding to building: notebooks, the drift monitor and query suggestions

Krusgraph's plan (keys and relationships with the rule behind each) has so far been turned into an API, a semantic
model, an ontology, views and a data agent. This round adds three things a data engineer builds next, all from the
same plan and all with a draft that creates nothing:

| Tool | Gives | Creates |
| --- | --- | --- |
| `silver_notebook_draft` / `create_silver_notebook` | a PySpark notebook that builds clean silver tables | one notebook item (dry run by default) |
| `drift_monitor_draft` / `create_drift_monitor` | a nightly notebook and pipeline that report schema changes to a webhook | a notebook, a pipeline and a daily schedule (dry run by default) |
| `answer_query_draft`, `query_graphql(question=...)` | a T-SQL or GraphQL query for a question, over the safest join path | nothing |

Status: unit-tested. The generated notebooks also run on a local PySpark 4.0.1 against the shop seed
(`tests/test_spark_notebooks.py`: in the sandbox with Java 21 on 26 October 2026, and in CI's `notebooks` job with
Java 17); none of it has run in a Fabric workspace yet. The local stdio server has `answer_query_draft` (T-SQL) and
`silver_notebook_draft` too; the creating tools and the drift monitor need Fabric item ids and are hosted only.

## Silver tables (`silver_notebook_draft`, `create_silver_notebook`)

For a lakehouse (other sources: put the tables in a lakehouse as OneLake shortcuts first), the notebook does, per
table, in the order of the relationships (parents first):

1. **Read** the source table. Sources are only read: the targets are in `silver_schema` (default `silver`; on a
   lakehouse without schemas the tables are prefixed `silver_`), the tool refuses a silver schema that is the source
   schema or a target name that is a source table, and the notebook checks the same again before it writes anything.
   On a lakehouse without schemas the `silver_*` tables and the quarantine table sit beside the sources, so a plan made
   after the first run lists them; they are treated as the notebook's own outputs, not as sources, and the run-time mark
   (step 4) keeps the notebook off any such table it did not write.
2. **Key** (rule K0–K5): rows whose key is NULL go to quarantine; of rows that share a key, the latest by the ordering
   column wins and the others go to quarantine. The ordering column is `order_by` (`{"orders": "updated_at"}`), else
   a column named like `updated_at`, `modified`, `ingested_at`, `loaded_at` or `created_at`; without one the kept row
   is chosen by a content hash, so a re-run keeps the same row. Keyless tables (K3) are copied as they are.
3. **References** (rule R0–R4 or `confirmed`): rows whose reference has no row in the parent's silver table go to
   quarantine with the reason (`customer_id has no row in customers (orders.customer_id = customers.customer_id)`);
   a NULL reference stays. Because parents are written first, an order whose customer was quarantined takes its order
   lines with it. A table that points at itself (`employees.manager_id`) is checked against its own rows again until no
   more rows drop out, so the people under a quarantined manager follow the manager there.
4. **Write** a Delta table, overwritten on every run, marked with the table property `krusgraph.silver` set to the
   source it was built from (`<lakehouse id>/<schema>`). A target that exists without that mark, or with another
   source's, is never overwritten: the notebook stops before writing anything, with "was not written by this
   notebook". Two notebooks for two schemas of one lakehouse therefore need two silver schemas.

At the end `krusgraph_quarantine` (`source_table`, `rule`, `reason`, `row_json`, `checked_at`) is rewritten with this
run's rows, and a summary per table is printed (read, written, quarantined per reason). Every step is commented in the
notebook with the rule that motivates it. Re-running rewrites the same tables from the source (idempotent).

The format is the one Fabric uses for a PySpark notebook in Git and in its item definition (`notebook-content.py`,
`fabricGitSource`), with the source lakehouse as the default lakehouse. `create_silver_notebook` sends it with
`POST /v1/workspaces/{id}/notebooks` (or `.../notebooks/{id}/updateDefinition` for a notebook of that name) and runs
nothing; open it in Fabric and Run all, or add it to a pipeline.

Sources: microsoft/fabric-rest-api-specs (commit a96c37a, read 26 October 2026) `notebook/swagger.json`
(`Items_CreateNotebook`, `Items_UpdateNotebookDefinition`: long-running, delegated scope `Notebook.ReadWrite.All` or
`Item.ReadWrite.All`, Contributor on the workspace, a Fabric capacity) and `notebook/definitions.json` (formats `ipynb`
and `fabricGitSource`); MicrosoftDocs/fabric-docs (commit 0b9f0f8) `fundamentals/understand-best-practices-fabric-cicd.md`
(the `# Fabric notebook source` header and the default-lakehouse metadata).

Tested: the same steps in Python on the shop seed with a NULL key, an exact duplicate, a newer version of an order,
an order with an unknown customer and its line, an orphan line and a NULL reference added (`silver.simulate`); the
generated notebook on a local Spark against the same rows gives the same tables and quarantine, a second run gives
the same again, and the two guards stop a run before anything is written (`tests/test_spark_notebooks.py`); a test
checks over both lakehouse kinds and several schema names that no source table is ever a write target.

## The nightly drift monitor (`drift_monitor_draft`, `create_drift_monitor`)

A notebook and a pipeline. Every night the pipeline runs the notebook, which:

1. reads the lakehouse's tables and columns from the Spark catalog and infers today's plan with the same rules;
2. compares it with the plan the last run saved (`fabric_backend.monitor.diff`: tables, columns, types, keys and
   relationships added or removed);
3. when something changed, finds what it reaches: the GraphQL APIs, semantic models, data agents and (when the
   runtime has the Fabric Data Warehouse connector) views that use the changed tables, with `lineage`'s logic, and per
   GraphQL API what a `create_backend` re-run would drop, with `plan_drift`'s comparison;
4. sends a short summary to `webhook_url` ("Column country in table customers disappeared — used by GraphQL API
   shop_api, view krusgraph.vw_orders.") as an Adaptive Card message, only when something changed (`notify = "always"`
   for every night);
5. saves today's plan as a new row in `krusgraph.plans` (`krusgraph_plans` on a lakehouse without schemas). A failed
   webhook stops the run before the save, so the next night reports the same changes again.

The logic is the library's (`fabric_backend.monitor`, `lineage`, `drift`), installed in the notebook with
`%pip install "fabric-backend @ git+https://github.com/Krusmaster/fabric-backend@v<version>"` (`v0.8.0` today): by
default the tag of the server's own version, so every night runs the code that drafted the notebook and saved its first plan, and nothing
pushed later changes what the monitor does until you choose it. `library_ref` names another tag or a commit, or
`main` to follow the main branch (which moves with every push). The tag is made with each release
([PUBLISHING.md](PUBLISHING.md)); without it the `%pip` cell fails and the run stops there. The pipeline passes
`_inlineInstallationEnabled = true`, which a pipeline run needs for `%pip`.

**No secret in the code.** The webhook address is a pipeline parameter with an empty default; you set it in Fabric
(pipeline, Parameters, `webhook_url`). The Notebook activity has `secureInput` on, so the pipeline's run history does not
show the address, and a failed webhook call reports only the kind of failure, never the address (it carries its own
`sig=` key). Not checked: whether Fabric's snapshot of a notebook run shows the parameter cell the pipeline injects;
treat the snapshot as readable by whoever can open the run, and rotate the workflow's URL if that matters. The
activity does not retry, so a run that sent its message and then failed cannot send it twice. For Teams: a workflow "When a Teams webhook request is received" that posts to a channel. For e-mail: a Power
Automate flow "When an HTTP request is received" → "Send an email (V2)", or add Fabric's Office 365 Outlook activity to
the pipeline after the notebook (the notebook's exit value carries the title and the lines). The Fabric REST calls of
step 3 use the identity that runs the notebook (`notebookutils.credentials.getToken('pbi')`).

`create_drift_monitor` creates or updates the notebook (`name`) and the pipeline (`name_nightly`), then adds a daily
schedule at `at` in `time_zone` (a Windows time zone id, default `W. Europe Standard Time`) unless a daily schedule at
that time exists. After creating: set `webhook_url`, open the Notebook activity once and check its Connection (choose
your account or the workspace identity if Fabric asks), and run the pipeline once by hand to save the baseline.

Sources: fabric-rest-api-specs a96c37a `dataPipeline/swagger.json` (`Items_CreateDataPipeline`,
`Items_UpdateDataPipelineDefinition`, `BackgroundJobs_ScheduleExecute`; at most 20 schedules per pipeline; the
schedule needs `DataPipeline.Execute.All` or `Item.Execute.All` and `DataPipeline.ReadWrite.All` or
`Item.ReadWrite.All`), `common/job_scheduling.json` (`DailyScheduleConfig`); fabric-docs 0b9f0f8
`notebookutils-credentials.md`, `library-management.md`, `notebook-limitation.md`, `spark-data-warehouse-connector.md`.
The Notebook activity's JSON (`TridentNotebook`, `notebookId`, `workspaceId`, `parameters`) is not in the
specification; it follows pipelines exported from Fabric, and is the part most likely to need a correction on the
first live run.

Tested: the comparison, what a change reaches and the message on the shop schema (`tests/test_drift_monitor.py`); the
generated notebook ran two nights on a local Spark with Fabric's REST answers stood in: the first night saved a
baseline and sent nothing, the second (a column dropped) sent one message naming the column, the GraphQL API that uses
it and what `create_backend` would drop, and a third night without change sent nothing.

## Query suggestions (`answer_query_draft`, `query_graphql` with `question`)

A question in Swedish or English plus the tables it is about. From the question the tool reads the aggregate (count,
sum, average), the grouping ("per", "by", "för varje", "efter"), the counted table ("how many orders", "antal
ordrar"), top N ("top 5", "vilka 5 kunder") and "latest"/"senaste"; words are matched to tables and columns through
the same names and synonym table the inference uses (`kund` → customers, `land` → country). The join path is the
safest one (`join_path`'s cost 1/certainty per rule), and every step carries its rule. Everything it assumed is listed.

- **T-SQL** always: `SELECT … FROM [schema].[table] … JOIN … GROUP BY … ORDER BY …`, with `DISTINCT` on the key when a
  step goes one-to-many and a note when a sum could count a value twice.
- **GraphQL** with `api`: a list walks the API's relationship fields (many-to-one as an object, one-to-many as a
  connection with `items`); an aggregate uses `groupBy(fields: [...])` and `aggregations { count(field: ...) }`.
  Fabric's GraphQL groups only by a table's own columns, so "total quantity per category" over order lines answers with
  the reason and the T-SQL instead (fabric-docs `api-graphql-aggregations.md`).
- `query_graphql(workspace, api, question=..., tables=[...], source=...)` builds the GraphQL suggestion and runs it,
  and shows the query beside the result.

Tested on the shop schema with eight questions in both languages: the T-SQL runs on the seed rows in SQLite and the
counts, sums and the order of the latest orders match the same numbers computed in Python; the GraphQL validates
against a schema built from the API's own definition in the shape Fabric generates (`tests/test_answer_query.py`).

**Characters an agent reads** for the same question, without and with the suggestion (without: `describe_backend` and
`join_path`, before writing the query itself; a token is about four characters). Measured 26 October 2026 on the shop
schema; this is input for the measurement rig in Krusmaster/fabric-eval, not a claim about every schema:

| Question | describe_backend + join_path | answer_query_draft |
| --- | --- | --- |
| How many orders per customer? | 4 851 | 1 529 |
| Total quantity per category | 5 569 | 1 512 |
| De 10 senaste ordrarna med kund | 4 851 | 1 319 |

Since 26 October 2026 (round n12) the two questions about customers carry a short `personal_data` note: `customers.name`
looks like a person's name by the privacy rules, so the query groups and lists by `customer_id` instead unless
`show_personal_data=true`. Before that change the same answers were 1 323 and 1 082 characters.

## Permissions

`create_silver_notebook` needs `Notebook.ReadWrite.All` (or `Item.ReadWrite.All`); `create_drift_monitor` needs that
plus `DataPipeline.ReadWrite.All` and, for the schedule, `DataPipeline.Execute.All` (or `Item.Execute.All`). The app
does not ask for them today: without them the dry runs work and the creates answer `kind: consent` naming the scope.
`docs/SCOPES.md` has the commands to add them.
