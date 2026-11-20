"""Round n176 (split out by WP1, 18 November 2026, from tests/test_workload_publish.py): the package names.

The package builds as Krusgraph.Modeler (the default since W12) or Org.Krusgraph and refuses every other Krusgraph.* name; the item type
follows the name and is written once, by the build. These tests need only pytest (no server extras), so
tools/workload_package.py runs them in a clean Azure Cloud Shell; the server tests of n176 stay in test_workload_publish.py."""
import importlib.util
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WL_ID = "99999999-8888-7777-6666-555555555555"


def _builder():
    spec = importlib.util.spec_from_file_location("build_package_n176", ROOT / "workload/scripts/build_package.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ the package names --------------------------------

def _read(pkg: Path) -> dict[str, str]:
    with zipfile.ZipFile(pkg) as z:
        return {n: z.read(n).decode("utf-8", "replace") for n in z.namelist() if n.endswith((".xml", ".json", ".nuspec", ".rels"))}


@pytest.mark.parametrize("args, name", [
    ([], "Krusgraph.Modeler"),                         # W12: the default is the permanent name
    (["--name", "Org.Krusgraph"], "Org.Krusgraph"),
    (["--name", "Krusgraph.Modeler"], "Krusgraph.Modeler"),
])
def test_the_package_takes_its_name_from_the_build(tmp_path, args, name):
    run = subprocess.run(["bash", str(ROOT / "workload/scripts/build-package"), "--frontend-app-id", WL_ID, "--version", "1.0.9",
                          "--out", str(tmp_path), *args], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert f"item type {name}.Model" in run.stdout and "Nothing was uploaded" in run.stdout
    assert ("cannot be undone" in run.stdout) == (name == "Krusgraph.Modeler")
    files = _read(tmp_path / f"{name}.1.0.9.nupkg")
    assert f'WorkloadName="{name}"' in files["BE/WorkloadManifest.xml"]
    assert f'<Item TypeName="{name}.Model"' in files["BE/ModelItem.xml"] and f'WorkloadName="{name}"' in files["BE/ModelItem.xml"]
    assert f"<id>{name}</id>" in files[f"{name}.nuspec"]
    product = json.loads(files["FE/Product.json"])
    assert product["createExperience"]["cards"][0]["itemType"] == "Model"            # Fabric adds the workload part
    other = "Org.Krusgraph" if name == "Krusgraph.Modeler" else "Krusgraph.Modeler"
    for path, text in files.items():
        assert "{{" not in text and other not in text, path


def test_the_name_is_written_once_in_the_sources():
    """The manifests carry the placeholder only; build_package.py is the one place the two names are written."""
    for p in (ROOT / "workload/Workload/Manifest").rglob("*"):
        if p.suffix in (".xml", ".json", ".nuspec"):
            text = p.read_text(encoding="utf-8-sig")
            assert "Org.Krusgraph" not in text and "Krusgraph.Modeler" not in text, p
    item = (ROOT / "workload/Workload/Manifest/items/ModelItem/ModelItem.xml").read_text()
    assert 'TypeName="{{WORKLOAD_NAME}}.Model"' in item
    b = _builder()
    assert b.item_type("Krusgraph.Modeler") == "Krusgraph.Modeler.Model" and b.item_type("Org.Krusgraph") == "Org.Krusgraph.Model"


@pytest.mark.parametrize("name, word", [
    ("Krusgraph.Model", "reserve it in the tenant for good"),
    ("Krusgraph.Modeller", "reserve it in the tenant for good"),
    ("krusgraph.modeler", "reserve it in the tenant for good"),                     # the exact spelling only
    ("Krusgraph.Modeler.Model", "reserve it in the tenant for good"),
    ("Org.Other", "must be Krusgraph.Modeler or Org.Krusgraph"),
    ("", "must be Krusgraph.Modeler or Org.Krusgraph"),
])
def test_every_other_name_is_refused_before_anything_is_written(tmp_path, name, word):
    b = _builder()
    with pytest.raises(b.PackageError, match=word):
        b.build(WL_ID, "1.0.1", out_dir=tmp_path, name=name)
    assert not list(tmp_path.glob("*.nupkg"))
    run = subprocess.run(["bash", str(ROOT / "workload/scripts/build-package"), "--frontend-app-id", WL_ID, "--version", "1.0.1",
                          "--out", str(tmp_path), "--name", name], capture_output=True, text=True)
    assert run.returncode == 1 and "STOP" in run.stderr


def test_a_stray_workload_name_in_a_manifest_file_stops_the_build(tmp_path):
    import shutil
    b = _builder()
    for stray in ("Org.Krusgraph", "Krusgraph.Other"):
        manifest = tmp_path / stray / "Manifest"
        shutil.copytree(ROOT / "workload/Workload/Manifest", manifest)
        item = manifest / "items/ModelItem/ModelItem.json"
        item.write_text(item.read_text().replace('"name": "Model"', f'"name": "Model", "note": "{stray}.Model"'))
        with pytest.raises(b.PackageError, match="names"):
            b.build(WL_ID, "1.0.1", out_dir=tmp_path / "out", manifest=manifest, name="Krusgraph.Modeler")


def test_the_hosted_editor_reads_the_workload_from_the_item():
    """One editor build for both names: the worker and the engine scope follow the item type, not WORKLOAD_NAME alone."""
    app = ROOT / "workload/Workload/app"
    worker = (app / "index.worker.ts").read_text(encoding="utf-8")
    assert "sampleWorkloadName" not in worker and worker.count("workloadOf(createdItem.itemType)") == 3
    assert "rememberWorkloadOf(got.item.type)" in (app / "items/ModelItem/ModelItemEditor.tsx").read_text(encoding="utf-8")
    assert "getWorkloadName()" in (app / "items/ModelItem/engineClient.ts").read_text(encoding="utf-8")
