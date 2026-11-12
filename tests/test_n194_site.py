"""Round n194: the founder kept the home page from before n190 (the film, the replay, the hub, the FAQ and the developer
note). What remains of n190: n190's 'What you can build' grid, unchanged in look, at the top of /docs after 'Which
Krusgraph should I use?' and the film, and in its Markdown twin (fabric_backend/claims.py stays its only source); /choose no longer
says Krusgraph for Fabric never runs the pipeline; the three n190 website documents, marked as not applied."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import claims, server, tool_status as ts

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


def _main(html: str) -> str:
    return html[html.index('<main id="main"'):html.index("</main>")]


def test_home_page_is_the_one_from_before_n190(client):
    html = _main(client.get("/").text)
    assert "{{HOME_FILM}}" in (ROOT / "fabric_backend/page_templates/home.html").read_text()
    assert 'id="faq"' in html
    for gone in ("What you can build", "intent-tile", "data-claim=", "Your data already has connections"):
        assert gone not in html, gone


def test_claims_are_derived_from_tool_status():
    assert claims.status("semantic_model") == "Tested live" and "create_semantic_model" in ts.LATER_LIVE
    assert claims.status("pipeline") == "Tested live" and "create_pipeline" in ts.RAN_LIVE
    assert claims.status("data_agent") == "Experimental" and "create_data_agent" in ts.CREATE_RECORD
    assert claims.status("graphql") == "Experimental" and ts.create_api_word() == "Experimental"
    assert claims.status("app") == "Preview"
    assert {r["status"] for r in claims.table()} <= set(claims.CHIPS)
    assert [n for _k, n, *_ in claims.OUTPUTS] == ["Power BI semantic model", "Power BI report", "Fabric IQ ontology",
                                                    "Notebooks and a pipeline", "API for GraphQL", "Data agent", "App (Rayfin)"]


def test_docs_start_page_has_what_you_can_build_after_which_krusgraph(client):
    html = _main(client.get("/docs").text)
    which, build = html.index("<strong>Which Krusgraph should I use?</strong>"), html.index('id="what-you-can-build"')   # n196: the guide in the article, not the menu
    # n196: "What Krusgraph does" (the sentence and the three points) now opens the page, before the guide
    assert html.index("See how your tables connect:") < which < html.index('id="film"') < build
    sec = html[build:html.index("</section>", build)]
    assert sec.count('class="out-tile"') == len(claims.OUTPUTS) == 7
    found = re.findall(r'data-claim="(\w+)" data-status="([^"]+)"[^>]*>([^<]+)</a>', sec)
    assert [k for k, _, _ in found] == [k for k, *_ in claims.OUTPUTS]
    for key, status, text in found:
        assert status == claims.status(key) == text, key
    assert sec.count('class="out-tile-more"') == 7 and "chip-legend" in sec
    assert claims.RUNS in sec and claims.CHECK_LINE in sec


def test_markdown_twin_carries_the_same_table(client):
    md = client.get("/docs.md").text
    assert "**What you can build.**" in md and claims.RUNS in md and claims.CHECK_LINE in md
    assert all(f"| {r['name']} | {r['status']} |" in md for r in claims.table())
    assert md.index("See how your tables connect:") < md.index("**What you can build.**")   # n196


def test_only_the_docs_carry_the_chips(client):
    for path in ("/", "/start", "/choose", "/pricing"):
        assert "data-claim=" not in client.get(path).text, path


def test_choose_no_longer_says_fabric_never_runs_the_pipeline(client):
    for path in ("/choose", "/choose.md"):
        text = client.get(path).text
        assert "Does not run or schedule" not in text, path
        assert "Run once or Schedule" in text, path


@pytest.mark.parametrize("name", ["WEBSITE_UX_AUDIT.md", "WEBSITE_COPY_REWRITE.md", "WEBSITE_IMPLEMENTATION_PLAN.md"])
def test_n190_documents_are_marked_not_applied(name):
    first = (ROOT / "docs" / name).read_text().splitlines()[0]
    assert first == "Not applied: the founder kept the previous home page on 10 Nov 2026 (n194)."
