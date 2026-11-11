"""Round n205: trust, honest labels, the comparison and findability before the launch of 11 November 2026.

- /trust (and /trust.md), written from docs/TRUST-PACK.md: renders, is linked from the footer ("Security and data"),
  /pricing and /choose, is in the sitemap and llms.txt, and carries no claim words.
- Every hosted tool's title ends in "(experimental)" exactly when tool_status.experimental() says so; its name never
  changes. README.md's status block equals tool_status.readme_status_md().
- /choose has the comparison "Why not just Microsoft's tools?" with its five rows; /docs links to it.
- /pricing says what is free today, that the code stays MIT and that a Marketplace team plan is planned with no price.
- README's first line, its Roadmap, and docs/FOUNDER-TODO.md.
The browser half runs tests/n205_browser.js (375 and 1280 px)."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import offering, server, tool_status as ts

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
# the words a claim would use: no certification, compliance, partnership, endorsement or speed is claimed anywhere new
CLAIMS = re.compile(r"\b(certified|compliant|partner of|endorsed|faster)\b", re.I)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _main(html: str) -> str:
    return html.split('<main id="main"', 1)[1].split("</main>", 1)[0]


# ------------------------------------------------------------------ 1. /trust ------------------------------------------

def test_trust_renders_with_every_part_the_brief_names(client):
    r = client.get("/trust")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    text = _plain(_main(r.text))
    for part in ("Security and data", "What passes through, and what is stored", "No table contents are stored",
                 "Sweden Central", "Sub-processors", "Sign-in and delegated permissions", "How to revoke access",
                 "What is and is not in place", "Answers to a standard security questionnaire"):
        assert part in text, part
    # the status table: no certification held, the attestation a draft, no penetration test
    assert "holds no certification" in text and "Not held" in text
    assert re.search(r"vendor attestation \(Krusgraph\.Modeler\) Draft", text)
    assert re.search(r"Penetration test or independent security assessment Not done", text)
    # the thirty questionnaire rows
    rows = re.findall(r"<tr><td>(\d+)</td>", _main(r.text))
    assert rows == [str(i) for i in range(1, 31)]
    assert '<link rel="alternate" type="text/markdown" href="/trust.md"' in r.text


def test_trust_markdown_twin_and_discovery(client):
    md = client.get("/trust.md")
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert md.text.startswith("# Security and data") and "{{" not in md.text
    assert "/trust" in client.get("/sitemap.xml").text
    assert "/trust.md" in client.get("/llms.txt").text and "# Security and data" in client.get("/llms-full.txt").text


@pytest.mark.parametrize("path", ["/", "/check", "/docs", "/pricing", "/choose", "/privacy"])
def test_footer_links_security_and_data(client, path):
    footer = client.get(path).text.split('<footer class="site-footer">', 1)[1]
    assert '<a href="/trust">Security and data</a>' in footer


@pytest.mark.parametrize("path", ["/pricing", "/choose"])
def test_pricing_and_choose_link_trust_in_their_body(client, path):
    assert 'href="/trust"' in _main(client.get(path).text)


@pytest.mark.parametrize("path", ["/trust", "/trust.md", "/pricing", "/choose", "/choose.md"])
def test_no_claim_words(client, path):
    text = client.get(path).text
    text = _main(text) if path.endswith(("trust", "pricing", "choose")) else text
    assert not CLAIMS.search(_plain(text)), CLAIMS.search(_plain(text))


def test_no_claim_words_in_the_new_texts():
    for name in ("fabric_backend/page_templates/TRUST.md", "docs/FOUNDER-TODO.md"):
        assert not CLAIMS.search((ROOT / name).read_text(encoding="utf-8")), name
    roadmap = README.split("## Roadmap", 1)[1].split("\n## ", 1)[0]
    alternatives = " ".join(" ".join(r) for r in offering.ALTERNATIVES) + offering.ALTERNATIVES_INTRO
    for text in (roadmap, alternatives, README.splitlines()[0]):
        assert not CLAIMS.search(text), text


# ------------------------------------------------------------------ 2. honest labels ---------------------------------

def _hosted_tools():
    return asyncio.run(server.mcp.list_tools())


def test_every_title_says_experimental_exactly_when_tool_status_does():
    tools = _hosted_tools()
    assert {t.name for t in tools} == set(ts.STATUS)
    for t in tools:
        marked = t.title.endswith(ts.EXPERIMENTAL)
        assert marked == ts.experimental(t.name), (t.name, ts.short(t.name), t.title)
        assert t.annotations.title == t.title, t.name                    # the directory reads annotations.title
        assert "experimental" not in t.name and t.title.count("(experimental)") <= 1


def test_experimental_follows_the_short_status_the_site_uses():
    for name in ts.STATUS:
        s = ts.short(name)
        assert ts.experimental(name) == (not (s.startswith("tested end to end") or s.startswith("created live"))), name
    # as the record stands on 10 November 2026
    assert {n for n in ts.STATUS if ts.experimental(n)} == {"domain_draft", "sap_pack_draft", "create_views",
                                                            "create_data_agent", "compare_semantic_model",
                                                            "start"}                     # n219: unit tests only
    # create_pipeline created pipeline_shop live and it ran in Fabric (RAN_LIVE): created live, not a draft
    assert ts.short("create_pipeline") == "created live"


def test_readme_status_lines_equal_tool_status():
    block = README.split(ts.README_BEGIN, 1)[1].split(ts.README_END, 1)[0]
    assert ts.README_BEGIN + block + ts.README_END == ts.readme_status_md(), \
        "README.md's status block is stale: paste fabric_backend.tool_status.readme_status_md() between the markers"
    for name in ts.STATUS:
        assert f"| `{name}` | {ts.short(name)} |" in block, name


def test_readme_says_what_tool_status_says_about_create_backend():
    # tool_status: updated in place live (27 October from Claude, 30 October from Lovable), a new API by unit tests only
    assert ts.word("create_backend") == "Tested end to end as an update in place"
    assert "creating a new API is unit-tested only" in ts.OPEN["create_backend"]
    assert "Creating a new API with `create_backend` has still not run live." in README
    assert "a Lovable app read `shop_api` live on 30 October 2026" in README


# ------------------------------------------------------------------ 3. the comparison on /choose ------------------------

def test_choose_has_the_comparison_with_its_five_rows(client):
    page = _main(client.get("/choose").text)
    assert 'id="why-not-microsoft"' in page and "Why not just Microsoft" in page
    section = page.split('id="why-not-microsoft"', 1)[1].split("</section>", 1)[0]
    assert "<th scope=\"col\">What it does</th>" in section and "<th scope=\"col\">What Krusgraph adds</th>" in section
    rows = re.findall(r'<tr><th scope="row">([^<]+)</th>', section)
    assert rows == ["Fabric API for GraphQL, set up by hand", "GraphQL MCP and Lovable&#x27;s Fabric connector",
                    "Fabric MCP, Fabric IQ MCP and the Power BI Modeling MCP", "Power BI&#x27;s automatic relationships",
                    "dbt tests"]
    assert "<img" not in section and "<svg" not in section                # names in plain text, no logos
    md = client.get("/choose.md").text
    assert "## Why not just Microsoft's tools?" in md and "| dbt tests |" in md


def test_docs_link_to_the_comparison(client):
    assert 'href="/choose#why-not-microsoft"' in client.get("/docs").text


# ------------------------------------------------------------------ 4. /pricing ----------------------------------------

def test_pricing_says_what_is_free_and_that_marketplace_is_planned_without_a_price(client):
    text = _plain(_main(client.get("/pricing").text))
    para = text.split("Free today:", 1)[1].split(".", 3)
    para = ".".join(para[:3])
    assert "Check my tables" in para and "connector" in para and "open-source code" in para
    assert "The open code stays under the MIT licence. A paid team plan through Microsoft Marketplace is planned; it has no price yet" in text
    assert not re.search(r"(SEK|EUR|€|\$)\s*\d", text)


# ------------------------------------------------------------------ 5. findability -----------------------------------

def test_readme_first_line_and_roadmap():
    first = README.splitlines()[0]
    assert first.startswith("# Krusgraph") and "Microsoft Fabric" in first and "this repository is the Krusgraph source" in first
    roadmap = README.split("\n## Roadmap\n", 1)[1].split("\n## ", 1)[0]
    items = [ln for ln in roadmap.splitlines() if ln.startswith("- ")]
    assert len(items) == 5 and all("(planned)" in ln for ln in items)
    for what in ("Create in the background", "data product page", "Health over time", "SAP Datasphere", "Marketplace"):
        assert what in roadmap, what


def test_founder_todo_lists_the_github_settings():
    todo = (ROOT / "docs" / "FOUNDER-TODO.md").read_text(encoding="utf-8")
    assert "Krusgraph: keys and relationships for Microsoft Fabric tables, checked against the rows" in todo
    for topic in ("microsoft-fabric", "mcp", "graphql", "data-modeling", "power-bi", "krusgraph"):
        assert f"`{topic}`" in todo, topic
    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
    assert "Release" in todo and f"v{version}" in todo


# ------------------------------------------------------------------ browser: /trust at 375 and 1280 px -----------------

def _playwright() -> bool:
    return bool(shutil.which("node")) and subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


@pytest.fixture(scope="module")
def browser():
    if not _playwright():
        pytest.skip("node + playwright not available")
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    env = os.environ | {"PRODUCT_NAME": "Krusgraph", "MCP_PUBLIC_URL": "https://krusgraph.test/mcp", "CONTACT_EMAIL": "hello@krusgraph.test",
                        "ENTRA_CLIENT_ID": "00000000-0000-0000-0000-000000000000", "ENTRA_CLIENT_SECRET": "test-only"}
    proc = subprocess.Popen([sys.executable, "-m", "fabric_backend.server", "--host", "127.0.0.1", "--port", str(port)], env=env,
                            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(base + "/healthz", timeout=1); break
            except Exception:
                time.sleep(0.25)
        else:
            pytest.fail("server did not start")
        run = subprocess.run(["node", str(ROOT / "tests" / "n205_browser.js"), base], capture_output=True, text=True, timeout=300)
        assert run.returncode == 0, run.stderr[-3000:]
        yield json.loads(run.stdout.strip().splitlines()[-1])
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_browser_trust_at_375_and_1280(browser):
    assert not browser["errors"], browser["errors"]
    assert set(browser["runs"]) == {"light-1280", "light-375", "dark-1280", "dark-375"}
    for key, run in browser["runs"].items():
        assert run["status"] == 200 and run["h1"] == "Security and data", key
        assert "What is and is not in place" in run["h2"] and run["tables"] >= 5, key
        assert not run["pageOverflow"], key                                 # no horizontal page scroll; tables scroll in their box
        assert run["footerLink"], key
        if key.endswith("375"):
            assert run["articleWidth"] <= 375 and run["articleLeft"] >= 0, (key, run)
