# sap_demo36: a small CSV sample of the 36-month synthetic SAP demo

Synthetic, SAP-shaped, not SAP data: every name, address and e-mail address is made up (example.com). These files are
the rows of the first four customers (their master data, orders, deliveries, invoices, document flow and partners) of
`fabric_backend/sap_demo36.py` with seed 36, plus T001 and TVKO; `tests/test_ap2_sap_demo36.py` checks that they are
what the generator writes. The full data (about 130 000 rows in 17 tables) is never committed: the generator makes it
in a second, and the Fabric notebook writes it into a schema of its own (`docs/ANALYSIS-PLAN.md`, section 6).

    python -m fabric_backend.sap_demo36 --sample examples/sap_demo36     # write these files again
    python -m fabric_backend.sap_demo36 --ipynb sap_demo36.ipynb         # the notebook to import in Fabric
