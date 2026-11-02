"""Synthetic Younium + Salesforce tables with rows, for running the younium_salesforce pack's checks end to end (round n72).

Every value is made up: accounts "Demo Account 1" to "Demo Account 4", e-mail addresses at example.invalid, ids that
only look like GUIDs and Salesforce ids. Nothing comes from a Younium tenant, a Salesforce org or a customer. The
tables follow the pack's keys and relationships, so a run on them shows that the tools work on Younium-shaped and
Salesforce-shaped data, never that the pack is right about Younium: the rows are written from the pack (and the pack
from sources the writing session could not open; see docs/YOUNIUM-SALESFORCE.md).

Fourteen tables: ten Younium (prefix younium_, snake-case columns as a flattening pipeline would write them) and four
Salesforce (prefix sf_, the objects' API field names). 58 rows. Amounts are whole numbers (the declared types are
decimal(15,2)), so a loader that types columns by their values (browser_check._sqlite_source, the benchmark) sees numbers. The traps are planted, and EXPECTED says what each
check should find:
- invoice INV-1001 has three lines, so younium_invoices.total_amount summed over its lines comes out three times too
  large (the check 'the total that doubles'); the Salesforce opportunity amount over its line items is the same trap,
  and comes with Salesforce's own model (Amount is the sum of the line items);
- an orphan: Demo Account 4's external_crm_id holds the 15-character form of its Salesforce id, the form the user
  interface shows, while sf_account.Id has 18: the link ACCOUNTS.EXTERNAL_CRM_ID -> ACCOUNT.ID finds nothing for that row;
- subscription SUB-2001 has three versions, one valid today: a sum of prices over all versions is wrong by three;
- Demo Account 3 is billed in EUR, the others in SEK; a usage charge whose quantity is reported, not agreed; a draft
  invoice beside the posted ones; an invoice account that differs from the subscription's account.

    tables()                -> {name: (columns, types, rows)}; names without the prefixes (ACCOUNTS, ACCOUNT, ...)
    sqlite()                -> (Schema, execute) over the rows in SQLite with the prefixes, as the tests and a local run use
    write_csv(folder)       -> one CSV per table, the types in _types.json, and a PySpark notebook that loads them
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

PACK = "younium_salesforce"
PREFIXES = {"younium": "younium_", "salesforce": "sf_"}
DEMO_WHERE = "synthetic Younium + Salesforce demo"          # what a run on these tables is; never a verification
_D = "decimal(15,2)"
_I = "int"
FOREVER = "9999-12-31"


def _t(cols: list[str], rows: list[tuple], decimals: tuple[str, ...] = (), ints: tuple[str, ...] = ()) -> tuple[list[str], list[str], list[tuple]]:
    return cols, [_D if c in decimals else _I if c in ints else "string" for c in cols], rows


def _guid(prefix: str, n: int) -> str:
    return f"{prefix}000000-0000-4000-8000-{n:012d}"


def _sfid(prefix: str, n: int) -> str:
    """An 18-character id of the shape Salesforce returns: 3-character object prefix, 12 characters, 3 checksum characters."""
    return f"{prefix}A00000000{n:03d}AAA"


ACC = [_guid("a1", n) for n in range(1, 5)]
PRD = [_guid("b2", n) for n in range(1, 3)]
CPL = [_guid("c3", n) for n in range(1, 4)]
CHG = [_guid("d4", n) for n in range(1, 5)]
SUB = [_guid("e5", n) for n in range(1, 4)]
VER = [_guid("f6", n) for n in range(1, 6)]
SCH = [_guid("a7", n) for n in range(1, 8)]
INV = [_guid("b8", n) for n in range(1, 5)]
LIN = [_guid("c9", n) for n in range(1, 9)]
PAY = [_guid("da", n) for n in range(1, 4)]
SF_ACC = [_sfid("001", n) for n in range(1, 5)]
SF_CON = [_sfid("003", n) for n in range(1, 5)]
SF_OPP = [_sfid("006", n) for n in range(1, 4)]
SF_OLI = [_sfid("00k", n) for n in range(1, 5)]


def tables() -> dict[str, tuple[list[str], list[str], list[tuple]]]:
    return {
        # ------------------------------------------------------------------ Younium
        "ACCOUNTS": _t(["id", "account_number", "name", "currency", "external_crm_id", "external_erp_id", "invoice_email"], [
            (ACC[0], "A-1001", "Demo Account 1", "SEK", SF_ACC[0], "C1001", "invoices@account1.example.invalid"),
            (ACC[1], "A-1002", "Demo Account 2", "SEK", SF_ACC[1], "C1002", "invoices@account2.example.invalid"),
            (ACC[2], "A-1003", "Demo Account 3", "EUR", SF_ACC[2], "C1003", "invoices@account3.example.invalid"),
            (ACC[3], "A-1004", "Demo Account 4", "SEK", SF_ACC[3][:15], None, "invoices@account4.example.invalid")]),   # planted: 15 characters
        "PRODUCTS": _t(["id", "product_number", "name"], [(PRD[0], "P-100", "Demo Platform"), (PRD[1], "P-200", "Demo Add-on")]),
        "CHARGE_PLANS": _t(["id", "charge_plan_number", "product_id", "name", "effective_start_date"], [
            (CPL[0], "CP-100-1", PRD[0], "Platform, yearly", "2026-01-01"),
            (CPL[1], "CP-100-2", PRD[0], "Platform, monthly", "2026-01-01"),
            (CPL[2], "CP-200-1", PRD[1], "Add-on, usage", "2026-01-01")]),
        "CHARGES": _t(["id", "charge_number", "charge_plan_id", "name", "charge_type", "price_period", "list_price"], [
            (CHG[0], "C-100-1-1", CPL[0], "Platform licence", "Recurring", "Year", 12000),
            (CHG[1], "C-100-1-2", CPL[0], "Onboarding", "One-off", "Once", 5000),
            (CHG[2], "C-100-2-1", CPL[1], "Platform licence", "Recurring", "Month", 1100),
            (CHG[3], "C-200-1-1", CPL[2], "API calls (per thousand)", "Usage", "Month", 1)], ("list_price",)),
        "SUBSCRIPTIONS": _t(["id", "subscription_number", "account_id", "invoice_account_id", "status", "currency", "external_crm_id"], [
            (SUB[0], "SUB-2001", ACC[0], ACC[0], "Active", "SEK", SF_OPP[0]),
            (SUB[1], "SUB-2002", ACC[1], ACC[0], "Active", "SEK", SF_OPP[1]),          # billed to another account
            (SUB[2], "SUB-2003", ACC[2], ACC[2], "Active", "EUR", None)]),
        "SUBSCRIPTION_VERSIONS": _t(["id", "subscription_id", "version", "is_last_version", "effective_start_date", "effective_end_date"], [
            (VER[0], SUB[0], 1, 0, "2026-01-01", "2026-04-01"),
            (VER[1], SUB[0], 2, 0, "2026-04-01", "2026-09-01"),
            (VER[2], SUB[0], 3, 1, "2026-09-01", FOREVER),                                 # the one valid today
            (VER[3], SUB[1], 1, 1, "2026-03-01", FOREVER),
            (VER[4], SUB[2], 1, 1, "2026-06-01", FOREVER)], ints=("version", "is_last_version")),
        "SUBSCRIPTION_CHARGES": _t(["id", "subscription_version_id", "charge_id", "charge_type", "quantity", "price"], [
            (SCH[0], VER[0], CHG[0], "Recurring", 10, 12000),
            (SCH[1], VER[0], CHG[1], "One-off", 1, 5000),
            (SCH[2], VER[1], CHG[0], "Recurring", 15, 12000),                           # seats added: a new version
            (SCH[3], VER[2], CHG[0], "Recurring", 20, 12000),
            (SCH[4], VER[2], CHG[3], "Usage", 0, 1),                                    # quantity comes from usage
            (SCH[5], VER[3], CHG[2], "Recurring", 5, 1100),
            (SCH[6], VER[4], CHG[2], "Recurring", 8, 1100)], ("price",), ("quantity",)),
        "INVOICES": _t(["id", "invoice_number", "account_id", "invoice_date", "due_date", "status", "currency", "sub_total", "tax_amount", "total_amount"], [
            (INV[0], "INV-1001", ACC[0], "2026-09-01", "2026-10-01", "Posted", "SEK", 125000, 31250, 156250),   # three lines
            (INV[1], "INV-1002", ACC[0], "2026-09-01", "2026-10-01", "Posted", "SEK", 5500, 1375, 6875),         # SUB-2002, billed to account 1
            (INV[2], "INV-1003", ACC[2], "2026-09-01", "2026-10-01", "Posted", "EUR", 8800, 0, 8800),
            (INV[3], None, ACC[1], "2026-10-01", None, "Draft", "SEK", 5500, 1375, 6875)],                       # a draft: no number yet
            ("sub_total", "tax_amount", "total_amount")),
        "INVOICE_LINES": _t(["id", "invoice_id", "line_number", "charge_number", "subscription_number", "product_number", "quantity", "unit_price", "amount",
                             "service_period_start_date", "service_period_end_date"], [
            (LIN[0], INV[0], 1, "C-100-1-1", "SUB-2001", "P-100", 20, 6000, 120000, "2026-09-01", "2027-02-28"),   # half a year of the yearly licence
            (LIN[1], INV[0], 2, "C-100-1-2", "SUB-2001", "P-100", 1, 5000, 5000, "2026-09-01", "2026-09-01"),
            (LIN[2], INV[0], 3, "C-200-1-1", "SUB-2001", "P-200", 0, 1, 0, "2026-08-01", "2026-08-31"),             # usage: 0 this period
            (LIN[3], INV[1], 1, "C-100-2-1", "SUB-2002", "P-100", 5, 1100, 5500, "2026-09-01", "2026-09-30"),
            (LIN[4], INV[2], 1, "C-100-2-1", "SUB-2003", "P-100", 8, 1100, 8800, "2026-09-01", "2026-09-30"),
            (LIN[5], INV[3], 1, "C-100-2-1", "SUB-2002", "P-100", 5, 1100, 5500, "2026-10-01", "2026-10-31"),
            (LIN[6], INV[2], 2, "C-200-1-1", "SUB-2003", "P-200", 0, 1, 0, "2026-08-01", "2026-08-31"),
            (LIN[7], INV[1], 2, "C-200-1-1", "SUB-2002", "P-200", 0, 1, 0, "2026-08-01", "2026-08-31")],
            ("unit_price", "amount"), ("line_number", "quantity")),
        "PAYMENTS": _t(["id", "payment_number", "account_id", "invoice_id", "payment_date", "amount"], [
            (PAY[0], "PAY-3001", ACC[0], INV[0], "2026-09-28", 156250),
            (PAY[1], "PAY-3002", ACC[0], INV[1], "2026-09-28", 6875),
            (PAY[2], "PAY-3003", ACC[2], INV[2], "2026-10-02", 8800)], ("amount",)),
        # ------------------------------------------------------------------ Salesforce
        "ACCOUNT": _t(["Id", "Name", "Industry", "BillingCountry", "ParentId"], [
            (SF_ACC[0], "Demo Account 1", "Software", "SE", None),
            (SF_ACC[1], "Demo Account 2", "Retail", "SE", SF_ACC[0]),
            (SF_ACC[2], "Demo Account 3", "Health", "FI", None),
            (SF_ACC[3], "Demo Account 4", "Finance", "SE", None)]),
        "CONTACT": _t(["Id", "AccountId", "FirstName", "LastName", "Email"], [
            (SF_CON[0], SF_ACC[0], "First1", "Last1", "contact1@account1.example.invalid"),
            (SF_CON[1], SF_ACC[0], "First2", "Last2", "contact2@account1.example.invalid"),
            (SF_CON[2], SF_ACC[1], "First3", "Last3", "contact3@account2.example.invalid"),
            (SF_CON[3], SF_ACC[3], "First4", "Last4", "contact4@account4.example.invalid")]),
        "OPPORTUNITY": _t(["Id", "AccountId", "Name", "StageName", "CloseDate", "CurrencyIsoCode", "Amount"], [
            (SF_OPP[0], SF_ACC[0], "Demo Account 1 - platform", "Closed Won", "2025-12-15", "SEK", 125000),       # the sum of two line items
            (SF_OPP[1], SF_ACC[1], "Demo Account 2 - monthly", "Closed Won", "2026-02-20", "SEK", 13200),
            (SF_OPP[2], SF_ACC[3], "Demo Account 4 - pilot", "Negotiation", "2026-12-01", "SEK", 4400)], ("Amount",)),
        "OPPORTUNITYLINEITEM": _t(["Id", "OpportunityId", "Quantity", "UnitPrice", "TotalPrice"], [
            (SF_OLI[0], SF_OPP[0], 10, 12000, 120000),
            (SF_OLI[1], SF_OPP[0], 1, 5000, 5000),
            (SF_OLI[2], SF_OPP[1], 12, 1100, 13200),
            (SF_OLI[3], SF_OPP[2], 4, 1100, 4400)], ("UnitPrice", "TotalPrice"), ("Quantity",)),
    }


def module_of(name: str) -> str:
    """Which module of the pack a demo table belongs to: ACCOUNT, CONTACT, OPPORTUNITY, OPPORTUNITYLINEITEM are Salesforce."""
    return "salesforce" if name in ("ACCOUNT", "CONTACT", "OPPORTUNITY", "OPPORTUNITYLINEITEM") else "younium"


def landing_name(name: str) -> str:
    """The table's name in the lakehouse: younium_accounts, sf_account."""
    return PREFIXES[module_of(name)] + name.lower()


# What the checks should find on these rows. The tests run validate_plan, amount_levels and the privacy rules on them in
# SQLite (through the pack's keys and relationships) and compare with this.
EXPECTED = {
    "tables": 14,
    "rows": 58,
    "orphans": {("ACCOUNTS", "ACCOUNT"): "Demo Account 4's external_crm_id has 15 characters, sf_account.Id 18"},
    "doubled": [("INVOICES", "INVOICE_LINES", "total_amount"), ("OPPORTUNITY", "OPPORTUNITYLINEITEM", "Amount")],
    "max_lines": {("INVOICES", "INVOICE_LINES"): 3, ("OPPORTUNITY", "OPPORTUNITYLINEITEM"): 2},
    "versions_of_sub_2001": 3,
    "recurring_price_valid_today": 20 * 12000,          # the one version valid today, recurring charges only
    "recurring_price_over_all_versions": (10 + 15 + 20) * 12000,
    "masked": [("CONTACT", "Email"), ("CONTACT", "FirstName"), ("ACCOUNTS", "invoice_email")],
    "not_applied_targets": {"CHARGES", "SUBSCRIPTIONS", "PRODUCTS", "OPPORTUNITY", "ACCOUNT"},   # the listed links: by number, the opportunity, the parent account
}


def write_csv(folder: str | Path) -> list[Path]:
    """One CSV per table (header row; text as text), _types.json with each column's type, and load_younium_demo.py, the
    PySpark cells that load them as younium_<name> and sf_<name>. Upload the folder to the lakehouse's
    Files/younium_demo and run the notebook there; nothing here connects to Fabric."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written, types = [], {}
    for name, (cols, kinds, rows) in tables().items():
        path = folder / f"{landing_name(name)}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        written.append(path)
        types[landing_name(name)] = dict(zip(cols, kinds))
    (folder / "_types.json").write_text(json.dumps(types, indent=2) + "\n", encoding="utf-8")
    (folder / "load_younium_demo.py").write_text(notebook(), encoding="utf-8")
    return written + [folder / "_types.json", folder / "load_younium_demo.py"]


def notebook() -> str:
    """PySpark for a Fabric notebook attached to the lakehouse that holds the CSVs under Files/younium_demo."""
    return '''# Synthetic Younium + Salesforce demo tables for Krusgraph (fabric_backend/younium_demo.py). Every value is made up.
# Attach this notebook to the lakehouse, upload the CSV files and _types.json to Files/younium_demo, then run.
# Tables are written as younium_<name> and sf_<name> in the default schema; existing tables of those names are replaced.
import json
from pyspark.sql import functions as F

base = "Files/younium_demo"
types = json.loads("".join(r.value for r in spark.read.text(f"{base}/_types.json").collect()))
for name, cols in types.items():
    df = spark.read.option("header", True).option("inferSchema", False).csv(f"{base}/{name}.csv")
    for c, t in cols.items():
        if t != "string":
            df = df.withColumn(c, F.col(c).cast(t))
    df.write.mode("overwrite").format("delta").saveAsTable(name)
    print(name, df.count(), "rows")
'''


def rows_for_check() -> dict[str, tuple[list[str], list[tuple]]]:
    """{landing name: (columns, rows)}, the shape browser_check._sqlite_source takes, for a /check example in a later round."""
    return {landing_name(name): (cols, rows) for name, (cols, _types, rows) in tables().items()}


def sqlite(schema: str = "billing"):
    """(Schema, execute) over the demo rows in an in-memory SQLite database, the way the tests and a local run use them."""
    import sqlite3

    from .dialects import sqlite_sql
    from .schema import Schema
    con = sqlite3.connect(":memory:")
    con.execute(f"ATTACH DATABASE ':memory:' AS {schema}")
    info = []
    for name, (cols, kinds, rows) in tables().items():
        t = landing_name(name)
        con.execute(f"CREATE TABLE {schema}.[{t}] ({', '.join(f'[{c}]' for c in cols)})")
        con.executemany(f"INSERT INTO {schema}.[{t}] VALUES ({','.join('?' * len(cols))})", rows)
        info += [(schema, t, c, {"string": "nvarchar", _I: "int"}.get(k, "decimal"), i) for i, (c, k) in enumerate(zip(cols, kinds), 1)]

    def execute(sql: str):
        cur = con.execute(sqlite_sql(sql))
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]
    return Schema.from_information_schema(info, schema=schema), execute
