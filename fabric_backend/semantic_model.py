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
The syntax here is what those files use and nothing beyond it (the TMDL language reference on learn.microsoft.com,
analysis-services/tmdl/*, was not read for it). Open points are written to
README.generated.md rather than guessed.

Every document written here starts with an object. On 30 October 2026 Power BI Desktop (2.151) opened the shop project
from /check but refused the SAP one: its relationships.tmdl held one comment line and nothing else, and the TMDL parser
stopped with "InvalidLineType, unexpected line type: Other!, Document: ./relationships, line 1". A document that would
hold only comments is therefore not written (relationships.tmdl is left out when nothing is expressible), and the
explanation goes to README.generated.md. `has_object` is the rule; the draft applies it to every part before returning.

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
_OBJECT = re.compile(r"^(database|model|table|expression|relationship|role|perspective|culture|function|namespace|entity)\b")


# n151: the format of a count and of a sum of whole numbers. On 7 November 2026 Power BI showed such a measure of a live
# model as "59,00"; "#,0" is a whole number with a thousands separator, in the culture of the report.
WHOLE = "#,0"
DECIMAL = "#,##0.00"


def number_format(data_type: str) -> str:
    """The formatString of a SUM measure: whole numbers for an int64 column, two decimals otherwise."""
    return WHOLE if data_type == "int64" else DECIMAL


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
# d3ccb50 pbidevmode/fabricps-pbip/SamplePBIP does. The draft reads no rows, so without `date_range` the range is a
# placeholder written in the README. n151: create_semantic_model reads the first and last value of the related date
# columns (MIN and MAX, read-only) and passes them as `date_range`; the calendar then spans the whole years from the first
# to the last date. It also has "Year Month" ("2026-10", text that sorts in time order), so a chart by month does not add
# up the same month of different years.
CALENDAR_FIRST_YEAR, CALENDAR_LAST_YEAR = 2020, 2030
_DATE_TABLE_NAMES = {"date", "dates", "calendar", "kalender", "datum", "dimdate", "datedim", "calendardim", "time", "tid"}


def _norm_name(name: str) -> str:
    return "".join(_words(name))


def _sql_base(sql_type: str) -> str:
    return (sql_type or "").lower().split("(")[0].strip()


def suggested_measures(plan: Plan, chosen, role_of: dict[str, str], ref_cols: set[tuple[str, str]],
                       whole: set[tuple[str, str]] = frozenset()) -> list[dict]:
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
        out.append({"table": t.name, "column": None, "name": unique(f"Rows in {t.name}", t.name), "expression": f"COUNTROWS({_dax_table(t.name)})",
                    "format": WHOLE, "why": f"{t.name} is a fact table (role from the plan's graph): its row count is the first number a report asks for"})
        for c in t.columns:
            if c.name not in t.column_names:
                continue
            is_ref = (t.name, c.name.lower()) in ref_cols or c.name in key
            if summarize_by(c.name, c.data_type, is_ref) != "sum":
                continue
            dt = data_type(c.data_type)
            out.append({"table": t.name, "column": c.name, "name": unique(f"Total {c.name}", t.name),
                        "expression": f"SUM({_dax_table(t.name)}[{_dax_column(c.name)}])",
                        "format": WHOLE if (t.name, c.name) in whole else number_format(dt),
                        "why": f"{t.name}.{c.name} is a number in a fact table and neither a key, a reference nor an id, code or year, "
                               "so its default summarization is sum (summarizeBy: sum); the measure makes that sum explicit"})
    return out


def header_amount_columns(plan: Plan, names: set[str]) -> dict[tuple[str, str], list[str]]:
    """(header, column) -> the line tables in the model that have several rows per header row (amounts.py)."""
    from . import amounts
    out: dict[tuple[str, str], list[str]] = {}
    for f in amounts.header_amounts(plan):
        if f["header"] in names and f["line"] in names:
            for c in f["amount_columns"]:
                out.setdefault((f["header"], c), [])
                if f["line"] not in out[(f["header"], c)]:
                    out[(f["header"], c)].append(f["line"])
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


def quantity_columns(plan: Plan, tables: list[str] | None = None) -> list[tuple[str, str]]:
    """(fact table, column) of the quantity columns of a decimal type the draft would sum: create_semantic_model counts
    whether their rows hold whole numbers only (n151; the shop's order_items.quantity is DOUBLE and holds 1, 2, 3)."""
    from . import amounts, graphs
    role_of = {t: r["role"] for t, r in graphs.analyze(plan, None)["roles"].items()}
    wanted = {t.lower() for t in tables} if tables else None
    out = []
    for t in plan.schema:
        if role_of.get(t.name) != "fact" or (wanted and t.name.lower() not in wanted):
            continue
        for c in t.columns:
            if c.name in t.column_names and data_type(c.data_type) in ("double", "decimal") and amounts.is_quantity(c.name, c.data_type):
                out.append((t.name, c.name))
    return out


def related_date_columns(plan: Plan, tables: list[str] | None = None) -> list[tuple[str, str]]:
    """(fact table, column) of the `date` columns the calendar relates to: create_semantic_model reads their first and
    last value for the calendar's range (n151)."""
    from . import graphs
    role_of = {t: r["role"] for t, r in graphs.analyze(plan, None)["roles"].items()}
    wanted = {t.lower() for t in tables} if tables else None
    chosen = [t for t in plan.schema if not wanted or t.name.lower() in wanted]
    return date_columns(plan, chosen, role_of)[0]


def range_sql(schema: str, table: str, column: str) -> str:
    """The first and last value of a date column (the caller keeps the first ten characters, YYYY-MM-DD). Read-only."""
    from .dialects import TSQL
    q = TSQL.quote(column)
    return f"SELECT MIN({q}) AS first_date, MAX({q}) AS last_date FROM {TSQL.table(schema, table)}"


def whole_sql(schema: str, table: str, column: str) -> str:
    """How many rows of a decimal column hold a number with a fraction. Read-only."""
    from .dialects import TSQL
    q = TSQL.quote(column)
    return f"SELECT COUNT(*) AS fractions FROM {TSQL.table(schema, table)} WHERE {q} <> CAST({q} AS BIGINT)"


def calendar_years(date_range: tuple[str, str] | None) -> tuple[int, int, bool]:
    """(first year, last year, from the data?): the years of `date_range` ("YYYY-MM-DD" first and last date), else the
    placeholder."""
    if date_range:
        try:
            first, last = int(str(date_range[0])[:4]), int(str(date_range[1])[:4])
            if 1900 <= first <= last <= 2200:
                return first, last, True
        except (TypeError, ValueError, IndexError):
            pass
    return CALENDAR_FIRST_YEAR, CALENDAR_LAST_YEAR, False


def calendar_tmdl(name: str, model: str, date_range: tuple[str, str] | None = None) -> str:
    first, last, _ = calendar_years(date_range)
    source = (f'ADDCOLUMNS(CALENDAR(DATE({first}, 1, 1), DATE({last}, 12, 31)), '
              '"Year", YEAR([Date]), "Month", MONTH([Date]), "Year Month", FORMAT([Date], "yyyy-mm"))')
    lines = [f"/// The model's date table, generated because fact tables have date columns; marked as the date table (dataCategory: Time).",
             f"table {tmdl_name(name)}", f"\tlineageTag: {_tag(model, 'table', name)}", "\tdataCategory: Time", ""]
    for col, dt, extra in (("Date", "dateTime", ["\t\tisKey", "\t\tformatString: yyyy-mm-dd"]), ("Year", "int64", ["\t\tformatString: 0"]),
                           ("Month", "int64", ["\t\tformatString: 0"]), ("Year Month", "string", [])):
        lines += [f"\tcolumn {tmdl_name(col)}", f"\t\tdataType: {dt}", *extra, f"\t\tlineageTag: {_tag(model, 'column', name, col)}",
                  "\t\tsummarizeBy: none", "\t\tisDataTypeInferred", f"\t\tsourceColumn: [{col}]", "", "\t\tannotation SummarizationSetBy = Automatic", ""]
    lines += [f"\tpartition {tmdl_name(name)} = calculated", "\t\tmode: import", f"\t\tsource = {source}", ""]
    return "\n".join(lines)


def has_object(text: str) -> bool:
    """Whether a TMDL document holds an object: its first line that is neither blank nor a comment (`//`, or a `///`
    description) starts an object such as `database`, `model`, `table`, `expression` or `relationship`. The parser in
    Power BI Desktop refuses a document without one (InvalidLineType, 30 October 2026)."""
    for line in text.splitlines():
        body = line.strip()
        if body and not body.startswith("//"):
            return _OBJECT.match(body) is not None
    return False


def _m_text(value) -> str:
    """A Power Query M text literal: a double quote doubled, a line break as #(lf)/#(cr), so a lakehouse named
    `my "lh"` stays one string (review L8)."""
    s = str(value).replace("#(", "#(#)(").replace('"', '""').replace("\r", "#(cr)").replace("\n", "#(lf)")
    return '"' + s + '"'


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


def not_expressible_why(plan: Plan, r: Relationship) -> str:
    """Why a relationship of the plan cannot be a tabular relationship as the tables stand: either it uses several
    columns per side (a composite key, SAP's MANDT+VBELN), or its one column points at a table whose key has several
    columns, so the one side is not unique on that column. Direct Lake allows no calculated columns, so the combined key
    has to be a column of the Delta table: a gold view (gold_views_draft, create_gold_views) or the silver step."""
    key = plan.keys.get(r.target, ([], ""))[0]
    combined = " + '|' + ".join(r.target_cols if len(r.target_cols) > 1 else key)
    if len(r.source_cols) > 1 or len(r.target_cols) > 1:
        return (f"a tabular relationship uses one column per side, and this one needs {len(r.source_cols)}; Direct Lake allows no "
                f"calculated column to combine them. Add a combined key column ({combined}) to `{r.target}` and the matching column "
                f"to `{r.source}` in the lakehouse, for example in a gold view (gold_views_draft / create_gold_views), and relate on it")
    if not key:
        return (f"`{r.target}` has no key, so `{r.target_cols[0]}` is not known to be unique on the one side. Give `keys` for `{r.target}` "
                "(or add a key column to it in the lakehouse) and relate on it")
    return (f"`{r.target}`'s key has {len(key)} columns ({'+'.join(key)}), so `{r.target_cols[0]}` alone is not unique on the one side; "
            f"Direct Lake allows no calculated column to combine them. Add a combined key column ({combined}) to `{r.target}` and the "
            f"matching column to `{r.source}` in the lakehouse, for example in a gold view (gold_views_draft / create_gold_views), and relate on it")


def keys_not_unique(plan: Plan, validation: dict | None) -> dict[str, dict]:
    """n150: table -> validate_plan's count of its key, for every key of the plan that the rows show is not unique or has
    NULLs. Such a column is no `isKey`, and nothing is related onto it: Power BI refuses a one side with duplicates, and a
    join onto it repeats the many side's rows (4 customers rows with 3 distinct customer_id: an order of the duplicated
    customer counts twice)."""
    out = {}
    for k in (validation or {}).get("keys", []):
        key = plan.keys.get(k.get("table"), ([], ""))[0]
        if key and [c.lower() for c in k.get("columns", [])] == [c.lower() for c in key] and not str(k.get("verdict", "")).startswith("unique"):
            out[k["table"]] = k
    return out


def not_unique_why(table: str, k: dict) -> str:
    cols = "+".join(k["columns"])
    return (f"`{table}.{cols}` is not unique in the rows ({k['rows']} rows, {k['distinct']} distinct values, {k['nulls']} NULLs), so it "
            f"cannot be the one side: a relationship onto it would count each duplicated {table} row's matches more than once. Give the "
            f"real key of `{table}` (or keep one row per value in silver) and relate on it")


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


def draft(plan: Plan, info: dict, name: str = "semantic_model", tables: list[str] | None = None, validation: dict | None = None,
          date_range: tuple[str, str] | None = None, whole_quantities: set[tuple[str, str]] = frozenset()) -> dict:
    """info: item_name, item_kind, schema, sql_endpoint, sql_db, schemas_enabled (from server._source_inputs); returns
    {"parts": {path: content}, "summary": {...}}. `validation` (evidence.validate's answer) raises the certainty of the
    links it confirmed when the active set is chosen. `date_range` (first, last date of the related date columns, read
    by create_semantic_model) sets the calendar's range; without it the range is a placeholder (n151).
    `whole_quantities`: (table, column) of quantity columns of a decimal type whose rows hold whole numbers only (counted
    by create_semantic_model, `quantity_columns` and `whole_sql`); their sum is formatted as a whole number (n151)."""
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

    dup = keys_not_unique(plan, validation)                      # n150: a key the rows show is not unique is no one side
    single = [r for r in plan.relationships if r.source in names and r.target in names and r.target not in dup
              and len(r.source_cols) == 1 and len(r.target_cols) == 1 and len(plan.keys.get(r.target, ([], ""))[0]) == 1]
    composite = [r for r in plan.relationships if r.source in names and r.target in names and r not in single]
    why_not = lambda r: not_unique_why(r.target, dup[r.target]) if r.target in dup else not_expressible_why(plan, r)
    active, inactive = active_relationships(plan, single, validation)
    ref_cols = {(r.source, r.source_cols[0].lower()) for r in single}

    measures = suggested_measures(plan, chosen, role_of, ref_cols, set(whole_quantities))
    header_level = header_amount_columns(plan, names)
    for (t, c), lines_of in header_level.items():                 # the total that doubles (amounts.py): a measure on the header
        why = (f"{t}.{c} is an amount at the level of {t}, and {', '.join(lines_of)} has several rows per {t} row: the measure sums it "
               f"once per {t} row, while summing it over {lines_of[0]} rows (a flat table, a view or an export of the joined rows) "
               f"would count each {t} once per line, so the column itself is not summed by default (summarizeBy: none). "
               "Order amount and line amount are different levels")
        m = next((x for x in measures if x["table"] == t and x["column"] == c), None)
        if m:
            m["why"] = why
            continue
        taken = {x["name"].lower() for x in measures} | {x.name.lower() for x in chosen} | {col.name.lower() for x in chosen for col in x.columns}
        mname = f"Total {c}" if f"total {c}".lower() not in taken else f"Total {c} ({t})"
        dt = data_type(next(col.data_type for col in plan.schema[t].columns if col.name == c))
        measures.append({"table": t, "column": c, "name": mname, "expression": f"SUM({_dax_table(t)}[{_dax_column(c)}])",
                         "format": number_format(dt), "why": why})
    # the amount that is not there (amounts.py): a line with a quantity and no amount, the price on the table it points at
    from . import amounts as _amounts
    order_amount = _amounts.order_amount_measures(plan, active, names)
    consumed = {(m["dimension"], m["price"]) for m in order_amount["measures"]}
    measures = [m for m in measures if (m["table"], m["column"]) not in consumed]   # no sum of a price that feeds the order amount
    taken = {x["name"].lower() for x in measures} | {x.name.lower() for x in chosen} | {col.name.lower() for x in chosen for col in x.columns}
    for m in order_amount["measures"]:
        if m["name"].lower() in taken:
            m["name"] = f"{m['name']} ({m['table']})"
        taken.add(m["name"].lower())
        measures.append(m)
    feeds = {(d, c): next(m["name"] for m in order_amount["measures"] if (m["dimension"], m["price"]) == (d, c)) for d, c in consumed}
    from . import level_measures as _levels                       # n133: sums at the right level (an amount's own table, the header)
    flat = _levels.flat_amounts(validation, names)
    measures = [m for m in measures if (m["table"], m.get("column")) not in flat]   # a flat header amount: no plain sum
    more, flat = _levels.suggest(plan, chosen, measures, header_level, consumed, ref_cols, taken, validation, summarize_by, data_type, role_of)
    measures += more
    by_table: dict[str, list[dict]] = {}
    for m in measures:
        by_table.setdefault(m["table"], []).append(m)
    dates, timed = date_columns(plan, chosen, role_of)
    cal_first, cal_last, cal_from_data = calendar_years(date_range)
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
        f"expression {EXPRESSION} =", "\t\tlet", f'\t\t    database = Sql.Database({_m_text(endpoint)}, {_m_text(database)})',
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
            is_key = len(key) == 1 and c.name == key[0] and t.name not in dup
            summarize = summarize_by(c.name, c.data_type, (t.name, c.name.lower()) in ref_cols or c.name in key)
            if (t.name, c.name) in feeds:
                summarize = "none"
                lines.append(f"\t/// A price at the level of {t.name}, read by the measure {tmdl_name(feeds[(t.name, c.name)])} through RELATED. "
                             f"Not summed by default: a sum of prices over the line rows would count each price once per line.")
            elif (t.name, c.name) in flat:
                summarize = "none"
                lines.append(f"\t/// An amount at the level of {flat[(t.name, c.name)]}, repeated on every {t.name} row of it (amount_levels). "
                             "Not summed by default: use the measure, which takes it once per value.")
            elif (t.name, c.name) in header_level:
                summarize = "none"
                lines.append(f"\t/// An amount at the level of {t.name}; {', '.join(header_level[(t.name, c.name)])} has several rows per "
                             f"{t.name} row. Not summed by default: use the measure, never a sum over the line rows.")
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
        parts[f"definition/tables/{calendar}.tmdl"] = calendar_tmdl(calendar, name, date_range)

    rel_lines: list[str] = []
    for r in active + [x for x, _ in inactive]:
        why = next((w for x, w in inactive if x is r), "")
        rel_lines.append(f"relationship {_tag(name, 'relationship', r.source, r.source_cols[0], r.target)}")
        if why:
            rel_lines.append("\tisActive: false")
        rel_lines.append(f"\tfromColumn: {tmdl_name(r.source)}.{tmdl_name(r.source_cols[0])}")
        rel_lines.append(f"\ttoColumn: {tmdl_name(r.target)}.{tmdl_name(r.target_cols[0])}")
        rel_lines.append("")
    # The calendar joins the active relationships under the same rule: one active path between any two tables. A date
    # relationship whose fact is already connected to the calendar through active links (a second date column of the same
    # fact, or a line table whose header already relates to the calendar) stays inactive.
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for r in active:
        parent[find(r.source)] = find(r.target)
    date_rels = []
    for fact, col in dates if calendar else []:
        joined = find(fact) == find("\x00calendar")
        if not joined:
            parent[find(fact)] = find("\x00calendar")
        why = "" if not joined else (
            f"{fact} already relates to {calendar} through another date column" if any(d["fact"] == fact and d["active"] for d in date_rels) else
            f"{fact} already reaches {calendar} through active relationships (one active path between two tables)")
        date_rels.append({"fact": fact, "column": col, "active": not joined, **({"why": why} if why else {})})
        rel_lines.append(f"relationship {_tag(name, 'relationship', fact, col, calendar)}")
        if joined:
            rel_lines.append("\tisActive: false")
        rel_lines += [f"\tfromColumn: {tmdl_name(fact)}.{tmdl_name(col)}", f"\ttoColumn: {tmdl_name(calendar)}.Date", ""]
    if rel_lines:                       # with nothing to relate the document is left out: a TMDL document must hold an object,
        parts["definition/relationships.tmdl"] = "\n".join(rel_lines)      # and a comment-only one stops Power BI Desktop (see the module docstring)
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
               "## Relationships", ""]
    if active or inactive:
        readme += ["| From | To | Rule | Active |", "| --- | --- | --- | --- |"]
        for r in active:
            readme.append(f"| `{r.source}.{r.source_cols[0]}` | `{r.target}.{r.target_cols[0]}` | {plan.label(r.rule)} | yes |")
        for r, why in inactive:
            readme.append(f"| `{r.source}.{r.source_cols[0]}` | `{r.target}.{r.target_cols[0]}` | {plan.label(r.rule)} | no: {why} |")
    if not rel_lines:
        readme += [f"None in the model, so there is no `definition/relationships.tmdl`: a TMDL document must hold an object, and Power BI "
                   "Desktop (2.151, 30 October 2026) refuses one that holds only a comment (`InvalidLineType`, document `./relationships`, "
                   "line 1). " + (f"The plan found {len(composite)} relationship(s) that the tables cannot express yet; each is under "
                                  "Decisions to check with what the lakehouse needs." if composite else "The plan found no relationship between these tables.")]
    elif composite:
        readme += ["", f"{len(composite)} relationship(s) of the plan are not in the file: see Decisions to check."]
    readme += ["", "## Decisions to check", ""]
    for r, why in inactive:
        readme.append(f"- `{r.source}.{r.source_cols[0]} -> {r.target}` is inactive: {why}. Use USERELATIONSHIP in DAX or pick another active one.")
    for r in composite:
        readme.append(f"- `{r.source}.{'+'.join(r.source_cols)} -> {r.target}.{'+'.join(r.target_cols)}` ({plan.label(r.rule)}) is not in the model: "
                      f"{why_not(r)}.")
    for t, k in dup.items():
        if t in names:
            readme.append(f"- `{t}.{'+'.join(k['columns'])}` is the plan's key of `{t}` but not unique in the rows ({k['verdict']}): no `isKey`, "
                          "and no relationship is built onto it.")
    for t in keyless:
        readme.append(f"- `{t}` has no key: it is in the model but nothing relates to it (rule K3). Give `keys` to change that.")
    for t in multi_key:
        readme.append(f"- `{t}` has a composite key ({'+'.join(plan.keys[t][0])}): no `isKey` column and nothing can relate to it one-to-many "
                      "until the lakehouse has a combined key column (a gold view); Direct Lake allows no calculated column for it.")
    readme += ["", "## Uncertain, written down rather than guessed", "",
               "- Key uniqueness: `isKey` is set from the plan's inferred keys (rules K0–K5). Power BI refuses a one-side column with "
               "duplicates when the model is framed; run `validate_plan` first.",
               f"- `schemaName`: {'written for every partition' if with_schema else 'omitted because a lakehouse without schemas exposes dbo without one'} "
               "(docs: direct-lake-power-bi-desktop.md; the REST property `defaultSchema` tells the two kinds of lakehouse apart). "
               "If this is wrong for your lakehouse, add or remove the `schemaName` lines.",
               "- Filter direction is single (dimension to fact), the TMDL default; nothing is set to both directions.",
               "- Dates are `dateTime` (TMDL has no date type).",
               "- The syntax follows Microsoft's published sample definitions (microsoft/fabric-rest-api-specs and the PBIP "
               "samples listed in fabric_backend/semantic_model.py), and nothing beyond what they use.",
               ""]
    readme += ["## Suggested measures", ""] + ([f"- `{m['name']}` = `{m['expression']}` on `{m['table']}`: {m['why']}." for m in measures]
                                              or ["- None: the plan has no fact table (a table that points at others and that nothing points at)."])
    readme += ["", "## Amounts at header level", ""] + ([(f"- `{t}.{c}`: a price on `{t}`, read by the measure `{feeds[(t, c)]}` through RELATED; "
                                                             f"`summarizeBy: none` and no sum of its own (a sum of prices over the line rows would count "
                                                             "each price once per line)." if (t, c) in feeds else
                                                             f"- `{t}.{c}`: an amount on `{t}`, which {', '.join(f'`{x}`' for x in ls)} has "
                                                             f"several rows for; `summarizeBy: none` and a measure on `{t}` instead. Order amount and "
                                                             "line amount are different levels: summed over the line rows it would count each "
                                                             f"`{t}` row once per line.") for (t, c), ls in header_level.items()]
                                                           or ["- None: no table that another one has several rows for carries an amount column."])
    readme += ["", "## Order amount (quantity × price)", ""]
    readme += [f"- `{m['name']}` = `{m['expression']}` on `{m['table']}`: {m['why']}" for m in order_amount["measures"]]
    readme += [f"- `{x['line']}` keeps its own amount: {x['why']}." for x in order_amount["own_amounts"]]
    readme += [f"- `{x['line']}.{x['quantity']}` × a price ({', '.join(x['prices'])}): not created, {x['why']}." for x in order_amount["not_created"]]
    if not any(order_amount.values()):
        readme.append("- None: no table has a quantity column with a price on a table it points at (names: quantity, qty, menge; price, "
                      "list_price, unit_price, netpr), or the line carries an amount of its own.")
    readme += ["", "No measure sums an id, a code, a year or a reference: they use the same rule as `summarizeBy`. Dimension tables get "
               "no sums; their numbers describe one row.", "", "## Date table", ""]
    if calendar:
        readme += [f"`{calendar}` is a calculated table (`CALENDAR` with `Year`, `Month` and `Year Month`) marked as the date table (`dataCategory: Time`, "
                   "`isKey` on `Date`); a calculated table that references no Direct Lake table is allowed in Direct Lake on SQL "
                   "(direct-lake-overview.md). `Year Month` is text such as 2026-10, so a chart by month keeps the years apart."]
        if cal_from_data:
            readme.append(f"- The range {cal_first}-01-01 to {cal_last}-12-31: the whole years from the first to the last date in the related "
                          f"date columns ({date_range[0]} to {date_range[1]}, read when the model was made). Rows added later outside it "
                          "have no date to filter by until the range is widened in the partition's `source`.")
        else:
            readme.append(f"- The range {CALENDAR_FIRST_YEAR}-01-01 to {CALENDAR_LAST_YEAR}-12-31 is a placeholder: this draft reads no rows. Set it to "
                          "your data's first and last year in the partition's `source`, or rows outside it have no date to filter by.")
        readme += [f"- `{d['fact']}.{d['column']} -> {calendar}.Date`" + (" (active)" if d["active"] else f" (inactive: {d['why']}; use USERELATIONSHIP)")
                   for d in date_rels]
        readme += [f"- `{f}.{c}` carries a time of day and is not related: Direct Lake on SQL does not relate on the date part of a datetime "
                   "(direct-lake-overview.md). Add a date column (for example in a gold view) and relate that." for f, c in timed]
    elif lookalike:
        readme += [f"- None generated: the plan already has a table that looks like a date table ({', '.join(lookalike)}). Mark it as the date "
                   "table in Power BI (Table tools -> Mark as date table) once its date column is unique."]
    else:
        readme += ["- None generated: no fact table has a date column."]
    readme += ["", "## Opening it in Power BI Desktop", "",
               "- If the files came as a zip (the Power BI project from /check), extract the whole zip first and open the `.pbip` from the "
               "extracted folder. Opening the `.pbip` from inside the zip extracts that one file only, and Power BI Desktop stops with "
               "\"definition.pbism is missing\".",
               "- Every `.tmdl` document here starts with an object; one that would hold only comments is not written, because the TMDL "
               "parser refuses it (seen on 30 October 2026 with a relationships.tmdl of one comment line).",
               "- The shop project from /check was opened in Power BI Desktop 2.151 on 30 October 2026; the data shows once the tables are "
               "in a Fabric lakehouse and `expressions.tmdl` names its SQL analytics endpoint."]
    for path in [p for p, c in parts.items() if p.endswith(".tmdl") and not has_object(c)]:
        del parts[path]                 # the rule above, applied to every document (none is expected here; relationships is handled above)
    readme += ["", "## Files", ""] + [f"- `{p}`" for p in parts] + [""]
    parts["README.generated.md"] = "\n".join(readme)
    summary = {"tables": len(chosen), "roles": {t.name: role_of.get(t.name) for t in chosen},
               "relationships_active": len(active), "relationships_inactive": len(inactive),
               "relationships_not_expressible": len(composite), "keyless": keyless, "composite_keys": multi_key,
               "storage_mode": "directLake (SQL analytics endpoint)", "compatibility_level": COMPATIBILITY_LEVEL,
               "inactive": [{"source": r.source, "columns": r.source_cols, "target": r.target, "why": why} for r, why in inactive],
               "not_expressible": [{"source": r.source, "columns": r.source_cols, "target": r.target, "target_columns": r.target_cols,
                                    "rule": r.rule, "why": why_not(r), **({"key_not_unique": True} if r.target in dup else {})}
                                   for r in composite],

               "measures": [{k: m[k] for k in ("table", "name", "expression", "why")} for m in measures],
               "header_amounts": [{"table": t, "column": c, "lines": ls, "summarize_by": "none"} for (t, c), ls in header_level.items()],
               "order_amount": {"measures": [{k: m[k] for k in ("table", "name", "expression", "dimension", "price", "via", "rule", "price_note")}
                                             for m in order_amount["measures"]],
                                "own_amounts": order_amount["own_amounts"], "not_created": order_amount["not_created"]},
               "date_table": ({"name": calendar, "marked_as_date_table": True, "related": date_rels,
                               "not_related": [{"fact": f, "column": c, "why": "datetime with a time of day"} for f, c in timed],
                               "range": (f"{cal_first}-01-01 to {cal_last}-12-31 (the data's years, {date_range[0]} to {date_range[1]})" if cal_from_data
                                         else f"{CALENDAR_FIRST_YEAR}-01-01 to {CALENDAR_LAST_YEAR}-12-31 (placeholder; see README)")} if calendar else None)}
    if flat:
        summary["flat_amounts"] = [{"table": t, "column": c, "header": h, "summarize_by": "none"} for (t, c), h in flat.items()]
    if dup.keys() & names:                                         # n150: only when the rows showed one
        summary["keys_not_unique"] = [{"table": t, "columns": list(k["columns"]), "rows": k["rows"], "distinct": k["distinct"],
                                       "nulls": k["nulls"]} for t, k in dup.items() if t in names]
    return {"parts": parts, "summary": summary}
