"""Q1: a Qlik load script into Krusgraph's plan (fabric_backend/qlik/, docs/QLIK-MIGRATION-PRODUCT.md).

Synthetic only: the script is tests/fixtures/q1/sales.qvs, written by hand, and the rows behind it are written here.
Nothing was exported from Qlik, and no rule about Qlik has been read on Qlik's own pages (Unverified, as the package says).
"""
import re
import sqlite3
from pathlib import Path

import pytest

from fabric_backend import evidence, migration_read, qlik, semantic_model
from fabric_backend.platforms.local import _sqlite_execute
from fabric_backend.qlik import model, script

ROOT = Path(__file__).resolve().parent.parent
Q1 = ROOT / "tests" / "fixtures" / "q1"

# The landed tables, as the mapping names them. Planted on purpose: one order of a customer that is not there (C9), one
# shipment of an order that is not there (O7), three shipments whose Status differs from their order's, two returns of
# one order line and one return of a line that is not there, a budget and sales at different grains.
ROWS = {
    "Customers": [("C1", "Alfa", "SE", "Retail"), ("C2", "Beta", "SE", "Retail"), ("C3", "Gamma", "NO", "Trade"), ("C4", "Delta", "DK", "Trade")],
    "Products": [("P1", "Hammer", 10), ("P2", "Saw", 20), ("P3", "Drill", 90)],
    "Stores": [("S1", "North", "SE", "Nordics"), ("S2", "West", "NO", "Nordics"), ("S3", "South", "SE", "Nordics")],
    "Orders": [("O1", "C1", "S1", "2026-09-01", "open"), ("O2", "C1", "S1", "2026-09-02", "closed"), ("O3", "C2", "S2", "2026-09-03", "open"),
               ("O4", "C3", "S2", "2026-09-04", "closed"), ("O5", "C4", "S3", "2026-09-05", "open"), ("O6", "C9", "S3", "2026-09-06", "open")],
    "Shipments": [("SH1", "O1", "shipped", "2026-09-02"), ("SH2", "O1", "shipped", "2026-09-03"), ("SH3", "O2", "closed", "2026-09-03"),
                  ("SH4", "O3", "shipped", "2026-09-04"), ("SH5", "O7", "shipped", "2026-09-05")],
    "OrderLines": [("O1", 1, "P1", 2, 10, 20), ("O1", 2, "P2", 1, 20, 20), ("O2", 1, "P1", 1, 10, 10), ("O3", 1, "P3", 1, 90, 90),
                   ("O4", 1, "P2", 2, 20, 40), ("O5", 1, "P1", 3, 10, 30), ("O6", 1, "P1", 1, 10, 10)],
    "Returns": [("R1", "O1", 1, 1), ("R2", "O1", 1, 1), ("R3", "O2", 1, 1), ("R4", "O3", 2, 1)],
    "Budget": [("S1", "2026-09", "CC1", 100), ("S1", "2026-09", "CC2", 50), ("S2", "2026-09", "CC1", 70), ("S1", "2026-10", "CC1", 100)],
    "StoreSales": [("S1", "2026-09", "web", 10), ("S1", "2026-09", "shop", 20), ("S2", "2026-09", "shop", 5)],
}


@pytest.fixture(scope="module")
def read():
    return qlik.read_script((Q1 / "sales.qvs").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def execute(read):
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute("ATTACH DATABASE ':memory:' AS landed")
    for t in read["tables"]:
        cols = [c["column"] for c in t["columns"]]
        con.execute(f"CREATE TABLE landed.[{t['table']}] ({', '.join('[' + c + ']' for c in cols)})")
        con.executemany(f"INSERT INTO landed.[{t['table']}] VALUES ({','.join('?' * len(cols))})", ROWS[t["name"]])
    yield _sqlite_execute(con)
    con.close()


@pytest.fixture(scope="module")
def counted(read, execute):
    return qlik.map_associations(read, execute, schema="landed")


def _table(read, name):
    return next(t for t in read["tables"] if t["name"] == name)


def _syn(mapping, a, b):
    return next(s for s in mapping["synthetic_keys"] if s["tables"] == [a, b])


# ------------------------------------------------------------------ the script ---------------------------------------

def test_the_tables_and_their_lakehouse_columns(read):
    assert {t["name"]: [c["column"] for c in t["columns"]] for t in read["tables"]} == {
        "Customers": ["CustomerID", "Customers_Name", "Country", "Segment"],
        "Products": ["ProductID", "Products_Name", "ListPrice"],
        "Stores": ["StoreID", "StoreName", "Country", "Region"],
        "Orders": ["OrderID", "CustomerID", "StoreID", "Order_Date", "Status"],
        "Shipments": ["ShipmentID", "OrderID", "Status", "ShippedOn"],
        "OrderLines": ["OrderID", "LineNo", "ProductID", "Quantity", "UnitPrice", "LineAmount"],
        "Returns": ["ReturnID", "OrderID", "LineNo", "ReturnedQuantity"],
        "Budget": ["StoreID", "Month", "CostCentre", "BudgetAmount"],
        "StoreSales": ["StoreID", "Month", "Channel", "SalesAmount"],
    }
    assert [t["name"] for t in read["tables"] if t["as_loaded"]] == ["Products", "Shipments", "Returns", "Budget"]


def test_load_sql_select_and_a_preceding_load_are_traced_to_the_source_column(read):
    orders = {c["field"]: c for c in _table(read, "Orders")["columns"]}
    assert orders["OrderID"]["from"] == "order_id" and orders["OrderID"]["source"] == "sql shop.orders"
    assert orders["Order Date"]["column"] == "Order_Date" and orders["Order Date"]["from"] == "order_date"
    assert [(s["how"], s["kind"]) for s in _table(read, "Orders")["sources"]] == [("load", "sql"), ("concatenate", "file")]
    assert any("2 loads appended" in s for s in _table(read, "Orders")["steps"])
    assert any("WHERE" in s for s in _table(read, "Orders")["steps"])


def test_resident_and_join_are_read_through_a_dropped_table(read):
    lines = _table(read, "OrderLines")
    cols = {c["field"]: c for c in lines["columns"]}
    assert cols["Quantity"]["from"] == "quantity" and cols["Quantity"]["source"] == "file lib://Shop/order_items.qvd"
    assert cols["UnitPrice"]["from"] == "ListPrice" and cols["UnitPrice"]["source"] == "resident Products"
    assert cols["UnitPrice"]["via"].startswith("join into OrderItems")
    assert cols["LineAmount"]["expression"] == "Quantity * UnitPrice"
    assert lines["sources"][0]["dropped_table_loaded_from"] == "file lib://Shop/order_items.qvd"
    assert lines["steps"][0].startswith("left join of resident Products into OrderItems")
    assert {"table": "OrderItems", "line": 65} in read["dropped"]


def test_mapping_tables_stay_out_of_the_model_and_applymap_says_how_to_rebuild_it(read):
    assert [m["name"] for m in read["mapping_tables"]] == ["RegionMap", "SegmentMap"]
    assert not {"RegionMap", "SegmentMap"} & {t["name"] for t in read["tables"]}
    uses = {u["field"]: u for u in read["mapping_uses"]}
    assert uses["Region"]["map"] == "RegionMap" and uses["Region"]["key"] == "country" and uses["Region"]["default"] == "'Other'"
    assert "the default 'Other'" in uses["Region"]["rebuild"]
    assert uses["Segment"]["default"] is None and "the looked-up value itself" in uses["Segment"]["rebuild"]
    assert uses["Segment"]["mapping_table"]["fields"] == ["segment_code", "segment_name"]
    assert all("a join repeats the row" in u["rebuild"] for u in uses.values())
    assert script._apply_map("Upper(ApplyMap('M', a & '|' & b, Left(c, 2)))") == {
        "map": "M", "key": "a & '|' & b", "default": "Left(c, 2)", "whole_expression": False}
    missing = qlik.read_script("T:\nLOAD a, ApplyMap('Nowhere', b) AS c FROM [lib://X/t.qvd] (qvd);")
    assert missing["mapping_uses"][0]["mapping_table"] == "not found in the script"


def test_qualify_takes_a_field_out_of_the_associations(read):
    assert read["qualified_fields"] == [{"table": "Customers", "field": "Name", "as": "Customers.Name"},
                                        {"table": "Products", "field": "Name", "as": "Products.Name"}]
    assert "Name" not in {a["field"] for a in read["associations"]}
    assert "StoreName" in _table(read, "Stores")["fields"]             # after Unqualify
    plain = qlik.read_script("A:\nLOAD k, Name FROM [lib://X/a.qvd] (qvd);\nB:\nLOAD k2, Name FROM [lib://X/b.qvd] (qvd);")
    assert [a["field"] for a in plain["associations"]] == ["Name"]     # without Qualify the same field links the tables


def test_what_is_not_read_is_listed_with_its_line(read):
    assert [(n["line"], n["statement"][:18]) for n in read["not_read"]] == [(82, "Targets: GENERIC L")]
    text = qlik.listing(read)
    assert text.splitlines()[0] == "9 table(s), 8 linking field(s), 3 synthetic key(s), 1 circular reference(s), 1 statement(s) not read"
    assert "not read, line 82" in text


def test_column_names_a_delta_table_accepts():
    assert qlik.column_name("OrderID") == "OrderID"
    assert qlik.column_name("Order Date") == "Order_Date"
    assert qlik.column_name("%Key (old)") == "Key_old"
    assert qlik.column_name("2026") == "_2026"
    assert qlik.column_name("a b", {"A_B"}) == "a_b_2"
    both = qlik.read_script("T:\nLOAD [a b], [a-b] FROM [lib://X/t.qvd] (qvd);")
    assert [c["column"] for c in both["tables"][0]["columns"]] == ["a_b", "a_b_2"]


# ------------------------------------------------------------------ associations, counted ----------------------------

def test_one_shared_field_becomes_a_relationship_onto_the_table_where_it_is_unique(counted):
    assert counted["decided_by"] == "counts in the rows"
    assert [r["id"] for r in counted["relationships"]] == [
        "Budget.StoreID -> Stores", "OrderLines.OrderID -> Orders", "OrderLines.ProductID -> Products",
        "Orders.CustomerID -> Customers", "Orders.StoreID -> Stores", "Returns.OrderID+LineNo -> OrderLines",
        "Returns.OrderID -> Orders", "Shipments.OrderID -> Orders", "StoreSales.StoreID -> Stores"]
    r = next(r for r in counted["relationships"] if r["id"] == "Orders.CustomerID -> Customers")
    assert r["one_side"] == "counted in the rows" and r["counts"] == {
        "with_value": 6, "without_a_match": 1, "verdict": "1 of 6 rows (16.7%) point at nothing"}
    assert "land on the blank row" in r["moves_numbers"]
    roles = {t["table"]: t["role"] for t in counted["tables"]}
    assert roles["Customers"] == roles["Stores"] == roles["Products"] == "dimension"
    assert roles["Shipments"] == roles["Budget"] == roles["Returns"] == "fact"
    assert roles["Orders"].startswith("dimension that points on")
    assert {t["table"]: t.get("key") for t in counted["tables"]}["OrderLines"] == ["OrderID", "LineNo"]


def test_the_synthetic_key_trap_one_field_links_and_the_other_only_shares_a_name(counted):
    s = _syn(counted, "Orders", "Shipments")
    assert s["case"] == "one_field_links" and s["link"] == {"source": "Shipments", "target": "Orders", "field": "OrderID"}
    other = s["other_fields"][0]
    assert other["field"] == "Status" and other["rows_that_match_on_the_link_but_differ_here"] == 3
    assert other["moves_numbers"].startswith("3 row(s) of Shipments did not associate with their Orders row in Qlik")
    assert "rename it per table (Shipments_Status, Orders_Status)" in other["proposal"]
    # never one relationship per shared field: nothing links the two tables on Status
    assert not [r for r in counted["relationships"] if "Status" in r["qlik_fields"]]


def test_a_synthetic_key_that_is_a_composite_key_is_one_relationship_on_all_its_fields(counted):
    s = _syn(counted, "OrderLines", "Returns")
    assert s["case"] == "composite_key" and s["link"] == {"source": "Returns", "target": "OrderLines", "fields": ["OrderID", "LineNo"]}
    assert s["counts"]["OrderLines"]["verdict"] == "unique in all 7 rows"
    assert s["counts"]["Returns"]["unique"] is False
    r = next(r for r in counted["relationships"] if r["target"] == "OrderLines")
    assert r["source_cols"] == ["OrderID", "LineNo"] and r["counts"]["without_a_match"] == 1


def test_two_facts_that_share_dimensions_get_no_relationship_between_them(counted):
    s = _syn(counted, "Budget", "StoreSales")
    assert s["case"] == "two_facts_sharing_dimensions"
    assert s["dimensions"][1] == {"field": "StoreID", "dimension": "Stores"}
    assert s["dimensions"][0]["dimension"] is None and "a new dimension table of the distinct values of Month" in s["dimensions"][0]["proposal"]
    assert "a person decides" in s["in_the_model"]
    assert not [r for r in counted["relationships"] if {r["source"], r["target"]} == {"Budget", "StoreSales"}]


def test_a_shared_field_that_is_unique_nowhere_is_not_a_relationship_and_the_loop_goes_with_it(counted):
    assert [a["field"] for a in counted["shared_fields_with_no_key_side"]] == ["Country"]
    a = counted["shared_fields_with_no_key_side"][0]
    assert a["counts"]["Customers"]["verdict"].startswith("not unique") and "a person decides" in a["in_the_model"]
    loop = counted["circular_references"][0]
    assert loop["tables"] == ["Customers", "Orders", "Stores"] and loop["in_the_plan"].startswith("the link on Country is not a relationship")
    assert counted["undecided"] == []                                  # Month, Status and LineNo are explained by their synthetic keys


def test_a_second_way_between_two_tables_is_named(counted):
    assert counted["two_paths"] == [{"between": ["Returns", "Orders"], "one_way": "Returns.OrderID -> Orders",
                                     "other_way": ["Returns.OrderID+LineNo -> OrderLines", "OrderLines.OrderID -> Orders"],
                                     "in_the_model": counted["two_paths"][0]["in_the_model"]}]
    assert "inactive" in counted["two_paths"][0]["in_the_model"]


def test_small_cases_one_per_rule():
    def run(script_text, rows):
        rd = qlik.read_script(script_text)
        con = sqlite3.connect(":memory:")
        con.execute("ATTACH DATABASE ':memory:' AS landed")
        for t in rd["tables"]:
            cols = [c["column"] for c in t["columns"]]
            con.execute(f"CREATE TABLE landed.[{t['table']}] ({', '.join(cols)})")
            con.executemany(f"INSERT INTO landed.[{t['table']}] VALUES ({','.join('?' * len(cols))})", rows[t["name"]])
        return qlik.map_associations(rd, _sqlite_execute(con), schema="landed")

    two = "A:\nLOAD x, y, a FROM [lib://X/a.qvd] (qvd);\nB:\nLOAD x, y, b FROM [lib://X/b.qvd] (qvd);"
    # both fields are unique in B: either could carry the link
    m = run(two, {"A": [(1, 1, "p"), (1, 2, "q"), (2, 1, "r")], "B": [(1, 5, "s"), (2, 6, "t")]})
    assert m["synthetic_keys"][0]["case"] == "a_person_decides" and len(m["synthetic_keys"][0]["candidates"]) == 2
    assert m["relationships"] == []
    # the pair is unique in both tables: one-to-one on the fields together
    m = run(two, {"A": [(1, 1, "p"), (1, 2, "q"), (2, 1, "r")], "B": [(1, 1, "s"), (1, 2, "t"), (2, 1, "u")]})
    assert m["synthetic_keys"][0]["case"] == "a_person_decides" and "one-to-one" in m["synthetic_keys"][0]["why"]
    # the other field repeats the one side's value in every matching row: a copy, and no number moves
    m = run(two, {"A": [(1, 7, "p"), (1, 7, "q"), (2, 8, "r")], "B": [(1, 7, "s"), (2, 8, "t"), (3, 7, "u")]})
    other = m["synthetic_keys"][0]["other_fields"][0]
    assert m["synthetic_keys"][0]["link"]["field"] == "x" and other["rows_that_match_on_the_link_but_differ_here"] == 0
    assert "repeats B's value" in other["proposal"] and "moves_numbers" not in other
    # one field unique in two tables: one-to-one, and the names do not say which is the parent
    one = "A:\nLOAD x, a FROM [lib://X/a.qvd] (qvd);\nB:\nLOAD x, b FROM [lib://X/b.qvd] (qvd);"
    m = run(one, {"A": [(1, "p"), (2, "q")], "B": [(1, "s"), (2, "t")]})
    assert m["relationships"] == [] and "one-to-one" in m["undecided"][0]["why"]
    # an empty table decides nothing
    m = run(one, {"A": [(1, "p"), (1, "q")], "B": []})
    assert m["relationships"] == [] and m["undecided"][0]["field"] == "x"


def test_a_failed_count_and_the_query_limit_are_said_and_decide_nothing(read):
    def broken(sql):
        raise RuntimeError("no such table")
    m = qlik.map_associations(read, broken, schema="landed")
    assert m["relationships"] == [] and m["counting"]["failed"] and m["counting"]["failed"][0]["why"] == "RuntimeError"
    assert all(s["case"] == "not_decided" for s in m["synthetic_keys"])
    m = qlik.map_associations(read, lambda sql: [{"n": 1, "nulls": 0, "distinct_keys": 1}], schema="landed", max_queries=2)
    assert m["counting"]["queries"] == 2 and m["counting"]["not_counted_limit"] > 0


# ------------------------------------------------------------------ associations, names only -------------------------

def test_without_rows_the_one_side_comes_from_the_names_and_says_so(read):
    m = qlik.map_associations(read)
    assert m["decided_by"] == "names only: nothing was counted" and m["counting"]["queries"] == 0
    assert all(r["one_side"].startswith("by name (rule K") and "counts" not in r for r in m["relationships"])
    assert _syn(m, "Budget", "StoreSales")["case"] == "not_decided"
    assert _syn(m, "Orders", "Shipments")["other_fields"][0]["rows_that_match_on_the_link_but_differ_here"] == "not counted"
    assert [u["field"] for u in m["undecided"]] == ["Country"]
    assert m["shared_fields_with_no_key_side"] == []                   # "unique nowhere" is never said without counting


# ------------------------------------------------------------------ into the engine ----------------------------------

def test_the_mapping_is_a_krusgraph_plan_the_engine_checks_and_drafts_a_model_from(counted, execute):
    p, also = qlik.to_plan(counted, "landed")
    assert {t: k for t, (k, _) in p.keys.items()}["OrderLines"] == ["OrderID", "LineNo"]
    assert p.keys["Customers"] == (["CustomerID"], "K1")
    assert len(p.relationships) == 9 and {r.rule for r in p.relationships} == {"confirmed"}
    assert all(r.note.startswith("a Qlik association on ") for r in p.relationships)
    assert also == []
    v = evidence.validate(p, execute, max_items=200)                   # the engine's own check counts the same rows
    by = {(r["source"], r["target"]): r for r in v["relationships"]}
    assert by[("Orders", "Customers")]["orphans"] == 1 and by[("Shipments", "Orders")]["orphans"] == 1
    info = dict(workspace_id="ws", item_id="lh", item_name="sales_lh", item_kind="Lakehouse", schema="landed", sql_endpoint="x",
                sql_db="sales_lh", schemas_enabled=True)
    d = semantic_model.draft(p, info, "sales_model", validation=v)
    tmdl = d["parts"]["definition/relationships.tmdl"]
    assert "Orders.CustomerID" in tmdl.replace("'", "") and "Status" not in tmdl
    assert d["summary"]["combined_key_columns"]                        # the composite key is carried, not dropped


def test_what_the_name_rules_would_add_is_shown_and_kept_out():
    rd = qlik.read_script("customers:\nLOAD customer_id, name FROM [lib://X/c.qvd] (qvd);\n"
                          "orders:\nLOAD order_id, customer_id, invoice_customer_id FROM [lib://X/o.qvd] (qvd);")
    p, also = qlik.to_plan(qlik.map_associations(rd))
    assert [(r.source, r.source_cols, r.target) for r in p.relationships] == [("orders", ["customer_id"], "customers")]
    assert [(a["source_cols"], a["target"]) for a in also] == [(["invoice_customer_id"], "customers")]


# ------------------------------------------------------------------ what it is not -----------------------------------

def test_it_calls_nothing_and_claims_nothing():
    """Q2 made it three tools (fabric_backend/qlik_tools.py, tests/test_q2_qlik_tools.py). What still holds: the package
    and the tool module open no connection and import no AI client, and the workload does not call them yet."""
    paths = sorted((ROOT / "fabric_backend" / "qlik").glob("*.py")) + [ROOT / "fabric_backend" / "qlik_tools.py"]
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+(requests|httpx|urllib|socket|subprocess|anthropic|openai)\b", source, re.M), path.name
        assert "certified" not in source.lower() and "partner" not in source.lower(), path.name
    assert not re.search(r"\bqlik\b", (ROOT / "fabric_backend" / "workload_api.py").read_text(encoding="utf-8"), re.I)
    assert "Unverified" in qlik.__doc__ and "synthetic" in qlik.__doc__ and "trademark" in qlik.__doc__
    assert "synthetic" in (Q1 / "sales.qvs").read_text(encoding="utf-8").lower()


def test_inline_rows_section_access_and_connections_stay_out():
    rd = qlik.read_script("LIB CONNECT TO 'secret-connection';\nSECTION ACCESS;\nLOAD * INLINE [\nACCESS, USERID\nADMIN, USER_A\n];\n"
                          "SECTION APPLICATION;\nT:\nLOAD * INLINE [\nk, v\n1, hidden-value\n];")
    text = repr(rd) + repr(qlik.map_associations(rd))
    assert "hidden-value" not in text and "USER_A" not in text and "secret-connection" not in text
    assert [t["name"] for t in rd["tables"]] == ["T"]


def test_the_private_helpers_of_the_w7_reader_this_module_leans_on_are_there():
    for name in ("_statements", "_prefixes", "_parse_load", "_parse_select", "_split_commas", "_unquote", "_CONTROL", "_NAME"):
        assert hasattr(migration_read, name), name
    assert model.to_schema(qlik.read_script("T:\nLOAD a FROM [lib://X/t.qvd] (qvd);")).tables["T"].column_names == ["a"]
