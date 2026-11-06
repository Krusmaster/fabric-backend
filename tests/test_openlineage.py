"""n125: lineage(format="openlineage") — the graph as OpenLineage RunEvents, validated against the published JSON schema.

The schema files in tests/fixtures/openlineage/ are vendored unmodified from github.com/OpenLineage/OpenLineage at commit
6e9fd64478313b77884dd578cae94a1d9d32bc9a (Apache-2.0, LICENSE-OpenLineage.txt next to them)."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

import test_golden
from fabric_backend import lineage, openlineage, seed
from test_golden import SRC, fabric  # noqa: F401  (the hosted server against the shop workspace)

HERE = Path(__file__).parent / "fixtures" / "openlineage"
FACET = Path(__file__).parent.parent / "fabric_backend" / "openlineage_krusgraph_facet.json"
WS = "11111111-2222-3333-4444-555555555555"


def _registry() -> Registry:
    docs = [json.loads(p.read_text()) for p in sorted(HERE.glob("*.json"))] + [json.loads(FACET.read_text())]
    return Registry().with_resources((d["$id"], Resource.from_contents(d)) for d in docs)


def _validator(url: str) -> Draft202012Validator:
    reg = _registry()
    base, _, pointer = url.partition("#")
    schema = {"$ref": url} if pointer else reg.contents(base)
    return Draft202012Validator(schema, registry=reg, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _check(ev: dict) -> None:
    _validator(openlineage.SPEC).validate(ev)
    _validator(ev["schemaURL"]).validate(ev)
    facets = [*ev["job"]["facets"].values(), *(f for d in ev["inputs"] + ev["outputs"] for f in d["facets"].values())]
    for f in facets:
        _validator(f["_schemaURL"]).validate(f)


def _events(fabric):
    from fabric_backend import server
    return json.loads(server.lineage(**SRC, format="openlineage"))


def test_shop_events_validate_against_the_published_schema(fabric):
    out = _events(fabric)
    assert out["format"] == "openlineage" and out["events"]
    for ev in out["events"]:
        _check(ev)
    jobs = {e["job"]["name"] for e in out["events"]}
    assert {"graphql_api.shop_api", "semantic_model.shop_model"} <= jobs


def test_a_bad_event_fails_the_schema():
    with pytest.raises(Exception):
        _validator(openlineage.SPEC).validate({"eventType": "DONE", "producer": "x"})
    with pytest.raises(Exception):
        _validator(openlineage.SCHEMA_FACET).validate({"fields": [{"name": "a"}]})      # no _producer / _schemaURL


def test_naming_follows_the_sql_server_form():
    assert openlineage.dataset_namespace("abc.datawarehouse.fabric.microsoft.com") == "sqlserver://abc.datawarehouse.fabric.microsoft.com:1433"
    assert openlineage.dataset_namespace("tcp:abc.x.com,1433") == "sqlserver://abc.x.com:1433"
    s = seed.schema("shop")
    g = lineage.graph({"displayName": "shop_lh", "id": "lh"}, "shop", [t.name for t in s],
                      [lineage.edge("orders", "view", "krusgraph.vw_orders", "v1", "VIEW_TABLE_USAGE"),
                       lineage.edge("orders", "graphql_api", "shop_api", "api-1", "type orders")])
    evs = openlineage.events(g, s, WS, {"sql_host": "h.fabric.microsoft.com", "sql_db": "shop_lh"}, event_time="2026-11-06T00:00:00Z",
                             created_ids={"api-1"})
    by = {e["job"]["name"]: e for e in evs}
    assert by["view.krusgraph.vw_orders"]["outputs"][0]["name"] == "shop_lh.krusgraph.vw_orders"
    assert by["graphql_api.shop_api"]["inputs"][0] == {**by["graphql_api.shop_api"]["inputs"][0],
                                                       "namespace": "sqlserver://h.fabric.microsoft.com:1433", "name": "shop_lh.shop.orders"}
    assert by["graphql_api.shop_api"]["job"]["namespace"] == f"fabric://{WS}"
    assert by["graphql_api.shop_api"]["job"]["facets"]["krusgraph"]["created_by_krusgraph"] is True
    assert by["view.krusgraph.vw_orders"]["job"]["facets"]["krusgraph"]["created_by_krusgraph"] is False
    assert by["graphql_api.shop_api"]["outputs"] == []
    for ev in evs:
        _check(ev)


def test_output_is_deterministic(fabric):
    a, b = _events(fabric)["events"], _events(fabric)["events"]
    strip = lambda evs: [{k: v for k, v in e.items() if k != "eventTime"} for e in evs]          # noqa: E731
    assert json.dumps(strip(a), sort_keys=True) == json.dumps(strip(b), sort_keys=True)
    s = seed.schema("shop")
    g = lineage.graph({"displayName": "shop_lh"}, "shop", [t.name for t in s], [lineage.edge("orders", "view", "dbo.v", "v1", "x")])
    args = (g, s, WS, {"sql_host": "h", "sql_db": "d"})
    assert openlineage.events(*args, event_time="t") == openlineage.events(*args, event_time="t")


def test_relationship_rules_and_counts_and_no_row_values(fabric):
    out = _events(fabric)
    rels = [r for e in out["events"] for r in e["job"]["facets"]["krusgraph"]["relationships"]]
    assert rels and all(r["rule"] and isinstance(r["rows_with_value"], int) and isinstance(r["orphans"], int) for r in rels)
    # no row value: every value seeded into the shop tables is absent from the answer
    text = json.dumps(out)
    seeded = {str(v) for rows in seed.rows().values() for row in rows for v in row
              if isinstance(v, str) and len(str(v)) > 3}
    leaked = sorted(v for v in seeded if json.dumps(v)[1:-1] in text and v not in _names(out))
    assert leaked == []
    for ev in out["events"]:
        for d in ev["inputs"]:
            assert all(set(f) <= {"name", "type", "ordinal_position"} for f in d["facets"]["schema"]["fields"])


def _names(out) -> set[str]:
    """Identifiers that may legitimately equal a seeded string (table, column, item names)."""
    s = seed.schema("shop")
    return {t.name for t in s} | {c.name for t in s for c in t.columns} | {c.data_type for t in s for c in t.columns}


def test_graph_stays_the_default(fabric):
    from fabric_backend import server
    assert "nodes" in json.loads(server.lineage(**SRC))
    assert test_golden.SRC == SRC
