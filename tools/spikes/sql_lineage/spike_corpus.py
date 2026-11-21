"""Corpus loader for the SQL-lineage spike (throwaway; see README.md). Not part of the server.

Each corpus/*.sql file starts with `-- key: value` header lines:
    -- dialect: tsql | spark
    -- expected_joins: A.X = B.Y | ...          (unordered pairs of base TABLE.COLUMN; "(none)" for none)
    -- expected_lineage: out <- T.C, T.D | ...    (per output column, the set of base TABLE.COLUMN; "(none)" = literal)
The SQL itself is the whole file, header comments included (both parsers must cope with comments).
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
RESULTS = HERE / "results"


def norm(table_col: str) -> str:
    """'lh.dbo.VBAK.netwr' -> 'VBAK.NETWR': last table part and column, upper case (all demo names are case-insensitive)."""
    parts = table_col.replace("`", "").replace("[", "").replace("]", "").replace('"', "").split(".")
    return f"{parts[-2]}.{parts[-1]}".upper()


def pair(a: str, b: str) -> str:
    """An unordered join pair as one canonical string: 'A.X = B.Y' with the two sides sorted."""
    x, y = sorted((norm(a), norm(b)))
    return f"{x} = {y}"


def _header(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("-- "):
            break
        key, _, value = line[3:].partition(":")
        out[key.strip()] = value.strip()
    return out


def load() -> list[dict]:
    items = []
    for f in sorted(CORPUS.glob("*.sql")):
        text = f.read_text(encoding="utf-8")
        h = _header(text)
        joins = set()
        if h.get("expected_joins", "(none)") != "(none)":
            for p in h["expected_joins"].split("|"):
                a, b = (s.strip() for s in p.split("="))
                joins.add(pair(a, b))
        lineage: dict[str, list[str]] = {}
        if h.get("expected_lineage", "(none)") != "(none)":
            for p in h["expected_lineage"].split("|"):
                out, _, src = p.partition("<-")
                srcs = src.strip()
                lineage[out.strip().upper()] = [] if srcs == "(none)" else sorted({norm(s.strip()) for s in srcs.split(",")})
        items.append({"id": f.stem, "file": f"corpus/{f.name}", "dialect": h["dialect"], "sql": text,
                      "expected_joins": sorted(joins), "expected_lineage": lineage})
    return items


def demo_schema() -> dict[str, dict[str, str]]:
    """{TABLE: {COLUMN: type}} from the repo's synthetic SAP and Salesforce demos, written to schema.json for the JS runner."""
    import sys
    sys.path.insert(0, str(HERE.parents[2]))
    from fabric_backend import salesforce_demo, sap_demo
    schema: dict[str, dict[str, str]] = {}
    for mod in (sap_demo, salesforce_demo):
        for name, (cols, types, _rows) in mod.tables().items():
            schema[name] = dict(zip(cols, types))
    return schema


def write_json(path: Path, data) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
