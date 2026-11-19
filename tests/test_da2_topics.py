"""Round DA2 (19 November 2026): create_data_agent writes data agent topics (one Markdown file per business area) and
example-query templates from the checked joins, by rules, with no AI (fabric_backend/agent_topics.py). Sources and what
Microsoft Learn does not document: docs/DATA-AGENT-TOPICS-TEMPLATES.md.

What these tests hold:
- the same plan and counts give the same topics and templates, byte for byte (a golden file on the synthetic SAP sample);
- a join is under "Checked joins" only when validate_plan counted it and it held, with the counts as evidence; an orphan
  join is listed as not to use, with its match rate; without counts no join is called checked and there is no template;
- the doubled header total (VBAK.NETWR over VBAP) is a known trap of the order-to-cash topic;
- no row value of the sample reaches a topic or a template, and the templates run on the sample's rows;
- the dry run writes nothing; Create writes each topic with PUT …/topics?fileName=krusgraph-*.md as text/markdown and
  the templates as example queries; a refused topic (preview runtime off) is reported and the agent still stands;
- the tool's description says what a person should understand, and makes no claim it cannot back.
"""
import json
import os
import re
from pathlib import Path

import pytest
import requests

from fabric_backend import agent_context, agent_topics, data_agent, evidence, gold, privacy, sap_demo, seed, server
from fabric_backend.infer import plan
from test_creating_tools import INFO, fake, holds, runnable, shop  # noqa: F401 - fixtures are used by name

GOLDEN = Path(__file__).parent / "golden" / "da2_sap_demo_topics.json"
UPDATE = os.environ.get("KRUSGRAPH_UPDATE_GOLDEN") == "1"


def sap():
    s, execute = sap_demo.sqlite()
    p = plan(s)
    return p, execute, evidence.validate(p, execute, max_items=200)


def built(p, v, schema="sap"):
    j = agent_context.joins(p, v)
    return agent_topics.build(p, schema, j, v, agent_context.repeated_amounts(p, v), privacy.personal_columns(p.schema))


# ------------------------------------------------------------------ the SAP sample ------------

def test_topics_and_templates_match_the_golden_file_and_never_change_between_runs():
    p, _, v = sap()
    first = built(p, v)
    for _ in range(2):
        p2, _, v2 = sap()
        assert built(p2, v2) == first
    got = {"topics": first["topics"], "templates": first["templates"]}
    if UPDATE:
        GOLDEN.write_text(json.dumps(got, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    assert json.loads(GOLDEN.read_text(encoding="utf-8")) == json.loads(json.dumps(got)), \
        "the DA2 topics changed: regenerate with KRUSGRAPH_UPDATE_GOLDEN=1 if that was meant"


def test_one_topic_per_business_area_with_front_matter_and_krusgraph_file_names():
    p, _, v = sap()
    topics = built(p, v)["topics"]
    assert [t["file_name"] for t in topics] == ["krusgraph-order-to-cash.md", "krusgraph-customer-master.md"]
    for t in topics:
        md = t["markdown"]
        assert md.startswith(f"---\nname: {t['name']}\ndescription: \"") and "\n---\n\n## " in md   # documented: name, description
        assert md.count("\n## ") == 1                                    # one heading per topic, subjects below it
        for h in ("### Tables and what their fields mean", "### Checked joins (use these)", "### Known traps"):
            assert h in md
        assert t["chars"] == len(md) < agent_topics.MAX_TOPIC_CHARS_PER_SOURCE
    o2c = topics[0]
    assert set(o2c["tables"]) >= {"sap_vbak", "sap_vbap", "sap_likp", "sap_vbrk", "sap_vbrp"}
    assert "`sap.sap_vbak` (VBAK: Sales document, header): one row per MANDT + VBELN (key rule SAP pack)." in o2c["markdown"]
    assert "  - `KUNNR`: points at sap_kna1.MANDT+KUNNR (rule SAP pack)." in o2c["markdown"]
    assert "  - `NETWR`: an amount at header level, in the currency of WAERK." in o2c["markdown"]


def test_checked_joins_carry_their_counts_and_the_orphan_join_is_not_to_use():
    p, _, v = sap()
    md = built(p, v)["topics"][0]["markdown"]
    checked = md.split("### Checked joins (use these)")[1].split("###")[0]
    assert ("`sap_vbak.MANDT = sap_kna1.MANDT AND sap_vbak.KUNNR = sap_kna1.KUNNR`: sap_vbak to sap_kna1, many-to-one (rule SAP "
            "pack; counted: 3 of 3 rows with a value find their sap_kna1 row (100.0% match); the target key is unique).") in checked
    assert "sap_vbap.VBELN = sap_vbak.VBELN" not in checked             # the sample plants an item without its order
    unsafe = md.split("### Joins not to use without asking")[1].split("###")[0]
    assert "sap_vbap.VBELN = sap_vbak.VBELN" in unsafe and "5 of 6 rows with a value find their sap_vbak row (83.3% match)" in unsafe


def test_the_doubled_header_total_is_a_known_trap_of_order_to_cash():
    p, _, v = sap()
    traps = built(p, v)["topics"][0]["markdown"].split("### Known traps")[1]
    assert "Never SUM(sap_vbak.NETWR) over sap_vbap rows: sum it on sap_vbak first" in traps
    assert "Header amounts and item amounts are different levels" in traps          # the pack's own trap, cited text


def test_no_row_value_reaches_a_topic_or_a_template():
    p, _, v = sap()
    text = json.dumps(built(p, v), ensure_ascii=False)
    for _name, (cols, _kinds, rows) in sap_demo.tables().items():
        for row in rows:
            for c, val in zip(cols, row):
                s = str(val)
                # a value that is more than one ordinary word (names, addresses, e-mail): single words such as "Contact"
                # are also words of the pack's own text
                if len(s) >= 5 and re.search(r"[\s@]", s.strip()) and s not in cols:
                    assert s not in text, f"{c}={s!r} leaked"
    assert "Demo Customer" not in text and "example.invalid" not in text


def test_personal_columns_are_left_out_of_the_topics_by_name():
    p, _, v = sap()
    cm = built(p, v)["topics"][1]["markdown"]
    assert "`NAME1`" not in cm and "Left out as personal data by name: NAME1" in cm


def test_templates_use_checked_joins_only_say_where_filters_go_and_run_on_the_rows():
    p, execute, v = sap()
    b = built(p, v)
    safe = {(e["source"], e["target"]) for e in agent_context.joins(p, v)["safe"]}
    assert 0 < len(b["templates"]) <= agent_topics.MAX_TEMPLATES
    for t in b["templates"]:
        src, tgt = t["from"].removeprefix("checked join ").split(" -> ")
        assert (src, tgt) in safe
        assert t["query"].startswith("-- Template from the checked join ") and "-- For one " in t["query"]
        assert execute(t["query"]) is not None                       # T-SQL, run on the sample's rows through SQLite
    cust = next(t for t in b["templates"] if t["from"] == "checked join sap_vbak -> sap_kna1")
    assert cust["question"] == "Which KNA1 (customer master) has the most VBAK (sales document) rows?"
    assert "-- For one KNA1 (customer master), add: WHERE t.[MANDT] = '<MANDT>' AND t.[KUNNR] = '<KUNNR>'" in cust["query"]
    assert "-- For one period, add: WHERE s.[ERDAT] BETWEEN '<from>' AND '<to>'" in cust["query"]
    assert "-- For one TVKO (sales organizations), add: WHERE s.[MANDT] = '<MANDT>' AND s.[VKORG] = '<VKORG>'" in cust["query"]
    assert len({t["question"] for t in b["templates"]}) == len(b["templates"])


def test_without_counts_nothing_is_called_checked_and_no_template_is_made():
    p, _, _ = sap()
    b = built(p, None)
    assert b["templates"] == []
    for t in b["topics"]:
        assert "- None yet. No join was counted: create_data_agent with validate=true counts them." in t["markdown"]
        assert "% match" not in t["markdown"]


def test_gold_views_get_one_template_each_over_their_columns():
    p, _, v = sap()
    views = gold.spec(p, {"schema": "sap", "schemas_enabled": True})["views"]
    tmpl = agent_topics.gold_templates(views, "gold", p)
    assert tmpl and len(tmpl) <= len(views)
    for t in tmpl:
        assert "FROM [gold]." in t["query"] and "JOIN" not in t["query"] and t["from"].startswith("gold view gold.")


# ------------------------------------------------------------------ the tool ------------------

def test_the_dry_run_shows_topics_and_templates_and_writes_nothing(shop, fake, monkeypatch):  # noqa: F811
    f = fake()
    monkeypatch.setattr(server._evidence, "validate", lambda p, execute, max_items=200: holds(p))
    out = json.loads(server.create_data_agent(*shop, name="shop_agent", schema="shop", validate=True))
    assert out["dry_run"] is True and f.topics == {} and not [c for c in f.calls if c[0] in ("put", "post", "patch")]
    a = out["agent"]
    assert [t["file_name"] for t in a["topics"]] == ["krusgraph-customers.md", "krusgraph-products.md", "krusgraph-other-tables.md"]
    assert a["templates"] and all(t["query"].startswith("-- Template from the checked join") for t in a["templates"])
    assert a["topics_note"].startswith("3 topic file(s)") and "preview" in a["topics_note"]
    assert out["reuse"].startswith("Krusgraph checks the joins once, with evidence and your approval; your data agent then "
                                   "reuses them in topics and templates.")
    assert any("/topics?fileName=krusgraph-<area>.md" in r for r in out["rest"])
    runnable(a["templates"])


def test_create_writes_topics_as_markdown_and_templates_as_examples(shop, fake, monkeypatch):  # noqa: F811
    f = fake()
    monkeypatch.setattr(server._evidence, "validate", lambda p, execute, max_items=200: holds(p))
    puts = []
    real = requests.put
    monkeypatch.setattr(requests, "put", lambda url, **k: puts.append((url, k)) or real(url, **k))
    out = json.loads(server.create_data_agent(*shop, name="shop_agent", schema="shop", validate=True, dry_run=False, publish=False))
    assert out["result"]["status"] == "Succeeded"
    assert sorted(f.topics) == ["krusgraph-customers.md", "krusgraph-other-tables.md", "krusgraph-products.md"]
    assert f.topics["krusgraph-customers.md"].startswith("---\nname: Customers\n")
    for url, k in puts:
        assert url.endswith("/staging/datasources/ds-1/topics") and k["headers"]["Content-Type"] == "text/markdown"
        assert k["params"]["fileName"].startswith("krusgraph-")
    assert "topics: 3 of 3 written" in out["result"]["log"]
    questions = {s["question"] for s in f.fewshots}
    assert {t["question"] for t in out["agent"]["templates"]} <= questions
    assert {t["question"] for t in out["agent"]["fewshots"]} <= questions
    assert not [c for c in f.calls if c[0] == "delete"]


def test_a_refused_topic_is_reported_and_the_agent_still_stands(shop, fake, monkeypatch):  # noqa: F811
    from test_creating_tools import Resp
    f = fake(fail={"/topics": Resp(400, {"errorCode": "InvalidRequest", "message": "topics need the preview runtime"})})
    out = json.loads(server.create_data_agent(*shop, name="shop_agent", schema="shop", dry_run=False, publish=True))
    log = " ".join(out["result"]["log"])
    assert out["result"]["status"] == "Succeeded" and out["result"]["published"] is True
    assert "topics: 0 of 3 written; not written: krusgraph-customers.md (HTTP 400)" in log and "preview runtime" in log
    assert f.published


def test_only_krusgraph_topic_files_are_ever_written():
    calls = []

    class R:
        status_code = 200

    class Req:
        @staticmethod
        def put(url, **k):
            calls.append(k["params"]["fileName"])
            return R()
    words = data_agent.write_topics(Req, {}, "https://x/v1/topics", [
        {"file_name": "krusgraph-a.md", "markdown": "# a"}, {"file_name": "company-policies.md", "markdown": "# b"}])
    assert calls == ["krusgraph-a.md"] and "company-policies.md (not a Krusgraph topic file name)" in words


def test_a_source_learn_does_not_list_as_sql_gets_no_topics():
    p = plan(seed.schema("shop"))
    d = data_agent.draft(p, {**INFO, "item_kind": "MirroredAzureDatabricksCatalog"}, "a", "shop", validation=holds(p))
    assert d["topics"] == [] and d["topics_note"].startswith("no topics: Learn documents topics for SQL data sources only")
    assert d["templates"]


def test_the_description_says_what_a_person_should_see_and_claims_nothing_it_cannot_back():
    doc = server.create_data_agent.__doc__ if hasattr(server.create_data_agent, "__doc__") else ""
    text = " ".join((doc or "").split()) + " " + server._DATA_AGENT_REUSE
    assert "Krusgraph checks the joins once, with evidence and your approval; your data agent then reuses them in topics and templates" in text
    for word in ("partner", "certified", "endorsed", "faster", "seconds", "accuracy", "Microsoft recommends", "% more"):
        assert word.lower() not in text.lower()


@pytest.mark.parametrize("path", ["docs/DATA-AGENT-TOPICS-TEMPLATES.md"])
def test_the_doc_cites_learn_with_the_date_read(path):
    text = (Path(__file__).parent.parent / path).read_text(encoding="utf-8")
    for url in ("https://learn.microsoft.com/fabric/data-science/data-agent-topics",
                "https://learn.microsoft.com/rest/api/fabric/dataagent/staging/upload-datasource-topic",
                "https://learn.microsoft.com/fabric/data-science/data-agent-example-queries",
                "https://learn.microsoft.com/rest/api/fabric/articles/item-management/definitions/data-agent-definition",
                "https://learn.microsoft.com/fabric/data-science/data-agent-add-datasources"):
        assert url in text, url
    assert "19 November 2026" in text and "not tested live" in text.lower()
