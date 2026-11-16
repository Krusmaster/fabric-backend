"""n230: released SAP CDS views in the SAP pack (packs/sap/cds_*.json) and the sample shaped like them
(fabric_backend/sap_cds_demo.py, seed(spark, schema="sap_cds")). Synthetic rows, written from the pack: a run on them
shows that the engine reads CDS-shaped tables, never that the pack is right about SAP."""
import json
import re
from pathlib import Path

import pytest

from fabric_backend import evidence, sap_cds_demo as d, sap_pack, seed
from fabric_backend.infer import plan
from fabric_backend.schema import Schema

ROOT = Path(__file__).resolve().parents[1]
MODULES = sorted((sap_pack.PACKS / "sap").glob("cds_*.json"))
STYLES = ("view", "plain", "lower", "snake", "upper")


def _views():
    return {n: t for n, t in sap_pack.load()["tables"].items() if t.get("source_name")}


# ------------------------------------------------------------------ the pack modules --------------------------------

def test_three_modules_for_order_to_cash_master_data_and_the_journal():
    assert [p.stem for p in MODULES] == ["cds_journal", "cds_master_data", "cds_order_to_cash"]
    views = _views()
    assert len(views) == 19 and sap_pack.problems(sap_pack.load()) == []
    assert {views[n]["source_name"] for n in views} >= {"I_SalesDocument", "I_SalesDocumentItem", "I_BillingDocument", "I_BillingDocumentItem",
                                                         "I_Customer", "I_Product", "I_JournalEntry", "I_JournalEntryItem"}


def test_every_view_says_proposed_names_its_table_and_carries_no_client():
    p = sap_pack.load()
    for path in MODULES:
        m = json.loads(path.read_text(encoding="utf-8"))
        assert m["status"] == "documented" and m["status_note"].startswith("Proposed, not tested on a customer."), path.name
    for name, t in _views().items():
        assert name.startswith("I_") and t["variants"] == ["s4hana"], name
        assert not set(t["key"]) & set(sap_pack.CLIENT_COLUMNS), name
        assert t["corresponds_to"]["table"] in p["tables"] and not p["tables"][t["corresponds_to"]["table"]].get("source_name"), name
        assert t["sources"] and t["corresponds_to"]["sources"], name
    want = {"I_SALES_DOCUMENT": "VBAK", "I_SALES_DOCUMENT_ITEM": "VBAP", "I_BILLING_DOCUMENT": "VBRK", "I_BILLING_DOCUMENT_ITEM": "VBRP",
            "I_CUSTOMER": "KNA1", "I_PRODUCT": "MARA", "I_JOURNAL_ENTRY": "BKPF", "I_JOURNAL_ENTRY_ITEM": "ACDOCA"}
    assert {n: _views()[n]["corresponds_to"]["table"] for n in want} == want


def test_keys_amounts_and_associations_as_the_pack_states_them():
    v = _views()
    assert v["I_SALES_DOCUMENT_ITEM"]["key"] == ["SALES_DOCUMENT", "SALES_DOCUMENT_ITEM"]
    assert v["I_JOURNAL_ENTRY_ITEM"]["key"] == ["SOURCE_LEDGER", "COMPANY_CODE", "FISCAL_YEAR", "ACCOUNTING_DOCUMENT", "LEDGER_GL_LINE_ITEM", "LEDGER"]
    assert v["I_SALES_DOCUMENT"]["amounts"] == [{"column": "TOTAL_NET_AMOUNT", "level": "header", "currency": "TRANSACTION_CURRENCY"}]
    assert v["I_SALES_DOCUMENT_ITEM"]["amounts"] == [{"column": "NET_AMOUNT", "level": "item", "currency": "TRANSACTION_CURRENCY"}]
    assert "SalesDocumentItem" in v["I_SALES_DOCUMENT_ITEM"]["source_columns"]
    rels = [r for r in sap_pack.load()["relationships"] if r["source"] in v]
    assert len(rels) == 44 and all(r["target"] in v for r in rels)
    item = next(r for r in rels if (r["source"], r["target"]) == ("I_SALES_DOCUMENT_ITEM", "I_SALES_DOCUMENT"))
    assert item["cardinality"] == "many-to-one" and "_Item [0..*]" in item["association"]
    sold = next(r for r in rels if (r["source"], r["target"], r.get("role")) == ("I_SALES_DOCUMENT", "I_CUSTOMER", "sold_to"))
    assert sold["source_cols"] == ["SOLD_TO_PARTY"] and "_SoldToParty" in sold["association"]


def test_a_source_is_marked_read_only_when_it_was():
    src = sap_pack.load()["sources"]
    assert src["cds_ms_mirroring_sap"]["fetched"] and "15 November 2026" in src["cds_ms_mirroring_sap"]["note"]
    for sid in ("sap_hub_cds", "sap_help_vdm", "sap_help_cds_client", "sap_help_s4_journal"):
        assert src[sid]["fetched"] is False and "Unverified" in src[sid]["note"], sid


# ------------------------------------------------------------------ matching -------------------------------------------

@pytest.mark.parametrize("name", ["I_SalesDocument", "i_salesdocument", "I_SALESDOCUMENT", "i_sales_document", "SalesDocument", "salesdocument",
                                  "sales_document", "bronze.I_SalesDocument", "sap_i_salesdocument", "cds_SalesDocument"])
def test_a_view_is_known_with_and_without_its_prefix_and_in_any_case(name):
    assert sap_pack.pack_table(name) == "I_SALES_DOCUMENT"


def test_the_tables_keep_their_names():
    assert sap_pack.pack_table("bronze.SAP_VBAK") == "VBAK" and sap_pack.pack_table("orders") is None


@pytest.mark.parametrize("style", STYLES)
def test_the_plan_finds_every_key_and_link_from_the_pack(style):
    s = d.schema(style=style)
    p = plan(s)
    assert p.pack["pack"] == "sap" and len(p.pack["tables"]) == 14 == len(p.keys) and not p.keyless
    assert {rule for _cols, rule in p.keys.values()} == {"SAP pack"} and {r.rule for r in p.relationships} == {"SAP pack"}
    assert len(p.relationships) == 30
    item = d.rename("I_SalesDocumentItem", style)
    assert [c.lower().replace("_", "") for c in p.keys[item][0]] == ["salesdocument", "salesdocumentitem"]
    links = {(r.source, r.target) for r in p.relationships}
    for a, b in (("I_SalesDocumentItem", "I_SalesDocument"), ("I_SalesDocument", "I_Customer"), ("I_BillingDocumentItem", "I_BillingDocument"),
                 ("I_BillingDocumentItem", "I_SalesDocumentItem"), ("I_JournalEntryItem", "I_JournalEntry"), ("I_BillingDocument", "I_JournalEntry")):
        assert (d.rename(a, style), d.rename(b, style)) in links, (a, b)
    assert p.pack["variant_hint"].startswith("s4hana")


def test_a_view_without_its_key_fields_is_not_taken():
    rows = [("s", "I_SalesDocument", c, "nvarchar", i) for i, c in enumerate(["SalesDocument", "SoldToParty"], 1)]
    rows += [("s", "I_SalesDocumentItem", c, "nvarchar", i) for i, c in enumerate(["SalesDocument", "NetAmount"], 1)]   # no SalesDocumentItem
    rows += [("s", "I_Customer", c, "nvarchar", i) for i, c in enumerate(["Customer"], 1)]
    m = sap_pack.match(Schema.from_information_schema(rows, schema="s"))
    assert set(m.tables) == {"I_SalesDocument", "I_Customer"} and m.unmatched_keyless == ["I_SalesDocumentItem"]


def test_customer_and_product_alone_are_ordinary_words():
    def schema(names):
        rows = [("s", t, c, "nvarchar", i) for t, cols in names.items() for i, c in enumerate(cols, 1)]
        return Schema.from_information_schema(rows, schema="s")
    plain = schema({"customer": ["customer", "name"], "product": ["product", "name"]})
    assert sap_pack.match_any(plain) is None and plan(plain).pack is None
    assert sap_pack.match_any(schema({"I_Customer": ["Customer"], "I_Product": ["Product"]})).pack == "sap"
    assert sap_pack.match_any(schema({"customer": ["customer"], "SalesDocument": ["SalesDocument", "SoldToParty"]})).pack == "sap"
    assert plan(seed.schema()).pack is None                                  # the shop stays the shop


def test_the_amounts_come_back_in_the_schemas_spelling():
    m = sap_pack.match(d.schema())
    assert {"table": "I_SalesDocument", "column": "TotalNetAmount", "level": "header", "currency": "TransactionCurrency"} in sap_pack.amounts(m)
    low = sap_pack.match(d.schema(style="snake"))
    assert {"table": "i_sales_document", "column": "TOTAL_NET_AMOUNT", "level": "header", "currency": "TRANSACTION_CURRENCY"} in sap_pack.amounts(low)


def test_sap_pack_draft_answers_on_views():
    out = sap_pack.draft(plan(d.schema()))
    assert out["summary"].startswith("14 SAP table(s) recognised, 30 pack relationship(s) apply")
    row = next(t for t in out["tables"] if t["table"] == "I_SalesDocument")
    assert row["source_name"] == "I_SalesDocument" and row["corresponds_to"] == "VBAK" and row["key"] == ["SalesDocument"] and "de" not in row


# ------------------------------------------------------------------ the sample -----------------------------------------

def test_the_sample_carries_only_names_the_pack_has():
    views = {t["source_name"]: t for t in _views().values()}
    tables = d.tables()
    assert len(tables) == d.EXPECTED["tables"] == 14
    for name, (cols, types, rows) in tables.items():
        assert set(cols) <= set(views[name]["source_columns"]), (name, set(cols) - set(views[name]["source_columns"]))
        assert all(len(r) == len(cols) == len(types) for r in rows), name
        assert not {c.upper() for c in cols} & set(sap_pack.CLIENT_COLUMNS), name
    text = json.dumps([[str(v) for v in r] for _c, _t, rows in tables.values() for r in rows])
    assert "@" not in text and "Demo Customer 10" in text


def test_the_row_check_flags_the_orphan_and_the_doubled_total():
    f = d.facts()
    assert (f["keys_unique"], f["keys_checked"], f["links_held"], f["links_checked"]) == (14, 14, 29, 30)
    assert f["summary"] == "14 of 14 keys unique, 29 of 30 relationships hold without orphans"
    source, target, n = d.EXPECTED["orphan"]
    assert f["orphans"] == [{"source": source, "columns": ["SalesDocument"], "target": target, "orphans": n}]
    found = {(h["header"], h["line"], h["columns"][0]): (h["over_the_join"], h["on_the_header"]) for h in f["header_amounts"]}
    for header, line, column, wrong, right in d.EXPECTED["header_amounts"]:
        assert found[(header, line, column)] == (wrong, right)


def test_the_same_findings_as_on_the_table_shaped_demo():
    """The dbo sample (sap_demo) and the CDS sample tell one story: an orphan item and a header amount repeated on lines."""
    from fabric_backend import sap_demo
    schema, execute = sap_demo.sqlite()
    v = evidence.validate(plan(schema), execute, max_items=200)
    old = {(sap_pack.pack_table(r["source"]), sap_pack.pack_table(r["target"])) for r in v["relationships"] if r["orphans"]}
    assert ("VBAP", "VBAK") in old
    views = _views()
    f = d.facts()
    new = {(views[sap_pack.pack_table(o["source"])]["corresponds_to"]["table"], views[sap_pack.pack_table(o["target"])]["corresponds_to"]["table"])
           for o in f["orphans"]}
    assert new == {("VBAP", "VBAK")}
    assert ("VBAK", "VBAP") in {(sap_pack.pack_table(x["header"]), sap_pack.pack_table(x["line"])) for x in v["amount_levels"]["findings"]}


def test_a_run_on_the_sample_is_never_recorded_as_verification():
    src = d.source()
    try:
        v = evidence.validate(plan(src.schema), src.execute, max_items=200)
    finally:
        src.close()
    report = sap_pack.verification(v, "synthetic CDS-shaped sample", "2026-11-15")
    assert report["counts"]["verified"] >= 25 and report["counts"]["review"] == 1
    with pytest.raises(ValueError):
        sap_pack.write_verified(report)


class _Spark:
    def __init__(self, schemas=("dbo",)):
        self.sql_calls, self.saved, self.schemas = [], [], schemas

    def sql(self, q):
        self.sql_calls.append(q)
        rows = [(s,) for s in self.schemas] if q == "SHOW SCHEMAS" else []
        return type("R", (), {"collect": lambda self_: rows})()

    def createDataFrame(self, data, ddl):
        spark = self

        class W:
            def mode(self, *_):
                return self

            def option(self, *_):
                return self

            def saveAsTable(self, name):
                spark.saved.append((name, len(data), ddl))
        return type("DF", (), {"write": W()})()


def test_seed_writes_the_sample_to_its_schema_and_nothing_else():
    spark = _Spark()
    counts = seed.seed(spark, schema="sap_cds")
    assert "CREATE SCHEMA IF NOT EXISTS sap_cds" in spark.sql_calls
    assert [n for n, _rows, _ddl in spark.saved] == [f"sap_cds.{t}" for t in d.tables()] and len(counts) == 14
    assert counts["I_SalesDocument"] == 2 and counts["I_SalesDocumentItem"] == 5 and counts["I_JournalEntryItem"] == 6
    ddl = dict((n, x) for n, _rows, x in spark.saved)["sap_cds.I_SalesDocument"]
    assert "TotalNetAmount DECIMAL(15,2)" in ddl and "SalesDocument STRING" in ddl
    bare = _Spark(schemas=())                                               # a lakehouse without schemas: the default schema
    seed.seed(bare, schema="sap_cds")
    assert bare.saved[0][0] == "I_CompanyCode" and not [q for q in bare.sql_calls if q.startswith("CREATE SCHEMA")]


# ------------------------------------------------------------------ the docs and the wording -------------------------

def test_the_doc_states_the_measured_numbers():
    doc = (ROOT / "docs/SAP-CDS.md").read_text(encoding="utf-8")
    f = d.facts()
    assert f["summary"] in doc and 'seed(spark, schema="sap_cds")' in doc
    assert "proposed, not tested on a customer" in doc.lower() and "Unverified" in doc
    assert "1 900" in doc and "700" in doc
    for name in ("SAP-CDS.md",):
        assert name in (ROOT / "docs/PACKS.md").read_text(encoding="utf-8") and name in (ROOT / "docs/SAP.md").read_text(encoding="utf-8")


def test_nothing_says_certified_or_compatible_about_sap():
    """No text of the pack, the sample, the docs of this round or the site's templates claims an SAP certification or
    compatibility. docs/MIGRATION-DESIGN.md and two tests quote the words to forbid them; they are not read here."""
    words = re.compile(r"sap[\s\-]*(certified|certification|compatible)|certified (by|for) sap|compatible with sap|sap[\s\-]*partner", re.I)
    paths = list((ROOT / "fabric_backend/packs").rglob("*.*")) + list((ROOT / "fabric_backend/page_templates").rglob("*.*"))
    paths += [ROOT / "fabric_backend" / n for n in ("sap_cds_demo.py", "sap_pack.py", "sap_demo.py", "sap_sample.py", "seed.py", "pack_manifest.py")]
    paths += [ROOT / "docs" / n for n in ("SAP-CDS.md", "SAP.md", "PACKS.md", "SAMPLE-SAP.md", "SAP-MIRRORING.md", "LIVE-TEST-SAP.md")]
    paths += [ROOT / "README.md", ROOT / "CHANGELOG.md"]
    hits = []
    for path in paths:
        if path.is_file() and path.suffix in (".json", ".yaml", ".md", ".py", ".html", ".txt"):
            hits += [f"{path.relative_to(ROOT)}: {m.group(0)}" for m in words.finditer(path.read_text(encoding="utf-8", errors="ignore"))]
    assert hits == []
