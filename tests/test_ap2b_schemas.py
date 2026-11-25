"""Round AP2b (finding 2): the server's rule for Krusgraph's own schemas (workload_api.krusgraph_schema) is the Model
editor's (krusgraphSchema and OWN_WORDS in workload/Workload/app/items/ModelItem/sourceWords.ts, round W1): the same two
patterns and the same words, read here out of the TypeScript file, so the two cannot drift apart unnoticed; and the
editor's own test cases give the same answers."""
from __future__ import annotations

import re
from pathlib import Path

from fabric_backend import workload_api as W

TS = Path(__file__).resolve().parent.parent / "workload/Workload/app/items/ModelItem/sourceWords.ts"


def _function(src: str, name: str) -> str:
    start = src.index(f"export function {name}(")
    return src[start:src.index("\n}\n", start)]


def test_the_patterns_and_words_are_the_editors():
    src = TS.read_text(encoding="utf-8")
    body = _function(src, "krusgraphSchema")
    regexes = re.findall(r"/(\^[^/]+\$)/", body)
    assert regexes == [W.OWN_SCHEMA_WRITTEN.pattern, W.OWN_SCHEMA_LOOKS.pattern]
    assert 'n === "krusgraph"' in body and 'n === "silver" || n === "gold"' in body
    words = dict(re.findall(r'(written|looks): "([^"]+)"', src[src.index("export const OWN_WORDS"):]))
    assert words == W.OWN_SCHEMA_WORDS


def test_the_editors_cases():
    for n in ("krusgraph", "krusgraph_quarantine", "krusgraph_analysis"):
        assert W.krusgraph_schema(n) == "written", n
    for n in ("silver", "GOLD", "sap_silver", "sap_gold"):
        assert W.krusgraph_schema(n) == "looks", n
    for n in ("dbo", "shop", "sap", "silverware", "golden", "silver_2025", "goldsmith", "krusgraphx", "", None):
        assert W.krusgraph_schema(n) is None, n
