# Delegated permissions per tool

What each tool needs from the signed-in user's token, against what the Entra app asks for today. Nothing here changes
the app: the `az` commands are for the maintainer to run (or not). Scopes are those the Fabric REST specification names
per operation (microsoft/fabric-rest-api-specs, `## Required Delegated Scopes` in each swagger.json, read 25 October 2026).

## What the app has today (README, deploy check `REQUIRED_SCOPES`)

| Resource | Delegated permission | Used by |
| --- | --- | --- |
| Microsoft Graph | `User.Read` | sign-in |
| Power BI Service / Fabric (`00000009-0000-0000-c000-000000000000`) | `Workspace.Read.All` | `list_workspaces`, workspace by name |
| | `Item.Read.All` | `list_sources`, item lookups |
| | `GraphQLApi.ReadWrite.All` | `create_backend`; also reading a GraphQL API's definition (`describe_backend`, `plan_drift`, `app_starter`, `app_readiness`, `answer_query_draft` with `api`): getDefinition takes `GraphQLApi.ReadWrite.All` or `Item.ReadWrite.All`, no read-only scope |
| | `GraphQLApi.Execute.All` | `query_graphql` |
| Azure SQL Database (`022907d3-0f1b-48f7-badc-1ba6abab6d66`) | `user_impersonation` | every tool that reads the SQL analytics endpoint (`list_tables`, `plan_backend`, `validate_plan`, `sample_rows`, the drafts, `join_path`, `data_dictionary`, `dbt_schema`, `create_views`) |

## What each tool needs

| Tool | Fabric REST operation(s) | Delegated permission | Have it? |
| --- | --- | --- | --- |
| `create_backend` | `graphQLApis` create / `updateDefinition` | `GraphQLApi.ReadWrite.All` | yes |
| `create_semantic_model` | `semanticModels` create (`Items_CreateSemanticModel`), `updateDefinition` | `SemanticModel.ReadWrite.All` **or** `Item.ReadWrite.All` | **no** |
| `create_views` | none — T-SQL on the SQL analytics endpoint / warehouse | Azure SQL `user_impersonation` (have), plus the SQL right to create objects: Contributor on the workspace, or `CREATE VIEW` / `ALTER SCHEMA` granted on the endpoint | yes (scope); rights are per workspace |
| `create_data_agent` | `dataAgents` create, `staging/settings`, `staging/datasources`, `…/elements`, `…/fewshots`, `staging/publish` | `Item.ReadWrite.All` (create/update); the staging routes also accept `DataAgent.ReadWrite.All`, but creating the item needs `Item.ReadWrite.All` | **no** |
| `create_ontology` (dry run by default) | `ontologies` create / `updateDefinition` | `Item.ReadWrite.All` | **no** |
| `create_silver_notebook` (dry run by default) | `notebooks` create (`Items_CreateNotebook`) / `updateDefinition` | `Notebook.ReadWrite.All` **or** `Item.ReadWrite.All` | **no** |
| `create_drift_monitor` (dry run by default) | `notebooks` create / `updateDefinition`; `dataPipelines` create (`Items_CreateDataPipeline`) / `updateDefinition`; `dataPipelines/{id}/jobs/execute/schedules` (`BackgroundJobs_ScheduleExecute`) | `Notebook.ReadWrite.All` and `DataPipeline.ReadWrite.All` (or `Item.ReadWrite.All` for both); the schedule also `DataPipeline.Execute.All` **or** `Item.Execute.All` | **no** |
| `answer_query_draft`, `query_graphql` with `question` | the plan (SQL endpoint) and, with an API, `items/{id}/getDefinition`; then the GraphQL endpoint | what the app has (`GraphQLApi.ReadWrite.All` for the definition, `GraphQLApi.Execute.All`, Azure SQL `user_impersonation`) | yes |
| `app_starter` | `items/{id}/getDefinition` on the GraphQL API | `GraphQLApi.ReadWrite.All` (getDefinition has no read-only scope) | yes |
| `lineage` | `semanticModels/{id}/getDefinition` for the semantic models it reads | `SemanticModel.ReadWrite.All` **or** `Item.ReadWrite.All`; without it those models are listed under "could not be read" | **no** (for semantic models) |
| `compare_semantic_model` | `semanticModels/{id}/getDefinition` (`Items_GetSemanticModelDefinition`, format TMDL); with `tmdl` given, none | `SemanticModel.ReadWrite.All` **or** `Item.ReadWrite.All`, and read and write permission on the model; answers `kind: consent` with that scope without it | **no** (by name); yes with `tmdl` |
| `gold_views_draft` | metadata reads only | what the app has | yes |
| `create_gold_views` (dry run by default) | `notebooks` create / `updateDefinition` | `Notebook.ReadWrite.All` **or** `Item.ReadWrite.All` | **no** |
| `export_item_definitions` | metadata reads only (and the SQL endpoint id, as `create_backend`) | what the app has | yes |
| `sample_rows`, `validate_plan` (the sensitivity label) | the label comes with the item `_resolve_source` already reads (`Item.sensitivityLabel`, id only) | what the app has | yes |
| all `*_draft`, `join_path`, `data_dictionary`, `dbt_schema`, `plan_drift` | metadata reads only | what the app has | yes |

Not yet observed live: on 26 October 2026 `create_views` ran against the demo workspace as a dry run only, and
`create_semantic_model` and `create_data_agent` were not run. The `consent` answers above are unit-tested.

Until the permission is added and consented, those tools work in `dry_run=true` (the default) and answer
`kind: consent` with the permission's name when asked to create.

`Item.ReadWrite.All` covers the semantic model, the data agent, the ontology, the notebooks and the pipeline at once;
`SemanticModel.ReadWrite.All`, `Notebook.ReadWrite.All` and `DataPipeline.ReadWrite.All` are narrower and cover one item
type each. The narrow choice is the better one for a connector that is listed publicly; `Item.ReadWrite.All` is one
consent for all of them. Scheduling the drift monitor's pipeline also needs `DataPipeline.Execute.All` (or
`Item.Execute.All`): an execute permission, so the app could then run pipelines as the user; leave `schedule=false` and
add the schedule in the portal if that is not wanted.

## Reading an existing semantic model: why getDefinition (round n12)

`compare_semantic_model` needs a model's relationships with cardinality, direction and active state. The paths checked
on 26 October 2026, least privilege first:

| Path | Scope and permission | Returns relationships? |
| --- | --- | --- |
| Power BI REST *Datasets - Execute Queries In Group* with the DAX `INFO.VIEW.*` functions | `Dataset.Read.All` (read-only), Read and Build on the model; the tenant setting *Semantic Model Execute Queries REST API* | Not as documented: the reference says "Only DAX queries are supported at this time. MDX, INFO functions and DMV queries are not supported" (microsoft/PowerBI-CSharp `sdk/swaggers/swagger.json`, release 5.1.0) |
| XMLA endpoint, read-only | Build on the model; Premium or Fabric capacity | No: "Users with Build semantic model permissions … cannot see internal semantic model metadata" (fabric-docs `enterprise/powerbi/service-premium-connect-tools.md`) |
| Fabric *Get Semantic Model Definition* (TMDL) | `SemanticModel.ReadWrite.All` or `Item.ReadWrite.All`, read and write on the model (fabric-rest-api-specs a96c37a `semanticModel/swagger.json`) | Yes |
| The model's TMDL files from a PBIP folder or Git, passed as `tmdl` | none | Yes |

So the tool reads through getDefinition, the one documented REST path, and takes `tmdl` for anyone without that
permission. `SemanticModel.ReadWrite.All` is the narrower of the two scopes and is the one `create_semantic_model` needs
too. Microsoft's Fabric IQ MCP server reads model metadata with `Item.Read.All` and `Item.Execute.All`
(fabric-docs `iq/connectors/fabric-iq-mcp.md`), but as an MCP server, not a REST API this server can call.

## Sensitivity labels: what is read and what would need more

The Fabric Items API returns an item's Microsoft Purview label as `sensitivityLabel.id` (read-only, `common/definitions.json`
`Item`), so `sample_rows` and `validate_plan` name the id with the scopes the app has. Its display name needs Microsoft
Graph: `GET /security/dataSecurityAndGovernance/sensitivityLabels/{id}` with the delegated `SensitivityLabel.Read`
(admin consent required; microsoft-graph-docs `sensitivitylabel-get.md`). The app does not ask for it, and nothing
calls Graph for labels. No Fabric API exposes column-level labels.

## Adding a permission (maintainer only — not run by any agent)

The permission ids are properties of the Fabric service principal in the tenant, so they are looked up rather than
copied from here. With the app's client id in `$APP_ID`:

```bash
FABRIC=00000009-0000-0000-c000-000000000000

# the id of each delegated permission (oauth2PermissionScopes) on the Fabric service principal
for scope in SemanticModel.ReadWrite.All Item.ReadWrite.All DataAgent.ReadWrite.All Notebook.ReadWrite.All \
             DataPipeline.ReadWrite.All DataPipeline.Execute.All; do
  printf '%s %s\n' "$scope" "$(az ad sp show --id $FABRIC --query "oauth2PermissionScopes[?value=='$scope'].id" -o tsv)"
done

# add what is needed (pick one line, or both); =Scope marks it delegated
az ad app permission add --id "$APP_ID" --api $FABRIC \
  --api-permissions "$(az ad sp show --id $FABRIC --query "oauth2PermissionScopes[?value=='SemanticModel.ReadWrite.All'].id" -o tsv)=Scope"
az ad app permission add --id "$APP_ID" --api $FABRIC \
  --api-permissions "$(az ad sp show --id $FABRIC --query "oauth2PermissionScopes[?value=='Item.ReadWrite.All'].id" -o tsv)=Scope"

# the notebooks and the drift monitor, narrow (or rely on Item.ReadWrite.All above for the first two)
for scope in Notebook.ReadWrite.All DataPipeline.ReadWrite.All DataPipeline.Execute.All; do
  az ad app permission add --id "$APP_ID" --api $FABRIC \
    --api-permissions "$(az ad sp show --id $FABRIC --query "oauth2PermissionScopes[?value=='$scope'].id" -o tsv)=Scope"
done

# check the registration
az ad app permission list --id "$APP_ID" -o table
```

Admin consent for the whole app (the same URL `admin_consent_url()` in `fabric_backend/entra.py` builds; it consents
every configured permission, for the tenant whose admin opens it):

```
https://login.microsoftonline.com/organizations/adminconsent?client_id=<APP_ID>
```

or for one tenant: `https://login.microsoftonline.com/<tenant id>/adminconsent?client_id=<APP_ID>`.

After consent, users sign in again (Claude: Settings → Connectors → the connector → Reconnect) so the new token
carries the scope. `deploy/krusgraph.sh --check` compares the registration against `REQUIRED_SCOPES` in
`deploy/azure_containerapp.py`; add the new scope there in the same change so the check keeps passing.

## Notes

- The connector directory listing should mention any added write scope: the listing text today says the connector
  writes only by creating or updating API for GraphQL items.
- `create_views` needs no new Entra scope. Whether the signed-in user may create a schema and views on a given
  endpoint is a Fabric workspace/SQL permission; Contributor on the workspace is enough on a warehouse and on a
  lakehouse's SQL analytics endpoint.
- `Workspace.ReadWrite.All` is not needed by anything here.
