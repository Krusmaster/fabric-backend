"""2026-11-21, round BL8 (sprint item BL8, backlog C-10). SAP tables found with any prefix or suffix.

A landed SAP table carries the system id, the client or a landing word (`ecc_VBAK`, `VBAK_800`, `P01_VBAK`): the pack
finds it and says why. A table under a name that says nothing is recognised by its key columns (MANDT + KUNNR) as a
suggestion, not applied, so the renamed corpus keeps its published scores. Two tables pointing at one pack table are
reported, never guessed. A non-SAP schema matches nothing.
"""
from __future__ import annotations

import pytest

from fabric_backend import sap_pack
from fabric_backend.schema import Schema

HEADER = ["MANDT", "VBELN", "KUNNR", "AUART", "NETWR", "WAERK"]
ITEM = ["MANDT", "VBELN", "POSNR", "MATNR", "NETWR", "WAERK"]
CUSTOMER = ["MANDT", "KUNNR", "NAME1", "LAND1"]


def schema(tables: dict[str, list[str]]) -> Schema:
    rows = [("s", t, c, "nvarchar", i) for t, cols in tables.items() for i, c in enumerate(cols, 1)]
    return Schema.from_information_schema(rows, schema="s")


# ---------------------------------------------------------------- the names an SAP architect tries first

@pytest.mark.parametrize("name, prefix, suffix", [
    ("ecc_VBAK", "ecc_", ""),
    ("VBAK_800", "", "_800"),
    ("P01_VBAK", "P01_", ""),
    ("p01-vbak.800", "p01-", ".800"),
    ("bronze.P01_VBAK_prd", "bronze.P01_", "_prd"),
])
def test_a_known_table_is_found_with_a_prefix_or_suffix(name, prefix, suffix):
    assert sap_pack.pack_table(name) == "VBAK"
    m = sap_pack.match(schema({name: HEADER, "KNA1": CUSTOMER}))
    assert m.tables == {name: "VBAK", "KNA1": "KNA1"}
    assert m.keys[name] == ["MANDT", "VBELN"]
    parts = ([f"prefix {prefix}"] if prefix else []) + ([f"suffix {suffix}"] if suffix else [])
    assert m.name_reasons == {name: f"VBAK matched as {name}, {' and '.join(parts)}"}
    assert any(r["source"] == name and r["target"] == "KNA1" for r in m.relationships)


def test_the_reason_is_written_as_the_sprint_asks():
    m = sap_pack.match(schema({"P01_VBAK": HEADER, "P01_VBAP": ITEM}))
    assert m.name_reasons["P01_VBAK"] == "VBAK matched as P01_VBAK, prefix P01_"
    assert {(r["source"], r["target"]) for r in m.relationships} >= {("P01_VBAP", "P01_VBAK")}


def test_a_prefixed_table_still_needs_its_key_columns():
    m = sap_pack.match(schema({"P01_VBAK": HEADER, "P01_VBAP": ["MANDT", "MATNR"], "KNA1": CUSTOMER}))
    assert set(m.tables) == {"P01_VBAK", "KNA1"} and m.unmatched_keyless == ["P01_VBAP"]


@pytest.mark.parametrize("name", ["VBAK_old_stuff", "VBAKX", "my_sales_VBAK", "dim_Customer", "stg-customers"])
def test_a_word_that_is_not_a_landing_affix_is_not_stripped(name):
    # a version, a client, a system id or a landing word only; an alias (CUSTOMER of I_Customer) never takes an affix
    assert sap_pack._affixed(name) is None


def test_the_other_packs_take_no_affix():
    assert sap_pack.pack_table("P01_Account", "salesforce") is None
    assert sap_pack._affixed("P01_Account", "salesforce") is None


# ---------------------------------------------------------------- an unknown name with SAP's key columns

def test_a_table_with_the_key_signature_is_recognised_by_its_key_columns():
    s = schema({"P01_VBAK": HEADER, "VBAP_800": ITEM, "debitors": CUSTOMER})
    rec = {r["table"]: r for r in sap_pack.recognise(s)}
    assert rec["debitors"]["pack_table"] == "KNA1" and rec["debitors"]["how"] == "key columns"
    assert rec["debitors"]["reason"].startswith("key columns: debitors carries KNA1's key MANDT + KUNNR")
    m = sap_pack.match(s)
    # a suggestion, not applied: the name says nothing, so the pack's keys and links are not put on it
    assert "debitors" not in m.tables
    assert m.by_key_columns == [{"table": "debitors", "pack_table": "KNA1", "reason": rec["debitors"]["reason"]}]


def test_a_key_that_fits_several_tables_is_reported_not_guessed():
    rec = {r["table"]: r for r in sap_pack.recognise(schema({"docs": ["MANDT", "VBELN"]}))}
    assert rec["docs"]["how"] == "ambiguous" and rec["docs"]["pack_table"] is None
    assert {"VBAK", "LIKP", "VBRK"} <= set(rec["docs"]["candidates"])


# ---------------------------------------------------------------- ambiguity

def test_two_landings_of_one_table_are_reported_not_guessed():
    m = sap_pack.match(schema({"P01_VBAK": HEADER, "VBAK_800": HEADER, "KNA1": CUSTOMER, "VBAP": ITEM}))
    assert "P01_VBAK" not in m.tables and "VBAK_800" not in m.tables
    assert m.ambiguous == [{"tables": ["P01_VBAK", "VBAK_800"], "candidates": ["VBAK"],
                            "why": "P01_VBAK, VBAK_800 all point at VBAK; not guessed"}]


def test_the_own_name_wins_over_a_prefixed_copy_and_the_copy_is_reported():
    m = sap_pack.match(schema({"VBAK": HEADER, "P01_VBAK": HEADER, "KNA1": CUSTOMER}))
    assert m.tables == {"VBAK": "VBAK", "KNA1": "KNA1"}
    assert [x["tables"] for x in m.ambiguous] == [["P01_VBAK"]]
    assert "is there by its name (VBAK)" in m.ambiguous[0]["why"]


def test_two_tables_by_name_keep_their_old_answer_and_are_reported():
    m = sap_pack.match(schema({"vbak": HEADER, "sap_vbak": HEADER, "KNA1": CUSTOMER}))
    assert m.tables["vbak"] == "VBAK" and "sap_vbak" not in m.tables          # as before round BL8
    assert m.ambiguous == [{"tables": ["vbak", "sap_vbak"], "candidates": ["VBAK"],
                            "why": "vbak, sap_vbak all point at VBAK by name; the first with its key columns is used, as before round BL8"}]


# ---------------------------------------------------------------- what must not change

def test_the_shop_matches_nothing():
    from fabric_backend import seed
    s = seed.schema()
    assert sap_pack.match(s) is None
    assert all(r["pack_table"] is None and r["how"] is None for r in sap_pack.recognise(s))


def test_a_schema_named_the_plain_way_is_matched_as_before():
    m = sap_pack.match(schema({"VBAK": HEADER, "VBAP": ITEM, "KNA1": CUSTOMER}))
    assert m.tables == {"VBAK": "VBAK", "VBAP": "VBAP", "KNA1": "KNA1"}
    assert m.name_reasons == {} and m.by_key_columns == [] and m.ambiguous == []
