"""DP1: the catalog of classic data products, the four packs' tables mapped to it, and the gap report.

The catalog and the mapping are data (fabric_backend/data_products/); the loader and its checks are
fabric_backend/data_product_catalog.py; the report is docs/DATA-PRODUCT-CATALOG.md. These tests keep the three in step
with each other and with the pack manifests, so a pack that gains a table cannot be merged without a place for it.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

pytest.importorskip("yaml")

from fabric_backend import data_product_catalog as dpc, pack_manifest  # noqa: E402
from tests.test_n205_trust import CLAIMS  # noqa: E402
from tests.test_site import SALES  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "DATA-PRODUCT-CATALOG.md"
FILES = [dpc.CATALOG, dpc.MAPPING, dpc.SCHEMA, dpc.MAPPING_SCHEMA, ROOT / "fabric_backend" / "data_product_catalog.py", DOC]

# The classic products the round was asked to cover, by the catalog's ids.
ASKED = ("customer", "supplier", "product", "employee", "organisation", "chart_of_accounts", "sales_order", "delivery",
         "invoice", "payment", "open_item", "gl_journal_entry", "purchase_order", "goods_receipt", "inventory_movement",
         "price", "opportunity", "lead", "crm_account", "contact", "case", "campaign", "subscription", "quote", "budget", "date")


@pytest.fixture(scope="module")
def catalog():
    return dpc.load_catalog()


@pytest.fixture(scope="module")
def mapping():
    return dpc.load_mapping()


# ---------------------------------------------------------------- the catalog

def test_the_catalog_loads_and_is_well_formed(catalog):
    assert dpc.catalog_problems(catalog) == []
    ps = dpc.products(catalog)
    assert 25 <= len(ps) <= 32
    assert set(ASKED) <= set(ps)
    assert catalog["review_status"] == "proposed"


def test_every_product_says_grain_key_dimensions_measures_traps_and_questions(catalog):
    for p in catalog["products"]:
        assert p["grain"] and p["business_key"] and p["traps"], p["id"]
        assert 1 <= len(p["questions"]) <= 3, p["id"]
        if p["kind"] == "transaction":
            assert p["measures"] and p["roles"]["required"], p["id"]
            assert "date" in p["dimensions"], p["id"]
    sales_order = dpc.products(catalog)["sales_order"]
    assert sales_order["business_key"] == ["tenant_id", "order_number", "line_number"]
    assert {"header", "line"} == set(sales_order["roles"]["required"])
    assert any(t["kind"] == "header_amount_per_line" for t in sales_order["traps"])
    kinds = {t["kind"] for p in catalog["products"] for t in p["traps"]}
    assert {"header_amount_per_line", "versions", "soft_delete", "multi_company"} <= kinds


@pytest.mark.parametrize("damage, expected", [
    (lambda c: c["products"][0].pop("grain"), "grain is missing"),
    (lambda c: c["products"][0].update(area="astrology"), "area 'astrology'"),
    (lambda c: c["products"][0]["dimensions"].append("planet"), "dimension 'planet'"),
    (lambda c: c["products"][1].update(id=c["products"][0]["id"]), "a product id is repeated"),
    (lambda c: c["products"][0]["traps"].append({"kind": "weather", "text": "x"}), "a trap needs a kind"),
    (lambda c: c["products"][0].update(questions=["a?", "b?", "c?", "d?"]), "one to three questions"),
    (lambda c: c["products"][0]["roles"]["required"].append("footnote"), "role 'footnote'"),
    (lambda c: c["products"][0].update(business_key=[]), "business_key"),
])
def test_the_catalog_check_finds_what_is_wrong(catalog, damage, expected):
    c = copy.deepcopy(catalog)
    damage(c)
    assert any(expected in p for p in dpc.catalog_problems(c)), dpc.catalog_problems(c)


@pytest.mark.parametrize("schema, load", [(dpc.SCHEMA, dpc.load_catalog), (dpc.MAPPING_SCHEMA, dpc.load_mapping)])
def test_the_files_follow_their_json_schemas(schema, load):
    jsonschema = pytest.importorskip("jsonschema")
    s = json.loads(schema.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator.check_schema(s)
    assert sorted(map(str, jsonschema.Draft7Validator(s).iter_errors(load()))) == []


def test_the_schema_lists_are_the_loaders_lists():
    s = json.loads(dpc.SCHEMA.read_text(encoding="utf-8"))["properties"]["products"]["items"]["properties"]
    assert tuple(s["area"]["enum"]) == dpc.AREAS and tuple(s["kind"]["enum"]) == dpc.KINDS
    assert tuple(s["traps"]["items"]["properties"]["kind"]["enum"]) == dpc.TRAP_KINDS
    assert tuple(s["roles"]["properties"]["required"]["items"]["enum"]) == dpc.ROLES


# ---------------------------------------------------------------- the mapping against the manifests

def test_the_mapping_is_in_step_with_the_catalog_and_every_manifest(mapping, catalog):
    assert dpc.mapping_problems(mapping, catalog) == []


def test_every_manifest_table_is_mapped_or_listed_with_a_reason(mapping):
    for pack in pack_manifest.available():
        names = {e["name"] for e in pack_manifest.load(pack)["entities"]}
        mapped, nots = dpc.tables(pack, mapping), dpc.not_products(pack, mapping)
        assert names == set(mapped) | set(nots), pack
        assert not set(mapped) & set(nots), pack
        assert all(v["reason"] for v in nots.values())


def test_the_younium_pack_takes_the_salesforce_objects_from_the_salesforce_mapping(mapping):
    y = dpc.tables("younium_salesforce", mapping)
    s = mapping["packs"]["salesforce"]["tables"]
    assert y["ACCOUNT"] == s["ACCOUNT"] and y["ORDERITEM"] == s["ORDERITEM"]
    assert "ACCOUNT" not in mapping["packs"]["younium_salesforce"]["tables"]


@pytest.mark.parametrize("damage, expected", [
    (lambda m: m["packs"]["sap"]["tables"].pop("VBAK"), "sap.VBAK: in the manifest but neither mapped"),
    (lambda m: m["packs"]["sap"]["tables"].update(ZZ_MADE_UP=[{"product": "customer", "role": "master", "key": {},
                                                             "confidence": "high", "evidence": "unverified"}]),
     "sap.ZZ_MADE_UP: not a table of the sap manifest"),
    (lambda m: m["packs"]["sap"]["tables"]["KNA1"][0].update(evidence="verified"), "the pack's sources say 'unverified'"),
    (lambda m: m["packs"]["sap"]["tables"]["KNA1"][0]["key"].update(customer_number="NAME1"), "'NAME1' is not a column"),
    (lambda m: m["packs"]["sap"]["tables"]["KNA1"][0]["key"].update(order_number="KUNNR"), "'order_number' is not in the business key"),
    (lambda m: m["packs"]["sap"]["tables"]["KNA1"][0].update(product="unicorn"), "not a product of the catalog"),
    (lambda m: m["packs"]["dynamics365"]["not_a_data_product"].update(CUSTOMER={"kind": "helper", "reason": "x"}),
     "dynamics365.CUSTOMER: both mapped and listed"),
    (lambda m: m["sources"]["sap_cds"]["modules"].append("cds_nothing"), "module 'cds_nothing'"),
])
def test_the_mapping_check_finds_drift(mapping, catalog, damage, expected):
    m = copy.deepcopy(mapping)
    damage(m)
    problems = dpc.mapping_problems(m, catalog)
    assert any(expected in p for p in problems), problems


def test_the_evidence_follows_the_packs_own_sources(mapping):
    ev = lambda pack, t: mapping["packs"][pack]["tables"][t][0]["evidence"]  # noqa: E731
    assert ev("dynamics365", "SALES_HEADER") == "verified"          # Learn pages read
    assert ev("salesforce", "OPPORTUNITY") == "verified"            # Salesforce developer documentation read
    assert ev("sap", "VBAK") == "partly_verified"                   # one source of two read
    assert ev("sap", "KNA1") == "unverified"                        # help.sap.com not reached
    assert ev("sap", "I_SALES_ORDER") == "partly_verified"          # the release list read, the view's page not
    assert ev("younium_salesforce", "SUBSCRIPTIONS") == "unverified"


def test_the_mapping_file_is_in_the_layout_render_writes(mapping):
    assert dpc.render_mapping(mapping) == dpc.MAPPING.read_text(encoding="utf-8")


# ---------------------------------------------------------------- coverage

def test_coverage_states(mapping, catalog):
    sap = dpc.coverage("sap_tables", mapping, catalog)
    assert sap["sales_order"]["state"] == "full" and sap["sales_order"]["tables"]["header"] == ["VBAK"]
    assert sap["goods_receipt"]["state"] == "partial" and sap["goods_receipt"]["missing_required"] == ["header"]
    assert sap["inventory_movement"]["state"] == "none" and "MATDOC" in sap["inventory_movement"]["hint"]
    assert sap["date"]["state"] == "generated"
    sf = dpc.coverage("salesforce", mapping, catalog)
    assert sf["invoice"]["state"] == "none" and sf["opportunity"]["state"] == "full"
    assert sf["employee"]["state"] == "partial" and sf["employee"]["weak_required"] == ["master"]
    bc = dpc.coverage("business_central", mapping, catalog)
    assert bc["inventory_movement"]["state"] == "full" and bc["delivery"]["state"] == "none"
    yo = dpc.coverage("younium_salesforce", mapping, catalog)
    assert yo["subscription"]["state"] == "full" and yo["subscription"]["tables"]["version"] == ["SUBSCRIPTION_VERSIONS"]
    assert {dpc.coverage(s, mapping, catalog)["budget"]["state"] for s in mapping["sources"]} == {"none"}


def test_the_reports_matrix_is_the_codes_matrix():
    text = DOC.read_text(encoding="utf-8")
    block = re.search(r"<!-- matrix:start -->\n(.*?)\n<!-- matrix:end -->", text, re.S)
    assert block and block.group(1) == dpc.matrix_markdown()


def test_the_report_names_every_product_and_every_table_that_is_not_a_product(mapping, catalog):
    text = DOC.read_text(encoding="utf-8")
    for p in catalog["products"]:
        assert f"| {p['title']} |" in text, p["id"]
    nots = [n for pack in pack_manifest.available() for n in mapping["packs"][pack]["not_a_data_product"]]
    assert len(nots) == 7 and "Seven tables are no data product of their own" in text
    assert all(n in text for n in nots)


def test_the_report_says_what_it_rests_on_and_that_the_matcher_uses_no_ai():
    text = DOC.read_text(encoding="utf-8")
    text = re.sub(r"\s+", " ", text)
    assert "Nothing here has been verified on a customer system" in text
    assert "public documentation and synthetic demos" in text
    assert "no AI or language model anywhere in the decision" in text
    assert "Order to cash: 5 of 6 products present; delivery missing, so late-delivery questions cannot be answered" in text


# ---------------------------------------------------------------- what may not be said

def test_no_claim_of_certification_partnership_endorsement_compliance_or_speed():
    words = re.compile(r"\b(certified|certification|endorsed|endorsement|partnership|official partner|affiliated|"
                       r"compliant|compliance|approved by|faster|fastest|in seconds|in minutes)\b", re.I)
    for f in FILES:
        text = f.read_text(encoding="utf-8")
        assert not words.findall(text), (f.name, words.findall(text))
        assert not CLAIMS.findall(text), f.name
        low = text.lower()
        assert not [w for w in SALES if w in low], f.name


def test_no_prices_no_contact_names_and_no_fetch_of_sap_pages():
    money = re.compile(r"(?:[$€£]\s?\d|\b\d[\d ,.]*\s?(?:SEK|EUR|USD|kr)\b|\b(?:SEK|EUR|USD)\s?\d)")
    person = re.compile(r"\b(?:contact|account manager|sales rep(?:resentative)?) (?:at|from) Microsoft\b|@microsoft\.com", re.I)
    for f in FILES:
        text = f.read_text(encoding="utf-8")
        assert not money.findall(text), (f.name, money.findall(text))
        assert not person.findall(text), f.name
        assert "api.sap.com" not in text and "help.sap.com" not in text.replace("help.sap.com could not be reached", ""), f.name
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text), f.name
