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
CLIENT_COLUMNS = ("MANDT", "RCLNT", "CLIENT")      # BUT000 and the CVI link tables name it CLIENT
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
        kind, target = r.get("kind", "key"), tables[r["target"]]
        if kind == "unique":                                             # VBAK.KNUMV: a unique column set the table declares
            if list(r["target_cols"]) not in [list(u) for u in target.get("unique_keys", [])]:
                out.append(f"{name}: the target columns are not a unique key {r['target']} declares (unique_keys)")
        elif kind == "valid_on":                                         # CSKS: the key without its valid-to column, plus a date
            v = r.get("valid_on") or {}
            # the key is the join columns, one end of the period (CSKS: DATBI, ADRC: DATE_FROM) and any target column a
            # filter fixes to one value or to blank (ADRC.NATION)
            fixed = [w["column"] for w in r.get("where", []) if w["side"] == "target" and (w.get("blank") or len(w.get("in", [])) == 1)]
            if not {"target_from", "target_to"} <= set(v) or not (v.get("source_date") or v.get("on") == "today"):
                out.append(f"{name}: valid_on needs target_from, target_to and a source_date or on: today")
            elif not any(sorted(list(r["target_cols"]) + [end] + fixed) == sorted(target["key"]) for end in (v["target_to"], v["target_from"])):
                out.append(f"{name}: the target columns, one end of the period and the fixed filters are not {r['target']}'s key")
        elif r["cardinality"] != "many-to-many" and r.get("apply") is not False:
            # a key join that is only listed may point elsewhere (a conditional link); an applied one never. A target-side
            # filter to one value completes the key: KONV.KAPPL+KSCHL -> T685 where T685.KVEWE = 'A'
            fixed = [w["column"] for w in r.get("where", []) if w["side"] == "target" and (w.get("blank") or len(w.get("in", [])) == 1)]
            if sorted(list(r["target_cols"]) + fixed) != sorted(target["key"]) or (not fixed and list(r["target_cols"]) != list(target["key"])):
                out.append(f"{name}: the target columns are not {r['target']}'s key")
        for w in r.get("where", []):
            if w.get("side") not in ("source", "target") or not (w.get("in") or w.get("blank")):
                out.append(f"{name}: a where entry needs side source or target and at least one value, or blank")
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
                lost.append((s, a) if not ha else (g, b))
        kind = r.get("kind", "key")
        valid = None
        if kind == "valid_on":                                            # the date and the period columns must be there too
            v = r["valid_on"]
            tf, tt = cols[g].get(v["target_from"]), cols[g].get(v["target_to"])
            need = [(g, v["target_from"], tf), (g, v["target_to"], tt)]
            valid = {"target_from": tf, "target_to": tt}
            if v.get("on") == "today":
                valid["on"] = "today"
            else:
                sd = cols[s].get(v["source_date"])
                need.append((s, v["source_date"], sd))
                valid["source_date"] = sd
            lost += [(t_, c_) for t_, c_, have in need if not have]
        where = []
        for w in r.get("where", []):                                       # the filter columns must be there too
            table = s if w["side"] == "source" else g
            have = cols[table].get(w["column"])
            if have:
                where.append({**w, "column": have})
            else:
                lost.append((table, w["column"]))
        info = {k: r[k] for k in ("cardinality", "role", "condition", "sources", "module") if k in r}
        info["kind"] = kind
        if valid:
            info["valid_on"] = valid
        if where:
            info["where"] = where
        if lost:
            for table in dict.fromkeys(x for x, _ in lost):
                missing_cols.append({"table": table, "columns": [c for x, c in lost if x == table],
                                     "relationship": f"{r['source']}.{'+'.join(r['source_cols'])} -> {r['target']}"})
            not_applied.append({"source": s, "target": g, "pack_source_cols": r["source_cols"],
                                "why": "columns missing: " + ", ".join(f"{x}.{c}" for x, c in lost), **info})
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


def amounts(m: Match) -> list[dict]:
    """Every amount the pack knows on a matched table, with its level and currency column. An amount on a table that
    others point at many-to-one (VBAK.NETWR for VBAP, VBAP.NETWR for VBEP) is repeated by a join with them."""
    p = load(m.pack)
    return [{"table": t, "column": a["column"], "level": a["level"], "currency": a["currency"]}
            for t, name in m.tables.items() for a in p["tables"][name].get("amounts", [])]


EXPORTS = ("none", "krusgraph", "dab", "extraction", "dbt")


def draft(plan, source_name: str = "sap", export: str = "none", variant: str | None = None) -> dict:
    """What the pack recognises in a plan's schema and what it lacks, read-only; optionally one export of the plan.
    The answer behind the sap_pack_draft tool."""
    from .infer import PlanInputError
    if export not in EXPORTS:
        raise PlanInputError(f"export: {export!r} is not one of {', '.join(EXPORTS)}")
    p = load("sap")
    if variant is not None and variant not in p["variants"]:
        raise PlanInputError(f"variant: {variant!r} is not one of {', '.join(p['variants'])}")
    m = match(plan.schema, "sap", variant)
    if m is None:
        near = [t.name for t in plan.schema if table_name(t.name) in p["tables"]]
        return {"summary": "no SAP tables recognised (the pack needs two or more of its tables with their key columns); the plan "
                           "is the name rules' alone" + (f". Names the pack knows but without their key columns: {', '.join(near)}" if near else ""),
                "pack_tables": sorted(p["tables"]), "modules": p["modules"]}
    srcs = lambda ids: [{"title": p["sources"][i]["title"], "url": p["sources"][i]["url"], "fetched": p["sources"][i]["fetched"]} for i in ids]
    tables = [{"table": t, "pack_table": n, "level": p["tables"][n]["level"], "en": p["tables"][n]["en"], "de": p["tables"][n]["de"],
               "key": m.keys[t], **({"note": p["tables"][n]["note"]} if p["tables"][n].get("note") else {}),
               "sources": srcs(p["tables"][n]["sources"])} for t, n in m.tables.items()]
    rels = [{"source": r["source"], "source_cols": r["source_cols"], "target": r["target"], "target_cols": r["target_cols"],
             "cardinality": r["cardinality"], "kind": r.get("kind", "key"), **({"valid_on": r["valid_on"]} if r.get("valid_on") else {}),
             **({"role": r["role"]} if r.get("role") else {}),
             **({"condition": r["condition"]} if r.get("condition") else {}), "sources": srcs(r["sources"])} for r in m.relationships]
    in_plan = {(r.source, tuple(c.lower() for c in r.source_cols), r.target): r.rule for r in plan.relationships}
    in_plan.update({(r.source, tuple(c.lower() for c in r.source_cols), r.target): f"{r.rule} ({r.kind}, plan.extended)" for r in plan.extended})
    for r in rels:
        r["in_plan"] = in_plan.get((r["source"], tuple(c.lower() for c in r["source_cols"]), r["target"]), "no (confirmed or keys override it)")
    out = {"summary": f"{len(m.tables)} SAP table(s) recognised, {len(rels)} pack relationship(s) apply, {len(m.not_applied)} listed "
                      f"but not applied, {len(m.missing_tables)} pack table(s) missing that would complete them",
           "status": "documented in public sources, not verified against data: run validate_plan with the same keys/confirmed",
           "variant_hint": m.variant_hint or "no table that only one variant has",
           "tables": tables, "relationships": rels, "not_applied": m.not_applied, "missing_tables": m.missing_tables,
           "missing_columns": m.missing_columns, "client_dropped": m.client_dropped,
           "amounts": amounts(m),
           "traps": [{"title": t["title"], "text": t["text"]} for t in p["traps"]],
           "next": "validate_plan checks keys and relationships against the rows; validate_plan's amount_levels names the header amounts a join repeats."}
    if export != "none":
        from . import exports
        if export == "krusgraph":
            out["export"] = exports.krusgraph_plan(plan)
        elif export == "dab":
            out["export"] = {"path": "dab-config.json", "config": exports.dab_config(plan)}
        elif export == "extraction":
            out["export"] = exports.extraction_list(plan, m)
        else:
            from . import dbt
            out["export"] = {"path": f"models/sources/{source_name}.yml", "yaml": dbt.schema_yml(plan, source_name, plan.schema.schema)}
    return out


# ------------------------------------------------------------------ verification against real rows (round n31) ------

def _pack_relationship(entry: dict, pack: dict) -> tuple[int, dict] | None:
    """The pack relationship a validate_plan entry checked: same tables by pack name, same columns (the client may have
    been dropped by the extract)."""
    src, tgt = table_name(entry["source"]), table_name(entry["target"])
    cols = {c.upper() for c in entry["columns"]}
    for i, r in enumerate(pack["relationships"]):
        if r["source"] != src or r["target"] != tgt:
            continue
        mine = set(r["source_cols"])
        if cols <= mine and mine - cols <= set(CLIENT_COLUMNS):
            return i, r
    return None


def verification(validation: dict, where: str, when: str, pack: str = "sap") -> dict:
    """A proposal per pack relationship from a saved validate_plan answer: verified (it held for every row with a value,
    and no row matched twice), review (orphans or rows that matched more than one target row: read its condition first),
    no evidence (no row had a value), or not checked (a pack relationship between the tables checked that the answer
    does not contain: listed only, or past max_items). Proposals only; write_verified records the verified ones.
    `where` says what was checked, without names of a real company (for example "SAP S/4HANA sandbox, synthetic data");
    `when` is the date of the run."""
    p = load(pack)
    rows, seen = [], set()
    for e in validation.get("relationships", []):
        if e.get("rule") != RULE:
            continue
        found = _pack_relationship(e, p)
        if found is None:
            continue
        i, r = found
        seen.add(i)
        n, orphans, several = int(e.get("rows_with_value") or 0), int(e.get("orphans") or 0), int(e.get("several") or 0)
        if n == 0:
            proposal, why = "no evidence", "no row had a value in the reference columns"
        elif orphans or several:
            proposal = "review"
            why = "; ".join(x for x in (f"{orphans} of {n} rows point at nothing" if orphans else "",
                                        f"{several} rows match more than one target row" if several else "") if x)
            if r.get("condition"):
                why += f". The pack's condition: {r['condition']}"
        else:
            proposal, why = "verified", f"held for all {n} rows with a value"
        rows.append({"module": r["module"], "index": i, "source": r["source"], "source_cols": r["source_cols"], "target": r["target"],
                     "kind": r.get("kind", "key"), "proposal": proposal, "why": why,
                     "evidence": {"rows_with_value": n, "orphans": orphans, "several": several}})
    checked = {table_name(k["table"]) for k in validation.get("keys", [])}
    for i, r in enumerate(p["relationships"]):
        if i not in seen and r["source"] in checked and r["target"] in checked:
            rows.append({"module": r["module"], "index": i, "source": r["source"], "source_cols": r["source_cols"], "target": r["target"],
                         "kind": r.get("kind", "key"), "proposal": "not checked",
                         "why": "listed only, not applied" if r.get("apply") is False else "not in the answer (raise max_items, or the columns were missing)"})
    counts = {k: sum(1 for x in rows if x["proposal"] == k) for k in ("verified", "review", "no evidence", "not checked")}
    return {"where": where, "when": when, "counts": counts, "relationships": rows,
            "summary": ", ".join(f"{v} {k}" for k, v in counts.items()),
            "note": "Proposals from counts, not proof of meaning: a relationship that held on one system can fail on another. "
                    "Record only runs on systems you may describe, and describe them without naming a company."}


def write_verified(report: dict, pack: str = "sap") -> list[str]:
    """Add {where, when, rows_with_value} to the `verified` list of every relationship the report proposes as verified,
    in the pack's own files (one line per relationship, as they are written). Returns what was changed."""
    from .sap_demo import DEMO_WHERE
    if DEMO_WHERE in report["where"].lower() or "synthetic" in report["where"].lower():
        raise ValueError("a run on synthetic rows proves nothing about the pack (the rows are written from it); "
                         "record only runs on a real SAP system you may describe")
    changed = []
    p = load(pack)
    by_module: dict[str, list[dict]] = {}
    for x in report["relationships"]:
        if x["proposal"] == "verified":
            by_module.setdefault(x["module"], []).append(x)
    for module, items in by_module.items():
        path = PACKS / pack / f"{module}.json"
        lines = path.read_text(encoding="utf-8").split("\n")
        for x in items:
            r = {k: v for k, v in p["relationships"][x["index"]].items() if k != "module"}
            for n, line in enumerate(lines):
                st = line.strip()
                if not st.startswith("{") or '"source_cols"' not in st:
                    continue
                obj = json.loads(st.rstrip(","))
                if (obj["source"], obj["source_cols"], obj["target"], obj["target_cols"]) != (r["source"], r["source_cols"], r["target"], r["target_cols"]):
                    continue
                entry = {"where": report["where"], "when": report["when"], "rows_with_value": x["evidence"]["rows_with_value"]}
                if entry not in obj.get("verified", []):
                    obj["verified"] = obj.get("verified", []) + [entry]
                    srcs = obj.pop("sources")
                    obj["sources"] = srcs                                       # sources stay last on the line
                    indent = line[:len(line) - len(line.lstrip())]
                    lines[n] = indent + json.dumps(obj, ensure_ascii=False) + ("," if st.endswith(",") else "")
                    changed.append(f"{module}: {r['source']}.{'+'.join(r['source_cols'])} -> {r['target']}")
                break
        text = "\n".join(lines)
        json.loads(text)
        path.write_text(text, encoding="utf-8")
    _load.cache_clear()
    return changed


def verification_markdown(report: dict) -> str:
    out = [f"# SAP pack verification: {report['where']}, {report['when']}", "", report["summary"], "", report["note"], "",
           "| Proposal | Relationship | Kind | Rows | Orphans | Several | Why |", "| --- | --- | --- | --- | --- | --- | --- |"]
    order = {"review": 0, "verified": 1, "no evidence": 2, "not checked": 3}
    for x in sorted(report["relationships"], key=lambda x: (order[x["proposal"]], x["module"], x["source"])):
        ev = x.get("evidence", {})
        out.append(f"| {x['proposal']} | {x['source']}.{'+'.join(x['source_cols'])} → {x['target']} | {x['kind']} | "
                   f"{ev.get('rows_with_value', '')} | {ev.get('orphans', '')} | {ev.get('several', '')} | {x['why'].replace('|', '/')} |")
    return "\n".join(out) + "\n"
