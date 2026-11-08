# Running the Krusgraph workload in Fabric (development, phase 1)

Round n166, 8 November 2026. These are the founder's steps for the first run of the workload in `workload/`: in a
Fabric workspace, **+ New item** offers **Krusgraph Model**; creating one opens our editor inside Fabric, where you
choose a lakehouse, review keys and relationships, see a dry run and create an API for GraphQL.

Nothing in this round was created, registered or changed in Entra, Azure or Fabric. Every step below is yours, on
**your own laptop** (not an employer computer) and in **your own tenant** (the company tenant of
`docs/WORKLOAD-FEASIBILITY.md`, checklist steps 3 to 6). Nothing here has run against Fabric yet: what the code does is
covered by unit tests (`tests/test_workload_api.py`, `workload/Workload/app/items/ModelItem/ModelItemDefinition.test.ts`),
not by a live run. The items marked **Check on the first run** are what the study left unconfirmed.

The workload name for development is **`Org.Krusgraph`**. The `Org.` form needs no registration. **Never use or upload a
`Krusgraph.*` name**: the first upload reserves that name in the tenant for good, and choosing it is checklist step 9.
Developer mode (DevGateway) uploads nothing to the tenant's workload catalogue.

## What runs where

```
Fabric portal (app.fabric.microsoft.com)
 └─ iframe: the editor, from http://localhost:60006 (StartDevServer.ps1, webpack dev server)
      └─ /workload/v1/review and /build ── forwarded by the dev server ──> http://localhost:8000 (our Python server)
                                                                            └─ on-behalf-of you → Fabric REST and the
                                                                               lakehouse's SQL analytics endpoint
DevGateway (StartDevGateway.ps1) tells Fabric that Org.Krusgraph is served from localhost:60006, for your workspace.
```

The editor asks Fabric for a token for the workload's Entra app; our server accepts only that app's audience on
`/workload/v1/*` (a token for the MCP app is refused there, and a workload token is refused at `/mcp`), and exchanges it
on-behalf-of you with the workload app's own secret. Every read and every created item runs with your own Fabric
permissions. No row values are sent to the editor or saved in the item: `review.json` holds names, types, rules,
decisions and counts.

## 0. On the laptop

| Need | What |
| --- | --- |
| Node.js | an LTS version (22 works for the tests in this repository) |
| PowerShell 7 | `pwsh`; the starter kit's scripts are PowerShell |
| .NET 8 SDK or runtime | DevGateway is a .NET program |
| Azure CLI | `az`; `CreateDevAADApp.ps1` signs in with it and creates the app through Microsoft Graph |
| Python 3.12 and ODBC Driver 18 for SQL Server | our server reads the SQL analytics endpoint over ODBC (`docs/LOCAL.md`, "ODBC") |
| Git | `git clone https://github.com/Krusmaster/fabric-backend` |

## 1. Tenant settings and Developer Mode

In the Fabric admin portal of your tenant (**Admin portal → Tenant settings → Additional workloads**), turn on:

- "Capacity admins and contributors can add and remove additional workloads"
- "Workspace admins can develop partner workloads"
- "Users can see and work with additional workloads not validated by Microsoft"

Then turn on **Fabric Developer Mode** for your user (Fabric's settings, developer settings; the starter kit's setup
guide [S18] has the exact place). Settings can take some minutes to apply.

**Check on the first run:** whether a workload in development runs on a **Fabric trial capacity**. The study found no
page that says so. If the editor does not load on a trial, use the smallest paid F capacity and pause it when idle.

## 2. A workspace with the synthetic shop lakehouse

1. Create a workspace on the capacity, e.g. `krusgraph-dev`. Note its id (the GUID in the URL after `/groups/`).
2. In it, create a lakehouse `shop_lh` with **Lakehouse schemas** turned on.
3. Open a notebook attached to it and run:

   ```python
   %pip install git+https://github.com/Krusmaster/fabric-backend
   from fabric_backend.seed import seed
   seed(spark, schema="shop")
   ```

   Seven tables of invented shop data appear under the schema `shop` (`fabric_backend/seed.py`). Never use a customer's
   or an employer's workspace for this.

## 3. The workload's Entra app: `CreateDevAADApp.ps1`

From the repository's `workload/` folder:

```powershell
pwsh ./scripts/Setup/CreateDevAADApp.ps1 -HostingType FERemote -WorkloadName Org.Krusgraph `
     -ApplicationName "Krusgraph workload (dev)" -TenantId <your tenant id>
```

It signs you in with `az login`, creates a **multitenant app with SPA redirect URIs** (`http://localhost:60006/close` and
the `workloadSignIn` URLs for `Org.Krusgraph`), the delegated permission `Fabric.Extend`, an Application ID URI of the
form `api://localdevinstance/<tenant>/Org.Krusgraph/<random>`, and a client secret valid for 180 days. Copy what it
prints: **Application Id**, **ApplicationIdUri / Audience** and **secret** (shown once). It also prints an admin consent
link; open it as the tenant admin a minute later.

The script makes the app for the editor only. For the editor to call our engine, and for the engine to act on your
behalf, add these in the Entra admin centre (**App registrations → Krusgraph workload (dev)**):

1. **Expose an API → Add a scope**: name `user_impersonation`, who can consent "Admins and users", any display text.
   The scope is then `<ApplicationIdUri>/user_impersonation`.
2. **Manifest**: set `"requestedAccessTokenVersion": 2` (in the `api` section; older manifests call it
   `accessTokenAcceptedVersion`). Our server accepts version 2 tokens only, as it does for the MCP app.
3. **API permissions → Add a permission**, delegated: Power BI Service (Fabric) `Workspace.Read.All`,
   `Item.ReadWrite.All` (or `GraphQLApi.ReadWrite.All`, the scope the dry run names) and `Lakehouse.Read.All`; Azure SQL Database `user_impersonation`. Then **Grant admin consent**.
   These are what the on-behalf-of exchange asks for when it reads the lakehouse and creates the API for GraphQL.

This is a separate app from the Krusgraph MCP app (`https://krusgraph.com/mcp`); do not reuse the MCP app's id or
secret here. When the MCP app is configured on the same server, the server refuses to start if the workload variables
name the MCP app.

**Check on the first run:**

- **SPA or Web redirect type.** The script creates SPA redirects, as Microsoft's tutorial says; the general publishing
  requirements page says "Web application". Developer mode should work with what the script creates; if sign-in in the
  iframe fails with a redirect error, note the message.
- Whether `acquireFrontendAccessToken` returns a token for the scope added in step 1 without a consent prompt (the SDK
  page says full consent prompting is "not yet available"). If the editor shows a sign-in or consent error on the first
  engine call, open the admin consent link again after adding the scope.

## 4. Our server, with the workload's variables

In a terminal at the repository root:

```bash
python -m venv .venv && . .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[server]"
export KRUSGRAPH_WORKLOAD_CLIENT_ID=<Application Id from step 3>
export KRUSGRAPH_WORKLOAD_CLIENT_SECRET=<secret from step 3>
export KRUSGRAPH_WORKLOAD_APP_ID_URI=<ApplicationIdUri from step 3>
export KRUSGRAPH_WORKLOAD_ALLOWED_TENANTS=<your tenant id>    # optional; keeps other tenants out
fabric-backend-server --port 8000
```

(PowerShell: `$env:KRUSGRAPH_WORKLOAD_CLIENT_ID = "..."` and so on.) `KRUSGRAPH_WORKLOAD_SCOPE` defaults to
`user_impersonation`; set it only if you named the scope differently. Leave the MCP variables (`MCP_PUBLIC_URL`,
`ENTRA_*`) unset on the laptop; the workload routes do not need them. With none of the `KRUSGRAPH_WORKLOAD_*` variables
set, `/workload/v1/*` does not exist (404), which is how the hosted service runs today.

Quick check: `curl -i -X POST http://localhost:8000/workload/v1/review` answers **401** with `"kind": "sign_in"` (the
route exists and wants a token). A 404 means the variables did not reach the server.

## 5. The workload: `SetupWorkload.ps1`, `StartDevServer.ps1`, `StartDevGateway.ps1`

From `workload/`:

```powershell
pwsh ./scripts/Setup/SetupWorkload.ps1 -WorkloadName Org.Krusgraph -FrontendAppId <Application Id> -WorkloadDisplayName "Krusgraph"
```

This writes `Workload/.env.dev` (git-ignored). Open it and set:

```
KRUSGRAPH_ENGINE_SCOPE=<ApplicationIdUri>/user_impersonation
KRUSGRAPH_ENGINE_URL=
KRUSGRAPH_ENGINE_DEV_TARGET=http://localhost:8000
```

Check that `ITEM_NAMES=Model` and `WORKLOAD_NAME=Org.Krusgraph`. Then:

```powershell
cd Workload; npm install; cd ..                     # once: the kit's dependencies (a few minutes)
pwsh ./scripts/Setup/SetupDevEnvironment.ps1        # asks for the workspace id from step 2; downloads DevGateway
pwsh ./scripts/Run/StartDevServer.ps1               # terminal 2: the editor on http://localhost:60006
pwsh ./scripts/Run/StartDevGateway.ps1              # terminal 3: registers Org.Krusgraph for your workspace
```

`StartDevGateway.ps1` first builds the manifest package with `nuget` (on macOS and Linux the kit runs it with `mono`). Keep the three terminals (our server, dev
server, DevGateway) open while you work.

## 6. In Fabric: + New item → Krusgraph Model

Open the workspace from step 2 in `app.fabric.microsoft.com`, choose **+ New item**, and look for **Krusgraph Model**.
Fabric's own create dialog asks for a name (e.g. `shop_model`); that is the only way the item is created.

What you should see, view by view:

| View | What is there | What to check |
| --- | --- | --- |
| Empty state | "Choose a lakehouse", the button **Choose lakehouse** (Fabric's own picker), a **Schema** field (`dbo` by default) and **Find keys and relationships**. Ribbon: one tab, **Home**, with Save and Choose source. | Pick `shop_lh`, set the schema to `shop`. |
| Review | The lakehouse and schema as the title; one line with the numbers the engine returned (keys, relationships, open, proposed, accepted, rejected); open questions; then the list: open items first, each with a **K** or **R** pill and its rule (K0–K5, R0–R5, confirmed), **Accept** and **Reject**. Ribbon: Save, Refresh plan, Next, Back. | The seven shop tables' keys and relationships, e.g. `orders.customer_id → customers.customer_id`. Reject one relationship. Save. |
| Choose outputs | **API for GraphQL** ticked, its name (`shop_lh_api` by default); Semantic model, Report, Pipeline, Ontology and Data agent shown as "(later)" and disabled. | Keep the name or change it (letters, digits, underscores). **Preview**. |
| Preview (dry run) | "Dry run: create shop_lh_api"; what changes (counts per kind); the checks that passed; what was left out because of your review; "Not checked: validate_plan…". Nothing has been written yet. | The relationship you rejected is listed as left out. |
| Result | The GraphQL endpoint, the created item's type, name and id, and the steps still left in the portal (introspection, permissions). **Open item** opens the API. | This is the first real creating call: approve it yourself (checklist step 8). |

Close the item and open it again: the editor re-plans with the saved `review.json` as the previous review, so your
Accept and Reject decisions are still there.

**Check on the first run:** how the Krusgraph Model appears in Fabric's **lineage** view. No page the study read says how
a workload declares lineage; the created API's id is saved in the item's `outputs.json` and the API names the lakehouse in
its own definition. Note what lineage shows.

## 7. Removing it again

1. In the workspace, delete the Krusgraph Model item(s) and the API for GraphQL item you created.
2. Stop DevGateway (Ctrl+C in its terminal): Fabric no longer shows Org.Krusgraph or **Krusgraph Model** under
   **+ New item**. Stop the dev server and our server.
3. Turn off Fabric Developer Mode, and the three tenant settings if nothing else needs them.
4. In the Entra admin centre, delete the app **Krusgraph workload (dev)** (App registrations → the app → Delete), and
   remove its consent under Enterprise applications if it is still listed. The secret is gone with it.
5. Delete `workload/Workload/.env.dev` and `workload/build/` on the laptop, and unset the `KRUSGRAPH_WORKLOAD_*`
   variables.

Nothing was uploaded to the tenant's workload catalogue, so there is no workload to deactivate there.

## When something does not work

| You see | Likely cause |
| --- | --- |
| **Krusgraph Model** is not under + New item | DevGateway not running, Developer Mode off, a tenant setting off, or the wrong workspace id in `SetupDevEnvironment.ps1`. |
| The editor stays blank | The dev server is not running on port 60006, or the browser blocks `http://localhost` inside the iframe. |
| "sign-in required" or "invalid token" | The scope in `.env.dev` does not match the exposed scope, the token is version 1 (step 3.2), or the audience in `KRUSGRAPH_WORKLOAD_APP_ID_URI` differs from the app's. |
| "on-behalf-of failed" | The secret is wrong or expired, or the permissions of step 3.3 lack admin consent. |
| `kind: no_access` or `not_found` | Your account cannot read the lakehouse, or the schema name is wrong (`shop`, not `dbo`, for the seed). |
| `kind: would_remove` on Create | An API of that name exists and the update would drop relationships it has. Choose another name in phase 1. |

## Files

| File | What it is |
| --- | --- |
| `workload/` | Fork of `microsoft/fabric-extensibility-toolkit` at commit `dacab1b` (MIT; `workload/LICENSE`) with the HelloWorld item renamed to the Model item |
| `workload/Workload/app/items/ModelItem/` | The editor, the item definition (`review.json`, `source.json`, `outputs.json`, `item.json`, all version 1) and its unit tests |
| `workload/Workload/Manifest/items/ModelItem/` | The item manifest: type `{{WORKLOAD_NAME}}.Model`, display name "Krusgraph Model" |
| `fabric_backend/workload_api.py` | The engine API: `POST /workload/v1/review` and `/build` (API for GraphQL only, dry run by default) |
| `fabric_backend/entra.py` (`WorkloadConfig`) | The workload app's separate audience |
| `tests/test_workload_api.py` | Audience, routes on and off, CORS and frame-ancestors, the review and build answers on the shop schema |

[S18]: https://learn.microsoft.com/fabric/extensibility-toolkit/setup-guide (`docs/WORKLOAD-FEASIBILITY.md`, sources)
