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
    """`2026-11-17` -> `17 Nov 2026`; `2026-11-14T14:54Z` -> `2026-11-14 14:54 UTC` (WB10: the time of the row check,
    written as the editor's Thinker line writes it, nextSteps.ts proofLine); anything else as it is."""
    from datetime import datetime, timezone
    text = str(day or "")
    if "T" in text:
        try:
            t = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
        t = t.astimezone(timezone.utc) if t.tzinfo else t
        return t.strftime("%Y-%m-%d %H:%M UTC")
    try:
        d = date.fromisoformat(text)
    except (TypeError, ValueError):
        return text
    return f"{d.day} {d.strftime('%b')} {d.year}"


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def counted_keys(validation: dict | None) -> list[dict]:
    """WB10: the keys the check counted (rows > 0), the same set the editor's Thinker line counts (review.json's passed
    and failed keys). The one source of every key count on the page."""
    return [k for k in (validation or {}).get("keys", []) if isinstance(k.get("rows"), int) and k["rows"] > 0]


def counted_links(validation: dict | None) -> list[dict]:
    """WB10: the links the check counted (rows with a value > 0), as the Thinker line counts them."""
    return [r for r in (validation or {}).get("relationships", []) if isinstance(r.get("orphans"), int)
            and (r.get("rows_with_value") is None or r.get("rows_with_value", 0) > 0)]


def _unique(k: dict) -> bool:
    return k.get("status") == "passed" if k.get("status") else str(k.get("verdict", "")).startswith("unique")


def _home(products: list[dict] | None) -> dict[str, str]:
    return {t.lower(): c["name"] for c in products or [] for t in c["tables"]}


def link_split(validation: dict | None, products: list[dict] | None, tables: list[str] | None = None) -> dict:
    """WB10, one source of truth for links: every counted link touching `tables` (all tables when None), as links inside
    one data product, links between two data products ({"a and b": n}) and links to a table in no data product."""
    home = _home(products)
    mine = None if tables is None else {t.lower() for t in tables}
    inside, between, outside, orphans, n = 0, {}, 0, 0, 0
    for r in counted_links(validation):
        s, t = r.get("source", "").lower(), r.get("target", "").lower()
        if mine is not None and s not in mine and t not in mine:
            continue
        n += 1
        orphans += r["orphans"]
        hs, ht = home.get(s), home.get(t)
        if hs and ht and hs == ht:
            inside += 1
        elif hs and ht:
            pair = " and ".join(sorted({hs, ht}, key=str.lower))
            between[pair] = between.get(pair, 0) + 1
        else:
            outside += 1
    return {"links": n, "inside": inside, "between": between, "outside": outside, "orphans": orphans}


def _between_words(between: dict) -> list[str]:
    return [f"{_plural(n, 'link')} between {pair}" for pair, n in between.items()]


def evidence(validation: dict | None, tables: list[str], checked_on: str | None, products: list[dict] | None = None,
             name: str | None = None) -> dict:
    """What the check counted for these tables: keys unique of keys counted, and every counted link touching them, split
    into links inside the product, links between data products (stated separately) and links to tables in no data
    product, with their orphan rows, and the time of the check. Without counts: says so, and claims nothing."""
    if not validation:
        return {"counted": False, "line": "keys and links not yet checked against the rows"}
    mine = {t.lower() for t in tables}
    keys = [k for k in counted_keys(validation) if k.get("table", "").lower() in mine]
    unique = sum(1 for k in keys if _unique(k))
    split = link_split(validation, products if products is not None else [{"name": name or "", "tables": tables}], tables)
    parts = []
    if keys:
        parts.append(f"{unique} of {_plural(len(keys), 'key')} unique")
    if split["links"]:
        where = f" inside {name}" if name else ""
        bits = [f"{_plural(split['inside'], 'link')}{where}"] if split["inside"] or not split["between"] else []
        bits += _between_words(split["between"])
        if split["outside"]:
            bits.append(f"{_plural(split['outside'], 'link')} to tables in no data product")
        parts.append(f"{_plural(split['orphans'], 'orphan row')} over " + (" and ".join(bits) if len(bits) < 3
                     else ", ".join(bits[:-1]) + " and " + bits[-1]))
    when = day_words(checked_on) if checked_on else ""
    line = (", ".join(parts) or "nothing counted for these tables") + (f", checked {when}" if when and parts else "")
    return {"counted": bool(parts), "keys_counted": len(keys), "keys_unique": unique, "links_counted": split["links"],
            "links_inside": split["inside"], "links_between": split["between"], "links_outside": split["outside"],
            "orphan_rows": split["orphans"], "checked_on": checked_on, "line": line}


def page_evidence(validation: dict | None, products: list[dict], checked_on: str | None) -> dict:
    """WB10: the whole check in one sentence, the same totals as the editor's Thinker line (every counted key and link),
    with the links between data products stated separately. The summary and every item description use it."""
    if not validation:
        return {"counted": False, "line": "keys and links not yet checked against the rows", "short": ""}
    keys = counted_keys(validation)
    unique = sum(1 for k in keys if _unique(k))
    sp = link_split(validation, products)
    head = f"{unique} of {_plural(len(keys), 'key')} unique, {_plural(sp['orphans'], 'orphan row')} over {_plural(sp['links'], 'link')}"
    bits = [f"{sp['inside']} inside the data products"] if products else []
    bits += _between_words(sp["between"])
    if sp["outside"]:
        bits.append(f"{sp['outside']} to tables in no data product")
    when = f", checked {day_words(checked_on)}" if checked_on else ""
    detail = f" ({'; '.join(bits)})" if sp["links"] and (sp["between"] or sp["outside"]) else ""
    return {"counted": bool(keys or sp["links"]), "keys_counted": len(keys), "keys_unique": unique,
            "links_counted": sp["links"], "links_inside": sp["inside"], "links_between": sp["between"],
            "links_outside": sp["outside"], "orphan_rows": sp["orphans"], "checked_on": checked_on,
            "line": f"{head}{detail}{when}", "short": f"{head}{when}"}


def _fit(*versions: str) -> str:
    for v in versions:
        if len(v) <= DESCRIPTION_MAX:
            return v
    v = versions[-1]
    return v[:DESCRIPTION_MAX - 1].rsplit(" ", 1)[0] + "…"


_EMAIL = re.compile(r"[^\s()<>,;]+@[^\s()<>,;]+")


def owner_name(owner: str | None) -> str | None:
    """ED3 (Gustav: 'Owner: <name> (<email>)' in a description): the owner's name only, never an e-mail address. A
    value that is only an address gives no name at all."""
    v = " ".join(_EMAIL.sub("", str(owner or "")).replace("()", "").replace("<>", "").split()).strip(" ,;")
    return v or None


def description(name: str, tables: list[str], schema: str, ev: dict, owner: str | None) -> str:
    ents = [words(entity_name(t)) for t in tables]
    shown = owner_name(owner)
    who = f" Owner: {shown}." if shown else ""
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
    # ED3 (Gustav: one 'customers' product of 5 tables while the plan has two): ED2's one grouping (domains.data_products,
    # the plan's rules only), one ODCS contract per data product of it
    d = _domains.data_products(p)
    d["contracts"] = {x["slug"]: _domains.contract(p, x, d["interfaces"], schema, source, validation) for x in d["domains"]}
    d["domains_as_products"] = [{"name": (names.get(x["slug"]) or x["name"]).strip(), "tables": x["tables"]} for x in d["domains"]]
    out = []
    for dom in d["domains"]:
        name = (names.get(dom["slug"]) or dom["name"]).strip()
        owner = (owners.get(dom["slug"]) or "").strip() or None
        ev = evidence(validation, dom["tables"], checked_on, d["domains_as_products"], name)
        out.append({
            "name": name, "slug": dom["slug"], "tables": dom["tables"],
            "description": description(name, dom["tables"], schema, ev, owner),
            "owner": owner_name(owner) or "not chosen yet",
            **({"owner_contact": owner} if owner and owner != owner_name(owner) else {}),
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
