"""W7: the reader for a synthetic Qlik load script and Tableau workbook (fabric_backend/migration_read.py).

The proof in docs/MIGRATION-DESIGN.md: it lists tables, keys, synthetic keys or joins and calculated fields, and it
lists what it did not read. Synthetic files only (tests/fixtures/w7/); nothing here was exported from Qlik or Tableau.
"""
import io
import re
import zipfile
from pathlib import Path

import pytest

from fabric_backend import migration_read as mr

ROOT = Path(__file__).resolve().parent.parent
W7 = ROOT / "tests" / "fixtures" / "w7"


@pytest.fixture(scope="module")
def qvs():
    return mr.read_qvs((W7 / "shop.qvs").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def twb():
    return mr.read_twb((W7 / "shop.twb").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ Qlik: the fixture --------------------------------

def test_qvs_tables_and_fields(qvs):
    tables = {t["name"]: t["fields"] for t in qvs["tables"]}
    assert tables == {
        "Customers": ["CustomerID", "CustomerName", "Country", "Region"],
        "Products": ["ProductID", "ProductName", "CategoryID", "ListPrice"],
        "Categories": ["CategoryID", "CategoryName"],
        "ShipTo": ["ShipToID", "City", "Country"],
        "Orders": ["OrderID", "CustomerID", "ShipToID", "OrderDate", "OrderYear", "OrderMonth"],
        "OrderLines": ["OrderID", "LineNo", "ProductID", "Quantity", "UnitPrice", "LineAmount"],
        "Shipments": ["ShipmentID", "OrderID", "CustomerID", "ShippedOn"],
        "Budget": ["BudgetYear", "BudgetAmount"],
    }


def test_qvs_keys_are_the_fields_two_tables_share(qvs):
    assert {a["field"]: a["tables"] for a in qvs["associations"]} == {
        "CategoryID": ["Categories", "Products"],
        "Country": ["Customers", "ShipTo"],
        "CustomerID": ["Customers", "Orders", "Shipments"],
        "OrderID": ["OrderLines", "Orders", "Shipments"],
        "ProductID": ["OrderLines", "Products"],
        "ShipToID": ["Orders", "ShipTo"],
    }
    keys = {t["name"]: t["keys"] for t in qvs["tables"]}
    assert keys["Orders"] == ["OrderID", "CustomerID", "ShipToID"]
    assert keys["Budget"] == [] and qvs["unlinked_tables"] == ["Budget"]


def test_qvs_synthetic_key_and_circular_reference(qvs):
    assert qvs["synthetic_keys"] == [{"tables": ["Orders", "Shipments"], "fields": ["CustomerID", "OrderID"]}]
    assert qvs["circular_references"] == [{"tables": ["Customers", "Orders", "ShipTo"],
                                           "fields": ["Country", "CustomerID", "ShipToID"]}]


def test_qvs_calculated_fields_with_their_lines(qvs):
    got = [(c["table"], c["field"], c["expression"], c["line"]) for c in qvs["calculated_fields"]]
    assert ("Customers", "Region", "ApplyMap('CountryMap', country, 'Other')", 26) in got
    assert ("Orders", "OrderYear", "Year(OrderDate)", 51) in got
    assert ("OrderLines", "LineAmount", "Quantity * UnitPrice", 67) in got
    assert len(got) == 6                                         # OrderYear and OrderMonth twice: the archive load too


def test_qvs_preceding_load_join_concatenate_and_drop(qvs):
    orders = next(t for t in qvs["tables"] if t["name"] == "Orders")
    assert orders["loads"][0]["source"] == {"kind": "sql", "name": "shop.orders", "sql_join": False}
    assert orders["loads"][0]["preceding_loads"] == 1 and orders["loads"][0]["where"] is True
    assert orders["concatenated"][0]["source"]["name"] == "lib://Shop/orders_archive.qvd"
    assert orders["concatenated"][0]["automatic"] is False
    assert qvs["dropped"] == [{"table": "OrderItems", "line": 69}]
    lines = next(t for t in qvs["tables"] if t["name"] == "OrderLines")
    assert lines["loads"][0]["source"] == {"kind": "resident", "name": "OrderItems"}   # `*` took the joined UnitPrice


def test_qvs_mapping_and_section_access_are_not_in_the_model(qvs):
    names = {t["name"] for t in qvs["tables"]}
    assert qvs["mapping_tables"] == [{"name": "CountryMap", "fields": ["code", "region"], "line": 18}]
    assert "CountryMap" not in names
    assert qvs["section_access"]["present"] is True
    assert qvs["section_access"]["tables"][0]["fields"] == ["ACCESS", "USERID", "REGION"]
    assert not any("USERID" in t["fields"] for t in qvs["tables"])


def test_qvs_tabs_variables_and_statements_without_effect(qvs):
    assert [t["name"] for t in qvs["tabs"]] == ["Main", "Access", "Dimensions", "Facts", "Other"]
    assert [(v["name"], v["kind"]) for v in qvs["variables"]] == [("ThousandSep", "set"), ("DateFormat", "set"), ("vStart", "let")]
    assert qvs["other_statements"] == {"store": 1, "trace": 1}
    assert qvs["dollar_expansions"] == 1


def test_qvs_what_is_not_read_is_listed_with_its_line(qvs):
    assert [(n["line"], n["statement"].split()[0]) for n in qvs["not_read"]] == [(83, "FOR"), (85, "NEXT"), (87, "Targets:")]
    assert "Targets" not in {t["name"] for t in qvs["tables"]}
    assert all(n["why"] for n in qvs["not_read"])


# ------------------------------------------------------------------ Qlik: one rule per small script ------------------

def _tables(script: str) -> dict:
    return {t["name"]: t for t in mr.read_qvs(script)["tables"]}


def test_two_common_fields_are_a_synthetic_key_not_a_loop():
    r = mr.read_qvs("A: LOAD x, y, a FROM a.qvd (qvd);\nB: LOAD x, y, b FROM b.qvd (qvd);\nC: LOAD x, c FROM c.qvd (qvd);")
    assert r["synthetic_keys"] == [{"tables": ["A", "B"], "fields": ["x", "y"]}]
    assert r["circular_references"] == []


def test_three_tables_on_one_field_are_not_a_loop():
    r = mr.read_qvs("A: LOAD k, a FROM a.qvd (qvd);\nB: LOAD k, b FROM b.qvd (qvd);\nC: LOAD k, c FROM c.qvd (qvd);")
    assert r["circular_references"] == [] and r["synthetic_keys"] == []


def test_a_loop_of_three_tables_is_found():
    r = mr.read_qvs("A: LOAD ab, ca FROM a.qvd (qvd);\nB: LOAD ab, bc FROM b.qvd (qvd);\nC: LOAD bc, ca FROM c.qvd (qvd);")
    assert r["circular_references"] == [{"tables": ["A", "B", "C"], "fields": ["ab", "bc", "ca"]}]


def test_link_table_candidate_by_shape():
    r = mr.read_qvs("Sales: LOAD %Key, Amount FROM s.qvd (qvd);\nLink: LOAD %Key, CustomerID, ProductID FROM l.qvd (qvd);\n"
                    "Customers: LOAD CustomerID, Name FROM c.qvd (qvd);\nProducts: LOAD ProductID, Title FROM p.qvd (qvd);")
    assert r["link_table_candidates"] == [{"table": "Link", "fields": ["%Key", "CustomerID", "ProductID"],
                                           "links": ["Customers", "Products", "Sales"]}]
    assert r["calculated_fields"] == []                          # %Key is a field name, not an expression


def test_same_fields_concatenate_automatically_unless_noconcatenate():
    auto = _tables("A: LOAD x, y FROM a.qvd (qvd);\nB: LOAD y, x FROM b.qvd (qvd);")
    assert list(auto) == ["A"] and auto["A"]["concatenated"][0]["automatic"] is True
    kept = _tables("A: LOAD x, y FROM a.qvd (qvd);\nB: NOCONCATENATE LOAD y, x FROM b.qvd (qvd);")
    assert list(kept) == ["A", "B"]


def test_join_adds_fields_and_names_the_common_ones():
    t = _tables("A: LOAD k, a FROM a.qvd (qvd);\nINNER JOIN (A) LOAD k, b FROM b.qvd (qvd);")
    assert t["A"]["fields"] == ["k", "a", "b"]
    assert t["A"]["joins"][0]["kind"] == "inner" and t["A"]["joins"][0]["on"] == ["k"]


def test_keep_leaves_two_tables():
    t = _tables("A: LOAD k, a FROM a.qvd (qvd);\nB: LEFT KEEP (A) LOAD k, b FROM b.qvd (qvd);")
    assert list(t) == ["A", "B"] and t["B"]["keep"] == {"kind": "left", "with": "A"}


def test_qualify_rename_and_drop_field():
    t = _tables("QUALIFY *;\nUNQUALIFY k;\nA: LOAD k, name FROM a.qvd (qvd);\nB: LOAD k, name FROM b.qvd (qvd);")
    assert t["A"]["fields"] == ["k", "A.name"] and t["B"]["fields"] == ["k", "B.name"]
    t = _tables("A: LOAD k, a, tmp FROM a.qvd (qvd);\nRENAME FIELD a TO [A name];\nDROP FIELD tmp;\nRENAME TABLE A TO Alpha;")
    assert list(t) == ["Alpha"] and t["Alpha"]["fields"] == ["k", "A name"]


def test_an_unlabelled_table_is_named_after_its_source():
    t = _tables("LOAD k FROM [lib://Shop/customers.qvd] (qvd);\nSQL SELECT k2 FROM shop.orders;")
    assert list(t) == ["customers", "orders"]


def test_a_star_over_a_file_says_the_fields_are_unknown():
    t = _tables("A: LOAD * FROM a.qvd (qvd);")
    assert t["A"]["fields"] == [] and "not in the script" in t["A"]["fields_unknown"]


def test_names_that_differ_only_by_case_are_listed():
    r = mr.read_qvs("A: LOAD CustomerID, a FROM a.qvd (qvd);\nB: LOAD CustomerId, b FROM b.qvd (qvd);")
    assert r["associations"] == [] and r["names_that_differ_only_by_case"] == [["CustomerID", "CustomerId"]]


def test_comments_and_quotes_do_not_break_statements():
    r = mr.read_qvs("// A: LOAD x FROM gone.qvd;\n/* B: LOAD y FROM gone.qvd; */\nREM C: LOAD z FROM gone.qvd;\n"
                    "A: LOAD k, 'a;b' AS [semi;colon], If(k > 1, 'x,y', 'z') AS flag FROM a.qvd (qvd);")
    assert [t["name"] for t in r["tables"]] == ["A"]
    assert r["tables"][0]["fields"] == ["k", "semi;colon", "flag"]
    assert r["tables"][0]["loads"][0]["line"] == 4


def test_a_load_without_a_source_at_the_end_is_not_read():
    r = mr.read_qvs("A: LOAD k, a;")
    assert r["tables"] == [] and r["not_read"][0]["why"].startswith("a load without a source")


def test_unknown_statements_are_listed_never_dropped():
    r = mr.read_qvs("FROBNICATE everything;\nBINARY [other.qvf];\nA: LOAD k FROM a.qvd (qvd);")
    assert [n["statement"] for n in r["not_read"]] == ["FROBNICATE everything", "BINARY [other.qvf]"]
    assert [t["name"] for t in r["tables"]] == ["A"]


def test_what_stays_out_of_the_answer():
    r = mr.read_qvs("SET vDbPassword='hunter2';\nLIB CONNECT TO 'shop (user_a)';\n"
                    "A: LOAD * INLINE [\nk, name\n1, Alpha\n2, Beta\n];")
    text = repr(r)
    assert "hunter2" not in text and "user_a" not in text and "Alpha" not in text
    assert r["variables"][0]["value"].startswith("(not shown") and r["other_statements"] == {"lib connect": 1}
    assert r["tables"][0]["loads"][0]["source"] == {"kind": "inline", "name": "", "rows": 2}
    wb = repr(mr.read_twb((W7 / "shop.twb").read_text(encoding="utf-8")))
    assert "example.invalid" not in wb and "WHERE list_price" not in wb


def test_qvs_refuses_what_it_does_not_take():
    with pytest.raises(mr.ReadError):
        mr.read_qvs(b"LOAD 1;")
    with pytest.raises(mr.ReadError):
        mr.read_qvs("x" * (mr.MAX_CHARS + 1))


# ------------------------------------------------------------------ Tableau: the fixture -----------------------------

def test_twb_data_sources_tables_and_extract(twb):
    orders, products = twb["datasources"]
    assert (orders["caption"], products["caption"]) == ("Shop orders", "Products")
    assert [(t["name"], t.get("table")) for t in orders["tables"]] == [
        ("orders", "[shop].[orders]"), ("order_items", "[shop].[order_items]"), ("customers", "[shop].[customers]")]
    assert orders["extract"] == {"enabled": True, "filters": 0} and products["extract"]["enabled"] is False
    assert orders["connection_classes"] == ["hyper", "sqlserver"]
    assert twb["version"] == "18.1" and twb["dashboards"] == ["Shop overview"]


def test_twb_joins_with_their_clauses_and_keys(twb):
    orders = twb["datasources"][0]
    assert orders["joins"] == [
        {"type": "inner", "clauses": [{"left": "[orders].[order_id]", "right": "[order_items].[order_id]", "op": "="}],
         "tables": ["orders", "order_items"]},
        {"type": "left", "clauses": [{"left": "[orders].[customer_id]", "right": "[customers].[customer_id]", "op": "="}],
         "tables": ["orders", "customers"]},
    ]
    assert orders["keys"] == ["[customers].[customer_id]", "[order_items].[order_id]", "[orders].[customer_id]", "[orders].[order_id]"]
    assert orders["relationships"] == []


def test_twb_relationship_custom_sql_and_prefixed_tags(twb):
    products = twb["datasources"][1]
    assert products["relationships"] == [{"tables": ["products", "categories"],
                                          "clauses": [{"left": "[category_id]", "right": "[category_id (categories)]", "op": "="}]}]
    assert products["joins"] == []
    assert [(t["name"], t["kind"]) for t in products["tables"]] == [
        ("products", "table"), ("categories", "table"), ("price list", "custom_sql")]
    assert next(t for t in products["tables"] if t["kind"] == "custom_sql")["sql_lines"] == 3


def test_twb_calculated_fields_and_their_kinds(twb):
    calcs = {c["caption"]: c for c in twb["datasources"][0]["calculated_fields"]}
    assert {k: v["kind"] for k, v in calcs.items()} == {
        "Order amount per order": "level_of_detail", "First order date": "level_of_detail",
        "Quantity per order": "level_of_detail", "Total quantity": "aggregate",
        "Running quantity": "table_calculation", "Is large line": "row_level"}
    assert calcs["Order amount per order"]["level_of_detail"] == [{"scope": "FIXED", "dimensions": ["order_id"]}]
    assert calcs["Quantity per order"]["level_of_detail"] == [{"scope": "INCLUDE", "dimensions": ["order_id"]}]
    assert calcs["Is large line"]["formula"] == "[quantity] >= [Parameters].[Parameter 1]"
    assert calcs["Is large line"]["references"] == ["Parameter 1", "Parameters", "quantity"]
    assert twb["datasources"][1]["calculated_fields"] == []


def test_twb_parameters_and_worksheets(twb):
    assert twb["parameters"] == [{"name": "[Parameter 1]", "caption": "Top N", "datatype": "integer", "value": "10"}]
    sheets = {w["name"]: w for w in twb["worksheets"]}
    assert sheets["Orders by country"]["calculated_fields"] == ["Order amount per order"]
    assert sheets["Orders by country"]["filters"][0]["context"] is False
    assert sheets["Quantity in context"]["filters"][0]["context"] is True


def test_twb_traps(twb):
    traps = [(t["trap"], t.get("field") or t.get("table") or tuple(t.get("tables", []))) for t in twb["traps"]]
    assert traps == [
        ("fixed_lod_with_filter_outside_context", "Order amount per order"),
        ("lod_depends_on_the_view", "Quantity per order"),
        ("table_calculation", "Running quantity"),
        ("physical_join", ("orders", "order_items")),
        ("physical_join", ("orders", "customers")),
        ("custom_sql", "price list"),
    ]
    fixed = twb["traps"][0]
    assert fixed["worksheet"] == "Orders by country"            # the sheet whose filter is in context is not a trap
    assert "Unverified" in fixed["why"]


def test_a_lod_without_a_keyword_is_fixed_over_the_table():
    wb = ("<workbook version='18.1'><datasources><datasource name='d'><column caption='All' name='[c]'>"
          "<calculation class='tableau' formula='{ SUM([x]) }' /></column></datasource></datasources></workbook>")
    c = mr.read_twb(wb)["datasources"][0]["calculated_fields"][0]
    assert c["kind"] == "level_of_detail" and c["level_of_detail"][0]["scope"] == "FIXED" and c["level_of_detail"][0]["dimensions"] == []


def test_twb_lists_top_level_elements_it_does_not_know():
    r = mr.read_twb("<workbook version='18.1'><datasources /><something-new /></workbook>")
    assert r["not_read"] == [{"element": "something-new", "why": "not an element this reader knows"}]


def test_twb_refuses_what_it_does_not_take():
    for bad in ("<workbook><unclosed></workbook>", "<datasource />", "<!DOCTYPE x [<!ENTITY a 'b'>]><workbook />"):
        with pytest.raises(mr.ReadError):
            mr.read_twb(bad)


def test_twbx_reads_the_one_workbook_in_the_package(twb):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("shop.twb", (W7 / "shop.twb").read_text(encoding="utf-8"))
        z.writestr("Data/Extracts/shop.hyper", b"not opened")
    r = mr.read_twbx(buf.getvalue())
    assert r["package"] == {"workbook": "shop.twb", "other_files": 1}
    assert r["datasources"] == twb["datasources"]
    with pytest.raises(mr.ReadError):
        mr.read_twbx(b"not a zip")
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("readme.txt", "no workbook")
    with pytest.raises(mr.ReadError):
        mr.read_twbx(empty.getvalue())


# ------------------------------------------------------------------ the list, and the limits of the proof ------------

def test_listing_names_tables_keys_synthetic_keys_joins_and_calculated_fields(qvs, twb):
    q = mr.listing(qvs)
    assert q.splitlines()[0] == ("Qlik load script: 8 table(s), 6 linking field(s), 1 synthetic key(s), 1 circular reference(s), "
                                 "6 calculated field(s), 3 statement(s) not read.")
    for line in ("table Orders: OrderID, CustomerID, ShipToID, OrderDate, OrderYear, OrderMonth | keys: OrderID, CustomerID, ShipToID",
                 "synthetic key: Orders and Shipments share CustomerID, OrderID",
                 "circular reference: Customers - Orders - ShipTo through Country, CustomerID, ShipToID",
                 "calculated field OrderLines.LineAmount = Quantity * UnitPrice (line 67)"):
        assert line in q.splitlines()
    t = mr.listing(twb)
    assert t.splitlines()[0] == ("Tableau workbook: 2 data source(s), 6 table(s), 2 join(s), 1 relationship(s), "
                                 "6 calculated field(s), 6 trap(s).")
    for line in ("  inner join: [orders].[order_id] = [order_items].[order_id]",
                 "  relationship products - categories: [category_id] = [category_id (categories)]",
                 "  calculated field Order amount per order (level_of_detail) = { FIXED [order_id] : MAX([order_amount]) }"):
        assert line in t.splitlines()


def test_reading_is_deterministic(qvs, twb):
    assert mr.read_qvs((W7 / "shop.qvs").read_text(encoding="utf-8")) == qvs
    assert mr.read_twb((W7 / "shop.twb").read_bytes()) == twb


def test_the_reader_is_a_proof_and_not_a_tool():
    source = (ROOT / "fabric_backend" / "migration_read.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(requests|httpx|urllib|socket|subprocess|anthropic|openai)\b", source, re.M)
    for name in ("server.py", "mcp_server.py", "workload_api.py"):
        assert "migration_read" not in (ROOT / "fabric_backend" / name).read_text(encoding="utf-8")
    assert "Unverified" in mr.__doc__ and "synthetic" in mr.__doc__


def test_the_fixtures_and_the_design_make_no_claim_they_cannot_back():
    for path in (W7 / "shop.qvs", W7 / "shop.twb", W7 / "README.md", ROOT / "fabric_backend" / "migration_read.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "certified" not in text and "sap-compatible" not in text, path.name
    for path in (W7 / "shop.qvs", W7 / "shop.twb"):
        assert "synthetic" in path.read_text(encoding="utf-8").lower()
