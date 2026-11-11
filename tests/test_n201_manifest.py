"""Round n201: the workload's detail page in Fabric said "Compatible with: Lakehouse" only and showed one image.

Both packages (Org.Krusgraph and Krusgraph.Modeler, built from the one Product.json template by
workload/scripts/build_package.py) now list the mirrored database, the warehouse and the SQL database as compatible item
types (the REST API's ItemType names; Learn shows the field with such names and lists no accepted values), say so in the
detail page's text, show the founder's overview film first (mediaType 1, a YouTube embed URL, as Learn's
frontend-manifests page documents) with the image after it, and point the "Certification" support link at the attestation
page, which says "Draft." at the top (Learn documents no label for a support link). A new package is needed: the
founder builds it and uploads it in Fabric.
"""
import importlib.util
import json
import shutil
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "workload" / "Workload" / "Manifest"
APP_ID = "853a0cf0-7d35-42b7-b384-26178755a72a"
FILM = "https://www.youtube.com/embed/69oikujqZDI"


def _builder():
    spec = importlib.util.spec_from_file_location("build_package_n201", ROOT / "workload/scripts/build_package.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _builder()


def _package(name: str, tmp_path: Path, manifest: Path = MANIFEST) -> dict[str, bytes]:
    pkg = B.build(APP_ID, "1.0.2", out_dir=tmp_path / name, manifest=manifest, name=name)
    with zipfile.ZipFile(pkg) as z:
        return {n: z.read(n) for n in z.namelist()}


@pytest.mark.parametrize("name", ["Org.Krusgraph", "Krusgraph.Modeler"])
def test_both_packages_list_mirrored_databases_warehouses_and_sql_databases_as_compatible(tmp_path, name):
    files = _package(name, tmp_path)
    product = json.loads(files["FE/Product.json"])
    assert product["compatibleItemTypes"] == ["Lakehouse", "MirroredDatabase", "Warehouse", "SQLDatabase"]
    assert tuple(product["compatibleItemTypes"]) == B.COMPATIBLE
    words = json.loads(files["FE/assets/locales/en-US/translations.json"])
    detail = words[product["productDetail"]["description"]]
    assert "mirrored database" in detail and "SAP mirrored through SAP Datasphere" in detail
    assert "Works with data mirrored into Fabric." in detail
    assert "mirrored database" in words[product["description"]]


@pytest.mark.parametrize("name", ["Org.Krusgraph", "Krusgraph.Modeler"])
def test_the_film_comes_first_and_the_image_after_it(tmp_path, name):
    product = json.loads(_package(name, tmp_path)["FE/Product.json"])
    slides = product["productDetail"]["slideMedia"]
    assert slides[0] == {"mediaType": 1, "source": FILM}
    assert slides[1] == {"mediaType": 0, "source": "assets/images/Workload_Hub_SlideMedia_1.png"}
    assert len(slides) <= B.MAX_SLIDES


@pytest.mark.parametrize("name", ["Org.Krusgraph", "Krusgraph.Modeler"])
def test_the_certification_link_opens_the_attestation_page_that_says_draft(tmp_path, name):
    from fabric_backend.pages import ATTESTATION_DRAFT_MARKER, ATTESTATION_PATH, attestation_md
    product = json.loads(_package(name, tmp_path)["FE/Product.json"])
    link = product["productDetail"]["supportLink"]["certification"]
    assert set(link) == {"url"}                                   # no label field is documented, so none is sent
    assert link["url"] == "https://krusgraph.com" + ATTESTATION_PATH
    first = [line for line in attestation_md().splitlines() if line.strip()][:2]
    assert first[1].startswith(ATTESTATION_DRAFT_MARKER)          # "Draft." right under the title


@pytest.mark.parametrize("slide, message", [
    ({"mediaType": 1, "source": "https://youtu.be/69oikujqZDI"}, "not a YouTube embed"),
    ({"mediaType": 1, "source": "https://www.vimeo.com/video/1"}, "not a YouTube embed"),
    ({"mediaType": 0, "source": "assets/images/Nope.png"}, "names no image"),
    ({"mediaType": 2, "source": "assets/images/Workload_Hub_SlideMedia_1.png"}, "mediaType"),
])
def test_a_slide_fabric_would_not_show_is_refused(tmp_path, slide, message):
    manifest = tmp_path / "Manifest"
    shutil.copytree(MANIFEST, manifest)
    product = json.loads((manifest / "Product.json").read_text(encoding="utf-8"))
    product["productDetail"]["slideMedia"].insert(0, slide)
    (manifest / "Product.json").write_text(json.dumps(product, indent=4), encoding="utf-8")
    with pytest.raises(B.PackageError, match=message):
        _package("Org.Krusgraph", tmp_path, manifest)


def test_the_documented_video_forms_pass():
    for url in (FILM, "https://youtube.com/embed/UNgpBOCvwa8?si=KwsR879MaVZd5CJi", "https://player.vimeo.com/video/123"):
        assert B.SLIDE_VIDEO.match(url), url


def test_no_claim_of_certification_partnership_or_endorsement_in_the_detail_page():
    words = json.loads((MANIFEST / "assets/locales/en-US/translations.json").read_text(encoding="utf-8"))
    text = " ".join(words.values()).lower()
    for w in ("certified", "certification", "partner", "endorse", "approved by sap", "approved by microsoft"):
        assert w not in text, w
