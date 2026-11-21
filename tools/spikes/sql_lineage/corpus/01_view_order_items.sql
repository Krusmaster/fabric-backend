-- dialect: tsql
-- covers: CREATE VIEW, three-part names, table aliases, INNER JOIN with a composite ON (MANDT + VBELN)
-- expected_joins: VBAK.MANDT = VBAP.MANDT | VBAK.VBELN = VBAP.VBELN
-- expected_lineage: order_no <- VBAK.VBELN | sold_to <- VBAK.KUNNR | item_no <- VBAP.POSNR | material <- VBAP.MATNR | item_net <- VBAP.NETWR
CREATE VIEW dbo.v_order_items AS
SELECT k.VBELN AS order_no, k.KUNNR AS sold_to, p.POSNR AS item_no, p.MATNR AS material, p.NETWR AS item_net
FROM lakehouse.dbo.VBAK AS k
INNER JOIN lakehouse.dbo.VBAP AS p ON p.MANDT = k.MANDT AND p.VBELN = k.VBELN;
