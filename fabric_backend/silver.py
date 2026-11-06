"""Silver tables from the plan: a PySpark notebook for a Fabric lakehouse that turns the source tables into clean
copies in a schema of their own, with every step commented with the rule that motivates it.

Per table, in the order of the relationships (a parent before the tables that point at it):
  1. read the source table (never written: the targets are in another schema, or carry a prefix on a lakehouse
     without schemas, and a guard in the notebook refuses to start if a target would be a source table);
  2. rows whose key is NULL go to quarantine (the key's rule, K0-K5);
  3. rows that share a key: the latest by the ordering column wins (`order_by`, else a column named like updated_at /
     modified / ingested_at / __timestamp); without one, one row per key by a content hash, so a re-run keeps the same
     row; the others go to quarantine;
  4. per relationship (R0-R5 or confirmed): rows whose reference has no row in the parent's silver table go to
     quarantine with the reason; a NULL reference stays (it says "unknown", not "wrong");
  5. the result is written as a Delta table, overwritten on every run (idempotent), and marked with the table
     property krusgraph.silver = <lakehouse id>/<schema>; a target without that mark (or with another source's) is never
     overwritten. A table that points at itself is checked again until no more rows drop out.
At the end the quarantine table (krusgraph_quarantine: source_table, rule, reason, row_json, checked_at) is rewritten
with this run's rows, and a summary is printed. Keyless tables (K3) are copied without de-duplication.

`spec()` is the plan of the notebook as data; `cells()` renders it as PySpark; `simulate()` runs the same steps on
Python rows (the tests run both on the shop seed and compare). Nothing here talks to Fabric.

Round n115: `apply_fixes(spec, fixes.suggest(...))` puts the fix suggestions for validate_plan's findings into the draft.
A duplicate key's step becomes keep_one_per_key (exact copies first; rows that share a key and differ need a winner
named in DUPLICATE_WINNER), an orphan reference's step becomes resolve_reference (ORPHANS: "quarantine" or "set_null"),
and a flat table's header amount moves to <table>_per_<header>. The decisions sit in the parameters cell as None, and a
cell before the first table stops the run, before anything is written, while one the data needs is None. Without
fixes the notebook is exactly what it was.
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


def spec(plan: Plan, info: dict, silver_schema: str = "silver", order_by: dict | None = None, tables: list[str] | None = None,
         show_personal_data: bool = False) -> dict:
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

    label = getattr(plan, "label", None) or (lambda rule: rule)
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
            # n115: the rule as a person reads it (plan.label: a pack other than SAP by its own name), its text by the code
            checks.append({"columns": list(r.source_cols), "parent": r.target, "parent_columns": list(r.target_cols), "rule": label(r.rule),
                           **({"rule_text": _rule_text(r.rule)} if label(r.rule) != r.rule else {}),
                           "parent_from": "silver" if (r.target in chosen and (order.index(r.target) < order.index(t) or r.target == t)) else
                                          ("source_cycle" if r.target in chosen else "source"),
                           "note": r.note})
        out_tables.append({"table": t, "target": target(t), "key": list(key), "key_rule": label(key_rule) if key else "K3",
                           **({"key_rule_text": _rule_text(key_rule)} if key and label(key_rule) != key_rule else {}),
                           "order_by": col, "order_why": why, "checks": checks})
    owner = f"{info.get('item_id') or info.get('item_name') or 'lakehouse'}/{schema}"
    from . import privacy
    personal: dict[str, list[str]] = {}
    for (t, c), _f in sorted(privacy.personal_columns(plan.schema, chosen).items()):
        personal.setdefault(t, []).append(c)
    return {"source": {"item": info.get("item_name") or "", "item_id": info.get("item_id") or "", "workspace_id": info.get("workspace_id") or "",
                       "schema": schema, "schemas_enabled": schemas_enabled, "tables": sorted(names.values(), key=str.lower), "owner": owner},
            "silver_schema": silver_schema, "quarantine": target(QUARANTINE), "tables": out_tables,
            "personal": personal, "mask_personal_data": not show_personal_data,
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
# Columns whose name looks like personal data (Krusgraph's rules P1-P6, by name): masked in the quarantine's row_json while
# MASK_PERSONAL_DATA is True. The silver tables themselves keep every column.
PERSONAL_COLUMNS = {personal}
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
    masked = set(PERSONAL_COLUMNS.get(table, [])) if MASK_PERSONAL_DATA else set()
    fields = [F.when(col(c).isNull(), F.lit(None).cast("string")).otherwise(F.lit("***")).alias(c) if c in masked else col(c)
              for c in rows.columns]
    quarantined.append(rows.select(F.lit(table).alias("source_table"), F.lit(rule).alias("rule"), F.lit(reason).alias("reason"),
                                   F.to_json(F.struct(*fields)).alias("row_json")))


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


# n115: the helpers the fix suggestions use, added to the setup cell only when the draft has fixes.
FIX_HELPERS = '''

# ---- n115: the steps of the fix suggestions ----
def _content(df):
    return F.sha2(F.to_json(F.struct(*[col(c) for c in df.columns])), 256)


def differing_keys(df, key):
    """Key values whose rows are not all exact copies of each other (NULL keys left out)."""
    present = df
    for c in key:
        present = present.filter(col(c).isNotNull())
    return present.dropDuplicates().groupBy(*[col(c) for c in key]).count().filter(F.col("count") > 1).count()


def amount_differs(df, header, amounts):
    """Header values whose amount differs between their rows (a NULL beside a value counts as different)."""
    g = df.filter(col(header).isNotNull()).groupBy(col(header)).agg(
        F.count(F.lit(1)).alias("_n"), *[F.countDistinct(col(a)).alias(f"_d{{i}}") for i, a in enumerate(amounts)],
        *[F.count(col(a)).alias(f"_c{{i}}") for i, a in enumerate(amounts)])
    cond = None
    for i in range(len(amounts)):
        c = (F.col(f"_d{{i}}") > 1) | ((F.col(f"_c{{i}}") > 0) & (F.col(f"_c{{i}}") < F.col("_n")))
        cond = c if cond is None else (cond | c)
    return g.filter(cond).count()


def keep_one_per_key(df, key, winner, table, rule):
    """One row per key value. Exact copies first: one stays, the others go to quarantine. Rows that share the key and
    still differ: the latest by `winner` stays (ties by content); the decisions cell stopped the run if there are such
    rows and no winner was named."""
    content = _content(df)
    copies = df.withColumn("_krusgraph_rank", F.row_number().over(Window.partitionBy(*[col(c) for c in key], content).orderBy(content)))
    to_quarantine(copies.filter(F.col("_krusgraph_rank") > 1).drop("_krusgraph_rank"), table, rule,
                  f"an exact copy of another row with the same key ({{', '.join(key)}}); one copy was kept")
    df = copies.filter(F.col("_krusgraph_rank") == 1).drop("_krusgraph_rank")
    if winner is None:
        return df
    content = _content(df)
    ranked = df.withColumn("_krusgraph_rank", F.row_number().over(
        Window.partitionBy(*[col(c) for c in key]).orderBy(col(winner).desc_nulls_last(), content.desc())))
    to_quarantine(ranked.filter(F.col("_krusgraph_rank") > 1).drop("_krusgraph_rank"), table, rule,
                  f"another row has the same key ({{', '.join(key)}}) and differs; the row with the latest {{winner}} was kept (DUPLICATE_WINNER)")
    return ranked.filter(F.col("_krusgraph_rank") == 1).drop("_krusgraph_rank")


def resolve_reference(df, columns, parent_df, parent_columns, table, rule, reason, choice):
    """ORPHANS: "quarantine" is check_reference; "set_null" keeps a row whose reference finds no row in the parent, with
    the reference set to NULL, and puts a copy of the original row in quarantine so the value is not lost."""
    if choice == "quarantine":
        return check_reference(df, columns, parent_df, parent_columns, table, rule, reason)
    parent_keys = parent_df.select(*[col(c).alias(f"_krusgraph_p{{i}}") for i, c in enumerate(parent_columns)]).distinct()
    has_ref, on = None, None
    for i, c in enumerate(columns):
        has_ref = col(c).isNotNull() if has_ref is None else (has_ref & col(c).isNotNull())
        match = col(c) == F.col(f"_krusgraph_p{{i}}")
        on = match if on is None else (on & match)
    with_ref = df.filter(has_ref)
    orphans = with_ref.join(parent_keys, on, "left_anti")
    to_quarantine(orphans, table, rule, f"{{reason}}; kept in silver with {{', '.join(columns)}} set to NULL (ORPHANS)")
    nulled = orphans.select(*[F.lit(None).cast(df.schema[c].dataType).alias(c) if c in columns else col(c) for c in df.columns])
    return df.filter(~has_ref).unionByName(with_ref.join(parent_keys, on, "left_semi")).unionByName(nulled)


def move_to_header(df, header, amounts, table):
    """Amounts with one value per header value go to a table of their own, one row per header value; the rows keep every
    other column. A row with an amount and no header value keeps its place without it, and a copy goes to quarantine."""
    has_amount = None
    for a in amounts:
        has_amount = col(a).isNotNull() if has_amount is None else (has_amount | col(a).isNotNull())
    to_quarantine(df.filter(col(header).isNull() & has_amount), table, "flat amount",
                  f"{{', '.join(amounts)}} with no {{header}}: kept in silver without it, as it has no header row to move to")
    level = df.filter(col(header).isNotNull()).groupBy(col(header).alias(header)).agg(*[F.max(col(a)).alias(a) for a in amounts])
    return df.drop(*amounts), level
'''


def apply_fixes(s: dict, suggestions: list[dict]) -> dict:
    """The spec with fix suggestions (fixes.py) in it, as a new dict: per table the key step and the reference steps they
    change and the amounts that move, and under "fixes" each fix or choice the draft takes, with `at` (its index in
    `suggestions`) and `draft` (the exact parameter line and table-cell lines). A suggestion for a table outside the
    spec, a question, or a step the spec has no place for, is left out. Raises PlanInputError when a header table would
    be a source table or another target."""
    import copy
    out = copy.deepcopy(s)
    by = {t["table"]: t for t in out["tables"]}
    taken = []
    for i, f in enumerate(suggestions):
        st = f.get("silver") or {}
        t = by.get(st.get("table"))
        if f.get("kind") not in ("fix", "choice") or t is None:
            continue
        if st["step"] == "key" and t["key"] and [c.lower() for c in t["key"]] == [c.lower() for c in st["key"]]:
            winner = t["order_by"] if t.get("order_why") == "given in order_by" else None
            t["fix_key"] = {"winner": winner, "named": t["order_by"] if winner is None else None}
            taken.append((i, f, t["table"]))
        elif st["step"] == "reference":
            c = next((c for c in t["checks"] if c["parent"] == st["parent"] and [x.lower() for x in c["columns"]] == [x.lower() for x in st["columns"]]), None)
            if c is not None:
                c["fix_id"] = st["id"]
                taken.append((i, f, t["table"]))
        elif st["step"] == "move_amount":
            moves = t.setdefault("moves", [])
            m = next((m for m in moves if m["header"] == st["header_column"]), None)
            if m is None:
                m = {"header": st["header_column"], "amounts": [], "target_table": st["target"],
                     "target": _target_of(out, st["target"])}
                moves.append(m)
            if st["amount_column"] not in m["amounts"]:
                m["amounts"].append(st["amount_column"])
            taken.append((i, f, t["table"]))
    sources = set(source_tables(out))
    targets = [".".join(x for x in t["target"] if x).lower() for t in out["tables"]] + [".".join(x for x in out["quarantine"] if x).lower()]
    for t in out["tables"]:
        for m in t.get("moves", []):
            full = ".".join(x for x in m["target"] if x).lower()
            if full in sources or full in targets:
                raise PlanInputError(f"the header table for {t['table']}.{', '.join(m['amounts'])} would be {full}, which is "
                                     "already a source table or a silver table; choose another silver_schema")
            targets.append(full)
    out["fixes"] = []
    for i, f, table in taken:
        t = by[table]
        out["fixes"].append({"at": i, "kind": f["kind"], "finding": f["finding"], "table": table, "column": f.get("column", ""),
                             "rule": f.get("rule", ""), "before": dict((f.get("counts") or {}).get("before") or {}),
                             "after": dict((f.get("counts") or {}).get("after") or {}),
                             "choices": [{"id": c["id"], "after": dict(c["after"])} for c in f.get("choices", [])],
                             "questions": [q["ask"] for q in f.get("questions", [])],
                             "draft": {"cell": table, "parameter": _fix_parameter(t, f), "pyspark": _fix_lines(t, f)}})
    return out


def _target_of(s: dict, table: str) -> list:
    return [s["silver_schema"], table] if s["source"]["schemas_enabled"] else [None, f"{s['silver_schema']}_{table}"]


def _winner_line(t: dict) -> str:
    fk = t["fix_key"]
    hint = (f" (given in order_by)" if fk["winner"] else
            f" ({fk['named']} is named like a change time: write it here if the latest by it should win)" if fk["named"] else "")
    return (f"DUPLICATE_WINNER[{_py(t['table'])}] = {_py(fk['winner'])}   # rows that share {', '.join(t['key'])} and differ: the "
            f"column whose latest value wins{hint}; None stops the run if there are such rows")


def _orphan_line(c: dict) -> str:
    return f"ORPHANS[{_py(c['fix_id'])}] = None   # \"quarantine\" or \"set_null\": your choice; None stops the run"


def _fix_parameter(t: dict, f: dict) -> str | None:
    st = f["silver"]
    if st["step"] == "key":
        return _winner_line(t)
    if st["step"] == "reference":
        return _orphan_line(next(c for c in t["checks"] if c.get("fix_id") == st["id"]))
    return None


def _move_lines(t: dict, m: dict) -> list[str]:
    name, target = t["table"], m["target_table"]
    return [f"# n115 fix: {', '.join(m['amounts'])} has one value per {m['header']} (validate_plan counted it): it moves to "
            f"{target}, one row per {m['header']}.",
            f"df, _header_level = move_to_header(df, {_py(m['header'])}, {_py(m['amounts'])}, {_py(name)})",
            f"read_counts[{_py(target)}] = None   # built from silver {name}, not read from a source table",
            f"silver[{_py(target)}] = write_silver(_header_level, {_py(target)})"]


def _fix_lines(t: dict, f: dict) -> str:
    """The lines of the table's cell that a fix or choice adds or changes, exactly as cells() writes them."""
    st = f["silver"]
    lines = _table_cell(t).splitlines()
    if st["step"] == "key":
        return "\n".join(x for x in lines if x.startswith("df = keep_one_per_key("))
    if st["step"] == "reference":
        return "\n".join(x.strip() for x in lines if "resolve_reference(" in x and f"ORPHANS[{_py(st['id'])}]" in x)
    m = next(m for m in t["moves"] if m["header"] == st["header_column"])
    return "\n".join(_move_lines(t, m))


def _key_comment(t: dict) -> list[str]:
    if t["key_rule"] == "K3" or not t["key"]:
        return [f"# No key (rule K3: {_rule_text('K3')}): every row is kept as it is; nothing to de-duplicate on."]
    lines = [f"# Key {' + '.join(t['key'])} (rule {t['key_rule']}: {t.get('key_rule_text') or _rule_text(t['key_rule'])}).",
             "# A key identifies one row: rows without a key go to quarantine, and of rows that share a key only one is kept."]
    if t["order_by"]:
        lines.append(f"# Latest row wins by {t['order_by']} ({t['order_why']}).")
    else:
        lines.append("# No ordering column (none given in order_by, none named like updated_at): the kept row is chosen by a content hash, so a re-run keeps the same one.")
    return lines


def _ref_call(c: dict, parent: str, name: str, reason: str) -> str:
    args = f"{_py(c['columns'])}, {parent}, {_py(c['parent_columns'])}, {_py(name)}, {_py(c['rule'])}, {_py(reason)}"
    if c.get("fix_id"):                                                  # n115: the orphans' choice, made in ORPHANS
        return f"resolve_reference(df, {args}, ORPHANS[{_py(c['fix_id'])}])"
    return f"check_reference(df, {args})"


def _table_cell(t: dict) -> str:
    name = t["table"]
    out = [f"# ---- {name} -> {'.'.join(x for x in t['target'] if x)} ----", *_key_comment(t),
           f"df = spark.read.table(source({_py(name)}))", f"read_counts[{_py(name)}] = df.count()"]
    if t["key"] and t.get("fix_key"):                                    # n115: the duplicate key's fix suggestion
        out += [f"# n115 fix: validate_plan counted duplicate or NULL keys here. Exact copies: one stays; rows that share the key and",
                "# differ: the latest by DUPLICATE_WINNER stays, and the decisions cell stopped the run if there are such rows and none is named.",
                f"df = drop_null_keys(df, {_py(t['key'])}, {_py(name)}, {_py(t['key_rule'])})",
                f"df = keep_one_per_key(df, {_py(t['key'])}, DUPLICATE_WINNER[{_py(name)}], {_py(name)}, {_py(t['key_rule'])})"]
    elif t["key"]:
        out += [f"df = drop_null_keys(df, {_py(t['key'])}, {_py(name)}, {_py(t['key_rule'])})",
                f"df = keep_latest(df, {_py(t['key'])}, {_py(t['order_by'])}, {_py(name)}, {_py(t['key_rule'])})"]
    for c in t["checks"]:
        on = " and ".join(f"{name}.{a} = {c['parent']}.{b}" for a, b in zip(c["columns"], c["parent_columns"]))
        reason = f"{', '.join(c['columns'])} has no row in {c['parent']} ({on})"
        out.append(f"# Reference {on} (rule {c['rule']}: {c.get('rule_text') or _rule_text(c['rule'])}"
                   + (f"; {c['note']}" if c.get("note") else "") + ").")
        if c["parent_from"] == "silver" and c["parent"] != name:
            out.append(f"# Checked against the silver {c['parent']}, so rows whose {c['parent']} was quarantined follow it there.")
            parent = f"silver[{_py(c['parent'])}]"
        elif c["parent"] == name:
            out += ["# The table points at itself: checked against its own rows, again until no more rows drop out, so a row whose",
                    "# parent was quarantined follows it there (at most 100 rounds: the depth of the hierarchy).",
                    "for _round in range(100):",
                    "    _before = df.count()",
                    f"    df = {_ref_call(c, 'df', name, reason)}",
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
        out.append(f"df = {_ref_call(c, parent, name, reason)}")
    for m in t.get("moves", []):                                         # n115: a flat table's header amount
        out += _move_lines(t, m)
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


def _fix_parameters(s: dict) -> str:
    lines = ["# n115 fix suggestions: your decisions (the cell above lists them). None is \"not decided\": the decisions cell",
             "# stops the run before anything is written while a decision the data needs is None.",
             "DUPLICATE_WINNER = {}"]
    lines += [_winner_line(t) for t in s["tables"] if t.get("fix_key")]
    lines.append("ORPHANS = {}")
    lines += [_orphan_line(c) for t in s["tables"] for c in t["checks"] if c.get("fix_id")]
    return "\n".join(lines)


def _counts(d: dict) -> str:
    return ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in d.items()) or "not counted"


def _fixes_markdown(s: dict) -> str:
    out = ["## Fix suggestions (drafts to review)", "",
           "validate_plan counted the findings below; each one changes a step of this notebook. The counts before are the "
           "check's own, and after is what the silver tables hold once this notebook has run with the step in it. It has not "
           "run: nothing is fixed until it has, and its summary prints the counts. The source tables are never written; the "
           f"steps write only the silver tables and `{QUARANTINE}`. A decision is never made for you: the parameters cell "
           "holds each one as None, and the run stops before writing anything while one the data needs is None.", ""]
    for i, f in enumerate(s["fixes"], 1):
        out.append(f"{i}. **{f['finding']}** in `{f['table']}` ({f['column']}), {f['kind']}: {f['rule']}")
        out.append(f"   Before: {_counts(f['before'])}.")
        if f["after"]:
            out.append(f"   After: {_counts(f['after'])}.")
        out += [f"   After, if {c['id']}: {_counts(c['after'])}." for c in f["choices"]]
        out += [f"   Question: {q}" for q in f["questions"]]
    return "\n".join(out)


DECISIONS = """# ---- n115: the decisions and the run-time checks of the fix suggestions, before anything is written ----
DEDUP_KEYS = __DEDUP__
MOVES = __MOVES__
_open = sorted(k for k, v in ORPHANS.items() if v not in ("quarantine", "set_null"))
if _open:
    raise ValueError("ORPHANS: choose 'quarantine' or 'set_null' for " + ", ".join(_open) + ". Nothing was written.")
for _t, _key in DEDUP_KEYS.items():
    _df = spark.read.table(source(_t))
    _w = DUPLICATE_WINNER.get(_t)
    if _w is not None and _w not in _df.columns:
        raise ValueError(f"DUPLICATE_WINNER[{_t!r}]: {_t} has no column {_w!r}. Nothing was written.")
    _n = 0 if _w is not None else differing_keys(_df, _key)
    if _n:
        raise ValueError(f"{_t}: {_n} value(s) of {', '.join(_key)} have rows that differ; name the column whose latest value "
                         f"wins in DUPLICATE_WINNER[{_t!r}], or record the right key. Nothing was written.")
for _m in MOVES:
    _n = amount_differs(spark.read.table(source(_m["table"])), _m["header"], _m["amounts"])
    if _n:
        raise ValueError(f"{_m['table']}: {_n} value(s) of {_m['header']} carry different {', '.join(_m['amounts'])} values now, "
                         "so moving the amount is no longer mechanical. Nothing was written.")"""


def _decisions_cell(s: dict) -> str:
    dedup = {t["table"]: t["key"] for t in s["tables"] if t.get("fix_key")}
    moves = [{"table": t["table"], "header": m["header"], "amounts": m["amounts"]} for t in s["tables"] for m in t.get("moves", [])]
    return DECISIONS.replace("__DEDUP__", json.dumps(dedup)).replace("__MOVES__", json.dumps(moves))


def cells(s: dict) -> list[tuple[str, str]]:
    src = s["source"]
    intro = (f"# Silver tables for {src['item'] or 'the lakehouse'}.{src['schema']}\n\n"
             f"Generated by Krusgraph from the plan: clean copies of {len(s['tables'])} table(s) in "
             + (f"the schema `{s['silver_schema']}`" if src["schemas_enabled"] else f"tables prefixed `{s['silver_schema']}_`")
             + ", de-duplicated on each table's key and with every reference checked; rows that fail a check are kept in "
             f"`{QUARANTINE}` with the reason. The source tables are only read. Run it again at any time: every silver table "
             "is rewritten from the source. Each step below names the rule (K0–K5, R0–R5) that motivates it.")
    params = (f"SILVER_SCHEMA = {_py(s['silver_schema'])}   # where the silver tables go; never the source schema\n"
              'TABLE_FORMAT = "delta"     # lakehouse tables are Delta; leave as it is\n'
              f"MASK_PERSONAL_DATA = {s.get('mask_personal_data', True)}   # quarantined rows keep personal-data columns as *** (see PERSONAL_COLUMNS)")
    fixed = bool(s.get("fixes"))
    if fixed:                                                            # n115: the decisions the fix suggestions need
        params += "\n" + _fix_parameters(s)
    writes = [t["table"] for t in s["tables"]] + [m["target_table"] for t in s["tables"] for m in t.get("moves", [])] + [QUARANTINE]
    setup = (SETUP + (FIX_HELPERS if fixed else "")).format(source_schema=_py(src["schema"] if src["schemas_enabled"] else None),
                         schemas_enabled="True" if src["schemas_enabled"] else "False",
                         source_tables=_py(src["tables"]), writes=_py(writes), owner=_py(src["owner"]),
                         personal=json.dumps(s.get("personal", {})))
    out = [("markdown", intro)] + ([("markdown", _fixes_markdown(s))] if fixed else [])
    out += [("parameters", params), ("code", setup.strip("\n"))] + ([("code", _decisions_cell(s))] if fixed else [])
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


def _differing_keys(rows: list[dict], key: list[str], columns: list[str]) -> int:
    groups: dict[tuple, set] = {}
    for r in rows:
        k = tuple(r.get(c) for c in key)
        if None not in k:
            groups.setdefault(k, set()).add(tuple(r.get(c) for c in columns))
    return sum(1 for v in groups.values() if len(v) > 1)


def _amount_differs(rows: list[dict], header: str, amounts: list[str]) -> int:
    groups: dict = {}
    for r in rows:
        if r.get(header) is not None:
            groups.setdefault(r[header], []).append(r)
    n = 0
    for g in groups.values():
        for a in amounts:
            vals = [r.get(a) for r in g]
            present = [v for v in vals if v is not None]
            if len(set(present)) > 1 or (present and len(present) < len(vals)):
                n += 1
                break
    return n


def decisions(s: dict, data: dict[str, list[dict]], given: dict | None = None) -> dict:
    """n115: the decisions cell in Python: DUPLICATE_WINNER and ORPHANS as the parameters cell drafts them, updated with
    `given` ({"DUPLICATE_WINNER": {...}, "ORPHANS": {...}}); raises ValueError where the notebook stops."""
    given = given or {}
    winners = {t["table"]: t["fix_key"]["winner"] for t in s["tables"] if t.get("fix_key")}
    winners.update(given.get("DUPLICATE_WINNER") or {})
    orphans = {c["fix_id"]: None for t in s["tables"] for c in t["checks"] if c.get("fix_id")}
    orphans.update(given.get("ORPHANS") or {})
    still = sorted(k for k, v in orphans.items() if v not in ("quarantine", "set_null"))
    if still:
        raise ValueError("ORPHANS: choose 'quarantine' or 'set_null' for " + ", ".join(still) + ". Nothing was written.")
    for t in s["tables"]:
        if not t.get("fix_key"):
            continue
        rows = data.get(t["table"], [])
        columns = list(rows[0].keys()) if rows else []
        w = winners.get(t["table"])
        if w is not None and w not in columns:
            raise ValueError(f"DUPLICATE_WINNER[{t['table']!r}]: {t['table']} has no column {w!r}. Nothing was written.")
        n = 0 if w is not None else _differing_keys(rows, t["key"], columns)
        if n:
            raise ValueError(f"{t['table']}: {n} value(s) of {', '.join(t['key'])} have rows that differ; name the column whose "
                             f"latest value wins in DUPLICATE_WINNER[{t['table']!r}], or record the right key. Nothing was written.")
    for t in s["tables"]:
        for m in t.get("moves", []):
            n = _amount_differs(data.get(t["table"], []), m["header"], m["amounts"])
            if n:
                raise ValueError(f"{t['table']}: {n} value(s) of {m['header']} carry different {', '.join(m['amounts'])} values "
                                 "now, so moving the amount is no longer mechanical. Nothing was written.")
    return {"DUPLICATE_WINNER": winners, "ORPHANS": orphans}


def _keep_one_per_key(rows, key, winner, columns, name, rule, quarantine) -> list[dict]:
    copies: dict[tuple, dict] = {}
    for r in rows:
        k = (tuple(r.get(c) for c in key), tuple(r.get(c) for c in columns))
        if k in copies:
            quarantine.append({"source_table": name, "rule": rule, "row": r,
                               "reason": f"an exact copy of another row with the same key ({', '.join(key)}); one copy was kept"})
        else:
            copies[k] = r
    rows = list(copies.values())
    if winner is None:
        return rows
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault(tuple(r.get(c) for c in key), []).append(r)
    kept = []
    for group in groups.values():
        group.sort(key=lambda r: (r.get(winner) is not None, r.get(winner) if r.get(winner) is not None else 0, _content_hash(r, columns)),
                   reverse=True)
        kept.append(group[0])
        quarantine += [{"source_table": name, "rule": rule, "row": r,
                        "reason": f"another row has the same key ({', '.join(key)}) and differs; the row with the latest {winner} was kept (DUPLICATE_WINNER)"}
                       for r in group[1:]]
    return kept


def simulate(s: dict, data: dict[str, list[dict]], given: dict | None = None) -> dict:
    """Run the notebook's steps on rows in memory: {"silver": {table: rows}, "quarantine": [{source_table, rule, reason,
    row}]}. Ties without an ordering column are broken by a content hash like the notebook's, but not the same hash
    (Spark's JSON differs), so with such ties only the counts are comparable. With fixes (apply_fixes), `given` holds the
    decisions as the parameters cell would ({"DUPLICATE_WINNER": {...}, "ORPHANS": {...}}), and the run stops with
    ValueError where the notebook's decisions cell does."""
    silver: dict[str, list[dict]] = {}
    quarantine: list[dict] = []
    deduped: dict[str, list[dict]] = {}
    chosen = decisions(s, data, given) if s.get("fixes") else {"DUPLICATE_WINNER": {}, "ORPHANS": {}}
    for t in s["tables"]:
        name = t["table"]
        rows = [dict(r) for r in data.get(name, [])]
        columns = list(rows[0].keys()) if rows else []
        if t["key"] and t.get("fix_key"):                                # n115: exact copies, then the named winner
            null_key = [r for r in rows if any(r.get(c) is None for c in t["key"])]
            quarantine += [{"source_table": name, "rule": t["key_rule"], "reason": f"the key ({', '.join(t['key'])}) is NULL", "row": r} for r in null_key]
            rows = _keep_one_per_key([r for r in rows if r not in null_key], t["key"], chosen["DUPLICATE_WINNER"].get(name),
                                     columns, name, t["key_rule"], quarantine)
        elif t["key"]:
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
            set_null = chosen["ORPHANS"].get(c.get("fix_id")) == "set_null"
            for _round in range(100 if c["parent"] == name else 1):     # a self-reference: until no more rows drop out
                if c["parent"] == name:
                    parent_rows = rows
                keys = {tuple(p.get(x) for x in c["parent_columns"]) for p in parent_rows}
                keep, dropped = [], 0
                for r in rows:
                    ref = tuple(r.get(x) for x in c["columns"])
                    if any(v is None for v in ref) or ref in keys:
                        keep.append(r)
                    elif set_null:                                   # n115: kept with the reference NULL, a copy in quarantine
                        dropped += 1
                        quarantine.append({"source_table": name, "rule": c["rule"], "row": r,
                                           "reason": f"{reason}; kept in silver with {', '.join(c['columns'])} set to NULL (ORPHANS)"})
                        keep.append({k: (None if k in c["columns"] else v) for k, v in r.items()})
                    else:
                        dropped += 1
                        quarantine.append({"source_table": name, "rule": c["rule"], "reason": reason, "row": r})
                rows = keep
                if not dropped:
                    break
        for m in t.get("moves", []):                                     # n115: a flat table's header amount
            level: dict = {}
            for r in rows:
                if r.get(m["header"]) is None:
                    if any(r.get(a) is not None for a in m["amounts"]):
                        quarantine.append({"source_table": name, "rule": "flat amount", "row": r,
                                           "reason": f"{', '.join(m['amounts'])} with no {m['header']}: kept in silver without it, as it has no header row to move to"})
                    continue
                e = level.setdefault(r[m["header"]], {m["header"]: r[m["header"]], **{a: None for a in m["amounts"]}})
                for a in m["amounts"]:
                    if r.get(a) is not None and (e[a] is None or r[a] > e[a]):
                        e[a] = r[a]
            silver[m["target_table"]] = list(level.values())
            rows = [{k: v for k, v in r.items() if k not in m["amounts"]} for r in rows]
        silver[name] = rows
    if s.get("mask_personal_data", True) and s.get("personal"):                # as the notebook's to_quarantine writes row_json
        for q in quarantine:
            cols = set(s["personal"].get(q["source_table"], []))
            q["row"] = {k: (None if v is None else "***") if k in cols else v for k, v in q["row"].items()}
    return {"silver": silver, "quarantine": quarantine}


def written_tables(s: dict) -> list[str]:
    """Every table name the notebook writes, fully qualified as Spark sees it (lower case): the test that no source
    table is ever a target compares these with the source tables."""
    out = []
    for t in s["tables"]:
        out.append(".".join(x for x in t["target"] if x).lower())
        out += [".".join(x for x in m["target"] if x).lower() for m in t.get("moves", [])]      # n115: a header amount's table
    out.append(".".join(x for x in s["quarantine"] if x).lower())
    return out


def source_tables(s: dict) -> list[str]:
    src = s["source"]
    return [(f"{src['schema']}.{t}" if src["schemas_enabled"] else t).lower() for t in src["tables"]]
