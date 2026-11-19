"""Notebook drafts for the phase-1 analyses: A7 forecasting, A8 RFM segmentation, A3 ABC/XYZ (round AP2).

    spec(result, analysis, info, output_schema="krusgraph_analysis") -> the notebook as data
    cells(spec) -> [(kind, text)]; notebook_source(spec) -> notebook-content.py; ipynb(spec) -> .ipynb (JSON)

Built like the silver and gold notebook drafts: a draft creates nothing and runs nothing. The notebook is wired to the
customer's tables by analysis_plan's answer (which table and column is the date, the amount, the customer, the material,
the item-to-header join with the client column), carries its own reason (the rule's "because", caveats and thresholds)
and the counts at plan time, and stops before modelling when the rows it reads differ from them by more than TOLERANCE.

The analysis itself uses Fabric Data Science's own features when the notebook runs in Fabric: every run is logged to an
ML experiment (MLflow), A7 adds an AutoML (FLAML) forecast in pandas mode beside a seasonal naive and an ETS baseline,
A8 k-means (scikit-learn) beside the RFM scores, the prepared DataFrame can be opened in Data Wrangler, and a semantic
model can be cross-checked through semantic link (SemPy). A library that is not installed is skipped with a printed line,
never silently (a local Spark has none of them). Output tables go to OUTPUT_SCHEMA with the table property
krusgraph.analysis, and a table without that mark is never replaced. Krusgraph runs none of this; the analyst does.
"""
from __future__ import annotations

import json

from . import notebook as _nb
from .infer import PlanInputError

ANALYSES = ("A7", "A8", "A3")
OUTPUT = {"A7": "forecast_monthly", "A8": "rfm_segments", "A3": "abc_xyz"}
MARK = "krusgraph.analysis"


def _py(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def spec(result: dict, analysis: str, info: dict, output_schema: str = "krusgraph_analysis") -> dict:
    """The notebook as data, from analysis_plan.recommend()'s answer for one schema."""
    analysis = str(analysis).upper()
    if analysis not in ANALYSES:
        raise PlanInputError(f"analysis {analysis!r}: phase 1 has notebooks for {', '.join(ANALYSES)}; the others are planned")
    entry = next(e for e in result["recommendations"] if e["analysis"] == analysis)
    ds = result["signals"]["dataset"]
    if entry["readiness"] == "missing" or not ds:
        raise PlanInputError(f"{analysis} is not ready on this data: " + "; ".join(entry["missing"] or ["no sales dataset"]))
    if output_schema.lower() in {str(info.get("schema") or "").lower(), "dbo"}:
        raise PlanInputError("output_schema must be a schema of its own, not the source schema or dbo")
    counts = (result["signals"].get("counts") or {})
    c = counts.get(ds["name"], {}) if isinstance(counts, dict) else {}
    plan_counts = {"months": c.get("totals", {}).get("months"), "customers": c.get("totals", {}).get("customers"),
                   "materials": c.get("totals", {}).get("materials"), "rows": c.get("totals", {}).get("row_count")}
    owner = f"{info.get('item_id') or info.get('item_name') or 'lakehouse'}/{info.get('schema') or 'dbo'}/{analysis}"
    return {"analysis": analysis, "name": entry["name"], "readiness": entry["readiness"], "because": entry["because"],
            "reasons": entry["reasons"], "caveats": entry["caveats"], "rule": entry["rule"], "rule_version": result["rule_version"],
            "thresholds": result["thresholds"], "dataset": ds, "plan_counts": {k: v for k, v in plan_counts.items() if v is not None},
            "source": {"schema": info.get("schema") or "dbo", "schemas_enabled": bool(info.get("schemas_enabled", True)),
                       "item_name": info.get("item_name") or "", "workspace_id": info.get("workspace_id") or "",
                       "item_id": info.get("item_id") or ""},
            "output_schema": output_schema, "output_table": OUTPUT[analysis], "owner": owner,
            "experiment": f"krusgraph-{analysis.lower()}-{ds['name']}"}


# ------------------------------------------------------------------ cells ---------------------------------------------

def _intro(s: dict) -> str:
    th = s["thresholds"]
    lines = [f"# {s['analysis']} {s['name']}, drafted by Krusgraph",
             "",
             f"**Why this analysis.** {s['because']}",
             ""]
    if s["caveats"]:
        lines += ["**Caveats.**", *[f"- {c}" for c in s["caveats"]], ""]
    lines += [f"Rule {s['rule']} ({s['rule_version']}), deterministic: no AI chose it. Thresholds used: "
              + ", ".join(f"{k} {v}" for k, v in th.items() if k in ("months", "customers", "repeat_share", "materials",
                                                                      "xyz_months_per_item", "ready", "partial")) + ".",
              "",
              f"Reads `{s['dataset']['item']}` joined to `{s['dataset']['header']}` in `{s['source']['schema']}` and writes one table, "
              f"`{s['output_schema']}.{s['output_table']}`. Krusgraph wrote this notebook and ran nothing: you run it, read the ML "
              "experiment and decide. Fabric Data Science does the modelling and tracking (MLflow experiments; AutoML for A7; "
              "Data Wrangler to explore; semantic link to cross-check a semantic model). Libraries that are not installed are "
              "skipped with a printed line."]
    return "\n".join(lines)


def _params(s: dict) -> str:
    th = s["thresholds"]
    extra = {"A7": ["HORIZON = 6                      # months to forecast, and months held out for the backtest",
                    "TIME_BUDGET = 60                 # seconds for AutoML (FLAML) when it is installed"],
             "A8": [f"CLUSTER_MIN_CUSTOMERS = {th['cluster_customers']}       # k-means only from this many customers",
                    "K_RANGE = [3, 4, 5, 6]           # k values tried; the best silhouette is kept"],
             "A3": ["A_SHARE, B_SHARE = 0.8, 0.95     # cumulative revenue share for A and B (a convention: change it)",
                    "X_CV, Y_CV = 0.5, 1.0            # coefficient of variation of monthly quantity for X and Y (a convention)"]}
    lines = [f"SOURCE_SCHEMA = {_py(s['source']['schema'])}        # where the SAP tables are",
             f"SCHEMAS_ENABLED = {s['source']['schemas_enabled']}",
             f"OUTPUT_SCHEMA = {_py(s['output_schema'])}   # the result table goes here, never into the source schema",
             f"OUTPUT_TABLE = {_py(s['output_table'])}",
             f"EXPERIMENT_NAME = {_py(s['experiment'])}   # the ML experiment (MLflow) every run is logged to",
             "DATE_FROM = None                 # 'YYYY-MM-DD' to start later; None: all rows",
             "DATE_TO = None                   # 'YYYY-MM-DD' to stop earlier",
             "CURRENCY = None                  # e.g. 'EUR': only documents in that currency (convert first when there are several)",
             "DOCUMENT_TYPES = None            # e.g. ['F2']: only these document types; None: all",
             f"PLAN_COUNTS = {_py(s['plan_counts'])}   # counted by analysis_plan when the notebook was drafted",
             "TOLERANCE = 0.10                 # stop before modelling when the rows read differ from PLAN_COUNTS by more",
             "WRITE_OUTPUT = True              # False: compute and show, write no table",
             "SEMANTIC_MODEL = None            # a semantic model to cross-check through semantic link (SemPy), or None",
             "SEMANTIC_TABLE = None            # its table that holds the same items",
             'TABLE_FORMAT = "delta"',
             *extra[s["analysis"]]]
    return "\n".join(lines)


def _read(s: dict) -> str:
    ds = s["dataset"]
    f = ds["field_columns"]
    alias = lambda x: ("h" if x["table"] == ds["header"] else "i") + ".`" + x["column"].replace("`", "``") + "`"  # noqa: E731
    cols = {k: alias(f[k]) if f.get(k) else "NULL" for k in ("date", "customer", "material", "amount", "quantity", "currency", "doc_type")}
    doc_cols = [c for c in ds["join"]["target_cols"] if c.upper() not in ("MANDT", "RCLNT", "CLIENT")] if ds["join"] else []
    doc = ("h.`" + doc_cols[-1] + "`") if doc_cols else "NULL"
    if ds["join"]:
        on = " AND ".join(f"i.`{a}` = h.`{b}`" for a, b in zip(ds["join"]["source_cols"], ds["join"]["target_cols"]))
        src = f'{{source({_py(ds["item"])})}} AS i JOIN {{source({_py(ds["header"])})}} AS h ON {on}'
    else:
        src = f'{{source({_py(ds["item"] or ds["header"])})}} AS ' + ("i" if ds["item"] else "h")
    return f'''# Read: the item rows joined to their header by the plan's relationship (the client column in the join), at item
# grain: amounts are summed from the items, never from the header repeated over its items.
from pyspark.sql import functions as F


def q(*parts):
    return ".".join("`" + p.replace("`", "``") + "`" for p in parts)


def source(table):
    return q(SOURCE_SCHEMA, table) if SCHEMAS_ENABLED else q(table)


rows = spark.sql(f"""
SELECT {cols["date"]} AS doc_date, {doc} AS document, {cols["customer"]} AS customer, {cols["material"]} AS material,
       {cols["amount"]} AS amount, {cols["quantity"]} AS quantity, {cols["currency"]} AS currency, {cols["doc_type"]} AS doc_type
FROM {src}
""")
# SAP writes dates as 'YYYYMMDD' text, a lakehouse often as DATE: both become a date; SAP's initial date (00000000) is no date
_text = F.regexp_replace(F.substring(F.col("doc_date").cast("string"), 1, 10), "-", "")
rows = rows.withColumn("doc_date", F.when(_text.rlike("^(19|20)[0-9]{{6}}$"), F.to_date(_text, "yyyyMMdd")))
rows = rows.filter(F.col("doc_date").isNotNull())
if DATE_FROM:
    rows = rows.filter(F.col("doc_date") >= F.to_date(F.lit(DATE_FROM)))
if DATE_TO:
    rows = rows.filter(F.col("doc_date") <= F.to_date(F.lit(DATE_TO)))
if CURRENCY:
    rows = rows.filter(F.col("currency") == CURRENCY)
if DOCUMENT_TYPES:
    rows = rows.filter(F.col("doc_type").isin(DOCUMENT_TYPES))
rows = rows.withColumn("month", F.date_format("doc_date", "yyyy-MM")).cache()
print(rows.count(), "item rows read")'''


CHECK = '''# Data check: the counts analysis_plan used, recounted on the rows read. A difference above TOLERANCE stops the notebook
# before any model is fitted (a filter above, rows landed since, or a different table).
def _filled(c):
    return F.col(c).isNotNull() & (F.trim(F.col(c).cast("string")) != "")


now = rows.agg(F.countDistinct("month").alias("months"), F.countDistinct(F.when(_filled("customer"), F.col("customer"))).alias("customers"),
               F.countDistinct(F.when(_filled("material"), F.col("material"))).alias("materials"), F.count(F.lit(1)).alias("rows")).collect()[0].asDict()
filtered = any(x is not None for x in (DATE_FROM, DATE_TO, CURRENCY, DOCUMENT_TYPES))
for k, planned in PLAN_COUNTS.items():
    got = now.get(k)
    off = abs(got - planned) / max(planned, 1) if planned is not None and got is not None else 0
    print(f"{k:10} at plan time {planned!s:>8}   now {got!s:>8}" + ("   differs" if off > TOLERANCE else ""))
    if off > TOLERANCE and not filtered:
        raise ValueError(f"{k}: {got} now, {planned} when the notebook was drafted (more than {TOLERANCE:.0%} apart). "
                         "Draft the notebook again with analysis_plan, or raise TOLERANCE if the change is expected. Nothing was fitted.")
if SEMANTIC_MODEL and SEMANTIC_TABLE:
    try:
        import sempy.fabric as fabric                     # semantic link (SemPy); the Spark connector is not used
        n = fabric.evaluate_dax(SEMANTIC_MODEL, f"EVALUATE ROW(\\"rows\\", COUNTROWS('{SEMANTIC_TABLE}'))").iloc[0, 0]
        print(f"semantic model {SEMANTIC_MODEL}: {n} rows in {SEMANTIC_TABLE}; {now['rows']} item rows read here")
    except ImportError:
        print("semantic link (sempy) is not installed here: the cross-check with the semantic model was skipped")

# ML experiment: every run below is logged with its parameters, metrics and these input counts.
try:
    import mlflow
    mlflow.set_experiment(EXPERIMENT_NAME)
except ImportError:
    mlflow = None
    print("MLflow is not installed here: runs are not logged (Fabric notebooks include it).")


def log_run(name, params, metrics):
    if mlflow is None:
        print("not logged (no MLflow):", name, metrics)
        return
    with mlflow.start_run(run_name=name):
        mlflow.log_params({**{k: str(v) for k, v in params.items()}, **{f"input_{k}": v for k, v in now.items()}})
        mlflow.log_metrics({k: float(v) for k, v in metrics.items() if v is not None})'''

EXPLORE = '''# Explore: the prepared table. In Fabric, open `analysis_df` in Data Wrangler (the notebook's Data Wrangler button) to
# look at outliers and try your own steps; it writes the pandas code for you.
analysis_df = {frame}
print(analysis_df.describe(include="all").transpose().head(20))'''

A7 = '''# A7 forecasting: monthly revenue, a seasonal naive and an ETS baseline, then AutoML (FLAML), backtested on the last
# HORIZON months. Every model's error is logged to the ML experiment; the baseline stays beside the model.
import math
import pandas as pd

series = analysis_df.set_index("month")["amount"].astype(float)
full = pd.period_range(series.index.min(), series.index.max(), freq="M").strftime("%Y-%m")
series = series.reindex(full, fill_value=0.0)
h = max(1, min(HORIZON, len(series) // 4))
train, test = series.iloc[:-h], series.iloc[-h:]


def errors(pred):
    pred = pd.Series(list(pred), index=test.index, dtype=float)
    mae = float((pred - test).abs().mean())
    mape = float(((pred - test).abs() / test.where(test != 0)).mean() * 100) if (test != 0).any() else None
    return {"mae": mae, "mape": mape}


results = {}
season = 12 if len(train) >= 24 else 1
naive = [train.iloc[-season + (i % season)] if season > 1 else train.iloc[-1] for i in range(h)]
results["seasonal_naive" if season > 1 else "naive"] = (naive, errors(naive))
try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    ets = ExponentialSmoothing(train.values, trend="add", seasonal="add" if season > 1 else None,
                               seasonal_periods=12 if season > 1 else None).fit()
    results["ets"] = (list(ets.forecast(h)), errors(ets.forecast(h)))
except ImportError:
    print("statsmodels is not installed here: the ETS baseline was skipped")
try:
    from flaml import AutoML                               # AutoML in pandas mode, so the model's signature is logged
    automl = AutoML()
    frame = pd.DataFrame({"ds": pd.to_datetime(train.index), "y": train.values})
    automl.fit(dataframe=frame, label="y", task="ts_forecast", period=h, time_budget=TIME_BUDGET, verbose=0)
    pred = automl.predict(pd.DataFrame({"ds": pd.to_datetime(test.index)}))
    results["automl_" + str(automl.best_estimator)] = (list(pred), errors(pred))
except ImportError:
    print("FLAML (AutoML) is not installed here: the AutoML forecast was skipped")
for name, (pred, err) in results.items():
    print(f"{name:24} MAE {err['mae']:.2f}" + (f"   MAPE {err['mape']:.1f} %" if err["mape"] is not None else ""))
    log_run(name, {"analysis": "A7", "horizon": h, "months": len(series)}, err)
best = min(results, key=lambda k: results[k][1]["mae"])
print("lowest backtest error:", best, "(the baseline is kept beside it)")
out = pd.DataFrame({"month": list(test.index), "actual": list(test.values), "kind": "backtest"})
for name, (pred, _) in results.items():
    out[name] = list(pred)
future = pd.period_range(pd.Period(series.index[-1], "M") + 1, periods=h, freq="M").strftime("%Y-%m")
ahead = [series.iloc[-season + (i % season)] if season > 1 else series.iloc[-1] for i in range(h)]
result_df = pd.concat([out, pd.DataFrame({"month": list(future), "actual": [None] * h, "kind": "forecast",
                                          ("seasonal_naive" if season > 1 else "naive"): ahead})], ignore_index=True)
print(result_df)'''

A8 = '''# A8 RFM: recency (days since the last document), frequency (documents), monetary (amount) per customer, each scored
# 1-5 by quintile; named segments; k-means on R, F and M when there are enough customers. Logged to the ML experiment.
import pandas as pd

rfm = analysis_df.copy()
rfm["recency_days"] = (pd.to_datetime(rfm["last_date"]).max() - pd.to_datetime(rfm["last_date"])).dt.days


def quintile(s, ascending=True):
    if s.nunique() < 5:
        return pd.Series(3, index=s.index)
    r = s.rank(method="first", ascending=ascending)
    return pd.qcut(r, 5, labels=[1, 2, 3, 4, 5]).astype(int)


rfm["R"] = quintile(rfm["recency_days"], ascending=False)    # recent buyers score 5
rfm["F"] = quintile(rfm["frequency"])
rfm["M"] = quintile(rfm["monetary"])


def segment(r):
    if r.R >= 4 and r.F >= 4 and r.M >= 4:
        return "Champions"
    if r.R >= 3 and r.F >= 4:
        return "Loyal"
    if r.R >= 4 and r.F <= 2:
        return "New or occasional"
    if r.R <= 2 and r.F >= 3:
        return "At risk"
    if r.R == 1:
        return "Lost"
    return "Regular"


rfm["segment"] = rfm.apply(segment, axis=1)
summary = rfm.groupby("segment").agg(customers=("customer", "count"), revenue=("monetary", "sum")).sort_values("revenue", ascending=False)
print(summary)
log_run("rfm_quintiles", {"analysis": "A8", "customers": len(rfm)},
        {f"share_{k.lower().replace(' ', '_')}": v / len(rfm) for k, v in rfm["segment"].value_counts().items()})
rfm["cluster"] = None
if len(rfm) >= CLUSTER_MIN_CUSTOMERS:
    try:
        import numpy as np
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score
        from sklearn.preprocessing import StandardScaler
        X = StandardScaler().fit_transform(np.log1p(rfm[["recency_days", "frequency", "monetary"]].astype(float)))
        best = None
        for k in K_RANGE:
            labels = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(X)
            score = silhouette_score(X, labels)
            log_run(f"kmeans_k{k}", {"analysis": "A8", "k": k}, {"silhouette": score})
            if best is None or score > best[0]:
                best = (score, k, labels)
        rfm["cluster"] = best[2]
        print(f"k-means: k = {best[1]} has the best silhouette ({best[0]:.3f}); compare the clusters with the segments")
    except ImportError:
        print("scikit-learn is not installed here: k-means was skipped")
else:
    print(f"k-means not run: {len(rfm)} customers, fewer than CLUSTER_MIN_CUSTOMERS ({CLUSTER_MIN_CUSTOMERS})")
result_df = rfm[["customer", "last_date", "recency_days", "frequency", "monetary", "R", "F", "M", "segment", "cluster"]]'''

A3 = '''# A3 ABC/XYZ: ABC by cumulative share of revenue, XYZ by the coefficient of variation of monthly quantity over the
# months in the data (a month without sales counts as 0). Cut-offs are parameters: they are conventions, not rules.
import pandas as pd

months = sorted(analysis_df["month"].unique())
grid = analysis_df.pivot_table(index="material", columns="month", values="quantity", aggfunc="sum", fill_value=0).reindex(columns=months, fill_value=0)
value = analysis_df.groupby("material")["amount"].sum().sort_values(ascending=False)
share = value.cumsum() / value.sum()
abc = share.apply(lambda s: "A" if s <= A_SHARE else ("B" if s <= B_SHARE else "C"))
abc.iloc[0] = "A"                                            # the largest material is A even when it alone passes A_SHARE
mean, std = grid.mean(axis=1), grid.std(axis=1, ddof=0)
cv = (std / mean.where(mean > 0)).reindex(value.index)
xyz = cv.apply(lambda c: "Z" if pd.isna(c) or c > Y_CV else ("Y" if c > X_CV else "X"))
result_df = pd.DataFrame({"material": value.index, "revenue": value.values, "revenue_share_cum": share.values,
                          "abc": abc.values, "cv_monthly_quantity": cv.values, "xyz": xyz.values,
                          "months_with_sales": (grid.reindex(value.index) > 0).sum(axis=1).values})
result_df["class"] = result_df["abc"] + result_df["xyz"]
matrix = result_df.pivot_table(index="abc", columns="xyz", values="material", aggfunc="count", fill_value=0)
print(matrix)
print("A/Z materials (high value, erratic demand):", list(result_df.loc[result_df["class"] == "AZ", "material"].head(20)))
log_run("abc_xyz", {"analysis": "A3", "a_share": A_SHARE, "b_share": B_SHARE, "x_cv": X_CV, "y_cv": Y_CV, "months": len(months)},
        {f"count_{k}": int(v) for k, v in result_df["class"].value_counts().items()})'''

FRAMES = {
    "A7": 'rows.groupBy("month").agg(F.sum("amount").cast("double").alias("amount"), F.sum("quantity").cast("double").alias("quantity"), F.countDistinct("document").alias("documents")).orderBy("month").toPandas()',
    "A8": 'rows.filter(_filled("customer")).groupBy("customer").agg(F.max("doc_date").alias("last_date"), F.countDistinct("document").alias("frequency"), F.sum("amount").cast("double").alias("monetary")).toPandas()',
    "A3": 'rows.filter(_filled("material")).groupBy("material", "month").agg(F.sum("amount").cast("double").alias("amount"), F.sum("quantity").cast("double").alias("quantity")).toPandas()',
}

WRITE = '''# Output: one Delta table in OUTPUT_SCHEMA, marked as written by this notebook (table property {mark}); a table of the
# same name without that mark is never replaced.
OWNER = {owner}
name = q(OUTPUT_SCHEMA, OUTPUT_TABLE) if SCHEMAS_ENABLED else q(OUTPUT_SCHEMA + "_" + OUTPUT_TABLE)


def ours_or_absent(name):
    if not spark.catalog.tableExists(name):
        return True
    props = {{r[0]: r[1] for r in spark.sql(f"SHOW TBLPROPERTIES {{name}}").collect()}}
    return props.get("{mark}") == OWNER


if not WRITE_OUTPUT:
    print("WRITE_OUTPUT = False: nothing was written")
elif not ours_or_absent(name):
    raise ValueError(f"{{name}} exists and was not written by this notebook; nothing was written. Choose another OUTPUT_SCHEMA.")
else:
    if SCHEMAS_ENABLED:
        spark.sql(f"CREATE SCHEMA IF NOT EXISTS {{q(OUTPUT_SCHEMA)}}")
    import pandas as pd
    from pyspark.sql.types import DoubleType, StringType, StructField, StructType
    fields, cols = [], []
    for c in result_df.columns:                 # numbers as double, everything else as text; NaN and None as NULL
        number = pd.api.types.is_numeric_dtype(result_df[c]) and not pd.api.types.is_bool_dtype(result_df[c])
        fields.append(StructField(str(c), DoubleType() if number else StringType(), True))
        cols.append([None if v is None or (isinstance(v, float) and v != v) else (float(v) if number else str(v))
                     for v in result_df[c].tolist()])
    out_df = spark.createDataFrame(list(zip(*cols)), StructType(fields))
    out_df.write.format(TABLE_FORMAT).mode("overwrite").option("overwriteSchema", "true").saveAsTable(name)
    spark.sql(f"ALTER TABLE {{name}} SET TBLPROPERTIES ('{mark}' = '{{OWNER}}')")
    print(name, spark.read.table(name).count(), "rows written")'''

NEXT = {
    "A7": '''# Next (commented out: you decide). Register the model you trust and score it monthly with Fabric's PREDICT:
# mlflow.register_model(f"runs:/{run_id}/model", "krusgraph_a7_forecast")
# from synapse.ml.predict import MLFlowTransformer
# scored = MLFlowTransformer(inputCols=["ds"], outputCol="forecast", modelName="krusgraph_a7_forecast", modelVersion=1).transform(df)
# Add OUTPUT_SCHEMA.OUTPUT_TABLE to the semantic model to show the forecast beside the actuals in Power BI.''',
    "A8": '''# Next (commented out: you decide). Track segment movement month to month by running this notebook monthly (a pipeline
# can set DATE_TO), and add OUTPUT_SCHEMA.OUTPUT_TABLE to the semantic model by customer.''',
    "A3": '''# Next (commented out: you decide). Review the A/Z materials with planning; change A_SHARE / X_CV in the parameters cell
# and run again (each run is logged), then add OUTPUT_SCHEMA.OUTPUT_TABLE to the semantic model by material.''',
}


def cells(s: dict) -> list[tuple[str, str]]:
    a = s["analysis"]
    return [("markdown", _intro(s)), ("parameters", _params(s)), ("code", _read(s)), ("code", CHECK),
            ("code", EXPLORE.format(frame=FRAMES[a])), ("code", {"A7": A7, "A8": A8, "A3": A3}[a]),
            ("code", WRITE.format(mark=MARK, owner=_py(s["owner"]))), ("code", NEXT[a])]


def notebook_source(s: dict) -> str:
    src = s["source"]
    return _nb.fabric_source(cells(s), _nb.notebook_metadata(src["workspace_id"], src["item_id"], src["item_name"]))


def ipynb(s: dict) -> dict:
    from .sap_demo36 import ipynb as _ipynb
    return _ipynb(cells(s))


def draft(result: dict, analysis: str, info: dict, output_schema: str = "krusgraph_analysis") -> dict:
    """The tools' answer: the reason, the steps and the notebook source; creates nothing, runs nothing."""
    s = spec(result, analysis, info, output_schema)
    return {"summary": f"{s['analysis']} {s['name']} ({s['readiness']}): a notebook that reads {s['dataset']['item']} + "
                       f"{s['dataset']['header']} and writes {s['output_schema']}.{s['output_table']}; nothing was created or run",
            "analysis": s["analysis"], "readiness": s["readiness"], "because": s["because"], "caveats": s["caveats"],
            "plan_counts": s["plan_counts"],
            "steps": ["read the item rows joined to their header (client column in the join), item grain",
                      "data check: the plan's counts recounted; stops before modelling when they differ by more than TOLERANCE",
                      "explore: the prepared table (open it in Data Wrangler)",
                      {"A7": "seasonal naive and ETS baselines, AutoML (FLAML) forecast; backtest on the last months; each run in the ML experiment",
                       "A8": "R, F, M quintile scores and named segments; k-means when there are enough customers; logged to the ML experiment",
                       "A3": "ABC by cumulative revenue share, XYZ by coefficient of variation of monthly quantity; logged to the ML experiment"}[s["analysis"]],
                      f"write {s['output_schema']}.{s['output_table']} (marked {MARK}; never replaces a table it did not write)"],
            "notebook": {"path": "notebook-content.py", "format": "fabricGitSource", "content": notebook_source(s)},
            "run": ["In Fabric: import the notebook (or paste the cells), attach it to the lakehouse that holds the tables, and run "
                    "it yourself. Krusgraph created nothing and ran nothing on your data.",
                    f"Runs are logged to the ML experiment {s['experiment']}; MLflow, statsmodels, scikit-learn and FLAML are "
                    "part of Fabric's runtime, and a missing one is skipped with a printed line."],
            "note": "Unit-tested; the notebook's cells ran on a local PySpark 4.0.1 against the synthetic SAP demo (MLflow, "
                    "AutoML and scikit-learn absent there, so skipped); not yet run in Fabric."}
