| Statement | Dialect | sqlglot joins P / R / lineage | sqllens joins P / R / lineage |
|---|---|---|---|
| 01_view_order_items | tsql | 2/2 / 2/2 / 5/5 | 2/2 / 2/2 / 5/5 |
| 02_bracket_quoting | tsql | 4/4 / 4/4 / 4/4 | 4/4 / 4/4 / 4/4 |
| 03_chained_ctes | tsql | 4/4 / 4/4 / 4/4 | 4/4 / 4/4 / 4/4 |
| 04_subquery_in_from | tsql | 4/4 / 4/4 / 3/3 | 4/4 / 4/4 / 3/3 |
| 05_old_style_where | tsql | 4/4 / 4/4 / 4/4 | 4/4 / 4/4 / 4/4 |
| 06_outer_apply | tsql | 3/3 / 3/3 / 2/3 | 3/3 / 3/3 / 3/3 |
| 07_cross_apply | tsql | 4/4 / 4/4 / 1/3 | 4/4 / 4/4 / 3/3 |
| 08_merge | tsql | 4/4 / 4/4 / - | 2/2 / 2/4 / - |
| 09_insert_select | tsql | 4/4 / 4/4 / 5/5 | 4/4 / 4/4 / 5/5 |
| 10_union | tsql | 4/4 / 4/4 / 3/3 | 4/4 / 4/4 / 1/3 |
| 11_window | tsql | 1/1 / 1/1 / 5/5 | 1/1 / 1/1 / 5/5 |
| 12_date_range_not_a_key | tsql | 4/4 / 4/4 / 3/3 | 4/4 / 4/4 / 3/3 |
| 13_spark_backticks | spark | 3/3 / 3/3 / 4/4 | 3/3 / 3/3 / 4/4 |
| 14_spark_cte_lakehouse | spark | 2/2 / 2/2 / 3/3 | 2/2 / 2/2 / 3/3 |
| 15_dbt_rendered | spark | 1/1 / 1/1 / 4/4 | 1/1 / 1/1 / 4/4 |
| 16_dbt_ref_jinja | spark | 1/1 / 1/1 / 3/3 | 1/1 / 1/1 / 3/3 |
| 17_spark_insert_overwrite | spark | 7/7 / 7/7 / 5/5 | 7/7 / 7/7 / 5/5 |
| 18_spark_exists | spark | 2/2 / 2/2 / 2/2 | 2/2 / 2/2 / 2/2 |
| 19_spark_using | spark | 3/3 / 3/3 / 3/3 | 3/3 / 3/3 / 3/3 |

| Run | Version | Join precision | Join recall | Lineage exact | Parse failures |
|---|---|---|---|---|---|
| sqlglot | 30.33.0 | 61/61 (100%) | 61/61 (100%) | 63/66 (95%) | 0/19 |
| sqllens | 1.11.0 | 59/59 (100%) | 59/61 (97%) | 64/66 (97%) | 0/19 |
| sqlglot raw | 30.33.0 | 58/58 (100%) | 58/61 (95%) | 60/66 (91%) | 1/19 |
| sqllens raw | 1.11.0 | 47/47 (100%) | 47/61 (77%) | 51/66 (77%) | 1/19 |

Misses and wrong pairs/columns per run:
- sqlglot 06_outer_apply: missed joins -; wrong joins -; lineage wrong [('FIRST_DELIVERY_DATE', ['VBAP.MANDT', 'VBAP.POSNR', 'VBAP.VBELN'])]
- sqlglot 07_cross_apply: missed joins -; wrong joins -; lineage wrong [('PARVW', ['VBAK.MANDT', 'VBAK.VBELN']), ('PARTNER_NAME', ['VBAK.MANDT', 'VBAK.VBELN'])]
- sqllens 08_merge: missed joins ['ORDER_SUMMARY.MANDT = VBAK.MANDT', 'ORDER_SUMMARY.VBELN = VBAK.VBELN']; wrong joins -; lineage wrong -
- sqllens 10_union: missed joins -; wrong joins -; lineage wrong [('DOC_TYPE', ['VBRK.VBELN']), ('DOC_NO', ['KNA1.NAME1', 'VBAK.VBELN'])]
- sqlglot raw 06_outer_apply: missed joins -; wrong joins -; lineage wrong [('FIRST_DELIVERY_DATE', ['VBAP.MANDT', 'VBAP.POSNR', 'VBAP.VBELN'])]
- sqlglot raw 07_cross_apply: missed joins -; wrong joins -; lineage wrong [('PARVW', ['VBAK.MANDT', 'VBAK.VBELN']), ('PARTNER_NAME', ['VBAK.MANDT', 'VBAK.VBELN'])]
- sqlglot raw 08_merge: missed joins ['ORDER_SUMMARY.MANDT = VBAK.MANDT', 'ORDER_SUMMARY.VBELN = VBAK.VBELN']; wrong joins -; lineage wrong -
- sqlglot raw 16_dbt_ref_jinja: missed joins ['ACCOUNT.ID = CONTACT.ACCOUNTID']; wrong joins -; lineage wrong [('CONTACT_ID', None), ('LAST_NAME', None), ('ACCOUNT_NAME', None)]
- sqllens raw 01_view_order_items: missed joins ['VBAK.MANDT = VBAP.MANDT', 'VBAK.VBELN = VBAP.VBELN']; wrong joins -; lineage wrong [('ORDER_NO', None), ('SOLD_TO', None), ('ITEM_NO', None), ('MATERIAL', None), ('ITEM_NET', None)]
- sqllens raw 08_merge: missed joins ['ORDER_SUMMARY.MANDT = VBAK.MANDT', 'ORDER_SUMMARY.VBELN = VBAK.VBELN', 'VBAK.MANDT = VBAP.MANDT', 'VBAK.VBELN = VBAP.VBELN']; wrong joins -; lineage wrong -
- sqllens raw 09_insert_select: missed joins ['ACCOUNT.ID = OPPORTUNITY.ACCOUNTID', 'OPPORTUNITY.ID = OPPORTUNITYLINEITEM.OPPORTUNITYID', 'OPPORTUNITYLINEITEM.PRICEBOOKENTRYID = PRICEBOOKENTRY.ID', 'PRICEBOOKENTRY.PRODUCT2ID = PRODUCT2.ID']; wrong joins -; lineage wrong [('OPPORTUNITY_ID', None), ('ACCOUNT_NAME', None), ('PRODUCT_NAME', None), ('QUANTITY', None), ('TOTAL_PRICE', None)]
- sqllens raw 10_union: missed joins -; wrong joins -; lineage wrong [('DOC_TYPE', ['VBRK.VBELN']), ('DOC_NO', ['KNA1.NAME1', 'VBAK.VBELN'])]
- sqllens raw 16_dbt_ref_jinja: missed joins ['ACCOUNT.ID = CONTACT.ACCOUNTID']; wrong joins -; lineage wrong [('CONTACT_ID', None), ('LAST_NAME', None), ('ACCOUNT_NAME', None)]
- sqllens raw 19_spark_using: missed joins ['VBAP.MANDT = VBEP.MANDT', 'VBAP.POSNR = VBEP.POSNR', 'VBAP.VBELN = VBEP.VBELN']; wrong joins -; lineage wrong -
