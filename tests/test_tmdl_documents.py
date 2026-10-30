"""Every TMDL document the writer gives holds an object (n67). On 30 October 2026 Power BI Desktop 2.151 opened the shop
project from /check and refused the SAP one: its relationships.tmdl was one comment line, and the TMDL parser stopped with
"InvalidLineType, unexpected line type: Other!, Document: ./relationships, line 1". The rule here: in each generated
document the first line that is neither blank nor a comment starts an object, and no document is comments only. Checked
for the three examples /check offers (the shop, the SAP demo, Salesforce + ERP), in the draft and in the downloaded zip."""
import base64
import io
import json
import re
import shutil
import zipfile

import pytest

from fabric_backend import browser_build as bb, browser_check as bc, semantic_model
from fabric_backend.infer import Relationship, plan
from fabric_backend.schema import Schema

KINDS = ("sample", "sap", "crm")                   # the shop, the SAP demo, Salesforce + ERP, as /check names them
OBJECT = re.compile(r"^(database|model|table|expression|relationship)\b")


def check_document(path: str, text: str) -> None:
    """The first non-blank line that is not a comment (`//`, or a `///` description) starts an object at depth 0; a
    document of comments only, or an empty one, is the bug of 30 October 2026."""
    real = [line for line in text.splitlines() if line.strip() and not line.strip().startswith("//")]
    assert real, f"{path}: no object, only comments or nothing"
    assert OBJECT.match(real[0]), f"{path}: the first line is not an object: {real[0]!r}"
    assert not real[0][0].isspace(), f"{path}: the first object is indented: {real[0]!r}"


def _draft(kind: str) -> dict:
    src, folder = bc._source(kind, None, "")
    try:
        p = plan(src.schema)
        out = semantic_model.draft(p, {"schema": p.schema.schema, "item_kind": "Lakehouse"}, f"{kind}_model")
        out["plan"] = p
        return out
    finally:
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
        if src.close:
            src.close()


@pytest.mark.parametrize("kind", KINDS)
def test_every_generated_tmdl_document_starts_with_an_object(kind):
    out = _draft(kind)
    docs = {p: c for p, c in out["parts"].items() if p.endswith(".tmdl")}
    assert {"definition/database.tmdl", "definition/model.tmdl", "definition/expressions.tmdl"} <= set(docs)
    assert {f"definition/tables/{t.name}.tmdl" for t in out["plan"].schema} <= set(docs)
    for path, text in docs.items():
        check_document(path, text)
        assert semantic_model.has_object(text), path                      # the writer's own rule agrees with the test's
    assert not any("no single-column relationships" in c for c in out["parts"].values())   # the comment that stopped Desktop
    assert all(f"`{p}`" in out["parts"]["README.generated.md"] for p in docs)               # the README lists what exists
    assert "extract the whole zip first" in out["parts"]["README.generated.md"]


def test_relationships_tmdl_is_left_out_when_nothing_is_expressible_and_the_readme_says_why():
    sap = _draft("sap")
    s = sap["summary"]
    assert "definition/relationships.tmdl" not in sap["parts"]
    assert s["relationships_active"] == 0 and s["relationships_inactive"] == 0 and s["relationships_not_expressible"] == 24
    assert len(s["not_expressible"]) == 24 and {len(x["columns"]) > 1 for x in s["not_expressible"]} == {True}
    first = s["not_expressible"][0]
    assert first == {"source": "sap_vbap", "columns": ["MANDT", "VBELN"], "target": "sap_vbak", "target_columns": ["MANDT", "VBELN"],
                     "rule": "SAP pack", "why": first["why"]}
    assert "one column per side" in first["why"] and "Direct Lake allows no calculated column" in first["why"]
    assert "MANDT + '|' + VBELN" in first["why"] and "create_gold_views" in first["why"] and "lakehouse" in first["why"]
    readme = sap["parts"]["README.generated.md"]
    assert "no `definition/relationships.tmdl`" in readme and "InvalidLineType" in readme and "24 relationship(s)" in readme
    assert "`sap_vbap.MANDT+VBELN -> sap_vbak.MANDT+VBELN` (SAP pack) is not in the model" in readme
    assert "or a calculated column" not in readme                            # the old advice: not allowed in Direct Lake
    assert "relationships.tmdl`\n" not in readme.split("## Files", 1)[1]
    # the two examples with single-column keys keep the file, with objects in it
    for kind in ("sample", "crm"):
        out = _draft(kind)
        rels = out["parts"]["definition/relationships.tmdl"]
        assert rels.startswith("relationship ") and out["summary"]["not_expressible"] == []
        assert "| From | To | Rule | Active |" in out["parts"]["README.generated.md"]


def test_the_rule_and_the_reason_for_a_single_column_that_points_at_a_composite_key():
    assert semantic_model.has_object("relationship r\n\tfromColumn: a.b\n\ttoColumn: c.d\n")
    assert semantic_model.has_object("/// the date table\ntable Calendar\n\tdataCategory: Time\n")
    assert semantic_model.has_object("\n\n// a note\n\ndatabase\n\tcompatibilityLevel: 1604\n")
    assert not semantic_model.has_object("// no single-column relationships in the plan\n")
    assert not semantic_model.has_object("") and not semantic_model.has_object("\n\t\n")
    assert not semantic_model.has_object("\tcolumn x\n\t\tdataType: string\n")     # a property block without its object
    # one column on the many side, a composite key on the one side: not unique there, so not expressible either
    from fabric_backend import seed
    p = plan(seed.schema("shop"))
    why = semantic_model.not_expressible_why(p, Relationship("orders", ["order_id"], "order_items", ["order_id"], "R1"))
    assert why.startswith("`order_items`'s key has 2 columns (order_id+line_no), so `order_id` alone is not unique on the one side")
    assert "order_id + '|' + line_no" in why and "create_gold_views" in why
    why = semantic_model.not_expressible_why(p, Relationship("orders", ["customer_id"], "audit_log", ["customer_id"], "confirmed"))
    assert why.startswith("`audit_log` has no key, so `customer_id` is not known to be unique on the one side")
    # a schema whose only relationship has two columns per side: no relationships.tmdl, the plan's link under Decisions to check
    s = Schema.from_information_schema([
        ("dbo", "Heads", "Client", "varchar", 1), ("dbo", "Heads", "DocNo", "varchar", 2), ("dbo", "Heads", "Amount", "decimal", 3),
        ("dbo", "Lines", "Client", "varchar", 1), ("dbo", "Lines", "DocNo", "varchar", 2), ("dbo", "Lines", "ItemNo", "int", 3)])
    out = semantic_model.draft(plan(s, keys={"Heads": ["Client", "DocNo"], "Lines": ["Client", "DocNo", "ItemNo"]},
                                    confirmed=[{"source": "Lines", "source_cols": ["Client", "DocNo"], "target": "Heads", "target_cols": ["Client", "DocNo"]}]),
                               {"schema": "dbo", "item_kind": "Lakehouse"}, "m")
    assert "definition/relationships.tmdl" not in out["parts"] and out["summary"]["relationships_not_expressible"] == 1
    for path, text in out["parts"].items():
        if path.endswith(".tmdl"):
            check_document(path, text)


@pytest.mark.parametrize("kind", KINDS)
def test_the_zip_from_check_holds_the_whole_project_and_only_documents_with_objects(kind):
    r = bb.build(kind)
    n = f"{r['name']}_model"
    z = zipfile.ZipFile(io.BytesIO(base64.b64decode(r["downloads"][f"{n}.zip"])))
    names = set(z.namelist())
    assert {f"{n}.pbip", f"{n}.SemanticModel/definition.pbism", f"{n}.SemanticModel/.platform", f"{n}.SemanticModel/README.generated.md",
            f"{n}.Report/.platform", f"{n}.Report/definition.pbir", f"{n}.Report/report.json", "README.md"} <= names, names
    assert json.loads(z.read(f"{n}.pbip"))["artifacts"] == [{"report": {"path": f"{n}.Report"}}]
    assert json.loads(z.read(f"{n}.SemanticModel/.platform"))["metadata"]["type"] == "SemanticModel"
    assert json.loads(z.read(f"{n}.Report/.platform"))["metadata"]["type"] == "Report"
    docs = {p: z.read(p).decode() for p in names if p.endswith(".tmdl")}
    assert docs and {f"{n}.SemanticModel/definition/database.tmdl", f"{n}.SemanticModel/definition/model.tmdl"} <= set(docs)
    for path, text in docs.items():
        check_document(path, text)
    assert (f"{n}.SemanticModel/definition/relationships.tmdl" in names) == (kind != "sap")
    readme = z.read("README.md").decode()
    assert f"Extract the whole zip first, then open `{n}.pbip`" in readme and "definition.pbism is missing" in readme
    assert "the SAP example stopped with a TMDL format error" in readme
