"""After landing: did the migration keep the data? (round MG1)

One counting query per side, built from the checked plan: per table the rows, the key's distinct values and NULLs, the
totals of its number columns that are neither key nor link; per link the rows whose reference finds nothing (orphans).
The query returns two columns, metric and value, so the customer runs it in Snowflake or Databricks and saves one CSV;
on the Fabric side the local server can run it itself (read-only) or the customer saves that result too. compare()
puts the two side by side: what is equal, what is not, by how much. No value leaves either side, only counts and sums.

Equal counts do not prove equal values: a row can change and another change back. The report says so.
"""
from __future__ import annotations

import csv
import io
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

_NUM = ("decimal", "numeric", "number", "int", "integer", "bigint", "smallint", "tinyint", "float", "double", "real", "money")

DIALECTS = {
    "snowflake": {"q": lambda n: '"' + n.replace('"', '""') + '"', "text": "VARCHAR"},
    "databricks": {"q": lambda n: "`" + n.replace("`", "``") + "`", "text": "STRING"},
    "tsql": {"q": lambda n: "[" + n.replace("]", "]]") + "]", "text": "VARCHAR(100)"},
    "sqlite": {"q": lambda n: "[" + n.replace("]", "]]") + "]", "text": "TEXT"},
}


def _is_num(t: str) -> bool:
    b = (t or "").lower().split("(")[0].strip()
    return b in _NUM or b.startswith(("decimal", "numeric", "number"))


def spec(p, source_model=None) -> dict:
    """What to count, from a plan, in lower-case names: tables with key and amount columns, links."""
    linked = {(r.source.lower(), c.lower()) for r in p.relationships for c in r.source_cols}
    types = {}
    if source_model is not None:                   # the source's types decide what is a number (the landed side may differ)
        for t in source_model.tables.values():
            for c in t.columns:
                types[(t.name.lower(), c.name.lower())] = c.data_type
    tables = {}
    for t in p.schema:
        key = [c.lower() for c in p.keys.get(t.name, ([], ""))[0]]
        amounts = [c.name.lower() for c in t.columns if c.name in t.column_names and c.name.lower() not in key
                   and (t.name.lower(), c.name.lower()) not in linked and _is_num(types.get((t.name.lower(), c.name.lower()), c.data_type))]
        tables[t.name.lower()] = {"key": key, "amounts": amounts}
    links = [{"source": r.source.lower(), "cols": [c.lower() for c in r.source_cols], "target": r.target.lower(),
              "target_cols": [c.lower() for c in r.target_cols]} for r in p.relationships]
    return {"tables": tables, "links": links}


def present(sp: dict, names: dict) -> dict:
    """The part of the spec the other side has: tables found in `names` (lower-case table or 'table.column' -> spelling),
    with only the key and amount columns it has; links whose both tables and columns are there."""
    tables = {}
    for t, v in sp["tables"].items():
        if t not in names or any(f"{t}.{c}" not in names for c in v["key"]):
            continue
        tables[t] = {"key": v["key"], "amounts": [c for c in v["amounts"] if f"{t}.{c}" in names]}
    links = [x for x in sp["links"] if x["source"] in tables and x["target"] in tables
             and all(f"{x['source']}.{c}" in names for c in x["cols"]) and all(f"{x['target']}.{c}" in names for c in x["target_cols"])]
    return {"tables": tables, "links": links}


def link_id(link: dict) -> str:
    return f"{link['source']}({','.join(link['cols'])})->{link['target']}"


def counting_sql(sp: dict, dialect: str, schema: str, names: dict | None = None) -> str:
    """One UNION ALL query returning (metric, value) rows. names: lower-case table or 'table.column' -> spelling on this
    side (Snowflake's upper case, Fabric's own); a name not in it is used as written in the spec."""
    d = DIALECTS[dialect]
    q, text = d["q"], d["text"]
    names = {k.lower(): v for k, v in (names or {}).items()}
    tn = lambda t: f"{q(schema)}.{q(names.get(t, t))}" if schema else q(names.get(t, t))
    cn = lambda t, c: q(names.get(f"{t}.{c}", c))
    parts = []
    for t, v in sorted(sp["tables"].items()):
        parts.append(f"SELECT 'rows|{t}' AS metric, CAST(COUNT(*) AS {text}) AS value FROM {tn(t)}")
        if v["key"]:
            k = ", ".join(cn(t, c) for c in v["key"])
            notnull = " AND ".join(f"{cn(t, c)} IS NOT NULL" for c in v["key"])
            anynull = " OR ".join(f"{cn(t, c)} IS NULL" for c in v["key"])
            parts.append(f"SELECT 'key_distinct|{t}' AS metric, CAST(COUNT(*) AS {text}) AS value FROM "
                         f"(SELECT {k} FROM {tn(t)} WHERE {notnull} GROUP BY {k}) d")
            parts.append(f"SELECT 'key_null|{t}' AS metric, CAST(COUNT(*) AS {text}) AS value FROM {tn(t)} WHERE {anynull}")
        for c in v["amounts"]:
            parts.append(f"SELECT 'sum|{t}|{c}' AS metric, CAST(SUM({cn(t, c)}) AS {text}) AS value FROM {tn(t)}")
    for link in sp["links"]:
        s, t = link["source"], link["target"]
        on = " AND ".join(f"s.{cn(s, a)} = r.{cn(t, b)}" for a, b in zip(link["cols"], link["target_cols"]))
        filled = " AND ".join(f"s.{cn(s, a)} IS NOT NULL" for a in link["cols"])
        parts.append(f"SELECT 'orphans|{link_id(link)}' AS metric, CAST(COUNT(*) AS {text}) AS value FROM {tn(s)} s "
                     f"LEFT JOIN {tn(t)} r ON {on} WHERE {filled} AND r.{cn(t, link['target_cols'][0])} IS NULL")
    return "\nUNION ALL\n".join(parts)


def run(execute, sql: str) -> dict[str, str | None]:
    """Run the counting query on a connection (execute(sql) -> rows as dicts): {metric: value}."""
    out = {}
    for r in execute(sql):
        r = {str(k).lower(): v for k, v in dict(r).items()}
        out[str(r["metric"])] = None if r["value"] is None else str(r["value"])
    return out


def read_results(path) -> dict[str, str | None]:
    """A saved result: CSV with columns metric,value (any case) or JSON {metric: value} / [{metric, value}]."""
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        if isinstance(data, dict):
            return {str(k): None if v is None else str(v) for k, v in data.items()}
        rows = data
    else:
        rows = list(csv.DictReader(io.StringIO(text)))
    out = {}
    for r in rows:
        r = {str(k).strip().strip('"').lower(): v for k, v in r.items()}
        out[str(r["metric"])] = None if r.get("value") in (None, "", "NULL") else str(r["value"])
    return out


def _num(v):
    if v is None:
        return None
    try:
        return Decimal(str(v).strip())
    except InvalidOperation:
        return None


def compare(before: dict, after: dict, sp: dict) -> dict:
    """Side by side per table and link. A metric only one side has is listed as missing on the other."""
    tables, links, differences = [], [], []
    for t, v in sorted(sp["tables"].items()):
        def pair(metric):
            return _num(before.get(metric)), _num(after.get(metric)), metric in before, metric in after
        rb, ra, hb, ha = pair(f"rows|{t}")
        row = {"table": t, "rows_before": rb, "rows_after": ra}
        if not hb or not ha:
            row["missing"] = "before" if not hb else "after"
            differences.append(f"{t}: no count {'before' if not hb else 'after'} (the table is not on that side, or the query was not run)")
            tables.append(row)
            continue
        if rb != ra:
            differences.append(f"{t}: rows {rb} before, {ra} after ({ra - rb:+})")
        if v["key"]:
            db, da, _, _ = pair(f"key_distinct|{t}")
            nb, na, _, _ = pair(f"key_null|{t}")
            dup_b = (rb - nb - db) if None not in (rb, nb, db) else None
            dup_a = (ra - na - da) if None not in (ra, na, da) else None
            row.update({"key": v["key"], "key_unique_before": dup_b == 0 and nb == 0, "key_unique_after": dup_a == 0 and na == 0,
                        "key_duplicates_before": dup_b, "key_duplicates_after": dup_a, "key_nulls_before": nb, "key_nulls_after": na})
            if (dup_b, nb) != (dup_a, na):
                differences.append(f"{t}: key ({', '.join(v['key'])}) duplicates {dup_b} -> {dup_a}, NULLs {nb} -> {na}")
        sums = []
        for c in v["amounts"]:
            sb, sa, _, _ = pair(f"sum|{t}|{c}")
            sums.append({"column": c, "before": sb, "after": sa, "equal": sb == sa})
            if sb != sa:
                differences.append(f"{t}.{c}: total {sb} before, {sa} after" + (f" ({sa - sb:+})" if None not in (sa, sb) else
                                   " (the column was not counted on one side)" if f"sum|{t}|{c}" not in after or f"sum|{t}|{c}" not in before else ""))
        row["totals"] = sums
        tables.append(row)
    for link in sp["links"]:
        lid = link_id(link)
        ob, oa = _num(before.get(f"orphans|{lid}")), _num(after.get(f"orphans|{lid}"))
        links.append({"link": lid, "orphans_before": ob, "orphans_after": oa})
        if ob != oa and f"orphans|{lid}" in before and f"orphans|{lid}" in after:
            differences.append(f"{lid}: orphans {ob} before, {oa} after")
    kept = not differences
    return {"verdict": "kept: every count and total is equal on both sides" if kept else f"{len(differences)} difference(s)",
            "kept": kept, "differences": differences, "tables": tables, "links": links,
            "note": "counts and totals, not values: equal numbers do not prove that every value is equal"}


def markdown(cmp: dict, source: str, checks: dict | None = None) -> str:
    """The short before/after report."""
    f = lambda x: "-" if x is None else (f"{x:,}".replace(",", " ") if isinstance(x, Decimal) and x == x.to_integral() else str(x))
    lines = [f"# Before and after: {source} -> Fabric", "", f"**{cmp['verdict']}.** {cmp['note']}.", ""]
    if checks:
        lines += [f"Checks on the Fabric side (validate_plan): {checks.get('summary', '')}", ""]
    lines += ["| Table | Rows before | Rows after | Key unique before / after | Totals equal |", "|---|---|---|---|---|"]
    for t in cmp["tables"]:
        if t.get("missing"):
            lines.append(f"| {t['table']} | {f(t['rows_before'])} | {f(t['rows_after'])} | not on the {t['missing']} side | - |")
            continue
        ku = "-" if "key" not in t else f"{'yes' if t['key_unique_before'] else 'no'} / {'yes' if t['key_unique_after'] else 'no'}"
        te = "-" if not t["totals"] else ("yes" if all(s["equal"] for s in t["totals"]) else
                                          "no: " + ", ".join(s["column"] for s in t["totals"] if not s["equal"]))
        lines.append(f"| {t['table']} | {f(t['rows_before'])} | {f(t['rows_after'])} | {ku} | {te} |")
    if cmp["links"]:
        lines += ["", "| Link | Orphans before | Orphans after |", "|---|---|---|"]
        lines += [f"| {x['link']} | {f(x['orphans_before'])} | {f(x['orphans_after'])} |" for x in cmp["links"]]
    if cmp["differences"]:
        lines += ["", "Differences:", ""] + [f"- {d}" for d in cmp["differences"]]
    return "\n".join(lines) + "\n"
