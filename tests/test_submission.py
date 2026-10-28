"""deploy/SUBMISSION.md says what the portal's Tools step will read from the server; keep it equal to the server."""
import asyncio
import re
from pathlib import Path

from fabric_backend import server

TEXT = (Path(__file__).resolve().parent.parent / "deploy" / "SUBMISSION.md").read_text(encoding="utf-8")


def _tools():
    return asyncio.run(server.mcp.list_tools())


def _tools_answer() -> str:
    return TEXT[TEXT.index("**2 Tools**"):TEXT.index("**3 Listing**")]


def test_counts_match_the_server():
    tools = _tools()
    write = [t for t in tools if not t.annotations.read_only_hint]
    m = re.search(r"(\d+) tools, (\d+) read-only, (\d+) write", _tools_answer())
    assert m and tuple(map(int, m.groups())) == (len(tools), len(tools) - len(write), len(write))


def test_write_tools_are_named():
    named = set(re.findall(r"`(create_\w+)`", _tools_answer()))
    assert named == {t.name for t in _tools() if not t.annotations.read_only_hint}


def test_every_tool_has_a_title_and_a_hint():
    for t in _tools():
        a = t.annotations
        assert a and a.title, t.name
        assert a.read_only_hint or a.destructive_hint is not None, t.name
