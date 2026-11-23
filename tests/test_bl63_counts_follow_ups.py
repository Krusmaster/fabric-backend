"""BL63 (23 November 2026): Gustav's decisions on BL51's open questions, on top of the counted active set.

1. A declared or confirmed link (R0, `confirmed`, `decided`) whose counts show no match at all is still not made active,
   and it carries a clear warning: in the model's summary (`active_by_counts.confirmed_without_match`), in the README's
   "What the counts decided", in analyze_schema's answer and in validate_plan's answer (`confirmed_without_match`).
   Counts only, never a row value.
2. No threshold: one matching row is "counted with matches".
3. The model on the gold views (DPM1), `analyze_schema` (graphs.analyze) and `join_path` follow the same counted active
   set when counts are passed. Without counts every answer is byte for byte as before (the golden tests hold that for
   the tools; here for the functions).

Synthetic samples only (sap_sd, sap_demo, shop, shop_faults), counted once on SQLite; nothing talks to Fabric.
"""
from __future__ import annotations

import json

import pytest

from fabric_backend import demo, evidence, gold, graphs, paths, sap_demo, sap_sample, semantic_model, shop_faults
from fabric_backend.infer import Relationship, plan as infer_plan
from test_bl33_one_count import _faults_db
from test_bl19_receipt_notebook import _execute
from test_bl51_active_relationships import (LAKEHOUSE, _ambiguous_plan, _filter_routes_ok, _link, _pairs, _tmdl_relationships)

CONFIRMED = [{"source": "newsletter_signups", "source_cols": ["customer_id"], "target": "customers",
              "target_columns": ["customer_id"], "target_cols": ["customer_id"]}]
GOLD_INFO = {"item_name": "sap_lh", "item_kind": "Lakehouse", "schema": "sap_sd", "schemas_enabled": True}


@pytest.fixture(scope="module")
def faults_confirmed():
    """shop_faults with the planted link that matches nothing (0 of 8) given as `confirmed`, counted on SQLite."""
    p = infer_plan(shop_faults.schema(), None, CONFIRMED)
    assert [r.rule for r in p.relationships if (r.source, r.target) == ("newsletter_signups", "customers")] == ["confirmed"]
    return p, evidence.validate(p, _execute(_faults_db()), 500)


@pytest.fixture(scope="module")
def sap_sd():
    src = sap_sample.source("sap_sd")
    p = infer_plan(src.schema)
    v = evidence.validate(p, src.execute, 500)
    yield p, v
    src.close()


# ------------------------------------------------------------------ 1. a confirmed link with no match -----------------

def test_a_confirmed_link_with_no_match_is_not_active_and_says_so(faults_confirmed):
    p, v = faults_confirmed
    active, inactive = semantic_model.active_relationships(p, p.relationships, v)
    assert ("newsletter_signups", "customers") not in _pairs(active)
    why = dict(((r.source, r.target), w) for r, w in inactive)[("newsletter_signups", "customers")]
    assert why.startswith("counted with no match: 8 of 8 rows with a value point at nothing in customers")
    assert "warning: newsletter_signups.customer_id -> customers is confirmed (`confirmed`), but validate_plan counted no match" in why
    before, _ = semantic_model.active_relationships(p, p.relationships)
    assert ("newsletter_signups", "customers") in _pairs(before)                  # without counts: as before


def test_the_warning_is_in_the_summary_and_the_readme(faults_confirmed):
    p, v = faults_confirmed
    d = semantic_model.draft(p, {**LAKEHOUSE, "schema": shop_faults.SCHEMA}, "m", validation=v)
    assert ("newsletter_signups", "customers", True) not in _tmdl_relationships(d["parts"])
    by = d["summary"]["active_by_counts"]
    warned = by["confirmed_without_match"]
    assert [(x["source"], x["target"], x["rule"], x["rows_with_value"], x["orphans"]) for x in warned] == [
        ("newsletter_signups", "customers", "confirmed", 8, 8)]
    # shop_faults' customers key is not unique in the rows (F1), so no link into customers is a relationship of the
    # model at all (n150); the warning is given all the same, since the confirmation itself is what is in doubt
    assert not [x for x in by["relationships"] if x["target"] == "customers"]
    assert not [x for x in by["relationships"] if x.get("warning")]
    readme = d["parts"]["README.generated.md"].split("### What the counts decided")[1]
    assert "**Warning: 1 declared or confirmed relationship(s) counted with no match, not made active.**" in readme
    assert f"- {warned[0]['warning']}." in readme
    assert "even when it is declared or confirmed" in by["rule"]


def test_a_confirmed_relationship_of_the_model_says_its_warning_in_its_own_row():
    p = _ambiguous_plan()
    p.relationships[1].rule = "confirmed"
    v = {"keys": [], "relationships": [_link("orders", 10, 0), {**_link("deliveries", 10, 10), "rule": "confirmed"}]}
    d = semantic_model.draft(p, {**LAKEHOUSE, "schema": "dbo"}, "m", validation=v)
    by = d["summary"]["active_by_counts"]
    entry = next(x for x in by["relationships"] if x["target"] == "deliveries")
    assert entry["active"] is False and entry["rule"] == "confirmed"
    assert entry["warning"] == by["confirmed_without_match"][0]["warning"]
    assert [x["target"] for x in by["relationships"] if x["active"]] == ["orders"]
    row = next(line for line in d["parts"]["README.generated.md"].splitlines() if line.startswith("| `ext.doc_no` | `deliveries`"))
    assert "| fails: 0 of 10 rows match | no |" in row and "warning: ext.doc_no -> deliveries is confirmed" in row


def test_an_inferred_link_with_no_match_carries_no_warning():
    """The planted link as R1 (BL51's case): inactive by rule 1, but it was never confirmed, so nothing is warned about."""
    p = infer_plan(shop_faults.schema())
    v = evidence.validate(p, _execute(_faults_db()), 500)
    d = semantic_model.draft(p, {**LAKEHOUSE, "schema": shop_faults.SCHEMA}, "m", validation=v)
    assert "confirmed_without_match" not in d["summary"]["active_by_counts"]
    assert "**Warning:" not in d["parts"]["README.generated.md"]
    assert graphs.confirmed_without_match(p, v) == []


def test_validate_plans_answer_carries_the_warning(faults_confirmed, monkeypatch):
    """The local server's validate_plan over the same rows, with the link confirmed: a warning with counts only."""
    from fabric_backend import mcp_server
    p, _ = faults_confirmed
    execute, close = shop_faults._sqlite(shop_faults.tables(), shop_faults.SCHEMA)
    monkeypatch.delenv("KRUSGRAPH_PLATFORM", raising=False)
    monkeypatch.delenv("KRUSGRAPH_CSN", raising=False)
    monkeypatch.setattr(mcp_server, "_execute_factory", lambda schema: execute)
    monkeypatch.setattr(mcp_server, "_plan_on", lambda ex, schema, keys=None, confirmed=None, decisions=True:
                        infer_plan(shop_faults.schema(schema), keys, confirmed))
    try:
        out = json.loads(mcp_server.validate_plan(schema=shop_faults.SCHEMA, confirmed=CONFIRMED))
        plain = json.loads(mcp_server.validate_plan(schema=shop_faults.SCHEMA))
    finally:
        close()
    [w] = out["confirmed_without_match"]
    assert (w["source"], w["target"], w["rule"], w["rows_with_value"], w["orphans"], w["active"]) == (
        "newsletter_signups", "customers", "confirmed", 8, 8, False)
    assert "is confirmed (`confirmed`), but validate_plan counted no match: 8 of 8 rows" in w["warning"]
    assert "confirmed_without_match" not in plain                               # nothing confirmed: the answer as before
    values = {x for _cols, rows in shop_faults.tables().values() for row in rows for x in row if isinstance(x, str) and len(x) >= 5}
    assert values and not [x for x in values if x in json.dumps(out["confirmed_without_match"])]     # counts only


def test_the_counts_win_over_a_confirmation_in_an_ambiguous_group():
    """Two targets for one column, the confirmed one matching nothing: it is not the one, and it is warned about."""
    p = _ambiguous_plan()
    p.relationships[1].rule = "confirmed"
    v = {"keys": [], "relationships": [_link("orders", 10, 0), {**_link("deliveries", 10, 10), "rule": "confirmed"}]}
    active, inactive = semantic_model.active_relationships(p, p.relationships, v)
    assert _pairs(active) == {("ext", "orders")}
    assert "warning: ext.doc_no -> deliveries is confirmed" in dict((r.target, w) for r, w in inactive)["deliveries"]
    assert [x["target"] for x in graphs.confirmed_without_match(p, v)] == ["deliveries"]


def test_analyze_schema_carries_the_warning_too(faults_confirmed):
    p, v = faults_confirmed
    a = graphs.analyze(p, v)
    assert [(x["source"], x["target"]) for x in a["confirmed_without_match"]] == [("newsletter_signups", "customers")]
    assert ("newsletter_signups", "customers") not in {(e["source"], e["target"]) for e in a["active_relationships"]}
    assert "confirmed_without_match" not in graphs.analyze(p)


# ------------------------------------------------------------------ 2. no threshold ------------------------------------

def test_one_matching_row_is_counted_with_matches():
    """1 of 100 rows matching is not "no match": the link is not refuted, and in an ambiguous group it is the one."""
    p = _ambiguous_plan()
    v = {"keys": [], "relationships": [_link("orders", 100, 99), _link("deliveries", 100, 100)]}
    active, inactive = semantic_model.active_relationships(p, p.relationships, v)
    assert _pairs(active) == {("ext", "orders")}
    assert dict((r.target, w) for r, w in inactive)["deliveries"].startswith("counted with no match")
    single = _ambiguous_plan()
    single.relationships = single.relationships[:1]
    active, inactive = semantic_model.active_relationships(single, single.relationships, {"keys": [], "relationships": [_link("orders", 100, 99)]})
    assert _pairs(active) == {("ext", "orders")} and inactive == []
    assert "counted, 1 of 100 rows with a value match" in graphs.counted_active_set(
        single, graphs.edges(single), {"keys": [], "relationships": [_link("orders", 100, 99)]})[0][0]["why"]


def test_two_links_with_one_match_each_still_leave_the_choice_to_a_person():
    p = _ambiguous_plan()
    v = {"keys": [], "relationships": [_link("orders", 50, 49), _link("deliveries", 50, 49)]}
    active, inactive = semantic_model.active_relationships(p, p.relationships, v)
    assert active == [] and all("a person chooses one with `confirmed`" in w for _r, w in inactive)


# ------------------------------------------------------------------ 3. gold, analyze_schema and join_path --------------

def test_analyze_schema_follows_the_models_active_set(sap_sd):
    p, v = sap_sd
    a = graphs.analyze(p, v)
    model, _ = semantic_model.active_relationships(p, p.relationships, v)
    assert sorted((e["source"], e["target"], tuple(e["columns"])) for e in a["active_relationships"]) == \
        sorted((r.source, r.target, tuple(r.source_cols)) for r in model)
    assert ("VBAP", "VBAK") in {(e["source"], e["target"]) for e in a["active_relationships"]}
    off = {(e["source"], e["target"]): e["why"] for e in a["inactive_relationships"]}
    assert off[("ZSD_ORDER_EXT", "LIKP")].startswith("counted with no match: 301 of 301")
    assert "chosen by validate_plan's counts, as in the semantic model" in a["summary"]
    assert a["active_by_counts"]["rule"] == semantic_model.COUNTED_SAID
    json.dumps(a)                                                                 # the answer stays plain JSON


@pytest.mark.parametrize("name", ["shop", "shop_faults", "sap_demo"])
def test_without_counts_analyze_and_join_path_are_as_before(name):
    from test_bl51_active_relationships import _counted
    p, v = _counted(name)
    plain = graphs.analyze(p)
    assert "active_by_counts" not in plain and "(chosen by" not in plain["summary"]
    forest, rest = graphs.spanning_forest(p, graphs.edges(p))
    assert [e["source"] + e["target"] for e in plain["active_relationships"]] == [e["source"] + e["target"] for e in forest]
    assert graphs.analyze(p, {"keys": [], "relationships": []}) == plain          # an answer that counted none of the links
    names = sorted(t.name for t in p.schema)
    for a, b in [(names[0], names[-1]), (names[1], names[-2])]:
        j = paths.join_path(p, a, b)
        assert j == paths.join_path(p, a, b, validation={"keys": [], "relationships": []})
        assert "active_by_counts" not in j and not any("active" in s for x in j["paths"] for s in x["steps"])


def test_join_path_follows_the_active_set_with_counts(sap_sd):
    p, v = sap_sd
    before = paths.join_path(p, "ZSD_ORDER_EXT", "LIKP")
    assert before["safest"]["tables"] == ["ZSD_ORDER_EXT", "LIKP"]                 # the R3 guess, 0 of 301 matching
    j = paths.join_path(p, "ZSD_ORDER_EXT", "LIKP", validation=v)
    assert j["active_by_counts"] is True
    assert j["safest"]["tables"] == ["ZSD_ORDER_EXT", "VBAK", "KNA1", "LIKP"]
    assert all(s["active"] for s in j["safest"]["steps"])
    assert "keeps active by validate_plan's counts" in j["safest"]["why"] and "a shorter path uses a relationship" in j["safest"]["why"]
    [direct] = [x for x in j["paths"] if x["hops"] == 1]
    assert direct["steps"][0]["active"] is False
    assert direct["steps"][0]["inactive_why"].startswith("counted with no match: 301 of 301")
    # the shortest paths themselves are the same as without counts; only the marks are added
    assert [x["tables"] for x in j["paths"]] == [x["tables"] for x in before["paths"]]


def test_join_path_says_when_only_an_inactive_link_connects():
    """Two tables connected only through links the counts refute: the path is given, and said to need USERELATIONSHIP."""
    p = _ambiguous_plan()
    v = {"keys": [], "relationships": [_link("orders", 10, 2), _link("deliveries", 10, 8)]}       # a person must choose
    j = paths.join_path(p, "ext", "orders", validation=v)
    assert j["active_by_counts"] is False and j["safest"]["tables"] == ["ext", "orders"]
    assert "USERELATIONSHIP" in j["safest"]["why"] and j["safest"]["steps"][0]["active"] is False


def _gold_sap_sd(sap_sd):
    p, v = sap_sd
    g = gold.spec(p, GOLD_INFO, "silver", "gold", dimensions=True)
    return p, v, g, semantic_model.gold_model(p, g, v)


def test_the_model_on_gold_follows_the_counts(sap_sd):
    p, v, g, og = _gold_sap_sd(sap_sd)
    d = semantic_model.draft_on_gold(p, GOLD_INFO, g, "m", validation=v)
    by = d["summary"]["active_by_counts"]
    assert by["rule"] == semantic_model.COUNTED_SAID
    on = {(a, b) for a, b, act in _tmdl_relationships(d["parts"]) if act}
    assert _filter_routes_ok(sorted(on))                                          # Power BI's rule, the calendar included
    # every gold link is counted as the source link it was made from, and said so when that link is another table's
    entries = {(x["source"], x["target"]): x for x in by["relationships"]}
    assert entries[("VBAP", "KNA1")]["counted_link"] == "VBAK.MANDT+KUNNR -> KNA1"
    assert entries[("VBAP", "KNA1")]["state"] == "holds" and entries[("VBAP", "KNA1")]["active"]
    # the star: an item view keeps both its customer and its material (the forest by certainty cut one of them)
    gp = og["plan"]
    forest, _, _ = semantic_model.active_set(gp, gp.relationships, v, counted=False)
    assert ("VBAP", "MARA") not in _pairs(forest) and ("VBAP", "MARA") in _pairs(
        semantic_model.active_set(gp, gp.relationships, v, og["source_plan"], basis=og["made_from"])[0])
    assert {("VBAP", "MARA"), ("VBAP", "KNA1"), ("LIPS", "MARA"), ("VBRK", "T001")} <= {(a.split(".")[0], b.split(".")[0]) for a, b in on}


def test_the_model_on_gold_never_activates_a_link_the_counts_refute():
    """shop_faults on gold, with its planted fault confirmed: a gold link made from a refuted source link is inactive."""
    p = infer_plan(shop_faults.schema(), None, CONFIRMED)
    v = evidence.validate(p, _execute(_faults_db()), 500)
    info = {"item_name": "lh", "item_kind": "Lakehouse", "schema": shop_faults.SCHEMA, "schemas_enabled": True}
    g = gold.spec(p, info, "silver", "gold", dimensions=True)
    d = semantic_model.draft_on_gold(p, info, g, "m", validation=v)
    by = d["summary"]["active_by_counts"]
    refuted = [x for x in by["relationships"] if x["state"] == "fails" and x["matched"] == 0]
    assert all(not x["active"] for x in refuted)
    assert all(x.get("warning") for x in refuted if x["rule"] == "confirmed")
    on = {(a, b) for a, b, act in _tmdl_relationships(d["parts"]) if act}
    assert _filter_routes_ok(sorted(on))


def test_the_model_on_gold_without_counts_is_as_before():
    """No counts: no active_by_counts, and the gold plan's forest by certainty, exactly as DPM1 wrote it."""
    p = demo.plan(demo.schema("shop"), keys=demo.DEMO_KEYS)
    g = gold.spec(p, demo.FLOW_INFO, "silver", "gold", dimensions=True)
    d = semantic_model.draft_on_gold(p, demo.FLOW_INFO, g, "shop_model")
    assert "active_by_counts" not in d["summary"]
    og = semantic_model.gold_model(p, g, None)
    gp = og["plan"]
    single = [r for r in gp.relationships if len(r.source_cols) == 1]
    forest, rest = graphs.spanning_forest(gp, [e for e in graphs.edges(gp) if e["rel"] in single])
    assert d["summary"]["relationships_active"] == len(forest)


def test_the_shop_model_on_gold_with_counts_obeys_power_bis_rule():
    p = demo.plan(demo.schema("shop"), keys=demo.DEMO_KEYS)
    g = gold.spec(p, demo.FLOW_INFO, "silver", "gold", dimensions=True)
    d = semantic_model.draft_on_gold(p, demo.FLOW_INFO, g, "shop_model", validation=demo.demo_validation())
    on = {(a.split(".")[0], b.split(".")[0]) for a, b, act in _tmdl_relationships(d["parts"]) if act}
    assert _filter_routes_ok(sorted(on))
    assert ("order_items", "customers") in on                                     # the line view's customer, as counted
    assert all(x["state"] == "holds" for x in d["summary"]["active_by_counts"]["relationships"])


def test_sap_demo_on_gold_with_counts_obeys_power_bis_rule():
    schema, execute = sap_demo.sqlite()
    p = infer_plan(schema)
    v = evidence.validate(p, execute, max_items=200)
    info = {"item_name": "sap_lh", "item_kind": "Lakehouse", "schema": "sap", "schemas_enabled": True}
    g = gold.spec(p, info, "silver", "gold", dimensions=True)
    d = semantic_model.draft_on_gold(p, info, g, "m", validation=v)
    assert "active_by_counts" in d["summary"]
    on = {(a.split(".")[0], b.split(".")[0]) for a, b, act in _tmdl_relationships(d["parts"]) if act}
    assert _filter_routes_ok(sorted(on))


def test_gold_model_records_the_source_link_of_each_gold_link(sap_sd):
    _p, _v, _g, og = _gold_sap_sd(sap_sd)
    made = og["made_from"]
    for r in og["plan"].relationships:
        if r.rule == "aa1-prediction":
            continue
        src = made[id(r)]
        assert isinstance(src, Relationship) and src.target == r.target and src in og["source_plan"].relationships
