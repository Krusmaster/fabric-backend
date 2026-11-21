-- dialect: tsql
-- covers: INSERT ... SELECT over a four-join Salesforce chain (single-column Id keys)
-- expected_joins: OPPORTUNITY.ID = OPPORTUNITYLINEITEM.OPPORTUNITYID | ACCOUNT.ID = OPPORTUNITY.ACCOUNTID | OPPORTUNITYLINEITEM.PRICEBOOKENTRYID = PRICEBOOKENTRY.ID | PRICEBOOKENTRY.PRODUCT2ID = PRODUCT2.ID
-- expected_lineage: opportunity_id <- OPPORTUNITY.ID | account_name <- ACCOUNT.NAME | product_name <- PRODUCT2.NAME | quantity <- OPPORTUNITYLINEITEM.QUANTITY | total_price <- OPPORTUNITYLINEITEM.TOTALPRICE
INSERT INTO dbo.opportunity_lines_flat (opportunity_id, account_name, product_name, quantity, total_price)
SELECT o.Id AS opportunity_id, a.Name AS account_name, pr.Name AS product_name,
       li.Quantity AS quantity, li.TotalPrice AS total_price
FROM dbo.OpportunityLineItem li
JOIN dbo.Opportunity o ON o.Id = li.OpportunityId
JOIN dbo.Account a ON a.Id = o.AccountId
JOIN dbo.PricebookEntry pbe ON pbe.Id = li.PricebookEntryId
JOIN dbo.Product2 pr ON pr.Id = pbe.Product2Id;
