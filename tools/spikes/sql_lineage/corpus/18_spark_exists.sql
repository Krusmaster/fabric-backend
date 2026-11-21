-- dialect: spark
-- covers: a correlated EXISTS subquery (a semi-join written in WHERE) and an uncorrelated IN subquery
-- note: k.KUNNR IN (SELECT c.KUNNR ...) is a semi-join on KUNNR without MANDT; it is not an equality and is not expected
-- expected_joins: LIPS.MANDT = VBAK.MANDT | LIPS.VGBEL = VBAK.VBELN
-- expected_lineage: VBELN <- VBAK.VBELN | NETWR <- VBAK.NETWR
SELECT k.VBELN, k.NETWR
FROM sap_lh.sap.VBAK k
WHERE EXISTS (
    SELECT 1 FROM sap_lh.sap.LIPS i
    WHERE i.MANDT = k.MANDT AND i.VGBEL = k.VBELN
)
AND k.KUNNR IN (SELECT c.KUNNR FROM sap_lh.sap.KNA1 c WHERE c.LAND1 = 'DE')
