"""Parameter types of the remote server's tools, with the description each one carries in tools/list
(inputSchema.properties.*.description). The types are exactly the ones the tools had before; only the descriptions are
new. Shared parameters are defined once here and used by every tool that takes them; parameters with a meaning of their
own in one tool are defined next to the shared ones under that tool's name. tests/test_tool_descriptions.py fails when
a parameter has no description."""
from __future__ import annotations

from typing import Annotated

from pydantic import Field


def _d(text: str):
    return Field(description=text)


# ------------------------------------------------------------------ shared ---------------------

Workspace = Annotated[str, _d('Fabric workspace, name or id.')]
Source = Annotated[str, _d('Lakehouse, warehouse or SQL database, name or id.')]
Schema = Annotated[str, _d('Schema in the source. Default "dbo".')]
Keys = Annotated[dict[str, list[str]] | None, _d(
    'Primary keys replacing the inferred ones. Default: inferred. Example: {"order_items": ["order_id", "line_no"]}.')]
Confirmed = Annotated[list[dict] | None, _d(
    'Relationships the user confirmed, added to the plan. Default none. Example: [{"source": "orders", "source_cols": '
    '["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}].')]
TablesShown = Annotated[list[str] | None, _d('Table names or globs to show. Default all. Example: ["sales_*"].')]
TablesOnly = Annotated[list[str] | None, _d('Exact table names to include. Default all.')]
Detail = Annotated[str, _d('"auto" (default: full up to 60 tables, else summary), "full" or "summary".')]
MaxItems = Annotated[int, _d('Cap on counting queries (one per key and relationship), 1–200. Default 60.')]
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
DriftApi = Annotated[str, _d('Existing API for GraphQL item to compare with, by name or id. Example: "shop_api".')]
DriftWritable = Annotated[bool, _d('Whether the update create_backend would make includes mutations, as its writable. '
                                   'Default false. Example: true.')]
AgentName = Annotated[str, _name("data agent", "shop_agent")]
Publish = Annotated[bool, _d('true (default) publishes the agent after creating or updating it; false leaves a draft. '
                             'Example: false.')]
SilverName = Annotated[str, _name("notebook item", "silver_shop")]
GoldName = Annotated[str, _name("notebook item", "gold_shop")]
MonitorDraftName = Annotated[str, _d('Base name of the notebook and pipeline. Default "" (drift_monitor_<schema>). '
                                     'Example: "drift_shop".')]
MonitorName = Annotated[str, _d('Base name of the notebook and pipeline; existing items with these names are updated '
                                'in place. Example: "drift_shop".')]
Schedule = Annotated[bool, _d('true (default) adds the daily schedule to the pipeline; false creates the items without '
                              'one. Example: false.')]
ExportItems = Annotated[list[str] | None, _d(
    'Which creating tools to export: create_backend, create_semantic_model, create_views, create_silver_notebook, '
    'create_drift_monitor, create_gold_views. Default: all. Example: ["create_backend", '
    '"create_semantic_model"].')]
ExportNames = Annotated[dict[str, str] | None, _d(
    '{tool: display name} per exported item. Default: <source>_api, <source>_model, silver_<schema>, '
    'drift_monitor_<schema>, gold_<schema>. Example: {"create_backend": "shop_api"}.')]
StarterApi = Annotated[str, _d('API for GraphQL item created by create_backend, by name or id.')]
LineageTable = Annotated[str | None, _d('One table to trace: the answer adds what a change to it reaches. Default: none. '
                                        'Example: "orders".')]
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
