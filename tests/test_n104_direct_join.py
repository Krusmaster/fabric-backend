"""Round n104: the relationship check joins the target table directly, without SELECT DISTINCT, only when the same
validate run has counted exactly the target's join columns unique with no NULLs. Everywhere else it keeps the DISTINCT
form, and the counts are the same either way."""
import json
import sqlite3

import pytest

import golden_support as gs
from fabric_backend import evidence as ev
from fabric_backend import seed
from fabric_backend.dialects import sqlite_sql
from fabric_backend.infer import plan

DISTINCT = "LEFT JOIN (SELECT DISTINCT"


def _execute(con, log=None):
    def execute(sql):
        if log is not None:
            log.append(sql)
        cur = con.execute(sqlite_sql(sql))
        return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    return execute


def _counts(execute, schema, r, unique):
    row = execute(ev.relationship_sql(schema, r.source, r.source_cols, r.target, r.target_cols,
                                      blank_is_none=r.rule == "SAP pack", target_unique=unique))[0]
    return int(row["with_value"] or 0), int(row["orphans"] or 0)


def test_the_two_forms_differ_only_in_the_join():
    old = ev.relationship_sql("shop", "orders", ["customer_id"], "customers", ["customer_id"])
    new = ev.relationship_sql("shop", "orders", ["customer_id"], "customers", ["customer_id"], target_unique=True)
    assert old == ev.relationship_sql("shop", "orders", ["customer_id"], "customers", ["customer_id"], target_unique=False)
    assert "SELECT DISTINCT" in old and "DISTINCT" not in new
    assert old.replace("(SELECT DISTINCT [customer_id] FROM [shop].[customers])", "[shop].[customers]") == new


# ------------------------------------------------------------------ identical counts -------------------------------

def _sources():
    """Every fixture with rows: the shop rows, and the browser examples (planted orphans, the SAP pack's blanks)."""
    from fabric_backend.browser_check import _source
    yield "shop", plan(seed.schema("shop")), _execute(gs.shop_database())
    for kind in ("sample", "sap", "crm", "billing"):
        src, _ = _source(kind, None, "")
        yield kind, plan(src.schema), src.execute


@pytest.mark.parametrize("name,p,execute", list(_sources()), ids=lambda x: x if isinstance(x, str) else "")
def test_counts_are_identical_where_the_direct_form_runs(name, p, execute):
    out = ev.validate(p, execute, max_items=200)
    direct = 0
    for r in p.relationships:
        if ev.target_key_unique(out["keys"], r.target, r.target_cols):
            direct += 1
            assert _counts(execute, p.schema.schema, r, True) == _counts(execute, p.schema.schema, r, False), (name, vars(r))
    assert direct, f"{name}: no relationship to a unique key"


def _dirty_shop():
    """The shop rows with duplicates and NULLs: a duplicated customer and a customer without an id (the target side),
    orders with a NULL customer_id, two orders pointing at the duplicated customer and one at nothing (the source side)."""
    con = gs.shop_database()
    con.execute("INSERT INTO shop.customers SELECT * FROM shop.customers WHERE customer_id = 1")
    con.execute("INSERT INTO shop.customers (customer_id, name) VALUES (NULL, 'no id')")
    con.execute("INSERT INTO shop.orders (order_id, customer_id) VALUES (9001, NULL), (9002, 1), (9003, 1), (9004, 999999)")
    return con


def test_duplicates_and_nulls_keep_the_distinct_form_and_its_counts():
    con, log = _dirty_shop(), []
    p = plan(seed.schema("shop"))
    out = ev.validate(p, _execute(con, log))
    cust = next(k for k in out["keys"] if k["table"] == "customers")
    assert not cust["verdict"].startswith("unique") and cust["nulls"] == 1
    rel = next(r for r in p.relationships if r.source == "orders" and r.target == "customers")
    ran = next(s for s in log if "AS orphans" in s and "[shop].[orders] AS s" in s and "[customers]" in s)
    assert DISTINCT in ran
    entry = next(x for x in out["relationships"] if x["source"] == "orders" and x["target"] == "customers")
    clean = dict(zip(("with_value", "orphans"), _counts(_execute(gs.shop_database()), "shop", rel, False)))
    assert (entry["rows_with_value"], entry["orphans"]) == (clean["with_value"] + 3, clean["orphans"] + 1)
    # the DISTINCT form is needed here: a direct join would count the duplicated customer twice
    assert _counts(_execute(con), "shop", rel, True) != _counts(_execute(con), "shop", rel, False)


def test_nulls_and_duplicates_on_the_source_side_give_identical_counts():
    con = gs.shop_database()
    con.execute("INSERT INTO shop.orders (order_id, customer_id) VALUES (9001, NULL), (9002, 1), (9003, 1), (9004, 999999)")
    p = plan(seed.schema("shop"))
    out = ev.validate(p, _execute(con))
    assert next(k for k in out["keys"] if k["table"] == "customers")["verdict"].startswith("unique")
    rel = next(r for r in p.relationships if r.source == "orders" and r.target == "customers")
    assert _counts(_execute(con), "shop", rel, True) == _counts(_execute(con), "shop", rel, False)
    entry = next(x for x in out["relationships"] if x["source"] == "orders" and x["target"] == "customers")
    assert entry["orphans"] == 1


# ------------------------------------------------------------------ when each form runs ----------------------------

def test_the_direct_form_runs_only_after_a_unique_verdict_in_the_same_run():
    log = []
    p = plan(seed.schema("shop"))
    out = ev.validate(p, _execute(gs.shop_database(), log))
    unique = {k["table"]: k["columns"] for k in out["keys"] if k["verdict"].startswith("unique")}
    rel_sql = [s for s in log if "AS orphans" in s and "AS several" not in s]
    # n108: the two order_items relationships run in one statement, the others alone
    combined = [r for r in p.relationships if r.source == "order_items"]
    assert len(rel_sql) == len(p.relationships) - len(combined) + 1
    for r in p.relationships:
        direct = sorted(unique.get(r.target, [])) == sorted(r.target_cols)
        own = ev.relationship_sql("shop", r.source, r.source_cols, r.target, r.target_cols, target_unique=direct)
        if r in combined:
            ran = next(s for s in rel_sql if "with_value_1" in s)
            joined = f"[shop].[{r.target}]" if direct else f"(SELECT DISTINCT [{r.target_cols[0]}] FROM [shop].[{r.target}])"
            assert f"LEFT JOIN {joined} AS t" in ran
        else:
            assert own in rel_sql
        assert (DISTINCT not in own) == (r.target in unique)
    # n226: each relationship query ran after its target's key query (check_order), not after every key
    for r in p.relationships:
        if r in combined:
            continue
        own = next(s for s in rel_sql if f"FROM [shop].[{r.source}] AS s" in s and f"[{r.target}]" in s)
        key = next(i for i, s in enumerate(log) if "distinct_keys" in s and s.endswith(f"FROM [shop].[{r.target}]"))
        assert key < log.index(own)


def test_a_verdict_from_another_run_does_not_count():
    """validate starts each run from its own key results: a run whose key check says "not unique" uses DISTINCT,
    whatever an earlier run found."""
    p = plan(seed.schema("shop"))
    ev.validate(p, _execute(gs.shop_database()))
    log = []
    ev.validate(p, _execute(_dirty_shop(), log))
    ran = next(s for s in log if "AS orphans" in s and "[shop].[orders] AS s" in s and "[customers]" in s)
    assert DISTINCT in ran


def _fake(answers, log):
    def execute(sql):
        log.append(sql)
        if "distinct_keys" in sql:
            return [answers.get("key", {"n": 5, "nulls": 0, "distinct_keys": 5})]
        return [{"with_value": 3, "orphans": 0, "several": 0}]
    return execute


UNIQUE = {"table": "t", "columns": ["a", "b"], "rows": 5, "nulls": 0, "distinct": 5, "verdict": "unique in all 5 rows"}


@pytest.mark.parametrize("keys,cols,expect", [
    ([UNIQUE], ["a", "b"], True),
    ([UNIQUE], ["b", "a"], True),                                                     # the same columns in another order
    ([UNIQUE], ["a"], False),                                                         # only part of a composite key
    ([{**UNIQUE, "columns": ["a"]}], ["a", "b"], False),                              # the key is part of the join columns
    ([UNIQUE], ["a", "c"], False),
    ([UNIQUE], ["A", "B"], False),                                                    # another spelling: not the checked key
    ([UNIQUE], ["a", "a"], False),
    ([{**UNIQUE, "table": "u"}], ["a", "b"], False),                                  # another table's key
    ([], ["a", "b"], False),                                                          # not checked
    ([{**UNIQUE, "nulls": 1, "verdict": "not a key: 1 of 5 rows have a NULL in it"}], ["a", "b"], False),
    ([{**UNIQUE, "distinct": 4, "verdict": "not unique: 1 duplicate rows (4 distinct values in 5 rows)"}], ["a", "b"], False),
    ([{**UNIQUE, "rows": 0, "distinct": 0, "verdict": "empty table: nothing to check"}], ["a", "b"], False),
])
def test_target_key_unique_keeps_distinct_in_every_doubtful_case(keys, cols, expect):
    assert ev.target_key_unique(keys, "t", cols) is expect


def test_composite_key_where_only_part_matches_keeps_distinct():
    """order_items has the composite key (order_id, line_no), counted unique; a reference to order_id alone is not a
    reference to that key and keeps DISTINCT."""
    from fabric_backend.infer import Relationship
    p = plan(seed.schema("shop"), keys={"order_items": ["order_id", "line_no"]})
    p.relationships.append(Relationship("orders", ["order_id"], "order_items", ["order_id"], "test"))
    log = []
    out = ev.validate(p, _execute(gs.shop_database(), log))
    assert next(k for k in out["keys"] if k["table"] == "order_items")["verdict"].startswith("unique")
    ran = [s for s in log if "AS orphans" in s and "FROM [shop].[orders] AS s" in s and "[order_items]" in s]
    assert len(ran) == 1 and DISTINCT in ran[0]
    assert any(DISTINCT not in s for s in log if "FROM [shop].[order_items] AS s" in s)    # order_items -> orders: direct


def test_a_key_left_out_by_max_items_keeps_distinct():
    """A key max_items left out was not checked in the run, so it cannot make a relationship direct (validate stops
    the relationships at the same budget; target_key_unique is asked with the keys that did run)."""
    p = plan(seed.schema("shop"))
    log = []
    out = ev.validate(p, _execute(gs.shop_database(), log), max_items=2)
    # n226: check_order takes a link right after its target's key, so two items are one key and one link
    assert len(out["keys"]) == 1 and len(out["relationships"]) == 1
    left_out = [t for t in p.keys if t not in {k["table"] for k in out["keys"]}]
    for r in p.relationships:
        if r.target in left_out:
            assert not ev.target_key_unique(out["keys"], r.target, r.target_cols)


def test_extended_relationships_keep_their_own_query():
    """plan.extended (the SAP example's joins on a non-key column, on a date, or filtered) runs extended_sql, unchanged:
    no direct join, whatever the key verdicts."""
    from fabric_backend.browser_check import _source
    src, _ = _source("sap", None, "")
    p = plan(src.schema)
    assert p.extended
    log = []

    def execute(sql):
        log.append(sql)
        return src.execute(sql)
    ev.validate(p, execute, max_items=200)
    # n226: counted in check_order, so compared without their order
    assert sorted(s for s in log if "AS several" in s) == sorted(ev.extended_sql(p.schema.schema, r) for r in p.extended)


def test_the_sql_the_demo_shows_is_the_sql_that_ran():
    """The demo shows a failing relationship's counting SQL as its evidence: it is the statement validate ran."""
    from fabric_backend import demo_app
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "kunder.csv").write_text("KundNr;Namn\n1;a\n2;b\n3;c\n", encoding="utf-8")
        (Path(d) / "order.csv").write_text("OrderNr;KundNr\n10;1\n11;2\n12;2\n13;9\n", encoding="utf-8")
        src = demo_app.folder_source(Path(d))
        ran = []
        real = src.execute

        def execute(sql, *a, **k):
            ran.append(sql)
            return real(sql, *a, **k)
        src.execute = execute
        st = demo_app.Session(src).state()
        orphan = next(f for f in st["health"]["findings"] if f["id"].startswith("rel:order"))
        assert DISTINCT not in orphan["evidence"]                      # kunder.KundNr was counted unique in this run
        assert orphan["evidence"] in ran
        src.close()


def test_validate_answers_have_the_same_fields_and_counts_as_before():
    """Nothing in the answer changes: the stored golden answer for the shop rows is still the answer."""
    from pathlib import Path
    want = json.loads((Path(__file__).parent / "golden" / "engine_shop_rows.json").read_text(encoding="utf-8"))["validate"]
    got = json.loads(json.dumps(ev.validate(plan(seed.schema("shop")), _execute(gs.shop_database())), sort_keys=True, default=str))
    assert got == want
    # n108 added one entry, the combined statement that ran; the others are the ones n104 recorded
    assert sorted(got) == ["amount_levels", "combined_relationship_queries", "keys", "note", "relationships", "summary"]
