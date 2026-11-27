"""GR1 (27 November 2026): match_records, the same customer in a CRM, an ERP and an MDM hub, counted on the rows.

What must hold: the four normalisation rules do what their names say (run on SQLite); a rule is proposed by the
column's name and always shown; every bucket on the synthetic three-system set (fabric_backend/seed.py RECORDS) has the
count worked out by hand in the comments below; the SQL is SELECTs only and is shown per count; example keys are masked
when the key looks like personal data; the answer has counts.summary and next_steps, an error has error, kind and hint;
sides in different workspaces or on different SQL hosts are refused before anything is read; sides in two lakehouses of
one workspace are counted over one connection with three-part names; nothing writes to Fabric; the tool is registered
only with KRUSGRAPH_MATCH_RECORDS=1."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys

import pytest
from fixtures import multi_lakehouse as mlh

from fabric_backend import record_match as rm
from fabric_backend import server
from fabric_backend.dialects import TSQL, sqlite_sql
from fabric_backend.schema import Column, Table

WRITE_WORDS = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|EXEC|GRANT)\b", re.I)


def _sample(**kw) -> dict:
    return json.loads(server.match_records(sample=True, **kw))


# ------------------------------------------------------------------------------------------------ the rules
@pytest.mark.parametrize("rule, value, want", [
    ("N1", "  qx-1001-01 ", "QX-1001-01"),
    ("N2", " qx-1001.01 / ", "QX100101"),
    ("N2", "QX 1008 08", "QX100808"),
    ("N3", "  Info@Alpha.Example ", "info@alpha.example"),
    ("N4", "+46 70-123 45 67", "46701234567"),
    ("N4", "0046 (70) 123.45/67", "46701234567"),
    ("N4", "070-123 45 67", "0701234567"),
])
def test_each_rule_does_what_its_name_says(rule, value, want):
    con = sqlite3.connect(":memory:")
    got = con.execute(sqlite_sql(f"SELECT {rm.normal(':v', rule)}"), {"v": value}).fetchone()[0]
    assert got == want
    assert rule in rm.RULES and rm.RULES[rule]


def test_an_unknown_rule_is_refused():
    with pytest.raises(rm.MatchInputError) as e:
        rm.normal("x", "N9")
    assert e.value.kind == "bad_input"
    out = _sample(sides=[{**rm.SAMPLE_SIDES[0], "rules": "N7"}, rm.SAMPLE_SIDES[1]])
    assert out["kind"] == "bad_input" and "N7" in out["error"] and "N2" in out["hint"]


@pytest.mark.parametrize("column, rule", [("org_no", "N2"), ("VAT__c", "N2"), ("org_number", "N2"), ("email", "N3"),
                                          ("phone", "N4"), ("KUNNR", "N1"), ("customer_id", "N1")])
def test_a_rule_is_proposed_by_the_column_name(column, rule):
    assert rm.propose_rule("accounts", column)[0] == rule


def test_the_rules_are_always_shown_and_stcd1_takes_n2_beside_the_org_numbers():
    out = _sample()
    keys = {s["label"]: s["key"][0] for s in out["sides"]}
    assert {k: v["rule"] for k, v in keys.items()} == {"CRM": "N2", "ERP": "N2", "MDM": "N2"}
    assert keys["CRM"]["why"].startswith("proposed: org_no is named as an organisation number")
    assert keys["ERP"]["why"].startswith("proposed: N2, as for CRM's org_no")
    assert all(v["rule_says"] == rm.RULES["N2"] for v in keys.values())
    assert set(out["rules"]) == {"N1", "N2", "N3", "N4"}
    assert out["warnings"] == []
    # a rule chosen in the call wins and is said so; then the sides differ and the answer warns
    chosen = _sample(sides=[{**rm.SAMPLE_SIDES[0], "rules": "N1"}, rm.SAMPLE_SIDES[1]])
    assert chosen["sides"][0]["key"][0] == {"column": "org_no", "rule": "N1", "rule_says": rm.RULES["N1"],
                                           "why": "chosen in the call"}
    assert chosen["sides"][1]["key"][0]["rule"] == "N1"          # nothing named to align with: STCD1's own N1
    assert chosen["counts"]["pairs"][0]["counts"]["matched"] == 0  # dashes on one side, none on the other


# ------------------------------------------------------------------------------------------------ the buckets
# Normalised by N2, the CRM holds 11 keys (QX100808 twice, Lambda Lås without a number), the ERP 11 (QX101111 twice),
# the MDM 13. Over the pairs:
#   CRM + ERP: 8 matched (1001-1009 without 1008), 2 only in CRM (1010, 1016), 1 only in ERP (1212), 2 duplicated
#              (1008 in the CRM, 1111 in the ERP); conflicts: Delta's country (NO/SE) and Zeta's name.
#   CRM + MDM: 9 matched (1001-1010 without 1008), 1 only in CRM (1016), 3 only in MDM (1212, 1313, 1414), 1 duplicated
#              (1008); conflict: Delta's country. Candidate for a person: Omikron Optik, 1016 in the CRM, 1414 in the MDM.
#   ERP + MDM: 10 matched (1001-1009, 1212), 0 only in ERP, 3 only in MDM (1010, 1313, 1414), 1 duplicated (1111);
#              conflict: Zeta's name.
#   All three: 15 keys; 8 in all once each, 2 in some (1010, 1212), 3 in one only (1016, 1313, 1414), 2 duplicated,
#              2 conflicts (Delta, Zeta).
PAIRS = {
    ("CRM", "ERP"): {"keys_total": 13, "matched": 8, "only_in_a": 2, "only_in_b": 1, "duplicated": 2, "conflicts": 2,
                     "conflicts_by_field": {"name": 1, "country": 1}},
    ("CRM", "MDM"): {"keys_total": 14, "matched": 9, "only_in_a": 1, "only_in_b": 3, "duplicated": 1, "conflicts": 1,
                     "conflicts_by_field": {"name": 0, "country": 1}},
    ("ERP", "MDM"): {"keys_total": 14, "matched": 10, "only_in_a": 0, "only_in_b": 3, "duplicated": 1, "conflicts": 1,
                     "conflicts_by_field": {"name": 1, "country": 0}},
}


def test_every_bucket_of_every_pair_is_counted_as_worked_out_by_hand():
    out = _sample()
    got = {(p["a"], p["b"]): p["counts"] for p in out["counts"]["pairs"]}
    assert got == PAIRS
    for c in got.values():                                        # every key in exactly one bucket
        assert c["matched"] + c["only_in_a"] + c["only_in_b"] + c["duplicated"] == c["keys_total"]


def test_all_three_together_and_per_side():
    out = _sample()
    assert out["counts"]["all_sides"] == {"keys_total": 15, "in_all": 8, "in_some": 2, "in_one_only": 3, "duplicated": 2,
                                          "conflicts": 2}
    assert out["counts"]["per_side"] == [
        {"side": "CRM", "rows": 13, "rows_without_key": 1, "keys": 11, "keys_duplicated": 1, "rows_in_duplicated_keys": 2},
        {"side": "ERP", "rows": 12, "rows_without_key": 0, "keys": 11, "keys_duplicated": 1, "rows_in_duplicated_keys": 2},
        {"side": "MDM", "rows": 13, "rows_without_key": 0, "keys": 13, "keys_duplicated": 0, "rows_in_duplicated_keys": 0}]


def test_examples_are_the_first_keys_of_each_bucket():
    ex = {(p["a"], p["b"]): p["examples"] for p in _sample()["counts"]["pairs"]}
    assert ex[("CRM", "ERP")] == {"matched": ["QX100101", "QX100202", "QX100303"], "only_in_a": ["QX101010", "QX101616"],
                                  "only_in_b": ["QX101212"], "duplicated": ["QX100808", "QX101111"],
                                  "conflicts": ["QX100404", "QX100606"]}
    assert ex[("ERP", "MDM")]["only_in_a"] == []


def test_candidates_for_a_person_are_exact_names_only_and_never_matched():
    pairs = {(p["a"], p["b"]): p["candidates_for_a_person"] for p in _sample()["counts"]["pairs"]}
    assert pairs[("CRM", "MDM")]["pairs"] == [{"CRM": "QX101616", "MDM": "QX101414"}]
    assert pairs[("CRM", "MDM")]["count"] == 1 and "never matched" in pairs[("CRM", "MDM")]["rule"]
    assert pairs[("CRM", "ERP")]["count"] == 0
    # without a name field on both sides nothing is listed, and the answer says why
    no_name = [{**s, "compare": {"country": s["compare"]["country"]}} for s in rm.SAMPLE_SIDES]
    for p in _sample(sides=no_name)["counts"]["pairs"]:
        assert p["candidates_for_a_person"] == {"not_listed": "no compare field named name on both sides"}
        assert p["counts"]["matched"] + p["counts"]["conflicts"] >= p["counts"]["matched"]


def test_two_sides_give_one_pair_and_its_sentence():
    out = _sample(sides=rm.SAMPLE_SIDES[:2])
    assert "all_sides" not in out["counts"] and len(out["counts"]["pairs"]) == 1
    assert out["counts"]["summary"].startswith("Customer keys in CRM and ERP, normalised by N2: 8 matched, 2 only in CRM, "
                                               "1 only in ERP, 2 duplicated within a side; 2 of the matched differ on name or country.")


def test_a_composite_key_is_joined_part_by_part():
    sides = [{**rm.SAMPLE_SIDES[0], "key": ["org_no", "country"]}, {**rm.SAMPLE_SIDES[2], "key": ["org_number", "country_code"]}]
    out = _sample(sides=sides)
    assert [k["rule"] for k in out["sides"][0]["key"]] == ["N2", "N1"]
    c = out["counts"]["pairs"][0]["counts"]
    assert c["matched"] == 8                                      # Delta Logistik (NO in the CRM) no longer meets
    assert "CONCAT(" in out["queries"][0]["sql"]


# ------------------------------------------------------------------------------------------------ the SQL
def test_the_sql_is_selects_only_and_each_count_carries_its_statement():
    out = _sample()
    labels = [q["counts"] for q in out["queries"]]
    assert labels[:3] == ["side CRM", "side ERP", "side MDM"]
    assert "pair CRM + ERP" in labels and "examples CRM + ERP" in labels and "candidates CRM + MDM" in labels
    assert labels[-1] == "all sides"
    for q in out["queries"]:
        assert q["sql"].startswith("WITH ") and not WRITE_WORDS.search(q["sql"]), q["counts"]
        assert "COUNT_BIG(" in q["sql"] or q["counts"].startswith(("examples", "candidates"))
    pair = next(q["sql"] for q in out["queries"] if q["counts"] == "pair CRM + ERP")
    assert "FROM [crm].[accounts] AS t" in pair and "FROM [erp].[KNA1] AS t" in pair
    assert "REPLACE(REPLACE(REPLACE(REPLACE(UPPER(LTRIM(RTRIM(CAST(t.[org_no] AS NVARCHAR(4000))))), ' ', ''), '-', ''), '.', ''), '/', '')" in pair


def test_three_part_names_when_a_catalog_is_set():
    t = Table("accounts", [Column("org_no", "varchar")], schema="crm")
    side = rm.bind(rm.parse_sides([{"source": "crm_lh", "schema": "crm", "table": "accounts", "key": "org_no"},
                                   {"source": "erp_lh", "schema": "erp", "table": "accounts", "key": "org_no", "label": "b"}])[0],
                   t, TSQL.with_catalog("crm_lh").table("crm", "accounts"))
    assert "FROM [crm_lh].[crm].[accounts] AS t" in rm.side_sql(side)


# ------------------------------------------------------------------------------------------------ masking
def _email_sides():
    return [{"label": "A", "schema": "crm", "table": "accounts", "key": "email"},
            {"label": "B", "schema": "crm", "table": "accounts", "key": "email"}]


def test_example_keys_are_masked_when_the_key_looks_like_personal_data():
    out = _sample(sides=_email_sides())
    assert out["sides"][0]["key"][0]["rule"] == "N3"
    assert out["personal_data"]["masked"] is True
    assert out["personal_data"]["key_columns"][0]["rule"] == "P2"
    ex = out["counts"]["pairs"][0]["examples"]["matched"]
    assert ex and set(ex) == {"***"}
    assert "@" not in json.dumps(out["counts"])
    shown = _sample(sides=_email_sides(), show_personal_data=True)
    assert shown["personal_data"]["masked"] is False
    assert "info@alpha.example" in shown["counts"]["pairs"][0]["examples"]["matched"]


def test_org_numbers_are_not_masked_and_no_name_or_country_value_is_returned():
    out = _sample()
    assert out["personal_data"]["masked"] is False
    text = json.dumps({k: v for k, v in out.items() if k != "queries"})
    for value in ("Zeta Data Aktiebolag", "Delta Logistik", "Omikron", '"NO"'):
        assert value not in text


# ------------------------------------------------------------------------------------------------ the envelope
def test_the_answer_envelope():
    out = _sample()
    assert isinstance(out["counts"]["summary"], str)
    assert out["counts"]["summary"] == (
        "Customer keys in CRM, ERP and MDM, normalised by N2: 8 in all 3 once each, 2 in some but not all, 3 in one only, "
        "2 duplicated within a source (cannot match safely); 2 of those 8 differ on a compared field. 1 row has no key. "
        "Counted on the rows; nothing merged.")
    assert out["next_steps"][0]["label"] == "Decide per field which source wins; a golden record view comes next"
    assert "nothing is merged" in out["never"]
    assert out["where"]["sample"].startswith("the synthetic CRM, ERP and MDM")
    assert out["entity"] == "customer"
    assert _sample(entity="supplier")["counts"]["summary"].startswith("Supplier keys")


@pytest.mark.parametrize("sides, kind, words", [
    ([rm.SAMPLE_SIDES[0]], "bad_input", "2 or 3"),
    (rm.SAMPLE_SIDES + [rm.SAMPLE_SIDES[0]], "bad_input", "2 or 3"),
    ([{**rm.SAMPLE_SIDES[0], "table": "nope"}, rm.SAMPLE_SIDES[1]], "table_not_found", "nope"),
    ([{**rm.SAMPLE_SIDES[0], "key": "vat"}, rm.SAMPLE_SIDES[1]], "column_not_found", "vat"),
    ([rm.SAMPLE_SIDES[0], {**rm.SAMPLE_SIDES[1], "compare": {"name": "NAME9"}}], "column_not_found", "NAME9"),
    ([rm.SAMPLE_SIDES[0], {**rm.SAMPLE_SIDES[1], "label": "crm"}], "bad_input", "same label"),
    ([{**rm.SAMPLE_SIDES[0], "key": []}, rm.SAMPLE_SIDES[1]], "bad_input", "key"),
])
def test_errors_answer_error_kind_and_hint(sides, kind, words):
    out = _sample(sides=sides)
    assert set(out) == {"error", "kind", "hint"}
    assert out["kind"] == kind and words in out["error"] and out["hint"]


# ------------------------------------------------------------------------------------------------ Fabric (fixture)
def _fabric_sides(crm="sales_product_lh", sap="sales_product_lh", crm_schema="crm", sap_schema="sap"):
    return [{"label": "CRM", "source": crm, "schema": crm_schema, "table": "Account", "key": "SAP_Customer_No__c"},
            {"label": "SAP", "source": sap, "schema": sap_schema, "table": "KNA1", "key": "KUNNR"}]


def test_one_lakehouse_with_two_schemas_is_counted_on_one_connection_and_nothing_is_written(monkeypatch):
    ws = mlh.install(monkeypatch, "c")
    try:
        out = json.loads(server.match_records(sides=_fabric_sides(), workspace=mlh.WORKSPACE))
        kunnr = [r[1] for r in mlh.rows("sap")["KNA1"][2]]
        crm = [v for v in mlh.SAP_NO if v]
        c = out["counts"]["pairs"][0]["counts"]
        want_matched = sum(1 for v in set(crm) if crm.count(v) == 1 and kunnr.count(v) == 1)
        assert c["matched"] == want_matched == 2
        assert c["duplicated"] == 1                               # KUNNR 0000000010 in two clients (MANDT): not unique alone
        assert c["only_in_a"] == 1                                # "11": N1 does not strip leading zeros
        assert c["keys_total"] == len(set(crm) | set(kunnr))
        assert out["where"] == {"connection": "one SQL connection to sales_product_lh", "names": "two-part names [schema].[table]"}
        assert len(ws.connections) == 1
        assert all(not WRITE_WORDS.search(q) for q in ws.connections[0].queries if q.lstrip().upper().startswith("WITH"))
        assert mlh.WRITES == []
    finally:
        ws.close()


class _Recorder:
    """A connection that keeps the SQL and answers counts of zero (SQLite has no third name part)."""

    def __init__(self, lakehouse):
        self.lakehouse, self.queries = lakehouse, []

    def __call__(self, sql, *a, **k):
        self.queries.append(sql)
        return [{}] if "COUNT_BIG(" in sql else []

    def close(self):
        pass


def test_two_lakehouses_of_one_workspace_use_three_part_names_over_one_connection(monkeypatch):
    ws = mlh.install(monkeypatch, "b")
    made = []

    def factory(item, token):
        made.append(_Recorder(item["displayName"]))
        return made[-1]
    monkeypatch.setattr(server, "_execute_factory", factory)
    try:
        out = json.loads(server.match_records(sides=_fabric_sides("crm_lh", "sap_lh", "crm_silver", "sap_silver"),
                                              workspace=mlh.WORKSPACE))
        assert out["where"]["names"].startswith("three-part names")
        counting = [m for m in made if any(q.startswith("WITH") for q in m.queries)]
        assert len(counting) == 1 and counting[0].lakehouse == "crm_lh"
        assert all(not m.queries for m in made if m is not counting[0])      # the other: its metadata only (patched reader)
        pair = next(q for q in counting[0].queries if "UNION" in q)
        assert "[crm_lh].[crm_silver].[Account]" in pair and "[sap_lh].[sap_silver].[KNA1]" in pair
        assert mlh.WRITES == []
    finally:
        ws.close()


def test_sides_in_two_workspaces_are_refused_before_anything_is_read(monkeypatch):
    ws = mlh.install(monkeypatch, "b")
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: {"other": "w-other"}.get(workspace, mlh.WORKSPACE_ID))
    opened = []
    monkeypatch.setattr(server, "_execute_factory", lambda item, token: opened.append(item) or _Recorder("x"))
    try:
        sides = _fabric_sides("crm_lh", "sap_lh", "crm_silver", "sap_silver")
        sides[1]["workspace"] = "other"
        out = json.loads(server.match_records(sides=sides, workspace=mlh.WORKSPACE))
        assert out["kind"] == "cross_workspace" and "OneLake shortcut" in out["hint"]
        assert opened == []
    finally:
        ws.close()


def test_sources_on_different_sql_hosts_are_refused(monkeypatch):
    ws = mlh.install(monkeypatch, "b")
    resolve = server._resolve_source
    monkeypatch.setattr(server, "_resolve_source", lambda w, s, h: {**resolve(w, s, h), "sql_host": f"{s}.example"})
    try:
        out = json.loads(server.match_records(sides=_fabric_sides("crm_lh", "sap_lh", "crm_silver", "sap_silver"),
                                              workspace=mlh.WORKSPACE))
        assert out["kind"] == "cross_source" and "shortcut" in out["hint"] and set(out["sources"]) == {"crm_lh", "sap_lh"}
    finally:
        ws.close()


def test_not_found_answers_on_fabric(monkeypatch):
    ws = mlh.install(monkeypatch, "c")
    try:
        out = json.loads(server.match_records(sides=_fabric_sides(), workspace=""))
        assert out["kind"] == "bad_input" and "workspace" in out["error"]
        missing = _fabric_sides()
        missing[0]["table"] = "Nope"
        assert json.loads(server.match_records(sides=missing, workspace=mlh.WORKSPACE))["kind"] == "table_not_found"
        missing = _fabric_sides()
        missing[0]["schema"] = "nope"
        assert json.loads(server.match_records(sides=missing, workspace=mlh.WORKSPACE))["kind"] == "schema_not_found"
        missing = _fabric_sides(crm="no_such_lh")
        got = json.loads(server.match_records(sides=missing, workspace=mlh.WORKSPACE))
        assert got["kind"] == "not_found" and set(got) >= {"error", "hint"}
        assert mlh.WRITES == []
    finally:
        ws.close()


# ------------------------------------------------------------------------------------------------ registration
def _listed(env: dict) -> dict:
    code = ("import asyncio, json; from fabric_backend import server; "
            "print(json.dumps({t.name: t.annotations.read_only_hint for t in asyncio.run(server.mcp.list_tools())}))")
    full = {**os.environ, "KRUSGRAPH_ADVANCED_TOOLS": "1", **env}
    full.pop("KRUSGRAPH_MATCH_RECORDS", None) if "KRUSGRAPH_MATCH_RECORDS" not in env else None
    out = subprocess.run([sys.executable, "-c", code], env=full, capture_output=True, text=True, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_registered_read_only_only_when_the_operator_switches_it_on():
    assert "match_records" not in _listed({})
    on = _listed({"KRUSGRAPH_MATCH_RECORDS": "1"})
    assert on["match_records"] is True


# ------------------------------------------------------------------------------------------------ the seed
def test_seed_writes_the_three_systems_only_when_asked():
    from test_seed import FakeSpark
    from fabric_backend import seed as seedmod
    spark = FakeSpark(["dbo"])
    assert "crm.accounts" not in seedmod.seed(spark, "shop")
    spark = FakeSpark(["dbo"])
    counts = seedmod.seed(spark, "shop", records=True)
    assert {k: counts[k] for k in ("crm.accounts", "erp.KNA1", "mdm.customer")} == {"crm.accounts": 13, "erp.KNA1": 12,
                                                                                    "mdm.customer": 13}
    assert ("save", "erp.KNA1") in spark.log and ("sql", "CREATE SCHEMA IF NOT EXISTS mdm") in spark.log
    flat = json.dumps(seedmod.RECORDS)
    assert re.findall(r"QX[-. ]?\d{4}[-. ]?\d{2}", flat, re.I) and not re.search(r"\b\d{6}-\d{4}\b", flat)
