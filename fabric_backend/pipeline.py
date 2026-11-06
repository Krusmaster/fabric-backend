"""The pipeline draft (round n110): one Fabric Data Pipeline that runs the existing steps in order, silver notebook, gold
views notebook, then a check notebook, and fails when the check fails. It is exported with export_item_definitions
(items=["pipeline"]) as files in Fabric's Git format, and since round n120 create_pipeline creates it through the REST
API (the three notebooks, then the pipeline with their ids); no tool runs or schedules it. Nothing here talks to Fabric.

The silver and gold notebooks are exactly the ones silver_notebook_draft and gold_views_draft produce (silver.py,
gold.py); no transformation is added here. The check notebook is thin, like the drift monitor's (monitor.py): each
cell calls this module, so the logic is the library's and the tests run it without Spark or Fabric.

  check_spec(plan, silver_spec, gold_spec)   what the check checks, as plain data written into the check notebook:
                                             the keys and relationships of the tables the silver notebook writes, and
                                             per gold view the fact table and its amount and quantity columns
  run(spec, schema, execute)                 keys (unique, no NULL) and orphans with evidence.validate, the same
                                             counts as validate_plan, on the silver tables; and per gold view the row
                                             count and each amount's SUM before the join (the silver fact table) and
                                             after it (the gold view)
  raise_if_failed(result)                    CheckFailed when any of them does not hold: the notebook fails, so its
                                             Notebook activity fails, and so does the pipeline run
  check_cells / pipeline_content             the check notebook and pipeline-content.json; with `ids` and `workspace_id`
                                             the activities name the notebooks by their item ids (create_pipeline), without
                                             them by their logical IDs (the Git export)

What the format rests on, read 6 November 2026:
- microsoft/fabric-rest-api-specs 6f817cb (3 November 2026), dataPipeline/definitions.json and
  examples/CreateDataPipeline.json: the definition is one part, pipeline-content.json, with
  {"properties": {"description", "activities": [...]}}; each activity has name, type, dependsOn and typeProperties,
  and dependsOn is [{"activity": <name>, "dependencyConditions": ["Succeeded"]}].
- MicrosoftDocs/fabric-docs 999d4d4 (5 November 2026): data-factory/pipeline-rest-api-capabilities.md (ms.date
  08/28/2025) for the same shape; data-factory/activity-overview.md for the conditions Succeeded, Failed, Skipped and
  Completed; cicd/cross-workspace-dependency-binding.md (09/01/2026): a pipeline's reference to a notebook is stored
  as the notebook's logical ID in Git and binds to the notebook in the workspace the branch is synced to ("Pipeline ->
  Notebook: Yes"); cicd/git-integration/source-code-format.md for the logical ID in .platform.
- The Notebook activity's JSON type, TridentNotebook, with typeProperties notebookId and workspaceId, is not in
  either of those; it is the type of the sample pipeline "Run Hello World.DataPipeline/pipeline-content.json" in
  microsoft/fabric-cicd f0b40c5 (MIT; read as documentation, nothing copied), whose notebookId is the logical ID of the
  notebook folder next to it and whose workspaceId is the zero GUID. monitor.py uses the same type.
Not verified against Fabric: that a Git update creates this pipeline and binds the three notebookIds, that the zero
workspaceId is accepted there, and that the check's SQL (dialects.DATABRICKS, Spark SQL) runs in a Fabric runtime.
"""
from __future__ import annotations

import json
import math

from . import amounts as _amounts, notebook as _nb
from .git_export import logical_id
from .monitor import DEFAULT_REF, LIBRARY

ZERO_WORKSPACE = "00000000-0000-0000-0000-000000000000"   # as in fabric-cicd's sample: the same workspace as the pipeline
ACTIVITY_TYPE = "TridentNotebook"
CONDITIONS = ("Succeeded", "Failed", "Skipped", "Completed")
STEPS = ("Silver tables", "Gold views", "Check keys, orphans and sums")
NOTHING_CREATED = ("This pipeline is a draft: nothing was created and nothing is scheduled. It runs only when someone "
                   "runs it in Fabric or adds a schedule there.")
NOT_RUN = ("Creating runs nothing and schedules nothing: no notebook and no pipeline run is started and no schedule is added. "
           "The pipeline runs only when someone runs it in Fabric or adds a schedule there.")


def placeholder(notebook: str) -> str:
    """What the dry run writes for a notebook's id, which Fabric assigns when the notebook is created; the real create
    puts the id in its place and changes nothing else."""
    return f"<id of the notebook {notebook}>"

# The shape of pipeline-content.json as the sources above document it, for the tests and for anyone who checks a file.
SHAPE = {
    "type": "object", "required": ["properties"], "additionalProperties": False,
    "properties": {"properties": {
        "type": "object", "required": ["activities"],
        "properties": {
            "description": {"type": "string"},
            "activities": {"type": "array", "minItems": 1, "items": {
                "type": "object", "required": ["name", "type", "dependsOn", "typeProperties"],
                "properties": {
                    "name": {"type": "string", "minLength": 1, "maxLength": 55},
                    "type": {"enum": [ACTIVITY_TYPE]},
                    "dependsOn": {"type": "array", "items": {
                        "type": "object", "required": ["activity", "dependencyConditions"], "additionalProperties": False,
                        "properties": {"activity": {"type": "string"},
                                       "dependencyConditions": {"type": "array", "minItems": 1, "items": {"enum": list(CONDITIONS)}}}}},
                    "policy": {"type": "object"},
                    "typeProperties": {
                        "type": "object", "required": ["notebookId", "workspaceId"],
                        "properties": {"notebookId": {"type": "string", "format": "uuid"},
                                       "workspaceId": {"type": "string", "format": "uuid"},
                                       "parameters": {"type": "object"}}}}}}}}}}


class CheckFailed(Exception):
    """Raised by the check notebook when keys, orphans or the sums do not hold; it fails the notebook run."""


# ------------------------------------------------------------------ what the check checks ---------------------------

def _sum_columns(plan, view: dict) -> list[dict]:
    fact = view["fact"]
    types = {c.name: c.data_type for c in plan.schema[fact].columns}
    out = []
    for c in view["columns"]:
        if c["table"] != fact:
            continue
        t = types.get(c["column"], "")
        if _amounts.is_numeric(t) and (_amounts.looks_like_amount(c["column"], t) or _amounts.is_quantity(c["column"], t)):
            out.append({"column": c["column"], "in_view": c["as"]})
    return out


def check_spec(plan, silver_spec: dict, gold_spec: dict) -> dict:
    """The check as data: keys and relationships between the tables the silver notebook writes (the ones it enforces),
    and per gold view the fact table and the amount and quantity columns to sum before and after the join."""
    tables = [t["table"] for t in silver_spec["tables"]]
    keys = [{"table": t["table"], "columns": list(t["key"]), "rule": t["key_rule"]} for t in silver_spec["tables"] if t["key"]]
    rels = [{"source": r.source, "columns": list(r.source_cols), "target": r.target, "target_columns": list(r.target_cols), "rule": r.rule}
            for r in plan.relationships if r.source in tables and r.target in tables]
    views = [{"view": v["name"].split(".", 1)[1], "fact": v["fact"], "sums": _sum_columns(plan, v)} for v in gold_spec["views"]]
    return {"silver_schema": silver_spec["silver_schema"], "gold_schema": gold_spec["gold_schema"], "keys": keys,
            "relationships": rels, "views": views}


# ------------------------------------------------------------------ the check itself --------------------------------

def silver_plan(schema, spec: dict):
    """A Plan over the silver tables with exactly the checked keys and relationships (no inference)."""
    from .infer import Plan, Relationship
    names = {t.name.lower(): t.name for t in schema}
    wanted = {k["table"] for k in spec["keys"]} | {r[s] for r in spec["relationships"] for s in ("source", "target")}
    wanted |= {v["fact"] for v in spec["views"]}
    missing = sorted(t for t in wanted if t.lower() not in names)
    if missing:
        raise CheckFailed(f"silver tables missing in {spec['silver_schema']}: {', '.join(missing)}; the silver notebook did not write them")
    keys = {names[k["table"].lower()]: (list(k["columns"]), k["rule"]) for k in spec["keys"]}
    rels = [Relationship(names[r["source"].lower()], list(r["columns"]), names[r["target"].lower()], list(r["target_columns"]), r["rule"])
            for r in spec["relationships"]]
    return Plan(schema=schema, keys=keys, relationships=rels)


def sums_sql(schema: str, table: str, columns: list[str], dialect) -> str:
    """One row: the rows of `table` (n) and the SUM of each column (s0, s1, ...)."""
    parts = [f"{dialect.count}(*) AS n"] + [f"SUM({dialect.quote(c)}) AS s{i}" for i, c in enumerate(columns)]
    return f"SELECT {', '.join(parts)} FROM {dialect.table(schema, table)}"


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)
    return a == b


def run(spec: dict, schema, execute) -> dict:
    """The check on the silver tables (`schema`, read from the catalog) and the gold views, through `execute(sql) -> rows
    as dicts` with a .dialect. Returns {passed, keys, relationships, joins, failures, lines}; raises nothing itself."""
    from . import evidence
    from .dialects import of as dialect_of
    plan = silver_plan(schema, spec)
    d = dialect_of(execute)
    v = evidence.validate(plan, execute, max_items=max(1, len(plan.keys) + len(plan.relationships)))
    failures = []
    for k in v["keys"]:
        if not k["verdict"].startswith(("unique", "empty table")):
            failures.append(f"key {k['table']}({', '.join(k['columns'])}): {k['verdict']}")
    for r in v["relationships"]:
        if not r["verdict"].startswith(("holds", "no rows with a value")):
            failures.append(f"{r['source']}.{'+'.join(r['columns'])} -> {r['target']}: {r['verdict']}")
    joins = []
    for view in spec["views"]:
        before = execute(sums_sql(spec["silver_schema"], view["fact"], [s["column"] for s in view["sums"]], d))[0]
        after = execute(sums_sql(spec["gold_schema"], view["view"], [s["in_view"] for s in view["sums"]], d))[0]
        entry = {"view": f"{spec['gold_schema']}.{view['view']}", "fact": f"{spec['silver_schema']}.{view['fact']}",
                 "rows_before": int(before.get("n") or 0), "rows_after": int(after.get("n") or 0), "sums": []}
        if entry["rows_before"] != entry["rows_after"]:
            failures.append(f"{entry['view']}: {entry['rows_after']} rows after the join, {entry['rows_before']} in {entry['fact']}")
        for i, s in enumerate(view["sums"]):
            b, a = before.get(f"s{i}"), after.get(f"s{i}")
            entry["sums"].append({"column": s["column"], "before": b, "after": a, "holds": _same(a, b)})
            if not _same(a, b):
                failures.append(f"{entry['view']}: SUM({s['in_view']}) is {a} after the join, SUM({s['column']}) is {b} in {entry['fact']}")
        entry["holds"] = entry["rows_before"] == entry["rows_after"] and all(s["holds"] for s in entry["sums"])
        joins.append(entry)
    lines = [v["summary"]] + [f"{j['view']}: {j['rows_after']} of {j['rows_before']} rows, "
                              + (", ".join(f"SUM({s['column']}) {s['after']} of {s['before']}" for s in j["sums"]) or "no amount column")
                              for j in joins]
    lines.append("The check holds." if not failures else f"The check failed ({len(failures)}): " + "; ".join(failures))
    return {"passed": not failures, "keys": v["keys"], "relationships": v["relationships"], "joins": joins,
            "failures": failures, "lines": lines}


def raise_if_failed(result: dict) -> None:
    if not result["passed"]:
        raise CheckFailed("The check failed, so the pipeline stops: " + "; ".join(result["failures"]))


def spark_connection(spark):
    """spark.sql as the engine's connection: rows as dicts, Spark SQL (dialects.DATABRICKS: backticks, COUNT)."""
    from .dialects import DATABRICKS
    from .platforms.base import connection
    return connection(lambda sql: [r.asDict() for r in spark.sql(sql).collect()], dialect=DATABRICKS)


# ------------------------------------------------------------------ the check notebook and the pipeline --------------

def _py(value) -> str:
    return json.dumps(value, indent=4, sort_keys=True)


def check_cells(spec: dict, label: str) -> list[tuple[str, str]]:
    intro = (f"# Check after the gold views for {label}\n\n"
             "Generated by Krusgraph from the checked plan; the last step of the pipeline (silver tables, gold views, this check). "
             f"It counts, in the silver tables in `{spec['silver_schema']}`, that each key is unique and never NULL and that every "
             "reference finds its row (no orphans), the same counts as validate_plan; and, per gold view in "
             f"`{spec['gold_schema']}`, that the join kept the rows and the sums: the same row count and the same SUM of each amount "
             "before the join (the silver fact table) and after it (the view). When any of them does not hold, the notebook raises "
             "an error, so the pipeline run fails. It only reads.")
    pip = f'%pip install "fabric-backend @ {LIBRARY.format(ref=DEFAULT_REF)}" --quiet'
    params = (f"SILVER_SCHEMA = {json.dumps(spec['silver_schema'])}   # where the silver notebook wrote the silver tables\n"
              f"GOLD_SCHEMA = {json.dumps(spec['gold_schema'])}       # where the gold notebook created the views")
    data = {k: spec[k] for k in ("keys", "relationships", "views")}
    setup = ("import json\n\nfrom fabric_backend import pipeline\nfrom fabric_backend.schema import Schema\n\n"
             f"CHECK = {_py(data)}\n"
             "CHECK.update(silver_schema=SILVER_SCHEMA, gold_schema=GOLD_SCHEMA)")
    count = ("# 1. Keys and orphans in the silver tables, and rows and sums before and after each gold view's join.\n"
             "schema = Schema.from_spark(spark, SILVER_SCHEMA, SILVER_SCHEMA)\n"
             "result = pipeline.run(CHECK, schema, pipeline.spark_connection(spark))\n"
             "for line in result['lines']:\n    print(line)")
    stop = ("# 2. Stop here when anything does not hold: the error fails this notebook, its Notebook activity and the pipeline run.\n"
            "pipeline.raise_if_failed(result)\n"
            "try:\n    notebookutils.notebook.exit(json.dumps({'passed': True, 'lines': result['lines']}))\n"
            "except NameError:\n    print('passed')")
    return [("markdown", intro), ("code", pip), ("parameters", params), ("code", setup), ("code", count), ("code", stop)]


def check_source(spec: dict, label: str, workspace_id: str = "", lakehouse_id: str = "", lakehouse_name: str = "") -> str:
    meta = _nb.notebook_metadata(workspace_id, lakehouse_id, lakehouse_name) if lakehouse_id else _nb.notebook_metadata()
    return _nb.fabric_source(check_cells(spec, label), meta)


def _activity(name: str, notebook_id: str, workspace_id: str, after: str | None, parameters: dict | None = None) -> dict:
    a = {"name": name, "type": ACTIVITY_TYPE,
         "dependsOn": [{"activity": after, "dependencyConditions": ["Succeeded"]}] if after else [],
         # no retry: a failed check is an answer, not a hiccup; a failed silver or gold run is left for a person to read
         "policy": {"timeout": "0.12:00:00", "retry": 0, "retryIntervalInSeconds": 30, "secureOutput": False, "secureInput": False},
         "typeProperties": {"notebookId": notebook_id, "workspaceId": workspace_id}}
    if parameters:
        a["typeProperties"]["parameters"] = parameters
    return a


def pipeline_content(silver: str, gold: str, check: str, label: str, ids: dict | None = None,
                     workspace_id: str = ZERO_WORKSPACE) -> dict:
    """pipeline-content.json: three Notebook activities, each after the one before it has Succeeded. Without `ids` the
    notebooks are named by their logical IDs (the .platform files the export writes), so the Git update binds them;
    with `ids` ({notebook name: item id or placeholder}) by those, in `workspace_id`, as create_pipeline sends it."""
    nid = (lambda n: ids[n]) if ids is not None else (lambda n: logical_id("Notebook", n))
    return {"properties": {
        "description": (f"Krusgraph pipeline for {label}: the silver tables ({silver}), the gold views ({gold}), then the check "
                        f"({check}); a step runs only when the one before it succeeded, and a failed check fails the run. "
                        "No schedule."),
        "activities": [_activity(STEPS[0], nid(silver), workspace_id, None), _activity(STEPS[1], nid(gold), workspace_id, STEPS[0]),
                       _activity(STEPS[2], nid(check), workspace_id, STEPS[1],
                                 {"_inlineInstallationEnabled": {"value": True, "type": "bool"}})]}}
