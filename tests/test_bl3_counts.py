"""BL3 (21 Nov 2026): one count, and "not counted" never reads as passed (fabric_backend/counts.py, review.py; backlog
C-31 and C-07; F1's B5, B6, B10, B14 and A4 in docs/FINDINGS-13NOV.md).

On the synthetic shop and SAP demo (SQLite), counts.summary gives the same numbers as the evidence report and the
review file; a link to a non-unique target never holds; an uncounted check, an empty table and a link with no values
are open, and a review can never say "Nothing open" while one of them is.
"""
from __future__ import annotations

import copy

import pytest

from fabric_backend import counts, evidence, evidence_report, review, sap_demo
from fabric_backend.infer import plan as infer_plan
from fabric_backend.platforms import local


def _shop():
    src = local.sample_source()
    return src.schema, src.execute


SOURCES = {"shop": _shop, "sap": sap_demo.sqlite}


def _run(name: str):
    schema, execute = SOURCES[name]()
    p = infer_plan(schema)
    return p, evidence.validate(p, execute, 200)


def _review(p, v, **kw):
    return review.build(p, p, {"source": "bl3", "schema": p.schema.schema or ""}, checks=v, checked_at="2026-11-21T10:00:00Z", **kw)


# ------------------------------------------------------------------ one count on the two samples ---------------------

@pytest.mark.parametrize("name", sorted(SOURCES))
def test_counts_equal_the_evidence_report(name):
    p, v = _run(name)
    c = counts.summary(p, v)
    rep = evidence_report.report(p, v, generated_at="2026-11-21T10:00:00Z")
    for kind, group in (("key", c["keys"]), ("relationship", c["links"])):
        checks = [x for x in rep["checks"] if x["check"] == kind]
        assert len(checks) == group["total"]
        assert sum(1 for x in checks if x.get("passed")) == group["holds"]
        assert sum(1 for x in checks if x["result"] == evidence_report.NOT_CHECKED) == group["not_counted"]
        assert sum(1 for x in checks if x["result"] != evidence_report.NOT_CHECKED and not x.get("passed")) \
            == group["fails"] + group["no_rows"]
    assert rep["summary"]["keys"] == c["keys"]["total"] and rep["summary"]["relationships"] == c["links"]["total"]


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_counts_equal_validate_and_the_review(name):
    p, v = _run(name)
    c = counts.summary(p, v)
    t = evidence.summarize(v, p)["totals"]
    assert t["keys"]["checked"] == c["keys"]["total"] and t["keys"]["passed"] == c["keys"]["holds"]
    rt = t["relationships"]
    assert rt["checked"] == c["links"]["total"] and rt["passed"] == c["links"]["holds"]
    assert rt["failed"] + rt.get("passed_with_warning", 0) == c["links"]["fails"]
    assert rt.get("not_counted", 0) == c["links"]["no_rows"]
    rv = _review(p, v)
    assert rv["counts"]["sentence"] == c["sentence"]
    items = rv["items"]
    st = {x["id"]: x["state"] for x in c["items"]}
    for it in items:                                               # the review's check status is the count's state
        assert it["check"]["status"] == {"holds": "passed", "fails": "failed"}.get(st[it["id"]], "not_checked"), it["id"]
    passed = sum(1 for it in items if st[it["id"]] == "holds")
    assert f"checks: {passed} passed, " in review.summary(rv)
    assert c["sentence"] in review.summary(rv) and c["sentence"] in review.markdown(rv)


def test_f1_b5_b6_the_sap_links_said_once():
    p, v = _run("sap")
    c = counts.summary(p, v)
    assert c["links"]["sentence"] == ("32 of 34 hold, 1 fails, 1 has no rows to check "
                                      "(24 in the plan, 10 the SAP pack lists with a condition)")
    assert c["keys"]["sentence"] == "17 of 17 hold"
    assert (c["links"]["in_plan"], c["links"]["extended"]) == (len(p.relationships), len(p.extended)) == (24, 10)
    assert {x["state"] for x in c["open"]} == {"fails", "no_rows"} and len(c["open"]) == 2


def test_f1_b10_b14_open_questions_are_counted_apart():
    p, v = _run("shop")
    c = counts.summary(p, v)
    assert c["sentence"] == "Keys: 6 of 6 hold. Links: 6 of 6 hold. The plan also asks 1 open question."
    assert c["questions"] == [{"about": "key:audit_log", "kind": "no_key"}] and not c["open"]
    assert not counts.nothing_open(c)
    rv = _review(p, v)
    assert "The plan also asks 1 open question." in review.summary(rv)


# ------------------------------------------------------------------ C-07: the soft spots -----------------------------

def _target_key(p, v):
    """A link of the plan and the key entry of its target in v."""
    for r in p.relationships:
        for k in v["keys"]:
            if k["table"] == r.target:
                return r, k
    raise AssertionError("no link with a counted target key")


def test_a_link_to_a_non_unique_target_never_holds():
    p, v = _run("shop")
    r, k = _target_key(p, v)
    bad = copy.deepcopy(v)
    for x in bad["keys"]:
        if x["table"] == r.target:
            x.update(distinct=x["rows"] - 1, verdict=evidence.key_verdict(x["rows"], 0, x["rows"] - 1))
    # the link's own verdict says "holds" (as an answer counted before the key, or merged from two calls, would)
    c = counts.summary(p, bad)
    rid = review.rel_id(r.source, r.source_cols, r.target)
    state = {x["id"]: x for x in c["items"]}
    assert state[rid]["state"] == "fails" and "not unique" in state[rid]["reason"]
    assert state[review.key_id(r.target)]["state"] == "fails"
    # and when the verdict carries validate's own "; but the target key ... is not unique"
    for x in bad["relationships"]:
        if (x["source"], x["target"]) == (r.source, r.target):
            x["verdict"] += f"; but the target key of {r.target} is not unique, so a row can match more than one"
    assert counts.link_state(next(x for x in bad["relationships"] if (x["source"], x["target"]) == (r.source, r.target)))[0] == "fails"
    rv = _review(p, bad)
    it = next(i for i in rv["items"] if i["id"] == rid)
    assert it["check"]["status"] == "failed"
    assert "- Nothing open." not in review.markdown(rv)


def _refusing(sql):
    raise PermissionError("SELECT permission denied")


def test_an_uncounted_check_is_open_and_never_passed():
    p, _ = _run("shop")
    v = evidence.validate(p, _refusing, 200)
    assert v.get("not_counted")
    c = counts.summary(p, v)
    assert c["keys"]["holds"] == c["links"]["holds"] == 0
    assert c["keys"]["not_counted"] + c["links"]["not_counted"] == len(p.keys) + len(p.relationships)
    assert "not counted" in c["sentence"] and not counts.nothing_open(c)
    rv = _review(p, v)
    att = review.attention(rv)
    assert any("not counted" in a and "PermissionError" in a for a in att), att
    md = review.markdown(rv)
    assert "- Nothing open." not in md and "0 of 6 hold, 6 not counted" in md
    assert "checks: 0 passed, 0 failed, 0 stale, 12 not checked." in review.summary(rv)
    assert all("PermissionError" in it["check"]["not_counted"] for it in rv["items"])   # told apart from "not asked"


def test_no_validation_is_not_counted_and_says_so():
    p, _ = _run("shop")
    c = counts.summary(p, None)
    assert {x["state"] for x in c["items"]} == {"not_counted"}
    assert all(x["reason"] == counts.NOT_ASKED for x in c["items"])
    rv = _review(p, None)
    assert any("validate=true" in a for a in review.attention(rv))
    assert "- Nothing open." not in review.markdown(rv)


def test_a_check_left_out_by_max_items_is_not_counted():
    p, _ = _run("sap")
    schema, execute = SOURCES["sap"]()
    v = evidence.validate(p, execute, 5)
    c = counts.summary(p, v)
    counted = len(v["keys"]) + len(v["relationships"])
    assert c["keys"]["total"] + c["links"]["total"] - counted == c["keys"]["not_counted"] + c["links"]["not_counted"] > 0
    assert any(x["reason"] == counts.LEFT_OUT for x in c["open"])


def test_an_empty_table_has_no_rows_to_check_and_is_open():
    p, v = _run("shop")
    r, _ = _target_key(p, v)
    empty = copy.deepcopy(v)
    for x in empty["keys"]:
        if x["table"] == r.target:
            x.update(rows=0, nulls=0, distinct=0, verdict=evidence.key_verdict(0, 0, 0))
    for x in empty["relationships"]:
        if x["source"] == r.target:
            x.update(rows_with_value=0, orphans=0, verdict=evidence.relationship_verdict(0, 0))
    c = counts.summary(p, empty)
    kid = review.key_id(r.target)
    assert next(x for x in c["items"] if x["id"] == kid)["state"] == "no_rows"
    assert c["keys"]["no_rows"] == 1 and c["keys"]["holds"] == len(p.keys) - 1
    assert "1 has no rows to check" in c["keys"]["sentence"]
    rv = _review(p, empty)
    md = review.markdown(rv)
    assert "- Nothing open." not in md and kid in md and "no rows to check" in md


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_nothing_open_only_when_everything_holds(name):
    p, v = _run(name)
    cases = [v, None, evidence.validate(p, _refusing, 200)]
    for case in cases:
        rv = _review(p, case)
        if rv["counts"]["open"] or rv["open_questions"]:
            assert "- Nothing open." not in review.markdown(rv)
    clean = copy.deepcopy(v)
    clean["relationships"] = [x for x in clean["relationships"]
                              if counts.link_state(x)[0] == "holds"]
    keep = {(x["source"], x["target"]) for x in clean["relationships"]}
    p2 = copy.copy(p)
    p2.relationships = [r for r in p.relationships if (r.source, r.target) in keep]
    p2.extended = [r for r in getattr(p, "extended", []) if (r.source, r.target) in keep]
    p2.keyless, p2.ambiguous = [], []
    c = counts.summary(p2, clean)
    assert counts.nothing_open(c)


def test_scope_follows_the_review_tables():
    p, v = _run("shop")
    t = sorted(p.keys)[0]
    c = counts.summary(p, v, tables=[t])
    rv = _review(p, v, tables=[t])
    assert rv["counts"]["sentence"] == c["sentence"]
    assert all(x["kind"] != "key" or x["table"] == t for x in c["items"])
