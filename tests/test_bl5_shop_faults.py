"""2026-11-21, round BL5 (sprint item BL5, backlog C-37). The shop with five planted faults (fabric_backend/shop_faults.py).

Each fault of FAULTS is asserted with the reason Krusgraph gives, word for word, and nothing else is flagged beyond what
the clean shop already shows. F5 (two currencies in one amount column) is not detected today: the test asserts that
too, so the day a check finds it this file fails and FAULTS and docs/PLANTED-FAULTS.md are updated on purpose.

tests/corpus/shop_faults.json is the corpus case in the shape of tests/corpus/<name>.json (tests/f2_corpus.py): the
three plans scored against the truth, the plan and what the rows say. It is asserted exactly here.

    python tests/test_bl5_shop_faults.py --write    write tests/corpus/shop_faults.json from what the engine does now

--write is for a conscious change of a rule: read the diff before committing it. No network, no Fabric, SQLite only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import f2_corpus as corpus                          # noqa: E402
from fabric_backend import shop_faults as sf        # noqa: E402

CASE = ROOT / "tests" / "corpus" / "shop_faults.json"
DOC = ROOT / "docs" / "PLANTED-FAULTS.md"

# the truth the generator writes: the shop's keys and links, and the signups' own key and link (it points at customers
# by intent; the rows are what is wrong)
TRUTH = {"keys": {"customers": ["customer_id"], "categories": ["id"], "products": ["product_id"], "addresses": ["address_id"],
                  "orders": ["order_id"], "order_items": ["order_id", "line_no"], "newsletter_signups": ["signup_id"]},
         "links": [["products", ["category_id"], "categories"], ["addresses", ["customer_id"], "customers"],
                   ["orders", ["customer_id"], "customers"], ["orders", ["ship_to_id"], "addresses"],
                   ["order_items", ["order_id"], "orders"], ["order_items", ["product_id"], "products"],
                   ["audit_log", ["customer_id"], "customers"], ["newsletter_signups", ["customer_id"], "customers"]]}


def corpus_case() -> dict:
    """The case as tests/f2_corpus.py's run() writes one: names, names and R5, and with the row profile."""
    from fabric_backend import propose
    from fabric_backend.infer import plan
    data = sf.tables()
    tables = {t: cols for t, (cols, _r) in data.items()}
    rows = {t: r for t, (_c, r) in data.items()}
    schema, execute, close = corpus.database(sf.SCHEMA, tables, rows)
    try:
        aliases = propose.signature_aliases
        propose.signature_aliases = lambda *a, **k: ({}, {})
        try:
            names = plan(schema)
            before = plan(schema, execute=execute)
        finally:
            propose.signature_aliases = aliases
        after = plan(schema, execute=execute, profile=True)
        return {"name": "shop_faults", "title": "Shop sample with five planted faults",
                "source": "fabric_backend/shop_faults.py, synthetic (the seed shop with five faults planted, round BL5)",
                "rows": sum(len(r) for r in rows.values()),
                "names": corpus.score(names, TRUTH), "before": corpus.score(before, TRUTH), "after": corpus.score(after, TRUTH),
                "plan": corpus.plan_of(after), "row_results": corpus.rows_of(after, execute),
                "planted": {f["id"]: f"{f['table']}: {f['planted']}" for f in sf.FAULTS}}
    finally:
        close()


@pytest.fixture(scope="module")
def result():
    return sf.check()


def test_the_samples_rows_are_the_same_on_every_run():
    assert sf.tables() == sf.tables()
    t = sf.tables()
    assert set(t) == set(sf.COLUMNS) and len(t["customers"][1]) == 11 and len(t["order_items"][1]) == 137
    assert {r[5] for r in t["orders"][1]} == {"EUR", "SEK"}


@pytest.mark.parametrize("fault", [f for f in sf.FAULTS if f["detected"]], ids=lambda f: f["id"])
def test_each_planted_fault_is_found_with_its_reason(result, fault):
    said = result["flagged"].get(fault["item"])
    assert said is not None, f"{fault['id']} not flagged: {sorted(result['flagged'])}"
    assert fault["finding"] in said


def test_the_currency_fault_is_not_detected_yet_and_says_so(result):
    f5 = next(f for f in sf.FAULTS if f["id"] == "F5")
    assert f5["detected"] is False and f5["finding"].startswith("not detected")
    assert f5["item"] not in result["flagged"]
    assert not any("currenc" in v.lower() for v in result["flagged"].values())


def test_nothing_else_is_flagged(result):
    assert result["other"] == []
    assert set(result["flagged"]) == {f["item"] for f in sf.FAULTS if f["detected"]} | set(sf.CLEAN_FINDINGS)
    assert all(f["as_expected"] for f in result["faults"])
    assert result["summary"] == "5 of 6 keys unique, 5 of 7 relationships hold without orphans"


def test_f1_also_adds_a_caveat_to_every_link_into_customers_and_nowhere_else(result):
    """A duplicate key makes every link into that table ambiguous: the passing links into customers say so."""
    caveat = "but the target key of customers is not unique"
    with_caveat = sorted(f"{r['source']}.{'+'.join(r['columns'])} -> {r['target']}" for r in result["validate"]["relationships"]
                         if caveat in str(r.get("verdict", "")))
    assert with_caveat == ["addresses.customer_id -> customers", "audit_log.customer_id -> customers",
                           "newsletter_signups.customer_id -> customers", "orders.customer_id -> customers"]


def test_the_clean_shop_flags_only_the_list_price_level():
    clean = sf.clean_check()
    assert set(clean["flagged"]) == set(sf.CLEAN_FINDINGS)
    assert clean["summary"] == "6 of 6 keys unique, 6 of 6 relationships hold without orphans"


def test_the_validate_plan_tool_gives_the_same_findings(monkeypatch):
    """The MCP tool itself (local server), over the same rows: its plan comes from the schema's names."""
    from fabric_backend import mcp_server
    from fabric_backend.infer import plan
    execute, close = sf._sqlite(sf.tables(), sf.SCHEMA)
    monkeypatch.delenv("KRUSGRAPH_PLATFORM", raising=False)
    monkeypatch.delenv("KRUSGRAPH_CSN", raising=False)
    monkeypatch.setattr(mcp_server, "_execute_factory", lambda schema: execute)
    monkeypatch.setattr(mcp_server, "_plan_on", lambda ex, schema, keys=None, confirmed=None, decisions=True:
                        plan(sf.schema(schema), keys, confirmed))
    try:
        out = json.loads(mcp_server.validate_plan(schema=sf.SCHEMA, detail="full", max_items=200))
    finally:
        close()
    got = sf.flagged(out)
    assert set(got) == {f["item"] for f in sf.FAULTS if f["detected"]} | set(sf.CLEAN_FINDINGS)
    for f in sf.FAULTS:
        if f["detected"]:
            assert f["finding"] in got[f["item"]]


def test_the_corpus_case_is_what_the_engine_does_now():
    assert json.loads(CASE.read_text(encoding="utf-8")) == corpus_case()


def test_the_corpus_case_scores_and_the_shops_scores_do_not_drop():
    case = json.loads(CASE.read_text(encoding="utf-8"))
    for stage in ("names", "before", "after"):
        assert case[stage]["keys_wrong"] == 0 and case[stage]["links_wrong"] == 0, stage
    # the faults are in the rows, not in the names: every true key and link but the signups' key is found by names
    assert (case["after"]["keys_right"], case["after"]["links_found"]) >= (case["names"]["keys_right"], case["names"]["links_found"] - 1)
    shop = corpus.expected("shop")
    assert corpus.run("shop")["after"] == shop["after"]                 # the clean shop is untouched
    assert "shop_faults" not in corpus.ORDER or corpus.expected("shop_faults") == case


def test_the_doc_lists_the_five_faults_and_says_f5_is_not_detected():
    doc = DOC.read_text(encoding="utf-8")
    assert doc.startswith("> 2026-11-21, round BL5")
    for f in sf.FAULTS:
        assert f"| {f['id']} |" in doc and f"`{f['table']}`" in doc
    assert "not detected" in doc and "BL10" in doc
    assert "python -m pytest tests/test_bl5_shop_faults.py" in doc


def test_no_model_call_and_no_network_in_the_module():
    src = (ROOT / "fabric_backend" / "shop_faults.py").read_text(encoding="utf-8")
    for word in ("anthropic", "openai", "requests", "urllib", "http://", "https://"):
        assert word not in src


if __name__ == "__main__":
    if "--write" in sys.argv:
        CASE.write_text(json.dumps(corpus_case(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {CASE.relative_to(ROOT)}")
    else:
        print(json.dumps({k: v for k, v in corpus_case().items() if k in ("names", "before", "after")}, indent=1))
