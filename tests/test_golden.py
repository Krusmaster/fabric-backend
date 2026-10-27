"""Golden answers: what the engine and every tool answer today, byte for byte, stored in tests/golden/.

Written before the platform adapters (round n13) moved code, so that move could be shown not to change a single
answer: the files in tests/golden/ were committed first and are unchanged by the move. They cover

- the engine on the synthetic shop schema and on every benchmark fixture in tests/fixtures/schemas (plan, graph
  analysis, join paths, counting SQL, dictionary, dbt, views, semantic model, GraphQL definition, Rayfin, ontology,
  silver and gold drafts),
- every tool of the hosted server, called the way Claude calls it, against a Fabric workspace answered from memory
  and an SQL endpoint backed by SQLite (tests/golden_support.py: the doubles sit at `requests` and `pyodbc`),
- every tool of the local stdio server over the same SQLite-backed ODBC connection,
- the tool listings (names, titles, annotations, parameters, descriptions) and the hosted server's instructions.

A deliberate change to an answer is made by regenerating: `KRUSGRAPH_UPDATE_GOLDEN=1 python -m pytest tests/test_golden.py`,
and the diff of tests/golden/ is then part of the commit that changes the answer, where a reviewer sees it.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

import golden_support as gs
from fabric_backend import seed
from fabric_backend.infer import plan

from fabric_backend import server as _server

GOLDEN = Path(__file__).parent / "golden"
_REAL_EXISTING_API = _server._existing_api          # tests/conftest.py stubs the guard out; the golden answers keep it
UPDATE = os.environ.get("KRUSGRAPH_UPDATE_GOLDEN") == "1"
FIXTURES = Path(__file__).parent / "fixtures" / "schemas"
BENCHMARKS = ("northwind", "chinook", "tpch", "adventureworks", "sakila", "wideworldimporters", "wideworldimportersdw",
              "nordic_sv", "nordic_de", "dw_names", "app_names")


def check(name: str, value) -> None:
    """Compare with tests/golden/<name>.json, entry by entry so a failure names what changed."""
    path = GOLDEN / f"{name}.json"
    text = json.dumps(value, indent=1, sort_keys=True, default=str, ensure_ascii=False) + "\n"
    if UPDATE:
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    assert path.exists(), f"no golden file {path.name}: run with KRUSGRAPH_UPDATE_GOLDEN=1 once"
    want = json.loads(path.read_text(encoding="utf-8"))
    got = json.loads(text)
    if isinstance(want, dict) and isinstance(got, dict):
        assert sorted(got) == sorted(want), f"{name}: entries differ"
        for k in want:
            assert got[k] == want[k], f"{name}: {k!r} differs from the golden answer"
    assert got == want


def _try(fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception as e:  # noqa: BLE001 — an engine refusal is part of today's answer too
        return {"raises": f"{type(e).__name__}: {e}"}


def plan_dict(p) -> dict:
    return {"summary": p.summary(), "mermaid": p.mermaid(), "keyless": p.keyless, "ambiguous": p.ambiguous,
            "synonyms": p.synonyms, "keys": {t: [c, r] for t, (c, r) in p.keys.items()},
            "relationships": [vars(r) for r in p.relationships]}


def engine_answers(s, schema: str) -> dict:
    from fabric_backend import dbt, dictionary, evidence, gold, graphs, ontology, paths, rayfin, semantic_model, silver, views
    from fabric_backend.graphql import decode, definition
    p = plan(s)
    names = [t.name for t in s]
    info = {"workspace_id": "ws-1", "item_id": "lh-1", "item_name": "src", "item_kind": "Lakehouse", "schema": schema,
            "sql_endpoint": "x.datawarehouse.fabric.microsoft.com", "sql_db": "src", "schemas_enabled": schema != "dbo",
            "sql_endpoint_id": "ep-1"}
    out = {
        "plan": plan_dict(p),
        "composite_key_suggestions": evidence.suggest_composite_keys(p),
        "analyze": _try(graphs.analyze, p),
        "candidates": _try(graphs.candidates, p),
        "join_paths": {f"{a}->{b}": _try(paths.join_path, p, a, b) for a in names[:3] for b in names if a != b},
        "key_sql": {t: evidence.key_sql(schema, t, c) for t, (c, _) in p.keys.items()},
        "relationship_sql": [evidence.relationship_sql(schema, r.source, r.source_cols, r.target, r.target_cols) for r in p.relationships],
        "sample_sql": {t.name: evidence.sample_sql(schema, t.name, t.column_names, 10, {c.name: c.data_type for c in t.columns}) for t in s},
        "dictionary": _try(dictionary.data_dictionary, p, "src", schema),
        "dbt": _try(dbt.schema_yml, p, "src", schema),
        "views": _try(views.statements, p, "krusgraph"),
        "semantic_model": _try(semantic_model.draft, p, info, "model"),
        "graphql": _try(lambda: decode(definition(p, "api", "ws-1", "ep-1", "SqlAnalyticsEndpoint"))),
        "rayfin": _try(rayfin.rayfin_files, p, "data"),
        "ontology_ttl": _try(ontology.ontology_ttl, p, "onto", schema),
        "silver": _try(lambda: silver.notebook_source(silver.spec(p, info))),
        "gold": _try(lambda: gold.statements(gold.spec(p, info))),
    }
    return out


def digest_large(answers: dict, limit: int = 20000) -> dict:
    """The benchmark schemas are large: an entry over `limit` bytes is kept as its SHA-256 and length, so a change still
    fails the test while the repository does not carry megabytes of generated text (the shop schema is kept whole)."""
    import hashlib
    out = {}
    for k, v in answers.items():
        text = json.dumps(v, sort_keys=True, default=str, ensure_ascii=False)
        out[k] = v if len(text) <= limit else {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "bytes": len(text)}
    return out


def test_engine_answers_on_the_shop_schema():
    check("engine_shop", engine_answers(seed.schema("shop"), "shop"))
    s = seed.schema("shop")
    check("engine_shop_confirmed", plan_dict(plan(s, keys={"order_items": ["order_id", "line_no"]}, confirmed=[gs.SHIP_TO])))


@pytest.mark.parametrize("name", BENCHMARKS)
def test_engine_answers_on_the_benchmark_fixtures(name):
    from fabric_backend.schema import Schema
    fx = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    rows = [("dbo", t["name"], col, typ, i) for t in fx["tables"] for i, (col, typ) in enumerate(t["columns"], 1)]
    check(f"engine_{name}", digest_large(engine_answers(Schema.from_information_schema(rows, schema="dbo"), "dbo")))


def test_validation_and_suggestions_on_the_shop_rows():
    from fabric_backend import evidence, graphs
    db = gs.shop_database()

    def execute(sql):
        cur = db.execute(gs._sqlite(sql))
        return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    p = plan(seed.schema("shop"))
    check("engine_shop_rows", {"validate": evidence.validate(p, execute), "suggest": graphs.suggest(p, execute)})


# ------------------------------------------------------------------ the hosted server ------------------------------

RECORDED_ON = (2026, 10, 26)         # the day the golden answers were made; the drift monitor's schedule starts the next day


@pytest.fixture
def fabric(monkeypatch):
    """The hosted server against the workspace in golden_support: Fabric REST and the SQL endpoint, nothing else mocked
    but the two tokens the Auth object hands out, and the date the drift monitor's schedule counts from."""
    import datetime
    import requests
    from fabric_backend import monitor, server

    class RecordedDay(datetime.date):
        @classmethod
        def today(cls):
            return cls(*RECORDED_ON)
    monkeypatch.setattr(monitor, "date", RecordedDay)
    fake = gs.FakeFabric()
    for verb in ("get", "post", "patch"):
        monkeypatch.setattr(requests, verb, getattr(fake, verb))
    odbc = gs.fake_pyodbc()
    monkeypatch.setitem(sys.modules, "pyodbc", odbc)
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "limiter", None)
    monkeypatch.setattr(server, "_existing_api", _REAL_EXISTING_API)
    fake.odbc = odbc
    return fake


SRC = {"workspace": "demo", "source": "demo_lh", "schema": "shop"}
HOSTED_CALLS = [
    ("list_workspaces", {}),
    ("list_sources", {"workspace": "demo"}),
    ("list_sources", {"workspace": gs.WS}),
    ("list_sources", {"workspace": "nowhere"}),
    ("list_tables", SRC),
    ("list_tables", {**SRC, "detail": "summary", "tables": ["order*"]}),
    ("list_tables", {**SRC, "schema": "dbo"}),
    ("list_tables", {**SRC, "source": "missing_lh"}),
    ("plan_backend", SRC),
    ("plan_backend", {**SRC, "keys": {"order_items": ["order_id", "line_no"]}, "confirmed": [gs.SHIP_TO]}),
    ("plan_backend", {**SRC, "detail": "summary"}),
    ("plan_backend", {**SRC, "keys": {"orders": ["ghost"]}}),
    ("plan_backend", {"workspace": "demo", "source": "demo_wh", "schema": "shop"}),
    ("validate_plan", SRC),
    ("validate_plan", {"workspace": "demo", "source": "demo_wh", "schema": "shop"}),
    ("sample_rows", {**SRC, "table": "customers"}),
    ("sample_rows", {**SRC, "table": "customers", "n": 3, "show_personal_data": True}),
    ("sample_rows", {**SRC, "table": "ghost"}),
    ("create_backend", {**SRC, "name": "shop_api_v2"}),
    ("create_backend", {**SRC, "name": "shop_api"}),
    ("create_backend", {**SRC, "workspace": gs.WS, "name": "shop_api_v2"}),
    ("create_backend", {**SRC, "workspace": gs.WS, "name": "shop_api"}),
    ("create_backend", {**SRC, "workspace": gs.WS, "name": "shop_api", "confirmed": [gs.SHIP_TO]}),
    ("rayfin_connector", {**SRC, "connector": "shop"}),
    ("ontology_draft", SRC),
    ("create_ontology", {**SRC, "name": "shop_onto"}),
    ("semantic_model_draft", SRC),
    ("compare_semantic_model", {**SRC, "model": "shop_model"}),
    ("join_path", {**SRC, "start": "customers", "end": "categories"}),
    ("join_path", {**SRC, "start": "audit_log", "end": "customers"}),
    ("analyze_schema", SRC),
    ("suggest_relationships", SRC),
    ("data_dictionary", SRC),
    ("data_dictionary", {**SRC, "validate": True}),
    ("dbt_schema", SRC),
    ("plan_drift", {**SRC, "api": "shop_api"}),
    ("create_semantic_model", {**SRC, "name": "shop_model_v2"}),
    ("create_semantic_model", {**SRC, "name": "shop_model_v2", "dry_run": False}),
    ("create_views", SRC),
    ("create_views", {**SRC, "dry_run": False}),
    ("create_data_agent", {**SRC, "name": "shop_agent"}),
    ("silver_notebook_draft", SRC),
    ("create_silver_notebook", {**SRC, "name": "shop_silver"}),
    ("gold_views_draft", SRC),
    ("create_gold_views", {**SRC, "name": "shop_gold"}),
    ("drift_monitor_draft", SRC),
    ("create_drift_monitor", {**SRC, "name": "shop_drift"}),
    ("export_item_definitions", SRC),
    ("app_starter", {"workspace": "demo", "api": "shop_api"}),
    ("app_readiness", {"workspace": "demo", "api": "shop_api"}),
    ("lineage", SRC),
    ("lineage", {**SRC, "table": "orders"}),
    ("describe_backend", {"workspace": "demo", "api": "shop_api"}),
    ("answer_query_draft", {**SRC, "question": "Hur många ordrar per kund?", "tables": ["orders", "customers"]}),
    ("answer_query_draft", {**SRC, "question": "Revenue per category", "tables": ["order_items", "categories"], "api": "shop_api"}),
    ("query_graphql", {"workspace": "demo", "api": "shop_api", "query": "{ orders { items { order_id } } }"}),
    ("query_graphql", {"workspace": "demo", "api": "shop_api", "query": "mutation { x }"}),
]


def _answer(text: str):
    try:
        return json.loads(text)
    except ValueError:
        return text


def test_every_hosted_tool_answers_as_it_did(fabric):
    from fabric_backend import server
    out = []
    for name, kwargs in HOSTED_CALLS:
        before = len(fabric.calls)
        text = getattr(server, name)(**kwargs)
        out.append({"tool": name, "args": kwargs, "answer": _answer(text), "rest": fabric.calls[before:]})
    out.append({"created": fabric.created, "ddl": fabric.odbc.ddl, "dsns": sorted(set(fabric.odbc.dsns))})
    check("hosted_tools", out)


def _listing(mcp) -> list[dict]:
    """The tools as a client lists them. A description is a docstring, and Python 3.13 strips its indentation when it
    compiles while 3.12 (CI and the image) keeps it, so the description is compared after inspect.cleandoc."""
    import inspect
    tools = asyncio.run(mcp.list_tools())
    out = []
    for t in sorted(tools, key=lambda t: t.name):
        entry = json.loads(t.model_dump_json(exclude_none=True))
        if entry.get("description"):
            entry["description"] = inspect.cleandoc(entry["description"])
        out.append(entry)
    return out


def test_hosted_tool_listing_and_instructions_are_unchanged():
    from fabric_backend import server
    check("hosted_listing", {"tools": _listing(server.mcp), "instructions": server.mcp.instructions})


# ------------------------------------------------------------------ the local stdio server ------------------------

@pytest.fixture
def local(monkeypatch):
    import requests
    fake = gs.FakeFabric()
    for verb in ("get", "post", "patch"):
        monkeypatch.setattr(requests, verb, getattr(fake, verb))
    odbc = gs.fake_pyodbc()
    monkeypatch.setitem(sys.modules, "pyodbc", odbc)
    monkeypatch.setenv("FABRIC_ODBC", f"Driver={{ODBC Driver 18 for SQL Server}};Server={gs.SQL_HOST};Database=demo_lh;Authentication=ActiveDirectoryInteractive")
    monkeypatch.setenv("FABRIC_TOKEN", "fabric-token")
    for var in ("FABRIC_SOURCE_KIND", "FABRIC_SCHEMAS_ENABLED"):
        monkeypatch.delenv(var, raising=False)
    fake.odbc = odbc
    return fake


S = {"schema": "shop"}
LOCAL_CALLS = [
    ("list_tables", S),
    ("list_tables", {"schema": "dbo"}),
    ("plan_backend", S),
    ("plan_backend", {**S, "keys": {"order_items": ["order_id", "line_no"]}, "confirmed": [gs.SHIP_TO]}),
    ("plan_backend", {**S, "detail": "summary", "tables": ["order*"]}),
    ("validate_plan", S),
    ("sample_rows", {**S, "table": "customers"}),
    ("sample_rows", {**S, "table": "ghost"}),
    ("create_backend", {"workspace": gs.WS, "source": "demo_lh", "name": "shop_api_v2", **S, "dry_run": True}),
    ("create_backend", {"workspace": gs.WS, "source": "demo_lh", "name": "shop_api_v2", **S}),
    ("rayfin_connector", {**S, "connector": "shop"}),
    ("ontology_draft", S),
    ("semantic_model_draft", S),
    ("join_path", {**S, "start": "customers", "end": "categories"}),
    ("data_dictionary", S),
    ("data_dictionary", {**S, "validate": True}),
    ("dbt_schema", S),
    ("analyze_schema", S),
    ("suggest_relationships", S),
    ("create_views", S),
    ("create_views", {**S, "dry_run": False}),
    ("answer_query_draft", {**S, "question": "Hur många ordrar per kund?", "tables": ["orders", "customers"]}),
    ("silver_notebook_draft", S),
]


def test_every_local_tool_answers_as_it_did(local, monkeypatch):
    from fabric_backend import mcp_server
    out = []
    for name, kwargs in LOCAL_CALLS:
        before = len(local.calls)
        out.append({"tool": name, "args": kwargs, "answer": _answer(getattr(mcp_server, name)(**kwargs)), "rest": local.calls[before:]})
    monkeypatch.setenv("FABRIC_SOURCE_KIND", "SQLServer")                 # the Fabric-only drafts explain themselves
    for name in ("semantic_model_draft", "ontology_draft", "silver_notebook_draft"):
        out.append({"tool": name, "kind": "SQLServer", "answer": _answer(getattr(mcp_server, name)(**S))})
    monkeypatch.delenv("FABRIC_ODBC")
    out.append({"tool": "plan_backend", "no_odbc": True, "answer": _answer(mcp_server.plan_backend(**S))})
    out.append({"created": local.created, "ddl": local.odbc.ddl})
    check("local_tools", out)


def test_local_tool_listing_is_unchanged():
    """Tools may be added to the local server; the ones in the golden file keep their exact entry."""
    from fabric_backend import mcp_server
    now = {t["name"]: t for t in _listing(mcp_server.mcp)}
    path = GOLDEN / "local_listing.json"
    if UPDATE:
        check("local_listing", now)
        return
    want = json.loads(path.read_text(encoding="utf-8"))
    for name, entry in want.items():
        assert json.loads(json.dumps(now.get(name), default=str)) == entry, f"local tool {name} changed"


# ------------------------------------------------------------------ the 20-minute demo and the CLI ----------------

def test_demo_sources_answer_as_they_did(tmp_path):
    from fabric_backend import demo, demo_app
    folder = tmp_path / "files"
    folder.mkdir()
    (folder / "kunder.csv").write_text("kund_id;namn;ort\n1;Ett AB;Visby\n2;Två AB;Lund\n", encoding="utf-8")
    (folder / "ordrar.csv").write_text("order_id,kund_id,belopp,datum\n10,1,99.5,2026-10-01\n11,2,12,2026-10-02\n12,3,5,2026-10-03\n", encoding="utf-8")
    out = {"demo_plan": demo.demo_plan(), "demo_validation": demo.demo_validation()}
    for kind, value in (("sample", ""), ("folder", str(folder))):
        session = demo_app.Session()
        session.connect(kind, value)
        state = session.state()
        out[kind] = _no_clock(json.loads(json.dumps(state, default=str).replace(str(folder), "<folder>")))
    check("demo", out)


def _no_clock(v):
    """The demo's state carries wall-clock times (when a step was entered, now); they are not part of the answer."""
    if isinstance(v, dict):
        return {k: ("<time>" if k in ("entered", "now", "started") and v[k] is not None else _no_clock(x)) for k, x in v.items()}
    if isinstance(v, list):
        return [_no_clock(x) for x in v]
    return v


def test_cli_offline_outputs_are_unchanged(tmp_path, capsys, monkeypatch):
    from fabric_backend import cli
    cols = Path(__file__).parent.parent / "examples" / "columns.csv"
    monkeypatch.chdir(tmp_path)                                  # dictionary and dbt write their file into the working directory
    out = {}
    for args in (["plan", str(cols)], ["join-path", str(cols), "customers", "categories"], ["dictionary", str(cols)],
                 ["dbt", str(cols)], ["analyze", str(cols)], ["views", str(cols)]):
        try:
            code = cli.main(args)
        except SystemExit as e:
            code = e.code
        out[" ".join(args[:1] + args[2:])] = {"exit": code, "stdout": capsys.readouterr().out}
    out["files"] = {f.name: f.read_text(encoding="utf-8") for f in sorted(tmp_path.iterdir()) if f.is_file()}
    check("cli", out)
