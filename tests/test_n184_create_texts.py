"""Round n184, addition 1: the card texts of the founder's live Create (9 November 2026, package 1.0.913).

(c) a card's steps carry no tool names: the gold card says "Run <the silver notebook's name> first", the report card
drops "export_item_definitions does not include reports" and keeps "refresh it once" only when this Create's model was
not refreshed (failed or skipped); (e) the pipeline says "created" when its own item did not exist, though the silver
and gold notebooks this Create made a moment earlier exist. The editor's texts (a, b, d, f) and the finish are in
workload/Workload/app/items/ModelItem/createWords.test.ts."""
import pytest

pytest.importorskip("jwt")

from fabric_backend import server, workload_api  # noqa: E402
from test_workload_api import keys  # noqa: E402,F401
from test_workload_build import EVERY_SCOPE, _build, make  # noqa: E402,F401

FLOW = [{"kind": "silver_notebook", "name": "demo_lh_silver"}, {"kind": "gold_views", "name": "demo_lh_gold"},
        {"kind": "pipeline", "name": "demo_lh_pipeline"}, {"kind": "semantic_model", "name": "demo_lh_model"},
        {"kind": "report", "name": "demo_lh_report"}, {"kind": "ontology", "name": "demo_lh_ontology"}]


def _cards(make, **extra):
    client, fake, priv = make(scp=EVERY_SCOPE)
    r, _ = _build(client, priv, FLOW, dry_run=False, **extra)
    out = r.json()
    assert out["refused"] == 0, [c.get("refusal") or c["answer"].get("error") for c in out["outputs"]]
    return {c["output"]: c for c in out["outputs"]}


def test_no_card_step_names_a_tool(make):
    cards = _cards(make)
    for kind, card in cards.items():
        for step in card.get("portal_steps") or []:
            assert not workload_api.TOOL_NAME.search(step), (kind, step)
            assert "export_item_definitions" not in step and "create_silver_notebook" not in step, (kind, step)


def test_the_gold_card_names_the_silver_notebook_of_this_create(make):
    steps = _cards(make)["gold_views"]["portal_steps"]
    assert steps[0].startswith("Run demo_lh_silver first: the gold views read its silver tables.")
    assert workload_api.plain_steps(["Run create_silver_notebook's notebook first: x"], {}) == ["Run the silver notebook first: x"]


@pytest.mark.parametrize("status,kept", [("refreshed", False), ("refreshing", False), ("failed", True), ("not_run", True), (None, False)])
def test_the_report_asks_for_a_refresh_only_when_create_did_not_refresh_the_model(status, kept):
    built = {"semantic_model": {"refresh": {"status": status}} if status else {}}
    steps = workload_api._portal_steps("report", {"after_creation": list(server.REPORT_AFTER_CREATION)}, {}, built)
    assert any(s.startswith("If the model was just created, refresh it once") for s in steps) is kept
    assert not any("export_item_definitions" in s for s in steps)
    assert steps[0].startswith("Open the report")


def test_the_report_card_of_a_live_create_drops_the_refresh_step_when_the_model_was_refreshed(make, monkeypatch):
    monkeypatch.setattr(workload_api, "refresh_new_model", lambda *a, **k: {"status": "refreshed"})
    cards = _cards(make)
    assert cards["semantic_model"]["refresh"]["status"] == "refreshed"
    assert not any("refresh" in s.lower() for s in cards["report"]["portal_steps"])


def test_a_pipeline_that_did_not_exist_says_created_though_its_notebooks_do(make):
    cards = _cards(make)
    assert cards["silver_notebook"]["would"] == "create" and cards["gold_views"]["would"] == "create"
    assert cards["pipeline"]["would"] == "create"                  # was "update": the notebooks made a moment earlier exist
    assert [c["type"] for c in cards["pipeline"]["created"]] == ["DataPipeline", "Notebook", "Notebook", "Notebook"]


@pytest.mark.parametrize("existing,would", [
    ({"Notebook:demo_lh_silver": "s1", "Notebook:demo_lh_gold": "g1"}, "create"),             # the founder's fresh workspace
    ({"DataPipeline:demo_lh_pipeline": "p1", "Notebook:demo_lh_silver": "s1"}, "update"),       # this Model built it before
])
def test_only_the_pipeline_item_itself_decides_updated(monkeypatch, existing, would):
    monkeypatch.setattr(server, "_find_item", lambda ws, name, headers, typ: existing.get(f"{typ}:{name}"))
    o = {"kind": "pipeline", "name": "demo_lh_pipeline"}
    chosen = {"silver_notebook": "demo_lh_silver", "gold_views": "demo_lh_gold"}
    got, refusal, _found = workload_api._ownership(o, chosen, {"schema": "shop"}, "ws", {}, set(existing.values()))
    assert refusal is None and got == would


def test_a_notebook_of_the_pipeline_made_by_someone_else_is_still_refused(monkeypatch):
    monkeypatch.setattr(server, "_find_item", lambda ws, name, headers, typ: "x1" if name == "demo_lh_gold" else None)
    o = {"kind": "pipeline", "name": "demo_lh_pipeline"}
    _w, refusal, _f = workload_api._ownership(o, {"silver_notebook": "demo_lh_silver", "gold_views": "demo_lh_gold"},
                                              {"schema": "shop"}, "ws", {}, set())
    assert refusal["kind"] == "already_exists"
