# Scores

How many keys and links Krusgraph's rules find on schemas whose true keys and links are known. The numbers are
written by `python tests/f2_corpus.py --write-docs` from `tests/corpus/*.json`, and `tests/test_f2_corpus.py` fails
when the engine gives other numbers, a different plan or different row results. `docs/scores.json` holds the same
numbers for a program.

- **Names**: names only, no rows read (what `tests/test_inference_quality.py` measures).
- **Before**: names and R5 over the rows, as `main` planned at commit `8066dd0`, before round F2.
- **After**: with the row profile of round F2: keys counted in the same call, K6 (a key from the rows), R6 (a link
  from the rows) and a pack table recognised by its key columns (`fabric_backend/propose.py`, `docs/INFERENCE.md`).

A key is right when it is exactly the true set of columns, wrong when it is another set, missed when the table gets
none, extra when the table has no key and the plan gives it one. A link is found when source, columns and target are a true link; a wrong link is a link of the plan that is
not a true link.

**The rows are synthetic in every corpus.** For AdventureWorks the tables, columns, keys and foreign keys are the ones
Microsoft's script declares; the rows are generated from those declared constraints, because the sample's own rows
are not in this repository. Its numbers say what the rules do with rows that follow the declared constraints. They
are not a measurement on the sample's own rows, and no corpus here is a customer's data. Nothing on this page was run
in Fabric: the corpus runs on SQLite with the SQL the engine writes.

## Keys

| Corpus | Tables | True keys | Names: right / wrong / missed / extra | Before: right / wrong / missed / extra | After: right / wrong / missed / extra |
| --- | --- | --- | --- | --- | --- |
| AdventureWorks (OLTP) (`adventureworks`) | 71 | 71 | 47 / 4 / 20 / 0 | 47 / 4 / 20 / 0 | 62 / 6 / 3 / 0 |
| Shop sample (`shop`) | 7 | 6 | 6 / 0 / 0 / 0 | 6 / 0 / 0 / 0 | 6 / 0 / 0 / 0 |
| SAP-shaped sample, order to invoice (`sap_sd`) | 12 | 12 | 10 / 0 / 2 / 0 | 10 / 0 / 2 / 0 | 12 / 0 / 0 / 0 |
| SAP-shaped sample, purchase to pay (`sap_mm`) | 8 | 8 | 7 / 0 / 1 / 0 | 7 / 0 / 1 / 0 | 8 / 0 / 0 / 0 |
| SAP-shaped sample, tables renamed (`sap_renamed`) | 12 | 12 | 0 / 0 / 12 / 0 | 0 / 0 / 12 / 0 | 11 / 0 / 1 / 0 |
| Nordic-ERP-like shape (`nordic_erp`) | 8 | 8 | 0 / 0 / 8 / 0 | 0 / 0 / 8 / 0 | 8 / 0 / 0 / 0 |
| Business-Central-like shape (`bc_like`) | 10 | 10 | 10 / 0 / 0 / 0 | 10 / 0 / 0 / 0 | 10 / 0 / 0 / 0 |
| Dynamics 365 demo (Dataverse and Business Central) (`dynamics365`) | 33 | 33 | 33 / 0 / 0 / 0 | 33 / 0 / 0 / 0 | 33 / 0 / 0 / 0 |
| Salesforce-shaped sample, lead to cash and service (`salesforce`) | 21 | 21 | 21 / 0 / 0 / 0 | 21 / 0 / 0 / 0 | 21 / 0 / 0 / 0 |

## Links

| Corpus | True links | Names: found / wrong | Before: found / wrong | After: found / wrong |
| --- | --- | --- | --- | --- |
| AdventureWorks (OLTP) (`adventureworks`) | 90 | 62 / 17 | 62 / 17 | 87 / 6 |
| Shop sample (`shop`) | 7 | 6 / 0 | 7 / 0 | 7 / 0 |
| SAP-shaped sample, order to invoice (`sap_sd`) | 18 | 17 / 2 | 17 / 2 | 17 / 2 |
| SAP-shaped sample, purchase to pay (`sap_mm`) | 7 | 7 / 1 | 7 / 1 | 7 / 1 |
| SAP-shaped sample, tables renamed (`sap_renamed`) | 18 | 0 / 0 | 0 / 0 | 13 / 2 |
| Nordic-ERP-like shape (`nordic_erp`) | 9 | 0 / 0 | 0 / 0 | 5 / 0 |
| Business-Central-like shape (`bc_like`) | 12 | 10 / 0 | 10 / 0 | 10 / 0 |
| Dynamics 365 demo (Dataverse and Business Central) (`dynamics365`) | 57 | 57 / 0 | 57 / 0 | 57 / 0 |
| Salesforce-shaped sample, lead to cash and service (`salesforce`) | 53 | 53 / 0 | 53 / 0 | 53 / 0 |

## The corpora

### AdventureWorks (OLTP) (`adventureworks`)

Source: tables, keys and foreign keys as Microsoft's script declares them; rows generated from those constraints (synthetic), not the sample's own rows. 14890 rows in 71 tables.

Keys still wrong after (6): `BusinessEntityContact`, `EmailAddress`, `EmployeeDepartmentHistory`, `PurchaseOrderDetail`, `SalesOrderDetail`, `WorkOrderRouting`.

Keys still missed after (3): `Document`, `PersonPhone`, `ProductDocument`.

Links still missed after (3): `BillOfMaterials.componentid -> Product`, `Document.owner -> Employee`, `ProductDocument.documentnode -> Document`.

Links still wrong after (6): `SalesOrderDetail.productid -> Product`, `SalesOrderDetail.specialofferid -> SpecialOffer`, `TransactionHistoryArchive.productid -> Product`, `TransactionHistoryArchive.transactionid -> TransactionHistory`, `WorkOrderRouting.locationid+productid -> ProductInventory`, `WorkOrderRouting.productid -> Product`.

Proposed, not applied (3):

- Address.PostalCode -> AddressType [R5]: Address.PostalCode is text, AddressType.AddressTypeID is number
- Address.PostalCode -> EmailAddress [R5]: Address.PostalCode is text, EmailAddress.EmailAddressID is number
- Address.PostalCode -> Location [R5]: Address.PostalCode is text, Location.LocationID is number

Row results of the plan after: 68 of 68 keys unique, 92 of 93 relationships hold without orphans.

### Shop sample (`shop`)

Source: fabric_backend/seed.py, synthetic. 272 rows in 7 tables.

Row results of the plan after: 6 of 6 keys unique, 7 of 7 relationships hold without orphans.

### SAP-shaped sample, order to invoice (`sap_sd`)

Source: fabric_backend/sap_sample.py, synthetic, SAP-shaped, not SAP data. 4327 rows in 12 tables.

Links still missed after (1): `ZSD_KAM_ASSIGN.zz_kunde_nr -> KNA1`.

Links still wrong after (2): `ZSD_ORDER_EXT.mandt+vbeln -> LIKP`, `ZSD_ORDER_EXT.mandt+vbeln -> VBRK`.

Row results of the plan after: 12 of 12 keys unique, 15 of 19 relationships hold without orphans.

### SAP-shaped sample, purchase to pay (`sap_mm`)

Source: fabric_backend/sap_sample.py, synthetic, SAP-shaped, not SAP data. 2637 rows in 8 tables.

Links still wrong after (1): `ZMM_PO_CONF.ebeln+mandt -> EKKO`.

Row results of the plan after: 8 of 8 keys unique, 7 of 8 relationships hold without orphans.

### SAP-shaped sample, tables renamed (`sap_renamed`)

Source: the order-to-invoice sample with table names that say nothing to the pack (sales_doc_header for VBAK); synthetic. 4327 rows in 12 tables.

Keys still missed after (1): `material_texts`.

Links still missed after (5): `billing_header.bukrs+mandt -> company_codes`, `billing_header.kunag+mandt -> customer_master`, `billing_header.kunrg+mandt -> customer_master`, `delivery_header.kunag+mandt -> customer_master`, `kam_assignment.zz_kunde_nr -> customer_master`.

Links still wrong after (2): `order_extension.mandt+vbeln -> billing_header`, `order_extension.mandt+vbeln -> delivery_header`.

Recognised by key columns: `billing_header` as VBRK, `billing_item` as VBRP, `delivery_header` as LIKP, `delivery_item` as LIPS, `material_master` as MARA, `sales_doc_header` as VBAK, `sales_doc_item` as VBAP.

Proposed, not applied (4):

- billing_header.MANDT+BUKRS -> company_codes [R6]: billing_header.BUKRS has 1 distinct value: too few to tell
- billing_header.MANDT+KUNAG -> customer_master [R6]: 292 of 292 value(s) of billing_header.KUNAG are in customer_master.KUNNR, but the name gives no support: confirm it to apply it
- billing_header.MANDT+KUNRG -> customer_master [R6]: 292 of 292 value(s) of billing_header.KUNRG are in customer_master.KUNNR, but the name gives no support: confirm it to apply it
- delivery_header.MANDT+KUNAG -> customer_master [R6]: 292 of 292 value(s) of delivery_header.KUNAG are in customer_master.KUNNR, but the name gives no support: confirm it to apply it

Row results of the plan after: 11 of 11 keys unique, 11 of 15 relationships hold without orphans.

### Nordic-ERP-like shape (`nordic_erp`)

Source: short Swedish names (kus, oh, orp, ftgnr, artnr); synthetic, written for this corpus, not a product's schema. 1150 rows in 8 tables.

Planted on purpose: fh.kundnr holds kus.ftgnr without its leading zeros: the link holds only after stripping them; orp: 3 rows of order 59999, which is not in oh.

Links still missed after (4): `fh.kundnr -> kus`, `kus.saljare -> salj`, `oh.saljare -> salj`, `orp.ordernr -> oh`.

Proposed, not applied (4):

- fh.kundnr -> kus [R6]: fh.kundnr fits no key as written; 158 of 158 rows with a value match after stripping leading zeros (0 as written) in kus.ftgnr: the link holds only with that conversion, so it is proposed, not applied (the join needs the same conversion on both sides)
- kus.saljare -> salj [R6]: 80 of 80 value(s) of kus.saljare are in salj.sign, but the name gives no support: confirm it to apply it
- oh.saljare -> salj [R6]: 200 of 200 value(s) of oh.saljare are in salj.sign, but the name gives no support: confirm it to apply it
- orp.ordernr -> oh [R6]: 3 of 491 value(s) of orp.ordernr are not in oh.ordernr; re-counted over all rows: 488 of 491 rows with a value match as written; trimming spaces, folding case and stripping leading zeros match no more

Row results of the plan after: 8 of 8 keys unique, 5 of 5 relationships hold without orphans.

### Business-Central-like shape (`bc_like`)

Source: `<company>$<table>$<app id>` table names, `No_` keys; synthetic, written for this corpus, not Microsoft's schema. 1181 rows in 10 tables.

Links still missed after (2): `Example AB$Purchase Line$437dbf0e-84ff-417a-965d-ed2bb9650972.no_ -> Example AB$Item$437dbf0e-84ff-417a-965d-ed2bb9650972`, `Example AB$Sales Line$437dbf0e-84ff-417a-965d-ed2bb9650972.no_ -> Example AB$Item$437dbf0e-84ff-417a-965d-ed2bb9650972`.

Row results of the plan after: 10 of 10 keys unique, 10 of 10 relationships hold without orphans.

### Dynamics 365 demo (Dataverse and Business Central) (`dynamics365`)

Source: fabric_backend/dynamics_demo.py, SYNTHETIC DEMO DATA written from the dynamics365 pack; Dataverse as Link to Microsoft Fabric lands it, Business Central as bc2adls names it. 109 rows in 33 tables.

Planted on purpose: one salesorderdetail row soft-deleted (IsDelete 1, empty body); activity Demo call 2 regarding an account purged from the lake (a filtered link, in plan.extended); Business Central customer C10000, item 1000 and invoice 103001 in two companies ($Company in the key).

Row results of the plan after: 33 of 33 keys unique, 81 of 89 relationships hold without orphans.

### Salesforce-shaped sample, lead to cash and service (`salesforce`)

Source: fabric_backend/salesforce_demo.py, synthetic rows written from the salesforce pack, object and field API names as a Copy job lands them; not Salesforce data. 81 rows in 21 tables.

Planted on purpose: PricebookEntry.Pricebook2Id -> Pricebook2 has an orphan: a price book deleted while lines used it is archived and not returned; Opportunity.Pricebook2Id -> Pricebook2 has an orphan: a price book deleted while lines used it is archived and not returned.

Row results of the plan after: 21 of 21 keys unique, 51 of 53 relationships hold without orphans.

## Not in the corpus

- `sap_cds`: n230's CDS-shaped sample (seed(spark, schema='sap_cds')) is not on main at the time of this round; it is added here when it is.
- Real ERP data, a schema of several hundred tables, and a run on a Fabric SQL endpoint: none is here. The profile's
  statements are T-SQL that SQLite also runs; the leading-zero strip uses `PATINDEX`, which the test database emulates.
