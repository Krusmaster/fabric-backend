"""Round W12: Krusgraph.Modeler ready to upload on the day Microsoft registers the name.

The package builds as Krusgraph.Modeler by default from one constant (build_package.WORKLOAD_NAME); the offline
validator (workload/scripts/validate_package.py) passes it and catches a broken one; CI builds, validates and keeps it as
an artifact; docs/MODELER-GO-LIVE.md gives the founder's steps without ever going live on an offer."""
from __future__ import annotations

import importlib.util
import re
import shutil
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "workload" / "scripts"
WL_ID = "853a0cf0-7d35-42b7-b384-26178755a72a"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load("build_package")
V = _load("validate_package")


def test_one_constant_names_the_workload_and_it_is_the_default():
    src = (SCRIPTS / "build_package.py").read_text(encoding="utf-8")
    assert B.WORKLOAD_NAME == "Krusgraph.Modeler" and B.PUBLISHED_NAME is B.WORKLOAD_NAME
    assert len(re.findall(r'^\w+ = "Krusgraph\.Modeler"', src, flags=re.M)) == 1
    assert B.NAMES == ("Krusgraph.Modeler", "Org.Krusgraph")
    # no other script and no CI step writes the name out itself; they take it from the constant
    assert "Krusgraph.Modeler" not in (SCRIPTS / "validate_package.py").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    step = ci.split("Build and validate the upload-ready Krusgraph.Modeler package")[1].split("- uses:")[0]
    assert "print(m.WORKLOAD_NAME)" in step and "Krusgraph.Modeler" not in step


@pytest.fixture(scope="module")
def package(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("w12")
    return B.build(WL_ID, "1.0.12", out_dir=out)


def test_the_default_package_is_krusgraph_modeler_and_passes(package):
    assert package.name == "Krusgraph.Modeler.1.0.12.nupkg"
    r = V.validate(package, require_xsd=bool(shutil.which("xmllint")))
    assert r["problems"] == [], r["problems"]
    assert r["name"] == "Krusgraph.Modeler" and r["version"] == "1.0.12" and len(r["sha256"]) == 64
    assert any("1.3.1" in g for g in r["gaps"])                         # the offer link, reported, not refused
    text = V.report(r)
    assert "**PASSED**" in text and "nothing was uploaded" in text and "Not checked here" in text


def test_the_validator_passes_with_the_offer_link(tmp_path):
    pkg = B.build(WL_ID, "1.0.13", out_dir=tmp_path,
                  offer_url="https://marketplace.microsoft.com/product/saas/kruseconsultingab.krusgraph")
    r = V.validate(pkg)
    assert r["problems"] == [] and r["gaps"] == []


def _rewrite(src: Path, dst: Path, change) -> Path:
    with zipfile.ZipFile(src) as z:
        files = {n: z.read(n) for n in z.namelist()}
    files = change(files) or files
    with zipfile.ZipFile(dst, "w") as z:
        for n, b in files.items():
            z.writestr(n, b)
    return dst


@pytest.mark.parametrize("label, change, word", [
    ("version", lambda f: f.update({"BE/WorkloadManifest.xml": f["BE/WorkloadManifest.xml"].replace(b"1.0.12", b"1.0.11")}),
     "Version is not 1.0.12"),
    ("other name", lambda f: f.update({"BE/ModelItem.xml": f["BE/ModelItem.xml"] + b"<!-- Krusgraph.Other -->"}),
     "Krusgraph.Other"),
    ("dev name", lambda f: f.update({"BE/ModelItem.xml": f["BE/ModelItem.xml"] + b"<!-- Org.Krusgraph -->"}), "Org.Krusgraph"),
    ("missing part", lambda f: f.pop("FE/ModelItem.json"), "missing parts"),
    ("missing asset", lambda f: f.pop("FE/assets/images/Workload_Icon.png"), "not in the package"),
    ("placeholder", lambda f: f.update({"FE/ModelItem.json": f["FE/ModelItem.json"] + b" {{WORKLOAD_NAME}}"}), "PLACEHOLDER"),
    ("localhost", lambda f: f.update({"BE/WorkloadManifest.xml": f["BE/WorkloadManifest.xml"].replace(
        b"https://workload.krusgraph.com", b"http://localhost:60006")}), "frontend"),
])
def test_the_validator_catches_a_broken_package(package, tmp_path, label, change, word):
    bad = _rewrite(package, tmp_path / package.name, lambda f: (change(f), f)[1])
    r = V.validate(bad)
    assert r["problems"], label
    assert any(word in p for p in r["problems"]), (label, r["problems"])
    assert V.main([str(bad)]) == 1


@pytest.mark.skipif(not shutil.which("xmllint"), reason="xmllint not installed")
def test_the_validator_runs_the_xsds(package, tmp_path):
    bad = _rewrite(package, tmp_path / package.name, lambda f: {**f, "BE/WorkloadManifest.xml": f["BE/WorkloadManifest.xml"]
                   .replace(b"<Cloud>Public</Cloud>", b"<Cloud>Public</Cloud><Unknown/>")})
    r = V.validate(bad, require_xsd=True)
    assert r["xsd"] == "failed" and any("WorkloadDefinition.xsd" in p for p in r["problems"])


def test_a_file_name_that_is_not_a_package_is_refused(tmp_path):
    odd = tmp_path / "Krusgraph.Other.1.0.1.nupkg"
    odd.write_bytes(b"PK")
    r = V.validate(odd)
    assert any("reserve it in the tenant for good" in p for p in r["problems"])


def test_ci_keeps_the_validated_package_as_an_artifact():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    job = ci.split("\n  workload:")[1]
    for word in ("git fetch --unshallow", "set -o pipefail", "libxml2-utils", "validate_package.py", "--require-xsd", "VALIDATION.md", "SHA256SUMS.txt",
                 "steps.modeler.outputs.artifact", "if-no-files-found: error"):
        assert word in job, word
    assert "upload_workload" not in job.lower() and "fabric.microsoft.com" not in job


GO_LIVE = (ROOT / "docs" / "MODELER-GO-LIVE.md").read_text(encoding="utf-8")


def test_the_go_live_page_has_the_steps_in_order_with_success_and_rollback():
    assert GO_LIVE.startswith("# Krusgraph.Modeler") and "2026-11-16, round W12" in GO_LIVE
    heads = re.findall(r"^## (\d+)\. ", GO_LIVE, flags=re.M)
    assert heads == [str(i) for i in range(1, len(heads) + 1)] and len(heads) >= 7
    sections = re.split(r"^## \d+\. ", GO_LIVE, flags=re.M)[1:]
    for s in sections:
        assert "**Success:**" in s, s[:40]
    assert "## If something goes wrong: rollback" in GO_LIVE
    assert "K r u s g r a p h . M o d e l e r" in GO_LIVE and "cannot be undone" in GO_LIVE
    assert "validate_package.py" in GO_LIVE and "Artifacts" in GO_LIVE


def test_the_go_live_page_never_goes_live_and_makes_no_claims():
    for line in GO_LIVE.splitlines():
        if "go live" in line.lower():
            assert re.search(r"\b(never|not)\b", line, flags=re.I), line
    low = GO_LIVE.lower()
    for word in ("works with claude", "certified", "partnership", "endorsed", "compliant", "faster", "price", "plan id",
                 "offer id"):
        assert word not in low, word
    assert "@" not in GO_LIVE                                              # no names or e-mail addresses


# What Fabric and Microsoft's review show of the workload: the Workload Hub texts, the attestation page the
# certification link opens, the pilot page and guide. The workload id is spelled one way only.
LISTING = [ROOT / "workload/Workload/Manifest/assets/locales/en-US/translations.json",
           ROOT / "workload/Workload/Manifest/Product.json",
           ROOT / "fabric_backend/page_templates/WORKLOAD-ATTESTATION.md",
           ROOT / "fabric_backend/page_templates/pilot_fabric.html",
           ROOT / "docs/PILOT-ONBOARDING.md",
           ROOT / "docs/MODELER-GO-LIVE.md"]


@pytest.mark.parametrize("path", LISTING, ids=lambda p: p.name)
def test_the_listing_sources_spell_the_workload_one_way(path):
    text = path.read_text(encoding="utf-8")
    for odd in re.findall(r"Krusgraph[ _-]?Modell?er|Krusgraph\.Modeller|krusgraph\.modeler", text):
        assert odd == "Krusgraph.Modeler", (path, odd)
    for name in re.findall(r"\bKrusgraph\.(?!com\b)[A-Za-z]+", text):
        assert name == "Krusgraph.Modeler", (path, name)
    assert "works with claude" not in text.lower()


def test_the_attestation_names_krusgraph_modeler():
    text = (ROOT / "fabric_backend/page_templates/WORKLOAD-ATTESTATION.md").read_text(encoding="utf-8")
    assert "Krusgraph.Modeler" in text
