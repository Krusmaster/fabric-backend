"""Round n108: validate counts the relationships of one source table in one statement (combined_relationship_sql), so
the source table is read once instead of once per relationship. The counts must be the ones the separate statements
(relationship_sql, with n104's direct join where it applies) give, in every case; the separate statements still run for
extended relationships, for a relationship whose join columns differ in type, for a source table with one relationship,
and for every relationship of a source table whose combined statement failed.

The reference in every comparison is the same validate run with the combined statement refused: that is the fallback
path, which runs exactly the statements validate ran before n108."""
import json
import random
import sqlite3
from pathlib import Path

import pytest

import golden_support as gs
from fabric_backend import evidence as ev
from fabric_backend import seed
from fabric_backend.dialects import sqlite_sql
from fabric_backend.infer import Relationship, plan
from fabric_backend.schema import Column, Schema, Table

FIXTURES = Path(__file__).parent / "fixtures" / "schemas"
BENCHMARKS = sorted(p.stem for p in FIXTURES.glob("*.json"))


def _execute(con, log=None, refuse_combined=False):
    def execute(sql):
        if log is not None:
            log.append(sql)
        if refuse_combined and "with_value_1" in sql:
            raise RuntimeError("refused by the test")
        cur = con.execute(sqlite_sql(sql))
        return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    return execute


def _wrap(execute, log=None, refuse_combined=False):
    def run(sql):
        if log is not None:
            log.append(sql)
        if refuse_combined and "with_value_1" in sql:
            raise RuntimeError("refused by the test")
        return execute(sql)
    return run


def _combined(log):
    return [s for s in log if "with_value_1" in s]


def _separate(log):
    return [s for s in log if "AS orphans" in s and "AS several" not in s and "with_value_1" not in s]


def _same_counts(p, execute_for, name, require=True):
    """validate with the combined statements and with them refused; the relationship entries must be identical, and at
    least one combined statement must have run (otherwise the comparison says nothing)."""
    log = []
    got = ev.validate(p, execute_for(log, False), max_items=200)
    ref = ev.validate(p, execute_for([], True), max_items=200)
    assert bool(_combined(log)) is require, f"{name}: a source table with two relationships, or none"
    assert all("fell_back" not in c for c in got.get("combined_relationship_queries", [])), name
    assert all("fell_back" in c for c in ref.get("combined_relationship_queries", [])), name
    assert got["relationships"] == ref["relationships"], name
    assert got["keys"] == ref["keys"] and got["summary"] == ref["summary"] and got["amount_levels"] == ref["amount_levels"]
    return got, log


# ------------------------------------------------------------------ the fixtures with rows -------------------------

def _dirty_shop():
    """Duplicated and NULL target keys (customers, products), NULL and dangling references, and a second order_items
    reference to products, so order_items has three relationships, two of them to the same target."""
    con = gs.shop_database()
    con.execute("INSERT INTO shop.customers SELECT * FROM shop.customers WHERE customer_id = 1")
    con.execute("INSERT INTO shop.customers (customer_id, name) VALUES (NULL, 'no id')")
    con.execute("INSERT INTO shop.products SELECT * FROM shop.products WHERE product_id = 2")
    con.execute("INSERT INTO shop.orders (order_id, customer_id) VALUES (9001, NULL), (9002, 1), (9003, 1), (9004, 999999)")
    con.execute("INSERT INTO shop.order_items (order_id, line_no, product_id, quantity) VALUES "
                "(9002, 1, 2, 1), (9002, 2, NULL, 1), (NULL, 3, 2, 1), (777777, 1, 888888, 1)")
    return con


def _shop_plan(**kw):
    p = plan(seed.schema("shop"), **kw)
    return p


@pytest.mark.parametrize("dirty", [False, True], ids=["shop", "shop_dirty"])
def test_shop_rows(dirty):
    con = _dirty_shop() if dirty else gs.shop_database()
    p = _shop_plan()
    # the same target twice: order_items.quantity -> products as a second (wrong, so with orphans) reference
    p.relationships.append(Relationship("order_items", ["line_no"], "products", ["product_id"], "test"))
    got, log = _same_counts(p, lambda log, refuse: _execute(con, log, refuse), "shop")
    assert [c["source"] for c in got["combined_relationship_queries"]] == ["order_items"]
    assert len(got["combined_relationship_queries"][0]["relationships"]) == 3
    if dirty:
        assert any("SELECT DISTINCT" in s for s in _combined(log))         # products is not unique here


def test_composite_keys_on_both_sides():
    """order_items has the composite key (order_id, line_no); a second table refers to it by both columns, and to
    orders and products too, so its combined statement has a composite join next to single ones."""
    con = gs.shop_database()
    con.execute("CREATE TABLE shop.returns (return_id INTEGER, order_id INTEGER, line_no INTEGER, product_id INTEGER)")
    con.executemany("INSERT INTO shop.returns VALUES (?, ?, ?, ?)",
                    [(1, 100, 1, 3), (2, 100, 2, 6), (3, 100, None, 3), (4, None, None, 1), (5, 999, 1, 4), (6, 101, 99, 99)])
    s = seed.schema("shop")
    s.tables["returns"] = (Table("returns", [Column("return_id", "int"), Column("order_id", "int"), Column("line_no", "int"),
                                      Column("product_id", "int")], schema="shop"))
    for duplicated in (False, True):
        if duplicated:                                              # the composite key with a duplicate: DISTINCT again
            con.execute("INSERT INTO shop.order_items SELECT * FROM shop.order_items WHERE order_id = 100 AND line_no = 1")
        p = plan(s, keys={"order_items": ["order_id", "line_no"], "returns": ["return_id"]})
        p.relationships.append(Relationship("returns", ["order_id", "line_no"], "order_items", ["order_id", "line_no"], "test"))
        got, log = _same_counts(p, lambda log, refuse: _execute(con, log, refuse), "composite")
        entry = next(c for c in got["combined_relationship_queries"] if c["source"] == "returns")
        assert "rel:returns.order_id+line_no>order_items" in [r["id"] for r in entry["relationships"]]
        comp = next(r for r in got["relationships"] if r["source"] == "returns" and r["target"] == "order_items")
        assert (comp["rows_with_value"], comp["orphans"]) == (4, 2)
        sql = next(s for s in _combined(log) if "FROM [shop].[returns] AS s" in s)
        assert ("(SELECT DISTINCT [order_id], [line_no] FROM [shop].[order_items])" in sql) is duplicated


@pytest.mark.parametrize("kind", ["sample", "sap", "crm", "billing"])
def test_browser_examples(kind):
    """The browser examples: planted orphans, the SAP pack's blank-as-none joins on a client column, extended joins."""
    from fabric_backend.browser_check import _source
    src, _ = _source(kind, None, "")
    p = plan(src.schema)
    # crm has no source table with two relationships: everything runs alone there, as before
    got, log = _same_counts(p, lambda log, refuse: _wrap(src.execute, log, refuse), kind, require=kind != "crm")
    if kind == "sap":
        assert any("LTRIM(RTRIM(" in s for s in _combined(log))     # a blank-as-none join inside a combined statement
        ext = [s for s in log if "AS several" in s]
        assert ext == [ev.extended_sql(p.schema.schema, r) for r in p.extended]      # extended: own statements, unchanged


def _sap_blank_db():
    """A SAP-shaped pair with blanks, spaces and NULLs in the reference and the client column MANDT in the join, and a
    target with a duplicated key: blank-as-none applies per relationship, inside the combined statement."""
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS sap")
    con.execute("CREATE TABLE sap.KNA1 (MANDT TEXT, KUNNR TEXT, NAME1 TEXT)")
    con.execute("CREATE TABLE sap.VBAK (MANDT TEXT, VBELN TEXT, KUNNR TEXT, KUNWE TEXT)")
    con.executemany("INSERT INTO sap.KNA1 VALUES (?, ?, ?)",
                    [("100", "A", "x"), ("100", "B", "y"), ("100", "B", "y"), ("200", "A", "z"), ("100", "", "blank")])
    con.executemany("INSERT INTO sap.VBAK VALUES (?, ?, ?, ?)",
                    [("100", "1", "A", "B"), ("100", "2", "", "A"), ("100", "3", "  ", None), ("100", "4", None, "C"),
                     ("200", "5", "A", "A"), ("200", "6", "B", " "), ("", "7", "A", "A"), ("100", "8", "B", "")])
    s = Schema({t.name: t for t in [Table("KNA1", [Column("MANDT", "nvarchar"), Column("KUNNR", "nvarchar"), Column("NAME1", "nvarchar")], schema="sap"),
                Table("VBAK", [Column("MANDT", "nvarchar"), Column("VBELN", "nvarchar"), Column("KUNNR", "nvarchar"),
                               Column("KUNWE", "nvarchar")], schema="sap")]}, schema="sap")
    return con, s


def test_blank_as_none_sap_joins_with_a_client_column_and_the_same_target_twice():
    con, s = _sap_blank_db()
    p = plan(s, keys={"KNA1": ["MANDT", "KUNNR"], "VBAK": ["MANDT", "VBELN"]})
    p.relationships[:] = [Relationship("VBAK", ["MANDT", "KUNNR"], "KNA1", ["MANDT", "KUNNR"], "SAP pack"),
                          Relationship("VBAK", ["MANDT", "KUNWE"], "KNA1", ["MANDT", "KUNNR"], "SAP pack"),
                          Relationship("VBAK", ["MANDT", "KUNWE"], "KNA1", ["MANDT", "KUNNR"], "R1")]   # blanks count here
    got, log = _same_counts(p, lambda log, refuse: _execute(con, log, refuse), "sap blanks")
    a, b, c = got["relationships"]
    # KUNNR: blanks are no value, the client column is not blank-checked: (200, B) and ('', A) point at nothing
    assert (a["rows_with_value"], a["orphans"]) == (5, 2)
    # KUNWE with blank-as-none: C and ('', A) point at nothing; ' ' and '' are no value
    assert (b["rows_with_value"], b["orphans"]) == (5, 2)
    # the same columns without it: (200, ' ') is an orphan too, and (100, '') finds KNA1's blank row
    assert (c["rows_with_value"], c["orphans"]) == (7, 3)
    assert len(_combined(log)) == 1 and not _separate(log)


# ------------------------------------------------------------------ every schema fixture, rows from a seed ---------

def _fill(schema: Schema, seed_: int):
    """Rows for every table of a schema fixture: few distinct values, so references both match and miss; NULLs; key
    columns unique in some tables and duplicated in others, so both n104 forms run."""
    rnd = random.Random(seed_)
    con = sqlite3.connect(":memory:")
    con.execute(f"ATTACH DATABASE ':memory:' AS [{schema.schema}]")
    for t in schema:
        cols = [c.name for c in t.columns]
        con.execute(f"CREATE TABLE [{schema.schema}].[{t.name}] ({', '.join('[' + c.replace(']', ']]') + ']' for c in cols)})")
        unique = rnd.random() < 0.6
        rows = []
        for i in range(rnd.randint(0, 14)):
            row = []
            for j, c in enumerate(cols):
                if j == 0 and unique:
                    row.append(i + 1)
                else:
                    row.append(None if rnd.random() < 0.15 else rnd.randint(1, 9))
            rows.append(row)
        if rows:
            con.executemany(f"INSERT INTO [{schema.schema}].[{t.name}] VALUES ({', '.join('?' * len(cols))})", rows)
    return con


def _benchmark_plan(name):
    fx = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    rows = [("dbo", t["name"], c, typ, i) for t in fx["tables"] for i, (c, typ) in enumerate(t["columns"], 1)]
    return plan(Schema.from_information_schema(rows, schema="dbo"))


@pytest.mark.parametrize("name", BENCHMARKS)
@pytest.mark.parametrize("seed_", [1, 2, 3])
def test_every_schema_fixture_with_rows_from_a_seed(name, seed_):
    p = _benchmark_plan(name)
    if not any(n > 1 for n in _sources_with_several(p).values()):
        pytest.skip(f"{name}: no source table with two relationships")
    con = _fill(p.schema, seed_)
    _same_counts(p, lambda log, refuse: _execute(con, log, refuse), name)


def _sources_with_several(p):
    out: dict[str, int] = {}
    for r in p.relationships:
        if ev.combinable(p, r):
            out[r.source] = out.get(r.source, 0) + 1
    return out


# ------------------------------------------------------------------ the statements -----------------------------------

def test_each_join_follows_n104_and_the_combined_statement_reads_the_source_once():
    log = []
    p = _shop_plan()
    out = ev.validate(p, _execute(gs.shop_database(), log))
    sql = _combined(log)
    assert len(sql) == 1 and sql[0].count("FROM [shop].[order_items]") == 1
    entry = out["combined_relationship_queries"][0]
    assert entry["sql"] == sql[0] and entry["source"] == "order_items" and "fell_back" not in entry
    rels = [r for r in p.relationships if r.source == "order_items"]
    want = ev.combined_relationship_sql("shop", "order_items", [
        dict(source_cols=r.source_cols, target=r.target, target_cols=r.target_cols,
             target_unique=ev.target_key_unique(out["keys"], r.target, r.target_cols)) for r in rels])
    assert sql[0] == want
    assert "SELECT DISTINCT" not in sql[0]                          # orders and products were counted unique
    # each relationship's own statement, the one a customer can run alone, is in the answer next to it
    assert [x["id"] for x in entry["relationships"]] == [f"rel:order_items.{r.source_cols[0]}>{r.target}" for r in rels]
    for x, r in zip(entry["relationships"], rels):
        assert x["sql"] == ev.relationship_sql("shop", r.source, r.source_cols, r.target, r.target_cols,
                                               target_unique=ev.target_key_unique(out["keys"], r.target, r.target_cols))
        assert x["sql"] not in log                                  # it did not run: the combined one counted it
    # the relationships with a source table of their own ran alone, as before
    alone = [r for r in p.relationships if r.source != "order_items"]
    assert len(_separate(log)) == len(alone)


def test_query_counts_shop_and_adventureworks():
    """Statements validate runs with every check in budget: shop 13 -> 12 (order_items' two relationships in one),
    AdventureWorks 150 -> 116 (79 relationships from 45 statements: 20 source tables with two to six)."""
    def count(p, execute, combine):
        log = []
        real = ev.combinable
        if not combine:
            ev.combinable = lambda p, r: False
        try:
            ev.validate(p, _wrap(execute, log), max_items=200)
        finally:
            ev.combinable = real
        return len(log), len([s for s in log if "AS orphans" in s and "AS several" not in s])

    db = gs.shop_database()
    shop = _shop_plan()
    assert count(shop, _execute(db), False) == (13, 6)
    assert count(shop, _execute(db), True) == (12, 5)
    aw = _benchmark_plan("adventureworks")
    con = _fill(aw.schema, 1)
    assert len(aw.relationships) == 79 and not aw.extended
    assert count(aw, _execute(con), False) == (150, 79)
    assert count(aw, _execute(con), True) == (116, 45)


def test_a_failing_combined_statement_falls_back_and_says_so():
    log = []
    p = _shop_plan()
    out = ev.validate(p, _execute(gs.shop_database(), log, refuse_combined=True))
    entry = out["combined_relationship_queries"][0]
    assert entry["fell_back"] == ("the combined statement failed (RuntimeError); each relationship of order_items was "
                                  "counted with its own statement instead")
    assert all(x["sql"] in log for x in entry["relationships"])     # the separate statements ran
    clean = ev.validate(p, _execute(gs.shop_database()))
    assert out["relationships"] == clean["relationships"]


def test_an_answer_without_the_numbered_columns_falls_back():
    """A driver that answers the combined statement with other column names: not trusted, the separate ones run."""
    db = gs.shop_database()
    inner = _execute(db)

    def execute(sql):
        return [{"with_value": 1, "orphans": 0}] if "with_value_1" in sql else inner(sql)
    out = ev.validate(_shop_plan(), execute)
    assert "LookupError" in out["combined_relationship_queries"][0]["fell_back"]
    assert out["relationships"] == ev.validate(_shop_plan(), _execute(gs.shop_database()))["relationships"]


def test_max_items_still_counts_relationships():
    """max_items counts relationships, not statements: a group cut by the budget combines only what is in it, and a
    relationship over the budget is not counted, in a combined statement or otherwise."""
    p = _shop_plan()
    order_items = [i for i, r in enumerate(p.relationships) if r.source == "order_items"]
    assert len(order_items) == 2
    budget = len(p.keys) + order_items[1]                           # the second order_items relationship is left out
    log = []
    out = ev.validate(p, _execute(gs.shop_database(), log), max_items=budget)
    assert len(out["relationships"]) == order_items[1]
    assert not _combined(log) and "combined_relationship_queries" not in out
    assert "raise max_items" in out["summary"]
    log = []
    out = ev.validate(p, _execute(gs.shop_database(), log), max_items=len(p.keys) + len(p.relationships))
    assert len(out["relationships"]) == len(p.relationships) and len(_combined(log)) == 1


def test_join_columns_of_another_type_keep_their_own_statement():
    s = seed.schema("shop")
    oi = next(t for t in s if t.name == "order_items")
    oi.columns = [Column(c.name, "bigint" if c.name == "product_id" else c.data_type) for c in oi.columns]
    p = plan(s)
    rel = next(r for r in p.relationships if r.source == "order_items" and r.target == "products")
    assert not ev.combinable(p, rel)
    log = []
    out = ev.validate(p, _execute(gs.shop_database(), log))
    assert not _combined(log) and "combined_relationship_queries" not in out
    assert len(_separate(log)) == len(p.relationships)


def test_verdicts_and_the_summary_form_are_unchanged():
    """The relationship entries and the n101 summary with its n103 next steps are what the separate statements give;
    only the full answer has the added combined_relationship_queries."""
    p = _shop_plan()
    got = ev.validate(p, _execute(gs.shop_database()))
    ref = ev.validate(p, _execute(gs.shop_database(), refuse_combined=True))
    ref.pop("combined_relationship_queries")
    assert set(got) - set(ref) == {"combined_relationship_queries"}
    assert ev.summarize(got, p) == ev.summarize(ref, p)
    assert "combined_relationship_queries" not in json.dumps(ev.summarize(got, p))
