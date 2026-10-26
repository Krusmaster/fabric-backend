# Plan: a native Fabric Extensibility Toolkit workload on the same `plan()` engine

Status: plan only, no code. Written 2026-10-25 from Microsoft's public documentation and starter kit (sources at
the end; everything marked *unverified* could not be confirmed from a primary page and must be checked before it
drives a decision). The Learn pages were read from the source Markdown in `MicrosoftDocs/fabric-docs`
(`docs/extensibility-toolkit/`), because learn.microsoft.com itself was not reachable from the environment this
was written in; the URLs below are the corresponding Learn pages.

## Why

Today Krusgraph lives outside Fabric: an MCP server that Claude (or Cursor, Lovable) talks to. A Fabric
Extensibility Toolkit (FET) workload would put the same plan — tables, inferred keys and relationships, the rule
behind each — *inside* the Fabric portal, as an item type a workspace user creates next to their lakehouse,
reviews in an editor, and turns into an API for GraphQL item without leaving Fabric. The engine is the same;
what changes is where the user is standing.

## What FET is, in one paragraph

FET is Microsoft's successor to the Workload Development Kit: you host a web app (React in the starter kit), Fabric
renders it in a sandboxed iframe as a workload with its own item types, and the frontend talks to Fabric through
the workload client SDK [1][2]. The decisive difference from the WDK is a *frontend-only* architecture: no
mandatory backend, tokens acquired in the browser, item state stored by Fabric as an item definition, the standard
"create item" dialog, and CRUD through the public Items API [3]. Optional *remote endpoints* (jobs, lifecycle
notifications) bring a backend back only where you need one [4]. Preview was announced in September 2025 [5];
general availability was announced at FabCon in March 2026 with CI/CD, remote lifecycle notifications and the
scheduler entering preview (*GA date from blog listings, body not fetched: unverified*) [6][7]. Not supported on
Power BI Pro capacities, and all workloads are blocked in tenants with Private Link enabled [1][3].

## Target experience

An item type `Krusgraph.Graph` (the `Publisher.Item` form is required for the Workload Hub; `Org.Item` for
in-tenant use [8]) with one editor:

1. **Create**: the standard Fabric create dialog; the user names the item and, in the editor's empty state, picks
   a source in the workspace (lakehouse, warehouse, SQL database, mirrored database).
2. **Plan**: the engine runs and the editor shows the same graph as krusgraph.com/explore: table cards, wires
   labelled K0–K5 / R0–R4, ambiguous and unlinked columns to review, Accept/Skip for suggestions. Decisions are
   saved in the item definition.
3. **Build**: "Create API for GraphQL" creates or updates the GraphQL item in the same workspace from the reviewed
   plan and shows the endpoint plus the two portal steps that remain (introspection, permissions).
4. **Re-plan**: when the schema changes, re-run; the saved decisions are re-applied and only new columns need a
   look.

The mascots can come along (they are plain SVG and CSS), but the publishing checklist asks for Fluent styling and
a ribbon with a Home tab [9]; that sets the tone of the editor, not of the website.

## Architecture

```
Fabric portal (iframe) ── React editor (TypeScript) ── workload client SDK ── Fabric REST APIs
                                   │                                              │
                                   └── remote endpoint (HTTPS, any runtime) ──────┘
                                       runs the Python engine, reads INFORMATION_SCHEMA over TDS
```

**Frontend** (new, TypeScript): the item editor, the graph view, the review UI, save/load of the item definition,
the "create GraphQL item" call. It acquires tokens with `acquireFrontendAccessToken` for the Fabric API and for any
other Entra-protected scope, including our own remote endpoint [10][11].

**Remote endpoint** (new hosting of existing Python): the piece FET does not do for us. The SQL analytics endpoint
speaks TDS, which a browser cannot; the Fabric REST surface lists lakehouse tables but not their columns
(`GET /lakehouses/{id}/tables` returns name, type, location and format only [12]), so column and constraint
metadata must come from a server that runs `INFORMATION_SCHEMA` queries with the user's token, or from Delta logs
read out of OneLake, or from Spark [13]. The remote endpoint receives a subject token and an app token and does a
real on-behalf-of exchange server-side [14][4] — the same exchange `fabric_backend/entra.py` already implements.
Remote endpoints may be written in any language that can expose an HTTPS endpoint [4].

**Item definition**: the plan and the user's decisions, as JSON parts saved through `saveItemDefinition`
(up to five text parts, no server-side validation, versioned by us) [15]. That makes the reviewed plan part of
the item, visible to the Items API and to Git integration.

## What is reused from this repository

| Reused as-is | Where it lives today |
| --- | --- |
| Inference: keys and relationships with rules K0–K5 / R0–R4, ambiguous and unlinked reporting | `fabric_backend/infer.py` |
| Schema reading from `INFORMATION_SCHEMA` (columns and declared constraints) | `fabric_backend/schema.py` |
| GraphQL item definition and create-or-update deployment, source resolution | `fabric_backend/graphql.py`, `fabric_backend/deploy.py` |
| Rayfin entity generation (a second output from the same plan) | `fabric_backend/rayfin.py` |
| Token validation and on-behalf-of exchange | `fabric_backend/entra.py` |
| The plan-as-JSON shape and the graph renderer (table cards, cardinality wires, rule pills, Accept/Skip) | `fabric_backend/demo.py`, `fabric_backend/static/site.js` |
| The synthetic shop schema for tests and demos | `fabric_backend/seed.py` |

The MCP server itself is not reused inside the workload; it stays as the path for Claude and other agents.

## What must be built

1. **Workload manifest package**: `WorkloadManifest.xml` with `HostingType=FERemote`, the Entra frontend app id
   and the frontend service endpoint; one `Item.xml` for the graph item; `Product.json` and `Item.json` with the
   editor path, icons, create-dialog cards and quick actions; packaged as a NuGet `.nupkg` of at most 20 MB [8][16][17].
2. **Entra app for the workload**: multitenant, SPA redirects for `{frontend}/close` and the Fabric
   `workloadSignIn` URL, delegated permissions including the mandatory `Fabric.Extend`, plus `Item.ReadWrite.All`,
   `Workspace.Read.All`, Azure Storage `user_impersonation` (OneLake) and Graph `User.Read`; Fabric's client apps
   pre-authorised [18]. This is a *second* app registration next to the Krusgraph MCP app, or the same app with
   added permissions; decide after reading the publishing checklist's constraints on token acquisition [9].
3. **The React editor**: item editor with ribbon, empty and detail views, the graph (port of `site.js` to
   TypeScript/React), the review panel, the build dialog, save and autosave of the item definition [19][20].
4. **The remote endpoint**: an HTTPS service hosting the Python engine behind the SubjectAndAppToken contract:
   `plan` (source → plan JSON) and `build` (plan + decisions → GraphQL item). It can reuse the current container
   image and Azure Container App with a second route. The job contract swagger and the remote configuration
   schema are marked "TBD" in the docs [4]; build against the starter kit's reference implementation and expect
   churn.
5. **Hosting and domain**: the frontend must be served over HTTPS from a subdomain of an Entra-verified custom
   domain, with CORS for `*.fabric.microsoft.com` and `*.powerbi.com` [21]. `app.krusgraph.com` or
   `fabric.krusgraph.com` would do; the domain is already verified in the tenant.
6. **Dev loop**: Node LTS, PowerShell 7, .NET SDK for the DevGateway, VS Code or Codespaces; tenant settings for
   developer mode and non-validated workloads; the local server on port 60006 and the DevGateway registration [22][23][24].
7. **Publishing**: first in-tenant (upload the package in the OneLake catalog's workload configuration, activate
   a version) [25][26]; then, if it should reach other tenants, the Workload Hub process: publisher name reserved on
   first upload, test with up to 20 tenants, the publishing request form, verified-publisher Entra app, attestation
   document URL in the manifest, the validator tool and the UX/security checklist [27][28][9][29].
8. **Tests**: the engine tests stay; add contract tests for the remote endpoint (token handling, OBO, plan
   shape) and editor tests on the demo plan.

## Open questions

- **Can relationships be expressed in the GraphQL item definition through the API?** Microsoft's public
  definition page documents `datasources[].objects`; whether relationships are accepted through
  `createGraphQLApi` / `updateDefinition` is not stated there, and one community thread reports failures with full
  payloads [30][31]. This repository's own evidence says yes: `fabric_backend/graphql.py` writes
  ManyToOne/OneToMany relationships into the definition, and the README records a sandbox run on 2026-10-21 where
  nested queries resolved over four inferred hops (issue #1 in this repository). Treat it as *working but
  undocumented*: keep the sandbox test in the pilot checklist and expect the payload shape to change without notice.
- **Which identity reaches the SQL endpoint?** The remote endpoint receives subject and app tokens and may
  exchange them for other scopes [14]; confirm that an exchange to `https://database.windows.net/.default` is
  allowed for a workload app, as it is for the MCP app today.
- **Remote backend support in the manifest.** The publishing requirements page says backend configurations are
  not supported in the manifest, while the starter kit's v2026.03 release is titled "Remote Hosting & Job
  Scheduling" [32][21]. Which statement is current is *unverified*.
- **One Entra app or two?** The MCP app's Application ID URI is `https://krusgraph.com/mcp` and its scope is
  `user_impersonation`; the workload needs SPA redirects and `Fabric.Extend`. Two apps keep the consent stories
  separate; one app keeps the admin's life simpler.
- **Python in the loop or a TypeScript port?** The engine is ~200 lines of name rules; a faithful TypeScript port
  would make the workload frontend-only for *planning* (if column metadata can be read without TDS, e.g. from
  Delta logs in OneLake [33]) and leave only *building* to Fabric's own REST API from the browser. That removes
  the remote endpoint entirely but duplicates the rules. Decide after measuring how reliably Delta logs give
  column names and types for the sources we care about.
- **Pro capacities and Private Link** exclude some customers from any FET workload [1][3]; the MCP path stays
  for them.

## Suggested order

1. Verify the two blocking questions (relationships in the definition; OBO to SQL from a workload app) with a
   throwaway in-tenant workload — days, not weeks.
2. Port the graph renderer to React against `/demo/plan.json`; it is useful on its own and risk-free.
3. Stand up the remote endpoint from the existing container; wire `plan` first, `build` second.
4. In-tenant publish, pilot with one workspace, then decide on the Workload Hub.

## Sources

1. Extensibility toolkit overview — https://learn.microsoft.com/fabric/extensibility-toolkit/extensibility-toolkit-overview
2. Architecture — https://learn.microsoft.com/fabric/extensibility-toolkit/architecture
3. Key concepts — https://learn.microsoft.com/fabric/extensibility-toolkit/key-concepts
4. Remote endpoints — https://learn.microsoft.com/fabric/extensibility-toolkit/how-to-enable-remote-endpoint
5. FabCon Vienna announcement, 16 Sep 2025 — https://www.microsoft.com/en-us/microsoft-fabric/blog/2025/09/16/fabcon-vienna-build-data-rich-agents-on-an-enterprise-ready-foundation/
6. "Microsoft Fabric Extensibility Toolkit generally available" (blog listing; body not fetched) — https://blog.fabric.microsoft.com/en-US/blog/microsoft-fabric-extensibility-toolkit-generally-available/
7. Starter kit release notes v2026.03 — https://github.com/microsoft/fabric-extensibility-toolkit/blob/main/docs/ReleaseNotes/2026/v2026.03.md
8. Workload manifest — https://learn.microsoft.com/fabric/extensibility-toolkit/manifest-workload
9. Publishing requirements: workload — https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-workload
10. Authentication JavaScript API — https://learn.microsoft.com/fabric/extensibility-toolkit/authentication-javascript-api
11. Access Fabric APIs — https://learn.microsoft.com/fabric/extensibility-toolkit/how-to-access-fabric-apis
12. Lakehouse REST API (tables) — https://github.com/microsoft/fabric-rest-api-specs/blob/main/lakehouse/swagger.json
13. Cloud Shell sample (Spark/Livy) — https://learn.microsoft.com/fabric/extensibility-toolkit/sample-cloud-shell
14. Authentication for remote endpoints — https://learn.microsoft.com/fabric/extensibility-toolkit/authentication-remote
15. Store the item definition — https://learn.microsoft.com/fabric/extensibility-toolkit/how-to-store-item-definition
16. Manifest overview — https://learn.microsoft.com/fabric/extensibility-toolkit/manifest-overview
17. Item manifest — https://learn.microsoft.com/fabric/extensibility-toolkit/manifest-item
18. Create the Entra app — https://learn.microsoft.com/fabric/extensibility-toolkit/tutorial-create-entra-app
19. Item overview (editor) — https://learn.microsoft.com/fabric/extensibility-toolkit/concept-item-overview
20. Starter kit components — https://github.com/microsoft/fabric-extensibility-toolkit/blob/main/docs/components/README.md
21. Publishing requirements: general — https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-general
22. Get started — https://learn.microsoft.com/fabric/extensibility-toolkit/get-started
23. Setup guide — https://learn.microsoft.com/fabric/extensibility-toolkit/setup-guide
24. Register a local workload — https://learn.microsoft.com/fabric/extensibility-toolkit/tools-register-local-workload
25. Publishing overview — https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-overview
26. Publish a workload (tutorial) — https://learn.microsoft.com/fabric/extensibility-toolkit/tutorial-publish-workload
27. Publishing requirements overview — https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-overview
28. Publishing requirements: item — https://learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-item
29. Validate a workload — https://learn.microsoft.com/fabric/extensibility-toolkit/tutorial-validate-workload
30. GraphQL API REST spec — https://github.com/microsoft/fabric-rest-api-specs/blob/main/graphQLApi/swagger.json
31. GraphQL API item definition — https://learn.microsoft.com/rest/api/fabric/articles/item-management/definitions/graphql-api-definition
32. Starter kit repository — https://github.com/microsoft/fabric-extensibility-toolkit
33. Store data in OneLake — https://learn.microsoft.com/fabric/extensibility-toolkit/how-to-store-data-in-onelake
34. Workload Development Kit overview (points to FET) — https://learn.microsoft.com/fabric/workload-development-kit/development-kit-overview
35. API for GraphQL: overview, relationships, limits — https://learn.microsoft.com/fabric/data-engineering/api-graphql-overview · https://learn.microsoft.com/fabric/data-engineering/manage-relationships-graphql · https://learn.microsoft.com/fabric/data-engineering/api-graphql-limits
