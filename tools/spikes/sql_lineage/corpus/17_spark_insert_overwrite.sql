-- dialect: spark
-- covers: INSERT OVERWRITE ... SELECT, item-level composite keys (MANDT, VBELN, POSNR) via reference columns AUBEL/AUPOS
-- expected_joins: VBRK.MANDT = VBRP.MANDT | VBRK.VBELN = VBRP.VBELN | VBAK.MANDT = VBRP.MANDT | VBAK.VBELN = VBRP.AUBEL | VBAP.MANDT = VBRP.MANDT | VBAP.VBELN = VBRP.AUBEL | VBAP.POSNR = VBRP.AUPOS
-- expected_lineage: invoice_no <- VBRP.VBELN | invoice_item <- VBRP.POSNR | order_no <- VBRP.AUBEL | sold_to <- VBAK.KUNNR | item_net <- VBRP.NETWR
INSERT OVERWRITE TABLE gold.invoice_items
SELECT r.VBELN AS invoice_no, r.POSNR AS invoice_item, r.AUBEL AS order_no, k.KUNNR AS sold_to, r.NETWR AS item_net
FROM sap_lh.sap.VBRP r
JOIN sap_lh.sap.VBRK h ON h.MANDT = r.MANDT AND h.VBELN = r.VBELN
LEFT JOIN sap_lh.sap.VBAK k ON k.MANDT = r.MANDT AND k.VBELN = r.AUBEL
LEFT JOIN sap_lh.sap.VBAP p ON p.MANDT = r.MANDT AND p.VBELN = r.AUBEL AND p.POSNR = r.AUPOS
