"""DIR1 (20 November 2026): every hosted tool run once on a synthetic data set, the way the hosted server registers it
with the cards on, and the size of each answer measured.

The Claude connector directory's review asks that responses are "reasonably sized for the task" and that every tool
returns a successful response for valid input (claude.com/docs/connectors/building/review-criteria, read 20 Nov 2026).
This tool runs the 48 hosted tools on three synthetic data sets with a fake Fabric (only the outer seams are replaced:
the Fabric REST readers, the SQL endpoint, the tokens; a POST, PATCH, PUT or DELETE fails the run):

- `sap`: the small SAP order-to-cash demo (fabric_backend/sap_demo.py, 17 tables with rows);
- `sap36`: the larger SAP demo (fabric_backend/sap_demo36.py, the same 17 tables, 36 months of rows);
- `wwi`: the 33-table WideWorldImporters schema (tests/fixtures/schemas/wideworldimporters.json; empty tables, so the
  answers are as wide as a 33-table plan makes them).

    python tools/directory_measure.py               # a table: tool, data set, bytes, ok or the error kind
    python tools/directory_measure.py --json out.json

The size of an answer is what a host receives: the text contents plus the structuredContent as compact JSON. Nothing
here reaches Fabric; no AI is involved. tests/test_dir1_directory_readiness.py runs the same harness.
"""
from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ITEM = {"id": "aaaaaaaa-0000-0000-0000-0000000000a1", "displayName": "demo_lh", "type": "Lakehouse", "schemas_enabled": True}
API = {"id": "bbbbbbbb-0000-0000-0000-0000000000b2", "displayName": "demo_api", "type": "GraphQLApi"}
QVS = ROOT / "tests" / "fixtures" / "q1" / "sales.qvs"


class _Response:
    ok, headers, status_code = True, {}, 200

    def __init__(self, body=None):
        self._body = body if body is not None else {"value": []}
        self.text = json.dumps(self._body)
        self.content = self.text.encode()

    def json(self):
        return self._body

    def raise_for_status(self):
        return None


def _get(url, *a, **k):
    if f"/lakehouses/{ITEM['id']}" in str(url) and str(url).rstrip("/").endswith(ITEM["id"]):
        return _Response({**ITEM, "properties": {"defaultSchema": "dbo", "sqlEndpointProperties": {
            "id": "ep-1", "connectionString": "demo.datawarehouse.fabric.microsoft.com", "provisioningStatus": "Success"}}})
    return _Response()


def data_set(name: str):
    """(Schema, execute) for a data set: sap, sap36 or wwi."""
    from fabric_backend import sap_demo, sap_demo36
    if name == "sap":
        return sap_demo.sqlite(schema="dbo")
    if name == "sap36":
        return sap_demo36.sqlite(schema="dbo")
    if name == "wwi":
        import sqlite3

        from fabric_backend.dialects import sqlite_sql
        from fabric_backend.schema import Schema
        fx = json.loads((ROOT / "tests" / "fixtures" / "schemas" / "wideworldimporters.json").read_text(encoding="utf-8"))
        con = sqlite3.connect(":memory:", check_same_thread=False)
        con.execute("ATTACH DATABASE ':memory:' AS dbo")
        rows = []
        for t in fx["tables"]:
            con.execute(f"CREATE TABLE dbo.[{t['name']}] ({', '.join(f'[{c}]' for c, _ in t['columns'])})")
            rows += [("dbo", t["name"], c, typ, i) for i, (c, typ) in enumerate(t["columns"], 1)]

        def execute(sql: str):
            cur = con.execute(sqlite_sql(sql))
            names = [d[0] for d in cur.description]
            return [dict(zip(names, r)) for r in cur.fetchall()]
        return Schema.from_information_schema(rows, schema="dbo"), execute
    raise ValueError(f"unknown data set {name!r}: sap, sap36 or wwi")


@contextmanager
def fake_fabric(name: str = "sap"):
    """The hosted server's seams replaced for one data set; restored on exit. Yields the Schema."""
    import pytest
    import requests

    from fabric_backend import server
    from concurrent.futures import ThreadPoolExecutor
    db = ThreadPoolExecutor(max_workers=1)                  # SQLite answers only in the thread that opened it
    schema, raw = db.submit(data_set, name).result()

    def execute(sql, *a, **k):
        return db.submit(raw, sql, *a, **k).result()

    def no_write(*a, **k):
        raise AssertionError(f"DIR1: a write was attempted: {a[:1]}")
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(requests, "get", _get)
        for verb in ("post", "patch", "put", "delete"):
            mp.setattr(requests, verb, no_write)
        mp.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
        mp.setattr(server.auth, "sql", lambda ctx: "sql-token")
        mp.setattr(server, "limiter", None)
        mp.setattr(server, "_workspaces", lambda headers: [{"id": "w-demo", "name": "demo", "capacity_id": "cap-1"}])
        mp.setattr(server, "_workspace_hints", lambda ids, headers: {"w-demo": "1 lakehouse"})
        mp.setattr(server, "_workspace_id", lambda workspace, headers: "w-demo")
        mp.setattr(server, "_resolve_source", lambda workspace, source, headers: dict(ITEM))
        mp.setattr(server, "_execute_factory", lambda item, token: execute)
        mp.setattr(server, "_item_names", lambda workspace, ctx: [])
        mp.setattr(server, "_source_schemas", lambda workspace, source, ctx: [{"schema": "dbo", "tables": len(schema)}])
        mp.setattr(server._fabric.PLATFORM, "read_schema", lambda ex, n: schema)
        yield schema
    finally:
        mp.undo()
        db.shutdown(wait=False)


def calls(schema, data: str) -> list[tuple[str, dict]]:
    """One valid call per hosted tool on the data set (every creating tool as its default dry run)."""
    ws = {"workspace": "demo", "source": "demo_lh", "schema": "dbo"}
    tables = [t.name for t in schema]
    if data.startswith("sap"):
        a, b, fact = "sap_vbak", "sap_kna1", "sap_vbap"
        question, q_tables = "revenue per customer", ["sap_vbak", "sap_kna1"]
    else:
        a, b, fact = "Orders", "Customers", "OrderLines"
        question, q_tables = "orders per customer", ["Orders", "Customers"]
    a = a if a in tables else tables[0]
    b = b if b in tables else tables[1]
    fact = fact if fact in tables else tables[2]
    script = QVS.read_text(encoding="utf-8") if QVS.exists() else "Orders: LOAD OrderID, CustomerID FROM orders.qvd (qvd);"
    out = [
        ("start", {}), ("start", {"sample": True}), ("start", {**ws, "step": "map"}), ("start", {**ws, "step": "check"}),
        ("start", {**ws, "step": "dry_run"}),
        ("list_workspaces", {}), ("list_sources", {"workspace": "demo"}), ("list_tables", ws),
        ("plan_backend", ws), ("plan_backend", {**ws, "detail": "full"}), ("validate_plan", ws),
        ("validate_plan", {**ws, "detail": "full"}), ("review_plan", ws), ("sample_rows", {**ws, "table": a}),
        ("create_backend", {**ws, "name": "demo_api"}), ("rayfin_connector", ws), ("ontology_draft", ws),
        ("create_ontology", {**ws, "name": "demo_ontology"}), ("semantic_model_draft", ws),
        ("compare_semantic_model", {**ws, "tmdl": TMDL}), ("join_path", {**ws, "start": a, "end": b}),
        ("analyze_schema", ws), ("suggest_relationships", ws), ("data_dictionary", ws), ("dbt_schema", ws),
        ("dbt_schema", {**ws, "project": True}), ("domain_draft", ws), ("sap_pack_draft", ws),
        ("plan_drift", {**ws, "api": "demo_api"}), ("create_semantic_model", {**ws, "name": "demo_model"}),
        ("create_report", {"workspace": "demo", "model": "demo_model", "name": "demo_report"}),
        ("create_views", ws), ("create_data_agent", {**ws, "name": "demo_agent"}), ("analysis_plan", ws),
        ("analysis_notebook_draft", {**ws, "analysis": "A7"}),
        ("requirements_draft", {"requirements": "Revenue per customer per month\nOpen orders not yet invoiced", **ws}),
        ("silver_notebook_draft", ws), ("create_silver_notebook", {**ws, "name": "demo_silver"}), ("gold_views_draft", ws),
        ("create_gold_views", {**ws, "name": "demo_gold"}), ("drift_monitor_draft", ws),
        ("create_drift_monitor", {**ws, "name": "demo_drift"}), ("create_pipeline", {**ws, "name": "demo_pipeline"}),
        ("export_item_definitions", ws), ("verify_build", {**ws, "items": {"semantic_model": "demo_model"}}),
        ("app_starter", {"workspace": "demo", "api": "demo_api"}), ("app_readiness", {"workspace": "demo", "api": "demo_api"}),
        ("lineage", ws), ("describe_backend", {"workspace": "demo", "api": "demo_api"}),
        ("answer_query_draft", {**ws, "question": question, "tables": q_tables}),
        ("query_graphql", {"workspace": "demo", "api": "demo_api", "query": "{ __typename }"}),
        ("publish_catalog", ws), ("qlik_plan", {"script": script}),
        ("qlik_measures_draft", {"measures": [{"name": "Sales", "expression": "Sum(Sales)"},
                                                {"name": "Orders", "expression": "Count(DISTINCT OrderID)"}]}),
        ("qlik_reconcile_draft", {"script": script, "kpis": [{"name": "Sales", "expression": "Sum(Sales)", "value": 1000}]}),
    ]
    return out


TMDL = "<the parts of semantic_model_draft on the same data>"
# Expected refusals on a data set: the data cannot support the call, and the answer says why (kind bad_input). The small
# SAP demo covers a few days, so no analysis is ready on it; the 36-month demo is where analysis_notebook_draft succeeds.
REFUSED = {("sap", "analysis_notebook_draft"), ("wwi", "analysis_notebook_draft")}
# Tools that read an API for GraphQL or a semantic model in Fabric: the fake Fabric has none, so they answer not_found.
# They ran against the live demo workspace (fabric_backend/tool_status.py).
NEEDS_ITEM = ("plan_drift", "create_report", "app_starter", "app_readiness", "describe_backend", "query_graphql")


def run(name: str, arguments: dict) -> dict:
    """One call as the hosted server registers it (cards on): {bytes, text_bytes, structured_bytes, error, kind, result}."""
    from fabric_backend import mcp_apps, server
    if arguments.get("tmdl") == TMDL:
        arguments = {**arguments, "tmdl": json.loads(server.semantic_model_draft(
            **{k: arguments[k] for k in ("workspace", "source", "schema")}))["parts"]}
    fn = mcp_apps.structured(getattr(server, name), name)
    r = fn(**arguments)
    if isinstance(r, str):
        texts, sc = [r], None
    else:
        texts, sc = [c.text for c in r.content], r.structured_content
    tb = sum(len(t.encode("utf-8")) for t in texts)
    sb = len(json.dumps(sc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")) if sc is not None else 0
    answer = None
    try:
        answer = json.loads(texts[-1])
    except (ValueError, IndexError):
        pass
    err = answer.get("error") if isinstance(answer, dict) else None
    kind = answer.get("kind") if isinstance(answer, dict) else None
    return {"bytes": tb + sb, "text_bytes": tb, "structured_bytes": sb, "error": err, "kind": kind, "texts": texts,
            "structured": sc}


def measure(data_sets=("sap", "sap36", "wwi")) -> list[dict]:
    import os
    os.environ.setdefault("KRUSGRAPH_MCP_APPS", "1")
    out = []
    for data in data_sets:
        with fake_fabric(data) as schema:
            for name, args in calls(schema, data):
                try:
                    r = run(name, args)
                except Exception as e:                       # noqa: BLE001 - recorded, the run goes on
                    r = {"bytes": 0, "text_bytes": 0, "structured_bytes": 0, "error": f"raised {type(e).__name__}: {e}"[:300],
                         "kind": "raised"}
                out.append({"data": data, "tool": name, "arguments": sorted(args), **{k: r[k] for k in
                            ("bytes", "text_bytes", "structured_bytes", "error", "kind")}})
    return out


def main(argv: list[str]) -> int:
    import logging
    logging.disable(logging.CRITICAL)
    rows = measure()
    if "--json" in argv:
        Path(argv[argv.index("--json") + 1]).write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    for r in sorted(rows, key=lambda r: -r["bytes"]):
        state = "ok" if not r["error"] else f"{r['kind']}: {str(r['error'])[:90]}"
        print(f"{r['bytes']:>9}  {r['data']:<6} {r['tool']:<26} {','.join(r['arguments'])[:40]:<40} {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
