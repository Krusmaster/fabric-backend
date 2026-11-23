"""BL65 (23 November 2026): semantic_view_draft on the silver layer's combined key columns.

A Fabric semantic view relates tables on one column per side, with a unique `to` side (Microsoft Learn, "Semantic view
YAML syntax reference", MicrosoftDocs/fabric-docs docs/fundamentals/semantic-views-yaml-reference.md, ms.date
2026-10-20, read at commit 0374a4d). Every order-to-cash link of SAP uses MANDT plus a key, so BL64's view of sap_sd had
no relationship. With `combined=True` (the hosted tool's silver=true) the view reads the silver tables, where the silver
step writes one combined key column per composite key and link (n226, combined_keys.py), as the semantic model draft
does. Here, on the synthetic samples shop, sap_demo, sap_sd and shop_faults, with validate_plan counted on SQLite:

- without the option the file is BL64's, byte for byte (tests/golden/semantic_view_bl64.json, written by BL64's code);
- sap_sd with silver relates order to cash on combined columns, named and placed as the silver notebook draft names them;
- shop and shop_faults have no composite key, so silver changes nothing in their file;
- a composite key validate_plan did not count unique is listed, never a `to` side;
- the YAML parses and follows the reference; the relationships are the semantic model draft's own active set on silver;
- needs_key_column names the silver column that fixes each entry and the tools that build it;
- the answer says the silver notebook must run in Fabric before the view is published;
- personal data, the lakehouse gate, no HTTP call and no row value hold as in BL64.

SQLite only, synthetic rows only; nothing talks to Fabric, Azure or any service.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest
import yaml

from fabric_backend import combined_keys, semantic_model, semantic_view, silver
from test_bl64_semantic_view import (DATASET_ALLOWED, DATASET_REQUIRED, LAKEHOUSE, METRIC_ALLOWED, METRIC_REQUIRED, REL_REQUIRED,
                                     ROOT_ALLOWED, ROOT_REQUIRED, SAMPLES, _rows, _sample)

GOLDEN = Path(__file__).parent / "golden" / "semantic_view_bl64.json"
ORDER_TO_CASH = {("VBAP", "MANDT_VBELN_key", "VBAK", "MANDT_VBELN_key"), ("LIPS", "MANDT_VBELN_key", "LIKP", "MANDT_VBELN_key"),
                 ("VBRP", "MANDT_VBELN_key", "VBRK", "MANDT_VBELN_key"), ("VBAK", "MANDT_KUNNR_key", "KNA1", "MANDT_KUNNR_key"),
                 ("VBRK", "MANDT_BUKRS_key", "T001", "MANDT_BUKRS_key")}


@pytest.fixture(scope="module")
def counted():
    return {n: _sample(n) for n in SAMPLES}


def _draft(counted, name, validation=True, combined=True, info=None, **kw):
    p, v, schema = counted[name]
    if validation is True:
        validation = v
    return semantic_view.draft(p, {**LAKEHOUSE, "schema": schema, **(info or {})}, f"{name}_view",
                               validation=validation or None, combined=combined, **kw)


def _text(d) -> str:
    (text,) = d["parts"].values()
    return text


def _doc(d) -> dict:
    return yaml.safe_load(_text(d))


def _rels(d) -> set[tuple[str, str, str, str]]:
    return {(r["from"], r["from_columns"][0], r["to"], r["to_columns"][0]) for r in _doc(d).get("relationships", [])}


# ------------------------------------------------------------------ without the option, BL64 byte for byte ----------

@pytest.mark.parametrize("name", SAMPLES)
@pytest.mark.parametrize("with_counts", (True, False))
def test_without_silver_the_file_is_bl64s_byte_for_byte(counted, name, with_counts):
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    key = f"{name}|{'counted' if with_counts else 'not_counted'}"
    assert _text(_draft(counted, name, validation=with_counts, combined=False)) == golden[key]
    p, v, schema = counted[name]
    default = semantic_view.draft(p, {**LAKEHOUSE, "schema": schema}, f"{name}_view", validation=v if with_counts else None)
    assert _text(default) == golden[key] and "before_publish" not in default and "reads" not in default["summary"]


@pytest.mark.parametrize("name", ("shop", "shop_faults"))
def test_without_a_composite_key_silver_changes_nothing_in_the_file(counted, name):
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    d = _draft(counted, name)
    assert _text(d) == golden[f"{name}|counted"]
    assert d["summary"]["reads"]["layer"] == "source" and "changes nothing" in d["summary"]["reads"]["said"]
    assert "before_publish" not in d and "combined_key_columns" not in d["summary"]


# ------------------------------------------------------------------ sap_sd on silver --------------------------------

def test_sap_sd_with_silver_relates_order_to_cash_on_combined_columns(counted):
    d = _draft(counted, "sap_sd")
    got = _rels(d)
    assert ORDER_TO_CASH <= got, ORDER_TO_CASH - got
    assert d["summary"]["needs_key_column"] == 0 and not d["needs_key_column"]["relationships"]
    p = counted["sap_sd"][0]
    comb = combined_keys.columns(p)
    for frm, fcol, to, tcol in got:                                           # n226's own names, on both sides
        assert tcol == combined_keys.key_column(p, to, comb)
        assert fcol in {c.name for c in comb[frm]}
    # each relationship's comment says which columns it combines, and carries the counts of the source link
    text = _text(d)
    assert "# rule SAP pack; combined key columns of VBAP.MANDT+VBELN -> VBAK.MANDT+VBELN; validate_plan counted" in text
    for r in d["summary"]["relationships_list"]:
        assert r["combines"]["from"] and r["state"] in ("holds", "fails")


@pytest.mark.parametrize("schemas_enabled,silver_schema", ((True, "silver"), (True, "slv"), (False, "silver")))
def test_datasets_are_the_silver_tables_as_the_silver_notebook_draft_names_them(counted, schemas_enabled, silver_schema):
    p, v, schema = counted["sap_sd"]
    info = {**LAKEHOUSE, "schema": schema, "schemas_enabled": schemas_enabled, "silver_schema": silver_schema}
    d = semantic_view.draft(p, info, "v", validation=v, combined=True)
    spec = silver.spec(p, info, silver_schema)
    want = {t["table"]: (f"{t['target'][0]}.{t['target'][1]}" if t["target"][0] else f"{schema}.{t['target'][1]}")
            for t in spec["tables"]}
    got = {ds["name"]: ds["source"] for ds in _doc(d)["datasets"]}
    assert got == want
    written = {(t["table"], c["name"]) for t in spec["tables"] for c in t.get("combined", [])}
    for frm, fcol, to, tcol in _rels(d):                                      # every column related on is one silver writes
        assert (frm, fcol) in written and (to, tcol) in written


def test_the_answer_says_the_silver_notebook_must_run_before_publishing(counted):
    d = _draft(counted, "sap_sd")
    assert "Run the silver notebook in Fabric" in d["before_publish"] and "before the view is published" in d["before_publish"]
    assert "silver_notebook_draft" in d["before_publish"] and "create_silver_notebook" in d["before_publish"]
    assert "# Before publishing: run the silver notebook in Fabric." in _text(d)
    reads = d["summary"]["reads"]
    assert reads["layer"] == "silver" and reads["schema"] == "silver" and reads["tables"] == "<table>"
    assert d["summary"]["combined_key_columns"] == combined_keys.describe(combined_keys.columns(counted["sap_sd"][0]))


# ------------------------------------------------------------------ uniqueness of the `to` side ---------------------

def _with_key(v: dict, table: str, verdict: str | None) -> dict:
    """validate_plan's answer with one key's count changed (verdict given) or left out (None)."""
    out = copy.deepcopy(v)
    keys = []
    for k in out["keys"]:
        if k["table"] == table:
            if verdict is None:
                continue
            k.update(verdict=verdict, distinct=k["rows"] - 1)
        keys.append(k)
    out["keys"] = keys
    return out


def test_a_composite_key_counted_not_unique_is_listed_not_emitted(counted):
    _p, v, _s = counted["sap_sd"]
    d = _draft(counted, "sap_sd", validation=_with_key(v, "VBAK", "not unique: 1 duplicate rows (299 distinct values in 300 rows)"))
    assert not any(to == "VBAK" for _f, _fc, to, _tc in _rels(d))
    listed = {(x["from"], tuple(x["columns"]), x["to"]) for x in d["not_unique"]}
    assert ("VBAP", ("MANDT", "VBELN"), "VBAK") in listed
    assert all("not unique in the rows" in x["why"] for x in d["not_unique"])


def test_a_composite_key_not_counted_is_listed_not_emitted(counted):
    _p, v, _s = counted["sap_sd"]
    d = _draft(counted, "sap_sd", validation=_with_key(v, "VBAK", None))
    assert not any(to == "VBAK" for _f, _fc, to, _tc in _rels(d))
    items = [x for x in d["to_side_not_checked"]["relationships"] if x["to"] == "VBAK"]
    assert items and all("MANDT+VBELN of VBAK (its combined column MANDT_VBELN_key)" in x["why"] for x in items)
    assert all(x["silver_columns"]["to"] == "VBAK.MANDT_VBELN_key" for x in items)


def test_without_counts_silver_writes_no_relationship(counted):
    d = _draft(counted, "sap_sd", validation=False)
    assert "relationships" not in _doc(d)
    assert d["to_side_not_checked"]["relationships"] and d["summary"]["counted"] is False


# ------------------------------------------------------------------ the reference, and the model's active set -------

@pytest.mark.parametrize("name", SAMPLES)
def test_the_yaml_parses_and_follows_the_reference(counted, name):
    d = _draft(counted, name)
    doc = _doc(d)
    assert ROOT_REQUIRED <= set(doc) <= ROOT_ALLOWED and str(doc["version"]) == "0.2.0.dev0"
    names = [ds["name"] for ds in doc["datasets"]]
    assert len({n.lower() for n in names}) == len(names)
    for ds in doc["datasets"]:
        assert DATASET_REQUIRED <= set(ds) <= DATASET_ALLOWED
        assert re.fullmatch(r"[^.\s]+\.[^.\s]+", ds["source"]), ds["source"]          # schema-qualified, no query
    for r in doc.get("relationships", []):
        assert set(r) == REL_REQUIRED and r["from"] in names and r["to"] in names
        assert len(r["from_columns"]) == 1 and len(r["to_columns"]) == 1
    assert len({r["name"] for r in doc.get("relationships", [])}) == len(doc.get("relationships", []))
    for m in doc.get("metrics", []):
        assert METRIC_REQUIRED <= set(m) <= METRIC_ALLOWED
        assert [x["dialect"] for x in m["expression"]["dialects"]] == ["DAX"]
        assert m["name"].lower() not in {n.lower() for n in names} | {"metrics"}
    assert d["written"] is False


@pytest.mark.parametrize("name", SAMPLES)
def test_the_relationships_are_the_model_drafts_active_set_on_silver(counted, name):
    """The semantic model draft reads silver by itself when a link needs a composite key (n226); the view with silver
    relates exactly its active relationships whose one side validate_plan counted unique, and lists the rest."""
    p, v, schema = counted[name]
    d = _draft(counted, name)
    tmdl = semantic_model.draft(p, {**LAKEHOUSE, "schema": schema}, "m", validation=v)["parts"]
    on = set()
    for block in tmdl.get("definition/relationships.tmdl", "").split("relationship ")[1:]:
        if "isActive: false" in block:
            continue
        frm = re.search(r"fromColumn: '?([^'.]+)'?\.'?([^'\n]+?)'?\n", block)
        to = re.search(r"toColumn: '?([^'.]+)'?\.'?([^'\n]+?)'?\n", block)
        if to.group(1) not in ("Calendar", "Krusgraph Calendar"):
            on.add((frm.group(1), frm.group(2), to.group(1), to.group(2)))
    unique = semantic_view.checked_unique(p, v, composite=True)
    got = _rels(d)
    assert got == {x for x in on if x[2] in unique}
    listed = {x["to"] for x in d["to_side_not_checked"]["relationships"] + d["not_in_view_personal_data"]}
    assert {x[2] for x in on} - {x[2] for x in got} <= listed


# ------------------------------------------------------------------ needs_key_column names the fix ------------------

@pytest.mark.parametrize("name", ("sap_sd", "sap_demo"))
def test_needs_key_column_names_the_silver_column_that_fixes_each_entry(counted, name):
    d = _draft(counted, name, combined=False)
    need = d["needs_key_column"]
    assert need["relationships"] and "silver_notebook_draft" in need["silver"] and "create_silver_notebook" in need["silver"]
    on_silver = _draft(counted, name)
    placed = {(f"{f}.{fc}", f"{t}.{tc}") for f, fc, t, tc in _rels(on_silver)}
    placed |= {(x["silver_columns"]["from"], x["silver_columns"]["to"])
               for k in ("not_in_view_inactive", "not_in_view_personal_data") for x in on_silver[k]}
    placed |= {(x["silver_columns"]["from"], x["silver_columns"]["to"]) for x in on_silver["to_side_not_checked"]["relationships"]}
    for x in need["relationships"]:
        fix = x["silver_columns"]
        assert fix, x
        assert (fix["from"], fix["to"]) in placed                             # the column named is the one silver relates on
        assert fix["from"].split(".", 1)[1] in x["fix"] and "silver=true" in x["fix"]


# ------------------------------------------------------------------ what BL64 kept ----------------------------------

def test_a_relationship_on_a_personal_data_column_stays_out(counted, monkeypatch):
    """A combined column is personal when one of its parts is: flag KNA1.KUNNR and every link onto KNA1 is listed."""
    real = semantic_view._privacy.personal_columns

    def flag(schema, tables):
        out = dict(real(schema, tables))
        out[("KNA1", "KUNNR")] = {"rule": "P-test", "what": "a test flag"}
        return out
    monkeypatch.setattr(semantic_view._privacy, "personal_columns", flag)
    d = _draft(counted, "sap_sd")
    assert not any(to == "KNA1" for _f, _fc, to, _tc in _rels(d))
    assert {x["to"] for x in d["not_in_view_personal_data"]} == {"KNA1"}
    shown = _draft(counted, "sap_sd", show_personal_data=True)
    assert any(to == "KNA1" for _f, _fc, to, _tc in _rels(shown))


def test_a_warehouse_keeps_the_gate_and_reads_the_source(counted):
    p, v, schema = counted["sap_sd"]
    d = semantic_view.draft(p, {"item_kind": "Warehouse", "schema": schema}, "v", validation=v, combined=True)
    assert "lakehouses only" in d["gate"] and "before_publish" not in d
    assert d["summary"]["reads"]["layer"] == "source" and "lakehouse only" in d["summary"]["reads"]["said"]
    assert not _rels(d)


@pytest.mark.parametrize("name", SAMPLES)
def test_no_row_value_is_written(counted, name):
    p, d = counted[name][0], _draft(counted, name)
    text = json.dumps(d)
    names = ({t.name.lower() for t in p.schema} | {c.name.lower() for t in p.schema for c in t.columns}
             | {c["column"].lower() for c in d["summary"].get("combined_key_columns", [])})
    leaked = {s for s in _rows(name) if isinstance(s, str) and len(s) >= 4 and s.lower() not in names and not s.isdigit() and s in text}
    assert not leaked, sorted(leaked)[:5]


def test_nothing_is_sent(counted, monkeypatch):
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
        assert _draft(counted, name)["written"] is False


def test_the_hosted_tool_takes_silver_and_stays_read_only():
    import asyncio
    import inspect

    from fabric_backend import server
    tool = next(t for t in asyncio.run(server.mcp.list_tools()) if t.name == "semantic_view_draft")
    assert tool.annotations.read_only_hint is True
    prop = tool.input_schema["properties"]["silver"]
    assert prop["type"] == "boolean" and prop["default"] is False
    assert inspect.signature(server.semantic_view_draft).parameters["silver"].default is False


def test_the_hosted_tool_with_silver_says_what_must_run_first(counted, monkeypatch):
    """The tool's own path, with Fabric replaced: the silver schema is found as the model draft finds it (_layers), and
    a silver schema the source does not have yet is said, with the tools that build it."""
    from types import SimpleNamespace

    from fabric_backend import server
    p, v, schema = counted["sap_sd"]
    asked = {}
    monkeypatch.setattr(server, "_source_inputs", lambda *a, **k: (p, {**LAKEHOUSE, "schema": schema, "workspace_id": "w"}))
    monkeypatch.setattr(server, "_connected", lambda *a, **k: (SimpleNamespace(schema=schema), lambda sql: []))
    monkeypatch.setattr(server._evidence, "validate", lambda *a, **k: v)

    def layers(info, silver_schema="", gold_schema="", pipeline="", ctx=None, need=True, which=("silver", "gold")):
        asked["need"] = need
        return {"silver": "silver", "gold": "gold", "from": {"silver": "the default", "gold": "the default"}, "said": ""}
    monkeypatch.setattr(server, "_layers", layers)
    monkeypatch.setattr(server, "_silver_there", lambda *a, **k: False)
    out = json.loads(server.semantic_view_draft(workspace="w", source="lh", name="v", schema=schema, silver=True))
    assert asked["need"] is True and out["summary"]["reads"]["schema_from"] == "the default"
    assert ORDER_TO_CASH <= _rels(out)
    assert "create_silver_notebook" in out["silver_not_built"] and "silver_notebook_draft" in out["silver_not_built"]
    assert out["before_publish"] in out["note"]
    plain = json.loads(server.semantic_view_draft(workspace="w", source="lh", name="v", schema=schema))
    assert "silver_not_built" not in plain and "before_publish" not in plain and not _rels(plain)
