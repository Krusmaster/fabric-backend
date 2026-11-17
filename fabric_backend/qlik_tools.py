"""Krusgraph Migrate, from Qlik to Power BI: the three chat tools (round Q2, docs/QLIK-MIGRATION-PRODUCT.md).

- `qlik_plan`: a Qlik load script in; tables, keys, associations (synthetic keys and circular references included)
  out, as Krusgraph's plan (`keys` and `confirmed`, the arguments the planning and building tools take) and as a
  proposed star schema.
- `qlik_measures_draft`: master measures and chart expressions as DAX where a fixed rule carries them over, with
  what was not translated and why.
- `qlik_reconcile_draft`: the KPI values exported from the Qlik app, the T-SQL that computes the same KPIs on the
  migrated tables, and the comparison table.

All three read text they are given and return text: they are read-only, they use fixed rules and no AI model, and they
connect to nothing on the Qlik side. Only `qlik_plan` may read Fabric, and only when a workspace and a source are named:
it then counts the keys and links in the landed tables. The hosted server keeps no script, expression or value after
the call; the local server (`fabric-backend-mcp`, the open-source package on the user's own machine) answers the same
three tools without the text leaving that machine.

The tools themselves are defined in `server.py` and `mcp_server.py`, as every tool is (the site and the tests read
those files); this module holds their parameter types and their answers.

The answers carry `kg_card`: the result in plain words (one line, at most five more, and notes), as the other tools'
cards have it. Tested on synthetic scripts and rows and on public load scripts (tests/fixtures/qlik/SOURCES.md); not
on a script from a customer's Qlik installation. The rules about Qlik are Unverified (see fabric_backend/qlik/).
Qlik is a trademark of QlikTech International AB and Power BI of Microsoft; Krusgraph is affiliated with neither.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

import functools

from . import qlik as _qlik
from .dialects import TSQL
from .errors import PlatformError
from .migration_read import ReadError
from .qlik import measures as _measures, reconcile as _reconcile, star as _star

NAMES = ("qlik_plan", "qlik_measures_draft", "qlik_reconcile_draft")
TITLES = {"qlik_plan": "Plan from a Qlik load script (nothing created)",
          "qlik_measures_draft": "Draft DAX measures from Qlik expressions (nothing created)",
          "qlik_reconcile_draft": "Draft SQL comparing Qlik KPI values with the migrated tables (runs nothing)"}
NOTE = ("Read by fixed rules; no AI model and no connection to Qlik. Tested on synthetic and public load scripts, not on a "
        "customer's Qlik installation. A draft for a person to review.")


def _d(text: str):
    return Field(description=text)


Script = Annotated[str, _d("Qlik load script as text (a .qvs file's content). Read, not run, not kept.")]
OptionalScript = Annotated[str | None, _d("The app's load script: says which table holds each field. Default none.")]
OptionalWorkspace = Annotated[str | None, _d("Fabric workspace with the landed tables, to count in them. Default none: "
                                             "nothing is counted.")]
OptionalSource = Annotated[str | None, _d("Lakehouse, warehouse or SQL database with the landed tables. Needed with workspace.")]
LandedSchema = Annotated[str, _d('Schema of the landed tables. Default "dbo".')]
TableNames = Annotated[dict[str, str] | None, _d(
    'Landed name per Qlik table where it differs. Example: {"Orders": "sales_orders"}.')]
Detail = Annotated[str, _d('"summary" (default) or "full" (each column\'s source and the script\'s steps per table).')]
Measures = Annotated[list[dict] | str, _d(
    'List of {"name", "expression"}, or text with `Name = expression` per line. At most 500.')]
Tmdl = Annotated[bool, _d("true adds the drafts as TMDL lines. Default false.")]
Kpis = Annotated[list[dict], _d(
    '{"name", "expression", "value"}, or {"name", "expression", "by": [fields], "values": [{<field>: ..., "value": n}]} '
    'per grain value. Exported with no selections. At most 50.')]
Tolerance = Annotated[float, _d("Largest difference that counts as equal. Default 0.005.")]
Results = Annotated[dict[str, list[dict]] | None, _d(
    "Rows a statement returned, per KPI name: fills the comparison in. Default none.")]
Relationships = Annotated[list[dict] | None, _d(
    "Relationships to join through instead of the script's: qlik_plan's plan.confirmed. Default none.")]
Count = Annotated[bool, _d("true counts the keys and links in the tables of `schema` behind this server. Default false.")]


# The local server's descriptions (mcp_server.py), kept here with the tools they describe.
LOCAL_DOCS = {
    "qlik_plan": """Reads a Qlik load script: its tables, keys and associations as a plan, each synthetic key in one of five
    cases, circular references and a proposed star schema. Requires script. With count=true it counts keys and links
    in the tables of `schema` behind this local server; by default it counts nothing. The script stays on this
    machine. Returns JSON: plan.keys and plan.confirmed, statements not read, kg_card. Fixed rules, no AI model, no
    connection to Qlik. Not tested on a customer's Qlik installation. Errors: {error, kind, hint}.""",
    "qlik_measures_draft": """Drafts DAX from Qlik master measures or chart expressions by fixed rules, each labelled translated,
    suggested (with when it may differ from Qlik) or not_translated (with the reason). Requires measures. Covers Sum,
    Min, Max, Avg, Count, arithmetic, If, literal set modifiers and TOTAL; not Aggr, P(), E(), searches, alternate
    states or run-time dollar-sign expansion. Returns JSON with counts and kg_card. Runs no Qlik and no DAX; creates
    nothing; no AI model. Errors: {error, kind, hint}.""",
    "qlik_reconcile_draft": """Writes one T-SQL statement per KPI: the values exported from Qlik, the same KPI computed on the migrated
    tables at the same grain, and the comparison (qlik_value, new_value, difference, status). Requires script and
    kpis. Runs nothing; with results (the rows a statement returned) it fills the comparison in. A KPI no rule covers
    gets no SQL and the reason; a difference is listed as open, never explained by guess. Returns JSON with kg_card.
    No AI model. Errors: {error, kind, hint}.""",
}


def local_doc(fn):
    """Gives a local tool its description from LOCAL_DOCS, as its docstring."""
    fn.__doc__ = LOCAL_DOCS[fn.__name__]
    return fn


def bad_input(fn):
    """A script, a measure list or a KPI list that cannot be read is the caller's to fix: kind bad_input, with the
    reader's own sentence, instead of an unexpected error."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (ValueError, ReadError) as e:
            raise PlatformError("bad_input", str(e), "Correct the argument and call again. Nothing was created, and "
                                                     "nothing was kept from this call.") from None
    return wrapper


def _n(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _listed(xs, most: int = 3) -> str:
    xs = [str(x) for x in xs]
    return ", ".join(xs[:most]) + (f" and {len(xs) - most} more" if len(xs) > most else "")


# ------------------------------------------------------------------ qlik_plan ----------------------------------------

def _plan_card(out: dict) -> dict:
    r, cov, star = out["read"], out["statements"], out["star_schema"]
    rels = [x for x in out["relationships"] if x["in_plan"] == "relationship"]
    lines = []
    syn = out["synthetic_keys"]
    if syn:
        words = {"one_field_links": "one field links", "composite_key": "a combined key", "two_facts_sharing_dimensions":
                 "two facts sharing dimensions", "a_person_decides": "yours to decide", "not_decided": "not decided until the rows are counted"}
        cases: dict[str, int] = {}
        for s in syn:
            cases[words[s["case"]]] = cases.get(words[s["case"]], 0) + 1
        lines.append(f"{_n(len(syn), 'synthetic key')}: " + ", ".join(f"{n} {w}" for w, n in cases.items()) + ".")
    if out["circular_references"]:
        kept = sum(1 for c in out["circular_references"] if c["in_the_plan"].startswith("every link"))
        gone = len(out["circular_references"]) - kept
        lines.append(f"{_n(len(out['circular_references']), 'circular reference')}: "
                     + (f"{gone} no longer a loop in the plan" if gone else "")
                     + (", " if gone and kept else "") + (f"{kept} kept with one path inactive" if kept else "") + ".")
    lines.append(f"Proposed star schema: {_n(len(star['facts']), 'fact')}, {_n(len(star['dimensions']), 'dimension')}"
                 + (f", {_n(len(star['tables_in_between']), 'table')} in between" if star["tables_in_between"] else "")
                 + (f", {_n(len(star['proposed_dimensions']), 'new dimension')} to build" if star["proposed_dimensions"] else "") + ".")
    lines.append("The one sides were counted in the rows." if out["decided_by"] == "counts in the rows"
                 else "Nothing was counted: the one sides come from the names until the tables are landed.")
    if cov["not_read"] or cov["control_flow"] or cov["include"]:
        parts = ([f"{_n(cov['not_read'], 'statement was', 'statements were')} not read"] if cov["not_read"] else []) \
            + ([f"{_n(cov['control_flow'], 'control statement was', 'control statements were')} listed, not run"] if cov["control_flow"] else []) \
            + ([f"{_n(cov['include'], 'included file was', 'included files were')} not given"] if cov["include"] else [])
        lines.append("; ".join(parts)[0].upper() + "; ".join(parts)[1:] + ".")
    notes = []
    decide = star["a_person_decides"]
    if decide:
        notes.append({"line": f"{_n(len(decide), 'thing is', 'things are')} yours to decide.",
                      "items": [(f"{' and '.join(d['between'])} on {', '.join(d['fields'])}" if "between" in d
                                 else f"{d['field']} in {', '.join(d['tables'])}") + f": {d['why']}" for d in decide][:60]})
    if star["changes"]:
        notes.append({"line": f"{_n(len(star['changes']), 'change')} to make for a star schema.", "items": star["changes"][:60]})
    moved = [x["moves_numbers"] for x in out["relationships"] if x.get("moves_numbers")] + [
        o["moves_numbers"] for s in syn for o in s.get("other_fields", []) if o.get("moves_numbers")]
    if moved:
        notes.append({"line": f"{_n(len(moved), 'finding moves', 'findings move')} numbers between Qlik and the new model.",
                      "items": moved[:60]})
    return {"title": "Plan from a Qlik load script",
            "result": f"Read {_n(r['tables'], 'table')} and {_n(r['linking_fields'], 'linking field')} from the load script; "
                      f"{_n(len(rels), 'relationship is', 'relationships are')} in the plan. Nothing was created.",
            "lines": lines[:5], **({"notes": notes} if notes else {})}


def plan_answer(script: str, execute=None, schema: str = "dbo", tables: dict[str, str] | None = None,
                detail: str = "summary", dialect=TSQL, landed=None) -> dict:
    """qlik_plan's answer. `execute` runs read-only counting queries over the landed tables in `schema`; without it
    nothing is counted. `landed` is the landed tables' own Schema (their types), when it was read."""
    if detail not in ("summary", "full"):
        raise ValueError('detail must be "summary" or "full"')
    read = _qlik.read_script(script)
    mapping = _qlik.map_associations(read, execute, schema=schema, dialect=dialect, tables=tables)
    plan, also = _qlik.to_plan(mapping, landed if landed is not None else schema)
    by_name = {t["name"]: t for t in read["tables"]}
    out_tables = []
    for t in mapping["tables"]:
        src = by_name[t["qlik"]]
        row = dict(t)
        if "$(" in t["qlik"]:
            row["name_built_when_the_script_runs"] = "the table's name holds a dollar-sign expansion: say its real name in tables"
        if src.get("fields_unknown"):
            row["columns_not_in_the_script"] = src["fields_unknown"]
        if not t["as_loaded"]:
            row["shaped_in_the_script"] = len(src["steps"])
        if detail == "full":
            row["sources"] = src["sources"]
            row["steps"] = src["steps"]
            row["column_sources"] = [{k: v for k, v in c.items() if k != "column"} | {"column": c["column"]} for c in src["columns"]]
        out_tables.append(row)
    keys = {t["table"]: t["key"] for t in mapping["tables"] if "key" in t}
    confirmed = [{"source": r["source"], "source_cols": r["source_cols"], "target": r["target"], "target_cols": r["target_cols"]}
                 for r in mapping["relationships"] if r["in_plan"] == "relationship"]
    out = {
        "kind": "qlik_plan",
        "note": NOTE,
        "read": {"tables": len(read["tables"]), "linking_fields": len(read["associations"]),
                 "synthetic_keys": len(read["synthetic_keys"]), "circular_references": len(read["circular_references"]),
                 "mapping_tables": len(read["mapping_tables"]), "calculated_fields": len(read["calculated_fields"]),
                 "dollar_expansions": read["dollar_expansions"], "section_access": read["section_access"]["present"]},
        "statements": _star.statement_coverage(read),
        "decided_by": mapping["decided_by"],
        "tables": out_tables,
        "relationships": mapping["relationships"],
        "synthetic_keys": mapping["synthetic_keys"],
        "circular_references": mapping["circular_references"],
        "shared_fields_with_no_key_side": mapping["shared_fields_with_no_key_side"],
        "two_paths": mapping["two_paths"],
        "undecided": mapping["undecided"],
        "plan": {"keys": keys, "confirmed": confirmed,
                 "use": "pass keys and confirmed, as they are, to plan_backend, validate_plan, semantic_model_draft and the "
                        "creating tools once the tables are landed under these names",
                 "also_found_by_name": also,
                 "also_found_note": "links Krusgraph's name rules would add that were not associations in Qlik: not in the plan"},
        "star_schema": _star.star_schema(mapping),
        "mapping_tables": [{"table": u["table"], "field": u["field"], "map": u["map"], "rebuild": u["rebuild"]}
                           for u in read["mapping_uses"]],
        "renamed_for_the_lakehouse": read["renamed_for_the_lakehouse"],
        "differences_that_move_numbers": mapping["differences_that_move_numbers"],
        "counting": mapping["counting"],
        "includes": read["includes"],
        "not_read": read["not_read"],
        "next": [
            "Land the tables in a lakehouse under the names in `tables`, from the original sources; where a table is shaped "
            "in the script, rebuild its steps (detail=\"full\" lists them).",
            "Ask again with workspace and source: the keys and links are then counted in the rows, and each synthetic key "
            "is decided by counts.",
            "qlik_measures_draft drafts the measures; qlik_reconcile_draft compares exported KPI values with the migrated tables.",
        ],
    }
    if read["section_access"]["present"]:
        out["section_access"] = ("the script has a Section Access part: who may see which rows. It is not read into the plan; "
                                 "row-level security in the new model is a person's work")
    out["kg_card"] = _plan_card(out)
    return out


# ------------------------------------------------------------------ qlik_measures_draft ------------------------------

def measures_answer(measures, script: str | None = None, tables: dict[str, str] | None = None, tmdl: bool = False) -> dict:
    read = _qlik.read_script(script) if script else None
    out = _measures.draft(measures, read, tables)
    c = out["counts"]
    out["note"] = NOTE + " The DAX has not been run, and no share of an app's expressions is promised: these counts are of the expressions given."
    out["labels"] = {"translated": "every part has a rule and nothing depends on where the measure is used",
                     "suggested": "a rule gives DAX; may_differ says when it gives another number than Qlik",
                     "not_translated": "no rule; why says what stopped it, and a person decides"}
    if tmdl:
        out["tmdl"] = _measures.tmdl(out)
    why: dict[str, list[str]] = {}
    for m in out["measures"]:
        if m["label"] == "not_translated":
            why.setdefault(m["why"].split(":")[0][:80], []).append(m["name"])
    lines = []
    if c["translated"]:
        lines.append(f"Translated by rule: {_listed([m['name'] for m in out['measures'] if m['label'] == 'translated'])}.")
    if c["suggested"]:
        lines.append(f"Suggested, may differ from Qlik: {_listed([m['name'] for m in out['measures'] if m['label'] == 'suggested'])}.")
    if c["not_translated"]:
        lines.append(f"Not translated: {_listed([m['name'] for m in out['measures'] if m['label'] == 'not_translated'])}.")
    if not script:
        lines.append("No load script was given, so the fields have no table yet.")
    notes = [{"line": f"{_n(len(names), 'measure')}: {reason}.", "items": names[:60]} for reason, names in why.items()]
    differ = [f"{m['name']}: {x}" for m in out["measures"] for x in m.get("may_differ", [])]
    if differ:
        notes.append({"line": f"{_n(len(differ), 'case')} where a suggested measure may differ from Qlik.", "items": differ[:60]})
    out["kg_card"] = {"title": "Measures drafted from Qlik expressions",
                      "result": f"{c['translated']} of {_n(c['total'], 'expression')} translated by rule, {c['suggested']} suggested, "
                                f"{c['not_translated']} not translated. Nothing was created and no DAX was run.",
                      "lines": lines[:5], **({"notes": notes} if notes else {})}
    return out


# ------------------------------------------------------------------ qlik_reconcile_draft -----------------------------

def reconcile_answer(script: str, kpis, schema: str = "dbo", tolerance: float = _reconcile.DEFAULT_TOLERANCE,
                     results: dict | None = None, tables: dict[str, str] | None = None, confirmed: list[dict] | None = None) -> dict:
    read = _qlik.read_script(script)
    out = _reconcile.draft(read, kpis, schema=schema, tolerance=tolerance, results=results, tables=tables, confirmed=confirmed)
    out["note"] = NOTE + " The statements have not been run by Krusgraph."
    t = out["totals"]
    filled = results is not None and t["to_compute"] < t["rows"]
    lines = []
    if filled:
        lines.append(f"{_n(t['equal'], 'row')} equal within {tolerance:g}, {t['different']} different, "
                     f"{t['only_in_qlik']} only in Qlik, {t['only_on_the_migrated_tables']} only on the migrated tables.")
        if t["to_compute"]:
            lines.append(f"{_n(t['to_compute'], 'row has', 'rows have')} no result yet.")
        if t["different"] or t["only_in_qlik"] or t["only_on_the_migrated_tables"]:
            lines.append("Each difference is open: no reason is named until a count reproduces it.")
    else:
        lines.append(f"{_n(t['rows'], 'exported value')} to compare; run each statement on the SQL analytics endpoint.")
    if t["without_sql"]:
        lines.append(f"{_n(t['without_sql'], 'KPI has', 'KPIs have')} no SQL: "
                     + _listed([k['name'] for k in out['kpis'] if not k['sql']]) + ".")
    notes = []
    no_sql = [f"{k['name']}: {k['why_no_sql']}" for k in out["kpis"] if not k["sql"]]
    if no_sql:
        notes.append({"line": f"{_n(len(no_sql), 'KPI')} without SQL, and why.", "items": no_sql[:60]})
    diff = [f"{k['name']}" + "".join(f", {g} {r.get(g)}" for g in k["by"]) + f": Qlik {r['qlik_value']}, migrated {r['new_value']} ({r['status']})"
            for k in out["kpis"] for r in k["comparison"]["rows"] if r["status"] in ("different", "only in Qlik", "only on the migrated tables")]
    if diff:
        notes.append({"line": f"{_n(len(diff), 'row differs', 'rows differ')}.", "items": diff[:60]})
    out["kg_card"] = {
        "title": "KPI comparison after a migration from Qlik",
        "result": (f"Compared {_n(t['rows'] - t['to_compute'], 'row')} for {_n(t['kpis'], 'KPI')}: {t['equal']} equal, "
                   f"{t['rows'] - t['to_compute'] - t['equal']} not." if filled else
                   f"SQL written for {t['with_sql']} of {_n(t['kpis'], 'KPI')}. Nothing was run."),
        "lines": lines[:5], **({"notes": notes} if notes else {})}
    return out
