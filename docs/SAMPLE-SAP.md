# The SAP-shaped sample ('sap_sd' and 'sap_mm')

**Synthetic, SAP-shaped, not SAP data.** Two small sets of tables with the structure of SAP ERP and SAP S/4HANA sales
and purchasing tables, for demos, [/check](https://krusgraph.com/check) and films (round n202). No row comes from an SAP
system, an SAP customer or SAP's own demo data. SAP and S/4HANA are named here only as the source of the structure.
Krusgraph is not made, tested or endorsed by SAP.

- `sap_sd`, order to invoice: customers, materials, sales orders, deliveries, invoices, and two customer-specific (Z) tables.
- `sap_mm`, purchase to pay: suppliers, materials, purchase orders, the purchase order history, and one Z table.

The rows are generated from a seed by `fabric_backend/sap_sample.py` (the same seed gives the same rows on every machine),
a few hundred rows per table, 6 964 rows in all (`sap_sd` 4 327, `sap_mm` 2 637), two years of dates from 1 November
2024 to 31 October 2026, one client (`MANDT` 100). Customer, supplier and material names are invented
("Example Customer 0007", "Example Supplier 0012"); document numbers are text with leading zeros, as SAP stores them.

## Load it

- **In Fabric**: in a notebook attached to a lakehouse with *Lakehouse schemas* turned on,
  `%pip install git+https://github.com/Krusmaster/fabric-backend` and then
  `from fabric_backend.seed import seed; seed(spark, schema="shop", sap=True)`. It writes the shop as before and the two
  samples to the schemas `sap_sd` and `sap_mm` (existing tables of those names are replaced). It is off by default.
  On a lakehouse without schemas the samples are not written, with a printed note.
- **In the browser**: [/check](https://krusgraph.com/check) offers "SAP-shaped sample (synthetic)", order to invoice and
  purchase to pay, next to the shop and the manufacturing sample. Nothing is uploaded.
- **In Python**: `fabric_backend.sap_sample.source("sap_sd")` is the sample in SQLite; `python -m fabric_backend.sap_sample`
  prints what the engine finds on both, as JSON.

## The tables, and where each name comes from

Every standard table and every column of a standard table is a name the repository's SAP pack already has
(`fabric_backend/packs/sap/`, which cites SAP's public documentation for each table; [SAP.md](SAP.md)). A column the pack
does not name is not added, which has two visible consequences:

- `MAKT` has only its key (`MANDT`, `MATNR`, `SPRAS`): the pack names no text column. It keeps one row per material
  and language (E and D), so a join that does not filter `SPRAS` doubles the rows, the pack's "texts" trap.
- There is **no material document table** in the S/4HANA form (`MATDOC`), nor `MKPF`/`MSEG`: the pack does not describe
  them ([SAP.md](SAP.md) lists them as not built). The goods receipts are rows of the purchase order history `EKBE` with
  `VGABE` '1', which the pack has.

No customer field (`ZZ_`) is appended to a standard table: the pack has no rule for appends, so the standard tables carry
the pack's columns only. The test `tests/test_sap_sample.py` fails when a standard table carries a column outside the
pack (`sap_sample.pack_columns`).


#### `sap_sd`

| Table | Rows | What it holds | Columns | Source of the name (via the SAP pack) |
| --- | --- | --- | --- | --- |
| `T001` | 2 | Company codes | MANDT, BUKRS, KTOPL, WAERS | SAP Help Portal, `sap_help_sd` (SAP ERP and SAP S/4HANA product documentation, Sales and Distribution (sales, shipping and billing documents)) |
| `KNA1` | 120 | Customer master, general data | MANDT, KUNNR, NAME1, STRAS, PSTLZ, ORT01, ERDAT | SAP Help Portal, `sap_help_sd` (SAP ERP and SAP S/4HANA product documentation, Sales and Distribution (sales, shipping and billing documents)) |
| `MARA` | 150 | Material master, general data | MANDT, MATNR, ERSDA, LAEDA | SAP Help Portal, `sap_help_sd` (SAP ERP and SAP S/4HANA product documentation, Sales and Distribution (sales, shipping and billing documents)) |
| `MAKT` | 300 | Material descriptions | MANDT, MATNR, SPRAS | SAP Help Portal, `sap_help_sd` (SAP ERP and SAP S/4HANA product documentation, Sales and Distribution (sales, shipping and billing documents)) |
| `VBAK` | 300 | Sales document, header | MANDT, VBELN, AUART, ERDAT, KUNNR, NETWR, WAERK | SAP Help Portal, `sap_help_sd` (SAP ERP and SAP S/4HANA product documentation, Sales and Distribution (sales, shipping and billing documents)) |
| `VBAP` | 844 | Sales document, items | MANDT, VBELN, POSNR, MATNR, KWMENG, VRKME, NETWR, WAERK, ERDAT | SAP Help Portal, `sap_help_sd` (SAP ERP and SAP S/4HANA product documentation, Sales and Distribution (sales, shipping and billing documents)) |
| `LIKP` | 292 | Delivery, header | MANDT, VBELN, KUNNR, KUNAG, ERDAT | SAP Help Portal, `sap_help_sd` (SAP ERP and SAP S/4HANA product documentation, Sales and Distribution (sales, shipping and billing documents)) |
| `LIPS` | 823 | Delivery, items | MANDT, VBELN, POSNR, MATNR, VGBEL, VGPOS, LFIMG, VRKME, ERDAT | SAP Help Portal, `sap_help_sd` (SAP ERP and SAP S/4HANA product documentation, Sales and Distribution (sales, shipping and billing documents)) |
| `VBRK` | 292 | Billing document, header | MANDT, VBELN, FKART, BUKRS, KUNAG, KUNRG, NETWR, MWSBK, WAERK, ERDAT | SAP Help Portal, `sap_help_sd` (SAP ERP and SAP S/4HANA product documentation, Sales and Distribution (sales, shipping and billing documents)) |
| `VBRP` | 823 | Billing document, items | MANDT, VBELN, POSNR, MATNR, AUBEL, AUPOS, VGBEL, VGPOS, FKIMG, VRKME, NETWR, ERDAT | SAP Help Portal, `sap_help_sd` (SAP ERP and SAP S/4HANA product documentation, Sales and Distribution (sales, shipping and billing documents)) |
| `ZSD_ORDER_EXT` | 301 | Customer extension of the sales order header: region and campaign (invented) | MANDT, VBELN, ZZ_REGION, ZZ_CAMPAIGN | none: invented for this sample, unknown to the pack |
| `ZSD_KAM_ASSIGN` | 80 | Key account manager and segment per customer, custom column names only (invented) | ZZ_KUNDE_NR, ZZ_KAM_NAME, ZZ_SEGMENT | none: invented for this sample, unknown to the pack |

#### `sap_mm`

| Table | Rows | What it holds | Columns | Source of the name (via the SAP pack) |
| --- | --- | --- | --- | --- |
| `T001` | 2 | Company codes | MANDT, BUKRS, KTOPL, WAERS | SAP Help Portal, `sap_help_sd` (SAP ERP and SAP S/4HANA product documentation, Sales and Distribution (sales, shipping and billing documents)) |
| `LFA1` | 40 | Supplier master, general data | MANDT, LIFNR, NAME1, STRAS, PSTLZ, ORT01, ERDAT | SAP Help Portal, `sap_help_mm` (SAP ERP and SAP S/4HANA product documentation, Materials Management (purchasing documents, purchase order history, logistics invoice verification)) |
| `MARA` | 150 | Material master, general data | MANDT, MATNR, ERSDA, LAEDA | SAP Help Portal, `sap_help_sd` (SAP ERP and SAP S/4HANA product documentation, Sales and Distribution (sales, shipping and billing documents)) |
| `MAKT` | 300 | Material descriptions | MANDT, MATNR, SPRAS | SAP Help Portal, `sap_help_sd` (SAP ERP and SAP S/4HANA product documentation, Sales and Distribution (sales, shipping and billing documents)) |
| `EKKO` | 260 | Purchasing document, header | MANDT, EBELN, BSART, BUKRS, LIFNR, WAERS, AEDAT | SAP Help Portal, `sap_help_mm` (SAP ERP and SAP S/4HANA product documentation, Materials Management (purchasing documents, purchase order history, logistics invoice verification)) |
| `EKPO` | 643 | Purchasing document, items | MANDT, EBELN, EBELP, MATNR, MENGE, MEINS, NETWR, LOEKZ, AEDAT | SAP Help Portal, `sap_help_mm` (SAP ERP and SAP S/4HANA product documentation, Materials Management (purchasing documents, purchase order history, logistics invoice verification)) |
| `EKBE` | 600 | Purchase order history | MANDT, EBELN, EBELP, ZEKKN, VGABE, GJAHR, BELNR, BUZEI, MENGE, WRBTR, WAERS, CPUDT | SAP Help Portal, `sap_help_mm` (SAP ERP and SAP S/4HANA product documentation, Materials Management (purchasing documents, purchase order history, logistics invoice verification)) |
| `ZMM_PO_CONF` | 642 | Supplier's confirmed delivery date per purchase order item (invented) | MANDT, EBELN, EBELP, ZZ_CONF_DATE, ZZ_CONF_BY | none: invented for this sample, unknown to the pack |

The pack's sources were cited from public knowledge of SAP's documentation and are marked not fetched in the pack itself
(help.sap.com could not be reached from the sessions that wrote it); see each entry in
`fabric_backend/packs/sap/manifest.yaml`.

### The customer-specific (Z) tables

SAP reserves table names that start with Z or Y for its customers' own tables, and ZZ for their own fields (a public
naming convention). The three Z tables here, their names and their fields are **invented** for this sample. The SAP pack
knows none of them: it covers standard tables only.

- `ZSD_ORDER_EXT` extends the sales order header. It carries the standard key fields `MANDT` and `VBELN` and two invented
  fields, `ZZ_REGION` and `ZZ_CAMPAIGN`. One row points at an order that does not exist (planted).
- `ZSD_KAM_ASSIGN` has only custom names. `ZZ_KUNDE_NR` holds `KNA1` customer numbers, but nothing in its name says so.
- `ZMM_PO_CONF` holds the supplier's confirmed delivery date per purchase order item (`MANDT`, `EBELN`, `EBELP`,
  `ZZ_CONF_DATE`, `ZZ_CONF_BY`).

## What is planted, and what Krusgraph finds

Each item is listed in `tests/fixtures/sap_sample/planted.json`, with the engine's answer; the tests assert both exactly.

### Keys with the client `MANDT`

Every standard table gets its key from the SAP pack (rule `SAP pack`), each starting with `MANDT`: `VBAK` `MANDT` +
`VBELN`, `VBAP` `MANDT` + `VBELN` + `POSNR`, `EKPO` `MANDT` + `EBELN` + `EBELP`, `MAKT` `MANDT` + `MATNR` + `SPRAS`,
`EKBE` its eight-column key. The health check counts them:

- `sap_sd`: "10 of 10 keys unique, 15 of 19 relationships hold without orphans";
- `sap_mm`: "7 of 7 keys unique, 7 of 8 relationships hold without orphans".

### Header to item, and the document flow

From the pack (rule `SAP pack`): `VBAP` → `VBAK`, `LIPS` → `LIKP`, `VBRP` → `VBRK`, `EKPO` → `EKKO`, `EKBE` → `EKPO`;
the document flow from the delivery item to the order item (`LIPS.VGBEL` + `VGPOS`), from the billing item to the order
item (`VBRP.AUBEL` + `AUPOS`) and to the delivery item (`VBRP.VGBEL` + `VGPOS`); and the links to `KNA1`, `LFA1`,
`MARA` and `T001`. `VBFA` is not in the sample.

### Orphan items

Three `VBAP` items of orders 0000019901 to 0000019903, which do not exist; one `EKPO` item of purchase order 4500099901,
which does not exist. /check: "VBAP.MANDT+VBELN → VBAK: 3 orphan(s)" and "EKPO.MANDT+EBELN → EKKO: 1 orphan(s)".

### The total that doubles

`VBAK.NETWR` is the net value of the whole order and the sum of its items' `VBAP.NETWR`. Summed over a join with `VBAP`,
each order counts once per item. `amount_levels` flags it ("VBAK.NETWR would be summed once per VBAP row"): over the
joined rows the sum is 20 286 871.77, against 6 125 324.89 once per order, 3.31 times too much. Its example is order
0000010011: 22 147.34 on the header, five items, so the join counts it as 110 736.70.

Two gold views show it. `sql_sums` (the view check) flags the first and not the second:

```sql
CREATE VIEW sap_sd.gold_revenue_by_customer_wrong AS
SELECT k.KUNNR, SUM(k.NETWR) AS order_value
FROM sap_sd.VBAK k
JOIN sap_sd.VBAP p ON p.MANDT = k.MANDT AND p.VBELN = k.VBELN
GROUP BY k.KUNNR
```

```sql
CREATE VIEW sap_sd.gold_revenue_by_customer AS
SELECT k.KUNNR, SUM(p.NETWR) AS order_value
FROM sap_sd.VBAK k
JOIN sap_sd.VBAP p ON p.MANDT = k.MANDT AND p.VBELN = k.VBELN
GROUP BY k.KUNNR
```

The same check also flags `VBAP.NETWR` over `LIPS` and `VBRP`, and `VBRK.NETWR` over `VBRP` (true: a header amount
repeats on its lines), and `EKPO.NETWR` over `EKBE` in `sap_mm`. It also flags `VBAK.NETWR` over `ZSD_ORDER_EXT` and
`EKPO.NETWR` over `ZMM_PO_CONF`: the Z tables have no key, so the engine cannot know they hold one row per order or item.

### Late goods receipts

Every eleventh received purchase order item is received after the date the supplier confirmed. The KPI compares the goods
receipt in `EKBE` with the Z table's `ZZ_CONF_DATE`:

```sql
SELECT COUNT(*) AS received_items,
       SUM(CASE WHEN b.CPUDT > c.ZZ_CONF_DATE THEN 1 ELSE 0 END) AS late_items
FROM sap_mm.EKBE b
JOIN sap_mm.ZMM_PO_CONF c ON c.MANDT = b.MANDT AND c.EBELN = b.EBELN AND c.EBELP = b.EBELP
WHERE b.VGABE = '1'
```

On the sample: 54 of 600 received items late, 91.0% on time.

## Z tables: what Krusgraph does with them (measured)

Run on the sample, by names and again with the rows:

| Z table | Key | Links found | Rule | The rows |
| --- | --- | --- | --- | --- |
| `ZSD_ORDER_EXT` | none (K3: no column is named like a key) | → `VBAK` on `MANDT` + `VBELN` | R3 (all of the target's key columns appear) | holds, with the 1 planted orphan |
| | | → `LIKP` on `MANDT` + `VBELN` | R3 | 301 of 301 rows orphaned: reject it in the review |
| | | → `VBRK` on `MANDT` + `VBELN` | R3 | 301 of 301 rows orphaned: reject it in the review |
| `ZSD_KAM_ASSIGN` | none (K3) | nothing: `ZZ_KUNDE_NR` → `KNA1` is **not found** | none | add it in the review |
| `ZMM_PO_CONF` | none (K3) | → `EKKO` on `MANDT` + `EBELN`, → `EKPO` on `MANDT` + `EBELN` + `EBELP` | R3 | both hold, 0 orphans |

- **Found by the name rules and confirmed by the rows**: a Z table that carries SAP's standard key fields is linked by
  the generic rule R3 to every table keyed by those fields. `ZMM_PO_CONF` → `EKKO` and `EKPO` hold with no orphan.
  `ZSD_ORDER_EXT` → `VBAK` holds (one planted orphan). R3 also proposes `ZSD_ORDER_EXT` → `LIKP` and → `VBRK`, because
  deliveries and invoices are keyed by `MANDT` + `VBELN` too; the rows reject both (no row matches), and the review is
  where you reject them.
- **Found only by the row check**: none. R5 (code and role columns checked against the rows) and
  `suggest_relationships` look only at targets with a single-column key, and every SAP key starts with `MANDT`. What the
  rows do add: /check suggests `VBELN` as the key of `ZSD_ORDER_EXT` and `ZZ_KUNDE_NR` as the key of `ZSD_KAM_ASSIGN`
  (each unique in the data); `ZMM_PO_CONF` is listed as a table without a key.
- **Not found**: `ZSD_KAM_ASSIGN.ZZ_KUNDE_NR` → `KNA1.KUNNR`. No name rule reads `ZZ_KUNDE_NR` as a customer number, and
  the row checks do not reach `KNA1`'s two-column key. You add it in the review (or pass it as `confirmed`).
- **No key by name**: none of the Z tables gets a key from the name rules. Give it in the review (`keys`), for example
  `MANDT` + `VBELN` for `ZSD_ORDER_EXT`.
- **The SAP pack** knows no Z table and adds nothing to them.

## Questions

**Does Krusgraph work on customised SAP tables (Z tables)?**
Yes, for keys and links that use SAP's standard field names, and the rows decide which of those links hold. A Z table
that carries `MANDT` and `VBELN` is linked by the general name rule R3 to every table keyed by those fields;
`validate_plan` then counts the rows. On our synthetic sample the link to the sales order header held (with one planted
orphan), and the links to the delivery and billing headers matched no row, so you reject them in the review. A Z table
gets no key from its name: you give it in the review, for example `MANDT` + `VBELN`. A link through a custom-named
column (`ZZ_KUNDE_NR` holding customer numbers) is shown only if the row check finds it, and on SAP tables it does not,
because every SAP key starts with `MANDT` and the row checks look at single-column keys: you add it in the review. The
SAP pack covers standard tables only. Tested on synthetic, SAP-shaped data, not on a real SAP system.

## Film scripts

Two films of about 20 seconds each, recorded on the sample. Every number below is the engine's answer on the sample
(`python -m fabric_backend.sap_sample`; `tests/test_sap_sample.py` checks this section against it). The first frame of
each film says: "Synthetic, SAP-shaped data. Not SAP data."

### (a) Order to invoice: the doubled total, found and fixed

| Time | Picture | Words |
| --- | --- | --- |
| 0–3 s | /check, "SAP-shaped sample (synthetic)", order to invoice | "Order to invoice, SAP-shaped, synthetic." |
| 3–8 s | The map: `VBAK` → `VBAP` → `LIPS` → `VBRP`, keys with `MANDT` | "Keys with MANDT and the document flow, each with its rule." |
| 8–14 s | The finding "VBAK.NETWR would be summed once per VBAP row" | "Summed over the items, order value is 20 286 871.77. Once per order it is 6 125 324.89: 3.31 times too much." |
| 14–20 s | The two gold views side by side, the wrong one flagged | "Order 0000010011: 22 147.34, counted five times. Sum the items' NETWR instead, and the flag is gone." |

### (b) Purchase to pay: MANDT, a Z table, and late deliveries

| Time | Picture | Words |
| --- | --- | --- |
| 0–4 s | /check, purchase to pay: `EKKO`, `EKPO`, `EKBE` with keys starting with `MANDT` | "Purchase to pay. Every key starts with the client, MANDT." |
| 4–10 s | `ZMM_PO_CONF` on the map, linked to `EKPO` by rule R3; health "7 of 7 keys unique, 7 of 8 relationships hold without orphans" | "A customer's own Z table, linked by its standard fields, and the rows confirm it: no orphans." |
| 10–20 s | The data agent asked "How many purchase order items arrived after the date the supplier confirmed?" | "54 of 600 received items were late: 91.0% on time." |

## Limits

- Synthetic and SAP-shaped: the structure follows the SAP pack, the values are invented. It shows what Krusgraph does on
  tables shaped like SAP's, not that it was run on a real SAP system.
- One client, one currency per document set, no `VBFA`, no pricing conditions, no material document table.
- The Z tables, their names and fields are invented examples of the customer namespace, not tables of any customer.
