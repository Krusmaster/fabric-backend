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

## Tokens per answer: the ten most used tools, before and after

Measured on 26 October 2026 with Fabric mocked and the shop rows in SQLite (`validate_plan`, `sample_rows` and
`suggest_relationships` count real rows there); bytes of the JSON answer. "Before" is the code of that morning (commit
ecaf209), "after" the compact answers of round C plus the trims of round E: `analyze_schema` without the constant
`weights` and the three per-table centrality maps (the ten most central tables keep their numbers, every role carries
its own), `plan_backend` without empty `note` fields and with `mermaid=false` on request, and `semantic_model_draft`,
`data_dictionary` and `dbt_schema` bounded at 60 000 characters with `tables` patterns for the rest.

| Tool | shop before → after | 300 tables before → after |
| --- | --- | --- |
| `list_tables` | 1 123 → 1 123 | 158 672 → 8 605 (summary) |
| `plan_backend` | 3 408 → 3 300 (2 100 with `mermaid=false`) | 443 000 → 44 585 (summary) |
| `validate_plan` | 3 344 → 3 344 | needs rows |
| `sample_rows` | 1 293 → 1 293 | needs rows |
| `analyze_schema` | 5 671 → 4 655 | 747 000 → 21 231 (summary) |
| `suggest_relationships` | 3 628 → 3 628 | 461 → 461 (no candidates without rows) |
| `join_path` | 1 348 → 1 348 | 10 832 → 10 832 |
| `semantic_model_draft` | 14 855 → 14 855 | 908 774 → 30 907 (table files left out, listed under `omitted`) |
| `data_dictionary` | 10 235 → 10 235 | 989 145 → 55 384 (cut on a line, says so) |
| `dbt_schema` | 4 290 → 4 290 | 436 916 → 56 180 (cut on a line, says so) |

What was not changed: the `note` texts that say what a tool has and has not done live (tests pin several of them, and
they are the only place an agent sees the verification status); the GraphQL field names in `plan_backend` (they are
what `create_backend` and `describe_backend` use); the Mermaid diagram by default on small schemas (the docs promise
it; `mermaid=false` and the summary form leave it out). The shop answers are already small; the gains are on large
schemas, where a 1 MB answer is not an answer.

## SAP tables: with and without the SAP pack (rounds n20–n24; measurement corrected in n24; unit test, synthetic schema)

The SAP pack ([SAP.md](SAP.md)) on a synthetic SAP schema generated in `tests/sap_support.py` from the pack itself:
the order-to-cash, procure-to-pay, finance, pricing, business-partner and accounting-document tables with their key columns and a few
ordinary columns each, no rows, no data from any SAP system. Three ways to plan it: the name rules alone
(`plan(..., packs=False)`, Krusgraph before the pack); the name rules with every key given by the caller (`keys=`), as
someone who knows SAP keys would pass them; and the pack.

| Schema | Planned by | Keys right | Pack relationships found | Implied (shortcut) | Listed by the pack | Wrong | Wrong share |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ecc, upper names, 53 tables | names | 0 of 53 | 0 of 89 | 0 | 0 | 0 | – |
| ecc, upper names, 53 tables | names+keys | 53 of 53 | 78 of 89 | 9 | 20 | 27 | 0.20 |
| ecc, upper names, 53 tables | pack (self-check) | 53 of 53 | 89 of 89 | 0 | 0 | 0 | 0.00 |
| ecc, prefix names, 53 tables | names | 0 of 53 | 0 of 89 | 0 | 0 | 0 | – |
| ecc, prefix names, 53 tables | names+keys | 53 of 53 | 78 of 89 | 9 | 20 | 27 | 0.20 |
| ecc, prefix names, 53 tables | pack (self-check) | 53 of 53 | 89 of 89 | 0 | 0 | 0 | 0.00 |
| s4hana, lower names, 47 tables | names | 0 of 47 | 0 of 75 | 0 | 0 | 0 | – |
| s4hana, lower names, 47 tables | names+keys | 47 of 47 | 59 of 75 | 4 | 12 | 14 | 0.16 |
| s4hana, lower names, 47 tables | pack (self-check) | 47 of 47 | 75 of 75 | 0 | 0 | 0 | 0.00 |

**The pack row is a self-check, not a precision figure.** The schema is generated from the pack and scored against
the pack, so it shows only that the engine applies the pack as written. Whether the pack is right about SAP is not
measured here; `validate_plan` against real rows is the only test of that, and none has been run.

**What the name rules get wrong, and what they do not.** A relationship the name rules find that the pack does not
apply is sorted into three kinds (round n24):

- *implied*: a shortcut the pack reaches through a longer path that starts with the same columns, such as
  `EKET.MANDT+EBELN` → `EKKO` where the pack has `EKET` → `EKPO` → `EKKO`. The join is right; it only skips a table.
- *listed by the pack*: partly right. The pack lists the link but does not apply it because it holds for some rows
  only (`VBPA.VBELN` → `LIKP` for the partner rows of deliveries), or the link is a shortcut whose last step is such
  a listed link (`VBAP` → `VBUK`, the status row of the same document). Never two conditional steps in a row.
- *wrong*: neither. In ECC 24 of the 27 are a document number read as another kind of document: `LIPS.VBELN` (a
  delivery) as an order or an invoice, `VBAP.VBELN` (an order) as a delivery, and `BSEG`/`BKPF.BELNR` (an accounting
  document) as a supplier invoice in `RBKP`/`RSEG`, or the reverse. The other 3 (`VBFA`/`VBPA` → `VBUK`/`VBUP`) hold
  for some rows through two conditions and are counted as wrong to stay on the safe side.

The first version of this measurement (rounds n20–n23) counted every relationship outside the pack as wrong (70 in
ECC). About 25 of those were real links the pack lacked: `BUKRS` → `T001`, `LIFNR`+`BUKRS` → `LFB1`, open items →
their `BSEG` line, `KNVV` → `TVTW`/`TSPA`. They are in the pack since round n24, and the measurement sorts the rest as
above. The wrong share is wrong ÷ everything the name rules found.

The pack finds the 11 links (ECC) the name rules miss with keys given: role names such as `VBRK.KUNRG` (payer) →
`KNA1.KUNNR`, `LIPS.VGBEL`+`VGPOS` → `VBAP`, `BSEG.HKONT` → `SKB1.SAKNR`, `CVI_CUST_LINK.CUSTOMER` → `KNA1.KUNNR`, `BUT050.PARTNER1`/`PARTNER2` → `BUT000`. Without keys the name rules find nothing:
no SAP table has an `id` or `<table>_id` column. `python tests/test_sap_inference.py` prints the table; the numbers are
asserted in that test. Schemas without SAP tables plan exactly as before (the golden tests are unchanged).

## Rerunning

```
python -m pytest -q tests/test_inference_quality.py tests/test_infer_rules.py tests/test_compact_outputs.py
PYTHONPATH=. python tests/test_inference_quality.py       # the table above, plus the missed and wrong items per schema
```

These numbers are for the repository and this page only; the website does not quote them.

## How the tools describe themselves (round n18, 28 October 2026)

Every parameter of the 36 hosted tools has a description in tools/list (`inputSchema.properties.*.description`),
defined once per shared parameter in `fabric_backend/tool_params.py`; `tests/test_tool_descriptions.py` fails on a
parameter without one and on an instructing phrase in a description. Size of the hosted tools/list: the tools array of
`server.mcp.list_tools()` as compact JSON (`separators=(",", ":")`, `ensure_ascii=False`), in characters; "tool
descriptions" is the sum of the `description` strings, "parameter schemas" the sum of each `inputSchema` as compact
JSON (with the parameter descriptions in it); the rest is names, titles, annotations and outputSchema. "Read-only" is
the 28 tools with `readOnlyHint: true`. Tokens are estimated as characters / 4, not counted by a tokenizer.

| | all 36: characters | ≈ tokens | tool descriptions | parameter schemas | read-only 28: characters |
| --- | ---: | ---: | ---: | ---: | ---: |
| before n18 (8a87132) | 59 384 | ≈ 14 800 | 19 739 | 24 499 | 43 946 |
| after n18 (cd4f7d9) | 93 278 | ≈ 23 300 | 15 197 | 63 048 | 67 165 |
| after n26 | 80 672 | ≈ 20 200 | 14 768 | 50 875 | 57 974 |

n18 made the tool descriptions shorter (−23 %), but the parameter descriptions (meaning, format, default and an
example) added more than that saved, so the whole listing grew by 57 %. Most of the growth was the shared parameters
repeated in each tool: `confirmed` and `keys` (18 read-only tools each) with their examples. Round n26 shortened those
shared descriptions and moved what holds for every tool (where a workspace, source or API name comes from, that
`confirmed` is not an approval flag and its optional fields, that `tables` never narrows the plan itself) to the
server's instructions, which are sent once. The read-only listing is 14 % smaller than after n18; the goal of 30 % was
not reached, because about half of what remains is schema structure (types, titles, `anyOf`, defaults, annotations,
outputSchema) that may not change, and cutting the rest further would remove meaning or the examples for `confirmed` and
`keys`. `tests/test_tool_descriptions.py` caps the read-only listing at 60 000 characters.

### Structured output, a possible change after the listing

Each tool's outputSchema is `{result: string}` with JSON text inside; the descriptions name the fields of that JSON
and the error shape `{error, kind, hint}`. Once the connector is listed, the tools could return structured content
with a real outputSchema per tool (and the error as its own shape), so a client can read fields without parsing text.
Not now: the catalog reviews the current format.
