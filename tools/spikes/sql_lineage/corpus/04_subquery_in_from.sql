-- dialect: tsql
-- covers: a join inside a derived table, then a join on the derived table's renamed column (order_no -> LIPS.VGBEL)
-- expected_joins: LIKP.MANDT = LIPS.MANDT | LIKP.VBELN = LIPS.VBELN | LIKP.MANDT = VBAK.MANDT | LIPS.VGBEL = VBAK.VBELN
-- expected_lineage: delivery <- LIKP.VBELN | order_no <- LIPS.VGBEL | AUART <- VBAK.AUART
SELECT d.VBELN AS delivery, d.order_no, k.AUART
FROM (
    SELECT h.MANDT, h.VBELN, i.VGBEL AS order_no
    FROM dbo.LIKP h
    INNER JOIN dbo.LIPS i ON i.MANDT = h.MANDT AND i.VBELN = h.VBELN
) AS d
INNER JOIN dbo.VBAK k ON k.MANDT = d.MANDT AND k.VBELN = d.order_no;
