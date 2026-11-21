# Demo: the dbt project Krusgraph writes, built with dbt-core-mcp (SAP order to cash)

Written 21 November 2026 by round DBT1. A script for showing the dbt flow on the synthetic SAP demo
(`fabric_backend/sap_demo.py`: 17 SAP-shaped tables, every value made up, the traps planted on purpose). Krusgraph checks
and drafts; you run and test the project in your own environment. dbt-core-mcp
(<https://github.com/NiclasOlofsson/dbt-core-mcp>, MIT) is a separate open-source project, used here as one way to run
dbt from a chat; Krusgraph does not depend on it. `docs/DBT.md` says what each test is.

What has been tested: steps 1 and 4 (which tests fail, and why) run in the unit tests on the demo rows in SQLite
(`tests/test_dbt1_singular_tests.py`, 21 November 2026). Steps 2 and 3 have not been run by us: they need your dbt
installation and a Fabric Warehouse.

**Before you start**

- Use it in Claude: the Krusgraph connector is added in claude.ai.
- The SAP demo tables are in a lakehouse (`docs/LIVE-TEST-SAP.md`, steps 1–2), here `demo_lh`, schema `sap`.
- A Fabric Warehouse to build in (a lakehouse's SQL analytics endpoint is read-only, so it is only the source), dbt-core
  1.12 with dbt-fabric 1.12.0, the ODBC Driver 18, and `az login`.

## 1. Krusgraph writes the project (tested in the unit tests)

Ask in Claude:

> Write a dbt project for the sap schema in demo_lh, with the rows counted: dbt_schema with project=true and check_rows=true.

**Expected:** 17 staging models, 6 marts (`fct_sap_vbak`, `fct_sap_vbap`, `fct_sap_lips`, `fct_sap_vbpa`, `fct_sap_vbrk`,
`fct_sap_vbrp`), a sources file with its tests, `profiles.example.yml` with placeholders, a README, and 93 singular
tests, 48 of them in `tests/krusgraph_checks/`. Nothing is created or run. Save the files in a folder as they are.

## 2. You build it with dbt-core-mcp (not tested by us)

1. In the folder: `pip install "dbt-core~=1.12.0" "dbt-fabric==1.12.0"`; copy `profiles.example.yml` to
   `~/.dbt/profiles.yml` and fill in the Warehouse. No secret goes in the folder.
2. Add dbt-core-mcp to your MCP client (its README: `uvx dbt-core-mcp --project-dir <the folder>`).
3. Ask it to check the connection (`get_project_info`, which runs `dbt debug`), then to build everything
   (`build_models`). Building creates the views and tables in the Warehouse: read the models first.

## 3. What dbt reports (expected, not run by us)

The build reports failing tests, and dbt skips the models downstream of a failed source test (here `sap_vbap`'s staging
model and the marts that read it). That is the point of the demo: the traps were planted, and the tests find them.

## 4. Which tests fail on purpose, and why (tested on the demo rows in SQLite)

| Test | Returns | Why |
| --- | --- | --- |
| `tests/krusgraph_checks/sap__sap_vbap__orphans_mandt_vbeln__in_sap_vbak.sql` | `100`, `0000000009` | Planted: an item of an order that does not exist. Krusgraph's relationship check counted it before (1 of 6 rows point at nothing); the file's first line says so. |
| `tests/stg_sap__sap_vbap__references_sap_vbak.sql` | the same row | The same orphan, tested after staging (round n156's test). |
| `tests/stg_sap__sap_vbpa__references_sap_kna1.sql`, `tests/stg_sap__sap_vbpa__references_sap_knvk.sql` | partner rows with a blank `KUNNR` or `PARNR` | Round n156's staging tests count a blank as a reference. SAP writes "no value" as a blank, and Krusgraph's own count, and the new tests in `tests/krusgraph_checks/`, do not count it. Not changed in this round (the existing output stays as it was); see the note at the end. |

Every other singular test passes on the demo rows in SQLite, and no key column the sources file tests is NULL there. The amount tests pass too: `fct_sap_vbak__netwr_summed_once.sql` passes because
the drafted mart sums the items before the join. To show what it guards against, change `fct_sap_vbak` to join
`stg_sap__sap_vbak` to `stg_sap__sap_vbap` on `mandt` and `vbeln` and run the test again: it returns `1950` against
`750`, the order total counted once per item (the planted order 0000000001 has three items).

**Say it in three lines**

1. Krusgraph checks the SAP rows and writes a dbt project with tests named after its checks; it runs nothing.
2. You build it in your own environment, for example with dbt-core-mcp, a separate open-source MCP server.
3. The tests fail where the demo's traps are planted (the orphan item) and pass on what the checks found sound.

**Note for the maintainer.** The two VBPA staging tests above fail on blank references because round n156's
`_relationship_test` has no blank rule, while validate_plan's count has one under the SAP pack. Making them agree changes
existing output, which this round was asked not to do.
