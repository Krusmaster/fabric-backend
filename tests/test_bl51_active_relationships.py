"""BL51 (23 November 2026, backlog C-33): the counted evidence decides which relationships of the semantic model draft
are active.

F1 (docs/FINDINGS-13NOV.md B7, docs/FINDINGS-13NOV-ADDENDUM.md XA2 and XB1): on the SAP-shaped sample the order header
was cut off from its items and its customer, and `ZSD_ORDER_EXT -> LIKP`, a guess by R3 that validate_plan counts as 301
of 301 rows pointing at nothing, was active. Here, on the synthetic samples `sap_sd`, `sap_demo`, `shop_faults` and
`shop`, with validate_plan's answer counted once on SQLite:

- a link counted with no match is never active, and says so with the count;
- on `sap_sd` VBAP -> VBAK and VBAK -> KNA1 are active, in the plan and in the draft on the silver layer;
- columns that point at several tables: the counted one wins; when the counts do not choose, none is active and a
  person chooses (`confirmed`);
- Power BI's rule holds in every draft: no table filters another by two routes (the calendar included);
- every relationship is explained with its count, and no row value is written;
- without counts nothing changes: the forest by certainty decides exactly as before (the golden tests hold that too).

SQLite only, synthetic rows only; nothing talks to Fabric, Azure or any service.
"""
from __future__ import annotations

import json
import re

import pytest

from fabric_backend import evidence, graphs, sap_demo, sap_sample, semantic_model, shop_faults
from fabric_backend.infer import Relationship, plan as infer_plan
from fabric_backend.platforms import local
from fabric_backend.schema import Schema
from test_bl33_one_count import _faults_db
from test_bl19_receipt_notebook import _execute, _sap_db, _shop_db

LAKEHOUSE = {"item_name": "lh", "item_kind": "Lakehouse"}


@pytest.fixture(scope="module")
def sap_sd():
    src = sap_sample.source("sap_sd")
    p = infer_plan(src.schema)
    v = evidence.validate(p, src.execute, 500)
    yield p, v
    src.close()


def _counted(name: str):
    db, schema = {"sap_demo": (_sap_db, lambda: sap_demo.sqlite()[0]),
                  "shop_faults": (_faults_db, shop_faults.schema),
                  "shop": (_shop_db, lambda: local.sample_source().schema)}[name]
    p = infer_plan(schema())
    return p, evidence.validate(p, _execute(db()), 500)


def _pairs(rels) -> set[tuple[str, str]]:
    return {(r.source, r.target) for r in rels}


def _filter_routes_ok(active: list[tuple[str, str]]) -> bool:
    """Power BI's rule: with single-direction relationships a filter travels from the one side (target) to the many side
    (source); no table may reach another by two routes, and no filter may come back to where it started."""
    down: dict[str, list[str]] = {}
    for s, t in active:
        down.setdefault(t, []).append(s)
    nodes = {x for pair in active for x in pair}
    for a in nodes:                                     # no loop: a filter never comes back
        stack, seen = list(down.get(a, [])), set()
        while stack:
            v = stack.pop()
            if v == a:
                return False
            if v not in seen:
                seen.add(v)
                stack += down.get(v, [])

    def routes(a: str, b: str) -> int:                  # acyclic now, so the plain count terminates
        return 1 if a == b else sum(routes(w, b) for w in down.get(a, []))

    return all(routes(a, b) <= 1 for a in nodes for b in nodes)


def _tmdl_relationships(parts: dict) -> list[tuple[str, str, bool]]:
    text = parts.get("definition/relationships.tmdl", "")
    out = []
    for block in text.split("relationship ")[1:]:
        frm = re.search(r"fromColumn: ('?)(.+?)\1\.", block).group(2)
        to = re.search(r"toColumn: ('?)(.+?)\1\.", block).group(2)
        out.append((frm, to, "isActive: false" not in block))
    return out


# ------------------------------------------------------------------ the SAP-shaped sample (F1 XA2) ---------------------

def test_on_sap_sd_the_order_header_keeps_its_items_and_its_customer(sap_sd):
    p, v = sap_sd
    before, _ = semantic_model.active_relationships(p, p.relationships)
    assert ("VBAP", "VBAK") not in _pairs(before) and ("VBAK", "KNA1") not in _pairs(before)      # F1's finding, without counts
    assert ("ZSD_ORDER_EXT", "LIKP") in _pairs(before)
    active, inactive = semantic_model.active_relationships(p, p.relationships, v)
    assert {("VBAP", "VBAK"), ("VBAK", "KNA1"), ("LIKP", "KNA1"), ("VBRK", "KNA1"), ("VBAP", "MARA")} <= _pairs(active)
    why = {(r.source, r.target): w for r, w in inactive}
    for target in ("LIKP", "VBRK"):                     # the R3 guesses that match nothing: never active, with the count
        assert ("ZSD_ORDER_EXT", target) not in _pairs(active)
        assert why[("ZSD_ORDER_EXT", target)].startswith("counted with no match: 301 of 301 rows with a value point at nothing")
    assert ("ZSD_ORDER_EXT", "VBAK") in _pairs(active)          # the one that matches (300 of 301) is the one
    assert _filter_routes_ok(sorted(_pairs(active)))


def test_the_draft_on_the_silver_layer_follows_the_counts_and_explains_each_link(sap_sd):
    p, v = sap_sd
    d = semantic_model.draft(p, {**LAKEHOUSE, "schema": "sap_sd"}, "m", validation=v)
    rels = _tmdl_relationships(d["parts"])
    on = {(a, b) for a, b, act in rels if act}
    assert {("VBAP", "VBAK"), ("VBAK", "KNA1")} <= on
    assert ("ZSD_ORDER_EXT", "LIKP") not in on
    assert _filter_routes_ok(sorted(on))                # calendar included
    s = d["summary"]
    by = s["active_by_counts"]
    assert by["rule"] == semantic_model.COUNTED_SAID and "never active" in by["rule"]
    assert len(by["relationships"]) == s["relationships_active"] + s["relationships_inactive"]
    for x in by["relationships"]:
        assert "BL51 rule" in x["why"] and x["state"] in ("holds", "fails", "no_rows", "not_counted")
        assert x["active"] == x["why"].startswith("active:")
        assert isinstance(x["rows_with_value"], int) and isinstance(x["matched"], int)
        assert x["counted_columns"][0] == "MANDT"           # the silver column is said with the columns that were counted
    vbap = next(x for x in by["relationships"] if (x["source"], x["target"]) == ("VBAP", "VBAK"))
    assert vbap["active"] and vbap["state"] == "fails" and vbap["orphans"] == vbap["rows_with_value"] - vbap["matched"] > 0
    readme = d["parts"]["README.generated.md"]
    assert "### What the counts decided" in readme and semantic_model.COUNTED_SAID in readme
    # the calendar: orders, deliveries and invoices each by their own date (the line tables through their header)
    dates = {x["fact"]: x["active"] for x in s["date_table"]["related"]}
    assert dates == {"VBAK": True, "VBAP": False, "LIKP": True, "LIPS": False, "VBRK": True, "VBRP": False}


def test_no_row_value_is_written(sap_sd):
    p, v = sap_sd
    d = semantic_model.draft(p, {**LAKEHOUSE, "schema": "sap_sd"}, "m", validation=v)
    said = json.dumps(d["summary"]["active_by_counts"]) + d["parts"]["README.generated.md"].split("### What the counts decided")[1]
    values = {str(x) for rows in sap_sample.rows("sap_sd").values() for row in rows for x in row
              if isinstance(x, str) and len(x) >= 5}
    assert values and not [x for x in values if x in said]


# ------------------------------------------------------------------ the planted link without a match --------------------

def test_on_shop_faults_the_planted_link_without_a_match_is_inactive():
    p, v = _counted("shop_faults")
    active, inactive = semantic_model.active_relationships(p, p.relationships, v)
    assert ("newsletter_signups", "customers") not in _pairs(active)
    why = dict(((r.source, r.target), w) for r, w in inactive)[("newsletter_signups", "customers")]
    assert why.startswith("counted with no match: 8 of 8 rows with a value point at nothing in customers")
    before, _ = semantic_model.active_relationships(p, p.relationships)
    assert ("newsletter_signups", "customers") in _pairs(before)                      # without counts: as before
    d = semantic_model.draft(p, {**LAKEHOUSE, "schema": shop_faults.SCHEMA}, "m", validation=v)
    assert ("newsletter_signups", "customers", True) not in _tmdl_relationships(d["parts"])


def test_a_link_with_some_rows_pointing_at_nothing_stays_usable():
    p, v = _counted("sap_demo")
    active, _ = semantic_model.active_relationships(p, p.relationships, v)
    assert ("sap_vbap", "sap_vbak") in _pairs(active)            # 1 of 6 rows point at nothing: counted with matches
    assert _filter_routes_ok(sorted(_pairs(active)))


# ------------------------------------------------------------------ ambiguity: one column, several tables (F1 XB1) ------

def _ambiguous_plan():
    s = Schema.from_information_schema([("dbo", n, c, "int", i) for n, cols in (
        ("ext", ["ext_id", "doc_no"]), ("orders", ["doc_no", "x"]), ("deliveries", ["doc_no", "y"])) for i, c in enumerate(cols, 1)],
        schema="dbo")
    p = infer_plan(s, keys={"orders": ["doc_no"], "deliveries": ["doc_no"], "ext": ["ext_id"]})
    p.relationships = [Relationship("ext", ["doc_no"], "orders", ["doc_no"], "R3"),
                       Relationship("ext", ["doc_no"], "deliveries", ["doc_no"], "R3")]
    return p


def _link(target: str, rows: int, orphans: int) -> dict:
    return {"source": "ext", "columns": ["doc_no"], "target": target, "target_columns": ["doc_no"], "rule": "R3",
            "rows_with_value": rows, "orphans": orphans,
            "verdict": evidence.relationship_verdict(rows, orphans)}


def test_when_the_counts_do_not_choose_a_person_does():
    p = _ambiguous_plan()
    v = {"keys": [], "relationships": [_link("orders", 10, 2), _link("deliveries", 10, 8)]}
    active, inactive = semantic_model.active_relationships(p, p.relationships, v)
    assert active == [] and len(inactive) == 2
    for _r, why in inactive:
        assert "ambiguous: ext.doc_no points at 2 tables (deliveries, orders)" in why and "a person chooses one with `confirmed`" in why


def test_the_counted_link_wins_over_one_without_a_match_or_one_not_counted():
    p = _ambiguous_plan()
    v = {"keys": [], "relationships": [_link("orders", 10, 0), _link("deliveries", 10, 10)]}
    active, inactive = semantic_model.active_relationships(p, p.relationships, v)
    assert _pairs(active) == {("ext", "orders")}
    assert dict(((r.target, w) for r, w in inactive))["deliveries"].startswith("counted with no match")
    v = {"keys": [], "relationships": [_link("orders", 10, 0)]}                   # deliveries not counted
    active, inactive = semantic_model.active_relationships(p, p.relationships, v)
    assert _pairs(active) == {("ext", "orders")}
    why = dict(((r.target, w) for r, w in inactive))["deliveries"]
    assert "the link to orders is the one" in why and "this link: not counted" in why


def test_a_confirmed_link_of_the_group_is_the_one():
    p = _ambiguous_plan()
    p.relationships[1].rule = "confirmed"
    v = {"keys": [], "relationships": [_link("orders", 10, 0), {**_link("deliveries", 10, 0), "rule": "confirmed"}]}
    active, _ = semantic_model.active_relationships(p, p.relationships, v)
    assert _pairs(active) == {("ext", "deliveries")}


# ------------------------------------------------------------------ rules, determinism, the default --------------------

def test_a_counted_link_ranks_above_one_not_counted_on_the_same_routes():
    """f -> a -> b and f -> b: a filter on b would reach f two ways, so one link goes; the two counted ones stay."""
    s = Schema.from_information_schema([("dbo", n, c, "int", i) for n, cols in (
        ("f", ["f_id", "a_id", "b_id"]), ("a", ["a_id", "b_id"]), ("b", ["b_id"])) for i, c in enumerate(cols, 1)], schema="dbo")
    p = infer_plan(s)
    rel = lambda src, col, tgt, rows: {"source": src, "columns": [col], "target": tgt, "rows_with_value": rows, "orphans": 0,
                                       "verdict": evidence.relationship_verdict(rows, 0)}
    v = {"keys": [], "relationships": [rel("a", "b_id", "b", 5), rel("f", "a_id", "a", 9)]}
    active, inactive = semantic_model.active_relationships(p, p.relationships, v)
    assert [(r.source, r.target) for r, _ in inactive] == [("f", "b")]
    assert "a filter on b would reach f two ways" in inactive[0][1] and "this link: not counted" in inactive[0][1]


def test_the_same_counts_give_the_same_answer_whatever_the_order(sap_sd):
    p, v = sap_sd
    a1, i1 = semantic_model.active_relationships(p, p.relationships, v)
    a2, i2 = semantic_model.active_relationships(p, list(reversed(p.relationships)), v)
    assert _pairs(a1) == _pairs(a2) and {(r.source, r.target, w) for r, w in i1} == {(r.source, r.target, w) for r, w in i2}
    d1 = semantic_model.draft(p, {**LAKEHOUSE, "schema": "sap_sd"}, "m", validation=v)
    d2 = semantic_model.draft(p, {**LAKEHOUSE, "schema": "sap_sd"}, "m", validation=v)
    assert d1 == d2


@pytest.mark.parametrize("name", ["shop", "shop_faults", "sap_demo"])
def test_without_counts_nothing_changes(name):
    p, v = _counted(name)
    info = {**LAKEHOUSE, "schema": p.schema.schema or "dbo"}
    plain = semantic_model.draft(p, info, "m")
    assert "active_by_counts" not in plain["summary"]
    es = graphs.edges(p)
    forest, rest = graphs.spanning_forest(p, es)
    active, inactive = semantic_model.active_relationships(p, p.relationships)
    assert active == [e["rel"] for e in forest] and inactive == [(e["rel"], e["why"]) for e in rest]
    # an answer that counted none of the links is no count: the draft is the same, byte for byte
    assert semantic_model.draft(p, info, "m", validation={"keys": [], "relationships": []}) == plain
    assert semantic_model.draft(p, info, "m", validation={"keys": v["keys"], "relationships": []})["summary"].get("active_by_counts") is None


def test_where_all_links_hold_the_model_is_written_as_before():
    """The shop: every link counted and holding, the counted rule keeps the same active set, and the relationships file
    is byte for byte the one written without counts."""
    p, v = _counted("shop")
    info = {**LAKEHOUSE, "schema": "shop"}
    with_counts = semantic_model.draft(p, info, "m", validation=v)
    assert with_counts["parts"]["definition/relationships.tmdl"] == semantic_model.draft(p, info, "m")["parts"]["definition/relationships.tmdl"]
    assert all(x["active"] and x["state"] == "holds" for x in with_counts["summary"]["active_by_counts"]["relationships"])
