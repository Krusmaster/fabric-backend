"""Round n123: the server-wide switches (fabric_backend/switches.py, docs/LANDSCAPE.md idea 3).

KRUSGRAPH_READ_ONLY=1 leaves out the tools that create or change something in Fabric; KRUSGRAPH_NO_ROW_VALUES=1
leaves out sample_rows and takes the row values out of every other answer. Both off (the default) changes nothing.

The listings are read in a fresh interpreter per setting, because the servers decide registration at import. The
answers are read in this process against the golden tests' synthetic shop workspace (tests/golden_support.py), with
the settings switched at call time, and checked against the known values of fabric_backend/seed.py's rows plus a
GraphQL result carrying values of its own.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fabric_backend import discovery, seed, server, switches, tool_status
from test_golden import HOSTED_CALLS, LOCAL_CALLS, SRC, fabric, local  # noqa: F401  (the synthetic shop workspace)

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).parent / "golden"
SETTINGS = (switches.READ_ONLY, switches.NO_ROW_VALUES)

_LIST = r"""
import asyncio, inspect, json, sys
mod = __import__("fabric_backend." + sys.argv[1], fromlist=["mcp"])
from mcp import Client
tools = asyncio.run(mod.mcp.list_tools())
out = []
for t in sorted(tools, key=lambda t: t.name):
    e = json.loads(t.model_dump_json(exclude_none=True))
    if e.get("description"):
        e["description"] = inspect.cleandoc(e["description"])
    out.append(e)
ro = [t.model_dump(by_alias=True, exclude_none=True, mode="json") for t in tools if t.annotations and t.annotations.read_only_hint]
for t in ro:
    t["description"] = inspect.cleandoc(t.get("description", ""))

async def call(name):
    try:
        async with Client(mod.mcp) as c:
            r = await c.call_tool(name, {})
            return {"is_error": bool(r.is_error), "text": " ".join(getattr(p, "text", "") for p in r.content)}
    except Exception as e:  # an SDK may raise instead of answering is_error
        return {"is_error": True, "text": str(e)}

print(json.dumps({"tools": out, "ro_size": len(json.dumps({"tools": ro}, separators=(",", ":"), ensure_ascii=False)),
                  "calls": {n: asyncio.run(call(n)) for n in sys.argv[2:]}}))
"""


def _listing(module: str, env: dict, calls: tuple = ()) -> dict:
    base = {k: v for k, v in os.environ.items() if k not in SETTINGS}
    run = subprocess.run([sys.executable, "-c", _LIST, module, *calls], env=base | env, cwd=ROOT,
                         capture_output=True, text=True, check=True)
    return json.loads(run.stdout)


def _creating(tools: list[dict]) -> set[str]:
    """What the settings should remove under READ_ONLY, read from tool_status and the annotations as switches.py does."""
    return {t["name"] for t in tools
            if (s := tool_status.STATUS.get(t["name"])) is not None and s.kind == tool_status.CREATES
            or (t.get("annotations") or {}).get("read_only_hint") is False}


# ------------------------------------------------------------------ the listings ---------------------------------------

@pytest.fixture(scope="module")
def hosted():
    some = ("create_backend", "sample_rows")
    return {name: _listing("server", env, some) for name, env in (
        ("off", {}), ("zero", {switches.READ_ONLY: "0", switches.NO_ROW_VALUES: "0"}),
        ("ro", {switches.READ_ONLY: "1"}), ("nrv", {switches.NO_ROW_VALUES: "1"}),
        ("both", {switches.READ_ONLY: "1", switches.NO_ROW_VALUES: "1"}))}


def test_with_both_off_the_hosted_listing_is_unchanged(hosted):
    golden = json.loads((GOLDEN / "hosted_listing.json").read_text(encoding="utf-8"))["tools"]
    assert hosted["off"]["tools"] == golden and hosted["zero"]["tools"] == golden
    assert {t["name"] for t in golden} >= {"create_backend", "sample_rows"}  # the tool count is test_tool_count_texts.py's
    assert hosted["off"]["ro_size"] <= 66_500                                # the read-only listing cap (n26)


def test_read_only_removes_exactly_the_creating_tools(hosted):
    off = {t["name"] for t in hosted["off"]["tools"]}
    ro = {t["name"] for t in hosted["ro"]["tools"]}
    creating = _creating(hosted["off"]["tools"])
    assert {"create_backend", "create_views", "create_report", "create_semantic_model"} <= creating
    assert ro == off - creating and "sample_rows" in ro
    assert all(t["annotations"]["read_only_hint"] is True for t in hosted["ro"]["tools"])
    assert hosted["ro"]["ro_size"] == hosted["off"]["ro_size"] <= 66_500    # the read tools are as they were
    assert [t for t in hosted["ro"]["tools"]] == [t for t in hosted["off"]["tools"] if t["name"] in ro]


def test_tool_status_and_the_annotations_agree_on_what_creates(hosted):
    """switches.py reads both; on the hosted server they must say the same, so neither can drift unseen."""
    for t in hosted["off"]["tools"]:
        s = tool_status.STATUS.get(t["name"])
        if s is not None:
            assert (s.kind == tool_status.CREATES) == (t["annotations"]["read_only_hint"] is False), t["name"]


def test_no_row_values_removes_sample_rows_only(hosted):
    off = {t["name"] for t in hosted["off"]["tools"]}
    assert {t["name"] for t in hosted["nrv"]["tools"]} == off - {"sample_rows"}
    both = {t["name"] for t in hosted["both"]["tools"]}
    assert both == off - {"sample_rows"} - _creating(hosted["off"]["tools"])


def test_a_removed_tool_refuses_when_called_by_name(hosted):
    assert not hosted["off"]["calls"]["create_backend"]["text"].startswith("Unknown tool")
    for setting, gone in (("ro", "create_backend"), ("nrv", "sample_rows"), ("both", "create_backend"), ("both", "sample_rows")):
        call = hosted[setting]["calls"][gone]
        assert call["is_error"] and "unknown tool" in call["text"].lower(), (setting, call)
    assert not hosted["nrv"]["calls"]["create_backend"]["text"].lower().startswith("unknown tool")


def test_the_local_server_follows_the_same_settings():
    golden = json.loads((GOLDEN / "local_listing.json").read_text(encoding="utf-8"))
    off = _listing("mcp_server", {})
    assert {t["name"]: t for t in off["tools"] if t["name"] in golden} == golden
    names = {t["name"] for t in off["tools"]}
    creating = _creating(off["tools"])
    assert {"create_backend", "create_views"} <= creating
    assert {n for n in names if n.startswith("create_databricks")} <= creating            # when the Databricks tools are there
    ro = _listing("mcp_server", {switches.READ_ONLY: "1"}, ("create_views",))
    assert {t["name"] for t in ro["tools"]} == names - creating
    assert ro["calls"]["create_views"]["is_error"] and "unknown tool" in ro["calls"]["create_views"]["text"].lower()
    nrv = _listing("mcp_server", {switches.NO_ROW_VALUES: "1"}, ("sample_rows",))
    assert {t["name"] for t in nrv["tools"]} == names - {"sample_rows"}
    assert nrv["calls"]["sample_rows"]["is_error"]


# ------------------------------------------------------------------ the answers ----------------------------------------

MARKER = "Quokka-Harbour-7731"                    # a value only the GraphQL fixture's rows carry


def _known_values() -> set[str]:
    """String values of the synthetic shop rows that cannot be mistaken for a name or a word of the answers' own text:
    longer than five characters, not a table or column name, and not a lower-case code such as audit_log's 'export'."""
    names = {t.lower() for t in seed.SCHEMAS} | {c.split()[0].strip("[]").lower() for ddl in seed.SCHEMAS.values()
                                                 for c in ddl.split(",")}
    out = set()
    for rows in seed.rows().values():
        for r in rows:
            for v in r:
                if isinstance(v, str) and len(v) > 5 and v.lower() not in names and not v.replace("_", "").islower():
                    out.add(v)
    return out | {MARKER}


@pytest.fixture
def valued(fabric, monkeypatch):  # noqa: F811
    """The golden workspace, its GraphQL API answering with rows that carry MARKER."""
    import requests
    post = requests.post

    def with_rows(url, *a, json=None, **k):
        if url.endswith("/graphql") and "__schema" not in (json or {}).get("query", ""):
            from golden_support import Response
            return Response(200, {"data": {"orders": {"items": [{"order_id": 100, "note": MARKER},
                                                                {"order_id": 101, "note": MARKER + "-b"}]}}})
        return post(url, *a, json=json, **k)
    monkeypatch.setattr(requests, "post", with_rows)
    return fabric


def _hosted_answers() -> dict:
    out = {}
    for i, (name, kwargs) in enumerate(HOSTED_CALLS):
        out[f"{i}:{name}"] = getattr(server, name)(**kwargs)
    out["q:query_graphql"] = server.query_graphql(workspace="demo", api="shop_api", query="{ orders { items { order_id note } } }")
    return out


def test_the_fixture_carries_known_values_with_the_switch_off(valued, monkeypatch):
    for s in SETTINGS:
        monkeypatch.delenv(s, raising=False)
    known = _known_values()
    rows = server.sample_rows(**SRC, table="customers", show_personal_data=True)
    assert any(v in rows for v in known)                                      # the check below can fail
    assert MARKER in server.query_graphql(workspace="demo", api="shop_api", query="{ orders { items { note } } }")


def test_no_hosted_answer_contains_a_row_value(valued, monkeypatch):
    monkeypatch.setenv(switches.NO_ROW_VALUES, "1")
    known = _known_values()
    answers = _hosted_answers()
    for key, text in answers.items():
        hit = [v for v in known if v in text]
        assert not hit, (key, hit[:3])
    for key, text in answers.items():
        if key.split(":")[1] == "sample_rows":
            assert json.loads(text)["kind"] == "switched_off"
    q = json.loads(answers["q:query_graphql"])
    assert q["data"] == {"orders": {"items": {"count": 2, "fields": {"order_id": switches.REMOVED, "note": switches.REMOVED}}}}
    summary = json.loads(answers[next(k for k in answers if k.endswith("validate_plan") and HOSTED_CALLS[int(k.split(":")[0])][1] == SRC)])
    assert summary["next_steps"] and all(s["tool"] != "sample_rows" for s in summary["next_steps"])
    assert summary["summary"]                                                # the counts and words are still there


def test_the_other_answers_keep_their_names_and_counts(valued, monkeypatch):
    for s in SETTINGS:
        monkeypatch.delenv(s, raising=False)
    plain = {k: v for k, v in _hosted_answers().items()}
    monkeypatch.setenv(switches.NO_ROW_VALUES, "1")
    switched = _hosted_answers()
    same = [k for k in plain if plain[k] == switched[k] or json.loads(plain[k]) == json.loads(switched[k])]
    changed = sorted({k.split(":")[1] for k in plain if k not in same})
    # n158 (review L4): create_semantic_model's read_from_rows drops the first and last date under the switch
    assert set(changed) <= {"sample_rows", "query_graphql", "validate_plan", "create_semantic_model"}, changed
    assert "plan_backend" not in changed and "data_dictionary" not in changed


def test_read_only_refuses_the_creating_tools_and_leaves_the_rest(valued, monkeypatch):
    for s in SETTINGS:
        monkeypatch.delenv(s, raising=False)
    plain = _hosted_answers()
    monkeypatch.setenv(switches.READ_ONLY, "1")
    switched = _hosted_answers()
    for k, text in switched.items():
        name = k.split(":")[1]
        if switches.creates(name):
            assert json.loads(text)["kind"] == "switched_off", k
        else:
            assert json.loads(text) == json.loads(plain[k]), k


def test_no_local_answer_contains_a_row_value(local, monkeypatch):  # noqa: F811
    from fabric_backend import mcp_server
    monkeypatch.setenv(switches.NO_ROW_VALUES, "1")
    known = _known_values()
    for name, kwargs in LOCAL_CALLS:
        text = getattr(mcp_server, name)(**kwargs)
        hit = [v for v in known if v in text]
        assert not hit, (name, hit[:3])
        if name == "sample_rows":
            assert json.loads(text)["kind"] == "switched_off"


def test_a_value_quoted_in_an_error_message_is_removed():
    env = {switches.NO_ROW_VALUES: "1"}
    text = json.dumps({"error": "The SQL analytics endpoint answered with an error for workspace 'demo': Conversion failed "
                                "when converting the nvarchar value 'Anna Berg' to data type int.", "kind": "sql_error",
                       "hint": "Check the message."})
    out = json.loads(switches.answer(text, environ=env))
    assert "Anna Berg" not in out["error"] and "value '…'" in out["error"] and "workspace 'demo'" in out["error"]
    assert switches.answer(text, environ={}) == text                          # off: the answer is the same text


def test_rows_anywhere_in_an_answer_become_a_count():
    env = {switches.NO_ROW_VALUES: "1"}
    text = json.dumps({"table": "t", "columns": ["a"], "rows": [{"a": "secret"}, {"a": "other"}], "nested": {"rows": [[1, 2]]}})
    out = json.loads(switches.answer(text, environ=env))
    assert out == {"table": "t", "columns": ["a"], "rows": {"count": 2, "values": switches.REMOVED},
                   "nested": {"rows": {"count": 1, "values": switches.REMOVED}}}


# ------------------------------------------------------------------ where the switches are said ------------------------

def test_the_switches_are_named_in_the_listing_llms_and_the_docs():
    from fabric_backend import mcp_server
    for text in (server.mcp.instructions, mcp_server.INSTRUCTIONS, discovery.llms_txt()):
        assert switches.SENTENCE in text
    docs = (ROOT / "fabric_backend" / "page_templates" / "DOCS.md").read_text(encoding="utf-8")
    hosting = docs[docs.index("## Hosting and permissions"):docs.index("### Cold start")]
    assert "`KRUSGRAPH_READ_ONLY=1` leaves out the tools that create or change something in Fabric" in hosting
    assert "`KRUSGRAPH_NO_ROW_VALUES=1` leaves out `sample_rows` and removes row values" in hosting
    register = (ROOT / "docs" / "RISK-REGISTER.md").read_text(encoding="utf-8")
    r3 = register[register.index("## R3"):register.index("## R4")]
    assert "KRUSGRAPH_READ_ONLY" in r3 and "Täcker inte" in r3


@pytest.mark.parametrize("env, said", [({}, "default"), ({switches.READ_ONLY: "1"}, "read-only"),
                                       ({switches.NO_ROW_VALUES: "1"}, "no-row-values"),
                                       ({switches.READ_ONLY: "1", switches.NO_ROW_VALUES: "1"}, "read-only, no-row-values")])
def test_healthz_says_the_mode(monkeypatch, env, said):
    from starlette.testclient import TestClient
    for s in SETTINGS:
        monkeypatch.delenv(s, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with TestClient(server.build_app()) as client:
        body = client.get("/healthz").json()
    assert body["ok"] is True and body["mode"] == said
