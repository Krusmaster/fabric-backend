"""Health over time (n200, docs/LIFECYCLE-DESIGN.md section 8, round 1; sections 1.1, 1.2 and 5.3).

The pipeline Krusgraph makes now remembers how each run went. Two pieces of plain Python are written verbatim into its
notebooks, like pipeline.CHECK_CODE (no %pip, no import of this library, only the standard library and spark):

  DRIFT_CODE    the silver notebook's first code cell (only the pipeline's silver notebook, never the stand-alone draft):
                today's source tables and columns against the plan the outputs were built from. A drift that breaks
                silver or gold (a source table gone, or a column a key, a relationship, an ordering or a gold view uses)
                stops the run before anything is written, with the reason; a drift that does not (a new table, a new
                column, a column nothing uses dropped, a changed type) is recorded and the run goes on.
  HEALTH_CODE   the check notebook, after the check: one row per check in `krusgraph`.`health` (`krusgraph_health` on a
                lakehouse without schemas), with the previous run of the same plan as the baseline.
  ALERT_CODE    in both: the table write and the optional Teams / Power Automate alert. The webhook address is read from
                the owner's Azure Key Vault at run time (notebookutils.credentials.getSecret), never written in code.

The table holds names, rules, statuses and counts, never a row value: no key value, no sample row, no amount. join_sums
says pass or fail, never the sums. Columns: run_id, checked_at, plan_id, schema_fingerprint, check, object, rule, status,
count, baseline (docs/HEALTH.md).

The item reads the table as the signed-in user: read_sql() and summarize() give one health word per data product
(green, amber, red, not checked yet) and the open findings, for POST /workload/v1/health (workload_api.run_health).
"""
from __future__ import annotations

import re

from .codegen import py_literal as _py_literal

TABLE = ("krusgraph", "health")                    # schema, table on a lakehouse with schemas
TABLE_FLAT = "krusgraph_health"                    # on a lakehouse without schemas
WORDS = ("green", "amber", "red", "not checked yet")
NOT_CHECKED = "not checked yet"
CHECKS = ("key", "orphans", "join_rows", "join_sums", "row_count", "freshness", "quarantine", "drift")
DEFAULTS = {"row_drop": 0.5, "warn_intervals": 2, "fail_intervals": 3, "interval_minutes": 1440}
PLAN_ID = re.compile(r"^plan-[0-9a-f]{6,64}$")


def table_parts(schemas_enabled: bool = True) -> list:
    return list(TABLE) if schemas_enabled else [None, TABLE_FLAT]


def interval_minutes(schedule: dict | None) -> int:
    """The pipeline's schedule as minutes between runs (pipeline_jobs.schedule_spec's shape); one day without one."""
    if schedule and schedule.get("every") == "hours" and int(schedule.get("hours") or 0) > 0:
        return int(schedule["hours"]) * 60
    return DEFAULTS["interval_minutes"]


# ------------------------------------------------------------------ verbatim notebook code -------------------------

# Shared by both notebooks: the table's shape, the write, and the alert. Plain Python on spark; the standard library only.
ALERT_CODE = r'''
import json
import urllib.request
from datetime import datetime, timezone

HEALTH_COLUMNS = ("run_id", "checked_at", "plan_id", "schema_fingerprint", "check", "object", "rule", "status", "count", "baseline")
HEALTH_DDL = ("run_id string, checked_at timestamp, plan_id string, schema_fingerprint string, `check` string, object string, "
              "rule string, status string, `count` bigint, baseline bigint")


def _hq(parts):
    return ".".join("`" + str(p).replace("`", "``") + "`" for p in parts if p)


def health_row(ctx, check, obj, rule, status, count=None, baseline=None):
    """One row of the health table: names, a rule, a status and counts. Never a row value."""
    assert status in ("pass", "warn", "fail"), status
    return {"run_id": ctx["run_id"], "checked_at": ctx["checked_at"], "plan_id": ctx["plan_id"],
            "schema_fingerprint": ctx["schema_fingerprint"], "check": check, "object": obj, "rule": rule or "",
            "status": status, "count": None if count is None else int(count), "baseline": None if baseline is None else int(baseline)}


def write_health(spark, parts, rows, fmt="delta"):
    """Append the rows to the health table (made on the first run); nothing is ever deleted or updated."""
    if not rows:
        return 0
    if parts[0]:
        spark.sql("CREATE SCHEMA IF NOT EXISTS " + _hq([parts[0]]))
    data = [tuple(r[c] for c in HEALTH_COLUMNS) for r in rows]
    spark.createDataFrame(data, HEALTH_DDL).write.format(fmt).mode("append").saveAsTable(_hq(parts))
    return len(data)


def _line(r):
    was = "" if r["baseline"] is None else f" (last run {r['baseline']})"
    n = "" if r["count"] is None else f": {r['count']}"
    rule = f" ({r['rule']})" if r["rule"] else ""
    return f"{r['status'].upper()} {r['check']} {r['object']}{rule}{n}{was}"


def alert_card(title, rows, alert_on="fail"):
    """The Adaptive Card a Teams workflow ("When a Teams webhook request is received") posts to a channel, or a Power
    Automate HTTP trigger forwards as an e-mail. Built from the health rows only, so it carries no row value."""
    shown = [r for r in rows if r["status"] == "fail" or (alert_on == "warn" and r["status"] == "warn")]
    body = [{"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "wrap": True}]
    body += [{"type": "TextBlock", "text": _line(r), "wrap": True, "spacing": "Small"} for r in shown[:30]]
    if len(shown) > 30:
        body.append({"type": "TextBlock", "text": f"... and {len(shown) - 30} more in the health table.", "wrap": True})
    if rows:
        body.append({"type": "TextBlock", "text": f"Run {rows[0]['run_id']}, plan {rows[0]['plan_id']}.", "wrap": True,
                     "spacing": "Small", "isSubtle": True})
    return {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None,
                                                "content": {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                                                            "type": "AdaptiveCard", "version": "1.4", "body": body}}]}


def _post(url, card):
    req = urllib.request.Request(url, data=json.dumps(card).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def alert(title, rows, key_vault, secret_name, alert_on, get_secret, post=None):
    """Posts the card when a check failed (or warned, with alert_on = "warn") and the owner set a Key Vault and a secret
    name. Returns what happened in words; never raises, so the run's own verdict decides, and the address (which carries
    its own signature) is never printed."""
    due = any(r["status"] == "fail" or (alert_on == "warn" and r["status"] == "warn") for r in rows)
    if not due:
        return "No alert: nothing failed."
    if not key_vault or not secret_name:
        return "No alert sent: no webhook is set (ALERT_KEY_VAULT and ALERT_SECRET_NAME on the pipeline)."
    try:
        url = get_secret(key_vault, secret_name)
    except Exception as e:  # noqa: BLE001 - the vault's own error may name more than we want in the run's output
        return f"No alert sent: the secret could not be read from the Key Vault ({type(e).__name__})."
    if not str(url or "").lower().startswith("https://"):
        return "No alert sent: the secret is not an https:// address (a Teams workflow or Power Automate HTTP trigger)."
    try:
        status = (post or _post)(url, alert_card(title, rows, alert_on))
    except Exception as e:  # noqa: BLE001 - the address is never shown
        return f"The alert could not be sent ({type(e).__name__}); the address is not shown."
    return f"Alert sent (HTTP {status})." if int(status or 0) < 300 else f"The webhook answered HTTP {status}."
'''.strip("\n") + "\n"


# The drift step, the first code cell of the pipeline's silver notebook. BUILT is the plan the outputs were built from:
# per source table its columns (and their types) and the columns silver and gold use.
DRIFT_CODE = r'''
class DriftBreaks(Exception):
    """Raised before anything is written when the source no longer has what silver or gold needs."""


def type_family(t):
    """Types compared by family: the plan reads them from the SQL endpoint (varchar, int, datetime2), Spark names them
    its own way (string, int, timestamp)."""
    t = str(t or "").lower().split("(")[0].strip()
    for family, names in (("text", ("string", "varchar", "nvarchar", "char", "nchar", "text", "ntext")),
                          ("integer", ("int", "integer", "bigint", "smallint", "tinyint", "long", "short", "byte")),
                          ("decimal", ("decimal", "numeric", "money", "smallmoney")),
                          ("float", ("float", "double", "real")),
                          ("bool", ("boolean", "bit", "bool")),
                          ("timestamp", ("timestamp", "datetime", "datetime2", "datetimeoffset", "smalldatetime", "timestamp_ntz")),
                          ("date", ("date",)),
                          ("binary", ("binary", "varbinary", "image"))):
        if t in names:
            return family
    return t


def drift(built, live, live_tables):
    """Findings, each {kind, table, column, breaking, why}. `built`: {"tables": {table: {"columns": {col: type},
    "uses": [col, ...]}}}; `live`: {table: {col: type} or None when the table is gone}; `live_tables`: every table in the
    source schema now."""
    out = []
    for t, b in sorted(built["tables"].items()):
        now = live.get(t)
        if now is None:
            out.append({"kind": "table_removed", "table": t, "column": "", "breaking": True,
                        "why": f"the source table {t} is gone; silver reads it"})
            continue
        low = {c.lower(): (c, ty) for c, ty in now.items()}
        uses = {u.lower() for u in b.get("uses", [])}
        for c, ty in sorted(b["columns"].items()):
            if c.lower() not in low:
                used = c.lower() in uses
                out.append({"kind": "column_removed", "table": t, "column": c, "breaking": used,
                            "why": (f"{t}.{c} is gone; a key, a relationship, an ordering or a gold view uses it" if used else
                                    f"{t}.{c} is gone; nothing Krusgraph built uses it")})
            elif type_family(ty) != type_family(low[c.lower()][1]):
                out.append({"kind": "type_changed", "table": t, "column": c, "breaking": False,
                            "why": f"{t}.{c} was {ty}, is now {low[c.lower()][1]}"})
        known = {c.lower() for c in b["columns"]}
        out += [{"kind": "column_added", "table": t, "column": c, "breaking": False, "why": f"{t}.{c} is new"}
                for c, _ty in sorted(now.items()) if c.lower() not in known]
    planned = {t.lower() for t in built["tables"]} | {t.lower() for t in built.get("other_tables", [])}
    out += [{"kind": "table_added", "table": t, "column": "", "breaking": False, "why": f"the table {t} is new"}
            for t in sorted(live_tables) if t.lower() not in planned]
    return out


def drift_rows(ctx, schema, findings):
    """Health rows for the drift step: one per finding (fail when it breaks silver or gold, warn otherwise), or one pass."""
    if not findings:
        return [health_row(ctx, "drift", schema, "plan", "pass", 0)]
    return [health_row(ctx, "drift", f"{schema}.{f['table']}" + (f".{f['column']}" if f["column"] else ""), f["kind"],
                       "fail" if f["breaking"] else "warn", 1) for f in findings]
'''.strip("\n") + "\n"


# The health step, in the check notebook after CHECK_CODE: it uses check()'s answer and adds row counts, freshness from
# Delta's table history (a commit time, never a value in the rows) and quarantine counts per rule.
HEALTH_CODE = r'''
# Commits in Delta's table history that write no rows: they do not make a table fresher.
NOT_A_WRITE = {"OPTIMIZE", "VACUUM START", "VACUUM END", "SET TBLPROPERTIES", "UNSET TBLPROPERTIES", "ADD COLUMNS",
               "CHANGE COLUMN", "REPLACE COLUMNS", "RENAME COLUMN", "DROP COLUMNS", "ADD CONSTRAINT", "DROP CONSTRAINT",
               "UPGRADE PROTOCOL", "FSCK", "REORG", "SET TBLPROPERTIES (CLUSTER BY)"}


def _lit(v):
    return "'" + str(v).replace("'", "''") + "'"


def previous_run(execute, exists, parts, plan_id, run_id):
    """{(check, object, rule): count} of the latest earlier run of the same plan; {} the first time."""
    name = _hq(parts)
    if not exists(name):
        return {}
    last = _one(execute, f"SELECT run_id FROM {name} WHERE plan_id = {_lit(plan_id)} AND run_id <> {_lit(run_id)} "
                         f"ORDER BY checked_at DESC LIMIT 1")
    if not last.get("run_id"):
        return {}
    rows = execute(f"SELECT `check` AS c, object AS o, rule AS r, `count` AS n FROM {name} "
                   f"WHERE plan_id = {_lit(plan_id)} AND run_id = {_lit(last['run_id'])}")
    return {(r["c"], r["o"], r["r"] or ""): (None if r["n"] is None else int(r["n"])) for r in rows}


def last_write(execute, name):
    """The time of the last commit that wrote rows, from Delta's table history (DESCRIBE HISTORY): a commit time, never a
    value in the rows. None when the table has no readable history."""
    for r in execute(f"DESCRIBE HISTORY {name} LIMIT 50"):
        op = str(r.get("operation") or "").upper()
        if op and op not in NOT_A_WRITE and not op.startswith("VACUUM"):
            return r.get("timestamp")
    return None


def _utc(t):
    if t is None:
        return None
    if isinstance(t, str):
        t = datetime.fromisoformat(t.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)      # Fabric's Spark sessions run in UTC


def freshness(ctx, sources, settings, history, previous):
    """Per source table the minutes since its last write: warn after `warn_intervals` schedule intervals, fail after
    `fail_intervals`."""
    rows = []
    every = settings["interval_minutes"]
    for s in sources:
        last = None
        for name in s.get("names") or [s["name"]]:        # a mirrored source: its OneLake path candidates, in order
            try:
                last = _utc(history(name))
            except Exception:  # noqa: BLE001 - a table without Delta history (a shortcut to files, say)
                continue
            if last is not None:
                break
        if last is None:
            rows.append(health_row(ctx, "freshness", s["object"], "no history", "warn", None))
            continue
        minutes = max(int((ctx["checked_at"] - last).total_seconds() // 60), 0)
        status = ("fail" if minutes > settings["fail_intervals"] * every else
                  "warn" if minutes > settings["warn_intervals"] * every else "pass")
        rows.append(health_row(ctx, "freshness", s["object"], "minutes since last write", status, minutes,
                               previous.get(("freshness", s["object"], "minutes since last write"))))
    return rows


def missing_objects(spec, exists):
    silver, gold = spec["silver_schema"], spec["gold_schema"]
    wanted = set(spec["health"]["silver_tables"]) | {k["table"] for k in spec["keys"]} | {v["fact"] for v in spec["views"]}
    out = [f"{silver}.{t}" for t in sorted(wanted) if not exists(_tbl(silver, t))]
    return out + [f"{gold}.{v['view']}" for v in spec["views"] if not exists(_tbl(gold, v["view"]))]


def health_rows(spec, result, execute, exists, ctx, previous, settings, history=None):
    """One row per check for this run. `result` is check()'s answer, or None when check() stopped on a missing table."""
    silver, gold, h = spec["silver_schema"], spec["gold_schema"], spec["health"]
    was = lambda c, o, r: previous.get((c, o, r or ""))                       # noqa: E731
    rows = []
    if result is None:
        rows += [health_row(ctx, "row_count", o, "missing", "fail", 0, was("row_count", o, "missing"))
                 for o in missing_objects(spec, exists)]
    else:
        for k, res in zip(spec["keys"], result["keys"]):
            o = f"{silver}.{k['table']}"
            status = "pass" if res["holds"] else ("fail" if res["enforced"] else "warn")
            rows.append(health_row(ctx, "key", o, k["rule"], status, res["nulls"] + res["duplicates"], was("key", o, k["rule"])))
        for rel, res in zip(spec["relationships"], result["relationships"]):
            o = f"{silver}.{rel['source']}.{'+'.join(rel['columns'])}"
            rows.append(health_row(ctx, "orphans", o, rel["rule"], "pass" if res["holds"] else "fail", res["orphans"],
                                   was("orphans", o, rel["rule"])))
        for j in result["joins"]:
            diff = abs(j["rows_after"] - j["rows_before"])
            rows.append(health_row(ctx, "join_rows", j["view"], "rows", "pass" if diff == 0 else "fail", diff,
                                   was("join_rows", j["view"], "rows")))
            if j["sums"]:                                  # pass or fail only: the number of amounts that differ, never a sum
                off = sum(1 for s in j["sums"] if not s["holds"])
                rows.append(health_row(ctx, "join_sums", j["view"], "sums", "pass" if off == 0 else "fail", off,
                                       was("join_sums", j["view"], "sums")))
        objects = [(f"{silver}.{t}", _tbl(silver, t)) for t in h["silver_tables"]]
        objects += [(f"{gold}.{v['view']}", _tbl(gold, v["view"])) for v in spec["views"]]
        for o, name in objects:
            n = int(_one(execute, f"SELECT COUNT(*) AS n FROM {name}").get("n") or 0)
            base = was("row_count", o, "rows")
            fell = base is not None and base > 0 and n <= base * (1 - settings["row_drop"])
            rows.append(health_row(ctx, "row_count", o, "rows", "warn" if fell else "pass", n, base))
    rows += freshness(ctx, h["sources"], settings, history or (lambda name: last_write(execute, name)), previous)
    q = _hq(h["quarantine"])
    if exists(q):
        counted = execute(f"SELECT source_table AS t, rule AS r, COUNT(*) AS n FROM {q} GROUP BY source_table, rule")
        for c in sorted(counted, key=lambda c: (str(c["t"]), str(c["r"]))):
            o = f"{silver}.{c['t']}"
            rows.append(health_row(ctx, "quarantine", o, c["r"], "warn" if int(c["n"] or 0) else "pass", c["n"],
                                   was("quarantine", o, c["r"])))
        if not counted:
            rows.append(health_row(ctx, "quarantine", ".".join(p for p in h["quarantine"] if p), "all", "pass", 0))
    return rows


def health_title(label, rows):
    fails = sum(r["status"] == "fail" for r in rows)
    warns = sum(r["status"] == "warn" for r in rows)
    if fails:
        return f"Krusgraph health for {label}: {fails} check(s) failed"
    return f"Krusgraph health for {label}: " + (f"{warns} warning(s)" if warns else "all checks passed")
'''.strip("\n") + "\n"

# The library runs the same text the notebooks run (the tests check that code). CHECK_CODE's helpers (_one, _tbl) come
# first, as in the check notebook.
_NS: dict = {}


def namespace() -> dict:
    """CHECK_CODE + ALERT_CODE + DRIFT_CODE + HEALTH_CODE executed together, as the notebooks execute them."""
    if not _NS:
        from .pipeline import CHECK_CODE
        exec(compile(CHECK_CODE + ALERT_CODE + DRIFT_CODE + HEALTH_CODE, "<krusgraph health notebook code>", "exec"), _NS)
    return _NS


# ------------------------------------------------------------------ the specs the notebooks carry -------------------

def health_spec(silver_spec: dict, plan_mark: dict, schedule: dict | None = None) -> dict:
    """What the check notebook's health step needs, as plain data: where the table is, the plan, the silver tables to
    count, the source tables whose freshness is read, the quarantine table and the schedule's interval."""
    src = silver_spec["source"]
    enabled = bool(src.get("schemas_enabled", True))
    read = sorted({t["table"] for t in silver_spec["tables"]}, key=str.lower)
    paths = _read_paths(src, read)
    return {"table": table_parts(enabled), "plan_id": plan_mark.get("plan_id") or "",
            "schema_fingerprint": plan_mark.get("schema_fingerprint") or "",
            "silver_tables": [t["table"] for t in silver_spec["tables"]],
            "sources": [{"name": paths[t][0], "names": paths[t], "object": f"{src['schema']}.{t}"} if paths else
                        {"name": _hq([src["schema"] if enabled else None, t]), "object": f"{src['schema']}.{t}"} for t in read],
            "quarantine": list(silver_spec["quarantine"]), "interval_minutes": interval_minutes(schedule)}


def _read_paths(src: dict, tables) -> dict:
    """n201's read-only sources (a mirrored database) are read by their OneLake path, Tables/<schema>/<table> when it
    holds a Delta log, else Tables/<table> (silver.MIRROR_SOURCE): per table those two names, as delta.`<path>`."""
    rf = src.get("read_from") or {}
    if not rf.get("tables_path"):
        return {}
    base = str(rf["tables_path"]).rstrip("/")
    schema = src["schema"] if src.get("schemas_enabled", True) else None

    def name(path):
        return "delta.`" + path.replace("`", "``") + "`"
    return {t: ([name(f"{base}/{schema}/{t}")] if schema else []) + [name(f"{base}/{t}")] for t in tables}


def _hq(parts) -> str:
    return ".".join("`" + str(p).replace("`", "``") + "`" for p in parts if p)


def drift_spec(plan, silver_spec: dict, gold_spec: dict, plan_mark: dict) -> dict:
    """What the silver notebook's drift step compares with: per source table silver reads, the columns and types of the
    plan the outputs were built from, and the columns a key, a relationship, an ordering or a gold view uses."""
    src = silver_spec["source"]
    tables = {t["table"]: t for t in silver_spec["tables"]}
    uses: dict[str, set] = {t: set(x["key"]) | ({x["order_by"]} if x.get("order_by") else set()) for t, x in tables.items()}
    for t, x in tables.items():
        for c in x["checks"]:
            uses[t] |= set(c["columns"])
            if c["parent"] in uses:
                uses[c["parent"]] |= set(c["parent_columns"])
    for v in gold_spec.get("views", []):
        for c in v["columns"]:
            if c["table"] in uses:
                uses[c["table"]].add(c["column"])
    built = {t: {"columns": {c.name: (c.data_type or "").lower() for c in plan.schema[t].columns},
                 "uses": sorted(uses[t], key=str.lower)} for t in sorted(tables, key=str.lower)}
    others = [t for t in src.get("tables", []) if t not in tables]
    return {"read_paths": _read_paths(src, sorted(tables)), "schema": src["schema"], "schemas_enabled": bool(src.get("schemas_enabled", True)), "tables": built,
            "other_tables": others, "table": table_parts(bool(src.get("schemas_enabled", True))),
            "plan_id": plan_mark.get("plan_id") or "", "schema_fingerprint": plan_mark.get("schema_fingerprint") or ""}


def _py(value) -> str:
    return _py_literal(value, indent=4, sort_keys=True)


# The pipeline hands these to both notebooks (pipeline.pipeline_content); the owner sets the three alert ones on the
# pipeline in Fabric. Empty means no alert.
ALERT_PARAMETERS = ("alert_key_vault", "alert_secret_name", "alert_on")

ALERT_PARAMS_TEXT = (
    'RUN_ID = ""             # the pipeline run id (the pipeline sets it); empty when the notebook is run by hand\n'
    'ALERT_KEY_VAULT = ""    # https://<vault>.vault.azure.net/ holding the webhook address; set on the pipeline in Fabric\n'
    'ALERT_SECRET_NAME = ""  # the secret whose value is the Teams workflow or Power Automate HTTP trigger address\n'
    'ALERT_ON = "fail"       # "fail": a card when a check fails; "warn": also on warnings')

RUN_CONTEXT = (
    "import uuid\n\n"
    "def _get_secret(vault, name):\n"
    "    # the signed-in identity of the run reads the owner's Key Vault (Learn: microsoft-spark-utilities, getSecret)\n"
    "    try:\n"
    "        return notebookutils.credentials.getSecret(vault, name)\n"
    "    except NameError:\n"
    "        return mssparkutils.credentials.getSecret(vault, name)\n\n"
    "HEALTH_CTX = {'run_id': RUN_ID or ('manual-' + uuid.uuid4().hex[:12]), 'checked_at': datetime.now(timezone.utc).replace(microsecond=0),\n"
    "              'plan_id': HEALTH['plan_id'], 'schema_fingerprint': HEALTH['schema_fingerprint']}")


def drift_cell(d: dict, label: str) -> str:
    """The silver notebook's drift step: plain Python on spark, before the setup cell, so nothing is written when it stops."""
    src = "q(SOURCE_SCHEMA_D, t)" if d["schemas_enabled"] else "q(t)"
    return ("# ---- n200: drift against the plan this pipeline was built from, before anything is written ----\n"
            "# A source table gone, or a column a key, a relationship, an ordering or a gold view uses, stops the run here with the\n"
            "# reason. A new table, a new column, a column nothing uses dropped or a changed type is recorded and the run goes on.\n"
            "# Every finding is a row in the health table (names and counts, never a row value).\n"
            + ALERT_CODE + "\n" + DRIFT_CODE + "\n"
            f"HEALTH = {_py({k: d[k] for k in ('table', 'plan_id', 'schema_fingerprint')})}\n"
            f"BUILT = {_py({'tables': d['tables'], 'other_tables': d['other_tables']})}\n"
            f"SOURCE_SCHEMA_D = {_py_literal(d['schema'])}\n"
            f"LABEL_D = {_py_literal(label)}\n"
            + RUN_CONTEXT + "\n\n"
            "def q(*parts):\n    return '.'.join('`' + str(p).replace('`', '``') + '`' for p in parts if p)\n\n"
            + (_live_by_path(d) if d.get("read_paths") else
               "live = {}\n"
               "for t in BUILT['tables']:\n"
               f"    name = {src}\n"
               "    live[t] = ({f.name: f.dataType.simpleString() for f in spark.table(name).schema.fields}\n"
               "               if spark.catalog.tableExists(name) else None)\n"
               + ("live_tables = [x.name for x in spark.catalog.listTables(SOURCE_SCHEMA_D)]\n" if d["schemas_enabled"] else
                  "live_tables = []      # a lakehouse without schemas: new tables are not listed\n"))
            + "findings = drift(BUILT, live, live_tables)\n"
            "drift_found = drift_rows(HEALTH_CTX, SOURCE_SCHEMA_D, findings)\n"
            "for f in findings:\n    print(('STOPS: ' if f['breaking'] else 'recorded: ') + f['why'])\n"
            "print(f\"Drift against plan {HEALTH['plan_id']}: {len(findings)} finding(s).\")\n"
            "write_health(spark, HEALTH['table'], drift_found, TABLE_FORMAT)\n"
            "breaks = [f for f in findings if f['breaking']]\n"
            "if breaks:\n"
            "    print(alert(f'Krusgraph drift stopped the pipeline for {LABEL_D}', drift_found, ALERT_KEY_VAULT, ALERT_SECRET_NAME,\n"
            "                ALERT_ON, _get_secret))\n"
            "    raise DriftBreaks('The source no longer matches the plan this pipeline was built from, so the run stops before '\n"
            "                      'anything is written: ' + '; '.join(f['why'] for f in breaks) + '. Review the plan again in the '\n"
            "                      'Krusgraph Model item and Update the pipeline.')")


def _live_by_path(d: dict) -> str:
    """The drift cell's reading of a read-only source (n201): each table by its OneLake path, the first that reads."""
    return (f"READ_PATHS = {_py(d['read_paths'])}   # a read-only source: its tables by their OneLake path\n"
            "live = {}\n"
            "for t in BUILT['tables']:\n"
            "    live[t] = None\n"
            "    for name in READ_PATHS.get(t, []):\n"
            "        try:\n"
            "            live[t] = {f.name: f.dataType.simpleString() for f in spark.table(name).schema.fields}\n"
            "            break\n"
            "        except Exception:  # noqa: BLE001 - not this layout, or the table is gone\n"
            "            continue\n"
            "live_tables = []      # a read-only source: new tables are not listed here\n")


def check_health_cells(spec: dict, label: str) -> list[tuple[str, str]]:
    """The check notebook's health code cell and its run cell (they replace the plain count cell)."""
    code = ("# n200: health over time. One row per check in the health table; the alert when a check fails.\n"
            + ALERT_CODE + "\n" + HEALTH_CODE)
    run = ("# 1. Count in the silver tables and the gold views, and keep one row per check in the health table.\n"
           + RUN_CONTEXT + "\n\n"
           "def execute(sql):\n    return [r.asDict() for r in spark.sql(sql).collect()]\n\n"
           "SETTINGS = {'row_drop': ROW_COUNT_DROP, 'warn_intervals': FRESHNESS_WARN_INTERVALS,\n"
           "            'fail_intervals': FRESHNESS_FAIL_INTERVALS, 'interval_minutes': SCHEDULE_MINUTES}\n"
           "previous = previous_run(execute, spark.catalog.tableExists, HEALTH['table'], HEALTH['plan_id'], HEALTH_CTX['run_id'])\n"
           "stopped = None\n"
           "try:\n    result = check(CHECK, execute, spark.catalog.tableExists)\n"
           "except CheckFailed as e:\n    result, stopped = None, e\n"
           "health = health_rows(CHECK, result, execute, spark.catalog.tableExists, HEALTH_CTX, previous, SETTINGS)\n"
           "write_health(spark, HEALTH['table'], health, TABLE_FORMAT)\n"
           "for line in (result['lines'] if result else [str(stopped)]):\n    print(line)\n"
           "print(f\"Health: {len(health)} row(s) for run {HEALTH_CTX['run_id']}: \"\n"
           "      + ', '.join(f\"{sum(r['status'] == s for r in health)} {s}\" for s in ('pass', 'warn', 'fail')))\n"
           f"print(alert(health_title({_py_literal(label)}, health), health, ALERT_KEY_VAULT, ALERT_SECRET_NAME, ALERT_ON, _get_secret))\n"
           "if stopped is not None:\n    raise stopped")
    return [("code", code), ("code", run)]


HEALTH_PARAMS_TEXT = (
    "TABLE_FORMAT = \"delta\"         # the health table is a Delta table; leave as it is\n"
    "ROW_COUNT_DROP = 0.5           # warn when a table's rows fall by this share or more since the last run of this plan\n"
    "FRESHNESS_WARN_INTERVALS = 2   # warn when a source table was last written more than this many schedule intervals ago\n"
    "FRESHNESS_FAIL_INTERVALS = 3   # fail after this many\n")


# ------------------------------------------------------------------ what the item reads -----------------------------

def read_sql(schemas_enabled: bool, plan_ids: list[str]) -> str:
    """T-SQL for the lakehouse's SQL analytics endpoint: every row of the latest run of each plan. Plan ids are checked
    against PLAN_ID before they get here, so the literal is safe."""
    for p in plan_ids:
        if not PLAN_ID.match(p):
            raise ValueError(f"not a plan id: {p!r}")
    name = "[krusgraph].[health]" if schemas_enabled else "[dbo].[krusgraph_health]"
    ids = ", ".join(f"'{p}'" for p in plan_ids)
    return (f"WITH last AS (SELECT plan_id, run_id, ROW_NUMBER() OVER (PARTITION BY plan_id ORDER BY checked_at DESC) AS rn "
            f"FROM {name} WHERE plan_id IN ({ids})) "
            f"SELECT h.run_id, h.checked_at, h.plan_id, h.[check], h.[object], h.[rule], h.[status], h.[count], h.[baseline] "
            f"FROM {name} AS h JOIN last AS l ON l.plan_id = h.plan_id AND l.run_id = h.run_id AND l.rn = 1")


def exists_sql(schemas_enabled: bool) -> str:
    schema, table = ("krusgraph", "health") if schemas_enabled else ("dbo", "krusgraph_health")
    return (f"SELECT COUNT(*) AS n FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = '{schema}' AND TABLE_NAME = '{table}'")


FINDING_FIELDS = ("check", "object", "rule", "status", "count", "baseline")
_ORDER = {"fail": 0, "warn": 1, "pass": 2}


def _iso(v) -> str | None:
    if v is None:
        return None
    text = v.isoformat() if hasattr(v, "isoformat") else str(v)
    return text.replace("+00:00", "Z")


def summarize(rows: list[dict], products: list[dict]) -> list[dict]:
    """One entry per data product ({name, plan_id}): its health word and the open findings of its latest run.
    red: a check failed; amber: a warning, or the check notebook wrote nothing in that run (it stopped before the check,
    or is still running); green: every check passed; not checked yet: no run of this plan is in the table."""
    low = [{str(k).lower(): v for k, v in r.items()} for r in rows]
    out = []
    for p in products:
        mine = [r for r in low if r.get("plan_id") == p["plan_id"]]
        entry = {"name": p["name"], "plan_id": p["plan_id"], "health": NOT_CHECKED, "run_id": None, "checked_at": None,
                 "checks": 0, "findings": []}
        if mine:
            findings = [{f: (r.get(f) if f not in ("count", "baseline") or r.get(f) is None else int(r[f])) for f in FINDING_FIELDS}
                        for r in mine if r.get("status") in ("warn", "fail")]
            if not any(r.get("check") != "drift" for r in mine) and not any(r.get("status") == "fail" for r in mine):
                findings.append({"check": "run", "object": "", "rule": "", "status": "warn", "count": None, "baseline": None,
                                 "why": "the check notebook wrote nothing in this run: the run stopped before it, or is still running"})
            findings.sort(key=lambda f: (_ORDER.get(f["status"], 3), f["check"], f["object"]))
            statuses = {f["status"] for f in findings}
            entry.update(health="red" if "fail" in statuses else "amber" if "warn" in statuses else "green",
                         run_id=mine[0].get("run_id"), checked_at=_iso(max((r.get("checked_at") for r in mine), key=lambda x: str(x))),
                         checks=len(mine), findings=findings)
        out.append(entry)
    return out
