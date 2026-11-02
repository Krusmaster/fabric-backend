"""Round n72: the younium_salesforce pack (fabric_backend/packs/younium_salesforce/) and its synthetic demo
(fabric_backend/younium_demo.py). The pack's files are valid and consistent (tests/test_sap_pack.py checks every pack
file against the schema), every claim names a source and says it is unverified, the loader reads the demo's tables with
their system prefixes and camelCase or snake_case columns, and the planted traps are found. Since round n78 the engine
reads the pack itself (infer._pack calls sap_pack.match_any); the tests at the end say that it does, that the plans of the
other benchmark sets are the ones the SAP-only engine made, and that a few tables with the pack's ordinary names do not
light it. The fixture `run` still plans through sap_pack.plan_with, the caller-side stand-in of round n72."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from fabric_backend import browser_check as bc, domains, evidence, privacy, sap_pack, seed, younium_demo as yd
from fabric_backend.infer import plan
from fabric_backend.schema import Schema

ROOT = Path(__file__).resolve().parents[1]
PACK_FILES = sorted((sap_pack.PACKS / "younium_salesforce").glob("*.json"))


@pytest.fixture(scope="module")
def run():
    schema, execute = yd.sqlite()
    p, m = sap_pack.plan_with(schema, "younium_salesforce")
    return schema, execute, p, m, evidence.validate(p, execute, max_items=200)


def _pack(name: str) -> str:
    return sap_pack.table_name(name)


# ---------------------------------------------------------------- the pack's files

def test_two_modules_and_a_consistent_merge():
    assert [f.stem for f in PACK_FILES] == ["salesforce", "younium"]
    p = sap_pack.load("younium_salesforce")
    assert sap_pack.problems(p) == []
    assert set(p["tables"]) == {"ACCOUNTS", "PRODUCTS", "CHARGE_PLANS", "CHARGES", "SUBSCRIPTIONS", "SUBSCRIPTION_VERSIONS", "SUBSCRIPTION_CHARGES",
                                "SALES_ORDERS", "INVOICES", "INVOICE_LINES", "PAYMENTS",
                                "ACCOUNT", "CONTACT", "OPPORTUNITY", "OPPORTUNITYLINEITEM", "PRODUCT2", "PRICEBOOKENTRY", "ORDER", "ORDERITEM", "CONTRACT"}
    assert sap_pack.available() == ["sap", "younium_salesforce"]


def test_the_relationships_the_round_asked_for_are_there():
    p = sap_pack.load("younium_salesforce")
    rels = {(r["source"], tuple(r["source_cols"]), r["target"]): r for r in p["relationships"]}
    bridge = rels[("ACCOUNTS", ("EXTERNAL_CRM_ID",), "ACCOUNT")]
    assert bridge["target_cols"] == ["ID"] and "15" in bridge["condition"] and bridge["sources"] == ["younium_sf_integration"]
    for key in [("SUBSCRIPTIONS", ("ACCOUNT_ID",), "ACCOUNTS"), ("SUBSCRIPTION_VERSIONS", ("SUBSCRIPTION_ID",), "SUBSCRIPTIONS"),
                ("CHARGES", ("CHARGE_PLAN_ID",), "CHARGE_PLANS"), ("CHARGE_PLANS", ("PRODUCT_ID",), "PRODUCTS"),
                ("INVOICES", ("ACCOUNT_ID",), "ACCOUNTS"), ("INVOICE_LINES", ("INVOICE_ID",), "INVOICES"), ("PAYMENTS", ("INVOICE_ID",), "INVOICES"),
                ("OPPORTUNITY", ("ACCOUNT_ID",), "ACCOUNT"), ("OPPORTUNITYLINEITEM", ("OPPORTUNITY_ID",), "OPPORTUNITY"),
                ("PRICEBOOKENTRY", ("PRODUCT2_ID",), "PRODUCT2"), ("ORDERITEM", ("ORDER_ID",), "ORDER"), ("CONTRACT", ("ACCOUNT_ID",), "ACCOUNT")]:
        assert rels[key].get("apply") is not False, key
    # the links the documentation could not be read for are listed, never applied: the invoice line by number
    for key in [("INVOICE_LINES", ("CHARGE_NUMBER",), "CHARGES"), ("INVOICE_LINES", ("SUBSCRIPTION_NUMBER",), "SUBSCRIPTIONS")]:
        assert rels[key]["apply"] is False and rels[key]["kind"] == "unique" and "could not be read" in rels[key]["condition"]


def test_every_source_is_marked_unverified_with_the_date_it_was_not_reached():
    p = sap_pack.load("younium_salesforce")
    assert p["sources"] and all(not s["fetched"] for s in p["sources"].values())
    for s in p["sources"].values():
        assert s["note"].startswith("Unverified") and "1 November 2026" in s["note"], s["title"]
        assert s["url"].startswith(("https://developer.younium.com", "https://support.younium.com", "https://developer.salesforce.com"))
    for t in p["tables"].values():
        assert t["sources"] and t.get("area") in {"customers", "subscriptions", "billing", "product catalog", "sales"}, t["name"]
    for m in p["modules"]:
        assert m["status"] == "documented"
    ids = {t["id"] for t in p["traps"]}
    assert {"subscription_versions", "amounts_on_lines", "mrr_arr", "currency_per_account", "usage_charges", "salesforce_id_length", "two_accounts"} <= ids


def test_no_certification_or_affiliation_words_and_no_real_party():
    texts = [f.read_text(encoding="utf-8") for f in PACK_FILES] + [(ROOT / "fabric_backend" / "younium_demo.py").read_text(encoding="utf-8"),
                                                                   (ROOT / "docs" / "YOUNIUM-SALESFORCE.md").read_text(encoding="utf-8")]
    for text in texts:
        low = text.lower()
        for word in ("certified", "endorsed", "official partner", "partner program", "partners with", "partner of", "a partner"):
            assert word not in low, word
        for word in ("verified against", "tested against a younium", "tested against a salesforce"):
            assert word not in low or "not " + word in low or "never" in low, word
    for name, (cols, _types, rows) in yd.tables().items():
        for r in rows:
            for v in r:
                if isinstance(v, str) and "@" in v:
                    assert v.endswith(".example.invalid"), (name, v)
        if "name" in [c.lower() for c in cols]:
            i = [c.lower() for c in cols].index("name")
            assert all(r[i].startswith("Demo ") or r[i].startswith("Platform") or r[i].startswith("Add-on") or r[i].startswith("Onboarding") or r[i].startswith("API") for r in rows), name


# ---------------------------------------------------------------- the loader on prefixed tables and either column case

@pytest.mark.parametrize("name,expected", [("younium_accounts", "ACCOUNTS"), ("sf_account", "ACCOUNT"), ("salesforce_opportunity", "OPPORTUNITY"),
                                           ("crm_contact", "CONTACT"), ("raw_younium_invoice_lines", "INVOICE_LINES"), ("bronze.sf_opportunitylineitem", "OPPORTUNITYLINEITEM"),
                                           ("sap_vbak", "VBAK"), ("accounts", "ACCOUNTS")])
def test_system_prefixes_are_read_past(name, expected):
    assert sap_pack.table_name(name) == expected


def test_camel_case_columns_match_the_snake_case_pack():
    rows = [("s", "accounts", c, "nvarchar", i) for i, c in enumerate(["id", "accountNumber", "externalCrmId", "currency"], 1)]
    rows += [("s", "subscriptions", c, "nvarchar", i) for i, c in enumerate(["id", "orderNumber", "accountId", "invoiceAccountId"], 1)]
    rows += [("s", "Account", c, "nvarchar", i) for i, c in enumerate(["Id", "Name"], 1)]
    m = sap_pack.match(Schema.from_information_schema(rows, schema="s"), "younium_salesforce")
    assert set(m.tables.values()) == {"ACCOUNTS", "SUBSCRIPTIONS", "ACCOUNT"} and m.keys == {"accounts": ["id"], "subscriptions": ["id"], "Account": ["Id"]}
    got = {(r["source"], tuple(r["source_cols"]), r["target"], tuple(r["target_cols"]), r.get("role")) for r in m.relationships}
    assert got == {("accounts", ("externalCrmId",), "Account", ("Id",), "salesforce_account"),
                   ("subscriptions", ("accountId",), "accounts", ("id",), "account"),
                   ("subscriptions", ("invoiceAccountId",), "accounts", ("id",), "invoice_account")}


def test_the_sap_pack_still_matches_the_same_way():
    from tests import sap_support
    for style in ("upper", "lower", "prefix"):
        m = sap_pack.match(sap_support.schema(style=style))
        assert len(m.tables) == len(sap_support.schema(style=style)) and sap_pack.match_any(sap_support.schema(style=style)).pack == "sap"


def test_match_any_takes_the_pack_that_recognises_most(run):
    assert sap_pack.match_any(run[0]).pack == "younium_salesforce"
    assert sap_pack.match_any(seed.schema()) is None


# ---------------------------------------------------------------- the demo and its planted traps

def test_the_demo_is_recognised_whole_and_the_listed_links_are_named(run):
    schema, _, p, m, validation = run
    assert len(schema) == yd.EXPECTED["tables"] and sum(len(r) for _, _, r in yd.tables().values()) == yd.EXPECTED["rows"]
    assert len(m.tables) == 14 and m.missing_columns == [] and m.client_dropped == []
    assert m.missing_tables == ["CONTRACT", "ORDER", "PRICEBOOKENTRY", "PRODUCT2", "SALES_ORDERS"]
    assert {_pack(r["target"]) for r in m.not_applied} == yd.EXPECTED["not_applied_targets"]
    assert len(p.relationships) == 15 and all(r.rule == "confirmed" for r in p.relationships)
    assert all(k["verdict"].startswith("unique") for k in validation["keys"])


def test_without_the_pack_the_name_rules_find_nothing_between_the_prefixed_tables(run):
    p0 = plan(run[0], packs=False)
    assert p0.relationships == [] and p0.ambiguous == [] and all(rule == "K2" for _, rule in p0.keys.values())


def test_only_the_planted_orphan_the_15_character_salesforce_id(run):
    orphans = {(_pack(r["source"]), _pack(r["target"])): (r["orphans"], r["rows_with_value"]) for r in run[4]["relationships"] if r.get("orphans")}
    assert orphans == {("ACCOUNTS", "ACCOUNT"): (1, 4)}
    short = [r for r in yd.tables()["ACCOUNTS"][2] if r[4] and len(r[4]) == 15]
    assert len(short) == 1 and short[0][2] == "Demo Account 4" and all(len(r[0]) == 18 for r in yd.tables()["ACCOUNT"][2])


def test_the_invoice_total_and_the_opportunity_amount_double_over_their_lines(run):
    findings = {(_pack(f["header"]), _pack(f["line"])): f for f in run[4]["amount_levels"]["findings"]}
    for header, line, column in yd.EXPECTED["doubled"]:
        f = findings[(header, line)]
        assert column in f["amount_columns"] and f["rows_per_header"]["max_lines"] == yd.EXPECTED["max_lines"][(header, line)]


def test_one_version_is_valid_today_and_a_sum_over_versions_is_wrong_by_the_number_of_versions(run):
    _, execute, *_ = run
    sql = ("SELECT SUM(c.[price] * c.[quantity]) AS total FROM [billing].[younium_subscription_charges] c "
           "JOIN [billing].[younium_subscription_versions] v ON v.[id] = c.[subscription_version_id] "
           "JOIN [billing].[younium_subscriptions] s ON s.[id] = v.[subscription_id] "
           "WHERE s.[subscription_number] = 'SUB-2001' AND c.[charge_type] = 'Recurring'")
    assert execute(sql)[0]["total"] == yd.EXPECTED["recurring_price_over_all_versions"]
    assert execute(sql + " AND v.[is_last_version] = 1")[0]["total"] == yd.EXPECTED["recurring_price_valid_today"]
    assert execute("SELECT COUNT(*) AS n FROM [billing].[younium_subscription_versions] v JOIN [billing].[younium_subscriptions] s ON s.[id] = v.[subscription_id] "
                   "WHERE s.[subscription_number] = 'SUB-2001'")[0]["n"] == yd.EXPECTED["versions_of_sub_2001"]


def test_currency_per_account_and_a_draft_invoice_are_in_the_rows():
    acc = yd.tables()["ACCOUNTS"]
    assert sorted({r[3] for r in acc[2]}) == ["EUR", "SEK"]
    inv = yd.tables()["INVOICES"]
    drafts = [r for r in inv[2] if r[5] == "Draft"]
    assert len(drafts) == 1 and drafts[0][1] is None


def test_personal_columns_are_flagged(run):
    flagged = {(_pack(t), c) for t, c in privacy.personal_columns(run[0])}
    assert set(yd.EXPECTED["masked"]) <= flagged


# ---------------------------------------------------------------- domains

def test_domain_draft_names_the_domains_after_the_pack_areas(run):
    schema, _, p, m, validation = run
    out = domains.draft(p, "billing", validation=validation, areas=domains.pack_areas(m))
    by = {d["name"]: d["tables"] for d in out["domains"]}
    assert set(by) == {"billing", "product catalog and subscriptions", "customers and sales"}
    assert {"younium_invoices", "younium_invoice_lines", "younium_payments"} <= set(by["billing"])
    assert {"younium_subscription_versions", "younium_subscription_charges", "younium_charges", "younium_charge_plans", "younium_products"} <= set(by["product catalog and subscriptions"])
    assert by["customers and sales"] == ["sf_account", "sf_contact", "sf_opportunity", "sf_opportunitylineitem"]
    assert out["unassigned"] == [] and any(i["source"] == "younium_accounts" and i["target"] == "sf_account" for i in out["interfaces"])
    assert all("knowledge pack's areas" in d["name_reason"] for d in out["domains"])
    # since round n78 a plan carries plan.pack, so the proposal reads the areas from it unasked
    assert {d["name"] for d in domains.propose_plan(p, validation)["domains"]} == set(by)
    # without the pack in the plan the names fall back to the prefixes the tables share
    bare, _ = sap_pack.plan_with(schema, "younium_salesforce", packs=False)
    assert bare.pack is None and {d["name"] for d in domains.propose_plan(bare, validation)["domains"]} == {"younium", "younium 2", "sf_account"}


def test_shop_and_sap_proposals_are_unchanged_by_the_areas():
    out = domains.draft(plan(seed.schema("shop")), "shop", "shop_lh")
    assert {d["name"] for d in out["domains"]} == {"customers", "products"}
    assert domains.pack_areas(None) == {} and domains._plan_areas(plan(seed.schema("shop"))) == {}


# ---------------------------------------------------------------- files for Fabric and for /check

def test_the_files_hold_the_same_rows_and_check_can_take_them(tmp_path):
    written = yd.write_csv(tmp_path)
    assert (tmp_path / "younium_accounts.csv") in written and (tmp_path / "sf_account.csv") in written
    types = json.loads((tmp_path / "_types.json").read_text(encoding="utf-8"))
    assert types["younium_invoices"]["total_amount"] == "decimal(15,2)" and types["younium_subscription_versions"]["version"] == "int"
    nb = (tmp_path / "load_younium_demo.py").read_text(encoding="utf-8")
    compile(nb, "load_younium_demo.py", "exec")
    assert "Files/younium_demo" in nb
    src = bc._sqlite_source("folder", "Synthetic Younium + Salesforce tables", "billing", yd.rows_for_check(), "synthetic")
    try:
        assert len(src.schema) == 14 and sap_pack.match_any(src.schema).pack == "younium_salesforce"
        assert src.execute("SELECT COUNT(*) AS n FROM [billing].[younium_invoice_lines]")[0]["n"] == 8
    finally:
        src.close()


def test_the_doc_names_the_sources_the_date_and_what_is_unverified():
    md = (ROOT / "docs" / "YOUNIUM-SALESFORCE.md").read_text(encoding="utf-8")
    for needle in ("1 November 2026", "unverified", "developer.younium.com", "support.younium.com/hc/en-us/articles/29942644887954",
                   "support.younium.com/hc/en-us/articles/4402123737617", "developer.salesforce.com", "External CRM Id", "15", "18",
                   "fabric_backend/younium_demo.py", "match_any"):
        assert needle in md, needle
    assert re.search(r"^## .*[Qq]uestions", md, re.M)


# ---------------------------------------------------------------- the engine reads the pack (round n78)

def _rels(p) -> set:
    return {(r.source, tuple(r.source_cols), r.target, tuple(r.target_cols), r.rule) for r in p.relationships}


def test_the_engine_plans_the_demo_with_the_pack(run):
    schema, execute, via_caller, _, _ = run
    p = plan(schema)
    assert p.pack["pack"] == "younium_salesforce" and p.pack["rule"] == "SAP pack" and len(p.pack["tables"]) == 14
    assert {t["id"] for t in p.pack["traps"]} >= {"salesforce_id_length", "sf_rollup_amounts", "amounts_on_lines", "subscription_versions"}
    assert {(a["table"], a["column"]) for a in p.pack["amounts"]} >= {("younium_invoices", "TOTAL_AMOUNT"), ("sf_opportunity", "AMOUNT")}
    # the same fifteen joins plan_with gave as the caller's, now with the pack's rule and its source on the note
    assert {r[:4] for r in _rels(p)} == {r[:4] for r in _rels(via_caller)} and len(p.relationships) == 15
    assert {r.rule for r in p.relationships} == {"SAP pack"} and all(r.note.startswith("younium_salesforce pack (") for r in p.relationships)
    assert p.keys["younium_accounts"] == (["id"], "SAP pack") and p.keys["sf_account"] == (["Id"], "SAP pack")


def test_validate_plan_shows_the_three_planted_traps_on_the_engine_plan(run):
    schema, execute, *_ = run
    v = evidence.validate(plan(schema), execute, max_items=200)
    orphans = {(r["source"], tuple(r["columns"]), r["target"]): r["orphans"] for r in v["relationships"] if r.get("orphans")}
    assert orphans == {("younium_accounts", ("external_crm_id",), "sf_account"): 1}         # the 15-character Salesforce id
    doubled = {(f["header"], f["line"]) for f in v["amount_levels"]["findings"]
               if isinstance(f["rows_per_header"], dict) and f["rows_per_header"]["max_lines"] > 1}
    assert {("younium_invoices", "younium_invoice_lines"), ("sf_opportunity", "sf_opportunitylineitem")} <= doubled


def _old_engine_plan(schema, monkeypatch, **kw):
    """The plan as the engine made it before round n78, when infer._pack read the SAP pack alone (sap_pack.match)."""
    with monkeypatch.context() as mp:
        mp.setattr(sap_pack, "match_any", lambda s, variant=None: sap_pack.match(s))
        return plan(schema, **kw)


def _same(a, b):
    assert a.keys == b.keys and _rels(a) == _rels(b) and [r.note for r in a.relationships] == [r.note for r in b.relationships]
    assert a.pack == b.pack and a.ambiguous == b.ambiguous and a.keyless == b.keyless and len(a.extended) == len(b.extended)


@pytest.mark.parametrize("name", ["shop", "sap", "crm", "traps"])
def test_the_other_benchmark_sets_plan_as_before(name, monkeypatch):
    import sys
    sys.path.insert(0, str(ROOT / "examples" / "benchmark"))
    import benchmark
    src = benchmark.source(name)
    try:
        _same(plan(src.schema, execute=src.execute), _old_engine_plan(src.schema, monkeypatch, execute=src.execute))
        assert (plan(src.schema).pack or {}).get("pack") == ("sap" if name == "sap" else None)
    finally:
        if getattr(src, "close", None):
            src.close()


def test_the_shop_and_sap_plans_are_the_ones_before(monkeypatch):
    from tests import sap_support
    for schema in [seed.schema("shop"), sap_support.schema(), sap_support.schema(style="prefix")]:
        _same(plan(schema), _old_engine_plan(schema, monkeypatch))
    assert plan(seed.schema("shop")).pack is None and plan(sap_support.schema()).pack["pack"] == "sap"


def test_salesforce_objects_alone_do_not_light_the_pack():
    """The crm set: Account, Contact and Opportunity are tables the pack knows, but every one is marked common_name."""
    t = bc.crm_tables()
    rows = [("crm", n, c, "nvarchar", i) for n, (cols, _) in t.items() for i, c in enumerate(cols, 1)]
    schema = Schema.from_information_schema(rows, schema="crm")
    assert set(sap_pack.match(schema, "younium_salesforce").tables.values()) == {"ACCOUNT", "CONTACT", "OPPORTUNITY"}
    assert sap_pack.distinctive(sap_pack.match(schema, "younium_salesforce")) == []
    assert sap_pack.match_any(schema) is None and plan(schema).pack is None


def _generic(extra: dict | None = None) -> Schema:
    """An ordinary billing schema of another system whose table names happen to be the pack's (accounts, products,
    invoices, invoice_lines, payments, subscriptions, a Contact), each keyed by id."""
    tables = {"accounts": ["id", "name", "country"], "products": ["id", "name", "price"],
              "invoices": ["id", "account_id", "invoice_date", "total_amount"],
              "invoice_lines": ["id", "invoice_id", "product_id", "amount"], "payments": ["id", "invoice_id", "account_id", "amount"],
              "subscriptions": ["id", "account_id", "start_date"], "Contact": ["Id", "AccountId", "Email"], **(extra or {})}
    rows = [("app", n, c, "int" if c == "id" or c.endswith("_id") else "nvarchar", i) for n, cols in tables.items() for i, c in enumerate(cols, 1)]
    return Schema.from_information_schema(rows, schema="app")


def test_a_few_tables_with_the_packs_ordinary_names_do_not_light_it():
    schema = _generic()
    m = sap_pack.match(schema, "younium_salesforce")
    assert m is not None and len(m.tables) == 7 and sap_pack.distinctive(m) == []     # asked for by name, the pack reads them
    assert sap_pack.match_any(schema) is None
    p = plan(schema)
    assert p.pack is None and "SAP pack" not in {r.rule for r in p.relationships} | {rule for _, rule in p.keys.values()}
    no_pack = plan(schema, packs=False)
    assert p.keys == no_pack.keys and _rels(p) == _rels(no_pack)
    for two in (["accounts", "invoices"], ["invoices", "invoice_lines"], ["Contact", "accounts"]):
        sub = Schema.from_information_schema([r for r in [("app", t.name, c.name, c.data_type, i) for t in schema for i, c in enumerate(t.columns, 1)]
                                              if r[1] in two], schema="app")
        assert sap_pack.match_any(sub) is None and plan(sub).pack is None, two


def test_one_table_of_the_systems_own_lights_it():
    """The boundary: with subscription_versions beside them, a table no other system names so, the pack is read."""
    schema = _generic({"subscription_versions": ["id", "subscription_id", "version", "effective_start_date", "effective_end_date"]})
    assert sap_pack.match_any(schema).pack == "younium_salesforce" and sap_pack.distinctive(sap_pack.match_any(schema)) == ["SUBSCRIPTION_VERSIONS"]
    assert plan(schema).pack["pack"] == "younium_salesforce"


def test_only_ordinary_names_are_marked_and_no_sap_table_is():
    marked = {n for n, t in sap_pack.load("younium_salesforce")["tables"].items() if t.get("common_name")}
    assert marked == {"ACCOUNTS", "PRODUCTS", "CHARGES", "SUBSCRIPTIONS", "SALES_ORDERS", "INVOICES", "INVOICE_LINES", "PAYMENTS",
                      "ACCOUNT", "CONTACT", "OPPORTUNITY", "ORDER", "ORDERITEM", "CONTRACT"}
    assert not any(t.get("common_name") for t in sap_pack.load("sap")["tables"].values())
