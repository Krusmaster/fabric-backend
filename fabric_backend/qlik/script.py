"""A Qlik load script as tables for a lakehouse (Q1). See the package docstring for what rests on what.

Qlik facts used here, all Unverified (the pages could not be opened):
- `ApplyMap('Map', expr [, default])` looks `expr` up in the first column of the mapping table and returns its second
  column; without a match it returns the default, or `expr` itself when no default is given; when the mapping table
  holds a value twice the first row is used.
- `QUALIFY f` renames a field to `<table>.<field>` on load, so it no longer shares a name with other tables.
- A Delta column name may not hold a blank or any of `,;{}()=` or a line break or tab (Delta Lake without column
  mapping); a name of letters, digits and `_` is safe everywhere Krusgraph writes.

It imports private helpers of migration_read (the statement splitter and the LOAD and SELECT parsers) rather than
keeping a second parser; tests/test_q1_qlik.py fails if they change shape.
"""
from __future__ import annotations

import re

from .. import migration_read as mr

_SAFE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")
_APPLYMAP = re.compile(r"\bapplymap\s*\(", re.I)


def column_name(field: str, taken: set[str] | None = None) -> str:
    """The lakehouse column for a Qlik field: the name itself when it is letters, digits and `_`; otherwise every run
    of other characters becomes one `_` (`Order Date` -> `Order_Date`, `Customers.Name` -> `Customers_Name`,
    `%Key` -> `Key`). A name the table already has gets `_2`, `_3`."""
    name = field if _SAFE.match(field) else (re.sub(r"[^A-Za-z0-9_]+", "_", field).strip("_") or "field")
    if name[0].isdigit():
        name = "_" + name
    taken = {t.lower() for t in (taken or set())}
    base, n = name, 1
    while name.lower() in taken:
        n += 1
        name = f"{base}_{n}"
    return name


def _chains(text: str) -> list[dict]:
    """Every load of the script as (label, prefixes, levels): a preceding load and its source are one chain, top level
    first, the way migration_read groups them. Loads inside section access are marked and never read further."""
    statements, _ = mr._statements(text.replace("\r\n", "\n"))
    out, pending, access = [], None, False
    for line, st in statements:
        if mr._CONTROL.match(st):
            continue
        m = re.match(rf"({mr._NAME})\s*:\s*(?=\S)", st)
        label, body = (mr._unquote(m.group(1)), st[m.end():]) if m and not re.match(r"(set|let)\b", st, re.I) else (None, st)
        prefixes, body = mr._prefixes(body)
        if re.match(r"load\b", body, re.I):
            parsed = mr._parse_load(body, line)
        elif re.match(r"(sql\s+)?select\b", body, re.I):
            parsed = mr._parse_select(body, line)
        else:
            sec = re.match(r"section\s+(access|application)\b", body, re.I)
            if sec:
                access = sec.group(1).lower() == "access"
            pending = None
            continue
        chain = pending or {"label": label, "prefixes": prefixes, "levels": [], "line": line, "access": access}
        chain["levels"].append(parsed)
        pending = chain if parsed["source"] is None else None
        if pending is None:
            out.append(chain)
    return out


def _apply_map(expression: str) -> dict | None:
    """The first ApplyMap call of an expression: the mapping table, the looked-up expression and the default."""
    m = _APPLYMAP.search(expression)
    if not m:
        return None
    depth, i = 1, m.end()
    while i < len(expression) and depth:
        depth += {"(": 1, ")": -1}.get(expression[i], 0)
        i += 1
    args = mr._split_commas(expression[m.end():i - 1])
    if len(args) < 2:
        return None
    return {"map": mr._unquote(args[0]), "key": args[1], "default": args[2] if len(args) > 2 else None,
            "whole_expression": expression.strip().lower().startswith("applymap") and i == len(expression.strip())}


def _trace(chain: dict) -> list[dict]:
    """Per field of a chain's top level: the source column it is (through renames in preceding loads), or the
    expression that computes it. A `*` gives no entry: its fields are not written in the script."""
    levels, out = chain["levels"], []
    for item in levels[0]["fields"]:
        if item.get("wildcard"):
            continue
        cur, expression = item, None
        for depth in range(len(levels)):
            if "expression" in cur:
                expression = cur
                break
            src = cur.get("renamed_from", cur["name"])
            below = levels[depth + 1]["fields"] if depth + 1 < len(levels) else None
            if below is None:
                cur = {"name": src}
                break
            cur = next((f for f in below if not f.get("wildcard") and f["name"] == src), {"name": src})
        row = {"field": item["name"]}
        if expression is not None:
            row["expression"] = expression["expression"]
            row["line"] = expression["line"]
            am = _apply_map(expression["expression"])
            if am:
                row["mapping"] = am
        else:
            row["from"] = cur["name"]
        out.append(row)
    return out


def _steps(t: dict, calculated: int, mapped: int) -> list[str]:
    """What the script does to a table beyond copying and renaming, as the list a person rebuilds in silver."""
    loads = t["loads"] + t.get("concatenated", [])
    out = []
    if len(t["loads"]) + len(t.get("concatenated", [])) > 1:
        auto = sum(1 for c in t.get("concatenated", []) if c.get("automatic"))
        out.append(f"{len(loads)} loads appended into one table (Concatenate"
                   + (f"; {auto} by Qlik's automatic concatenation of loads with the same fields" if auto else "") + ")")
    for j in t.get("joins", []):
        out.append(f"{j['kind']} join with {j['source']['kind']} {j['source'].get('name') or 'rows'} on {', '.join(j['on']) or 'no common field'}")
    if "keep" in t:
        out.append(f"{t['keep']['kind']} keep with {t['keep']['with']}: rows without a match are removed, the tables stay apart")
    for word, flag in (("a WHERE filter", "where"), ("GROUP BY", "group_by"), ("DISTINCT", "distinct")):
        n = sum(1 for x in loads + t.get("joins", []) if x.get(flag))
        if n:
            out.append(f"{word} in {n} load(s)")
    if any(x.get("source", {}).get("sql_join") for x in loads):
        out.append("a join inside the SQL SELECT")
    if calculated:
        out.append(f"{calculated} calculated field(s)" + (f", {mapped} of them through a mapping table (ApplyMap)" if mapped else ""))
    return out


def read_script(text: str) -> dict:
    """`migration_read.read_qvs(text)` plus, per table: `table` (the lakehouse name), `columns` (per field: the column
    name, and `from`, `expression`, `mapping` or `via` a join), `sources`, `steps` and `as_loaded`; and for the script:
    `mapping_uses`, `qualified_fields` and `renamed_for_the_lakehouse`. Everything the reader did not read stays under
    `not_read`, with its line."""
    rd = mr.read_qvs(text)
    chains = [c for c in _chains(text) if not c["access"]]
    by_line = {c["line"]: c for c in chains}
    by_label = {c["label"]: c for c in chains if c["label"]}
    maps = {m["name"]: m for m in rd["mapping_tables"]}
    table_names: set[str] = set()
    uses, qualified, renamed = [], [], []
    for t in rd["tables"]:
        t["table"] = column_name(t["name"], table_names)
        table_names.add(t["table"])
        if t["table"] != t["name"]:
            renamed.append({"table": t["name"], "as": t["table"]})
        traced: dict[str, dict] = {}
        for how, entries in (("load", t["loads"]), ("concatenate", t.get("concatenated", [])), ("join", t.get("joins", []))):
            for e in entries:
                chain = by_line.get(e["line"])
                src = e["source"]
                for row in _trace(chain) if chain else []:
                    row = {**row, "via": how, "source": f"{src['kind']} {src.get('name', '')}".strip()}
                    traced.setdefault(row["field"], row)
        through = []                                                    # resident tables that were dropped later: read through
        for e in t["loads"] + t.get("concatenated", []):
            name = e["source"].get("name", "")
            if e["source"]["kind"] == "resident" and not any(x["name"] == name for x in rd["tables"]):
                for c in chains:
                    joined = c["prefixes"].get("join") and c["prefixes"].get("target") == name
                    if c["label"] == name or (c["prefixes"].get("target") == name and not c["prefixes"].get("mapping")):
                        src = c["levels"][-1]["source"]
                        said = f"{src['kind']} {src.get('name', '')}".strip()
                        for row in _trace(c):
                            traced.setdefault(row["field"], {**row, "via": f"{'join' if joined else 'load'} into {name}, dropped later",
                                                             "source": said})
                        if joined:
                            through.append(f"{c['prefixes']['join']} join of {said} into {name}, the resident table this one is "
                                           "loaded from (dropped later)")
        cols, taken, calculated, mapped = [], set(), 0, 0
        for f in t["fields"]:
            bare = f[len(t["name"]) + 1:] if f.startswith(t["name"] + ".") else f
            row = {"field": f, "column": column_name(f, taken)}
            taken.add(row["column"])
            if row["column"] != f:
                renamed.append({"table": t["name"], "field": f, "as": row["column"]})
            if bare != f:
                row["qualified"] = True
                qualified.append({"table": t["name"], "field": bare, "as": f})
            hit = traced.get(bare)
            if hit is None:
                row["not_traced"] = "its name is not written in the script (a `*`, or a later Rename)"
            else:
                row.update({k: v for k, v in hit.items() if k != "field" and not (k == "via" and v == "load")})
                if "expression" in hit:
                    calculated += 1
                if "mapping" in hit:
                    mapped += 1
                    m = maps.get(hit["mapping"]["map"])
                    uses.append({"table": t["name"], "field": f, **hit["mapping"], "line": hit["line"],
                                 "mapping_table": ({"fields": m["fields"], "line": m["line"]} if m else "not found in the script"),
                                 "rebuild": "a left join on the mapping table's first column, taking its second; without a match "
                                            + (f"the default {hit['mapping']['default']}" if hit["mapping"]["default"] else "the looked-up value itself")
                                            + "; count the mapping table's first column first: Qlik takes the first row of a "
                                              "repeated value, a join repeats the row"})
            cols.append(row)
        t["columns"] = cols
        sources = []
        for how, entries in (("load", t["loads"]), ("concatenate", t.get("concatenated", [])), ("join", t.get("joins", []))):
            for e in entries:
                s = {"how": how, "kind": e["source"]["kind"], "name": e["source"].get("name", ""), "line": e["line"]}
                if s["kind"] == "resident" and not any(x["name"] == s["name"] for x in rd["tables"]):
                    base = by_label.get(s["name"])                      # a resident table that was dropped later
                    s["dropped_table_loaded_from"] = (f"{base['levels'][-1]['source']['kind']} {base['levels'][-1]['source'].get('name', '')}".strip()
                                                      if base else "not found in the script")
                sources.append(s)
        t["sources"] = sources
        t["steps"] = through + _steps(t, calculated, mapped)
        t["as_loaded"] = not t["steps"]
    return {**rd, "kind": "qlik_script_for_a_lakehouse", "mapping_uses": uses, "qualified_fields": qualified,
            "renamed_for_the_lakehouse": renamed}


def listing(read: dict) -> str:
    """The reading as plain lines, counts first."""
    t = read["tables"]
    lines = [f"{len(t)} table(s), {len(read['associations'])} linking field(s), {len(read['synthetic_keys'])} synthetic key(s), "
             f"{len(read['circular_references'])} circular reference(s), {len(read['not_read'])} statement(s) not read",
             f"{sum(1 for x in t if x['as_loaded'])} table(s) are copies of their source with renamed columns; "
             f"{sum(1 for x in t if not x['as_loaded'])} are shaped in the script"]
    for x in t:
        lines.append(f"- {x['name']}" + (f" (lakehouse: {x['table']})" if x["table"] != x["name"] else "") + f": {len(x['fields'])} field(s)"
                     + ("" if x["as_loaded"] else "; " + "; ".join(x["steps"])))
    for u in read["mapping_uses"]:
        lines.append(f"- mapping: {u['table']}.{u['field']} = {u['map']} looked up by {u['key']}; {u['rebuild'].split(';')[0]}")
    for n in read["not_read"]:
        lines.append(f"- not read, line {n['line']}: {n['statement']} ({n['why']})")
    return "\n".join(lines)
