-- dialect: tsql
-- covers: CROSS APPLY over a derived table that has its own JOIN and a correlated WHERE
-- expected_joins: KNA1.MANDT = VBPA.MANDT | KNA1.KUNNR = VBPA.KUNNR | VBAK.MANDT = VBPA.MANDT | VBAK.VBELN = VBPA.VBELN
-- expected_lineage: VBELN <- VBAK.VBELN | PARVW <- VBPA.PARVW | partner_name <- KNA1.NAME1
SELECT k.VBELN, pa.PARVW, pa.partner_name
FROM dbo.VBAK k
CROSS APPLY (
    SELECT v.PARVW, c.NAME1 AS partner_name
    FROM dbo.VBPA v
    JOIN dbo.KNA1 c ON c.MANDT = v.MANDT AND c.KUNNR = v.KUNNR
    WHERE v.MANDT = k.MANDT AND v.VBELN = k.VBELN AND v.POSNR = '000000'
) AS pa;
