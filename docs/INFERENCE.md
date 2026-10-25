# Inference quality

How well `plan()` recovers declared primary and foreign keys from table and column names alone, measured on five
openly available example databases. The ground truth is the keys their official DDL declares; the sources and
licences are listed in `tests/fixtures/schemas/README.md`. The benchmark is `tests/test_inference_quality.py`,
which asserts these exact numbers, so a rule change has to update this page.

Method: each schema is loaded with columns and types only, as a lakehouse SQL analytics endpoint presents it
(no keys, no foreign keys), and `plan()` runs without `keys` or `confirmed`.

- **Keys hit:** tables whose inferred key is exactly the declared primary key. **Wrong:** a key was inferred but
  differs from the declared one. **Missed:** no key inferred.
- **Rels hit:** declared foreign keys (source table, columns, target table) that were inferred. **Missed:** declared
  but not inferred. **Wrong:** inferred but not declared. A "wrong" relationship is not always a bad join (see the
  notes), but it is one the DDL does not back.

## Results, 25 October 2026 (unit test, no live workspace)

| Schema | Tables | Keys declared | Keys hit | Keys wrong | Keys missed | FKs declared | Rels hit | Rels missed | Rels wrong | Ambiguous |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| northwind | 13 | 13 | 11 | 0 | 2 | 13 | 10 | 3 | 0 | 0 |
| chinook | 11 | 11 | 11 | 0 | 0 | 11 | 9 | 2 | 0 | 0 |
| tpch | 8 | 8 | 8 | 0 | 0 | 8 | 8 | 0 | 2 | 0 |
| adventureworks | 71 | 71 | 47 | 4 | 20 | 90 | 62 | 28 | 17 | 0 |
| sakila | 16 | 16 | 15 | 0 | 1 | 22 | 22 | 0 | 1 | 0 |

Before the rules below were added (same fixtures, same scoring):

| Schema | Keys hit | Keys wrong | Keys missed | Rels hit | Rels missed | Rels wrong |
| --- | --- | --- | --- | --- | --- | --- |
| northwind | 9 | 0 | 4 | 10 | 3 | 0 |
| chinook | 10 | 0 | 1 | 9 | 2 | 0 |
| tpch | 0 | 0 | 8 | 0 | 8 | 0 |
| adventureworks | 32 | 3 | 36 | 46 | 44 | 16 |
| sakila | 13 | 0 | 3 | 20 | 2 | 1 |

The synthetic shop schema (`fabric_backend/seed.py`) is unchanged except that `order_items` now gets its key
`order_id + line_no` by rule K5 instead of needing the `keys` override: 7 tables, 6 with keys, 6 relationships,
`audit_log` keyless, `orders.ship_to_id` unlinked, no ambiguity.

## What was added

Every rule is described in `fabric_backend/infer.py` and has a test in `tests/test_infer_rules.py`.

| Change | Rule | What it fixed |
| --- | --- | --- |
| A prefix shared by every column of a table is not part of the name (`N_NATIONKEY` in NATION reads as `nationkey`) | K2, R1–R4 | TPC-H: 0 → 8 keys, 0 → 8 relationships |
| `<table>_code` counts like `<table>_id` | K2, R1 | AdventureWorks `Currency`, `CountryRegion`, `UnitMeasure` and the columns that point at them |
| `<X>Header` / `<X>_hdr` also answers to `<X>` | K2, R1 | `SalesOrderHeader.SalesOrderID`, `PurchaseOrderHeader.PurchaseOrderID` and their detail tables |
| Abbreviations of four letters or more (`cust_key` → customer), never when the abbreviation is another table's name | K2, R4 | TPC-H `O_CUSTKEY`, `L_SUPPKEY`; `PS_PARTKEY` stays a reference to PART |
| A role before the target's name (`manager_staff_id` → staff, `ShipToAddressID` → Address), on a word boundary | R4 | Sakila 20 → 22 relationships; AdventureWorks bill-to/ship-to addresses, from/to currencies, size/weight unit measures |
| Junction key: the leading run of two or more reference columns, not for history tables | K4 | `film_actor`, `PlaylistTrack`, `Order Details`, `PARTSUPP`, `EmployeeTerritories`, nine AdventureWorks bridge tables |
| Line key: header reference plus a line-number column | K5 | `LINEITEM` (`L_ORDERKEY` + `L_LINENUMBER`), shop `order_items` |
| R3 compares names after prefix stripping | R3 | `LINEITEM (L_PARTKEY, L_SUPPKEY) → PARTSUPP`, `SalesOrderDetail (SpecialOfferID, ProductID) → SpecialOfferProduct` |

Field names in GraphQL definitions are unchanged for every column the old rules matched, so an existing API is
not renamed by an update.

## What is still missed, and why

- **Columns that name a role but not the table** (`Orders.ShipVia`, `Employees.ReportsTo`, `Customer.SupportRepId`,
  `Document.Owner`, `BillOfMaterials.ComponentID`): nothing in the name says which table. `confirmed=[...]` is the
  way to add them.
- **Subtype chains** (AdventureWorks `Person`, `Employee`, `SalesPerson`, `Vendor`, `Store` are all keyed by
  `BusinessEntityID`): no column is named after the table, so these tables get no key, and every `BusinessEntityID`
  column points at `BusinessEntity` rather than the nearest subtype the DDL declares. That accounts for 12 of the
  17 "wrong" AdventureWorks relationships; the join is still valid, the target is the root of the chain. Give
  `keys={"Person": ["BusinessEntityID"], ...}` to get the declared picture.
- **History tables** keyed by a reference plus a date (`ProductCostHistory`, `EmployeePayHistory`,
  `SalesTerritoryHistory`): not guessed; `plan_backend` suggests `reference + start_date` under `suggested_keys`
  where a start column exists, and `validate_plan` checks the suggestion for uniqueness.
- **Keys named after something else** (`CustomerDemographics.CustomerTypeID`, `SalesTerritory.TerritoryID`,
  `TransactionHistory.TransactionID`, `Document.DocumentNode`): not inferred; a rule that strips words from table
  names would mis-key tables such as `order_items` (`item_id`) and was not added.
- **Composite primary keys that include a surrogate** (`SalesOrderDetail`: `SalesOrderID + SalesOrderDetailID`): the
  rules take the `<table>ID` column alone, which is unique on its own. Counted as "wrong" here.
- **`WorkOrderRouting`**: `WorkOrderID + OperationSequence` is inferred (K5); the declared key also has `ProductID`.
  Its inferred `ProductID + LocationID → ProductInventory` (R3) is a plausible but undeclared link.
- **TPC-H's two "wrong" relationships** (`L_PARTKEY → PART`, `L_SUPPKEY → SUPPLIER`) are foreign keys in the
  specification's table layouts but not in `dss.ri`; see the fixture README.
- **Sakila's one** (`film_text.film_id → film`) is a one-to-one extension table without a declared foreign key.

## Rerunning

```
python -m pytest -q tests/test_inference_quality.py tests/test_infer_rules.py
PYTHONPATH=. python tests/test_inference_quality.py       # the table above, plus the missed and wrong items per schema
```

These numbers are for the repository and this page only; the website does not quote them.
