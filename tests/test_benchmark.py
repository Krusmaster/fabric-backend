"""Rounds n61 and n62: the comparison benchmark in examples/benchmark/ is reproducible and says what it measured."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "examples" / "benchmark"


def _load():
    spec = importlib.util.spec_from_file_location("n61_benchmark", HERE / "benchmark.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_run_reproduces_the_committed_results_and_the_readme_table():
    b = _load()
    res = b.run()
    assert json.loads(json.dumps(res, sort_keys=True)) == json.loads((HERE / "results.json").read_text())
    assert b.markdown(res) in (HERE / "README.md").read_text()


def test_what_each_method_catches_and_misses():
    res = _load().run()
    k, a, d = (res["traps"][m] for m in ("krusgraph", "autodetect", "dbt"))
    assert k["doubled_found"] == "2/2" and d["doubled_found"] == "0/2" and a["doubled_found"] == "0/2"
    assert a["ambiguous_fallen_for"] == "2/2" and "countries code -> currencies" in a["false_positives"]
    assert k["ambiguous_fallen_for"] == "0/2" and k["precision"] == 1.0 and not k["false_positives"]   # R5 adds no trap
    # n62, measured: with the rows R5 plans the six links n61 missed (code columns and role names), at precision 1.0
    for ds in ("shop", "sap", "crm", "traps"):
        r = res[ds]["krusgraph"]
        assert (r["precision"], r["recall"], r["recall_with_suggestions"]) == (1.0, 1.0, 1.0), ds
    assert (res["shop"]["krusgraph"]["true_positives"], res["crm"]["krusgraph"]["true_positives"], k["true_positives"]) == (7, 5, 8)
    assert res["sap"]["dbt"]["orphans_found"] == "0/1"                                   # composite keys: no built-in test


def test_the_baseline_is_never_called_power_bi_itself():
    text = (HERE / "README.md").read_text() + (HERE / "benchmark.py").read_text()
    assert "approximation of documented autodetect rules" in text.lower()
    assert "learn.microsoft.com/en-us/power-bi/transform-model/desktop-create-and-manage-relationships" in text
