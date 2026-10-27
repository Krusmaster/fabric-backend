"""compare_semantic_model: the TMDL reader, the comparison on a model fixture over the shop schema (one relationship
missing, one wrong), and the tool with Fabric mocked."""
import json
from pathlib import Path

import pytest
import requests

from fabric_backend import model_compare, seed, semantic_model, server
from fabric_backend.infer import plan
from fabric_backend.schema import Schema

FIXTURE = Path(__file__).parent / "fixtures" / "semantic_model_shop"
WS = "11111111-1111-1111-1111-111111111111"
INFO = dict(workspace_id="ws", item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse", schema="shop",
            sql_endpoint="x.datawarehouse.fabric.microsoft.com", sql_db="shop_lh")


def fixture_parts() -> dict[str, str]:
    return {str(p.relative_to(FIXTURE)).replace("\\", "/"): p.read_text(encoding="utf-8") for p in FIXTURE.rglob("*.tmdl")}


def shop_plan(confirmed=None):
    return plan(seed.schema("shop"), None, confirmed)


# ------------------------------------------------------------------ reading TMDL --------------------------------------

def test_tmdl_reader_takes_tables_sources_columns_measures_and_relationships():
    m = model_compare.from_tmdl(fixture_parts())
    assert set(m["tables"]) == {"Customer", "Order Lines", "addresses", "categories", "orders", "products"}
    assert m["tables"]["Customer"]["source"] == "customers" and m["tables"]["Order Lines"]["source"] == "order_items"
    assert m["tables"]["orders"]["columns"]["ship_to_id"]["summarize_by"] == "sum" and m["tables"]["orders"]["columns"]["order_id"]["is_key"]
    assert m["tables"]["orders"]["measures"]["Total order id"]["expression"] == "SUM(orders[order_id])"
    rels = {(r["from_table"], r["from_column"], r["to_table"], r["to_column"]) for r in m["relationships"]}
    assert ("Order Lines", "order_id", "orders", "order_id") in rels and len(rels) == 5
    assert all(r["active"] and r["cross_filter"] == "oneDirection" and (r["from_cardinality"], r["to_cardinality"]) == ("many", "one")
               for r in m["relationships"])


def test_tmdl_reader_reads_quoted_names_flags_and_multi_line_measures():
    parts = {"definition/relationships.tmdl": "relationship r1\n\tisActive: false\n\tcrossFilteringBehavior: bothDirections\n"
                                              "\tfromCardinality: one\n\tfromColumn: Sales.'Order Date'\n\ttoColumn: 'My Calendar'.Date\n",
             "definition/tables/Sales.tmdl": "table Sales\n\tmeasure 'Margin' = ```\n\t\t\tSUMX ( Sales,\n\t\t\t    Sales[Qty] )\n\t\t\t```\n"
                                             "\t\tformatString: 0\n\t\tkpi\n\t\t\ttargetExpression = 1\n\n\tcolumn 'Order Date'\n\t\tdataType: dateTime\n"
                                             "\t\tsourceColumn: order_date\n\n\t\tannotation SummarizationSetBy = Automatic\n"}
    m = model_compare.from_tmdl(parts)
    r = m["relationships"][0]
    assert (r["from_table"], r["from_column"], r["to_table"], r["to_column"]) == ("Sales", "Order Date", "My Calendar", "Date")
    assert r["active"] is False and r["cross_filter"] == "bothDirections" and r["from_cardinality"] == "one"
    assert m["tables"]["Sales"]["measures"]["Margin"]["expression"] == "SUMX ( Sales, Sales[Qty] )"
    assert m["tables"]["Sales"]["columns"]["Order Date"]["source_column"] == "order_date"
    assert model_compare.split_column_ref("'A''s'.'b c'") == ("A's", "b c")


def test_tmdl_reader_reads_what_semantic_model_draft_writes():
    parts = semantic_model.draft(shop_plan(), INFO, "m")["parts"]
    m = model_compare.from_tmdl(parts)
    out = model_compare.compare(shop_plan(), m)
    # a model drafted from the plan agrees with the plan: nothing missing, nothing contradicted
    assert out["missing_in_model"] == [] and out["contradicted"] == [] and out["active_differences"] == []
    assert len(out["agrees"]) == 6 and out["measures"]["suggested_missing"] == [] and out["summarization"] == []
    assert out["tables"]["model_only"] == ["Calendar"] and out["outside_the_plan"][0]["to"] == "Calendar.Date"


# ------------------------------------------------------------------ the comparison ------------------------------------

def test_fixture_one_missing_and_one_wrong_relationship_with_the_rule_behind_each():
    out = model_compare.compare(shop_plan(), model_compare.from_tmdl(fixture_parts()))
    assert [m["plan"] for m in out["missing_in_model"]] == ["products.category_id -> categories.id"]
    assert out["missing_in_model"][0]["rule"].startswith("R1") and out["missing_in_model"][0]["add"] == \
        "fromColumn: products.category_id; toColumn: categories.id"
    wrong = out["contradicted"]
    assert len(wrong) == 1 and wrong[0]["from"] == "products.category_id" and wrong[0]["to"] == "Customer.customer_id"
    assert wrong[0]["by"] == "rule" and "the plan links products.category_id to categories.id (R1" in wrong[0]["why"]
    assert len(out["agrees"]) == 4 and out["not_in_plan"] == [] and out["cardinality_differences"] == []
    assert out["tables"]["mapped"]["Customer"] == "customers" and out["tables"]["mapped"]["Order Lines"] == "order_items"
    assert out["tables"]["not_in_model"] == ["audit_log"]
    # ship_to_id summed and a measure over an id: both against the summarizeBy rule
    assert out["summarization"] == [{"column": "orders.ship_to_id", "model": "summarizeBy: sum", "plan": "summarizeBy: none",
                                     "why": "its name ends in an id, code, number or year word"}]
    assert [q["measure"] for q in out["measures"]["questionable"]] == ["orders[Total order id]"]
    # '# Lines' counts the order lines already; the missing suggestions come in the model's own names
    missing = {m["expression"] for m in out["measures"]["suggested_missing"]}
    assert missing == {"COUNTROWS('orders')", "SUM('Order Lines'[quantity])"}
    assert "1 missing in the model, 1 contradicted" in out["summary"]


def test_cardinality_direction_and_active_differences():
    parts = fixture_parts()
    parts["definition/relationships.tmdl"] = parts["definition/relationships.tmdl"].replace(
        "\tfromColumn: orders.customer_id\n", "\tcrossFilteringBehavior: bothDirections\n\tisActive: false\n\tfromColumn: orders.customer_id\n").replace(
        "\tfromColumn: addresses.customer_id\n", "\tfromCardinality: one\n\ttoCardinality: one\n\tfromColumn: addresses.customer_id\n")
    out = model_compare.compare(shop_plan(), model_compare.from_tmdl(parts))
    assert [d["from"] for d in out["direction_differences"]] == ["orders.customer_id"]
    assert out["active_differences"][0]["from"] == "orders.customer_id" and out["active_differences"][0]["plan_active"] is True
    card = out["cardinality_differences"]
    assert [c["from"] for c in card] == ["addresses.customer_id"] and "one-to-one" in card[0]["why"] and "rule K2" in card[0]["why"]


def test_a_link_the_plan_lacks_is_offered_as_confirmed_and_the_data_can_contradict_it():
    parts = fixture_parts()
    parts["definition/relationships.tmdl"] += ("\nrelationship extra\n\tfromColumn: orders.ship_to_id\n\ttoColumn: addresses.address_id\n")
    out = model_compare.compare(shop_plan(), model_compare.from_tmdl(parts))
    extra = next(x for x in out["not_in_plan"] if x["from"] == "orders.ship_to_id")
    assert extra["confirmed"] == {"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}
    assert ("orders", "ship_to_id", "addresses", "address_id") in model_compare.to_check(out)
    data = {"orders.ship_to_id -> addresses.address_id": {"one_side": {"verdict": "unique in all 15 rows"},
                                                          "orphans": {"orphans": 3, "verdict": "3 of 60 rows (5.0%) point at nothing"}}}
    out = model_compare.compare(shop_plan(), model_compare.from_tmdl(parts), data_checks=data)
    bad = next(x for x in out["contradicted"] if x["from"] == "orders.ship_to_id")
    assert bad["by"] == "data" and "3 of 60 rows" in bad["why"]
    # confirmed, the same link agrees
    out = model_compare.compare(shop_plan([extra["confirmed"]]), model_compare.from_tmdl(parts))
    assert "orders.ship_to_id -> addresses.address_id (confirmed)" in out["agrees"]


def test_a_column_name_ending_in_a_bracket_is_matched_as_it_is():
    from fabric_backend.schema import Schema as S
    s = S.from_information_schema([("dbo", "sales", "sale_id", "int", 1), ("dbo", "sales", "customer_id", "int", 2), ("dbo", "sales", "store_id", "int", 3),
                                   ("dbo", "sales", "Amount (EUR)", "decimal", 4), ("dbo", "customers", "customer_id", "int", 1), ("dbo", "stores", "store_id", "int", 1)])
    p = plan(s)
    parts = semantic_model.draft(p, dict(INFO, schema="dbo"), "m")["parts"]
    out = model_compare.compare(p, model_compare.from_tmdl(parts))
    assert out["measures"]["suggested_missing"] == []                       # SUM('sales'[Amount (EUR)]) is found, not re-suggested


def test_microsofts_sample_model_reads_without_errors():
    """The PBIP sample in microsoft/Analysis-Services (pbidevmode/fabricps-pbip/SamplePBIP) as recorded excerpts: an Import
    model with Power Query partitions, a calendar, inactive date relationships and fenced multi-line measures."""
    parts = {"definition/relationships.tmdl": "relationship d4e6dc5a\n\tfromColumn: Sales.CustomerKey\n\ttoColumn: Customer.CustomerKey\n\n"
                                              "relationship 21bd108e\n\tisActive: false\n\tfromColumn: Sales.'Delivery Date'\n\ttoColumn: Calendar.Date\n",
             "definition/tables/Sales.tmdl": "table Sales\n\tlineageTag: x\n\n\tmeasure Margin = ```\n\t\t\tSUMX ( \n\t\t\t    Sales, \n\t\t\t    Sales[Quantity] \n"
                                             "\t\t\t        * ( Sales[Net Price] - Sales[Unit Cost] )\n\t\t\t)\n\t\t\t```\n\t\tformatString: $ #,##0\n\n"
                                             "\tcolumn CustomerKey\n\t\tdataType: int64\n\t\tsummarizeBy: none\n\t\tsourceColumn: CustomerKey\n\n"
                                             "\tpartition Sales = m\n\t\tmode: import\n\t\tsource =\n\t\t\t\tlet\n\t\t\t\t    Source = Sql.Database(\"x\", \"y\"),\n"
                                             "\t\t\t\t    t = Source{[Schema=\"dbo\",Item=\"FactSales\"]}[Data]\n\t\t\t\tin\n\t\t\t\t    t\n"}
    m = model_compare.from_tmdl(parts)
    assert m["tables"]["Sales"]["source"] == "FactSales" and m["tables"]["Sales"]["source_schema"] == "dbo"
    assert m["tables"]["Sales"]["measures"]["Margin"]["expression"].startswith("SUMX ( Sales, Sales[Quantity]")
    assert [r["active"] for r in m["relationships"]] == [True, False]


# ------------------------------------------------------------------ the tool ------------------------------------------

class Resp:
    def __init__(self, status, body=None):
        self.status_code, self._body, self.text = status, body, json.dumps(body or {})

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


@pytest.fixture
def shop(monkeypatch):
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": "Lakehouse", "id": "lh-1", "displayName": src,
                                                                             "sql_host": "x", "sql_db": src, "schemas_enabled": True})
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: []))
    monkeypatch.setattr(server, "find_item_by_name", lambda ws, name, headers, types=(): {"id": "sm-1", "displayName": name, "type": "SemanticModel"}
                        if name == "Shop model" else None)
    return monkeypatch


def test_tool_reads_the_definition_and_compares(shop):
    shop.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: []))
    asked = []
    shop.setattr(server, "_item_definition_parts", lambda ws, route, item_id, headers, fmt=None: asked.append((route, item_id, fmt)) or fixture_parts())
    shop.setattr(requests, "post", lambda *a, **k: pytest.fail("nothing is posted besides getDefinition"))
    out = json.loads(server.compare_semantic_model("Sales", "shop_lh", "Shop model", schema="shop"))
    assert asked == [("semanticModels", "sm-1", "TMDL")]
    assert out["model"]["read_with"] == "Fabric getDefinition (TMDL)" and out["model"]["delegated_scope"].startswith("SemanticModel.ReadWrite.All")
    assert "INFO functions" in out["model"]["spec"] and len(out["missing_in_model"]) == 1 and len(out["contradicted"]) == 1
    from fabric_backend import tool_status
    assert tool_status.answer_note("compare_semantic_model") in out["note"] and "only as far as the model lookup" in out["note"]


def test_tool_403_is_consent_with_the_scope_and_the_tmdl_way_round(shop):
    def refuse(ws, route, item_id, headers, fmt=None):
        Resp(403, {"errorCode": "InsufficientScopes"}).raise_for_status()
    shop.setattr(server, "_item_definition_parts", refuse)
    out = json.loads(server.compare_semantic_model("Sales", "shop_lh", "Shop model", schema="shop"))
    assert out["kind"] == "consent" and out["scope"] == "SemanticModel.ReadWrite.All (or Item.ReadWrite.All)" and "`tmdl`" in out["hint"]
    assert "test-only" not in json.dumps(out)


def test_tool_takes_tmdl_without_any_call_to_the_model_and_names_a_missing_model(shop):
    shop.setattr(server, "_item_definition_parts", lambda *a, **k: pytest.fail("tmdl given: the model is not read"))
    out = json.loads(server.compare_semantic_model("Sales", "shop_lh", tmdl=fixture_parts(), schema="shop"))
    assert out["model"]["read_with"].startswith("TMDL files given") and len(out["agrees"]) == 4
    assert json.loads(server.compare_semantic_model("Sales", "shop_lh", "Ghost", schema="shop"))["kind"] == "not_found"
    assert json.loads(server.compare_semantic_model("Sales", "shop_lh", schema="shop"))["kind"] == "bad_input"


def test_tool_with_check_data_counts_the_models_extra_link(shop):
    parts = fixture_parts()
    parts["definition/relationships.tmdl"] += "\nrelationship extra\n\tfromColumn: orders.ship_to_id\n\ttoColumn: Customer.customer_id\n"
    ran = []

    def execute(sql):
        ran.append(sql)
        if "COUNT_BIG(*) AS with_value" in sql and "[ship_to_id]" in sql:
            return [{"with_value": 60, "orphans": 25}]
        if "COUNT_BIG(*) AS with_value" in sql:
            return [{"with_value": 10, "orphans": 0}]
        return [{"n": 10, "nulls": 0, "distinct_keys": 10}]
    shop.setattr(server, "_execute_factory", lambda item, tok: execute)
    shop.setattr(server, "_item_definition_parts", lambda *a, **k: parts)
    out = json.loads(server.compare_semantic_model("Sales", "shop_lh", "Shop model", schema="shop", check_data=True))
    bad = next(x for x in out["contradicted"] if x["from"] == "orders.ship_to_id")
    assert bad["by"] == "data" and "25 of 60 rows" in bad["why"] and out["validate_plan"].startswith("6 of 6 keys unique")
    assert any("[ship_to_id]" in s for s in ran)
