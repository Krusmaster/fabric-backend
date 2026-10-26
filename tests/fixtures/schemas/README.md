# Schema fixtures for the inference benchmark

Seven openly available example databases whose official DDL declares primary and foreign keys. The benchmark
(`tests/test_inference_quality.py`) gives `plan()` the table and column names only, as a lakehouse SQL endpoint
would, and scores the inferred keys and relationships against the declared ones. The results are in
`docs/INFERENCE.md`.

Each JSON file holds, per table: its SQL schema, the columns with their declared types in order, the PRIMARY KEY
columns and the FOREIGN KEY constraints (columns, referenced table, referenced columns). Nothing was added or
corrected by hand: `extract.py` reads the DDL files below and writes the JSON. A FOREIGN KEY without a column
list (TPC-H) refers to the target's primary key, as SQL defines it. Schemas are flattened to table names
because `fabric_backend.schema.Schema` holds one schema at a time; table names are unique in every fixture.

| Fixture | Source file(s) | Repository and commit | Licence |
| --- | --- | --- | --- |
| `northwind.json` | `samples/databases/northwind-pubs/instnwnd.sql` | github.com/microsoft/sql-server-samples @ `348bbbc` | MIT (`license.txt`, Microsoft Corporation) |
| `chinook.json` | `ChinookDatabase/DataSources/Chinook_SqlServer.sql` | github.com/lerocha/chinook-database @ `7f67772` | MIT (`LICENSE.md`, Luis Rocha) |
| `tpch.json` | `dss.ddl` and `dss.ri` from the TPC-H dbgen kit, version 2.x | github.com/electrum/tpch-dbgen @ `32f1c1b` | TPC-H is a specification of the Transaction Processing Performance Council (TPC); the dbgen kit is distributed by the TPC under its end-user licence. Only the eight table definitions and the keys in `dss.ri` are reproduced here, as metadata. |
| `adventureworks.json` | `samples/databases/adventure-works/oltp-install-script/instawdb.sql` | github.com/microsoft/sql-server-samples @ `348bbbc` | MIT (`license.txt`, Microsoft Corporation) |
| `wideworldimporters.json` | `samples/databases/wide-world-importers/wwi-ssdt/wwi-ssdt/<schema>/Tables/*.sql` (the SSDT project: one CREATE TABLE with inline constraints per table), without the `*_Archive` tables (system-versioned history tables, no keys) and the `DataLoadSimulation` schema (load-simulation helpers, not the data model) | github.com/microsoft/sql-server-samples @ `348bbbc` | MIT (`license.txt`, Microsoft Corporation) |
| `wideworldimportersdw.json` | `samples/databases/wide-world-importers/wwi-dw-ssdt/wwi-dw-ssdt/Dimension/Tables/*.sql` and `Fact/Tables/*.sql` (the star schema; the `Integration` staging tables and `dbo.SampleVersion` are left out) | github.com/microsoft/sql-server-samples @ `348bbbc` | MIT (`license.txt`, Microsoft Corporation) |
| `sakila.json` | `sql-server-sakila-db/sql-server-sakila-schema.sql` | github.com/jOOQ/sakila @ `e089a5b` | BSD (the port's own header: "License: BSD, Copyright DB Software Laboratory"; repository `LICENSE`: BSD 2-Clause). Sakila was originally developed by Mike Hillyer of the MySQL AB documentation team and is published by MySQL under the New BSD licence. |

Four more fixtures are **synthetic, written by hand** for the naming rules and say so in their `synthetic` field; they
have no public source and their declared keys are simply the keys the names were written to express:
`nordic_sv.json` (Swedish: Kunder, Artiklar, Leverantörer, Ordrar, Orderrader, Fakturor), `nordic_de.json` (German:
Kunden, Abteilungen, Mitarbeiter, Bestellungen, Rechnungen), `dw_names.json` (dim_/fact_ prefixes, _sk and _bk suffixes,
a date_key role column) and `app_names.json` (tbl_ prefixes, PascalCase, CustId/EmpId/DeptId/ProdId/CatId/AcctMgrId,
two self-references).

## Notes on what the ground truth is

- **WideWorldImporters** is Microsoft's current sample; the OLTP SSDT project declares every primary and foreign key
  inline. 33 tables after leaving out the temporal history tables and the load-simulation schema; the `LastEditedBy`
  columns (foreign keys to `People`) are 30 of its 98 declared foreign keys. **WideWorldImportersDW** is its star
  schema: 14 Dimension and Fact tables; the fact tables have composite primary keys of the surrogate key plus the
  date partition column (`Sale Key, Invoice Date Key`), which the benchmark counts as "wrong" when the surrogate alone
  is inferred. Microsoft's Contoso retail warehouse sample has no DDL with keys (its script creates the tables with
  CTAS from blob storage), so it could not be used as ground truth; WideWorldImportersDW is the official star schema
  with declared keys.

- **AdventureWorks, not AdventureWorksLT.** Microsoft distributes AdventureWorksLT only as a `.bak` backup (the
  release page of sql-server-samples lists `AdventureWorksLT20xx.bak`; there is no install script and no bacpac),
  so there is no official text definition to take keys from. The full AdventureWorks OLTP install script is the
  official DDL that exists; its 71 tables in the schemas `Person`, `HumanResources`, `Production`, `Purchasing`,
  `Sales` and `dbo` are a superset of the LT tables' content. Nothing was derived or hand-written for LT.
- **TPC-H:** `dss.ri` declares one foreign key per column pair except on LINEITEM, where it declares
  `L_ORDERKEY → ORDERS` and the compound `(L_PARTKEY, L_SUPPKEY) → PARTSUPP` only. The TPC-H specification's
  table layouts (clause 1.4) additionally describe `L_PARTKEY` and `L_SUPPKEY` as foreign keys to PART and
  SUPPLIER. The fixture follows `dss.ri`, the file we have; the two single-column links therefore count as
  "wrong" in the benchmark although the specification names them. `dss.ri` qualifies tables as `TPCD.…`; the
  fixture keeps the bare table names from `dss.ddl`.
- **Northwind:** the script creates the 8 classic tables inline and adds `CustomerCustomerDemo`,
  `CustomerDemographics`, `Region`, `Territories` and `EmployeeTerritories` with `ALTER TABLE … ADD CONSTRAINT`;
  both forms are read. `Order Details` keeps its space.
- **Chinook:** the SQL Server script with explicit (non-identity) keys. Types are as declared (`NVARCHAR`,
  `NUMERIC`, `DATETIME`, `INT`).
- **Sakila:** the SQL Server port. `film_text` has a primary key (`film_id`) but no declared foreign key to
  `film`; the benchmark counts an inferred `film_text.film_id → film` as "wrong" for that reason.
- Types are kept as the DDL spells them (lower-cased, without lengths). Computed columns carry the type
  `computed`; AdventureWorks' alias types (`Name`, `Flag`, `Phone`, …) are kept as such.

## Rebuilding

```
git clone --depth 1 --filter=blob:none --sparse https://github.com/microsoft/sql-server-samples
(cd sql-server-samples && git sparse-checkout set samples/databases/northwind-pubs samples/databases/adventure-works)
git clone --depth 1 https://github.com/lerocha/chinook-database
git clone --depth 1 https://github.com/electrum/tpch-dbgen
git clone --depth 1 https://github.com/jOOQ/sakila
python tests/fixtures/schemas/extract.py northwind sql-server-samples/samples/databases/northwind-pubs/instnwnd.sql > tests/fixtures/schemas/northwind.json
python tests/fixtures/schemas/extract.py chinook chinook-database/ChinookDatabase/DataSources/Chinook_SqlServer.sql > tests/fixtures/schemas/chinook.json
python tests/fixtures/schemas/extract.py tpch tpch-dbgen/dss.ddl tpch-dbgen/dss.ri > tests/fixtures/schemas/tpch.json
python tests/fixtures/schemas/extract.py adventureworks sql-server-samples/samples/databases/adventure-works/oltp-install-script/instawdb.sql > tests/fixtures/schemas/adventureworks.json
python tests/fixtures/schemas/extract.py sakila sakila/sql-server-sakila-db/sql-server-sakila-schema.sql > tests/fixtures/schemas/sakila.json
(cd sql-server-samples && git sparse-checkout add samples/databases/wide-world-importers)
W=sql-server-samples/samples/databases/wide-world-importers
python tests/fixtures/schemas/extract.py wideworldimporters $(ls $W/wwi-ssdt/wwi-ssdt/*/Tables/*.sql | grep -v _Archive | grep -v DataLoadSimulation) > tests/fixtures/schemas/wideworldimporters.json
python tests/fixtures/schemas/extract.py wideworldimportersdw "$W"/wwi-dw-ssdt/wwi-dw-ssdt/Dimension/Tables/*.sql "$W"/wwi-dw-ssdt/wwi-dw-ssdt/Fact/Tables/*.sql > tests/fixtures/schemas/wideworldimportersdw.json
```
(The DW table files have spaces in their names; quote them as above.)

The benchmark table: `PYTHONPATH=. python tests/test_inference_quality.py`.
