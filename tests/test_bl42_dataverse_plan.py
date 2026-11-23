"""BL42 (backlog I-43, BL25 follow-up), 23 November 2026: Dataverse `$metadata` fed to the plan as declared candidates.

dataverse_meta.plan puts the keys and plain lookups a `$metadata` file declares into infer.plan the way csn.plan does,
with the rule "Dataverse metadata"; validate_plan then counts them like any other. On the synthetic Dynamics 365 demo lake
with BL25's synthetic `$metadata` (tests/fixtures/dataverse_metadata_demo.xml) the declared links are in the plan and
counted; multi-table lookups stay out (listed); unmapped names are reported. The CLI's `plan --dataverse-metadata FILE`
takes a local file and refuses a URL. Nothing here reaches the network."""
import json
import socket
from pathlib import Path

import pytest

from fabric_backend import dataverse_meta as dm
from fabric_backend import dynamics_demo as dd
from fabric_backend import evidence
from fabric_backend import krusgraph_cli as cli
from fabric_backend.infer import plan as infer_plan

FIXTURE = Path(__file__).parent / "fixtures" / "dataverse_metadata_demo.xml"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("no network")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture(scope="module")
def planned():
    schema, execute = dd.sqlite()
    p, report = dm.plan(schema, dm.read(FIXTURE))
    return schema, execute, p, report


def test_declared_lookups_are_in_the_plan_with_their_rule(planned):
    _schema, _x, p, report = planned
    ours = {(r.source, tuple(r.source_cols), r.target) for r in p.relationships if r.rule == dm.RULE}
    declared = {(r["source"], tuple(r["source_cols"]), r["target"]) for r in report["links"]}
    assert declared and ours == declared
    assert ("salesorderdetail", ("salesorderid",), "salesorder") in ours
    assert p.dataverse is report and "Dataverse metadata" in p.summary()
    assert p.keys["account"] == (["accountid"], dm.RULE)


def test_validate_counts_the_declared_links(planned):
    _schema, execute, p, _report = planned
    v = evidence.validate(p, execute, 200)
    counted = [r for r in v["relationships"] if r.get("rule") == dm.RULE]
    assert counted and all("orphans" in r and "verdict" in r for r in counted)          # counted, not taken on trust
    before = {(r["source"], r["target"]) for r in counted}
    assert ("salesorderdetail", "salesorder") in before


def test_multi_table_lookups_and_unmapped_names_are_reported_not_applied(planned):
    _schema, _x, p, report = planned
    assert report["filtered"] and all(f.get("filter") for f in report["filtered"])
    plain = {(r.source, tuple(r.source_cols)) for r in p.relationships}
    for f in report["filtered"]:
        assert (f["source"], tuple(f["source_cols"])) not in {(s, c) for s, c in plain if any(
            r.rule == dm.RULE and r.source == s and tuple(r.source_cols) == c for r in p.relationships)}
    assert "unmapped_columns" in report and "unmatched" in report


def test_a_key_the_caller_gives_wins(planned):
    schema, _x, _p, _r = planned
    p, report = dm.plan(schema, dm.read(FIXTURE), keys={"salesorder": ["name"]})
    assert p.keys["salesorder"][0] == ["name"]
    assert any("salesorder" in d.get("lookup", "") and "caller wins" in d["why"] for d in report["not_applied"])


def test_without_metadata_the_plan_is_as_before(planned):
    schema, *_ = planned
    p = infer_plan(schema)
    assert p.dataverse is None and not any(r.rule == dm.RULE for r in p.relationships)


def test_cli_takes_a_local_file_and_refuses_a_url(capsys):
    code = cli.main(["plan", "--sample", "shop", "--dataverse-metadata", str(FIXTURE), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code in (cli.OK, 6) and out["result"]["dataverse"]["files"]
    assert out["result"]["dataverse"]["unmatched"]                                         # the shop has no Dataverse tables
    code = cli.main(["plan", "--sample", "shop", "--dataverse-metadata", "https://org.api.crm.dynamics.com/api/data/v9.2/$metadata", "--json"])
    assert code != cli.OK
    assert "never a URL" in capsys.readouterr().out + capsys.readouterr().err
