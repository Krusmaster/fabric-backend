-- dialect: spark
-- covers: lakehouse.schema.table without quoting, a CTE whose columns are joined on, a boolean filter
-- expected_joins: OPPORTUNITY.ID = QUOTE.OPPORTUNITYID | PRICEBOOK2.ID = QUOTE.PRICEBOOK2ID
-- expected_lineage: opportunity_name <- OPPORTUNITY.NAME | quote_total <- QUOTE.GRANDTOTAL | pricebook_name <- PRICEBOOK2.NAME
WITH quotes AS (
    SELECT q.Id, q.OpportunityId, q.Pricebook2Id, q.GrandTotal
    FROM sales_lh.salesforce.Quote q
    WHERE q.IsSyncing = true
)
SELECT o.Name AS opportunity_name, qt.GrandTotal AS quote_total, pb.Name AS pricebook_name
FROM sales_lh.salesforce.Opportunity o
JOIN quotes qt ON qt.OpportunityId = o.Id
LEFT JOIN sales_lh.salesforce.Pricebook2 pb ON pb.Id = qt.Pricebook2Id
