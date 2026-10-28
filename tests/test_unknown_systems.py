"""Customer B: a first meeting with an export folder or a columns list and no idea which systems are behind them.

The names are synthetic but shaped like common business systems: Swedish (Kund, Kundnr, Orderrad, Leverantorsnr) and
English ERP exports (Customer.No, SalesHeader.DocumentNo, SellToCustomerNo). Step 1 of the demo ends with one of five
answers, never a percentage."""
import pytest

from fabric_backend.demo_app import Session, verdict
from fabric_backend.infer import plan
from fabric_backend.platforms.local import folder_source, parse_columns, pasted_source

SWEDISH = """Tabell;Kolumn;Typ
Kund;Kundnr;int
Kund;Namn;nvarchar(80)
Order;Ordernr;int
Order;Kundnr;int
Order;Orderdatum;date
Order;Ordervarde;decimal(18,2)
Orderrad;Ordernr;int
Orderrad;Radnr;int
Orderrad;Artikelnr;int
Orderrad;Radbelopp;decimal(18,2)
Artikel;Artikelnr;int
Artikel;Benamning;nvarchar(80)
Leverantor;Leverantorsnr;int
Leverantor;Namn;nvarchar(80)
Artikel;Leverantorsnr;int
"""

ENGLISH = """Customer: No, Name, City
Item: No, Description, UnitPrice
SalesHeader: DocumentNo, SellToCustomerNo, OrderDate, Amount
SalesLine: DocumentNo, LineNo, ItemNo, Quantity, LineAmount
"""


@pytest.mark.parametrize("text,expected", [
    ("Kund.Kundnr int\nKund.Namn", [("Kund", "Kundnr", "int"), ("Kund", "Namn", "")]),
    ("Kund\tKundnr\nKund\tNamn", [("Kund", "Kundnr", ""), ("Kund", "Namn", "")]),
    ("Kund: Kundnr, Namn", [("Kund", "Kundnr", ""), ("Kund", "Namn", "")]),
    ("Kund\n  Kundnr int\n  Namn\n", [("Kund", "Kundnr", "int"), ("Kund", "Namn", "")]),
    ("Table,Column,Type\nKund,Kundnr,int", [("Kund", "Kundnr", "int")]),
    ("TABLE_NAME;COLUMN_NAME\nKund;Kundnr", [("Kund", "Kundnr", "")]),
])
def test_the_shapes_a_columns_list_comes_in(text, expected):
    assert parse_columns(text) == expected


def test_swedish_business_names_give_keys_relationships_and_the_genitive():
    p = plan(pasted_source(SWEDISH).schema)
    assert p.keys["Leverantor"][0] == ["Leverantorsnr"] and p.keys["Orderrad"] == (["Ordernr", "Radnr"], "K5")
    rels = {(r.source, r.source_cols[0], r.target) for r in p.relationships}
    assert {("Order", "Kundnr", "Kund"), ("Orderrad", "Ordernr", "Order"), ("Orderrad", "Artikelnr", "Artikel"),
            ("Artikel", "Leverantorsnr", "Leverantor")} <= rels


def test_english_erp_names_with_a_bare_no_and_tables_without_a_primary_key():
    p = plan(pasted_source(ENGLISH).schema)
    assert p.keys["Customer"][0] == ["No"] and p.keys["Item"][0] == ["No"]
    assert "SalesHeader" in p.keys or "SalesHeader" in p.keyless         # either way the plan says so; it never guesses silently
    s = Session()
    s.connect("paste", ENGLISH)
    v = s.state()["verdict"]
    assert v["headline"]["state"] in ("enough", "knowledge")
    assert "%" not in str(v)


def test_a_folder_with_an_old_excel_file_an_empty_export_and_a_keyless_log(tmp_path):
    (tmp_path / "kund.csv").write_text("Kundnr;Namn\n1;Alfa\n2;Beta\n", encoding="utf-8")
    (tmp_path / "order.csv").write_text("Ordernr;Kundnr;Belopp\n10;1;100\n11;2;50\n", encoding="utf-8")
    (tmp_path / "logg.csv").write_text("Handelse;Tid\nexport;2026-10-01\n", encoding="utf-8")
    (tmp_path / "leverantor.csv").write_text("Leverantorsnr;Namn\n", encoding="utf-8")
    (tmp_path / "gammal.xls").write_bytes(b"\xd0\xcf\x11\xe0")
    src = folder_source(tmp_path)
    assert src.unsupported and "gammal.xls" in src.unsupported[0] and "xlsx" in src.unsupported[0]
    assert src.empty == ["leverantor"]
    p = plan(src.schema)
    v = verdict(src, p)
    states = {i["state"] for i in v["items"]}
    assert v["headline"]["state"] == "enough" and {"unsupported", "material", "knowledge"} <= states
    assert any("logg" in i["text"] for i in v["items"] if i["state"] == "knowledge")


def test_the_five_states():
    assert verdict(None, None, error="Error: ('28000', \"[28000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]Login failed for user 'x'. (18456)\")")["headline"]["state"] == "access"
    one = pasted_source("Kund.Kundnr\nKund.Namn")
    assert verdict(one, plan(one.schema))["headline"]["state"] == "material"                 # one table, no rows
    loose = pasted_source("Kund.Kundnr\nKund.Namn\nLogg.Handelse")
    assert verdict(loose, plan(loose.schema))["headline"]["state"] == "material"             # nothing links; no rows
    assert any(i["state"] == "knowledge" for i in verdict(loose, plan(loose.schema))["items"])
    sv = pasted_source(SWEDISH)
    assert verdict(sv, plan(sv.schema))["headline"]["state"] == "enough"
    assert set(verdict(None, None)["states"]) == {"Enough to start", "We need your knowledge about", "Missing material:",
                                                  "Missing access:", "Not supported yet:"}


def test_a_failed_connect_leaves_its_verdict_on_the_page():
    s = Session()
    with pytest.raises(FileNotFoundError):
        s.connect("folder", "/nowhere/at/all")
    assert s.state()["verdict"]["headline"]["state"] == "material"
    status, _, body = s.handle("POST", "/api/connect", b'{"kind": "paste", "value": "Kund.Kundnr\\nOrder.Ordernr\\nOrder.Kundnr"}')
    assert status == 200 and b'"enough"' in body
