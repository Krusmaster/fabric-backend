"""The lineage graph as OpenLineage events (LANDSCAPE idea 4, round n125).

Written from the OpenLineage specification, no code copied: OpenLineage.json 2-0-2 (RunEvent, Run, Job, InputDataset,
OutputDataset, BaseFacet), the facets SchemaDatasetFacet 1-2-0, JobTypeJobFacet 2-0-4 and DocumentationJobFacet 1-1-0,
read at commit 6e9fd64478313b77884dd578cae94a1d9d32bc9a of github.com/OpenLineage/OpenLineage (Apache-2.0), and the
naming conventions in docs/spec/naming.md at commit e3199c2aab03e06e59c46ba5768f94e24fa68305 of
github.com/OpenLineage/docs, both read on 6 November 2026. The schema files are vendored as test fixtures in
tests/fixtures/openlineage/ and the tests validate every event against them.

One RunEvent (eventType COMPLETE) per object that builds on the source: a GraphQL API, a semantic model, a view or a
data agent, whether Krusgraph created it ("Created by Krusgraph" in the item's description) or found it.

  inputs    the source's tables the object reads. Fabric's SQL analytics endpoint speaks TDS, and the naming table has
            no Fabric row, so the SQL Server form of its Azure Synapse row is used: namespace sqlserver://{host}:1433.
            One endpoint host serves every lakehouse and warehouse of a workspace, so the name carries the database
            in front of Synapse's {schema}.{table}: {database}.{schema}.{table}. The facet `schema` lists column names
            and types only.
  outputs   a view is a dataset on the same endpoint ({database}.{view schema}.{view}); a GraphQL API, a semantic model
            and a data agent are not datasets in the naming table, so they are jobs with inputs and no outputs.
  job       namespace fabric://{workspace id}, name {kind}.{object name}; facets jobType (integration KRUSGRAPH),
            documentation, and the custom facet `krusgraph`: whether Krusgraph created the item, the edges as read
            (via, certain), and for each relationship between two of the job's input tables that validate_plan's
            counts checked, its rule (R0..R5, pack, confirmed) and counts (rows with a value, orphans, verdict).

No row value appears anywhere: names, types, rules and counts. The run id is a UUID derived from the job and its
inputs (uuid5), so the same graph gives the same JSON; only eventTime, which the caller passes, changes between calls.
"""
from __future__ import annotations

import uuid

SPEC = "https://openlineage.io/spec/2-0-2/OpenLineage.json"
SCHEMA_FACET = "https://openlineage.io/spec/facets/1-2-0/SchemaDatasetFacet.json#/$defs/SchemaDatasetFacet"
JOB_TYPE_FACET = "https://openlineage.io/spec/facets/2-0-4/JobTypeJobFacet.json#/$defs/JobTypeJobFacet"
DOC_FACET = "https://openlineage.io/spec/facets/1-1-0/DocumentationJobFacet.json#/$defs/DocumentationJobFacet"
PRODUCER = "https://github.com/Krusmaster/fabric-backend"
KRUSGRAPH_FACET = f"{PRODUCER}/blob/main/fabric_backend/openlineage_krusgraph_facet.json"
_RUN_NS = uuid.UUID("6f1c3a52-9e0b-4d55-8a3e-125b0a5e0125")       # uuid5 namespace for run ids (any fixed UUID)

_JOB_TYPE = {"graphql_api": "GRAPHQL_API", "semantic_model": "SEMANTIC_MODEL", "view": "VIEW", "data_agent": "DATA_AGENT"}
_WORDS = {"graphql_api": "API for GraphQL", "semantic_model": "semantic model", "view": "view on the SQL analytics endpoint",
          "data_agent": "data agent"}
CREATED_MARK = "created by krusgraph"


def _host(sql_host: str | None) -> str:
    h = (sql_host or "").strip()
    for p in ("tcp:", "Server=", "server="):
        h = h[len(p):] if h.startswith(p) else h
    h = h.split(";")[0].split(",")[0].strip()
    return h or "unknown-host"


def dataset_namespace(sql_host: str | None) -> str:
    """sqlserver://{host}:1433 (the naming table's Azure Synapse row; Fabric's endpoint listens on 1433)."""
    return f"sqlserver://{_host(sql_host)}:1433"


def dataset_name(database: str, schema: str, table: str) -> str:
    return f"{database}.{schema}.{table}"


def _facet(url: str, **body) -> dict:
    return {"_producer": PRODUCER, "_schemaURL": url, **body}


def _schema_facet(table) -> dict:
    """Column names and types only (SchemaDatasetFacet fields: name, type, ordinal_position)."""
    return _facet(SCHEMA_FACET, fields=[{"name": c.name, "type": c.data_type, "ordinal_position": i}
                                        for i, c in enumerate(table.columns, 1)])


def events(graph: dict, schema_obj, workspace_id: str, source: dict, *, event_time: str,
           created_ids: set[str] | None = None, checks: list[dict] | None = None) -> list[dict]:
    """RunEvents for lineage.graph()'s answer. schema_obj: the source's tables (schema.Schema); source: the resolved item
    (sql_host, sql_db, displayName); created_ids: the item ids whose description says Krusgraph created them; checks:
    validate_plan's relationships (evidence.validate()["relationships"]), counts only."""
    schema = graph["source"]["schema"]
    database = source.get("sql_db") or source.get("displayName") or graph["source"].get("name") or "unknown"
    ns = dataset_namespace(source.get("sql_host"))
    tables = {t.name: t for t in schema_obj}
    created_ids = created_ids or set()
    by_object: dict[str, list[dict]] = {}
    for e in graph["edges"]:
        by_object.setdefault(e["to"], []).append(e)
    nodes = {n["id"]: n for n in graph["nodes"]}
    out = []
    for node_id in sorted(by_object):
        node, edges = nodes[node_id], sorted(by_object[node_id], key=lambda e: e["from"])
        kind, name = node["kind"], node["name"]
        used = sorted({e["from"].split(":", 1)[1] for e in edges})
        inputs = [{"namespace": ns, "name": dataset_name(database, schema, t),
                   "facets": {"schema": _schema_facet(tables[t])} if t in tables else {}} for t in used]
        outputs = []
        if kind == "view":
            v_schema, _, v_name = name.rpartition(".")
            outputs = [{"namespace": ns, "name": dataset_name(database, v_schema or schema, v_name), "facets": {}}]
        rels = [{"from": f"{r['source']}.{','.join(r['columns'])}", "to": f"{r['target']}.{','.join(r['target_columns'])}",
                 "rule": r["rule"], "rows_with_value": r.get("rows_with_value"), "orphans": r.get("orphans"),
                 "verdict": r.get("verdict")}
                for r in (checks or []) if r["source"] in used and r["target"] in used]
        created = node.get("item_id") in created_ids
        job = {"namespace": f"fabric://{workspace_id}", "name": f"{kind}.{name}", "facets": {
            "jobType": _facet(JOB_TYPE_FACET, processingType="BATCH", integration="KRUSGRAPH", jobType=_JOB_TYPE.get(kind, kind.upper())),
            "documentation": _facet(DOC_FACET, description=(
                f"{_WORDS.get(kind, kind)} {name} over {len(used)} table(s) of {graph['source'].get('name')} ({schema}); "
                + ("created by Krusgraph" if created else "found in the workspace") + ". Read by Krusgraph's lineage tool.")),
            "krusgraph": _facet(KRUSGRAPH_FACET, created_by_krusgraph=created, item_id=node.get("item_id"), kind=kind,
                                edges=[{"table": e["from"].split(":", 1)[1], "via": e["via"], "certain": e["certain"]} for e in edges],
                                relationships=rels)}}
        run_id = str(uuid.uuid5(_RUN_NS, "|".join([job["namespace"], job["name"], ns, *used])))
        out.append({"eventType": "COMPLETE", "eventTime": event_time, "producer": PRODUCER, "schemaURL": f"{SPEC}#/$defs/RunEvent",
                    "run": {"runId": run_id, "facets": {}}, "job": job, "inputs": inputs, "outputs": outputs})
    return out


def created_ids(items: list[dict]) -> set[str]:
    """Ids of workspace items whose description says Krusgraph created them (the create_* tools write that)."""
    return {it.get("id") for it in items if CREATED_MARK in (it.get("description") or "").lower()}


def answer(graph: dict, evs: list[dict], checked: bool) -> dict:
    return {"format": "openlineage", "spec": SPEC, "events": evs, "summary": graph["summary"],
            "skipped": graph.get("skipped", []),
            "note": ("One OpenLineage RunEvent per object that builds on the source, ready to POST one by one to a catalog's "
                     "OpenLineage endpoint; Krusgraph sends nothing itself. Datasets: namespace sqlserver://{host}:1433, "
                     "name {database}.{schema}.{table}; schema facets carry column names and types, never a row value. "
                     + ("Relationship counts come from validate_plan's counting queries in this call."
                        if checked else "No relationship was counted in this call."))}
