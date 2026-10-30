"""Domain drafts: the plan's graph split into proposed domains (domain-driven design), each a candidate data product
with an Open Data Contract Standard (ODCS) v3.2.0 contract written from the plan.

How the split is made (round n56, after feedback from an architect with DDD experience):
- The graph is the plan's tables with a key and its relationships. Each relationship is weighted by how sure the
  engine is of it: declared (R0), confirmed by the caller or from the SAP pack 1.0, R1 0.9, R2 and R3 0.8, R4 0.5,
  an extended join (a unique non-key column, a validity period) 0.6 or 0.4. When validate_plan's counts are given, a
  relationship that holds counts 1.0 and one with orphans half its weight. Coupling through the keys is the one
  criterion of Service Cutter's list (https://github.com/ServiceCutter/ServiceCutter/wiki) a schema alone can show.
- Aggregates first: a table whose key holds its reference to a parent (order_items -> orders, VBAP -> VBAK) is kept
  with that parent, so a header and its items are never proposed in two domains.
- Communities are found with a small Leiden-style method (Traag, Waltman & van Eck 2019,
  https://arxiv.org/abs/1810.08473): local moving on modularity, a refinement that keeps every community connected
  (the property Leiden adds over Louvain), aggregation, repeated until nothing moves. Nodes are visited in name order
  and ties go to the lower community name, so the same schema always gives the same proposal; there is no randomness.
- Honest about what it cannot place: a table without a key cannot carry a uniqueness promise and is "unassigned" (with
  the domain it points at, if any); a group below MIN_TABLES tables is "unassigned" too rather than a domain of one.
- Names: SAP tables the pack recognises are named after their part of order-to-cash ("order-to-cash" itself when a
  domain holds sales documents, deliveries and billing) (public SAP knowledge: sales
  documents, deliveries, billing, customer master, material master, organisation); otherwise the longest common
  name prefix of the domain's tables; otherwise the table the others point at most.
- Relationships between two domains are the interfaces between the data products: the consuming side holds the
  reference, the providing side owns the key.

Pure Python without dependencies, so /check's engine in the browser (Pyodide) can call `propose_from_check(result)`
on the result of browser_check.analyze. Nothing here creates a Fabric domain: that is POST /v1/admin/domains, which
needs a Fabric administrator and Tenant.ReadWrite.All; the customer's admin creates domains from this proposal.
"""
from __future__ import annotations

import re

ODCS_VERSION = "v3.2.0"
MIN_TABLES = 2
RESOLUTION = 1.0
WEIGHTS = {"R0": 1.0, "confirmed": 1.0, "SAP pack": 1.0, "R1": 0.9, "R2": 0.8, "R3": 0.8, "R4": 0.5}
EXTENDED_WEIGHTS = {"unique": 0.6, "key": 0.6, "valid_on": 0.4}

# Public SAP ERP tables by their part of order-to-cash (SD and its master data), as named in SAP's own documentation.
SAP_AREAS = {
    "sales documents": ("VBAK", "VBAP", "VBEP", "VBPA", "VBFA", "VBUK", "VBUP", "VBKD", "KONV"),
    "deliveries": ("LIKP", "LIPS"),
    "billing": ("VBRK", "VBRP"),
    "customer master": ("KNA1", "KNVV", "KNB1", "KNVK", "KNVP", "ADRC", "ADR6", "BUT000", "CVI_CUST_LINK"),
    "material master": ("MARA", "MAKT", "MARC", "MVKE", "MARD"),
    "organisation": ("T001", "TVKO", "TVTW", "TSPA", "T001W"),
}
_SAP_AREA = {t: a for a, ts in SAP_AREAS.items() for t in ts}


# ------------------------------------------------------------------ the graph -------------------------------------

def _graph(tables: list[str], rels: list[dict]) -> dict[str, dict[str, float]]:
    g: dict[str, dict[str, float]] = {t: {} for t in tables}
    for r in rels:
        a, b = r["source"], r["target"]
        if a == b or a not in g or b not in g:
            continue
        g[a][b] = g[a].get(b, 0.0) + r["weight"]
        g[b][a] = g[b].get(a, 0.0) + r["weight"]
    return g


def _components(nodes: list[str], g: dict[str, dict[str, float]]) -> list[list[str]]:
    inside, seen, out = set(nodes), set(), []
    for n in sorted(nodes):
        if n in seen:
            continue
        stack, comp = [n], []
        seen.add(n)
        while stack:
            x = stack.pop()
            comp.append(x)
            for y in sorted(g[x]):
                if y in inside and y not in seen:
                    seen.add(y)
                    stack.append(y)
        out.append(sorted(comp))
    return out


def _local_moving(g: dict[str, dict[str, float]], comm: dict[str, str], gamma: float) -> bool:
    """Move each node to the neighbouring community with the largest modularity gain, in name order, until stable."""
    deg = {n: sum(w.values()) for n, w in g.items()}
    m2 = sum(deg.values())
    if m2 == 0:
        return False
    tot: dict[str, float] = {}
    for n, c in comm.items():
        tot[c] = tot.get(c, 0.0) + deg[n]
    moved_any, moved = False, True
    while moved:
        moved = False
        for n in sorted(g):
            here = comm[n]
            links: dict[str, float] = {}
            for y, w in g[n].items():
                if y != n:
                    links[comm[y]] = links.get(comm[y], 0.0) + w
            tot[here] -= deg[n]
            best, gain = here, links.get(here, 0.0) - gamma * tot[here] * deg[n] / m2
            for c in sorted(links):
                v = links[c] - gamma * tot[c] * deg[n] / m2
                if v > gain + 1e-12:
                    best, gain = c, v
            tot[best] = tot.get(best, 0.0) + deg[n]
            if best != here:
                comm[n], moved, moved_any = best, True, True
    return moved_any


def leiden(g: dict[str, dict[str, float]], gamma: float = RESOLUTION) -> list[list[str]]:
    """Communities of an undirected weighted graph, each connected; deterministic. A compact Leiden-style method:
    local moving, refinement into connected parts, aggregation, repeated on the aggregate graph until nothing moves."""
    members = {n: [n] for n in g}                         # aggregate node -> original nodes
    graph = {n: dict(w) for n, w in g.items()}
    while True:
        comm = {n: n for n in graph}
        if not _local_moving(graph, comm, gamma):
            break
        # refinement: a community whose members are not connected becomes one community per connected part
        groups: dict[str, list[str]] = {}
        for n, c in comm.items():
            groups.setdefault(c, []).append(n)
        parts = [p for c in sorted(groups) for p in _components(groups[c], graph)]
        if len(parts) == len(graph):
            break
        name = {n: min(x for m in p for x in members[m]) for p in parts for n in p}
        new: dict[str, dict[str, float]] = {name[p[0]]: {} for p in parts}
        for a, ws in graph.items():
            for b, w in ws.items():
                new[name[a]][name[b]] = new[name[a]].get(name[b], 0.0) + w   # inside a part: a self-loop, so degrees keep it
        members = {name[p[0]]: sorted(x for m in p for x in members[m]) for p in parts}
        graph = new
    out = [sorted(ms) for ms in members.values()]
    return sorted(out, key=lambda c: (-len(c), c[0].lower()))


# ------------------------------------------------------------------ names -----------------------------------------

def _sap_base(table: str) -> str | None:
    u = table.upper()
    for t in sorted(_SAP_AREA, key=len, reverse=True):
        if u == t or u.endswith("_" + t):
            return t
    return None


def _words(name: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1_\2", name).lower()) if w]


def _common_prefix(names: list[str], skip: int) -> list[str]:
    ws = [_words(n)[skip:] for n in names]
    out = []
    for parts in zip(*ws):
        if len(set(parts)) != 1:
            break
        out.append(parts[0])
    return out


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "domain"


def _name(tables: list[str], g: dict[str, dict[str, float]], into: dict[str, float], schema_prefix: int) -> tuple[str, str]:
    areas: dict[str, int] = {}
    for t in tables:
        a = _SAP_AREA.get(_sap_base(t) or "")
        if a:
            areas[a] = areas.get(a, 0) + 1
    if areas and sum(areas.values()) * 2 > len(tables):
        top = sorted(areas, key=lambda a: (-areas[a], list(SAP_AREAS).index(a)))
        if {"sales documents", "deliveries", "billing"} <= set(areas):
            name = "order-to-cash"
        else:
            name = top[0] if len(top) == 1 or areas[top[1]] * 2 < areas[top[0]] else f"{top[0]} and {top[1]}"
        return name, (f"SAP order-to-cash{' (sales documents, deliveries and billing together)' if name == 'order-to-cash' else ''}: {', '.join(f'{areas[a]} table(s) of {a}' for a in top)} (public SAP table roles; "
                      "the SAP pack recognised them)")
    pre = _common_prefix(tables, schema_prefix)
    if pre and len("_".join(pre)) >= 3:
        return "_".join(pre), f"the tables share the name prefix {'_'.join(pre)!r}"
    hub = sorted(tables, key=lambda t: (-into.get(t, 0.0), -sum(g[t].values()), t.lower()))[0]
    return hub, f"{hub} is the table the others in the domain point at most"


# ------------------------------------------------------------------ the proposal ----------------------------------

def _weight(rule: str, kind: str | None = None, check: dict | None = None) -> float:
    w = EXTENDED_WEIGHTS.get(kind, 0.4) if kind else WEIGHTS.get(rule, 0.5)
    if check:
        if check.get("verdict", "").startswith("holds"):
            return 1.0
        if check.get("orphans"):
            return w / 2
    return w


def propose(tables: list[dict], relationships: list[dict], validation: dict | None = None,
            gamma: float = RESOLUTION) -> dict:
    """Domains from plain data, the form both the plan and /check's result give:
    tables [{"name", "key": [cols]}], relationships [{"source", "source_cols", "target", "target_cols", "rule", "kind"?}],
    validation: validate_plan's output (optional). Returns {"domains", "unassigned", "interfaces", "method"}."""
    checks = {(r["source"], tuple(c.lower() for c in r["columns"]), r["target"]): r for r in (validation or {}).get("relationships", [])}
    keyed = sorted((t["name"] for t in tables if t.get("key")), key=str.lower)
    keyless = sorted((t["name"] for t in tables if not t.get("key")), key=str.lower)
    rels = []
    for r in relationships:
        chk = checks.get((r["source"], tuple(c.lower() for c in r["source_cols"]), r["target"]))
        rels.append({**r, "weight": round(_weight(r.get("rule", ""), r.get("kind"), chk), 3),
                     **({"check": chk["verdict"]} if chk else {})})
    # aggregates first (DDD, and Service Cutter's identity and lifecycle): a table whose key holds its reference to a
    # parent (order_items -> orders, VBAP -> VBAK, MAKT -> MARA) lives and dies with that parent, so it is never split from it
    key_of = {t["name"]: [c.lower() for c in t.get("key") or []] for t in tables}
    parent: dict[str, tuple[str, str]] = {}
    for r in sorted(rels, key=lambda r: (r["source"].lower(), r["target"].lower())):
        k, cols = key_of.get(r["source"], []), [c.lower() for c in r["source_cols"]]
        if (not r.get("extended") and r["source"] != r["target"] and r["target"] in key_of and key_of[r["target"]]
                and set(cols) <= set(k) and len(k) > len(cols) and r["source"] not in parent):
            parent[r["source"]] = (r["target"], f"part of {r['target']}'s aggregate: its key {'+'.join(key_of[r['source']])} holds the reference {'+'.join(r['source_cols'])}")

    def root(t: str, seen=()) -> str:
        return t if t not in parent or t in seen else root(parent[t][0], seen + (t,))
    agg = {t: root(t) for t in keyed}
    ag_rels = [{**r, "source": agg.get(r["source"], r["source"]), "target": agg.get(r["target"], r["target"])} for r in rels]
    g0 = _graph(sorted(set(agg.values()), key=str.lower), ag_rels)
    g = _graph(keyed, rels)
    into: dict[str, float] = {}
    for r in rels:
        if r["source"] in g and r["target"] in g:
            into[r["target"]] = into.get(r["target"], 0.0) + r["weight"]
    all_names = [t["name"] for t in tables]
    first = {(_words(n) or [""])[0] for n in all_names}
    schema_prefix = 1 if len(first) == 1 and len(all_names) > 1 and len(next(iter(first))) <= 4 else 0  # sap_, a system prefix

    domains, unassigned, where = [], [], {}
    found = [sorted((t for t in keyed if agg[t] in c), key=str.lower) for c in leiden(g0, gamma)]
    for comm in sorted(found, key=lambda c: (-len(c), c[0].lower())):
        if len(comm) < MIN_TABLES:
            for t in comm:
                unassigned.append({"table": t, "reason": "linked to no other table with a key" if not g[t]
                                   else f"a group of {len(comm)} table(s), below the {MIN_TABLES} a domain needs"})
            continue
        name, why = _name(comm, g, into, schema_prefix)
        domains.append({"name": name, "slug": _slug(name), "name_reason": why, "tables": comm})
    seen: dict[str, int] = {}
    for d in domains:                                     # two domains with one name get a number, in order
        seen[d["slug"]] = seen.get(d["slug"], 0) + 1
        if seen[d["slug"]] > 1:
            d["name"] += f" {seen[d['slug']]}"; d["slug"] += f"_{seen[d['slug']]}"
    for d in domains:
        for t in d["tables"]:
            where[t] = d["slug"]
    for d in domains:
        d["reasons"] = {}
        for t in d["tables"]:
            inner = sorted((r for r in rels if (r["source"] == t and where.get(r["target"]) == d["slug"] and r["target"] != t)
                            or (r["target"] == t and where.get(r["source"]) == d["slug"] and r["source"] != t)),
                           key=lambda r: (-r["weight"], r["source"].lower(), r["target"].lower()))
            r = inner[0]
            how = f"{r['source']}.{'+'.join(r['source_cols'])} → {r['target']} ({r.get('rule') or r.get('kind')}, weight {r['weight']})"
            d["reasons"][t] = (parent[t][1] + "; " if t in parent else "") + f"{len(inner)} relationship(s) inside the domain; strongest: {how}"
    for t in keyless:
        points = sorted({where[r["target"]] for r in rels if r["source"] == t and r["target"] in where})
        unassigned.append({"table": t, "reason": "no key: a contract cannot promise its rows are unique"
                           + (f"; it points at {', '.join(points)}, place it there by hand if it belongs" if points else "")})
    interfaces = []
    for r in rels:
        a, b = where.get(r["source"]), where.get(r["target"])
        if a and b and a != b:
            interfaces.append({"consumer": a, "provider": b, "source": r["source"], "source_cols": r["source_cols"],
                               "target": r["target"], "target_cols": r["target_cols"], "rule": r.get("rule") or r.get("kind"),
                               "weight": r["weight"]})
    interfaces.sort(key=lambda i: (i["consumer"], i["provider"], i["source"].lower(), i["target"].lower()))
    return {"domains": domains, "unassigned": sorted(unassigned, key=lambda u: u["table"].lower()), "interfaces": interfaces,
            "method": {"algorithm": "Leiden-style community detection (local moving, connected refinement, aggregation), "
                                    "deterministic: name order, no random seed",
                       "resolution": gamma, "min_tables": MIN_TABLES, "weights": {**WEIGHTS, **{f"extended {k}": v for k, v in EXTENDED_WEIGHTS.items()}},
                       "validated": validation is not None}}


def _plan_data(p) -> tuple[list[dict], list[dict]]:
    tables = [{"name": t.name, "key": p.keys.get(t.name, ([], ""))[0]} for t in p.schema]
    rels = [{"source": r.source, "source_cols": r.source_cols, "target": r.target, "target_cols": r.target_cols, "rule": r.rule}
            for r in p.relationships]
    rels += [{"source": r.source, "source_cols": r.source_cols, "target": r.target, "target_cols": r.target_cols,
              "rule": r.rule, "kind": r.kind, "extended": True} for r in getattr(p, "extended", [])]
    return tables, rels


def propose_plan(p, validation: dict | None = None, gamma: float = RESOLUTION) -> dict:
    """Domains of a plan (infer.plan)."""
    tables, rels = _plan_data(p)
    return propose(tables, rels, validation, gamma)


def propose_from_check(result: dict, gamma: float = RESOLUTION) -> dict:
    """Domains from browser_check.analyze's result, for /check's engine in the browser (its tables and relationships)."""
    return propose(result.get("tables", []), result.get("relationships", []), None, gamma)


# ------------------------------------------------------------------ ODCS contracts --------------------------------

def _logical(data_type: str) -> str:
    t = (data_type or "").lower()
    if any(w in t for w in ("int", "long", "short", "byte")):
        return "integer"
    if any(w in t for w in ("decimal", "numeric", "float", "double", "real", "money")):
        return "number"
    if "bool" in t or t == "bit":
        return "boolean"
    if "timestamp" in t or "datetime" in t:
        return "timestamp"
    if t == "date":
        return "date"
    return "string"


def _q(v) -> str:
    """A YAML scalar: plain when safe, otherwise double-quoted."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.\-/ ]*", s) and s.strip() == s and s.lower() not in ("true", "false", "null", "yes", "no", "on", "off", "y", "n"):
        return s
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _yaml(v, indent: int = 0) -> list[str]:
    pad = "  " * indent
    out: list[str] = []
    if isinstance(v, dict):
        for k, x in v.items():
            if isinstance(x, (dict, list)) and x:
                out.append(f"{pad}{k}:")
                out += _yaml(x, indent + 1)
            else:
                out.append(f"{pad}{k}: {_q(x) if not isinstance(x, (dict, list)) else ('{}' if isinstance(x, dict) else '[]')}")
    else:
        for x in v:
            if isinstance(x, dict):
                lines = _yaml(x, indent + 1)
                out.append(f"{pad}- " + lines[0].lstrip())
                out += lines[1:]
            else:
                out.append(f"{pad}- {_q(x)}")
    return out


def _quote(name: str) -> str:
    return "[" + name.replace("]", "]]") + "]"


def contract(p, domain: dict, interfaces: list[dict], schema: str, source: str = "", validation: dict | None = None) -> str:
    """One domain as an ODCS v3.2.0 data contract in YAML: each table with its columns and key, uniqueness of the key
    (duplicateValues mustBe 0), relationships as foreignKey, and an SQL rule counting orphans per relationship
    (mustBe 0). Freshness is left as a commented slaProperties block: the latency is the data owner's to agree."""
    checks_k = {k["table"]: k for k in (validation or {}).get("keys", [])}
    checks_r = {(r["source"], tuple(c.lower() for c in r["columns"]), r["target"]): r for r in (validation or {}).get("relationships", [])}
    mine = set(domain["tables"])
    rels = [r for r in list(p.relationships) if r.source in mine]
    objects, dated = [], []
    for name in domain["tables"]:
        t = p.schema[name]
        key = p.keys.get(name, ([], ""))
        props = []
        for c in t.columns:
            if c.name not in t.column_names:
                continue
            prop = {"name": c.name, "physicalName": c.name, "logicalType": _logical(c.data_type), "physicalType": c.data_type}
            if c.name in key[0]:
                prop.update({"primaryKey": True, "primaryKeyPosition": key[0].index(c.name) + 1, "required": True})
            props.append(prop)
            if prop["logicalType"] in ("date", "timestamp"):
                dated.append(f"{name}.{c.name}")
        obj = {"name": name, "physicalName": f"{schema}.{name}", "physicalType": "table", "logicalType": "object",
               "description": domain["reasons"].get(name, "") + f"; key by rule {key[1]}", "properties": props}
        quality = []
        if key[0]:
            rule = {"name": f"{name}_key_unique", "description": f"Key {'+'.join(key[0])} ({key[1]}) has no duplicates",
                    "dimension": "uniqueness", "type": "library", "metric": "duplicateValues", "mustBe": 0,
                    "arguments": {"properties": list(key[0])}}
            k = checks_k.get(name)
            if k:
                rule["customProperties"] = [{"property": "lastCheck", "value": f"validate_plan: {k['verdict']}"}]
            quality.append(rule)
        own = [r for r in rels if r.source == name]
        for r in own:
            on = " AND ".join(f"t.{_quote(b)} = s.{_quote(a)}" for a, b in zip(r.source_cols, r.target_cols))
            some = " OR ".join(f"s.{_quote(a)} IS NOT NULL" for a in r.source_cols)
            rule = {"name": f"{name}_{'_'.join(r.source_cols)}_no_orphans".lower(),
                    "description": f"Every {name}.{'+'.join(r.source_cols)} with a value finds a row in {r.target} ({r.rule})",
                    "dimension": "consistency", "type": "sql",
                    "query": (f"SELECT COUNT(*) FROM {_quote(schema)}.{_quote(name)} s WHERE ({some}) AND NOT EXISTS "
                              f"(SELECT 1 FROM {_quote(schema)}.{_quote(r.target)} t WHERE {on})"),
                    "mustBe": 0}
            k = checks_r.get((r.source, tuple(c.lower() for c in r.source_cols), r.target))
            if k:
                rule["customProperties"] = [{"property": "lastCheck", "value": f"validate_plan: {k['verdict']}"}]
            quality.append(rule)
        if quality:
            obj["quality"] = quality
        if own:
            obj["relationships"] = [{"type": "foreignKey",
                                     "from": f"{name}.{r.source_cols[0]}" if len(r.source_cols) == 1 else [f"{name}.{c}" for c in r.source_cols],
                                     "to": f"{r.target}.{r.target_cols[0]}" if len(r.target_cols) == 1 else [f"{r.target}.{c}" for c in r.target_cols]}
                                    for r in own]
        objects.append(obj)
    provides = sorted({i["consumer"] for i in interfaces if i["provider"] == domain["slug"]})
    consumes = sorted({i["provider"] for i in interfaces if i["consumer"] == domain["slug"]})
    desc = {"purpose": f"Proposed data product for the {domain['name']} domain of {schema}"
                       + (f" in {source}" if source else "") + f": {domain['name_reason']}.",
            "usage": ("Draft written by Krusgraph from the plan's keys and relationships; review before agreeing it. "
                      + (f"Provides keys to: {', '.join(provides)}. " if provides else "")
                      + (f"Consumes keys of: {', '.join(consumes)}." if consumes else "")).strip()}
    doc = {"apiVersion": ODCS_VERSION, "kind": "DataContract", "id": f"krusgraph-{_slug(source or schema)}-{_slug(schema)}-{domain['slug']}",
           "name": domain["name"], "version": "0.1.0", "status": "draft", "domain": domain["name"],
           "dataProduct": domain["slug"], "description": desc, "schema": objects}
    lines = [f"# ODCS {ODCS_VERSION} draft from Krusgraph's plan: review before use. Nothing was created in Fabric."]
    lines += _yaml(doc)
    if dated:
        lines += ["# Freshness: agree a latency with the data owner, then uncomment (no value is assumed here).",
                  "# slaProperties:", "#   - property: latency", "#     value: <agree>", "#     unit: d",
                  f"#     element: {dated[0]}"]
    return "\n".join(lines) + "\n"


def draft(p, schema: str, source: str = "", validation: dict | None = None, gamma: float = RESOLUTION) -> dict:
    """The proposal plus one ODCS contract per domain: {"domains", "unassigned", "interfaces", "method", "contracts"}."""
    out = propose_plan(p, validation, gamma)
    out["contracts"] = {d["slug"]: contract(p, d, out["interfaces"], schema, source, validation) for d in out["domains"]}
    return out
