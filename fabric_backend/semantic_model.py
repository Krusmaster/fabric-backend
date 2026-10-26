"""A Power BI semantic model in TMDL from a plan: one Direct Lake table per source table, relationships with
cardinality and filter direction, nothing created.

Format followed — the files read on 25 October 2026 (commit in brackets):
- microsoft/fabric-samples [18b94bc] docs-samples/data-science/enrich-powerbi-report-with-machine-learning/
  "Bank Customer Churn Analysis.SemanticModel"/definition/{database,model,expressions,tables/churn}.tmdl and
  definition.pbism: a Direct Lake model as Fabric writes it — `compatibilityLevel: 1604`, a shared expression with
  `annotation PBI_IncludeFutureArtifacts = False`, tables with `sourceLineageTag: [schema].[table]`, columns with
  `dataType`, `sourceLineageTag`, `summarizeBy`, `sourceColumn`, and `partition <table> = entity` / `mode: directLake`
  / `source` / `entityName`, `expressionSource`.
- MicrosoftDocs/fabric-docs [6b1f955] docs/fundamentals/direct-lake-develop.md ("The mode property of Direct Lake
  partitions is set to directLake", "Direct Lake on SQL — the expression points to the SQL analytics endpoint"),
  docs/fundamentals/understand-best-practices-fabric-cicd.md (expressions.tmdl for Direct Lake on SQL calls
  `Sql.Database(<SQL analytics endpoint connect string>, "<lakehouse name>")`),
  docs/fundamentals/direct-lake-power-bi-desktop.md (`schemaName` only for sources with schemas).
- microsoft/Analysis-Services [d3ccb50] pbidevmode/fabricps-pbip/SamplePBIP/Sales.SemanticModel/definition/
  relationships.tmdl and tables/Customer.tmdl: `relationship <name>` with `fromColumn: Table.Column`,
  `toColumn`, `isActive: false`; `isKey` on key columns; names with spaces quoted as 'Order Date'.
- microsoft/fabric-cicd [a9be0e9] sample/workspace/ABC.SemanticModel: `crossFilteringBehavior`, `fromCardinality`,
  `ref table` lines in model.tmdl, definition.pbism.
- microsoft/fabric-rest-api-specs [a96c37a] semanticModel/examples/GetSemanticModelDefinitionDefault.json and
  swagger.json: part paths `definition/database.tmdl`, `definition/model.tmdl`, `definition/tables/*.tmdl`,
  `definition.pbism`; the definition `format` defaults to TMDL.
The TMDL language reference on learn.microsoft.com (analysis-services/tmdl/*) could not be fetched from the
build environment; the syntax here is what those files use and nothing beyond it. Open points are written to
README.generated.md rather than guessed.

Why Direct Lake on SQL and not Import: the plan comes from the source's SQL analytics endpoint, and Direct Lake
reads the same Delta tables without a refresh or a copy; the endpoint supplies schema and security. Import would
need a refresh schedule and a copy of the data for no gain here. Direct Lake on OneLake (recommended by the docs
for new models) needs the OneLake storage URL of the item rather than the endpoint; that variant is noted in the
README and is a one-line change in expressions.tmdl.
"""
from __future__ import annotations

import re
import uuid

from .infer import Plan, Relationship, _words

COMPATIBILITY_LEVEL = 1604          # Direct Lake needs 1604 or higher (direct-lake-develop.md)
EXPRESSION = "DatabaseQuery"        # the shared expression every partition points at

# SQL analytics endpoint types -> TMDL dataType (Tabular: string, int64, double, dateTime, decimal, boolean, binary)
_TYPES = [
    (re.compile(r"^(bigint|int|integer|smallint|tinyint)"), "int64"),
    (re.compile(r"^(bit|boolean)"), "boolean"),
    (re.compile(r"^(float|real|double)"), "double"),
    (re.compile(r"^(decimal|numeric|money|smallmoney|number)"), "decimal"),
    (re.compile(r"^(date|datetime|datetime2|smalldatetime|timestamp|time)"), "dateTime"),
    (re.compile(r"^(binary|varbinary|image)"), "binary"),
]

_PLAIN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# The last word of a column that identifies, codes or labels something rather than measuring it: never summed.
_NOT_ADDITIVE = {"id", "key", "code", "no", "nr", "num", "number", "status", "type", "year", "month"}


def _looks_like_id(column: str) -> bool:
    """An identifier, a code or a label number is never summed, whether or not the plan links it: ship_to_id, line_no,
    sku_code, id, CustomerId, PersonID, SalesPersonID, RevisionNumber, Status, TaxType, ExpYear. Judged by the last word
    (snake_case or CamelCase), so `PAID` or `unit_price` stay measures."""
    c = column.lower()
    if c in ("id", "key", "code") or c.endswith(("_id", "_key", "_code", "_no", "_nr", "_number")):
        return True
    words = _words(column)
    return bool(words) and words[-1] in _NOT_ADDITIVE


def summarize_by(column: str, sql_type: str, is_ref: bool) -> str:
    """summarizeBy for a column: `sum` for a number that is neither a key, a reference nor an id-like column, else
    `none`. The suggested sum measures use the same rule, so a column is summed in a measure exactly when it is summed
    by default."""
    return "sum" if data_type(sql_type) in ("int64", "double", "decimal") and not is_ref and not _looks_like_id(column) else "none"


# The calendar a model gets when a fact table has date columns: a calculated table that references no Direct Lake table,
# which Direct Lake on SQL allows ("calculated tables that don't reference Direct Lake columns or tables are supported in
# all scenarios", MicrosoftDocs/fabric-docs a2de7f9 docs/fundamentals/direct-lake-overview.md, ms.date 09/02/2026), marked
# as the date table with `dataCategory: Time` and `isKey` on its Date column, as Calendar.tmdl in microsoft/Analysis-Services
# d3ccb50 pbidevmode/fabricps-pbip/SamplePBIP does. The range is a placeholder written in the README: the draft reads no
# rows, so it cannot know the first and last date.
CALENDAR_FIRST_YEAR, CALENDAR_LAST_YEAR = 2020, 2030
_DATE_TABLE_NAMES = {"date", "dates", "calendar", "kalender", "datum", "dimdate", "datedim", "calendardim", "time", "tid"}


def _norm_name(name: str) -> str:
    return "".join(_words(name))


def _sql_base(sql_type: str) -> str:
    return (sql_type or "").lower().split("(")[0].strip()


def suggested_measures(plan: Plan, chosen, role_of: dict[str, str], ref_cols: set[tuple[str, str]]) -> list[dict]:
    """Measures worth having from the start, each with the reason: the row count of every fact table, and a sum of each
    of its columns that summarizeBy sums (never an id, code, year or reference). Dimensions get none: their numbers
    (a list price, a weight) are attributes of one row, and adding them up is a decision for whoever builds the report."""
    out: list[dict] = []
    taken = {c.name.lower() for t in chosen for c in t.columns} | {t.name.lower() for t in chosen}

    def unique(name: str, table: str) -> str:
        n = name if name.lower() not in taken else f"{name} ({table})"
        taken.add(n.lower())
        return n
    for t in chosen:
        if role_of.get(t.name) != "fact":
            continue
        key = plan.keys.get(t.name, ([], ""))[0]
        out.append({"table": t.name, "name": unique(f"Rows in {t.name}", t.name), "expression": f"COUNTROWS({_dax_table(t.name)})",
                    "format": "#,##0", "why": f"{t.name} is a fact table (role from the plan's graph): its row count is the first number a report asks for"})
        for c in t.columns:
            if c.name not in t.column_names:
                continue
            is_ref = (t.name, c.name.lower()) in ref_cols or c.name in key
            if summarize_by(c.name, c.data_type, is_ref) != "sum":
                continue
            dt = data_type(c.data_type)
            out.append({"table": t.name, "name": unique(f"Total {c.name}", t.name), "expression": f"SUM({_dax_table(t.name)}[{_dax_column(c.name)}])",
                        "format": "#,##0" if dt == "int64" else "#,##0.00",
                        "why": f"{t.name}.{c.name} is a number in a fact table and neither a key, a reference nor an id, code or year, "
                               "so its default summarization is sum (summarizeBy: sum); the measure makes that sum explicit"})
    return out


def _dax_table(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _dax_column(name: str) -> str:
    return name.replace("]", "]]")


def date_columns(plan: Plan, chosen, role_of: dict[str, str]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(fact, column) pairs with a date type: those of SQL type `date` relate to the calendar; datetime and timestamp
    columns carry a time of day, and Direct Lake on SQL does not relate on the date part of a datetime
    (direct-lake-overview.md), so they are listed instead."""
    dates, timed = [], []
    for t in chosen:
        if role_of.get(t.name) != "fact":
            continue
        for c in t.columns:
            if c.name not in t.column_names or data_type(c.data_type) != "dateTime":
                continue
            (dates if _sql_base(c.data_type) == "date" else timed).append((t.name, c.name))
    return dates, timed


def calendar_tmdl(name: str, model: str) -> str:
    source = (f'ADDCOLUMNS(CALENDAR(DATE({CALENDAR_FIRST_YEAR}, 1, 1), DATE({CALENDAR_LAST_YEAR}, 12, 31)), '
              '"Year", YEAR([Date]), "Month", MONTH([Date]))')
    lines = [f"/// The model's date table, generated because fact tables have date columns; marked as the date table (dataCategory: Time).",
             f"table {tmdl_name(name)}", f"\tlineageTag: {_tag(model, 'table', name)}", "\tdataCategory: Time", ""]
    for col, dt, extra in (("Date", "dateTime", ["\t\tisKey", "\t\tformatString: yyyy-mm-dd"]), ("Year", "int64", ["\t\tformatString: 0"]),
                           ("Month", "int64", ["\t\tformatString: 0"])):
        lines += [f"\tcolumn {col}", f"\t\tdataType: {dt}", *extra, f"\t\tlineageTag: {_tag(model, 'column', name, col)}",
                  "\t\tsummarizeBy: none", "\t\tisDataTypeInferred", f"\t\tsourceColumn: [{col}]", "", "\t\tannotation SummarizationSetBy = Automatic", ""]
    lines += [f"\tpartition {tmdl_name(name)} = calculated", "\t\tmode: import", f"\t\tsource = {source}", ""]
    return "\n".join(lines)


def tmdl_name(name: str) -> str:
    """Object names in TMDL: bare when they are identifier-like, otherwise in single quotes."""
    return name if _PLAIN.match(name) else "'" + name.replace("'", "''") + "'"


def data_type(sql_type: str) -> str:
    t = (sql_type or "").lower().split("(")[0].strip()
    for rx, out in _TYPES:
        if rx.match(t):
            return out
    return "string"


def _tag(*parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "krusgraph-semantic-model|" + "|".join(parts)))


def active_relationships(plan: Plan, rels: list[Relationship], validation: dict | None = None) -> tuple[list[Relationship], list[tuple[Relationship, str]]]:
    """Which relationships can be active at once: the maximum spanning forest by certainty from graphs.py (a tabular
    model allows one active path between two tables). The rest are inactive with the reason."""
    from . import graphs
    es = [e for e in graphs.edges(plan, validation) if e["rel"] in rels]
    active, inactive = graphs.spanning_forest(plan, es)
    return [e["rel"] for e in active], [(e["rel"], e["why"]) for e in inactive]


def envelope(parts: dict[str, str], name: str, description: str = "") -> dict:
    """The body for POST /workspaces/{id}/semanticModels and the `definition` for updateDefinition: every
    definition/*.tmdl part and definition.pbism as InlineBase64, plus the .platform part (type SemanticModel), the
    layout of GetSemanticModelDefinitionDefault.json / CreateSemanticModel.json in fabric-rest-api-specs. The
    README is not a definition part and is left out."""
    import base64
    import json

    def b64(text: str) -> str:
        return base64.b64encode(text.encode("utf-8")).decode()
    platform = {"$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                "metadata": {"type": "SemanticModel", "displayName": name},
                "config": {"version": "2.0", "logicalId": str(uuid.uuid5(uuid.NAMESPACE_URL, "semanticmodel|" + name))}}
    rest = [{"path": p, "payload": b64(c), "payloadType": "InlineBase64"} for p, c in sorted(parts.items()) if p != "README.generated.md"]
    rest.append({"path": ".platform", "payload": b64(json.dumps(platform, indent=2)), "payloadType": "InlineBase64"})
    body = {"displayName": name, "definition": {"format": "TMDL", "parts": rest}}
    if description:
        body["description"] = description
    return body


def draft(plan: Plan, info: dict, name: str = "semantic_model", tables: list[str] | None = None, validation: dict | None = None) -> dict:
    """info: item_name, item_kind, schema, sql_endpoint, sql_db, schemas_enabled (from server._source_inputs); returns
    {"parts": {path: content}, "summary": {...}}. `validation` (evidence.validate's answer) raises the certainty of the
    links it confirmed when the active set is chosen."""
    from . import graphs
    analysis = graphs.analyze(plan, validation)
    role_of = {t: r["role"] for t, r in analysis["roles"].items()}
    wanted = {t.lower() for t in tables} if tables else None
    chosen = [t for t in plan.schema if not wanted or t.name.lower() in wanted]
    names = {t.name for t in chosen}
    schema = info.get("schema") or plan.schema.schema or "dbo"
    kind = info.get("item_kind") or "Lakehouse"
    endpoint = info.get("sql_endpoint") or "<sql analytics endpoint host>"
    database = info.get("sql_db") or info.get("item_name") or "<source item name>"
    # schemaName: a lakehouse created without schemas exposes its tables as dbo and has no schemaName in TMDL
    # (direct-lake-power-bi-desktop.md); one created with schemas (REST: properties.defaultSchema present) has it,
    # dbo included. Without that flag, a lakehouse's dbo is taken as "no schemas" and any other schema as schema-enabled.
    schemas_enabled = info.get("schemas_enabled")
    with_schema = bool(schemas_enabled) if schemas_enabled is not None else not (kind == "Lakehouse" and schema.lower() == "dbo")

    single = [r for r in plan.relationships if r.source in names and r.target in names
              and len(r.source_cols) == 1 and len(r.target_cols) == 1 and len(plan.keys.get(r.target, ([], ""))[0]) == 1]
    composite = [r for r in plan.relationships if r.source in names and r.target in names and r not in single]
    active, inactive = active_relationships(plan, single, validation)
    ref_cols = {(r.source, r.source_cols[0].lower()) for r in single}

    measures = suggested_measures(plan, chosen, role_of, ref_cols)
    by_table: dict[str, list[dict]] = {}
    for m in measures:
        by_table.setdefault(m["table"], []).append(m)
    dates, timed = date_columns(plan, chosen, role_of)
    lookalike = [t.name for t in chosen if _norm_name(t.name) in _DATE_TABLE_NAMES]
    calendar = None
    if (dates or timed) and not lookalike:
        calendar = "Calendar" if "calendar" not in {t.name.lower() for t in chosen} else "Krusgraph Calendar"

    parts: dict[str, str] = {}
    parts["definition/database.tmdl"] = f"database\n\tcompatibilityLevel: {COMPATIBILITY_LEVEL}\n"
    model = ["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3", "\tsourceQueryCulture: en-US",
             "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull", "",
             f'annotation PBI_QueryOrder = ["{EXPRESSION}"]', "", "annotation __PBI_TimeIntelligenceEnabled = 0", ""]
    model += [f"ref table {tmdl_name(t.name)}" for t in chosen]
    if calendar:
        model.append(f"ref table {tmdl_name(calendar)}")
    parts["definition/model.tmdl"] = "\n".join(model) + "\n"
    parts["definition/expressions.tmdl"] = "\n".join([
        f"expression {EXPRESSION} =", "\t\tlet", f'\t\t    database = Sql.Database("{endpoint}", "{database}")',
        "\t\tin", "\t\t    database", f"\tlineageTag: {_tag(name, 'expression')}", "",
        "\tannotation PBI_IncludeFutureArtifacts = False", ""])

    for t in chosen:
        key = plan.keys.get(t.name, ([], ""))[0]
        lines = [f"table {tmdl_name(t.name)}", f"\tlineageTag: {_tag(name, 'table', t.name)}",
                 f"\tsourceLineageTag: [{schema}].[{t.name}]", ""]
        for m in by_table.get(t.name, []):
            lines += [f"\t/// Suggested by Krusgraph: {m['why']}.", f"\tmeasure {tmdl_name(m['name'])} = {m['expression']}",
                      f"\t\tformatString: {m['format']}", f"\t\tlineageTag: {_tag(name, 'measure', t.name, m['name'])}", ""]
        for c in t.columns:
            dt = data_type(c.data_type)
            is_key = len(key) == 1 and c.name == key[0]
            summarize = summarize_by(c.name, c.data_type, (t.name, c.name.lower()) in ref_cols or c.name in key)
            lines.append(f"\tcolumn {tmdl_name(c.name)}")
            lines.append(f"\t\tdataType: {dt}")
            if is_key:
                lines.append("\t\tisKey")
            if dt == "int64":
                lines.append("\t\tformatString: 0")
            lines += [f"\t\tlineageTag: {_tag(name, 'column', t.name, c.name)}", f"\t\tsourceLineageTag: {c.name}",
                      f"\t\tsummarizeBy: {summarize}", f"\t\tsourceColumn: {c.name}", "",
                      "\t\tannotation SummarizationSetBy = Automatic", ""]
        lines += [f"\tpartition {tmdl_name(t.name)} = entity", "\t\tmode: directLake", "\t\tsource", f"\t\t\tentityName: {t.name}"]
        if with_schema:
            lines.append(f"\t\t\tschemaName: {schema}")
        lines += [f"\t\t\texpressionSource: {EXPRESSION}", "", "\tannotation PBI_ResultType = Table", "",
                  f"\tannotation Krusgraph_Role = {role_of.get(t.name, 'other')}", ""]
        parts[f"definition/tables/{t.name}.tmdl"] = "\n".join(lines)
    if calendar:
        parts[f"definition/tables/{calendar}.tmdl"] = calendar_tmdl(calendar, name)

    rel_lines: list[str] = []
    for r in active + [x for x, _ in inactive]:
        why = next((w for x, w in inactive if x is r), "")
        rel_lines.append(f"relationship {_tag(name, 'relationship', r.source, r.source_cols[0], r.target)}")
        if why:
            rel_lines.append("\tisActive: false")
        rel_lines.append(f"\tfromColumn: {tmdl_name(r.source)}.{tmdl_name(r.source_cols[0])}")
        rel_lines.append(f"\ttoColumn: {tmdl_name(r.target)}.{tmdl_name(r.target_cols[0])}")
        rel_lines.append("")
    date_rels = []
    for fact, col in dates if calendar else []:
        first = not any(d["fact"] == fact for d in date_rels)
        date_rels.append({"fact": fact, "column": col, "active": first})
        rel_lines.append(f"relationship {_tag(name, 'relationship', fact, col, calendar)}")
        if not first:
            rel_lines.append("\tisActive: false")
        rel_lines += [f"\tfromColumn: {tmdl_name(fact)}.{tmdl_name(col)}", f"\ttoColumn: {tmdl_name(calendar)}.Date", ""]
    parts["definition/relationships.tmdl"] = "\n".join(rel_lines) if rel_lines else "// no single-column relationships in the plan\n"
    parts["definition.pbism"] = ('{\n  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/'
                                 'definitionProperties/1.0.0/schema.json",\n  "version": "4.2",\n  "settings": {}\n}\n')

    keyless = [t.name for t in chosen if t.name not in plan.keys]
    multi_key = [t.name for t in chosen if len(plan.keys.get(t.name, ([], ""))[0]) > 1]
    readme = [f"# {name}: generated semantic model (TMDL)", "",
              f"Source: {kind} `{info.get('item_name') or database}`, schema `{schema}`, SQL analytics endpoint `{endpoint}`.",
              f"Storage mode: Direct Lake on the SQL analytics endpoint (`mode: directLake`, shared expression `{EXPRESSION}` = "
              f"`Sql.Database(endpoint, \"{database}\")`), compatibility level {COMPATIBILITY_LEVEL}. Chosen because the plan comes from "
              "that endpoint and Direct Lake reads the Delta tables in place; Import would add a refresh and a copy for nothing. "
              "For Direct Lake on OneLake replace the expression with `AzureStorage.DataLake(\"https://onelake.dfs.fabric.microsoft.com/"
              "<workspace id>/<item id>\", [HierarchicalNavigation=true])` as in Microsoft's fabric-samples model.", "",
              f"Tables: {len(chosen)}. Relationships: {len(active)} active, {len(inactive)} inactive, {len(composite)} not expressible. "
              "The active set keeps one path between any two tables and prefers the higher-confidence rule (declared/confirmed, "
              "then R1, R2, R4, R3); a relationship made inactive lost to one of a higher or equal rule.", "",
              "## Table roles (from the plan's graph, see analyze_schema)", "", "| Table | Role | Why |", "| --- | --- | --- |"]
    readme += [f"| `{t.name}` | {analysis['roles'][t.name]['role']} | {analysis['roles'][t.name]['why']} |" for t in chosen]
    readme += ["", "Fact tables are the many side of the model; dimensions are what they point at. A fact table's numeric columns "
               "are the ones to turn into measures.", "",
               "## Relationships", "", "| From | To | Rule | Active |", "| --- | --- | --- | --- |"]
    for r in active:
        readme.append(f"| `{r.source}.{r.source_cols[0]}` | `{r.target}.{r.target_cols[0]}` | {r.rule} | yes |")
    for r, why in inactive:
        readme.append(f"| `{r.source}.{r.source_cols[0]}` | `{r.target}.{r.target_cols[0]}` | {r.rule} | no: {why} |")
    readme += ["", "## Decisions to check", ""]
    for r, why in inactive:
        readme.append(f"- `{r.source}.{r.source_cols[0]} -> {r.target}` is inactive: {why}. Use USERELATIONSHIP in DAX or pick another active one.")
    for r in composite:
        readme.append(f"- `{r.source}.{'+'.join(r.source_cols)} -> {r.target}` ({r.rule}) is not in the model: tabular relationships use one "
                      "column per side. Add a combined key column in the source (or a calculated column) and relate on it.")
    for t in keyless:
        readme.append(f"- `{t}` has no key: it is in the model but nothing relates to it (rule K3). Give `keys` to change that.")
    for t in multi_key:
        readme.append(f"- `{t}` has a composite key ({'+'.join(plan.keys[t][0])}): no `isKey` column and nothing can relate to it one-to-many.")
    readme += ["", "## Uncertain, written down rather than guessed", "",
               "- Key uniqueness: `isKey` is set from the plan's inferred keys (rules K0–K5). Power BI refuses a one-side column with "
               "duplicates when the model is framed; run `validate_plan` first.",
               f"- `schemaName`: {'written for every partition' if with_schema else 'omitted because a lakehouse without schemas exposes dbo without one'} "
               "(docs: direct-lake-power-bi-desktop.md; the REST property `defaultSchema` tells the two kinds of lakehouse apart). "
               "If this is wrong for your lakehouse, add or remove the `schemaName` lines.",
               "- Filter direction is single (dimension to fact), the TMDL default; nothing is set to both directions.",
               "- Dates are `dateTime` (TMDL has no date type).",
               "- The TMDL language reference itself could not be fetched when this generator was written; the syntax follows "
               "Microsoft's published sample definitions listed in fabric_backend/semantic_model.py.",
               ""]
    readme += ["## Suggested measures", ""] + ([f"- `{m['name']}` = `{m['expression']}` on `{m['table']}`: {m['why']}." for m in measures]
                                              or ["- None: the plan has no fact table (a table that points at others and that nothing points at)."])
    readme += ["", "No measure sums an id, a code, a year or a reference: they use the same rule as `summarizeBy`. Dimension tables get "
               "no sums; their numbers describe one row.", "", "## Date table", ""]
    if calendar:
        readme += [f"`{calendar}` is a calculated table (`CALENDAR` with `Year` and `Month`) marked as the date table (`dataCategory: Time`, "
                   "`isKey` on `Date`); a calculated table that references no Direct Lake table is allowed in Direct Lake on SQL "
                   "(direct-lake-overview.md).",
                   f"- The range {CALENDAR_FIRST_YEAR}-01-01 to {CALENDAR_LAST_YEAR}-12-31 is a placeholder: this draft reads no rows. Set it to "
                   "your data's first and last year in the partition's `source`, or rows outside it have no date to filter by."]
        readme += [f"- `{d['fact']}.{d['column']} -> {calendar}.Date`" + (" (active)" if d["active"] else " (inactive: the fact's first date column is the active one; use USERELATIONSHIP)")
                   for d in date_rels]
        readme += [f"- `{f}.{c}` carries a time of day and is not related: Direct Lake on SQL does not relate on the date part of a datetime "
                   "(direct-lake-overview.md). Add a date column (for example in a gold view) and relate that." for f, c in timed]
    elif lookalike:
        readme += [f"- None generated: the plan already has a table that looks like a date table ({', '.join(lookalike)}). Mark it as the date "
                   "table in Power BI (Table tools -> Mark as date table) once its date column is unique."]
    else:
        readme += ["- None generated: no fact table has a date column."]
    readme += ["", "## Files", ""] + [f"- `{p}`" for p in parts] + [""]
    parts["README.generated.md"] = "\n".join(readme)
    summary = {"tables": len(chosen), "roles": {t.name: role_of.get(t.name) for t in chosen},
               "relationships_active": len(active), "relationships_inactive": len(inactive),
               "relationships_not_expressible": len(composite), "keyless": keyless, "composite_keys": multi_key,
               "storage_mode": "directLake (SQL analytics endpoint)", "compatibility_level": COMPATIBILITY_LEVEL,
               "inactive": [{"source": r.source, "columns": r.source_cols, "target": r.target, "why": why} for r, why in inactive],
               "measures": [{k: m[k] for k in ("table", "name", "expression", "why")} for m in measures],
               "date_table": ({"name": calendar, "marked_as_date_table": True, "related": date_rels,
                               "not_related": [{"fact": f, "column": c, "why": "datetime with a time of day"} for f, c in timed],
                               "range": f"{CALENDAR_FIRST_YEAR}-01-01 to {CALENDAR_LAST_YEAR}-12-31 (placeholder; see README)"} if calendar else None)}
    return {"parts": parts, "summary": summary}
