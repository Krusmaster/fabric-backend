"""Synthetic Dynamics 365 tables with rows, for running the dynamics365 pack's checks end to end (round PK2).

SYNTHETIC DEMO DATA. Every value is made up: accounts "Demo Account 1" to "Demo Account 4", companies "Demo Company A" and
"Demo Company B", e-mail addresses at example.invalid, ids that only look like GUIDs. Nothing comes from a Dataverse
environment, a Business Central company or a customer. The rows are written from the pack, so a run on them shows that
the tools work on tables of these shapes, never that the pack is right about Dynamics 365 (docs/DYNAMICS365.md says
what was verified, and where). Krusgraph is independent and not affiliated with Microsoft.

Two shapes, as the pack's sources describe them:
- Dataverse (Sales and Customer Service), as Link to Microsoft Fabric lands it: one table per logical name (account,
  salesorderdetail), logical column names, lookups as their logical name (parentaccountid), the system columns Id,
  IsDelete, SinkCreatedOn and versionnumber. 20 tables.
- Business Central, as bc2adls exports it: <Table>-<id> tables and <Field>-<id> columns of letters and digits
  (SalesHeader-36, SelltoCustomerNo-2) with a $Company column; two companies. Field numbers are the base application's.
  13 tables.

The traps are planted, and EXPECTED says what each check should find:
- order SO-1001 has three lines: salesorder.totalamount summed over its lines comes out three times too large; the
  same for opportunity.estimatedvalue over opportunityproduct and Business Central's posted invoice over its lines
  is not possible (its Amount is a FlowField and is not in the export);
- one order line is soft-deleted (IsDelete true, empty body): counting lines without the filter counts it;
- one contact's parentcustomerid is another contact (parentcustomeridtype contact): a plain join to account finds
  nothing for it, the filtered relationship of the pack does;
- SO-1003 is in EUR, the others in SEK: extendedamount across orders adds currencies, extendedamount_base does not;
- activity "Demo call 2" is regarding an account that is no longer in the lake (deleted and purged): one orphan of
  activitypointer.regardingobjectid -> account, where regardingobjecttypecode is account;
- Business Central: customer C10000, item 1000 and order 1001 exist in both companies, and order 1001 and quote 1001
  in one: keys without $Company and Document Type are not unique; a sales line of type G/L Account carries an account
  number in No.; a ledger entry's dimension set has two dimensions.

    tables()                -> {landing name: (columns, types, rows)}
    sqlite()                -> (Schema, execute) over the rows in SQLite (schema "dynamics"), as the tests use them
    write_csv(folder)       -> one CSV per table, _types.json, and a PySpark notebook that loads them
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

PACK = "dynamics365"
DEMO_WHERE = "synthetic Dynamics 365 demo"          # what a run on these tables is; never a verification
SYNTHETIC = "SYNTHETIC DEMO DATA: made up for Krusgraph's tests and demos; not from any Dynamics 365 environment or company"
_D = "decimal(15,2)"
_I = "int"
SINK = "2026-11-01T06:00:00Z"
A, B = "Demo Company A", "Demo Company B"


def _guid(prefix: str, n: int) -> str:
    return f"{prefix}000000-0000-4000-8000-{n:012d}"


def _dv(cols: list[str], rows: list[tuple], decimals: tuple[str, ...] = (), ints: tuple[str, ...] = ()):
    """A Dataverse table as Link to Microsoft Fabric lands it: Id (the record's GUID), the columns, IsDelete,
    SinkCreatedOn, versionnumber."""
    allc = ["Id"] + cols + ["IsDelete", "SinkCreatedOn", "versionnumber"]
    out = []
    for i, r in enumerate(rows, 1):
        deleted = r[-1] == "__deleted__"
        body = r[:-1] if deleted else r
        if deleted:                                    # a soft delete: the id stays, the body is empty
            out.append((body[0], body[0]) + (None,) * (len(cols) - 1) + (1, SINK, 1000 + i))
        else:
            out.append((body[0],) + tuple(body) + (0, SINK, 1000 + i))
    kinds = [_D if c in decimals else _I if c in ints + ("IsDelete", "versionnumber") else "string" for c in allc]
    return allc, kinds, out


ACC = [_guid("a1", n) for n in range(1, 5)]
CON = [_guid("c2", n) for n in range(1, 5)]
LEA = [_guid("1e", n) for n in range(1, 4)]
OPP = [_guid("0b", n) for n in range(1, 4)]
OPR = [_guid("0c", n) for n in range(1, 6)]
QUO = [_guid("9a", n) for n in range(1, 3)]
QDT = [_guid("9b", n) for n in range(1, 5)]
SOR = [_guid("50", n) for n in range(1, 4)]
SOD = [_guid("51", n) for n in range(1, 8)]
INV = [_guid("1a", n) for n in range(1, 3)]
IND = [_guid("1b", n) for n in range(1, 5)]
PRD = [_guid("e1", n) for n in range(1, 4)]
PRL = [_guid("e2", n) for n in range(1, 3)]
PPL = [_guid("e3", n) for n in range(1, 5)]
CAS = [_guid("ca", n) for n in range(1, 4)]
USR = [_guid("5e", n) for n in range(1, 3)]
TEA = [_guid("7e", 1)]
BU = [_guid("b0", 1)]
CUR = [_guid("cc", n) for n in range(1, 3)]       # SEK, EUR
ACT = [_guid("ac", n) for n in range(1, 7)]
PURGED = _guid("a1", 9)                            # an account deleted and purged from the lake; an activity still names it
SEK, EUR = CUR


def _dataverse() -> dict:
    return {
        "transactioncurrency": _dv(["transactioncurrencyid", "isocurrencycode", "currencyname", "exchangerate"], [
            (SEK, "SEK", "Swedish krona", 1), (EUR, "EUR", "Euro", 0.09)], ("exchangerate",)),
        "businessunit": _dv(["businessunitid", "name", "parentbusinessunitid"], [(BU[0], "Demo Business Unit", None)]),
        "systemuser": _dv(["systemuserid", "fullname", "internalemailaddress", "businessunitid", "parentsystemuserid"], [
            (USR[0], "Demo User 1", "user1@demo.example.invalid", BU[0], None),
            (USR[1], "Demo User 2", "user2@demo.example.invalid", BU[0], USR[0])]),
        "team": _dv(["teamid", "name", "businessunitid"], [(TEA[0], "Demo Service Team", BU[0])]),
        "account": _dv(["accountid", "name", "parentaccountid", "primarycontactid", "transactioncurrencyid", "ownerid", "owneridtype", "owningbusinessunit"], [
            (ACC[0], "Demo Account 1", None, CON[0], SEK, USR[0], "systemuser", BU[0]),
            (ACC[1], "Demo Account 2", ACC[0], CON[2], SEK, USR[1], "systemuser", BU[0]),
            (ACC[2], "Demo Account 3", None, None, EUR, TEA[0], "team", BU[0]),
            (ACC[3], "Demo Account 4", None, None, SEK, USR[0], "systemuser", BU[0])]),
        "contact": _dv(["contactid", "fullname", "emailaddress1", "parentcustomerid", "parentcustomeridtype"], [
            (CON[0], "Demo Person 1", "person1@account1.example.invalid", ACC[0], "account"),
            (CON[1], "Demo Person 2", "person2@account1.example.invalid", ACC[0], "account"),
            (CON[2], "Demo Person 3", "person3@account2.example.invalid", ACC[1], "account"),
            (CON[3], "Demo Person 4", "person4@example.invalid", CON[0], "contact")]),            # planted: a contact's parent is a contact
        "lead": _dv(["leadid", "fullname", "parentaccountid", "qualifyingopportunityid", "estimatedamount", "transactioncurrencyid"], [
            (LEA[0], "Demo Lead 1", ACC[0], OPP[0], 150000, SEK),
            (LEA[1], "Demo Lead 2", ACC[2], OPP[2], 20000, EUR),
            (LEA[2], "Demo Lead 3", None, None, 5000, SEK)], ("estimatedamount",)),
        "pricelevel": _dv(["pricelevelid", "name", "transactioncurrencyid"], [(PRL[0], "Demo Price List SEK", SEK), (PRL[1], "Demo Price List EUR", EUR)]),
        "product": _dv(["productid", "name", "pricelevelid", "parentproductid"], [
            (PRD[0], "Demo Platform", PRL[0], None), (PRD[1], "Demo Add-on", PRL[0], PRD[0]), (PRD[2], "Demo Service Day", PRL[0], None)]),
        "productpricelevel": _dv(["productpricelevelid", "pricelevelid", "productid", "amount"], [
            (PPL[0], PRL[0], PRD[0], 40000), (PPL[1], PRL[0], PRD[1], 5000), (PPL[2], PRL[0], PRD[2], 10000), (PPL[3], PRL[1], PRD[0], 3600)], ("amount",)),
        "opportunity": _dv(["opportunityid", "name", "parentaccountid", "customerid", "customeridtype", "originatingleadid", "pricelevelid",
                            "transactioncurrencyid", "estimatedvalue", "totalamount", "ownerid", "owneridtype"], [
            (OPP[0], "Demo Account 1 - platform", ACC[0], ACC[0], "account", LEA[0], PRL[0], SEK, 150000, 150000, USR[0], "systemuser"),  # three products
            (OPP[1], "Demo Account 2 - add-on", ACC[1], ACC[1], "account", None, PRL[0], SEK, 10000, 10000, USR[1], "systemuser"),
            (OPP[2], "Demo Account 3 - platform", ACC[2], ACC[2], "account", LEA[1], PRL[1], EUR, 18000, 18000, TEA[0], "team")],
            ("estimatedvalue", "totalamount")),
        "opportunityproduct": _dv(["opportunityproductid", "opportunityid", "productid", "quantity", "priceperunit", "baseamount", "extendedamount",
                                   "transactioncurrencyid"], [
            (OPR[0], OPP[0], PRD[0], 3, 40000, 120000, 120000, SEK),
            (OPR[1], OPP[0], PRD[1], 2, 5000, 10000, 10000, SEK),
            (OPR[2], OPP[0], PRD[2], 2, 10000, 20000, 20000, SEK),
            (OPR[3], OPP[1], PRD[1], 2, 5000, 10000, 10000, SEK),
            (OPR[4], OPP[2], PRD[0], 5, 3600, 18000, 18000, EUR)], ("priceperunit", "baseamount", "extendedamount"), ("quantity",)),
        "quote": _dv(["quoteid", "name", "opportunityid", "customerid", "customeridtype", "pricelevelid", "transactioncurrencyid", "totalamount"], [
            (QUO[0], "QUO-1001", OPP[0], ACC[0], "account", PRL[0], SEK, 150000),
            (QUO[1], "QUO-1002", OPP[1], ACC[1], "account", PRL[0], SEK, 10000)], ("totalamount",)),
        "quotedetail": _dv(["quotedetailid", "quoteid", "productid", "quantity", "extendedamount", "transactioncurrencyid"], [
            (QDT[0], QUO[0], PRD[0], 3, 120000, SEK), (QDT[1], QUO[0], PRD[1], 2, 10000, SEK), (QDT[2], QUO[0], PRD[2], 2, 20000, SEK),
            (QDT[3], QUO[1], PRD[1], 2, 10000, SEK)], ("extendedamount",), ("quantity",)),
        "salesorder": _dv(["salesorderid", "name", "quoteid", "opportunityid", "customerid", "customeridtype", "pricelevelid", "transactioncurrencyid",
                           "totallineitemamount", "totalamount", "totalamount_base", "exchangerate", "ownerid", "owneridtype"], [
            (SOR[0], "SO-1001", QUO[0], OPP[0], ACC[0], "account", PRL[0], SEK, 150000, 150000, 150000, 1, USR[0], "systemuser"),   # three lines
            (SOR[1], "SO-1002", QUO[1], OPP[1], ACC[1], "account", PRL[0], SEK, 10000, 10000, 10000, 1, USR[1], "systemuser"),
            (SOR[2], "SO-1003", None, OPP[2], CON[3], "contact", PRL[1], EUR, 18000, 18000, 200000, 0.09, TEA[0], "team")],          # EUR, a contact
            ("totallineitemamount", "totalamount", "totalamount_base", "exchangerate")),
        "salesorderdetail": _dv(["salesorderdetailid", "salesorderid", "productid", "quotedetailid", "quantity", "priceperunit", "extendedamount",
                                 "extendedamount_base", "transactioncurrencyid"], [
            (SOD[0], SOR[0], PRD[0], QDT[0], 3, 40000, 120000, 120000, SEK),
            (SOD[1], SOR[0], PRD[1], QDT[1], 2, 5000, 10000, 10000, SEK),
            (SOD[2], SOR[0], PRD[2], QDT[2], 2, 10000, 20000, 20000, SEK),
            (SOD[3], SOR[1], PRD[1], QDT[3], 2, 5000, 10000, 10000, SEK),
            (SOD[4], SOR[2], PRD[0], None, 5, 3600, 18000, 200000, EUR),
            (SOD[5], SOR[2], None, None, 1, 0, 0, 0, EUR),                                                  # a write-in line: no product
            (SOD[6], "__deleted__")], ("priceperunit", "extendedamount", "extendedamount_base"), ("quantity",)),   # planted: soft-deleted
        "invoice": _dv(["invoiceid", "name", "salesorderid", "opportunityid", "customerid", "customeridtype", "transactioncurrencyid", "totalamount"], [
            (INV[0], "INV-1001", SOR[0], OPP[0], ACC[0], "account", SEK, 150000),
            (INV[1], "INV-1002", SOR[1], OPP[1], ACC[1], "account", SEK, 10000)], ("totalamount",)),
        "invoicedetail": _dv(["invoicedetailid", "invoiceid", "productid", "salesorderdetailid", "quantity", "extendedamount", "transactioncurrencyid"], [
            (IND[0], INV[0], PRD[0], SOD[0], 3, 120000, SEK), (IND[1], INV[0], PRD[1], SOD[1], 2, 10000, SEK),
            (IND[2], INV[0], PRD[2], SOD[2], 2, 20000, SEK), (IND[3], INV[1], PRD[1], SOD[3], 2, 10000, SEK)], ("extendedamount",), ("quantity",)),
        "incident": _dv(["incidentid", "title", "customerid", "customeridtype", "primarycontactid", "productid", "parentcaseid", "ownerid", "owneridtype"], [
            (CAS[0], "Demo case 1: login fails", ACC[0], "account", CON[0], PRD[0], None, TEA[0], "team"),
            (CAS[1], "Demo case 2: login fails again", ACC[0], "account", CON[1], PRD[0], CAS[0], TEA[0], "team"),
            (CAS[2], "Demo case 3: invoice question", CON[3], "contact", CON[3], None, None, USR[1], "systemuser")]),
        "activitypointer": _dv(["activityid", "subject", "activitytypecode", "regardingobjectid", "regardingobjecttypecode", "ownerid", "owneridtype"], [
            (ACT[0], "Demo call 1", "phonecall", ACC[0], "account", USR[0], "systemuser"),
            (ACT[1], "Demo e-mail 1", "email", OPP[0], "opportunity", USR[0], "systemuser"),
            (ACT[2], "Demo task 1", "task", CAS[0], "incident", TEA[0], "team"),
            (ACT[3], "Demo e-mail 2", "email", CON[3], "contact", USR[1], "systemuser"),
            (ACT[4], "Demo appointment 1", "appointment", SOR[2], "salesorder", USR[1], "systemuser"),
            (ACT[5], "Demo call 2", "phonecall", PURGED, "account", USR[0], "systemuser")]),               # planted: an orphan
    }


def _bc(table: str, fields: list[tuple[str, int]], rows: list[tuple], decimals: tuple[str, ...] = (), ints: tuple[str, ...] = ()):
    """A Business Central table as bc2adls names it: $Company first, then <Field>-<id> (letters and digits only)."""
    cols = ["$Company"] + [f"{n}-{i}" for n, i in fields]
    kinds = ["string"] + [_D if n in decimals else _I if n in ints else "string" for n, _ in fields]
    return cols, kinds, rows


def _business_central() -> dict:
    amt = ("Amount", "AmountIncludingVAT", "LineAmount", "UnitPrice")
    return {
        "Customer-18": _bc("Customer", [("No", 1), ("Name", 2), ("SalespersonCode", 29), ("CountryRegionCode", 35), ("CurrencyCode", 22)], [
            (A, "C10000", "Demo Customer 1", "AH", "SE", ""), (A, "C20000", "Demo Customer 2", "JR", "FI", "EUR"),
            (A, "C30000", "Demo Customer 3", "AH", "SE", ""),
            (B, "C10000", "Demo Customer 4", "AH", "SE", "")]),                                     # the same number in company B
        "Vendor-23": _bc("Vendor", [("No", 1), ("Name", 2), ("PurchaserCode", 29), ("CountryRegionCode", 35)], [
            (A, "V10000", "Demo Vendor 1", "JR", "SE"), (B, "V10000", "Demo Vendor 2", "AH", "SE")]),
        "Item-27": _bc("Item", [("No", 1), ("Description", 3), ("UnitPrice", 18)], [
            (A, "1000", "Demo Item 1", 100), (A, "1100", "Demo Item 2", 250), (A, "1200", "Demo Item 3", 40), (B, "1000", "Demo Item 4", 90)],
            ("UnitPrice",)),
        "SalespersonPurchaser-13": _bc("Salesperson/Purchaser", [("Code", 1), ("Name", 2)], [
            (A, "AH", "Demo Seller 1"), (A, "JR", "Demo Seller 2"), (B, "AH", "Demo Seller 3")]),
        "CountryRegion-9": _bc("Country/Region", [("Code", 1), ("Name", 2)], [(A, "SE", "Sweden"), (A, "FI", "Finland"), (B, "SE", "Sweden")]),
        "SalesHeader-36": _bc("Sales Header", [("DocumentType", 1), ("SelltoCustomerNo", 2), ("No", 3), ("BilltoCustomerNo", 4), ("OrderDate", 19),
                                               ("CurrencyCode", 32), ("SalespersonCode", 43), ("DimensionSetID", 480)], [
            (A, "1", "C10000", "1001", "C10000", "2026-10-02", "", "AH", 1),          # an order
            (A, "0", "C20000", "1001", "C20000", "2026-10-05", "EUR", "JR", 0),       # a quote with the same No.
            (B, "1", "C10000", "1001", "C10000", "2026-10-03", "", "AH", 0)], ints=("DimensionSetID",)),   # company B's order 1001
        "SalesLine-37": _bc("Sales Line", [("DocumentType", 1), ("DocumentNo", 3), ("LineNo", 4), ("Type", 5), ("No", 6), ("Quantity", 15),
                                           ("UnitPrice", 22), ("Amount", 29), ("AmountIncludingVAT", 30), ("LineAmount", 103)], [
            (A, "1", "1001", 10000, "2", "1000", 5, 100, 500, 625, 500),
            (A, "1", "1001", 20000, "2", "1100", 2, 250, 500, 625, 500),
            (A, "1", "1001", 30000, "1", "6110", 1, 80, 80, 100, 80),                 # a G/L account line: No. is not an item
            (A, "0", "1001", 10000, "2", "1200", 10, 40, 400, 500, 400),
            (B, "1", "1001", 10000, "2", "1000", 3, 90, 270, 337.5, 270)], amt, ("LineNo", "Quantity")),
        "SalesInvoiceHeader-112": _bc("Sales Invoice Header", [("SelltoCustomerNo", 2), ("No", 3), ("BilltoCustomerNo", 4), ("PostingDate", 20),
                                                              ("SalespersonCode", 43), ("OrderNo", 44)], [
            (A, "C10000", "103001", "C10000", "2026-10-10", "AH", "1001"),
            (A, "C30000", "103002", "C30000", "2026-10-12", "AH", ""),
            (B, "C10000", "103001", "C10000", "2026-10-11", "AH", "1001")]),
        "SalesInvoiceLine-113": _bc("Sales Invoice Line", [("DocumentNo", 3), ("LineNo", 4), ("Type", 5), ("No", 6), ("Quantity", 15),
                                                          ("Amount", 29), ("AmountIncludingVAT", 30), ("LineAmount", 103)], [
            (A, "103001", 10000, "2", "1000", 5, 500, 625, 500), (A, "103001", 20000, "2", "1100", 2, 500, 625, 500),
            (A, "103001", 30000, "1", "6110", 1, 80, 100, 80),
            (A, "103002", 10000, "2", "1200", 4, 160, 200, 160),
            (B, "103001", 10000, "2", "1000", 3, 270, 337.5, 270)], amt, ("LineNo", "Quantity")),
        "CustLedgerEntry-21": _bc("Cust. Ledger Entry", [("EntryNo", 1), ("CustomerNo", 3), ("PostingDate", 4), ("DocumentNo", 6), ("SalesLCY", 18),
                                                        ("DimensionSetID", 480)], [
            (A, 1, "C10000", "2026-10-10", "103001", 1080, 1), (A, 2, "C30000", "2026-10-12", "103002", 160, 0),
            (B, 1, "C10000", "2026-10-11", "103001", 270, 0)], ("SalesLCY",), ("EntryNo", "DimensionSetID")),
        "DetailedCustLedgEntry-379": _bc("Detailed Cust. Ledg. Entry", [("EntryNo", 1), ("CustLedgerEntryNo", 2), ("EntryType", 3), ("PostingDate", 4),
                                                                       ("Amount", 7), ("AmountLCY", 8), ("CustomerNo", 9)], [
            (A, 1, 1, "1", "2026-10-10", 1350, 1350, "C10000"),          # initial entry: the invoice incl. VAT
            (A, 2, 1, "2", "2026-10-30", -1350, -1350, "C10000"),        # application: paid
            (A, 3, 2, "1", "2026-10-12", 200, 200, "C30000"),
            (B, 1, 1, "1", "2026-10-11", 337.5, 337.5, "C10000")], ("Amount", "AmountLCY"), ("EntryNo", "CustLedgerEntryNo")),
        "GLEntry-17": _bc("G/L Entry", [("EntryNo", 1), ("GLAccountNo", 3), ("PostingDate", 4), ("DocumentNo", 6), ("Amount", 17), ("SourceType", 57),
                                        ("SourceNo", 58), ("DimensionSetID", 480)], [
            (A, 1, "2310", "2026-10-10", "103001", 1350, "1", "C10000", 1),     # receivables (debit)
            (A, 2, "6110", "2026-10-10", "103001", -1080, "1", "C10000", 1),    # revenue (credit: negative)
            (A, 3, "5610", "2026-10-10", "103001", -270, "1", "C10000", 1)],    # VAT
            ("Amount",), ("EntryNo", "DimensionSetID")),
        "DimensionSetEntry-480": _bc("Dimension Set Entry", [("DimensionSetID", 1), ("DimensionCode", 2), ("DimensionValueCode", 3)], [
            (A, 1, "DEPARTMENT", "SALES"), (A, 1, "PROJECT", "DEMO")], ints=("DimensionSetID",)),    # two dimensions in set 1
    }


def tables() -> dict[str, tuple[list[str], list[str], list[tuple]]]:
    return {**_dataverse(), **_business_central()}


def module_of(name: str) -> str:
    return "business_central" if "-" in name else "dataverse"


# What the checks should find on these rows; the tests compare.
EXPECTED = {
    "tables": 33,
    "dataverse_tables": 20,
    "business_central_tables": 13,
    "rows": None,                                         # computed by the tests from tables(); written in docs/DYNAMICS365.md
    "doubled": [("salesorder", "salesorderdetail", "totalamount"), ("opportunity", "opportunityproduct", "estimatedvalue")],
    "max_lines": {("salesorder", "salesorderdetail"): 3, ("opportunity", "opportunityproduct"): 3},
    "soft_deleted": {"salesorderdetail": 1},
    "order_lines_sek": 160000,                            # extendedamount of SO-1001 and SO-1002 (SEK)
    "order_lines_base": 360000,                           # extendedamount_base of every live line
    "contact_parent_contact": 1,
    "orphans": {("activitypointer", "account"): "Demo call 2 is regarding an account purged from the lake"},                          # the row a plain join to account would miss
    "bc_not_unique_without_company": ["Customer-18", "Item-27", "SalesInvoiceHeader-112"],
    "bc_doc_type_shared_no": 1,                           # quote 1001 beside order 1001 in company A
    "bc_dimension_rows_per_entry": 2,
    "bc_gl_revenue_103001": -1080,
}


def _sqlite_type(kind: str) -> str:
    return {"string": "nvarchar", _I: "int"}.get(kind, "decimal")


def sqlite(schema: str = "dynamics", only: list[str] | None = None):
    """(Schema, execute) over the demo rows in an in-memory SQLite database; `only` limits the Schema (not the database)
    to those tables, as a lakehouse holding just them would be read."""
    import sqlite3

    from .dialects import sqlite_sql
    from .schema import Schema
    con = sqlite3.connect(":memory:")
    con.execute(f"ATTACH DATABASE ':memory:' AS {schema}")
    info = []
    for name, (cols, kinds, rows) in tables().items():
        con.execute(f"CREATE TABLE {schema}.[{name}] ({', '.join(f'[{c}]' for c in cols)})")
        con.executemany(f"INSERT INTO {schema}.[{name}] VALUES ({','.join('?' * len(cols))})", rows)
        if only is None or name in only:
            info += [(schema, name, c, _sqlite_type(k), i) for i, (c, k) in enumerate(zip(cols, kinds), 1)]

    def execute(sql: str):
        cur = con.execute(sqlite_sql(sql))
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]
    return Schema.from_information_schema(info, schema=schema), execute


# The four data products the demo is drafted into (round PK2). The table lists are the scope a person would choose for
# each; within it everything is the engine's: the plan, the checks on the rows, the domain proposal, the ontology and
# semantic model drafts (products() below).
PRODUCTS = {
    "lead_to_cash": {"title": "Lead to cash (Dataverse: Dynamics 365 Sales)",
                     "tables": ["lead", "opportunity", "opportunityproduct", "quote", "quotedetail", "salesorder", "salesorderdetail",
                                "invoice", "invoicedetail", "account", "product", "transactioncurrency"]},
    "order_to_cash": {"title": "Order to cash (Business Central)",
                      "tables": ["Customer-18", "Item-27", "SalespersonPurchaser-13", "SalesHeader-36", "SalesLine-37", "SalesInvoiceHeader-112",
                                 "SalesInvoiceLine-113", "CustLedgerEntry-21", "DetailedCustLedgEntry-379", "GLEntry-17", "DimensionSetEntry-480"]},
    "customer_360": {"title": "Customer 360 (Dataverse)",
                     "tables": ["account", "contact", "activitypointer", "opportunity", "salesorder", "invoice", "incident", "systemuser", "team"]},
    "service_cases": {"title": "Service cases (Dataverse: Dynamics 365 Customer Service)",
                      "tables": ["incident", "account", "contact", "product", "activitypointer", "systemuser", "team", "businessunit"]},
}


def products() -> dict:
    """What the engine makes of each data product's tables on the demo rows: the plan (keys, relationships), the checks
    on the rows (evidence.validate), the header amounts a join repeats, the domain proposal, the ontology draft and the
    semantic model draft (their summaries). Every number is computed here; the tests compare it with
    tests/golden/pk2_dynamics_products.json."""
    from . import domains, evidence, ontology, semantic_model
    from .infer import plan
    out = {}
    for pid, spec in PRODUCTS.items():
        schema, execute = sqlite(only=spec["tables"])
        p = plan(schema)
        v = evidence.validate(p, execute, max_items=500)
        rels = v["relationships"]
        doubled = sorted({(f["header"], f["line"], c) for f in v["amount_levels"]["findings"]
                          if (f.get("rows_per_header") or {}).get("max_lines", 0) > 1 for c in f["amount_columns"]})
        dm = domains.propose_plan(p, v)
        onto = ontology.summary(p)
        info = dict(workspace_id="", item_id="", item_name="dynamics_demo", item_kind="Lakehouse", schema=schema.schema,
                    sql_endpoint="example.invalid", sql_db="dynamics_demo", schemas_enabled=None)
        sm = semantic_model.draft(p, info, pid)["summary"]
        out[pid] = {
            "title": spec["title"], "tables": len(spec["tables"]), "pack": (p.pack or {}).get("pack"),
            "keys": {"total": len(v["keys"]), "unique": sum(1 for k in v["keys"] if str(k.get("verdict", "")).startswith("unique"))},
            "relationships": {"planned": len(p.relationships), "extended": len(p.extended), "checked": len(rels),
                              "hold": sum(1 for r in rels if str(r.get("verdict", "")).startswith("holds")),
                              "orphans": sorted(f"{r['source']}.{'+'.join(r['columns'])} -> {r['target']}: {r['orphans']}"
                                                for r in rels if r.get("orphans"))},
            "doubled_amounts": [f"{h}.{c} over {l}" for h, l, c in doubled],
            "domains": [{"name": d["name"], "tables": d["tables"]} for d in dm["domains"]],
            "unassigned": [u["table"] for u in dm["unassigned"]],
            "ontology": {k: onto[k] for k in ("entity_types", "with_key", "relationship_types", "skipped_relationships")},
            "semantic_model": {"tables": sm["tables"], "relationships_active": sm["relationships_active"],
                               "relationships_inactive": sm["relationships_inactive"], "measures": len(sm["measures"]),
                               "header_amounts": sorted(f"{h['table']}.{h['column']}" for h in sm["header_amounts"])},
        }
    return out


def rows_for_check() -> dict[str, tuple[list[str], list[tuple]]]:
    return {name: (cols, rows) for name, (cols, _k, rows) in tables().items()}


def write_csv(folder: str | Path) -> list[Path]:
    """One CSV per table, _types.json, and load_dynamics_demo.py (PySpark cells for a Fabric notebook). Nothing here
    connects to Fabric. Table names with a hyphen are written with an underscore (SalesHeader_36), as a lakehouse table
    name cannot carry the hyphen; the pack reads both."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written, types = [], {}
    for name, (cols, kinds, rows) in tables().items():
        safe = name.replace("-", "_")
        path = folder / f"{safe}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        written.append(path)
        types[safe] = dict(zip(cols, kinds))
    (folder / "_types.json").write_text(json.dumps(types, indent=2) + "\n", encoding="utf-8")
    (folder / "README.txt").write_text(SYNTHETIC + ".\n", encoding="utf-8")
    (folder / "load_dynamics_demo.py").write_text(notebook(), encoding="utf-8")
    return written + [folder / "_types.json", folder / "README.txt", folder / "load_dynamics_demo.py"]


def notebook() -> str:
    return '''# SYNTHETIC DEMO DATA: Dynamics-365-shaped tables for Krusgraph (fabric_backend/dynamics_demo.py). Every value is made up.
# Attach this notebook to a lakehouse, upload the CSV files and _types.json to Files/dynamics_demo, then run.
import json
from pyspark.sql import functions as F

base = "Files/dynamics_demo"
types = json.loads("".join(r.value for r in spark.read.text(f"{base}/_types.json").collect()))
for name, cols in types.items():
    df = spark.read.option("header", True).option("inferSchema", False).csv(f"{base}/{name}.csv")
    for c, t in cols.items():
        if t != "string":
            df = df.withColumn(c, F.col(c).cast(t))
    df.write.mode("overwrite").option("delta.columnMapping.mode", "name").format("delta").saveAsTable(name)
    print(name, df.count(), "rows")
'''
