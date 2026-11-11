"""Round n212: standards on /trust, robots.txt that opts out of AI training crawlers, the trust page comparison.

- /trust (and /trust.md) has a Standards section with one row each for ISO/IEC 27001, NIS2 and the Swedish
  cybersecurity act, GDPR and Microsoft's publisher requirements; each row links its file and says what is not in
  place; the section never claims a certification, compliance or approval.
- /trust says in one sentence what robots.txt asks and that it is a request, not a technical block.
- /robots.txt keeps search engines and the AI answer fetchers in and asks the documented AI training crawlers out of
  everything; a standard parser reads it that way; /llms.txt and the .md twins are untouched.
- The trust pack has the same rows; the stale "no tool deletes anything" lines are gone; the self-assessment knows the
  incident process; docs/TRUST-PAGE-COMPARISON.md says which host was blocked and gives five improvements.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.robotparser import RobotFileParser

import pytest
from starlette.testclient import TestClient

from fabric_backend import discovery, server

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
TRUST_PACK = (DOCS / "TRUST-PACK.md").read_text(encoding="utf-8")
ISO = (DOCS / "ISO27001-SELF-ASSESSMENT.md").read_text(encoding="utf-8")
COMPARISON = (DOCS / "TRUST-PAGE-COMPARISON.md").read_text(encoding="utf-8")
SITE_MD = (DOCS / "SITE.md").read_text(encoding="utf-8")
CLAIM_WORDS = re.compile(r"\b(certified|compliant|compliance with|approved|endorsed)\b", re.I)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    with TestClient(server.build_app()) as c:
        yield c


def _section(md: str, heading: str) -> str:
    start = md.index(heading)
    nxt = md.find("\n## ", start + len(heading))
    return md[start: nxt if nxt != -1 else len(md)]


def test_trust_has_a_standards_row_for_each_and_links_the_files(client):
    md = client.get("/trust.md").text
    std = _section(md, "## Standards")
    rows = [r for r in std.splitlines() if r.startswith("| ") and not r.startswith("| ---") and "Standard or requirement" not in r]
    assert len(rows) == 4
    for row, name in zip(rows, ("ISO/IEC 27001", "NIS2", "GDPR", "Microsoft's publisher requirements")):
        assert name in row, name
        assert row.count(" | ") >= 3                                     # has, does not have, next
    for link in ("docs/ISO27001-SELF-ASSESSMENT.md", "docs/SECURITY-SUPPLIER.md", "docs/INCIDENT-RESPONSE.md",
                 "docs/DPA-DRAFT.md", "(/workload/attestation)", "(/privacy)", "(/it#verified-publisher)"):
        assert link in std, link
    for gap in ("No certification", "no external audit", "no penetration test", "draft", "not signed", "self-assessment"):
        assert gap.lower() in std.lower(), gap
    assert not CLAIM_WORDS.search(std), CLAIM_WORDS.search(std)
    html = client.get("/trust").text
    assert ">Standards<" in html and 'href="/workload/attestation"' in html


def test_trust_says_what_robots_asks_and_that_it_is_a_request(client):
    md = client.get("/trust.md").text
    crawl = _section(md, "## Search engines and AI crawlers")
    body = " ".join(crawl.split("\n", 1)[1].split())
    assert body.count(". ") == 0 and body.endswith(".")                 # one sentence
    assert "(/robots.txt)" in crawl and "request" in body and "not a technical block" in body
    for bot in ("GPTBot", "ClaudeBot", "Google-Extended", "CCBot"):
        assert bot in body and bot in discovery.AI_TRAINING_CRAWLERS


def test_trust_no_longer_says_no_tool_deletes(client):
    md = client.get("/trust.md").text
    assert "No tool deletes anything" not in md and "never deletes them itself" not in md and "never does |" not in md
    assert "Delete from Fabric" in md
    for text in (TRUST_PACK, (DOCS / "TRUST.md").read_text(encoding="utf-8"), (DOCS / "PILOT-ONBOARDING.md").read_text(encoding="utf-8")):
        assert "No tool deletes anything" not in text and "Krusgraph never deletes them" not in text
    assert "never deletes anything" not in client.get("/docs.md").text


def _parser(text: str) -> RobotFileParser:
    rp = RobotFileParser()
    rp.parse(text.splitlines())
    return rp


def test_robots_lets_search_and_answer_fetchers_in_and_asks_training_crawlers_out(client):
    t = client.get("/robots.txt").text
    rp = _parser(t)
    for ua in ("Googlebot", "Bingbot", "Applebot", "DuckDuckBot", "OAI-SearchBot", "ChatGPT-User", "Claude-User",
               "Claude-SearchBot", "PerplexityBot"):
        for path in ("/", "/trust", "/llms.txt", "/docs.md", "/sitemap.xml"):
            assert rp.can_fetch(ua, f"https://krusgraph.test{path}"), (ua, path)
        assert not rp.can_fetch(ua, "https://krusgraph.test/mascots"), ua
    for ua in ("GPTBot", "ClaudeBot", "Google-Extended", "Applebot-Extended", "CCBot", "Meta-ExternalAgent"):
        for path in ("/", "/trust", "/llms.txt", "/docs.md"):
            assert not rp.can_fetch(ua, f"https://krusgraph.test{path}"), (ua, path)
    assert "request, not a technical block" in t
    assert t.strip().endswith("Sitemap: https://krusgraph.test/sitemap.xml")


def test_robots_names_only_documented_agents_and_each_has_its_source():
    assert set(discovery.AI_ANSWER_FETCHERS).isdisjoint(discovery.AI_TRAINING_CRAWLERS)
    robots_part = _section(SITE_MD, "## robots.txt and AI crawlers")
    for bot in discovery.AI_CRAWLERS:
        assert f"`{bot}`" in robots_part, bot
    for host in ("support.claude.com", "developers.openai.com", "developers.google.com", "support.apple.com",
                 "commoncrawl.org", "developers.facebook.com"):
        assert host in robots_part, host
    assert "11 Nov 2026" in robots_part and "**Unverified**" in robots_part
    rows = [r for r in robots_part.splitlines() if r.startswith("| ") and "---" not in r and "Vendor" not in r]
    assert sum("Opened" in r for r in rows) + sum("Unverified" in r for r in rows) == len(rows) == 6


def test_llms_and_markdown_twins_stay(client):
    assert client.get("/llms.txt").status_code == 200 and client.get("/llms-full.txt").status_code == 200
    for path in ("/trust.md", "/privacy.md", "/docs.md", "/security.md"):
        assert client.get(path).status_code == 200, path


def test_trust_pack_has_the_same_standards_rows_and_no_claim():
    std = TRUST_PACK[TRUST_PACK.index("### Standards, one row each"): TRUST_PACK.index("**When ISO 27001 or SOC 2 would make sense.**")]
    for name, file in (("ISO/IEC 27001", "docs/ISO27001-SELF-ASSESSMENT.md"), ("NIS2", "docs/SECURITY-SUPPLIER.md"),
                       ("GDPR", "docs/DPA-DRAFT.md"), ("publisher requirements", "/workload/attestation")):
        assert name in std and file in std, name
    assert "docs/INCIDENT-RESPONSE.md" in std and "robots.txt" in std
    assert not re.search(r"\b(certified|compliant|approved)\b", std, re.I)


def test_self_assessment_knows_what_n211_added():
    assert "Updated 11 November 2026 (round n212)" in ISO
    row = lambda c: re.search(r"^\| " + re.escape(c) + r" \|.*$", ISO, re.M).group(0)
    for c in ("5.24", "5.25", "5.26", "5.28"):
        assert "docs/INCIDENT-RESPONSE.md" in row(c), c
        assert "| missing |" not in row(c), c
    assert "/security" in row("6.8") and "docs/SECURITY-SUPPLIER.md" in row("5.19")
    assert "never delete" in row("8.27") and "Delete from Fabric" in row("8.27")
    assert "not ISO 27001 certified" in ISO                               # the opening disclaimer stays


def test_comparison_names_the_blocked_hosts_marks_snippets_and_gives_five_improvements():
    assert "www.modernrequirements.com" in COMPARISON and "allowed" in COMPARISON
    assert COMPARISON.count("[snippet]") >= 10
    improvements = _section(COMPARISON, "## Five improvements")
    assert len(re.findall(r"^\d\. \*\*", improvements, re.M)) == 5
    assert "/trust" in improvements and "/pricing" in improvements
    assert not re.search(r"\bKrusgraph (?:is|are) (?!not\b)[^.\n]{0,40}\b(certified|compliant|approved|endorsed)\b", COMPARISON, re.I)
