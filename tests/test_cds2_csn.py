"""CDS2: SAP's Core Schema Notation (CSN) read as declared-by-metadata candidates (fabric_backend/csn.py).

Fixtures (tests/fixtures/csn/, README.md there): one public CSN file from SAP-samples/datasphere-content (Apache-2.0),
and two synthetic CSN files written for these tests. No metadata exported from an SAP system.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from fabric_backend import csn, csn_demo, evidence
from fabric_backend.infer import plan
from fabric_backend.schema import Schema

FIX = Path(__file__).parent / "fixtures" / "csn"
BIKE = FIX / "datasphere_bike_sales_model.json"
ORDERS = FIX / "synthetic_service_orders.json"
CAP = FIX / "synthetic_cap_bookshop.json"
AIRLINE = FIX / "interop_airline.json"
ARIBA = FIX / "interop_cap_ariba_supplier_service.json"
DOC = Path(__file__).resolve().parent.parent / "docs" / "SAP-CSN.md"


def _schema(tables: dict[str, list[str]], name: str = "dbo", types: dict[str, str] | None = None) -> Schema:
    return Schema.from_information_schema([(name, t, c, (types or {}).get(c, "varchar"), i + 1)
                                           for t, cols in tables.items() for i, c in enumerate(cols)], schema=name)


def _bike_schema(table=lambda n: n, column=lambda c: c, cdc: bool = False) -> Schema:
    m = csn.read(BIKE)
    tables, types = {}, {}
    for n, e in m.entities.items():
        tables[table(n)] = [column(c) for c in e.elements] + (list(csn.CDC_COLUMNS) if cdc else [])
        types.update({column(c): "decimal" for c, el in e.elements.items() if "Decimal" in el["type"]})
    return _schema(tables, types=types)


# ---------------------------------------------------------------------------------------------------- the fixtures

def test_the_public_fixture_is_the_pinned_file_with_its_licence_recorded():
    readme = (FIX / "README.md").read_text(encoding="utf-8")
    assert "SAP-samples/datasphere-content" in readme and "695af09278d8a57d0fb0a441f247060eaea5daf5" in readme
    assert "Apache-2.0" in readme and "Copyright" in readme
    import hashlib
    assert hashlib.sha256(BIKE.read_bytes()).hexdigest() in readme
    for f, sha in ((AIRLINE, "6e9a2a1b90b88ef47e316c5d72aab715ffbced57db519864acdadc34f68328ce"),
                   (ARIBA, "a14d791fe2b379b41b60ed04e5d772429468f2ba9526b6c416240fdac1d5d92b")):
        assert hashlib.sha256(f.read_bytes()).hexdigest() == sha and sha in readme
    assert "ccf90cbba0be6eae411be4cf8356c2989c40bd30" in readme
    notices = (Path(__file__).resolve().parent.parent / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "datasphere-content" in notices and "csn-interop-specification" in notices
    for lic in ("LICENSE-datasphere-content.txt", "LICENSE-csn-interop-specification.txt"):
        assert "Apache License" in (FIX / lic).read_text(encoding="utf-8")


def test_the_synthetic_fixtures_say_they_are_synthetic():
    for f in (ORDERS, CAP):
        assert "SYNTHETIC" in json.loads(f.read_text(encoding="utf-8"))["meta"]["creator"]


# ---------------------------------------------------------------------------------------------------- reading

def test_reads_the_public_datasphere_er_model():
    m = csn.read(BIKE)
    assert len(m.entities) == 9
    assert m.versions[0]["csn"] == "0.2" and m.versions[0]["flavor"] == "sap.dwc.ermodel"
    so = m.entities["SalesOrders"]
    assert so.keys == ["SALESORDERID"] and so.label == "Sales Orders"
    assert so.elements["NETAMOUNT"]["type"] == "cds.Decimal(15,2)"
    assert m.entities["SalesOrderItems"].keys == ["SALESORDERID", "SALESORDERITEM"]
    assert m.entities["Employees"].keys == ["EMPLOYEEID", "VALIDITY_ENDDATE"]
    a = {x.name: x for x in so.associations}
    assert a["_SalesOrderItems"].pairs == [("SALESORDERID", "SALESORDERID")] and a["_SalesOrderItems"].cardinality is None
    assert a["_Employees"].pairs == [("CREATEDBY", "EMPLOYEEID")]
    assert m.ignored == []


def test_reads_sap_csn_interop_examples():
    m = csn.read(AIRLINE)
    assert m.versions[0]["interop"] == "1.2" and m.versions[0]["$version"] == "2.0"
    assert not any(x["what"] in ("$schema", "csnInteropEffective") for x in m.ignored)
    fl = m.entities["AirlineService.Flight"]
    assert fl.keys == ["AirlineID", "FlightDate", "ConnectionID"] and fl.data_category == "ANALYTICAL_FACT"
    assert fl.amounts == [{"column": "Price", "currency": "CurrencyCode_code", "from": "@Semantics.amount.currencyCode"}]
    conn = {a.name: a for a in fl.associations}["to_Connection"]
    assert conn.pairs == [("AirlineID", "AirlineID"), ("ConnectionID", "ConnectionID")]
    assert m.entities["AirlineService.FlightConnection"].quantities[0]["unit"] == "DistanceUnit"
    assert m.entities["AirlineService.Countries_texts"].data_category == "LANGUAGE_DEPENDENT_TEXT"
    assert m.entities["AirlineService.Airport"].foreign_keys == {"CountryCode_code": "to_CountryCode"}
    assert {x["what"] for x in m.ignored} >= {"AirlineService", "@Semantics.language"}
    a = csn.read(ARIBA)
    assert a.versions[0]["creator"] == "CDS Compiler v5.4.2"
    assert {x.name: x for x in a.entities["ariba.BusinessPartner"].associations}["alternative"].pairs == [
        ("alternative_BP_NUMBER", "BP_NUMBER"), ("alternative_BP_TYPE", "BP_TYPE")]


def test_interop_airline_plan_on_a_snake_case_landing():
    m = csn.read(AIRLINE)
    snake = lambda x: re.sub(r"(?<=[a-z])(?=[A-Z])", "_", x).lower()
    s = _schema({snake(n.split(".")[-1]): [snake(c) for c in e.elements] + [snake(c) for a in e.associations for c, _ in a.pairs if a.managed]
                 for n, e in m.entities.items()}, types={"price": "decimal", "distance": "decimal"})
    p, rep = csn.plan(s, m)
    assert len(rep["matched"]) == 7 and p.keys["flight"] == (["airline_id", "flight_date", "connection_id"], csn.RULE)
    r = {k: v for k, v in _rels(p).items() if v.rule == csn.RULE}
    assert ("flight", ("airline_id", "connection_id"), "flight_connection") in r
    assert ("countries_texts", ("code",), "countries") in r                       # Countries.texts, read the other way
    assert "declares to-many" in r[("flight", ("airline_id",), "airline")].note     # to_Airline [0..*] on Airline's key
    assert {(a["table"], a["column"]) for a in rep["amounts"] if a["kind"] == "amount"} == {("flight", "price")}


def test_reads_keys_cardinality_and_semantic_annotations():
    m = csn.read(ORDERS)
    so, it = m.entities["ZI_ServiceOrder"], m.entities["ZI_ServiceOrderItem"]
    assert so.kind == "view" and so.data_category == "FACT" and m.entities["ZI_Customer"].data_category == "DIMENSION"
    assert m.entities["ZI_ProductText"].data_category == "TEXT"
    assert so.amounts == [{"column": "TotalNetAmount", "currency": "TransactionCurrency", "from": "@Semantics.amount.currencyCode"}]
    assert it.quantities == [{"column": "Quantity", "unit": "QuantityUnit", "from": "@Semantics.quantity.unitOfMeasure"}]
    assert so.currency_codes == ["TransactionCurrency"] and it.units == ["QuantityUnit"]
    assert so.texts == [{"column": "ServiceOrder", "text_element": "ServiceOrderDescription"}]
    assert m.entities["ZI_Product"].texts == [{"column": "Product", "text_association": "_Text"}]
    assert it.foreign_keys == {"ServiceOrder": "_ServiceOrder", "Product": "_Product"}
    assert so.measures == ["TotalNetAmount"]
    a = {x.name: x for x in so.associations}
    assert a["_Item"].to_many is True and a["_Customer"].to_many is False
    assert a["_Item"].pairs == [("ServiceOrder", "ServiceOrder")]
    assert not a["_StatusText"].understood and "literal" in a["_StatusText"].why


def test_what_is_not_understood_is_listed_not_guessed():
    m = csn.read(ORDERS)
    whats = {x["what"]: x["why"] for x in m.ignored}
    assert "kind 'type'" in whats["ZAmount"] and "kind 'service'" in whats["ZServiceOrderService"]
    assert "annotation not read" in whats["@AccessControl.authorizationCheck"]
    assert "literal" in whats["ZI_ServiceOrder._StatusText"]


def test_cap_managed_associations_backlinks_and_structured_elements():
    m = csn.read(CAP)
    books = m.entities["my.bookshop.Books"]
    a = {x.name: x for x in books.associations}
    assert a["author"].managed and a["author"].pairs == [("author_ID", "ID")]
    assert a["currency"].pairs == [("currency_code", "code")]
    assert a["genre"].pairs == [("genre_ID", "ID")]                     # no keys given: the target's key
    back = m.entities["my.bookshop.Authors"].associations[0]
    assert back.pairs == [("ID", "author_ID")]                          # books.author = $self
    assert "address_city" in m.entities["my.bookshop.Authors"].elements
    assert books.amounts == [{"column": "price", "currency": "currency_code", "from": "@Measures.ISOCurrency"}]
    assert [x["what"] for x in m.ignored] == ["my.bookshop"]


@pytest.mark.parametrize("on, why", [
    ([{"ref": ["a"]}, "=", {"ref": ["_T", "a"]}, "or", {"ref": ["b"]}, "=", {"ref": ["_T", "b"]}], "not AND"),
    ([{"ref": ["a"]}, ">", {"ref": ["_T", "a"]}], "equalities"),
    ([{"func": "upper", "args": [{"ref": ["a"]}]}, "=", {"ref": ["_T", "a"]}], "expression"),
    ([{"ref": ["a"]}, "=", {"ref": ["b"]}], "same side"),
    ([{"ref": ["Other", "a"]}, "=", {"ref": ["_T", "a"]}], "neither"),
])
def test_an_on_condition_it_cannot_reduce_to_column_pairs_is_refused(on, why):
    d = {"definitions": {"S": {"kind": "entity", "elements": {"a": {"key": True, "type": "cds.String"}, "b": {"type": "cds.String"},
                                                             "_T": {"type": "cds.Association", "target": "T", "on": on}}},
                         "T": {"kind": "entity", "elements": {"a": {"key": True, "type": "cds.String"}, "b": {"type": "cds.String"}}}}}
    a = csn.read(d).entities["S"].associations[0]
    assert not a.understood and why in a.why


def test_parenthesised_and_xpr_on_conditions_are_read():
    on = ["(", {"ref": ["a"]}, "=", {"ref": ["_T", "a"]}, ")", "and", {"xpr": [{"ref": ["$projection", "b"]}, "=", {"ref": ["_T", "b"]}]}]
    d = {"definitions": {"S": {"kind": "entity", "elements": {"a": {"key": True, "type": "cds.String"}, "b": {"type": "cds.String"},
                                                             "_T": {"type": "cds.Association", "target": "T", "on": on}}}}}
    assert csn.read(d).entities["S"].associations[0].pairs == [("a", "a"), ("b", "b")]


def test_nested_annotations_and_plain_string_values_are_read():
    d = {"definitions": {"E": {"kind": "entity", "@Analytics": {"dataCategory": "#CUBE"}, "elements": {
        "k": {"key": True, "type": "cds.String"},
        "amt": {"type": "cds.Decimal", "@Semantics": {"amount": {"currencyCode": "cur"}}},
        "cur": {"type": "cds.String"}}}}}
    e = csn.read(d).entities["E"]
    assert e.data_category == "CUBE" and e.amounts[0]["currency"] == "cur"


def test_a_folder_is_read_in_name_order_and_a_second_definition_is_ignored(tmp_path):
    (tmp_path / "a.json").write_text(ORDERS.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "b.csn").write_text(ORDERS.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not read", encoding="utf-8")
    m = csn.read(tmp_path)
    assert m.files == ["a.json", "b.csn"] and m.entities["ZI_Customer"].file == "a.json"
    assert any(x["file"] == "b.csn" and x["what"] == "ZI_Customer" and "defined again" in x["why"] for x in m.ignored)


def test_bad_input_says_what_is_wrong(tmp_path):
    with pytest.raises(ValueError, match="no such file"):
        csn.read(tmp_path / "missing.json")
    (tmp_path / "x.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not JSON"):
        csn.read(tmp_path / "x.json")
    m = csn.read({"something": 1})
    assert m.entities == {} and "no 'definitions'" in m.ignored[0]["why"]
    m = csn.read({"definitions": {"V": {"kind": "entity", "query": {"SELECT": {}}}}})
    assert "no elements" in m.ignored[0]["why"]
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="no .json or .csn"):
        csn.read(empty)


# ---------------------------------------------------------------------------------------------------- names

@pytest.mark.parametrize("entity, table", [
    ("SalesDocument", "SalesDocument"), ("SalesDocument", "SALESDOCUMENT"), ("SalesDocument", "sales_document"),
    ("SalesDocument", "salesdocument"), ("I_SalesDocument", "SalesDocument"), ("I_SalesDocument", "I_SALES_DOCUMENT"),
    ("my.bookshop.Books", "my_bookshop_Books"), ("my.bookshop.Books", "Books"), ("my.bookshop.Books", "MY_BOOKSHOP_BOOKS"),
    ("ZI_ServiceOrder", "ServiceOrder"), ("ZI_ServiceOrder", "dsp_zi_serviceorder"), ("SalesOrders", "bronze_SalesOrders"),
])
def test_a_table_answers_to_the_entity_in_any_spelling(entity, table):
    names = {n for n, _ in csn.entity_names(entity)}
    assert names & set(csn.table_names(table))


def test_the_callers_prefix_is_dropped():
    assert "SALESORDERS" in csn.table_names("acme01_SalesOrders", prefix="acme01_")
    assert "SALESORDERS" not in csn.table_names("acme01_SalesOrders")


@pytest.mark.parametrize("style", ["as is", "upper", "lower", "snake", "prefixed"])
def test_every_bike_entity_is_matched_in_every_landing_spelling(style):
    snake = lambda s: re.sub(r"(?<=[a-z])(?=[A-Z])", "_", s).lower()
    t, c = {"as is": (lambda n: n, lambda c: c), "upper": (str.upper, str.upper), "lower": (str.lower, str.lower),
            "snake": (snake, str.lower), "prefixed": (lambda n: "sap_" + n.lower(), str.lower)}[style]
    nm = csn.match(_bike_schema(t, c), csn.read(BIKE))
    assert len(nm.tables) == 9 and nm.unmatched == [] and nm.ambiguous == []


def test_a_table_without_the_key_columns_is_not_taken():
    nm = csn.match(_schema({"SalesOrders": ["PARTNERID", "NETAMOUNT"]}), csn.read(BIKE))
    assert "SalesOrders" not in nm.tables
    assert any(x["entity"] == "SalesOrders" and "lacks key" in x["why"] for x in nm.unmatched)


def test_two_tables_answering_to_one_entity_are_reported_not_resolved():
    nm = csn.match(_schema({"SalesOrders": ["SALESORDERID"], "sales_orders": ["SALESORDERID"]}), csn.read(BIKE))
    assert "SalesOrders" not in nm.tables and nm.ambiguous[0]["entity"] == "SalesOrders"


def test_two_entities_answering_to_one_table_are_reported():
    d = {"definitions": {n: {"kind": "entity", "elements": {"Id": {"key": True, "type": "cds.String"}}} for n in ("I_Order", "ZI_Order")}}
    nm = csn.match(_schema({"Order": ["Id"]}), csn.read(d))
    assert nm.tables == {} and nm.ambiguous and set(nm.ambiguous[0]["entities"]) == {"I_Order", "ZI_Order"}


def test_the_change_columns_are_reported_and_left_out_of_the_tables_columns():
    s = _bike_schema(cdc=True)
    assert "__operation_type" not in s["SalesOrders"].column_names
    assert "__sequence_number" not in s["SalesOrders"].column_names and "__timestamp" not in s["SalesOrders"].column_names
    nm = csn.match(s, csn.read(BIKE))
    assert nm.cdc_columns["SalesOrders"] == list(csn.CDC_COLUMNS) and "SalesOrders" not in nm.extra_columns


def test_a_numeric_element_landed_as_text_is_reported():
    s = _schema({"SalesOrders": ["SALESORDERID", "NETAMOUNT"]}, types={"NETAMOUNT": "varchar"})
    nm = csn.match(s, csn.read(BIKE))
    assert nm.type_differences[0]["column"] == "NETAMOUNT" and "cast" in nm.type_differences[0]["why"]


# ---------------------------------------------------------------------------------------------------- the plan

def _rels(p):
    return {(r.source, tuple(r.source_cols), r.target): r for r in p.relationships}


def test_bike_keys_and_links_from_the_csn_with_reverse_reading():
    s = _bike_schema(str.lower, str.lower, cdc=True)
    p, rep = csn.plan(s, csn.read(BIKE))
    assert all(p.keys[t][1] == csn.RULE for t in rep["keys"]) and len(rep["keys"]) == 9
    assert p.keys["employees"] == (["employeeid", "validity_enddate"], csn.RULE)
    r = _rels(p)
    expected = {("salesorderitems", ("salesorderid",), "salesorders"),       # SalesOrders._SalesOrderItems, read the other way
                ("salesorderitems", ("productid",), "products"),
                ("salesorders", ("partnerid",), "businesspartners"),
                ("businesspartners", ("addressid",), "addresses"),
                ("employees", ("addressid",), "addresses"),
                ("products", ("prodcategoryid",), "productcategories"),
                ("producttexts", ("productid",), "products"),                # Products._ProductTexts, read the other way
                ("productcategorytext", ("prodcategoryid",), "productcategories")}
    assert {k for k, v in r.items() if v.rule == csn.RULE} == expected
    assert "read as" in r[("salesorderitems", ("salesorderid",), "salesorders")].note
    na = {x["association"]: x["why"] for x in rep["not_applied"]}
    assert "not a key join" in na["SalesOrders._Employees"]                 # EMPLOYEEID alone of EMPLOYEEID + VALIDITY_ENDDATE
    assert all(x["provenance"] == csn.PROVENANCE for x in rep["links"])
    assert "CSN metadata" in p.summary()


def test_a_csn_header_amount_feeds_the_doubled_total_check():
    s = _bike_schema()
    p, rep = csn.plan(s, csn.read(BIKE))
    from fabric_backend import amounts
    found = {(f["header"], f["line"]): f["amount_columns"] for f in amounts.header_amounts(p)}
    assert "NETAMOUNT" in found[("SalesOrders", "SalesOrderItems")]     # by name; the CSN gave the link


def test_an_amount_named_like_nothing_is_found_because_the_csn_marks_it():
    d = {"definitions": {
        "H": {"kind": "entity", "elements": {"Doc": {"key": True, "type": "cds.String"},
                                              "Wert": {"type": "cds.Decimal", "@Semantics.amount.currencyCode": {"=": "Cur"}},
                                              "Cur": {"type": "cds.String", "@Semantics.currencyCode": True},
                                              "_I": {"type": "cds.Association", "target": "I", "cardinality": {"max": "*"},
                                                     "on": [{"ref": ["Doc"]}, "=", {"ref": ["_I", "Doc"]}]}}},
        "I": {"kind": "entity", "elements": {"Doc": {"key": True, "type": "cds.String"}, "Pos": {"key": True, "type": "cds.String"}}}}}
    s = _schema({"H": ["Doc", "Wert", "Cur"], "I": ["Doc", "Pos"]}, types={"Wert": "decimal"})
    from fabric_backend import amounts
    assert not amounts.looks_like_amount("Wert", "decimal")
    p, rep = csn.plan(s, csn.read(d))
    assert rep["amounts"][0]["level"] == "header" and rep["amounts"][0]["repeated_by"] == ["I"]
    assert amounts.header_amounts(p)[0]["amount_columns"] == ["Wert"]
    assert amounts.header_amounts(plan(s)) == []                         # without the CSN: not an amount, and no link


def test_cap_bookshop_plan_with_managed_associations():
    s = _schema({"my_bookshop_Authors": ["ID", "name", "address_city", "address_country"],
                 "my_bookshop_Books": ["ID", "title", "price", "currency_code", "author_ID", "genre_ID"],
                 "my_bookshop_Genres": ["ID", "name", "parent_ID"], "sap_common_Currencies": ["code", "symbol"]})
    p, rep = csn.plan(s, csn.read(CAP))
    r = {k for k, v in _rels(p).items() if v.rule == csn.RULE}
    assert ("my_bookshop_Books", ("author_ID",), "my_bookshop_Authors") in r
    assert ("my_bookshop_Books", ("genre_ID",), "my_bookshop_Genres") in r
    assert ("my_bookshop_Books", ("currency_code",), "sap_common_Currencies") in r
    assert ("my_bookshop_Genres", ("parent_ID",), "my_bookshop_Genres") in r
    author = next(x for x in rep["links"] if x["source_cols"] == ["author_ID"])
    assert len(author["declared_in"]) == 2                              # Books.author and the backlink Authors.books: one link


def test_the_callers_keys_and_links_win_over_the_csn():
    s = _bike_schema()
    p, rep = csn.plan(s, csn.read(BIKE), keys={"Employees": ["EMPLOYEEID"]},
                      confirmed=[{"source": "SalesOrders", "source_cols": ["CREATEDBY"], "target": "Employees",
                                                  "target_cols": ["EMPLOYEEID"]}])
    assert p.keys["Employees"] == (["EMPLOYEEID"], "K1")
    assert _rels(p)[("SalesOrders", ("CREATEDBY",), "Employees")].rule == "confirmed"


def test_without_a_matching_table_nothing_changes():
    s = _schema({"orders": ["order_id", "customer_id", "amount"], "customers": ["customer_id", "name"]})
    p, rep = csn.plan(s, csn.read(BIKE))
    base = plan(s)
    assert rep["matched"] == {} and p.keys == base.keys
    assert [(r.source, r.target, r.rule) for r in p.relationships] == [(r.source, r.target, r.rule) for r in base.relationships]


def test_downstream_outputs_take_the_csn_rule():
    from fabric_backend.dbt import schema_yml
    from fabric_backend.dictionary import data_dictionary
    p, _ = csn.plan(csn_demo.schema(), csn.read(ORDERS))
    assert "CSN metadata" in p.mermaid()
    assert "dsp_zi_serviceorder" in data_dictionary(p, "lakehouse", p.schema.schema)
    assert "dsp_zi_serviceorder" in schema_yml(p, "lakehouse", p.schema.schema)


# ---------------------------------------------------------------------------------------------------- the rows

def test_the_engine_on_the_csn_described_sample():
    f = csn_demo.facts()
    e = csn_demo.EXPECTED
    assert f["tables"] == e["tables"] and f["csn_keys"] == e["csn_keys"] and f["csn_links"] == e["csn_links"]
    assert f["keys_unique"] == e["keys_unique"] and f["not_unique"] == [e["not_unique"]]   # metadata is not proof
    assert [(o["source"], o["target"], o["orphans"]) for o in f["orphans"]] == e["orphans"]
    assert [(h["header"], h["line"], h["columns"][0], h["over_the_join"], h["on_the_header"]) for h in f["header_amounts"]] == e["header_amounts"]
    assert {(a["table"], a["column"], a["level"]) for a in f["csn_amounts"] if a["kind"] == "amount"} == {
        ("dsp_zi_serviceorder", "TOTALNETAMOUNT", "header"), ("dsp_zi_serviceorderitem", "NETAMOUNT", "item")}
    assert len(f["cdc_columns"]) == 5


def test_without_the_csn_the_name_rules_find_nothing_on_that_landing():
    src = csn_demo.source()
    try:
        p = plan(src.schema)
        assert p.keys == {} and p.relationships == []
    finally:
        src.close()


# ---------------------------------------------------------------------------------------------------- inputs

def test_cli_reads_a_csn_file_and_plans_with_columns(tmp_path, capsys):
    from fabric_backend.cli import main
    assert main(["csn", str(ORDERS)]) == 0
    out = capsys.readouterr().out
    assert "ZI_ServiceOrder (view, FACT): key ServiceOrder" in out and "ignored: ZAmount" in out
    cols = tmp_path / "columns.csv"
    rows = ["table_schema,table_name,column_name,data_type,ordinal_position"]
    for t, (cs, types, _) in csn_demo.tables().items():
        rows += [f"dbo,{t},{c},{'decimal' if 'DECIMAL' in ty else 'varchar'},{i + 1}" for i, (c, ty) in enumerate(zip(cs, types))]
    cols.write_text("\n".join(rows) + "\n", encoding="utf-8")
    out_json = tmp_path / "report.json"
    assert main(["csn", str(ORDERS), "--columns", str(cols), "--json", str(out_json)]) == 0
    out = capsys.readouterr().out
    assert "dsp_zi_serviceorderitem.SERVICEORDER -> dsp_zi_serviceorder.SERVICEORDER  [CSN metadata]" in out
    assert "amount dsp_zi_serviceorder.TOTALNETAMOUNT: header level" in out
    assert json.loads(out_json.read_text(encoding="utf-8"))["rule"] == csn.RULE
    assert main(["csn", str(tmp_path / "missing.json")]) == 2


def test_the_local_mcp_server_plans_with_the_csn_named_in_its_environment(monkeypatch):
    pytest.importorskip("mcp")
    from fabric_backend import mcp_server
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: csn_demo.schema()))
    monkeypatch.setenv("KRUSGRAPH_CSN", str(ORDERS))
    p = mcp_server._plan_on(lambda sql: [], "csn_demo")
    assert p.csn is not None and p.keys["dsp_zi_serviceorder"][1] == csn.RULE
    monkeypatch.delenv("KRUSGRAPH_CSN")
    monkeypatch.setattr(mcp_server, "plan_from", lambda **kw: plan(csn_demo.schema()))
    assert mcp_server._plan_on(lambda sql: [], "csn_demo").csn is None


def test_nothing_here_fetches_anything():
    src = (Path(csn.__file__)).read_text(encoding="utf-8") + Path(csn_demo.__file__).read_text(encoding="utf-8")
    assert not re.search(r"\b(requests|urllib|http\.client|socket)\b", src)


# ---------------------------------------------------------------------------------------------------- the doc

def test_the_doc_states_the_measured_numbers():
    doc = DOC.read_text(encoding="utf-8")
    f = csn_demo.facts()
    assert f["summary"] in doc
    h = f["header_amounts"][0]
    assert f"{h['over_the_join']:,.0f}".replace(",", " ") in doc and f"{h['on_the_header']:,.0f}".replace(",", " ") in doc
    assert "695af09278d8a57d0fb0a441f247060eaea5daf5" in doc and "Apache-2.0" in doc


def test_nothing_claims_certification_partnership_or_endorsement():
    text = " ".join(p.read_text(encoding="utf-8") for p in (DOC, Path(csn.__file__), Path(csn_demo.__file__), FIX / "README.md"))
    for bad in ("SAP-certified", "SAP certified", "SAP-compatible", "SAP compatible", "certified by", "partner of SAP",
                "endorsed by", "SAP partner"):
        assert bad.lower() not in text.lower(), bad
    assert "not affiliated with SAP" in DOC.read_text(encoding="utf-8")
