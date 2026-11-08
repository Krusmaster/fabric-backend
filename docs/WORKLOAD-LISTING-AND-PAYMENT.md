# Reaching other Fabric tenants, and getting paid

Round n167, 8 November 2026. Documentation only: no product code, nothing created, signed up for or changed in Partner
Center, Fabric, Entra or Azure. This continues `docs/WORKLOAD-FEASIBILITY.md` (n153, sources `[Sn]`) and
`docs/WORKLOAD-DEV.md` (n166, phase 1: the item "Krusgraph Model" as `Org.Krusgraph` through DevGateway). It answers
two questions: how a Fabric user in another organisation gets to add and use the item, and how Kruse Consulting AB gets
paid for it through Microsoft. The founder's target is **Tuesday 17 November 2026**; section 4 says what fits by then.

## How this was researched

- Every fact about Microsoft carries a source number `[Ln]`; the list is at the end, with URL, the page's own `ms.date`,
  the commit Learn reports for the page, and the date read. Everything was read on **8 November 2026**.
- **learn.microsoft.com answered from this environment in this round** (it was blocked for n153), so the Partner Center
  and Marketplace pages were read as published on Learn. Their source repository, `MicrosoftDocs/partner-center-pr`,
  is **private**: it could not be cloned, and no public Microsoft repository holds the Marketplace pages any more
  (`MicrosoftDocs/azure-docs` no longer has `articles/marketplace`). Public third-party copies of those pages exist on
  GitHub; they are not primary and were not used.
- The Fabric pages were read both from `MicrosoftDocs/fabric-docs` at commit `caec836` (6 November 2026, the same
  commit n153 read) and on Learn.
- **Unconfirmed** marks anything no primary page read here states. Facts about this repository and the company come
  from the files named next to them.
- Nothing here is legal or tax advice. Amounts are Microsoft's list figures as printed on the pages, in USD.

## Summary

| Question | Short answer |
| --- | --- |
| Can the item be used in our own tenant? | Yes, as `Org.Krusgraph`, uploaded by an admin. No registration, no Microsoft review [L1][L2]. The general requirements still apply: verified custom domain, frontend on a subdomain of it, HTTPS [L3]. |
| Can `Org.Krusgraph` be used in other tenants? | No. The manifest page: use `Org.` "if you don't intend to publish to other tenants"; "for publishing across tenants, register a full WorkloadName with Fabric" [L2]. Even the 20-tenant test needs the permanent `Krusgraph.<Workload>` name [L1]. |
| Up to 20 other tenants without Microsoft's review? | Yes, once the `Krusgraph.*` name is registered: Publish tab → Selected tenants → up to 20 tenant ids. Visible within about 10 minutes, and only where that tenant's admin has turned on "Users can see and work with additional workloads not validated by Microsoft" [L1][L8]. |
| A listing for every Fabric user? | Preview, then GA, each through a publishing request that Microsoft reviews. A **published** Marketplace offer is required already for Preview [L1][L4]. **No review time is documented** in any page read. |
| Where must the editor and engine run? | On our own hosting, HTTPS, as subdomains of a domain verified in our Entra tenant; not `*.onmicrosoft` [L3]. DevGateway's `localhost` only works for the developer's own workspace [L7]. |
| How do we get paid? | A transactable ("Sell through Microsoft") SaaS offer in Microsoft Marketplace: flat rate or per user, optionally with metered dimensions on flat rate; Microsoft bills and keeps a **3% store service fee** [L9][L10][L11]. Payouts are monthly, after the customer pays (MCA) or in the next cycle (EA) [L18]. |
| Does Fabric check the licence for us? | **No.** Microsoft documents no Fabric-side licensing, capacity-based billing or licence check for partner workloads. The toolkit "does not provide additional tools for Azure Marketplace integration"; the partner tracks subscription state and gates features itself [L5][L6]. We would check the caller's tenant id against our own record of Marketplace subscriptions. |
| Partner benefits? | ISV Success, Marketplace Rewards and Azure IP co-sell are being consolidated into **Frontier Accelerate for Marketplace** (planned GA 4 September 2026): free tier and a Premium tier at USD 1,550 a year [L29][L30]. The pages disagree in places; see section 3. |
| By 17 November? | Realistic: the item working in **our own tenant**, and, if the founder registers the permanent name and the editor is hosted on a `krusgraph.com` subdomain, **one or two pilot tenants** by direct (selected-tenant) publishing, unpaid or paid outside Marketplace. **Not** realistic: a Workload Hub listing, or a customer paying through Marketplace. |

## 1. Three levels of reach

### 1a. Our own tenant (internal publishing)

| | |
| --- | --- |
| **Name** | `Org.[WorkloadName]`, e.g. `Org.Krusgraph`. "Organizational publishing doesn't require separate registration" [L1]; `Org.` is for workloads not published to other tenants [L2]. |
| **Microsoft review** | None. "Publishing requirements are only required for ISV/Software Development Company scenarios ... Organizations publishing workloads for internal tenant use do not need to meet these requirements" [L1]. |
| **Still required** | The general requirements "apply to both internal and cross-tenant publishing": a verified custom domain in the Entra tenant; frontend on a subdomain of it, at most one extra segment; reply URL on the frontend host; HTTPS everywhere; a resource-id style Application ID URI; no `*.onmicrosoft` [L3]. The page also lists 99.9% uptime and page loads under 3 seconds for all workloads [S8]. |
| **Founder does** | Upload the `.nupkg` in OneLake catalog → Govern → Configurations → Workloads, activate a version; tenant settings and capacity so users can create items [L1][L7]. |
| **We build** | The production build of the editor and its hosting on a `krusgraph.com` subdomain; the workload app's Application ID URI in the resource-id form; the package (`workload/`). |
| **Development only** | DevGateway (phase 1, `docs/WORKLOAD-DEV.md`) uploads nothing and serves the editor from `localhost:60006` to workspaces named in its configuration; while connected, it takes precedence over the activated workload for those workspaces [L7]. It is not a way to serve anyone else. |

### 1b. Up to 20 selected tenants (no Microsoft review)

| | |
| --- | --- |
| **Name** | The permanent `[Publisher].[Workload]`, workload part at most 32 characters, e.g. `Krusgraph.Modeler`. On first upload a "Confirm workload Name" dialog appears; once confirmed "the Workload Name is permanently reserved in your tenant ... and can't be changed" [L1]. |
| **Steps** | Upload the package with that name and confirm → Publish tab → "Selected tenants" → up to 20 tenant ids → choose a version → Publish. "It might take up to 10 minutes" to become visible [L1]. |
| **Each pilot tenant** | Its admin must turn on "Users can see and work with additional workloads not validated by Microsoft"; Microsoft's text asks the admin to "make sure that you trust the publishers" first [L8]. Adding the workload to a capacity needs "Capacity admins and contributors can add and remove additional workloads" (or the preview workspace-admin setting) [L8]. The pilot needs a Fabric capacity: workloads are not supported on Power BI Pro [S1], and are blocked where Private Link is on [S10]. The same page warns admins that "their data and access tokens, including name and email, are sent to the publisher" [L8]. |
| **Hosting** | Same as 1a. The workload Entra app must be **multitenant** ("required for cross-tenant publishing") [L3]. |
| **Microsoft review** | None documented for this step; the publishing requirements apply to the Workload Hub listing [L1]. |
| **Founder does** | Decide the permanent name; upload and confirm; collect each pilot's tenant id; send each admin the setting to turn on. |
| **We build** | Everything in 1a, plus the cross-tenant consent path (a pilot's admin consents to the multitenant workload app) and a short admin guide for the pilot. |

### 1c. Workload Hub listing: Preview, then GA

| | |
| --- | --- |
| **Steps** | Meet the publishing requirements → submit the Publishing Request Form (`https://aka.ms/fabric_workload_publishing`) → address Microsoft's validation feedback → on acceptance "your workload is listed as Preview to all tenants" → for GA "submit the publishing request again to remove the preview badge" [L1]. |
| **Marketplace offer** | Requirement 1.3.1 "Marketplace Offer has been published", **required at Preview and at GA**: the manifest field `product.productDetail.supportLink.license.url` must be an HTTPS URL on `azuremarketplace.microsoft.com`, `appsource.microsoft.com` or `marketplace.microsoft.com` that answers 200–399 [L4]. The publisher name must match between manifest and Marketplace listing (1.3.4) [L4]. The page does not say the offer must be transactable; a "Contact me" listing would satisfy the wording read here (**unconfirmed** with Microsoft). The older WDK page calls "Contact me" "a popular listing type" for workloads [L6]. |
| **Everything else** | The list in `docs/WORKLOAD-FEASIBILITY.md` section 5, steps 6–13 (publisher verification, attestation, manifest links, validator, request) [S9][S19][S31]. |
| **Review times** | **Not documented.** No Fabric page read gives a time for the publishing request, the validation feedback or the GA request. Marketplace offer certification has no overall time either; only sub-steps are timed (e.g. "Offer validation (<30 min)" for SaaS) [L23]. |
| **Trials** | Microsoft "expect[s] our partners to provide an out of the box trial experience for users within Fabric", available "without any deployment steps or communication with the workload provider"; the partner defines and enforces the limits in its own backend; trials are not bound to Fabric trials [L6]. This is on the WDK page; the toolkit requirement page read here does not mention trials (n153 listed "trial and monetisation experiences" as optional; that line could not be found again in [L4] at this commit, so treat it as **unconfirmed**). |

## 2. Getting paid

### 2a. Who can be the publisher

- Marketplace enrolment requires the **organisation** to be enrolled in the Microsoft AI Cloud Partner Program
  (MAICPP); "A Microsoft Entra work account alone doesn't meet this prerequisite." The prerequisites include the
  registered legal business name, "a business registration number", and business registration and domain ownership
  documents for verification [L21]. Verification checks the business registration, that the primary contact is an
  employee (with domain documents) and an identity document; "in most cases, the process takes three to five business
  days" [L22].
- An older page (ms.date 2024-05-23) shows an "Account type (Company or Individual)" on the developer account [L19].
  The current enrolment page describes only the business path [L21]. Whether an individual can still enrol for
  Marketplace is **unconfirmed**; for us it does not matter, because the publisher is Kruse Consulting AB.
- **What the repository records:** the MCP Entra app "Krusgraph" was made a verified publisher on 30 October 2026,
  "linked to Partner Center, publisher display name Kruse Consulting AB", publisher domain krusgraph.com
  (`docs/SCOPES.md`). Publisher verification needs a verified partner account [S26], so an MAICPP account for the
  company exists and passed verification. Whether it is enrolled in the **Commercial Marketplace** program, and whether
  its payout and tax profiles exist, is not recorded here: the founder checks under Account settings → Programs.
- The Entra tenant that holds `krusgraph.com` is the one the workload must be published from (the frontend must be a
  subdomain of a domain verified in the publishing tenant [L3]). Whether that is the same tenant as the Partner Center
  account is for the founder to confirm.

### 2b. The offer: a transactable SaaS offer

| Topic | What Microsoft documents |
| --- | --- |
| Listing options | "Contact me", "Free trial" (redirect, publisher runs the trial and the move to paid outside Marketplace), "Get it now (Free)", and "Sell through Microsoft" (transactable). The listing option of a transactable offer "can't [be] change[d] once your offer is published" [L9]. |
| Pricing models | Flat rate or per user; "All plans in the same offer must use the same pricing model" and it cannot be changed after publishing [L11]. Contract terms of one month, one, two or three years (SaaS also up to 5 years), billed monthly, annually or upfront [L10]. Per-user plans can set minimum and maximum users [L11]. |
| Metered (usage) | Custom meter dimensions are available **only on flat-rate plans**, at most 30 per offer, each with a price per unit and a quantity included in the base; the publisher sends only usage above the base [L10][L11][L12]. The Marketplace metering service accepts one event per resource, dimension and hour, no older than 24 hours [L13]. |
| Store service fee | "Microsoft charges a 3% standard store service fee"; example: customer billed USD 100.00, publisher paid USD 97.00. A 50% discount on the fee is possible for private-offer customer renewals [L10]. Our Azure hosting is billed to us, not to the customer [L9]. |
| Technical requirements | Entra ID single sign-on (and Microsoft accounts) on our site; a **landing page**; the **SaaS fulfilment APIs** (resolve the purchase token, activate); a **connection webhook**; both "should be running 24/7"; "Critical API changes must be supported within 24 hours" [L9][L14]. With **auto activation** on a plan, billing starts at purchase and a Subscribe webhook replaces the resolve/activate calls [L9][L14][L17]. |
| Free trial | On transactable SaaS: 1 to 180 days per plan; converts to paid unless the customer cancels or turns off auto-renew; the trial must meet the same technical requirements [L9][L10][L11]. |
| Private plans | A plan can be private to specific tenant ids: up to 10 by hand, up to 20,000 by CSV; a private plan can later go public, not the reverse [L11]. |
| Private offers | Customer-specific prices, terms and durations, sent to the customer's Azure billing account; "generally available within 15 minutes", private plans "up to 48 hours"; single-click purchase for eligible SaaS offers on MCA or EA billing accounts [L24]. Microsoft's own advice: use private offers, not the preview audience, to show an offer to people outside your organisation [L23]. |
| Testing | Keep a separate DEV offer; test in preview with nominal amounts; the publisher pays test invoices; purchases cancelled within 72 hours are refunded on the next invoice; do not press "Go live" on the DEV offer [L9][L11]. |
| Legal | Microsoft's Standard Contract (with up to 10 custom amendments) or our own terms, not both [L9]. Microsoft acts as agent; the publisher remains "the seller, provider, distributor, and licensor" [L10]. |

### 2c. Payouts, payout account and tax

- **Who pays:** "Payments to publishers on global Microsoft Marketplace sales are made by Microsoft Corporation", a US
  entity [L18].
- **When:** "In general, payments happen monthly." EA customers: payout in the next cycle, often before Microsoft has
  collected, e.g. an order in month 1 is paid out in month 2, no later than the 15th. MCA/CSP customers: payout after
  Microsoft collects; Microsoft's example shows an order on 1 January paid out between 8 and 14 February [L18]. If a
  customer never pays, Microsoft recovers the amount from later payouts or invoices the publisher [L18].
- **Profiles:** a transactable offer needs a payout account and a tax profile [L10]. "A Tax profile needs to be
  submitted first before a Payout profile can be created. A Tax profile submission can take up to 48 hours to
  validate." The bank account "must be in the same country or region where you registered your Partner Center
  account" [L19]. Every publisher fills in US tax forms (W-8 outside the US); the default US withholding for most
  non-US developers is 30% and applies only to sales into the US; a treaty claim on the W-8BEN can lower it [L19].
  Whether a company files the W-8BEN or the W-8BEN-E is not stated on the page read; **unconfirmed**, ask a tax adviser.
- **VAT:** Sweden is on Microsoft's list of **Microsoft-managed** countries, where Microsoft calculates, collects and
  remits certain transaction taxes and deducts them before payout; Microsoft "strongly recommends" publishers check with
  their own tax advisers [L20].

### 2d. Azure benefit eligibility (MACC)

- A customer's Microsoft Azure Consumption Commitment counts 100% of the pre-tax price of an "Azure benefit eligible"
  offer, when bought in the Azure portal with a subscription under the customer's agreement (not by card in the web
  store) [L26].
- For an offer to be enrolled: it "must meet all Azure IP Co-sell eligibility requirements"; then "within 1 week".
  Free and BYOL offers do not qualify [L25].
- Azure IP co-sell eligible needs co-sell-ready status plus: **USD 100,000** of Azure consumed revenue over a trailing
  12 months or USD 100,000 cumulative Marketplace billed revenue for the offer (credits do not count); a technical
  validation that the solution is "primarily platformed on Microsoft Azure"; a reference architecture diagram; and a
  transactable listing [L27]. **This is out of reach in 2026** and is listed only so nobody promises it to a customer.

### 2e. How the item checks that a tenant has paid

**Microsoft documents no licence check for partner workloads.** The toolkit page lists "Subscription state: Track user
subscription status across sessions" and "Feature gating: Control access based on subscription level" as the
partner's work, and says the toolkit "does not provide additional tools for Azure Marketplace integration" [L5]. The WDK
page: "It's up to you as a partner to communicate the updated license status to your extension backend", via the
Marketplace landing page for a transactable offer or "a special dialog as part of the item flow" for your own licence
[L6]. Workload Hub shows "licensing information" for a workload [L7]; no page read describes Fabric billing a partner
workload against the customer's capacity (**none documented**).

What that means for us, all of it our own code:

1. **Landing page** (`https://<sub>.krusgraph.com/marketplace/landing?token=…`): Entra sign-in, then `resolve` the
   `x-ms-marketplace-token` to the subscription, which names the offer, plan, quantity and the beneficiary's and
   purchaser's `tenantId`; then `activate` (or nothing, with auto activation) [L15][L17].
2. **Webhook**: validate the Entra bearer token on each call, then record Subscribe, ChangePlan, ChangeQuantity,
   Renew, Suspend, Reinstate, Unsubscribe; ChangePlan and ChangeQuantity must be answered within 10 seconds [L16].
3. **Record per tenant**: the existing dormant entitlement check (`fabric_backend/entitlements.py`) already keys on the
   token's `tid` and can read an Azure Table; the webhook writes the row, the engine reads it.
4. **Gate in the engine API**: `/workload/v1/build` (real, not dry run) answers `kind: upgrade` for a tenant without an
   active subscription, as the MCP tools would with the flag on. Reading and dry runs stay free, which is also the
   in-Fabric trial Microsoft expects [L6] (the split in `docs/PRICING-NOTES.md`).
5. **Metering**, only if a metered dimension is chosen: hourly usage events to the metering service [L13], from the
   anonymous counts `fabric_backend/usage.py` already keeps, extended with the tenant id. That changes what the privacy
   policy must say (`docs/PRICING-NOTES.md`).

## 3. Partner programme benefits

The pages read disagree, because Microsoft is mid-way through a merger of its programmes:

- **Frontier Accelerate for Marketplace** "consolidates ISV Success, Marketplace Rewards, Azure IP co-sell, and
  Solutions Partner with certified software designations into one unified offering", planned GA **4 September 2026**
  [L30]. Eligibility: active MAICPP membership; a B2B solution, for repeatable sales, built on a Microsoft Cloud
  platform, with intent to publish to Marketplace; enrolment needs the company's **global admin** (personal accounts
  are not supported) and legal vetting. Joining the Marketplace program is not needed to enrol, only to publish [L30].
- **Two tiers** [L29][L30]: free, and Premium at a list price of **USD 1,550 a year**. Premium adds technical
  consultations, a named engagement manager, development sandboxes and tools, and "Azure dev/test credits — Build &
  Publish Internal-Use Rights (IUR): $30,000 (new Premium partners)". Free gives self-service enablement, App Advisor
  listing help, go-to-market benefits and Azure sponsorship as Marketplace milestones are reached, and co-sell
  participation when criteria are met.
- **Grow Azure sponsorship** (both tiers, milestone-based): grants of 100% discounted first-party Azure usage, e.g. to
  "offset the infrastructure costs of offering free trials" on our own tenant; not for CSP billing accounts [L30].
  The milestones and thresholds are in a "Tiers & Benefits Matrix" not read here (**unconfirmed**).
- **ISV Success** page (ms.date 2026-10-05) still describes the older 12-month package: Azure sponsorship of USD 5,000,
  Azure standard support, Visual Studio Enterprise, an M365 E5 developer subscription, GitHub Enterprise Cloud (new
  enterprises only) and consultations; renewal at USD 1,550 requires having published or upgraded an offer to
  transactable [L28]. New partners are sent to "Join Frontier Accelerate for Marketplace" from the same page [L28].
  Which package a partner enrolling in November 2026 receives is **unconfirmed**: the FAQ (ms.date 2026-11-03) is the
  newer page and says current ISV Success members move to Premium automatically [L30].
- **Marketplace Rewards** as a separate offering is folded into the "Grow" stage [L30]. Its old tier details were not
  read (**unconfirmed**).
- **Co-sell**: "co-sell ready" needs a live Marketplace offer, a complete business profile, sales contacts and a
  one-pager and pitch deck [L27]. Azure IP co-sell: see 2d. The FAQ calls its new co-sell criteria "emerging from a
  pilot" and subject to change [L30].

Nothing here costs money to look at; Premium is a purchase and is the founder's decision.

## 4. Plan to Tuesday 17 November 2026

### What can and cannot be done by 17 November

| Goal | By 17 Nov? | Why |
| --- | --- | --- |
| Item works in our own tenant through DevGateway | **Yes, likely** | Phase 1 code is in `workload/` (n166); needs the founder's laptop steps in `docs/WORKLOAD-DEV.md` and one live run. |
| Item uploaded as `Org.Krusgraph` in our own tenant | **Possible** | Needs the editor hosted on a `krusgraph.com` subdomain over HTTPS and the workload app's resource-id URI on the verified domain [L3]; one build round. |
| One or two pilot tenants | **Possible, with conditions** | Needs the permanent `Krusgraph.*` name (a decision that cannot be undone) [L1], hosted editor and engine, a multitenant app [L3], and each pilot admin turning on the "not validated by Microsoft" setting [L8]. No Microsoft review. |
| Pilots paying | **Only outside Marketplace** | A written pilot agreement and an invoice from Kruse Consulting AB (`docs/PILOT.md`). Getting paid by Microsoft needs a live transactable offer with landing page and webhook [L9]; certification time is not documented [L23]. |
| A private offer to a pilot through Marketplace | **Unlikely** | Needs the transactable offer published first [L24]; the integration (2e) is at least one build round; certification time unknown. |
| Workload Hub Preview listing | **No** | Needs a published Marketplace offer [L4], the attestation, the validator and Microsoft's review, whose time is not documented [L1]. |
| GA listing, MACC eligibility, IP co-sell | **No** | GA needs a second request [L1]; MACC needs IP co-sell, which needs USD 100,000 in revenue or Azure consumption [L25][L27]. |

### The shortest honest path

**Own tenant first, then one or two pilots by direct publishing, paid (if at all) by our own invoice; Marketplace
starts in parallel and lands after 17 November.**

### Founder's steps, in order

| # | When | Step | Source |
| --- | --- | --- | --- |
| 1 | Mon 9 Nov | Confirm in Partner Center: which tenant the account uses; Account settings → Programs shows Commercial Marketplace enrolled or not; tax and payout profiles present or not. | [L21][L19] |
| 2 | Mon 9 Nov | Confirm `krusgraph.com` is a verified domain in the tenant you will publish from; that is where the workload app and the uploads live. | [L3] |
| 3 | 9–10 Nov | Run phase 1 through DevGateway (`docs/WORKLOAD-DEV.md`). | [L7] |
| 4 | 9–10 Nov | If not enrolled: add the Commercial Marketplace program to the existing MAICPP account (publisher name and publisher id; accept the Publisher Agreement). Verification of any new checks "in most cases" 3–5 business days. | [L21][L22] |
| 5 | 9–11 Nov | Tax profile first (up to 48 hours to validate), then payout profile with a Swedish company bank account. | [L19] |
| 6 | by 11 Nov | **Decide the permanent workload name** (`Krusgraph.<Workload>`, ≤ 32 characters after the dot) and the public publisher name; they must match the Marketplace listing. Only then upload a `Krusgraph.*` package. | [L1][L4] |
| 7 | by 12 Nov | Pick one or two pilot organisations with a Fabric capacity; get their tenant ids; send their admins the two tenant settings and a note on what data reaches us (`docs/TRUST.md`). | [L8] |
| 8 | 13–16 Nov | Upload, confirm the name, publish to the selected tenants; the pilots' admins consent to the app. | [L1] |
| 9 | after | Create the DEV and PROD SaaS offers; choose pricing model (cannot change later); publish; send private offers to pilots. | [L9][L11][L24] |
| 10 | after | Enrol in Frontier Accelerate for Marketplace (free tier, or Premium if the USD 1,550 and its credits are worth it). | [L30] |
| 11 | after | Workload Hub Preview request, as in `docs/WORKLOAD-FEASIBILITY.md` section 5. | [L1][L4] |

### Build rounds

**By 17 November**

| Round | What | Done when |
| --- | --- | --- |
| R1 Hosting | Production build of the editor; host it on a subdomain, e.g. `fabric.krusgraph.com` (frontend at most one segment below the verified domain [L3]); the engine API on the same scheme; CORS and CSP for Fabric; the workload app's Application ID URI in the resource-id form; manifest endpoints from `.env`. Deployment stays the maintainer's (`CONTRIBUTING.md`). | `Org.Krusgraph` package uploads and opens in our tenant from the hosted URL. |
| R2 Cross-tenant | Package as `Krusgraph.<Workload>` (only after step 6); multitenant workload app; admin-consent page and a one-page pilot admin guide; per-tenant limits already in `limits.py` checked for the workload routes. | A second tenant (a pilot, or a free test tenant of the founder) creates a Model item. |

**After 17 November**

| Round | What |
| --- | --- |
| R3 Marketplace | Landing page (Entra sign-in, resolve, activate or auto activation) and webhook (token validation, all actions, 10-second answers) [L15][L16][L17]; write the tenant's subscription to the entitlement table; turn the gate on for `/workload/v1/build`. Test against the DEV offer in preview only [L9]. |
| R4 Listing | Manifest license URL pointing to the live offer; terms, privacy, support and help pages; attestation draft; validator run [L4][S9][S31]. |
| R5 Metering (only if chosen) | Hourly usage events per tenant and dimension [L13]; privacy policy update first. |

### Decisions that are the founder's alone

- The permanent workload name, and the public publisher name (must match the listing) [L1][L4].
- Pricing model, flat rate or per user, and whether to add meters (flat rate only) [L11]; it cannot be changed after
  publishing.
- Standard Contract or own terms [L9].
- Whether to buy Frontier Accelerate Premium [L30].
- Who the pilots are, and whether they pay before Marketplace is ready.

## Sources

All read on 8 November 2026. "Learn commit" is the `git_commit_id` the Learn page reports; for Partner Center pages its
source is the private repository `MicrosoftDocs/partner-center-pr` (not reachable). Fabric pages were also read in
`MicrosoftDocs/fabric-docs` at `caec836`. `[Sn]` numbers refer to the sources of `docs/WORKLOAD-FEASIBILITY.md`.

| # | Title (`ms.date`) | URL | Learn commit / src |
| --- | --- | --- | --- |
| L1 | Publishing Overview (2026-04-08) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-overview | `80a24c9`; fabric-docs docs/extensibility-toolkit/publishing-overview.md |
| L2 | Workload Manifest (2025-12-15) | https://learn.microsoft.com/fabric/extensibility-toolkit/manifest-workload | fabric-docs …/manifest-workload.md |
| L3 | General Publishing Requirements (2025-12-15) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-general | `5156dc5`; …/publishing-requirements-general.md |
| L4 | Validation guidelines and requirements for workloads (2026-02-24) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-workload | `5e656ad`; …/publishing-requirements-workload.md |
| L5 | How to monetize your workload (2025-12-15) | https://learn.microsoft.com/fabric/extensibility-toolkit/how-to-monetize-workload | `5156dc5`; …/how-to-monetize-workload.md |
| L6 | Fabric Workload Development Kit monetization (2026-04-29) | https://learn.microsoft.com/fabric/workload-development-kit/monetization | fabric-docs docs/workload-development-kit/monetization.md |
| L7 | How to publish and manage a workload (2025-11-18) | https://learn.microsoft.com/fabric/extensibility-toolkit/tutorial-publish-workload | `80a24c9`; …/tutorial-publish-workload.md |
| L8 | Tenant settings for additional workloads (2026-04-08) | https://learn.microsoft.com/fabric/admin/service-admin-portal-additional-workloads | `80a24c9` |
| L9 | Plan a SaaS offer for Microsoft Marketplace (2026-07-22) | https://learn.microsoft.com/partner-center/marketplace-offers/plan-saas-offer | `3d1a72a` |
| L10 | Microsoft Marketplace transact capabilities (2026-07-22) | https://learn.microsoft.com/partner-center/marketplace-offers/marketplace-commercial-transaction-capabilities-and-considerations | `3cb5dc9` |
| L11 | Create plans for a SaaS offer (2026-07-22) | https://learn.microsoft.com/partner-center/marketplace-offers/create-new-saas-offer-plans | `3d1a72a` |
| L12 | Metered billing for SaaS offers (2026-07-22) | https://learn.microsoft.com/partner-center/marketplace-offers/saas-metered-billing | `3d1a72a` |
| L13 | Metering service APIs (2025-04-21) | https://learn.microsoft.com/partner-center/marketplace-offers/marketplace-metering-service-apis | `651727a` |
| L14 | SaaS fulfillment APIs (2026-07-22) | https://learn.microsoft.com/partner-center/marketplace-offers/pc-saas-fulfillment-apis | `3d1a72a` |
| L15 | SaaS fulfillment Subscription APIs v2 (2026-07-22) | https://learn.microsoft.com/partner-center/marketplace-offers/pc-saas-fulfillment-subscription-api | `3d1a72a` |
| L16 | Implementing a webhook on the SaaS service (2026-04-29) | https://learn.microsoft.com/partner-center/marketplace-offers/pc-saas-fulfillment-webhook | `3d1a72a` |
| L17 | Build the landing page for your transactable SaaS offer (2026-04-29) | https://learn.microsoft.com/partner-center/marketplace-offers/azure-ad-transactable-saas-landing-page | `59e2bde` |
| L18 | Payout schedules and processes (2025-10-22) | https://learn.microsoft.com/partner-center/marketplace-offers/payout-policy-details | `cc54314` |
| L19 | Manage a Microsoft Marketplace account in Partner Center (2024-05-23) | https://learn.microsoft.com/partner-center/account-settings/manage-account | `60ce816` |
| L20 | Tax Responsibilities for Microsoft Marketplace (2026-11-04) | https://learn.microsoft.com/partner-center/marketplace-offers/tax-details-marketplace | `1ab2881` |
| L21 | Enroll in Microsoft Marketplace or M365 Copilot in Partner Center (2026-10-27) | https://learn.microsoft.com/partner-center/account-settings/create-account | `c3d2002` |
| L22 | Understand the verification process in Partner Center (2026-07-27) | https://learn.microsoft.com/partner-center/enroll/understand-the-verification-process | `c161d06` |
| L23 | How to review and publish an offer (2025-01-08) | https://learn.microsoft.com/partner-center/marketplace-offers/review-publish-offer | `4064024` |
| L24 | ISV-to-customer private offers (2026-10-27) | https://learn.microsoft.com/partner-center/marketplace-offers/isv-customer | `f4f1005` |
| L25 | Azure Consumption Commitment enrollment (2025-01-21) | https://learn.microsoft.com/partner-center/marketplace-offers/azure-consumption-commitment-enrollment | `4064024` |
| L26 | Azure Consumption Commitment Benefit, customer docs (2024-10-27) | https://learn.microsoft.com/marketplace/azure-consumption-commitment-benefit | `1f72dd3` |
| L27 | Co-sell requirements (2026-10-05) | https://learn.microsoft.com/partner-center/referrals/co-sell-requirements | `6a017af` |
| L28 | Build and Publish with ISV Success (2026-10-05) | https://learn.microsoft.com/partner-center/membership/isv-success | `a3e1e78` |
| L29 | Frontier Accelerate for Marketplace benefits (2026-09-16) | https://learn.microsoft.com/partner-center/frontier-accelerate-marketplace/benefits | `5f69ced` |
| L30 | Frontier Accelerate for Marketplace FAQ (2026-11-03) | https://learn.microsoft.com/partner-center/frontier-accelerate-marketplace/faq | `c697d0b` |

Also opened and not cited for a fact: the Partner Center November 2026 announcements (2026-11-06; private offers can
now be accepted and purchased in one step, and the open-source SaaS accelerator ends .NET 8 support on 10 November
2026), "Benefits by program and offer" and "Azure Benefits" (partner Azure credits; not needed for the answers above).

Could not be reached or read: `MicrosoftDocs/partner-center-pr` (private); `partner.microsoft.com`,
`azuremarketplace.microsoft.com`, `appsource.microsoft.com` (no connection from this environment); the Frontier
Accelerate "Tiers & Benefits Matrix" and "Benefits guide"; the Microsoft Publisher Agreement itself.
