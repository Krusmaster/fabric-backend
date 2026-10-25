"""Graph theory on the plan: tables are nodes, relationships are directed edges (many side -> one side) with a
certainty per rule. Pure Python, deterministic (sorted node order, fixed tie-breaks), no data queries except the
inclusion check that `suggest_relationships` asks evidence.py to run.

Edge certainty (weight) and cost = 1 / certainty:

| Origin of the relationship                                   | certainty | cost  |
| ------------------------------------------------------------ | --------- | ----- |
| R0 declared foreign key, `confirmed` by the caller           | 1.0       | 1.00  |
| any rule, and `evidence.validate` said the link holds        | 0.9       | 1.11  |
| R1 column named after the target table                       | 0.8       | 1.25  |
| R2 column with the target key's name                         | 0.6       | 1.67  |
| R3 all columns of a composite key present                    | 0.5       | 2.00  |
| R4 role prefix or abbreviation (weaker name match)           | 0.5       | 2.00  |

A verified link (holds, no orphans) is worth 0.9 whatever its rule, but a declared or confirmed one keeps 1.0.
"""
from __future__ import annotations

import math
from collections import deque

from .infer import Plan, Relationship, _abbreviates, _stem, _singulars, _words

WEIGHTS = {"R0": 1.0, "confirmed": 1.0, "verified": 0.9, "R1": 0.8, "R2": 0.6, "R3": 0.5, "R4": 0.5}
DEFAULT_WEIGHT = 0.5
PAGERANK_DAMPING = 0.85
PAGERANK_ROUNDS = 100
MEASURE_TYPES = ("int64", "double", "decimal", "dateTime")


# ------------------------------------------------------------------ edges and weights -----------

def _verified(validation: dict | None) -> set[tuple]:
    out = set()
    for r in (validation or {}).get("relationships", []):
        if str(r.get("verdict", "")).startswith("holds"):
            out.add((r["source"], tuple(c.lower() for c in r["columns"]), r["target"]))
    return out


def certainty(r: Relationship, verified: set[tuple] = frozenset()) -> float:
    base = WEIGHTS.get(r.rule, DEFAULT_WEIGHT)
    if base < WEIGHTS["verified"] and r.key in verified:
        return WEIGHTS["verified"]
    return base


def edges(plan: Plan, validation: dict | None = None) -> list[dict]:
    """One dict per relationship: source, target, columns, rule, certainty, cost — sorted for determinism."""
    ok = _verified(validation)
    out = []
    for r in plan.relationships:
        w = certainty(r, ok)
        out.append({"source": r.source, "target": r.target, "columns": list(r.source_cols), "target_columns": list(r.target_cols),
                    "rule": r.rule, "certainty": w, "cost": round(1 / w, 4), "verified": r.key in ok, "rel": r})
    out.sort(key=lambda e: (e["source"], e["target"], e["columns"]))
    return out


def _adjacency(plan: Plan, es: list[dict]) -> tuple[dict[str, list[dict]], dict[str, list[dict]], dict[str, list[tuple[str, dict]]]]:
    """out-edges, in-edges, and the undirected view (neighbour, edge)."""
    out: dict[str, list[dict]] = {t.name: [] for t in plan.schema}
    inn: dict[str, list[dict]] = {t.name: [] for t in plan.schema}
    und: dict[str, list[tuple[str, dict]]] = {t.name: [] for t in plan.schema}
    for e in es:
        if e["source"] in out and e["target"] in inn:
            out[e["source"]].append(e)
            inn[e["target"]].append(e)
            und[e["source"]].append((e["target"], e))
            und[e["target"]].append((e["source"], e))
    return out, inn, und


# ------------------------------------------------------------------ centrality -------------------

def betweenness(nodes: list[str], und: dict[str, list[tuple[str, dict]]]) -> dict[str, float]:
    """Brandes' algorithm on the undirected, unweighted graph (how often a table sits on the shortest route between
    two others); normalised to [0, 1] by (n-1)(n-2)/2."""
    bc = {v: 0.0 for v in nodes}
    for s in nodes:
        stack: list[str] = []
        pred: dict[str, list[str]] = {v: [] for v in nodes}
        sigma = {v: 0.0 for v in nodes}
        dist = {v: -1 for v in nodes}
        sigma[s], dist[s] = 1.0, 0
        q = deque([s])
        while q:
            v = q.popleft()
            stack.append(v)
            for w, _ in sorted(und[v], key=lambda x: x[0]):
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    q.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = {v: 0.0 for v in nodes}
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                bc[w] += delta[w]
    n = len(nodes)
    scale = (n - 1) * (n - 2) if n > 2 else 1          # undirected: each pair counted twice above, so no extra /2
    return {v: round(bc[v] / scale, 4) for v in nodes}


def pagerank(nodes: list[str], out: dict[str, list[dict]], damping: float = PAGERANK_DAMPING, rounds: int = PAGERANK_ROUNDS) -> dict[str, float]:
    """Power iteration on the directed graph (a reference is a vote for its target), uniform start, dangling mass
    spread evenly; fixed round count, so the same plan gives the same numbers."""
    n = len(nodes)
    if n == 0:
        return {}
    rank = {v: 1.0 / n for v in nodes}
    for _ in range(rounds):
        dangling = sum(rank[v] for v in nodes if not out[v])
        new = {v: (1 - damping) / n + damping * dangling / n for v in nodes}
        for v in nodes:
            if out[v]:
                share = rank[v] / len(out[v])
                for e in out[v]:
                    new[e["target"]] += damping * share
        rank = new
    return {v: round(rank[v], 4) for v in nodes}


# ------------------------------------------------------------------ roles ------------------------

_AUDIT = ("modified", "created", "updated", "rowguid", "last_update", "lastupdate", "inserted", "loaded", "etl")


def measure_share(plan: Plan, table: str, ref_cols: set[str]) -> float:
    """Among the columns that are neither key nor reference nor audit stamps, the share that are numbers or dates."""
    from .semantic_model import data_type
    t = plan.schema[table]
    key = {c.lower() for c in plan.keys.get(table, ([], ""))[0]}
    rest = [c for c in t.columns if c.name.lower() not in key and c.name.lower() not in ref_cols
            and not any(a in c.name.lower() for a in _AUDIT)]
    if not rest:
        return 0.0
    return round(sum(1 for c in rest if data_type(c.data_type) in MEASURE_TYPES) / len(rest), 2)


def roles(plan: Plan, es: list[dict], bc: dict[str, float]) -> dict[str, dict]:
    """fact / dimension / bridge / isolated / other, each with the numbers that decided it."""
    out, inn, _ = _adjacency(plan, es)
    refs = {t.name: {c.lower() for e in out[t.name] for c in e["columns"]} for t in plan.schema}
    share = {t.name: measure_share(plan, t.name, refs[t.name]) for t in plan.schema}
    max_bc = max(bc.values(), default=0.0)
    result: dict[str, dict] = {}
    for t in plan.schema:
        n, o, i = t.name, len(out[t.name]), len(inn[t.name])
        key_rule = plan.keys.get(n, ([], "K3"))[1]
        why = f"out {o}, in {i}, betweenness {bc[n]}, measure share {share[n]}"
        if o == 0 and i == 0:
            result[n] = {"role": "isolated", "why": "no relationships in or out"}
        elif key_rule == "K4" or (o >= 2 and i == 0 and len(plan.schema[n].columns) - len(refs[n]) <= 1):
            result[n] = {"role": "bridge", "why": f"many-to-many pattern: {o} references out and {'a junction key (K4)' if key_rule == 'K4' else 'no columns of its own'}; {why}"}
        elif i == 0 and o >= 1 and (o >= 2 or share[n] >= 0.5):
            result[n] = {"role": "fact", "why": f"nothing points at it, {o} reference(s) out, measures {share[n]}; {why}"}
        elif i >= 1 and o <= 1 and share[n] < 0.3:
            result[n] = {"role": "dimension", "why": f"{i} reference(s) in, {o} out, few measures ({share[n]}); {why}"}
        else:
            result[n] = {"role": "other", "why": why}
    # a header table: pointed at by a fact, pointing at dimensions, with measures of its own (orders between order_items and customers)
    changed = True
    while changed:
        changed = False
        for n, r in result.items():
            if r["role"] == "other":
                from_fact = any(result[e["source"]]["role"] == "fact" for e in inn[n])
                if from_fact and out[n] and share[n] >= 0.3:
                    result[n] = {"role": "fact", "why": f"pointed at by a fact table, {len(out[n])} reference(s) out, measures {share[n]} (a header table); " + r["why"]}
                    changed = True
    for n, r in result.items():
        if r["role"] == "other":
            o, i = len(out[n]), len(inn[n])
            if i >= 1 and o >= 2 and bc[n] >= 0.5 * max_bc and max_bc > 0:
                result[n] = {"role": "bridge", "why": f"high betweenness ({bc[n]} of max {max_bc}) as a many side between {o} tables with {i} in; " + r["why"]}
            elif i >= 1 and o <= 1:
                result[n] = {"role": "dimension", "why": f"{i} reference(s) in, {o} out; " + r["why"]}
            elif i == 0 and o >= 1:
                result[n] = {"role": "dimension", "why": f"a leaf that only refers to others (a child entity without measures); " + r["why"]}
    return result


# ------------------------------------------------------------------ communities ------------------

def communities(nodes: list[str], und: dict[str, list[tuple[str, dict]]], pr: dict[str, float]) -> list[dict]:
    """Label propagation on the undirected graph with certainty as edge weight, nodes visited in sorted order, ties
    broken by the smallest label, at most 50 rounds: deterministic. Each area is named after its highest-PageRank
    table."""
    label = {v: v for v in nodes}
    for _ in range(50):
        changed = False
        for v in nodes:
            if not und[v]:
                continue
            score: dict[str, float] = {}
            for w, e in und[v]:
                score[label[w]] = score.get(label[w], 0.0) + e["certainty"]
            best = sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            if best != label[v]:
                label[v] = best
                changed = True
        if not changed:
            break
    groups: dict[str, list[str]] = {}
    for v in nodes:
        groups.setdefault(label[v], []).append(v)
    out = []
    for members in groups.values():
        central = sorted(members, key=lambda m: (-pr.get(m, 0), m))[0]
        out.append({"name": f"{central} area", "central_table": central, "tables": sorted(members)})
    out.sort(key=lambda g: (-len(g["tables"]), g["name"]))
    return out


# ------------------------------------------------------------------ spanning forest and cycles ---

def spanning_forest(plan: Plan, es: list[dict]) -> tuple[list[dict], list[dict]]:
    """Kruskal on certainty (highest first; ties: fewer references leaving the source go later, so a fact table keeps
    its direct links; then names): the relationships a semantic model can have active at once. The rest are inactive
    with the reason."""
    out_deg: dict[str, int] = {}
    for e in es:
        out_deg[e["source"]] = out_deg.get(e["source"], 0) + 1
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    active, inactive = [], []
    for e in sorted(es, key=lambda e: (-e["certainty"], -out_deg[e["source"]], e["source"], e["target"], e["columns"])):
        a, b = find(e["source"]), find(e["target"])
        if a == b:
            if any(x["source"] == e["source"] and x["target"] == e["target"] for x in active):
                why = "a relationship between these two tables is already active"
            else:
                path = _forest_path(active, e["source"], e["target"])
                why = ("it would close a cycle with " + " - ".join(path) + "; the active path has certainty "
                       f"{min((x['certainty'] for x in active if x['source'] in path and x['target'] in path), default=e['certainty'])}, this link {e['certainty']}")
            inactive.append({**e, "why": why})
            continue
        parent[a] = b
        active.append(e)
    return active, inactive


def _forest_path(active: list[dict], a: str, b: str) -> list[str]:
    adj: dict[str, list[str]] = {}
    for e in active:
        adj.setdefault(e["source"], []).append(e["target"])
        adj.setdefault(e["target"], []).append(e["source"])
    prev = {a: None}
    q = deque([a])
    while q:
        v = q.popleft()
        if v == b:
            break
        for w in sorted(adj.get(v, [])):
            if w not in prev:
                prev[w] = v
                q.append(w)
    if b not in prev:
        return [a, b]
    path, v = [], b
    while v is not None:
        path.append(v)
        v = prev[v]
    return path[::-1]


def ambiguity(plan: Plan, es: list[dict], active: list[dict], inactive: list[dict]) -> dict:
    """Cycles (one per relationship the forest left out: the forest path between its ends plus the link itself) and
    the table pairs that therefore have more than one path — where a Power BI model would get ambiguous filter paths."""
    cycles, pairs = [], set()
    for e in inactive:
        path = _forest_path(active, e["source"], e["target"])
        cycle = path if path[-1] == e["source"] or path[0] == e["source"] else path + [e["source"]]
        cycles.append({"tables": path, "closed_by": f"{e['source']}.{'+'.join(e['columns'])} -> {e['target']} ({e['rule']})"})
        for i in range(len(path)):
            for j in range(i + 1, len(path)):
                pairs.add(tuple(sorted((path[i], path[j]))))
    return {"cycles": cycles, "pairs_with_multiple_paths": [list(p) for p in sorted(pairs)][:50],
            "note": ("every relationship beyond a spanning forest closes a cycle; any two tables on a cycle can be reached two ways, "
                     "so a semantic model must leave one link on each cycle inactive" if cycles else "no cycles: every pair of connected tables has exactly one path")}


# ------------------------------------------------------------------ analysis ---------------------

def analyze(plan: Plan, validation: dict | None = None) -> dict:
    es = edges(plan, validation)
    nodes = sorted(t.name for t in plan.schema)
    out, inn, und = _adjacency(plan, es)
    bc = betweenness(nodes, und)
    pr = pagerank(nodes, out)
    role = roles(plan, es, bc)
    degree = {v: {"in": len(inn[v]), "out": len(out[v])} for v in nodes}
    central = sorted(nodes, key=lambda v: (-pr[v], -bc[v], -(degree[v]["in"] + degree[v]["out"]), v))[:10]
    active, inactive = spanning_forest(plan, es)
    amb = ambiguity(plan, es, active, inactive)

    def edge_view(e: dict) -> dict:
        return {k: v for k, v in e.items() if k != "rel"}
    return {
        "summary": (f"{len(nodes)} tables, {len(es)} relationships; roles: "
                    + ", ".join(f"{sum(1 for r in role.values() if r['role'] == k)} {k}" for k in ("fact", "dimension", "bridge", "isolated", "other") if any(r["role"] == k for r in role.values()))
                    + f"; {len(active)} relationships can be active at once, {len(inactive)} would be inactive; {len(amb['cycles'])} cycle(s)"),
        "weights": {k: v for k, v in WEIGHTS.items()},
        "roles": {v: role[v] for v in nodes},
        "centrality": {"top": [{"table": v, "pagerank": pr[v], "betweenness": bc[v], **degree[v], "role": role[v]["role"]} for v in central],
                       "degree": degree, "betweenness": bc, "pagerank": pr},
        "areas": communities(nodes, und, pr),
        "ambiguity": amb,
        "active_relationships": [edge_view(e) for e in active],
        "inactive_relationships": [edge_view(e) for e in inactive],
    }


# ------------------------------------------------------------------ weighted paths ---------------

def safest_path(plan: Plan, start: str, end: str, validation: dict | None = None) -> list[dict] | None:
    """Dijkstra on cost = 1/certainty over the undirected graph; the steps with rule and certainty, or None."""
    es = edges(plan, validation)
    _, _, und = _adjacency(plan, es)
    dist = {start: 0.0}
    prev: dict[str, tuple[str, dict] | None] = {start: None}
    todo = {start}
    done: set[str] = set()
    while todo:
        v = min(todo, key=lambda x: (dist[x], x))
        todo.discard(v)
        done.add(v)
        if v == end:
            break
        for w, e in sorted(und[v], key=lambda x: (x[0], x[1]["columns"])):
            if w in done:
                continue
            nd = dist[v] + e["cost"]
            if nd < dist.get(w, math.inf) - 1e-12:
                dist[w] = nd
                prev[w] = (v, e)
                todo.add(w)
    if end not in prev:
        return None
    steps, v = [], end
    while prev[v] is not None:
        u, e = prev[v]
        fwd = e["source"] == u
        steps.append({"from": u, "to": v, "rule": e["rule"], "certainty": e["certainty"], "cost": e["cost"],
                      "on": [f"{a} = {b}" for a, b in zip(e["columns"], e["target_columns"])] if fwd else [f"{b} = {a}" for a, b in zip(e["columns"], e["target_columns"])],
                      "direction": "many-to-one" if fwd else "one-to-many", "rel": e["rel"], "forward": fwd})
        v = u
    return steps[::-1]


# ------------------------------------------------------------------ link prediction --------------

def _type(c: str) -> str:
    return (c or "").lower().split("(")[0].strip()


def _type_similarity(a: str, b: str) -> float:
    a, b = _type(a), _type(b)
    if a == b:
        return 1.0
    ints = {"int", "integer", "bigint", "smallint", "tinyint", "int64", "long", "short"}
    texts = {"varchar", "nvarchar", "char", "nchar", "string", "text"}
    if a in ints and b in ints or a in texts and b in texts:
        return 0.8
    return 0.0


def _name_similarity(column: str, table: str) -> float:
    stem, _ = _stem(column)
    words = set(stem) if stem else set(_words(column))
    tw = set(_words(table)) | {s for b in _singulars(table) for s in _words(b)}
    if not words or not tw:
        return 0.0
    if any(_abbreviates(w, table) for w in words):
        return 0.7
    inter = words & tw
    return round(len(inter) / len(words | tw), 2) if inter else 0.0


def candidates(plan: Plan, limit: int = 50) -> list[dict]:
    """Columns that could point at another table's single-column key and are in no relationship yet, ranked without
    data: name similarity (role stem vs table name words, abbreviations), type similarity, and triangular closure
    (A already refers to B, and B refers to C: A.x -> C is likelier when x resembles C)."""
    es = edges(plan)
    out, _, _ = _adjacency(plan, es)
    linked = {(e["source"], c.lower()) for e in es for c in e["columns"]}
    reach2 = {t.name: {e2["target"] for e in out[t.name] for e2 in out[e["target"]]} for t in plan.schema}
    single = {t: cols[0] for t, (cols, _) in plan.keys.items() if len(cols) == 1}
    types = {(t.name, c.name): c.data_type for t in plan.schema for c in t.columns}
    found = []
    for t in plan.schema:
        key = {c.lower() for c in plan.keys.get(t.name, ([], ""))[0]}
        for c in t.columns:
            if c.name.lower() in key or (t.name, c.name.lower()) in linked:
                continue
            _, suffix = _stem(c.name)
            for target, tkey in single.items():
                if target == t.name:
                    continue
                ts = _type_similarity(c.data_type, types[(target, tkey)])
                if ts == 0.0:
                    continue
                ns = _name_similarity(c.name, target)
                if ns == 0.0 and not suffix and c.name.lower() != tkey.lower():
                    continue                                                   # a plain attribute of the same type: not a candidate
                tri = 1.0 if target in reach2[t.name] else 0.0
                score = round(3 * ns + ts + tri + (0.5 if suffix else 0.0), 2)
                found.append({"source": t.name, "source_cols": [c.name], "target": target, "target_cols": [tkey], "score": score,
                              "name_similarity": ns, "type_similarity": ts, "triangular_closure": bool(tri),
                              "why": (f"{t.name}.{c.name} ({_type(c.data_type)}) is in no relationship and matches the type of {target}.{tkey}"
                                      + (f"; its name resembles {target} ({ns})" if ns else "")
                                      + (f"; {t.name} already reaches {target} in two hops" if tri else ""))})
    found.sort(key=lambda f: (-f["score"], f["source"], f["source_cols"], f["target"]))
    return found[:limit]


def suggest(plan: Plan, execute=None, check: int = 15, limit: int = 50) -> dict:
    """Candidates, and for the best `check` of them the inclusion evidence from the data when `execute` is given.
    Nothing is applied: each suggestion carries a ready `confirmed` entry."""
    from . import evidence
    cands = candidates(plan, limit)
    checked = 0
    for cand in cands:
        cand["confirmed"] = {"source": cand["source"], "source_cols": cand["source_cols"], "target": cand["target"], "target_cols": cand["target_cols"]}
        if execute is not None and checked < check:
            checked += 1
            row = execute(evidence.inclusion_sql(plan.schema.schema, cand["source"], cand["source_cols"][0], cand["target"], cand["target_cols"][0]))[0]
            with_value, matched, distinct = (evidence._int(row.get(k)) for k in ("with_value", "matched", "distinct_values"))
            cand["evidence"] = {"rows_with_value": with_value, "matched": matched, "distinct_values": distinct,
                                "inclusion": round(matched / with_value, 4) if with_value else None,
                                "verdict": ("every value exists in the target key" if with_value and matched == with_value else
                                            "no rows with a value" if not with_value else f"{with_value - matched} value(s) not in the target key")}
    if execute is not None:
        cands.sort(key=lambda c: (-(c.get("evidence", {}).get("inclusion") or 0), -c["score"], c["source"], c["source_cols"], c["target"]))
    return {"candidates": cands, "checked_against_data": checked,
            "note": "Suggestions only: nothing is applied. Pass the `confirmed` entry of the one you accept to plan_backend or "
                    "create_backend. Inclusion = share of non-NULL values of the column that exist in the target key; 100% with "
                    "many distinct values is strong evidence, 100% with two distinct values is not."}
