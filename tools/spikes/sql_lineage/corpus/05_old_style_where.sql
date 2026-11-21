-- dialect: tsql
-- covers: old-style comma joins with the join condition in WHERE, mixed with a literal filter
-- expected_joins: KNA1.MANDT = VBRK.MANDT | KNA1.KUNNR = VBRK.KUNRG | TVKO.MANDT = VBRK.MANDT | TVKO.VKORG = VBRK.VKORG
-- expected_lineage: invoice <- VBRK.VBELN | NETWR <- VBRK.NETWR | payer_name <- KNA1.NAME1 | BUKRS <- TVKO.BUKRS
SELECT r.VBELN AS invoice, r.NETWR, c.NAME1 AS payer_name, o.BUKRS
FROM dbo.VBRK r, dbo.KNA1 c, dbo.TVKO o
WHERE c.MANDT = r.MANDT AND c.KUNNR = r.KUNRG
  AND o.MANDT = r.MANDT AND o.VKORG = r.VKORG
  AND r.FKART = 'F2';
