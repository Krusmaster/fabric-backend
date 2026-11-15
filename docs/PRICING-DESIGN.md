# Pricing design: a cost and pricing model before the Marketplace go-live

Round P1, 15 November 2026. Documentation only: no code, nothing created or changed in Partner Center, Azure, Entra or
Fabric, and nothing on the site. The founder, 12 November 2026: "we need a good cost model before we go live with
Krusgraph on the workload marketplace. We can have different prices per country. And we can have one price but launch
with a discount, and extend the discount or not."

**No price in this document is decided.** Every amount for Krusgraph is a *proposal to test*, written so the founder
can strike it out and write another. Nothing here says what a customer will gain or avoid in money; where the document
compares with what a buyer pays for other things, those are public list prices or labelled estimates. No customer or
prospect is named. Nothing here is legal or tax advice. Krusgraph is published by Kruse Consulting AB, which is not
affiliated with Microsoft.

It builds on what is already decided (`docs/BILLING-MODEL.md`, `docs/MARKETPLACE-SETUP.md`,
`docs/WORKLOAD-LISTING-AND-PAYMENT.md`, `docs/PRICING-NOTES.md`, `docs/PILOT.md`):

- A DEV offer `krusgraph-dev` with plans at a nominal 1 USD, for tests only, never "Go live".
- One 30-day trial per organisation (Entra tenant) from first use after admin consent, for the hosted MCP server and
  the Fabric workload together. After it, writing to Fabric needs a Marketplace subscription; reads, checks and dry
  runs stay free.
- Monthly billing, with the founder's wish for about three months' notice (which Marketplace cannot enforce on a
  1-month term; `docs/BILLING-MODEL.md`, sections 3 and 4).
- The self-hosted open-source code stays free and is never gated.

## How this was researched

- **Microsoft Learn** answered from this environment. 42 pages were read on **15 November 2026**; each fact carries a
  source `[Dn]`, listed at the end with the page's own `ms.date`. Quotes are verbatim. What no page states is marked
  **Not on Learn**.
- **Nothing else from Microsoft could be opened**: `azure.microsoft.com`, `prices.azure.com`,
  `marketplace.microsoft.com` and `partner.microsoft.com` were blocked. So **no Azure unit price here is verified
  against Microsoft's price sheet**, and none is specific to Sweden Central. They are marked **snippet** (a search
  result quoting the page, the page itself not opened) or **memory** (recalled, unverified). The founder's own Azure
  invoice (Cost Management on `rg-krusgraph`) replaces all of them.
- **Vendor price pages were blocked too.** Comparable tools' prices are search snippets of the URL given, or third
  parties quoting the vendor; they are marked the same way. Treat them as "about", and open the page before quoting
  one to a customer.
- Exchange rates: EUR/USD 1.1127, EUR/GBP 0.836, EUR/SEK 11.05 (Bank of Finland, 11 November 2026, snippet). EUR/DKK
  7.47 (1 July 2026), EUR/NOK 10.83 and EUR/CHF 0.917 (4 May 2026) are **stale**; re-check before entering a price.

## Summary

| Question | Short answer |
| --- | --- |
| What does it cost us to run? | In cash, little: roughly SEK 2,000 to 10,000 a month all in (section 1), of which Azure is a few hundred kronor. The real cost is the founder's time. Nothing in Azure grows much with customers, because the work runs in the customer's own Fabric capacity; support time does. |
| What does Microsoft take? | 3% of what the customer pays, deducted at payout [D1]. Microsoft handles invoicing, collection and VAT in all eight countries looked at [D10]. |
| Flat rate or per user? | Must be chosen once for the offer and cannot be changed after publishing [D5]. Recommendation: **flat rate per organisation, in sizes by number of users** (section 6). |
| Prices per country? | Yes. A plan's price is entered in USD and converted once; after that each market's price is static and can be overridden per market in its own currency with an exported and imported price file [D8][D9][D5]. |
| A launch discount? | Marketplace has no coupon or promotional price on a public plan (**Not on Learn**). Four real mechanisms exist (section 2.5). Recommendation: publish the real list price and give the launch discount as **private offers** (a percentage off list, per customer, with an end date); at the end the customer renews at list, or gets a new private offer if the founder extends. |
| What must be decided first? | Ten decisions, section 7. Four cannot be undone once the production offer is published: the pricing model, the offer id, each plan id, and making a plan public. |

## 1. Our costs

### 1.1 What runs, as `deploy/` has it

`deploy/azure_containerapp.py` creates: one Container Apps environment and app on the Consumption profile, 0 to 2
replicas of 0.25 vCPU and 0.5 GiB, in Sweden Central; a Container Registry (Basic); optionally a Key Vault; optionally
a Log Analytics workspace; one storage account (Standard LRS) with tables for sign-in records, subscriptions and
trials; a cost budget with e-mail. The domain and the managed certificate sit on the container app.

### 1.2 Fixed costs per month (estimates; replace with the invoice)

| Item | Estimate per month | Basis and how sure |
| --- | --- | --- |
| Container Apps, one replica always on (`min_replicas` 1) | USD 4 to 15 (SEK 40 to 150) | 657,000 vCPU-seconds and 1,314,000 GiB-seconds a month, minus the monthly free grant of 180,000 vCPU-seconds, 360,000 GiB-seconds and 2 million requests [D40]; rates USD 0.000024 per vCPU-second active, 0.000003 idle, 0.000003 per GiB-second (snippet, US East). With `min_replicas` 0 it is inside the free grant at today's volume. Marketplace expects the landing page and webhook to run around the clock and to answer plan changes within 10 seconds (`docs/WORKLOAD-LISTING-AND-PAYMENT.md`, 2e), so count on one replica once the offer is live. |
| A second replica at peaks | up to USD 15 more | same rates |
| Container Registry, Basic | USD 5 (SEK 50) | USD 0.167 a day (snippet) |
| Key Vault, Table Storage | under USD 1 | per 10,000 operations (snippet, memory) |
| Log Analytics | 0 at today's volume | first 5 GB a month free; `docs/OPERATIONS.md` estimates under 1 GB a month |
| Alert rules, availability test | USD 2 to 8 | memory |
| Custom domain binding and managed certificate | 0 | [D41] |
| `krusgraph.com` renewal | about SEK 15 (USD 12 to 20 a year) | memory |
| **Azure and domain, sum** | **about SEK 150 to 400** | |
| Fabric capacity for demos (the founder's own) | SEK 150 if paused outside demos; about SEK 2,600 if an F2 runs all month | F2 pay-as-you-go about USD 263 a month, F4 about USD 526 (snippet, US price; Sweden Central not found). 40 hours of an F2 is about USD 14. A Fabric trial capacity costs nothing while it lasts. |
| Mailbox (`hello@krusgraph.com`), Microsoft 365 Business Basic or Standard | SEK 70 to 140 | USD 7 or 14 per user a month (snippet) |
| Partner programme | 0, or about SEK 1,280 | Frontier Accelerate for Marketplace: a free tier, and Premium at USD 1,550 a year with Azure dev/test credits for new Premium partners [D42]. The credits could cover the Azure rows above. |
| Insurance: professional indemnity and cyber | SEK 500 to 1,700 | **Estimate**: SEK 6,000 to 20,000 a year for a one-person IT company; no insurer's list price was found. Get a quote; customers under NIS2 will ask (`docs/SECURITY-SUPPLIER.md`). |
| Legal: terms and the DPA written with a lawyer | SEK 1,250 to 4,200 | **Estimate**: one-off SEK 30,000 to 100,000 (10 to 25 hours), spread over 24 months. `docs/DPA-DRAFT.md` and the draft clause in `docs/BILLING-MODEL.md` are the lawyer's starting point. |
| Accounting, tools the founder develops with | the founder fills in | not known to this repository |
| **Cash cost, sum** | **about SEK 2,100 (lean) to 10,300 (everything on)** | The calculations below use SEK 6,000. |
| The founder's time | the largest cost | Not a cash cost of the product until there is a salary. Section 4 uses **SEK 90,000 a month** as "one person's full cost" (an assumption: replace it with your own number). |

### 1.3 What grows with customers

| Per customer | Cost | Note |
| --- | --- | --- |
| Azure | close to 0 | One row per organisation in Table Storage. Counting queries, the SQL endpoint, pipelines and items run in the **customer's** Fabric capacity and are billed to the customer by Microsoft (`docs/PRICING-NOTES.md`). 100 organisations with 8 users and 50 calls a working day are about 0.9 million requests a month, inside the free 2 million; beyond that requests are about USD 0.40 a million (snippet), and a second replica is the row above. |
| Marketplace fee | 3% of the price | "Microsoft charges a 3% standard store service fee when customers purchase your transact offer from Microsoft Marketplace", deducted "at the time of publisher payout" [D1]. On a private offer the fee is on the private price [D17]. A renewal by private offer can get "a 50% discount ... to your existing Microsoft Marketplace transaction fee", if attested when the offer is created, not afterwards [D3]. |
| Payment, invoicing, VAT | 0 to us | Microsoft invoices and collects. All eight countries in section 3 are Microsoft-managed for tax: Microsoft calculates, collects and remits [D10]. Payouts go out monthly, typically by the 15th, above USD 50, in the payout currency chosen in Partner Center [D36][D37][D9]. |
| Currency | a risk, not a fee | Local prices are static once saved [D8]. If the payout currency differs from the customer's billing currency, Microsoft converts at the rate of the month of the transaction [D9]. A weaker USD, NOK or GBP lowers what arrives in SEK until the price is changed. |
| Non-payment | rare, ours | If a customer never pays Microsoft, the payout is deducted from later payouts [D36]. |
| Onboarding | about 8 hours once (assumption) | Admin consent, the two tenant settings, a first data product together. With a pilot, it is inside the pilot. |
| Support | about 2 hours a month (assumption) | The cost that scales. At 100 customers it is 200 hours a month: more than one person. |

**Fixed versus per customer.** Almost everything in cash is fixed and small. What decides whether the product carries
itself is the price times the number of customers against one person's time, and how many support hours a customer
needs. That is why section 4 counts in hours as well as kronor.

## 2. What Marketplace allows

The offer is a transactable SaaS offer; the Fabric workload's manifest links to it. Fabric does not check a licence or
bill for a partner workload: "Fabric Extensibility toolkit does not provide additional tools for Azure Marketplace
integration" [D38], and trial limits are for the partner "to define ... and enforce them within the workload's
backend" [D39]. So every rule below is Marketplace's, and every gate is `fabric_backend/billing.py`.

### 2.1 Pricing models, terms, trials

| Topic | What Learn says |
| --- | --- |
| Model | Flat rate or per user. "An offer can have only one pricing model ... However, a SaaS offer can have some plans with flat rate with metered billing and other flat rate plans without metered billing" [D7]. "After your offer is published, you can't change the pricing model" [D5]. Whether a second offer with the other model is allowed: **Not on Learn** (several offers per account are implied [D12]). |
| Per user | A minimum and maximum number of users per plan, optional; "The user limits (min and max) cannot be changed once the offer is in preview state or published live" [D5]. The customer changes the quantity in the Azure portal or Microsoft 365 Admin Center and the webhook tells us [D34]. Who gets a seat is ours to decide: **Not on Learn**. |
| Metered dimensions | Only on flat-rate plans, at most 30, each with a unit price and an included quantity; we would send usage every hour (`docs/WORKLOAD-LISTING-AND-PAYMENT.md` [L10][L12][L13]). A meter's price change applies at once, whatever the term [D11]. |
| Terms | 1 month; 1 year paid upfront or monthly; longer terms upfront, monthly or yearly (`docs/BILLING-MODEL.md` [B1]). "You can't remove the contract durations and billing frequencies you make available. However, you can update the price per charge in the future and add more duration and frequency options" [D7]. A term with pending payments cannot be cancelled after 72 hours (`docs/BILLING-MODEL.md` [B3]). |
| Free trial in Marketplace | 1 to 180 days per plan; it converts to paid unless the customer cancels [D33]. It can be switched off later; "Changes to free trial settings apply only to new trials" [D33] (the price-change FAQ lists "Disabling free trial" as not allowed *during a price change* [D11]). Day-based trials are not supported through CSP [D5]. Our own 30-day trial does not use this. |
| Plans | Up to 100 per offer, up to 45 private [D7]. "You can't modify the plan ID after you select Create" [D5]. "once you publish a public plan, you can't change its visibility to private"; private to public is allowed [D5]. |
| Stopping a plan | "Stop distribution" hides it from new buyers; existing customers keep it and can renew. It needs more than one plan in the offer and a republish [D13]. Plans are not deleted without a support ticket [D32]. |

### 2.2 Prices per country

- **Markets.** Each plan lists the markets it is sold in: "You must select a minimum of one and maximum of 141
  markets" [D5]. A market can be added later (its price is then converted at the current rate [D7]) and selling in a
  market can be stopped [D8]; the procedure for removing one is **Not on Learn**.
- **One USD price, converted once.** "Prices you enter in USD automatically convert to the customers' static local
  currency according to the exchange rate at the time you first save the price for the plan" [D8]. "After you create
  and save a plan, the prices in all local currencies are static. They don't update automatically" [D8].
- **Overriding per market**, in that market's currency [D5][D9]:
  1. Enter a USD price and **Save draft** ("You must first save your pricing changes to enable export").
  2. Under Pricing, select **Export pricing data**; open `exportedPrice.xlsx` in Excel.
  3. Change the price for each market; save the file.
  4. Select **Import pricing data**, answer **Yes**, choose the file. The pricing section then says "Market pricing"
     instead of a USD price.
  - "The prices for a given contract duration must be defined for the same billing frequency across all markets" [D5].
  - Learn names the file both `.xlsx` and `.csv`, and the link both "Export pricing data" and "Export prices (xlsx)"
    [D5][D7][D9]: do it once on the DEV offer first.
- **Currencies** [D8]: Sweden SEK, Norway NOK, Denmark DKK, Finland EUR, Switzerland CHF, Germany EUR, United Kingdom
  GBP, United States USD. The customer is invoiced "in the billing account currency associated with their Microsoft
  agreement, which may differ from their market currency"; Microsoft then converts at the month's rate [D9].
- **Tax.** All eight are Microsoft-managed [D10].

### 2.3 Changing a price after publishing

| | Rule |
| --- | --- |
| Decrease | "Price decreases are scheduled for the first of the next month" [D11]. |
| Increase | "Price increases are scheduled for the first of a future month, at least 90 calendar days after the price change is published" [D11]. No custom date, no expediting [D14]. For SaaS, publish at least four calendar days before the end of a month [D11]. |
| Who is told | For an increase, "existing customers of the offer receive an email notification" and the listing shows "a notice of the upcoming increased price" [D11]. |
| Who pays what | "Existing customers maintain their price for the duration of the billing term. Upon renewal, the new price in effect at that time applies. New customers are billed at the price in effect when they purchase" [D11]. |
| One at a time | A second change must wait until the first has taken effect; an increase and a decrease on the same plan together are not supported [D11][D14]. To cancel a scheduled change: a support request at least four calendar days before its date [D11]. |
| Not possible | From free or 0 to paid; through the API; on hidden plans [D11]. Only the price changes; do not change anything else in the same publish, since "Price changes go through full certification" [D11]. |
| In preview | A price can be changed freely before the offer is live: "This isn't considered a price change" [D14]. |
| Markets | The new price is converted at current rates for each market, or set per market with the price file [D11]. |

### 2.4 What cannot be changed after publishing

The offer id and alias [D12]; the plan id [D5]; the pricing model [D5]; "Sell through Microsoft" back to listing-only
[D12]; a public plan back to private [D5]; a contract duration or billing frequency once offered [D7]; per-user seat
limits [D5]; and, if chosen, CSP resale by "Any partner in the CSP program" ("you can't change or update it") [D29].

### 2.5 Selling below the list price for a limited time

There is **no coupon, discount code or promotional price on a public plan** (Not on Learn; nothing in the Partner
Center pages read). These are the mechanisms that exist:

| Mechanism | How it works | How it ends or is extended | Fits |
| --- | --- | --- | --- |
| **A. Private offer to one customer** | Needs the offer live and publicly transactable [D17]. A percentage discount on a public plan, or an absolute price (also as a new plan with its own term of 1 to 120 months) [D17][D1]. One customer billing account per offer; clone it for the next [D17]. Start on acceptance or the first of a month; an end date; an accept-by date [D17][D18]. Available "within 15 minutes" [D16]. Cannot be edited after submission, only withdrawn before acceptance [D17]. The fee is on the private price [D17]. Can be created through an API [D19]. | "If the customer chose automatic renewal, and you don't create a new private offer that the customer accepts, the customer is charged at the list price of the public plan after the private offer End date" [D18]. With auto-renew off (the default for private offers) the subscription ends on the end date [D18]. To extend: a new private offer; a renewal can carry the halved fee [D3]. Two offers for the same account and plan with overlapping dates are blocked [D18]. | The list price stays visible and true. The first customers are sold by hand anyway. Not for a customer who buys through a CSP ("aren't eligible for private offers or private plans" [D21]). |
| **B. A lower public price now, an increase later** | Publish the plan at the launch price. Later publish an increase; Microsoft schedules it at least 90 days ahead, e-mails customers and shows the notice [D11]. | To extend: do not publish the increase yet. To end: publish it; existing customers keep their price to the end of their term and renew at the new one [D11]. | Reaches buyers who never talk to us. But the storefront shows only the launch price, the "list price" exists only on our own page until the increase is scheduled, and a published increase cannot be moved [D14]. |
| **C. A private plan for named organisations** | A plan visible only to listed tenant ids, at "higher or lower pricing ... than the publicly available plan" [D1]; up to 10 ids by hand, more by file; the audience can be synced without republishing [D5][D13]. Up to 48 hours to appear [D16]. | Stop distribution; **existing customers can still renew on it** [D13], so the discount only ends with a price increase on that plan (90 days) [D14]. Not through CSP [D31]. Microsoft: "supported scenarios are limited" [D31]. | A "founding customer" plan for a known group. Hard to end cleanly. |
| **D. Marketplace's free trial** | 1 to 180 days free on a plan, then paid [D33]. | Switch it off for new trials [D33]. | Would be a second trial on top of ours, so not recommended (`docs/BILLING-MODEL.md`). An absolute-price private offer cannot be made on a plan with a trial [D18]. |

**Through others.** A multiparty private offer: we set a "Partner price" (the wholesale price) for a channel partner,
the partner adds its own adjustment, and "Microsoft invoices and collects payment from the customer" [D22][D23][D24].
The 3% is on the partner price, not on the partner's markup [D25]. On 13 November 2026 the table of supported countries
(for the customer's billing account and the partner's tax profile) had Sweden, Norway, Denmark, Finland, Germany, the
United Kingdom and the United States; **Switzerland was not in it** [D22]. A CSP private offer gives chosen CSP
partners "a percentage off your plan's list price" as margin; the CSP sets the customer's price and invoices outside
Marketplace, and when the offer ends the partner can go on selling at list [D27]. A referral fee or commission:
**Not on Learn**; co-sell referrals (partner to partner) share an opportunity, they do not pay anyone [D43][D44].

## 3. Value and willingness to pay

### 3.1 What the buyer weighs it against

Described, not priced: nobody has measured this at a customer, and this document makes no claim about it.

- **Rebuilds.** A semantic model, a set of views or an API built on a guessed join, then built again when the key
  turns out to be composite or the relationship many-to-many.
- **Wrong numbers.** Totals that double after a join (the site's blog post), found late, by someone who trusted them.
- **Consultant days.** The same hand-over work done by hand: finding keys, documenting relationships, a data
  dictionary, a first model. This is the comparison a buyer makes first, so it is the anchor below.
- **Staying put.** No budget line for it this year. For a mid-size industrial company this is the usual competitor.

### 3.2 Public prices a buyer already knows

| What | Public price | Unit | Source | How sure |
| --- | --- | --- | --- | --- |
| Power BI Pro / Premium Per User | USD 14 / 24 | user a month | microsoft.com/power-platform/products/power-bi/pricing | page read 15 Nov 2026 |
| Microsoft 365 Copilot | USD 30 | user a month | – | memory |
| Fabric capacity F2 / F4 / F64, pay-as-you-go | about USD 263 / 526 / 8,410 | month | third parties quoting azure.microsoft.com | snippet |
| Tabular Editor 3 Business / Enterprise | USD 35 / 95 | user a month | tabulareditor.com/pricing | snippet |
| dbt, Starter plan | USD 100 | seat a month, at most 5 seats | third parties quoting getdbt.com | snippet |
| Measure Killer, Enterprise | from USD 108 | user a month | measurekiller.com/compare | snippet |
| Argus PBI | USD 400 a month or 4,000 a year | tenant | arguspbi.com/pricing | snippet |
| Power BI Sentinel | USD 395 / 1,030 / 1,550 | organisation a month | powerbisentinel.com/license-compare | snippet; tier names unclear |
| Select Star, Growth | USD 810 | organisation a month | third party | snippet |
| Soda, Team | from USD 750 plus usage | organisation a month | third party | snippet |
| Other workloads in the Fabric Workload Hub | none found | – | marketplace.microsoft.com blocked | **unknown**; most appeared to be quote-only (memory) |
| Senior BI or data consultant, Sweden | SEK 950 to 1,600 an hour | hour | Brainville averages via konsultguiden.se; blogs | snippet |
| Same, Germany | EUR 95 to 120 an hour | hour | freelancermap Freelancer-Kompass | snippet |
| Same, Switzerland | CHF 130 to 250 an hour | hour | Swiss freelancer guides | snippet |
| Same, United Kingdom | about GBP 440 to 500 a day | day | itjobswatch.co.uk | snippet |
| Same, United States | USD 120 to 250 an hour | hour | contractor rate guides | snippet |
| Same, Norway, Denmark, Finland | NOK 1,200 to 1,800; DKK 800 to 1,250; EUR 80 to 120 an hour | hour | – | **guess** (Denmark: one blog) |

What this says: tools a data team buys **per user** sit between USD 35 and 110 a user a month; tools bought **per
tenant** for governance or monitoring sit between USD 400 and 1,550 a month. The founder's earlier thought, about EUR
1,000 a month per organisation, is inside the second band, and five figures CHF a year for an enterprise is the same
number times twelve with a Swiss premium.

### 3.3 The budget of a Nordic or Swiss mid-size industrial company

Not researched with data; these are judgements to test in conversations:

- A data or BI team of 2 to 10 people, a Fabric capacity of F8 to F64, one or two consultancies on call.
- A team lead can usually approve a few thousand kronor a month without a tender; around EUR 1,000 a month it becomes
  a line the head of IT or finance sees; above about EUR 25,000 a year it is often a procurement case with a supplier
  assessment (`docs/TRUST-PACK.md` is written for that).
- Marketplace helps where the company already has a Microsoft agreement: no new supplier to register, Microsoft's
  invoice. Counting against an Azure commitment is **not** available to us yet (`docs/WORKLOAD-LISTING-AND-PAYMENT.md`,
  2d) and must not be promised.

### 3.4 A proposal for the reference price

Proposal to test, in EUR, for a 1-year term paid monthly: **Team** (up to 5 users) **EUR 490 a month**; **Business**
(6 to 25 users) **EUR 990 a month**; **Enterprise** (more than 25 users, own terms) by private offer **from EUR 2,400
a month**. The same plans on a 1-month term about 20% higher (EUR 590 and 1,190).

The reasoning, with no claim about what a customer gains: Team is about what four to five hours of a senior consultant
cost in Sweden in a month, Business about a consultant day. For five users Team is about EUR 98 a user, level with
the per-user tools above; for 25 users Business is about EUR 40 a user. Business matches the founder's "about EUR 1,000
a month per organisation"; Enterprise is EUR 28,800 a year, which is five figures in CHF.

### 3.5 A country price table (proposal to test)

Monthly price in the market's own currency, 1-year term paid monthly. "Index" is the price converted to EUR at the
rates above, with Germany and Finland as 100.

| Market | Currency [D8] | Team (up to 5) | Business (6 to 25) | Index | Reasoning |
| --- | --- | --- | --- | --- | --- |
| Germany | EUR | 490 | 990 | 100 | The reference. Freelance rates near Sweden's; the largest market of the eight; price-sensitive mid-size buyers. |
| Finland | EUR | 490 | 990 | 100 | Same currency; price level close to Sweden's (Eurostat 2025: FI 120.8, SE 121.0, EU = 100; snippet). |
| Sweden | SEK | 5,400 | 10,900 | 100 | Home market, the first customers and the pilot. A round number at today's rate; no premium. |
| Denmark | DKK | 3,900 | 7,900 | 107 | Price level 139.7. The krone is pegged to the euro, so the price holds. |
| Norway | NOK | 5,900 | 11,900 | 111 | Price level 128.6 and higher consultant rates (guess). The krone moves: review twice a year. |
| Switzerland | CHF | 540 | 1,090 | 120 | Price level 171.3; consultant rates about double Sweden's; the founder's enterprise thought was in CHF. |
| United Kingdom | GBP | 420 | 850 | 103 | About the EUR number at today's rate; day rates below the Nordics', so no premium. |
| United States | USD | 590 | 1,190 | 108 | Consultant rates well above Europe's and per-tenant tools at USD 400 to 1,550. Not a launch market; a price so the listing is complete. |

Rules for the table, whatever the numbers become:

1. **One reference price, a fixed index per market**, written down. A customer who asks why Zurich pays more gets one
   sentence: local price level and local currency.
2. **Round local numbers**, not converted ones (5,400, not 5,414).
3. **Review twice a year**, 1 May and 1 November: if a currency has moved more than 10% against EUR, change that
   market. A decrease takes effect the first of next month; an increase needs 90 days [D11].
4. **Markets at launch**: the eight, or the Nordics, Germany and Switzerland first. Every other market left selected
   gets the USD conversion at the rate on the day of the first save [D8]; either deselect them or accept that.
5. A customer is invoiced in its billing account's currency, which can differ from its market's [D9]; a group that
   buys from another country gets that country's price. That is fine; do not try to prevent it.

## 4. Pricing options

### 4.1 What a plan can include today, in code

- **The gate is one decision** (`billing.decide`): an active subscription, a running trial or an exempt tenant opens
  everything; otherwise writing to Fabric is refused and every read, check and dry run still runs. With the trial
  switched on, **no feature is tied to a plan**: a subscriber on any plan has every tool.
- **Users**: counted per organisation over 30 days as salted hashes; `KRUSGRAPH_PLAN_USER_CAPS` maps a plan id to a
  number. Over the cap the users see one line and the founder gets `plan_over_cap`. **Nothing is blocked.**
- **Quantity**: the webhook stores a subscription's `quantity`, so a per-user plan's seat count is known, but nothing
  compares it with the users seen.
- **Metering**: not built (`docs/WORKLOAD-LISTING-AND-PAYMENT.md`, round R5); it needs the privacy policy changed first.

So tiers by number of users work today as a soft cap; tiers by feature, a hard seat cap and meters each need a build
round. Every option below says what it needs.

### 4.2 What is in which plan (the same for options A to C)

| | Free (no subscription, after the trial) | Team / Business (subscription) | Enterprise (private offer) |
| --- | --- | --- | --- |
| Reads: workspaces, sources, tables, plan, validate, join path, describe, lineage, drafts, dry runs of everything | yes | yes | yes |
| The browser check, the open-source server and command line you run yourself | yes, always | yes | yes |
| Create and change in Fabric: API for GraphQL, views, semantic model, report, data agent, ontology, notebooks, pipeline (`dry_run=false`; the workload's Build) | 30-day trial only | yes | yes |
| Lifecycle (promote, retire), verify what was built, drift monitor and what exists of repair by rules | reads and dry runs | yes, as far as each exists | yes |
| SAP pack, CDS modules | reads and dry runs | yes | yes |
| Migrations (the coached journey) | reading an old platform | yes, as far as it exists | yes, usually with services |
| Users | – | 5 / 25, soft cap | agreed |
| Terms | preview terms | Standard Contract or our terms, the DPA | own contract and DPA attached to the private offer, supplier assessment answered |
| Support | the support page | e-mail, answer within a working day (a proposal; nothing is promised today) | a named contact, agreed times |

Each feature's status is the one in `fabric_backend/tool_status.py`; several of the rows are experimental or designs
(`docs/LIFECYCLE-DESIGN.md`, `docs/INTEGRATE-AND-HEAL-DESIGN.md`, `docs/MIGRATION-DESIGN.md`). **A plan description in
Partner Center must list only what runs today**, with the same status words as the site.

Recommendation on feature tiers: none at launch. The SAP pack or migrations as an Enterprise-only feature is tempting,
but it needs code, it makes the trial harder to explain, and the mid-size SAP company is exactly the Team or Business
buyer.

### 4.3 The options

Illustration only. Assumptions, the same for all: of every ten customers six have 4 users, three have 12 and one has
30; net is after Microsoft's 3%; EUR 1 = SEK 11.05; list prices with no launch discount; cash cost SEK 6,000 a month;
one person's full cost SEK 90,000 a month; 2 support hours a customer a month.

| | A. Flat by size | B. Per user | C. One flat price | D. Flat base plus a meter |
| --- | --- | --- | --- | --- |
| Marketplace model | flat rate | per user | flat rate | flat rate with a metered dimension |
| Plans (proposals) | Team up to 5: EUR 490; Business 6 to 25: EUR 990; Enterprise by private offer from EUR 2,400 | EUR 99 a user a month, at least 3 | EUR 990 per organisation; Enterprise from EUR 2,400 | EUR 290 base, plus for example EUR 60 per data product built in the month |
| Where the idea came from | a prospect's: one price for 1 to 5 users, a package price above | the per-user tools in 3.2 | the founder's "about EUR 1,000 a month per organisation" | usage-based tools |
| Seat cap | our soft cap, as built | Marketplace's quantity; we must compare it with users seen (a small build) | none needed below Enterprise | none |
| Needs building | nothing | seat check; a decision on who holds a seat | nothing | metering, hourly usage events, a privacy change |
| Average per customer a month | EUR 831 | EUR 891 | EUR 1,131 | EUR 560 (if half the users build one product a month) |
| 5 customers: net a month | SEK 44,500 | SEK 47,800 | SEK 60,600 | SEK 30,000 |
| 20 customers: net a month | SEK 178,000 | SEK 191,000 | SEK 242,000 | SEK 120,000 |
| 100 customers: net a month | SEK 891,000 | SEK 955,000 | SEK 1,212,000 | SEK 600,000 |
| Customers to cover cash cost plus one person (SEK 96,000) | 11 | 11 | 8 | 16 |
| Support hours a month at 5 / 20 / 100 | 10 / 40 / 200 | the same | the same | the same |
| Main risks | A 6-person team feels the step from 490 to 990. A large organisation can stay on Business, since the cap is soft. | Teams share one sign-in or keep users off it, which works against being used. Seat administration and quantity changes are support work. Cannot add meters later [D7]. Readers are free anyway, so only builders need seats, and those are few. | EUR 990 is a high first step for a team of two or three; fewer start. No way to grow with a customer except Enterprise. | Revenue is hard to foresee, for us and for the buyer's budget. It charges for building, which is what we want customers to do. Not built. |

Reading the table:

- **Cash break-even is not the question**: two Team customers at list cover the cash cost in every option. The
  question is the 8 to 16 customers that carry one person, and the 200 support hours at 100 customers, which is a
  second person or a product that needs less help.
- **With a launch discount of 40% on year one** for everyone, option A needs about 18 customers instead of 11 to carry
  one person in that year.
- A and B bring in about the same at this mix. A is simpler to buy and already built; B earns more only from
  customers with many builders, and those are Enterprise conversations anyway.
- C earns most per customer on paper and loses the small team, which is where the first customers are.
- D is the only one where a quiet month costs the customer less, and the only one that needs a build round and a
  privacy change. It can be added to A later, because A is flat rate; it cannot be added to B.

## 5. A launch plan

### 5.1 List price and launch discount

1. **Publish the real list price** on the production offer (section 3.5, whatever numbers the founder sets). That is
   the price a buyer who never talks to us pays after the trial, and the price every discount is counted from.
2. **Launch discount: a private offer per customer**, mechanism A in 2.5. Proposal to test: **40% off the list price
   for the first 12 months, for organisations that subscribe before a fixed date** (proposal: 30 June 2027), on the
   1-year term paid monthly. The customer gets the offer in the Azure portal, accepts, and Microsoft bills the lower
   amount; the 3% is on the lower amount [D17].
3. **How it is shown honestly.**
   - One sentence on `/pricing` and in the trial's last-week notice: the list price, the launch price, the last day to
     subscribe at it, and that after 12 months the subscription continues at the list price then in force.
   - The list price is a real price: it is what the public plan costs, in Marketplace, from day one. No crossed-out
     price that nobody could have paid.
   - One end date. If it is extended, say so once, with the new date, and say that it was extended. No rolling "ends
     soon". Swedish marketing law (marknadsföringslagen) applies between companies too; a time limit that is not real
     is misleading. Ask the lawyer who reads the terms to read this sentence as well.
   - Never "certified", "partner" or "endorsed by Microsoft" next to the price (`CONTRIBUTING.md`).
4. **How it ends.** Nothing has to be done: after the private offer's end date a customer with auto-renew is "charged
   at the list price of the public plan" [D18]. Two things to manage:
   - Auto-renew is **off by default** on a private offer, and then the subscription ends on the end date [D18]. So 60
     days before each customer's end date the founder writes to them: renew at list (switch on recurring billing), or
     accept a renewal offer.
   - A percentage discount follows the list price: "If the price changes after the private offer is created, the
     discount is applied to the latest retail price" [D14]. Do not raise the list price in the launch year without
     meaning it for the discounted customers too.
5. **How it is extended.** Per customer: a new private offer for the next term, at a smaller discount (proposal: 20%
   in year two for the first ten customers, then list). Mark it as a renewal when creating it, for the halved fee
   [D3]. For everyone: move the date on `/pricing` and keep making offers.
6. **If self-service buyers matter sooner than expected**: mechanism B. Lower the public price to the launch price
   (effective the first of next month), say on `/pricing` what the price will be and from when, and publish the
   increase at least 90 days ahead, at least four days before a month ends [D11]. Do not combine B with new private
   offers on the same plan, or the 40% lands on the lowered price [D14].

Why not the other mechanisms: a private "founding" plan cannot be ended without a 90-day increase and does not work
through CSP [D13][D31]; Marketplace's free trial would be a second trial [D33].

### 5.2 The 1-month plan

Keep it, about 20% above the 1-year price, with no launch discount. It is the honest answer to "can we leave?" and the
reason the 1-year price is the lower one. A customer cannot move between the two with a plan change
(`docs/BILLING-MODEL.md`, section 4), so the choice is made at purchase. Learn suggests one plan can carry both
durations, since a plan "supports only one billing frequency for a contract duration" (`docs/BILLING-MODEL.md` [B1])
and more durations can be added [D7]; try that on the DEV offer, because it halves the number of plan ids.

### 5.3 The early-adopter path: a pilot with services

The first pilot can be a company that is itself a Microsoft partner and wants to go from no data platform to an
advanced Fabric setup. That is two things sold together, and they should be priced apart: **services** by Kruse
Consulting AB (people's time, invoiced by Kruse Consulting), and the **subscription** (the product, through
Marketplace). Nothing about such a company is written in this repository.

| Step | What | Price (proposal to test) | How it is paid |
| --- | --- | --- | --- |
| 0. Scoping | A 30-minute call and a written scope: one business question, the sources, what "done" means | 0 | – |
| 1. Fixed-scope pilot | The scope of `docs/PILOT.md` widened to a first platform: a workspace layout, one source landed, keys and relationships reviewed, one data product built and verified, hand-over. About 8 to 10 days of work over 4 to 6 weeks. | a fixed price, **SEK 95,000 to 140,000** (about SEK 12,000 to 14,000 a day); the small guided pilot in `docs/PILOT.md` stays at its SEK 15,000 proposal | invoice from Kruse Consulting AB, half at start, half at hand-over |
| During the pilot | The pilot's tenant is in `trial_exempt_tenants`, so no trial clock runs and nothing is gated | 0 | – |
| 2. Subscription, year one | The plan that fits, on the 1-year term | list price, minus the **pilot credit**: half the pilot fee, at most half of year one at list, if the company subscribes within 60 days of hand-over | a private offer with that percentage, 12 months [D17]. The 3% is on the reduced price. |
| 3. Setup and migration | More sources, the SAP pack fitted, a migration from an old BI tool, training | by the day, or a fixed price per package once two have been done | invoice from Kruse Consulting AB |
| 4. Year two | Renews at list, or a renewal offer (5.1, point 5) | list | Marketplace |

A worked example with the proposals above, not an offer: a pilot at SEK 120,000; Business in Sweden at list is SEK
10,900 × 12 = SEK 130,800; the credit is SEK 60,000 (half the pilot, under the cap of SEK 65,400); year one costs SEK
70,800, which is a private offer of 46% off for 12 months. The credit replaces the launch discount; it is not added to
it.

Why credit half and not all: with the whole fee credited, year one is close to free and the subscription's price is
never tested. Why a cap: so a large services job cannot zero out the product.

**The pilot company as a reseller or a referrer.** Three ways, from least to most set-up:

1. **Referral, outside Marketplace.** A written agreement: a fee for a customer they introduce who subscribes
   (proposal to test: 15% of the first year's net subscription, invoiced to Kruse Consulting AB when the customer has
   paid). Marketplace has no referral fee of its own (Not on Learn). Simple, and it works from the first day.
2. **Multiparty private offer.** We set the partner price (proposal to test: 15 to 20% below list), they set the
   customer's price and Microsoft invoices the customer and pays both [D22][D23][D24]. Sweden is supported for the
   customer and for the channel partner; Switzerland was not on 13 November 2026 [D22]. What the partner needs in
   its own Partner Center account is on [D24]. Worth setting up when the first joint customer exists, not before.
3. **CSP.** If they are a CSP: authorise them as a specific CSP partner and give the margin with a CSP private offer
   [D27][D29]. They then invoice their customer themselves. Day-based trials, private plans and customer private offers
   do not work for customers who buy through a CSP [D5][D31][D21]; and choose "Specific partners", never "Any partner",
   which cannot be undone [D29].

Their own use comes first: they are a customer before they are a channel, and what they pay as a customer should not
depend on what they later sell.

## 6. Recommendation

1. **Option A: flat rate per organisation, sized by users** (Team up to 5, Business 6 to 25, Enterprise by private
   offer). It is what the code already does, what a prospect asked for, what an administrator can buy in one step, and
   the only choice that keeps meters possible later. Per user closes that door and adds seat administration for a
   product whose readers are free.
2. **Keep the cap soft at launch.** The `plan_over_cap` event starts a conversation about Business or Enterprise;
   blocking a sixth user in a paying team does not. Revisit after ten customers.
3. **No feature tiers at launch**; every subscriber has every tool. Enterprise differs by users, terms, and people.
4. **Two terms**: 1 year paid monthly as the main price, 1 month about 20% higher.
5. **Prices per market from one EUR reference and a written index** (3.5), round local numbers, reviewed twice a year.
6. **List price public; the launch discount by private offer**, one end date, a clean return to list (5.1).
7. **Pilots and services invoiced by Kruse Consulting AB**, with a capped credit against year one given as a private
   offer (5.3). A referral agreement first; a multiparty private offer when there is a joint customer.
8. **Before any of it**: replace the estimates in section 1 with the Azure invoice, and test five to ten prices in
   conversations. The numbers here are a place to start arguing from.

What would change this recommendation: three conversations in which the buyer asks for a per-user price (then B, and
decide before publishing); a first customer with more than 25 builders (then set the Enterprise floor from that
conversation); the Workload Hub bringing buyers who subscribe without talking to us (then mechanism B for the
discount).

## 7. Decisions for the founder before the production offer's plans are created

| # | Decision | Can it be changed later? | Recommended |
| --- | --- | --- | --- |
| 1 | Pricing model: flat rate or per user | **No** [D5] | flat rate |
| 2 | The production offer id and alias, and each plan id | **No** [D12][D5] | `krusgraph`; `team`, `business` (no prices or sizes in an id) |
| 3 | The user sizes: 5 and 25, or others; soft or hard cap | Yes (our code and `plan_user_caps`) | 5 and 25, soft |
| 4 | The reference prices for Team and Business, and the Enterprise floor | A decrease in a month; an increase in 90 days [D11] | test first; section 3.4 is a starting point |
| 5 | Terms offered: 1 year paid monthly, 1 month, or both; the 1-month premium | Durations can be added, **not removed** [D7] | both; about 20% |
| 6 | Markets at launch and the index per market | Markets can be added; prices as in 4 | the eight, with section 3.5's index |
| 7 | The launch discount: size, length, last day, and whether by private offer (A) or a lower public price (B) | Yes; a published increase cannot be moved [D14] | A; 40%, 12 months, one date |
| 8 | Pilot: the fixed price, the credit rule and its cap; who is in `trial_exempt_tenants` | Yes | half the fee, at most half of year one |
| 9 | Channel: a referral fee; CSP "No partners" or "Specific partners" (never "Any partner") | "Any partner" **cannot be undone** [D29] | referral agreement; CSP "No partners" at launch |
| 10 | Legal and money: Standard Contract or own terms; the DPA with a lawyer; insurance; the payout currency; Frontier Accelerate free or Premium | Mostly yes | a lawyer before the first paid subscription; payout in SEK if Partner Center offers it (**Not on Learn** for a Swedish company) |

## 8. Partner Center steps, in order

The production offer is a **separate offer** from `krusgraph-dev`. **Never select Go live on the DEV offer**: "Don't
ever select Go live for a development/test offer" [D35]. Purchases in preview are real for both offers [D32].

**On the DEV offer first (rehearsal, preview only):**

1. Create a test plan with the chosen pricing model. Enter a USD price, **Save draft**, **Export pricing data**,
   change two markets, **Import pricing data**; confirm the pricing section says "Market pricing" [D5].
2. Try both terms (1 month; 1 year paid monthly) inside one plan. Note whether Partner Center accepts it.
3. Buy it from a test tenant through the preview link; check the webhook's plan id and the row in the table; cancel
   within 72 hours (`docs/MARKETPLACE-SETUP.md`, section 5).
4. Change the price in preview to see the flow; in preview it is not a price change [D14].

**The production offer:**

1. Partner Center → Marketplace offers → **+ New offer → Software as a Service**. Offer id and alias (decision 2; they
   cannot be changed [D12]). "Sell through Microsoft": yes.
2. **Offer setup, Properties, Offer listing, Preview audience** (up to 10 e-mail addresses by hand [D30]),
   **Technical configuration**: as `docs/MARKETPLACE-SETUP.md`, section 3, with the production landing page, webhook
   and Entra app. The listing's publisher name must match the workload manifest
   (`docs/WORKLOAD-LISTING-AND-PAYMENT.md`, 1c).
3. **Plan overview → + Create new plan**, once per plan [D5]:
   - Plan id (cannot be changed) and plan name.
   - **Plan listing**: name and description. Only what runs today, with the status words of `tool_status.py`; the
     number of users; that reads and dry runs are free without a plan.
   - **Pricing and availability**:
     - **Markets → Edit markets**: select the launch markets (decision 6).
     - **Auto activation**: as tested on the DEV offer.
     - **Pricing**: Flat rate. The contract durations and payment options (decision 5). A USD price for each.
       **No custom meter dimension.**
     - **Save draft → Export pricing data →** enter the local prices of section 3.5 for each market and duration
       **→ Import pricing data**.
     - **Free trial**: off (our own trial is the trial).
     - **Plan visibility**: Public for Team and Business. A public plan cannot be made private again [D5]. If unsure
       about a plan, publish it private to our own tenant first and make it public later.
4. **Resell through CSPs**: "No partners in the CSP program" at launch (decision 9) [D29].
5. **Review and publish → Publish**. Wait for certification and the preview link. Buy once from a test tenant at the
   real price in each of two markets to check the local prices; open a support ticket within seven days to have the
   test paid out without the fee, or cancel within 72 hours [D32].
6. **Go live** on the production offer only.
7. Put the plan ids and sizes in `deploy/krusgraph.json` (`plan_user_caps`), the offer link in
   `marketplace_offer_url`, the pilot tenants in `trial_exempt_tenants`; set `"trial": true` and deploy
   (`docs/BILLING-MODEL.md`, section 5). Update `/pricing`, `/terms` and `/privacy` first
   (`docs/MARKETPLACE-SETUP.md`, section 6).
8. **For each launch customer**: Partner Center → Marketplace offers → **Private offers → + New private offer →
   Customer private offer** (the labels as recalled; follow [D17] on screen). Enter the customer's billing account id
   (they find it in the Azure portal, Cost Management + Billing); a price adjustment to the public plan, the
   percentage; start on acceptance; the end date 12 months on; an accept-by date; submit. It cannot be edited
   afterwards, only withdrawn before acceptance [D17]. Ask the customer to check eligibility first with Microsoft's
   pre-check [D20].
9. **Each 1 May and 1 November**: the currency review (3.5, rule 3). **60 days before each private offer ends**: the
   renewal letter (5.1, point 4).

## 9. What was not verified

- Every Azure unit price, the Fabric capacity price in Sweden Central, and every comparable tool's price: none of the
  pages could be opened from here (see the top). The founder's invoice and a browser fix this in an hour.
- Prices of other workloads in the Fabric Workload Hub: not found.
- Consultant rates for Norway and Finland, and the budget thresholds in 3.3: guesses.
- Insurance and lawyer costs: estimates with no quote behind them.
- Whether one plan can carry both terms; whether a customer who pays by card can accept a private offer (Learn asks
  only for "a valid payment instrument" [D20]); the longest a private price can run; whether a Swedish company can be
  paid out in SEK: **Not on Learn**, to try on the DEV offer or ask Partner Center support.
- Learn contradicts itself on the auto-renew default (off for all SaaS subscriptions [D34], yet trials "convert"
  [D33]) and on term lengths (`docs/BILLING-MODEL.md`, 3.4). Check on a real test purchase what the renewal switch
  shows.
- No price here has been shown to a buyer.

## Sources

Read on learn.microsoft.com on **15 November 2026**. `B` =
`https://learn.microsoft.com/en-us/partner-center/marketplace-offers/`. The date is the page's own `ms.date`.

| # | Page | `ms.date` |
| --- | --- | --- |
| D1 | B + `marketplace-commercial-transaction-capabilities-and-considerations` | 2026-07-22 |
| D2 | B + `marketplace-faq-publisher-guide` | 2025-05-09 |
| D3 | B + `agency-fee-discount-for-renewals` | 2026-03-25 |
| D4 | B + `private-offers-for-channel` | 2026-05-08 |
| D5 | B + `create-new-saas-offer-plans` | 2026-07-22 |
| D6 | B + `plan-saas-offer` | 2026-07-22 |
| D7 | B + `plans-pricing` | 2026-07-22 |
| D8 | B + `marketplace-geo-availability-currencies` | 2026-01-21 |
| D9 | B + `commercial-marketplace-fx-faq` | 2026-06-05 |
| D10 | B + `tax-details-marketplace` | 2026-11-04 |
| D11 | B + `price-changes` | 2025-01-13 |
| D12 | B + `create-new-saas-offer` | 2026-07-22 |
| D13 | B + `update-existing-offer` | 2025-01-08 |
| D14 | B + `price-changes-faq` | 2025-06-01 |
| D16 | B + `isv-customer` | 2026-10-27 |
| D17 | B + `manage-isv-customer-private-offers` | 2026-10-27 |
| D18 | B + `isv-customer-faq` | 2026-10-27 |
| D19 | B + `private-offers-api` | 2026-03-10 |
| D20 | `https://learn.microsoft.com/en-us/marketplace/private-offers-pre-check` | 2026-09-11 |
| D21 | `https://learn.microsoft.com/en-us/marketplace/private-offers-eligibility-report` | 2025-01-23 |
| D22 | B + `multiparty-private-offers-overview` | 2026-11-13 |
| D23 | B + `multiparty-private-offers-for-isvs` | 2026-07-17 |
| D24 | B + `multiparty-private-offers-for-channel-partners` | 2026-07-14 |
| D25 | B + `multiparty-private-offers-faq` | 2026-07-14 |
| D27 | B + `isv-csp-reseller` | 2026-08-18 |
| D28 | B + `isv-csp-faq` | 2026-04-02 |
| D29 | B + `cloud-solution-providers` | 2025-05-28 |
| D30 | B + `create-new-saas-offer-preview` | 2025-01-29 |
| D31 | B + `private-plans` | 2026-03-30 |
| D32 | B + `plan-saas-dev-test-offer` | 2025-01-29 |
| D33 | B + `saas-free-trials` | 2026-07-23 |
| D34 | B + `pc-saas-fulfillment-life-cycle` | 2026-07-22 |
| D35 | B + `test-publish-saas-offer` | 2025-01-29 |
| D36 | B + `payout-policy-details` | 2025-10-22 |
| D37 | B + `payment-thresholds-methods-timeframes` | 2025-10-22 |
| D38 | `https://learn.microsoft.com/en-us/fabric/extensibility-toolkit/how-to-monetize-workload` | 2025-12-15 |
| D39 | `https://learn.microsoft.com/en-us/fabric/workload-development-kit/monetization` | 2026-04-29 |
| D40 | `https://learn.microsoft.com/en-us/azure/container-apps/billing` | read for the free grant |
| D41 | `https://learn.microsoft.com/en-us/azure/container-apps/custom-domains-managed-certificates` | read for the certificate |
| D42 | `https://learn.microsoft.com/en-us/partner-center/frontier-accelerate-marketplace/faq` | 2026-11-03 |
| D43 | `https://learn.microsoft.com/en-us/partner-center/referrals/co-sell-overview` | 2026-10-05 |
| D44 | `https://learn.microsoft.com/en-us/partner-center/referrals/manage-co-sell-opportunities` | 2026-10-28 |

Read and not cited for a fact of their own: D2 (repeats the 3%), D4 ("the partner creating the private offer pays the
3% Marketplace agency fee"), D6, D28. Also read: `resale-enabled-offers-overview` (2026-05-08),
`pc-saas-fulfillment-subscription-api` (2026-07-22), and the two Fabric publishing-requirement pages cited in
`docs/WORKLOAD-LISTING-AND-PAYMENT.md`.

Not Microsoft, and not opened (search snippets only, 15 November 2026): the tool vendors' price pages named in 3.2;
Brainville via konsultguiden.se; freelancermap's Freelancer-Kompass; itjobswatch.co.uk; Eurostat's price level index
2025 through a news article; the Bank of Finland and ECB reference rates.
