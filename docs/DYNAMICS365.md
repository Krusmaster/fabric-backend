# Dynamics 365 tables: the dynamics365 pack

Round PK2, 17 November 2026. General naming rules read Dynamics 365 badly in two different ways. Dataverse names every
key `<table>id` and every lookup after its logical name, but a customer, owner or "regarding" lookup holds the id of
one of several tables, and header totals sit beside line amounts. Business Central keys documents by Document Type and
No., spreads every table over companies, and keeps its header amounts as FlowFields that never reach a lake. The
dynamics365 pack says these things per table and per relationship, with the public page each claim rests on, and the
engine uses it before the name rules, as it uses the SAP pack ([SAP.md](SAP.md)).

**Status (ON1, 25 November 2026).** Dynamics 365 can now be combined with SAP in one data product: the customer
(`account`, or Business Central's `Customer`) and the product (`product`, or `Item`) are matched to SAP's KNA1 and MARA
by rules with counts, and one shared Fabric IQ ontology is drafted over both ("Combined with SAP" below). Unit tests on
synthetic data only; **not run against Fabric**.

The pack describes tables, not a connector: it holds no credentials, endpoints or extraction logic and connects to
nothing ([PACKS.md](PACKS.md), "What a pack is, and is not"). Microsoft product names are used only as names.
Krusgraph is independent and not affiliated with Microsoft.

## What is in it

`fabric_backend/packs/dynamics365/` (format: `packs/pack.schema.json`; manifest: `manifest.yaml`, review status
`proposed`, version 0.1.0):

| Module | Tables | Relationships |
| --- | --- | --- |
| `dataverse` | Sales and Customer Service: `account`, `contact`, `lead`, `opportunity`, `opportunityproduct`, `quote`, `quotedetail`, `salesorder`, `salesorderdetail`, `invoice`, `invoicedetail`, `product`, `pricelevel`, `productpricelevel`, `incident` (case), `systemuser`, `team`, `businessunit`, `transactioncurrency`, `activitypointer` (20) | 73: 43 plain key lookups, all applied, and 30 filtered on a type column (customer, parent customer, owner, regarding) |
| `business_central` | Customer (18), Vendor (23), Item (27), Salesperson/Purchaser (13), Country/Region (9), Sales Header (36), Sales Line (37), Sales Invoice Header (112), Sales Invoice Line (113), Purchase Header (38), Purchase Line (39), G/L Entry (17), Cust. Ledger Entry (21), Detailed Cust. Ledg. Entry (379), Item Ledger Entry (32), Value Entry (5802), Dimension Set Entry (480) (17) | 28: 22 key joins, 3 filtered on the line Type (No. is an item only for Type Item), 3 listed and not applied (an invoice's Order No.; a ledger entry's Dimension Set ID, which matches one row per dimension) |

**Keys.** Dataverse: the GUID column `<table>id` (`accountid`, `salesorderdetailid`); `activitypointer` is the
exception, `activityid`. Business Central: the AL primary key with the company first, `$Company` + `No.` for master
data, `$Company` + `Document Type` + `No.` for Sales/Purchase Header, + `Line No.` for their lines, `Document No.` +
`Line No.` for posted invoice lines, `Entry No.` for every ledger, `Dimension Set ID` + `Dimension Code` for dimension
sets. Like SAP's client, the company is dropped from keys and joins on both sides when a landing has no company column
(a per-company SQL table).

**Where the amounts live** (each amount has a level in the pack, so `validate_plan`'s amount check names the total
that doubles):

| Header | Header amount | Line | Line amount |
| --- | --- | --- | --- |
| `opportunity` | `estimatedvalue` (forecast, typed or computed), `actualvalue`, `totalamount` | `opportunityproduct` | `extendedamount` (after manual discount), `baseamount` |
| `quote` | `totalamount` | `quotedetail` | `extendedamount` |
| `salesorder` | `totalamount`, `totallineitemamount`, `totaltax` | `salesorderdetail` | `extendedamount`, `baseamount` |
| `invoice` | `totalamount` | `invoicedetail` | `extendedamount` |
| Sales Header, Sales Invoice Header, Purchase Header | none stored: `Amount` is a FlowField | Sales Line, Sales Invoice Line, Purchase Line | `Amount`, `Amount Including VAT`, `Line Amount` |
| Cust. Ledger Entry | `Sales (LCY)`; `Amount` and `Remaining Amount` are FlowFields | Detailed Cust. Ledg. Entry | `Amount`, `Amount (LCY)` |

Every Dataverse money column is in the record's currency (`transactioncurrencyid`), with a `_base` twin in the base
currency.

## How the data reaches Fabric, and what the pack reads

| Route | Table names | Columns | Read by the pack |
| --- | --- | --- | --- |
| Dataverse: Link to Microsoft Fabric (or Azure Synapse Link for Dataverse, Delta) | logical names (`salesorderdetail`) | logical names; system columns `Id`, `IsDelete`, `SinkCreatedOn`, `SinkModifiedOn`, `versionnumber`; choice labels in `OptionsetMetadata` and friends | yes |
| Dataverse Web API (a pipeline of your own) | as the pipeline names them | lookups as `_<name>_value` | yes: `_parentaccountid_value` is read as `parentaccountid` |
| Business Central: SQL database copy (on premises) | `<company>$<table>$<app id>`, dots as underscores (`Cust_ Ledger Entry`) | `Document No_` | yes, without a company column |
| Business Central: bc2adls (unsupported, archived) | `<Table>-<id>` (`SalesHeader-36`) | `<Field>-<id>` (`DocumentNo-3`), `$Company` | yes |
| Business Central: Fabric mirroring (preview) | not documented on the pages read | not documented | not yet: confirm the names on a mirror |
| Business Central: Power Query connector, API v2.0 (Dataflow Gen2) | API entities (`salesOrders`) | camelCase, keyed by the SystemId GUID | no: the API entities are not described |

The loader changes behind this, in `sap_pack.py`: `table_name` takes the table out of `<company>$<table>$<app id>` and
drops bc2adls' `-<id>`; columns are compared without any punctuation (`No.`, `No_` and `NO` are one name), and
`_x_value` and `x-<id>` are read as `x`; `COMPANY` joins `MANDT` among the columns dropped from both sides when absent.
The SAP, Younium and Salesforce packs read exactly as before (the regression corpus and the benchmark are unchanged
apart from `bc_like`, below).

## The traps it explains

| Trap | Check on the rows |
| --- | --- |
| Header totals and line amounts are the same money (`salesorder.totalamount` over `salesorderdetail`, `opportunity.estimatedvalue` over `opportunityproduct`) | `amount_level` |
| Customer, owner and regarding lookups point at more than one table: filter on `customeridtype`, `owneridtype`, `regardingobjecttypecode` first | `referential_integrity` (the filtered relationships) |
| Pipeline, quotes, orders and invoices are four stages of one sale | manual |
| Deleted rows stay in the lake with `IsDelete` (about 30 days); `SinkCreatedOn` is not `createdon` | manual |
| A lookup is `_<name>_value` in the Web API and `<name>` in the reference | manual |
| Choice columns hold numbers; labels are in the metadata tables, one row per language | manual |
| Every money column is in the record's own currency | manual |
| Business Central header amounts are FlowFields: not in the export | manual |
| Every Business Central table is per company | manual (the key check shows it when `$Company` is left out) |
| Open documents of every kind share Sales Header; No. is unique only per Document Type | manual |
| No. on a line is an item only when Type says so | the filtered relationships |
| One posted invoice appears in several ledgers; G/L revenue is negative | manual |
| Joining a dimension set repeats the entry | manual |
| How the names arrive depends on the route | manual |

## The demo: SYNTHETIC DEMO DATA

`fabric_backend/dynamics_demo.py` builds 33 tables with 109 rows, every value made up ("Demo Account 1", "Demo
Company A", addresses at example.invalid): 20 Dataverse tables as Link to Microsoft Fabric lands them and 13 Business
Central tables as bc2adls names them, in two companies. The rows are written from the pack, so a run on them shows
that the tools work on such tables, never that the pack is right about Dynamics 365. `write_csv(folder)` writes CSV
files, `_types.json` and a notebook that loads them into a lakehouse; nothing here connects to Fabric.

Planted, and found by the engine (`tests/test_pk2_dynamics_pack.py`, numbers from the engine on SQLite, 17 November
2026): 33 of 33 keys unique, 81 of 89 relationships hold without orphans (7 have no rows with a value
in the demo); one orphan, an activity regarding an account purged from the lake; the totals that double on
`salesorder`, `opportunity`, `quote` and `invoice`, three lines on SO-1001 and on the first opportunity; one
soft-deleted order line; a contact whose parent customer is a contact; one order in EUR; and in Business Central
customer C10000, item 1000 and invoice 103001 in both companies (unique only with `$Company`), quote 1001 beside order
1001, a G/L Account line beside the item lines, a dimension set with two dimensions.

## Data products on the demo

`dynamics_demo.products()` takes four scopes (the table lists are chosen by hand, as a person would) and lets the
engine do the rest: the plan, `validate_plan`'s checks, the domain proposal, the ontology draft and the semantic model
draft. The numbers below are its output, kept in `tests/golden/pk2_dynamics_products.json` and asserted by the tests.

| Data product | Tables | Keys unique | Relationships hold / checked | Totals that double | Domains the engine proposes | Ontology: entity types / relationship types | Semantic model: active / inactive relationships, measures |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Lead to cash (Dataverse) | 12 | 12 / 12 | 30 / 30 | 7, among them `salesorder.totalamount` and `opportunity.estimatedvalue` over their lines | "lead to cash and order to cash" (headers), the same with a 2 (lines and products) | 12 / 26 | 11 / 15, 75 |
| Order to cash (Business Central) | 11 | 11 / 11 | 14 / 14 | 1: `Cust. Ledger Entry.Sales (LCY)` over its detailed entries | "order to cash" (documents and master data), "order to cash 2" (customer ledger); G/L Entry and Dimension Set Entry unassigned | 11 / 12 | 7 / 5, 26 |
| Customer 360 (Dataverse) | 9 | 9 / 9 | 31 / 35 (1 orphan, 3 without rows of their type) | none in scope | "order to cash and customer 360", "customer 360 and organisation" | 9 / 9 | 5 / 4, 23 |
| Service cases (Dataverse) | 8 | 8 / 8 | 22 / 24 (1 orphan, 1 without rows) | none in scope | "customer 360 and product catalog", "organisation" | 8 / 11 | 6 / 5, 6 |

What the drafts do not do yet, seen on this run:

- The filtered (polymorphic) relationships are checked on the rows but stay in `plan.extended`: the ontology and
  semantic model drafts relate only plain key joins, so a case's customer is not a relationship of the model.
- The semantic model draft proposes sums of the system columns: 20 of the 75 Lead to cash measures sum `IsDelete` or
  `versionnumber`. Delete them in the draft; teaching the engine those columns is the next step (Engine).
- The domain names follow the pack's areas; the engine splits by structure, so "Lead to cash" comes out as headers and
  lines in two domains of the same name.

## Regression corpus

`tests/corpus/bc_like.json` (the Business-Central-shaped corpus of round F2) now reads through the pack. Keys right /
wrong / missed / extra and links found / wrong:

| `bc_like` | Before PK2 | With the pack |
| --- | --- | --- |
| Names only | 3 / 4 / 3 / 0, 0 / 0 | 10 / 0 / 0 / 0, 10 / 0 |
| With the row profile | 8 / 2 / 0 / 0, 10 / 1 | 10 / 0 / 0 / 0, 10 / 0 |

The two links still missed are Sales Line and Purchase Line No. to Item, which the pack applies only filtered on
Type, a column this corpus lacks. The new corpus `dynamics365` is the demo: 33 of 33 keys and 57 of 57 plain key links
by names alone ([SCORES.md](SCORES.md); the truth is written from the pack, so this shows the pack is read, not that it
is right).

## Sources, and what is verified

Every page was opened on 17 November 2026; the module files carry each page's `ms.date`.

| Claim | Source | Status |
| --- | --- | --- |
| Dataverse keys, lookups and their targets, money columns, for all 20 tables | Learn table/column reference (`power-apps/.../reference/entities/<t>` for account, contact, systemuser, team, businessunit, transactioncurrency, activitypointer; `dynamics365/developer/reference/entities/<t>` for the other 13), ms.date 2026-09-18 | Verified on Learn |
| Fabric Link landing: Delta in Dataverse storage, shortcuts in a lakehouse, tables with Track changes | `azure-synapse-link-view-in-fabric` (2026-07-06), `fabric-link-to-data-platform` (2026-11-11) | Verified on Learn |
| System columns `Id`, `IsDelete`, `SinkCreatedOn`, `SinkModifiedOn`, `versionnumber`; soft and hard deletes | `azure-synapse-link-select-fno-data` (2026-11-03), `export-data-lake-faq` (2026-11-06) | Verified on Learn; the two pages differ on 28 or 30 days, and one sentence on filtering `isDelete` reads reversed |
| Choice labels in metadata tables; TargetMetadata names lookups by logical name | `azure-synapse-link-choice-labels` (2022-04-27) | Verified on Learn |
| `_<name>_value` lookups; multi-table lookups | `webapi/web-api-properties` (2022-04-06), `webapi/multitable-lookup` (2026-10-27) | Verified on Learn |
| That every lookup column in the Fabric lakehouse is named by its logical name | none found | **Unverified**: no page read says so |
| How a type column of a multi-table lookup is spelled and valued in the lake | none found | **Unverified** |
| Business Central table numbers and field names | Learn base application table reference, ms.date 2024-10-01 (17 pages) | Verified on Learn |
| Business Central primary keys, FlowFields, table relations, enum values (Document Type, Line Type) | Microsoft's AL source, microsoft/BCApps at commit f9d965b8 (16 November 2026), Base Application 30.0.0.0 | Verified in first-party source, **not on Learn** (the Learn pages do not show them) |
| SQL names `<company>$<table>$<app id>`; per-company default; FlowFields not stored; system fields | Learn telemetry example (2026-03-30), DataPerCompany (2026-10-01), FlowFields (2026-07-02), system fields (2026-08-25) | Verified on Learn |
| Fabric mirroring of Business Central: an open mirrored database, preview, online only, several companies | `admin-fabric` and related (2026-10-29) | Verified on Learn; entity and column naming and the company column are **not documented** there |
| bc2adls naming (`<Table>-<id>`, `<Field>-<id>`, `$Company`), FlowFields refused | microsoft/bc2adls at b90a69e (6 September 2023) | Read in its source; the project is archived and listed as unsupported |
| API v2.0 entities keyed by `id` (SystemId) | `api-reference/v2.0` (2026-08-10; resources 2026-08-21) | Verified on Learn; the entities themselves are not in the pack |

Nothing has been checked against a real environment's or company's rows. `validate_plan` does that on yours.

## Keys and links from your own `$metadata` (layer 2)

Round BL25, 21 November 2026. The pack above is what Krusgraph knows about Dataverse in general. Your environment says
more about itself: the Web API publishes every table's key and every lookup in its CSDL `$metadata` document, custom
tables and columns included. `fabric_backend/dataverse_meta.py` reads that file, the same way `csn.py` reads an SAP
CSN file ([SAP-CSN.md](SAP-CSN.md)). It reads a file you hand over; it fetches nothing and refuses a URL.

**Exporting it.** Signed in to the environment, open
`https://<your-org>.api.crm.dynamics.com/api/data/v9.2/$metadata` in the browser and save the page as an `.xml` file
(the address is your environment's Web API endpoint followed by `$metadata`; Learn, "Dataverse Web API service
documents", ms.date 2026-10-26, opened 21 November 2026, also shows how to download it with Insomnia or PowerShell).
The file describes tables, columns and relationships, not rows.

**What it reads** (Learn, "Web API EntityTypes", ms.date 2023-05-18, and "Web API navigation properties", ms.date
2026-01-07, both opened 21 November 2026):

| In the `$metadata` | Becomes | Example |
| --- | --- | --- |
| `EntityType` `Key` / `PropertyRef` (inherited through `BaseType` when the type has none) | the table's key | `account`: `accountid`; `phonecall`: `activityid` from `activitypointer` |
| single-valued `NavigationProperty` with a `ReferentialConstraint` | a link, many-to-one, on the lookup column (`_parentaccountid_value` lands as `parentaccountid`) | `salesorderdetail.salesorderid` -> `salesorder.salesorderid` |
| one lookup property that is the constraint of several navigation properties | a multi-table lookup: one **filtered** link per target, on its type column | `salesorder.customerid` -> `account` where `customeridtype = 'account'`, and -> `contact` where it is `'contact'` |
| collection navigation properties that partner each other | a many-to-many: listed, not applied (the intersect table holds the pairs) | `opportunity` <-> `competitor` |
| complex types, enums, actions, functions, the entity container | counted under `ignored` | |

Every key and link is marked "declared by Dataverse metadata, not counted": it is a candidate, in the shape the CSN
reader gives, until `validate_plan` counts it in your rows. The report also says what does not map to the lakehouse:
tables Link to Fabric did not land, columns that are not there (not chosen, or renamed), a multi-table lookup whose type
column is missing (then it is not applied, never joined plainly), and the lake's own columns the `$metadata` does not
name.

```python
from fabric_backend import dataverse_meta
model = dataverse_meta.read("metadata.xml")
report = dataverse_meta.candidates(schema, model)   # keys, links, filtered, not_applied, unmatched, unmapped_columns
```

**Verified, and how.** Unit tests only (`tests/test_bl25_dataverse_meta.py`): a synthetic `$metadata` written for the
tests (`tests/fixtures/dataverse_metadata_demo.xml`: account, contact, salesorder, salesorderdetail, a many-to-many, two
multi-table lookups, an inherited key) against the synthetic demo lake above. Every declared link joins the demo rows
without an orphan. Not run on a `$metadata` exported from a real environment.

**Limits.** The type column of a multi-table lookup is read as `<lookup>type` (`customeridtype`), as the pack and the
demo do; that spelling is still **unverified** (the table above). Learn says `systemuser` and `team` take their key
`ownerid` from the abstract `principal`; a lake that lands `systemuserid` then reports the table as not matched rather
than guessing. Only the first `Schema` namespace is read.

**Fed to the plan (round BL42, 23 November 2026).** `dataverse_meta.plan(schema, model)` gives the plan with the declared
keys and plain lookups first, the way `csn.plan` does for a CSN: rule "Dataverse metadata", and `validate_plan` counts
them in your rows like any other link. Multi-table lookups and many-to-manys stay in the report (`plan.dataverse`), not
applied; a key you give still wins. From the command line:

```bash
krusgraph plan --folder ./landing --dataverse-metadata metadata.xml
```

It takes a saved file and refuses a URL. Unit tests only (`tests/test_bl42_dataverse_plan.py`, synthetic metadata and
demo lake). Next: read the file from the lakehouse's Files in the hosted tools and the workload item (`server.py`), as
the CSN file is.

## Combined with SAP (ON1)

Round ON1, 25 November 2026 ([SMOOTH/COMBINE-SOURCES.md](SMOOTH/COMBINE-SOURCES.md), section 7). With SAP and
Dynamics 365 as two schemas of one lakehouse (`schema="sap+d365"`):

- **Built:** the customer match (`account.accountnumber`, or a custom column that names SAP such as
  `new_sapcustomerno`, against `KNA1.KUNNR`; Business Central's `Customer` takes part through a column such as
  `SAP_Customer_No`) and the product match (`product.productnumber` against `MARA.MATNR`; `Item` likewise), each
  counted as matched, ambiguous, only in SAP and only in Dynamics 365, compared after trimming, case folding and
  stripping leading zeros. Link to Fabric's system columns (`Id`, `versionnumber`, ...) are never a match key. Once the
  person accepts a match, `create_ontology` drafts one shared ontology: Customer and Product shared, every other
  concept one entity type per source, relationships only where the plan proves them.
- **Not built:** the gold in the pipeline (creating the shared ontology answers `not_yet`); Order and Invoice across
  sources (no rule matches them); the filtered lookups (`customerid`, `ownerid`) as relationships; lines and products
  related to the shared Product; the agent over both; Business Central counted on rows (names only in the tests).

On the synthetic pair `tests/fixtures/sap_dynamics.py`: customers 3 matched, 2 ambiguous (two accounts carry customer
13), 2 only in SAP, 1 only in Dynamics 365; products 2 matched, 2 only in SAP, 1 only in Dynamics 365. Nothing here
was checked on a real environment's rows.

## Next

- **Finance and operations apps**: not a module yet. The route is Link to Microsoft Fabric, which can add finance and
  operations tables (Delta only, entities prefixed `mserp_`; `azure-synapse-link-select-fno-data`, ms.date
  2026-11-03). The tables to start with: `CustTable`, `CustInvoiceJour`, `CustInvoiceTrans`, `SalesTable`,
  `SalesLine`, `VendTable`, `GeneralJournalAccountEntry`, `InventTrans` (**unverified**: no Learn page opened in this
  round names them; `CustTable` appears there only as an example).
- Business Central through Fabric mirroring: confirm the entity and column names and the company column on a mirror,
  and add them as a variant.
- Business Central API entities (`salesOrders`, `salesOrderLines`, `generalLedgerEntries`) as a module of their own.
- The engine: keep `IsDelete`, `versionnumber` and `Sink*` out of measures, and let the drafts relate filtered
  relationships.
- Review: the manifest is `proposed`; a person reads it against the sources above before it becomes 1.0.0.

## Contributing

As for any pack ([PACKS.md](PACKS.md), "Adding a pack"): public sources only, every claim with a source and a status,
synthetic rows only, no customer, tenant or company names. `python -m fabric_backend.pack_manifest dynamics365
--write` regenerates the manifest; `python -m pytest -q tests/test_pk2_dynamics_pack.py tests/test_pack_manifest.py`
checks the pack.
