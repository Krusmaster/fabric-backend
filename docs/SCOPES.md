# Delegated permissions per tool

What each tool needs from the signed-in user's token, against what the Entra app asks for today. Nothing here changes
the app: the `az` commands are for the maintainer to run (or not). Scopes are those the Fabric REST specification names
per operation (microsoft/fabric-rest-api-specs, `## Required Delegated Scopes` in each swagger.json, read 25 October 2026).

## What the app has today (README, deploy check `REQUIRED_SCOPES`)

| Resource | Delegated permission | Used by |
| --- | --- | --- |
| Microsoft Graph | `User.Read` | sign-in |
| Power BI Service / Fabric (`00000009-0000-0000-c000-000000000000`) | `Workspace.Read.All` | `list_workspaces`, workspace by name |
| | `Item.Read.All` | `list_sources`, `describe_backend`, `plan_drift`, `app_starter`, item lookups |
| | `GraphQLApi.ReadWrite.All` | `create_backend` |
| | `GraphQLApi.Execute.All` | `query_graphql` |
| Azure SQL Database (`022907d3-0f1b-48f7-badc-1ba6abab6d66`) | `user_impersonation` | every tool that reads the SQL analytics endpoint (`list_tables`, `plan_backend`, `validate_plan`, `sample_rows`, the drafts, `join_path`, `data_dictionary`, `dbt_schema`, `create_views`) |

## What each tool needs

| Tool | Fabric REST operation(s) | Delegated permission | Have it? |
| --- | --- | --- | --- |
| `create_backend` | `graphQLApis` create / `updateDefinition` | `GraphQLApi.ReadWrite.All` | yes |
| `create_semantic_model` | `semanticModels` create (`Items_CreateSemanticModel`), `updateDefinition` | `SemanticModel.ReadWrite.All` **or** `Item.ReadWrite.All` | **no** |
| `create_views` | none — T-SQL on the SQL analytics endpoint / warehouse | Azure SQL `user_impersonation` (have), plus the SQL right to create objects: Contributor on the workspace, or `CREATE VIEW` / `ALTER SCHEMA` granted on the endpoint | yes (scope); rights are per workspace |
| `create_data_agent` | `dataAgents` create, `staging/settings`, `staging/datasources`, `…/elements`, `…/fewshots`, `staging/publish` | `Item.ReadWrite.All` (create/update); the staging routes also accept `DataAgent.ReadWrite.All`, but creating the item needs `Item.ReadWrite.All` | **no** |
| `create_ontology` (behind `KRUSGRAPH_ONTOLOGY_WRITE=1`) | `ontologies` create / `updateDefinition` | `Item.ReadWrite.All` | **no** |
| `app_starter` | `items/{id}/getDefinition` on the GraphQL API | `Item.Read.All` | yes |
| all `*_draft`, `join_path`, `data_dictionary`, `dbt_schema`, `plan_drift` | metadata reads only | what the app has | yes |

Until the permission is added and consented, those tools work in `dry_run=true` (the default) and answer
`kind: consent` with the permission's name when asked to create.

`Item.ReadWrite.All` covers the semantic model, the data agent and the ontology at once; `SemanticModel.ReadWrite.All`
is narrower and covers only the first. The narrow choice is the better one for a connector that is listed publicly;
`Item.ReadWrite.All` is one consent for the three.

## Adding a permission (maintainer only — not run by any agent)

The permission ids are properties of the Fabric service principal in the tenant, so they are looked up rather than
copied from here. With the app's client id in `$APP_ID`:

```bash
FABRIC=00000009-0000-0000-c000-000000000000

# the id of each delegated permission (oauth2PermissionScopes) on the Fabric service principal
for scope in SemanticModel.ReadWrite.All Item.ReadWrite.All DataAgent.ReadWrite.All; do
  printf '%s %s\n' "$scope" "$(az ad sp show --id $FABRIC --query "oauth2PermissionScopes[?value=='$scope'].id" -o tsv)"
done

# add what is needed (pick one line, or both); =Scope marks it delegated
az ad app permission add --id "$APP_ID" --api $FABRIC \
  --api-permissions "$(az ad sp show --id $FABRIC --query "oauth2PermissionScopes[?value=='SemanticModel.ReadWrite.All'].id" -o tsv)=Scope"
az ad app permission add --id "$APP_ID" --api $FABRIC \
  --api-permissions "$(az ad sp show --id $FABRIC --query "oauth2PermissionScopes[?value=='Item.ReadWrite.All'].id" -o tsv)=Scope"

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
