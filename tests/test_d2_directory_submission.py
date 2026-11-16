"""D2: the directory submission pack, docs/DIRECTORY-SUBMISSION.md. The text the founder pastes into Claude's Connectors
Directory and ChatGPT's form fits each field's limit (Claude's submission page, read 16 November 2026: name up to 100
characters, one-liner up to 200, description up to 2,000), passes C1's wording test and the site's sales words, holds
no credential, and every URL it gives is one the site serves. The registry description is the site's one-liner. The
screenshots in docs/directory/screenshots/ match the carousel's specification (PNG, 3 to 5 at 1000 px or wider), each
with a caption and its prompt."""
import json
import re
import struct
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import server
from fabric_backend.discovery import DESCRIPTION

ROOT = Path(__file__).resolve().parent.parent
PACK = (ROOT / "docs" / "DIRECTORY-SUBMISSION.md").read_text(encoding="utf-8")
SHOTS = ROOT / "docs" / "directory" / "screenshots"
FIELDS = dict(re.findall(r"^Field: (\w+)\n\n```text\n(.*?)\n```", PACK, re.M | re.S))
LIMITS = {"name": 100, "one_liner": 200, "description": 2000}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.com/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.com")
    with TestClient(server.build_app()) as c:
        yield c


def test_every_field_is_there_and_within_the_forms_limits():
    assert set(FIELDS) == {"name", "one_liner", "description", "website", "documentation_url", "privacy_url", "terms_url",
                           "support_url", "support_email", "icon", "company"}
    for f, n in LIMITS.items():
        assert 0 < len(FIELDS[f]) <= n, (f, len(FIELDS[f]))
    assert "\n" not in FIELDS["one_liner"] and FIELDS["name"] == "Krusgraph for Microsoft Fabric"


def test_the_words_people_use_are_in_the_text_they_read():
    text = (FIELDS["one_liner"] + " " + FIELDS["description"]).lower()
    for w in ("sap", "vbak", "keys and relationships", "lakehouse", "semantic model", "power bi report", "data products",
              "data engineering", "microsoft fabric"):
        assert w in text, w


def test_no_promotional_wording_and_no_claim_beyond_what_is_tested():
    from tests.test_c1_tool_description_wording import promotional
    from tests.test_site import SALES
    for f in ("name", "one_liner", "description"):
        assert not promotional(FIELDS[f]), (f, promotional(FIELDS[f]))
    assert not promotional(PACK), promotional(PACK)
    low = PACK.lower()
    assert not [w for w in SALES if w in low]
    for pat in (r"sap[- ]certified", r"\bcertified\b", r"\bcompatible\b", r"endorsed", r"\bpartnership\b", r"\bfaster\b",
                r"\bcompliant\b", r"\bguarantee"):
        assert not re.search(pat, FIELDS["description"] + FIELDS["one_liner"], re.I), pat
    assert "Not affiliated with Microsoft or SAP." in FIELDS["description"]
    assert "has not been verified against an SAP system" in FIELDS["description"]


def test_no_credential_in_the_pack():
    assert not re.search(r"(?i)(password|passwd|secret|token)\s*[:=]\s*\S", PACK)
    assert not re.search(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", PACK)    # no tenant or client id
    assert not re.search(r"[A-Za-z0-9_~.-]{3}8Q~[A-Za-z0-9_~.-]{20,}", PACK)                           # an Entra secret's shape
    assert "Don't put credentials in the portal." in PACK and '"Review details"' in PACK


def test_the_urls_are_the_sites_own(client):
    for f in ("documentation_url", "privacy_url", "terms_url", "support_url", "icon", "website"):
        url = FIELDS[f]
        assert url.startswith("https://krusgraph.com/"), f
        r = client.get(url.removeprefix("https://krusgraph.com"))
        assert r.status_code == 200, (f, url, r.status_code)
    png = client.get("/static/icon-512.png").content
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", png[16:24]) == (512, 512)
    assert FIELDS["support_email"] == "hello@krusgraph.com"
    for slug in ("sap-sales-tables-in-fabric", "sap-tables-to-power-bi-report"):
        assert f"https://krusgraph.com/blog/{slug} |" in PACK
        assert client.get(f"/blog/{slug}").status_code == 200


def test_the_registry_description_is_the_sites_and_the_command_is_written():
    sj = json.loads((ROOT / "server.json").read_text())
    assert sj["description"] == DESCRIPTION and len(DESCRIPTION) <= 100
    assert f'"{DESCRIPTION}"' in " ".join(PACK.split())
    assert "explainable graph" not in sj["description"]
    for line in ("mcp-publisher login dns --domain krusgraph.com", "mcp-publisher validate", "mcp-publisher publish"):
        assert line in PACK


def test_the_test_cases_use_synthetic_data_and_the_engines_numbers():
    rows = re.findall(r"^\| ([PN]\d) \|", PACK, re.M)
    assert rows == ["P1", "P2", "P3", "P4", "P5", "P6", "N1", "N2", "N3"]
    assert "6 of 6 keys unique and 7 of 7 relationships without orphans" in PACK
    assert '"12 of 12 keys unique, 15 of 19 relationships hold without orphans"' in PACK      # checked in test_d2_explainers.py


def _png_size(path: Path) -> tuple[int, int]:
    b = path.read_bytes()[:24]
    assert b[:8] == b"\x89PNG\r\n\x1a\n", path
    return struct.unpack(">II", b[16:24])


@pytest.mark.skipif(not SHOTS.is_dir(), reason="no screenshots yet (taken after n227 releases the chat cards)")
def test_the_screenshots_match_the_carousels_specification():
    readme = (SHOTS / "README.md").read_text(encoding="utf-8")
    wide = sorted(SHOTS.glob("*-1280.png"))
    narrow = sorted(SHOTS.glob("*-375.png"))
    assert 3 <= len(wide) <= 5 and len(narrow) == len(wide)
    for p in wide:
        assert _png_size(p)[0] >= 1000, p.name
        assert p.name in readme and p.name.replace("-1280", "-375") in readme, p.name
    for p in narrow:
        assert _png_size(p)[0] >= 375, p.name
    assert readme.count("Caption:") >= len(wide) and readme.count("Prompt:") >= len(wide)
