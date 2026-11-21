"""SAPD1 (21 Nov 2026): the SAP full demo, sap_demo.tables(full=True). The 17 order-to-cash tables plus 28 tables of the
pack's procure-to-pay, finance, accounting document, business partner and pricing modules; every value is made up.

Checks: only names the pack contains, the small demo unchanged, the planted traps found as EXPECTED_FULL says, and the
engine's five data products (domains.draft) as /sources shows them."""
from __future__ import annotations

import json
import re

import pytest

from fabric_backend import cli, domains, evidence, privacy, sap_demo, sap_pack, sources_page
from fabric_backend.infer import plan

PACK = sap_pack.load("sap")


@pytest.fixture(scope="module")
def run():
    schema, execute = sap_demo.sqlite(full=True)
    p = plan(schema)
    validation = evidence.validate(p, execute, max_items=200)
    return schema, p, validation, sap_pack.verification(validation, "local check of the full demo", "2026-11-21")


def _pack(name: str) -> str:
    return sap_pack.table_name(name)


def _pack_text() -> str:
    """Every word the SAP pack's module files hold (keys, relationships, amounts, notes and traps)."""
    from pathlib import Path
    folder = Path(sap_pack.__file__).resolve().parent / "packs" / "sap"
    return " ".join(f.read_text(encoding="utf-8") for f in sorted(folder.glob("*.json")))


def test_the_small_demo_is_unchanged_and_the_full_one_adds_to_it():
    small, full = sap_demo.tables(), sap_demo.tables(full=True)
    assert len(small) == sap_demo.EXPECTED["tables"] == 17
    assert len(full) == sap_demo.EXPECTED_FULL["tables"] == 17 + len(sap_demo.FULL_TABLES)
    assert {n: full[n] for n in small} == small and list(full)[17:] == list(sap_demo.FULL_TABLES)


def test_only_table_and_column_names_the_pack_contains():
    words = set(re.findall(r"\b[A-Z][A-Z0-9_]+\b", _pack_text()))
    for name in sap_demo.FULL_TABLES:
        assert name in PACK["tables"], name
        cols, kinds, rows = sap_demo.tables(full=True)[name]
        assert set(cols) <= words, (name, set(cols) - words)
        assert all(len(r) == len(cols) for r in rows) and len(kinds) == len(cols)


def test_every_table_is_recognised_with_a_unique_key(run):
    schema, p, validation, _ = run
    assert len(p.pack["tables"]) == len(schema) == 45
    assert all(k["verdict"].startswith("unique") for k in validation["keys"])
    assert p.pack["variant_hint"].startswith("s4hana")            # ACDOCA and PRCD_ELEMENTS, no ECC twin next to them


def test_only_the_planted_problems_need_review(run):
    report = run[3]
    by = lambda what: {(x["source"], x["target"]) for x in report["relationships"] if x["proposal"] == what}
    assert by("review") == set(sap_demo.EXPECTED_FULL["review"])
    assert by("no evidence") == set(sap_demo.EXPECTED_FULL["no_evidence"])
    assert set(sap_demo.EXPECTED_FULL["verified_at_least"]) <= by("verified")


def test_header_amounts_repeated_per_line_are_found(run):
    found = {(_pack(f["header"]), _pack(f["line"])): f for f in run[2]["amount_levels"]["findings"]}
    for header, line, column in sap_demo.EXPECTED_FULL["header_amounts"]:
        assert column in found[(header, line)]["amount_columns"], (header, line)
    assert found[("RBKP", "RSEG")]["rows_per_header"]["max_lines"] == 2
    assert found[("EKPO", "EKBE")]["rows_per_header"]["max_lines"] == 2         # goods receipt and invoice per item


def test_validity_periods_pick_one_row(run):
    rel = {(_pack(r["source"]), _pack(r["target"])): r for r in run[2]["relationships"]}
    csks = rel[("ACDOCA", "CSKS")]
    assert (csks["rows_with_value"], csks["orphans"], csks["several"]) == (2, 0, 0)   # two periods, one valid on BUDAT


def test_the_other_traps_are_in_the_rows():
    t = {n: [dict(zip(c, r)) for r in rows] for n, (c, _k, rows) in sap_demo.tables(full=True).items()}
    assert {r["RLDNR"] for r in t["ACDOCA"]} == {"0L", "2L"} and sum(r["WSL"] for r in t["ACDOCA"] if r["RLDNR"] == "0L") == 0
    assert any(r["LOEKZ"] for r in t["EKPO"])
    assert {r["GJAHR"] for r in t["RBKP"] if r["BELNR"] == "5105600001"} == {"2025", "2026"}
    assert any(r["BELNR"] == "5105600001" for r in t["BKPF"])                  # the same BELNR, another document
    assert len({r["KTOPL"] for r in t["SKA1"] if r["SAKNR"] == "0000800000"}) == 2
    assert not {r["PARTNER"] for r in t["BUT000"]} & {r["KUNNR"] for r in t["KNA1"]}
    order = [r for r in t["PRCD_ELEMENTS"] if r["KNUMV"] == "0000000501"]
    assert sum(r["KWERT"] for r in order) == 837 and sum(r["KWERT"] for r in order if r["KSCHL"] == "PR00") == 600
    assert {r["MANDT"] for r in t["EKKO"]} == {"100", "200"} and {r["MANDT"] for r in t["LFM1"]} == {"100"}


def test_personal_columns_are_flagged(run):
    flagged = {(_pack(t), c) for t, c in privacy.personal_columns(run[0])}
    assert set(sap_demo.EXPECTED_FULL["masked"]) <= flagged


def test_the_engine_proposes_five_data_products(run):
    schema, p, validation, _ = run
    out = domains.draft(p, "sap", "sap demo", validation=validation)
    names = {d["name"]: {_pack(t) for t in d["tables"]} for d in out["domains"]}
    assert tuple(names) == sap_demo.EXPECTED_FULL["products"] and not out["unassigned"]
    assert {"EKKO", "EKPO", "RBKP", "RSEG", "LFA1"} <= names["procure-to-pay"]
    assert {"VBAK", "VBAP", "LIKP", "LIPS", "VBRK", "VBRP"} <= names["order-to-cash"]
    assert {"ACDOCA", "BKPF", "SKA1", "SKB1", "CSKS", "CEPC"} <= names["finance"]
    assert {"ADRC", "BUT000", "CVI_CUST_LINK"} <= names["customer master"]
    assert names["pricing"] == {"KONH", "KONP", "PRCD_ELEMENTS", "T685"}
    reasons = {d["name"]: d["name_reason"] for d in out["domains"]}
    assert reasons["procure-to-pay"].startswith("SAP procure-to-pay (purchasing and supplier invoices together)")
    assert reasons["finance"].startswith("SAP finance (accounting and general ledger together)")
    for c in out["contracts"].values():
        __import__("yaml").safe_load(c)


def test_sources_page_shows_the_full_demo():
    s = next(x for x in sources_page.summary() if x["key"] == "sap")
    assert s["demo_tables"] == 45 and [p["name"] for p in s["products"]] == list(sap_demo.EXPECTED_FULL["products"])
    assert all(p["question"] for p in s["products"])


def test_a_run_on_the_full_demo_cannot_be_recorded_as_verified(run):
    report = sap_pack.verification(run[2], sap_demo.DEMO_WHERE, "2026-11-21")
    with pytest.raises(ValueError, match="synthetic rows"):
        sap_pack.write_verified(report)


def test_the_command_and_the_notebook_hold_the_full_rows(tmp_path, capsys):
    assert cli.main(["sap-demo", "--full", "--out", str(tmp_path / "demo")]) == 0
    assert (tmp_path / "demo" / "ACDOCA.csv").exists() and (tmp_path / "demo" / "KNA1.csv").exists()
    capsys.readouterr()
    nb = sap_demo.notebook_inline(full=True)
    compile(nb, "load_sap_full_demo_inline.py", "exec")
    data = json.loads(nb.split('json.loads(r"""', 1)[1].split('""")', 1)[0])
    assert len(data) == 45 and data["EKKO"]["rows"][0][1] == "4500000000"


def test_no_value_looks_like_a_real_party():
    for name in sap_demo.FULL_TABLES:
        for r in sap_demo.tables(full=True)[name][2]:
            for v in r:
                if isinstance(v, str):
                    assert "@" not in v or v.endswith(".example.invalid"), (name, v)
                    assert not re.search(r"[a-z]", v) or v.startswith(("Demo ", "Other ", "Supply ")), (name, v)
