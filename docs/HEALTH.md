# Health over time: `krusgraph.health`, drift, alerts and the health word

Round n200, the first build round of [LIFECYCLE-DESIGN.md](LIFECYCLE-DESIGN.md) (section 8, round 1; sections 1.1,
1.2 and 5.3). Written 11 November 2026. The code is `fabric_backend/health.py`; the pipeline notebooks carry it
verbatim, like the check (`pipeline.CHECK_CODE`). No AI, no new permission.

**Status:** unit-tested on SQLite (`tests/test_n200_health.py`, the shop and mill samples) and on a local PySpark
(`tests/test_spark_notebooks.py`). **Not yet run in Fabric:** the Delta table history read, the Key Vault read and the
Adaptive Card post have not run in a Fabric workspace.

## 1. What a pipeline run writes

Every pipeline Krusgraph creates now appends rows to one table in the lakehouse:

- `krusgraph.health` on a lakehouse with schemas (the pipeline needs one);
- `krusgraph_health` on a lakehouse without schemas (the code supports it; the pipeline is not offered there).

The table is made on the first run and only ever appended to. Nothing is deleted or updated.

| Column | Type | Example | Note |
|---|---|---|---|
| `run_id` | string | the pipeline run id | `@pipeline().RunId`, handed to the silver and check notebooks; `manual-<12 hex>` for a notebook run by hand |
| `checked_at` | timestamp | 2026-11-11T06:00:00Z | UTC |
| `plan_id` | string | `plan-0123456789ab` | The plan the outputs were built from, as `outputs.json` records it |
| `schema_fingerprint` | string | `sha256:00112233445566ff` | The same plan's fingerprint |
| `check` | string | `orphans` | One of `key`, `orphans`, `join_rows`, `join_sums`, `row_count`, `freshness`, `quarantine`, `drift` |
| `object` | string | `silver.order_items.order_id` | A table, a view, a column, a relationship's source columns |
| `rule` | string | `R1` | The engine's rule (K0–K5, R0–R5), or the kind of finding (below) |
| `status` | string | `fail` | `pass`, `warn` or `fail` |
| `count` | bigint | 1 | Rows, NULL or duplicate keys, orphans, quarantined rows, minutes, or differing amounts (below) |
| `baseline` | bigint | 0 | The same count in the previous run of the same plan; empty on the first run |

**Never a row value.** The rows hold names, rules, statuses and counts. No key value, no sample row, no amount. For
`join_sums` the row says only whether the sums match; `count` is the number of amount columns that differ, never a sum.
The quarantine table keeps its rows as before (in the customer's lakehouse); the health table only counts them.

### The checks

| `check` | `object` | `rule` | `count` | `status` |
|---|---|---|---|---|
| `key` | `silver.<table>` | the key's rule | NULL keys plus duplicated values | `fail` when a key silver de-duplicates on does not hold; `warn` for a key guessed from names (n208: silver kept every row, reported, never a failure) |
| `orphans` | `silver.<table>.<column>[+<column>]` | the relationship's rule | rows without their row in the target | `fail` on any orphan |
| `join_rows` | `gold.<view>` | `rows` | the difference between the rows before and after the join | `fail` when it is not 0 |
| `join_sums` | `gold.<view>` (only views with an amount) | `sums` | amount columns whose SUM differs | `fail` when it is not 0 |
| `row_count` | `silver.<table>`, `gold.<view>` | `rows` | rows | `warn` when it fell by 50 % or more against `baseline` (the owner's `ROW_COUNT_DROP`) |
| `row_count` | a silver table or gold view that is not there | `missing` | 0 | `fail` (the check stops the run, after writing) |
| `freshness` | `<source schema>.<table>`, each table silver reads | `minutes since last write` | minutes since the last commit that wrote rows | `warn` after 2 schedule intervals, `fail` after 3 (`FRESHNESS_WARN_INTERVALS`, `FRESHNESS_FAIL_INTERVALS`) |
| `freshness` | the same | `no history` | empty | `warn`: the table has no readable Delta history (a shortcut to files, say) |
| `quarantine` | `silver.<table>` | the rule that put rows there | rows quarantined in this run | `warn` when rows were set aside; one `pass` row (`all`, 0) when none were |
| `drift` | see section 2 | the kind of drift | 1 | `fail` when it breaks silver or gold, `warn` otherwise; one `pass` row (`plan`, 0) without drift |

The schedule interval is the pipeline's own: every N hours gives N × 60 minutes; a daily schedule, or none, gives one
day (`SCHEDULE_MINUTES` in the check notebook).

**Freshness from the table history, not from the rows.** `DESCRIBE HISTORY <table> LIMIT 50` gives Delta's commits;
the first one that wrote rows is used (maintenance commits such as `OPTIMIZE`, `VACUUM`, `SET TBLPROPERTIES` or a
column change are skipped). Only the commit time is read, never a value in the rows.

The **baseline** is the latest earlier run of the same `plan_id` (another plan's runs are never compared). A new
plan starts without a baseline.

## 2. Drift against the plan, before anything is written

The pipeline's silver notebook (only the one Create puts in the pipeline; the stand-alone silver draft is unchanged)
starts with a drift cell. It compares the source tables now (the Spark catalog: tables, columns and types) with the
plan the outputs were built from (written into the cell). Types are compared by family (text, integer, decimal, float,
bool, date, timestamp, binary), because the plan reads them from the SQL endpoint and Spark names them its own way.

| Finding (`rule`) | Breaks the run? |
|---|---|
| `table_removed`: a source table silver reads is gone | Yes |
| `column_removed`: a column a key, a relationship, an ordering column or a gold view uses is gone | Yes |
| `column_removed`: a column nothing Krusgraph built uses is gone | No |
| `type_changed`: another type family | No |
| `column_added` | No |
| `table_added` (a table in the source schema the plan did not have) | No |

A breaking drift writes its rows, sends the alert when one is set, and stops the run with the reason (`DriftBreaks`:
"... so the run stops before anything is written: orders.order_id is gone ..."). No silver table is written. A
non-breaking drift is recorded and the run goes on. Keys and relationships are not re-inferred in the notebook (that
needs this library); the item's review and Update do that.

## 3. Alerts

### Teams or Power Automate (optional)

1. Make the webhook: in Teams, a workflow "When a Teams webhook request is received" that posts to a channel; or a
   Power Automate flow with an HTTP trigger that sends an e-mail.
2. Put its address in an **Azure Key Vault** secret. The identity that runs the pipeline needs to read that secret.
3. In Fabric, open the pipeline, **Parameters**, and set `alert_key_vault` (`https://<vault>.vault.azure.net/`) and
   `alert_secret_name`. `alert_on` is `fail` (a card when a check fails or a drift breaks the run) or `warn` (warnings
   too).

The address never appears in code, in the notebooks or in the pipeline: the notebook reads the secret at run time
(`notebookutils.credentials.getSecret(vault, name)`, which uses the run's own credentials; Learn,
`data-engineering/microsoft-spark-utilities.md`, ms.date 2026-07-08). The card is an Adaptive Card 1.4 built from the
health rows only (status, check, object, rule, count and last run's count), so it carries no row value. A failed
alert never fails the run and its message never shows the address. A Fabric connection is not offered: notebook code
has no documented way to read one (Unverified).

### Fabric's own e-mail on a failed run (free)

Fabric sends a free e-mail when a **scheduled** run fails (preview; not for manual runs). Learn,
`fabric/admin/monitoring-hub-alerts` (ms.date 2026-09-21):

1. In Fabric, open **Monitor** (the new Monitor experience).
2. Under **Manage**, select **Alerts**, then the **Schedule failure emails** tab, then **+ Configure notifications**.
3. Choose the pipeline, then **Select a scheduled item**.
4. In **Select recipients**, add Entra users or groups, then **Save**.

You need Contributor in the workspace or Write on the pipeline. The pipeline's card (its `steps`) says this after
every Create; the create_pipeline answer also has it under `health`.

## 4. The health word: `POST /workload/v1/health`

A read-only route of the workload engine for the item's data product page (n198 shows it). It runs as the signed-in
user (on-behalf-of, like every workload route) and reads the health table through the lakehouse's SQL analytics
endpoint. It changes nothing in Fabric.

Request:

```json
{
  "workspace": "<workspace id>",
  "source": "<lakehouse id>",
  "source_name": "shop_lh",
  "products": [{"name": "Sales", "plan_id": "plan-0123456789ab"}]
}
```

`products`: 1 to 50 entries; `plan_id` as `outputs.json` records it (`plan-<hex>`); `name` is echoed back.
`source_name` is optional (used in error messages).

Answer (HTTP 200):

```json
{
  "products": [
    {
      "name": "Sales",
      "plan_id": "plan-0123456789ab",
      "health": "red",
      "run_id": "5f0c…",
      "checked_at": "2026-11-11T06:00:00Z",
      "checks": 38,
      "findings": [
        {"check": "orphans", "object": "silver.order_items.order_id", "rule": "R1", "status": "fail", "count": 1, "baseline": 0},
        {"check": "quarantine", "object": "silver.orders", "rule": "K1", "status": "warn", "count": 1, "baseline": 1}
      ]
    }
  ],
  "table": "krusgraph.health",
  "read_as": "the signed-in user",
  "note": "Nothing was created or changed in Fabric. The health table holds names, rules, statuses and counts, never a row value."
}
```

| `health` | When |
|---|---|
| `red` | a row of the latest run of this plan has `fail` |
| `amber` | a row has `warn`, or the run wrote only drift rows (it stopped before the check, or is still running: a finding with `check: "run"` and a `why`) |
| `green` | every row of the latest run passed |
| `not checked yet` | no run of this plan is in the table (or the table does not exist yet; the `note` says so) |

`findings` are the `warn` and `fail` rows of the latest run, failures first. `checked_at` is the latest row's time.
Errors use the workload's usual `{error, kind, hint}` (400 for a bad request; the SQL endpoint's own errors as on the
other routes). The SQL endpoint may show a fresh Delta write a little later (Unverified how long).

## 5. Where it lives

| Part | File |
|---|---|
| The verbatim notebook code (`ALERT_CODE`, `DRIFT_CODE`, `HEALTH_CODE`), the specs, the read SQL and `summarize` | `fabric_backend/health.py` |
| The check notebook's parameters and cells, the pipeline's parameters | `fabric_backend/pipeline.py` |
| The drift cell in the pipeline's silver notebook | `fabric_backend/silver.py` (`cells`, when the spec has `drift`) |
| The plan mark handed to the pipeline; `POST /workload/v1/health` | `fabric_backend/workload_api.py` |
| The pipeline card's steps and `health` | `fabric_backend/server.py` (`create_pipeline`, `PIPELINE_HEALTH_STEPS`) |

`export_item_definitions(items=["pipeline"])` exports the check notebook with the health step; its silver notebook stays
the stand-alone draft (no drift cell).
