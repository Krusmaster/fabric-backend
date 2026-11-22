"""SM5 (gap G4 in docs/SMOOTH/MULTI-LAKEHOUSE.md): a plan over several schemas of one item.

Layout (c) of a multi-lakehouse workspace keeps each source as a schema of one lakehouse (`sap`, `crm`), often as schema
shortcuts from the source lakehouses (docs/SMOOTH/COMBINE-SOURCES.md, section 1). One SQL connection reads them all with
two-part names, so one plan can hold both:

- `schema="sap+crm"` (or `"sap,crm"`) reads each schema with the platform's own reader and joins them into one `Schema`
  whose name is `sap+crm` (the parts in the order given, separated by `+`).
- Every table is keyed `schema.table` (`sap.KNA1`, `crm.Account`), so two schemas may both have a `Customer` table.
- A declared foreign key keeps its target inside its own schema (`crm.Contact` -> `crm.Account`). One that pointed into
  another schema was already left out by the reader; a link across schemas comes from the person (`confirmed`) or,
  later, from the match rules of COMBINE-SOURCES.md (SM7).
- `Dialect.table("sap+crm", "sap.KNA1")` quotes it as `[sap].[KNA1]`, so every counting query (the join check, the
  row check, the samples) runs over the right schema on the one connection: a link from `crm.Account` to `sap.KNA1` is
  counted in one query.

Nothing here reads rows or infers anything. A name without `+` or `,` is one schema, read as before.
"""
from __future__ import annotations

from .schema import Schema, Table

SEP = "+"


def parts(schema: str | None) -> list[str]:
    """The schema names in `schema`: ["sap", "crm"] for "sap+crm" or "sap, crm"; [schema] for one name. Repeats go."""
    raw = str(schema or "").replace(",", SEP)
    out: list[str] = []
    for p in (x.strip() for x in raw.split(SEP)):
        if p and p.lower() not in {o.lower() for o in out}:
            out.append(p)
    return out


def is_multi(schema: str | None) -> bool:
    return len(parts(schema)) > 1


def split(schema: str, table: str) -> tuple[str, str]:
    """(schema, table) of a table key in a combined plan: ("sap", "KNA1") for ("sap+crm", "sap.KNA1"). A table key of a
    one-schema plan comes back unchanged."""
    if SEP in str(schema) and "." in str(table):
        s, t = str(table).split(".", 1)
        return s, t
    return schema, table


def combine(schemas: list[Schema]) -> Schema:
    """One Schema over several: tables keyed `schema.table`, foreign keys re-keyed inside their own schema."""
    name = SEP.join(s.schema for s in schemas)
    out = Schema(schema=name)
    for s in schemas:
        for t in s:
            key = f"{s.schema}.{t.name}"
            out.tables[key] = Table(key, list(t.columns), list(t.keys),
                                    [(list(c), f"{s.schema}.{target}", list(tc)) for c, target, tc in t.foreign_keys],
                                    schema=name, tags=dict(t.tags))
    return out


def read(read_one, execute, schema: str) -> Schema:
    """read_one(execute, name) for each schema in `schema`, combined; one name is read as before. An empty schema stays
    out of the combination (the caller's SchemaEmpty speaks when every one is empty)."""
    names = parts(schema)
    if len(names) <= 1:
        return read_one(execute, schema)
    read_ = [read_one(execute, n) for n in names]
    kept = [s for s in read_ if len(s)]
    return combine(kept or read_[:1])


def by_schema(s: Schema) -> dict[str, int]:
    """{schema: tables} of a combined plan, in the order read; {} for a one-schema plan."""
    if SEP not in str(s.schema):
        return {}
    out: dict[str, int] = {p: 0 for p in parts(s.schema)}
    for t in s:
        out[split(s.schema, t.name)[0]] = out.get(split(s.schema, t.name)[0], 0) + 1
    return out


def packs(s: Schema, keys, one_pack):
    """infer._pack over a combined plan: each schema's tables are matched on their own (SAP in `sap`, Salesforce in
    `crm`), so one source's pack never hides the other's. The keys, relationships and tables are joined; plan.pack is
    the pack with the most tables, with `by_schema` naming each schema's pack and `tables` covering them all."""
    groups: dict[str, Schema] = {}
    for t in s:
        part = split(s.schema, t.name)[0]
        groups.setdefault(part, Schema(schema=part)).tables[t.name] = t      # one name: no recursion
    found = []
    for part, sub in groups.items():
        summary, k, rels, tables = one_pack(sub, keys)
        if summary is not None:
            found.append((part, summary, k, rels, tables))
    if not found:
        return None, {}, [], set()
    found.sort(key=lambda x: -len(x[4]))
    top = dict(found[0][1])
    top["tables"] = {t: n for _, sm, *_ in found for t, n in sm["tables"].items()}
    top["by_schema"] = {part: sm["pack"] for part, sm, *_ in found}
    k_all: dict = {}
    rels_all: list = []
    tables_all: set = set()
    for _, _, k, rels, tables in found:
        k_all.update(k)
        rels_all += rels
        tables_all |= tables
    return top, k_all, rels_all, tables_all
