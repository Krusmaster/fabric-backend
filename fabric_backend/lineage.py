"""Lineage: which Fabric objects build on a source's tables, and what is affected when a table changes.

Edges run from a table to the object that uses it ("used by"). Four kinds of objects, each read from where Fabric
keeps the truth about it:

  GraphQL API      graphql-definition.json (items/{id}/getDefinition): datasources[].sourceItemId names the source item,
                   objects[].sourceObject the "schema.table". Certain.
  semantic model   the TMDL definition (semanticModels/{id}/getDefinition?format=TMDL): each table's partition has
                   entityName and, for a schema-enabled source, schemaName; sourceLineageTag carries [schema].[table];
                   expressions.tmdl names the database the Direct Lake expression opens. Certain when the database or
                   the lineage tag names the source; "by table name" when only the entity name matches.
  view             INFORMATION_SCHEMA.VIEW_TABLE_USAGE on the source's SQL analytics endpoint (sys.sql_expression_dependencies
                   as the fallback): view -> table rows. Certain.
  data agent       the data agent's definition (dataAgents/{id}/getDefinition, part DataAgentV1.json). Its layout is
                   documented only in a Learn article this code could not read, so the part is searched as text for the
                   source item id and the table names: "named in the definition", not certain.

The parsers are pure: the server fetches and passes the bodies; the tests pass recorded ones. `workspace_edges()` and
the three `rest_*` readers at the end fetch them with a Fabric token; the server's lineage and plan_drift and the
nightly drift monitor notebook (monitor.py) use them, so the logic lives here once. Unit-tested, not yet run against a
live workspace.
"""
from __future__ import annotations

import json
import re

VIEW_USAGE_SQL = "SELECT VIEW_SCHEMA, VIEW_NAME, TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.VIEW_TABLE_USAGE"
VIEW_USAGE_SQL_SYS = ("SELECT s.name AS VIEW_SCHEMA, v.name AS VIEW_NAME, d.referenced_schema_name AS TABLE_SCHEMA, "
                      "d.referenced_entity_name AS TABLE_NAME FROM sys.sql_expression_dependencies d "
                      "JOIN sys.views v ON v.object_id = d.referencing_id JOIN sys.schemas s ON s.schema_id = v.schema_id")

_ENTITY = re.compile(r"^\s*entityName:\s*(.+?)\s*$", re.M)
_SCHEMA = re.compile(r"^\s*schemaName:\s*(.+?)\s*$", re.M)
_LINEAGE = re.compile(r"^\s*sourceLineageTag:\s*\[(.+?)\]\.\[(.+?)\]\s*$", re.M)
_TABLE = re.compile(r"^table\s+(?:'((?:[^']|'')+)'|(\S+))", re.M)
_SQL_DATABASE = re.compile(r'Sql\.Database\(\s*"([^"]*)"\s*,\s*"([^"]*)"')


def _unquote(name: str) -> str:
    name = name.strip()
    if len(name) >= 2 and name[0] == name[-1] == "'":
        return name[1:-1].replace("''", "'")
    return name


def edge(table: str, kind: str, name: str, item_id: str, via: str, certain: bool = True) -> dict:
    return {"table": table, "kind": kind, "object": name, "id": item_id, "via": via, "certain": certain}


def from_graphql_definition(body: dict, item: dict, source_id, schema: str, tables: set[str]) -> list[dict]:
    """objects whose datasource is the source item (or any, when the id is unknown) and whose sourceObject is one of our
    tables. `source_id` is one id or a set: an API over a lakehouse names the lakehouse's SQL analytics endpoint, so
    the caller passes both the lakehouse's id and its endpoint's."""
    out = []
    lower = {t.lower(): t for t in tables}
    ids = set(source_id) if isinstance(source_id, (set, frozenset, list, tuple)) else ({source_id} if source_id else set())
    for ds in body.get("datasources", []):
        if ids and ds.get("sourceItemId") and ds["sourceItemId"] not in ids:
            continue
        for o in ds.get("objects", []):
            so = str(o.get("sourceObject", ""))
            sch, _, tab = so.rpartition(".")
            if sch and sch.lower() != schema.lower():
                continue
            if tab.lower() in lower:
                out.append(edge(lower[tab.lower()], "graphql_api", item.get("displayName", ""), item.get("id", ""),
                                f"type {o.get('graphqlType')} in graphql-definition.json"))
    return out


def from_tmdl_parts(parts: dict[str, str], item: dict, database_names: set[str], schema: str, tables: set[str]) -> list[dict]:
    """Direct Lake tables of a semantic model that read our tables."""
    lower = {t.lower(): t for t in tables}
    dbs = {d.lower() for d in database_names if d}
    opened = [m.group(2).lower() for m in _SQL_DATABASE.finditer(parts.get("definition/expressions.tmdl", ""))]
    database_matches = any(d in dbs for d in opened)
    out = []
    for path, text in parts.items():
        if not path.startswith("definition/tables/") or not path.endswith(".tmdl"):
            continue
        heading = _TABLE.search(text)
        model_table = _unquote(heading.group(1) or heading.group(2)) if heading else path.rsplit("/", 1)[-1][:-5]
        entity = _ENTITY.search(text)
        lineage = _LINEAGE.search(text)
        sch = _SCHEMA.search(text)
        table = None
        certain = False
        if lineage and lineage.group(1).lower() == schema.lower() and lineage.group(2).lower() in lower:
            table, certain = lower[lineage.group(2).lower()], True
        elif entity and _unquote(entity.group(1)).lower() in lower:
            if sch and _unquote(sch.group(1)).lower() != schema.lower():
                continue
            table, certain = lower[_unquote(entity.group(1)).lower()], bool(database_matches or (sch and _unquote(sch.group(1)).lower() == schema.lower()))
        if table:
            via = f"Direct Lake partition of table {model_table}" + ("" if certain else " (matched by table name only)")
            out.append(edge(table, "semantic_model", item.get("displayName", ""), item.get("id", ""), via, certain))
    return out


def from_view_rows(rows, item: dict, schema: str, tables: set[str]) -> list[dict]:
    """INFORMATION_SCHEMA.VIEW_TABLE_USAGE rows (dicts or tuples: view schema, view name, table schema, table name)."""
    lower = {t.lower(): t for t in tables}
    out = []
    for r in rows:
        if hasattr(r, "keys"):
            d = {k.lower(): r[k] for k in r.keys()}
            vs, vn, ts, tn = d.get("view_schema"), d.get("view_name"), d.get("table_schema"), d.get("table_name")
        else:
            vs, vn, ts, tn = (list(r) + [None] * 4)[:4]
        if ts and str(ts).lower() != schema.lower():
            continue
        if tn and str(tn).lower() in lower:
            out.append(edge(lower[str(tn).lower()], "view", f"{vs}.{vn}", item.get("id", ""), "INFORMATION_SCHEMA.VIEW_TABLE_USAGE"))
    return out


def from_data_agent_parts(parts: dict[str, str], item: dict, source_id: str | None, schema: str, tables: set[str]) -> list[dict]:
    """The agent's definition searched as text: tables named next to the source item are reported, not certain."""
    text = "\n".join(v for k, v in parts.items() if not k.startswith("."))
    if source_id and source_id not in text:
        return []
    out = []
    for t in sorted(tables):
        pattern = re.compile(r'["\'`\[\.]' + re.escape(t) + r'["\'`\]\b]', re.I)
        if pattern.search(text):
            out.append(edge(t, "data_agent", item.get("displayName", ""), item.get("id", ""), "named in the agent's definition", certain=False))
    return out


def graph(source: dict, schema: str, tables: list[str], edges: list[dict], skipped: list[dict] | None = None) -> dict:
    """Nodes (tables and objects), edges (table -> object), used_by per table, unused tables, and a summary."""
    nodes = [{"id": f"table:{t}", "kind": "table", "name": f"{schema}.{t}"} for t in tables]
    seen = set()
    for e in edges:
        key = (e["kind"], e["object"], e["id"])
        if key not in seen:
            seen.add(key)
            nodes.append({"id": f"{e['kind']}:{e['object']}", "kind": e["kind"], "name": e["object"], "item_id": e["id"]})
    used_by: dict[str, list[dict]] = {t: [] for t in tables}
    for e in edges:
        entry = {"kind": e["kind"], "object": e["object"], "via": e["via"], "certain": e["certain"]}
        if entry not in used_by.setdefault(e["table"], []):
            used_by[e["table"]].append(entry)
    unused = [t for t in tables if not used_by.get(t)]
    kinds = {}
    for e in edges:
        kinds.setdefault(e["kind"], set()).add(e["object"])
    summary = (f"{len(tables)} tables in {source.get('displayName') or source.get('name') or 'the source'}; "
               + (", ".join(f"{len(v)} {k.replace('_', ' ')}(s)" for k, v in sorted(kinds.items())) or "no object builds on them")
               + f"; {len(unused)} table(s) used by nothing")
    return {"source": {"name": source.get("displayName") or source.get("name"), "id": source.get("id"), "type": source.get("type"), "schema": schema},
            "nodes": nodes, "edges": [{"from": f"table:{e['table']}", "to": f"{e['kind']}:{e['object']}", "via": e["via"], "certain": e["certain"]} for e in edges],
            "used_by": used_by, "unused_tables": unused, "skipped": skipped or [], "summary": summary,
            "note": ("Edges come from each object's own definition (GraphQL API, semantic model, view) or, for a data agent, from its "
                     "definition text; `certain: false` marks a match by name only. Unit-tested, not yet run against a live workspace.")}


def impact(lineage: dict, table: str) -> dict:
    """What is affected if `table` changes: the objects that use it, with how, and the tables that share those objects."""
    lower = {t.lower(): t for t in lineage["used_by"]}
    if table.lower() not in lower:
        return {"table": table, "error": f"{table!r} is not a table of {lineage['source']['schema']}", "kind": "table_not_found",
                "hint": "list_tables shows the tables in a schema."}
    t = lower[table.lower()]
    objects = lineage["used_by"][t]
    shared = sorted({other for other, uses in lineage["used_by"].items() if other != t
                     and any((u["kind"], u["object"]) in {(o["kind"], o["object"]) for o in objects} for u in uses)})
    return {"table": t, "objects": objects, "tables_in_the_same_objects": shared,
            "summary": (f"{t} is used by {len(objects)} object(s)" if objects else f"{t} is used by nothing we can see")
            + (f"; a change reaches {', '.join(o['object'] for o in objects)}" if objects else "")}


def impact_of_changes(edges: list[dict], tables: list[str]) -> dict:
    """For plan_drift: table -> objects that use it, for the tables the drift touches."""
    out: dict[str, list[dict]] = {}
    for t in tables:
        hits = [{"kind": e["kind"], "object": e["object"], "via": e["via"], "certain": e["certain"]} for e in edges if e["table"].lower() == t.lower()]
        out[t] = hits
    return out


def decode_parts(parts: list[dict]) -> dict[str, str]:
    """{path: text} from a definition's InlineBase64 parts."""
    import base64
    out = {}
    for p in parts or []:
        if p.get("payloadType", "InlineBase64") == "InlineBase64" and p.get("payload"):
            try:
                out[p["path"]] = base64.b64decode(p["payload"]).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001 — a part that is not text is of no use here
                continue
    return out


def as_json(text: str) -> dict:
    try:
        return json.loads(text)
    except ValueError:
        return {}


# ------------------------------------------------------------------ reading the workspace ---------------------------
# Library functions: the MCP server passes its own (patchable) readers; the drift monitor notebook uses these directly.

def rest_items(workspace: str, headers: dict) -> list[dict]:
    """Every item in the workspace (id, displayName, type), all pages."""
    import requests
    from .deploy import FABRIC
    out, url = [], f"{FABRIC}/v1/workspaces/{workspace}/items"
    while url:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        body = r.json()
        out += body.get("value", [])
        url = body.get("continuationUri")
    return out


def _definition_response(url: str, headers: dict):
    import requests
    from .deploy import FABRIC, wait_operation
    r = requests.post(url, headers=headers, timeout=60)
    status = getattr(r, "status_code", 200)
    if status == 202:
        op = r.headers.get("x-ms-operation-id") or r.headers.get("Location", "").rstrip("/").split("/")[-1]
        result = wait_operation(op, headers, poll_seconds=2, max_polls=30)
        if result.get("status") != "Succeeded":
            raise RuntimeError(f"reading the definition did not finish: {result.get('status')}")
        r = requests.get(f"{FABRIC}/v1/operations/{op}/result", headers=headers, timeout=60)
        status = getattr(r, "status_code", 200)
    if status >= 400:
        r.raise_for_status()
    return r


def rest_definition_parts(workspace: str, route: str, item_id: str, headers: dict, fmt: str | None = None) -> dict[str, str]:
    """{path: text} of an item's definition (POST /workspaces/{ws}/{route}/{id}/getDefinition, long-running when Fabric says so)."""
    from .deploy import FABRIC
    url = f"{FABRIC}/v1/workspaces/{workspace}/{route}/{item_id}/getDefinition" + (f"?format={fmt}" if fmt else "")
    return decode_parts((_definition_response(url, headers).json().get("definition") or {}).get("parts", []))


def rest_graphql_definition(workspace: str, api_id: str, headers: dict) -> dict:
    """graphql-definition.json of an API for GraphQL item (getDefinition, long-running when Fabric says so)."""
    import base64
    from .deploy import FABRIC
    r = _definition_response(f"{FABRIC}/v1/workspaces/{workspace}/items/{api_id}/getDefinition", headers)
    parts = (r.json().get("definition") or {}).get("parts", [])
    part = next((x for x in parts if x.get("path") == "graphql-definition.json"), None)
    if not part:
        raise RuntimeError("the API has no graphql-definition.json part")
    return json.loads(base64.b64decode(part["payload"]))


def workspace_edges(workspace_id: str, item: dict, schema: str, tables: set[str], headers: dict, view_rows=None, *,
                    items=None, graphql_definition=None, definition_parts=None) -> tuple[list[dict], list[dict]]:
    """Edges table -> object over every item in the workspace that can be read, plus the items that could not.
    `view_rows` are INFORMATION_SCHEMA.VIEW_TABLE_USAGE rows when the caller could read them (None: views not read)."""
    from .errors import explain
    items = items or rest_items
    graphql_definition = graphql_definition or rest_graphql_definition
    definition_parts = definition_parts or rest_definition_parts
    source_id = item.get("id")
    api_sources = {x for x in (source_id, item.get("sql_endpoint_id")) if x}       # a lakehouse's APIs name its SQL endpoint
    databases = {item.get("sql_db") or "", item.get("displayName") or ""}
    edges: list[dict] = []
    skipped: list[dict] = []
    try:
        listed = items(workspace_id, headers)
    except Exception as e:  # noqa: BLE001 — the workspace's items cannot be listed: say so, keep the views
        listed = []
        skipped.append({"item": "the workspace's items", "kind": "Workspace", "reason": explain(e, "listing the workspace's items").get("kind", "unexpected")})
    for it in listed:
        kind, meta = it.get("type"), {"id": it.get("id"), "displayName": it.get("displayName")}
        try:
            if kind == "GraphQLApi":
                edges += from_graphql_definition(graphql_definition(workspace_id, it["id"], headers), meta, api_sources, schema, tables)
            elif kind == "SemanticModel":
                edges += from_tmdl_parts(definition_parts(workspace_id, "semanticModels", it["id"], headers, fmt="TMDL"), meta, databases, schema, tables)
            elif kind == "DataAgent":
                edges += from_data_agent_parts(definition_parts(workspace_id, "dataAgents", it["id"], headers), meta, source_id, schema, tables)
        except Exception as e:  # noqa: BLE001 — one unreadable item must not hide the rest
            skipped.append({"item": it.get("displayName"), "kind": kind, "reason": explain(e, f"reading {it.get('displayName')!r}").get("kind", "unexpected")})
    if view_rows is not None:
        edges += from_view_rows(view_rows, item, schema, tables)
    return edges, skipped
