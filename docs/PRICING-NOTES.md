# Pricing notes (internal, not on the site)

Status: a decision the maintainer has not taken. Since 26 October 2026 the code has two pieces that are ready for it
and change nothing on their own: anonymous usage counting (`fabric_backend/usage.py`: tool, outcome kind, duration, dry
run; no user ids; see docs/OPERATIONS.md) and a dormant entitlement check (`fabric_backend/entitlements.py`, off unless
`KRUSGRAPH_ENTITLEMENTS=1`; how to switch it on is at the end of this note). Nothing bills, nothing knows about
accounts, there is no pricing page.

## What a free tier and a paid tier could contain

The split that follows the product's own shape: reading is free, creating and operating is paid. Reading is what
makes someone trust the tool; creating is where it saves a day of work; operating is what a company pays for
monthly.

| | Free | Paid (per user or per workspace) |
| --- | --- | --- |
| Read-only tools: `list_workspaces`, `list_sources`, `list_tables`, `plan_backend`, `sample_rows`, `validate_plan`, `join_path`, `analyze_schema`, `suggest_relationships`, `describe_backend`, `query_graphql` | yes, one workspace at a time | yes |
| Hand-over drafts: `semantic_model_draft`, `data_dictionary`, `dbt_schema`, `rayfin_connector`, `ontology_draft`, `app_starter`, `app_readiness` | yes, with a visible footer naming the product in the generated files | yes, without the footer |
| Creating tools: `create_backend`, `create_semantic_model`, `create_views`, `create_data_agent`, `create_ontology`, `create_silver_notebook` | `create_backend` for one API per workspace, the others dry run only | all, unlimited |
| `plan_drift`, `lineage` | `plan_drift` yes; `lineage` no | yes, and `lineage` across all items of the workspace |
| Drafts that only read: `silver_notebook_draft`, `answer_query_draft` | yes | yes |
| The nightly drift monitor: `drift_monitor_draft`, `create_drift_monitor` | `create_drift_monitor` as a dry run only | yes |
| Several workspaces in one session, a team's shared connections | no | yes |
| Operations: a daily drift check of the APIs a team created, mail when an API would change, the `impact` of a planned schema change before it is deployed | no | yes (this is the feature that justifies a monthly price; it does not exist yet) |
| The local server and the command line (open source, MIT) | always free, no sign-in | n/a |
| Support | the support page | a named contact, response within a working day |

Counting queries (`validate_plan`, `suggest_relationships`) cost the customer's own Fabric capacity, not ours; that
stays true in both tiers and should be said on the pricing page.

Prices are not proposed here. The reference points to compare against are the per-user prices of the tools a
consultant would otherwise use for the same hand-over work (modelling and documentation tools), and what a day of
that consultant costs; both are known to the maintainer and not written down in this repository.

## What has to be measured per user for this to work

Only what the tiers need, never the content of a call:

- **Who**: the user's object id and tenant id from the validated token (`oid`, `tid`), and the workspace id a call
  names. Nothing about the data: no table names, no query text, no results.
- **What**: the tool name, the outcome kind (`ok`, or the error `kind` the tool answered with), the duration, and for
  creating tools whether it was a dry run.
- **When**: a timestamp. From these three a monthly count per user and per workspace of calls per tool follows,
  which is what a tier limit ("one API per workspace", "lineage is paid") and a usage page need.
- **Nothing else**: not the plan, not the counts a validation found, not the generated TMDL, not the GraphQL
  query. The privacy policy currently says the server stores nothing; a tier model changes that sentence to "stores
  the call records above for N months" and must say so before the first record is written.

Retention: long enough to bill a month and answer a dispute (ninety days is enough), then deleted; aggregated
counts may be kept longer without the user id.

## What it requires technically

1. **A store.** Today there is none by design (in-memory only). The smallest honest option is one table in a Fabric
   SQL database or Azure SQL in the publisher's own tenant, written by the server after each call (fire and forget,
   with a bounded queue so a slow store never slows a tool). The server's `KRUSGRAPH_*` flags pattern applies:
   `KRUSGRAPH_METERING=0` by default.
2. **Entitlement.** A tier per tenant (the simplest unit: the admin who consented is the one who pays) or per user,
   read at call time from the same store and cached in memory for a few minutes. A free tenant hitting a paid tool
   gets the existing error format: `kind: upgrade` with a hint naming the page to upgrade on. No tool changes
   its behaviour otherwise, so the open-source server keeps working for anyone who self-hosts without the flag.
   This part now exists, dormant: see *Switching the entitlement check on* below.
3. **Billing.** Outside the server: an invoice from the company's accounting, or a hosted checkout page that writes
   the tenant's tier into the store. No card data ever touches this code.
4. **A usage page**, per signed-in user, showing their own counts (the same records), and an export for the admin
   of a tenant. This is also what the directory's connector dashboard shows per tool for us; the two should agree.
5. **Terms.** A terms-of-service page and the privacy policy update above; the plugin manifest has a
   `termsOfServiceUrl` field waiting for it.
6. **Tests.** The metering writer with the store mocked, the entitlement check per tool, and a test that proves no
   content field (schema, query, result) ever reaches the store, in the style of the existing "no token reaches the
   logs" tests.

## What not to do

- Do not meter by rows or by data volume; the customer already pays Fabric for that, and measuring it means
  looking at the data.
- Do not make the read-only tools paid; the free tier is the demo and the trust.
- Do not add accounts of our own; the Entra sign-in is the account.
- Do not build any of this before the directory listing is decided and a first paying conversation has happened.

## Switching the entitlement check on (when the maintainer decides)

`fabric_backend/entitlements.py` decides per organisation (the `tid` of the signed-in user) whether a call may use a
paid feature. With `KRUSGRAPH_ENTITLEMENTS` unset or `0` (the default) it never runs and no tool changes; tests lock
that (`tests/test_operations.py::test_entitlements_off_changes_nothing`). With the flag on, a call to a paid feature
from an organisation without it runs nothing and answers:

```json
{"error": "Creating items in Fabric is part of the paid plan, and your organisation does not have it on this server.",
 "kind": "upgrade", "feature": "create",
 "hint": "See https://krusgraph.com/pricing for the plans. The dry run (dry_run=true) is free and shows exactly what would be created. Planning, validation and the drafts stay free."}
```

| Feature | Tools | Paid when |
| --- | --- | --- |
| `create` | `create_semantic_model`, `create_views`, `create_data_agent`, `create_ontology`, `create_silver_notebook` | `dry_run=false` |
| `lineage` | `lineage` | always |
| `drift_monitor` | `drift_monitor_draft`, `create_drift_monitor` | the draft always, the create with `dry_run=false` |

`create_backend` is not in the list: the free tier's "one API per workspace" needs a count of created APIs per
workspace, and that needs the store in *What it requires technically*, which does not exist. Until then
`create_backend` stays free.

Steps, in order, when the decision is taken:

1. Publish the pricing page and the terms (`termsOfServiceUrl` in the plugin manifest). The hint links to
   `KRUSGRAPH_UPGRADE_URL`, or to `/pricing` on the server's own domain when that is unset.
2. Choose where the entitlements live:
   - `KRUSGRAPH_ENTITLEMENTS_SOURCE=env` (default) with `KRUSGRAPH_ENTITLED_TENANTS='{"<tenant id>": ["create", "lineage"], "<tenant id>": ["*"]}'`:
     enough for the first customers; changing it is a new revision.
   - `KRUSGRAPH_ENTITLEMENTS_SOURCE=table` with `KRUSGRAPH_ENTITLEMENTS_TABLE=https://<account>.table.core.windows.net/<table>`:
     one entity per organisation, `PartitionKey` = `tenant`, `RowKey` = the tenant id in lower case, a string property
     `features` (`create,lineage` or `*`). The container app's identity needs "Storage Table Data Reader" on that table
     (`az role assignment create --assignee-object-id <identity principal id> --assignee-principal-type ServicePrincipal
     --role "Storage Table Data Reader" --scope <storage account id>/tableServices/default/tables/<table>`), and the
     app needs `AZURE_CLIENT_ID` (set by `deploy/krusgraph.sh --key-vault`, or by hand). Read for each organisation at
     most every five minutes; a storage error refuses the paid feature for that call and says so, never the free ones.
3. `az containerapp update -n krusgraph -g rg-krusgraph --set-env-vars KRUSGRAPH_ENTITLEMENTS=1 ...` with the variables
   above. Setting it back to `0` turns everything off again at the next revision.
4. Say on `/privacy` and the pricing page that the tenant id is used to look up the plan (it is already processed in
   memory for the fair-use limits).

