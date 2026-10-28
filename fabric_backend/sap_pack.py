"""Knowledge packs: the keys and relationships of a known source system, read from declarative files.

General naming rules cannot read SAP: `VBAP.VBELN` names the order it belongs to, `LIPS.VBELN` a delivery and
`VBRP.VBELN` an invoice, every key starts with the client `MANDT`, and the names are German abbreviations. A pack
says it outright, per table and per relationship, with the public source it rests on.

The files are in `fabric_backend/packs/<pack>/<module>.json` and follow `packs/pack.schema.json`. They describe
tables, not a tool: the same pack serves a Fabric mirror, a Databricks catalog, a Data API builder config or a
pipeline's table list (exports.py). Nothing here connects to anything.

    load("sap")                    -> the merged pack (all modules)
    problems(pack)                 -> what is inconsistent in it (the test runs this on every file)
    match(schema, "sap")           -> which tables of a schema the pack knows, their keys and the relationships it can
                                      apply, with what is missing; None when fewer than two tables match

A table matches on its name without case, schema or a leading `sap_`/`raw_`/`stg_`/`bronze_` word (`VBAK`, `vbak`,
`sap_vbak`, `bronze.SAP_VBAK`), and only when its key columns are there. When an extract has dropped the client
column, the client is left out of keys and relationships on both sides, and the match says so.
A pack is a suggestion with a source, not evidence: validate_plan checks its relationships against the rows.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PACKS = Path(__file__).parent / "packs"
RULE = "SAP pack"
CLIENT_COLUMNS = ("MANDT", "RCLNT")
_LEADING = ("sap", "raw", "stg", "src", "bronze", "landing", "mirror", "mirrored", "ext", "extract")


def available() -> list[str]:
    return sorted(p.name for p in PACKS.iterdir() if p.is_dir())


@lru_cache(maxsize=None)
def _load(pack: str) -> str:
    files = sorted((PACKS / pack).glob("*.json"))
    if not files:
        raise KeyError(f"no pack named {pack!r}; available: {', '.join(available())}")
    merged: dict = {"pack": pack, "modules": [], "variants": {}, "sources": {}, "tables": {}, "relationships": [], "traps": []}
    for f in files:
        m = json.loads(f.read_text(encoding="utf-8"))
        merged["modules"].append({"module": m["module"], "title": m["title"], "status": m["status"], "file": f"packs/{pack}/{f.name}"})
        merged["rule"] = m["rule"]
        merged["variants"].update(m["variants"])
        for sid, s in m["sources"].items():
            merged["sources"][sid] = s
        for t in m["tables"]:
            merged["tables"][t["name"]] = {**t, "module": m["module"]}
        merged["relationships"] += [{**r, "module": m["module"]} for r in m["relationships"]]
        merged["traps"] += [{**t, "module": m["module"]} for t in m.get("traps", [])]
    return json.dumps(merged)


def load(pack: str = "sap") -> dict:
    """The pack with all its modules merged: tables by name, relationships, sources, traps."""
    return json.loads(_load(pack))


def problems(pack: dict) -> list[str]:
    """Inconsistencies the JSON schema cannot see: unknown sources, relationships to tables or columns the pack does
    not describe, column lists of different length, a target that is not the target's key."""
    out = []
    tables = pack["tables"]
    sources = pack["sources"]
    for t in tables.values():
        for s in t["sources"]:
            if s not in sources:
                out.append(f"{t['name']}: unknown source {s!r}")
        for v in t.get("variants", []):
            if v not in pack["variants"]:
                out.append(f"{t['name']}: unknown variant {v!r}")
        if len(set(t["key"])) != len(t["key"]):
            out.append(f"{t['name']}: a key column is repeated")
    for r in pack["relationships"]:
        name = f"{r['source']}.{'+'.join(r['source_cols'])} -> {r['target']}"
        for s in r["sources"]:
            if s not in sources:
                out.append(f"{name}: unknown source {s!r}")
        if r["source"] not in tables or r["target"] not in tables:
            out.append(f"{name}: a table the pack does not describe")
            continue
        if len(r["source_cols"]) != len(r["target_cols"]):
            out.append(f"{name}: {len(r['source_cols'])} source column(s) against {len(r['target_cols'])} target column(s)")
        if r["cardinality"] != "many-to-many" and list(r["target_cols"]) != list(tables[r["target"]]["key"]):
            out.append(f"{name}: the target columns are not {r['target']}'s key")
        for v in r.get("variants", []):
            if v not in pack["variants"]:
                out.append(f"{name}: unknown variant {v!r}")
    for tr in pack["traps"]:
        for s in tr["sources"]:
            if s not in sources:
                out.append(f"trap {tr['id']}: unknown source {s!r}")
    return out


def table_name(name: str) -> str:
    """The name a pack would know a table by: `bronze.SAP_VBAK` -> `VBAK`."""
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name.split(".")[-1]) if w]
    while len(words) > 1 and words[0].lower() in _LEADING:
        words = words[1:]
    return "_".join(words).upper()


@dataclass
class Match:
    pack: str
    tables: dict[str, str]                                  # schema table -> pack table
    keys: dict[str, list[str]]                              # schema table -> key columns, in the schema's spelling
    relationships: list[dict]                               # applied: source, source_cols, target, target_cols (schema spelling) + pack fields
    not_applied: list[dict] = field(default_factory=list)   # pack relationships between matched tables that are not applied, with why
    missing_tables: list[str] = field(default_factory=list) # pack tables a relationship of a matched table needs and the schema lacks
    missing_columns: list[dict] = field(default_factory=list)
    client_dropped: list[str] = field(default_factory=list) # matched tables without their client column
    variant_hint: str = ""
    unmatched_keyless: list[str] = field(default_factory=list)  # names a pack knows whose key columns are not all there

    def source_of(self, ids: list[str]) -> list[dict]:
        pack = load(self.pack)
        return [{"id": i, **{k: pack["sources"][i][k] for k in ("title", "url", "fetched")}} for i in ids]


def _cols(table) -> dict[str, str]:
    return {c.upper(): c for c in table.column_names}


def match(schema, pack: str = "sap", variant: str | None = None) -> Match | None:
    """The pack's view of a schema; None when fewer than two of its tables are recognised (then nothing changes)."""
    p = load(pack)
    found: dict[str, str] = {}
    cols: dict[str, dict[str, str]] = {}
    keys: dict[str, list[str]] = {}
    dropped: list[str] = []
    keyless: list[str] = []
    taken: set[str] = set()
    for t in schema:
        name = table_name(t.name)
        pt = p["tables"].get(name)
        if pt is None or name in taken:
            continue
        if variant and pt.get("variants") and variant not in pt["variants"]:
            continue
        have = _cols(t)
        key = [c for c in pt["key"] if c in have or c not in CLIENT_COLUMNS]
        if not all(c in have for c in key) or len(key) == 0:
            keyless.append(t.name)
            continue
        taken.add(name)
        found[t.name] = name
        cols[t.name] = have
        if len(key) < len(pt["key"]):
            dropped.append(t.name)
        keys[t.name] = [have[c] for c in key]
    if len(found) < 2:
        return None
    by_pack = {v: k for k, v in found.items()}
    applied, not_applied, missing_cols = [], [], []
    missing_tables: set[str] = set()
    for r in p["relationships"]:
        s, g = by_pack.get(r["source"]), by_pack.get(r["target"])
        if s is None and g is None:
            continue
        if s is None or g is None:
            missing_tables.add(r["target"] if s else r["source"])
            continue
        if variant and r.get("variants") and variant not in r["variants"]:
            continue
        pairs = []
        lost = []
        for a, b in zip(r["source_cols"], r["target_cols"]):
            ha, hb = cols[s].get(a), cols[g].get(b)
            if ha and hb:
                pairs.append((ha, hb))
            elif a in CLIENT_COLUMNS or b in CLIENT_COLUMNS:
                continue                                                  # the client dropped on one side: dropped on both
            else:
                lost.append(a if not ha else b)
        info = {k: r[k] for k in ("cardinality", "role", "condition", "sources", "module") if k in r}
        if lost:
            missing_cols.append({"table": s if any(x not in cols[g] for x in lost) else g, "columns": lost,
                                 "relationship": f"{r['source']}.{'+'.join(r['source_cols'])} -> {r['target']}"})
            not_applied.append({"source": s, "target": g, "pack_source_cols": r["source_cols"], "why": "columns missing: " + ", ".join(lost), **info})
            continue
        rel = {"source": s, "source_cols": [a for a, _ in pairs], "target": g, "target_cols": [b for _, b in pairs], **info}
        if r.get("apply") is False:
            not_applied.append({**rel, "why": "conditional: " + r.get("condition", "holds for some rows only") + " Listed, not applied; confirm it if your rows are of that kind."})
            continue
        applied.append(rel)
    hint, seen = "", variant
    present = set(found.values())
    for v in p["variants"]:
        only = [n for n, t in p["tables"].items() if t.get("variants") == [v] and n in present]
        if only:
            hint, seen = f"{v} (tables only that variant has: {', '.join(sorted(only))})", seen or v
    if seen:                                                              # BSEG is not missing from an S/4HANA schema
        missing_tables = {n for n in missing_tables if not p["tables"][n].get("variants") or seen in p["tables"][n]["variants"]}
    return Match(pack, found, keys, applied, not_applied, sorted(missing_tables), missing_cols, dropped, hint, keyless)


def table_info(pack_table: str, pack: str = "sap") -> dict:
    return load(pack)["tables"][pack_table]


def header_amounts(m: Match) -> list[tuple[str, str]]:
    """(schema table, column) for every amount the pack puts on a header: what a join with the items repeats."""
    p = load(m.pack)
    out = []
    for t, name in m.tables.items():
        for a in p["tables"][name].get("amounts", []):
            if a["level"] == "header":
                out.append((t, a["column"]))
    return out
