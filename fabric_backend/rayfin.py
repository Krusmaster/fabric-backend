"""Third consumer of the same plan: Rayfin (Fabric Apps) connector entities.

Rayfin — Microsoft's open-source backend SDK for apps on Fabric — reaches existing lakehouse /
warehouse / SQL database tables through *connectors*. `npx rayfin connector add` discovers the
schema into metadata.json, and then every entity class is written by hand:

    @role('authenticated', ['read'])
    @entity()
    export class Order extends Source({ schema: 'dbo', table: 'Order', primaryKey: ['orderId'] }) {
      @int({ column: 'OrderID' }) orderId!: number;
      @text() customerEmail!: string;
    }

This module writes those files from a Plan: one class per table with the right field decorators,
the key, and the relationships the plan inferred as `@one(() => Target)` / `@many(() => Target)`.

Docs used (Oct 2026): learn.microsoft.com/fabric/apps/connectors and the decorators reference
shipped in @microsoft/rayfin-core. Verified with `npx rayfin up` in a sandbox (2026-10-22). On 2026-11-05, with Rayfin
1.36.2 against a synthetic lakehouse, the steps in `_readme` were run from `npm create` to `npx rayfin up`; `rayfin up`
answered 403 "The feature is not available" until the tenant setting AppBackendTenant was on. Later in the same run a
published app showed rows from a table through the connector, after the page and src/lib/connectors.ts were changed by
hand: `connector add` printed "Wired 0", and importing the entity classes with their decorators stopped the build, so
the page imported the generated schema as a type only and passed explicit column lists. Since n109 those files are
generated too (`connectors_ts`, `page_tsx`, `RAYFIN_TSCONFIG`, from the installed 1.36.2 packages, see below), and
tests/test_rayfin_app.py compiles them with the pinned versions; they have not been deployed or run in a browser. The
template used was `dataapp`, which is built for semantic models. Since n128 the generated README recommends `blankapp`
(see BLANKAPP_APP_DIR below). Two things the docs do not say:
- `@one` / `@many` work on connector entities, but only with `{ sourceFields, targetFields }` —
  without them Rayfin derives a column like `customer_customer_id` that the table does not have.
- `@date()` properties are typed `Date`, not `string`, or the type check fails.
And one thing the docs do say: "don't infer a primary key from a column name". We do (rule K2) —
and print the rule beside every key so you can take it out.
"""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from . import privacy
from .infer import Plan
from .schema import Table

CONNECTOR_TYPES = {
    "SqlAnalyticsEndpoint": "fabric-sqlanalytics",
    "Warehouse": "fabric-warehouse",
    "SqlDbNative": "fabric-sqldatabase",
}

_TYPE_RULES = [
    (re.compile(r"^(uniqueidentifier|uuid)"), "uuid", "string"),
    (re.compile(r"^(int|integer|smallint|tinyint|bigint|long|short|byte)"), "int", "number"),
    (re.compile(r"^(decimal|numeric|money|smallmoney|float|real|double)"), "decimal", "number"),
    (re.compile(r"^(bit|boolean|bool)"), "boolean", "boolean"),
    (re.compile(r"^(date|datetime|datetime2|smalldatetime|timestamp|time)"), "date", "Date"),   # @date() is typed Date (connector contract §4)
]


def rayfin_type(data_type: str) -> tuple[str, str]:
    """(decorator, TypeScript type) for a SQL / Spark type name. Anything unknown is text."""
    t = (data_type or "").lower().strip()
    for rx, deco, ts in _TYPE_RULES:
        if rx.match(t):
            return deco, ts
    return "text", "string"


def prop_name(column: str) -> str:
    """customer_id -> customerId, OrderID -> orderID is ugly so -> orderId, __timestamp -> timestamp."""
    c = column.strip("_")
    parts = re.split(r"[^A-Za-z0-9]+", c)
    parts = [p for p in parts if p]
    if not parts:
        return "_"
    if len(parts) == 1:
        p = parts[0]
        # ALLCAPS or Mixed -> lower first letter only; keep internal caps of mixed case
        if p.isupper():
            return p.lower()
        return p[0].lower() + p[1:]
    head = parts[0].lower() if parts[0].isupper() else parts[0][0].lower() + parts[0][1:]
    tail = "".join(x.capitalize() if x.islower() or x.isupper() else x for x in parts[1:])
    n = head + tail
    return n if not n[:1].isdigit() else "_" + n


def class_name(table: str) -> str:
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", table) if p]
    n = "".join(p[0].upper() + (p[1:].lower() if p.isupper() else p[1:]) for p in parts)
    return n if not n[:1].isdigit() else "_" + n


def _fk_fields(source: list[str], target: list[str]) -> str:
    """Without sourceFields/targetFields Rayfin derives the FK column as <field>_<target key> (customer_customer_id),
    which a connector table does not have; so the join columns are always spelled out."""
    def q(xs: list[str]) -> str:
        return "[" + ", ".join(f"'{x}'" for x in xs) + "]"
    return f"{{ sourceFields: {q(source)}, targetFields: {q(target)} }}"


def entity_ts(t: Table, plan: Plan, relationships: bool = True,
              role: tuple[str, list[str]] | None = ("authenticated", ["read"])) -> str:
    cls = class_name(t.name)
    keys = plan.keys.get(t.name)
    decos_used: set[str] = set()
    lines: list[str] = []
    for c in t.columns:
        deco, ts = rayfin_type(c.data_type)
        decos_used.add(deco)
        p = prop_name(c.name)
        opt = f"{{ column: '{c.name}' }}" if p != c.name else ""
        lines.append(f"  @{deco}({opt}) {p}!: {ts};")

    rel_lines: list[str] = []
    imports: list[str] = []
    if relationships:
        for r in plan.relationships:
            if r.source == t.name and r.target in plan.keys:
                tc = class_name(r.target)
                fields = _fk_fields([prop_name(c) for c in r.source_cols], [prop_name(c) for c in r.target_cols])
                rel_lines.append(f"  @one(() => {tc}, {fields}) {prop_name(r.field_name)}?: {tc};    // {'+'.join(r.source_cols)} -> {r.target} [{plan.label(r.rule)}]")
                decos_used.add("one")
                imports.append(tc)
            elif r.target == t.name:
                sc = class_name(r.source)
                fields = _fk_fields([prop_name(c) for c in r.target_cols], [prop_name(c) for c in r.source_cols])
                rel_lines.append(f"  @many(() => {sc}, {fields}) {prop_name(r.reverse_name)}?: {sc}[];    // {r.source}.{'+'.join(r.source_cols)} [{plan.label(r.rule)}]")
                decos_used.add("many")
                imports.append(sc)
    if role:
        decos_used.add("role")
    core = sorted(decos_used | {"entity"})
    out = [f"// rayfin/connectors/<connector>/{cls}.ts — generated by fabric-backend from {t.schema}.{t.name}",
           f"import {{ {', '.join(core)} }} from '@microsoft/rayfin-core';",
           "import { Source } from '@microsoft/rayfin-connectors';"]
    for imp in sorted(set(imports) - {cls}):
        out.append(f"import {{ {imp} }} from './{imp}.js';")
    out.append("")
    if role:
        out.append(f"@role('{role[0]}', [{', '.join(repr(x) for x in role[1])}])".replace("'", "'"))
    out.append("@entity()")
    src = f"schema: '{t.schema}', table: '{t.name}'"
    if keys:
        kcols, rule = keys
        src += ", primaryKey: [" + ", ".join(f"'{prop_name(k)}'" for k in kcols) + "]"
        out.append(f"// key {'+'.join(kcols)} by rule {plan.label(rule)}" + ("  (by name — remove primaryKey if that is wrong)" if rule == "K2" else ""))
    else:
        out.append("// no key (rule K3): query only, no key-addressed operations")
    out.append(f"export class {cls} extends Source({{ {src} }}) {{")
    out.extend(lines)
    if rel_lines:
        out.append("")
        out.extend(rel_lines)
    out.append("}")
    return "\n".join(out) + "\n"


def schema_ts(connector: str, classes: list[str], connector_type: str, operations: list[str] | None = None) -> str:
    ops = operations or ["read"]
    pascal = class_name(connector)
    out = [f"// rayfin/connectors/{connector}/schema.ts — generated by fabric-backend",
           "import type { GraphQLBackedConnector } from '@microsoft/rayfin-connector-fabric-graphql';",
           "import type { ConnectorConfig } from '@microsoft/rayfin-connectors';"]
    for c in classes:
        out.append(f"import {{ {c} }} from './{c}.js';")
    out.append("")
    for c in classes:
        out.append(f"export {{ {c} }} from './{c}.js';")
    out += ["", "export const connectorConfig = {", f"  connector: '{connector_type}',",
            "  operations: [" + ", ".join(repr(o) for o in ops) + "],",
            "  entities: { " + ", ".join(classes) + " },", "} as const satisfies ConnectorConfig;", "",
            f"export type {pascal}Schema = GraphQLBackedConnector<",
            "  { " + ", ".join(f"{c}: typeof {c}" for c in classes) + " },",
            "  typeof connectorConfig", ">;"]
    return "\n".join(out) + "\n"


def rayfin_files(plan: Plan, connector: str = "data", source_type: str = "SqlAnalyticsEndpoint",
                 tables: list[str] | None = None, relationships: bool = True,
                 role: tuple[str, list[str]] | None = ("authenticated", ["read"]),
                 page_table: str | None = None) -> dict[str, str]:
    """{relative path: content}, relative to the app's root: rayfin/connectors/<connector>/ (entity files, schema.ts,
    README.generated.md), src/lib/connectors.ts (the wiring), src/pages/<Class>Page.tsx (the latest rows of
    `page_table`, by default a fact table) and rayfin/tsconfig.json (written only where the project has none)."""
    if source_type not in CONNECTOR_TYPES:
        raise ValueError(f"source_type must be one of {list(CONNECTOR_TYPES)} (semantic models are DAX, not entities)")
    wanted = {x.lower() for x in tables} if tables else None
    if wanted:
        # Only relationships between generated tables: an @one/@many to a class that is not generated would be an
        # import of a file that does not exist, and the Rayfin project would not build.
        import copy
        plan = copy.copy(plan)
        plan.relationships = [r for r in plan.relationships
                              if r.source.lower() in wanted and r.target.lower() in wanted]
    files: dict[str, str] = {}
    classes: list[str] = []
    generated: list[Table] = []
    for t in plan.schema:
        if wanted and t.name.lower() not in wanted:
            continue
        cls = class_name(t.name)
        if cls in classes:
            raise ValueError(f"two tables map to the same class name {cls}")
        classes.append(cls)
        generated.append(t)
        files[f"rayfin/connectors/{connector}/{cls}.ts"] = entity_ts(t, plan, relationships, role)
    files[f"rayfin/connectors/{connector}/schema.ts"] = schema_ts(connector, classes, CONNECTOR_TYPES[source_type])
    if not generated:
        raise ValueError("no table to generate: `tables` names none of the source's tables")
    personal = privacy.personal_columns(plan.schema, [t.name for t in generated])
    page = _page_table(plan, generated, page_table)
    files["src/lib/connectors.ts"] = connectors_ts(connector, generated, CONNECTOR_TYPES[source_type], personal)
    page_path = f"src/pages/{class_name(page.name)}Page.tsx"
    files[page_path] = page_tsx(connector, page, plan, personal)
    files[RAYFIN_TSCONFIG_PATH] = RAYFIN_TSCONFIG
    files[f"rayfin/connectors/{connector}/README.generated.md"] = _readme(connector, source_type, classes, plan,
                                                                          page, page_path, personal)
    return files


# --- the app side: src/lib/connectors.ts, the data page, rayfin/tsconfig.json --------------------------------------
#
# Read from the installed packages, versions 1.36.2 (the run of 5 November 2026 and tests/fixtures/rayfin_check):
# - @microsoft/rayfin-cli dist/services/connector-wiring.js: `connector add` and `connector remove` rewrite
#   src/lib/connectors.ts (exports `AppConnectorsSchema`, `connectorConfigs`, `connectorRuntimes`) only when the file
#   is missing nothing of its own: a file with the marker "@generated by `rayfin connector add`" or with both maps
#   empty. A connector is wired only once its schema.ts exports `connectorConfig`; at `connector add` time schema.ts is
#   a placeholder, which is why that run printed "Wired 0". The file written here carries no marker (not even quoted
#   in a comment: the CLI looks for the text anywhere in the file), so the CLI leaves it alone and prints the wiring it
#   would want instead.
# - @microsoft/rayfin-connectors dist/ConnectorsSchema.d.ts, `ConnectorConfig.entities`: "Prefer the string-array form
#   in code the browser loads. A decorated entity class cannot be bundled" — the build failure of that run. The app
#   therefore imports the connector's schema.ts with `import type` only, and lists each entity's columns by name.
# - @microsoft/rayfin-connector-fabric-graphql assets/docs/index.md ("Wire the client": `ConnectorsRayfinClient` from
#   @microsoft/rayfin-client, the connector name identical in rayfin.yml, `AppConnectorsSchema` and `connectors`) and
#   querying.md (a query chain needs an explicit `.select([...])`; `.orderBy()`, `.first(n)`, `.execute()`).
# - @microsoft/rayfin-cli templates/data-app (src/lib/rayfin-client.ts reads VITE_RAYFIN_API_URL and
#   VITE_RAYFIN_PUBLISHABLE_KEY and resolves the rest with `resolveRayfinConfig`; src/vite-env.d.ts types them).

PAGE_ROWS = 20          # rows the page asks for
PAGE_COLUMNS = 8        # columns it shows at most, so a wide table stays readable

RAYFIN_TSCONFIG_PATH = "rayfin/tsconfig.json"
# rayfin/tsconfig.json of the data-app template in the npm package @microsoft/rayfin-cli@1.36.2
# (templates/data-app/rayfin/tsconfig.json), unmodified. Copyright (c) Microsoft Corporation, MIT License (the LICENSE
# file of that package, read at 1.36.2). Without it `rayfin up` compiles with the root tsconfig.json, which has
# noEmit, and the connector apply fails with "No usable compiled connector entities".
RAYFIN_TSCONFIG = """{
  "extends": "../tsconfig.json",
  "compilerOptions": {
    "outDir": ".temp/compiled",
    "rootDir": ".",
    "declaration": true,
    "composite": true,
    "noEmit": false,
    "allowImportingTsExtensions": false,
    "module": "nodenext",
    "moduleResolution": "nodenext"
  },
  "include": ["**/*"],
  "exclude": [".temp/**/*"]
}
"""

# Paths write_rayfin does not overwrite: the project's own file wins.
KEEP_IF_PRESENT = {RAYFIN_TSCONFIG_PATH}


def _page_table(plan: Plan, generated: list[Table], wanted: str | None) -> Table:
    """The table the page lists: the one asked for, else the first fact table (two or more references out, none in),
    else the first table with a key, else the first table."""
    if wanted:
        for t in generated:
            if t.name.lower() == wanted.lower():
                return t
        raise ValueError(f"page_table {wanted!r} is not one of the generated tables: {', '.join(t.name for t in generated)}")
    from .views import fact_tables
    names = {t.name for t in generated}
    for f in fact_tables(plan):
        if f in names:
            return plan.schema[f]
    return next((t for t in generated if t.name in plan.keys), generated[0])


def _shown(t: Table, personal: dict) -> list[str]:
    """The columns of `t` the app may read by default: all but those that look like personal data by name."""
    return [c.name for c in t.columns if (t.name, c.name) not in personal]


def _order_column(t: Table, plan: Plan, shown: list[str]) -> str | None:
    """What "latest" means for the page: the first date column, else the first key column, else nothing."""
    types = {c.name: rayfin_type(c.data_type)[0] for c in t.columns}
    for c in shown:
        if types[c] == "date":
            return c
    key = plan.keys.get(t.name)
    if key and key[0][0] in shown:
        return key[0][0]
    return None


def _ts_key(name: str) -> str:
    return name if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name) else f"'{name}'"


def _access(name: str) -> str:
    return f".{name}" if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name) else f"['{name}']"


def _left_out_comment(items: list[str], indent: str = "") -> list[str]:
    if not items:
        return []
    return [f"{indent}// Left out, they look like personal data by name (Krusgraph's privacy rules): {', '.join(items)}."]


def connectors_ts(connector: str, tables: list[Table], connector_type: str, personal: dict,
                  operations: list[str] | None = None) -> str:
    """src/lib/connectors.ts: the connector wired into the app, in the shape `rayfin connector add` writes, without
    importing a single entity class."""
    ops = operations or ["read"]
    schema_type = f"{class_name(connector)}Schema"
    out = [f"// src/lib/connectors.ts — generated by fabric-backend for the connector '{connector}' ({connector_type})",
           "//",
           "// Wires the connector into the app: the CLI's `connector add` wired nothing in the run of 5 November 2026",
           "// (\"Wired 0\"), because rayfin/connectors/<name>/schema.ts was still its placeholder then. This file does not",
           "// carry the CLI's own generated-file marker, so the CLI does not rewrite it (do not add one: the CLI would",
           "// write the entity classes back in); when it prints wiring of its own, merge that by hand.",
           "//",
           "// Only types come from the connector's schema.ts (`import type`, erased from the build). Importing the entity",
           "// classes would bring their decorators into the browser bundle, which stopped the app build; so `entities`",
           "// lists each entity's columns by name, the form @microsoft/rayfin-connectors recommends for browser code.",
           "import { ConnectorsRayfinClient, resolveRayfinConfig } from '@microsoft/rayfin-client';",
           "import type { ConnectorConfig, ConnectorsRuntime } from '@microsoft/rayfin-connectors';",
           "",
           "import type {",
           *[f"  {n}," for n in sorted([schema_type] + [class_name(t.name) for t in tables])],
           f"}} from '../../rayfin/connectors/{connector}/schema';",
           "",
           "export type AppConnectorsSchema = {",
           f"  {_ts_key(connector)}: {schema_type};",
           "};",
           "",
           "export const connectorConfigs = {",
           f"  {_ts_key(connector)}: {{",
           f"    connector: '{connector_type}',",
           "    operations: [" + ", ".join(f"'{o}'" for o in ops) + "],",
           "    // The default columns of findMany / findFirst / findByKey, checked against the entity types. A query chain",
           "    // names its own with .select([...]).",
           "    entities: {"]
    for t in tables:
        left = [c.name for c in t.columns if (t.name, c.name) in personal]
        out += _left_out_comment(left, "      ")
        cls = class_name(t.name)
        cols = ", ".join(f"'{prop_name(c)}'" for c in _shown(t, personal))
        out.append(f"      {cls}: [{cols}] satisfies (keyof {cls})[],")
    out += ["    },",
            "  },",
            "} satisfies Record<keyof AppConnectorsSchema, ConnectorConfig>;",
            "",
            "// SQL (Category A) connectors return JSON: no client-side runtime.",
            "export const connectorRuntimes: ConnectorsRuntime = {};",
            "",
            "export type AppConnectorsClient = ConnectorsRayfinClient<",
            "  Record<string, never>,",
            "  Record<string, never>,",
            "  AppConnectorsSchema",
            ">;",
            "",
            "let client: Promise<AppConnectorsClient> | undefined;",
            "",
            "/** The app's client with `client.connectors" + _access(connector) + "`; created once, again after a failure. */",
            "export function getConnectorsClient(): Promise<AppConnectorsClient> {",
            "  if (!client) {",
            "    client = createClient().catch((error: unknown) => {",
            "      client = undefined;",
            "      throw error;",
            "    });",
            "  }",
            "  return client;",
            "}",
            "",
            "async function createClient(): Promise<AppConnectorsClient> {",
            "  const apiUrl = import.meta.env.VITE_RAYFIN_API_URL;",
            "  const publishableKey = import.meta.env.VITE_RAYFIN_PUBLISHABLE_KEY;",
            "  if (!apiUrl || !publishableKey) {",
            "    throw new Error(\"Missing VITE_RAYFIN_API_URL or VITE_RAYFIN_PUBLISHABLE_KEY: run 'npx rayfin up'\");",
            "  }",
            "  const resolved = await resolveRayfinConfig({",
            "    apiUrl,",
            "    publishableKey,",
            "    workspaceId: import.meta.env.VITE_FABRIC_WORKSPACE_ID,",
            "    itemId: import.meta.env.VITE_FABRIC_ITEM_ID,",
            "    portalUrl: import.meta.env.VITE_FABRIC_PORTAL_URL,",
            "  });",
            "  return new ConnectorsRayfinClient<Record<string, never>, Record<string, never>, AppConnectorsSchema>(",
            "    {",
            "      baseUrl: resolved.baseUrl ?? apiUrl,",
            "      publishableKey: resolved.publishableKey ?? publishableKey,",
            "      authStorage: true,",
            "      runtimeConfig: resolved.runtimeConfig,",
            "      connectors: connectorConfigs,",
            "    },",
            "    connectorRuntimes,",
            "  );",
            "}"]
    return "\n".join(out) + "\n"


def page_tsx(connector: str, t: Table, plan: Plan, personal: dict, rows: int = PAGE_ROWS,
             max_columns: int = PAGE_COLUMNS) -> str:
    """src/pages/<Class>Page.tsx: the latest rows of one table through the connector, with an explicit column list
    and the entity type imported as a type only."""
    cls = class_name(t.name)
    shown = _shown(t, personal)
    order = _order_column(t, plan, shown)
    cols = shown[:max_columns]
    if order and order not in cols:
        cols = [order] + cols[:max_columns - 1]
    props = [prop_name(c) for c in cols]
    left = [c.name for c in t.columns if (t.name, c.name) in personal]
    more = [c for c in shown if c not in cols]
    dated = order is not None and rayfin_type(next(c.data_type for c in t.columns if c.name == order))[0] == "date"
    if order and dated:
        what = f"the {rows} latest rows of {t.schema}.{t.name}, newest {order} first"
    elif order:
        what = f"the {rows} rows of {t.schema}.{t.name} with the highest {order} (its key; the table has no date column)"
    else:
        what = f"{rows} rows of {t.schema}.{t.name} (the table has no date column and no key to say which are the latest)"
    chain = f".orderBy({{ {prop_name(order)}: 'desc' }})" if order else ""
    title = f"{t.name}: latest {rows} rows" if dated else f"{t.name}: {rows} rows"
    out = [f"// src/pages/{cls}Page.tsx — generated by fabric-backend: {what},",
           f"// through the connector '{connector}'. Show it from src/App.tsx: `return <{cls}Page />;`",
           "import { useEffect, useState } from 'react';",
           "",
           f"import type {{ {cls} }} from '../../rayfin/connectors/{connector}/schema';",
           "import { getConnectorsClient } from '../lib/connectors';",
           ""]
    out += _left_out_comment(left)
    if more:
        out.append(f"// Not shown, to keep the table narrow: {', '.join(more)}.")
    out += ["const COLUMNS = [" + ", ".join(f"'{p}'" for p in props) + "] as const;",
            f"const ROWS = {rows};",
            "",
            f"type Row = Pick<{cls}, (typeof COLUMNS)[number]>;",
            "",
            "function cell(value: unknown): string {",
            "  if (value === null || value === undefined) return '';",
            "  if (value instanceof Date) return value.toISOString();",
            "  return String(value);",
            "}",
            "",
            f"export function {cls}Page() {{",
            "  const [rows, setRows] = useState<Row[] | null>(null);",
            "  const [error, setError] = useState<string | null>(null);",
            "",
            "  useEffect(() => {",
            "    let cancelled = false;",
            "    getConnectorsClient()",
            "      .then((client) =>",
            f"        client.connectors{_access(connector)}.{cls}",
            "          .select([...COLUMNS])" + (f"\n          {chain}" if chain else ""),
            "          .first(ROWS)",
            "          .execute(),",
            "      )",
            "      .then((result) => {",
            "        if (!cancelled) setRows(result);",
            "      })",
            "      .catch((e: unknown) => {",
            "        if (!cancelled) setError(e instanceof Error ? e.message : String(e));",
            "      });",
            "    return () => {",
            "      cancelled = true;",
            "    };",
            "  }, []);",
            "",
            "  return (",
            "    <main className=\"p-6\">",
            f"      <h1 className=\"mb-4 text-xl font-semibold\">{title}</h1>",
            "      {error && <p role=\"alert\">Could not read the rows: {error}</p>}",
            "      {!error && rows === null && <p>Loading…</p>}",
            "      {rows && (",
            "        <table className=\"text-left text-sm\">",
            "          <thead>",
            "            <tr>",
            "              {COLUMNS.map((c) => (",
            "                <th key={c} className=\"px-2 py-1\">",
            "                  {c}",
            "                </th>",
            "              ))}",
            "            </tr>",
            "          </thead>",
            "          <tbody>",
            "            {rows.map((row, i) => (",
            "              <tr key={i}>",
            "                {COLUMNS.map((c) => (",
            "                  <td key={c} className=\"px-2 py-1\">",
            "                    {cell(row[c])}",
            "                  </td>",
            "                ))}",
            "              </tr>",
            "            ))}",
            "          </tbody>",
            "        </table>",
            "      )}",
            "    </main>",
            "  );",
            "}",
            "",
            f"export default {cls}Page;"]
    return "\n".join(out) + "\n"


def _readme(connector: str, source_type: str, classes: list[str], plan: Plan, page: Table, page_path: str,
            personal: dict) -> str:
    n_rel = sum(1 for r in plan.relationships if r.target in plan.keys)
    ctype = CONNECTOR_TYPES[source_type]
    schema = getattr(plan.schema, "schema", None) or "<schema>"
    page_cls = class_name(page.name)
    left = sorted(f"{t}.{c}" for (t, c) in personal)
    left_line = (f"Columns left out of the wiring's default columns and of the page, because they look like personal "
                 f"data by name: {', '.join(left)}. Add one only where the app's users may see it.\n\n" if left else "")
    return f"""# {connector} — generated by fabric-backend

{len(classes)} entities, {n_rel} relationships, connector type `{ctype}`.

## The files

- `rayfin/connectors/{connector}/*.ts` and `schema.ts`: one entity class per table, with keys and relationships.
- `src/lib/connectors.ts`: the connector wired into the app (`AppConnectorsSchema`, `connectorConfigs`,
  `connectorRuntimes` and `getConnectorsClient()`). It imports the connector's schema as a type only and lists each
  entity's columns by name, so no entity class with decorators reaches the app build.
- `{page_path}`: a page that lists the latest rows of {page.schema}.{page.name} through the connector, with an explicit
  column list.
- `rayfin/tsconfig.json`: the one in the `data-app` template of `@microsoft/rayfin-cli`, written only where the
  project has none.

In a `blankapp` project the app lives in `packages/frontend/`: `--out .` writes `src/lib/connectors.ts` and the page
under `packages/frontend/src/` when it finds `packages/frontend/package.json`, and keeps the project's own
`rayfin/tsconfig.json`.

{left_line}## Publishing in Fabric

Use the `blankapp` template. On 6 November 2026, with the 1.36.2 packages, the generated files type-checked, compiled
for `rayfin up` and built in a `blankapp` project with no hand change. In a `dataapp` project (built for semantic
models) the same files needed three hand changes in the template's files (keep the `SemanticModelConnectors` type in
`src/lib/connectors.ts`, give `new ConnectorsRayfinClient` in `src/lib/rayfin-client.ts` its type arguments, cast
through `unknown` in `src/hooks/use-semantic-model-query.ts`), and the template's `src/lib/connectors.spec.ts` then
fails.

First, a Fabric admin turns on the tenant setting "Enable Fabric App Items (preview)" (`AppBackendTenant`)
in the Admin portal. Until it is on, `npx rayfin up` stops with 403 "The feature is not available". An admin can read
the setting with `GET /v1/admin/tenantsettings`. Leave anonymous data access off.

1. `npm create @microsoft/rayfin@latest -- <app> --template blankapp --workspace "<workspace>"`
   (in Windows PowerShell `npm.cmd create ...`), then `cd <app>`.
2. `npm run pack:add -- connectors` (the template's step for existing Fabric sources: the connector SDK, a seeded
   `packages/frontend/src/lib/connectors.ts` and a client typed by `AppConnectorsSchema`).
3. `npx rayfin login`
4. `npx rayfin connector add --type {ctype} --workspace-id <ws> --item-id <item> --name {connector} --operations read`
   registers the connector in rayfin.yml, writes `rayfin/connectors/{connector}/metadata.json` and prints an
   `npm install`; run that inside the project. It may say it wired nothing; the generated `src/lib/connectors.ts` does
   that.
5. Generate the files from that metadata.json, at the project's root:
   `fabric-backend rayfin rayfin/connectors/{connector}/metadata.json --schema {schema} --connector {connector} --out .`
   (`--page-table <table>` picks the page's table).
6. Review the keys. Keys marked K2 were inferred from column names. Rayfin's docs say not to; delete `primaryKey`
   where it is wrong.
7. Use the generated files: in `packages/frontend/src/App.tsx`, import `{page_cls}Page` from
   `./pages/{page_cls}Page` and return `<{page_cls}Page />` in place of the template's placeholder.
8. `npx tsc -p rayfin/tsconfig.json --noEmit`, `npm run typecheck` and `npm run build`
9. `npx rayfin up --workspace <workspace>`; when asked, choose that visitors must sign in.
10. If the connector step failed: `npx rayfin up connector apply --name {connector}`. Read the warnings of `rayfin up`:
   a failed connector apply ("No usable compiled connector entities") does not make the deploy report failure.

## What was verified, and what was not

- Run of 5 November 2026, Rayfin 1.36.2, synthetic lakehouse, `dataapp` template:
  a published app showed rows from a table through the connector. In that run `src/lib/connectors.ts` and the page were written by hand; the generated
  files do the same things (type-only schema import, explicit column lists), but they have not been deployed to Fabric
  or opened in a browser, and no app has been published from a `blankapp` project.
- fabric-backend's tests compile the generated files, the page included, with `tsc` against `@microsoft/rayfin-*`
  1.36.2 and TypeScript 5.7.3, in a project laid out like the `dataapp` template and in one laid out like the
  `blankapp` template after `pack:add -- connectors`. That checks types, not behaviour: sign-in, the connector apply
  and reading rows happen only in Fabric.

`@one` / `@many` come from the inferred relationships. If the connector rejects them, regenerate with
`relationships=False` and keep this file's list as documentation.

Entities: {', '.join(classes)}
"""


# --- the project layout: `blankapp` or `dataapp` ---------------------------------------------------------------------
#
# Checked on 6 November 2026 (n128) with the npm packages only (`npm create @microsoft/rayfin@1.36.2`, no login, no
# `rayfin up`): a `dataapp` and a `blankapp` project (the names `create-rayfin --list-templates` prints), the files
# generated for the shop example dropped in, then `tsc` and the app build.
# - `dataapp` keeps the app at the root (src/). Its src/lib/connectors.ts carries the CLI's marker and an app-owned
#   `SemanticModelConnectors` type that src/hooks/use-semantic-model-query.ts imports, and its src/lib/rayfin-client.ts
#   builds the client without type arguments. With the generated src/lib/connectors.ts in place the type check needed
#   three hand changes (keep `SemanticModelConnectors`, give `new ConnectorsRayfinClient` its type arguments, cast
#   through `unknown` in the hook), and the template's own src/lib/connectors.spec.ts then fails two tests that expect
#   the CLI's marker.
# - `blankapp` (the "universal-app" template of @microsoft/rayfin-cli) keeps the app in packages/frontend/, whose
#   tsconfig.json already includes ../../rayfin/connectors/**/*.ts and which ships its own rayfin/tsconfig.json. After
#   `npm run pack:add -- connectors` (the template's step for existing Fabric sources: it seeds
#   packages/frontend/src/lib/connectors.ts with both maps empty and a rayfin-client.ts typed by
#   `AppConnectorsSchema`), the generated files type-check, compile for `rayfin up` and build with no hand change,
#   once they sit under packages/frontend/src and import rayfin/connectors/ two levels further up. write_rayfin does
#   that when it finds packages/frontend/package.json under the root.

BLANKAPP_APP_DIR = "packages/frontend"


def app_dir_of(root: str | Path) -> str:
    """The app's folder inside a Rayfin project: packages/frontend in a `blankapp` project, "" (the root) otherwise."""
    return BLANKAPP_APP_DIR if (Path(root) / BLANKAPP_APP_DIR / "package.json").is_file() else ""


def in_app_dir(files: dict[str, str], app_dir: str) -> dict[str, str]:
    """The files of rayfin_files with src/ moved under `app_dir` and their imports of rayfin/connectors/ adjusted."""
    if not app_dir:
        return dict(files)
    up = "../" * len(PurePosixPath(app_dir).parts)
    out = {}
    for rel, content in files.items():
        if rel.startswith("src/"):
            content = (content.replace("from '../../rayfin/connectors/", f"from '../../{up}rayfin/connectors/")
                       .replace("// src/", f"// {app_dir}/src/", 1)
                       .replace("Show it from src/App.tsx", f"Show it from {app_dir}/src/App.tsx"))
            rel = f"{app_dir}/{rel}"
        out[rel] = content
    return out


def write_rayfin(files: dict[str, str], root: str | Path = ".", app_dir: str | None = None) -> list[Path]:
    """Write {relative path: text} under `root`. For the Rayfin app files, `app_dir` None means: look at the project
    (packages/frontend in a `blankapp` project, the root otherwise)."""
    root = Path(root)
    if "src/lib/connectors.ts" in files:
        files = in_app_dir(files, app_dir_of(root) if app_dir is None else app_dir)
    out = []
    for rel, content in files.items():
        p = root / rel
        if rel in KEEP_IF_PRESENT and p.exists():
            continue                                            # the project's own rayfin/tsconfig.json wins
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")   # no CRLF on Windows
        out.append(p)
    return out
