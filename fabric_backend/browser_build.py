"""What /check offers under its result (n49): a Power BI model and a small app from the same plan, previewed on the
visitor's own rows and downloaded as files, all in the browser (Pyodide), nothing sent anywhere.

Both are drafts and say so with the status words of `tool_status`:
- the model is `semantic_model.draft` unchanged (the TMDL that semantic_model_draft returns), packed as a Power BI
  project (.pbip): the semantic model folder plus an empty report that points at it by path. There is no report tool in
  Krusgraph, so the report preview here is drawn from the rows by this module, with the draft's own measures; where the
  plan has a total that doubles (amounts.py), the right sum stands beside the wrong one, both counted in the rows.
- the app is `rayfin.rayfin_files` (the Rayfin connector) and `app_starter.starter` (a Lovable prompt, queries, the
  edge function) for an API that does not exist yet: its description comes from `graphql.definition` over the same plan,
  read the way describe_backend reads a created API's definition, with placeholders for the workspace and endpoint.

The previews count with the engine's own SQL dialect over the source /check already read (browser_check._source), so
the numbers are the visitor's rows, not an illustration.
"""
from __future__ import annotations

import base64
import io
import json
import re
import zipfile

from . import tool_status as ts

DRAFT_WORD = "Draft only"            # the status word for the report part: there is no report tool to give it another
ENDPOINT = "<your API for GraphQL endpoint, after Create it in your own Fabric>"
WORKSPACE = "<workspace id>"


def _name(src) -> str:
    base = {"sample": "shop", "sap": "sap_sales", "crm": "crm_erp"}.get(getattr(src, "_kind", ""), "") or re.sub(r"\W+", "_", src.schema.schema or "data")
    return (base.strip("_") or "data")[:40]


def _one(execute, sql: str):
    rows = list(execute(sql))
    return next(iter(rows[0].values())) if rows else None


def _num(v) -> float | int | None:
    if v is None:
        return None
    f = float(v)
    return int(f) if f.is_integer() else round(f, 2)


def _label_column(plan, table: str) -> str:
    """The column that names a row of a dimension in a chart: its first text column outside the key, else the key."""
    t = plan.schema[table]
    key = {c.lower() for c in plan.keys.get(table, ([], ""))[0]}
    text = [c.name for c in t.columns if c.name.lower() not in key and not re.search(r"(^|_)(id|no|nr)$", c.name.lower())
            and any(x in (c.data_type or "").lower() for x in ("char", "string", "text"))]
    return text[0] if text else (plan.keys.get(table, ([t.columns[0].name], ""))[0][0])


_SUM = re.compile(r"^SUM\('?(.+?)'?\[(.+)\]\)$")         # the draft's measures: COUNTROWS('t') or SUM('t'[c])


def _measures(plan, src, measures: list[dict]) -> list[dict]:
    from .dialects import of
    d = of(src.execute)
    schema = plan.schema.schema
    out = []
    for m in measures:
        hit = _SUM.match(m.get("expression", ""))
        m = {**m, "column": m.get("column") or (hit.group(2).replace("]]", "]") if hit else None)}
        sql = (f"SELECT SUM({d.quote(m['column'])}) AS v FROM {d.table(schema, m['table'])}" if m.get("column")
               else f"SELECT {d.count}(*) AS v FROM {d.table(schema, m['table'])}")
        try:
            out.append({"name": m["name"], "table": m["table"], "column": m.get("column"), "value": _num(_one(src.execute, sql)), "dax": m["expression"]})
        except Exception:                                          # noqa: BLE001 - one measure that cannot be counted is left out
            continue
    return out


def _chart(plan, src, measures: list[dict]) -> dict | None:
    """The first measure, by the dimension its table points at: at most eight bars, largest first."""
    from .dialects import of
    d = of(src.execute)
    schema = plan.schema.schema
    pairs = [(m, r) for m in sorted(measures, key=lambda x: not x.get("column")) for r in plan.relationships
             if r.source == m["table"] and r.target != r.source and len(r.source_cols) == 1 and len(r.target_cols) == 1]
    named = lambda r: _label_column(plan, r.target) not in plan.keys.get(r.target, ([], ""))[0]   # a name, not a key, on the bars
    for m, rel in sorted(pairs, key=lambda x: not named(x[1])):
        label = _label_column(plan, rel.target)
        value = f"SUM(f.{d.quote(m['column'])})" if m.get("column") else f"{d.count}(*)"
        sql = (f"SELECT g.{d.quote(label)} AS label, {value} AS v FROM {d.table(schema, m['table'])} AS f "
               f"JOIN {d.table(schema, rel.target)} AS g ON f.{d.quote(rel.source_cols[0])} = g.{d.quote(rel.target_cols[0])} "
               f"GROUP BY g.{d.quote(label)}")
        try:
            rows = [r for r in src.execute(sql) if r.get("v") is not None]
        except Exception:                                          # noqa: BLE001
            continue
        rows.sort(key=lambda r: -float(r["v"]))
        if rows:
            return {"title": f"{m['name']} by {rel.target}.{label}", "measure": m["name"], "by": f"{rel.target}.{label}",
                    "bars": [{"label": str(r["label"]), "value": _num(r["v"])} for r in rows[:8]], "more": max(0, len(rows) - 8)}
    return None


def _doubled(plan, src) -> dict | None:
    """The plan's first total that doubles, both sums counted in the rows (amounts.before_after)."""
    from . import amounts
    for f in amounts.check(plan)["findings"]:
        ba = amounts.before_after(plan.schema.schema, f, src.execute)
        if ba and ba["summed_over_lines"] is not None and ba["summed_per_header"] is not None:
            return {"column": f"{f['header']}.{ba['column']}", "header": f["header"], "line": f["line"],
                    "right": _num(ba["summed_per_header"]), "wrong": _num(ba["summed_over_lines"]),
                    "why": f"Summed over the {f['line']} rows each {f['header']} row counts once per line; summed on {f['header']} it counts once."}
    return None


def _app_rows(plan, src, fact: str, n: int = 8) -> dict:
    """The first rows of the fact table, with the name of what it points at; columns that look like personal data by
    name are left out, as in the drafted queries."""
    from . import evidence, privacy
    from .dialects import of
    d = of(src.execute)
    schema = plan.schema.schema
    t = plan.schema[fact]
    hidden = {c for (tb, c) in privacy.personal_columns(plan.schema, [fact])}
    cols = [c.name for c in t.columns if c.name not in hidden][:4]
    rows = list(src.execute(evidence.sample_sql(schema, fact, cols, n, {c.name: c.data_type for c in t.columns}, d)))
    rel = next((r for r in plan.relationships if r.source == fact and len(r.source_cols) == 1 and len(r.target_cols) == 1
                and r.target != fact and r.source_cols[0] in cols), None)
    extra = None
    if rel:
        label = _label_column(plan, rel.target)
        if label not in {c for (tb, c) in privacy.personal_columns(plan.schema, [rel.target])}:
            names = {str(r["k"]): r["v"] for r in src.execute(
                f"SELECT {d.quote(rel.target_cols[0])} AS k, {d.quote(label)} AS v FROM {d.table(schema, rel.target)}")}
            extra = f"{rel.target}.{label}"
            for r in rows:
                r[extra] = names.get(str(r.get(rel.source_cols[0])))
    head = cols + ([extra] if extra else [])
    return {"table": fact, "columns": head, "rows": [[_cell(r.get(c)) for c in head] for r in rows]}


def _cell(v):
    if v is None or isinstance(v, (int, float, str)):
        return v
    return str(v)


# ------------------------------------------------------------------ the files ---------------------------------------

def pbip_files(name: str, parts: dict[str, str]) -> dict[str, str]:
    """A Power BI project: <name>.pbip, the semantic model folder with the draft's parts, and an empty report bound to
    it by path (definition.pbir byPath). The layout of a project as Power BI Desktop saves it (PBIP, report in the
    PBIR-legacy report.json); the shop project from /check was opened in Power BI Desktop on 30 October 2026."""
    sm, rp = f"{name}.SemanticModel", f"{name}.Report"
    platform = lambda kind: json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                                        "metadata": {"type": kind, "displayName": name},
                                        "config": {"version": "2.0", "logicalId": "00000000-0000-0000-0000-000000000000"}}, indent=2)
    out = {f"{name}.pbip": json.dumps({"version": "1.0", "artifacts": [{"report": {"path": rp}}], "settings": {"enableAutoRecovery": True}}, indent=2)}
    for p, c in parts.items():
        out[f"{sm}/{p}"] = c
    out[f"{sm}/.platform"] = platform("SemanticModel")
    out[f"{rp}/definition.pbir"] = json.dumps({"version": "4.0", "datasetReference": {"byPath": {"path": f"../{sm}"}}}, indent=2)
    out[f"{rp}/report.json"] = json.dumps({"config": json.dumps({"version": "5.37", "themeCollection": {}, "activeSectionIndex": 0}),
                                           "layoutOptimization": 0, "resourcePackages": [],
                                           "sections": [{"config": "{}", "displayName": "Page 1", "displayOption": 1, "filters": "[]",
                                                         "height": 720.0, "name": "ReportSection", "visualContainers": [], "width": 1280.0}]}, indent=2)
    out[f"{rp}/.platform"] = platform("Report")
    out["README.md"] = "\n".join([
        f"# {name}: a Power BI project drafted by Krusgraph /check", "",
        f"Status: {ts.label('semantic_model_draft')} (the model, from semantic_model_draft); the report: {DRAFT_WORD}, an empty page.",
        "Made in your browser from the plan /check showed; nothing was sent anywhere.", "",
        f"- `{sm}/`: the semantic model in TMDL, Direct Lake on a Fabric SQL analytics endpoint, exactly as semantic_model_draft writes it.",
        f"- `{rp}/`: an empty report bound to the model by path. Krusgraph has no report tool; the preview on /check was drawn there, not here.",
        "", "Before it shows data: Direct Lake reads Delta tables in Fabric, so the tables must be in a lakehouse first, and",
        f"`{sm}/definition/expressions.tmdl` must name its SQL analytics endpoint and lakehouse (now placeholders).",
        "Create it in your own Fabric (krusgraph.com/start) does that with create_semantic_model.", "",
        "Opened in Power BI Desktop on 30 October 2026 (the shop project from /check): the empty report page opens, and the data shows",
        "once the tables are in a Fabric lakehouse. If it does not open for you, tell us (krusgraph.com/support).", ""])
    return out


def _describe(env: dict) -> dict:
    """describe_backend's reading of an API definition (server.describe_definition), for a definition made here: the
    server module itself does not load in the browser. tests/test_check.py keeps the two equal."""
    from .graphql import decode
    body, types = decode(env), []
    for ds in body.get("datasources", []):
        for o in ds.get("objects", []):
            actions = o.get("actions", {})
            types.append({"type": o.get("graphqlType"),
                          "query_field": o.get("graphqlType") if str(o.get("graphqlType", "")).endswith("s") else f"{o.get('graphqlType')}s",
                          "source": o.get("sourceObject"), "fields": list((o.get("fieldMappings") or {}).values()),
                          "relationships": [{"field": r.get("field"), "to": r.get("targetObject"), "cardinality": r.get("cardinality")}
                                            for r in o.get("relationships", [])],
                          "by_key": actions.get("Query_by_pk") == "Enabled",
                          "writable": any(actions.get(a) == "Enabled" for a in ("Create", "Update", "Delete"))})
    return {"types": types, "how_to_query": "{ <query_field>(first: 10, filter: {...}, orderBy: {...}) { items { <fields> <relationship> { ... } } } }"}


def app_files(name: str, plan) -> dict[str, str]:
    from .app_starter import starter
    from .graphql import definition
    from .rayfin import rayfin_files
    api = f"{name}_api"
    s = starter(_describe(definition(plan, api, WORKSPACE, "<lakehouse id>")), ENDPOINT, api, WORKSPACE)
    out = {f"app/{p}": c for p, c in rayfin_files(plan).items()}
    out["app/lovable-prompt.md"] = s["lovable_prompt"] + "\n"
    out["app/queries.graphql"] = "\n\n".join(f"# {q['title']}\n{q['query']}" for q in s["queries"]) + "\n"
    out["app/checklist.md"] = "\n".join(f"- [ ] {c}" for c in s["checklist"]) + "\n"
    out[f"app/{s['backend']['edge_function']['path']}"] = s["backend"]["edge_function"]["source"]
    out[f"app/{s['backend']['frontend']['path']}"] = s["backend"]["frontend"]["source"]
    out["app/README.md"] = "\n".join([
        f"# {name}: an app starter drafted by Krusgraph /check", "",
        f"Status: Rayfin connector {ts.label('rayfin_connector')}; app starter {ts.label('app_starter')}.",
        "Made in your browser from the plan /check showed; nothing was sent anywhere.", "",
        "- `rayfin/connectors/data/`: Rayfin (Fabric Apps) entity classes with the plan's keys and relationships (rayfin_connector).",
        "- `lovable-prompt.md`, `queries.graphql`, `checklist.md`, `supabase/`, `src/`: app_starter for an API for GraphQL over the same plan.",
        "", f"The API does not exist yet: `{ENDPOINT}` and `{WORKSPACE}` are placeholders until you create it in your own Fabric",
        "(krusgraph.com/start, create_backend). The preview on /check was drawn there from your rows; this is the code, not that preview.", ""])
    return out


def zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p, c in sorted(files.items()):
            z.writestr(zipfile.ZipInfo(p, (2026, 1, 1, 0, 0, 0)), c.encode("utf-8"), zipfile.ZIP_DEFLATED)
    return buf.getvalue()


# ------------------------------------------------------------------ the one call the page makes ---------------------

def build(kind: str = "sample", files: list | None = None, text: str = "") -> dict:
    """Both previews and both downloads for one input of /check: {"report", "app", "status", "downloads": {file name:
    base64}}. The input is read again from the same bytes (files stay in the worker, never on a server)."""
    import shutil

    from . import graphs, semantic_model
    from .browser_check import _source
    from .infer import plan as make_plan
    src, folder = _source(kind, files, text)
    src._kind = kind
    try:
        p = make_plan(src.schema)
        name = _name(src)
        sm = semantic_model.draft(p, {"schema": p.schema.schema, "item_kind": "Lakehouse"}, f"{name}_model")
        roles = graphs.analyze(p)["roles"]
        facts = [t.name for t in p.schema if roles.get(t.name, {}).get("role") == "fact" and t.name in p.keys] or \
                [t.name for t in p.schema if t.name in p.keys] or [t.name for t in p.schema]
        report: dict = {"tables": len(p.schema), "relationships": len(p.relationships), "measures": [], "chart": None, "doubled": None,
                        "has_data": src.has_data}
        app: dict = {"kpis": [], "list": None, "chart": None, "has_data": src.has_data}
        if src.has_data and len(p.schema):
            ms = _measures(p, src, sm["summary"].get("measures", []))
            report["measures"], report["chart"], report["doubled"] = ms[:4], _chart(p, src, ms), _doubled(p, src)
            from .dialects import of
            d = of(src.execute)
            for t in facts[:3]:
                try:
                    app["kpis"].append({"label": f"Rows in {t}", "value": _num(_one(src.execute, f"SELECT {d.count}(*) AS v FROM {d.table(p.schema.schema, t)}"))})
                except Exception:                                  # noqa: BLE001
                    pass
            app["kpis"] += [{"label": m["name"], "value": m["value"]} for m in ms if m.get("column")][:1]
            try:
                app["list"] = _app_rows(p, src, facts[0])
            except Exception:                                      # noqa: BLE001 - the downloads still come
                app["list"] = None
            app["chart"] = report["chart"]
        downloads = {f"{name}_model.zip": base64.b64encode(zip_bytes(pbip_files(f"{name}_model", sm["parts"]))).decode(),
                     f"{name}_app.zip": base64.b64encode(zip_bytes(app_files(name, p))).decode()}
        return {"name": name, "report": report, "app": app, "downloads": downloads,
                "status": {"model": ts.label("semantic_model_draft"), "report": DRAFT_WORD, "create_model": ts.short("create_semantic_model"),
                           "rayfin": ts.label("rayfin_connector"), "app_starter": ts.label("app_starter")}}
    finally:
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
        if src.close:
            src.close()
