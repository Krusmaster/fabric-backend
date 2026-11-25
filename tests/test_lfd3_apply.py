"""Round LFD3 (25 November 2026): the change list applied to the drafts (changes.apply, silver.apply_changes,
gold.apply_changes, semantic_model.draft(changes=...), docs/CHANGES.md).

An empty list gives every draft byte for byte as without one; filter_rows on shop_lfd gives LFD1's numbers without the
test customers in silver.simulate and leaves the source rows as they were; add_column's gold view runs in SQLite with one
row per order; add_measure is DAX built from the contract; scenario A's three changes give the same drafts and ids every
time. No network, no model: SQLite over the synthetic samples of fabric_backend/lfd_demo.py."""
from __future__ import annotations

import ast
import copy
import sqlite3
from decimal import Decimal

import pytest

from fabric_backend import changes, gold, lfd_demo, notebook, semantic_model, server, silver
from fabric_backend.infer import plan as make_plan

INFO = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse",
            schema="shop", schemas_enabled=True)
IS_TEST = {"column": "is_test", "op": "is_true"}
C1 = {"type": "filter_rows", "table": "customers", "drop_where": IS_TEST, "cascade": ["orders", "order_items", "addresses", "audit_log"]}
SHIP_TO = {"from": {"table": "orders", "columns": ["ship_to_id"]}, "to": {"table": "addresses", "columns": ["address_id"]}}
C2 = {"type": "add_column", "table": "orders", "from": "addresses", "columns": ["region"], "via": [SHIP_TO]}
C3 = {"type": "add_measure", "name": "Order value per customer",
      "measure": {"form": "ratio", "numerator": {"measure": "Order amount"},
                  "denominator": {"form": "distinct_count", "table": "orders", "column": "customer_id"}}}
SCENARIO_A = [C1, C2, C3]
ORDER_VALUE_DAX = "DIVIDE([Order amount], DISTINCTCOUNT('orders'[customer_id]))"


@pytest.fixture(scope="module")
def shop():
    schema, execute = lfd_demo.sqlite("shop_lfd")
    p = server._hosted_plan(schema, None, None, execute)            # the plan as plan_backend makes it (names, R5)
    data = {t.name: execute(f"SELECT * FROM [shop].[{t.name}]") for t in p.schema}
    return p, data


def drafts(p, applied=None, dimensions=False):
    """Every draft of the plan, as text: the silver spec and notebook, the gold spec and notebook, the TMDL parts on the
    source and on gold."""
    kw = {"changes": applied} if applied is not None else {}
    s = silver.spec(p, INFO, **kw)
    g = gold.spec(p, INFO, dimensions=dimensions, **kw)
    model = semantic_model.draft(p, INFO, **kw)
    on_gold = semantic_model.draft_on_gold(p, INFO, gold.spec(p, INFO, dimensions=True, **kw), **kw)
    return {"silver_spec": repr(s), "silver_notebook": silver.notebook_source(s), "gold_spec": repr(g),
            "gold_notebook": gold.notebook_source(g), "tmdl": model["parts"], "tmdl_on_gold": on_gold["parts"]}


def steps_only(notebook_text: str) -> str:
    """LFD7: the silver notebook without the change list its parameters cell carries (CHANGE_LIST and its comment)."""
    drop = (*silver.CHANGE_LIST_COMMENT.splitlines(), "CHANGE_LIST = ")
    return "\n".join(x for x in notebook_text.split("\n") if not x.startswith(drop))


def silver_db(sim: dict, p) -> callable:
    """SQLite with silver.simulate's tables in an attached `silver` schema, columns in the plan's order."""
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS silver")
    for t, rows in sim.items():
        cols = p.schema[t].column_names
        con.execute(f"CREATE TABLE silver.`{t}` ({', '.join('`' + c + '`' for c in cols)})")
        con.executemany(f"INSERT INTO silver.`{t}` VALUES ({', '.join('?' * len(cols))})", [tuple(r.get(c) for c in cols) for r in rows])
    con.row_factory = sqlite3.Row
    return lambda sql: [dict(r) for r in con.execute(sql).fetchall()]


# ------------------------------------------------------------------ an empty list changes nothing ------------------

@pytest.mark.parametrize("which", ["shop_lfd", "sap_lfd", "shop_names_only"])
def test_an_empty_list_gives_every_draft_byte_for_byte(which):
    if which == "shop_names_only":
        p = make_plan(lfd_demo.sqlite("shop_lfd")[0])
    else:
        schema, execute = lfd_demo.sqlite(which)
        p = server._hosted_plan(schema, None, None, execute)
    empty = changes.apply([], p)
    assert empty == {"result": "ok", "plan": changes.plan_mark(p), "changes": [], "reverted": [], "confirmed": []}
    for dims in (False, True):
        assert drafts(p, empty, dims) == drafts(p, None, dims)
    s, g = silver.spec(p, INFO), gold.spec(p, INFO)
    assert silver.apply_changes(s, empty) is s and gold.apply_changes(g, empty) is g
    assert silver.apply_changes(s, None) is s and gold.apply_changes(g, None) is g


def test_an_empty_list_gives_the_same_simulation(shop):
    p, data = shop
    assert silver.simulate(silver.spec(p, INFO, changes=changes.apply([], p)), data) == silver.simulate(silver.spec(p, INFO), data)


def test_a_list_without_a_change_of_a_drafts_type_leaves_that_draft_as_it_is(shop):
    p, _ = shop
    only_measure = changes.apply([C3], p)
    assert steps_only(drafts(p, only_measure)["silver_notebook"]) == drafts(p)["silver_notebook"]   # LFD7: the list only
    assert drafts(p, only_measure)["gold_notebook"] == drafts(p)["gold_notebook"]
    only_filter = changes.apply([C1], p)
    assert drafts(p, only_filter)["gold_notebook"] == drafts(p)["gold_notebook"]
    assert drafts(p, only_filter)["tmdl"] != drafts(p)["tmdl"]                 # the README says where the filter is drafted
    assert all(v == drafts(p)["tmdl"][k] for k, v in drafts(p, only_filter)["tmdl"].items() if k != "README.generated.md")


# ------------------------------------------------------------------ filter_rows in silver --------------------------

def test_filter_rows_with_cascade_gives_lfd1s_numbers_in_silver_and_leaves_the_source_alone(shop):
    p, data = shop
    before = copy.deepcopy(data)
    s = silver.spec(p, INFO, changes=changes.apply([C1], p))
    sim = silver.simulate(s, data)
    want = lfd_demo.EXPECTED["shop_lfd"]["numbers"]
    got = {t: len(sim["silver"][t]) for t in ("customers", "addresses", "orders", "order_items")}
    assert got == {"customers": want["real_customers"], "addresses": want["real_addresses"], "orders": want["real_orders"],
                   "order_items": want["real_order_lines"]} == {"customers": 10, "addresses": 17, "orders": 60, "order_items": 134}
    assert not [r for r in sim["silver"]["customers"] if r["is_test"]]
    assert data == before                                                     # the source rows are never changed
    cid = changes.apply([C1], p)["changes"][0]["id"]
    left = {}
    for q in sim["quarantine"]:
        left[(q["source_table"], q["rule"])] = left.get((q["source_table"], q["rule"]), 0) + 1
    assert left == {("customers", cid): 2, ("addresses", cid): 2, ("orders", cid): 6, ("order_items", cid): 12}
    # the order value over what silver holds is LFD1's, 51 296.70
    price = {r["product_id"]: Decimal(str(r["list_price"])) for r in sim["silver"]["products"]}
    value = sum(Decimal(str(i["quantity"])) * price[i["product_id"]] for i in sim["silver"]["order_items"])
    assert f"{value:.2f}" == want["real_order_value"] == "51296.70"


def test_filter_rows_is_a_step_of_the_notebook_that_reads_the_source_and_writes_only_silver(shop):
    p, _ = shop
    applied = changes.apply([C1], p)
    cid = applied["changes"][0]["id"]
    s = silver.spec(p, INFO, changes=applied)
    by = {t["table"]: t for t in s["tables"]}
    assert by["customers"]["change_filters"] == [{"id": cid, "drop_where": IS_TEST, "said": "is_test is true"}]
    assert [x["parent"] for c in by["orders"]["change_cascade"] for x in c["through"]] == ["customers", "addresses"]
    assert s["changes"] == [{"id": cid, "table": "customers", "drop_where": IS_TEST, "said": "is_test is true",
                             "cascade": ["addresses", "audit_log", "order_items", "orders"]}]
    assert silver.written_tables(s) == silver.written_tables(silver.spec(p, INFO))              # no new target
    assert not set(silver.written_tables(s)) & set(silver.source_tables(s))
    text = silver.notebook_source(s)
    for kind, code in notebook.parse(text):
        if kind != "markdown":
            ast.parse(code)
    cell = next(code for kind, code in silver.cells(s) if "---- customers ->" in code)
    assert (f'df = exclude_rows(df, F.coalesce(col("is_test").cast("boolean"), F.lit(False)), "customers", "{cid}", '
            f'"change {cid} (filter_rows): is_test is true")') in cell
    assert cell.index("exclude_rows") < cell.index("drop_null_keys") if "drop_null_keys" in cell else True
    assert "## Changes (drafts to review)" in text and "the source tables are never written" in text
    assert "DELETE" not in text and ".mode(\"overwrite\")" in text and "saveAsTable(source(" not in text


def test_a_table_outside_the_cascade_keeps_its_rows(shop):
    p, data = shop
    applied = changes.apply([{**C1, "cascade": ["orders", "order_items"]}], p)
    s = silver.spec(p, INFO, changes=applied)
    sim = silver.simulate(s, data)
    assert {t: len(sim["silver"][t]) for t in ("customers", "addresses", "orders", "order_items")} == \
        {"customers": 10, "addresses": 19, "orders": 60, "order_items": 134}
    assert not [q for q in sim["quarantine"] if q["source_table"] == "addresses"]       # not quarantined as orphans
    check = next(c for t in s["tables"] if t["table"] == "addresses" for c in t["checks"])
    assert check["also_excluded_by"] == [applied["changes"][0]["id"]]
    assert "with_excluded(silver[\"customers\"], \"customers\"" in silver.notebook_source(s)


def test_a_null_never_matches_and_equals_compares_values():
    assert changes.holds(IS_TEST, {"is_test": 1}) and changes.holds(IS_TEST, {"is_test": True})
    assert not changes.holds(IS_TEST, {"is_test": 0}) and not changes.holds(IS_TEST, {"is_test": None})
    eq = {"column": "country", "op": "equals", "value": "SE"}
    assert changes.holds(eq, {"country": "SE"}) and not changes.holds(eq, {"country": None})
    assert not changes.holds({"column": "n", "op": "equals", "value": 1}, {"n": "1"})
    both = {"any": [eq, {"column": "note", "op": "is_not_empty"}]}
    assert changes.holds(both, {"country": "DE", "note": "x"}) and not changes.holds(both, {"country": "DE", "note": "  "})
    assert silver.spark_condition(both) == ('F.coalesce(((col("country") == F.lit("SE")) | (col("note").isNotNull() & '
                                            '(F.trim(col("note").cast("string")) != ""))), F.lit(False))')
    assert silver.spark_condition({"column": "is_test", "op": "equals", "value": True}) == \
        'F.coalesce((col("is_test") == F.lit(True)), F.lit(False))'


# ------------------------------------------------------------------ add_column in gold -----------------------------

def test_add_column_region_runs_in_sqlite_with_one_row_per_order(shop):
    p, data = shop
    applied = changes.apply([C1, C2], p)
    cid = applied["changes"][1]["id"]
    sim = silver.simulate(silver.spec(p, INFO, changes=applied), data)["silver"]
    g = gold.spec(p, INFO, changes=applied)
    view = next(v for v in g["views"] if v["fact"] == "orders")
    region = next(c for c in view["columns"] if c["as"] == "addresses_region")
    assert region["changes"] == [cid] and region["table"] == "addresses"
    assert g["changes"] == [{"id": cid, "table": "orders", "from": "addresses", "columns": ["region"], "path": ["orders", "addresses"],
                             "views": [{"view": "gold.orders", "added": [], "already_in_view": ["addresses_region"]}]}]
    rows = gold.run_select(view, g, silver_db(sim, p))
    assert len(rows) == 60 and len({r["order_id"] for r in rows}) == 60          # no row repeated
    assert "addresses_region" in rows[0] and {r["addresses_region"] for r in rows} == {"North", "South"}
    assert f"-- addresses_region: addresses.region, added by change {cid} (add_column)" in gold.create_sql(view, g)


def test_add_column_over_a_join_the_view_does_not_have_adds_a_left_join(shop):
    p, data = shop
    applied = changes.apply([C1, {"type": "add_column", "table": "addresses", "from": "customers", "columns": ["country"]}], p)
    cid = applied["changes"][1]["id"]
    sim = silver.simulate(silver.spec(p, INFO, changes=applied), data)["silver"]
    g = gold.spec(p, INFO, dimensions=True, changes=applied)
    view = next(v for v in gold.all_views(g) if v["fact"] == "addresses")
    assert view["joins"] == [{"from": "addresses", "to": "customers", "on": ["customer_id = customer_id"], "rule": "R1", "certainty": None,
                              "alias": "c1", "from_alias": "f", "source_cols": ["customer_id"], "target_cols": ["customer_id"], "change": cid}]
    assert view["filters"] == [] and view["tables"] == ["addresses", "customers"]
    sql = gold.select_sql(view, g["silver_schema"])
    assert sql.endswith("c1.`country` AS `customers_country`\nFROM `silver`.`addresses` AS f\n"
                        "    LEFT JOIN `silver`.`customers` AS c1 ON f.`customer_id` = c1.`customer_id`")
    rows = gold.run_select(view, g, silver_db(sim, p))
    assert len(rows) == 17 and len({r["address_id"] for r in rows}) == 17 and all(r["customers_country"] for r in rows)
    assert "customers" in gold.notebook_source(g).split("SILVER_TABLES = ")[1].split("\n")[0]
    # the semantic model on gold carries the column
    on_gold = semantic_model.draft_on_gold(p, INFO, g, changes=applied)
    assert "column customers_country" in on_gold["parts"]["definition/tables/addresses.tmdl"]


def test_a_second_path_to_the_same_table_is_a_new_join_and_its_name_says_the_link():
    from fabric_backend.schema import Column
    schema = lfd_demo.sqlite("shop_lfd")[0]
    schema["orders"].columns.append(Column("bill_to_id", "int"))
    p = make_plan(schema, confirmed=[{"source": "orders", "source_cols": [c], "target": "addresses", "target_cols": ["address_id"]}
                                     for c in ("ship_to_id", "bill_to_id")])
    g = gold.spec(p, INFO)
    view = next(v for v in g["views"] if v["fact"] == "orders")
    assert [(j["to"], j["source_cols"]) for j in view["joins"]] == [("addresses", ["bill_to_id"]), ("customers", ["customer_id"])]
    applied = changes.apply([C2], p)                                          # region over ship_to_id, which the view does not join
    out = gold.apply_changes(g, applied)
    changed = next(v for v in out["views"] if v["fact"] == "orders")
    assert changed["joins"][-1]["source_cols"] == ["ship_to_id"] and changed["joins"][-1]["alias"] == "c1"
    assert [c["as"] for c in changed["columns"]][-1] == "addresses_region_via_ship_to_id"
    assert "c1.`region` AS `addresses_region_via_ship_to_id`" in gold.select_sql(changed, out["silver_schema"])
    assert view is not changed and len(view["joins"]) == 2                    # a new dict; the spec given is unchanged


# ------------------------------------------------------------------ add_measure in the semantic model ---------------

def test_order_value_per_customer_is_deterministic_dax_in_the_tmdl(shop):
    p, _ = shop
    applied = changes.apply([C3], p)
    cid = applied["changes"][0]["id"]
    model = semantic_model.draft(p, INFO, changes=applied)
    tmdl = model["parts"]["definition/tables/orders.tmdl"]
    assert (f"\t/// Added by change {cid} (add_measure): the measure Order amount divided by the number of distinct values of "
            f"orders.customer_id (ratio, from the change contract).\n\tmeasure 'Order value per customer' = {ORDER_VALUE_DAX}\n"
            "\t\tformatString: #,##0.00\n") in tmdl
    assert model["summary"]["changes"] == [{"id": cid, "type": "add_measure", "name": "Order value per customer", "table": "orders",
                                            "expression": ORDER_VALUE_DAX,
                                            "said": f"the measure 'Order value per customer' on orders = {ORDER_VALUE_DAX}"}]
    assert "[Order amount]" in ORDER_VALUE_DAX and "measure 'Order amount' = SUMX(" in model["parts"]["definition/tables/order_items.tmdl"]
    assert semantic_model.draft(p, INFO, changes=changes.apply([C3], p))["parts"] == model["parts"]


def test_every_form_is_dax_from_the_contract(shop):
    p, _ = shop
    forms = [
        ("Customers counted", {"form": "count", "table": "customers"}, "COUNTROWS('customers')", "#,0"),
        ("Buyers", {"form": "distinct_count", "table": "orders", "column": "customer_id"}, "DISTINCTCOUNT('orders'[customer_id])", "#,0"),
        ("Quantity sold", {"form": "sum", "table": "order_items", "column": "quantity"}, "SUM('order_items'[quantity])", "#,##0.00"),
        ("Lines per order", {"form": "ratio", "numerator": {"form": "count", "table": "order_items"},
                             "denominator": {"form": "count", "table": "orders"}}, "DIVIDE(COUNTROWS('order_items'), COUNTROWS('orders'))", "#,##0.00"),
        ("Quantity per buyer", {"form": "ratio", "numerator": {"measure": "quantity sold"}, "denominator": {"measure": "Buyers"}},
         "DIVIDE([Quantity sold], [Buyers])", "#,##0.00"),
    ]
    applied = changes.apply([{"type": "add_measure", "name": n, "measure": m} for n, m, _, _ in forms], p)
    assert applied["result"] == "ok", applied
    got = {x["name"]: x for x in semantic_model.draft(p, INFO, changes=applied)["summary"]["changes"]}
    for name, _, dax, fmt in forms:
        assert got[name]["expression"] == dax, name
    model = semantic_model.draft(p, INFO, changes=applied)["parts"]
    assert "measure 'Quantity per buyer' = DIVIDE([Quantity sold], [Buyers])\n\t\tformatString: #,##0.00" in model["definition/tables/order_items.tmdl"]
    assert "measure Buyers = DISTINCTCOUNT('orders'[customer_id])\n\t\tformatString: #,0" in model["definition/tables/orders.tmdl"]


def test_a_measure_the_model_cannot_hold_is_said_not_added(shop):
    p, _ = shop
    applied = changes.apply([C3], p)
    model = semantic_model.draft(p, INFO, tables=["customers", "orders"], changes=applied)
    assert model["summary"]["changes"][0]["not_added"] == "this model has no measure Order amount"
    assert "Order value per customer" not in model["parts"]["definition/tables/orders.tmdl"]


# ------------------------------------------------------------------ scenario A -------------------------------------

def test_scenario_a_gives_the_expected_drafts_with_deterministic_ids_and_order(shop):
    p, data = shop
    a = changes.apply(SCENARIO_A, p)
    assert a["result"] == "ok" and [x["type"] for x in a["changes"]] == ["filter_rows", "add_column", "add_measure"]
    ids = [x["id"] for x in a["changes"]]
    assert ids == [changes.validate(c, p)["id"] for c in SCENARIO_A] and len(set(ids)) == 3
    assert all(x["position"] == i for i, x in enumerate(a["changes"]))
    assert changes.apply(SCENARIO_A, p) == a                                   # the same list, the same answer
    assert changes.apply([*SCENARIO_A, C1], p) == a                            # the same change twice is one change
    assert changes.apply([changes.validate(c, p) for c in SCENARIO_A], p) == a  # ok answers are entries too
    flipped = changes.apply(list(reversed(SCENARIO_A)), p)
    assert [x["id"] for x in flipped["changes"]] == list(reversed(ids))        # the list's order, as given
    once, twice = drafts(p, a, True), drafts(p, changes.apply(SCENARIO_A, p), True)
    assert once == twice
    # the drafts: silver leaves the test customers out, gold carries the region, the model has the measure
    sim = silver.simulate(silver.spec(p, INFO, changes=a), data)["silver"]
    assert [len(sim[t]) for t in ("customers", "orders", "order_items")] == [10, 60, 134]
    g = gold.spec(p, INFO, changes=a)
    assert [(v["fact"], c["as"], c["changes"]) for v in g["views"] for c in v["columns"] if c.get("changes")] == \
        [("orders", "addresses_region", [ids[1]])]
    assert f"measure 'Order value per customer' = {ORDER_VALUE_DAX}" in once["tmdl"]["definition/tables/orders.tmdl"]
    assert f"measure 'Order value per customer' = {ORDER_VALUE_DAX}" in once["tmdl_on_gold"]["definition/tables/orders.tmdl"]
    readme = once["tmdl"]["README.generated.md"].split("## Changes")[1]
    assert [line.split("`")[1] for line in readme.splitlines() if line.startswith("- `chg-")] == ids
    assert "this model reads the source tables, where the rows stay" in readme
    assert "this model reads gold, so they are not in it" in once["tmdl_on_gold"]["README.generated.md"]
    # what the measure gives over silver: 51 296.70 over 10 customers, LFD1's 5 129.67
    price = {r["product_id"]: Decimal(str(r["list_price"])) for r in sim["products"]}
    value = sum(Decimal(str(i["quantity"])) * price[i["product_id"]] for i in sim["order_items"])
    per = (value / len({o["customer_id"] for o in sim["orders"]})).quantize(Decimal("0.01"))
    assert str(per) == lfd_demo.EXPECTED["shop_lfd"]["numbers"]["real_order_value_per_customer"] == "5129.67"


def test_revert_takes_a_change_out_of_the_list(shop):
    p, _ = shop
    ids = [x["id"] for x in changes.apply(SCENARIO_A, p)["changes"]]
    a = changes.apply([*SCENARIO_A, {"type": "revert", "change": ids[0]}], p)
    assert [x["id"] for x in a["changes"]] == ids[1:] and a["reverted"] == [ids[0]]
    assert steps_only(drafts(p, a)["silver_notebook"]) == drafts(p)["silver_notebook"]           # LFD7: the list only
    denied = changes.apply([C3, {"type": "revert", "change": ids[0]}], p)
    assert denied["result"] == "denied" and denied["kind"] == "unknown_change" and denied["at"] == 1


# ------------------------------------------------------------------ add_link, the plan made again ------------------

def test_add_link_asks_for_a_new_plan_and_the_same_list_applies_to_it():
    schema = lfd_demo.sqlite("shop_lfd")[0]
    p0 = make_plan(schema)                                                     # names only: no ship_to link
    link = {"type": "add_link", **SHIP_TO}
    first = changes.validate(link, p0)
    region = {"type": "add_column", "table": "orders", "from": "addresses", "columns": ["region"]}
    listed = [{**C1, "base": changes.plan_mark(p0)}, {**link, "base": changes.plan_mark(p0)}, region]
    again = changes.apply(listed, p0)
    want = {"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}
    assert again["result"] == "replan" and again["confirmed"] == [want] == [first["resolved"]["confirmed"]]
    p1 = make_plan(schema, confirmed=again["confirmed"])                       # plan_backend with confirmed
    assert changes.plan_mark(p1)["plan_id"] != changes.plan_mark(p0)["plan_id"]
    a = changes.apply(listed, p1)
    assert a["result"] == "ok", a
    assert [x["type"] for x in a["changes"]] == ["filter_rows", "add_link", "add_column"] and a["confirmed"] == [want]
    assert a["changes"][1]["resolved"]["in_plan"]["rule"] == "confirmed"
    assert all(x["change"]["base"] == changes.plan_mark(p1) for x in a["changes"])
    assert a["changes"][2]["change"]["via"] == [SHIP_TO]
    # the re-planned silver notebook checks the link, and gold joins over it
    s = silver.spec(p1, INFO, changes=a)
    assert any(c["columns"] == ["ship_to_id"] and c["rule"] == "confirmed" for t in s["tables"] for c in t["checks"])
    assert changes.apply(listed, p1) == a


def test_a_change_written_against_other_tables_is_stale_and_nothing_applies(shop):
    p, _ = shop
    other = make_plan(lfd_demo.sqlite("sap_lfd")[0])
    got = changes.apply([C3, {**C1, "base": changes.plan_mark(other)}], p)
    assert got["result"] == "denied" and got["kind"] == "stale_base" and got["at"] == 1


def test_a_question_or_a_denial_stops_the_list(shop):
    p, _ = shop
    asked = changes.apply([C3, {"type": "filter_rows", "table": "customers"}], p)
    assert asked["result"] == "question" and asked["kind"] == "filter_column" and asked["at"] == 1
    denied = changes.apply([{"type": "add_measure", "name": "x", "measure": "SUM(1)"}], p)
    assert denied["result"] == "denied" and denied["kind"] == "free_text" and denied["at"] == 0
    assert changes.apply("not a list", p)["result"] == "denied"
    with pytest.raises(changes.ChangeError):
        silver.spec(p, INFO, changes=asked)


def test_no_tool_is_added():
    import asyncio
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert not {n for n in names if "change" in n}
