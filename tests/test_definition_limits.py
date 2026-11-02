"""limits.part_problems / ontology_problems / check_definition (n81): the parts of a definition and Fabric's own payload
limits for an ontology, as "Payload limits" in microsoft/mcp's ontology-definition.md (commit 7257a94) gives them."""
import base64

import pytest

from fabric_backend import limits, ontology, seed
from fabric_backend.infer import plan


def part(path, text="x"):
    return {"path": path, "payload": base64.b64encode(text.encode()).decode(), "payloadType": "InlineBase64"}


def test_good_parts_pass():
    assert limits.part_problems([part(".platform"), part("database.tmdl"), part("tables/a.tmdl"), part("tables/b.tmdl")]) == []
    assert limits.part_problems({"model.tmdl": "", "entities/a.tmdl": ""}) == []


def test_paths_are_unique_ignoring_case():
    problems = limits.part_problems([part("tables/Orders.tmdl"), part("tables/orders.tmdl")])
    assert problems == ["parts 'tables/Orders.tmdl' and 'tables/orders.tmdl' have the same path when case is ignored"]


@pytest.mark.parametrize("paths", [["tables", "tables/a.tmdl"], ["Tables", "tables/a.tmdl"], ["a/b", "a/b/c.tmdl"]])
def test_no_path_is_both_a_file_and_a_folder(paths):
    problems = limits.part_problems([part(p) for p in paths])
    assert len(problems) == 1 and "is a file, and also a folder" in problems[0]


@pytest.mark.parametrize("payload", ["not base64!", "abc", "eA=", "e A=="])
def test_an_inline_payload_must_be_valid_base64(payload):
    assert limits.part_problems([{"path": "a.tmdl", "payload": payload, "payloadType": "InlineBase64"}]) == [
        "part 'a.tmdl': the payload is not valid base64"]


@pytest.mark.parametrize("path", ["", "/abs.tmdl", "a//b.tmdl", "../up.tmdl", "a/./b.tmdl", "a\\b.tmdl"])
def test_paths_are_relative_and_plain(path):
    assert limits.part_problems([part(path)])


def test_the_shop_ontology_is_within_fabrics_limits():
    parts = ontology.ontology_parts(plan(seed.schema("shop"), None, None), "shop_ontology", workspace_id="w", item_id="i", item_name="shop_lh")
    assert limits.ontology_problems(parts) == []
    limits.check_definition(ontology.envelope("shop_ontology", parts)["definition"], "Ontology")


def test_fabrics_limits_are_the_documented_numbers():
    L = limits.ONTOLOGY_LIMITS
    assert (L["tables"], L["columns_per_table"], L["model_budget"]) == (15_998, 15_997, 16_000)
    assert L["entities"] == L["relationships"] == L["entity_relationships"] == L["namespaces"] == L["expressions"] == 10_000
    assert (L["rules"], L["partitions_per_table"], L["properties_per_entity"]) == (1_000, 1_000, 1_000)
    assert (L["name_chars"], L["description_chars"], L["annotation_chars"]) == (512, 4_000, 4_000)
    assert 1024 not in L.values()                                       # another project's local budget, not Fabric's


def test_counts_over_a_limit_are_named(monkeypatch):
    monkeypatch.setitem(limits.ONTOLOGY_LIMITS, "columns_per_table", 2)
    monkeypatch.setitem(limits.ONTOLOGY_LIMITS, "model_budget", 5)
    monkeypatch.setitem(limits.ONTOLOGY_LIMITS, "properties_per_entity", 1)
    table = "table t\n\tlineageTag: x\n\n\tcolumn a\n\t\tdataType: string\n\tcolumn b\n\tcolumn c\n\n\tpartition t = entity\n"
    entity = "entity t\n\tproperty a\n\tproperty b\n"
    problems = limits.ontology_problems({"tables/t.tmdl": table, "entities/t.tmdl": entity})
    assert problems == ["columns in tables/t.tmdl: 3, Fabric's limit is 2", "2 + tables + columns: 6, Fabric's limit is 5",
                        "properties in entities/t.tmdl: 2, Fabric's limit is 1"]


def test_long_names_descriptions_and_annotations_are_refused():
    long = "n" * 513
    parts = {"tables/t.tmdl": f"table {long}\n\tpartition t = entity\n\t\tannotation A = {'v' * 4001}\n",
             "entities/t.tmdl": f"/// {'d' * 4001}\nentity t\n"}
    problems = limits.ontology_problems(parts)
    assert any("the name of a table in tables/t.tmdl: 513" in p for p in problems)
    assert any("an annotation value in tables/t.tmdl: 4,001" in p for p in problems)
    assert any("a description in entities/t.tmdl: 4,001" in p for p in problems)


def test_check_definition_says_nothing_was_sent():
    with pytest.raises(limits.DefinitionError) as refused:
        limits.check_definition({"parts": [part("a"), part("a/b")]})
    assert str(refused.value).startswith("the definition was not sent to Fabric: ")
