# How SAP Sales Tables Connect in Fabric: VBAK, VBAP, KNA1, LIKP and VBRK

You have copied SAP sales tables into a Fabric lakehouse, and now you need to join them. The names are short, every table has a `VBELN`, and the obvious join on it can return the wrong rows or none at all.

**Quick answer:** an order is VBAK (header) with VBAP (items), keyed on MANDT + VBELN and MANDT + VBELN + POSNR. The customer is KNA1, reached from VBAK.KUNNR. A delivery (LIKP, LIPS) points back to the order item through LIPS.VGBEL and VGPOS, and an invoice (VBRK, VBRP) through VBRP.AUBEL and AUPOS. Join on the client MANDT too, never on VBELN alone between different documents, and sum each amount on its own table.

## The data in this article

Every number below comes from Krusgraph's engine run on the SAP-shaped sample `sap_sd` on 16 November 2026, and is checked again by the site's tests on every change (`tests/test_d2_explainers.py`). The sample is synthetic: invented customers and materials in tables that have the structure of SAP sales tables. It is not SAP data and did not come from an SAP system. The SQL was run in SQLite on that sample, not in a Fabric workspace. It is plain T-SQL, the dialect of a lakehouse's SQL analytics endpoint.

The sample has 300 orders (VBAK) with 844 items (VBAP), 292 deliveries (LIKP) and 292 invoices (VBRK), 120 customers (KNA1) and 150 materials (MARA). Three of the items belong to orders that do not exist, on purpose.

## The tables and their keys

Each of these tables starts its key with the client, MANDT. One database can hold several clients, so the key is never VBELN alone.

| Table | One row is | Key |
|---|---|---|
| VBAK | a sales document header (an order, and also quotations, contracts and returns) | MANDT + VBELN |
| VBAP | one item of a sales document | MANDT + VBELN + POSNR |
| KNA1 | a customer | MANDT + KUNNR |
| LIKP | a delivery header | MANDT + VBELN |
| LIPS | one item of a delivery | MANDT + VBELN + POSNR |
| VBRK | a billing document header (invoices, and also credit memos and cancellations) | MANDT + VBELN |
| VBRP | one item of a billing document | MANDT + VBELN + POSNR |
| MARA | a material | MANDT + MATNR |

The keys come from the SAP pack in Krusgraph's engine, which cites SAP's public documentation for each table. They were not verified against an SAP system. Counted against the sample's rows, all ten are unique.

## How the tables connect

There is no direct column from an order header to its delivery or invoice. The flow runs through the items:

| From | Columns | To | What it means |
|---|---|---|---|
| VBAP | MANDT, VBELN | VBAK | the item belongs to the order |
| VBAK | MANDT, KUNNR | KNA1 | the order's sold-to customer |
| VBAP | MANDT, MATNR | MARA | the material ordered |
| LIPS | MANDT, VBELN | LIKP | the delivery item belongs to the delivery |
| LIPS | MANDT, VGBEL, VGPOS | VBAP | the delivery item delivers this order item |
| LIKP | MANDT, KUNNR | KNA1 | the delivery's ship-to customer |
| VBRP | MANDT, VBELN | VBRK | the invoice item belongs to the invoice |
| VBRP | MANDT, AUBEL, AUPOS | VBAP | the invoice item bills this order item |
| VBRP | MANDT, VGBEL, VGPOS | LIPS | the invoice item bills this delivery item |
| VBRK | MANDT, KUNRG | KNA1 | the invoice's payer |

Krusgraph's plan on the sample has 16 relationships between the standard tables, all from the SAP pack: the ten above, plus LIKP.KUNAG and VBRK.KUNAG to KNA1 (the sold-to party on a delivery and an invoice), LIPS.MATNR, VBRP.MATNR to MARA, MAKT to MARA and VBRK.BUKRS to the company codes in T001.

"Revenue per customer" therefore needs a choice: VBAK.KUNNR is the sold-to party, LIKP.KUNNR the ship-to party and VBRK.KUNRG the payer. They can be different customers.

## From order to invoice in one query

Follow the items, and carry MANDT in every join:

```sql
SELECT COUNT(DISTINCT k.VBELN) AS orders,
       COUNT(DISTINCT d.VBELN) AS deliveries,
       COUNT(DISTINCT b.VBELN) AS invoices
FROM sap_sd.VBAK AS k
JOIN sap_sd.VBAP AS p ON p.MANDT = k.MANDT AND p.VBELN = k.VBELN
LEFT JOIN sap_sd.LIPS AS d ON d.MANDT = p.MANDT AND d.VGBEL = p.VBELN AND d.VGPOS = p.POSNR
LEFT JOIN sap_sd.VBRP AS b ON b.MANDT = p.MANDT AND b.AUBEL = p.VBELN AND b.AUPOS = p.POSNR;
```

On the sample it returns 300 orders, 292 deliveries and 292 invoices. The 8 orders without a delivery are the most recent ones, still open in the sample. Counting distinct document numbers is safe here; summing amounts over this join is not (see the last section).

## Trap 1: VBELN means a different document in each table

VBAK.VBELN is an order number, LIKP.VBELN a delivery number and VBRK.VBELN a billing document number. The column has the same name in all three, so a rule that matches names alone links them:

```sql
SELECT COUNT(*) AS matched_rows
FROM sap_sd.VBAK AS k
JOIN sap_sd.LIKP AS d ON d.MANDT = k.MANDT AND d.VBELN = k.VBELN;
```

On the sample it returns 0, because the orders and the deliveries use different number ranges. In a real system the ranges can overlap, and then the same join returns rows that pair unrelated documents, which is worse than none.

The sample shows it in a table the SAP pack does not know. `ZSD_ORDER_EXT` is an invented customer table (SAP reserves names that start with Z for its customers) with the order's MANDT and VBELN. With no pack entry for it, the engine's generic name rule (R3) proposed three links from it: to VBAK, LIKP and VBRK. The counts against the rows tell them apart. The link to VBAK has 1 row with no matching order, which is planted. The links to LIKP and VBRK have 301 such rows each: every row, so neither link is real. That is why the check counts rows before you trust a link proposed from a name.

## Trap 2: a join without MANDT

A key without its client pairs an order of one client with an item of another when a database holds more than one. The sample has one client, so leaving MANDT out changes no count here, and that is the danger: the join looks right in a test system and goes wrong in one with several clients. Krusgraph's SAP pack carries MANDT in every key and relationship. When an extract has dropped the column, the pack drops it on both sides and says so.

## Trap 3: the order value counted once per item

VBAK.NETWR is the net value of the whole order. VBAP.NETWR is the value of one item. Join the two and sum the header's column, and each order is counted once per item:

```sql
SELECT COUNT(*)                AS joined_rows,
       COUNT(DISTINCT k.VBELN) AS distinct_orders,
       SUM(k.NETWR)            AS header_netwr_summed_per_item,
       SUM(p.NETWR)            AS item_netwr
FROM sap_sd.VBAK AS k
JOIN sap_sd.VBAP AS p ON p.MANDT = k.MANDT AND p.VBELN = k.VBELN;
```

| Measure | Result on the sample |
|---|---|
| Joined rows | 841 |
| Distinct orders | 300 |
| Header NETWR summed over the join | 20,286,871.77 |
| Item NETWR summed over the join | 6,125,324.89 |
| VBAK.NETWR summed on VBAK alone | 6,125,324.89 |

The first sum is 3.3 times the real order value. One order shows the mechanism: order 0000010011 has a net value of 22,147.34 and 5 items, so it adds 110,736.70 to the joined sum. Sum each amount on its own table, or aggregate the items to one row per order before the join. The same holds one level down: VBAP.NETWR summed over a join with LIPS or VBRP counts an item once per delivery or invoice item. The next article, [from SAP tables to a Power BI report](https://krusgraph.com/blog/sap-tables-to-power-bi-report), shows what this means in a semantic model.

The 841 joined rows are the 844 items less the 3 whose order does not exist. An inner join drops them without a word:

```sql
SELECT COUNT(*) AS items_without_order
FROM sap_sd.VBAP AS p
LEFT JOIN sap_sd.VBAK AS k ON k.MANDT = p.MANDT AND k.VBELN = p.VBELN
WHERE k.VBELN IS NULL;
```

It returns 3. On the sample, `validate_plan` reported "Keys: 12 of 12 hold. Links: 15 of 19 hold, 4 fail." The 12 keys are the eight standard tables above plus T001 and MAKT, from the SAP pack, and one for each of the two Z tables, which the rows gave (rule K6). The four relationships that do not hold are the one with the 3 items and the three name-based links of `ZSD_ORDER_EXT` above.

## Check your own tables

The free [check on krusgraph.com](https://krusgraph.com/check?example=sap_sd) runs this sample in your browser: the map of the tables, the keys and links with the rule behind each, and the findings above. You can also drop your own CSV or Excel exports, or paste a list of columns. The files are read in your browser and not uploaded. It needs no account.

In a Fabric lakehouse, the Krusgraph connector does the same against your own tables, with your own permissions: `plan_backend` proposes the keys and relationships with their rules, `validate_plan` counts duplicate keys and rows with no match, and `sap_pack_draft` lists which SAP tables the pack recognises and which are missing. Nothing is created by these three. A person still decides what each link means, for example which customer counts as "the" customer.

## FAQ

### How do I join VBAK and VBAP in Fabric?

Join on both MANDT and VBELN: `VBAP.MANDT = VBAK.MANDT AND VBAP.VBELN = VBAK.VBELN`. VBAK has one row per order and VBAP one row per item, so the result has one row per item. Sum item amounts from VBAP, not VBAK.NETWR, over that join.

### How do I get from a sales order to its delivery and invoice?

Through the items. A delivery item points at the order item with LIPS.VGBEL and LIPS.VGPOS, and an invoice item with VBRP.AUBEL and VBRP.AUPOS, both together with MANDT. The headers LIKP and VBRK have no column that holds the order number.

### Why does my SAP order value triple in Power BI or SQL?

VBAK.NETWR is the value of the whole order, and a join with VBAP repeats it on every item row. On the synthetic sample in this article the header value summed over the join is 20,286,871.77 instead of 6,125,324.89. Sum VBAK.NETWR on VBAK alone, or sum VBAP.NETWR.
