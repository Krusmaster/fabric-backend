# Inference quality

How well `plan()` recovers declared primary and foreign keys from table and column names alone, measured on seven
openly available example databases and four synthetic naming fixtures. The ground truth is the keys the official DDL
declares (for the synthetic fixtures: the keys their names were written to express); sources and licences are in
`tests/fixtures/schemas/README.md`. The benchmark is `tests/test_inference_quality.py`, which asserts these exact
numbers, so a rule change has to update this page.

Method: each schema is loaded with columns and types only, as a lakehouse SQL analytics endpoint presents it
(no keys, no foreign keys), and `plan()` runs without `keys` or `confirmed`.

- **Keys hit:** tables whose inferred key is exactly the declared primary key. **Wrong:** a key was inferred but
  differs from the declared one. **Missed:** no key inferred.
- **Rels hit:** declared foreign keys (source table, columns, target table) that were inferred. **Missed:** declared
  but not inferred. **Wrong:** inferred but not declared. A "wrong" relationship is not always a bad join (see the
  notes), but it is one the DDL does not back.

## Results, 26 October 2026 (unit test, no live workspace)

| Schema | Tables | Keys declared | Keys hit | Keys wrong | Keys missed | FKs declared | Rels hit | Rels missed | Rels wrong | Ambiguous |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| northwind | 13 | 13 | 11 | 0 | 2 | 13 | 10 | 3 | 0 | 0 |
| chinook | 11 | 11 | 11 | 0 | 0 | 11 | 9 | 2 | 0 | 0 |
| tpch | 8 | 8 | 8 | 0 | 0 | 8 | 8 | 0 | 2 | 0 |
| adventureworks | 71 | 71 | 47 | 4 | 20 | 90 | 62 | 28 | 17 | 0 |
| sakila | 16 | 16 | 15 | 0 | 1 | 22 | 22 | 0 | 1 | 0 |
| wideworldimporters | 33 | 31 | 30 | 0 | 1 | 98 | 65 | 33 | 0 | 0 |
| wideworldimportersdw | 14 | 13 | 8 | 5 | 0 | 29 | 26 | 3 | 0 | 0 |
| nordic_sv (synthetic) | 6 | 6 | 6 | 0 | 0 | 6 | 6 | 0 | 0 | 0 |
| nordic_de (synthetic) | 5 | 5 | 5 | 0 | 0 | 5 | 4 | 1 | 0 | 0 |
| dw_names (synthetic) | 4 | 4 | 4 | 0 | 0 | 3 | 3 | 0 | 0 | 0 |
| app_names (synthetic) | 7 | 7 | 7 | 0 | 0 | 8 | 6 | 2 | 0 | 0 |

The synthetic shop schema (`fabric_backend/seed.py`) is unchanged: 7 tables, 6 with keys, 6 relationships, `audit_log`
keyless, `orders.ship_to_id` unlinked, no ambiguity; every field name of an existing API stays the same.

## The naming rules of 26 October: before and after

Added on 26 October 2026 (commit of that day; the five original fixtures are unchanged to the number, which the test
asserts): a documented synonym table, transliteration, irregular plurals, table-kind prefixes, the `_sk`/`_bk`
suffixes, a suffix tie-break and a suffix guard for the weakest rule. Measured with the old rules and the new ones on the
same fixtures in two separate processes:

| Schema | Tables | Keys hit before → after | Rels hit before → after | Rels wrong before → after |
| --- | --- | --- | --- | --- |
| northwind | 13 | 11/13 → 11/13 | 10/13 → 10/13 | 0 → 0 |
| chinook | 11 | 11/11 → 11/11 | 9/11 → 9/11 | 0 → 0 |
| tpch | 8 | 8/8 → 8/8 | 8/8 → 8/8 | 2 → 2 |
| adventureworks | 71 | 47/71 → 47/71 | 62/90 → 62/90 | 17 → 17 |
| sakila | 16 | 15/16 → 15/16 | 22/22 → 22/22 | 1 → 1 |
| wideworldimporters | 33 | 29/31 → 30/31 | 53/98 → 65/98 | 0 → 0 |
| wideworldimportersdw | 14 | 8/13 → 8/13 | 26/29 → 26/29 | 4 → 0 |
| nordic_sv | 6 | 1/6 → 6/6 | 2/6 → 6/6 | 2 → 0 |
| nordic_de | 5 | 5/5 → 5/5 | 4/5 → 4/5 | 0 → 0 |
| dw_names | 4 | 0/4 → 4/4 | 0/3 → 3/3 | 0 → 0 |
| app_names | 7 | 4/7 → 7/7 | 1/8 → 6/8 | 0 → 0 |

What each change does (all in `fabric_backend/infer.py`, each with a test in `tests/test_infer_rules.py`):

| Change | Rule | What it fixed |
| --- | --- | --- |
| **The synonym table** `SYNONYMS`: a word as it appears in a name → the English singular the rest of the names use. Abbreviations (`cust`, `prod`, `ord`, `emp`, `inv`, `acct`, `addr`, `cat`, `dept`, `supp`, `vend`, `whs`, `mgr`, …), Swedish (`kund`/`kunder`, `artikel`/`artiklar`, `ordrar`, `faktura`/`fakturor`, `leverantör`/`leverantörer`, `avdelning`, `lager`, …) and German (`kunde`/`kunden`, `bestellung`/`bestellungen`, `rechnung`, `lieferant`, `mitarbeiter`, `abteilung`, …) business words, singular and plural. Used only when the literal name finds nothing; every such match is listed under `plan.synonyms` and on the relationship's `note` ("through the synonym table: kund -> customer"), and the summary counts them | K2, R4 | `KundNr` keys `Kunder`, `Kunde_ID` in `Bestellungen` points at `Kunden`, `CustId` → `tbl_customers`, `CatId` → `categories`; nordic_sv 1 → 6 keys and 2 → 6 relationships, app_names 4 → 7 keys and 1 → 6 relationships |
| Transliteration before matching (`å ä ö ü ß é ø æ` → `a a o u ss e o ae`) | all | `LeverantörID` and `Leverantörer` compare as the same word |
| Irregular English plurals (`people` → `person`, `children`, `men`, `women`, `indices`, `criteria`, …) | K2, R1 | WideWorldImporters: `People.PersonID` becomes the key, and the twelve `…PersonID` columns (`ContactPersonID`, `SalespersonPersonID`, `PrimaryContactPersonID`, …) point at `People`: 53 → 65 relationships |
| A leading kind word is not part of the table's name: `dim_`, `fact_`, `tbl_`, `stg_`, `vw_`, `ref_`, `lkp_` | K2, R1, R4 | `dim_customer` is keyed by `customer_sk` and `fact_sales.customer_sk` points at it; `tbl_orders` answers to `order` |
| `_sk` and `_bk` as key suffixes next to `_id`, `_key`, `_code`, `_nr`, `_no` | K2, R1 | dw_names 0 → 4 keys, 0 → 3 relationships |
| Swedish and German line words (`rad`, `radnr`, `zeile`, `zeilennr`, `posnr`) | K5 | `Orderrader` gets `OrderNr + Radnr` |
| Suffix tie-break: when two tables answer to a name, the one whose key carries the column's suffix wins | R1, R4 | `customer_sk` next to both `dim_customer` (`customer_sk`) and `customers` (`customer_id`) is no longer ambiguous |
| The weakest rule never crosses suffixes: a `…ID` column does not point at a table keyed by `… Key` | R4 | WideWorldImportersDW: `WWI Purchase Order ID` and `WWI Stock Item Transaction ID` (source-system ids) no longer point at the `Order` and `Transaction` fact tables: 4 → 0 wrong |
| Abbreviated keys are not taken when the stem is another table's name through the synonym table | K2 | `Orderrader` is not keyed by `OrderNr` because `order` names `Ordrar` |
| An abbreviation that the synonym table resolves but that is also a prefix of another table stays ambiguous | R4 | `prod_id` with both `products` and `producers` is reported, not guessed |

## What was added earlier (25 October)

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

## What is still missed, and why

- **Columns that name a role but not the table** (`Orders.ShipVia`, `Employees.ReportsTo`, `Customer.SupportRepId`,
  `Document.Owner`, `BillOfMaterials.ComponentID`, WideWorldImporters' thirty `LastEditedBy` columns and
  `Picker Key` / `Salesperson Key` in the warehouse, `VorgesetzterID`, `ManagerId`, `AcctMgrId`): nothing in the name
  says which table. `confirmed=[...]` is the way to add them; `suggest_relationships` finds them from the data.
- **Self-references** (`Orders.BackorderOrderID → Orders`, `Customers.BillToCustomerID → Customers`,
  `employees.ManagerId → employees`): a table is never linked to itself by name; a self-join is a `confirmed` entry.
- **Subtype chains** (AdventureWorks `Person`, `Employee`, `SalesPerson`, `Vendor`, `Store` are all keyed by
  `BusinessEntityID`): no column is named after the table, so these tables get no key, and every `BusinessEntityID`
  column points at `BusinessEntity` rather than the nearest subtype the DDL declares. That accounts for 12 of the
  17 "wrong" AdventureWorks relationships; the join is still valid, the target is the root of the chain. Give
  `keys={"Person": ["BusinessEntityID"], ...}` to get the declared picture.
- **Composite keys with a partition column** (WideWorldImportersDW `Fact.Sale`: `Sale Key + Invoice Date Key`, and
  the four other fact tables): the surrogate alone is inferred and is unique on its own; counted as "wrong" here.
- **History tables** keyed by a reference plus a date (`ProductCostHistory`, `EmployeePayHistory`,
  `SalesTerritoryHistory`): not guessed; `plan_backend` suggests `reference + start_date` under `suggested_keys`
  where a start column exists, and `validate_plan` checks the suggestion for uniqueness.
- **Keys named after something else** (`CustomerDemographics.CustomerTypeID`, `SalesTerritory.TerritoryID`,
  `TransactionHistory.TransactionID`, `Document.DocumentNode`, `StockItemHoldings.StockItemID`): not inferred; a rule
  that strips words from table names would mis-key tables such as `order_items` (`item_id`) and was not added.
- **Composite primary keys that include a surrogate** (`SalesOrderDetail`: `SalesOrderID + SalesOrderDetailID`): the
  rules take the `<table>ID` column alone, which is unique on its own. Counted as "wrong" here.
- **A part of a compound word** (`StockItems.OuterPackageID` → `PackageTypes`): `package` is a prefix of
  `packagetype`, not a word of it; not matched.
- **`WorkOrderRouting`**: `WorkOrderID + OperationSequence` is inferred (K5); the declared key also has `ProductID`.
  Its inferred `ProductID + LocationID → ProductInventory` (R3) is a plausible but undeclared link.
- **TPC-H's two "wrong" relationships** (`L_PARTKEY → PART`, `L_SUPPKEY → SUPPLIER`) are foreign keys in the
  specification's table layouts but not in `dss.ri`; see the fixture README.
- **Sakila's one** (`film_text.film_id → film`) is a one-to-one extension table without a declared foreign key.

The synonym table is a list of assumptions, not knowledge of the schema: `land` means country in both Swedish and
German and is mapped so; a schema that uses `land` for something else gets a wrong suggestion, which the `note` on the
relationship and `plan.synonyms` make visible and `validate_plan` would count against the rows.

## Large schemas: time and answer size

Measured on 26 October 2026 on synthetic schemas with 300 and 1 000 tables (`tests/test_compact_outputs.py::synth`:
seven subject-area prefixes, twenty nouns, 5–15 columns per table, 30 % of them references), in this sandbox, unit test
only. The answer sizes are the JSON the tools return; "summary" is `detail="summary"`, which `detail="auto"` (the
default) picks above 60 tables.

| Tables | Relationships | `plan()` / `analyze()` time | `list_tables` full → summary | `plan_backend` full → summary | `analyze_schema` full → summary |
| --- | --- | --- | --- | --- | --- |
| 300 | 806 | 0.13 s / 0.5 s | 159 kB → 8 kB | 443 kB → 44 kB | 747 kB → 21 kB |
| 1 000 | 2 644 | 0.44 s / 4.6 s | 515 kB → 28 kB | 1 456 kB → 59 kB (relationships list cut, says so) | 2 889 kB → 43 kB |

What the summary form keeps: the summary line, one line per key (`order_id (K2)`) and per relationship
(`orders.customer_id -> customers [R1]`), ambiguous columns, keyless tables, suggested keys and synonym uses as single
lines; for `analyze_schema` the tables grouped by role, the ten most central tables, the areas by size with their first
tables, counts of cycles, multi-path pairs and active relationships, and the first thirty inactive ones with their
reason. What it drops: GraphQL field names, the Mermaid diagram, the per-table reasons and the full centrality maps.
Every answer is bounded at 60 000 characters: a full answer that is still too large first loses the diagram, then has
its lists cut to the same number of leading items with a `truncated` note that says to narrow with
`tables=["pattern*"]`. The `tables` filter takes names or fnmatch patterns, case-insensitive; the plan is still made
from the whole schema, so relationships into tables outside the filter are kept. The same switches exist on the local
stdio server.

The 4.6 s of `analyze()` on 1 000 tables is betweenness centrality (one shortest-path tree per table); acceptable under
a tool timeout, and `tables=` does not shorten it (the graph is analysed whole, then filtered).

## Rerunning

```
python -m pytest -q tests/test_inference_quality.py tests/test_infer_rules.py tests/test_compact_outputs.py
PYTHONPATH=. python tests/test_inference_quality.py       # the table above, plus the missed and wrong items per schema
```

These numbers are for the repository and this page only; the website does not quote them.
