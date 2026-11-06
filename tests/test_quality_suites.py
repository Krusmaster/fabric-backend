"""Round n122: dbt_schema(quality=..., profile=...), Great Expectations and Soda drafts of the plan's checks
(fabric_backend/quality_suites.py), on the synthetic shop schema (fabric_backend/seed.py) with counts taken in SQLite."""
from __future__ import annotations

import json
import re

import pytest

from fabric_backend import evidence, quality_suites as qs, seed, server
from fabric_backend.infer import plan
from test_dbt_project import _connection, tool  # noqa: F401  (the tool fixture)

yaml = pytest.importorskip("yaml")


@pytest.fixture(scope="module")
def shop():
    p = plan(seed.schema("shop"))
    con, execute = _connection("shop", {t: (seed.SCHEMAS[t], rows) for t, rows in seed.rows().items()})
    return p, evidence.validate(p, execute), con


def _validated(shop):
    return shop[0], shop[1]


def test_every_key_and_relationship_becomes_a_check_in_both_formats(shop):
    p, validation = _validated(shop)
    files = qs.suites(p, "shop", "both", validation)
    gx = {path: json.loads(text) for path, text in files.items() if path.endswith(".json")}
    soda = yaml.safe_load(files["quality/soda/checks_shop.yml"])
    for table, (key, rule) in p.keys.items():
        if not key:
            continue
        exp = gx[f"quality/gx/{table}.json"]["expectations"]
        types = [(e["type"], e["kwargs"].get("column") or tuple(e["kwargs"].get("column_list", ()))) for e in exp]
        if len(key) == 1:
            assert ("expect_column_values_to_be_unique", key[0]) in types
            assert f"duplicate_count({key[0]}) = 0" in [next(iter(c)) for c in soda[f"checks for {table}"]]
        else:
            assert ("expect_compound_columns_to_be_unique", tuple(key)) in types
        for col in key:
            assert ("expect_column_values_to_not_be_null", col) in types
            assert f"missing_count({col}) = 0" in [next(iter(c)) for c in soda[f"checks for {table}"]]
        assert all(e["meta"]["krusgraph_rule"] for e in exp)
    for r in p.relationships:
        exp = gx[f"quality/gx/{r.source}.json"]["expectations"]
        rel = [e for e in exp if e["type"] == "unexpected_rows_expectation" and e["meta"]["references"].startswith(r.target + "(")]
        assert rel and "{batch}" in rel[0]["kwargs"]["unexpected_rows_query"]
        assert set(rel[0]["meta"]["counts"]) >= {"rows_with_value", "orphans"}
        if len(r.source_cols) == 1:
            line = f"values in ({r.source_cols[0]}) must exist in {r.target} ({r.target_cols[0]})"
            assert line in [next(iter(c)) for c in soda[f"checks for {r.source}"]]


def test_deterministic_and_without_row_values_or_secrets(shop):
    p, validation = _validated(shop)
    a, b = qs.suites(p, "shop", "both", validation), qs.suites(p, "shop", "both", validation)
    assert a == b
    text = "\n".join(a.values()) + qs.profiles_yml("krusgraph_shop", "shop")
    con = shop[2]
    if True:   # no text value of the seeded rows (8+ characters, not a date) appears in the drafts
        for (name,) in con.execute("SELECT name FROM shop.sqlite_master WHERE type='table'"):
            for row in con.execute(f"SELECT * FROM shop.[{name}] LIMIT 20"):
                for v in row:
                    if isinstance(v, str) and len(v) >= 8 and not re.fullmatch(r"[\d\-: .T]+", v):
                        assert v not in text, v
    assert not re.search(r"(?i)(password|client_secret|secret\s*:|token\s*:)", text)


def test_profiles_yml_parses_with_placeholders(shop):
    prof = yaml.safe_load(qs.profiles_yml("krusgraph_shop", "shop"))
    dev = prof["krusgraph_shop"]["outputs"]["dev"]
    assert dev["type"] == "fabric" and dev["authentication"] == "CLI" and "<sql-endpoint>" in dev["server"]
    assert dev["database"] == "<warehouse>" and dev["schema"] == "shop"


def test_unknown_format_is_refused(shop):
    with pytest.raises(ValueError):
        qs.suites(shop[0], "shop", "dbt")


def test_dbt_schema_quality_and_profile_options(tool, shop, monkeypatch):
    out = json.loads(server.dbt_schema(*tool, schema="shop", quality="both"))
    assert "quality/soda/checks_shop.yml" in out["quality"] and any(k.startswith("quality/gx/") for k in out["quality"])
    assert "not counted" in out["quality"]["quality/soda/checks_shop.yml"]
    monkeypatch.setattr(server._evidence, "validate", lambda p, execute, max_items=60: shop[1])
    proj = json.loads(server.dbt_schema(*tool, schema="shop", project=True, check_rows=True, quality="gx", profile=True))
    assert "profiles.yml" in proj["files"] and "quality/soda/checks_shop.yml" not in proj["files"]
    gx = [json.loads(v) for k, v in proj["files"].items() if k.startswith("quality/gx/")]
    assert gx and all(isinstance(e["meta"]["counts"], dict) for s in gx for e in s["expectations"])
    assert yaml.safe_load(proj["files"]["profiles.yml"])["krusgraph_shop"]["outputs"]["dev"]["type"] == "fabric"
    bad = json.loads(server.dbt_schema(*tool, schema="shop", quality="dbt"))
    assert "error" in bad
