"""Round n184: Microsoft's Fabric item icons on the Krusgraph Model editor's output cards.

The icons come only from the npm package @fabric-msft/svg-icons at the pinned version, which Microsoft Learn's
"Microsoft Fabric product, experience, and item icons" offers for Fabric platform extension development; webpack copies
them unchanged and no icon file lives in the repository. The notices carry the trademark line, and every output's
default name is "<lakehouse>_<suffix>". The rendering and the byte-for-byte hash against the installed package are in
workload/Workload/app/items/ModelItem/fabricIcons.test.ts (`npm test`, the workload job); the hash check here runs
when node_modules is present."""
import hashlib
import json
import re
from pathlib import Path

import pytest

from fabric_backend import workload_api

ROOT = Path(__file__).resolve().parent.parent
WL = ROOT / "workload" / "Workload"
MODEL = WL / "app" / "items" / "ModelItem"
ICONS = json.loads((MODEL / "fabricIcons.json").read_text(encoding="utf-8"))
TRADEMARK = "Microsoft, Microsoft Fabric and Power BI are trademarks of the Microsoft group of companies."
TERMS = "https://learn.microsoft.com/fabric/fundamentals/icons"


def test_every_output_has_an_icon_with_the_item_type_as_text():
    assert set(ICONS["kinds"]) == set(workload_api.KINDS)
    for kind, icon in ICONS["kinds"].items():
        assert icon["alt"].strip(), kind
        assert icon["file"] in ICONS["files"], kind
        assert re.fullmatch(r"[a-z_]+_24_item\.svg", icon["file"]), kind
    assert ICONS["kinds"]["silver_notebook"]["alt"] == "Notebook"
    assert ICONS["kinds"]["semantic_model"]["alt"] == "Semantic model"
    assert ICONS["kinds"]["graphql"]["alt"] == "API for GraphQL"
    assert set(ICONS["files"]) == {i["file"] for i in ICONS["kinds"].values()}


def test_icons_come_only_from_the_cited_package_at_the_pinned_version():
    assert ICONS["package"] == "@fabric-msft/svg-icons"
    assert ICONS["sourceDir"] == "node_modules/@fabric-msft/svg-icons/svg"
    assert ICONS["terms"] == TERMS
    pkg = json.loads((WL / "package.json").read_text(encoding="utf-8"))
    assert pkg["dependencies"]["@fabric-msft/svg-icons"] == ICONS["version"]          # exact, no ^ or ~
    lock = json.loads((WL / "package-lock.json").read_text(encoding="utf-8"))
    entry = lock["packages"]["node_modules/@fabric-msft/svg-icons"]
    assert entry["version"] == ICONS["version"]
    assert entry["integrity"] == ICONS["integrity"]
    assert entry["resolved"].startswith("https://registry.npmjs.org/@fabric-msft/svg-icons/")
    # webpack copies them from the package, nowhere else
    web = (WL / "webpack.config.js").read_text(encoding="utf-8")
    assert 'require("./app/items/ModelItem/fabricIcons.json")' in web
    assert "from: `./${FABRIC_ICONS.sourceDir}/${file}`" in web
    # the editor points at the served copies only, through fabricIcons.ts
    ts = (MODEL / "fabricIcons.ts").read_text(encoding="utf-8")
    assert "`${ICONS.servedAt}/${k.file}`" in ts
    views = (MODEL / "ModelItemViews.tsx").read_text(encoding="utf-8")
    assert "fabric-icons" not in views and "svg-icons" not in views
    assert re.search(r'<img className="krusgraph-item-icon" src=\{icon\.src\} alt=\{icon\.alt\} width=\{ICON_SIZE\} height=\{ICON_SIZE\}', views)


def test_no_icon_file_is_stored_or_modified_in_the_repository():
    hashes = set(ICONS["files"].values())
    for path in (ROOT / "workload").rglob("*.svg"):
        if "node_modules" in path.parts:
            continue
        assert path.name not in ICONS["files"], path
        assert hashlib.sha256(path.read_bytes()).hexdigest() not in hashes, path


def test_installed_icons_match_the_source_hashes():
    src = WL / ICONS["sourceDir"]
    if not src.is_dir():
        pytest.skip("workload/Workload/node_modules is not installed (the workload job checks it with npm test)")
    meta = json.loads((src.parent / "package.json").read_text(encoding="utf-8"))
    assert meta["version"] == ICONS["version"]
    for name, sha in ICONS["files"].items():
        assert hashlib.sha256((src / name).read_bytes()).hexdigest() == sha, name


def test_notices_carry_the_terms_and_the_trademark_line():
    ts = (MODEL / "fabricIcons.ts").read_text(encoding="utf-8")
    assert f'"{TRADEMARK}"' in ts
    assert "NOTICES" in ts and "<AboutNotices />" in (MODEL / "ModelItemViews.tsx").read_text(encoding="utf-8")
    for doc in (ROOT / "THIRD_PARTY_NOTICES.md", ROOT / "docs" / "WORKLOAD-DEV.md", ROOT / "tools" / "third_party_notices.py"):
        text = doc.read_text(encoding="utf-8")
        assert TRADEMARK in text, doc
        assert TERMS in text, doc
        assert "@fabric-msft/svg-icons" in text, doc


def test_default_names_follow_one_pattern_from_the_lakehouse():
    expected = {"silver_notebook": "silver", "gold_views": "gold", "pipeline": "pipeline", "semantic_model": "model",
                "report": "report", "graphql": "api", "ontology": "ontology", "data_agent": "agent", "rayfin_app": "app"}
    assert {k: v["suffix"] for k, v in workload_api.KINDS.items()} == expected
    words = (MODEL / "buildWords.ts").read_text(encoding="utf-8")
    for kind, suffix in expected.items():
        assert re.search(rf'kind: "{kind}",[^\n]*suffix: "{suffix}"', words), kind
    assert "return `${base}_${kindInfo(kind)?.suffix ?? kind}`" in words
