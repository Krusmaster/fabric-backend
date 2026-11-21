"""2026-11-21, round BL10 (sprint item BL10, backlog C-16): measures that respect currency, unit and sign.

A sum of NETWR over EUR and SEK rows is no amount, and a sum of KWMENG over pieces and kilograms is no quantity. The
semantic model draft keeps every suggested SUM within one currency or one unit (fabric_backend/level_measures.py,
respect_units; the names in fabric_backend/amounts.py). All rows are synthetic: the SAP-shaped demo (sap_demo.py), the
SAP sample (sap_sample.py) and the shop (seed.py). Nothing here calls Fabric; no DAX is evaluated, the TMDL is read back
and every reference resolved as tests/test_n133_level_measures.py does.
"""
from __future__ import annotations

import contextlib
import re

import pytest

from fabric_backend import amounts, level_measures, sap_demo, seed, semantic_model
from fabric_backend.infer import plan
from fabric_backend.schema import Column, Schema, Table
from test_n133_level_measures import _parses_and_resolves

SEK = "UPDATE sap.[sap_vbap] SET WAERK = 'SEK' WHERE POSNR = (SELECT MIN(POSNR) FROM sap.[sap_vbap])"


def _update(ex, sql: str) -> None:
    """sap_demo's execute reads result rows; an UPDATE has none (the statement has run when that read fails)."""
    with contextlib.suppress(TypeError):
        ex(sql)


GUARD = re.compile(r"^IF\((HASONEVALUE\('[^']+'\[[^\]]+\]\)(?: && HASONEVALUE\('[^']+'\[[^\]]+\]\))*), (.+)\)$")


def _draft(full: bool = True, counts: bool = False, rows=None):
    s, ex = sap_demo.sqlite(full=full)
    if rows:
        rows(ex)
    p = plan(s)
    v = {"unit_counts": amounts.unit_counts(p, ex, max_items=100)} if counts else None
    return p, semantic_model.draft(p, {"schema": "sap"}, validation=v)


def _summed(expression: str) -> list[tuple[str, str]]:
    """The (table, column) pairs a measure adds up: SUM('t'[c]), and the price inside SUMX(... * RELATED('t'[c]))."""
    return re.findall(r"SUM\('([^']+)'\[([^\]]+)\]\)", expression) + re.findall(r"RELATED\('([^']+)'\[([^\]]+)\]\)", expression)


@pytest.fixture(scope="module")
def sap():
    return _draft()


def test_names_that_carry_a_currency_or_a_unit():
    for c in ("WAERS", "WAERK", "HWAER", "RWCUR", "RHCUR", "currency", "currency_code", "CurrencyIsoCode", "valuta"):
        assert amounts.is_currency_column(c), c
    for c in ("CurrencyRateDate", "currency_rate", "exchange_rate", "NETWR", "amount"):
        assert not amounts.is_currency_column(c), c
    assert not amounts.is_currency_column("currency", "decimal(10,2)")           # a code is text, never a number
    assert not amounts.is_currency_column("currency_date", "date")
    for c in ("MEINS", "VRKME", "BSTME", "unit", "quantity_unit", "uom", "enhet", "unit_of_measure"):
        assert amounts.is_unit_column(c), c
    for c in ("unit_price", "units_in_stock", "UnitPrice", "KWMENG"):
        assert not amounts.is_unit_column(c), c
    for c in ("NETPR", "KBETR", "unit_price", "UnitPrice", "list_price"):
        assert amounts.is_unit_price(c), c
    assert not amounts.is_unit_price("NETWR") and not amounts.is_unit_price("TotalPrice")
    assert all(amounts.is_quantity_like(c) for c in ("MENGE", "KWMENG", "LFIMG", "FKIMG", "quantity", "antal"))


def test_the_currency_is_found_in_the_table_or_in_the_document_header(sap):
    p, _ = sap
    assert amounts.label_columns(p, "sap_vbap", "NETWR", "currency")["columns"] == [("sap_vbap", "WAERK")]
    assert amounts.label_columns(p, "sap_vbap", "KWMENG", "unit")["columns"] == [("sap_vbap", "VRKME")]
    vbrp = amounts.label_columns(p, "sap_vbrp", "NETWR", "currency")           # the invoice line: the currency is on VBRK
    assert vbrp["where"] == "header" and vbrp["columns"] == [("sap_vbrk", "WAERK")]
    assert amounts.label_columns(p, "sap_ekpo", "NETWR", "currency")["columns"] == [("sap_ekko", "WAERS")]
    assert amounts.label_columns(p, "sap_acdoca", "WSL", "currency")["columns"] == [("sap_acdoca", "RWCUR")]
    assert amounts.label_columns(p, "sap_acdoca", "HSL", "currency")["columns"] == [("sap_acdoca", "RHCUR")]
    assert amounts.label_columns(p, "sap_ekbe", "DMBTR", "currency")["where"] == "missing"   # company code currency
    assert amounts.document_headers(p, "sap_vbrp") == ["sap_vbrk"]          # not VBAP (AUBEL) and not MARA (MATNR)


def test_no_suggested_sum_mixes_currencies_or_units_on_the_sap_demo(sap):
    p, d = sap
    checked = 0
    for m in d["summary"]["measures"]:
        for t, c in _summed(m["expression"]):
            col = next(x for x in p.schema.tables[t].columns if x.name == c)
            assert not amounts.is_unit_price(c, col.data_type), m
            kind = "unit" if amounts.is_quantity_like(c, col.data_type) and "RELATED" not in m["expression"] else "currency"
            labels = amounts.label_columns(p, t, c, kind)["columns"]
            if not labels:
                continue
            g = GUARD.match(m["expression"])
            assert g, (m["name"], m["expression"])
            assert set(re.findall(r"HASONEVALUE\('([^']+)'\[([^\]]+)\]\)", g.group(1))) == set(labels), m["name"]
            checked += 1
    assert checked >= 25                                                     # the SAP demo's amounts and quantities
    by = {(m["table"], m["name"]): m for m in d["summary"]["measures"]}
    assert by[("sap_vbap", "Total NETWR")]["expression"] == "IF(HASONEVALUE('sap_vbap'[WAERK]), SUM('sap_vbap'[NETWR]))"
    assert by[("sap_vbap", "Total KWMENG")]["expression"] == "IF(HASONEVALUE('sap_vbap'[VRKME]), SUM('sap_vbap'[KWMENG]))"
    assert by[("sap_vbrp", "Total NETWR (sap_vbrp)")]["expression"] == "IF(HASONEVALUE('sap_vbrk'[WAERK]), SUM('sap_vbrp'[NETWR]))"
    assert "amounts in several currencies are not added up" in by[("sap_vbap", "Total NETWR")]["why"]
    assert "(not counted)" in by[("sap_vbap", "Total NETWR")]["why"]
    assert not any("DMBTR" in m["expression"] for m in d["summary"]["measures"])   # its currency is in no table here
    _parses_and_resolves(d)


def test_a_sign_column_is_noted_in_the_description(sap):
    _, d = sap
    m = next(x for x in d["summary"]["measures"] if x["table"] == "sap_ekbe" and "WRBTR" in x["expression"])
    assert "sign: sap_ekbe.SHKZG marks each row as debit or credit" in m["why"]
    assert "SHKZG" not in m["expression"]
    assert "/// Suggested by Krusgraph:" in d["parts"]["definition/tables/sap_ekbe.tmdl"]
    assert "sign:" not in next(x for x in d["summary"]["measures"] if x["table"] == "sap_vbap" and x["name"] == "Total NETWR")["why"]


def test_one_counted_currency_keeps_the_plain_sum_and_two_keep_the_guard():
    _, one = _draft(counts=True)
    by = {(m["table"], m["name"]): m for m in one["summary"]["measures"]}
    m = by[("sap_vbap", "Total NETWR")]
    assert m["expression"] == "SUM('sap_vbap'[NETWR])" and "counted with one value" in m["why"]

    def sek(ex):                                                             # one synthetic order line in SEK
        _update(ex, SEK)
    _, two = _draft(counts=True, rows=sek)
    by = {(m["table"], m["name"]): m for m in two["summary"]["measures"]}
    m = by[("sap_vbap", "Total NETWR")]
    assert m["expression"] == "IF(HASONEVALUE('sap_vbap'[WAERK]), SUM('sap_vbap'[NETWR]))"
    assert "counted: sap_vbap.WAERK 2 values" in m["why"]
    assert by[("sap_vbak", "Total NETWR (sap_vbak)")]["expression"] == "SUM('sap_vbak'[NETWR])"   # VBAK still one currency


def test_the_sum_the_guard_prevents_is_a_real_mix():
    """The same rows in SQL: with one line in SEK, the plain sum adds EUR and SEK; per currency they stay apart."""
    s, ex = sap_demo.sqlite()
    _update(ex, SEK)
    per = ex("SELECT WAERK, SUM(NETWR) AS s FROM sap.[sap_vbap] GROUP BY WAERK ORDER BY WAERK")
    total = ex("SELECT SUM(NETWR) AS s FROM sap.[sap_vbap]")[0]["s"]
    assert [r["WAERK"] for r in per] == ["EUR", "SEK"] and round(sum(r["s"] for r in per), 2) == round(total, 2)
    assert amounts.unit_counts(plan(s), ex)["sap_vbap.WAERK"] == 2
    assert "COUNT_BIG(DISTINCT [WAERK]) AS u0" in amounts.unit_counts_sql("sap", "sap_vbap", ["WAERK", "VRKME"])


def test_a_price_per_unit_is_never_summed():
    s = Schema(schema="x")
    s.tables["orders"] = Table("orders", [Column("order_id", "int"), Column("order_date", "date")], schema="x")
    s.tables["order_items"] = Table("order_items", [Column(c, t) for c, t in (
        ("order_id", "int"), ("line_no", "int"), ("product_id", "int"), ("quantity", "int"), ("unit_price", "decimal(10,2)"),
        ("NETPR", "decimal(10,2)"), ("KBETR", "decimal(10,2)"), ("line_amount", "decimal(10,2)"))], schema="x")
    s.tables["products"] = Table("products", [Column("product_id", "int"), Column("name", "nvarchar")], schema="x")
    p = plan(s, keys={"orders": ["order_id"], "order_items": ["order_id", "line_no"], "products": ["product_id"]})
    d = semantic_model.draft(p, {"schema": "x"})
    summed = {c for m in d["summary"]["measures"] for _, c in _summed(m["expression"])}
    assert not summed & {"unit_price", "NETPR", "KBETR"}
    assert {"quantity", "line_amount"} <= summed


def test_the_shop_has_no_currency_column_and_its_measures_do_not_change():
    p = plan(seed.schema())
    d = semantic_model.draft(p, {"schema": "shop"})
    assert d["summary"]["measures"] and not any("HASONEVALUE" in m["expression"] for m in d["summary"]["measures"])
    assert not any(amounts.is_currency_column(c.name, c.data_type) or amounts.is_unit_column(c.name, c.data_type)
                   for t in p.schema for c in t.columns)


def test_respect_units_drops_what_cannot_be_kept_apart_and_says_why(sap):
    p, _ = sap
    chosen = list(p.schema)
    ms = [{"table": "sap_ekbe", "column": "DMBTR", "name": "x", "expression": "SUM('sap_ekbe'[DMBTR])", "why": "w"},
          {"table": "sap_ekbe", "column": "WRBTR", "name": "y", "expression": "SUM('sap_ekbe'[WRBTR])", "why": "w"},
          {"table": "sap_ekbe", "column": None, "name": "z", "expression": "COUNTROWS('sap_ekbe')", "why": "w"}]
    dropped = level_measures.respect_units(p, chosen, ms, None)
    assert [m["name"] for m in dropped] == ["x"] and dropped[0]["not_summed"].startswith("amounts in several currencies")
    assert ms[1]["expression"].startswith("IF(HASONEVALUE('sap_ekbe'[WAERS])") and ms[2]["expression"] == "COUNTROWS('sap_ekbe')"
    again = level_measures.respect_units(p, chosen, ms[1:], None)            # applied once: no double guard
    assert again == [] and ms[1]["expression"].count("HASONEVALUE") == 1
    # the model without the header: the currency is not in the model, so no sum is suggested
    lines_only = [t for t in chosen if t.name != "sap_vbrk"]
    m = {"table": "sap_vbrp", "column": "NETWR", "name": "n", "expression": "SUM('sap_vbrp'[NETWR])", "why": "w"}
    assert level_measures.respect_units(p, lines_only, [m], None) == [m] and "sap_vbrk.WAERK is not in the model" in m["not_summed"]
