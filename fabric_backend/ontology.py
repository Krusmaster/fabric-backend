"""The same plan, as a Fabric IQ ontology (preview).

An ontology item in Fabric IQ is entity types with properties and a key, relationship types between them, and
data bindings that tie each entity type to a table. That is exactly what `infer.plan` produces for a source, with
the rule behind every key and link, so this module writes the plan out in the three forms the ontology item takes:

  ontology_parts()   the item definition (generation 2, TMDL parts) that `POST /workspaces/{id}/ontologies` and
                     Git integration take: tables bound DirectLake-style to the source, entities with a key and
                     properties, table relationships and entity relationships
  ontology_ttl()     a Turtle file the portal's "Import ontology" accepts into an empty item (schema only: entity
                     types, properties, relationships, with the rule in each description; bindings are then done in
                     the portal, following bindings())
  bindings()         the binding checklist: entity → table, key column, property → column, relationship → columns

Grounding: the generation-2 skeleton (model, database, namespaces, .platform) is the official REST example; the
entity, table, relationship and expression syntax follows what the item's own getDefinition returns for a
lakehouse-backed ontology (as mirrored by tools that round-trip it). Supported property types and the key rule
(string or integer) are from the ontology docs. Verified against those recorded definitions, not yet live from here.
"""
from __future__ import annotations

import base64
import json
import re
import uuid

from .infer import Plan, check_tables

_BARE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LINEAGE_NS = uuid.UUID("6f1c6a5e-7b1e-5d3a-9c2b-0a0b0c0d0e0f")      # fixed namespace: same plan, same lineage tags
PLATFORM_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json"

# SQL / Spark type words → (TMDL dataType, ontology property value type). Anything else binds as string, which the
# ontology docs list as the catch-all (decimal(p,s), binary, struct, ...).
_TYPES = {
    "int": ("int64", "integer"), "integer": ("int64", "integer"), "bigint": ("int64", "integer"), "long": ("int64", "integer"),
    "smallint": ("int64", "integer"), "tinyint": ("int64", "integer"), "short": ("int64", "integer"),
    "bit": ("boolean", "boolean"), "boolean": ("boolean", "boolean"), "bool": ("boolean", "boolean"),
    "date": ("dateTime", "datetime"), "datetime": ("dateTime", "datetime"), "datetime2": ("dateTime", "datetime"),
    "timestamp": ("dateTime", "datetime"), "smalldatetime": ("dateTime", "datetime"),
    "double": ("double", "double"), "float": ("double", "double"), "real": ("double", "double"),
    "decimal": ("double", "double"), "numeric": ("double", "double"), "money": ("double", "double"),
}


def prop_type(sql_type: str) -> tuple[str, str]:
    """(TMDL dataType, ontology value type) for a column's declared type."""
    t = (sql_type or "").strip().lower()
    if t.startswith("decimal(") or t.startswith("numeric("):                 # decimal(p, s) binds as string per the ontology docs
        return ("string", "string")
    word = re.sub(r"[ (].*$", "", t)
    return _TYPES.get(word, ("string", "string"))


def entity_name(table: str) -> str:
    """`order_items` → `OrderItems`: an identifier Fabric accepts (letters, digits, underscores; starts with a letter)."""
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", table) if p]
    name = "".join(p[0].upper() + p[1:] for p in parts) or "Entity"
    return name if name[0].isalpha() else "E" + name


def _tmdl(name: str) -> str:
    """A TMDL object name: bare when it can be, quoted (with doubled quotes) otherwise."""
    return name if _BARE.match(name) else "'" + name.replace("'", "''") + "'"


def _tag(*parts: str) -> str:
    """Deterministic lineage tag, so the same plan always yields the same definition."""
    return str(uuid.uuid5(_LINEAGE_NS, "\x1f".join(parts)))


def _relationship_name(r) -> str:
    cols = "_".join(_ident(c) for c in r.source_cols)
    return f"{entity_name(r.source)}_{cols}_{entity_name(r.target)}"


def _entity_relationship_name(r, plan: Plan | None = None) -> str:
    """`OrdersHasCustomers`; when a source points at the same target through two columns, the column disambiguates."""
    twice = plan is not None and sum(1 for x in plan.relationships if x.source == r.source and x.target == r.target) > 1
    if twice:
        return f"{entity_name(r.source)}_{_ident('_'.join(r.source_cols))}_{entity_name(r.target)}"
    return f"{entity_name(r.source)}Has{entity_name(r.target)}"


def _ident(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]+", "_", s).strip("_") or "x"
    return s if s[0].isalpha() else "x_" + s


def _model(plan: Plan, tables: set[str] | None):
    """The entity types this ontology gets, in plan order, with their key column (None when composite or missing)."""
    out = []
    for t in plan.schema:
        if tables and t.name.lower() not in tables:
            continue
        cols, rule = plan.keys.get(t.name, ([], ""))
        key = cols[0] if len(cols) == 1 and prop_type(_type_of(t, cols[0]))[1] in ("string", "integer") else None
        out.append((t, key, cols, rule))
    return out


def _type_of(t, col: str) -> str:
    for c in t.columns:
        if c.name == col:
            return c.data_type
    return "string"


def summary(plan: Plan, tables: list[str] | None = None) -> dict:
    """What the ontology will contain and what needs a hand in the portal."""
    wanted = {x.lower() for x in tables} if tables else None
    model = _model(plan, wanted)
    names = {t.name for t, *_ in model}
    rels = [r for r in plan.relationships if r.source in names and r.target in names]
    single = [r for r in rels if len(r.source_cols) == 1 and len(r.target_cols) == 1]
    notes = []
    for t, key, cols, rule in model:
        if not cols:
            notes.append(f"{entity_name(t.name)}: no key was found (rule K3); the entity type is keyless, so nothing can point at it. "
                         f"Set a key in the portal if the table has one.")
        elif key is None and len(cols) > 1:
            notes.append(f"{entity_name(t.name)}: composite key {cols} is emitted as a keyless entity type with the key columns as properties; "
                         f"the ontology key is one string or integer property, so pick or add one in the portal.")
        elif key is None:
            notes.append(f"{entity_name(t.name)}: key column {cols[0]!r} is not a string or integer; the entity type is emitted keyless.")
    for r in rels:
        if r not in single:
            notes.append(f"{entity_name(r.source)} → {entity_name(r.target)} ({r.rule}, {'+'.join(r.source_cols)}): a composite-column relationship; "
                         f"bind it in the portal with a mapping table, it is not in relationships.tmdl.")
    return {
        "entity_types": len(model), "with_key": sum(1 for _, key, *_ in model if key), "relationship_types": len(single),
        "skipped_relationships": len(rels) - len(single), "notes": notes,
    }


def bindings(plan: Plan, source_name: str, schema: str = "dbo", tables: list[str] | None = None) -> list[dict]:
    """The checklist for binding in the portal (or for reading the definition): one entry per entity type."""
    wanted = {x.lower() for x in tables} if tables else None
    model = _model(plan, wanted)
    names = {t.name for t, *_ in model}
    out = []
    for t, key, cols, rule in model:
        out.append({
            "entity_type": entity_name(t.name), "table": f"{schema}.{t.name}", "source": source_name,
            "key": key, "key_rule": rule or "K3", "key_columns": cols,
            "properties": [{"name": c.name, "column": c.name, "type": prop_type(c.data_type)[1], "source_type": c.data_type} for c in t.columns],
            "relationships": [{"name": _entity_relationship_name(r, plan), "to": entity_name(r.target), "from_columns": r.source_cols,
                               "to_columns": r.target_cols, "rule": r.rule}
                              for r in plan.relationships if r.source == t.name and r.target in names],
        })
    return out


def ontology_parts(plan: Plan, name: str, *, workspace_id: str, item_id: str, item_name: str, item_kind: str = "Lakehouse",
                   schema: str = "dbo", sql_endpoint: str = "", tables: list[str] | None = None, namespace: str = "default") -> dict[str, str]:
    """The item definition as {part path: text}. Generation 2 (TMDL)."""
    check_tables(plan.schema, tables)
    wanted = {x.lower() for x in tables} if tables else None
    model = _model(plan, wanted)
    if not model:
        raise ValueError("the ontology would be empty: no tables")
    names = {t.name for t, *_ in model}
    seen: dict[str, str] = {}
    for t, *_ in model:
        e = entity_name(t.name).lower()
        if e in seen:
            raise ValueError(f"two tables map to the same entity name ({seen[e]!r} and {t.name!r}); rename one or use tables= to leave one out")
        seen[e] = t.name
    single = [r for r in plan.relationships if r.source in names and r.target in names and len(r.source_cols) == 1 and len(r.target_cols) == 1]
    expr = f"DirectLake - {item_name}"
    nl = "\n"
    parts: dict[str, str] = {
        ".platform": json.dumps({"$schema": PLATFORM_SCHEMA, "metadata": {"type": "Ontology", "displayName": name},
                                 "config": {"version": "2.0", "logicalId": "00000000-0000-0000-0000-000000000000"}}, indent=2) + nl,
        "database.tmdl": f"database {_tmdl(name)}{nl}\tcompatibilityLevel: 1000000{nl}",
        f"namespaces/{namespace}.tmdl": f"namespace {_tmdl(namespace)}{nl}\tlineageTag: {namespace}{nl}",
        "expressions.tmdl": nl.join([
            f"expression {_tmdl(expr)} =", "\t\tlet",
            f'\t\t    Source = AzureStorage.DataLake("https://onelake.dfs.fabric.microsoft.com/{workspace_id}/{item_id}", [HierarchicalNavigation=true])',
            "\t\tin", "\t\t    Source", f"\tlineageTag: {_tag(name, 'expression', item_id)}", ""]),
    }
    model_lines = [f"model {_tmdl(name)}", ""]
    model_lines += [f"ref table {_tmdl(entity_name(t.name))}" for t, *_ in model] + [""]
    model_lines += [f"ref entity {_tmdl(entity_name(t.name))}" for t, *_ in model] + [""]
    model_lines += [f"ref namespace {_tmdl(namespace)}", ""]
    parts["model.tmdl"] = nl.join(model_lines)

    for t, key, cols, rule in model:
        e = entity_name(t.name)
        lines = [f"table {_tmdl(e)}", f"\tlineageTag: {_tag(name, 'table', e)}", ""]
        for c in t.columns:
            lines += [f"\tcolumn {_tmdl(c.name)}", f"\t\tdataType: {prop_type(c.data_type)[0]}",
                      f"\t\tlineageTag: {_tag(name, 'column', e, c.name)}", f"\t\tsourceColumn: {c.name}", ""]
        lines += [f"\tpartition {_tmdl(e)} = entity", "\t\tmode: directLake", "\t\tsource", f"\t\t\tentityName: {t.name}",
                  f"\t\t\tschemaName: {schema}", f"\t\t\texpressionSource: {_tmdl(expr)}", ""]
        for k, v in (("ONT_WorkspaceId", workspace_id), ("ONT_ItemId", item_id), ("ONT_ItemKind", item_kind), ("ONT_ItemName", item_name),
                     ("ONT_SqlEndpoint", sql_endpoint), ("ONT_SqlDatabase", item_name)):
            if v:
                lines += [f"\t\tannotation {k} = {v}", ""]
        parts[f"tables/{e}.tmdl"] = nl.join(lines)

        desc = f"/// {t.name}: key {'+'.join(cols)} by rule {rule}" if cols else f"/// {t.name}: no key found (K3)"
        lines = [desc, f"entity {_tmdl(e)}", f"\tlineageTag: {_tag(name, 'entity', e)}", f"\tbackingTable: {_tmdl(e)}"]
        if key:
            lines.append(f"\tkeyProperty: {_tmdl(key)}")
        lines.append("")
        for c in t.columns:
            lines += [f"\tproperty {_tmdl(c.name)}", f"\t\tdataType: {prop_type(c.data_type)[0]}",
                      f"\t\tlineageTag: {_tag(name, 'column', e, c.name)}", "", "\t\tbackingConfiguration",
                      f"\t\t\tvalueColumn: {_tmdl(e)}.{_tmdl(c.name)}", ""]
        parts[f"entities/{e}.tmdl"] = nl.join(lines)

    if single:
        rel_lines, erel_lines = [], []
        for r in single:
            rn = _relationship_name(r)
            rel_lines += [f"relationship {_tmdl(rn)}", f"\tfromColumn: {_tmdl(entity_name(r.source))}.{_tmdl(r.source_cols[0])}",
                          f"\ttoColumn: {_tmdl(entity_name(r.target))}.{_tmdl(r.target_cols[0])}", ""]
            en = _entity_relationship_name(r, plan)
            erel_lines += [f"/// {r.source}.{r.source_cols[0]} -> {r.target}.{r.target_cols[0]} by rule {r.rule}",
                           f"entityRelationship {_tmdl(en)}", f"\tlabel: {en}", f"\tlineageTag: {_tag(name, 'relationship', en)}",
                           f"\tfromEntity: {_tmdl(entity_name(r.source))}", f"\ttoEntity: {_tmdl(entity_name(r.target))}", "",
                           "\tbackingConfiguration", f"\t\trelationship: {_tmdl(rn)}", ""]
        parts["relationships.tmdl"] = nl.join(rel_lines)
        parts["entityRelationships.tmdl"] = nl.join(erel_lines)
    return parts


def envelope(name: str, parts: dict[str, str], description: str = "") -> dict:
    """The request body for POST /workspaces/{id}/ontologies (or updateDefinition without displayName)."""
    return {"displayName": name, "description": description or f"Generated by Krusgraph from the inferred plan: {len(parts)} parts.",
            "definition": {"parts": [{"path": p, "payload": base64.b64encode(text.encode("utf-8")).decode("ascii"), "payloadType": "InlineBase64"}
                                     for p, text in parts.items()]}}


def _ttl_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


_XSD = {"int64": "xsd:integer", "double": "xsd:double", "dateTime": "xsd:dateTime", "boolean": "xsd:boolean", "string": "xsd:string"}


def ontology_ttl(plan: Plan, name: str, schema: str = "dbo", tables: list[str] | None = None, base: str = "") -> str:
    """Turtle for the portal's Import ontology (an empty item): classes, datatype properties, object properties, with
    the rule in every description and the table in the class description. Bindings are not part of a TTL import."""
    check_tables(plan.schema, tables)
    wanted = {x.lower() for x in tables} if tables else None
    model = _model(plan, wanted)
    names = {t.name for t, *_ in model}
    base = base or f"urn:krusgraph:ontology:{_ident(name)}"
    out = ["@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .", "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
           "@prefix owl: <http://www.w3.org/2002/07/owl#> .", "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
           "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .", f"@prefix : <{base}#> .", "",
           f"<{base}> a owl:Ontology ;", f"    rdfs:label {_ttl_str(name)} ;",
           f"    rdfs:comment {_ttl_str('Generated by Krusgraph from inferred keys and relationships; every description names the rule (K0-K3, R0-R3).')} .", ""]
    for t, key, cols, rule in model:
        e = entity_name(t.name)
        keytxt = f"key {'+'.join(cols)} ({rule})" if cols else "no key (K3)"
        out += [f":{e} a owl:Class ;", f"    rdfs:label {_ttl_str(e)} ;", f"    skos:altLabel {_ttl_str(t.name)} ;",
                f"    rdfs:comment {_ttl_str(f'Table {schema}.{t.name}; {keytxt}.')} .", ""]
        for c in t.columns:
            comment = f"Column {c.name} ({c.data_type})" + ("; key." if c.name in cols else ".")
            out += [f":{e}__{_ident(c.name)} a owl:DatatypeProperty ;", f"    rdfs:label {_ttl_str(c.name)} ;", f"    rdfs:domain :{e} ;",
                    f"    rdfs:range {_XSD[prop_type(c.data_type)[0]]} ;", f"    rdfs:comment {_ttl_str(comment)} .", ""]
    for r in plan.relationships:
        if r.source not in names or r.target not in names:
            continue
        en = _entity_relationship_name(r, plan)
        comment = f"{r.source}.{'+'.join(r.source_cols)} -> {r.target}.{'+'.join(r.target_cols)} by rule {r.rule}."
        out += [f":{en} a owl:ObjectProperty ;", f"    rdfs:label {_ttl_str(en)} ;", f"    rdfs:domain :{entity_name(r.source)} ;",
                f"    rdfs:range :{entity_name(r.target)} ;", f"    rdfs:comment {_ttl_str(comment)} .", ""]
    return "\n".join(out)


def ontology_files(plan: Plan, name: str, *, workspace_id: str, item_id: str, item_name: str, item_kind: str = "Lakehouse",
                   schema: str = "dbo", sql_endpoint: str = "", tables: list[str] | None = None) -> dict[str, str]:
    """Everything as files under ontology/<name>/: the definition parts, the TTL, the bindings and a README."""
    parts = ontology_parts(plan, name, workspace_id=workspace_id, item_id=item_id, item_name=item_name, item_kind=item_kind,
                           schema=schema, sql_endpoint=sql_endpoint, tables=tables)
    folder = f"ontology/{_ident(name)}"
    files = {f"{folder}/definition/{p}": text for p, text in parts.items()}
    files[f"{folder}/{_ident(name)}.ttl"] = ontology_ttl(plan, name, schema, tables)
    files[f"{folder}/bindings.json"] = json.dumps(bindings(plan, item_name, schema, tables), indent=2) + "\n"
    files[f"{folder}/README.generated.md"] = _readme(name, summary(plan, tables), workspace_id)
    return files


def _readme(name: str, s: dict, workspace_id: str) -> str:
    notes = "".join(f"- {n}\n" for n in s["notes"]) or "- nothing; every entity type has a key and every relationship is single-column\n"
    return f"""# {name}: Fabric IQ ontology draft (generated)

{s['entity_types']} entity types ({s['with_key']} with a key), {s['relationship_types']} relationship types
({s['skipped_relationships']} composite-column relationships left for the portal).

Two ways in:

1. **REST / Git:** `definition/` is a generation-2 ontology item definition. Create the item with
   `POST https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/ontologies` and the parts base64-encoded
   (delegated scope `Item.ReadWrite.All`, Contributor on the workspace), or commit it through Git integration.
2. **Portal:** create an empty ontology item, *Import ontology* with the `.ttl` file (entity types, properties,
   relationships), then bind each entity type to its table following `bindings.json`.

To review before trusting:

{notes}
Ontology is in preview; its definition format can change. This draft follows the item's own definition as of 2026.
"""
