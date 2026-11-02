# Subscription billing: Younium beside Salesforce (the `younium_salesforce` pack)

Round n72, 1 November 2026. A second knowledge pack, built like the SAP pack: tables, keys and relationships of a known
source system, with a public source per claim, read by the same loader (`fabric_backend/sap_pack.py`) from
`fabric_backend/packs/younium_salesforce/`. It describes Younium's objects as its API v2 shows them, the Salesforce
standard objects Younium's Salesforce connector meets, and the one link between the two systems: a Younium account's
External CRM Id is the Salesforce Account Id.

**Read this first.** None of the source pages could be opened from the session that wrote the pack:
`developer.younium.com`, `support.younium.com` and `developer.salesforce.com` are outside that session's allowed
network. The pack was written after what is publicly known of the systems and after web search results of 1 November
2026 that quote the pages; every source carries `fetched: false` and a note that says so, and this page lists what has to
be checked. Nothing comes from a Younium tenant, a Salesforce org or a customer; the demo rows are made up and written
from the pack, so a run on them shows that the tools work on such tables, never that the pack is right about Younium.

## What the pack knows

### Younium (module `younium`, API v2)

| Table | Key | Points at | Note |
| --- | --- | --- | --- |
| `ACCOUNTS` | `ID` (GUID); `ACCOUNT_NUMBER` unique | `ACCOUNT.ID` through `EXTERNAL_CRM_ID` | one currency per account; `EXTERNAL_ERP_ID` for the ERP |
| `PRODUCTS` | `ID`; `PRODUCT_NUMBER` unique | | no price on the product |
| `CHARGE_PLANS` | `ID`; `CHARGE_PLAN_NUMBER` unique | `PRODUCTS` | a way of pricing a product |
| `CHARGES` | `ID`; `CHARGE_NUMBER` unique | `CHARGE_PLANS` | type Recurring, One-off, Usage, Measured; a list price per price period, not an amount |
| `SUBSCRIPTIONS` | `ID`; `SUBSCRIPTION_NUMBER` unique (the API's orderNumber) | `ACCOUNTS` twice: account and invoice account; `OPPORTUNITY` listed only | carries no amount |
| `SUBSCRIPTION_VERSIONS` | `ID`; `SUBSCRIPTION_ID`+`VERSION` unique | `SUBSCRIPTIONS` | one version valid on a date; `IS_LAST_VERSION`, effective start and end |
| `SUBSCRIPTION_CHARGES` | `ID` | `SUBSCRIPTION_VERSIONS`, `CHARGES` | the agreed `PRICE` and `QUANTITY` per charge and version |
| `SALES_ORDERS` | `ID`; `SALES_ORDER_NUMBER` unique | `ACCOUNTS`; `SUBSCRIPTIONS` listed only | fields not read: unverified |
| `INVOICES` | `ID`; `INVOICE_NUMBER` unique | `ACCOUNTS` | `TOTAL_AMOUNT`, `SUB_TOTAL`, `TAX_AMOUNT` at header level; status draft or posted |
| `INVOICE_LINES` | `ID` | `INVOICES`; by number to `CHARGES`, `SUBSCRIPTIONS`, `PRODUCTS` listed only | `AMOUNT` at line level; service period |
| `PAYMENTS` | `ID` | `INVOICES`, `ACCOUNTS` | `AMOUNT`; one invoice per row assumed |

### Salesforce (module `salesforce`, standard objects)

`ACCOUNT` (with `PARENT_ID` to itself, listed only), `CONTACT` → `ACCOUNT`, `OPPORTUNITY` → `ACCOUNT` and → `CONTRACT`,
`OPPORTUNITYLINEITEM` → `OPPORTUNITY`, → `PRICEBOOKENTRY` and (derived, read-only) → `PRODUCT2`, `PRICEBOOKENTRY` →
`PRODUCT2`, `ORDER` → `ACCOUNT`, `CONTRACT` and `OPPORTUNITY`, `ORDERITEM` → `ORDER`, `PRICEBOOKENTRY` and `PRODUCT2`,
`CONTRACT` → `ACCOUNT`. Amounts: `OPPORTUNITY.AMOUNT` and `ORDER.TOTAL_AMOUNT` at header level (sums of their lines'
`TOTAL_PRICE`), `TOTAL_PRICE` at line level, `UNIT_PRICE` a price. Personal data is named on `CONTACT` (names, e-mail,
telephone, address, birth date) and on `ACCOUNT` (telephone, addresses).

Table names are the objects' API names in upper case; columns are compared without case or underscores, so `AccountId`
and `account_id` both read as the pack's `ACCOUNT_ID`. A system prefix in front of a table name (`younium_accounts`,
`sf_account`, `salesforce_opportunity`, `crm_contact`) is read past, like `sap_vbak`.

### The traps it explains

- **Never sum over all versions of a subscription.** Every activated change is a new version with its own effective
  period; one version holds on a date. A sum of seats or prices over `SUBSCRIPTION_VERSIONS` or `SUBSCRIPTION_CHARGES`
  without a date filter counts every change again. In the demo, subscription SUB-2001 has three versions: 540 000 over
  all of them against 240 000 for the version valid today.
- **Amounts sit on charges and invoice lines, not on the subscription.** The header total of an invoice is repeated
  once per line in a join (the check *the total that doubles*, which the pack feeds with `INVOICES.TOTAL_AMOUNT`,
  `OPPORTUNITY.AMOUNT` and `ORDER.TOTAL_AMOUNT`).
- **MRR and ARR are measures, not columns.** Recurring charges of the version valid on the date, price times quantity
  normalized to a month or a year, in the account's currency. Younium's own figure is reproduced only with the same
  definition.
- **One currency per account.** `ACCOUNTS.CURRENCY`, repeated on the invoice. In Salesforce, `CurrencyIsoCode` exists only
  in a multi-currency org.
- **Usage and measured charges.** The quantity comes from reported usage, the price per a price period that may differ
  from the billing period; keep the volume as its own measure.
- **Salesforce ids: 15 characters in the user interface, 18 through the API.** The connector fills External CRM Id with
  18; a value pasted from the user interface has 15 and finds nothing. The demo plants exactly this: Demo Account 4's
  `external_crm_id` is the 15-character form, and the check reports one orphan of four.
- **One customer, two account rows.** The Salesforce Account and the Younium account are bound only by
  `ACCOUNTS.EXTERNAL_CRM_ID = ACCOUNT.ID`; a match on the name is not the link. A subscription's invoice account can
  differ from its account.
- Also: fields without a value are left out of the API's JSON (a column can be missing from one load), draft invoices
  beside posted ones, table names in Fabric are the integrator's choice, the Salesforce product is reached through the
  price book entry, and a currency column exists only in a multi-currency org.

## How the engine reads it (round n78)

- `sap_pack.load("younium_salesforce")`, `sap_pack.problems(...)`, `sap_pack.match(schema, "younium_salesforce")`: the
  pack's view of a schema (tables, keys, applied and listed relationships, missing tables), as for SAP.
- **The engine reads the pack.** Since round n78 (2 November 2026) `infer._pack` calls `sap_pack.match_any(schema)` in
  place of `sap_pack.match(schema)`: the pack that recognises most of a schema's tables, SAP or this one. A schema it
  recognises gets the pack's keys and applied relationships in the plan, with the rule `SAP pack` (one rule for every
  pack, so the answers keep their shape) and the pack's name, module and public source on each relationship's note
  (`younium_salesforce pack (younium): source: ...`); `plan.pack` carries the pack's name, tables, amounts and traps as
  it does for SAP. `plan_backend`, `/check`, `domain_draft` and the drafts built from a plan therefore plan
  `younium_subscriptions.account_id -> younium_accounts` through the prefix, and `validate_plan` checks the joins and
  feeds *the total that doubles* with the pack's amounts.
- **When the pack counts.** Many of the pack's table names are ordinary words (`ACCOUNTS`, `PRODUCTS`, `CHARGES`,
  `SUBSCRIPTIONS`, `SALES_ORDERS`, `INVOICES`, `INVOICE_LINES`, `PAYMENTS`; Salesforce's `ACCOUNT`, `CONTACT`,
  `OPPORTUNITY`, `ORDER`, `ORDERITEM`, `CONTRACT`), and another system's tables can carry them with an `id` key. Those
  tables are marked `common_name` in the pack files, and `match_any` takes the pack only when at least one table it
  recognises is not marked: `CHARGE_PLANS`, `SUBSCRIPTION_VERSIONS`, `SUBSCRIPTION_CHARGES`, `OPPORTUNITYLINEITEM`,
  `PRODUCT2` or `PRICEBOOKENTRY`. A schema of accounts, products, invoices, invoice lines, payments and a Contact is
  planned by the name rules as before; so is the `/check` CRM example (Account, Contact, Opportunity beside an ERP).
  No SAP table is marked, so a schema the SAP pack recognises gets exactly the plan it got before, and no Salesforce or
  Younium table shares a name with an SAP table. `tests/test_younium_pack.py` compares the plans of the benchmark's
  shop, sap, crm and traps sets, and of the SAP test schemas, with the plans of the engine that read the SAP pack
  alone, and checks the tables of ordinary names alone.
- `sap_pack.plan_with(schema, "younium_salesforce")`: `infer.plan` with the pack's keys and plain relationships given
  as the caller's keys and confirmed relationships, for a pack named by the caller; it stood in for the engine in round
  n72 and stays for comparing, and for a schema `match_any` does not take.
- Measured by the engine on the demo (2 November 2026, SQLite, `examples/benchmark/README.md`): 15 of 15 planned
  relationships right, recall 15 of 18 (the three links by number the invoice lines carry are listed by the pack as
  unverified and not applied), and `validate_plan` shows the three planted traps: the 15-character Salesforce id as the
  one orphan of `younium_accounts.external_crm_id -> sf_account` (the count says one row points at nothing; that the
  reason is 15 against 18 characters is the pack's trap `salesforce_id_length` in `plan.pack`), the invoice total over
  its three lines and the opportunity amount over its line items. The rows were written from the pack, so this shows
  what the pack adds on such a schema, not that the pack is right about Younium.
- The domain proposal (`fabric_backend/domains.py`) names a domain after the pack's areas when it has them (read
  from `plan.pack` since round n78): on the demo, *billing* (invoices, invoice lines, payments, with the accounts and the subscriptions), *product catalog and
  subscriptions* (products, charge plans, charges, subscription versions and charges) and *customers and sales* (the
  four Salesforce tables). The split itself is the deterministic community detection it always was; only the names
  are new.

## The demo (`fabric_backend/younium_demo.py`)

Fourteen tables, 58 rows, every value made up: ten Younium tables with the prefix `younium_` and snake-case columns, four
Salesforce tables with the prefix `sf_` and the API field names. Planted: the 15-character Salesforce id (one orphan),
invoice INV-1001 with three lines (the header total doubles), three versions of one subscription, an account billed in
EUR beside accounts in SEK, a usage charge, a draft invoice, a subscription billed to another account. `EXPECTED` in
the module says what each check finds; `tests/test_younium_pack.py` runs them in SQLite. `write_csv(folder)` writes the
CSVs, `_types.json` and a PySpark notebook for a lakehouse (nothing here connects to Fabric), and `rows_for_check()`
gives the rows in the shape `browser_check._sqlite_source` takes, so `/check` has it as the example *Subscription billing*
(round n78) without a change to the demo. `examples/benchmark/` has the demo as its fifth set.

## Sources, with dates, and what is unverified

Every source was looked for on 1 November 2026 from a session whose network does not allow these hosts; none was
opened. "Seen" below means a web search result of that day quoted the page; the quotation is in the pack's source note.

| Id in the pack | Page | Status |
| --- | --- | --- |
| `younium_api_v2` | https://developer.younium.com/ (API v2 reference) | not opened; seen: accounts, products, subscriptions, invoices, payments; a change creates a new version; products → charge plans → charges; invoices draft then posted; empty fields omitted from the JSON |
| `younium_api_subscriptions` | https://developer.younium.com/api-s/api-2.0/subscriptions | not opened; seen: `GET /Subscriptions/{orderNumber}/versions`, `version`, `isLastVersion`, `externalERPId`/`externalCRMId` on the subscription, its account and invoiceAccount, its products and charges, `chargeNumber` |
| `younium_api_news` | https://developer.younium.com/news-and-updates | not opened; seen: release notes for API 2.1, `POST /Payments` |
| `younium_sf_integration` | https://support.younium.com/hc/en-us/articles/29942644887954 (Salesforce Integration) | not opened; seen: the connector moves Accounts, Opportunities and Opportunity Products from Salesforce to Younium; External CRM Id is populated from the Salesforce Account Id and cannot be custom mapped; opportunity currency → currency code; opportunity status mapped by hand |
| `younium_sf_gen1` | https://support.younium.com/hc/en-us/articles/4402123737617 | not opened; seen: an earlier (Gen 1) connector whose account mapping has name and shipping address and no External CRM Id; which article describes which generation is not confirmed |
| `younium_product_structure` | https://support.younium.com/hc/en-us/articles/12275717885073-Youniums-Product-structure | not opened; seen: products → charge plans → charges; charge types Recurring, One-off, Usage, Measured; price period |
| `sf_object_reference` | https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/ | not opened; written from public knowledge of the standard objects |
| `sf_opportunitylineitem` | …/sforce_api_objects_opportunitylineitem.htm | not opened; seen: `OpportunityId` required, `PricebookEntryId` for pricing, `Product2Id` read-only (API 30.0+), a Pricebook2 before line items |
| `sf_id_field_type` | https://developer.salesforce.com/docs/atlas.en-us.api.meta/api/field_types.htm | not opened; seen through third-party pages: 15 case-sensitive characters, 18 case-safe through the API, `CASESAFEID` |

Unverified in particular, and written after the known:

- Every Younium field name and which object carries it: `accountNumber`, `externalCrmId` (the search result spells it
  `externalCRMId`), `invoiceAccount`, the invoice's `totalAmount`/`subTotal`/`taxAmount`, the line's `amount`,
  `servicePeriodStartDate`, the payment's fields.
- What an invoice line names: a charge number, a product number, the subscription's order number, or ids. The pack
  lists these links and does not apply them.
- Whether a payment settles one invoice (a row per invoice) or several (a link table).
- Whether the subscription's External CRM Id carries the Opportunity Id; whether and how a Younium product is matched
  to a Product2; what the invoices sent back to Salesforce land in (a custom object of the connector's package, not
  described).
- The fields of `SALES_ORDERS` and how a sales order points at the subscription it created.
- Cardinality of the account link: the connector is described as one Younium account per Salesforce account; the pack
  says many-to-one so the join is never wrong, and `validate_plan`'s counts tell.
- The Salesforce claims are standard-object knowledge and the least uncertain, but the pages were not opened either.

When the hosts are allowed from a session, open the nine pages, set `fetched: true` where the text agrees, correct
the rest, and keep this list in step; the test `test_every_source_is_marked_unverified_with_the_date_it_was_not_reached`
will then need its assertion turned around.

## Questions for someone who runs the Younium–Salesforce integration

1. **Which objects land in Fabric, and how?** A pipeline over the API (which resources, api-version 2.0 or 2.1, how
   often), a Younium export, or a third-party connector? With which table names, and are nested arrays (versions,
   products and charges on a subscription, invoice lines) flattened into tables of their own?
2. **Subscriptions.** Does the landing hold one row per version (the API's shape) or a subscription table and a
   version table? Which columns bound a version's period, and is `isLastVersion` kept?
3. **Invoice lines.** Which of charge number, product number, order number and ids does a line carry? Does a line point
   at the subscription charge (version) it bills?
4. **Payments.** One invoice per payment row, or a payment applied to several invoices?
5. **The Salesforce side.** Which Salesforce objects does the Fabric landing hold (the standard objects, the connector's
   package objects for invoices and products, both)? Is the org multi-currency? Are ids 18 characters everywhere?
6. **The link.** Is External CRM Id filled for every account, or only for accounts the connector created? Can two
   Younium accounts (an account and an invoice account) point at one Salesforce Account?
7. **Measures.** Which definition of MRR and ARR does the business use (recurring charges only; normalization; the
   version valid on the date), so the semantic model's measure matches Younium's reports?
8. **Names in Fabric.** camelCase, snake_case, or Younium's labels; with or without a system prefix.

Nothing in round n72 or n78 deploys or calls Azure, Entra, DNS or Fabric; the `/check` example for the pack came in
round n78.
