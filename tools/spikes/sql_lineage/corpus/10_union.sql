-- dialect: tsql
-- covers: UNION ALL with a join in each branch (same alias c reused), a literal output column
-- expected_joins: KNA1.MANDT = VBAK.MANDT | KNA1.KUNNR = VBAK.KUNNR | KNA1.MANDT = VBRK.MANDT | KNA1.KUNNR = VBRK.KUNAG
-- expected_lineage: doc_type <- (none) | doc_no <- VBAK.VBELN, VBRK.VBELN | customer_name <- KNA1.NAME1
SELECT 'order' AS doc_type, k.VBELN AS doc_no, c.NAME1 AS customer_name
FROM dbo.VBAK k
JOIN dbo.KNA1 c ON c.MANDT = k.MANDT AND c.KUNNR = k.KUNNR
UNION ALL
SELECT 'invoice', r.VBELN, c.NAME1
FROM dbo.VBRK r
JOIN dbo.KNA1 c ON c.MANDT = r.MANDT AND c.KUNNR = r.KUNAG;
