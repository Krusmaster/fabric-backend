# Entitlements: the dormant paid-feature check

`fabric_backend/entitlements.py` can refuse a paid feature to an organisation that does not have it. It is off unless
`KRUSGRAPH_ENTITLEMENTS=1`, and with it off no tool changes. Nothing bills and nothing knows about accounts; prices are
not part of this repository. A refused call answers in the existing error format, `kind: upgrade`, with a hint naming
the page to upgrade on; the read-only tools, the drafts and every dry run are never refused.

## Switching it on (when the maintainer decides)

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
| `drift_monitor` | `drift_monitor_draft`, `create_drift_monitor` | always, the create's dry run included (it returns the same notebook and pipeline as the draft) |

`create_backend` is not in the list: limiting it would need a count of created APIs per workspace, and that needs a
store of call records, which does not exist (the server keeps nothing between calls). Until then `create_backend` stays
free.

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

## Microsoft Marketplace (n171)

With `KRUSGRAPH_MARKETPLACE=1` next to `KRUSGRAPH_ENTITLEMENTS=1`, the entitlement is the organisation's Marketplace
subscription: a tenant whose best subscription is `Subscribed` has every paid feature, the upgrade answer links to the
offer (`KRUSGRAPH_MARKETPLACE_OFFER_URL`, also returned as `upgrade_url`), and `create_backend` with `dry_run=false` is
paid too (the Fabric editor's Create is that call, and the free tier's count of APIs per workspace does not exist).
Dry runs and the read-only tools stay free. Prices live in Partner Center only. Setup, the fields to fill in and the
DEV offer test: `docs/MARKETPLACE-SETUP.md`.
