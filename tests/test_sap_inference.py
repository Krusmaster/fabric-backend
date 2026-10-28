"""The SAP pack in the engine, measured on the synthetic SAP schema of tests/sap_support.py (names only, no rows).

Three ways to plan the same schema, scored against the pack's own keys and applied relationships:
- names: the name rules alone (plan(..., packs=False)), what Krusgraph did before the pack;
- names + keys: the name rules with every table's key given by the caller (keys=), as a consultant who knows SAP
  keys would pass them;
- pack: plan() as it is.
The numbers are asserted exactly, like tests/test_inference_quality.py; `python tests/test_sap_inference.py` prints
the table docs/INFERENCE.md carries. The truth is the pack itself, so the pack row measures that the engine applies
it, not that the pack is right about SAP: that is what validate_plan on real rows is for.
"""
from __future__ import annotations

import pytest

from fabric_backend import amounts
from fabric_backend.infer import plan
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests import sap_support  # noqa: E402

CASES = [("ecc", "upper"), ("ecc", "prefix"), ("s4hana", "lower")]


def score(variant: str, style: str, how: str) -> dict:
    s = sap_support.schema(style=style, variant=variant)
    keys, truth = sap_support.truth(variant)
    name = {t.name: t.name.upper().removeprefix("SAP_") for t in s}
    given = {t.name: [c for c in t.column_names if c.upper() in {k.upper() for k in keys[name[t.name]]}] for t in s} if how == "names+keys" else None
    if given:                                                               # in the key's own order
        given = {t: sorted(cols, key=lambda c: [k.upper() for k in keys[name[t]]].index(c.upper())) for t, cols in given.items()}
    p = plan(s, keys=given, packs=how == "pack")
    inferred = {(name[r.source], tuple(c.lower() for c in r.source_cols), name[r.target]) for r in p.relationships}
    key_hits = sum(1 for t, (cols, _) in p.keys.items() if tuple(c.lower() for c in cols) == keys[name[t]])
    hits = len(inferred & truth)
    return {"tables": len(s), "keys": len(keys), "key_hits": key_hits, "relationships": len(truth), "rel_hits": hits,
            "rel_wrong": len(inferred - truth), "precision": round(hits / len(inferred), 2) if inferred else None,
            "coverage": round(hits / len(truth), 2)}




@pytest.mark.parametrize("variant,style", CASES)
def test_the_pack_finds_every_key_and_relationship_and_nothing_else(variant, style):
    r = score(variant, style, "pack")
    assert (r["key_hits"], r["rel_hits"], r["rel_wrong"]) == (r["keys"], r["relationships"], 0)


@pytest.mark.parametrize("variant,style", CASES)
def test_without_the_pack_the_name_rules_find_nothing_right(variant, style):
    r = score(variant, style, "names")
    assert r["rel_hits"] == 0 and r["key_hits"] == 0


def test_numbers():
    assert {f"{v}/{s}/{h}": score(v, s, h) for v, s in CASES for h in ("names", "names+keys", "pack")} == NUMBERS


NUMBERS = {'ecc/prefix/names': {'coverage': 0.0, 'key_hits': 0, 'keys': 33, 'precision': None, 'rel_hits': 0, 'rel_wrong': 0, 'relationships': 48, 'tables': 33},
    'ecc/prefix/names+keys': {'coverage': 0.88, 'key_hits': 33, 'keys': 33, 'precision': 0.45, 'rel_hits': 42, 'rel_wrong': 51, 'relationships': 48, 'tables': 33},
    'ecc/prefix/pack': {'coverage': 1.0, 'key_hits': 33, 'keys': 33, 'precision': 1.0, 'rel_hits': 48, 'rel_wrong': 0, 'relationships': 48, 'tables': 33},
    'ecc/upper/names': {'coverage': 0.0, 'key_hits': 0, 'keys': 33, 'precision': None, 'rel_hits': 0, 'rel_wrong': 0, 'relationships': 48, 'tables': 33},
    'ecc/upper/names+keys': {'coverage': 0.88, 'key_hits': 33, 'keys': 33, 'precision': 0.45, 'rel_hits': 42, 'rel_wrong': 51, 'relationships': 48, 'tables': 33},
    'ecc/upper/pack': {'coverage': 1.0, 'key_hits': 33, 'keys': 33, 'precision': 1.0, 'rel_hits': 48, 'rel_wrong': 0, 'relationships': 48, 'tables': 33},
    's4hana/lower/names': {'coverage': 0.0, 'key_hits': 0, 'keys': 31, 'precision': None, 'rel_hits': 0, 'rel_wrong': 0, 'relationships': 48, 'tables': 31},
    's4hana/lower/names+keys': {'coverage': 0.85, 'key_hits': 31, 'keys': 31, 'precision': 0.53, 'rel_hits': 41, 'rel_wrong': 36, 'relationships': 48, 'tables': 31},
    's4hana/lower/pack': {'coverage': 1.0, 'key_hits': 31, 'keys': 31, 'precision': 1.0, 'rel_hits': 48, 'rel_wrong': 0, 'relationships': 48, 'tables': 31}}


def test_pack_relationships_carry_rule_and_source():
    p = plan(sap_support.schema())
    assert p.pack and p.pack["pack"] == "sap" and "SAP pack" in p.summary()
    r = next(r for r in p.relationships if (r.source, r.target) == ("VBAP", "VBAK"))
    assert r.rule == "SAP pack" and "SAP Help Portal" in r.note and r.source_cols == ["MANDT", "VBELN"]
    assert any(n["source"] == "VBFA" for n in p.pack["not_applied"])


def test_caller_keys_and_confirmed_still_win():
    s = sap_support.schema(["VBAK", "VBAP", "KNA1"])
    p = plan(s, keys={"VBAK": ["VBELN"]}, confirmed=[{"source": "VBAP", "source_cols": ["VBELN"], "target": "VBAK", "target_cols": ["VBELN"]}])
    assert p.keys["VBAK"] == (["VBELN"], "K1")
    rels = {(r.source, tuple(r.source_cols), r.rule) for r in p.relationships if r.target == "VBAK"}
    assert ("VBAP", ("VBELN",), "confirmed") in rels and not any(rule == "SAP pack" for *_, rule in rels)


def test_the_header_amount_of_an_sap_order_is_found():
    found = amounts.header_amounts(plan(sap_support.schema(["VBAK", "VBAP", "VBEP"])))
    pairs = {(f["header"], f["line"], tuple(f["amount_columns"])) for f in found}
    assert ("VBAK", "VBAP", ("NETWR",)) in pairs                       # the order's net value repeated per item
    assert ("VBAP", "VBEP", ("NETWR",)) in pairs                       # the item's net value repeated per schedule line


if __name__ == "__main__":
    print("| Schema | Planned by | Keys right | Relationships right | Wrong | Precision | Coverage |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for v, s in CASES:
        for h in ("names", "names+keys", "pack"):
            r = score(v, s, h)
            prec = "–" if r["precision"] is None else f"{r['precision']:.2f}"
            print(f"| {v}, {s} names, {r['tables']} tables | {h} | {r['key_hits']} of {r['keys']} | {r['rel_hits']} of {r['relationships']} "
                  f"| {r['rel_wrong']} | {prec} | {r['coverage']:.2f} |")


def test_the_data_dictionary_names_the_pack_its_traps_and_sources():
    from fabric_backend.dictionary import data_dictionary
    md = data_dictionary(plan(sap_support.schema()), "sap_lh", "sap")
    assert "## Known from the sap pack" in md and "MANDT in every join" in md and "| SAP pack |" in md
    assert "help.sap.com" in md


def _sqlite(rows: dict):
    """A tiny synthetic SAP schema in SQLite: no values from any real system."""
    import sqlite3

    from fabric_backend.dialects import sqlite_sql
    from fabric_backend.schema import Schema
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS sap")
    info = []
    for t, (cols, data) in rows.items():
        con.execute(f"CREATE TABLE sap.[{t}] ({', '.join(cols)})")
        con.executemany(f"INSERT INTO sap.[{t}] VALUES ({','.join('?' * len(cols))})", data)
        info += [("sap", t, c, "nvarchar", i) for i, c in enumerate(cols, 1)]

    def execute(sql: str):
        cur = con.execute(sqlite_sql(sql))
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]
    return Schema.from_information_schema(info, schema="sap"), execute


def test_validate_plan_checks_pack_relationships_against_rows():
    from fabric_backend import evidence
    s, execute = _sqlite({
        "VBAK": (["MANDT", "VBELN", "KUNNR"], [("100", "0000000001", "0000000010"), ("200", "0000000001", "0000000010")]),
        "VBAP": (["MANDT", "VBELN", "POSNR"], [("100", "0000000001", "000010"), ("100", "0000000002", "000010")]),
        "KNA1": (["MANDT", "KUNNR"], [("100", "0000000010")]),
    })
    out = evidence.validate(plan(s), execute)
    rel = {(r["source"], r["target"]): r for r in out["relationships"]}
    assert rel[("VBAP", "VBAK")]["rule"] == "SAP pack" and rel[("VBAP", "VBAK")]["orphans"] == 1   # 0000000002 has no header
    assert rel[("VBAK", "KNA1")]["orphans"] == 1                  # client 200's customer is not in client 100: MANDT matters
    assert all(k["verdict"].startswith("unique") for k in out["keys"])


def test_procure_to_pay_amounts_and_the_two_belnr():
    p = plan(sap_support.schema(["EKKO", "EKPO", "EKBE", "RBKP", "RSEG", "BKPF", "LFA1", "T001"]))
    pairs = {(f["header"], f["line"], tuple(f["amount_columns"])) for f in amounts.header_amounts(p)}
    assert ("EKPO", "EKBE", ("NETWR",)) in pairs                       # the order item once per history row
    assert ("RBKP", "RSEG", ("RMWWR", "WMWST1")) in pairs              # the invoice's gross amount once per item
    assert not [r for r in p.relationships if {r.source, r.target} == {"RBKP", "BKPF"}]   # two different BELNR
    assert not [r for r in p.relationships if (r.source, r.target) == ("EKBE", "RBKP")]  # conditional: listed only
    assert any((n["source"], n["target"]) == ("EKBE", "RBKP") for n in p.pack["not_applied"])
    names = plan(sap_support.schema(["RBKP", "BKPF"]), keys={"RBKP": ["MANDT", "BELNR", "GJAHR"], "BKPF": ["MANDT", "BUKRS", "BELNR", "GJAHR"]}, packs=False)
    assert any((r.source, r.target, r.rule) == ("RBKP", "BKPF", "R3") for r in names.relationships)   # what the name rules alone do
