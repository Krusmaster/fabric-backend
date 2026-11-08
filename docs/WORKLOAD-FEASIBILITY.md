# Feasibility study: Krusgraph as a native Fabric workload

Round n153, 8 November 2026. Documentation only: no product code, nothing created in Fabric, Azure or Entra, no
sign-ups. It updates `docs/FET-PLAN.md` (25 October 2026) with what Microsoft's documentation says today, and turns it
into a plan of build rounds that can start once the founder has a company and his own Entra tenant.

## How this was researched

- Every fact about Microsoft's platform carries a source number `[Sn]`. The list is at the end, with URL, the commit
  read and the date read. All sources were read on **8 November 2026**.
- learn.microsoft.com and blog.fabric.microsoft.com could not be reached from the environment this was written in (DNS
  blocked). The Learn pages were therefore read from their source Markdown in `MicrosoftDocs/fabric-docs` (commit
  `caec836`, 6 November 2026) and `MicrosoftDocs/entra-docs` (commit `38d2355`, 7 November 2026). These repositories
  are what Learn publishes; the Learn URL is given next to each file. Each page's own `ms.date` is listed too.
- The starter kit was read at `microsoft/fabric-extensibility-toolkit` commit `dacab1b` (6 August 2026). Its
  `LICENSE` is MIT (copyright Microsoft Corporation), opened and read at that commit.
- **Unconfirmed** marks anything that no primary page read here states. Treat those as questions, not facts.
- The Fabric blog post on general availability could not be opened. Nothing in this study depends on its content.

## Summary

| Question | Short answer |
| --- | --- |
| Can Krusgraph be a Fabric item type? | Yes, technically. A workload is our own web app, hosted by us, shown by Fabric in an iframe, with its own item types [S1][S2]. |
| Can the Python engine stay? | Yes. The frontend must be a web app (TypeScript/React in the starter kit), but it may call our own Entra-protected service with a token from the Fabric SDK [S5]. Our server already does the on-behalf-of exchange that Microsoft's remote-endpoint docs describe [S6]. |
| Can we use it in our own tenant without Microsoft's review? | Yes. Internal publishing needs no registration and no publishing requirements [S3][S4]. The general requirements (verified domain, HTTPS, Entra app) still apply [S8]. |
| Can other tenants use it before Microsoft lists it? | Yes, up to 20 selected tenants, and only if each tenant's admin turns on "Users can see and work with additional workloads not validated by Microsoft" [S3]. |
| What does a public listing need? | A published Azure Marketplace or AppSource offer, a verified-publisher Entra app, an attestation document, a passing validation, and a publishing request. Required already for the Preview listing, not only for GA [S9]. |
| What is permanent? | The workload name `[Publisher].[Workload]`. It is reserved in the publishing tenant at first upload and cannot be changed [S3][S7]. |
| Biggest blockers | The company, tenant and Partner Center account (founder's steps); the Marketplace offer requirement; documentation gaps for remote backends ("link TBD", "currently not supported"). |

## 1. What the Extensibility Toolkit is

**What it is.** A workload is "a partner- or customer-built web application that integrates into the Fabric portal."
The Fabric host loads the app according to its manifest, provides Entra tokens and exposes a host API for navigation,
theming and notifications. The app is "hosted by you, rendered in Fabric via iFrame" [S1]. A workload can contribute
item types that appear in workspaces and take part in sharing, search, lineage and lifecycle operations; item CRUD goes
through the standard Fabric Items REST API [S1][S10].

**Relation to the Workload Development Kit (WDK).** Both the toolkit overview and the WDK overview say: "The
Extensibility Toolkit is the modern evolution of the Workload Development Kit" [S1][S30]. The WDK pages remain
published (WDK overview `ms.date` 05/07/2026) and do not announce a retirement date in the files read (**unconfirmed**
whether the WDK is deprecated). The practical differences that matter to us:

| | WDK (older) | Extensibility Toolkit |
| --- | --- | --- |
| Backend | A .NET backend was part of the model [S30] | Frontend-only by default; tokens acquired in the browser [S12] |
| Remote code | Always | Optional "remote endpoints" for jobs and lifecycle notifications [S13] |
| Starter | `Microsoft-Fabric-workload-development-sample` | `microsoft/fabric-extensibility-toolkit` (MIT) [S28] |

**Status.**

- The toolkit pages read here carry no "preview" label on the toolkit itself [S1]. The repository's earlier
  `docs/FET-PLAN.md` cites a Fabric blog listing titled "generally available"; its body could not be read, so **the GA
  date is unconfirmed**.
- Several features are still marked as in development on the Key concepts page (`ms.date` 12/15/2025): "CI/CD support
  for the Extensibility Toolkit is currently under development", and the same for the item CRUD notification API and the
  Fabric scheduler [S10]. The starter kit's release v2026.03 adds remote hosting ("Production Ready"), job scheduling
  and lifecycle operations [S29]. The two sources are months apart; **which features are GA today is unconfirmed**.
- **Partner publishing** has its own two stages, per workload: after Microsoft accepts a publishing request the workload
  "is listed as Preview to all tenants"; a second request removes the preview badge for General Availability [S3].
- The tenant settings for additional workloads: "Workspace admins can add and remove additional workloads" is marked
  (preview); the other three settings carry no preview label [S20].
- Not supported on Power BI Pro capacities [S1]. "All workloads are blocked for consumption and development if Private
  Link is enabled on tenant or workspace level" [S10].

## 2. Architecture

### What runs where

```
Fabric portal (app.fabric.microsoft.com / app.powerbi.com)
 └─ iframe: Krusgraph editor (TypeScript/React, Fluent UI, @ms-fabric/workload-client)   ← hosted by us
      ├─ Fabric REST APIs (items, definitions, workspaces)  — token from acquireFrontendAccessToken
      ├─ OneLake (item folder)                               — token for storage scope
      └─ Krusgraph engine API (Python, existing container)  — token for our own app's scope
            └─ on-behalf-of → SQL analytics endpoint (TDS) and Fabric REST, as the user
```

| Part | Where | Notes |
| --- | --- | --- |
| Fabric host | Microsoft | Renders the iframe, gets tokens, mediates platform calls [S2]. |
| Editor (frontend) | Our hosting, HTTPS, a subdomain of our Entra-verified domain | CORS for `*.powerbi.com` and `*.fabric.microsoft.com`, CSP frame ancestors for Fabric [S8]. Starter kit uses React 18, Fluent UI v8/v9 and `@ms-fabric/workload-client` ^3.1.1 [S28]. |
| Engine API (backend) | Our hosting (today: Azure Container Apps, Sweden Central) | Called by the editor with a Bearer token [S6]. Optional: Fabric calls it for jobs and lifecycle events [S13]. |
| Item state | Fabric | Item definition stored by Fabric in a hidden OneLake folder [S10][S11]. |
| Item data | OneLake | Each item has its own folder with `Files` and `Tables` [S10][S15]. |

### Authentication

- **One Entra app for the workload.** Multitenant (`AzureADMultipleOrgs`). Delegated Power BI Service (Fabric)
  permissions `Fabric.Extend` (mandatory), `Workspace.Read.All`, `Item.Read.All`, `Item.ReadWrite.All`,
  `Item.Execute.All`, `Item.Reshare.All`, `Lakehouse.Read.All` and others; Azure Storage `user_impersonation` for
  OneLake; Microsoft Graph `User.Read`. Fabric and Power BI client apps are pre-authorized [S14]. The publishing rules
  say to keep scopes to what is needed (optional at both stages) [S9].
- **Redirect URIs** (SPA platform per the tutorial): `{frontend}/close` and
  `https://app.fabric.microsoft.com/workloadSignIn/{tenant}/{workload}` (plus `app.powerbi.com`) [S14]. The `/close`
  page must only run `window.close()` [S9]. The general requirements page says "Type: Web application" [S8], the
  tutorial says SPA [S14]: **unconfirmed which one the validator expects**.
- **Application ID URI.** In development `api://localdevinstance/{tenant}/{workload}/{random}` [S14]. For publishing,
  a resource ID on the verified domain: `https://<verified-domain>/<frontend>/<backend>/<workload-id>/<optional>`, the
  frontend a subdomain with at most one extra segment, no `*.onmicrosoft` domains [S8].
- **Tokens the frontend gets.** `workloadClient.auth.acquireFrontendAccessToken({ scopes })` returns a JWT. With no
  scopes it is a Fabric API token; with scopes it can be for Azure Storage or "any Entra-secured application you own"
  [S5][S12]. Tokens must come only from this SDK API; no third-party cookies [S9]. The API page says "Advanced
  features like full consent prompting and conditional access handling are not yet available" [S5], while the
  publishing requirements ask workloads to support Conditional Access [S9]: a gap to watch.
- **Tokens a remote endpoint gets.** When Fabric calls our backend (jobs, lifecycle) the header is
  `SubjectAndAppToken1.0 subjectToken="…", appToken="…"`. The app token proves the call is from Fabric (app id
  `00000009-0000-0000-c000-000000000000`); the subject token is the user's, with scope `FabricWorkloadControl`, and may
  be missing for system operations. The backend exchanges it with the on-behalf-of flow for
  `https://analysis.windows.net/powerbi/api/.default` (Fabric) or `https://storage.azure.com/.default` (OneLake) [S6].
- **Frontend to our backend** uses plain Bearer tokens [S6].

### How an item stores its state

- **Item definition** = the control plane: "all the information necessary to recreate the item's functional state."
  Up to five human-readable text parts (JSON or YAML). Stored with `saveItemDefinition`; not parsed or validated by
  Fabric; may be restored from Git in an older version, so it needs a version field and migrations [S11].
- **OneLake item folder** = the data plane, for files and Delta/Iceberg tables [S10][S15].
- Environment-specific values (connections, other items' ids) should use the Variable Library [S11].

### Calling Fabric on the user's behalf

From the browser: the Fabric token from `acquireFrontendAccessToken` against `https://api.fabric.microsoft.com/v1/...`
[S5]; the starter kit wraps this in `FabricPlatformAPIClient` [S15]. From the backend: OBO with the subject or Bearer
token [S6]. In both cases the call runs with the user's own Fabric permissions.

### Mapping our Python server onto it

The deciding constraint: column and constraint metadata comes from the SQL analytics endpoint over TDS, which a browser
cannot speak (see `docs/FET-PLAN.md`, "Remote endpoint"). So the engine stays server-side.

| Category | What | Files today |
| --- | --- | --- |
| **Reuse as-is** | Inference (keys K0–K5, relationships R0–R4), the review file and its two statuses, counting checks, GraphQL definition and create-or-update with dry run, semantic model/report/pipeline/ontology/data-agent builders, lineage reading, Git export layout | `infer.py`, `schema.py`, `review.py`, `evidence.py`, `graphql.py`, `deploy.py`, `ontology.py`, `pipeline.py`, `data_agent.py`, `lineage.py`, `git_export.py` |
| **Reuse with a change** | Token validation and OBO: accept a second audience (the workload app or its API scope) next to the MCP app | `entra.py` |
| **Wrap** | The MCP tools return JSON strings for an agent. The workload needs a small HTTP API with stable JSON shapes: `POST /workload/v1/review`, `/check`, `/build` (dry run and real), calling the same functions the tools call | new `fabric_backend/workload_api.py`, routes mounted in `server.py` |
| **New** | The editor (TypeScript/React/Fluent), the manifests and package, item definition load/save and migrations, the graph view port | new top-level `workload/` (from the starter kit, MIT) |
| **New, later** | Fabric-called endpoints (jobs, lifecycle) behind `SubjectAndAppToken` validation | `fabric_backend/workload_remote.py` |
| **Not reused inside Fabric** | The MCP protocol layer, the website | stays as the path for Claude and other agents |

Whether the workload app can reuse the existing MCP Entra app or needs a second one is open. The workload app's
publisher and name must "align with the workload name" [S9] and its Application ID URI follows the resource ID rule
above [S8]; the MCP app's URI is `https://krusgraph.com/mcp`. A second app is the cautious choice.

## 3. Item design: "Krusgraph Model"

### Names

- Workload name: `Krusgraph.<Workload>` with the workload part at most 32 characters, e.g. `Krusgraph.Modeler`; item
  type `Krusgraph.Modeler.Model` (the starter kit names types `{{WORKLOAD_NAME}}.HelloWorld`) [S7][S28].
- Display name "Krusgraph Model". Generic words such as "AI" or "Agent" without a qualifier are not allowed [S9].
- During development use `Org.Krusgraph`; the `Org.` form needs no registration [S3]. Do not upload a `Krusgraph.*`
  package until the publisher name is final, because the first upload reserves it for good [S3].

### Stored definition (at most five text parts [S11])

| Part | Content | Source in this repo |
| --- | --- | --- |
| `review.json` | The review file: plan, each key and relationship with `review` (proposed/accepted/rejected/open) and `check` (not_checked/passed/failed/stale), reasons, counts. Never row values, tokens or secrets. | `review.py` (same bytes for the same input) |
| `source.json` | `version`, the source reference (workspace, item, schema) — as Variable Library references where possible | new |
| `outputs.json` | Chosen outputs and their names and options (writable or not, tables included), plus the ids of items already created | new |
| `item.json` | Definition format version and editor settings | new |

The item does not need OneLake data in phase 1. Later the evidence report (Markdown) can go to the item's `Files`
folder.

### Editor

The publishing rules fix the frame: one ribbon, sticky, with a first tab called "Home"; Fluent styling; creation only
through Fabric's standard create dialog (`createItemDialogConfig` in `Product.json`); support for the multitasking
menu; works on both Fabric domains [S16]. Inside that frame, the four steps of the Shop Desk "Build your own" flow
(review plan → choose what to build → preview → result) become views of one editor. Shop Desk is a Lovable app
(`demo.krusgraph.com`) whose source is not in this repository; the step list is taken from the round's brief and
`fabric_backend/page_templates/LOVABLE.md`.

| View | What the user does | Engine call | Ribbon (Home) |
| --- | --- | --- | --- |
| Empty state | Pick a lakehouse (later: warehouse, SQL database) in the workspace | none | Choose source |
| Review | Graph of tables with K/R rule pills; list of keys and relationships with Accept / Reject; open items first | `review` (and `check` on demand) | Refresh plan, Check against rows, Save |
| Choose outputs | Tick API for GraphQL (phase 1); later semantic model, report, pipeline, ontology, data agent draft | none | Next |
| Preview (dry run) | See what would be created or changed, and the checks that passed | `build` with `dry_run=true` | Create |
| Result | Endpoint, links to created items, the portal steps still left (introspection, permissions) | `build` with `dry_run=false` | Open item |

Re-opening the item re-runs the plan with the saved `review.json` as `previous`, so decisions carry over and only new
columns need a look (`review_plan` already takes `previous`).

### Lineage

Fabric's lineage view for a custom item: no page read here documents how a workload declares lineage edges
(**unconfirmed**). The attestation must describe lineage support [S9][S19]. What is known: the item's state "should hold
references (IDs, URIs) to the items it created" [S10]; the created GraphQL API names its source in its own definition
(`lineage.py` reads it). Plan: store created item ids in `outputs.json` and show them in the editor; ask Microsoft how
custom items appear in lineage.

### Git and CI/CD

Item definitions are what Fabric Git integration stores and what deployment pipelines carry [S11]. CI/CD for toolkit
items is described as "under development" on the Key concepts page [S10]; the manifest's CICD section is optional at
both stages; describing ALM in the attestation is required [S9]. Consequences for us: keep `review.json` stable and
diff-friendly (it already is), keep ids out of it, version every part.

### Permissions

Workspace roles and tenant governance apply to workload items automatically [S1]. Every engine call runs on the user's
own token (OBO), so a user who cannot read the lakehouse or create items gets Fabric's own error. Which workspace role
is needed to create items through the API is set by Fabric (**not checked here**).

## 4. Development setup

| Need | What | Source |
| --- | --- | --- |
| Code | Fork of the starter kit (MIT), in Codespaces or locally | [S17][S28] |
| Tools | Node.js LTS, PowerShell 7, .NET SDK (DevGateway), Azure CLI (Entra app creation only), VS Code | [S17] |
| Entra | Permission to register apps; the `CreateDevAADApp.ps1` script creates the dev app | [S14] |
| Tenant settings | "Capacity admins and contributors can add and remove additional workloads", "Workspace admins can develop partner workloads", "Users can see and work with additional workloads not validated by Microsoft"; then Fabric Developer Mode | [S18][S20] |
| Run | `StartDevServer.ps1` (local server, `http://localhost:60006`) and `StartDevGateway.ps1` (registers the local instance with Fabric) | [S14][S18] |
| Workspace | "Access to a Fabric tenant and a workspace where you can create items" | [S17] |

**Cheapest option.**

- Not a Power BI Pro capacity [S1]. A Fabric trial gives 60 days on an F4 or F64 trial capacity [S21]. Whether a
  workload in development runs on a trial capacity is **unconfirmed**; test it first.
- After the trial: the smallest paid F capacity, paused when not in use (pausing stops the charge; overages are billed
  on pause) [S22]. The live tests of 27 October 2026 already ran on an F2. Prices: **not checked here**; read the Azure
  pricing page for the chosen region before buying.
- A trial can be started with a personal email through an Azure account [S23]; for this project use the company tenant
  instead, because the workload name is reserved in the publishing tenant.

**What must exist before the first upload.**

| Item | Rule | Source |
| --- | --- | --- |
| Verified custom domain in the publishing tenant | Required for all publishing, internal too; frontend is a subdomain of it | [S8] |
| Workload name | `[Publisher].[Workload]`, workload part ≤ 32 characters; confirmed in a dialog at first upload; "permanently reserved in your tenant" and cannot be changed | [S3][S7] |
| Publisher name | Must be clear and match the Marketplace listing and the Entra app publisher | [S9] |
| Package | NuGet `.nupkg`, at most 20 MB; `Product.json` at most 50 KB; every upload a new version number | [S24][S25] |
| Admin account | Upload is done in OneLake catalog → Govern → Configurations → Workloads, by an admin | [S25] |

A note on the domain: `krusgraph.com` today serves the MCP app with Application ID URI `https://krusgraph.com/mcp`.
If the domain has to move to the new company tenant, the existing MCP app moves with it or must be re-registered there.
Whether a domain can be verified in two Entra tenants at once is **unconfirmed** (Entra docs not read in this round).

## 5. Publishing path

| # | Step | Who | Source |
| --- | --- | --- | --- |
| 1 | Build and test with DevGateway in the company tenant (`Org.Krusgraph`) | build rounds | [S18] |
| 2 | Upload the package as `Org.Krusgraph` and activate a version: internal use, no registration, no review | founder (admin) | [S3][S25] |
| 3 | Decide the final `Krusgraph.<Workload>` name; upload; confirm the name dialog (permanent) | **founder** | [S3] |
| 4 | Publish tab → "Selected tenants" → up to 20 tenant ids → choose version → Publish. Visible after up to 10 minutes; each tenant's admin must turn on the "not validated by Microsoft" setting | **founder**, plus each test tenant's admin | [S3] |
| 5 | Join the Microsoft AI Cloud Partner Program; get the partner global account verified; associate the Entra tenant | **founder** | [S26] |
| 6 | Mark the workload Entra app as publisher verified (needs step 5; no charge, no licence) | **founder** | [S26] |
| 7 | Publish an Azure Marketplace / AppSource SaaS offer in Partner Center; put its URL in the manifest's license link. Required for Preview | **founder** | [S9][S27] |
| 8 | Write the attestation document from Microsoft's template; host it at a public HTTPS URL; put the URL in the manifest | rounds draft, **founder** signs | [S9][S19] |
| 9 | Manifest links: terms of use, privacy policy, documentation, help, support contact, getting started; icons (product 240×240), banner 1920×240, an image or video for "At a glance" | rounds | [S9] |
| 10 | Run the validator (`microsoft/fabric-extensibility-toolkit-validator`, Node.js, against the published workload, best from a different tenant): automated and manual tests, report in Markdown/HTML/PDF | rounds, **founder** for manual checks | [S31][S32] |
| 11 | Submit the Publishing Request Form (`https://aka.ms/fabric_workload_publishing`) | **founder** | [S3] |
| 12 | Address Microsoft's feedback; on acceptance the workload is listed as Preview to all tenants | rounds + founder | [S3] |
| 13 | For GA: meet the GA-only items (live-site contacts, supportability with SLA) and submit the request again | **founder** | [S3][S9] |

**Requirements that differ between Preview and GA** [S9]: almost all are required at both. Optional at Preview,
required at GA: live site (contact details for Microsoft's support teams) and supportability (SLA, contact methods).
Optional at both: B2B, business continuity, service-health page, scope minimisation, Monitoring Hub, jobs, trial and
monetisation experiences, item settings, custom actions, CICD manifest section.

**Requirements for all workloads, internal included** [S8]: HTTPS with valid certificates, "Minimum 99.9% uptime
SLA", "Page load times under 3 seconds", CORS and CSP for Fabric domains, OAuth 2.0, token validation, encryption in
transit and at rest. "Backend Configuration (if applicable): Backend configurations are currently not supported."

**Billing.** Two routes: an Azure Marketplace SaaS offer (Partner Center, landing page, webhook, SaaS fulfillment and
metering APIs) or our own billing; the toolkit adds no tools for Marketplace integration [S27]. A Marketplace offer must
exist either way for a listing [S9].

**Fees.** Publisher verification: no charge [S26]. No fee for Workload Hub publishing is mentioned in the pages read
(absence is not confirmation). Marketplace transaction fees: **not checked here**.

## 6. Risks and unknowns

| Risk | What we know | What to do |
| --- | --- | --- |
| Remote backend support | The engine needs a backend. Docs say backend configurations "are currently not supported" [S8] and the job contract swagger is "link TBD" [S13]; the starter kit calls remote hosting "Production Ready" [S29]. | Phase 1 avoids Fabric-called endpoints: the editor calls our API with a Bearer token, a documented path [S5][S6]. Ask Microsoft before relying on jobs. |
| Conditional Access | Required in the attestation [S9]; SDK says CA handling "not yet available" [S5]. | Ask Microsoft; test with a CA policy in the company tenant. |
| Capacity costs (customer) | Counting checks and API creation run on the customer's capacity (`docs/PRICING-NOTES.md`). The UI in the iframe is our hosting. | Keep checks opt-in; show what a check will query. |
| Capacity costs (ours) | A dev capacity costs money while running [S22]; the trial is 60 days [S21]. | Pause when idle; trial first. |
| Data residency | Fabric makes "an Enterprise Promise around data not leaving the geography of the tenant"; the attestation must state our commitments [S9]. Our hosting is Azure Sweden Central (`docs/TRUST.md`). What leaves the tenant: table and column names, types, counts; no row values (`review.py`). | State it plainly in the attestation and on the site. A tenant outside the EU sends metadata to Sweden. Consider a second region only if a customer requires it. |
| Uptime and page load | 99.9% and under 3 seconds apply to all workloads [S8]. One Container App today. | Health checks, min replicas ≥ 1, measure page load in the Fabric iframe. |
| Support obligations | Help link and support contact required at Preview; SLA and live-site contacts at GA [S9]. One person. | Write a support page with honest hours before Preview. |
| Customers we cannot serve | Pro capacities and tenants or workspaces with Private Link [S1][S10]; tenants whose admin will not add a non-validated workload (before listing) [S3]. | The MCP server stays the path for them. |
| What Microsoft can change | Requirements pages change (`ms.date` 02/2026–04/2026); features "under development" [S10]; Fabric "reserves the rights to block the integration" when `Fabric.Extend` consent is missing [S9]. | Pin the SDK version; re-read the requirement pages before each publishing step. |
| Permanent name | Workload name cannot be changed after the first upload [S3]. | Founder decides once, after the company name is settled. |
| Item definition drift | Old definitions can come back from Git [S11]. | Version field and migrations from day one. |
| GraphQL relationships | Relationships in the GraphQL definition worked in our sandbox but are not documented (`docs/FET-PLAN.md`). | Keep the sandbox test in every live run. |

**What would block us outright:** no company or Partner Center account (blocks steps 5–13); the employment/IP question
unresolved (blocks any upload, since the name is permanent); Microsoft declining a workload whose engine runs outside
Fabric (no page says so; **unconfirmed** either way).

## 7. Phased build plan

Each phase is a round of a few days. Each ends with green tests and a short live check in the company tenant.

### Phase 0 — founder only (before any build round)

Company, Entra tenant, verified domain, Fabric trial or F capacity, tenant settings. See the checklist below.

### Phase 1 — one item, one flow: lakehouse → reviewed model → API for GraphQL

Built in round n166 (8 November 2026; not yet run in Fabric). The founder's steps for the first run, and how to remove
it again, are in `docs/WORKLOAD-DEV.md`.

- **Scope:** `Org.Krusgraph` workload with one item type. Editor views: empty state (choose lakehouse), review
  (list-first: keys and relationships with Accept/Reject; a simple graph), preview (dry run), result. Save
  `review.json`, `source.json`, `outputs.json` as the item definition. Engine API: `review`, `build` (GraphQL only).
- **Files:** `workload/` (starter kit fork, HelloWorld item renamed; copy rules in `CONTRIBUTING.md`: commit `dacab1b`,
  MIT, entry in `THIRD_PARTY_NOTICES.md`); `fabric_backend/workload_api.py`; second audience in `entra.py`; routes in
  `server.py`.
- **Tests:** `tests/test_workload_api.py` (token audience accepted and rejected, the review and build JSON shapes on the
  synthetic shop schema in `seed.py`, dry run writes nothing); frontend unit tests for definition load/save and
  migration from `version` 1; one manual run in Fabric through DevGateway.
- **Founder:** run `CreateDevAADApp.ps1` in the company tenant; turn on tenant settings and Developer Mode; approve the
  first real `build`.

### Phase 2 — review depth and re-plan

- **Scope:** "Check against rows" (counting checks, opt-in, shows what it will query); re-open uses saved decisions
  (`previous`); the graph view ported from `fabric_backend/static/site.js`; definition version 2 with migration.
- **Files:** editor graph component; `workload_api.py` `check` route.
- **Tests:** stale-check rule (a changed column makes a pass stale); a version-1 definition opens in version 2.
- **Founder:** none beyond review.

### Phase 3 — more outputs

- **Scope:** choose outputs: semantic model, report, pipeline, ontology, data agent draft, each with a dry run.
  Created item ids stored in `outputs.json`; links in the result view.
- **Files:** `workload_api.py` `build` per output, reusing the existing builders.
- **Tests:** one dry-run test per output on the shop schema; refusal paths (name taken, would remove relationships).
- **Founder:** approve each first real creation in the company tenant.

### Phase 4 — Fabric platform features

- **Scope:** Variable Library for the source reference; Git round trip (commit the item, deploy to a second
  workspace); evidence report to the item's OneLake `Files`; ask Microsoft about lineage and Conditional Access;
  optional: `validate` as a Fabric job once the job contract is published.
- **Tests:** definition round trip through Git export layout (`git_export.py` shares the folder rules).
- **Founder:** connect a test workspace to a Git repository; second workspace for deployment.

### Phase 5 — publish-ready in our tenant and test tenants

- **Scope:** production hosting of the frontend on a subdomain; CSP/CORS; resource-ID Application ID URI; product
  page assets (icons, banner, "At a glance" image); terms, privacy, docs, help and support links; attestation draft;
  run the validator.
- **Files:** `workload/Manifest/*`, `deploy/` additions for the frontend host, `docs/WORKLOAD-ATTESTATION.md` (draft).
- **Tests:** validator report clean for Preview; page-load measurement in the iframe.
- **Founder:** final workload name and first `Krusgraph.*` upload; selected-tenant publish to test tenants.

### Phase 6 — listing

- **Scope:** respond to Microsoft's validation feedback.
- **Founder:** Partner Program, publisher verification, Marketplace offer, publishing request.

## Sources

All read on 8 November 2026. "src" is the file read; the Learn URL is the published page.

| # | Title (`ms.date`) | URL | src |
| --- | --- | --- | --- |
| S1 | Microsoft Fabric Extensibility Toolkit (12/15/2025) | https://learn.microsoft.com/fabric/extensibility-toolkit/extensibility-toolkit-overview | fabric-docs `caec836` docs/extensibility-toolkit/extensibility-toolkit-overview.md |
| S2 | Extensibility Toolkit Architecture (02/25/2025) | https://learn.microsoft.com/fabric/extensibility-toolkit/architecture | …/architecture.md |
| S3 | Publishing Overview (04/08/2026) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-overview | …/publishing-overview.md |
| S4 | Publishing requirements overview (04/08/2026) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-overview | …/publishing-requirements-overview.md |
| S5 | Authentication JavaScript API reference (12/15/2025) | https://learn.microsoft.com/fabric/extensibility-toolkit/authentication-javascript-api | …/authentication-javascript-api.md |
| S6 | Authenticate Remote Endpoints (02/12/2026) | https://learn.microsoft.com/fabric/extensibility-toolkit/authentication-remote | …/authentication-remote.md |
| S7 | Workload Manifest (12/15/2025) | https://learn.microsoft.com/fabric/extensibility-toolkit/manifest-workload | …/manifest-workload.md |
| S8 | General Publishing Requirements (12/15/2025) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-general | …/publishing-requirements-general.md |
| S9 | Validation guidelines and requirements for workloads (02/24/2026) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-workload | …/publishing-requirements-workload.md |
| S10 | Key concepts and Features (12/15/2025) | https://learn.microsoft.com/fabric/extensibility-toolkit/key-concepts | …/key-concepts.md |
| S11 | Store Item Definition (State) (12/15/2025) | https://learn.microsoft.com/fabric/extensibility-toolkit/how-to-store-item-definition | …/how-to-store-item-definition.md |
| S12 | Authentication overview (12/15/2025) | https://learn.microsoft.com/fabric/extensibility-toolkit/authentication-overview | …/authentication-overview.md |
| S13 | Enable Remote Endpoints for Custom Items (02/12/2026) | https://learn.microsoft.com/fabric/extensibility-toolkit/how-to-enable-remote-endpoint | …/how-to-enable-remote-endpoint.md |
| S14 | Create Microsoft Entra App for Fabric Workload (12/15/2025) | https://learn.microsoft.com/fabric/extensibility-toolkit/tutorial-create-entra-app | …/tutorial-create-entra-app.md |
| S15 | Store data in an item (12/15/2025) | https://learn.microsoft.com/fabric/extensibility-toolkit/how-to-store-data-in-item | …/how-to-store-data-in-item.md |
| S16 | Validation guidelines and requirements for items (02/24/2026) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-item | …/publishing-requirements-item.md |
| S17 | Get started (12/15/2025) | https://learn.microsoft.com/fabric/extensibility-toolkit/get-started | …/get-started.md |
| S18 | Detailed Setup Guide (12/15/2025) | https://learn.microsoft.com/fabric/extensibility-toolkit/setup-guide | …/setup-guide.md |
| S19 | Vendor attestation template (02/24/2026) | https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-vendor-attestation-template | …/publishing-vendor-attestation-template.md |
| S20 | Tenant settings for additional workloads (04/08/2026) | https://learn.microsoft.com/fabric/admin/service-admin-portal-additional-workloads | docs/admin/service-admin-portal-additional-workloads.md |
| S21 | Fabric trial capacity (08/12/2026) | https://learn.microsoft.com/fabric/fundamentals/fabric-trial | docs/fundamentals/fabric-trial.md |
| S22 | Pause and resume your Fabric capacity | https://learn.microsoft.com/fabric/enterprise/pause-resume | docs/enterprise/pause-resume.md |
| S23 | Free trial with a personal email (02/27/2026) | https://learn.microsoft.com/fabric/fundamentals/free-trial-account-personal-email | docs/fundamentals/free-trial-account-personal-email.md |
| S24 | Manifest overview (12/15/2025) | https://learn.microsoft.com/fabric/extensibility-toolkit/manifest-overview | …/manifest-overview.md |
| S25 | How to publish and manage a workload (11/18/2025) | https://learn.microsoft.com/fabric/extensibility-toolkit/tutorial-publish-workload | …/tutorial-publish-workload.md |
| S26 | Publisher verification overview (08/13/2024) | https://learn.microsoft.com/entra/identity-platform/publisher-verification-overview | entra-docs `38d2355` docs/identity-platform/publisher-verification-overview.md |
| S27 | How to monetize your workload (12/15/2025) | https://learn.microsoft.com/fabric/extensibility-toolkit/how-to-monetize-workload | …/how-to-monetize-workload.md |
| S28 | Starter kit repository (manifests, `package.json`, LICENSE) | https://github.com/microsoft/fabric-extensibility-toolkit | commit `dacab1b`: Workload/Manifest/WorkloadManifest.xml, items/HelloWorldItem/HelloWorldItem.xml, Workload/package.json, LICENSE |
| S29 | Starter kit release notes v2026.03 | https://github.com/microsoft/fabric-extensibility-toolkit/blob/main/docs/ReleaseNotes/2026/v2026.03.md | commit `dacab1b` |
| S30 | Workload Development Kit overview (05/07/2026) | https://learn.microsoft.com/fabric/workload-development-kit/development-kit-overview | docs/workload-development-kit/development-kit-overview.md |
| S31 | Extensibility Toolkit Validator (12/04/2025) | https://learn.microsoft.com/fabric/extensibility-toolkit/tools-workload-validator | …/tools-workload-validator.md |
| S32 | Validate your workload for publishing (12/15/2025) | https://learn.microsoft.com/fabric/extensibility-toolkit/tutorial-validate-workload | …/tutorial-validate-workload.md |

Not reachable from this environment and therefore not used: learn.microsoft.com directly, blog.fabric.microsoft.com
(the GA announcement), the validator repository itself, Partner Center and Azure pricing pages.

## Founder's checklist, in order

Each line is something only the founder can do. Build rounds can start after step 6.

1. ☐ Clear the employment/IP question in writing.
2. ☐ Register the company (Kruse Consulting AB or another entity); note its legal name — it becomes the publisher name
   customers see.
3. ☐ Create the company's own Microsoft Entra tenant with a global admin account that is not tied to any employer.
4. ☐ Verify a custom domain in that tenant (e.g. `krusgraph.com`). Before moving it, decide what happens to the existing
   MCP Entra app that uses `https://krusgraph.com/mcp`.
5. ☐ Start a Fabric trial in the tenant (60 days); if workloads do not run on it, buy the smallest F capacity and pause
   it when idle.
6. ☐ In OneLake catalog → Govern → Tenant settings, turn on: "Capacity admins and contributors can add and remove
   additional workloads", "Workspace admins can develop partner workloads", "Users can see and work with additional
   workloads not validated by Microsoft". Turn on Fabric Developer Mode. Create one workspace with a lakehouse holding
   the synthetic shop schema.
7. ☐ Run `CreateDevAADApp.ps1` (or approve a round doing it with your sign-in) to create the development Entra app.
8. ☐ Approve each first real creating call during phases 1–3.
9. ☐ Choose the permanent workload name `Krusgraph.<Workload>` (≤ 32 characters after the dot). It cannot be changed.
10. ☐ Upload the first `Krusgraph.*` package and confirm the name dialog.
11. ☐ Find up to 20 test tenants; send each admin the tenant setting to turn on; publish to them.
12. ☐ Join the Microsoft AI Cloud Partner Program; complete verification of the partner global account; associate
    the Entra tenant.
13. ☐ Mark the workload Entra app as publisher verified.
14. ☐ Create and publish the Marketplace (SaaS) offer in Partner Center, with the same publisher name; decide Marketplace
    billing or own billing.
15. ☐ Publish terms of use, privacy policy (naming Azure Sweden Central), documentation, help and a support contact.
16. ☐ Review and sign the attestation document; host it at a public HTTPS URL.
17. ☐ Run the validator's manual tests and read its report.
18. ☐ Submit the Publishing Request Form (`https://aka.ms/fabric_workload_publishing`) for Preview.
19. ☐ Before GA: set a support SLA and live-site contacts; submit the request again.
