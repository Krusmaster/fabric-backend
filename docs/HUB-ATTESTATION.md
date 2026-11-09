# Vendor attestation: Krusgraph (draft)

**Draft, round n178, 9 November 2026. Not signed, not hosted, not sent to Microsoft.** It follows Microsoft's
"Vendor Attestation Document Template" [H1] section by section and heading by heading, and is filled only with what this
repository can show. Every point the repository cannot prove says **founder to confirm** or **not met yet**. Nothing here
is a compliance or certification claim: Krusgraph holds no certification, and this document claims none.

How to use it (`docs/HUB-READINESS.md`, steps 6 and 7): the founder corrects every marked point, signs Section II, sends
Sections I to III to Microsoft with the publishing request, and hosts **Section III only** at a public HTTPS URL [H1]
(as a web page or a PDF [H2, 1.4.1]); that URL goes into the manifest field
`product.productDetail.supportLink.certification.url`. Microsoft's validator downloads the document from that URL and
searches it for the terms of each requirement, and for the workload's name [H8]; `tools/hub_readiness.py` checks this
draft for the same terms on every push (`.github/workflows/hub-readiness.yml`). Remove this paragraph and the
evidence column before hosting.

The template says the vendor must notify Microsoft before releasing a change that materially affects the attestation,
especially on security, compliance, privacy, or the design guidelines [H1].

---

## Section I

### ISV Information

#### Vendor Information

| Description | Value | Required or Optional |
| --- | --- | --- |
| Company Name: | Kruse Consulting AB (the publisher display name recorded for the verified Entra app in `docs/SCOPES.md`; **founder to confirm** the legal name as registered) | (Required) |
| Company Website: | https://krusgraph.com | (Required) |
| Address: | **founder to confirm** | (Required) |
| City: | **founder to confirm** (the site's /it page says "Based in Uppsala, Sweden, and Bern, Switzerland") | (Required) |
| State: | **founder to confirm** (Sweden has no states; "Uppsala län" or "n/a") | (Required) |
| Postal Code: | **founder to confirm** | (Required) |
| County: | **founder to confirm** (the template's word; probably "Country": Sweden) | (Required) |
| Phone: | **founder to confirm** or leave empty | (Optional) |

#### Primary Contact

| Description | Value | Required or Optional |
| --- | --- | --- |
| Name: | **founder to confirm** | (Required) |
| Title: | **founder to confirm** | (Required) |
| Email: | hello@krusgraph.com (the contact in `CONTRIBUTING.md` and `docs/SECURITY.md`; **founder to confirm** it is the alias Microsoft should use) | (Required / Email Alias OK) |

## Section II

### Attestation

To: Microsoft Corporation

Subject: Vendor Self-Attestation for Compliance with Microsoft Workload Development Requirements

We, the undersigned, Kruse Consulting AB, hereby confirm and attest that we have reviewed, understood, and complied with
all applicable requirements as outlined in the Microsoft Extensibility toolkit documentation, specifically the Publish
Workload Requirements.

**Not signed.** This sentence is the template's [H1]. It cannot be signed truthfully while the points marked "not met
yet" below remain (`docs/HUB-READINESS.md` lists them). Signature, name, title and date: **founder, after the gaps are
closed**.

---

## Section III

### Publish Workload Requirements Attestation Checklist

We, the vendor, Kruse Consulting AB, confirm and attest to reviewing, meeting, and complying with the requirements
outlined in the Microsoft Fabric Extensibility Toolkit specifically the Publish Workload Requirements

The following sections documents details, exceptions, or variances regarding the attestation of adherence to the
Publish Workload Requirements.

#### Workload Information

| Description | Value | Required or Optional |
| --- | --- | --- |
| Workload Version: | **founder to confirm** at submission: the package version uploaded (`workload/scripts/build-package` numbers it `1.0.<commits>`; `Org.Krusgraph` 1.0.877 was uploaded on 8 November 2026, `docs/WORKLOAD-DEV.md`) | (Required) |
| Workload Name: | Krusgraph.Modeler (**proposed, not registered**: the name is reserved for good at its first upload [H6]; **founder to confirm** before any upload. Today the workload runs only as `Org.Krusgraph` in the founder's tenant) | (Required) |
| Release Date: | **founder to confirm** | (Required / Email Alias OK) |

### Business Requirements

#### Value To Customers

The workload provides the following value to customers –

> Krusgraph reads the table and column names of a lakehouse and proposes keys and relationships, each with the rule
> that found it. The person reviews them (accept or reject each one, or all that passed), can check them against the
> rows (counts of orphans, duplicates and empty values; never a row value), and then builds from what was accepted, dry
> run first: a silver notebook, gold views, a pipeline, a semantic model, a report, an API for GraphQL, an ontology and
> a data agent, optionally bundled as one data product, with the data flow drawn.

Evidence: `workload/Workload/Manifest/assets/locales/en-US/translations.json`, `CHANGELOG.md` (n173, n174),
`docs/WORKLOAD-DEV.md` ("What the editor does since n174"). Note: the Workload Hub description in the translations file
still says semantic models, reports and pipelines "come later"; it must be updated before listing
(`docs/HUB-READINESS.md`, finding F7).

#### Trial

We provide an easy and fast trial experience. The trial is available to the customer without waiting time (less than 5
seconds), and provides a free and easy way to explore the offered workload for a limited time in accordance with
Microsoft guidelines for Trials

[ ] Yes

[ ] No

> **Founder to confirm.** What the code does: reading, the review, the check against the rows and every dry run are
> free; only a creating call (`/workload/v1/build` with `dry_run=false`) is refused for a tenant without an active
> Marketplace subscription, and only when `KRUSGRAPH_ENTITLEMENTS=1` (`docs/MARKETPLACE-SETUP.md`, section 1, step 6;
> `fabric_backend/entitlements.py`). That is a free tier, not a time-limited trial. Whether it counts as Microsoft's
> trial, and the under-5-seconds start, is **not measured**.

#### Monetization

The workload is available on the marketplace for the customer to procure with or without a trial in accordance with the
monetization guidelines

[ ] Yes

[x] No

> **Not met yet.** No live Microsoft Marketplace offer exists for Krusgraph. The landing page and webhook are built and
> off by default (`fabric_backend/marketplace.py`, `docs/MARKETPLACE-SETUP.md`); only a DEV offer is planned for
> testing, which must never go live. The production SaaS offer's URL goes here and into the manifest's license link.

### Technical Requirements

#### Microsoft Entra Access

The workloads use Microsoft Entra authentication and authorization.

[x] No other authentication and authorization mechanisms are used

[ ] Different authentication and authorization mechanisms are used for stored data In Fabric

> The editor obtains every token from the Fabric host through the Fabric Workload Client SDK
> (`workloadClient.auth.acquireFrontendAccessToken`, `workload/Workload/app/items/ModelItem/engineClient.ts`,
> `app/clients/FabricAuthenticationService.ts`); it holds no other sign-in library and no password. The engine API
> (`fabric_backend/workload_api.py`) accepts only version 2 Entra access tokens for the workload app's own audience
> (`fabric_backend/entra.py`, `WorkloadConfig`; `tests/test_workload_api.py`) and calls Fabric REST and the SQL analytics
> endpoint with the on-behalf-of flow, so every call runs with the signed-in user's own Fabric permissions.
>
> Entra app: today "Krusgraph workload (dev)", application id `853a0cf0-7d35-42b7-b384-26178755a72a`, in tenant
> `d2fcf72a-9b80-451d-868b-8d47af30d8ae` (`docs/WORKLOAD-DEV.md`). **Founder to confirm** the app used for the listing:
> its name must match the workload and its publisher must be verified [H2, 2.1.1, 4.1.4]; the "(dev)" app does not.
>
> Delegated permissions the workload app uses (`docs/WORKLOAD-DEV.md`, sections 3 and Hosted step 7): Power BI Service
> (Fabric) `Fabric.Extend` (mandatory [H2, 2.1.2]), `Workspace.Read.All`, `Lakehouse.Read.All`, and for building either
> `Item.ReadWrite.All` or the narrower `Notebook.ReadWrite.All`, `DataPipeline.ReadWrite.All`,
> `SemanticModel.ReadWrite.All`, `Report.ReadWrite.All`, `GraphQLApi.ReadWrite.All`, `DataAgent.ReadWrite.All`; Azure
> SQL Database `user_impersonation`. No Execute permission is requested or used. Endpoint: the engine at
> `https://workload.krusgraph.com/workload/v1/*`, scope `<Application ID URI>/user_impersonation`.

#### One Lake

Workloads integrate with One Lake to store data in the standard formats supported by the Fabric platform so that other
services can take advantage of it.

[ ] All data and metadata is stored in One Lake or Fabric Data Stores

[x] Not all data and metadata is stored in One Lake or Fabric Data Stores

> The item's state is its Fabric item definition (four JSON parts: `review.json`, `source.json`, `outputs.json`,
> `item.json`; `ModelItemDefinition.ts`), and everything it builds is an ordinary Fabric item in the customer's
> workspace (notebook, materialized lake views, pipeline, semantic model, report, API for GraphQL, ontology, data agent).
> The workload writes nothing to OneLake itself. Outside Fabric, Krusgraph keeps: usage records and technical logs without
> content (no table contents, query text, tokens or headers) in Azure Log Analytics, Sweden Central, for the configured
> retention (`docs/TRUST.md`); and, when Marketplace is switched on, one row per subscribing tenant (tenant id and the
> subscription's offer, plan, quantity and status) in Azure Table Storage (`docs/MARKETPLACE-SETUP.md`, "What the store
> keeps"). Table and column names pass through the service's memory during a call and are not saved.

#### Microsoft Entra Conditional Access

Enterprise customers require centralized control and management of the identities and credentials used to access their
resources and data and via Microsoft Entra to further secure their environment via conditional access.

[ ] The service works in its entirety with even if customers enable this functionality

[ ] The service works in with limitations if customers enable this functionality

[ ] The service doesn't work Microsoft Entra Conditional Access

> **Not tested; founder to confirm.** Tokens come only from the Fabric host, and the on-behalf-of exchange is Entra's own,
> so a Conditional Access policy applies at sign-in. Microsoft's SDK page says "full consent prompting and conditional
> access handling are not yet available" in `acquireFrontendAccessToken` (`docs/WORKLOAD-FEASIBILITY.md`, [S5]); what the
> editor shows when the on-behalf-of exchange returns a claims challenge is not tested. Test with a Conditional Access
> policy in the founder's tenant before ticking a box.

#### Admin REST API

Admin REST APIs are an integral part of Fabric admin and governance process. These APIs help Fabric admins in
discovering workspaces and items, and enforcing governance such as performing access reviews, etc. Basic functionality is
supported as part of the Workload Development Kit and doesn't need any work from Partners.

[ ] Microsoft Fabric Admin APIs are being used (/admin/*)

[x] No Microsoft Fabric Admin APIs are being used

> The workload's engine routes (`fabric_backend/workload_api.py`) call no `/admin/*` endpoint. (The separate Krusgraph
> MCP server has a tagging tool that uses the admin tags API; the workload does not call it.)

#### Customer Facing Monitoring & Diagnostic

Health and telemetry data needs to be stored for a minimum for 30 days including activity ID for customer support
purposes, including Trials.

[ ] Minimum 30 days requirement is adhered to

[ ] Vendor stores the data for __ days beyond the minimum requirement

> **Founder to confirm.** Retention is a deployment setting, `log_retention_days`, 30 to 730 days, 30 proposed; it is 0
> while console logs go nowhere (`deploy/azure_containerapp.py`, `docs/TRUST.md`). The /it page shows the live value.
> **Not met yet:** the logs carry no Fabric activity id; a support case cannot be matched to a log line by the id the
> customer sees (`docs/HUB-READINESS.md`, finding F9). Diagnostic for the customer: each error in the editor names its
> kind (`sign_in`, `consent`, `no_access`, `already_exists` and others) and the step that fixes it.

#### B2B

The implementation of the workload is in line with Microsoft Fabric's sharing strategy focused on allowing customers to
collaborate with their business partners, customers, vendors, subsidiaries, etc. It also means users from other tenants
can potentially be granted access to items partners are creating.

[ ] Cross tenant B2B collaboration supported

[ ] Workload Item Access only within the tenant

> **Not tested; founder to confirm** (optional at Preview [H2, 2.5]). The engine can restrict tenants
> (`KRUSGRAPH_WORKLOAD_ALLOWED_TENANTS`); how a B2B guest's token looks to the engine has not been tried.

#### Business Continuity and disaster recovery

The vendor has a comprehensive Business Continuity and Disaster Recovery (BCDR) plans designed to tackle unplanned
disasters and recovery steps.

> **Not met yet** (optional at Preview [H2, 2.6]). One Azure Container App in Sweden Central; the image is rebuilt from
> this public repository with `deploy/krusgraph.sh` (`docs/OPERATIONS.md`). The workload keeps no customer state of its
> own (the item's state is in Fabric), so a rebuild in another region restores the service; no written plan, recovery
> time or recovery point exists.

#### Performance

The Workload implementation takes measures to test and track performance of their Items

[ ] Performance Metrics on workload performance are available via the monitoring hub

[ ] Workload includes a separate monitoring UI to test and track performance

[x] Performance tracking isn't currently available to the end user however vendor support personnel can monitor, test,
track performance via their internal instrumentation and monitoring systems

> The usage records (`fabric_backend/usage.py`) and the container's metrics. **Not measured:** the editor's load time in
> the Fabric frame (Microsoft's general requirement: under 3 seconds [H7]).

#### Presence

To ensure that customer expectations independent of their home or capacity region are met, vendors need to align with
fabric regions and clouds. Availability in certain restrictions also impacts your Data Residency commitments.

[x] Service availability and colocation/alignment in the following fabric regions

> Microsoft Azure, Sweden Central only (`deploy/krusgraph.example.json`, `docs/TRUST.md`); Fabric public cloud only
> (`<Cloud>Public</Cloud>` in `workload/Workload/Manifest/WorkloadManifest.xml`). Customers in every Fabric region reach the
> same service in Sweden Central.

[ ] All or part of the service doesn't reside in Azure

> Everything runs in Azure.

#### Public APIs

Fabric Public APIs are the backbone of automation, enabling seamless communication and integration for both customers
and partners within the Fabric ecosystem. Fabric Public API empowers users to build innovative solutions, enhance
scalability, and streamline workflows.

[X] The workload uses Fabric Public APIs

> Fabric REST (`https://api.fabric.microsoft.com/v1`) for items and definitions, and the lakehouse's SQL analytics
> endpoint for column metadata and counts, on the user's behalf.

### Design / UX Requirements

#### Common UX

The workload and all item types the partner provides as part of it comply with the Fabric UX guidelines.

[ ] The following variance and/or exceptions have been granted by Microsoft

> None requested or granted. The editor is built on Microsoft's starter kit (Fluent UI, its `ItemEditor` and `Ribbon`
> components): one sticky ribbon with Home as the first tab (`ModelItemEditor.tsx`). The mascots (Onto, Thinker,
> Builder) and the map are our own drawings inside the canvas; whether they fit the guidelines is for Microsoft's
> review. **Founder to confirm** after the validator's manual UX tests.

#### Item Creation Experience

The item creation experience is in accordance with the Fabric UX System.

[x] Yes

[ ] No

> Fabric's own create dialog (`createItemDialogConfig` in `Product.json` and `ModelItem.json`); available in Home, the
> Creation Hub and the workspace's + New (`availableIn`). Seen working in Fabric on 8 November 2026 (founder's run,
> `CHANGELOG.md` n173). **Not tested:** creation under `*.powerbi.com` (only `app.fabric.microsoft.com` was used).

#### Monitoring Hub All Long running operations need to integrate with Fabric Monitoring Hub

[ ] Yes

[x] No

> `supportedInMonitoringHub: false`. Builds run during the call and return; the item starts no job (no notebook or
> pipeline is run or scheduled).

#### Trial Experience

The workload provides a Trial Experience for users as outlined in the design guidelines

[ ] Trial Supported

[ ] Trial Not Supported

> **Founder to confirm**: see Trial above.

#### Monetization Experience

The monetization experience is in line with the design guidelines provided

[ ] The monetization experience is integrated with the market place and compliant with the guidelines

[ ] Bring Your Own License (BYOL)

[ ] Free / Freemium

[ ] Other

> **Founder to confirm.** Built: a refused build answers HTTP 402 with a link to the offer, shown in the editor's error
> bar (`docs/MARKETPLACE-SETUP.md`). Off until the production offer is live. Terms: https://krusgraph.com/terms ("Preview
> terms" today).

#### Accessibility

The user experience is in compliance with the Fabric UX design guidelines for Accessibility

[ ] The user experience is compliant with the guidelines

[x] The following limitations exist

> **No accessibility audit has been done.** What exists: Fluent UI components; the map has a **List** view with the same
> keys and relationships as rows "for the keyboard and screen readers"; each box of the data flow opens with a click,
> Enter or Space; the mascots can be switched off and their sentences are then plain text (`docs/WORKLOAD-DEV.md`, n173
> and n174). Not checked: contrast in Fabric's themes, screen-reader names on the map and the flow, focus order.

#### World Readiness / Internationalization

English is supported as the default language. Localization through optional, should be considered.

[x] English is the only supported language

[ ] The following languages are supported

> `workload/Workload/Manifest/assets/locales/en-US/` is the only locale.

#### Item Settings

Item settings are implemented as a part of the ribbon as outlined in the UX guidelines

[ ] Yes

[x] No

> Optional [H3, 7.6]; none implemented.

#### Samples

Samples are optionally provided that preconfigure items of their type to help customers get started more easily.

[x] Samples not provided

[ ] Samples for preconfiguration of items provided

> A synthetic shop dataset can be seeded with a notebook (`fabric_backend/seed.py`, `docs/WORKLOAD-DEV.md`, section 2); it
> is not offered inside the workload.

#### Custom Actions

Custom actions can be optionally provided as a part of the item editor.

[x] Custom Actions aren't implemented

[ ] Custom Actions implemented as part of Workload

> `contextMenuItems: []` and `customActions: []` in the manifests.

#### Workspace settings

Workspace settings provide a way that workloads can be configured on a workspace level.

[ ] Supported

[X] Not Supported

#### Global Search

Searching for items in Fabric is supported through the top search bar.

[ ] Supported

[X] Not supported

> As the template marks it [H1]; not tested for Krusgraph Model items.

### Security / Compliance Requirements

#### Security general

Protection of customer data and metadata is of paramount importance. Workloads must go through a security review and
assessment. Vendor attests that the security review and assessment was completed and will be periodically performed as
enhancements and changes are made. Security issues discovered which could have a detrimental impact on the customer
should be addressed promptly and customers notified where applicable.

> **Not met yet: no independent security assessment or penetration test has been done.** What exists, all in the public
> repository: `docs/SECURITY.md` (reporting, what holds by default); `docs/ISO27001-SELF-ASSESSMENT.md` (a self-assessment,
> not a certification); dependency audit and SBOM on every push (`.github/workflows/audit.yml`, `sbom.yml`); the
> workload host's headers (Content-Security-Policy with `frame-ancestors https://*.fabric.microsoft.com
> https://*.powerbi.com`, CORS only for those origins, HSTS, no cookie; `fabric_backend/workload_host.py`,
> `tests/test_workload_host.py`); token validation tests (`tests/test_workload_api.py`). **Founder to confirm** who performs
> the assessment and when.

#### Privacy

Partners that build workloads also have a responsibility to protect that data when they access it. Every workload goes
through a privacy assessment and a privacy review. Vendor attests that privacy review was completed and is periodically
performed as enhancements and changes are made.

**Extra Requirements:

[x] Publisher attests that only essential HTTP-only cookies are used by the Workload and only after positively
authenticating the user.

> Stronger than required: the workload host sets **no cookie at all**; it strips `Set-Cookie` even from the engine's
> answers (`fabric_backend/workload_host.py`; `tests/test_workload_host.py`). (The Marketplace landing page on
> krusgraph.com, outside the workload, uses one short-lived HttpOnly first-party cookie during sign-in.)

[x] Publisher attests that it's not using or relying on third-party cookies as part of their solution.

[x] Publisher attests that's obtaining any Microsoft Entra token using the JavaScript APIs provided by the Fabric
Workload Client SDK

> `acquireFrontendAccessToken` only (see Microsoft Entra Access); no MSAL or other token library in
> `workload/Workload/app/`.
>
> Privacy policy: https://krusgraph.com/privacy (`fabric_backend/page_templates/PRIVACY.md`); a draft data processing
> agreement: `docs/DPA-DRAFT.md`. **Not met yet: no independent privacy review has been done; founder to confirm.**

#### Data Residency

Microsoft Fabric is making an Enterprise Promise around data not leaving the geography of the tenant for stored data
and data in transit. As a workload in Fabric directly and users need to be aware what your commitments to Data Residency
are. Define what your commitments are to the Data Residency of customer data.

> - The service runs in Microsoft Azure, **Sweden Central** (EU), only.
> - **What reaches it from the customer's tenant:** lakehouse table and column names, data types, constraint metadata,
>   and counts (rows, orphans, duplicates, empty values); the user's token for the on-behalf-of exchange. **No row
>   values**: the review and the check read names and counts only (`fabric_backend/review.py`, `ModelItemDefinition.ts`,
>   `docs/TRUST.md`).
> - **What it stores:** none of the above. The item's state and everything it builds stay in the customer's own
>   workspace, in the customer's region. Logs without content and, with Marketplace, the tenant's subscription row stay
>   in Sweden Central (see One Lake).
> - **Consequence for a tenant outside the EU:** its metadata (names and counts) is processed in Sweden in transit.
>   Krusgraph has no other region today. Self-hosting in the customer's own Azure region is possible with the same script
>   (`docs/TRUST.md`), but the listed workload points to the hosted service.
> - Details: https://krusgraph.com/it and https://krusgraph.com/privacy. **Founder to confirm** the wording.

#### Compliance

The publisher attests to the following security, data, and compliance regulations and standards

> **None.** Krusgraph holds no certification or audit report (no ISO 27001, SOC 2, HIPAA or other). It is operated by
> Kruse Consulting AB in the EU under the GDPR; `docs/ISO27001-SELF-ASSESSMENT.md` is a self-assessment and claims no
> certification. Security, data and compliance information: https://krusgraph.com/it.

### Support

#### Live site

Partner workloads are an integral part of Fabric that requires that the Microsoft support teams are aware of how to
contact you in case customers are reaching out to us directly.

Microsoft direct vendor outreach:

| Contact Name/Team: | **founder to confirm** (Kruse Consulting AB, Krusgraph support) |
| --- | --- |
| Number | **founder to confirm** (optional) |
| Email alias | hello@krusgraph.com (**founder to confirm**) |
| Self Service portal | https://krusgraph.com/support |

> Optional at Preview, required at GA [H2, 5.1].

#### Supportability

Vendors are responsible for defining and documenting their support parameters (Service level agreement, contact
methods, ...). This information needs to be linked from the Workload page and should always be accessible to customers.
In addition, the Marketplace criteria, need to be taken into account for the listing of the SaaS offer.

[ ] Vendor attests that support information is published to the marketplace offering and available to user/customers
directly via the workload

> **Not met yet.** The workload page links help (https://krusgraph.com/support) and documentation; there is no SLA and no
> Marketplace offer yet. Optional at Preview, required at GA [H2, 5.2]; the help link and a support contact are required
> at Preview [H2, 5.2.1, 5.2.2].

#### Service Health and Availability

Vendors need to host a service health dashboard that shows their service health and availability to customers. This
information can be included on the Supportability page.

Service heath dashboard can be found here:

> **Not met yet** (optional [H2, 5.3]). The service answers `GET https://krusgraph.com/health`; no status page shows
> history or incidents.

### Fabric Features

#### Application Life Cycle Management (ALM)

Microsoft Fabric's lifecycle management tools enable efficient product development, continuous updates, fast releases,
and ongoing feature enhancements.

[ ] Supported

[X] Not Supported

> **Not tested; founder to confirm.** The item definition is designed for Git: four small JSON parts, each with a
> version field so an older definition restored from Git can be read and migrated, and no token or row value in them
> (`ModelItemDefinition.ts`). Whether Fabric Git integration and deployment pipelines carry a Krusgraph Model item has
> not been tried.

#### CI/CD (Continuous Integration / Continuous Deployment)

The workload supports CI/CD pipelines to enable automated deployment and integration workflows within Microsoft Fabric.

[ ] CI/CD is supported via the Fabric CICD manifest section

[x] CI/CD is not supported

> The manifest has no CICD section (optional [H2, 6.1.1]).

#### Item Definition Portability

Items can be exported with their full definition and restored in other workspaces, enabling lifecycle management and
cross-workspace deployment.

[ ] Items can be restored with their definition in other workspaces

[ ] Items cannot be restored in other workspaces

> **Not tested.** Limitation by design: `source.json` holds the source lakehouse's workspace id and item id, and
> `outputs.json` the ids of the items built; a copy in another workspace still points at the original lakehouse until
> the person chooses another one. No Variable Library support.

#### Private Links

In Fabric, you can configure and use an endpoint that allows your organization to access Fabric privately.

[ ] Supported

[X] Not Supported

> The editor and engine are on the public internet (workload.krusgraph.com).

#### Data Hub

The OneLake data hub makes it easy to find, explore, and use the Fabric data items in your organization that you have
access to. It provides information about the items and entry points for working with them. If you're implementing a
Data Item, show up in the Data Hub as well.

[ ] Supported

[X] Not Supported

> The Krusgraph Model is not a data item; the items it builds (semantic model, API for GraphQL and others) are Fabric's own
> and appear in the OneLake catalog as usual. **Founder to confirm**: the item manifest sets `supportedInDatahubL1: true`
> (the starter kit's value); whether that should stay is for a Workload round (finding F10).

#### Data Lineage

In modern business intelligence (BI) projects, understanding the flow of data from the data source to its destination
can be a challenge. The challenge is even bigger if you built advanced analytical projects spanning multiple data
sources, data items, and dependencies. Questions like "What happens if I change this data?" or "Why isn't this report up
to date?" can be hard to answer.

[ ] Supported

[X] Not Supported

> **Not met yet in Fabric's lineage view.** The item draws its own data flow (bronze tables → silver → gold views →
> what is built on them) and keeps the ids of what it built in `outputs.json`; the API for GraphQL names its source in
> its own definition. No Microsoft page read documents how a workload item declares lineage edges
> (`docs/WORKLOAD-FEASIBILITY.md`, "Lineage").

#### Sensitivity labels

Sensitivity labels from Microsoft Purview Information Protection on items can guard your sensitive content against
unauthorized data access and leakage. They're a key component in helping your organization meet its governance and
compliance requirements. Labeling your data correctly with sensitivity labels ensures that only authorized people can
access your data.

Extra requirements:

For partners that are using Export functionality within their Item they need to follow the guidelines.

[ ] Supported

[X] Not Supported

> The item exports no data (its **Copy** button copies generated code, never row values). Sensitivity Labels on the
> Krusgraph Model item and on the items it builds: not tested.

### Extra Notes

Use this section to provide any further explanations, references, or notes that may be relevant to your attestation:

> The engine is the same open-source code (MIT) as Krusgraph's MCP server, https://github.com/Krusmaster/fabric-backend.
> Every creating call is a dry run first and is never run on the user's behalf without the user pressing Create.

### References

> - Website and IT page: https://krusgraph.com, https://krusgraph.com/it
> - Documentation: https://krusgraph.com/docs
> - Support: https://krusgraph.com/support
> - Privacy policy: https://krusgraph.com/privacy
> - Terms: https://krusgraph.com/terms
> - Security reporting: `docs/SECURITY.md`
> - Source code: https://github.com/Krusmaster/fabric-backend
> - Marketplace offer: **not met yet**
> - Service health dashboard: **not met yet**

---

## Sources (remove before hosting)

Read on learn.microsoft.com and github.com on **9 November 2026**. "Learn commit" is the `git_commit_id` the page reports.

| # | Title (`ms.date`) | URL | Learn commit / source |
| --- | --- | --- | --- |
| H1 | Vendor Attestation Document Template (2026-02-24; "last updated" 2026-08-30) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-vendor-attestation-template | `e567e67` |
| H2 | Validation guidelines and requirements for workloads (2026-02-24) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-workload | `5e656ad` |
| H3 | Validation guidelines and requirements for items (2026-02-24) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-item | `bd2c301` |
| H6 | Publishing Overview (2026-04-08; "last updated" 2026-09-29) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-overview | `80a24c9` |
| H7 | General Publishing Requirements (2025-12-15) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-general | `5156dc5` |
| H8 | `microsoft/fabric-extensibility-toolkit-validator`: README.md, validator/README.md, specifications/testcases/*.json | https://github.com/microsoft/fabric-extensibility-toolkit-validator | commit `78e17c3` (15 December 2025); LICENSE MIT, read at that commit |

`[Sn]` refers to the sources of `docs/WORKLOAD-FEASIBILITY.md`. H4 and H5 are in `docs/HUB-READINESS.md`.
