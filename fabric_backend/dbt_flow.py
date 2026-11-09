"""The dbt project's flow, drawn (round n177). The founder, 9 November 2026: the dbt step in the chat demo and the
dbt_schema card draw the same flow as the Krusgraph Model's data flow (n174, data_flow.py): sources -> staging ->
marts -> model, the boxes folded, a click shows the box's SQL or YAML.

Built from the files dbt_schema(project=true) writes and nothing else: a source table is a `source('…', '…')` a staging
model selects from (its code: that table's block of the sources file), a staging or mart model is its .sql file (its code:
the file), an edge is a `source()` or `ref()` in a model's SQL. The last column is the semantic model: dbt does not make
it (create_semantic_model builds it from the plan, on the source tables), so it is drawn dashed, as data_flow.py draws
what a build does not make. A node's code is the file's own text, referenced by `file` (the card has the files in the
answer) or carried in `code` (the sources' YAML blocks, and the chat demo's plan JSON).
"""
from __future__ import annotations

import re

COLUMNS = (("sources", "Sources: your tables"), ("staging", "Staging: one clean row per key"),
           ("marts", "Marts: joined for reporting"), ("model", "Model"))

_SOURCE = re.compile(r"source\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)")
_REF = re.compile(r"ref\(\s*'([^']+)'\s*\)")


def _first_comment(sql: str) -> str:
    """The first comment line's text after the model's name ("-- fct_orders: one row per orders row (order_id).")."""
    for line in sql.splitlines():
        s = line.strip()
        if s.startswith("--"):
            text = s[2:].strip()
            return text.split(": ", 1)[1] if ": " in text else text
        if s:
            break
    return ""


def table_block(yml: str, table: str) -> str:
    """One table's block of a dbt sources file: its `- name: <table>` line and everything indented under it."""
    lines, out, indent = yml.splitlines(), [], None
    for line in lines:
        stripped, lead = line.lstrip(), len(line) - len(line.lstrip())
        if indent is not None:
            if stripped and lead <= indent:
                break
            out.append(line)
        elif stripped == f"- name: {table}" and lead >= 4:
            indent = lead
            out.append(line)
    pad = min((len(x) - len(x.lstrip()) for x in out if x.strip()), default=0)
    return "\n".join(x[pad:] for x in out).rstrip() + ("\n" if out else "")


def flow(files: dict[str, str], with_code: bool = False) -> dict | None:
    """The flow of a dbt project's files, or None when there is no model to draw (a sources file alone)."""
    models = {p: t for p, t in files.items() if p.startswith("models/") and p.endswith(".sql")}
    if not models:
        return None
    sources_files = [p for p in files if p.startswith("models/sources/") and p.endswith(".yml")]
    nodes, edges, seen_src = [], [], {}
    name_of = {p: p.rsplit("/", 1)[-1][:-4] for p in models}
    column_of = {p: ("marts" if "/marts/" in p else "staging") for p in models}
    for p in sorted(models, key=lambda x: (column_of[x] != "staging", x)):
        sql, mid = models[p], f"model:{name_of[p]}"
        for src, table in _SOURCE.findall(sql):
            sid = f"source:{src}.{table}"
            if sid not in seen_src:
                block = next((table_block(files[f], table) for f in sources_files if table_block(files[f], table)), "")
                seen_src[sid] = {"id": sid, "column": "sources", "label": table, "lines": [f"source {src}"], "built": True,
                                 "code": block, "language": "yaml", "code_title": f"{table} in the sources file, with its tests",
                                 "file": next(iter(sources_files), "")}
            edges.append({"from": sid, "to": mid, "built": True})
        for ref in _REF.findall(sql):
            edges.append({"from": f"model:{ref}", "to": mid, "built": True})
        node = {"id": mid, "column": column_of[p], "label": name_of[p], "lines": [x for x in [_first_comment(sql)] if x],
                "built": True, "file": p, "language": "sql", "code_title": p}
        if with_code:
            node["code"] = sql
        nodes.append(node)
    marts = [n["id"] for n in nodes if n["column"] == "marts"]
    model = {"id": "model:semantic_model", "column": "model", "label": "Semantic model", "built": False,
             "lines": ["not made by dbt: Krusgraph builds it from the plan, on the source tables"], "code": "", "language": ""}
    all_nodes = list(seen_src.values()) + nodes + [model]
    ids = {n["id"] for n in all_nodes}
    edges = [e for e in edges if e["from"] in ids]
    edges += [{"from": m, "to": model["id"], "built": False} for m in marts]
    return {"columns": [{"id": c, "label": label} for c, label in COLUMNS], "nodes": all_nodes, "edges": edges}
