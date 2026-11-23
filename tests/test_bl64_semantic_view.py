"""BL64 (23 November 2026): semantic_view_draft, the plan as Fabric semantic view YAML (preview).

The format is Microsoft Learn's "Semantic view YAML syntax reference" (MicrosoftDocs/fabric-docs
docs/fundamentals/semantic-views-yaml-reference.md, ms.date 2026-10-20, read at commit 0374a4d). Here, on the synthetic
samples shop, sap_demo, sap_sd and shop_faults, with validate_plan's answer counted on SQLite:

- the file parses as YAML and has the reference's required properties at each level, and only properties it supports;
- every relationship has exactly one column per side, and its `to` side is a key validate_plan counted unique;
- composite-key links (SAP's MANDT+VBELN) are listed under needs_key_column with the sentence, never written;
- with counts, the relationships are the semantic model draft's active set (the same call, semantic_model.active_set);
- every relationship carries its rule and counts as a comment; no row value is written;
- nothing is sent: no HTTP call is made.

SQLite only, synthetic rows only; nothing talks to Fabric, Azure or any service.
"""
from __future__ import annotations

import json
import re

import pytest
import yaml

from fabric_backend import evidence, sap_demo, sap_sample, semantic_model, semantic_view, shop_faults
from fabric_backend.infer import plan as infer_plan
from fabric_backend.platforms import local
from test_bl19_receipt_notebook import _execute, _sap_db, _shop_db
from test_bl33_one_count import _faults_db

LAKEHOUSE = {"item_name": "lh", "item_kind": "Lakehouse"}
SAMPLES = ("shop", "sap_demo", "sap_sd", "shop_faults")

# The reference's tables: required properties per level, and the supported ones (fields, keys, ai_context and
# custom_extensions are omitted by Publish with a warning, so the draft writes none of them).
ROOT_REQUIRED, ROOT_ALLOWED = {"version", "name"}, {"version", "name", "description", "datasets", "relationships", "metrics"}
DATASET_REQUIRED, DATASET_ALLOWED = {"name", "source"}, {"name", "source", "description"}
REL_REQUIRED = REL_ALLOWED = {"name", "from", "to", "from_columns", "to_columns"}     # relationships have no description
METRIC_REQUIRED, METRIC_ALLOWED = {"name", "expression"}, {"name", "expression", "description"}


def _sample(name: str):
    if name == "sap_sd":
        src = sap_sample.source("sap_sd")
        p = infer_plan(src.schema)
        try:
            return p, evidence.validate(p, src.execute, 500), "sap_sd"
        finally:
            src.close()
    db, schema = {"sap_demo": (_sap_db, lambda: sap_demo.sqlite()[0]),
                  "shop_faults": (_faults_db, shop_faults.schema),
                  "shop": (_shop_db, lambda: local.sample_source().schema)}[name]
    p = infer_plan(schema())
    return p, evidence.validate(p, _execute(db()), 500), p.schema.schema


@pytest.fixture(scope="module")
def counted():
    return {n: _sample(n) for n in SAMPLES}


def _draft(counted, name, validation=True, **kw):
    p, v, schema = counted[name]
    return p, v, semantic_view.draft(p, {**LAKEHOUSE, "schema": schema}, f"{name}_view", validation=v if validation else None, **kw)


def _doc(d) -> dict:
    (path, text), = d["parts"].items()
    assert path == f"Context/Semantic Views/{d['view']}/{d['view']}_semantic_view.yaml"
    return yaml.safe_load(text)


@pytest.mark.parametrize("name", SAMPLES)
def test_the_yaml_parses_and_has_the_required_properties(counted, name):
    _p, _v, d = _draft(counted, name)
    doc = _doc(d)
    assert ROOT_REQUIRED <= set(doc) <= ROOT_ALLOWED
    assert str(doc["version"]) == "0.2.0.dev0" and doc["name"] == f"{name}_view"
    assert doc["datasets"], "a nonempty datasets array"
    for ds in doc["datasets"]:
        assert DATASET_REQUIRED <= set(ds) <= DATASET_ALLOWED
        assert re.fullmatch(r"[^.\s]+\.[^.\s]+", ds["source"]), ds["source"]          # schema-qualified, no query
    names = [ds["name"] for ds in doc["datasets"]]
    assert len({n.lower() for n in names}) == len(names)
    for r in doc.get("relationships", []):
        assert set(r) == REL_REQUIRED
        assert r["from"] in names and r["to"] in names
    assert len({r["name"] for r in doc.get("relationships", [])}) == len(doc.get("relationships", []))
    for m in doc.get("metrics", []):
        assert METRIC_REQUIRED <= set(m) <= METRIC_ALLOWED
        dax = [x for x in m["expression"]["dialects"] if x["dialect"] == "DAX"]
        assert len(dax) == 1 and dax[0]["expression"]
        assert m["name"].lower() not in {n.lower() for n in names} | {"metrics"}       # a metric name is no table name
        ref = re.fullmatch(r"COUNTROWS\('((?:[^']|'')+)'\)", dax[0]["expression"])         # the only metric drafted
        assert ref and ref.group(1).replace("''", "'") in names
    assert d["written"] is False and "later round" in d["left_for_later"]


@pytest.mark.parametrize("name", SAMPLES)
def test_relationships_have_one_column_per_side_onto_a_counted_unique_key(counted, name):
    p, v, d = _draft(counted, name)
    doc = _doc(d)
    unique = semantic_view.checked_unique(p, v)
    for r in doc.get("relationships", []):
        assert len(r["from_columns"]) == 1 and len(r["to_columns"]) == 1
        assert r["to"] in unique
        assert p.keys[r["to"]][0] == r["to_columns"]


@pytest.mark.parametrize("name", SAMPLES)
def test_with_counts_the_view_has_the_semantic_model_drafts_active_set(counted, name):
    p, v, d = _draft(counted, name)
    names = {t.name for t in p.schema}
    dup = semantic_model.keys_not_unique(p, v)
    single = [r for r in p.relationships if r.target not in dup and len(r.source_cols) == 1 and len(r.target_cols) == 1
              and len(p.keys.get(r.target, ([], ""))[0]) == 1 and r.source in names and r.target in names]
    active, inactive, evidence_ = semantic_model.active_set(p, single, v, p)
    assert evidence_ is not None or not single                                # the counts decided (BL51)
    unique = semantic_view.checked_unique(p, v)
    want = {(r.source, r.source_cols[0], r.target) for r in active if r.target in unique}
    got = {(r["from"], r["from_columns"][0], r["to"]) for r in _doc(d).get("relationships", [])}
    assert got == want
    # the model draft on the source tables (combined=False) relates the same active set
    tmdl = semantic_model.draft(p, {**LAKEHOUSE, "schema": counted[name][2]}, "m", validation=v, combined=False)["parts"]
    on = set()
    for block in tmdl.get("definition/relationships.tmdl", "").split("relationship ")[1:]:
        if "isActive: false" in block:
            continue
        frm = re.search(r"fromColumn: '?([^'.]+)'?\.'?([^'\n]+?)'?\n", block)
        to = re.search(r"toColumn: '?([^'.]+)'?\.", block)
        if to.group(1) not in {c for c in ("Calendar", "Krusgraph Calendar")}:
            on.add((frm.group(1), frm.group(2), to.group(1)))
    assert got <= on and {x for x in on if x[2] in unique} == got
    # nothing active is lost: what is not in the view is listed with its reason
    listed = {(x["from"], x["columns"][0], x["to"]) for x in d["to_side_not_checked"]["relationships"] + d["not_in_view_personal_data"]}
    assert {(r.source, r.source_cols[0], r.target) for r in active} == got | listed
    assert {(x["from"], x["columns"][0], x["to"]) for x in d["not_in_view_inactive"]} == {(r.source, r.source_cols[0], r.target) for r, _ in inactive}


def test_each_relationship_carries_its_rule_and_counts_as_a_comment(counted):
    _p, _v, d = _draft(counted, "shop")
    text, = d["parts"].values()
    blocks = text.split("relationships:\n", 1)[1].split("metrics:\n", 1)[0]
    comments = re.findall(r"^  # (rule .+)$", blocks, re.M)
    assert len(comments) == len(_doc(d)["relationships"]) == d["summary"]["relationships"] > 0
    for c in comments:
        assert re.fullmatch(r"rule R\d; validate_plan counted \d+ rows with a value, \d+ matched, \d+ orphans \(\w+\)", c), c
    for r in d["summary"]["relationships_list"]:
        assert {"rule", "rows_with_value", "matched", "orphans"} <= set(r)


def test_composite_keys_are_listed_under_needs_key_column_and_never_written(counted):
    for name in ("sap_sd", "sap_demo"):
        p, _v, d = _draft(counted, name)
        need = d["needs_key_column"]
        assert need["relationships"], name
        assert "combined key column in silver or gold" in need["say"]
        written = {(r["from"], r["to"]) for r in _doc(d).get("relationships", [])}
        for x in need["relationships"]:
            assert len(x["columns"]) > 1 or len(p.keys[x["to"]][0]) > 1
            assert (x["from"], x["to"]) not in written
            assert x["rule"] and x["counts"]
    _p, _v, d = _draft(counted, "sap_sd")
    pairs = {(x["from"], tuple(x["columns"]), x["to"]) for x in d["needs_key_column"]["relationships"]}
    assert ("VBAP", ("MANDT", "VBELN"), "VBAK") in pairs


def test_a_key_the_counts_show_is_not_unique_is_never_a_to_side(counted):
    p, v, d = _draft(counted, "shop_faults")
    dup = semantic_model.keys_not_unique(p, v)
    assert dup
    assert not any(r["to"] in dup for r in _doc(d).get("relationships", []))
    assert {x["to"] for x in d["not_unique"]} <= set(dup) and d["not_unique"]


def test_without_counts_no_relationship_is_written_and_each_is_listed(counted):
    p, _v, d = _draft(counted, "shop", validation=False)
    assert "relationships" not in _doc(d)
    assert d["to_side_not_checked"]["relationships"] and "validate=true" in d["to_side_not_checked"]["say"]
    assert d["summary"]["counted"] is False


@pytest.mark.parametrize("name", SAMPLES)
def test_no_row_value_is_written(counted, name):
    """The answer holds names and counts only: no value of a text column of the sample rows appears in it."""
    p, v, d = _draft(counted, name)
    rows = _rows(name)
    text = json.dumps(d)
    names = {t.name.lower() for t in p.schema} | {c.name.lower() for t in p.schema for c in t.columns}
    leaked = {s for s in rows if isinstance(s, str) and len(s) >= 4 and s.lower() not in names and not s.isdigit() and s in text}
    assert not leaked, sorted(leaked)[:5]


def _rows(name: str) -> set:
    con = {"shop": _shop_db, "sap_demo": _sap_db, "shop_faults": _faults_db}.get(name)
    out = set()
    if con is None:                                                           # sap_sd: read it through its own source
        src = sap_sample.source("sap_sd")
        try:
            for t in src.schema:
                for r in src.execute(f"SELECT * FROM [{src.schema.schema}].[{t.name}]"):
                    out |= set(r.values())
        finally:
            src.close()
        return out
    c = con()
    for (schema,) in [(s[1],) for s in c.execute("PRAGMA database_list") if s[1] not in ("main", "temp")]:
        for (t,) in c.execute(f"SELECT name FROM [{schema}].sqlite_master WHERE type='table'"):
            for r in c.execute(f"SELECT * FROM [{schema}].[{t}]"):
                out |= set(r)
    return out


def test_personal_data_columns_follow_the_masking_rule(counted):
    p, v, d = _draft(counted, "shop")
    cols = {(x["table"], x["column"]) for x in d["personal_data"]["columns"]}
    assert ("customers", "name") in cols and d["personal_data"]["shown"] is False
    assert "show_personal_data=true" in d["personal_data"]["note"] and "gold view" in d["personal_data"]["note"]
    doc = _doc(d)
    for r in doc.get("relationships", []):                                    # no relationship on such a column
        assert (r["from"], r["from_columns"][0].lower()) not in {(t, c.lower()) for t, c in cols}
        assert (r["to"], r["to_columns"][0].lower()) not in {(t, c.lower()) for t, c in cols}
    for m in doc.get("metrics", []):                                          # no metric reads one
        assert not any(f"[{c}]" in m["expression"]["dialects"][0]["expression"] for _t, c in cols)
    _p, _v, shown = _draft(counted, "shop", show_personal_data=True)
    assert shown["personal_data"]["shown"] is True and "unless" not in shown["personal_data"]["note"]


def test_metrics_are_row_counts_of_the_fact_tables_as_the_model_draft_suggests(counted):
    p, v, d = _draft(counted, "shop")
    tmdl = semantic_model.draft(p, {**LAKEHOUSE, "schema": "shop"}, "m", validation=v, combined=False)["parts"]
    counts = {m.group(1) for text in tmdl.values() for m in re.finditer(r"= COUNTROWS\('([^']+)'\)", text)}
    got = {re.search(r"'(.+)'", m["dax"]).group(1) for m in d["summary"]["metrics_list"]}
    assert got and got == counts


def test_a_name_a_folder_cannot_have_is_refused():
    p = infer_plan(local.sample_source().schema)
    for bad in ("", " x", "a/b", "a:b"):
        with pytest.raises(ValueError):
            semantic_view.draft(p, LAKEHOUSE, bad)


def test_a_warehouse_gets_the_lakehouse_only_gate():
    p = infer_plan(local.sample_source().schema)
    d = semantic_view.draft(p, {"item_kind": "Warehouse", "schema": "shop"}, "v")
    assert "lakehouses only" in d["gate"]
    assert any("lakehouses only" in x for x in d["limits"]["items"])


def test_nothing_is_sent(counted, monkeypatch):
    """The draft makes no HTTP call: requests, urllib and sockets are cut off while it runs."""
    import socket
    import urllib.request

    import requests

    def refuse(*_a, **_k):
        raise AssertionError("semantic_view.draft tried to reach the network")
    for verb in ("get", "post", "put", "patch", "delete", "request"):
        monkeypatch.setattr(requests, verb, refuse)
    monkeypatch.setattr(requests.Session, "request", refuse)
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    for name in SAMPLES:
        _p, _v, d = _draft(counted, name)
        assert d["written"] is False


def test_the_hosted_tool_is_registered_read_only():
    import asyncio

    from fabric_backend import server
    tool = next(t for t in asyncio.run(server.mcp.list_tools()) if t.name == "semantic_view_draft")
    assert tool.annotations.read_only_hint is True
    assert {"workspace", "source", "name", "tables", "validate", "show_personal_data"} <= set(tool.input_schema["properties"])
