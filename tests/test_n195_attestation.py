"""Round n195: Krusgraph.Modeler ready for Microsoft's publishing review.

- The attestation link: Product.json's productDetail.supportLink.certification.url, the field Microsoft's requirement 1.4.1
  and its validator read (publishing-requirements-workload; microsoft/fabric-extensibility-toolkit-validator 78e17c3,
  Testcases_Workload.json). The Krusgraph.Modeler package points it at /workload/attestation; Org.Krusgraph keeps /it,
  and WorkloadManifest.xml carries no attestation element (the kit's WorkloadDefinition.xsd has none).
- The build refuses a Krusgraph.Modeler package that lacks what the review reads and we can fill truthfully, and prints
  what we cannot fill yet (the Marketplace offer).
- The attestation page: renders, has a Markdown twin, follows the template's Section III headings, carries the terms the
  validator searches for, says "Draft" until the founder removes it, is not linked from the home page or the navigation,
  and claims no certification, compliance or endorsement.
Nothing here uploads anything or calls Fabric, Entra or Azure."""
import importlib.util
import json
import re
import shutil
import zipfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import server
from fabric_backend.pages import ATTESTATION_DRAFT_MARKER, ATTESTATION_PATH, PAGES, attestation_md

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "workload" / "Workload" / "Manifest"
APP_ID = "853a0cf0-7d35-42b7-b384-26178755a72a"
ATTESTATION_URL = "https://krusgraph.com/workload/attestation"


def _builder():
    spec = importlib.util.spec_from_file_location("build_package_n195", ROOT / "workload/scripts/build_package.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _builder()


def _package(name: str, tmp_path: Path, manifest: Path = MANIFEST) -> dict[str, bytes]:
    pkg = B.build(APP_ID, "1.0.1", out_dir=tmp_path / name, manifest=manifest, name=name)
    with zipfile.ZipFile(pkg) as z:
        return {n: z.read(n) for n in z.namelist()}


# ------------------------------------------------------------------ the manifest ------------------------------------

def test_modeler_package_carries_the_attestation_link_and_what_the_review_reads(tmp_path):
    files = _package("Krusgraph.Modeler", tmp_path)
    product = json.loads(files["FE/Product.json"])
    detail = product["productDetail"]
    assert detail["supportLink"]["certification"]["url"] == ATTESTATION_URL == B.ATTESTATION_URL
    assert detail["publisher"] == "Kruse Consulting AB"
    links = {k: v["url"] for k, v in detail["supportLink"].items()}
    assert set(links) == {"documentation", "certification", "help", "privacy", "terms", "license"}
    assert all(u.startswith("https://") for u in links.values())
    words = json.loads(files["FE/assets/locales/en-US/translations.json"])
    for key in (product["displayName"], product["description"], detail["slogan"], detail["description"],
                product["createExperience"]["description"]):
        assert words[key].strip(), key
    assert b"{{" not in files["FE/Product.json"]


def test_org_package_points_at_the_attestation_page_too_and_the_workload_xml_has_no_attestation_element(tmp_path):
    # n201 (the founder, 10 November 2026): Fabric labels this link "Certification" and Learn documents no label for it,
    # so both packages point at the attestation page, which says "Draft." at the top. Until n201 Org.Krusgraph kept /it.
    org = json.loads(_package("Org.Krusgraph", tmp_path)["FE/Product.json"])
    assert org["productDetail"]["supportLink"]["certification"]["url"] == B.ATTESTATION_URL
    for name in ("Org.Krusgraph", "Krusgraph.Modeler"):
        xml = _package(name, tmp_path / "x")["BE/WorkloadManifest.xml"].decode()
        assert "attestation" not in xml.lower(), name             # WorkloadDefinition.xsd has no such element
    assert "Attestation" not in (MANIFEST / "WorkloadDefinition.xsd").read_text(encoding="utf-8")


def _copy_manifest(tmp_path: Path) -> Path:
    dst = tmp_path / "Manifest"
    shutil.copytree(MANIFEST, dst)
    return dst


@pytest.mark.parametrize("change, message", [
    (lambda p: p["productDetail"].update(publisher="Someone else"), "productDetail.publisher"),
    (lambda p: p["productDetail"]["supportLink"]["help"].update(url="http://krusgraph.com/support"), "supportLink.help"),
    (lambda p: p["productDetail"]["supportLink"]["certification"].update(url="https://krusgraph.com/it"), "attestation link"),
    (lambda p: p.update(favicon="assets/images/Workload_Hub_Banner.png"), "favicon"),
    (lambda p: p["homePage"].update(learningMaterials=[]), "learningMaterials"),
    (lambda p: p["productDetail"].update(slogan="No_Such_Key"), "productDetail.slogan"),
])
def test_modeler_build_refuses_a_package_the_review_would_reject(tmp_path, change, message):
    manifest = _copy_manifest(tmp_path)
    product = json.loads((manifest / "Product.json").read_text(encoding="utf-8"))
    change(product)
    (manifest / "Product.json").write_text(json.dumps(product, indent=4), encoding="utf-8")
    with pytest.raises(B.PackageError, match="not ready for Microsoft's publishing review") as e:
        _package("Krusgraph.Modeler", tmp_path, manifest)
    assert message in str(e.value)
    _package("Org.Krusgraph", tmp_path, manifest)                  # the development package is not held to it


def test_build_prints_the_marketplace_gap_and_the_attestation_link(tmp_path, capsys):
    assert B.main(["--name", "Krusgraph.Modeler", "--frontend-app-id", APP_ID, "--version", "1.0.2",
                   "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert ATTESTATION_URL in out
    assert "not a Microsoft Marketplace offer" in out and "1.3.1" in out
    assert B.main(["--frontend-app-id", APP_ID, "--version", "1.0.2", "--out", str(tmp_path)]) == 0
    assert "Marketplace" not in capsys.readouterr().out


def test_ci_workload_job_builds_and_checks_the_modeler_package():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    job = ci[ci.index("\n  workload:"):]
    assert "build_package.py --name \"$name\"" in job and "Krusgraph.Modeler" in job
    assert ATTESTATION_URL in job


# ------------------------------------------------------------------ the page ----------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.delenv("COMPANY_ORGNR", raising=False)
    with TestClient(server.build_app()) as c:
        yield c


def _article(page: str) -> str:
    return page[page.index("<article"):page.index("</article>")]


def test_page_and_markdown_twin_render(client):
    r = client.get(ATTESTATION_PATH)
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "<h1>Vendor attestation: Krusgraph.Modeler</h1>" in r.text
    md = client.get(ATTESTATION_PATH + ".md")
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert md.text == attestation_md()
    assert f'href="{ATTESTATION_PATH}.md"' in r.text                # the Markdown twin is announced


def test_draft_marker_is_there_and_keeps_the_page_out_of_search(client):
    md = attestation_md()
    assert md.splitlines()[2].startswith(ATTESTATION_DRAFT_MARKER)
    page = client.get(ATTESTATION_PATH).text
    assert "<strong>Draft.</strong>" in _article(page)
    assert 'name="robots" content="noindex,nofollow"' in page
    from fabric_backend import discovery
    assert ATTESTATION_PATH not in discovery.sitemap_xml()


def test_not_linked_from_home_or_navigation(client):
    assert ATTESTATION_PATH not in client.get("/").text
    for path in list(PAGES)[:6] + ["/docs", "/privacy", ATTESTATION_PATH]:
        page = client.get(path).text
        nav = page[page.index("<nav"):page.index("</nav>")] if "<nav" in page else ""
        footer = page[page.index("<footer"):] if "<footer" in page else ""
        assert ATTESTATION_PATH not in nav and ATTESTATION_PATH not in footer, path


def test_no_claim_words(client):
    for text in (_article(client.get(ATTESTATION_PATH).text), attestation_md()):
        low = text.lower()
        for word in ("certified", "compliant", "endorsed", "partner of microsoft", "microsoft partner", "partnership"):
            assert not re.search(r"\b" + word + r"\b", low), word
        assert "no certification" in low


# Microsoft's template, Section III: every heading, in order (publishing-vendor-attestation-template, ms.date 24
# February 2026, read 10 November 2026). "One Lake" is written "OneLake" because the validator searches for that word.
TEMPLATE_HEADINGS = [
    "Publish Workload Requirements Attestation Checklist", "Workload Information", "Business Requirements",
    "Value To Customers", "Trial", "Monetization", "Technical Requirements", "Microsoft Entra Access", "OneLake",
    "Microsoft Entra Conditional Access", "Admin REST API", "Customer Facing Monitoring & Diagnostic", "B2B",
    "Business Continuity and disaster recovery", "Performance", "Presence", "Public APIs", "Design / UX Requirements",
    "Common UX", "Item Creation Experience", "Monitoring Hub", "Trial Experience", "Monetization Experience",
    "Accessibility", "World Readiness / Internationalization", "Item Settings", "Samples", "Custom Actions",
    "Workspace settings", "Global Search", "Security / Compliance Requirements", "Security general", "Privacy",
    "Data Residency", "Compliance", "Support", "Live site", "Supportability", "Service Health and Availability",
    "Fabric Features", "Application Life Cycle Management (ALM)", "CI/CD (Continuous Integration / Continuous Deployment)",
    "Item Definition Portability", "Private Links", "Data Hub", "Data Lineage", "Sensitivity Labels", "Extra Notes",
    "References"]

# The terms the validator's ATTESTATION tests search for, case-insensitive (Testcases_Workload.json at 78e17c3), with
# {{workloadName}} replaced by the workload name.
VALIDATOR_TERMS = ["Workload Name", "Krusgraph.Modeler", "OneLake", "Microsoft Entra Conditional Access", "Monitoring",
                   "Diagnostic", "B2B", "Business Continuity and disaster recovery", "Performance", "Presence",
                   "Accessibility", "World Readiness", "Internationalization", "Security", "JavaScript",
                   "HTTP-only cookies", "Data Residency", "Compliance Requirements", "Live site", "support", "contact",
                   "Service Health and Availability", "Application Life Cycle Management", "Private Links", "Data Hub",
                   "Data Lineage", "Sensitivity Labels"]


def test_follows_the_template_and_carries_the_validator_terms(client):
    md = attestation_md()
    headings = [m.group(1) for m in re.finditer(r"^#{2,3} (.+)$", md, re.M)]
    assert headings == TEMPLATE_HEADINGS
    text = re.sub(r"<[^>]+>", " ", _article(client.get(ATTESTATION_PATH).text)).lower()
    for term in VALIDATOR_TERMS:
        assert term.lower() in text, term


def test_states_the_facts_the_founder_asked_for():
    md = attestation_md()
    assert "No row values" in md and "Delegated permissions only" in md and "no application permissions" in md
    assert "Azure Container Apps" in md and "Sweden Central" in md
    assert "gustav@krusgraph.com" in md                              # SECURITY.md and security.txt
    for scope in ("Fabric.Extend", "Lakehouse.Read.All", "Item.ReadWrite.All", "user_impersonation", "DataPipeline.Execute.All"):
        assert scope in md, scope
    for gap in ("penetration test", "service level agreement", "publisher verification", "Marketplace offer"):
        assert gap in md, gap


def test_every_site_link_on_the_page_exists(client):
    urls = {u.rstrip(".") for u in re.findall(r"https://krusgraph\.com(/[A-Za-z0-9/._-]*)", attestation_md())}
    assert {"/it", "/privacy", "/terms", "/support", "/docs", "/health", "/.well-known/security.txt"} <= urls
    for path in urls - {"/workload/workload/Krusgraph.Modeler/user_impersonation"}:   # a scope, not a page
        assert client.get(path).status_code == 200, path


# ------------------------------------------------------------------ the runbook -------------------------------------

def test_runbook_covers_the_founders_steps():
    doc = (ROOT / "docs" / "WORKLOAD-PUBLISH.md").read_text(encoding="utf-8")
    for words in ("not registered with Microsoft", "Subject:", "97022330",                       # blocker and ticket
                  "Partner One ID", "partner global account", "Publisher domain", "Add Partner ID to verify publisher",
                  "| Letter | K | r | u | s | g | r | a | p | h | . | M | o | d | e | l | e | r |",
                  "afd60f91-ebf2-4e00-b221-bd2ebfd15095", "Selected tenants",
                  "Users can see and work with additional workloads not validated by Microsoft", "adminconsent?client_id=",
                  "Publishing Stage", "Publishing Tenant ID", "Workload ID", "Version Number", "Attestation URL",
                  ATTESTATION_URL, "fabric-extensibility-toolkit-validator", "TODO list", "Unverified"):
        assert words in doc, words
    assert len("Krusgraph.Modeler") == 17 and len("Modeler") <= 32
