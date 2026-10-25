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

from .infer import Plan, Relationship

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


def active_relationships(plan: Plan, rels: list[Relationship]) -> tuple[list[Relationship], list[tuple[Relationship, str]]]:
    """Which relationships can be active at once. A tabular model allows one active path between two tables, so a
    second relationship on the same pair and any relationship that would close a cycle are made inactive.
    Order of preference: declared/confirmed, then R1, R2, R4, R3 — the plan's own confidence order; within a rule,
    relationships leaving the table with the most references first (the fact table keeps its direct links, a
    second path through a shared dimension goes inactive), then by name so the result is deterministic."""
    rank = {"R0": 0, "confirmed": 0, "R1": 1, "R2": 2, "R4": 3, "R3": 4}
    out_degree: dict[str, int] = {}
    for r in rels:
        out_degree[r.source] = out_degree.get(r.source, 0) + 1
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    active, inactive = [], []
    for r in sorted(rels, key=lambda r: (rank.get(r.rule, 9), -out_degree[r.source], r.source, r.target, r.source_cols)):
        a, b = find(r.source), find(r.target)
        if a == b:
            why = ("a relationship between these two tables is already active"
                   if any(x.source == r.source and x.target == r.target for x in active)
                   else "it would close a cycle, making filter paths ambiguous")
            inactive.append((r, why))
            continue
        parent[a] = b
        active.append(r)
    return active, inactive


def draft(plan: Plan, info: dict, name: str = "semantic_model", tables: list[str] | None = None) -> dict:
    """info: item_name, item_kind, schema, sql_endpoint (from server._ontology_inputs); returns
    {"parts": {path: content}, "summary": {...}}."""
    wanted = {t.lower() for t in tables} if tables else None
    chosen = [t for t in plan.schema if not wanted or t.name.lower() in wanted]
    names = {t.name for t in chosen}
    schema = info.get("schema") or plan.schema.schema or "dbo"
    kind = info.get("item_kind") or "Lakehouse"
    endpoint = info.get("sql_endpoint") or "<sql analytics endpoint host>"
    database = info.get("sql_db") or info.get("item_name") or "<source item name>"
    # schemaName: a lakehouse created without schemas exposes its tables as dbo and has no schemaName in TMDL
    with_schema = not (kind == "Lakehouse" and schema.lower() == "dbo")

    single = [r for r in plan.relationships if r.source in names and r.target in names
              and len(r.source_cols) == 1 and len(r.target_cols) == 1 and len(plan.keys.get(r.target, ([], ""))[0]) == 1]
    composite = [r for r in plan.relationships if r.source in names and r.target in names and r not in single]
    active, inactive = active_relationships(plan, single)
    ref_cols = {(r.source, r.source_cols[0].lower()) for r in single}

    parts: dict[str, str] = {}
    parts["definition/database.tmdl"] = f"database\n\tcompatibilityLevel: {COMPATIBILITY_LEVEL}\n"
    model = ["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3", "\tsourceQueryCulture: en-US",
             "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull", "",
             f'annotation PBI_QueryOrder = ["{EXPRESSION}"]', "", "annotation __PBI_TimeIntelligenceEnabled = 0", ""]
    model += [f"ref table {tmdl_name(t.name)}" for t in chosen]
    parts["definition/model.tmdl"] = "\n".join(model) + "\n"
    parts["definition/expressions.tmdl"] = "\n".join([
        f"expression {EXPRESSION} =", "\t\tlet", f'\t\t    database = Sql.Database("{endpoint}", "{database}")',
        "\t\tin", "\t\t    database", f"\tlineageTag: {_tag(name, 'expression')}", "",
        "\tannotation PBI_IncludeFutureArtifacts = False", ""])

    for t in chosen:
        key = plan.keys.get(t.name, ([], ""))[0]
        lines = [f"table {tmdl_name(t.name)}", f"\tlineageTag: {_tag(name, 'table', t.name)}",
                 f"\tsourceLineageTag: [{schema}].[{t.name}]", ""]
        for c in t.columns:
            dt = data_type(c.data_type)
            is_key = len(key) == 1 and c.name == key[0]
            is_ref = (t.name, c.name.lower()) in ref_cols or c.name in key
            summarize = "sum" if dt in ("int64", "double", "decimal") and not is_ref else "none"
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
        lines += [f"\t\t\texpressionSource: {EXPRESSION}", "", "\tannotation PBI_ResultType = Table", ""]
        parts[f"definition/tables/{t.name}.tmdl"] = "\n".join(lines)

    rel_lines: list[str] = []
    for r in active + [x for x, _ in inactive]:
        why = next((w for x, w in inactive if x is r), "")
        rel_lines.append(f"relationship {_tag(name, 'relationship', r.source, r.source_cols[0], r.target)}")
        if why:
            rel_lines.append("\tisActive: false")
        rel_lines.append(f"\tfromColumn: {tmdl_name(r.source)}.{tmdl_name(r.source_cols[0])}")
        rel_lines.append(f"\ttoColumn: {tmdl_name(r.target)}.{tmdl_name(r.target_cols[0])}")
        rel_lines.append("")
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
               "(docs: direct-lake-power-bi-desktop.md). If the lakehouse was created with schemas, add `schemaName: dbo`.",
               "- Filter direction is single (dimension to fact), the TMDL default; nothing is set to both directions.",
               "- Dates are `dateTime` (TMDL has no date type); no date table and no measures are generated.",
               "- The TMDL language reference itself could not be fetched when this generator was written; the syntax follows "
               "Microsoft's published sample definitions listed in fabric_backend/semantic_model.py.",
               "", "## Files", ""] + [f"- `{p}`" for p in parts] + [""]
    parts["README.generated.md"] = "\n".join(readme)
    summary = {"tables": len(chosen), "relationships_active": len(active), "relationships_inactive": len(inactive),
               "relationships_not_expressible": len(composite), "keyless": keyless, "composite_keys": multi_key,
               "storage_mode": "directLake (SQL analytics endpoint)", "compatibility_level": COMPATIBILITY_LEVEL,
               "inactive": [{"source": r.source, "columns": r.source_cols, "target": r.target, "why": why} for r, why in inactive]}
    return {"parts": parts, "summary": summary}
