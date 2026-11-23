"""AA1: from the feature table to a model and to predictions in gold (Gustav, 21 November 2026: the Data Science starter
ran in Fabric; next, a model and predictions that land in gold and in the semantic model).

The notebooks are advanced_stages.py's templates. Here they are parsed, made into .ipynb, and run cell by cell on the
synthetic SAP full demo (sap_demo36: 4,220 invoices) and the shop sample (60 orders) with a pandas stand-in for Spark and
a small stand-in for MLflow and PREDICT, so the code a person runs in Fabric is the code these tests ran (Spark, MLflow and
synapse.ml themselves are not here). The semantic model gets a prediction table only when it exists in gold. Nothing
calls Fabric."""
from __future__ import annotations

import ast
import json
import re
import sys
import types
from contextlib import contextmanager

import pytest

from fabric_backend import advanced_stages as A, demo, gold, model_compare, report, semantic_model as sm

pd = pytest.importorskip("pandas")
pytest.importorskip("sklearn")

SHOP = A.FIXTURE_CASES[0]


# ------------------------------------------------------------------ the synthetic data ---------------------------------

def _frame(tables, name):
    cols, kinds, rows = tables[name]
    df = pd.DataFrame(rows, columns=cols)
    for c, k in zip(cols, kinds):
        if k != "string":
            df[c] = df[c].astype(float)
    return df


def _features(parent, child, key, numeric, prefix):
    """Stage 1 as nextSteps.ts featureCells writes it: the child's numeric columns summed per parent row first, then
    joined once on the proven key (one row per parent)."""
    per = child.groupby(key).agg(**{f"{prefix}_rows": (key[0], "size")},
                                 **{f"{prefix}_{c}_sum": (c, "sum") for c in numeric}).reset_index()
    out = parent.merge(per, on=key, how="left")
    out[f"{prefix}_rows"] = out[f"{prefix}_rows"].fillna(0)
    return out


@pytest.fixture(scope="module")
def sap36():
    from fabric_backend import sap_demo36
    t = sap_demo36.tables()
    vbrk, vbrp = _frame(t, "VBRK"), _frame(t, "VBRP")
    feat = _features(vbrk, vbrp, ["MANDT", "VBELN"], ["NETWR", "FKIMG"], "sap_vbrp")
    grain = {"child": "sap_vbrp", "parent": "sap_vbrk", "childColumns": ["MANDT", "VBELN"], "parentColumns": ["MANDT", "VBELN"],
             "childIds": ["AUBEL", "AUPOS", "MANDT", "MATNR", "POSNR", "VBELN", "VGBEL", "VGPOS"], "parentRows": len(vbrk)}
    links = [{"source": "sap_vbrk", "columns": ["MANDT", "KUNAG"], "target": "sap_kna1", "target_columns": ["MANDT", "KUNNR"]}]
    return feat, A.stages(grain, {"name": "sap_lh", "schema": "sap"}, links), vbrp


@pytest.fixture(scope="module")
def shop():
    rows = demo.seed_rows() if hasattr(demo, "seed_rows") else None
    from fabric_backend import seed
    r = seed.rows()
    orders = pd.DataFrame(r["orders"], columns=["order_id", "customer_id", "order_date", "ship_to_id"])
    items = pd.DataFrame(r["order_items"], columns=["order_id", "line_no", "product_id", "quantity"])
    feat = _features(orders, items, ["order_id"], ["quantity"], "order_items")
    return feat, A.stages(SHOP["grain"], SHOP["source"], SHOP["links"])


# ------------------------------------------------------------------ Spark and MLflow, stood in for ---------------------

class _DF:
    def __init__(self, pdf, store=None):
        self.pdf, self.store = pdf.reset_index(drop=True), store

    def toPandas(self):
        return self.pdf.copy()

    def count(self):
        return len(self.pdf)

    @property
    def write(self):
        df = self

        class W:
            def format(self, *_):
                return self

            def mode(self, *_):
                return self

            def option(self, *_):
                return self

            def saveAsTable(self, name):
                df.store[name] = df.pdf.copy()
        return W()


class _Spark:
    def __init__(self, tables):
        self.tables, self.props, self.sqls = dict(tables), {}, []
        spark = self

        class Read:
            def table(self, name):
                if name not in spark.tables:
                    raise KeyError(name)
                return _DF(spark.tables[name], spark.tables)

        class Catalog:
            def tableExists(self, name):
                return name in spark.tables
        self.read, self.catalog = Read(), Catalog()

    def createDataFrame(self, pdf):
        return _DF(pd.DataFrame(pdf), self.tables)

    def sql(self, text):
        self.sqls.append(text)
        m = re.match(r"ALTER TABLE (\S+) SET TBLPROPERTIES \('([^']+)' = '([^']+)'\)", text)
        if m:
            self.props.setdefault(m.group(1), {})[m.group(2)] = m.group(3)
        m = re.match(r"SHOW TBLPROPERTIES (\S+)", text)
        rows = list(self.props.get(m.group(1), {}).items()) if m else []
        return types.SimpleNamespace(collect=lambda: rows)


class _MLflow:
    """What the notebooks call: autolog, set_experiment, start_run, log_params/metrics, sklearn.log_model with
    registered_model_name, MlflowClient().search_model_versions; and PREDICT's MLFlowTransformer."""

    def __init__(self):
        self.runs, self.models, self.autolog_calls, self.experiment = [], {}, [], None

    def modules(self):
        ml = types.ModuleType("mlflow")
        ml.autolog = lambda **kw: self.autolog_calls.append(kw)
        ml.set_experiment = lambda name: setattr(self, "experiment", name)

        @contextmanager
        def start_run(run_name=None):
            run = {"name": run_name, "params": {}, "metrics": {}, "id": f"run{len(self.runs) + 1:04d}"}
            self.runs.append(run)
            yield types.SimpleNamespace(info=types.SimpleNamespace(run_id=run["id"]))
        ml.start_run = start_run
        ml.log_params = lambda p: self.runs[-1]["params"].update(p)
        ml.log_metrics = lambda m: self.runs[-1]["metrics"].update(m)
        sk = types.ModuleType("mlflow.sklearn")

        def log_model(model, path, signature=None, registered_model_name=None):
            versions = self.models.setdefault(registered_model_name, [])
            versions.append(types.SimpleNamespace(version=str(len(versions) + 1), run_id=self.runs[-1]["id"], model=model))
        sk.log_model = log_model
        ml.sklearn = sk
        models = types.ModuleType("mlflow.models")
        sig = types.ModuleType("mlflow.models.signature")
        sig.infer_signature = lambda x, y=None: ("signature", list(getattr(x, "columns", [])))
        tracking = types.ModuleType("mlflow.tracking")
        outer = self

        class Client:
            def search_model_versions(self, flt):
                name = re.search(r"name='([^']+)'", flt).group(1)
                return list(outer.models.get(name, []))
        tracking.MlflowClient = Client
        predict = types.ModuleType("synapse.ml.predict")

        class MLFlowTransformer:
            def __init__(self, inputCols, outputCol, modelName, modelVersion):
                self.cols, self.out = inputCols, outputCol
                self.model = next(v.model for v in outer.models[modelName] if int(v.version) == int(modelVersion))

            def transform(self, df):
                pdf = df.toPandas()
                pdf[self.out] = self.model.predict(pdf[self.cols])
                return _DF(pdf)
        predict.MLFlowTransformer = MLFlowTransformer
        synapse, synapse_ml = types.ModuleType("synapse"), types.ModuleType("synapse.ml")
        return {"mlflow": ml, "mlflow.sklearn": sk, "mlflow.models": models, "mlflow.models.signature": sig,
                "mlflow.tracking": tracking, "synapse": synapse, "synapse.ml": synapse_ml, "synapse.ml.predict": predict}


def _run(cells, spark, ml, monkeypatch):
    for name, mod in ml.modules().items():
        monkeypatch.setitem(sys.modules, name, mod)
    ns = {"spark": spark, "display": print}
    for c in cells:
        exec(compile(c, "<cell>", "exec"), ns)          # noqa: S102 - the generated notebook, on synthetic rows
    return ns


# ------------------------------------------------------------------ the notebooks ---------------------------------------

def _all(st):
    return [(a["analysis"], s) for a in st["analyses"] for s in a["stages"] if s.get("cells")]


def test_the_editors_copy_is_the_pythons():
    assert A.GENERATED.read_text(encoding="utf-8") == A.generated_ts(), "run python -m fabric_backend.advanced_stages"
    assert A.FIXTURE.read_text(encoding="utf-8") == A.fixture(), "run python -m fabric_backend.advanced_stages"


def test_every_cell_parses_and_names_nothing_undefined(sap36, shop):
    import builtins
    for st in (sap36[1], shop[1]):
        for analysis, s in _all(st):
            code = "\n\n".join(s["cells"])
            tree = ast.parse(code)
            assert not re.search(r"\{\{\w+\}\}|\[\[\w+\]\]", code), (analysis, s["stage"])           # every placeholder filled
            defined = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
            defined |= {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
            defined |= {a.asname or a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
            defined |= {a.arg for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.Lambda)) for a in n.args.args + n.args.kwonlyargs}
            defined |= {n.name for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and n.name}
            used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
            assert used - defined - set(dir(builtins)) <= {"spark"}, (analysis, s["stage"], used - defined - set(dir(builtins)))


def test_the_notebooks_are_valid_ipynb(sap36):
    from fabric_backend.sap_demo36 import ipynb
    for analysis, s in _all(sap36[1]):
        nb = json.loads(json.dumps(ipynb([("code", c) for c in s["cells"]])))
        assert nb["nbformat"] == 4 and len(nb["cells"]) == len(s["cells"])
        assert all(c["cell_type"] == "code" and isinstance(c["source"], (list, str)) for c in nb["cells"])
        assert len(s["cells"]) <= 12 and sum(len(c) for c in s["cells"]) <= 60_000      # what POST /workload/v1/starter takes


def test_each_notebook_reads_only_the_feature_table_and_joins_no_fact_to_a_fact(sap36):
    for analysis, s in _all(sap36[1]):
        code = "\n".join(s["cells"])
        assert re.findall(r"spark\.read\.table\(([^)]*)\)", code) in (['P["feature_table"]'], ['P["feature_table"]', "name"]), analysis
        assert ".join(" not in re.sub(r'"[^"\n]*"\.join\(|\'[^\'\n]*\'\.join\(', "", code), analysis       # no Spark join at all
        assert "check_grain(pdf, P[\"order_key\"])" in code


def test_the_grain_check_stops_a_doubled_total(sap36):
    feat = sap36[0]
    ns = {}
    exec(A.CORE, ns)                                                                   # noqa: S102
    assert ns["check_grain"](feat, ["MANDT", "VBELN"]) == len(feat)
    doubled = pd.concat([feat, feat.head(3)])
    with pytest.raises(ValueError, match="totals would be doubled"):
        ns["check_grain"](doubled, ["MANDT", "VBELN"])


def test_the_value_is_the_items_summed_per_order_not_the_headers_amount(sap36):
    """sap_demo36 plants a header whose NETWR is twice its items: the value column is the items' sum."""
    feat, st, vbrp = sap36
    ns = {}
    exec(A.CORE, ns)                                                                   # noqa: S102
    col, what = ns["pick_value"](feat, "sap_vbrp", st["values"]["ids"])
    assert (col, what) == ("sap_vbrp_NETWR_sum", "amount summed from the items")
    assert abs(feat[col].sum() - vbrp["NETWR"].sum()) < 0.01


# ------------------------------------------------------------------ run on the SAP full demo ----------------------------

def test_forecast_model_then_predictions_in_gold(sap36, monkeypatch):
    feat, st, _ = sap36
    fc = next(a for a in st["analyses"] if a["analysis"] == "forecast")
    assert fc["model"] and not fc["too_few"]
    spark, ml = _Spark({"sap_vbrk_features": feat}), _MLflow()
    ns = _run(fc["stages"][1]["cells"], spark, ml, monkeypatch)
    assert ml.autolog_calls == [{"exclusive": False}] and ml.experiment == "sap_vbrk_experiment"
    m = ml.runs[0]["metrics"]
    assert {"mae_regression", "mae_baseline", "weeks_held_out"} <= set(m) and m["weeks_held_out"] == 8
    assert ml.runs[0]["params"]["baseline"] == "seasonal naive (52 weeks)"
    assert [v.version for v in ml.models["sap_vbrk_weekly_forecast"]] == ["1"]
    ns = _run(fc["stages"][2]["cells"], spark, ml, monkeypatch)
    out = spark.tables["`gold`.`sap_vbrk_forecast`"]
    assert len(out) == A.HORIZON and list(out.columns)[:3] == ["week_start", "forecast_orders", "baseline_orders"]
    assert set(out["model_version"]) == {"1"} and set(out["run_id"]) == {ml.runs[0]["id"]} and set(out["scored_with"]) == {"PREDICT"}
    assert (out["forecast_orders"] >= 0).all()
    assert A.prediction_kind(list(out.columns)) == "forecast"
    assert spark.props["`gold`.`sap_vbrk_forecast`"][A.PREDICTION_MARK] == "sap_vbrk_features/sap_vbrk_forecast"


def test_segments_model_then_predictions_in_gold(sap36, monkeypatch):
    feat, st, _ = sap36
    seg = next(a for a in st["analyses"] if a["analysis"] == "segments")
    spark, ml = _Spark({"sap_vbrk_features": feat}), _MLflow()
    _run(seg["stages"][1]["cells"], spark, ml, monkeypatch)
    p = ml.runs[0]["params"]
    assert p["k"] in A.K_RANGE and "best silhouette" in p["k_rule"]
    assert {f"silhouette_k{k}" for k in A.K_RANGE} <= set(ml.runs[0]["metrics"])
    _run(seg["stages"][2]["cells"], spark, ml, monkeypatch)
    out = spark.tables["`gold`.`customer_segment`"]
    assert "MANDT_KUNNR_key" in out.columns                       # gold's combined key column of sap_kna1
    assert out["MANDT_KUNNR_key"].str.startswith("100\x1f").all()
    assert out["MANDT_KUNNR_key"].is_unique and out["segment"].str.match(r"Segment \d of \d: ").all()
    assert out["cluster"].nunique() == p["k"] and A.prediction_kind(list(out.columns)) == "segments"


def test_drivers_is_descriptive_and_writes_its_top10(sap36, monkeypatch):
    feat, st, _ = sap36
    dr = next(a for a in st["analyses"] if a["analysis"] == "drivers")
    assert [s["stage"] for s in dr["stages"]] == ["features", "model"] and dr["model_name"] is None
    spark, ml = _Spark({"sap_vbrk_features": feat}), _MLflow()
    _run(dr["stages"][1]["cells"], spark, ml, monkeypatch)
    out = spark.tables["`gold`.`sap_vbrk_top10`"]
    assert not ml.models and ml.runs[0]["params"]["kind"] == "descriptive, no model"
    assert (out.groupby("dimension")["share_of_orders"].sum() <= 1.0 + 1e-9).all()
    assert (out.groupby("dimension")["rank"].max() <= 10).all()
    assert A.prediction_kind(list(out.columns)) is None              # not a prediction table: the model leaves it out


def test_a_table_it_did_not_write_is_never_replaced(sap36, monkeypatch):
    feat, st, _ = sap36
    fc = next(a for a in st["analyses"] if a["analysis"] == "forecast")
    spark, ml = _Spark({"sap_vbrk_features": feat, "`gold`.`sap_vbrk_forecast`": pd.DataFrame({"x": [1]})}), _MLflow()
    _run(fc["stages"][1]["cells"], spark, ml, monkeypatch)
    with pytest.raises(ValueError, match="was not written by this notebook"):
        _run(fc["stages"][2]["cells"], spark, ml, monkeypatch)
    assert list(spark.tables["`gold`.`sap_vbrk_forecast`"].columns) == ["x"]


def test_predictions_before_a_model_stop_and_write_nothing(sap36, monkeypatch):
    feat, st, _ = sap36
    fc = next(a for a in st["analyses"] if a["analysis"] == "forecast")
    spark = _Spark({"sap_vbrk_features": feat})
    with pytest.raises(ValueError, match="run the model notebook first"):
        _run(fc["stages"][2]["cells"], spark, _MLflow(), monkeypatch)
    assert set(spark.tables) == {"sap_vbrk_features"}


# ------------------------------------------------------------------ the shop sample: too few rows ---------------------

def test_the_shop_sample_says_once_it_has_too_few_rows_and_trains_nothing(shop, monkeypatch, capsys):
    feat, st = shop
    assert [a["analysis"] for a in st["analyses"]] == ["forecast", "segments", "drivers"]
    assert {a["too_few"] for a in st["analyses"] if a["analysis"] != "drivers"} == {
        "Too few rows for a model (60 orders; a model starts at 200 orders). The feature table is still useful: it has one row "
        "per order, so its totals are not doubled."}
    spark, ml = _Spark({"orders_features": feat}), _MLflow()
    _run(st["analyses"][0]["stages"][1]["cells"], spark, ml, monkeypatch)
    assert "Too few rows for a model (60 orders" in capsys.readouterr().out
    assert not ml.runs and not ml.models
    _run(st["analyses"][2]["stages"][1]["cells"], spark, ml, monkeypatch)                # drivers: no model, still useful
    out = spark.tables["`gold`.`orders_top10`"]
    assert set(out["dimension"]) == {"customer_id"} and out["share_of_orders"].sum() <= 1.0 + 1e-9


def test_the_rules():
    v = A.values(SHOP["grain"], SHOP["source"], A.customer_link(SHOP["grain"], SHOP["links"]))
    assert v["customer"] == "customer_id" and v["customer_key"] == "customer_id" and v["feature_table"] == "orders_features"
    no_customer = A.stages(SHOP["grain"], SHOP["source"], [l for l in SHOP["links"] if l["target"] != "customers"])
    assert [a["analysis"] for a in no_customer["analyses"]] == ["forecast", "drivers"]
    assert A.prediction_kind(["customer_id", "segment", "cluster", "model_version", "run_id"]) == "segments"
    assert A.prediction_kind(["customer_id", "segment", "cluster"]) is None               # no version or run id: not ours


def test_no_names_and_no_claims_in_the_generated_text(sap36):
    text = json.dumps(A.TEMPLATES) + A.__doc__
    for word in ("accurate", "accuracy", "certified", "partner of", "endorsed", "guarantee", "faster", "compliant"):
        assert word not in text.lower(), word
    assert "Krusgraph ran nothing" in text and "the numbers are your own run's" in text


# ------------------------------------------------------------------ into the semantic model and the report ------------

def _cols(xs):
    return [{"name": n, "type": t} for n, t in xs]


PRED_SHOP = [
    {"table": "customer_segment", "columns": _cols([("customer_id", "int"), ("segment", "string"), ("cluster", "bigint"),
                                                     ("recency_days", "double"), ("frequency", "double"), ("monetary", "double"),
                                                     ("model_name", "string"), ("model_version", "string"), ("run_id", "string"),
                                                     ("scored_at", "timestamp"), ("scored_with", "string")])},
    {"table": "orders_forecast", "columns": _cols([("week_start", "date"), ("forecast_orders", "double"), ("baseline_orders", "double"),
                                                    ("model_name", "string"), ("model_version", "string"), ("run_id", "string"),
                                                    ("scored_at", "timestamp"), ("scored_with", "string")])},
    {"table": "orders_top10", "columns": _cols([("dimension", "string"), ("rank", "bigint"), ("orders", "bigint")])},
]


@pytest.fixture(scope="module")
def shop_model():
    p = demo.plan(demo.schema("shop"), keys=demo.DEMO_KEYS)
    g = gold.spec(p, demo.FLOW_INFO, "silver", "gold", dimensions=True)
    before = sm.draft_on_gold(p, demo.FLOW_INFO, g, "shop_model", validation=demo.demo_validation())
    after = sm.draft_on_gold(p, demo.FLOW_INFO, g, "shop_model", validation=demo.demo_validation(), predictions=PRED_SHOP)
    return before, after


def test_nothing_is_added_when_no_prediction_table_exists(shop_model):
    before, _ = shop_model
    p = demo.plan(demo.schema("shop"), keys=demo.DEMO_KEYS)
    g = gold.spec(p, demo.FLOW_INFO, "silver", "gold", dimensions=True)
    empty = sm.draft_on_gold(p, demo.FLOW_INFO, g, "shop_model", validation=demo.demo_validation(), predictions=[])
    assert empty["parts"] == before["parts"]
    assert before["summary"]["advanced_analytics"]["tables"] == []
    assert not any("customer_segment" in t or "orders_forecast" in t for t in before["parts"])


def test_a_prediction_table_in_gold_joins_the_model_on_its_proven_key(shop_model):
    _, after = shop_model
    aa = after["summary"]["advanced_analytics"]
    assert [(t["table"], t["kind"], t["measure"]) for t in aa["tables"]] == [
        ("customer_segment", "segments", "Customers in segments"), ("orders_forecast", "forecast", "Forecast orders")]
    assert aa["tables"][0]["related"] == "customer_segment.customer_id -> customers.customer_id"
    rel = after["parts"]["definition/relationships.tmdl"]
    assert "fromColumn: customer_segment.customer_id\n\ttoColumn: customers.customer_id" in rel
    assert "fromColumn: orders_forecast.week_start\n\ttoColumn: Calendar.Date" in rel
    for t, m in (("customer_segment", "Customers in segments"), ("orders_forecast", "Forecast orders")):
        text = after["parts"][f"definition/tables/{t}.tmdl"]
        assert text.count("\tmeasure ") == 1 and f"measure '{m}'" in text
        assert "displayFolder: Advanced analytics" in text and "annotation Krusgraph_AdvancedAnalytics = Advanced analytics" in text
        assert "schemaName: gold" in text
    assert "orders_top10" not in json.dumps(after["summary"])                     # descriptive, not a prediction table
    assert not any(r for r in after["summary"]["interfaces"] if "customer_segment" in json.dumps(r))


def test_the_report_gets_one_visual_for_each(shop_model):
    before, after = shop_model
    vis = lambda d: report.definition_parts(model_compare.from_tmdl(d["parts"]), "00000000-0000-0000-0000-0000000000aa",
                                            model_name="shop_model", created="22 November 2026")["visuals"]
    b, a = vis(before), vis(after)
    added = [v for v in a if v["title"] not in {x["title"] for x in b}]
    assert [(v["type"], v["title"]) for v in added] == [("clusteredBarChart", "Customers by segment"),
                                                       ("clusteredColumnChart", "Forecast orders by week")]
    assert [v["title"] for v in b] == [v["title"] for v in a if v not in added]   # the rest of the page as it was
    model = model_compare.from_tmdl(after["parts"])
    vs = report.visuals(model)["visuals"]
    full = [{"type": "title", "title": "Overview · shop_model", "text": "Overview · shop_model", "fields": ["title"]}] + vs + \
           [{"type": "footnote", "title": "Footnote", "text": "22 November 2026. Created by Krusgraph from the checked plan.", "fields": ["footnote"]}]
    for v, pos in zip(full, report._positions(full)):
        assert not report.text_problems(v, pos), (v["title"], report.text_problems(v, pos))


def test_on_the_sap_full_demo_the_segments_relate_on_the_combined_customer_key():
    from fabric_backend import evidence, sap_demo
    from fabric_backend.infer import plan
    schema, execute = sap_demo.sqlite(full=True)
    p = plan(schema)
    v = evidence.validate(p, execute, max_items=200)
    info = {"item_name": "sap_lh", "item_kind": "Lakehouse", "schema": "sap", "schemas_enabled": True}
    g = gold.spec(p, info, "silver", "gold", dimensions=True)
    preds = [{"table": "customer_segment", "columns": _cols([("MANDT_KUNNR_key", "string"), ("segment", "string"), ("cluster", "bigint"),
                                                              ("model_version", "string"), ("run_id", "string")])}]
    d = sm.draft_on_gold(p, info, g, "sap_model", validation=v, predictions=preds)
    aa = d["summary"]["advanced_analytics"]
    assert aa["tables"][0]["related"] == "customer_segment.MANDT_KUNNR_key -> sap_kna1.MANDT_KUNNR_key"
    bad = [{"table": "customer_segment", "columns": _cols([("KUNNR", "string"), ("segment", "string"), ("cluster", "bigint"),
                                                            ("model_version", "string"), ("run_id", "string")])}]
    d2 = sm.draft_on_gold(p, info, g, "sap_model", validation=v, predictions=bad)
    assert d2["summary"]["advanced_analytics"]["tables"] == []
    assert "could not relate on a proven key" in d2["summary"]["advanced_analytics"]["not_added"][0]["why"]
    assert "definition/tables/customer_segment.tmdl" not in d2["parts"]


def test_create_semantic_model_reads_the_prediction_tables_only_from_gold(monkeypatch):
    from fabric_backend import server as S
    from fabric_backend.schema import Column, Schema, Table
    seen = {}

    def fake_connected(ws, item, schema, ctx):
        seen["args"] = (ws, item, schema)
        tables = {"orders_forecast": Table("orders_forecast", [Column(c["name"], c["type"]) for c in PRED_SHOP[1]["columns"]], schema="gold"),
                  "orders": Table("orders", [Column("order_id", "int")], schema="gold")}
        return Schema(tables, schema="gold"), types.SimpleNamespace(close=lambda: seen.setdefault("closed", True))
    monkeypatch.setattr(S, "_connected", fake_connected)
    got = S._prediction_tables({"workspace_id": "ws", "item_id": "lh", "item_name": "shop_lh"}, "gold", None)
    assert [t["table"] for t in got] == ["orders_forecast"] and seen["args"] == ("ws", "lh", "gold") and seen["closed"]

    def broken(*_a):
        raise RuntimeError("no gold schema")
    monkeypatch.setattr(S, "_connected", broken)
    assert S._prediction_tables({"workspace_id": "ws", "item_id": "lh", "item_name": "shop_lh"}, "gold", None) == []


def test_the_starter_records_the_stage():
    from fabric_backend import workload_api as W
    base = {"workspace": "ws", "source": "lh", "schema": "shop", "name": "shop_lh_orders_forecast_model", "cells": ["print(1)"]}
    assert W.starter_request(base)["stage"] == "features"
    assert W.starter_request({**base, "stage": "model"})["stage"] == "model"
    with pytest.raises(Exception, match="stage"):
        W.starter_request({**base, "stage": "train"})
    assert W.STARTER_STAGES["predictions"][0] == "ds_predictions"
