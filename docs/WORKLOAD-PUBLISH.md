# Publishing Krusgraph.Modeler: the founder's runbook

Round n195, 10 November 2026 (first written in n176, 9 November 2026). The permanent workload name is
**`Krusgraph.Modeler`** (publisher part `Krusgraph`, workload part `Modeler`; the founder's decision of 9 November 2026).
This page is the founder's steps, in order, from today's blocker to Microsoft's publishing review. What each pilot's own
administrator does is in `docs/PILOT-ONBOARDING.md` and on the site at `/pilot/fabric`.

Nothing here was run by a build round. No round uploads a package, creates or changes an Entra app, signs in to Partner
Center or calls Fabric. Every step marked **founder only** needs the founder's own sign-in. Anything the sources below do
not show is marked **Unverified**; write down what the screen actually shows and correct this page.

Where things stand on 10 November 2026:

- `Org.Krusgraph` 1.0.937 runs in the company tenant (krusgraph.com, `d2fcf72a-9b80-451d-868b-8d47af30d8ae`, home
  region Sweden Central), with the Entra app `853a0cf0-7d35-42b7-b384-26178755a72a`.
- Uploading `Krusgraph.Modeler.1.0.937.nupkg` fails with the name-registration error (step 1). A support ticket is being
  raised. Nothing in the package or this repository works around it.
- The attestation page is written (step 6) and the Krusgraph.Modeler package points at it; it goes live with the next
  redeploy.

## Step 0. Redeploy, then build Krusgraph.Modeler again

1. Cloud Shell, `~/fabric-backend`: `git pull --rebase origin main`, then `bash deploy/krusgraph.sh --from-azure --update`.
2. Open `https://krusgraph.com/workload/attestation`: it shows the attestation with **Draft.** at the top. The Markdown
   twin is `https://krusgraph.com/workload/attestation.md`. Neither is linked from the home page or the navigation, and
   the page is `noindex` while it says Draft.
3. Build the package again:
   `workload/scripts/build-package --name Krusgraph.Modeler --frontend-app-id 853a0cf0-7d35-42b7-b384-26178755a72a`.
   It prints the attestation link and one line **Not ready for Microsoft's publishing review yet** for the Marketplace
   offer (step 8). Keep the file for step 3; do not upload it until step 1 is solved.

## Step 1. The name-registration blocker (founder only)

The upload answers: *"The package contains a Workload name that is not registered with Microsoft. Only tenants that are
enrolled in a Partner Center program may publish workloads and reserve names via package upload."*

What Learn says: the name "is automatically registered when you confirm it during the first upload" [P2]; before
cross-tenant publishing you need a "Publishing tenant" and a unique `[Publisher].[Workload]` name [P1]. Learn does not
say how a tenant is recognised as "enrolled in a Partner Center program" (**Unverified**). Our tenant is linked in
Partner Center (Partner and Developer tabs), and Kruse Consulting AB (seller id 97022330) is enrolled in the AI Cloud
Partner Program and the Commercial Marketplace, with payout and tax profile complete. So the recognition is on
Microsoft's side; do not try another name, another tenant or a changed package.

Support ticket text (Partner Center → Help + support → New request; or Fabric support. Which queue handles it is
**Unverified**):

> **Subject:** Fabric workload name cannot be registered on upload: tenant enrolled in Partner Center
>
> We are trying to upload our Microsoft Fabric workload package in OneLake catalog → Govern → Workloads → Upload
> workload. The upload fails with: "The package contains a Workload name that is not registered with Microsoft. Only
> tenants that are enrolled in a Partner Center program may publish workloads and reserve names via package upload."
>
> - Workload name in the package: Krusgraph.Modeler (WorkloadName in WorkloadManifest.xml; package
>   Krusgraph.Modeler.1.0.937.nupkg)
> - Publishing tenant: d2fcf72a-9b80-451d-868b-8d47af30d8ae (verified domain krusgraph.com, home region Sweden Central)
> - Company: Kruse Consulting AB, Partner Center seller id 97022330, enrolled in the AI Cloud Partner Program and the
>   Commercial Marketplace; payout and tax profile complete; the tenant above is linked to the Partner Center account
>   (Partner and Developer tabs).
> - The same tenant already runs our development workload under an Org.* name, uploaded the same way.
>
> Please tell us what is missing for this tenant to register the workload name Krusgraph.Modeler on upload, or register
> it for us. We have not tried any other name.

Write the ticket number and Microsoft's answer here when it comes.

## Step 2. Publisher verification of the Entra app (founder only)

Microsoft's requirement: "All workloads must use a verified Microsoft Entra application", with "verified publisher
status", completed "before workload publishing" [P3]; requirement 2.1.1 "Verified Microsoft Entra App ID" and 4.1.4
"Microsoft Entra App Name and publisher need to be aligned with the Workload", both required at Preview [P5].

What publisher verification needs [P10]:

- a Partner One ID of a Microsoft AI Cloud Partner Program account that has completed verification, and it must be the
  **partner global account (PGA)**, not a location id;
- the app registered with a Microsoft Entra work account, in a tenant associated with that PGA;
- the app's **publisher domain** set, and not `*.onmicrosoft.com`;
- the domain of the email used during the partner account's verification must match the publisher domain or be a
  DNS-verified custom domain of the tenant;
- the person doing it: Application Administrator or Cloud Application Administrator in Entra, **and** AI Cloud Partner
  Program Admin or Accounts Admin in Partner Center; signed in with multifactor authentication.

Steps:

1. **Partner Center**: Account settings → Legal info / Identifiers (labels **Unverified**): note the **Partner One ID of
   the partner global account** (not a location id). Check that the account's verification is complete and which email
   address it was verified with. That email's domain should be `krusgraph.com`; if it is not, note which domain it is.
2. **Partner Center**: check that tenant `d2fcf72a-9b80-451d-868b-8d47af30d8ae` is associated with the PGA (you have
   linked it on the Partner and Developer tabs; the association Learn names is "Add an Azure AD tenant to your account"
   [P10]).
3. **Entra admin centre** (`https://entra.microsoft.com`), signed in with MFA as Application Administrator or Cloud
   Application Administrator: **Entra ID → Domain names**: `krusgraph.com` must be listed as **Verified**.
4. **App registrations → All applications → Krusgraph workload (dev)** (`853a0cf0-…`) → **Branding & properties**:
   - **Name**: rename to `Krusgraph` (the decision recorded below, "keep the dev app"); 4.1.4 asks for the name to align
     with the workload.
   - **Publisher domain** → **Configure a domain** / **Update domain** → **Select a verified domain** → `krusgraph.com`
     [P11]. (Only if krusgraph.com were not a verified domain of the tenant would you need **Verify a new domain** with
     `https://krusgraph.com/.well-known/microsoft-identity-association.json`, served as `application/json`; it is not
     needed here, and the site does not serve that file.)
   - **Add Partner ID to verify publisher** → enter the PGA's Partner One ID → **Verify and save** [P12]. Wait a few
     minutes. On success the blue verified badge appears next to **Publisher display name** [P12].
5. Check: open the admin consent link of step 5 in a test tenant with `&prompt=consent` added once; the consent screen
   shows the blue badge [P12]. Write the date here.

If verification fails, the error names the missing requirement; Learn's troubleshooting page lists them
(`troubleshoot-publisher-verification`, not read this round: **Unverified**).

## Step 3. Upload Krusgraph.Modeler and confirm the name, letter by letter (founder only; after step 1)

1. In Fabric, as a Fabric administrator: **OneLake catalog → Govern → Configurations → Workloads → Upload workload**,
   choose `Krusgraph.Modeler.1.0.<N>.nupkg` [P6].
2. The **Confirm workload Name** dialog appears; the name "comes from your manifest and you can't change it in this
   dialog" [P1]. Read it letter by letter before **Confirm**:

   | # | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 |
   | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
   | Letter | K | r | u | s | g | r | a | p | h | . | M | o | d | e | l | e | r |

   Capital K, capital M, one dot, no space, 17 characters; the workload part `Modeler` is 7 of the 32 allowed [P4]. If
   the dialog shows anything else, **Cancel**. "The Workload Name is permanently reserved in your tenant after
   confirmation and can't be changed" [P1]. **This is the one step that cannot be undone.**
3. Select the uploaded version → **Add**; Status shows **Active in tenant** [P6].
4. Try it in the company tenant: a workspace on a capacity → **+ New item** → **Krusgraph Model**. Both workloads are
   listed side by side; the workload name under Govern → Workloads tells them apart.

Each later upload needs a version never uploaded before [P6]; the build numbers it `1.0.<commits on main>`.

## Step 4. Microsoft's test tenant and the pilots: Publish to selected tenants (founder only)

1. Select **Krusgraph.Modeler** under **Govern → Configurations → Workloads** → the **Publish** tab → **Publish to** →
   **Selected tenants** [P1].
2. Add, one by one, up to 20 tenant ids in all [P1]:
   - **Microsoft's test tenant `afd60f91-ebf2-4e00-b221-bd2ebfd15095`**: the submission form says it must already be in
     the preview audience for a Preview request (the founder's reading of the form, 10 November 2026; not on Learn:
     **Unverified** beyond the form).
   - each pilot's tenant id.
3. Choose the version → **Publish**. "It might take up to 10 minutes" before target tenants see it [P1].
4. On our server, add each pilot's tenant id to `workload_allowed_tenants` in `deploy/krusgraph.json` and run
   `bash deploy/krusgraph.sh --update` (A2 below). Microsoft's test tenant: add it too, or its
   reviewers see "Krusgraph is not turned on for your organisation yet" on the first call (**to decide**: allowing it
   is needed for the review to try the editor).

## Step 5. In each target tenant: the admin setting and admin consent (the target tenant's administrator)

1. Fabric admin portal → **Tenant settings → Additional workloads** → **Users can see and work with additional
   workloads not validated by Microsoft** → on. Target tenants "can only see and use your workload" with it [P1].
2. Admin consent for the Entra app, by a Global Administrator or Privileged Role Administrator of that tenant:
   `https://login.microsoftonline.com/<their tenant id>/adminconsent?client_id=853a0cf0-7d35-42b7-b384-26178755a72a`.
   An administrator can also select **Consent** on the workload in **Manage my tenant** "to grant organization-wide
   consent" [P6].
3. The rest (network, capacity, + New item) is `docs/PILOT-ONBOARDING.md` and `/pilot/fabric`. Send that to pilots; for
   Microsoft's test tenant the reviewers do these steps themselves (**Unverified**).

## Step 6. The attestation document

- Hosted: `https://krusgraph.com/workload/attestation` (source
  `fabric_backend/page_templates/WORKLOAD-ATTESTATION.md`, Markdown twin at `…/attestation.md`). It is **Section III**
  of Microsoft's template, the only section the template asks to host for customers [P7]; it marks every open point
  **Not yet** or **To confirm**, and claims no certification, audit, compliance standard or endorsement.
- In the manifest: Krusgraph.Modeler's `Product.json` has `productDetail.supportLink.certification.url` =
  `https://krusgraph.com/workload/attestation`. That is the field requirement 1.4.1 and Microsoft's validator read for
  the attestation link [P5][P9]. Learn's overview also says "Your workload manifest must include the `AttestationUrl`
  property" [P3], but neither the workload manifest page [P4] nor the starter kit's `WorkloadDefinition.xsd` (commit
  `dacab1b`) has such an element, and adding one would break the schema. So we fill the field the review reads and put
  no `AttestationUrl` element in `WorkloadManifest.xml` (**Unverified**: whether the form's "Attestation URL that must
  also be in the manifest" means this field; ask in the review if it is questioned). `Org.Krusgraph` keeps `/it`.
- **Final**: when every point is answered, delete the paragraph that starts with `**Draft.**` in the source file and
  redeploy. The page then drops `noindex`. Template rule: tell Microsoft before releasing a change that materially
  affects the attestation [P7].
- Sections I and II go to Microsoft, not on the site. Our answers:

  | Section I field | Answer |
  | --- | --- |
  | Company Name | Kruse Consulting AB (**to confirm** the registered name) |
  | Company Website | https://krusgraph.com |
  | Address, City, State, Postal Code, County | **founder**: the registered address; Sweden; "State" not applicable |
  | Phone (optional) | **founder** or empty |
  | Primary Contact Name, Title | **founder** |
  | Email (alias OK) | **founder**: gustav@krusgraph.com, or a support alias if one is created |

  Section II is one sentence: "We, the undersigned, Kruse Consulting AB, hereby confirm and attest that we have
  reviewed, understood, and complied with all applicable requirements … specifically the Publish Workload
  Requirements" [P7]. **Do not sign it while points on the hosted page say Not yet.** That is the founder's call.

## Step 7. Run Microsoft's validator (founder only)

Microsoft's tool is `microsoft/fabric-extensibility-toolkit-validator` [P8][P9]. It cannot run in CI or in a build
round: it needs Node.js 14+, Chrome, a browser signed in to Fabric, and the workload already published to a tenant; it
downloads the manifest from the Workload Hub by name, and recommends validating from a different tenant than the
publishing one [P9]. After step 4:

```bash
git clone https://github.com/microsoft/fabric-extensibility-toolkit-validator.git
cd fabric-extensibility-toolkit-validator/validator && npm install
node index.js --workload-name "Krusgraph.Modeler" --workload-stage "Preview"
```

Results land in `Results/Krusgraph.Modeler/Preview/<id>/Reports/` (Markdown, HTML, PDF) [P9]. Paste the summary here.

What CI checks instead (offline, on every push): `workload/scripts/build_package.py` refuses a Krusgraph.Modeler package
without the attestation link, the publisher, the en-US names and descriptions, https support links, getting-started and
at-a-glance material, or icons and banner at the validator's sizes (the `workload` job builds both packages);
`.github/workflows/hub-readiness.yml` runs the validator's own test-case list against the manifest and the n178 draft;
`tests/test_n195_attestation.py` checks the hosted page for every term the validator's attestation tests search for.
The offline run on 10 November 2026 (validator `78e17c3`): every automated manifest, link and image check met except
**1.3.1 and 1.3.2, the Marketplace offer link** (step 8). Not ours to settle offline: requirement 3.1.2.1 says the product
icon is 240x240, while the validator's image check accepts 16 to 64 px only; the icon stays 64x64, which the validator
passes (**Unverified** which one the review applies).

## Step 8. The submission form (https://aka.ms/fabric_workload_publishing)

The form could not be opened from the build session (aka.ms is outside its network), so only page 2 is from the
founder's reading. Other pages: **Unverified**; note their questions here on first use.

**Page 2:**

| Question | Our answer | Waits for |
| --- | --- | --- |
| Publishing Stage | **Preview** | Microsoft's test tenant in the preview audience (step 4) |
| Publishing Tenant ID | `d2fcf72a-9b80-451d-868b-8d47af30d8ae` | nothing |
| Workload ID (max 32 characters) | `Krusgraph.Modeler` (17 characters). If the form means only the workload part, `Modeler` (**Unverified** which; both fit) | step 1 (the name registered) and step 3 |
| Version Number | the version uploaded and published in steps 3 and 4, e.g. `1.0.937` for the package built on 10 November 2026; if the field takes only one number, ask (**Unverified**) | step 3 |
| Attestation URL (must also be in the manifest) | `https://krusgraph.com/workload/attestation` | step 0 (redeploy) and the Draft marker removed (step 6) |

**What the review asks that is not met yet** (requirements marked required at Preview [P5]):

1. **Marketplace offer (1.3.1, 1.3.2)**: `productDetail.supportLink.license.url` must be an Azure Marketplace or AppSource
   offer. There is none; today it points at the MIT licence on GitHub. Waits for the production SaaS offer
   (`docs/MARKETPLACE-SETUP.md`); then change that one URL in `Product.json` and rebuild.
2. **Verified Entra app, name aligned (2.1.1, 4.1.4)**: step 2.
3. **The attestation's open points (2.3, 2.4, 4.1, 4.2)**: Conditional Access not tested; logs without the Fabric
   activity id; no independent security assessment or penetration test; no privacy review. Required at Preview as an
   attestation; the hosted page says "Not yet" for each.

## The founder's TODO list (from the attestation and the form)

| # | What | Why | Blocks |
| --- | --- | --- | --- |
| 1 | Support ticket for the name registration (step 1) | upload refused | everything below that needs an upload |
| 2 | Publisher verification and rename of the Entra app (step 2) | 2.1.1, 4.1.4 | the request |
| 3 | Production Marketplace SaaS offer, then its URL as the license link | 1.3.1, 1.3.2 | the request |
| 4 | Trial and monetization model: decide and state (free, freemium, Marketplace) | attestation: Trial, Monetization | final attestation |
| 5 | Independent security assessment / penetration test: who and when | 4.1 | final attestation |
| 6 | Privacy review | 4.2 | final attestation |
| 7 | Test with a Conditional Access policy in a tenant | 2.3 | final attestation |
| 8 | Fabric activity id in the logs; log retention at 30 days or more, confirmed live on /it | 2.4 | final attestation (also a code round) |
| 9 | SLA and support terms; a support alias if wanted | 5.1, 5.2 (required at GA) | GA |
| 10 | Service health page | 5.3 (optional) | none |
| 11 | Business continuity and disaster recovery plan | 2.6 (optional at Preview) | GA |
| 12 | Accessibility check (contrast in Fabric themes, screen-reader names, focus order) | 2.9 | final attestation |
| 13 | Section I details (address, contact name and title) and the Section II signature | template | the request |
| 14 | Remove the Draft paragraph and redeploy | step 6 | the request |
| 15 | Test B2B guests and `*.powerbi.com` creation | 2.5, item 2.7 | final attestation |
| 16 | Run Microsoft's validator after publishing to selected tenants (step 7) | validation | the request |

## Sources

Read on 10 November 2026. "Learn commit" is the page's `git_commit_id`.

| # | Page (`ms.date`) | URL | Learn commit |
| --- | --- | --- | --- |
| P1 | Publishing Overview (2026-04-08) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-overview | `80a24c9` |
| P2 | Publishing Requirements overview (2026-04-08) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-overview | `80a24c9` |
| P3 | the same page, "Microsoft Entra App Verification" and "Attestation Documentation" | as P2 | `80a24c9` |
| P4 | Workload Manifest (2025-12-15) | https://learn.microsoft.com/fabric/extensibility-toolkit/manifest-workload | `80a24c9` |
| P5 | Validation guidelines and requirements for workloads (2026-02-24); for items (2026-02-24); General Publishing Requirements (2025-12-15) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-workload, …/publishing-requirements-item, …/publishing-requirements-general | `5e656ad`, `bd2c301`, `5156dc5` |
| P6 | How to publish and manage a workload (2025-11-18) | https://learn.microsoft.com/fabric/extensibility-toolkit/tutorial-publish-workload | `80a24c9` |
| P7 | Vendor attestation template (2026-02-24) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-vendor-attestation-template | `e567e67` |
| P8 | How to validate your workload for publishing (2025-12-15) | https://learn.microsoft.com/fabric/extensibility-toolkit/tutorial-validate-workload | `5156dc5` |
| P9 | `microsoft/fabric-extensibility-toolkit-validator`: README, `validator/validators/*`, `specifications/testcases/Testcases_Workload.json` (MIT, LICENSE read at that commit) | https://github.com/microsoft/fabric-extensibility-toolkit-validator | commit `78e17c3` (15 December 2025) |
| P10 | Publisher verification overview (2024-08-13) | https://learn.microsoft.com/entra/identity-platform/publisher-verification-overview | `a4be4ac` |
| P11 | Configure an app's publisher domain (2023-04-27) | https://learn.microsoft.com/entra/identity-platform/howto-configure-publisher-domain | `a4be4ac` |
| P12 | Mark an app as publisher verified (2024-05-31) | https://learn.microsoft.com/entra/identity-platform/mark-app-as-publisher-verified | `a4be4ac` |

The Learn page named "publish-workload-flow" in the task resolves to the same content as P1 (**Unverified**: that
address was not opened separately).

---

# Detail from n176 (still current): A1 to A4

The Entra addresses, the server's lists and the upload in more detail. A1 and A2 come before step 3 above; A3 and A4 are
steps 3 and 4 above, with n176's notes.

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

## A1. Entra: the Krusgraph.Modeler addresses on the workload app

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

## A2. The server: both URIs, and the pilots' tenants

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
here **and** on Fabric's Publish tab (A4); the two lists are separate, and a pilot needs both.

- Adding a pilot: append `,<pilot tenant id>` to `workload_allowed_tenants`, then `bash deploy/krusgraph.sh --update`.
  The pilot's tenant id goes into `deploy/krusgraph.json` only, which is git-ignored; never into the repository.
- A tenant in Fabric's list but not in this one: the editor opens, and its first call to the engine shows *"Krusgraph is
  not turned on for your organisation yet."* with the tenant id and the pilot page, in the editor's error bar. Nothing
  is read or changed in their workspace. It does not ask the user to sign in again.
- A tenant in neither list does not see the workload at all.
- An empty `workload_allowed_tenants` means every tenant whose administrator consented. Do not leave it empty while
  publishing to selected tenants.

## A3. Upload Krusgraph.Modeler

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

## A4. Publish to selected tenants

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

1. Their tenant id: add it to `workload_allowed_tenants` and run `bash deploy/krusgraph.sh --update` (A2).
2. The Publish tab → Selected tenants → add the id → Publish (A4). Twenty at most.
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
