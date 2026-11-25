"""ON1 (issue #152, docs/SMOOTH/COMBINE-SOURCES.md): one shared Fabric IQ ontology over a plan of several sources.

A plan over several schemas of one item (`schema="sap+d365"`, multi_schema.py) holds each source's tables apart.
combine.py counts, by rules, which rows of two sources are the same customer (and, since ON1, the same product), and
the person accepts or rejects each match. This module turns that into one ontology:

- **One entity type per business concept** the catalog of data products (DP1, data_products/mapping.yaml) names for
  a table: Customer (`customer`, `crm_account` masters), Product (`product` masters), Order (`sales_order` headers),
  Invoice (`invoice` headers), Opportunity, Delivery and Case (their headers). Lines, texts and extensions are not
  entity types in this slice.
- **Shared** when the concept has a counted match the person accepted: one entity type (`Customer`, `Product`) bound
  to the conformed dimension the gold SQL builds (`gold.dim_customer`, `gold.dim_product`, combine.gold_sql), keyed on
  the conformed key. It records its source tables in both systems and the match's counts (matched, ambiguous, only in
  one source), the rule and the match's id.
- **Single-source** otherwise: one entity type per source table (`SapOrder`, `D365Order`), bound to that table in the
  product lakehouse. Orders and invoices are never matched across systems: no rule says an SAP order and a Dynamics
  order are the same order, and a guess is not a rule. A concept that only one source has (Delivery in SAP,
  Opportunity in Dataverse) is single-source by itself.
- **Relationships only where the plan proves them.** A transaction table re-keyed to `customer_key` (combine.facts,
  once the customer match is accepted) points at the shared Customer: the plan's own link to the party table, plus
  the accepted match. Every other relationship type is one of the plan's relationships between two entity tables,
  single-column, as ontology.py writes them. A link into a table that is now part of a shared entity, and a
  composite-column link, are listed under `notes`, not written. Nothing crosses sources otherwise.

Nothing here reads rows or writes to Fabric: `draft` takes the counts combine.count made, `parts` writes the item
definition. The server's `create_ontology` shows them as a dry run; creating the item waits until the pipeline builds
the conformed gold it binds to (kind `not_yet`, as the combined semantic model). Not run against Fabric.
"""
from __future__ import annotations

import json

from . import combine
from .ontology import PLATFORM_SCHEMA, _tag, _tmdl, entity_name, prop_type

GOLD = "gold"
# (entity type, DP1 catalog products, roles, the combine concept that matches it across sources or None)
CONCEPTS = (
    ("Customer", combine.PARTY, ("master",), "customer"),
    ("Product", ("product",), ("master",), "product"),
    ("Order", ("sales_order",), ("header",), None),
    ("Invoice", ("invoice",), ("header",), None),
    ("Opportunity", ("opportunity",), ("header",), None),
    ("Delivery", ("delivery",), ("header",), None),
    ("Case", ("case",), ("header",), None),
)


def concept_tables(plan) -> dict[str, dict[str, str]]:
    """{concept: {schema: table key}}: the first table per schema (plan order) whose DP1 entry is the concept's
    product in the concept's role. A matched concept takes combine.parties' table, so the match and the entity agree."""
    entries = combine._entries(plan)
    out: dict[str, dict[str, str]] = {}
    for name, products, roles, matched in CONCEPTS:
        found: dict[str, str] = {}
        if matched:
            found = {s: v["table"] for s, v in combine.parties(plan, matched).items()}
        else:
            for t in plan.schema:
                s = combine._schema_of(t.name)
                if s and s not in found and any(e.get("product") in products and e.get("role") in roles
                                                for e in entries.get(t.name, [])):
                    found[s] = t.name
        if found:
            out[name] = found
    return out


def _rule(plan, table: str, rule: str) -> str:
    """The rule as a person reads it: a pack rule names the pack of the table's own source (`sap pack`,
    `dynamics365 pack`), since a combined plan has one pack per schema."""
    pack = ((plan.pack or {}).get("by_schema") or {}).get(combine._schema_of(table))
    return f"{pack} pack" if rule == "SAP pack" and pack else rule


def _key(plan, table: str, columns: list[str]) -> tuple[str | None, list[str], str]:
    """(the ontology key or None, the plan's key columns, its rule) of a source table bound as it is."""
    cols, rule = plan.keys.get(table, ([], ""))
    types = {c.name: c.data_type for c in plan.schema[table].columns}
    key = cols[0] if len(cols) == 1 and cols[0] in columns and prop_type(types.get(cols[0], ""))[1] in ("string", "integer") else None
    return key, list(cols), _rule(plan, table, rule or "K3")


def _side(c: dict, side: str, role: str) -> dict:
    x = c[side]
    return {"source": x["schema"], "table": x["table"], "key": list(x["key"]), "column": x["column"], "role": role}


def _match_record(c: dict, state: str) -> dict:
    return {"id": c["id"], "state": state, "rule": c["rule"], "certainty": c.get("certainty"), "line": combine.match_line(c),
            "counts": dict(c["counts"]), "evidence": combine.evidence(c)}


def draft(plan, found: dict[str, dict], decisions, gold: str = GOLD) -> dict:
    """The shared ontology over a combined plan: {entities, relationships, matches, gold_sql, notes, summary}.
    `found` is {combine concept: combine.count(plan, execute, concept=...)}; `decisions` the flow state's (a match
    item accepted or rejected by the person). Counts and names only; no row value."""
    chosen = {k: combine.accepted(v, decisions) for k, v in found.items()}
    taken = {str(d.get("item")): d.get("review") for d in decisions or [] if isinstance(d, dict)}
    cust = chosen.get("customer")
    fact_list = (found.get("customer") or {}).get("facts") or [] if cust else []
    facts_by_table = {f["table"]: f for f in fact_list}
    tables = concept_tables(plan)
    entities: list[dict] = []
    owner: dict[str, str] = {}                     # source table -> entity type
    shared_of: dict[str, str] = {}                 # source table -> shared entity type it is part of
    gold_sql: dict[str, str] = {}
    matches: list[dict] = []
    notes: list[str] = []
    fact_schema = combine.model_schema(cust, plan, fact_list, gold) if cust else None
    for name, _products, _roles, mk in CONCEPTS:
        per = tables.get(name) or {}
        if not per:
            continue
        c = chosen.get(mk) if mk else None
        if mk and found.get(mk):
            best = next((x for x in found[mk]["candidates"] if x["id"] == found[mk].get("proposed")), None)
            if c:
                matches.append({"concept": name, **_match_record(c, "accepted")})
            elif best:
                state = "rejected" if taken.get(best["id"]) == "rejected" else "open"
                matches.append({"concept": name, **_match_record(best, state)})
        if c and c["to"]["table"] in per.values() and c["from"]["table"] in per.values():
            dim = combine.model_schema(c, plan, fact_list if mk == "customer" else [], gold, mk).tables[f"dim_{mk}"]
            sources = [_side(c, "to", f"master: each row is one {name}"),
                       _side(c, "from", f"matched to the master on {c['from']['column']} ({c['rule']})")]
            entities.append({
                "name": name, "concept": name, "shared": True, "sources": sources,
                "match": _match_record(c, "accepted"),
                "binding": {"schema": gold, "table": dim.name, "built_by": "gold_sql"},
                "key": f"{mk}_key", "key_columns": [f"{mk}_key"], "key_rule": f"conformed key ({c['rule']}, accepted)",
                "properties": [{"name": x.name, "type": prop_type(x.data_type)[1], "source_type": x.data_type} for x in dim.columns]})
            for s in sources:
                owner[s["table"]] = shared_of[s["table"]] = name
            gold_sql.update(combine.gold_sql(c, plan, fact_list if mk == "customer" else [], gold, concept=mk))
            continue
        for schema, table in per.items():
            e = entity_name(f"{schema}_{name}")
            f = facts_by_table.get(table)
            if f is not None:                       # re-keyed to customer_key by the accepted customer match
                cols = [(x.name, x.data_type) for x in fact_schema.tables[f["name"]].columns]
                binding = {"schema": gold, "table": f["name"], "built_by": "gold_sql"}
            else:
                cols = [(x.name, x.data_type) for x in plan.schema[table].columns]
                binding = {"schema": schema, "table": table.split(".", 1)[-1], "built_by": "source"}
            key, kcols, rule = _key(plan, table, [n for n, _ in cols])
            if key is None:
                notes.append(f"{e}: {'composite key ' + '+'.join(kcols) if len(kcols) > 1 else 'no single string or integer key'}"
                             f"; the entity type is keyless (as ontology.py writes it). Pick or add one key in the portal.")
            entities.append({
                "name": e, "concept": name, "shared": False,
                "sources": [{"source": schema, "table": table, "key": kcols, "role": "the only source of this entity type"}],
                "match": None, "binding": binding, "key": key, "key_columns": kcols, "key_rule": rule,
                "properties": [{"name": n, "type": prop_type(t)[1], "source_type": t} for n, t in cols]})
            owner[table] = e
        if len(per) > 1 and not mk:
            notes.append(f"{name}: in {' and '.join(sorted(per))}, one entity type per source. No rule matches "
                         f"{name.lower()}s across sources, so none is guessed.")
    relationships = _relationships(plan, entities, owner, shared_of, facts_by_table, cust, notes)
    summary = {"entity_types": len(entities), "shared": [e["name"] for e in entities if e["shared"]],
               "single_source": [e["name"] for e in entities if not e["shared"]],
               "with_key": sum(1 for e in entities if e["key"]), "relationship_types": len(relationships),
               "sources": sorted({s["source"] for e in entities for s in e["sources"]})}
    return {"entities": entities, "relationships": relationships, "matches": matches, "gold_sql": gold_sql,
            "notes": notes, "summary": summary}


def _relationships(plan, entities, owner, shared_of, facts_by_table, cust, notes) -> list[dict]:
    """The plan's proof, and nothing else (see the module's text)."""
    out: list[dict] = []
    names: dict[str, int] = {}

    def add(frm: str, to: str, fc: str, tc: str, proof: dict):
        base = f"{frm}Has{to}"
        names[base] = names.get(base, 0) + 1
        name = base if names[base] == 1 else f"{frm}_{combine._joined(fc) or 'x'}_{to}"
        out.append({"name": name, "from": frm, "to": to, "from_column": fc, "to_column": tc, "proof": proof})

    rekeyed = set()
    for table, f in facts_by_table.items():
        if table not in owner:
            continue
        r = next((r for r in plan.relationships if r.source == table and list(r.source_cols) == f["cols"]), None)
        add(owner[table], "Customer", "customer_key", "customer_key",
            {"plan": f"{table}.{'+'.join(f['cols'])} -> {r.target if r else ''}.{'+'.join(f['party_cols'])}",
             "rule": _rule(plan, table, r.rule) if r else "", "match": cust["id"], "via": f"{GOLD}.xref_customer"})
        rekeyed.add((table, tuple(f["cols"])))
    for r in plan.relationships:
        if r.source not in owner or r.target not in owner or r.source == r.target:
            continue
        rule = _rule(plan, r.source, r.rule)
        said = f"{r.source}.{'+'.join(r.source_cols)} -> {r.target}.{'+'.join(r.target_cols)} ({rule})"
        if (r.source, tuple(r.source_cols)) in rekeyed:
            continue
        if r.target in shared_of or r.source in shared_of:
            notes.append(f"Not related: {said}. The table is part of the shared {shared_of.get(r.target) or shared_of.get(r.source)}; "
                         f"only a table re-keyed to its conformed key points at it.")
            continue
        if len(r.source_cols) != 1 or len(r.target_cols) != 1:
            notes.append(f"Not related: {said} is a composite-column link; bind it in the portal (as ontology.py does).")
            continue
        add(owner[r.source], owner[r.target], r.source_cols[0], r.target_cols[0], {"plan": said, "rule": rule})
    for x in getattr(plan, "extended", None) or []:          # filtered (polymorphic) lookups: counted, never plain links
        if x.source in owner and x.target in owner and x.source != x.target and getattr(x, "where", None):
            only = "; ".join(f"{w.get('column')} in {list(w.get('in') or [])}" for w in x.where if isinstance(w, dict))
            notes.append(f"Not related: {x.source}.{'+'.join(x.source_cols)} -> {x.target}.{'+'.join(x.target_cols)} holds "
                         f"only where {only} (a filtered link); the ontology relates plain links of the plan only.")
    return out


def parts(model: dict, name: str, *, workspace_id: str, item_id: str, item_name: str, item_kind: str = "Lakehouse",
          sql_endpoint: str = "") -> dict[str, str]:
    """The item definition (generation 2, TMDL), as ontology.ontology_parts writes it, with each entity type bound to
    its own schema of the product lakehouse (gold for shared entities and re-keyed facts, the source's otherwise) and
    its sources and match counts in its description."""
    ents = model["entities"]
    if not ents:
        raise ValueError("the shared ontology would be empty: no concept table in the plan")
    nl, ns = "\n", "default"
    expr = f"DirectLake - {item_name}"
    out: dict[str, str] = {
        ".platform": json.dumps({"$schema": PLATFORM_SCHEMA, "metadata": {"type": "Ontology", "displayName": name},
                                 "config": {"version": "2.0", "logicalId": "00000000-0000-0000-0000-000000000000"}}, indent=2) + nl,
        "database.tmdl": f"database {_tmdl(name)}{nl}\tcompatibilityLevel: 1000000{nl}",
        f"namespaces/{ns}.tmdl": f"namespace {_tmdl(ns)}{nl}\tlineageTag: {ns}{nl}",
        "expressions.tmdl": nl.join([
            f"expression {_tmdl(expr)} =", "\t\tlet",
            f'\t\t    Source = AzureStorage.DataLake("https://onelake.dfs.fabric.microsoft.com/{workspace_id}/{item_id}", [HierarchicalNavigation=true])',
            "\t\tin", "\t\t    Source", f"\tlineageTag: {_tag(name, 'expression', item_id)}", ""]),
    }
    model_lines = [f"model {_tmdl(name)}", ""] + [f"ref table {_tmdl(e['name'])}" for e in ents] + [""]
    model_lines += [f"ref entity {_tmdl(e['name'])}" for e in ents] + ["", f"ref namespace {_tmdl(ns)}", ""]
    out["model.tmdl"] = nl.join(model_lines)
    for e in ents:
        n, b = e["name"], e["binding"]
        lines = [f"table {_tmdl(n)}", f"\tlineageTag: {_tag(name, 'table', n)}", ""]
        for p in e["properties"]:
            lines += [f"\tcolumn {_tmdl(p['name'])}", f"\t\tdataType: {prop_type(p['source_type'])[0]}",
                      f"\t\tlineageTag: {_tag(name, 'column', n, p['name'])}", f"\t\tsourceColumn: {p['name']}", ""]
        lines += [f"\tpartition {_tmdl(n)} = entity", "\t\tmode: directLake", "\t\tsource", f"\t\t\tentityName: {b['table']}",
                  f"\t\t\tschemaName: {b['schema']}", f"\t\t\texpressionSource: {_tmdl(expr)}", ""]
        for k, v in (("ONT_WorkspaceId", workspace_id), ("ONT_ItemId", item_id), ("ONT_ItemKind", item_kind),
                     ("ONT_ItemName", item_name), ("ONT_SqlEndpoint", sql_endpoint), ("ONT_SqlDatabase", item_name)):
            if v:
                lines += [f"\t\tannotation {k} = {v}", ""]
        out[f"tables/{n}.tmdl"] = nl.join(lines)
        srcs = "; ".join(f"{s['table']} ({'+'.join(s['key'])})" for s in e["sources"])
        desc = [f"/// {e['concept']} from {srcs}"]
        if e["match"]:
            desc.append(f"/// {e['match']['id']} ({e['match']['rule']}, accepted): {e['match']['line']}")
        lines = desc + [f"entity {_tmdl(n)}", f"\tlineageTag: {_tag(name, 'entity', n)}", f"\tbackingTable: {_tmdl(n)}"]
        if e["key"]:
            lines.append(f"\tkeyProperty: {_tmdl(e['key'])}")
        lines.append("")
        for p in e["properties"]:
            lines += [f"\tproperty {_tmdl(p['name'])}", f"\t\tdataType: {prop_type(p['source_type'])[0]}",
                      f"\t\tlineageTag: {_tag(name, 'column', n, p['name'])}", "", "\t\tbackingConfiguration",
                      f"\t\t\tvalueColumn: {_tmdl(n)}.{_tmdl(p['name'])}", ""]
        out[f"entities/{n}.tmdl"] = nl.join(lines)
    rels = model["relationships"]
    if rels:
        rel_lines, erel_lines = [], []
        for r in rels:
            rn = f"{r['from']}_{r['from_column']}_{r['to']}"
            rel_lines += [f"relationship {_tmdl(rn)}", f"\tfromColumn: {_tmdl(r['from'])}.{_tmdl(r['from_column'])}",
                          f"\ttoColumn: {_tmdl(r['to'])}.{_tmdl(r['to_column'])}", ""]
            proof = r["proof"]["plan"] + (f" by rule {r['proof']['rule']}" if r["proof"].get("rule") else "")
            if r["proof"].get("match"):
                proof += f", through the accepted {r['proof']['match']}"
            erel_lines += [f"/// {proof}", f"entityRelationship {_tmdl(r['name'])}", f"\tlabel: {r['name']}",
                           f"\tlineageTag: {_tag(name, 'relationship', r['name'])}", f"\tfromEntity: {_tmdl(r['from'])}",
                           f"\ttoEntity: {_tmdl(r['to'])}", "", "\tbackingConfiguration", f"\t\trelationship: {_tmdl(rn)}", ""]
        out["relationships.tmdl"] = nl.join(rel_lines)
        out["entityRelationships.tmdl"] = nl.join(erel_lines)
    return out


def line(model: dict) -> str:
    """'SAP + D365 → 8 entity types: Customer and Product shared, 6 from one source; 4 relationship types.'"""
    s = model["summary"]
    srcs = " + ".join(combine._source_word(x) for x in s["sources"])
    shared = " and ".join(s["shared"]) or "none"
    return (f"{srcs} {chr(8594)} {s['entity_types']} entity types: {shared} shared, {len(s['single_source'])} from one "
            f"source; {s['relationship_types']} relationship types.")
