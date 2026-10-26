"""compare_semantic_model: an existing Power BI semantic model against the plan. Read-only.

The model is read from its TMDL definition (`definition/tables/*.tmdl`, `definition/relationships.tmdl`) into one shape:
tables with their source table, columns and measures; relationships with both ends, cardinality, cross-filter
direction and whether they are active. The files come from one of two places:

- Fabric's Get Semantic Model Definition (format TMDL). It is the documented REST path that returns a model's
  relationships, and it needs the delegated scope SemanticModel.ReadWrite.All or Item.ReadWrite.All and read and
  write permission on the model (microsoft/fabric-rest-api-specs a96c37a, semanticModel/swagger.json,
  Items_GetSemanticModelDefinition). The read-only alternative was checked and rejected: the Power BI REST
  "Datasets - Execute Queries In Group" takes Dataset.Read.All with Read and Build permission, but its reference says
  "Only DAX queries are supported at this time. MDX, INFO functions and DMV queries are not supported"
  (microsoft/PowerBI-CSharp sdk/swaggers/swagger.json, release 5.1.0), and the INFO.VIEW functions are what would read
  the relationships. The XMLA endpoint shows Build users no model metadata either (fabric-docs
  enterprise/powerbi/service-premium-connect-tools.md). docs/SCOPES.md keeps the comparison.
- The same files from the user: a PBIP folder or the workspace's Git repository holds them, and reading them needs no
  permission at all, so the tool takes them as input (`tmdl`).

`compare(plan, model, ...)` then lists what differs, each with the rule (K0-K5, R0-R4) or the validation result behind
it. Nothing here talks to Fabric.
"""
from __future__ import annotations

import re

from .infer import Plan, Relationship, RULES, _content_words, _norm, _singulars
from . import semantic_model as _sm

# ------------------------------------------------------------------ the model, from TMDL -----------------------------

_OBJ = re.compile(r"^(\t*)(table|column|measure|partition|relationship|calculationGroup|hierarchy|annotation|ref|role|"
                  r"perspective|culture|expression|calculationItem|level|variation|changedProperty|extendedProperty)\b(.*)$")
_PROP = re.compile(r"^(\t*)([A-Za-z][A-Za-z0-9]*)\s*(?::\s*(.*))?$")


def _name_and_rest(text: str) -> tuple[str, str]:
    """`'Order Details' = entity` -> ("Order Details", "= entity"); `orders` -> ("orders", "")."""
    text = text.strip()
    if text.startswith("'"):
        i, out = 1, []
        while i < len(text):
            if text[i] == "'" and i + 1 < len(text) and text[i + 1] == "'":
                out.append("'")
                i += 2
                continue
            if text[i] == "'":
                return "".join(out), text[i + 1:].strip()
            out.append(text[i])
            i += 1
        return "".join(out), ""
    m = re.match(r"^([^=\s]+)\s*(.*)$", text)
    return (m.group(1), m.group(2).strip()) if m else (text, "")


def split_column_ref(ref: str) -> tuple[str, str]:
    """`orders.customer_id`, `'Order Details'.'Unit Price'`, `Sales.'Order Date'` -> (table, column)."""
    ref = ref.strip()
    if ref.startswith("'"):
        table, rest = _name_and_rest(ref)
    else:
        table, _, rest = ref.partition(".")
        rest = "." + rest
    rest = rest.strip()[1:].strip() if rest.strip().startswith(".") else rest.strip()
    column = _name_and_rest(rest)[0] if rest.startswith("'") else rest
    return table.strip(), column.strip()


def _m_source_table(text: str) -> tuple[str | None, str | None]:
    """The table an Import/DirectQuery partition's Power Query reads, when it says so plainly:
    `Schema="shop",Item="orders"` or `[Name="orders"]`. Anything else is left unmapped rather than guessed."""
    item = re.search(r'Item\s*=\s*"([^"]+)"', text)
    schema = re.search(r'Schema\s*=\s*"([^"]+)"', text)
    if item:
        return item.group(1), schema.group(1) if schema else None
    name = re.search(r'\[Name\s*=\s*"([^"]+)"', text)
    return (name.group(1), None) if name else (None, None)


def from_tmdl(parts: dict[str, str]) -> dict:
    """{path: text} of a TMDL definition -> the model shape. Unknown lines are skipped; nothing is executed."""
    model: dict = {"tables": {}, "relationships": [], "read_with": "TMDL definition files"}
    for path in sorted(parts):
        if not path.endswith(".tmdl"):
            continue
        table = None
        current: dict | None = None            # the object whose properties follow
        kind = None
        m_text: list[str] | None = None
        skip_below: int | None = None           # inside an annotation or extendedProperty value: not part of anything we read
        expr_open = False                       # a measure's expression may continue on the lines below it
        for raw in parts[path].splitlines():
            if not raw.strip() or raw.strip().startswith("///"):
                continue
            o = _OBJ.match(raw)
            depth = len(raw) - len(raw.lstrip("\t"))
            if skip_below is not None:
                if depth > skip_below:
                    continue
                skip_below = None
            if o and depth >= 1 and o.group(2) in ("annotation", "changedProperty", "extendedProperty"):
                skip_below = depth
                continue
            if m_text is not None:
                if depth >= 2:                                       # the partition's mode, source and Power Query lines
                    m_text.append(raw)
                    if depth == 2 and raw.strip().startswith("mode:"):
                        table["mode"] = raw.split(":", 1)[1].strip()
                    continue
                src, sch = _m_source_table("\n".join(m_text))
                if table is not None and src and not table.get("source"):
                    table["source"], table["source_schema"] = src, sch
                m_text = None
            if o and depth == 0 and o.group(2) == "table":
                name, _ = _name_and_rest(o.group(3))
                table = model["tables"].setdefault(name, {"name": name, "source": None, "source_schema": None, "kind": None,
                                                          "columns": {}, "measures": {}})
                current, kind = table, "table"
                continue
            if o and depth == 0 and o.group(2) == "relationship":
                current = {"name": o.group(3).strip(), "active": True, "cross_filter": "oneDirection",
                           "from_cardinality": "many", "to_cardinality": "one"}
                model["relationships"].append(current)
                kind = "relationship"
                continue
            if o and depth == 1 and table is not None and o.group(2) in ("column", "measure", "partition"):
                name, rest = _name_and_rest(o.group(3))
                if o.group(2) == "column":
                    current = table["columns"].setdefault(name, {"name": name, "source_column": None, "data_type": None,
                                                                 "is_key": False, "summarize_by": None, "calculated": rest.startswith("=")})
                elif o.group(2) == "measure":
                    current = {"name": name, "expression": (rest[1:].strip() if rest.startswith("=") else rest).strip("`").strip()}
                    table["measures"][name] = current
                    expr_open = True
                else:
                    mode = rest[1:].strip() if rest.startswith("=") else ""
                    table["kind"] = mode or table["kind"]
                    current = table
                    if mode == "m":
                        m_text = []
                kind = o.group(2)
                continue
            if o and depth <= 1:
                current, kind = None, None
                continue
            p = _PROP.match(raw)
            if kind == "measure" and current is not None and expr_open:
                if depth >= 3:                                       # the expression's next line (one level below its properties)
                    current["expression"] = (current["expression"] + " " + raw.strip().strip("`")).strip()
                    continue
                expr_open = False                                    # formatString, lineageTag, kpi: the expression is over
            if kind == "measure" and depth >= 3:
                continue
            if not p or current is None:
                continue
            prop, value = p.group(2), (p.group(3) or "").strip()
            if kind == "relationship":
                if prop == "fromColumn":
                    current["from_table"], current["from_column"] = split_column_ref(value)
                elif prop == "toColumn":
                    current["to_table"], current["to_column"] = split_column_ref(value)
                elif prop == "isActive":
                    current["active"] = value.lower() != "false"
                elif prop == "crossFilteringBehavior":
                    current["cross_filter"] = value
                elif prop in ("fromCardinality", "toCardinality"):
                    current["from_cardinality" if prop == "fromCardinality" else "to_cardinality"] = value.lower()
            elif kind == "column":
                if prop == "sourceColumn":
                    current["source_column"] = value.strip("[]")
                elif prop == "dataType":
                    current["data_type"] = value
                elif prop == "isKey":
                    current["is_key"] = value.lower() != "false"
                elif prop == "summarizeBy":
                    current["summarize_by"] = value
            elif kind == "partition" and table is not None:
                if prop == "entityName":
                    table["source"] = value
                elif prop == "schemaName":
                    table["source_schema"] = value
                elif prop == "mode":
                    table["mode"] = value
        if m_text is not None and table is not None:
            src, sch = _m_source_table("\n".join(m_text))
            if src and not table.get("source"):
                table["source"], table["source_schema"] = src, sch
    model["relationships"] = [r for r in model["relationships"] if r.get("from_table") and r.get("to_table")]
    return model


# ------------------------------------------------------------------ the comparison -----------------------------------

def _table_forms(name: str) -> set[str]:
    words = _content_words(name)
    base = "_".join(words) if words else name
    return {_norm(x) for x in _singulars(base)} | {_norm(base)}


def map_tables(plan: Plan, model: dict) -> dict[str, str | None]:
    """model table -> plan table: the partition's source table first, then the same name, then the same name without
    a kind prefix (dim_, fact_) and in singular or plural. A table no rule maps (a calculated table, another source)
    maps to None."""
    names = {t.name.lower(): t.name for t in plan.schema}
    forms: dict[str, list[str]] = {}
    for t in plan.schema:
        for f in _table_forms(t.name):
            forms.setdefault(f, []).append(t.name)
    out: dict[str, str | None] = {}
    taken: set[str] = set()
    for name, t in sorted(model["tables"].items()):
        hit = None
        if t.get("source") and str(t["source"]).lower() in names:
            hit = names[str(t["source"]).lower()]
        elif name.lower() in names:
            hit = names[name.lower()]
        out[name] = hit
        if hit:
            taken.add(hit)
    for name in sorted(n for n, v in out.items() if v is None):
        if model["tables"][name].get("kind") in ("calculated", "Calculated"):
            continue
        hits = sorted({p for f in _table_forms(name) for p in forms.get(f, []) if p not in taken})
        if len(hits) == 1:
            out[name] = hits[0]
            taken.add(hits[0])
    return out


def _column(plan: Plan, table: str, model_table: dict, column: str) -> str | None:
    c = model_table["columns"].get(column) or {}
    src = c.get("source_column") or column
    t = plan.schema[table]
    return next((x for x in t.column_names if x.lower() == str(src).lower()), None)


def _ref(r: Relationship) -> str:
    return f"{r.source}.{'+'.join(r.source_cols)} -> {r.target}.{'+'.join(r.target_cols)}"


def _rule(rule: str) -> str:
    return f"{rule}: {RULES.get(rule, rule).split(';')[0]}"


def _mrel(mr: dict) -> dict:
    return {"from": f"{mr['from_table']}.{mr['from_column']}", "to": f"{mr['to_table']}.{mr['to_column']}",
            "cardinality": f"{mr['from_cardinality']}-to-{mr['to_cardinality']}", "cross_filter": mr["cross_filter"], "active": mr["active"]}


def _confirmed(source: str, col: str, target: str, tcol: str) -> dict:
    return {"source": source, "source_cols": [col], "target": target, "target_cols": [tcol]}


def compare(plan: Plan, model: dict, validation: dict | None = None, data_checks: dict | None = None) -> dict:
    """What differs between the model and the plan. `validation` is evidence.validate's answer for the plan;
    `data_checks` maps a model relationship's "from -> to" text to {"one_side": key verdict dict, "orphans": relationship
    verdict dict} counted for relationships the plan does not have."""
    tmap = map_tables(plan, model)
    single = [r for r in plan.relationships if len(r.source_cols) == 1 and len(r.target_cols) == 1
              and len(plan.keys.get(r.target, ([], ""))[0]) == 1]
    composite = [r for r in plan.relationships if r not in single]
    active, inactive = _sm.active_relationships(plan, single, validation)
    why_inactive = {id(r): w for r, w in inactive}
    unique = {k["table"]: k for k in (validation or {}).get("keys", [])}
    holds = {(x["source"], tuple(c.lower() for c in x["columns"]), x["target"]): x for x in (validation or {}).get("relationships", [])}
    ambiguous = {(a["table"], a["column"].lower()): a for a in plan.ambiguous}
    by_source_col = {}
    for r in single:
        by_source_col.setdefault((r.source, r.source_cols[0].lower()), []).append(r)

    out = {"missing_in_model": [], "contradicted": [], "cardinality_differences": [], "direction_differences": [],
           "active_differences": [], "not_in_plan": [], "outside_the_plan": [], "agrees": []}
    matched: set[int] = set()
    for mr in model["relationships"]:
        ft, tt = tmap.get(mr["from_table"]), tmap.get(mr["to_table"])
        if not ft or not tt:
            out["outside_the_plan"].append({**_mrel(mr), "why": "a table of this relationship is not a table of the source "
                                            f"({', '.join(n for n, v in ((mr['from_table'], ft), (mr['to_table'], tt)) if not v)}: "
                                            "calculated, from another source, or renamed beyond recognition)"})
            continue
        fc = _column(plan, ft, model["tables"][mr["from_table"]], mr["from_column"])
        tc = _column(plan, tt, model["tables"][mr["to_table"]], mr["to_column"])
        if not fc or not tc:
            out["contradicted"].append({**_mrel(mr), "by": "schema", "why": "a column of this relationship is no longer in the source table "
                                        f"({ft}.{mr['from_column'] if not fc else ''}{' / ' if not fc and not tc else ''}{tt + '.' + mr['to_column'] if not tc else ''})".replace("(.", "(")})
            continue
        # which end is the many side in the model
        fcard, tcard = mr["from_cardinality"], mr["to_cardinality"]
        many, one = ((ft, fc), (tt, tc)) if (fcard, tcard) != ("one", "many") else ((tt, tc), (ft, fc))
        p = next((r for r in single if {(r.source, r.source_cols[0].lower()), (r.target, r.target_cols[0].lower())}
                  == {(ft, fc.lower()), (tt, tc.lower())}), None)
        if p is not None:
            matched.add(id(p))
            diffs = 0
            base = {**_mrel(mr), "plan": _ref(p), "rule": _rule(p.rule)}
            if (fcard, tcard) in (("one", "one"), ("many", "many")):
                key = unique.get(p.target)
                evidence = f"; validate_plan: {p.target} key {key['verdict']}" if key else ""
                rel_check = holds.get(p.key)
                evidence += f"; {p.source}.{p.source_cols[0]}: {rel_check['verdict']}" if rel_check else ""
                out["cardinality_differences"].append({**base, "why": f"the model has {fcard}-to-{tcard}; the plan has many-to-one from "
                                                       f"{p.source} to {p.target}, because {p.target}.{p.target_cols[0]} is its key "
                                                       f"(rule {plan.keys.get(p.target, ([], '?'))[1]}){evidence}"})
                diffs += 1
            elif many[0] != p.source:
                out["cardinality_differences"].append({**base, "why": f"the model's one side is {one[0]}.{one[1]}; the plan points from "
                                                       f"{p.source} (many) to {p.target} (one), the key of {p.target} (rule "
                                                       f"{plan.keys.get(p.target, ([], '?'))[1]})"})
                diffs += 1
            if mr["cross_filter"] == "bothDirections":
                out["direction_differences"].append({**base, "why": "the model filters in both directions; the plan drafts a single direction "
                                                     f"({p.target} filters {p.source}), because both directions on a model with more than one path "
                                                     "make filters ambiguous (analyze_schema lists the cycles)"})
                diffs += 1
            plan_active = id(p) not in why_inactive
            if mr["active"] != plan_active:
                why = (why_inactive.get(id(p)) if not plan_active else
                       "it is on the plan's maximum spanning forest by certainty, so it is the one path between these tables")
                out["active_differences"].append({**base, "model_active": mr["active"], "plan_active": plan_active, "why": why})
                diffs += 1
            if not diffs:
                out["agrees"].append(f"{mr['from_table']}.{mr['from_column']} -> {mr['to_table']}.{mr['to_column']} ({p.rule})")
            continue
        # the model has a relationship the plan does not: does a rule or the data say otherwise?
        reasons = []
        for r in by_source_col.get((many[0], many[1].lower()), []):
            if (r.target, r.target_cols[0].lower()) != (one[0], one[1].lower()):
                reasons.append({"by": "rule", "why": f"the plan links {many[0]}.{many[1]} to {r.target}.{r.target_cols[0]} ({_rule(r.rule)})"})
        a = ambiguous.get((many[0], many[1].lower()))
        if a:
            reasons.append({"by": "rule", "why": f"the rules found {many[0]}.{many[1]} ambiguous ({', '.join(a.get('candidates', []))}); none was applied"})
        key = plan.keys.get(one[0])
        if key is None:
            reasons.append({"by": "rule", "why": f"{one[0]} has no key in the plan ({_rule('K3')})"})
        elif [c.lower() for c in key[0]] != [one[1].lower()]:
            reasons.append({"by": "rule", "why": f"the plan's key of {one[0]} is {'+'.join(key[0])} ({_rule(key[1])}), not {one[1]}"})
        checks = (data_checks or {}).get(f"{many[0]}.{many[1]} -> {one[0]}.{one[1]}") or {}
        one_side = checks.get("one_side")
        if one_side and not str(one_side.get("verdict", "")).startswith("unique"):
            reasons.append({"by": "data", "why": f"{one[0]}.{one[1]} is the one side but is {one_side['verdict']} (a one side must be unique)"})
        orphans = checks.get("orphans")
        if orphans and int(orphans.get("orphans") or 0) > 0:
            reasons.append({"by": "data", "why": f"{many[0]}.{many[1]}: {orphans['verdict']}"})
        sides = {"many_side": f"{many[0]}.{many[1]}", "one_side": f"{one[0]}.{one[1]}"}
        if reasons:
            out["contradicted"].append({**_mrel(mr), **sides, "by": " and ".join(sorted({r["by"] for r in reasons})),
                                        "why": "; ".join(r["why"] for r in reasons)})
        else:
            out["not_in_plan"].append({**_mrel(mr), **sides, "why": "no rule made this link and nothing contradicts it"
                                       + ("" if checks else " (pass check_data=true to count it against the rows)")
                                       + "; pass it as confirmed to make it part of the plan",
                                       "confirmed": _confirmed(many[0], many[1], one[0], one[1])})
    in_model = {v for v in tmap.values() if v}
    for r in single:
        if id(r) in matched:
            continue
        if r.source in in_model and r.target in in_model:
            check = holds.get(r.key)
            out["missing_in_model"].append({"plan": _ref(r), "rule": _rule(r.rule), "active_in_plan": id(r) not in why_inactive,
                                            **({"validate_plan": check["verdict"]} if check else {}),
                                            "add": f"fromColumn: {_model_name(tmap, r.source)}.{_col_name(model, tmap, plan, r.source, r.source_cols[0])}; "
                                                   f"toColumn: {_model_name(tmap, r.target)}.{_col_name(model, tmap, plan, r.target, r.target_cols[0])}"
                                                   + ("" if id(r) not in why_inactive else "; isActive: false (" + why_inactive[id(r)] + ")")})
    out["not_expressible_in_a_model"] = [{"plan": _ref(r), "rule": _rule(r.rule), "why": "tabular relationships use one column per side"}
                                         for r in composite if r.source in in_model and r.target in in_model]
    out["tables"] = _tables(plan, model, tmap)
    out["summarization"] = _summarization(plan, model, tmap)
    out["measures"] = _measures(plan, model, tmap)
    counts = {k: len(v) for k, v in out.items() if isinstance(v, list)}
    out["summary"] = (f"{len(model['tables'])} model tables ({len(in_model)} mapped to the source), {len(model['relationships'])} model relationships: "
                      f"{counts['agrees']} agree with the plan, {counts['missing_in_model']} missing in the model, {counts['contradicted']} contradicted, "
                      f"{counts['cardinality_differences']} with another cardinality, {counts['direction_differences']} filtering both ways, "
                      f"{counts['active_differences']} active where the plan says inactive or the reverse, {counts['not_in_plan']} not in the plan")
    return out


def _model_name(tmap: dict, plan_table: str) -> str:
    name = next((m for m, p in tmap.items() if p == plan_table), plan_table)
    return _sm.tmdl_name(name)


def _col_name(model: dict, tmap: dict, plan: Plan, plan_table: str, col: str) -> str:
    mname = next((m for m, p in tmap.items() if p == plan_table), None)
    if mname:
        for name, c in model["tables"][mname]["columns"].items():
            if str(c.get("source_column") or name).lower() == col.lower():
                return _sm.tmdl_name(name)
    return _sm.tmdl_name(col)


def _tables(plan: Plan, model: dict, tmap: dict) -> dict:
    mapped = {v for v in tmap.values() if v}
    gone = []
    for mname, p in sorted(tmap.items()):
        if not p:
            continue
        for cname, c in sorted(model["tables"][mname]["columns"].items()):
            if c.get("calculated") or cname.startswith("RowNumber"):
                continue
            if _column(plan, p, model["tables"][mname], cname) is None:
                gone.append({"model": f"{mname}.{cname}", "source_table": p,
                             "why": f"no column {c.get('source_column') or cname!r} in the source table {p} (renamed or removed?)"})
    return {"mapped": {m: p for m, p in sorted(tmap.items()) if p},
            "model_only": [m for m, p in sorted(tmap.items()) if not p],
            "not_in_model": sorted(t.name for t in plan.schema if t.name not in mapped),
            "columns_gone": gone}


def _summarization(plan: Plan, model: dict, tmap: dict) -> list[dict]:
    """Model columns summed by default that the plan's rule would not sum: keys, references, ids, codes, years."""
    refs = {(r.source, r.source_cols[0].lower()) for r in plan.relationships if len(r.source_cols) == 1}
    out = []
    for mname, p in sorted(tmap.items()):
        if not p:
            continue
        key = plan.keys.get(p, ([], ""))[0]
        for cname, c in sorted(model["tables"][mname]["columns"].items()):
            if str(c.get("summarize_by") or "").lower() != "sum":
                continue
            src = _column(plan, p, model["tables"][mname], cname)
            if src is None:
                continue
            is_ref = (p, src.lower()) in refs or src in key
            if is_ref or _sm._looks_like_id(src):
                why = ("it is the key of " + p if src in key else "it is a reference in the plan" if (p, src.lower()) in refs
                       else "its name ends in an id, code, number or year word")
                out.append({"column": f"{mname}.{cname}", "model": "summarizeBy: sum", "plan": "summarizeBy: none", "why": why})
    return out


_AGG = re.compile(r"\b(SUM|COUNTROWS)\s*\(\s*('(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_]*)\s*(?:\[([^\]]+)\])?\s*\)", re.I)


def _measures(plan: Plan, model: dict, tmap: dict) -> dict:
    """The model's measures, the suggested ones it lacks (semantic_model_draft's rule), and sums over ids or keys."""
    found = set()
    listed, questionable = [], []
    back = {m: p for m, p in tmap.items() if p}
    refs = {(r.source, r.source_cols[0].lower()) for r in plan.relationships if len(r.source_cols) == 1}
    for mname, t in sorted(model["tables"].items()):
        for name, m in sorted(t["measures"].items()):
            expr = str(m.get("expression") or "")
            listed.append({"table": mname, "name": name, "expression": expr[:200] + ("…" if len(expr) > 200 else "")})
            for fn, tname, cname in _AGG.findall(expr):
                tname = tname.strip("'").replace("''", "'")
                p = back.get(tname)
                if not p:
                    continue
                col = _column(plan, p, model["tables"][tname], cname) if cname else None
                found.add((fn.upper(), p, (col or "").lower()))
                if fn.upper() == "SUM" and col and ((p, col.lower()) in refs or col in plan.keys.get(p, ([], ""))[0] or _sm._looks_like_id(col)):
                    questionable.append({"measure": f"{mname}[{name}]", "expression": expr[:200],
                                         "why": f"it sums {p}.{col}, which identifies rows rather than measuring them (key, reference, id, code or year)"})
    from . import graphs
    role_of = {t: r["role"] for t, r in graphs.analyze(plan)["roles"].items()}
    chosen = [t for t in plan.schema if t.name in back.values()]
    ref_cols = {(r.source, r.source_cols[0].lower()) for r in plan.relationships if len(r.source_cols) == 1 and len(r.target_cols) == 1}
    missing = []
    model_of = {p: m for m, p in back.items()}
    for s in _sm.suggested_measures(plan, chosen, role_of, ref_cols):
        fn = "SUM" if s.get("column") else "COUNTROWS"
        col = s.get("column") or ""
        if (fn, s["table"], col.lower()) in found:
            continue
        mt = model_of[s["table"]]                                   # written in the model's own names
        mcol = next((n for n, c in model["tables"][mt]["columns"].items() if str(c.get("source_column") or n).lower() == col.lower()), col)
        expr = f"COUNTROWS({_sm._dax_table(mt)})" if fn == "COUNTROWS" else f"SUM({_sm._dax_table(mt)}[{_sm._dax_column(mcol)}])"
        missing.append({"table": mt, "suggested": s["name"].replace(s["table"], mt), "expression": expr, "why": s["why"]})
    return {"count": len(listed), "in_model": listed[:100], "suggested_missing": missing, "questionable": questionable}


def to_check(result: dict) -> list[tuple[str, str, str, str]]:
    """(many table, column, one table, column) for every model relationship the plan does not have: the ones whose
    one side (uniqueness) and many side (orphans) are worth counting against the rows."""
    out = []
    for entry in result.get("contradicted", []) + result.get("not_in_plan", []):
        if "many_side" in entry:
            mt, mc = entry["many_side"].split(".", 1)
            ot, oc = entry["one_side"].split(".", 1)
            out.append((mt, mc, ot, oc))
    return out
