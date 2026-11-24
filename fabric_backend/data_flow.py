"""The data flow, drawn (round n174). The founder, 8 November 2026, 23:40: "when you create a data flow you want to see it
visually: bronze to gold, which silvers are joined"; 23:50: "click the boxes and you see the code unfolded, otherwise
not".

The Krusgraph Model editor (workload/) draws this left to right: the source tables (bronze) -> the silver tables the
silver notebook writes (what each one cleans: one row per key, the references it checks, as the dry run lists them) ->
the gold views (which silver tables each joins, on which columns, with the rule) -> the items built on the source
(semantic model, API for GraphQL, report, ontology, data agent). The pipeline's three steps sit under the columns they
run.

Every node comes from the engine's own drafts, made with the same calls the creating tools make (silver.spec,
gold.spec, pipeline.pipeline_content), and each node's code is exactly what the dry run sends: a silver node's notebook
cell (silver._table_cell, the cell notebook_source writes), a gold node's CREATE MATERIALIZED LAKE VIEW (gold.create_sql,
the SQL of the dry run's `views`), a pipeline step's activity (the dry run's pipeline-content.json), a semantic model's
relationships and measures (an excerpt of the dry run's TMDL). tests/test_workload_build.py compares them on the shop
schema. `built` says whether this build creates the node: what is not part of it is drawn dashed.

The model, the API and the ontology read the source tables (bronze) directly: that is what their definitions bind to,
so the flow draws them from the source, not from the gold views. W1/W4: the data agent reads one layer first (the silver
tables by default, or the gold views), as the recorded build says; it is drawn from that layer, and from the source only
while the layer is not filled and only when the source is in the same lakehouse. DPM1: a semantic model built in
the same run as the gold views reads them (semantic_model.draft_on_gold): its card carries `on_gold` (the gold views it
reads), the flow draws a line from each of them to the model, and the column is titled "Built on gold".
"""
from __future__ import annotations

import json

from . import gold as _gold, pipeline as _pipeline, silver as _silver


def _listed(xs: list[str]) -> str:
    xs = [str(x) for x in xs]
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]

COLUMNS = (("bronze", "Bronze: the source tables"), ("silver", "Silver: cleaned tables"), ("gold", "Gold: views"),
           ("built", "Built on the source"))
ON_SOURCE = ("semantic_model", "graphql", "ontology", "data_agent")
FLOW_KINDS = ("silver_notebook", "gold_views", "pipeline")


def _dot(target) -> str:
    return ".".join(x for x in target if x)


def built_title(items: list[dict]) -> str:
    """W4: the last column's title, from what its items read: "Built on gold" (DPM1), "Built on silver", "Built on the source,
    silver and gold", "Built on the source" (also for no item). A report on a model reads
    through the model, so it does not count."""
    read = set()
    for it in items:
        if it.get("on_model"):
            continue
        if it.get("on_gold"):
            read.add("gold")
        elif it.get("layer_first"):
            read.add(it["layer_first"] if it["layer_first"] in ("silver", "gold") else "silver")
        else:
            read.add("source")
    if not read or read == {"source"}:
        return COLUMNS[-1][1]
    return "Built on " + _listed([w for x, w in (("source", "the source"), ("silver", "silver"), ("gold", "gold")) if x in read])


def silver_nodes(spec: dict, built: bool) -> tuple[list[dict], list[dict]]:
    nodes, edges = [], []
    for t in spec["tables"]:
        lines, pills = [], []
        if t["key"] and t.get("key_check_counts"):                      # DPM1: the row check ran: what it counted
            kc = t["key_check_counts"]
            lines.append(f"key checked: {kc['distinct']} of {kc['rows']} unique")
            if (t.get("key_checked") or {}).get("on"):
                lines.append(f"checked against the rows on {t['key_checked']['on']}")
            if t.get("dedupe") and t["order_by"]:
                lines.append(f"the latest by {t['order_by']}")
            pills.append(t["key_rule"])
        elif t["key"] and not t.get("dedupe") and not t.get("fix_key"):     # n208: a guessed key removes no rows
            lines.append(f"every row kept: key {' + '.join(t['key'])} " + ("counted unique when the plan was made"
                                                                          if t.get("key_counted_unique") else "not checked"))
            pills.append(t["key_rule"])
        elif t["key"] and t.get("key_checked"):                         # n221: the key the row check or the review stands behind
            kc = t["key_checked"]
            lines.append(f"one row per key: key {' + '.join(t['key'])} " + (
                f"checked against the rows on {kc['on']}" if kc.get("how") == "rows" and kc.get("on") else
                "checked against the rows" if kc.get("how") == "rows" else "accepted in the review"))
            if t["order_by"]:
                lines.append(f"the latest by {t['order_by']}")
            pills.append(t["key_rule"])
        elif t["key"]:
            lines.append(f"one row per {' + '.join(t['key'])}")
            if t["order_by"]:
                lines.append(f"the latest by {t['order_by']}")
            pills.append(t["key_rule"])
        else:
            lines.append("no key: rows kept as they are")
        for c in t["checks"]:
            lines.append(f"{'+'.join(c['columns'])} → {c['parent']}")
            pills.append(c["rule"])
        nid = f"silver:{t['table']}"
        nodes.append({"id": nid, "column": "silver", "label": _dot(t["target"]), "table": t["table"], "lines": lines,
                      "pills": pills, "built": built, "code": _silver._table_cell(t), "language": "python",
                      "code_title": f"Notebook cell for {t['table']}"})
        edges.append({"from": f"bronze:{t['table']}", "to": nid, "label": "cleaned", "built": built})
    return nodes, edges


def gold_nodes(spec: dict, built: bool) -> tuple[list[dict], list[dict]]:
    nodes, edges = [], []
    for v in _gold.all_views(spec):
        nid = f"gold:{v['name']}"
        lines = ([f"dimension: one row per {v['fact']} row"] if v.get("kind") == "dimension" else
                 [f"one row per {v['fact']} row"] + [f"joins {j['to']} on {'+'.join(j['source_cols'])}" for j in v["joins"]])
        nodes.append({"id": nid, "column": "gold", "label": v["name"], "table": v["fact"], "lines": lines,
                      "pills": [j["rule"] for j in v["joins"]], "built": built, "code": _gold.create_sql(v, spec),
                      "language": "sql", "code_title": f"CREATE MATERIALIZED LAKE VIEW {v['name']}"})
        edges.append({"from": f"silver:{v['fact']}", "to": nid, "label": "dimension" if v.get("kind") == "dimension" else "fact",
                      "built": built})
        for j in v["joins"]:
            edges.append({"from": f"silver:{j['to']}", "to": nid, "label": f"on {', '.join(j['on'])}", "rule": j["rule"],
                          "via": j["from"], "built": built})
    return nodes, edges


def pipeline_nodes(content: dict, names: tuple[str, str, str], name: str, built: bool) -> list[dict]:
    under = ("silver", "gold", "built")
    out = []
    for i, a in enumerate(content["properties"]["activities"]):
        after = a["dependsOn"][0]["activity"] if a["dependsOn"] else None
        out.append({"id": f"pipeline:{i}", "column": "pipeline", "under": under[i], "label": a["name"], "notebook": names[i],
                    "lines": [f"runs {names[i]}"] + ([f"after {after} succeeded"] if after else ["first step"]),
                    "pills": [], "built": built, "code": json.dumps(a, indent=2), "language": "json",
                    "code_title": f"Activity {a['name']} of {name}"})
    return out


def tmdl_excerpt(parts: dict) -> str:
    """The relationships and the measures of a semantic model's TMDL parts, as the dry run gives them."""
    out = []
    rel = parts.get("definition/relationships.tmdl")
    if rel:
        out.append("// definition/relationships.tmdl\n" + rel.strip("\n"))
    for path in sorted(p for p in parts if p.startswith("definition/tables/")):
        lines, keep, block = parts[path].splitlines(), False, []
        for line in lines:
            if line.startswith("\tmeasure "):
                keep = True
                block.append(line)
                continue
            if keep and (line.startswith("\t\t") or not line.strip()) and not line.startswith("\t\tannotation"):
                if line.strip():
                    block.append(line)
                continue
            keep = False
        if block:
            out.append(f"// {path} (measures)\n" + "\n".join(block))
    return "\n\n".join(out)


def flow(p, info: dict, chosen: dict, *, silver_schema: str = "silver", gold_schema: str = "gold",
         pipeline_names: tuple[str, str, str] | None = None, items: list[dict] | None = None, dimensions: bool = False) -> dict:
    """The flow of one build. `chosen`: {kind: name} of the outputs in the build. `items`: the cards of the items built on
    the source ({output, label, name, code?, on_model?}). Nothing is invented: a column the engine has nothing for is
    left out, and `notes` says why. `dimensions` (DPM1): the gold views include the dimension views, as when a semantic
    model in the build reads gold; an item with `on_gold` (the gold view names it reads) is drawn from them."""
    silver_spec = _silver.spec(p, info, silver_schema, None, None, False)
    silver_built = "silver_notebook" in chosen or "pipeline" in chosen
    gold_built = "gold_views" in chosen or "pipeline" in chosen
    nodes = [{"id": f"bronze:{t['table']}", "column": "bronze", "label": f"{info.get('schema')}.{t['table']}", "table": t["table"],
              "lines": [], "pills": [], "built": True, "exists": True, "code": None} for t in silver_spec["tables"]]
    sn, edges = silver_nodes(silver_spec, silver_built)
    nodes += sn
    notes, gold_spec = [], None
    if info.get("schemas_enabled"):
        gold_spec = _gold.spec(p, info, silver_schema, gold_schema, None, False, dimensions=dimensions)
        gn, ge = gold_nodes(gold_spec, gold_built)
        nodes += gn
        edges += ge
        if not gold_spec["views"]:
            notes.append("No fact table in the plan, so there is no gold view.")
    else:
        notes.append("Gold views are materialized lake views, which need a lakehouse created with schemas; this one has none.")
    pipe = None
    if "pipeline" in chosen and pipeline_names and gold_spec is not None:
        content = _pipeline.pipeline_content(*pipeline_names, f"{info.get('item_name')}.{info.get('schema')}",
                                             ids={n: _pipeline.placeholder(n) for n in pipeline_names},
                                             workspace_id=info.get("workspace_id"))
        steps = pipeline_nodes(content, pipeline_names, chosen["pipeline"], True)
        nodes += steps
        for a, b in zip(steps, steps[1:]):
            edges.append({"from": a["id"], "to": b["id"], "label": "on success", "built": True})
        pipe = {"name": chosen["pipeline"], "steps": [s["id"] for s in steps]}
    for it in items or []:
        nid = f"item:{it['output']}"
        nodes.append({"id": nid, "column": "built", "label": it["name"], "kind_label": it["label"], "lines": [it.get("reads", "")],
                      "pills": [], "built": True, "code": it.get("code"), "language": it.get("language", "text"),
                      "code_title": it.get("code_title", "")})
        if it.get("on_model"):
            edges.append({"from": it["on_model"], "to": nid, "label": "on the model", "built": True})
        elif it.get("on_gold"):                                   # DPM1: a line from each gold view the item reads
            edges += [{"from": f"gold:{g}", "to": nid, "label": "built on gold", "built": True} for g in it["on_gold"]]
        elif it.get("layer_first"):                               # W1/W4: an item that reads a layer first, the data agent
            layer = it["layer_first"] if it["layer_first"] in ("silver", "gold") else "silver"
            if it.get("fallback", True):
                edges.append({"from": "bronze", "to": nid, "label": f"until {layer} is filled", "built": True})
            if layer == "gold" and gold_spec is not None:
                froms = [f"gold:{v['name']}" for v in gold_spec["views"]]
            else:
                froms = [n["id"] for n in sn] if layer == "silver" else []
            edges += [{"from": x, "to": nid, "label": f"reads {layer}", "built": True} for x in froms]
        else:
            edges.append({"from": "bronze", "to": nid, "label": "reads the source tables", "built": True})
    # W1: an item that reads a layer first (the data agent on silver or gold) is not said to read the source directly
    on_source = [it for it in items or [] if not it.get("on_model") and not it.get("on_gold") and not it.get("layer_first")]
    if on_source and gold_spec and chosen.get("gold_views"):         # n179: the founder's live preview, 9 November 2026
        notes.append(f"{_listed([it['label'] for it in on_source])} {'reads' if len(on_source) == 1 else 'read'} the source tables "
                     "(bronze) directly, also with the gold views built in this run. Building them on the gold views is a later "
                     "option; this version does not.")
    n_gold = len(gold_spec["views"]) if gold_spec else 0
    n_dim = len(gold_spec.get("dimension_views") or []) if gold_spec else 0
    said = (f"Bronze to gold: {len(silver_spec['tables'])} source table(s) become {len(silver_spec['tables'])} silver table(s)"
            + (f", and {n_gold} gold view(s) join them" if n_gold else "")
            + (f", beside {n_dim} gold dimension view(s)" if n_dim else "")
            + ". Dashed boxes are not part of this build. Click a box to see its code.")
    titles = [(c, built_title(items or []) if c == "built" else t) for c, t in COLUMNS]
    return {"columns": [{"id": c, "title": t} for c, t in titles], "nodes": nodes, "edges": edges, "pipeline": pipe,
            "notes": notes, "said": said}
