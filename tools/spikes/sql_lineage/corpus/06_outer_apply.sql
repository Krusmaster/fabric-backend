-- dialect: tsql
-- covers: OUTER APPLY with TOP 1 and a correlated WHERE on a three-column key (MANDT, VBELN, POSNR)
-- expected_joins: VBAP.MANDT = VBEP.MANDT | VBAP.VBELN = VBEP.VBELN | VBAP.POSNR = VBEP.POSNR
-- expected_lineage: VBELN <- VBAP.VBELN | POSNR <- VBAP.POSNR | first_delivery_date <- VBEP.EDATU
SELECT p.VBELN, p.POSNR, s.EDATU AS first_delivery_date
FROM dbo.VBAP AS p
OUTER APPLY (
    SELECT TOP 1 e.EDATU
    FROM dbo.VBEP AS e
    WHERE e.MANDT = p.MANDT AND e.VBELN = p.VBELN AND e.POSNR = p.POSNR
    ORDER BY e.EDATU
) AS s;
