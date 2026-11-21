-- dialect: tsql
-- covers: window functions (ROW_NUMBER, SUM OVER); lineage counts every column the output expression reads
-- expected_joins: ACCOUNT.ID = OPPORTUNITY.ACCOUNTID
-- expected_lineage: account_name <- ACCOUNT.NAME | opportunity_name <- OPPORTUNITY.NAME | Amount <- OPPORTUNITY.AMOUNT | rank_in_account <- OPPORTUNITY.ACCOUNTID, OPPORTUNITY.AMOUNT | account_pipeline <- OPPORTUNITY.AMOUNT, ACCOUNT.ID
SELECT a.Name AS account_name, o.Name AS opportunity_name, o.Amount,
       ROW_NUMBER() OVER (PARTITION BY o.AccountId ORDER BY o.Amount DESC) AS rank_in_account,
       SUM(o.Amount) OVER (PARTITION BY a.Id) AS account_pipeline
FROM dbo.Opportunity AS o
INNER JOIN dbo.Account AS a ON a.Id = o.AccountId
WHERE o.IsDeleted = 0;
