"""BL43 (backlog B-24, BL17 follow-up), 23 November 2026: security roles in the semantic model dry run, off by default.

semantic_model.draft(..., roles=[column]) adds BL17's row-level role (security_roles.draft) and the security_user_map
table with its "fill this in" note; without `roles` the model is byte-equal to before. On the synthetic SAP demo BUKRS
gives one role that model_compare's TMDL reader parses; the shop proposes none, so nothing is added."""
import pytest

from fabric_backend import evidence, model_compare, sap_demo, security_roles as sr, semantic_model
from fabric_backend.infer import plan as infer_plan
from fabric_backend.platforms import local

INFO = {"schema": "sap", "item_name": "sap_lh", "item_kind": "Lakehouse", "sql_endpoint": "x.example", "sql_db": "sap_lh"}


@pytest.fixture(scope="module")
def sap():
    schema, execute = sap_demo.sqlite()
    p = infer_plan(schema)
    return p, evidence.validate(p, execute, 200)


def test_without_roles_the_model_is_unchanged(sap):
    p, v = sap
    a = semantic_model.draft(p, INFO, validation=v)
    b = semantic_model.draft(p, INFO, validation=v, roles=None)
    c = semantic_model.draft(p, INFO, validation=v, roles=[])
    assert a["parts"] == b["parts"] == c["parts"] and "security_roles" not in a["summary"] and "security_roles" not in c["summary"]


def test_bukrs_adds_one_role_and_the_map_table_and_it_parses(sap):
    p, v = sap
    out = semantic_model.draft(p, INFO, validation=v, roles=["BUKRS"])
    roles = [k for k in out["parts"] if k.startswith("definition/roles/")]
    assert roles == ["definition/roles/Rows by company code (BUKRS).tmdl"]
    assert f"definition/tables/{sr.MAP_TABLE}.tmdl" in out["parts"]
    assert f"ref table {sr.MAP_TABLE}" in out["parts"]["definition/model.tmdl"]
    s = out["summary"]["security_roles"]
    assert [r["column"] for r in s["added"]] == ["BUKRS"] and s["written"] is False and "Fill this in" in s["fill_in"]
    model = model_compare.from_tmdl(out["parts"])                     # the whole definition still reads
    assert model is not None
    plain = semantic_model.draft(p, INFO, validation=v)
    assert {k: x for k, x in out["parts"].items() if k in plain["parts"] and k != "definition/model.tmdl"} == \
        {k: x for k, x in plain["parts"].items() if k != "definition/model.tmdl"}           # nothing else moved


def test_a_role_whose_tables_are_not_in_the_model_is_not_added(sap):
    p, v = sap
    some = [t for t in p.schema.tables][:1]
    out = semantic_model.draft(p, INFO, validation=v, tables=some, roles=["BUKRS"])
    s = out["summary"]["security_roles"]
    if s["added"]:                                                   # only when the one table carries BUKRS itself
        assert all(set(r["tables"]) <= set(some) for r in s["added"])
    else:
        assert s["not_added"] and "not in this model" in s["not_added"][0]["why"]
        assert not any(k.startswith("definition/roles/") for k in out["parts"])


def test_the_shop_proposes_none_so_none_is_added():
    src = local.sample_source()
    p = infer_plan(src.schema)
    v = evidence.validate(p, src.execute, 200)
    assert sr.candidates(p) == []
    out = semantic_model.draft(p, {**INFO, "schema": src.schema.schema}, validation=v, roles=["BUKRS"])
    assert not any(k.startswith("definition/roles/") for k in out["parts"])
    assert out["summary"]["security_roles"]["not_added"][0]["column"] == "BUKRS"
