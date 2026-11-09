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
from .rayfin import (CONNECTOR_TYPES, RAYFIN_TSCONFIG_PATH, READ_ONLY, class_name, page_tsx, prop_name, rayfin_files,
                     rayfin_type)

LABEL = "App (Rayfin, preview)"
ITEM_TYPE = "AppBackend"                       # the documented item type; the portal shows it as "App"
APP_SCOPE = "Item.ReadWrite.All"               # Create App Backend's only delegated scope
SETTINGS_SCOPES = ("Tenant.Read.All", "Tenant.ReadWrite.All")
SETTING_TITLE = "Enable Fabric App Items (preview)"
SETTING_NAMES = ("AppBackendTenant",)          # seen in the founder's run; not documented
LOOKUP_ROWS = 1000                             # rows a chart reads of each lookup table
WIRING = "src/lib/app-connectors.ts"           # beside the template's own src/lib/connectors.ts, which stays as it is
MAX_DEFAULT_CHARTS = 2

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


def options(plan: Plan) -> dict:
    """Every key figure, list page and chart the app can show, each with a default and the rule that made it."""
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
        kpis.append({"id": f"rows:{t.name}", "label": f"Rows in {t.name}", "table": t.name, "op": "count", "column": col,
                     "default": fact and t.name in plan.keys,
                     "why": ("COUNTROWS in the semantic model draft (a fact table)" if fact else "the table's row count")
                            + ("" if col in plan.keys.get(t.name, ([], ""))[0] else f"; counts rows where {col} is set")})
    for m in measures:
        if m.get("column"):
            kpis.append({"id": f"sum:{m['table']}.{m['column']}", "label": m["name"], "table": m["table"], "op": "sum",
                         "column": m["column"], "default": True, "why": f"{m['expression']} in the semantic model draft"})
    main = (fact_tables(plan) or [None])[0]
    linked = {r.target for r in single if r.source == main}
    for t in plan.schema:
        keyed_fact = role_of.get(t.name) == "fact" and t.name in plan.keys
        tables.append({"id": f"table:{t.name}", "label": t.name, "table": t.name,
                       "default": keyed_fact or t.name in linked,
                       "why": "a fact table with a key" if keyed_fact else (f"{main} links to it" if t.name in linked else "a table of the plan")})
    out_of = {}
    for r in single:
        out_of.setdefault(r.source, []).append(r)
    for m in measures:
        if not m.get("column"):
            continue
        fact = m["table"]
        paths = [[r] for r in out_of.get(fact, [])]
        paths += [[r, r2] for r in out_of.get(fact, []) for r2 in out_of.get(r.target, []) if r2.target != fact]
        for path in paths:
            end = plan.schema[path[-1].target]
            label = _label_column(plan, end, personal)
            if label is None:
                continue
            via = " → ".join(f"{r.source}.{r.source_cols[0]}" for r in path)
            charts.append({"id": f"chart:{fact}.{m['column']}:" + ">".join(f"{r.source}.{r.source_cols[0]}" for r in path),
                           "label": f"{m['name']} by {end.name} ({label})", "fact": fact, "measure": m["column"],
                           "path": [{"source": r.source, "column": r.source_cols[0], "target": r.target,
                                     "target_column": r.target_cols[0], "rule": r.rule} for r in path],
                           "label_table": end.name, "label_column": label, "leaf": end.name not in out_of,
                           "default": False, "why": f"{via} → {end.name}.{label}: a link of the plan ({', '.join(r.rule for r in path)})"})
    for c in [c for c in charts if c["leaf"]][:MAX_DEFAULT_CHARTS]:
        c["default"] = True
    return {"kpis": kpis, "tables": tables, "charts": charts, "left_out": left_out}


def defaults(opts: dict) -> dict:
    return {k: [o["id"] for o in opts[k] if o["default"]] for k in ("kpis", "tables", "charts")}


def resolve(opts: dict, choices: dict | None) -> dict:
    """The ticked options (choices: {kpis, tables, charts} as lists of ids; None: the defaults). An id the plan does not
    offer any more (the review changed) is listed under `gone`, never guessed."""
    choices = defaults(opts) if choices is None else choices
    out, gone = {}, []
    for k in ("kpis", "tables", "charts"):
        ids = choices.get(k) or []
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise ValueError(f"app.{k} must be a list of option ids")
        by_id = {o["id"]: o for o in opts[k]}
        out[k] = [by_id[i] for i in ids if i in by_id]
        gone += [i for i in ids if i not in by_id]
    if not (out["kpis"] or out["tables"] or out["charts"]):
        raise ValueError("tick at least one key figure, list page or chart for the app")
    out["gone"] = gone
    return out


# ------------------------------------------------------------------ the pages -------------------------------------

def _connector_name(schema: str) -> str:
    n = re.sub(r"[^a-z0-9]+", "-", (schema or "data").lower()).strip("-")
    return n if n and n[0].isalpha() else f"data-{n}" if n else "data"


def _acc(name: str) -> str:
    return f".{name}" if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name) else f"['{name}']"


def _ts(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


HEADER = "// {path} — generated by Krusgraph (App, Rayfin preview) from the reviewed plan. Read-only: queries only.\n"


def kpis_tsx(connector: str, kpis: list[dict]) -> str:
    lines = [HEADER.format(path="src/pages/KpisPage.tsx"),
             "import { useEffect, useState } from 'react';", "", "import { getConnectorsClient } from '../lib/app-connectors';", "",
             "type Kpi = { label: string; value: number | null };", "",
             "async function readKpis(): Promise<Kpi[]> {",
             f"  const data = (await getConnectorsClient()).connectors{_acc(connector)};",
             "  const out: Kpi[] = [];"]
    for k in kpis:
        lines += ["  {",
                  f"    const rows = await data.{class_name(k['table'])}.aggregate({{ value: {{ {k['op']}: '{prop_name(k['column'])}' }} }}).execute();",
                  f"    out.push({{ label: {_ts(k['label'])}, value: rows[0]?.aggregations.value ?? null }});",
                  "  }"]
    lines += ["  return out;", "}", "",
              "export function KpisPage() {",
              "  const [kpis, setKpis] = useState<Kpi[] | null>(null);",
              "  const [error, setError] = useState<string | null>(null);",
              "  useEffect(() => {",
              "    let cancelled = false;",
              "    readKpis()",
              "      .then((k) => {", "        if (!cancelled) setKpis(k);", "      })",
              "      .catch((e: unknown) => {", "        if (!cancelled) setError(e instanceof Error ? e.message : String(e));", "      });",
              "    return () => {", "      cancelled = true;", "    };",
              "  }, []);",
              "  return (",
              "    <section className=\"p-6\">",
              "      <h1 className=\"mb-4 text-xl font-semibold\">Key figures</h1>",
              "      {error && <p role=\"alert\">Could not read the figures: {error}</p>}",
              "      {!error && kpis === null && <p>Loading…</p>}",
              "      <div className=\"flex flex-wrap gap-4\">",
              "        {(kpis ?? []).map((k) => (",
              "          <div key={k.label} className=\"rounded border p-4\">",
              "            <div className=\"text-sm\">{k.label}</div>",
              "            <div className=\"text-2xl font-semibold\">{k.value === null ? '–' : k.value.toLocaleString()}</div>",
              "          </div>",
              "        ))}",
              "      </div>",
              "    </section>",
              "  );",
              "}", "", "export default KpisPage;"]
    return "\n".join(lines) + "\n"


def charts_tsx(connector: str, charts: list[dict], plan: Plan) -> str:
    lines = [HEADER.format(path="src/pages/ChartsPage.tsx"),
             "import { useEffect, useState } from 'react';", "", "import { getConnectorsClient } from '../lib/app-connectors';", "",
             "type Bar = { label: string; value: number };",
             "type Chart = { title: string; bars: Bar[] };", "",
             f"/** Rows read of each lookup table; a chart over more rows than this names the rest by their key. */",
             f"const LOOKUP_ROWS = {LOOKUP_ROWS};", "",
             "function lookup<R>(rows: readonly R[], key: (r: R) => unknown, value: (r: R) => unknown): Map<string, unknown> {",
             "  return new Map(rows.map((r) => [String(key(r)), value(r)] as [string, unknown]));",
             "}", "",
             "/** Sums the groups along the links (each hop a lookup) and names them by the last table's label. */",
             "function rollUp(groups: { key: unknown; value: number | null }[], hops: Map<string, unknown>[], labels: Map<string, unknown>): Bar[] {",
             "  const sums = new Map<string, number>();",
             "  for (const g of groups) {",
             "    let k: unknown = g.key;",
             "    for (const hop of hops) k = k === null || k === undefined ? undefined : hop.get(String(k));",
             "    const name = k === null || k === undefined ? '(none)' : String(labels.get(String(k)) ?? k);",
             "    sums.set(name, (sums.get(name) ?? 0) + (g.value ?? 0));",
             "  }",
             "  return [...sums].map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value);",
             "}", "",
             "async function readCharts(): Promise<Chart[]> {",
             f"  const data = (await getConnectorsClient()).connectors{_acc(connector)};",
             "  const out: Chart[] = [];"]
    for ch in charts:
        path = ch["path"]
        first = prop_name(path[0]["column"])
        lines += ["  {",
                  f"    // {ch['why']}",
                  f"    const grouped = await data.{class_name(ch['fact'])}.groupBy(['{first}']).aggregate({{ value: {{ sum: '{prop_name(ch['measure'])}' }} }}).execute();"]
        hops = []
        for i, step in enumerate(path[1:], 1):
            prev = path[i - 1]
            k, v = prop_name(prev["target_column"]), prop_name(step["column"])
            lines.append(f"    const hop{i} = await data.{class_name(step['source'])}.select(['{k}', '{v}']).first(LOOKUP_ROWS).execute();")
            hops.append(f"lookup(hop{i}, (r) => r.{k}, (r) => r.{v})")
        lk, lv = prop_name(path[-1]["target_column"]), prop_name(ch["label_column"])
        lines += [f"    const names = await data.{class_name(ch['label_table'])}.select(['{lk}', '{lv}']).first(LOOKUP_ROWS).execute();",
                  f"    out.push({{ title: {_ts(ch['label'])}, bars: rollUp(grouped.map((g) => ({{ key: g.fields.{first}, value: g.aggregations.value }})), "
                  f"[{', '.join(hops)}], lookup(names, (r) => r.{lk}, (r) => r.{lv})) }});",
                  "  }"]
    lines += ["  return out;", "}", "",
              "export function ChartsPage() {",
              "  const [charts, setCharts] = useState<Chart[] | null>(null);",
              "  const [error, setError] = useState<string | null>(null);",
              "  useEffect(() => {",
              "    let cancelled = false;",
              "    readCharts()",
              "      .then((c) => {", "        if (!cancelled) setCharts(c);", "      })",
              "      .catch((e: unknown) => {", "        if (!cancelled) setError(e instanceof Error ? e.message : String(e));", "      });",
              "    return () => {", "      cancelled = true;", "    };",
              "  }, []);",
              "  return (",
              "    <section className=\"p-6\">",
              "      {error && <p role=\"alert\">Could not read the charts: {error}</p>}",
              "      {!error && charts === null && <p>Loading…</p>}",
              "      {(charts ?? []).map((c) => {",
              "        const max = Math.max(1, ...c.bars.map((b) => b.value));",
              "        return (",
              "          <figure key={c.title} className=\"mb-6\">",
              "            <figcaption className=\"mb-2 font-semibold\">{c.title}</figcaption>",
              "            {c.bars.slice(0, 15).map((b) => (",
              "              <div key={b.label} className=\"flex items-center gap-2 text-sm\">",
              "                <span className=\"w-40 truncate\">{b.label}</span>",
              "                <span className=\"inline-block h-3 bg-current\" style={{ width: `${(b.value / max) * 60}%` }} />",
              "                <span>{b.value.toLocaleString()}</span>",
              "              </div>",
              "            ))}",
              "          </figure>",
              "        );",
              "      })}",
              "    </section>",
              "  );",
              "}", "", "export default ChartsPage;"]
    return "\n".join(lines) + "\n"


def app_tsx(pages: list[dict]) -> str:
    imports = [f"import {{ {p['component']} }} from './pages/{p['component']}';" for p in pages]
    entries = [f"  {{ id: {_ts(p['id'])}, title: {_ts(p['title'])}, render: () => <{p['component']} /> }}," for p in pages]
    return "\n".join([HEADER.format(path="src/App.tsx").rstrip("\n"),
                      "// It replaces the template's src/App.tsx; main.tsx renders it inside the template's sign-in.",
                      "import { useState } from 'react';", "", *imports, "",
                      "const PAGES = [", *entries, "];", "",
                      "export function App() {",
                      "  const [page, setPage] = useState(PAGES[0].id);",
                      "  const current = PAGES.find((p) => p.id === page) ?? PAGES[0];",
                      "  return (",
                      "    <main>",
                      "      <nav className=\"flex gap-2 border-b p-2\" aria-label=\"Pages\">",
                      "        {PAGES.map((p) => (",
                      "          <button key={p.id} type=\"button\" aria-current={p.id === page ? 'page' : undefined} onClick={() => setPage(p.id)}>",
                      "            {p.title}",
                      "          </button>",
                      "        ))}",
                      "      </nav>",
                      "      {current.render()}",
                      "      <p className=\"p-2 text-xs\">Preview: a Fabric App (Rayfin, preview) generated by Krusgraph. Read-only.</p>",
                      "    </main>",
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


def package(plan: Plan, chosen: dict, source_type: str = "SqlAnalyticsEndpoint", connector: str | None = None) -> dict:
    """{files, pages, connector}: the package for the `dataapp` template. The connector covers every table and every link
    (read-only); the pages show only what was ticked."""
    connector = connector or _connector_name(getattr(plan.schema, "schema", "data"))
    base = rayfin_files(plan, connector, source_type, operations=READ_ONLY)
    files = {p: t for p, t in base.items() if not p.startswith("src/")}
    files[WIRING] = base["src/lib/connectors.ts"].replace("// src/lib/connectors.ts", f"// {WIRING}", 1)
    personal = privacy.personal_columns(plan.schema, [t.name for t in plan.schema])
    pages = []
    if chosen["kpis"]:
        files["src/pages/KpisPage.tsx"] = kpis_tsx(connector, chosen["kpis"])
        pages.append({"id": "kpis", "title": "Key figures", "component": "KpisPage", "shows": [k["label"] for k in chosen["kpis"]]})
    if chosen["charts"]:
        files["src/pages/ChartsPage.tsx"] = charts_tsx(connector, chosen["charts"], plan)
        pages.append({"id": "charts", "title": "Charts", "component": "ChartsPage", "shows": [c["label"] for c in chosen["charts"]]})
    for o in chosen["tables"]:
        t = plan.schema[o["table"]]
        cls = class_name(t.name)
        files[f"src/pages/{cls}Page.tsx"] = page_tsx(connector, t, plan, personal).replace("from '../lib/connectors'", "from '../lib/app-connectors'")
        pages.append({"id": f"table-{t.name}", "title": t.name, "component": f"{cls}Page", "shows": [f"the latest rows of {t.name}"]})
    files["src/App.tsx"] = app_tsx(pages)
    assert RAYFIN_TSCONFIG_PATH in files
    return {"files": files, "pages": pages, "connector": connector}


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


def readme(name: str, pages: list[dict], api: dict, cmds: list[dict], why: str) -> str:
    rows = "\n".join(f"- {p['title']}: {', '.join(p['shows'])}" for p in pages)
    steps = "\n".join(f"{i}. {c['step']}: `{c['command']}`" for i, c in enumerate(cmds, 1))
    links = "\n".join(f"- {l['from']} → {l['to']} ({l['rule']})" for l in api["links"])
    return f"""# {name}: App (Rayfin, preview), generated by Krusgraph

Fabric Apps and Rayfin are in preview. This package was generated from the reviewed plan; it has not been run in your
tenant.

## Pages

{rows}

## The connector `{api['connector']}` (`{api['connector_type']}`)

Read-only: `operations: ['read']`; the GraphQL API it gets has queries only, no mutations. Links:

{links}

## Publish

{why}

{steps}

Unzip at the project's root: it replaces `src/App.tsx`, adds `{WIRING}` and the pages, and brings `rayfin/tsconfig.json`
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
           workspace_label: str, create=None, pre: dict | None = None) -> dict:
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
        return {"error": str(e), "kind": "bad_input", "hint": "Tick at least one key figure, list page or chart.", "options": opts}
    st = source_type_of(info.get("item_kind", "Lakehouse"))
    source_item = info.get("item_id") or "<source item id>"
    if info.get("item_kind", "Lakehouse") == "Lakehouse" and info.get("item_id"):
        try:
            source_item = sql_endpoint_id_for_lakehouse(info["workspace_id"], info["item_id"], headers)
        except Exception:  # noqa: BLE001 — the command shows the placeholder instead
            source_item = "<the lakehouse's SQL analytics endpoint id>"
    pkg = package(p, chosen, st)
    api = api_summary(p, pkg["connector"], st)
    cmds = commands(pkg["connector"], CONNECTOR_TYPES[st], workspace_label, info.get("workspace_id", ""), source_item, name)
    files = {**pkg["files"], "KRUSGRAPH-APP.md": readme(name, pkg["pages"], api, cmds, NOT_PUBLISHED_WHY)}
    out = {"dry_run": dry_run, "label": LABEL, "preview": True, "preflight": pre, "options": opts,
           "chosen": {k: [o["id"] for o in chosen[k]] for k in ("kpis", "tables", "charts")}, "gone": chosen["gone"],
           "pages": pkg["pages"], "api": api, "files": sorted(files), "commands": cmds, "published": False,
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
