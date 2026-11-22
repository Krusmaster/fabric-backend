# A catalog of classic data products, and what the packs cover of it

Round DP1, 21 November 2026. Design, data and a gap report; no matcher for unknown tables yet, no change to the site,
the tools or the Krusgraph Model item, and no call to Fabric.

**What this rests on.** The catalog is written from general data-modelling knowledge (facts and dimensions, grain,
business keys). The mapping of the packs' tables to it rests on the packs, and the packs rest on public documentation
and synthetic demos (docs/PACKS.md). Nothing here has been verified on a customer system. Where a table outside a pack
is named below (in "What is missing"), it is named from general knowledge and has not been checked.

The goal, in Gustav's words: "Vi vill kunna ge rekommendationer på dataprodukter för alla tabeller som kan tänkas
finnas". The way there is to start from the data products a business usually wants and the keys that make them
unique, map the systems' raw tables to them, and only then (next round) suggest products for tables nobody has mapped.

## The files

| File | What it is |
| --- | --- |
| `fabric_backend/data_products/catalog.yaml` | The catalog: 30 products, each with its grain, business key, conformed dimensions, measures with their level, traps, questions, and the table roles it needs. |
| `fabric_backend/data_products/catalog.schema.json` | Its JSON schema (draft 7). |
| `fabric_backend/data_products/mapping.yaml` | Every table of the four packs mapped to the catalog, or listed as not a data product with a reason. |
| `fabric_backend/data_products/mapping.schema.json` | Its JSON schema. |
| `fabric_backend/data_product_catalog.py` | The loader, the checks (`catalog_problems`, `mapping_problems`) and the coverage per source (`coverage`, `matrix`, `matrix_markdown`). |
| `tests/test_dp1_data_product_catalog.py` | Checks the schema, the loader, the mapping against the pack manifests, the matrix below against the code, and the wording. |

No licensed industry data model was copied or consulted for the catalog, and no other model is cross-referenced in this
round. A later cross-reference to an open model would cite its URL and licence, and only point at it.

## The catalog in plain words

A **data product** here is a set of tables that answers one kind of business question with a promise about its rows:
what one row is (the **grain**) and which columns make a row unique (the **business key**). The key names are generic
(`tenant_id`, `order_number`, `line_number`); the mapping says which column of each system plays that part.
`tenant_id` stands for the system's client, company or organisation column; a system with one organisation per
landing (Salesforce, Dataverse) has none.

| Product | Area | Grain (one row is) | Business key |
| --- | --- | --- | --- |
| Customer | master data | one customer (a party that buys and is billed), per client or tenant | `tenant_id`, `customer_number` |
| Supplier | master data | one supplier (a party we buy from and pay), per client or tenant | `tenant_id`, `supplier_number` |
| Product or material | master data | one product, material or item that is sold, bought or stocked | `tenant_id`, `product_number` |
| Employee or user | hr | one person who works for the organisation (an employee, or a user or sales representative in an application) | `tenant_id`, `employee_number` |
| Organisation and company | master data | one organisation unit (a company or legal entity, a sales or purchasing organisation, a plant, a business unit, a team) | `tenant_id`, `organisation_type`, `organisation_code` |
| Chart of accounts (G/L accounts) | finance | one general ledger account in one chart of accounts | `tenant_id`, `chart_of_accounts`, `account_number` |
| Cost centre and profit centre | finance | one cost centre or profit centre in one controlling area, for one validity period | `tenant_id`, `controlling_area`, `cost_object`, `valid_to` |
| Currency and exchange rate | reference | one currency, and for rates one currency pair, rate type and date | `currency_code` |
| Date (calendar) | reference | one calendar day | `calendar_date` |
| Sales order (header and line) | sales | one line of a sales order (product, quantity, price); the header holds customer, dates and status | `tenant_id`, `order_number`, `line_number` |
| Delivery (outbound shipment) | supply chain | one line of a delivery (a quantity of a product shipped from a plant for an order line) | `tenant_id`, `delivery_number`, `line_number` |
| Customer invoice (billing) | finance | one line of an invoice or credit memo sent to a customer | `tenant_id`, `invoice_number`, `line_number` |
| Receivables and payables (open and cleared items) | finance | one open or cleared item on a customer or supplier account (an invoice, credit memo or payment line not yet or already settled) | `tenant_id`, `company`, `fiscal_year`, `document_number`, `line_number` |
| Payment | finance | one incoming or outgoing payment, and which invoices it settles | `tenant_id`, `payment_number` |
| General ledger journal entry | finance | one line of a journal entry (an account, an amount, a debit or credit) in one ledger | `tenant_id`, `ledger`, `company`, `fiscal_year`, `document_number`, `line_number` |
| Budget and plan | planning | one planned amount for an account or cost centre (or a product and customer), a period and a plan version | `tenant_id`, `plan_version`, `period`, `account`, `cost_object` |
| Purchase order (header and line) | procurement | one line of a purchase order (a product or service, quantity and price from a supplier) | `tenant_id`, `purchase_order_number`, `line_number` |
| Goods receipt | procurement | one received quantity of a product against a purchase order line, on a date | `tenant_id`, `receipt_document_number`, `fiscal_year`, `line_number` |
| Supplier invoice | procurement | one line of an invoice received from a supplier, often matched to a purchase order line | `tenant_id`, `invoice_document_number`, `fiscal_year`, `line_number` |
| Inventory movement and stock | supply chain | one movement of a quantity of a product in or out of a location; stock on a date is the running sum (or a snapshot table) | `tenant_id`, `movement_document_number`, `fiscal_year`, `line_number` |
| Price and condition | sales | one price (or discount) for a product, possibly per customer, price list and currency, valid for a period | `tenant_id`, `price_list`, `product_number`, `currency`, `valid_from` |
| Account (CRM) | crm | one company (or person) the sales team works with, whether or not it has bought | `tenant_id`, `account_id` |
| Contact | crm | one person at an account or customer | `tenant_id`, `contact_id` |
| Lead | crm | one prospect (a person or company) not yet qualified | `tenant_id`, `lead_id` |
| Opportunity (pipeline) | crm | one potential sale to an account, with its lines (products) when they are used | `tenant_id`, `opportunity_id` |
| Quote | sales | one line of a formal offer to a customer | `tenant_id`, `quote_number`, `line_number` |
| Case or ticket (customer service) | service | one customer question, problem or request | `tenant_id`, `case_id` |
| Marketing campaign | marketing | one campaign, and its members (the leads and contacts it reached) | `tenant_id`, `campaign_id` |
| Activity (calls, meetings, tasks, e-mails) | crm | one logged activity about a record (an account, a contact, an opportunity, a case) | `tenant_id`, `activity_id` |
| Subscription or contract | subscription | one subscription (or contract) with its charges, in the version valid on a date | `tenant_id`, `subscription_number`, `version` |

Each product also says which **table roles** it needs. A sales order needs a header and a line; a customer needs a
master table; a goods receipt needs a header and a line; a payment needs a payment table (a link from invoices to
clearing documents alone is a bridge, not the payment). The roles are: header, line, master, extension (a master's rows
per company or sales area), text (one row per language), version (a row per validity period or change), bridge (a link
table: partners, contact roles, campaign members, clearing), schedule_line, status, flow (the links from one document
to the next) and snapshot.

The traps are typed, so a later round can explain them by kind: a header amount repeated on every line, versions with
valid-from and valid-to, soft deletes, several companies or clients, currencies, a type column that mixes document
kinds, double counting across ledgers or copies, signs, identity across systems, personal data, text per language,
leading zeros, hierarchies, a fiscal calendar, polymorphic lookups.

## How the packs map to it

Every table of the four packs (sap with its CDS views, salesforce, dynamics365 with Dataverse and Business Central,
younium_salesforce) has a row in `mapping.yaml`: the product, its role there, how its key columns map to the product's
business key, a confidence, and the evidence the pack itself gives:

- **verified**: every source the pack cites for the table was opened and read (Microsoft Learn, Salesforce's developer
  documentation). The Dataverse, Business Central and Salesforce tables are here.
- **partly_verified**: some were. The SAP CDS views are here (SAP's list of released views was read; the views' own
  pages were not).
- **unverified**: none was. The SAP tables (help.sap.com could not be reached) and the Younium tables are here.

Read is not tested: "verified" says the documentation was read, not that a system was seen.

A table can belong to more than one product (VBAK holds sales orders and quotations; VBFA links orders, deliveries and
invoices). Seven tables are no data product of their own: ADR2 and ADR6 (phone numbers and e-mail of an address), T685
(condition types), COUNTRY_REGION and DIMENSION_SET_ENTRY (helpers), and two classic products this catalog does not hold
yet: EBAN (purchase requisition) and the Salesforce ASSET (installed base).

The test fails when a table in a manifest is neither mapped nor listed, when a mapped table is not in its manifest,
when a key names a column the pack does not name for that table, or when the evidence written differs from the pack's
sources. So a pack that gains a table cannot be merged without a decision about the table's place in the catalog.

## Coverage per source

A cell is **full** when the source has a table, mapped with high confidence, for every role the product needs;
**partial** when a role has no table ("no header") or only a table mapped with medium confidence ("master weak": a user
table standing in for employees); "–" when no table maps to the product; **generated** for the date table, which no
source holds. The sources are the packs' modules: SAP tables and SAP CDS views are one pack, Dataverse and Business
Central another, and Younium with Salesforce reads nine Salesforce objects from the Salesforce pack.

<!-- matrix:start -->
| Product | SAP ERP and S/4HANA tables | SAP S/4HANA released CDS views | Salesforce standard objects | Dynamics 365 Sales and Customer Service (Dataverse) | Dynamics 365 Business Central | Younium with Salesforce |
| --- | --- | --- | --- | --- | --- | --- |
| Customer | full | full | – | – | full | full |
| Supplier | full | full | – | – | full | – |
| Product or material | full | full | full | full | full | full |
| Employee or user | – | – | partial (master weak) | partial (master weak) | partial (master weak) | – |
| Organisation and company | full | full | – | full | – | – |
| Chart of accounts (G/L accounts) | full | – | – | – | – | – |
| Cost centre and profit centre | full | – | – | – | – | – |
| Currency and exchange rate | – | – | – | partial (master weak) | – | – |
| Date (calendar) | generated | generated | generated | generated | generated | generated |
| Sales order (header and line) | full | full | full | full | full | full |
| Delivery (outbound shipment) | full | full | – | – | – | – |
| Customer invoice (billing) | full | full | – | full | full | full |
| Receivables and payables (open and cleared items) | full | – | – | – | full | – |
| Payment | partial (no header) | – | – | – | partial (no header) | full |
| General ledger journal entry | full | full | – | – | full | – |
| Budget and plan | – | – | – | – | – | – |
| Purchase order (header and line) | full | – | – | – | full | – |
| Goods receipt | partial (no header, line weak) | – | – | – | partial (no header, line weak) | – |
| Supplier invoice | full | – | – | – | – | – |
| Inventory movement and stock | – | – | – | – | full | – |
| Price and condition | partial (no master) | – | full | full | – | full |
| Account (CRM) | – | – | full | full | – | full |
| Contact | full | – | full | full | – | full |
| Lead | – | – | full | full | – | – |
| Opportunity (pipeline) | – | – | full | full | – | full |
| Quote | full | full | full | full | full | – |
| Case or ticket (customer service) | – | – | full | full | – | – |
| Marketing campaign | – | – | full | – | – | – |
| Activity (calls, meetings, tasks, e-mails) | – | – | full | full | – | – |
| Subscription or contract | – | – | partial (no line, header weak) | – | – | full |
<!-- matrix:end -->

In numbers (of 30 products; date is generated everywhere):

| Source | Full | Partial | None |
| --- | --- | --- | --- |
| SAP ERP and S/4HANA tables | 15 | 3 | 11 |
| SAP S/4HANA released CDS views | 9 | 0 | 20 |
| Salesforce standard objects | 11 | 2 | 16 |
| Dynamics 365 Sales and Customer Service (Dataverse) | 12 | 2 | 15 |
| Dynamics 365 Business Central | 10 | 3 | 16 |
| Younium with Salesforce | 10 | 0 | 19 |

## What cannot be built today, per source, and why

The hints are in `mapping.yaml` under `not_in_pack`; table names there that are not in a pack come from general
knowledge and are marked as not checked.

**SAP tables.** Strong on order to cash, finance and procure to pay. Cannot build:
- *Inventory movement and stock*: the material documents (MKPF/MSEG in ECC, MATDOC in S/4HANA) and the stock tables
  are not in the pack. For the same reason *goods receipt* is only partial: the purchase order history (EKBE) shows
  receipts against an order, but the receipt document itself is missing.
- *Payment*: only the clearing link (AUGBL in the cleared items) is there; the payment is a journal entry of its own
  document type, which can be read from BKPF/BSEG but is not marked as such.
- *Price*: the condition records (KONH, KONP) and the conditions applied on documents (KONV, PRCD_ELEMENTS) are there,
  but the condition tables that say which product and customer a record is for are not.
- *Employee, currency, budget*: HR, the currency and exchange-rate tables and the plan data are not in the pack.
- *Lead, opportunity, CRM account, case, campaign, activity, subscription*: these live in a CRM or subscription system,
  not in SAP ERP's tables.
- Column level, as RQ1 found on the demo (docs/REQUIREMENTS-TO-FABRIC.md): *delivery* is full by tables, but "late
  deliveries" needs the actual goods issue date (`LIKP.WADAT_IST`), which the demo does not have.

**SAP CDS views.** The pack has views for master data, order to cash and the journal. Purchasing, open items, pricing
and controlling are read from the tables.

**Salesforce.** Strong on CRM, marketing and service. No customer (the account is the CRM account, see below), no
invoice, payment, ledger, delivery, purchasing or inventory: billing lives in another system. *Subscription* is
partial: a Contract has no charges or versions. *Employee* is partial: a User is not an HR employee.

**Dynamics 365 Dataverse.** Like Salesforce, plus invoices (the Sales invoice tables). No campaign in the pack, no ERP
side. *Currency* is partial: the currency table is there, the exchange rates are a column of each record.

**Dynamics 365 Business Central.** Strong on the ERP side. Cannot build *delivery* (posted shipments are not in the
pack), *supplier invoice* (posted purchase invoices), *chart of accounts* (the G/L Account table), *budget*, *cost
centre* (dimension values), *organisation* (a company is the `COMPANY` column, not a table). *Payment* is partial:
payments are customer ledger entries of a document type, applied to invoices in the detailed entries. *Goods receipt*
is partial: the item ledger's purchase entries give the quantities, not the receipt document.

**Younium with Salesforce.** Subscription, invoice and payment are full; so are the nine Salesforce objects the pack
reads (account, contact, opportunity, order, product, price book, contract). No ledger: Younium hands invoices to an
accounting system.

**Nowhere today:** *budget and plan*. No pack has plan data.

## Products that cross sources, and the key that would join them

A business question often needs one product from two systems: revenue per CRM segment needs the invoice (ERP or
billing) and the account (CRM). That needs a **conformed key**: a column in one system that holds the other system's
key, checked on the rows.

| Product | Where it lives | Conformed key today | What exists |
| --- | --- | --- | --- |
| Customer ↔ CRM account | Younium `ACCOUNTS` and Salesforce `ACCOUNT` | `ACCOUNTS.EXTERNAL_CRM_ID` = `ACCOUNT.ID` | In the younium_salesforce pack, as a relationship and the trap `two_accounts` (a name match is not the link; a Younium-only account has no Salesforce row). The engine plans it when both land in one schema. |
| Subscription ↔ opportunity | Younium `SUBSCRIPTIONS` and Salesforce `OPPORTUNITY` | `SUBSCRIPTIONS.EXTERNAL_CRM_ID` = `OPPORTUNITY.ID` | In the same pack. |
| Customer ↔ CRM account | SAP `KNA1`/`BUT000` and Salesforce or Dataverse `ACCOUNT` | none in any pack | Integrations usually keep the ERP number in a custom CRM field or the CRM id in an ERP field; which one is the customer's choice, so no pack can name it. |
| Customer ↔ CRM account | Business Central `CUSTOMER` and Dataverse `ACCOUNT` | none in the pack | The same: a link exists only if an integration writes one. |
| Product | SAP `MARA`, Business Central `ITEM`, Salesforce `PRODUCT2`, Dataverse `PRODUCT`, Younium `PRODUCTS` | none across systems | Each system's own number; a shared product code is a convention, not a key the packs know. |
| Sales order ↔ invoice | Salesforce `ORDER` and SAP `VBRK`, or Dataverse `SALESORDER` and Business Central | none | Same as the customer. |

docs/MULTI-SOURCE.md is the design for links across items. Today the engine plans one source and one schema; tables
from two systems are planned together only when they sit in one lakehouse (shortcuts work). Its rules X0–X3 would
find a conformed key: X2 by name and type, X3 by counting the share of values that exist on the other side. Nothing of
X2/X3 is built.

## Proposal for the next round: a matcher and a coverage answer

Two pieces, both by rules and with no AI or language model anywhere in the decision.

**1. A deterministic matcher: which catalog product is this table?** For a table that no pack recognises, score each
catalog product from evidence the engine already has, and show the evidence with the score:

- *Column names*: the business-key names and their usual spellings in a small word list per product (`order_no`,
  `ordernumber`, `so_id`, `vbeln` are order numbers; `line_no`, `posnr`, `item` are line numbers), the same way
  `requirements_draft` keeps its word lists. A table with `invoice_no` and `line_no` and an amount is an invoice-line
  candidate.
- *Key patterns*: the key the engine finds (`infer.py`'s key rules, `combined_keys.py`'s composite keys) compared with
  the product's business key: a composite key that ends in a line number points at a line role; a key with a
  valid-from or valid-to points at a version; a single id that other tables point at points at a master.
- *Graph position*: header and line pairs (an aggregate in `domains.py`), the table others point at most, a table
  that links two masters (a bridge).
- *Row checks* `validate_plan` already runs: the key counted unique, the relationships counted without orphans, and
  `amount_levels` (a header amount that repeats on its lines). A candidate is "suggested" by names and keys alone and
  "checked" only when the counts hold.
- *Packs first*: a table a pack recognises takes its product from `mapping.yaml`; the matcher only covers the rest.

The answer would be per table: the best product and role, the runner-up, the evidence, and "no product" when nothing
scores above a floor. The same schema gives the same answer, byte for byte (a golden file, as RQ1 does).

**2. A coverage answer per process.** Group the catalog's products into processes (order to cash: customer, product,
sales order, delivery, invoice, open item, payment; procure to pay; record to report; lead to cash; subscription) and
answer from `coverage()` and the matcher:

> Order to cash: 5 of 6 products present; delivery missing, so late-delivery questions cannot be answered.

Each missing product names the questions from the catalog it blocks, and each partial one names the role that is
missing. This is what `requirements_draft` needs to say "missing data" outside SAP order to cash (today rule `RQ-X0`):
a requirement maps to the catalog's questions, the questions to products, the products to the tables present.

**What the next round would not do:** create anything in Fabric, propose a product as checked without counts, or
guess a conformed key across systems without the inclusion check of docs/MULTI-SOURCE.md.

## DP2 (21 November 2026): the matcher and the coverage answer, built

Round DP2 built the proposal above in `fabric_backend/data_product_match.py`. No AI and no language model: fixed word
lists and rules decide, so the same schema and the same counts give the same answer, byte for byte.

**How a table gets a product.** Packs first: a table a pack recognises takes its product and role from `mapping.yaml`
(rule DP2-P1). Every other table is read by its name: the words, also inside German and Swedish compounds
(`Auftragspositionen` = auftrag + positionen, `Leverantörsfakturor` = leverantör + fakturor), go through a word list
in English, German and Swedish (customer/kunde/kund, order/auftrag/order, invoice/rechnung/faktura,
amount/betrag/belopp ...) (DP2-N1). A name ending in a list word (type, method, category, status, group, art ...) is a
reference list, not the product: `PaymentMethods` and `Zahlungsarten` get none. Then the key: a column read as
"<concept> number" (`KundenNr`, `OrderID`, `FakturaNr`) is the business key (DP2-K1), with a line number (`PosNr`,
`LineNo`, `Radnr`) for a line. A line belongs to the header of the same product that its document number points at,
by the plan's relationship or the same column (DP2-L1, DP2-L2). Amount columns (DP2-A1) and the plan's relationships
pointing at a master (DP2-M1) add to it. Last the rows: validate_plan's counts, or, in the same call, the same
counting statements (`evidence.key_sql`, `evidence.relationship_sql`, at most 20): the candidate key unique (DP2-C1)
and the line's link to its header without orphans (DP2-C2).

**Confidence.** `high`: the names (or a pack) and the key agree and the rows confirm it. `medium`: they agree, the rows
were not counted. `low`: one signal only, or the rows disagree; a hint, never counted as present. Every suggestion
lists its evidence: the rule and, for a count, the numbers. A table with no signal gets nothing.

**The coverage answer.** The products are grouped into processes (order to cash, procure to pay, record to report,
lead to cash, customer service, subscription, inventory). Per process: how many products are present (every required
role at medium or high), which are partial (a role missing) or missing, the catalog's questions it can answer and
those it cannot, with why. On the SAP demo (17 tables, rows counted):

> Order to cash: 5 of 7 products present; receivables and payables and payment missing, so a question like “Which
> customers have unpaid invoices past their due date?” cannot be answered.

**Where it shows.** One `data_products` field in the answers of `plan_backend` (names and keys only) and
`validate_plan` (with its counts), and on the start card's Check step one line, "Data products: …", with each process
and each table's product, confidence and evidence under Details (on your own data and on the shop sample).
`requirements_draft` on a schema no pack knows (rule RQ-X0) now names the catalog product a requirement's measure
needs: a missing product, or a missing role of it, comes first in `missing`; a present one is named with its tables.

**Tested on** the SAP, Salesforce and Dynamics 365 demos with their rows, an invented ERP with German names
(`tests/fixtures/dp2/unknown_erp_de.json`, rows counted), the WideWorldImporters and Swedish benchmark schemas (names
only) and a negative case of tables whose names mean nothing (no medium or high suggestion). The answers are golden
files (`tests/golden/dp2_*.json`); `tests/test_dp2_product_match.py`. Nothing has been run on a customer system.

**Not done.** The word list is small and hand-written; a schema in another language or with codes for names (SAP's
own) relies on the packs. Products across two systems (the conformed key above) are not matched. The review file of
`review_plan` does not carry the products.

## Checking and changing it

- `python -m pytest tests/test_dp1_data_product_catalog.py -q` runs the checks.
- A new pack table: add its row to `mapping.yaml` (or to `not_a_data_product` with a reason); the test says which
  tables are missing. The evidence column must be what the pack's sources say; `render_mapping` writes it.
- The coverage matrix above is `data_product_catalog.matrix_markdown()`; the test fails when it differs, so change
  the mapping and paste the new table.
