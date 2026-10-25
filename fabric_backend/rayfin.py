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
shipped in @microsoft/rayfin-core. Verified with `npx rayfin up` in a sandbox (2026-10-22). Two things the docs do not say:
- `@one` / `@many` work on connector entities, but only with `{ sourceFields, targetFields }` —
  without them Rayfin derives a column like `customer_customer_id` that the table does not have.
- `@date()` properties are typed `Date`, not `string`, or the type check fails.
And one thing the docs do say: "don't infer a primary key from a column name". We do (rule K2) —
and print the rule beside every key so you can take it out.
"""
from __future__ import annotations

import re
from pathlib import Path

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
                rel_lines.append(f"  @one(() => {tc}, {fields}) {prop_name(r.field_name)}?: {tc};    // {'+'.join(r.source_cols)} -> {r.target} [{r.rule}]")
                decos_used.add("one")
                imports.append(tc)
            elif r.target == t.name:
                sc = class_name(r.source)
                fields = _fk_fields([prop_name(c) for c in r.target_cols], [prop_name(c) for c in r.source_cols])
                rel_lines.append(f"  @many(() => {sc}, {fields}) {prop_name(r.reverse_name)}?: {sc}[];    // {r.source}.{'+'.join(r.source_cols)} [{r.rule}]")
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
        out.append(f"// key {'+'.join(kcols)} by rule {rule}" + ("  (by name — remove primaryKey if that is wrong)" if rule == "K2" else ""))
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
                 role: tuple[str, list[str]] | None = ("authenticated", ["read"])) -> dict[str, str]:
    """{relative path: content} for rayfin/connectors/<connector>/ — entity files + schema.ts."""
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
    for t in plan.schema:
        if wanted and t.name.lower() not in wanted:
            continue
        cls = class_name(t.name)
        if cls in classes:
            raise ValueError(f"two tables map to the same class name {cls}")
        classes.append(cls)
        files[f"rayfin/connectors/{connector}/{cls}.ts"] = entity_ts(t, plan, relationships, role)
    files[f"rayfin/connectors/{connector}/schema.ts"] = schema_ts(connector, classes, CONNECTOR_TYPES[source_type])
    files[f"rayfin/connectors/{connector}/README.generated.md"] = _readme(connector, source_type, classes, plan)
    return files


def _readme(connector: str, source_type: str, classes: list[str], plan: Plan) -> str:
    n_rel = sum(1 for r in plan.relationships if r.target in plan.keys)
    return f"""# {connector} — generated by fabric-backend

{len(classes)} entities, {n_rel} relationships, connector type `{CONNECTOR_TYPES[source_type]}`.

Before `npx rayfin up`:

1. `npx rayfin connector add --type {CONNECTOR_TYPES[source_type]} --workspace-id <ws> --item-id <item> --name {connector} --operations read`
   (registers the connector in rayfin.yml and prints the npm install to run); then drop these files in.
2. Keys marked K2 were inferred from column names. Rayfin's docs say not to; delete `primaryKey` where it is wrong.
3. `@one` / `@many` come from the inferred relationships. If the connector rejects them, regenerate with
   `relationships=False` and keep this file's list as documentation.

Entities: {', '.join(classes)}
"""


def write_rayfin(files: dict[str, str], root: str | Path = ".") -> list[Path]:
    root = Path(root)
    out = []
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")   # no CRLF on Windows
        out.append(p)
    return out
