# tests/fixtures/w7

Two synthetic files for `fabric_backend/migration_read.py` (round W7, the proof in `docs/MIGRATION-DESIGN.md`).

- `shop.qvs`: the shop schema of `fabric_backend/seed.py` written as a Qlik load script by hand. It holds one
  synthetic key (Orders and Shipments share OrderID and CustomerID), one circular reference
  (Customers, Orders, ShipTo), a mapping table, a preceding load, a join, a concatenation, a section access part and
  two statements the reader does not read.
- `shop.twb`: the same schema written as a Tableau workbook by hand: a data source with two joins and an extract, a
  data source with a relationship and custom SQL, six calculated fields (two FIXED, one INCLUDE, one table
  calculation), and two worksheets, one with a filter outside context.

Neither file was exported from Qlik or saved by Tableau, and neither holds customer data or a real name. The server
name in the workbook is `example.invalid`. The layout of each file follows what the reader's docstring says was read
and what was not: most of it is Unverified against the vendors' documentation.
