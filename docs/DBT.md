# dbt from Krusgraph

`dbt_schema` writes dbt files from the plan Krusgraph checked. Without `project` it returns one sources file
(`models/sources/<source>.yml`: `unique` and `not_null` on key columns, `relationships` on every one-column
relationship). With `project=true` it returns a whole dbt project draft for the dbt-fabric adapter 1.12 on dbt-core 1.12
and a Fabric Data Warehouse (T-SQL): staging models typed and de-duplicated on the key, marts only over relationships the
counts showed to be many-to-one, a profile without a secret, a README that says how to run it, and singular tests. The
code is `fabric_backend/dbt.py` and `fabric_backend/dbt_checks.py`; the tests are `tests/test_dbt_project.py`,
`tests/test_n156_dbt_flow.py` and `tests/test_dbt1_singular_tests.py`.

Krusgraph writes the files and runs nothing: no dbt command, no Warehouse change. A person reads them and runs dbt.

## The tests Krusgraph writes from its checks

Since round DBT1 the project has a folder `tests/krusgraph_checks/` of singular tests (a `.sql` file that returns the
failing rows; dbt passes it when it returns none). Each file starts with a comment that says which Krusgraph check or
pack rule it comes from and what was counted. They are T-SQL for dbt-fabric with no CTE (the adapter rejects nested CTEs,
and dbt compiles a test inside one) and no dbt-utils (dbt-fabric's documentation says it is not supported).

| Test | From | Fails when |
| --- | --- | --- |
| `<source>__<table>__duplicate_<key columns>.sql` | the key check, for every key over several columns | two rows of the **source** share the key. The staging model keeps one row per key, so its own key test cannot see this. |
| `<source>__<table>__orphans_<columns>__in_<parent>.sql` | the relationship check, for every relationship over several columns | a child row's reference has no row in the parent, counted as validate_plan counts it (a NULL is no reference; under the SAP pack a blank outside the client column is none either) |
| `<mart>__<amount>_summed_once.sql` | validate_plan's `amount_levels` (a header amount a join repeats) and the pack trap with check `amount_level` that names it | the mart at the header's grain sums the amount to a different total than the header table: a mart that joins the lines and carries the header amount on each of them gives a larger total |
| `<mart>__one_row_per_<line>_row.sql` | the same finding, for the mart at the line's grain | the mart has a different number of rows than the line table. The header amount is left out of that mart, and "never sum it over the lines" cannot be written as a generic test there, so the grain is tested instead |

One-column keys and relationships already have dbt's built-in tests in the sources file, so they get no file here.

An example from the synthetic SAP demo (`fabric_backend/sap_demo.py`), `tests/krusgraph_checks/fct_sap_vbak__netwr_summed_once.sql`:

```sql
-- From Krusgraph's amount check (validate_plan, amount_levels): sap_vbak.NETWR is an amount of the whole sap_vbak row, repeated on every sap_vbap row in a join (sap_vbap.MANDT+VBELN -> sap_vbak.MANDT+VBELN, rule SAP pack); counted: up to 3 sap_vbap rows per sap_vbak row (average 1.67).
-- Pack rule: sap trap amount_levels (Header amounts and item amounts are different levels).
-- fct_sap_vbak has one row per sap_vbak row. Returns the two sums of netwr when the mart's differs from sap_vbak's own; passes when it returns none.
-- A mart that joins the lines and carries netwr on each of them sums it once per line, and its total comes out larger.
select m.[total] as [mart_total], h.[total] as [sap_vbak_total]
from (select sum(cast([netwr] as decimal(38, 4))) as [total] from {{ ref('fct_sap_vbak') }}) as m
cross join (select sum(cast([netwr] as decimal(38, 4))) as [total] from {{ ref('stg_sap__sap_vbak') }}) as h
where abs(coalesce(m.[total], 0) - coalesce(h.[total], 0)) >= 0.01
```

How this was verified (unit tests, 21 November 2026, `tests/test_dbt1_singular_tests.py`): on the synthetic SAP,
Salesforce and Dynamics 365 demos the new tests' SQL is compared with golden files, parses as T-SQL, and is run in
SQLite on the demo rows with the staging models and marts as views. Only the planted orphan fails (SAP: item
0000000009 of an order that does not exist). A planted duplicate fails exactly its key test; a mart rewritten to join
the header to its lines fails its sum test (SAP: 1 950 against 750); a line mart rewritten to join its lines many-to-many
fails its grain test. dbt itself was not run.

## Run the project Krusgraph wrote with dbt-core-mcp

Krusgraph checks and drafts; you run and test the project in your own environment. One way to do that from a chat is
dbt-core-mcp (<https://github.com/NiclasOlofsson/dbt-core-mcp>, MIT), a separate open-source MCP server that runs dbt
commands with the dbt installation and adapter of the project folder it is pointed at. It is not part of Krusgraph:
Krusgraph does not depend on it, contains none of its code and does not call it. Nothing here claims a partnership or
an endorsement, and we have not run it on a Krusgraph project against a Fabric Warehouse ourselves.

What its README says (read 21 November 2026, at commit `343225e`; 1.7.1 on PyPI): it needs dbt Core 1.9 or newer in
the project's environment (this draft asks for 1.12); it is started with `uvx dbt-core-mcp` (or `pipx run
dbt-core-mcp`) and takes `--project-dir`; its tools include `get_project_info` (which runs `dbt debug`),
`get_lineage`, `run_models`, `test_models` and `build_models`. Running models changes the Warehouse, as `dbt build`
always does.

1. In Claude, ask Krusgraph for the project: `dbt_schema` with `project=true` and `check_rows=true`. Save the files it
   returns in a folder, as they are.
2. In that folder, install dbt-core 1.12 and dbt-fabric 1.12.0 (the README of the project says how), copy
   `profiles.example.yml` to your own `~/.dbt/profiles.yml` and fill it in. No secret goes in the project folder.
3. Point dbt-core-mcp at the folder (`--project-dir`), in the MCP client you use, and ask it to check the connection
   (`get_project_info`), then to build (`build_models`) or test (`test_models`). Read the models first: building is the
   step that creates views and tables in the Warehouse.
4. Read the failing tests. Each file under `tests/krusgraph_checks/` says in its first lines which Krusgraph check it
   comes from; a failure there is the same finding Krusgraph showed, now on the Warehouse's rows.

A failing test on a source stops dbt from building the models that read that source (dbt skips what is downstream of a
failed test). That is on purpose for an orphan or a duplicate you have not decided about yet. When you have decided
(the staging model drops the orphans, for example), set the test's severity to `warn` in its own file with
`{{ config(severity='warn') }}`, or leave it out with `--exclude`.

`docs/demo/DBT-DEMO.md` walks through this on the synthetic SAP demo.

dbt Labs' own MCP server, dbt-labs/dbt-mcp (Apache-2.0), can run the same project too; `fabric_backend/dbt.py`'s module
notes say what was read about it.
