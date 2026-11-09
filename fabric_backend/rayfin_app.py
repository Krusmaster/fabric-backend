"""n181: an App (Rayfin, preview) output of the plan: simple choices, a read-only connector, a package, a preflight.

The Krusgraph Model editor offers "App (Rayfin, preview)" beside the model, report, ontology and API. From the plan (and
the semantic model draft's measures) the person ticks which key figures, list pages and charts the app shows (no AI:
every option is a rule over the plan, `options`). The package is `rayfin.rayfin_files` (the connector `rayfin_connector`
writes: one entity per table, every link the review kept as @one/@many, `operations: ['read']`) plus the pages, laid out
for the `dataapp` template of @microsoft/rayfin-cli with `rayfin/tsconfig.json` included. tests/test_rayfin_app.py
compiles it with `tsc --noEmit` against the pinned template packages.

What Microsoft documents (docs/RAYFIN-APP.md, read 9 November 2026):
- Items - Create App Backend, learn.microsoft.com/rest/api/fabric/appbackend/items/create-app-backend: "Create an
  AppBackend in the specified workspace." POST /v1/workspaces/{workspaceId}/appBackends, body displayName, description,
  folderId, sensitivityLabelSettings; "Required Delegated Scopes: Item.ReadWrite.All"; contributor role; the AppBackend
  item is in preview. There is no definition part and no Get/Update Definition: the app's pages, connector and GraphQL
  API are deployed by `rayfin up` through calls Microsoft does not document. So Create makes the (empty) App item with
  the documented call, and the app itself goes in with the package and three commands.
- Tenants - List Tenant Settings, learn.microsoft.com/rest/api/fabric/admin/tenants/list-tenant-settings: GET
  /v1/admin/tenantsettings, "The caller must be a Fabric administrator", "Required Delegated Scopes: Tenant.Read.All or
  Tenant.ReadWrite.All". The setting is "Enable Fabric App Items (preview)" in the Microsoft Fabric section of the
  admin portal's tenant settings (tenant-settings-index). Its settingName is not documented; the founder's run of
  5 November 2026 saw AppBackendTenant. For anyone else the setting cannot be read, and the preflight says so.
"""
from __future__ import annotations

import io
import json
import re
import zipfile

from . import privacy
from .infer import Plan
from .rayfin_app_ui import ACCENTS, DEFAULT_ACCENT, UI_TSX, css as ui_css
from .rayfin import (CONNECTOR_TYPES, RAYFIN_TSCONFIG_PATH, READ_ONLY, class_name, prop_name, rayfin_files,
                     rayfin_type)

LABEL = "App (Rayfin, preview)"
ITEM_TYPE = "AppBackend"                       # the documented item type; the portal shows it as "App"
APP_SCOPE = "Item.ReadWrite.All"               # Create App Backend's only delegated scope
SETTINGS_SCOPES = ("Tenant.Read.All", "Tenant.ReadWrite.All")
SETTING_TITLE = "Enable Fabric App Items (preview)"
SETTING_NAMES = ("AppBackendTenant",)          # seen in the founder's run; not documented
LOOKUP_ROWS = 1000                             # rows a chart or a filter reads of each lookup table
PAGE_SIZE = 25                                 # rows a list page shows at a time (n189)
WIRING = "src/lib/app-connectors.ts"           # beside the template's own src/lib/connectors.ts, which stays as it is
MAX_DEFAULT_CHARTS = 2
EDIT_WITH_AI = "EDIT-WITH-AI.md"              # n189: change the app with Claude, VS Code or Lovable
EDIT_TITLE = "Change the app yourself"
TICKS = ("kpis", "tables", "charts", "filters")
OVERVIEW = "overview"                          # the page with the filters, the key figures and the charts (n189)
CATEGORY_TYPES = ("bar", "table")              # a measure by a dimension; the first is the default
TIME_TYPES = ("line", "bar", "table")          # a measure by month or week
# a load or change time, not a business date: what the header's "last refresh" reads, and never a default chart
TECHNICAL_DATE = re.compile(r"^_|(^|_)(timestamp|ts|loaded|load|ingested|ingest|etl|modified|updated|inserted|refreshed)(_at|_on|_date|_time|_ts)?$", re.I)

ADMIN_STEPS = [
    "A Fabric administrator opens the Fabric portal → Settings (gear) → Admin portal → Tenant settings.",
    f"In the Microsoft Fabric section: {SETTING_TITLE} → Enabled (for the whole organisation or a security group that "
    "includes the people who publish the app) → Apply.",
    "Leave \"Enable anonymous data access for Fabric Apps (Preview)\" off.",
    "Reopen this item; the check runs again before anything else.",
]
NOT_PUBLISHED_WHY = ("Microsoft documents a call that creates an empty App item (Create App Backend, preview), but no "
                     "definition for its pages, connector or GraphQL API: `rayfin up` deploys those through calls that "
                     "are not documented. So the editor does not publish the app; the package and the commands below do.")


# ------------------------------------------------------------------ the choices -----------------------------------

def _single(plan: Plan):
    return [r for r in plan.relationships if len(r.source_cols) == 1 and len(r.target_cols) == 1 and r.target in plan.keys]


def _numeric(t, col: str) -> bool:
    return rayfin_type(next(c.data_type for c in t.columns if c.name == col))[0] in ("int", "decimal")


def _count_column(plan: Plan, t) -> str | None:
    """The column a row count counts (Rayfin's count accepts numeric fields only): a numeric key column, else the first
    numeric column (then the count is of rows where it is set)."""
    key = plan.keys.get(t.name, ([], ""))[0]
    for c in key:
        if _numeric(t, c):
            return c
    return next((c.name for c in t.columns if rayfin_type(c.data_type)[0] in ("int", "decimal")), None)


def _label_column(plan: Plan, t, personal: dict) -> str | None:
    """What a chart's bars are named by: the first text column that is not a key and not personal data by name."""
    key = set(plan.keys.get(t.name, ([], ""))[0])
    for c in t.columns:
        if rayfin_type(c.data_type)[0] == "text" and c.name not in key and (t.name, c.name) not in personal:
            return c.name
    return None


def _out_of(plan: Plan) -> dict[str, list]:
    out: dict[str, list] = {}
    for r in _single(plan):
        out.setdefault(r.source, []).append(r)
    return out


def _paths(out_of: dict, start: str, hops: int) -> list[list]:
    """Every chain of many-to-one links from `start`, one to `hops` long, never back through a table it passed."""
    found, frontier = [], [[r] for r in out_of.get(start, [])]
    while frontier:
        path = frontier.pop(0)
        found.append(path)
        if len(path) < hops:
            seen = {start, *(r.target for r in path)}
            frontier += [path + [r] for r in out_of.get(path[-1].target, []) if r.target not in seen]
    return found


def _path_to(plan: Plan, start: str, target: str, hops: int = 3) -> list | None:
    """The shortest chain of links from `start` to `target` ([] when they are the same table), or None."""
    if start == target:
        return []
    return next((p for p in sorted(_paths(_out_of(plan), start, hops), key=len) if p[-1].target == target), None)


def _hop(r) -> dict:
    return {"source": r.source, "column": r.source_cols[0], "target": r.target, "target_column": r.target_cols[0], "rule": r.rule}


def _technical_date(col: str) -> bool:
    """A load or change time rather than a business date: what the header's "last refresh" reads."""
    return bool(TECHNICAL_DATE.search(col))


def _date_columns(t, personal: dict) -> list[str]:
    return [c.name for c in t.columns if rayfin_type(c.data_type)[0] == "date" and (t.name, c.name) not in personal]


def _filter_label(table: str, column: str) -> str:
    words = column.strip("_").replace("_", " ")
    if column.lower() in ("name", "title", "label", "description"):
        words = table.replace("_", " ")
    return words[:1].upper() + words[1:]


def options(plan: Plan) -> dict:
    """Every key figure, list page, chart and filter the app can show, each with a default and the rule that made it;
    the chart types each chart allows, the pages whose order can change and the accent presets."""
    from . import graphs, semantic_model as sm
    from .views import fact_tables
    role_of = {t: r["role"] for t, r in graphs.analyze(plan, None)["roles"].items()}
    single = _single(plan)
    personal = privacy.personal_columns(plan.schema, [t.name for t in plan.schema])
    ref_cols = {(r.source, r.source_cols[0].lower()) for r in single}
    measures = sm.suggested_measures(plan, list(plan.schema), role_of, ref_cols)
    kpis, tables, charts, left_out = [], [], [], []
    for t in plan.schema:
        col = _count_column(plan, t)
        if col is None:
            left_out.append(f"Rows in {t.name}: Rayfin counts a numeric column and {t.name} has none")
            continue
        fact = role_of.get(t.name) == "fact"
        keyed = col in plan.keys.get(t.name, ([], ""))[0]
        kpis.append({"id": f"rows:{t.name}", "label": f"Rows in {t.name}", "table": t.name, "op": "count", "column": col,
                     "unit": "rows" if keyed else f"rows with {col} set",
                     "default": fact and t.name in plan.keys,
                     "why": ("COUNTROWS in the semantic model draft (a fact table)" if fact else "the table's row count")
                            + ("" if keyed else f"; counts rows where {col} is set")})
    for m in measures:
        if m.get("column"):
            kpis.append({"id": f"sum:{m['table']}.{m['column']}", "label": m["name"], "table": m["table"], "op": "sum",
                         "column": m["column"], "unit": f"sum of {m['table']}.{m['column']}", "default": True,
                         "why": f"{m['expression']} in the semantic model draft"})
    main = (fact_tables(plan) or [None])[0]
    linked = {r.target for r in single if r.source == main}
    for t in plan.schema:
        keyed_fact = role_of.get(t.name) == "fact" and t.name in plan.keys
        tables.append({"id": f"table:{t.name}", "label": t.name, "table": t.name,
                       "default": keyed_fact or t.name in linked,
                       "why": "a fact table with a key" if keyed_fact else (f"{main} links to it" if t.name in linked else "a table of the plan")})
    out_of = _out_of(plan)
    times = []
    for m in measures:
        if not m.get("column"):
            continue
        fact = m["table"]
        paths = _paths(out_of, fact, 2)
        for path in paths:
            end = plan.schema[path[-1].target]
            label = _label_column(plan, end, personal)
            if label is None:
                continue
            via = " → ".join(f"{r.source}.{r.source_cols[0]}" for r in path)
            charts.append({"id": f"chart:{fact}.{m['column']}:" + ">".join(f"{r.source}.{r.source_cols[0]}" for r in path),
                           "label": f"{m['name']} by {end.name} ({label})", "kind": "category", "measure_name": m["name"],
                           "fact": fact, "measure": m["column"], "path": [_hop(r) for r in path],
                           "label_table": end.name, "label_column": label, "leaf": end.name not in out_of,
                           "types": list(CATEGORY_TYPES), "type": CATEGORY_TYPES[0],
                           "default": False, "why": f"{via} → {end.name}.{label}: a link of the plan ({', '.join(r.rule for r in path)})"})
        for path in [[]] + paths:
            end = plan.schema[path[-1].target] if path else plan.schema[fact]
            for col in _date_columns(end, personal):
                hops = ">".join(f"{r.source}.{r.source_cols[0]}" for r in path)
                via = " → ".join([f"{r.source}.{r.source_cols[0]}" for r in path] + [f"{end.name}.{col}"])
                times.append({"id": f"chart:{fact}.{m['column']}:time:{hops}@{end.name}.{col}",
                              "label": f"{m['name']} by month ({end.name}.{col})", "kind": "time", "measure_name": m["name"],
                              "fact": fact, "measure": m["column"], "path": [_hop(r) for r in path],
                              "date_table": end.name, "date_column": col, "technical": _technical_date(col),
                              "types": list(TIME_TYPES), "type": TIME_TYPES[0], "default": False,
                              "why": f"{via}: a date" + (f" along links of the plan ({', '.join(r.rule for r in path)})" if path else
                                                         " of the fact table") + "; by week when the dates span three months or less"})
    for c in [c for c in charts if c["leaf"]][:MAX_DEFAULT_CHARTS]:
        c["default"] = True
    business = sorted((c for c in times if not c["technical"]), key=lambda c: len(c["path"]))
    if business:
        business[0]["default"] = True
    charts += times
    filters, seen = [], set()
    for c in charts:
        table, column = (c["label_table"], c["label_column"]) if c["kind"] == "category" else (c["date_table"], c["date_column"])
        fid = f"filter:{table}.{column}"
        if fid in seen:
            if c["default"]:
                next(f for f in filters if f["id"] == fid)["default"] = True
            continue
        seen.add(fid)
        filters.append({"id": fid, "label": _filter_label(table, column), "table": table, "column": column,
                        "kind": "values" if c["kind"] == "category" else "dates", "default": c["default"],
                        "why": f"{table}.{column}: " + ("a value list" if c["kind"] == "category" else "a date range")
                               + ", applied to every key figure and chart whose table links to it"})
    return {"kpis": kpis, "tables": tables, "charts": charts, "filters": filters, "left_out": left_out,
            "pages": [{"id": OVERVIEW, "label": "Overview (key figures and charts)"}] + [{"id": t["id"], "label": t["label"]} for t in tables],
            "accents": [{"id": k, "label": k.capitalize(), "light": l, "dark": d} for k, (l, d) in ACCENTS.items()],
            "chart_types": {"category": list(CATEGORY_TYPES), "time": list(TIME_TYPES)}}


def defaults(opts: dict) -> dict:
    d = {k: [o["id"] for o in opts[k] if o["default"]] for k in TICKS}
    return {**d, "chart_types": {}, "page_order": [], "accent": DEFAULT_ACCENT}


def resolve(opts: dict, choices: dict | None) -> dict:
    """The ticked options (choices: {kpis, tables, charts, filters} as lists of ids, chart_types {chart id: bar|line|table},
    page_order [page ids], accent; None or a missing key: the defaults). An id the plan does not offer any more (the
    review changed) is listed under `gone`, never guessed."""
    base = defaults(opts)
    choices = base if choices is None else choices
    if not isinstance(choices, dict):
        raise ValueError("app must be an object of choices")
    out, gone = {}, []
    for k in TICKS:
        ids = choices.get(k, base[k])
        if ids is None:
            ids = base[k]
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise ValueError(f"app.{k} must be a list of option ids")
        by_id = {o["id"]: o for o in opts[k]}
        out[k] = [by_id[i] for i in dict.fromkeys(ids) if i in by_id]
        gone += [i for i in ids if i not in by_id]
    if not (out["kpis"] or out["tables"] or out["charts"]):
        raise ValueError("tick at least one key figure, list page or chart for the app")
    types = choices.get("chart_types") or {}
    if not isinstance(types, dict) or not all(isinstance(v, str) for v in types.values()):
        raise ValueError("app.chart_types must map a chart id to bar, line or table")
    out["chart_types"] = {}
    for c in out["charts"]:
        t = types.get(c["id"], c["type"])
        if t not in c["types"]:
            raise ValueError(f"app.chart_types: {c['label']} can be {', '.join(c['types'])}, not {t!r}")
        out["chart_types"][c["id"]] = t
    pages = ([OVERVIEW] if out["kpis"] or out["charts"] else []) + [o["id"] for o in out["tables"]]
    order = choices.get("page_order") or []
    if not isinstance(order, list) or not all(isinstance(i, str) for i in order):
        raise ValueError("app.page_order must be a list of page ids")
    out["page_order"] = [i for i in dict.fromkeys(order) if i in pages] + [i for i in pages if i not in order]
    accent = choices.get("accent") or DEFAULT_ACCENT
    if accent not in ACCENTS:
        raise ValueError(f"app.accent is one of {', '.join(ACCENTS)}")
    out["accent"] = accent
    out["gone"] = gone
    return out


def chosen_ids(chosen: dict) -> dict:
    """The choices as outputs.json keeps them (and the dry run shows them): ids, types, order, accent."""
    return {**{k: [o["id"] for o in chosen[k]] for k in TICKS}, "chart_types": dict(chosen["chart_types"]),
            "page_order": list(chosen["page_order"]), "accent": chosen["accent"]}


# ------------------------------------------------------------------ the pages -------------------------------------

def _connector_name(schema: str) -> str:
    n = re.sub(r"[^a-z0-9]+", "-", (schema or "data").lower()).strip("-")
    return n if n and n[0].isalpha() else f"data-{n}" if n else "data"


def _acc(name: str) -> str:
    return f".{name}" if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name) else f"['{name}']"


def _ts(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


HEADER = "// {path} — generated by Krusgraph (App, Rayfin preview) from the reviewed plan. Read-only: queries only.\n"
EDIT_NOTE = "// Change it yourself, with Claude, VS Code or Lovable: see EDIT-WITH-AI.md. Keep `npm run typecheck` green.\n"


def _fkey(f: dict) -> str:
    return prop_name(f"{f['table']}_{f['column']}")


def _where_fn(table: str) -> str:
    return f"where{class_name(table)}"


def _lookup_chain(plan: Plan, f: dict, path: list, cond: str, indent: str) -> list[str]:
    """TypeScript that turns the filter's condition on its own table into a condition on the path's first table: the
    keys of the rows that match, carried back one link at a time (each a read-only query of at most LOOKUP_ROWS rows)."""
    lines = []
    if not path:
        return [f"{indent}and.push({{ {prop_name(f['column'])}: {cond} }});"]
    last = path[-1]
    key = prop_name(last.target_cols[0])
    lines.append(f"{indent}{'let' if len(path) > 1 else 'const'} keys = present((await data.{class_name(f['table'])}.select(['{key}']).where({{ {prop_name(f['column'])}: {cond} }})"
                 f".first(LOOKUP_ROWS).execute()).map((r) => r.{key}));")
    lines.append(f"{indent}if (!keys.length) return null;")
    for i in range(len(path) - 1, 0, -1):
        step, prev = path[i], path[i - 1]
        k = prop_name(prev.target_cols[0])
        lines.append(f"{indent}const keys{i} = present((await data.{class_name(step.source)}.select(['{k}']).where({{ {prop_name(step.source_cols[0])}: {{ in: keys }} }})"
                     f".first(LOOKUP_ROWS).execute()).map((r) => r.{k}));")
        lines.append(f"{indent}if (!keys{i}.length) return null;")
        lines.append(f"{indent}keys = keys{i};")
    lines.append(f"{indent}and.push({{ {prop_name(path[0].source_cols[0])}: {{ in: keys }} }});")
    return [l for l in lines if l]


def data_ts(plan: Plan, connector: str, chosen: dict, refresh: tuple[str, str] | None) -> tuple[str, dict]:
    """src/lib/app-data.ts: the filters' state, the values they offer, one where-builder per table the cards and charts
    read (filters reach a table along the plan's links), the chart helpers and the last refresh. Returns the text and
    {table: [filter keys that reach it]}."""
    filters = chosen["filters"]
    subjects = sorted({k["table"] for k in chosen["kpis"]} | {c["fact"] for c in chosen["charts"]})
    reach = {t: [(f, _path_to(plan, t, f["table"])) for f in filters] for t in subjects}
    reach = {t: [(f, p) for f, p in fs if p is not None] for t, fs in reach.items()}
    out = [HEADER.format(path="src/lib/app-data.ts").rstrip("\n"), EDIT_NOTE.rstrip("\n"),
           "// The filters reach a table along the links of the plan: the keys of the rows that match are read (at most",
           "// LOOKUP_ROWS per step) and passed on as `{ column: { in: keys } }`. Every call here is a query.",
           "import type { AppConnectorsClient } from './app-connectors';",
           "import { LOOKUP_ROWS } from './app-config';", "",
           f"export type Data = AppConnectorsClient['connectors'][{_ts(connector)}];",
           "export type Range = { from: string; to: string };", "",
           "export type Filters = {"]
    out += [f"  {_fkey(f)}: {'string[]' if f['kind'] == 'values' else 'Range'};" for f in filters]
    out += ["};", "",
            "export const NO_FILTERS: Filters = {"]
    out += [f"  {_fkey(f)}: " + ("[]" if f["kind"] == "values" else "{ from: '', to: '' }") + "," for f in filters]
    out += ["};", "",
            "export type FilterKey = keyof Filters;", "",
            "/** The filters the overview shows, in this order. */",
            "export const FILTERS: { key: FilterKey; label: string; kind: 'values' | 'dates'; column: string }[] = ["]
    out += [f"  {{ key: '{_fkey(f)}', label: {_ts(f['label'])}, kind: '{f['kind']}', column: {_ts(f['table'] + '.' + f['column'])} }},"
            for f in filters]
    out += ["];", "",
            "export function isActive(f: Filters, key: FilterKey): boolean {",
            "  const v = f[key] as string[] | Range;",
            "  return Array.isArray(v) ? v.length > 0 : Boolean(v.from || v.to);",
            "}", "",
            "/** \"Not filtered by …\" for the active filters that do not reach a table. */",
            "export function notReached(f: Filters, reached: readonly FilterKey[]): string | undefined {",
            "  const missed = FILTERS.filter((x) => isActive(f, x.key) && !reached.includes(x.key)).map((x) => x.label);",
            "  return missed.length ? `Not filtered by ${missed.join(', ')}: no link from this table.` : undefined;",
            "}", "",
            "function present<T>(values: readonly (T | null | undefined)[]): T[] {",
            "  return [...new Set(values.filter((v): v is T => v !== null && v !== undefined))];",
            "}", "",
            "function dateRange(r: Range): { gte?: Date; lte?: Date } {",
            "  return {",
            "    ...(r.from ? { gte: new Date(`${r.from}T00:00:00.000Z`) } : {}),",
            "    ...(r.to ? { lte: new Date(`${r.to}T23:59:59.999Z`) } : {}),",
            "  };",
            "}", ""]
    values = [f for f in filters if f["kind"] == "values"]
    out += ["/** The values each list filter offers: the distinct values of its column (of the first LOOKUP_ROWS rows). */",
            f"export async function readFilterValues(data: Data): Promise<Record<string, string[]>> {{"]
    if values:
        out.append("  const read = await Promise.all([")
        out += [f"    data.{class_name(f['table'])}.select(['{prop_name(f['column'])}']).first(LOOKUP_ROWS).execute()"
                f".then((rows) => present(rows.map((r) => r.{prop_name(f['column'])})).map(String).sort()),"
                for f in values]
        out.append("  ]);")
        out.append("  return { " + ", ".join(f"{_fkey(f)}: read[{i}]" for i, f in enumerate(values)) + " };")
    else:
        out.append("  void data;")
        out.append("  return {};")
    out += ["}", ""]
    reached = {}
    for t in subjects:
        cls = class_name(t)
        out += [f"export type {cls}Where = Parameters<Data['{cls}']['where']>[0];", "",
                f"/** {t}: the filters as a where argument; null when no row can match. */",
                f"export async function {_where_fn(t)}(data: Data, f: Filters): Promise<{cls}Where | null> {{",
                f"  const and: {cls}Where[] = [];"]
        reached[t] = []
        for f, path in reach[t]:
            k = _fkey(f)
            reached[t].append(k)
            route = " → ".join([f"{f['table']}.{f['column']}"] + [f"{r.source}.{r.source_cols[0]}" for r in reversed(path)])
            if f["kind"] == "values":
                out += [f"  if (f.{k}.length) {{", f"    // {route}"]
                out += _lookup_chain(plan, f, path, f"{{ in: f.{k} }}", "    ")
            else:
                out += [f"  if (f.{k}.from || f.{k}.to) {{", f"    // {route}"]
                out += _lookup_chain(plan, f, path, f"dateRange(f.{k})", "    ")
            out.append("  }")
        if not reach[t]:
            out.append("  void data;")
            out.append("  void f;")
        out += ["  return and.length === 0 ? {} : and.length === 1 ? and[0] : { and };", "}", ""]
    out += ["export function lookup<R>(rows: readonly R[], key: (r: R) => unknown, value: (r: R) => unknown): Map<string, unknown> {",
            "  return new Map(rows.map((r) => [String(key(r)), value(r)] as [string, unknown]));",
            "}", "",
            "/** Follows each group's key along the links (each hop a lookup) to what the last table says about it. */",
            "export function follow(key: unknown, hops: readonly Map<string, unknown>[]): unknown {",
            "  let k: unknown = key;",
            "  for (const hop of hops) k = k === null || k === undefined ? undefined : hop.get(String(k));",
            "  return k;",
            "}", "",
            "export type Point = { label: string; value: number };", "",
            "/** Sums by name, largest first. */",
            "export function byName(rows: readonly { name: unknown; value: number | null }[]): Point[] {",
            "  const sums = new Map<string, number>();",
            "  for (const r of rows) {",
            "    const name = r.name === null || r.name === undefined ? '(none)' : String(r.name);",
            "    sums.set(name, (sums.get(name) ?? 0) + (r.value ?? 0));",
            "  }",
            "  return [...sums].map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value);",
            "}", "",
            "export function toDate(v: unknown): Date | null {",
            "  if (v === null || v === undefined || v === '') return null;",
            "  const d = v instanceof Date ? v : new Date(String(v));",
            "  return Number.isNaN(d.getTime()) ? null : d;",
            "}", "",
            "/** Sums by month, or by week (from Monday) when the dates span three months or less; in date order. */",
            "export function byPeriod(rows: readonly { when: unknown; value: number | null }[]): { grain: 'month' | 'week'; points: Point[] } {",
            "  const dated = rows.map((r) => ({ when: toDate(r.when), value: r.value ?? 0 })).filter((r): r is { when: Date; value: number } => r.when !== null);",
            "  const times = dated.map((r) => r.when.getTime());",
            "  const grain = times.length && Math.max(...times) - Math.min(...times) <= 92 * 86400000 ? 'week' : 'month';",
            "  const sums = new Map<string, number>();",
            "  for (const r of dated) {",
            "    let d = r.when;",
            "    if (grain === 'week') d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - ((d.getUTCDay() + 6) % 7)));",
            "    const label = grain === 'week' ? d.toISOString().slice(0, 10) : d.toISOString().slice(0, 7);",
            "    sums.set(label, (sums.get(label) ?? 0) + r.value);",
            "  }",
            "  return { grain, points: [...sums].sort(([a], [b]) => a.localeCompare(b)).map(([label, value]) => ({ label, value })) };",
            "}", ""]
    out += ["/** When the data was last loaded: " + (f"the latest {refresh[0]}.{refresh[1]}" if refresh else
                                                     "the plan has no load-time column, so null (the header shows when the page read the data)") + ". */",
            "export async function readLastRefresh(data: Data): Promise<Date | null> {"]
    if refresh:
        cls, col = class_name(refresh[0]), prop_name(refresh[1])
        out += [f"  const rows = await data.{cls}.select(['{col}']).orderBy({{ {col}: 'desc' }}).first(1).execute();",
                f"  return toDate(rows[0]?.{col});"]
    else:
        out += ["  void data;", "  return null;"]
    out += ["}"]
    return "\n".join(out) + "\n", reached


def _refresh_column(plan: Plan, chosen: dict, personal: dict) -> tuple[str, str] | None:
    """The column the header's "last refresh" reads: a load-time column (TECHNICAL_DATE) of a table the app shows, the
    fact tables first. None when there is none: a business date (an order date) is not when the data was refreshed, so
    the header then says when the page read the data."""
    tables = [k["table"] for k in chosen["kpis"]] + [c["fact"] for c in chosen["charts"]] + [o["table"] for o in chosen["tables"]]
    for t in dict.fromkeys(tables):
        for c in _date_columns(plan.schema[t], personal):
            if _technical_date(c):
                return t, c
    return None


def overview_tsx(plan: Plan, chosen: dict, reached: dict) -> str:
    kpis, charts, filters = chosen["kpis"], chosen["charts"], chosen["filters"]
    subjects = sorted({k["table"] for k in kpis} | {c["fact"] for c in charts})
    lines = [HEADER.format(path="src/pages/OverviewPage.tsx").rstrip("\n"), EDIT_NOTE.rstrip("\n"),
             "import { useEffect, useState } from 'react';", "",
             "import { BarChart, DateRange, KpiCard, LineChart, MultiSelect, Section, Status, ValueTable } from '../components/kg-ui';",
             "import { getConnectorsClient } from '../lib/app-connectors';",
             "import { LOOKUP_ROWS } from '../lib/app-config';",
             "import {",
             "  FILTERS,", "  NO_FILTERS,", "  byName,", "  byPeriod,", "  follow,", "  lookup,", "  notReached,", "  readFilterValues,",
             *[f"  {_where_fn(t)}," for t in subjects],
             "} from '../lib/app-data';",
             "import type { Data, Filters, Point } from '../lib/app-data';", "",
             "type Kpi = { id: string; label: string; unit: string; value: number | null; note?: string };",
             "type Chart = { id: string; title: string; type: 'bar' | 'line' | 'table'; axis: string; points: Point[]; note?: string };", "",
             "/** Each table's where argument for the filters, read once per change of the filters. */",
             "async function readWheres(data: Data, f: Filters) {",
             f"  const [{', '.join(prop_name(t) + 'Where' for t in subjects)}] = await Promise.all([{', '.join(f'{_where_fn(t)}(data, f)' for t in subjects)}]);",
             f"  return {{ {', '.join(prop_name(t) + 'Where' for t in subjects)} }};",
             "}", "",
             "type Wheres = Awaited<ReturnType<typeof readWheres>>;", "",
             "/** The key figures, each with the filters that reach its table. */",
             "async function readKpis(data: Data, f: Filters, w: Wheres): Promise<Kpi[]> {",
             "  return Promise.all(["]
    for k in kpis:
        cls = class_name(k["table"])
        lines += ["    (async (): Promise<Kpi> => {",
                  f"      const where = w.{prop_name(k['table'])}Where;",
                  f"      const rows = where === null ? [] : await data.{cls}.where(where).aggregate({{ value: {{ {k['op']}: '{prop_name(k['column'])}' }} }}).execute();",
                  f"      const value = where === null ? 0 : (rows[0]?.aggregations.value ?? null);",
                  f"      return {{ id: {_ts(k['id'])}, label: {_ts(k['label'])}, unit: {_ts(k['unit'])}, value, "
                  f"note: notReached(f, [{', '.join(repr(x) for x in reached.get(k['table'], []))}]) }};",
                  "    })(),"]
    lines += ["  ]);", "}", "",
              "/** The charts: the measure summed by the dimension (or the date) its links reach, with the filters applied. */",
              "async function readCharts(data: Data, f: Filters, w: Wheres): Promise<Chart[]> {",
              "  return Promise.all(["]
    for ch in charts:
        cls = class_name(ch["fact"])
        path = ch["path"]
        typ = chosen["chart_types"][ch["id"]]
        note = f"notReached(f, [{', '.join(repr(x) for x in reached.get(ch['fact'], []))}])"
        lines += ["    (async (): Promise<Chart> => {", f"      // {ch['why']}",
                  f"      const where = w.{prop_name(ch['fact'])}Where;"]
        if ch["kind"] == "time" and not path:
            col = prop_name(ch["date_column"])
            lines += [f"      const grouped = where === null ? [] : await data.{cls}.where(where).groupBy(['{col}']).aggregate({{ value: {{ sum: '{prop_name(ch['measure'])}' }} }}).execute();",
                      f"      const series = byPeriod(grouped.map((g) => ({{ when: g.fields.{col}, value: g.aggregations.value }})));",
                      f"      return {{ id: {_ts(ch['id'])}, title: `{ch['measure_name']} by ${{series.grain}} ({ch['date_table']}.{ch['date_column']})`, "
                      f"type: '{typ}', axis: series.grain === 'week' ? 'Week' : 'Month', points: series.points, note: {note} }};"]
        else:
            first = prop_name(path[0]["column"])
            lines.append(f"      const grouped = where === null ? [] : await data.{cls}.where(where).groupBy(['{first}']).aggregate({{ value: {{ sum: '{prop_name(ch['measure'])}' }} }}).execute();")
            hops = []
            for i, step in enumerate(path[1:], 1):
                prev = path[i - 1]
                k, v = prop_name(prev["target_column"]), prop_name(step["column"])
                lines.append(f"      const hop{i} = await data.{class_name(step['source'])}.select(['{k}', '{v}']).first(LOOKUP_ROWS).execute();")
                hops.append(f"lookup(hop{i}, (r) => r.{k}, (r) => r.{v})")
            end_table = ch["label_table"] if ch["kind"] == "category" else ch["date_table"]
            end_col = ch["label_column"] if ch["kind"] == "category" else ch["date_column"]
            lk, lv = prop_name(path[-1]["target_column"]), prop_name(end_col)
            lines.append(f"      const ends = await data.{class_name(end_table)}.select(['{lk}', '{lv}']).first(LOOKUP_ROWS).execute();")
            lines.append(f"      const hops = [{', '.join(hops + [f'lookup(ends, (r) => r.{lk}, (r) => r.{lv})'])}];")
            if ch["kind"] == "category":
                lines += [f"      const points = byName(grouped.map((g) => ({{ name: follow(g.fields.{first}, hops), value: g.aggregations.value }})));",
                          f"      return {{ id: {_ts(ch['id'])}, title: {_ts(ch['label'])}, type: '{typ}', axis: {_ts(_filter_label(end_table, end_col))}, points, note: {note} }};"]
            else:
                lines += [f"      const series = byPeriod(grouped.map((g) => ({{ when: follow(g.fields.{first}, hops), value: g.aggregations.value }})));",
                          f"      return {{ id: {_ts(ch['id'])}, title: `{ch['measure_name']} by ${{series.grain}} ({end_table}.{end_col})`, "
                          f"type: '{typ}', axis: series.grain === 'week' ? 'Week' : 'Month', points: series.points, note: {note} }};"]
        lines.append("    })(),")
    lines += ["  ]);", "}", "",
              "function ChartView(props: { chart: Chart }) {",
              "  const c = props.chart;",
              "  if (c.type === 'line') return <LineChart title={c.title} points={c.points} note={c.note} />;",
              "  if (c.type === 'table') return <ValueTable title={c.title} points={c.points} label={c.axis} note={c.note} />;",
              "  return <BarChart title={c.title} points={c.points} note={c.note} />;",
              "}", "",
              "export function OverviewPage() {",
              "  const [filters, setFilters] = useState<Filters>(NO_FILTERS);",
              "  const [values, setValues] = useState<Record<string, string[]>>({});",
              "  const [kpis, setKpis] = useState<Kpi[] | null>(null);",
              "  const [charts, setCharts] = useState<Chart[] | null>(null);",
              "  const [error, setError] = useState<string | null>(null);", "",
              "  useEffect(() => {",
              "    let cancelled = false;",
              "    getConnectorsClient()",
              "      .then((client) => readFilterValues(client.connectors" + _acc(chosen["connector"]) + "))",
              "      .then((v) => {", "        if (!cancelled) setValues(v);", "      })",
              "      .catch(() => undefined);",
              "    return () => {", "      cancelled = true;", "    };",
              "  }, []);", "",
              "  useEffect(() => {",
              "    let cancelled = false;",
              "    setError(null);",
              "    getConnectorsClient()",
              "      .then(async (client) => {",
              "        const data = client.connectors" + _acc(chosen["connector"]) + ";",
              "        const w = await readWheres(data, filters);",
              "        const [k, c] = await Promise.all([readKpis(data, filters, w), readCharts(data, filters, w)]);",
              "        if (!cancelled) {", "          setKpis(k);", "          setCharts(c);", "        }",
              "      })",
              "      .catch((e: unknown) => {", "        if (!cancelled) setError(e instanceof Error ? e.message : String(e));", "      });",
              "    return () => {", "      cancelled = true;", "    };",
              "  }, [filters]);", "",
              "  return (",
              "    <>"]
    if filters:
        lines += ["      {FILTERS.length > 0 && (",
                  "        <Section title=\"Filters\" hideTitle>",
                  "          <div className=\"kg-filters\">",
                  "            {FILTERS.map((x) => {",
                  "              const v = filters[x.key];",
                  "              return Array.isArray(v) ? (",
                  "                <MultiSelect key={x.key} label={x.label} options={values[x.key] ?? []} selected={v}",
                  "                  onChange={(next) => setFilters({ ...filters, [x.key]: next })} />",
                  "              ) : (",
                  "                <DateRange key={x.key} label={x.label} value={v} onChange={(next) => setFilters({ ...filters, [x.key]: next })} />",
                  "              );",
                  "            })}",
                  "            <button type=\"button\" className=\"kg-button\" onClick={() => setFilters(NO_FILTERS)}>",
                  "              Clear filters",
                  "            </button>",
                  "          </div>",
                  "        </Section>",
                  "      )}"]
    lines += ["      <Status error={error} loading={!error && kpis === null} what=\"the figures\" />"]
    if kpis:
        lines += ["      <Section title=\"Key figures\" hideTitle>",
                  "        <div className=\"kg-cards\">",
                  "          {(kpis ?? []).map((k) => (",
                  "            <KpiCard key={k.id} label={k.label} value={k.value} unit={k.unit} note={k.note} />",
                  "          ))}",
                  "        </div>",
                  "      </Section>"]
    if charts:
        lines += ["      <Section title=\"Charts\" hideTitle>",
                  "        <div className=\"kg-charts\">",
                  "          {(charts ?? []).map((c) => (",
                  "            <ChartView key={c.id} chart={c} />",
                  "          ))}",
                  "        </div>",
                  "      </Section>"]
    lines += ["    </>", "  );", "}", "", "export default OverviewPage;"]
    return "\n".join(lines) + "\n"


def list_tsx(plan: Plan, t, personal: dict) -> str:
    """src/pages/<Class>ListPage.tsx: one table's rows, sortable by any column shown, searchable in its text columns,
    a page of PAGE_SIZE rows at a time (the connector's cursor paging)."""
    from .rayfin import PAGE_COLUMNS, _order_column, _shown
    cls = class_name(t.name)
    shown = _shown(t, personal)
    order = _order_column(t, plan, shown)
    cols = shown[:PAGE_COLUMNS]
    if order and order not in cols:
        cols = [order] + cols[:PAGE_COLUMNS - 1]
    types = {c.name: rayfin_type(c.data_type)[0] for c in t.columns}
    text_cols = [c for c in cols if types[c] == "text"]
    left = [c.name for c in t.columns if (t.name, c.name) in personal]
    count = _count_column(plan, t)
    lines = [HEADER.format(path=f"src/pages/{cls}ListPage.tsx").rstrip("\n"), EDIT_NOTE.rstrip("\n")]
    if left:
        lines.append(f"// Left out, they look like personal data by name (Krusgraph's privacy rules): {', '.join(left)}.")
    lines += ["import { useEffect, useState } from 'react';", "",
              "import { DataTable, SearchBox, Section, Status } from '../components/kg-ui';",
              "import type { Sort } from '../components/kg-ui';",
              "import { getConnectorsClient } from '../lib/app-connectors';",
              "import { PAGE_SIZE } from '../lib/app-config';",
              "import type { Data } from '../lib/app-data';", "",
              "const COLUMNS = [" + ", ".join(f"'{prop_name(c)}'" for c in cols) + "] as const;",
              "const HEADINGS = [",
              *[f"  {{ key: '{prop_name(c)}', label: {_ts(c)}, numeric: {'true' if types[c] in ('int', 'decimal') else 'false'} }}," for c in cols],
              "] as const;",
              f"const DEFAULT_SORT: Sort | null = {('{ column: ' + repr(prop_name(order)) + ', dir: ' + chr(39) + 'desc' + chr(39) + ' }') if order else 'null'};", "",
              f"type OrderBy = Parameters<Data['{cls}']['orderBy']>[0];",
              f"type Where = Parameters<Data['{cls}']['where']>[0];", "",
              "function searchWhere(q: string): Where {"]
    if text_cols:
        conds = [f"{{ {prop_name(c)}: {{ contains: q }} }}" for c in text_cols]
        lines.append(f"  return {conds[0]};" if len(conds) == 1 else f"  return {{ or: [{', '.join(conds)}] }};")
    else:
        lines += ["  void q;", "  return {};"]
    lines += ["}", "",
              f"async function readPage(data: Data, q: string, sort: Sort | null, after: string | null) {{",
              f"  let query = data.{cls}.select([...COLUMNS]).where(q ? searchWhere(q) : {{}});",
              "  if (sort) query = query.orderBy({ [sort.column]: sort.dir } as OrderBy);",
              "  query = query.first(PAGE_SIZE);",
              "  if (after) query = query.after(after);",
              "  return query.executePaginated();",
              "}", ""]
    if count:
        lines += ["async function readCount(data: Data, q: string): Promise<number | null> {",
                  f"  const rows = await data.{cls}.where(q ? searchWhere(q) : {{}}).aggregate({{ n: {{ count: '{prop_name(count)}' }} }}).execute();",
                  "  return rows[0]?.aggregations.n ?? null;",
                  "}", ""]
    lines += [f"export function {cls}ListPage() {{",
              "  const [q, setQ] = useState('');",
              "  const [sort, setSort] = useState<Sort | null>(DEFAULT_SORT);",
              "  const [cursors, setCursors] = useState<(string | null)[]>([null]);",
              "  const [page, setPage] = useState<{ rows: Record<string, unknown>[]; next: string | null } | null>(null);",
              "  const [total, setTotal] = useState<number | null>(null);",
              "  const [error, setError] = useState<string | null>(null);",
              "  const after = cursors[cursors.length - 1];", "",
              "  useEffect(() => {",
              "    let cancelled = false;",
              "    setError(null);",
              "    getConnectorsClient()",
              "      .then((client) => readPage(client.connectors" + "@@ACC@@" + ", q, sort, after))",
              "      .then((r) => {",
              "        if (!cancelled) setPage({ rows: r.items as Record<string, unknown>[], next: r.hasNextPage ? (r.endCursor ?? null) : null });",
              "      })",
              "      .catch((e: unknown) => {", "        if (!cancelled) setError(e instanceof Error ? e.message : String(e));", "      });",
              "    return () => {", "      cancelled = true;", "    };",
              "  }, [q, sort, after]);", ""]
    if count:
        lines += ["  useEffect(() => {",
                  "    let cancelled = false;",
                  "    getConnectorsClient()",
                  "      .then((client) => readCount(client.connectors" + "@@ACC@@" + ", q))",
                  "      .then((n) => {", "        if (!cancelled) setTotal(n);", "      })",
                  "      .catch(() => undefined);",
                  "    return () => {", "      cancelled = true;", "    };",
                  "  }, [q]);", ""]
    else:
        lines += ["  void setTotal;", ""]
    lines += ["  const restart = () => setCursors([null]);",
              "  return (",
              f"    <Section title={_ts(t.name)}>",
              "      <div className=\"kg-card\">",
              "        <div className=\"kg-toolbar\">"]
    if text_cols:
        lines += [f"          <SearchBox label={_ts('Search ' + ', '.join(text_cols))} onSearch={{(v) => {{ setQ(v); restart(); }}}} />"]
    lines += ["          <span className=\"kg-note\" aria-live=\"polite\">",
              "            {total === null ? '' : `${total.toLocaleString()} rows`}",
              "            {q ? ` matching “${q}”` : ''}",
              "          </span>",
              "        </div>",
              "        <Status error={error} loading={!error && page === null} what=\"the rows\" />",
              "        {page && (",
              f"          <DataTable caption={_ts(t.name + ', page ')} columns={{HEADINGS}} rows={{page.rows}} sort={{sort}}",
              "            onSort={(s) => { setSort(s); restart(); }} />",
              "        )}",
              "        {page && page.rows.length === 0 && <p className=\"kg-empty\">No rows.</p>}",
              "        <nav className=\"kg-pager\" aria-label=\"Pages of rows\">",
              "          <button type=\"button\" className=\"kg-button\" disabled={cursors.length <= 1} onClick={() => setCursors(cursors.slice(0, -1))}>",
              "            Previous",
              "          </button>",
              "          <span>Page {cursors.length}</span>",
              "          <button type=\"button\" className=\"kg-button\" disabled={!page?.next} onClick={() => page?.next && setCursors([...cursors, page.next])}>",
              "            Next",
              "          </button>",
              "        </nav>",
              "      </div>",
              "    </Section>",
              "  );",
              "}", "", f"export default {cls}ListPage;"]
    return "\n".join(lines) + "\n"


def config_ts(title: str, chosen: dict, pages: list[dict]) -> str:
    return "\n".join([HEADER.format(path="src/lib/app-config.ts").rstrip("\n"), EDIT_NOTE.rstrip("\n"),
                      "// The choices made in the Krusgraph Model item's App card. Change them here, or in the card and download again.",
                      f"export const APP_TITLE = {_ts(title)};",
                      f"/** One of {', '.join(ACCENTS)} (src/krusgraph-app.css). */",
                      f"export const ACCENT = {_ts(chosen['accent'])};",
                      f"/** The pages, in this order. */",
                      "export const PAGE_ORDER = [" + ", ".join(_ts(p["id"]) for p in pages) + "] as const;",
                      f"/** Rows a filter or a chart reads of each lookup table (a link followed by keys). */",
                      f"export const LOOKUP_ROWS = {LOOKUP_ROWS};",
                      f"/** Rows a list page shows at a time. */",
                      f"export const PAGE_SIZE = {PAGE_SIZE};", ""])


def app_tsx(pages: list[dict], connector: str) -> str:
    imports = [f"import {{ {p['component']} }} from './pages/{p['component']}';" for p in pages]
    entries = [f"  {{ id: {_ts(p['id'])}, title: {_ts(p['title'])}, render: () => <{p['component']} /> }}," for p in pages]
    return "\n".join([HEADER.format(path="src/App.tsx").rstrip("\n"), EDIT_NOTE.rstrip("\n"),
                      "// It replaces the template's src/App.tsx; main.tsx renders it inside the template's sign-in and theme.",
                      "import { useEffect, useState } from 'react';", "",
                      "import { Header, Nav } from './components/kg-ui';",
                      "import { getConnectorsClient } from './lib/app-connectors';",
                      "import { ACCENT, APP_TITLE } from './lib/app-config';",
                      "import { readLastRefresh } from './lib/app-data';",
                      *imports,
                      "import './krusgraph-app.css';", "",
                      "const PAGES = [", *entries, "];", "",
                      "function when(d: Date): string {",
                      "  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });",
                      "}", "",
                      "export function App() {",
                      "  const [page, setPage] = useState(PAGES[0].id);",
                      "  const [round, setRound] = useState(0);",
                      "  const [loaded, setLoaded] = useState<Date | null>(null);",
                      "  const [readAt, setReadAt] = useState<Date | null>(null);",
                      "  const [busy, setBusy] = useState(true);",
                      "  const current = PAGES.find((p) => p.id === page) ?? PAGES[0];", "",
                      "  useEffect(() => {",
                      "    let cancelled = false;",
                      "    setBusy(true);",
                      "    getConnectorsClient()",
                      f"      .then((client) => readLastRefresh(client.connectors{_acc(connector)}))",
                      "      .then((d) => {", "        if (!cancelled) setLoaded(d);", "      })",
                      "      .catch(() => undefined)",
                      "      .finally(() => {",
                      "        if (!cancelled) {", "          setReadAt(new Date());", "          setBusy(false);", "        }",
                      "      });",
                      "    return () => {", "      cancelled = true;", "    };",
                      "  }, [round]);", "",
                      "  const refreshed = loaded",
                      "    ? `Last refresh ${when(loaded)}`",
                      "    : readAt",
                      "      ? `Data read ${when(readAt)}`",
                      "      : 'Reading the data…';",
                      "  return (",
                      "    <div className=\"kg-app\" data-accent={ACCENT}>",
                      "      <a className=\"kg-skip\" href=\"#kg-main\">",
                      "        Skip to the content",
                      "      </a>",
                      "      <div className=\"kg-accent-bar\" />",
                      "      <Header title={APP_TITLE} refreshed={refreshed} busy={busy} onRefresh={() => setRound(round + 1)} />",
                      "      <Nav pages={PAGES} current={current.id} onSelect={setPage} />",
                      "      <main id=\"kg-main\" className=\"kg-main\" key={`${current.id}-${round}`} tabIndex={-1}>",
                      "        {current.render()}",
                      "      </main>",
                      "      <footer className=\"kg-footer\">",
                      "        A Fabric App (Rayfin, preview) generated by Krusgraph from the reviewed plan. Read-only: it reads, it never writes.",
                      "      </footer>",
                      "    </div>",
                      "  );",
                      "}", "", "export default App;"]) + "\n"


def api_summary(plan: Plan, connector: str, source_type: str) -> dict:
    """The connector's GraphQL API as the dry run shows it: read-only (no mutation types), every link the review kept.
    The per-type actions are those of graphql.definition with writable false (the API for GraphQL definition's
    `actions`, learn.microsoft.com/rest/api/fabric/articles/item-management/definitions/graphql-api-definition)."""
    from . import graphql
    env = graphql.definition(plan, "app_api", "00000000-0000-0000-0000-000000000000", "00000000-0000-0000-0000-000000000000",
                             source_type if source_type in graphql.SOURCE_TYPES else "SqlAnalyticsEndpoint", writable=False)
    objects = graphql.decode(env)["datasources"][0]["objects"]
    types = [{"type": o["graphqlType"], "queries": [a for a, v in o["actions"].items() if v == "Enabled"]} for o in objects]
    mutations = sorted({a for o in objects for a, v in o["actions"].items() if v == "Enabled" and a not in ("Query", "Query_by_pk")})
    links = [{"from": f"{r.source}.{'+'.join(r.source_cols)}", "to": f"{r.target}.{'+'.join(r.target_cols)}", "rule": r.rule}
             for r in plan.relationships if r.target in plan.keys]
    return {"connector": connector, "connector_type": CONNECTOR_TYPES[source_type], "operations": list(READ_ONLY),
            "read_only": not mutations, "mutations": mutations, "types": types, "links": links,
            "note": "Rayfin's connector apply (rayfin up) makes the GraphQL API from the connector's entities. `operations: "
                    "['read']` in schema.ts and in the app's wiring allows queries only, and every link below is an @one/@many "
                    "on the entities, so the API carries it."}


def package(plan: Plan, chosen: dict, source_type: str = "SqlAnalyticsEndpoint", connector: str | None = None,
            title: str | None = None) -> dict:
    """{files, pages, connector, design}: the package for the `dataapp` template. The connector covers every table and
    every link (read-only); the pages show only what was ticked, in the chosen order, with the chosen filters, chart
    types and accent."""
    connector = connector or _connector_name(getattr(plan.schema, "schema", "data"))
    title = title or getattr(plan.schema, "schema", None) or "Data app"
    base = rayfin_files(plan, connector, source_type, operations=READ_ONLY)
    files = {p: t for p, t in base.items() if not p.startswith("src/")}
    files[WIRING] = base["src/lib/connectors.ts"].replace("// src/lib/connectors.ts", f"// {WIRING}", 1)
    personal = privacy.personal_columns(plan.schema, [t.name for t in plan.schema])
    chosen = {**chosen, "connector": connector}
    refresh = _refresh_column(plan, chosen, personal)
    data, reached = data_ts(plan, connector, chosen, refresh)
    files["src/lib/app-data.ts"] = data
    files["src/components/kg-ui.tsx"] = UI_TSX
    files["src/krusgraph-app.css"] = ui_css()
    by_id = {}
    if chosen["kpis"] or chosen["charts"]:
        files["src/pages/OverviewPage.tsx"] = overview_tsx(plan, chosen, reached)
        shows = [f"key figure {k['label']} ({k['unit']})" for k in chosen["kpis"]]
        shows += [f"{chosen['chart_types'][c['id']]} chart {c['label']}" for c in chosen["charts"]]
        shows += [f"filter {f['label']}" for f in chosen["filters"]]
        by_id[OVERVIEW] = {"id": OVERVIEW, "title": "Overview", "component": "OverviewPage", "shows": shows}
    for o in chosen["tables"]:
        t = plan.schema[o["table"]]
        cls = class_name(t.name)
        files[f"src/pages/{cls}ListPage.tsx"] = list_tsx(plan, t, personal).replace("@@ACC@@", _acc(connector))
        by_id[o["id"]] = {"id": o["id"], "title": t.name, "component": f"{cls}ListPage",
                          "shows": [f"the rows of {t.name}: sort, search, {PAGE_SIZE} a page"]}
    pages = [by_id[i] for i in chosen["page_order"] if i in by_id]
    files["src/lib/app-config.ts"] = config_ts(title, chosen, pages)
    files["src/App.tsx"] = app_tsx(pages, connector)
    assert RAYFIN_TSCONFIG_PATH in files
    design = {"accent": chosen["accent"], "accent_colours": dict(zip(("light", "dark"), ACCENTS[chosen["accent"]])),
              "page_order": [p["title"] for p in pages],
              "charts": [{"id": c["id"], "label": c["label"], "type": chosen["chart_types"][c["id"]]} for c in chosen["charts"]],
              "filters": [{"id": f["id"], "label": f["label"], "kind": f["kind"],
                           "reaches": sorted(t for t, ks in reached.items() if _fkey(f) in ks)} for f in chosen["filters"]],
              "last_refresh": f"{refresh[0]}.{refresh[1]}" if refresh else None,
              "look": "Fluent-like: Segoe UI, neutral greys, one accent; light and dark; 375 px and up; labels, contrast, keyboard"}
    return {"files": files, "pages": pages, "connector": connector, "design": design}


def commands(connector: str, connector_type: str, workspace: str, workspace_id: str, source_item_id: str, app_name: str) -> list[dict]:
    """The commands that publish the package, with the workspace filled in (Learn, fabric/apps/connectors, and the
    package's own README). `rayfin up` looks the App item up by name in the workspace (rayfin-cli 1.36.2, observed)."""
    return [
        {"step": "Create the project (once)", "command": f"npm create @microsoft/rayfin@latest -- {app_name} --template dataapp --workspace \"{workspace}\""},
        {"step": "Sign in", "command": "npx rayfin login"},
        {"step": "Add the read-only connector", "command": f"npx rayfin connector add --type {connector_type} --workspace-id {workspace_id} "
                                                            f"--item-id {source_item_id} --name {connector} --operations read"},
        {"step": "Unzip the package into the project, then publish", "command": f"npx rayfin up --workspace \"{workspace}\""},
    ]


TYPECHECK = "tsc -p rayfin/tsconfig.json --noEmit && tsc --noEmit"
TYPECHECK_SETUP = f"npm pkg set scripts.typecheck=\"{TYPECHECK}\""
PROMPT_TEMPLATE = ("Add a chart of <measure> by <dimension> on the <page> page; keep queries read-only; "
                   "run npm run typecheck")


def edit_with_ai(name: str, workspace: str, pages: list[dict], connector: str) -> str:
    """EDIT-WITH-AI.md: how to change the generated app with Claude (with Krusgraph for Claude), VS Code or Lovable, a
    prompt to start from, the rules, and how to publish again."""
    page_list = "\n".join(f"- {p['title']} (`src/pages/{p['component']}.tsx`)" for p in pages)
    return f"""# Change {name} yourself: with Claude, VS Code or Lovable

This app was generated by Krusgraph from the reviewed plan. It is plain React and TypeScript in the Rayfin `dataapp`
template, so you can change the pages, the charts and the look yourself, with or without AI. Fabric Apps and Rayfin
are in preview.

## Where things are

{page_list}
- `src/App.tsx`: the header (title, last refresh), the page tabs and their order
- `src/lib/app-config.ts`: the title, the accent colour, the page order, rows per page
- `src/lib/app-data.ts`: the filters and every query the cards and charts run (read-only)
- `src/components/kg-ui.tsx`: cards, bar and line charts, tables, filter controls
- `src/krusgraph-app.css`: colours, spacing and type, light and dark
- `rayfin/connectors/{connector}/`: the read-only connector (one entity per table, every link of the plan)

## Once: the type check

Run this once in the project, so `npm run typecheck` checks the app and the connector:

```
{TYPECHECK_SETUP}
npm run typecheck
```

## Open it in Claude

1. Connect Krusgraph for Claude: <https://krusgraph.com/mcp/connect>. Claude can then read the plan, the tables and
   the links behind this app, and answer questions about the data.
2. Open the project folder in Claude Code (`claude` in the project folder), or attach the folder in the Claude app.
3. Paste the prompt below, filled in.

## Open it in VS Code

1. Open the project folder (`code .`).
2. Use the chat of your choice (GitHub Copilot, or Claude Code in VS Code) with the prompt below, or edit by hand:
   the files above are short and commented.
3. `npm run dev` shows the app locally after `npx rayfin login`.

## Open it in Lovable

1. Push the project to a GitHub repository (it holds no secrets: see the rules).
2. In Lovable, import the repository and give it the prompt below.
3. Pull Lovable's changes back, run `npm run typecheck`, and publish with `npx rayfin up` from your machine or Azure
   Cloud Shell: Lovable does not publish to Fabric.

## A prompt to start from

```
{PROMPT_TEMPLATE}
```

For example: "Add a chart of Total quantity by products (name) on the Overview page; keep queries read-only; run npm
run typecheck". More ideas: "Show the key figures as a row of four on wide screens", "Add a filter by product
category to the list page of order_items", "Use the teal accent".

## The rules

- **Read-only.** Read through `getConnectorsClient()` and the connector `{connector}` only: `select`, `where`,
  `orderBy`, `first`, `after`, `groupBy`, `aggregate`, `execute`. Never `create`, `update` or `delete`, and keep
  `operations: ['read']` in `rayfin/connectors/{connector}/schema.ts` and `src/lib/app-connectors.ts`.
- **No secrets in code.** No keys, tokens, passwords or connection strings in any file; `rayfin up` and the sign-in
  take care of access. No calls to other web addresses.
- **Keep the type check green.** `npm run typecheck` passes before every publish.
- **Personal data stays out.** Columns that look like personal data by name were left out of the pages; do not add
  them back without asking whoever owns the data.

## Publish again

```
npx rayfin login
npm run typecheck
npx rayfin up --workspace "{workspace}"
```

`rayfin up` publishes into the App item of the same name; run it from your machine or Azure Cloud Shell.
"""


def readme(name: str, pages: list[dict], api: dict, cmds: list[dict], why: str, design: dict | None = None) -> str:
    rows = "\n".join(f"- {p['title']}: {', '.join(p['shows'])}" for p in pages)
    steps = "\n".join(f"{i}. {c['step']}: `{c['command']}`" for i, c in enumerate(cmds, 1))
    links = "\n".join(f"- {l['from']} → {l['to']} ({l['rule']})" for l in api["links"])
    look = ""
    if design:
        look = (f"\n## Look\n\nAccent {design['accent']} ({design['accent_colours']['light']} light, "
                f"{design['accent_colours']['dark']} dark). {design['look']}. Last refresh: "
                f"{design['last_refresh'] or 'when the page read the data (the plan has no load-time column)'}.\n")
    return f"""# {name}: App (Rayfin, preview), generated by Krusgraph

Fabric Apps and Rayfin are in preview. This package was generated from the reviewed plan; it has not been run in your
tenant. To change it yourself, with Claude, VS Code or Lovable, see EDIT-WITH-AI.md.

## Pages

{rows}
{look}
## The connector `{api['connector']}` (`{api['connector_type']}`)

Read-only: `operations: ['read']`; the GraphQL API it gets has queries only, no mutations. Links:

{links}

## Publish

{why}

{steps}

Unzip at the project's root: it replaces `src/App.tsx`, adds `{WIRING}`, the pages, `src/lib/app-data.ts`,
`src/lib/app-config.ts`, `src/components/kg-ui.tsx` and `src/krusgraph-app.css`, and brings `rayfin/tsconfig.json`
(the `dataapp` template's own; `rayfin up` compiles the connector with it). Check first with
`npx tsc -p rayfin/tsconfig.json --noEmit` and `npx tsc --noEmit`.

If `rayfin up` answers 403 "The feature is not available", a Fabric administrator turns on "{SETTING_TITLE}" (Admin
portal → Tenant settings → Microsoft Fabric).
"""


def zip_b64(files: dict[str, str]) -> str:
    import base64
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(files):
            z.writestr(p, files[p])
    return base64.b64encode(buf.getvalue()).decode()


# ------------------------------------------------------------------ preflight -------------------------------------

def _setting(settings: list[dict]) -> dict | None:
    for s in settings:
        if s.get("settingName") in SETTING_NAMES or str(s.get("title", "")).strip().lower().startswith("enable fabric app items"):
            return s
    return None


def off_card(reason: str) -> dict:
    return {"error": f"Fabric App items are turned off for your organisation, so no app can be published; nothing was created. {reason}",
            "kind": "feature_disabled", "setting": SETTING_TITLE, "where": "Admin portal → Tenant settings → Microsoft Fabric",
            "admin_steps": list(ADMIN_STEPS),
            "hint": f"A Fabric administrator turns on \"{SETTING_TITLE}\"; the steps are below. Your own permissions are not the problem."}


def preflight(headers: dict, scopes: set[str] | None) -> dict:
    """Is "Enable Fabric App Items (preview)" on? status on, off (the card; stop), or unknown (the setting is readable only
    by a Fabric administrator with Tenant.Read.All; then Create's own call says it, mapped to the same card)."""
    from .deploy import FABRIC, send
    unknown = {"status": "unknown", "setting": SETTING_TITLE,
               "note": f"Only a Fabric administrator can read the tenant setting \"{SETTING_TITLE}\" (List Tenant Settings, "
                       "Tenant.Read.All). If it is off, Create's first call is refused and this card says so; nothing else "
                       "is tried."}
    if scopes is not None and not set(SETTINGS_SCOPES) & scopes:
        return {**unknown, "reason": "your sign-in does not carry Tenant.Read.All"}
    try:
        r = send("get", f"{FABRIC}/v1/admin/tenantsettings", headers, write=False, timeout=30)
    except Exception as exc:  # noqa: BLE001
        return {**unknown, "reason": type(exc).__name__}
    status = getattr(r, "status_code", 0)
    if status in (401, 403):
        return {**unknown, "reason": f"Fabric answered HTTP {status}: not a Fabric administrator"}
    if status >= 400:
        return {**unknown, "reason": f"Fabric answered HTTP {status}"}
    s = _setting((r.json() or {}).get("tenantSettings") or [])
    if s is None:
        return {**unknown, "reason": "the setting is not in the tenant's list"}
    if not s.get("enabled"):
        return {"status": "off", **off_card("The tenant setting is off.")}
    groups = [g.get("name") for g in s.get("enabledSecurityGroups") or [] if g.get("name")]
    return {"status": "on", "setting": SETTING_TITLE,
            "note": "On for the organisation." if not groups else f"On for the security groups {', '.join(groups)}: who publishes must be in one."}


def feature_disabled(status: int, body) -> bool:
    """The 403 of a turned-off App items setting ("The feature is not available", FeatureNotAvailable), as opposed to a
    missing permission or role."""
    text = json.dumps(body) if not isinstance(body, str) else body
    return status == 403 and bool(re.search(r"feature is not available|FeatureNotAvailable|FeatureDisabled", text, re.I))



# ------------------------------------------------------------------ the output, as the editor and the MCP tool see it --

def source_type_of(item_kind: str) -> str:
    return {"Warehouse": "Warehouse", "SQLDatabase": "SqlDbNative"}.get(item_kind, "SqlAnalyticsEndpoint")


def description(name: str) -> str:
    return f"Created by Krusgraph: App (Rayfin, preview) {name}; its pages are published with rayfin up."


def first_check(headers: dict, scopes: set[str] | None, dry_run: bool) -> tuple[dict, dict | None]:
    """The preflight, before the source is read: (preflight, the off card's answer or None)."""
    pre = preflight(headers, scopes)
    if pre["status"] != "off":
        return pre, None
    return pre, {**{k: v for k, v in pre.items() if k != "status"}, "preflight": {"status": "off", "setting": SETTING_TITLE},
                 "dry_run": dry_run, "label": LABEL}


def answer(p: Plan, info: dict, headers: dict, name: str, choices: dict | None, dry_run: bool, scopes: set[str] | None,
           workspace_label: str, create=None, pre: dict | None = None, title: str | None = None) -> dict:
    """The App output: the preflight before anything else (off: the card, and nothing more), the choices, the pages, the
    read-only connector and its API, the package and the commands; with dry_run false, the App item made by the
    documented call (`create`: a function of (url, body) -> write_and_wait's answer; None in the MCP tool)."""
    from .deploy import FABRIC, sql_endpoint_id_for_lakehouse
    pre = pre or preflight(headers, scopes)
    if pre["status"] == "off":
        return {**{k: v for k, v in pre.items() if k != "status"}, "preflight": {"status": "off", "setting": SETTING_TITLE},
                "dry_run": dry_run, "label": LABEL}
    opts = options(p)
    try:
        chosen = resolve(opts, choices)
    except ValueError as e:
        return {"error": str(e), "kind": "bad_input",
                "hint": "Tick at least one key figure, list page or chart; chart types, page order and accent from the options.",
                "options": opts}
    st = source_type_of(info.get("item_kind", "Lakehouse"))
    source_item = info.get("item_id") or "<source item id>"
    if info.get("item_kind", "Lakehouse") == "Lakehouse" and info.get("item_id"):
        try:
            source_item = sql_endpoint_id_for_lakehouse(info["workspace_id"], info["item_id"], headers)
        except Exception:  # noqa: BLE001 — the command shows the placeholder instead
            source_item = "<the lakehouse's SQL analytics endpoint id>"
    pkg = package(p, chosen, st, title=title or name)
    api = api_summary(p, pkg["connector"], st)
    cmds = commands(pkg["connector"], CONNECTOR_TYPES[st], workspace_label, info.get("workspace_id", ""), source_item, name)
    edit = edit_with_ai(name, workspace_label, pkg["pages"], pkg["connector"])
    files = {**pkg["files"], "KRUSGRAPH-APP.md": readme(name, pkg["pages"], api, cmds, NOT_PUBLISHED_WHY, pkg["design"]),
             EDIT_WITH_AI: edit}
    out = {"dry_run": dry_run, "label": LABEL, "preview": True, "preflight": pre, "options": opts,
           "chosen": chosen_ids(chosen), "gone": chosen["gone"], "design": pkg["design"],
           "pages": pkg["pages"], "api": api, "files": sorted(files), "commands": cmds, "published": False,
           "edit_yourself": {"title": EDIT_TITLE, "file": EDIT_WITH_AI, "markdown": edit, "prompt": PROMPT_TEMPLATE,
                             "ways": ["Claude, with Krusgraph for Claude (https://krusgraph.com/mcp/connect)", "VS Code", "Lovable"],
                             "publish_again": "npx rayfin up"},
           "why_not_published": NOT_PUBLISHED_WHY,
           "package": {"filename": f"{name}_rayfin_app.zip", "zip_base64": zip_b64(files)},
           "item": {"type": ITEM_TYPE, "name": name, "rest": {"method": "POST", "path": "/v1/workspaces/{workspaceId}/appBackends",
                                                              "delegated_scope": APP_SCOPE, "spec": "learn.microsoft.com/rest/api/fabric/appbackend/items/create-app-backend"}},
           "portal_steps": [f"{c['step']}: {c['command']}" for c in cmds]}
    if dry_run or create is None:
        out["note"] = ("Nothing was created or changed in Fabric. Create makes the App item (empty, preview) with Microsoft's documented "
                       "call; the package and the commands publish the pages into it.")
        return out
    res = create(f"{FABRIC}/v1/workspaces/{info['workspace_id']}/appBackends", {"displayName": name, "description": description(name)})
    if res.get("status") == "Failed":
        body = res.get("body") or ""
        if feature_disabled(int(res.get("http") or 0), body):
            return {**off_card("Fabric refused to create the App item: \"The feature is not available\"."),
                    "preflight": {"status": "off", "setting": SETTING_TITLE}, "dry_run": False, "label": LABEL}
        from .errors import classify_http
        out.update(classify_http(int(res.get("http") or 400), body, f"creating the App item {name!r}"))
        res = {k: v for k, v in res.items() if k != "body"}
    elif res.get("status") == "Timeout":
        out.update({"error": f"Fabric is still working on the App item {name!r}.", "kind": "timeout",
                    "hint": "Check the workspace in a minute; choose Create again and an App item Krusgraph made is shown as built."})
    out["result"] = res
    return out
