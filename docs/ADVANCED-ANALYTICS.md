# Advanced analytics: feature table, model, predictions in gold

Round AA1, 22 November 2026. On 21 November the Data Science starter notebook that Krusgraph created in Fabric
(`shop_lh_orders_features`) ran for the first time: it wrote the feature table `orders_features` (one row per order) and
MLflow created the experiment `orders_experiment` with one run. This page describes the next step: from that table to a
model, and from the model to predictions that land in gold and in the semantic model.

Krusgraph writes the notebooks by fixed rules from the keys and links it proved on the rows. It does not use AI to write
them, it does not run them, it does not train anything, and it does not read your rows, your metrics or your models. You
run each notebook in Fabric, and every number it shows comes from your own run.

## The three stages

The Data Science card under **Next, with other Fabric workloads** in the Model item shows each analysis the rules
recommend, with three stages:

| Stage | Notebook | What it writes | Who runs it |
| --- | --- | --- | --- |
| 1. Feature table | `<lakehouse>_<orders>_features` (the WB10 starter, unchanged) | `<orders>_features`: one row per order, with the items summed per order first | you, in Fabric |
| 2. Model | `<lakehouse>_<orders>_<analysis>_model` | a run in the ML experiment `<orders>_experiment` with its parameters and metrics; a registered ML model | you, in Fabric |
| 3. Predictions in gold | `<lakehouse>_<orders>_<analysis>_predictions` | a gold table with `model_name`, `model_version`, `run_id`, `scored_at` and `scored_with` on every row | you, in Fabric |

Each stage has **Dry run** (what would be created, nothing written), **Create** (the notebook in the item's workspace,
attached to the lakehouse, as you), **Open in Fabric** (after Create) and **Download (.ipynb)**. Create never overwrites
a notebook of the same name. The model and prediction notebooks are recorded on the item as `ds_model` and
`ds_predictions`, like the starter's `ds_features`.

**Run now** is not part of this round. It comes from ED3's pull request #136, which is still waiting for the
maintainer. Until #136 is merged, you run each notebook from Fabric with Open in Fabric, then Run all.

## The analyses and their rules

The rules work on the proven grain: the link between the item table and the order table (for example
`order_items -> orders`, or `sap_vbrp -> sap_vbrk` with the client column), where the order table has a proven key.

| Analysis | Recommended when | Stage 2 | Stage 3 (gold) |
| --- | --- | --- | --- |
| Weekly orders forecast | always (the notebook stops when the feature table has no date column) | a seasonal naive baseline (the same week 52 weeks earlier, or the last week when there is less than a year) and a scikit-learn `LinearRegression` on the trend and the week of the year, backtested on the last 8 weeks (mean absolute error of each); the regression is registered | `gold.<orders>_forecast`: `week_start`, `forecast_orders`, `baseline_orders` for the next 8 weeks |
| Customer segments | the order table has a proven link to a table whose name reads as a customer (`customer`, `kunde`, `kna1`, ...) | k-means on recency, frequency and value per customer (log(1+x), standardised, in a scikit-learn pipeline). k is chosen by a stated rule: the best silhouette over k = 2 to 6, and a smaller k within 0.01 of the best wins | `gold.customer_segment`: the customer key, `segment` (for example "Segment 1 of 3: recent, frequent, high value"), `cluster`, `recency_days`, `frequency`, `monetary` |
| Top 10 drivers | always | descriptive, no model: the top 10 customers and the top 10 values of each text column with 2 to 50 values, by share of orders and of value | none (stage 2 writes `gold.<orders>_top10` itself) |

The value column is also chosen by a rule. It is the first that exists of: an amount summed from the items (stage 1's
`<items>_<column>_sum`), the order's own amount, a quantity summed from the items, or the number of item rows. The date
column is the first column with a date type. If there is none, it is the first text column whose name ends like a date
and whose values are dates (SAP's `YYYYMMDD` included).

**Row thresholds.** No model is trained below 200 orders, 30 weeks (forecast) or 30 customers (segments). Below the
threshold the editor says once, "Too few rows for a model (60 orders; a model starts at 200 orders). The feature table
is still useful", and the notebook prints the same sentence and trains nothing. The shop sample has 60 orders, so it
shows this sentence. The SAP full demo (`sap_demo36`: 4,220 invoices over 36 months, about 300 customers) has rows
enough for every model.

**Grain.** Every stage-2 and stage-3 notebook reads only the feature table, which already has one row per order. Before
anything else, each notebook checks that the order key does not repeat. A repeated key would double every total summed
over it, so the notebook stops before it fits anything. The notebooks join no table to another, and no fact to a fact.

## Fabric features used (Microsoft Learn, read 22 November 2026)

- Autologging: Fabric turns on `mlflow.autolog()` when a notebook imports MLflow. The notebooks call
  `mlflow.autolog(exclusive=False)` so that their own parameters and metrics are logged in the same run.
  <https://learn.microsoft.com/fabric/data-science/mlflow-autologging> (ms.date 2026-05-15).
- Model scoring with PREDICT: `synapse.ml.predict.MLFlowTransformer(inputCols, outputCol, modelName, modelVersion)`.
  Sklearn is one of the supported flavors, and the model must be in MLflow format with its signature (the notebooks log it
  with `infer_signature`). <https://learn.microsoft.com/fabric/data-science/model-scoring-predict> (ms.date 2026-02-28).
  If `synapse.ml` cannot be imported, the notebook scores with `mlflow.pyfunc.spark_udf` and writes that in
  `scored_with`.
- ML experiments and ML models: `mlflow.set_experiment` creates the experiment item in the workspace, and
  `registered_model_name` registers an ML model item.
  <https://learn.microsoft.com/fabric/data-science/machine-learning-experiment>,
  <https://learn.microsoft.com/fabric/data-science/machine-learning-model>.

## Metrics in the editor: "Open the experiment"

The editor does not show the experiment's metrics. Fabric's REST API for ML experiments
(<https://learn.microsoft.com/rest/api/fabric/mlexperiment/items>) has Create, Delete, Get, List and Update for the item,
and nothing for its runs, parameters or metrics. Reading them would need MLflow's tracking API against the workspace's
tracking endpoint, which Microsoft does not document for a workload's delegated token. That would mean a new permission
or an undocumented call, and this round adds neither. So the section says where the metrics are and links to the
experiment ("Open the experiment"). Status in the editor is what Krusgraph knows itself: which notebooks it created.

## Into the semantic model and the report

When the semantic model is drafted on gold (DPM1, [MODEL-ON-GOLD.md](MODEL-ON-GOLD.md)), Krusgraph reads the tables of
the gold schema, as the signed-in user, with the same metadata read as any plan. A table counts as a prediction table
when it has `model_version` and `run_id`, plus `segment` and `cluster` (segments) or `week_start` and `forecast_orders`
(forecast). Each prediction table found:

- is added to the model with one measure in the display folder **Advanced analytics** ("Customers in segments" =
  `COUNTROWS`, "Forecast orders" = `SUM` of `forecast_orders`) and the annotation `Krusgraph_AdvancedAnalytics`. It is in
  no data product and no perspective;
- `customer_segment` relates on its customer column to the dimension view whose one-column key has that name. On SAP the
  customer key is the client plus the customer, so the notebook writes gold's combined key column (`MANDT_KUNNR_key`,
  with the values joined by U+001F, as in `combined_keys.py`). If no dimension has that key, the table is not added, and
  the dry run says why;
- the forecast's `week_start` relates to the calendar, like any date column of a fact;
- the report gets one more visual for each table: "Customers by segment" (a bar chart) and "Forecast orders by week" (a
  column chart).

If no prediction table exists, nothing is added, and the model is the same as before this round.
`orders_top10` is descriptive and stays out of the model.

## What leaves Fabric

Nothing. The notebooks run in your workspace on your lakehouse. Their runs, models and gold tables stay there.
Krusgraph creates the notebooks in your workspace with your token (the same Notebook create the starter has used since
WB10) and reads table metadata for the semantic model's dry run. No row, metric or model reaches Krusgraph. This round
adds no Entra permission.

## How it was tested

`tests/test_aa1_advanced_stages.py` (22 November 2026) runs each generated notebook cell by cell on the synthetic SAP full
demo and on the shop sample. It uses a pandas stand-in for Spark and a small stand-in for MLflow and PREDICT, so the real
Spark, MLflow and `synapse.ml` are not exercised. The tests check that each notebook parses, uses no undefined name, and
makes a valid `.ipynb`. They also check the grain check, the value taken from the items rather than the header, that a
table the notebook did not write is never replaced, the too-few-rows sentence, the gold tables' columns, and the semantic
model with and without prediction tables. In CI the tests that need pandas and scikit-learn are skipped where those
packages are not installed. `advancedStages.test.tsx` checks that the editor fills the templates exactly as the Python
does, and that it shows the three stages. None of this has run in Fabric yet. The next live test is Gustav's.
