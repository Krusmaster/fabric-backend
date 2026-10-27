"""A Fabric Data Agent over the source, built from the plan: instructions (tables, keys, relationships with their
rules, join paths) and a handful of example question/T-SQL pairs, created or updated through the public REST API.

REST surface used (microsoft/fabric-rest-api-specs [a96c37a] dataAgent/swagger.json, examples/, read 25 Oct 2026):
- POST /workspaces/{ws}/dataAgents {displayName, description}  (Items_CreateDataAgent; CreateDataAgentWithoutDefinition.json)
- PATCH .../dataAgents/{id}/staging/settings {aiInstructions}  (Staging_UpdateSettings)
- GET/POST .../staging/datasources — {type: LakehouseTables, lakehouseReference: {referenceType: ById, itemId, workspaceId}}
  for a lakehouse, {type: FabricItem, itemReference: {...}} for a warehouse, SQL database, mirrored database …
  (CreateStagingDataAgentDatasource.json, CreateStagingDataAgentWarehouseDatasource.json)
- PATCH .../staging/datasources/{dsId} {instructions, description}  (Staging_UpdateDatasource)
- GET .../staging/datasources/{dsId}/elements?rootId=…, PATCH …/elements?id=… {isSelected}  (schema elements)
- GET/POST/PATCH .../staging/datasources/{dsId}/fewshots {question, query}  (Staging_*DatasourceFewshot)
- POST .../dataAgents/{id}/staging/publish {publishedDescription}  (Items_PublishDataAgent)
Scopes per swagger: Item.ReadWrite.All for create/update; the staging routes also accept DataAgent.ReadWrite.All.
The create-with-definition variant exists (CreateDataAgent.json shows parts under Files/Config/…) but its part
format is documented only in an article this environment could not fetch, so this module uses the staging API,
whose bodies the specification defines in full. Nothing here deletes anything.

Columns the privacy rules flag by name (privacy.py: a person's name, an e-mail address, ...) are left out of the
instructions' column lists and of the examples' SELECT and GROUP BY, the key standing in, as in answer_query_draft;
the instructions name them so the agent leaves them out too. show_personal_data=true keeps them.
"""
from __future__ import annotations

from . import privacy
from .evidence import qi
from .infer import Plan, RULES
from .paths import shortest_paths, sql_for

MAX_FEWSHOTS = 10


def personal(plan: Plan, show: bool = False) -> dict[tuple[str, str], dict]:
    """{(table, column): finding} for the columns the privacy rules flag, or none when the caller asked to see them."""
    return {} if show else privacy.personal_columns(plan.schema)


def instructions(plan: Plan, source_name: str, schema: str, personal_data: dict | None = None) -> str:
    personal_data = personal_data or {}
    lines = [f"You answer questions about the {source_name} data (schema {schema}) with T-SQL on its SQL analytics endpoint. "
             "Use only the tables, keys and relationships below; they were inferred from the names and checked where noted, "
             "and every one carries the rule that produced it.", "", "Tables and keys:"]
    for t in plan.schema:
        key, rule = plan.keys.get(t.name, ([], "K3"))
        cols = [c for c in t.column_names if (t.name, c) not in personal_data or c in key]
        lines.append(f"- {schema}.{t.name}: columns {', '.join(cols)}; key {'+'.join(key) if key else 'none'} (rule {rule})")
    lines += ["", "Relationships (join conditions):"]
    for r in plan.relationships:
        on = " AND ".join(f"{r.source}.{a} = {r.target}.{b}" for a, b in zip(r.source_cols, r.target_cols))
        lines.append(f"- {r.source} -> {r.target}: {on} (rule {r.rule}, many-to-one)")
    if plan.keyless:
        lines.append(f"\nTables without a key (do not join to them as a dimension): {', '.join(plan.keyless)}")
    if plan.ambiguous:
        lines.append("\nColumns that could point at two tables and must not be joined without asking: "
                     + "; ".join(f"{a['table']}.{a['column']} ({' or '.join(a['candidates'])})" for a in plan.ambiguous))
    if personal_data:
        lines.append("\nColumns that look like personal data by name, left out of the lists above: "
                     + "; ".join(f"{f['table']}.{f['column']} ({f['rule']}: {f['what']})" for f in privacy.findings(personal_data))
                     + ". Do not select, group by or show them; group by the table's key instead.")
    lines += ["", "Rules: " + "; ".join(f"{k} = {v.split(' (')[0]}" for k, v in RULES.items() if k != "confirmed"),
              "", "Always quote identifiers with square brackets, qualify tables with the schema, and prefer the relationships above over guessing joins."]
    return "\n".join(lines)


def fewshots(plan: Plan, schema: str, limit: int = MAX_FEWSHOTS, personal_data: dict | None = None) -> list[dict]:
    """5–10 question/T-SQL pairs: a count per fact-like table, a 'per dimension' count per relationship, and one
    multi-hop join from paths.join_path. Deterministic order. A label column in `personal_data` gives way to the
    target's key, and the join's columns leave those columns out."""
    personal_data = personal_data or {}
    out: list[dict] = []
    in_deg = {r.target for r in plan.relationships}
    facts = [t.name for t in plan.schema if t.name not in in_deg and any(r.source == t.name for r in plan.relationships)]
    for f in facts:
        out.append({"question": f"How many rows are there in {f}?", "query": f"SELECT COUNT_BIG(*) AS row_count FROM {qi(schema)}.{qi(f)}"})
    for r in plan.relationships:
        if len(r.source_cols) != 1:
            continue
        label = next((c for c in plan.schema[r.target].column_names if c.lower() in ("name", "title", "label", "description")), r.target_cols[0])
        if (r.target, label) in personal_data:
            label = r.target_cols[0]                                   # the key stands in, as in answer_query_draft
        out.append({"question": f"Which {r.target} have the most rows in {r.source}?",
                    "query": (f"SELECT TOP (10) t.{qi(label)}, COUNT_BIG(*) AS {qi(r.source + '_count')} FROM {qi(schema)}.{qi(r.source)} AS s "
                              f"JOIN {qi(schema)}.{qi(r.target)} AS t ON s.{qi(r.source_cols[0])} = t.{qi(r.target_cols[0])} "
                              f"GROUP BY t.{qi(label)} ORDER BY {qi(r.source + '_count')} DESC")})
    # the longest of the shortest paths between two keyed tables, as one worked example
    best: tuple[int, str, str, list] | None = None
    names = [t.name for t in plan.schema if t.name in plan.keys]
    for a in names:
        for b in names:
            if a < b:
                paths = shortest_paths(plan, a, b, limit=1)
                if paths and (best is None or len(paths[0]) > best[0]):
                    best = (len(paths[0]), a, b, paths[0])
    if best and best[0] >= 2:
        via = [(r.target if fwd else r.source) for r, fwd in best[3]][:-1]       # the tables between start and end
        through = f" through {', '.join(via[:-1])} and {via[-1]}" if len(via) > 1 else (f" through {via[0]}" if via else "")
        out.append({"question": f"Show {best[1]} joined to {best[2]}{through}.",
                    "query": sql_for(plan, best[1], best[3], top=100, leave_out=set(personal_data))})
    return out[:limit]


def draft(plan: Plan, info: dict, name: str, schema: str, show_personal_data: bool = False) -> dict:
    """What create_data_agent would create: settings, data source, selected tables, few-shots and the REST calls."""
    flagged = personal(plan, show_personal_data)
    kind = info.get("item_kind") or "Lakehouse"
    if kind == "Lakehouse":
        datasource = {"type": "LakehouseTables", "lakehouseReference": {"referenceType": "ById", "itemId": info.get("item_id"), "workspaceId": info.get("workspace_id")}}
    else:
        datasource = {"type": "FabricItem", "itemReference": {"referenceType": "ById", "itemId": info.get("item_id"), "workspaceId": info.get("workspace_id")}}
    ds_instructions = (f"Tables live in schema {schema}. " + " ".join(
        f"{r.source}.{'+'.join(r.source_cols)} joins {r.target}.{'+'.join(r.target_cols)}." for r in plan.relationships))
    ws = info.get("workspace_id")
    return {
        "name": name, "instructions": instructions(plan, info.get("item_name") or "source", schema, flagged),
        "datasource": datasource, "datasource_instructions": ds_instructions,
        "tables_to_select": [t.name for t in plan.schema], "fewshots": fewshots(plan, schema, personal_data=flagged),
        "personal_left_out": privacy.findings(flagged),
        "rest": [f"POST /v1/workspaces/{ws}/dataAgents (or reuse the item named {name!r})",
                 f"PATCH /v1/workspaces/{ws}/dataAgents/{{id}}/staging/settings",
                 f"POST /v1/workspaces/{ws}/dataAgents/{{id}}/staging/datasources (once; reused if it exists)",
                 "PATCH …/staging/datasources/{dsId}; PATCH …/elements?id=… isSelected for the tables above",
                 "POST or PATCH …/staging/datasources/{dsId}/fewshots, one per example",
                 f"POST /v1/workspaces/{ws}/dataAgents/{{id}}/staging/publish"],
        "delegated_scope": "Item.ReadWrite.All (staging routes also accept DataAgent.ReadWrite.All)",
    }


def _check(r, what: str) -> dict:
    if r.status_code >= 400:
        raise RestError(what, r.status_code, getattr(r, "text", ""))
    try:
        return r.json() if r.text else {}
    except ValueError:
        return {}


class RestError(Exception):
    def __init__(self, what: str, status: int, body: str) -> None:
        super().__init__(f"{what}: HTTP {status}")
        self.what, self.status, self.body = what, status, body


def apply(spec: dict, workspace: str, headers: dict, publish: bool = True, poll_seconds: int = 3, max_polls: int = 60) -> dict:
    """Create or update the agent from a draft. Idempotent: the agent, its data source and its few-shots are matched by
    name / item / question and updated in place; nothing is deleted. Returns a step log and the agent id."""
    import requests
    from .deploy import FABRIC, find_item, wait_operation
    base = f"{FABRIC}/v1/workspaces/{workspace}/dataAgents"
    log: list[str] = []
    agent_id = find_item(workspace, spec["name"], headers, "DataAgent")
    if agent_id:
        log.append(f"reused data agent {spec['name']!r} ({agent_id})")
    else:
        r = requests.post(base, headers=headers, json={"displayName": spec["name"], "description": "Created by Krusgraph from the inferred plan"}, timeout=60)
        body = _check(r, "creating the data agent")
        op = r.headers.get("x-ms-operation-id")
        if op:
            s = wait_operation(op, headers, poll_seconds, max_polls)
            if s.get("status") != "Succeeded":
                return {"status": s.get("status", "Failed"), "log": log + [f"create operation {op} ended {s.get('status')}"], **({"http": s["http"]} if s.get("http") else {})}
        agent_id = body.get("id") or find_item(workspace, spec["name"], headers, "DataAgent")
        log.append(f"created data agent {spec['name']!r} ({agent_id})")
    stage = f"{base}/{agent_id}/staging"
    _check(requests.patch(f"{stage}/settings", headers=headers, json={"aiInstructions": spec["instructions"]}, timeout=60), "setting the instructions")
    log.append("instructions set")
    ds_ref = spec["datasource"].get("lakehouseReference") or spec["datasource"].get("itemReference")
    existing = _check(requests.get(f"{stage}/datasources", headers=headers, timeout=60), "listing data sources").get("value", [])
    ds = next((d for d in existing if (d.get("lakehouseReference") or d.get("itemReference") or {}).get("itemId") == ds_ref.get("itemId")), None)
    if ds:
        log.append(f"reused data source {ds.get('id')}")
    else:
        r = requests.post(f"{stage}/datasources", headers=headers, json=spec["datasource"], timeout=60)
        ds = _check(r, "adding the data source")
        op = r.headers.get("x-ms-operation-id")
        if op and not ds.get("id"):
            wait_operation(op, headers, poll_seconds, max_polls)
            existing = _check(requests.get(f"{stage}/datasources", headers=headers, timeout=60), "listing data sources").get("value", [])
            ds = next((d for d in existing if (d.get("lakehouseReference") or d.get("itemReference") or {}).get("itemId") == ds_ref.get("itemId")), ds)
        log.append(f"added data source {ds.get('id')}")
    ds_id = ds.get("id")
    _check(requests.patch(f"{stage}/datasources/{ds_id}", headers=headers, json={"instructions": spec["datasource_instructions"]}, timeout=60), "setting data source instructions")
    log.append("data source instructions set")
    selected = _select_tables(requests, headers, f"{stage}/datasources/{ds_id}/elements", spec["tables_to_select"])
    log.append(f"selected {selected} of {len(spec['tables_to_select'])} tables in the data source" if selected is not None
               else "table selection skipped: the schema tree did not have the expected shape; select the tables in the portal")
    have = {f.get("question"): f for f in _check(requests.get(f"{stage}/datasources/{ds_id}/fewshots", headers=headers, timeout=60), "listing examples").get("value", [])}
    added = updated = 0
    for shot in spec["fewshots"]:
        old = have.get(shot["question"])
        if old and old.get("query") == shot["query"]:
            continue
        if old:
            _check(requests.patch(f"{stage}/datasources/{ds_id}/fewshots/{old['id']}", headers=headers, json={"query": shot["query"]}, timeout=60), "updating an example")
            updated += 1
        else:
            _check(requests.post(f"{stage}/datasources/{ds_id}/fewshots", headers=headers, json=shot, timeout=60), "adding an example")
            added += 1
    log.append(f"examples: {added} added, {updated} updated, {len(spec['fewshots']) - added - updated} unchanged")
    if publish:
        _check(requests.post(f"{stage}/publish", headers=headers, json={"publishedDescription": "Published by Krusgraph from the inferred plan"}, timeout=60), "publishing")
        log.append("published")
    return {"status": "Succeeded", "id": agent_id, "datasource_id": ds_id, "log": log}


def _select_tables(requests, headers: dict, url: str, tables: list[str]) -> int | None:
    """Walk the schema tree (Root -> Schemas/Tables -> …) and select the plan's tables. Best effort: None when the tree
    is not shaped as the specification's example."""
    wanted = {t.lower() for t in tables}
    try:
        def children(root_id=None):
            params = {"rootId": root_id} if root_id else {}
            r = requests.get(url, headers=headers, params=params, timeout=60)
            return _check(r, "listing schema elements").get("value", [])
        count = 0
        stack = [None]
        seen = known = 0
        while stack and seen < 2000:
            node = stack.pop()
            for el in children(node):
                seen += 1
                known += el.get("type") in ("Root", "Schemas", "Schema", "Tables", "Table", "Views", "View", "Column", "Files", "Directory")
                if el.get("type") == "Table":
                    if el.get("displayName", "").lower() in wanted and not el.get("isSelected"):
                        _check(requests.patch(url, headers=headers, params={"id": el["id"]}, json={"isSelected": True}, timeout=60), "selecting a table")
                        count += 1
                    elif el.get("displayName", "").lower() in wanted:
                        count += 1
                elif el.get("hasSubElements") and el.get("type") in ("Root", "Schemas", "Schema", "Tables"):
                    stack.append(el["id"])
        return count if known else None                       # nothing the specification describes: not our tree
    except RestError:
        raise
    except Exception:  # noqa: BLE001 — an unexpected tree shape is reported, not fatal
        return None
