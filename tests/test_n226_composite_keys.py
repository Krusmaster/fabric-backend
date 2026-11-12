"""n226 (SCOPE-REVIEW section 6, item 3): composite keys carried through.

The silver step writes one combined key column per composite key and per composite link (fabric_backend/combined_keys.py),
and the semantic model and the ontology relate on those columns, reading the silver layer. Proved on the repository's
synthetic SAP sample (fabric_backend/sap_sample.py: SAP-shaped, not SAP data, not an SAP system).

Measured on 12 November 2026, before and after (the "before" is the same draft with combined=False, which is exactly
what the code produced before n226):
  sap_sd  model: 0 relationships, 19 not expressible  ->  19 relationships (10 active, 9 inactive), 0 not expressible
          ontology: 0 of 12 entity types with a key, 0 relationship types, 19 skipped  ->  10 with a key, 19, 0 skipped
  sap_mm  model: 0 relationships, 8 not expressible   ->  8 relationships (7 active, 1 inactive), 0 not expressible
          ontology: 0 of 8 with a key, 0 relationship types, 8 skipped  ->  7 with a key, 8, 0 skipped
A schema with single-column links only (the shop) is drafted exactly as before: nothing is combined."""
import pytest

from fabric_backend import combined_keys as ck, ontology, sap_sample, seed, semantic_model, silver
from fabric_backend.infer import plan

INFO = {"item_name": "lh", "item_kind": "Lakehouse", "item_id": "i", "workspace_id": "w"}

# (model active, inactive, not expressible; ontology with_key, relationship types, skipped) before and after
BEFORE = {"sap_sd": (0, 0, 19, 0, 0, 19), "sap_mm": (0, 0, 8, 0, 0, 8)}
AFTER = {"sap_sd": (10, 9, 0, 10, 19, 0), "sap_mm": (7, 1, 0, 7, 8, 0)}


def _plan(sample):
    return plan(sap_sample.schema(sample))


def _numbers(p, sample, combined):
    m = semantic_model.draft(p, {**INFO, "schema": sample}, combined=combined)["summary"]
    o = ontology.summary(p) if combined is not False else _ontology_before(p)
    return (m["relationships_active"], m["relationships_inactive"], m["relationships_not_expressible"],
            o["with_key"], o["relationship_types"], o["skipped_relationships"])


def _ontology_before(p):
    """The ontology as it was before n226: the plan's own composite keys and links, nothing combined."""
    model = ontology._model(p, None)
    names = {t.name for t, *_ in model}
    rels = [r for r in p.relationships if r.source in names and r.target in names]
    single = [r for r in rels if len(r.source_cols) == 1 and len(r.target_cols) == 1]
    return {"with_key": sum(1 for _, key, *_ in model if key), "relationship_types": len(single),
            "skipped_relationships": len(rels) - len(single)}


@pytest.mark.parametrize("sample", sap_sample.SAMPLES)
def test_sap_sample_before_and_after(sample):
    p = _plan(sample)
    assert _numbers(p, sample, False) == BEFORE[sample]
    assert _numbers(p, sample, None) == AFTER[sample]


def test_the_model_relates_on_the_combined_columns_and_reads_silver():
    p = _plan("sap_sd")
    d = semantic_model.draft(p, {**INFO, "schema": "sap_sd"})
    rels = d["parts"]["definition/relationships.tmdl"]
    assert "fromColumn: VBAP.MANDT_VBELN_key\n\ttoColumn: VBAK.MANDT_VBELN_key" in rels
    assert "fromColumn: VBRP.MANDT_AUBEL_AUPOS_key\n\ttoColumn: VBAP.MANDT_VBELN_POSNR_key" in rels
    vbak = d["parts"]["definition/tables/VBAK.tmdl"]
    assert "\tcolumn MANDT_VBELN_key\n\t\tdataType: string\n\t\tisKey\n" in vbak
    assert "\t\t\tentityName: VBAK\n\t\t\tschemaName: silver\n" in vbak
    reads = d["summary"]["reads"]
    assert reads["layer"] == "silver" and "only the silver step writes them" in reads["said"]
    assert {"table": "VBAK", "column": "MANDT_VBELN_key", "combines": ["MANDT", "VBELN"], "for": ["the key of VBAK"]} \
        in d["summary"]["combined_key_columns"]
    readme = d["parts"]["README.generated.md"]
    assert "## Combined key columns" in readme and "validate_plan counts whether it is unique" in readme


def test_a_lakehouse_without_schemas_reads_the_prefixed_silver_tables():
    p = _plan("sap_sd")
    d = semantic_model.draft(p, {**INFO, "schema": "dbo", "schemas_enabled": False})
    vbak = d["parts"]["definition/tables/VBAK.tmdl"]
    assert "entityName: silver_VBAK" in vbak and "schemaName" not in vbak


def test_a_warehouse_has_no_silver_step_so_nothing_is_combined():
    p = _plan("sap_sd")
    s = semantic_model.draft(p, {**INFO, "schema": "sap_sd", "item_kind": "Warehouse"})["summary"]
    assert s["relationships_not_expressible"] == 19 and "reads" not in s


def test_the_ontology_keys_and_relates_on_the_combined_columns():
    p = _plan("sap_mm")
    parts = ontology.ontology_parts(p, "o", workspace_id="w", item_id="i", item_name="lh", schema="sap_mm")
    assert "\tkeyProperty: MANDT_EBELN_EBELP_key\n" in parts["entities/EKPO.tmdl"]
    assert "fromColumn: EKBE.MANDT_EBELN_EBELP_key\n\ttoColumn: EKPO.MANDT_EBELN_EBELP_key" in parts["relationships.tmdl"]
    assert "schemaName: silver" in parts["tables/EKPO.tmdl"]
    b = {x["entity_type"]: x for x in ontology.bindings(p, "lh", "sap_mm")}
    assert b["EKPO"]["table"] == "silver.EKPO" and b["EKPO"]["key"] == "MANDT_EBELN_EBELP_key"
    assert "silver" in ontology.summary(p)["reads"]


def test_silver_writes_the_combined_columns_with_the_unit_separator():
    p = _plan("sap_sd")
    s = silver.spec(p, {**INFO, "schema": "sap_sd"})
    src = silver.notebook_source(s)
    assert ('df = df.withColumn("MANDT_VBELN_key", F.concat(col(\'MANDT\').cast(\'string\'), F.lit(chr(31)), '
            "col('VBELN').cast('string')))") in src
    vbap = next(t for t in s["tables"] if t["table"] == "VBAP")
    assert [c["name"] for c in vbap["combined"]] == ["MANDT_VBELN_POSNR_key", "MANDT_VBELN_key", "MANDT_MATNR_key"]
    step = next(x for x in silver.steps(s) if x["table"] == "VBAP")
    assert step["combined_key_columns"][0] == {"column": "MANDT_VBELN_POSNR_key", "combines": ["MANDT", "VBELN", "POSNR"]}


@pytest.mark.parametrize("sample", sap_sample.SAMPLES)
def test_on_the_silver_rows_every_carried_link_finds_its_combined_key(sample):
    """The silver step in Python (silver.simulate) on the sample's rows: after its reference checks, every combined
    source value of a carried link is a combined key value of the target, and every combined key is unique there."""
    p = _plan(sample)
    data = {t: [dict(zip([c for c, _ in sap_sample._cols(sample, t)], r)) for r in rows]
            for t, rows in sap_sample.rows(sample).items()}
    rows = silver.simulate(silver.spec(p, {**INFO, "schema": sample}), data)["silver"]
    carried, combined = ck.carry(p)
    checked = 0
    for r in carried.relationships:
        if r.source_cols[0].endswith(ck.SUFFIX):
            keys = [x[r.target_cols[0]] for x in rows[r.target]]
            assert len(keys) == len(set(keys)) and None not in keys
            values = {x[r.source_cols[0]] for x in rows[r.source]} - {None}
            assert values <= set(keys), (r.source, r.target)
            checked += 1
    assert checked == len(p.relationships)


def test_the_value_is_unambiguous_and_null_when_a_part_is():
    assert ck.value({"a": "1", "b": "23"}, ["a", "b"]) != ck.value({"a": "12", "b": "3"}, ["a", "b"])
    assert ck.value({"a": "1", "b": None}, ["a", "b"]) is None
    assert ck.column_name(["MANDT", "VBELN"], {"mandt_vbeln_key"}) == "MANDT_VBELN_key_kg"
    assert ck.sql_expr(["MANDT", "VBELN"], lambda c: f"`{c}`", "s") == "concat(CAST(s.`MANDT` AS STRING), char(31), CAST(s.`VBELN` AS STRING))"


def test_single_column_links_are_drafted_exactly_as_before():
    p = plan(seed.schema("shop"))
    assert ck.columns(p) == {} and ck.carry(p) == (p, {})
    info = {**INFO, "schema": "shop"}
    assert semantic_model.draft(p, info) == semantic_model.draft(p, info, combined=False)
    s = silver.spec(p, info)
    assert not any("combined" in t for t in s["tables"]) and "Combined key column" not in silver.notebook_source(s)
    assert "reads" not in ontology.summary(p)
