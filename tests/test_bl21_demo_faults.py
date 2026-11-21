"""2026-11-21, round BL21 (sprint item BL21, backlog C-37, C-38): `krusgraph demo faults`, the planted-faults walk as one
command (fabric_backend/krusgraph_cli.py, docs/demo/PLANTED-FAULTS-WALK.md).

The command's JSON lists the same found faults as shop_faults.FAULTS and docs/PLANTED-FAULTS.md, flags nothing else, and
every receipt SQL it prints re-runs on SQLite to its counts. Its text is the tool's own answer, not expected text (C-38).
"""
from __future__ import annotations

import json
import re
import socket
import sqlite3
from pathlib import Path

import pytest

from fabric_backend import krusgraph_cli as cli
from fabric_backend import shop_faults

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("krusgraph demo faults must not reach the network")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def run_json(capsys, *argv):
    code = cli.main(list(argv) + ["--json"])
    out, _err = capsys.readouterr()
    return code, json.loads(out)


@pytest.fixture(scope="module")
def answer():
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(["demo", "faults", "--json"])
    assert code == cli.OK
    return json.loads(buf.getvalue())


def test_envelope_and_counts(answer):
    assert answer["ok"] is True and answer["read_only"] is True and answer["command"] == "demo"
    r = answer["result"]
    assert r["sample"] == "shop_faults" and r["planted"] == len(shop_faults.FAULTS) == 5
    assert [f["id"] for f in r["faults"]] == [f["id"] for f in shop_faults.FAULTS]
    assert r["found"] + r["not_found_yet"] == 5


def test_found_faults_match_shop_faults_and_the_doc(answer):
    r = answer["result"]
    found = {f["id"] for f in r["faults"] if f["found"]}
    assert found == {f["id"] for f in shop_faults.FAULTS if f["detected"]}
    doc = (ROOT / "docs" / "PLANTED-FAULTS.md").read_text(encoding="utf-8")
    line = re.search(r"^F1 .*$", doc, re.M).group(0)                    # "F1 found  F2 found ... F5 not detected"
    in_doc = set(re.findall(r"(F\d) found", line))
    assert found == in_doc, (found, line)
    for f in r["faults"]:
        assert f["status"] == ("found" if f["found"] else "not found yet")
        if not f["found"]:
            assert f["krusgraph_said"] is None and f["receipt"] == []


def test_text_is_the_tools_own_answer(answer):
    """C-38: what the walk says Krusgraph found is shop_faults.check's flagged answer, word for word."""
    flagged = shop_faults.check()["flagged"]
    for f in answer["result"]["faults"]:
        assert f["krusgraph_said"] == flagged.get(f["item"])
    for f, planted in zip(answer["result"]["faults"], shop_faults.FAULTS):
        if planted["detected"]:
            assert planted["finding"] in f["krusgraph_said"]


def test_no_false_finding(answer):
    r = answer["result"]
    assert r["unexpected"] == []
    assert {x["item"] for x in r["also_flagged"]} == set(shop_faults.CLEAN_FINDINGS)


def test_every_found_fault_has_a_receipt(answer):
    for f in answer["result"]["faults"]:
        if f["found"]:
            assert f["receipt"] and all(x["sql"] and x["counts"] for x in f["receipt"]), f["id"]


def _shop_faults_sqlite():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute(f"ATTACH DATABASE ':memory:' AS [{shop_faults.SCHEMA}]")
    for t, (cols, rows) in shop_faults.tables().items():
        con.execute(f"CREATE TABLE [{shop_faults.SCHEMA}].[{t}] ({', '.join(f'[{c}]' for c, _ in cols)})")
        con.executemany(f"INSERT INTO [{shop_faults.SCHEMA}].[{t}] VALUES ({','.join('?' * len(cols))})", rows)
    return con


def _same(stated, got):
    if isinstance(stated, float) or isinstance(got, float):
        return got is not None and abs(float(stated) - float(got)) < 0.01
    return stated == got


def test_every_receipt_sql_reruns_on_sqlite_to_its_count(answer):
    con = _shop_faults_sqlite()
    proofs = [x for f in answer["result"]["faults"] for x in f["receipt"]] + \
             [x for a in answer["result"]["also_flagged"] for x in a["receipt"]]
    assert len(proofs) >= 4
    for x in proofs:
        assert x["sql"].lstrip().upper().startswith("SELECT")
        row = dict(con.execute(x["sql"]).fetchone())
        for k, stated in x["counts"].items():
            assert _same(stated, row.get(k)), (k, stated, row.get(k), x["sql"])
    con.close()


def test_human_text_walks_each_fault(capsys):
    code = cli.main(["demo", "faults", "--human"])
    out = capsys.readouterr().out
    assert code == 0
    for f in shop_faults.FAULTS:
        assert f"{f['id']}  {f['table']}:" in out
    assert "NOT FOUND YET" in out and "SELECT" in out and "UNEXPECTED" not in out


def test_apply_is_refused_and_unknown_demo_is_a_usage_error(capsys):
    code, d = run_json(capsys, "demo", "faults", "--apply")
    assert code == cli.REFUSED and d["error"]["kind"] == "refused_write"
    with pytest.raises(SystemExit) as e:
        cli.main(["demo", "nosuch"])
    assert e.value.code == cli.USAGE
    capsys.readouterr()


def test_help_and_check_list_the_demo(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["demo", "--help"])
    out = capsys.readouterr().out
    assert e.value.code == 0 and "examples:" in out and "krusgraph demo faults" in out
    code, d = run_json(capsys, "check")
    assert code == 0 and "demo faults" in d["result"]["demos"]


def test_walk_doc_exists_and_is_dated():
    doc = (ROOT / "docs" / "demo" / "PLANTED-FAULTS-WALK.md").read_text(encoding="utf-8")
    assert doc.startswith("> 2026-11-21, round BL21") and "krusgraph demo faults" in doc
    assert "`demo faults`" in (ROOT / "docs" / "CLI.md").read_text(encoding="utf-8")
