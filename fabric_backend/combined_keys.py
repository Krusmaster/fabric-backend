"""Composite keys carried through (n226): one combined key column per composite key and per composite link.

A Power BI relationship and a Fabric IQ ontology relationship use one column per side, and Direct Lake allows no
calculated column (semantic_model.not_expressible_why). A plan on SAP-shaped tables has nothing but composite keys
(MANDT + VBELN), so before n226 its model had no relationship at all and its ontology no key. The fix the model's own
text describes: a combined key column, written into the Delta table by a Krusgraph step, and the relationship made on it.

What is combined, decided here and nowhere else:
  - a relationship is *carried* when its target has a key of two or more columns and the relationship's target columns
    are exactly that key (any order) with one source column per key column. Its source table gets one combined column
    of its source columns, put in the order of the target's key columns, and the relationship becomes a one-column
    relationship from that column to the target's combined key column;
  - when at least one relationship is carried, every table with a composite key gets its combined key column, so its
    entity in the ontology has a key and its table in the model an `isKey` column;
  - when none is carried (a schema with single-column keys only, or a composite key nobody points at), nothing changes:
    no column is added anywhere, and every output is what it was before n226.
A relationship that is not carried (one column pointing at a part of a composite key, a link to a non-key column set)
stays "not expressible", with the reason, as before.

The value: the parts cast to text and joined with SEPARATOR, U+001F (the ASCII unit separator, made for exactly this
and not found in business keys), so `('1', '23')` and `('12', '3')` never give the same value as `1|23` and `12|3`
could with a printable separator inside a value. A NULL in any part gives NULL (Spark's `concat`, not `concat_ws`,
which would skip it and make two different keys equal). Both sides use the same expression, so the values match exactly
when every part matches as text; MANDT (the client) is a part like any other.

Where the column lives: the silver step (silver.py) writes it into each silver table, after the key and reference
checks, so the semantic model and the ontology read the silver layer when anything is carried, and say so. The source
tables are never changed. This is a draft on the repository's synthetic SAP sample (fabric_backend/sap_sample.py),
not something run on an SAP system.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

SEPARATOR = "\x1f"
SUFFIX = "_key"
DEFAULT_LAYER = "silver"


def column_name(columns: list[str], taken: set[str] | None = None) -> str:
    """The combined column of `columns` (in that order): MANDT + VBELN -> MANDT_VBELN_key. A name the table already has
    gets `_kg` appended until it is free."""
    name = "_".join(columns) + SUFFIX
    taken = {t.lower() for t in (taken or set())}
    while name.lower() in taken:
        name += "_kg"
    return name


@dataclass
class Combined:
    """One combined column: its table, its name and the columns it joins, in order; `why` says what needs it."""
    table: str
    name: str
    columns: list[str]
    why: list[str] = field(default_factory=list)


def _key(plan, table: str) -> list[str]:
    return list(plan.keys.get(table, ([], ""))[0])


def carried_parts(plan, r) -> list[str] | None:
    """The source columns of relationship `r` in the order of its target's composite key, when `r` can be carried by a
    combined key column; None otherwise."""
    key = _key(plan, r.target)
    if len(key) < 2 or len(r.source_cols) != len(r.target_cols) or len(r.target_cols) != len(key):
        return None
    by_target = {str(t).lower(): s for s, t in zip(r.source_cols, r.target_cols)}
    if sorted(by_target) != sorted(c.lower() for c in key):
        return None
    return [by_target[c.lower()] for c in key]


def columns(plan, tables: list[str] | None = None) -> dict[str, list[Combined]]:
    """table -> the combined columns it gets, in a fixed order (its key first, then per relationship in plan order).
    Empty when no relationship among `tables` (all when None) is carried."""
    wanted = {t.lower() for t in tables} if tables else None
    names = {t.name for t in plan.schema if wanted is None or t.name.lower() in wanted}
    rels = [r for r in plan.relationships if r.source in names and r.target in names and carried_parts(plan, r) is not None]
    if not rels:
        return {}
    out: dict[str, list[Combined]] = {}

    def add(table: str, parts: list[str], why: str) -> Combined:
        have = out.setdefault(table, [])
        for c in have:
            if [x.lower() for x in c.columns] == [x.lower() for x in parts]:
                if why not in c.why:
                    c.why.append(why)
                return c
        taken = {c.name for c in plan.schema[table].columns} | {c.name for c in have}
        c = Combined(table, column_name(parts, taken), list(parts), [why])
        have.append(c)
        return c
    for t in plan.schema:                                       # every composite key, in plan order
        key = _key(plan, t.name)
        if t.name in names and len(key) > 1:
            add(t.name, key, f"the key of {t.name}")
    for r in rels:
        add(r.source, carried_parts(plan, r), f"{r.source}.{'+'.join(r.source_cols)} -> {r.target}")
    return out


def key_column(plan, table: str, combined: dict[str, list[Combined]]) -> str | None:
    key = _key(plan, table)
    for c in combined.get(table, []):
        if [x.lower() for x in c.columns] == [x.lower() for x in key]:
            return c.name
    return None


def source_column(plan, r, combined: dict[str, list[Combined]]) -> str | None:
    parts = carried_parts(plan, r)
    if parts is None:
        return None
    for c in combined.get(r.source, []):
        if [x.lower() for x in c.columns] == [x.lower() for x in parts]:
            return c.name
    return None


def carry(plan, tables: list[str] | None = None):
    """The plan as the silver layer holds it: (plan', combined), where plan' is a copy whose tables carry the combined
    columns (text), whose composite keys are their combined key column (same rule) and whose carried relationships are
    one-column relationships between combined columns (same rule; the note says which columns they combine). (plan,
    {}) when nothing is carried: the plan itself, untouched."""
    combined = columns(plan, tables)
    if not combined:
        return plan, {}
    from .schema import Column
    p = copy.deepcopy(plan)
    for table, cols in combined.items():
        p.schema[table].columns += [Column(c.name, "string") for c in cols]
    keys = {}
    for table, (cols, rule) in p.keys.items():
        k = key_column(plan, table, combined)
        keys[table] = ([k], rule) if k else (cols, rule)
    rels = []
    for r in p.relationships:
        src = source_column(plan, r, combined)
        tgt = key_column(plan, r.target, combined) if src else None
        if src and tgt:
            orig = f"{'+'.join(r.source_cols)} -> {r.target}.{'+'.join(r.target_cols)}"
            r.note = ((r.note + "; ") if r.note else "") + f"combined key column of {orig} (written by the silver step)"
            r.source_cols, r.target_cols = [src], [tgt]
        rels.append(r)
    p.keys, p.relationships = keys, rels
    return p, combined


def spark_expr(parts: list[str]) -> str:
    """The PySpark expression of the silver notebook (its helper `col`): the parts as text with the separator between."""
    inner = ", F.lit(chr(31)), ".join(f"col({c!r}).cast('string')" for c in parts)
    return f"F.concat({inner})"


def sql_expr(parts: list[str], quote, alias: str = "") -> str:
    """The same value in Spark SQL (gold views, checks): concat(CAST(a AS STRING), char(31), ...)."""
    pre = f"{alias}." if alias else ""
    return "concat(" + ", char(31), ".join(f"CAST({pre}{quote(c)} AS STRING)" for c in parts) + ")"


def value(row: dict, parts: list[str]) -> str | None:
    """The same value in Python (silver.simulate, the tests)."""
    vals = [row.get(c) for c in parts]
    if any(v is None for v in vals):
        return None
    return SEPARATOR.join(str(v) for v in vals)


def layer(info: dict, combined: dict) -> dict | None:
    """Which layer an output reads when columns are combined: the silver schema (info["silver_schema"], else "silver"),
    on a lakehouse without schemas the prefixed tables. None when nothing is combined (the source, as before)."""
    kind = info.get("item_kind") or "Lakehouse"
    if not combined or kind != "Lakehouse":                 # the silver step writes into a lakehouse only (a warehouse:
        return None                                         # as before, the relationships stay not expressible)
    silver = info.get("silver_schema") or DEFAULT_LAYER
    enabled = info.get("schemas_enabled")
    source = info.get("schema") or "dbo"
    enabled = bool(enabled) if enabled is not None else not (kind == "Lakehouse" and source.lower() == "dbo")
    n = sum(len(v) for v in combined.values())
    return {"layer": "silver", "schema": silver if enabled else None, "prefix": "" if enabled else f"{silver}_",
            "schemas_enabled": enabled, "combined_columns": n,
            "said": (f"Reads the silver layer ({silver + '.<table>' if enabled else silver + '_<table>'}), not the source tables: "
                     f"{n} combined key column(s) carry the composite keys and links, and only the silver step writes them "
                     "(create_silver_notebook or create_pipeline). Run that step first; the source tables are not changed.")}


def describe(combined: dict) -> list[dict]:
    """For an answer: [{table, column, combines, for}]."""
    return [{"table": c.table, "column": c.name, "combines": c.columns, "for": c.why}
            for cols in combined.values() for c in cols]
