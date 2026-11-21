> 2026-11-21, round BL5 (sprint item BL5, backlog C-37). Code: `fabric_backend/shop_faults.py`. Test:
> `tests/test_bl5_shop_faults.py`. Corpus case: `tests/corpus/shop_faults.json`. Synthetic data only.

# Planted faults: the shop with five known faults

Clean demo data only ever says "holds". This sample is the synthetic shop of `fabric_backend/seed.py` with five faults
put in on purpose, so a demo shows Krusgraph's checks finding what is wrong, and a data engineer can see that they find
exactly what was planted and nothing else. The same rows come out on every run, so the demo can be repeated.

## The five faults

| Id | Table | What was planted | What Krusgraph says |
| --- | --- | --- | --- |
| F1 | `customers` | `customer_id` 4 is on two rows (a second row for the same customer, as a double load gives). | Key not unique: "not unique: 1 duplicate rows (10 distinct values in 11 rows)". |
| F2 | `order_items` | Three order lines of orders 990 and 991, which are not in `orders`. | Link `order_items.order_id -> orders`: "3 of 137 rows (2.2%) point at nothing". |
| F3 | `orders` | `order_amount`, each order's total, on the header of `order_items`. | Amount level: "orders.order_amount is an amount on orders, and order_items has 2.23 rows for each row of orders on average and up to 3", so summing it over the lines counts each order two or three times. |
| F4 | `newsletter_signups` | `customer_id` holds numbers of an older system (1001 to 1008): right by name, no matching row. | Link `newsletter_signups.customer_id -> customers`: "8 of 8 rows (100.0%) point at nothing". |
| F5 | `orders` | `order_amount` is in SEK for the Swedish customers and in EUR for the rest; the `currency` column says which. | **Not detected today.** |

Four of five are found. F5 is honest about what the checks do not do yet: neither `validate_plan` nor the amount
check reads a currency column, so adding SEK and EUR in one sum is not flagged. Sprint item BL10 (measures that respect
currency, unit and sign) is where it belongs. The test asserts that F5 is not flagged, rather than being tuned to pass:
the day a check finds it, the test fails and this page and `FAULTS` are updated on purpose.

## What else the answer says, and why it is not a planted fault

- **One finding comes from the clean shop as well.** `products.list_price` is a price on the header of `order_items`,
  so summing it over the order lines repeats it. The clean shop gives the same finding; it is listed in
  `CLEAN_FINDINGS` and not counted as a fault.
- **F1 echoes on every link into `customers`.** The links from `addresses`, `orders`, `audit_log` and
  `newsletter_signups` add "but the target key of customers is not unique, so a row can match more than one". The
  links that hold still say "holds for all ... rows"; the note is F1's consequence, not a fault of its own.
- **F2 shows up in F3's count too.** The amount-level finding says that 3 `order_items` rows point at 2 values that
  are not in `orders`.

Nothing else is flagged: every other key is unique and every other link holds.

## How to run it

```
python -m pytest tests/test_bl5_shop_faults.py -q
python -c "from fabric_backend import shop_faults as s; r = s.check(); print(r['summary']); [print(f) for f in r['faults']]"
```

`shop_faults.check()` plans the eight tables by their names (as `validate_plan` does) and runs `validate_plan`'s
counting checks over the rows in an in-memory SQLite database: one query per key and per link, and the amount levels.
Read-only, no network, no Fabric. The test also runs the local `validate_plan` tool itself over the same rows and
asserts the same findings.

The expected answer, in short:

```
5 of 6 keys unique, 5 of 7 relationships hold without orphans
F1 found  F2 found  F3 found  F4 found  F5 not detected
```

## The corpus case

`tests/corpus/shop_faults.json` has the shape of the other cases in `tests/corpus/`: the plan by names, by names and
rows, and with the row profile, each scored against the truth the generator writes, plus what the rows say about the
plan and the five planted faults. The scores are unaffected by the faults (no wrong key, no wrong link; with the
profile 7 of 7 keys and 8 of 8 links), because the faults are in the rows, not in the names. The clean shop's case
(`tests/corpus/shop.json`) is unchanged. Regenerate the file with `python tests/test_bl5_shop_faults.py --write` and
read the diff.

The case is not yet in the published score table (`docs/SCORES.md`): that needs `tests/f2_corpus.py`,
`tests/test_f2_corpus.py` and the table itself, which this round did not touch.
