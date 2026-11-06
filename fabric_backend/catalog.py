"""OneLake catalog draft (round n116): what Krusgraph knows about a plan (table roles, keys, relationships with their rule
and, when counted, their counts, the ontology's entity names, the proposed domains) as the description and the tags it
would set on each Fabric item the plan touches, with the exact REST calls. A draft only: nothing here calls Fabric, and
no tool sends these calls.

What can be set today, from Microsoft's public sources (read 6 November 2026; learn.microsoft.com itself could not be
opened from the session that wrote this, so the pages' sources were read):
- microsoft/fabric-rest-api-specs 6f817cb (2 Nov 2026), the source of learn.microsoft.com/rest/api/fabric:
  - Items - Update Item (platform/swagger.json, Items_UpdateItem; /rest/api/fabric/core/items/update-item):
    PATCH /v1/workspaces/{workspaceId}/items/{itemId}, body UpdateItemRequest {displayName, description}: "The item
    description. Maximum length is 256 characters." "The caller must have *read and write* permissions for the item";
    scopes "Generic scope: Item.ReadWrite.All / Specific scope: *itemType*.ReadWrite.All". "This API is supported for a
    number of item types": an item type gets a call here only when the specs also have its own Items_Update<Type>
    operation with a description field (UPDATABLE below). The SQL analytics endpoint has none (its only PATCH is
    settings/sqlAudit), so it gets nothing.
  - Tags (platform/swagger.json; /rest/api/fabric/core/tags/...): Tags_ListTags GET /v1/tags (Tag.Read.All; "Maximum
    25 requests per one minute per principal"); Tags_ApplyTags POST /v1/workspaces/{workspaceId}/items/{itemId}/applyTags
    with ApplyTagsRequest {"tags": [...]}, "The array of tag IDs" (uuid): tags are applied by id, not by name; "The
    caller must have *contributor* or higher role on the workspace"; scopes "ItemMetadata.ReadWrite.All or ...
    Item.ReadWrite.All / *itemType*.ReadWrite.All". No preview note on either.
  - Tags_BulkCreateTags (admin/swagger.json) POST /v1/admin/tags/bulkCreateTags, {"createTagsRequest":
    [{"displayName"}]} with an optional scope (Tenant or Domain): "The caller must have administrator rights such as
    Fabric administrator", Tenant.ReadWrite.All; "The display name cannot contain more than 40 characters."
  - Lakehouse tables (lakehouse/swagger.json, Tables_ListTables, a preview API): a table has type, name, location and
    format; UpdateLakehouseRequest has displayName and description only. No public API sets a table's description or
    tags, so table-level knowledge goes into the item's description and stays in data_dictionary.
  - Catalog_Search POST /v1/catalog/search (preview, Catalog.Read.All): "search" matches "the display name, workspace
    display name, and description"; the filter takes Type and WorkspaceId only, so tags do not make an item findable
    there, the description does.
  - No endorsement operation exists in the specs; endorsement (promoted, certified) is left out.
- MicrosoftDocs/fabric-docs 28d4ff3 (6 Nov 2026): governance/tags-overview.md (ms.date 03/11/2026: "Fabric admins
  create tenant-level tags; Fabric or domain admins create domain-level tags", "An item or workspace can have a maximum
  of 10 tags"), tags-define.md (09/04/2025: "Tag names can be up to 40 characters long"), tags-apply.md (04/07/2026),
  onelake-catalog-item-details.md and onelake-catalog-explore.md (10/08/2026: the item's description is "displayed
  under the item name"; "Use the tags selector to display items tagged with the tags you select").
- microsoft/mcp 42c66a2 (6 Nov 2026), servers/Fabric.Mcp.Server/README.md: `core_search-catalog` "Calls the Catalog
  Search API" (Catalog.Read.All); `core_update-item` is one PATCH .../items/{itemId} and does not change tags; no tool
  applies tags. Krusgraph sits beside it: this draft gives the descriptions those tools and the catalog then find.

The descriptions are generated from the plan only: table names, the ontology's entity names, counts and rule names. No
row value, no column name (so no column the privacy rules mask is ever named), no statement about quality beyond the
counts validate_plan returned.
"""
from __future__ import annotations

from . import domains as _domains
from . import graphs as _graphs
from .ontology import entity_name

FABRIC = "https://api.fabric.microsoft.com"
DESCRIPTION_MAX = 256          # UpdateItemRequest.description
TAG_MAX = 40                   # BulkCreateTags displayName
TAGS_PER_ITEM = 10             # tags-overview.md
PROVENANCE_TAG = "Krusgraph"

# Item types with their own documented update operation (fabric-rest-api-specs 6f817cb): {type: (operation, path, type scope)}.
UPDATABLE = {
    "Lakehouse": ("Items_UpdateLakehouse", "lakehouses", "Lakehouse.ReadWrite.All"),
    "Warehouse": ("Items_UpdateWarehouse", "warehouses", "Warehouse.ReadWrite.All"),
    "SQLDatabase": ("Items_UpdateSQLDatabase", "sqlDatabases", "SQLDatabase.ReadWrite.All"),
    "MirroredDatabase": ("Items_UpdateMirroredDatabase", "mirroredDatabases", "MirroredDatabase.ReadWrite.All"),
    "SnowflakeDatabase": ("Items_UpdateSnowflakeDatabase", "snowflakeDatabases", None),
    "MirroredAzureDatabricksCatalog": ("Items_UpdateMirroredAzureDatabricksCatalog", "mirroredAzureDatabricksCatalogs",
                                       "MirroredAzureDatabricksCatalog.ReadWrite.All"),
    "MirroredCatalog": ("Items_UpdateMirroredCatalog", "mirroredCatalogs", None),
    "GraphQLApi": ("Items_UpdateGraphQLApi", "graphQLApis", "GraphQLApi.ReadWrite.All"),
    "SemanticModel": ("Items_UpdateSemanticModel", "semanticModels", "SemanticModel.ReadWrite.All"),
    "Notebook": ("Items_UpdateNotebook", "notebooks", "Notebook.ReadWrite.All"),
    "DataPipeline": ("Items_UpdateDataPipeline", "dataPipelines", "DataPipeline.ReadWrite.All"),
}

APIS = [
    {"operation": "Items_UpdateItem", "method": "PATCH", "path": "/v1/workspaces/{workspaceId}/items/{itemId}",
     "sets": "description (at most 256 characters) and displayName of one item",
     "scopes": "Item.ReadWrite.All or <itemType>.ReadWrite.All", "who": "read and write permission on the item",
     "status": "documented, no preview note", "used": True},
    {"operation": "Tags_ListTags", "method": "GET", "path": "/v1/tags", "sets": "nothing: lists the tenant's tags, to find their ids",
     "scopes": "Tag.Read.All", "who": "no role named in the docs", "status": "documented, no preview note", "used": True},
    {"operation": "Tags_ApplyTags", "method": "POST", "path": "/v1/workspaces/{workspaceId}/items/{itemId}/applyTags",
     "sets": "tags on one item, by tag id; at most 10 per item",
     "scopes": "ItemMetadata.ReadWrite.All, Item.ReadWrite.All or <itemType>.ReadWrite.All",
     "who": "Contributor or higher on the workspace", "status": "documented, no preview note", "used": True},
    {"operation": "Tags_BulkCreateTags", "method": "POST", "path": "/v1/admin/tags/bulkCreateTags",
     "sets": "new tenant or domain tags (names of at most 40 characters)", "scopes": "Tenant.ReadWrite.All",
     "who": "a Fabric administrator", "status": "documented, admin API", "used": "only for tags the tenant does not have"},
    {"operation": "Catalog_Search", "method": "POST", "path": "/v1/catalog/search",
     "sets": "nothing: searches display names, workspace names and descriptions (not tags)", "scopes": "Catalog.Read.All",
     "who": "items the caller may see", "status": "preview", "used": "to check afterwards that the items are found"},
]

NOT_SET = [
    {"what": "lakehouse and warehouse tables",
     "why": "tables are not Fabric items: no public API sets a table's description or tags (a lakehouse table has type, "
            "name, location and format); what the plan knows per table goes into the source item's description, in "
            "short, and in full into data_dictionary"},
    {"what": "the T-SQL views of create_views", "why": "views are not Fabric items; they have no description or tags in the catalog"},
    {"what": "the SQL analytics endpoint", "why": "the specs have no update operation for it (its only PATCH is settings/sqlAudit)"},
    {"what": "endorsement (promoted, certified)", "why": "no public REST operation; certifying is for people a Fabric "
                                                         "administrator names, so it is left out"},
    {"what": "Fabric domains", "why": "assigning a workspace to a domain is an admin API (Tenant.ReadWrite.All); the proposed "
                                      "domains appear here as tags, domain_draft has the proposal"},
]

PERMISSIONS = {
    "has_today": "Item.ReadWrite.All (delegated, on the hosted app since 28 October 2026) covers Update Item and Apply Tags "
                 "for a user who is Contributor on the workspace.",
    "new_for_writing": ["Tag.Read.All: to look up the tags' ids (GET /v1/tags), which Apply Tags takes instead of names"],
    "optional": ["Catalog.Read.All: to search the catalog afterwards (Catalog_Search, preview)"],
    "stays_with_the_customer": ["Tenant.ReadWrite.All with a Fabric administrator: creating the tags (bulkCreateTags); "
                                "Krusgraph should not hold it"],
}


# ------------------------------------------------------------------ the facts ------------------------------------

def _in(tables: list[str] | None, name: str) -> bool:
    return tables is None or name.lower() in {t.lower() for t in tables}


def _rules(rules) -> str:
    rs = sorted(set(rules))
    return ", ".join(rs)


def facts(p, validation: dict | None = None, tables: list[str] | None = None) -> dict:
    """What the descriptions are written from: per table its role, entity name and key rule; per relationship its rule
    and, when validate_plan's counts are given, its orphans; the proposed domains. Table and rule names and counts only."""
    an = _graphs.analyze(p)
    roles = an.get("roles", {})
    names = sorted((t.name for t in p.schema if _in(tables, t.name)), key=str.lower)
    keep = set(names)
    rels = [r for r in p.relationships if r.source in keep and r.target in keep]
    counted_keys = {(k["table"], tuple(c.lower() for c in k["columns"])): k for k in (validation or {}).get("keys", [])
                    if isinstance(k.get("rows"), int)}
    counted_rels = {(r["source"], tuple(c.lower() for c in r["columns"]), r["target"]): r for r in (validation or {}).get("relationships", [])
                    if isinstance(r.get("orphans"), int)}
    table_facts = []
    for n in names:
        cols, rule = p.keys.get(n, ([], None))
        k = counted_keys.get((n, tuple(c.lower() for c in cols))) if cols else None
        entry = {"table": n, "entity": entity_name(n), "role": roles.get(n, {}).get("role", "other"),
                 "key_rule": p.label(rule) if cols else None, "key_columns": len(cols)}
        if k is not None:
            entry["key_counted"] = {"rows": k["rows"], "unique": k.get("distinct") == k["rows"] and not k.get("nulls"),
                                    "nulls": k.get("nulls", 0)}
        table_facts.append(entry)
    rel_facts = []
    for r in sorted(rels, key=lambda r: (r.source.lower(), r.target.lower(), [c.lower() for c in r.source_cols])):
        c = counted_rels.get(r.key)
        entry = {"from": r.source, "to": r.target, "from_entity": entity_name(r.source), "to_entity": entity_name(r.target),
                 "rule": p.label(r.rule)}
        if c is not None:
            entry["counted"] = {"rows_with_value": c.get("rows_with_value"), "orphans": c["orphans"]}
        rel_facts.append(entry)
    proposal = _domains.propose_plan(p, validation)
    doms = [{"name": d["name"], "tables": [t for t in d["tables"] if t in keep]} for d in proposal["domains"]]
    doms = [d for d in doms if d["tables"]]
    return {"tables": table_facts, "relationships": rel_facts, "domains": doms, "counted": validation is not None}


def _checked(f: dict) -> str:
    if not f["counted"]:
        return "not counted against the rows"
    keys = [t for t in f["tables"] if "key_counted" in t]
    rels = [r for r in f["relationships"] if "counted" in r]
    return (f"counted: {sum(1 for t in keys if t['key_counted']['unique'])} of {len(keys)} keys unique, "
            f"{sum(1 for r in rels if r['counted']['orphans'] == 0)} of {len(rels)} relationships without orphans")


def _by_role(f: dict, role: str, entities: bool = False) -> list[str]:
    return [t["entity"] if entities else t["table"] for t in f["tables"] if t["role"] == role]


def _fit(*versions: str) -> str:
    """The first version that fits the 256 characters of UpdateItemRequest.description; the last is cut on a word."""
    for v in versions:
        if len(v) <= DESCRIPTION_MAX:
            return v
    v = versions[-1]
    return v[:DESCRIPTION_MAX - 1].rsplit(" ", 1)[0] + "…"


def _list(xs: list[str]) -> str:
    return ", ".join(xs) if xs else "none"


def _rel_part(f: dict) -> str:
    rs = f["relationships"]
    return f"{len(rs)} relationships ({_rules(r['rule'] for r in rs) or 'none'})"


def _domain_part(f: dict) -> str:
    return "proposed domains: " + _list([d["name"] for d in f["domains"]])


# ------------------------------------------------------------------ descriptions per item ---------------------------

def source_description(f: dict, schema: str) -> str:
    ts, keyed = f["tables"], [t for t in f["tables"] if t["key_rule"]]
    head = f"Schema {schema}, planned by Krusgraph: {len(ts)} tables"
    tail = f"{len(keyed)} with a key ({_rules(t['key_rule'] for t in keyed) or 'none'}); {_rel_part(f)}, {_checked(f)}; {_domain_part(f)}."
    roles = [(r, _by_role(f, r)) for r in ("fact", "dimension", "bridge")]
    named = "; ".join(f"{r}s {', '.join(xs)}" for r, xs in roles if xs)
    counted = "; ".join(f"{len(xs)} {r}s" for r, xs in roles if xs)
    return _fit(f"{head} ({named}), {tail}", f"{head} ({counted}), {tail}", f"{head}, {tail}")


def _entities(f: dict, role: str | None = None) -> list[str]:
    return [t["entity"] for t in f["tables"] if role is None or t["role"] == role]


def item_description(tool: str, item_type: str, f: dict, label: str, names: dict, schemas: dict) -> str:
    rel = f"{_rel_part(f)} from Krusgraph's plan, {_checked(f)}"
    if item_type == "GraphQLApi":
        return _fit(f"API for GraphQL over {label}: types {_list(_entities(f))}; {rel}.",
                    f"API for GraphQL over {label}: {len(f['tables'])} types; {rel}.")
    if item_type == "SemanticModel":
        return _fit(f"Direct Lake model over {label}: facts {_list(_entities(f, 'fact'))}; dimensions "
                    f"{_list(_entities(f, 'dimension'))}; {rel}.",
                    f"Direct Lake model over {label}: {len(f['tables'])} tables; {rel}.")
    keys = sum(1 for t in f["tables"] if t["key_rule"])
    if tool == "create_silver_notebook":
        return _fit(f"Writes de-duplicated silver tables in {schemas['silver']} from {label}: {keys} keys, "
                    f"{len(f['relationships'])} references checked per row, rows without a match go to a quarantine table. "
                    "Generated by Krusgraph from the plan.")
    if tool == "create_gold_views":
        return _fit(f"Creates materialized lake views in {schemas['gold']} over the silver tables of {label}, with the plan's "
                    "keys and relationships as data quality rules. Generated by Krusgraph from the plan.")
    if tool == "create_drift_monitor" and item_type == "Notebook":
        return _fit(f"Compares the tables of {label} with the last plan and sends the changes to a webhook. Generated by Krusgraph.")
    if tool == "create_drift_monitor":
        return _fit(f"Runs the notebook {names['create_drift_monitor']} each night. Generated by Krusgraph.")
    if tool == "pipeline" and item_type == "Notebook":
        return _fit(f"Checks keys and orphans in {schemas['silver']} and the rows and sums of each gold view of {label}; "
                    "raises an error when one does not hold. Generated by Krusgraph.")
    if tool == "pipeline":
        return _fit(f"Runs {names['create_silver_notebook']}, then {names['create_gold_views']}, then {names['pipeline']}_check "
                    f"for {label}; a failed check fails the run. Generated by Krusgraph.")
    return _fit(f"Built by Krusgraph from the plan of {label}.")


# ------------------------------------------------------------------ tags and calls ----------------------------------

def tag_names(f: dict) -> tuple[list[str], list[str]]:
    """The provenance tag and one per proposed domain, each at most 40 characters; at most 10. Returns (kept, left out)."""
    names = [PROVENANCE_TAG] + [("domain: " + d["name"])[:TAG_MAX].rstrip() for d in f["domains"]]
    names = list(dict.fromkeys(names))
    return names[:TAGS_PER_ITEM], names[TAGS_PER_ITEM:]


def _tag_ref(name: str) -> str:
    return f"<id of tag {name!r} from GET /v1/tags>"


def calls(item_type: str, workspace_id: str, item_id: str, description: str, tags: list[str]) -> list[dict]:
    op, path, scope = UPDATABLE[item_type]
    base = f"{FABRIC}/v1/workspaces/{workspace_id}/items/{item_id}"
    return [
        {"operation": "Items_UpdateItem", "method": "PATCH", "url": base, "body": {"description": description},
         "scopes": "Item.ReadWrite.All" + (f" or {scope}" if scope else ""),
         "same_with": f"{op}: PATCH {FABRIC}/v1/workspaces/{workspace_id}/{path}/{item_id}"},
        {"operation": "Tags_ApplyTags", "method": "POST", "url": base + "/applyTags", "body": {"tags": [_tag_ref(t) for t in tags]},
         "scopes": "ItemMetadata.ReadWrite.All or Item.ReadWrite.All" + (f" or {scope}" if scope else "")},
    ]


def draft(p, info: dict, made: list[dict], names: dict, schemas: dict, validation: dict | None = None,
          tables: list[str] | None = None) -> dict:
    """The catalog draft for the source item and the items in `made` ({tool, type, name}). Deterministic: the same plan,
    names and counts give the same answer."""
    f = facts(p, validation, tables)
    schema = info["schema"]
    label = f"{info['item_name']}.{schema}"
    tags, tags_left = tag_names(f)
    ws = info["workspace_id"]
    items, skipped = [], []

    def one(name: str, item_type: str, tool: str | None, item_id: str | None, description: str) -> None:
        if item_type not in UPDATABLE:
            skipped.append({"item": name, "type": item_type, "why": f"the specs have no update operation for {item_type}"})
            return
        exists = item_id is not None
        items.append({"item": name, "type": item_type, "tool": tool, "exists": exists, "description": description,
                      "description_chars": len(description), "tags": tags,
                      "calls": calls(item_type, ws, item_id or f"<id of {name} once created>", description, tags)})
    one(info["item_name"], info["item_kind"], None, info["item_id"] or None, source_description(f, schema))
    for m in made:
        if m["type"] == "T-SQL":
            continue
        one(m["name"], m["type"], m["tool"], None, item_description(m["tool"], m["type"], f, label, names, schemas))
    out = {
        "summary": (f"{len(items)} item(s) with a description and {len(tags)} tag(s) each; "
                    + ("counts from validate_plan" if f["counted"] else "rules only, not counted (check_rows=true counts)")
                    + "; nothing sent"),
        "items": items,
        "tag_setup": {
            "tags": tags,
            "calls": [{"operation": "Tags_ListTags", "method": "GET", "url": f"{FABRIC}/v1/tags", "scopes": "Tag.Read.All",
                       "why": "Apply Tags takes tag ids: find each tag's id by its displayName (pages with continuationToken)"},
                      {"operation": "Tags_BulkCreateTags", "method": "POST", "url": f"{FABRIC}/v1/admin/tags/bulkCreateTags",
                       "body": {"createTagsRequest": [{"displayName": t} for t in tags]}, "scopes": "Tenant.ReadWrite.All",
                       "why": "only for the tags GET /v1/tags does not list, and only by a Fabric administrator; a domain "
                              "admin can create them as domain tags with \"scope\": {\"type\": \"Domain\", \"domainId\": ...}"}]},
        "not_set": NOT_SET,
        "facts": f,
        "apis": APIS,
        "permissions": PERMISSIONS,
        "find_it": "The OneLake catalog shows the description under the item's name and filters by tag; Catalog_Search "
                   "(preview) and Microsoft's Fabric MCP server's core_search-catalog match the description, not the tags.",
        "sources": "microsoft/fabric-rest-api-specs 6f817cb (2 Nov 2026); MicrosoftDocs/fabric-docs 28d4ff3 governance/tags-*.md, "
                   "onelake-catalog-*.md; microsoft/mcp 42c66a2 servers/Fabric.Mcp.Server/README.md; read 6 Nov 2026",
        "note": "A draft: no tool sends these calls. Review the descriptions and tags, then send them yourself, for example "
                "with Microsoft's Fabric MCP server (core_update-item for the description) or the REST API.",
    }
    if skipped:
        out["skipped"] = skipped
    if tags_left:
        out["tags_left_out"] = {"tags": tags_left, "why": f"an item can have at most {TAGS_PER_ITEM} tags"}
    return out
