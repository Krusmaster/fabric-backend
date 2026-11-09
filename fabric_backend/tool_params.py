"""Parameter types of the remote server's tools, with the description each one carries in tools/list
(inputSchema.properties.*.description). The types are exactly the ones the tools had before; only the descriptions are
new. Shared parameters are defined once here and used by every tool that takes them; parameters with a meaning of their
own in one tool are defined next to the shared ones under that tool's name. tests/test_tool_descriptions.py fails when
a parameter has no description."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field


def _d(text: str):
    return Field(description=text)


# ------------------------------------------------------------------ shared ---------------------

Workspace = Annotated[str, _d('Fabric workspace, name or id.')]
Source = Annotated[str, _d('Lakehouse, warehouse or SQL database, name or id.')]
Schema = Annotated[str, _d('Schema in the source. Default "dbo".')]
PlanSchema = Annotated[str | None, _d(
    'Schema in the source; leave it out unless the user named one. Default: the only schema with tables; when the '
    'source has several, the answer lists them and asks which (choose_schema), and nothing is planned.')]
Keys = Annotated[dict[str, list[str]] | None, _d(
    'Primary keys replacing the inferred ones. Default: inferred. Example: {"order_items": ["order_id", "line_no"]}.')]
Confirmed = Annotated[list[dict] | None, _d(
    'Relationships the user confirmed, added to the plan. Default none. Example: [{"source": "orders", "source_cols": '
    '["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}].')]
TablesShown = Annotated[list[str] | None, _d('Table names or globs to show. Default all. Example: ["sales_*"].')]
TablesOnly = Annotated[list[str] | None, _d('Exact table names to include. Default all.')]
Detail = Annotated[str, _d('"auto" (default: full up to 60 tables, else summary), "full" or "summary".')]
ValidateDetail = Annotated[str, _d('"summary" (default) or "full" (every check).')]
Profile = Annotated[bool | dict, _d('true adds per column of the checked tables: NULL share, distinct count, number '
                                   'min/max below/above zero; {"numbers": [lo, hi], "dates": [from, to]} states ranges. '
                                   'One query per table within max_items; never values. Default false.')]
MaxItems = Annotated[int, _d('Cap on counting queries (one per key and relationship), 1–200. Default 60.')]
SqlSums = Annotated[bool, _d('true also reads the SQL views\' definitions (no rows) and lists views that SUM a header '
                             'amount after joining its line table, and views it could not read. Default false.')]
Fixes = Annotated[bool, _d('true: a fix per finding; applies nothing.')]
Review = Annotated[dict | str | None, _d('With fixes: a review_plan file.')]
AcceptedFixes = Annotated[list | None, _d('Ids from validate_plan(fixes=true).')]
DryRun = Annotated[bool, _d(
    'true (default) returns what would be created and the REST calls, changing nothing; false creates or updates.')]
ShowPersonalData = Annotated[bool, _d(
    'true includes columns named like personal data; false (default) masks or omits them.')]
Api = Annotated[str, _d('API for GraphQL item, name or id (list_sources: graphql_apis).')]
Writable = Annotated[bool, _d('true includes create, update and delete mutations in the API; false (default) gives a '
                              'read-only API. Example: true.')]
SilverSchema = Annotated[str, _d('Lakehouse schema with the silver tables create_silver_notebook writes. Default '
                                 '"silver".')]
GoldSchema = Annotated[str, _d('Lakehouse schema for the gold views. Default "gold". Example: "gold".')]
ViewsSchema = Annotated[str, _d('Schema the T-SQL views go into; created if missing. Default "krusgraph". Example: '
                                '"reporting".')]
OrderBy = Annotated[dict[str, str] | None, _d(
    '{table: column} deciding which duplicate row is kept (the latest wins). Default: a column named like updated_at. '
    'Example: {"orders": "modified_at"}.')]
Validate = Annotated[bool, _d('true runs validate_plan\'s counting queries and includes the counts; false (default) '
                              'reads metadata only.')]
At = Annotated[str, _d('Daily run time, hh:mm in time_zone. Default "02:00". Example: "05:30".')]
TimeZone = Annotated[str, _d('Windows time zone id for `at`. Default "W. Europe Standard Time". Example: "UTC".')]
LibraryRef = Annotated[str | None, _d('Git tag, branch or commit of fabric-backend that the notebook installs. Default: '
                                      'the tag of this server\'s version. Example: "main".')]


def _name(item: str, example: str, default: str | None = None) -> Field:
    tail = f' Default "{default}".' if default is not None else ""
    return _d(f'Display name of the {item}; an existing item with this name is updated in place.{tail} '
              f'Example: "{example}".')


# ------------------------------------------------------------------ per tool -------------------

Mermaid = Annotated[bool, _d('false leaves the Mermaid ER diagram out of a full answer. Default true. Example: false.')]
Decisions = Annotated[list[dict] | None, _d(
    'Review decisions, [{"item", "review", "reason"}]; review is accepted, rejected, open or proposed; item ids are '
    'in the file. Default: none. Example: [{"item": "rel:orders.ship_to_id>addresses", "review": "accepted", '
    '"reason": "checked with sales"}].')]
Previous = Annotated[dict | str | None, _d(
    'An earlier file from review_plan (object or JSON text); its decisions are applied again and checks on changed '
    'tables become stale. Default: none. Example: the "file" of the last answer.')]
SampleTable = Annotated[str, _d('Table to read, by name. Example: "orders".')]
SampleN = Annotated[int, _d('Number of rows, 1–20. Default 10. Example: 5.')]
BackendName = Annotated[str, _name("API for GraphQL item", "shop_api")]
AllowRemovals = Annotated[bool, _d(
    'true lets an update drop relationships the existing API has; false (default) writes nothing and lists them '
    'instead. Example: true.')]
CreateBackendTables = Annotated[list[str] | None, _d(
    'Exact table names the API exposes; the plan is still made from the whole schema. Default: all tables. Example: '
    '["orders", "customers"].')]
Connector = Annotated[str, _d('Connector name; files go under rayfin/connectors/<connector>/. Default "data". '
                              'Example: "shop".')]
RayfinRelationships = Annotated[bool, _d('false leaves the @one/@many relationship fields out. Default true. '
                                         'Example: false.')]
CheckRows = Annotated[bool, _d(
    'true: with row counts. Default false.')]
OntologyDraftName = Annotated[str, _d('Name of the ontology in the draft. Default "ontology". Example: "shop_ontology".')]
OntologyName = Annotated[str, _name("ontology item", "shop_ontology")]
ModelDraftName = Annotated[str, _d('Name of the semantic model in the draft. Default "semantic_model". Example: '
                                   '"shop_model".')]
ModelName = Annotated[str, _name("semantic model item", "shop_model")]
ReportModel = Annotated[str, _d('Semantic model the report is bound to, name or id (as create_semantic_model named it). '
                                'Example: "shop_model".')]
ReportName = Annotated[str, _d('Display name of the report; a report of this name in the workspace is left alone and the call '
                               'refused. Example: "shop_report".')]
EmptyPage = Annotated[bool, _d('true creates the report with one blank page and reads nothing of the model; false (default) '
                              'draws a page from its measures and columns. Example: false.')]
CompareModel = Annotated[str, _d('Existing semantic model in the workspace, by name or id. Default "" (only with '
                                 'tmdl). Example: "Sales model".')]
CheckData = Annotated[bool, _d('true counts the plan\'s keys and relationships and the model\'s extra links against the '
                               'rows; false (default) compares metadata only. Example: true.')]
Tmdl = Annotated[dict[str, str] | None, _d(
    '{path: text} of the model\'s TMDL files (as in a PBIP folder or Git), read instead of fetching the model. '
    'Default: none. Example: {"definition/relationships.tmdl": "relationship …"}.')]
Start = Annotated[str, _d('Table the path starts at. Example: "order_items".')]
End = Annotated[str, _d('Table the path ends at. Example: "customers".')]
Check = Annotated[int, _d('How many top candidates are counted against the data. Default 15. Example: 5.')]
SourceName = Annotated[str | None, _d('Name of the dbt source. Default: the schema name. Example: "shop".')]
ArgumentsBlock = Annotated[bool, _d('true (default) puts test arguments under arguments: (dbt 1.10.5+); false writes '
                                    'them top-level for older dbt. Example: false.')]
DbtProject = Annotated[bool, _d('true: a whole dbt project as files (staging, marts per domain) instead of the sources file. '
                                 'Default false. Example: true.')]
Quality = Annotated[str | None, _d('Also drafts the same key and relationship checks as a Great Expectations suite per table '
                                   '("gx"), as SodaCL checks ("soda") or both ("both"), each with its rule and counts. Default none.')]
DbtProfile = Annotated[bool, _d('With project=true: adds a profiles.yml for Fabric with placeholders and no secret. Default false.')]
DriftApi = Annotated[str, _d('Existing API for GraphQL item to compare with, by name or id. Example: "shop_api".')]
DriftWritable = Annotated[bool, _d('Whether the update create_backend would make includes mutations, as its writable. '
                                   'Default false. Example: true.')]
AgentName = Annotated[str, _name("data agent", "shop_agent")]
Publish = Annotated[bool, _d('true (default) publishes the agent after creating or updating it; false leaves a draft. '
                             'Example: false.')]
AgentTests = Annotated[bool, _d('true also checks the plan against the rows (counts only, as validate_plan) and drafts 10-20 '
                                'test questions for the agent, each with the T-SQL that gives the right answer, the answer\'s '
                                'shape and the finding it tests. Default false.')]
SilverName = Annotated[str, _name("notebook item", "silver_shop")]
GoldName = Annotated[str, _name("notebook item", "gold_shop")]
MonitorDraftName = Annotated[str, _d('Base name of the notebook and pipeline. Default "" (drift_monitor_<schema>). '
                                     'Example: "drift_shop".')]
MonitorName = Annotated[str, _d('Base name of the notebook and pipeline; existing items with these names are updated '
                                'in place. Example: "drift_shop".')]
PipelineName = Annotated[str, _d('Display name of the pipeline; its check notebook is <name>_check. Existing items with '
                                 'these names are updated in place. Example: "pipeline_shop".')]
PipelineSilverName = Annotated[str, _d('Display name of the silver notebook the pipeline runs, updated in place if it exists. '
                                       'Default "" (silver_<schema>). Example: "silver_shop".')]
PipelineGoldName = Annotated[str, _d('Display name of the gold views notebook the pipeline runs, updated in place if it '
                                     'exists. Default "" (gold_<schema>). Example: "gold_shop".')]
Schedule = Annotated[bool, _d('false (default) creates the items without a schedule: a schedule needs '
                              'DataPipeline.Execute.All, which the hosted app does not request; true adds the daily '
                              'schedule where that permission is granted. Example: true.')]
RunOnce = Annotated[bool, _d('true starts one run of the pipeline after it is created and reads it for up to two minutes '
                             '(per step: Succeeded, Failed or Running, with durations and a link). Default false: nothing '
                             'runs. Needs DataPipeline.Execute.All.')]
PipelineSchedule = Annotated[dict | None, _d(
    'A schedule for the pipeline. Default none: nothing is scheduled. {"every": "day", "at": "06:00"} or {"every": '
    '"hours", "hours": 4, "at": "06:00"}, optional "time_zone" (default "Europe/Stockholm") and "start" (YYYY-MM-DD, '
    'default tomorrow). A schedule Krusgraph made is updated, others are left alone. Needs DataPipeline.Execute.All.')]
AgentLayer = Annotated[str, _d('Which tables the agent reads, one layer only: "source" (default, the source schema), '
                               '"silver" (the silver tables create_silver_notebook writes, else the source), "gold" (the '
                               'gold views, else the source). The plan\'s tables in the other layers are deselected.')]
ExportItems = Annotated[list[str] | None, _d(
    'Which creating tools to export: create_backend, create_semantic_model, create_views, create_silver_notebook, '
    'create_drift_monitor, create_gold_views; or "pipeline", a draft no tool creates (silver, gold, then a check), with '
    'the silver and gold notebooks; or "catalog", item descriptions and tags (alone: no files). Default: all creating '
    'tools. Example: ["create_backend", "pipeline"].')]
ExportNames = Annotated[dict[str, str] | None, _d(
    '{tool: display name} per exported item. Default: <source>_api, <source>_model, silver_<schema>, '
    'drift_monitor_<schema>, gold_<schema>, pipeline_<schema> (its check notebook: <name>_check). '
    'Example: {"create_backend": "shop_api"}.')]
StarterApi = Annotated[str, _d('API for GraphQL item created by create_backend, by name or id.')]
LineageTable = Annotated[str | None, _d('One table to trace: the answer adds what a change to it reaches. Default: none. '
                                        'Example: "orders".')]
LineageFormat = Annotated[Literal["graph", "openlineage"], _d('"graph" (default) or "openlineage": one OpenLineage '
                                    'RunEvent per object, tables as datasets with column names and types, relationship '
                                    'rules and counts in a custom facet; no row values.')]
LineageRuns = Annotated[str | None, _d('A data pipeline or notebook in the workspace, by name or id: the answer is then its '
                                       'latest runs, each activity\'s status, Fabric\'s error text and a heuristic category '
                                       'with a next step, instead of the graph. Default: none. Example: "pipeline_shop".')]
Question = Annotated[str, _d('The question, in Swedish or English. Example: "total amount per customer last month".')]
QuestionTables = Annotated[list[str], _d('Tables the question is about, exact names. Example: ["orders", "customers"].')]
QuestionApi = Annotated[str | None, _d('API for GraphQL item over the source; when given, a GraphQL query is drafted too. '
                                       'Default: none (T-SQL only). Example: "shop_api".')]
Query = Annotated[str, _d('GraphQL query text; mutations and subscriptions are refused. Default "" (then question is '
                          'used). Example: "{ customers(first: 5) { items { customer_id name } } }".')]
Variables = Annotated[dict | None, _d('GraphQL variables for query. Default: none. Example: {"id": 42}.')]
GraphqlQuestion = Annotated[str | None, _d('Instead of query: a question in Swedish or English, built into a query as '
                                           'answer_query_draft does and run. Default: none. Example: "orders per '
                                           'customer".')]
GraphqlTables = Annotated[list[str] | None, _d('With question: the tables it is about. Default: none. Example: '
                                               '["orders", "customers"].')]
GraphqlSource = Annotated[str | None, _d('With question: the lakehouse or warehouse the API reads. Default: none. '
                                         'Example: "demo_lh".')]
SapSchema = Annotated[str, _d('Schema with the SAP tables, as the mirroring or pipeline named it. Default "dbo". Example: '
                              '"sap".')]
SapKeys = Annotated[dict[str, list[str]] | None, _d(
    'Key overrides as in plan_backend, {table: [columns]}; they win over the pack. Default none. Example: '
    '{"vbap": ["mandt", "vbeln", "posnr"]}.')]
SapConfirmed = Annotated[list[dict] | None, _d(
    'Confirmed relationships as in plan_backend; they win over the pack. Default none. Example: [{"source": "vbap", '
    '"source_cols": ["mandt", "vbeln"], "target": "vbak", "target_cols": ["mandt", "vbeln"]}].')]
SapVariant = Annotated[str | None, _d('"ecc" or "s4hana" to consider only that variant\'s tables. Default: the tables '
                                      'present decide. Example: "s4hana".')]
SapExport = Annotated[str, _d('"none" (default), or one export of the plan: "krusgraph" (keys/confirmed), "dab" (Data '
                              'API builder config), "extraction" (tables, keys, delta columns) or "dbt". Example: "dbt".')]
