"""A star schema proposed from a Qlik script's associations (Q2), and the script's statements counted by type.

`star_schema(mapping)` sorts what `map_associations` decided into facts, dimensions, tables in between, dimensions that
do not exist yet, and what a person decides. It adds no relationship of its own: a table is a fact because it points
at other tables and nothing points at it, and a dimension because others point at it. `changes` lists what must be
built for the model to be a star: combined key columns, new dimension tables, fields to rename.

`statement_coverage(read)` counts the statements of a script by type and by what the reader did with each: `read`
(applied to the tables, or known to leave them as they are), `control_flow` (If, For, Sub and the like: listed, and
the loads inside them read as if each ran once), `include` (another file, which was not given) and `not_read`.
"""
from __future__ import annotations


def star_schema(mapping: dict) -> dict:
    tables = {t["table"]: t for t in mapping["tables"]}
    rels = [r for r in mapping["relationships"] if r["in_plan"] == "relationship"]
    out_of: dict[str, list[dict]] = {}
    into: dict[str, list[dict]] = {}
    for r in rels:
        out_of.setdefault(r["source"], []).append(r)
        into.setdefault(r["target"], []).append(r)
    facts, dims, steps = [], [], []
    for name, t in tables.items():
        if name in out_of and name not in into:
            facts.append({"table": name, "dimensions": [{"table": r["target"], "on": r["source_cols"]} for r in out_of[name]]})
        elif name in into and name not in out_of:
            dims.append({"table": name, "key": t.get("key", []), "used_by": sorted({r["source"] for r in into[name]})})
        elif name in into and name in out_of:
            steps.append({"table": name, "key": t.get("key", []), "used_by": sorted({r["source"] for r in into[name]}),
                          "points_at": [{"table": r["target"], "on": r["source_cols"]} for r in out_of[name]],
                          "what": "others point at it and it points on: a header above its lines, a fact another fact refers to, or a dimension with a "
                                  "parent (a snowflake step). A star keeps it as it is, or folds the parent's columns "
                                  "into it: a person decides"})
    proposed, changes, decide = [], [], []
    for s in mapping["synthetic_keys"]:
        a, b = s["tables"]
        if s["case"] == "two_facts_sharing_dimensions":
            for d in s["dimensions"]:
                if d["dimension"] is None:
                    proposed.append({"field": d["field"], "for": [a, b],
                                     "what": f"a new dimension table of the distinct values of {d['field']}, which {a} and {b} "
                                             "both relate to"})
                    changes.append(f"Build a dimension table of the distinct values of {d['field']} for {a} and {b}.")
        elif s["case"] == "composite_key":
            f = "+".join(s["link"]["fields"])
            changes.append(f"Add one combined key column for {f} to {s['link']['source']} and {s['link']['target']} "
                           "(a relationship has one column per side).")
        elif s["case"] == "one_field_links":
            for o in s["other_fields"]:
                changes.append(f"{o['field']} is shared by {a} and {b} beside the link on {s['link']['field']}: {o['proposal']}.")
        else:
            decide.append({"between": [a, b], "fields": s["fields"], "why": s.get("why", "")})
    for x in mapping["shared_fields_with_no_key_side"]:
        decide.append({"field": x["field"], "tables": x["tables"], "why": x["in_the_model"]})
    for u in mapping["undecided"]:
        decide.append({"field": u["field"], "tables": u["tables"], "why": u["why"]})
    for p in mapping["two_paths"]:
        changes.append(f"Two ways lead between {p['between'][0]} and {p['between'][1]}: the model keeps one active "
                       f"({p['other_way'][0] if p['other_way'] else p['one_way']}) and the other inactive.")
    return {
        "facts": facts, "dimensions": dims, "tables_in_between": steps, "proposed_dimensions": proposed,
        "bridge_candidates": [{"table": x["table"], "links": x["links"]} for x in mapping["link_table_candidates"]],
        "not_linked": [n for n, t in tables.items() if t["role"] == "not linked"],
        "changes": changes, "a_person_decides": decide,
        "note": "a proposal from the associations in the script; nothing in it is built, and a table's role follows "
                "from which tables point at which",
    }


def statement_coverage(read: dict) -> dict:
    by_type: dict[str, dict[str, int]] = {}
    totals = {"total": 0, "read": 0, "control_flow": 0, "include": 0, "not_read": 0}
    names = {"read": "read", "control": "control_flow", "include": "include", "not_read": "not_read"}
    for s in read.get("statements", []):
        col = names[s["outcome"]]
        row = by_type.setdefault(s["type"], {"total": 0, "read": 0})
        row["total"] += 1
        row[col] = row.get(col, 0) + 1
        totals["total"] += 1
        totals[col] += 1
    return {**totals, "by_type": dict(sorted(by_type.items(), key=lambda kv: (-kv[1]["total"], kv[0])))}


def add_coverage(a: dict, b: dict) -> dict:
    """Two coverage counts as one."""
    out = {k: a.get(k, 0) + b.get(k, 0) for k in ("total", "read", "control_flow", "include", "not_read")}
    by: dict[str, dict[str, int]] = {}
    for src in (a.get("by_type", {}), b.get("by_type", {})):
        for t, row in src.items():
            tgt = by.setdefault(t, {})
            for k, v in row.items():
                tgt[k] = tgt.get(k, 0) + v
    out["by_type"] = dict(sorted(by.items(), key=lambda kv: (-kv[1]["total"], kv[0])))
    return out
