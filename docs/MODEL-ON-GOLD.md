# The semantic model on gold, grouped by data product (round DPM1)

Gustav, 21 November 2026, looking at the shop sample's data flow and data products in the site's demo chat: *"ska vi
inte använda dataprodukterna för den semantiska modellen?"* The flow card said the model `shop_model` "reads the source
tables in shop (bronze) directly, not the gold views built in this run", while the data products picture grouped the
same tables into `customers` and `products`. Now the model is built on gold and shaped by those data products.

## What the model reads

| The build has | The model reads | Said as |
| --- | --- | --- |
| gold views (the gold views output or the pipeline) and a semantic model | the gold views: one fact view per fact table and one dimension view per dimension table (a star schema) | `Built on gold: reads the gold views in schema gold (N fact view(s), M dimension view(s), a star schema), grouped into K data product(s): ...` |
| no gold views | the source tables (bronze), as before, or the silver tables when composite keys are combined (n226) | `Reads: the source tables of ..., schema ... (bronze, Direct Lake): no gold views in this build.` |

The line is the same in the dry run, the result and the data flow card (`workload_api.model_reads`,
`semantic_model.gold_model`). The data flow's last column is then titled **Built on gold**, with a line from each gold
view the model reads.

The dimension views come from `gold.spec(..., dimensions=True)`: one materialized lake view per dimension table with a
key, over its silver table, its own columns only (personal data left out as in the fact views, its key kept). A
composite key (SAP's MANDT + KUNNR) is related on the combined key column the silver step writes (`combined_keys.py`),
which the fact and dimension views then carry. The gold notebook adds them only when the build also has a semantic
model (`server.MODEL_ON_GOLD`, set by the Krusgraph Model's build); `gold_views_draft` on its own is unchanged.

## How the data products shape it

The grouping is `domains.data_products`, the one ED2 made the editor, the dry run and the site use.

- **One model, a perspective per data product.** The interface between two data products (the shop's
  `order_items.product_id -> products`) has to be a relationship, and a relationship holds only inside one model. One
  model per data product would lose it, or copy the other product's tables into each model. So it is one model, and each
  data product is a TMDL `perspective` with its tables, the tables its interfaces point at, and the calendar
  (`perspective` / `perspectiveTable` / `perspectiveColumn` / `perspectiveMeasure`; learn.microsoft.com,
  analysis-services/tmdl/tmdl-overview, ms.date 2023-12-27, read 22 November 2026). Each table carries the annotation
  `Krusgraph_DataProduct`, and each measure the display folder of its data product (`displayFolder`, same page). Tables
  themselves have no display folder in TMDL; the perspective is the table-level group.
- **Interfaces are relationships.** A relationship between tables of two data products carries the annotation
  `Krusgraph_Interface = <from product> -> <to product>`, and the summary lists it under `interfaces`.
- **Outside every data product, outside the model.** The shop's `audit_log` (no key: a contract cannot promise its rows
  are unique) is in no data product, so it is not in the model; `left_out` says so in one line. A table of a data product
  that is neither a fact nor a dimension with a key (SAP's VBAK header) has no gold view of its own; its columns are in
  the line views that join it, and `not_in_gold` says which.
- **Advanced analytics.** The model's annotation `Krusgraph_AdvancedAnalyticsFolder` names the display folder
  `Advanced analytics`, reserved for prediction tables (round AA1). TMDL has no empty display folder, so it appears once
  something is placed in it.

## Relationships

- From a fact view to a dimension view, over the column the view carries: its own reference, or the reference of a fact
  it joins (the shop's `order_items.orders_customer_id -> customers`). Between two dimension views as the plan links
  them (`products.category_id -> categories`).
- Never from one fact to another: the line view already carries the header's columns, and a header amount is left out
  of it (`header_amounts_left_out`), so the doubled header total stays protected. `fact_to_fact_left_out` says why.
- Only onto a key the row check counted unique, when it ran (the demo's checks, the editor's Check against the rows).
  A key it did not count, or found not unique, gets no relationship, and `not_related` says why. Without any row check
  the plan's keys are used and `keys_checked` is false.

## Before and after, shop sample

| | Before | After |
| --- | --- | --- |
| Reads | `shop.*` (bronze), 7 tables | `gold.*`: order_items, orders (facts); addresses, categories, customers, products (dimensions) |
| Groups | none | perspectives `customers` (addresses, customers, order_items, orders; with products through the interface) and `products` (categories, products) |
| Relationships | 6 over bronze, including order_items -> orders and audit_log -> customers | 5: order_items.product_id -> products (interface customers -> products), order_items.orders_customer_id -> customers, orders.customer_id -> customers, products.category_id -> categories, addresses.customer_id -> customers; plus the calendar |
| audit_log | in the model | out: in no data product |

## The silver boxes

A silver box says `key checked: N of N unique` when the row check ran and counted the key (the demo's checks, the
editor's Check against the rows: `workload_api.checked_keys` now carries its row and distinct counts), and `every row
kept: key ... not checked` only when it did not run.

Verified: unit tests (`tests/test_dpm1_model_on_gold.py`) on the shop sample, the SAP demo and the SAP full demo, on
22 November 2026. Not yet created in a Fabric workspace.

Round AA1 fills the display folder `Advanced analytics`: a prediction table in gold (customer segments, the weekly
orders forecast) joins the model when it exists, with one measure each ([ADVANCED-ANALYTICS.md](ADVANCED-ANALYTICS.md)).
