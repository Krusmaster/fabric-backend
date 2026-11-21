"""2026-11-21, round BL25: the Dataverse $metadata reader (layer 2), on a synthetic $metadata and the synthetic
Dynamics 365 demo lake. Asserts keys, plain and filtered links, the many-to-many, what does not map, and that nothing is
fetched."""
from __future__ import annotations

import socket
from pathlib import Path

import pytest

from fabric_backend import dataverse_meta as dm
from fabric_backend import dynamics_demo as dd

FIXTURE = Path(__file__).parent / "fixtures" / "dataverse_metadata_demo.xml"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any socket opened while a test runs fails the test: the reader reads a file and fetches nothing."""
    def refuse(*a, **k):
        raise AssertionError("dataverse_meta opened a network connection")
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(scope="module")
def model():
    return dm.read(FIXTURE)


@pytest.fixture(scope="module")
def demo():
    return dd.sqlite()


@pytest.fixture(scope="module")
def report(model, demo):
    return dm.candidates(demo[0], model)


def _pairs(rels):
    return {(r["source"], r["source_cols"][0], r["target"], r["target_cols"][0]) for r in rels}


def test_reads_entity_types_keys_and_inherited_key(model):
    assert set(model.entities) == {"transactioncurrency", "account", "contact", "product", "opportunity", "competitor",
                                   "opportunitycompetitors", "salesorder", "salesorderdetail", "activitypointer", "phonecall"}
    assert model.abstract == ["crmbaseentity"]
    assert model.namespace == "Microsoft.Dynamics.CRM" and model.alias == "mscrm"
    assert model.entities["account"].keys == ["accountid"]
    assert model.entities["salesorderdetail"].keys == ["salesorderdetailid"]
    pc = model.entities["phonecall"]
    assert pc.keys == ["activityid"] and pc.key_from == "activitypointer"
    assert {"activityid", "subject", "phonenumber"} <= set(pc.properties)


def test_lookups_carry_the_lake_column_name(model):
    sod = {lk.nav: lk for lk in model.entities["salesorderdetail"].lookups}
    assert sod["salesorderid"].prop == "_salesorderid_value"
    assert sod["salesorderid"].column == "salesorderid"
    assert sod["salesorderid"].referenced == "salesorderid" and sod["salesorderid"].target == "salesorder"
    assert dm.lake_column("_parentcustomerid_value") == "parentcustomerid"
    assert dm.lake_column("name") == "name"


def test_polymorphic_lookups_are_found(model):
    assert {p: sorted(lk.target for lk in v) for p, v in model.entities["salesorder"].polymorphic().items()} == \
        {"_customerid_value": ["account", "contact"]}
    assert set(model.entities["contact"].polymorphic()) == {"_parentcustomerid_value"}
    assert model.entities["account"].polymorphic() == {}


def test_keys_on_the_demo_lake(report):
    assert report["keys"]["account"] == ["accountid"]
    assert report["keys"]["salesorder"] == ["salesorderid"]
    assert report["keys"]["salesorderdetail"] == ["salesorderdetailid"]
    assert report["keys"]["activitypointer"] == ["activityid"]
    assert report["provenance"] == "declared by Dataverse metadata, not counted"
    assert "not verified against the rows" in report["status"]


def test_plain_links_in_the_csn_candidate_shape(report):
    assert _pairs(report["links"]) == {
        ("account", "parentaccountid", "account", "accountid"),
        ("account", "primarycontactid", "contact", "contactid"),
        ("account", "transactioncurrencyid", "transactioncurrency", "transactioncurrencyid"),
        ("opportunity", "parentaccountid", "account", "accountid"),
        ("salesorder", "opportunityid", "opportunity", "opportunityid"),
        ("salesorder", "transactioncurrencyid", "transactioncurrency", "transactioncurrencyid"),
        ("salesorderdetail", "salesorderid", "salesorder", "salesorderid"),
        ("salesorderdetail", "productid", "product", "productid"),
    }
    for r in report["links"]:
        assert {"source", "source_cols", "target", "target_cols", "rule", "provenance", "declared_in", "note"} <= set(r)
        assert r["rule"] == dm.RULE and r["provenance"] == dm.PROVENANCE
        assert "filter" not in r


def test_polymorphic_lookups_are_filtered_links_never_plain(report):
    assert _pairs(report["filtered"]) == {
        ("contact", "parentcustomerid", "account", "accountid"),
        ("contact", "parentcustomerid", "contact", "contactid"),
        ("salesorder", "customerid", "account", "accountid"),
        ("salesorder", "customerid", "contact", "contactid"),
    }
    filters = {(r["source"], r["target"]): r["filter"] for r in report["filtered"]}
    assert filters[("salesorder", "contact")] == {"column": "customeridtype", "value": "contact"}
    assert filters[("contact", "account")] == {"column": "parentcustomeridtype", "value": "account"}
    plain = {(r["source"], r["source_cols"][0]) for r in report["links"]}
    assert ("salesorder", "customerid") not in plain and ("contact", "parentcustomerid") not in plain


def test_many_to_many_is_listed_not_applied(model, report):
    assert len(model.many_to_many) == 1
    mm = model.many_to_many[0]
    assert sorted(mm["entities"]) == ["competitor", "opportunity"] and mm["intersect"] == "opportunitycompetitors"
    rows = [x for x in report["not_applied"] if "many_to_many" in x]
    assert len(rows) == 1 and "intersect" in rows[0]["why"]


def test_what_does_not_map_is_reported(report):
    assert sorted(u["entity"] for u in report["unmatched"]) == ["competitor", "opportunitycompetitors", "phonecall"]
    assert [(u["table"], u["column"]) for u in report["unmapped_columns"]] == [("account", "revenue")]
    assert report["ambiguous"] == []
    assert set(report["system_columns"]["account"]) == {"Id", "IsDelete", "SinkCreatedOn", "versionnumber"}
    assert "owneridtype" in report["extra_columns"]["account"]                 # in the lake, not in this $metadata
    assert {i["what"] for i in report["ignored"]} == {"Action", "ComplexType", "EntityContainer", "EnumType", "Function"}


def test_declared_links_join_the_demo_rows(report, demo):
    """The candidates are usable as they stand: every plain and filtered link joins the synthetic rows without an
    orphan (validate_plan does the real count once they are fed to the plan; this only shows the shape is right)."""
    _, execute = demo
    for r in report["links"] + report["filtered"]:
        s, sc, t, tc = r["source"], r["source_cols"][0], r["target"], r["target_cols"][0]
        where = f" AND s.[{r['filter']['column']}] = '{r['filter']['value']}'" if "filter" in r else ""
        sql = (f"SELECT COUNT(*) AS n FROM dynamics.[{s}] s LEFT JOIN dynamics.[{t}] t ON s.[{sc}] = t.[{tc}] "
               f"WHERE s.[{sc}] IS NOT NULL AND t.[{tc}] IS NULL{where}")
        assert execute(sql)[0]["n"] == 0, (s, sc, t)


def test_a_missing_type_column_is_not_applied(model):
    from fabric_backend.schema import Schema
    info = [("d", "salesorder", c, "nvarchar", i) for i, c in enumerate(["salesorderid", "customerid"], 1)]
    info += [("d", "account", "accountid", "nvarchar", 1), ("d", "contact", "contactid", "nvarchar", 1)]
    rep = dm.candidates(Schema.from_information_schema(info, schema="d"), model)
    assert not [r for r in rep["filtered"] if r["source"] == "salesorder"]
    why = [x["why"] for x in rep["not_applied"] if x.get("lookup", "").startswith("salesorder.customerid_")]
    assert len(why) == 2 and all("no customeridtype column" in w for w in why)


def test_layer_prefix_and_case(model):
    from fabric_backend.schema import Schema
    info = [("d", "bronze_SalesOrder", c, "nvarchar", i) for i, c in enumerate(["SalesOrderId", "OpportunityId"], 1)]
    info += [("d", "bronze_Opportunity", "OpportunityId", "nvarchar", 1)]
    rep = dm.candidates(Schema.from_information_schema(info, schema="d"), model)
    assert rep["matched"]["salesorder"]["table"] == "bronze_SalesOrder"
    assert ("bronze_SalesOrder", "OpportunityId", "bronze_Opportunity", "OpportunityId") in _pairs(rep["links"])


def test_reads_text_and_bytes_the_same(model):
    raw = FIXTURE.read_bytes()
    assert set(dm.read(raw).entities) == set(model.entities)
    assert set(dm.read(raw.decode("utf-8")).entities) == set(model.entities)


def test_a_url_is_refused_and_nothing_is_fetched():
    with pytest.raises(ValueError, match="fetches nothing"):
        dm.read("https://example.invalid/api/data/v9.2/$metadata")


def test_doctype_and_entities_are_refused():
    bad = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx"/>'
    with pytest.raises(ValueError, match="DOCTYPE or ENTITY"):
        dm.read(bad)


def test_not_csdl_is_refused():
    with pytest.raises(ValueError, match="not an OData CSDL"):
        dm.read("<root/>")


def test_summary_is_json_and_says_candidates(model):
    import json
    s = json.loads(json.dumps(dm.summary(model)))
    assert s["entities"]["salesorder"]["lookups"][0]["polymorphic"] is True
    assert "candidates" in s["note"]


def test_no_network_library_is_imported():
    src = Path(dm.__file__).read_text(encoding="utf-8")
    for lib in ("urllib", "requests", "httpx", "http.client", "socket", "aiohttp"):
        assert f"import {lib}" not in src and f"from {lib}" not in src
