"""D2 (16 November 2026): two explainer articles on the SAP-shaped sample (fabric_backend/sap_sample.py, synthetic, not
SAP data), written for people who search with a problem. Every number an article states is measured here, from the
engine or by running the article's own SQL on the sample, so an engine change that moves a number turns this red
instead of leaving a wrong page. The articles are served like the first blog post (tests/test_blog.py) and are listed
in the sitemap and llms.txt from pages.BLOG_POSTS."""
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import amounts, browser_check, evidence, pages, sap_sample, semantic_model, server, sql_sums
from fabric_backend.infer import plan

SALES_SLUG, BI_SLUG = "sap-sales-tables-in-fabric", "sap-tables-to-power-bi-report"
DIR = Path(pages.__file__).parent / "page_templates"
TEXT = {s: (DIR / f"BLOG-{s}.md").read_text(encoding="utf-8") for s in (SALES_SLUG, BI_SLUG)}
MODEL_TABLES = ["KNA1", "MARA", "VBAK", "VBAP", "LIKP", "LIPS", "VBRK", "VBRP"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    with TestClient(server.build_app()) as c:
        yield c


@pytest.fixture(scope="module")
def measured():
    """The engine on sap_sd: the plan with the rows, validate_plan's answer, the semantic model draft on the eight
    tables, the gold-view check and /check's findings."""
    src = sap_sample.source("sap_sd")
    try:
        p = plan(src.schema, execute=src.execute)
        v = evidence.validate(p, src.execute)
        v = {**v, "unit_counts": amounts.unit_counts(p, src.execute)}      # BL10: the sample has one currency, counted
        draft = semantic_model.draft(p, {"item_name": "sap_lh", "item_kind": "Lakehouse", "schema": "sap_sd",
                                         "schemas_enabled": True}, name="sap_sales", tables=MODEL_TABLES, validation=v)
        counts = {t: src.execute(f"SELECT COUNT(*) AS n FROM sap_sd.{t}")[0]["n"] for t in sap_sample.SCHEMAS["sap_sd"]}
        header_alone = round(src.execute("SELECT SUM(NETWR) AS s FROM sap_sd.VBAK")[0]["s"], 2)
        no_mandt = src.execute("SELECT COUNT(*) AS n FROM sap_sd.VBAK AS k JOIN sap_sd.VBAP AS p ON p.VBELN = k.VBELN")[0]["n"]
        open_orders = [r["VBELN"] for r in src.execute(
            "SELECT k.VBELN FROM sap_sd.VBAK AS k WHERE NOT EXISTS (SELECT 1 FROM sap_sd.LIPS AS d "
            "WHERE d.MANDT = k.MANDT AND d.VGBEL = k.VBELN) ORDER BY k.VBELN")]
        latest = [r["VBELN"] for r in src.execute(f"SELECT VBELN FROM sap_sd.VBAK ORDER BY ERDAT DESC, VBELN DESC LIMIT {len(open_orders)}")]
    finally:
        src.close()
    return {"plan": p, "validate": v, "draft": draft, "counts": counts, "header_alone": header_alone,
            "no_mandt": no_mandt, "open_orders": open_orders, "latest": latest,
            "gold": sql_sums.check(plan(sap_sample.schema("sap_sd")), sap_sample.gold_views("sap_sd")),
            "check": browser_check.analyze("sap_sd"), "facts": sap_sample.facts("sap_sd")}


@pytest.fixture
def hosted(monkeypatch):
    """The hosted tools on sap_sd: the golden tests' fake Fabric (tests/golden_support.py) for REST and the SQL endpoint,
    with the queries on schema sap_sd answered by the SAP-shaped sample, as docs/directory/shoot.py does."""
    import sys
    import requests
    import golden_support as gs
    fake = gs.FakeFabric()
    for verb in ("get", "post", "patch"):
        monkeypatch.setattr(requests, verb, getattr(fake, verb))
    monkeypatch.setitem(sys.modules, "pyodbc", gs.fake_pyodbc())
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "limiter", None)
    sap = sap_sample.source("sap_sd")
    shop_factory = server._execute_factory

    def factory(item, token):
        shop = shop_factory(item, token)
        return lambda sql, *a, **k: (sap.execute if "sap_sd" in sql.lower() else shop)(sql, *a, **k)
    monkeypatch.setattr(server, "_execute_factory", factory)
    platform = server._fabric.PLATFORM
    read = platform.read_schema
    monkeypatch.setattr(platform, "read_schema",
                        lambda execute, schema: sap_sample.schema("sap_sd") if schema.lower() == "sap_sd" else read(execute, schema))
    import json
    args = {"workspace": "demo", "source": "demo_lh", "schema": "sap_sd"}
    yield {"validate": json.loads(server.validate_plan(**args)), "plan": json.loads(server.plan_backend(**args, detail="summary"))}
    sap.close()


def _sql_blocks(md: str) -> list[str]:
    return [b.strip().rstrip(";") for b in re.findall(r"```sql\n(.*?)```", md, re.S)]


def _run(sql: str) -> list[dict]:
    src = sap_sample.source("sap_sd")
    try:
        return src.execute(sql)
    finally:
        src.close()


def _money(x: float) -> str:
    return f"{x:,.2f}"


# ------------------------------------------------------------------ served, listed, linked ----------------------------

@pytest.mark.parametrize("slug", [SALES_SLUG, BI_SLUG])
def test_the_article_is_served_listed_and_in_the_sitemap_and_llms_txt(client, slug):
    path = "/blog/" + slug
    r = client.get(path)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert client.get(path + ".md").content == (DIR / f"BLOG-{slug}.md").read_bytes()
    assert f'href="{path}"' in client.get("/blog").text
    assert f"https://krusgraph.test{path}</loc>" in client.get("/sitemap.xml").text
    assert f"https://krusgraph.test{path}.md" in client.get("/llms.txt").text
    post = pages.blog_post(slug)
    assert post["date"] == "2026-11-16" and len(post["description"]) < 160 and len(post["faq"]) == 3


def test_the_articles_link_to_check_and_to_each_other():
    for slug, other in ((SALES_SLUG, BI_SLUG), (BI_SLUG, SALES_SLUG)):
        md = TEXT[slug]
        assert "(https://krusgraph.com/check?example=sap_sd)" in md          # the sample, run in the browser
        assert f"(https://krusgraph.com/blog/{other})" in md
    assert "sap_sd" in browser_check.KINDS


def test_no_claim_beyond_what_is_tested():
    """No certification, compatibility, partnership, endorsement, speed or compliance claim, no customer, and the C1
    wording test (tests/test_c1_tool_description_wording.py) finds nothing promotional."""
    from tests.test_c1_tool_description_wording import promotional
    from tests.test_site import SALES
    banned = (r"certif", r"\bcompatible\b", r"\bpartner(?:ship)?\b", r"endorse", r"\bfaster\b", r"\bspeed\b", r"\bcomplian",
              r"\bGDPR\b", r"\bSOC ?2\b", r"\bISO\b", r"\bunique (?:tool|product|solution|approach|way)\b", r"\bonly tool\b", r"\bcustomers? of krusgraph\b")
    for slug, md in TEXT.items():
        assert not promotional(md), (slug, promotional(md))
        low = md.lower()
        assert not [w for w in SALES if w in low], slug
        hits = [p for p in banned if re.search(p, md, re.I)]
        assert not hits, (slug, hits)
        assert "not SAP data" in md and "synthetic" in md                     # says what the data is
        assert "16 November 2026" in md and "tests/test_d2_explainers.py" in md


# ------------------------------------------------------------------ article 1: how the tables connect -----------------

def test_sales_article_counts_are_the_samples(measured):
    md, c = TEXT[SALES_SLUG], measured["counts"]
    said = (f"The sample has {c['VBAK']} orders (VBAK) with {c['VBAP']} items (VBAP), {c['LIKP']} deliveries (LIKP) and "
            f"{c['VBRK']} invoices (VBRK), {c['KNA1']} customers (KNA1) and {c['MARA']} materials (MARA). Three of the items")
    assert said in md
    assert len(sap_sample.ORPHAN_ORDERS) == 3


def test_sales_article_keys_are_the_plans(measured):
    md, keys = TEXT[SALES_SLUG], measured["plan"].keys
    for t in ("VBAK", "VBAP", "KNA1", "LIKP", "LIPS", "VBRK", "VBRP", "MARA"):
        cols, rule = keys[t]
        assert rule == "SAP pack"
        assert re.search(rf"^\| {t} \| [^|]+ \| {re.escape(' + '.join(cols))} \|$", md, re.M), t
    assert measured["validate"]["summary"] == "10 of 10 keys unique, 15 of 19 relationships hold without orphans"
    assert "Counted against the sample's rows, all ten are unique." in md                  # the eight above, T001 and MAKT


def test_the_hosted_tools_numbers_are_the_articles(hosted):
    """What a person sees from the connector: the hosted plan also takes a key from the rows for each Z table (K6)."""
    summary = hosted["validate"]["summary"]
    assert summary == "Keys: 12 of 12 hold. Links: 15 of 19 hold, 4 fail."               # BL39: counts.summary's sentence
    for md in TEXT.values():
        assert f'`validate_plan` reported "{summary}"' in md
    keys = hosted["plan"]["keys"]
    assert sorted(t for t, k in keys.items() if k.endswith("(K6)")) == ["ZSD_KAM_ASSIGN", "ZSD_ORDER_EXT"]
    assert sum(k.endswith("(SAP pack)") for k in keys.values()) == 10
    assert "one for each of the two Z tables, which the rows gave (rule K6)" in TEXT[SALES_SLUG]
    pack = (Path(__file__).resolve().parent.parent / "docs" / "DIRECTORY-SUBMISSION.md").read_text(encoding="utf-8")
    assert f'"{summary}" (the hosted tool on the same rows' in pack


def test_sales_article_links_are_the_plans(measured):
    md, p = TEXT[SALES_SLUG], measured["plan"]
    links = {(r.source, tuple(r.source_cols), r.target): r.rule for r in p.relationships}
    rows = re.findall(r"^\| (\w+) \| ([A-Z, ]+) \| (\w+) \| [^|]+ \|$", md, re.M)
    assert len(rows) == 10
    for src, cols, tgt in rows:
        assert links.get((src, tuple(cols.split(", ")), tgt)) == "SAP pack", (src, cols, tgt)
    standard = [k for k, rule in links.items() if k[0] in sap_sample.STANDARD["sap_sd"]]
    assert len(standard) == 16 and all(links[k] == "SAP pack" for k in standard)
    assert "16 relationships between the standard tables, all from the SAP pack" in md
    extra = {(s, c, t) for s, c, t in standard} - {(s, tuple(c.split(", ")), t) for s, c, t in rows}
    assert extra == {("LIKP", ("MANDT", "KUNAG"), "KNA1"), ("VBRK", ("MANDT", "KUNAG"), "KNA1"),
                     ("LIPS", ("MANDT", "MATNR"), "MARA"), ("VBRP", ("MANDT", "MATNR"), "MARA"),
                     ("MAKT", ("MANDT", "MATNR"), "MARA"), ("VBRK", ("MANDT", "BUKRS"), "T001")}
    assert not any(r.source in ("LIKP", "VBRK") and r.target == "VBAK" for r in p.relationships)   # no header-to-header link


def test_sales_article_sql_returns_what_it_says(measured):
    chain, wrong, fanout, orphans = _sql_blocks(TEXT[SALES_SLUG])
    assert _run(chain) == [{"orders": 300, "deliveries": 292, "invoices": 292}]
    assert "it returns 300 orders, 292 deliveries and 292 invoices. The 8 orders" in TEXT[SALES_SLUG]
    assert len(measured["open_orders"]) == 8 and set(measured["open_orders"]) == set(measured["latest"])   # the most recent
    assert _run(wrong) == [{"matched_rows": 0}] and "On the sample it returns 0, because" in TEXT[SALES_SLUG]
    (row,) = _run(fanout)
    assert (row["joined_rows"], row["distinct_orders"]) == (841, 300)
    assert round(row["header_netwr_summed_per_item"], 2) == 20286871.77 and round(row["item_netwr"], 2) == 6125324.89
    assert measured["header_alone"] == 6125324.89
    for label, value in (("Joined rows", "841"), ("Distinct orders", "300"), ("Header NETWR summed over the join", "20,286,871.77"),
                         ("Item NETWR summed over the join", "6,125,324.89"), ("VBAK.NETWR summed on VBAK alone", "6,125,324.89")):
        assert f"| {label} | {value} |" in TEXT[SALES_SLUG], label
    assert f"{row['header_netwr_summed_per_item'] / row['item_netwr']:.1f}" == "3.3" and "3.3 times" in TEXT[SALES_SLUG]
    assert _run(orphans) == [{"items_without_order": 3}] and "It returns 3." in TEXT[SALES_SLUG]
    assert measured["counts"]["VBAP"] - 3 == 841
    assert measured["no_mandt"] == 841                       # one client: leaving MANDT out changes no count here


def test_sales_article_example_order_is_the_engines(measured):
    d = measured["facts"]["doubled"]
    assert (d["header"], d["line"], d["column"]) == ("VBAK", "VBAP", "NETWR")
    assert (_money(d["wrong"]), _money(d["right"])) == ("20,286,871.77", "6,125,324.89")
    ex = d["example"]
    assert ex["id"] == "100 + 0000010011" and ex["lines"] == 5
    assert f"order 0000010011 has a net value of {_money(ex['amount'])} and {ex['lines']} items, so it adds {_money(ex['repeated'])}" in TEXT[SALES_SLUG]


def test_sales_article_name_rule_links_and_their_orphans(measured):
    p, v = measured["plan"], measured["validate"]
    z = {r.target: r.rule for r in p.relationships if r.source == "ZSD_ORDER_EXT"}
    assert z == {"VBAK": "R3", "LIKP": "R3", "VBRK": "R3"}
    orph = {r["target"]: r["orphans"] for r in v["relationships"] if r["source"] == "ZSD_ORDER_EXT"}
    assert orph == {"VBAK": 1, "LIKP": 301, "VBRK": 301} and measured["counts"]["ZSD_ORDER_EXT"] == 301
    md = TEXT[SALES_SLUG]
    assert "generic name rule (R3) proposed three links from it: to VBAK, LIKP and VBRK" in md
    assert "The link to VBAK has 1 row with no matching order" in md and "The links to LIKP and VBRK have 301 such rows each: every row" in md


# ------------------------------------------------------------------ article 2: to a Power BI report ------------------

def test_bi_article_combined_keys_are_the_drafts(measured):
    s, md = measured["draft"]["summary"], TEXT[BI_SLUG]
    combined = s["combined_key_columns"]
    assert len(combined) == 22 and "needs 22 combined key columns" in md
    assert s["reads"]["layer"] == "silver"
    vbap = [(c["column"], " + ".join(c["combines"])) for c in combined if c["table"] == "VBAP"]
    assert vbap == [("MANDT_VBELN_POSNR_key", "MANDT + VBELN + POSNR"), ("MANDT_VBELN_key", "MANDT + VBELN"),
                    ("MANDT_MATNR_key", "MANDT + MATNR")]
    for col, parts in vbap:
        assert f"| VBAP | {col} | {parts} |" in md
    assert len([c for c in combined if c["for"] == [f"the key of {c['table']}"]]) == 8        # one per table's key
    from fabric_backend import silver
    spec = silver.spec(plan(sap_sample.schema("sap_sd")), {"item_name": "sap_lh", "item_kind": "Lakehouse", "schema": "sap_sd",
                                                           "schemas_enabled": True}, tables=MODEL_TABLES)
    assert all(f"'{c['column']}'" in str(spec) for c in combined)           # the silver step writes each of them


def test_bi_article_active_and_inactive_are_the_drafts(measured):
    s, p, md = measured["draft"]["summary"], measured["plan"], TEXT[BI_SLUG]
    among = [r for r in p.relationships if r.source in MODEL_TABLES and r.target in MODEL_TABLES]
    assert len(among) == 14 and "the plan has 14 relationships" in md
    # BL51: with validate_plan's counts the active set follows them (one filter path between two tables)
    assert (s["relationships_active"], s["relationships_inactive"], s["relationships_not_expressible"]) == (9, 5, 0)
    assert "the draft keeps 9 active and makes 5 inactive" in md
    assert "a filter on KNA1 would reach VBRP two ways" in [x["why"] for x in s["inactive"] if x["source"] == "VBRP"][0]
    to_kna1 = sorted(f"{r.source}.{r.source_cols[1]}" for r in among if r.target == "KNA1")
    assert to_kna1 == ["LIKP.KUNAG", "LIKP.KUNNR", "VBAK.KUNNR", "VBRK.KUNAG", "VBRK.KUNRG"] and "KNA1 is reached by five links" in md
    inactive_kna1 = {x["source"] + "." + x["columns"][0].split("_")[1] for x in s["inactive"] if x["target"] == "KNA1"}
    assert inactive_kna1 == {"LIKP.KUNNR", "VBRK.KUNRG"}                      # one per document stays active
    assert "The draft keeps VBAK.KUNNR, LIKP.KUNAG and VBRK.KUNAG active" in md
    assert "Decisions to check" in measured["draft"]["parts"]["README.generated.md"]
    cal = s["date_table"]
    assert cal["marked_as_date_table"] and [x["fact"] for x in cal["related"] if x["active"]] == ["VBAK", "LIKP", "VBRK"]
    assert "VBAK.ERDAT, LIKP.ERDAT and VBRK.ERDAT are active" in md
    assert len(cal["related"]) == 6 and all(x["column"] == "ERDAT" for x in cal["related"])


def test_bi_article_doubled_total_and_the_gold_views(measured):
    md, s = TEXT[BI_SLUG], measured["draft"]["summary"]
    assert "the order value of the sample becomes 20,286,871.77. The real total is 6,125,324.89" in md
    (view,) = _sql_blocks(md)
    assert view == sap_sample.GOLD_VIEWS["gold_revenue_by_customer_wrong"].format(schema="sap_sd")
    right = sap_sample.GOLD_VIEWS["gold_revenue_by_customer"].format(schema="sap_sd")
    assert view.replace("_wrong", "").replace("SUM(k.NETWR)", "SUM(p.NETWR)") == right
    g = measured["gold"]
    assert [f["view"] for f in g["flagged"]] == ["sap_sd.gold_revenue_by_customer_wrong"]
    assert list(g["read_not_flagged"]) == ["sap_sd.gold_revenue_by_customer"]
    heads = {(h["table"], h["column"]): h["summarize_by"] for h in s["header_amounts"]}
    assert heads == {("VBAK", "NETWR"): "none", ("VBAP", "NETWR"): "none", ("VBRK", "NETWR"): "none", ("VBRK", "MWSBK"): "none"}
    assert "VBAK.NETWR, VBRK.NETWR and VBRK.MWSBK, and VBAP.NETWR" in md
    m = [x for x in s["measures"] if x["table"] == "VBAK" and x["name"] == "Total NETWR"]
    assert m and m[0]["expression"] == "SUM('VBAK'[NETWR])" and "`Total NETWR = SUM('VBAK'[NETWR])`" in md
    assert {r[6] for r in sap_sample.rows("sap_sd")["VBAK"]} == {"EUR"} and "the sample has one currency, EUR" in md


def test_bi_article_check_titles_are_what_check_shows(measured):
    titles = {f["title"] for f in measured["check"]["findings"]}
    assert "VBAK.NETWR would be summed once per VBAP row" in titles and '"VBAK.NETWR would be summed once per VBAP row"' in TEXT[BI_SLUG]
    assert "VBAP.MANDT+VBELN → VBAK: 3 orphan(s)" in titles


def test_bi_article_status_of_the_creating_tools():
    """The three creating tools were tried live on the synthetic shop schema, and the article says no more."""
    from fabric_backend import tool_status as ts
    for t in ("create_silver_notebook", "create_semantic_model", "create_report"):
        assert ts.label(t).startswith("Tried live"), t
    assert "These three were tried live on the synthetic shop schema in a Fabric workspace, not on SAP tables." in TEXT[BI_SLUG]
