"""How well `plan()` recovers declared keys and foreign keys from names alone.

Each fixture in tests/fixtures/schemas/ is an openly licensed example database whose official DDL declares primary
and foreign keys (see the README there). The benchmark feeds `plan()` the table and column names only — exactly
what a lakehouse SQL endpoint offers — and scores the inferred keys and relationships against the declared ones.

The numbers below are the current state and are asserted exactly, so any change to a rule shows up here and has
to be a conscious decision: an improvement raises `hits` or lowers `wrong`; a regression fails the test.
`python tests/test_inference_quality.py` prints the table that docs/INFERENCE.md carries.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fabric_backend import seed
from fabric_backend.infer import plan
from fabric_backend.schema import Schema

FIXTURES = Path(__file__).parent / "fixtures" / "schemas"
NAMES = ("northwind", "chinook", "tpch", "adventureworks", "sakila", "wideworldimporters", "wideworldimportersdw")
SYNTHETIC = ("nordic_sv", "nordic_de", "dw_names", "app_names")      # written by hand for the naming rules; no public source


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def names_only(fixture: dict) -> Schema:
    """The fixture as a lakehouse would present it: columns and types, no keys, no foreign keys."""
    rows = [("dbo", t["name"], col, typ, i) for t in fixture["tables"] for i, (col, typ) in enumerate(t["columns"], 1)]
    return Schema.from_information_schema(rows, schema="dbo")


def _k(cols) -> tuple[str, ...]:
    return tuple(c.lower() for c in cols)


def score(fixture: dict) -> dict:
    """keys: per table with a declared primary key, is the inferred key exactly that key?
    relationships: per declared foreign key (source, columns, target), was it inferred? `wrong` counts inferred
    relationships that are not declared, `wrong_keys` inferred keys that differ from the declared one."""
    p = plan(names_only(fixture))
    declared_keys = {t["name"]: _k(t["primary_key"]) for t in fixture["tables"] if t["primary_key"]}
    inferred_keys = {t: _k(cols) for t, (cols, _) in p.keys.items()}
    key_hits = sum(1 for t, k in declared_keys.items() if inferred_keys.get(t) == k)
    key_wrong = sum(1 for t, k in declared_keys.items() if t in inferred_keys and inferred_keys[t] != k)
    declared = {(t["name"], _k(f["columns"]), f["ref_table"]) for t in fixture["tables"] for f in t["foreign_keys"]}
    inferred = {(r.source, _k(r.source_cols), r.target) for r in p.relationships}
    return {
        "tables": len(fixture["tables"]), "keys_declared": len(declared_keys), "key_hits": key_hits,
        "key_wrong": key_wrong, "key_missed": len(declared_keys) - key_hits - key_wrong,
        "fks_declared": len(declared), "rel_hits": len(declared & inferred), "rel_missed": len(declared - inferred),
        "rel_wrong": len(inferred - declared), "ambiguous": len(p.ambiguous),
        "missed_keys": sorted(t for t, k in declared_keys.items() if inferred_keys.get(t) != k),
        "missed_rels": sorted(f"{s}.{'+'.join(c)} -> {t}" for s, c, t in declared - inferred),
        "wrong_rels": sorted(f"{s}.{'+'.join(c)} -> {t}" for s, c, t in inferred - declared),
    }


# The current state, asserted exactly (see the module docstring). Update together with docs/INFERENCE.md.
EXPECTED = {
    "northwind": {"tables": 13, "keys_declared": 13, "key_hits": 11, "key_wrong": 0, "key_missed": 2,
                  "fks_declared": 13, "rel_hits": 10, "rel_missed": 3, "rel_wrong": 0, "ambiguous": 0},
    "chinook": {"tables": 11, "keys_declared": 11, "key_hits": 11, "key_wrong": 0, "key_missed": 0,
                "fks_declared": 11, "rel_hits": 9, "rel_missed": 2, "rel_wrong": 0, "ambiguous": 0},
    "tpch": {"tables": 8, "keys_declared": 8, "key_hits": 8, "key_wrong": 0, "key_missed": 0,
             "fks_declared": 8, "rel_hits": 8, "rel_missed": 0, "rel_wrong": 2, "ambiguous": 0},
    "adventureworks": {"tables": 71, "keys_declared": 71, "key_hits": 47, "key_wrong": 4, "key_missed": 20,
                       "fks_declared": 90, "rel_hits": 62, "rel_missed": 28, "rel_wrong": 17, "ambiguous": 0},
    "sakila": {"tables": 16, "keys_declared": 16, "key_hits": 15, "key_wrong": 0, "key_missed": 1,
               "fks_declared": 22, "rel_hits": 22, "rel_missed": 0, "rel_wrong": 1, "ambiguous": 0},
    "wideworldimporters": {"tables": 33, "keys_declared": 31, "key_hits": 30, "key_wrong": 0, "key_missed": 1,
                           "fks_declared": 98, "rel_hits": 65, "rel_missed": 33, "rel_wrong": 0, "ambiguous": 0},
    "wideworldimportersdw": {"tables": 14, "keys_declared": 13, "key_hits": 8, "key_wrong": 5, "key_missed": 0,
                             "fks_declared": 29, "rel_hits": 26, "rel_missed": 3, "rel_wrong": 0, "ambiguous": 0},
    "nordic_sv": {"tables": 6, "keys_declared": 6, "key_hits": 6, "key_wrong": 0, "key_missed": 0,
                  "fks_declared": 6, "rel_hits": 6, "rel_missed": 0, "rel_wrong": 0, "ambiguous": 0},
    "nordic_de": {"tables": 5, "keys_declared": 5, "key_hits": 5, "key_wrong": 0, "key_missed": 0,
                  "fks_declared": 5, "rel_hits": 4, "rel_missed": 1, "rel_wrong": 0, "ambiguous": 0},
    "dw_names": {"tables": 4, "keys_declared": 4, "key_hits": 4, "key_wrong": 0, "key_missed": 0,
                 "fks_declared": 3, "rel_hits": 3, "rel_missed": 0, "rel_wrong": 0, "ambiguous": 0},
    "app_names": {"tables": 7, "keys_declared": 7, "key_hits": 7, "key_wrong": 0, "key_missed": 0,
                  "fks_declared": 8, "rel_hits": 6, "rel_missed": 2, "rel_wrong": 0, "ambiguous": 0},
}


@pytest.mark.parametrize("name", NAMES + SYNTHETIC)
def test_scores_are_the_documented_ones(name):
    got = score(load(name))
    numbers = {k: v for k, v in got.items() if not k.startswith(("missed_", "wrong_"))}
    assert numbers == EXPECTED[name], got


def test_shop_schema_is_not_degraded():
    """The synthetic shop schema from seed.py is the reference every rule change is checked against."""
    p = plan(seed.schema("shop"))
    assert p.summary().startswith("7 tables, 6 with keys, 6 relationships")
    assert p.keys["order_items"] == (["order_id", "line_no"], "K5") and p.keys["orders"] == (["order_id"], "K2")
    assert {(r.source, tuple(r.source_cols), r.target, r.rule) for r in p.relationships} == {
        ("products", ("category_id",), "categories", "R1"), ("addresses", ("customer_id",), "customers", "R1"),
        ("orders", ("customer_id",), "customers", "R1"), ("order_items", ("order_id",), "orders", "R1"),
        ("order_items", ("product_id",), "products", "R1"), ("audit_log", ("customer_id",), "customers", "R1")}
    assert p.ambiguous == [] and p.keyless == ["audit_log"]
    assert not any(r.source_cols == ["ship_to_id"] for r in p.relationships)      # no rule matches it; stays unlinked


def markdown() -> str:
    head = "| Schema | Tables | Keys declared | Keys hit | Keys wrong | Keys missed | FKs declared | Rels hit | Rels missed | Rels wrong | Ambiguous |"
    out = [head, "|" + " --- |" * 11]
    for n in NAMES + SYNTHETIC:
        s = score(load(n))
        out.append(f"| {n} | {s['tables']} | {s['keys_declared']} | {s['key_hits']} | {s['key_wrong']} | {s['key_missed']} | "
                   f"{s['fks_declared']} | {s['rel_hits']} | {s['rel_missed']} | {s['rel_wrong']} | {s['ambiguous']} |")
    return "\n".join(out)


if __name__ == "__main__":
    print(markdown())
    for n in NAMES + SYNTHETIC:
        s = score(load(n))
        print(f"\n## {n}\nmissed keys: {s['missed_keys']}\nmissed rels: {s['missed_rels']}\nwrong rels: {s['wrong_rels']}")
