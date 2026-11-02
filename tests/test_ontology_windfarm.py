"""Microsoft's WindFarm ontology sample against what ontology.ontology_parts writes (n81).

The fixture is the 35 parts of the "Full WindFarm ontology definition example" in
tools/Fabric.Mcp.Tools.Docs/src/Resources/item-definitions/ontology-definition.md, github.com/microsoft/mcp at commit
7257a94355dd63ba4f1ba43fc5ae5dfcd1a7203d (MIT, Copyright (c) Microsoft Corporation; tests/fixtures/ontology_windfarm/).

The tests check that both definitions have the same skeleton and the same object shapes, and they write down every
difference found (DIFFERENCES), each as an assertion on both sides. The writer is not changed here: our format created
shop_ontology live, and a difference is taken over only once it has been tried in Fabric.
"""
import base64
import hashlib
import json
from pathlib import Path

import pytest

from fabric_backend import limits, ontology, seed
from fabric_backend.infer import plan

FIXTURE = Path(__file__).parent / "fixtures" / "ontology_windfarm"
MANIFEST = json.loads((FIXTURE / "parts.json").read_text())
ARGS = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="shop_lh", schema="shop",
            sql_endpoint="x.datawarehouse.fabric.microsoft.com")

# What the sample does that ontology_parts does not (or the other way round), as found on 2 November 2026.
DIFFERENCES = [
    ("database.tmdl", "`database` without a name (and a /// description)", "`database {name}`"),
    ("model.tmdl", "`model Model`", "`model {name}`"),
    ("expressions.tmdl", "`expression DatabaseQuery = Sql.Database(\"<SQL analytics endpoint>\", \"<database id>\")`",
     "`expression 'DirectLake - {item}' = AzureStorage.DataLake(\"https://onelake.dfs.fabric.microsoft.com/{ws}/{item}\", ...)`"),
    ("tables/*", "no annotations on the partition", "annotations ONT_WorkspaceId, ONT_ItemId, ONT_ItemKind, ONT_ItemName, "
     "ONT_SqlEndpoint, ONT_SqlDatabase under the partition"),
    ("tables/*", "`formatString` on number and date columns", "no formatString"),
    ("entityRelationships.tmdl", "no `label`; names with spaces, quoted ('Blade On Turbine')", "a `label:` line; names without spaces"),
    ("entities/*", "a /// description on every property", "a /// line on the entity only (the key and its rule)"),
    ("entities/*", "a keyProperty on every entity", "no keyProperty when the table has no single-column key (OrderItems: a composite key; AuditLog: none, rule K3)"),
    ("all TMDL parts", "CRLF line ends", "LF line ends"),
    ("coverage", "a second namespace with a namespaced entity (mynamespace#...), a rule, measures, timeSeries properties",
     "the default namespace only; none of the others"),
]


def windfarm() -> dict[str, str]:
    return {p["path"]: (FIXTURE / "parts" / p["path"]).read_bytes().decode("utf-8").replace("\r\n", "\n") for p in MANIFEST["parts"]}


@pytest.fixture(scope="module")
def ours() -> dict[str, str]:
    return ontology.ontology_parts(plan(seed.schema("shop"), None, None), "shop_ontology", **ARGS)


@pytest.fixture(scope="module")
def both(ours):
    return {"windfarm": windfarm(), "ours": ours}


# ------------------------------------------------------------------ a small TMDL reader: lines by tab depth ---------

def tree(text: str) -> list[dict]:
    root: dict = {"line": "", "children": []}
    stack = [(-1, root)]
    for raw in text.split("\n"):
        bare = raw.lstrip("\t")
        if not bare.strip() or bare.startswith("///"):
            continue
        depth = len(raw) - len(bare)
        node = {"line": bare.rstrip(), "children": []}
        while stack[-1][0] >= depth:
            stack.pop()
        stack[-1][1]["children"].append(node)
        stack.append((depth, node))
    return root["children"]


def decl(node: dict) -> tuple[str, str]:
    word, _, rest = node["line"].partition(" ")
    return word, rest.split(" = ")[0].removesuffix(" =").strip().strip("'")


def props(node: dict) -> dict[str, str]:
    return {k: v for k, _, v in (c["line"].partition(": ") for c in node["children"]) if v}


def objects(parts: dict[str, str], prefix: str, keyword: str) -> dict[str, dict]:
    out = {}
    for path, text in parts.items():
        if path.startswith(prefix):
            for node in tree(text):
                if decl(node)[0] == keyword:
                    out[decl(node)[1]] = node
    return out


def child(node: dict, keyword: str) -> list[dict]:
    return [c for c in node["children"] if decl(c)[0] == keyword]


# ------------------------------------------------------------------ the fixture itself ------------------------------

def test_the_fixture_is_the_35_parts_of_the_sample_unmodified():
    assert MANIFEST["source"]["commit"] == "7257a94355dd63ba4f1ba43fc5ae5dfcd1a7203d" and len(MANIFEST["parts"]) == 35
    on_disk = sorted(str(p.relative_to(FIXTURE / "parts")) for p in (FIXTURE / "parts").rglob("*") if p.is_file())
    assert on_disk == sorted(p["path"] for p in MANIFEST["parts"])
    for p in MANIFEST["parts"]:
        assert p["payloadType"] == "InlineBase64"
        assert hashlib.sha256((FIXTURE / "parts" / p["path"]).read_bytes()).hexdigest() == p["sha256"], p["path"]
    assert (FIXTURE / "LICENSE-microsoft-mcp.txt").read_text().startswith("MIT License")


def test_both_definitions_pass_the_part_checks_and_fabrics_limits(both):
    for name, parts in both.items():
        env = ontology.envelope(name, parts)
        assert limits.part_problems(env["definition"]["parts"]) == [], name
        assert limits.ontology_problems(parts) == [], name
        limits.check_definition(env["definition"], "Ontology")


# ------------------------------------------------------------------ the same skeleton and shapes --------------------

def _kind(path: str) -> str:
    return path.split("/")[0] + "/" if "/" in path else path


def test_the_same_skeleton(both):
    required = {".platform", "database.tmdl", "model.tmdl", "namespaces/default.tmdl"}
    assert required <= set(both["windfarm"]) and required <= set(both["ours"])
    assert {_kind(p) for p in both["ours"]} <= {_kind(p) for p in both["windfarm"]}      # we write no kind of part the sample lacks
    platforms = [json.loads(parts[".platform"]) for parts in both.values()]
    assert [sorted(p) for p in platforms] == [["$schema", "config", "metadata"]] * 2
    assert all(p["metadata"]["type"] == "Ontology" and p["config"] == {"version": "2.0", "logicalId": "0" * 8 + "-0000-0000-0000-" + "0" * 12}
               for p in platforms)
    assert platforms[0]["$schema"] == platforms[1]["$schema"] == ontology.PLATFORM_SCHEMA


@pytest.mark.parametrize("side", ["windfarm", "ours"])
def test_model_refs_name_exactly_the_parts(both, side):
    parts = both[side]
    refs: dict[str, set] = {}
    for node in tree(parts["model.tmdl"]):
        word, rest = node["line"].partition(" ")[::2]
        if word == "ref":
            kind, _, name = rest.partition(" ")
            refs.setdefault(kind, set()).add(name.strip("'"))
    assert refs["table"] == set(objects(parts, "tables/", "table"))
    assert refs["entity"] == set(objects(parts, "entities/", "entity"))
    assert refs["namespace"] == set(objects(parts, "namespaces/", "namespace")) and "default" in refs["namespace"]
    assert refs.get("rule", set()) == set(objects(parts, "rules/", "rule"))
    for path, node in ((p, tree(t)[0]) for p, t in parts.items() if p.startswith(("tables/", "rules/", "namespaces/"))):
        assert path.split("/", 1)[1] == decl(node)[1] + ".tmdl"                       # each file is named after its object


@pytest.mark.parametrize("side", ["windfarm", "ours"])
def test_tables_have_columns_and_one_direct_lake_partition_on_a_declared_expression(both, side):
    parts = both[side]
    expressions = set(objects(parts, "expressions.tmdl", "expression"))
    assert len(expressions) == 1
    for name, table in objects(parts, "tables/", "table").items():
        assert "lineageTag" in props(table)
        for column in child(table, "column"):
            assert {"dataType", "lineageTag", "sourceColumn"} <= set(props(column)), (name, column["line"])
        (partition,) = child(table, "partition")
        assert partition["line"].endswith(" = entity") and props(partition)["mode"] == "directLake"
        (source,) = [c for c in partition["children"] if c["line"] == "source"]
        assert set(props(source)) == {"entityName", "schemaName", "expressionSource"}
        assert props(source)["expressionSource"].strip("'") in expressions


@pytest.mark.parametrize("side", ["windfarm", "ours"])
def test_entities_are_backed_by_a_table_with_a_key_and_bound_properties(both, side):
    parts = both[side]
    tables = {name: {decl(c)[1] for c in child(t, "column")} for name, t in objects(parts, "tables/", "table").items()}
    for name, entity in objects(parts, "entities/", "entity").items():
        p = props(entity)
        assert p["backingTable"] in tables and "lineageTag" in p
        properties = {decl(c)[1]: c for c in child(entity, "property")}
        assert p.get("keyProperty") in properties or (side == "ours" and name in ("OrderItems", "AuditLog")), name   # DIFFERENCES
        for prop, node in properties.items():
            assert {"dataType", "lineageTag"} <= set(props(node))
            (binding,) = [c for c in node["children"] if c["line"] == "backingConfiguration"]
            table, _, column = props(binding)["valueColumn"].partition(".")
            assert column in tables[table], (name, prop)


@pytest.mark.parametrize("side", ["windfarm", "ours"])
def test_relationships_join_existing_columns_and_entity_relationships_name_them(both, side):
    parts = both[side]
    tables = {name: {decl(c)[1] for c in child(t, "column")} for name, t in objects(parts, "tables/", "table").items()}
    entities = set(objects(parts, "entities/", "entity"))
    relationships = objects(parts, "relationships.tmdl", "relationship")
    assert relationships
    for rel in relationships.values():
        for end in ("fromColumn", "toColumn"):
            table, _, column = props(rel)[end].partition(".")
            assert column in tables[table]
    for erel in objects(parts, "entityRelationships.tmdl", "entityRelationship").values():
        p = props(erel)
        assert {p["fromEntity"], p["toEntity"]} <= entities and "lineageTag" in p
        (binding,) = [c for c in erel["children"] if c["line"] == "backingConfiguration"]
        assert props(binding)["relationship"] in relationships


# ------------------------------------------------------------------ the differences, written down -------------------

def test_the_differences_are_the_ones_written_down(both):
    """Each line of DIFFERENCES, checked on both sides: when either side changes, this fails and the list is revisited."""
    wf, us = both["windfarm"], both["ours"]
    raw = {p["path"]: (FIXTURE / "parts" / p["path"]).read_bytes() for p in MANIFEST["parts"]}
    assert len(DIFFERENCES) == 10
    # database.tmdl and model.tmdl
    assert [n["line"] for n in tree(wf["database.tmdl"])] == ["database"] and wf["database.tmdl"].startswith("///")
    assert [n["line"] for n in tree(us["database.tmdl"])] == ["database shop_ontology"]
    assert tree(wf["model.tmdl"])[0]["line"] == "model Model" and tree(us["model.tmdl"])[0]["line"] == "model shop_ontology"
    # the expression
    assert "Sql.Database(" in wf["expressions.tmdl"] and "expression DatabaseQuery =" in wf["expressions.tmdl"]
    assert "AzureStorage.DataLake(\"https://onelake.dfs.fabric.microsoft.com/" in us["expressions.tmdl"]
    assert "Sql.Database" not in us["expressions.tmdl"] and "AzureStorage" not in wf["expressions.tmdl"]
    # tables: annotations and formatString
    tables_wf = [t for p, t in wf.items() if p.startswith("tables/")]
    tables_us = [t for p, t in us.items() if p.startswith("tables/")]
    assert not any("annotation " in t for t in tables_wf) and all("annotation ONT_ItemId = lh-1" in t for t in tables_us)
    assert any("formatString:" in t for t in tables_wf) and not any("formatString:" in t for t in tables_us)
    # entity relationships
    assert "label:" not in wf["entityRelationships.tmdl"] and "entityRelationship 'Blade On Turbine'" in wf["entityRelationships.tmdl"]
    assert all(child(n, "label") or "label" in props(n) for n in tree(us["entityRelationships.tmdl"]))
    # descriptions on properties
    assert "\t/// " in wf["entities/wind_turbines.tmdl"]
    assert not any("\t/// " in t for p, t in us.items() if p.startswith("entities/"))
    # keys
    assert all("keyProperty" in props(n) for n in objects(wf, "entities/", "entity").values())
    assert [e for e, n in objects(us, "entities/", "entity").items() if "keyProperty" not in props(n)] == ["OrderItems", "AuditLog"]
    # line ends
    assert all(b"\r\n" in b for p, b in raw.items() if p.endswith(".tmdl"))
    assert not any("\r" in t for t in us.values())
    # coverage
    assert "namespaces/mynamespace.tmdl" in wf and "entities/mynamespace#wind_turbines2.tmdl" in wf and "rules/SpeedLimit.tmdl" in wf
    assert any("type: timeSeries" in t for t in wf.values()) and any("\tmeasure " in t for t in wf.values())
    assert [p for p in us if p.startswith("namespaces/")] == ["namespaces/default.tmdl"]
    assert not any(p.startswith("rules/") or "#" in p for p in us)
    assert not any("timeSeries" in t or "\tmeasure " in t for t in us.values())


def test_the_payloads_round_trip_through_base64_as_in_the_sample():
    for p in MANIFEST["parts"]:
        data = (FIXTURE / "parts" / p["path"]).read_bytes()
        assert base64.b64decode(base64.b64encode(data), validate=True) == data
