"""BL39 (backlog C-31, BL3 follow-up), 23 November 2026: validate_plan's summary says counts.summary's numbers.

Before, validate_plan wrote its own: "5 of 7 relationships hold without orphans" on the planted-faults shop, where the
one count (counts.summary, the review, the receipt and the cards) says "2 of 7 hold, 5 fail" (a link to a table whose
key is not unique fails), and "2 of 2 keys" where max_items had left 15 of 17 keys not counted. Now every number in the
answer's summary is the one count's, on the shop, the planted-faults shop, the SAP demo and the multi-lakehouse
fixture; what followed the counts (checked n of m, the time budget) is kept."""
import json
import re

import pytest

from fabric_backend import counts, evidence, sap_demo, server, shop_faults
from fabric_backend.infer import plan as infer_plan
from fabric_backend.platforms import local
from fabric_backend.shop_faults import make_plan


def _numbers(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"\d+", text)]


def _cases():
    src = local.sample_source()
    p = infer_plan(src.schema)
    yield "shop", p, evidence.validate(p, src.execute, 200)
    r = shop_faults.check()
    yield "shop_faults", make_plan(shop_faults.schema()), r["validate"]
    s, ex = sap_demo.sqlite()
    p3 = infer_plan(s)
    yield "sap_demo", p3, evidence.validate(p3, ex, 200)
    yield "sap_demo max_items=10", p3, evidence.validate(p3, ex, 10)


@pytest.mark.parametrize("name,plan,validation", list(_cases()), ids=lambda x: x if isinstance(x, str) else "")
def test_the_summary_numbers_are_the_one_count(name, plan, validation):
    said = server._one_count_summary(plan, dict(validation), None)
    one = counts.summary(plan, validation)
    assert said.startswith(one["sentence"]), (name, said)
    assert _numbers(said)[: len(_numbers(one["sentence"]))] == _numbers(one["sentence"])
    assert "relationships hold without orphans" not in said


def test_the_planted_faults_now_say_five_links_fail():
    r = shop_faults.check()
    said = server._one_count_summary(make_plan(shop_faults.schema()), r["validate"], None)
    assert said.startswith("Keys: 5 of 6 hold, 1 fails. Links: 2 of 7 hold, 5 fail.")
    assert r["validate"]["summary"].startswith("5 of 6 keys unique, 5 of 7 relationships")      # what it said before


def test_what_followed_the_counts_is_kept():
    s, ex = sap_demo.sqlite()
    p = infer_plan(s)
    v = evidence.validate(p, ex, 10)
    said = server._one_count_summary(p, v, None)
    assert "15 not counted" in said and said.endswith("Checked 10 of 51; raise max_items to check the rest.")


def test_the_hosted_answer_on_several_lakehouses_says_the_one_count(monkeypatch):
    mlh = pytest.importorskip("fixtures.multi_lakehouse")
    e = mlh.EXPECTED["c"]
    mlh.install(monkeypatch, "c")
    v = json.loads(server.validate_plan(workspace=mlh.WORKSPACE, source="sales_product_lh", schema=e["schema"],
                                        detail="full", max_items=200))
    assert re.match(r"^Keys: \d+ of \d+ hold", v["summary"]) and "relationships hold without orphans" not in v["summary"]
