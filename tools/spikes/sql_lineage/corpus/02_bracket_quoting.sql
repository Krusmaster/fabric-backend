-- dialect: tsql
-- covers: bracket quoting, [lh].[dbo].[table] three-part names, chained LEFT JOINs, a literal filter inside ON
-- expected_joins: MARA.MANDT = VBAP.MANDT | MARA.MATNR = VBAP.MATNR | MAKT.MANDT = MARA.MANDT | MAKT.MATNR = MARA.MATNR
-- expected_lineage: VBELN <- VBAP.VBELN | POSNR <- VBAP.POSNR | MTART <- MARA.MTART | material_text <- MAKT.MAKTX
SELECT [p].[VBELN], [p].[POSNR], [m].[MTART], [t].[MAKTX] AS [material_text]
FROM [lh].[dbo].[VBAP] AS [p]
LEFT JOIN [lh].[dbo].[MARA] AS [m] ON [m].[MANDT] = [p].[MANDT] AND [m].[MATNR] = [p].[MATNR]
LEFT JOIN [lh].[dbo].[MAKT] AS [t] ON [t].[MANDT] = [m].[MANDT] AND [t].[MATNR] = [m].[MATNR] AND [t].[SPRAS] = 'E';
