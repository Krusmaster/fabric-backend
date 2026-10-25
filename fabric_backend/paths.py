"""Join paths through the plan: the shortest chain of relationships between two tables, with the rule per step
and a ready T-SQL SELECT … JOIN … using quoted identifiers. No data is read."""
from __future__ import annotations

from collections import deque

from .evidence import qi
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


def sql_for(plan: Plan, start: str, path: list[tuple[Relationship, bool]], top: int = 100) -> str:
    schema = plan.schema.schema
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
        joins.append(f"JOIN {qi(schema)}.{qi(nxt)} AS {alias[nxt]} ON {on}")
    end = tables[-1]
    start_key = plan.keys.get(start, ([plan.schema[start].column_names[0]], ""))[0]
    select = [f"t0.{qi(c)} AS {qi(f'{start}_{c}')}" for c in start_key]
    select += [f"{alias[end]}.{qi(c)}" for c in plan.schema[end].column_names]
    return (f"SELECT TOP ({int(top)}) " + ", ".join(select) + f"\nFROM {qi(schema)}.{qi(start)} AS t0\n" + "\n".join(joins))


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


def join_path(plan: Plan, start: str, end: str, limit: int = 5, top: int = 100, validation: dict | None = None) -> dict:
    names = {t.name.lower(): t.name for t in plan.schema}
    missing = [x for x in (start, end) if x.lower() not in names]
    if missing:
        from .infer import PlanInputError
        raise PlanInputError("tables: not in the schema: " + ", ".join(repr(m) for m in missing))
    start, end = names[start.lower()], names[end.lower()]
    if start == end:
        return {"start": start, "end": end, "paths": [], "note": "start and end are the same table"}
    from .graphs import _verified, safest_path
    verified = _verified(validation)
    paths = shortest_paths(plan, start, end, limit)
    out: dict = {"start": start, "end": end, "paths": []}
    for p in paths:
        steps = _steps(plan, start, p, verified)
        out["paths"].append({"tables": [start] + [s["to"] for s in steps], "hops": len(steps), "steps": steps,
                             "cost": round(sum(s["cost"] for s in steps), 4), "sql": sql_for(plan, start, p, top)})
    safest = safest_path(plan, start, end, validation)
    if safest:
        chain = [(s["rel"], s["forward"]) for s in safest]
        steps = _steps(plan, start, chain, verified)
        out["safest"] = {"tables": [start] + [s["to"] for s in steps], "hops": len(steps), "steps": steps,
                         "cost": round(sum(s["cost"] for s in steps), 4), "sql": sql_for(plan, start, chain, top)}
        shortest_cost = min(p["cost"] for p in out["paths"])
        if out["safest"]["cost"] < shortest_cost - 1e-9:
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
