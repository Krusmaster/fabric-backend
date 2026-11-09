# Running the Krusgraph workload in Fabric (development, phase 1)

Round n166, 8 November 2026. These are the founder's steps for the first run of the workload in `workload/`: in a
Fabric workspace, **+ New item** offers **Krusgraph Model**; creating one opens our editor inside Fabric, where you
choose a lakehouse, review keys and relationships, see a dry run and create an API for GraphQL.

Nothing in this round was created, registered or changed in Entra, Azure or Fabric. Every step below is yours, on
**your own laptop** (not an employer computer) and in **your own tenant** (the company tenant of
`docs/WORKLOAD-FEASIBILITY.md`, checklist steps 3 to 6). Nothing here has run against Fabric yet: what the code does is
covered by unit tests (`tests/test_workload_api.py`, `workload/Workload/app/items/ModelItem/ModelItemDefinition.test.ts`),
not by a live run. The items marked **Check on the first run** are what the study left unconfirmed.

This page is the development workload, `Org.Krusgraph`. Publishing the permanent name `Krusgraph.Modeler` to selected
pilot tenants (n176) is `docs/WORKLOAD-PUBLISH.md`; the pilot's administrator's steps are `docs/PILOT-ONBOARDING.md`.

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
   Since n174 the item builds more outputs; the permissions each needs are in Hosted, step 7. `Item.ReadWrite.All`
   covers all of them; no Execute permission is ever needed.

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

### 6. After each deploy: a new package version

Round n173 (the editor's check against the rows, the map, the mascots, Accept all). The editor and the engine API are in
the image, so a round that changes `workload/Workload/app/` or `fabric_backend/workload_api.py` reaches Fabric with a
redeploy. The package (`.nupkg`) holds only the manifest: the item's name, the frontend address and the app id. Fabric
keeps the uploaded version until a new one is added, and every upload must carry a higher version than the last. After
a deploy, do all four steps, in this order:

1. **Redeploy** (Cloud Shell, in `~/fabric-backend`):

   ```bash
   git pull --rebase origin main
   bash deploy/krusgraph.sh --update --dry-run      # what will change; nothing is built
   bash deploy/krusgraph.sh --update                # builds the image (editor included) and starts a new revision
   ```

   `--update` keeps the `workload_*` settings from section 3 (deploy/krusgraph.json and the app's variables), so
   `--workload-host` is not needed again. Check that the new route answers (401 without a token is the right answer):
   `curl -s -o /dev/null -w "%{http_code}\n" -X POST https://workload.krusgraph.com/workload/v1/check`.
2. **Build the package again** (same shell, after the pull, so the commit count and the version have grown):

   ```bash
   bash workload/scripts/build-package --frontend-app-id <Application (client) ID>
   ls workload/build/package/                       # Org.Krusgraph.1.0.<N>.nupkg, N higher than the version in Fabric
   ```

   The version is `1.0.<number of commits on this checkout>`, so it is higher than 1.0.877 (the version uploaded on
   8 November 2026) after any later pull. Do not pass `--version` by hand. Download the file (**Manage files →
   Download**, `fabric-backend/workload/build/package/Org.Krusgraph.1.0.<N>.nupkg`).
3. **Add the new version in Fabric** (as a Fabric administrator, `app.fabric.microsoft.com`): **OneLake catalog → Govern
   → Workloads** (on some tenants **Govern → Configurations → Workloads**) → **Org.Krusgraph** → **Upload** (the upload
   of section 5, on the workload that already exists) → choose the new `.nupkg`. Check that the dialog names
   **Org.Krusgraph** and the new version; cancel if it names anything else.
4. **Activate it**: the workload's page → the new version → **Activate**. Then reload the Fabric tab and open
   **shop_krusgraph** in workspace **demo**: the review shows **Check against the rows** in the Home ribbon, the map, and
   Onto, Thinker and Builder.

**Check on the first run:** whether the existing workload's page offers the upload of a version directly or only
through **Upload workload** (both end in the same version list), and whether the old version must be deactivated first;
note the screens.

*Undo:* activate the previous version again on the same page; the image keeps working with either version, since n173
changed no manifest file.

### 7. Round n174: every output, the data product, the data flow

Round n174 (9 November 2026). The editor builds everything the MCP tools build. Nothing in this round ran against
Fabric: the routes, the cards, the refusals, the product and the flow are covered by `tests/test_workload_build.py`
(Fabric REST and the SQL endpoint are the test doubles of the golden tests, on the synthetic shop schema) and the
editor's unit tests (`buildWords.test.ts`, `dataFlow.test.ts`). In this order:

1. **Entra: the permissions the new outputs need** (Entra admin centre, as a Global Administrator or Privileged Role
   Administrator): **App registrations → All applications → Krusgraph workload (dev)** (Application (client) ID
   `853a0cf0-7d35-42b7-b384-26178755a72a`) → **API permissions → Add a permission → Microsoft APIs → Power BI Service →
   Delegated permissions**. Tick what you want the item to build, then **Add permissions** and **Grant admin consent for
   <your organisation> → Yes**:

   | Output | Delegated permission (Power BI Service) | Or |
   | --- | --- | --- |
   | Silver notebook, gold views | `Notebook.ReadWrite.All` | `Item.ReadWrite.All` |
   | Pipeline | `Notebook.ReadWrite.All` and `DataPipeline.ReadWrite.All` | `Item.ReadWrite.All` |
   | Semantic model | `SemanticModel.ReadWrite.All` | `Item.ReadWrite.All` |
   | Semantic model's one refresh after Create (n180) | `Dataset.ReadWrite.All` (Power BI REST; without it the model is created and its card says to refresh it in the portal) | |
   | Report | `Report.ReadWrite.All` and `SemanticModel.ReadWrite.All` (it reads the model's measures) | `Item.ReadWrite.All` |
   | API for GraphQL | `GraphQLApi.ReadWrite.All` | `Item.ReadWrite.All` |
   | Ontology | `Item.ReadWrite.All` | |
   | Data agent | `DataAgent.ReadWrite.All` | `Item.ReadWrite.All` |
   | App (Rayfin, preview), n181 | `Item.ReadWrite.All` (Create App Backend; the package path needs none) | |
   | App preflight, optional (n181) | `Tenant.Read.All` (reads "Enable Fabric App Items (preview)"; only a Fabric administrator's sign-in can) | |

   If step 3.3 already granted `Item.ReadWrite.All`, nothing is missing. **Do not add** `DataPipeline.Execute.All`,
   `Notebook.Execute.All`, `Item.Execute.All` or `Lakehouse.Execute.All`: the item never runs or schedules a notebook
   or a pipeline, and the code never asks for them. After the consent, reload the Fabric tab so the editor signs in
   again with the new permission.

   When the token lacks one, the dry run's card says so, and Create refuses that output with `kind: consent`, the
   permission and these same steps (`workload_api.entra_steps`, with the app's id taken from the server's own
   `KRUSGRAPH_WORKLOAD_CLIENT_ID`). Other outputs of the same build still go ahead.
2. **Redeploy** (Cloud Shell, `~/fabric-backend`), as in step 6.1: `git pull --rebase origin main`, then
   `bash deploy/krusgraph.sh --update --dry-run` and `bash deploy/krusgraph.sh --update`. The editor and the engine API
   are both in the image; no new variable, DNS record or redirect is needed.
3. **Build and upload a new package version**, as in steps 6.2 to 6.4: `bash workload/scripts/build-package
   --frontend-app-id 853a0cf0-7d35-42b7-b384-26178755a72a`, download `Org.Krusgraph.1.0.<N>.nupkg`, **Govern →
   Workloads → Org.Krusgraph → Upload**, then **Activate** the new version. The manifest did not change in n174, so the
   previous version also works with the new image; uploading keeps the version list in step with the deploys.
4. **Try it** in workspace **demo** on **shop_krusgraph**: Next → **Choose what to build** → tick, for example, Silver
   notebook, Gold views, Pipeline, Semantic model and Report, and **Bundle them as one data product** → **Preview**.
   Expect one dry-run card per output, the data flow drawn (click a silver box: its notebook cell unfolds), and the
   product with the domains Krusgraph proposes. **Create** is your call: it creates the items in the workspace (each the
   first real creation of that output from the editor, the founder's approval of `docs/WORKLOAD-FEASIBILITY.md`, phase 3).

**Check on the first run:** whether a report created right after its semantic model draws its visuals (the model is
read back with getDefinition; until the model is refreshed once the report shows no data, as its portal steps say),
and whether the data agent stays unpublished with the editor's draft visible to you only.

### 8. Round n175: schema names, Krusgraph icons and the workload page

Round n175 (9 November 2026, for the meeting with Microsoft on 11 and 13 November). Verified in unit tests only
(`tests/test_schema_case.py` on a case-sensitive double of the SQL endpoint, `tests/test_workload_manifest.py`); nothing
ran against Fabric in this round.

- **Schema name case.** A schema typed as `Shop` when the lakehouse has `shop` is read and queried as `shop` on every
  path (MCP tools, the editor's review, check and build, R5's counting, the creating tools' definitions); table and column
  names in keys and confirmed links are spelled as the metadata spells them too. The answer carries `schema_used`
  ({asked, used, note}); the editor saves the exact name and shows a notification. Two schemas that differ only by case
  answer `schema_ambiguous` with both names, and nothing is counted.
- **Icons and the workload page.** The starter kit's purple images are replaced by the Krusgraph logo mark and the site's
  style (`workload/scripts/build_manifest_images.py` draws all eight: workload icon 64 px, favicon 32 px, item icon 48 px, active item icon 48 px, the New item card's 24 px icon, banner, getting started, quick look).
  Product.json and its strings describe every output, the data product and the data flow; the publisher is Kruse
  Consulting AB; the links are /docs, /support, /privacy, /terms, /it (as the certification link: our IT page until a
  Marketplace offer exists) and the licence. The page tells IT which hosts to allow.
- **Network.** krusgraph.com/it has "Network: hosts to allow" (`#network`); the docs' first-time errors and the table
  below have the symptom.

The manifest changed (images, Product.json, the item's small icon), so this round needs a **new package**, not only a
redeploy. The steps are those of section 6, all four, in this order:

1. **Redeploy** in Cloud Shell: `git pull --rebase origin main`, `bash deploy/krusgraph.sh --update --dry-run`, then
   `bash deploy/krusgraph.sh --update` (the engine's schema fix and the editor's notification are in the image).
2. **Build the package**: `bash workload/scripts/build-package --frontend-app-id <Application (client) ID>`; the version
   is `1.0.<N>` with N above 883 (the version in Fabric on 9 November). Download it from **Manage files → Download**.
3. **Add the version in Fabric**: **OneLake catalog → Govern → Workloads → Org.Krusgraph → Upload**, the new `.nupkg`;
   check that the dialog names Org.Krusgraph and the new version.
4. **Activate it**, reload the Fabric tab. Check: the workload's page shows the Krusgraph banner, publisher Kruse
   Consulting AB, the getting-started steps and the map as quick look; + New item shows the three-dot icon; the
   workspace list and the editor tab show it too. Then open **shop_krusgraph**, type the schema `Shop`, and run the
   review and **Check against the rows**: 7 links, no 42S02, and a notification that `Shop` was read as `shop`.

**Check on the first run:** which of `icon` (the mark alone) and `activeIcon` (the mark on the cream tile) Fabric shows
in the editor tab, and whether the workload page crops the banner; note the screens. The icons have sizes Microsoft's
validator approves (64 px workload icon, 32 px favicon, 48 and 24 px item icons; `tools/hub_readiness.py`, n178).

*Undo:* activate the previous version (1.0.883) again on the same page.

### 9. Round n179: Create one output at a time, the schema picked from a list

Round n179 (9 November 2026), from the founder's live preview and Create at 09:53–09:58 (schema typed `Shop`, eight
outputs, on a phone on a home network). Verified in unit tests only (`tests/test_workload_create.py`,
`workload/Workload/app/items/ModelItem/createEach.test.ts`); nothing ran against Fabric in this round.

**What happened.** Create sent all eight outputs in one `POST /workload/v1/build`. After about 60 s the browser reported
only "Failed to fetch", but the server carried on: demo_lh_silver, demo_lh_gold, demo_lh_pipeline (with
demo_lh_pipeline_check), demo_lh_model, demo_lh_ontology (with its eventhouse, KQL database and graph model) and
demo_lh_agent were created; demo_lh_report and the API were not, and their cards never reached the browser.

**Why, as far as the repository can tell.**

- Not the ingress: Azure Container Apps cuts an HTTP request at 240 s ("Request time out is 240 seconds", *Ingress in
  Azure Container Apps*, learn.microsoft.com/azure/container-apps/ingress-overview, updated 22 October 2026), and the
  answer was lost at about 60 s.
- Not CORS on the hosted editor: it calls `/workload/v1` on its own host (`workload.krusgraph.com`), so the request is
  same-origin. An error answered without CORS headers would explain "Failed to fetch" only with a separate engine URL
  (`KRUSGRAPH_ENGINE_URL`); since n179 every error carries them anyway.
- Possible, and now visible in the log: the container restarting in the middle of the request (0.25 vCPU and 0.5 GiB;
  the liveness probe restarts it after three missed `/healthz` answers 10 s apart), or the phone's connection
  closing (a phone that locks its screen or changes network drops the open request). A build of the shop schema peaks at
  about 95 MB in the tests, so memory is not the first suspect, but the live service also holds the MCP sessions.
- The **API** most likely failed on the schema name: the request carried `Shop` and the lakehouse has `shop` (n175 fixes
  this on every path). The **report** reads the new semantic model's definition right after the model is created; a model
  made moments earlier may not give its definition yet.

**What changed.**

1. The editor sends **one request per output** (every chosen output goes along, `only` names the one to build, so the
   pipeline runs the notebooks chosen with it), in the engine's order (the model before its report), and shows each card
   as waiting, creating, then its own result. The report is sent the id of the model the previous request created. The
   created ids are saved in the item after each output. A request with no answer becomes that card's "no answer yet:
   it may still be running in Fabric; reopen in a minute and choose Create again", never a bare "Failed to fetch"; the
   editor stops waiting at 230 s, before the ingress does. Then one last call (`finish`) gives the data product and the
   data flow from the created ids, calling no tool.
2. **Re-run**: Create sends `skip_built`. An output whose items are all in the workspace, built by this Model or carrying
   Krusgraph's description ("Created by Krusgraph …", "… generated by Krusgraph …", "Krusgraph pipeline …"), is shown
   as already built and nothing is written for it; only the rest is tried. For the 09:58 workspace that means: the six
   items found, the report and the API tried again. An item of that name without Krusgraph's description is still
   refused (`already_exists`).
3. The report tries the new model's definition again after 5, 15 and 30 s; then its card says Fabric's answer and
   "Choose Create again in a minute" (`kind: source_not_ready`).
4. Every error on the workload routes is JSON with the CORS headers, and one JSON line per event goes to the console log:
   `{"krusgraph": "workload", "event": "build_output", "output": "report", "outcome": "ok", "seconds": 12.3,
   "peak_rss_mb": 180}`, `route_failed` and `run_failed` with the exception's type, and `{"krusgraph": "server",
   "event": "start"}` at every start, so a restart in the middle of a Create shows next to it. No token, body or name is
   logged.
5. **The schema is chosen, not typed.** After Choose lakehouse the editor lists the lakehouse's schemas
   (`POST /workload/v1/schemas`, INFORMATION_SCHEMA.SCHEMATA with each schema's number of tables), schemas without
   tables greyed, and preselects the only schema with tables (or `dbo` when it is the only one). The name sent is the
   one the endpoint gives. The text field remains only when the list cannot be read, with the reason.
6. From the preview: the semantic model's card says its tables, active and inactive relationships, measures and date
   table in words (it showed "[object Object]"); generated gold SQL names the rule without the certainty number; the
   flow's bronze names are the lakehouse's (`shop`), and the semantic model, API, ontology and agent say "reads the
   source tables in shop (bronze) directly, not the gold views built in this run", with a note that building them on
   the gold views is a later option. The permissions under each output are folded into a **Permissions** note.

**If the log shows a restart during a Create** (`event: start` in the middle of `build_output` lines, or a
`ContainerAppSystemLogs` entry with `OOMKilled` or a failed liveness probe), give the container more room. The
Consumption plan's next size is 0.5 vCPU and 1 GiB:

```bash
az containerapp update -n <app> -g <resource group> --cpu 0.5 --memory 1.0Gi
```

`deploy/azure_containerapp.py` still writes 0.25 vCPU and 0.5 GiB on a full run; change it there too once a restart is
seen, not before.

**Founder's steps:** a redeploy is enough for the editor and the engine (section 6, step 1); no manifest file changed in
this round, so no new package is needed beyond n175's. Then reopen **shop_krusgraph**: the schema list shows `dbo (no
tables)` and `shop (7 tables)` with shop selected; choose Create on the preview, and the six items of 09:58 show as
already built while the report and the API are tried.

### 10. Round n180: "already built" means built from this plan

Round n180 (9 November 2026), from the founder's re-run at 12:14 CET on **shop_krusgraphtest** (schema `shop`, 7 tables,
7 links including R5 `ship_to_id`, check 13 passed). Create showed demo_lh_silver, demo_lh_gold, demo_lh_pipeline,
demo_lh_model, demo_lh_report, demo_lh_ontology and demo_lh_agent as "already built"; they had been built that
morning from schema `Shop` with 6 links, so only the API was created from the plan on screen, and the cards said
"0 silver table(s)", "0 visual(s)" and "0 table(s) selected" for items that hold them. Verified in unit tests only
(`tests/test_workload_plans.py`, `workload/Workload/app/items/ModelItem/planCards.test.ts`); nothing ran against Fabric.

**What changed.**

1. **Every item a Create writes records its plan**: the review's plan id and schema fingerprint, the exact schema name
   and the number of links left after the review. It is kept in outputs.json (`created[].plan`) and written at the end
   of the item's Fabric description, where Krusgraph's items are already marked, as
   `[Krusgraph plan plan-…, schema shop (sha256:…), 7 links]` (`PATCH /workspaces/{ws}/items/{id}`; the description
   stays within 256 characters, and a failed write leaves the item as it is and is logged as `plan_mark`).
2. **A re-run skips an output only when its items were built from this same plan.** An item recorded with another plan
   gets the card "built from a different plan (schema Shop, 6 links; now shop, 7 links)"; an item Krusgraph built
   before plans were recorded gets "built by Krusgraph, plan unknown (now shop, 7 links)". Nothing is written for either;
   the card offers **Update** (not for a report, which is never updated in place) and **Choose a new name** (the outputs
   view opens with a free name, e.g. `demo_lh_silver_2`). An older build is never taken as current.
3. **Update is a dry run first.** The first Update sends `update: [kind]` with `dry_run: true`: the card shows what the tool
   would write and **Update in Fabric**. Only that second click writes, and the engine requires the dry run's
   `confirm_update` back (`confirm: {kind: …}`); without it the card says `dry_run_first` and nothing is written. Update
   applies to items this Model built or that carry Krusgraph's description; anyone else's item is still refused.
4. **Counts on cards of existing items are what the item holds**, read from its definition where that is one read:
   a notebook's cells (and the gold notebook's views), a report's pages and visuals, a semantic model's tables and
   relationships, a data agent's example questions. Where nothing was read (the pipeline, the API, the ontology, or a
   read that failed) the card shows no count, never a zero.

**Founder's steps:** redeploy (section 6, step 1) and **upload a new package version** of the workload, so the editor in
Fabric has the Update and new-name buttons. Then reopen **shop_krusgraphtest** and choose Create: the seven items of the
morning, and the API of 12:14, show "built by Krusgraph, plan unknown" (they were built before plans were recorded).
Choose Update on each one that should follow the plan on screen (a dry run first, then Update in Fabric), or a new name
to keep the morning's build; the report offers only a new name. A second Create afterwards shows them as already built.

**Addition 4 (the founder's run of 12:40 CET).** demo_lh_report2, built from the editor, showed the right figures
(Orders 60, Order lines 134, Units 324; Units by category Tea 141, Accessories 120, Bikes 63) only after demo_lh_model3
was refreshed by hand; before that every visual said "Error fetching data". Its title read "Overview · 3cd7bfba-…",
and the cards' captions and the slicer's title "Category name" were cut off. Since then:

5. **Create refreshes a semantic model it has just created, once**, and waits for it before the next output (the
   report) is sent: `POST https://api.powerbi.com/v1.0/myorg/groups/{workspace}/datasets/{model}/refreshes` with
   `{"notifyOption": "NoNotification"}`, then `GET …/refreshes?$top=1` every 5 s, at most 24 times (Microsoft Learn,
   *Datasets - Refresh Dataset In Group* and *Datasets - Get Refresh History In Group*, Power BI REST APIs, read
   9 November 2026; required scope `Dataset.ReadWrite.All`; on a shared capacity at most eight refreshes a day). The
   token is the user's, exchanged on-behalf-of for the Power BI audience (`https://analysis.windows.net/powerbi/api`).
   The model's card says **refreshed**, **refreshing** (still running after 120 s: open the report when it is done),
   **refresh failed: reason** (Fabric's error code), or **not refreshed** with the missing permission and the Entra
   steps; except when refreshed, the portal step "Refresh the model once" stays. The dry run says "Create refreshes the
   model once; nothing else is run or scheduled". A model that was updated, found built or named for the report is
   never refreshed. Add `Dataset.ReadWrite.All` to the workload app (step 1's table) for this.
6. **The report's title names the model** ("Overview · demo_lh_model3"): given an id, create_report reads the model's
   display name (`GET /workspaces/{ws}/items/{id}`).
7. **The cards and slicers fit their text at 1280 x 720**: the cards are 120 px high with set sizes (title 11 pt, number
   24 pt, caption 11 pt, smaller only for a long measure name), the slicers 76 px with their header off and a 10 pt
   title. `report.text_problems` checks every card and slicer of a page in the tests. Not yet seen in Fabric.

### 11. Round n181: App (Rayfin, preview), one more output of the plan

Round n181 (9 November 2026). Fabric Apps and Rayfin are in preview. The findings with their sources are in
`docs/RAYFIN-APP.md`; in short, Microsoft documents a call that creates an **empty** App item (Create App Backend,
`POST /v1/workspaces/{ws}/appBackends`, `Item.ReadWrite.All`), and no definition for its pages, connector or API. Verified
in unit tests only (`tests/test_n181_rayfin_app.py`, the `tsc` checks in `tests/test_rayfin_app.py`,
`workload/Workload/app/items/ModelItem/appWords.test.ts`); nothing ran against Fabric.

**What the editor does.**

1. **Choose what to build** has **App (Rayfin, preview)**. **Preview** first checks the tenant setting **Enable
   Fabric App Items (preview)** (`GET /v1/admin/tenantsettings`, only readable by a Fabric administrator with
   `Tenant.Read.All`). Off: a plain card with the setting, where it is (Admin portal → Tenant settings → Microsoft
   Fabric) and the steps for the administrator; nothing else is read or built. Cannot be read: the card says so, and
   Create's own answer decides; its 403 "The feature is not available" is shown as the same admin card.
2. **Ticks, no AI**: key figures (row counts, the semantic model draft's sums), list pages (one per table) and charts
   (a sum by a dimension one or two links away). Shop's defaults: rows in orders and order_items, total quantity;
   order_items, orders and products; quantity by category and by customer country. The ticks are saved in
   `outputs.json` (`outputs[].app`) as soon as they change.
3. **The dry run** shows the pages, the connector (`rayfin_connector`'s files, `operations: ['read']`, every link the
   review kept, R5 `ship_to_id → addresses` included) and its API: queries only, no mutation types. **Download the
   package** (a zip for the `dataapp` template, with `rayfin/tsconfig.json`) and the commands with the workspace filled
   in: `npm create ...`, `npx rayfin login`, `npx rayfin connector add ... --operations read`, `npx rayfin up`.
4. **Create** makes the App item by the documented call, records its id and plan in `outputs.json` and in its
   description, and links to it. The pages go in with the package and the commands: the card says why the editor
   cannot publish them. An App item of that name that Krusgraph did not make is refused; an App Krusgraph made is
   never updated (a new name is offered); shop-desk, shop_desk_gql and shop_api are never written.

**For the founder.**

1. **Redeploy** (Cloud Shell, `~/fabric-backend`): `git pull --rebase origin main`, `bash deploy/krusgraph.sh --update
   --dry-run`, then `bash deploy/krusgraph.sh --update`.
2. **Permissions**: nothing new if `Item.ReadWrite.All` is already granted (step 7). Optional `Tenant.Read.All` for the
   preflight; the `az ad app permission add` and `admin-consent` lines are in `docs/RAYFIN-APP.md`, section 6.
3. **Upload a new package version**: `bash workload/scripts/build-package --frontend-app-id
   853a0cf0-7d35-42b7-b384-26178755a72a`, Govern → Workloads → Upload → Activate (step 6.2 to 6.4). The manifest did
   not change.
4. **Try it** on **shop_krusgraph**: tick App (Rayfin, preview) only → Preview → read the card → Create is your call
   (it creates one empty App item, `<lakehouse>_app`). Then the four commands on your laptop.

### 12. Round n183: a Fluent-style item icon, the logo in the editor, a banner without text

Round n183 (9 November 2026). Checked by `tests/test_n183_site.py` and `tests/test_workload_manifest.py`; nothing ran
in Fabric.

- **The item icon** (`ModelItem_Icon.png` 48 px, `ModelItem_Icon_Small.png` 24 px, `ModelItem_Icon_Active.png` 48 px)
  is Fluent-style: a rounded container with a soft gradient and a slight depth, and Krusgraph's own interior, the three
  connected nodes in Krusgraph's coral, green and violet. It uses no Microsoft colour sequence and no Microsoft product
  shape. The active icon has a warmer container. The workload icon (64 px) and favicon (32 px) stay the Krusgraph logo
  mark, the brand. The guidance followed is Microsoft Learn, *Fabric Extensibility toolkit validation guidelines and
  requirements for items*, 1.2 "Item has a clear icon" and 1.2.1 "Item has a clear active icon"
  (<https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-item>, ms.date 24 February 2026,
  read 9 November 2026): "Filetype icons are comprised of a container and an interior Fluent system icon"; sizes
  "20 / 24 / 32 / 40 / 48 / 64"; "28px in 48px container" and "14px in 24px container"; "The interior icon should be
  centered within the container"; links at 1.5 px, as allowed when "an icon is composed of only/mostly strokes".
  `workload/scripts/build_manifest_images.py` (`fluent_item`) draws them.
- **The editor's logo**: the same 48 px item icon, shown at 24 px at the top left of the ribbon, before the Home tab
  (`app/assets/krusgraph-item-icon.png`; the kit's `Ribbon` has a new optional `logo`).
- **The banner** (`Workload_Hub_Banner.png`) has no text and no logo, only the site's shapes and the three mascots on the
  right. The workload page in Fabric writes the workload's name and description over the banner's left side, where the
  old banner's own "Krusgraph" and tagline overlapped them.

**For the founder.**

1. **Redeploy** (Cloud Shell, `~/fabric-backend`): `git pull --rebase origin main`, `bash deploy/krusgraph.sh --update
   --dry-run`, then `bash deploy/krusgraph.sh --update` (the site's diagram, the home page and the editor's logo).
2. **Upload a new package version**, because the manifest's images changed (new item icons and banner):
   `bash workload/scripts/build-package --frontend-app-id 853a0cf0-7d35-42b7-b384-26178755a72a`, then Govern →
   Workloads → Upload → Activate (step 6.2 to 6.4).
3. **Check**: + New item, the workspace list and the editor tab show the new icon; the editor shows it at the top left;
   the workload page's own text no longer runs into the banner's text.

### 13. Round n184: Fabric item icons on the outputs, one default-name pattern

Round n184 (9 November 2026). Checked by `app/items/ModelItem/fabricIcons.test.ts` (`npm test`) and
`tests/test_workload_fabric_icons.py`; nothing ran in Fabric.

- **The icons.** Each output card in *Choose what to build*, and each card of the dry run (Preview) and of Create,
  shows the Fabric icon of the item type it creates, 20 px, at the left of the card's title, with the item type as alt
  text: Notebook (silver notebook and gold views, both are notebooks), Pipeline, Semantic model, Report, API for
  GraphQL, Ontology, Data agent, App. The icons are never next to the Krusgraph logo or a mascot.
- **The source.** Microsoft Learn, *Microsoft Fabric product, experience, and item icons*
  (<https://learn.microsoft.com/fabric/fundamentals/icons>, ms.date 3 July 2025, read 9 November 2026). Its terms:
  "Microsoft permits the use of these icons in architectural diagrams, training materials, or documentation. You can
  copy, distribute, and display the icons only for the permitted use unless granted explicit permission by Microsoft.
  Microsoft reserves all other rights. Fabric icons are also available as a npm package for use in Microsoft Fabric
  platform extension development." The npm package is `@fabric-msft/svg-icons` (Microsoft's Fabric UX icons), and a
  Fabric workload is platform extension development, so it is the package used, pinned exactly at **12.0.0**
  (`workload/Workload/package.json`, integrity in `package-lock.json`). Its `package.json` says MIT; the package
  carries no licence file, so the permission relied on is the Learn page's, not the metadata. The Learn page's
  "Download icons from GitHub" zip (fabric-samples) is for diagrams and documentation only and is not used. The
  page's don'ts are kept: no cropping, flipping, rotating or changed shapes, and the icons stand for Fabric's item
  types, never for Krusgraph.
- **First choice checked first.** The workload SDK, `@ms-fabric/workload-client` 3.1.1, exposes no item-type icon
  files or components; its `isFabricIcons` flag only lets the host draw icons in its own dialogs.
- **Unmodified.** No icon file is stored in this repository. `webpack.config.js` copies the eight files named in
  `app/items/ModelItem/fabricIcons.json` from `node_modules/@fabric-msft/svg-icons/svg/` to `/assets/fabric-icons/`
  byte for byte, and the editor shows them with `<img>` (no recolouring; the SVGs keep their own gradients). The JSON
  holds each file's SHA-256 at 12.0.0, and the tests compare the installed files with it.
- **API for GraphQL.** Version 12.0.0 has no API for GraphQL item icon, so that card shows the package's
  `generic_placeholder_24_item.svg` (Fabric's generic item icon) with the alt text "API for GraphQL". When a later
  version adds one, change the file and its hash in `fabricIcons.json`.
- **App (Rayfin, preview)** uses `fabric_apps_24_item.svg`, the package's Fabric Apps item icon.
- **Notices.** *About and notices* under *Choose what to build* states the source, the terms and the trademark line,
  also in `THIRD_PARTY_NOTICES.md`:

  Microsoft, Microsoft Fabric and Power BI are trademarks of the Microsoft group of companies.
- **Default names** follow one pattern from the lakehouse: `demo_lh_silver`, `demo_lh_gold`, `demo_lh_pipeline`,
  `demo_lh_model`, `demo_lh_report`, `demo_lh_api`, `demo_lh_ontology`, `demo_lh_agent`, `demo_lh_app`. Before n184
  the API for GraphQL, ticked before a lakehouse was chosen, kept the Model item's name (`demo_api`). Now a name still
  at the earlier default follows the chosen lakehouse, also when a saved item is opened again; a name typed by hand,
  or one an item was already built under, stays.

**Additions from the founder's live Create** (9 November 2026, 19:20 CET, package 1.0.913, all nine outputs created,
the model refreshed by Create). Checked by `app/items/ModelItem/createWords.test.ts` and `tests/test_n184_create_texts.py`.

- **While Create runs**, Builder's line counts what has happened so far ("4 of 9 created, 1 creating, 4 waiting"); it
  said "Nothing was created: each card below says why" while outputs were already in Fabric.
- **The data product's list** names each item by its own type: the pipeline's output holds the silver, gold and check
  notebooks, which are listed as Notebook, as the Open links already did.
- **Plain steps.** The gold card says "Run demo_lh_silver first" (the silver notebook of this Create), not the tool's
  name; no step on a card names a tool (`workload_api.plain_steps`). The report card no longer says
  "export_item_definitions does not include reports", and says "refresh it once" only when Create's refresh of the model
  failed or was skipped for want of a permission.
- **The report's visuals** are counted the same way on both cards: charts, cards, the table and slicers, not the page's
  title and footnote. When Create draws fewer than the dry run did, the card says so: the dry run draws from this build's
  draft of the model, Create from the model as Fabric returns it after creating it, and each visual not drawn is listed
  with its reason. Why the live run drew 8 against 10 was not reproduced here (no live Fabric in CI); the card now names
  the difference the next time it happens.
- **"Updated" pipeline on a fresh workspace.** The pipeline also writes its notebooks, and the silver and gold notebooks
  the same Create had made a moment earlier exist, so the ownership check said "update". Now only the pipeline item
  itself decides: "created" when it did not exist before (`workload_api._ownership`).
- **The App card** says "Empty App item created; its pages and connector come from the package and commands below", and
  the commands are under "Still to do (in a terminal with Node, e.g. Azure Cloud Shell)".
- **A clear finish.** When every chosen output has its answer: a banner, "Done: 9 of 9 created in demo" (green; the name
  is the Krusgraph Model item's, as the editor does not know the workspace's name) or "Done with problems: 7 of 9
  created, 2 failed" (red, amber when outputs only wait for a choice), with each reason; Onto and Builder celebrate when
  the mascots are on and every output is done (they hop only under `prefers-reduced-motion: no-preference`; with the
  mascots off no figure is drawn). Each card's title has a mark: green created, amber created with a step still to do
  (the App's pages, a model Create could not refresh, a report on it) or waiting for a choice, red failed. Under the
  banner, *Next* (run the pipeline, or the silver then gold notebooks; open the report; publish the data agent when its
  answers are right; the App's terminal steps) and *Keep it up to date* (data changes: the pipeline run or a schedule,
  the model is Direct Lake; tables or columns change: open the item, *Check against the rows again*, and Create shows
  what is out of date with Update or a new name). The finish is kept in `outputs.json` as `last_create` and shown again,
  with the date of the last Create, when the item is reopened; an Update on a card changes its line.

**For the founder.**

1. **Redeploy** (Cloud Shell, `~/fabric-backend`): `git pull --rebase origin main`, `bash deploy/krusgraph.sh --update
   --dry-run`, then `bash deploy/krusgraph.sh --update` (the editor at workload.krusgraph.com).
2. **Upload a new package version**: `bash workload/scripts/build-package --frontend-app-id
   853a0cf0-7d35-42b7-b384-26178755a72a`, then Govern → Workloads → Upload → Activate (step 6.2 to 6.4).
3. **Check**: open a Krusgraph Model, *Choose what to build* shows an icon left of each output; Preview and Create
   cards show the same; *About and notices* opens with the trademark line; a new Model on `demo_lh` proposes
   `demo_lh_api`. Create counts "n of 9 created" while it runs, ends with the banner, marks, *Next* and *Keep it up to
   date*, and shows them again when the item is reopened.

### What the editor does since n174

- **Choose what to build**: every output the MCP tools build, each with its name, what it is, and the permission it
  needs. A report is built on the semantic model chosen above, or on one already in the workspace (its name in
  **Built on**). Several at once; the engine runs them in this order: silver notebook, gold views, pipeline, semantic
  model, report, API for GraphQL, ontology, data agent, and since n181 App (Rayfin, preview), `docs/RAYFIN-APP.md`.
- **Preview**: one card per output from that output's own MCP tool (`/workload/v1/build` with `outputs: [{kind, name}]`,
  on-behalf-of you, dry run): what it would create or update, a few facts from the dry run, and anything that would
  stop it. An item of the same name that this Model did not build is never written (`already_exists`: choose another
  name); a report is never updated in place.
- **Data product** (optional): one name over the build, with the domains `domain_draft` proposes for these tables, an
  owner nobody has chosen yet, and the plan's id and schema fingerprint. After Create it is kept in `outputs.json`
  with the created items' ids; re-opening the item shows it, and each output it built is offered as **Update** (the
  tools that update in place) or with a new name (a report).
- **The data flow** (with the silver notebook, the gold views or the pipeline): bronze tables → silver tables (one row
  per key, the links each checks, with the rule pills) → gold views (which silver tables each joins, on which columns)
  → what is built on the source tables; the pipeline's three steps below. Dashed: not part of this build. Builder
  presents it. Click a box, or press Enter or Space on it, to unfold its code below the picture, exactly what the dry
  run sends (a silver box: its notebook cell; a gold box: its CREATE MATERIALIZED LAKE VIEW; a pipeline step: its
  activity; the model: its relationships and measures in TMDL), with **Copy**. One box is open at a time. The flow is
  drawn only in the editor: `create_silver_notebook`, `create_gold_views` and `create_pipeline` have no MCP Apps card in
  Claude yet, so adding the picture there is a card of its own (with its own Create buttons and goldens), not a cheap
  addition to the shared renderer.
- **Result**: each created item with **Open in Fabric**, and the portal steps still left, as the tools say them:
  refresh the semantic model once, introspection and permissions on the API, run the notebooks or the pipeline and add
  a schedule yourself (the item adds none), publish the data agent when it answers well.

### What the editor does since n173

- **Check against the rows** (Home ribbon and a button in the review): `POST /workload/v1/check` runs validate_plan's
  counting queries on the reviewed plan, on-behalf-of the signed-in user with the workload app's audience, as `/review`
  does. Each key and link comes back passed (green), failed (red, with its orphans, duplicates or empty values) or not
  checked (grey), written into `review.json`, so a re-opened item shows its last check and the dry run says what passed
  instead of "Not checked: validate_plan". Counts only, never a row value; nothing in Fabric changes.
- **The map** is the MCP Apps cards' own drawing (n170/n172): `workload/scripts/build_card_map.py` copies
  `fabric_backend/mcp_apps_pictures.py` and the mascots into `cardMap.generated.ts`, and
  `tests/test_workload_check.py` fails when the copy is stale. The editor adds a table's key check and accepted links on
  top (`cardMap.ts`). **List** shows the same keys and links as rows, for the keyboard and screen readers.
- **Onto** (green) says the numbers, **Thinker** (violet) the check and the questions, **Builder** (coral) what comes
  next; the site's figures, a switch turns them off and their sentences are then shown as plain text. Thinker's open
  question (audit_log has no key) comes with its choices inline: keep it without a key, or pick its key column.
- **Accept all** and **Accept all that passed the check**; Accept and Reject per row as before. Accept all never
  overturns a rejection.
- Words: `modelWords.ts`; rule codes stay as pills, with a tooltip that says what the rule means.

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
| `kind: consent` on a card (n174) | The workload app lacks the delegated permission the card names: Hosted, step 7.1, then reload the Fabric tab. |
| `kind: already_exists` on a card (n174) | An item of that name exists and this Model did not build it, or it is a report. Choose another name. |
| **Krusgraph Model keeps loading** in Fabric (n175), or `ERR_SSL_VERSION_OR_CIPHER_MISMATCH` for `workload.krusgraph.com` | A corporate web filter blocks a domain it does not know yet (seen live on 9 November 2026; the server supports TLS 1.2 and 1.3). Ask IT to allow `workload.krusgraph.com` and `krusgraph.com` on port 443, TLS 1.2 or later: the site's [/it#network](https://krusgraph.com/it#network) says what each is for. |
| `Invalid object name 'Shop.addresses'` (42S02) on Check against the rows, or one link fewer than expected | Before n175: the schema was typed in another case than the lakehouse's (`Shop` for `shop`). Since n175 the engine uses the metadata's spelling everywhere and says so (`schema_used`, a notification in the editor). |
| "Failed to fetch" at the top after Create (before n179) | One request carried every output and the browser lost its answer while the server went on (Hosted, step 9). Since n179 each output is its own request; a lost one says "no answer yet" on its card. Reopen in a minute and choose Create again: what was built is skipped. |
| A card says "built from a different plan" or "plan unknown" (n180) | The item of that name was built from another plan (schema spelling, links) or before plans were recorded. Nothing was written. Choose Update (a dry run first) or a new name on the card. |
| A card says `dry_run_first` (n180) | An Update was sent without its dry run's confirmation. Choose Update again: the dry run comes first, then Update in Fabric. |
| A card says `source_not_ready` on the report (n179) | The semantic model was created moments before and Fabric did not give its definition yet. Choose Create again in a minute. |
| `kind: schema_ambiguous` (n175) | Two schemas differ only by case; type the one you mean exactly as the answer lists it. |

## Files

| File | What it is |
| --- | --- |
| `workload/` | Fork of `microsoft/fabric-extensibility-toolkit` at commit `dacab1b` (MIT; `workload/LICENSE`) with the HelloWorld item renamed to the Model item |
| `workload/Workload/app/items/ModelItem/` | The editor, the item definition (`review.json`, `source.json`, `outputs.json`, `item.json`, all version 1) and its unit tests |
| `workload/Workload/Manifest/items/ModelItem/` | The item manifest: type `{{WORKLOAD_NAME}}.Model`, display name "Krusgraph Model" |
| `fabric_backend/workload_api.py` | The engine API: `POST /workload/v1/review`, `/check` (n173) and `/build` (n174: every output, dry run by default) |
| `fabric_backend/entra.py` (`WorkloadConfig`) | The workload app's separate audience |
| `tests/test_workload_api.py` | Audience, routes on and off, CORS and frame-ancestors, the review and build answers on the shop schema |
| `fabric_backend/workload_host.py` | n168: the hosted editor on `KRUSGRAPH_WORKLOAD_HOST`: its files, `/close`, the engine API, and the headers |
| `workload/scripts/build_card_map.py` | n173: copies the MCP Apps cards' map and the mascots into the editor (`cardMap.generated.ts`); `--check` says whether the copy is current |
| `tests/test_workload_check.py` | n173: `/check` (shape, audience, on-behalf-of, a failing check's counts), the inline answers, the copy of the cards' map |
| `fabric_backend/data_flow.py` | n174: the data flow (bronze, silver, gold, pipeline, what is built on the source) from the engine's drafts, each node with the dry run's code |
| `workload/Workload/app/items/ModelItem/buildWords.ts`, `FlowView.tsx`, `dataFlow.ts` | n174: the outputs, cards and product in words; the flow's picture and its folded code |
| `workload/scripts/build_flow_fixture.py` | n174: writes `flow.fixture.json` (the shop schema's flow) for the editor's tests; `--check` says whether it is current |
| `tests/test_workload_build.py` | n174: the build per output (dry run, refusal to overwrite, consent), the product, the flow against the dry run |
| `workload/scripts/build_manifest_images.py` | n175: draws the workload's eight images (logo mark as icon and favicon, the item's icons, banner, getting started, the map as quick look); `--list` gives the sizes |
| `tests/test_workload_manifest.py` | n175: the images (sizes, Fabric's asset rules, every one referenced), Product.json's text and links, the XSDs |
| `tests/test_schema_case.py` | n175: a schema typed in another case, on a case-sensitive double of the SQL endpoint |
| `workload/scripts/build-package` | n168: the `Org.Krusgraph` package for the hosted editor (Python standard library; uploads nothing) |
| `deploy/azure_containerapp.py` | n168: `--update --workload-host [--dry-run]`, the `workload_*` keys of `deploy/krusgraph.json` |
| `tests/test_workload_host.py`, `tests/test_deploy_workload.py` | n168: host routing and headers; the deploy flags and the package |

[S18]: https://learn.microsoft.com/fabric/extensibility-toolkit/setup-guide (`docs/WORKLOAD-FEASIBILITY.md`, sources)
