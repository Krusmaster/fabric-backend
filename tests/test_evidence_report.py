"""Round n79: the evidence report (fabric_backend/evidence_report.py), the pilot's hand-over: every key and
relationship of the plan with its rule, every check with its counts or "not checked", the open questions, decisions
and created ids as given; no row value and nothing marked as passed that was not counted."""
from __future__ import annotations

import json
import re

import pytest

from fabric_backend import browser_check as bc, demo_app, evidence, evidence_report as er, tool_status as ts, younium_demo as yd
from fabric_backend.infer import plan
from fabric_backend.platforms.local import sample_source

AT = "2026-11-02T08:00:00+00:00"


@pytest.fixture()
def shop():
    src = sample_source()
    p = plan(src.schema)                                        # as /check plans it: by the names
    yield src, p, evidence.validate(p, src.execute)
    src.close()


def _row_values(src) -> set[str]:
    """Every text value in the shop's rows that could be recognised in a file (four characters or more)."""
    out = set()
    for t in src.schema:
        for row in src.execute(f"SELECT * FROM shop.[{t.name}]"):
            out |= {str(v) for v in row.values() if isinstance(v, str) and len(v) >= 4}
    return out


def test_every_relationship_and_key_of_the_shop_plan_is_in_the_report(shop):
    src, p, v = shop
    rep = er.report(p, v, source="shop (synthetic)", generated_at=AT)
    md = er.markdown(rep)
    got = {(r["source"], tuple(r["source_cols"]), r["target"], r["rule"]) for r in rep["relationships"]}
    assert got == {(r.source, tuple(r.source_cols), r.target, r.rule) for r in p.relationships} and len(got) == len(p.relationships)
    for r in p.relationships:
        assert f"| {r.source} | {'+'.join(r.source_cols)} | {r.target} | {'+'.join(r.target_cols)} | {r.rule} |" in md
        assert f"| relationship | {r.source}.{'+'.join(r.source_cols)} -> {r.target} | holds for all " in md
    assert {k["table"] for k in rep["keys"]} == set(p.keys) and all(f"| key | key {t}." in md for t in p.keys)
    assert rep["status"] == "Draft" == ts.EVIDENCE_REPORT and "Status: **Draft**" in md
    assert rep["engine"]["version"] and rep["generated_at"] == AT and rep["source"] == "shop (synthetic)"
    assert rep["summary"]["not_checked"] == 0 and all(c["read"].startswith("all ") for c in rep["checks"])


def test_no_row_value_is_in_the_report(shop):
    src, p, v = shop
    values = _row_values(src)
    assert len(values) > 50                                     # names, e-mail addresses, cities, dates
    text = er.markdown(er.report(p, v, generated_at=AT)) + er.to_json(er.report(p, v, generated_at=AT))
    assert not [x for x in values if x in text]
    check = bc.analyze("sample")
    assert not [x for x in values if x in check["evidence_report"]["markdown"]]
    assert "For example" in json.dumps(check["findings"])       # the page quotes an example row; the report does not
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text)   # no tenant or workspace id


def test_a_check_that_did_not_run_is_not_checked_never_passed(shop):
    src, p, _ = shop
    v = evidence.validate(p, src.execute, max_items=3)          # three counting queries: the rest is skipped
    rep = er.report(p, v, generated_at=AT)
    skipped = [c for c in rep["checks"] if c["result"] == "not checked"]
    assert len([c for c in skipped if c["check"] != "amount_level"]) == len(p.keys) + len(p.relationships) - 3
    assert [c["what"] for c in skipped if c["check"] == "amount_level"] == ["products.list_price over order_items"]   # no budget left to count it
    assert len(skipped) == rep["summary"]["not_checked"]
    assert all("passed" not in c and "counts" not in c and c["read"] == "not checked" for c in skipped)
    md = er.markdown(rep)
    assert all(f"| {c['check']} | {c['what']} | not checked | — | not checked |" in md for c in skipped)
    none = er.report(p, None, generated_at=AT)
    assert all(c["result"] == "not checked" for c in none["checks"]) and len(none["checks"]) == len(p.keys) + len(p.relationships)
    assert "Nothing was counted against the rows: every key and relationship is not checked." in none["open_questions"]


def test_decisions_and_created_ids_are_copied_as_given(shop):
    _, p, v = shop
    rep = er.report(p, v, decisions=[{"what": "orders.ship_to_id -> addresses", "decision": "accepted", "by": "Data owner", "at": "2026-11-02"},
                                     {"what": "audit_log has no key", "decision": "left keyless"}],
                    created=[{"kind": "GraphQLApi", "id": "item-123", "name": "shop_api"}], generated_at=AT)
    assert rep["decisions"][0]["by"] == "Data owner" and rep["decisions"][1] == {"what": "audit_log has no key", "decision": "left keyless",
                                                                                  "by": "not recorded", "at": "not recorded"}
    md = er.markdown(rep)
    assert "| audit_log has no key | left keyless | not recorded | not recorded |" in md and "- GraphQLApi: `item-123` (shop_api)" in md


def test_the_open_questions_name_what_a_person_decides(shop):
    _, p, v = shop
    q = er.report(p, v, generated_at=AT)["open_questions"]
    assert "audit_log has no key: nothing can point at it. Is there one?" in q
    assert any(x.startswith("products.list_price over order_items") for x in q)


def test_a_pack_relationship_names_the_pack_and_its_source():
    schema, execute = yd.sqlite()
    p = plan(schema)
    rep = er.report(p, evidence.validate(p, execute, max_items=200), generated_at=AT)
    assert {r["rule"] for r in rep["relationships"]} == {"Younium + Salesforce pack"} and {r["rule_code"] for r in rep["relationships"]} == {"SAP pack"}
    assert all(r["basis"].startswith("younium_salesforce pack (") for r in rep["relationships"])
    assert any("1 of 4 rows point at nothing" in x for x in rep["open_questions"])


def test_check_offers_it_as_a_draft_file_for_every_example():
    for kind, name in bc.NAMES.items():
        e = bc.analyze(kind)["evidence_report"]
        assert e["name"] == f"{name}_evidence_report.md" and e["status"] == "Draft" and e["markdown"].startswith("# Evidence report: ")
    e = bc.analyze("columns", text="orders.order_id\norders.customer_id\ncustomers.customer_id")["evidence_report"]
    assert e["summary"]["counted"] == 0 and e["summary"]["not_checked"] == e["summary"]["checks"] > 0


def test_the_demo_writes_it_beside_the_dictionary_with_the_decisions_and_their_time():
    s = demo_app.Session(sample_source())
    s.accept("sug:orders.ship_to_id>addresses")
    names = [x["name"] for x in s.state()["exports"]]
    assert names.index("evidence-report.md") == names.index("dictionary.md") + 1 and "evidence-report.json" in names
    files = s.exports(s.plan(), s._validation, [])
    rep = json.loads(files["evidence-report.json"][1])
    assert rep["decisions"][0]["decision"] == "accepted" and rep["decisions"][0]["by"] == "not recorded"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", rep["decisions"][0]["at"])
    assert ("orders", ["ship_to_id"], "addresses", "confirmed") in [(r["source"], r["source_cols"], r["target"], r["rule"]) for r in rep["relationships"]]
    assert files["evidence-report.md"][1].startswith("# Evidence report: Synthetic shop data")
