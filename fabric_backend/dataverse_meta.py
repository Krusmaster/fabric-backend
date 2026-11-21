"""Dataverse `$metadata`: keys and relationships that Dataverse declares, as candidates (2026-11-21, round BL25).

Layer 2, the same idea as the SAP CSN reader (csn.py): metadata the customer's own system ships beats a pack. Dataverse
publishes its tables, keys and lookups in the Web API's CSDL `$metadata` document, an OData XML file the customer
downloads from `https://<their-org>.api.crm.dynamics.com/api/data/v9.2/$metadata` and hands over. That file is read
where it lies; nothing here fetches anything, and a URL is refused.

What it reads (Microsoft Learn, "Dataverse Web API service documents", ms.date 2026-10-26; "Web API EntityTypes",
ms.date 2023-05-18; "Web API navigation properties", ms.date 2026-01-07; all opened 21 November 2026):

- every `EntityType` that is not abstract: its `Key` (`PropertyRef`), inherited through `BaseType` when the type has no
  key of its own (an activity such as `phonecall` takes `activityid` from `activitypointer`), and its `Property`
  elements with their `Edm` type;
- every single-valued `NavigationProperty` with a `ReferentialConstraint`: a lookup. `Property` is the lookup property
  (`_parentaccountid_value`), `ReferencedProperty` the related table's primary key (`accountid`). When one lookup
  property is the constraint of several navigation properties (`_customerid_value` for `customerid_account` and
  `customerid_contact`), it is a multi-table (polymorphic) lookup;
- a collection-valued navigation property whose `Partner` is a collection on the other side as well: a many-to-many.
  Collections whose partner is a lookup are the other side of that lookup and add nothing.

What it does with them. The metadata is a declaration, not evidence: a landing may drop rows, a lookup may point at a
purged record (the dynamics_demo's "Demo call 2"). So every key and link carries `provenance` "declared by Dataverse
metadata, not counted", and validate_plan counts it against the rows like any other once it is fed to the plan (the
next step; it touches infer.py, which this round does not).

- a plain lookup becomes a link source -> target, many-to-one, on the lookup column, in the candidate shape csn.links
  gives (`source`, `source_cols`, `target`, `target_cols`, `rule`, `provenance`, `declared_in`, `note`);
- a polymorphic lookup becomes one *filtered* link per target table (`filter`: the lookup's type column, such as
  `customeridtype`, equal to the target's logical name), never a plain link: a plain join of `customerid` to account
  would call every contact an orphan;
- a many-to-many is listed, not applied: the intersect table carries it, and Dataverse declares no lookups on it;
- what is not understood is never guessed: `Model.ignored` lists it.

Names, as Link to Microsoft Fabric lands Dataverse (docs/DYNAMICS365.md; fabric_backend/dynamics_demo.py): one table per
logical name (`account`, `salesorderdetail`), logical column names, a lookup as its logical name (the Web API's
`_parentaccountid_value` lands as `parentaccountid`), a polymorphic lookup's type as `<name>type`, and the system
columns `Id`, `IsDelete`, `SinkCreatedOn`, `SinkModifiedOn`, `versionnumber`. Tables match without case and underscores,
with a leading layer word or the caller's `prefix` dropped (csn.table_names); a table is taken only when its key
columns are there. What does not map is reported: tables, columns, lookups.

    read(path | str | bytes)            -> Model: entities, many_to_many, namespace, files, ignored
    match(schema, model, prefix)        -> csn.NameMatch, plus the columns that did not map
    candidates(schema, model, prefix)   -> the report: keys, links, filtered links, not applied, unmapped (plan-ready)
    summary(model)                      -> a JSON-able digest of what was read

Tested on a synthetic `$metadata` written for the tests (tests/fixtures/dataverse_metadata_demo.xml) against the
synthetic Dynamics 365 demo lake (dynamics_demo.sqlite); not run on a `$metadata` exported from a customer's
environment. Krusgraph is independent and not affiliated with Microsoft.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

from .csn import NameMatch, norm, table_names

RULE = "Dataverse metadata"
PROVENANCE = "declared by Dataverse metadata, not counted"
EDM = "{http://docs.oasis-open.org/odata/ns/edm}"
EDMX = "{http://docs.oasis-open.org/odata/ns/edmx}"
SYSTEM_COLUMNS = ("Id", "IsDelete", "SinkCreatedOn", "SinkModifiedOn", "versionnumber")   # added by Link to Fabric
_LOOKUP = re.compile(r"^_(.+)_value$")
_COLLECTION = re.compile(r"^Collection\((.+)\)$")


@dataclass
class Lookup:
    nav: str                     # the navigation property: customerid_account
    target: str                  # the related entity type's logical name: account
    prop: str                    # the lookup property: _customerid_value
    referenced: str              # the related table's key: accountid
    partner: str = ""

    @property
    def column(self) -> str:
        """The lookup as Link to Fabric lands it: _customerid_value -> customerid."""
        return lake_column(self.prop)


@dataclass
class Entity:
    name: str
    base: str = ""
    keys: list[str] = field(default_factory=list)
    key_from: str = ""                                            # the base type the key was inherited from, if any
    properties: dict[str, str] = field(default_factory=dict)      # Web API name -> Edm type
    lookups: list[Lookup] = field(default_factory=list)
    collections: list[dict] = field(default_factory=list)        # {nav, target, partner}

    def polymorphic(self) -> dict[str, list[Lookup]]:
        """Lookup property -> its navigation properties, for the ones that are the constraint of more than one."""
        by: dict[str, list[Lookup]] = {}
        for lk in self.lookups:
            by.setdefault(lk.prop, []).append(lk)
        return {p: v for p, v in by.items() if len(v) > 1}


@dataclass
class Model:
    entities: dict[str, Entity] = field(default_factory=dict)
    many_to_many: list[dict] = field(default_factory=list)       # {entities, nav, intersect, why}
    abstract: list[str] = field(default_factory=list)
    namespace: str = ""
    alias: str = ""
    files: list[str] = field(default_factory=list)
    ignored: list[dict] = field(default_factory=list)            # {what, count | name, why}


def lake_column(name: str) -> str:
    """A Web API property name as Link to Fabric lands the column: a lookup _<name>_value as <name>, the rest as is."""
    m = _LOOKUP.match(name)
    return m.group(1) if m else name


# --------------------------------------------------------------------------------------------------------------------
# reading


def _text(source) -> tuple[bytes, str]:
    if isinstance(source, Path):
        return source.read_bytes(), str(source)
    if isinstance(source, bytes):
        return source, "<bytes>"
    if isinstance(source, str):
        s = source.lstrip("﻿").lstrip()
        if s.startswith("<"):
            return s.encode("utf-8"), "<text>"
        if re.match(r"^[a-z][a-z0-9+.-]*://", s, re.I):
            raise ValueError("give the $metadata file, not its address: Krusgraph fetches nothing (download it yourself, "
                             "docs/DYNAMICS365.md, 'Keys and links from your own $metadata')")
        return Path(source).read_bytes(), source
    raise TypeError("read() takes a path, the XML as text, or bytes")


def _type_name(t: str, namespace: str, alias: str) -> str:
    """mscrm.account / Microsoft.Dynamics.CRM.account -> account; Edm types and others unchanged."""
    for p in (alias, namespace):
        if p and t.startswith(p + "."):
            return t[len(p) + 1:]
    return t


def read(source) -> Model:
    """Read one CSDL `$metadata` document: a path, the XML as text, or bytes. A DOCTYPE or an entity declaration is
    refused (a `$metadata` has none, and they are how an XML file makes a parser fetch or expand)."""
    raw, name = _text(source)
    head = raw[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in raw.lower():
        raise ValueError(f"{name}: a DOCTYPE or ENTITY declaration; a Dataverse $metadata has none, so it is not read")
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as e:
        raise ValueError(f"{name}: not XML ({e})") from e
    if root.tag != f"{EDMX}Edmx":
        raise ValueError(f"{name}: not an OData CSDL document (the root is {root.tag}, not edmx:Edmx)")
    model = Model(files=[name])
    schemas = root.findall(f"{EDMX}DataServices/{EDM}Schema")
    if not schemas:
        raise ValueError(f"{name}: no edm Schema under edmx:DataServices")
    raw_types: dict[str, ElementTree.Element] = {}
    for sch in schemas:
        ns, alias = sch.get("Namespace", ""), sch.get("Alias", "")
        if not model.namespace:
            model.namespace, model.alias = ns, alias
        elif ns != model.namespace:
            model.ignored.append({"what": f"Schema {ns}", "why": "a second namespace; only the first is read"})
            continue
        counts: dict[str, int] = {}
        for el in sch:
            tag = el.tag.replace(EDM, "")
            if tag == "EntityType":
                raw_types[el.get("Name", "")] = el
            else:
                counts[tag] = counts.get(tag, 0) + 1
        for tag, n in sorted(counts.items()):            # ComplexType, EnumType, Action, Function, EntityContainer, ...
            model.ignored.append({"what": tag, "count": n, "why": "not a table, key or relationship"})
    ns, alias = model.namespace, model.alias
    for tname, el in raw_types.items():
        if el.get("Abstract") == "true":
            model.abstract.append(tname)
            continue
        e = Entity(name=tname, base=_type_name(el.get("BaseType", ""), ns, alias))
        model.entities[tname] = e
    for tname, e in model.entities.items():
        chain, seen = [], set()
        cur: str | None = tname
        while cur and cur in raw_types and cur not in seen:   # this type first, then its bases
            seen.add(cur)
            chain.append(raw_types[cur])
            cur = _type_name(raw_types[cur].get("BaseType", ""), ns, alias) or None
        for i, el in enumerate(chain):
            keys = [r.get("Name") for r in el.findall(f"{EDM}Key/{EDM}PropertyRef")]
            if keys and not e.keys:
                e.keys, e.key_from = keys, ("" if i == 0 else el.get("Name", ""))
            for p in el.findall(f"{EDM}Property"):
                e.properties.setdefault(p.get("Name", ""), p.get("Type", ""))
        for nav in chain[0].findall(f"{EDM}NavigationProperty"):
            nname, ntype, partner = nav.get("Name", ""), nav.get("Type", ""), nav.get("Partner", "")
            m = _COLLECTION.match(ntype)
            if m:
                e.collections.append({"nav": nname, "target": _type_name(m.group(1), ns, alias), "partner": partner})
                continue
            rcs = nav.findall(f"{EDM}ReferentialConstraint")
            target = _type_name(ntype, ns, alias)
            if len(rcs) != 1:
                model.ignored.append({"what": f"{tname}.{nname}", "why": f"a single-valued navigation property with {len(rcs)} "
                                      "ReferentialConstraint elements; a lookup has exactly one"})
                continue
            e.lookups.append(Lookup(nav=nname, target=target, prop=rcs[0].get("Property", ""),
                                    referenced=rcs[0].get("ReferencedProperty", ""), partner=partner))
        if not e.keys:
            model.ignored.append({"what": tname, "why": "an entity type with no Key, not even inherited"})
    _many_to_many(model)
    return model


def _many_to_many(model: Model) -> None:
    """Collection navigation properties whose partner is a collection too: a many-to-many, reported once per pair."""
    done: set[tuple] = set()
    for en, e in model.entities.items():
        for c in e.collections:
            other = model.entities.get(c["target"])
            if other is None:
                model.ignored.append({"what": f"{en}.{c['nav']}", "why": f"a collection of {c['target']}, which is not defined"})
                continue
            if any(lk.nav == c["partner"] for lk in other.lookups):
                continue                                      # the other side of a lookup read from the referencing table
            back = next((x for x in other.collections if x["nav"] == c["partner"]), None)
            if back is None:
                model.ignored.append({"what": f"{en}.{c['nav']}", "why": "a collection with no lookup or collection named as "
                                      "its partner on the other side"})
                continue
            pair = tuple(sorted([(en, c["nav"]), (c["target"], back["nav"])]))
            if pair in done:
                continue
            done.add(pair)
            guess = c["nav"][:-len("_association")] if c["nav"].endswith("_association") else c["nav"]
            intersect = guess if guess in model.entities else None
            model.many_to_many.append({
                "entities": [pair[0][0], pair[1][0]], "nav": c["nav"], "intersect": intersect,
                "why": "many-to-many: no lookup on either table; the intersect table holds the pairs"
                       + (f" ({intersect}, which declares no lookups, so its columns are not linked here)" if intersect
                          else " (not in this $metadata)")})


# --------------------------------------------------------------------------------------------------------------------
# names


def match(schema, model: Model, prefix: str | None = None) -> tuple[NameMatch, list[dict]]:
    """(NameMatch, unmapped columns): which table each entity is, and its columns in the schema's spelling. A table is
    taken only when its key columns are there; two entities answering to one table are reported, not resolved."""
    nm = NameMatch()
    index: dict[str, list[str]] = {}
    for t in schema:
        for n in table_names(t.name, prefix):
            index.setdefault(n, []).append(t.name)
    claims: dict[str, list[str]] = {}
    for en in model.entities:
        hits = sorted(set(index.get(norm(en), [])))
        if len(hits) > 1:
            nm.ambiguous.append({"entity": en, "tables": hits, "why": f"{len(hits)} tables answer to {en}; give the prefix"})
        elif not hits:
            nm.unmatched.append({"entity": en, "why": "no table of the schema carries its logical name (Link to Fabric "
                                                      "lands only the tables chosen for it)"})
        else:
            claims.setdefault(hits[0], []).append(en)
    unmapped: list[dict] = []
    for table, ens in claims.items():
        if len(ens) > 1:
            nm.ambiguous.append({"table": table, "entities": ens, "why": "two entities answer to this table"})
            continue
        en, t = ens[0], schema[table]
        e = model.entities[en]
        cols: dict[str, str] = {}
        for c in t.columns:
            cols.setdefault(norm(c.name), c.name)
        missing = [k for k in e.keys if norm(lake_column(k)) not in cols]
        if missing:
            nm.unmatched.append({"entity": en, "table": table, "why": f"{table} lacks key column(s) {', '.join(missing)}"})
            continue
        nm.tables[en], nm.how[en] = table, "logical name"
        nm.columns[en] = {}
        for p in e.properties:
            lc = lake_column(p)
            if norm(lc) in cols:
                nm.columns[en][p] = cols[norm(lc)]
            else:
                unmapped.append({"table": table, "property": p, "column": lc,
                                 "why": f"{lc} is not a column of {table} (not chosen for the link, or renamed)"})
        for lk in e.polymorphic():
            tc = lake_column(lk) + "type"
            if norm(tc) in cols:
                nm.columns[en][tc] = cols[norm(tc)]
        known = {norm(x) for x in nm.columns[en].values()} | {norm(c) for c in SYSTEM_COLUMNS}
        system = [c.name for c in t.columns if c.name.lower() in {x.lower() for x in SYSTEM_COLUMNS}]
        if system:
            nm.cdc_columns[table] = system
        extra = [c.name for c in t.columns if norm(c.name) not in known]
        if extra:
            nm.extra_columns[table] = extra
    return nm, unmapped


# --------------------------------------------------------------------------------------------------------------------
# candidates


def _declared(en: str, lk: Lookup) -> dict:
    return {"entity": en, "navigation_property": lk.nav, "lookup_property": lk.prop, "referenced": f"{lk.target}.{lk.referenced}"}


def candidates(schema, model: Model, prefix: str | None = None) -> dict:
    """What the `$metadata` declares, on the schema's tables, in the shape csn.plan's report has: keys, links (plain
    lookups, many-to-one), filtered links (one per target of a polymorphic lookup), what was not applied and why, and
    what did not map. Nothing is counted here and nothing is fed to the plan yet."""
    nm, unmapped = match(schema, model, prefix)
    keys = {nm.tables[en]: [nm.columns[en][k] for k in model.entities[en].keys] for en in nm.tables}
    links: list[dict] = []
    filtered: list[dict] = []
    not_applied: list[dict] = []
    for en, e in model.entities.items():
        poly = e.polymorphic()
        for lk in e.lookups:
            where = f"{en}.{lk.nav} -> {lk.target}"
            t = model.entities.get(lk.target)
            if t is None:
                not_applied.append({"lookup": where, "why": f"{lk.target} is not defined in the $metadata read"})
                continue
            if [lk.referenced] != t.keys:
                not_applied.append({"lookup": where, "why": f"ReferencedProperty {lk.referenced} is not {lk.target}'s key "
                                                           f"({', '.join(t.keys) or 'none'})"})
                continue
            miss = [x for x in (en, lk.target) if x not in nm.tables]
            if miss:
                not_applied.append({"lookup": where, "why": f"no table for {', '.join(miss)} in the schema"})
                continue
            src_col = nm.columns[en].get(lk.prop)
            if src_col is None:
                not_applied.append({"lookup": where, "why": f"the lookup column {lk.column} is not in {nm.tables[en]}"})
                continue
            rel = {"source": nm.tables[en], "source_cols": [src_col], "target": nm.tables[lk.target],
                   "target_cols": [nm.columns[lk.target][lk.referenced]], "rule": RULE, "provenance": PROVENANCE,
                   "declared_in": [_declared(en, lk)]}
            if lk.prop in poly:
                tc = nm.columns[en].get(lake_column(lk.prop) + "type")
                others = sorted(x.target for x in poly[lk.prop] if x is not lk)
                if tc is None:
                    not_applied.append({"lookup": where, "why": f"{lk.column} is polymorphic (also {', '.join(others)}) and "
                                        f"{nm.tables[en]} has no {lk.column}type column to tell them apart"})
                    continue
                rel["filter"] = {"column": tc, "value": lk.target}
                rel["note"] = (f"{lk.column} is a multi-table lookup (also {', '.join(others)}): join only the rows whose "
                               f"{tc} is '{lk.target}'")
                filtered.append(rel)
            else:
                rel["note"] = f"{lk.nav}: a lookup, many-to-one"
                links.append(rel)
    for mm in model.many_to_many:
        not_applied.append({"many_to_many": " <-> ".join(mm["entities"]), "nav": mm["nav"], "intersect": mm["intersect"],
                            "why": mm["why"]})
    return {
        "rule": RULE, "provenance": PROVENANCE,
        "status": "declared by Dataverse metadata, not verified against the rows: validate_plan counts it once it is fed "
                  "to the plan (next step)",
        "files": list(model.files), "namespace": model.namespace, "entities": len(model.entities),
        "matched": {en: {"table": t, "by": nm.how[en]} for en, t in nm.tables.items()},
        "keys": keys, "links": links, "filtered": filtered, "not_applied": not_applied,
        "unmatched": nm.unmatched, "ambiguous": nm.ambiguous, "unmapped_columns": unmapped,
        "system_columns": nm.cdc_columns, "extra_columns": nm.extra_columns, "ignored": model.ignored,
    }


def summary(model: Model) -> dict:
    """A digest of what was read, per entity: keys (and where they came from), properties, lookups, collections."""
    ents = {}
    for en, e in model.entities.items():
        poly = e.polymorphic()
        ents[en] = {
            "keys": e.keys, **({"key_from": e.key_from} if e.key_from else {}), **({"base": e.base} if e.base else {}),
            "properties": dict(e.properties),
            "lookups": [{"nav": lk.nav, "target": lk.target, "column": lk.column, "referenced": lk.referenced,
                         **({"polymorphic": True} if lk.prop in poly else {})} for lk in e.lookups],
        }
    return {"files": model.files, "namespace": model.namespace, "entities": ents, "abstract": model.abstract,
            "many_to_many": model.many_to_many, "ignored": model.ignored, "provenance": PROVENANCE,
            "note": "metadata only: keys and links are candidates until validate_plan counts them in the rows"}
