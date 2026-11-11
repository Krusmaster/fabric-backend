# Billing model: a 30-day trial per organisation, then a Marketplace subscription

Round n213, 11 November 2026. The founder's decisions of 11 November 2026, how the code carries them out
(`fabric_backend/billing.py`), what Microsoft Learn allows for terms and notice, a recommendation, and what the founder
must do in Partner Center. **Everything here is off** until the founder sets `"trial": true` and runs
`bash deploy/krusgraph.sh --update`. No prices are set or written anywhere in this round. Nothing here is a claim about
speed, certification, partnership or endorsement; Krusgraph is published by Kruse Consulting AB, which is not affiliated
with Microsoft.

Sources `[Bn]` are in the table at the end, all read on learn.microsoft.com on **11 November 2026**. What Learn does not
state is marked **Unverified**.

## 1. The flow, from consent to subscription

1. **Consent.** An Entra administrator of the customer's organisation approves Krusgraph's Entra app (hosted MCP
   server, `/start`) or the workload's app (Fabric). Nothing about billing happens at consent.
2. **First use starts the trial.** The first authenticated call from that organisation's Entra tenant id (`tid`) on
   either product starts one 30-day trial for the organisation, for both products: a tool call on the hosted MCP server,
   or opening the Krusgraph Model item in Fabric (the editor calls `POST /workload/v1/access` when it opens). The trial
   is one row in the table that already holds the Marketplace subscriptions (PartitionKey `trial`, RowKey the tenant
   id): `first_seen`, `trial_ends`, which product was first, the users' salted hashes (point 5) and the dates the
   founder's notices were sent. No names, no e-mail addresses, no object ids.
3. **During the trial** everything works. The workload editor shows one quiet line, for example
   "Trial: 23 days left (until 4 December 2026). Subscribe through Microsoft Marketplace: <offer link>". In the last
   7 days, the MCP tools' answers carry `billing_notice` with the end date and the link.
4. **After 30 days without a subscription**: reading, checks and dry runs keep working. Create, and every tool or route
   that writes to Fabric, is refused with `kind: upgrade` (HTTP 402 in the workload), in plain words, with the end date,
   0 days left and the offer link. Writing means: the creating MCP tools (`create_backend`, `create_views`,
   `create_semantic_model`, `create_report`, `create_data_agent`, `create_ontology`, `create_silver_notebook`,
   `create_gold_views`, `create_pipeline`, `create_drift_monitor`) with `dry_run=false`, and the workload's `/build`
   and `/product` retire with `dry_run=false`. The list of creating tools is read from the code (`switches.creates`),
   not typed, so a new creating tool is gated without a change here. Items Krusgraph already made stay the customer's
   and can be changed or deleted in Fabric itself.
5. **Subscription.** An administrator or purchaser subscribes once for the organisation through Microsoft Marketplace
   (the existing landing page and webhook, n171/n204, `docs/MARKETPLACE-SETUP.md`). An active subscription
   (`Subscribed`) opens everything again; `Suspended` or `Unsubscribed` closes writing again. Microsoft bills.
6. **Users per organisation.** Plans are flat rate per organisation by number of users (draft: up to 5 users; 6 to 25
   users). Each user is kept only as `HMAC-SHA256(salt, tid:oid)`, the first 24 hex characters, with the last day
   seen; entries older than 30 days are dropped and the count is what is left. The salt is the container-app secret
   `user-hash-salt` (`KRUSGRAPH_USER_HASH_SALT`), never in code; without it nobody is counted. Over the plan's cap
   (`KRUSGRAPH_PLAN_USER_CAPS`), the users see one line and the founder gets the event `plan_over_cap` (at most once
   per organisation in 30 days). **Nothing is blocked for being over the cap in this round.**

**Exempt, never gated and never written**: Kruse Consulting's own tenant (`KRUSGRAPH_PUBLISHER_TENANT_ID`, default
`KRUSGRAPH_MARKETPLACE_TENANT_ID`) and the pilot tenants in `KRUSGRAPH_TRIAL_EXEMPT_TENANTS`. A B2B guest working in the
publisher's tenant (`docs/GUEST-TRIAL.md`) is exempt the same way: the guest's token carries the publisher's tenant id,
so no trial starts for the guest's own organisation.

**Self-hosted open source stays free and is never gated**: the switch is off by default and nothing in the MIT code
requires it.

**One decision.** `billing.decide` is the only gate, used by the MCP tools (`server._instrumented`) and the workload
routes (`workload_api.routes`). With `KRUSGRAPH_TRIAL=1` it replaces the feature split of `entitlements.py` (lineage
and the drift monitor's draft are reads and stay open after the trial). A store that cannot be read closes writing for
that call with "try again in a minute" and never closes reading.

## 2. What the founder is told

| Event (`{"krusgraph":"billing","event":...}`) | When | Fields |
| --- | --- | --- |
| `trial_started` | the first call from a new organisation (not exempt, not already subscribed) | tenant, product, first_seen, trial_ends |
| `trial_ends_soon` | once, from 7 days before the end: on a call from the organisation, or in the sweep every 6 hours | tenant, trial_ends, days_left |
| `plan_over_cap` | users in 30 days above the plan's cap, at most once in 30 days | tenant, plan, cap, users_30_days |

`docs/OPERATIONS.md`, section 4, turns these into an Azure Monitor e-mail alert (the `az` commands are there). With the
container-app secret `founder-webhook` (`KRUSGRAPH_FOUNDER_WEBHOOK_URL`, a Teams workflow or Power Automate HTTP
trigger, as in n200) the same event is also posted as an Adaptive Card; the address is never logged.

## 3. What Microsoft Learn allows for terms and notice

The founder asked for **monthly billing with roughly a three-month notice period**.

1. **Terms and billing frequency.** For SaaS plans: a 1-month term is paid "one-time upfront" each month; a 1-year term
   can be paid upfront or **monthly**; 2- to 5-year terms upfront, monthly or annually; a flexible schedule only through
   a private offer. "A given plan supports only one billing frequency for a contract duration. To offer an additional
   billing frequency for the same contract duration, create another plan." [B1] "For contract durations with equal
   payments, payment collection is enforced for the entire term" [B1]. Pricing models: "either flat rate or per user",
   and "All plans in the same offer must use the same pricing model" [B1]; a per-user plan can set a minimum and maximum
   number of users, which Marketplace then enforces, unlike our own count (a choice for the founder, see 5.1).
2. **Cancellation and refunds.** "You're eligible for a full refund, excluding metered billing charges, if you cancel
   your SaaS subscription within 72 hours of purchase." [B2] "SaaS subscriptions with pending future payments aren't
   eligible for cancellation after the standard 72-hour cancellation period passes. Cancellation for such
   subscriptions isn't possible until the current billing term is over, and all pending payments are complete." [B3]
   After 72 hours, refunds go through the publisher [B2]. Publisher-defined cancellation policies beyond that:
   **Unverified** (Learn says nothing more).
3. **Auto-renew.** "When recurring billing is off, the SaaS subscription and service terminate on the renewal date. You
   can change the renewal option only while the subscription is active." [B3] Monthly and 1-year plans renew
   automatically when the term ends [B4]. The default for public plans is not stated: **Unverified**. For private
   offers, auto-renew is off by default [B5].
4. **Private offers.** "Custom pricing and duration: Configure private prices, contract durations, and billing
   schedules", and "Custom terms and contract upload: Attach a PDF with customer-specific terms" [B6]. Custom terms of
   "1 to 120 months or 1 to 10 years" for absolute-pricing SaaS private offers; month-based durations not divisible by
   12 can be billed one-time upfront, monthly or on a flexible schedule [B7]. The same page also says "The maximum
   contract duration for private plans is three years" [B7]: Learn contradicts itself. Flexible schedules apply to
   flat-rate SaaS, up to 70 instalments, and "Cancellation and refund policies remain unchanged" [B8]; whether such a
   plan auto-renews is contradictory between [B8] and [B4].
5. **Free trial in Marketplace.** "Free trials are available for flat rate, per user, and metered pricing monetization
   models, and you can configure them for 1 to 180 days" [B1]; "When the trial ends, the subscription automatically
   converts to a paid subscription unless the customer cancels before the trial period ends or disables auto-renew" [B7].
   Our own trial (above) does not use this: it starts on first use, before anyone visits Marketplace.
6. **Your own terms.** "You either offer your solution under the Standard Contract or your own terms and conditions";
   amendments are limited to 4,000 characters [B10]. "The customer can cancel your offer at any time." [B1] Learn gives
   no basis for Marketplace enforcing a notice period written in the publisher's terms: **Unverified**, and the Azure
   portal's Cancel and auto-renew-off actions work regardless. `Unsubscribe` is "a notify-only event" that the
   publisher cannot reject [B11].

**So: a monthly plan with a three-month notice period cannot be built in Marketplace.** A customer on a 1-month term can
switch off renewal (service ends at the end of the month) or cancel.

## 4. Recommendation

The closest honest options, best first:

- **A (recommended default): public plans with a 1-year term, paid monthly.** Microsoft enforces the commitment: after
  72 hours a subscription with pending payments cannot be cancelled until the term ends [B3]. Monthly cash flow. It is a
  12-month commitment, not a three-month notice, and the page must say so plainly.
- **B (alongside A): the same plans with a 1-month term**, paid each month, as the flexible choice. Honest about the
  effective one-month notice. They are separate plans [B1], and a customer cannot move between A and B with a plan
  change, because plan changes work only between plans with the same billing term and payment option [B3].
- **C (for a larger customer): a private offer with a 3-month (or 6- or 9-month) term, billed monthly**, with a
  custom-terms PDF [B6][B7]. The shortest commitment Microsoft enforces. Per customer and manual; auto-renew is off by
  default [B5]; confirm the term lengths with Partner Center support before relying on them, since Learn contradicts
  itself [B7].

**Do not** write a three-month notice clause into the terms and assume Marketplace applies it.

## 5. What the founder must do in Partner Center (and around it)

1. In the SaaS offer, create the plans (draft: up to 5 users; 6 to 25 users), each **flat rate** (the decision; the
   per-user model with a minimum and maximum per plan is the alternative Marketplace itself enforces [B1], and the
   pricing model cannot be changed after publishing [B1]), with the terms chosen
   above (A: 1 year, monthly payment; B: 1 month), and prices you set yourself. Note each plan id.
2. Do not switch on Marketplace's own free trial on these plans (point 3.5), so there are not two trials.
3. Choose Standard Contract or your own terms [B10]. The draft clause for `/terms` in section 6 below is for you and a
   lawyer; it is not on the site (the live `/terms` stays the preview terms, and `tests/test_site.py` keeps words such as
   "notice period" off it until real terms exist).
4. Put the plan ids and their caps in `deploy/krusgraph.json`: `"plan_user_caps": "{\"<plan id>\": 5, \"<plan id>\": 25}"`.
5. Put the pilot tenants in `"trial_exempt_tenants"` and check `"marketplace_tenant_id"` (or `"publisher_tenant_id"`) is
   Kruse Consulting's tenant.
6. Store the salt (and, optionally, the Teams/Power Automate address) as container-app secrets; the commands are
   printed by `bash deploy/krusgraph.sh --update --dry-run`, which lists what is missing.
7. Create the Azure Monitor alert (`docs/OPERATIONS.md`, section 4).
8. Set `"trial": true` (with `"marketplace": true`) and run `bash deploy/krusgraph.sh --update`. Until then nothing
   changes for anyone.

## 6. DRAFT clause for `/terms` (for the founder and a lawyer; not published, not in force)

> **DRAFT.** Trial, subscription and notice.
>
> 1. Trial. The first use of the hosted service or of the Krusgraph Model item in Microsoft Fabric by a user of an
>    organisation (identified by its Microsoft Entra tenant) starts one trial of 30 days for that organisation, on both.
>    No payment is taken for the trial.
> 2. After the trial. Without an active subscription the service keeps reading, checking and showing dry runs, and does
>    not create or change anything in Microsoft Fabric. Items already created remain the organisation's.
> 3. Subscription. The organisation subscribes through Microsoft Marketplace. Microsoft bills on the publisher's behalf;
>    the term, the payment option, cancellation, refunds and renewal follow the plan chosen in Microsoft Marketplace and
>    Microsoft's marketplace terms.
> 4. Notice. [For the lawyer: the plan's term in Microsoft Marketplace (section 4: a 1-year term paid monthly, or a
>    1-month term) decides when a subscription ends. A separate three-month notice period in these terms would not
>    change what Microsoft Marketplace lets a customer do [B1][B3][B11], so it should not be written as if it did.]
> 5. Users. A plan covers a number of users. Going above it is not blocked; the organisation is told and may change the
>    plan in Microsoft Marketplace.
> 6. Open source. The source code under the MIT licence, run by anyone themselves, is not affected by any of the above.

## Sources (read 11 November 2026)

| | Page |
| --- | --- |
| B1 | https://learn.microsoft.com/en-us/partner-center/marketplace-offers/plan-saas-offer |
| B2 | https://learn.microsoft.com/en-us/marketplace/refund-policies |
| B3 | https://learn.microsoft.com/en-us/marketplace/saas-subscription-lifecycle-management |
| B4 | https://learn.microsoft.com/en-us/marketplace/purchase-saas-offer-in-azure-portal |
| B5 | https://learn.microsoft.com/en-us/marketplace/private-offers-purchase |
| B6 | https://learn.microsoft.com/en-us/partner-center/marketplace-offers/isv-customer |
| B7 | https://learn.microsoft.com/en-us/partner-center/marketplace-offers/marketplace-commercial-transaction-capabilities-and-considerations |
| B8 | https://learn.microsoft.com/en-us/partner-center/marketplace-offers/flexible-billing-schedule |
| B10 | https://learn.microsoft.com/en-us/partner-center/marketplace-offers/standard-contract |
| B11 | https://learn.microsoft.com/en-us/partner-center/marketplace-offers/pc-saas-fulfillment-webhook |
