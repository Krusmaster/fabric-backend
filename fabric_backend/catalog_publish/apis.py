"""CA1: what each API allows and who may call it, from Microsoft Learn, every page opened on 17 November 2026 (the
page's own date in SOURCES). Nothing here is assumed: what a page does not say is marked Unverified in
docs/CATALOG-ACCELERATOR.md."""
from __future__ import annotations

READ_ON = "2026-11-17"
LEARN = "https://learn.microsoft.com/en-us"
FABRIC_DOCS = "https://learn.microsoft.com/en-us/fabric/governance"

SOURCES = {
    "update_item": (f"{LEARN}/rest/api/fabric/core/items/update-item", "updated 2026-11-16"),
    "list_tags": (f"{LEARN}/rest/api/fabric/core/tags/list-tags", "updated 2026-09-15"),
    "apply_tags": (f"{LEARN}/rest/api/fabric/core/tags/apply-tags", "updated 2026-09-15"),
    "unapply_tags": (f"{LEARN}/rest/api/fabric/core/tags/unapply-tags", "updated 2026-09-15"),
    "bulk_create_tags": (f"{LEARN}/rest/api/fabric/admin/tags/bulk-create-tags", "updated 2026-09-15"),
    "tags_overview": (f"{FABRIC_DOCS}/tags-overview", "ms.date 2026-03-11"),
    "tags_define": (f"{FABRIC_DOCS}/tags-define", "ms.date 2025-09-04"),
    "endorsement": (f"{LEARN}/fabric/fundamentals/endorsement-promote-certify", "ms.date 2024-07-11"),
    "endorsement_overview": (f"{FABRIC_DOCS}/endorsement-overview", "ms.date 2024-07-11"),
    "fabric_rest_toc": (f"{LEARN}/rest/api/fabric/toc.json", "read 2026-11-17: no endorse, certify or promote entry"),
    "create_domain": (f"{LEARN}/rest/api/fabric/admin/domains/create-domain", "updated 2026-11-09"),
    "assign_workspaces_by_ids": (f"{LEARN}/rest/api/fabric/admin/domains/assign-domain-workspaces-by-ids", "updated 2026-09-15"),
    "list_domains": (f"{LEARN}/rest/api/fabric/core/domains/list-domains", "updated 2026-09-15"),
    "assign_to_domain": (f"{LEARN}/rest/api/fabric/core/workspaces/assign-to-domain", "updated 2026-09-15"),
    "domains": (f"{FABRIC_DOCS}/domains", "ms.date 2025-05-01"),
    "catalog_search": (f"{LEARN}/rest/api/fabric/core/catalog/search", "updated 2026-11-16, preview"),
    "catalog_explore": (f"{FABRIC_DOCS}/onelake-catalog-explore", "ms.date 2026-10-08"),
    "catalog_item_details": (f"{FABRIC_DOCS}/onelake-catalog-item-details", "ms.date 2026-10-08"),
    "purview_unified_catalog": (f"{LEARN}/purview/unified-catalog", "updated 2026-11-12, retirement notice"),
    "purview_api_overview": (f"{LEARN}/rest/api/purview/unified-catalog-api-overview", "2026-04-30, public preview"),
    "purview_data_products": (f"{LEARN}/rest/api/purview/purview-unified-catalog/data-products/create"
                              "?view=rest-purview-purview-unified-catalog-2026-03-20-preview", "updated 2026-05-11"),
    "purview_auth": (f"{LEARN}/purview/data-gov-api-rest-data-plane", "updated 2026-11-12"),
    "purview_roles": (f"{LEARN}/purview/data-governance-roles-permissions", "updated 2026-11-12"),
    "purview_dq_rules": (f"{LEARN}/purview/unified-catalog-data-quality-rules", "updated 2026-11-12"),
    "purview_dq_api": (f"{LEARN}/rest/api/purview/purviewdataquality/create-rules/create-rules"
                       "?view=rest-purview-purviewdataquality-2026-01-12-preview", "updated 2026-04-23, public preview"),
}

# ED3: quoted verbatim from learn.microsoft.com/en-us/purview/unified-catalog ("Learn about Microsoft Purview Unified
# Catalog", ms.date 2026-10-13, updated 2026-11-12, read 21 November 2026), its "Retirement of Microsoft Purview data
# governance capabilities only" notice; nothing added. A test keeps it word for word.
PURVIEW_RETIRING_SOURCE = "https://learn.microsoft.com/en-us/purview/unified-catalog"
PURVIEW_RETIRING_READ = "page dated 2026-10-13, updated 2026-11-12, read 21 November 2026"
PURVIEW_RETIRING = ("Microsoft Purview Unified Catalog and classic Microsoft Purview data governance capabilities (formerly "
                    "Azure Purview) are being retired. Microsoft is consolidating its data governance capabilities in "
                    "Microsoft Fabric. New Microsoft Purview data governance accounts can no longer be created, and existing "
                    "data governance capabilities will remain in maintenance mode through November 12, 2027.")

# Who may do what, per action. `by`: you (the signed-in user, as Krusgraph writes), fabric_admin, domain_admin,
# workspace_admin, reviewer (a certifier the Fabric admin named), purview_* (Unified Catalog roles). `krusgraph`: what
# Krusgraph does with it.
ROLES = [
    {"action": "Set an item's description", "api": "PATCH /v1/workspaces/{ws}/items/{id} (Update Item)",
     "who": "read and write permission on the item", "by": "you",
     "scopes": "Item.ReadWrite.All or <itemType>.ReadWrite.All", "limit": "256 characters", "source": "update_item",
     "krusgraph": "writes it after the dry run (descriptions of items it built, of the Krusgraph Model item itself, or "
                  "of items with none)"},
    {"action": "List the tenant's tags (to find a tag's id)", "api": "GET /v1/tags (List Tags)",
     "who": "no role named", "by": "you", "scopes": "Tag.Read.All", "limit": "25 requests a minute",
     "source": "list_tags", "krusgraph": "reads it when the token has Tag.Read.All; the apps do not ask for it today, "
                                         "so tag ids come from tags already on the workspace's items"},
    {"action": "Apply or remove existing tags on an item", "api": "POST .../items/{id}/applyTags, /unapplyTags",
     "who": "Contributor or higher on the workspace", "by": "you",
     "scopes": "ItemMetadata.ReadWrite.All or Item.ReadWrite.All", "limit": "10 tags per item, by id",
     "source": "apply_tags", "krusgraph": "applies the tags that exist, only adds, never removes"},
    {"action": "Create tenant tags, or domain tags", "api": "POST /v1/admin/tags/bulkCreateTags",
     "who": "Fabric administrator (REST); a domain admin creates domain tags in the admin portal", "by": "fabric_admin",
     "scopes": "Tenant.ReadWrite.All", "limit": "40 characters a name", "source": "bulk_create_tags",
     "krusgraph": "hands over the request; never holds Tenant.ReadWrite.All"},
    {"action": "Create a domain or subdomain", "api": "POST /v1/admin/domains (parentDomainId for a subdomain)",
     "who": "Fabric administrator (a domain admin may create subdomains in the portal)", "by": "fabric_admin",
     "scopes": "Tenant.ReadWrite.All", "limit": "name 40, description 256 characters", "source": "create_domain",
     "krusgraph": "hands over the proposal"},
    {"action": "Assign a workspace to a domain", "api": "POST /v1/workspaces/{ws}/assignToDomain",
     "who": "workspace admin who is also a domain contributor (everyone by default) or domain admin", "by": "workspace_admin",
     "scopes": "Workspace.ReadWrite.All", "limit": "one workspace", "source": "assign_to_domain",
     "krusgraph": "hands over the step: the apps do not hold Workspace.ReadWrite.All (adding it is Gustav's decision)"},
    {"action": "Assign workspaces to a domain in bulk", "api": "POST /v1/admin/domains/{id}/assignWorkspaces",
     "who": "Fabric administrator", "by": "fabric_admin", "scopes": "Tenant.ReadWrite.All",
     "limit": "overrides earlier assignments", "source": "assign_workspaces_by_ids", "krusgraph": "hands over the request"},
    {"action": "Promote an item", "api": "none: item settings in Fabric only", "who": "write permission on the item",
     "by": "you", "scopes": "-", "limit": "-", "source": "endorsement",
     "krusgraph": "never: shows the evidence a person needs; endorsement stays a person's decision"},
    {"action": "Certify an item, or mark it master data", "api": "none: item settings in Fabric only",
     "who": "a reviewer the Fabric administrator named (or the domain's, when delegated), with write permission",
     "by": "reviewer", "scopes": "-", "limit": "-", "source": "endorsement", "krusgraph": "never"},
    {"action": "Set the owner or contact", "api": "none found (Update Item has displayName and description only)",
     "who": "-", "by": "you", "scopes": "-", "limit": "-", "source": "update_item",
     "krusgraph": "keeps the owner on the card, in the contract and the handover files; never in a description (W3)"},
    {"action": "Find items in the catalog", "api": "POST /v1/catalog/search (preview)",
     "who": "returns only what the caller can access", "by": "you", "scopes": "Catalog.Read.All",
     "limit": "searches name, workspace name and description; not tags", "source": "catalog_search",
     "krusgraph": "not called: the description is what makes an item findable"},
    {"action": "Create a governance domain in Purview", "api": "POST {purview}/datagovernance/catalog/businessdomains "
                                                           "(2026-03-20-preview)",
     "who": "Governance Domain Creator", "by": "purview_domain_creator", "scopes": "https://purview.azure.net/.default "
                                                                                 "(documented with a service principal)",
     "limit": "preview; Purview is retiring", "source": "purview_api_overview", "krusgraph": "hands over the request"},
    {"action": "Create a data product and glossary terms in Purview", "api": "POST {purview}/datagovernance/catalog/"
                                                                         "dataProducts, /terms (2026-03-20-preview)",
     "who": "Data Product Owner or Data Steward in the governance domain", "by": "purview_steward",
     "scopes": "https://purview.azure.net/.default", "limit": "preview; Purview is retiring",
     "source": "purview_data_products", "krusgraph": "hands over the requests"},
    {"action": "Create data quality rules in Purview", "api": "PUT {purview}/datagovernance/quality/business-domains/"
                                                             "{bd}/data-products/{dp}/data-assets/{da}/rules/{id} "
                                                             "(2026-01-12-preview)",
     "who": "Data Quality Steward (with Governance Domain Reader and Data Product Owner); the asset must exist first",
     "by": "purview_dq_steward", "scopes": "https://purview.azure.net/.default", "limit": "preview; Purview is retiring",
     "source": "purview_dq_rules", "krusgraph": "hands over the rules in Purview's rule types"},
]

WHO = {
    "you": "you (the signed-in person)",
    "workspace_admin": "a workspace admin who is a domain contributor, or a domain admin",
    "fabric_admin": "a Fabric administrator (domain tags: also a domain admin, in the admin portal)",
    "reviewer": "a person: Promoted by anyone with write permission, Certified only by a reviewer the Fabric admin named",
    "purview_domain_creator": "a Purview Governance Domain Creator",
    "purview_steward": "a Purview Data Product Owner or Data Steward",
    "purview_dq_steward": "a Purview Data Quality Steward",
}
