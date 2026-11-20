# Save to lakehouse Files: setup (WB14)

Round WB14, issue #108. Gustav approved on 18 November 2026 adding the storage permission that lets the Model editor
save a generated file (the draw.io map, a notebook `.ipynb`, the handover files, `contracts/*.odcs.yaml`, the App
package, `EDIT-WITH-AI.md`) straight into a lakehouse's **Files** folder. It is a second option beside WB10's
single-use download link (PR #79, `fileOffer.tsx`, `fabric_backend/file_links.py`), which stays as it is.

The code is merged with its switch **off**. Nothing changes for anyone until Gustav does the three steps below.
**Gustav makes every Entra and Azure change himself**; no round changes Entra or Azure, and no secret is involved.

## What the editor does when it is on

- Beside **Download** (and **Copy**) of every generated file there is **Save to lakehouse Files**.
- The first click is a dry run: *Dry run: Save would write `<file>` (size) to `<lakehouse> › Files/krusgraph/<item
  name>/<file>`, as you.* Nothing is written yet. **Save** writes; **Cancel** does nothing.
- The lakehouse is the one the item already targets: the target lakehouse chosen for the build, else the source
  lakehouse. A warehouse or SQL database source without a target lakehouse shows no Save button.
- A file of that name already there is never overwritten: the editor says so and asks **Replace** or **Keep the file
  there**. Only **Replace** overwrites.
- Without the permission (or without consent) the editor says: *Your admin has not granted storage access yet; use
  Download instead.* Download keeps working.
- The write is the signed-in person's own, in their own name: the token is delegated and Fabric checks their role in
  the workspace. Krusgraph's engine is not involved and never sees the file or the token.
- The browser console gets the HTTP status and OneLake's request id (`x-ms-request-id`) only; never the file, the path's
  contents or a token.

## The permission, and why it is the least one that works

| | |
| --- | --- |
| API | **Azure Storage** (in *APIs my organization uses*; resource `https://storage.azure.com`) |
| Permission | **user_impersonation** ("Access Azure Storage") |
| Type | **Delegated** (never Application) |
| Asked for by | the editor, with `workloadClient.auth.acquireFrontendAccessToken({ scopes: ["https://storage.azure.com/user_impersonation"] })` |
| App | the workload's Entra app, **Krusgraph workload (dev)** (the app both `Org.Krusgraph` and `Krusgraph.Modeler` use) |

Why this one:

1. **OneLake accepts only Storage tokens.** "OneLake only supports tokens in the `Storage` audience." Microsoft Learn,
   *How do I connect to OneLake?*, `learn.microsoft.com/fabric/onelake/onelake-access-api` (ms.date 05/18/2026, read 20
   November 2026). Fabric's own scopes (Power BI Service `OneLake.ReadWrite.All` and the like) are for the Fabric REST
   APIs, not for the DFS endpoint `https://onelake.dfs.fabric.microsoft.com` that writes a file.
2. **It is the documented scope for a workload.** *Authentication JavaScript API reference*,
   `learn.microsoft.com/fabric/extensibility-toolkit/authentication-javascript-api` (ms.date 12/15/2025, read 20 November
   2026) lists `https://storage.azure.com/user_impersonation` for Azure Storage, and *Authentication guidelines*,
   `…/extensibility-toolkit/authentication-guidelines` (ms.date 12/15/2025) says to add it on the app's **API
   permissions** tab. Microsoft's starter kit, which this workload is a fork of, uses the same scope for OneLake
   (`workload/Workload/app/clients/FabricPlatformScopes.ts`, `ONELAKE_STORAGE`).
3. **Azure Storage has no narrower delegated permission.** `user_impersonation` is its one delegated permission.
4. **Delegated means the person's own rights, no more.** The token acts as the signed-in person. OneLake checks their
   workspace role (a Viewer cannot write); the app gets no access of its own. No application permission, no service
   principal, no client secret.

What it also allows, said plainly: the same delegated permission would let the editor reach an Azure storage account in
which the signed-in person holds a data role. Krusgraph's code calls only `onelake.dfs.fabric.microsoft.com`
(`onelakeSave.ts`; `tests/test_wb14_onelake_save.py` fails if another host appears).

**The workload manifest does not change.** It names the frontend app (`AADFEApp` › `AppId`) and has no element for
scopes (*Workload Manifest*, `…/extensibility-toolkit/manifest-workload`, ms.date 12/15/2025). The scope is a permission
of the Entra app. So there is no manifest pull request and no new package for this. `EnableSandboxRelaxation` stays
`false`.

How the file is written (ADLS Gen2 *Path - Create* and *Path - Update*,
`learn.microsoft.com/rest/api/storageservices/datalakestoragegen2/path/create`, ms.date 10/23/2026):
`PUT …/<workspace id>/<lakehouse id>/Files/krusgraph/<item>/<file>?resource=file` with `If-None-Match: "*"` (409 when the
file is there), then `PATCH ?action=append&position=0` with the bytes and `PATCH ?action=flush&position=<length>`.
**Replace** sends the same create without `If-None-Match`, which overwrites.

## Gustav's click-list

### 1. Entra: add the permission and consent

1. Open **entra.microsoft.com**, signed in as a Global Administrator or Privileged Role Administrator of the tenant.
2. **Identity › Applications › App registrations › All applications** › **Krusgraph workload (dev)** (Application
   (client) ID `853a0cf0-7d35-42b7-b384-26178755a72a`).
3. **API permissions › + Add a permission**.
4. Tab **APIs my organization uses**, search **Azure Storage**, choose it. (It is also under *Microsoft APIs* ›
   *Azure Storage* in some tenants.)
5. **Delegated permissions** › tick **user_impersonation** › **Add permissions**.
6. Back on **API permissions**: **Grant admin consent for \<your organisation\>** › **Yes**. The row *Azure Storage ·
   user_impersonation · Delegated* shows a green *Granted*.

Leave every other permission as it is. Do not add an application permission.

A customer tenant that installs `Krusgraph.Modeler` later consents for its own organisation the same way (its admin
consents to the multitenant app); until then the button, when on, shows the plain message and Download works.

### 2. Turn the switch on (Cloud Shell)

The switch is an environment variable on the container app; it adds the meta tag `krusgraph-onelake-save` to the
editor's page (`fabric_backend/workload_host.py`). No new package, no rebuild.

```bash
az containerapp update -n krusgraph -g rg-krusgraph --set-env-vars KRUSGRAPH_ONELAKE_SAVE=on
```

Reload the Fabric tab (Ctrl+F5) after the new revision is running.

### 3. Test on workspace *demo*, lakehouse *demo_lh*

1. In workspace **demo**, open (or create) a Krusgraph Model item on **demo_lh**, schema `shop`.
2. Run the review (**Find keys and relationships**). Under the map: **Save to lakehouse Files**. Check the dry run's
   path: `demo_lh › Files/krusgraph/<the item's name>/demo_lh.shop-map.drawio`. Choose **Save**: *Saved to …*.
3. In **demo_lh**, **Files › krusgraph › \<item\>**: the `.drawio` file is there (open it in draw.io to check).
4. Choose **Save to lakehouse Files › Save** again: the editor says the file is already there and asks **Replace**.
   Choose **Keep the file there** once (nothing changes), then **Replace** (the file's modified time changes).
5. On the Data product page and Next steps, save one handover file and the Data Science notebook the same way.
6. Optional, the no-consent path: sign in as a member of a tenant that has not consented, or before step 1, and check
   the plain message and that **Download** still works.

What to note if it fails: the message on the card, and from the browser console (F12) the line
`krusgraph.onelake_save {status, activity_id}`. A `TypeError: Failed to fetch` there with no status means the browser
refused the call before OneLake answered (CORS); that has not been seen with Microsoft's starter kit, which calls the
same endpoint from the browser, but it was not tried in Fabric before this merge.

### Turn it off, or revoke

- **Switch off** (the button disappears at the next reload; Download is unchanged):
  `az containerapp update -n krusgraph -g rg-krusgraph --set-env-vars KRUSGRAPH_ONELAKE_SAVE=off`
  (or `--remove-env-vars KRUSGRAPH_ONELAKE_SAVE`).
- **Revoke the consent**: Entra › **Enterprise applications** › **Krusgraph workload (dev)** › **Permissions** ›
  the *Azure Storage · user_impersonation* row › **Revoke permission**. Then App registrations › the app › **API
  permissions** › the row's **…** › **Remove permission**. Tokens already issued expire within about an hour.
- Files already saved stay in the lakehouse; delete `Files/krusgraph/` in the lakehouse if you want them gone.

## Verified, and how

20 November 2026: unit tests with OneLake's answers mocked (`onelakeSave.test.tsx`: 201 Created, 403 without consent, a
token the host will not give, 409 already there then Replace, a timeout, a zip's bytes), `tests/test_wb14_onelake_save.py`
(the switch, the manifest unchanged, the hosts the editor calls), and the end-to-end walk's flow 24 on the doubles at 390
px, light and dark (`workload/scripts/e2e/run.js`, OneLake answered in the browser by `page.route`). **Not run against
Fabric or OneLake**: no Entra change was made and no token was used.
