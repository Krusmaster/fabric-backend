"""The SAP pack: its files are valid and consistent, it recognises SAP tables however they are named, and the
exports built from it follow the formats they claim (Data API builder against its own published schema)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fabric_backend import exports, sap_pack
from fabric_backend.infer import plan
from fabric_backend.schema import Schema
from tests import sap_support

FILES = sorted((sap_pack.PACKS).glob("*/*.json"))


def test_there_are_pack_files():
    assert {f.stem for f in FILES} >= {"order_to_cash", "accounting_document"}


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_every_pack_file_follows_the_schema(path):
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((sap_pack.PACKS / "pack.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft7Validator.check_schema(schema)
    errors = sorted(jsonschema.Draft7Validator(schema).iter_errors(json.loads(path.read_text(encoding="utf-8"))), key=str)
    assert not errors, "\n".join(f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors)


def test_the_merged_pack_is_consistent():
    assert sap_pack.problems(sap_pack.load("sap")) == []


def test_every_claim_has_a_source_and_every_client_specific_key_starts_with_the_client():
    p = sap_pack.load()
    for t in p["tables"].values():
        assert t["sources"] and t["key"][0] in sap_pack.CLIENT_COLUMNS, t["name"]
    for r in p["relationships"]:
        assert r["sources"], r
        assert r["source_cols"][0] in sap_pack.CLIENT_COLUMNS and r["target_cols"][0] in sap_pack.CLIENT_COLUMNS, r


def test_no_customer_specific_tables():
    names = list(sap_pack.load()["tables"])
    assert not [n for n in names if n[:1] in "ZY"]


def test_the_traps_are_explained():
    ids = {t["id"] for t in sap_pack.load()["traps"]}
    assert {"client", "amount_levels", "currency", "leading_zeros", "document_flow", "partners"} <= ids


def test_variants_are_declared_per_table():
    p = sap_pack.load()
    assert p["tables"]["ACDOCA"]["variants"] == ["s4hana"]
    assert p["tables"]["BSEG"]["variants"] == ["ecc"]
    assert p["tables"]["VBUK"]["variants"] == ["ecc"]


@pytest.mark.parametrize("name,expected", [("VBAK", "VBAK"), ("vbak", "VBAK"), ("sap_vbak", "VBAK"), ("SAP_VBAK", "VBAK"),
                                           ("bronze.sap_vbak", "VBAK"), ("stg_sap_vbap", "VBAP"), ("raw_T001", "T001"),
                                           ("orders", "ORDERS")])
def test_table_names(name, expected):
    assert sap_pack.table_name(name) == expected


@pytest.mark.parametrize("style", ["upper", "lower", "prefix"])
def test_match_with_and_without_prefix(style):
    m = sap_pack.match(sap_support.schema(style=style))
    assert m is not None and len(m.tables) == len(sap_support.schema(style=style))
    vbap = next(t for t, n in m.tables.items() if n == "VBAP")
    assert [c.upper() for c in m.keys[vbap]] == ["MANDT", "VBELN", "POSNR"]
    pairs = {(m.tables[r["source"]], m.tables[r["target"]]) for r in m.relationships}
    assert ("VBAP", "VBAK") in pairs and ("LIPS", "VBAP") in pairs and ("VBRP", "VBRK") in pairs
    assert ("VBFA", "LIPS") not in pairs                                  # many-to-many and conditional: listed, not applied
    assert any(r["source"] == next(t for t, n in m.tables.items() if n == "VBFA") for r in m.not_applied)


def test_a_dropped_client_column_is_dropped_on_both_sides_and_reported():
    m = sap_pack.match(sap_support.schema(drop_client=True))
    assert set(m.client_dropped) == set(m.tables)
    r = next(r for r in m.relationships if (r["source"], r["target"]) == ("VBAP", "VBAK"))
    assert r["source_cols"] == ["VBELN"] and r["target_cols"] == ["VBELN"]


def test_a_variant_shows_and_its_missing_tables_are_not_reported():
    m = sap_pack.match(sap_support.schema(variant="s4hana"))
    assert m.variant_hint.startswith("s4hana") and "BSEG" not in m.missing_tables
    ecc = sap_pack.match(sap_support.schema(variant="ecc"))
    assert ecc.variant_hint.startswith("ecc") and "ACDOCA" not in ecc.missing_tables


def test_a_schema_without_sap_tables_does_not_match():
    from fabric_backend import seed
    assert sap_pack.match(seed.schema()) is None


def test_one_sap_table_alone_does_not_match():
    assert sap_pack.match(sap_support.schema(["VBAK"])) is None


def test_a_table_without_its_key_columns_is_not_taken():
    rows = [("s", "VBAK", c, "nvarchar", i) for i, c in enumerate(["MANDT", "VBELN", "KUNNR"], 1)]
    rows += [("s", "VBAP", c, "nvarchar", i) for i, c in enumerate(["MANDT", "MATNR"], 1)]     # no VBELN/POSNR
    rows += [("s", "KNA1", c, "nvarchar", i) for i, c in enumerate(["MANDT", "KUNNR"], 1)]
    m = sap_pack.match(Schema.from_information_schema(rows, schema="s"))
    assert set(m.tables) == {"VBAK", "KNA1"} and m.unmatched_keyless == ["VBAP"]


# ---------------------------------------------------------------- exports

def _dab_schema():
    return json.loads((Path(__file__).parent / "fixtures" / "dab" / "dab.draft.schema.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("dab2", [False, True])
def test_dab_config_follows_the_published_schema(dab2):
    jsonschema = pytest.importorskip("jsonschema")
    cfg = exports.dab_config(plan(sap_support.schema()), dab2=dab2)
    errors = list(jsonschema.Draft7Validator(_dab_schema()).iter_errors(cfg))
    assert not errors, [e.message for e in errors][:5]
    assert cfg["data-source"]["database-type"] == "dwsql"
    for e in cfg["entities"].values():
        assert ("fields" in e) == dab2 and ("key-fields" in e["source"]) != dab2       # never both: DAB 2.0 refuses it


def test_dab_relationships_go_both_ways():
    from fabric_backend import seed
    cfg = exports.dab_config(plan(seed.schema()))
    rels = [(n, r["cardinality"], r["target.entity"]) for n, e in cfg["entities"].items() for r in e.get("relationships", {}).values()]
    assert any(c == "one" for _, c, _ in rels) and any(c == "many" for _, c, _ in rels)
    for e in cfg["entities"].values():
        for r in e.get("relationships", {}).values():
            assert r["target.entity"] in cfg["entities"] and len(r["source.fields"]) == len(r["target.fields"])


def test_krusgraph_plan_round_trips():
    from fabric_backend import seed
    p = plan(seed.schema())
    out = exports.krusgraph_plan(p)
    again = plan(seed.schema(), keys=out["keys"], confirmed=[{k: v for k, v in c.items() if k != "rule"} for c in out["confirmed"]])
    assert {r.key for r in again.relationships} == {r.key for r in p.relationships}


def test_extraction_list_takes_delta_columns_from_the_pack():
    s = sap_support.schema(style="prefix")
    out = exports.extraction_list(plan(s), sap_pack.match(s))
    assert out["format"] == exports.EXTRACTION_FORMAT
    vbak = next(t for t in out["tables"] if t["table"] == "sap_vbak")
    assert vbak["delta_columns"] == ["erdat", "aedat"] and vbak["pack_table"] == "VBAK"
    for t in out["tables"]:
        assert t.get("open_mirroring_metadata") == ({"keyColumns": t["key"]} if t["key"] else None)
