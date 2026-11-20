# Combining several sources into one data product, by rules (SM1 design, 20 November 2026)

**The case.** SAP holds orders and customers. A CRM such as Salesforce holds accounts, opportunities and cases. The
business wants one question answered over both, for example "revenue and open opportunities per customer". It wants one
semantic model, one ontology and one data agent over both, published as one data product. Today Krusgraph builds each
of these over one source only (MULTI-LAKEHOUSE.md).

**The constraints.**
- No AI inside Krusgraph: every match is a rule with a count.
- Nothing is created without a dry run and a second tap.
- No row values in answers: counts only.
- The person decides what the rules cannot know.

This design builds on `docs/MULTI-SOURCE.md` (rules X0-X3 across items), `docs/DOMAINS-DESIGN.md` (roles, contract,
shared entities) and `docs/CATALOG-ACCELERATOR.md` (publishing to the OneLake catalog).

## 1. Where the data meets: one product lakehouse, one schema per source

The simplest layout that every Fabric engine reads is the recommended one. Each source keeps its own lakehouse and its
own silver (layouts (a) or (b)). A **product lakehouse** gets one **schema shortcut** per source silver schema, plus a
`gold` schema of its own:

```
sales_product_lh (schema-enabled)
  sap   -> schema shortcut to sap_lh.sap_silver      (no copy)
  crm   -> schema shortcut to crm_lh.crm_silver      (no copy)
  gold  -> conformed dimensions, crosswalks, facts (written by the pipeline)
```

Why this layout:

- Shortcut tables are read by the SQL analytics endpoint, by Spark and by Direct Lake (Learn, *OneLake shortcuts*,
  ms.date 2026-11-05).
- Krusgraph's existing one-item machinery then applies unchanged:
  - one SQL connection;
  - two-part names (`sap.KNA1`, `crm.Account`);
  - one Direct Lake on SQL model;
  - one ontology binding;
  - one agent data source.
- The engine change is gap G4 in MULTI-LAKEHOUSE.md: a plan over several schemas of one item.
- No data is copied. Deleting a shortcut leaves the source unchanged.
- One caveat: under Direct Lake on SQL, the model's owner identity reaches the shortcut target, not the viewer's. The dry
  run must say so, and Learn names Direct Lake on OneLake as the way round it.

Krusgraph proposes the shortcuts in the dry run ("2 schema shortcuts in sales_product_lh: sap -> sap_lh.sap_silver, crm
-> crm_lh.crm_silver; nothing copied") and creates them on the second tap. In a workspace whose sources are already
schemas of one lakehouse (layout (c)), there is nothing to create.

## 2. How entities are matched across sources: rules with counts

Matching runs only between tables that the per-source plans already know as entity tables (a counted key, K1-K3). It
proposes *candidate pairs*, for example `sap.KNA1` ↔ `crm.Account`, and *candidate key pairs* for each.

| Rule | Evidence | Example | Certainty |
|---|---|---|---|
| **M0 declared** | A crosswalk the person already has (a mapping table, or an external-id field the CRM fills from SAP) | `crm.Account.SAP_Customer_No__c` → `sap.KNA1.KUNNR` | 1.0 after the overlap count |
| **M1 same identifier** | A column on each side whose name and pattern say it is the same official identifier: VAT id (`KNA1.STCEG`, `Account.VAT__c`), organisation number, GLN, DUNS, IBAN prefix. Values normalised by fixed steps: trim, upper case, remove spaces and separators, add or remove the country prefix | `SE556677889901` = `556677-8899` after normalising | 0.9 when the overlap holds |
| **M2 counted overlap** | Any pair of key-shaped columns with compatible types, where the share of distinct values found on the other side is high after the S1 normalisation (trim, case fold, leading zeros stripped) | `KNA1.KUNNR` `0000100023` = `Account.AccountNumber` `100023` | 0.6 → 0.9 with ≥ 95 % overlap and ≥ 50 distinct values |
| **M3 conformed dimension** | Both sides hold a code from the same public list: currency (ISO 4217), country (ISO 3166-1), unit of measure (UN/ECE Rec. 20), calendar date | `VBAK.WAERK` and `Account.CurrencyIsoCode` → one `dim_currency`; dates → one `dim_date` | 1.0 when every value is in the list |
| **M4 name only** | Same column name, no overlap counted | `Name` ↔ `NAME1` | **never used for a match**; shown as "not a key: names are not identifiers" |

Every proposed match shows its counts and nothing else. The card says it in at most 25 words:

> "SAP has 38 950 customers, the CRM 41 200 accounts. 37 800 match on VAT id after normalising. 1 150 only in SAP,
> 3 400 only in the CRM."

The counts come from one query per candidate key pair on the product lakehouse's SQL endpoint (two schemas, one
connection). The number of queries is capped, as `max_items` caps them today. Fuzzy name matching is out of scope: it
is not a rule a person can check, and it would be AI by another name.

## 3. What a person decides (and nothing else)

Each decision is one tap, with a default chosen for the person and Undo available:

| Decision | Default Krusgraph proposes | Why a person |
|---|---|---|
| Which match rule makes two rows the same customer | The highest-certainty rule whose overlap holds (M0 > M1 > M2) | Business meaning: a VAT id can be shared by two legal units |
| Which source is the master per entity (survivorship) | The source with the most distinct keys for that entity; per property, "master first, the other when the master's is empty" | Ownership of the truth |
| What happens to rows found on one side only | Kept, flagged `only_in = 'sap'` or `'crm'`; never dropped | Whether "only in CRM" means a prospect or an error |
| The product's name, owner and domain | `<domain>_<entity>` from the workspace's Fabric domain, if any; the owner is the signed-in person | Accountability (DOMAINS-DESIGN.md part 2) |
| Which question it answers first | The requirement the person pasted (RQ1), otherwise "per customer: revenue, open opportunities, open cases" | The business question |

What Krusgraph decides itself, without asking:
- the conformed dimensions from public code lists (M3);
- the surrogate keys;
- the grain of each fact, from the per-source totals rules (header vs line amounts, WB1 and AP2);
- naming;
- the build order.

## 4. What Krusgraph builds (dry run first, then one Create per item)

| Item | Content |
|---|---|
| Schema shortcuts | One per source silver schema into the product lakehouse (section 1) |
| `gold.xref_customer` | The crosswalk: `customer_key`, `sap_kunnr`, `crm_account_id`, `match_rule`, `matched_on` (column name, never a value), `only_in` |
| `gold.dim_customer` | One row per conformed customer. Properties follow survivorship; each property's source is recorded as a column-level description |
| `gold.dim_date`, `gold.dim_currency`, `gold.dim_country` | Conformed dimensions (M3) |
| `gold.fact_sales` (SAP), `gold.fact_opportunity` (CRM), ... | Per-source facts re-keyed to `customer_key`, at their own grain; never joined to each other row by row (no doubled totals across sources) |
| Check notebook | The existing row checks, plus: crosswalk unique per side, every fact row finds its `customer_key` or is counted as "unmatched", the overlap counts again on each run (a drop is a health warning) |
| Semantic model | One Direct Lake model over `gold`: facts from both sources share the conformed dimensions, measures per fact, no relationship between facts |
| Ontology | Entity `Customer` bound to `gold.dim_customer`; `Order` and `Opportunity` linked to it; each source's own entities in their own namespace |
| Data agent | One data source (the product lakehouse's `gold`), with the questions from section 3 as example queries |
| Data product in the OneLake catalog | `publish_catalog`: description with the dated evidence line ("37 800 of 41 200 accounts matched on VAT id, checked 20 Nov 2026"), tags, the ODCS contract with both sources as inputs, the Purview handover file. Endorsement stays a human act in Fabric |

## 5. From one team to several

The four roles are those of DOMAINS-DESIGN.md: domain owner, data product owner, steward, platform team. Krusgraph
grants none of them; it records names and shows who is next.

1. **One team.** One data product owner builds "Sales 360" over SAP + CRM in the Sales domain. `Customer` is owned by
   this product (`shared: true` in its contract).
2. **A second team.** Service builds over its case system. Krusgraph sees an entity table whose key overlaps Sales'
   `dim_customer`, and proposes to *reference* it rather than build a second customer: "Your cases point at 4 812
   customers; 4 790 are in Sales 360's Customer. Use it?" One tap: Service's gold reads Sales' `dim_customer` through a
   shortcut. Service's own properties go in its own namespace.
3. **Several domains.**
   - The register of shared entities is read from the contracts (no new item).
   - The steward decides a two-claimant conflict from the counts.
   - An owner's key change is a major version and names every consumer before approval.
   - The portfolio shows each product's step and health per Fabric domain.
4. **The platform team** sees one list of what only an admin can do: tenant settings, domains, capacity, workspace
   roles. It is generated from the dry runs.

What Krusgraph does not claim: it does not make an organisation a data mesh, it does not replace anyone's role, and it
does not certify anything. It counts, proposes, builds what was approved, and checks it again on every run.

## 6. Size

| Part | Effort | Depends on |
|---|---|---|
| Plan over several schemas of one item (G4) | M-L | |
| Schema shortcuts as a build step (G5) | M | |
| Match rules M0-M3 with counts, decisions in the flow state | M | G4 |
| Conformed gold (xref, dims, re-keyed facts) in the pipeline | M-L | the match rules |
| Model / ontology / agent over the conformed gold | S-M | the gold (one item, as today) |
| Reference a shared entity from a second product | M | DOMAINS-DESIGN part 4 |
