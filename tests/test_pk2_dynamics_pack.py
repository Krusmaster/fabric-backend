"""Round PK2: the dynamics365 pack (fabric_backend/packs/dynamics365/, Dataverse and Business Central), the loader's
reading of their names, the synthetic demo (fabric_backend/dynamics_demo.py) with its planted traps, and the four data
products the engine drafts from it (tests/golden/pk2_dynamics_products.json)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from fabric_backend import dynamics_demo as dd, evidence, sap_pack
from fabric_backend.infer import plan
from fabric_backend.schema import Schema

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted((sap_pack.PACKS / "dynamics365").glob("*.json"))
DATAVERSE = {"ACCOUNT", "CONTACT", "LEAD", "OPPORTUNITY", "OPPORTUNITYPRODUCT", "QUOTE", "QUOTEDETAIL", "SALESORDER", "SALESORDERDETAIL",
             "INVOICE", "INVOICEDETAIL", "PRODUCT", "PRICELEVEL", "PRODUCTPRICELEVEL", "INCIDENT", "SYSTEMUSER", "TEAM", "BUSINESSUNIT",
             "TRANSACTIONCURRENCY", "ACTIVITYPOINTER"}
BC = {"CUSTOMER", "VENDOR", "ITEM", "SALESPERSON_PURCHASER", "COUNTRY_REGION", "SALES_HEADER", "SALES_LINE", "SALES_INVOICE_HEADER",
      "SALES_INVOICE_LINE", "PURCHASE_HEADER", "PURCHASE_LINE", "G_L_ENTRY", "CUST_LEDGER_ENTRY", "DETAILED_CUST_LEDG_ENTRY",
      "ITEM_LEDGER_ENTRY", "VALUE_ENTRY", "DIMENSION_SET_ENTRY"}


@pytest.fixture(scope="module")
def run():
    schema, execute = dd.sqlite()
    p = plan(schema)
    return schema, execute, p, evidence.validate(p, execute, max_items=500)


def _schema(tables: dict[str, list[str]]) -> Schema:
    info = [("dbo", t, c, "nvarchar", i) for t, cols in tables.items() for i, c in enumerate(cols, 1)]
    return Schema.from_information_schema(info, schema="dbo")


# ---------------------------------------------------------------- the pack's files

def test_two_modules_with_the_tables_the_round_asked_for():
    assert [f.stem for f in FILES] == ["business_central", "dataverse"]
    p = sap_pack.load("dynamics365")
    assert sap_pack.problems(p) == [] and p["rule"] == "Dynamics 365 pack"
    by = {m: {n for n, t in p["tables"].items() if t["module"] == m} for m in ("dataverse", "business_central")}
    assert by == {"dataverse": DATAVERSE, "business_central": BC}


def test_dataverse_keys_are_the_guid_id_columns_and_bc_keys_the_documented_ones():
    t = sap_pack.load("dynamics365")["tables"]
    for n in DATAVERSE:
        assert t[n]["key"] == (["ACTIVITYID"] if n == "ACTIVITYPOINTER" else [n + "ID"]), n
    assert t["SALES_HEADER"]["key"] == ["COMPANY", "DOCUMENT_TYPE", "NO"]
    assert t["SALES_LINE"]["key"] == ["COMPANY", "DOCUMENT_TYPE", "DOCUMENT_NO", "LINE_NO"]
    assert t["SALES_INVOICE_LINE"]["key"] == ["COMPANY", "DOCUMENT_NO", "LINE_NO"]
    assert t["DIMENSION_SET_ENTRY"]["key"] == ["COMPANY", "DIMENSION_SET_ID", "DIMENSION_CODE"]
    assert all(t[n]["key"][0] == "COMPANY" for n in BC) and "COMPANY" in sap_pack.CLIENT_COLUMNS


def test_every_source_was_opened_and_says_when_and_its_page_date():
    p = sap_pack.load("dynamics365")
    for sid, s in p["sources"].items():
        assert s["fetched"] is True and "Read 17 November 2026" in s["note"], sid
        assert s["url"].startswith(("https://learn.microsoft.com/", "https://github.com/microsoft/")), sid
        if s["url"].startswith("https://learn.microsoft.com/"):
            assert re.search(r"ms\.date 20\d\d-\d\d-\d\d", s["note"]), sid
    # what the pages do not say is said, not hidden
    assert "does not say how lookup columns are named" in p["sources"]["fabric_link"]["note"]
    assert "do not say how entities and columns are named" in p["sources"]["bc_fabric_mirroring"]["note"]
    assert "not Learn" in p["sources"]["bcapps_source"]["note"]


def test_where_the_amounts_live_and_the_doubled_total_trap():
    t = sap_pack.load("dynamics365")["tables"]
    lvl = lambda n: {a["column"]: a["level"] for a in t[n].get("amounts", [])}
    assert lvl("OPPORTUNITY")["ESTIMATEDVALUE"] == "header" and lvl("OPPORTUNITYPRODUCT")["EXTENDEDAMOUNT"] == "item"
    assert lvl("SALESORDER")["TOTALAMOUNT"] == "header" and lvl("SALESORDERDETAIL")["EXTENDEDAMOUNT"] == "item"
    assert "AMOUNT" not in lvl("SALES_HEADER") and "AMOUNT" not in lvl("CUST_LEDGER_ENTRY")      # FlowFields: not stored
    traps = {x["id"]: x for x in sap_pack.load("dynamics365")["traps"]}
    assert {"dv_doubled_totals", "dv_soft_delete", "dv_polymorphic_lookups", "bc_flowfield_totals", "bc_company_scope"} <= set(traps)


def test_polymorphic_lookups_are_filtered_never_plain_key_joins():
    rels = sap_pack.load("dynamics365")["relationships"]
    poly = [r for r in rels if r["source_cols"] in (["CUSTOMERID"], ["OWNERID"], ["REGARDINGOBJECTID"], ["PARENTCUSTOMERID"])]
    assert poly and all(r.get("where") and r["where"][0]["side"] == "source" for r in poly)
    regarding = {r["target"] for r in poly if r["source"] == "ACTIVITYPOINTER" and r["source_cols"] == ["REGARDINGOBJECTID"]}
    assert {"ACCOUNT", "CONTACT", "OPPORTUNITY", "INCIDENT", "SALESORDER"} <= regarding
    line_items = [r for r in rels if r["source"] in ("SALES_LINE", "PURCHASE_LINE", "SALES_INVOICE_LINE") and r["target"] == "ITEM"]
    assert len(line_items) == 3 and all(r["where"][0]["column"] == "TYPE" and "2" in r["where"][0]["in"] for r in line_items)


# ---------------------------------------------------------------- the loader reads the landings

def test_the_loader_reads_business_central_and_web_api_spellings():
    assert sap_pack.table_name("Example AB$Cust_ Ledger Entry$437dbf0e-84ff-417a-965d-ed2bb9650972") == "CUST_LEDGER_ENTRY"
    assert sap_pack.table_name("dbo.Demo Inc.$Sales Header$437dbf0e") == "SALES_HEADER"
    assert sap_pack.table_name("SalesHeader-36") == "SALESHEADER" and sap_pack.pack_table("SalesHeader-36", "dynamics365") == "SALES_HEADER"
    assert sap_pack.table_name("bronze.SAP_VBAK") == "VBAK" and sap_pack.table_name("younium_invoices") == "INVOICES"   # unchanged
    assert sap_pack.column_key("_parentaccountid_value") == "PARENTACCOUNTID" == sap_pack.column_key("parentaccountid")
    assert sap_pack.column_key("DocumentNo-3") == "DOCUMENTNO" == sap_pack.column_key("Document No_") == sap_pack.column_key("DOCUMENT_NO")
    web = _schema({"account": ["accountid", "name", "_parentaccountid_value", "_primarycontactid_value"],
                   "contact": ["contactid", "fullname"], "systemuser": ["systemuserid", "_businessunitid_value"],
                   "businessunit": ["businessunitid"]})
    m = sap_pack.match(web, "dynamics365")
    got = {(r["source"], tuple(r["source_cols"]), r["target"]) for r in m.relationships}
    assert ("account", ("_parentaccountid_value",), "account") in got and ("account", ("_primarycontactid_value",), "contact") in got
    assert ("systemuser", ("_businessunitid_value",), "businessunit") in got


def test_sql_per_company_tables_drop_the_company_from_keys():
    sql = _schema({"CRONUS$Sales Header$437dbf0e": ["Document Type", "No_", "Sell-to Customer No_"],
                   "CRONUS$Sales Line$437dbf0e": ["Document Type", "Document No_", "Line No_", "Type", "No_"],
                   "CRONUS$Customer$437dbf0e": ["No_", "Name"]})
    m = sap_pack.match_any(sql)
    assert m is not None and m.pack == "dynamics365" and sorted(m.client_dropped) == sorted(m.tables)
    assert m.keys["CRONUS$Sales Line$437dbf0e"] == ["Document Type", "Document No_", "Line No_"]
    assert any(r["source"] == "CRONUS$Sales Line$437dbf0e" and r["target"] == "CRONUS$Sales Header$437dbf0e" for r in m.relationships)


def test_ordinary_names_alone_do_not_light_the_pack():
    plain = _schema({"account": ["accountid", "name"], "contact": ["contactid", "parentcustomerid"], "product": ["productid", "name"],
                     "invoice": ["invoiceid", "accountid"]})
    assert sap_pack.match(plain, "dynamics365") is not None                      # asked by name it reads them
    m = sap_pack.match_any(plain)
    assert m is None or m.pack != "dynamics365"                                   # but they alone are not Dynamics 365


# ---------------------------------------------------------------- the demo and its planted traps

def test_the_demo_is_labelled_synthetic_and_recognised_whole(run):
    schema, _x, p, v = run
    assert len(dd.tables()) == dd.EXPECTED["tables"] == 33 and sum(len(r) for *_x2, r in dd.tables().values()) == 109
    assert sum(1 for n in dd.tables() if dd.module_of(n) == "dataverse") == dd.EXPECTED["dataverse_tables"]
    assert "SYNTHETIC DEMO DATA" in (ROOT / "fabric_backend" / "dynamics_demo.py").read_text(encoding="utf-8")
    assert p.pack["pack"] == "dynamics365" and len(p.pack["tables"]) == 33
    assert v["summary"] == "33 of 33 keys unique, 81 of 89 relationships hold without orphans"


def test_the_planted_traps_are_found(run):
    schema, execute, p, v = run
    orphans = {(r["source"], r["target"]): r["orphans"] for r in v["relationships"] if r.get("orphans")}
    assert orphans == {("activitypointer", "account"): 1} and set(orphans) == set(dd.EXPECTED["orphans"])
    found = {(f["header"], f["line"]): f for f in v["amount_levels"]["findings"]}
    for header, line, col in dd.EXPECTED["doubled"]:
        f = found[(header, line)]
        assert col in f["amount_columns"] and f["rows_per_header"]["max_lines"] == dd.EXPECTED["max_lines"][(header, line)]
    q = lambda sql: execute(sql)[0]["n"]
    assert q("SELECT COUNT(*) AS n FROM [dynamics].[salesorderdetail] WHERE IsDelete = 1") == 1
    assert q("SELECT SUM(extendedamount_base) AS n FROM [dynamics].[salesorderdetail] WHERE IsDelete = 0") == dd.EXPECTED["order_lines_base"]
    assert q("SELECT SUM(d.extendedamount) AS n FROM [dynamics].[salesorderdetail] d JOIN [dynamics].[salesorder] o ON o.salesorderid = d.salesorderid "
             "WHERE d.IsDelete = 0 AND o.transactioncurrencyid = '" + dd.SEK + "'") == dd.EXPECTED["order_lines_sek"]
    # the total that doubles: the header amount summed over the lines
    assert q("SELECT SUM(o.totalamount) AS n FROM [dynamics].[salesorder] o JOIN [dynamics].[salesorderdetail] d ON d.salesorderid = o.salesorderid "
             "WHERE o.name = 'SO-1001'") == 3 * 150000
    assert q("SELECT COUNT(*) AS n FROM [dynamics].[contact] WHERE parentcustomeridtype = 'contact'") == dd.EXPECTED["contact_parent_contact"]


def test_business_central_company_document_type_and_dimension_traps(run):
    _s, execute, _p, v = run
    q = lambda sql: execute(sql)[0]["n"]
    for t in dd.EXPECTED["bc_not_unique_without_company"]:
        assert q(f"SELECT COUNT(*) - COUNT(DISTINCT [No-{ {'Customer-18': 1, 'Item-27': 1, 'SalesInvoiceHeader-112': 3}[t] }]) AS n FROM [dynamics].[{t}]") >= 1, t
    keys = {k["table"]: k for k in v["keys"]}
    assert all(str(keys[t]["verdict"]).startswith("unique") for t in dd.EXPECTED["bc_not_unique_without_company"])   # with $Company
    assert q("SELECT COUNT(*) AS n FROM [dynamics].[SalesHeader-36] WHERE [$Company] = 'Demo Company A' AND [No-3] = '1001'") == 2
    assert q("SELECT COUNT(*) AS n FROM [dynamics].[DimensionSetEntry-480] WHERE [DimensionSetID-1] = 1") == dd.EXPECTED["bc_dimension_rows_per_entry"]
    assert q("SELECT SUM([Amount-17]) AS n FROM [dynamics].[GLEntry-17] WHERE [GLAccountNo-3] = '6110'") == dd.EXPECTED["bc_gl_revenue_103001"]


def test_the_csv_export_writes_every_table_and_says_synthetic(tmp_path):
    files = dd.write_csv(tmp_path)
    assert len([f for f in files if f.suffix == ".csv"]) == 33 and (tmp_path / "SalesHeader_36.csv").exists()
    assert "SYNTHETIC DEMO DATA" in (tmp_path / "README.txt").read_text() and "SYNTHETIC DEMO DATA" in (tmp_path / "load_dynamics_demo.py").read_text()


# ---------------------------------------------------------------- the data products, from the engine

def test_the_four_data_products_are_what_the_engine_computes():
    golden = json.loads((ROOT / "tests" / "golden" / "pk2_dynamics_products.json").read_text(encoding="utf-8"))
    golden.pop("_about")
    assert json.loads(json.dumps(dd.products())) == golden
    assert list(golden) == ["lead_to_cash", "order_to_cash", "customer_360", "service_cases"]
    l2c = golden["lead_to_cash"]
    assert "salesorder.totalamount over salesorderdetail" in l2c["doubled_amounts"]
    assert "opportunity.estimatedvalue over opportunityproduct" in l2c["doubled_amounts"]
    assert all(g["pack"] == "dynamics365" and g["keys"]["unique"] == g["keys"]["total"] for g in golden.values())


# ---------------------------------------------------------------- words

def test_no_certification_partnership_or_endorsement_claims():
    texts = [f.read_text(encoding="utf-8") for f in FILES] + [(ROOT / "fabric_backend" / "dynamics_demo.py").read_text(encoding="utf-8"),
                                                              (ROOT / "docs" / "DYNAMICS365.md").read_text(encoding="utf-8"),
                                                              (sap_pack.PACKS / "dynamics365" / "manifest.yaml").read_text(encoding="utf-8")]
    for text in texts:
        low = text.lower()
        for word in ("certified", "certification", "partner of microsoft", "microsoft partner", "endorsed", "approved by microsoft",
                     "official microsoft", "seamless", "best-in-class", "ai-powered"):
            assert word not in low, word
    doc = (ROOT / "docs" / "DYNAMICS365.md").read_text(encoding="utf-8")
    assert "independent and not affiliated with Microsoft" in doc and "SYNTHETIC DEMO DATA" in doc
