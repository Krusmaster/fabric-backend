"""W5 (24 November 2026, after W4 was deployed): verify_build compares the pipeline's notebooks with the keys Create used.

The Krusgraph Model's Create builds silver and the check on the keys its row check passed (workload_api.checked_keys
into Plan.checked_keys: silver removes duplicates on them, the check enforces them). verify_build rebuilt the dry run
from the plan alone, so those keys came out guessed: the silver notebook read "differs" from its `# Key ... (rule K2`
comment on, and the check notebook from `"rule": "K2"` (Fabric) against `"not_enforced": ...` (the dry run), with nothing
changed in Fabric. Now the dry run is rebuilt on the key checks the Model recorded (its review.json), else on the keys
counted again against the rows, else the two notebooks say "not checked" (key validation unknown).

Also: in a build in another workspace, the refresh step names the build's workspace, where the model is.

Fabric's REST API and the SQL endpoint are test doubles (test_n229_verify_build's workspace); the rows are the synthetic
shop sample. No tenant, no customer data.
"""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from fabric_backend import profile, review as R, server, verify_build as vb, workload_api as W
from test_n229_verify_build import INFO, WS, fabric, rows  # noqa: F401  (fixtures)
from test_w4_tenant_followups import BUILD, elsewhere  # noqa: F401  (fixture)

MODEL_ITEM = "55555555-5555-5555-5555-555555555555"
PIPELINE_ID = "66666666-6666-6666-6666-666666666666"
NOTEBOOKS = ("silver_shop", "gold_shop", "pipeline_shop_check")


def _checks(p, execute, only: set[str] | None = None) -> dict:
    """validate_plan's counts of the plan's keys on the rows (the Model's "Check against the rows")."""
    out, _ = profile.validate_with_profile(p, execute, 60, False)
    return {"keys": [k for k in out["keys"] if only is None or k["table"] in only], "relationships": []}


def _review(p, execute, only=None) -> dict:
    return R.build(p, p, {"platform": "fabric", "source": "demo_lh", "schema": "shop"}, checks=_checks(p, execute, only),
                   checked_at="2026-11-20T09:00Z")


def _built_with(fabric, rv: dict) -> dict:
    """The notebooks in Fabric as the Model's Create wrote them: on the plan with the review's key checks (run_build_many's
    adjust_checked), the same functions, nothing else changed."""
    checked = W.checked_keys(R.read(rv))
    build = server._pipeline_build(replace(fabric.plan, checked_keys=checked), INFO, "shop", "silver", "gold", None, False,
                                   "pipeline_shop", "", "")
    fabric.notebooks = {n["name"]: n["content"] for n in build["notebooks"]}
    return checked


def _with_model(fabric, monkeypatch, rv: dict, created_id: str = "p-1"):
    """A Krusgraph Model in the workspace whose outputs.json lists the pipeline and whose review.json holds the checks."""
    fabric.items.append({"id": MODEL_ITEM, "displayName": "shop_product", "type": "Org.Krusgraph.Model"})
    parts = fabric.parts

    def read(ws, route, item_id, headers, fmt=None):
        if route == "items" and item_id == MODEL_ITEM:
            fabric.reads.append(f"items/{item_id}")
            return {"outputs.json": json.dumps({"created": [{"type": "DataPipeline", "id": created_id, "name": "pipeline_shop",
                                                             "workspace": WS, "output": "pipeline"}]}),
                    "review.json": json.dumps(rv)}
        return parts(ws, route, item_id, headers, fmt)
    monkeypatch.setattr(server, "_item_definition_parts", read)


def verify(items=None, **kw):
    return json.loads(server.verify_build("demo", "demo_lh", items or {"pipeline": "pipeline_shop"}, schema="shop", **kw))


def line(out, name):
    return next(x for x in out["lines"] if x["item"] == name)


# ------------------------------------------------------------------ the cause, reproduced ----------------------------

def test_the_plan_alone_makes_guessed_keys_where_create_enforced_checked_ones(fabric, rows):
    """The live report of 24 November 2026: the silver notebook differs from a `# Key ... (rule K2` line, the check
    notebook from `"rule": "K2"` against `"not_enforced"`: silver.spec dedupes a K2 key only with Plan.checked_keys."""
    plain = server._pipeline_build(fabric.plan, INFO, "shop", "silver", "gold", None, False, "pipeline_shop", "", "")
    _built_with(fabric, _review(fabric.plan, rows))
    silver, gold, check = (vb.compare_notebook(n["content"], fabric.notebooks[n["name"]])["differences"] for n in plain["notebooks"])
    assert silver and "# Key" in silver[0]["said"] and "rule K2" in silver[0]["said"]
    assert check and "not_enforced" in check[0]["said"] and '"rule": "K2"' in check[0]["said"]
    assert not gold                                                         # gold verified live, and here
    assert vb.enforces_fewer_keys(plain["notebooks"][2]["content"], fabric.notebooks["pipeline_shop_check"])
    assert not vb.enforces_fewer_keys(plain["notebooks"][1]["content"], fabric.notebooks["gold_shop"])


# ------------------------------------------------------------------ 1. the Model's record -----------------------------

def test_keys_validated_at_create_are_read_from_the_model_and_verify(fabric, monkeypatch, rows):
    rv = _review(fabric.plan, rows)
    _built_with(fabric, rv)
    _with_model(fabric, monkeypatch, rv)
    out = verify()
    assert {x["state"] for x in out["lines"]} == {"verified"}, out["result_lines"]
    for n in ("silver_shop", "pipeline_shop_check"):
        assert line(out, n)["notes"] == ["Keys as the key checks the Krusgraph Model shop_product recorded at Create."]
    assert f"items/{MODEL_ITEM}" in fabric.reads


def test_with_the_model_s_record_a_changed_notebook_still_differs(fabric, monkeypatch, rows):
    rv = _review(fabric.plan, rows)
    _built_with(fabric, rv)
    _with_model(fabric, monkeypatch, rv)
    fabric.notebooks["silver_shop"] += "\nprint('changed in Fabric')\n"
    out = verify()
    assert line(out, "silver_shop")["state"] == "differs" and line(out, "pipeline_shop_check")["state"] == "verified"


def test_a_model_that_did_not_build_these_items_is_no_record(fabric, monkeypatch, rows):
    rv = _review(fabric.plan, rows)
    _built_with(fabric, rv)
    _with_model(fabric, monkeypatch, rv, created_id="77777777-7777-7777-7777-777777777777")
    out = verify()                                                          # the rows are counted again instead
    assert {x["state"] for x in out["lines"]} == {"verified"}, out["result_lines"]
    assert "counted again against the rows now" in line(out, "silver_shop")["notes"][0]


def test_the_model_editor_s_verify_hands_its_review_s_key_checks(fabric, rows):
    rv = _review(fabric.plan, rows)
    _built_with(fabric, rv)
    fabric.items[4]["id"] = PIPELINE_ID
    created = [{"type": "DataPipeline", "id": PIPELINE_ID, "name": "pipeline_shop", "workspace": WS, "output": "pipeline"}]
    out = W.run_verify(W.verify_request({"workspace": WS, "source": INFO["item_id"], "source_name": "demo_lh", "schema": "shop",
                                         "review": rv, "created": created}))
    assert [x["item"] for x in out["lines"]] == ["pipeline_shop", *NOTEBOOKS]
    assert {x["state"] for x in out["lines"]} == {"verified"}, out["result_lines"]
    assert line(out, "silver_shop")["notes"] == ["Keys as the key checks of this Model's review."]


# ------------------------------------------------------------------ 2. no record: counted again ----------------------

def test_without_a_record_the_keys_are_counted_again_and_the_dates_are_not_compared(fabric, rows):
    _built_with(fabric, _review(fabric.plan, rows))
    assert "checked against the rows on 20 November 2026" in fabric.notebooks["silver_shop"]
    out = verify()
    assert {x["state"] for x in out["lines"]} == {"verified"}, out["result_lines"]
    note = line(out, "pipeline_shop_check")["notes"][0]
    assert note.startswith("Keys counted again against the rows now (6 unique and never NULL)") and "dates" in note


def test_a_build_on_the_plan_s_own_keys_is_verified_without_counting(fabric, monkeypatch):
    def no_sql(*a, **k):
        raise AssertionError("nothing is counted when the notebooks match the plan's keys")
    monkeypatch.setattr(server, "_recounted_keys", no_sql)
    out = verify()
    assert {x["state"] for x in out["lines"]} == {"verified"} and "notes" not in line(out, "silver_shop")


def test_a_changed_notebook_on_the_plan_s_keys_still_differs(fabric):
    fabric.notebooks["silver_shop"] += "\nprint('changed in Fabric')\n"
    assert line(verify(), "silver_shop")["state"] == "differs"


# ------------------------------------------------------------------ 3. neither: not checked ---------------------------

def test_some_keys_checked_and_no_record_is_not_checked_key_validation_unknown(fabric, rows):
    _built_with(fabric, _review(fabric.plan, rows, only={"customers", "orders"}))
    out = verify()
    for n in ("silver_shop", "pipeline_shop_check"):
        ln = line(out, n)
        assert ln["state"] == "not checked" and server.KEYS_UNKNOWN in ln["said"], ln["said"]
        assert "does not match it either" in ln["said"]
    assert line(out, "gold_shop")["state"] == "verified" and line(out, "pipeline_shop")["state"] == "verified"


def test_keys_that_cannot_be_counted_are_not_checked_key_validation_unknown(fabric, monkeypatch, rows):
    _built_with(fabric, _review(fabric.plan, rows))

    def refused(*a, **k):
        raise RuntimeError("the SQL endpoint did not answer")
    monkeypatch.setattr(server, "_recounted_keys", refused)
    out = verify()
    ln = line(out, "silver_shop")
    assert ln["state"] == "not checked" and "key validation unknown" in ln["said"] and "did not answer" in ln["said"]


# ------------------------------------------------------------------ 4. the refresh step names the build's workspace ---

def test_the_refresh_step_of_a_build_in_another_workspace_names_that_workspace(elsewhere):
    elsewhere.refreshes = []
    out = json.loads(server.verify_build("demo_build", "demo_lh", {"semantic_model": "shop_model"}, schema="shop",
                                         source_workspace="demo"))
    step = out["next_steps"][0]
    assert step["label"] == "Refresh the model once" and step["workspace"] == "demo_build"
    assert "shop_model in the workspace demo_build" in step["ask"] and "source in demo" in step["ask"]
    assert 'workspace="demo"' not in step["ask"] and "create_semantic_model with" not in step["ask"]


def test_the_refresh_step_in_the_source_s_own_workspace_is_unchanged(fabric):
    fabric.refreshes = []
    step = verify({"semantic_model": "shop_model"})["next_steps"][0]
    assert "create_semantic_model with" in step["ask"] and 'workspace="demo"' in step["ask"] and "workspace" not in step
