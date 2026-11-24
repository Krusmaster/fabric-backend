"""W7 (the founder, 24 November 2026): /it lists Power BI Service Dataset.Read.All (delegated), which verify_build uses
to read a semantic model's refresh history and run its DAX figure queries (W4). Read-only, granted since 24 November
2026, and organisations that consented before that date grant admin consent again (the adminconsent link with the client
id /it shows). The row is not part of access.GRANTED, which stays equal to the deploy check's REQUIRED_SCOPES
(deploy/azure_containerapp.py is a protected path and is unchanged); docs/SCOPES.md carries the same table."""
import html
import importlib
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import access, server

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-w7")
    with TestClient(server.build_app()) as c:
        yield c


def _row(page: str, scope: str) -> list[str]:
    tr = re.search(r"<tr><td><code>" + re.escape(scope) + r"</code>.*?</tr>", page, re.S).group(0)
    return [html.unescape(re.sub(r"<[^>]+>", "", c)) for c in re.findall(r"<td>(.*?)</td>", tr, re.S)]


def test_the_it_page_lists_dataset_read_all_as_read_only_since_24_november(client):
    it = client.get("/it").text
    resource, granted, used, runs = _row(it, "Dataset.Read.All")
    assert resource == "Dataset.Read.All (Power BI Service)"
    assert granted == "since 24 November 2026"                                        # as the other rows say it
    assert used.startswith("verify_build reads a semantic model's refresh history and runs its DAX figure queries")
    assert "read-only" in used
    assert runs.startswith("no") and "only reads" in runs
    assert "read from the code on 24 November 2026" in it


def test_the_row_comes_last_and_the_other_rows_are_unchanged(client):
    listed = re.findall(r"<tr><td><code>([\w.]+)</code> \(", client.get("/it").text)
    assert listed == access.scopes() + ["Dataset.Read.All"]
    assert [g.since for g in access.GRANTED].count("24 November 2026") == 0


def test_the_deploy_check_is_not_changed():
    deploy = importlib.import_module("deploy.azure_containerapp")
    assert "Dataset.Read.All" not in set().union(*deploy.REQUIRED_SCOPES.values())
    assert "Dataset.Read.All" not in access.scopes()
    assert set(access.scopes()) == set().union(*deploy.REQUIRED_SCOPES.values())


def test_consent_again_with_the_client_id_shown_on_the_page(client):
    it = client.get("/it").text
    note = re.search(r'<p id="consent-again">(.*?)</p>', it, re.S).group(1)
    assert "Consented before 24 November 2026?" in note and "<code>cid-w7</code>" in note
    assert "https://login.microsoftonline.com/&lt;your tenant id&gt;/adminconsent?client_id=cid-w7" in note
    assert "Dataset.Read.All" in note
    assert it.index("it-scopes") < it.index('id="consent-again"') < it.index('id="verified-publisher"')
    assert "has to grant admin consent again" in it                                     # the table's own sentence


def test_scopes_md_has_the_same_table_and_the_w7_note():
    doc = (ROOT / "docs/SCOPES.md").read_text(encoding="utf-8")
    table = doc.split("<!-- access:table -->\n", 1)[1].split("\n<!-- /access:table -->", 1)[0]
    assert table == access.table_md()
    assert ("| `Dataset.Read.All` (Power BI Service) | since 24 November 2026 | `verify_build` reads a semantic model's "
            "refresh history") in table
    assert "**W7 (24 November 2026).**" in doc and "adminconsent?client_id=" in doc


def test_the_other_pages_with_the_table_carry_the_row(client):
    for path in ("/start", "/privacy", "/docs/hosting-and-permissions/what-it-accesses"):
        assert "<code>Dataset.Read.All</code> (Power BI Service)" in client.get(path).text, path
    assert "Dataset.Read.All" in client.get("/llms.txt").text
