"""Compare an ontology's live definition (Get Definition) with what Krusgraph writes, part by part.

B2, 15 November 2026 (backlog B-01). Microsoft's Learn says the old ontology experience, whose definition is entity-type
JSON (`definition.json`, `EntityTypes/{id}/definition.json`), retires on 31 January 2027; the new experience's
definition is TMDL (`.platform` with config version 2.0, `database.tmdl`, `model.tmdl`, `entities/*.tmdl`, ...).
Krusgraph writes the TMDL format only (fabric_backend/ontology.py, ontology_parts). This script takes the answer of
Get Definition for an ontology Krusgraph created and says which format Fabric holds it in and how each part compares
with ontology_parts for the same plan. Nothing here calls Fabric: the maintainer makes the call (docs/LIVE-TEST.md,
"Ontology format check") and passes the saved answer.

    python tools/ontology_compare.py shop_ontology.json                 # the shop sample's plan, schema 'shop'
    python tools/ontology_compare.py answer.json --name shop_ontology --schema shop --json

The workspace, item and endpoint that ontology_parts needs are read from the live tables' annotations (ONT_WorkspaceId,
ONT_ItemId, ...), which Krusgraph writes; --workspace-id and friends override them.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fabric_backend import ontology, seed  # noqa: E402
from fabric_backend.infer import plan as _plan  # noqa: E402

OLD = "old (entity-type JSON; retires 31 January 2027)"
NEW = "TMDL (new experience)"
_ANNOTATION = re.compile(r"^\s*annotation (ONT_\w+) = (.*)$", re.M)
_SKIP_LINE = re.compile(r"^\s*lineageTag:")      # Fabric may keep or reassign lineage tags; they are not compared


def decode(answer: dict) -> dict[str, str]:
    """{path: text} from a Get Definition answer ({"definition": {"parts": [...]}}) or a bare parts list."""
    parts = answer.get("definition", answer).get("parts") if isinstance(answer, dict) else answer
    if not isinstance(parts, list):
        raise ValueError("not a Get Definition answer: no definition.parts")
    out = {}
    for p in parts:
        raw = base64.b64decode(p.get("payload", ""))
        out[p["path"]] = raw.decode("utf-8-sig", errors="replace")
    return out


def format_of(parts: dict[str, str]) -> str:
    paths = set(parts)
    if "definition.json" in paths or any(p.startswith("EntityTypes/") for p in paths):
        return OLD
    platform = parts.get(".platform", "")
    try:
        version = json.loads(platform).get("config", {}).get("version") if platform.strip() else None
    except json.JSONDecodeError:
        version = None
    if any(p.endswith(".tmdl") for p in paths) and version == "2.0":
        return NEW
    return f"unknown (.platform config version {version!r})"


def annotations(parts: dict[str, str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for path, text in parts.items():
        if path.startswith("tables/"):
            for k, v in _ANNOTATION.findall(text):
                found.setdefault(k, v.strip())
    return found


def _norm(text: str) -> list[str]:
    return [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")
            if line.strip() and not _SKIP_LINE.match(line)]


def compare(live: dict[str, str], ours: dict[str, str]) -> dict:
    """Paths only on one side, and per shared part 'same' or the number of lines that differ (lineage tags, line ends
    and blank lines ignored)."""
    shared = sorted(set(live) & set(ours))
    parts = {}
    for p in shared:
        a, b = _norm(live[p]), _norm(ours[p])
        if p == ".platform":
            try:
                a = [json.dumps({k: v for k, v in json.loads(live[p]).items() if k != "config"}, sort_keys=True)]
                b = [json.dumps({k: v for k, v in json.loads(ours[p]).items() if k != "config"}, sort_keys=True)]
            except json.JSONDecodeError:
                pass
        diff = len(set(a) ^ set(b))
        parts[p] = "same" if a == b else ("same lines, other order" if sorted(a) == sorted(b) else f"{diff} lines differ")
    return {"only_live": sorted(set(live) - set(ours)), "only_ours": sorted(set(ours) - set(live)), "parts": parts}


def report(answer: dict, name: str = "shop_ontology", schema: str = "shop", **override) -> dict:
    live = decode(answer)
    fmt = format_of(live)
    out = {"format": fmt, "parts_live": len(live)}
    if fmt != NEW:
        out["verdict"] = ("Fabric holds this ontology in the old format: re-create it from Krusgraph before 31 January "
                          "2027" if fmt == OLD else "format not recognised; compare by hand")
        return out
    ann = annotations(live)
    args = {"workspace_id": override.get("workspace_id") or ann.get("ONT_WorkspaceId", ""),
            "item_id": override.get("item_id") or ann.get("ONT_ItemId", ""),
            "item_name": override.get("item_name") or ann.get("ONT_ItemName", ""),
            "item_kind": override.get("item_kind") or ann.get("ONT_ItemKind", "Lakehouse"),
            "sql_endpoint": override.get("sql_endpoint") or ann.get("ONT_SqlEndpoint", "")}
    if not (args["workspace_id"] and args["item_id"] and args["item_name"]):
        out["verdict"] = "the live tables carry no ONT_ annotations; pass --workspace-id, --item-id and --item-name"
        return out
    ours = ontology.ontology_parts(_plan(seed.schema(schema), None, None), name, schema=schema, **args)
    out.update(compare(live, ours))
    out["entity_paths_unqualified"] = all("#" not in p for p in live if p.startswith("entities/"))
    same = not out["only_live"] and not out["only_ours"] and all(v == "same" for v in out["parts"].values())
    out["verdict"] = ("TMDL, and every part as Krusgraph writes it" if same else
                      "TMDL; the differences above are Fabric's normal form or a change to take over after a live try")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("answer", help="the saved Get Definition answer (JSON)")
    ap.add_argument("--name", default="shop_ontology")
    ap.add_argument("--schema", default="shop", help="the seed schema the ontology was planned from")
    for k in ("workspace-id", "item-id", "item-name", "item-kind", "sql-endpoint"):
        ap.add_argument(f"--{k}")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    r = report(json.loads(Path(a.answer).read_text(encoding="utf-8-sig")), a.name, a.schema,
               **{k: getattr(a, k) for k in ("workspace_id", "item_id", "item_name", "item_kind", "sql_endpoint")})
    if a.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"format: {r['format']} ({r['parts_live']} parts)")
        for k in ("only_live", "only_ours"):
            for p in r.get(k, []):
                print(f"  {k.replace('_', ' ')}: {p}")
        for p, v in r.get("parts", {}).items():
            print(f"  {p}: {v}")
        print(r["verdict"])
    return 0 if r["format"] == NEW else 1


if __name__ == "__main__":
    sys.exit(main())
