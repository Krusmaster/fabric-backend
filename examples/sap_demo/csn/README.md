# A CSN file for the SAP demo tables (synthetic)

`sap_demo_o2c.json` is a hand-written CSN file for four of the synthetic SAP demo tables that
[`../load_sap_demo_inline.py`](../load_sap_demo_inline.py) writes (`sap_kna1`, `sap_mara`, `sap_vbak`, `sap_vbap`). It was
not exported from an SAP system; SAP and CSN are named only as the format ([docs/SAP-CSN.md](../../../docs/SAP-CSN.md)).

It declares the keys (with `MANDT`), three associations (`VBAK._SoldTo` to `KNA1`, the composition `VBAK._Item` to
`VBAP`, read as items to header, and `VBAP._Material` to `MARA`) and the amounts `VBAK.NETWR` and `VBAP.NETWR` with
`@Semantics.amount.currencyCode`, plus the quantity `VBAP.KWMENG`.

Use it: in the lakehouse that holds the demo tables, open *Files*, create the folder `krusgraph/csn` and upload this file.
`plan_backend` and `validate_plan` then show a `csn` block, and the four tables' keys and the three links carry the rule
"CSN metadata" with `provenance: "declared by metadata (CSN)"`. `validate_plan` counts them in the rows like any other.

Locally (round LT1, 17 November 2026) against `fabric_backend.sap_demo.sqlite(schema="dbo")`: 4 entities matched by name
(the `sap_` prefix is dropped), 4 keys and 3 links applied, nothing in `not_applied`, `unmatched` or `ignored`;
`VBAK.NETWR` read as a header amount repeated by `sap_vbap`. It has not yet been read from a lakehouse.
