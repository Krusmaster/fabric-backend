-- dialect: tsql
-- covers: non-equality join predicates (BETWEEN, >=) next to equality ones; only the equalities are key evidence
-- expected_joins: LIKP.MANDT = VBAK.MANDT | LIKP.KUNAG = VBAK.KUNNR | LIKP.MANDT = VBRK.MANDT | LIKP.KUNAG = VBRK.KUNAG
-- expected_lineage: order_no <- VBAK.VBELN | delivery_no <- LIKP.VBELN | invoice_no <- VBRK.VBELN
SELECT k.VBELN AS order_no, h.VBELN AS delivery_no, r.VBELN AS invoice_no
FROM dbo.VBAK k
JOIN dbo.LIKP h ON h.MANDT = k.MANDT AND h.KUNAG = k.KUNNR
               AND h.ERDAT BETWEEN k.ERDAT AND k.AEDAT
LEFT JOIN dbo.VBRK r ON r.MANDT = h.MANDT AND r.KUNAG = h.KUNAG AND r.FKDAT >= h.ERDAT;
