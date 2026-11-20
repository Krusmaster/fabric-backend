# Publish to OneLake catalog (the catalog accelerator)

> 17 November 2026, round CA1. Code: `fabric_backend/catalog_publish/`, the MCP tool `publish_catalog`, the route
> `POST /workload/v1/catalog` and the Model editor's step on the Data product page (`CatalogPanel.tsx`). Status: unit
> tests and a browser check of the editor's page at 375, 412 and 1280 px. **Not run against Fabric.**

The OneLake catalog is part of every Fabric tenant: nothing is provisioned. "Publish to OneLake catalog" fills it in
one step for the data products Krusgraph has checked, and shows exactly what it would write before anything is
written. No AI model is used: the same plan and the same counts give the same answer.

## What it does

1. **A product card per data product.** The products are the groupings `domain_draft` proposes. Each card has:
   - a plain description of at most 256 characters, ending with the dated evidence line, for example "4 of 4 keys
     unique, 0 orphan rows over 3 links, checked 17 Nov 2026";
   - the owner you name, or "not chosen yet";
   - the proposed domain;
   - tags (`Krusgraph` and the product's name; never a health word, because a tag has no date);
   - the ODCS v3.2.0 contract;
   - glossary terms, one per entity of the ontology, defined from its key and its links;
   - the data quality rules that follow from what was proven.

   Without counts (`check_rows=false`) the card says "not yet checked against the rows" and claims nothing.
2. **Quality rules from the proof** (`quality.py`). Each rule comes with the T-SQL that counts it (must be 0) and a
   status: proven, proposed (counted and broken) or not counted.
   - `unique_key`: no duplicates and no empty values.
   - `no_orphans`: every reference with a value finds its row.
   - `rows_kept_after_join`: totals at the right grain. Where `validate_plan`'s amount levels found a header amount that
     a join repeats, the join keeps each line row once, and the header amount is summed on the header table.
3. **The diff of what you may write** (`writes.py`). Each change is listed with what is there now and what would be
   there after. Only two calls are ever sent:
   - Update Item, for the description. A description is replaced only on an item Krusgraph built (its plan marker
     stays) or on an item with no description. Any other item keeps its own words, and the card's text is offered to
     copy.
   - Apply Tags, for tags that already exist, added by id. Tags are never removed, and an item gets at most 10.
4. **Handover files for everyone else** (`handover.py`, `purview.py`):
   - `handover/fabric-admin.md`: tags to create, the domain, and assigning the workspace;
   - `handover/endorsement.md`: the evidence for a reviewer;
   - `handover/purview.json`: governance domain, data product, glossary terms and data quality rules in Purview's
     rule types;
   - `contracts/<product>.odcs.yaml`.

   Each file names who must approve. Nothing in them is sent.

## Who may do what

All pages were read on Microsoft Learn on 17 November 2026; each page's own date is in brackets.

| Action | API | Who | Scope | What Krusgraph does |
|---|---|---|---|---|
| Item description | `PATCH /v1/workspaces/{ws}/items/{id}` ([Update Item](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/update-item), updated 2026-11-16): "The caller must have read and write permissions for the item"; "Maximum length is 256 characters" | you | `Item.ReadWrite.All` or `<type>.ReadWrite.All` | writes it after the dry run |
| List the tenant's tags | `GET /v1/tags` ([List Tags](https://learn.microsoft.com/en-us/rest/api/fabric/core/tags/list-tags), 2026-09-15): 25 requests a minute | no role named | `Tag.Read.All` | reads it if the token has it. **The apps do not hold it today**, so tag ids come from tags already on the workspace's items |
| Apply or remove tags on an item | `POST .../items/{id}/applyTags`, `/unapplyTags` ([Apply Tags](https://learn.microsoft.com/en-us/rest/api/fabric/core/tags/apply-tags), 2026-09-15): "contributor or higher role on the workspace"; 10 per item ([tags overview](https://learn.microsoft.com/en-us/fabric/governance/tags-overview), 2026-03-11) | you (Contributor+) | `ItemMetadata.ReadWrite.All` or `Item.ReadWrite.All` | applies tags that exist, only adds |
| Create tenant or domain tags | `POST /v1/admin/tags/bulkCreateTags` ([Bulk Create Tags](https://learn.microsoft.com/en-us/rest/api/fabric/admin/tags/bulk-create-tags), 2026-09-15): "administrator rights such as Fabric administrator"; a domain admin creates domain tags in the admin portal ([tags-define](https://learn.microsoft.com/en-us/fabric/governance/tags-define), 2025-09-04); names of at most 40 characters | Fabric admin (domain admin in the portal) | `Tenant.ReadWrite.All` | handover |
| Create a domain or subdomain | `POST /v1/admin/domains` with `parentDomainId` for a subdomain ([Create Domain](https://learn.microsoft.com/en-us/rest/api/fabric/admin/domains/create-domain), 2026-11-09): "The caller must be a Fabric administrator". A domain admin may create subdomains in the portal ([domains](https://learn.microsoft.com/en-us/fabric/governance/domains), 2025-05-01) | Fabric admin | `Tenant.ReadWrite.All` | handover |
| Assign a workspace to a domain | `POST /v1/workspaces/{ws}/assignToDomain` ([Assign To Domain](https://learn.microsoft.com/en-us/rest/api/fabric/core/workspaces/assign-to-domain), 2026-09-15): "contributor permissions or be a domain Admin" and "workspace admin role". Domain contributors are everyone by default ([domains](https://learn.microsoft.com/en-us/fabric/governance/domains)) | workspace admin who is a domain contributor | `Workspace.ReadWrite.All` | handover. The apps do not hold this scope, and adding it is Gustav's decision |
| Bulk-assign workspaces | `POST /v1/admin/domains/{id}/assignWorkspaces` ([by ids](https://learn.microsoft.com/en-us/rest/api/fabric/admin/domains/assign-domain-workspaces-by-ids), 2026-09-15) | Fabric admin | `Tenant.ReadWrite.All` | handover |
| Promote | no REST API: the Fabric and Power BI REST tables of contents have no endorse, certify or promote entry. Item settings only ([promote and certify](https://learn.microsoft.com/en-us/fabric/fundamentals/endorsement-promote-certify), 2024-07-11): "you must have write permissions" | a person with write permission | none | **never**: shows the evidence instead |
| Certify, master data | the same: "Only authorized reviewers (defined by the Fabric administrator) can certify items"; certification can be delegated to domain admins ([endorsement overview](https://learn.microsoft.com/en-us/fabric/governance/endorsement-overview)) | a named reviewer | none | **never** |
| Owner or contact | no API found: Update Item has only displayName and description | none | none | puts the owner in the description, the contract and the handover |
| Find items | `POST /v1/catalog/search` ([Catalog Search](https://learn.microsoft.com/en-us/rest/api/fabric/core/catalog/search), preview, 2026-11-16): searches display name, workspace name and description, not tags; returns only what the caller can access | you | `Catalog.Read.All` | not called: the description is what makes an item findable |

OneLake catalog: the item details pane shows the description, owner, tags and endorsement; Explore filters by tag and
domain, and lists items "you have access to, or can directly request access to"
([explore](https://learn.microsoft.com/en-us/fabric/governance/onelake-catalog-explore), 2026-10-08).

### Microsoft Purview Unified Catalog

Every Purview data governance page opened on 17 November 2026 (for example
[Unified Catalog](https://learn.microsoft.com/en-us/purview/unified-catalog), updated 2026-11-12) still carries this
notice: "Microsoft Purview Unified Catalog and classic Microsoft Purview data governance capabilities (formerly Azure
Purview) are being retired. … existing capabilities will remain in maintenance mode through November 12, 2027." So
Krusgraph sends nothing to Purview. For a customer who still uses it, the requests are ready in `handover/purview.json`.

| Action | API (public preview) | Who |
|---|---|---|
| Governance domain | `POST {endpoint}/datagovernance/catalog/businessdomains?api-version=2026-03-20-preview` | Governance Domain Creator |
| Data product, glossary terms | `POST .../catalog/dataProducts`, `.../catalog/terms` ([data products](https://learn.microsoft.com/en-us/rest/api/purview/purview-unified-catalog/data-products/create?view=rest-purview-purview-unified-catalog-2026-03-20-preview)) | Data Product Owner or Data Steward ([roles](https://learn.microsoft.com/en-us/purview/data-governance-roles-permissions), 2026-11-12) |
| Data quality rules | `PUT .../datagovernance/quality/business-domains/{bd}/data-products/{dp}/data-assets/{da}/rules/{id}?api-version=2026-01-12-preview` ([Create Rules](https://learn.microsoft.com/en-us/rest/api/purview/purviewdataquality/create-rules/create-rules)); the asset's metadata must exist first | Data Quality Steward (with Governance Domain Reader and Data Product Owner) |

Purview documents authentication with a service principal ("client_credentials",
[tutorial](https://learn.microsoft.com/en-us/purview/data-gov-api-rest-data-plane)) and scope
`https://purview.azure.net/.default`. Krusgraph acts as the signed-in user, so it does not call these APIs.

Purview's rule list ([data quality rules](https://learn.microsoft.com/en-us/purview/unified-catalog-data-quality-rules),
2026-11-12) maps to Krusgraph's rules like this:

| Krusgraph rule | Purview rule |
|---|---|
| single-column unique key | "Unique values" |
| composite unique key | "Duplicate rows" (API type `Duplicate`) |
| each key column | "Empty/blank fields" |
| no orphans | "Table lookup" ("The reference table or data asset must belong to the same governance domain") |
| rows kept after a join | none: Purview's Custom (SQL) rules are row predicates. Krusgraph's own check keeps this rule |

### Per role, in short

- **You (Contributor or Member):** item descriptions; apply or remove existing tags; promote in the portal.
- **Workspace admin:** also assign the workspace to a domain, if a domain contributor.
- **Domain admin (portal):** domain tags, subdomains, assigning workspaces; certifies when certification is delegated.
- **Fabric admin:** every `/v1/admin` tag and domain API; decides who may certify.
- **Purview steward roles:** as in the Purview table above. Purview is preview and retiring.

### Unverified

- Whether a domain admin can call the tag admin REST APIs (the pages name only the Fabric administrator).
- What "contributor permissions" means on Assign To Domain (read here as domain contributor).
- Whether Purview's APIs accept a delegated user token.
- The API `type` strings for Purview rules other than `Duplicate`.
- Whether List Items returns each item's tags (the code uses them when present).
- The page behind aka.ms/DG-Deprecation (it could not be opened from this session).

## Using it

- **MCP:** `publish_catalog(workspace, source, schema, owner=…, items=[…])` is a dry run. It answers the cards, the
  diff, `confirm`, `undo` and the handover. `publish_catalog(…, dry_run=false, confirm=<the dry run's>)` writes.
- **Workload:** Data product page, **Publish to OneLake catalog**, then **Prepare (nothing is written)**. Check the
  changes and tick that you checked them, then **Write N changes as me**. The handover files download from the same
  step.

## The guard

- A write needs `dry_run=false`, the dry run's `confirm` and a workspace listed in
  `KRUSGRAPH_CATALOG_WRITE_WORKSPACES`. The confirm is a hash of exactly the writes shown, so if an item changed since
  the dry run, the write is refused.
- The list is the operator's: empty means no workspace. While this is tested, it holds only Kruse Consulting's demo
  workspace.
- No new Entra permission and no manifest change: Update Item and Apply Tags are covered by `Item.ReadWrite.All`, which
  the apps already hold.

## How to undo

Every write answer carries `undo`: Update Item with the description that was there before, and Unapply Tags with the
ids that were added. Send them as the same person, or put the description back in the item's settings and remove the
tags in Fabric. Nothing is deleted, and endorsement is never touched.

## Decisions for Gustav

1. Whether to add `Tag.Read.All` to the apps, so tags can be found by name. This is an Entra change and needs-gustav.
2. Whether to add `Workspace.ReadWrite.All`, so the workspace admin can assign the domain from the step. It is not
   proposed, because it also allows changing workspaces.
3. Which demo workspace id goes in `KRUSGRAPH_CATALOG_WRITE_WORKSPACES` on the hosted service.
4. The first live run in that workspace with synthetic data. The tool status says "not run against Fabric" until then.
