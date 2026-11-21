-- dialect: spark
-- covers: Spark backtick quoting of every part, `lakehouse`.`schema`.`table`, a reserved word as a table name (Order)
-- expected_joins: ORDER.ID = ORDERITEM.ORDERID | ACCOUNT.ID = ORDER.ACCOUNTID | ORDERITEM.PRODUCT2ID = PRODUCT2.ID
-- expected_lineage: order_id <- ORDER.ID | account_name <- ACCOUNT.NAME | Quantity <- ORDERITEM.QUANTITY | ProductCode <- PRODUCT2.PRODUCTCODE
SELECT `o`.`Id` AS order_id, `a`.`Name` AS account_name, `oi`.`Quantity`, `p`.`ProductCode`
FROM `sales_lh`.`dbo`.`Order` AS `o`
JOIN `sales_lh`.`dbo`.`OrderItem` AS `oi` ON `oi`.`OrderId` = `o`.`Id`
JOIN `sales_lh`.`dbo`.`Account` AS `a` ON `a`.`Id` = `o`.`AccountId`
LEFT JOIN `sales_lh`.`dbo`.`Product2` AS `p` ON `p`.`Id` = `oi`.`Product2Id`
