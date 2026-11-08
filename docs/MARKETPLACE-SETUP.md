# Selling Krusgraph through Microsoft Marketplace: setup

Round n171, 8 November 2026. The code is in `fabric_backend/marketplace.py` (landing page, connection webhook, the
store) and `fabric_backend/entitlements.py` (the licence check), all **off by default**: with `KRUSGRAPH_MARKETPLACE`
unset no `/marketplace` route exists and nothing on the site or in the tools changes. This page is what the founder
fills in and switches on. Nothing in Partner Center, Entra, Azure or Fabric was created or changed by this round.

It continues `docs/WORKLOAD-LISTING-AND-PAYMENT.md` (n167), sections 2b and 2e; sources `[Ln]` are that page's. The
sources `[Mn]` below were read on learn.microsoft.com on **8 November 2026**; the code builds only what they document.
Prices are not decided and appear nowhere in the code: plans and prices live in Partner Center only.

## 1. What happens, end to end

1. A buyer subscribes in Microsoft Marketplace and presses **Configure account**. Microsoft sends the browser to
   `https://krusgraph.com/marketplace/landing?token=…` [M3].
2. The page sends the buyer to Microsoft Entra to sign in (the site's existing multitenant app, scopes `openid profile`
   only, authorization code flow with PKCE). The purchase token waits in a short-lived, HttpOnly cookie on our own
   domain; it is never logged.
3. Back on `/marketplace/callback`, the server checks the ID token (signature, audience, the issuer of the buyer's own
   tenant, the nonce) [M6][M7], then **resolves** the purchase token with the fulfilment API as the publisher's app
   [M1][M5], and shows offer, plan, quantity, status and the beneficiary's tenant id. No payment details, no names.
4. If the plan waits for activation (status `PendingFulfillmentStart`), the buyer presses **Activate the
   subscription**; the server calls **activate** [M1]. With **auto activation** on a plan the status is already
   `Subscribed`, the page says there is nothing to activate, and Microsoft sends a `Subscribe` webhook [M1][M8].
   An account from a third organisation (neither beneficiary nor purchaser) sees the details but cannot activate.
5. From then on Microsoft calls `https://krusgraph.com/marketplace/webhook` for `Subscribe`, `ChangePlan`,
   `ChangeQuantity`, `Renew`, `Suspend`, `Reinstate` and `Unsubscribe` [M2]. Each call: the bearer token is checked
   (below), the operation is confirmed with **Get operation** [M2][M4], recorded once per operation id, and `ChangePlan`,
   `ChangeQuantity` and `Reinstate` are acknowledged with **Patch operation `Success`** [M4], in the background, after
   the HTTP 200 (Microsoft accepts an unanswered change after 10 seconds [M2]). A call that cannot be confirmed or
   written gets **503**, so Microsoft retries (500 retries over eight hours [M2]); a `ChangePlan` or `ChangeQuantity` is
   never answered with a 4xx, which would mean "rejected" [M2].
6. The licence check (`KRUSGRAPH_ENTITLEMENTS=1`): a creating call with `dry_run=false` (the MCP creating tools, and
   the Fabric editor's **Create**, `/workload/v1/build`) from a tenant without an **active** (`Subscribed`) subscription
   answers `kind: upgrade` with the offer's link in `upgrade_url` and the hint. Reading, checks, drafts and every dry
   run stay free. In Claude's card the Create button shows that message and a button to the offer; in Fabric the
   editor shows it in its error bar (HTTP 402).

### The webhook's token, exactly as Microsoft documents it [M2]

| Claim | Must be |
| --- | --- |
| signature | an Entra signing key of the publisher's tenant (`https://login.microsoftonline.com/<tenant>/discovery/v2.0/keys`) [M6] |
| `iss` | `https://login.microsoftonline.com/<tenant>/v2.0` or `https://sts.windows.net/<tenant>/` (v2.0 and v1.0 tokens) [M6] |
| `tid` | the publisher's tenant id, the one entered in Partner Center (*Microsoft Entra tenant ID*) |
| `aud` | the fulfilment app's id, the one entered in Partner Center (*Microsoft Entra application ID*) |
| `appid` or `azp` | `20e940b3-4c77-4b0b-9a53-9e16a1b010a7`, the Marketplace SaaS API resource; "the token has either of the two claims" |
| `exp`, `nbf` | not expired, already valid (60 seconds of clock skew) |

Anything else is a 401 and nothing is recorded. The webhook URL carries no secret: Microsoft warns that tokens in the
URL may stop the Authorization header from arriving [M2][M9].

### What the store keeps

The Azure Table the entitlement check already reads (`KRUSGRAPH_ENTITLEMENTS_TABLE`):

| PartitionKey | RowKey | Properties |
| --- | --- | --- |
| `marketplace` | the **beneficiary** tenant id (lower case) | `subscription_id`, `offer`, `plan`, `status`, `active`, `updated_at` of the tenant's best subscription, and `subscriptions`: every subscription of that tenant as JSON (id → offer, plan, quantity, status, free trial, test, updated_at) |
| `marketplace-op` | the webhook's operation id | `action`, `subscription_id`, `at` (so a retried call is applied once) |

"Best" is `Subscribed` before `Suspended` before `PendingFulfillmentStart` before `Unsubscribed`, then the latest change;
the tenant is licensed while the best one is `Subscribed`. A webhook operation older than the one already applied to
that subscription (by its `timeStamp`) is ignored. **Not kept:** the buyer's or purchaser's e-mail address, object id,
puid, name, the subscription's display name, any token, anything from the customer's Fabric data. The licence check
reads a tenant's row at most once a minute.

## 2. Entra: which apps

Microsoft recommends two apps: the multitenant one the buyer signs in with, and a **single-tenant** app that alone talks
to the fulfilment API [M3][M5].

### 2a. Sign-in on the landing page: the existing "Krusgraph" app (`ENTRA_CLIENT_ID`)

No new permission. The landing page asks for `openid` and `profile` only (no Microsoft Graph call, so not even
`User.Read`); Microsoft says not to ask for anything that needs admin consent there [M3]. One change:

- **Authentication → Web → Redirect URIs → add** `https://krusgraph.com/marketplace/callback`.

### 2b. The fulfilment app: create it

In the publisher's Entra tenant (the one that holds `krusgraph.com`), **App registrations → New registration** [M5]:

| Setting | Value |
| --- | --- |
| Name | `Krusgraph Marketplace fulfilment` |
| Supported account types | **Accounts in this organizational directory only** (single tenant) [M5] |
| Redirect URI | none |
| Certificates & secrets | **New client secret**; copy the value once, straight into Key Vault or the container app (section 4) |
| API permissions | none |
| Authentication | **Allow public client flows: No** [M5] |

Then register the Marketplace SaaS API's service principal in the same tenant, once [M5]:

```bash
az login --tenant <publisher tenant id>
az ad sp create --id 20e940b3-4c77-4b0b-9a53-9e16a1b010a7
```

The server gets its token with the client credentials flow, scope `20e940b3-4c77-4b0b-9a53-9e16a1b010a7/.default`, from
`https://login.microsoftonline.com/<publisher tenant id>/oauth2/v2.0/token` [M5]. Tokens must come from the **same**
tenant id and application id entered in Partner Center [M5]. A client certificate instead of a secret is not supported
by this code yet.

## 3. Partner Center: the SaaS offer's Technical configuration

Create the **DEV** offer first (section 5). Offer → **Technical configuration** [M9]:

| Partner Center field | What to enter |
| --- | --- |
| **Landing page URL** | `https://krusgraph.com/marketplace/landing` (no `#`, no secret in it [M9]) |
| **Connection webhook** | `https://krusgraph.com/marketplace/webhook` |
| **Microsoft Entra tenant ID** | the publisher's tenant id: Entra → App registrations → *Krusgraph Marketplace fulfilment* → **Directory (tenant) ID** |
| **Microsoft Entra application ID** | that app's **Application (client) ID** |

The same two ids go into `KRUSGRAPH_MARKETPLACE_TENANT_ID` and `KRUSGRAPH_MARKETPLACE_CLIENT_ID`. The DEV and the PROD
offer can use the same app and the same URLs; the store keeps each subscription's `offer` id, so they stay apart.

Plans (n167 planned them, nothing created): `team` public, monthly and annual; `pilot` private, free trial [L11]. Both
must use the same pricing model, flat rate, which cannot be changed after publishing [L11]. **Auto activation** can be
on or off per plan; the code handles both [M8]. Every active plan currently grants every paid feature.

## 4. The server's settings

| Variable | `deploy/krusgraph.json` key | Value |
| --- | --- | --- |
| `KRUSGRAPH_MARKETPLACE` | `marketplace` | `1` (true) switches the routes on |
| `KRUSGRAPH_ENTITLEMENTS` | `entitlements` | `1` (true) switches the licence check on |
| `KRUSGRAPH_MARKETPLACE_TENANT_ID` | `marketplace_tenant_id` | the publisher's tenant id |
| `KRUSGRAPH_MARKETPLACE_CLIENT_ID` | `marketplace_client_id` | the fulfilment app's id |
| `KRUSGRAPH_MARKETPLACE_CLIENT_SECRET_KEYVAULT_URI` | `marketplace_secret_keyvault_uri` | `https://<vault>.vault.azure.net/secrets/<name>` (preferred: survives a full deploy run) |
| `KRUSGRAPH_MARKETPLACE_CLIENT_SECRET` | – | or `secretref:marketplace-secret`, set by `--update` when the container app holds that secret |
| `KRUSGRAPH_MARKETPLACE_OFFER_URL` | `marketplace_offer_url` | the offer's page in Marketplace; the upgrade answer links to it |
| `KRUSGRAPH_ENTITLEMENTS_SOURCE` | `entitlements_source` | `table` |
| `KRUSGRAPH_ENTITLEMENTS_TABLE` | `entitlements_table` | `https://<account>.table.core.windows.net/<table>` |

The container app's identity needs **Storage Table Data Contributor** on that table (the webhook writes; the reader
role of `docs/PRICING-NOTES.md` is not enough) and **Key Vault Secrets User** on the vault for the Key Vault reference.
With `KRUSGRAPH_MARKETPLACE=1` and a setting missing, the server does not start and says which.

Storing the secret without showing it, either way:

```bash
# Key Vault (the vault deploy/krusgraph.sh --key-vault made):
read -rsp "Marketplace-appens klienthemlighet: " MS; echo
az keyvault secret set --vault-name <vault> --name marketplace-client-secret --value "$MS" --output none; unset MS
# or the container app:
read -rsp "Marketplace-appens klienthemlighet: " MS; echo
az containerapp secret set -n krusgraph -g rg-krusgraph --secrets marketplace-secret="$MS" --output none; unset MS
```

`bash deploy/krusgraph.sh --update --dry-run` prints the variables `--update` would set, carries over any of them set
by hand on the app (with the key to add to `deploy/krusgraph.json`, as for the n159 switches), and lists by name only
what is still missing: switches, ids, the secret, the offer URL, the table, the table role and the redirect URI.
`--update` stops before building when the switch is on and no secret exists. A full run (no flag) keeps only the
Entra secret, so with the container-app secret it sets `KRUSGRAPH_MARKETPLACE=0` and prints what to run next; the Key
Vault reference has no such step.

### Switching on and off

- **On:** in `deploy/krusgraph.json` set `"marketplace": true, "entitlements": true` and the keys above, then
  `bash deploy/krusgraph.sh --update --dry-run`, then `bash deploy/krusgraph.sh --update`.
- **Off:** `"marketplace": false` (and/or `"entitlements": false`) and `--update`: the variable becomes `0`, the
  `/marketplace` routes are gone at the next revision, the table and its rows stay. With `entitlements` off nothing
  is gated; with `marketplace` off and `entitlements` on, the check falls back to `docs/PRICING-NOTES.md`'s rules.
- Self-hosted and open-source use: both unset, nothing changes.

## 5. Testing with the DEV offer [L9][L11][M9]

1. Create a **separate DEV offer** (for example `krusgraph-dev`), Technical configuration as in section 3.
2. Plans with a **nominal price** (or zero), the same pricing model as the real offer.
3. **Preview audience:** the founder's own Microsoft or Entra account (up to 10 by hand) [M10].
4. Publish to **preview only**. **Never press Go live on the DEV offer**: that publishes it on the storefront [M10].
5. Buy it with the preview link in a test tenant; the publisher pays test invoices. **Cancel within 72 hours**: the
   refund comes on the next month's invoice [M10]. Microsoft's webhook page also suggests a zero price, or cancelling
   within 24 hours [M2].
6. Check, in order: the landing page shows the plan and the test tenant's id; **Activate** turns the row `Subscribed`
   (or, with auto activation, the `Subscribe` webhook does); a creating call from that tenant runs; a call from
   another tenant gets `kind: upgrade`; cancel in the Azure portal → `Unsubscribe` → upgrade again. *Change plan* and
   *change quantity* are triggered from Microsoft 365 Admin Center [M2].
7. Look at the log lines (`krusgraph.marketplace`): action, subscription id and outcome only.

## 6. What the live site must say before the first subscription

Not changed by this round (the flag is off and nothing is stored yet). Before switching on:

- **/privacy**, the table *What we process*, a new row: "When your organisation subscribes through Microsoft
  Marketplace: your organisation's tenant id, and the subscription's id, offer, plan, quantity, status, whether it is a
  free trial or a test, and when it changed | deciding whether creating items is included for your organisation |
  in our Azure Table Storage while the subscription exists" plus the retention the founder decides for ended ones
  (**nothing deletes rows yet**: an ended subscription's row stays until removed by hand, so either add a clean-up
  or say so; the table's region is the storage account's). And
  one sentence: "We do not keep the buyer's or purchaser's name, e-mail address or user id that Microsoft sends us."
  The sentence "the server stores nothing" must not remain unqualified.
- **/pricing**: the Team plan says it is bought through Microsoft Marketplace (link to the offer) and billed by
  Microsoft; prices only as Partner Center has them. Today the page says "Invoiced" and "Contact us".
- **/terms**: the terms the offer uses (Microsoft's Standard Contract or our own [L9]); the current page is "Preview
  terms".
- **/it** and **/start**: one line that reading and dry runs are free and creating needs the organisation's
  subscription.
- **/support**: how to reach us about a subscription (Microsoft handles billing and refunds).
- `docs/DPA-DRAFT.md`: the subscription row as a processing activity.

## Sources

All read on learn.microsoft.com on **8 November 2026**. "Learn commit" is the `git_commit_id` the page reports.

| # | Title (`ms.date`) | URL | Learn commit |
| --- | --- | --- | --- |
| M1 | SaaS fulfillment Subscription APIs v2 in Microsoft Marketplace (2026-07-22) | https://learn.microsoft.com/partner-center/marketplace-offers/pc-saas-fulfillment-subscription-api | `3d1a72a` |
| M2 | Implementing a webhook on the SaaS service (2026-04-29; "last updated" 2026-07-23) | https://learn.microsoft.com/partner-center/marketplace-offers/pc-saas-fulfillment-webhook | `3d1a72a` |
| M3 | Build the landing page for your transactable SaaS offer (2026-04-29) | https://learn.microsoft.com/partner-center/marketplace-offers/azure-ad-transactable-saas-landing-page | `59e2bde` |
| M4 | SaaS fulfillment operations APIs v2 (2025-03-11) | https://learn.microsoft.com/partner-center/marketplace-offers/pc-saas-fulfillment-operations-api | `60ce816` |
| M5 | Register a SaaS application (2025-01-30) | https://learn.microsoft.com/partner-center/marketplace-offers/pc-saas-registration | `14edc14` |
| M6 | Access tokens in the Microsoft identity platform (2025-05-14) | https://learn.microsoft.com/entra/identity-platform/access-tokens | `5389cde` |
| M7 | Secure applications and APIs by validating claims (2025-03-21) | https://learn.microsoft.com/entra/identity-platform/claims-validation | `a4be4ac` |
| M8 | Create plans for a SaaS offer, "Configure auto activation" (2026-07-22) | https://learn.microsoft.com/partner-center/marketplace-offers/create-new-saas-offer-plans | `3d1a72a` |
| M9 | Set up technical details for a SaaS offer (2026-08-10) | https://learn.microsoft.com/partner-center/marketplace-offers/create-new-saas-offer-technical | `aab3eb7` |
| M10 | Plan a SaaS offer for Microsoft Marketplace, "Preview audience" and "Test offer" (2026-07-22) | https://learn.microsoft.com/partner-center/marketplace-offers/plan-saas-offer | `3d1a72a` |

Also opened: "SaaS fulfillment APIs" overview and "Life cycle of a SaaS subscription" (2026-07-22), for orientation;
no fact above rests on them alone. Not reached: Partner Center itself, the offer pages on `marketplace.microsoft.com`.

**Unconfirmed** until the DEV offer runs: whether Microsoft's webhook token uses the v1.0 or v2.0 issuer (both are
accepted), and whether `aud` is the bare application id as [M2] says or an Application ID URI; if the log says
`wrong audience` on a real call, that is the place to look.
