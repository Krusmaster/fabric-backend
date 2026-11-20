"""Synthetic Salesforce tables with rows, written from the salesforce pack, for running its checks end to end (round PK1).

SYNTHETIC. Every value is made up: companies "Demo Company 1" to "Demo Company 5", people "First1 Last1", e-mail
addresses at example.invalid, ids that only have the shape of Salesforce ids (18 characters: a three-character object
prefix as commonly seen, then made-up characters). Nothing comes from a Salesforce org or a customer. The tables follow
the pack's keys and relationships (fabric_backend/packs/salesforce/salesforce.json), so a run on them shows that the
tools work on Salesforce-shaped data, never that the pack is right about Salesforce: the rows are written from the
pack. The pack's claims rest on Salesforce's public Object Reference, read on 17 November 2026 (docs/SALESFORCE.md).

Twenty-one tables, named as a Fabric Copy job lands them by default: the object's API name (Account,
OpportunityLineItem) with the field API names as columns (AccountId). The traps are planted, and EXPECTED says what
each check should find:
- Opportunity 1 has three line items: its Amount summed over its lines comes out three times (the total that doubles);
  Order 1 over its three products and Quote 1 over its three lines do the same;
- a price book that was deleted while lines still used it (archived: not returned by the API): one price book entry
  and one opportunity point at a Pricebook2 that is not in the landing;
- Task and Event point at a contact or a lead (WhoId) and at an account, an opportunity, a case or a campaign (WhatId);
- Lead 1 was converted into Demo Company 4, contact 6 and opportunity 4, and stays in the Lead table;
- Quote 1 syncs with opportunity 1 and mirrors its lines; Quote 2 is an earlier offer for the same opportunity;
- the campaigns carry the sums of their opportunities (AmountAllOpportunities, AmountWonOpportunities);
- one opportunity is deleted (IsDeleted), as a copy with 'Include deleted objects' would land it;
- one case and one lead are owned by a queue, not a user; one account is a person account; Demo Company 3 deals in EUR.

    tables()           -> {object: (columns, types, rows)}
    sqlite()           -> (Schema, execute) over the rows in SQLite (schema "salesforce"), as the tests and a local run use
    write_csv(folder)  -> one CSV per table, the types in _types.json, and a PySpark notebook that loads them
    report()           -> what the engine finds on the demo: plan, checks, domains, ontology and semantic-model drafts;
                          docs/SALESFORCE.md quotes it (python -m fabric_backend.salesforce_demo --doc)
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from .younium_demo import _sfid

PACK = "salesforce"
SCHEMA = "salesforce"
DEMO_WHERE = "synthetic Salesforce demo"          # what a run on these tables is; never a verification
LABEL = "SYNTHETIC: made-up rows written from the salesforce pack (fabric_backend/salesforce_demo.py); not Salesforce data"
_D = "decimal(18,2)"
_I = "int"
_B = "boolean"            # the API's boolean fields (IsWon, IsDeleted): 0 or 1 here, bit in the SQLite schema, boolean in Spark

# ids of the shape the API returns (18 characters); the three-character prefixes are the ones commonly seen per object
USR = [_sfid("005", n) for n in range(1, 4)]
QUEUE = _sfid("00G", 1)                     # a queue: owns a lead and a case; no User row
ACC = [_sfid("001", n) for n in range(1, 6)]
CON = [_sfid("003", n) for n in range(1, 7)]
LEA = [_sfid("00Q", n) for n in range(1, 6)]
CMP = [_sfid("701", n) for n in range(1, 3)]
CMM = [_sfid("00v", n) for n in range(1, 6)]
PRD = [_sfid("01t", n) for n in range(1, 4)]
PBK = [_sfid("01s", n) for n in range(1, 4)]   # PBK[2]: archived, not in the landing
PBE = [_sfid("01u", n) for n in range(1, 6)]
OPP = [_sfid("006", n) for n in range(1, 6)]
OLI = [_sfid("00k", n) for n in range(1, 7)]
OCR = [_sfid("00K", n) for n in range(1, 5)]
QUO = [_sfid("0Q0", n) for n in range(1, 3)]
QLI = [_sfid("0QL", n) for n in range(1, 6)]
CTR = [_sfid("800", n) for n in range(1, 3)]
ORD = [_sfid("801", n) for n in range(1, 3)]
ORI = [_sfid("802", n) for n in range(1, 5)]
AST = [_sfid("02i", n) for n in range(1, 4)]
CAS = [_sfid("500", n) for n in range(1, 5)]
TSK = [_sfid("00T", n) for n in range(1, 6)]
EVT = [_sfid("00U", n) for n in range(1, 4)]


def _t(cols: str, rows: list[tuple], decimals: str = "", ints: str = "") -> tuple[list[str], list[str], list[tuple]]:
    """Columns, their types and rows. `ints` lists the whole-number columns; those named Is*/Has*/Use* are booleans."""
    c, d, i = cols.split(), set(decimals.split()), set(ints.split())
    assert all(len(r) == len(c) for r in rows), cols
    flag = lambda x: x.startswith(("Is", "Has", "Use")) and x[3 if x.startswith("Use") else 2].isupper()
    return c, [_D if x in d else (_B if flag(x) else _I) if x in i else "string" for x in c], rows


def tables() -> dict[str, tuple[list[str], list[str], list[tuple]]]:
    u1, u2, u3 = USR
    return {
        "User": _t("Id Username FirstName LastName Name Email IsActive ManagerId", [
            (u1, "user1@demo.example.invalid", "First1", "User1", "First1 User1", "user1@demo.example.invalid", 1, None),
            (u2, "user2@demo.example.invalid", "First2", "User2", "First2 User2", "user2@demo.example.invalid", 1, u1),
            (u3, "user3@demo.example.invalid", "First3", "User3", "First3 User3", "user3@demo.example.invalid", 0, u1)], ints="IsActive"),
        "Account": _t("Id Name Industry BillingCountry ParentId IsPersonAccount CurrencyIsoCode OwnerId", [
            (ACC[0], "Demo Company 1", "Technology", "SE", None, 0, "SEK", u1),
            (ACC[1], "Demo Company 2", "Retail", "SE", ACC[0], 0, "SEK", u2),
            (ACC[2], "Demo Company 3", "Healthcare", "FI", None, 0, "EUR", u2),
            (ACC[3], "Demo Company 4", "Manufacturing", "SE", None, 0, "SEK", u1),          # created by converting Lead 1
            (ACC[4], "Person Demo5", None, "SE", None, 1, "SEK", u3)], ints="IsPersonAccount"),   # a person account
        "Contact": _t("Id AccountId FirstName LastName Email OwnerId", [
            (CON[0], ACC[0], "First1", "Last1", "contact1@company1.example.invalid", u1),
            (CON[1], ACC[0], "First2", "Last2", "contact2@company1.example.invalid", u1),
            (CON[2], ACC[1], "First3", "Last3", "contact3@company2.example.invalid", u2),
            (CON[3], ACC[2], "First4", "Last4", "contact4@company3.example.invalid", u2),
            (CON[4], None, "First5", "Last5", "contact5@example.invalid", u3),                 # a contact without an account
            (CON[5], ACC[3], "First6", "Last6", "lead1@company4.example.invalid", u1)]),        # from Lead 1
        "Lead": _t("Id FirstName LastName Company Email Status LeadSource IsConverted ConvertedDate ConvertedAccountId "
                   "ConvertedContactId ConvertedOpportunityId CampaignId OwnerId", [
            (LEA[0], "First6", "Last6", "Demo Company 4", "lead1@company4.example.invalid", "Closed - Converted", "Webinar", 1, "2026-05-04",
             ACC[3], CON[5], OPP[3], CMP[0], u1),                                                # converted: still a Lead row
            (LEA[1], "First7", "Last7", "Demo Prospect 7", "lead2@prospect7.example.invalid", "Working - Contacted", "Webinar", 0, None, None, None, None, CMP[0], u1),
            (LEA[2], "First8", "Last8", "Demo Prospect 8", "lead3@prospect8.example.invalid", "Open - Not Contacted", "Trade Show", 0, None, None, None, None, CMP[1], u2),
            (LEA[3], "First9", "Last9", "Demo Prospect 9", "lead4@prospect9.example.invalid", "Closed - Not Converted", "Web", 0, None, None, None, None, None, u2),
            (LEA[4], "First10", "Last10", "Demo Prospect 10", "lead5@prospect10.example.invalid", "Open - Not Contacted", "Web", 0, None, None, None, None, None, QUEUE)],
            ints="IsConverted"),
        "Campaign": _t("Id Name Type Status StartDate BudgetedCost ActualCost AmountAllOpportunities AmountWonOpportunities OwnerId", [
            (CMP[0], "Demo Webinar", "Webinar", "Completed", "2026-03-10", 20000, 18000, 166000, 136000, u1),   # O1 (won) + O4 (open)
            (CMP[1], "Demo Trade Fair", "Trade Show", "Completed", "2026-04-20", 60000, 64000, 52800, 52800, u2)],   # O2 (won)
            "BudgetedCost ActualCost AmountAllOpportunities AmountWonOpportunities"),
        "CampaignMember": _t("Id CampaignId LeadId ContactId Status HasResponded", [
            (CMM[0], CMP[0], LEA[0], CON[5], "Responded", 1),            # a converted lead tracked with both ids
            (CMM[1], CMP[0], None, CON[0], "Responded", 1),
            (CMM[2], CMP[0], LEA[1], None, "Sent", 0),
            (CMM[3], CMP[1], None, CON[2], "Responded", 1),
            (CMM[4], CMP[1], LEA[2], None, "Sent", 0)], ints="HasResponded"),
        "Product2": _t("Id Name ProductCode Family IsActive QuantityUnitOfMeasure", [
            (PRD[0], "Demo Platform", "PLAT", "Software", 1, "Each"),
            (PRD[1], "Demo Add-on", "ADD", "Software", 1, "Each"),
            (PRD[2], "Demo Onboarding", "SERV", "Services", 1, "Each")], ints="IsActive"),
        "Pricebook2": _t("Id Name IsStandard IsActive", [
            (PBK[0], "Standard Price Book", 1, 1),
            (PBK[1], "Demo Partner Price Book", 0, 1)], ints="IsStandard IsActive"),            # PBK[2] was deleted: archived
        "PricebookEntry": _t("Id Pricebook2Id Product2Id UnitPrice CurrencyIsoCode IsActive UseStandardPrice", [
            (PBE[0], PBK[0], PRD[0], 12000, "SEK", 1, 0),
            (PBE[1], PBK[0], PRD[1], 1100, "SEK", 1, 0),
            (PBE[2], PBK[0], PRD[2], 5000, "SEK", 1, 0),
            (PBE[3], PBK[0], PRD[0], 1100, "EUR", 1, 0),
            (PBE[4], PBK[2], PRD[1], 1000, "SEK", 1, 0)], "UnitPrice", "IsActive UseStandardPrice"),   # its price book is archived
        "Opportunity": _t("Id AccountId Name StageName CloseDate IsClosed IsWon Probability Amount ExpectedRevenue CurrencyIsoCode "
                          "CampaignId Pricebook2Id SyncedQuoteId IsDeleted OwnerId", [
            (OPP[0], ACC[0], "Demo Company 1 - platform", "Closed Won", "2026-04-15", 1, 1, 100, 136000, 136000, "SEK", CMP[0], PBK[0], QUO[0], 0, u1),
            (OPP[1], ACC[1], "Demo Company 2 - add-on", "Closed Won", "2026-05-20", 1, 1, 100, 52800, 52800, "SEK", CMP[1], PBK[0], None, 0, u2),
            (OPP[2], ACC[2], "Demo Company 3 - pilot", "Negotiation/Review", "2026-12-15", 0, 0, 60, 2200, 1320, "EUR", None, PBK[0], None, 0, u2),
            (OPP[3], ACC[3], "Demo Company 4 - add-on", "Prospecting", "2027-01-31", 0, 0, 10, 30000, 3000, "SEK", CMP[0], PBK[2], None, 0, u1),
            (OPP[4], ACC[0], "Demo Company 1 - lost", "Closed Lost", "2026-02-01", 1, 0, 0, 9000, 0, "SEK", None, None, None, 1, u1)],   # deleted
            "Probability Amount ExpectedRevenue", "IsClosed IsWon IsDeleted"),
        "OpportunityLineItem": _t("Id OpportunityId PricebookEntryId Product2Id Quantity UnitPrice ListPrice TotalPrice", [
            (OLI[0], OPP[0], PBE[0], PRD[0], 10, 12000, 12000, 120000),
            (OLI[1], OPP[0], PBE[2], PRD[2], 1, 5000, 5000, 5000),
            (OLI[2], OPP[0], PBE[1], PRD[1], 10, 1100, 1100, 11000),
            (OLI[3], OPP[1], PBE[1], PRD[1], 48, 1100, 1100, 52800),
            (OLI[4], OPP[2], PBE[3], PRD[0], 2, 1100, 1100, 2200),
            (OLI[5], OPP[3], PBE[4], PRD[1], 30, 1000, 1000, 30000)], "UnitPrice ListPrice TotalPrice", "Quantity"),
        "OpportunityContactRole": _t("Id OpportunityId ContactId Role IsPrimary", [
            (OCR[0], OPP[0], CON[0], "Decision Maker", 1),
            (OCR[1], OPP[0], CON[1], "Evaluator", 0),
            (OCR[2], OPP[1], CON[2], "Decision Maker", 1),
            (OCR[3], OPP[3], CON[5], "Business User", 1)], ints="IsPrimary"),
        "Quote": _t("Id OpportunityId AccountId ContactId Pricebook2Id Name QuoteNumber Status IsSyncing Subtotal TotalPrice GrandTotal CurrencyIsoCode OwnerId", [
            (QUO[0], OPP[0], ACC[0], CON[0], PBK[0], "Demo Company 1 - offer 2", "00000002", "Accepted", 1, 136000, 136000, 170000, "SEK", u1),
            (QUO[1], OPP[0], ACC[0], CON[0], PBK[0], "Demo Company 1 - offer 1", "00000001", "Denied", 0, 125000, 115000, 143750, "SEK", u1)],
            "Subtotal TotalPrice GrandTotal", "IsSyncing"),
        "QuoteLineItem": _t("Id QuoteId PricebookEntryId Product2Id OpportunityLineItemId Quantity UnitPrice Subtotal TotalPrice", [
            (QLI[0], QUO[0], PBE[0], PRD[0], OLI[0], 10, 12000, 120000, 120000),
            (QLI[1], QUO[0], PBE[2], PRD[2], OLI[1], 1, 5000, 5000, 5000),
            (QLI[2], QUO[0], PBE[1], PRD[1], OLI[2], 10, 1100, 11000, 11000),
            (QLI[3], QUO[1], PBE[0], PRD[0], None, 10, 12000, 120000, 110000),      # a discount on the earlier offer
            (QLI[4], QUO[1], PBE[2], PRD[2], None, 1, 5000, 5000, 5000)], "UnitPrice Subtotal TotalPrice", "Quantity"),
        "Contract": _t("Id AccountId ContractNumber Status StartDate ContractTerm EndDate OwnerId", [
            (CTR[0], ACC[0], "00000100", "Activated", "2026-05-01", 12, "2027-04-30", u1),
            (CTR[1], ACC[1], "00000101", "Draft", "2026-06-01", 24, "2028-05-31", u2)], ints="ContractTerm"),
        "Order": _t("Id AccountId ContractId OpportunityId QuoteId Pricebook2Id OrderNumber Status EffectiveDate TotalAmount CurrencyIsoCode OwnerId", [
            (ORD[0], ACC[0], CTR[0], OPP[0], QUO[0], PBK[0], "00000201", "Activated", "2026-05-01", 136000, "SEK", u1),
            (ORD[1], ACC[1], CTR[1], OPP[1], None, PBK[0], "00000202", "Draft", "2026-06-01", 52800, "SEK", u2)], "TotalAmount"),
        "OrderItem": _t("Id OrderId PricebookEntryId Product2Id QuoteLineItemId Quantity UnitPrice TotalPrice", [
            (ORI[0], ORD[0], PBE[0], PRD[0], QLI[0], 10, 12000, 120000),
            (ORI[1], ORD[0], PBE[2], PRD[2], QLI[1], 1, 5000, 5000),
            (ORI[2], ORD[0], PBE[1], PRD[1], QLI[2], 10, 1100, 11000),
            (ORI[3], ORD[1], PBE[1], PRD[1], None, 48, 1100, 52800)], "UnitPrice TotalPrice", "Quantity"),
        "Asset": _t("Id AccountId ContactId Product2Id Name SerialNumber Status InstallDate Quantity Price OwnerId", [
            (AST[0], ACC[0], CON[0], PRD[0], "Demo Platform - Company 1", "SN-0001", "Installed", "2026-05-10", 10, 120000, u1),
            (AST[1], ACC[0], None, PRD[2], "Demo Onboarding - Company 1", "SN-0002", "Installed", "2026-05-10", 1, 5000, u1),
            (AST[2], ACC[1], CON[2], PRD[1], "Demo Add-on - Company 2", "SN-0003", "Purchased", "2026-06-05", 48, 52800, u2)],
            "Price", "Quantity"),
        "Case": _t("Id CaseNumber AccountId ContactId AssetId ProductId Status Priority Origin Subject IsClosed IsEscalated CreatedDate ClosedDate SuppliedEmail OwnerId", [
            (CAS[0], "00001001", ACC[0], CON[0], AST[0], PRD[0], "Closed", "High", "Phone", "Sign-in fails after update", 1, 0, "2026-06-02", "2026-06-03", None, u3),
            (CAS[1], "00001002", ACC[0], CON[1], None, None, "Working", "Medium", "Email", "Question about the invoice", 0, 0, "2026-09-14", None, None, u3),
            (CAS[2], "00001003", ACC[1], CON[2], AST[2], PRD[1], "Escalated", "High", "Web", "Add-on stops at large files", 0, 1, "2026-10-01", None, None, u2),
            (CAS[3], "00001004", ACC[2], None, None, None, "New", "Low", "Web", "Request for a demo account", 0, 0, "2026-11-02", None,
             "visitor@company3.example.invalid", QUEUE)], ints="IsClosed IsEscalated"),                  # owned by a queue
        "Task": _t("Id WhoId WhatId AccountId Subject Status ActivityDate Priority TaskSubtype OwnerId", [
            (TSK[0], CON[0], OPP[0], ACC[0], "Call about the offer", "Completed", "2026-04-02", "Normal", "Call", u1),
            (TSK[1], LEA[1], None, None, "Call after the webinar", "Completed", "2026-03-12", "Normal", "Call", u1),
            (TSK[2], CON[2], CAS[2], ACC[1], "Follow up the escalated case", "Not Started", "2026-11-20", "High", "Task", u2),
            (TSK[3], None, ACC[2], ACC[2], "Send pilot plan", "In Progress", "2026-11-25", "Normal", "Email", u2),
            (TSK[4], CON[5], OPP[3], ACC[3], "Prepare the first meeting", "Not Started", "2026-12-01", "Normal", "Task", u1)]),
        "Event": _t("Id WhoId WhatId AccountId Subject StartDateTime EndDateTime DurationInMinutes OwnerId", [
            (EVT[0], CON[0], OPP[0], ACC[0], "Contract meeting", "2026-04-10T09:00:00Z", "2026-04-10T10:00:00Z", 60, u1),
            (EVT[1], LEA[2], CMP[1], None, "Meeting at the trade fair", "2026-04-20T13:00:00Z", "2026-04-20T13:30:00Z", 30, u2),
            (EVT[2], CON[2], ACC[1], ACC[1], "Quarterly review", "2026-10-15T14:00:00Z", "2026-10-15T15:00:00Z", 60, u2)], ints="DurationInMinutes"),
    }


# What the checks should find on these rows. tests/test_pk1_salesforce_pack.py runs validate_plan, the amount levels and
# the privacy rules on them in SQLite and compares with this.
EXPECTED = {
    "tables": 21,
    "rows": 81,
    "orphans": {("PricebookEntry", "Pricebook2"): "PBE 5's price book was deleted while lines used it (archived)",
                ("Opportunity", "Pricebook2"): "Opportunity 4 uses the archived price book"},
    "doubled": [("Opportunity", "OpportunityLineItem", "Amount"), ("Order", "OrderItem", "TotalAmount"), ("Quote", "QuoteLineItem", "TotalPrice")],
    "max_lines": {("Opportunity", "OpportunityLineItem"): 3, ("Order", "OrderItem"): 3, ("Quote", "QuoteLineItem"): 3},
    "who": {"Contact": 5, "Lead": 2},                  # Task and Event rows whose WhoId is a contact's or a lead's id
    "what": {"Opportunity": 3, "Account": 2, "Case": 1, "Campaign": 1},
    "masked": [("Contact", "Email"), ("Lead", "Email"), ("User", "Email")],
}


def write_csv(folder: str | Path) -> list[Path]:
    """One CSV per table (header row), _types.json with each column's type, README.txt saying the rows are synthetic, and
    load_salesforce_demo.py, the PySpark cells that load them as tables named after the objects. Nothing here connects
    to Fabric."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written, types = [], {}
    for name, (cols, kinds, rows) in tables().items():
        path = folder / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        written.append(path)
        types[name] = dict(zip(cols, kinds))
    (folder / "_types.json").write_text(json.dumps(types, indent=2) + "\n", encoding="utf-8")
    (folder / "README.txt").write_text(LABEL + "\n", encoding="utf-8")
    (folder / "load_salesforce_demo.py").write_text(notebook(), encoding="utf-8")
    return written + [folder / "_types.json", folder / "README.txt", folder / "load_salesforce_demo.py"]


def notebook() -> str:
    """PySpark for a Fabric notebook attached to the lakehouse that holds the CSVs under Files/salesforce_demo."""
    return '''# SYNTHETIC Salesforce-shaped demo tables for Krusgraph (fabric_backend/salesforce_demo.py). Every value is made up;
# nothing comes from a Salesforce org. Attach this notebook to the lakehouse, upload the CSV files and _types.json to
# Files/salesforce_demo, then run. Tables are written under the objects' API names (Account, OpportunityLineItem) in the
# default schema; existing tables of those names are replaced.
import json
from pyspark.sql import functions as F

base = "Files/salesforce_demo"
types = json.loads("".join(r.value for r in spark.read.text(f"{base}/_types.json").collect()))
for name, cols in types.items():
    df = spark.read.option("header", True).option("inferSchema", False).csv(f"{base}/{name}.csv")
    for c, t in cols.items():
        if t != "string":
            df = df.withColumn(c, F.col(c).cast(t))
    df.write.mode("overwrite").format("delta").saveAsTable(name)
    print(name, df.count(), "rows")
'''


def sqlite(schema: str = SCHEMA):
    """(Schema, execute) over the demo rows in an in-memory SQLite database, the way the tests and a local run use them."""
    import sqlite3

    from .dialects import sqlite_sql
    from .schema import Schema
    con = sqlite3.connect(":memory:")
    con.execute(f"ATTACH DATABASE ':memory:' AS {schema}")
    info = []
    for name, (cols, kinds, rows) in tables().items():
        con.execute(f"CREATE TABLE {schema}.[{name}] ({', '.join(f'[{c}]' for c in cols)})")
        con.executemany(f"INSERT INTO {schema}.[{name}] VALUES ({','.join('?' * len(cols))})", rows)
        info += [(schema, name, c, {"string": "nvarchar", _I: "int", _B: "bit"}.get(k, "decimal"), i) for i, (c, k) in enumerate(zip(cols, kinds), 1)]

    def execute(sql: str):
        cur = con.execute(sqlite_sql(sql))
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]
    return Schema.from_information_schema(info, schema=schema), execute


def report() -> dict:
    """What the engine finds on the demo, computed now: the plan (infer.plan reads the pack through match_any), the
    checks on the rows (evidence.validate), the domains it proposes (domains.draft), and the ontology and semantic-model
    drafts (the same functions ontology_draft and semantic_model_draft call). docs/SALESFORCE.md quotes this; a test
    fails when the page and the engine disagree."""
    from . import domains, evidence, ontology, sap_pack, semantic_model
    from .infer import plan, rule_label
    schema, execute = sqlite()
    p = plan(schema)
    m = sap_pack.match_any(schema)
    v = evidence.validate(p, execute, max_items=200)
    rels = v.get("relationships", [])
    orphans = sorted(f"{r['source']}.{'+'.join(r['columns'])} -> {r['target']}: {r['orphans']} of {r['rows_with_value']}"
                     for r in rels if r.get("orphans"))
    levels = sorted(f"{f['header']}.{', '.join(f['amount_columns'])} over {f['line']}.{'+'.join(f['line_columns'])}: up to "
                    f"{f['rows_per_header']['max_lines']} rows per {f['header']} row"
                    for f in (v.get("amount_levels") or {}).get("findings", [])
                    if (f.get("rows_per_header") or {}).get("max_lines", 0) > 1)
    d = domains.draft(p, SCHEMA, "salesforce demo", validation=v)
    onto = ontology.summary(p, None)
    sm = semantic_model.draft(p, {"item_name": "salesforce_demo", "item_kind": "Lakehouse", "schema": SCHEMA, "sql_endpoint": "",
                                  "sql_db": "", "schemas_enabled": False}, "salesforce_demo", None, validation=v)
    by_rule: dict[str, int] = {}
    for r in p.relationships:
        label = rule_label(r.rule, p.pack)
        by_rule[label] = by_rule.get(label, 0) + 1
    return {
        "label": LABEL,
        "pack": m.pack if m else None,
        "tables": len(list(schema)),
        "rows": sum(len(t[2]) for t in tables().values()),
        "pack_tables_recognised": len(m.tables) if m else 0,
        "keys": len(p.keys),
        "relationships": len(p.relationships),
        "relationships_by_rule": dict(sorted(by_rule.items())),
        "not_applied": len(m.not_applied) if m else 0,
        "orphans": orphans,
        "doubled_amounts": levels,
        "domains": [{"name": x["name"], "tables": sorted(x["tables"])} for x in d["domains"]],
        "unassigned": sorted(d.get("unassigned", [])),
        "ontology": onto,
        "semantic_model": sm["summary"],
    }


def _doc_block(r: dict) -> str:
    """The generated section of docs/SALESFORCE.md: every number in it is read from report()."""
    out = ["<!-- generated by python -m fabric_backend.salesforce_demo --doc; do not edit by hand -->", "",
           f"*{r['label']}.*", "",
           f"- Tables: {r['tables']}, rows: {r['rows']}; the engine picked the `{r['pack']}` pack and recognised "
           f"{r['pack_tables_recognised']} of its tables.",
           f"- Planned: {r['keys']} keys and {r['relationships']} relationships ("
           + ", ".join(f"{n} by {k}" for k, n in r["relationships_by_rule"].items()) + f"); {r['not_applied']} pack "
           f"relationships between the demo's tables are listed and not applied (polymorphic, self-references, second paths, queue owners).",
           "- Orphans `validate_plan` counts on the rows:" + ("" if r["orphans"] else " none")]
    out += [f"  - {o}" for o in r["orphans"]]
    out += ["- Header amounts a join with their lines repeats (*the total that doubles*):" + ("" if r["doubled_amounts"] else " none")]
    out += [f"  - {a}" for a in r["doubled_amounts"]]
    out += ["", "Data products (domains) the engine proposes, by community detection over the planned relationships and named "
                "after the pack's areas:", ""]
    out += [f"| {i} | {x['name']} | {', '.join(x['tables'])} |" if i else "" for i, x in enumerate(r["domains"], 1)]
    out = out[:-len(r["domains"])] + ["| # | Proposed data product | Tables |", "| --- | --- | --- |"] + \
        [f"| {i} | {x['name']} | {', '.join(x['tables'])} |" for i, x in enumerate(r["domains"], 1)]
    if r["unassigned"]:
        out += ["", "Not assigned to a domain: " + ", ".join(r["unassigned"]) + "."]
    out += ["", "Ontology draft (`ontology_draft`, nothing created): " + _short(r["ontology"]),
            "", "Semantic-model draft (`semantic_model_draft`, nothing created): " + _short(r["semantic_model"]), "",
            "<!-- end of generated section -->"]
    return "\n".join(out)


def _short(summary) -> str:
    if isinstance(summary, dict):
        keep = {k: v for k, v in summary.items() if isinstance(v, (int, str)) and (not isinstance(v, str) or len(v) < 200)}
        keep.update({k: len(v) for k, v in summary.items() if k in ("measures", "header_amounts") and isinstance(v, list)})
        return "; ".join(f"{k}: {v}" for k, v in keep.items())
    return str(summary)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    r = report()
    print(_doc_block(r) if "--doc" in argv else json.dumps(r, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
