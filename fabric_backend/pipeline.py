"""The pipeline draft (round n110): one Fabric Data Pipeline that runs the existing steps in order, silver notebook, gold
views notebook, then a check notebook, and fails when the check fails. It is exported with export_item_definitions
(items=["pipeline"]) as files in Fabric's Git format, and since round n120 create_pipeline creates it through the REST
API (the three notebooks, then the pipeline with their ids); no tool runs or schedules it. Nothing here talks to Fabric.

The silver and gold notebooks are exactly the ones silver_notebook_draft and gold_views_draft produce (silver.py,
gold.py); no transformation is added here. Since round n140 the check notebook is self-contained like them: the check
is CHECK_CODE, plain Python on spark.sql written verbatim into a cell, with no %pip and no import of this library (the
first live run, 7 November 2026, failed with "cannot import name 'pipeline' from 'fabric_backend'" because the
notebook installed the published release, which is older than main). run() executes the same text, so the tests run
the code Fabric runs, on SQLite and on a local Spark.

  check_spec(plan, silver_spec, gold_spec)   what the check checks, as plain data written into the check notebook:
                                             the keys and relationships of the tables the silver notebook writes, and
                                             per gold view the fact table and its amount and quantity columns
  run(spec, schema, execute)                 CHECK_CODE's check(): keys (unique, no NULL) and orphans (NOT EXISTS),
                                             the same counts as validate_plan, on the silver tables; and per gold view the row
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
workspaceId is accepted there, and that the check's Spark SQL runs in a Fabric runtime. On 7
November 2026 pipeline_shop ran in Fabric: silver_shop and gold_shop succeeded, the check failed on its import (fixed
in n140); the self-contained check notebook has not yet run in Fabric.
"""
from __future__ import annotations

import json

from . import amounts as _amounts, notebook as _nb
from .codegen import py_literal as _py_literal
from .git_export import logical_id

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


NOT_ENFORCED = ("the key was guessed from names and not checked, so the silver notebook removed no rows: reported, not a "
                "failure")


def check_spec(plan, silver_spec: dict, gold_spec: dict) -> dict:
    """The check as data: keys and relationships between the tables the silver notebook writes (the ones it enforces),
    and per gold view the fact table and the amount and quantity columns to sum before and after the join."""
    tables = [t["table"] for t in silver_spec["tables"]]
    # n208: a key silver removed no rows on (guessed from names) is counted and reported, but never fails the run: the
    # rows that share it may be real rows (a fact table), and silver kept them on purpose.
    keys = [{"table": t["table"], "columns": list(t["key"]), "rule": t["key_rule"],
             **({} if t.get("dedupe", True) or t.get("fix_key") else {"not_enforced": NOT_ENFORCED})}
            for t in silver_spec["tables"] if t["key"]]
    rels = [{"source": r.source, "columns": list(r.source_cols), "target": r.target, "target_columns": list(r.target_cols), "rule": r.rule}
            for r in plan.relationships if r.source in tables and r.target in tables]
    views = [{"view": v["name"].split(".", 1)[1], "fact": v["fact"], "sums": _sum_columns(plan, v)} for v in gold_spec["views"]]
    return {"silver_schema": silver_spec["silver_schema"], "gold_schema": gold_spec["gold_schema"], "keys": keys,
            "relationships": rels, "views": views}


# ------------------------------------------------------------------ the check itself --------------------------------

# The check as plain Python, written verbatim into the check notebook (n140): it needs only an `execute(sql) -> rows as
# dicts` and the names of the tables in the silver schema, so the notebook runs it on spark.sql with nothing installed
# and no import of this library. A notebook that pip-installed the library got the published release, which is older
# than the server that drafted it: the first live run (7 November 2026) failed with "cannot import name 'pipeline' from
# 'fabric_backend'". The library runs the same text (run() below), so the tests check the code Fabric runs. It uses
# only what Fabric Runtime 2.0 (Spark 4.1, Delta 4.2, Python 3.13; the run of 7 November 2026) provides: spark.sql,
# spark.catalog.tableExists (which the silver and gold notebooks call too) and the standard library (json, math); SQL
# that Spark SQL and SQLite both read (backticks, COUNT, NOT EXISTS).
CHECK_CODE = r'''
import math


class CheckFailed(Exception):
    """Raised when keys, orphans or the sums do not hold: the notebook fails, so its Notebook activity and the pipeline run fail."""


def _q(name):
    return "`" + str(name).replace("`", "``") + "`"


def _tbl(schema, table):
    return _q(schema) + "." + _q(table)


def _one(execute, sql):
    rows = execute(sql)
    return rows[0] if rows else {}


def _same(a, b):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)
    return a == b


def check_key(execute, schema, key):
    """A key holds when no row has NULL in it and no value occurs twice."""
    t, cols = key["table"], key["columns"]
    any_null = " OR ".join(_q(c) + " IS NULL" for c in cols)
    listed = ", ".join(_q(c) for c in cols)
    r = _one(execute, f"SELECT COUNT(*) AS n, SUM(CASE WHEN {any_null} THEN 1 ELSE 0 END) AS nulls FROM {_tbl(schema, t)}")
    d = _one(execute, f"SELECT COUNT(*) AS d FROM (SELECT {listed} FROM {_tbl(schema, t)} WHERE NOT ({any_null}) "
                      f"GROUP BY {listed} HAVING COUNT(*) > 1) AS dup")
    n, nulls, dups = int(r.get("n") or 0), int(r.get("nulls") or 0), int(d.get("d") or 0)
    problems = []
    if nulls:
        problems.append(f"not a key: {nulls} of {n} rows have NULL in it")
    if dups:
        problems.append(f"not unique: {dups} values occur more than once")
    verdict = "; ".join(problems) or ("empty table" if n == 0 else "unique, never NULL")
    enforced = not key.get("not_enforced")
    if problems and not enforced:                     # n208: a guessed key; silver kept every row, so this is reported only
        verdict += "; " + key["not_enforced"]
    return {"table": t, "columns": list(cols), "rows": n, "nulls": nulls, "duplicates": dups, "holds": not problems,
            "enforced": enforced, "verdict": verdict}


def check_reference(execute, schema, rel):
    """A reference holds when every row with a value finds its row in the target table (no orphans)."""
    src, tgt, cols, tcols = rel["source"], rel["target"], rel["columns"], rel["target_columns"]
    filled = " AND ".join("s." + _q(c) + " IS NOT NULL" for c in cols)
    match = " AND ".join("t." + _q(tc) + " = s." + _q(c) for c, tc in zip(cols, tcols))
    n = int(_one(execute, f"SELECT COUNT(*) AS n FROM {_tbl(schema, src)} AS s WHERE {filled}").get("n") or 0)
    o = int(_one(execute, f"SELECT COUNT(*) AS o FROM {_tbl(schema, src)} AS s WHERE {filled} AND NOT EXISTS "
                          f"(SELECT 1 FROM {_tbl(schema, tgt)} AS t WHERE {match})").get("o") or 0)
    verdict = (f"{o} of {n} rows find no row in {tgt}({', '.join(tcols)}) (orphans)" if o else
               "no rows with a value" if n == 0 else f"holds: all {n} rows find their row in {tgt}")
    return {"source": src, "columns": list(cols), "target": tgt, "target_columns": list(tcols), "rows": n, "orphans": o,
            "holds": o == 0, "verdict": verdict}


def _sums(execute, schema, table, columns):
    parts = ["COUNT(*) AS n"] + [f"SUM({_q(c)}) AS s{i}" for i, c in enumerate(columns)]
    return _one(execute, f"SELECT {', '.join(parts)} FROM {_tbl(schema, table)}")


def check_view(execute, spec, view):
    """The gold view keeps the rows and the sums of its fact table: the same row count and SUM of each amount."""
    before = _sums(execute, spec["silver_schema"], view["fact"], [s["column"] for s in view["sums"]])
    after = _sums(execute, spec["gold_schema"], view["view"], [s["in_view"] for s in view["sums"]])
    entry = {"view": spec["gold_schema"] + "." + view["view"], "fact": spec["silver_schema"] + "." + view["fact"],
             "rows_before": int(before.get("n") or 0), "rows_after": int(after.get("n") or 0), "sums": []}
    failures = []
    if entry["rows_before"] != entry["rows_after"]:
        failures.append(f"{entry['view']}: {entry['rows_after']} rows after the join, {entry['rows_before']} in {entry['fact']}")
    for i, s in enumerate(view["sums"]):
        b, a = before.get(f"s{i}"), after.get(f"s{i}")
        entry["sums"].append({"column": s["column"], "before": b, "after": a, "holds": _same(a, b)})
        if not _same(a, b):
            failures.append(f"{entry['view']}: SUM({s['in_view']}) is {a} after the join, SUM({s['column']}) is {b} in {entry['fact']}")
    entry["holds"] = not failures
    return entry, failures


def check(spec, execute, exists):
    """The whole check: `spec` as check_spec writes it, `execute(sql) -> rows as dicts`, `exists(name) -> bool` for a
    quoted `schema`.`table` (spark.catalog.tableExists, as the silver and gold notebooks call it). Silver tables are
    read as `<silver_schema>`.`<table>` and gold views as `<gold_schema>`.`<view>`, the names those notebooks write.
    Returns {passed, keys, relationships, joins, failures, lines}; raises CheckFailed when a table or view is missing."""
    silver, gold = spec["silver_schema"], spec["gold_schema"]
    wanted = [k["table"] for k in spec["keys"]] + [r[s] for r in spec["relationships"] for s in ("source", "target")]
    wanted += [v["fact"] for v in spec["views"]]
    missing = sorted({t for t in wanted if not exists(_tbl(silver, t))})
    if missing:
        raise CheckFailed(f"silver tables missing in {silver}: {', '.join(missing)}; the silver notebook did not write them")
    missing = sorted({v["view"] for v in spec["views"] if not exists(_tbl(gold, v["view"]))})
    if missing:
        raise CheckFailed(f"gold views missing in {gold}: {', '.join(missing)}; the gold notebook did not create them")
    keys = [check_key(execute, silver, k) for k in spec["keys"]]
    rels = [check_reference(execute, silver, r) for r in spec["relationships"]]
    failures = [f"key {k['table']}({', '.join(k['columns'])}): {k['verdict']}" for k in keys if not k["holds"] and k["enforced"]]
    failures += [f"{r['source']}.{'+'.join(r['columns'])} -> {r['target']}: {r['verdict']}" for r in rels if not r["holds"]]
    joins = []
    for view in spec["views"]:
        entry, failed = check_view(execute, spec, view)
        joins.append(entry)
        failures += failed
    lines = [f"Keys in {silver}: {sum(k['holds'] for k in keys)} of {len(keys)} unique and never NULL."]
    lines += [f"  {k['table']}({', '.join(k['columns'])}): {k['rows']} rows, {k['verdict']}" for k in keys]
    lines.append(f"References in {silver}: {sum(r['holds'] for r in rels)} of {len(rels)} without orphans.")
    lines += [f"  {r['source']}.{'+'.join(r['columns'])} -> {r['target']}: {r['verdict']}" for r in rels]
    lines.append(f"Gold views: {sum(j['holds'] for j in joins)} of {len(joins)} keep the rows and sums of their fact table.")
    lines += [f"  {j['view']}: {j['rows_after']} of {j['rows_before']} rows, "
              + (", ".join(f"SUM({s['column']}) {s['after']} of {s['before']}" for s in j["sums"]) or "no amount column")
              for j in joins]
    lines.append("The check holds." if not failures else f"The check failed ({len(failures)}): " + "; ".join(failures))
    return {"passed": not failures, "keys": keys, "relationships": rels, "joins": joins, "failures": failures, "lines": lines}


def raise_if_failed(result):
    if not result["passed"]:
        raise CheckFailed("The check failed, so the pipeline stops: " + "; ".join(result["failures"]))
'''.strip("\n") + "\n"

_CHECK: dict = {}
exec(compile(CHECK_CODE, "<krusgraph check notebook>", "exec"), _CHECK)
CheckFailed = _CHECK["CheckFailed"]
raise_if_failed = _CHECK["raise_if_failed"]


def run(spec: dict, schema, execute) -> dict:
    """The check notebook's code (CHECK_CODE) through `execute(sql) -> rows as dicts`; `schema` (a Schema read from the
    catalog) holds the silver tables, and a gold view exists when it can be read. Returns {passed, keys, relationships,
    joins, failures, lines}."""
    silver = {_CHECK["_tbl"](spec["silver_schema"], t.name).lower() for t in schema}

    def exists(name: str) -> bool:
        if name.lower().startswith(_CHECK["_q"](spec["silver_schema"]).lower() + "."):
            return name.lower() in silver
        try:
            execute(f"SELECT 1 FROM {name} LIMIT 1")
            return True
        except Exception:  # noqa: BLE001 — the engine's error for a table that is not there
            return False
    return _CHECK["check"](spec, execute, exists)


# ------------------------------------------------------------------ the check notebook and the pipeline --------------

def _py(value) -> str:
    return _py_literal(value, indent=4, sort_keys=True)                  # review L9


def check_cells(spec: dict, label: str) -> list[tuple[str, str]]:
    """The check notebook: self-contained. The check is CHECK_CODE in a cell of its own, plain Python on spark.sql;
    nothing is installed and nothing is imported but the standard library, so a run fetches nothing from the internet."""
    intro = (f"# Check after the gold views for {label}\n\n"
             "Generated by Krusgraph from the checked plan; the last step of the pipeline (silver tables, gold views, this check). "
             f"It counts, in the silver tables in `{spec['silver_schema']}`, that each key is unique and never NULL and that every "
             "reference finds its row (no orphans), the same counts as validate_plan; and, per gold view in "
             f"`{spec['gold_schema']}`, that the join kept the rows and the sums: the same row count and the same SUM of each amount "
             "before the join (the silver fact table) and after it (the view). When any of them does not hold, the notebook raises "
             "an error, so the pipeline run fails. It only reads.\n\n"
             "Self-contained: plain PySpark and Python, nothing is installed and no library is imported, so it runs the same "
             "with or without internet access.")
    params = (f"SILVER_SCHEMA = {_py_literal(spec['silver_schema'])}   # where the silver notebook wrote the silver tables\n"
              f"GOLD_SCHEMA = {_py_literal(spec['gold_schema'])}       # where the gold notebook created the views")
    data = {k: spec[k] for k in ("keys", "relationships", "views")}
    setup = ("import json\n\n"
             f"CHECK = {_py(data)}\n"
             "CHECK.update(silver_schema=SILVER_SCHEMA, gold_schema=GOLD_SCHEMA)")
    code = "# The check: keys, orphans, and rows and sums before and after each gold view's join, as plain Spark SQL.\n" + CHECK_CODE
    count = ("# 1. Count in the silver tables and the gold views.\n"
             "def execute(sql):\n    return [r.asDict() for r in spark.sql(sql).collect()]\n\n"
             "result = check(CHECK, execute, spark.catalog.tableExists)\n"
             "for line in result['lines']:\n    print(line)")
    stop = ("# 2. Stop here when anything does not hold: the error fails this notebook, its Notebook activity and the pipeline run.\n"
            "raise_if_failed(result)\n"
            "try:\n    notebookutils.notebook.exit(json.dumps({'passed': True, 'lines': result['lines']}))\n"
            "except NameError:\n    print('passed')")
    return [("markdown", intro), ("parameters", params), ("code", setup), ("code", code), ("code", count), ("code", stop)]


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
                       _activity(STEPS[2], nid(check), workspace_id, STEPS[1])]}}
