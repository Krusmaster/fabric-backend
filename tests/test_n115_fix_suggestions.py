"""Round n115: a fix suggestion for every finding of validate_plan (fabric_backend/fixes.py), in the n100 checklist and in
the silver notebook draft. A fix is a mechanical step with a stated rule, a choice is two of them with none chosen, and a
question is a business decision with no default. Counts before and after come from the check's own counts, and the
check's query gives them again; the silver steps run in Python (silver.simulate) on the same rows and end with those
counts. Only silver and the quarantine table are written; no source table, anywhere. All rows here are synthetic."""
from __future__ import annotations

import json
import re
from collections import Counter

import pytest

from fabric_backend import evidence, evidence_report as er, fixes, seed, silver
from fabric_backend.infer import plan
from silver_cases import seed_rows, sqlite_execute
from test_evidence_report import AT, WRONG_KEY, WRONG_LINK, _all_kinds
from test_n106_flat_amounts import COLS, FLAT, _flat

INFO = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse",
            schema="shop", schemas_enabled=True)
KIND = {"key_not_unique": "fix", "orphans": "choice", "amount_repeated": "question", "flat_amount_repeated": "fix",
        "ambiguous_target": "question", "no_key": "question", "proposed_not_applied": "question",
        "pack_not_applied": "question", "not_counted": "question"}
WRITES = re.compile(r"\b(INSERT\s+INTO|UPDATE\s+\S+\s+SET|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE|DROP\s+TABLE|CREATE\s+TABLE)\b", re.I)


def bronze():
    """The shop with a bronze layer's problems (silver_cases): a NULL key and an exact copy in customers, a newer
    version of an order, references to a customer and an order that do not exist. In SQLite, as validate_plan reads it."""
    data = seed_rows()
    return data, sqlite_execute(data)


@pytest.fixture()
def shop():
    data, ex = bronze()
    p = plan(seed.schema("shop"))
    v = evidence.validate(p, ex)
    return data, ex, p, v, fixes.suggest(p, v)


def _by(sug, finding, table):
    return next(f for f in sug if f["finding"] == finding and f["table"] == table)


def _choose(sug, prefer="set_null"):
    """A decision for every orphan choice: `prefer` where it is offered, else quarantine."""
    return {"ORPHANS": {f["silver"]["id"]: prefer if prefer in [c["id"] for c in f["choices"]] else "quarantine"
                        for f in sug if f["kind"] == "choice"}}


# ------------------------------------------------------------------ one suggestion or question per finding type ---

def test_each_finding_type_maps_to_its_suggestion_or_question():
    from fabric_backend.platforms.local import sample_source
    src = sample_source()
    try:
        p = plan(src.schema, keys=WRONG_KEY, confirmed=[WRONG_LINK])
        rows = (er.report(_all_kinds(p), evidence.validate(p, src.execute), generated_at=AT)["checklist"]
                + er.report(p, None, generated_at=AT)["checklist"])
    finally:
        src.close()
    fp, fex = _flat()
    rows += er.report(fp, evidence.validate(fp, fex), generated_at=AT)["checklist"]
    assert set(KIND) == set(er.FINDING_TYPES) and {r["type"] for r in rows} == set(KIND)
    for r in rows:
        f = r["fix"]
        assert f["kind"] == KIND[r["type"]] and f["finding"] == r["type"] and f["status"] == "draft: not run", r["type"]
        assert all(q["default"] is None and q["ask"].endswith("?") for q in f["questions"])
        if f["kind"] == "question":
            assert f["why_not_a_fix"] and f["questions"] and not f.get("silver") and not f.get("draft")
        else:
            assert f["rule"] and f["silver"]["table"] == r["table"] and f["draft"]["pyspark"]
        if f["kind"] == "choice":
            assert f["default"] is None and [c["id"] for c in f["choices"]][0] == "quarantine"
    key = next(r["fix"] for r in rows if r["type"] == "key_not_unique")
    assert [q["id"] for q in key["questions"]] == ["winner:order_items"]      # 134 rows, 60 keys: which row wins is asked


def test_a_duplicate_that_differs_is_a_question_with_no_default(shop):
    data, _, p, v, sug = shop
    orders = _by(sug, "key_not_unique", "orders")
    assert orders["questions"][0]["default"] is None and "which one stays" in orders["questions"][0]["ask"]
    s = silver.apply_fixes(silver.spec(p, INFO), sug)                       # order_date is found by name, not given
    assert 'DUPLICATE_WINNER["orders"] = None' in silver.notebook_source(s)
    with pytest.raises(ValueError, match=r"orders: 1 value\(s\) of order_id have rows that differ.*Nothing was written"):
        silver.simulate(s, data, _choose(sug))
    out = silver.simulate(s, data, {**_choose(sug), "DUPLICATE_WINNER": {"orders": "order_date"}})
    assert len(out["silver"]["orders"]) == orders["counts"]["after"]["silver_rows"]
    given = silver.apply_fixes(silver.spec(p, INFO, order_by={"orders": "order_date"}), sug)    # the customer's own order_by
    assert 'DUPLICATE_WINNER["orders"] = "order_date"' in silver.notebook_source(given)
    # exact copies need no decision: customers' copy is collapsed without a winner
    assert silver.decisions(given, data, _choose(sug))["DUPLICATE_WINNER"]["customers"] is None


def test_an_orphan_choice_is_never_made_for_the_customer(shop):
    data, _, p, v, sug = shop
    s = silver.apply_fixes(silver.spec(p, INFO, order_by={"orders": "order_date"}), sug)
    with pytest.raises(ValueError, match=r"ORPHANS: choose 'quarantine' or 'set_null' for rel:audit_log.*Nothing was written"):
        silver.simulate(s, data)
    items = _by(sug, "orphans", "order_items")                              # order_id is part of the key order_id + line_no
    assert [c["id"] for c in items["choices"]] == ["quarantine"] and "part of the key" in items["set_null_not_offered"]
    assert [c["id"] for c in _by(sug, "orphans", "orders")["choices"]] == ["quarantine", "set_null"]
    assert all("exist elsewhere" in f["questions"][0]["ask"] for f in sug if f["finding"] == "orphans")


# ------------------------------------------------------------------ counts before and after -----------------------

def test_counts_before_are_the_checks_and_its_query_gives_them_again(shop):
    _, ex, p, v, sug = shop
    for k in v["keys"]:
        if k["verdict"].startswith("unique"):
            continue
        f = _by(sug, "key_not_unique", k["table"])
        b, a = f["counts"]["before"], f["counts"]["after"]
        assert (b["rows"], b["rows_with_null_key"], b["distinct_key_values"]) == (k["rows"], k["nulls"], k["distinct"])
        assert a["silver_rows"] == k["distinct"] and a["quarantined"] == k["rows"] - k["distinct"]
        assert a["of_which_null_key"] + a["of_which_duplicate"] == a["quarantined"]
        row = ex(f["counts"]["query"])[0]
        assert (row["n"], row["nulls"], row["distinct_keys"]) == (k["rows"], k["nulls"], k["distinct"])
    for r in v["relationships"]:
        if not r["orphans"]:
            continue
        f = _by(sug, "orphans", r["source"])
        assert f["counts"]["before"] == {"rows_with_value": r["rows_with_value"], "orphans": r["orphans"]}
        assert {c["id"]: c["after"]["silver_rows_with_value"] for c in f["choices"]} == \
            {c["id"]: r["rows_with_value"] - r["orphans"] for c in f["choices"]}
        row = ex(f["counts"]["query"])[0]
        assert (row["with_value"], row["orphans"]) == (r["rows_with_value"], r["orphans"])
    assert {f["finding"] for f in sug} == {"key_not_unique", "orphans", "amount_repeated", "no_key"}


def test_silver_ends_with_the_counts_the_suggestions_say(shop):
    """The silver steps on the same rows: with set_null where offered, silver holds exactly the after counts."""
    data, _, p, v, sug = shop
    s = silver.apply_fixes(silver.spec(p, INFO, order_by={"orders": "order_date"}), sug)
    out = silver.simulate(s, data, _choose(sug, "set_null"))
    q = Counter((x["source_table"], x["reason"]) for x in out["quarantine"])
    for f in sug:
        if f["finding"] == "key_not_unique":
            assert len(out["silver"][f["table"]]) == f["counts"]["after"]["silver_rows"]
            assert sum(n for (t, why), n in q.items() if t == f["table"] and "key" in why and "has no row" not in why) == \
                f["counts"]["after"]["quarantined"]
        if f["finding"] == "orphans":
            col = f["silver"]["columns"][0]
            choice = "set_null" if "set_null" in [c["id"] for c in f["choices"]] else "quarantine"
            after = next(c["after"] for c in f["choices"] if c["id"] == choice)
            # rows the table's own key step took out first (orders: the older version of order 100) are not there to count
            gone = sum(n for (t, why), n in q.items() if t == f["table"] and "key" in why and "has no row" not in why)
            assert sum(1 for r in out["silver"][f["table"]] if r[col] is not None) == after["silver_rows_with_value"] - gone
            moved = sum(n for (t, why), n in q.items() if t == f["table"] and f"{col} has no row" in why)
            assert moved == after.get("quarantined", after.get("copies_in_quarantine"))
    # with quarantine everywhere, order 200 (unknown customer) leaves silver, and its line follows it: one more than the check
    out = silver.simulate(s, data, _choose(sug, "quarantine"))
    items = _by(sug, "orphans", "order_items")
    assert len(out["silver"]["order_items"]) == items["counts"]["before"]["rows_with_value"] - items["counts"]["before"]["orphans"] - 1
    assert "a row whose orders row itself went to quarantine there is added" in items["counts"]["how"]
    assert "a NULL key or a duplicate" in _by(sug, "orphans", "orders")["counts"]["how"]


def test_a_flat_amount_moves_to_the_header_level_in_silver():
    p, ex = _flat()
    v = evidence.validate(p, ex)
    rows = er.report(p, v, generated_at=AT)["checklist"]
    f = next(r["fix"] for r in rows if r["type"] == "flat_amount_repeated")
    e = next(e for e in v["amount_levels"]["flat_tables"] if e["pattern"])
    assert f["counts"]["before"]["header_values"] == e["header_values"] == 3 and f["counts"]["after"] == \
        {"silver_rows_of_the_table": 6, "silver_rows_of_the_header_table": 3, "copies_of_the_amount": 3}
    row = ex(f["counts"]["query"])[0]
    assert (row["row_count"], row["header_values"], row["repeated_values"], row["differs_0"]) == (6, 3, 2, 0)
    s = silver.apply_fixes(silver.spec(p, dict(INFO, schema="x")), [r["fix"] for r in rows])
    data = {"order_lines": [dict(zip([c for c, _ in COLS], r)) for r in FLAT]}
    out = silver.simulate(s, data)
    assert len(out["silver"]["order_lines"]) == 6 and all("order_amount" not in r for r in out["silver"]["order_lines"])
    level = out["silver"]["order_lines_per_order_id"]
    assert len(level) == 3 and round(sum(r["order_amount"] for r in level), 2) == round(ex(e["sum_once_sql"])[0]["total"], 2)
    assert "silver.order_lines_per_order_id" in silver.written_tables(s)
    # an order whose amount differs by the time the notebook runs: it stops, nothing written
    changed = {"order_lines": data["order_lines"] + [{"order_id": 1, "line_no": 3, "product_code": "B", "order_amount": 1.0, "line_amount": 1.0}]}
    with pytest.raises(ValueError, match="no longer mechanical. Nothing was written"):
        silver.simulate(s, changed)
    # a line with no order keeps its place without the amount, and a copy goes to quarantine
    orphan = {"order_lines": data["order_lines"] + [{"order_id": None, "line_no": 1, "product_code": "B", "order_amount": 5.0, "line_amount": 5.0}]}
    out = silver.simulate(s, orphan)
    assert len(out["silver"]["order_lines"]) == 7 and [x["rule"] for x in out["quarantine"]] == ["flat amount"]


# ------------------------------------------------------------------ the draft writes only silver and quarantine ----

def test_the_draft_writes_only_silver_and_quarantine_and_no_source_anywhere(shop):
    data, _, p, v, sug = shop
    fp, fex = _flat()
    flat = [r["fix"] for r in er.report(fp, evidence.validate(fp, fex), generated_at=AT)["checklist"]]
    for pl, sg, info in ((p, sug, INFO), (fp, flat, dict(INFO, schema="x"))):
        for schemas_enabled in (True, False):
            s = silver.apply_fixes(silver.spec(pl, dict(info, schemas_enabled=schemas_enabled)), sg)
            assert s["fixes"] and not set(silver.written_tables(s)) & set(silver.source_tables(s))
            code = silver.notebook_source(s)
            assert code.count("saveAsTable") == 1 and ".write" not in code.replace("df.write.format(TABLE_FORMAT)", "")
            assert not WRITES.search(code)
            for f in s["fixes"]:
                assert f["draft"]["pyspark"] in code and (f["draft"]["parameter"] or "") in code
            # the targets the guard knows (WRITES) are exactly the tables the notebook writes
            writes = json.loads(re.search(r"^WRITES = (.*)$", code, re.M).group(1))
            assert len(writes) == len(silver.written_tables(s))
    for f in sug + flat:
        for q in [f.get("counts", {}).get("query", "")] + list((f.get("compare") or {}).values()):
            assert not q or (q.startswith("SELECT ") and not WRITES.search(q))
    md = er.markdown(er.report(p, v, generated_at=AT)) + er.markdown(er.report(fp, evidence.validate(fp, fex), generated_at=AT))
    assert not WRITES.search(md) and md.count(fixes.WHERE) == 2
    assert "The source tables are never written" in silver.notebook_source(silver.apply_fixes(silver.spec(p, INFO), sug))


def test_a_header_table_that_would_be_a_source_table_is_refused():
    from fabric_backend.infer import PlanInputError
    from fabric_backend.schema import Column, Table
    p, ex = _flat()
    rows = er.report(p, evidence.validate(p, ex), generated_at=AT)["checklist"]
    p.schema.tables["order_lines_per_order_id"] = Table("order_lines_per_order_id", [Column("x", "int")], schema="x")
    s = silver.spec(p, dict(INFO, schema="x"))                              # its own silver table is the header table's name
    with pytest.raises(PlanInputError, match="already a source table or a silver table"):
        silver.apply_fixes(s, [r["fix"] for r in rows])


def test_without_fixes_the_notebook_is_unchanged(shop):
    _, _, p, _, sug = shop
    s = silver.spec(p, INFO, order_by={"orders": "order_date"})
    assert silver.cells(silver.apply_fixes(s, [])) == silver.cells(s)
    assert silver.cells(silver.apply_fixes(s, [f for f in sug if f["kind"] == "question"])) == silver.cells(s)
    assert "keep_one_per_key" not in silver.notebook_source(s) and "ORPHANS" not in silver.notebook_source(s)


def test_the_suggestions_are_the_same_every_time(shop):
    data, ex, p, v, sug = shop
    again = fixes.suggest(plan(seed.schema("shop")), evidence.validate(plan(seed.schema("shop")), bronze()[1]))
    assert json.dumps(sug) == json.dumps(again)
    s1 = silver.notebook_source(silver.apply_fixes(silver.spec(p, INFO), sug))
    s2 = silver.notebook_source(silver.apply_fixes(silver.spec(p, INFO), again))
    assert s1 == s2
    a, b = (er.markdown(er.report(p, v, generated_at=AT)) for _ in range(2))
    assert a == b


def test_no_time_speed_or_one_click_claim_and_nothing_presented_as_fixed(shop):
    _, _, p, v, sug = shop
    fp, fex = _flat()
    text = (json.dumps(sug) + er.markdown(er.report(p, v, generated_at=AT))
            + er.markdown(er.report(fp, evidence.validate(fp, fex), generated_at=AT))
            + silver.notebook_source(silver.apply_fixes(silver.spec(p, INFO), sug)))
    assert not re.search(r"\b(minutes?|seconds?|hours?|fast|faster|quick(ly)?|instant(ly)?|one[- ]click|automatic(ally)?|"
                         r"in no time|speed)\b", text, re.I)
    assert not re.search(r"(?<!nothing )\b(is|are|was|were|has been|have been) (now )?fixed\b", text, re.I)
    assert "nothing is fixed until" in text and "It has not run" in text and "draft: not run" in text
