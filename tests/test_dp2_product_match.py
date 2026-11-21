"""Round DP2: catalog data products suggested for tables no pack knows, and the coverage answer per process.

The matcher (fabric_backend/data_product_match.py) is rules only, so each schema's answer is a golden file
(tests/golden/dp2_*.json). Regenerate them with KRUSGRAPH_UPDATE_GOLDEN=1 after a deliberate change and read the diff.

Schemas: the three pack demos (SAP, Salesforce, Dynamics 365) with their rows counted, an invented ERP with German
names (tests/fixtures/dp2/unknown_erp_de.json, rows counted), the WideWorldImporters and nordic_sv benchmark schemas
(names only), and a negative case of tables whose names mean nothing (tests/fixtures/dp2/random_tables.json).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from fabric_backend import data_product_match as m
from fabric_backend import dynamics_demo, evidence, requirements_draft as rq, salesforce_demo, sap_demo, start_flow
from fabric_backend.infer import plan
from fabric_backend.schema import Schema

GOLDEN = Path(__file__).parent / "golden"
SCHEMAS = Path(__file__).parent / "fixtures" / "schemas"
FIXTURES = Path(__file__).parent / "fixtures" / "dp2"


def _golden(name: str, value) -> None:
    path = GOLDEN / f"dp2_{name}.json"
    text = json.dumps(value, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    if os.environ.get("KRUSGRAPH_UPDATE_GOLDEN") == "1":
        path.write_text(text, encoding="utf-8")
    assert path.exists(), f"no golden file {path.name}: run with KRUSGRAPH_UPDATE_GOLDEN=1 once"
    assert path.read_text(encoding="utf-8") == text, f"{path.name} differs; regenerate with KRUSGRAPH_UPDATE_GOLDEN=1 and read the diff"


def dp2_sqlite(name: str, schema: str = "dbo"):
    """(Schema, execute) over a fixture's rows in an in-memory SQLite database, the way the demos load."""
    import sqlite3

    from fabric_backend.dialects import sqlite_sql
    fx = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    con = sqlite3.connect(":memory:")
    con.execute(f"ATTACH DATABASE ':memory:' AS {schema}")
    info = []
    for t, d in fx["tables"].items():
        cols = d["columns"]
        con.execute(f"CREATE TABLE {schema}.[{t}] ({', '.join(f'[{c}]' for c in cols)})")
        con.executemany(f"INSERT INTO {schema}.[{t}] VALUES ({','.join('?' * len(cols))})", [tuple(r) for r in d["rows"]])
        kinds = ["decimal" if all(isinstance(r[i], (int, float)) for r in d["rows"]) else "nvarchar" for i in range(len(cols))]
        info += [(schema, t, c, k, i) for i, (c, k) in enumerate(zip(cols, kinds), 1)]

    def execute(sql: str):
        cur = con.execute(sqlite_sql(sql))
        names = [x[0] for x in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]
    return Schema.from_information_schema(info, schema=schema), execute


def _counted(schema_execute):
    s, execute = schema_execute
    p = plan(s)
    v = evidence.validate(p, execute, max_items=200)
    return p, v, execute


def _names_only(name: str) -> Schema:
    fx = json.loads((SCHEMAS / f"{name}.json").read_text(encoding="utf-8"))
    rows = [("dbo", t["name"], c, ty, i) for t in fx["tables"] for i, (c, ty) in enumerate(t["columns"], 1)]
    return Schema.from_information_schema(rows, schema="dbo")


@pytest.fixture(scope="module")
def unknown():
    p, v, execute = _counted(dp2_sqlite("unknown_erp_de"))
    return p, v, execute, m.suggest(p, v, execute)


@pytest.fixture(scope="module")
def sap():
    p, v, _ = _counted(sap_demo.sqlite())
    return p, m.suggest(p, v)


def _by(answer: dict, table: str) -> dict:
    return next(x for x in answer["tables"] if x["table"] == table)


# ------------------------------------------------------------------ words --------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("Auftragspositionen", ["order", "line"]), ("Kundenauftrag", ["customer", "order"]), ("AuftragsNr", ["order", "number"]),
    ("Fakturarader", ["invoice", "line"]), ("Leverantörsfakturor", ["supplier", "invoice"]), ("Inköpsorder", ["purchase", "order"]),
    ("PosNr", ["line", "number"]), ("CustomerTransactions", ["customer", "transaction"]), ("Rechnungen", ["invoice"]),
    ("Zahlungsarten", ["payment", "lookup"]), ("tmp_load_01", []),
])
def test_names_are_read_in_english_german_and_swedish(name, expected):
    assert m.concepts(name) == expected


# ------------------------------------------------------------------ an unknown ERP -----------------------------------

def test_an_unknown_erp_gets_products_with_confidence_and_evidence(unknown):
    _, _, _, a = unknown
    line = _by(a, "Auftragspositionen")
    assert (line["product"], line["role"], line["confidence"], line["source"]) == ("sales_order", "line", "high", "names")
    assert line["key"] == ["AuftragsNr", "PosNr"] and line["header"] == "Auftragskopf"
    assert [e["rule"] for e in line["evidence"]] == ["DP2-N1", "DP2-K1", "DP2-L1", "DP2-A1", "DP2-C1", "DP2-C2"]
    assert line["evidence"][-1]["counts"] == {"rows_with_value": 24, "orphans": 0}
    assert _by(a, "Kunden")["product"] == "customer" and _by(a, "Rechnungen")["role"] == "header"
    assert "Zahlungsarten" in a["unmatched"]                    # a reference list (payment kinds), not a payment
    assert a["line"] == ("Data products: Order to cash: 5 of 7 products present; delivery without its line table, and "
                         "receivables and payables missing, so a question like “Which deliveries left later than the "
                         "customer was promised?” cannot be answered.")
    _golden("unknown_erp_de", a)


def test_without_counts_nothing_is_high(unknown):
    p, _, _, _ = unknown
    a = m.suggest(p)
    assert {x["confidence"] for x in a["tables"]} <= {"medium", "low"}
    assert not any(x["checked"] for x in a["tables"])
    assert a["counted"] == {"with_rows": False, "queries": 0}


def test_counts_that_contradict_the_names_make_it_low(unknown):
    p, v, _, _ = unknown
    v = json.loads(json.dumps(v))
    for k in v["keys"]:
        if k["table"] == "Kunden":
            k.update(rows=8, nulls=0, distinct=7, verdict="not unique: 1 duplicate rows (7 distinct values in 8 rows)")
    k = _by(m.suggest(p, v), "Kunden")
    assert k["confidence"] == "low" and "not unique" in k["evidence"][-1]["what"]


def test_candidate_keys_the_plan_lacks_are_counted_within_the_limit(unknown, monkeypatch):
    p, _, execute, a = unknown
    assert 0 < a["counted"]["queries"] <= m.MAX_QUERIES
    monkeypatch.setattr(m, "MAX_QUERIES", 1)
    b = m.suggest(p, None, execute)
    assert b["counted"]["queries"] == 1 and b["counted"]["limit"] == 1


def test_no_row_value_reaches_the_answer(unknown):
    _, _, _, a = unknown
    text = json.dumps(a, ensure_ascii=False)
    for value in ("Kunde 1", "AU0001", "K001", "RE0001", "Artikel 2", "2026-0"):
        assert value not in text


def test_the_same_schema_gives_the_same_answer(unknown):
    p, v, execute, a = unknown
    assert json.dumps(m.suggest(p, v, execute), sort_keys=True) == json.dumps(a, sort_keys=True)


# ------------------------------------------------------------------ the known packs ----------------------------------

def test_the_sap_demo_coverage_answer(sap):
    _, a = sap
    assert all(x["source"] == "pack" for x in a["tables"])
    o2c = next(x for x in a["processes"] if x["process"] == "order_to_cash")
    assert o2c["present"] == ["customer", "product", "sales_order", "delivery", "invoice"]
    assert o2c["missing"] == ["open_item", "payment"]
    assert o2c["line"] == ("Order to cash: 5 of 7 products present; receivables and payables and payment missing, so a "
                           "question like “Which customers have unpaid invoices past their due date?” cannot be answered.")
    assert "Which deliveries left later than the customer was promised?" in o2c["can_answer"]
    assert {c["question"] for c in o2c["cannot_answer"]} >= {"How many days do customers take to pay?"}
    assert _by(a, "sap_vbap")["confidence"] == "high"
    _golden("sap_demo", a)


def test_the_salesforce_demo():
    p, v, _ = _counted(salesforce_demo.sqlite())
    a = m.suggest(p, v)
    l2c = next(x for x in a["processes"] if x["process"] == "lead_to_cash")
    assert l2c["missing"] == ["invoice"] and a["processes"][0]["process"] == "lead_to_cash"
    _golden("salesforce_demo", a)


def test_the_dynamics_demo():
    p, v, _ = _counted(dynamics_demo.sqlite())
    a = m.suggest(p, v)
    assert next(x for x in a["processes"] if x["process"] == "lead_to_cash")["missing"] == []
    _golden("dynamics_demo", a)


# ------------------------------------------------------------------ names only ---------------------------------------

def test_wideworldimporters_names_only():
    a = m.suggest(plan(_names_only("wideworldimporters")))
    got = {x["table"]: (x["product"], x["role"]) for x in a["tables"] if x["confidence"] != "low"}
    assert got["OrderLines"] == ("sales_order", "line") and got["InvoiceLines"] == ("invoice", "line")
    assert got["PurchaseOrders"] == ("purchase_order", "header") and got["CustomerTransactions"] == ("open_item", "line")
    assert {"DeliveryMethods", "PaymentMethods", "TransactionTypes"} <= set(a["unmatched"])
    _golden("wideworldimporters", a)


def test_nordic_swedish_names_only():
    a = m.suggest(plan(_names_only("nordic_sv")))
    assert {x["table"]: x["product"] for x in a["tables"]} == {
        "Artiklar": "product", "Fakturor": "invoice", "Kunder": "customer", "Leverantörer": "supplier",
        "Orderrader": "sales_order", "Ordrar": "sales_order"}
    _golden("nordic_sv", a)


def test_random_tables_get_no_confident_suggestion():
    s, execute = dp2_sqlite("random_tables")
    a = m.suggest(plan(s), None, execute)
    assert not [x for x in a["tables"] if x["confidence"] in ("high", "medium")]
    assert a["processes"] == []
    assert a["line"] == "Data products: no table reads as a catalog data product by the names, keys and links."
    _golden("random_tables", a)


# ------------------------------------------------------------------ where users are ---------------------------------

def test_brief_keeps_confidence_and_evidence_per_table(unknown):
    b = m.brief(unknown[3], max_tables=3)
    assert b["line"] == unknown[3]["line"] and b["tables_not_shown"] == len(unknown[3]["tables"]) - 3
    assert all(t["confidence"] in m.CONFIDENCE and t["evidence"] for t in b["tables"])


def test_the_check_step_has_one_line_and_the_rest_under_details(unknown):
    review = {"items": [], "data_products": m.brief(unknown[3])}
    out = start_flow.guide(workspace="w", source="s", schema="dbo", step="check", review=review)
    assert out["lines"][-1] == unknown[3]["line"]
    assert sum(1 for x in out["lines"] if x.startswith("Data products:")) == 1
    assert any(x.startswith("Auftragspositionen: sales order (line), high.") for x in out["found"]["data_products"])
    plain = start_flow.guide(workspace="w", source="s", schema="dbo", step="check", review={"items": []})
    assert not any(x.startswith("Data products:") for x in plain.get("lines") or [])


def test_the_sample_check_step_says_it_too():
    out = start_flow.guide(sample=True, step="check")
    assert out["lines"][-1].startswith("Data products: Order to cash: 3 of 7 products present")
    assert out["found"]["data_products"]


def test_the_start_card_draws_the_details():
    from fabric_backend import mcp_apps_start
    assert "f.data_products" in mcp_apps_start.card_html()


def test_the_server_helper_never_breaks_an_answer():
    from fabric_backend import server
    assert server._data_products(object()) is None


def test_requirements_name_the_missing_product():
    from fabric_backend import seed
    p = plan(seed.schema("shop"))
    late, value = rq.draft(p, "Late deliveries per customer\nOrder value per month", None, "shop")["requirements"]
    assert late["state"] == "missing" and late["rule"] == "RQ-X0"
    assert late["missing"][0]["field"] == "Delivery (outbound shipment) (catalog data product delivery)"
    assert late["catalog"]["state"] == "missing"
    assert value["catalog"]["state"] == "present" and value["catalog"]["tables"] == {"header": ["orders"], "line": ["order_items"]}


def test_the_words_promise_nothing(unknown, sap):
    text = json.dumps([unknown[3], sap[1]]).lower()
    for w in ("certified", "partner", "endorsed", "works with claude", "guarantee", "compliant", "faster"):
        assert w not in text
    assert "no ai" in unknown[3]["how"].lower()
