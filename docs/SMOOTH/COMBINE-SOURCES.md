# Combining several sources into one data product, by rules (SM1 design, 20 November 2026)

**Status (SM7, 21 November 2026).** Built in `fabric_backend/combine.py` and on the start card: rules M0, M1 and M2 with
counts (section 2), the match decision as one tap kept in the flow state (section 3), and the conformed gold
(`xref_customer`, `dim_customer`, re-keyed facts) as Spark SQL plus one semantic model dry run over it (section 4). Two
choices differ from the text below and are Gustav's to confirm: the **master** is the side the match points at (SAP's
KNA1 for M0), not the side with the most keys, because two CRM accounts may point at one SAP customer and a master per
account would give that customer two keys and double its SAP totals; and when the side pointed at has a tenant column
(MANDT) and the other has none, the match runs **within the tenant with the most rows**. Properties are carried per
source (`sap_LAND1`, `crm_Industry`); personal-data columns are left out.

**Status (ON1, 25 November 2026).** SAP and Dynamics 365 are matched the same way, and one shared ontology is drafted
over the result (section 7). Built: the customer match (KNA1 against Dataverse `account` or Business Central
`Customer`) and the product match (MARA against Dataverse `product` or Business Central `Item`), counted with the
ambiguous rows apart; the shared ontology as a `create_ontology` dry run once a match is accepted. Unit tests on a
synthetic SAP + Dataverse pair only; **not run against Fabric**. Not built yet (issue #152): schema shortcuts (G5), M3,
the gold in the pipeline (so creating the shared ontology answers `not_yet`), the agent over the combined sources,
catalog publish, survivorship choices, a matched or unioned Order and Invoice, and the Product decision on the start
card (it is accepted from the ontology dry run's action).

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

## 7. SAP and Dynamics 365, and one shared ontology (ON1, 25 November 2026)

Built in `fabric_backend/combine.py` (the matches) and `fabric_backend/shared_ontology.py` (the ontology). Unit tests
only (`tests/test_on1_shared_ontology.py`, on the synthetic pair `tests/fixtures/sap_dynamics.py`); **not run against
Fabric**.

**The matches.** The rules of section 2 now run per concept: `customer` (the party masters of DP1's catalog: SAP's
KNA1, Dataverse's `account`, Business Central's `Customer`) and `product` (the `product` masters: SAP's MARA,
Dataverse's `product`, Business Central's `Item`). Two additions, both by name:

- Dataverse names columns in lower case without separators. In such a name, a word ending in number, no, nr or num is
  read as its head and that identifier word, so `accountnumber` and `productnumber` are key-shaped (M2), and
  `new_sapcustomerno` names SAP (M0). Lookups ending in `id` are GUIDs and are never split.
- The columns Link to Fabric adds (`Id`, `IsDelete`, `SinkCreatedOn`, `SinkModifiedOn`, `versionnumber`) are never a
  candidate. Before ON1, Dataverse's `Id` was proposed against `KNA1.KUNNR`.

Every match is counted on the rows, two statements as before: matched, **ambiguous** (a row whose normalised number is
also held by another row of its side, or finds more than one row on the other side), only in one source, only in the
other. The rules never resolve an ambiguous row: the evidence says how many there are, and accepting the match stays
the person's tap. The start card's Check line is SM7's (`card_line`, ambiguous rows counted as matching);
`match_line` gives them apart.

On the synthetic pair (SAP demo plus two customers; Dataverse demo plus two accounts, `accountnumber` and
`productnumber`):

| Match | Rule | D365 rows | SAP rows | Matched | Ambiguous | Only in SAP | Only in D365 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `d365.account.accountnumber` → `sap.KNA1.KUNNR` | M2 | 6 (5 filled) | 6 | 3 | 2 accounts on one customer | 2 (one in client 200) | 1 |
| `d365.product.productnumber` → `sap.MARA.MATNR` | M2 | 3 (2 filled) | 4 | 2 | 0 | 2 (one in client 200) | 1 |

**The shared ontology.** `create_ontology` over a plan of several schemas, once a match is accepted on the path,
answers with one ontology instead of one per source:

- one entity type per concept DP1 names for a table: Customer, Product, Order, Invoice, Opportunity, Delivery, Case
  (masters and headers; lines and texts are not entity types yet);
- **shared** when the concept's match is accepted: `Customer` bound to `gold.dim_customer`, `Product` to
  `gold.dim_product` (the gold SQL of section 4, now also for products), keyed on the conformed key, recording both
  source tables and the counted match;
- **single-source** otherwise: one entity type per source table (`SapOrder`, `D365Order`). Orders and invoices exist
  in both systems but no rule says an SAP order is a Dynamics order, so none is guessed. Opportunity and Case come from
  Dataverse only, Delivery from SAP only;
- **relationships only where the plan proves them**: a transaction table re-keyed to `customer_key` points at the shared
  Customer (its own plan link to the party table, plus the accepted match); otherwise the plan's single-column links
  inside one source. Composite links, links into a table that is now part of a shared entity, and Dataverse's filtered
  lookups (`salesorder.customerid` where `customeridtype` is account) are listed under `notes`, not written.

On the pair, with both matches accepted: 9 entity types (Customer and Product shared; SapOrder, D365Order, SapInvoice,
D365Invoice, D365Opportunity, SapDelivery and D365Case from one source each) and 7 relationship types. The dry run
writes nothing; `dry_run=false` answers `not_yet` until the pipeline builds the gold the shared entity types bind to
(section 8 builds it). A match not yet accepted is offered as a `start` action in the dry run.

## 8. The shared gold and the shared ontology created (ON2, 25 November 2026)

Built in `fabric_backend/shared_gold.py`, `combine.gold_sql(..., apart=True)` and the combined branches of
`create_pipeline`, `create_ontology` and `verify_build` in `server.py`. Unit tests with a fake Fabric that records
writes (`tests/test_on2_shared_gold.py`), and the gold SQL run on SQLite over the synthetic pair; **not run against
Fabric**.

With a match accepted on the path, the order is: Decide, then `create_pipeline`, run it once, then `create_ontology`,
then `verify_build`. Each creating call is a dry run first, and changes Fabric only with `dry_run=false` after the
person's yes; a run starts only with `run_once` and the `confirm_jobs` code of its dry run.

- **The pipeline.** On a plan of several schemas with an accepted match, `create_pipeline` builds the shared gold
  instead of the per-table silver and gold: one notebook (`<name>_shared_gold`) and a pipeline with one Notebook
  activity, in the product lakehouse's workspace. The notebook runs the shared ontology's gold SQL in order
  (`xref_customer`, `dim_customer`, the re-keyed facts, `xref_product`, `dim_product`), all as Delta tables (the facts
  were views in section 4; the SQL analytics endpoint and the ontology's OneLake binding do not see a Spark view). It
  stops before anything is created when `gold` is a source schema or a table of these names exists that it did not
  create (the table property `krusgraph.gold`). Source tables are only read.
- **Ambiguous rows apart.** The gold keeps every ambiguous row apart exactly as section 7 counts it: a row of either
  side that is in more than one matching pair keeps its own key, with `ambiguous` true and `only_in` its own source;
  only one-to-one pairs share a key. The notebook's last cell counts the xref again (matched, ambiguous, only in each
  source), prints it beside the counts the person accepted, and fails the run when a source row has two keys, an
  ambiguous row was merged or a key is more than one row of its dimension. SM7's combined model (section 4) still drafts
  the earlier SQL, which joins an ambiguous row to its customer.
- **Create.** `create_ontology` with `dry_run=false` reads the product lakehouse's `gold` schema on the SQL analytics
  endpoint (the same connection that counts the matches). When every table and column the shared entity types bind is
  there, it creates the shared ontology through the same create path as every ontology (POST, or updateDefinition of
  an ontology of that name), with the dry run's definition. Otherwise it answers `not_yet`, lists what is missing and
  names the step that comes first: `create_pipeline` with the same workspace, source and schema.
- **Verify.** `verify_build` with `items={"ontology": name}` on the same path reads the created ontology back and
  compares it with the shared dry run (entity types, keys, bindings, relationship types). The graph is still the
  person's step in Fabric, as for every ontology.

On the synthetic pair, run on SQLite: `gold.dim_customer` 9 rows (3 matched pairs, the 2 ambiguous accounts and SAP
customer 13 each on their own, 1 only in Dynamics 365, 2 only in SAP), `gold.dim_product` 5 rows (2 matched, 1 only in
Dynamics 365, 2 only in SAP), each fact with as many rows as its source table.

Not built: the combined semantic model (SM7) still answers `not_yet`; its card and counts merge an ambiguous row, so
moving it onto this gold is more than a small change. Not run against Fabric: the notebook, the pipeline and the
ontology create are checked with a fake Fabric; Fabric's own Spark and ontology have not seen them.
