# Krusgraph.Modeler: the upload day

2026-11-16, round W12. The founder's steps for the day Microsoft confirms that our tenant can register the workload
name `Krusgraph.Modeler`. Do them in this order, on a laptop with a browser. Each step says what success looks like.
The longer runbook with sources is `docs/WORKLOAD-PUBLISH.md`; this page is the short version for that day.

Nothing here has been run by a build round. No round registers, uploads, publishes or signs in anywhere.

## Where we are (20 November 2026)

- **19 November 2026, about 18:30 UTC:** Gustav uploaded the CI artifact `Krusgraph.Modeler.1.0.1258` (from PR #26's
  CI run 43891633798) in Fabric: **OneLake catalog → Govern → Configurations → Workloads → Publish → Upload workload**.
  The upload stopped only at the name: Fabric said the workload name is not registered, or that the tenant is not
  enrolled in a Partner Center program for it. Nothing was reserved and nothing changed in the tenant.
- What that shows: the package's format passed Fabric's own checks up to the name registration. The only open point is
  on Microsoft's side.
- A Partner Center support case about registering the name is open. Its number is kept outside this repository.
  An open case is a question to Microsoft, not an approval of anything.
- `Org.Krusgraph` **1.0.1395** stays active in the tenant (shown as **Krusgraph (preview)**) and keeps working. It is
  updated through `.github/workflows/workload-package.yml` (`docs/WORKLOAD-PACKAGE-UPDATES.md`), not through this page.
- Since round MOD1 (PR #26 merged), CI builds and validates a fresh `Krusgraph.Modeler.1.0.<N>` artifact on every push
  to `main`, so a current package is ready the day the name is unlocked (step 3).

## Two packages, two jobs: which one to download

| Package | Built by | When | Needs | For |
| --- | --- | --- | --- | --- |
| `Krusgraph.Modeler.1.0.<N>` (artifact of the same name: `.nupkg`, `VALIDATION.md`, `SHA256SUMS.txt`, 90 days) | `.github/workflows/ci.yml`, job **workload** | every push to `main` and every pull request | nothing (the workload app's public client id is in the workflow) | this page: the first upload of the permanent name |
| `Org.Krusgraph.1.0.<N>` (artifact `workload-package-Org.Krusgraph-1.0.<N>`, plus an issue "New workload package ready") | `.github/workflows/workload-package.yml` | a push to `main` that changes the manifest or the package build, once the variable is set | the repository variable `KRUSGRAPH_WORKLOAD_APP_ID` (not set yet) | an update of the live `Org.Krusgraph` |

The two never build the same workload name, so they cannot offer two different packages for one workload. For the
upload day, take only the first one, from a run on **main**.

**One step cannot be undone: confirming the name in step 6.** Everything else can be rolled back (end of this page).

**Not part of this day:** creating, publishing or going live with any Marketplace offer. Never press **Go live** on any
offer, the DEV offer `krusgraph-dev` above all. The Marketplace offer comes later, with its own decisions.

## Before you start (5 minutes)

- Microsoft's answer on the support case says the tenant can now register the name. Keep the case at hand.
- You can sign in as a Fabric administrator of the company tenant, and as an Application Administrator in Entra.
- `Org.Krusgraph` keeps running all day. Do not deactivate or delete it.

## 1. Read Microsoft's answer

1. Open Microsoft's reply to the support case (Partner Center → **Help + support**, or the e-mail).
2. Check that it says the name can be registered by upload, or that Microsoft registered it for us.
3. If it asks you to do something in Partner Center (accept an agreement, link the tenant, choose a program), do only
   that, and nothing with offers.

**Success:** the reply says the tenant may now upload a `[Publisher].[Workload]` name. If it says anything else, stop
here and send the reply to the coordinator.

## 2. Partner Center: a quick check, no changes

1. Partner Center → **Account settings → Tenants**: the company tenant is listed as linked.
2. Partner Center → **Account settings → Programs**: the AI Cloud Partner Program and the Commercial Marketplace show
   as enrolled.

**Success:** both are as before. Do not open **Marketplace offers**; nothing there changes today.

## 3. Get the package

Take the package CI built and checked; building it yourself is the fallback.

1. In a browser: <https://github.com/Krusmaster/fabric-backend/actions/workflows/ci.yml?query=branch%3Amain+is%3Asuccess>
   → open the newest run (event **push**, branch **main**) → scroll to **Artifacts** → click
   `Krusgraph.Modeler.1.0.<N>`. GitHub downloads a zip; unzip it on the laptop. Do not take an artifact from a
   pull request's run, and not a `workload-package-Org.Krusgraph-…` artifact.
2. Inside are three files: `Krusgraph.Modeler.1.0.<N>.nupkg`, `VALIDATION.md` and `SHA256SUMS.txt`.
3. Open `VALIDATION.md`: the first lines say **Result: PASSED** and **XSD check: passed**. The one known gap, the
   license link that is not a Marketplace offer yet, does not stop the upload.

Or in Azure Cloud Shell (Bash), with the GitHub CLI there (`gh auth login` once, as yourself):

```bash
RUN=$(gh run list --repo Krusmaster/fabric-backend --workflow ci.yml --branch main --event push --status success \
        --limit 1 --json databaseId --jq '.[0].databaseId')
ART=$(gh api "repos/Krusmaster/fabric-backend/actions/runs/$RUN/artifacts" \
        --jq '.artifacts[] | select(.name | startswith("Krusgraph.Modeler.")) | .name')
echo "run $RUN, artifact $ART"
gh run download "$RUN" --repo Krusmaster/fabric-backend --name "$ART" --dir ~/modeler
cd ~/modeler && sha256sum -c SHA256SUMS.txt && head -5 VALIDATION.md
```

Then **Manage files → Download** `~/modeler/Krusgraph.Modeler.1.0.<N>.nupkg` to the laptop.

Fallback, building it yourself in Cloud Shell:

```bash
cd ~/fabric-backend && git pull --rebase origin main && git fetch --unshallow 2>/dev/null; true
workload/scripts/build-package --frontend-app-id 853a0cf0-7d35-42b7-b384-26178755a72a
python3 workload/scripts/validate_package.py workload/build/package/Krusgraph.Modeler.1.0.*.nupkg
```

Then **Manage files → Download** the `.nupkg` from `fabric-backend/workload/build/package/`.

**Success:** a file named exactly `Krusgraph.Modeler.1.0.<N>.nupkg` and a validation that says PASSED.

## 4. Entra: add the Krusgraph.Modeler addresses to the workload app

In Azure Cloud Shell (Bash), signed in to the company tenant. This adds four sign-in addresses and one Application ID
URI to the workload app; it removes nothing. It is runbook A1 in `docs/WORKLOAD-PUBLISH.md`.

```bash
APP=853a0cf0-7d35-42b7-b384-26178755a72a
TENANT=$(az account show --query tenantId -o tsv)
OBJ=$(az ad app show --id "$APP" --query id -o tsv)
az ad app show --id "$APP" --query "{spa: spa.redirectUris, uris: identifierUris}" -o json | tee ~/workload-app-before.json
NEW=$(for h in app.fabric.microsoft.com app.powerbi.com msit.fabric.microsoft.com msit.powerbi.com; do
        echo "https://$h/workloadSignIn/$TENANT/Krusgraph.Modeler"; done)
BODY=$( { az ad app show --id "$APP" --query "spa.redirectUris[]" -o tsv; echo "$NEW"; } | sort -u | jq -R . | jq -sc '{spa: {redirectUris: .}}')
az rest --method PATCH --uri "https://graph.microsoft.com/v1.0/applications/$OBJ" --headers Content-Type=application/json --body "$BODY"
az ad app update --id "$APP" --identifier-uris $(az ad app show --id "$APP" --query "identifierUris[]" -o tsv) \
        "https://krusgraph.com/workload/workload/Krusgraph.Modeler"
az ad app show --id "$APP" --query "{spa: spa.redirectUris, uris: identifierUris}" -o json
```

**Success:** the last command lists the old addresses (with `Org.Krusgraph`) **and** four new
`.../workloadSignIn/.../Krusgraph.Modeler` addresses and `https://krusgraph.com/workload/workload/Krusgraph.Modeler`.

## 5. The server: accept tokens for Krusgraph.Modeler

1. In Cloud Shell, `cd ~/fabric-backend` and open `deploy/krusgraph.json` (`code deploy/krusgraph.json`).
2. Set `workload_app_id_uri` to both addresses, the old one first:
   `https://krusgraph.com/workload/workload/Org.Krusgraph,https://krusgraph.com/workload/workload/Krusgraph.Modeler`
3. Leave `workload_allowed_tenants` as it is (the company tenant). Save.
4. Run `bash deploy/krusgraph.sh --update`.

**Success:** the script ends without an error, and the page source of `https://workload.krusgraph.com/` shows two
scopes in `<meta name="krusgraph-engine-scopes">`. An `Org.Krusgraph` Model still opens as before.

## 6. Upload and confirm the name (cannot be undone)

1. Open Fabric (`https://app.fabric.microsoft.com`) as a Fabric administrator.
2. **OneLake catalog → Govern → Configurations → Workloads → Publish → Upload workload** (the path used on 19 November
   2026). Choose `Krusgraph.Modeler.1.0.<N>.nupkg`.
3. The **Confirm workload Name** dialog appears. Read the name letter by letter:
   `K r u s g r a p h . M o d e l e r`. Capital K, capital M, one dot, no spaces, 17 characters.
4. Only if it matches exactly: **Confirm**. If anything differs: **Cancel** and stop.

**Success:** the upload finishes and `Krusgraph.Modeler` is listed under **Govern → Workloads**, next to
`Org.Krusgraph`. If the name error from the ticket comes back, stop: nothing has been reserved, and the reply goes back
to Microsoft.

## 7. Activate and try it in the company tenant

1. Under **Govern → Workloads**, open **Krusgraph.Modeler**, select version `1.0.<N>` → **Add** (or **Activate**).
2. Open a workspace on a Fabric capacity → **+ New item** → **Krusgraph Model** (pick the one under Krusgraph.Modeler).
3. Choose a lakehouse with the synthetic shop data and run **Review**.

**Success:** status **Active in tenant**; the editor opens from `workload.krusgraph.com`, signs in without an error and
shows keys and relationships on the map.

## 8. Tell the coordinator

Send: the version uploaded, the time, a screenshot of **Govern → Workloads** with both workloads, and whether step 7
worked. The next rounds then do: publish to selected test tenants, Microsoft's validator, and later the offer (the
order is `docs/PUBLISHING-READINESS.md`).

**Success:** the coordinator has the version and the screenshot, and the next round can start from them.

## If something goes wrong: rollback

- **The name itself cannot be taken back** once confirmed. Everything below leaves it reserved, which is harmless.
- **A bad version:** under **Govern → Workloads → Krusgraph.Modeler**, add the previous version again, or deactivate
  Krusgraph.Modeler. `Org.Krusgraph` was never touched and keeps working.
- **Sign-in errors in the editor:** check step 4's output first. To undo step 4, `~/workload-app-before.json` holds
  the old lists; put them back with the same `az rest --method PATCH` (body `{"spa": {"redirectUris": [<old list>]}}`)
  and `az ad app update --id "$APP" --identifier-uris <old URIs>`.
- **The server:** set `workload_app_id_uri` back to the `Org.Krusgraph` address alone and run
  `bash deploy/krusgraph.sh --update`.
- **Never** rename, re-upload under another `Krusgraph.*` name, or try another tenant to "fix" a problem: a
  `Krusgraph.*` name is reserved for good at its first confirmed upload. The build refuses any other `Krusgraph.*` name.
