"""Round PK1: the standalone salesforce pack (fabric_backend/packs/salesforce/), its synthetic demo
(fabric_backend/salesforce_demo.py) and docs/SALESFORCE.md.

The pack was checked against Salesforce's public Object Reference and Field Reference, read on 17 November 2026; the
facts read (field names, types, lengths, relationship types and targets) are kept in
tests/fixtures/pk1/salesforce_reference.json, and these tests hold the pack to them: every column the pack names is a
field of its object, every link points where the page says, every key is the 18-character Id. The demo's rows are
synthetic and written from the pack; the tests run the engine on them and compare with EXPECTED, and docs/SALESFORCE.md's
generated section with what the engine says now.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from fabric_backend import evidence, privacy, sap_pack, salesforce_demo as sd, seed, younium_demo as yd
from fabric_backend.infer import plan
from test_golden import check, digest_large, engine_answers

ROOT = Path(__file__).resolve().parents[1]
REF = json.loads((Path(__file__).parent / "fixtures" / "pk1" / "salesforce_reference.json").read_text(encoding="utf-8"))
OBJECTS = REF["objects"]
DOC = ROOT / "docs" / "SALESFORCE.md"
ASKED = ["Account", "Contact", "Lead", "Opportunity", "OpportunityLineItem", "OpportunityContactRole", "Case", "Campaign", "CampaignMember",
         "Order", "OrderItem", "Product2", "Pricebook2", "PricebookEntry", "Quote", "QuoteLineItem", "Contract", "Asset", "User", "Task", "Event"]


def _obj(pack_table: str) -> str:
    return next(o for o in OBJECTS if o.upper() == pack_table)


def _field(obj: str, pack_col: str) -> str | None:
    """The API field a pack column means (ACCOUNT_ID -> AccountId), compared as the pack compares: without case and underscores."""
    return next((f for f in OBJECTS[obj]["fields"] if f.upper() == pack_col.replace("_", "")), None)


@pytest.fixture(scope="module")
def pack():
    return sap_pack.load("salesforce")


@pytest.fixture(scope="module")
def run():
    schema, execute = sd.sqlite()
    p = plan(schema)
    return schema, execute, p, evidence.validate(p, execute, max_items=200)


# ---------------------------------------------------------------- the pack against the pages read

def test_the_pack_covers_the_objects_asked_for_and_is_consistent(pack):
    assert sorted(pack["tables"]) == sorted(o.upper() for o in ASKED) and sorted(OBJECTS) == sorted(ASKED)
    assert sap_pack.problems(pack) == [] and pack["rule"] == "Salesforce pack"
    assert [m["file"] for m in pack["modules"]] == ["packs/salesforce/salesforce.json"]


def test_every_key_is_the_18_character_id(pack):
    for name, t in pack["tables"].items():
        assert t["key"] == ["ID"], name
        assert OBJECTS[_obj(name)]["fields"]["Id"] == {"type": "id", "length": 18}, name
        assert f"sf_fields_{name.lower()}" in t["sources"] and f"sf_obj_{name.lower()}" in t["sources"], name


def test_every_column_the_pack_names_is_a_field_of_its_object(pack):
    missing = []
    for name, t in pack["tables"].items():
        cols = set(t["key"]) | set(t.get("delta", [])) | {a["column"] for a in t.get("amounts", []) + t.get("quantities", [])}
        cols |= {p["column"] for p in t.get("personal", [])} | {c for u in t.get("unique_keys", []) for c in u}
        missing += [f"{name}.{c}" for c in sorted(cols) if _field(_obj(name), c) is None]
    for r in pack["relationships"]:
        missing += [f"{r['source']}.{c}" for c in r["source_cols"] if _field(_obj(r["source"]), c) is None]
    assert missing == []


def test_amounts_are_currency_fields_and_quantities_numbers(pack):
    for name, t in pack["tables"].items():
        for a in t.get("amounts", []):
            assert OBJECTS[_obj(name)]["fields"][_field(_obj(name), a["column"])]["type"] == "currency", (name, a)
        for q in t.get("quantities", []):
            assert OBJECTS[_obj(name)]["fields"][_field(_obj(name), q["column"])]["type"] == "double", (name, q)


def test_every_link_points_where_the_object_reference_says(pack):
    """A link's target is among the objects the page's 'Refers to' names. OwnerId is not on the object pages: the field
    reference gives it as a reference of 18 characters, and the field-types page says it holds the owning user's id."""
    for r in pack["relationships"]:
        src, tgt = _obj(r["source"]), _obj(r["target"])
        f = OBJECTS[src]["fields"][_field(src, r["source_cols"][0])]
        assert f["type"] == "reference" and f.get("length", 18) == 18, r
        if r["source_cols"] == ["OWNER_ID"]:
            assert "refers_to" not in f and "sf_id_field_type" in r["sources"] and tgt == "User", r
            continue
        assert tgt in f["refers_to"], (r, f)
        if f["relationship"] == "polymorphic":
            assert r["apply"] is False and "polymorphic" in r["condition"], r          # modelled honestly: listed, never applied
        if f["relationship"] == "masterdetail":
            assert "Master-detail" in r["condition"], r


def test_the_polymorphic_who_and_what_are_listed_for_every_target(pack):
    for act in ("TASK", "EVENT"):
        who = {r["target"] for r in pack["relationships"] if r["source"] == act and r["source_cols"] == ["WHO_ID"]}
        what = {r["target"] for r in pack["relationships"] if r["source"] == act and r["source_cols"] == ["WHAT_ID"]}
        f = OBJECTS[_obj(act)]["fields"]
        assert who == {o.upper() for o in f["WhoId"]["refers_to"]} == {"CONTACT", "LEAD"}
        assert what == {o.upper() for o in f["WhatId"]["refers_to"]} and f["WhatId"]["refers_to_others"] > 1000


def test_the_doubled_total_is_where_the_pages_put_it(pack):
    t = pack["tables"]
    assert [a["column"] for a in t["OPPORTUNITY"]["amounts"]] == ["AMOUNT"] and t["OPPORTUNITYLINEITEM"]["amounts"][0]["column"] == "TOTAL_PRICE"
    assert t["ORDER"]["amounts"][0] == {**t["ORDER"]["amounts"][0], "column": "TOTAL_AMOUNT", "level": "header"}
    assert {a["column"] for a in t["QUOTE"]["amounts"]} == {"TOTAL_PRICE", "GRAND_TOTAL"} and t["QUOTELINEITEM"]["amounts"][0]["column"] == "TOTAL_PRICE"
    trap = next(x for x in pack["traps"] if x["id"] == "sf_rollup_amounts")
    assert "read-only" in trap["text"] and "sf_obj_opportunitylineitem" in trap["sources"]


def test_sources_say_what_was_read(pack):
    s = pack["sources"]
    unread = sorted(k for k, v in s.items() if not v["fetched"])
    assert unread == ["sf_queue_owner"] and "Not read" in s["sf_queue_owner"]["note"]
    for k, v in s.items():
        assert v["url"].startswith(("https://developer.salesforce.com/docs/platform/", "https://learn.microsoft.com/en-us/",
                                    "https://help.salesforce.com/")), k
        assert v["publisher"] == ("Microsoft" if "learn.microsoft.com" in v["url"] else "Salesforce"), k
        if v["fetched"]:
            assert "17 November 2026" in v["note"], k
    assert {k for k in s if k.startswith("ms_")} >= {"ms_sf_objects_connector", "ms_sf_copy_activity", "ms_copy_job_create", "ms_mirroring_overview"}


def test_no_claim_of_partnership_certification_or_endorsement():
    words = re.compile(r"\b(certified|certification|endorsed|endorsement|partnership|official partner|affiliated)\b", re.I)
    for path in [ROOT / "fabric_backend/packs/salesforce/salesforce.json", DOC]:
        text = path.read_text(encoding="utf-8")
        hits = [m.group(0) for m in words.finditer(text)]
        assert all(h.lower() == "affiliated" for h in hits), (path.name, hits)
        assert text.count("affiliated") == text.count("not affiliated"), path.name


# ---------------------------------------------------------------- one truth: younium_salesforce reads this pack

def test_younium_salesforce_reads_the_salesforce_objects_from_this_pack(pack):
    y = sap_pack.load("younium_salesforce")
    assert not (sap_pack.PACKS / "younium_salesforce" / "salesforce.json").exists()
    shared = {n for n in y["tables"] if n in pack["tables"]}
    assert shared == {"ACCOUNT", "CONTACT", "OPPORTUNITY", "OPPORTUNITYLINEITEM", "PRODUCT2", "PRICEBOOKENTRY", "ORDER", "ORDERITEM", "CONTRACT"}
    assert all(y["tables"][n] == pack["tables"][n] for n in shared)
    assert all(y["sources"][k] == pack["sources"][k] for k in y["sources"] if k in pack["sources"])
    assert y["rule"] == "Younium + Salesforce pack"


def test_match_any_picks_the_pack_that_recognises_most():
    assert sap_pack.match_any(sd.sqlite()[0]).pack == "salesforce"
    assert sap_pack.match_any(yd.sqlite()[0]).pack == "younium_salesforce"
    assert sap_pack.match_any(seed.schema()) is None


def test_ordinary_names_alone_never_make_a_schema_salesforce(pack):
    from fabric_backend.schema import Schema
    common = sorted(n for n, t in pack["tables"].items() if t.get("common_name"))
    assert {"ACCOUNT", "CONTACT", "LEAD", "CASE", "ORDER", "USER", "TASK", "EVENT", "QUOTE", "ASSET", "CAMPAIGN"} <= set(common)
    rows = [("dbo", n.lower(), c, "nvarchar", i) for n in ("ACCOUNT", "CONTACT", "LEAD", "CASE", "TASK") for i, c in enumerate(["Id", "Name"], 1)]
    assert sap_pack.match_any(Schema.from_information_schema(rows, schema="dbo")) is None


# ---------------------------------------------------------------- the synthetic demo

def test_the_demo_is_synthetic_and_follows_the_reference():
    t = sd.tables()
    assert len(t) == sd.EXPECTED["tables"] == 21 and sum(len(r) for _, _, r in t.values()) == sd.EXPECTED["rows"]
    assert "SYNTHETIC" in sd.LABEL and "SYNTHETIC" in sd.__doc__ and "SYNTHETIC" in sd.notebook()
    for name, (cols, _kinds, rows) in t.items():
        assert set(cols) <= set(OBJECTS[name]["fields"]), (name, set(cols) - set(OBJECTS[name]["fields"]))
        for r in rows:
            for c, v in zip(cols, r):
                if c == "Id" or (OBJECTS[name]["fields"][c]["type"] == "reference" and v is not None):
                    assert isinstance(v, str) and len(v) == 18, (name, c, v)
                if isinstance(v, str) and "@" in v:
                    assert v.endswith("example.invalid"), (name, c, v)


def test_the_engine_plans_the_demo_from_the_pack(run):
    schema, _, p, v = run
    assert p.pack["pack"] == "salesforce" and len(p.keys) == 21 and all(c == ["Id"] for c, _ in p.keys.values())
    facit = json.loads((Path(__file__).parent / "fixtures" / "pk1" / "facit.json").read_text(encoding="utf-8"))["salesforce"]
    truth = {(r["source"], tuple(r["source_cols"]), r["target"]) for r in facit["relationships"]}
    assert {(r.source, tuple(r.source_cols), r.target) for r in p.relationships} == truth
    assert all(k["verdict"].startswith("unique") for k in v["keys"])


def test_the_planted_traps_are_found(run):
    _, execute, p, v = run
    orphans = {(r["source"], r["target"]) for r in v["relationships"] if r.get("orphans")}
    assert orphans == set(sd.EXPECTED["orphans"])
    findings = {(f["header"], f["line"]): f for f in v["amount_levels"]["findings"]}
    for header, line, col in sd.EXPECTED["doubled"]:
        f = findings[(header, line)]
        assert col in f["amount_columns"] and f["rows_per_header"]["max_lines"] == sd.EXPECTED["max_lines"][(header, line)]
        joined = execute(f"SELECT SUM(h.[{col}]) AS s FROM salesforce.[{header}] h JOIN salesforce.[{line}] l ON l.[{header}Id] = h.Id")[0]["s"]
        once = execute(f"SELECT SUM([{col}]) AS s FROM salesforce.[{header}] WHERE Id IN (SELECT [{header}Id] FROM salesforce.[{line}])")[0]["s"]
        assert joined > once, (header, joined, once)


def test_who_and_what_point_at_several_tables():
    t = sd.tables()
    ids = {n: {r[0] for r in rows} for n, (_c, _k, rows) in t.items()}
    who, what = {}, {}
    for act in ("Task", "Event"):
        cols, _k, rows = t[act]
        for r in rows:
            row = dict(zip(cols, r))
            for col, out in (("WhoId", who), ("WhatId", what)):
                if row[col]:
                    kind = next(n for n, s in ids.items() if row[col] in s)
                    out[kind] = out.get(kind, 0) + 1
    assert who == sd.EXPECTED["who"] and what == sd.EXPECTED["what"]


def test_personal_data_is_masked_through_the_pack(run):
    schema = run[0]
    flagged = privacy.personal_columns(schema, [t.name for t in schema])
    found = {(f["table"], f["column"]) for f in privacy.findings(flagged)}
    assert set(sd.EXPECTED["masked"]) <= found, set(sd.EXPECTED["masked"]) - found


def test_write_csv_labels_the_rows_synthetic(tmp_path):
    files = sd.write_csv(tmp_path)
    assert len(files) == 21 + 3 and (tmp_path / "README.txt").read_text().startswith("SYNTHETIC")
    assert json.loads((tmp_path / "_types.json").read_text())["Opportunity"]["Amount"] == "decimal(18,2)"


def test_the_engine_answers_on_the_demo_are_the_golden_ones():
    schema, _ = sd.sqlite()
    check("engine_salesforce_demo", digest_large(engine_answers(schema, "salesforce")))


# ---------------------------------------------------------------- the page

def test_the_page_quotes_the_engine_not_typed_numbers():
    text = DOC.read_text(encoding="utf-8")
    start, end = text.index("<!-- generated by python -m fabric_backend.salesforce_demo --doc"), text.index("<!-- end of generated section -->")
    assert text[start:end + len("<!-- end of generated section -->")] == sd._doc_block(sd.report())


def test_the_page_says_what_was_verified_and_what_not():
    text = DOC.read_text(encoding="utf-8")
    for must in ("17 November 2026", "developer.salesforce.com", "learn.microsoft.com", "fetched: false", "sf_queue_owner",
                 "not affiliated with Salesforce or Microsoft", "SYNTHETIC", "unverified"):
        assert must in text, must
