"""From a validate_plan answer on SAP tables to a status per pack relationship (round n31): the proposals, and
recording the verified ones in a copy of the pack files. Synthetic rows in SQLite; no SAP system."""
from __future__ import annotations

import json
import shutil

import pytest

from fabric_backend import cli, evidence, sap_pack
from fabric_backend.infer import plan
from tests.test_sap_inference import _sqlite


@pytest.fixture
def answer():
    s, execute = _sqlite({
        "VBAK": (["MANDT", "VBELN", "KUNNR", "VKORG"], [("100", "0000000001", "0000000010", "1000"), ("100", "0000000002", "0000000010", "1000")]),
        "VBAP": (["MANDT", "VBELN", "POSNR", "MATNR"], [("100", "0000000001", "000010", "M1"), ("100", "0000000003", "000010", "M1")]),
        "KNA1": (["MANDT", "KUNNR"], [("100", "0000000010")]),
        "MARA": (["MANDT", "MATNR"], [("100", "M1")]),
        "TVKO": (["MANDT", "VKORG"], []),
    })
    return evidence.validate(plan(s), execute)


def test_proposals_follow_the_counts(answer):
    report = sap_pack.verification(answer, "synthetic SQLite rows", "2026-10-28")
    by = {(x["source"], x["target"]): x for x in report["relationships"]}
    assert by[("VBAK", "KNA1")]["proposal"] == "verified" and by[("VBAP", "MARA")]["proposal"] == "verified"
    assert by[("VBAP", "VBAK")]["proposal"] == "review" and "1 of 2 rows point at nothing" in by[("VBAP", "VBAK")]["why"]
    assert by[("VBAK", "TVKO")]["proposal"] == "review"                    # TVKO is empty: every reference is an orphan
    assert report["counts"]["verified"] == 2
    md = sap_pack.verification_markdown(report)
    assert md.startswith("# SAP pack verification: synthetic SQLite rows, 2026-10-28") and "| review | VBAP.MANDT+VBELN → VBAK |" in md


def test_no_rows_is_no_evidence():
    report = sap_pack.verification({"keys": [], "relationships": [
        {"source": "VBAP", "columns": ["MANDT", "VBELN"], "target": "VBAK", "target_columns": ["MANDT", "VBELN"],
         "rule": "SAP pack", "rows_with_value": 0, "orphans": 0}]}, "x", "2026-10-28")
    assert report["relationships"][0]["proposal"] == "no evidence"


def test_a_dropped_client_column_still_finds_the_pack_relationship():
    report = sap_pack.verification({"keys": [], "relationships": [
        {"source": "sap_vbap", "columns": ["vbeln"], "target": "sap_vbak", "target_columns": ["vbeln"],
         "rule": "SAP pack", "rows_with_value": 5, "orphans": 0}]}, "x", "2026-10-28")
    assert [(x["source"], x["proposal"]) for x in report["relationships"]] == [("VBAP", "verified")]


def test_other_rules_are_not_proposed():
    report = sap_pack.verification({"keys": [], "relationships": [
        {"source": "orders", "columns": ["customer_id"], "target": "customers", "target_columns": ["customer_id"],
         "rule": "R1", "rows_with_value": 5, "orphans": 0}]}, "x", "2026-10-28")
    assert report["relationships"] == []


def test_write_verified_records_where_and_when_in_a_copy(answer, tmp_path, monkeypatch):
    shutil.copytree(sap_pack.PACKS, tmp_path / "packs")
    monkeypatch.setattr(sap_pack, "PACKS", tmp_path / "packs")
    sap_pack._load.cache_clear()
    try:
        report = sap_pack.verification(answer, "synthetic SQLite rows", "2026-10-28")
        changed = sap_pack.write_verified(report)
        assert sorted(changed) == ["order_to_cash: VBAK.MANDT+KUNNR -> KNA1", "order_to_cash: VBAP.MANDT+MATNR -> MARA"]
        r = next(r for r in sap_pack.load()["relationships"] if (r["source"], r["target"]) == ("VBAK", "KNA1"))
        assert r["verified"] == [{"where": "synthetic SQLite rows", "when": "2026-10-28", "rows_with_value": 2}]
        assert sap_pack.write_verified(report) == []                       # the same run twice is recorded once
        assert sap_pack.problems(sap_pack.load()) == []
        jsonschema = pytest.importorskip("jsonschema")
        schema = json.loads((tmp_path / "packs" / "pack.schema.json").read_text(encoding="utf-8"))
        doc = json.loads((tmp_path / "packs" / "sap" / "order_to_cash.json").read_text(encoding="utf-8"))
        assert not list(jsonschema.Draft7Validator(schema).iter_errors(doc))
    finally:
        sap_pack._load.cache_clear()


def test_the_command_prints_the_report(answer, tmp_path, capsys):
    path = tmp_path / "validation.json"
    path.write_text(json.dumps(answer), encoding="utf-8")
    assert cli.main(["sap-verify", str(path), "--where", "synthetic SQLite rows", "--when", "2026-10-28"]) == 0
    assert "| verified | VBAK.MANDT+KUNNR → KNA1 |" in capsys.readouterr().out
