# App (Rayfin, preview): what Microsoft documents, and what the Krusgraph Model does with it

Round n181, 9 November 2026. Fabric Apps (the App item) and Rayfin are in **preview**. Every source below was read on
9 November 2026; the dates in brackets are each Learn page's own "updated" date. Nothing here ran against Fabric in
this round. The editor's App output is covered by unit tests (`tests/test_n181_rayfin_app.py`, `tests/test_rayfin_app.py`,
`workload/Workload/app/items/ModelItem/appWords.test.ts`) against test doubles of Fabric.

## 1. Is there a documented REST API that creates or updates an App item from a definition?

**No definition. There is a documented call that creates an empty App item.**

- The item type is **`AppBackend`**; the portal shows it as "App". *Items - Create App Backend*,
  <https://learn.microsoft.com/rest/api/fabric/appbackend/items/create-app-backend> [6 Nov 2026]: "Create an
  AppBackend in the specified workspace." "The AppBackend item is currently in preview."
  `POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/appBackends`, body `displayName`, `description`,
  `folderId`, `sensitivityLabelSettings`; a long-running operation (201 or 202).
- The operation list (<https://learn.microsoft.com/rest/api/fabric/appbackend/items>) has Create, Delete, Get, List and
  Update App Backend. **Update** (`PATCH .../appBackends/{appBackendId}`) takes only `displayName` and `description`.
  **There is no Get or Update Definition.**
- *Items - Create Item* (<https://learn.microsoft.com/rest/api/fabric/core/items/create-item>) [6 Nov 2026] lists
  "AppBackend — An AppBackend." in its `ItemType`. "OrgApp" is a different item. No type is called "App".
- *Definition Details for Supported Item Types*
  (<https://learn.microsoft.com/rest/api/fabric/articles/item-management/definitions/item-definition-overview>)
  [28 Oct 2026] has **no App or AppBackend definition**.
- What `rayfin up` does is **observed, not documented**. This comes from `@microsoft/rayfin-cli` and
  `@microsoft/rayfin-tools-common` 1.36.2, the latest on npm, published 2 October 2026:
  - `dist/fabric.js` sets `itemType: 'AppBackend'`.
  - `dist/services/fabric/rayfin-item.js` looks the item up by name (`GET .../items?type=AppBackend`) and creates it
    when missing (`POST .../items` with `type` and `displayName`; a code comment says the workload ignores any
    definition).
  - Pages, connectors, functions and secrets go through `/v1/workspaces/{ws}/appBackends/{id}/__private/...` calls
    (`applyconfig`, `connectors`, `webapp/deploy`, ...).
  - Krusgraph does not call undocumented endpoints.

**What the editor does with this.** Create makes the App item by the documented call (Create App Backend). It records
the item's id and plan in `outputs.json` and writes the plan marker into the item's description. The pages, the
read-only connector and the GraphQL API that the connector gets are published by the person with the downloadable
package and the commands (section 5). The card says why: no definition is documented.

## 2. Which delegated scope

- Create App Backend and Update App Backend: "Required Delegated Scopes: Item.ReadWrite.All". The caller needs the
  contributor workspace role. There is no AppBackend-specific scope; the scopes article
  (<https://learn.microsoft.com/rest/api/fabric/articles/scopes>) does not mention AppBackend.
- The workload app (`853a0cf0-7d35-42b7-b384-26178755a72a`) already lists `Item.ReadWrite.All` for the ontology
  (docs/WORKLOAD-DEV.md, step 7). If it was never granted, the App's card says so and Create refuses with the consent
  steps. The package path works without it (section 6).

## 3. Reading the tenant setting

- **Where.** Admin portal → Tenant settings → **Microsoft Fabric** → **Enable Fabric App Items (preview)**
  (<https://learn.microsoft.com/fabric/admin/tenant-settings-index>) [5 Nov 2026]. The setting next to it, "Enable
  anonymous data access for Fabric Apps (Preview)", stays off.
- The Fabric Apps overview (<https://learn.microsoft.com/fabric/apps/overview>) [3 Nov 2026] says: "A Fabric tenant
  administrator must enable the Fabric Apps workload before users can create items."
- **Reading it.** *Tenants - List Tenant Settings*
  (<https://learn.microsoft.com/rest/api/fabric/admin/tenants/list-tenant-settings>) [15 Sep 2026]:
  `GET https://api.fabric.microsoft.com/v1/admin/tenantsettings`. "The caller must be a Fabric administrator or
  authenticate using a service principal." "Required Delegated Scopes: Tenant.Read.All or Tenant.ReadWrite.All."
  "Maximum 25 requests per minute."
- Capacity overrides are listed by *List Capacities Tenant Settings Overrides*, which also needs a Fabric
  administrator. Krusgraph does not read them.
- The setting's `settingName` is not documented. The founder's run of 5 November saw `AppBackendTenant`. The preflight
  matches that name or the title.
- **No documented non-admin way exists.** For anyone who is not a Fabric administrator with `Tenant.Read.All`, the
  preflight says "could not check". Create's own call then decides. Its 403 "The feature is not available" (what
  `rayfin up` answered on 5 November) is shown as the same admin card, never as a generic error.

## 4. Simple choices, no AI

`fabric_backend/rayfin_app.options` turns the plan into rules:

- **Key figures.** A row count per table: Rayfin's `count` takes a numeric column, so a numeric key column, or the
  first numeric column. Each sum measure of the semantic model draft (`semantic_model.suggested_measures`).
- **List pages.** One per table: its latest rows, with personal-data columns left out by name.
- **Charts.** One per measure and dimension reached by one or two links, each named by the dimension's first text
  column that is not personal data.
- **Defaults for shop.** Rows in orders, Rows in order_items, Total quantity. List pages for order_items, orders and
  products. Total quantity by categories (name) and by customers (country).

The ticks are stored in the item (`outputs.json`, `outputs[].app`) and sent with the next Preview and Create.

## 5. Dry run, package and commands

- **What the dry run shows.**
  - The preflight result and the pages.
  - The connector: `rayfin_connector`'s files with `operations: ['read']` over every table, and every link the review
    kept as `@one`/`@many`, R5 `orders.ship_to_id → addresses` included.
  - The API the connector gets: queries only, no mutation types (the per-type actions of the API for GraphQL
    definition with writing off). The founder's hand-made shop_desk_gql allowed mutations on all seven tables and
    missed ship_to_id.
- **The package** (a zip from the card) is laid out for the `dataapp` template:
  - `rayfin/connectors/<schema>/` (the entities and `schema.ts`).
  - `rayfin/tsconfig.json`, the template's own; without it `rayfin up` cannot compile the connector.
  - `src/lib/app-connectors.ts`, beside the template's own `src/lib/connectors.ts`, which stays as it is.
  - `src/pages/*` and `src/App.tsx`, and `KRUSGRAPH-APP.md`.
  - No `declare` fields.
  - `tests/test_rayfin_app.py` runs `tsc -p rayfin/tsconfig.json` and `tsc --noEmit` on it with the pinned
    `@microsoft/rayfin-*` 1.36.2 and TypeScript 5.7.3 (CI's test job, `CI=true`).
- **The commands**, with the workspace filled in:
  1. `npm create @microsoft/rayfin@latest -- <app> --template dataapp --workspace "<workspace>"`
  2. `npx rayfin login` (a person signs in; the editor cannot)
  3. `npx rayfin connector add --type fabric-sqlanalytics --workspace-id <ws> --item-id <SQL endpoint id> --name <schema> --operations read`
  4. Unzip the package at the project's root, then `npx rayfin up --workspace "<workspace>"`
- **Not verified.** Whether `rayfin up` deploys into the App item Krusgraph created (it looks items up by name; name
  the project as the item) has not been tried. Nothing generated here has been deployed or opened in a browser.

## 6. Permissions

| For | Delegated permission (Power BI Service) | Needed? |
| --- | --- | --- |
| Create the App item | `Item.ReadWrite.All` | Only for Create; the package path works without it |
| Read the tenant setting (preflight) | `Tenant.Read.All` | Optional, and only a Fabric administrator's sign-in can use it |

Cloud Shell, maintainer only (the permission ids are looked up, never copied; same pattern as `docs/SCOPES.md`):

```bash
APP_ID=853a0cf0-7d35-42b7-b384-26178755a72a
FABRIC=00000009-0000-0000-c000-000000000000
for scope in Item.ReadWrite.All Tenant.Read.All; do
  az ad app permission add --id "$APP_ID" --api $FABRIC \
    --api-permissions "$(az ad sp show --id $FABRIC --query "oauth2PermissionScopes[?value=='$scope'].id" -o tsv)=Scope"
done
az ad app permission admin-consent --id "$APP_ID"
az ad app permission list --id "$APP_ID" -o table
```

Add `Tenant.Read.All` only if a Fabric administrator should see the setting checked. Without it the preflight says
"could not check" and Create's own answer decides.

## 7. In Claude (MCP)

`rayfin_connector` runs the same preflight before it reads the source. When the setting is off, it answers with the
admin card, `kind: feature_disabled`. When the setting cannot be read, its answer is the connector files as before.
The App package itself is the editor's output; adding a parameter would have taken the hosted tool listing over its
size cap (`tests/test_tool_descriptions.py`).

## 8. What is never touched

- Create writes only the App item it makes, and only under a name no other item has. An App item of that name that
  Krusgraph did not make is refused (`already_exists`).
- An App this Model made is never updated in place; a new name is offered.
- Items made by hand (shop-desk, shop_desk_gql, shop_api) are never read for writing, renamed or removed.
- `outputs.json` holds the ids and plan of exactly what Krusgraph made, so a later cleanup can remove only those.
