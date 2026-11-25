"""verify_build: what was built in Fabric, read back and compared with the dry run. Read-only, by rules (round n229).

The founder, 12 November 2026, after building what his chat proposed: "an agent that double-checks Krusgraph's
deployed proposals". Krusgraph for Fabric uses no AI model, so this is a verifier, not an agent: every line below is a
comparison or a count a person can repeat, and the answer says so (LABEL). Nothing here writes, and nothing here talks
to Fabric: the caller (server.verify_build, workload_api.run_verify, the tests) hands in what it read.

Four kinds of checks, each ending in one of three states (STATES), never in a guess:

1. The definition, read back. The expected side is the dry run's definition, built again by the same rules from the
   same plan and arguments (a dry run is a pure function of them, so "the dry run that was confirmed" and "the dry run
   built now" are the same text unless the source changed in between; the answer says that too). The actual side is the
   item's getDefinition. Compared per item type:
     semantic model   tables, each table's source table and columns (the combined key columns of a composite key among
                      them), relationships (both ends, active or inactive, cardinality, cross-filter), measures and the
                      table each sits on (its level), each measure's expression
     report           the model it is bound to, the visuals by type, title and fields
     ontology         entity types, the key of each, properties and their data binding (the bound column), the bound
                      table and schema, relationship types and their ends
     API for GraphQL  types, fields, relationships with their cardinality, what can be written
     pipeline         the steps in order, what each waits for, the notebook each runs
     notebook         the code cells' sources, line by line (the markers, the metadata blocks, which hold ids, and the
                      markdown are left out, as Fabric writes them its own way; AP3b); a notebook an earlier
                      Krusgraph wrote is said to be one
2. The figures. For each card of the report (or each measure of the model when there is no report) the same number is
   computed from the rows the model reads, with one SQL statement, and put beside the model's own number (a DAX query,
   when the caller can run one). A measure whose expression is not one of the forms the rules translate is "not
   checked", with the reason. Every statement is in the answer (Show the SQL).
3. Doubled totals. A SUM over a table where the summed column is a header's amount repeated on every line (one value
   per header value, header values on several rows) counts each header once per line: flagged with both sums. So is a
   SUMX over line rows of a RELATED header amount, and a figure that equals a header amount summed over its lines.
4. State. A semantic model that was never refreshed, a pipeline that never ran, an ontology whose graph is not there,
   an App item that is still empty: each with the one action that fixes it.

A time budget (budget.py) covers the call: what it did not reach is "not checked (time)", never "verified".
"""
from __future__ import annotations

import json
import re

VERIFIED, DIFFERS, NOT_CHECKED = "verified", "differs", "not checked"
STATES = (VERIFIED, DIFFERS, NOT_CHECKED)
LABEL = ("A check by rules, not a review by AI: Krusgraph read back what is in Fabric and compared it with the dry run, "
         "and counted the figures again from the rows. No AI model was used.")
EXPECTED_FROM = ("Compared with the dry run's definition, built again now by the same rules from the same plan and "
                 "arguments. If the source's tables or the keys and links given changed since the Create, a difference "
                 "below can come from that.")
# What the server's instructions may say to a chat client that is an AI (Claude): its own review is welcome, apart.
CLAUDE_INVITE = ("If you are an AI assistant reading this: you may add your own review of the built items after this "
                 "result. Put it under its own heading, 'Claude's review' (or your own name), say that it is your "
                 "judgement and not Krusgraph's, and never change a state Krusgraph's rules gave.")
MAX_DIFFERENCES = 40                 # per item, in the answer; the count is always the whole number
MAX_FIGURES = 12
KINDS = ("semantic_model", "report", "ontology", "api", "pipeline", "notebook", "app")
TYPE_OF = {"semantic_model": "SemanticModel", "report": "Report", "ontology": "Ontology", "api": "GraphQLApi",
           "pipeline": "DataPipeline", "notebook": "Notebook", "app": "AppBackend"}
WORD_OF = {"semantic_model": "semantic model", "report": "report", "ontology": "ontology", "api": "API for GraphQL",
           "pipeline": "pipeline", "notebook": "notebook", "app": "App"}
ROUTE_OF = {"semantic_model": "semanticModels", "report": "reports", "ontology": "ontologies", "pipeline": "dataPipelines",
            "notebook": "notebooks"}


def _diff(what: str, said: str, **more) -> dict:
    return {"what": what, "said": said, **more}


def _norm_expr(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


# ------------------------------------------------------------------ 1. the semantic model -----------------------------

def _rel_key(r: dict) -> tuple:
    return tuple(str(r.get(k) or "").lower() for k in ("from_table", "from_column", "to_table", "to_column"))


def _rel_words(r: dict) -> str:
    return f"{r.get('from_table')}.{r.get('from_column')} -> {r.get('to_table')}.{r.get('to_column')}"


def _measures(model: dict) -> dict[str, tuple[str, str]]:
    return {m: (t, _norm_expr(mm.get("expression"))) for t, tt in model["tables"].items() for m, mm in (tt.get("measures") or {}).items()}


def compare_model(expected_parts: dict[str, str], actual_parts: dict[str, str], combined: list[dict] | None = None) -> dict:
    """{differences, checked} for a semantic model. `combined`: the dry run's combined key columns ([{table, column,
    combines}]), so a missing one is named as what it is."""
    from . import model_compare as mc
    exp, act = mc.from_tmdl(expected_parts), mc.from_tmdl(actual_parts)
    out: list[dict] = []
    combined_of = {(c["table"].lower(), c["column"].lower()): c for c in combined or []}
    et, at = {t.lower(): t for t in exp["tables"]}, {t.lower(): t for t in act["tables"]}
    for low in sorted(set(et) - set(at)):
        out.append(_diff("table", f"Table {et[low]} is in the dry run and not in the model in Fabric."))
    for low in sorted(set(at) - set(et)):
        out.append(_diff("table", f"Table {at[low]} is in the model in Fabric and not in the dry run."))
    for low in sorted(set(et) & set(at)):
        e, a = exp["tables"][et[low]], act["tables"][at[low]]
        if (e.get("source"), e.get("source_schema")) != (a.get("source"), a.get("source_schema")) and e.get("source"):
            out.append(_diff("table", f"Table {et[low]} reads {a.get('source_schema') or '(no schema)'}.{a.get('source')} in Fabric; "
                                      f"the dry run reads {e.get('source_schema') or '(no schema)'}.{e.get('source')}."))
        ec, ac = {c.lower(): c for c in e["columns"]}, {c.lower(): c for c in a["columns"]}
        for c in sorted(set(ec) - set(ac)):
            comb = combined_of.get((low, c))
            out.append(_diff("column", f"Column {et[low]}.{ec[c]} is in the dry run and not in Fabric"
                                       + (f": the combined key column for {' + '.join(comb['combines'])}." if comb else ".")))
        for c in sorted(set(ac) - set(ec)):
            out.append(_diff("column", f"Column {at[low]}.{ac[c]} is in Fabric and not in the dry run."))
        for c in sorted(set(ec) & set(ac)):
            if bool(e["columns"][ec[c]].get("is_key")) != bool(a["columns"][ac[c]].get("is_key")):
                out.append(_diff("column", f"Column {et[low]}.{ec[c]} is {'the key' if e['columns'][ec[c]].get('is_key') else 'not a key'} "
                                           f"in the dry run and {'the key' if a['columns'][ac[c]].get('is_key') else 'not a key'} in Fabric."))
    er, ar = {_rel_key(r): r for r in exp["relationships"]}, {_rel_key(r): r for r in act["relationships"]}
    for k in sorted(set(er) - set(ar)):
        out.append(_diff("relationship", f"Relationship {_rel_words(er[k])} is in the dry run and not in Fabric."))
    for k in sorted(set(ar) - set(er)):
        out.append(_diff("relationship", f"Relationship {_rel_words(ar[k])} is in Fabric and not in the dry run."))
    for k in sorted(set(er) & set(ar)):
        e, a = er[k], ar[k]
        if bool(e.get("active", True)) != bool(a.get("active", True)):
            out.append(_diff("relationship", f"Relationship {_rel_words(e)} is {'active' if e.get('active', True) else 'inactive'} in the "
                                             f"dry run and {'active' if a.get('active', True) else 'inactive'} in Fabric."))
        ecard, acard = (e.get("from_cardinality"), e.get("to_cardinality")), (a.get("from_cardinality"), a.get("to_cardinality"))
        if ecard != acard:
            out.append(_diff("relationship", f"Relationship {_rel_words(e)} is {ecard[0]}-to-{ecard[1]} in the dry run and "
                                             f"{acard[0]}-to-{acard[1]} in Fabric."))
        if str(e.get("cross_filter") or "").lower() != str(a.get("cross_filter") or "").lower():
            out.append(_diff("relationship", f"Relationship {_rel_words(e)} filters {e.get('cross_filter')} in the dry run and "
                                             f"{a.get('cross_filter')} in Fabric."))
    em, am = _measures(exp), _measures(act)
    for m in sorted(set(em) - set(am)):
        out.append(_diff("measure", f"Measure {em[m][0]}[{m}] is in the dry run and not in Fabric."))
    for m in sorted(set(am) - set(em)):
        out.append(_diff("measure", f"Measure {am[m][0]}[{m}] is in Fabric and not in the dry run."))
    for m in sorted(set(em) & set(am)):
        if em[m][0].lower() != am[m][0].lower():
            out.append(_diff("measure", f"Measure {m} sits on {am[m][0]} in Fabric and on {em[m][0]} in the dry run: another level."))
        if em[m][1] != am[m][1]:
            out.append(_diff("measure", f"Measure {m} is {am[m][1]} in Fabric and {em[m][1]} in the dry run."))
    active = sum(1 for r in exp["relationships"] if r.get("active", True))
    return {"differences": out, "model": act,
            "checked": {"tables": len(exp["tables"]), "relationships": len(exp["relationships"]), "active": active,
                        "inactive": len(exp["relationships"]) - active, "measures": len(em),
                        "combined_key_columns": len(combined_of)}}


# ------------------------------------------------------------------ the report ----------------------------------------

def _literal(node) -> str | None:
    try:
        v = node["expr"]["Literal"]["Value"]
    except (KeyError, TypeError):
        return None
    return v[1:-1].replace("''", "'") if isinstance(v, str) and len(v) >= 2 and v[0] == "'" and v[-1] == "'" else v


def report_shape(parts: dict[str, str]) -> dict:
    """{model_id, visuals: [{type, title, fields}]} of a PBIR definition; text boxes are left out (the footnote holds a date)."""
    model_id, visuals = None, []
    for path in sorted(parts):
        try:
            body = json.loads(parts[path])
        except (TypeError, ValueError):
            continue
        if path.endswith("definition.pbir"):
            conn = str((((body.get("datasetReference") or {}).get("byConnection") or {}).get("connectionString")) or "")
            m = re.search(r"semanticmodelid=([0-9a-fA-F-]{36})", conn)
            model_id = m.group(1).lower() if m else None
        elif path.endswith("/visual.json"):
            v = body.get("visual") or {}
            if v.get("visualType") in (None, "textbox"):
                continue
            state = (v.get("query") or {}).get("queryState") or {}
            fields = [p.get("queryRef") for role in sorted(state) for p in (state[role].get("projections") or []) if p.get("queryRef")]
            title = None
            for t in ((v.get("visualContainerObjects") or {}).get("title") or []):
                title = _literal((t.get("properties") or {}).get("text")) or title
            visuals.append({"type": v["visualType"], "title": title, "fields": fields})
    return {"model_id": model_id, "visuals": visuals}


def compare_report(expected_parts: dict[str, str], actual_parts: dict[str, str]) -> dict:
    exp, act = report_shape(expected_parts), report_shape(actual_parts)
    out = []
    if exp["model_id"] and act["model_id"] and exp["model_id"] != act["model_id"]:
        out.append(_diff("model", f"The report in Fabric is bound to the semantic model {act['model_id']}, the dry run to {exp['model_id']}."))
    key = lambda v: (v["type"], tuple(v["fields"]))
    ev, av = {key(v): v for v in exp["visuals"]}, {key(v): v for v in act["visuals"]}
    words = lambda v: f"{v['type']} {v.get('title') or ''} ({', '.join(v['fields'])})".replace("  ", " ")
    for k in sorted(set(ev) - set(av)):
        out.append(_diff("visual", f"Visual {words(ev[k])} is in the dry run and not in Fabric."))
    for k in sorted(set(av) - set(ev)):
        out.append(_diff("visual", f"Visual {words(av[k])} is in Fabric and not in the dry run."))
    for k in sorted(set(ev) & set(av)):
        if (ev[k].get("title") or "") != (av[k].get("title") or ""):
            out.append(_diff("visual", f"Visual {words(ev[k])} is titled {av[k].get('title')!r} in Fabric."))
    return {"differences": out, "checked": {"visuals": len(exp["visuals"])}, "shape": act}


# ------------------------------------------------------------------ the ontology --------------------------------------

_ONT_OBJ = re.compile(r"^(\t*)(entityRelationship|entity|property|relationship|table|column|partition)\s+(.+?)\s*(?:=\s*\S+)?\s*$")
_ONT_PROP = re.compile(r"^\t*([A-Za-z][A-Za-z0-9]*)\s*:\s*(.*)$")


def ontology_shape(parts: dict[str, str]) -> dict:
    """{entities: {name: {key, backing, properties: {name: {type, column}}}}, relationships: {name: {from, to}} (the
    backing relationships: column to column), entity_relationships: {name: {from, to, backing}} (the relationship types:
    entity to entity, each bound to a backing relationship), tables: {name: {entity, schema}}} of an ontology definition
    (the generation-2 layout ontology.py writes)."""
    ent, rel, tab, erel = {}, {}, {}, {}
    for path in sorted(parts):
        if not path.endswith(".tmdl"):
            continue
        top = prop = None
        kind = None
        for raw in str(parts[path]).splitlines():
            if not raw.strip() or raw.strip().startswith("///"):
                continue
            depth = len(raw) - len(raw.lstrip("\t"))
            o = _ONT_OBJ.match(raw)
            if o and depth == 0 and o.group(2) in ("entity", "relationship", "table", "entityRelationship"):
                name = o.group(3).strip().strip("'")
                kind, prop = o.group(2), None
                top = {"entity": ent, "relationship": rel, "table": tab, "entityRelationship": erel}[kind].setdefault(
                    name, {"key": None, "backing": None, "properties": {}} if kind == "entity" else
                    {"from": None, "to": None} if kind == "relationship" else
                    {"from": None, "to": None, "backing": None} if kind == "entityRelationship" else {"entity": None, "schema": None})
                continue
            if depth == 0:
                top = kind = None
                continue
            if top is None:
                continue
            if o and depth == 1 and kind == "entity" and o.group(2) == "property":
                prop = top["properties"].setdefault(o.group(3).strip().strip("'"), {"type": None, "column": None})
                continue
            if o and depth == 1:
                prop = None
            p = _ONT_PROP.match(raw)
            if not p:
                continue
            k, v = p.group(1), p.group(2).strip().strip("'")
            if kind == "entity":
                if depth == 1 and k == "keyProperty":
                    top["key"] = v
                elif depth == 1 and k == "backingTable":
                    top["backing"] = v
                elif prop is not None and k == "dataType" and depth == 2:
                    prop["type"] = v
                elif prop is not None and k == "valueColumn":
                    prop["column"] = v
            elif kind == "relationship":
                if k == "fromColumn":
                    top["from"] = v
                elif k == "toColumn":
                    top["to"] = v
            elif kind == "entityRelationship":
                if k == "fromEntity":
                    top["from"] = v
                elif k == "toEntity":
                    top["to"] = v
                elif k == "relationship":
                    top["backing"] = v
            elif kind == "table":
                if k == "entityName":
                    top["entity"] = v
                elif k == "schemaName":
                    top["schema"] = v
    return {"entities": ent, "relationships": rel, "tables": tab, "entity_relationships": erel}


def compare_ontology(expected_parts: dict[str, str], actual_parts: dict[str, str]) -> dict:
    exp, act = ontology_shape(expected_parts), ontology_shape(actual_parts)
    out = []
    for n in sorted(set(exp["entities"]) - set(act["entities"])):
        out.append(_diff("entity", f"Entity type {n} is in the dry run and not in Fabric."))
    for n in sorted(set(act["entities"]) - set(exp["entities"])):
        out.append(_diff("entity", f"Entity type {n} is in Fabric and not in the dry run."))
    for n in sorted(set(exp["entities"]) & set(act["entities"])):
        e, a = exp["entities"][n], act["entities"][n]
        if e["key"] != a["key"]:
            out.append(_diff("key", f"Entity type {n} has the key {a['key'] or '(none)'} in Fabric and {e['key'] or '(none)'} in the dry run."))
        for p in sorted(set(e["properties"]) - set(a["properties"])):
            out.append(_diff("property", f"Property {n}.{p} is in the dry run and not in Fabric."))
        for p in sorted(set(a["properties"]) - set(e["properties"])):
            out.append(_diff("property", f"Property {n}.{p} is in Fabric and not in the dry run."))
        for p in sorted(set(e["properties"]) & set(a["properties"])):
            if e["properties"][p]["column"] != a["properties"][p]["column"]:
                out.append(_diff("binding", f"Property {n}.{p} is bound to {a['properties'][p]['column'] or '(nothing)'} in Fabric and to "
                                            f"{e['properties'][p]['column'] or '(nothing)'} in the dry run."))
    for n in sorted(set(exp["tables"]) & set(act["tables"])):
        e, a = exp["tables"][n], act["tables"][n]
        if (e["entity"], e["schema"]) != (a["entity"], a["schema"]):
            out.append(_diff("binding", f"{n} is bound to the table {a['schema'] or '(no schema)'}.{a['entity']} in Fabric and to "
                                        f"{e['schema'] or '(no schema)'}.{e['entity']} in the dry run."))
    for n in sorted(set(exp["tables"]) - set(act["tables"])):
        out.append(_diff("binding", f"The data binding of {n} is in the dry run and not in Fabric."))
    for n in sorted(set(exp["entity_relationships"]) - set(act["entity_relationships"])):
        e = exp["entity_relationships"][n]
        out.append(_diff("relationship", f"Relationship type {n} ({e['from']} -> {e['to']}) is in the dry run and not in Fabric."))
    for n in sorted(set(act["entity_relationships"]) - set(exp["entity_relationships"])):
        a = act["entity_relationships"][n]
        out.append(_diff("relationship", f"Relationship type {n} ({a['from']} -> {a['to']}) is in Fabric and not in the dry run."))
    for n in sorted(set(exp["entity_relationships"]) & set(act["entity_relationships"])):
        e, a = exp["entity_relationships"][n], act["entity_relationships"][n]
        if (e["from"], e["to"]) != (a["from"], a["to"]):
            out.append(_diff("relationship", f"Relationship type {n} goes {a['from']} -> {a['to']} in Fabric and {e['from']} -> {e['to']} in the dry run."))
        if e["backing"] != a["backing"]:
            out.append(_diff("binding", f"Relationship type {n} is bound to {a['backing'] or '(nothing)'} in Fabric and to "
                                        f"{e['backing'] or '(nothing)'} in the dry run."))
    for n in sorted(set(exp["relationships"]) - set(act["relationships"])):
        out.append(_diff("binding", f"The column binding {n} of a relationship type is in the dry run and not in Fabric."))
    for n in sorted(set(act["relationships"]) - set(exp["relationships"])):
        out.append(_diff("binding", f"The column binding {n} is in Fabric and not in the dry run."))
    for n in sorted(set(exp["relationships"]) & set(act["relationships"])):
        e, a = exp["relationships"][n], act["relationships"][n]
        if (e["from"], e["to"]) != (a["from"], a["to"]):
            out.append(_diff("binding", f"The column binding {n} goes {a['from']} -> {a['to']} in Fabric and {e['from']} -> {e['to']} in the dry run."))
    return {"differences": out,
            "checked": {"entity_types": len(exp["entities"]), "with_key": sum(1 for e in exp["entities"].values() if e["key"]),
                        "relationship_types": len(exp["entity_relationships"]), "data_bindings": len(exp["tables"]) + len(exp["relationships"])}}


# ------------------------------------------------------------------ API for GraphQL, pipeline, notebook ---------------

def api_shape(definition: dict) -> dict:
    types = {}
    for ds in (definition or {}).get("datasources", []):
        for o in ds.get("objects", []):
            actions = o.get("actions") or {}
            types[str(o.get("graphqlType"))] = {
                "source": o.get("sourceObject"), "fields": sorted((o.get("fieldMappings") or {}).values()),
                "relationships": {str(r.get("field")): (r.get("targetObject"), r.get("cardinality")) for r in o.get("relationships", [])},
                "writable": any(actions.get(a) == "Enabled" for a in ("Create", "Update", "Delete"))}
    return types


def compare_api(expected: dict, actual: dict) -> dict:
    exp, act = api_shape(expected), api_shape(actual)
    out = []
    for t in sorted(set(exp) - set(act)):
        out.append(_diff("type", f"Type {t} is in the dry run and not in the API in Fabric."))
    for t in sorted(set(act) - set(exp)):
        out.append(_diff("type", f"Type {t} is in the API in Fabric and not in the dry run."))
    for t in sorted(set(exp) & set(act)):
        e, a = exp[t], act[t]
        if e["source"] != a["source"]:
            out.append(_diff("type", f"Type {t} reads {a['source']} in Fabric and {e['source']} in the dry run."))
        for f in sorted(set(e["fields"]) - set(a["fields"])):
            out.append(_diff("field", f"Field {t}.{f} is in the dry run and not in Fabric."))
        for f in sorted(set(a["fields"]) - set(e["fields"])):
            out.append(_diff("field", f"Field {t}.{f} is in Fabric and not in the dry run."))
        for r in sorted(set(e["relationships"]) - set(a["relationships"])):
            out.append(_diff("relationship", f"Relationship {t}.{r} is in the dry run and not in Fabric."))
        for r in sorted(set(a["relationships"]) - set(e["relationships"])):
            out.append(_diff("relationship", f"Relationship {t}.{r} is in Fabric and not in the dry run."))
        for r in sorted(set(e["relationships"]) & set(a["relationships"])):
            if e["relationships"][r] != a["relationships"][r]:
                out.append(_diff("relationship", f"Relationship {t}.{r} goes to {a['relationships'][r][0]} ({a['relationships'][r][1]}) in "
                                                 f"Fabric and to {e['relationships'][r][0]} ({e['relationships'][r][1]}) in the dry run."))
        if e["writable"] != a["writable"]:
            out.append(_diff("type", f"Type {t} is {'writable' if a['writable'] else 'read-only'} in Fabric and "
                                     f"{'writable' if e['writable'] else 'read-only'} in the dry run."))
    return {"differences": out, "checked": {"types": len(exp), "relationships": sum(len(t["relationships"]) for t in exp.values())}}


def pipeline_steps(content: dict, names: dict[str, str] | None = None) -> list[dict]:
    """[{step, type, after, notebook}] of a pipeline-content.json; `names` maps a notebook id to its name."""
    names = {k.lower(): v for k, v in (names or {}).items()}
    out = []
    for a in ((content or {}).get("properties") or {}).get("activities") or []:
        nb = str(((a.get("typeProperties") or {}).get("notebookId")) or "")
        out.append({"step": a.get("name"), "type": a.get("type"),
                    "after": [(d.get("activity"), tuple(d.get("dependencyConditions") or [])) for d in a.get("dependsOn") or []],
                    "notebook": names.get(nb.lower(), nb)})
    return out


_SCHEMA_NAME = re.compile(r"^\s*schemaName:\s*(\S+)\s*$", re.M)


def model_schemas(parts: dict) -> set[str]:
    """W4: the schemas a semantic model's Direct Lake partitions read (schemaName in its TMDL tables), lower case."""
    return {m.group(1).strip("'\"").lower() for path, text in (parts or {}).items()
            if str(path).startswith("definition/tables/") for m in _SCHEMA_NAME.finditer(str(text or ""))}


def model_basis(actual_schemas: set[str], gold_schema: str) -> str:
    """W4 (Gustav's tenant test, 24 November 2026): which dry run a semantic model is compared with, by rules. "gold":
    the dry run of a build with gold views (DPM1: the model reads them), when every partition of the model in Fabric
    reads the gold schema; "source" otherwise (the model on the plan's tables, or on silver). Only the choice between
    the two dry runs is made from the item; what is compared (tables, relationships, measures) is the dry run's. Before,
    a model built on gold was compared with the model on the source and read as "differs" for that alone."""
    if actual_schemas and actual_schemas == {str(gold_schema or "").lower()}:
        return "gold"
    return "source"


def compare_pipeline(expected: dict, actual: dict, expected_names: dict[str, str] | None = None,
                     actual_names: dict[str, str] | None = None, notebooks_known: bool = True) -> dict:
    """`expected_names` / `actual_names`: notebook id -> name on either side. With notebooks_known false the notebook a
    step runs is not compared (its name could not be read), and that is said by the caller."""
    exp, act = pipeline_steps(expected, expected_names), pipeline_steps(actual, actual_names)
    out = []
    if [s["step"] for s in exp] != [s["step"] for s in act]:
        out.append(_diff("steps", f"The steps in Fabric are {', '.join(str(s['step']) for s in act) or '(none)'}; the dry run has "
                                  f"{', '.join(str(s['step']) for s in exp)}."))
    by = {s["step"]: s for s in act}
    for s in exp:
        a = by.get(s["step"])
        if not a:
            continue
        if s["type"] != a["type"]:
            out.append(_diff("step", f"Step {s['step']} is a {a['type']} in Fabric and a {s['type']} in the dry run."))
        if s["after"] != a["after"]:
            said = lambda x: ", ".join(f"{n} ({'/'.join(c)})" for n, c in x) or "nothing"
            out.append(_diff("step", f"Step {s['step']} waits for {said(a['after'])} in Fabric and for {said(s['after'])} in the dry run."))
        if notebooks_known and str(s["notebook"]).lower() != str(a["notebook"]).lower():
            out.append(_diff("step", f"Step {s['step']} runs the notebook {a['notebook']} in Fabric and {s['notebook']} in the dry run."))
    return {"differences": out, "checked": {"steps": len(exp)}}


_MARKER = re.compile(r"^#\s*(?:MARKDOWN|CELL|PARAMETERS CELL|METADATA)\s*\*+\s*$")
_FABRIC_HEADER = "# Fabric notebook source"


def notebook_cells(source: str) -> list[dict]:
    """The cells of a notebook-content.py, as Fabric and Krusgraph both write it: [{kind, lines}] with kind "code",
    "parameters" or "markdown". The header line, every "# METADATA" block and its "# META" lines, and the cell markers
    themselves are left out; a cell's lines keep their text without trailing spaces, blank lines dropped. AP3b (the
    founder's live run of 25 November 2026): Fabric gives a notebook back with its own markers and metadata blocks, so
    the code is compared cell source by cell source, never marker by marker."""
    cells: list[dict] = []
    cur: dict | None = None
    for raw in str(source or "").replace("\r\n", "\n").splitlines():
        head = raw.strip()
        if head == _FABRIC_HEADER:
            continue
        if _MARKER.match(head):
            word = head.lstrip("#").strip().split("*")[0].strip().upper()
            if word == "METADATA":
                cur = None                                         # the block's "# META" lines belong to no cell
                continue
            cur = {"kind": {"MARKDOWN": "markdown", "PARAMETERS CELL": "parameters"}.get(word, "code"), "lines": []}
            cells.append(cur)
            continue
        if raw.lstrip().startswith("# META") or not head:
            continue
        if cur is None:                                            # text before any marker (a bare .py): one code cell
            cur = {"kind": "code", "lines": []}
            cells.append(cur)
        cur["lines"].append(raw.rstrip())
    return [c for c in cells if c["lines"]]


def _code_lines(source: str) -> list[str]:
    """The notebook's code lines: the code and parameters cells' sources one after the other, without the markdown
    cells, the metadata blocks, the markers and blank lines. LT1 (17 Nov 2026): Fabric stores a markdown cell in its own
    form, so the markdown (the notebook's description, not what runs) is not compared. AP3b: nor are the cell markers,
    which Fabric writes in its own way; a cell split in two or two cells joined is the same code."""
    return [ln for c in notebook_cells(source) if c["kind"] != "markdown" for ln in c["lines"]]


_PARAM = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _parameters(source: str) -> list[str]:
    return [m.group(1) for c in notebook_cells(source) if c["kind"] == "parameters" for ln in c["lines"] if (m := _PARAM.match(ln))]


def _description(source: str) -> set[str]:
    """The markdown cells' text lines, as a set: Fabric rewrites a markdown cell's layout (LT1), not its words."""
    return {x for c in notebook_cells(source) if c["kind"] == "markdown" for ln in c["lines"] if (x := " ".join(ln.lstrip("#").split()))}


EARLIER_VERSION = "built by an earlier version of Krusgraph; Update the build in place brings it to the current dry run"


def earlier_version(expected: str, actual: str) -> list[str]:
    """AP3b: the signs, by rules, that a Krusgraph notebook in Fabric was written by an earlier Krusgraph rather than
    changed by a person: its parameters cell lacks parameters the current one has (RUN_ID and the alert settings came
    on 11 November 2026, n200), or its description (Krusgraph's own markdown, which a person rarely edits) is another
    version's. Empty when neither holds; then a difference is only a difference."""
    signs = []
    exp_p, act_p = _parameters(expected), _parameters(actual)
    missing = [x for x in exp_p if x not in act_p]
    if act_p and missing and set(act_p) <= set(exp_p):
        signs.append(f"its parameters cell lacks {', '.join(missing[:4])}{' and more' if len(missing) > 4 else ''}, which "
                     "later versions add")
    exp_d, act_d = _description(expected), _description(actual)
    if act_d and exp_d and act_d != exp_d and any("krusgraph" in x.lower() for x in act_d):
        signs.append("its description is the one an earlier version wrote")
    return signs


def compare_notebook(expected: str, actual: str) -> dict:
    import difflib
    e, a = _code_lines(expected), _code_lines(actual)
    out = []
    if e != a:
        # LT1: count the lines that differ by a diff, not by position: one line added or gone no longer makes every
        # line after it differ
        ops = [op for op in difflib.SequenceMatcher(None, e, a, autojunk=False).get_opcodes() if op[0] != "equal"]
        differing = sum(max(i2 - i1, j2 - j1) for _, i1, i2, j1, j2 in ops)
        _, i1, _, j1, _ = ops[0]
        where = (f": {a[j1][:120]!r} in Fabric, {e[i1][:120]!r} in the dry run." if i1 < len(e) and j1 < len(a) else
                 f" (Fabric has {len(a)} lines, the dry run {len(e)}).")
        signs = earlier_version(expected, actual)
        if signs:
            out.append(_diff("code", f"The notebook was {EARLIER_VERSION} ({'; '.join(signs)}). Its code differs from the dry "
                                     f"run on {differing} line(s); the first is code line {i1 + 1}" + where, earlier_version=True))
        else:
            out.append(_diff("code", f"The notebook's code differs from the dry run on {differing} line(s); the first is code "
                                     f"line {i1 + 1}" + where))
    return {"differences": out, "checked": {"lines": len(e)}}


def _guessed_marks(source: str) -> int:
    """W5: the keys a pipeline notebook leaves unenforced as guessed: the check's "not_enforced" entries and silver's
    not_checked_keys[...] lines (pipeline.NOT_ENFORCED, silver._table_cell)."""
    return sum(1 for ln in _code_lines(source) if ln.lstrip().startswith(('"not_enforced":', "not_checked_keys[")))


def enforces_fewer_keys(expected: str, actual: str) -> bool:
    """W5: the notebook in Fabric enforces keys the dry run left as guessed: it was built on a key check (the Model's row
    check, workload_api.checked_keys) the dry run did not have."""
    return _guessed_marks(actual) < _guessed_marks(expected)


# ------------------------------------------------------------------ 2. the figures ------------------------------------

_DAX_T = r"('(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_]*)"
_DAX_C = r"\[((?:[^\]]|\]\])+)\]"
_COUNTROWS = re.compile(rf"^\s*COUNTROWS\s*\(\s*{_DAX_T}\s*\)\s*$", re.I)
_SUM = re.compile(rf"^\s*SUM\s*\(\s*{_DAX_T}\s*{_DAX_C}\s*\)\s*$", re.I)
_DISTINCT = re.compile(rf"^\s*DISTINCTCOUNT\s*\(\s*{_DAX_T}\s*{_DAX_C}\s*\)\s*$", re.I)
_SUMX_PRICE = re.compile(rf"^\s*SUMX\s*\(\s*{_DAX_T}\s*,\s*{_DAX_T}\s*{_DAX_C}\s*\*\s*RELATED\s*\(\s*{_DAX_T}\s*{_DAX_C}\s*\)\s*\)\s*$", re.I)
_SUMX_RELATED = re.compile(rf"^\s*SUMX\s*\(\s*{_DAX_T}\s*,\s*RELATED\s*\(\s*{_DAX_T}\s*{_DAX_C}\s*\)\s*\)\s*$", re.I)
_DIVIDE = re.compile(r"^\s*DIVIDE\s*\((.*)\)\s*$", re.I | re.S)
_MEASURE_REF = re.compile(rf"^\s*{_DAX_C}\s*$")
FORMS = ("COUNTROWS(table), SUM(table[column]), DISTINCTCOUNT(table[column]), SUMX(lines, lines[quantity] * RELATED(table[price])) "
         "and DIVIDE(a, b) of those or of [measure] (LFD4)")


def _t(name: str) -> str:
    return name[1:-1].replace("''", "'") if name.startswith("'") else name


def _c(name: str) -> str:
    return name.replace("]]", "]")


def _qi(name: str) -> str:
    return "[" + str(name).replace("]", "]]") + "]"


def _source_of(model: dict, table: str):
    """(schema, source table, the model's table) for a table of the model, or None when it is not bound to one."""
    t = next((tt for n, tt in model["tables"].items() if n.lower() == table.lower()), None)
    if not t or not t.get("source"):
        return None
    return t.get("source_schema"), t["source"], t


def _from(schema: str | None, table: str, default_schema: str) -> str:
    return f"{_qi(schema or default_schema)}.{_qi(table)}"


def _col(t: dict, column: str) -> str | None:
    c = next((cc for n, cc in t["columns"].items() if n.lower() == column.lower()), None)
    return (c.get("source_column") or c["name"]) if c else None


def _split_args(text: str) -> list[str] | None:
    """The arguments of a DAX call at the top level (commas inside parentheses, brackets or quotes stay), or None."""
    out, depth, cur, quote = [], 0, "", None
    for ch in text:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "[":
            quote = "]"
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return None
        elif ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
            continue
        cur += ch
    out.append(cur.strip())
    return out if depth == 0 and not quote else None


def _measure_expression(model: dict, name: str) -> str | None:
    return next((m.get("expression") or "" for t in model["tables"].values() for n, m in (t.get("measures") or {}).items()
                 if n.lower() == name.lower()), None)


def _ratio_sql(model: dict, expr: str, default_schema: str) -> dict | None:
    """LFD4: DIVIDE(numerator, denominator), each one of the other forms or a [measure] of the model in one of them. The
    SQL divides the two numbers as DAX's DIVIDE does: NULL (BLANK) where the denominator is 0 or empty. A ratio of a
    ratio is not a form (docs/CHANGES.md), so it is not translated either."""
    m = _DIVIDE.match(expr)
    if not m:
        return None
    args = _split_args(m.group(1))
    if not args or len(args) != 2:
        return {"why": "DIVIDE is translated with exactly two arguments, a numerator and a denominator"}
    parts = []
    for a in args:
        ref = _MEASURE_REF.match(a)
        if ref:
            inner = _measure_expression(model, _c(ref.group(1)))
            if inner is None:
                return {"why": f"[{_c(ref.group(1))}] is not a measure of the model"}
            a = _norm_expr(inner)
        if _DIVIDE.match(a):
            return {"why": "a ratio of a ratio is not one of the forms the rules translate"}
        q = measure_sql(model, a, default_schema)
        if "sql" not in q:
            return {"why": f"a part of the ratio is not translated: {q['why']}"}
        parts.append(q)
    num, den = parts
    return {"sql": (f"SELECT CASE WHEN d.v IS NULL OR d.v = 0 THEN NULL ELSE 1.0 * n.v / d.v END AS v "
                    f"FROM ({num['sql']}) AS n CROSS JOIN ({den['sql']}) AS d"),
            "table": num.get("table"), "ratio": True, "numerator": num["sql"], "denominator": den["sql"]}


def measure_sql(model: dict, expression: str, default_schema: str = "dbo") -> dict:
    """{sql} that computes a measure's number from the rows its table reads, or {why} when the rules do not translate
    the expression. T-SQL; the SQLite double of the tests rewrites COUNT_BIG. LFD4 adds the ratio form DIVIDE(a, b)."""
    expr = _norm_expr(expression)
    ratio = _ratio_sql(model, expr, default_schema)
    if ratio is not None:
        return ratio
    m = _COUNTROWS.match(expr)
    if m:
        src = _source_of(model, _t(m.group(1)))
        if not src:
            return {"why": f"{_t(m.group(1))} is not a table of the model bound to a source table"}
        return {"sql": f"SELECT COUNT_BIG(*) AS v FROM {_from(src[0], src[1], default_schema)}", "table": _t(m.group(1))}
    for rx, fn in ((_SUM, "SUM({c})"), (_DISTINCT, "COUNT(DISTINCT {c})")):
        m = rx.match(expr)
        if m:
            src = _source_of(model, _t(m.group(1)))
            col = _col(src[2], _c(m.group(2))) if src else None
            if not src or not col:
                return {"why": f"{_t(m.group(1))}[{_c(m.group(2))}] is not a column of a table bound to a source table"}
            return {"sql": f"SELECT {fn.format(c=_qi(col))} AS v FROM {_from(src[0], src[1], default_schema)}",
                    "table": _t(m.group(1)), "column": col, "sum": rx is _SUM}
    m = _SUMX_PRICE.match(expr)
    if m:
        line, line2, qty, dim, price = _t(m.group(1)), _t(m.group(2)), _c(m.group(3)), _t(m.group(4)), _c(m.group(5))
        ls, ds = _source_of(model, line), _source_of(model, dim)
        rel = next((r for r in model["relationships"] if r.get("active", True) and str(r.get("from_table", "")).lower() == line.lower()
                    and str(r.get("to_table", "")).lower() == dim.lower()), None)
        if line.lower() != line2.lower() or not ls or not ds or not rel:
            return {"why": f"no active relationship from {line} to {dim} in the model to follow for RELATED"}
        q, p, fk, pk = _col(ls[2], qty), _col(ds[2], price), _col(ls[2], rel["from_column"]), _col(ds[2], rel["to_column"])
        if not all((q, p, fk, pk)):
            return {"why": "a column of the expression is not in the model's tables"}
        return {"sql": (f"SELECT SUM(l.{_qi(q)} * d.{_qi(p)}) AS v FROM {_from(ls[0], ls[1], default_schema)} AS l "
                        f"LEFT JOIN {_from(ds[0], ds[1], default_schema)} AS d ON l.{_qi(fk)} = d.{_qi(pk)}"), "table": line}
    return {"why": f"the expression is not one of the forms the rules translate ({FORMS})"}


def kpis(model: dict, report: dict | None = None) -> list[dict]:
    """The figures to check: the report's cards (title and measure), else every measure of the model, at most MAX_FIGURES."""
    by = {(t.lower(), m.lower()): (t, m, mm.get("expression") or "") for t, tt in model["tables"].items()
          for m, mm in (tt.get("measures") or {}).items()}
    out = []
    if report:
        for v in report.get("visuals") or []:
            if v.get("type") != "card":
                continue
            for ref in v.get("fields") or []:
                t, _, m = str(ref).partition(".")
                hit = by.get((t.lower(), m.lower()))
                if hit:
                    out.append({"kpi": v.get("title") or hit[1], "table": hit[0], "measure": hit[1], "expression": hit[2], "on": "card"})
    if not out:
        out = [{"kpi": m, "table": t, "measure": m, "expression": e, "on": "measure"} for (_, _), (t, m, e) in sorted(by.items())]
    return out[:MAX_FIGURES]


def _number(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) else round(f, 4)


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= max(1e-6, 1e-9 * max(abs(float(a)), abs(float(b))))


def _first_value(rows):
    rows = list(rows or [])
    return next(iter(rows[0].values()), None) if rows and isinstance(rows[0], dict) else None


def figures(model: dict, report: dict | None, execute, dax=None, default_schema: str = "dbo", before=lambda what: None) -> list[dict]:
    """One entry per figure: {kpi, measure, state, said, source_rows, model, sql, dax}. `execute(sql)` reads the source's
    SQL endpoint; `dax(query)` runs a DAX query on the model and may be None or raise (then the model's own number is
    "not read", and the figure from the rows is shown for the eye). `before(what)` raises when the time is up."""
    out = []
    for k in kpis(model, report):
        row = {"kpi": k["kpi"], "measure": f"{k['table']}[{k['measure']}]", "expression": _norm_expr(k["expression"])}
        q = measure_sql(model, k["expression"], default_schema)
        if "sql" not in q:
            out.append({**row, "state": NOT_CHECKED, "said": f"{k['kpi']}: not checked: {q['why']}."})
            continue
        row["sql"], row["_q"] = q["sql"], q
        try:
            before(f"counting {k['kpi']}")
            if execute is None:
                raise RuntimeError("the source's SQL endpoint could not be opened")
            row["source_rows"] = _number(_first_value(execute(q["sql"])))
        except Exception as e:                                           # noqa: BLE001 - one failed count is one line
            out.append({**row, "state": NOT_CHECKED, "said": f"{k['kpi']}: not checked: the count from the rows did not run ({_why(e)})."})
            continue
        row["dax"] = f"EVALUATE ROW(\"v\", {_dax_measure(k['measure'])})"
        model_value, why = None, "no DAX query could be sent to the model from here"
        if dax is not None:
            try:
                before(f"reading {k['kpi']} from the model")
                model_value, why = _number(_first_value(dax(row["dax"]))), None
            except Exception as e:                                       # noqa: BLE001
                why = _why_dataset(e)
        if why is None:
            row["model"] = model_value
            if _same(model_value, row["source_rows"]):
                row.update(state=VERIFIED, said=f"{k['kpi']} = {_fmt(row['source_rows'])}: the model and the source rows agree.")
            else:
                row.update(state=DIFFERS, said=f"{k['kpi']}: the model says {_fmt(model_value)}, the source rows give {_fmt(row['source_rows'])}.")
        else:
            row.update(state=NOT_CHECKED, model_not_read=why,
                       said=f"{k['kpi']} = {_fmt(row['source_rows'])} from the source rows; not checked against the model: its own "
                            f"number was not read ({why}). Compare it with the card.")
        out.append(row)
    return out


def _dax_measure(name: str) -> str:
    return "[" + name.replace("]", "]]") + "]"


def _fmt(v) -> str:
    if v is None:
        return "(blank)"
    return f"{v:,}".replace(",", " ") if isinstance(v, int) else f"{v:,.2f}".replace(",", " ")


def _why(e: BaseException) -> str:
    status = getattr(getattr(e, "response", None), "status_code", None)
    text = (str(e) or type(e).__name__).strip().splitlines()[0][:200]
    return f"HTTP {status}" if status else text


# n241: the two Power BI reads (the model's refresh history, a DAX query) need a delegated Power BI permission that an
# app registration may not have yet; a 401/403 there says which one, so the person knows what to add in Entra.
DATASET_SCOPES_HINT = ("the sign-in may lack the Power BI permission Dataset.Read.All or Dataset.ReadWrite.All; an "
                       "administrator adds it to the app registration in Microsoft Entra and grants consent")
# W4 (Gustav's tenant test, 24 November 2026: a model's refresh history answered HTTP 401): the delegated Power BI
# permission the two reads need, named in a kind=consent answer as the creating tools name theirs (docs/SCOPES.md).
DATASET_READ_SCOPE = "Dataset.Read.All"
CONSENT_STEPS = (
    "Microsoft Entra admin centre (entra.microsoft.com) → App registrations → All applications → the Krusgraph MCP app "
    "(the app registration the MCP server signs in with).",
    "API permissions → Add a permission → Microsoft APIs → Power BI Service → Delegated permissions.",
    "Tick Dataset.Read.All (under Dataset) → Add permissions.",
    "Grant admin consent for your organisation (a Global Administrator, Application Administrator or Cloud Application "
    "Administrator) → Yes. The status shows 'Granted'.",
    "Sign in to the connector again (disconnect and connect), so the next token carries the permission; then call "
    "verify_build again.")


def _consent_failure(e: BaseException) -> bool:
    """A Power BI read refused for a missing permission: HTTP 401/403, or the on-behalf-of exchange asking for consent."""
    if _why(e).startswith(("HTTP 401", "HTTP 403")):
        return True
    text = str(e)
    return "AADSTS65001" in text or "consent_required" in text


def _why_dataset(e: BaseException) -> str:
    why = _why(e)
    return f"{why}: {DATASET_SCOPES_HINT}" if _consent_failure(e) else why


def consent_answer(lines: list[dict]) -> dict | None:
    """W4: {error, kind: consent, scope, hint, steps} when a Power BI read of this call was refused for a missing
    permission (the refresh history, or a figure's DAX query); None otherwise. The other lines stand."""
    hit = [ln["item"] for ln in lines if (ln.get("state_check") or {}).get("kind") == "consent"
           or any(DATASET_SCOPES_HINT in str(f.get("model_not_read") or "") for f in ln.get("figures") or [])]
    if not hit:
        return None
    return {"error": f"Power BI refused reading {', '.join(sorted(set(hit)))} (the refresh history or a figure): the sign-in does "
                     f"not carry the delegated permission {DATASET_READ_SCOPE}.",
            "kind": "consent", "scope": DATASET_READ_SCOPE,
            "hint": f"The operator adds Power BI Service → {DATASET_READ_SCOPE} (delegated) to the Krusgraph MCP app's registration "
                    "in Microsoft Entra and grants admin consent (docs/SCOPES.md); the steps are below. Everything else in this "
                    "answer was checked without it.",
            "steps": list(CONSENT_STEPS)}


# ------------------------------------------------------------------ 3. doubled totals ---------------------------------

def doubled(plan, model: dict, figs: list[dict], execute, before=lambda what: None) -> list[dict]:
    """Findings [{kpi, measure, state: differs, said, sql}] for figures that sum a header's amount once per line. `plan`
    may be None (then only the SUMX-of-RELATED rule and nothing counted)."""
    from . import amounts
    out = []
    headers = amounts.header_amounts(plan) if plan is not None else []
    flat = amounts.flat_candidates(plan) if plan is not None else []
    schema = plan.schema.schema if plan is not None else None
    for f in figs:
        expr = f.get("expression") or ""
        m = _SUMX_RELATED.match(expr)
        if m:
            out.append({"kpi": f["kpi"], "measure": f["measure"], "state": DIFFERS,
                        "said": f"{f['kpi']} sums {_t(m.group(2))}.{_c(m.group(3))} once per {_t(m.group(1))} row (SUMX over RELATED): a "
                                f"header's amount counted once per line. Sum it on {_t(m.group(2))} instead."})
            continue
        q = f.get("_q") or {}
        if not q.get("sum") or execute is None or plan is None:
            continue
        src = _source_of(model, q["table"])
        source_table = src[1] if src else q["table"]
        for c in flat:                                   # the flat table: the amount repeated on every row of a header value
            head = c["header_column"]
            if c["table"].lower() != source_table.lower() or q["column"].lower() not in {a.lower() for a in c["amount_columns"]}:
                continue
            try:
                before(f"counting {c['table']}.{q['column']} per {head}")
                dialect = amounts.dialect_of(execute)
                row = list(execute(amounts.flat_sql(schema, c["table"], head, [q["column"]], dialect)))[0]
                repeated, differs = int(row.get("repeated_values") or 0), int(row.get("differs_0") or 0)
                if repeated < amounts.MIN_REPEATED or differs:
                    continue
                once_sql = amounts.flat_sum_once_sql(schema, c["table"], head, q["column"], dialect)
                once = _number(_first_value(execute(once_sql)))
            except Exception:                                            # noqa: BLE001 - not counted is not flagged
                continue
            if not _same(once, f.get("source_rows")):
                out.append({"kpi": f["kpi"], "measure": f["measure"], "state": DIFFERS, "summed_over_rows": f.get("source_rows"),
                            "summed_once": once, "sql": [f["sql"], once_sql],
                            "said": f"{f['kpi']} looks doubled: {c['table']}.{q['column']} has one value per {head} and is "
                                    f"repeated on its rows, so the sum over the rows is {_fmt(f.get('source_rows'))} where once per "
                                    f"{head} gives {_fmt(once)}."})
                break
    known = {(o["measure"]) for o in out}
    for h in headers:                                    # a figure that equals a header amount summed over its line rows
        if execute is None:
            break
        for col in h["amount_columns"]:
            try:
                before(f"summing {h['header']}.{col} over {h['line']}")
                ba = amounts.before_after(schema, {**h, "amount_columns": [col]}, execute)
            except Exception:                                            # noqa: BLE001
                ba = None
            if not ba or _same(ba["summed_over_lines"], ba["summed_per_header"]):
                continue
            for f in figs:
                value = f.get("model") if "model" in f else None
                if f["measure"] in known or value is None or not _same(value, ba["summed_over_lines"]):
                    continue
                known.add(f["measure"])
                out.append({"kpi": f["kpi"], "measure": f["measure"], "state": DIFFERS, "summed_over_rows": _number(ba["summed_over_lines"]),
                            "summed_once": _number(ba["summed_per_header"]), "sql": [ba["sql_before"], ba["sql_after"]],
                            "said": f"{f['kpi']} looks doubled: its number {_fmt(_number(value))} is {h['header']}.{col} summed over the "
                                    f"{h['line']} rows; once per {h['header']} row it is {_fmt(_number(ba['summed_per_header']))}."})
    return out


# ------------------------------------------------------------------ 4. state ------------------------------------------

REFRESH_FIX = {"label": "Refresh the model once", "action": "refresh_model",
               "how": "In Fabric, open the semantic model and choose Refresh now (once: it frames the Direct Lake tables)."}
RUN_FIX = {"label": "Run the pipeline once", "action": "run_pipeline",
           "how": "In Fabric, open the pipeline and choose Run; or create_pipeline with run_once=true."}
GRAPH_FIX = {"label": "Build the ontology's graph", "action": "open_ontology",
             "how": "In Fabric, open the ontology and refresh its graph (the item's own command); nothing else builds it."}
APP_FIX = {"label": "Publish the App's package", "action": "publish_app",
           "how": "Upload the package Create gave to Azure Cloud Shell and run its one command (npx rayfin up); the App opens inside Fabric only."}


def model_state(refreshes) -> dict:
    """`refreshes`: the model's refresh history (Power BI: value of GET .../refreshes), newest first; or an exception."""
    if isinstance(refreshes, BaseException):
        return {"check": "refreshed", "state": NOT_CHECKED, "fix": REFRESH_FIX,
                **({"kind": "consent", "scope": DATASET_READ_SCOPE} if _consent_failure(refreshes) else {}),   # W4
                "said": f"Whether the model was ever refreshed was not read ({_why_dataset(refreshes)}). A new Direct Lake model shows no data "
                        "(\"Data refreshed: Invalid Date\", warning triangles) until it is refreshed once."}
    done = [r for r in refreshes or [] if str(r.get("status")) == "Completed"]
    if done:
        return {"check": "refreshed", "state": VERIFIED, "said": f"The model was refreshed (latest: {done[0].get('endTime') or done[0].get('startTime') or 'time not given'})."}
    if refreshes:
        last = refreshes[0]
        return {"check": "refreshed", "state": DIFFERS, "fix": REFRESH_FIX,
                "said": f"The model has no completed refresh: the latest is {last.get('status')}. Its tables show no data until one completes."}
    return {"check": "refreshed", "state": DIFFERS, "fix": REFRESH_FIX,
            "said": "The model was never refreshed: its tables show no data (\"Data refreshed: Invalid Date\", warning triangles) "
                    "until it is refreshed once."}


def pipeline_state(instances) -> dict:
    if isinstance(instances, BaseException):
        return {"check": "run", "state": NOT_CHECKED, "fix": RUN_FIX, "said": f"Whether the pipeline ever ran was not read ({_why(instances)})."}
    if not instances:
        return {"check": "run", "state": DIFFERS, "fix": RUN_FIX,
                "said": "The pipeline never ran: the silver tables and the gold views it writes are not there yet."}
    ok = [i for i in instances if str(i.get("status")) == "Completed"]
    if ok:
        return {"check": "run", "state": VERIFIED, "said": f"The pipeline has run ({len(ok)} completed of {len(instances)} run(s) listed)."}
    return {"check": "run", "state": DIFFERS, "fix": RUN_FIX,
            "said": f"The pipeline has no completed run: the latest of {len(instances)} is {instances[0].get('status')}."}


def ontology_state(name: str, items) -> dict:
    """Judged from the workspace's item list: Microsoft documents no call that gives an ontology graph's state."""
    limit = "Judged from the workspace's item list; no documented call reads the graph's state."
    if isinstance(items, BaseException):
        return {"check": "graph", "state": NOT_CHECKED, "fix": GRAPH_FIX, "said": f"Whether the ontology's graph is built was not read ({_why(items)})."}
    graphs = [i for i in items or [] if str(i.get("type") or "").lower() in ("graphmodel", "graph")]
    mine = [g for g in graphs if name.lower() in str(g.get("displayName") or "").lower()]
    if mine:
        return {"check": "graph", "state": VERIFIED, "said": f"A graph item named {mine[0].get('displayName')} exists beside the ontology. {limit}"}
    if graphs:
        return {"check": "graph", "state": NOT_CHECKED, "fix": GRAPH_FIX,
                "said": f"The workspace has {len(graphs)} graph item(s), none named after {name}: whether one of them is this ontology's is not known. {limit}"}
    return {"check": "graph", "state": DIFFERS, "fix": GRAPH_FIX,
            "said": f"No graph item is in the workspace: the ontology's graph does not look built, so nothing can be asked of it yet. {limit}"}


def app_state() -> dict:
    return {"check": "published", "state": NOT_CHECKED, "fix": APP_FIX,
            "said": "Create makes the App item empty, and no documented call reads what an App holds: whether its pages were "
                    "published is not known here. It is empty until the package's one command has run."}


# ------------------------------------------------------------------ the result ----------------------------------------

_ORDER = {DIFFERS: 0, NOT_CHECKED: 1, VERIFIED: 2}


def worst(states) -> str:
    states = [s for s in states if s]
    return min(states, key=lambda s: _ORDER[s]) if states else NOT_CHECKED


def line(kind: str, name: str, definition: dict | None = None, not_checked: str | None = None, figs: list[dict] | None = None,
         doubles: list[dict] | None = None, state_check: dict | None = None, notes: list[str] | None = None) -> dict:
    """One result line for one item. `definition` is a compare_* answer; `not_checked` the reason the definition could
    not be compared (not found, not readable, time)."""
    word = WORD_OF.get(kind, kind)
    out = {"item": name, "kind": kind, "type": TYPE_OF.get(kind, kind)}
    parts, states = [], []
    if not_checked:
        states.append(NOT_CHECKED)
        parts.append(f"Definition not checked: {not_checked}.")
    elif definition is not None:
        n = len(definition["differences"])
        states.append(DIFFERS if n else VERIFIED)
        checked = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in definition.get("checked", {}).items() if v)
        if n:
            parts.append(f"Definition: {n} difference(s) from the dry run" + (f" ({checked} compared)" if checked else "") + ": "
                         + definition["differences"][0]["said"] + (f" And {n - 1} more." if n > 1 else ""))
            out["differences"] = definition["differences"][:MAX_DIFFERENCES]
            out["differences_total"] = n
        elif checked:
            parts.append(f"Definition as the dry run ({checked} compared).")
        out["checked"] = definition.get("checked", {})
    if figs:
        out["figures"] = [{k: v for k, v in f.items() if not k.startswith("_")} for f in figs]
        states += [f["state"] for f in figs]
        c = {s: sum(1 for f in figs if f["state"] == s) for s in STATES}
        shown = ", ".join(f"{f['kpi']} = {_fmt(f['source_rows'])}" for f in figs if "source_rows" in f)
        parts.append("Figures: " + ", ".join(f"{c[s]} {s}" for s in STATES if c[s]) + (f" (from the rows: {shown})" if shown else "") + "."
                     + "".join(" " + f["said"] for f in figs if f["state"] == DIFFERS))
    if doubles:
        out["doubled_totals"] = doubles
        states.append(DIFFERS)
        parts.append(" ".join(d["said"] for d in doubles))
    elif figs and doubles is not None:
        parts.append("No doubled total found.")
    if state_check:
        out["state_check"] = state_check
        states.append(state_check["state"])
        parts.append(state_check["said"] + (f" Fix: {state_check['fix']['label']}." if state_check.get("fix") else ""))
        if state_check.get("fix"):
            out["fix"] = state_check["fix"]
    if notes:
        out["notes"] = notes
    out["state"] = worst(states)
    out["said"] = f"{name} ({word}): {out['state']}. " + " ".join(parts)
    return out


def result(lines: list[dict], time_budget: dict | None = None, expected_note: str | None = None) -> dict:
    """The answer: the label, the counts, one line per item, every SQL statement, the time budget."""
    counts = {s.replace(" ", "_"): sum(1 for ln in lines if ln["state"] == s) for s in STATES}
    figs = [f for ln in lines for f in ln.get("figures") or []]
    sql = []
    for ln in lines:
        for f in ln.get("figures") or []:
            if f.get("sql"):
                sql.append({"item": ln["item"], "what": f["kpi"], "sql": f["sql"], **({"dax": f["dax"]} if f.get("dax") else {})})
        for d in ln.get("doubled_totals") or []:
            for s in d.get("sql") or []:
                sql.append({"item": ln["item"], "what": d["kpi"] + " (doubled total)", "sql": s})
    fixes = [{"item": ln["item"], **ln["fix"]} for ln in lines if ln.get("fix")]
    n = len(lines)
    summary = (f"{n} item(s): {counts['verified']} verified, {counts['differs']} differ{'s' if counts['differs'] == 1 else ''}, "
               f"{counts['not_checked']} not checked.") if n else "Nothing to verify: no built item was named."
    if figs:
        fc = {s: sum(1 for f in figs if f["state"] == s) for s in STATES}
        summary += f" Figures: {fc[VERIFIED]} verified, {fc[DIFFERS]} differ{'s' if fc[DIFFERS] == 1 else ''}, {fc[NOT_CHECKED]} not checked."
    out = {"label": LABEL, "summary": summary, "counts": {**counts, "items": n}, "lines": lines,
           "result_lines": [ln["said"] for ln in lines], "fixes": fixes, "sql": sql,
           "compared_with": expected_note or EXPECTED_FROM, "writes": "nothing: every call is a read",
           "review_by_ai": CLAUDE_INVITE}
    consent = consent_answer(lines)                                  # W4: said as the creating tools say it
    if consent:
        out["consent"] = consent
    if time_budget:
        out["time_budget"] = time_budget
    return out
