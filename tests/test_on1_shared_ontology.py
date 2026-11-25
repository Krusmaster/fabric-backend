"""ON1 (issue #152; docs/SMOOTH/COMBINE-SOURCES.md, docs/FABRIC-IQ-AT-SCALE.md section 9): one shared Fabric IQ ontology
over SAP and Dynamics 365, on the synthetic pair tests/fixtures/sap_dynamics.py (SAP demo + Dataverse demo, schemas
`sap` and `d365` of one product lakehouse).

What must hold: the customer match (`d365.account.accountnumber` -> `sap.KNA1.KUNNR`) and the product match
(`d365.product.productnumber` -> `sap.MARA.MATNR`) are found by the rules and counted exactly as the fixture says,
ambiguous rows apart; with both matches accepted, Customer and Product are one entity type each, with both sources and
the counts; every other concept is a single-source entity type; no relationship appears that the plan does not prove;
the dry run writes nothing, and dry_run=false writes nothing either (kind not_yet). Without an accepted match the
ontology is drafted exactly as before. Not run against Fabric: the fixture fails any POST, PATCH, PUT or DELETE."""
from __future__ import annotations

import json

import pytest
import wb15_fake
from fixtures import multi_lakehouse as mlh
from fixtures import sap_dynamics as sd

from fabric_backend import combine, flow_state, infer, ontology, server
from fabric_backend import shared_ontology as so
from fabric_backend.schema import Column, Schema, Table

ARGS = {"workspace": sd.WORKSPACE, "source": sd.SOURCE, "schema": sd.SCHEMA}
BOTH = [{"item": sd.CUSTOMER, "review": "accepted"}, {"item": sd.PRODUCT, "review": "accepted"}]


@pytest.fixture(autouse=True)
def _clean():
    flow_state.clear()
    yield
    assert mlh.WRITES == [] and wb15_fake.WRITES == []
    flow_state.clear()


def _counted(monkeypatch):
    ws = sd.install(monkeypatch)
    p, found = server._combine_concepts(sd.WORKSPACE, sd.SOURCE, sd.SCHEMA, None)
    return ws, p, found


def _accept(items):
    """The person's taps on the path: each match accepted through start's own decision (the flow state)."""
    kept = [{"item": i, "review": "accepted", "reason": "decided in the test"} for i in items]
    json.loads(server.start(**ARGS, step="decide", plan={"decisions": kept}))


# ------------------------------------------------------------------------------------------------ the matches, counted
@pytest.mark.parametrize("concept", ["customer", "product"])
def test_the_match_is_found_and_counted_exactly(monkeypatch, concept):
    _, _p, found = _counted(monkeypatch)
    want = sd.EXPECTED[concept]
    r = found[concept]
    assert r["proposed"] == want["id"] and r["concept"] == concept
    assert [c["id"] for c in r["candidates"]] == [want["id"]]                       # one candidate, no guess
    c = r["candidates"][0]
    assert c["rule"] == want["rule"] and c["holds"] and c["share"] == 1.0
    assert c["counts"] == want["counts"]
    k = c["counts"]
    assert k["matched"] + k["ambiguous"] + k["only_a"] == k["a_rows"]                 # every D365 row counted once
    assert k["b_found"] + k["only_b"] == k["b_rows"]                                  # every SAP row counted once
    assert combine.customers(c) == want["customers"]


def test_the_match_lines_say_matched_ambiguous_and_only_in_each_source(monkeypatch):
    _, _p, found = _counted(monkeypatch)
    cust, prod = (found[k]["candidates"][0] for k in ("customer", "product"))
    assert combine.match_line(cust) == ("SAP has 6 customers, D365 6 accounts. 3 accounts match on accountnumber after "
                                        "normalising, 2 ambiguous. 2 only in SAP, 1 only in D365.")
    assert combine.match_line(prod) == ("SAP has 4 materials, D365 3 products. 2 products match on productnumber after "
                                        "normalising. 2 only in SAP, 1 only in D365.")
    assert all(len(combine.match_line(c).split()) <= 25 for c in (cust, prod))
    ev = combine.evidence(cust)
    assert "5 of 6 d365.account rows hold a value; 2 match as written, 5 after normalising." in ev
    assert any(x.startswith("2 d365.account rows are ambiguous") and x.endswith("you decide.") for x in ev)
    assert ev[-1] == "Nothing is joined until you accept."
    assert not any("ambiguous" in x for x in combine.evidence(prod))


def test_the_counts_run_on_one_connection_and_read_no_row_value(monkeypatch):
    ws, p, found = _counted(monkeypatch)
    product = [c for c in ws.connections if c.lakehouse == sd.SOURCE]
    q = [x for c in product for x in c.queries if "accountnumber" in x or "productnumber" in x]
    assert len(q) == 4 == sum(found[k]["queries"] for k in found)
    assert all(x.lstrip().upper().startswith("SELECT COUNT_BIG(*)") for x in q)
    said = json.dumps(so.draft(p, found, BOTH), default=str)
    for value in ("0000000013", "Demo Customer 13", "Demo Account 5", "000000000000000002", "Demo Platform"):
        assert value not in said


def test_dataverse_system_columns_and_guid_lookups_are_never_a_match_key(monkeypatch):
    _, _p, found = _counted(monkeypatch)
    cols = {c["from"]["column"] for r in found.values() for c in r["candidates"]}
    assert cols == {"accountnumber", "productnumber"}                                  # not Id, versionnumber, *id
    assert combine._rule_words("accountnumber") >= {"account", "number"}
    assert combine._rule_words("new_sapcustomerno", {"sap"}) >= {"sap", "no"}          # names SAP: M0
    assert "id" not in combine._rule_words("parentaccountid")                         # GUID lookups are not split
    assert combine._rule_words("KUNNR") == {"kunnr"} and combine._rule_words("AccountNumber") == {"account", "number"}


def test_business_central_customer_and_item_take_part_by_the_same_rules():
    """No rows: the names are enough to propose the pairs; a count would follow on the rows."""
    sap = {"sap.KNA1": [Column("MANDT"), Column("KUNNR")], "sap.MARA": [Column("MANDT"), Column("MATNR")]}
    bc = {"bc.Customer": [Column("COMPANY"), Column("NO"), Column("NAME"), Column("SAP_CUSTOMER_NO")],
          "bc.Item": [Column("COMPANY"), Column("NO"), Column("DESCRIPTION"), Column("SAP_MATERIAL_NO")]}
    s = Schema(schema="sap+bc")
    for name, cols in {**sap, **bc}.items():
        s.tables[name] = Table(name, cols, [], schema="sap+bc")
    p = infer.Plan(s, keys={"sap.KNA1": (["MANDT", "KUNNR"], "x"), "sap.MARA": (["MANDT", "MATNR"], "x"),
                            "bc.Customer": (["COMPANY", "NO"], "x"), "bc.Item": (["COMPANY", "NO"], "x")},
                   pack={"pack": "sap", "by_schema": {"sap": "sap", "bc": "dynamics365"},
                         "tables": {"sap.KNA1": "KNA1", "sap.MARA": "MARA", "bc.Customer": "Customer", "bc.Item": "Item"}})
    assert combine.parties(p)["bc"]["tenant"] == "COMPANY" and combine.parties(p, "product")["bc"]["table"] == "bc.Item"
    cust = {(c["rule"], c["from"]["column"], c["to"]["table"], c["to"]["column"]) for c in combine.candidates(p)}
    prod = {(c["rule"], c["from"]["column"], c["to"]["table"], c["to"]["column"]) for c in combine.candidates(p, "product")}
    assert ("M0", "SAP_CUSTOMER_NO", "sap.KNA1", "KUNNR") in cust
    assert ("M0", "SAP_MATERIAL_NO", "sap.MARA", "MATNR") in prod
    assert not any(x[1] in ("NAME", "DESCRIPTION") for x in cust | prod)               # names are never a match


# ------------------------------------------------------------------------------------------------ the shared ontology
def test_shared_entities_record_both_sources_and_the_counted_match(monkeypatch):
    _, p, found = _counted(monkeypatch)
    m = so.draft(p, found, BOTH)
    by = {e["name"]: e for e in m["entities"]}
    assert m["summary"]["shared"] == ["Customer", "Product"]
    for name, concept, sap_t, d_t in (("Customer", "customer", "sap.KNA1", "d365.account"),
                                      ("Product", "product", "sap.MARA", "d365.product")):
        e = by[name]
        assert e["shared"] and [s["table"] for s in e["sources"]] == [sap_t, d_t]
        assert [s["source"] for s in e["sources"]] == ["sap", "d365"]
        assert e["binding"] == {"schema": "gold", "table": f"dim_{concept}", "built_by": "gold_sql"}
        assert e["key"] == f"{concept}_key" and e["properties"][0]["name"] == f"{concept}_key"
        assert e["match"]["id"] == sd.EXPECTED[concept]["id"] and e["match"]["state"] == "accepted"
        assert e["match"]["counts"] == sd.EXPECTED[concept]["counts"]
        assert f"CREATE OR REPLACE TABLE `gold`.`dim_{concept}`" in m["gold_sql"][f"dim_{concept}"]
    props = {x["name"] for x in by["Customer"]["properties"]}
    assert {"sap_KUNNR", "d365_accountid", "only_in"} <= props and "sap_TELF1" not in props   # personal data left out
    assert "only_in" in {x["name"] for x in by["Product"]["properties"]}


def test_concepts_without_a_match_stay_single_source(monkeypatch):
    _, p, found = _counted(monkeypatch)
    m = so.draft(p, found, BOTH)
    single = {e["name"]: e for e in m["entities"] if not e["shared"]}
    assert set(single) == {"SapOrder", "D365Order", "SapInvoice", "D365Invoice", "D365Opportunity", "SapDelivery",
                           "D365Case"}
    assert all(len(e["sources"]) == 1 and e["match"] is None for e in single.values())
    assert single["SapDelivery"]["sources"][0]["table"] == "sap.LIKP"                 # only in SAP
    assert single["D365Opportunity"]["sources"][0]["table"] == "d365.opportunity"     # only in Dynamics 365
    assert single["D365Order"]["binding"] == {"schema": "d365", "table": "salesorder", "built_by": "source"}
    assert single["SapOrder"]["binding"] == {"schema": "gold", "table": "fact_sap_sales_order", "built_by": "gold_sql"}
    assert any(n.startswith("Order: in d365 and sap, one entity type per source.") for n in m["notes"])


def test_without_an_accepted_match_nothing_is_shared(monkeypatch):
    _, p, found = _counted(monkeypatch)
    m = so.draft(p, found, [])
    assert m["summary"]["shared"] == [] and m["gold_sql"] == {}
    assert {"SapCustomer", "D365Customer", "SapProduct", "D365Product"} <= set(m["summary"]["single_source"])
    assert [(x["concept"], x["state"]) for x in m["matches"]] == [("Customer", "open"), ("Product", "open")]
    rejected = so.draft(p, found, [{"item": sd.CUSTOMER, "review": "rejected"}])
    assert [(x["concept"], x["state"]) for x in rejected["matches"]] == [("Customer", "rejected"), ("Product", "open")]


def test_no_relationship_appears_that_the_plan_does_not_prove(monkeypatch):
    _, p, found = _counted(monkeypatch)
    m = so.draft(p, found, BOTH)
    by = {e["name"]: e for e in m["entities"]}
    plan_links = {(r.source, r.source_cols[0], r.target) for r in p.relationships}
    rels = {(r["from"], r["to"]): r for r in m["relationships"]}
    assert set(rels) == {("SapOrder", "Customer"), ("SapInvoice", "Customer"), ("SapDelivery", "Customer"),
                         ("D365Opportunity", "Customer"), ("D365Order", "D365Opportunity"),
                         ("D365Invoice", "D365Order"), ("D365Invoice", "D365Opportunity")}
    for r in m["relationships"]:
        frm, to = by[r["from"]], by[r["to"]]
        if to["shared"]:                                    # a re-keyed fact: the plan's link to the party, plus the match
            assert (r["from_column"], r["to_column"]) == ("customer_key", "customer_key")
            assert r["proof"]["match"] == sd.CUSTOMER and r["proof"]["rule"].endswith(" pack")
            assert r["proof"]["plan"].endswith(("sap.KNA1.MANDT+KUNNR", "d365.account.accountid"))
        else:                                               # a plain link of the plan, inside one source
            assert frm["sources"][0]["source"] == to["sources"][0]["source"]
            assert (frm["sources"][0]["table"], r["from_column"], to["sources"][0]["table"]) in plan_links
    assert not [k for k in rels if k[1] == "Product" or k[0] == "Product"]            # no line in scope proves one
    assert ("D365Order", "Customer") not in rels                                      # customerid is a filtered lookup
    assert any("d365.salesorder.customerid -> d365.account.accountid holds only where customeridtype" in n for n in m["notes"])
    assert any(n.startswith("Not related: d365.incident.productid -> d365.product.productid") for n in m["notes"])
    assert len(m["relationships"]) == m["summary"]["relationship_types"] == 7


def test_the_definition_binds_each_entity_where_it_is_and_says_its_sources(monkeypatch):
    _, p, found = _counted(monkeypatch)
    m = so.draft(p, found, BOTH)
    parts = so.parts(m, "sales_360", workspace_id="w", item_id="i", item_name=sd.SOURCE)
    assert parts["model.tmdl"].count("ref entity ") == len(m["entities"]) == 9
    cust = parts["entities/Customer.tmdl"]
    assert cust.startswith("/// Customer from sap.KNA1 (MANDT+KUNNR); d365.account (accountid)\n/// " + sd.CUSTOMER)
    assert "keyProperty: customer_key" in cust
    assert "schemaName: gold" in parts["tables/Customer.tmdl"] and "entityName: dim_customer" in parts["tables/Customer.tmdl"]
    assert "schemaName: d365" in parts["tables/D365Order.tmdl"] and "entityName: salesorder" in parts["tables/D365Order.tmdl"]
    assert "keyProperty" not in parts["entities/SapOrder.tmdl"]                       # composite MANDT+VBELN: keyless
    rel = parts["relationships.tmdl"]
    assert rel.count("relationship ") == 7 and "toColumn: Customer.customer_key" in rel
    assert "toColumn: Product." not in rel


# ------------------------------------------------------------------------------------------------ the tool
def test_create_ontology_dry_run_is_the_shared_ontology_once_a_match_is_accepted(monkeypatch):
    sd.install(monkeypatch)
    _accept([sd.CUSTOMER])
    o = json.loads(server.create_ontology(**ARGS, name="sales_360"))
    assert o["dry_run"] is True and o["combined"]["shared"] == ["Customer"]
    assert o["combined"]["line"] == ("D365 + SAP → 10 entity types: Customer shared, 9 from one source; "
                                     "8 relationship types.")
    ask = o["actions"][0]
    assert ask["tool"] == "start" and ask["label"] == "Accept the product match"
    assert [d["item"] for d in ask["arguments"]["plan"]["decisions"]] == [sd.CUSTOMER, sd.PRODUCT]
    json.loads(server.start(**ask["arguments"]))                                     # the person's yes, on the path
    o = json.loads(server.create_ontology(**ARGS, name="sales_360"))
    assert o["combined"]["shared"] == ["Customer", "Product"] and "actions" not in o
    assert [x["state"] for x in o["combined"]["matches"]] == ["accepted", "accepted"]
    assert set(o["gold_sql"]) >= {"xref_customer", "dim_customer", "xref_product", "dim_product"}
    assert o["first"].startswith("Build the conformed gold first") and "Not run against Fabric" in o["note"]


def test_the_dry_run_writes_nothing_and_create_waits_for_the_gold(monkeypatch):
    sd.install(monkeypatch)
    _accept([sd.CUSTOMER, sd.PRODUCT])
    json.loads(server.create_ontology(**ARGS, name="sales_360"))
    a = json.loads(server.create_ontology(**ARGS, name="sales_360", dry_run=False))
    assert a["kind"] == "not_yet" and mlh.WRITES == []


def test_without_an_accepted_match_create_ontology_answers_as_before(monkeypatch):
    sd.install(monkeypatch)
    o = json.loads(server.create_ontology(**ARGS, name="sales_360"))
    assert "combined" not in o and o["dry_run"] is True
    p, args = server._ontology_inputs(sd.WORKSPACE, sd.SOURCE, sd.SCHEMA, None, None, None)
    assert set(o["parts"]) | set(o.get("omitted") or []) == set(ontology.ontology_parts(p, "sales_360", **args))
    assert server._combined_ontology(sd.WORKSPACE, sd.SOURCE, "sap", "x", True, None) is None      # one schema


def test_sap_and_salesforce_share_the_customer_the_same_way(monkeypatch):
    """SM7's fixture (SAP + CRM): the accepted M0 match gives one Customer over sap.KNA1 and crm.Account."""
    mlh.install(monkeypatch, "b")
    a = {"workspace": mlh.WORKSPACE, "source": "sales_product_lh", "schema": "crm+sap"}
    item = "match:crm.Account.SAP_Customer_No__c>sap.KNA1.KUNNR"
    json.loads(server.start(**a, step="decide", plan={"decisions": [{"item": item, "review": "accepted"}]}))
    o = json.loads(server.create_ontology(**a, name="sales_360"))
    cust = next(e for e in o["entities"] if e["name"] == "Customer")
    assert [s["table"] for s in cust["sources"]] == ["sap.KNA1", "crm.Account"] and cust["match"]["rule"] == "M0"
    assert cust["match"]["counts"]["ambiguous"] == 2 and cust["match"]["counts"]["matched"] == 2
