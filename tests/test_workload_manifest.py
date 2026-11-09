"""Round n175: the workload's own page and icons in Fabric (workload/Workload/Manifest), for the meeting with Microsoft.

The starter kit's purple images and sample texts are replaced by Krusgraph's (workload/scripts/build_manifest_images.py
draws the images). Checked here: every image Product.json and the item manifest name exists with the size the script
gives it, Fabric's asset rules (manifest-product on Microsoft Learn, read 9 November 2026: at most 15 files in assets,
.png/.jpg/.jpeg only, at most 1.5 MB each, each referenced, Product.json at most 50 KB), no starter-kit placeholder
text, the description of every n174 output, the links, the publisher, the network hosts for IT, and the built package's
XML against the XSDs in the repository (xmllint)."""
import importlib.util
import json
import re
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "workload" / "Workload" / "Manifest"
ASSETS = MANIFEST / "assets"
WL_ID = "11111111-2222-3333-4444-555555555555"


def _script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "workload" / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


IMAGES = _script("build_manifest_images")
PRODUCT = json.loads((MANIFEST / "Product.json").read_text(encoding="utf-8"))
ITEM = json.loads((MANIFEST / "items" / "ModelItem" / "ModelItem.json").read_text(encoding="utf-8"))
WORDS = json.loads((ASSETS / "locales" / "en-US" / "translations.json").read_text(encoding="utf-8"))


def _png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    return struct.unpack(">II", head[16:24])


def _referenced() -> set[str]:
    found = set()

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str) and x.startswith("assets/"):
            found.add(x)
    walk(PRODUCT)
    walk(ITEM)
    return found


# ------------------------------------------------------------------ the images ---------------------------------------

def test_every_referenced_image_exists_with_the_size_the_script_draws():
    refs = _referenced()
    assert refs, "Product.json names no image"
    for ref in refs:
        path = MANIFEST / ref
        assert path.exists(), f"{ref} is referenced but missing (Fabric refuses the upload)"
        w, h, _ = IMAGES.SIZES[path.name]
        assert _png_size(path) == (w, h), f"{path.name}: {_png_size(path)} is not {w}x{h}"
    assert {Path(r).name for r in refs} == set(IMAGES.SIZES)               # every image the script draws is used


APPROVED_ICON = {16, 20, 24, 32, 40, 48, 64}     # the validator's ImageValidator default (tools/hub_readiness.py, n178)


def test_icons_have_a_size_microsoft_s_validator_approves():
    card = PRODUCT["createExperience"]["cards"][0]
    for ref in (PRODUCT["icon"]["name"], PRODUCT["favicon"], card["icon"]["name"], card["icon_small"]["name"],
                ITEM["icon"]["name"], ITEM["activeIcon"]["name"]):
        w, h = _png_size(MANIFEST / ref)
        assert w == h and w in APPROVED_ICON, f"{ref}: {w}x{h}"
    assert _png_size(MANIFEST / PRODUCT["productDetail"]["image"]["source"]) == (1920, 240)


def test_fabric_s_asset_rules_hold():
    files = [p for p in ASSETS.rglob("*") if p.is_file()]
    assert len(files) <= 15
    images = [p for p in files if p.parent.name == "images"]
    assert all(p.suffix.lower() in (".png", ".jpg", ".jpeg") for p in images)
    assert all(p.stat().st_size <= 1.5 * 1024 * 1024 for p in files)
    assert {f"assets/images/{p.name}" for p in images} <= _referenced(), "an image no manifest references fails the upload"
    assert (MANIFEST / "Product.json").stat().st_size <= 50 * 1024


def test_the_workload_and_the_item_use_the_krusgraph_icons():
    assert PRODUCT["icon"]["name"] == "assets/images/Workload_Icon.png"
    assert PRODUCT["favicon"] == "assets/images/Workload_Favicon.png"
    card = PRODUCT["createExperience"]["cards"][0]
    assert card["icon"]["name"] == ITEM["icon"]["name"] == "assets/images/ModelItem_Icon.png"
    assert ITEM["activeIcon"]["name"] == "assets/images/ModelItem_Icon_Active.png"           # distinct (validator 1.2.1)
    assert card["icon_small"]["name"] == "assets/images/ModelItem_Icon_Small.png"
    assert PRODUCT["productDetail"]["image"]["source"] == "assets/images/Workload_Hub_Banner.png"
    assert [s["source"] for s in PRODUCT["productDetail"]["slideMedia"]] == ["assets/images/Workload_Hub_SlideMedia_1.png"]


def test_the_editor_loads_with_the_krusgraph_mark_not_the_fabric_logo():
    app = ROOT / "workload" / "Workload" / "app"
    assert IMAGES.EDITOR_ICON.read_bytes() == (MANIFEST / "assets/images/Workload_Icon.png").read_bytes()
    assert not (app / "assets" / "fabric-icon.png").exists()
    assert "'/assets/krusgraph-icon.png'" in (app / "components/ItemEditor/ItemEditorLoadingView.tsx").read_text(encoding="utf-8")


def _rgb(path: Path, x: int, y: int) -> tuple[int, int, int, int]:
    pytest.importorskip("PIL")
    from PIL import Image
    return Image.open(path).convert("RGBA").getpixel((x, y))


def test_the_icons_are_the_logo_mark_not_the_starter_kit_s_purple():
    """The mark's three dots at their places: coral on top, green left, violet right (favicon.svg's colours)."""
    pytest.importorskip("PIL")
    near = lambda a, b: all(abs(x - y) <= 12 for x, y in zip(a[:3], b))   # noqa: E731
    coral, green, violet = (0xF2, 0x73, 0x5C), (0x9D, 0xB8, 0xA0), (0xA9, 0x9A, 0xD8)
    w = MANIFEST / "assets/images/Workload_Icon.png"
    assert near(_rgb(w, 32, 16), coral) and near(_rgb(w, 16, 46), green) and near(_rgb(w, 48, 46), violet)
    # n183: the item icon is Fluent-style, the three nodes inside a rounded container (interior 28 px of 48, centred)
    for name, k in (("ModelItem_Icon.png", 1), ("ModelItem_Icon_Active.png", 1), ("ModelItem_Icon_Small.png", .5)):
        i = MANIFEST / "assets/images" / name
        at = lambda x, y: _rgb(i, round(x * k), round(y * k))       # noqa: E731
        soft = lambda a, b: all(abs(x - y) <= 26 for x, y in zip(a[:3], b))   # noqa: E731  (each node is a soft sphere)
        assert soft(at(24, 15), coral) and soft(at(15, 32), green) and soft(at(33, 32), violet), name
        assert _rgb(i, 0, 0)[3] == 0, name                           # the container's rounded corner leaves the ground clear


# ------------------------------------------------------------------ the text -----------------------------------------

def _text() -> str:
    return " ".join(str(v) for v in WORDS.values())


def test_no_starter_kit_placeholder_is_left():
    blob = _text() + json.dumps(PRODUCT) + json.dumps(ITEM)
    for gone in ("Your docs will appear here", "HelloWorld", "Hello World", "Sample", "sample workload", "Lorem",
                 "development build", "come later", "contoso", "aka.ms/fabric-extensibility"):
        assert gone.lower() not in blob.lower(), gone
    for key in re.findall(r'"([A-Za-z]+_[A-Za-z0-9_]+)"', json.dumps(PRODUCT) + json.dumps(ITEM)):
        if not key.startswith(("assets", "item", "workspace", "create")) and "_" in key and key[0].isupper():
            assert key in WORDS, f"{key} has no text in translations.json"


def test_the_page_describes_every_output_the_product_and_the_flow():
    d = WORDS["Workload_Hub_Description"]
    for word in ("API for GraphQL", "silver notebook", "gold views", "pipeline", "semantic model", "report", "ontology",
                 "data agent", "data product", "data flow", "dry run"):
        assert word.lower() in d.lower(), word
    assert "Semantic models, reports and pipelines come later" not in d
    for step in ("+ New item", "Check against the rows", "dry run", "Create"):
        assert step in WORDS["Workload_Hub_GetStarted_1_Description"], step


def test_no_speed_or_compliance_claims():
    blob = _text().lower()
    for claim in ("fast", "seconds", "instant", "gdpr", "iso 27001", "soc 2", "certified", "compliant", "secure", "guarantee"):
        assert claim not in blob, claim


def test_links_publisher_and_no_marketplace_link():
    links = {k: v["url"] for k, v in PRODUCT["productDetail"]["supportLink"].items()}
    assert links["documentation"] == "https://krusgraph.com/docs"
    assert links["help"] == "https://krusgraph.com/support"
    assert links["privacy"] == "https://krusgraph.com/privacy"
    assert links["terms"] == "https://krusgraph.com/terms"
    assert all(u.startswith(("https://krusgraph.com/", "https://github.com/Krusmaster/")) for u in links.values())
    assert "marketplace" not in json.dumps(PRODUCT).lower() and "appsource" not in json.dumps(PRODUCT).lower()
    assert PRODUCT["productDetail"]["publisher"] == "Kruse Consulting AB"
    assert "microsoft" not in json.dumps(PRODUCT).lower()


def test_the_page_tells_it_which_hosts_to_allow():
    d = WORDS["Workload_Hub_Description"]
    assert "workload.krusgraph.com" in d and "krusgraph.com" in d and "443" in d and "TLS 1.2" in d
    assert "keeps loading" in d


# ------------------------------------------------------------------ the IT page, the docs ---------------------------

def test_the_it_page_lists_the_hosts(monkeypatch):
    from starlette.testclient import TestClient
    from fabric_backend import server
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    with TestClient(server.build_app()) as client:
        html = client.get("/it").text
    section = html.split('id="network"')[1].split("<h2")[0]
    for word in ("workload.krusgraph.com", "<code>krusgraph.com</code>", "443", "TLS 1.2", "keeps loading",
                 "ERR_SSL_VERSION_OR_CIPHER_MISMATCH", "allow"):
        assert word in section, word


def test_the_docs_have_the_symptom():
    docs = (ROOT / "fabric_backend" / "page_templates" / "DOCS.md").read_text(encoding="utf-8")
    first = docs.split("### First-time errors")[1].split("\n## ")[0]
    assert "keeps loading" in first and "/it#network" in first and "workload.krusgraph.com" in first
    dev = (ROOT / "docs" / "WORKLOAD-DEV.md").read_text(encoding="utf-8")
    trouble = dev.split("## When something does not work")[1].split("\n## ")[0]
    assert "keeps loading" in trouble and "workload.krusgraph.com" in trouble


# ------------------------------------------------------------------ the package against the XSDs ------------------

@pytest.mark.skipif(not shutil.which("xmllint"), reason="xmllint not installed")
def test_the_package_s_xml_validates_against_the_xsds_and_carries_the_images(tmp_path):
    run = subprocess.run(["bash", str(ROOT / "workload/scripts/build-package"), "--frontend-app-id", WL_ID,
                          "--version", "1.0.9", "--out", str(tmp_path)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    with zipfile.ZipFile(tmp_path / "Org.Krusgraph.1.0.9.nupkg") as z:
        names = set(z.namelist())
        for ref in _referenced():
            assert f"FE/{ref}" in names, ref
        # The kit's CommonTypesDefinitions.xsd writes its version pattern with (?: groups, which .NET accepts and the XSD
        # regex language (libxml2) does not; a group in an XSD pattern never captures, so "(" matches the same strings.
        xsds = tmp_path / "xsd"
        xsds.mkdir()
        for x in MANIFEST.glob("*.xsd"):
            (xsds / x.name).write_text(x.read_text(encoding="utf-8").replace("(?:", "("), encoding="utf-8")
        for name, xsd in (("BE/WorkloadManifest.xml", "WorkloadDefinition.xsd"), ("BE/ModelItem.xml", "ItemDefinition.xsd")):
            out = tmp_path / Path(name).name
            out.write_bytes(z.read(name))
            check = subprocess.run(["xmllint", "--noout", "--schema", str(xsds / xsd), str(out)], capture_output=True, text=True)
            assert check.returncode == 0, check.stderr
