-- dialect: tsql
-- covers: MERGE with a joined USING source; the target table (order_summary) is not in the schema
-- expected_joins: VBAK.MANDT = VBAP.MANDT | VBAK.VBELN = VBAP.VBELN | ORDER_SUMMARY.MANDT = VBAK.MANDT | ORDER_SUMMARY.VBELN = VBAK.VBELN
-- expected_lineage: (none)
MERGE INTO dbo.order_summary AS t
USING (
    SELECT k.MANDT, k.VBELN, SUM(p.NETWR) AS items_net
    FROM dbo.VBAK k
    JOIN dbo.VBAP p ON p.MANDT = k.MANDT AND p.VBELN = k.VBELN
    GROUP BY k.MANDT, k.VBELN
) AS s
ON t.MANDT = s.MANDT AND t.VBELN = s.VBELN
WHEN MATCHED THEN UPDATE SET t.items_net = s.items_net
WHEN NOT MATCHED THEN INSERT (MANDT, VBELN, items_net) VALUES (s.MANDT, s.VBELN, s.items_net);
