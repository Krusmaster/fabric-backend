# Workload Hub readiness: Krusgraph.Modeler, Preview listing

Round n178, 9 November 2026. Documentation and one CI check only: no `workload/` code, site or engine changed, nothing
created, uploaded or signed up for in Fabric, Entra, Azure or Partner Center, and no `Krusgraph.*` name used anywhere but
on paper. It continues `docs/WORKLOAD-FEASIBILITY.md` (section 5, sources `[Sn]`), `docs/WORKLOAD-LISTING-AND-PAYMENT.md`
(`[Ln]`) and `docs/MARKETPLACE-SETUP.md` (`[Mn]`). The attestation draft is `docs/HUB-ATTESTATION.md`.

`Krusgraph.Modeler` is the **proposed** permanent name (`docs/WORKLOAD-LISTING-AND-PAYMENT.md`, 1b). It is not
registered: the first upload of a `[Publisher].[Workload]` name reserves it in the publishing tenant for good [H6]. Today
the workload exists only as `Org.Krusgraph` 1.0.877 in the founder's own tenant (uploaded 8 November 2026,
`docs/WORKLOAD-DEV.md`, Hosted).

## How this was researched

- Microsoft's pages were read on learn.microsoft.com on **9 November 2026** (reachable from this environment, as for
  n167). The validator was read on GitHub at commit `78e17c3` (15 December 2025): its README, `validator/README.md`,
  `validator/index.js`'s options, `validator/downloaders/manifest_downloader.js` and the test-case specifications
  `specifications/testcases/Testcases_Workload.json` and `Testcases_Item.json`. Its `LICENSE` is MIT (Microsoft
  Corporation), read at that commit. Nothing of it is copied here; the CI job reads its specifications as data at run
  time.
- The validator's code was **not run** in this round (running a downloaded tool's install scripts was not permitted in
  this environment, and it could not have reached Fabric anyway). Its test cases were read from its specification files.
- krusgraph.com was **not reachable** from this environment (the proxy refused it), so no link was fetched here; the CI
  job fetches them (below).
- Statuses: **met** (the evidence column shows where), **not met**, **unknown** (nothing in the repository proves it
  either way; most need the founder's run in Fabric), **n/a**. A "met" for an attestation requirement means only that
  the draft states it truthfully; the requirement is met when the founder signs and hosts it.

## Summary

| | |
| --- | --- |
| Preview listing possible now? | **No.** Hard blockers: no live Marketplace offer [H2 1.3.1], no hosted attestation [H2 1.4.1], no `Krusgraph.*` name registered [H6], the workload's Entra app is the "(dev)" app [H2 2.1.1, 4.1.4]. |
| Required at Preview | 92 of the validator's 106 test cases are required at Preview (55 of 61 workload, 37 of 45 item); almost every requirement is required at Preview and GA alike [H2][H3]. Optional at Preview, required at GA: live site and supportability [H2 5.1, 5.2]. |
| Microsoft's review time | **None is documented.** Neither the Publishing Overview [H6] nor the validator pages [H4][H5] give a time for the publishing request or the feedback; n167 found none either ([L1], [L23]). |
| Validator in CI? | **No.** It downloads the manifest from the Workload Hub in a Chrome session signed in to Fabric, and needs the workload published to that tenant [H4][H8]. CI runs our **pre-check** against its test-case specifications instead (`.github/workflows/hub-readiness.yml`). |
| Fee | None for Workload Hub publishing in the pages read (absence is not confirmation). Marketplace keeps 3% of transactions [L10]. |

## 1. Requirements, one by one

### 1a. General requirements (all publishing, internal included) [H7]

| Requirement | Status | Evidence |
| --- | --- | --- |
| Verified custom domain; frontend a subdomain of it, at most one extra segment; no `*.onmicrosoft` | met | `workload.krusgraph.com` on `krusgraph.com`; the `Org.Krusgraph` upload of 8 Nov 2026 ran with it (`docs/WORKLOAD-DEV.md`, Hosted) |
| Resource-id Application ID URI on the verified domain | met (for the dev app) | `docs/WORKLOAD-DEV.md`, Hosted step 3; the listing app needs the same (F1) |
| App registration: multitenant, redirect `{frontend}/close`, "Type: Web application" | unknown | The dev app is multitenant with **SPA** redirects (`CreateDevAADApp.ps1`); the page says Web. Which one the validator's manual test 2.1.3 accepts is unconfirmed (`docs/WORKLOAD-FEASIBILITY.md`) |
| `/close` runs only `window.close()` | met | `fabric_backend/workload_host.py` (`/close`, CSP with the script's hash); `tests/test_workload_host.py` |
| HTTPS, valid certificates | met | Azure Container Apps managed certificate (`deploy/azure_containerapp.py`) |
| Minimum 99.9% uptime SLA | not met | One container app, no SLA, no status page |
| Page load under 3 seconds | unknown | Not measured in the Fabric frame (F11) |
| CORS for `*.powerbi.com`, `*.fabric.microsoft.com`; CSP frame-ancestors | met | `workload_api.py` (`FRAME_ANCESTORS`, `cors_headers`), `workload_host.py`; `tests/test_workload_api.py`, `tests/test_workload_host.py` |
| OAuth 2.0, token validation, permission validation | met | `entra.py` `WorkloadConfig` (v2 tokens, workload audience); on-behalf-of, so Fabric enforces the user's permissions; `tests/test_workload_api.py` |
| Encryption in transit and at rest; input validation; security headers | met (in transit, headers); unknown (at rest: no customer data stored, logs in Log Analytics with Azure's default encryption, not verified) | `workload_host.py`; `docs/TRUST.md` |

### 1b. Workload requirements [H2], Preview column

"Attestation" means the requirement is answered in the attestation document; the validator searches the hosted document
for the terms in its specification (pre-check below).

| # | Requirement | Preview | Status | Evidence / what is missing |
| --- | --- | --- | --- | --- |
| 1.1 | Value to customers | required | met (draft) | Attestation; Hub description outdated (F7) |
| 1.2.1 | Terms of use link, HTTPS, 200–399 | required | met (offline) | `Product.json` `supportLink.terms.url` = https://krusgraph.com/terms; the page says "Preview terms"; reachability in CI |
| 1.2.2 | Privacy policy link | required | met (offline) | https://krusgraph.com/privacy; reachability in CI |
| 1.3.1 | Marketplace offer published; license URL on azuremarketplace / appsource / marketplace.microsoft.com | required | **not met** | `supportLink.license.url` is the GitHub LICENSE; no live offer (only a DEV offer is planned, which must never go live, `docs/MARKETPLACE-SETUP.md` §5) |
| 1.3.2 | Offer link in workload page correct | required | **not met** | as 1.3.1 |
| 1.3.3 | Publisher name clear | required | **not met** | `productDetail.publisher` = "Krusgraph (development build)" (F2) |
| 1.3.4 | Publisher name aligned with Marketplace | required | **not met** | No offer; the verified publisher is "Kruse Consulting AB" (`docs/SCOPES.md`) |
| 1.4.1 | Attestation link; document follows the template, contains the workload name | required | **not met** | `supportLink.certification.url` = https://krusgraph.com/it, which is not the attestation (F3); draft in `docs/HUB-ATTESTATION.md` |
| 1.4.2 | Getting started material exists | required | met (manifest) | `homePage.learningMaterials` → https://krusgraph.com/docs; content manual |
| 1.4.3 | "At a glance" image or video | required | met (manifest) | `slideMedia` = `Workload_Hub_SlideMedia_1.png` (985×552); content manual |
| 1.4.4 | Learning material on static pages | required | unknown | /docs is a server-rendered page; manual |
| 1.4.5 | Documentation link | required | met (offline) | https://krusgraph.com/docs |
| 2.1.1 | Verified Microsoft Entra app id | required | **not met** | Workload app "Krusgraph workload (dev)" `853a0cf0-…` has no publisher verification recorded; the MCP app "Krusgraph" is verified (`docs/SCOPES.md`) (F1) |
| 2.1.2 | Static dependency on `Fabric.Extend`, user consent | required | met (dev app) | `CreateDevAADApp.ps1` adds it; admin consent given in the founder's tenant. Consent in other tenants untested (F5) |
| 2.1.3 | Redirect URL lands in Fabric; `/close` only `window.close()` | required | met / unknown | `/close` as in 1a; SPA vs Web unconfirmed |
| 2.1.4 | Scopes kept to a limit | optional | met | `Item.ReadWrite.All` or per-type `*.ReadWrite.All`; no Execute (`docs/WORKLOAD-DEV.md`, Hosted step 7) |
| 2.2 | OneLake | required | met (draft) | Attestation: item state in Fabric, outputs are Fabric items, logs outside |
| 2.3 | Entra Conditional Access | required | **unknown** | Not tested; SDK says CA handling not yet available [S5] (F6) |
| 2.4 | Monitoring and diagnostic, 30 days, activity id | required | **not met** | Retention is a setting (30–730); no activity id in logs (F9) |
| 2.5 | B2B | optional | unknown | Not tested |
| 2.6 | BCDR | optional | not met | No written plan |
| 2.7 | Performance | required | met (draft) | Internal monitoring only; load time not measured |
| 2.8 | Presence | required | met (draft) | Azure Sweden Central, public cloud |
| 2.9 | Accessibility | required | met (draft), limitations | No audit; List view, keyboard on the flow |
| 2.10 | World readiness | required | met | English only (`assets/locales/en-US`) |
| 3.1.1 | Clear workload name | required | unknown | Display name "Krusgraph"; manual |
| 3.1.2 | Icons and images clear, not placeholders | required | unknown | Own images (n175); manual |
| 3.1.2.1 | Product icon | required | met (n175) | `Workload_Icon.png` 64×64, the Krusgraph mark (F4) |
| 3.1.2.2 | Favicon | required | met (n175) | `Workload_Favicon.png` 32×32 (F4) |
| 3.1.2.3 | Custom action icons | required | n/a | No custom actions |
| 3.1.2.4 / .5 | Create experience icons | required | met | `ModelItem_Icon.png` 48×48 |
| 3.1.2.6 / .7 | Tab icons, active | required | unknown | Not in the files; the validator reads them from the downloaded manifest |
| 3.1.3 | Subtitle | required | met | `Workload_Hub_Slogan` |
| 3.1.4 / 3.1.4.1 | Description; Hub card description | required | met (present) | Content outdated (F7) |
| 3.1.5 | Banner 1920×240 | required | met | `Workload_Hub_Banner.png` 1920×240 |
| 3.1.6 | No ads in gallery videos | required | met | No video |
| 4.1 | Security assessment and review | required | **not met** | No independent assessment (F12) |
| 4.1.1 / 4.1.2 / 4.2.3 | Tokens only from the Fabric host, through the SDK's JavaScript APIs | required | met | `engineClient.ts`, `FabricAuthenticationService.ts`: `acquireFrontendAccessToken` only; no MSAL in `workload/Workload/app/` |
| 4.1.3 / 4.2.1 / 4.2.2 | Only essential HTTP-only cookies after sign-in; no third-party cookies | required | met | Workload host sets no cookie and strips `Set-Cookie` (`workload_host.py`; `tests/test_workload_host.py`) |
| 4.1.4 | Entra app name and publisher aligned with the workload | required | **not met** | "Krusgraph workload (dev)", unverified (F1) |
| 4.2 | Privacy review | required | **not met** | Privacy policy and DPA draft exist; no independent review (F12) |
| 4.3 | Data residency | required | met (draft) | Sweden Central; names and counts, no row values (`docs/TRUST.md`) |
| 4.4 | Compliance attestation | required | met (draft) | States "none": no certification claimed |
| 5.1 | Live site contacts | optional | met (draft) | hello@krusgraph.com, founder to confirm |
| 5.2 | Supportability (SLA) | optional | not met | No SLA |
| 5.2.1 | Help link | required | met (offline) | https://krusgraph.com/support |
| 5.2.2 | Support contact on the product page | required | unknown | The help link leads to /support; whether the product page shows a contact is manual |
| 5.3 | Service health page | optional | not met | `/health` only |
| 6.1 | ALM | required | **unknown** | Definition is Git-shaped and versioned; Git integration and deployment pipelines not tried (F13) |
| 6.1.1 | CICD manifest section | optional | not met | None |
| 6.2 | Private Links | required | met (draft) | Attested "not supported" (the template allows it) |
| 6.3 | Data Hub | required | met (draft) | Not a data item; `supportedInDatahubL1: true` to review (F10) |
| 6.4 | Data lineage | required | **not met** | Not in Fabric's lineage view (F8) |
| 6.5 / 6.5.1 | Sensitivity labels; exports | required | met (draft) | Not supported; no data export |

How "required" is meant for 6.2–6.5: the template pre-ticks "Not Supported" for Private Links, Data Hub, lineage and
labels [H1], so the requirement is the honest answer in the attestation, not the feature. Microsoft's reviewers decide;
lineage is the one most likely to be asked about (`docs/WORKLOAD-FEASIBILITY.md`).

### 1c. Item requirements [H3], Krusgraph Model

| # | Requirement | Preview | Status | Evidence / what is missing |
| --- | --- | --- | --- | --- |
| 1.1 | Clear item name | required | met | "Krusgraph Model" (`translations.json`) |
| 1.2 | Clear icon | required | met (file) | `ModelItem_Icon.png` 48×48; Fabric's container/interior style manual |
| 1.2.1 | Distinct active icon | required | met (n175) | `activeIcon` is `ModelItem_Icon_Active.png`, the mark on the cream tile (F4) |
| 1.3 / 1.4 | Title and subtitle in the create menu | required | met | Card title equals the display name |
| 1.5 | Can be favourited in "new" | required | unknown | Manual |
| 2.1 / 2.4 | Platform create experience, no custom flow | required | met | `createItemDialogConfig`; founder's run 8 Nov 2026 |
| 2.2 / 2.3 | Creation Hub, workspace + New | required | met | `availableIn` has `create-hub`, `workspace-plus-new` |
| 2.5 | Persisted in the workspace | required | met | Founder's run 8 Nov 2026 (`shop_krusgraph` in workspace demo, `docs/WORKLOAD-DEV.md`) |
| 2.6 | In the multitasking menu, supports the behaviour | required | **unknown** | `editorTab` handlers come from the starter kit (`ModelItem.json`, `index.ui.tsx`: `canDeactivate` always true); switching between two open Models, and unsaved state on switching, not tested (F14) |
| 2.7 | Creation under `*.powerbi.com` and `*.fabric.microsoft.com` | required | **unknown** | Only `app.fabric.microsoft.com` used; the dev app has `workloadSignIn` redirects for both (F15) |
| 3.1 / 3.3 | One sticky ribbon, Home first; tabs do not switch the canvas | required | met (code) | `ModelItemEditor.tsx` ("one sticky ribbon, Home first"); **List**/map switch is in the canvas, check it is not a ribbon tab |
| 3.2–3.10, 3.2.10 | Ribbon style: subtle buttons, ≤ 32 px, colour, type, elevation, radius, spacing, tooltips | required | unknown | Starter kit's `Ribbon`; manual UX tests |
| 3.4 | Save button or autosave | optional | met | `createSaveAction` in the Home ribbon |
| 4.1–4.8 | Canvas border, empty state, drawers, tabs, switches, centre control | required | unknown | Manual UX tests; the mascot switch and the map are own components |
| 5.1 | Multi-level navigation | required | unknown | Manual |
| 6.1–6.6 | Dialog style | required | unknown | Manual |
| 7.1 | Monitoring Hub | optional | not met | `supportedInMonitoringHub: false` |
| 7.2 | Workspace actions (rename, delete, share) work | required | unknown | Manual (F14) |
| 7.3 / 7.4 | Trial, monetization experience | optional | partial | Free reading and dry runs; 402 with offer link when gating is on |
| 7.5 / 7.6 / 7.7 | Jobs, item settings, custom actions | optional | not used | Manifest has none |

## 2. The validator

### What it is and what it checks [H4][H5][H8]

A Node.js command-line tool (Node 14 or later) from Microsoft, MIT. One run:

1. **Manifest download.** It opens Chrome (through Puppeteer, with its own profile folder `browser-data/`) on
   `https://app.fabric.microsoft.com/workloadhub/my?experience=fabric-developer` and then the workload's page
   `…/workloadhub/detail/<WorkloadName>.Product`, and captures Fabric's `/metadata/extensions/manifests/…` answer. So the
   browser must be **signed in to Fabric** and the workload **published to that tenant** (`manifest_downloader.js`).
2. **Tests** from its specifications, by stage: 61 workload tests and 45 item tests per item type at commit `78e17c3`.
   Automated: manifest fields, links (HTTPS, 200–399, the Marketplace domains for the license link), images (PNG/JPEG/SVG
   and dimensions: banner 1920×240, other icons 16–64 px squares), and the attestation (downloaded from
   `certification.url`, website or PDF, searched case-insensitively for each requirement's terms and for "Workload Name"
   and the workload's name). Interactive: "manual" tests with instructions, answered by the person running it, and UX
   tests on the editor's CSS (ribbon, tabs, canvas).
3. **Report** in `Results/<Workload>/<Stage>/<ValidationId>/Reports/ValidationReport.md`, `.html` and `.pdf`, with the
   manifest and per-test JSON next to it.

"Successful self-validation is no guarantee for passing official validation" [H4].

### Why it does not run in CI

It needs a Fabric session in a real browser and a published workload; there is no option for a local manifest or a
`.nupkg` (`index.js` options: `--workload-name`, `--workload-stage`, `--print-testcases`, `--skipInteractiveTests`,
`--skipPassedTests`, `--skipUpdates`). Running it here would need the founder's credentials in CI, which this
repository never holds (`CONTRIBUTING.md`).

### What CI runs instead: `tools/hub_readiness.py`

`.github/workflows/hub-readiness.yml` (a separate workflow, on changes to the manifest, the attestation draft or the
script, and by hand) fetches the validator at the pinned commit, reads its two specification files as data, and checks
`workload/Workload/Manifest/` and `docs/HUB-ATTESTATION.md` against them. Offline step: **red only when the attestation
draft lacks a term the validator searches for**, or the specifications cannot be read (a new validator format means
re-reading this page). Online step (links and the hosted attestation): report only. The report is the job summary and
the artifact `hub-precheck` (30 days).

Result on this commit's files, run locally (validator `78e17c3`, offline), required tests only: **manual 48, met 8,
met (draft) 24, met (offline) 5, not met 4, unknown 3**. The four automated failures: 1.3.1 and 1.3.2 (license link not
on a Marketplace domain), 3.1.2.1 and 3.1.2.2 (product icon and favicon 256×257). The three unknowns are the tab icons
and custom-action icons, which exist only in the manifest Fabric serves. The online step will also mark 1.4.1 and every
attestation term "not met" until the attestation is hosted at the manifest's `certification.url`: today that URL is the
/it page.

### How the founder runs it (after steps 1–7 below)

In a **second tenant** (Microsoft's advice: "Use a different tenant for validation than the one used for publishing"
[H4]), i.e. one of the selected test tenants the workload was published to, with its admin's "Users can see and work
with additional workloads not validated by Microsoft" turned on [L8]:

```bash
git clone https://github.com/microsoft/fabric-extensibility-toolkit-validator
cd fabric-extensibility-toolkit-validator/validator
npm install                                   # installs Puppeteer, which downloads its own Chrome
cd ..
node --no-deprecation validator/index.js --workload-name "Krusgraph.Modeler" --workload-stage Preview
```

1. Chrome opens; **sign in to Fabric with the test tenant's account** (the profile is kept in `browser-data/`, so
   later runs reuse it). Check that the Workload Hub shows Krusgraph.
2. Answer the manual tests in the terminal (value to customers, publisher name, Entra app, `Fabric.Extend`, redirect,
   multitasking, both domains, workspace actions, the UX tests on an open Krusgraph Model). Have a Model with a review
   open in a workspace.
3. Read `Results/Krusgraph.Modeler/Preview/<id>/Reports/ValidationReport.md`; fix, then run again (passed tests are
   skipped by default).
4. Keep the PDF for the publishing request; add a short note to this page with the date and the counts.

The README's examples write the stage as `Preview` or `GA`; the code's help text says `PublicPreview, GeneralAvailability`
and its specifications use `Preview` and `GeneralAvailability`. Use `Preview`; for GA try `GeneralAvailability` if `GA`
finds no tests.

## 3. The founder's steps, in order

Each step needs the previous one. Steps the rounds can prepare are marked (rounds).

| # | Step | Needs | Source |
| --- | --- | --- | --- |
| 1 | **Real Marketplace SaaS offer live** (not `krusgraph-dev`, which must never go live): create the PROD offer in Partner Center with publisher name Kruse Consulting AB, plans, the landing page and webhook of `docs/MARKETPLACE-SETUP.md`; publish; wait for certification (no overall time documented [L23]). Switch `KRUSGRAPH_MARKETPLACE`/`ENTITLEMENTS` on only with the /privacy and /terms changes of `docs/MARKETPLACE-SETUP.md` §6. | Commercial Marketplace enrolment, tax and payout profiles [L19][L21] | [H2 1.3.1][L9] |
| 2 | **Verified publisher on the workload's Entra app**: create or rename the listing app (e.g. "Krusgraph", publisher domain krusgraph.com), multitenant, resource-id URI, `Fabric.Extend`; mark it publisher verified with the same MPN account as the MCP app | Step 1's partner account (already verified for the MCP app, `docs/SCOPES.md`) | [H2 2.1.1, 4.1.4][S26] |
| 3 | **Decide and register the name**: `Krusgraph.Modeler` or another (≤ 32 characters after the dot); build the package with it (rounds: F1) and upload; confirm the name dialog. Permanent. | Steps 1–2 decided; manifest fixes F2–F4, F7 merged | [H6] |
| 4 | **Publish to selected tenants** (up to 20), including the second tenant for the validator | Step 3 | [H6] |
| 5 | **Correct and sign the attestation** (`docs/HUB-ATTESTATION.md`): every "founder to confirm"; close or honestly state every "not met yet" | Steps 1–2 (offer URL, app) | [H1] |
| 6 | **Host Section III at a public HTTPS URL** (e.g. `https://krusgraph.com/attestation`, a page or a PDF; rounds: F3) | Step 5 | [H1][H2 1.4.1] |
| 7 | **Manifest links**: license → the live offer's URL; certification → step 6's URL; publisher → the Marketplace publisher name; terms, privacy, docs, help as now; new package version, upload, activate (rounds: F2, F3) | Steps 1, 6 | [H2 1.2–1.4, 5.2.1] |
| 8 | **Validator report** from the second tenant (section 2); fix and repeat until the automated tests pass and the manual answers are honest | Steps 4, 7 | [H4][H5] |
| 9 | **Publishing request**: the form at `https://aka.ms/fabric_workload_publishing`, with the attestation (Sections I–III) and the report | Step 8 | [H6][S3] |
| 10 | Address Microsoft's feedback; on acceptance the workload is listed as Preview to all tenants. **Review time: not documented.** | Step 9 | [H6] |

## 4. Findings: code changes before a listing

Each is a one-line round brief for a later Workload round (this round touched no `workload/` code). "Area" is the
claim table's.

| # | Area | Brief |
| --- | --- | --- |
| F1 | Workload, Deployment | Build the package with a configurable workload name and the listing Entra app's id (not `Org.Krusgraph`, not the "(dev)" app), behind an explicit flag so no round can upload a `Krusgraph.*` name by accident. |
| F2 | Workload | `Product.json` `productDetail.publisher`: the Marketplace publisher name (founder's choice, e.g. "Kruse Consulting AB" or "Krusgraph"), set from `.env`, not "Krusgraph (development build)". |
| F3 | Workload, Website | `supportLink.certification.url` → the hosted attestation (a new static page `/attestation` rendered from Section III, or a PDF); `supportLink.license.url` → the live offer's URL from `.env`; the Hub validator's link checks pass. |
| F4 | Workload | Product icon and favicon as square PNGs the validator accepts (64×64, plus a 240×240 product icon if Microsoft's page is right; ask), not 256×257; a distinct active item icon (`activeIcon`). |
| F5 | Workload, MCP tools and errors | Cross-tenant consent: a pilot tenant's admin-consent path for the workload app (consent URL and a one-page admin guide), and a clear editor message when `Fabric.Extend` or a permission is not consented in that tenant. |
| F6 | Workload | Conditional Access: when the on-behalf-of exchange returns `interaction_required` or a claims challenge, show it in the editor with the next step, and test with a CA policy in the founder's tenant. |
| F7 | Workload | Hub texts (`translations.json`): the description still says semantic models, reports and pipelines "come later"; say what n174 builds, and keep the card and the create subtitle in step. |
| F8 | Workload, Engine | Lineage: ask Microsoft how a workload item appears in Fabric's lineage view; until then show the source lakehouse and the built items' ids in the item, and say "not supported" in the attestation. |
| F9 | Workload, Engine | Activity id: log Fabric's request/activity id (or our own per-call id shown in the editor's error bar) with every engine call, so a support case maps to a log line within the 30-day retention. |
| F10 | Workload | Decide `supportedInDatahubL1` for a non-data item (starter kit value `true`) and `itemJobTypes` (`storeData`, `others`, unused). |
| F11 | Workload, Tests | Measure the editor's load in the Fabric frame (under 3 s [H7]): a Playwright timing of the built editor from `workload.krusgraph.com` in CI, and the bundle size. |
| F12 | Docs and submission | A security and privacy review by someone other than the author (scope, date, findings, fixes) to cite in the attestation's Security general and Privacy sections. |
| F13 | Workload, Tests | ALM: a definition round trip through Fabric Git integration and a deployment pipeline on the synthetic schema; the Variable Library for `source.json`'s workspace and item ids. |
| F14 | Workload | Multitasking and workspace actions: two Models open at once, switching keeps unsaved edits or asks (`canDeactivate` is always true today), rename, delete and share from the workspace. |
| F15 | Workload, Deployment | Both Fabric domains: create and open a Model under `app.powerbi.com` as well as `app.fabric.microsoft.com`; check the listing app's `workloadSignIn` redirects for both. |

## 5. The top five gaps

1. **No live Marketplace offer** (1.3.1, 1.3.2, 1.3.4): the first hard blocker, and the slowest (enrolment, profiles,
   certification with no documented time).
2. **Workload Entra app not verified and named "(dev)"** (2.1.1, 4.1.4), and no `Krusgraph.*` name registered: the
   listing package does not exist yet (F1).
3. **Attestation not hosted, and the manifest points to /it** (1.4.1, and every attestation-checked requirement), with
   no independent security or privacy review behind sections 4.1 and 4.2 (F3, F12).
4. **Manifest assets and texts the validator fails**: product icon and favicon 256×257, same active icon, publisher
   "Krusgraph (development build)", outdated description (F2, F4, F7). *Done in n175* (64 px icon, 32 px favicon, a
   distinct active icon, publisher Kruse Consulting AB, the description of every output); the pre-check now has 2 of
   the 4 automated failures left, both the Marketplace licence link (1.3.1, 1.3.2).
5. **Fabric platform behaviour untested**: Conditional Access, multitasking, `*.powerbi.com`, cross-tenant consent,
   lineage and ALM (F5, F6, F8, F13–F15); each is a manual validator test or an attestation answer.

## Sources

Read on **9 November 2026**. "Learn commit" is the `git_commit_id` the page reports.

| # | Title (`ms.date`) | URL | Learn commit / source |
| --- | --- | --- | --- |
| H1 | Vendor Attestation Document Template (2026-02-24; last updated 2026-08-30) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-vendor-attestation-template | `e567e67` |
| H2 | Validation guidelines and requirements for workloads (2026-02-24; last updated 2026-02-24) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-workload | `5e656ad` |
| H3 | Validation guidelines and requirements for items (2026-02-24) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-item | `bd2c301` |
| H4 | Microsoft Fabric Extensibility Toolkit Validator (2025-12-04; last updated 2025-12-16) | https://learn.microsoft.com/fabric/extensibility-toolkit/tools-workload-validator | `5156dc5` |
| H5 | Validate your workload for publishing (2025-12-15) | https://learn.microsoft.com/fabric/extensibility-toolkit/tutorial-validate-workload | `5156dc5` |
| H6 | Publishing Overview (2026-04-08; last updated 2026-09-29) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-overview | `80a24c9` |
| H7 | General Publishing Requirements (2025-12-15; last updated 2026-01-08) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-general | `5156dc5` |
| H8 | `microsoft/fabric-extensibility-toolkit-validator`: README.md, validator/README.md, validator/index.js (options), validator/downloaders/manifest_downloader.js, validator/validators/attestation_validator.js and image_validator.js (behaviour only), specifications/testcases/Testcases_Workload.json and Testcases_Item.json | https://github.com/microsoft/fabric-extensibility-toolkit-validator | commit `78e17c3` (15 December 2025); LICENSE MIT (Copyright (c) Microsoft Corporation), read at that commit |

The pages' requirements match what n153 and n167 read ([S9], [L4]); what is new here is the item page's itemised list
[H3] (multitasking 2.6, both domains 2.7) and the validator's own test cases [H8]. Two inconsistencies, noted for the
founder: the workload page asks for a 240×240 product icon in a heading but lists 16–64 px formats beneath, and the
validator checks the 16–64 px set [H2 3.1.2.1][H8]; the validator's specification checks test 4.1.1 with the terms of
2.10 ("World Readiness"), a copy error on Microsoft's side that makes no difference to a complete attestation.
