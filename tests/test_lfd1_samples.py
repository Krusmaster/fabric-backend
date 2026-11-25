"""Round LFD1: the two synthetic samples of the change-by-chat demo (fabric_backend/lfd_demo.py, docs/SAMPLE-LFD.md).

The plan as plan_backend makes it and the check as validate_plan runs it give lfd_demo.EXPECTED byte for byte on both
samples; without its test customers shop_lfd gives exactly what the shop gives; the shop, the SAP demo and the golden
files are untouched (tests/test_golden.py runs as before)."""
from __future__ import annotations

import json

import pytest

from fabric_backend import amounts, evidence, lfd_demo, sap_demo, seed, server
from fabric_backend.platforms.local import sample_source


def _rel(src, sc, tgt, tc) -> str:
    return f"{src}.{'+'.join(sc)} -> {tgt}.{'+'.join(tc)}"


def facts(schema, execute) -> dict:
    """What plan_backend and validate_plan answer, in the form EXPECTED keeps: the plan of the hosted tools
    (server._hosted_plan: names rules, R5, the SAP pack) and the check of validate_plan (evidence.validate, max_items 60)."""
    p = server._hosted_plan(schema, None, None, execute)
    v = evidence.validate(p, execute, max_items=60)
    return {
        "plan_summary": p.summary(),
        "keys": {t: f"{'+'.join(c)} ({r})" for t, (c, r) in p.keys.items()},
        "relationships": [f"{_rel(r.source, r.source_cols, r.target, r.target_cols)} ({r.rule})" for r in p.relationships],
        "check_summary": v["summary"],
        "key_rows": {k["table"]: [k["rows"], k["distinct"]] for k in v["keys"]},
        "checked": [f"{_rel(r['source'], r['columns'], r['target'], r['target_columns'])}: {r['rows_with_value']} with a value, "
                    f"{r['orphans']} orphan(s)" for r in v["relationships"]],
        "header_amounts": [f"{f['header']}.{'+'.join(f['amount_columns'])} over {f['line']}: up to "
                           f"{f['rows_per_header']['max_lines']} per header" for f in v["amount_levels"]["findings"]],
    }


def _text(value) -> str:
    return json.dumps(value, indent=1, ensure_ascii=False)


@pytest.fixture(scope="module", params=lfd_demo.SAMPLES)
def sample(request):
    schema, execute = lfd_demo.sqlite(request.param)
    return request.param, schema, execute


def test_plan_and_check_give_expected_byte_for_byte(sample):
    name, schema, execute = sample
    got = {**facts(schema, execute), "numbers": lfd_demo.numbers(name, execute)}
    assert _text(got) == _text(lfd_demo.EXPECTED[name])


def test_without_the_test_customers_shop_lfd_is_the_shop():
    schema, execute = lfd_demo.sqlite("shop_lfd", include_test=False)
    src = sample_source()
    assert _text(facts(schema, execute)) == _text(facts(src.schema, src.execute))
    n = lfd_demo.numbers("shop_lfd", execute)
    want = lfd_demo.EXPECTED["shop_lfd"]["numbers"]
    assert (n["customers"], n["addresses"], n["orders"], n["order_lines"], n["order_value"]) == \
        (want["real_customers"], want["real_addresses"], want["real_orders"], want["real_order_lines"], want["real_order_value"]) == \
        (10, 17, 60, 134, "51296.70")
    assert n["order_value_per_customer"] == "5129.67" and n["test_orders"] == 0
    # the rows are the shop's own, with is_test and region added
    rows, base = lfd_demo.shop_rows(include_test=False), seed.rows(42)
    assert [r[:3] for r in rows["customers"]] == base["customers"] and [r[:3] for r in rows["addresses"]] == base["addresses"]
    assert {k: v for k, v in rows.items() if k not in ("customers", "addresses")} == \
        {k: v for k, v in base.items() if k not in ("customers", "addresses")}


def test_the_numbers_of_the_plan():
    n = lfd_demo.EXPECTED["shop_lfd"]["numbers"]
    assert (n["customers"], n["addresses"], n["orders"], n["order_lines"], n["order_value"]) == (12, 19, 66, 146, "56834.70")
    assert (n["real_customers"], n["real_orders"], n["real_order_lines"], n["real_order_value"]) == (10, 60, 134, "51296.70")
    assert (n["real_via_customer_rows"], n["real_via_customer_value"]) == (103, "93842.80")
    assert (n["real_ship_to_found"], n["real_orders"]) == (60, 60) and n["ship_to_regions"] == 2
    assert (n["real_order_value_per_customer"], n["order_value_per_customer"]) == ("5129.67", "4736.23")


def test_two_test_customers_one_address_each_six_orders_of_923():
    rows = lfd_demo.shop_rows()
    test = {c[0] for c in rows["customers"] if c[3]}
    assert len(test) == 2 and all(c[3] is False for c in rows["customers"] if c[0] not in test)
    assert sorted(a[1] for a in rows["addresses"] if a[1] in test) == sorted(test)
    orders = [o for o in rows["orders"] if o[1] in test]
    own = {a[0]: a[1] for a in rows["addresses"]}
    assert len(orders) == 6 and all(own[o[3]] == o[1] for o in orders)        # each ships to its customer's own address
    price = {p[0]: p[3] for p in rows["products"]}
    ids = {o[0] for o in orders}
    lines = [i for i in rows["order_items"] if i[0] in ids]
    assert len(lines) == 12
    for oid in ids:
        assert round(sum(q * price[p] for o, _, p, q in lines if o == oid), 2) == 923.00
    regions = {a[3] for a in rows["addresses"]}
    assert regions == {"North", "South"}


def test_the_order_value_is_the_engines_quantity_times_list_price():
    schema, execute = lfd_demo.sqlite("shop_lfd")
    m = amounts.order_amount_measures(server._hosted_plan(schema, None, None, execute))["measures"]
    assert [(x["table"], x["column"], x["dimension"], x["price"]) for x in m] == [("order_items", "quantity", "products", "list_price")]
    assert "is_test" not in lfd_demo.SHOP_SQL["order_value_cents"] and "quantity" in lfd_demo.SHOP_SQL["order_value_cents"]


def test_sap_lfd_header_sums_are_the_engines():
    schema, execute = lfd_demo.sqlite("sap_lfd")
    p = server._hosted_plan(schema, None, None, execute)
    found = {(f["header"], f["line"]): amounts.before_after(schema.schema, f, execute) for f in amounts.check(p, execute)["findings"]}
    n = lfd_demo.EXPECTED["sap_lfd"]["numbers"]
    vbak = found[("sap_vbak", "sap_vbap")]
    assert (f"{vbak['summed_per_header']:.2f}", f"{vbak['summed_over_lines']:.2f}") == \
        (n["order_value_per_header"], n["order_value_over_lines"]) == ("950.00", "2150.00")
    vbrk = found[("sap_vbrk", "sap_vbrp")]
    assert (f"{vbrk['summed_per_header']:.2f}", f"{vbrk['summed_over_lines']:.2f}") == (n["billed"], n["billed_over_lines"]) == ("600.00", "1000.00")
    assert (n["billing_documents"], n["billing_documents_counted"], n["billed_without_cancellations"]) == (3, 1, "400.00")


def test_sap_lfd_adds_to_the_sap_demo_and_keeps_its_plan():
    small, lfd = sap_demo.tables(), lfd_demo.sap_tables()
    assert list(lfd) == list(small) and len(lfd) == sap_demo.EXPECTED["tables"] == 17
    for name, (cols, kinds, rows) in small.items():
        lcols, lkinds, lrows = lfd[name]
        assert lcols[:len(cols)] == cols and lkinds[:len(kinds)] == kinds
        assert [r[:len(cols)] for r in lrows[:len(rows)]] == rows, name
    assert lfd["VBRK"][0][-3:] == ["VBTYP", "FKSTO", "SFAKN"]
    vbrk = {r[1]: r for r in lfd["VBRK"][2]}
    assert vbrk["0090000002"][-2] == "X" and vbrk["0090000003"][-1] == "0090000002"
    assert ("100", "2000", "1000", "EUR") in lfd["TVKO"][2]
    # the same keys and relationships as the SAP demo: the new rows change counts, not the plan
    s1, e1 = sap_demo.sqlite()
    s2, e2 = lfd_demo.sqlite("sap_lfd")
    p1, p2 = server._hosted_plan(s1, None, None, e1), server._hosted_plan(s2, None, None, e2)
    assert p1.keys == p2.keys and [vars(r) for r in p1.relationships] == [vars(r) for r in p2.relationships]


def test_only_the_planted_orphan_needs_review_on_sap_lfd():
    checked = lfd_demo.EXPECTED["sap_lfd"]["checked"]
    assert [c for c in checked if not c.endswith(" 0 orphan(s)")] == \
        ["sap_vbap.MANDT+VBELN -> sap_vbak.MANDT+VBELN: 7 with a value, 1 orphan(s)"]


def test_unknown_sample_is_refused():
    with pytest.raises(ValueError, match="unknown sample"):
        lfd_demo.sqlite("shop")
