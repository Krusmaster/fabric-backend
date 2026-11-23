"""BL46 (backlog B-24, BL43 follow-up), 23 November 2026: the security-role candidates in the model dry run.

create_semantic_model's dry run lists the row-level security roles security_roles.candidates proposes (by rule, with the
column and the tables each filters) as `role_candidates`, off by default: nothing is added to the model unless the
caller passes the roles they accept (`roles=["BUKRS"]`), as a key or a link is accepted. The workload's model output
takes the same list (outputs[{kind: semantic_model, roles}]) and its card shows the roles. Without `roles` the model's
parts and summary are as before; a source with no candidate (the synthetic shop) answers exactly as before. An unknown
role is refused in plain words before anything is read. Names only: no row value is read or shown.

Synthetic data only: the shop sample and the SAP-shaped demo (sap_demo.py; not SAP data, not an SAP system)."""
import json

import pytest

from fabric_backend import sap_demo, security_roles as sr, seed, server, workload_api
from fabric_backend.infer import plan

WS = "11111111-1111-1111-1111-111111111111"
INFO = {"workspace_id": WS, "item_id": "33333333-3333-3333-3333-333333333333", "item_name": "demo_lh", "item_kind": "Lakehouse",
        "schema": "sap", "sql_endpoint": "h", "sql_db": "demo_lh", "schemas_enabled": True, "onelake_tables_path": ""}


def _fabric(monkeypatch, p, schema):
    items = [{"id": "lh", "displayName": "demo_lh", "type": "Lakehouse", "description": ""}]
    read = []
    monkeypatch.setattr(server, "_source_inputs", lambda workspace, source, sch, keys, confirmed, ctx: (p, {**INFO, "schema": schema}))
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server, "_list_items", lambda ws, headers: list(items))
    monkeypatch.setattr(server, "_model_reads", lambda *a, **k: read.append(1) or {"date_range": None, "whole": set(), "said": []})
    monkeypatch.setattr(server, "_model_replacement", lambda *a, **k: None)
    monkeypatch.setattr(server, "_source_schemas", lambda workspace, source, ctx: [{"schema": schema, "tables": len(p.schema.tables)}])
    monkeypatch.setattr(server, "_create_semantic_model", lambda body, ws, token_provider=None: {"status": "Succeeded", "id": "m-1", "mode": "created"})
    return read


@pytest.fixture
def sap(monkeypatch):
    schema, _execute = sap_demo.sqlite()
    p = plan(schema)
    return p, _fabric(monkeypatch, p, p.schema.schema)


@pytest.fixture
def shop(monkeypatch):
    p = plan(seed.schema("shop"))
    return p, _fabric(monkeypatch, p, "shop")


def _dry(**kw) -> dict:
    return json.loads(server.create_semantic_model("demo", "demo_lh", "sap_model", schema="sap", **kw))


def _roles(parts: dict) -> list[str]:
    return sorted(k for k in parts if k.startswith("definition/roles/"))


# ------------------------------------------------------------------ default unchanged --------------------------------

def test_without_roles_the_model_is_unchanged_and_the_shop_answers_as_before(sap, shop):
    p, _ = shop
    out = json.loads(server.create_semantic_model("demo", "demo_lh", "shop_model", schema="shop"))
    same = json.loads(server.create_semantic_model("demo", "demo_lh", "shop_model", schema="shop", roles=None))
    assert out == same and "role_candidates" not in out                     # the shop proposes none: not a key more
    assert not _roles(out["parts"]) and "security_roles" not in out["summary"]


def test_without_roles_the_sap_model_has_no_role_and_the_same_parts(sap):
    out = _dry()
    assert not _roles(out["parts"]) and "security_roles" not in out["summary"]
    assert f"definition/tables/{sr.MAP_TABLE}.tmdl" not in out["parts"]
    assert _dry(roles=None)["parts"] == _dry(roles=[])["parts"] == out["parts"]


# ------------------------------------------------------------------ the dry run lists the candidates ------------------

def test_the_dry_run_lists_bukrs_with_its_rule_column_and_tables_as_a_proposal(sap):
    out = _dry()
    rc = out["role_candidates"]
    assert rc["written"] is False and rc["map_table"] == sr.MAP_TABLE and "nothing is added" in rc["how"]
    by = {r["column"]: r for r in rc["proposed"]}
    assert list(by)[:2] == ["BUKRS", "VKORG"] and "MANDT" in by          # the systems' own names, in the rules' order
    b = by["BUKRS"]
    assert b["rule"] == "S1" and b["role"] == "Rows by company code (BUKRS)"
    assert b["filters"] == ["sap_t001", "sap_tvko", "sap_vbrk"]
    assert b["fits"] is True and b["added"] is False and b["why"].startswith("S1:")
    assert not any(r["added"] for r in rc["proposed"])


def test_the_candidates_carry_names_only_never_a_row_value(sap):
    _schema, execute = sap_demo.sqlite()
    values = {str(next(iter(row.values()))) for row in execute("SELECT DISTINCT BUKRS FROM sap_t001")}
    assert values
    text = json.dumps(_dry()["role_candidates"])
    assert not any(f'"{v}"' in text for v in values)                    # a company code's value is never shown


def test_a_table_filter_without_a_roles_tables_says_it_would_not_fit(sap):
    out = _dry(tables=["sap_vbak", "sap_vbap"])
    by = {r["column"]: r for r in out["role_candidates"]["proposed"]}
    assert by["BUKRS"]["fits"] is False and "not in this model" in by["BUKRS"]["why_not"]


# ------------------------------------------------------------------ accepting a role adds it --------------------------

def test_passing_the_accepted_role_adds_it_and_only_it(sap):
    plain, out = _dry(), _dry(roles=["BUKRS"])
    assert _roles(out["parts"]) == ["definition/roles/Rows by company code (BUKRS).tmdl"]
    shown = set(out["parts"]) | set(out.get("omitted") or [])         # a long dry run leaves the table files out by name
    assert f"definition/tables/{sr.MAP_TABLE}.tmdl" in shown
    assert f"ref table {sr.MAP_TABLE}" in out["parts"]["definition/model.tmdl"]
    s = out["summary"]["security_roles"]
    assert [r["column"] for r in s["added"]] == ["BUKRS"] and s["written"] is False and "Fill this in" in s["fill_in"]
    by = {r["column"]: r for r in out["role_candidates"]["proposed"]}
    assert by["BUKRS"]["added"] is True and by["VKORG"]["added"] is False
    assert {k: v for k, v in out["parts"].items() if k in plain["parts"] and k != "definition/model.tmdl"} == \
        {k: v for k, v in plain["parts"].items() if k != "definition/model.tmdl"}           # nothing else moved
    assert sorted(set(out.get("omitted") or []) - {f"definition/tables/{sr.MAP_TABLE}.tmdl"}) == sorted(plain.get("omitted") or [])
    assert out["dry_run"] is True


def test_a_role_is_found_by_its_column_in_any_case_and_said_once(sap):
    out = _dry(roles=["bukrs", "BUKRS"])
    assert [r["column"] for r in out["summary"]["security_roles"]["added"]] == ["BUKRS"]


def test_create_sends_the_accepted_role_in_the_definition(sap, monkeypatch):
    import base64
    sent = []
    monkeypatch.setattr(server, "_create_semantic_model",
                        lambda body, ws, token_provider=None: sent.append(body) or {"status": "Succeeded", "id": "m-1", "mode": "created"})
    json.loads(server.create_semantic_model("demo", "demo_lh", "sap_model", schema="sap", roles=["BUKRS"], dry_run=False))
    paths = [x["path"] for x in sent[0]["definition"]["parts"]]
    assert "definition/roles/Rows by company code (BUKRS).tmdl" in paths
    role = next(x for x in sent[0]["definition"]["parts"] if x["path"].startswith("definition/roles/"))
    assert "USERPRINCIPALNAME()" in base64.b64decode(role["payload"]).decode()


# ------------------------------------------------------------------ an unknown role is refused -----------------------

def test_an_unknown_role_is_refused_in_plain_words_before_anything_is_read(sap):
    _p, read = sap
    out = _dry(roles=["KUNNR"])
    assert out["kind"] == "bad_input" and "'KUNNR' is not a role proposed" in out["error"]
    assert "BUKRS" in out["error"] and "Nothing was read or written" in out["error"]
    assert not read                                                    # refused before the model's reads
    assert "parts" not in out


def test_the_shop_refuses_any_role_and_says_none_is_proposed(shop):
    out = json.loads(server.create_semantic_model("demo", "demo_lh", "shop_model", schema="shop", roles=["country"]))
    assert out["kind"] == "bad_input" and "none (no column here names a unit" in out["error"]


def test_a_malformed_roles_list_is_refused(sap):
    assert _dry(roles=[""])["kind"] == "bad_input"


# ------------------------------------------------------------------ the workload's model output ----------------------

BASE = {"workspace": "demo", "source": "demo_lh", "schema": "sap", "review": {}}


def test_the_workload_request_takes_roles_on_the_model_output_only():
    got = workload_api.build_request({**BASE, "outputs": [{"kind": "semantic_model", "name": "m", "roles": ["BUKRS"]}]})
    assert got["outputs"][0]["roles"] == ["BUKRS"]
    plain = workload_api.build_request({**BASE, "outputs": [{"kind": "semantic_model", "name": "m"}]})
    assert "roles" not in plain["outputs"][0]
    for bad in ("BUKRS", [1], ["a b"], ["x"] * 21):
        with pytest.raises(workload_api.BadRequest):
            workload_api.build_request({**BASE, "outputs": [{"kind": "semantic_model", "name": "m", "roles": bad}]})


def test_the_workload_passes_the_accepted_roles_and_nothing_else_by_default():
    calls = []

    class S:
        @staticmethod
        def create_semantic_model(**kw):
            calls.append(kw)
            return "{}"
    common = {"workspace": "demo", "source": "demo_lh", "schema": "sap", "keys": None, "confirmed": None, "dry_run": True}
    workload_api._call_tool(S, "semantic_model", {"kind": "semantic_model", "name": "m"}, {}, {}, None, None, True, {}, common, {})
    workload_api._call_tool(S, "semantic_model", {"kind": "semantic_model", "name": "m", "roles": ["BUKRS"]}, {}, {}, None, None,
                            True, {}, common, {})
    assert "roles" not in calls[0] and calls[1]["roles"] == ["BUKRS"]


def test_the_workload_card_shows_the_roles_from_the_dry_run(sap):
    card = workload_api.role_card(_dry()["role_candidates"])
    assert card["written"] is False and "Nothing is written until Create" in card["how"]
    b = next(r for r in card["proposed"] if r["column"] == "BUKRS")
    assert b == {"role": "Rows by company code (BUKRS)", "column": "BUKRS", "rule": "S1",
                 "filters": ["sap_t001", "sap_tvko", "sap_vbrk"], "why": b["why"], "fits": True, "added": False}
