"""The SAP pack in the engine, on the synthetic SAP schema of tests/sap_support.py (names only, no rows).

Three ways to plan the same schema:
- names: the name rules alone (plan(..., packs=False)), what Krusgraph did before the pack;
- names + keys: the name rules with every table's key given by the caller (keys=), as a consultant who knows SAP
  keys would pass them;
- pack: plan() as it is.

Read the pack row as a self-check, not as precision: the schema is generated from the pack and scored against the
pack, so 100 % only shows that the engine applies the pack as written. Whether the pack is right about SAP is not
measured here; validate_plan on real rows is the only test of that.

A relationship found by the name rules but not in the pack is sorted, so a link the pack lacks is not counted as an
error of the name rules (round n24, after the first measurement counted all of them as wrong):
- implied: the pack reaches the same target through a longer path that starts with the same columns
  (EKET.MANDT+EBELN -> EKKO, where the pack has EKET -> EKPO -> EKKO);
- listed: partly right. The pack lists that link but does not apply it (conditional, many-to-many, or on a unique
  column that is not the key: VBPA.VBELN -> VBAK holds for the partner rows of sales documents only), or the link is a
  shortcut over a path that uses such a listed link;
- wrong: neither. These are the real errors: a column that names another document (LIPS.VBELN, a delivery, read as
  an order; RBKP.BELNR, an invoice number, read as an accounting document).
The numbers are asserted exactly; `python tests/test_sap_inference.py` prints the table docs/INFERENCE.md carries.
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


def _implied(rel: tuple, truth: set, last: set = frozenset()) -> bool:
    """The pack reaches rel's target from rel's source through two or more of its relationships, the first one
    carrying rel's columns (so the shortcut is the same join, only skipping a table). With `last`, the final hop may
    be one listed (conditional) link: never two in a row, since two conditions need not hold for the same rows
    (VBAP -> VBAK -> VBUK -> LIKP would read an order as a delivery)."""
    src, cols, tgt = rel
    out: dict[str, set] = {}
    for s, _, t in truth:
        out.setdefault(s, set()).add(t)
    ends: dict[str, set] = {}
    for s, _, t in last:
        ends.setdefault(s, set()).add(t)
    for s, c, mid in truth | last:
        if s != src or mid == tgt or not set(cols) <= set(c):
            continue
        if (s, c, mid) in last:                                         # the first hop is the listed one: it must also be the last
            continue
        seen, todo = {mid}, [mid]
        while todo:
            n0 = todo.pop()
            if tgt in out.get(n0, ()) or tgt in ends.get(n0, ()):
                return True
            for n in out.get(n0, ()):
                if n not in seen:
                    seen.add(n)
                    todo.append(n)
    return False


def score(variant: str, style: str, how: str) -> dict:
    s = sap_support.schema(style=style, variant=variant)
    keys, truth = sap_support.truth(variant)
    listed = sap_support.listed(variant)
    name = {t.name: t.name.upper().removeprefix("SAP_") for t in s}
    given = {t.name: [c for c in t.column_names if c.upper() in {k.upper() for k in keys[name[t.name]]}] for t in s} if how == "names+keys" else None
    if given:                                                               # in the key's own order
        given = {t: sorted(cols, key=lambda c: [k.upper() for k in keys[name[t]]].index(c.upper())) for t, cols in given.items()}
    p = plan(s, keys=given, packs=how == "pack")
    inferred = {(name[r.source], tuple(c.lower() for c in r.source_cols), name[r.target]) for r in p.relationships}
    key_hits = sum(1 for t, (cols, _) in p.keys.items() if tuple(c.lower() for c in cols) == keys[name[t]])
    hits = len(inferred & truth)
    other = inferred - truth
    implied = {r for r in other if _implied(r, truth)}
    # partly right: a link the pack lists (conditional), or a shortcut over a path that uses one
    partly = {r for r in other - implied if any(r[0] == l[0] and r[2] == l[2] and set(r[1]) <= set(l[1]) for l in listed)
              or _implied(r, truth, listed)}
    wrong = other - implied - partly
    return {"tables": len(s), "keys": len(keys), "key_hits": key_hits, "relationships": len(truth), "rel_hits": hits,
            "implied": len(implied), "listed": len(partly), "wrong": len(wrong),
            "wrong_share": round(len(wrong) / len(inferred), 2) if inferred else None,
            "coverage": round(hits / len(truth), 2)}




@pytest.mark.parametrize("variant,style", CASES)
def test_the_pack_finds_every_key_and_relationship_and_nothing_else(variant, style):
    r = score(variant, style, "pack")
    assert (r["key_hits"], r["rel_hits"], r["implied"], r["listed"], r["wrong"]) == (r["keys"], r["relationships"], 0, 0, 0)


@pytest.mark.parametrize("variant,style", CASES)
def test_without_the_pack_the_name_rules_find_nothing_right(variant, style):
    r = score(variant, style, "names")
    assert r["rel_hits"] == 0 and r["key_hits"] == 0


def test_numbers():
    assert {f"{v}/{s}/{h}": score(v, s, h) for v, s in CASES for h in ("names", "names+keys", "pack")} == NUMBERS


NUMBERS = {'ecc/prefix/names': {'coverage': 0.0, 'implied': 0, 'key_hits': 0, 'keys': 53, 'listed': 0, 'rel_hits': 0, 'relationships': 89, 'tables': 53, 'wrong': 0, 'wrong_share': None},
    'ecc/prefix/names+keys': {'coverage': 0.88, 'implied': 9, 'key_hits': 53, 'keys': 53, 'listed': 20, 'rel_hits': 78, 'relationships': 89, 'tables': 53, 'wrong': 27, 'wrong_share': 0.2},
    'ecc/prefix/pack': {'coverage': 1.0, 'implied': 0, 'key_hits': 53, 'keys': 53, 'listed': 0, 'rel_hits': 89, 'relationships': 89, 'tables': 53, 'wrong': 0, 'wrong_share': 0.0},
    'ecc/upper/names': {'coverage': 0.0, 'implied': 0, 'key_hits': 0, 'keys': 53, 'listed': 0, 'rel_hits': 0, 'relationships': 89, 'tables': 53, 'wrong': 0, 'wrong_share': None},
    'ecc/upper/names+keys': {'coverage': 0.88, 'implied': 9, 'key_hits': 53, 'keys': 53, 'listed': 20, 'rel_hits': 78, 'relationships': 89, 'tables': 53, 'wrong': 27, 'wrong_share': 0.2},
    'ecc/upper/pack': {'coverage': 1.0, 'implied': 0, 'key_hits': 53, 'keys': 53, 'listed': 0, 'rel_hits': 89, 'relationships': 89, 'tables': 53, 'wrong': 0, 'wrong_share': 0.0},
    's4hana/lower/names': {'coverage': 0.0, 'implied': 0, 'key_hits': 0, 'keys': 47, 'listed': 0, 'rel_hits': 0, 'relationships': 75, 'tables': 47, 'wrong': 0, 'wrong_share': None},
    's4hana/lower/names+keys': {'coverage': 0.79, 'implied': 4, 'key_hits': 47, 'keys': 47, 'listed': 12, 'rel_hits': 59, 'relationships': 75, 'tables': 47, 'wrong': 14, 'wrong_share': 0.16},
    's4hana/lower/pack': {'coverage': 1.0, 'implied': 0, 'key_hits': 47, 'keys': 47, 'listed': 0, 'rel_hits': 75, 'relationships': 75, 'tables': 47, 'wrong': 0, 'wrong_share': 0.0}}


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
    print("| Schema | Planned by | Keys right | Pack relationships found | Implied (shortcut) | Listed by the pack | Wrong | Wrong share |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for v, s in CASES:
        for h in ("names", "names+keys", "pack"):
            r = score(v, s, h)
            share = "–" if r["wrong_share"] is None else f"{r['wrong_share']:.2f}"
            label = "pack (self-check)" if h == "pack" else h
            print(f"| {v}, {s} names, {r['tables']} tables | {label} | {r['key_hits']} of {r['keys']} | {r['rel_hits']} of {r['relationships']} "
                  f"| {r['implied']} | {r['listed']} | {r['wrong']} | {share} |")


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


def test_finance_time_dependent_masters_and_the_chart_of_accounts():
    p = plan(sap_support.schema(["ACDOCA", "BKPF", "SKA1", "SKB1", "T001", "T004", "CSKS", "CEPC", "TKA01"], variant="s4hana"))
    rels = {(r.source, r.target) for r in p.relationships}
    assert ("ACDOCA", "SKB1") in rels and ("T001", "T004") in rels and ("SKA1", "T004") in rels
    assert ("ACDOCA", "CSKS") not in rels and ("ACDOCA", "CEPC") not in rels       # time-dependent: listed, not applied
    assert {(n["source"], n["target"]) for n in p.pack["not_applied"]} >= {("ACDOCA", "CSKS"), ("ACDOCA", "CEPC")}
    assert ("SKB1", "SKA1") not in rels                                            # no KTOPL in SKB1: through T001 only
    assert p.keys["CSKS"] == (["MANDT", "KOKRS", "KOSTL", "DATBI"], "SAP pack")


def test_open_items_point_at_their_accounting_document():
    p = plan(sap_support.schema(["BKPF", "BSEG", "BSID", "BSAK", "KNA1", "LFA1"], variant="ecc"))
    rels = {(r.source, r.target, tuple(r.source_cols)) for r in p.relationships}
    assert ("BSID", "BKPF", ("MANDT", "BUKRS", "BELNR", "GJAHR")) in rels and ("BSAK", "LFA1", ("MANDT", "LIFNR")) in rels
    # an open item is a copy of one journal line, and points at it (added in round n24; the first version lacked it)
    assert ("BSID", "BSEG", ("MANDT", "BUKRS", "BELNR", "GJAHR", "BUZEI")) in rels


@pytest.mark.parametrize("variant,conditions", [("ecc", "KONV"), ("s4hana", "PRCD_ELEMENTS")])
def test_pricing_conditions_are_found_through_knumv_not_applied(variant, conditions):
    p = plan(sap_support.schema([conditions, "KONH", "KONP", "T685", "VBAK", "VBAP", "VBRK", "EKKO"], variant=variant))
    rels = {(r.source, r.target) for r in p.relationships}
    assert (conditions, "KONH") in rels and ("KONP", "KONH") in rels
    assert not [r for r in p.relationships if r.source == conditions and r.target in ("VBAK", "VBRK", "EKKO", "VBAP", "T685")]
    listed = {(n["source"], n["target"]) for n in p.pack["not_applied"]}
    assert {(conditions, "VBAK"), (conditions, "VBRK"), (conditions, "EKKO"), (conditions, "T685")} <= listed
    assert p.keys[conditions] == (["MANDT", "KNUMV", "KPOSN", "STUNR", "ZAEHK"], "SAP pack")


def test_the_classification_counts_a_wrong_document_as_wrong_and_a_shortcut_as_implied():
    from tests.test_sap_inference import _implied
    keys, truth = sap_support.truth("ecc")
    listed = sap_support.listed("ecc")
    assert _implied(("EKET", ("mandt", "ebeln"), "EKKO"), truth)                    # EKET -> EKPO -> EKKO
    assert not _implied(("LIPS", ("mandt", "vbeln"), "VBAK"), truth, listed)        # a delivery number is not an order
    assert not _implied(("VBAP", ("mandt", "vbeln"), "LIKP"), truth, listed)        # not through two conditional links
    assert _implied(("VBAP", ("mandt", "vbeln"), "VBUK"), truth, listed)            # the status row of the same document
    assert not _implied(("RBKP", ("mandt", "bukrs", "belnr", "gjahr"), "BKPF"), truth, listed)   # two different BELNR


def test_business_partner_links_through_cvi_not_by_number():
    p = plan(sap_support.schema(["BUT000", "BUT100", "BUT020", "BUT050", "CVI_CUST_LINK", "CVI_VEND_LINK", "KNA1", "LFA1"], variant="s4hana"))
    rels = {(r.source, tuple(r.source_cols), r.target) for r in p.relationships}
    assert ("CVI_CUST_LINK", ("CLIENT", "CUSTOMER"), "KNA1") in rels and ("CVI_VEND_LINK", ("CLIENT", "VENDOR"), "LFA1") in rels
    assert ("BUT050", ("CLIENT", "PARTNER2"), "BUT000") in rels
    assert not [r for r in p.relationships if {r.source, r.target} == {"BUT000", "KNA1"}]       # never PARTNER = KUNNR
    listed = {(n["source"], n["target"]) for n in p.pack["not_applied"]}
    assert {("CVI_CUST_LINK", "BUT000"), ("CVI_VEND_LINK", "BUT000")} <= listed                   # on the GUID: listed only
    assert p.keys["BUT000"] == (["CLIENT", "PARTNER"], "SAP pack")


def test_a_dropped_client_column_named_client_is_dropped_too():
    p = plan(sap_support.schema(["BUT000", "BUT100", "CVI_CUST_LINK", "KNA1"], drop_client=True))
    r = next(r for r in p.relationships if (r.source, r.target) == ("CVI_CUST_LINK", "KNA1"))
    assert r.source_cols == ["CUSTOMER"] and r.target_cols == ["KUNNR"]
