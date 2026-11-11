"""n223: the check against the rows says how far it is ("3 of 7 keys and links counted"), so the Model editor's Onto can
show progress while Fabric's SQL endpoint counts; and the editor's loading words and lazy parts are where the editor
loads them (the words themselves are unit-tested in workload/Workload/app/items/ModelItem/waitWords.test.ts)."""
from pathlib import Path

from fabric_backend import evidence as ev
from fabric_backend import operations
from fabric_backend import workload_api as W

from tests.test_evidence import python_execute, shop_plan

MODEL = Path(__file__).resolve().parents[1] / "workload" / "Workload" / "app" / "items" / "ModelItem"


def test_validate_says_each_key_and_link_counted_up_to_all_of_them():
    steps = []
    out = ev.validate(shop_plan(keys={"order_items": ["order_id", "line_no"]}), python_execute(), on_step=lambda d, t: steps.append((d, t)))
    total = len(out["keys"]) + len(out["relationships"])
    assert steps[-1] == (total, total)
    assert all(t == total for _, t in steps)
    assert [d for d, _ in steps] == sorted(d for d, _ in steps)            # never goes back
    assert out["summary"].startswith("6 of 6 keys unique, 6 of 6 relationships hold")   # the answer is unchanged


def test_validate_counts_only_what_max_items_allows():
    steps = []

    def execute(sql):
        return [{"n": 1, "nulls": 0, "distinct_keys": 1, "with_value": 1, "orphans": 0}]
    ev.validate(shop_plan(), execute, max_items=3, on_step=lambda d, t: steps.append((d, t)))
    assert steps == [(1, 3), (2, 3), (3, 3)]


def test_validate_without_on_step_is_as_before():
    assert ev.validate(shop_plan(keys={"order_items": ["order_id", "line_no"]}), python_execute())["keys"]


def test_check_progress_writes_at_most_once_a_second_and_always_the_end(monkeypatch):
    written = []
    monkeypatch.setattr(operations, "progress", lambda status=None, **f: written.append((status, f)))
    now = [0.0]
    step = W.check_progress(clock=lambda: now[0])
    for i, t in enumerate([0.0, 0.2, 0.5, 1.1, 1.3, 1.4], start=1):
        now[0] = t
        step(i, 7)
    now[0] = 1.5
    step(7, 7)                                                              # the end is written however soon
    assert [f["done"] for _, f in written] == [1, 4, 7]
    assert all(s == "running" and f["total"] == 7 and f["unit"] == "keys and links counted" for s, f in written)


def test_check_progress_outside_an_operation_does_nothing():
    W.check_progress()(1, 2)                                                # no operation: operations.progress is a no-op


def test_run_check_passes_the_progress_to_the_counting():
    src = Path(W.__file__).read_text(encoding="utf-8")
    assert 'E.validate(p, execute, max_items=req["max_items"], on_step=check_progress())' in src


def test_the_editor_draws_every_wait_with_one_component_and_loads_its_heavy_parts_when_shown():
    editor = (MODEL / "ModelItemEditor.tsx").read_text(encoding="utf-8")
    views = (MODEL / "ModelItemViews.tsx").read_text(encoding="utf-8")
    lazy = (MODEL / "lazyParts.tsx").read_text(encoding="utf-8")
    assert "loadingContent={<div className=\"krusgraph-view\"><OntoWait wait={opening}" in editor
    assert "<OntoWait wait={wait}" in views and "<Spinner label=" not in views
    for part in ("planMapView", "FlowView", "DataProductView"):
        assert f'import(/* webpackChunkName: ' in lazy and f'"./{part}")' in lazy
        assert f'from "./{part}"' not in editor and f'from "./{part}"' not in views
    # the item and its definition are read at the same time
    assert "Promise.all([callGetItem(workloadClient, itemObjectId), callGetItemDefinition(workloadClient, itemObjectId)])" in editor


def test_no_speed_claims_on_the_site():
    root = Path(__file__).resolve().parents[1] / "fabric_backend"
    for p in list((root / "page_templates").rglob("*.html")) + [root / "pages.py"]:
        text = p.read_text(encoding="utf-8").lower()
        assert "loads faster" not in text and "n223" not in text, p
