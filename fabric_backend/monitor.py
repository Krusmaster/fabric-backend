"""The nightly drift monitor: a Fabric notebook and a pipeline that, every night, read the lakehouse's schema, compare
today's plan with the one saved last time, save today's, and send a short summary of what changed and what it
reaches to a Teams (or Power Automate) webhook the user sets on the pipeline in Fabric.

The notebook is thin: each cell calls a function in this module, so the logic is the library's (the same plan
inference, plan_drift's comparison with each GraphQL API's definition, lineage's reading of the workspace) and the
tests run it without Spark or Fabric. Nothing here talks to Fabric unless a notebook calls it.

  snapshot(plan)            today's plan as plain data: columns and types, keys and rules, relationships and rules
  diff(old, new)            tables, columns, types, keys and relationships added or removed since the last snapshot
  affected(...)             the objects that use the changed tables (lineage edges) and, per GraphQL API on the
                            source, what a re-run of create_backend would drop (drift.compare)
  summary_text / teams_message   the message; webhook_url is a notebook parameter, never in the code
  load_last / save          the snapshots, one row per run, in krusgraph.plans (krusgraph_plans without schemas)
  notebook_cells / pipeline_content   the items create_drift_monitor creates

Sources (read 26 October 2026): fabric-rest-api-specs a96c37a dataPipeline/swagger.json (Items_CreateDataPipeline,
BackgroundJobs_ScheduleExecute; scopes DataPipeline.ReadWrite.All or Item.ReadWrite.All, and for the schedule also
DataPipeline.Execute.All or Item.Execute.All; a pipeline has at most 20 schedules) and common/job_scheduling.json
(DailyScheduleConfig); fabric-docs 0b9f0f8: notebookutils-credentials.md (getToken('pbi') for the Fabric REST API),
library-management.md and notebook-limitation.md (%pip in a pipeline run needs _inlineInstallationEnabled = true),
spark-data-warehouse-connector.md (synapsesql pass-through queries, used to read view dependencies). The Notebook
activity's JSON (type TridentNotebook) is not in the specification; it follows pipelines exported from Fabric.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

PLANS = ("krusgraph", "plans")                     # schema, table on a lakehouse with schemas
PLANS_FLAT = "krusgraph_plans"                     # the table on a lakehouse without schemas (left out of the snapshot)
LIBRARY = "git+https://github.com/Krusmaster/fabric-backend@{ref}"


# ------------------------------------------------------------------ the plan as data ------------------------------

def snapshot(plan, exclude: tuple[str, ...] = (PLANS_FLAT,)) -> dict:
    skip = {e.lower() for e in exclude}
    tables = {}
    for t in sorted(plan.schema, key=lambda x: x.name.lower()):
        if t.name.lower() in skip:
            continue
        key, rule = plan.keys.get(t.name, ([], "K3"))
        tables[t.name] = {"columns": {c.name: (c.data_type or "").lower() for c in t.columns if c.name in t.column_names},
                          "key": list(key), "key_rule": rule if key else "K3"}
    rels = sorted(({"source": r.source, "columns": list(r.source_cols), "target": r.target, "target_columns": list(r.target_cols), "rule": r.rule}
                   for r in plan.relationships if r.source in tables and r.target in tables),
                  key=lambda r: (r["source"].lower(), r["columns"], r["target"].lower()))
    return {"version": 1, "schema": plan.schema.schema, "tables": tables, "relationships": rels}


def _rel_key(r: dict) -> tuple:
    return (r["source"].lower(), tuple(c.lower() for c in r["columns"]), r["target"].lower(), tuple(c.lower() for c in r["target_columns"]))


def diff(old: dict | None, new: dict) -> dict:
    """What changed from `old` to `new`; `first_run` when there is nothing to compare with."""
    out = {"first_run": old is None, "tables_added": [], "tables_removed": [], "columns_added": [], "columns_removed": [],
           "types_changed": [], "keys_changed": [], "relationships_added": [], "relationships_removed": []}
    if old is None:
        out["changed"] = False
        return out
    o, n = old.get("tables", {}), new.get("tables", {})
    olow, nlow = {k.lower(): k for k in o}, {k.lower(): k for k in n}
    out["tables_added"] = sorted(nlow[k] for k in set(nlow) - set(olow))
    out["tables_removed"] = sorted(olow[k] for k in set(olow) - set(nlow))
    for k in sorted(set(olow) & set(nlow)):
        ot, nt = o[olow[k]], n[nlow[k]]
        name = nlow[k]
        oc = {c.lower(): (c, ty) for c, ty in ot["columns"].items()}
        nc = {c.lower(): (c, ty) for c, ty in nt["columns"].items()}
        out["columns_added"] += [{"table": name, "column": nc[c][0], "type": nc[c][1]} for c in nc if c not in oc]
        out["columns_removed"] += [{"table": name, "column": oc[c][0], "type": oc[c][1]} for c in oc if c not in nc]
        out["types_changed"] += [{"table": name, "column": nc[c][0], "from": oc[c][1], "to": nc[c][1]}
                                 for c in nc if c in oc and oc[c][1] != nc[c][1]]
        if [x.lower() for x in ot["key"]] != [x.lower() for x in nt["key"]]:
            out["keys_changed"].append({"table": name, "from": ot["key"], "from_rule": ot["key_rule"], "to": nt["key"], "to_rule": nt["key_rule"]})
    orels = {_rel_key(r): r for r in old.get("relationships", [])}
    nrels = {_rel_key(r): r for r in new.get("relationships", [])}
    out["relationships_added"] = [nrels[k] for k in sorted(set(nrels) - set(orels))]
    out["relationships_removed"] = [orels[k] for k in sorted(set(orels) - set(nrels))]
    out["changed"] = any(out[k] for k in out if k not in ("first_run",))
    return out


def touched_tables(changes: dict) -> list[str]:
    """Tables whose change can break something downstream: removed, or with a column removed, retyped or a key changed."""
    names = set(changes.get("tables_removed", []))
    for k in ("columns_removed", "types_changed", "keys_changed"):
        names |= {x["table"] for x in changes.get(k, [])}
    names |= {r["source"] for r in changes.get("relationships_removed", [])}
    return sorted(names, key=str.lower)


def affected(changes: dict, edges: list[dict], api_drift: list[dict] | None = None) -> dict:
    """Objects that use the touched tables (lineage edges), and per GraphQL API what create_backend would drop."""
    from .lineage import impact_of_changes
    by_table = {t: objs for t, objs in impact_of_changes(edges, touched_tables(changes)).items() if objs}
    objects = sorted({(o["kind"], o["object"]) for objs in by_table.values() for o in objs})
    return {"by_table": by_table, "objects": [{"kind": k, "object": n} for k, n in objects],
            "graphql_apis": [a for a in (api_drift or []) if a.get("removed_columns") or a.get("tables_gone") or a.get("relationships_unsupported")]}


def api_drift(plan, definitions: dict[str, dict], workspace_id: str, source_id: str, source_type: str) -> list[dict]:
    """plan_drift's comparison (drift.compare) for each GraphQL API on this source: {api name: graphql-definition.json}."""
    from .drift import compare
    out = []
    for name, body in sorted(definitions.items()):
        if not any(ds.get("sourceItemId") in (None, source_id) for ds in body.get("datasources", [])):
            continue
        d = compare(plan, body, name, workspace_id, source_id, source_type)
        out.append({"api": name, "tables_gone": [g["table"] for g in d["tables_gone"]],
                    "removed_columns": [f"{c['table']}.{c['column']}" for c in d["removed_columns"]],
                    "relationships_unsupported": [f"{u['table']}.{u['field']} -> {u['target']}" for u in d["relationships_unsupported"]]})
    return out


_KIND_WORDS = {"graphql_api": "GraphQL API", "semantic_model": "semantic model", "view": "view", "data_agent": "data agent"}


def summary_lines(changes: dict, impact: dict | None = None) -> list[str]:
    impact = impact or {"by_table": {}, "objects": [], "graphql_apis": []}

    def users(table: str) -> str:
        objs = impact["by_table"].get(table) or []
        return (" — used by " + ", ".join(f"{_KIND_WORDS.get(o['kind'], o['kind'])} {o['object']}" for o in objs)) if objs else ""
    lines = []
    lines += [f"Table {t} disappeared{users(t)}." for t in changes["tables_removed"]]
    lines += [f"Column {c['column']} in table {c['table']} disappeared{users(c['table'])}." for c in changes["columns_removed"]]
    lines += [f"Column {c['column']} in table {c['table']} changed type from {c['from']} to {c['to']}{users(c['table'])}." for c in changes["types_changed"]]
    lines += [f"The key of {k['table']} changed from {'+'.join(k['from']) or 'none'} ({k['from_rule']}) to {'+'.join(k['to']) or 'none'} ({k['to_rule']})."
              for k in changes["keys_changed"]]
    lines += [f"Relationship {r['source']}.{'+'.join(r['columns'])} -> {r['target']} ({r['rule']}) is no longer inferred." for r in changes["relationships_removed"]]
    for a in impact.get("graphql_apis", []):
        parts = ([f"still maps {', '.join(a['removed_columns'])}"] if a["removed_columns"] else []) + \
                ([f"still has {', '.join(a['tables_gone'])}"] if a["tables_gone"] else []) + \
                ([f"would lose {', '.join(a['relationships_unsupported'])}"] if a["relationships_unsupported"] else [])
        lines.append(f"GraphQL API {a['api']} {'; '.join(parts)}: check plan_drift before running create_backend again.")
    if changes["tables_added"]:
        lines.append(f"New table(s): {', '.join(changes['tables_added'])}.")
    if changes["columns_added"]:
        lines.append(f"New column(s): {', '.join(c['table'] + '.' + c['column'] for c in changes['columns_added'])}.")
    if changes["relationships_added"]:
        lines.append(f"New relationship(s): {', '.join(r['source'] + '.' + '+'.join(r['columns']) + ' -> ' + r['target'] for r in changes['relationships_added'])}.")
    return lines


def summary_text(label: str, changes: dict, impact: dict | None = None, since: str | None = None) -> tuple[str, list[str]]:
    """(title, lines) for the message."""
    if changes.get("first_run"):
        return f"Drift monitor for {label}: first run", ["Today's plan is saved; tomorrow's run compares with it."]
    if not changes.get("changed"):
        return f"Drift monitor for {label}: no change" + (f" since {since}" if since else ""), ["The tables, columns, keys and relationships are as last time."]
    return f"Drift monitor for {label}: changes" + (f" since {since}" if since else ""), summary_lines(changes, impact)


def teams_message(title: str, lines: list[str]) -> dict:
    """An Adaptive Card message, the body a Teams "When a Teams webhook request is received" workflow posts to a channel;
    a Power Automate flow with an HTTP trigger can forward the same body as an e-mail."""
    body = [{"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "wrap": True}]
    body += [{"type": "TextBlock", "text": line, "wrap": True, "spacing": "Small"} for line in lines[:30]]
    if len(lines) > 30:
        body.append({"type": "TextBlock", "text": f"... and {len(lines) - 30} more; the notebook's run output has all of them.", "wrap": True})
    return {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None,
                                                "content": {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                                                            "type": "AdaptiveCard", "version": "1.4", "body": body}}]}


def send(webhook_url: str, message: dict, post=None) -> int:
    """POST the message; raises on a failure so the pipeline run shows it (and the plan is not saved, so the next run
    reports the same changes again)."""
    if not webhook_url.lower().startswith("https://"):
        raise ValueError("webhook_url must be an https:// address (a Teams workflow or Power Automate HTTP trigger)")
    if post is None:
        import requests
        post = requests.post
    try:
        r = post(webhook_url, json=message, timeout=30)
    except Exception as e:  # noqa: BLE001 — the address carries its own secret (sig=...): never let it reach the run's error
        raise RuntimeError(f"the webhook could not be reached ({type(e).__name__}); the address is not shown") from None
    status = getattr(r, "status_code", 0)
    if status >= 300:
        raise RuntimeError(f"the webhook answered HTTP {status}")
    return status


# ------------------------------------------------------------------ in the notebook ------------------------------

def plans_table(schemas_enabled: bool) -> str:
    return f"`{PLANS[0]}`.`{PLANS[1]}`" if schemas_enabled else f"`{PLANS_FLAT}`"


def load_last(spark, table: str, source_key: str) -> tuple[dict | None, str | None]:
    """The snapshot saved by the last run for this source, and when it was taken; (None, None) the first time."""
    from pyspark.sql import functions as F
    if not spark.catalog.tableExists(table):
        return None, None
    rows = spark.read.table(table).filter(F.col("source") == source_key).orderBy(F.col("taken_at").desc()).limit(1).collect()
    if not rows:
        return None, None
    return json.loads(rows[0]["plan_json"]), str(rows[0]["taken_at"])[:16] + " UTC"


def save(spark, table: str, source_key: str, snap: dict, changes: dict, taken_at, fmt: str = "delta") -> None:
    """Append today's snapshot (one row per run; nothing is ever deleted)."""
    if "." in table and table.startswith("`krusgraph`"):
        spark.sql("CREATE SCHEMA IF NOT EXISTS `krusgraph`")
    row = [(source_key, snap.get("schema"), taken_at, json.dumps(snap, sort_keys=True), bool(changes.get("changed")),
            json.dumps({k: len(v) for k, v in changes.items() if isinstance(v, list)}))]
    (spark.createDataFrame(row, "source string, schema string, taken_at timestamp, plan_json string, changed boolean, counts string")
     .write.format(fmt).mode("append").saveAsTable(table))


def read_view_usage(spark, lakehouse: str):
    """INFORMATION_SCHEMA.VIEW_TABLE_USAGE through the Spark connector for Fabric Data Warehouse (pass-through query on
    the lakehouse's SQL analytics endpoint); None when the connector cannot read it (views are then left out)."""
    from .lineage import VIEW_USAGE_SQL
    try:
        import com.microsoft.spark.fabric  # noqa: F401  # type: ignore
        from com.microsoft.spark.fabric.Constants import Constants  # type: ignore
        return [r.asDict() for r in spark.read.option(Constants.DatabaseName, lakehouse).synapsesql(VIEW_USAGE_SQL).collect()]
    except Exception:  # noqa: BLE001 — not every runtime has the connector; the summary says views were not read
        return None


def graphql_definitions(workspace_id: str, headers: dict, items=None, read=None) -> dict[str, dict]:
    """{name: graphql-definition.json} of every API for GraphQL item in the workspace that can be read."""
    from . import lineage
    items = items or lineage.rest_items
    read = read or lineage.rest_graphql_definition
    out = {}
    try:
        listed = items(workspace_id, headers)
    except Exception:  # noqa: BLE001 — lineage.workspace_edges reports the listing failure; here nothing is compared
        return out
    for it in listed:
        if it.get("type") == "GraphQLApi":
            try:
                out[it.get("displayName")] = read(workspace_id, it["id"], headers)
            except Exception:  # noqa: BLE001 — lineage reports unreadable items; here they are simply not compared
                continue
    return out


# ------------------------------------------------------------------ the items create_drift_monitor creates ---------

def _py(value) -> str:
    return "None" if value is None else ("True" if value is True else "False" if value is False else json.dumps(value))


_REF = __import__("re").compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")


def notebook_cells(source: dict, library_ref: str = "main") -> list[tuple[str, str]]:
    """source: workspace_id, item_id, item_name, schema, schemas_enabled, source_id (SQL endpoint), source_type."""
    if not _REF.match(library_ref or ""):
        from .infer import PlanInputError
        raise PlanInputError("library_ref: a branch, tag or commit of github.com/Krusmaster/fabric-backend (letters, digits, . _ / -)")
    label = f"{source['item_name']}.{source['schema']}"
    intro = (f"# Drift monitor for {label}\n\n"
             "Generated by Krusgraph. Every night (see the pipeline) it reads the lakehouse's tables, infers today's plan with "
             "the same rules as the MCP tools, compares it with the plan saved by the last run, saves today's, and sends a short "
             "summary of what changed and which GraphQL APIs, semantic models, views and data agents use the changed tables to "
             "the webhook set on the pipeline (parameter webhook_url). No secret is stored in this notebook.")
    pip = f'%pip install "fabric-backend @ {LIBRARY.format(ref=library_ref)}" --quiet'
    params = ('webhook_url = ""    # a Teams workflow or Power Automate HTTP trigger; set it on the pipeline in Fabric\n'
              'notify = "changes"  # "changes": only when something changed; "always": every night')
    setup = (
        "import json\nfrom datetime import datetime, timezone\n\n"
        "from fabric_backend import monitor\nfrom fabric_backend.infer import plan\nfrom fabric_backend.schema import Schema\n\n"
        "SOURCE = {\n" + ",\n".join(f"    {json.dumps(k)}: {_py(v)}" for k, v in source.items()) + "\n}\n"
        f"LABEL = {_py(label)}\n"
        f"PLANS_TABLE = monitor.plans_table({_py(bool(source['schemas_enabled']))})\n"
        "SOURCE_KEY = f\"{SOURCE['item_id']}/{SOURCE['schema']}\"\n"
        "RUN_AT = datetime.now(timezone.utc).replace(microsecond=0)")
    read = ("# 1. Today's plan: the tables and columns in the Spark catalog, keys and relationships by the rules K0–K5 and R0–R4.\n"
            "schema = Schema.from_spark(spark, SOURCE['schema'], SOURCE['schema'] if SOURCE['schemas_enabled'] else None)\n"
            "today_plan = plan(schema)\n"
            "today = monitor.snapshot(today_plan)\n"
            "print(today_plan.summary())")
    compare = ("# 2. Compare with the plan the last run saved.\n"
               "last, since = monitor.load_last(spark, PLANS_TABLE, SOURCE_KEY)\n"
               "changes = monitor.diff(last, today)")
    reach = ("# 3. What the changes reach: objects in the workspace that use the changed tables (lineage), and per GraphQL API\n"
             "#    what a re-run of create_backend would drop (plan_drift). Read with the identity that runs the notebook.\n"
             "impact = None\n"
             "if changes['changed']:\n"
             "    headers = {'Authorization': 'Bearer ' + notebookutils.credentials.getToken('pbi')}\n"
             "    from fabric_backend import lineage\n"
             "    item = {'id': SOURCE['item_id'], 'displayName': SOURCE['item_name'], 'sql_db': SOURCE.get('sql_db') or SOURCE['item_name'],\n"
             "            'sql_endpoint_id': SOURCE['source_id']}\n"
             "    views = monitor.read_view_usage(spark, SOURCE['item_name'])\n"
             "    edges, skipped = lineage.workspace_edges(SOURCE['workspace_id'], item, SOURCE['schema'], set(monitor.touched_tables(changes)), headers, views)\n"
             "    apis = monitor.api_drift(today_plan, monitor.graphql_definitions(SOURCE['workspace_id'], headers),\n"
             "                             SOURCE['workspace_id'], SOURCE['source_id'], SOURCE['source_type'])\n"
             "    impact = monitor.affected(changes, edges, apis)\n"
             "    if views is None:\n"
             "        print('Views were not read (the Fabric Data Warehouse connector is not available in this runtime).')\n"
             "    if skipped:\n"
             "        print('Could not read:', skipped)")
    tell = ("# 4. Tell someone: only when something changed (or every night with notify = \"always\"). A failed webhook\n"
            "#    stops the run before the plan is saved, so tomorrow's run reports the same changes again.\n"
            "title, lines = monitor.summary_text(LABEL, changes, impact, since)\n"
            "print(title)\nfor line in lines:\n    print('-', line)\n"
            "if webhook_url and (changes['changed'] or notify == 'always'):\n"
            "    monitor.send(webhook_url, monitor.teams_message(title, lines))")
    keep = ("# 5. Save today's plan (one row per run in the plans table; nothing is deleted) and hand the summary to the pipeline.\n"
            "monitor.save(spark, PLANS_TABLE, SOURCE_KEY, today, changes, RUN_AT)\n"
            "result = {'changed': changes['changed'], 'first_run': changes['first_run'], 'title': title, 'lines': lines}\n"
            "try:\n    notebookutils.notebook.exit(json.dumps(result))\nexcept NameError:\n    print(json.dumps(result))")
    return [("markdown", intro), ("code", pip), ("parameters", params), ("code", setup), ("code", read), ("code", compare),
            ("code", reach), ("code", tell), ("code", keep)]


def pipeline_content(notebook_id: str, workspace_id: str, label: str) -> dict:
    """pipeline-content.json: one Notebook activity that runs the monitor with the pipeline's parameters. The webhook
    address is a pipeline parameter with an empty default that the user sets in Fabric; secureInput keeps it out of
    the run history."""
    def param(name):
        return {"value": {"value": f"@pipeline().parameters.{name}", "type": "Expression"}, "type": "string"}
    return {"properties": {
        "description": f"Krusgraph drift monitor for {label}: runs the monitor notebook; set webhook_url under Parameters.",
        "activities": [{
            "name": "Check drift", "type": "TridentNotebook", "dependsOn": [],
            # no retry: a run that sent its message and then failed to save would send it again; the next night reports anyway
            "policy": {"timeout": "0.01:00:00", "retry": 0, "retryIntervalInSeconds": 300, "secureOutput": False, "secureInput": True},
            "typeProperties": {"notebookId": notebook_id, "workspaceId": workspace_id,
                               "parameters": {"webhook_url": param("webhook_url"), "notify": param("notify"),
                                              "_inlineInstallationEnabled": {"value": True, "type": "bool"}}}}],
        "parameters": {"webhook_url": {"type": "string", "defaultValue": ""}, "notify": {"type": "string", "defaultValue": "changes"}}}}


def schedule_body(at: str = "02:00", time_zone: str = "W. Europe Standard Time", start: date | None = None) -> dict:
    """POST .../dataPipelines/{id}/jobs/execute/schedules: daily at `at` (hh:mm) in `time_zone` (a Windows time zone id),
    from tomorrow for ten years (the end is required)."""
    start = start or (date.today() + timedelta(days=1))
    end = start + timedelta(days=3650)
    return {"enabled": True, "configuration": {"type": "Daily", "startDateTime": f"{start.isoformat()}T00:00:00",
                                               "endDateTime": f"{end.isoformat()}T23:59:00", "localTimeZoneId": time_zone, "times": [at]}}
