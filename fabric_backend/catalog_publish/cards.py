"""CA1: the product card of each data product Krusgraph has proven, from the plan, domain_draft's proposal and
validate_plan's counts. A card holds what a catalog entry needs and nothing Krusgraph cannot back:

- a plain description (what it is, its tables, and one dated line of what was counted), at most 256 characters, the
  limit of Fabric's Update Item description;
- the owner the person named, or "not chosen yet" (Fabric has no owner field to write: the card carries it to the
  handover files and the ODCS contract);
- the proposed Fabric domain (a proposal: creating domains and assigning workspaces is for a Fabric or domain admin);
- tags: stable facts only (`Krusgraph`, the product's name), never a health word: a tag carries no date;
- the ODCS v3.2.0 contract domain_draft writes for the same grouping;
- glossary terms: one per entity of the ontology (entity_name of each table), defined from its key and its links;
- the row-check evidence ("6 of 6 keys unique, 0 orphan rows, checked 17 Nov 2026") and the data quality rules that
  follow from what was proven (quality.py).

Table, entity, rule and column names and counts only: never a row value."""
from __future__ import annotations

import re
from datetime import date

from .. import domains as _domains
from ..ontology import entity_name
from . import quality as _quality

DESCRIPTION_MAX = 256           # Items - Update Item: "Maximum length is 256 characters."
TAG_MAX = 40                    # Tags: a tag's display name is at most 40 characters
PROVENANCE_TAG = "Krusgraph"


def words(entity: str) -> str:
    """`OrderItems` -> `Order items`: the term as a person reads it."""
    parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", entity) or [entity]
    text = " ".join(p.lower() if i else p[:1].upper() + p[1:].lower() for i, p in enumerate(parts))
    return text


def day_words(day: str | None) -> str:
    """`2026-11-17` -> `17 Nov 2026`; anything else as it is."""
    try:
        d = date.fromisoformat(str(day))
    except (TypeError, ValueError):
        return str(day or "")
    return f"{d.day} {d.strftime('%b')} {d.year}"


def evidence(validation: dict | None, tables: list[str], checked_on: str | None) -> dict:
    """What validate_plan counted for these tables: keys unique of keys counted, orphan rows over the relationships
    counted (both ends inside the product), and the day. Without counts: says so, and claims nothing."""
    if not validation:
        return {"counted": False, "line": "keys and links not yet checked against the rows"}
    mine = {t.lower() for t in tables}
    keys = [k for k in validation.get("keys", []) if k.get("table", "").lower() in mine and isinstance(k.get("rows"), int)]
    rels = [r for r in validation.get("relationships", []) if r.get("source", "").lower() in mine
            and r.get("target", "").lower() in mine and isinstance(r.get("orphans"), int)]
    unique = sum(1 for k in keys if str(k.get("verdict", "")).startswith("unique"))
    orphans = sum(r["orphans"] for r in rels)
    parts = []
    if keys:
        parts.append(f"{unique} of {len(keys)} keys unique")
    if rels:
        parts.append(f"{orphans} orphan row{'' if orphans == 1 else 's'} over {len(rels)} link{'' if len(rels) == 1 else 's'}")
    when = day_words(checked_on) if checked_on else ""
    line = (", ".join(parts) or "nothing counted for these tables") + (f", checked {when}" if when and parts else "")
    return {"counted": bool(parts), "keys_counted": len(keys), "keys_unique": unique, "links_counted": len(rels),
            "orphan_rows": orphans, "checked_on": checked_on, "line": line}


def _fit(*versions: str) -> str:
    for v in versions:
        if len(v) <= DESCRIPTION_MAX:
            return v
    v = versions[-1]
    return v[:DESCRIPTION_MAX - 1].rsplit(" ", 1)[0] + "…"


def description(name: str, tables: list[str], schema: str, ev: dict, owner: str | None) -> str:
    ents = [words(entity_name(t)) for t in tables]
    who = f" Owner: {owner}." if owner else ""
    head = f"Data product {name} ({schema}):"
    tail = f" Checked by Krusgraph: {ev['line']}.{who}" if ev["counted"] else f" Krusgraph: {ev['line']}.{who}"
    return _fit(f"{head} {', '.join(ents)}.{tail}", f"{head} {len(tables)} tables.{tail}", f"{head}{tail}")


def tags(name: str) -> list[str]:
    return list(dict.fromkeys([PROVENANCE_TAG, name[:TAG_MAX].rstrip()]))


def glossary(p, tables: list[str], schema: str) -> list[dict]:
    """One term per entity: its name as a person reads it, a definition from its key and its links inside the plan,
    and where it lives. A definition from structure only: the business meaning is for the steward to add."""
    rels = list(p.relationships)
    out = []
    for t in tables:
        cols, rule = p.keys.get(t, ([], None))
        ent = entity_name(t)
        links = sorted({words(entity_name(r.target)) for r in rels if r.source == t and r.target != t})
        used_by = sorted({words(entity_name(r.source)) for r in rels if r.target == t and r.source != t})
        bits = [f"One row of {schema}.{t}"]
        bits.append(f"identified by {' + '.join(cols)} (rule {p.label(rule)})" if cols else "no key found")
        if links:
            bits.append("refers to " + ", ".join(links))
        if used_by:
            bits.append("referred to by " + ", ".join(used_by))
        out.append({"term": words(ent), "entity": ent, "table": f"{schema}.{t}",
                    "definition": "; ".join(bits) + ".", "status": "draft",
                    "note": "structure only: the business meaning is the steward's to write"})
    return out


def cards(p, schema: str, source: str = "", validation: dict | None = None, checked_on: str | None = None,
          owners: dict | None = None, names: dict | None = None) -> dict:
    """{"products": [card], "unassigned": [...]}: one card per grouping domain_draft proposes. `owners` and `names`
    map a product's slug to the owner and the name the person chose."""
    owners, names = owners or {}, names or {}
    d = _domains.draft(p, schema, source, validation)
    out = []
    for dom in d["domains"]:
        name = (names.get(dom["slug"]) or dom["name"]).strip()
        owner = (owners.get(dom["slug"]) or "").strip() or None
        ev = evidence(validation, dom["tables"], checked_on)
        out.append({
            "name": name, "slug": dom["slug"], "tables": dom["tables"],
            "description": description(name, dom["tables"], schema, ev, owner),
            "owner": owner or "not chosen yet",
            "domain": {"proposed": dom["name"], "why": dom["name_reason"],
                       "note": "a proposal: a Fabric or domain admin creates the domain and assigns the workspace"},
            "tags": tags(name),
            "contract": {"format": f"ODCS {_domains.ODCS_VERSION}", "status": "draft",
                         "file": f"contracts/{dom['slug']}.odcs.yaml", "yaml": d["contracts"][dom["slug"]]},
            "glossary": glossary(p, dom["tables"], schema),
            "evidence": ev,
            "quality_rules": _quality.rules(p, dom["tables"], schema, validation, checked_on),
        })
    return {"products": out, "unassigned": d["unassigned"], "interfaces": d["interfaces"]}
