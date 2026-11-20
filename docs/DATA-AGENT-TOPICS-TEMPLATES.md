# Data agent topics and example-query templates from checked joins

Round DA2, 19 November 2026. What Microsoft Learn documents about topics, example queries (query templates) and
semantic model configuration in a Fabric data agent, what `create_data_agent` now writes, and what is design only.

**Krusgraph checks the joins once, with evidence and your approval; your data agent then reuses them in topics and
templates.** Rules and templates only: no language model, no AI in Krusgraph. The same plan and the same counts give
the same text.

**Not tested live.** Unit-tested with the Fabric REST calls mocked and on the synthetic SAP sample in SQLite
(`tests/test_da2_topics.py`, golden file `tests/golden/da2_sap_demo_topics.json`). The repository does not document a
way for a round to reach the demo workspace from this environment, so nothing was written to Fabric in DA2. The next
live run should follow `docs/LIVE-TEST.md` and switch the agent to the preview runtime first (topics need it).

## 1. What Microsoft Learn documents (read 19 November 2026)

Only public Learn pages and the documented REST API; no portal-internal endpoints. Dates are each page's own "last
updated" date.

| What | Documented? | What Learn says | Source |
| --- | --- | --- | --- |
| (a) Topics for SQL sources | **Yes, preview**, as a REST resource of the data source | "large, topic-based instructions"; the agent "searches the topic content and sends the relevant sections to NL2SQL"; "up to 1 million characters of topic content to each supported SQL data source"; "Use Markdown headings to organize the content"; "Keep each topic self-contained"; "Topics are in preview and are available only for SQL data sources on the preview runtime" | [Topics (preview)](https://learn.microsoft.com/fabric/data-science/data-agent-topics), updated 2026-09-10 |
| | | `PUT /v1/workspaces/{ws}/dataAgents/{id}/staging/datasources/{dsId}/topics?fileName={name}.md`, body `text/markdown`, "May include YAML frontmatter with name and description fields"; "Creates or replaces a topic file"; also List, Download, Delete and Format (which adds front matter); "Data Agent configuration management is currently in Preview"; scopes `Item.ReadWrite.All` or `DataAgent.ReadWrite.All` | [Staging - Upload Datasource Topic](https://learn.microsoft.com/rest/api/fabric/dataagent/staging/upload-datasource-topic), [List Datasource Topics](https://learn.microsoft.com/rest/api/fabric/dataagent/staging/list-datasource-topics), [Format Datasource Topic](https://learn.microsoft.com/rest/api/fabric/dataagent/staging/format-datasource-topic), updated 2026-11-04 |
| | **Not** in the item definition | The Data Agent definition article lists `data_agent.json`, `stage_config.json`, `datasource.json`, `fewshots.json`, `publish_info.json`; no topic part. The source-control article describes the same folders and files, no topic files | [Data Agent definition](https://learn.microsoft.com/rest/api/fabric/articles/item-management/definitions/data-agent-definition), updated 2026-02-11; [Source control, CI/CD and ALM](https://learn.microsoft.com/fabric/data-science/data-agent-source-control), updated 2026-08-27 |
| (b) Example queries | **Yes** | `{question, query}` per data source (`fewshots.json`; Staging - Create Datasource Fewshot); "typically the top four" are retrieved; every example "is validated against the schema of the selected data source"; best practice 2: "Include comments in the query to guide the agent (`-- substitute customer_id here`)" | [Example queries](https://learn.microsoft.com/fabric/data-science/data-agent-example-queries), updated 2026-01-30; [Staging - Create Datasource Fewshot](https://learn.microsoft.com/rest/api/fabric/dataagent/staging/create-datasource-fewshot), updated 2026-09-15 |
| | Parameters: **not documented** | No field for parameters, no placeholder syntax, no "query template" resource in the REST reference or the definition format | same pages |
| (c) Semantic model configuration | **No** (for what a data agent stores) | For a semantic model source: data source instructions "No* … managed through Prep for AI"; data source description "No"; topics "No"; example queries "No* … Use Verified Answers in Prep for AI"; "Fewshots aren't supported for Semantic Model and Ontology datasources" | [Add a data source](https://learn.microsoft.com/fabric/data-science/data-agent-add-datasources), updated 2026-09-30; Create Datasource Fewshot |

The November 2026 feature summary (Fabric Updates Blog, 17 November 2026; known here from the round's brief, the blog was not read from this environment) names query templates for SQL and semantic
models and configuring semantic models inside a data agent as previews. On 19 November 2026 Learn did not yet document
how either is stored or written, so they stay design (section 4).

## 2. What `create_data_agent` writes now

Dry run by default: the answer shows every topic file and every template it would write (`agent.topics`,
`agent.templates`, `agent.topics_note`, the REST calls in `rest`). Writing needs `dry_run=false`, as before; that call is
the person's approval of what the dry run showed.

**Topics** (`fabric_backend/agent_topics.py`), one file per business area, for SQL sources only (Lakehouse, Warehouse,
SQL database, mirrored database: Learn's SQL category). Areas are the ones `domain_draft` proposes (on SAP-shaped data:
order-to-cash and customer master). Each file:

- YAML front matter `name` and `description` (documented), then one `##` heading for the area;
- *Tables and what their fields mean*: the pack's description and note of each table, its key with the rule, and per
  column what Krusgraph knows (part of the key, which table it points at and by which rule, an amount and its currency,
  a change date). Personal columns by name are left out and named;
- *Checked joins (use these)*: only joins `validate_plan` counted and that held, with the counts as evidence ("3 of 3
  rows with a value find their sap_kna1 row (100.0% match); the target key is unique"); "confirmed by you" where the
  person confirmed the join;
- *Joins not to use without asking*: orphans (with the match rate), a target key that is not unique, joins never
  counted, pack joins that need an extra condition;
- *Known traps*: a header amount summed over its lines (VBAK.NETWR over VBAP: the total that doubles), the pack's traps
  that name a table of the area (currency per document, sold-to/ship-to/payer, text tables per language…).

File names start with `krusgraph-`; Krusgraph writes (creates or replaces) only those and deletes nothing. Topics are a
preview of the preview runtime: if Fabric refuses a topic, the log says so and the rest of the agent is written and
published as before. No topics for the gold layer (the views are already joined; the layer's instructions cover them).

**Templates** (example queries). One runnable T-SQL example per checked join, grouped by the target's key, up to 20, as
ordinary example queries next to the 3–5 examples from round n130. Where a customer, a period or another filter goes is
written as comments, Learn's own advice, because no parameter format is documented:

```sql
-- Template from the checked join sap_vbak.MANDT = sap_kna1.MANDT AND sap_vbak.KUNNR = sap_kna1.KUNNR (rule SAP pack; counted: 3 of 3 rows with a value find their sap_kna1 row (100.0% match)).
-- For one KNA1 (customer master), add: WHERE t.[MANDT] = '<MANDT>' AND t.[KUNNR] = '<KUNNR>'
-- For one period, add: WHERE s.[ERDAT] BETWEEN '<from>' AND '<to>'
-- For one TVKO (sales organizations), add: WHERE s.[MANDT] = '<MANDT>' AND s.[VKORG] = '<VKORG>'
SELECT TOP (25) t.[MANDT], t.[KUNNR], COUNT_BIG(*) AS [sap_vbak_count]
FROM [sap].[sap_vbak] AS s
JOIN [sap].[sap_kna1] AS t ON s.[MANDT] = t.[MANDT] AND s.[KUNNR] = t.[KUNNR]
GROUP BY t.[MANDT], t.[KUNNR]
ORDER BY [sap_vbak_count] DESC
```

The period comment appears only for a column of a date type or a change date the SAP pack lists (ERDAT, AEDAT);
Krusgraph does not guess a date from a column name. On the gold layer each gold view gets one template, counted per a
joined table whose key the view carries. Without counts (`validate=false`) no join is checked, so no template is made.

## 3. Semantic model sources

Nothing is built: Learn says a semantic model source takes no data source instructions, description, topics or example
queries in the data agent; they belong in Prep for AI in Power BI. The agent instructions (`aiInstructions`) can say
when to use the model; `create_data_agent` already writes those for SQL sources.

## 4. Design only (not built)

- **Parameterized templates.** When Learn documents a parameter syntax for example queries, the comments above become
  parameters: the target's key (customer), the source's date (period) and the other checked joins of the same source
  (sales organisation), each typed from the column. Until then, comments only.
- **Topics in the item definition / Git.** When the definition article lists a topic part, `export_item_definitions`
  can write the same files into the Git format; the text is already deterministic, so a diff shows exactly what
  changed.
- **Semantic model configuration in the data agent** (November 2026 preview: descriptions, instructions, example
  queries, column and measure selection). When documented, the source would be `create_semantic_model`'s own model:
  descriptions from the plan's business names, instructions from the same traps, measure selection from the measures
  Krusgraph wrote. Semantic Model Topics ("Skills for Fabric") likewise wait for a documented format.
- **Feedback and traces.** The data agent feedback API (beta) and Application Insights tracing can show which questions
  failed; a later round could map a failed question to the topic or join it used. Not designed in detail.
- **Materialized lake views:** `REFRESH_HINT UNIQUE(...)` incremental refresh for deletes and updates, and file
  ingestion `USING OneLake_Files`, could make `create_gold_views` refresh incrementally. A follow-up; nothing built.

## 5. Domains REST API (checked in DA2)

Microsoft removed the preview versions of the OneLake Domains REST APIs in November 2026. Krusgraph sends no Domains
call: `fabric_backend/catalog_publish/handover.py` prepares `POST /v1/admin/domains` and `POST
/v1/workspaces/{id}/assignToDomain` for a Fabric administrator to send, and `catalog_publish/apis.py` cites the GA
pages. Neither uses a `preview` parameter or a preview-only field: the body is `displayName` and `description` (at most
256 characters), as [Create Domain](https://learn.microsoft.com/rest/api/fabric/admin/domains/create-domain) (updated
2026-11-09) documents. Also checked: `domains.py`, `catalog.py`, the `domain_draft` tool in `server.py`, the workload's
`app/clients/`. No change was needed.
