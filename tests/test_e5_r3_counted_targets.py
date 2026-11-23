"""E5 (23 November 2026, XB1 from BL51/BL63): when R3 gives the same columns several target tables, validate_plan's
counts decide between them (Gustav's option (b)), instead of listing every R3 target under `ambiguous`.

- validate_plan counts every target of such a group in the same answer: check_order keeps a group's keys and links
  together, and a max_items cut never falls inside a group;
- exactly one target counted with matches: it is the one (`counts_pick`);
- none with matches: the R3 link is refuted (`refuted`);
- two or more with matches: nothing is guessed, a person chooses with `confirmed` (`person_chooses`), as BL51 rule 2;
- the decision is in validate_plan's answer (`r3_targets`) and in the model summary's `active_by_counts.r3_targets`,
  and agrees with the active set the model draws;
- without counts plan_backend, the semantic model and every golden file are unchanged (the golden tests hold the
  files; here the functions on sap_sd, sap_demo, shop and shop_faults);
- counts only, never a row value.

Synthetic rows only, counted on SQLite; nothing talks to Fabric.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from fabric_backend import evidence, graphs, sap_demo, sap_sample, semantic_model, shop_faults
from fabric_backend.infer import plan as infer_plan
from fabric_backend.platforms import local
from fabric_backend.schema import Schema
from test_bl19_receipt_notebook import _execute, _sap_db, _shop_db
from test_bl33_one_count import _faults_db
from test_bl51_active_relationships import LAKEHOUSE, _pairs

SAP_SD = ("ZSD_ORDER_EXT", ["MANDT", "VBELN"])


@pytest.fixture(scope="module")
def sap_sd():
    src = sap_sample.source("sap_sd")
    p = infer_plan(src.schema)
    v = evidence.validate(p, src.execute, 500)
    yield p, v, src
    src.close()


def _counted(name: str):
    db, schema = {"sap_demo": (_sap_db, lambda: sap_demo.sqlite()[0]),
                  "shop_faults": (_faults_db, shop_faults.schema),
                  "shop": (_shop_db, lambda: local.sample_source().schema)}[name]
    p = infer_plan(schema())
    return p, evidence.validate(p, _execute(db()), 500)


# A small synthetic schema where R3 gives ext.client+doc_no three targets; the rows say which hold.
def _r3_db(ext_docs: list[int], a_docs=(1, 2, 3), b_docs=(4, 5, 6), c_docs=(7, 8, 9)):
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS r3")
    tables = {"hdr_a": ["client", "doc_no", "amount"], "hdr_b": ["client", "doc_no", "weight"],
              "hdr_c": ["client", "doc_no", "total"], "ext": ["ext_id", "client", "doc_no", "note"]}
    for t, cols in tables.items():
        con.execute(f"CREATE TABLE r3.[{t}] ({', '.join(f'[{c}]' for c in cols)})")
    for t, docs in (("hdr_a", a_docs), ("hdr_b", b_docs), ("hdr_c", c_docs)):
        con.executemany(f"INSERT INTO r3.[{t}] VALUES (?,?,?)", [(100, d, d * 10) for d in docs])
    con.executemany("INSERT INTO r3.[ext] VALUES (?,?,?,?)", [(i, 100, d, "Alpha AB") for i, d in enumerate(ext_docs, 1)])
    schema = Schema.from_information_schema([("r3", t, c, "int" if c != "note" else "varchar", i)
                                             for t, cols in tables.items() for i, c in enumerate(cols, 1)], schema="r3")
    keys = {"hdr_a": ["client", "doc_no"], "hdr_b": ["client", "doc_no"], "hdr_c": ["client", "doc_no"], "ext": ["ext_id"]}
    p = infer_plan(schema, keys=keys)
    assert sorted(r.target for r in p.relationships if r.source == "ext" and r.rule == "R3") == ["hdr_a", "hdr_b", "hdr_c"]
    assert p.ambiguous == []                            # the plan is as before: every R3 target, nothing listed as ambiguous
    return p, evidence.validate(p, _execute(con), 500)


# ------------------------------------------------------------------ no change without counts ------------------------

@pytest.mark.parametrize("name", ["sap_demo", "shop", "shop_faults"])
def test_without_counts_or_without_a_group_nothing_changes(name):
    p, v = _counted(name)
    assert graphs.r3_targets(p, None) == [] and graphs.r3_targets(p, v) == []
    assert evidence.r3_groups(p) == {}                  # no group: the check order is the one before E5
    d = semantic_model.draft(p, {**LAKEHOUSE, "schema": "s"}, "m", validation=v)
    assert "r3_targets" not in json.dumps(d["summary"])


def test_on_sap_sd_the_plan_and_the_model_without_counts_are_as_before(sap_sd):
    p, _v, _src = sap_sd
    assert [r.target for r in p.relationships if (r.source, r.source_cols) == SAP_SD] == ["VBAK", "LIKP", "VBRK"]
    assert all(r.rule == "R3" for r in p.relationships if r.source == SAP_SD[0]) and p.ambiguous == []
    assert graphs.r3_targets(p, None) == []
    d = semantic_model.draft(p, {**LAKEHOUSE, "schema": "sap_sd"}, "m")
    assert "active_by_counts" not in d["summary"] and "R3 links to several tables" not in d["parts"]["README.generated.md"]


# ------------------------------------------------------------------ one match picks (sap_sd) --------------------------

def test_on_sap_sd_the_counts_pick_vbak(sap_sd):
    p, v, _src = sap_sd
    [g] = graphs.r3_targets(p, v)
    assert (g["source"], g["columns"], g["decision"], g["chosen"]) == ("ZSD_ORDER_EXT", ["MANDT", "VBELN"], "counts_pick", "VBAK")
    by = {t["target"]: (t["rows_with_value"], t["matched"], t["orphans"]) for t in g["targets"]}
    assert by == {"VBAK": (301, 300, 1), "LIKP": (301, 0, 301), "VBRK": (301, 0, 301)}
    assert "the link to VBAK is the one" in g["why"] and "refuted, counted with no match: LIKP, VBRK" in g["why"]
    # the model draws the same: VBAK active, LIKP and VBRK never
    active, _ = semantic_model.active_relationships(p, p.relationships, v)
    assert ("ZSD_ORDER_EXT", "VBAK") in _pairs(active)
    assert not {("ZSD_ORDER_EXT", "LIKP"), ("ZSD_ORDER_EXT", "VBRK")} & _pairs(active)


def test_the_model_summary_and_readme_say_the_decision(sap_sd):
    p, v, _src = sap_sd
    d = semantic_model.draft(p, {**LAKEHOUSE, "schema": "sap_sd"}, "m", validation=v)
    [g] = d["summary"]["active_by_counts"]["r3_targets"]
    assert g["decision"] == "counts_pick" and g["chosen"] == "VBAK"
    on = {(x["source"], x["target"]): x["active"] for x in d["summary"]["active_by_counts"]["relationships"]
          if x["source"] == "ZSD_ORDER_EXT"}
    assert on == {("ZSD_ORDER_EXT", "VBAK"): True, ("ZSD_ORDER_EXT", "LIKP"): False, ("ZSD_ORDER_EXT", "VBRK"): False}
    assert f"- {g['why']}." in d["parts"]["README.generated.md"].split("### What the counts decided")[1]


def test_validate_plans_answer_carries_the_decision(sap_sd, monkeypatch):
    """The local server's validate_plan over the sap_sd rows: `r3_targets` with the rule and the group, counts only."""
    from fabric_backend import mcp_server
    p, _v, src = sap_sd
    monkeypatch.delenv("KRUSGRAPH_PLATFORM", raising=False)
    monkeypatch.delenv("KRUSGRAPH_CSN", raising=False)
    monkeypatch.setattr(mcp_server, "_execute_factory", lambda schema: (lambda sql: src.execute(sql)))
    monkeypatch.setattr(mcp_server, "_plan_on", lambda ex, schema, keys=None, confirmed=None, decisions=True: infer_plan(src.schema))
    for detail in ("full", "summary"):
        out = json.loads(mcp_server.validate_plan(schema="sap_sd", detail=detail))
        assert out["r3_targets"]["rule"] == graphs.R3_TARGETS_RULE
        [g] = out["r3_targets"]["groups"]
        assert (g["source"], g["decision"], g["chosen"]) == ("ZSD_ORDER_EXT", "counts_pick", "VBAK")


def test_a_max_items_cut_never_splits_the_group(sap_sd):
    p, _v, src = sap_sd
    queue = evidence.check_order(p)
    at = [n for n, (k, x) in enumerate(queue) if k == "rel" and p.relationships[x].source == "ZSD_ORDER_EXT"]
    assert at == list(range(at[0], at[0] + 3))           # the three links next to each other
    for m in range(1, len(queue) + 1):
        v = evidence.validate(p, src.execute, m)
        got = sorted(r["target"] for r in v["relationships"] if r["source"] == "ZSD_ORDER_EXT")
        assert got in ([], ["LIKP", "VBAK", "VBRK"]), m
        if got:
            assert graphs.r3_targets(p, v)[0]["chosen"] == "VBAK"


# ------------------------------------------------------------------ zero match refutes ----------------------------------

def test_when_no_target_matches_the_r3_link_is_refuted():
    p, v = _r3_db([50, 51, 52, 53])
    [g] = graphs.r3_targets(p, v)
    assert g["decision"] == "refuted" and g["chosen"] is None and "candidates" not in g
    assert all(t["matched"] == 0 and t["rows_with_value"] == 4 for t in g["targets"])
    assert "the R3 link is refuted" in g["why"]
    active, _ = semantic_model.active_relationships(p, p.relationships, v)
    assert not [a for a in _pairs(active) if a[0] == "ext"]


def test_one_match_among_three_picks_it():
    p, v = _r3_db([4, 5, 6, 5])
    [g] = graphs.r3_targets(p, v)
    assert (g["decision"], g["chosen"]) == ("counts_pick", "hdr_b")
    active, _ = semantic_model.active_relationships(p, p.relationships, v)
    assert {a for a in _pairs(active) if a[0] == "ext"} == {("ext", "hdr_b")}


# ------------------------------------------------------------------ two matches: a person chooses ---------------------

def test_when_two_targets_match_a_person_chooses():
    p, v = _r3_db([1, 2, 4, 50])                        # 2 rows match hdr_a, 1 hdr_b, none hdr_c
    [g] = graphs.r3_targets(p, v)
    assert g["decision"] == "person_chooses" and g["chosen"] is None
    assert sorted(g["candidates"]) == ["hdr_a", "hdr_b"]
    assert "a person chooses one with `confirmed`" in g["why"] and "refuted, counted with no match: hdr_c" in g["why"]
    active, _ = semantic_model.active_relationships(p, p.relationships, v)
    assert not [a for a in _pairs(active) if a[0] == "ext"]          # BL51 rule 2: none is active, nothing guessed


def test_a_confirmation_settles_it():
    s = _r3_db([1, 2, 4, 50])[0].schema
    confirmed = [{"source": "ext", "source_cols": ["client", "doc_no"], "target": "hdr_b", "target_cols": ["client", "doc_no"]}]
    p = infer_plan(s, keys={"hdr_a": ["client", "doc_no"], "hdr_b": ["client", "doc_no"], "hdr_c": ["client", "doc_no"],
                            "ext": ["ext_id"]}, confirmed=confirmed)
    v = {"keys": [], "relationships": [
        {"source": "ext", "columns": r.source_cols, "target": r.target, "target_columns": r.target_cols, "rule": r.rule,
         "rows_with_value": 4, "orphans": {"hdr_a": 2, "hdr_b": 3, "hdr_c": 4}[r.target],
         "verdict": evidence.relationship_verdict(4, {"hdr_a": 2, "hdr_b": 3, "hdr_c": 4}[r.target])}
        for r in p.relationships if r.source == "ext"]}
    [g] = graphs.r3_targets(p, v)
    assert (g["decision"], g["chosen"]) == ("declared", "hdr_b")


def test_a_group_partly_counted_is_not_decided_without_matches():
    p, v = _r3_db([50, 51])
    v = {**v, "relationships": [r for r in v["relationships"] if r["target"] != "hdr_c"]}
    [g] = graphs.r3_targets(p, v)
    assert g["decision"] == "not_decided" and g["chosen"] is None and "hdr_c: not counted" in g["why"]


# ------------------------------------------------------------------ counts only --------------------------------------

def test_no_row_value_is_written(sap_sd):
    p, v, _src = sap_sd
    d = semantic_model.draft(p, {**LAKEHOUSE, "schema": "sap_sd"}, "m", validation=v)
    said = json.dumps(graphs.r3_targets(p, v)) + json.dumps(d["summary"]["active_by_counts"]["r3_targets"]) + graphs.R3_TARGETS_RULE
    values = {str(x) for rows in sap_sample.rows("sap_sd").values() for row in rows for x in row
              if isinstance(x, str) and len(x) >= 5}
    assert values and not [x for x in values if x in said]
    p2, v2 = _r3_db([1, 2, 4, 50])
    assert "Alpha AB" not in json.dumps(graphs.r3_targets(p2, v2))
