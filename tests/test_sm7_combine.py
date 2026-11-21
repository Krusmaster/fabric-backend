"""SM7 (docs/SMOOTH/PLAN.md, row 6; docs/SMOOTH/COMBINE-SOURCES.md): SAP + CRM in one data product, on the synthetic
fixture tests/fixtures/multi_lakehouse.py, layout (b): `sap_lh`, `crm_lh` and `sales_product_lh`, whose `sap` and `crm`
schemas are the two sources (simulated schema shortcuts).

What must hold: the match rules find `crm.Account.SAP_Customer_No__c` -> `sap.KNA1.KUNNR` (M0) and count it on the rows
(3 of 4 filled values as written, 4 after normalising); the card says it in at most 25 words; nothing is combined until
the person accepts (the decision is kept in the flow state); then the model dry run has facts from both sources sharing
one `dim_customer`, with no fact-to-fact relationship. Start -> combined dry run in at most 6 taps. Nothing is written:
the fixture fails any POST, PATCH, PUT or DELETE."""
from __future__ import annotations

import json

import pytest
import wb15_fake
from fixtures import multi_lakehouse as mlh

from fabric_backend import combine, flow_state, infer, multi_schema, server
from fabric_backend import start_flow as sf
from fabric_backend.schema import Column, Schema, Table

W = mlh.WORKSPACE
E = mlh.EXPECTED["b"]["match"]
ARGS = {"workspace": W, "source": "sales_product_lh", "schema": "crm+sap"}
MATCH = "match:crm.Account.SAP_Customer_No__c>sap.KNA1.KUNNR"


@pytest.fixture(autouse=True)
def _clean():
    flow_state.clear()
    yield
    assert mlh.WRITES == [] and wb15_fake.WRITES == []
    flow_state.clear()


def _counted(monkeypatch):
    ws = mlh.install(monkeypatch, "b")
    p, found = server._combine_counts(W, "sales_product_lh", "crm+sap", None)
    return ws, p, found


def _walk(monkeypatch, accept: bool = True):
    """Start -> the dry run on layout (b), tapping what a person taps; returns (dry-run card, taps)."""
    mlh.install(monkeypatch, "b")
    card, taps = json.loads(server.start()), 0
    both = next(x for x in card["actions"] if x["kind"] == "choose" and "+" in x["label"])
    card, taps = json.loads(server.start(**both["arguments"])), taps + 1                 # the two sources, one plan
    while card["stage"] != "dry_run":
        tap = next((a for a in card["actions"] if a.get("decision") == "accepted" and a.get("item") == MATCH), None) \
            if accept and card["stage"] == "decide" and card.get("open_decisions") else None
        card = json.loads(server.start(**(tap or card["after"])["arguments"]))
        taps += 1
        assert taps < 8
    return card, taps


# ------------------------------------------------------------------------------------------------ the rules, counted
def test_the_party_tables_come_from_the_dp1_catalog(monkeypatch):
    _, p, found = _counted(monkeypatch)
    party = found["party"]
    assert party["sap"]["table"] == "sap.KNA1" and party["sap"]["product"] == "customer"
    assert party["sap"]["number"] == "KUNNR" and party["sap"]["tenant"] == "MANDT"          # DP1: tenant_id + customer_number
    assert party["crm"]["table"] == "crm.Account" and party["crm"]["product"] == "crm_account"
    assert party["crm"]["key"] == ["Id"] and party["crm"]["tenant"] is None


def test_m0_is_found_and_counted_as_the_fixture_says(monkeypatch):
    _, p, found = _counted(monkeypatch)
    c = next(x for x in found["candidates"] if x["id"] == MATCH)
    assert c["rule"] == mlh.EXPECTED["b"]["match"]["rule"] == "M0"
    assert f"{c['from']['table']}.{c['from']['column']}" == E["from"] and f"{c['to']['table']}.{c['to']['column']}" == E["to"]
    k = c["counts"]
    assert (k["filled"], k["a_rows"], k["found_raw"], k["found"]) == (E["filled"], E["of"], E["found_raw"], E["found_normalised"])
    assert (k["b_rows"], k["b_found"], k["b_shared"], k["only_a"], k["only_b"]) == (4, 3, 1, 1, 1)
    assert c["holds"] and c["certainty"] == 1.0 and found["proposed"] == MATCH
    assert not [x for x in found["candidates"] if x["rule"] == "M4"]                       # names are never a match
    assert not [x for x in found["candidates"] if x["from"]["column"] in ("ParentId", "OwnerId", "Name")]


def test_the_counts_run_on_one_connection_and_read_no_row_value(monkeypatch):
    ws, p, found = _counted(monkeypatch)
    product = [c for c in ws.connections if c.lakehouse == "sales_product_lh"]
    q = [x for c in product for x in c.queries if "SAP_Customer_No__c" in x]
    assert len(q) == found["queries"] == 2 and all("[crm].[Account]" in x and "[sap].[KNA1]" in x for x in q)
    assert all(x.lstrip().upper().startswith("SELECT COUNT_BIG(*)") for x in q)            # counts only
    said = json.dumps(server._combine_view(p, found, None))
    for value in ("0000000010", "SE556000001001", "Demo Customer"):
        assert value not in said


def test_the_card_line_is_at_most_25_words():
    c = {"from": {"schema": "crm", "table": "crm.Account", "column": "SAP_Customer_No__c"},
         "to": {"schema": "sap", "table": "sap.KNA1", "column": "KUNNR"}, "rule": "M0",
         "counts": {"a_rows": 41200, "found": 37800, "found_raw": 30000, "b_rows": 38950, "only_a": 3400, "only_b": 1150}}
    line = combine.card_line(c)
    assert line == ("SAP has 38950 customers, the CRM 41200 accounts. 37800 accounts match on SAP_Customer_No__c after "
                    "normalising. 1150 only in SAP, 3400 only in the CRM.")
    assert len(line.split()) <= 25


def test_m1_same_identifier_and_m2_counted_overlap_by_rules():
    sap = Table("sap.KNA1", [Column("MANDT"), Column("KUNNR"), Column("STCEG")], ["MANDT", "KUNNR"], schema="crm+sap")
    crm = Table("crm.Account", [Column("Id"), Column("VAT__c"), Column("AccountNumber"), Column("CurrencyIsoCode"),
                                Column("Name")], ["Id"], schema="crm+sap")
    s = Schema(schema="crm+sap")
    s.tables.update({"sap.KNA1": sap, "crm.Account": crm})
    p = infer.Plan(s, keys={"sap.KNA1": (["MANDT", "KUNNR"], "x"), "crm.Account": (["Id"], "x")},
                   pack={"pack": "sap", "by_schema": {"sap": "sap", "crm": "salesforce"},
                         "tables": {"sap.KNA1": "KNA1", "crm.Account": "ACCOUNT"}})
    got = {(c["rule"], c["from"]["column"], c["to"]["column"]) for c in combine.candidates(p)}
    assert ("M1", "VAT__c", "STCEG") in got and ("M2", "AccountNumber", "KUNNR") in got
    assert not any(c[1] in ("Name", "CurrencyIsoCode") for c in got)                       # M4 never; M3 is a code list
    assert combine.identifier_of("VAT__c") == combine.identifier_of("STCEG") == "vat id"
    assert combine.identifier_of("Name") is None


def test_m1_normalises_by_fixed_steps_on_the_engine():
    import sqlite3
    con = sqlite3.connect(":memory:")
    expr = combine.normal("x", "M1")
    for raw, want in (("SE 5566-7788.99/01", "5566778899"[:10] + "01"), ("556677-8899", "5566778899"), ("  gb123 ", "123")):
        assert con.execute(f"SELECT {expr} FROM (SELECT ? AS x)", (raw,)).fetchone()[0] == want


# ------------------------------------------------------------------------------------------------ the path
def test_check_shows_the_counts_and_one_decision_waits(monkeypatch):
    mlh.install(monkeypatch, "b")
    c = json.loads(server.start(**ARGS, step="check"))
    assert c["lines"][0] == ("SAP has 4 customers, the CRM 5 accounts. 4 accounts match on SAP_Customer_No__c after "
                             "normalising. 1 only in SAP, 1 only in the CRM.")
    assert len(c["lines"][0].split()) <= 25 and c["say"].endswith("1 needs you.") and c["match"]["id"] == MATCH
    assert c["match"]["customers"] == 5


def test_nothing_is_combined_until_the_person_accepts(monkeypatch):
    d, taps = _walk(monkeypatch, accept=False)
    assert d["combined"].startswith("No match accepted")
    m = json.loads(server.create_semantic_model(**ARGS, name="m"))
    assert "combined" not in m and "dim_customer" not in json.dumps(m["parts"])
    assert not (flow_state.state("local", W, "sales_product_lh", "crm+sap") or {}).get("decisions")


def test_decide_asks_for_the_match_with_its_evidence(monkeypatch):
    mlh.install(monkeypatch, "b")
    c = json.loads(server.start(**ARGS, step="decide"))
    q = c["found"]["decisions"][0]
    assert q["item"] == MATCH and q["state"] == "open" and q["rule"] == "M0"
    assert "4 of 5 crm.Account rows hold a value; 3 match as written, 4 after normalising." in q["evidence"]
    labels = [a["label"] for a in c["actions"] if a.get("item") == MATCH]
    assert labels == ["Accept the match", "Keep them apart"] and c["open_decisions"] == 1
    assert len(c["say"].split()) <= 25


def test_the_decision_goes_into_the_flow_state_and_the_latest_tap_wins(monkeypatch):
    mlh.install(monkeypatch, "b")
    c = json.loads(server.start(**ARGS, step="decide"))
    acc = next(a for a in c["actions"] if a.get("decision") == "accepted")
    rej = next(a for a in c["actions"] if a.get("decision") == "rejected")
    json.loads(server.start(**acc["arguments"]))
    kept = flow_state.state("local", W, "sales_product_lh", "crm+sap")["decisions"]
    assert [(d["item"], d["review"]) for d in kept] == [(MATCH, "accepted")]
    json.loads(server.start(**rej["arguments"]))
    json.loads(server.start(**ARGS, step="dry_run"))                               # an older card's Next undoes nothing
    kept = flow_state.state("local", W, "sales_product_lh", "crm+sap")["decisions"]
    assert [(d["item"], d["review"]) for d in kept] == [(MATCH, "rejected")]
    assert "combined" not in json.loads(server.create_semantic_model(**ARGS, name="m"))


def test_start_to_the_combined_dry_run_in_at_most_six_taps(monkeypatch):
    # The seconds (target 5) are measured by tools/smooth_measure.py --combine on a quiet machine, not here: in the
    # parallel suite a shared CI runner's load decides them, not the product.
    d, taps = _walk(monkeypatch)
    everything = next(a for a in d["actions"] if a["kind"] == "dry_run_all")
    taps += 1
    answers = {r["tool"]: json.loads(getattr(server, r["tool"])(**r["arguments"])) for r in everything["runs"]}
    assert taps <= 6
    assert not [t for t, a in answers.items() if a.get("error")]
    assert d["combined"].startswith("SAP + CRM → 1 dim_customer (5 customers)")
    assert "5 customers in one dim_customer" in d["say"] and len(d["say"].split()) <= 15
    assert answers["create_semantic_model"]["combined"]["match"] == MATCH


def test_the_model_dry_run_has_facts_from_both_sources_sharing_dim_customer(monkeypatch):
    _walk(monkeypatch)
    m = json.loads(server.create_semantic_model(**ARGS, name="sales_360_model"))
    k = m["combined"]
    sources = {f["source"] for f in k["facts"]}
    assert sources == {"sap", "crm"} and k["dimension"] == "dim_customer" and k["customers"] == 5
    assert {"fact_sap_sales_order", "fact_crm_opportunity"} <= {f["name"] for f in k["facts"]}
    assert k["fact_to_fact"] == [] and all(r["to"] == "dim_customer.customer_key" for r in k["relationships"])
    assert len(k["relationships"]) == len(k["facts"])
    rel = m["parts"]["definition/relationships.tmdl"]
    assert rel.count("toColumn: dim_customer.customer_key") == len(k["facts"])
    assert "toColumn: fact_" not in rel                                                   # no link between facts
    assert 'Sql.Database("mlh.datawarehouse.fabric.microsoft.com", "sales_product_lh")' in m["parts"]["definition/expressions.tmdl"]
    assert m["layers_to"] == "model → sales_product_lh (gold)" and m["first"].startswith("Build the conformed gold first")
    assert {"sap.KNA1.TELF1", "crm.Account.Name"} <= set(k["personal_left_out"])


def test_the_gold_sql_keys_each_source_row_once(monkeypatch):
    _walk(monkeypatch)
    g = json.loads(server.create_semantic_model(**ARGS, name="m"))["gold_sql"]
    x, dim = g["xref_customer"], g["dim_customer"]
    assert x.startswith("CREATE OR REPLACE TABLE `gold`.`xref_customer`") and "`sap`.`KNA1`" in x and "`crm`.`Account`" in x
    assert "REGEXP_REPLACE(" in x and "ORDER BY COUNT(*) DESC" in x                       # normalised, within one client
    assert "'M0' END AS match_rule" in x and "only_in" in x
    assert "GROUP BY customer_key" in dim and "TELF1" not in dim                          # one row per customer
    f = g["fact_sap_sales_order"]
    assert "f.`MANDT` = x.`sap_MANDT` AND f.`KUNNR` = x.`sap_KUNNR`" in f and "SELECT DISTINCT customer_key" in f


def test_the_gold_sql_runs_and_conforms_the_fixture(monkeypatch):
    """The xref and dim_customer statements, translated to SQLite by fixed replacements, on the fixture's rows."""
    ws, p, found = _counted(monkeypatch)
    c = combine.accepted(found, [{"item": MATCH, "review": "accepted"}])
    g = combine.gold_sql(c, p, found["facts"])
    con = ws.connect("sales_product_lh")
    con._con.execute("ATTACH DATABASE ':memory:' AS gold")

    def lite(sql):
        sql = sql.replace("CREATE OR REPLACE TABLE", "CREATE TABLE")
        sql = sql.replace("CREATE OR REPLACE VIEW `gold`.", "CREATE TEMP VIEW ")     # SQLite: a view reads one file
        sql = sql.replace("`", '"').replace(" AS STRING)", " AS TEXT)")
        sql = sql.replace("REGEXP_REPLACE(", "LTRIM(").replace(", '^0+', '')", ", '0')").replace("TRUE", "1")
        return sql.replace("LEFT ANTI JOIN m ON a.\"crm_Id\" = m.\"crm_Id\")", "WHERE a.\"crm_Id\" NOT IN (SELECT \"crm_Id\" FROM m))")
    for name in ("xref_customer", "dim_customer", "fact_sap_sales_order", "fact_crm_opportunity"):
        con._con.execute(lite(g[name]))
    rows = con._con.execute('SELECT COUNT(*), COUNT(DISTINCT customer_key) FROM gold.dim_customer').fetchone()
    assert rows == (5, 5) == (combine.customers(c), combine.customers(c))
    per_account = con._con.execute('SELECT COUNT(*) FROM gold.xref_customer WHERE "crm_Id" IS NOT NULL').fetchone()[0]
    assert per_account == 5                                                               # each account once
    one_key = con._con.execute('SELECT MAX(n) FROM (SELECT COUNT(DISTINCT customer_key) AS n FROM gold.xref_customer '
                               'GROUP BY "sap_MANDT", "sap_KUNNR")').fetchone()[0]
    assert one_key == 1                                                                   # each SAP customer once
    vbak = con._con.execute('SELECT COUNT(*) FROM "sap"."VBAK"').fetchone()[0]
    assert con._con.execute('SELECT COUNT(*) FROM fact_sap_sales_order').fetchone()[0] == vbak   # no doubled rows
    con.close()


def test_create_of_the_combined_model_is_not_offered_yet(monkeypatch):
    _walk(monkeypatch)
    a = json.loads(server.create_semantic_model(**ARGS, name="m", dry_run=False))
    assert a["kind"] == "not_yet" and mlh.WRITES == []


# ------------------------------------------------------------------------------------------------ nothing else changes
def test_one_schema_and_the_demo_are_unchanged(monkeypatch):
    mlh.install(monkeypatch, "b")
    one = json.loads(server.start(workspace=W, source="sales_product_lh", schema="sap", step="check"))
    assert "match" not in one and not any("only in" in x for x in one.get("lines") or [])
    monkeypatch.undo()
    wb15_fake.install(monkeypatch)
    chosen = json.loads(server.start())["chosen"]
    d = json.loads(server.start(**{k: chosen[k] for k in ("workspace", "source", "schema")}, step="dry_run"))
    assert "combined" not in d and d["say"] == "One tap dry-runs everything. Nothing is created."
    assert not multi_schema.is_multi(chosen["schema"]) and sf.MATCH == combine.PREFIX


def test_the_cached_demo_validation_is_the_same_whoever_calls_first():
    """The start card's sample (start_flow.sample_products) may be the first to call demo.demo_validation, inside a
    tool call's time budget; the cached answer must not carry that budget (tests/test_golden.py compares it)."""
    from fabric_backend import budget, demo
    demo.demo_validation.cache_clear()
    try:
        with budget.call(30):
            inside = demo.demo_validation()
        assert "time_budget" not in inside
    finally:
        demo.demo_validation.cache_clear()
    assert demo.demo_validation() == inside

