-- dialect: spark
-- covers: a dbt model as compiled (jinja already rendered): import CTEs with select *, a final CTE, select * from final
-- expected_joins: OPPORTUNITY.ID = OPPORTUNITYLINEITEM.OPPORTUNITYID
-- expected_lineage: opportunity_id <- OPPORTUNITY.ID | header_amount <- OPPORTUNITY.AMOUNT | lines_total <- OPPORTUNITYLINEITEM.TOTALPRICE | line_count <- OPPORTUNITYLINEITEM.ID
with opportunities as (
    select * from sales_lh.salesforce.Opportunity where IsDeleted = false
),
line_items as (
    select * from sales_lh.salesforce.OpportunityLineItem
),
final as (
    select
        opportunities.Id as opportunity_id,
        opportunities.Amount as header_amount,
        sum(line_items.TotalPrice) as lines_total,
        count(line_items.Id) as line_count
    from opportunities
    left join line_items on line_items.OpportunityId = opportunities.Id
    group by opportunities.Id, opportunities.Amount
)
select * from final
