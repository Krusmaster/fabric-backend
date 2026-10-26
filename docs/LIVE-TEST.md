# Live test checklist

For the maintainer, after `bash deploy/krusgraph.sh --update`, against the demo workspace `demo`, the lakehouse
`demo_lh` and the schema `shop` (the synthetic data of `fabric_backend/seed.py`). The workspace id is not written here;
the protocol of a run stays outside the repository.

## Fixed after the 26 October run, unit-tested only

The 26 October run found these three; each is fixed and covered by unit tests, and none has run live since.

| What the run showed | Fixed in | Question in Claude | Expected now | Result | Date |
| --- | --- | --- | --- | --- | --- |
| `semantic_model_draft` summed `orders.ship_to_id` (`summarizeBy: sum` on an id) | 77c9cbc | *"Draft a semantic model for demo_lh, schema shop, and show me orders.tmdl."* | `ship_to_id` has `summarizeBy: none`; only `order_items.quantity` is summed | | |
| `suggest_relationships` gave all four candidates for `orders.ship_to_id` the same score | 7791941 | *"Which columns in demo_lh, schema shop, look like references but are in no relationship? Check the best ones against the data."* | `addresses.address_id` ranks first before the data check (about 3.94 against 1.5 or less) and holds for every value after it | | |
| `create_views` (dry run) proposed one view only | 961f8b6 | *"Which views would create_views make in demo_lh, schema shop? Dry run."* | `vw_order_items`, `vw_orders` and, once `orders.ship_to_id` is confirmed, `vw_orders_ship_to` | | |

## Before the next `create_backend shop_api`

`plan_drift` on `shop_api` showed that the API carries `orders.ship_to_id → addresses.address_id` and the plan does not
infer it. The next `create_backend` with the name `shop_api` must pass it, or the relationship is dropped (the tool then
stops with `kind: would_remove` and nothing is written):

```json
"confirmed": [{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}]
```

In Claude: *"Update shop_api from demo_lh, schema shop, and keep orders.ship_to_id → addresses.address_id."*
