"""The synthetic SAP demo (fabric_backend/sap_demo.py): its rows give exactly the findings EXPECTED names, in SQLite,
and its files load the same rows in Fabric. Every value is made up; nothing comes from an SAP system."""
from __future__ import annotations

import csv
import json

import pytest

from fabric_backend import amounts, cli, evidence, privacy, sap_demo, sap_pack
from fabric_backend.infer import plan


@pytest.fixture(scope="module")
def run():
    schema, execute = sap_demo.sqlite()
    p = plan(schema)
    validation = evidence.validate(p, execute, max_items=200)
    return schema, p, validation, sap_pack.verification(validation, "local check of the demo", "2026-10-28")


def _pack(name: str) -> str:
    return sap_pack.table_name(name)


def test_every_table_is_recognised_with_its_key(run):
    schema, p, validation, _ = run
    assert len(p.pack["tables"]) == sap_demo.EXPECTED["tables"] == len(schema)
    assert all(k["verdict"].startswith("unique") for k in validation["keys"])


def test_only_the_planted_orphan_needs_review(run):
    report = run[3]
    review = {(x["source"], x["target"]) for x in report["relationships"] if x["proposal"] == "review"}
    assert review == set(sap_demo.EXPECTED["review"])
    no_evidence = {(x["source"], x["target"]) for x in report["relationships"] if x["proposal"] == "no evidence"}
    assert no_evidence == set(sap_demo.EXPECTED["no_evidence"])
    verified = {(x["source"], x["target"]) for x in report["relationships"] if x["proposal"] == "verified"}
    assert set(sap_demo.EXPECTED["verified_at_least"]) <= verified


def test_the_client_column_keeps_the_two_clients_apart(run):
    rel = {(_pack(r["source"]), _pack(r["target"])): r for r in run[2]["relationships"]}
    assert rel[("VBAP", "VBAK")]["orphans"] == 1                  # only 0000000009: client 200's item finds client 200's order


def test_the_header_amount_is_found_with_its_lines_counted(run):
    header, line, column = sap_demo.EXPECTED["header_amount"]
    f = next(f for f in run[2]["amount_levels"]["findings"] if (_pack(f["header"]), _pack(f["line"])) == (header, line))
    assert column in f["amount_columns"] and f["rows_per_header"]["max_lines"] == 3


def test_addresses_valid_today_in_the_standard_version(run):
    rel = {(_pack(r["source"]), _pack(r["target"])): r for r in run[2]["relationships"]}
    kna1 = rel[("KNA1", "ADRC")]
    assert (kna1["rows_with_value"], kna1["orphans"], kna1["several"]) == (3, 0, 0)   # one row each despite version I and the old period
    assert (rel[("VBPA", "ADRC")]["rows_with_value"], rel[("VBPA", "ADRC")]["orphans"]) == (1, 0)


def test_personal_columns_are_flagged(run):
    flagged = {(_pack(t), c) for t, c in privacy.personal_columns(run[0])}
    assert set(sap_demo.EXPECTED["masked"]) <= flagged


def test_a_run_on_the_demo_cannot_be_recorded_as_verified(run):
    report = sap_pack.verification(run[2], sap_demo.DEMO_WHERE, "2026-10-28")
    with pytest.raises(ValueError, match="synthetic rows"):
        sap_pack.write_verified(report)


def test_the_files_hold_the_same_rows(tmp_path):
    written = sap_demo.write_csv(tmp_path)
    assert (tmp_path / "load_sap_demo.py") in written
    types = json.loads((tmp_path / "_types.json").read_text(encoding="utf-8"))
    assert types["VBAK"]["NETWR"] == "decimal(15,2)" and types["VBAK"]["VBELN"] == "string"
    with (tmp_path / "VBAK.csv").open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0][:2] == ["MANDT", "VBELN"] and rows[1][1] == "0000000001"         # leading zeros kept as text
    nb = (tmp_path / "load_sap_demo.py").read_text(encoding="utf-8")
    assert 'saveAsTable("sap_" + name.lower())' in nb and "inferSchema\", False" in nb
    compile(nb, "load_sap_demo.py", "exec")


def test_no_value_looks_like_a_real_party():
    for name, (cols, _, rows) in sap_demo.tables().items():
        for r in rows:
            for v in r:
                if isinstance(v, str) and "@" in v:
                    assert v.endswith(".example.invalid"), (name, v)


def test_the_command_writes_the_folder(tmp_path, capsys):
    assert cli.main(["sap-demo", "--out", str(tmp_path / "demo")]) == 0
    assert (tmp_path / "demo" / "KNA1.csv").exists() and "Files/sap_demo" in capsys.readouterr().out


def test_the_one_cell_notebook_holds_the_same_rows_and_is_committed():
    from pathlib import Path
    nb = sap_demo.notebook_inline()
    compile(nb, "load_sap_demo_inline.py", "exec")
    data = json.loads(nb.split('json.loads(r"""', 1)[1].split('""")', 1)[0])
    assert {n: [tuple(r) for r in t["rows"]] for n, t in data.items()} == {n: [tuple(r) for r in rows] for n, (_, _, rows) in sap_demo.tables().items()}
    committed = Path(__file__).resolve().parent.parent / "examples" / "sap_demo" / "load_sap_demo_inline.py"
    assert committed.read_text(encoding="utf-8") == nb, "regenerate: fabric-backend sap-demo --notebook examples/sap_demo/load_sap_demo_inline.py"



def test_extended_sql_has_no_subquery_inside_an_aggregate(run):
    """SQL Server (Fabric's SQL endpoint) refuses SUM over a subquery (error 130), which SQLite accepts: the
    correlated count must sit in a derived table, not inside SUM. Found in the live run of LIVE-TEST-SAP.md part 0."""
    import re
    p = run[1]
    assert p.extended
    for r in p.extended:
        sql = evidence.extended_sql("dbo", r)
        assert not re.search(r"SUM\(CASE WHEN \(SELECT", sql), sql
