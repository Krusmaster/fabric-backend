> 2026-11-25, round LFD9. Code: `fabric_backend/change_demo.py` and `krusgraph demo change` in
> `fabric_backend/krusgraph_cli.py`. Test: `tests/test_lfd9_demo_e2e.py`. Synthetic data only.

# Change by chat: the demo script

A person has a data product in Fabric. They change it by typing a sentence in Claude. Krusgraph checks the change by
rules, shows what it would change and what the numbers become, and applies it only on a yes. No AI model runs inside
Krusgraph: the client's model writes a small JSON request, and Krusgraph answers it.

This script is for recording. Every answer and every number below comes from `krusgraph demo change`, which runs the
same code as the tools `propose_change` and `apply_change`, against an in-memory Fabric. It has not been recorded
against a real Fabric workspace yet. The live run is a checklist in [LIVE-TEST.md](../LIVE-TEST.md), section
"Change by chat (LFD) live run".

## Before you record

- The data: the synthetic sample `shop_lfd` ([SAMPLE-LFD.md](../SAMPLE-LFD.md)). A shop with 10 real customers and 2
  test customers.
- The server: `KRUSGRAPH_CHANGES=1`, and `KRUSGRAPH_MCP_APPS=1` for the card. Both are off by default.
- A dry rehearsal on your own machine, no Fabric needed:

```bash
krusgraph demo change --human          # scenario A on shop_lfd
krusgraph demo change --sap --human    # scenario B on sap_lfd
```

The rehearsal prints each step as the chat shows it. It takes about 5 seconds.

## Scenario A: the shop

### Step 1. Build first (about 1 minute on screen)

**You type:** *Build the data product for shop_lh: the pipeline and the semantic model. Dry run first.*

**Krusgraph answers:** two dry runs: the pipeline with its three notebooks, and the semantic model. Nothing is
written.

**You type:** *Yes, create them.*

**Krusgraph answers:** created. The workspace now has `silver_shop`, `gold_shop`, `pipeline_shop_check`,
`pipeline_shop` and `shop_model`.

Cut here if the first pipeline run is slow. Come back when it has finished.

### Step 2 (A2). Remove the test customers (about 2 minutes)

**You type:** *Remove the test customers.*

**Krusgraph asks:** *Which column marks the customers rows to remove?* One button: **is_test**.

**You tap:** is_test.

**Krusgraph asks:** *4 tables point at customers. Remove their rows too?* Two buttons: **Yes, from all 4** and
**No, keep their rows**.

**You tap:** Yes, from all 4.

**Krusgraph answers with the card:** *Removes rows from customers where is_test is true, and their rows in 4 tables.*

Open the folds one by one:

- **Plan:** Filter added: customers where is_test is true (and addresses, audit_log, order_items, orders).
- **Items:** `silver_shop`: 1 filter step on customers and its 4 dependents. Show the diff briefly.
- **Numbers:**

| Number | Before | After |
| --- | --- | --- |
| Customers | 12 | 10 |
| Addresses | 19 | 17 |
| Orders | 66 | 60 |
| Order lines | 146 | 134 |
| Order amount | 56 834.70 | 51 296.70 (−5 538.00) |

Say: "Every number is a count on the rows. The SQL is in the answer."

**You tap:** Yes.

**Krusgraph answers:** the silver notebook written, one pipeline run, one refresh. The definition reads back as
written. After the run, the silver tables hold 10 customers, 60 orders and 134 lines.

**Cut here while the pipeline runs.** In Fabric, `apply_change` waits 30 seconds for the run. If the run takes longer,
the answer says the numbers are not checked yet. Ask again later, or run `verify_build`.

### Step 3 (A3). Add region (about 2 minutes)

**You type:** *Add region from addresses to orders.*

**Krusgraph asks:** *Which column links orders to addresses?* One button: **orders.ship_to_id → addresses**.

This question comes when the plan has no link from orders to addresses. If Krusgraph counted the link already (rule
R5, which shop_lfd passes: 60 of 60 orders find their address), there is no question. Then skip to "Now add region".

**You tap:** the link.

**Krusgraph answers:** *Links orders.ship_to_id → addresses.* Plan: Link added. Items: the silver, check and gold
notebooks follow the new plan. Numbers: none, because a link changes no row.

**You tap:** Yes. Krusgraph writes the three notebooks and the model, runs once and refreshes.

**You type:** *Now add region.*

**Krusgraph answers:** *Adds region from addresses to orders.* Items: `gold_shop`, the orders view gets
`addresses_region`. Numbers: orders 60 rows before and after the join, region missing on 0 rows, 2 distinct values,
and the order amount 51 296.70 before and after the join. Say: "The join repeats no row. The total does not double."

**You tap:** Yes. Krusgraph writes the gold notebook, runs once and refreshes.

**Cut here while the pipeline runs.**

### Step 4 (A4). Add a measure (about 1 minute)

**You type:** *Add a measure: order value per customer.*

**Krusgraph answers:** *Adds the measure Order value per customer.* Items: `shop_model` only. Numbers: **5 129.67**
(4 736.23 on the source with the test customers still in). Pipeline run needed: no.

**You tap:** Yes. Krusgraph writes the semantic model and refreshes it. No pipeline run.

No cut needed here.

Do not open the Power BI report to show 5 129.67. The model that `create_semantic_model` builds reads the source tables,
not silver or gold, so a filter does not reach it: the report shows 12 customers and 4 736.23 per customer. The model's
README says so. Show the numbers in the card instead.

### Step 5 (A6). Undo (about 1 minute)

**You type:** *Undo removing the test customers.*

**Krusgraph answers:** *Takes out the filter on customers.* Plan: Filter taken out. Items: `silver_shop`, the filter
step taken out. Numbers: the numbers of the undone change. The undo takes each one back from after to before:
customers 10 → 12, orders 60 → 66, lines 134 → 146, order amount 51 296.70 → 56 834.70.

The card shows these numbers as the undone change had them (12 → 10). The answer's text says the undo reads them back;
the card does not. Say it out loud, so nobody reads the arrow the wrong way.

**You tap:** Yes. Krusgraph writes the silver notebook, runs once and refreshes. After the run the silver tables hold
12 customers, 66 orders and 146 lines again. Region and the measure stay.

**Cut here while the pipeline runs.**

## Timings

The times above are a plan for the video, about 7 minutes in all. They are not measured in Fabric. Four steps start a
pipeline run: A2, the link in A3, the column in A3, and the undo in A6. Cut at each run and come back when it has
finished. A4 needs no run.

## Scenario B: SAP billing documents

The variant for an SAP audience, on the synthetic sample `sap_lfd`. It is synthetic data, not SAP data. That `FKSTO`
and `SFAKN` mean exactly this in a real SAP system is not verified ([SAMPLE-LFD.md](../SAMPLE-LFD.md)).

**You type:** *Build the data product for sap_lh.* Then *Yes, create them.*

**You type:** *Leave out cancelled billing documents and their cancellations.*

**Krusgraph answers:** *Removes rows from sap_vbrk where the condition holds, and their rows in sap_vbrp.* Plan:
Filter added: sap_vbrk where (FKSTO equals 'X' or SFAKN is not empty) (and sap_vbrp).

| Number | Before | After |
| --- | --- | --- |
| Billing documents (`sap_vbrk`) | 3 | 1 |
| Billing items (`sap_vbrp`) | 4 | 2 |
| Billed (`sap_vbrk.NETWR`) | 600.00 | 400.00 (−200.00) |
| Orders (`sap_vbak`) | 4 | 4, untouched |
| Order value (`sap_vbak.NETWR`) | 950.00 | 950.00, untouched |

Say: "The cancelled document and its cancellation added 200.00 to billing. The orders do not change."

**You tap:** Yes. Krusgraph writes the silver notebook, runs once and refreshes. After the run silver holds 1 billing
document and 2 items.

## What this script does not show

- Nothing here has run against a Fabric workspace. The live checks are in [LIVE-TEST.md](../LIVE-TEST.md).
- The card's Yes button needs `apply_change` listed, so `KRUSGRAPH_CHANGES=1` on the server.
- `ok` means "allowed and unambiguous against this plan". It does not mean the change is a good idea.
- The Power BI report. The model reads the source tables, so the filters of A2 and B do not change its numbers. A model
  that reads gold is not written by `apply_change` yet.
