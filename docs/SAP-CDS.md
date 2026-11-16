# SAP CDS views: the released views in the SAP pack

Round n230, 15 November 2026. The founder asked on 12 November 2026: "Does Krusgraph work for CDS views too? We need to
test that." Until this round the SAP pack ([SAP.md](SAP.md)) knew tables (`VBAK`, `VBAP`, `KNA1`, `ACDOCA`) and not the
views SAP S/4HANA publishes over them (`I_SalesDocument`, `I_SalesDocumentItem`, `I_Customer`, `I_JournalEntryItem`),
whose names and fields are business names in camelCase and whose relations are associations.

The short answer: on a synthetic sample shaped like CDS views the engine now finds every key and link from the pack
and the row check shows the same kinds of findings as on the table-shaped sample. Everything in the pack about the
views is **proposed, not tested on a customer**: it is written from public knowledge of SAP's documentation, the
SAP pages that list each view's fields could not be opened from the writing session, and no SAP system has been read.
`validate_plan` checks every key and link against your rows; that check is the test.

## 1. How CDS view data reaches Fabric

What was read, and when. "Read" means the page was opened on 15 November 2026 and says this; **Unverified** means it
was not opened (the host is blocked from the session) or the page does not say it.

| Route | What the page says | Source, page date | Status |
| --- | --- | --- | --- |
| Mirroring SAP in Fabric | An SAP Datasphere replication flow extracts the source (initial load and changes) into Azure Data Lake Storage Gen2 as Parquet files, and the mirroring merges the files into the tables of a mirrored database. Sources are whatever Datasphere offers: SAP S/4HANA, SAP ECC, SAP BW/4HANA, SAP BW. The tutorial's worked example replicates CDS views of an SAP S/4HANA system (`CDS_EXTRACTION`). SAP's Premium Outbound Integration pricing applies. | Microsoft Fabric docs, `mirroring/sap.md`, `sap-limitations.md`, `sap-datasphere-tutorial.md`, each ms.date 02/26/2026 | Read |
| Copy job in Fabric Data Factory | The same two steps: Copy job reads what a Datasphere replication flow has landed in cloud storage ("SAP Datasphere Outbound"), inserts, updates and deletions, with the same CDS example. | `data-factory/copy-job-tutorial-sap-datasphere.md` ms.date 05/22/2026; `cdc-copy-job.md` ms.date 03/17/2026 | Read |
| SAP connectors in Fabric Data Factory | The connector overview lists SAP Table, SAP HANA, SAP BW and SAP BW Open Hub (pipelines and Copy job for Table, HANA and Open Hub). It lists no ODP-based SAP CDC connector. | `data-factory/connector-overview.md` ms.date 10/30/2026 | Read |
| SAP CDC connector (ODP) | Azure Data Factory and Synapse, not Fabric: CDS views are read through the ODP context `ABAP_CDS` by an ODP name, and incremental runs need the key columns named. The page notes SAP Note 3255746, which restricts the ODP RFC interface for third-party clients. | Azure Data Factory docs, `sap-change-data-capture-introduction-architecture.md` ms.date 02/13/2025; the dataset page ms.date 05/15/2024 | Read |
| Open mirroring partners | Several partner tools that read SAP are listed; what each lands is the tool's own. | `mirroring/open-mirroring-partners-ecosystem.md` ms.date 05/29/2026 | Read |
| Which views a replication flow can read | Extraction-enabled CDS views that are C1-released (`@Analytics.dataExtraction.enabled: true`); delta needs the change data capture annotation; a source without a primary key supports an initial load only. A cloud storage target gets three columns appended: `__operation_type`, `__sequence_number`, `__timestamp`. | SAP Datasphere documentation (github.com/SAP-docs/sap-datasphere, commit of 20 October 2026; the pages carry no date) | Read |
| Which views are released | The views named in this document are all listed as released; `I_Material` is not to be released, and `C_SalesDocumentItemDEX` is deprecated for `C_SalesDocumentItemDEX_1`. The list holds no fields. | SAP Cloudification Repository (github.com/SAP/abap-atc-cr-cv-s4hc, commit of 12 November 2026) | Read |
| The fields, keys and associations of each view | The catalogue is the SAP Business Accelerator Hub (api.sap.com, CDS views) and the SAP Help Portal. | api.sap.com, help.sap.com | **Unverified**: not opened (network policy) |

**The shape that lands in OneLake.** None of the Microsoft pages says how the mirrored tables and columns are named,
whether keys are declared on them, or whether a client column is present. What follows is therefore **Unverified**,
from public knowledge and not from a page:

- Table name: the replication flow's target object, which defaults to the view's name (`I_SalesDocument`).
- Field names: the view's element names (`SalesDocument`, `SoldToParty`), not the table's (`VBELN`, `KUNNR`); a route
  through the ABAP extraction interfaces may write them in upper case (`SALESDOCUMENT`).
- Keys: the view's key fields are in the data, and delta needs them; nothing read says they arrive as declared
  constraints. Krusgraph does not rely on declared keys: the pack names them and `validate_plan` counts them.
- Client: a CDS view handles the client itself and does not list it as a field, so no `MANDT` column is expected, and
  one extraction holds one client.
- Change columns: `__operation_type` and `__timestamp` are in the landed files (read, above); whether the mirrored
  table keeps them is not stated.
- The SAP Table connector reads dictionary objects, so it would address a classic view by its SQL view name and land
  upper-case technical columns with the client: a different shape, which the pack does not recognise by name.

So the first live test has one question before any other: **what are the tables and columns called in your
lakehouse?** If they are the view's names in any case, with or without `I_`, the pack reads them.

## 2. What the pack covers

Three module files in `fabric_backend/packs/sap/`: `cds_order_to_cash.json`, `cds_master_data.json` and
`cds_journal.json`. 19 views, 44 relationships (39 written from a named association), 9 traps. Every view has its
key fields, the table it reads (`corresponds_to`), its amounts with their level and currency field, the fields in the
source's own spelling (`source_columns`), and its sources with whether each was read.

| View | Key fields | Reads | Amounts (level, currency field) |
| --- | --- | --- | --- |
| `I_SalesDocument` | `SalesDocument` | `VBAK` | `TotalNetAmount` (header, `TransactionCurrency`) |
| `I_SalesDocumentItem` | `SalesDocument`, `SalesDocumentItem` | `VBAP` | `NetAmount` (item, `TransactionCurrency`) |
| `I_SalesDocumentScheduleLine` | `SalesDocument`, `SalesDocumentItem`, `ScheduleLine` | `VBEP` | none named |
| `I_SalesOrder` | `SalesOrder` | `VBAK` | `TotalNetAmount` (header, `TransactionCurrency`) |
| `I_SalesOrderItem` | `SalesOrder`, `SalesOrderItem` | `VBAP` | `NetAmount` (item, `TransactionCurrency`) |
| `I_DeliveryDocument` | `DeliveryDocument` | `LIKP` | none named |
| `I_DeliveryDocumentItem` | `DeliveryDocument`, `DeliveryDocumentItem` | `LIPS` | none named |
| `I_BillingDocument` | `BillingDocument` | `VBRK` | `TotalNetAmount` (header, `TransactionCurrency`); `TotalTaxAmount` (header, `TransactionCurrency`) |
| `I_BillingDocumentItem` | `BillingDocument`, `BillingDocumentItem` | `VBRP` | `NetAmount` (item, `TransactionCurrency`); `TaxAmount` (item, `TransactionCurrency`) |
| `I_Customer` | `Customer` | `KNA1` | none named |
| `I_CustomerSalesArea` | `Customer`, `SalesOrganization`, `DistributionChannel`, `Division` | `KNVV` | none named |
| `I_Supplier` | `Supplier` | `LFA1` | none named |
| `I_Product` | `Product` | `MARA` | none named |
| `I_ProductText` | `Product`, `Language` | `MAKT` | none named |
| `I_CompanyCode` | `CompanyCode` | `T001` | none named |
| `I_SalesOrganization` | `SalesOrganization` | `TVKO` | none named |
| `I_JournalEntry` | `CompanyCode`, `FiscalYear`, `AccountingDocument` | `BKPF` | none named |
| `I_JournalEntryItem` | `SourceLedger`, `CompanyCode`, `FiscalYear`, `AccountingDocument`, `LedgerGLLineItem`, `Ledger` | `ACDOCA` | `AmountInTransactionCurrency` (item, `TransactionCurrency`); `AmountInCompanyCodeCurrency` (item, `CompanyCodeCurrency`); `AmountInGlobalCurrency` (item, `GlobalCurrency`) |
| `I_GLAccountLineItemRawData` | `SourceLedger`, `CompanyCode`, `FiscalYear`, `AccountingDocument`, `LedgerGLLineItem` | `ACDOCA` | `AmountInTransactionCurrency` (item, `TransactionCurrency`); `AmountInCompanyCodeCurrency` (item, `CompanyCodeCurrency`); `AmountInGlobalCurrency` (item, `GlobalCurrency`) |

**Associations as candidate links.** A CDS association is written from the side that holds the reference, many-to-one,
with the association and the cardinality the view declares on the row (`association`):
`I_SalesDocumentItem.SalesDocument → I_SalesDocument` is `_SalesDocument [1..1]` on the item and `_Item [0..*]` on the
header; `I_SalesDocument.SoldToParty → I_Customer.Customer` is `_SoldToParty [0..1]`. The billing item points at its
sales document item (`SalesDocument`, `SalesDocumentItem`) and at its reference document item (`ReferenceSDDocument`,
`ReferenceSDDocumentItem`, the delivery for delivery-related billing); the billing document at its journal entry
(`CompanyCode`, `FiscalYear`, `AccountingDocument`). The association names and cardinalities are Unverified like the
fields.

**Matching.** By name and by key fields, as for the tables. The name is compared without case and underscores, so
`I_SalesDocument`, `i_salesdocument`, `I_SALESDOCUMENT` and `i_sales_document` are one name, a leading layer word is
dropped (`bronze_`, `sap_`, `cds_`), and each view also answers to its name without `I_` (`SalesDocument`). A table is
taken only when the view's key fields are among its columns, compared the same way (`SalesDocumentItem`,
`SALESDOCUMENTITEM`, `sales_document_item`). `Customer`, `Product` and `Supplier` without the prefix are ordinary
words: a schema with only those is not read as SAP. A view is never joined to the table it reads.

**What it does not do.** It does not recognise a technical SQL view name or an extractor's own name, a renamed field,
or a custom view (`Z...`, `YY1_...`): give those keys and links to `plan_backend` yourself, or rename in the landing.
It does not know the extraction views' own field lists (`C_SalesDocumentItemDEX_1`, `C_BillingDocItemBasicDEX_1`), the
partner, pricing or purchasing views, or cost and profit centers.

## 3. The synthetic sample and its numbers

`fabric_backend/sap_cds_demo.py` tells the small order-to-cash story of the dbo sample (`sap_demo.py`) in CDS shape:
14 tables named as views (`I_SalesDocument`, `I_SalesDocumentItem`, `I_SalesDocumentScheduleLine`,
`I_DeliveryDocument`, `I_DeliveryDocumentItem`, `I_BillingDocument`, `I_BillingDocumentItem`, `I_Customer`,
`I_Product`, `I_ProductText`, `I_CompanyCode`, `I_SalesOrganization`, `I_JournalEntry`, `I_JournalEntryItem`),
camelCase fields, no client column. Every value is made up; no row comes from an SAP system. Measured on
15 November 2026 with the unit tests (SQLite), not yet in Fabric:

- The plan: 14 of 14 tables recognised by the pack, 14 keys and 30 links, all by the rule "SAP pack". The same in
  five spellings: as the view writes them, without `I_`, lower case, snake case, upper case.
- The row check (`validate_plan`): 14 of 14 keys unique, 29 of 30 relationships hold without orphans.
- The orphan: `I_SalesDocumentItem → I_SalesDocument` has 1 row that points at nothing, the planted item of order
  0000000009.
- The total that doubles: `I_SalesDocument.TotalNetAmount` summed over the join with `I_SalesDocumentItem` gives
  1 900, against 700 summed once per order. `I_BillingDocument.TotalNetAmount` over its items gives 800 against 400.
- The dbo sample for comparison (17 tables, with a second client and the document flow): 17 of 17 keys, 32 of 34
  links ([LIVE-TEST-SAP.md](LIVE-TEST-SAP.md)).

A run on these rows shows that the engine reads CDS-shaped tables. It proves nothing about SAP: the rows are written
from the pack, and `sap-verify` refuses to record such a run.

## 4. Testing it in Fabric

1. In a notebook attached to a lakehouse with schemas:

   ```python
   %pip install git+https://github.com/Krusmaster/fabric-backend
   from fabric_backend.seed import seed
   seed(spark, schema="sap_cds")
   ```

   It writes the 14 tables to the schema `sap_cds` and nothing else (on a lakehouse without schemas, to the default
   schema: use `dbo`).
2. In the chat, say **Start Krusgraph** and choose the schema `sap_cds`.
3. Expect: 14 tables recognised by the SAP pack, 14 keys, 30 links; `validate_plan` answers "14 of 14 keys unique,
   29 of 30 relationships hold without orphans", names the one orphan in `I_SalesDocumentItem` and lists
   `I_SalesDocument.TotalNetAmount` as a header amount a join with the items repeats.
4. Then the real test: point it at a schema where CDS views of an SAP system have landed, and send back the table
   and column names it did not recognise.

## 5. Sources

Each module file lists its sources with `fetched` and a note; the manifest (`packs/sap/manifest.yaml`) shows them as
`verified` or not. Read on 15 November 2026: the Microsoft Fabric and Azure Data Factory pages above, the SAP
Datasphere documentation and the SAP Cloudification Repository. Not opened, and so Unverified: the SAP Business
Accelerator Hub and the SAP Help Portal, which is where the fields, key fields, associations and the view-to-table
mapping of every view would be confirmed. That is the first thing a review of these modules should do
([PACKS.md](PACKS.md), the review step).

Nothing in this round deploys or calls Azure, Entra, DNS or Fabric.
