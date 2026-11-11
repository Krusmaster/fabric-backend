"""Round n211: a supplier security pack for customers under NIS2 and the Swedish cybersecurity act.

- /.well-known/security.txt follows RFC 9116: Contact, Expires within a year (and more than 30 days away), Policy on
  the site's own /security page, Preferred-Languages "en, sv", Canonical; no field twice, no unknown field.
- /security (and /security.md) is the vulnerability disclosure policy: it renders, names the same address as
  security.txt's Contact, states scope and testing rules, and carries no claim words.
- /trust links the supplier pack, the incident process and the disclosure policy, with the honest status.
- docs/SECURITY-SUPPLIER.md and docs/INCIDENT-RESPONSE.md exist, cover what the brief names, say what is not in place,
  mark the notification time as a proposal, and never say Krusgraph is compliant, certified or approved.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import discovery, server

ROOT = Path(__file__).resolve().parents[1]
SUPPLIER = (ROOT / "docs" / "SECURITY-SUPPLIER.md").read_text(encoding="utf-8")
INCIDENT = (ROOT / "docs" / "INCIDENT-RESPONSE.md").read_text(encoding="utf-8")
TRUST_PACK = (ROOT / "docs" / "TRUST-PACK.md").read_text(encoding="utf-8")
# a claim sentence: "<Krusgraph or it> is/are ... compliant|certified|approved" without a negation in between
CLAIM = re.compile(r"\b(?:Krusgraph|Kruse Consulting AB|it)\s+(?:is|are)\s+(?!not\b|\*\*not\*\*)[^.\n]{0,40}?\b(compliant|certified|approved|endorsed)\b", re.I)
RFC9116_FIELDS = {"Acknowledgments", "Canonical", "Contact", "Encryption", "Expires", "Hiring", "Policy", "Preferred-Languages", "CSAF"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    with TestClient(server.build_app()) as c:
        yield c


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def test_security_txt_fields_follow_rfc_9116(client):
    r = client.get("/.well-known/security.txt")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    lines = [ln for ln in r.text.splitlines() if ln and not ln.startswith("#")]
    names = [ln.split(":", 1)[0] for ln in lines]
    assert set(names) <= RFC9116_FIELDS
    assert names.count("Expires") == 1 and names.count("Contact") >= 1           # RFC 9116 2.5.3 and 2.5.5
    fields = {ln.split(": ", 1)[0]: ln.split(": ", 1)[1] for ln in lines}
    assert fields["Contact"].startswith(("mailto:", "https://"))
    assert fields["Policy"] == "https://krusgraph.test/security"
    assert fields["Preferred-Languages"] == "en, sv"
    assert fields["Canonical"] == "https://krusgraph.test/.well-known/security.txt"
    expires = datetime.strptime(fields["Expires"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert timedelta(days=30) < expires - datetime.now(timezone.utc) <= timedelta(days=366), "renew Expires in discovery.py"
    assert client.head("/.well-known/security.txt").status_code == 200


def test_the_policy_named_in_security_txt_is_served_and_uses_the_same_address(client):
    contact = discovery.SECURITY_CONTACT.removeprefix("mailto:")
    r = client.get("/security")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    text = _plain(r.text.split('<main id="main"', 1)[1].split("</main>", 1)[0])
    for part in ("Vulnerability disclosure policy", contact, "What is in scope", "Testing rules", "What to expect",
                 "krusgraph.com", "workload.krusgraph.com", "no bug bounty", "Do not open a public GitHub issue"):
        assert part in text, part
    md = client.get("/security.md")
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown") and contact in md.text
    assert "/security</loc>" in client.get("/sitemap.xml").text
    assert not re.search(r"\b(certified|compliant|endorsed|partner of)\b", text, re.I)
    root_policy = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert contact in root_policy and "/security" in root_policy


def test_trust_links_the_supplier_pack_with_its_honest_status(client):
    text = client.get("/trust").text
    assert "For customers under NIS2 and the Swedish cybersecurity act" in text
    for href in ("/blob/main/docs/SECURITY-SUPPLIER.md", "/blob/main/docs/INCIDENT-RESPONSE.md", 'href="/security"',
                 'href="/.well-known/security.txt"'):
        assert href in text, href
    plain = _plain(text)
    assert "a proposal, not yet confirmed" in plain
    assert "Not in place yet: a signed data processing agreement, an external penetration test, a service level agreement" in plain


def test_the_trust_pack_links_the_new_documents():
    for name in ("docs/SECURITY-SUPPLIER.md", "docs/INCIDENT-RESPONSE.md", "/security", "security.txt"):
        assert name in TRUST_PACK, name


def test_the_supplier_pack_covers_what_the_brief_names():
    for part in ("Directive (EU) 2022/2555", "Article 21", "Article 23", "24 hours", "72 hours", "one month",
                 "SFS 2025:1506", "15 January 2026", "MCFFS 2026:11", "Annex II", "medium-sized",
                 "Information owner", "System owner", "Microsoft (Azure)", "AI provider",
                 "Delegated permissions only", "No table contents stored", "retention", "Revoke", "Sweden Central",
                 "Open source", "Dry run before writes", "docs/TRUST-PACK.md", "/trust",
                 "Unverified", "not legal advice"):
        assert part in SUPPLIER, part
    for letter in "abcdefghij":                                                   # the Article 21(2) table, every point
        assert re.search(rf"^\| \({letter}\) ", SUPPLIER, re.M), letter
    not_yet = SUPPLIER.split("## 6. What is not in place yet", 1)[1].split("## 7.", 1)[0]
    for gap in ("data processing agreement", "penetration test", "service level agreement", "certification"):
        assert gap in not_yet, gap


def test_the_incident_process_marks_the_target_as_a_proposal():
    for part in ("## 1. Detect", "## 2. Assess", "## 3. Contain", "## 4. Notify affected customers",
                 "## 5. After the incident", "## 6. What the founder must decide", "without undue delay",
                 "Proposal for the founder to confirm", "not a promise", "KRUSGRAPH_CLIENT_REGISTRATION=0",
                 "workload_allowed_tenants", "What the notice contains"):
        assert part in INCIDENT, part


@pytest.mark.parametrize("name", ["SECURITY-SUPPLIER.md", "INCIDENT-RESPONSE.md"])
def test_no_claim_of_compliance_certification_or_approval(name):
    text = (ROOT / "docs" / name).read_text(encoding="utf-8")
    assert not CLAIM.search(text), CLAIM.search(text)
    assert not re.search(r"\bNIS2[- ]compliant\b", text, re.I)
    assert not re.search(r"\b(partner of|endorsed by)\b", text, re.I)
