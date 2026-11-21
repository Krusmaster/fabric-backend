-- dialect: spark
-- covers: JOIN ... USING (MANDT, VBELN, POSNR): the key pairs are implicit, no ON predicate exists
-- expected_joins: VBAP.MANDT = VBEP.MANDT | VBAP.VBELN = VBEP.VBELN | VBAP.POSNR = VBEP.POSNR
-- expected_lineage: MATNR <- VBAP.MATNR | EDATU <- VBEP.EDATU | WMENG <- VBEP.WMENG
SELECT VBELN, POSNR, p.MATNR, e.EDATU, e.WMENG
FROM sap_lh.sap.VBAP p
JOIN sap_lh.sap.VBEP e USING (MANDT, VBELN, POSNR)
