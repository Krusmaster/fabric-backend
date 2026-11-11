"""Round n209: docs/GUEST-TRIAL.md (outside Fabric users try Org.Krusgraph as B2B guests in the publisher's tenant before
the name is registered) and its short section on /pilot/fabric."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import server

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "GUEST-TRIAL.md"


@pytest.fixture
def site(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _sources() -> dict[str, str]:
    rows = re.findall(r"^\| (G\d+) \|(.*)$", _doc(), flags=re.M)
    return {g: row for g, row in rows}


def test_the_doc_exists_and_cites_learn_for_each_topic():
    assert DOC.exists()
    src = _sources()
    assert len(src) >= 5
    for g, row in src.items():
        assert "https://learn.microsoft.com/" in row, g
        assert re.search(r"\(20\d\d-\d\d-\d\d", row), g                        # the page's date
        assert '"' in row, g                                                   # an exact sentence quoted
    topics = {   # topic: (a URL fragment of its Learn page, words that page's row must carry)
        "Entra B2B invite": ("entra/external-id/b2b-quickstart-add-guest-users-portal", "Invite external user"),
        "guest tenant setting": ("fabric/admin/service-admin-portal-export-sharing", "guest users can access Fabric"),
        "additional workloads": ("fabric/admin/tenant-settings-index",
                                 "Users can see and work with additional workloads not validated by Microsoft"),
        "ctid": ("powerbi-implementation-planning-tenant-setup", "customer tenant ID (CTID)"),
        "licence below F64": ("fabric/enterprise/licenses", "On F SKUs smaller than F64"),
    }
    for topic, (url, words) in topics.items():
        rows = [r for r in src.values() if url in r]
        assert rows, topic
        assert any(words in r for r in rows), topic


def test_the_doc_names_the_settings_and_the_ctid_link():
    doc = _doc()
    for words in ("**Guest users can access Microsoft Fabric**",
                  "**Users can see and work with additional workloads not validated by Microsoft**",
                  "**Capacity admins and contributors can add and remove additional workloads**",
                  "?ctid=<tenant id>", "Invite external user", "Contributor", "Viewer",
                  "Pro", "PPU", "F64", "Delete user", "Org.Krusgraph"):
        assert words in doc, words
    order = ["## 1. A dedicated workspace", "## 2. Invite the guests", "## 3. Let guest users use Fabric",
             "## 4. The additional-workloads", "## 5. Workspace roles", "## 6. The link with", "## 7. Licences",
             "## 9. After the trial", "## Sources"]
    at = [doc.index(h) for h in order]
    assert at == sorted(at)


def test_unverified_is_marked_where_learn_is_silent():
    doc = _doc()
    assert doc.count("**Unverified:**") >= 5
    unverified = doc.split("### Unverified", 1)[1]
    for words in ("?ctid=", "home", "consent", "Org.*"):
        assert words in unverified, words
    lic = doc.split("## 7. Licences", 1)[1].split("## 8.", 1)[0]
    assert "**Unverified:**" in lic and "create" in lic                       # home-tenant licence for creating


def test_synthetic_data_dedicated_workspace_and_no_claims():
    doc = _doc()
    low = doc.lower()
    assert "synthetic data only" in low and "dedicated workspace" in low
    assert "seed(spark, schema=\"shop\")" in doc
    assert "not affiliated with Microsoft" in doc and "Microsoft does not endorse" in doc
    for word in ("faster", "in seconds", "certified by", "partner of microsoft", "guarantee", "seamless", "effortless"):
        assert word not in low, word


def test_no_personal_data_in_the_doc():
    doc = _doc()
    emails = set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", doc))
    assert emails <= {"hello@krusgraph.com"}, emails
    assert not re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", doc)   # no tenant or app ids
    assert not re.search(r"\+?\d[\d ()-]{8,}\d", doc.split("## Sources", 1)[0])        # no phone numbers


def test_the_pilot_page_has_the_guest_section_with_the_link(site):
    r = site.get("/pilot/fabric")
    assert r.status_code == 200
    page = r.text
    assert 'id="guest-trial"' in page
    section = page.split('id="guest-trial"', 1)[1].split("</section>", 1)[0]
    assert "Try it as a guest before the name is registered" in section
    assert 'href="https://github.com/Krusmaster/fabric-backend/blob/main/docs/GUEST-TRIAL.md"' in section
    for words in ("Org.Krusgraph", "synthetic", "dedicated workspace", "Guest users can access Microsoft Fabric",
                  "?ctid=", "F64", "Pro"):
        assert words in section, words
    assert page.index('id="new-item"') < page.index('id="guest-trial"')       # after the five steps
