"""The overview of tools, functions and clients on /docs, /docs.md and llms-full.txt: one source
(fabric_backend/tool_status.py), so the pages and the server's instructions cannot say different things."""
import asyncio

import pytest

from fabric_backend import mcp_server, tool_status as ts
from tests.test_site import client  # noqa: F401  (the site's test client)


def test_local_tools_are_the_hosted_tools_the_local_server_has():
    local = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert set(ts.LOCAL_TOOLS) == local & set(ts.STATUS)


def test_every_tool_once_every_word_a_status_word_and_the_clients_of_the_brief():
    md = ts.overview_md()
    for t in ts.STATUS:
        assert md.count(f"| `{t}` | {ts.label(t)} | {ts.where(t)} |") == 1, t
    assert ts.overview_words() <= set(ts.WORDS)
    clients = {c.name: (c.status, c.path) for c in ts.CLIENTS}
    assert clients == {"Claude": ("Tested end to end", "/mcp"), "VS Code": ("Experimental", "/mcp/connect"),
                       "Claude Code": ("Experimental", "/mcp/connect"), "Cursor": ("Experimental", "/mcp/connect"),
                       "Glama": ("Experimental", "/mcp/connect"), "Lovable": ("Experimental", "")}
    # working (signed in and ran tools) is named on the site; the status word stays Experimental for /mcp/connect
    assert set(ts.CLIENTS_TESTED) == {"Claude", "VS Code", "Cursor", "Glama"}
    assert "%" not in md


@pytest.mark.parametrize("registration", ["", "1"])
def test_docs_docs_md_and_llms_full_carry_the_same_table(client, monkeypatch, registration):  # noqa: F811
    monkeypatch.setenv("KRUSGRAPH_CLIENT_REGISTRATION", registration)
    table = ts.overview_md(bool(registration))
    assert table in client.get("/docs.md").text
    assert table in client.get("/llms-full.txt").text
    html = client.get("/docs").text
    assert "Overview: tools, functions and clients" in html and "plan_sql_server" in html and "Claude Code (client)" in html
    assert ("cannot sign in to this server" in table) != bool(registration)


def test_the_server_instructions_take_their_status_from_the_same_source():
    from fabric_backend import server
    instructions = getattr(server.mcp, "instructions", None) or server.mcp._mcp_server.instructions
    assert ts.instructions_sentence() in instructions
