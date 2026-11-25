# The samples of the change-by-chat demo ('shop_lfd' and 'sap_lfd')

*Written by round LFD1, 24 November 2026.*

**Synthetic, not customer data, not SAP data.** Two small samples for a demo that changes a plan in conversation and
shows the change as a diff. The demo itself is not part of this round; it will sit behind a setting that is off by
default. These samples are its data. They are built by `fabric_backend/lfd_demo.py` from the rows of two samples that
already exist, and add to them: the shop (`fabric_backend/seed.py`, the `sample` source) and the SAP demo
(`fabric_backend/sap_demo.py`). Neither of those, nor any golden answer in `tests/golden/`, changes.

- `lfd_demo.sqlite("shop_lfd")` and `lfd_demo.sqlite("sap_lfd")` give `(Schema, execute)` over the rows in SQLite, the
  way `sap_demo.sqlite()` does. `lfd_demo.shop_rows()` and `lfd_demo.sap_tables()` give the rows.
- `lfd_demo.EXPECTED` holds what the plan (as `plan_backend` makes it), the check (as `validate_plan` runs it) and the
  numbers below give on each sample. `tests/test_lfd1_samples.py` compares them byte for byte.
- `lfd_demo.numbers(sample, execute)` counts the numbers with read-only SQL (`SHOP_SQL`, `SAP_SQL`). Amounts are summed
  in cents, as whole numbers, so no float rounding enters; a value per customer is rounded half up.

Verified with unit tests in SQLite (`tests/test_lfd1_samples.py`), not against a Fabric workspace.

## shop_lfd

The shop of seed 42 (seven tables, ten customers) plus:

- `customers.is_test`, a boolean flag: false (0) on the ten shop customers, true (1) on two test customers.
- `addresses.region`: `North` for addresses in SE, NO and FI, `South` for DE. Both values occur among the addresses that
  orders ship to.
- Two test customers, `Test Customer Alpha` (SE) and `Test Customer Beta` (DE), with one address each (18 and 19) and
  three orders each (160 to 165). Every test order has two lines: one trail bike (899.00) and two bottles (2 × 12.00),
  923.00 per order, 5 538.00 for the six.

The order value is the engine's: the shop's order lines carry a quantity and no amount, so the value is quantity ×
`products.list_price` summed over `order_items` (`amounts.order_amount_measures`, the measure the semantic model gets).

| Number | Without test customers (`is_test` = 0) | With test customers |
| --- | --- | --- |
| Customers | 10 | 12 |
| Addresses | 17 | 19 |
| Orders | 60 | 66 |
| Order lines | 134 | 146 |
| Order value | 51 296.70 | 56 834.70 |
| Order value per customer | 51 296.70 / 10 = 5 129.67 | 56 834.70 / 12 = 4 736.23 (4 736.225, rounded half up) |

Without its test customers every number is the shop's own: `lfd_demo.sqlite("shop_lfd", include_test=False)` gives the
same plan and the same check as the `sample` source, byte for byte (a test compares them). Also on the shop without
test customers:

- `orders.ship_to_id → addresses.address_id` (rule R5): 60 of 60 orders find their address.
- The path the plan does not take, orders to addresses through the customer (`addresses.customer_id`) instead of
  `ship_to_id`: each order is repeated once per address of its customer, 103 rows instead of 60, and the order value
  over that join is 93 842.80 instead of 51 296.70.

The plan of `shop_lfd` is the shop's: 7 tables, 6 keys, the same 7 relationships (6 by R1, `ship_to_id` by R5). The
new columns add no key and no relationship. The check finds every key unique and no orphan.

## sap_lfd

The 17 order-to-cash tables of the SAP demo, with all their rows and planted traps, plus:

- **A second sales organization**: `2000` in `TVKO` (client 100, company code 1000), with one order, `0000000003`, one
  item, 200.00.
- **Three columns on `VBRK`**: `VBTYP`, `FKSTO` and `SFAKN`. The existing invoice `0090000001` gets `VBTYP` `M` and the
  other two empty.
- **A cancelled billing document** `0090000002` (`FKSTO` = `X`, 100.00) for item 10 of order `0000000002`, and **its
  cancellation** `0090000003` (`FKART` `S1`, `VBTYP` `N`, 100.00, `SFAKN` = `0090000002`), one item each, with their
  document flow in `VBFA` (order → invoice `M`, invoice → cancellation `N`).

**Not verified**: that `FKSTO`, `SFAKN` and `VBTYP` mean exactly this in a real SAP system (a cancelled document
flagged `X` in `FKSTO`, the cancelled document's number in the cancellation's `SFAKN`). The SAP pack's own note on
`VBRK` says only that cancellations and credit memos are billing documents too, and that `FKART` and the cancellation
flag decide whether to count them. The engine does not use these three columns: no rule reads them, and the plan has no
relationship from `SFAKN`.

| Number | sap_lfd |
| --- | --- |
| Orders (`VBAK` headers, both clients) | 4 (one in sales organization 2000) |
| Sales organizations in client 100 | 2 |
| Order value, `VBAK.NETWR` once per header | 950.00 |
| Order value, `VBAK.NETWR` summed over the joined `VBAP` items | 2 150.00 |
| Billing documents (`VBRK`) | 3 |
| Billed, `VBRK.NETWR` once per document | 600.00 |
| Billed, `VBRK.NETWR` summed over the joined `VBRP` items | 1 000.00 |
| Billing documents without the cancelled one and the cancellation | 1 |
| Billed without the cancelled document and the cancellation | 400.00 |

The two "once per header" and "summed over the items" pairs are what the engine's doubled-total check gives
(`amounts.before_after`); the numbers without cancellations are counted with `FKSTO` <> `X` and an empty `SFAKN`. Over
all three billing documents the cancelled document and its cancellation add 200.00, while their effect on the revenue
is meant to be nil: which documents to count is the question the demo asks, not one the engine answers.

The plan of `sap_lfd` is the SAP demo's: the pack recognises the same 17 tables with the same keys and 24
relationships. The check: 17 of 17 keys unique, 32 of 34 relationships hold without orphans; as on the SAP demo, only
the planted item of order `0000000009` (`VBAP → VBAK`) points at nothing, and `VBFA → VBAK` has no rows to check. A new
finding comes from the cancellation: item 10 of order `0000000002` now has two billing items (the cancelled invoice and
its cancellation), so `VBAP.NETWR` summed over `VBRP` gives 700.00 against 600.00 once per item.
