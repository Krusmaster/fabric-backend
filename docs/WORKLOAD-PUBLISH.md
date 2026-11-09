# Publishing Krusgraph.Modeler to selected tenants

Round n176, 9 November 2026. The founder's decision of that day: the permanent workload name is **`Krusgraph.Modeler`**
(publisher part `Krusgraph`, workload part `Modeler`). This page is the founder's steps, in order, to publish it to up to
20 selected tenants without Microsoft's review (`docs/WORKLOAD-LISTING-AND-PAYMENT.md`, 1b;
`docs/WORKLOAD-FEASIBILITY.md`, section 5, steps 3–4). What each pilot's own administrator does is in
`docs/PILOT-ONBOARDING.md` and on the site at `/pilot/fabric`.

Nothing here was run by a build round. No round uploads a package, creates or changes an Entra app, or calls Fabric.
Every screen that no primary source shows is marked **check on first run**; write down what Fabric actually shows and
correct this page.

What stays as it is: `Org.Krusgraph` in the company tenant, the founder's development workload, with the same hosted
editor at `https://workload.krusgraph.com` and the same Entra app. Both names run side by side until the founder retires
`Org.Krusgraph`.

## What the build does now

| | `Org.Krusgraph` (default) | `Krusgraph.Modeler` |
| --- | --- | --- |
| Build | `workload/scripts/build-package --frontend-app-id <app id>` | the same, plus `--name Krusgraph.Modeler` |
| Item type | `Org.Krusgraph.Model` | `Krusgraph.Modeler.Model` |
| Who sees it | the company tenant only | the company tenant, plus the tenants on the Publish tab |
| Application ID URI the editor asks for | `https://krusgraph.com/workload/workload/Org.Krusgraph` | `https://krusgraph.com/workload/workload/Krusgraph.Modeler` |

The name is written once, in the build (`build_package.py`, `--name`); the manifest, the nuspec, `Product.json` and the
item manifest take it from there. Any other `Krusgraph.*` name is refused by the build, because its first upload would
reserve it in the tenant for good. The hosted editor is one build for both names: it reads the workload name from the
item it opens (`Krusgraph.Modeler.Model` → `Krusgraph.Modeler`) and asks for the scope of that workload's URI. The
server accepts tokens for every URI in `KRUSGRAPH_WORKLOAD_APP_ID_URI` (a comma list) and lists them in the editor's
page, so no image rebuild is needed when a URI is added.

## Step 1. Entra: the Krusgraph.Modeler addresses on the workload app

The workload app is `Krusgraph workload (dev)`, Application (client) ID `853a0cf0-7d35-42b7-b384-26178755a72a`,
multitenant, in the company tenant `d2fcf72a-9b80-451d-868b-8d47af30d8ae`. Two things are added; nothing is removed.

- **Redirect URIs (Single-page application)**: `https://<host>/workloadSignIn/<tenant>/Krusgraph.Modeler` for
  `app.fabric.microsoft.com`, `app.powerbi.com`, `msit.fabric.microsoft.com` and `msit.powerbi.com`, the four forms
  the starter kit's `CreateDevAADApp.ps1` made for `Org.Krusgraph` [S14 in the feasibility study].
- **Application ID URI**: `https://krusgraph.com/workload/workload/Krusgraph.Modeler`. The resource-ID rule
  (`docs/WORKLOAD-FEASIBILITY.md`, section 2, "Application ID URI"):
  `https://<verified domain>/<frontend>/<backend>/<workload id>`, here frontend and backend both `workload` (one host
  serves both), the workload id `Krusgraph.Modeler`. The scope `user_impersonation` is then also
  `https://krusgraph.com/workload/workload/Krusgraph.Modeler/user_impersonation`.

In Azure Cloud Shell (Bash), signed in to the company tenant:

```bash
APP=853a0cf0-7d35-42b7-b384-26178755a72a
TENANT=d2fcf72a-9b80-451d-868b-8d47af30d8ae
OBJ=$(az ad app show --id "$APP" --query id -o tsv)

# 0. What is there now, kept for the undo below
az ad app show --id "$APP" --query "{spa: spa.redirectUris, uris: identifierUris}" -o json | tee ~/workload-app-before.json

# 1. The SPA redirect URIs: the ones there now, plus the four for Krusgraph.Modeler
NEW=$(for h in app.fabric.microsoft.com app.powerbi.com msit.fabric.microsoft.com msit.powerbi.com; do
        echo "https://$h/workloadSignIn/$TENANT/Krusgraph.Modeler"; done)
BODY=$( { az ad app show --id "$APP" --query "spa.redirectUris[]" -o tsv; echo "$NEW"; } | sort -u | jq -R . | jq -sc '{spa: {redirectUris: .}}')
az rest --method PATCH --uri "https://graph.microsoft.com/v1.0/applications/$OBJ" \
        --headers Content-Type=application/json --body "$BODY"

# 2. The Application ID URIs: the ones there now, plus Krusgraph.Modeler's
az ad app update --id "$APP" --identifier-uris $(az ad app show --id "$APP" --query "identifierUris[]" -o tsv) \
        "https://krusgraph.com/workload/workload/Krusgraph.Modeler"

# 3. Check: the old addresses are all still there, and the new ones are added
az ad app show --id "$APP" --query "{spa: spa.redirectUris, uris: identifierUris}" -o json
```

The `PATCH` replaces the whole SPA list with the list it was given, which is why step 1 reads the current list first and
adds to it. `https://workload.krusgraph.com/close`, `http://localhost:60006/close` and the `Org.Krusgraph` addresses
must still be in the output of step 3.

**Check on first run:** whether the `workloadSignIn` address takes the publisher's tenant (as the kit's script does) or
each pilot's. The kit makes it with the tenant the app lives in; if a pilot's sign-in in the editor fails with a redirect
error that names its own tenant id, add `https://app.fabric.microsoft.com/workloadSignIn/<pilot tenant>/Krusgraph.Modeler`
(and `app.powerbi.com`) the same way, and note it here.

*Undo:* `~/workload-app-before.json` holds the lists from before. Put them back with the same two commands: the `PATCH`
with `{"spa": {"redirectUris": [<the old list>]}}` and `az ad app update --identifier-uris <the old URIs>`.

## Step 2. The server: both URIs, and the pilots' tenants

In Cloud Shell, in `~/fabric-backend` after `git pull --rebase`, edit two keys of `deploy/krusgraph.json`:

```json
"workload_app_id_uri": "https://krusgraph.com/workload/workload/Org.Krusgraph,https://krusgraph.com/workload/workload/Krusgraph.Modeler",
"workload_allowed_tenants": "d2fcf72a-9b80-451d-868b-8d47af30d8ae"
```

then `bash deploy/krusgraph.sh --update`. The first URI stays the one the server used before, so the running
`Org.Krusgraph` editor is unchanged; tokens for either URI are accepted. Opening `https://workload.krusgraph.com/` and
viewing the page source shows both scopes in `<meta name="krusgraph-engine-scopes">`.

**Allowed tenants.** `workload_allowed_tenants` (the server variable `KRUSGRAPH_WORKLOAD_ALLOWED_TENANTS`) is the
comma list of tenant ids whose users the engine answers. Keep the company tenant in it. Each pilot's tenant id is added
here **and** on Fabric's Publish tab (step 4); the two lists are separate, and a pilot needs both.

- Adding a pilot: append `,<pilot tenant id>` to `workload_allowed_tenants`, then `bash deploy/krusgraph.sh --update`.
  The pilot's tenant id goes into `deploy/krusgraph.json` only, which is git-ignored; never into the repository.
- A tenant in Fabric's list but not in this one: the editor opens, and its first call to the engine shows *"Krusgraph is
  not turned on for your organisation yet."* with the tenant id and the pilot page, in the editor's error bar. Nothing
  is read or changed in their workspace. It does not ask the user to sign in again.
- A tenant in neither list does not see the workload at all.
- An empty `workload_allowed_tenants` means every tenant whose administrator consented. Do not leave it empty while
  publishing to selected tenants.

## Step 3. Upload Krusgraph.Modeler

1. Build the package. In Cloud Shell:

   ```bash
   cd ~/fabric-backend && git pull --rebase
   workload/scripts/build-package --name Krusgraph.Modeler --frontend-app-id 853a0cf0-7d35-42b7-b384-26178755a72a
   ```

   It prints `Built …/Krusgraph.Modeler.1.0.<N>.nupkg … item type Krusgraph.Modeler.Model` and uploads nothing. Download
   the file (Cloud Shell: **Manage files → Download**, path `fabric-backend/workload/build/package/…`).
2. In Fabric, as a Fabric administrator: **OneLake catalog → Govern → Workloads → Upload workload**, choose the file
   [L1][L7 in the listing study]. The workloads page path is the one `docs/WORKLOAD-DEV.md` used for `Org.Krusgraph`.
3. **The name dialog.** On the first upload of a `Krusgraph.*` name a **"Confirm workload Name"** dialog appears. Once
   confirmed, "the Workload Name is permanently reserved in your tenant ... and can't be changed" [L1]. Read the name in
   the dialog letter by letter: `Krusgraph.Modeler`. If it shows anything else, cancel. **This is the one step that
   cannot be undone.**
4. Activate the uploaded version (the same way as for `Org.Krusgraph`). **Check on first run:** whether Fabric asks
   for activation separately for a `Krusgraph.*` name or only when publishing.
5. Try it in the company tenant first: a workspace on a Fabric capacity → **+ New item** → **Krusgraph Model**. The
   editor opens from `https://workload.krusgraph.com`; choose a lakehouse with the synthetic shop schema
   (`fabric_backend/seed.py`) and run Review. Both workloads can be
   listed at the same time, with the same display name and publisher (Kruse Consulting AB, in `Product.json`); the
   workload name under **Govern → Workloads** tells them apart. **Check on first run** how **+ New item** shows two
   Krusgraph Model entries.

Each later upload needs a higher version; the build takes `1.0.<commits on main>` by default, so a new build after a
new commit is enough.

## Step 4. Publish to selected tenants

1. In the workload's page under **Govern → Workloads**, open the **Publish** tab [L1].
2. Choose **Selected tenants**, add the pilot's tenant id (up to 20 in all), choose the version, **Publish** [L1].
3. "It might take up to 10 minutes" before the pilot's users see it [L1].
4. Tell the pilot's administrator to follow `/pilot/fabric` (or send `docs/PILOT-ONBOARDING.md`): the tenant setting,
   admin consent, the network, then **+ New item**.
5. The item's outputs (n181): silver notebook, gold views, pipeline, semantic model, report, API for GraphQL, ontology,
   data agent and **App (Rayfin, preview)**. The App needs one more tenant setting, **Enable Fabric App Items
   (preview)** (Admin portal → Tenant settings → Microsoft Fabric), which a pilot turns on only if they want it; the
   editor checks it first and says so (`docs/RAYFIN-APP.md`). Its pages are published by the pilot with `rayfin up`.
6. The pipeline's two choices (n185), both off until the pilot ticks them: **Run once after Create** (one run of the
   pipeline: silver, then gold, then the check, read on the card per step with durations and a link to the run) and
   **Schedule** (daily at a time, or every N hours, in a time zone, default Europe/Stockholm, from a start date; the
   card shows the next run). Both need the delegated permission **`DataPipeline.Execute.All`** (Power BI Service) on
   the workload app, granted with admin consent in the pilot's tenant. Without it the two choices are shown disabled
   with that explanation and the manual steps in Fabric (Run, Schedule), and Create builds the pipeline and runs
   nothing. A Krusgraph schedule is updated on the next Create, never duplicated; a schedule Krusgraph did not make is
   never touched. The run ids and schedule ids are kept in the item's `outputs.json` (`pipeline_jobs`), so a later
   cleanup can remove the schedule (`docs/WORKLOAD-DEV.md`, Hosted, step 14).

**Check on first run:** the exact labels on the Publish tab, whether tenant ids are entered one at a time or as a
list, and what the tab shows once published (state, version, tenant count). Note them here.

**What the pilot sees in Fabric** (from the admin page [L8]; **check on first run** with the first pilot): nothing until
their administrator turns on "Users can see and work with additional workloads not validated by Microsoft". Then the
workload appears under Workloads, with the publisher Kruse Consulting AB, and the item **Krusgraph Model** appears under
**+ New item** in workspaces on a capacity where workloads may be added. The admin page warns that "their data and access
tokens, including name and email, are sent to the publisher" [L8]; `/it` says what Krusgraph keeps.

## Adding the next pilot

1. Their tenant id: add it to `workload_allowed_tenants` and run `bash deploy/krusgraph.sh --update` (step 2).
2. The Publish tab → Selected tenants → add the id → Publish (step 4). Twenty at most.
3. Send them `/pilot/fabric`.

The package is not rebuilt for a new pilot.

## Withdrawing a pilot, or the workload

- **One pilot**: remove their id from the Publish tab and publish again, and remove it from `workload_allowed_tenants`
  (`--update`). Removing it from the server's list stops the engine for them at once; the Fabric list hides the workload.
  **Check on first run** whether Fabric removes the pilot's existing Krusgraph Model items or only hides them. Their
  administrator can also remove the app's consent under **Enterprise applications**.
- **Everyone**: unpublish on the Publish tab (**check on first run** for the exact action), and empty the server's list
  except for the company tenant. The name `Krusgraph.Modeler` stays reserved in the tenant; it is not given back.

## Decision: keep the "dev" app as the production app, or make a new one

**Recommendation: keep the existing app (`853a0cf0-…`) and make it the production app now, before the first pilot
consents.** Rename it in Entra (**App registrations → Krusgraph workload (dev) → Branding & properties → Name**:
`Krusgraph`), so a pilot's administrator sees "Krusgraph" on the consent screen, and leave its id as it is.

Why, from the docs:

- **Consent is to an app id.** Every pilot's administrator grants admin consent to one application id. Moving to another
  app later means every pilot consents again. Whichever app is chosen, it must be chosen before the first pilot.
- **The server holds one workload app.** `entra.WorkloadConfig` takes one client id and one secret for the on-behalf-of
  exchange; both `Org.Krusgraph` and `Krusgraph.Modeler` use it, with two Application ID URIs on the same app (this
  round). A second app would need a second deployment or server changes for two client ids, a second secret to rotate,
  and the permissions of `docs/WORKLOAD-DEV.md` (Hosted, step 7) granted again.
- **What publishing asks of the app is already true of this one**: multitenant ("required for cross-tenant publishing"),
  a resource-ID Application ID URI on the verified domain, the reply URL on the frontend host [L3]. Publisher
  verification (feasibility study, section 5, step 6) is set per app and can be done on this one.

What speaks for a new app, and why it does not outweigh this: the dev app also carries `http://localhost:60006/close` and
the `api://localdevinstance/…` URI, which a production app does not need. Remove them from this app once DevGateway is
no longer used (Authentication → remove the localhost URI; `az ad app update --identifier-uris` without the
`api://localdevinstance` URI). If DevGateway work is needed again, make a separate app for it then, with
`CreateDevAADApp.ps1`; local development does not need the production app. **Check on first run** whether the validator
(feasibility study, section 5, step 10) flags a localhost redirect; it is not in the pages read.

Nothing was created or changed by this round.
