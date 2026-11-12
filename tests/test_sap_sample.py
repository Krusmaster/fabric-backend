"""n202: the SAP-shaped samples 'sap_sd' and 'sap_mm' (fabric_backend/sap_sample.py): synthetic, SAP-shaped, not SAP data.

tests/fixtures/sap_sample/planted.json is the source of truth: what the generator plants and what the engine found on
it (keys, links with their rules, the Z-table results, the doubled total, the late goods receipts). When the engine's
answer on the samples changes, a test here says what changed, and docs/SAMPLE-SAP.md and the Q&A answer must follow."""
import datetime as dt
import json
import re
from pathlib import Path

import pytest

from fabric_backend import browser_check as bc, evidence, sap_pack, sap_sample as s, seed, sql_sums
from fabric_backend.infer import plan

ROOT = Path(__file__).resolve().parents[1]
FIX = json.loads((ROOT / "tests/fixtures/sap_sample/planted.json").read_text(encoding="utf-8"))
DOC = (ROOT / "docs/SAMPLE-SAP.md").read_text(encoding="utf-8")


def _links(p):
    return [[x.source, list(x.source_cols), x.target, list(x.target_cols), x.rule] for x in p.relationships]


@pytest.fixture(scope="module", params=s.SAMPLES)
def sample(request):
    src = s.source(request.param)
    yield request.param, src
    src.close()


@pytest.fixture(scope="module")
def facts():
    return {name: s.facts(name) for name in s.SAMPLES}


# ------------------------------------------------------------------ the rows ----------------------------------------

def test_the_same_seed_gives_the_same_rows_and_another_seed_other_rows():
    for name in s.SAMPLES:
        a, b = s.rows(name), s.rows(name)
        assert a == b and list(a) == list(s.SCHEMAS[name])
        other = s.rows(name, 8)
        assert other != a and other["MARA"] == a["MARA"] and other["T001"] == a["T001"]    # master data fixed; movements vary
    with pytest.raises(ValueError):
        s.rows("sap_fi")


def test_a_few_hundred_rows_per_table_and_two_years_of_dates():
    counts = {name: {t: len(v) for t, v in s.rows(name).items()} for name in s.SAMPLES}
    assert counts == {
        "sap_sd": {"T001": 2, "KNA1": 120, "MARA": 150, "MAKT": 300, "VBAK": 300, "VBAP": 844, "LIKP": 292, "LIPS": 823,
                   "VBRK": 292, "VBRP": 823, "ZSD_ORDER_EXT": 301, "ZSD_KAM_ASSIGN": 80},
        "sap_mm": {"T001": 2, "LFA1": 40, "MARA": 150, "MAKT": 300, "EKKO": 260, "EKPO": 643, "EKBE": 600, "ZMM_PO_CONF": 642}}
    for name in s.SAMPLES:
        doc_dates = []
        for table, rows in s.rows(name).items():
            cols = s._cols(name, table)
            assert all(len(r) == len(cols) for r in rows), table
            if table in ("VBAK", "LIKP", "VBRK", "EKKO", "EKBE"):
                doc_dates += [v for r in rows for v in r if isinstance(v, dt.date)]
        assert min(doc_dates) >= s.START and max(doc_dates) <= s.END and (max(doc_dates) - min(doc_dates)).days >= 700, name


def test_every_standard_table_and_column_is_a_name_the_sap_pack_has():
    """For a standard table only names the repository's SAP pack already has (it cites SAP's public documentation);
    a column the pack does not name is not added. The pack knows no Z table."""
    pack = sap_pack.load("sap")["tables"]
    for name in s.SAMPLES:
        for table in s.STANDARD[name]:
            assert table in pack, table
            outside = [c for c, _t in s._cols(name, table) if c not in s.pack_columns(table)]
            assert not outside, (name, table, outside)
        for table in s.Z_TABLES[name]:
            assert table[0] in "ZY" and table not in pack and not s.pack_columns(table)
            assert all(c in ("MANDT", "VBELN", "POSNR", "EBELN", "EBELP") or c.startswith("ZZ_") for c, _t in s._cols(name, table)), table
    assert s._cols("sap_sd", "MAKT") == [("MANDT", "STRING"), ("MATNR", "STRING"), ("SPRAS", "STRING")]   # no text column: the pack names none
    assert not any(t in ("MATDOC", "MKPF", "MSEG") for t in s.SCHEMAS["sap_mm"])                         # the pack describes no material document
    assert all(c.startswith("ZZ_") for c, _t in s._cols("sap_sd", "ZSD_KAM_ASSIGN"))                   # only custom names


def test_marked_synthetic_with_invented_names_and_no_sap_branding():
    assert s.LABEL == "synthetic, SAP-shaped, not SAP data"
    for name in s.SAMPLES:
        src = s.source(name)
        try:
            assert s.LABEL in src.label and s.LABEL in src.notes[0]
        finally:
            src.close()
    sd, mm = s.rows("sap_sd"), s.rows("sap_mm")
    assert all(re.fullmatch(r"Example Customer \d{4}", r[2]) for r in sd["KNA1"])
    assert all(re.fullmatch(r"Example Supplier \d{4}", r[2]) for r in mm["LFA1"])
    text = (ROOT / "fabric_backend/sap_sample.py").read_text(encoding="utf-8") + DOC
    assert "not SAP data" in DOC and "synthetic" in DOC.lower()
    for word in (r"SAP[- ]certified", r"SAP[- ]compatible", r"\bpartner(ship)? (of|with) SAP\b", r"SAP partner", r"logo"):
        assert not re.search(word, text, re.I), word


# ------------------------------------------------------------------ what is planted ---------------------------------

def test_the_rows_hold_exactly_the_planted_problems():
    sd, mm = s.rows("sap_sd"), s.rows("sap_mm")
    orders = {r[1] for r in sd["VBAK"]}
    assert sorted({r[1] for r in sd["VBAP"] if r[1] not in orders}) == FIX["sap_sd"]["planted"]["orphan_items"]["missing_orders"]
    assert [r[1] for r in sd["ZSD_ORDER_EXT"] if r[1] not in orders] == [FIX["sap_sd"]["planted"]["z_orphan"]["missing_order"]]
    pos = {r[1] for r in mm["EKKO"]}
    assert [r[1] for r in mm["EKPO"] if r[1] not in pos] == FIX["sap_mm"]["planted"]["orphan_items"]["missing_orders"]
    items = {}
    for r in sd["VBAP"]:
        items[r[1]] = round(items.get(r[1], 0) + r[6], 2)
    assert all(abs(h[5] - items[h[1]]) < 0.01 for h in sd["VBAK"])      # the header holds the sum of its items
    assert all(r[0] == s.CLIENT for name in s.SAMPLES for t, rows in s.rows(name).items() if t != "ZSD_KAM_ASSIGN" for r in rows)
    kunnr = {r[1] for r in sd["KNA1"]}
    assert {r[0] for r in sd["ZSD_KAM_ASSIGN"]} <= kunnr                  # the custom-named column holds KNA1 customer numbers


def test_the_late_goods_receipts_are_every_eleventh(facts):
    mm = s.rows("sap_mm")
    conf = {(r[1], r[2]): r[3] for r in mm["ZMM_PO_CONF"]}
    late = [b for b in mm["EKBE"] if b[11] > conf[(b[1], b[2])]]
    assert len(late) == len(mm["EKBE"]) // s.LATE_EVERY and all(b[4] == "1" for b in mm["EKBE"])
    assert facts["sap_mm"]["late"] == FIX["sap_mm"]["engine"]["late"] == {"received_items": len(mm["EKBE"]), "late_items": len(late),
                                                                         "on_time_percent": round(100 * (len(mm["EKBE"]) - len(late)) / len(mm["EKBE"]), 1)}


# ------------------------------------------------------------------ plan, validate, amount_levels -------------------

def test_plan_finds_exactly_the_expected_keys_and_links(sample):
    name, src = sample
    want = FIX[name]["engine"]
    for ex in (None, src.execute):                       # by names, and with the rows (R5 adds nothing here)
        p = plan(src.schema, execute=ex)
        assert {t: {"columns": list(k), "rule": r} for t, (k, r) in p.keys.items()} == want["keys"]
        assert p.keyless == want["keyless"] == s.Z_TABLES[name]
        assert _links(p) == want["links"]
        assert not p.ambiguous and [x for x in p.relationships if x.rule == "R5"] == [] and p.proposed == []
    assert all(k["columns"][0] == "MANDT" and k["rule"] == "SAP pack" for t, k in want["keys"].items())   # composite keys with the client
    assert set(p.pack["tables"].values()) == set(want["pack_tables"]) == set(s.STANDARD[name])           # the pack knows no Z table


def test_header_to_item_and_document_flow_links_come_from_the_pack():
    links = {(a, tuple(b), c, tuple(d)): r for a, b, c, d, r in FIX["sap_sd"]["engine"]["links"] + FIX["sap_mm"]["engine"]["links"]}
    for item, header, cols in (("VBAP", "VBAK", ("MANDT", "VBELN")), ("LIPS", "LIKP", ("MANDT", "VBELN")),
                               ("VBRP", "VBRK", ("MANDT", "VBELN")), ("EKPO", "EKKO", ("MANDT", "EBELN"))):
        assert links[(item, cols, header, cols)] == "SAP pack", item
    assert links[("LIPS", ("MANDT", "VGBEL", "VGPOS"), "VBAP", ("MANDT", "VBELN", "POSNR"))] == "SAP pack"     # delivery item -> order item
    assert links[("VBRP", ("MANDT", "AUBEL", "AUPOS"), "VBAP", ("MANDT", "VBELN", "POSNR"))] == "SAP pack"     # billing item -> order item
    assert links[("VBRP", ("MANDT", "VGBEL", "VGPOS"), "LIPS", ("MANDT", "VBELN", "POSNR"))] == "SAP pack"     # billing item -> delivery item
    assert links[("EKBE", ("MANDT", "EBELN", "EBELP"), "EKPO", ("MANDT", "EBELN", "EBELP"))] == "SAP pack"     # history -> order item


def test_the_z_table_results_are_what_the_fixture_says(facts):
    """Item 2 of n202, measured: the Z tables get no key from the name rules (K3); a Z table that carries the standard
    key fields is linked by R3 to every table keyed by them, and the rows decide which link holds; R5 and
    suggest_relationships find nothing, because every SAP key starts with MANDT and both look only at single-column
    keys; the custom-named ZZ_KUNDE_NR is found by nothing."""
    sd, mm = facts["sap_sd"], facts["sap_mm"]
    assert sd["z"]["keys"] == {"ZSD_KAM_ASSIGN": None, "ZSD_ORDER_EXT": None} and mm["z"]["keys"] == {"ZMM_PO_CONF": None}
    z_sd = [(x["source"], x["target"], x["rule"], x["orphans"]) for x in sd["z"]["links"]]
    assert z_sd == [("ZSD_ORDER_EXT", "VBAK", "R3", 1), ("ZSD_ORDER_EXT", "LIKP", "R3", 301), ("ZSD_ORDER_EXT", "VBRK", "R3", 301)]
    z_mm = [(x["source"], x["source_cols"], x["target"], x["rule"], x["orphans"]) for x in mm["z"]["links"]]
    assert z_mm == [("ZMM_PO_CONF", ["MANDT", "EBELN"], "EKKO", "R3", 0), ("ZMM_PO_CONF", ["MANDT", "EBELN", "EBELP"], "EKPO", "R3", 0)]
    assert sd["r5"] == mm["r5"] == [] and sd["r5_proposed"] == mm["r5_proposed"] == []
    assert sd["not_found"] == FIX["sap_sd"]["engine"]["not_found"] == [
        {"source": "ZSD_KAM_ASSIGN", "column": "ZZ_KUNDE_NR", "points_at": "KNA1.KUNNR", "by_name": False, "by_rows": False}]
    assert sd["check"]["suggestions"] == ["ZSD_KAM_ASSIGN has no key; ZZ_KUNDE_NR is unique in the data",
                                          "ZSD_ORDER_EXT has no key; VBELN is unique in the data"]
    for name in s.SAMPLES:
        for k in ("keys", "keyless", "summary", "orphans", "amount_levels", "r5", "r5_proposed", "pack_tables", "check"):
            assert facts[name][k] == FIX[name]["engine"][k], (name, k)


def test_validate_counts_the_planted_orphans(sample):
    name, src = sample
    v = evidence.validate(plan(src.schema), src.execute)
    assert v["summary"] == FIX[name]["engine"]["summary"]
    got = [{"source": x["source"], "columns": x["columns"], "target": x["target"], "orphans": x["orphans"]} for x in v["relationships"] if x["orphans"]]
    assert got == FIX[name]["engine"]["orphans"]


def test_the_doubled_total_is_flagged_and_the_fixed_view_is_not(facts):
    sd = facts["sap_sd"]
    assert ["VBAK", "VBAP"] in sd["amount_levels"] and ["EKPO", "EKBE"] in facts["sap_mm"]["amount_levels"]
    assert sd["doubled"] == FIX["sap_sd"]["engine"]["doubled"]
    assert sd["doubled"]["wrong"] > 3 * sd["doubled"]["right"]
    g = sql_sums.check(plan(s.schema("sap_sd")), s.gold_views("sap_sd"))
    assert [f["view"] for f in g["flagged"]] == ["sap_sd.gold_revenue_by_customer_wrong"] and g["flagged"][0]["amount"] == "VBAK.NETWR"
    assert g["read_not_flagged"] == ["sap_sd.gold_revenue_by_customer"] and not g["could_not_be_read"]
    src = s.source("sap_sd")                              # the two views run on the rows: the wrong one adds up too much
    try:
        sums = {}
        for n, sql in s.GOLD_VIEWS.items():
            body = sql.format(schema="sap_sd").split(" AS\n", 1)[1]
            sums[n] = round(sum(r["order_value"] for r in src.execute(body)), 2)
    finally:
        src.close()
    assert sums == {"gold_revenue_by_customer_wrong": sd["doubled"]["wrong"], "gold_revenue_by_customer": sd["doubled"]["right"]}


def test_check_shows_exactly_the_fixture(facts):
    for name in s.SAMPLES:
        r = bc.analyze(name)
        assert r["verdict"]["headline"]["title"] == FIX[name]["engine"]["check"]["headline"] == "Enough to start"
        assert sorted([f["severity"], f["check"], f["title"]] for f in r["findings"]) == FIX[name]["engine"]["check"]["findings"]
        assert s.LABEL in r["source"]["label"] and r["evidence_report"]["name"] == f"{name}_evidence_report.md"


# ------------------------------------------------------------------ the seed ----------------------------------------

class _Spark:
    def __init__(self, schemas=("dbo",)):
        self.sql_run, self.saved, self.schemas = [], {}, schemas

    def sql(self, text):
        self.sql_run.append(text)
        rows = [(x,) for x in self.schemas]

        class Result:
            def collect(self):
                return rows
        return Result()

    def createDataFrame(self, data, ddl):
        spark = self

        class Writer:
            def mode(self, _m):
                return self

            def option(self, *_a):
                return self

            def saveAsTable(self, name):
                spark.saved[name] = (ddl, data)

        class Frame:
            write = Writer()
        return Frame()


def test_the_seed_writes_the_sap_samples_only_when_asked():
    from decimal import Decimal
    spark = _Spark()
    seed.seed(spark)
    assert not any(k.startswith("sap_") for k in spark.saved)
    spark = _Spark()
    counts = seed.seed(spark, sap=True)
    assert {k for k in spark.saved if k.startswith("sap_")} == {f"{n}.{t}" for n in s.SAMPLES for t in s.SCHEMAS[n]}
    assert "CREATE SCHEMA IF NOT EXISTS sap_sd" in spark.sql_run and "CREATE SCHEMA IF NOT EXISTS sap_mm" in spark.sql_run
    assert counts["sap_sd.VBAK"] == 300 and counts["sap_mm.EKKO"] == 260
    ddl, data = spark.saved["sap_sd.VBAK"]
    assert "NETWR DECIMAL(15,2)" in ddl and isinstance(data[0][5], Decimal)
    spark = _Spark(schemas=("default",))                  # without lakehouse schemas: not written
    seed.seed(spark, sap=True)
    assert not any(k.startswith("sap_") for k in spark.saved)


# ------------------------------------------------------------------ the docs ----------------------------------------

def test_the_doc_lists_every_table_with_its_rows_and_its_pack_source():
    for name in s.SAMPLES:
        for t, v in s.rows(name).items():
            assert re.search(rf"\| `{t}` \| {f'{len(v):,}'.replace(',', ' ')} \|", DOC), (name, t)
    pack = sap_pack.load("sap")
    for name in s.SAMPLES:
        for t in s.STANDARD[name]:
            src = pack["tables"][t]["sources"][0]
            assert re.search(rf"\| `{t}` \|[^\n]*{re.escape(pack['sources'][src]['title'].split(':')[0])}", DOC), t
    for z in s.Z_TABLES["sap_sd"] + s.Z_TABLES["sap_mm"]:
        assert re.search(rf"\| `{z}` \|[^\n]*invented", DOC), z


def _fmt(x: float) -> str:
    return f"{x:,.2f}".replace(",", " ")


def test_the_numbers_in_the_doc_and_the_film_scripts_come_from_the_engine(facts):
    d, late = facts["sap_sd"]["doubled"], facts["sap_mm"]["late"]
    films = DOC.split("## Film scripts", 1)[1]
    assert _fmt(d["wrong"]) in films and _fmt(d["right"]) in films and f"{d['wrong'] / d['right']:.2f}" in films
    assert f"{late['late_items']} of {late['received_items']}" in films and f"{late['on_time_percent']}" in films
    assert facts["sap_sd"]["summary"] in DOC and facts["sap_mm"]["summary"] in DOC
    blocks = re.findall(r"```sql\n(.*?)```", DOC, re.S)
    assert [b.strip() for b in blocks] == [s.GOLD_VIEWS["gold_revenue_by_customer_wrong"].format(schema="sap_sd"),
                                           s.GOLD_VIEWS["gold_revenue_by_customer"].format(schema="sap_sd"),
                                           s.KPI_SQL["late_goods_receipts"].format(schema="sap_mm")]
    src = s.source("sap_mm")                              # the KPI block runs on the sample and gives the numbers above
    try:
        assert src.execute(blocks[2]) == [{"received_items": late["received_items"], "late_items": late["late_items"]}]
    finally:
        src.close()


def _qa(text: str) -> str:
    m = re.search(r"Does Krusgraph work on customised SAP tables \(Z tables\)\?(.*?)(?=\n#|\n\*\*[A-Z]|\Z)", text, re.S)
    assert m, "the Z-table question is missing"
    return m.group(1)


def test_the_qa_answer_matches_the_measured_z_table_results(facts):
    """The public Q&A says what item 2 measured: keys and links that use the standard field names are found by a rule
    (R3) and the rows confirm or reject them; the Z tables get no key by name (the user gives it); a custom-named
    reference is not found and is added in the review; the pack covers standard tables only; synthetic, not a real
    SAP system."""
    docs = (ROOT / "fabric_backend/page_templates/DOCS.md").read_text(encoding="utf-8")
    sd = facts["sap_sd"]
    assert sd["z"]["links"][0]["rule"] == "R3" and sd["not_found"][0]["by_rows"] is False and sd["r5"] == []
    for text in (_qa(docs), _qa(DOC)):
        flat = " ".join(text.split())
        # n224 (S1 section 4 #3): the site's answer starts "Partly" (a Z table gets no key from the pack)
        first = flat.lstrip("*").strip()
        assert first.startswith(("Yes", "Partly")) or flat.split(" ", 1)[1].startswith(("Yes", "Partly")), flat[:80]
        for must in ("R3", "MANDT", "the rows", "no key", "review", "standard tables only", "synthetic", "not on a real SAP system"):
            assert must in flat, must
        assert "ZZ_KUNDE_NR" in flat or "custom" in flat
        assert not re.search(r"\bR5\b[^.]*(finds|found|links)", flat), "R5 found nothing on the samples"
