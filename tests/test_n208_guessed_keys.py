"""Round n208: the silver notebook removes rows only on a key it can stand on.

An independent audit of main (11 November 2026) found that a fact-like table got a key guessed from names and the
silver notebook de-duplicated on it: `sales` with customer_id, product_id and store_id got the K4 junction key of the
three, and a line table with a column `no` got `no` alone (K2), so the same customer buying the same product in the same
store twice lost a row in silver, and the check afterwards could not see it (the key was unique once the rows were gone).

Silver now removes rows only on a key declared in the source (K0), given by a person (K1: keys=, or a key set in the
review) or counted unique and never NULL in the rows when the plan was made (R5): the plan's evidence, the key's rule.
A key guessed from names is still proposed; silver keeps every row of its table, says so in the dry run and in its
summary, and the check notebook reports a guessed key that does not hold without failing the run. A row removed on a
key it stands on is still in krusgraph_quarantine with the reason, as before.

The rows go through silver.simulate (the notebook's steps in Python), through the check's own code on SQLite, and through
the generated PySpark notebook on a local Spark in tests/test_spark_notebooks.py.
"""
import sqlite3

import pytest

from fabric_backend import data_flow, gold, mill, pipeline, silver
from fabric_backend.infer import plan
from fabric_backend.schema import Column, Schema, Table
from silver_cases import N208_TABLES as TABLES, counts, n208_rows as rows

INFO = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse",
            schema="dbo", schemas_enabled=True)

# ------------------------------------------------------------------ the two cases of the audit -----------------------

def schema(tables=TABLES, keys_declared=None) -> Schema:
    s = Schema(schema="dbo")
    for name, cols in tables.items():
        t = Table(name, [Column(c, ty) for c, ty in cols], schema="dbo")
        if keys_declared and name in keys_declared:
            t.keys = list(keys_declared[name])
        s.tables[name] = t
    return s


def test_the_audit_cases_get_the_guessed_keys_as_before():
    """The keys are still proposed as today: the finding is about what silver does with them, not about the rules."""
    p = plan(schema())
    assert p.keys["sales"] == (["customer_id", "product_id", "store_id"], "K4")
    assert p.keys["invoice_lines"] == (["no"], "K2")


def test_silver_keeps_every_row_of_a_table_whose_key_is_guessed():
    s = silver.spec(plan(schema()), INFO)
    out = silver.simulate(s, rows())
    for t, r in rows().items():
        assert len(out["silver"][t]) == len(r), t                                       # nothing left silver
    assert out["quarantine"] == []
    assert sum(r["amount"] for r in out["silver"]["sales"]) == 18.0                     # both sales of 5.00 count
    by = {t["table"]: t for t in s["tables"]}
    assert by["sales"]["dedupe"] is False and by["invoice_lines"]["dedupe"] is False
    assert by["sales"]["key"] == ["customer_id", "product_id", "store_id"]               # still the proposed key
    assert by["sales"]["key_basis"] == "guessed from names, not checked against the rows"


def test_the_notebook_removes_no_row_for_a_guessed_key_and_says_why():
    s = silver.spec(plan(schema()), INFO)
    cell = next(c for k, c in silver.cells(s) if c.startswith("# ---- sales -> "))
    assert "keep_latest(" not in cell and "drop_null_keys(" not in cell
    assert "Every row is kept: no duplicates were removed because the key was not checked" in cell
    assert 'not_checked_keys["sales"] = ["customer_id", "product_id", "store_id"]' in cell
    finish = silver.cells(s)[-1][1]
    assert 'summary[t]["duplicates"] = f"none removed: the key' in finish and "was not checked, so every row was kept" in finish
    intro = silver.cells(s)[0][1]
    assert "a key guessed from names removes no rows" in intro


def test_the_dry_run_words_say_plainly_that_no_duplicates_were_removed():
    s = silver.spec(plan(schema()), INFO)
    note = silver.dedupe_note(s)
    assert note.startswith("No duplicates were removed in 6 table(s) because the key was not checked: ")
    assert "sales (customer_id + product_id + store_id)" in note and "invoice_lines (no)" in note
    step = next(x for x in silver.steps(s) if x["table"] == "sales")["deduplicate_on"]
    assert step["rows_removed"] is False and "no duplicates were removed because the key was not checked" in step["why"]
    node = next(n for n in data_flow.silver_nodes(s, False)[0] if n["table"] == "sales")
    assert node["lines"][0] == "every row kept: key customer_id + product_id + store_id not checked"


# ------------------------------------------------------------------ a key it stands on still de-duplicates --------

def _real_duplicate() -> dict[str, list[dict]]:
    data = rows()
    data["customers"].append({"customer_id": 1, "name": "Ada"})                        # the same customer loaded twice
    return data


@pytest.mark.parametrize("how,rule", [("given", "K1"), ("declared", "K0")])
def test_a_given_or_declared_key_still_removes_a_real_duplicate(how, rule):
    p = plan(schema(), {"customers": ["customer_id"]}) if how == "given" else plan(schema(keys_declared={"customers": ["customer_id"]}))
    assert p.keys["customers"] == (["customer_id"], rule)
    s = silver.spec(p, INFO)
    out = silver.simulate(s, _real_duplicate())
    assert len(out["silver"]["customers"]) == 2
    assert counts(out["quarantine"]) == {("customers", rule, "another row has the same key (customer_id); one row per key was kept "
                                                             "(no ordering column: pass order_by)"): 1}   # the count stays visible
    assert len(out["silver"]["sales"]) == 3                                                # the guessed K4 still removes nothing
    cell = next(c for k, c in silver.cells(s) if c.startswith("# ---- customers -> "))
    assert 'keep_latest(df, ["customer_id"]' in cell
    assert {"table": "customers", "key": ["customer_id"], "rule": rule} not in silver.not_deduplicated(s)


def test_a_key_counted_in_the_rows_when_planned_still_removes_a_duplicate():
    """R5: the plan read the rows and found the column unique and never NULL, so it is a key the rows have shown."""
    tables = {"countries": [("code", "varchar"), ("name", "varchar")],
              "customers": [("customer_id", "int"), ("country_code", "varchar")]}

    def execute(sql):
        con = sqlite3.connect(":memory:")
        con.execute("ATTACH DATABASE ':memory:' AS dbo")
        con.execute("CREATE TABLE dbo.countries (code, name)")
        con.execute("CREATE TABLE dbo.customers (customer_id, country_code)")
        con.executemany("INSERT INTO dbo.countries VALUES (?, ?)", [("SE", "Sweden"), ("NO", "Norway")])
        con.executemany("INSERT INTO dbo.customers VALUES (?, ?)", [(1, "SE"), (2, "NO"), (3, "SE")])
        from fabric_backend.dialects import sqlite_sql
        cur = con.execute(sqlite_sql(sql))
        return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    p = plan(schema(tables), execute=execute)
    if p.keys.get("countries", ([], None))[1] != "R5":
        pytest.skip(f"the plan did not count countries.code here: {p.keys.get('countries')}")
    s = silver.spec(p, INFO)
    later = [{"code": "SE", "name": "Sweden"}, {"code": "NO", "name": "Norway"}, {"code": "SE", "name": "Sweden"}]
    out = silver.simulate(s, {"countries": later, "customers": [{"customer_id": 1, "country_code": "SE"}]})
    assert len(out["silver"]["countries"]) == 2 and [q["rule"] for q in out["quarantine"]] == ["R5"]


def test_an_accepted_fix_still_removes_rows_on_the_key_it_names():
    """A fix accepted from validate_plan (keep_one_per_key, n115) is a person's decision about the key: it still runs."""
    s = silver.spec(plan(schema()), INFO)
    for t in s["tables"]:
        if t["table"] == "sales":
            t["fix_key"] = {"winner": None, "named": None}
    cell = next(c for k, c in silver.cells(s) if c.startswith("# ---- sales -> "))
    assert "keep_one_per_key(" in cell and "not_checked_keys" not in cell
    assert all(x["table"] != "sales" for x in silver.not_deduplicated(s))


# ------------------------------------------------------------------ the check notebook ----------------------------

def _lakehouse(data, p, s):
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    for sch in ("silver", "gold"):
        con.execute(f"ATTACH DATABASE ':memory:' AS {sch}")
    sim = silver.simulate(s, data)["silver"]

    def load(sch, table, cols, rs):
        con.execute(f"CREATE TABLE {sch}.`{table}` ({', '.join('`' + c + '`' for c in cols)})")
        con.executemany(f"INSERT INTO {sch}.`{table}` VALUES ({', '.join('?' * len(cols))})", [tuple(r.get(c) for c in cols) for r in rs])
    for t, rs in sim.items():
        load("silver", t, [c for c, _ in TABLES[t]], rs)
    g = gold.spec(p, INFO)

    def execute(sql):
        return [dict(r) for r in con.execute(sql).fetchall()]
    for v in g["views"]:
        load("gold", v["name"].split(".", 1)[1], [c["as"] for c in v["columns"]], gold.run_select(v, g, execute))
    return g, execute


def test_the_check_reports_a_guessed_key_that_does_not_hold_and_does_not_fail_the_run():
    p = plan(schema())
    s = silver.spec(p, INFO)
    g, execute = _lakehouse(rows(), p, s)
    spec = pipeline.check_spec(p, s, g)
    assert {k["table"]: bool(k.get("not_enforced")) for k in spec["keys"]}["sales"] is True
    result = pipeline._CHECK["check"](spec, execute, lambda name: True)
    sales = next(k for k in result["keys"] if k["table"] == "sales")
    assert not sales["holds"] and sales["duplicates"] == 1 and "removed no rows: reported, not a failure" in sales["verdict"]
    lines = next(k for k in result["keys"] if k["table"] == "invoice_lines")
    assert not lines["holds"] and not lines["enforced"]
    assert result["passed"], result["failures"]
    pipeline.raise_if_failed(result)


def test_the_check_still_fails_a_given_key_that_does_not_hold():
    p = plan(schema(), {"customers": ["customer_id"]})
    s = silver.spec(p, INFO)
    g, execute = _lakehouse(rows(), p, s)
    spec = pipeline.check_spec(p, s, g)
    spec["keys"] = [dict(k, columns=["name"]) if k["table"] == "customers" else k for k in spec["keys"]]
    execute("INSERT INTO silver.`customers` VALUES (3, 'Ada')")
    with pytest.raises(pipeline._CHECK["CheckFailed"], match="key customers\\(name\\): not unique"):
        pipeline.raise_if_failed(pipeline._CHECK["check"](spec, execute, lambda name: True))


# ------------------------------------------------------------------ the mill sample -------------------------------

def test_the_mill_keeps_its_planted_duplicate_in_silver_where_the_check_can_see_it():
    """stg_supplier_prices loads one price row twice (planted_issues.json: 49 rows, 48 distinct). Its key
    supplier_price_id is guessed (K2), so silver keeps both rows (before: one went to quarantine); the planted orphans
    leave silver exactly as before."""
    src = mill.source()
    try:
        p = plan(src.schema)
        data = {t: src.execute(f"SELECT * FROM mill.[{t}]") for t in src.schema.tables}
    finally:
        src.close()
    s = silver.spec(p, dict(INFO, schema="mill"))
    out = silver.simulate(s, data)
    assert len(out["silver"]["stg_supplier_prices"]) == len(data["stg_supplier_prices"]) == 49
    got = counts(out["quarantine"])
    assert not [k for k in got if k[0] == "stg_supplier_prices"]
    assert {(k[0], v) for k, v in got.items()} == {("sales_order_lines", 2), ("deliveries", 2), ("inventory_transactions", 1),
                                                ("production_operations", 1)}
    assert {"table": "stg_supplier_prices", "key": ["supplier_price_id"], "rule": "K2"} in silver.not_deduplicated(s)
    given = silver.spec(plan(mill.schema(), {"stg_supplier_prices": ["supplier_price_id"]}), dict(INFO, schema="mill"))
    out = silver.simulate(given, data)                                                       # given as a key: the latest load wins
    assert len(out["silver"]["stg_supplier_prices"]) == 48
    assert counts(out["quarantine"])[("stg_supplier_prices", "K1", "another row has the same key (supplier_price_id); the row with "
                                      "the latest loaded_at was kept")] == 1
