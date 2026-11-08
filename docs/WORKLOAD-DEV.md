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

## Hosted (no laptop)

Round n168. The same editor, served by the container app that already serves krusgraph.com, from
**https://workload.krusgraph.com**, and the workload uploaded to your tenant as **`Org.Krusgraph`**: no laptop, no
DevGateway, no Developer Mode. Everything below is done by you in **Azure Cloud Shell** (Bash), the **Entra admin centre**
and **Fabric**, in your own tenant (`d2fcf72a-9b80-451d-868b-8d47af30d8ae`). Nothing in this round was created or changed in
Azure, Entra, DNS or Fabric; what the code does is covered by tests (`tests/test_workload_host.py`,
`tests/test_deploy_workload.py`), not by a live run.

```
Fabric portal (app.fabric.microsoft.com)
 └─ iframe: https://workload.krusgraph.com            ← the container app, host name workload.krusgraph.com
      ├─ /                  the editor (built in the image by the Dockerfile; index.html carries the engine scope)
      ├─ /close             the sign-in redirect page: one script, window.close()
      └─ /workload/v1/*     the engine API, same origin ──> on-behalf-of you → Fabric REST and the SQL endpoint
https://krusgraph.com       the website and /mcp, unchanged
```

On `workload.krusgraph.com` the server answers with nothing but those three: no site pages, no `/mcp`, no `/docs`
(404). Its responses carry `Content-Security-Policy: … frame-ancestors https://*.fabric.microsoft.com
https://*.powerbi.com`, CORS headers only for an origin under those two domains, HSTS, and never a cookie
(`fabric_backend/workload_host.py`).

**Still `Org.Krusgraph`.** The package and the image use that name only. Do not type a `Krusgraph.*` name anywhere,
in any dialog: the first upload of such a name reserves it in the tenant for good (checklist step 9).

### Before you start

- The workload's Entra app from section 3 ("Krusgraph workload (dev)"), with the scope `user_impersonation`, version 2
  tokens and the admin-consented permissions of step 3. If you never ran section 3 on a laptop, run the same
  `CreateDevAADApp.ps1` command in Cloud Shell: switch it to PowerShell (`pwsh`), `git clone` the repository there, and
  run it from `workload/`. Then do steps 3.1–3.3 in the Entra admin centre.
- Its **Application (client) ID** and a **client secret value** (the one `CreateDevAADApp.ps1` printed, or a new one under
  **Certificates & secrets**).
- `krusgraph.com` verified as a custom domain **in this tenant** (Entra admin centre → **Settings → Domain names**,
  status "Verified"). The Application ID URI below uses it; Entra refuses an `https://` URI on a domain it has not verified.
- The three tenant settings of section 1 (Developer Mode is not needed for this path).
- DevGateway stopped if it ever ran: the developer instance and the uploaded workload share the name `Org.Krusgraph`.

### 1. Namecheap: two DNS records

Get the exact values first (reads the app, changes nothing):

```bash
cd ~/fabric-backend && git pull --rebase
bash deploy/krusgraph.sh --update --workload-host --dry-run       # add --from-azure if deploy/krusgraph.json is missing
```

It prints, under "DNS-poster för workload.krusgraph.com":

| Type | Host | Value |
| --- | --- | --- |
| CNAME | `workload` | the container app's address, `<app>.<random>.swedencentral.azurecontainerapps.io` |
| TXT | `asuid.workload` | the app's domain verification id (the same value as the existing `asuid` record) |

In Namecheap: **Domain List → krusgraph.com → Manage → Advanced DNS → Add new record**, once per row, TTL Automatic. Do
not change the existing `@`, `www`, `asuid` and `asuid.www` records. Check from Cloud Shell after a few minutes:
`nslookup workload.krusgraph.com` names the container app's address.

*Undo:* delete the two records in Namecheap.

### 2. Entra: the hosted editor's addresses on the workload app

In the Entra admin centre, **App registrations → Krusgraph workload (dev)**:

1. **Authentication → Single-page application → Add URI**: `https://workload.krusgraph.com/close`. Keep
   `http://localhost:60006/close` and the `workloadSignIn` addresses that are there. Save.
2. **Expose an API → Application ID URI → Edit**, or, to keep the developer URI next to it, in Cloud Shell:

   ```bash
   APP=<Application (client) ID>
   az ad app show --id "$APP" --query identifierUris                 # note what is there now
   az ad app update --id "$APP" --identifier-uris "<the api://localdevinstance/... URI from above>" \
       "https://krusgraph.com/workload/workload/Org.Krusgraph"
   ```

   The form is the resource-ID rule of `docs/WORKLOAD-FEASIBILITY.md`, section 2:
   `https://<verified domain>/<frontend>/<backend>/<workload id>`, here frontend and backend both `workload` (the one
   host serves both). The scope `user_impersonation` stays; it is now also
   `https://krusgraph.com/workload/workload/Org.Krusgraph/user_impersonation`.

**Check on the first run:** whether Fabric's upload accepts this URI form, and whether it wants the `/close` address
under **Web** instead of **Single-page application** (section 3, "SPA or Web redirect type"). If the upload or the sign-in
names the redirect or the URI, note the message; adding the same `/close` address under **Web** as well does no harm.

*Undo:* remove `https://workload.krusgraph.com/close` from Authentication, and run the `az ad app update` line again with
only the URIs `az ad app show` listed before.

### 3. Cloud Shell: the server learns the workload app, then the host name

```bash
cd ~/fabric-backend && git pull --rebase
ls deploy/krusgraph.json || bash deploy/krusgraph.sh --from-azure    # writes the file from the running app if missing

# a) the workload app's secret, stored in the container app (typed hidden; changes nothing on the running server)
read -rsp "Workload app secret (VALUE, hidden): " WS; echo
az containerapp secret set -n krusgraph -g rg-krusgraph --secrets workload-secret="$WS" --output none; unset WS

# b) the workload keys in deploy/krusgraph.json
python3 - <<'PY'
import json, pathlib
p = pathlib.Path("deploy/krusgraph.json"); c = json.loads(p.read_text())
c.update(workload_client_id="<Application (client) ID>",
         workload_app_id_uri="https://krusgraph.com/workload/workload/Org.Krusgraph",
         workload_allowed_tenants="d2fcf72a-9b80-451d-868b-8d47af30d8ae",
         workload_host="workload.krusgraph.com")
p.write_text(json.dumps(c, indent=2) + "\n")
PY

# c) what will change (no build, nothing changed), then the real run
bash deploy/krusgraph.sh --update --workload-host --dry-run
bash deploy/krusgraph.sh --update --workload-host
```

(Use your app and resource group names in a) if they are not `krusgraph` and `rg-krusgraph`; `--dry-run` prints them in
its hint when the secret is missing.) The real run builds the image in Azure, editor included (`az acr build`; the
Dockerfile's first stage runs `npm ci` and the production build, nothing runs on your machine), sets
`KRUSGRAPH_WORKLOAD_CLIENT_ID`, `_APP_ID_URI`, `_ALLOWED_TENANTS`, `_HOST` and `_CLIENT_SECRET=secretref:workload-secret`
in one revision, checks krusgraph.com as before, prints the two DNS records again and, **once the CNAME resolves to the
app**, adds `workload.krusgraph.com` with a managed certificate (`az containerapp hostname add` and `hostname bind
--validation-method CNAME`; a few minutes). If the CNAME does not resolve yet it says so and adds nothing: run the same
last command again later. `--update` keeps workload variables that were set by hand on the app, with one line asking you
to write them into `deploy/krusgraph.json`, as it does for the n159 switches. A full run (no flag) replaces the app's
secret list: it leaves the workload's id and URI out and tells you to repeat a) and c).

Check:

```bash
curl -sI https://workload.krusgraph.com/ | grep -i -E "^HTTP|content-security|strict-transport"   # 200, frame-ancestors, HSTS
curl -s  https://workload.krusgraph.com/close                                                     # <script>window.close();</script>
curl -s -o /dev/null -w "%{http_code}\n" https://workload.krusgraph.com/mcp                        # 404: not the MCP server
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://workload.krusgraph.com/workload/v1/review # 401: the engine wants a token
curl -s https://krusgraph.com/healthz                                                             # the site, unchanged
```

*Undo:* `az containerapp hostname delete --hostname workload.krusgraph.com -n krusgraph -g rg-krusgraph` (the managed
certificate goes with it after a while); set the four `workload_*` keys back to `""`, and remove the variables and the
secret: `az containerapp update -n krusgraph -g rg-krusgraph --remove-env-vars KRUSGRAPH_WORKLOAD_CLIENT_ID
KRUSGRAPH_WORKLOAD_APP_ID_URI KRUSGRAPH_WORKLOAD_ALLOWED_TENANTS KRUSGRAPH_WORKLOAD_HOST KRUSGRAPH_WORKLOAD_CLIENT_SECRET`, then
`az containerapp secret remove -n krusgraph -g rg-krusgraph --secret-names workload-secret`. krusgraph.com and `/mcp` are
not affected by any of it.

### 4. The package: `workload/scripts/build-package`

In Cloud Shell (or from CI; it needs `python3` and `git` only, no nuget, mono or npm):

```bash
cd ~/fabric-backend
bash workload/scripts/build-package --frontend-app-id <Application (client) ID>
```

It writes `workload/build/package/Org.Krusgraph.1.0.<N>.nupkg` (N = the number of commits, so every new checkout gives a
higher version, as each upload must) with the frontend `https://workload.krusgraph.com`, the app id, the item
`Org.Krusgraph.Model` and the Product.json of `workload/Workload/Manifest`. It refuses a non-GUID app id, a frontend off
`krusgraph.com` or with more than one path segment, and any `Krusgraph.*` name. **It uploads nothing.** Download the file
from Cloud Shell (**Manage files → Download**, path `fabric-backend/workload/build/package/…`).

**Check on the first run:** the package is written by this script in the layout `nuget pack` produces, not by
`nuget.exe` itself. If Fabric's upload rejects the file as a package, build it with the starter kit's own script on any
machine with PowerShell and nuget (`pwsh workload/scripts/Build/BuildManifestPackage.ps1 -Environment prod` with a
`Workload/.env.prod` holding `WORKLOAD_NAME=Org.Krusgraph`, `FRONTEND_APPID`, `FRONTEND_URL=https://workload.krusgraph.com`,
`WORKLOAD_VERSION`, `ITEM_NAMES=Model`) and note the message.

*Undo:* delete the file; nothing else was made.

### 5. Fabric: upload `Org.Krusgraph` in your tenant

As a Fabric administrator, in `app.fabric.microsoft.com`: **OneLake catalog → Govern → Workloads** (on some tenants under
**Govern → Configurations → Workloads**) → **Upload workload** → choose the `.nupkg`. Check that the dialog names
**Org.Krusgraph**; if it asks you to confirm any other name, **cancel**. Then activate the uploaded version (the
workload's page → its version → **Activate**). After some minutes, in the workspace of section 2: **+ New item → Krusgraph
Model**. The editor now loads from `https://workload.krusgraph.com`; the views are those of section 6.

**Check on the first run:** where the activation control sits and whether the upload asks for capacities or workspaces
to enable the workload for; note the screens.

*Undo:* in the same place, deactivate the version and remove the workload; delete the Krusgraph Model items first
(section 7, step 1). An `Org.` name reserves nothing.

### Wednesday: the first pilot tenant

The pilot needs the workload published to their tenant id, which in `docs/WORKLOAD-FEASIBILITY.md`, section 5, step 4,
follows the permanent `Krusgraph.<Workload>` name (step 3). That name is yours to choose; this round did not choose or
use one. With it chosen, the same image and host serve the pilot: build the package with that name in a later round,
and add the pilot's tenant id to `workload_allowed_tenants` (comma-separated) before `--update`.

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
| `fabric_backend/workload_host.py` | n168: the hosted editor on `KRUSGRAPH_WORKLOAD_HOST`: its files, `/close`, the engine API, and the headers |
| `workload/scripts/build-package` | n168: the `Org.Krusgraph` package for the hosted editor (Python standard library; uploads nothing) |
| `deploy/azure_containerapp.py` | n168: `--update --workload-host [--dry-run]`, the `workload_*` keys of `deploy/krusgraph.json` |
| `tests/test_workload_host.py`, `tests/test_deploy_workload.py` | n168: host routing and headers; the deploy flags and the package |

[S18]: https://learn.microsoft.com/fabric/extensibility-toolkit/setup-guide (`docs/WORKLOAD-FEASIBILITY.md`, sources)
