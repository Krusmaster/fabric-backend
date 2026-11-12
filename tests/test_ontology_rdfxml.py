"""n80: the plan as RDF/XML for Microsoft's Ontology Playground (ontology.ontology_rdfxml), checked with the
Playground's own rules ported to Python (tests/playground_rdf.py) and against its generator guide at commit
7bf7acb427424ce68f917fa26f484fb06ca42051 (docs/external-rdf-generators.md, docs/rdf-export-profiles.md). The fixture
tests/fixtures/rdf/cosmic-coffee.rdf is catalogue/official/cosmic-coffee/cosmic-coffee.rdf at that commit, unmodified:
a file the Playground ships as valid, so the ported rules are shown to accept it before they judge ours."""
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import playground_rdf as pr
import sap_support
from fabric_backend import ontology, seed
from fabric_backend.infer import PlanInputError, plan
from fabric_backend.schema import Column, Schema, Table

FIXTURES = Path(__file__).parent / "fixtures" / "rdf"
COSMIC = FIXTURES / "cosmic-coffee.rdf"
# the upstream file's SHA-256 (git blob 28edf4dfaf6ad0733ac06d83ff3ea297731b7d81 at 7bf7acb), so the copy stays unmodified
COSMIC_SHA256 = "19d95caa7171970dae3d467648a3dd23ae1a6a20409dd0a8f39e2f95a518de60"
RDF, RDFS, OWL, ONT = pr.RDF, pr.RDFS, pr.OWL, ontology.PLAYGROUND_NS
ABSOLUTE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
CARDINALITIES = {"one-to-one", "one-to-many", "many-to-one", "many-to-many"}


@pytest.fixture(scope="module")
def shop():
    return plan(seed.schema("shop"), None, None)


@pytest.fixture(scope="module")
def sap():
    return plan(sap_support.schema())


def cosmic() -> bytes:
    return COSMIC.read_bytes()


# ------------------------------------------------------------------ the ported rules, on the Playground's own file
def test_the_fixture_is_the_official_file_unmodified_with_its_licence_beside_it():
    assert hashlib.sha256(cosmic()).hexdigest() == COSMIC_SHA256
    assert (FIXTURES / "LICENSE-Ontology-Playground.txt").read_text().startswith("MIT License\n\nCopyright (c) Microsoft Corporation.")
    assert sorted(p.name for p in FIXTURES.iterdir()) == ["LICENSE-Ontology-Playground.txt", "cosmic-coffee.rdf"]   # official/ only


def test_the_ported_rules_accept_the_official_cosmic_coffee_file():
    r = pr.validate(cosmic())
    assert r["errors"] == [] and r["warnings"] == []
    m = r["model"]
    assert [e["id"] for e in m["entities"]] == ["customer", "order", "product", "store", "supplier", "shipment"]
    assert len(m["relationships"]) == 7 and all(x["cardinality"] in CARDINALITIES for x in m["relationships"])


@pytest.mark.parametrize("change, code", [
    (lambda s: s.replace('<?xml version="1.0" encoding="UTF-8"?>\n', '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE rdf:RDF [<!ENTITY x "y">]>\n', 1),
     "source-active-xml"),
    (lambda s: s.replace("</rdf:RDF>", "<owl:Class"), "source-xml"),
    (lambda s: s.replace('/Order">', '/Order">', 1).replace("</rdf:RDF>", '<owl:Class rdf:about="http://example.org/x/customer"/></rdf:RDF>'),
     "source-graph-id-collision"),
    (lambda s: s.replace('<rdfs:range rdf:resource="http://example.org/ontology/cosmic-coffee-company/Order"/>',
                         '<rdfs:range rdf:resource="http://example.org/ontology/cosmic-coffee-company/Ghost"/>', 1)
     .replace("<ont:toEntityId>order</ont:toEntityId>", "", 1), "source-relationship-target"),     # without the explicit id, the range counts
    (lambda s: s.replace("</rdf:RDF>", '<owl:ObjectProperty rdf:about="http://example.org/ontology/cosmic-coffee-company/customer_places_order">'
                         '<rdfs:domain rdf:resource="http://example.org/ontology/cosmic-coffee-company/Customer"/>'
                         '<rdfs:range rdf:resource="http://example.org/ontology/cosmic-coffee-company/Order"/></owl:ObjectProperty></rdf:RDF>'),
     "source-relationship-duplicate"),
    (lambda s: s.replace("</rdf:RDF>", '<owl:ObjectProperty rdf:about="http://example.org/x/half"><rdfs:domain rdf:resource="http://example.org/x/a"/>'
                         "<ont:toEntityId></ont:toEntityId></owl:ObjectProperty></rdf:RDF>"), "source-relationship-endpoints"),
    (lambda s: s.replace("</rdf:RDF>", '<owl:Class rdf:about="http://example.org/x/"/></rdf:RDF>'), "source-class-identifier"),
    (lambda s: s.replace("</rdf:RDF>", '<owl:ObjectProperty rdf:about="http://example.org/x/r"><ont:fromEntityId>customer</ont:fromEntityId>'
                         "<ont:toEntityId>nobody</ont:toEntityId></owl:ObjectProperty></rdf:RDF>"), "relationship-target"),
    (lambda s: s.replace("<rdfs:label>name</rdfs:label>", "<rdfs:label>email</rdfs:label>", 1), "property-name-duplicate"),
])
def test_the_ported_rules_refuse_what_the_playground_refuses(change, code):
    text = cosmic().decode("utf-8")
    changed = change(text)
    assert changed != text
    assert code in pr.codes(pr.validate(changed.encode("utf-8")))


def test_size_utf8_and_empty_are_refused():
    assert pr.codes(pr.validate(b" " * (8 * 1024 * 1024 + 1))) == ["source-size-limit"]
    assert pr.codes(pr.validate(b"<rdf:RDF \xff")) == ["source-utf8"]
    empty = b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>'
    assert pr.codes(pr.validate(empty)) == ["ontology-empty"]


# ------------------------------------------------------------------ our export against the rules and the guide
@pytest.mark.parametrize("which", ["shop", "sap"])
def test_the_shop_and_sap_plans_pass_the_playground_rules(which, shop, sap):
    p = shop if which == "shop" else sap
    r = pr.validate(ontology.ontology_rdfxml(p, which).encode("utf-8"))
    assert r["errors"] == []
    # keyless or composite-key tables, said as a warning; n226 (intended): the SAP plan's composite keys are carried by
    # combined key columns, so every SAP table has one identifier and the warning is gone there
    assert [w["code"] for w in r["warnings"]] == (["designer-identifiers"] if which == "shop" else [])
    m = r["model"]
    assert len(m["entities"]) == len(p.schema.tables) and len(m["relationships"]) == len(p.relationships)
    ids = [e["id"] for e in m["entities"]] + [x["id"] for x in m["relationships"]]
    assert len(set(ids)) == len(ids) and not any(re.search(r"-\d+$", i) for i in ids)     # the importer numbered nothing
    cp = ontology._carry(p, None, which)[0]                   # n226: the plan with its combined key columns (SAP), else p itself
    assert sum(len(e["properties"]) for e in m["entities"]) == sum(len(t.columns) for t in cp.schema)
    keyed = {ontology.entity_name(t.name) for t, key, *_ in ontology._model(cp, None) if key}
    assert {e["name"] for e in m["entities"] if any(x["isIdentifier"] for x in e["properties"])} == keyed


def test_the_document_meets_the_generator_guide(shop, sap):
    for p, name in ((shop, "shop"), (sap, "sap_sales")):
        text = ontology.ontology_rdfxml(p, name)
        assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<rdf:RDF\n') and "DOCTYPE" not in text and "xml:base" not in text
        assert len(text.encode("utf-8")) <= ontology.RDFXML_MAX_BYTES
        root = ET.fromstring(text.encode("utf-8"))
        assert root.tag == f"{{{RDF}}}RDF"
        for e in root.iter():
            for attr in (f"{{{RDF}}}about", f"{{{RDF}}}resource"):
                if e.get(attr) is not None:
                    assert ABSOLUTE.match(e.get(attr)), e.get(attr)
        assert len(root.findall(f"{{{OWL}}}Ontology")) == 1
        for c in root.findall(f"{{{OWL}}}Class"):
            assert (c.findtext(f"{{{RDFS}}}label") or "").strip()
        for d in root.findall(f"{{{OWL}}}DatatypeProperty"):
            assert len(d.findall(f"{{{RDFS}}}domain")) == 1 and len(d.findall(f"{{{RDFS}}}range")) == 1
            assert d.find(f"{{{RDFS}}}range").get(f"{{{RDF}}}resource").startswith("http://www.w3.org/2001/XMLSchema#")
            flag = d.find(f"{{{ONT}}}isIdentifier")
            assert flag is None or flag.text == "true"
        for o in root.findall(f"{{{OWL}}}ObjectProperty"):
            assert len(o.findall(f"{{{RDFS}}}domain")) == 1 and len(o.findall(f"{{{RDFS}}}range")) == 1
            assert o.findtext(f"{{{ONT}}}cardinality") in CARDINALITIES
            assert re.search(r" by rule \S", o.findtext(f"{{{RDFS}}}comment"))


def test_it_round_trips_through_an_xml_parser(shop):
    """Parsed, written out again by ElementTree and parsed once more, the model is the same and is the plan's."""
    text = ontology.ontology_rdfxml(shop, "shop", "shop")
    first = pr.project(ET.fromstring(text.encode("utf-8")))
    again = pr.project(ET.fromstring(ET.tostring(ET.fromstring(text.encode("utf-8")), encoding="utf-8")))
    assert first == again
    tables = {ontology.entity_name(t.name): t for t in shop.schema}
    assert {e["name"] for e in first["entities"]} == set(tables)
    for e in first["entities"]:
        assert [x["name"] for x in e["properties"]] == tables[e["name"]].column_names
    by_id = {e["id"]: e["name"] for e in first["entities"]}
    assert sorted((by_id[r["from"]], by_id[r["to"]]) for r in first["relationships"]) == sorted(
        (ontology.entity_name(r.source), ontology.entity_name(r.target)) for r in shop.relationships)
    root = ET.fromstring(text.encode("utf-8"))
    orders = next(c for c in root.findall(f"{{{OWL}}}Class") if c.findtext(f"{{{RDFS}}}label") == "Orders")
    assert orders.findtext(f"{{{RDFS}}}comment") == "Table shop.orders; key order_id (K2)."
    assert ontology.ontology_rdfxml(shop, "shop", "shop") == text                     # deterministic


def test_names_from_files_are_escaped_and_forbidden_characters_dropped():
    s = Schema(schema="dbo")
    s.tables['a&b<"c">'] = Table('a&b<"c">', [Column("id", "int"), Column("x'y\x01", "nvarchar")], schema="dbo")
    text = ontology.ontology_rdfxml(plan(s), "n & m")
    root = ET.fromstring(text.encode("utf-8"))
    assert root.find(f"{{{OWL}}}Ontology").findtext(f"{{{RDFS}}}label") == "n & m"
    assert "Table dbo.a&b<\"c\">;" in root.find(f"{{{OWL}}}Class").findtext(f"{{{RDFS}}}comment")
    assert "x'y" in [d.findtext(f"{{{RDFS}}}label") for d in root.findall(f"{{{OWL}}}DatatypeProperty")]
    assert pr.codes(pr.validate(text.encode("utf-8"))) == []


def test_ids_that_collide_after_the_first_letter_is_lower_cased_are_made_unique():
    """Two tables with one entity name, and a table named like a relationship: the export numbers them itself, so the
    Playground's collision rule passes and its importer has nothing to renumber."""
    s = Schema(schema="dbo")
    for name, cols in (("orders", ["order_id", "customer_id"]), ("customers", ["customer_id", "name"]),
                       ("order_items", ["order_items_id"]), ("OrderItems", ["OrderItems_id"]),
                       ("orders_has_customers", ["orders_has_customers_id"])):
        s.tables[name] = Table(name, [Column(c, "int") for c in cols], schema="dbo")
    p = plan(s)
    assert any(r.source == "orders" and r.target == "customers" for r in p.relationships)
    text = ontology.ontology_rdfxml(p, "x")
    r = pr.validate(text.encode("utf-8"))
    assert r["errors"] == []
    gids = [pr.graph_id(e["iri"]) for e in r["model"]["entities"]] + [pr.graph_id(x["iri"]) for x in r["model"]["relationships"]]
    assert len(gids) == len(set(gids))
    assert {"orderItems", "orderItems_2", "ordersHasCustomers", "ordersHasCustomers_2"} <= set(gids)


def test_the_size_limit_and_the_tables_filter(shop, monkeypatch):
    small = ontology.ontology_rdfxml(shop, "small", tables=["orders", "customers"])
    assert small.count("<owl:Class ") == 2 and small.count("<owl:ObjectProperty ") == 1
    with pytest.raises(PlanInputError):
        ontology.ontology_rdfxml(shop, "x", tables=["ghost"])
    monkeypatch.setattr(ontology, "RDFXML_MAX_BYTES", 1000)
    with pytest.raises(ValueError, match="8 MiB"):
        ontology.ontology_rdfxml(shop, "shop")


def test_ontology_files_carry_the_rdf_beside_the_ttl(shop):
    files = ontology.ontology_files(shop, "shop_ontology", workspace_id="w", item_id="i", item_name="shop_lh", schema="shop")
    assert files["ontology/shop_ontology/shop_ontology.rdf"] == ontology.ontology_rdfxml(shop, "shop_ontology", "shop")
    assert "Ontology Playground" in files["ontology/shop_ontology/README.generated.md"]


def test_check_offers_it_for_every_example_and_for_a_list_of_columns():
    """/check's worker writes the file (browser_check._ontology_rdfxml): named after the example, status Draft, and
    passing the Playground's rules; no row values, so the shop's example customer names are not in it."""
    from fabric_backend import browser_check as bc, tool_status as ts
    for kind, name in bc.NAMES.items():
        o = bc.analyze(kind)["ontology_rdfxml"]
        assert o["name"] == f"{name}_ontology.rdf" and o["status"] == "Draft" == ts.ONTOLOGY_RDFXML, kind
        assert pr.codes(pr.validate(o["xml"].encode("utf-8"))) == [], kind
        assert o["entity_types"] == o["xml"].count("<owl:Class ") > 0
    rows = {str(v) for t in seed.rows().values() for row in t for v in row if isinstance(v, str) and len(str(v)) > 3}
    sample = bc.analyze("sample")["ontology_rdfxml"]["xml"]
    assert not [v for v in rows if f">{v}<" in sample]
    o = bc.analyze("columns", text="orders.order_id\norders.customer_id\ncustomers.customer_id")["ontology_rdfxml"]
    assert o["entity_types"] == 2 and o["relationship_types"] == 1 and pr.codes(pr.validate(o["xml"].encode())) == []
