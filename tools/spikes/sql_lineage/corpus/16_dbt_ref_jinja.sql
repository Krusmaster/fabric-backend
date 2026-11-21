-- dialect: spark
-- covers: an uncompiled dbt model with {{ config() }} and {{ ref() }}; here the ref names equal the landed table names
-- expected_joins: ACCOUNT.ID = CONTACT.ACCOUNTID
-- expected_lineage: contact_id <- CONTACT.ID | last_name <- CONTACT.LASTNAME | account_name <- ACCOUNT.NAME
{{ config(materialized='table') }}
select
    c.Id as contact_id,
    c.LastName as last_name,
    a.Name as account_name
from {{ ref('Contact') }} as c
inner join {{ ref('Account') }} as a on a.Id = c.AccountId
