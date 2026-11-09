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

n185, one layer (the founder, 9 November 2026: after the pipeline wrote silver tables and gold views, demo_lh_agent's
data source had shop.orders and silver.orders ticked alike, so the agent saw two copies of every table). The tables
were matched by name only; now by schema too. A draft can carry `layers`, each the instructions, tables and examples
written for one schema of the lakehouse (silver first when it was asked for, the source last); apply walks the data
source's schema tree once (Staging_ListDatasourceElements: Schema, Tables, Table, MaterializedViews, MaterializedView),
takes the first layer whose tables are all there, selects exactly those and deselects the plan's tables in the other
layers' schemas (UpdateDataSourceElementRequest isSelected false: "the element configuration is preserved and restored
when re-selected"). Tables Krusgraph does not know are never touched.

n185, examples: the documented definition (Learn, "Data Agent item definition", ms.date 2026-01-21) has per data
source datasource.json and fewshots.json, in draft/ and, once published, published/; its stage_config.json has only
aiInstructions. The few-shots are what the portal calls "Example queries" ("When a user asks a question against a
data source, the Data Agent automatically retrieves the most relevant examples—typically the top four", Learn
data-agent-example-queries, ms.date 2025-09-11); neither documents a place for the questions the chat suggests. After
writing them, apply reads each example's validationStatus (Valid, Invalid, Validating; DataAgentFewshot) back, since
"queries that don't pass validation aren't sent to the agent".
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


def on_schema(plan: Plan, schema: str) -> Plan:
    """The same plan over the copies of its tables in another schema (the silver tables keep the source's names)."""
    from dataclasses import replace
    tables = {n: replace(t, schema=schema) for n, t in plan.schema.tables.items()}
    return replace(plan, schema=replace(plan.schema, tables=tables, schema=schema))


def draft(plan: Plan, info: dict, name: str, schema: str, show_personal_data: bool = False, validation: dict | None = None,
          layers: list[dict] | None = None) -> dict:
    """What create_data_agent would create: settings, data source, selected tables, few-shots and the REST calls. Since
    n130 the instructions, data source instructions and description, and the 3–5 examples come from agent_context
    (business names, checked joins, repeated amounts, answer_query_draft over safe joins); `validation` is
    validate_plan's full answer when the call counted the plan."""
    from . import agent_context
    flagged = personal(plan, show_personal_data)
    ctx = agent_context.build(plan, info.get("item_name") or "source", schema, flagged, validation, show_personal_data,
                              info.get("item_kind") or "Lakehouse")
    kind = info.get("item_kind") or "Lakehouse"
    if kind == "Lakehouse":
        datasource = {"type": "LakehouseTables", "lakehouseReference": {"referenceType": "ById", "itemId": info.get("item_id"), "workspaceId": info.get("workspace_id")}}
    else:
        datasource = {"type": "FabricItem", "itemReference": {"referenceType": "ById", "itemId": info.get("item_id"), "workspaceId": info.get("workspace_id")}}
    ws = info.get("workspace_id")
    variants = []
    for lay in layers or []:                                       # n185: the same agent written for another layer
        if lay["layer"] == "gold":
            variants.append({"layer": "gold", "schema": lay["schema"], "tables": list(lay["tables"]), "kinds": ("MaterializedView", "Table"),
                             "instructions": ctx["instructions"] + "\n\n## Layer\nAnswer from the gold views in schema "
                             f"{lay['schema']} ({', '.join(lay['tables'])}): one wide view per fact table, joined by the plan's keys.",
                             "datasource_instructions": ctx["datasource_instructions"], "datasource_description": ctx["datasource_description"],
                             "fewshots": []})
        elif lay["layer"] == "silver":
            sp = on_schema(plan, lay["schema"])
            c = agent_context.build(sp, info.get("item_name") or "source", lay["schema"], flagged, validation, show_personal_data, kind)
            variants.append({"layer": "silver", "schema": lay["schema"], "tables": [t.name for t in plan.schema], "kinds": ("Table",),
                             "instructions": c["instructions"], "datasource_instructions": c["datasource_instructions"],
                             "datasource_description": c["datasource_description"], "fewshots": c["fewshots"]})
    if variants:
        variants.append({"layer": "source", "schema": schema, "tables": [t.name for t in plan.schema], "kinds": ("Table",),
                         "instructions": ctx["instructions"], "datasource_instructions": ctx["datasource_instructions"],
                         "datasource_description": ctx["datasource_description"], "fewshots": ctx["fewshots"]})
    return {
        "layers": variants, "schema": schema,
        "name": name, "instructions": ctx["instructions"],
        "datasource": datasource, "datasource_instructions": ctx["datasource_instructions"],
        "datasource_description": ctx["datasource_description"],
        "tables_to_select": [t.name for t in plan.schema], "fewshots": ctx["fewshots"], "context": ctx["context"],
        "personal_left_out": privacy.findings(flagged),
        "rest": [f"POST /v1/workspaces/{ws}/dataAgents (or reuse the item named {name!r})",
                 f"PATCH /v1/workspaces/{ws}/dataAgents/{{id}}/staging/settings",
                 f"POST /v1/workspaces/{ws}/dataAgents/{{id}}/staging/datasources (once; reused if it exists)",
                 "PATCH …/staging/datasources/{dsId} (instructions, description); PATCH …/elements?id=… isSelected for the tables above",
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
    elements_url = f"{stage}/datasources/{ds_id}/elements"
    tree = _tree(requests, headers, elements_url)                    # n185: one walk, every table with its schema
    layer = choose_layer(spec, tree)
    use = layer or {"instructions": spec["instructions"], "datasource_instructions": spec["datasource_instructions"],
                    "datasource_description": spec.get("datasource_description"), "fewshots": spec["fewshots"]}
    _check(requests.patch(f"{stage}/settings", headers=headers, json={"aiInstructions": use["instructions"]}, timeout=60), "setting the instructions")
    log.append("instructions set")
    _check(requests.patch(f"{stage}/datasources/{ds_id}", headers=headers, json={"instructions": use["datasource_instructions"], **({"description": use["datasource_description"]} if use.get("datasource_description") else {})}, timeout=60), "setting data source instructions")
    log.append("data source instructions set")
    selection = select_layer(requests, headers, elements_url, tree, spec, layer)
    log.append(selection["words"])
    have = {f.get("question"): f for f in _check(requests.get(f"{stage}/datasources/{ds_id}/fewshots", headers=headers, timeout=60), "listing examples").get("value", [])}
    added = updated = 0
    for shot in use["fewshots"]:
        old = have.get(shot["question"])
        if old and old.get("query") == shot["query"]:
            continue
        if old:
            _check(requests.patch(f"{stage}/datasources/{ds_id}/fewshots/{old['id']}", headers=headers, json={"query": shot["query"]}, timeout=60), "updating an example")
            updated += 1
        else:
            _check(requests.post(f"{stage}/datasources/{ds_id}/fewshots", headers=headers, json=shot, timeout=60), "adding an example")
            added += 1
    log.append(f"examples: {added} added, {updated} updated, {len(use['fewshots']) - added - updated} unchanged")
    examples = example_status(requests, headers, f"{stage}/datasources/{ds_id}/fewshots", [f["question"] for f in use["fewshots"]])
    published = False
    if publish:
        _check(requests.post(f"{stage}/publish", headers=headers, json={"publishedDescription": spec.get("published_description") or "Published by Krusgraph from the inferred plan"}, timeout=60), "publishing")
        log.append("published")
        published = True
    return {"status": "Succeeded", "id": agent_id, "datasource_id": ds_id, "log": log, "selection": selection,
            "examples": examples, "published": published}


def _tree(requests, headers: dict, url: str) -> list[dict] | None:
    """Every Table and MaterializedView element of the data source with the schema it sits in ("" without schemas), or
    None when the tree is not shaped as the specification's ElementType describes it."""
    try:
        out, stack, seen, known = [], [(None, "")], 0, 0
        while stack and seen < 4000:
            node, schema = stack.pop()
            params = {"rootId": node} if node else {}
            for el in _check(requests.get(url, headers=headers, params=params, timeout=60), "listing schema elements").get("value", []):
                seen += 1
                t = el.get("type")
                known += t in ("Root", "Schemas", "Schema", "Tables", "Table", "Views", "View", "Column", "Files", "Directory",
                               "MaterializedViews", "MaterializedView")
                if t in ("Table", "MaterializedView"):
                    out.append({**el, "schema": schema})
                elif el.get("hasSubElements") and t in ("Root", "Schemas", "Schema", "Tables", "MaterializedViews"):
                    stack.append((el["id"], el.get("displayName", "") if t == "Schema" else schema))
        return out if known else None
    except RestError:
        raise
    except Exception:  # noqa: BLE001 — an unexpected tree shape is reported, not fatal
        return None


def choose_layer(spec: dict, tree: list[dict] | None) -> dict | None:
    """The first of the draft's layers whose tables are all in the tree (silver before the source); None without layers."""
    layers = spec.get("layers") or []
    if not layers or tree is None:
        return layers[-1] if layers else None
    for lay in layers:
        have = {e.get("displayName", "").lower() for e in tree if e["schema"].lower() == lay["schema"].lower() and e.get("type") in lay["kinds"]}
        if lay["layer"] == "source" and not any(e["schema"] for e in tree):
            return lay                                             # no Schema nodes: only the source can be told apart
        if {t.lower() for t in lay["tables"]} <= have:
            return lay
    return layers[-1]


def select_layer(requests, headers: dict, url: str, tree: list[dict] | None, spec: dict, layer: dict | None) -> dict:
    """Select the chosen layer's tables in its schema; deselect the plan's tables in the other layers' schemas. Without
    layers (a call that asked for none) only the plan's tables in the source schema are selected, as before n185, but by
    schema too."""
    if tree is None:
        return {"layer": (layer or {}).get("layer", "source"), "schema": (layer or {}).get("schema", spec.get("schema")), "selected": None,
                "deselected": 0, "one_layer": False,
                "words": "table selection skipped: the schema tree did not have the expected shape; select the tables in the portal"}
    want_schema = (layer or {}).get("schema") or spec.get("schema") or ""
    want = {t.lower() for t in ((layer or {}).get("tables") or spec["tables_to_select"])}
    kinds = (layer or {}).get("kinds") or ("Table",)
    others = {lay["schema"].lower(): {t.lower() for t in lay["tables"]} for lay in spec.get("layers") or [] if lay["schema"].lower() != want_schema.lower()}
    selected = deselected = 0
    for el in tree:
        sch, nm = el["schema"].lower(), el.get("displayName", "").lower()
        mine = sch == want_schema.lower() or not el["schema"]       # a tree without Schema nodes: one schema, matched by name
        if mine and nm in want and el.get("type") in kinds:
            if not el.get("isSelected"):
                _check(requests.patch(url, headers=headers, params={"id": el["id"]}, json={"isSelected": True}, timeout=60), "selecting a table")
            selected += 1
        elif sch in others and nm in others[sch] and el.get("isSelected"):
            _check(requests.patch(url, headers=headers, params={"id": el["id"]}, json={"isSelected": False}, timeout=60), "deselecting a table")
            deselected += 1
    still = [e for e in tree if e.get("isSelected") and e["schema"].lower() in others and e.get("displayName", "").lower() in others[e["schema"].lower()]]
    name = (layer or {}).get("layer", "source")
    return {"layer": name, "schema": want_schema, "selected": selected, "deselected": deselected,
            "one_layer": selected == len(want) and not (still and deselected < len(still)),
            "words": f"selected {selected} of {len(want)} tables in {want_schema or 'the lakehouse'} ({name})"
                     + (f"; deselected {deselected} of the same tables in other layers" if deselected else "")}


def example_status(requests, headers: dict, url: str, questions: list[str]) -> dict:
    """The examples' validationStatus as Fabric holds them: how many are Valid, Invalid (with the reason) or still
    Validating. Best effort: unknown when the list cannot be read."""
    try:
        rows = _check(requests.get(url, headers=headers, timeout=60), "listing examples").get("value", [])
    except Exception:  # noqa: BLE001
        return {"status": "unknown"}
    mine = [r for r in rows if r.get("question") in set(questions)]
    by = {"Valid": 0, "Invalid": 0, "Validating": 0}
    invalid = []
    for r in mine:
        v = (r.get("validationStatus") or {}).get("value") or "Validating"
        by[v] = by.get(v, 0) + 1
        if v == "Invalid":
            invalid.append({"question": r.get("question"), "reason": (r.get("validationStatus") or {}).get("reason")})
    return {"status": "read", "count": len(mine), **{k.lower(): n for k, n in by.items()}, "invalid_examples": invalid,
            "where": "Fabric shows them in the agent's Example queries pane (per data source); they guide the answers and are "
                     "not the chat's suggested questions."}
