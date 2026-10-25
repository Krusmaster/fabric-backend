"""Keys and relationships for tables that have none declared.

A lakehouse SQL endpoint has no primary keys and no foreign keys. A warehouse may have them
(NOT ENFORCED) — if so, they win. Otherwise we go by names, in this order, and every result says
which rule produced it so you can overrule it.

Keys (per table):
  K0  declared primary key
  K1  `keys` override from the caller
  K2  a column named `id`, `<table>_id`, `<table>id`, `<singular>_id`, `<singular>id`, `<table>_key`
  K3  nothing — the table gets no key; it can be queried but not by pk, and nothing can point at it

Relationships (per column of a table A that is not A's own key):
  R0  declared foreign key
  R1  column named `<B>_id` / `<B>id` / `<singular B>_id` / `<singular B>id` where B has a single key
  R2  column has exactly the same name as B's single key column, and that name is not just `id`
      (`customer_id` in orders -> customers.customer_id; `id` never matches)
  R3  all of B's composite key columns appear in A (header/items: order_id+line in order_items
      vs order_id in orders is R1; sales_org+plant in both is R3)
A column that could point at two tables is reported as ambiguous and not applied.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schema import Schema, Table


@dataclass
class Relationship:
    source: str                      # the table holding the reference (the "many" side)
    source_cols: list[str]
    target: str                      # the table being pointed at (the "one" side)
    target_cols: list[str]
    rule: str                        # R0..R3
    field_name: str = ""             # GraphQL field on the source, e.g. "customer"
    reverse_name: str = ""           # GraphQL field on the target, e.g. "orders"

    @property
    def key(self) -> tuple:
        return (self.source, tuple(c.lower() for c in self.source_cols), self.target)


@dataclass
class Plan:
    schema: Schema
    keys: dict[str, tuple[list[str], str]] = field(default_factory=dict)  # table -> (cols, rule)
    relationships: list[Relationship] = field(default_factory=list)
    ambiguous: list[dict] = field(default_factory=list)
    keyless: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"{len(self.schema)} tables, {len(self.keys)} with keys, {len(self.relationships)} relationships"]
        if self.keyless:
            lines.append("no key (query only; can reference others, cannot be referenced): " + ", ".join(self.keyless))
        if self.ambiguous:
            lines.append(f"{len(self.ambiguous)} ambiguous columns not applied — see plan.ambiguous")
        return "\n".join(lines)

    def mermaid(self) -> str:
        out = ["erDiagram"]
        for t in self.schema:
            out.append(f"  {_m(t.name)} {{")
            for c in t.column_names:
                mark = " PK" if c in self.keys.get(t.name, ([], ""))[0] else ""
                out.append(f"    {_m(c)} {_m(_type_word(t, c))}{mark}")
            out.append("  }")
        for r in self.relationships:
            out.append(f'  {_m(r.target)} ||--o{{ {_m(r.source)} : "{"+".join(r.source_cols)} {r.rule}"')
        return "\n".join(out)


# The rules, in the words of the docstring above. The site's demo and the MCP tools quote these, so the
# wording users read is the wording the engine documents. Kept in sync by a test.
RULES = {
    "K0": "declared primary key",
    "K1": "`keys` override from the caller",
    "K2": "a column named `id`, `<table>_id`, `<table>id`, `<singular>_id`, `<singular>id`, `<table>_key`",
    "K3": "nothing — the table gets no key; it can be queried but not by pk, and nothing can point at it",
    "R0": "declared foreign key",
    "R1": "column named `<B>_id` / `<B>id` / `<singular B>_id` / `<singular B>id` where B has a single key",
    "R2": "column has exactly the same name as B's single key column, and that name is not just `id`",
    "R3": "all of B's composite key columns appear in A",
    "confirmed": "given by the caller in `confirmed=[...]`, applied as-is, before inference",
}

_SPLIT = re.compile(r"[^a-z0-9]+")


def _norm(s: str) -> str:
    return _SPLIT.sub("", s.lower())


def _singulars(name: str) -> set[str]:
    n = name.lower()
    out = {n}
    if n.endswith("ies"):
        out.add(n[:-3] + "y")
    if n.endswith("sses") or n.endswith("xes") or n.endswith("ches") or n.endswith("shes"):
        out.add(n[:-2])
    if n.endswith("s") and not n.endswith("ss"):
        out.add(n[:-1])
    return out


def _key_candidates(table: str) -> set[str]:
    c = set()
    for base in _singulars(table):
        b = _norm(base)
        c.update({"id", b + "id", b + "key", b + "nr", b + "no"})
    return c


def _ref_candidates(target: str) -> set[str]:
    c = set()
    for base in _singulars(target):
        b = _norm(base)
        c.update({b + "id", b + "key", b + "nr", b + "no"})
    return c


def infer_keys(schema: Schema, keys: dict[str, list[str]] | None = None) -> dict[str, tuple[list[str], str]]:
    keys = {k.lower(): v for k, v in (keys or {}).items()}
    out: dict[str, tuple[list[str], str]] = {}
    for t in schema:
        if t.name.lower() in keys:
            out[t.name] = ([t.col(c) for c in keys[t.name.lower()]], "K1")
        elif t.keys:
            out[t.name] = (list(t.keys), "K0")
        else:
            cands = _key_candidates(t.name)
            hits = [c for c in t.column_names if _norm(c) in cands]
            # prefer the most specific name: <table>_id over id
            hits.sort(key=lambda c: (_norm(c) == "id", len(c)))
            if hits:
                out[t.name] = ([hits[0]], "K2")
    return out


def infer_relationships(schema: Schema, keys: dict[str, tuple[list[str], str]],
                        confirmed: list[dict] | None = None) -> tuple[list[Relationship], list[dict]]:
    """confirmed: [{"source": "orders", "source_cols": ["customer_id"], "target": "customers",
    "target_cols": ["customer_id"]}] — applied as-is, before inference, and never contradicted."""
    rels: list[Relationship] = []
    ambiguous: list[dict] = []
    seen: set[tuple] = set()

    def add(r: Relationship) -> None:
        if r.key in seen:
            return
        seen.add(r.key)
        rels.append(r)

    for c in confirmed or []:
        add(Relationship(c["source"], list(c["source_cols"]), c["target"], list(c.get("target_cols") or c["source_cols"]), "confirmed"))

    single_key: dict[str, str] = {t: k[0] for t, (k, _) in keys.items() if len(k) == 1}
    by_ref_name: dict[str, list[str]] = {}
    by_key_name: dict[str, list[str]] = {}                                # R2 index: normalised key column -> tables
    for t, k in single_key.items():
        for cand in _ref_candidates(t):
            by_ref_name.setdefault(cand, []).append(t)
        by_key_name.setdefault(_norm(k), []).append(t)

    for t in schema:
        own_key = set(x.lower() for x in keys.get(t.name, ([], ""))[0])
        for cols, target, tcols in t.foreign_keys:                     # R0
            if target in schema:
                add(Relationship(t.name, cols, target, tcols, "R0"))
        for c in t.column_names:
            if c.lower() in own_key and len(own_key) == 1:
                continue
            n = _norm(c)
            targets = [b for b in by_ref_name.get(n, []) if b != t.name]  # R1
            rule = "R1"
            if not targets and n != "id":                                 # R2
                targets = [b for b in by_key_name.get(n, []) if b != t.name]
                rule = "R2"
            if len(targets) > 1:
                ambiguous.append({"table": t.name, "column": c, "candidates": targets, "rule": rule})
                continue
            if targets:
                b = targets[0]
                add(Relationship(t.name, [c], b, [single_key[b]], rule))
        for b, (bk, _) in keys.items():                                  # R3
            if b == t.name or len(bk) < 2:
                continue
            if all(t.has(k) for k in bk) and set(x.lower() for x in bk) != own_key:
                add(Relationship(t.name, [t.col(k) for k in bk], b, list(bk), "R3"))

    _name_fields(rels)
    return rels, ambiguous


def _name_fields(rels: list[Relationship]) -> None:
    """GraphQL field names: `customer` on orders, `orders` on customers; disambiguate by column."""
    from collections import Counter
    fwd = Counter((r.source, r.target) for r in rels)
    back = Counter((r.target, r.source) for r in rels)
    for r in rels:
        base = sorted(_singulars(r.target), key=len)[0]
        r.field_name = _gql(base if fwd[(r.source, r.target)] == 1 else f"{base}_by_{'_'.join(r.source_cols)}")
        r.reverse_name = _gql(r.source if back[(r.target, r.source)] == 1 else f"{r.source}_by_{'_'.join(r.source_cols)}")


RESERVED_FIELDS = {"items", "edges", "nodes", "pageinfo", "endcursor", "hasnextpage"}


def _gql(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", s).lower()
    s = s if not s[:1].isdigit() else "_" + s
    # "items" as a relationship field collides with the GraphQL connection's own `items` list (500 in Fabric)
    return s + "_lines" if s in RESERVED_FIELDS else s


class PlanInputError(ValueError):
    """`keys=` or `confirmed=` names a table or column that is not in the schema (or an entry is malformed)."""


def check_input(schema: Schema, keys: dict[str, list[str]] | None, confirmed: list[dict] | None) -> None:
    """Every table and column the caller names must exist, so a typo is reported here and never reaches Fabric
    as a definition that refers to a column that is not there."""
    tables = {t.name.lower(): t for t in schema}
    problems: list[str] = []
    for name, cols in (keys or {}).items():
        t = tables.get(str(name).lower())
        if t is None:
            problems.append(f"keys: table {name!r} is not in the schema")
        elif not cols:
            problems.append(f"keys: table {name!r} has an empty column list")
        else:
            problems += [f"keys: column {c!r} is not in table {name!r}" for c in cols if not t.has(str(c))]
    for i, c in enumerate(confirmed or []):
        if not isinstance(c, dict) or not c.get("source") or not c.get("target") or not c.get("source_cols"):
            problems.append(f"confirmed[{i}]: each entry needs source, source_cols and target")
            continue
        for side, cols in (("source", c["source_cols"]), ("target", c.get("target_cols") or c["source_cols"])):
            t = tables.get(str(c[side]).lower())
            if t is None:
                problems.append(f"confirmed[{i}]: {side} table {c[side]!r} is not in the schema")
            else:
                problems += [f"confirmed[{i}]: column {col!r} is not in table {c[side]!r}" for col in cols if not t.has(str(col))]
    if problems:
        raise PlanInputError("; ".join(problems))


def plan(schema: Schema, keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None) -> Plan:
    check_input(schema, keys, confirmed)
    k = infer_keys(schema, keys)
    rels, amb = infer_relationships(schema, k, confirmed)
    return Plan(schema, k, rels, amb, keyless=[t.name for t in schema if t.name not in k])


def _m(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", s)


def _type_word(t: Table, c: str) -> str:
    for col in t.columns:
        if col.name == c:
            return re.sub(r"[^a-z0-9]", "", col.data_type.split("(")[0]) or "string"
    return "string"
