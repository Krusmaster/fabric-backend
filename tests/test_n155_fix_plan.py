"""Round n155: a proposed fix per finding (validate_plan fixes=true, fabric_backend/fix_plan.py), applied only through the
silver notebook (create_silver_notebook fixes=[...]). On the six /check datasets of round n150
(tests/fixtures/check_cases/) and the shop seed with a bronze layer's problems: what is wrong, the fix in plain words,
the PySpark it adds, counts before and expected after, and business decisions as questions that are never applied for
anyone. The silver steps run in Python (silver.simulate) on the same rows and end with the expected counts. Nothing
here writes a source table; all rows are synthetic."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from fabric_backend import evidence, fix_plan, seed, server, silver
from fabric_backend.infer import PlanInputError, plan
from fabric_backend.platforms.local import folder_source
from silver_cases import seed_rows, sqlite_execute

CASES = Path(__file__).parent / "fixtures" / "check_cases"
INFO = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="lh", item_kind="Lakehouse",
            schema="data", schemas_enabled=True)
WRITES = re.compile(r"\b(INSERT\s+INTO|UPDATE\s+\S+\s+SET|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE|DROP\s+TABLE|CREATE\s+TABLE)\b", re.I)


def _rows(src) -> dict[str, list[dict]]:
    return {t.name: [dict(r) for r in src.execute(f"SELECT * FROM [{src.schema.schema}].[{t.name}]")] for t in src.schema}


def case(name: str, folder: Path | None = None) -> dict:
    src = folder_source(folder or CASES / name)
    try:
        p = plan(src.schema)
        v = evidence.validate(p, src.execute)
        return {"plan": p, "validation": v, "proposal": fix_plan.propose(p, v, src.execute), "rows": _rows(src)}
    finally:
        src.close()


def by_id(c: dict, fid: str) -> dict:
    return next(e for e in c["proposal"]["fixes"] if e["id"] == fid)


def run(c: dict, accepted, given=None) -> dict:
    s = fix_plan.accept(silver.spec(c["plan"], INFO), c["proposal"]["fixes"], accepted, c["plan"])
    return silver.simulate(s, c["rows"], given) | {"spec": s}


# ------------------------------------------------------------------ the fixtures' expected values -----------------

def test_04_a_duplicate_parent_of_exact_copies_is_a_mechanical_fix_with_its_counts():
    c = case("04_duplicate_parent")
    e = by_id(c, "key:customers")
    assert e["type"] == "mechanical" and e["questions"] == [] and e["counts"]["differing_key_values"] == 0
    assert e["counts"]["before"] == {"rows": 4, "rows_with_null_key": 0, "distinct_key_values": 3, "duplicate_rows": 1}
    assert e["counts"]["expected_after"]["silver_rows"] == 3 and e["counts"]["expected_after"]["quarantined"] == 1
    assert "every one an exact copy" in e["what_is_wrong"] and e["proposed_fix"].startswith("In silver: of each set of exact copies")
    assert e["snippet"]["pyspark"].startswith("df = keep_one_per_key(") and "SELECT DISTINCT *" in e["snippet"]["tsql_differing"]
    out = run(c, ["key:customers"])
    assert len(out["silver"]["customers"]) == 3
    assert [q["source_table"] for q in out["quarantine"]] == ["customers"]
    assert "an exact copy" in out["quarantine"][0]["reason"]


def test_03_a_null_foreign_key_is_not_an_orphan_and_the_orphan_goes_to_quarantine():
    c = case("03_null_foreign_key")
    e = by_id(c, "rel:orders.customer_id>customers")
    assert e["type"] == "mechanical" and e["counts"]["before"] == {"rows_with_value": 3, "orphans": 1}
    assert e["counts"]["expected_after"] == {"silver_rows_with_value": 2, "quarantined": 1}
    assert "Rows with no value (NULL) are not orphans" in e["what_is_wrong"]
    assert e["snippet"]["parameter"].startswith('ORPHANS["rel:orders.customer_id>customers"] = "quarantine"')
    ids = [q["id"] for q in e["questions"]]
    assert ids == ["elsewhere:rel:orders.customer_id>customers", "drop_or_create:rel:orders.customer_id>customers"]
    assert all(q["default"] is None and q["ask"].endswith("?") for q in e["questions"])
    out = run(c, ["rel:orders.customer_id>customers"])
    orders = out["silver"]["orders"]
    assert len(orders) == 4 and sum(r["customer_id"] is not None for r in orders) == 2      # 2 matching + 2 NULL kept
    assert [(q["source_table"], q["row"]["customer_id"]) for q in out["quarantine"]] == [("orders", 999)]


def test_03_set_null_is_taken_only_when_chosen():
    c = case("03_null_foreign_key")
    out = run(c, [{"id": "rel:orders.customer_id>customers", "choice": "set_null"}])
    assert len(out["silver"]["orders"]) == 5 and sum(r["customer_id"] is None for r in out["silver"]["orders"]) == 3
    f = out["spec"]["fixes"][0]
    assert f["after"] == {"silver_rows_with_value": 2, "silver_rows_set_to_null": 1, "copies_in_quarantine": 1}
    with pytest.raises(PlanInputError, match="offers quarantine or set_null, not 'drop'"):
        run(c, [{"id": "rel:orders.customer_id>customers", "choice": "drop"}])


def test_05_the_sap_orphan_on_a_composite_reference_and_the_fan_out_sums():
    c = case("05_sap_mandt")
    o = by_id(c, "rel:VBAP.MANDT+VBELN>VBAK")
    assert o["type"] == "mechanical" and o["counts"]["before"] == {"rows_with_value": 5, "orphans": 1}
    assert o["counts"]["expected_after"] == {"silver_rows_with_value": 4, "quarantined": 1}
    assert "set_null_not_offered" in o and [c_["id"] for c_ in o["choices"]] == ["quarantine"]   # MANDT+VBELN is part of the key
    f = by_id(c, "level:VBAK.NETWR")
    assert f["type"] == "business_decision" and f["finding"] == "amount_repeated" and f["silver"] is None
    assert f["counts"]["sums"] == {"summed_over_lines": 700, "summed_per_header": 600}          # the fixture's expected values
    assert f["counts"]["before"]["max_lines"] == 2 and "fan-out" in f["what_is_wrong"]
    assert set(f["snippet"]["tsql_compare"]) == {"summed_over_lines", "summed_per_header"}
    out = run(c, ["rel:VBAP.MANDT+VBELN>VBAK"])
    assert len(out["silver"]["VBAP"]) == 4 and len(out["quarantine"]) == 1


def test_01_the_composite_key_holds_and_the_fan_out_is_a_question_with_the_sums():
    c = case("01_composite_key")
    assert c["plan"].keys["order_items"][0] == ["order_id", "line_no"]
    assert [e["finding"] for e in c["proposal"]["fixes"]] == ["amount_repeated"]                  # no key finding: it is unique
    f = c["proposal"]["fixes"][0]
    assert f["id"] == "level:orders.order_total" and f["type"] == "business_decision"
    assert f["counts"]["sums"] == {"summed_over_lines": 1300, "summed_per_header": 600}
    assert f["counts"]["before"]["max_lines"] == 3 and "never over the joined order_items rows" in f["proposed_fix"]


def test_02_and_06_have_nothing_to_fix_in_silver():
    assert all(e["silver"] is None for e in case("02_many_to_many")["proposal"]["fixes"])
    assert case("06_mismatched_names")["proposal"]["fixes"] == []


# ------------------------------------------------------------------ business decisions are never applied ----------

def test_a_business_decision_is_refused_as_a_fix():
    c = case("05_sap_mandt")
    with pytest.raises(PlanInputError, match="business decision with nothing for silver to do"):
        run(c, ["level:VBAK.NETWR"])
    with pytest.raises(PlanInputError, match="no such finding"):
        run(c, ["key:nope"])


def test_differing_duplicates_without_a_time_column_stop_the_notebook_until_someone_decides():
    data = seed_rows()
    p = plan(seed.schema("shop"))
    ex = sqlite_execute(data)
    prop = fix_plan.propose(p, evidence.validate(p, ex), ex)
    e = next(x for x in prop["fixes"] if x["id"] == "key:orders")
    assert e["type"] == "business_decision" and e["counts"]["differing_key_values"] == 1
    assert e["decision"] == {"winner": None} and [q["id"] for q in e["questions"]] == ["winner:orders"]
    s = fix_plan.accept(silver.spec(p, dict(INFO, schema="shop")), prop["fixes"], ["key:orders"], p)
    with pytest.raises(ValueError, match="name the column whose latest value wins"):
        silver.simulate(s, data)
    s = fix_plan.accept(silver.spec(p, dict(INFO, schema="shop")), prop["fixes"], [{"id": "key:orders", "winner": "order_date"}], p)
    out = silver.simulate(s, data)
    assert sum(r["order_id"] == 100 for r in out["silver"]["orders"]) == 1
    assert 'DUPLICATE_WINNER["orders"] = "order_date"' in silver.notebook_source(s)
    with pytest.raises(PlanInputError, match="has no column 'nope'"):
        fix_plan.accept(silver.spec(p, dict(INFO, schema="shop")), prop["fixes"], [{"id": "key:orders", "winner": "nope"}], p)


def test_differing_duplicates_with_a_change_time_keep_the_latest_mechanically(tmp_path):
    (tmp_path / "customers.csv").write_text("customer_id,customer_name,updated_at\n1,Alpha,2026-01-01\n1,Alpha AB,2026-03-01\n"
                                            "2,Beta,2026-01-01\n2,Beta,2026-01-01\n")
    c = case("", tmp_path)
    e = by_id(c, "key:customers")
    assert e["type"] == "mechanical" and e["decision"] == {"winner": "updated_at"} and e["questions"] == []
    assert e["counts"]["differing_key_values"] == 1 and "the latest by updated_at stays" in e["proposed_fix"]
    assert e["snippet"]["parameter"].startswith('DUPLICATE_WINNER["customers"] = "updated_at"')
    out = run(c, ["key:customers"])
    assert sorted((r["customer_id"], r["customer_name"]) for r in out["silver"]["customers"]) == [(1, "Alpha AB"), (2, "Beta")]
    assert len(out["quarantine"]) == 2


def test_nothing_is_applied_that_was_not_accepted():
    c = case("05_sap_mandt")
    s = fix_plan.accept(silver.spec(c["plan"], INFO), c["proposal"]["fixes"], [], c["plan"])
    assert not s.get("fixes") and silver.notebook_source(s) == silver.notebook_source(silver.spec(c["plan"], INFO))
    assert c["proposal"]["dry_run"] is True and c["proposal"]["status"].startswith("proposed: nothing ran")


# ------------------------------------------------------------------ the notebook ----------------------------------

def test_the_notebook_has_the_accepted_decisions_and_a_table_of_counts_per_fix():
    c = case("04_duplicate_parent")
    s = run(c, ["key:customers"])["spec"]
    code = silver.notebook_source(s)
    assert "FIX_COUNTS = [" in code and '"id": "key:customers"' in code and "expected_after" in code
    assert ".show(max(len(_fix_rows), 1), False)" in code
    assert silver.fix_counts(s) == [{"id": "key:customers", "table": "customers",
                                     "before": {"rows": 4, "rows_with_null_key": 0, "distinct_key_values": 3, "duplicate_rows": 1},
                                     "expected_after": {"silver_rows": 3, "quarantined": 1, "of_which_null_key": 0, "of_which_duplicate": 1}}]
    assert not WRITES.search(code)
    assert set(silver.written_tables(s)).isdisjoint(silver.source_tables(s))
    compile(code.replace("# MAGIC", "#"), "notebook", "exec")


# ------------------------------------------------------------------ the tools --------------------------------------

@pytest.fixture()
def hosted(monkeypatch):
    """validate_plan and the silver tools over the local copy of a /check dataset, as the hosted server reads Fabric."""
    opened = {}

    def connect(name):
        src = folder_source(CASES / name)
        opened[name] = src
        return src

    def connected(workspace, source, schema, ctx):
        src = connect(source)
        return src.schema, src.execute

    def inputs(workspace, source, schema, keys, confirmed, ctx):
        src = connect(source)
        return server._hosted_plan(src.schema, keys, confirmed, src.execute), dict(INFO, item_name=source)
    monkeypatch.setattr(server, "_connected", connected)
    monkeypatch.setattr(server, "_source_inputs", inputs)
    yield
    for s in opened.values():
        s.close()


def test_validate_plan_with_fixes_proposes_and_the_silver_draft_applies_the_accepted(hosted):
    out = json.loads(server.validate_plan("ws", "03_null_foreign_key", schema="data", fixes=True))
    fp = out["fix_plan"]
    assert fp["dry_run"] is True and fp["counts"] == {"findings": 1, "mechanical": 1, "business_decision": 0}
    assert [e["id"] for e in fp["fixes"]] == ["rel:orders.customer_id>customers"]
    assert "fix_plan" not in json.loads(server.validate_plan("ws", "03_null_foreign_key", schema="data"))
    draft = json.loads(server.silver_notebook_draft("ws", "03_null_foreign_key", schema="data", fixes=[fp["fixes"][0]["id"]]))
    assert [f["id"] for f in draft["fixes"]] == ["rel:orders.customer_id>customers"]
    assert draft["fixes"][0]["expected_after"] == {"silver_rows_with_value": 2, "quarantined": 1}
    assert 'ORPHANS["rel:orders.customer_id>customers"] = "quarantine"' in draft["notebook"]["content"]
    plain = json.loads(server.silver_notebook_draft("ws", "03_null_foreign_key", schema="data"))
    assert "fixes" not in plain and "ORPHANS" not in plain["notebook"]["content"]
    bad = json.loads(server.create_silver_notebook("ws", "05_sap_mandt", name="silver_x", schema="data", fixes=["level:VBAK.NETWR"]))
    assert bad["kind"] == "bad_input" and "business decision" in bad["error"]
    dry = json.loads(server.create_silver_notebook("ws", "04_duplicate_parent", name="silver_x", schema="data", fixes=["key:customers"]))
    assert dry["dry_run"] is True and dry["fixes"][0]["id"] == "key:customers"


def test_validate_plan_fixes_takes_a_review_file_and_tables(hosted):
    rv = json.loads(server.review_plan("ws", "05_sap_mandt", schema="data", decisions=[
        {"item": "rel:VBAP.MANDT+VBELN>VBAK", "review": "accepted", "reason": "checked"}]))["review"]
    out = json.loads(server.validate_plan("ws", "05_sap_mandt", schema="data", fixes=True, review=rv))["fix_plan"]
    assert by_id({"proposal": out}, "rel:VBAP.MANDT+VBELN>VBAK")["review"] == "accepted"
    only = json.loads(server.validate_plan("ws", "05_sap_mandt", schema="data", fixes=True, tables=["VBAK"]))["fix_plan"]
    assert [e["table"] for e in only["fixes"]] == ["VBAK"]


def test_no_speed_or_one_click_claim_and_nothing_presented_as_fixed():
    text = json.dumps(case("05_sap_mandt")["proposal"]).lower()
    for word in ("instant", "seconds", "one click", "one-click", "automatically fixed", "is fixed", "faster", "effortless"):
        assert word not in text, word


def test_the_validate_plan_card_lists_the_proposed_fixes_as_text():
    from fabric_backend import mcp_apps
    html = mcp_apps.card_html()
    assert "data.fix_plan" in html and '"Proposed fix, "' in html and '"To decide, "' in html
