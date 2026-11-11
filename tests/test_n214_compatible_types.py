"""Round n214: the workload's detail page in Fabric listed "Compatible with: Lakehouse, Unknown, Warehouse, Unknown".

n201 put the REST API's ItemType names MirroredDatabase and SQLDatabase into Product.json compatibleItemTypes; Fabric
(Org.Krusgraph 1.0.1023, 11 November 2026) showed both as "Unknown". Learn shows compatibleItemTypes only by example
("Lakehouse"; "Lakehouse", "Dataset", "Dataflow" in the extensibility toolkit's how-to-add-jobs-to-be-done, ms.date 15
December 2025, read 11 November 2026) and documents no identifier for a mirrored database or a SQL database in that field,
so both are left out. Every compatible type is pinned to the documented names, in both packages, and both packages
still validate against the kit's XSDs.
"""
import importlib.util
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "workload" / "Workload" / "Manifest"
APP_ID = "853a0cf0-7d35-42b7-b384-26178755a72a"
DOCUMENTED = {"Lakehouse", "Warehouse", "Dataset", "Dataflow"}     # Learn's examples, plus Warehouse (shown by name)


def _builder():
    spec = importlib.util.spec_from_file_location("build_package_n214", ROOT / "workload/scripts/build_package.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _builder()


def _package(name, tmp_path, manifest=MANIFEST):
    pkg = B.build(APP_ID, "1.0.2", out_dir=tmp_path / name, manifest=manifest, name=name)
    with zipfile.ZipFile(pkg) as z:
        return {n: z.read(n) for n in z.namelist()}


def test_the_documented_list_is_the_one_the_builder_checks():
    assert set(B.DOCUMENTED_COMPATIBLE) == DOCUMENTED
    assert B.COMPATIBLE == ("Lakehouse", "Warehouse")


@pytest.mark.parametrize("name", B.NAMES)
def test_every_compatible_type_is_a_documented_name(tmp_path, name):
    product = json.loads(_package(name, tmp_path)["FE/Product.json"])
    types = product["compatibleItemTypes"]
    assert types == list(B.COMPATIBLE)
    assert set(types) <= DOCUMENTED
    assert "MirroredDatabase" not in types and "SQLDatabase" not in types


@pytest.mark.parametrize("bad", ["MirroredDatabase", "SQLDatabase", "SqlDatabase", "Lakehouse"])
def test_an_undocumented_or_repeated_type_is_refused(tmp_path, bad):
    manifest = tmp_path / "Manifest"
    shutil.copytree(MANIFEST, manifest)
    product = json.loads((manifest / "Product.json").read_text(encoding="utf-8"))
    product["compatibleItemTypes"].append(bad)
    (manifest / "Product.json").write_text(json.dumps(product, indent=4), encoding="utf-8")
    with pytest.raises(B.PackageError, match="compatibleItemTypes"):
        _package("Org.Krusgraph", tmp_path, manifest)


@pytest.mark.skipif(not shutil.which("xmllint"), reason="xmllint not installed")
@pytest.mark.parametrize("name", B.NAMES)
def test_both_packages_validate_against_the_xsds(tmp_path, name):
    files = _package(name, tmp_path)
    # As in test_workload_manifest.py: the kit's version pattern uses "(?:", which libxml2's XSD regexes do not accept;
    # an XSD group never captures, so "(" matches the same strings.
    xsds = tmp_path / "xsd"
    xsds.mkdir()
    for x in MANIFEST.glob("*.xsd"):
        (xsds / x.name).write_text(x.read_text(encoding="utf-8").replace("(?:", "("), encoding="utf-8")
    for path, xsd in (("BE/WorkloadManifest.xml", "WorkloadDefinition.xsd"), ("BE/ModelItem.xml", "ItemDefinition.xsd")):
        out = tmp_path / Path(path).name
        out.write_bytes(files[path])
        check = subprocess.run(["xmllint", "--noout", "--schema", str(xsds / xsd), str(out)], capture_output=True, text=True)
        assert check.returncode == 0, f"{name} {path}: {check.stderr}"


def test_the_film_stays_first():
    product = json.loads((MANIFEST / "Product.json").read_text(encoding="utf-8"))
    assert product["productDetail"]["slideMedia"][0]["mediaType"] == 1
