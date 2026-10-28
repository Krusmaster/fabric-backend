"""Compact answers for large schemas: `detail="summary"` and a `tables` pattern filter for list_tables, plan_backend and
analyze_schema (remote and stdio servers).

An agent pays for every token of an answer and has a bounded context. On the synthetic shop schema the full answers are
a few kilobytes; on 300 tables plan_backend is ~400 kB and analyze_schema ~800 kB, on 1 000 tables 1.4 MB and 3 MB
(measured 26 October 2026, docs/INFERENCE.md). So:

- `detail="auto"` (the default) answers in full up to COMPACT_ABOVE tables and in summary form above that, and says so;
  `detail="full"` and `detail="summary"` force either.
- `tables=["sales_*", "customers"]` narrows the answer to the tables that match (fnmatch patterns, case-insensitive,
  exact names allowed); the plan itself is still made from the whole schema, so relationships into other tables are kept.
"""
from __future__ import annotations

import json
from fnmatch import fnmatchcase

from .infer import Plan, PlanInputError
from .schema import Schema

COMPACT_ABOVE = 60
DETAILS = ("auto", "full", "summary")
KEEP_WHOLE = ("columns", "source_cols", "target_cols", "target_columns", "key", "confirmed", "keys")   # identifier lists: cutting them changes the meaning


def pick_detail(detail: str | None, n_tables: int) -> str:
    d = (detail or "auto").strip().lower()
    if d not in DETAILS:
        raise PlanInputError(f"detail: {detail!r} is not one of {', '.join(DETAILS)}")
    if d == "auto":
        return "summary" if n_tables > COMPACT_ABOVE else "full"
    return d


def match_tables(schema: Schema, patterns: list[str] | None) -> set[str] | None:
    """The table names that match any pattern; None when no filter was given."""
    if patterns is None:
        return None
    if not isinstance(patterns, (list, tuple)) or not patterns:
        raise PlanInputError("tables: give a non-empty list of names or patterns such as [\"sales_*\"], or omit it")
    names = [t.name for t in schema]
    out: set[str] = set()
    for pat in patterns:
        p = str(pat).lower()
        hits = [n for n in names if fnmatchcase(n.lower(), p) or n.lower() == p]      # an exact name wins even with [ ] * ? in it
        if not hits:
            raise PlanInputError(f"tables: nothing matches {pat!r}; the schema has {len(names)} tables such as {', '.join(names[:5])}")
        out.update(hits)
    return out


def sub_plan(p: Plan, keep: set[str] | None) -> Plan:
    """The plan restricted to `keep` for display: those tables, the relationships with at least one end among them."""
    if keep is None:
        return p
    s = Schema(tables={n: t for n, t in p.schema.tables.items() if n in keep}, schema=p.schema.schema)
    return Plan(s, {t: k for t, k in p.keys.items() if t in keep},
                [r for r in p.relationships if r.source in keep or r.target in keep],
                [a for a in p.ambiguous if a["table"] in keep], [t for t in p.keyless if t in keep],
                [x for x in p.synonyms if x.get("table") in keep], pack=p.pack,
                extended=[r for r in p.extended if r.source in keep or r.target in keep])


NARROW_HINT = "Narrow the answer with tables=[\"pattern*\"] (names or fnmatch patterns), or ask for one area at a time."


def rel_line(r) -> str:
    """`orders.customer_id -> customers [R1]`: the target's key column is under keys, so it is not repeated here."""
    return f"{r.source}.{'+'.join(r.source_cols)} -> {r.target} [{r.rule}]" + (f" ({r.note})" if getattr(r, "note", "") else "")


def plan_summary(p: Plan, suggested_keys: list[dict], scope_note: str = "") -> dict:
    """plan_backend in summary form: one line per key and relationship, no field names, no diagram."""
    out = {
        "summary": p.summary(),
        "detail": "summary",
        "keys": {t: f"{'+'.join(k)} ({r})" for t, (k, r) in p.keys.items()},
        "relationships": [rel_line(r) for r in p.relationships],
        "ambiguous": [f"{a['table']}.{a['column']} could point at {', '.join(a['candidates'])} ({a.get('rule', '')})" for a in p.ambiguous],
        "keyless": p.keyless,
        "suggested_keys": [f"{s['table']}: {'+'.join(s['columns'])} ({s['why']})" for s in suggested_keys],
        "synonyms": [f"{x['table']}.{x['column']}" + (f" -> {x['target']}" if x.get("target") else "") + f" [{x['rule']}] via {x['via']}" for x in p.synonyms],
        "note": ("Summary form" + (f" ({scope_note})" if scope_note else "") + ": detail=\"full\" adds the GraphQL field names, the suggested-key "
                 "details and the Mermaid ER diagram; tables=[\"pattern*\"] narrows the answer to matching tables."),
    }
    if p.extended:
        out["extended_relationships"] = [f"{r.source} -> {r.target} ({r.kind}, {r.rule}): {r.join_sql()}" for r in p.extended]
    return out


def _extended(r) -> dict:
    """An ExtendedRelationship for an answer: what it joins and how, in one line of SQL."""
    out = {"source": r.source, "source_cols": r.source_cols, "target": r.target, "target_cols": r.target_cols,
           "kind": r.kind, "cardinality": r.cardinality, "rule": r.rule, "join": r.join_sql()}
    if r.valid_on:
        out["valid_on"] = r.valid_on
    if r.note:
        out["note"] = r.note
    return out


def plan_full(p: Plan, suggested_keys: list[dict], mermaid: bool = True) -> dict:
    out = {
        "summary": p.summary(),
        "keys": {t: {"columns": k, "rule": r} for t, (k, r) in p.keys.items()},
        "relationships": [{k: v for k, v in r.__dict__.items() if k != "note" or v} for r in p.relationships],   # an empty note is noise
        "ambiguous": p.ambiguous, "keyless": p.keyless,
        "suggested_keys": suggested_keys,
    }
    if p.synonyms:
        out["synonyms"] = p.synonyms
    if p.extended:                                     # only with a knowledge pack: other answers are unchanged
        out["extended_relationships"] = [_extended(r) for r in p.extended]
    if p.pack:
        out["pack"] = {k: p.pack[k] for k in ("pack", "rule", "status", "variant_hint", "not_applied", "missing_tables",
                                               "missing_columns", "client_dropped") if p.pack.get(k)}
    if mermaid:
        out["mermaid"] = p.mermaid()
    return out


def tables_summary(schema: Schema, keep: set[str] | None = None) -> dict:
    tables = [t for t in schema if keep is None or t.name in keep]
    return {"tables": len(tables), "columns": sum(len(t.columns) for t in tables),
            "per_table": {t.name: len(t.columns) for t in tables},
            "note": "Summary form: detail=\"full\" lists every column with its type; tables=[\"pattern*\"] narrows the answer."}


def tables_full(schema: Schema, keep: set[str] | None = None) -> dict:
    return {t.name: [[c.name, c.data_type] for c in t.columns] for t in schema if keep is None or t.name in keep}


def analysis_summary(a: dict, keep: set[str] | None = None, top: int = 10, inactive: int = 30) -> dict:
    """analyze_schema in summary form: tables grouped by role, the central tables, areas by size, counts for the rest."""
    roles = a.get("roles", {})
    by_role: dict[str, list[str]] = {}
    for t, r in roles.items():
        if keep is None or t in keep:
            by_role.setdefault(r["role"], []).append(t)
    central = [{"table": c["table"], "role": c["role"], "pagerank": c["pagerank"], "in": c["in"], "out": c["out"]}
               for c in a.get("centrality", {}).get("top", []) if keep is None or c["table"] in keep][:top]
    areas = [{"name": g["name"], "central_table": g["central_table"], "tables": len(g["tables"]), "first": g["tables"][:8]}
             for g in a.get("areas", []) if keep is None or any(t in keep for t in g["tables"])]
    amb = a.get("ambiguity", {})
    inact = [e for e in a.get("inactive_relationships", []) if keep is None or e["source"] in keep or e["target"] in keep]
    act = [e for e in a.get("active_relationships", []) if keep is None or e["source"] in keep or e["target"] in keep]
    return {
        "summary": a.get("summary", ""), "detail": "summary",
        "roles": {k: sorted(v) for k, v in sorted(by_role.items())},
        "central": central,
        "areas": sorted(areas, key=lambda g: -g["tables"]),
        "ambiguity": {"cycles": len(amb.get("cycles", [])), "pairs_with_multiple_paths": len(amb.get("pairs_with_multiple_paths", [])),
                      "first_pairs": amb.get("pairs_with_multiple_paths", [])[:10], "note": amb.get("note", "")},
        "active_relationships": len(act),
        "inactive_relationships": {"count": len(inact),
                                   "first": [f"{e['source']}.{'+'.join(e['columns'])} -> {e['target']} [{e['rule']} {e['certainty']}]: {e.get('why', '')}" for e in inact[:inactive]]},
        "note": ("Summary form: detail=\"full\" gives the reasons per table, every centrality measure, every cycle and every inactive "
                 "relationship; tables=[\"pattern*\"] narrows the answer."),
    }


def analysis_filtered(a: dict, keep: set[str] | None) -> dict:
    """The tool's full answer: without the constant `weights` and the per-table centrality maps (the ten most central
    tables keep their numbers and every role carries its own), optionally narrowed to `keep`."""
    out = {k: v for k, v in a.items() if k != "weights"}
    out["centrality"] = {"top": list(a["centrality"]["top"])}
    if keep is None:
        return out
    out["roles"] = {t: r for t, r in a["roles"].items() if t in keep}
    out["centrality"] = {"top": [x for x in a["centrality"]["top"] if x["table"] in keep]}
    out["areas"] = [g for g in a["areas"] if any(t in keep for t in g["tables"])]
    for k in ("active_relationships", "inactive_relationships"):
        out[k] = [e for e in a[k] if e["source"] in keep or e["target"] in keep]
    return out


def bounded_text(body: dict, key: str, limit: int, hint: str = NARROW_HINT) -> str:
    """A document answer (`markdown`, `yaml`) of at most `limit` characters: the text is cut on a line boundary and the
    answer says where and what to do."""
    text = json.dumps(body, indent=2, default=str)
    if len(text) <= limit:
        return text
    doc = str(body.get(key, ""))
    room = max(50, limit - (len(text) - len(json.dumps(doc))) - 400)
    out = dict(body)
    while True:                                                      # JSON escaping makes the text longer than the characters it holds
        cut = doc[:room]
        cut = cut[: cut.rfind("\n") + 1] if "\n" in cut and cut.rfind("\n") > room // 2 else cut
        out[key] = cut
        out["truncated"] = f"{key} cut after {len(cut)} of {len(doc)} characters: the whole document was too large for one answer. " + hint
        text = json.dumps(out, indent=2, default=str)
        if len(text) <= limit or room <= 50:
            return text
        room = int(room * 0.8)


def bounded(body, limit: int, hint: str = "Ask for fewer fields or page with first:/after.", drop: tuple[str, ...] = ()) -> str:
    """JSON of at most `limit` characters, always valid JSON. A result that is too large first loses the keys in `drop`
    (the Mermaid diagram of a plan), then has its lists cut to the same number of leading items each, and says so
    under `truncated`, instead of being chopped mid-document."""
    text = json.dumps(body, indent=2, default=str)
    if len(text) <= limit:
        return text
    dropped = [k for k in drop if isinstance(body, dict) and k in body]
    omitted = ""
    if dropped:
        omitted = f"{', '.join(dropped)} omitted; "
        body = {k: v for k, v in body.items() if k not in dropped}
        body["truncated"] = f"{', '.join(dropped)} omitted: the full result was too large for one answer. " + hint
        text = json.dumps(body, indent=2, default=str)
        if len(text) <= limit:
            return text

    def longest(node) -> int:
        if isinstance(node, list):
            return max([len(node)] + [longest(x) for x in node])
        if isinstance(node, dict):
            return max([0] + [longest(v) for v in node.values()])
        return 0

    def cut(node, keep):
        if isinstance(node, list):
            return [cut(x, keep) for x in node[:keep]]
        if isinstance(node, dict):
            return {k: (v if k in KEEP_WHOLE else cut(v, keep)) for k, v in node.items()}
        return node

    if not isinstance(body, dict):
        body = {"items": body}
    keep = longest(body)
    while keep > 1:
        keep //= 2
        slim = cut(body, keep)
        slim = dict(slim, truncated=f"{omitted}the full result was too large for one answer; every list was cut to its first {keep} items. " + hint)
        text = json.dumps(slim, indent=2, default=str)
        if len(text) <= limit:
            return text
    if isinstance(body, dict):                                        # a document in one string field: cut the longest string on a line
        strings = [k for k, v in body.items() if isinstance(v, str)]
        if strings:
            longest = max(strings, key=lambda k: len(body[k]))
            text = bounded_text(body, longest, limit, hint)
            if len(text) <= limit:
                return text
    preview = json.dumps(body, default=str)[:max(20, limit // 2 - 400)]
    return json.dumps({"truncated": "The result was too large for one answer even with one item per list; this is the start of it. "
                                    "Ask for fewer fields.", "preview": preview}, indent=2)
