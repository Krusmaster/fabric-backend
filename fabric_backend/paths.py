"""Join paths through the plan: the shortest chain of relationships between two tables, with the rule per step
and a ready T-SQL SELECT … JOIN … using quoted identifiers (or the SQL of another dialect, `dialect=`; see
fabric_backend/dialects.py). No data is read."""
from __future__ import annotations

from collections import deque

from .dialects import TSQL, Dialect
from .infer import Plan, Relationship, _ref_candidates, _norm, _stem, _words


def _edges(plan: Plan) -> dict[str, list[tuple[str, Relationship, bool]]]:
    """table -> [(neighbour, relationship, forward)]; forward means neighbour is the relationship's target."""
    adj: dict[str, list] = {t.name: [] for t in plan.schema}
    for r in plan.relationships:
        if r.source in adj and r.target in adj:
            adj[r.source].append((r.target, r, True))
            adj[r.target].append((r.source, r, False))
    return adj


def shortest_paths(plan: Plan, start: str, end: str, limit: int = 5) -> list[list[tuple[Relationship, bool]]]:
    """Every shortest path (up to `limit`) as a list of (relationship, forward) steps; [] when none."""
    adj = _edges(plan)
    dist = {start: 0}
    order = deque([start])
    while order:
        x = order.popleft()
        for y, _, _ in adj[x]:
            if y not in dist:
                dist[y] = dist[x] + 1
                order.append(y)
    if end not in dist:
        return []
    out: list[list[tuple[Relationship, bool]]] = []

    def walk(node: str, steps: list) -> None:
        if len(out) >= limit:
            return
        if node == end:
            out.append(list(steps))
            return
        for y, r, fwd in sorted(adj[node], key=lambda e: (e[0], e[1].rule, e[1].source_cols)):
            if dist.get(y) == dist[node] + 1:
                steps.append((r, fwd))
                walk(y, steps)
                steps.pop()
    walk(start, [])
    return out


def sql_for(plan: Plan, start: str, path: list[tuple[Relationship, bool]], top: int = 100, dialect: Dialect = TSQL,
            leave_out: set[tuple[str, str]] | None = None) -> str:
    """SELECT … JOIN … along `path`: the start's key and the end's columns, without the (table, column) pairs in
    `leave_out` (the end's key stands in when nothing else is left)."""
    schema = plan.schema.schema
    qi = dialect.quote
    alias = {start: "t0"}
    tables = [start]
    joins = []
    for i, (r, fwd) in enumerate(path, 1):
        prev = tables[-1]
        nxt = r.target if fwd else r.source
        alias[nxt] = f"t{i}"
        tables.append(nxt)
        left_cols, right_cols = (r.source_cols, r.target_cols) if fwd else (r.target_cols, r.source_cols)
        on = " AND ".join(f"{alias[prev]}.{qi(a)} = {alias[nxt]}.{qi(b)}" for a, b in zip(left_cols, right_cols))
        joins.append(f"JOIN {dialect.table(schema, nxt)} AS {alias[nxt]} ON {on}")
    end = tables[-1]
    start_key = plan.keys.get(start, ([plan.schema[start].column_names[0]], ""))[0]
    select = [f"t0.{qi(c)} AS {qi(f'{start}_{c}')}" for c in start_key]
    leave_out = leave_out or set()
    end_cols = [c for c in plan.schema[end].column_names if (end, c) not in leave_out] or plan.keys.get(end, ([], ""))[0]
    select += [f"{alias[end]}.{qi(c)}" for c in end_cols]
    return dialect.select(", ".join(select), f"\nFROM {dialect.table(schema, start)} AS t0\n" + "\n".join(joins), top)


def _components(plan: Plan) -> dict[str, int]:
    adj = _edges(plan)
    comp: dict[str, int] = {}
    for i, t in enumerate(sorted(adj)):
        if t in comp:
            continue
        comp[t] = i
        stack = [t]
        while stack:
            x = stack.pop()
            for y, _, _ in adj[x]:
                if y not in comp:
                    comp[y] = i
                    stack.append(y)
    return comp


def missing_link_suggestions(plan: Plan, start: str, end: str, limit: int = 5) -> list[dict]:
    """When no path exists: columns on the start side that look like references (a reference suffix, not in any
    relationship) paired with single-key tables on the end side of the same data type, ranked by shared name words."""
    comp = _components(plan)
    side_a = {t for t, c in comp.items() if c == comp[start]}
    side_b = {t for t, c in comp.items() if c == comp[end]}
    linked = {(r.source, c.lower()) for r in plan.relationships for c in r.source_cols}
    types = {(t.name, c.name): (c.data_type or "").lower().split("(")[0] for t in plan.schema for c in t.columns}
    out = []
    for a_side, b_side in ((side_a, side_b), (side_b, side_a)):
        for ta in sorted(a_side):
            for c in plan.schema[ta].column_names:
                stem, suf = _stem(c)
                if not suf or (ta, c.lower()) in linked or c in plan.keys.get(ta, ([], ""))[0]:
                    continue
                for tb in sorted(b_side):
                    key = plan.keys.get(tb, ([], ""))[0]
                    if len(key) != 1 or types.get((tb, key[0])) != types.get((ta, c)):
                        continue
                    words = set(stem) | set(_words(c))
                    score = len(words & set(_words(tb))) + (2 if _norm(c) in _ref_candidates(tb) else 0)
                    out.append({"score": score, "strength": "name and type" if score else "type only",
                                "source": ta, "source_cols": [c], "target": tb, "target_cols": [key[0]],
                                "why": f"{ta}.{c} looks like a reference ({c!r} ends in {suf!r}), is in no relationship, and has the "
                                       f"same type as {tb}.{key[0]}" + ("; the names share a word" if score else "")})
    out.sort(key=lambda s: (-s["score"], s["source"], s["source_cols"], s["target"]))
    for s in out:
        s["confirmed"] = {"source": s["source"], "source_cols": s["source_cols"], "target": s["target"], "target_cols": s["target_cols"]}
    return out[:limit]


def _steps(plan: Plan, start: str, p: list[tuple[Relationship, bool]], verified: set) -> list[dict]:
    from .graphs import certainty
    steps, node = [], start
    for r, fwd in p:
        nxt = r.target if fwd else r.source
        w = certainty(r, verified)
        steps.append({"from": node, "to": nxt, "on": [f"{a} = {b}" for a, b in zip(r.source_cols, r.target_cols)] if fwd
                      else [f"{b} = {a}" for a, b in zip(r.source_cols, r.target_cols)],
                      "rule": r.rule, "certainty": w, "cost": round(1 / w, 4), "direction": "many-to-one" if fwd else "one-to-many"})
        node = nxt
    return steps


def join_path(plan: Plan, start: str, end: str, limit: int = 5, top: int = 100, validation: dict | None = None,
              dialect: Dialect = TSQL) -> dict:
    names = {t.name.lower(): t.name for t in plan.schema}
    missing = [x for x in (start, end) if x.lower() not in names]
    if missing:
        from .infer import PlanInputError
        raise PlanInputError("tables: not in the schema: " + ", ".join(repr(m) for m in missing))
    start, end = names[start.lower()], names[end.lower()]
    if start == end:
        return {"start": start, "end": end, "paths": [], "note": "start and end are the same table"}
    from .graphs import _verified, counted_active_set, edges, safest_path
    verified = _verified(validation)
    # BL63: with validate_plan's counts, the safest path follows the semantic model's active set (BL51's counted rules)
    # where one connects the two tables, and every step says whether its relationship is active there. Without counts,
    # or with an answer that counted none of the links, the answer is exactly as before.
    by_counts = counted_active_set(plan, edges(plan, validation), validation) if validation else None
    active_ids = {id(e["rel"]) for e in by_counts[0]} if by_counts is not None else None
    why_off = {id(e["rel"]): e["why"] for e in by_counts[1]} if by_counts is not None else {}

    def mark(steps: list[dict], chain: list) -> list[dict]:
        if active_ids is None:
            return steps
        for st, (r, _fwd) in zip(steps, chain):
            st["active"] = id(r) in active_ids
            if id(r) in why_off:
                st["inactive_why"] = why_off[id(r)]
        return steps
    paths = shortest_paths(plan, start, end, limit)
    out: dict = {"start": start, "end": end, "paths": []}
    for p in paths:
        steps = mark(_steps(plan, start, p, verified), p)
        out["paths"].append({"tables": [start] + [s["to"] for s in steps], "hops": len(steps), "steps": steps,
                             "cost": round(sum(s["cost"] for s in steps), 4), "sql": sql_for(plan, start, p, top, dialect)})
    safest = safest_path(plan, start, end, validation, only=active_ids) if active_ids is not None else None
    on_active = safest is not None
    if safest is None:
        safest = safest_path(plan, start, end, validation)
    if safest:
        chain = [(s["rel"], s["forward"]) for s in safest]
        steps = mark(_steps(plan, start, chain, verified), chain)
        out["safest"] = {"tables": [start] + [s["to"] for s in steps], "hops": len(steps), "steps": steps,
                         "cost": round(sum(s["cost"] for s in steps), 4), "sql": sql_for(plan, start, chain, top, dialect)}
        shortest_cost = min(p["cost"] for p in out["paths"])
        if active_ids is not None:
            out["active_by_counts"] = on_active
            out["safest"]["why"] = (
                ("it goes over the relationships the semantic model keeps active by validate_plan's counts (BL51)"
                 + ("; it is also a shortest path" if out["safest"]["hops"] <= min(p["hops"] for p in out["paths"]) else
                    "; a shorter path uses a relationship the counts left inactive (see each step's inactive_why)"))
                if on_active else
                "no path over the relationships the counts keep active connects the two tables, so this one uses an inactive "
                "relationship (see each step's active and inactive_why); in the semantic model it needs USERELATIONSHIP")
        elif out["safest"]["cost"] < shortest_cost - 1e-9:
            weakest = min((s for p in out["paths"] for s in p["steps"]), key=lambda s: s["certainty"])
            out["safest"]["why"] = (f"the shortest path uses a {weakest['rule']} link ({weakest['from']} -> {weakest['to']}, certainty "
                                    f"{weakest['certainty']}); the safest takes {out['safest']['hops']} hop(s) over links of certainty "
                                    f"{min(s['certainty'] for s in steps)} or more (cost {out['safest']['cost']} against {shortest_cost})")
        else:
            out["safest"]["why"] = "the shortest path is also the safest"
    if not paths:
        out["note"] = f"no chain of relationships connects {start} and {end}"
        out["suggestions"] = missing_link_suggestions(plan, start, end)
        if not out["suggestions"]:
            out["note"] += "; no column on either side looks like a reference to the other, so a relationship would need to be given in `confirmed`"
    elif len(paths) > 1:
        out["note"] = f"{len(paths)} paths of {paths[0].__len__()} hops are equally short; each is listed with its SQL"
    return out
