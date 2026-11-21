"""BL17 (21 Nov 2026): row-level and object-level security drafted from the plan (fabric_backend/security_roles.py,
docs/SECURITY-ROLES.md).

On the synthetic SAP demo the rules propose BUKRS and VKORG; on the synthetic shop they propose none. The TMDL parses
with the reader compare_semantic_model uses, no row value reaches any output, and nothing talks to a service.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from fabric_backend import evidence, model_compare, sap_demo, security_roles as sr
from fabric_backend.infer import plan as infer_plan
from fabric_backend.platforms import local
from fabric_backend.schema import Column, Schema, Table
from fabric_backend.semantic_model import has_object

DOC = Path(__file__).resolve().parents[1] / "docs" / "SECURITY-ROLES.md"


@pytest.fixture(scope="module")
def sap():
    schema, execute = sap_demo.sqlite()
    p = infer_plan(schema)
    return p, evidence.validate(p, execute, 200)


@pytest.fixture(scope="module")
def shop():
    src = local.sample_source()
    p = infer_plan(src.schema)
    return p, evidence.validate(p, src.execute, 200), src


def test_sap_demo_proposes_company_code_and_sales_org_first(sap):
    p, _ = sap
    cols = [c["column"] for c in sr.candidates(p)]
    assert cols[:2] == ["BUKRS", "VKORG"]
    bukrs = sr.candidates(p)[0]
    assert set(bukrs["tables"]) == {"sap_t001", "sap_tvko", "sap_vbrk"}
    assert bukrs["rule"] == "S1" and "company code" in bukrs["reason"] and "T001" in bukrs["reason"]


def test_shop_proposes_none_and_says_why(shop):
    p, v, _ = shop
    assert sr.candidates(p) == []
    passed = sr.passed_over(p)
    assert [(x["columns"]) for x in passed] == [[("customers", "country")]]
    md = sr.markdown(p, v)
    assert "no role is proposed" in md and "customers.country" in md


def test_generic_name_in_two_tables_or_a_key_is_proposed():
    two = Schema(tables={"stores": Table("stores", [Column("store_id"), Column("region")], keys=["store_id"]),
                         "sales": Table("sales", [Column("sale_id"), Column("store_id"), Column("region")], keys=["sale_id"])})
    assert [c["column"] for c in sr.candidates(infer_plan(two))] == ["region"]
    key = Schema(tables={"companies": Table("companies", [Column("company_code"), Column("label")], keys=["company_code"])})
    assert [c["kind"] for c in sr.candidates(infer_plan(key))] == ["company"]
    bc = Schema(tables={"SalesHeader-36": Table("SalesHeader-36", [Column("$Company"), Column("No-3")])})
    assert [c["rule"] for c in sr.candidates(infer_plan(bc))] == ["B1"]


def test_a_client_column_outside_sap_is_not_the_sap_client():
    s = Schema(tables={"jobs": Table("jobs", [Column("job_id"), Column("client")], keys=["job_id"])})
    assert sr.candidates(infer_plan(s)) == []


def test_role_filters_the_tables_with_the_column_and_reaches_others_over_counted_links_only(sap):
    p, v = sap
    r = sr.reach(p, "VKORG", v)
    assert {t for t, _ in r["direct"]} == {"sap_tvko", "sap_vbak", "sap_likp", "sap_vbrk"}
    held = {x.key for x in sr.counted_links(p, v)}
    for table, path in r["reached"].items():
        assert path and path[-1].source == table and all(x.key in held for x in path)
    assert "sap_vbap" in r["not_reached"]              # VBAP -> VBAK has the planted orphan, so it is not a counted link
    assert sr.reach(p, "VKORG")["reached"] == {}       # without a validation nothing is counted, nothing is reached
    assert set(r["reached"]) | {t for t, _ in r["direct"]} | set(r["not_reached"]) == {t.name for t in p.schema}


def test_tmdl_parses_with_the_compare_reader(sap):
    p, v = sap
    parts = sr.all_parts(p, v)
    assert "definition/roles/Rows by company code (BUKRS).tmdl" in parts
    assert "definition/roles/Without personal data.tmdl" in parts
    assert all(has_object(t) for t in parts.values())
    model = model_compare.from_tmdl(parts)
    assert set(model["tables"]) == {sr.MAP_TABLE}           # roles are not mistaken for tables
    assert set(model["tables"][sr.MAP_TABLE]["columns"]) == {c for c, _ in sr.MAP_COLUMNS}
    role = parts["definition/roles/Rows by company code (BUKRS).tmdl"]
    assert "role 'Rows by company code (BUKRS)'" in role and "\tmodelPermission: read" in role
    assert re.search(r"^\ttablePermission sap_t001 = 'sap_t001'\[BUKRS\] IN CALCULATETABLE\(.*USERPRINCIPALNAME\(\)", role, re.M)
    # every line of a role is a tab-indented property of the role, or a comment
    for line in role.splitlines():
        assert not line or line.startswith(("///", "role ", "\t"))


def test_client_role_maps_adrc_client_under_mandt(sap):
    p, v = sap
    role = sr.draft(p, "MANDT", v)["parts"]["definition/roles/Rows by client (MANDT).tmdl"]
    assert "'sap_adrc'[CLIENT] IN" in role and "[filter_column] = \"MANDT\"" in role


def test_ols_hides_every_flagged_column(sap, shop):
    from fabric_backend.privacy import personal_columns
    for p in (sap[0], shop[0]):
        ols = sr.ols_draft(p)
        assert {(x["table"], x["column"]) for x in ols["columns"]} == set(personal_columns(p.schema))
        text = ols["parts"]["definition/roles/Without personal data.tmdl"]
        assert text.count("metadataPermission: none") == len(ols["columns"])
        assert "\t\tcolumnPermission " in text and "\ttablePermission " in text


def test_unknown_column_is_refused(shop):
    with pytest.raises(ValueError, match="candidates: none"):
        sr.draft(shop[0], "country")


def _values(rows_by_table) -> set[str]:
    out = set()
    for _, (cols, _types, rows) in rows_by_table.items():
        for row in rows:
            out |= {str(x) for x in row if x is not None and len(str(x)) >= 3}
    return out


def test_no_row_value_in_any_output(sap, shop):
    p, v = sap
    names = {t.name.lower() for t in p.schema} | {c.lower() for t in p.schema for c in t.column_names}
    texts = [sr.markdown(p, v), *sr.all_parts(p, v).values(), repr(sr.candidates(p))]
    blob = "\n".join(texts)
    leaked = [x for x in _values(sap_demo.tables()) if x.lower() not in names and re.search(rf"(?<![\w.]){re.escape(x)}(?![\w.])", blob)]
    assert leaked == []
    sp, sv, src = shop
    shop_blob = sr.markdown(sp, sv) + "\n".join(sr.all_parts(sp, sv).values())
    for t in sp.schema:
        for row in src.execute(f"SELECT * FROM {t.name}"):
            for x in row.values():
                if isinstance(x, str) and len(x) >= 4 and x.lower() not in {c.lower() for c in t.column_names}:
                    assert x not in shop_blob, (t.name, x)


def test_nothing_reads_rows_or_calls_a_service(sap, monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    p, v = sap
    for c in sr.candidates(p):
        assert sr.draft(p, c["column"], v)["written"] is False
    assert sr.ols_draft(p)["written"] is False
    assert "Nothing is written" in sr.markdown(p, v)


def test_the_doc_says_what_the_module_does():
    text = DOC.read_text(encoding="utf-8")
    for word in ("BUKRS", "VKORG", "the shop proposes no role", "security_user_map", "metadataPermission: none",
                 "nothing is written", "counted link", "Next step"):
        assert word.lower() in text.lower(), word
