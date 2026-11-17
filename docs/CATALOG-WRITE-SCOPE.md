# Catalog write: the Tag.Read.All question and the demo workspace

17 November 2026, round W14. This is an investigation only. No permission was added, `KRUSGRAPH_CATALOG_WRITE_WORKSPACES`
was not set, and nothing was written to Fabric. It covers the two decisions that CA1's live catalog write is waiting
for (`docs/CATALOG-ACCELERATOR.md`, "Decisions for Gustav", 1 and 3).

The sources are Microsoft Learn pages, read on 17 November 2026. "Updated" is the date each page gives.

## 1. What Tag.Read.All grants

| What | Source | What it says |
|---|---|---|
| List Tags, `GET https://api.fabric.microsoft.com/v1/tags` | [List Tags](https://learn.microsoft.com/en-us/rest/api/fabric/core/tags/list-tags), updated 2026-09-15 | "Returns a list of all the tenant's tags." "Required Delegated Scopes: Tag.Read.All". "Maximum 25 requests per one minute per principal." Supported identities: user, service principal and managed identity. The page has no Permissions section, so it names no workspace role. |
| Apply Tags, `POST …/workspaces/{ws}/items/{id}/applyTags` | [Apply Tags](https://learn.microsoft.com/en-us/rest/api/fabric/core/tags/apply-tags), updated 2026-09-15 | "The caller must have *contributor* or higher role on the workspace." Scopes: `ItemMetadata.ReadWrite.All`, or `Item.ReadWrite.All`, or `<itemType>.ReadWrite.All`. The body is `tags`, an array of tag **ids**. |
| Unapply Tags, `…/unapplyTags` | [Unapply Tags](https://learn.microsoft.com/en-us/rest/api/fabric/core/tags/unapply-tags) | Same role and scopes as Apply Tags. |
| Get Item and List Items | [Get Item](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/get-item), updated 2026-11-16 | "tags \| ItemTag[] \| List of applied tags", each with "id" and "displayName". This only shows tags that are already applied to an item. |
| Admin List Tags, `GET /v1/admin/tags` | [Admin - List Tags](https://learn.microsoft.com/en-us/rest/api/fabric/admin/tags/list-tags), updated 2026-09-15 | "Returns a list of all the tenant's tags." "Required Delegated Scopes: Tenant.Read.All or Tenant.ReadWrite.All". The page has no Permissions section. |

**In plain words:** `Tag.Read.All` lets the app read the names and ids of every tag defined in the tenant, as the
signed-in user. It does not let the app create, apply or remove tags. It reads no data and no item content. Applying
tags is already covered by `Item.ReadWrite.All`, which the apps hold.

**Does it need admin consent?** Microsoft does not document this. The [scopes article](https://learn.microsoft.com/en-us/rest/api/fabric/articles/scopes)
(ms.date 2025-02-03) has no admin-consent column, and neither the List Tags page nor a Learn search says either way.
In practice it depends on two things:

- the scope's type on the Power BI / Fabric service principal ("Admin" or "User");
- each customer tenant's user-consent settings.

Gustav can read the type without changing anything (step 2 of the checklist). Many tenants require admin consent for
any new permission. So a new scope means each customer's administrator consents again, and users reconnect.

## 2. What works without it

CA1 already works without `Tag.Read.All` (`fabric_backend/catalog_publish/`):

1. **Tags already on the workspace's items.** List Items and Get Item return each item's applied tags with their ids.
   The step matches a wanted tag by name against those and applies it by id. Today this is the default.
2. **Only the tags the product card names.** The step applies those whose ids it finds through option 1. It lists the
   rest as missing and puts them in the handover file for an administrator (`missing_tags`). Today the card's
   tags come from the plan. Letting the person type the tag names is a small change, but it is not built.
3. **Skip tags.** The description is written, and tags go only to the handover file. Nothing is lost: the description
   is what makes an item findable in Catalog Search, which does not search tags.
4. **Admin List Tags** (`Tenant.Read.All`) would find every tag, but it is an admin-level scope. It is a worse trade
   than `Tag.Read.All`, so it is not proposed.

What is lost without it: a tag that exists in the tenant but is not on any item in the workspace yet. That tag cannot
be found by name, so the first item cannot get it from Krusgraph. An administrator applies it once in Fabric, and from
then on option 1 finds it.

## 3. Recommendation (least privilege)

**Do not add `Tag.Read.All` now.** Run the first live write with what the apps already hold: option 1, with option 3 as
the fallback. Revisit it only if pilots repeatedly hit a tag that exists but is unused in the workspace. It is a
read-only scope, so it is a small step if needed. But it would still be a new consent prompt for every customer.
It is also an Entra change (`needs-gustav`) and a change to the directory listing's permission list.

## 4. The demo workspace for `KRUSGRAPH_CATALOG_WRITE_WORKSPACES`

**Which one:** a workspace in Kruse Consulting's own Fabric tenant, made for the demo. It holds only the synthetic shop
data (`fabric_backend/seed.py`) and what Krusgraph built from it. **Never** use a customer's workspace or a customer's
tenant, and never one with real data. The id is a tenant-specific value. It goes only into the container app's
settings, never into this repository (CONTRIBUTING.md, "What never goes into the repository").

**How to verify it before setting it:**

1. In Fabric, open the workspace and check:
   - its name says it is the demo (for example `krusgraph-demo`);
   - the tenant is Kruse Consulting's: the account menu shows the tenant;
   - the only lakehouse is the demo shop data (seven tables: `customers`, `orders`, `order_items` and so on).
2. Copy the id from the address bar (`/groups/<id>/`). Compare it with
   `az rest --method get --url https://api.fabric.microsoft.com/v1/workspaces/<id> --resource https://api.fabric.microsoft.com`,
   whose `displayName` must be the same name. This is a read and changes nothing.
3. Check who is a member: only Kruse Consulting accounts.

**Setting it** is a deployment change (the container app's environment). It belongs to whoever owns `deploy/` (DP1
today) and needs Gustav's yes. It is described here and not done: one id, no list. An empty value means no workspace
may be written.

## 5. What a first live run writes, and how to undo it

In the demo workspace, from the Model item's Data product page: **Publish to OneLake catalog**, then **Prepare (nothing
is written)**, then tick, then **Write N changes as me**. Only two kinds of call are sent, as the signed-in user:

| Call | What changes | Undo |
|---|---|---|
| Update Item (`PATCH …/items/{id}`, `description`) | Each item Krusgraph built (or one with no description) gets the product card's text, at most 256 characters. The plan marker stays at the end. | The answer's `undo` holds the old description; send it as the same person, or paste it back in the item's settings. |
| Apply Tags | Tags that already exist, found by option 1, at most 10 per item. Tags are only ever added. | The answer's `undo` holds Unapply Tags with exactly the ids added; or remove them in the item's settings. |

The run does not delete, endorse, promote or certify anything, and it does not create tags, domains or workspaces.
The confirm is a hash of exactly the writes shown, so a changed item refuses the write. Before running it, save the dry
run's answer (it has the before values).

## 6. Checklist for Gustav

1. **Decide:** keep `Tag.Read.All` out for now (the recommendation), or add it (Entra change, `needs-gustav`, a new
   consent for every customer).
2. **Optional, read-only:** see whether the scope would need admin consent:
   `az ad sp show --id 00000009-0000-0000-c000-000000000000 --query "oauth2PermissionScopes[?value=='Tag.Read.All'].{type:type,admin:adminConsentDisplayName}" -o table`.
   `type` `Admin` means admin consent is always needed. `User` means it depends on the tenant's settings.
3. **Pick the demo workspace** in Kruse Consulting's tenant and verify it (section 4, steps 1 to 3). Never a customer's.
4. **Set `KRUSGRAPH_CATALOG_WRITE_WORKSPACES`** to that one id on the container app, through the deploy owner. Not in
   the repository.
5. **First live run:**
   - in the demo workspace, Prepare, then save the dry run;
   - write;
   - check the descriptions and tags in the OneLake catalog;
   - undo one item with `undo`, to prove that undo works.
6. **Record the result** in `docs/LIVE-TEST.md`. Then set the tool's status from "not run against Fabric" to what was
   seen.
