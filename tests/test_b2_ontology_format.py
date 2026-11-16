"""B2 (15 November 2026, backlog B-01): the ontology format check before the old experience retires (31 January 2027).

Krusgraph writes the TMDL definition only; nothing in the package reads or writes the old entity-type JSON. The part
names follow Learn's ontology definition (read 15 November 2026): an unqualified entities/{name}.tmdl is an entity in
the default namespace, and namespaces/default.tmdl is required and referenced by `ref namespace default`.
tools/ontology_compare.py compares a live Get Definition answer with ontology_parts; here it runs on recorded and
synthetic answers only. Nothing is called in Fabric.
"""
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from fabric_backend import ontology, seed
from fabric_backend.infer import plan

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import ontology_compare as oc  # noqa: E402

ARGS = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="22222222-2222-2222-2222-222222222222",
            item_name="shop_lh", sql_endpoint="x.datawarehouse.fabric.microsoft.com")
WINDFARM = ROOT / "tests" / "fixtures" / "ontology_windfarm"


def ours() -> dict[str, str]:
    return ontology.ontology_parts(plan(seed.schema("shop"), None, None), "shop_ontology", schema="shop", **ARGS)


def answer(parts: dict[str, str]) -> dict:
    return {"definition": {"parts": [{"path": p, "payload": base64.b64encode(t.encode()).decode(), "payloadType": "InlineBase64"}
                                     for p, t in parts.items()]}}


def test_krusgraph_writes_tmdl_only_with_learns_default_namespace_layout():
    parts = ours()
    assert all(p == ".platform" or p.endswith(".tmdl") for p in parts)
    assert json.loads(parts[".platform"])["config"]["version"] == "2.0"
    assert "namespaces/default.tmdl" in parts and "ref namespace default" in parts["model.tmdl"]
    entities = [p for p in parts if p.startswith("entities/")]
    assert entities and all("#" not in p for p in entities)       # unqualified: the default namespace
    assert oc.format_of(parts) == oc.NEW


def test_another_namespace_is_refused_rather_than_written_wrong():
    with pytest.raises(ValueError, match="only the default namespace"):
        ontology.ontology_parts(plan(seed.schema("shop"), None, None), "x", schema="shop", namespace="sales", **ARGS)


def test_nothing_in_the_package_reads_or_writes_the_old_format():
    old = re.compile(r"EntityTypes/|KustoTable|ontology-old|entityIdParts|namespaceType")
    hits = [f"{p.relative_to(ROOT)}" for p in (ROOT / "fabric_backend").rglob("*")
            if p.is_file() and p.suffix in {".py", ".json", ".html", ".js", ".md", ".txt"} and old.search(p.read_text(errors="ignore"))]
    assert hits == []


def test_the_same_definition_compares_as_same():
    r = oc.report(answer(ours()))                                 # workspace and item read from the annotations
    assert r["format"] == oc.NEW and r["only_live"] == [] and r["only_ours"] == []
    assert set(r["parts"].values()) == {"same"} and r["entity_paths_unqualified"]
    assert r["verdict"] == "TMDL, and every part as Krusgraph writes it"


def test_fabrics_line_ends_and_lineage_tags_are_not_differences():
    live = {p: re.sub(r"lineageTag: \S+", "lineageTag: 0000", t).replace("\n", "\r\n") for p, t in ours().items()}
    r = oc.report(answer(live))
    assert set(r["parts"].values()) == {"same"}


def test_an_extra_part_and_a_changed_line_are_reported():
    live = ours()
    live["rules/SpeedLimit.tmdl"] = "rule SpeedLimit\n"
    live["database.tmdl"] = live["database.tmdl"].replace("1000000", "1600")
    r = oc.report(answer(live))
    assert r["only_live"] == ["rules/SpeedLimit.tmdl"] and r["parts"]["database.tmdl"] == "2 lines differ"
    assert r["verdict"].startswith("TMDL; the differences above")


def test_learns_old_format_sample_is_recognised_as_old():
    """The shape of the 200 answer in Learn's Get Ontology Definition example (page updated 19 October 2026)."""
    old = {"definition.json": "{}", "EntityTypes/8813598896083/definition.json": json.dumps({"id": "8813598896083", "name": "Equipment1"}),
           ".platform": "dotPlatformBase64String"}
    r = oc.report(answer(old))
    assert r["format"] == oc.OLD and "re-create it" in r["verdict"]


def test_microsofts_windfarm_sample_is_tmdl_with_a_namespaced_entity():
    manifest = json.loads((WINDFARM / "parts.json").read_text())
    parts = {p["path"]: (WINDFARM / "parts" / p["path"]).read_text(encoding="utf-8") for p in manifest["parts"]}
    assert oc.format_of(parts) == oc.NEW
    assert "entities/mynamespace#wind_turbines2.tmdl" in parts and "entities/wind_turbines.tmdl" in parts


def test_without_annotations_it_asks_for_the_ids():
    live = {p: re.sub(r"\t\tannotation ONT_\w+ = .*\n", "", t) for p, t in ours().items()}
    assert "pass --workspace-id" in oc.report(answer(live))["verdict"]


def test_the_command_line(tmp_path):
    f = tmp_path / "answer.json"
    f.write_text(json.dumps(answer(ours())))
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "ontology_compare.py"), str(f)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith("format: TMDL (new experience)") and "every part" in r.stdout
    f.write_text(json.dumps(answer({"definition.json": "{}"})))
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "ontology_compare.py"), str(f), "--json"], capture_output=True, text=True)
    assert r.returncode == 1 and json.loads(r.stdout)["format"] == oc.OLD
