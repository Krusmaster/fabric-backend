# Publishing readiness: the Krusgraph Fabric workload

Round W11, 15 November 2026. Where the workload stands against Microsoft's publishing flow, one table per stage: what
Microsoft requires, our status (**met**, **gap**, **unknown**), the evidence, the smallest fix and who does it (a round or
the founder). It updates `docs/HUB-READINESS.md` (n178, 9 November) and sits next to the founder's runbook
`docs/WORKLOAD-PUBLISH.md` (n195), which keeps the click-by-click steps. Nothing was uploaded, created, changed or
submitted in Fabric, Entra, Azure or Partner Center by this round. Business matters (contacts, customers, prices) are in
the private repository, not here.

**Status words.** *met*: the repository or a recorded run shows it. *gap*: known to be missing. *unknown*: nothing here
proves it either way, usually because it needs a run in Fabric or a page we could not open. A "met" on an attestation
point means the draft answers it truthfully, not that Microsoft accepted it.

## Sources (read 15 November 2026)

Microsoft Learn, `learn.microsoft.com/fabric/extensibility-toolkit/…` (ms.date / last update as shown on the page):

| # | Page | ms.date / updated |
| --- | --- | --- |
| R1 | `publish-workload-flow`: now redirects to `publishing-overview` | 2026-04-08 / 2026-09-29 |
| R2 | `publishing-requirements-overview` | 2026-04-08 / 2026-09-29 |
| R3 | `publishing-requirements-general` | 2025-12-15 / 2026-02-17 |
| R4 | `publishing-requirements-workload` (learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-workload) | 2026-02-24 / 2026-03-11 |
| R5 | `publishing-requirements-item` | 2026-02-24 / 2026-03-04 |
| R6 | `publishing-vendor-attestation-template` | 2026-02-24 / 2026-08-30 |
| R7 | `tutorial-publish-workload` | 2025-11-18 / 2026-09-29 |
| R8 | `tutorial-validate-workload` | 2025-12-15 / 2026-02-17 |
| R9 | `manifest-overview`, `manifest-workload`, `manifest-product`, `manifest-item` | 2025-12-15 / 2026-03-04 to 2026-09-29 |
| R10 | `how-to-configure-workload-media-section`, `how-to-monetize-workload` | 2025-12-15 / 2026-02-17 |

Partner Center, `learn.microsoft.com/partner-center/marketplace-offers/…`: P1 `create-new-saas-offer` (2026-07-22 /
2026-10-01), P2 `plan-saas-offer` (2026-07-22), P3 `create-new-saas-offer-listing` (2025-01-29 / 2025-09-25), P4
`create-new-saas-offer-technical` (2026-08-10 / 2026-09-01).

**Unverified (could not open):** the Publishing Request Form `https://aka.ms/fabric_workload_publishing` (outside this
session's network; its page 2 is known only from the founder's reading, `docs/WORKLOAD-PUBLISH.md` step 8);
`create-new-saas-offer-technical-publish` (404); krusgraph.com and workload.krusgraph.com (the proxy refused both, so
no live link was fetched by this round; CI's `hub-readiness` job fetches them). No page read describes test accounts
Microsoft needs for validation, or a review time.

**Microsoft's pages contradict themselves in four places** (worth asking, below): 3.1.2.1 says the product icon is
240×240 while its automated check takes 16 to 64 px; 3.1.5 says the banner is 1920×240 while its check lists the same
16 to 64 px; the image checks allow SVG while the package takes only PNG/JPEG; and `how-to-monetize-workload` allows
billing outside Marketplace while 1.3.1 requires a published Marketplace offer at Preview.

## The flow, in short [R1][R2][R7]

1. Register a `[Publisher].[Workload]` name: at the first upload, in the **Confirm workload Name** dialog; "permanently
   reserved in your tenant after confirmation and can't be changed". The workload part is at most 32 characters.
2. Test cross-tenant: **Publish → Selected tenants**, up to 20 tenant ids, up to 10 minutes to show; each target admin
   turns on *Users can see and work with additional workloads not validated by Microsoft*.
3. Run Microsoft's validator (`microsoft/fabric-extensibility-toolkit-validator`) [R8].
4. **Preview:** submit the Publishing Request Form, answer Microsoft's feedback; the workload is listed in the Workload
   Hub to every tenant with a Preview badge.
5. **General availability:** submit the same form again to remove the badge; 5.1 and 5.2 become required.

The Marketplace offer (1.3.1) is required already at Preview, so Partner Center runs in parallel from step 1.

## Where we are (15 November 2026)

- `Org.Krusgraph` runs in the company tenant; the last package uploaded was **1.0.1074** (the founder's test of 12
  November 2026, `CHANGELOG.md`, round n225), Entra app `853a0cf0-7d35-42b7-b384-26178755a72a`.
- `Krusgraph.Modeler` is built by CI but has never been accepted by Fabric: its upload on 10 November failed with the
  name-registration error (`docs/WORKLOAD-PUBLISH.md` step 1). Nothing in this repository records the answer to the
  support ticket; **unknown** whether it is solved.
- The Marketplace landing page and webhook exist, off by default (`docs/MARKETPLACE-SETUP.md`); the DEV offer
  `krusgraph-dev` is for preview testing only and never goes live (same page, section 5). No production offer exists.

## Blockers, ranked

| # | Blocker | Stage | Who |
| --- | --- | --- | --- |
| 1 | The permanent name is not registered: `Krusgraph.Modeler`'s upload is refused, and an `Org.*` name can never be listed | 0 | founder with Microsoft |
| 2 | No published production Marketplace offer, so no license link (1.3.1, 1.3.2) | 2, 4 | founder (Partner Center) |
| 3 | The workload's Entra app has no publisher verification and is named "Krusgraph workload (dev)" (2.1.1, 4.1.4) | 0, 2 | founder (Entra) |
| 4 | Attestation still a draft with open points (2.3 Conditional Access, 2.4 activity id, 4.1 security assessment, 4.2 privacy review), unsigned | 2 | founder; 2.4 also a round |
| 5 | Validator not run against a published `Krusgraph.Modeler` | 2 | founder |
| 6 | 99.9% uptime SLA stated as a general requirement; one container app, no SLA | 0, 3 | founder (decision) |

## Stage 0. Registration and prerequisites (both stages) [R2][R3][R9]

| Microsoft requires | Status | Evidence | Smallest fix | Who |
| --- | --- | --- | --- | --- |
| `[Publisher].[Workload]` name, workload part ≤ 32 characters, reserved for good at first upload | **gap** | `workload/scripts/build_package.py:42` (`Krusgraph.Modeler`, 7 characters after the dot); upload refused 10 Nov (`docs/WORKLOAD-PUBLISH.md:34`) | Microsoft enables the tenant to register the name; then upload and confirm letter by letter | founder with Microsoft |
| Publishing tenant defined | met | company tenant (`docs/WORKLOAD-PUBLISH.md:14`) | none | — |
| Verified custom domain, no `*.onmicrosoft`; frontend a subdomain with at most one extra segment; HTTPS | met | `build_package.py` `check_frontend_url`; `workload.krusgraph.com` | none | — |
| Entra app multitenant, redirect `{frontend}/close`, Application ID URI on the verified domain | met (Org.Krusgraph); unknown (Krusgraph.Modeler URIs added?) | `docs/WORKLOAD-PUBLISH.md` A1 | run A1 once, then check | founder |
| App type "Web" | unknown | the app has SPA redirects (`docs/HUB-READINESS.md` 1a) | ask Microsoft whether SPA passes 2.1.3 | founder asks |
| Publisher verification on the Entra app, before publishing | **gap** | `docs/WORKLOAD-PUBLISH.md` step 2 not recorded as done | Entra → Branding & properties → publisher domain `krusgraph.com` → Partner One ID (PGA) → Verify | founder |
| `/close` runs only `window.close()` | met | `fabric_backend/workload_host.py`; `tests/test_workload_host.py` | none | — |
| CORS for `*.powerbi.com`, `*.fabric.microsoft.com`; CSP frame-ancestors | met | `fabric_backend/workload_api.py` (`FRAME_ANCESTORS`); `tests/test_workload_api.py` | none | — |
| 99.9% uptime SLA | **gap** | one Azure Container App, no SLA (`docs/HUB-READINESS.md` 1a) | decide what to state; the attestation says what is true | founder |
| Page load under 3 s | unknown | not measured in the Fabric frame | measure once in Fabric | round (after upload) |
| Package: only BE/FE, Product.json ≤ 50 KB, package ≤ 20 MB, ≤ 15 assets of ≤ 1.5 MB, PNG/JPEG | met | `build_package.py` `check()` (50 KB, 20 MB); 8 PNG assets in `workload/Workload/Manifest/assets/images/` | none | — |
| Asset file names alphanumeric or hyphen, ≤ 32 characters | unknown | our names have underscores (`Workload_Hub_SlideMedia_1.png`, from the starter kit); Fabric accepted them in every upload up to 1.0.1074 | leave; rename only if Microsoft's review asks | — |
| Unique semantic version per upload | met | `build_package.py` `default_version` (1.0.<commits>) | none | — |

## Stage 1. Selected tenants (testing before the request; no Microsoft review) [R1][R7]

| Microsoft requires | Status | Evidence | Smallest fix | Who |
| --- | --- | --- | --- | --- |
| A registered name to publish beyond the own tenant | **gap** | as stage 0 | as stage 0 | founder with Microsoft |
| Up to 20 tenant ids on the Publish tab; target admin turns on the "not validated" setting and consents | ready on paper | `docs/WORKLOAD-PUBLISH.md` steps 4–5; `docs/PILOT-ONBOARDING.md` | follow the runbook | founder, target admins |
| Our server answers the target tenant | ready on paper | `workload_allowed_tenants` (`docs/WORKLOAD-PUBLISH.md` A2) | add each tenant id, redeploy | founder |
| Microsoft's test tenant in the audience for a Preview request | unknown | the form, as read by the founder (`docs/WORKLOAD-PUBLISH.md:133`); not on Learn | add it on the Publish tab and to `workload_allowed_tenants`; confirm with Microsoft | founder |
| Validator run, ideally from another tenant | **gap** | not run (`docs/WORKLOAD-PUBLISH.md` step 7); CI pre-check `.github/workflows/hub-readiness.yml` | run it after the first selected-tenant publish | founder |

## Stage 2. Preview listing in the Workload Hub [R4][R5][R6]

Only the points with something to do or to know are listed; the full row-by-row table of every requirement is
`docs/HUB-READINESS.md` section 1, whose statuses still hold except where this table says otherwise.

| # | Microsoft requires | Status | Evidence | Smallest fix | Who |
| --- | --- | --- | --- | --- | --- |
| 1.1 | Clear value | met (draft) | `assets/locales/en-US/translations.json` `Workload_Hub_Description` | none | — |
| 1.2.1 / 1.2.2 | Terms and privacy URLs, HTTPS, 200–399 | met offline; live unknown | `workload/Workload/Manifest/Product.json:86`–`:91`; routes in `fabric_backend/pages.py:51`, `:71`, `:1291` | CI `hub-readiness` fetches them | — |
| 1.3.1 | Published Marketplace offer; license URL on azuremarketplace / appsource / marketplace.microsoft.com | **gap** | `Product.json:92` is the MIT licence on GitHub | **W11:** `build-package --offer-url <live offer page>` fills it and refuses `krusgraph-dev`, preview links and other hosts (`build_package.py:157`); needs the production offer first | founder (offer), then one build |
| 1.3.2 | Offer link correct | **gap** | as 1.3.1 | as 1.3.1 | founder |
| 1.3.3 / 1.3.4 | Publisher name clear, the same as the Marketplace listing | met in manifest; listing unknown | `Product.json:59` "Kruse Consulting AB" | use exactly this publisher display name in Partner Center | founder |
| 1.4.1 | Attestation URL in `supportLink.certification.url`, following the template | gap (draft) | `build_package.py` `ATTESTATION_URL`; `fabric_backend/page_templates/WORKLOAD-ATTESTATION.md:3` says **Draft.** | answer open points, remove the Draft paragraph, redeploy | founder |
| 1.4.2–1.4.5 | Getting started, at a glance, static learning pages, documentation URL | met / 1.4.4 unknown | `Product.json` `learningMaterials`, `slideMedia` (YouTube embed plus one image) | none | — |
| 2.1.1 / 4.1.4 | Verified Entra app; name and publisher aligned with the workload | **gap** | app named "Krusgraph workload (dev)" | rename to "Krusgraph", publisher verification (stage 0) | founder |
| 2.1.2 | Static dependency on `Fabric.Extend`, user consent | met (own tenant); other tenants unknown | `docs/HUB-READINESS.md` 1b | confirm on the first selected tenant | founder |
| 2.3 | Conditional Access | unknown | not tested | test once with a CA policy in a test tenant | founder |
| 2.4 | Customer-facing monitoring, ≥ 30 days, activity id | **gap** | no Fabric activity id in the logs (`docs/HUB-READINESS.md` 1b) | a round adds the activity id to the workload routes' log lines | round (Workload/engine owner) |
| 2.10 | English default | met | only `assets/locales/en-US` | none | — |
| 3.1.2.1 | Product icon "(240x240)"; the check takes 16–64 px | unknown | `Workload_Icon.png` 64×64, passes the check | ask Microsoft which applies | founder asks |
| 3.1.2.2–3.1.2.7 | Favicon, create, small, tab and active icons | met (files) | 32×32 favicon, 48×48 item, 24×24 small, 48×48 active; `tests/test_workload_manifest.py` | none | — |
| 3.1.5 | Banner 1920×240 | met | `Workload_Hub_Banner.png` 1920×240 | none | — |
| 4.1 / 4.2 | Security assessment, privacy review (attested) | **gap** | attestation says Not yet | decide who reviews and when; the attestation stays honest meanwhile | founder |
| 4.4 | Compliance attestation | met (draft) | states none; claims no certification | none | — |
| 5.2.1 / 5.2.2 | Help URL; support contact on the product page | met / unknown | `Product.json:83` → /support (mail link in `page_templates/support.html`) | check in the Hub page after upload | founder |
| 6.1–6.5 | ALM, Private Links, Data Hub, lineage, labels (attested) | draft answers | `docs/HUB-READINESS.md` 1b | Microsoft decides; lineage the likeliest question | founder asks |
| Item 2.6, 2.7, 7.2 | Multitasking; creation under powerbi.com and fabric.microsoft.com; workspace actions | unknown | not tested (`docs/HUB-READINESS.md` 1c) | one manual pass in Fabric, noted in `docs/WORKLOAD-DEV.md` | founder |
| Item 3.x–6.x | Ribbon, canvas, dialogs to the style guide | unknown | starter kit components; manual | the validator's guided manual tests | founder |
| Form | Publishing Request Form (stage, tenant id, workload id, version, attestation URL) | not started | `docs/WORKLOAD-PUBLISH.md` step 8 | after 1.3.1, 2.1.1 and the validator | founder |
| Attestation I + II | Company details and signed letter to Microsoft; only Section III hosted | not started | `docs/WORKLOAD-PUBLISH.md` step 6 | fill and sign when no point says Not yet | founder |

## Stage 3. General availability [R1][R4]

| Microsoft requires | Status | Evidence | Smallest fix | Who |
| --- | --- | --- | --- | --- |
| Everything of stage 2 | gap | above | above | — |
| Same request form again | not started | — | after Preview feedback | founder |
| 5.1 Live-site contacts given to Microsoft | met (draft) | attestation names the support mailbox | confirm the contact | founder |
| 5.2 Supportability: SLA and contact methods, linked from the workload page, aligned with the Marketplace listing | **gap** | no SLA; /support has a mail link only | write the support terms; link them from /support and the listing | founder (decision), then a Website round |
| 99.9% uptime SLA (general requirement) | **gap** | as stage 0 | as stage 0 | founder |
| 5.3 Service health page (optional) | gap | `/health` only | optional | — |
| 2.6 BCDR (optional at Preview) | gap | no written plan | a plan in `docs/` | round |

## Stage 4. Marketplace offer in Partner Center (needed at Preview for 1.3.1) [P1]–[P4]

| Microsoft requires | Status | Evidence | Smallest fix | Who |
| --- | --- | --- | --- | --- |
| Partner Center account enrolled in the commercial marketplace, verification complete | met (founder's report) | `docs/WORKLOAD-PUBLISH.md:39` | none | — |
| Separate DEV and production offers; offer id ≤ 50 characters, lowercase, cannot change after Create | DEV planned; production **gap** | `docs/MARKETPLACE-SETUP.md:237` (`krusgraph-dev`, never Go live) | create the production offer with a final offer id | founder |
| Listing option: Contact me / Free trial / Get it now / Sell through Microsoft; transactable cannot become listing-only later | **decision** | — | decide; a listing-only offer may meet 1.3.1 but no page says so (ask) | founder |
| Transactable: landing page, connection webhook, Entra tenant id and app id, MSA + Entra sign-in | met in code, off by default | `fabric_backend/marketplace.py`; `docs/MARKETPLACE-SETUP.md` sections 2–4; `tests/test_marketplace.py`, `tests/test_n204_marketplace_personal_accounts.py` | switch on after the DEV offer test | founder |
| At least one plan; pricing model cannot change after publishing | **decision** | no price decided | decide (private repository) | founder |
| Listing text: name ≤ 200, summary ≤ 100, description ≤ 5,000, getting started ≤ 3,000, privacy URL | gap (not drafted for Partner Center) | the Hub texts in `translations.json` are a start | draft the listing texts in the private repository | round (Opus/Fable) then founder |
| Support and engineering contacts, public support URL | partly | https://krusgraph.com/support | founder names the contacts | founder |
| Logo PNG 216×216 to 350×350, square | **gap** | `fabric_backend/static/icon-512.png` is 512×512 | export a 300×300 PNG of the mark | round |
| 1–5 screenshots PNG 1280×720 with captions | **gap** | `docs/screenshots/` has site captures, none of the editor in Fabric at 1280×720 | capture the editor in Fabric at 1280×720 on synthetic data | founder (needs Fabric sign-in) |
| 1–3 PDF documents | gap | none | a one-page PDF of /docs or /it | round |
| Certification policies (general and 1000 SaaS) | unknown | `docs/MARKETPLACE-CERTIFICATION-NOTES.md` | Microsoft's offer certification decides | Microsoft |
| Trial / entitlement in the product | met in code, off by default | `fabric_backend/entitlements.py:50` (`KRUSGRAPH_ENTITLEMENTS`), `:69` (upgrade link from `KRUSGRAPH_MARKETPLACE_OFFER_URL`); `docs/BILLING-MODEL.md` | set the offer URL in the server settings when the offer is live | founder |

## What W11 changed

- `workload/scripts/build_package.py`: `--offer-url`. With the production offer's page it fills
  `productDetail.supportLink.license.url` (1.3.1, 1.3.2) and the build's "not ready" line disappears; it refuses the DEV
  offer `krusgraph-dev`, a preview-audience link (`flightCodes`), the storefront's front page, http and any host but
  the three Microsoft names. Without it the package is byte-for-byte as before. Tests: `tests/test_w11_offer_url.py`.
- This page. No price, no offer, no upload, no submission.

## The switch to Krusgraph.Modeler (decided 15 November 2026)

Every place the name lives, and what it needs. Nothing has been registered or uploaded.

| Place | Today | Change | When | Who |
| --- | --- | --- | --- | --- |
| Package build `workload/scripts/build_package.py` | builds both; `Org.Krusgraph` is the default, `--name Krusgraph.Modeler` the listed one; every other `Krusgraph.*` name is refused | none needed now. The default stays `Org.Krusgraph` until the name is registered, so a routine rebuild of the running development workload never makes a package whose upload fails or reserves a name by accident; flip the default in the round after step N3 | after N3 | round (Workload) |
| Manifest templates `workload/Workload/Manifest/` | the name only through `{{WORKLOAD_NAME}}`; item type `<name>.Model` | none | — | — |
| Product.json publisher, links | Kruse Consulting AB; attestation link for both names | none; license link via `--offer-url` (1.3.1) | after the offer | founder, one build |
| CI `.github/workflows/ci.yml` | builds and checks both packages | none | — | — |
| Frontend `workload/Workload/app/` | one editor for both names: the workload is read from the item type (`index.worker.ts:45`, `ModelItemEditor.tsx:295`, `engineClient.ts:587`) | none | — | — |
| Editor fallback name `Dockerfile:19` (`WORKLOAD_NAME=Org.Krusgraph`) | used only before an item is open | set to `Krusgraph.Modeler` when `Org.Krusgraph` is retired | after N7 | round (Deployment) |
| Server `KRUSGRAPH_WORKLOAD_APP_ID_URI` (`fabric_backend/entra.py:224`) | a comma list; accepts tokens for either URI | add `https://krusgraph.com/workload/workload/Krusgraph.Modeler` (runbook A2); drop the `Org.Krusgraph` URI at N7 | N2, N7 | founder (`deploy/krusgraph.json`) |
| Entra app `853a0cf0-…` | `Org.Krusgraph` redirect and Application ID URIs | add the four `workloadSignIn/…/Krusgraph.Modeler` redirects and the `Krusgraph.Modeler` URI (runbook A1); rename the app "Krusgraph"; publisher verification | N1, N2 | founder |
| Hosted attestation `fabric_backend/page_templates/WORKLOAD-ATTESTATION.md` | already names `Krusgraph.Modeler`; the Section III contact row says `gustav@krusgraph.com` | contact to hello@krusgraph.com | next Website round (the Website area is held tonight) | round (Website) |
| Pilot page `page_templates/pilot_fabric.html:31` | says the item runs as `Org.Krusgraph` until Microsoft registers the name | reword once registered | after N3 | round (Website) |
| Docs `docs/WORKLOAD-DEV.md`, `docs/WORKLOAD-PUBLISH.md`, this page | `Krusgraph.Modeler` is the listed name throughout | `docs/WORKLOAD-DEV.md` keeps `Org.Krusgraph` as the development path until N7 | after N7 | round (Docs) |
| Tests | pin both names and the refusal of other `Krusgraph.*` names (`tests/test_workload_publish.py`, `tests/test_deploy_workload.py`) | change with the default flip | after N3 | round (Tests) |

**Registering `Krusgraph.Modeler`, the founder's steps:**

- N1. Entra: add the `Krusgraph.Modeler` redirect URIs and Application ID URI to the app (runbook A1); rename it "Krusgraph".
- N2. Server: add the `Krusgraph.Modeler` URI to `workload_app_id_uri`, `bash deploy/krusgraph.sh --update` (runbook A2).
- N3. Get the "not registered with Microsoft" upload error resolved (runbook step 1); then build
  `workload/scripts/build-package --name Krusgraph.Modeler --frontend-app-id 853a0cf0-7d35-42b7-b384-26178755a72a`,
  upload it under Govern → Workloads, read the name in **Confirm workload Name** letter by letter (`Krusgraph.Modeler`,
  17 characters), Confirm. From here the name is reserved in the tenant for good.
- N4. Activate the version; in the company tenant create a Krusgraph Model under **+ New item** and run Review on the
  synthetic shop schema.
- N5. Publish to selected tenants (stage 1).

**What happens to `Org.Krusgraph`** (Learn [R2][R7]; the rest **Unverified**, check on first run):

- N6. Keep it active until `Krusgraph.Modeler` works end to end; both can be listed side by side, told apart under Govern
  → Workloads.
- Its items (type `Org.Krusgraph.Model`, e.g. in the demo workspace) do not become `Krusgraph.Modeler.Model` items:
  an item type follows its workload name, so a Model is created again under `Krusgraph.Modeler`. Its outputs (notebooks,
  views, models, the API) are ordinary Fabric items and stay.
- N7. Then deactivate `Org.Krusgraph` (the active version cannot be deleted until the workload is deactivated [R7]) and
  remove it; drop its URI from the server and its redirect and Application ID URIs from the Entra app. Whether Fabric
  removes or only hides its existing items on deactivation is **Unverified**: delete the test items by hand first.
- `Org.*` names are internal only, so nothing about `Org.Krusgraph` blocks or competes with the listed name. A new
  `Org.*` workload is the way to test locally later, never a second `Krusgraph.*` name.

## Company details for listing and support fields

Kruse Consulting AB, org. no. 559174-8719, Svartmangatan 4 D, 753 12 Uppsala, Sweden; support and contact
hello@krusgraph.com (the company's public registry details, given by the founder on 15 November 2026). Filled in by W11
in the attestation's Section I (`docs/HUB-ATTESTATION.md`, `docs/WORKLOAD-PUBLISH.md` step 6). The Marketplace listing's
support contact, the attestation's Section III contact and Partner Center's company profile use the same.

## The founder's steps, in order

Decide first (none of these can be taken back once done):

- **D1. The permanent workload name: decided, `Krusgraph.Modeler`** (the founder, 9 November, confirmed 15 November
  2026). `Org.Krusgraph` cannot be listed: `Org.*` is for internal publishing only [R2]. The name is reserved for good at
  the first confirmed upload; the switch is below.
- **D2. The production offer is separate from `krusgraph-dev`.** Its offer id and alias cannot change after Create;
  never press Go live on the DEV offer.
- **D3. The listing option and pricing model** (Contact me, Free trial, Get it now, or transactable; flat rate or per
  user). Not decided; the pricing model cannot change after publishing. Prices stay in the private repository.
- **D4. What to state on SLA and support** (5.2, and the 99.9% general requirement).

Then:

1. Get the name-registration error resolved by Microsoft (`docs/WORKLOAD-PUBLISH.md` step 1).
2. Entra: rename the workload app to "Krusgraph", set publisher domain krusgraph.com, verify with the PGA Partner One ID.
3. N1 and N2 above: the `Krusgraph.Modeler` addresses on the Entra app and the server; redeploy.
4. N3 and N4 above: build, upload, confirm `Krusgraph.Modeler` letter by letter, activate. Keep `Org.Krusgraph` (N6).
5. Publish to selected tenants: a second test tenant and Microsoft's test tenant; allow them on the server.
6. In the test tenant: turn on the "not validated" setting, admin consent, create a Krusgraph Model; check multitasking,
   powerbi.com, rename/delete/share, Conditional Access.
7. Run Microsoft's validator from the test tenant (`--workload-stage Preview`); keep the report.
8. Partner Center: create the production SaaS offer (D2, D3), listing texts, 300×300 logo, 1–5 screenshots at 1280×720,
   contacts, technical configuration (`docs/MARKETPLACE-SETUP.md` section 3).
9. Test the transactable flow with `krusgraph-dev` in preview only; cancel test purchases within 72 hours.
10. Publish the production offer and Go live; wait for Marketplace certification.
11. Build again with `--offer-url <the live offer page>`, upload the new version, publish it to the selected tenants.
12. Answer the attestation's open points, remove the Draft paragraph, redeploy; fill Sections I and II and sign.
13. Submit the Publishing Request Form for Preview; answer Microsoft's feedback.
14. After Preview: SLA and support terms, then the same form again for GA.
15. Once `Krusgraph.Modeler` runs for the test tenants: retire `Org.Krusgraph` (N7).

## What to ask Microsoft's helpers

1. What does our tenant need for `Krusgraph.Modeler` to register at upload (the "not registered with Microsoft" error)?
2. Does a listing-only (Contact me or Free) production offer meet 1.3.1/1.3.2 at Preview, or must it be transactable?
3. Product icon: 240×240 (3.1.2.1 text) or 16–64 px (its check)? Our 64×64 passes the check.
4. SPA redirects on the Entra app: accepted for 2.1.3, or must the app be type Web?
5. Is a 99.9% SLA required at Preview, and how is it evidenced?
6. Must Microsoft's test tenant `afd60f91-…` be in our selected tenants before the Preview request? Any test accounts?
7. Which attestation answers block Preview: "Not supported" for lineage, Private Links, labels; no independent assessment yet?
8. The form's "Workload ID": the full `Krusgraph.Modeler` or `Modeler`? And the expected review time?
