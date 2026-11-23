# From SAP Tables to a Power BI Report in Fabric: Keys, Relationships and the Doubled-Total Trap

The SAP sales tables are in a Fabric lakehouse and someone wants a Power BI report on them. Three things go wrong on the way: the keys have more columns than a relationship can use, there are more links than a model can keep active, and the order value gets counted once per item.

**Quick answer:** a Power BI relationship uses one column on each side, and SAP keys have two or three (MANDT + VBELN, or MANDT + VBELN + POSNR). Direct Lake allows no calculated columns, so write a combined key column into the lakehouse tables and relate on it. Keep one active path between any two tables and decide which customer link is active. Sum VBAK.NETWR only on VBAK, in a measure, and never over the items.

## The data in this article

Every number below comes from Krusgraph's engine run on the SAP-shaped sample `sap_sd` on 16 November 2026, and is checked again by the site's tests on every change (`tests/test_d2_explainers.py`). The sample is synthetic: invented customers and materials in tables that have the structure of SAP sales tables. It is not SAP data and did not come from an SAP system. The semantic model below is a draft written by the engine; it was not opened in Power BI for this article.

The model uses eight tables: KNA1 (customers), MARA (materials), VBAK and VBAP (orders and their items), LIKP and LIPS (deliveries and their items), VBRK and VBRP (invoices and their items). How they connect is in the previous article, [how SAP sales tables connect in Fabric](https://krusgraph.com/blog/sap-sales-tables-in-fabric).

## Step 1: check the keys against the rows

A relationship in Power BI needs a one side that is unique. Before building anything, count it. On the sample, `validate_plan` reported "Keys: 12 of 12 hold. Links: 15 of 19 hold, 4 fail." Among the four relationships that do not hold: 3 order items (VBAP) whose order is missing from VBAK. In a report those items appear under a blank order, and their value is not in any order's total.

Power BI refuses a relationship whose one side has duplicates. If a key is not unique in your data, find out why first, for example an extract that has kept old versions of a row.

## Step 2: one column per side, so combine the key

VBAP's key is MANDT + VBELN + POSNR, and it points at VBAK with MANDT + VBELN. A relationship in a semantic model takes exactly one column on each side. In Import mode you could add a calculated column; Direct Lake allows none, so the combined column has to exist in the Delta table itself.

For the eight tables, Krusgraph's semantic model draft needs 22 combined key columns: one for each table's own key and one for each link out of it. VBAP, for example, gets three:

| Table | Column | Combines | For |
|---|---|---|---|
| VBAP | MANDT_VBELN_POSNR_key | MANDT + VBELN + POSNR | the key of VBAP |
| VBAP | MANDT_VBELN_key | MANDT + VBELN | VBAP to VBAK |
| VBAP | MANDT_MATNR_key | MANDT + MATNR | VBAP to MARA |

Each combined column is the parts as text with a separator character between them, and empty (NULL) when any part is NULL, the same way on both sides. Two rows then relate exactly when every part matches. In the draft, the silver step writes these columns into new silver tables (`silver_notebook_draft`, or `create_silver_notebook` in Fabric), and the semantic model reads the silver tables. The source tables are not changed.

Keep MANDT in the combined key even when the data has one client. A model built without it relates documents across clients the day a second client arrives.

## Step 3: one active path between two tables

Among the eight tables, the plan has 14 relationships. A Power BI model can keep only one active path between any two tables, or a filter would have two ways to travel. The draft keeps 7 active and makes 7 inactive, each with its reason, for example "it would close a cycle with VBAP - VBRP - MARA".

The customer table shows why this is a decision and not a detail. KNA1 is reached by five links: VBAK.KUNNR (the order's sold-to party), LIKP.KUNNR and LIKP.KUNAG (the delivery's ship-to and sold-to party), VBRK.KUNAG and VBRK.KUNRG (the invoice's sold-to party and payer). Only one of them can be active. The draft picks one by its rules and lists the others under "Decisions to check". For revenue per sold-to customer on orders, make VBAK.KUNNR the active one and deactivate the link the draft chose instead. Reach the others with `USERELATIONSHIP` in a measure.

The same applies to dates. The draft adds a Calendar table, marked as a date table, related to the ERDAT column of each of the six document tables: VBAK.ERDAT is active, the other five are inactive.

## Step 4: the doubled total

VBAK.NETWR is the net value of the whole order. VBAP.NETWR is the value of one item. In a flat table or a view that joins orders to items, each order's NETWR repeats on every item row. Summed there, the order value of the sample becomes 20,286,871.77. The real total is 6,125,324.89, the same whether you sum VBAK.NETWR on VBAK or VBAP.NETWR on the items.

A view like this one is easy to write and wrong:

```sql
CREATE VIEW sap_sd.gold_revenue_by_customer_wrong AS
SELECT k.KUNNR, SUM(k.NETWR) AS order_value
FROM sap_sd.VBAK k
JOIN sap_sd.VBAP p ON p.MANDT = k.MANDT AND p.VBELN = k.VBELN
GROUP BY k.KUNNR
```

The right one's query differs in one letter: `SUM(p.NETWR)` instead of `SUM(k.NETWR)`. `validate_plan` with `sql_sums=true` reads the view definitions of a schema, without reading rows. On the sample it flagged the first view and not the second.

In the semantic model, the draft handles it in two ways:

- The header amounts are not summed by default (`summarizeBy: none`): VBAK.NETWR, VBRK.NETWR and VBRK.MWSBK, and VBAP.NETWR, which is a header amount again relative to the delivery and invoice items.
- Each gets an explicit measure on its own table, such as `Total NETWR = SUM('VBAK'[NETWR])`, which sums once per order.

Keep the model's tables at their own level, one row per order and one row per item, and do not load a joined view such as the one above into the model.

Two more traps sit beside it. NETWR is in the document's currency (WAERK), so add values across documents only after converting them; the sample has one currency, EUR. And billing documents include credit memos and cancellations, which a revenue measure has to filter by billing type.

## Step 5: build it in Fabric

With the Krusgraph connector, the same plan leads to the items in your workspace, each with a dry run first and created only when you confirm: `create_silver_notebook` writes the silver tables with the combined key columns, `create_semantic_model` the model on them, and `create_report` a report on the model. These three were tried live on the synthetic shop schema in a Fabric workspace, not on SAP tables. The drafts (`semantic_model_draft`, `silver_notebook_draft`) create nothing and give you the TMDL and the notebook to review first.

## Check your own tables first

The free [check on krusgraph.com](https://krusgraph.com/check?example=sap_sd) runs the sample in your browser and shows the doubled total as "VBAK.NETWR would be summed once per VBAP row", with the three orphan items. Drop your own CSV or Excel exports, or paste a list of columns, to see the same for your tables. The files are read in your browser and not uploaded, and it needs no account.

## FAQ

### Why can't I relate VBAK and VBAP directly in Power BI?

Their keys have several columns (MANDT + VBELN, and MANDT + VBELN + POSNR), and a relationship uses one column per side. In Direct Lake you cannot add a calculated column, so add a combined key column to both tables in the lakehouse and relate on it.

### Why is my SAP revenue too high in Power BI?

Most often the model or a view joins order headers to their items and sums the header's NETWR on every item row. On the synthetic sample in this article that gives 20,286,871.77 instead of 6,125,324.89. Load headers and items as separate tables and sum VBAK.NETWR only on VBAK.

### Which customer column should be active in an SAP sales model?

It depends on the question. VBAK.KUNNR is the sold-to party of the order, LIKP.KUNNR the ship-to party and VBRK.KUNRG the payer. Make the one your main report uses active, and use `USERELATIONSHIP` in measures for the others.
