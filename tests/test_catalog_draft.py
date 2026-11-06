"""n116: the OneLake catalog draft. export_item_definitions(items=["catalog"]) lists, per Fabric item the plan touches,
the description and the tags it would set and the exact REST calls (Items - Update Item, Tags - Apply Tags), from the
plan only. No tool sends them; the answer is the same for the same plan; only documented endpoints appear; item types
without a documented update operation get nothing; no row value and no masked column is ever named."""
import json
import re

import pytest

from fabric_backend import catalog, privacy, seed, server
from fabric_backend.infer import plan
from tests.test_golden import SRC, fabric  # noqa: F401  (the fixture: the hosted server against the in-memory workspace)

# The only calls a draft may name: the documented operations of fabric-rest-api-specs 6f817cb.
DOCUMENTED = {
    "Items_UpdateItem": ("PATCH", re.compile(r"^https://api\.fabric\.microsoft\.com/v1/workspaces/[^/]+/items/[^/]+$")),
    "Tags_ApplyTags": ("POST", re.compile(r"^https://api\.fabric\.microsoft\.com/v1/workspaces/[^/]+/items/[^/]+/applyTags$")),
    "Tags_ListTags": ("GET", re.compile(r"^https://api\.fabric\.microsoft\.com/v1/tags$")),
    "Tags_BulkCreateTags": ("POST", re.compile(r"^https://api\.fabric\.microsoft\.com/v1/admin/tags/bulkCreateTags$")),
}


def _catalog(**kw) -> dict:
    return json.loads(server.export_item_definitions(**SRC, items=["catalog"], **kw))


def _calls(cat: dict) -> list[dict]:
    return [c for i in cat["items"] for c in i["calls"]] + cat["tag_setup"]["calls"]


def test_one_entry_per_item_with_a_description_tags_and_the_two_calls(fabric):
    out = _catalog(check_rows=True)
    cat = out["catalog"]
    assert "files" not in out                       # catalog alone: the draft, not the definition files
    got = [(i["item"], i["type"]) for i in cat["items"]]
    assert got == [("demo_lh", "Lakehouse"), ("demo_lh_api", "GraphQLApi"), ("demo_lh_model", "SemanticModel"),
                   ("silver_shop", "Notebook"), ("drift_monitor_shop", "Notebook"), ("drift_monitor_shop_nightly", "DataPipeline"),
                   ("gold_shop", "Notebook")]
    src = cat["items"][0]
    assert src["exists"] and src["calls"][0]["url"].endswith("/items/aaaaaaaa-0000-0000-0000-000000000001")
    assert all(not i["exists"] and "<id of " + i["item"] + " once created>" in i["calls"][0]["url"] for i in cat["items"][1:])
    for i in cat["items"]:
        assert [c["operation"] for c in i["calls"]] == ["Items_UpdateItem", "Tags_ApplyTags"]
        assert i["calls"][0]["body"] == {"description": i["description"]}
        assert i["calls"][1]["body"] == {"tags": [f"<id of tag {t!r} from GET /v1/tags>" for t in i["tags"]]}
        assert 0 < len(i["description"]) == i["description_chars"] <= catalog.DESCRIPTION_MAX
        assert i["tags"] == ["Krusgraph", "domain: customers", "domain: products"]
    assert "counted: 6 of 6 keys unique, 7 of 7 relationships without orphans" in src["description"]
    assert "proposed domains: customers, products" in src["description"]
    api = cat["items"][1]["description"]
    assert "Customers" in api and "OrderItems" in api          # the ontology's entity names
    assert {r["rule"] for r in cat["facts"]["relationships"]} == {"R1", "R5"}
    assert all("counted" in r for r in cat["facts"]["relationships"])


def test_the_same_plan_gives_the_same_answer(fabric):
    assert server.export_item_definitions(**SRC, items=["catalog"], check_rows=True) == \
        server.export_item_definitions(**SRC, items=["catalog"], check_rows=True)
    assert server.export_item_definitions(**SRC, items=["catalog"]) == server.export_item_definitions(**SRC, items=["catalog"])


def test_only_documented_endpoints_and_nothing_is_sent(fabric):
    before = len(fabric.calls)
    cat = _catalog(check_rows=True)["catalog"]
    for c in _calls(cat):
        method, url = DOCUMENTED[c["operation"]]
        assert c["method"] == method and url.match(c["url"]), c
    for a in cat["apis"]:
        assert a["operation"] in set(DOCUMENTED) | {"Catalog_Search"}
    sent = fabric.calls[before:]
    assert not fabric.created
    assert sent and not [(m, path) for m, path in sent if m != "GET" or "applyTags" in path or path.startswith("/v1/tags")], sent


def test_without_check_rows_nothing_is_counted_and_the_text_says_so(fabric):
    queries = len(fabric.odbc.ddl)
    cat = _catalog()["catalog"]
    assert len(fabric.odbc.ddl) == queries
    assert not cat["facts"]["counted"]
    assert all("not counted against the rows" in i["description"] for i in cat["items"][:3])
    assert not any("counted" in r for r in cat["facts"]["relationships"])


def test_with_other_items_the_catalog_covers_exactly_those_and_keeps_the_files(fabric):
    out = json.loads(server.export_item_definitions(**SRC, items=["create_backend", "create_views", "catalog"]))
    assert "demo_lh_api.GraphQLApi/.platform" in out["files"]
    assert [i["type"] for i in out["catalog"]["items"]] == ["Lakehouse", "GraphQLApi"]   # the views are not an item
    assert "OneLake catalog draft" in out["summary"]
    assert any(n["what"].startswith("the T-SQL views") for n in out["catalog"]["not_set"])


def test_check_rows_without_the_catalog_counts_nothing(fabric):
    queries = len(fabric.odbc.ddl)
    out = json.loads(server.export_item_definitions(**SRC, items=["create_backend"], check_rows=True))
    assert "catalog" not in out and len(fabric.odbc.ddl) == queries
    assert any("check_rows counts rows for items" in n for n in out["notes"])


def test_tables_narrow_the_facts_and_the_tags(fabric):
    cat = _catalog(tables=["categories", "products"])["catalog"]
    assert [t["table"] for t in cat["facts"]["tables"]] == ["categories", "products"]
    assert cat["items"][0]["tags"] == ["Krusgraph", "domain: products"]


# ------------------------------------------------------------------ the module on its own --------------------------

def _info(kind: str = "Lakehouse") -> dict:
    return {"workspace_id": "ws", "item_id": "item-1", "item_name": "shop_lh", "item_kind": kind, "schema": "shop"}


NAMES = {"create_silver_notebook": "silver_shop", "create_gold_views": "gold_shop", "create_drift_monitor": "drift_shop",
         "pipeline": "pipeline_shop"}


@pytest.mark.parametrize("kind", ["SQLEndpoint", "Report", "KQLDatabase"])
def test_item_types_without_an_update_operation_get_nothing(kind):
    p = plan(seed.schema("shop"))
    out = catalog.draft(p, _info(kind), [{"tool": "create_views", "type": "T-SQL", "name": "krusgraph-sql"},
                                         {"tool": "create_backend", "type": "GraphQLApi", "name": "shop_api"}],
                        NAMES, {"silver": "silver", "gold": "gold"})
    assert [i["item"] for i in out["items"]] == ["shop_api"]
    assert out["skipped"] == [{"item": "shop_lh", "type": kind, "why": f"the specs have no update operation for {kind}"}]
    assert all(i["type"] in catalog.UPDATABLE for i in out["items"])


def test_every_source_kind_the_tools_read_has_an_update_operation():
    """The sources list_sources offers (lakehouse, warehouse, SQL database, mirrored and Snowflake items) all have one."""
    for kind in ("Lakehouse", "Warehouse", "SQLDatabase", "MirroredDatabase", "SnowflakeDatabase",
                 "MirroredAzureDatabricksCatalog", "MirroredCatalog"):
        out = catalog.draft(plan(seed.schema("shop")), _info(kind), [], NAMES, {"silver": "silver", "gold": "gold"})
        assert [i["type"] for i in out["items"]] == [kind] and "skipped" not in out


def _values() -> set[str]:
    """The seed's text values (names, cities, e-mail addresses, product names); numbers are left out because the counts
    the draft carries are numbers too."""
    return {v for rows in seed.rows().values() for r in rows for v in r if isinstance(v, str) and len(v) >= 3}


def test_no_row_values_and_no_masked_column_is_named(fabric):
    text = json.dumps(_catalog(check_rows=True)["catalog"], ensure_ascii=False)
    found = sorted(v for v in _values() if re.search(r"(?<![\w-])" + re.escape(v) + r"(?![\w-])", text))
    assert not found, found
    flagged = privacy.personal_columns(plan(seed.schema("shop")).schema)
    assert flagged                                  # the shop has masked columns (customers.name, addresses.city)
    descriptions = " ".join(i["description"] for i in _catalog(check_rows=True)["catalog"]["items"]).lower()
    for _, column in flagged:
        assert not re.search(rf"\b{re.escape(column.lower())}\b", descriptions), column
    p = plan(seed.schema("shop"))
    columns = {c.lower() for t in p.schema for c in t.column_names}
    assert not columns & set(re.findall(r"[a-z_]+", descriptions)) - {t.name for t in p.schema}, \
        "a description names a column"


def test_long_plans_fit_the_256_characters_and_the_tag_limits():
    p = plan(seed.schema("shop"))
    long = {**_info(), "item_name": "a_lakehouse_with_a_rather_long_name_for_this", "schema": "s" * 60}
    out = catalog.draft(p, long, [{"tool": "create_semantic_model", "type": "SemanticModel", "name": "m"}], NAMES,
                        {"silver": "silver", "gold": "gold"})
    assert all(len(i["description"]) <= catalog.DESCRIPTION_MAX for i in out["items"])
    many = {"tables": [], "relationships": [], "counted": False,
            "domains": [{"name": f"domain number {n} with a name far longer than forty", "tables": []} for n in range(12)]}
    kept, left = catalog.tag_names(many)
    assert len(kept) == catalog.TAGS_PER_ITEM and len(left) == 3
    assert all(len(t) <= catalog.TAG_MAX for t in kept + left)
