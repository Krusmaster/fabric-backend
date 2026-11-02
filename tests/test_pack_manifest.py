"""Round n77: one manifest per knowledge pack (fabric_backend/packs/<pack>/manifest.yaml). The manifest follows
packs/manifest.schema.json, every rule in the pack's module files has a row in it and the other way round, its
fixtures build, its candidate relationships agree with the benchmark facit, and sap_pack_draft names it without
changing its shape for existing clients."""
from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import pytest

from fabric_backend import pack_manifest as pm, sap_pack
from fabric_backend.infer import plan
from tests import sap_support

ROOT = Path(__file__).resolve().parents[1]
PACKS = sap_pack.available()


def _manifest(pack: str) -> dict:
    pytest.importorskip("yaml")
    return pm.load(pack)


def test_every_pack_has_a_manifest_and_the_two_packs_are_there():
    assert pm.available() == PACKS and {"sap", "younium_salesforce"} <= set(PACKS)


@pytest.mark.parametrize("pack", PACKS)
def test_the_manifest_follows_the_schema(pack):
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(pm.SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator.check_schema(schema)
    errors = sorted(jsonschema.Draft7Validator(schema).iter_errors(_manifest(pack)), key=str)
    assert not errors, "\n".join(f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors)


@pytest.mark.parametrize("pack", PACKS)
def test_every_rule_in_the_pack_files_has_a_row_in_the_manifest_and_the_other_way_round(pack):
    m = _manifest(pack)
    assert pm.problems(m, pack) == []
    p = sap_pack.load(pack)
    assert len(m["candidate_relationships"]) == len(p["relationships"])
    assert {e["name"] for e in m["entities"]} == set(p["tables"])
    assert {t["name"] for t in m["traps"]} == {t["id"] for t in p["traps"]}
    assert {s["id"] for s in m["sources"]} == set(p["sources"])
    for s in m["sources"]:                                                # verified is the module file's fetched, never more
        assert s["verified"] == p["sources"][s["id"]]["fetched"]
        assert s["accessed"] is None or s["verified"]


def test_the_check_sees_a_rule_missing_on_either_side_and_a_changed_one():
    m = _manifest("sap")
    gone = dict(m, candidate_relationships=m["candidate_relationships"][1:])
    assert any(x.startswith("candidate_relationships: in the module files but not in the manifest: ") for x in pm.problems(gone, "sap"))
    extra = dict(m, traps=m["traps"] + [{**m["traps"][0], "name": "made_up"}])
    assert "traps: in the manifest but not in the module files: made_up" in pm.problems(extra, "sap")
    changed = dict(m, candidate_relationships=[{**m["candidate_relationships"][0], "cardinality": "one-to-one"}] + m["candidate_relationships"][1:])
    assert any(x.endswith("differs in cardinality") for x in pm.problems(changed, "sap"))
    bad = dict(m, traps=[{**m["traps"][0], "check": "hope"}] + m["traps"][1:])
    assert any("check 'hope' is not one of" in x for x in pm.problems(bad, "sap"))
    assert any("reviewed_by" in x for x in pm.problems(dict(m, reviewed_by="someone"), "sap"))
    assert any("reviewed_at" in x for x in pm.problems(dict(m, review_status="reviewed"), "sap"))


@pytest.mark.parametrize("pack", PACKS)
def test_the_file_is_in_the_canonical_layout_and_regenerating_changes_nothing(pack):
    m = _manifest(pack)
    text = pm.path(pack).read_text(encoding="utf-8")
    assert pm.render(m) == text
    assert pm.render(pm.regenerate(pack, m)) == text
    assert pm.header(pack) == {k: m[k] for k in ("id", "version", "review_status")}


@pytest.mark.parametrize("pack", PACKS)
def test_the_sources_say_what_was_read_and_nothing_is_reviewed_yet(pack):
    m = _manifest(pack)
    assert m["sharing"] == "public-synthetic" and m["review_status"] == "proposed" and m["reviewed_by"] == "" and m["reviewed_at"] == ""
    assert m["version"].startswith("0.")
    unread = [s["id"] for s in m["sources"] if not s["verified"]]
    assert unread, "every source read and checked: the manifest should say so, not this test"
    if pack == "younium_salesforce":
        assert len(unread) == len(m["sources"])                           # n72: none of the nine pages could be opened
    else:
        assert "ms_fabric_mirroring_sap" not in unread and next(s for s in m["sources"] if s["id"] == "ms_fabric_mirroring_sap")["accessed"] == "2026-10-28"


@pytest.mark.parametrize("pack", PACKS)
def test_the_fixtures_build_and_the_pack_recognises_every_fixture_table(pack):
    m = _manifest(pack)
    fx = m["fixtures"]
    mod = importlib.import_module(fx["module"])
    tables = getattr(mod, fx["tables"])()
    expected = getattr(mod, fx["expected"])
    assert len(tables) == expected["tables"]
    entities = {e["name"] for e in m["entities"]}
    assert {sap_pack.table_name(n) for n in tables} <= entities
    schema, execute = getattr(mod, fx["sqlite"])()
    match = sap_pack.match(schema, pack)
    assert match is not None and len(match.tables) == len(tables)
    assert execute(f"SELECT COUNT(*) AS n FROM [{schema.schema}].[{next(iter(schema)).name}]")[0]["n"] >= 1


def _key(source: str, cols, target: str):
    return (sap_pack.table_name(source), tuple(sap_pack._norm(c) for c in cols), sap_pack.table_name(target))


@pytest.mark.parametrize("pack", PACKS)
def test_the_benchmark_facit_and_the_candidate_relationships_agree(pack):
    """Every facit relationship is a candidate of the manifest, and every applied candidate the fixture's tables and
    columns allow is in the facit. What the facit holds beyond that is listed in the manifest as not applied (n72: the
    three links by number the invoice lines carry in the rows)."""
    m = _manifest(pack)
    fx = m["fixtures"]
    facit = json.loads((ROOT / fx["facit"]).read_text(encoding="utf-8"))[fx["facit_set"]]
    truth = {_key(r["source"], r["source_cols"], r["target"]) for r in facit["relationships"]}
    tables = getattr(importlib.import_module(fx["module"]), fx["tables"])()
    cols = {sap_pack.table_name(n): {sap_pack._norm(c) for c in t[0]} for n, t in tables.items()}
    cands = {}
    for r in m["candidate_relationships"]:
        s, sc = pm.parse_ref(r["from"])
        t, tc = pm.parse_ref(r["to"])
        cands[_key(s, sc, t)] = (r, {sap_pack._norm(c) for c in tc})
    assert truth <= set(cands), truth - set(cands)
    applicable = {k for k, (r, tc) in cands.items() if r["applied"] and k[0] in cols and k[2] in cols and set(k[1]) <= cols[k[0]] and tc <= cols[k[2]]}
    assert applicable <= truth, applicable - truth
    assert all(not cands[k][0]["applied"] for k in truth - applicable), truth - applicable
    assert len(truth - applicable) == (3 if pack == "younium_salesforce" else 0)
    # the traps the facit plants are traps the manifest explains with an automated check
    checks = {t["check"] for t in m["traps"]}
    assert ("amount_level" in checks) == bool(facit["traps"]["doubled"]) and ("referential_integrity" in checks) == bool(facit["traps"]["orphans"])


def test_validation_names_what_validate_plan_can_check():
    m = _manifest("sap")
    by = {(r["from"], r["to"]): r for r in m["candidate_relationships"]}
    assert by[("VBAP.MANDT+VBELN", "VBAK.MANDT+VBELN")]["validation"] == ["referential_integrity", "cardinality", "amount_level"]
    assert by[("VBAK.MANDT+KUNNR", "KNA1.MANDT+KUNNR")]["validation"] == ["referential_integrity", "cardinality"]
    assert by[("VBRK.MANDT+BUKRS+BELNR+GJAHR", "BKPF.MANDT+BUKRS+BELNR+GJAHR")]["cardinality"] == "one-to-one"
    assert not by[("VBPA.MANDT+VBELN", "VBAK.MANDT+VBELN")]["applied"]
    assert all(set(r["validation"]) <= set(pm.VALIDATIONS) and r["rule"] == "SAP pack" for r in m["candidate_relationships"])


def test_the_draft_names_the_manifest_without_changing_its_shape():
    before = {"summary", "status", "variant_hint", "tables", "relationships", "not_applied", "missing_tables", "missing_columns",
              "client_dropped", "amounts", "traps", "next"}
    out = sap_pack.draft(plan(sap_support.schema(style="prefix")), "sap")
    assert set(out) == before | {"pack_manifest"}
    assert out["pack_manifest"] == {"id": "sap", "version": _manifest("sap")["version"], "review_status": "proposed"}
    from fabric_backend import seed
    none = sap_pack.draft(plan(seed.schema()))
    assert set(none) == {"summary", "pack_tables", "modules", "pack_manifest"}


def test_the_doc_describes_the_format_the_review_step_and_what_a_pack_is_not():
    md = (ROOT / "docs" / "PACKS.md").read_text(encoding="utf-8")
    for needle in ("manifest.yaml", "manifest.schema.json", "candidate_relationships", "review_status", "reviewed_by", "public-synthetic",
                   "connector", "pack_manifest", "python -m fabric_backend.pack_manifest", "tests/test_pack_manifest.py"):
        assert needle in md, needle
    assert re.search(r"^## .*[Rr]eview", md, re.M) and re.search(r"^- \*\*A connector is transport", md, re.M)
    low = md.lower()
    for word in ("certified", "endorsed", "ai-driven", "ai-powered", "seamless", "effortless", "enterprise-grade", "best-in-class"):
        assert word not in low, word
