"""A receipt for every number (21 November 2026, round BL1; backlog C-36; docs/RECEIPTS.md).

validate_plan (evidence.validate) answers with counts: a key is unique, a link holds for 6 rows with 1 orphan, a header
has up to 3 line rows. A receipt lists each of those numbers with the exact statement that counted it, so a buyer's
architect, a partner or a reseller can run that statement on the same tables and get the same number back, without
anyone from Krusgraph in the room.

    build(plan, validation)  -> one row per counted number: the sentence as Krusgraph says it, the SQL, the counts it
                                answered, the dialect and the UTC time of the receipt
    markdown(rows)           -> krusgraph-receipt.md: a title, one section per number, the SQL in a fenced block

The statements are not written here: they come from the same builders validate uses (evidence.key_sql,
evidence.relationship_sql, evidence.extended_sql, amounts.lines_per_header_sql, amounts.flat_sql) with the same
arguments. Where validate counted several links of one table in one combined statement, the receipt gives each link's own
statement (evidence.relationship_sql), which counts the same numbers (evidence.combined_relationship_sql says why).

A receipt holds counts and names only, never a row value. Items validate did not count (time, a failed query,
max_items) are listed as not counted, with no number. Nothing here runs a query; the CLI's `krusgraph receipt` runs
validate and then builds the receipt from its answer.
"""
from __future__ import annotations

import datetime as _dt

from . import amounts, evidence
from .dialects import TSQL, Dialect, sqlite_sql

FILENAME = "krusgraph-receipt.md"
FORMAT = 1


def _now(generated_at=None) -> str:
    if isinstance(generated_at, str):
        return generated_at
    t = generated_at or _dt.datetime.now(_dt.timezone.utc)
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    return t.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dialect(dialect) -> tuple[Dialect, str]:
    """(the dialect the engine writes in, the name the receipt states). "sqlite" is the engine's T-SQL translated by
    dialects.sqlite_sql, as the local sources run it."""
    if isinstance(dialect, Dialect):
        return dialect, dialect.name
    if dialect in (None, "", "tsql"):
        return TSQL, "tsql"
    if dialect == "sqlite":
        return TSQL, "sqlite"
    raise ValueError(f"unknown dialect {dialect!r}: tsql, sqlite or a dialects.Dialect")


def _cols(cols) -> str:
    return ", ".join(str(c) for c in cols)


def _initial(r) -> list[str]:
    if r.rule != "SAP pack":
        return []
    from .sap_pack import initial_columns
    return initial_columns(r.source, r.source_cols, r.target)


def _find_rel(plan, entry: dict, used: set[int]):
    for i, r in enumerate(plan.relationships):
        if i not in used and r.source == entry.get("source") and r.target == entry.get("target") \
                and list(r.source_cols) == list(entry.get("columns", [])) and list(r.target_cols) == list(entry.get("target_columns", [])):
            used.add(i)
            return r
    return None


def _find_ext(plan, entry: dict, used: set[int]):
    for j, r in enumerate(getattr(plan, "extended", [])):
        if j not in used and r.source == entry.get("source") and r.target == entry.get("target") and r.kind == entry.get("kind") \
                and list(r.source_cols) == list(entry.get("columns", [])) and list(r.target_cols) == list(entry.get("target_columns", [])):
            used.add(j)
            return r
    return None


def build(plan, validation: dict, generated_at=None, dialect="tsql") -> list[dict]:
    """One row per number in validate_plan's answer: keys, links (plain and extended), amount levels (rows per header and
    the flat-table check), then one row per item that was not counted (sql and counts None). `dialect`: "tsql" (the
    default, Fabric's SQL endpoint), "sqlite" (the local samples and folders: the statement as SQLite runs it) or a
    dialects.Dialect (Databricks)."""
    engine, name = _dialect(dialect)
    schema = plan.schema.schema
    at = _now(generated_at)
    as_run = sqlite_sql if name == "sqlite" else (lambda s: s)
    rows: list[dict] = []

    def add(kind: str, item: str, sentence: str, sql: str | None, counts: dict | None) -> None:
        row = {"n": len(rows) + 1, "kind": kind, "item": item, "sentence": sentence,
               "sql": as_run(sql) if sql else None, "counts": counts, "dialect": name, "generated_at": at}
        rows.append(row)

    keys = validation.get("keys", [])
    for k in keys:
        cols = list(k["columns"])
        add("key", f"key:{k['table']}", f"Key {k['table']}({_cols(cols)}): {k['verdict']}.",
            evidence.key_sql(schema, k["table"], cols, engine),
            {"n": k["rows"], "nulls": k["nulls"], "distinct_keys": k["distinct"]})

    used_rel: set[int] = set()
    used_ext: set[int] = set()
    for e in validation.get("relationships", []):
        link = f"{e['source']}.{'+'.join(e['columns'])} -> {e['target']}.{'+'.join(e['target_columns'])}"
        if "kind" in e:
            r = _find_ext(plan, e, used_ext)
            if r is None:
                continue
            add("extended link", f"rel:{e['source']}.{'+'.join(e['columns'])}>{e['target']}",
                f"Link {link} ({e['kind']}): {e['verdict']}.", evidence.extended_sql(schema, r, engine),
                {"with_value": e["rows_with_value"], "orphans": e["orphans"], "several": e.get("several", 0)})
            continue
        r = _find_rel(plan, e, used_rel)
        if r is None:
            continue
        initial = _initial(r)
        sql = evidence.relationship_sql(schema, r.source, list(r.source_cols), r.target, list(r.target_cols), engine,
                                        blank_is_none=r.rule == "SAP pack",
                                        target_unique=evidence.target_key_unique(keys, r.target, list(r.target_cols)),
                                        initial=initial or None)
        add("link", f"rel:{e['source']}.{'+'.join(e['columns'])}>{e['target']}", f"Link {link}: {e['verdict']}.", sql,
            {"with_value": e["rows_with_value"], "orphans": e["orphans"]})

    levels = validation.get("amount_levels") or {}
    for f in levels.get("findings", []):
        c = f.get("rows_per_header")
        if not isinstance(c, dict):
            continue
        counts = {k: c[k] for k in ("headers", "avg_lines", "min_lines", "max_lines", "headers_in_table", "orphan_values",
                                    "orphan_lines") if k in c}
        sentence = (f"{f['line']} has {c['avg_lines']:g} rows for each row of {f['header']} on average, between "
                    f"{c.get('min_lines', '?')} and {c['max_lines']} ({c['headers']} header value(s) counted), so "
                    f"SUM({f['header']}.{f['amount_columns'][0]}) over a join of the two "
                    + ("repeats it." if c["max_lines"] > 1 else "is correct today."))
        add("amount level", f"amount:{f['header']}<{f['line']}", sentence,
            amounts.lines_per_header_sql(schema, f["line"], list(f["line_columns"]), engine, f["header"],
                                         list(f["header_columns"])), counts)
    for e in levels.get("flat_tables", []):
        counts = {"row_count": e["rows"], "header_values": e["header_values"], "repeated_values": e["repeated_header_values"],
                  "differs_0": e["differing_header_values"]}
        add("flat amount", f"flat:{e['table']}.{e['amount_column']}/{e['header_column']}",
            f"{e['table']}.{e['amount_column']} per {e['header_column']}: {e['rows']} rows, {e['header_values']} header "
            f"values, {e['repeated_header_values']} on more than one row, {e['differing_header_values']} with differing amounts.",
            amounts.flat_sql(schema, e["table"], e["header_column"], [e["amount_column"]], engine), counts)

    for nc in validation.get("not_counted", []):
        add("not counted", nc["id"], f"{nc['kind'].capitalize()} {nc['id']}: {nc['evidence']}.", None, None)
    return rows


def _fence(sql: str) -> str:
    return sql.replace("```", "` ` `")


def markdown(rows: list[dict], source: str = "") -> str:
    """krusgraph-receipt.md: a title, how to re-run, one section per number with its SQL in a fenced block. Counts only."""
    counted = [r for r in rows if r["sql"]]
    at = rows[0]["generated_at"] if rows else _now()
    lines = ["# Krusgraph receipt", "",
             f"Generated {at} (UTC)" + (f" from {source}" if source else "") + f". {len(counted)} number(s) counted"
             + (f", {len(rows) - len(counted)} not counted" if len(rows) > len(counted) else "") + ".", "",
             "Each section is one number Krusgraph stated, with the statement that counted it. Run the statement on the "
             "same tables (read-only: it only counts) and compare the answer's columns with the counts listed. The counts "
             "are over the whole tables at the time above; new rows change them. No row value is in this file.", ""]
    for r in rows:
        lines += [f"## {r['n']}. {r['kind'].capitalize()}: `{r['item']}`", "", r["sentence"], ""]
        if not r["sql"]:
            lines += ["Not counted, so there is no number and no statement to re-run.", ""]
            continue
        lines += [f"Counts: {', '.join(f'`{k}` = {v}' for k, v in r['counts'].items())}. Dialect: {r['dialect']}.", "",
                  "```sql", _fence(r["sql"]), "```", ""]
    return "\n".join(lines).rstrip() + "\n"
