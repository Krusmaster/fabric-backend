# Updating the Fabric workload package

17 November 2026, round W14. The frontend and the engine deploy with the container app. A change to the workload's
**manifest** reaches Fabric only when a Fabric administrator uploads a new `.nupkg` and activates it. The manifest
holds the name, the item types, the icons, the Workload Hub texts, the version, and the Entra app with its frontend URL.

This page covers four things:
- what Microsoft documents about doing that upload automatically;
- the questions to ask Microsoft on 18 November;
- how to run the new tool, `tools/workload_package.py`, which builds, checks and compares the package and uploads
  nothing;
- the automatic build (round WP1, 18 November): when the manifest changes on `main`, CI builds the package and opens
  an issue, so Gustav only downloads and uploads it.

**Where we are (17 November 2026):** Gustav uploaded and activated `Org.Krusgraph` **1.0.1395** by hand (the previous
active version was 1.0.1074). Fabric shows it as **Krusgraph (preview)**. The Workloads page in his tenant is OneLake
catalog > Govern > Configurations > Workloads, direct link
<https://app.fabric.microsoft.com/onelake/govern/org-config/workloads/publish?experience=fabric-developer> (a page for a
person to open; nothing here calls it).

## 1. Findings (official Microsoft sources only)

All pages were read on 17 November 2026. "Updated" is the page's own last-updated date.

**There is no documented API, CLI or PowerShell command that uploads or updates a workload package.** The upload is
done in the Fabric portal only.

| Question | Source | Quote |
|---|---|---|
| Is there a REST API for it? | [Fabric REST API, Admin › Workloads](https://learn.microsoft.com/en-us/rest/api/fabric/admin/workloads), updated 2026-04-13 | It has only Create, Delete and List Workload Assignments, and List Workloads: "Returns all workloads, optionally filtered by assignment status." The List pages add: "Only published workloads are visible." Microsoft's specification repository (`microsoft/fabric-rest-api-specs`, commit 3f8600f9, `admin/swagger.json`) has the same four operations, and no `nupkg` or upload operation anywhere. |
| How is a package uploaded? | [Publish your workload (toolkit tutorial)](https://learn.microsoft.com/en-us/fabric/extensibility-toolkit/tutorial-publish-workload), updated 2026-09-29 | "Go to **OneLake catalog** > **Govern** > **Configurations** > **Workloads**. Select **Upload workload**." The [Workload Development Kit page](https://learn.microsoft.com/en-us/fabric/workload-development-kit/manage-workload) (ms.date 2026-04-29) says the same. |
| Does the toolkit's own script upload it? | `microsoft/fabric-extensibility-toolkit`, commit dacab1b, `scripts/Deploy/DeployToAzureWebApp.ps1`, lines 411 and 419–420 | "TODO: Go to the Fabric Admin Portal and upload the manifest package:" and "Automatic manifest deployment is not yet implemented." `scripts/Build/BuildRelease.ps1`, line 91: "You can now upload the manifest package and the app release to the Fabric portal." |
| Does the Fabric CLI do it? | [Fabric command line interface](https://learn.microsoft.com/en-us/rest/api/fabric/articles/fabric-command-line-interface), ms.date 2025-04-22 | It covers install and sign-in only. The `microsoft/fabric-cli` repository (commit 5b504195) has no workload or package command. |
| Who may upload? | tutorial-publish-workload | "A Fabric account with admin permissions." and "Sign in to Fabric with an admin account." No scope is documented, because there is no API. For comparison, the workload *assignment* APIs need "a Fabric administrator or … a service principal" with `Tenant.ReadWrite.All`. |
| Version rules | tutorial-publish-workload | "Each uploaded NuGet package must have a unique version number. If you try to upload a package with a version that already exists, you get a **This package has already been uploaded** error… increment the minor version." To change versions: "Select the version you want to activate and select **Add**." |
| Shipping to other tenants | [Publish workload flow](https://learn.microsoft.com/en-us/fabric/extensibility-toolkit/publish-workload-flow), updated 2026-09-29 | "go to the **Publish** tab… add up to 20 tenant IDs… Select a version and then select **Publish**." "It might take up to 10 minutes after publishing before the workload is visible in target tenants while the Workload Name propagates." For Preview: "Submit publishing request… to move to Preview". For GA: "submit the publishing request again to remove the preview badge". |
| What the customer does | [Consume workloads](https://learn.microsoft.com/en-us/fabric/extensibility-toolkit/consume-workloads), ms.date 2025-12-15 | Tenant, capacity or workspace administrators add a published workload. "Enable automatic updates where appropriate", but the page does not explain how that works. |

**What this means for Krusgraph:**
- An update is always the same steps: build a new package with a new version, upload it in the portal as a Fabric
  administrator, and activate it.
- For `Krusgraph.Modeler`, a version then reaches other tenants through the portal's Publish tab. The package lives in
  Fabric after the upload, so customers do not upload it themselves.
- An organisational workload such as `Org.Krusgraph` is uploaded per tenant.

**Not documented (unknowns):**
1. Any API, CLI or PowerShell for uploading or activating a package, or for publishing a version.
2. Whether "admin" means a Fabric administrator, or whether a capacity administrator is enough.
3. Whether a new published version reaches customer tenants automatically, and how "automatic updates" works.
4. Whether each new version after Preview or GA needs another publishing review.
5. Whether versions must increase, or only be unique. Our versions always increase, so both rules hold.
6. How long a new version (as opposed to a new name) takes to reach other tenants.

## 2. Three questions for Microsoft, 18 November

1. **Automation:** Is there a supported or planned API, or Fabric CLI command, to upload a workload package and
   activate a version? This covers the development workload in our own tenant and, after registration, the publisher
   tenant's Publish step. Which role and which delegated or application permission would it require? We want to build
   on every merge and upload only after our own approval, without any portal-only step.
2. **Updates to customers:** Once `Krusgraph.Modeler` is in Preview or GA, how does a new version reach customer
   tenants? Is it automatic once we publish it, or does each tenant's administrator act? Which manifest changes start a
   new publishing review or a new consent? Examples: an item type, the Workload Hub texts, a new Entra app or scope.
3. **Versions and rollback:** Must each version be higher than the last, or only unique? Can we roll customers back by
   activating or publishing an earlier version? How long does a new version take to reach published tenants?

## 3. The tool: `tools/workload_package.py`

One command, run from the repository root, in Azure Cloud Shell or anywhere with `python3` and `git`:

```sh
git clone https://github.com/Krusmaster/fabric-backend.git && cd fabric-backend
python3 -m pip install --user pytest pillow             # for the manifest tests (step 3); Cloud Shell has pip
bash tools/workload-package.sh --frontend-app-id <the workload app's Application (client) ID>
```

These three lines work in a clean Cloud Shell (Python 3.12) since round WP1. On 17 November they did not: the tool also
ran workload tests that import the server (`starlette`, then the full server extras), and those stopped at collection
("No module named 'starlette'"). Now the tool runs only the manifest tests that need pytest and pillow, and names the
others as run in CI. To run those here too, install the server extras once from the repository root and add
`--full-tests`:

```sh
python3 -m pip install --user -e '.[server,test]'
bash tools/workload-package.sh --frontend-app-id <id> --full-tests
```

What it does, in order:

1. **Builds** the `.nupkg` from `workload/Workload/Manifest` with `workload/scripts/build_package.py`, which is the
   same build as `workload/scripts/build-package` and CI's artifact. The tool does not change that script. The file goes to
   `workload/build/package/` (git-ignored), or to the folder given with `--out`.
2. **Chooses the version.** It is one patch above the last package (`--bump minor|major` for the others, or
   `--version 1.0.N`). It is never below `1.0.<commits on this checkout>`, the number the build has always used, never
   below one patch above the highest `workload-pkg/1.0.N` tag (the packages CI has offered; a plain `git clone`
   fetches the tags), and never below **1.0.1396** (`--min-version`; 1.0.1395 is active). So it also grows on a fresh
   clone, with no earlier package to read. A shallow clone stops with a message; run `git fetch --unshallow`.
3. **Checks** the manifest:
   - first `build_package.check()`: the name, the frontend URL and app id, the image sizes, and the Workload Hub fields
     for `Krusgraph.Modeler`;
   - then the repository's manifest tests that need only pytest and pillow: `tests/test_workload_manifest.py` (with
     the XSD validation when `xmllint` is installed), `test_n201_manifest.py` and `test_workload_package_names.py`. They
     run with `--noconftest`, because `tests/conftest.py` imports the server;
   - the server-dependent workload tests (`test_workload_build.py`, `test_workload_publish.py`,
     `test_wp1_workload_server_pages.py`) run too when the server extras are installed. Otherwise the tool prints that
     they were not run here and that CI runs them. `--full-tests` (used by CI) makes their absence a stop;
   - if the tests fail, the package is removed;
   - without pytest or pillow the tool stops and prints the one command to run: `python3 -m pip install --user pytest
     pillow`. `--skip-tests` builds anyway and prints that the tests were not run.
4. **Prints what changes for Fabric**, compared with the last package:
   - which package counts as the last one: the newest `<name>.<version>.nupkg` in the output folder, or
     `--previous <file>`, or `--previous-ref <git ref>` (the manifest at the commit you uploaded last, built the same
     way);
   - what is compared: the version, the workload name, the item types, the frontend Entra app and URL, each changed
     `Product.json` field and Workload Hub text, and added, removed or changed images;
   - a changed name or item type is flagged, because Fabric reserves a name for good at its first upload.
5. **Stops** and prints the Admin-portal steps with the file's path. It opens nothing.

`--upload` says that no documented API exists, sends nothing, and prints the same steps. The tool never calls the
portal's own endpoints. The upload code path is in place for the day Microsoft documents an API:
- `UPLOAD_API` gets that page's URL, scope and role;
- the tool then signs in through `az account get-access-token`, with no secret stored and no client secret;
- `--dry-run` shows what would be sent;
- it sends only after you type the package's name and version.

Tests: `tests/test_w14_workload_package.py` covers the build, the version rules, the diff, a failing manifest test,
`--skip-tests`, a missing pytest, a refused name, `--previous` and `--previous-ref`, the upload refusal, and the
documented-API path with stand-ins for `az` and HTTP.

Example (17 November 2026, this checkout, compared with W13's commit 3540434):

```
Built workload/build/package/Org.Krusgraph.1.0.1385.nupkg (140580 bytes): Org.Krusgraph 1.0.1385, item type Org.Krusgraph.Model.
Checked: the build's manifest checks passed (name, frontend URL and app id, images, Workload Hub fields).
Checked: the manifest tests passed (tests/test_workload_manifest.py tests/test_n201_manifest.py ...).

Changes against the manifest at 3540434:
  - Version: 3540434 -> 1.0.1385
  - translations.json Workload_Hub_GetStarted_1_Sub_Title: "… in three ste… -> "… in four step…
  ...
Nothing was uploaded. To add it in Fabric:
  1. The package is …/Org.Krusgraph.1.0.1385.nupkg (in Cloud Shell: Manage files -> Download, that path).
  2. As a Fabric administrator, at https://app.fabric.microsoft.com: OneLake catalog -> Govern -> Workloads …
  3. Org.Krusgraph -> Upload -> choose the file (version 1.0.1385).
  4. Activate it: the workload's page -> version 1.0.1385 -> Activate. Reload the Fabric tab.
  5. Undo: activate the previous version again on the same page.
```

## Automatic build

Round WP1, 18 November 2026: `.github/workflows/workload-package.yml`. It uploads nothing and calls neither Fabric nor
any portal endpoint; there is no browser automation either.

**When it runs:** on a push to `main` that changes `workload/Workload/Manifest/**`, the build script
(`workload/scripts/build_package.py`, `build-package`), `tools/workload_package.py`, `tools/workload_package_ci.py`,
`tools/workload-package.sh` or the workflow itself. It can also be started by hand: Actions > Workload package > Run
workflow. The box "Open the issue even when only the version would change" is off by default.

**What it does:**
1. It builds `Org.Krusgraph` with `tools/workload_package.py --full-tests`, so every workload manifest test runs,
   including the server-dependent ones.
2. It compares the package with a baseline:
   - before the first package, the manifest at `3610190`. That is `main` on 17 November with 1395 commits, most likely
     what 1.0.1395 was built from;
   - after that, the last package it offered (the tag `workload-pkg/1.0.N`);
   - while an issue is open and not ticked, the same baseline as that issue, so the diff covers everything since the
     last upload.
3. It keeps the `.nupkg` and `diff.txt` as the run's artifact for 30 days.
4. **If something changes for Fabric**, it tags the commit `workload-pkg/<version>` and opens one issue,
   **New workload package ready: Org.Krusgraph 1.0.N**. If an open issue of its own exists and its box is not ticked,
   it updates that issue instead (new title, new body, and a comment so you get a notification); it never opens a
   second one. If the box is ticked, it closes that issue and opens a new one. If nothing changes but the version, it
   offers nothing: no tag and no issue, only a line in the run's summary.

**What Gustav sees:** one issue with:
- what changes for Fabric, with a warning if the workload name or an item type changes;
- a link to the artifact (a zip with the `.nupkg` and the diff);
- the portal link <https://app.fabric.microsoft.com/onelake/govern/org-config/workloads/publish?experience=fabric-developer>;
- the steps: **Upload workload** > choose the file > the dialog must name **Org.Krusgraph** > open
  **Krusgraph (preview)** > select the new version > **Activate**. To undo, activate the previous version;
- a checkbox, **uploaded**. Tick it (or close the issue) after the upload.

**Versions** are unique and always increase. Each new version is the highest of three numbers:
- `1.0.<commits on main>`;
- one patch above the highest `workload-pkg/` tag;
- 1.0.1396.

A manual re-run on the same commit therefore gets the next number. Two runs never overlap (one `concurrency` group).
The tag is pushed before the issue is written, so a version that is already taken stops the run before the issue
changes. Tags are never moved or deleted. A package that was built but not offered (nothing changed) is not tagged, and
its number may be used again; it was never offered for upload. If you build by hand in Cloud Shell, the same rules
apply, because the clone has the tags. `tests/test_wp1_workload_package_ci.py` tests the rules.

**Permissions:** `contents: write` (only to push the tag) and `issues: write`. No secrets, no OIDC, no Azure sign-in.
The actions are pinned by commit.

**The one setting Gustav makes (once).** The workflow needs the workload app's Application (client) ID. That is a
public id, so it is a variable, not a secret:
1. Open <https://github.com/Krusmaster/fabric-backend/settings/variables/actions>. Or go to the repository >
   **Settings** > **Secrets and variables** > **Actions** > the **Variables** tab.
2. Click **New repository variable**.
3. Name: `KRUSGRAPH_WORKLOAD_APP_ID`. Value: the Application (client) ID you pass as `--frontend-app-id` in Cloud Shell
   (Microsoft Entra admin center > App registrations > the workload app > Overview).
4. Click **Add variable**. Then run it once: **Actions** > **Workload package** > **Run workflow** > `main`.

Without the variable, every run ends green with one line: "Skipped: the repository variable KRUSGRAPH_WORKLOAD_APP_ID
is not set". To switch the workflow off, delete the variable, or use **Actions** > **Workload package** > **...** >
**Disable workflow**.

## 4. CI design (W14's plan; the build part is now the automatic build above)

The automatic build above implements the build part of this plan. The upload part still waits for a documented API.

- **Build on every push to `main`.** A job runs `tools/workload_package.py` (without `--upload`): it builds, checks and
  diffs, with `--previous-ref` set to the commit of the last approved upload. It keeps the `.nupkg` and the diff as
  the run's artifact. This needs no secret and no Fabric access. The repository has a CI package artifact already
  (W12); this adds the diff and the tests.
- **When the diff is not empty**, the job comments the diff on the pull request that changed `workload/Workload/Manifest/`.
  That path is already protected, so the pull request carries `needs-gustav`, and Gustav reads what the upload would
  change before merging.
- **Upload only on Gustav's approval:**
  - Today: Gustav downloads the artifact and follows the printed steps. This is the only way while no API exists.
  - If Microsoft documents an API: a `workflow_dispatch` job behind a GitHub environment that requires Gustav's review.
    It would sign in with GitHub's OIDC token (no stored secret), as `deploy.yml` does, and call that documented API
    with the version the artifact names.
  - Record the uploaded commit, so the next diff compares against it.
- **Never:** an upload on push, a client secret, or a portal endpoint that Learn does not document.
