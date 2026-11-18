"""Round WB11: Microsoft's Fabric item icons beside every Fabric item type the Model editor names.

Gustav, 18 Nov 2026: "kan vi lägga in fler Microsoft-loggor för de items man kan välja att skapa?" n184 put the icons on
the output cards; WB11 uses the same package, at the same pinned version, for the next steps' cards, the data product's
Built list, Retire, the catalog's "What would be written as you" and the source. The rendering is checked in
workload/Workload/app/items/ModelItem/wb11Icons.test.tsx (`npm test`) and the browser in workload/scripts/e2e/run.js
(flows 8 and 22). This file checks the data without node: each type maps to an item icon of the package (or the
documented fallback), no product or Microsoft logo is used, the engine's catalog rows carry the item type, the notices
and the docs say where the icons come from."""
import json
import re
from pathlib import Path

from fabric_backend.catalog_publish import writes

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "workload" / "Workload" / "app" / "items" / "ModelItem"
ICONS = json.loads((MODEL / "fabricIcons.json").read_text(encoding="utf-8"))

# every Fabric item type the editor names: what Create makes, the source kinds, the next steps' Experiment and Activator
NAMED = {"Notebook", "DataPipeline", "SemanticModel", "Report", "GraphQLApi", "Ontology", "DataAgent", "AppBackend",
         "Lakehouse", "Warehouse", "SQLDatabase", "MirroredDatabase", "MLExperiment", "Reflex"}


def test_every_named_type_has_an_item_icon_or_the_documented_fallback():
    assert set(ICONS["types"]) == NAMED
    for t, icon in ICONS["types"].items():
        assert re.fullmatch(r"[a-z_]+_24_item\.svg", icon["file"]), t
        assert icon["file"] in ICONS["files"], t
        assert icon["alt"].strip(), t
    fallback = {t for t, i in ICONS["types"].items() if i["file"] == ICONS["fallback"]["file"]}
    assert fallback == {"GraphQLApi", "Reflex"}
    assert ICONS["fallback"]["file"] == "generic_placeholder_24_item.svg"
    assert "API for GraphQL" in ICONS["fallback"]["why"] and "Activator" in ICONS["fallback"]["why"]


def test_no_product_experience_or_microsoft_logo():
    for f in ICONS["files"]:
        assert f.endswith("_24_item.svg"), f
        assert not re.search(r"power_bi|^fabric_24|microsoft|_color\.svg|_filled\.svg|_regular\.svg", f), f


def test_the_types_words_match_the_editors_words():
    src = (MODEL / "createWords.ts").read_text(encoding="utf-8")
    labels = dict(re.findall(r"^\s+(\w+): \"([^\"]+)\",$", src.split("export const TYPE_LABEL")[1].split("};")[0], re.M))
    assert labels and all(ICONS["types"][t]["alt"] == w for t, w in labels.items())
    source = (MODEL / "sourceWords.ts").read_text(encoding="utf-8")
    for t in ("Lakehouse", "Warehouse", "SQLDatabase", "MirroredDatabase"):
        assert f'{t}: "{ICONS["types"][t]["alt"]}"' in source, t


def test_catalog_rows_carry_the_item_type():
    item = {"id": "i1", "displayName": "demo_lh", "type": "Lakehouse", "description": "", "tags": []}
    w, kept, _ = writes.item_writes("ws", item, ["Data product Shop"], [], [], {"i1"})
    rows = writes.diff(w, kept, [writes.offer({**item, "id": "i2", "type": "Warehouse", "displayName": "wh"}, w)])
    assert [r["type"] for r in rows] == ["Lakehouse", "Warehouse"]


def test_notices_and_docs_name_the_source_and_its_terms():
    ts = (MODEL / "fabricIcons.ts").read_text(encoding="utf-8")
    assert "beside the names of Fabric item types" in ts and "not made or endorsed by Microsoft" in ts
    doc = (ROOT / "docs" / "WORKLOAD-DEV.md").read_text(encoding="utf-8")
    section = doc.split("Round WB11")[1]
    for words in ("@fabric-msft/svg-icons", "12.0.0", "https://learn.microsoft.com/fabric/fundamentals/icons", "generic_placeholder_24_item.svg"):
        assert words in section, words
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "@fabric-msft/svg-icons" in notices
