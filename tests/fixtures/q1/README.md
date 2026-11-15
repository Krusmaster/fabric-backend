# tests/fixtures/q1

`sales.qvs`: an invented shop written by hand as a Qlik load script for `fabric_backend/qlik/` (round Q1,
`docs/QLIK-MIGRATION-PRODUCT.md`). It was not exported from Qlik and holds no customer data and no real name.

It holds one of each thing the mapping decides: a plain association (Orders and Customers on CustomerID), a field
shared by four tables (StoreID), three synthetic keys (Orders and Shipments on OrderID and Status, where one field
carries the link; OrderLines and Returns on OrderID and LineNo, a composite key; Budget and StoreSales on StoreID and
Month, two facts sharing dimensions), a circular reference (Customers, Orders, Stores through Country), two mapping
tables used through ApplyMap (one with a default, one without), QUALIFY, a field name with a blank, a preceding load
over a SQL SELECT, a concatenation, a join with a resident table, a dropped table and one statement that is not read.
The rows behind it are written in `tests/test_q1_qlik.py`.
