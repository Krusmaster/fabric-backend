"""Silver tables from the plan: a PySpark notebook for a Fabric lakehouse that turns the source tables into clean
copies in a schema of their own, with every step commented with the rule that motivates it.

Per table, in the order of the relationships (a parent before the tables that point at it):
  1. read the source table (never written: the targets are in another schema, or carry a prefix on a lakehouse
     without schemas, and a guard in the notebook refuses to start if a target would be a source table);
  2. rows whose key is NULL go to quarantine (the key's rule, K0-K5);
  3. rows that share a key: the latest by the ordering column wins (`order_by`, else a column named like updated_at /
     modified / ingested_at / __timestamp); without one, one row per key by a content hash, so a re-run keeps the same
     row; the others go to quarantine;
  4. per relationship (R0-R4 or confirmed): rows whose reference has no row in the parent's silver table go to
     quarantine with the reason; a NULL reference stays (it says "unknown", not "wrong");
  5. the result is written as a Delta table, overwritten on every run (idempotent), and marked with the table
     property krusgraph.silver = <lakehouse id>/<schema>; a target without that mark (or with another source's) is never
     overwritten. A table that points at itself is checked again until no more rows drop out.
At the end the quarantine table (krusgraph_quarantine: source_table, rule, reason, row_json, checked_at) is rewritten
with this run's rows, and a summary is printed. Keyless tables (K3) are copied without de-duplication.

`spec()` is the plan of the notebook as data; `cells()` renders it as PySpark; `simulate()` runs the same steps on
Python rows (the tests run both on the shop seed and compare). Nothing here talks to Fabric.
"""
from __future__ import annotations

import hashlib
import json
import re

from . import notebook as _nb
from .infer import Plan, PlanInputError, RULES, _norm

QUARANTINE = "krusgraph_quarantine"
ORDER_NAMES = ("updatedat", "lastupdated", "lastupdate", "updateddate", "modifiedat", "modified", "lastmodified", "modifieddate",
               "changedat", "changedate", "ingestedat", "ingestiontime", "loadedat", "loadts", "loaddate", "loadtimestamp",
               "etlloadedat", "timestamp", "ts", "insertedat", "createdat", "createddate")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,99}$")


def _rule_text(rule: str | None) -> str:
    if not rule:
        return ""
    return RULES.get(rule, rule).split(";")[0].split(" — ")[0]


def _order_column(table, given: str | None) -> tuple[str | None, str]:
    if given:
        hit = next((c for c in table.column_names if c.lower() == given.lower()), None)
        if hit is None:
            raise PlanInputError(f"order_by: {table.name} has no column {given!r}; list_tables shows its columns")
        return hit, "given in order_by"
    by_norm = {_norm(c): c for c in table.column_names}
    for n in ORDER_NAMES:
        if n in by_norm:
            return by_norm[n], f"named like a load or change time ({by_norm[n]})"
    return None, ""


def _topological(names: list[str], edges: list[tuple[str, str]]) -> list[str]:
    """Parents first (edges are parent -> child); tables in a cycle keep name order after the rest."""
    incoming = {n: {p for p, c in edges if c == n and p != n and p in names} for n in names}
    order: list[str] = []
    ready = sorted(n for n in names if not incoming[n])
    while ready:
        n = ready.pop(0)
        order.append(n)
        for m in sorted(names):
            if m not in order and m not in ready and n in incoming[m]:
                incoming[m].discard(n)
                if not incoming[m]:
                    ready.append(m)
        ready.sort()
    return order + sorted(n for n in names if n not in order)


def spec(plan: Plan, info: dict, silver_schema: str = "silver", order_by: dict | None = None, tables: list[str] | None = None) -> dict:
    """The notebook's plan: per table the key and its rule, the ordering column and why, the references to check with
    their rules, and the target. Raises PlanInputError for a schema or order_by that cannot work."""
    schema = info.get("schema") or plan.schema.schema
    schemas_enabled = bool(info.get("schemas_enabled", True))
    silver_schema = (silver_schema or "").strip()
    if not _IDENT.match(silver_schema):
        raise PlanInputError("silver_schema: letters, digits and underscores, starting with a letter (for example 'silver')")
    if schemas_enabled and silver_schema.lower() == schema.lower():
        raise PlanInputError(f"silver_schema {silver_schema!r} is the source schema; the silver tables need a schema of their own")
    names = {t.name.lower(): t.name for t in plan.schema}
    if not schemas_enabled:
        # Without schemas the silver tables sit beside the sources as <silver_schema>_*, so a re-plan after the first run
        # lists them: they are this notebook's outputs, not sources (the run-time mark keeps it off any other table).
        names = {k: v for k, v in names.items() if not k.startswith(silver_schema.lower() + "_") and k != QUARANTINE}
    chosen = sorted(names.values(), key=str.lower)
    if tables:
        missing = [t for t in tables if t.lower() not in names]
        if missing:
            raise PlanInputError("tables: not in the schema: " + ", ".join(repr(m) for m in missing))
        chosen = sorted({names[t.lower()] for t in tables}, key=str.lower)
    unknown = [t for t in (order_by or {}) if t.lower() not in names]
    if unknown:
        raise PlanInputError("order_by: not in the schema: " + ", ".join(repr(u) for u in unknown))
    given = {names[k.lower()]: v for k, v in (order_by or {}).items()}

    def target(t: str) -> list:
        return [silver_schema, t] if schemas_enabled else [None, f"{silver_schema}_{t}"]
    sources = {(t.lower() if not schemas_enabled else f"{schema}.{t}".lower()) for t in names.values()}
    for t in chosen + [QUARANTINE]:
        tgt = target(t)
        full = (tgt[1] if not schemas_enabled else f"{tgt[0]}.{tgt[1]}").lower()
        if full in sources:
            raise PlanInputError(f"the silver table for {t} would be {full}, which is a source table; choose another silver_schema")

    edges = [(r.target, r.source) for r in plan.relationships if r.source in chosen]
    order = _topological(chosen, [(p, c) for p, c in edges if p in chosen])
    out_tables = []
    for t in order:
        table = plan.schema[t]
        key, key_rule = plan.keys.get(t, ([], None))
        col, why = _order_column(table, given.get(t)) if key else (None, "")
        checks = []
        for r in plan.relationships:
            if r.source != t:
                continue
            checks.append({"columns": list(r.source_cols), "parent": r.target, "parent_columns": list(r.target_cols), "rule": r.rule,
                           "parent_from": "silver" if (r.target in chosen and (order.index(r.target) < order.index(t) or r.target == t)) else
                                          ("source_cycle" if r.target in chosen else "source"),
                           "note": r.note})
        out_tables.append({"table": t, "target": target(t), "key": list(key), "key_rule": key_rule if key else "K3",
                           "order_by": col, "order_why": why, "checks": checks})
    owner = f"{info.get('item_id') or info.get('item_name') or 'lakehouse'}/{schema}"
    return {"source": {"item": info.get("item_name") or "", "item_id": info.get("item_id") or "", "workspace_id": info.get("workspace_id") or "",
                       "schema": schema, "schemas_enabled": schemas_enabled, "tables": sorted(names.values(), key=str.lower), "owner": owner},
            "silver_schema": silver_schema, "quarantine": target(QUARANTINE), "tables": out_tables,
            "not_checked": [{"table": a["table"], "column": a["column"], "why": "ambiguous: it could point at " + " or ".join(a["candidates"])}
                            for a in plan.ambiguous if a["table"] in chosen]}


# ------------------------------------------------------------------ the notebook ---------------------------------

def _py(value) -> str:
    """A Python literal for a string, a list of strings, or None."""
    return "None" if value is None else json.dumps(value)


SETUP = '''from datetime import datetime, timezone
from pyspark.sql import Window
from pyspark.sql import functions as F

SOURCE_SCHEMA = {source_schema}
SCHEMAS_ENABLED = {schemas_enabled}
# Written into every silver table as the property krusgraph.silver: a table carrying another value (or none) belongs to
# someone else, and this notebook never overwrites it.
OWNER = {owner}
# Every table of the source schema: none of them is ever a write target.
SOURCE_TABLES = {source_tables}
# The silver tables this notebook writes, plus the quarantine table.
WRITES = {writes}
RUN_AT = datetime.now(timezone.utc).replace(microsecond=0)


def q(*parts):
    """A table name with every part quoted, for names with spaces or other characters."""
    return ".".join("`" + str(p).replace("`", "``") + "`" for p in parts if p)


def source(table):
    return q(SOURCE_SCHEMA, table) if SCHEMAS_ENABLED else q(table)


def target(table):
    # The silver tables live in a schema of their own (on a lakehouse without schemas: a prefix), never on a source table.
    return q(SILVER_SCHEMA, table) if SCHEMAS_ENABLED else q(f"{{SILVER_SCHEMA}}_{{table}}")


def col(name):
    return F.col("`" + name.replace("`", "``") + "`")


def is_ours_or_absent(name):
    """A target may be overwritten only if this notebook wrote it before (table property krusgraph.silver = OWNER)."""
    if not spark.catalog.tableExists(name):
        return True
    props = {{r[0]: r[1] for r in spark.sql(f"SHOW TBLPROPERTIES {{name}}").collect()}}
    return props.get("krusgraph.silver") == OWNER


# Guard before anything is written: no target is a source table, and no target is someone else's table.
_sources = {{source(t).lower() for t in SOURCE_TABLES}}
for _t in WRITES:
    if target(_t).lower() in _sources:
        raise ValueError(f"{{target(_t)}} is a source table; choose another SILVER_SCHEMA. Nothing was written.")
    if not is_ours_or_absent(target(_t)):
        raise ValueError(f"{{target(_t)}} exists and was not written by this notebook (for {{OWNER}}); nothing was written. "
                         "Choose another SILVER_SCHEMA.")
if SCHEMAS_ENABLED:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {{q(SILVER_SCHEMA)}}")

quarantined = []      # (rows, source table, rule, reason), written together at the end
silver = {{}}           # table -> its silver DataFrame, read back after writing
read_counts = {{}}


def to_quarantine(rows, table, rule, reason):
    quarantined.append(rows.select(F.lit(table).alias("source_table"), F.lit(rule).alias("rule"), F.lit(reason).alias("reason"),
                                   F.to_json(F.struct(*[col(c) for c in rows.columns])).alias("row_json")))


def drop_null_keys(df, key, table, rule):
    missing = None
    for c in key:
        missing = col(c).isNull() if missing is None else (missing | col(c).isNull())
    to_quarantine(df.filter(missing), table, rule, f"the key ({{', '.join(key)}}) is NULL")
    return df.filter(~missing)


def keep_latest(df, key, order_column, table, rule):
    content = F.sha2(F.to_json(F.struct(*[col(c) for c in df.columns])), 256)
    order = ([col(order_column).desc_nulls_last()] if order_column else []) + [content.desc()]
    ranked = df.withColumn("_krusgraph_rank", F.row_number().over(Window.partitionBy(*[col(c) for c in key]).orderBy(*order)))
    reason = (f"another row has the same key ({{', '.join(key)}}); the row with the latest {{order_column}} was kept" if order_column
              else f"another row has the same key ({{', '.join(key)}}); one row per key was kept (no ordering column: pass order_by)")
    to_quarantine(ranked.filter(F.col("_krusgraph_rank") > 1).drop("_krusgraph_rank"), table, rule, reason)
    return ranked.filter(F.col("_krusgraph_rank") == 1).drop("_krusgraph_rank")


def check_reference(df, columns, parent_df, parent_columns, table, rule, reason):
    """Rows whose reference (every column set) finds no row in the parent go to quarantine; a NULL reference stays."""
    parent_keys = parent_df.select(*[col(c).alias(f"_krusgraph_p{{i}}") for i, c in enumerate(parent_columns)]).distinct()
    has_ref, on = None, None
    for i, c in enumerate(columns):
        has_ref = col(c).isNotNull() if has_ref is None else (has_ref & col(c).isNotNull())
        match = col(c) == F.col(f"_krusgraph_p{{i}}")
        on = match if on is None else (on & match)
    with_ref = df.filter(has_ref)
    to_quarantine(with_ref.join(parent_keys, on, "left_anti"), table, rule, reason)
    return df.filter(~has_ref).unionByName(with_ref.join(parent_keys, on, "left_semi"))


def write_silver(df, table):
    name = target(table)
    if not is_ours_or_absent(name):
        raise ValueError(f"{{name}} exists and was not written by this notebook; it was left as it is.")
    df.write.format(TABLE_FORMAT).mode("overwrite").option("overwriteSchema", "true").saveAsTable(name)
    spark.sql(f"ALTER TABLE {{name}} SET TBLPROPERTIES ('krusgraph.silver' = '{{OWNER.replace(chr(39), chr(39) * 2)}}')")
    return spark.read.table(name)
'''


def _key_comment(t: dict) -> list[str]:
    if t["key_rule"] == "K3" or not t["key"]:
        return [f"# No key (rule K3: {_rule_text('K3')}): every row is kept as it is; nothing to de-duplicate on."]
    lines = [f"# Key {' + '.join(t['key'])} (rule {t['key_rule']}: {_rule_text(t['key_rule'])}).",
             "# A key identifies one row: rows without a key go to quarantine, and of rows that share a key only one is kept."]
    if t["order_by"]:
        lines.append(f"# Latest row wins by {t['order_by']} ({t['order_why']}).")
    else:
        lines.append("# No ordering column (none given in order_by, none named like updated_at): the kept row is chosen by a content hash, so a re-run keeps the same one.")
    return lines


def _table_cell(t: dict) -> str:
    name = t["table"]
    out = [f"# ---- {name} -> {'.'.join(x for x in t['target'] if x)} ----", *_key_comment(t),
           f"df = spark.read.table(source({_py(name)}))", f"read_counts[{_py(name)}] = df.count()"]
    if t["key"]:
        out += [f"df = drop_null_keys(df, {_py(t['key'])}, {_py(name)}, {_py(t['key_rule'])})",
                f"df = keep_latest(df, {_py(t['key'])}, {_py(t['order_by'])}, {_py(name)}, {_py(t['key_rule'])})"]
    for c in t["checks"]:
        on = " and ".join(f"{name}.{a} = {c['parent']}.{b}" for a, b in zip(c["columns"], c["parent_columns"]))
        reason = f"{', '.join(c['columns'])} has no row in {c['parent']} ({on})"
        out.append(f"# Reference {on} (rule {c['rule']}: {_rule_text(c['rule'])}"
                   + (f"; {c['note']}" if c.get("note") else "") + ").")
        if c["parent_from"] == "silver" and c["parent"] != name:
            out.append(f"# Checked against the silver {c['parent']}, so rows whose {c['parent']} was quarantined follow it there.")
            parent = f"silver[{_py(c['parent'])}]"
        elif c["parent"] == name:
            out += ["# The table points at itself: checked against its own rows, again until no more rows drop out, so a row whose",
                    "# parent was quarantined follows it there (at most 100 rounds: the depth of the hierarchy).",
                    "for _round in range(100):",
                    "    _before = df.count()",
                    f"    df = check_reference(df, {_py(c['columns'])}, df, {_py(c['parent_columns'])}, {_py(name)}, {_py(c['rule'])}, {_py(reason)})",
                    "    df = df.localCheckpoint()",
                    "    if df.count() == _before:",
                    "        break"]
            continue
        elif c["parent_from"] == "source_cycle":
            out.append(f"# {c['parent']} is part of a cycle of references and comes later: checked against its source rows.")
            parent = f"spark.read.table(source({_py(c['parent'])}))"
        else:
            out.append(f"# {c['parent']} is not part of this notebook: checked against its source table.")
            parent = f"spark.read.table(source({_py(c['parent'])}))"
        out.append(f"df = check_reference(df, {_py(c['columns'])}, {parent}, {_py(c['parent_columns'])}, {_py(name)}, {_py(c['rule'])}, {_py(reason)})")
    out.append(f"silver[{_py(name)}] = write_silver(df, {_py(name)})")
    return "\n".join(out)


FINISH = '''# ---- quarantine and summary ----
# Every row left out above is in the quarantine table with its source table, the rule and the reason. The table is
# rewritten on every run, so it always shows the latest run.
q_rows = spark.createDataFrame([], "source_table string, rule string, reason string, row_json string")
for part in quarantined:
    q_rows = q_rows.unionByName(part)
q_rows = q_rows.withColumn("checked_at", F.lit(RUN_AT))
write_silver(q_rows, {quarantine})
summary = {{t: {{"read": read_counts[t], "silver": silver[t].count()}} for t in silver}}
for r in spark.read.table(target({quarantine})).groupBy("source_table", "rule", "reason").count().collect():
    summary[r["source_table"]].setdefault("quarantined", []).append({{"rule": r["rule"], "reason": r["reason"], "rows": r["count"]}})
for t, s in summary.items():
    print(t, s)
'''


def cells(s: dict) -> list[tuple[str, str]]:
    src = s["source"]
    intro = (f"# Silver tables for {src['item'] or 'the lakehouse'}.{src['schema']}\n\n"
             f"Generated by Krusgraph from the plan: clean copies of {len(s['tables'])} table(s) in "
             + (f"the schema `{s['silver_schema']}`" if src["schemas_enabled"] else f"tables prefixed `{s['silver_schema']}_`")
             + ", de-duplicated on each table's key and with every reference checked; rows that fail a check are kept in "
             f"`{QUARANTINE}` with the reason. The source tables are only read. Run it again at any time: every silver table "
             "is rewritten from the source. Each step below names the rule (K0–K5, R0–R4) that motivates it.")
    params = (f"SILVER_SCHEMA = {_py(s['silver_schema'])}   # where the silver tables go; never the source schema\n"
              'TABLE_FORMAT = "delta"     # lakehouse tables are Delta; leave as it is')
    writes = [t["table"] for t in s["tables"]] + [QUARANTINE]
    setup = SETUP.format(source_schema=_py(src["schema"] if src["schemas_enabled"] else None),
                         schemas_enabled="True" if src["schemas_enabled"] else "False",
                         source_tables=_py(src["tables"]), writes=_py(writes), owner=_py(src["owner"]))
    out = [("markdown", intro), ("parameters", params), ("code", setup.strip("\n"))]
    out += [("code", _table_cell(t)) for t in s["tables"]]
    out.append(("code", FINISH.format(quarantine=_py(QUARANTINE)).strip("\n")))
    return out


def notebook_source(s: dict) -> str:
    src = s["source"]
    meta = _nb.notebook_metadata(src["workspace_id"], src["item_id"], src["item"]) if src["item_id"] else _nb.notebook_metadata()
    return _nb.fabric_source(cells(s), meta)


def steps(s: dict) -> list[dict]:
    """The same plan in words, one entry per table, for the answer a person reads."""
    out = []
    for t in s["tables"]:
        entry = {"table": t["table"], "writes": ".".join(x for x in t["target"] if x)}
        if t["key"]:
            entry["deduplicate_on"] = {"key": t["key"], "rule": t["key_rule"],
                                       "latest_by": t["order_by"] or "none (a stable row per key; pass order_by)"}
        else:
            entry["deduplicate_on"] = "no key (K3): rows kept as they are"
        entry["checks"] = [{"columns": c["columns"], "parent": c["parent"], "rule": c["rule"]} for c in t["checks"]]
        out.append(entry)
    return out


# ------------------------------------------------------------------ the same steps in Python ---------------------

def _content_hash(row: dict, columns: list[str]) -> str:
    return hashlib.sha256(json.dumps({c: row.get(c) for c in columns}, default=str, sort_keys=False).encode()).hexdigest()


def simulate(s: dict, data: dict[str, list[dict]]) -> dict:
    """Run the notebook's steps on rows in memory: {"silver": {table: rows}, "quarantine": [{source_table, rule, reason,
    row}]}. Ties without an ordering column are broken by a content hash like the notebook's, but not the same hash
    (Spark's JSON differs), so with such ties only the counts are comparable."""
    silver: dict[str, list[dict]] = {}
    quarantine: list[dict] = []
    deduped: dict[str, list[dict]] = {}
    for t in s["tables"]:
        name = t["table"]
        rows = [dict(r) for r in data.get(name, [])]
        columns = list(rows[0].keys()) if rows else []
        if t["key"]:
            null_key = [r for r in rows if any(r.get(c) is None for c in t["key"])]
            quarantine += [{"source_table": name, "rule": t["key_rule"], "reason": f"the key ({', '.join(t['key'])}) is NULL", "row": r} for r in null_key]
            rows = [r for r in rows if r not in null_key]
            groups: dict[tuple, list[dict]] = {}
            for r in rows:
                groups.setdefault(tuple(r.get(c) for c in t["key"]), []).append(r)
            kept = []
            for group in groups.values():
                group.sort(key=lambda r: (r.get(t["order_by"]) is not None, r.get(t["order_by"]) if t["order_by"] and r.get(t["order_by"]) is not None else 0,
                                          _content_hash(r, columns)), reverse=True)
                kept.append(group[0])
                reason = (f"another row has the same key ({', '.join(t['key'])}); the row with the latest {t['order_by']} was kept" if t["order_by"]
                          else f"another row has the same key ({', '.join(t['key'])}); one row per key was kept (no ordering column: pass order_by)")
                quarantine += [{"source_table": name, "rule": t["key_rule"], "reason": reason, "row": r} for r in group[1:]]
            rows = kept
        deduped[name] = rows
        for c in t["checks"]:
            if c["parent"] == name:
                parent_rows = rows
            elif c["parent_from"] == "silver":
                parent_rows = silver[c["parent"]]
            else:
                parent_rows = data.get(c["parent"], [])
            on = " and ".join(f"{name}.{a} = {c['parent']}.{b}" for a, b in zip(c["columns"], c["parent_columns"]))
            reason = f"{', '.join(c['columns'])} has no row in {c['parent']} ({on})"
            for _round in range(100 if c["parent"] == name else 1):     # a self-reference: until no more rows drop out
                if c["parent"] == name:
                    parent_rows = rows
                keys = {tuple(p.get(x) for x in c["parent_columns"]) for p in parent_rows}
                keep = []
                for r in rows:
                    ref = tuple(r.get(x) for x in c["columns"])
                    if any(v is None for v in ref) or ref in keys:
                        keep.append(r)
                    else:
                        quarantine.append({"source_table": name, "rule": c["rule"], "reason": reason, "row": r})
                dropped, rows = len(rows) - len(keep), keep
                if not dropped:
                    break
        silver[name] = rows
    return {"silver": silver, "quarantine": quarantine}


def written_tables(s: dict) -> list[str]:
    """Every table name the notebook writes, fully qualified as Spark sees it (lower case): the test that no source
    table is ever a target compares these with the source tables."""
    out = []
    for t in s["tables"]:
        out.append(".".join(x for x in t["target"] if x).lower())
    out.append(".".join(x for x in s["quarantine"] if x).lower())
    return out


def source_tables(s: dict) -> list[str]:
    src = s["source"]
    return [(f"{src['schema']}.{t}" if src["schemas_enabled"] else t).lower() for t in src["tables"]]
