# Learning design: how Krusgraph gets smarter from use, without AI inside it

Round LS2, 21 November 2026, finishing round L1. **A design: nothing in this file is built** unless a row says so and
names the file. No Fabric call was made for it. Microsoft Learn pages were opened on 21 November 2026; each is cited
with its `ms.date` and its "last updated" date as the page showed them.

It builds on, and does not repeat:

- [DECISION-RULES.md](DECISION-RULES.md): a team's accepted or rejected key or link becomes a rule for that tenant
  (built by L1, local MCP server only, unit tests only).
- [DOMAINS-DESIGN.md](DOMAINS-DESIGN.md) part 4 (shared entities) and part 5 (smarter from use, the closed list of
  rule shapes, where rules are stored, privacy).
- [SMOOTH/COMBINE-SOURCES.md](SMOOTH/COMBINE-SOURCES.md) (SM1): one product lakehouse with one schema per source,
  match rules M0 to M4 with counts, what a person decides, the conformed gold.
- [MULTI-SOURCE.md](MULTI-SOURCE.md) (rules X0 to X3 across items), [DATA-PRODUCT-CATALOG.md](DATA-PRODUCT-CATALOG.md)
  (DP1: 30 classic data products, the packs mapped to them), [PACKS.md](PACKS.md) (the knowledge packs),
  [CATALOG-ACCELERATOR.md](CATALOG-ACCELERATOR.md) (`publish_catalog`), [DATA-AGENT-TOPICS-TEMPLATES.md](DATA-AGENT-TOPICS-TEMPLATES.md)
  (DA2), [EVOLUTION.md](EVOLUTION.md) (the case record) and [LANDSCAPE.md](LANDSCAPE.md) (what other MCP servers do).

## 0. What "smarter" means here

One thing: **a fact that was established once, by a count on the rows or by a person's decision, is not asked again;
it shapes the next proposal; and the proposal says where it came from.** Nothing is trained, scored by a model or
guessed. Every rule is a stored decision or a published fact, applied in a fixed order, and the rows are counted
again before anything is called true ("rows outrank rules", DECISION-RULES.md section 2).

| Knowledge | Example | Who approves it | Kept where | Leaves the tenant? | Status |
| --- | --- | --- | --- | --- | --- |
| A key or a link inside one source | `orders.ship_to_id → addresses` accepted | a person in the team (a role) | the tenant's decision store | no | **built** locally (DECISION-RULES.md) |
| A join across systems (part A) | SAP customer number = CRM account's ERP number field | the data product owner, or a steward for a shared entity | the tenant's rule book | no | design |
| A public identifier shape (part A) | a VAT id is a country prefix and digits | Kruse Consulting, in a reviewed pack | a public pack in this repository | it is public already | design |
| A process template (part B) | order to cash needs customer, product, order, delivery, invoice, open item, payment | Kruse Consulting, in a reviewed template | a public template in this repository | it is public already | design; the catalog under it is **built** (DP1) |
| What is written back into Fabric (part C) | the evidence line in an item's description | the person who taps Create | the customer's own Fabric items | no (it is in their tenant) | partly built: `publish_catalog`, DA2 topics, the create tools |
| A decision that helps the next team (part D) | Sales' `dim_customer` offered to Service | the owner of the entity, then the consumer | the tenant's rule book and the contracts | no | design (SM9, DOMAINS-DESIGN part 4) |
| What other MCP servers do (part E) | an idea from another server | Gustav, per idea | [LANDSCAPE.md](LANDSCAPE.md) | it is public | the scan is a monthly routine |

The rest of this file says how each row works.

## A. Cross-system join knowledge

### A1. What a join rule is

A join rule says that a column in one system holds the same identifier as a column in another, after fixed
normalisation steps, and keeps the counts that showed it. It extends the decision record of DECISION-RULES.md section
1 with a third kind, `join` (today the store accepts `key` and `link` only, `fabric_backend/decisions.py`).

| Field | What it holds |
| --- | --- |
| `left`, `right` | system label, object, column on each side: `sap.KNA1.KUNNR`, `crm.Account.SAP_Customer_No__c`. Names only |
| `rule` | the match rule of COMBINE-SOURCES.md section 2: **M0** declared crosswalk, **M1** same official identifier, **M2** counted overlap, **M3** conformed public code list. **M4** (name only) is never stored as a join |
| `normalise` | the fixed steps applied to both sides, from a closed list: trim, upper case, strip separators, strip leading zeros, add or remove a country prefix. No fuzzy matching, no edit distance |
| `evidence` | distinct values on each side, values found on both, only on the left, only on the right, the date, and a digest of the counting SQL. **Counts only, never a value** |
| `decision`, `role`, `at`, `reason` | as for keys and links: accepted or rejected, the role (steward, owner, engineer, analyst, reviewer), when, a short reason |
| `scope` | `product` (one data product), `domain` or `tenant` (promoted, part D) |
| `source` | `decided` (a person in this tenant), or `pack:<id>@<version>` (a public pack proposed it, part A3) |
| `status` | `proposed`, `accepted`, `rejected`, `questioned` (the overlap fell since it was accepted, or it was rejected twice elsewhere) |

### A2. Examples, and which kind of knowledge each is

| Pair | Rule | Whose knowledge | Why |
| --- | --- | --- | --- |
| `KNA1.KUNNR` ↔ a CRM account field the integration fills with the SAP number (`Account.SAP_Customer_No__c` in SM1's synthetic fixture) | M0 | **the tenant's only** | The field is the customer's own custom field. No pack can name it (DATA-PRODUCT-CATALOG.md, "Products that cross sources") |
| `KNA1.STCEG` ↔ `Account.VAT__c` | M1, VAT id | the pair is the tenant's; the shape "a VAT id" is public | Which SAP field holds the VAT id is in the SAP pack's sources; the CRM side is usually a custom field |
| `LFA1.STCEG` ↔ a supplier's VAT id in a purchasing tool | M1 | the same | Procure to pay's version of the same idea |
| `KNA1.KUNNR` ↔ `account.accountnumber` (Dataverse) | M2, counted overlap after stripping leading zeros | the tenant's | A number system the customer chose; only the counts can show it |
| `VBAK.WAERK` ↔ `Account.CurrencyIsoCode` | M3, ISO 4217 | public | Every value is in a published code list; becomes one `dim_currency` |

What the person sees is the sentence of COMBINE-SOURCES.md section 2, for example "37 800 match on VAT id after
normalising. 1 150 only in SAP, 3 400 only in the CRM", and one tap to accept, with Undo.

### A3. The lifecycle of a join rule

1. **Proposed by a rule.** The match rules M0 to M3 run between entity tables the per-source plans already know (a
   counted key). They propose candidate pairs with counts. Nothing is accepted by itself.
2. **Decided by a person.** One tap, the default being the highest-certainty rule whose overlap holds (M0 before M1
   before M2), as COMBINE-SOURCES.md section 3 says. The decision is stored with its counts and role.
3. **Reused.** The next plan in the same tenant (the same product, or another product that can read the rule book,
   part D) proposes the pair directly as rule `decided` and says so: "joined on VAT id, accepted by a steward on 21
   November 2026; counted again now: 37 790 match".
4. **Counted again on every run.** The product's check notebook counts the overlap on each run
   (COMBINE-SOURCES.md section 4). A drop beyond a fixed threshold is a health warning and marks the rule
   `questioned`; it keeps working until a person decides again. Rows outrank rules.
5. **Undone.** Undo keeps the row as history, as for keys and links.

### A4. Optional shared public packs: what may be in them, and what may not

A **join pack** is a public file in this repository, reviewed like the other packs (PACKS.md: `review_status`,
sources with `accessed` and `verified`, a synthetic fixture). It can hold:

- **Identifier families with a deterministic shape check**: VAT ids (a country prefix and a country-specific pattern),
  national organisation numbers with a check digit (the Swedish *organisationsnummer*), GLN (13 digits, mod-10 check
  digit), LEI (20 characters, ISO 17442, mod-97 check), IBAN (ISO 13616, mod-97 check), DUNS (9 digits). Each family
  names the public standard it rests on; the round that builds the pack reads and cites each one. A shape check says a
  value *looks like* a VAT id. It never says that two rows are the same company: only the overlap count can say that.
- **Which standard field of a known system usually carries which family**, from that system's public documentation,
  read by the means PACKS.md allows (never by scraping a vendor's documentation portal): `KNA1.STCEG` and `LFA1.STCEG`
  for VAT ids in SAP; "usually a custom field: ask" for systems that have no standard one.
- **Public code lists for M3** (ISO 4217 currencies, ISO 3166-1 countries, UN/ECE Recommendation 20 units), cited.

It never holds: a customer's custom field names, a tenant's decision, a count from a customer, a value, or the name of
anyone who decided anything. A pack proposes; a tenant's rows and a tenant's person decide.

### A5. Learning across customers: still not proposed

Unchanged from DECISION-RULES.md section 5: nothing leaves a tenant. If Gustav ever wants it, the only form this design
would accept is opt-in per tenant, under a DPA that names it, carrying only the shape of a rule between two *published
standard* fields (for example "`KNA1.STCEG` was accepted as a VAT id join in *n* tenants"), shown only once *n* is at
least five, with no tenant, person, reason, count or custom name. Until then, what travels between customers is what
Kruse Consulting writes into a public pack by hand.

## B. Knowledge of data products and ontology patterns

### B1. Templates per process, on top of the catalog

DP1's catalog (`fabric_backend/data_products/catalog.yaml`, built) holds 30 data products with grain, business key,
conformed dimensions, measures with their level, traps and questions. A **process template** groups products into
what a business asks for and adds what the catalog does not have: the ontology's entities and relationships, the
semantic model's shape, the data agent's first questions, and the checks that must hold.

| Template | Products (catalog names) | Shared entities and conformed keys | Ontology (entities → relationships) | The trap it guards | First questions (agent topics, DA2) |
| --- | --- | --- | --- | --- | --- |
| **Order to cash** | Customer, Product or material, Sales order, Delivery, Customer invoice, Receivables, Payment; Date, Currency | Customer, Product; dates and currencies conformed (M3) | Customer → places → Order → has lines → Product; Order → shipped in → Delivery; Order → billed by → Invoice → settled by → Payment | header amounts summed over lines (the total that doubles); deliveries and invoices at line grain | revenue per customer per month; open receivables per customer; orders not yet invoiced |
| **Procure to pay** | Supplier, Product or material, Purchase order, Goods receipt, Supplier invoice, Payables, Payment | Supplier, Product; supplier VAT id (M1) | Supplier → receives → Purchase order → received as → Goods receipt; Supplier invoice → matches → Purchase order line | three-way match counted per line, not per header | spend per supplier; invoices without a goods receipt; open payables by due date |
| **Customer 360** | Customer, Account (CRM), Contact, Opportunity (pipeline), Case or ticket, Sales order, Customer invoice | Customer as the shared entity; the crosswalk `xref_customer` (part A) | Customer ↔ Account (same party, by the accepted join rule); Account → has → Opportunity, Case | facts from two systems never joined to each other row by row (COMBINE-SOURCES.md section 4) | revenue and open opportunities per customer; customers only in the CRM; cases per customer |

Each template is the order of work for SM7's combined product: which products to look for, which entity is shared,
which join rule to ask for, which facts stay apart.

### B2. How a template is applied

1. The packs map the tables they know (`mapping.yaml`); DP1's proposed matcher maps the rest by names, key patterns,
   graph position and row checks, deterministically.
2. The template answers coverage in one line, from counts: "Order to cash: 5 of 6 products present; delivery
   missing, so late-delivery questions cannot be answered" (DATA-PRODUCT-CATALOG.md, proposal 2).
3. The ontology is drafted with the template's entity names and relationship names, bound to the gold tables, one
   namespace per data product (DOMAINS-DESIGN.md part 4). The semantic model gets the template's facts and
   conformed dimensions and no fact-to-fact relationship. The agent gets the template's questions as example queries
   and topics.
4. A person may rename anything. A rename is the decision shape "Name of a thing" of DOMAINS-DESIGN.md part 5: it
   stays a rule in that tenant and is proposed again there; it never changes the public template.

### B3. Where templates live and how they change

- A YAML file per template beside `catalog.yaml`, with a JSON schema, `review_status` (`proposed` until the
  maintainer has reviewed it), `sharing: public-synthetic`, and a synthetic fixture whose `EXPECTED` the tests check,
  as PACKS.md does for packs.
- A template changes only through a reviewed pull request in this repository. Nothing a customer decides flows into a
  template. Sources other than general data-modelling knowledge are cited with URL and licence, and only pointed at.

## C. What is written back into Fabric, through documented APIs only

Knowledge is most useful where Fabric's own agents read it: item descriptions, tags, the ontology, the semantic
model's descriptions and the data agent's instructions. Microsoft's Fabric IQ MCP server, the ontology's MCP endpoint
and the data agent MCP server all serve what is in those items to any agent (section E). So writing the evidence
there makes Fabric answer better without Krusgraph in the loop.

Rule: Krusgraph writes only through an API that has a Learn page, only after a dry run that shows the exact text, and
only on the second tap. A preview API is named as preview in the dry run.

| What | How (documented API) | Learn page (ms.date / last updated, as read 21 Nov 2026) | What Krusgraph writes | In code today |
| --- | --- | --- | --- | --- |
| Item description | Items - Update Item (`description`) | [Update Item](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/update-item) (2022-12-28 / 2026-11-17) | at most 256 characters ending with the dated evidence line ("4 of 4 keys unique, 0 orphan rows over 3 links, checked 17 Nov 2026") and, for a combined product, the accepted join ("customers joined on VAT id, accepted 21 Nov 2026") | `publish_catalog` (CA1), unit tests only, not run against Fabric |
| Tags | Tags - Apply Tags; the tags themselves are defined by an admin | [Apply Tags](https://learn.microsoft.com/en-us/rest/api/fabric/core/tags/apply-tags) (2022-12-28 / 2026-09-15); [Tags in Microsoft Fabric](https://learn.microsoft.com/en-us/fabric/governance/tags-overview) (2026-03-11 / 2026-03-18) | `Krusgraph` and the product's name; never a health word, because a tag has no date | `publish_catalog`, unit tests only |
| Ontology entities, relationships, bindings, descriptions | the ontology item definition | [Ontology (new) item definition](https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/ontology-definition) (2026-09-10 / 2026-09-29); ontology is **preview** ([What is ontology](https://learn.microsoft.com/en-us/fabric/iq/ontology/overview), 2026-10-16) | the template's entity names (B1), each entity's key and the join rule it rests on in its description | `create_ontology`: unit tests; created live on 28 October 2026 (`tool_status.py`) |
| Semantic model descriptions | the semantic model definition (TMDL) | [SemanticModel definition](https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/semantic-model-definition) (2024-05-17 / 2026-03-18) | table and column descriptions with the rule behind each relationship | `create_semantic_model`: unit tests; created live on 29 October 2026 |
| Data agent instructions and example queries | the data agent item definition (`fewshots.json` and the data source files) | [Data Agent item definition](https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/data-agent-definition) (2026-01-21 / 2026-02-11) | the template's questions with the SQL over checked joins | `create_data_agent`: creating by unit tests only |
| Data agent topics | Staging - Upload Datasource Topic, **preview**, SQL sources on the preview runtime only | [Upload Datasource Topic](https://learn.microsoft.com/en-us/rest/api/fabric/dataagent/staging/upload-datasource-topic) (2022-12-28 / 2026-11-04); [Topics (preview)](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-topics) (2026-08-31 / 2026-09-10) | one topic per join and per trap, from the checked plan (DA2) | DA2, unit tests only |
| Shortcuts into the product lakehouse | OneLake shortcuts | [OneLake shortcuts](https://learn.microsoft.com/en-us/fabric/onelake/onelake-shortcuts) (2026-11-05 / 2026-11-08) | the schema shortcuts of COMBINE-SOURCES.md section 1 | not built (SM7, gap G5) |

**Not written by Krusgraph:** endorsement (a human act in Fabric), domain assignment (an admin's or a domain
contributor's act; Krusgraph lists it for the platform team), anything in Purview (a handover file, CATALOG-ACCELERATOR.md),
a column description in a lakehouse table (no documented API was found for it; the description goes into the semantic
model and the ontology instead), and anything whose API has no Learn page.

**What the written text holds:** names, rule ids, counts, dates and roles. Never a row value, never a person's name
unless the tenant's own setting shows names to its own people (DOMAINS-DESIGN.md part 5, privacy).

## D. How a decision in one team helps the next team

The roles are DOMAINS-DESIGN.md's: domain owner, data product owner, steward, platform team. Krusgraph grants none of
them; it records which role decided, and shows who is next.

| Step | What happens | Who decides | What the next team sees |
| --- | --- | --- | --- |
| 1. One team | Sales builds "Sales 360" over SAP and the CRM (SM7). The customer join on VAT id is accepted; `Customer` is owned by this product (`shared: true` in its contract) | Sales' data product owner | nothing yet |
| 2. The rule is promoted | The same join accepted on three products (a count, shown), or a steward promotes it at once: "Make this a domain rule?" | a steward | the rule in the domain's or tenant's rule book, with its decisions |
| 3. A second team | Service plans its case system. Its customer column overlaps Sales' `dim_customer`. Krusgraph proposes a reference, not a second customer: "Your cases point at 4 812 customers; 4 790 are in Sales 360's Customer. Use it?" (COMBINE-SOURCES.md section 5) | Service's data product owner | one tap: Service's gold reads Sales' `dim_customer` through a shortcut; Service's own properties go in its own namespace |
| 4. Many teams | The register of shared entities is read from the contracts. A conflict between two claimants is shown with counts and decided by a steward. An owner's key change is a major version that lists every consumer first | stewards, owners | the portfolio per Fabric domain (DOMAINS-DESIGN.md part 1) |
| 5. The platform team | One list of what only an admin can do, generated from the dry runs: tenant settings, domains, capacity, workspace roles | platform team | the list, nothing done for them |

**Privacy, the same at every step:**

- No row value leaves the tenant. Rules and join records hold names, counts, dates, roles and short reasons.
- The rule book lives in the customer's tenant (a Krusgraph Model item the platform team names, DOMAINS-DESIGN.md part
  5), so Fabric's own permissions decide who can read and change it. Krusgraph's hosted service stores none of it
  (BILLING-MODEL.md).
- Columns that `privacy.py` masks are never written into a rule by name.
- A team that cannot read another product's rule book gets no proposal from it. Knowledge flows only where Fabric
  already lets the person read.

What Krusgraph does not claim: it does not make an organisation a data mesh, it does not replace a role, and it
certifies nothing. It counts, proposes, records who decided, and counts again.

## E. Learning from the outside: other MCP servers and Microsoft's own

- **The scan.** A monthly routine (private procedure; the public result is [LANDSCAPE.md](LANDSCAPE.md)) lists new and
  changed MCP servers, reads each licence from its `LICENSE` file, and proposes ideas. It never builds and never copies
  code. An idea becomes work only after Gustav's yes (LANDSCAPE.md, Process 6), and code from another project only
  under CONTRIBUTING.md, "Reusing external code".
- **Microsoft's own servers are where the written-back knowledge is read.** Fabric IQ MCP (generally available per
  its page, ms.date 2026-11-10), the ontology's MCP endpoint (preview, ms.date 2026-11-06) and the data agent MCP
  server (ms.date 2026-09-03) serve semantic models, ontologies and agents to any agent. Krusgraph's job in that
  picture is to make sure what they serve rests on checked joins (`docs/COMPANION-MCP.md`).
- **Microsoft's skills** (microsoft/skills-for-fabric, MIT) are how-to knowledge for coding agents. They are read for
  what Fabric expects; nothing is copied without the reuse rules.

## F. Build order (each one round, each with a measurable "done")

Nothing here is approved. The order follows SM1's PLAN.md: the engine work after SM7.

| Order | What | Done when | Size | Depends on |
| --- | --- | --- | --- | --- |
| 1 | Join rules as a decision kind `join` in the local store, with M0 to M3 evidence | on SM5's synthetic multi-lakehouse fixture, an accepted VAT id join is proposed as `decided` in the next plan and counted again; undo restores the earlier proposal; the same input gives the same plan (golden) | M | SM7's match rules |
| 2 | The rule book item in the tenant (DOMAINS-DESIGN.md part 5, second round), promotion and the questioned mark | a second product in the fixture reads the first one's accepted join; a steward's promotion is an audit row; a fall in overlap marks the rule questioned | M | 1 |
| 3 | Process templates for order to cash, procure to pay and customer 360, with the coverage answer | the three templates load and validate; the SAP full demo answers "Order to cash: n of 7 products present" from counts, byte for byte against a golden file | M | DP1's matcher |
| 4 | Evidence and join text in descriptions, ontology, model and agent topics through the existing create tools' dry runs | each dry run shows the evidence line and the join rule in the text it would write; no API is called that lacks a Learn page (a test lists them) | S–M | 1, 3 |
| 5 | A public identifier pack (shape checks for VAT id, organisation number, GLN, LEI, IBAN, DUNS) with cited standards | each check passes the standard's own published examples and rejects altered ones; the pack's sources are read and dated | S | none |

Not proposed: learning across customers (A5), fuzzy matching, any model that predicts a join.
