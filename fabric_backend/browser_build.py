"""What /check offers under its result (n49): a Power BI model and a small app from the same plan, previewed on the
visitor's own rows and downloaded as files, all in the browser (Pyodide), nothing sent anywhere.

Both are drafts and say so with the status words of `tool_status`:
- the model is `semantic_model.draft` unchanged (the TMDL that semantic_model_draft returns), packed as a Power BI
  project (.pbip): the semantic model folder plus a report with one blank page that points at it by path. The report
  preview here is drawn from the rows by this module, with the draft's own measures (create_report, n144, draws a page
  only in Fabric, from a model there); where the plan has a total that doubles (amounts.py), the right sum stands beside the wrong one, both counted in the rows.
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
    from .browser_check import NAMES
    base = NAMES.get(getattr(src, "_kind", ""), "") or re.sub(r"\W+", "_", src.schema.schema or "data")
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


_COL = r"'((?:[^']|'')+)'\[((?:[^\]]|\]\])+)\]"                  # 'table'[column] as semantic_model.tmdl_name writes it
_COUNTROWS = re.compile(r"^COUNTROWS\('((?:[^']|'')+)'\)$")
_SUM = re.compile(rf"^SUM\({_COL}\)$")
# level_measures: a header amount once per header row that has line rows in the filter (n150: counted as such, not as rows)
_PER_HEADER = re.compile(rf"^CALCULATE\(SUM\({_COL}\), TREATAS\(VALUES\({_COL}\), {_COL}\)\)$")
_name_of = lambda x: x.replace("''", "'")
_col_of = lambda x: x.replace("]]", "]")


def _model(parts: dict[str, str]) -> dict:
    """The draft's own TMDL read back the way compare_semantic_model and create_report read a model (from_tmdl)."""
    from .model_compare import from_tmdl
    return from_tmdl(parts)


def _measures(plan, src, measures: list[dict], model: dict) -> list[dict]:
    """The draft's measures that create_report would draw (report.measures, n144: never a plain SUM of a column the model
    does not sum, such as a header amount repeated over its lines), each counted in the rows the way its DAX counts:
    COUNTROWS, SUM of a column, or a header amount once per header row that has lines (n150). A measure of any other
    form is left out rather than counted as something else."""
    from . import report as rp
    from .dialects import of
    d = of(src.execute)
    schema = plan.schema.schema
    drawn = {(m["table"], m["measure"]) for m in rp.measures(model)[0]}
    out = []
    for m in measures:
        if (m.get("table"), m.get("name")) not in drawn:
            continue
        e = (m.get("expression") or "").strip()
        if (hit := _COUNTROWS.match(e)):
            agg, column = "count", None
            sql = f"SELECT {d.count}(*) AS v FROM {d.table(schema, _name_of(hit.group(1)))}"
        elif (hit := _SUM.match(e)):
            agg, column = "sum", _col_of(hit.group(2))
            sql = f"SELECT SUM({d.quote(column)}) AS v FROM {d.table(schema, _name_of(hit.group(1)))}"
        elif (hit := _PER_HEADER.match(e)) and _name_of(hit.group(1)) == _name_of(hit.group(5)):
            h, column, line, fk, hk = _name_of(hit.group(1)), _col_of(hit.group(2)), _name_of(hit.group(3)), _col_of(hit.group(4)), _col_of(hit.group(6))
            agg = "per_header"
            sql = (f"SELECT SUM(h.{d.quote(column)}) AS v FROM {d.table(schema, h)} AS h WHERE h.{d.quote(hk)} IN "
                   f"(SELECT l.{d.quote(fk)} FROM {d.table(schema, line)} AS l)")
        else:
            continue
        try:
            out.append({"name": m["name"], "table": m["table"], "column": column, "agg": agg, "value": _num(_one(src.execute, sql)), "dax": e})
        except Exception:                                          # noqa: BLE001 - one measure that cannot be counted is left out
            continue
    return out


def _chart(plan, src, measures: list[dict], model: dict) -> dict | None:
    """The first measure, by the dimension its table points at: at most eight bars, largest first. Only a COUNTROWS or a
    plain SUM on the measure's own table, and only along an active relationship of the model itself (n150: one the
    draft did not build, such as one onto a key that is not unique, is never joined here)."""
    from .dialects import of
    d = of(src.execute)
    schema = plan.schema.schema
    tables = {t.name for t in plan.schema}                       # the draft's Calendar is not in the rows
    rels = [r for r in model.get("relationships", []) if r.get("active", True) and r.get("from_table") != r.get("to_table")
            and {r.get("from_table"), r.get("to_table")} <= tables and (r.get("from_cardinality"), r.get("to_cardinality")) == ("many", "one")]
    pairs = [(m, r) for m in sorted(measures, key=lambda x: x["agg"] != "sum") if m["agg"] in ("count", "sum")
             for r in sorted(rels, key=lambda r: (r["to_table"], r["from_column"])) if r["from_table"] == m["table"]]
    named = lambda r: _label_column(plan, r["to_table"]) not in plan.keys.get(r["to_table"], ([], ""))[0]   # a name, not a key, on the bars
    for m, rel in sorted(pairs, key=lambda x: not named(x[1])):
        label = _label_column(plan, rel["to_table"])
        value = f"SUM(f.{d.quote(m['column'])})" if m["agg"] == "sum" else f"{d.count}(*)"
        sql = (f"SELECT g.{d.quote(label)} AS label, {value} AS v FROM {d.table(schema, m['table'])} AS f "
               f"JOIN {d.table(schema, rel['to_table'])} AS g ON f.{d.quote(rel['from_column'])} = g.{d.quote(rel['to_column'])} "
               f"GROUP BY g.{d.quote(label)}")
        try:
            rows = [r for r in src.execute(sql) if r.get("v") is not None]
        except Exception:                                          # noqa: BLE001
            continue
        rows.sort(key=lambda r: -float(r["v"]))
        if rows:
            return {"title": f"{m['name']} by {rel['to_table']}.{label}", "measure": m["name"], "by": f"{rel['to_table']}.{label}",
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
        f"- `{rp}/`: a report with one blank page, bound to the model by path; the preview on /check was drawn there, not here.",
        "  In Fabric, create_report adds a report to a semantic model there with a default page drawn from the model's measures.",
        "", "Before it shows data: Direct Lake reads Delta tables in Fabric, so the tables must be in a lakehouse first, and",
        f"`{sm}/definition/expressions.tmdl` must name its SQL analytics endpoint and lakehouse (now placeholders).",
        "Create it in your own Fabric (krusgraph.com/start) does that with create_semantic_model.", "",
        f"Extract the whole zip first, then open `{name}.pbip` from the extracted folder. Opening the .pbip from inside the zip extracts",
        "that one file only, and Power BI Desktop stops with \"definition.pbism is missing\".", "",
        "Opened in Power BI Desktop on 30 October 2026 (the shop project from /check): the empty report page opens, and the data shows",
        "once the tables are in a Fabric lakehouse. The same day the SAP example stopped with a TMDL format error on a relationships.tmdl",
        "that held only a comment; a document with nothing to put in it is no longer written (README.generated.md in the model folder",
        "says what the plan found instead). If it does not open for you, tell us (krusgraph.com/support).", ""])
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
        validation = None
        if src.has_data and len(p.schema):                        # n150: the model is drafted with the counts, as semantic_model_draft is
            from . import evidence
            try:
                validation = evidence.validate(p, src.execute)
            except Exception:                                      # noqa: BLE001 - the draft by names still comes
                validation = None
        sm = semantic_model.draft(p, {"schema": p.schema.schema, "item_kind": "Lakehouse"}, f"{name}_model", validation=validation)
        roles = graphs.analyze(p)["roles"]
        facts = [t.name for t in p.schema if roles.get(t.name, {}).get("role") == "fact" and t.name in p.keys] or \
                [t.name for t in p.schema if t.name in p.keys] or [t.name for t in p.schema]
        summ, model = sm["summary"], _model(sm["parts"])           # n150: what the model holds, not what the plan found
        tnames = {t.name for t in p.schema}
        report: dict = {"tables": len(p.schema), "relationships": summ["relationships_active"] + summ["relationships_inactive"],
                        "plan_relationships": len(p.relationships),
                        "not_built": [{"what": f"{x['source']}.{'+'.join(x['columns'])} → {x['target']}", "why": x["why"],
                                       "reason": "key_not_unique" if x.get("key_not_unique") else "combined_key"} for x in summ["not_expressible"]],
                        "keys_not_unique": summ.get("keys_not_unique", []),
                        "built": sorted(f"{x['from_table']}.{x['from_column']} → {x['to_table']}" for x in model["relationships"]
                                        if {x.get("from_table"), x.get("to_table")} <= tnames),
                        "measures": [], "chart": None, "doubled": None, "has_data": src.has_data}
        app: dict = {"kpis": [], "list": None, "chart": None, "has_data": src.has_data}
        if src.has_data and len(p.schema):
            ms = _measures(p, src, sm["summary"].get("measures", []), model)
            report["measures"], report["chart"], report["doubled"] = ms[:4], _chart(p, src, ms, model), _doubled(p, src)
            from .dialects import of
            d = of(src.execute)
            for t in facts[:3]:
                try:
                    app["kpis"].append({"label": f"Rows in {t}", "value": _num(_one(src.execute, f"SELECT {d.count}(*) AS v FROM {d.table(p.schema.schema, t)}"))})
                except Exception:                                  # noqa: BLE001
                    pass
            app["kpis"] += [{"label": m["name"], "value": m["value"]} for m in ms if m["agg"] == "sum"][:1]
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
