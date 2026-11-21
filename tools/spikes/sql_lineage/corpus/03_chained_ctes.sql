-- dialect: tsql
-- covers: chained CTEs (a CTE reading a CTE), a join on CTE columns that must resolve to base tables, aggregation
-- expected_joins: VBAK.MANDT = VBAP.MANDT | VBAK.VBELN = VBAP.VBELN | KNA1.MANDT = VBAK.MANDT | KNA1.KUNNR = VBAK.KUNNR
-- expected_lineage: VBELN <- VBAK.VBELN | customer_name <- KNA1.NAME1 | header_net <- VBAK.NETWR | items_net <- VBAP.NETWR
WITH items AS (
    SELECT MANDT, VBELN, COUNT(*) AS item_count, SUM(NETWR) AS items_net
    FROM dbo.VBAP
    GROUP BY MANDT, VBELN
), orders AS (
    SELECT k.MANDT, k.VBELN, k.KUNNR, k.NETWR, i.item_count, i.items_net
    FROM dbo.VBAK k
    JOIN items i ON i.MANDT = k.MANDT AND i.VBELN = k.VBELN
)
SELECT o.VBELN, c.NAME1 AS customer_name, o.NETWR AS header_net, o.items_net
FROM orders o
JOIN dbo.KNA1 c ON c.MANDT = o.MANDT AND c.KUNNR = o.KUNNR;
