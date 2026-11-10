# Vendor attestation: Krusgraph.Modeler

**Draft.** Not yet signed, sent to Microsoft or accepted by anyone. Every point that says **Not yet** or **To confirm** is open, and the page says so instead of claiming it. Kruse Consulting AB removes this paragraph when the document is final.

This page is Section III of Microsoft's "Fabric Extensibility toolkit vendor attestation template" for the Microsoft Fabric workload **Krusgraph.Modeler** (the item **Krusgraph Model**), filled in by its publisher, Kruse Consulting AB. Microsoft's template asks for Section III to be hosted on the publisher's website for customers; Sections I and II go to Microsoft with the publishing request. It describes what the workload does as of 10 November 2026, read from its public source code at https://github.com/Krusmaster/fabric-backend. Krusgraph holds no certification and no audit report, and this page claims none.

## Publish Workload Requirements Attestation Checklist

We, the vendor, Kruse Consulting AB, have reviewed the Publish Workload Requirements of the Microsoft Fabric Extensibility Toolkit. The sections below give the details, exceptions and variances for each requirement, including the ones not met yet.

### Workload Information

| Description | Value |
| --- | --- |
| Workload Version | 1.0.937 (the package built for the first upload; the version in the publishing request is the one uploaded) |
| Workload Name | Krusgraph.Modeler |
| Release Date | Not yet released. To confirm at the publishing request. |
| Publisher | Kruse Consulting AB, Sweden |
| Item | Krusgraph Model (item type `Krusgraph.Modeler.Model`) |

## Business Requirements

### Value To Customers

The workload provides the following value to customers:

- It reads the table and column names of a lakehouse and proposes keys and relationships, each with the rule that found it.
- The person reviews them, accepts or rejects each one, and can check them against the rows: the check returns counts (orphans, duplicates, empty values), never a row value.
- From what was accepted it builds Fabric items in the same workspace, each shown as a dry run first: a silver notebook, gold views, a pipeline, a semantic model, a report, an API for GraphQL, an ontology, a data agent and a data product over them, with the data flow drawn.
- Nothing is created until the person chooses Create, and every call runs with that person's own Fabric permissions.

### Trial

- [ ] Yes
- [ ] No

Not yet decided. Today reading, the review, the check against the rows and every dry run cost nothing. A paid gate on creating items is built but switched off; it is not a time-limited trial. To confirm by Kruse Consulting AB.

### Monetization

- [ ] Yes
- [x] No

Not yet. There is no live Microsoft Marketplace offer for Krusgraph. The workload charges nothing today. The Marketplace link goes here once an offer is live.

## Technical Requirements

### Microsoft Entra Access

- [x] No other authentication and authorization mechanisms are used
- [ ] Different authentication and authorization mechanisms are used for stored data In Fabric

The editor gets every token from the Fabric host through the JavaScript APIs of the Fabric Workload Client SDK (`acquireFrontendAccessToken`); it has no other sign-in library and no password. The engine accepts only Microsoft Entra access tokens issued for the workload's own Entra app and exchanges them with the on-behalf-of flow, so every call to Fabric runs as the signed-in person.

- Entra app (multitenant): application (client) ID `853a0cf0-7d35-42b7-b384-26178755a72a`, registered in tenant `d2fcf72a-9b80-451d-868b-8d47af30d8ae`.
- Engine endpoint: `https://workload.krusgraph.com/workload/v1/`, scope `https://krusgraph.com/workload/workload/Krusgraph.Modeler/user_impersonation`.
- Delegated permissions only; the app has no application permissions. Power BI Service (Fabric): `Fabric.Extend`; `Workspace.Read.All` and `Lakehouse.Read.All` for reading; `Item.ReadWrite.All`, or the narrower `Notebook.ReadWrite.All`, `DataPipeline.ReadWrite.All`, `SemanticModel.ReadWrite.All`, `Report.ReadWrite.All`, `GraphQLApi.ReadWrite.All` and `DataAgent.ReadWrite.All`, for creating the items the person chooses. Optional, each only if the customer's administrator wants that choice: `Dataset.ReadWrite.All` (one refresh of the new semantic model), `DataPipeline.Execute.All` (Run once or Schedule for the new pipeline), `Tenant.Read.All` (a preflight read of tenant settings; see Admin REST API), `Capacity.Read.All` (a preflight read of the capacity's SKU before publishing a data agent). Azure SQL Database: `user_impersonation`, for reading column metadata and the counts of the check from the SQL analytics endpoint.
- Not yet: publisher verification of the Entra app, and its name matching the workload. To confirm before the publishing request.

### OneLake

- [ ] All data and metadata is stored in One Lake or Fabric Data Stores
- [x] Not all data and metadata is stored in One Lake or Fabric Data Stores

The item's state is its own Fabric item definition (`review.json`, `source.json`, `outputs.json`, `item.json`), and everything it builds is an ordinary Fabric item in the customer's workspace. The workload writes nothing to OneLake itself. Outside Fabric, Krusgraph keeps only usage records and technical logs without content (no table contents, query text, tokens or headers) in Azure Log Analytics, Sweden Central. Table and column names pass through the service's memory during a call and are not saved. No row values are read for the review or the check, and none are stored.

### Microsoft Entra Conditional Access

- [ ] The service works in its entirety even if customers enable this functionality
- [ ] The service works with limitations if customers enable this functionality
- [ ] The service doesn't work with Microsoft Entra Conditional Access

Not yet tested. Tokens come only from the Fabric host and the on-behalf-of exchange is Microsoft Entra's own, so a Conditional Access policy applies when the person signs in. What the editor shows when the on-behalf-of exchange returns a claims challenge has not been tried. To confirm after a test with a Conditional Access policy.

### Admin REST API

- [x] Microsoft Fabric Admin APIs are being used (/admin/*)
- [ ] No Microsoft Fabric Admin APIs are being used

One read-only call, and only as a preflight: List Tenant Settings (`GET /v1/admin/tenantsettings`, delegated `Tenant.Read.All`) checks whether a tenant setting that an output needs is on (Fabric App items for the App output, the Copilot settings for publishing a data agent). Fabric answers it only for a Fabric administrator; for anyone else the editor says the setting could not be read and goes on. The workload changes no tenant setting and calls no other `/admin/*` endpoint.

### Customer Facing Monitoring & Diagnostic

- [ ] Minimum 30 days requirement is adhered to
- [ ] Vendor stores the data for __ days beyond the minimum requirement

Not yet. Log retention is a deployment setting (`log_retention_days`, 30 to 730 days); https://krusgraph.com/it shows the live value. The logs do not yet carry the Fabric activity ID, so a support case cannot yet be matched to a log line by that ID. Diagnostic for the customer: each error in the editor names its kind (for example sign-in, consent, no access, already exists) and the step that fixes it.

### B2B

- [ ] Cross tenant B2B collaboration supported
- [ ] Workload Item Access only within the tenant

Not yet tested. The engine answers only the tenants on its allow-list; how a B2B guest's token is handled has not been tried.

### Business Continuity and disaster recovery

Not yet: there is no written business continuity and disaster recovery plan, recovery time objective or recovery point objective. What exists: the service is one Azure Container App in Sweden Central, rebuilt from the public repository with one script. The workload keeps no customer state of its own (the item's state is in the customer's Fabric workspace), so a rebuild restores the service. Terms: https://krusgraph.com/terms.

### Performance

- [ ] Performance Metrics on workload performance are available via the monitoring hub
- [ ] Workload includes a separate monitoring UI to test and track performance
- [x] Performance tracking isn't currently available to the end user however vendor support personnel can monitor, test, track performance via their internal instrumentation and monitoring systems

Usage records and the container's metrics in Azure. Not yet measured: the editor's load time inside Fabric.

### Presence

- [x] Service availability and colocation/alignment in the following fabric regions

Microsoft Azure, region Sweden Central (EU), only; Fabric public cloud only. Customers in every Fabric region reach the same service in Sweden Central.

- [ ] All or part of the service doesn't reside in Azure

Everything runs in Microsoft Azure: Azure Container Apps for the editor and the engine, Azure Log Analytics for logs.

### Public APIs

- [x] The workload uses Fabric Public APIs

Fabric REST (`https://api.fabric.microsoft.com/v1`) for workspaces, items, definitions and, when the person asks for it, a pipeline run or schedule; the lakehouse's SQL analytics endpoint for column metadata and counts. Always on the signed-in person's behalf.

## Design / UX Requirements

### Common UX

- [ ] The following variance and/or exceptions have been granted by Microsoft

None requested or granted. The editor is built on Microsoft's Fabric Extensibility Toolkit starter kit with Fluent UI: one sticky ribbon with Home as its first tab. The three mascots and the map are our own drawings inside the canvas.

### Item Creation Experience

- [x] Yes
- [ ] No

Fabric's own create dialog (`createItemDialogConfig`), offered on Home, in the Creation Hub and in the workspace's + New menu. Not yet tested under `*.powerbi.com`.

### Monitoring Hub

- [ ] Yes
- [x] No

The Krusgraph Model item does not report to the Monitoring hub (`supportedInMonitoringHub: false`). Builds run during the call. A pipeline the person chooses to run once or schedule is a Fabric pipeline, and its runs show in the Monitoring hub as that pipeline's runs.

### Trial Experience

- [ ] Trial Supported
- [ ] Trial Not Supported

Not yet decided; see Trial.

### Monetization Experience

- [ ] The monetization experience is integrated with the market place
- [ ] Bring Your Own License (BYOL)
- [ ] Free / Freemium
- [ ] Other

Not yet decided. The workload charges nothing today. Terms: https://krusgraph.com/terms (preview terms). Pricing: https://krusgraph.com/pricing.

### Accessibility

- [ ] The user experience follows the guidelines
- [x] The following limitations exist

No accessibility audit has been done. What exists: Fluent UI components; the map has a List view with the same keys and relationships as rows for the keyboard and screen readers; each box of the data flow opens with a click, Enter or Space; the mascots can be switched off. Not yet checked: contrast in Fabric's themes, screen-reader names on the map and the flow, focus order.

### World Readiness / Internationalization

- [x] English is the only supported language
- [ ] The following languages are supported

### Item Settings

- [ ] Yes
- [x] No

### Samples

- [x] Samples not provided
- [ ] Samples for preconfiguration of items provided

A synthetic sample dataset can be loaded with a notebook described in the documentation; it is not offered inside the workload.

### Custom Actions

- [x] Custom Actions aren't implemented
- [ ] Custom Actions implemented as part of Workload

### Workspace settings

- [ ] Supported
- [x] Not Supported

### Global Search

- [ ] Supported
- [x] Not supported

## Security / Compliance Requirements

### Security general

Not yet: no independent security assessment and no penetration test has been done. To confirm by Kruse Consulting AB who performs one, and when. What exists, all in the public repository: a security policy with how to report a vulnerability (`SECURITY.md`); a self-assessment against ISO 27001 controls that is not a certification and claims none; a dependency audit and a software bill of materials on every change; the editor's host sends a Content-Security-Policy whose `frame-ancestors` allows only `*.fabric.microsoft.com` and `*.powerbi.com`, CORS only for those origins, HSTS, and sets no cookie; automated tests of token validation.

Security contact: gustav@krusgraph.com (also in https://krusgraph.com/.well-known/security.txt).

### Privacy

- [x] Publisher attests that only essential HTTP-only cookies are used by the Workload and only after positively authenticating the user. The workload's host sets no cookie at all.
- [x] Publisher attests that it's not using or relying on third-party cookies as part of their solution.
- [x] Publisher attests that it's obtaining any Microsoft Entra token using the JavaScript APIs provided by the Fabric Workload Client SDK.

Privacy policy: https://krusgraph.com/privacy. Not yet: no independent privacy review has been done. To confirm by Kruse Consulting AB.

### Data Residency

- The service runs in Microsoft Azure, Sweden Central (EU), only.
- What reaches it from the customer's tenant: lakehouse table and column names, data types, constraint metadata and counts; the person's token for the on-behalf-of exchange. No row values.
- What it stores: none of that. The item's state and everything it builds stay in the customer's own workspace, in the customer's region. Logs without content stay in Sweden Central.
- For a tenant outside the EU, its metadata (names and counts) is processed in Sweden in transit. There is no other region today.
- Details: https://krusgraph.com/it and https://krusgraph.com/privacy.

### Compliance

None. Krusgraph holds no certification or audit report (no ISO 27001, SOC 2, HIPAA or other). It is operated by Kruse Consulting AB in Sweden under the EU General Data Protection Regulation. Security and data handling: https://krusgraph.com/it.

## Support

### Live site

Microsoft direct vendor outreach:

| Contact | Value |
| --- | --- |
| Contact Name/Team | Kruse Consulting AB, Krusgraph support |
| Number | Not provided |
| Email alias | gustav@krusgraph.com (to confirm whether a support alias replaces it) |
| Self Service portal | https://krusgraph.com/support |

### Supportability

- [ ] Vendor attests that support information is published to the marketplace offering and available to user/customers directly via the workload

Not yet: there is no service level agreement and no Marketplace offer. The workload page links help (https://krusgraph.com/support) and documentation (https://krusgraph.com/docs). Support is by email, best effort, from one person; no fixed response time.

### Service Health and Availability

Not yet: there is no service health dashboard. The service answers `GET https://krusgraph.com/health`.

## Fabric Features

### Application Life Cycle Management (ALM)

- [ ] Supported
- [x] Not Supported

Not yet tested. The item definition is small JSON parts with a version field and no token or row value, designed for Git, but Fabric Git integration and deployment pipelines have not been tried with it.

### CI/CD (Continuous Integration / Continuous Deployment)

- [ ] CI/CD is supported via the Fabric CICD manifest section
- [x] CI/CD is not supported

### Item Definition Portability

- [ ] Items can be restored with their definition in other workspaces
- [ ] Items cannot be restored in other workspaces

Not yet tested. By design, `source.json` names the source lakehouse and `outputs.json` the items built, so a copy in another workspace points at the original lakehouse until the person chooses another.

### Private Links

- [ ] Supported
- [x] Not Supported

The editor and the engine are on the public internet at workload.krusgraph.com.

### Data Hub

- [ ] Supported
- [x] Not Supported

The Krusgraph Model is not a data item. The items it builds are Fabric's own and appear in the OneLake catalog as usual.

### Data Lineage

- [ ] Supported
- [x] Not Supported

Not in Fabric's lineage view. The item draws its own data flow from bronze to gold and what is built on it.

### Sensitivity Labels

- [ ] Supported
- [x] Not Supported

The item exports no data; its Copy button copies generated code, never row values. Not yet tested: Sensitivity Labels on the Krusgraph Model item.

## Extra Notes

The workload is open source under the MIT licence: https://github.com/Krusmaster/fabric-backend. Every creating action is a dry run first and runs only when the person chooses Create. A pipeline is run or scheduled only when the person ticks Run once or Schedule.

## References

- Website: https://krusgraph.com
- For IT departments (permissions, data, retention): https://krusgraph.com/it
- Documentation: https://krusgraph.com/docs
- Support: https://krusgraph.com/support
- Privacy policy: https://krusgraph.com/privacy
- Terms: https://krusgraph.com/terms
- Source code: https://github.com/Krusmaster/fabric-backend
- Marketplace offer: not yet
- Service health dashboard: not yet
