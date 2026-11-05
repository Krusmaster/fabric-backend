"""The tool counts written in prose match the tools the hosted server registers (round n99)."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fabric_backend import server

ROOT = Path(__file__).resolve().parents[1]
WORDS = {30: "thirty", 31: "thirty-one", 32: "thirty-two", 33: "thirty-three", 34: "thirty-four", 35: "thirty-five",
         36: "thirty-six", 37: "thirty-seven", 38: "thirty-eight", 39: "thirty-nine", 40: "forty", 41: "forty-one",
         42: "forty-two", 43: "forty-three", 44: "forty-four", 45: "forty-five"}
COUNT = re.compile(r"\b(thirty(?:-\w+)?|forty(?:-\w+)?) tools\b|^Tools \([^)]*\): (thirty(?:-\w+)?|forty(?:-\w+)?)\b",
                   re.IGNORECASE | re.MULTILINE)


def _registered() -> list[str]:
    return sorted(t.name for t in asyncio.run(server.mcp.list_tools()))


def _counts(text: str) -> list[str]:
    return [(m.group(1) or m.group(2)).lower() for m in COUNT.finditer(text)]


def test_the_discovery_text_states_the_registered_count_and_names_every_tool():
    names = _registered()
    text = (ROOT / "fabric_backend" / "discovery.py").read_text(encoding="utf-8")
    found = _counts(text)
    assert found and set(found) == {WORDS[len(names)]}, (found, len(names))
    missing = [n for n in names if f"`{n}`" not in text]
    assert not missing, missing


def test_the_counts_in_readme_and_server_docstring_match():
    want = WORDS[len(_registered())]
    for rel in ("README.md", "fabric_backend/server.py"):
        found = _counts((ROOT / rel).read_text(encoding="utf-8"))
        assert found and set(found) == {want}, (rel, found)
