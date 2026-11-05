"""Round n101: validate_plan answers with a summary by default; detail="full" is the answer it gave before, unchanged.

The summary is written from the full answer only (evidence.summarize): the same queries, the same counts, the same
masking. These tests also measure what it saves, in characters of the JSON the tool returns (json.dumps, indent=2),
on the synthetic shop rows and on a larger golden fixture (tests/fixtures/schemas/adventureworks.json) whose counts
come from a fixed double; the numbers are the ones docs/INFERENCE.md quotes.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import golden_support as gs
from fabric_backend import evidence, seed
from fabric_backend.infer import PlanInputError, plan
from fabric_backend.schema import Schema

GOLDEN = Path(__file__).parent / "golden"
FIXTURES = Path(__file__).parent / "fixtures" / "schemas"


def _text(out: dict) -> str:
    return json.dumps(out, indent=2, default=str)                   # what the tool returns


def _shop():
    db = gs.shop_database()

    def execute(sql):
        cur = db.execute(gs._sqlite(sql))
        return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    p = plan(seed.schema("shop"))
    return p, evidence.validate(p, execute)


def _adventureworks():
    """The 71-table AdventureWorks fixture with counts from a double: every key unique except one with duplicates,
    every fourth relationship with orphans, one empty source (nothing to count), one line per header."""
    fx = json.loads((FIXTURES / "adventureworks.json").read_text(encoding="utf-8"))
    rows = [("dbo", t["name"], c, typ, i) for t in fx["tables"] for i, (c, typ) in enumerate(t["columns"], 1)]
    p = plan(Schema.from_information_schema(rows, schema="dbo"))
    seen = {"key": 0, "rel": 0}

    def execute(sql):
        row = {"n": 1000, "nulls": 0, "distinct_keys": 1000, "with_value": 800, "orphans": 0, "several": 0,
               "headers": 100, "headers_in_table": 100, "avg_lines": 1.0, "min_lines": 1, "max_lines": 1}
        if "distinct_keys" in sql:
            seen["key"] += 1
            if seen["key"] == 2:
                row["distinct_keys"] = 990
        elif "with_value" in sql:
            seen["rel"] += 1
            if seen["rel"] % 4 == 0:
                row["orphans"] = 12
            if seen["rel"] == 5:
                row["with_value"] = 0
        return [row]
    return p, evidence.validate(p, execute, max_items=200)


def test_the_default_is_the_summary_and_full_is_the_previous_answer():
    """The golden calls with detail="full" carry the answers recorded before n101 (the git history of tests/golden
    shows them unchanged); the default call's answer is the summary of exactly that full answer."""
    for name in ("hosted_tools", "local_tools"):
        calls = [e for e in json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8")) if e.get("tool") == "validate_plan"]
        full = next(e for e in calls if e["args"].get("detail") == "full" and e["args"].get("source", "demo_lh") == "demo_lh")
        default = next(e for e in calls if "detail" not in e["args"])
        assert "keys" in full["answer"] and "relationships" in full["answer"] and "detail" not in full["answer"]
        assert default["answer"]["detail"] == "summary"
        assert default["answer"] == json.loads(_text(evidence.summarize(full["answer"])))
        assert default["rest"] == full["rest"]                      # the same calls to Fabric


def test_failing_and_not_counted_checks_are_all_there_with_their_counts():
    p, full = _adventureworks()
    s = evidence.summarize(full, p)
    failing_keys = [k for k in full["keys"] if not k["verdict"].startswith("unique")]
    failing_rels = [r for r in full["relationships"] if not r["verdict"].startswith("holds") or "; but" in r["verdict"]]
    assert failing_keys and failing_rels
    assert s["attention"]["keys"] == failing_keys                   # whole entries: counts, rule, verdict
    assert s["attention"]["relationships"] == failing_rels
    assert any(r["verdict"].startswith("no rows with a value") for r in s["attention"]["relationships"])   # not counted
    assert s["needs_attention"] == len(failing_keys) + len(failing_rels)
    assert s["summary"] == full["summary"] and s["note"] == full["note"]
    t = s["totals"]
    assert t["keys"]["checked"] == len(full["keys"]) and t["keys"]["failed"] == 1
    assert t["relationships"]["checked"] == len(full["relationships"])
    assert t["relationships"]["passed"] + t["relationships"]["failed"] + t["relationships"].get("not_counted", 0) \
        + t["relationships"].get("passed_with_warning", 0) == len(full["relationships"])


def test_the_left_out_count_is_the_number_of_passing_checks():
    p, full = _adventureworks()
    s = evidence.summarize(full, p)
    passing = (sum(k["verdict"].startswith("unique") for k in full["keys"])
               + sum(r["verdict"].startswith("holds") and "; but" not in r["verdict"] for r in full["relationships"])
               + sum(isinstance(f["rows_per_header"], dict) and f["rows_per_header"]["max_lines"] <= 1
                     for f in full["amount_levels"]["findings"]))
    assert s["left_out"]["passing_checks"] == passing
    assert s["left_out"]["keys"] + s["left_out"]["relationships"] + s["left_out"].get("amount_levels", 0) == passing
    assert f"{passing} passing check(s) are left out" in s["left_out"]["how"] and 'detail="full"' in s["left_out"]["how"]
    shown = sum(len(v) for v in s["attention"].values())
    everything = len(full["keys"]) + len(full["relationships"]) + len(full["amount_levels"]["findings"])
    assert shown + passing == everything                            # nothing dropped without a word


def test_an_all_passing_plan_gets_the_one_line_form():
    p, full = _shop()
    full["amount_levels"]["findings"] = []                          # the shop's one header amount is the only finding
    s = evidence.summarize(full, p)
    assert "attention" not in s and "left_out" not in s
    assert "\n" not in s["result"]
    assert s["result"] == ('All 12 counted checks passed; they are left out of this summary, and detail="full" lists each '
                           "with its counts and rule.")


def test_checks_beyond_max_items_are_counted_as_not_checked():
    def execute(sql):
        return [{"n": 1, "nulls": 0, "distinct_keys": 1, "with_value": 1, "orphans": 0}]
    p = plan(seed.schema("shop"))
    s = evidence.summarize(evidence.validate(p, execute, max_items=3), p)
    assert s["totals"]["not_checked_beyond_max_items"] == len(p.keys) + len(p.relationships) - 3
    assert "3 passing check(s) are left out" in s["left_out"]["how"] and "raise max_items" in s["left_out"]["how"]
    assert "checked 3 of" in s["summary"]
    assert s["totals"]["amount_levels"]["not_counted"] == 1                    # no budget left to count the amount
    s = evidence.summarize({**evidence.validate(p, execute, max_items=3), "amount_levels": {"findings": []}}, p)
    assert "raise max_items" in s["result"] and s["result"].startswith("All 3 counted checks passed (")


def test_an_invalid_detail_is_a_clear_error():
    with pytest.raises(PlanInputError, match=r"detail: 'short' is not one of summary, full"):
        evidence.pick_detail("short")
    assert evidence.pick_detail(None) == "summary" and evidence.pick_detail(" FULL ") == "full"


def test_an_invalid_detail_from_the_tools_is_bad_input_before_any_query(monkeypatch):
    from fabric_backend import mcp_server
    monkeypatch.setattr(mcp_server, "_connection", lambda *a, **k: pytest.fail("no connection for a bad detail"))
    out = json.loads(mcp_server.validate_plan(schema="shop", detail="tiny"))
    assert out["kind"] == "bad_input" and "detail: 'tiny' is not one of summary, full" in out["error"]


# The measured sizes (characters of the tool's JSON). Pinned so the documentation cannot drift from them.
SIZES = {"shop": (5312, 3197), "adventureworks": (62235, 9946)}     # n103 added next_steps: 2246 and 8241 before


@pytest.mark.parametrize("name", ["shop", "adventureworks"])
def test_the_summary_is_smaller_and_its_size_is_measured(name):
    p, full = _shop() if name == "shop" else _adventureworks()
    f, s = len(_text(full)), len(_text(evidence.summarize(full, p)))
    print(f"\n{name}: full {f} characters, summary {s} ({round(100 * s / f)}%)")
    assert s < f
    assert (f, s) == SIZES[name]


def test_the_hosted_tool_answers_measure_the_same_on_the_shop():
    """The hosted golden answers (Fabric mocked, the shop rows in SQLite, R5's ship_to_id included): 5 608 characters
    in full, 3 197 as the summary (2 246 before n103's next_steps)."""
    calls = [e for e in json.loads((GOLDEN / "hosted_tools.json").read_text(encoding="utf-8")) if e.get("tool") == "validate_plan"]
    sizes = {e["args"].get("detail", "summary"): len(_text(e["answer"])) for e in calls if e["args"]["source"] == "demo_lh"}
    assert sizes == {"full": 5608, "summary": 3197}


def test_sap_verify_refuses_a_summary_and_asks_for_the_full_answer(tmp_path, capsys):
    from fabric_backend import cli
    p, full = _shop()
    path = tmp_path / "validation.json"
    path.write_text(_text(evidence.summarize(full, p)), encoding="utf-8")
    assert cli.main(["sap-verify", str(path), "--where", "synthetic", "--when", "2026-11-05"]) == 2
    assert 'detail="full"' in capsys.readouterr().err
