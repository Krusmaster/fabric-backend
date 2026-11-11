# Trust and pricing pages: Modern Requirements and Krusgraph compared

Round n212, 11 November 2026. The founder asked for a comparison with a vendor that sells through Microsoft's
marketplace: Modern Requirements (modernrequirements.com), a requirements-management tool for Azure DevOps. The aim is
to learn what such a vendor shows a buyer publicly, and to list improvements to Krusgraph's `/trust` and `/pricing`
that are honest for Krusgraph today. Their text and design are described here, not copied. Nothing here says anything
about Modern Requirements beyond what the sources below show, and nothing claims a partnership with or endorsement by
them or Microsoft.

## How this was read

**The vendor's site could not be opened from this session.** `www.modernrequirements.com` and
`marketplace.visualstudio.com` did not resolve (they are outside the session's allowed network). To read them first-hand,
these hosts must be allowed in the session's network settings: `www.modernrequirements.com`,
`marketplace.visualstudio.com`, `appsource.microsoft.com` and `azuremarketplace.microsoft.com`. Everything about Modern
Requirements below comes from web search results that quote or summarise their pages, and is marked **[snippet]**. A
snippet can be out of date or mis-summarised; re-read each page before quoting it to anyone.

| # | Page (as the search results gave it) | What the snippet said it holds | Read |
| --- | --- | --- | --- |
| S1 | https://www.modernrequirements.com/pricing/ | Tiers with "request pricing" / quote buttons rather than prices | [snippet], 11 Nov 2026 |
| S2 | https://www.modernrequirements.com/form/request-a-quote-4/ | A quote request form | [snippet], 11 Nov 2026 |
| S3 | https://www.modernrequirements.com/wp-content/uploads/2024/10/CP-vs-CP-Plus.pdf | The AI add-on's two tiers, a per-user monthly price billed annually, a token allowance per user | [snippet], 11 Nov 2026 |
| S4 | https://www.modernrequirements.com/?p=13110 (a press release) | A SOC 2 attestation after an audit by a named audit firm, December 2022 | [snippet], 11 Nov 2026 |
| S5 | https://modernrequirements.com/standards/ | Standards the product helps customers work with (ISO 26262, ISO 27001, SOC 2, HIPAA, GDPR and others) as requirement templates | [snippet], 11 Nov 2026 |
| S6 | https://www.modernrequirements.com/blogs/soc-2-compliance-in-devops/ | A blog post on SOC 2 in DevOps work | [snippet], 11 Nov 2026 |
| S7 | https://www.modernrequirements.com/privacy-policy/ | A privacy policy (personal information, GDPR, analytics, cookies) | [snippet], 11 Nov 2026 |
| S8 | A blog post on AI security and data privacy for the AI add-on (`/blogs/ai-security-and-data-privacy-with-copilot4devops/`) | Customer data not used to train models; the AI can be switched off by an admin | [snippet], 11 Nov 2026 |
| S9 | https://www.g2.com/products/modern-requirements4devops/pricing and Capterra / Software Advice listings | Third parties say the core product has no public price; figures for the AI add-on disagree with S3 | [snippet], 11 Nov 2026; third party |

## What Modern Requirements shows publicly [snippet]

| Topic | What the snippets show | Source |
| --- | --- | --- |
| Certifications and attestations | A press release (December 2022) on a SOC 2 attestation after an external audit. Search found no ISO/IEC 27001 certificate, no current SOC 2 report date and no trust centre page. A page title mentions ISO 9001 (quality, not security). The standards page lists frameworks the product helps customers manage requirements for, which is a product feature, not the vendor's own certification | S4, S5 |
| How evidence is offered | Not seen: no download, no "report on request" route was found in the snippets | — |
| Policies | A privacy policy. Not found in search: a data processing agreement, a sub-processor list, a vulnerability disclosure policy, an SLA, a status page | S7 |
| Data handling | The core product works inside the customer's own Azure DevOps (cloud) or Azure DevOps Server (on premises), so its data lives where the customer's Azure DevOps lives; an on-premises edition is offered when data must stay on site | S9, search summaries |
| AI | An AI add-on that uses OpenAI / Azure OpenAI; the vendor says customer data is not used to train models and an admin can turn the AI off. Which service and region is not stated in the snippets | S8 |
| Pricing model | Core product: tiers with no public price, a quote form instead. AI add-on: a per-user, per-month price billed annually, with a token allowance per user, in a PDF; review sites show other figures | S1, S2, S3, S9 |
| Trial | A free trial (30 days in the snippets), in a vendor sandbox or the customer's own Azure DevOps | search summaries |
| Marketplace | Listed on Microsoft's marketplaces (Visual Studio Marketplace, AppSource); how billing runs there could not be checked | search summaries |
| What a buyer meets first | Inferred, not observed: a home page that leads with a long Microsoft relationship and a free trial; security material sits in blog posts and a press release rather than one trust page | inference |

## What Krusgraph shows publicly

| Topic | Krusgraph today | Where |
| --- | --- | --- |
| Certifications | None, said in the first lines of `/trust`; a Standards table (n212) with one row each for ISO/IEC 27001, NIS2 and the Swedish cybersecurity act, GDPR and Microsoft's publisher requirements: what exists, what does not, what comes next | `/trust`, `docs/TRUST-PACK.md` §9 |
| Evidence | Everything is public and linked: the ISO 27001 self-assessment, the supplier pack, the incident process, the DPA draft, the attestation draft, the code itself (MIT) | `/trust`, GitHub |
| Policies | Privacy policy, vulnerability disclosure policy and security.txt, preview terms, a DPA draft (not signed), no SLA (said) | `/privacy`, `/security`, `/terms`, `docs/DPA-DRAFT.md` |
| Data handling | No table contents stored; a table of what passes through and what is kept, where and for how long; one region (Sweden Central); one sub-processor (Microsoft Azure); self-hosting in the customer's own Azure | `/trust`, `/it`, `/privacy` |
| AI | Krusgraph for Fabric uses no AI model; on the MCP path the customer's own AI client gets the answers under their own agreement; Krusgraph trains no model | `/trust`, questionnaire row 11 |
| Security questionnaire | 30 standard questions answered on the page, with Today / Planned / Open | `/trust` |
| Crawlers | robots.txt asks AI training crawlers out, allows search and answer fetchers (n212) | `/robots.txt`, `/trust` |
| Pricing model | Check and connector free; Pilot and Team "Contact us", quoted after a call, invoiced in SEK or EUR; a Marketplace team plan planned with no price yet | `/pricing` |
| Trial | No time-limited trial: the free parts are free; the Fabric workload is open to guest users in the publisher's tenant only | `/pricing`, `docs/GUEST-TRIAL.md` |

In short: the vendor appears to rely on one external attestation and a large product, with little policy material
found; Krusgraph has no external attestation but publishes far more of its own material, including what is missing.
Krusgraph should not try to look like a certified vendor; it should make its openness faster to read.

## Five improvements to /trust and /pricing, honest for Krusgraph today

Each is a proposal for a later Website round; none is done in n212 apart from the Standards table and the crawler
sentence.

1. **A one-screen summary at the top of `/trust`.** A short table before everything else: certification (none), the
   ISO 27001 self-assessment (exists, link), data stored (no table contents), region (Sweden Central), sub-processors
   (Microsoft Azure only), DPA (draft), penetration test (not done), how to report a problem (link). A buyer then has the
   answer to the first five questions without scrolling past the data tables. The words stay the ones already on the
   page.
2. **A document list with a date and a status per document.** One row each for the trust pack, the self-assessment,
   the supplier pack, the incident process, the DPA draft, the attestation draft and the disclosure policy: what it is,
   last updated (the commit date), status (in place, draft, proposal). Where the vendor appears to point at a report a
   buyer must request, Krusgraph can say "public, no NDA needed", which is true.
3. **"Last reviewed" on `/trust`, and changes kept visible.** A line at the top with the date the page was last checked
   against the code, and a link to the CHANGELOG entries that changed it. Procurement teams want to know the page is
   kept; the repository already records every change.
4. **`/pricing` says the pricing model in one line, even without a price.** For example: free parts free for good;
   Pilot a fixed scope, quoted after a 30-minute call, invoiced in SEK or EUR; Team per agreement; a Marketplace plan
   later, which will show its price and currency on `/pricing` and in the listing (Microsoft's certification policy asks
   the listing for the price and currency: `docs/MARKETPLACE-CERTIFICATION-NOTES.md`). No number is invented; if the
   founder sets a pilot price or a range, it goes here.
5. **`/pricing` says how to try each product, and where the data lives for each.** A small table: Check (in the browser,
   nothing uploaded), Krusgraph for Claude (free, the admin approves the app once, hosted in Sweden Central or in your
   own Azure), Krusgraph for Fabric (guests in the publisher's tenant until `Krusgraph.Modeler` is registered). The
   vendor makes the trial the main call to action; Krusgraph's equivalent is that most of it is free already, which
   `/pricing` should say plainly next to where the data goes.

## Keeping this true

The [snippet] rows are re-read first-hand once the hosts above are allowed, with the date, and any row that differs is
corrected or removed. The Krusgraph column changes when `/trust` or `/pricing` changes.
