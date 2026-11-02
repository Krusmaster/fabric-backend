"""Ontology Playground's own checks of an RDF/XML file, in Python, for the tests of ontology.ontology_rdfxml (n80).

Ported from microsoft/Ontology-Playground at commit 7bf7acb427424ce68f917fa26f484fb06ca42051:
scripts/catalogue-validation.ts (validateRdfSource with analyzeSourceGraph, validateResourceLimits,
validateExternalCore, externalCompatibilityWarnings) and scripts/validate-rdf.ts (how a file is read and the two are
merged). The projection in `project()` follows docs/external-rdf-generators.md, which describes what src/lib/rdf/parser.ts
reads; it is the part of the parser these rules need, not the parser. The error and warning codes are the
Playground's own. Copyright (c) Microsoft Corporation, MIT licence; the text is in
tests/fixtures/rdf/LICENSE-Ontology-Playground.txt.

What is left out: the catalogue metadata checks (metadata.json; a generated file has none) and the "authored" profile's
Designer rules (every entity needs an identifier, names of 26 characters at most), which apply to models made in the
Playground's Designer: a plan with a keyless table or a composite key is a valid external source but not a valid
Designer model, so those come back as the warnings the external profile gives.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from xml.parsers import expat

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
OWL = "http://www.w3.org/2002/07/owl#"
LIMITS = {"max_source_bytes": 8 * 1024 * 1024, "max_entities": 5_000, "max_relationships": 20_000,
          "max_properties": 50_000, "max_imports": 1_000}                      # DEFAULT_VALIDATION_LIMITS
FABRIC_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
SOURCE_ONLY_TERMS = (("OWL restrictions", ("Restriction",)), ("OWL set expressions", ("unionOf", "intersectionOf", "complementOf", "oneOf")),
                     ("OWL property chains", ("propertyChainAxiom",)), ("OWL keys", ("hasKey",)),
                     ("OWL disjointness axioms", ("disjointWith", "AllDisjointClasses", "AllDisjointProperties")))
_RANGE_TYPES = {"string": "string", "integer": "integer", "int": "integer", "long": "integer", "decimal": "decimal",
                "float": "decimal", "double": "double", "date": "date", "dateTime": "datetime", "boolean": "boolean"}


class _Doctype(Exception):
    pass


def _issue(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def _summarize(values: list[str]) -> str:
    shown = [f'"{v}"' for v in values[:3]]
    return ", ".join(shown) + (f", and {len(values) - 3} more" if len(values) > 3 else "")


def local_name(iri: str) -> str:
    if "#" in iri:
        return iri[iri.rfind("#") + 1:]
    return iri[iri.rfind("/") + 1:] if "/" in iri else iri


def graph_id(iri: str) -> str:
    """normalizedGraphId: the local name with only its first character lower-cased."""
    n = local_name(iri)
    return n[:1].lower() + n[1:] if n else ""


def _has_doctype(text: str) -> bool:
    """assertSupportedRdfXmlSource: a DOCTYPE is refused before any entity is expanded (expat stops at the declaration)."""
    p = expat.ParserCreate(namespace_separator=" ")

    def stop(*_):
        raise _Doctype()
    p.StartDoctypeDeclHandler = stop
    try:
        p.Parse(text, True)
    except _Doctype:
        return True
    except expat.ExpatError:
        return False                    # malformed: the XML parse below reports it
    return False


def _about(e: ET.Element) -> str:
    return e.get(f"{{{RDF}}}about") or ""


def _child(e: ET.Element, local: str, ns: str | None = None) -> ET.Element | None:
    for c in e:
        if not isinstance(c.tag, str):
            continue
        cns, _, cl = c.tag[1:].partition("}") if c.tag.startswith("{") else ("", "", c.tag)
        if cl == local and (ns is None or cns == ns):
            return c
    return None


def _child_resource(e: ET.Element, local: str, ns: str | None = None) -> str:
    c = _child(e, local, ns)
    return (c.get(f"{{{RDF}}}resource") or "") if c is not None else ""


def _child_text(e: ET.Element, local: str) -> str:
    c = _child(e, local)
    return "".join(c.itertext()).strip() if c is not None else ""


def _typed(root: ET.Element, ns: str, local: str) -> list[ET.Element]:
    """getTypedSourceElements: elements named ns:local, and rdf:Description nodes with rdf:type naming it."""
    out = list(root.iter(f"{{{ns}}}{local}"))
    for d in root.iter(f"{{{RDF}}}Description"):
        if any(c.tag == f"{{{RDF}}}type" and c.get(f"{{{RDF}}}resource") == ns + local for c in d):
            out.append(d)
    return out


def validate_source(data: bytes, limits: dict = LIMITS) -> tuple[dict, ET.Element | None]:
    """validateRdfSource: size, UTF-8, no DOCTYPE, well-formed XML, the import limit and the source graph analysis."""
    report = {"errors": [], "warnings": []}
    if len(data) > limits["max_source_bytes"]:
        report["errors"].append(_issue("source-size-limit", f"RDF source is {len(data):,} bytes; the limit is {limits['max_source_bytes']:,} bytes."))
        return report, None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        report["errors"].append(_issue("source-utf8", "RDF source must be valid UTF-8."))
        return report, None
    if not text.lstrip().startswith("<"):
        return report, None
    if _has_doctype(text):
        report["errors"].append(_issue("source-active-xml", "DOCTYPE declarations are not allowed in catalogue RDF."))
        return report, None
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        report["errors"].append(_issue("source-xml", f"Malformed XML: {e}"))
        return report, None
    imports = len(list(root.iter(f"{{{OWL}}}imports")))
    if imports > limits["max_imports"]:
        report["errors"].append(_issue("resource-imports", f"Ontology declares {imports:,} imports; the limit is {limits['max_imports']:,}."))
    graph = _analyze_graph(root)
    report["errors"] += graph["errors"]
    report["warnings"] += graph["warnings"]
    only = [(label, sum(len(_typed(root, OWL, t)) if t[0].isupper() else len(list(root.iter(f"{{{OWL}}}{t}"))) for t in terms))
            for label, terms in SOURCE_ONLY_TERMS]
    only = [(label, n) for label, n in only if n]
    if imports:
        only.append(("OWL imports", imports))
    if graph["skipped_object_properties"]:
        only.append(("unmapped OWL object properties", graph["skipped_object_properties"]))
    if graph["anonymous_classes"]:
        only.append(("anonymous OWL class expressions", graph["anonymous_classes"]))
    if only:
        report["warnings"].append(_issue("source-only-semantics", "Source-only semantics are preserved in the original RDF but are not expanded "
                                         "in the visual model: " + ", ".join(f"{label} ({n:,})" for label, n in only) + "."))
    return report, root


def _analyze_graph(root: ET.Element) -> dict:
    """analyzeSourceGraph: stable ids for classes and relationships, no collision of graph ids after the first letter is
    lower-cased, both endpoints of a relationship and both inside the graph, no relationship declared twice."""
    out = {"errors": [], "warnings": [], "anonymous_classes": 0, "skipped_object_properties": 0}
    classes, props = _typed(root, OWL, "Class"), _typed(root, OWL, "ObjectProperty")
    prop_iris = {_about(e) for e in props if _about(e)}
    owners: dict[str, str] = {}
    collisions, class_iris, missing_class = [], set(), []

    def own(gid: str, iri: str) -> None:
        if gid in owners and owners[gid] != iri:
            collisions.append(f"{gid}: {owners[gid]} and {iri}")
        else:
            owners[gid] = iri
    for e in classes:
        iri = _about(e)
        if not iri:
            out["anonymous_classes"] += 1
            continue
        if _child_resource(e, "subClassOf", RDFS) == RDF + "Statement" and _child_resource(e, "relation") in prop_iris:
            continue                                           # an association class, not an entity
        class_iris.add(iri)
        gid = graph_id(iri)
        if not gid:
            missing_class.append(iri)
            continue
        own(gid, iri)
    incomplete, unresolved, duplicate, missing_rel, seen = [], [], [], [], set()
    for e in props:
        iri = _about(e)
        from_el, to_el = _child(e, "fromEntityId"), _child(e, "toEntityId")
        explicit_from, explicit_to = _child_text(e, "fromEntityId"), _child_text(e, "toEntityId")
        domain, rng = _child_resource(e, "domain", RDFS), _child_resource(e, "range", RDFS)
        has_source, has_target = bool(explicit_from or domain), bool(explicit_to or rng)
        if not has_source and not has_target:
            out["skipped_object_properties"] += 1
            continue
        if not has_source or not has_target:
            if from_el is not None or to_el is not None:
                incomplete.append(iri or "anonymous object property")
            else:
                out["skipped_object_properties"] += 1
            continue
        if not iri:
            missing_rel.append("anonymous object property")
            continue
        if not explicit_from and domain and domain not in class_iris:
            unresolved.append(f"{iri} -> {domain}")
        if not explicit_to and rng and rng not in class_iris:
            unresolved.append(f"{iri} -> {rng}")
        if iri in seen:
            duplicate.append(iri)
            continue
        seen.add(iri)
        gid = graph_id(iri)
        if not gid:
            missing_rel.append(iri)
            continue
        own(gid, iri)
    for values, code, text in ((missing_class, "source-class-identifier", "OWL classes lack a stable source identifier"),
                               (missing_rel, "source-relationship-identifier", "visual relationships lack a stable source identifier"),
                               (collisions, "source-graph-id-collision", "source identifier collisions would require order-dependent graph IDs"),
                               (incomplete, "source-relationship-endpoints", "OWL object properties declare only one visual endpoint"),
                               (unresolved, "source-relationship-target", "OWL object property endpoints reference classes outside the visual graph"),
                               (duplicate, "source-relationship-duplicate", "visual relationships are declared more than once")):
        if values:
            out["errors"].append(_issue(code, f"{len(values):,} {text} ({_summarize(values)})."))
    return out


def project(root: ET.Element) -> dict:
    """The visual model the importer builds, as docs/external-rdf-generators.md describes it: entities (id from the class
    IRI, numbered on a collision), their properties (a datatype property whose domain is exactly a class IRI), and the
    relationships (ids from the IRI, endpoints from ont:fromEntityId/toEntityId or the domain and range)."""
    prop_iris = {_about(e) for e in _typed(root, OWL, "ObjectProperty") if _about(e)}
    entities, by_iri, used = [], {}, set()

    def unique(base: str) -> str:
        cand, n = base, 2
        while cand in used:
            cand, n = f"{base}-{n}", n + 1
        used.add(cand)
        return cand
    for e in _typed(root, OWL, "Class"):
        iri = _about(e)
        if not iri or iri in by_iri:
            continue
        if _child_resource(e, "subClassOf", RDFS) == RDF + "Statement" and _child_resource(e, "relation") in prop_iris:
            continue
        ent = {"id": unique(graph_id(iri)), "iri": iri, "name": _child_text(e, "label") or local_name(iri), "properties": []}
        entities.append(ent)
        by_iri[iri] = ent
    for e in _typed(root, OWL, "DatatypeProperty"):
        iri = _about(e)
        if not iri or _child(e, "relationshipAttributeOf") is not None:
            continue
        ent = by_iri.get(_child_resource(e, "domain", RDFS))
        if ent is None:
            continue                                           # missing or unknown domain: skipped, as the importer does
        rng = local_name(_child_resource(e, "range", RDFS))
        ent["properties"].append({"name": _child_text(e, "label") or local_name(iri), "type": _RANGE_TYPES.get(rng, "string"),
                                  "isIdentifier": _child_text(e, "isIdentifier") == "true"})
    rels = []
    for e in _typed(root, OWL, "ObjectProperty"):
        iri = _about(e)
        if not iri:
            continue
        end = lambda explicit, res: (explicit[:1].lower() + explicit[1:]) if explicit else (by_iri[res]["id"] if res in by_iri else graph_id(res) if res else "")
        frm = end(_child_text(e, "fromEntityId"), _child_resource(e, "domain", RDFS))
        to = end(_child_text(e, "toEntityId"), _child_resource(e, "range", RDFS))
        if not frm or not to:
            continue
        rels.append({"id": unique(local_name(iri)), "iri": iri, "name": _child_text(e, "label") or local_name(iri), "from": frm, "to": to,
                     "cardinality": _child_text(e, "cardinality") or "one-to-many"})
    return {"entities": entities, "relationships": rels}


def validate_model(model: dict, limits: dict = LIMITS) -> dict:
    """validateOntologyForTier with the external profile: validateResourceLimits, validateExternalCore and
    externalCompatibilityWarnings."""
    report = {"errors": [], "warnings": []}
    n_props = sum(len(e["properties"]) for e in model["entities"])
    for label, count, limit in (("entities", len(model["entities"]), limits["max_entities"]),
                                ("relationships", len(model["relationships"]), limits["max_relationships"]),
                                ("properties", n_props, limits["max_properties"])):
        if count > limit:
            report["errors"].append(_issue(f"resource-{label}", f"Ontology contains {count:,} {label}; the limit is {limit:,}."))
    if not model["entities"]:
        report["errors"].append(_issue("ontology-empty", "Ontology must contain at least one class."))
    ids, rel_ids = set(), set()
    for e in model["entities"]:
        if not e["id"].strip():
            report["errors"].append(_issue("entity-id-empty", f'External class "{e["name"]}" must have a stable identifier.'))
        elif e["id"] in ids:
            report["errors"].append(_issue("entity-id-duplicate", f'Duplicate external class identifier "{e["id"]}".'))
        else:
            ids.add(e["id"])
        names = set()
        for p in e["properties"]:
            if not p["name"].strip():
                report["errors"].append(_issue("property-name-empty", f'Properties on "{e["name"]}" must have a stable name.'))
            elif p["name"] in names:
                report["errors"].append(_issue("property-name-duplicate", f'Duplicate property name "{p["name"]}" on "{e["name"]}".'))
            else:
                names.add(p["name"])
    for r in model["relationships"]:
        if not r["id"].strip():
            report["errors"].append(_issue("relationship-id-empty", f'Relationship "{r["name"]}" must have a stable identifier.'))
        elif r["id"] in rel_ids:
            report["errors"].append(_issue("relationship-id-duplicate", f'Duplicate relationship identifier "{r["id"]}".'))
        else:
            rel_ids.add(r["id"])
        if r["from"] not in ids:
            report["errors"].append(_issue("relationship-source", f'Relationship "{r["name"]}" references missing source "{r["from"]}".'))
        if r["to"] not in ids:
            report["errors"].append(_issue("relationship-target", f'Relationship "{r["name"]}" references missing target "{r["to"]}".'))
    no_id = sum(1 for e in model["entities"] if not any(p["isIdentifier"] for p in e["properties"]))
    bad_names = sum(1 for e in model["entities"] if len(e["name"]) > 26 or not FABRIC_NAME.match(e["name"]))
    if no_id:
        report["warnings"].append(_issue("designer-identifiers", f"{no_id:,} external classes do not define Designer identifier properties; catalogue browsing remains supported."))
    if bad_names:
        report["warnings"].append(_issue("designer-entity-names", f"{bad_names:,} external class labels do not meet Designer naming conventions; their source labels are preserved."))
    return report


def validate(data: bytes) -> dict:
    """validate-rdf.ts's validateRdfBytes for a standalone file: the source checks, then the model checks on what the
    importer would build; {"errors", "warnings", "model"}. An error code list that is empty means the file passes."""
    report, root = validate_source(data)
    if report["errors"] or root is None:
        return {**report, "model": None}
    model = project(root)
    rest = validate_model(model)
    return {"errors": report["errors"] + rest["errors"], "warnings": report["warnings"] + rest["warnings"], "model": model}


def codes(report: dict) -> list[str]:
    return [i["code"] for i in report["errors"]]
