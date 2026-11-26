"""SC1 (26 November 2026): two things the founder saw on the live Claude run on the demo workspace (synthetic data).

1. A creating tool outside the start path's build steps showed the step label of another tool: create_ontology's dry run
   said "Step 4 of 5: Build silver and gold". Every creating tool with a card now has a heading that fits it; one outside
   the path (the ontology, the API for GraphQL, the report) shows no "Step n of 5". The start path's own labels (silver
   and gold, the semantic model, the data agent) are unchanged.
2. Step 5 of the start card offered only the pipeline, the model and the agent. It now also offers the API for GraphQL
   and the ontology, unticked (the default build stays the three of SM3), with the same pattern: names confirmed first,
   one Create per item, a second tap to create. A name an item already has moves to <name>_2; Done lists what was made.

Also: verify_build after create_ontology made shop_ontology_2 verified the older shop_ontology; the next step now names
the item just created, and verify_build says which item it checked and names the others built from the same plan.

Everything runs on synthetic data: the shop of fabric_backend/seed.py through tests/golden_support's fake Fabric.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fabric_backend import after_create, coach, mcp_apps, mcp_apps_build, mcp_apps_start, server, start_flow
from test_golden import SRC, fabric  # noqa: F401  (the hosted server against the synthetic shop workspace)

TESTS = Path(__file__).resolve().parent
B = {"workspace": "demo", "source": "demo_lh", "schema": "shop"}
CARD_TOOLS = mcp_apps_build.BUILD_TOOLS                    # the creating tools drawn on a card
ON_PATH = {"create_semantic_model": "Semantic model"}      # on the coach's build path: its step label stays
OWN = {"create_ontology": "Ontology", "create_backend": "API for GraphQL", "create_report": "Report"}


def test_every_creating_tool_with_a_card_is_listed_here():
    assert set(CARD_TOOLS) == set(ON_PATH) | set(OWN)


@pytest.mark.parametrize("tool", sorted(OWN))
@pytest.mark.parametrize("dry", [True, False])
def test_a_creating_tool_outside_the_path_has_its_own_heading_and_no_step(tool, dry):
    c = coach.coach(tool, {**B, "name": "shop_x", "dry_run": dry}, {"would_create": []})
    assert c["n"] is None and c["title"] == OWN[tool]
    assert "Build silver and gold" not in json.dumps(c) and "Bronze to silver" not in c["line"]
    assert c["text"].startswith(f"Coach ({OWN[tool]}, outside the five steps of Start Krusgraph)")
    assert "step 4 of 5" not in c["text"].lower()
    if dry:
        assert c["line"] == coach.LINE["dry_run"]
    else:
        assert c["line"].startswith("Done: the ") and OWN[tool].split()[0].lower() in c["line"].lower()
    assert set(coach.card(c)) == {"n", "of", "stage", "title", "who", "name", "pose", "line"}


@pytest.mark.parametrize("tool,title", [("create_semantic_model", "Semantic model"), ("create_pipeline", "Build silver and gold"),
                                        ("create_data_agent", "Data agent")])
def test_the_start_paths_own_labels_are_unchanged(tool, title):
    c = coach.coach(tool, {**B, "name": "shop_x", "dry_run": True}, {"would_create": []})
    assert (c["n"], c["of"], c["title"]) == (4, 5, title)
    assert c["text"].startswith(f"Coach (step 4 of 5: {title})")


def test_an_error_of_a_tool_outside_the_path_keeps_its_heading():
    c = coach.coach("create_ontology", {**B, "name": "shop_ontology"}, {"error": "No.", "kind": "consent"})
    assert c["n"] is None and c["title"] == "Ontology" and c["line"] == coach.LINE["error"]


def test_the_card_draws_no_step_when_there_is_none():
    from fabric_backend import mcp_apps_next
    js = mcp_apps_next.js()
    assert '(Number(c.n) > 0 ? "Step " + Number(c.n) + " of "' in js


def _sc(tool, /, **kw):
    return mcp_apps.structured(getattr(server, tool), tool)(**kw)


@pytest.mark.parametrize("tool,name", [("create_ontology", "shop_ontology"), ("create_backend", "shop_api")])
def test_the_hosted_dry_run_carries_its_own_heading(fabric, tool, name):
    r = _sc(tool, **SRC, name=name)
    d = r.structured_content
    assert d["coach"]["title"] == OWN[tool] and d["coach"]["n"] is None
    lead = "\n\n".join(c.text for c in r.content[:-1])
    assert f"Coach ({OWN[tool]}, outside the five steps" in lead and "Build silver and gold" not in lead


# ------------------------------------------------------------------ step 5 ---------------------------------------------

def test_step_5_offers_the_api_and_the_ontology_unticked():
    a = start_flow.guide(**B, step="create", taken=[])
    assert a["suggested"] == ["shop_pipeline", "shop_model", "shop_agent"]          # SM3's default build, unchanged
    assert [(o["tool"], o["name"]) for o in a["optional"]] == [("create_backend", "shop_api"), ("create_ontology", "shop_ontology")]
    confirm = [x for x in a["actions"] if x["kind"] == "confirm"]
    assert len(confirm) == 1 and confirm[0]["arguments"]["create"] == a["suggested"]
    assert "shop_api (an API for GraphQL), shop_ontology (a Fabric IQ ontology)" in a["then"]
    assert "shop_report" not in a["then"]                  # the question names what the button confirms
    assert "taken" not in a["chosen"]


def test_ticked_ones_get_their_own_create_after_the_confirmation():
    names = ["shop_pipeline", "shop_model", "shop_api", "shop_ontology", "shop_agent"]
    b = start_flow.guide(**B, step="create", create=names, confirm=True, taken=[])
    assert [x["label"] for x in b["actions"]] == [f"Create {n}" for n in names]
    assert all(x["kind"] == "create" and x["arguments"]["dry_run"] is False for x in b["actions"])
    by = {x["tool"]: x for x in b["actions"]}
    assert by["create_ontology"]["arguments"]["name"] == "shop_ontology" and by["create_backend"]["arguments"]["name"] == "shop_api"
    assert b["after"]["arguments"]["create"] == names and b["after"]["arguments"]["step"] == "done"


def test_a_name_an_item_has_moves_to_2_and_says_so():
    taken = ["shop_ontology", "shop_api", "shop_api_2"]
    d = start_flow.guide(**B, step="dry_run", taken=taken)
    assert {w["tool"]: w["name"] for w in d["would_build"]}["create_ontology"] == "shop_ontology_2"
    assert any("shop_ontology_2 because shop_ontology is already in this workspace" in x for x in d["renamed"])
    a = start_flow.guide(**B, step="create", taken=taken)
    assert {o["name"] for o in a["optional"]} == {"shop_api_3", "shop_ontology_2"}
    refused = start_flow.guide(**B, step="create", create=["shop_ontology"], confirm=True, taken=taken)
    assert refused.get("needs_confirmation") and not [x for x in refused["actions"] if x["kind"] == "create"]
    ok = start_flow.guide(**B, step="create", create=["shop_ontology_2"], confirm=True, taken=taken)
    assert [x["arguments"]["name"] for x in ok["actions"]] == ["shop_ontology_2"]


def test_without_the_item_names_nothing_is_created_from_step_5():
    e = start_flow.guide(**B, step="create", create=["shop_pipeline"], confirm=True, taken_error="403 Forbidden")
    assert not [x for x in e["actions"] if x["kind"] == "create"] and "cannot promise these names are free" in e["say"]


def test_done_lists_what_was_made():
    d = start_flow.guide(**B, step="done", create=["shop_pipeline", "shop_ontology_2"], taken=["shop_pipeline", "shop_ontology"])
    assert d["say"] == "Done. What next?"
    assert d["made"] == ["shop_pipeline"] and d["not_made"] == ["shop_ontology_2"]
    assert d["lines"] == ["Made: shop_pipeline.", "Not in Fabric yet: shop_ontology_2."]
    schedule = next(x for x in d["actions"] if x["label"] == "Schedule it")
    assert "shop_pipeline " in schedule["say"]                                     # the made pipeline, not shop_pipeline_2


def test_the_start_tool_reads_the_item_names_on_step_5(fabric, monkeypatch):
    monkeypatch.setattr(server, "_item_names", lambda workspace, ctx: ["shop_ontology"])
    d = json.loads(server.start(**SRC, step="create"))
    assert {o["name"] for o in d["optional"]} == {"shop_api", "shop_ontology_2"}

    def fail(workspace, ctx):
        raise RuntimeError("403 Forbidden")
    monkeypatch.setattr(server, "_item_names", fail)
    d = json.loads(server.start(**SRC, step="create", create=["shop_pipeline"], confirm=True))
    assert d["names_unread"] == "403 Forbidden" and not [x for x in d["actions"] if x["kind"] == "create"]


# ------------------------------------------------------------------ verify_build ---------------------------------------

def test_the_next_step_verifies_the_item_just_created():
    built = {"ontology": ["shop_ontology_2", "shop_ontology"]}          # the listing has the new one first
    out = after_create.next_steps("ontology", {**B}, built, "shop_ontology_2")
    verify = next(s for s in out["next_steps"] if s["step"] == "verify")
    assert verify["args"]["items"]["ontology"] == "shop_ontology_2"


def test_verify_build_says_which_item_it_checked_and_names_the_others():
    listing = [{"displayName": n, "type": "Ontology", "description": "Created by Krusgraph from demo_lh (shop)"}
               for n in ("shop_ontology", "shop_ontology_2")]
    out: dict = {}
    server._verify_which(out, {"ontology": "shop_ontology"}, listing, "demo_lh", "shop", {"item_name": "demo_lh"})
    assert out["checked_items"] == {"ontology": "shop_ontology"} and out["also_built"] == {"ontology": ["shop_ontology_2"]}
    assert out["which"].startswith("Checked shop_ontology; also built from demo_lh (shop): shop_ontology_2.")
    one: dict = {}
    server._verify_which(one, {"ontology": "shop_ontology_2"}, listing[1:], "demo_lh", "shop", {"item_name": "demo_lh"})
    assert one == {"checked_items": {"ontology": "shop_ontology_2"}}


# ------------------------------------------------------------------ the cards at 390 px --------------------------------

needs_browser = pytest.mark.skipif(not shutil.which("node") or subprocess.run(["node", "-e", "require('playwright')"],
                                                                              capture_output=True).returncode != 0,
                                   reason="node + playwright not available")


def _result(answer: dict) -> dict:
    text = json.dumps(answer)
    return {"content": [{"type": "text", "text": text}], "structuredContent": answer}


def _browse(tmp_path, html: str, data: dict) -> dict:
    (tmp_path / "card.html").write_text(html, encoding="utf-8")
    (tmp_path / "data.json").write_text(json.dumps(data), encoding="utf-8")
    run = subprocess.run(["node", str(TESTS / "wb13_card_browser.js"), str(tmp_path / "card.html"), str(tmp_path / "data.json")],
                         capture_output=True, text=True, timeout=180)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout)
    assert out["errors"] == [] and not out["overflow"], out["errors"]
    return out


@needs_browser
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_step_5_ticks_the_ontology_and_confirms_it_at_390(tmp_path, scheme):
    answer = start_flow.guide(**B, step="create", taken=[])
    answer["coach"] = coach.card(coach.coach("start", {**B, "step": "create"}, answer))
    first = _browse(tmp_path, mcp_apps_start.card_html(), {"result": _result(answer), "scheme": scheme, "width": 390,
                                                            "frame": 900, "caps": {"serverTools": {}}})
    assert all(n in first["text"] for n in ("shop_pipeline", "shop_model", "shop_agent", "shop_api", "shop_ontology"))
    assert [b["text"] for b in first["buttons"] if b["primary"]] == ["Confirm these names"]
    names = ["shop_pipeline", "shop_model", "shop_agent", "shop_ontology"]
    confirmed = start_flow.guide(**B, step="create", create=names, confirm=True, taken=[])
    out = _browse(tmp_path, mcp_apps_start.card_html(),
                  {"result": _result(answer), "scheme": scheme, "width": 390, "frame": 900, "caps": {"serverTools": {}},
                   "reply": _result(confirmed),
                   "clicks": [{"css": 'input[data-name="shop_ontology"]'}, {"css": 'button[data-kind="confirm"]'}]})
    assert "Create shop_ontology" in [b["text"] for b in out["buttons"]]
    calls = [m for m in out["log"] if m.get("method") == "tools/call"]
    assert calls and calls[-1]["params"]["name"] == "start"
    assert calls[-1]["params"]["arguments"]["create"] == names
    assert calls[-1]["params"]["arguments"]["confirm"] is True


@needs_browser
def test_the_ontology_card_shows_no_step_at_390(fabric, tmp_path):
    r = _sc("create_ontology", **SRC, name="shop_ontology")
    res = {"content": [{"type": "text", "text": c.text} for c in r.content], "structuredContent": r.structured_content}
    out = _browse(tmp_path, mcp_apps_build.card_html(), {"result": res, "args": {**SRC, "name": "shop_ontology"},
                                                         "width": 390, "frame": 900})
    assert "Ontology" in out["text"] and "Step 4 of 5" not in out["text"] and "Build silver and gold" not in out["text"]


# ------------------------------------------------------------------ every card: its own step, not the next one's -------

CLEAN = {"totals": {"keys": {"checked": 6, "passed": 6, "failed": 0}, "relationships": {"checked": 7, "passed": 7, "failed": 0}}}


def test_a_clean_check_card_is_the_check_step_not_silver_and_gold():
    c = coach.coach("validate_plan", B, CLEAN)
    assert (c["n"], c["title"], c["who"]) == (2, "Check the links against the rows", "thinker")
    assert "Bronze to silver" not in c["line"] and c["line"].startswith("Every key and link holds in the rows.")
    assert c["primary"]["label"] == "Build silver and gold (dry run first)"            # the next step is unchanged
    bad = coach.coach("validate_plan", B, {"totals": {"keys": {"checked": 6, "passed": 5, "failed": 1}}})
    assert (bad["n"], bad["title"]) == (3, "You decide the open links")


@pytest.mark.parametrize("tool,n,title", [("plan_backend", 2, "Krusgraph reads the tables"),
                                          ("gold_views_draft", 4, "Build silver and gold"),
                                          ("semantic_model_draft", 4, "Semantic model")])
def test_a_card_on_the_path_says_its_own_step(tool, n, title):
    c = coach.coach(tool, B, CLEAN if tool == "plan_backend" else {})
    assert (c["n"], c["title"]) == (n, title)


@pytest.mark.parametrize("tool", ["ontology_draft", "domain_draft", "dbt_schema", "requirements_draft", "verify_build"])
def test_a_card_outside_the_path_has_its_own_heading(tool):
    c = coach.coach(tool, B, {"summary": "x"})
    assert c["n"] is None and c["title"] == coach.OWN_TITLE[tool]
    assert "Build silver and gold" not in c["title"] and "Bronze to silver" not in c["line"]
    assert c["text"].startswith(f"Coach ({coach.OWN_TITLE[tool]}, outside the five steps")


def test_the_hosted_check_card_says_the_check_or_the_decisions(fabric):
    r = _sc("validate_plan", **SRC)
    d = r.structured_content
    assert (d["coach"]["n"], d["coach"]["title"]) in ((2, "Check the links against the rows"), (3, "You decide the open links"))
    assert "Build silver and gold" != d["coach"]["title"]


# ------------------------------------------------------------------ the verify card names what differs ----------------

def _verify_answer():
    from fabric_backend import verify_build as v
    lines = [v.line("api", "shop_api_2", {"differences": [], "checked": {"types": 5}}),
             v.line("semantic_model", "shop_model", {"differences": [{"said": "Relationship orders.customer_id to customers is missing."}],
                                                     "checked": {"tables": 5}}),
             v.line("report", "shop_report", not_checked="not read in time")]
    out = v.result(lines, None)
    out["fixes"] = [{"item": "shop_model", "label": "Update the model in place"}]
    out["note"] = "Unit-tested. " + __import__("fabric_backend.tool_status", fromlist=["x"]).answer_note("verify_build")
    return out


def test_the_verify_card_lists_what_differs_first_and_the_fixes():
    from fabric_backend import mcp_apps_words
    w = mcp_apps_words.card("verify_build", _verify_answer())
    assert w["title"] == "Verify what was built"
    assert w["lines"][0].startswith("shop_model (semantic model): differs.") and "orders.customer_id" in w["lines"][0]
    assert w["lines"][1].startswith("shop_report (report): not checked.")
    assert "Fix for shop_model: Update the model in place" in w["lines"]
    assert not any("verified" in x.split(".")[0] for x in w["lines"])               # the verified ones are behind Show
    assert len(w["notes"][0]["items"]) == 3 and w["notes"][0]["items"][-1].startswith("shop_api_2")


def test_the_verify_note_comes_from_tool_status(monkeypatch):
    from fabric_backend import tool_status
    monkeypatch.setattr(tool_status, "answer_note", lambda tool: f"STATUS-OF-{tool}")
    assert "STATUS-OF-verify_build" in _verify_answer()["note"]
    src = Path(server.__file__).read_text(encoding="utf-8")
    assert '_tool_status.answer_note("verify_build")' in src
    for mod in ("mcp_apps.py", "mcp_apps_result.py", "mcp_apps_build.py", "mcp_apps_words.py", "mcp_apps_next.py"):
        assert "Not yet run against a live workspace" not in (Path(server.__file__).with_name(mod)).read_text(encoding="utf-8")


@needs_browser
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_the_verify_card_shows_each_item_not_a_key_dump_at_390(tmp_path, scheme):
    from fabric_backend import mcp_apps_words
    d = _verify_answer()
    d["kg_card"] = mcp_apps_words.card("verify_build", d)
    out = _browse(tmp_path, mcp_apps_build.card_html(), {"result": _result(d), "scheme": scheme, "width": 390, "frame": 1400,
                                                         "clicks": [{"css": "summary", "text": "Show details"}]})
    text = out["text"]
    assert text.index("shop_model (semantic model): differs") < text.index("Show details")
    det = text[text.index("Show details"):]
    assert det.index("Differs: shop_model") < det.index("Not checked: shop_report") < det.index("Verified: shop_api_2")
    assert "Fix: shop_model: Update the model in place" in det
    for dump in ("Counts: ", "Lines: ", "Result lines: ", "Sql: "):
        assert dump not in det


# ------------------------------------------------------------------ verify_build finds what "Already built" names ------

LISTING = [{"id": "m1", "displayName": "shop_model", "type": "SemanticModel", "description": "Created by Krusgraph from demo_lh (shop)"},
           {"id": "r1", "displayName": "shop_overview", "type": "Report", "description": "Created by Krusgraph on the semantic model shop_model"}]


def test_verify_takes_the_report_already_built_when_the_default_name_is_not_there():
    found = {"report": None, "semantic_model": LISTING[0]}
    said = server._verify_built_instead(found, {"report": "shop_report", "semantic_model": "shop_model"}, {}, LISTING,
                                        "demo_lh", "shop", {"item_name": "demo_lh"})
    assert found["report"]["displayName"] == "shop_overview"
    assert said == ["No report is named shop_report; checked shop_overview, the report built from demo_lh (shop)."]
    # the same source as "Already built" after a Create
    built = after_create.built_from_plan(LISTING, "demo_lh", "shop", "demo_lh")
    assert built["report"] == ["shop_overview"]


def test_verify_names_the_candidates_and_picks_none_when_there_are_several():
    two = LISTING + [{"id": "r2", "displayName": "shop_sales", "type": "Report",
                      "description": "Created by Krusgraph on the semantic model shop_model"}]
    found = {"report": None}
    said = server._verify_built_instead(found, {"report": "shop_report"}, {}, two, "demo_lh", "shop", {"item_name": "demo_lh"})
    assert found["report"] is None and "shop_overview, shop_sales" in said[0] and "Name one in items" in said[0]
    named = {"report": None}                                   # an id recorded at Create is never swapped
    assert server._verify_built_instead(named, {"report": "x"}, {"report": {"id": "r9", "name": "x"}}, LISTING,
                                        "demo_lh", "shop", {"item_name": "demo_lh"}) == [] and named["report"] is None
