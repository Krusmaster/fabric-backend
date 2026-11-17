# Salesforce objects: the salesforce pack

Round PK1, 17 November 2026. A knowledge pack for the Salesforce standard objects of sales, marketing and service, built
like the SAP pack and read by the same loader (`fabric_backend/sap_pack.py`) from `fabric_backend/packs/salesforce/`:
the objects, their keys, the links between them, where the amounts live and the traps a person falls into when joining
them, with the public page each claim rests on. 'Salesforce' is used here only as the name of the product whose public
documentation the pack describes. Krusgraph is independent and not affiliated with Salesforce or Microsoft; nothing
here comes from a Salesforce org or a customer.

**What was read.** Unlike round n72, which wrote the Salesforce objects of the `younium_salesforce` pack without being
able to open a page, this round read Salesforce's public **Object Reference** and **Field Reference** for all 21
objects on developer.salesforce.com (API version 68.0, Winter '27) and checked the pack against them field by field.
The facts read (every field's name, type and length, and for each reference field the relationship type and the objects
it refers to) are kept in `tests/fixtures/pk1/salesforce_reference.json`; `tests/test_pk1_salesforce_pack.py` fails
when the pack names a column the page does not have, points a link where the page does not, or a key is not the
18-character `Id`. The pack's text is in our own words.

## What the pack covers

`fabric_backend/packs/salesforce/salesforce.json`, one module, 21 objects, 96 relationships of which 55 are applied
(the rest are listed with the reason they are not), 13 traps, 51 sources. Table names are the objects' API names in
upper case (`OPPORTUNITYLINEITEM`); columns are compared without case and underscores, so `AccountId`, `account_id` and
`ACCOUNT_ID` are the same column, and a prefix `sf_`, `salesforce_` or `crm_` in front of a table name is read past.

Every object's key is `Id`: type id, 18 characters through the API (each object's Field Reference). Links:

| Object | Applied links (field → object) | Listed, not applied | Amounts (level) | Object Reference page |
| --- | --- | --- | --- | --- |
| Account | `OwnerId` → User | `ParentId` | – | [Account](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-account.html) |
| Contact | `AccountId` → Account, `OwnerId` → User | `ReportsToId` | – | [Contact](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-contact.html) |
| Lead | `ConvertedAccountId` → Account, `ConvertedContactId` → Contact, `ConvertedOpportunityId` → Opportunity, `CampaignId` → Campaign | `OwnerId` | – | [Lead](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-lead.html) |
| Opportunity | `AccountId` → Account, `CampaignId` → Campaign, `ContractId` → Contract, `Pricebook2Id` → Pricebook2, `OwnerId` → User | `ContactId`, `PartnerAccountId`, `SyncedQuoteId` | `Amount` (header) | [Opportunity](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-opportunity.html) |
| OpportunityLineItem | `OpportunityId` → Opportunity, `PricebookEntryId` → PricebookEntry, `Product2Id` → Product2 | – | `TotalPrice` (item) | [OpportunityLineItem](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-opportunitylineitem.html) |
| OpportunityContactRole | `OpportunityId` → Opportunity, `ContactId` → Contact | – | – | [OpportunityContactRole](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-opportunitycontactrole.html) |
| Case | `AccountId` → Account, `ContactId` → Contact, `AssetId` → Asset, `ProductId` → Product2 | `OwnerId`, `ParentId` | – | [Case](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-case.html) |
| Campaign | `OwnerId` → User | `ParentId` | `AmountAllOpportunities` (header), `AmountWonOpportunities` (header), `BudgetedCost` (header), `ActualCost` (header) | [Campaign](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-campaign.html) |
| CampaignMember | `CampaignId` → Campaign, `LeadId` → Lead, `ContactId` → Contact, `AccountId` → Account | – | – | [CampaignMember](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-campaignmember.html) |
| Order | `AccountId` → Account, `ContractId` → Contract, `OpportunityId` → Opportunity, `QuoteId` → Quote, `Pricebook2Id` → Pricebook2, `OwnerId` → User | `CustomerAuthorizedById`, `OriginalOrderId` | `TotalAmount` (header) | [Order](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-order.html) |
| OrderItem | `OrderId` → Order, `PricebookEntryId` → PricebookEntry, `Product2Id` → Product2, `QuoteLineItemId` → QuoteLineItem | `OriginalOrderItemId` | `TotalPrice` (item) | [OrderItem](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-orderitem.html) |
| Product2 | – | – | – | [Product2](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-product2.html) |
| Pricebook2 | – | – | – | [Pricebook2](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-pricebook2.html) |
| PricebookEntry | `Pricebook2Id` → Pricebook2, `Product2Id` → Product2 | – | – | [PricebookEntry](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-pricebookentry.html) |
| Quote | `OpportunityId` → Opportunity, `AccountId` → Account, `ContactId` → Contact, `Pricebook2Id` → Pricebook2, `OwnerId` → User | – | `TotalPrice` (header), `GrandTotal` (header) | [Quote](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-quote.html) |
| QuoteLineItem | `QuoteId` → Quote, `PricebookEntryId` → PricebookEntry, `Product2Id` → Product2, `OpportunityLineItemId` → OpportunityLineItem | – | `TotalPrice` (item) | [QuoteLineItem](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-quotelineitem.html) |
| Contract | `AccountId` → Account, `OwnerId` → User | `CustomerSignedId`, `SourceOpportunityId` | – | [Contract](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-contract.html) |
| Asset | `AccountId` → Account, `ContactId` → Contact, `Product2Id` → Product2, `OwnerId` → User | `ParentId` | – | [Asset](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-asset.html) |
| User | – | `ContactId`, `ManagerId` | – | [User](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-user.html) |
| Task | `AccountId` → Account | `OwnerId`, `WhatId`, `WhoId` | – | [Task](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-task.html) |
| Event | `AccountId` → Account | `OwnerId`, `WhatId`, `WhoId` | – | [Event](https://developer.salesforce.com/docs/platform/object-reference/references/standard-objects/object-event.html) |

Why some links are listed and not applied:

- **Polymorphic `WhoId` and `WhatId`** (Task, Event). The Object Reference gives the relationship type *polymorphic*:
  `WhoId` refers to Contact or Lead, `WhatId` to some 1 500 object types (among the pack's: Account, Opportunity,
  Case, Campaign, Contract, Order, Quote, Asset, Product2). A join of `WhatId` to one table finds only that type's rows
  and the others look like orphans, so the pack lists one relationship per target with that condition and applies
  none. An id's first three characters name its object type (the field-types page; `describeSObjects` returns each
  object's prefix). The activity's `AccountId` is applied: it is derived and read-only.
- **Self-references** (`Account.ParentId`, `Contact.ReportsToId`, `Case.ParentId`, `Campaign.ParentId`,
  `Asset.ParentId`, `User.ManagerId`, reduction orders' `OriginalOrderId`).
- **Second paths and roles** (`Opportunity.PartnerAccountId`, `Opportunity.SyncedQuoteId`, `Opportunity.ContactId`,
  `Contract.SourceOpportunityId`, signatories), so the model has one path per pair of tables.
- **Owners that can be queues** (`OwnerId` of Lead and Case; Task and Event's *Assigned To*). The Object Reference
  pages do not list `OwnerId`; the Field Reference gives it as a reference of 18 characters and the field-types page
  says it holds the owning user's id. That a lead or case can be owned by a queue is from Salesforce Help, which could
  not be read (below), so it is marked unverified.

Master-detail: the Object Reference calls `Quote.OpportunityId` and `QuoteLineItem.QuoteId` master-detail.
`OpportunityLineItem.OpportunityId` and `OrderItem.OrderId` are required and not updatable on their pages, but the pages
call them relationships, not master-detail; the pack says exactly that.

### Where the amounts live (the total that doubles)

| Header amount | Lines | What the page says |
| --- | --- | --- |
| `Opportunity.Amount` (and `ExpectedRevenue`) | `OpportunityLineItem.TotalPrice` | each line item adds its `TotalPrice` to `Amount` (and `TotalPrice` times `Probability` to `ExpectedRevenue`), and `Amount` is read-only once the opportunity has line items (OpportunityLineItem, *Effects on Opportunities*) |
| `Order.TotalAmount` | `OrderItem.TotalPrice` | the net total of the order's products (Order, `TotalAmount`) |
| `Quote.TotalPrice`, `Quote.GrandTotal` | `QuoteLineItem.TotalPrice` | the quote's total of its lines after discounts, before tax and shipping; `GrandTotal` adds them (Quote). The same name `TotalPrice` is a header total on Quote and a line total on QuoteLineItem |
| `Campaign.AmountAllOpportunities`, `AmountWonOpportunities` | the campaign's opportunities | read-only sums over the campaign's opportunities (Campaign) |

Summed over a join with their lines, these count once per line. `UnitPrice` and `ListPrice` are prices, not amounts;
`PricebookEntry.UnitPrice` is the list price.

### The traps it explains

`sf_rollup_amounts` (above), `sf_product_through_price_book` (a line names a price book entry, which names the product;
a price book deleted while lines use it is archived and no longer returned by the API), `sf_multi_currency`
(`CurrencyIsoCode` only in a multi-currency org; a line's currency is its opportunity's), `sf_id_length` (15
case-sensitive characters in the user interface, 18 case-safe through the API), `sf_polymorphic_who_what`,
`sf_lead_conversion` (a converted lead stays in Lead beside the contact it became), `sf_campaign_rollups`,
`sf_quote_sync` (a syncing quote mirrors the opportunity's lines), `sf_contact_roles` (a many-to-many link table with
one primary contact), `sf_deleted_rows` (a copy can include deleted records, `IsDeleted`), `sf_owner_queue`,
`sf_landing_names` (below) and `sf_person_accounts`. Each is in the module file with its sources and in the manifest
(`packs/salesforce/manifest.yaml`) with the check that shows it on rows: `amount_level`, `referential_integrity`,
`privacy` or `manual`.

## One truth: `younium_salesforce` reads this pack

The Salesforce module of the `younium_salesforce` pack is gone. `packs/younium_salesforce/salesforce.include` names the
nine objects the Younium connector meets (Account, Contact, Opportunity, OpportunityLineItem, Product2, PricebookEntry,
Order, OrderItem, Contract) and three traps, and the loader reads them from `packs/salesforce/salesforce.json`, with
every relationship between them and the sources they cite. The pack keeps its rule label (*Younium + Salesforce
pack*). On the Younium demo the plan is unchanged (15 relationships); three links the salesforce pack lists and never
applies (`Contact.ReportsToId`, `Opportunity.ContactId`, `Opportunity.PartnerAccountId`) are now named as missing
columns, and the Salesforce sources of that pack are the ones read on 17 November 2026; its Younium sources are still
unread (docs/YOUNIUM-SALESFORCE.md).

`sap_pack.match_any` now chooses among three packs: the one that recognises most tables, of those with a table of the
system's own among them. Account, Contact, Lead, Case, Campaign, Order, OrderItem, Contract, Quote, Asset, User, Task
and Event are ordinary words and marked `common_name`, so a schema of such tables alone never becomes Salesforce;
OpportunityLineItem, OpportunityContactRole, CampaignMember, Product2, Pricebook2, PricebookEntry and QuoteLineItem
are Salesforce's own. On the Younium demo `younium_salesforce` still wins (14 tables against 4).

## How Salesforce data reaches Fabric

Read on Microsoft Learn on 17 November 2026:

- **No Salesforce source for database mirroring.** The mirroring overview's table of sources lists Azure and other
  databases (Azure SQL, Cosmos DB, PostgreSQL, MySQL, Databricks, BigQuery, Oracle, SAP Datasphere, Snowflake, SQL
  Server and others) and no Salesforce ([overview](https://learn.microsoft.com/en-us/fabric/mirroring/overview)). The
  open mirroring partner page names third-party tools that write Salesforce data into an open mirrored database
  ([partners](https://learn.microsoft.com/en-us/fabric/mirroring/open-mirroring-partners-ecosystem)); their table and
  column naming is theirs and **unverified** here.
- **The Salesforce objects connector of Data Factory** ([overview](https://learn.microsoft.com/en-us/fabric/data-factory/connector-salesforce-objects-overview)):
  Dataflow Gen2 as a source; a pipeline's copy activity (source and destination) and lookup; a **Copy job** (source and
  destination, full load, append, upsert). The copy activity reads an object by its API name (*Object API*), a report,
  or a SOQL query, and can include deleted records
  ([copy activity](https://learn.microsoft.com/en-us/fabric/data-factory/connector-salesforce-copy-activity)).
- **Names in OneLake.** A Copy job copies "with the same table name, column name, and data type as the source" unless a
  mapping renames them ([create a Copy job](https://learn.microsoft.com/en-us/fabric/data-factory/create-copy-job)): a
  Copy job from Salesforce objects therefore lands tables named after the objects (`Account`, `OpportunityLineItem`)
  with the field API names as columns (`AccountId`). That the source's *table name* for a Salesforce object is its API
  name is our reading of the two pages together, not a sentence on either: **unverified** until seen in a workspace.
  Dataflow Gen2 names a destination table after its query and adjusts characters the destination does not support
  ([destinations](https://learn.microsoft.com/en-us/fabric/data-factory/dataflow-gen2-data-destinations-and-managed-settings));
  the query names Power Query gives Salesforce objects, and the names of the relationship columns its *Include
  relationship columns* option adds ([Salesforce Objects](https://learn.microsoft.com/en-us/power-query/connectors/salesforce-objects)),
  are **unverified**. A pipeline's copy activity writes to the destination table its author names. How data types
  map (currency to decimal, boolean, datetime) is **unverified**.
- What this means for the pack: it reads `Account`, `account`, `sf_account` and `SALESFORCE_ACCOUNT` alike, but not
  a name someone chose freely (`crm_customers`). `Order`, `Case` and `User` are reserved words in SQL and need
  brackets; the engine's queries bracket every name.

## Verified, and what is not

| Claim | Source | Status |
| --- | --- | --- |
| Objects, fields, types, lengths, reference targets, relationship types (polymorphic, master-detail), required and updatable properties | Object Reference and Field Reference pages of the 21 objects (`sf_obj_*`, `sf_fields_*`) | read 17 November 2026, `fetched: true`; kept in `tests/fixtures/pk1/salesforce_reference.json` |
| Amount roll-ups, read-only `Amount`, line currency, price book rules, lead conversion, campaign members, quote sync | the same pages' field descriptions and usage sections | read 17 November 2026, `fetched: true` |
| 15 and 18 character ids; `OwnerId` holds the owning user; the object prefix | [Field types](https://developer.salesforce.com/docs/platform/object-reference/guide/field-types.html) (`sf_id_field_type`) | read 17 November 2026, `fetched: true` |
| Leads and cases can be owned by a queue | Salesforce Help (`sf_queue_owner`) | **`fetched: false`**: help.salesforce.com answered, but renders its articles in the browser and the session received no article text; unverified |
| How the data lands in Fabric | Microsoft Learn (`ms_*`, six pages) | read 17 November 2026, `fetched: true`; the naming of Dataflow Gen2, Power Query relationship columns, type mapping and open-mirroring partners unverified (above) |
| That the pack is right about a real org | nothing yet | **not verified**: no org was read; the demo rows are written from the pack, and `sap_pack.write_verified` refuses to record a synthetic run |

The old atlas URLs (`developer.salesforce.com/docs/atlas.en-us.object_reference.meta/...`) that round n72 cited now
redirect to the pages above. Hosts this round could not reach from its network: `resources.docs.salesforce.com`
(Salesforce's PDF versions of the references), `www.salesforce.com` and `trailhead.salesforce.com` (the proxy refused
them). They are not needed for what the pack claims; allow them in the environment's network settings only if a later
round wants the PDF references or Trailhead. To read Salesforce Help articles a session needs a browser, not only the
host.

## The demo and the data products the engine proposes

`fabric_backend/salesforce_demo.py`: SYNTHETIC rows, written from the pack, in 21 tables named as a Copy job lands them
(`Account`, `OpportunityLineItem`, field API names as columns). Every company, person, e-mail address (at
example.invalid) and id is made up; ids have the 18-character shape with commonly seen object prefixes. Planted: an
opportunity, an order and a quote with three lines each; a price book deleted while lines used it (archived, so not
in the landing); activities about contacts and leads, and about accounts, opportunities, a case and a campaign; a
converted lead; a syncing quote beside an earlier one; campaign sums; a deleted opportunity; a lead and a case owned
by a queue; a person account; one company in EUR. `EXPECTED` in the module says what each check should find.
`write_csv(folder)` writes CSVs, `_types.json`, a README that says SYNTHETIC, and a PySpark notebook for a lakehouse.

Everything below is generated by `python -m fabric_backend.salesforce_demo --doc` from what the engine does now:
`infer.plan` (which reads the pack through `match_any`), `validate_plan`'s checks (`evidence.validate`),
`domain_draft`'s proposal (`domains.draft`), and the functions behind `ontology_draft` and `semantic_model_draft`.
`tests/test_pk1_salesforce_pack.py` fails when this section and the engine disagree. No number in it is typed.

<!-- generated by python -m fabric_backend.salesforce_demo --doc; do not edit by hand -->

*SYNTHETIC: made-up rows written from the salesforce pack (fabric_backend/salesforce_demo.py); not Salesforce data.*

- Tables: 21, rows: 81; the engine picked the `salesforce` pack and recognised 21 of its tables.
- Planned: 21 keys and 53 relationships (53 by Salesforce pack); 43 pack relationships between the demo's tables are listed and not applied (polymorphic, self-references, second paths, queue owners).
- Orphans `validate_plan` counts on the rows:
  - Opportunity.Pricebook2Id -> Pricebook2: 1 of 4
  - PricebookEntry.Pricebook2Id -> Pricebook2: 1 of 5
- Header amounts a join with their lines repeats (*the total that doubles*):
  - Campaign.BudgetedCost, ActualCost, AmountAllOpportunities, AmountWonOpportunities over CampaignMember.CampaignId: up to 3 rows per Campaign row
  - Campaign.BudgetedCost, ActualCost, AmountAllOpportunities, AmountWonOpportunities over Lead.CampaignId: up to 2 rows per Campaign row
  - Campaign.BudgetedCost, ActualCost, AmountAllOpportunities, AmountWonOpportunities over Opportunity.CampaignId: up to 2 rows per Campaign row
  - Opportunity.Amount, ExpectedRevenue over OpportunityContactRole.OpportunityId: up to 2 rows per Opportunity row
  - Opportunity.Amount, ExpectedRevenue over OpportunityLineItem.OpportunityId: up to 3 rows per Opportunity row
  - Opportunity.Amount, ExpectedRevenue over Quote.OpportunityId: up to 2 rows per Opportunity row
  - Order.TotalAmount over OrderItem.OrderId: up to 3 rows per Order row
  - PricebookEntry.UnitPrice over OpportunityLineItem.PricebookEntryId: up to 2 rows per PricebookEntry row
  - PricebookEntry.UnitPrice over OrderItem.PricebookEntryId: up to 2 rows per PricebookEntry row
  - PricebookEntry.UnitPrice over QuoteLineItem.PricebookEntryId: up to 2 rows per PricebookEntry row
  - Quote.Subtotal, TotalPrice, GrandTotal over QuoteLineItem.QuoteId: up to 3 rows per Quote row

Data products (domains) the engine proposes, by community detection over the planned relationships and named after the pack's areas:

| # | Proposed data product | Tables |
| --- | --- | --- |
| 1 | activities and customers | Account, Asset, Case, Contact, Event, OpportunityContactRole, Task |
| 2 | sales | Contract, Opportunity, Order, Pricebook2, Quote, User |
| 3 | sales and product catalog | OpportunityLineItem, OrderItem, PricebookEntry, Product2, QuoteLineItem |
| 4 | marketing | Campaign, CampaignMember, Lead |

Ontology draft (`ontology_draft`, nothing created): entity_types: 21; with_key: 21; relationship_types: 53; skipped_relationships: 0

Semantic-model draft (`semantic_model_draft`, nothing created): tables: 21; relationships_active: 20; relationships_inactive: 33; relationships_not_expressible: 0; storage_mode: directLake (SQL analytics endpoint); compatibility_level: 1604; measures: 49; header_amounts: 18

<!-- end of generated section -->

The engine's four proposals map onto the usual names: *marketing* is the top of lead to cash (campaigns, members,
leads), *sales* and *sales and product catalog* the rest of it (opportunities, quotes, orders, contracts and their
lines with the catalog), and *activities and customers* is the customer and service view (accounts, contacts, assets,
cases and the activities about them). The names are the engine's, from the pack's areas; the split is its community
detection over the planned relationships. Nothing was created in Fabric: the ontology and the semantic model are
drafts, and no session in this round had a Fabric workspace.

The same demo is the corpus `salesforce` of `tests/f2_corpus.py` (scores in [SCORES.md](SCORES.md)), and its engine
answers are pinned in `tests/golden/engine_salesforce_demo.json`. Because the rows were written from the pack, the
scores show that the engine applies the pack as written, not that the pack is right about Salesforce.

## Running it

```
python -m fabric_backend.salesforce_demo          # the report as JSON
python -m fabric_backend.salesforce_demo --doc    # the generated section of this page
python -m fabric_backend.pack_manifest salesforce # the manifest as it would be regenerated
python -m pytest -q tests/test_pk1_salesforce_pack.py
```

## Next

- Verify on a real org's landing (a Copy job into a lakehouse): run `validate_plan`, then
  `sap_pack.verification(answer, where, when, pack="salesforce")` (the `sap-verify` command reads the SAP pack only), on
  systems that may be described without naming a company.
- Read the Salesforce Help article on queues from a session with a browser and set `sf_queue_owner` to `fetched: true`
  or correct the claim.
- Confirm in a workspace how Dataflow Gen2 and the Power Query connector name tables and relationship columns.
