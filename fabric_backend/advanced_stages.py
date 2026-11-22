"""From the feature table to a model and to predictions in gold: the three stages of Advanced analytics (round AA1).

Gustav, 21 November 2026: the Data Science starter (WB10, nextSteps.ts featureCells) ran in Fabric for the first time,
wrote the feature table (one row per order) and an ML experiment with one run. The next step goes from that table to a
model and to predictions that land in gold and in the semantic model. Three stages per recommended analysis:

    1. Feature table          the WB10 starter (unchanged): items summed per order first, one row per order
    2. Model                  a notebook that trains one simple, explainable baseline, logs it to the workspace's ML
                              experiment (MLflow autologging) and registers it as an ML model item
    3. Predictions in gold    a notebook that scores with the registered model (Fabric's PREDICT) and writes a gold
                              table with the model's version and run id on every row

The analyses (each recommended by a fixed rule below, never by AI):

    forecast   weekly number of orders: a seasonal naive baseline and one regression (scikit-learn LinearRegression on
               the week's trend and season), backtested on the last HORIZON weeks; the regression is registered
    segments   customers by recency, frequency and value (RFM) from the proven customer link: k-means, k chosen by the
               stated rule (the best silhouette over K_RANGE; within K_TIE of the best, the smaller k)
    drivers    the top 10 customers and the top 10 values of each low-cardinality text column by share of orders and of
               value: descriptive, no model, so it has no third stage

Deterministic code generation: Krusgraph writes the notebooks from the keys and links proven on the rows and never runs
them, trains nothing and reads no metric. The person runs them in Fabric. Every cell is a template (TEMPLATES) filled
from a few values (values()); the editor fills the same templates in TypeScript (advancedStages.generated.ts, written by
write_generated() and checked by tests/test_aa1_advanced_stages.py), so the notebook a person downloads or creates is
the one these tests ran. The CORE cell is plain pandas, numpy and scikit-learn (no Spark), and the tests run it on the
synthetic SAP demo (sap_demo36) and the shop sample.

Documented Fabric features used (Microsoft Learn, read 22 November 2026):
  - Autologging, mlflow.autolog(exclusive=False) for custom metrics: learn.microsoft.com/fabric/data-science/mlflow-autologging
    (ms.date 2026-05-15)
  - Model scoring with PREDICT, synapse.ml.predict.MLFlowTransformer; supported flavors include Sklearn; the model
    must be saved in MLflow format with its signature: learn.microsoft.com/fabric/data-science/model-scoring-predict
    (ms.date 2026-02-28). Where synapse.ml is not importable, the notebook scores with mlflow.pyfunc.spark_udf instead
    and says so in the scored_with column.
  - ML experiments and ML models (a registered model is an ML model item in the workspace):
    learn.microsoft.com/fabric/data-science/machine-learning-experiment and .../machine-learning-model
  - The Fabric REST API for ML experiments has Create, Delete, Get, List and Update of the item only, no runs and no
    metrics (learn.microsoft.com/rest/api/fabric/mlexperiment/items), so the editor shows "Open the experiment"
    instead of reading metrics (docs/ADVANCED-ANALYTICS.md says what reading them would need).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ANALYSES = ("forecast", "segments", "drivers")
STAGES = ("features", "model", "predictions")

# The stated thresholds. Below MIN_ORDERS no model is trained: the shop sample (60 orders) says so once, and its feature
# table is still useful. The rest are per analysis.
MIN_ORDERS = 200
MIN_WEEKS = 30
MIN_CUSTOMERS = 30
HORIZON = 8
K_RANGE = (2, 3, 4, 5, 6)
K_TIE = 0.01
PREDICTION_MARK = "krusgraph.prediction"
TOO_FEW = "Too few rows for a model ({n} orders; a model starts at {min} orders). The feature table is still useful: it has one row per order, so its totals are not doubled."

LEARN = {
    "autolog": "https://learn.microsoft.com/fabric/data-science/mlflow-autologging",
    "predict": "https://learn.microsoft.com/fabric/data-science/model-scoring-predict",
    "experiment": "https://learn.microsoft.com/fabric/data-science/machine-learning-experiment",
    "model": "https://learn.microsoft.com/fabric/data-science/machine-learning-model",
    "sklearn": "https://learn.microsoft.com/fabric/data-science/train-models-scikit-learn",
}

TITLES = {"forecast": "Weekly orders forecast", "segments": "Customer segments", "drivers": "Top 10 drivers"}
CUSTOMER_WORDS = re.compile(r"(cust|kunde|kna1|client|buyer|account|partner)", re.I)


def ident(s: str) -> str:
    """nextSteps.ts ident(): a name Spark and Fabric accept, lower case."""
    out = re.sub(r"[^A-Za-z0-9_]+", "_", s)
    out = re.sub(r"^(\d)", r"_\1", out)
    return out.lower()


# ------------------------------------------------------------------ the frame and the rules --------------------------

def customer_link(grain: dict, links: list[dict]) -> dict | None:
    """The proven link from the order table to a customer table: the first (by target, then column) whose target's name
    reads as a customer; None when there is none, and segmentation is then not recommended."""
    mine = [l for l in links if l.get("source") == grain["parent"] and len(l.get("columns") or []) >= 1]
    hits = sorted((l for l in mine if CUSTOMER_WORDS.search(l.get("target") or "")),
                  key=lambda l: (l["target"].lower(), [c.lower() for c in l["columns"]]))
    if not hits:
        return None
    l = hits[0]
    cols = [c for c in l["columns"] if c.upper() not in ("MANDT", "RCLNT", "CLIENT")] or l["columns"]
    tall = l.get("target_columns") or l["columns"]
    # one column: the key's own name; several (SAP's client + customer): the combined key column gold relates on
    # (combined_keys.py: the target's key columns joined by _ plus _key, the values joined by U+001F)
    key = tall[0] if len(tall) == 1 else "_".join(tall) + "_key"
    return {"table": l["target"], "column": cols[-1], "key": key, "parts": list(l["columns"])}


def values(grain: dict, source: dict, customer: dict | None) -> dict:
    """The few values every template is filled with. `grain` has nextSteps.ts Grain's fields (child, parent,
    childColumns, parentColumns, childIds, parentRows); `source` {name, schema}; `customer` customer_link()'s answer."""
    parent, child = grain["parent"], grain["child"]
    ids = sorted({*grain.get("parentColumns", []), *grain.get("childIds", []), *grain.get("childColumns", [])}
                 | ({customer["column"]} if customer else set()))
    stem = ident(parent)
    return {
        "source": f"{source.get('name') or 'the lakehouse'}" + (f" / {source['schema']}" if source.get("schema") else ""),
        "parent": parent, "child": child,
        "feature_table": ident(f"{parent}_features"),
        "order_key": list(grain["parentColumns"]),
        "ids": ids,
        "child_prefix": ident(child),
        "customer": customer["column"] if customer else None,
        "customer_table": customer["table"] if customer else None,
        "customer_key": customer["key"] if customer else None,
        "customer_parts": customer["parts"] if customer else [],
        "experiment": ident(f"{parent}_experiment"),
        "schemas_enabled": bool(source.get("schema")),
        "gold_schema": "gold",
        "orders": int(grain.get("parentRows") or 0),
        "forecast_model": f"{stem}_weekly_forecast", "forecast_table": f"{stem}_forecast",
        "segments_model": f"{stem}_customer_segments", "segments_table": "customer_segment",
        "drivers_table": f"{stem}_top10",
    }


def recommend(v: dict) -> list[dict]:
    """The analyses the rules recommend on this frame, each with why and whether there are rows enough for a model.
    Drivers needs no model and is always offered; segments needs a proven link to a customer table."""
    few = v["orders"] < MIN_ORDERS
    too_few = TOO_FEW.format(n=v["orders"], min=MIN_ORDERS) if few else ""
    out = [{"analysis": "forecast", "title": TITLES["forecast"],
            "why": f"One row per {v['parent']} with its date: the number of {v['parent']} per week is a series to forecast.",
            "model": not few, "too_few": too_few, "gold_table": f"{v['gold_schema']}.{v['forecast_table']}",
            "model_name": v["forecast_model"]}]
    if v["customer"]:
        out.append({"analysis": "segments", "title": TITLES["segments"],
                    "why": f"{v['parent']}.{v['customer']} -> {v['customer_table']} is proven: recency, frequency and value per "
                           "customer come from the proven key, one row per order.",
                    "model": not few, "too_few": too_few, "gold_table": f"{v['gold_schema']}.{v['segments_table']}",
                    "model_name": v["segments_model"]})
    out.append({"analysis": "drivers", "title": TITLES["drivers"],
                "why": f"Which customers and which values of {v['parent']}'s text columns carry most orders and most value: "
                       "descriptive, no model.",
                "model": False, "too_few": "", "gold_table": f"{v['gold_schema']}.{v['drivers_table']}", "model_name": None})
    return out


# ------------------------------------------------------------------ the templates ------------------------------------
# {{name}} is replaced by the value as a Python literal (code), [[name]] by the value as plain text (comments, prose).

HEADER = '''# Krusgraph, [[stage_title]]: [[title]] on [[feature_table]] ([[source]]).
# Written by rules from the keys and links Krusgraph proved on the rows, no AI. Krusgraph does not run this notebook,
# trains no model and reads none of your rows or metrics: you run it in Fabric, and the numbers are your own run's.
# The three stages: 1. feature table (one row per [[parent]]) -> 2. model (logged to the ML experiment, registered as an
# ML model) -> 3. predictions in gold (scored with the registered model, version and run id on every row).
# Fabric features used (Microsoft Learn): autologging [[learn_autolog]] ; PREDICT [[learn_predict]]'''

PARAMS = '''# Parameters: change them here, not below.
P = {
    "feature_table": {{feature_table}},      # stage 1's table: one row per [[parent]]
    "order_key": {{order_key}},              # its proven key
    "ids": {{ids}},                          # keys and links: never summed, never a feature
    "child_prefix": {{child_prefix}},        # the feature columns summed from [[child]] start with this
    "customer": {{customer}},                # the proven link to [[customer_table]], or None
    "customer_key": {{customer_key}},        # the key it points at: the prediction table's column of that name
    "customer_parts": {{customer_parts}},    # the link's columns: several are combined as gold's key column is
    "experiment": {{experiment}},            # the ML experiment in this workspace (MLflow)
    "model_name": {{model_name}},            # the registered ML model
    "gold_schema": {{gold_schema}},
    "gold_table": {{gold_table}},
    "schemas_enabled": {{schemas_enabled}},
    "date": None,                            # None: the rule in CORE picks the date column; or name it
    "value": None,                           # None: the rule in CORE picks the value column; or name it
    "min_orders": {{min_orders}}, "min_weeks": {{min_weeks}}, "min_customers": {{min_customers}},
    "horizon": {{horizon}},                  # weeks held out for the backtest, and weeks forecast
    "k_range": {{k_range}}, "k_tie": {{k_tie}},  # k-means: the best silhouette over k_range; within k_tie, the smaller k
}'''

CORE = r'''# CORE: plain pandas, numpy and scikit-learn, no Spark, so the same functions run anywhere (Krusgraph's tests run them
# on synthetic data). Every choice below is a stated rule, never a guess.
import re
import numpy as np
import pandas as pd

AMOUNT = re.compile(r"(amount|total|revenue|value|sales|netwr|wrbtr|dmbtr|kwert)", re.I)
QUANTITY = re.compile(r"(qty|quantity|kwmeng|fkimg|lfimg|menge|units)", re.I)
DATE_NAME = re.compile(r"(date|datum|dat|_at|time|day)$", re.I)
FORECAST_INPUTS = ["t", "woy_sin", "woy_cos"]
SEGMENT_INPUTS = ["recency_log", "frequency_log", "monetary_log"]


def check_grain(df, key):
    """One row per order, or stop: a repeated key would double every total summed over it."""
    dup = int(df.duplicated(subset=key).sum())
    if dup:
        raise ValueError(f"{dup} repeated {'+'.join(key)} in the feature table: it is not one row per order, so totals "
                         "would be doubled. Run stage 1 (the feature table) again; nothing was trained.")
    return len(df)


def as_dates(s):
    """A column as dates: dates and timestamps as they are, 'YYYYMMDD' text (SAP) parsed, SAP's 00000000 no date."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return pd.to_datetime(s).dt.tz_localize(None) if getattr(s.dt, "tz", None) else pd.to_datetime(s)
    text = s.astype("string").str.strip().str.slice(0, 10)
    eight = text.str.fullmatch(r"(19|20)\d{6}").fillna(False)
    if eight.any() and eight[text.notna() & (text != "")].mean() >= 0.95:
        return pd.to_datetime(text.where(eight), format="%Y%m%d", errors="coerce")
    return pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")


def customer_column(df, parts):
    """The customer as gold's dimension holds its key: one column as it is; several (SAP's client and customer) joined by
    U+001F, as gold's combined key column is, and no customer where a part is empty."""
    if len(parts) == 1:
        return parts[0]
    text = [df[c].astype("string").str.strip() for c in parts]
    empty = pd.concat([t.isna() | (t == "") for t in text], axis=1).any(axis=1)
    joined = text[0]
    for t in text[1:]:
        joined = joined + "\x1f" + t
    df["_customer"] = joined.where(~empty, None)
    return "_customer"


def pick_date(df, ids):
    """The rule: the first column of a date type; else the first text column whose name ends like a date and whose
    filled values are at least 95 % dates. None when there is none (then no forecast and no recency)."""
    import datetime as _dt
    for c in df.columns:
        if c in ids:
            continue
        s = df[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            return c
        filled = s.dropna()
        if len(filled) and filled.map(lambda x: isinstance(x, (_dt.date, pd.Timestamp))).all():
            return c
    for c in df.columns:
        if c in ids or not DATE_NAME.search(str(c)) or pd.api.types.is_numeric_dtype(df[c]):
            continue
        filled = df[c].dropna().astype("string").str.strip()
        filled = filled[filled != ""]
        if len(filled) and as_dates(filled).notna().mean() >= 0.95:
            return c
    return None


def pick_value(df, child_prefix, ids):
    """The rule, in this order: an amount summed from the items (stage 1's <items>_<column>_sum), the order's own
    amount, a quantity summed from the items, the number of item rows. Returns (column, what it is)."""
    numeric = [c for c in df.columns if c not in ids and pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    summed = [c for c in numeric if c.startswith(child_prefix + "_") and c.endswith("_sum")]
    own = [c for c in numeric if c not in summed and c != child_prefix + "_rows"]
    for cols, what in ((summed, "amount summed from the items"), (own, "the order's own amount")):
        hit = next((c for c in cols if AMOUNT.search(c)), None)
        if hit:
            return hit, what
    hit = next((c for c in summed if QUANTITY.search(c)), None)
    if hit:
        return hit, "quantity summed from the items"
    if child_prefix + "_rows" in df.columns:
        return child_prefix + "_rows", "number of item rows"
    return None, "no value column"


def enough(n_orders, P, n_weeks=None, n_customers=None):
    """(True, '') when there are rows enough for a model, else (False, the one sentence that says why)."""
    if n_orders < P["min_orders"]:
        return False, (f"Too few rows for a model ({n_orders} orders; a model starts at {P['min_orders']} orders). The feature "
                       "table is still useful: it has one row per order, so its totals are not doubled.")
    if n_weeks is not None and n_weeks < P["min_weeks"]:
        return False, f"Too few weeks for a forecast ({n_weeks}; it starts at {P['min_weeks']}). The feature table is still useful."
    if n_customers is not None and n_customers < P["min_customers"]:
        return False, f"Too few customers for segments ({n_customers}; they start at {P['min_customers']}). The feature table is still useful."
    return True, ""


# ---- forecast: orders per week
def weekly_orders(df, date_col):
    """Orders per week (weeks start on Monday), every week from the first to the last, 0 where there were none."""
    d = as_dates(df[date_col]).dropna()
    week = (d - pd.to_timedelta(d.dt.weekday, unit="D")).dt.normalize()
    counts = week.value_counts().sort_index()
    full = pd.date_range(counts.index.min(), counts.index.max(), freq="7D")
    return counts.reindex(full, fill_value=0).astype(float).rename("orders")


def forecast_inputs(weeks, first):
    """The model's inputs: the trend (weeks since the first week) and the season (week of the year as sine and cosine)."""
    weeks = pd.DatetimeIndex(weeks)
    woy = weeks.isocalendar().week.astype(float).to_numpy()
    return pd.DataFrame({"t": ((weeks - pd.Timestamp(first)).days / 7.0).astype(float),
                         "woy_sin": np.sin(2 * np.pi * woy / 52.18), "woy_cos": np.cos(2 * np.pi * woy / 52.18)})


def seasonal_naive(history, steps):
    """The baseline: the same week a year (52 weeks) earlier when there is a year of history, else the last week."""
    h = list(history)
    if len(h) >= 52:
        return [h[len(h) - 52 + (i % 52)] for i in range(steps)], "seasonal naive (52 weeks)"
    return [h[-1]] * steps, "naive (last week)"


def fit_forecast(series):
    from sklearn.linear_model import LinearRegression
    X = forecast_inputs(series.index, series.index[0])
    return LinearRegression().fit(X, series.to_numpy())


def backtest(series, horizon):
    """Both models fitted without the last `horizon` weeks and compared with them: mean absolute error in orders per
    week. The baseline is always kept beside the regression."""
    h = max(1, min(int(horizon), len(series) // 4))
    train, test = series.iloc[:-h], series.iloc[-h:]
    naive, naive_kind = seasonal_naive(train, h)
    reg = fit_forecast(train)
    pred = np.clip(reg.predict(forecast_inputs(test.index, series.index[0])), 0, None)
    mae = lambda p: float(np.mean(np.abs(np.asarray(p, dtype=float) - test.to_numpy())))
    m = {"mae_regression": mae(pred), "mae_baseline": mae(naive), "weeks_held_out": float(h),
         "weeks_of_history": float(len(series)), "mean_orders_per_week": float(series.mean())}
    m["mae_regression_vs_baseline"] = m["mae_regression"] / m["mae_baseline"] if m["mae_baseline"] else float("nan")
    return {"metrics": m, "baseline": naive_kind, "test": test, "regression": pred, "naive": naive}


def future_frame(series, horizon):
    """The weeks to forecast, after the last week of the data, with the model's inputs and the baseline beside them."""
    weeks = pd.date_range(series.index[-1] + pd.Timedelta(days=7), periods=int(horizon), freq="7D")
    out = forecast_inputs(weeks, series.index[0])
    out.insert(0, "week_start", weeks)
    out["baseline_orders"], _ = seasonal_naive(series, int(horizon))
    return out


# ---- segments: recency, frequency and value per customer
def rfm(df, customer, date_col, value_col, key):
    """One row per customer from the order rows: days since the last order (against the last date in the data), number
    of orders (distinct keys) and value (sum of the value column). The order table is already one row per order."""
    d = df.assign(_date=as_dates(df[date_col]), _value=(df[value_col].astype(float) if value_col else 1.0),
                  _order=df[key].astype(str).agg("|".join, axis=1))
    d = d[d[customer].notna() & (d[customer].astype(str).str.strip() != "") & d["_date"].notna()]
    g = d.groupby(d[customer].astype(str)).agg(last_date=("_date", "max"), frequency=("_order", "nunique"), monetary=("_value", "sum"))
    g["recency_days"] = (d["_date"].max() - g["last_date"]).dt.days.astype(float)
    g["frequency"] = g["frequency"].astype(float)
    g["monetary"] = g["monetary"].astype(float)
    g = g.reset_index().rename(columns={customer: "customer"})
    return segment_inputs(g)


def segment_inputs(g):
    g = g.copy()
    g["recency_log"] = np.log1p(g["recency_days"].clip(lower=0))
    g["frequency_log"] = np.log1p(g["frequency"].clip(lower=0))
    g["monetary_log"] = np.log1p(g["monetary"].clip(lower=0))
    return g


def segment_pipeline(k):
    from sklearn.cluster import KMeans
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return make_pipeline(StandardScaler(), KMeans(n_clusters=int(k), n_init=10, random_state=0))


def choose_k(X, k_range, k_tie):
    """The rule: fit k-means for every k in k_range and keep the best silhouette; a smaller k within k_tie of the best
    wins (fewer segments are easier to explain). Returns (k, {k: silhouette})."""
    from sklearn.metrics import silhouette_score
    scores = {}
    for k in k_range:
        if k >= len(X):
            continue
        p = segment_pipeline(k).fit(X)
        scores[int(k)] = float(silhouette_score(p[:-1].transform(X), p[-1].labels_))
    best = max(scores.values())
    return min(k for k, s in scores.items() if s >= best - k_tie), scores


def segment_names(g):
    """A name per cluster from its averages, ranked by mean value: 'Segment 1 of 4: recent, frequent, high value'. The
    words compare each cluster's median with the median of all customers."""
    med = g[["recency_days", "frequency", "monetary"]].median()
    stats = g.groupby("cluster")[["recency_days", "frequency", "monetary"]].median()
    order = list(g.groupby("cluster")["monetary"].mean().sort_values(ascending=False).index)
    names = {}
    for rank, c in enumerate(order, 1):
        s = stats.loc[c]
        words = ["recent" if s["recency_days"] <= med["recency_days"] else "lapsed",
                 "frequent" if s["frequency"] >= med["frequency"] else "occasional",
                 "high value" if s["monetary"] >= med["monetary"] else "low value"]
        names[c] = f"Segment {rank} of {len(order)}: {', '.join(words)}"
    return g["cluster"].map(names)


# ---- drivers: the top 10, descriptive
def top10(df, ids, customer, value_col, date_col=None):
    """For the customer column and every text column with 2 to 50 values (no key, no date): its top 10 values by share
    of orders, with their share of value. Shares of all orders, so a top 10 never adds up to more than 100 %."""
    dims = ([customer] if customer else []) + [c for c in df.columns if c not in ids and c != date_col and c != customer
                                               and not pd.api.types.is_numeric_dtype(df[c]) and 2 <= df[c].nunique() <= 50]
    n, total = len(df), float(df[value_col].astype(float).sum()) if value_col else 0.0
    rows = []
    for c in dims:
        g = df.groupby(df[c].astype("string").fillna("(empty)")).agg(orders=(c, "size"), **({"value": (value_col, "sum")} if value_col else {}))
        g = g.sort_values(["orders"] + (["value"] if value_col else []), ascending=False).head(10)
        for rank, (val, r) in enumerate(g.iterrows(), 1):
            rows.append({"dimension": c, "rank": rank, "dimension_value": str(val), "orders": int(r["orders"]),
                         "share_of_orders": r["orders"] / n if n else None,
                         "value": float(r["value"]) if value_col else None,
                         "share_of_value": (float(r["value"]) / total if value_col and total else None)})
    return pd.DataFrame(rows, columns=["dimension", "rank", "dimension_value", "orders", "share_of_orders", "value", "share_of_value"])'''

READ = '''# Read stage 1's feature table and check its grain before anything else: one row per [[parent]].
pdf = spark.read.table(P["feature_table"]).toPandas()
n_orders = check_grain(pdf, P["order_key"])
DATE = P["date"] or pick_date(pdf, P["ids"])
VALUE, VALUE_IS = (P["value"], "named in P") if P["value"] else pick_value(pdf, P["child_prefix"], P["ids"])
CUSTOMER = customer_column(pdf, P["customer_parts"]) if P["customer"] else None
print(f"{P['feature_table']}: {n_orders} rows, one per {'+'.join(P['order_key'])}; date column {DATE}; value column {VALUE} ({VALUE_IS})")'''

MLFLOW = '''import mlflow
from mlflow.models.signature import infer_signature
mlflow.autolog(exclusive=False)          # Fabric turns autologging on; exclusive=False adds our own metrics (Learn)
mlflow.set_experiment(P["experiment"])   # the ML experiment item in this workspace'''

TRAIN = {
    "forecast": MLFLOW + '''
weekly = weekly_orders(pdf, DATE) if DATE else None
ok, why = enough(n_orders, P, n_weeks=len(weekly) if weekly is not None else 0)
if not DATE:
    ok, why = False, "No date column in the feature table, so there is no series to forecast."
if not ok:
    print(why)
else:
    bt = backtest(weekly, P["horizon"])
    with mlflow.start_run(run_name="weekly orders forecast") as run:
        mlflow.log_params({"target": "orders per week", "baseline": bt["baseline"], "model": "LinearRegression(trend, week of year)",
                           "horizon_weeks": P["horizon"], "feature_table": P["feature_table"], "date_column": DATE})
        mlflow.log_metrics(bt["metrics"])
        model = fit_forecast(weekly)                       # refitted on all weeks for the predictions
        X = forecast_inputs(weekly.index, weekly.index[0])
        mlflow.sklearn.log_model(model, "krusgraph_model", signature=infer_signature(X, model.predict(X)),
                                 registered_model_name=P["model_name"])
    print(pd.DataFrame({"week": bt["test"].index.date, "actual": bt["test"].values, "baseline": bt["naive"], "regression": bt["regression"].round(1)}))
    print({k: round(v, 3) for k, v in bt["metrics"].items()})
    print(f"Registered {P['model_name']} (run {run.info.run_id}). Next: the predictions notebook.")''',
    "segments": MLFLOW + '''
seg = rfm(pdf, CUSTOMER, DATE, VALUE, P["order_key"]) if (CUSTOMER and DATE) else None
ok, why = enough(n_orders, P, n_customers=len(seg) if seg is not None else 0)
if seg is None:
    ok, why = False, "No customer link or no date column in the feature table, so there are no recency and frequency to segment on."
if not ok:
    print(why)
else:
    X = seg[SEGMENT_INPUTS]
    k, scores = choose_k(X, P["k_range"], P["k_tie"])
    with mlflow.start_run(run_name="customer segments (k-means on RFM)") as run:
        mlflow.log_params({"k": k, "k_rule": f"best silhouette over {list(P['k_range'])}, smaller k within {P['k_tie']}",
                           "inputs": "log(1+x) of recency days, orders, value; standardised", "value_column": VALUE,
                           "customer_column": P["customer"], "feature_table": P["feature_table"]})
        mlflow.log_metrics({**{f"silhouette_k{kk}": s for kk, s in scores.items()}, "customers": float(len(seg)), "k": float(k)})
        model = segment_pipeline(k).fit(X)
        mlflow.sklearn.log_model(model, "krusgraph_model", signature=infer_signature(X, model.predict(X)),
                                 registered_model_name=P["model_name"])
    seg["cluster"] = model.predict(X)
    seg["segment"] = segment_names(seg)
    print(seg.groupby("segment").agg(customers=("customer", "size"), median_recency_days=("recency_days", "median"),
                                     median_orders=("frequency", "median"), median_value=("monetary", "median")))
    print(f"k = {k} (silhouettes {dict((kk, round(s, 3)) for kk, s in scores.items())}). Registered {P['model_name']} "
          f"(run {run.info.run_id}). Next: the predictions notebook.")''',
    "drivers": MLFLOW + '''
result = top10(pdf, P["ids"], P["customer"], VALUE, DATE)
with mlflow.start_run(run_name="top 10 drivers (descriptive)") as run:
    mlflow.log_params({"kind": "descriptive, no model", "value_column": VALUE or "none", "dimensions": ", ".join(result["dimension"].unique())})
    mlflow.log_metrics({f"top10_share_of_orders_{d}": float(g["share_of_orders"].sum()) for d, g in result.groupby("dimension")})
for d, g in result.groupby("dimension", sort=False):
    print(d); print(g.drop(columns="dimension").to_string(index=False))
RUN_ID, MODEL_VERSION, SCORED_WITH = run.info.run_id, "none (descriptive)", "pandas"''',
}

SCORE = {
    "forecast": '''# Score with the registered model: the latest version, through Fabric's PREDICT (MLFlowTransformer, Learn: Model
# scoring with PREDICT; Sklearn is a supported flavor). Where synapse.ml is not importable: MLflow's pyfunc in Spark.
from mlflow.tracking import MlflowClient
weekly = weekly_orders(pdf, DATE)
versions = MlflowClient().search_model_versions(f"name='{P['model_name']}'")
if not versions:
    raise ValueError(f"No registered model {P['model_name']} yet: run the model notebook first. Nothing was written.")
latest = max(versions, key=lambda v: int(v.version))
RUN_ID, MODEL_VERSION = latest.run_id, str(latest.version)
future = future_frame(weekly, P["horizon"])
inputs = spark.createDataFrame(future[FORECAST_INPUTS])
try:
    from synapse.ml.predict import MLFlowTransformer
    scored = MLFlowTransformer(inputCols=FORECAST_INPUTS, outputCol="forecast_orders", modelName=P["model_name"],
                               modelVersion=int(latest.version)).transform(inputs)
    SCORED_WITH = "PREDICT"
except ImportError:
    import mlflow.pyfunc
    udf = mlflow.pyfunc.spark_udf(spark, f"models:/{P['model_name']}/{latest.version}")
    scored = inputs.withColumn("forecast_orders", udf(*FORECAST_INPUTS))
    SCORED_WITH = "mlflow.pyfunc.spark_udf"
scored = scored.toPandas()[["t", "forecast_orders"]]
result = future.merge(scored, on="t")[["week_start", "forecast_orders", "baseline_orders"]]
result["forecast_orders"] = result["forecast_orders"].astype(float).clip(lower=0).round(2)
result["week_start"] = pd.to_datetime(result["week_start"]).dt.date
print(result)''',
    "segments": '''# Score with the registered model: the latest version, through Fabric's PREDICT (MLFlowTransformer, Learn: Model
# scoring with PREDICT; Sklearn is a supported flavor). Where synapse.ml is not importable: MLflow's pyfunc in Spark.
from mlflow.tracking import MlflowClient
seg = rfm(pdf, CUSTOMER, DATE, VALUE, P["order_key"])
versions = MlflowClient().search_model_versions(f"name='{P['model_name']}'")
if not versions:
    raise ValueError(f"No registered model {P['model_name']} yet: run the model notebook first. Nothing was written.")
latest = max(versions, key=lambda v: int(v.version))
RUN_ID, MODEL_VERSION = latest.run_id, str(latest.version)
inputs = spark.createDataFrame(seg[["customer"] + SEGMENT_INPUTS])
try:
    from synapse.ml.predict import MLFlowTransformer
    scored = MLFlowTransformer(inputCols=SEGMENT_INPUTS, outputCol="cluster", modelName=P["model_name"],
                               modelVersion=int(latest.version)).transform(inputs)
    SCORED_WITH = "PREDICT"
except ImportError:
    import mlflow.pyfunc
    udf = mlflow.pyfunc.spark_udf(spark, f"models:/{P['model_name']}/{latest.version}", result_type="long")
    scored = inputs.withColumn("cluster", udf(*SEGMENT_INPUTS))
    SCORED_WITH = "mlflow.pyfunc.spark_udf"
seg = seg.merge(scored.toPandas()[["customer", "cluster"]], on="customer")
seg["cluster"] = seg["cluster"].astype(int)
seg["segment"] = segment_names(seg)
result = seg.rename(columns={"customer": P["customer_key"]})[
    [P["customer_key"], "segment", "cluster", "recency_days", "frequency", "monetary"]]
print(result.groupby("segment").size())''',
}

WRITE = '''# Write the gold table: every row carries the model's name, version and run id, and when it was scored. A table of the
# same name that this notebook did not write (no [[mark]] property) is never replaced.
import datetime as _dt
def q(*parts):
    return ".".join("`" + p.replace("`", "``") + "`" for p in parts)
name = q(P["gold_schema"], P["gold_table"]) if P["schemas_enabled"] else q(P["gold_schema"] + "_" + P["gold_table"])
OWNER = P["feature_table"] + "/" + P["gold_table"]
def ours_or_absent(name):
    if not spark.catalog.tableExists(name):
        return True
    props = {r[0]: r[1] for r in spark.sql(f"SHOW TBLPROPERTIES {name}").collect()}
    return props.get({{mark}}) == OWNER
if not ours_or_absent(name):
    raise ValueError(f"{name} exists and was not written by this notebook; nothing was written. Change P['gold_table'].")
out = result.assign(model_name=P["model_name"] or "none", model_version=MODEL_VERSION, run_id=RUN_ID,
                    scored_at=_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None), scored_with=SCORED_WITH)
if P["schemas_enabled"]:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {q(P['gold_schema'])}")
spark.createDataFrame(out).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(name)
spark.sql(f"ALTER TABLE {name} SET TBLPROPERTIES ('[[mark]]' = '{OWNER}')")
print(name, spark.read.table(name).count(), "rows written, model", P["model_name"], "version", MODEL_VERSION, "run", RUN_ID)'''

ABOUT = {
    "forecast": '''# What this shows, and what it does not.
print("""Shows: how many [[parent]] rows to expect per week for the next [[horizon]] weeks if the trend and the yearly
pattern of the past continue, beside a baseline (the same week a year earlier, or the last week). The backtest error in
the ML experiment says how far each was off on weeks it had not seen; compare them before you trust either.
Does not show: why the orders change, the effect of prices, campaigns or anything that is not in the past weeks, or how
certain a single week is. It is a baseline to beat, not a plan. Krusgraph ran nothing: the numbers are your own run's.""")''',
    "segments": '''# What this shows, and what it does not.
print("""Shows: groups of customers who buy alike, by how recently, how often and for how much they ordered, from the
proven [[parent]] -> [[customer_table]] link with one row per order. Each segment is named from its medians.
Does not show: why customers behave so, what they will do next, or that the groups are the right ones for a decision:
k was chosen by a fixed rule (the silhouette), and another k may suit your purpose. Customer ids only, no names.
Krusgraph ran nothing: the numbers are your own run's.""")''',
    "drivers": '''# What this shows, and what it does not.
print("""Shows: which customers and which values of the order's text columns carry the most orders, and their share of
the value, counted once per order (the items were summed per order first, so no total is doubled).
Does not show: cause and effect. A large share is a place to look, not a reason; nothing here is a model or a forecast.
Krusgraph ran nothing: the numbers are your own run's.""")''',
}


def _stage_cells(stage: str, analysis: str) -> list[str]:
    if stage == "model":
        if analysis == "drivers":
            return [HEADER, PARAMS, CORE, READ, TRAIN["drivers"], WRITE, ABOUT["drivers"]]
        return [HEADER, PARAMS, CORE, READ, TRAIN[analysis], ABOUT[analysis]]
    if stage == "predictions" and analysis in SCORE:
        return [HEADER, PARAMS, CORE, READ, SCORE[analysis], WRITE, ABOUT[analysis]]
    raise ValueError(f"no {stage} notebook for {analysis}")


TEMPLATES = {f"{stage}:{a}": _stage_cells(stage, a) for a in ANALYSES for stage in ("model", "predictions")
             if not (stage == "predictions" and a == "drivers")}


def fill_values(v: dict, analysis: str, stage: str) -> dict:
    """The values of one notebook: v plus what differs per analysis and stage, as the templates read them."""
    table = {"forecast": v["forecast_table"], "segments": v["segments_table"], "drivers": v["drivers_table"]}[analysis]
    model = {"forecast": v["forecast_model"], "segments": v["segments_model"], "drivers": None}[analysis]
    stage_title = "stage 2, the model" if stage == "model" and analysis != "drivers" else (
        "stage 2, descriptive (no model)" if stage == "model" else "stage 3, predictions in gold")
    return {**v, "title": TITLES[analysis], "stage_title": stage_title, "gold_table": table, "model_name": model,
            "min_orders": MIN_ORDERS, "min_weeks": MIN_WEEKS, "min_customers": MIN_CUSTOMERS, "horizon": HORIZON,
            "k_range": list(K_RANGE), "k_tie": K_TIE, "mark": PREDICTION_MARK,
            "learn_autolog": LEARN["autolog"], "learn_predict": LEARN["predict"]}


_CODE = re.compile(r"\{\{(\w+)\}\}")
_TEXT = re.compile(r"\[\[(\w+)\]\]")


def _literal(x) -> str:
    """A value as Python source: strings and lists as JSON (valid Python), None, True and False as Python spells them."""
    if x is None:
        return "None"
    if isinstance(x, bool):
        return "True" if x else "False"
    return json.dumps(x, ensure_ascii=False)


def fill(template: str, vals: dict) -> str:
    """{{name}} -> the value as a Python literal (code); [[name]] -> the value as plain text (comments and prose)."""
    out = _CODE.sub(lambda m: _literal(vals[m.group(1)]), template)
    return _TEXT.sub(lambda m: "None" if vals[m.group(1)] is None else str(vals[m.group(1)]), out)


def cells(v: dict, analysis: str, stage: str) -> list[str]:
    vals = fill_values(v, analysis, stage)
    return [fill(t, vals) for t in TEMPLATES[f"{stage}:{analysis}"]]


def notebook_name(v: dict, source_name: str, analysis: str, stage: str) -> str:
    """nextSteps.ts: the stage-1 notebook is <lakehouse>_<parent>_features; these follow it."""
    word = {"model": "model" if analysis != "drivers" else "top10", "predictions": "predictions"}[stage]
    return ident(f"{source_name}_{v['parent']}_{analysis}_{word}")[:123]


def stages(grain: dict, source: dict, links: list[dict]) -> dict:
    """Everything the editor shows for one feature table: the recommended analyses, each with its three stages."""
    cust = customer_link(grain, links)
    v = values(grain, source, cust)
    out = []
    for r in recommend(v):
        a = r["analysis"]
        st = [{"stage": "features", "name": ident(f"{source.get('name') or 'lakehouse'}_{grain['parent']}_features")[:123],
               "output": v["feature_table"]}]
        st.append({"stage": "model", "name": notebook_name(v, source.get("name") or "lakehouse", a, "model"),
                   "cells": cells(v, a, "model"), "output": r["model_name"] or r["gold_table"]})
        if a != "drivers":
            st.append({"stage": "predictions", "name": notebook_name(v, source.get("name") or "lakehouse", a, "predictions"),
                       "cells": cells(v, a, "predictions"), "output": r["gold_table"]})
        out.append({**r, "stages": st})
    return {"values": v, "analyses": out, "experiment": v["experiment"]}


# ------------------------------------------------------------------ the semantic model's part ------------------------

PREDICTION_COLUMNS = {"model_version", "run_id"}


def prediction_kind(columns: list[str]) -> str | None:
    """'segments' or 'forecast' for a table the predictions notebook wrote (by its columns), else None."""
    cols = {c.lower() for c in columns}
    if not PREDICTION_COLUMNS <= cols:
        return None
    if {"segment", "cluster"} <= cols:
        return "segments"
    if {"week_start", "forecast_orders"} <= cols:
        return "forecast"
    return None


MEASURES = {"segments": ("Customers in segments", "COUNTROWS({table})", "#,0"),
            "forecast": ("Forecast orders", "SUM({table}[forecast_orders])", "#,0")}


# ------------------------------------------------------------------ the editor's copy --------------------------------

GENERATED = Path(__file__).parent.parent / "workload" / "Workload" / "app" / "items" / "ModelItem" / "advancedStages.generated.ts"


def generated_ts() -> str:
    """The templates and thresholds for the editor (advancedStages.ts fills them the way fill() does)."""
    data = {"templates": TEMPLATES, "thresholds": {"min_orders": MIN_ORDERS, "min_weeks": MIN_WEEKS, "min_customers": MIN_CUSTOMERS,
                                                    "horizon": HORIZON, "k_range": list(K_RANGE), "k_tie": K_TIE},
            "mark": PREDICTION_MARK, "learn": LEARN, "titles": TITLES, "too_few": TOO_FEW}
    return ("// Written by fabric_backend/advanced_stages.py (write_generated); do not edit by hand.\n"
            "// tests/test_aa1_advanced_stages.py fails when it differs from the Python templates.\n"
            f"export const ADVANCED = {json.dumps(data, indent=1, ensure_ascii=False)} as const;\n")


FIXTURE = GENERATED.with_name("advancedStages.fixture.json")

# The two grains the editor's test fills: the shop sample (60 orders: too few for a model) and the SAP full demo
# (sap_demo36: 4,220 invoices, VBRP -> VBRK with the client column, KUNAG -> KNA1).
FIXTURE_CASES = [
    {"grain": {"child": "order_items", "parent": "orders", "childColumns": ["order_id"], "parentColumns": ["order_id"],
               "childIds": ["line_no", "order_id", "product_id"], "parentRows": 60},
     "source": {"name": "shop_lh", "schema": "shop"},
     "links": [{"source": "orders", "columns": ["customer_id"], "target": "customers", "target_columns": ["customer_id"]},
               {"source": "orders", "columns": ["ship_to_id"], "target": "addresses", "target_columns": ["address_id"]},
               {"source": "order_items", "columns": ["order_id"], "target": "orders", "target_columns": ["order_id"]}]},
    {"grain": {"child": "VBRP", "parent": "VBRK", "childColumns": ["MANDT", "VBELN"], "parentColumns": ["MANDT", "VBELN"],
               "childIds": ["AUBEL", "AUPOS", "MANDT", "MATNR", "POSNR", "VBELN", "VGBEL", "VGPOS"], "parentRows": 4220},
     "source": {"name": "sap_lh", "schema": "sap"},
     "links": [{"source": "VBRK", "columns": ["MANDT", "KUNAG"], "target": "KNA1", "target_columns": ["MANDT", "KUNNR"]},
               {"source": "VBRK", "columns": ["MANDT", "KUNRG"], "target": "KNA1", "target_columns": ["MANDT", "KUNNR"]},
               {"source": "VBRP", "columns": ["MANDT", "VBELN"], "target": "VBRK", "target_columns": ["MANDT", "VBELN"]}]},
]


def fixture() -> str:
    return json.dumps([{**c, "expected": stages(c["grain"], c["source"], c["links"])} for c in FIXTURE_CASES],
                      indent=1, ensure_ascii=False) + "\n"


def write_generated() -> Path:
    GENERATED.write_text(generated_ts(), encoding="utf-8")
    FIXTURE.write_text(fixture(), encoding="utf-8")
    return GENERATED


if __name__ == "__main__":
    print(write_generated())
